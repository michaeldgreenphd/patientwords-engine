"""Spend accounting for the Petri lane (design memo section 13): prices from the
engine's own tables, the pre-flight bound that refuses a run before any model
call, the post-run re-pricing of Inspect's usage into a cost sidecar the
ledger can read, and the billing channel a sidecar must state explicitly.

Inspect's bundled price table has no priced entries, so every model role gets
its price from here: the provider registry (data/advice_providers.json), the
engine's Anthropic table (medlang_circuits.evaluate_models.PRICING) and,
for anything neither names, the engine's conservative fallback rate. The
source is recorded per model; nothing is priced by a fuzzy match.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .framework import ROOT, load_json, sha256_text

PROVIDERS_PATH = ROOT / "data" / "advice_providers.json"
FALLBACK_PRICING = (10.0, 50.0)          # scripts/advice_eval.py _FALLBACK_PRICING, USD per million tokens
ZERO_PRICE_MODELS = ("mockllm/model", "mockllm/judge", "none/none")      # mockllm/judge: the local tests' judge (PR B)
# Prompt-cache tokens, which Inspect reports apart from `input_tokens` (it subtracts cached reads from an OpenAI-shaped
# prompt count, _openai.py model_output_from_openai; Anthropic reports reads and writes apart natively). Neither price
# table carries a cache rate (data/advice_providers.json prices "worst-case, cache-miss rates"), so each is bounded
# from the input rate, never priced at zero: a cache read costs at most the input rate (Anthropic ~0.1x, OpenAI below
# 1x), and a cache write at most twice it (Anthropic: 1.25x for the 5-minute TTL, 2x for the 1-hour TTL). Fail-closed
# upper bounds, not list prices; a registry cache-rate column would be the place to lower them (2026-09-23).
CACHE_READ_INPUT_MULTIPLIER = 1.0
CACHE_WRITE_INPUT_MULTIPLIER = 2.0


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float
    source: str

    @property
    def cache_read_per_mtok(self) -> float:
        return self.input_per_mtok * CACHE_READ_INPUT_MULTIPLIER

    @property
    def cache_write_per_mtok(self) -> float:
        return self.input_per_mtok * CACHE_WRITE_INPUT_MULTIPLIER

    def cost(self, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
        return (input_tokens * self.input_per_mtok / 1e6 + output_tokens * self.output_per_mtok / 1e6
                + cache_read_tokens * self.cache_read_per_mtok / 1e6 + cache_write_tokens * self.cache_write_per_mtok / 1e6)


def _engine_pricing() -> dict[str, tuple[float, float]]:
    try:
        from medlang_circuits.evaluate_models import PRICING  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - the package may be absent in the lane's 3.12 environment
        return {}
    out: dict[str, tuple[float, float]] = {}
    for key, value in dict(PRICING).items():
        try:
            if isinstance(value, dict):
                out[str(key)] = (float(value["input"]), float(value["output"]))
            else:
                out[str(key)] = (float(value[0]), float(value[1]))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return out


def split_inspect_name(model: str) -> tuple[str, str]:
    """"provider/model..." -> (provider, model); a bare name is Anthropic by the
    registry's convention."""
    if "/" in model:
        provider, rest = model.split("/", 1)
        return provider, rest
    return "anthropic", model


def registry_spec_to_inspect(spec: str, registry: dict | None = None) -> str:
    """The judge takes a registry spec (scripts/advice_eval.py `_resolve_spec`:
    `provider:model`, a bare provider the registry knows, or a bare Anthropic
    model id); prices are keyed by Inspect's `provider/model` form.
    `openrouter:vendor/model` becomes `openrouter/vendor/model`, which
    `resolve_price` prices by vendor entry. A bare provider expands to its
    `consumer_default`, the model the judge actually calls (Codex round 5:
    `openai` used to price as `anthropic/openai`, the fallback rate), and a
    provider without one is refused, as the resolver refuses it."""
    spec = spec.strip()
    if spec in ZERO_PRICE_MODELS:
        # already an Inspect name, and the only one a judge takes that no registry knows: expanding it to
        # `anthropic/mockllm/judge` priced the local mock judge at the 10/50 fallback and labelled its rows
        # provider-measured (Codex round 1 on PR #28)
        return spec
    if ":" in spec:
        provider, model = spec.split(":", 1)
        return f"{provider}/{model}"
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    cfg = registry.get(spec) if isinstance(registry, dict) else None
    if isinstance(cfg, dict):
        default = str(cfg.get("consumer_default") or "").strip()
        if not default:
            raise ValueError(f"judge spec {spec!r} names a registry provider with no consumer_default; give provider:model")
        return f"{spec}/{default}"
    return f"anthropic/{spec}"


def resolve_registry_price(spec: str, registry: dict | None = None, engine_pricing: dict | None = None) -> Price:
    """`resolve_price` for a registry-form spec (the judge's), under one
    registry load for both the spec expansion and the price."""
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    return resolve_price(registry_spec_to_inspect(spec, registry), registry, engine_pricing)


def registry_provider(spec: str, registry: dict | None = None) -> str:
    """The registry provider a judge spec names, by the advice resolver's own
    rule (scripts/advice_eval.py `_resolve_spec`): `provider:model`; a bare
    provider name that the registry knows (expanded to its consumer default);
    otherwise a bare Anthropic model id (Codex round 4)."""
    spec = spec.strip()
    if ":" in spec:
        return spec.split(":", 1)[0]
    if isinstance(registry, dict) and spec in registry and isinstance(registry.get(spec), dict):
        return spec
    return "anthropic"


def judge_billing_channel(spec: str, registry: dict | None = None) -> str:
    """The prepaid account a judge spec bills, derived from the provider
    registry's `key_env` rather than the spec's prefix: `openai:`, `xai:`,
    `deepseek:` and `moonshot:` route through OPENROUTER_API_KEY and bill the
    OpenRouter account (Codex round 3). Anything else, an unknown provider
    included, stays on the Anthropic channel, the one the daily ceiling bounds
    (fail closed, as fire_trigger.petri_channels does with the same rule). A
    provider billed through a third key (`google`, GEMINI_API_KEY) is booked
    here as Anthropic but bills its own vendor, so `cli preflight`, `cli run`
    and `cli judge` refuse such a spec before any call
    (`judge_key_routing_problems`, 2026-09-23)."""
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    cfg = registry.get(registry_provider(spec, registry)) if isinstance(registry, dict) else None
    key_env = cfg.get("key_env") if isinstance(cfg, dict) else None
    return "openrouter" if key_env == "OPENROUTER_API_KEY" else "anthropic"


def _registry_price(cfg: Any, name: str, label: str) -> Price | None:
    """A provider entry's own price for `name`: its `pricing` table, else its
    `default_pricing`; None when the entry names neither."""
    if not isinstance(cfg, dict):
        return None
    table = cfg.get("pricing") or {}
    if name in table:
        return Price(float(table[name][0]), float(table[name][1]), f"registry:{label}:pricing")
    if cfg.get("default_pricing"):
        dp = cfg["default_pricing"]
        return Price(float(dp[0]), float(dp[1]), f"registry:{label}:default_pricing")
    return None


def _openrouter_price(name: str, registry: dict, engine_pricing: dict) -> Price | None:
    """`openrouter/<vendor>/<model>`. The registry's OpenRouter entry keys its
    reviewed, markup-inclusive rates by `vendor/model` and documents its
    `default_pricing` as a deliberately high GPT-tier catch-all
    (data/advice_providers.json `pricing_note`). Precedence: the OpenRouter
    per-model entry; otherwise the higher, rate by rate, of the vendor's own
    registry price (its table or default, or the engine table for Anthropic
    models) and the OpenRouter catch-all, so a vendor whose list price exceeds
    the catch-all (Codex round 2: openai's 5.25/31.5 over 5/30) never
    understates the ceiling and a cheap vendor never undercuts the floor.
    A Petri target or judge that would reach the fallback is refused at
    pre-flight (`openrouter_price_problems`); the fallback remains for
    pricing whatever a log records."""
    ocfg = registry.get("openrouter") if isinstance(registry, dict) else None
    if isinstance(ocfg, dict) and name in (ocfg.get("pricing") or {}):
        entry = ocfg["pricing"][name]
        return Price(float(entry[0]), float(entry[1]), "registry:openrouter:pricing")
    floor = Price(float(ocfg["default_pricing"][0]), float(ocfg["default_pricing"][1]),
                  "registry:openrouter:default_pricing") if isinstance(ocfg, dict) and ocfg.get("default_pricing") else None
    vendor_price: Price | None = None
    if "/" in name:
        vendor, model = name.split("/", 1)
        vendor_price = _registry_price(registry.get(vendor) if isinstance(registry, dict) else None, name, vendor)
        if vendor_price is None and vendor == "anthropic" and model in engine_pricing:
            vendor_price = Price(*engine_pricing[model], "engine:evaluate_models.PRICING")
    if vendor_price and floor:
        return Price(max(vendor_price.input_per_mtok, floor.input_per_mtok),
                     max(vendor_price.output_per_mtok, floor.output_per_mtok),
                     f"max({vendor_price.source}, {floor.source})")
    return vendor_price or floor


UNREVIEWED_OPENROUTER_PRICE = "unreviewed_openrouter_price"


def openrouter_price_problems(model: str, registry: dict | None = None) -> list[str]:
    """Why an Inspect model name may not be priced for a Petri run: an
    `openrouter/<vendor>/<model>` name with no entry of its own in the
    registry's `openrouter.pricing` table. Any other name returns [].

    Without an entry, `_openrouter_price` falls back to the higher of the
    vendor's registry price and the 5/30 catch-all. That fallback suits the
    advice lane's arbitrary slugs, where the registry documents it as a
    deliberate over-estimate, but it is not a reviewed price: it understates
    any model dearer than it (a vendor's `default_pricing` prices all its
    unlisted models at one rate), and a mistyped slug or the `openrouter/auto`
    router slug resolves to it without complaint. The Petri pre-flight bound,
    Inspect's per-sample `cost_limit` and the cost sidecar all rest on this
    one price, so a Petri run needs a reviewed, markup-inclusive entry for its
    exact slug (no fuzzy match: a `:free` or `:nitro` variant is a different
    slug). The advice lane keeps the fallback; the refusal is this lane's
    alone (2026-09-23)."""
    provider, name = split_inspect_name(model.strip())
    if provider != "openrouter":
        return []
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    ocfg = registry.get("openrouter") if isinstance(registry, dict) else None
    table = (ocfg.get("pricing") if isinstance(ocfg, dict) else None) or {}
    if name in table:
        return []
    reviewed = ", ".join(sorted(table)) or "none"
    return [f"{UNREVIEWED_OPENROUTER_PRICE}: {model!r} has no per-model entry in data/advice_providers.json "
            f"openrouter.pricing (reviewed: {reviewed}); the catch-all default_pricing is the advice lane's fallback "
            "for arbitrary slugs, and a Petri run must be bounded, limited and booked at a reviewed price, so add a "
            "dated, sourced entry before running this model"]


def resolve_price(model: str, registry: dict | None = None, engine_pricing: dict | None = None) -> Price:
    """The price for an Inspect model string, with its source. Zero-cost mock
    and placeholder models price at zero so `cost_limit` can start."""
    if model in ZERO_PRICE_MODELS:
        return Price(0.0, 0.0, "zero:mock_or_placeholder")
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    engine_pricing = engine_pricing if engine_pricing is not None else _engine_pricing()
    provider, name = split_inspect_name(model)
    if provider == "openrouter":
        priced = _openrouter_price(name, registry, engine_pricing)
        if priced is not None:
            return priced
    else:
        priced = _registry_price(registry.get(provider) if isinstance(registry, dict) else None, name, provider)
        if priced is not None:
            return priced
        if name in engine_pricing:
            return Price(*engine_pricing[name], "engine:evaluate_models.PRICING")
    return Price(*FALLBACK_PRICING, "fallback:advice_eval._FALLBACK_PRICING")


def pricing_source_digest(registry: dict | None = None) -> str:
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    return sha256_text(json.dumps({"registry": registry, "engine": _engine_pricing(), "fallback": FALLBACK_PRICING},
                                  sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def billing_channel(models: list[str]) -> str:
    """The prepaid account the target calls bill: OpenRouter only when every
    model routes there; anything else stays on the Anthropic channel, the one
    the daily ceiling bounds (fail closed, as fire_trigger.fire_lane does)."""
    named = [m for m in models if m not in ZERO_PRICE_MODELS]
    if named and all(split_inspect_name(m)[0] == "openrouter" for m in named):
        return "openrouter"
    return "anthropic"


TARGET_PROVIDERS = ("anthropic", "openrouter")
"""The Inspect providers a target may name: the two whose spend the lane books to the account that pays it.
`billing_channel` here and `fire_trigger.petri_channels` book every target that is not `openrouter/` to the
Anthropic lane, while the workflow's run step also exports OPENAI_API_KEY and GEMINI_API_KEY, so `openai/...` or
`google/...` would bill a direct vendor key against the Anthropic ceiling (2026-09-23)."""


def target_provider_problems(target: str) -> list[str]:
    """Why a target spelling cannot be run on this lane: empty when it names
    Anthropic or OpenRouter, or a zero-price test sentinel (mockllm, none/none;
    the workflow refuses those in mode run and dry_run exists for them).
    Anything else is a direct-vendor spelling that bills its own key while the
    guard books it to the Anthropic lane, refused with the OpenRouter spelling
    to use instead. The bare-name convention (`split_inspect_name`) reads a
    target with no provider as Anthropic."""
    provider, _ = split_inspect_name(target.strip())
    if provider in TARGET_PROVIDERS or provider in ("mockllm", "none"):
        return []
    return [f"target {target!r} names Inspect provider {provider!r}, which bills that vendor's own key, while the lane "
            "books every target that is not openrouter/ to the Anthropic channel and its daily ceiling; route it "
            "through OpenRouter as openrouter/<vendor>/<model> with OpenRouter's vendor slug (for example "
            "openrouter/openai/gpt-5.4-mini)"]


JUDGE_KEY_ENVS = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")
"""The registry `key_env` values a judge spec may resolve to: the two whose spend the lane books to the account
that pays it. `judge_billing_channel` here and `fire_trigger.petri_channels` book OPENROUTER_API_KEY to the OpenRouter
lane and every other key to the Anthropic lane, so a provider billed through a third key (today `google`, whose
registry entry calls the Gemini API directly with GEMINI_API_KEY) would bill that vendor while counting against the
Anthropic ceiling (2026-09-23)."""


def judge_key_routing_problems(spec: str, registry: dict | None = None) -> list[str]:
    """Why a judge spec's key routing cannot run on this lane: empty when the
    registry provider it resolves to (`registry_provider`, the advice
    resolver's rule) bills ANTHROPIC_API_KEY or OPENROUTER_API_KEY. A provider
    whose `key_env` names any other key bills that vendor's own account while
    the guard books it to the Anthropic channel and its daily ceiling, and is
    refused with the OpenRouter spelling to use instead.

    The rule is the channel mismatch and nothing more. It does not refuse a
    `key_env` naming a secret the repository does not hold: which Actions
    secrets exist is not visible from the code (an absent secret reaches the
    job as an empty string, which the provider client refuses before a call),
    so no list of held secrets is kept here to go stale. A spec the registry
    cannot resolve (an unknown provider, a manual-UI one with no `key_env`, the
    MockJudge sentinel) is left to `judge_runner.judge_spec_problems` and
    `RegistryJudge`, which refuse it by name."""
    spec = spec.strip()
    if spec in ZERO_PRICE_MODELS:
        return []
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    provider = registry_provider(spec, registry)
    cfg = registry.get(provider) if isinstance(registry, dict) else None
    key_env = cfg.get("key_env") if isinstance(cfg, dict) else None
    if not key_env or key_env in JUDGE_KEY_ENVS:
        return []
    model = spec.split(":", 1)[1] if ":" in spec else (str(cfg.get("consumer_default") or "").strip() or "<model>")
    return [f"judge spec {spec!r} resolves to registry provider {provider!r}, whose key_env {key_env} bills that "
            "vendor's own account, while the lane books every judge not billed through OPENROUTER_API_KEY to the "
            "Anthropic channel and its daily ceiling; route it through OpenRouter as openrouter:<vendor>/<model> with "
            f"OpenRouter's vendor slug (for this spec, openrouter:{provider}/{model} if OpenRouter's slug for the "
            f"vendor is {provider!r})"]


def inspect_to_registry_spec(model: str, registry: dict | None = None) -> str | None:
    """The data/advice_providers.json spec an Inspect target string maps to,
    in the resolver's canonical `provider:model` form (scripts/advice_eval.py
    `_resolve_spec`), for the two providers a target may name: `anthropic/m`
    is `anthropic:m` and `openrouter/vendor/m` is `openrouter:vendor/m`, the
    same endpoint and key in both tools. None for anything else: a mock, or a
    direct vendor route the registry does not describe (its `openai` entry
    routes through OpenRouter, not the OPENAI_API_KEY Inspect's `openai/`
    bills). The manifest recorded the Inspect string itself here until
    2026-09-23."""
    provider, name = split_inspect_name(model.strip())
    if provider not in TARGET_PROVIDERS or not name:
        return None
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    return f"{provider}:{name}" if isinstance(registry, dict) and isinstance(registry.get(provider), dict) else None


@dataclass(frozen=True)
class PreflightBound:
    samples: int
    epochs: int
    token_limit: int
    per_sample_usd: float
    judge_reserve_usd: float
    total_usd: float
    max_spend_usd: float

    @property
    def within(self) -> bool:
        return self.total_usd <= self.max_spend_usd


def preflight_bound(*, samples: int, epochs: int, token_limit: int, price: Price, judge_reserve_usd: float,
                    max_spend_usd: float) -> PreflightBound:
    """The worst case the TARGET calls can cost before Inspect's per-sample
    limits stop them: every sample spends its whole token limit at the dearer
    of the two rates (input and output are not distinguishable in advance),
    times epochs. Compared against `max_spend`, the target ceiling. The judge
    has its own ceiling (`judge_max_spend`, enforced per call by
    judge_runner.SpendCeiling), which `fire_trigger.fire_commitment` counts as
    a second commitment; it is carried here for the report only and never
    added to the target bound, or the guard would count it twice. Derived
    from the limits the run passes, not from turn counts, which undercount
    (design memo section 13). Inspect's token limit counts prompt-cache
    tokens too, so the dearest rate includes the cache rates (2026-09-23)."""
    per_sample = token_limit * max(price.input_per_mtok, price.output_per_mtok, price.cache_read_per_mtok,
                                   price.cache_write_per_mtok) / 1e6
    total = samples * epochs * per_sample
    return PreflightBound(samples=samples, epochs=epochs, token_limit=token_limit, per_sample_usd=per_sample,
                          judge_reserve_usd=judge_reserve_usd, total_usd=total, max_spend_usd=max_spend_usd)


def usage_from_samples(samples: Any, role: str = "target") -> dict[str, dict[str, Any]]:
    """Per-model usage rows from Inspect samples (duck-typed, so the 3.11 suite
    can test it): token counts from the sample's aggregate `model_usage` when
    it has the model, else from the model event's own `output.usage` (Codex
    round 7: a failed eval can retain events with usage but no aggregate, and
    a row with calls and zero tokens priced a paid call at zero); calls
    counted from the events of the given role; an event without a usage block
    counted in `calls_without_usage`, never priced as zero. Prompt-cache
    tokens are carried as the adapter carries them (None until a usage
    reports the field), because Inspect counts them outside `input_tokens`
    and `reprice_usage` prices them (2026-09-23)."""
    rows: dict[str, dict[str, Any]] = {}

    def row(model: str) -> dict[str, Any]:
        return rows.setdefault(model, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                                       "input_tokens_cache_read": None, "input_tokens_cache_write": None,
                                       "calls": 0, "calls_without_usage": 0})

    def add(r: dict[str, Any], usage: Any) -> None:
        r["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        r["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
        r["total_tokens"] += int(getattr(usage, "total_tokens", 0) or 0)
        for attr in ("input_tokens_cache_read", "input_tokens_cache_write"):
            value = getattr(usage, attr, None)
            if value is not None:
                r[attr] = (r[attr] or 0) + int(value)

    for sample in samples:
        aggregate = dict(getattr(sample, "model_usage", None) or {})
        for model, usage in aggregate.items():
            add(row(model), usage)
        for e in getattr(sample, "events", None) or []:
            if getattr(e, "event", None) != "model" or getattr(e, "role", None) != role:
                continue
            r = row(e.model)
            r["calls"] += 1
            output = getattr(e, "output", None)
            usage = getattr(output, "usage", None) if output is not None else None
            if usage is None:
                r["calls_without_usage"] += 1
            elif e.model not in aggregate:
                add(r, usage)
    return rows


def usage_is_missing(usage: dict[str, Any]) -> bool:
    """A usage row cannot be priced when a token count is absent (None or no
    key) or when any of its calls returned no usage block at all
    (`calls_without_usage`, counted by the adapter per model event)."""
    if usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        return True
    return int(usage.get("calls_without_usage") or 0) > 0


def reprice_usage(model_usage: dict[str, dict[str, Any]], registry: dict | None = None,
                  target: str | None = None) -> tuple[float | None, list[dict]]:
    """Cost from Inspect's per-model usage under the engine's prices: the
    post-run layer of the four (design memo section 13). A priced model whose
    usage is missing is never priced as zero: its row carries `usage_missing:
    true` and a null cost, and the total is None, so the sidecar imputes the
    ceiling (`write_report_sidecar`) rather than booking a paid run below its
    charge. A zero-price model (mockllm, the placeholder) with missing usage
    costs exactly 0 whatever its token counts were, so its cost is 0 and the
    missing usage is still recorded on the row (the locked inspect-ai's mockllm
    returns no usage block at all). Prompt-cache reads and writes are priced
    beside input and output at the bounded cache rates (CACHE_*_MULTIPLIER):
    Inspect subtracts them from `input_tokens`, so pricing input and output
    alone under-booked every cached call (2026-09-23). A null cache count is
    no cached tokens: Inspect subtracts only what the provider reported."""
    rows: list[dict] = []
    total = 0.0
    any_missing = False
    if not model_usage and target:
        # no usage row at all for a run that had a target (an all-error eval, a provider failure before any usable
        # event): no evidence of zero spend, so the target is recorded as missing usage, which prices a paid target
        # at the ceiling and a zero-price target at zero (Codex round 4)
        model_usage = {target: {"input_tokens": None, "output_tokens": None, "calls": 0, "calls_without_usage": 0}}
    for model, usage in sorted(model_usage.items()):
        price = resolve_price(model, registry)
        missing = usage_is_missing(usage)
        zero_priced = price.input_per_mtok == 0 and price.output_per_mtok == 0
        in_tok = None if usage.get("input_tokens") is None else int(usage["input_tokens"])
        out_tok = None if usage.get("output_tokens") is None else int(usage["output_tokens"])
        cache_read = None if usage.get("input_tokens_cache_read") is None else int(usage["input_tokens_cache_read"])
        cache_write = None if usage.get("input_tokens_cache_write") is None else int(usage["input_tokens_cache_write"])
        if missing and not zero_priced:
            cost = None
            any_missing = True
        elif missing:
            cost = 0.0
        else:
            cost = price.cost(in_tok, out_tok, cache_read or 0, cache_write or 0)
            total += cost
        rows.append({"model": model, "input_tokens": in_tok, "output_tokens": out_tok,
                     "total_tokens": None if usage.get("total_tokens") is None and missing
                     else int(usage.get("total_tokens") or (in_tok or 0) + (out_tok or 0)),
                     "input_tokens_cache_read": cache_read, "input_tokens_cache_write": cache_write,
                     "calls": int(usage.get("calls") or 0),
                     "calls_without_usage": int(usage.get("calls_without_usage") or 0), "usage_missing": missing,
                     "cost_usd": None if cost is None else round(cost, 8), "price_source": price.source,
                     "input_per_mtok": price.input_per_mtok, "output_per_mtok": price.output_per_mtok,
                     "cache_read_per_mtok": price.cache_read_per_mtok, "cache_write_per_mtok": price.cache_write_per_mtok})
    return (None if any_missing else round(total, 8)), rows


def write_report_sidecar(path: Path, *, run_id: str, eval_id: str, model_usage: dict[str, dict[str, Any]],
                         max_spend_usd: float, judge_max_spend_usd: float | None, run_utc: str,
                         registry: dict | None = None, extra: dict | None = None, target: str | None = None) -> dict:
    """The `<stem>.report.json` the ledger folds into the daily spend: cost_usd
    re-priced from Inspect's usage, the ceilings, and an explicit
    billing_channel (Inspect's `openrouter/` ids would otherwise book
    OpenRouter spend to the Anthropic channel)."""
    cost, rows = reprice_usage(model_usage, registry, target=target)
    missing = [r["model"] for r in rows if r["usage_missing"]]
    if cost is None:
        # a model returned no usage for at least one paid call: the ledger gets the ceiling the guard reserved,
        # never a figure below what the provider may have charged, and the sidecar says why
        cost, basis = float(max_spend_usd), "ceiling_imputed:usage_missing"
    else:
        basis = "engine_repriced_from_inspect_model_usage"
    report = {
        "run_utc": run_utc, "run_id": run_id, "eval_id": eval_id, "task": "petri-audit",
        "cost_usd": cost, "cost_basis": basis, "usage_missing_models": missing,
        "max_spend_usd": max_spend_usd, "judge_max_spend_usd": judge_max_spend_usd,
        "billing_channel": billing_channel([r["model"] for r in rows]),
        "models": rows,
    }
    if extra:
        report.update(extra)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


# The least the cost sidecar may book for one prompt-cache token of an `openrouter/` target, as a multiple of the
# target's input rate. A read: the input rate, which bounds a read's discounted price (OpenRouter passes the
# upstream's cache discount through; the archived grok-4.3 bills price reads at 0.2 against 1.25 USD/Mtok input). A write:
# 1.25 times it, Anthropic's price for the 5-minute TTL of the ephemeral markers Inspect's OpenRouter provider puts
# on every `openrouter/anthropic/*` request by default (inspect_ai 0.3.237 openrouter.py `_ephemeral`).
CACHE_READ_FLOOR = 1.0
CACHE_WRITE_FLOOR = 1.25
CACHE_TOKENS_UNBOOKED = "cache_tokens_unbooked"
_CACHE_PROBE_TOKENS = 1_000_000


def cache_booking_problems(model: str, registry: dict | None = None) -> list[str]:
    """Why the cost sidecar would book an `openrouter/` target's cached calls
    below OpenRouter's bill. Any other name returns [].

    Inspect counts prompt-cache tokens outside `input_tokens`: its
    OpenAI-compatible mapping subtracts cached reads from the prompt count
    (inspect_ai 0.3.237 `_openai.py` `model_output_from_openai`), and its
    OpenRouter provider subtracts cache writes too (`openrouter.py`
    `_apply_cache_creation_usage`). A sidecar that prices input and output
    alone books every cache token at $0. While an OpenRouter target took the
    5/30 catch-all that gap was covered several times over; a reviewed entry
    ~5% above list does not cover it (review of 2026-09-23, through Inspect's
    own mapping: a grok-4.3 target shaped like a landed sample booked 0.88 of
    its list-price bill, a claude-haiku-4.5 target with one cache write 0.41).

    The check runs the sidecar's own path, `usage_from_samples` then
    `reprice_usage`, on a probe usage of cache-read tokens alone and another
    of cache-write tokens alone, and requires each booked at no less than its
    floor above. It tests what the sidecar books, not how it books it, so it
    clears once cache tokens are carried and priced and refuses again if a
    later change drops them. An Anthropic target is not checked: it prices at
    list with no catch-all margin to lose, and every landed run recorded zero
    cache tokens."""
    model = model.strip()
    provider, _ = split_inspect_name(model)
    if provider != "openrouter":
        return []
    rate = resolve_price(model, registry).input_per_mtok
    problems: list[str] = []
    for field, floor in (("input_tokens_cache_read", CACHE_READ_FLOOR), ("input_tokens_cache_write", CACHE_WRITE_FLOOR)):
        usage = SimpleNamespace(input_tokens=0, output_tokens=0, total_tokens=_CACHE_PROBE_TOKENS, reasoning_tokens=None,
                                input_tokens_cache_read=None, input_tokens_cache_write=None)
        setattr(usage, field, _CACHE_PROBE_TOKENS)
        # a sample as the spend-report path reads it (`usage_from_samples`): an aggregate `model_usage` and the target's
        # model event. The adapter carries cache counts with its own accumulator; both paths price by `reprice_usage`
        sample = SimpleNamespace(model_usage={model: usage}, events=[
            SimpleNamespace(event="model", role="target", model=model, output=SimpleNamespace(usage=usage))])
        booked, _ = reprice_usage(usage_from_samples([sample]), registry, target=model)
        need = _CACHE_PROBE_TOKENS * rate * floor / 1e6
        if booked is None or booked < need - 1e-9:
            booked_text = "no cost (usage missing)" if booked is None else f"${booked:.4f}"
            problems.append(
                f"{CACHE_TOKENS_UNBOOKED}: {model!r}: the cost sidecar books {_CACHE_PROBE_TOKENS} {field} tokens at "
                f"{booked_text}, below the ${need:.4f} floor ({floor}x the {rate}/Mtok input "
                "rate); Inspect counts prompt-cache tokens outside input_tokens, so every cached call would be booked "
                "below OpenRouter's bill, which the reviewed near-list price no longer covers. An OpenRouter target "
                "runs once usage_from_samples carries cache reads and writes and reprice_usage prices them")
    return problems
