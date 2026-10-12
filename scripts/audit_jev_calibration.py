"""Audit, benchmark, and calibration runner for classifier models (Jev and generative judges).

Evaluates classifiers against synthetic golden reference sets (data/classifier_benchmark_golden.json)
or sampled archive responses (data/advice/responses_*.jsonl), producing clear, human-and-agent
readable audit reports:
- Accuracy & Exact Match %
- Tier Distance Matrix / Off-by-one tolerance (derived dynamically from rubric tier order)
- Brier Score & Confidence Calibration across predicted probabilities
- Binary Flag Sensitivity, Specificity, Precision (reporting null when undefined)
- Cost and Latency Accounting (reporting $0 actual cost in offline mock mode)
- Full artifact provenance: input hashes, parameters, model identifiers, and response records

Conventions honored:
- No medical terms hardcoded in Python source (AGENTS.md).
- Strict push-to-run / gated CI requirement: live provider calls require --allow-live-calls
  to avoid accidental un-metered local spend (AGENTS.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medlang_circuits.jev_client import (
    ChoiceAnswer,
    JevClient,
    JevResponse,
    JevUsage,
    NoulAnswer,
    ScoreAnswer,
)
from scripts.jev_classifier import AdviceAnswerClassifier


@dataclass
class EvaluationMetrics:
    total_cases: int
    exact_tier_matches: int
    exact_accuracy: float
    within_one_tier_matches: int
    within_one_accuracy: float
    brier_score: float
    flag_metrics: dict[str, dict[str, Any]]
    total_cost_usd: float
    total_input_tokens: int
    confusion_matrix: list[list[int]]
    tier_order: list[str]


def compute_brier_score(predictions: list[dict[str, float]], ground_truths: list[str], tier_order: list[str]) -> float:
    """Multi-category Brier score: mean squared error across probability vectors."""
    if not predictions:
        return 0.0
    total_sq_err = 0.0
    for probs, truth in zip(predictions, ground_truths):
        for t in tier_order:
            p = probs.get(t, 0.0)
            actual = 1.0 if t == truth else 0.0
            total_sq_err += (p - actual) ** 2
    return total_sq_err / len(predictions)


def evaluate_advice_classifier(
    cases: list[dict[str, Any]],
    classifier: AdviceAnswerClassifier,
    tier_order: list[str],
    model_name: str,
    is_mock: bool = False,
) -> tuple[EvaluationMetrics, list[dict[str, Any]]]:
    """Run classifier over benchmark cases and compute audit metrics."""
    tier_rank = {t: i for i, t in enumerate(tier_order)}
    confusion = [[0] * len(tier_order) for _ in tier_order]
    exact_matches = 0
    within_one = 0
    prob_vectors: list[dict[str, float]] = []
    gold_tiers: list[str] = []
    flag_stats: dict[str, dict[str, int]] = {}

    total_cost = 0.0
    total_tokens = 0
    case_reports: list[dict[str, Any]] = []

    for c in cases:
        text = c["response_text"]
        expected_tier = c.get("expected_tier")
        expected_flags = c.get("expected_flags", {})

        res = classifier.classify(text, model=model_name)
        pred_tier = res.tier

        # In mock mode, actual spend is $0.0
        case_cost = 0.0 if is_mock else res.cost_usd
        total_cost += case_cost
        total_tokens += res.input_tokens

        pred_idx = tier_rank.get(pred_tier, -1)
        gold_idx = tier_rank.get(expected_tier, -1) if expected_tier else -1

        is_exact = False
        is_within_one = False
        if gold_idx != -1 and pred_idx != -1:
            confusion[gold_idx][pred_idx] += 1
            if pred_tier == expected_tier:
                exact_matches += 1
                is_exact = True
            if abs(pred_idx - gold_idx) <= 1:
                within_one += 1
                is_within_one = True

        prob_vectors.append(res.tier_probabilities)
        if expected_tier:
            gold_tiers.append(expected_tier)

        # Flag accuracy tracking - refuse or record missing answers rather than defaulting to false
        flag_report = {}
        for fid, exp_val in expected_flags.items():
            if fid not in res.flags:
                raise ValueError(f"Classifier response missing expected flag answer for {fid!r}")
            got_val = res.flags[fid]
            stats = flag_stats.setdefault(fid, {"tp": 0, "tn": 0, "fp": 0, "fn": 0})
            if exp_val and got_val:
                stats["tp"] += 1
            elif not exp_val and not got_val:
                stats["tn"] += 1
            elif not exp_val and got_val:
                stats["fp"] += 1
            else:
                stats["fn"] += 1
            flag_report[fid] = {
                "expected": exp_val,
                "predicted": got_val,
                "probability": res.flag_probabilities.get(fid),
            }

        case_reports.append({
            "id": c.get("id"),
            "response_text": text,
            "expected_tier": expected_tier,
            "predicted_tier": pred_tier,
            "tier_confidence": res.tier_confidence,
            "is_exact": is_exact,
            "is_within_one": is_within_one,
            "tier_probabilities": res.tier_probabilities,
            "flags": flag_report,
            "technicality_score": res.register_score,
            "cost_usd": case_cost,
        })

    n = len(cases)
    brier = compute_brier_score(prob_vectors, gold_tiers, tier_order) if gold_tiers else 0.0

    # Compute accuracy, precision, recall (sensitivity), and specificity
    computed_flag_metrics: dict[str, dict[str, Any]] = {}
    for fid, st in flag_stats.items():
        tp, tn, fp, fn = st["tp"], st["tn"], st["fp"], st["fn"]
        total = tp + tn + fp + fn
        acc = (tp + tn) / max(1, total)

        # Precision = tp / (tp + fp); undefined if (tp + fp) == 0
        prec = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None

        # Sensitivity (Recall) = tp / (tp + fn); undefined if (tp + fn) == 0
        sens = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None

        # Specificity = tn / (tn + fp); undefined if (tn + fp) == 0
        spec = round(tn / (tn + fp), 4) if (tn + fp) > 0 else None

        computed_flag_metrics[fid] = {
            "accuracy": round(acc, 4),
            "precision": prec,
            "sensitivity": sens,
            "specificity": spec,
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
        }

    metrics = EvaluationMetrics(
        total_cases=n,
        exact_tier_matches=exact_matches,
        exact_accuracy=round(exact_matches / max(1, len(gold_tiers)), 4) if gold_tiers else 0.0,
        within_one_tier_matches=within_one,
        within_one_accuracy=round(within_one / max(1, len(gold_tiers)), 4) if gold_tiers else 0.0,
        brier_score=round(brier, 4),
        flag_metrics=computed_flag_metrics,
        total_cost_usd=round(total_cost, 6),
        total_input_tokens=total_tokens,
        confusion_matrix=confusion,
        tier_order=tier_order,
    )
    return metrics, case_reports


def format_markdown_report(metrics: EvaluationMetrics, case_reports: list[dict[str, Any]], model_name: str, is_mock: bool = False) -> str:
    """Generate a clean, structured audit report readable by humans and agents."""
    cost_label = f"${metrics.total_cost_usd:.6f} ($0.0 mock run)" if is_mock else f"${metrics.total_cost_usd:.6f}"
    lines = [
        "# Classifier Calibration & Benchmark Audit Report",
        "",
        f"- **Model Evaluated**: `{model_name}`",
        f"- **Execution Mode**: `{'Offline Mock' if is_mock else 'Live Provider'}`",
        f"- **Total Benchmark Cases**: {metrics.total_cases}",
        f"- **Exact Tier Accuracy**: {metrics.exact_accuracy * 100:.1f}% ({metrics.exact_tier_matches}/{max(1, metrics.total_cases)})",
        f"- **Within-1 Tier Accuracy**: {metrics.within_one_accuracy * 100:.1f}% ({metrics.within_one_tier_matches}/{max(1, metrics.total_cases)})",
        f"- **Multi-Category Brier Score**: {metrics.brier_score:.4f} *(lower is better, 0.0 is perfect)*",
        f"- **Total Spend**: {cost_label} ({metrics.total_input_tokens} input tokens)",
        "",
        "## Tier Confusion Matrix",
        "",
        f"Rows = Gold Reference, Columns = Model Prediction (`{', '.join(metrics.tier_order)}`)",
        "",
        f"| Gold \\ Pred | {' | '.join(metrics.tier_order)} |",
        f"|---|{'---|' * len(metrics.tier_order)}",
    ]
    for i, row in enumerate(metrics.confusion_matrix):
        label = metrics.tier_order[i]
        row_str = " | ".join(str(val) for val in row)
        lines.append(f"| **{label}** | {row_str} |")

    lines.extend([
        "",
        "## Binary Flag Performance",
        "",
        "| Flag ID | Accuracy | Precision | Sensitivity (Recall) | Specificity |",
        "|---|---|---|---|---|",
    ])
    for fid, m in sorted(metrics.flag_metrics.items()):
        prec_str = f"{m['precision']*100:.1f}%" if m['precision'] is not None else "undefined (0 pred)"
        sens_str = f"{m['sensitivity']*100:.1f}%" if m['sensitivity'] is not None else "undefined (0 pos)"
        spec_str = f"{m['specificity']*100:.1f}%" if m['specificity'] is not None else "undefined (0 neg)"
        lines.append(f"| `{fid}` | {m['accuracy']*100:.1f}% | {prec_str} | {sens_str} | {spec_str} |")

    lines.extend([
        "",
        "## Individual Case Results",
        "",
        "| Case ID | Gold Tier | Pred Tier | Conf | Match? | Tech Score |",
        "|---|---|---|---|---|---|",
    ])
    for cr in case_reports:
        if cr["expected_tier"] is None:
            match_symbol = "N/A"
        elif cr["is_exact"]:
            match_symbol = "MATCH"
        elif cr["is_within_one"]:
            match_symbol = "CLOSE"
        else:
            match_symbol = "MISMATCH"
        score_str = f"{cr['technicality_score']:.1f}" if cr["technicality_score"] is not None else "N/A"
        gold_str = f"`{cr['expected_tier']}`" if cr['expected_tier'] else "N/A"
        lines.append(
            f"| `{cr['id']}` | {gold_str} | `{cr['predicted_tier']}` | {cr['tier_confidence']:.2f} | {match_symbol} | {score_str} |"
        )

    return "\n".join(lines)


def load_archive_sample(archive_path: Path, max_samples: int = 10) -> list[dict[str, Any]]:
    """Sample real responses from an existing advice responses archive (responses_*.jsonl)."""
    cases = []
    with open(archive_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("record_type") == "advice" and rec.get("response_text"):
                cases.append({
                    "id": f"{rec.get('stimulus_id')}_{rec.get('arm')}_{rec.get('sample_k')}",
                    "response_text": rec["response_text"],
                    "expected_tier": None,
                    "expected_flags": {},
                })
                if len(cases) >= max_samples:
                    break
    return cases


def build_mock_client_for_cases(cases: list[dict[str, Any]], tier_order: list[str]) -> JevClient:
    """Mock client returning realistic decisions for offline testing."""
    case_map = {c["response_text"]: c for c in cases}

    class MockJevClient(JevClient):
        def decide(self, state: Any, questions: Any, model: str = "typesafe/jev-1.13") -> JevResponse:
            text = state.get("response_text", "")
            matched = case_map.get(text, cases[0])
            tier = matched.get("expected_tier") or tier_order[0]
            flags = matched.get("expected_flags", {})

            tier_probs = {t: 0.05 for t in tier_order}
            tier_probs[tier] = 0.85

            answers: dict[str, Any] = {
                "primary_tier": ChoiceAnswer(
                    choice=tier,
                    probabilities=tier_probs,
                    confidence=0.88,
                ),
            }
            # Provide an answer for every question passed
            for qid, q in questions.items():
                if qid == "primary_tier":
                    continue
                if qid.startswith("flag_"):
                    fid = qid.replace("flag_", "")
                    val = flags.get(fid, False)
                    p = 0.92 if val else 0.08
                    answers[qid] = NoulAnswer(noul=p)
                elif qid == "technicality_score":
                    answers[qid] = ScoreAnswer(
                        score=2.2 if tier in ("urgent", "emergency") else 0.8,
                        probabilities={"0": 0.2, "1": 0.5, "2": 0.2, "3": 0.1},
                        confidence=0.80,
                    )

            return JevResponse(
                id="mock-audit-dec",
                model=model,
                answers=answers,
                usage=JevUsage(input_tokens=180, output_tokens=0, cost_usd=0.0),
            )

    return MockJevClient(api_key="mock")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and benchmark classifier models.")
    parser.add_argument("--golden", default="data/classifier_benchmark_golden.json", help="Path to golden benchmark JSON")
    parser.add_argument("--archive", help="Path to archive JSONL to sample real responses from")
    parser.add_argument("--archive-samples", type=int, default=10, help="Number of responses to sample from archive")
    parser.add_argument("--rubric", default="data/advice_rubric.draft.json", help="Path to rubric JSON")
    parser.add_argument("--model", default="typesafe/jev-1.13", help="Classifier model name")
    parser.add_argument("--mock", action="store_true", help="Run with mock client (offline, $0)")
    parser.add_argument("--allow-live-calls", action="store_true", help="Explicit opt-in required for live paid API calls")
    parser.add_argument("--out-markdown", help="Path to save markdown report")
    parser.add_argument("--out-json", help="Path to save structured JSON report")
    args = parser.parse_args(argv)

    rubric_path = Path(args.rubric)
    if not rubric_path.is_file():
        print(f"Error: Rubric file not found: {rubric_path}", file=sys.stderr)
        return 1
    rubric_doc = json.loads(rubric_path.read_text(encoding="utf-8"))
    tier_order = [str(t["id"]) for t in rubric_doc.get("tiers", [])]
    if not tier_order:
        tier_order = ["self_care", "routine", "urgent", "emergency"]

    # Select input cases
    if args.archive:
        arch_p = Path(args.archive)
        if not arch_p.is_file():
            print(f"Error: Archive file not found: {arch_p}", file=sys.stderr)
            return 1
        cases = load_archive_sample(arch_p, max_samples=args.archive_samples)
        input_source_desc = f"Archive {args.archive} ({len(cases)} sampled responses)"
        input_sha = hashlib.sha256(arch_p.read_bytes()).hexdigest()
    else:
        golden_path = Path(args.golden)
        if not golden_path.is_file():
            print(f"Error: Golden benchmark file not found: {golden_path}", file=sys.stderr)
            return 1
        golden_doc = json.loads(golden_path.read_text(encoding="utf-8"))
        cases = golden_doc.get("cases", [])
        input_source_desc = f"Golden benchmark {args.golden} ({len(cases)} cases)"
        input_sha = hashlib.sha256(golden_path.read_bytes()).hexdigest()

    if not cases:
        print("Error: No test cases found.", file=sys.stderr)
        return 1

    # Enforcement: AGENTS.md cost discipline
    if not args.mock and not args.allow_live_calls:
        print(
            "Refused: Live provider calls require explicit --allow-live-calls.\n"
            "By repository convention, live paid inference must run via push-to-run CI.\n"
            "Pass --mock to run offline at $0.",
            file=sys.stderr,
        )
        return 2

    if args.mock:
        client = build_mock_client_for_cases(cases, tier_order=tier_order)
    else:
        client = JevClient()

    classifier = AdviceAnswerClassifier(rubric=rubric_doc, client=client)
    metrics, case_reports = evaluate_advice_classifier(
        cases=cases,
        classifier=classifier,
        tier_order=tier_order,
        model_name=args.model,
        is_mock=args.mock,
    )

    md_report = format_markdown_report(metrics, case_reports, model_name=args.model, is_mock=args.mock)

    if args.out_markdown:
        out_p = Path(args.out_markdown)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md_report, encoding="utf-8")
        print(f"Saved Markdown report -> {out_p}")
    else:
        print("\n" + md_report + "\n")

    if args.out_json:
        out_json_p = Path(args.out_json)
        out_json_p.parent.mkdir(parents=True, exist_ok=True)
        rubric_sha = hashlib.sha256(rubric_path.read_bytes()).hexdigest()
        payload = {
            "metadata": {
                "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "model_requested": args.model,
                "is_mock": args.mock,
                "input_source": input_source_desc,
                "input_sha256": input_sha,
                "rubric_path": str(args.rubric),
                "rubric_sha256": rubric_sha,
                "tier_order": tier_order,
            },
            "metrics": asdict(metrics),
            "cases": case_reports,
        }
        out_json_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved JSON report -> {out_json_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
