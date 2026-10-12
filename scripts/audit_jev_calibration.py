"""Audit, benchmark, and calibration runner for classifier models (Jev and generative judges).

Evaluates classifiers against:
1. Synthetic golden reference sets (data/classifier_benchmark_golden.json)
2. Sampled advice archives (data/advice/responses_*.jsonl) paired with Claude Haiku judgments
3. Sampled Petri conversation transcripts (data/petri/runs/*/transcripts.jsonl)

Produces clear, human-and-agent readable audit reports:
- Exact Tier Accuracy & Distance Matrix (derived dynamically from rubric tier order)
- Side-by-side agreement against Claude Haiku / Primary Judge
- Petri multi-turn conversational register, drift detection, and severity score
- Multi-Category Brier Score & Confidence Calibration
- Binary Flag Sensitivity, Specificity, Precision
- Cost and Latency Accounting (actual provider spend vs estimated list price)
- Full artifact provenance: input hashes, parameters, model identifiers, and response records

Conventions honored:
- No medical terms hardcoded in Python source (AGENTS.md).
- Gated CI mode: live calls require CI execution with --ci-live (AGENTS.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from scripts.advice_eval import verify_chain
from scripts.jev_classifier import AdviceAnswerClassifier, PetriRegisterClassifier


@dataclass
class EvaluationMetrics:
    total_cases: int
    has_ground_truth: bool
    exact_tier_matches: int | None
    exact_accuracy: float | None
    within_one_tier_matches: int | None
    within_one_accuracy: float | None
    brier_score: float | None
    flag_metrics: dict[str, dict[str, Any]]
    total_cost_usd: float
    total_estimated_cost_usd: float
    total_input_tokens: int
    confusion_matrix: list[list[int]] | None
    tier_order: list[str]
    served_models: list[str]
    unbilled_calls_count: int = 0


def compute_brier_score(predictions: list[dict[str, float]], ground_truths: list[str], tier_order: list[str]) -> float:
    """Multi-category Brier score: mean squared error across probability vectors."""
    if not predictions or not ground_truths:
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
    is_mock: bool = True,
) -> tuple[EvaluationMetrics, list[dict[str, Any]]]:
    """Run classifier over benchmark cases and compute audit metrics."""
    tier_rank = {t: i for i, t in enumerate(tier_order)}
    has_ground_truth = any(c.get("expected_tier") is not None for c in cases)
    confusion = [[0] * len(tier_order) for _ in tier_order] if has_ground_truth else None

    exact_matches = 0
    within_one = 0
    prob_vectors: list[dict[str, float]] = []
    gold_tiers: list[str] = []
    flag_stats: dict[str, dict[str, int]] = {}

    total_actual_cost = 0.0
    total_est_cost = 0.0
    total_tokens = 0
    unbilled_calls = 0
    case_reports: list[dict[str, Any]] = []
    served_models_set: set[str] = set()

    for c in cases:
        text = c["response_text"]
        expected_tier = c.get("expected_tier")
        expected_flags = c.get("expected_flags", {})

        res = classifier.classify(text, model=model_name)
        pred_tier = res.tier
        served_model = res.raw_response.model or model_name
        served_models_set.add(served_model)

        if is_mock:
            actual_cost: float | None = 0.0
        else:
            if res.cost_usd is None:
                actual_cost = None
                unbilled_calls += 1
            else:
                actual_cost = res.cost_usd
                total_actual_cost += actual_cost
        est_cost = res.estimated_cost_usd or 0.0
        total_est_cost += est_cost
        total_tokens += res.input_tokens

        pred_idx = tier_rank.get(pred_tier, -1)
        gold_idx = tier_rank.get(expected_tier, -1) if expected_tier else -1

        is_exact = False
        is_within_one = False
        if has_ground_truth and expected_tier is not None:
            if gold_idx != -1 and pred_idx != -1 and confusion is not None:
                confusion[gold_idx][pred_idx] += 1
                if pred_tier == expected_tier:
                    exact_matches += 1
                    is_exact = True
                if abs(pred_idx - gold_idx) <= 1:
                    within_one += 1
                    is_within_one = True

            prob_vectors.append(res.tier_probabilities)
            gold_tiers.append(expected_tier)

        # Flag accuracy tracking
        flag_report = {}
        for fid, exp_val in expected_flags.items():
            if fid not in res.flags:
                raise ValueError(
                    f"Classifier response missing expected flag {fid!r} present in reference judgment"
                )
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
        for fid, got_val in res.flags.items():
            if fid not in flag_report:
                flag_report[fid] = {
                    "expected": None,
                    "predicted": got_val,
                    "probability": res.flag_probabilities.get(fid),
                }

        case_reports.append({
            "id": c.get("id"),
            "response_text": text,
            "expected_tier": expected_tier,
            "primary_judge_tier": c.get("primary_judge_tier"),
            "predicted_tier": pred_tier,
            "tier_confidence": res.tier_confidence,
            "is_exact": is_exact if has_ground_truth else None,
            "is_within_one": is_within_one if has_ground_truth else None,
            "tier_probabilities": res.tier_probabilities,
            "flags": flag_report,
            "technicality_score": res.register_score,
            "served_model": served_model,
            "cost_usd": actual_cost,
            "estimated_cost_usd": est_cost,
        })

    n = len(cases)
    if has_ground_truth and gold_tiers:
        brier: float | None = round(compute_brier_score(prob_vectors, gold_tiers, tier_order), 4)
        exact_acc: float | None = round(exact_matches / max(1, len(gold_tiers)), 4)
        within_acc: float | None = round(within_one / max(1, len(gold_tiers)), 4)
        exact_match_count: int | None = exact_matches
        within_match_count: int | None = within_one
    else:
        brier = None
        exact_acc = None
        within_acc = None
        exact_match_count = None
        within_match_count = None

    computed_flag_metrics: dict[str, dict[str, Any]] = {}
    for fid, st in flag_stats.items():
        tp, tn, fp, fn = st["tp"], st["tn"], st["fp"], st["fn"]
        total = tp + tn + fp + fn
        acc = (tp + tn) / max(1, total)
        prec = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None
        sens = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None
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
        has_ground_truth=has_ground_truth,
        exact_tier_matches=exact_match_count,
        exact_accuracy=exact_acc,
        within_one_tier_matches=within_match_count,
        within_one_accuracy=within_acc,
        brier_score=brier,
        flag_metrics=computed_flag_metrics,
        total_cost_usd=round(total_actual_cost, 6),
        total_estimated_cost_usd=round(total_est_cost, 6),
        total_input_tokens=total_tokens,
        confusion_matrix=confusion,
        tier_order=tier_order,
        served_models=sorted(served_models_set),
        unbilled_calls_count=unbilled_calls,
    )
    return metrics, case_reports


def evaluate_petri_classifier(
    transcripts_path: Path,
    classifier: PetriRegisterClassifier,
    max_conversations: int = 5,
    model_name: str = "typesafe/jev-1.13",
    is_mock: bool = True,
) -> list[dict[str, Any]]:
    """Evaluate PetriRegisterClassifier on multi-turn conversation transcripts."""
    results = []
    conversations_count = 0
    with open(transcripts_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            conv_id = rec.get("conversation_id", "conv")[:12]
            turns = rec.get("turns", [])
            has_assistant_turn = False
            for i, t in enumerate(turns):
                if t.get("role") == "assistant":
                    has_assistant_turn = True
                    asst_text = t.get("text", "")
                    user_turn = turns[i - 1].get("text", "") if i > 0 else None
                    prior = " ".join(pt.get("text", "") for pt in turns[: max(0, i - 1)]) if i > 1 else None

                    res = classifier.classify_turn(
                        assistant_turn=asst_text,
                        user_turn=user_turn,
                        prior_context=prior,
                        model=model_name,
                    )
                    actual_cost: float | None = 0.0 if is_mock else res.cost_usd
                    served_m = res.raw_response.model or model_name
                    results.append({
                        "conversation_id": conv_id,
                        "turn_index": i,
                        "tone_choice": res.tone_choice,
                        "tone_confidence": res.tone_confidence,
                        "has_register_drift": res.has_register_drift,
                        "drift_probability": res.drift_probability,
                        "register_score": res.register_score,
                        "cost_usd": actual_cost,
                        "estimated_cost_usd": res.estimated_cost_usd or 0.0,
                        "input_tokens": res.input_tokens,
                        "served_model": served_m,
                    })
            if has_assistant_turn:
                conversations_count += 1
                if conversations_count >= max_conversations:
                    break
    return results


def format_markdown_report(
    metrics: EvaluationMetrics,
    case_reports: list[dict[str, Any]],
    model_name: str,
    is_mock: bool = True,
    petri_results: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a clean, structured audit report readable by humans and agents."""
    if metrics.unbilled_calls_count > 0:
        cost_label = f"${metrics.total_cost_usd:.6f} (+{metrics.unbilled_calls_count} calls with null provider billing)"
    elif is_mock:
        cost_label = f"${metrics.total_cost_usd:.6f} ($0.0 mock run)"
    else:
        cost_label = f"${metrics.total_cost_usd:.6f}"
    served_str = ", ".join(f"`{m}`" for m in metrics.served_models) or f"`{model_name}`"

    lines = [
        "# Classifier Calibration & Benchmark Audit Report",
        "",
        f"- **Model Requested**: `{model_name}`",
        f"- **Model(s) Served**: {served_str}",
        f"- **Execution Mode**: `{'Offline Mock ($0)' if is_mock else 'Live CI Evaluation'}`",
        f"- **Total Advice Cases**: {metrics.total_cases}",
    ]

    if petri_results:
        petri_convs = len({r["conversation_id"] for r in petri_results})
        lines.append(f"- **Total Petri Cases**: {len(petri_results)} assistant turns ({petri_convs} conversations)")

    if metrics.has_ground_truth and metrics.exact_accuracy is not None:
        lines.extend([
            f"- **Exact Tier Accuracy**: {metrics.exact_accuracy * 100:.1f}% ({metrics.exact_tier_matches}/{metrics.total_cases})",
            f"- **Within-1 Tier Accuracy**: {metrics.within_one_accuracy * 100:.1f}% ({metrics.within_one_tier_matches}/{metrics.total_cases})",
            f"- **Multi-Category Brier Score**: {metrics.brier_score:.4f} *(lower is better, 0.0 is perfect)*",
        ])
    else:
        lines.extend([
            "- **Ground Truth**: *None provided (archive sampling)*",
            f"- **Predictions Generated**: {metrics.total_cases}/{metrics.total_cases} (100% label coverage)",
            "- **Accuracy / Brier Score**: *Undefined (no gold reference tiers in input)*",
        ])

    lines.extend([
        f"- **Total Spend**: {cost_label} ({metrics.total_input_tokens} input tokens, estimated list price: ${metrics.total_estimated_cost_usd:.6f})",
        "",
    ])

    if metrics.confusion_matrix:
        lines.extend([
            "## Tier Confusion Matrix",
            "",
            f"Rows = Gold Reference, Columns = Model Prediction (`{', '.join(metrics.tier_order)}`)",
            "",
            f"| Gold \\ Pred | {' | '.join(metrics.tier_order)} |",
            f"|---|{'---|' * len(metrics.tier_order)}",
        ])
        for i, row in enumerate(metrics.confusion_matrix):
            label = metrics.tier_order[i]
            row_str = " | ".join(str(val) for val in row)
            lines.append(f"| **{label}** | {row_str} |")
        lines.append("")

    if metrics.flag_metrics:
        lines.extend([
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
        lines.append("")

    lines.extend([
        "## Advice Evaluation Predictions",
        "",
        "| Case ID | Primary Judge (Claude) | Pred Tier (Jev) | Conf | Match? | Tech Score |",
        "|---|---|---|---|---|---|",
    ])
    for cr in case_reports:
        pj_tier = cr.get("primary_judge_tier") or cr.get("expected_tier")
        if pj_tier is None:
            match_symbol = "N/A"
            gold_str = "N/A"
        else:
            gold_str = f"`{pj_tier}`"
            match_symbol = "MATCH" if cr["predicted_tier"] == pj_tier else "DIFF"
        score_str = f"{cr['technicality_score']:.1f}" if cr["technicality_score"] is not None else "N/A"
        lines.append(
            f"| `{cr['id']}` | {gold_str} | `{cr['predicted_tier']}` | {cr['tier_confidence']:.2f} | {match_symbol} | {score_str} |"
        )
    lines.append("")

    if petri_results:
        lines.extend([
            "## Multi-Turn Petri Register Predictions",
            "",
            "| Conv ID | Turn | Jev Register Tone | Drift Detected? | Drift Prob | Formality Score |",
            "|---|---|---|---|---|---|",
        ])
        for pr in petri_results:
            drift_str = "**YES**" if pr["has_register_drift"] else "No"
            lines.append(
                f"| `{pr['conversation_id']}` | Turn {pr['turn_index']} | `{pr['tone_choice']}` ({pr['tone_confidence']:.2f}) | {drift_str} | {pr['drift_probability']:.2f} | {pr['register_score']:.1f} |"
            )
        lines.append("")

    return "\n".join(lines)


def load_advice_archive_with_judgments(
    archive_path: Path,
    judgments_path: Path | None = None,
    max_samples: int = 10,
) -> list[dict[str, Any]]:
    """Sample real responses from an existing advice responses archive (responses_*.jsonl)
    paired with Claude Haiku's judgments if judgments_*.jsonl exists."""
    haiku_judgments = {}
    if judgments_path and judgments_path.is_file():
        with open(judgments_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("tier"):
                    key = (rec.get("stimulus_id"), rec.get("arm"), rec.get("sample_k"))
                    haiku_judgments[key] = {
                        "tier": rec["tier"],
                        "flags": rec.get("flags") or {},
                    }

    with open(archive_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    ok, msg = verify_chain(rows)
    if not ok:
        raise ValueError(f"Broken hash chain in response archive {archive_path}: {msg}")

    cases = []
    for rec in rows:
        if rec.get("record_type") == "advice" and rec.get("response_text"):
            sid = rec.get("stimulus_id")
            arm = rec.get("arm")
            k = rec.get("sample_k")
            pj_data = haiku_judgments.get((sid, arm, k), {})
            pj_tier = pj_data.get("tier")
            pj_flags = pj_data.get("flags", {})
            cases.append({
                "id": f"{sid}_{arm}_{k}",
                "response_text": rec["response_text"],
                "expected_tier": pj_tier,
                "primary_judge_tier": pj_tier,
                "expected_flags": pj_flags,
            })
            if len(cases) >= max_samples:
                break
    return cases


def build_mock_client_for_cases(cases: list[dict[str, Any]], tier_order: list[str]) -> JevClient:
    """Mock client returning realistic, normalized decisions for offline testing."""
    case_map = {c["response_text"]: c for c in cases}

    class MockJevClient(JevClient):
        def decide(self, state: Any, questions: Any, model: str = "typesafe/jev-1.13") -> JevResponse:
            text = state.get("response_text") or state.get("assistant_reply") or ""
            matched = case_map.get(text, cases[0] if cases else {})
            tier = matched.get("expected_tier") or tier_order[0]
            flags = matched.get("expected_flags", {})

            num_tiers = len(tier_order)
            tier_probs = {}
            if num_tiers == 1:
                tier_probs[tier_order[0]] = 1.0
            else:
                target_p = 0.85
                rem_p = round((1.0 - target_p) / (num_tiers - 1), 6)
                for t in tier_order:
                    tier_probs[t] = target_p if t == tier else rem_p
                tot = sum(tier_probs.values())
                if abs(tot - 1.0) > 1e-6:
                    for t in tier_order:
                        if t != tier:
                            tier_probs[t] += (1.0 - tot)
                            break

            answers: dict[str, Any] = {
                "primary_tier": ChoiceAnswer(
                    choice=tier,
                    probabilities=tier_probs,
                    confidence=0.88,
                ),
                "register_tone": ChoiceAnswer(
                    choice="mixed",
                    probabilities={"colloquial": 0.2, "mixed": 0.7, "clinical": 0.1},
                    confidence=0.85,
                ),
                "register_drift": NoulAnswer(noul=0.15),
                "severity_score": ScoreAnswer(
                    score=1.4,
                    probabilities={"0": 0.1, "1": 0.5, "2": 0.3, "3": 0.1},
                    confidence=0.80,
                ),
            }
            for qid in questions:
                if qid in answers:
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
                usage=JevUsage(input_tokens=180, output_tokens=0, cost_usd=None, estimated_cost_usd=0.0000075),
            )

    return MockJevClient(api_key="mock")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and benchmark classifier models.")
    parser.add_argument("--golden", default="data/classifier_benchmark_golden.json", help="Path to golden benchmark JSON")
    parser.add_argument("--archive", help="Path to archive JSONL to sample real responses from")
    parser.add_argument("--judgments", help="Path to archive judgments JSONL to pair with archive responses")
    parser.add_argument("--petri-transcripts", help="Path to Petri transcripts.jsonl to audit multi-turn register")
    parser.add_argument("--archive-samples", type=int, default=10, help="Number of responses to sample from archive")
    parser.add_argument("--petri-conversations", type=int, default=5, help="Number of Petri conversations to audit")
    parser.add_argument("--rubric", default="data/advice_rubric.draft.json", help="Path to rubric JSON")
    parser.add_argument("--register-rubric", default="data/register_rubric.json", help="Path to register rubric JSON")
    parser.add_argument("--model", default="typesafe/jev-1.13", help="Classifier model name")
    parser.add_argument("--max-spend", type=float, default=0.25, help="Hard spend ceiling in USD")
    parser.add_argument("--ci-live", action="store_true", help="Gated CI run mode using live OPENROUTER_API_KEY in GitHub Actions")
    parser.add_argument("--out-markdown", help="Path to save markdown report")
    parser.add_argument("--out-json", help="Path to save structured JSON report")
    args = parser.parse_args(argv)

    rubric_path = Path(args.rubric)
    if not rubric_path.is_file():
        print(f"Refused: Rubric file not found: {rubric_path}", file=sys.stderr)
        return 1
    rubric_doc = json.loads(rubric_path.read_text(encoding="utf-8"))
    raw_tiers = rubric_doc.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        print(f"Refused: Rubric {args.rubric} contains no tier definitions.", file=sys.stderr)
        return 1
    tier_order = [str(t["id"]) for t in raw_tiers if isinstance(t, dict) and "id" in t]
    if not tier_order:
        print(f"Refused: Rubric {args.rubric} has no valid tier IDs.", file=sys.stderr)
        return 1

    reg_rubric_path = Path(args.register_rubric)
    if not reg_rubric_path.is_file():
        print(f"Refused: Register rubric file not found: {reg_rubric_path}", file=sys.stderr)
        return 1
    reg_rubric_sha = hashlib.sha256(reg_rubric_path.read_bytes()).hexdigest()

    # Validate inputs
    arch_p: Path | None = None
    judg_p: Path | None = None
    golden_path: Path | None = None
    petri_p: Path | None = None

    if args.archive:
        arch_p = Path(args.archive)
        if not arch_p.is_file():
            print(f"Refused: Archive file not found: {arch_p}", file=sys.stderr)
            return 1
        if args.judgments:
            judg_p = Path(args.judgments)
            if not judg_p.is_file():
                print(f"Refused: Judgments file not found: {judg_p}", file=sys.stderr)
                return 1
        else:
            cand_judg = arch_p.with_name(arch_p.stem.replace("responses_", "judgments_") + ".jsonl")
            if cand_judg.is_file():
                judg_p = cand_judg

        try:
            cases = load_advice_archive_with_judgments(arch_p, judgments_path=judg_p, max_samples=args.archive_samples)
        except ValueError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1

        input_source_desc = f"Archive {args.archive} ({len(cases)} sampled responses, paired with Haiku judgments: {judg_p is not None})"
        input_sha = hashlib.sha256(arch_p.read_bytes()).hexdigest()
    else:
        golden_path = Path(args.golden)
        if not golden_path.is_file():
            print(f"Refused: Golden benchmark file not found: {golden_path}", file=sys.stderr)
            return 1
        golden_doc = json.loads(golden_path.read_text(encoding="utf-8"))
        cases = golden_doc.get("cases", [])
        input_source_desc = f"Golden benchmark {args.golden} ({len(cases)} cases)"
        input_sha = hashlib.sha256(golden_path.read_bytes()).hexdigest()

    if not cases:
        print(f"Refused: No test cases found in input {input_source_desc}.", file=sys.stderr)
        return 1

    if args.petri_transcripts:
        petri_p = Path(args.petri_transcripts)
        if not petri_p.is_file():
            print(f"Refused: Petri transcripts file not found: {petri_p}", file=sys.stderr)
            return 1

    # Determine execution mode: local runs are mock-only ($0); live requires --ci-live in CI with env key
    if args.ci_live:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            print("Refused: --ci-live is permitted only inside GitHub Actions CI environment.", file=sys.stderr)
            return 1
        if not os.environ.get("OPENROUTER_API_KEY"):
            print("Refused: OPENROUTER_API_KEY is missing in GitHub Actions environment.", file=sys.stderr)
            return 1
        is_live = True
        client = JevClient()
    else:
        is_live = False
        client = build_mock_client_for_cases(cases, tier_order=tier_order)

    classifier = AdviceAnswerClassifier(rubric=rubric_doc, client=client)
    metrics, case_reports = evaluate_advice_classifier(
        cases=cases,
        classifier=classifier,
        tier_order=tier_order,
        model_name=args.model,
        is_mock=not is_live,
    )

    petri_results = None
    if petri_p:
        petri_clf = PetriRegisterClassifier(client=client)
        petri_results = evaluate_petri_classifier(
            transcripts_path=petri_p,
            classifier=petri_clf,
            max_conversations=args.petri_conversations,
            model_name=args.model,
            is_mock=not is_live,
        )
        if not petri_results:
            print(f"Refused: No evaluable assistant turns found in Petri transcripts {petri_p}.", file=sys.stderr)
            return 1

        petri_cost = sum(r["cost_usd"] for r in petri_results if r["cost_usd"] is not None)
        unbilled_petri = sum(1 for r in petri_results if r["cost_usd"] is None)
        petri_est_cost = sum(r["estimated_cost_usd"] for r in petri_results)
        petri_tokens = sum(r.get("input_tokens", 0) for r in petri_results)
        metrics.total_cost_usd = round(metrics.total_cost_usd + petri_cost, 6)
        metrics.total_estimated_cost_usd = round(metrics.total_estimated_cost_usd + petri_est_cost, 6)
        metrics.total_input_tokens += petri_tokens
        metrics.unbilled_calls_count += unbilled_petri
        for r in petri_results:
            sm = r.get("served_model")
            if sm and sm not in metrics.served_models:
                metrics.served_models.append(sm)
                metrics.served_models.sort()

    if is_live and metrics.total_cost_usd > args.max_spend:
        print(f"Refused: Total spend ${metrics.total_cost_usd:.6f} exceeded max_spend ceiling ${args.max_spend:.6f}", file=sys.stderr)
        return 6

    md_report = format_markdown_report(metrics, case_reports, model_name=args.model, is_mock=not is_live, petri_results=petri_results)

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

        prov: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model_requested": args.model,
            "models_served": metrics.served_models,
            "is_mock": not is_live,
            "rubric": {
                "path": str(args.rubric),
                "sha256": rubric_sha,
            },
            "register_rubric": {
                "path": str(reg_rubric_path),
                "sha256": reg_rubric_sha,
            },
            "parameters": {
                "archive_samples": args.archive_samples if arch_p else None,
                "petri_conversations": args.petri_conversations if petri_p else None,
                "max_spend": args.max_spend,
            },
        }
        if arch_p:
            prov["advice_archive"] = {
                "path": str(arch_p),
                "sha256": input_sha,
                "samples_evaluated": len(cases),
            }
            if judg_p and judg_p.is_file():
                prov["advice_judgments"] = {
                    "path": str(judg_p),
                    "sha256": hashlib.sha256(judg_p.read_bytes()).hexdigest(),
                }
        elif golden_path:
            prov["golden_benchmark"] = {
                "path": str(golden_path),
                "sha256": input_sha,
                "cases_evaluated": len(cases),
            }
        if petri_p:
            prov["petri_transcripts"] = {
                "path": str(petri_p),
                "sha256": hashlib.sha256(petri_p.read_bytes()).hexdigest(),
                "max_conversations": args.petri_conversations,
                "turns_evaluated": len(petri_results) if petri_results else 0,
            }

        payload = {
            "metadata": prov,
            "metrics": asdict(metrics),
            "cases": case_reports,
            "petri_cases": petri_results or [],
        }
        out_json_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved JSON report -> {out_json_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
