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
import copy
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


def save_checkpoint(
    checkpoint_path: Path,
    advice_cases: list[dict[str, Any]],
    petri_cases: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save intermediate evaluation progress to disk atomically."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "metadata": metadata or {},
        "advice_cases": advice_cases,
        "petri_cases": petri_cases or [],
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp_path = checkpoint_path.with_name(f"{checkpoint_path.name}.tmp")
    tmp_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp_path.replace(checkpoint_path)


class EvaluationInterruptedError(Exception):
    """Raised when evaluation is interrupted by ceiling or error, carrying partial progress."""

    def __init__(
        self,
        message: str,
        exit_code: int = 1,
        metrics: EvaluationMetrics | None = None,
        case_reports: list[dict[str, Any]] | None = None,
        petri_results: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.exit_code = exit_code
        self.metrics = metrics
        self.case_reports = case_reports
        self.petri_results = petri_results


def build_advice_metrics(
    n_cases: int,
    has_ground_truth: bool,
    exact_matches: int,
    within_one: int,
    gold_tiers: list[str],
    prob_vectors: list[dict[str, float]],
    tier_order: list[str],
    flag_stats: dict[str, dict[str, int]],
    confusion: list[list[int]] | None,
    total_actual_cost: float,
    total_est_cost: float,
    total_tokens: int,
    served_models_set: set[str],
    unbilled_calls: int,
) -> EvaluationMetrics:
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

    return EvaluationMetrics(
        total_cases=n_cases,
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


def update_metrics_with_petri(metrics: EvaluationMetrics, petri_results: list[dict[str, Any]]) -> None:
    """Fold Petri evaluation results into existing evaluation metrics."""
    petri_cost = sum(r.get("cost_usd", 0.0) or 0.0 for r in petri_results if r.get("cost_usd") is not None)
    unbilled_petri = sum(1 for r in petri_results if r.get("cost_usd") is None)
    petri_est_cost = sum(r.get("estimated_cost_usd", 0.0) or 0.0 for r in petri_results)
    petri_tokens = sum(r.get("input_tokens", 0) or 0 for r in petri_results)
    metrics.total_cost_usd = round(metrics.total_cost_usd + petri_cost, 6)
    metrics.total_estimated_cost_usd = round(metrics.total_estimated_cost_usd + petri_est_cost, 6)
    metrics.total_input_tokens += petri_tokens
    metrics.unbilled_calls_count += unbilled_petri
    for r in petri_results:
        sm = r.get("served_model")
        if sm and sm not in metrics.served_models:
            metrics.served_models.append(sm)
            metrics.served_models.sort()


def evaluate_advice_classifier(
    cases: list[dict[str, Any]],
    classifier: AdviceAnswerClassifier,
    tier_order: list[str],
    model_name: str,
    is_mock: bool = True,
    checkpoint_path: Path | None = None,
    cached_cases: list[dict[str, Any]] | None = None,
    cached_petri: list[dict[str, Any]] | None = None,
    checkpoint_metadata: dict[str, Any] | None = None,
    max_spend: float | None = None,
    checkpoint_interval: int = 25,
    max_petri_conversations: int | None = None,
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

    cached_map = {c["id"]: c for c in (cached_cases or []) if c.get("id")}

    # Scope cached_petri to conversations within the requested limit
    scoped_cached_petri: list[dict[str, Any]] = []
    if cached_petri:
        if max_petri_conversations is not None and max_petri_conversations > 0:
            seen_convs: list[str] = []
            for r in cached_petri:
                cid = r.get("conversation_id")
                if cid and cid not in seen_convs:
                    seen_convs.append(cid)
            allowed_convs = set(seen_convs[:max_petri_conversations])
            scoped_cached_petri = [r for r in cached_petri if r.get("conversation_id") in allowed_convs]
        elif max_petri_conversations == 0:
            scoped_cached_petri = []
        else:
            scoped_cached_petri = cached_petri

    try:
        for count, c in enumerate(cases, start=1):
            cid = c.get("id")
            text = c["response_text"]
            expected_tier = c.get("expected_tier")
            expected_flags = c.get("expected_flags", {})

            if cid and cid in cached_map:
                cached_rep = cached_map[cid]
                pred_tier = cached_rep["predicted_tier"]
                served_model = cached_rep.get("served_model") or model_name
                served_models_set.add(served_model)

                actual_cost = cached_rep.get("cost_usd")
                if actual_cost is not None:
                    total_actual_cost += actual_cost
                elif not is_mock:
                    unbilled_calls += 1

                est_cost = cached_rep.get("estimated_cost_usd") or 0.0
                total_est_cost += est_cost
                in_tokens = cached_rep.get("input_tokens") or 0
                total_tokens += in_tokens

                res_tier_probs = cached_rep.get("tier_probabilities") or {}
                cached_flags = cached_rep.get("flags") or {}
                flag_report = {}
                for fid, exp_val in expected_flags.items():
                    cf = cached_flags.get(fid) if isinstance(cached_flags.get(fid), dict) else {}
                    flag_report[fid] = {
                        "expected": exp_val,
                        "predicted": cf.get("predicted"),
                        "probability": cf.get("probability"),
                    }
                for fid, cf in cached_flags.items():
                    if fid not in flag_report and isinstance(cf, dict):
                        flag_report[fid] = {
                            "expected": expected_flags.get(fid),
                            "predicted": cf.get("predicted"),
                            "probability": cf.get("probability"),
                        }
                res_flags = {fid: d.get("predicted") for fid, d in flag_report.items() if isinstance(d, dict)}
                pred_confidence = cached_rep.get("tier_confidence") or 0.0
                res_reg_score = cached_rep.get("technicality_score") or 0.0
            else:
                cached_petri_cost = sum(r.get("cost_usd", 0.0) or 0.0 for r in scoped_cached_petri)
                active_cost = total_actual_cost + cached_petri_cost
                if not is_mock and max_spend is not None and active_cost > max_spend:
                    if checkpoint_path:
                        save_checkpoint(checkpoint_path, case_reports, cached_petri, metadata=checkpoint_metadata)
                    part_m = build_advice_metrics(
                        len(case_reports), has_ground_truth, exact_matches, within_one, gold_tiers,
                        prob_vectors, tier_order, flag_stats, confusion, total_actual_cost, total_est_cost,
                        total_tokens, served_models_set, unbilled_calls
                    )
                    if scoped_cached_petri:
                        update_metrics_with_petri(part_m, scoped_cached_petri)
                    raise EvaluationInterruptedError(
                        f"Live spend ${active_cost:.6f} exceeded max_spend ceiling ${max_spend:.6f}",
                        exit_code=6,
                        metrics=part_m,
                        case_reports=case_reports,
                        petri_results=scoped_cached_petri if scoped_cached_petri else None,
                    )

                res = classifier.classify(text, model=model_name)
                pred_tier = res.tier
                served_model = res.raw_response.model or model_name
                served_models_set.add(served_model)

                if is_mock:
                    actual_cost = 0.0
                else:
                    if res.cost_usd is None:
                        actual_cost = None
                        unbilled_calls += 1
                    else:
                        actual_cost = res.cost_usd
                        total_actual_cost += actual_cost
                est_cost = res.estimated_cost_usd or 0.0
                total_est_cost += est_cost
                in_tokens = res.input_tokens
                total_tokens += in_tokens
                res_tier_probs = res.tier_probabilities
                res_flags = res.flags
                pred_confidence = res.tier_confidence
                res_reg_score = res.register_score

                flag_report = {}
                for fid, exp_val in expected_flags.items():
                    if fid not in res.flags:
                        raise ValueError(
                            f"Classifier response missing expected flag {fid!r} present in reference judgment"
                        )
                    got_val = res.flags[fid]
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

                prob_vectors.append(res_tier_probs)
                gold_tiers.append(expected_tier)

            for fid, exp_val in expected_flags.items():
                got_val = res_flags.get(fid)
                stats = flag_stats.setdefault(fid, {"tp": 0, "tn": 0, "fp": 0, "fn": 0})
                if exp_val and got_val:
                    stats["tp"] += 1
                elif not exp_val and not got_val:
                    stats["tn"] += 1
                elif not exp_val and got_val:
                    stats["fp"] += 1
                else:
                    stats["fn"] += 1

            case_reports.append({
                "id": c.get("id"),
                "response_text": text,
                "expected_tier": expected_tier,
                "primary_judge_tier": c.get("primary_judge_tier"),
                "predicted_tier": pred_tier,
                "tier_confidence": pred_confidence,
                "is_exact": is_exact if has_ground_truth else None,
                "is_within_one": is_within_one if has_ground_truth else None,
                "tier_probabilities": res_tier_probs,
                "flags": flag_report,
                "technicality_score": res_reg_score,
                "served_model": served_model,
                "input_tokens": in_tokens,
                "cost_usd": actual_cost,
                "estimated_cost_usd": est_cost,
            })

            if checkpoint_path and (count % checkpoint_interval == 0 or count == len(cases)):
                save_checkpoint(checkpoint_path, case_reports, cached_petri, metadata=checkpoint_metadata)

    except EvaluationInterruptedError:
        raise
    except Exception as exc:
        if checkpoint_path and case_reports:
            save_checkpoint(checkpoint_path, case_reports, cached_petri, metadata=checkpoint_metadata)
        part_m = build_advice_metrics(
            len(case_reports), has_ground_truth, exact_matches, within_one, gold_tiers,
            prob_vectors, tier_order, flag_stats, confusion, total_actual_cost, total_est_cost,
            total_tokens, served_models_set, unbilled_calls
        ) if case_reports else None
        if scoped_cached_petri and part_m:
            update_metrics_with_petri(part_m, scoped_cached_petri)
        raise EvaluationInterruptedError(
            f"Classifier error during advice evaluation: {exc}",
            exit_code=1,
            metrics=part_m,
            case_reports=case_reports,
            petri_results=scoped_cached_petri if scoped_cached_petri else None,
        ) from exc

    metrics = build_advice_metrics(
        len(cases), has_ground_truth, exact_matches, within_one, gold_tiers,
        prob_vectors, tier_order, flag_stats, confusion, total_actual_cost, total_est_cost,
        total_tokens, served_models_set, unbilled_calls
    )
    return metrics, case_reports


def evaluate_petri_classifier(
    transcripts_path: Path,
    classifier: PetriRegisterClassifier,
    max_conversations: int = 5,
    model_name: str = "typesafe/jev-1.13",
    is_mock: bool = True,
    checkpoint_path: Path | None = None,
    cached_petri: list[dict[str, Any]] | None = None,
    prior_advice_cases: list[dict[str, Any]] | None = None,
    prior_metrics: EvaluationMetrics | None = None,
    checkpoint_metadata: dict[str, Any] | None = None,
    max_spend: float | None = None,
    checkpoint_interval: int = 25,
) -> list[dict[str, Any]]:
    """Evaluate PetriRegisterClassifier on multi-turn conversation transcripts."""
    if max_conversations < 0:
        raise ValueError(f"max_conversations must be non-negative (got {max_conversations}; use 0 for all)")
    results: list[dict[str, Any]] = []
    conversations_count = 0
    cached_turn_map = {(p["conversation_id"], p["turn_index"]): p for p in (cached_petri or [])}
    current_cost = prior_metrics.total_cost_usd if prior_metrics else 0.0

    try:
        with open(transcripts_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                conv_id = str(rec.get("conversation_id", "conv"))
                turns = rec.get("turns", [])
                has_assistant_turn = False
                for i, t in enumerate(turns):
                    if t.get("role") == "assistant":
                        has_assistant_turn = True
                        if (conv_id, i) in cached_turn_map:
                            results.append(cached_turn_map[(conv_id, i)])
                            continue

                        if not is_mock and max_spend is not None:
                            active_cost = current_cost + sum(r["cost_usd"] for r in results if r["cost_usd"] is not None)
                            if active_cost > max_spend:
                                if checkpoint_path:
                                    save_checkpoint(checkpoint_path, prior_advice_cases or [], results, metadata=checkpoint_metadata)
                                if prior_metrics:
                                    update_metrics_with_petri(prior_metrics, results)
                                raise EvaluationInterruptedError(
                                    f"Live spend ${active_cost:.6f} exceeded max_spend ceiling ${max_spend:.6f}",
                                    exit_code=6,
                                    metrics=prior_metrics,
                                    case_reports=prior_advice_cases,
                                    petri_results=results,
                                )

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
                        if checkpoint_path and len(results) % checkpoint_interval == 0:
                            save_checkpoint(checkpoint_path, prior_advice_cases or [], results, metadata=checkpoint_metadata)

                if has_assistant_turn:
                    conversations_count += 1
                    if max_conversations > 0 and conversations_count >= max_conversations:
                        break

        if checkpoint_path:
            save_checkpoint(checkpoint_path, prior_advice_cases or [], results, metadata=checkpoint_metadata)

    except EvaluationInterruptedError:
        raise
    except Exception as exc:
        if checkpoint_path:
            save_checkpoint(checkpoint_path, prior_advice_cases or [], results, metadata=checkpoint_metadata)
        if prior_metrics:
            update_metrics_with_petri(prior_metrics, results)
        raise EvaluationInterruptedError(
            f"Classifier error during Petri evaluation: {exc}",
            exit_code=1,
            metrics=prior_metrics,
            case_reports=prior_advice_cases,
            petri_results=results,
        ) from exc

    return results


def format_markdown_report(
    metrics: EvaluationMetrics,
    case_reports: list[dict[str, Any]],
    model_name: str,
    is_mock: bool = True,
    petri_results: list[dict[str, Any]] | None = None,
    judge_model: str = "claude-haiku-4-5",
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

    judge_label = judge_model.split("/")[-1] if "/" in judge_model else judge_model
    lines.extend([
        "## Advice Evaluation Predictions",
        "",
        f"| Case ID | Primary Judge ({judge_label}) | Pred Tier (Jev) | Conf | Match? | Tech Score |",
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
    allow_unmatched: bool = False,
    judge_model: str = "claude-haiku-4-5",
) -> tuple[list[dict[str, Any]], int]:
    """Sample real responses from an existing advice responses archive (responses_*.jsonl)
    paired with primary judge judgments by response_sha256 if judgments_*.jsonl exists.

    Filters judgments to the specified primary `judge_model` (default: "claude-haiku-4-5")
    so secondary re-judge rows cannot overwrite the primary reference.

    Returns:
        tuple of (cases, unmatched_count)
    """
    if max_samples < 0:
        raise ValueError(f"max_samples must be non-negative (got {max_samples}; use 0 for all)")

    haiku_judgments: dict[str, dict[str, Any]] = {}
    total_raw_judgments = 0
    if judgments_path and judgments_path.is_file():
        with open(judgments_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_raw_judgments += 1
                rec = json.loads(line)
                jm = rec.get("judge_model")
                if judge_model and jm != judge_model:
                    continue
                rsha = rec.get("response_sha256")
                if rsha and rec.get("tier"):
                    if rsha not in haiku_judgments:
                        haiku_judgments[rsha] = {
                            "tier": rec["tier"],
                            "flags": rec.get("flags") or {},
                            "model": rec.get("model"),
                            "judge_model": jm,
                        }

        if not haiku_judgments:
            raise ValueError(
                f"No usable judgments found in {judgments_path} matching judge model {judge_model!r} "
                f"({total_raw_judgments} rows examined; refusing empty judge set)."
            )

    with open(archive_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    ok, msg = verify_chain(rows)
    if not ok:
        raise ValueError(f"Broken hash chain in response archive {archive_path}: {msg}")

    cases = []
    unmatched_count = 0
    for rec in rows:
        if rec.get("record_type") == "advice" and rec.get("response_text"):
            sid = rec.get("stimulus_id")
            arm = rec.get("arm")
            k = rec.get("sample_k")
            model_req = rec.get("model_requested") or rec.get("model") or "unknown"
            rsha = rec.get("response_sha256")

            pj_tier = None
            pj_flags = {}
            if haiku_judgments:
                if rsha and rsha in haiku_judgments:
                    pj_data = haiku_judgments[rsha]
                    pj_tier = pj_data.get("tier")
                    pj_flags = pj_data.get("flags") or {}
                else:
                    unmatched_count += 1
                    if not allow_unmatched:
                        continue
            case_id = f"{sid}_{arm}_{k}_{model_req}"
            if rsha:
                case_id = f"{case_id}_{rsha[:8]}"
            cases.append({
                "id": case_id,
                "response_text": rec["response_text"],
                "response_sha256": rsha,
                "model_requested": model_req,
                "expected_tier": pj_tier,
                "primary_judge_tier": pj_tier,
                "expected_flags": pj_flags,
            })
            if max_samples > 0 and len(cases) >= max_samples:
                break

    if haiku_judgments and not cases:
        raise ValueError(
            f"No advice responses matched judgments in {judgments_path} by response_sha256 "
            f"({unmatched_count} unmatched responses found)."
        )

    if unmatched_count > 0 and haiku_judgments:
        print(
            f"Paired {len(cases)} responses with judgments by response_sha256 "
            f"({unmatched_count} unjudged responses omitted).",
            file=sys.stderr,
        )

    return cases, unmatched_count


def build_mock_client_for_cases(cases: list[dict[str, Any]], tier_order: list[str]) -> JevClient:
    """Mock client returning realistic, normalized decisions for offline testing."""
    case_map = {c.get("response_text") or c.get("text", ""): c for c in cases}

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


def write_reports(
    out_markdown: str | None,
    out_json: str | None,
    metrics: EvaluationMetrics,
    case_reports: list[dict[str, Any]],
    model_name: str,
    is_mock: bool,
    prov: dict[str, Any],
    petri_results: list[dict[str, Any]] | None = None,
    interrupted_reason: str | None = None,
    judge_model: str = "claude-haiku-4-5",
) -> None:
    """Format and write human-readable markdown and structured JSON reports."""
    md_report = format_markdown_report(
        metrics,
        case_reports,
        model_name=model_name,
        is_mock=is_mock,
        petri_results=petri_results,
        judge_model=judge_model,
    )
    if interrupted_reason:
        md_report = (
            f"> [!WARNING]\n"
            f"> **Evaluation Interrupted**: {interrupted_reason}\n"
            f"> Intermediate progress was saved to checkpoint; report reflects cases evaluated prior to interruption.\n\n"
            + md_report
        )

    if out_markdown:
        out_p = Path(out_markdown)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md_report, encoding="utf-8")
        print(f"Saved Markdown report -> {out_p}")
    else:
        print("\n" + md_report + "\n")

    if out_json:
        out_json_p = Path(out_json)
        out_json_p.parent.mkdir(parents=True, exist_ok=True)
        prov_copy = copy.deepcopy(prov)
        prov_copy["models_served"] = metrics.served_models
        if "advice_archive" in prov_copy:
            prov_copy["advice_archive"]["samples_evaluated"] = len(case_reports)
        if "golden_benchmark" in prov_copy:
            prov_copy["golden_benchmark"]["cases_evaluated"] = len(case_reports)
        if interrupted_reason:
            prov_copy["interrupted"] = {
                "reason": interrupted_reason,
                "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        if petri_results is not None and "petri_transcripts" in prov_copy:
            prov_copy["petri_transcripts"]["turns_evaluated"] = len(petri_results)

        payload = {
            "metadata": prov_copy,
            "metrics": asdict(metrics),
            "cases": case_reports,
            "petri_cases": petri_results or [],
        }
        out_json_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved JSON report -> {out_json_p}")


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
    parser.add_argument("--judge-model", default="claude-haiku-4-5", help="Primary judge model to filter judgments by")
    parser.add_argument("--max-spend", type=float, default=0.25, help="Hard spend ceiling in USD")
    parser.add_argument("--ci-live", action="store_true", help="Gated CI run mode using live OPENROUTER_API_KEY in GitHub Actions")
    parser.add_argument("--skip-advice", action="store_true",
                        help="Score the Petri transcripts only: no advice archive and no golden benchmark, so the "
                             "report's advice cases are empty. For runs whose advice phase another report already "
                             "covers (scripts/export_jev_calibration.py combines several reports). Needs "
                             "--petri-transcripts; refuses --archive and --judgments.")
    parser.add_argument("--checkpoint", help="Path to checkpoint JSON file to resume from and save intermediate state to")
    parser.add_argument("--out-markdown", help="Path to save markdown report")
    parser.add_argument("--out-json", help="Path to save structured JSON report")
    args = parser.parse_args(argv)

    if args.skip_advice and (args.archive or args.judgments):
        print("Refused: --skip-advice scores no advice responses; drop --archive and --judgments.", file=sys.stderr)
        return 1
    if args.skip_advice and not args.petri_transcripts:
        print("Refused: --skip-advice needs --petri-transcripts; a report with neither phase has nothing in it.",
              file=sys.stderr)
        return 1

    if args.archive_samples < 0:
        print(f"Refused: --archive-samples must be non-negative (got {args.archive_samples}; use 0 for all).", file=sys.stderr)
        return 1

    if args.petri_conversations < 0:
        print(f"Refused: --petri-conversations must be non-negative (got {args.petri_conversations}; use 0 for all).", file=sys.stderr)
        return 1

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
    rubric_sha = hashlib.sha256(rubric_path.read_bytes()).hexdigest()

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
    unmatched_count = 0

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
            cases, unmatched_count = load_advice_archive_with_judgments(
                arch_p,
                judgments_path=judg_p,
                max_samples=args.archive_samples,
                judge_model=args.judge_model,
            )
        except ValueError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1

        input_source_desc = f"Archive {args.archive} ({len(cases)} sampled responses, paired with {args.judge_model} judgments: {judg_p is not None})"
        input_sha = hashlib.sha256(arch_p.read_bytes()).hexdigest()
    elif args.skip_advice:
        cases = []
        input_source_desc = "no advice phase (--skip-advice)"
        input_sha = None
    else:
        golden_path = Path(args.golden)
        if not golden_path.is_file():
            print(f"Refused: Golden benchmark file not found: {golden_path}", file=sys.stderr)
            return 1
        golden_doc = json.loads(golden_path.read_text(encoding="utf-8"))
        cases = golden_doc.get("cases", [])
        input_source_desc = f"Golden benchmark {args.golden} ({len(cases)} cases)"
        input_sha = hashlib.sha256(golden_path.read_bytes()).hexdigest()

    if not cases and not args.skip_advice:
        print(f"Refused: No test cases found in input {input_source_desc}.", file=sys.stderr)
        return 1

    petri_sha: str | None = None
    if args.petri_transcripts:
        petri_p = Path(args.petri_transcripts)
        if not petri_p.is_file():
            print(f"Refused: Petri transcripts file not found: {petri_p}", file=sys.stderr)
            return 1
        petri_sha = hashlib.sha256(petri_p.read_bytes()).hexdigest()

    clf_file = Path(__file__).parent / "jev_classifier.py"
    client_file = Path(__file__).parent.parent / "medlang_circuits" / "jev_client.py"
    eval_file = Path(__file__)
    clf_hasher = hashlib.sha256()
    if clf_file.is_file():
        clf_hasher.update(clf_file.read_bytes())
    if client_file.is_file():
        clf_hasher.update(client_file.read_bytes())
    if eval_file.is_file():
        clf_hasher.update(eval_file.read_bytes())
    classifier_sha = clf_hasher.hexdigest()

    judgments_sha = hashlib.sha256(judg_p.read_bytes()).hexdigest() if (arch_p and judg_p and judg_p.is_file()) else None
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

    judge_model_meta = args.judge_model if (arch_p and judg_p) else None

    checkpoint_metadata = {
        "model": args.model,
        "is_mock": not is_live,
        "rubric_sha256": rubric_sha,
        "register_rubric_sha256": reg_rubric_sha,
        "input_sha256": input_sha,
        "input_type": "archive" if arch_p else "golden",
        "judgments_sha256": judgments_sha,
        "judge_model": judge_model_meta,
        "petri_transcripts_sha256": petri_sha,
        "classifier_sha256": classifier_sha,
    }

    # Checkpoint configuration
    checkpoint_path: Path | None = Path(args.checkpoint) if args.checkpoint else None
    cached_advice: list[dict[str, Any]] = []
    cached_petri: list[dict[str, Any]] = []
    if checkpoint_path and checkpoint_path.is_file():
        try:
            cp_data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Refused: Failed to parse checkpoint {checkpoint_path}: {exc}", file=sys.stderr)
            return 1

        cached_advice = cp_data.get("advice_cases") or []
        cached_petri = cp_data.get("petri_cases") or []
        cp_meta = cp_data.get("metadata") or {}

        if cached_advice or cached_petri:
            if not cp_meta:
                print(f"Refused: Checkpoint {checkpoint_path} lacks metadata validation fields.", file=sys.stderr)
                return 1
            if cp_meta.get("is_mock") is None:
                print(
                    f"Refused: Checkpoint {checkpoint_path} lacks is_mock metadata validation field.",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("is_mock") != (not is_live):
                print(
                    f"Refused: Checkpoint execution mode mismatch: checkpoint is_mock={cp_meta.get('is_mock')} != current is_mock={not is_live}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("model") != args.model:
                print(
                    f"Refused: Checkpoint model mismatch: {cp_meta.get('model')} != {args.model}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("rubric_sha256") != rubric_sha:
                print(
                    f"Refused: Checkpoint rubric mismatch: {cp_meta.get('rubric_sha256')} != {rubric_sha}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("input_sha256") != input_sha:
                print(
                    f"Refused: Checkpoint input mismatch: {cp_meta.get('input_sha256')} != {input_sha}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("register_rubric_sha256") != reg_rubric_sha:
                print(
                    f"Refused: Checkpoint register rubric mismatch: {cp_meta.get('register_rubric_sha256')} != {reg_rubric_sha}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("judgments_sha256") != judgments_sha:
                print(
                    f"Refused: Checkpoint judgments mismatch: {cp_meta.get('judgments_sha256')} != {judgments_sha}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("judge_model") != judge_model_meta:
                print(
                    f"Refused: Checkpoint judge model mismatch: {cp_meta.get('judge_model')} != {judge_model_meta}",
                    file=sys.stderr,
                )
                return 1
            if cp_meta.get("classifier_sha256") != classifier_sha:
                print(
                    f"Refused: Checkpoint classifier implementation mismatch: {cp_meta.get('classifier_sha256')} != {classifier_sha}",
                    file=sys.stderr,
                )
                return 1
            if cached_petri:
                if not petri_p:
                    print(
                        "Refused: Checkpoint contains cached Petri rows but --petri-transcripts was not provided.",
                        file=sys.stderr,
                    )
                    return 1
                if cp_meta.get("petri_transcripts_sha256") != petri_sha:
                    print(
                        f"Refused: Checkpoint Petri transcripts mismatch: {cp_meta.get('petri_transcripts_sha256')} != {petri_sha}",
                        file=sys.stderr,
                    )
                    return 1

        print(
            f"Resuming from checkpoint {checkpoint_path}: "
            f"{len(cached_advice)} advice cases, {len(cached_petri)} petri turns cached.",
            file=sys.stderr,
        )

    prov: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_requested": args.model,
        "models_served": [],
        "is_mock": not is_live,
        "rubric": {
            "path": str(args.rubric),
            "sha256": rubric_sha,
        },
        "register_rubric": {
            "path": str(reg_rubric_path),
            "sha256": reg_rubric_sha,
        },
        "classifier": {
            "path": str(clf_file),
            "jev_client_path": str(client_file),
            "evaluator_path": str(eval_file),
            "sha256": classifier_sha,
        },
        "parameters": {
            "archive_samples": (args.archive_samples if args.archive_samples > 0 else "all") if arch_p else None,
            "petri_conversations": (args.petri_conversations if args.petri_conversations > 0 else "all") if petri_p else None,
            "max_spend": args.max_spend,
        },
    }
    if arch_p:
        prov["advice_archive"] = {
            "path": str(arch_p),
            "sha256": input_sha,
            "samples_requested": len(cases),
            "samples_evaluated": len(cases),
            "unmatched_responses_omitted": unmatched_count,
        }
        if judg_p and judg_p.is_file():
            prov["advice_judgments"] = {
                "path": str(judg_p),
                "sha256": hashlib.sha256(judg_p.read_bytes()).hexdigest(),
                "judge_model": args.judge_model,
            }
    elif golden_path:
        prov["golden_benchmark"] = {
            "path": str(golden_path),
            "sha256": input_sha,
            "cases_requested": len(cases),
            "cases_evaluated": len(cases),
        }
    if petri_p:
        prov["petri_transcripts"] = {
            "path": str(petri_p),
            "sha256": hashlib.sha256(petri_p.read_bytes()).hexdigest(),
            "max_conversations": args.petri_conversations if args.petri_conversations > 0 else "all",
            "turns_evaluated": 0,
        }
    if checkpoint_path:
        prov["checkpoint"] = {
            "path": str(checkpoint_path),
            "resumed_advice_count": len(cached_advice),
            "resumed_petri_count": len(cached_petri),
        }

    classifier = AdviceAnswerClassifier(rubric=rubric_doc, client=client)
    interrupted_exc: EvaluationInterruptedError | None = None
    metrics: EvaluationMetrics | None = None
    case_reports: list[dict[str, Any]] = []
    petri_results: list[dict[str, Any]] | None = None

    try:
        max_petri_convs = args.petri_conversations if (petri_p and args.petri_conversations > 0) else (None if petri_p else 0)
        metrics, case_reports = evaluate_advice_classifier(
            cases=cases,
            classifier=classifier,
            tier_order=tier_order,
            model_name=args.model,
            is_mock=not is_live,
            checkpoint_path=checkpoint_path,
            cached_cases=cached_advice,
            cached_petri=cached_petri,
            checkpoint_metadata=checkpoint_metadata,
            max_spend=args.max_spend if is_live else None,
            max_petri_conversations=max_petri_convs,
        )

        if petri_p:
            petri_clf = PetriRegisterClassifier(client=client)
            petri_results = evaluate_petri_classifier(
                transcripts_path=petri_p,
                classifier=petri_clf,
                max_conversations=args.petri_conversations,
                model_name=args.model,
                is_mock=not is_live,
                checkpoint_path=checkpoint_path,
                cached_petri=cached_petri,
                prior_advice_cases=case_reports,
                prior_metrics=metrics,
                checkpoint_metadata=checkpoint_metadata,
                max_spend=args.max_spend if is_live else None,
            )
            if not petri_results:
                print(f"Refused: No evaluable assistant turns found in Petri transcripts {petri_p}.", file=sys.stderr)
                return 1
            update_metrics_with_petri(metrics, petri_results)

    except EvaluationInterruptedError as exc:
        interrupted_exc = exc
        metrics = exc.metrics
        case_reports = exc.case_reports or []
        petri_results = exc.petri_results

    if is_live and metrics and metrics.total_cost_usd > args.max_spend and not interrupted_exc:
        interrupted_exc = EvaluationInterruptedError(
            f"Total spend ${metrics.total_cost_usd:.6f} exceeded max_spend ceiling ${args.max_spend:.6f}",
            exit_code=6,
            metrics=metrics,
            case_reports=case_reports,
            petri_results=petri_results,
        )

    # a --skip-advice run has no advice rows, so its report is written when it has Petri rows
    if metrics and (case_reports or petri_results):
        write_reports(
            out_markdown=args.out_markdown,
            out_json=args.out_json,
            metrics=metrics,
            case_reports=case_reports,
            model_name=args.model,
            is_mock=not is_live,
            prov=prov,
            petri_results=petri_results,
            interrupted_reason=str(interrupted_exc) if interrupted_exc else None,
            judge_model=args.judge_model,
        )

    if interrupted_exc:
        print(f"Refused: {interrupted_exc}", file=sys.stderr)
        return interrupted_exc.exit_code

    return 0


if __name__ == "__main__":
    sys.exit(main())
