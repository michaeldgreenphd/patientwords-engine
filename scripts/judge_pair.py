"""The two-pass reservation shared by advice and Petri (owner decision R4).

The configured ceiling remains the first judge's. The second gets the first
ceiling times the larger of the two per-token price ratios, rounded upwards
to a microdollar. This bounds the same token envelope without assuming a
particular input/output mix. Both ceilings enter ONE journal reservation.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
import json
import os
from pathlib import Path
from typing import Any

SECONDARY = "anthropic:claude-haiku-5-5"
OPENROUTER_SECONDARY = "openrouter:anthropic/claude-haiku-5.5"


def allocation(spec: str, ceiling: float, primary_price: tuple[float, float],
               secondary_price: tuple[float, float], resolved_name: str, secondary_spec: str = SECONDARY) -> dict[str, Any]:
    """Record the extra reservation, or a zero for an already-selected second judge."""
    resolved_secondary = secondary_spec.replace(":", "/", 1)
    if resolved_name == resolved_secondary or resolved_name == "mockllm/judge":
        return {"judge_model": secondary_spec, "max_spend_usd": 0.0,
                "reason": "already_selected" if resolved_name != "mockllm/judge" else "rehearsal"}
    values = [Decimal(str(x)) for x in (*primary_price, *secondary_price, ceiling)]
    if any(not x.is_finite() or x <= 0 for x in values):
        raise ValueError("dual_judge_invalid_price_or_ceiling: positive finite prices and ceiling required")
    ratio = max(values[2] / values[0], values[3] / values[1])
    amount = (values[4] * ratio).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    return {"judge_model": secondary_spec, "max_spend_usd": float(amount), "primary_judge_model": spec,
            "primary_max_spend_usd": ceiling, "primary_price_per_mtok": list(primary_price),
            "secondary_price_per_mtok": list(secondary_price), "price_ratio": float(ratio),
            "allocation_basis": "max(input_price_ratio, output_price_ratio); round_up_microdollar"}


def require_advice_reservation(root: Path, judge_model: str, ceiling: float, reservation: dict) -> None:
    """Bind an actual paired advice pass to the pushed file and its one journal reservation."""
    try:
        from scripts import fire_trigger as ft
    except ModuleNotFoundError:
        import fire_trigger as ft
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise ValueError("dual_judge_ci_only: first-attempt push-to-run CI required")
    content = (root / ".github/trigger/advice-eval.json").read_text(encoding="utf-8")
    params = json.loads(content)
    entries = [json.loads(line) for line in (root / "ops/trigger_journal.jsonl").read_text().splitlines() if line.strip()]
    matches = [entry for entry in entries if entry.get("trigger") == "advice-eval"
               and entry.get("params_sha256") == ft.params_digest(content)
               and entry.get("ref") == os.environ.get("GITHUB_REF_NAME")]
    total, problem = ft.fire_commitment(params)
    if (not ft.judge_is_on(params) or str(params.get("judge_model") or ft.ADVICE_DEFAULT_SPEC) != judge_model
            or ft.parse_max_spend(params.get("judge_max_spend")) != ceiling
            or problem or len(matches) != 1 or matches[0].get("evicted") or matches[0].get("resolved")
            or matches[0].get("lane") != "anthropic" or matches[0].get("max_spend") != total
            or matches[0].get("secondary_judge") != reservation):
        raise ValueError("dual_judge_unreserved: the pushed params must bind one live dual-judge reservation")
