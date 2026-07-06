"""Multi-model efficacy evaluation for the medlang LLM scenarios.

Runs the Anthropic-backed steps of the pipeline across a set of models,
scores each model against expected outputs, and writes a JSON log plus a
markdown summary with per-model token consumption and estimated cost.

Three scenarios are supported:

- ``translation``: patient phrasing in, hit if any acceptable clinical term
  appears in the model's translation (single call per item).
- ``classification``: feature-style description in, hit if the returned
  category label matches exactly (single call per item).
- ``two_step``: the dual-stage conversion & re-evaluation pipeline. Each item
  makes three calls per model:

  * **Stage A (patient baseline)** — the raw patient phrasing is given to the
    model with the concept-extraction task ("name the precise clinical term
    for what this statement describes"), scored against the item's expected
    terms. This is the model's performance on language as patients speak it.
  * **Stage B (conversion)** — the *same* patient phrasing is translated into
    clinician language using the production translation prompt. The output is
    kept verbatim as the intermediate artifact.
  * **Stage C (clinician re-evaluation)** — the generated clinician phrasing
    is fed back through the identical Stage-A task and re-scored, so the only
    variable between A and C is the phrasing.

  Per model, the report compares patient vs. clinician accuracy (the delta),
  and every item is audit-flagged: ``patient_phrasing_failure`` (A missed,
  C hit — the patient wording alone broke the model, translation mitigates),
  ``translation_regression`` (A hit, C missed — the conversion lost the
  concept), or ``unresolved_failure`` (both missed).

Every run appends a timestamped entry to ``<out>/audit_registry_log.json``
recording the ISO execution time, config, per-stage token/cost accounting,
each intermediate clinician translation, and all flagged problematic cases.

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
from datetime import datetime, timezone
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
SCENARIOS = ("translation", "classification", "two_step")
# keys that must exist in the eval pairs file (two_step reuses the translation items)
DATA_KEYS = ("translation", "classification")
DEFAULT_PAIRS_PATH = Path(__file__).parent / "data" / "eval_pairs.json"
REGISTRY_FILENAME = "audit_registry_log.json"
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
    for key in DATA_KEYS:
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


# Stage A/C task: extract the clinical concept from a statement. Deliberately
# vocabulary-free - the scoring terms live in the eval pairs data file.
_CONCEPT_SYSTEM = (
    "You are assisting a clinical NLP evaluation. Given a short statement, respond with the "
    "single most precise standard clinical term for the primary symptom or condition it "
    "describes. Respond with only the term."
)

# Audit flags for two-step items (None when both stages hit).
FLAG_PATIENT_FAILURE = "patient_phrasing_failure"  # A missed, C hit: patient wording broke the model
FLAG_TRANSLATION_REGRESSION = "translation_regression"  # A hit, C missed: conversion lost the concept
FLAG_UNRESOLVED = "unresolved_failure"  # both missed: translation did not mitigate


def evaluate_two_step(
    client: Any,
    model: str,
    items: list[dict[str, Any]],
    tracker: CostTracker,
) -> dict[str, Any]:
    """Run the dual-stage conversion & re-evaluation pipeline for one model.

    For each item (a translation pair: patient phrasing + acceptable clinical
    terms), performs three calls:

    - Stage A: concept extraction on the raw patient phrasing (baseline).
    - Stage B: patient -> clinician translation (the production prompt);
      the raw output is the intermediate clinician text.
    - Stage C: the identical concept-extraction task re-run on the Stage-B
      output, so phrasing is the only variable between A and C.

    Both A and C are scored against the same expected terms; the block-level
    result reports patient vs. clinician accuracy, their delta, and audit
    flags for every problematic item. Budget is checked before each stage; an
    item interrupted mid-pipeline is excluded from the comparative metrics.
    """
    records: list[dict[str, Any]] = []
    patient_hits = clinician_hits = completed = skipped = 0
    flags: dict[str, int] = {FLAG_PATIENT_FAILURE: 0, FLAG_TRANSLATION_REGRESSION: 0, FLAG_UNRESOLVED: 0}

    for item in items:
        rec: dict[str, Any] = {"patient_text": item["patient"], "expected": item["expected"], "stages": {}}
        records.append(rec)

        def run_stage(name: str, system: str, prompt: str) -> str | None:
            if not tracker.can_afford(model):
                rec["skipped"] = f"budget exhausted before stage {name}"
                return None
            text, in_tok, out_tok = _call(client, model, system, prompt)
            cost = tracker.record(model, in_tok, out_tok)
            rec["stages"][name] = {
                "output": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(cost, 6),
            }
            return text

        try:
            baseline = run_stage("A_patient_baseline", _CONCEPT_SYSTEM, item["patient"])
            if baseline is None:
                skipped += 1
                continue
            clinician_text = run_stage("B_clinician_translation", _TRANSLATE_SYSTEM, item["patient"])
            if clinician_text is None:
                skipped += 1
                continue
            rec["clinician_text"] = clinician_text
            reeval = run_stage("C_clinician_reeval", _CONCEPT_SYSTEM, clinician_text)
            if reeval is None:
                skipped += 1
                continue
        except Exception as e:  # a single bad call should not sink the whole matrix
            logger.warning("two-step call failed for %s: %s", model, e)
            rec["error"] = str(e)
            continue

        hit_patient = _score_translation(baseline, item["expected"])
        hit_clinician = _score_translation(reeval, item["expected"])
        completed += 1
        patient_hits += int(hit_patient)
        clinician_hits += int(hit_clinician)
        rec.update({"hit_patient": hit_patient, "hit_clinician": hit_clinician})

        if hit_patient and hit_clinician:
            rec["flag"] = None
        elif hit_clinician:
            rec["flag"] = FLAG_PATIENT_FAILURE
        elif hit_patient:
            rec["flag"] = FLAG_TRANSLATION_REGRESSION
        else:
            rec["flag"] = FLAG_UNRESOLVED
        if rec["flag"]:
            flags[rec["flag"]] += 1

    return {
        "completed": completed,
        "skipped_for_budget": skipped,
        "patient_accuracy": patient_hits / completed if completed else None,
        "clinician_accuracy": clinician_hits / completed if completed else None,
        "delta": (clinician_hits - patient_hits) / completed if completed else None,
        "flags": flags,
        "items": records,
    }


def _problematic_cases(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every audit-flagged two-step item across models for the registry."""
    cases = []
    for model, blocks in results["by_model"].items():
        for rec in blocks.get("two_step", {}).get("items", []):
            if rec.get("flag"):
                cases.append({
                    "model": model,
                    "flag": rec["flag"],
                    "patient_text": rec["patient_text"],
                    "clinician_text": rec.get("clinician_text"),
                    "stage_a_output": rec["stages"].get("A_patient_baseline", {}).get("output"),
                    "stage_c_output": rec["stages"].get("C_clinician_reeval", {}).get("output"),
                    "expected": rec["expected"],
                })
    return cases


def append_registry(out_dir: Path, results: dict[str, Any]) -> Path:
    """Append this run to the cumulative audit registry (one JSON list, one entry per run).

    Each entry carries the ISO execution timestamp, run config, total and
    per-model token/cost usage, the full per-stage two-step detail (original
    patient text, intermediate clinician translation, per-stage tokens and
    cost), the comparative patient-vs-clinician metrics, and the flattened
    list of flagged problematic cases.
    """
    path = out_dir / REGISTRY_FILENAME
    registry: list[dict[str, Any]] = []
    if path.exists():
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(registry, list):
                registry = []
        except (OSError, json.JSONDecodeError):
            logger.warning("existing registry at %s unreadable; starting fresh", path)
    entry = {
        "run_timestamp": results["run_timestamp"],
        "models": results["models"],
        "scenarios": results["scenarios"],
        "sample_size": results["sample_size"],
        "max_spend_usd": results["max_spend_usd"],
        "warnings": results["warnings"],
        "usage": results["usage"],
        "two_step": {
            model: {
                "comparative_metrics": {k: blocks["two_step"][k] for k in
                                        ("patient_accuracy", "clinician_accuracy", "delta", "flags",
                                         "completed", "skipped_for_budget")},
                "items": blocks["two_step"]["items"],
            }
            for model, blocks in results["by_model"].items() if "two_step" in blocks
        },
        "problematic_cases": _problematic_cases(results),
    }
    registry.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    return path


def run_evaluation(
    models: list[str],
    scenario: str = "both",
    sample_size: int = 8,
    max_spend: float = 5.0,
    pairs_path: str | Path | None = None,
    out_dir: str | Path = "eval_out",
    client: Any = None,
) -> dict[str, Any]:
    """Evaluate every model on the requested scenario(s); write results.json, summary.md, and the audit registry.

    ``scenario`` accepts a single scenario name, ``"both"`` (translation +
    classification, the original pair), or ``"all"`` (adds the two-step
    conversion & re-evaluation pipeline). The two-step scenario reuses the
    translation items from the pairs file.
    """
    models, warnings = resolve_models(models)
    if scenario == "both":
        scenarios = ["translation", "classification"]
    elif scenario == "all":
        scenarios = list(SCENARIOS)
    else:
        scenarios = [scenario]
    if any(s not in SCENARIOS for s in scenarios):
        raise ValueError(f"unknown scenario {scenario!r}; expected one of {SCENARIOS + ('both', 'all')}")

    pairs = load_pairs(pairs_path)
    tracker = CostTracker(max_spend=max_spend)
    if client is None:
        client = _get_client()

    results: dict[str, Any] = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "models": models,
        "scenarios": scenarios,
        "sample_size": sample_size,
        "max_spend_usd": max_spend,
        "warnings": warnings,
        "by_model": {},
    }
    for model in models:
        blocks: dict[str, Any] = {}
        for s in scenarios:
            items = pairs["translation" if s == "two_step" else s][:sample_size]
            if s == "two_step":
                blocks[s] = evaluate_two_step(client, model, items, tracker)
            else:
                blocks[s] = evaluate_model(client, model, s, items, tracker)
        results["by_model"][model] = blocks
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
    append_registry(out, results)
    logger.info("Evaluation complete; $%.4f spent; outputs in %s", tracker.spent, out)
    return results


def render_summary(results: dict[str, Any]) -> str:
    """Markdown report: accuracy plus token/cost accounting per model.

    When the two-step scenario ran, appends the comparative "Patient vs.
    clinician phrasing" efficacy table (baseline accuracy, post-conversion
    accuracy, delta, and audit-flag counts) plus a list of every flagged
    problematic case - the sections GitHub Actions surfaces on the run page.
    """
    usage = results["usage"]
    single_call = [s for s in results["scenarios"] if s != "two_step"]
    lines = [
        "# Model evaluation summary",
        "",
        f"- Run: {results['run_timestamp']}",
        f"- Scenarios: {', '.join(results['scenarios'])}",
        f"- Sample size per scenario: {results['sample_size']}",
        f"- Budget: ${results['max_spend_usd']:.2f} — spent ${usage['total_cost_usd']:.4f}"
        + (" (**budget hit — run truncated**)" if usage["truncated_by_budget"] else ""),
        "",
    ]
    if results["warnings"]:
        lines += ["> " + w for w in results["warnings"]] + [""]

    header = "| model | " + " | ".join(f"{s} accuracy" for s in single_call) + " | calls | input tok | output tok | est. cost |"
    sep = "|" + "---|" * (len(single_call) + 5)
    lines += [header, sep]
    for model, blocks in results["by_model"].items():
        cells = [model]
        for s in single_call:
            block = blocks[s]
            acc = f"{block['accuracy']:.0%} ({block['hits']}/{block['attempted']})" if block["accuracy"] is not None else "—"
            if block["skipped_for_budget"]:
                acc += f" · {block['skipped_for_budget']} skipped"
            cells.append(acc)
        stats = usage["per_model"].get(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0})
        cells += [str(int(stats["calls"])), str(int(stats["input_tokens"])), str(int(stats["output_tokens"])), f"${stats['cost']:.4f}"]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    if "two_step" in results["scenarios"]:
        lines += [
            "## Patient vs. clinician phrasing (two-step conversion)",
            "",
            "Stage A scores the concept-extraction task on raw patient phrasing; Stage B translates it "
            "to clinician language; Stage C re-scores the identical task on the translation.",
            "",
            "| model | patient accuracy (A) | clinician accuracy (C) | Δ (C − A) | mitigated by translation | translation regressions | unresolved |",
            "|---|---|---|---|---|---|---|",
        ]
        for model, blocks in results["by_model"].items():
            ts = blocks["two_step"]
            if ts["patient_accuracy"] is None:
                lines.append(f"| {model} | — | — | — | — | — | — |")
                continue
            row = (
                f"| {model} | {ts['patient_accuracy']:.0%} | {ts['clinician_accuracy']:.0%} "
                f"| {ts['delta']:+.0%} | {ts['flags'][FLAG_PATIENT_FAILURE]} "
                f"| {ts['flags'][FLAG_TRANSLATION_REGRESSION]} | {ts['flags'][FLAG_UNRESOLVED]} |"
            )
            if ts["skipped_for_budget"]:
                row += f" ({ts['skipped_for_budget']} skipped)"
            lines.append(row)
        lines.append("")

        cases = _problematic_cases(results)
        if cases:
            lines += ["### Flagged problematic cases", ""]
            for c in cases:
                clin = f" → “{c['clinician_text']}”" if c.get("clinician_text") else ""
                lines.append(f"- **{c['model']}** · `{c['flag']}` · “{c['patient_text']}”{clin}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate translation/classification accuracy across Anthropic models.")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="model IDs to evaluate (legacy names are remapped)")
    parser.add_argument(
        "--scenario", choices=[*SCENARIOS, "both", "all"], default="both",
        help="'both' = translation + classification; 'all' adds the two-step conversion pipeline",
    )
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
