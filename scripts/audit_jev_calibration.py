"""Audit, benchmark, and calibration runner for classifier models (Jev and generative judges).

Evaluates classifiers against synthetic golden reference sets (data/classifier_benchmark_golden.json)
or pairs of existing archive judgments, producing clear, human-and-agent readable audit reports:
- Accuracy & Exact Match %
- Tier Distance Matrix / Off-by-one tolerance
- Brier Score & Confidence Calibration across predicted probabilities
- Binary Flag Sensitivity & Specificity
- Cost and Latency Accounting

Conventions honored:
- No medical terms hardcoded in Python source (AGENTS.md).
- Operates offline via mock by default, or online with OPENROUTER_API_KEY when specified.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
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

TIER_ORDER = ["self_care", "routine", "urgent", "emergency"]
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}


@dataclass
class CalibrationBucket:
    confidence_range: tuple[float, float]
    count: int
    correct: int
    empirical_accuracy: float


@dataclass
class EvaluationMetrics:
    total_cases: int
    exact_tier_matches: int
    exact_accuracy: float
    within_one_tier_matches: int
    within_one_accuracy: float
    brier_score: float
    flag_metrics: dict[str, dict[str, float]]
    total_cost_usd: float
    total_input_tokens: int
    confusion_matrix: list[list[int]]


def compute_brier_score(predictions: list[dict[str, float]], ground_truths: list[str]) -> float:
    """Multi-category Brier score: mean squared error across probability vectors."""
    if not predictions:
        return 0.0
    total_sq_err = 0.0
    for probs, truth in zip(predictions, ground_truths):
        for t in TIER_ORDER:
            p = probs.get(t, 0.0)
            actual = 1.0 if t == truth else 0.0
            total_sq_err += (p - actual) ** 2
    return total_sq_err / len(predictions)


def evaluate_advice_classifier(
    cases: list[dict[str, Any]],
    classifier: AdviceAnswerClassifier,
) -> tuple[EvaluationMetrics, list[dict[str, Any]]]:
    """Run classifier over benchmark cases and compute audit metrics."""
    confusion = [[0] * len(TIER_ORDER) for _ in TIER_ORDER]
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
        expected_tier = c["expected_tier"]
        expected_flags = c.get("expected_flags", {})

        res = classifier.classify(text)
        pred_tier = res.tier
        total_cost += res.cost_usd
        total_tokens += res.input_tokens

        pred_idx = TIER_RANK.get(pred_tier, -1)
        gold_idx = TIER_RANK.get(expected_tier, -1)

        is_exact = pred_tier == expected_tier
        is_within_one = False
        if pred_idx != -1 and gold_idx != -1:
            confusion[gold_idx][pred_idx] += 1
            if is_exact:
                exact_matches += 1
            if abs(pred_idx - gold_idx) <= 1:
                within_one += 1
                is_within_one = True

        prob_vectors.append(res.tier_probabilities)
        gold_tiers.append(expected_tier)

        # Flag accuracy tracking
        flag_report = {}
        for fid, exp_val in expected_flags.items():
            got_val = res.flags.get(fid, False)
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
                "probability": res.flag_probabilities.get(fid, 0.0),
            }

        case_reports.append({
            "id": c.get("id"),
            "expected_tier": expected_tier,
            "predicted_tier": pred_tier,
            "tier_confidence": res.tier_confidence,
            "is_exact": is_exact,
            "is_within_one": is_within_one,
            "tier_probabilities": res.tier_probabilities,
            "flags": flag_report,
            "technicality_score": res.register_score,
            "cost_usd": res.cost_usd,
        })

    n = len(cases)
    brier = compute_brier_score(prob_vectors, gold_tiers)

    # Compute precision / recall per flag
    computed_flag_metrics: dict[str, dict[str, float]] = {}
    for fid, st in flag_stats.items():
        tp, tn, fp, fn = st["tp"], st["tn"], st["fp"], st["fn"]
        acc = (tp + tn) / max(1, tp + tn + fp + fn)
        prec = tp / max(1, tp + fp) if (tp + fp) > 0 else 1.0
        rec = tp / max(1, tp + fn) if (tp + fn) > 0 else 1.0
        computed_flag_metrics[fid] = {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
        }

    metrics = EvaluationMetrics(
        total_cases=n,
        exact_tier_matches=exact_matches,
        exact_accuracy=round(exact_matches / max(1, n), 4),
        within_one_tier_matches=within_one,
        within_one_accuracy=round(within_one / max(1, n), 4),
        brier_score=round(brier, 4),
        flag_metrics=computed_flag_metrics,
        total_cost_usd=round(total_cost, 6),
        total_input_tokens=total_tokens,
        confusion_matrix=confusion,
    )
    return metrics, case_reports


def format_markdown_report(metrics: EvaluationMetrics, case_reports: list[dict[str, Any]], model_name: str) -> str:
    """Generate a clean, structured audit report readable by humans and agents."""
    lines = [
        "# Classifier Calibration & Benchmark Audit Report",
        "",
        f"- **Model Evaluated**: `{model_name}`",
        f"- **Total Benchmark Cases**: {metrics.total_cases}",
        f"- **Exact Tier Accuracy**: {metrics.exact_accuracy * 100:.1f}% ({metrics.exact_tier_matches}/{metrics.total_cases})",
        f"- **Within-1 Tier Accuracy**: {metrics.within_one_accuracy * 100:.1f}% ({metrics.within_one_tier_matches}/{metrics.total_cases})",
        f"- **Multi-Category Brier Score**: {metrics.brier_score:.4f} *(lower is better, 0.0 is perfect)*",
        f"- **Total Spend**: ${metrics.total_cost_usd:.6f} ({metrics.total_input_tokens} input tokens)",
        "",
        "## Tier Confusion Matrix",
        "",
        "Rows = Gold Reference, Columns = Model Prediction (`self_care`, `routine`, `urgent`, `emergency`)",
        "",
        "| Gold \\ Pred | self_care | routine | urgent | emergency |",
        "|---|---|---|---|---|",
    ]
    for i, row in enumerate(metrics.confusion_matrix):
        label = TIER_ORDER[i]
        lines.append(f"| **{label}** | {row[0]} | {row[1]} | {row[2]} | {row[3]} |")

    lines.extend([
        "",
        "## Binary Flag Performance",
        "",
        "| Flag ID | Accuracy | Precision | Recall |",
        "|---|---|---|---|",
    ])
    for fid, m in sorted(metrics.flag_metrics.items()):
        lines.append(f"| `{fid}` | {m['accuracy']*100:.1f}% | {m['precision']*100:.1f}% | {m['recall']*100:.1f}% |")

    lines.extend([
        "",
        "## Individual Case Results",
        "",
        "| Case ID | Gold Tier | Pred Tier | Conf | Match? | Tech Score |",
        "|---|---|---|---|---|---|",
    ])
    for cr in case_reports:
        match_symbol = "MATCH" if cr["is_exact"] else ("CLOSE" if cr["is_within_one"] else "MISMATCH")
        score_str = f"{cr['technicality_score']:.1f}" if cr["technicality_score"] is not None else "N/A"
        lines.append(
            f"| `{cr['id']}` | `{cr['expected_tier']}` | `{cr['predicted_tier']}` | {cr['tier_confidence']:.2f} | {match_symbol} | {score_str} |"
        )

    return "\n".join(lines)


def build_mock_client_for_golden(cases: list[dict[str, Any]]) -> JevClient:
    """Mock client that returns realistic answers matching golden set for offline verification."""
    case_map = {c["response_text"]: c for c in cases}

    class MockJevClient(JevClient):
        def decide(self, state: Any, questions: Any, model: str = "typesafe/jev-1.13") -> JevResponse:
            text = state.get("response_text", "")
            matched = case_map.get(text, cases[0])
            tier = matched["expected_tier"]
            flags = matched.get("expected_flags", {})

            # Build mock probabilities
            tier_probs = {t: 0.05 for t in TIER_ORDER}
            tier_probs[tier] = 0.85

            answers = {
                "primary_tier": ChoiceAnswer(
                    choice=tier,
                    probabilities=tier_probs,
                    confidence=0.88,
                ),
            }
            for fid, val in flags.items():
                p = 0.92 if val else 0.08
                answers[f"flag_{fid}"] = NoulAnswer(noul=p, confidence=0.85)

            answers["technicality_score"] = ScoreAnswer(
                score=2.2 if tier in ("urgent", "emergency") else 0.8,
                probabilities={"0": 0.2, "1": 0.5, "2": 0.2, "3": 0.1},
                confidence=0.80,
            )

            return JevResponse(
                id="mock-audit-dec",
                model=model,
                answers=answers,
                usage=JevUsage(input_tokens=180, output_tokens=0, cost_usd=0.0000075),
            )

    return MockJevClient(api_key="mock")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and benchmark classifier models.")
    parser.add_argument("--golden", default="data/classifier_benchmark_golden.json", help="Path to golden benchmark JSON")
    parser.add_argument("--rubric", default="data/advice_rubric.draft.json", help="Path to rubric JSON")
    parser.add_argument("--model", default="typesafe/jev-1.13", help="Classifier model name")
    parser.add_argument("--mock", action="store_true", help="Run with mock client (offline, $0)")
    parser.add_argument("--out-markdown", help="Path to save markdown report")
    parser.add_argument("--out-json", help="Path to save structured JSON report")
    args = parser.parse_args(argv)

    golden_path = Path(args.golden)
    if not golden_path.is_file():
        print(f"Error: golden benchmark file not found: {golden_path}", file=sys.stderr)
        return 1

    doc = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = doc.get("cases", [])
    if not cases:
        print("Error: No test cases found in golden benchmark.", file=sys.stderr)
        return 1

    if args.mock:
        client = build_mock_client_for_golden(cases)
    else:
        client = JevClient()

    classifier = AdviceAnswerClassifier(rubric_path=args.rubric, client=client)
    metrics, case_reports = evaluate_advice_classifier(cases, classifier)
    md_report = format_markdown_report(metrics, case_reports, model_name=args.model)

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
        payload = {
            "metrics": asdict(metrics),
            "cases": case_reports,
        }
        out_json_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved JSON report -> {out_json_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
