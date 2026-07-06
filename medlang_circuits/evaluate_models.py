"""Multi-model efficacy evaluation for the medlang LLM scenarios.

Runs the two Anthropic-backed steps of the pipeline (patient->clinical
translation and feature-description classification) across a set of models,
scores each model against expected outputs, and writes a JSON log plus a
markdown summary with per-model token consumption and estimated cost.

A hard spend ceiling is enforced: before every API call the tracker checks
that a conservative worst-case cost still fits under ``--max-spend``; when it
no longer does, remaining calls are skipped and the run is marked truncated.

Evaluation items live in ``data/eval_pairs.json`` (a data file, not source);
this module contains no domain vocabulary.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from medlang_circuits.llm_client import _CLASSIFY_SYSTEM, _TRANSLATE_SYSTEM, _get_client

logger = logging.getLogger(__name__)

# USD per million tokens: model -> (input, output)
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}
# Conservative fallback for models missing from PRICING (priced like the most expensive tier).
_FALLBACK_PRICING = (10.0, 50.0)

# Retired/deprecated model names -> current equivalents, so older configs keep working.
LEGACY_ALIASES: dict[str, str] = {
    "claude-3-5-sonnet": "claude-sonnet-5",
    "claude-3-5-sonnet-20241022": "claude-sonnet-5",
    "claude-3-5-haiku": "claude-haiku-4-5",
    "claude-3-haiku": "claude-haiku-4-5",
    "claude-3-haiku-20240307": "claude-haiku-4-5",
    "claude-3-opus": "claude-opus-4-8",
}

DEFAULT_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]
SCENARIOS = ("translation", "classification")
DEFAULT_PAIRS_PATH = Path(__file__).parent / "data" / "eval_pairs.json"
# Worst-case per-call sizing used for the pre-call budget check.
EST_INPUT_TOKENS = 500
MAX_OUTPUT_TOKENS = 200


def resolve_models(names: list[str]) -> tuple[list[str], list[str]]:
    """Map legacy model names to current IDs; returns (models, warnings)."""
    resolved: list[str] = []
    warnings: list[str] = []
    for name in names:
        target = LEGACY_ALIASES.get(name, name)
        if target != name:
            warnings.append(f"model '{name}' is retired/deprecated; using '{target}' instead")
            logger.warning("%s", warnings[-1])
        if target not in PRICING:
            warnings.append(f"model '{target}' has no pricing entry; costs estimated at the highest tier")
            logger.warning("%s", warnings[-1])
        if target not in resolved:
            resolved.append(target)
    return resolved, warnings


def _price(model: str) -> tuple[float, float]:
    return PRICING.get(model, _FALLBACK_PRICING)


@dataclass
class CostTracker:
    """Accumulates token usage and enforces a hard spend ceiling."""

    max_spend: float
    spent: float = 0.0
    truncated: bool = False
    per_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def can_afford(self, model: str) -> bool:
        in_price, out_price = _price(model)
        worst_case = EST_INPUT_TOKENS * in_price / 1e6 + MAX_OUTPUT_TOKENS * out_price / 1e6
        if self.spent + worst_case > self.max_spend:
            self.truncated = True
            return False
        return True

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        in_price, out_price = _price(model)
        cost = input_tokens * in_price / 1e6 + output_tokens * out_price / 1e6
        self.spent += cost
        bucket = self.per_model.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0})
        bucket["calls"] += 1
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["cost"] += cost
        return cost


def _call(client: Any, model: str, system: str, prompt: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> tuple[str, int, int]:
    """Single Messages API call; returns (text, input_tokens, output_tokens).

    Kept as a module-level seam so tests can monkeypatch it without a network.
    """
    if client is None:
        raise RuntimeError("Anthropic client unavailable - set ANTHROPIC_API_KEY and install the anthropic package")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    usage = getattr(response, "usage", None)
    return text, getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)


def _score_translation(output: str, expected: list[str]) -> bool:
    lowered = output.lower()
    return any(term.lower() in lowered for term in expected)


def _score_classification(output: str, label: str) -> bool:
    return output.strip().lower() == label.strip().lower()


def load_pairs(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    with open(path or DEFAULT_PAIRS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for key in SCENARIOS:
        if key not in data or not isinstance(data[key], list):
            raise ValueError(f"eval pairs file missing '{key}' list")
    return data


def evaluate_model(
    client: Any,
    model: str,
    scenario: str,
    items: list[dict[str, Any]],
    tracker: CostTracker,
) -> dict[str, Any]:
    """Run one (model, scenario) block; returns hits/attempts/skips plus per-item detail."""
    detail: list[dict[str, Any]] = []
    hits = attempted = skipped = 0
    for item in items:
        if not tracker.can_afford(model):
            skipped += 1
            detail.append({"input": item, "skipped": "budget"})
            continue
        if scenario == "translation":
            system, prompt = _TRANSLATE_SYSTEM, item["patient"]
        else:
            system, prompt = _CLASSIFY_SYSTEM, f"Description: {item['text']}"
        try:
            text, in_tok, out_tok = _call(client, model, system, prompt)
        except Exception as e:  # a single bad call should not sink the whole matrix
            logger.warning("call failed for %s/%s: %s", model, scenario, e)
            detail.append({"input": item, "error": str(e)})
            continue
        tracker.record(model, in_tok, out_tok)
        attempted += 1
        hit = _score_translation(text, item["expected"]) if scenario == "translation" else _score_classification(text, item["label"])
        hits += int(hit)
        detail.append({"input": item, "output": text, "hit": hit, "input_tokens": in_tok, "output_tokens": out_tok})
    return {
        "hits": hits,
        "attempted": attempted,
        "skipped_for_budget": skipped,
        "accuracy": hits / attempted if attempted else None,
        "items": detail,
    }


def run_evaluation(
    models: list[str],
    scenario: str = "both",
    sample_size: int = 8,
    max_spend: float = 5.0,
    pairs_path: str | Path | None = None,
    out_dir: str | Path = "eval_out",
    client: Any = None,
) -> dict[str, Any]:
    """Evaluate every model on the requested scenario(s) and write results.json + summary.md."""
    models, warnings = resolve_models(models)
    scenarios = list(SCENARIOS) if scenario == "both" else [scenario]
    if any(s not in SCENARIOS for s in scenarios):
        raise ValueError(f"unknown scenario {scenario!r}; expected one of {SCENARIOS + ('both',)}")

    pairs = load_pairs(pairs_path)
    tracker = CostTracker(max_spend=max_spend)
    if client is None:
        client = _get_client()

    results: dict[str, Any] = {
        "models": models,
        "scenarios": scenarios,
        "sample_size": sample_size,
        "max_spend_usd": max_spend,
        "warnings": warnings,
        "by_model": {},
    }
    for model in models:
        results["by_model"][model] = {
            s: evaluate_model(client, model, s, pairs[s][:sample_size], tracker) for s in scenarios
        }
    results["usage"] = {
        "total_cost_usd": round(tracker.spent, 6),
        "truncated_by_budget": tracker.truncated,
        "per_model": tracker.per_model,
    }

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    (out / "summary.md").write_text(render_summary(results), encoding="utf-8")
    logger.info("Evaluation complete; $%.4f spent; outputs in %s", tracker.spent, out)
    return results


def render_summary(results: dict[str, Any]) -> str:
    """Markdown report: accuracy plus token/cost accounting per model."""
    usage = results["usage"]
    lines = [
        "# Model evaluation summary",
        "",
        f"- Scenarios: {', '.join(results['scenarios'])}",
        f"- Sample size per scenario: {results['sample_size']}",
        f"- Budget: ${results['max_spend_usd']:.2f} — spent ${usage['total_cost_usd']:.4f}"
        + (" (**budget hit — run truncated**)" if usage["truncated_by_budget"] else ""),
        "",
    ]
    if results["warnings"]:
        lines += ["> " + w for w in results["warnings"]] + [""]

    header = "| model | " + " | ".join(f"{s} accuracy" for s in results["scenarios"]) + " | calls | input tok | output tok | est. cost |"
    sep = "|" + "---|" * (len(results["scenarios"]) + 5)
    lines += [header, sep]
    for model, blocks in results["by_model"].items():
        cells = [model]
        for s in results["scenarios"]:
            block = blocks[s]
            acc = f"{block['accuracy']:.0%} ({block['hits']}/{block['attempted']})" if block["accuracy"] is not None else "—"
            if block["skipped_for_budget"]:
                acc += f" · {block['skipped_for_budget']} skipped"
            cells.append(acc)
        stats = usage["per_model"].get(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0})
        cells += [str(int(stats["calls"])), str(int(stats["input_tokens"])), str(int(stats["output_tokens"])), f"${stats['cost']:.4f}"]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate translation/classification accuracy across Anthropic models.")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="model IDs to evaluate (legacy names are remapped)")
    parser.add_argument("--scenario", choices=[*SCENARIOS, "both"], default="both")
    parser.add_argument("--sample-size", type=int, default=8, help="items per scenario (5-10 recommended)")
    parser.add_argument("--max-spend", type=float, default=5.0, help="hard USD ceiling for the whole run")
    parser.add_argument("--pairs", default=None, help="path to eval pairs JSON (default: packaged data/eval_pairs.json)")
    parser.add_argument("--out", default="eval_out", help="output directory for results.json + summary.md")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = _get_client()
    if client is None:
        parser.error("ANTHROPIC_API_KEY is not set (or the anthropic package is missing) - cannot run live evaluation")

    results = run_evaluation(
        models=args.models,
        scenario=args.scenario,
        sample_size=args.sample_size,
        max_spend=args.max_spend,
        pairs_path=args.pairs,
        out_dir=args.out,
        client=client,
    )
    print(render_summary(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
