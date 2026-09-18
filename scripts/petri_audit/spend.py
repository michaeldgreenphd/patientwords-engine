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
from typing import Any

from .framework import ROOT, load_json, sha256_text

PROVIDERS_PATH = ROOT / "data" / "advice_providers.json"
FALLBACK_PRICING = (10.0, 50.0)          # scripts/advice_eval.py _FALLBACK_PRICING, USD per million tokens
ZERO_PRICE_MODELS = ("mockllm/model", "mockllm/judge", "none/none")      # mockllm/judge: the local tests' judge (PR B)


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float
    source: str

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return input_tokens * self.input_per_mtok / 1e6 + output_tokens * self.output_per_mtok / 1e6


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
    (fail closed, as fire_trigger.petri_channels does with the same rule)."""
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
    understates the ceiling and a cheap vendor never undercuts the floor."""
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
    (design memo section 13)."""
    per_sample = token_limit * max(price.input_per_mtok, price.output_per_mtok) / 1e6
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
    counted in `calls_without_usage`, never priced as zero."""
    rows: dict[str, dict[str, Any]] = {}

    def row(model: str) -> dict[str, Any]:
        return rows.setdefault(model, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                                       "calls": 0, "calls_without_usage": 0})

    def add(r: dict[str, Any], usage: Any) -> None:
        r["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        r["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
        r["total_tokens"] += int(getattr(usage, "total_tokens", 0) or 0)

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
    returns no usage block at all)."""
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
        if missing and not zero_priced:
            cost = None
            any_missing = True
        elif missing:
            cost = 0.0
        else:
            cost = price.cost(in_tok, out_tok)
            total += cost
        rows.append({"model": model, "input_tokens": in_tok, "output_tokens": out_tok,
                     "total_tokens": None if usage.get("total_tokens") is None and missing
                     else int(usage.get("total_tokens") or (in_tok or 0) + (out_tok or 0)),
                     "calls": int(usage.get("calls") or 0),
                     "calls_without_usage": int(usage.get("calls_without_usage") or 0), "usage_missing": missing,
                     "cost_usd": None if cost is None else round(cost, 8), "price_source": price.source,
                     "input_per_mtok": price.input_per_mtok, "output_per_mtok": price.output_per_mtok})
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
