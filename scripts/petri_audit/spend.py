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
ZERO_PRICE_MODELS = ("mockllm/model", "none/none")


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


def resolve_price(model: str, registry: dict | None = None, engine_pricing: dict | None = None) -> Price:
    """The price for an Inspect model string, with its source. Zero-cost mock
    and placeholder models price at zero so `cost_limit` can start."""
    if model in ZERO_PRICE_MODELS:
        return Price(0.0, 0.0, "zero:mock_or_placeholder")
    registry = registry if registry is not None else (load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {})
    engine_pricing = engine_pricing if engine_pricing is not None else _engine_pricing()
    provider, name = split_inspect_name(model)
    cfg = registry.get(provider) if isinstance(registry, dict) else None
    if isinstance(cfg, dict):
        table = cfg.get("pricing") or {}
        if name in table:
            return Price(float(table[name][0]), float(table[name][1]), f"registry:{provider}:pricing")
        if cfg.get("default_pricing"):
            dp = cfg["default_pricing"]
            return Price(float(dp[0]), float(dp[1]), f"registry:{provider}:default_pricing")
    if name in engine_pricing:
        return Price(*engine_pricing[name], "engine:evaluate_models.PRICING")
    if provider == "openrouter" and "/" in name:
        # openrouter/<vendor>/<model>: the registry keys OpenRouter prices by vendor entry
        vendor = name.split("/", 1)[0]
        vcfg = registry.get(vendor) if isinstance(registry, dict) else None
        if isinstance(vcfg, dict):
            table = vcfg.get("pricing") or {}
            if name in table:
                return Price(float(table[name][0]), float(table[name][1]), f"registry:{vendor}:pricing")
            if vcfg.get("default_pricing"):
                dp = vcfg["default_pricing"]
                return Price(float(dp[0]), float(dp[1]), f"registry:{vendor}:default_pricing")
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
    """The worst case a run can cost before Inspect's per-sample limits stop it:
    every sample spends its whole token limit at the dearer of the two rates
    (input and output are not distinguishable in advance), times epochs, plus
    the judge reserve. Derived from the limits the run passes, not from turn
    counts, which undercount (design memo section 13)."""
    per_sample = token_limit * max(price.input_per_mtok, price.output_per_mtok) / 1e6
    total = samples * epochs * per_sample + judge_reserve_usd
    return PreflightBound(samples=samples, epochs=epochs, token_limit=token_limit, per_sample_usd=per_sample,
                          judge_reserve_usd=judge_reserve_usd, total_usd=total, max_spend_usd=max_spend_usd)


def reprice_usage(model_usage: dict[str, dict[str, Any]], registry: dict | None = None) -> tuple[float, list[dict]]:
    """Cost from Inspect's per-model usage under the engine's prices: the
    post-run layer of the four (design memo section 13)."""
    rows: list[dict] = []
    total = 0.0
    for model, usage in sorted(model_usage.items()):
        price = resolve_price(model, registry)
        in_tok = int(usage.get("input_tokens") or 0)
        out_tok = int(usage.get("output_tokens") or 0)
        cost = price.cost(in_tok, out_tok)
        total += cost
        rows.append({"model": model, "input_tokens": in_tok, "output_tokens": out_tok,
                     "total_tokens": int(usage.get("total_tokens") or in_tok + out_tok),
                     "cost_usd": round(cost, 8), "price_source": price.source,
                     "input_per_mtok": price.input_per_mtok, "output_per_mtok": price.output_per_mtok})
    return round(total, 8), rows


def write_report_sidecar(path: Path, *, run_id: str, eval_id: str, model_usage: dict[str, dict[str, Any]],
                         max_spend_usd: float, judge_max_spend_usd: float | None, run_utc: str,
                         registry: dict | None = None, extra: dict | None = None) -> dict:
    """The `<stem>.report.json` the ledger folds into the daily spend: cost_usd
    re-priced from Inspect's usage, the ceilings, and an explicit
    billing_channel (Inspect's `openrouter/` ids would otherwise book
    OpenRouter spend to the Anthropic channel)."""
    cost, rows = reprice_usage(model_usage, registry)
    report = {
        "run_utc": run_utc, "run_id": run_id, "eval_id": eval_id, "task": "petri-audit",
        "cost_usd": cost, "cost_basis": "engine_repriced_from_inspect_model_usage",
        "max_spend_usd": max_spend_usd, "judge_max_spend_usd": judge_max_spend_usd,
        "billing_channel": billing_channel([r["model"] for r in rows]),
        "models": rows,
    }
    if extra:
        report.update(extra)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
