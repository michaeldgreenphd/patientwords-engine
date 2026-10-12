"""Export Jev calibration and multi-turn register drift data into the site payload.

Reads the Jev audit report (default: artifacts/jev_pilot_report.json), verifies
mathematical consistency of calibration metrics, and emits two sanitized JSON
payloads into the frontend repository (<site>/data/):

1. `data/jev_calibration.json`:
   - Dual-judge tier concordance (exact accuracy, within-1 accuracy, Brier score).
   - 4x4 tier confusion matrix and tier order.
   - Binary flag performance metrics (safety netting, clarifying questions, referrals).
   - Per-case probabilities, confidences, and technicality scores.
   - Cost and input token efficiency disclosures.

2. `data/petri_register_drift.json`:
   - Multi-turn register drift summary (total conversations, assistant turns, drift rate).
   - Turn-by-turn longitudinal drift progression trajectory.
   - Per-conversation tone choices, drift flags, probabilities, and formality scores.

Safety properties (matching other site exporters):
- Refuses (exit 2, site files untouched) when report is missing, invalid, or inconsistent.
- Strips all raw patient and response text to prevent any holdout phrase leakage.
- Validates that confusion matrix trace equals exact matches and cell sum equals total cases.
- Supports `--dry-run` to validate without writing to disk.

Usage:
  python scripts/export_jev_calibration.py \\
      [--report artifacts/jev_pilot_report.json] \\
      [--site ../patientwords] \\
      [--dry-run]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _refuse(reason: str) -> None:
    print(f"Refused: {reason} (site files left untouched)", file=sys.stderr)
    sys.exit(2)


def load_report(report_path: Path) -> tuple[dict[str, Any], str]:
    """Load and validate the Jev evaluation report JSON."""
    if not report_path.is_file():
        _refuse(f"Report file not found: {report_path}")

    raw_bytes = report_path.read_bytes()
    report_sha = hashlib.sha256(raw_bytes).hexdigest()

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        _refuse(f"Failed to parse report JSON {report_path}: {exc}")

    if not isinstance(data, dict):
        _refuse(f"Report root must be a JSON object (got {type(data).__name__})")

    for key in ("metadata", "metrics", "cases"):
        if key not in data:
            _refuse(f"Report missing required top-level key: '{key}'")

    return data, report_sha


def build_calibration_payload(report_data: dict[str, Any], report_sha: str) -> dict[str, Any]:
    """Build the jev_calibration.json payload with safety checks."""
    meta = report_data.get("metadata", {})
    metrics = report_data.get("metrics", {})
    cases = report_data.get("cases", [])

    total_cases = metrics.get("total_cases", len(cases))
    exact_matches = metrics.get("exact_tier_matches", 0)
    matrix = metrics.get("confusion_matrix") or []
    tier_order = metrics.get("tier_order") or ["self_care", "routine", "urgent", "emergency"]

    # Mathematical consistency checks
    if matrix:
        matrix_sum = sum(sum(row) for row in matrix)
        if matrix_sum != total_cases:
            _refuse(f"Confusion matrix sum ({matrix_sum}) does not match total cases ({total_cases})")
        diag_sum = sum(matrix[i][i] for i in range(min(len(matrix), len(tier_order))))
        if diag_sum != exact_matches:
            _refuse(f"Confusion matrix diagonal sum ({diag_sum}) does not match exact matches ({exact_matches})")

    cases_summary: dict[str, Any] = {}
    for c in cases:
        cid = c.get("id")
        if not cid:
            continue
        gold_tier = c.get("primary_judge_tier") or c.get("expected_tier")
        cases_summary[cid] = {
            "gold_tier": gold_tier,
            "pred_tier": c.get("predicted_tier"),
            "tier_confidence": c.get("tier_confidence"),
            "tier_probabilities": c.get("tier_probabilities") or {},
            "technicality_score": c.get("technicality_score"),
            "is_exact": c.get("is_exact"),
            "is_within_one": c.get("is_within_one"),
            "flags": c.get("flags") or {},
        }

    advice_judgments = meta.get("advice_judgments") or {}
    judge_model = advice_judgments.get("judge_model")

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_report_sha256": report_sha,
        "model_requested": meta.get("model_requested"),
        "models_served": meta.get("models_served") or [],
        "judge_model": judge_model,
        "is_mock": meta.get("is_mock", False),
        "headline_metrics": {
            "total_advice_cases": total_cases,
            "exact_matches": exact_matches,
            "exact_accuracy": round(metrics.get("exact_accuracy", 0.0), 4),
            "within_one_matches": metrics.get("within_one_tier_matches", 0),
            "within_one_accuracy": round(metrics.get("within_one_accuracy", 0.0), 4),
            "brier_score": round(metrics.get("brier_score", 0.0), 4),
            "total_cost_usd": round(metrics.get("total_cost_usd", 0.0), 6),
            "total_input_tokens": metrics.get("total_input_tokens", 0),
        },
        "tier_order": tier_order,
        "confusion_matrix": matrix,
        "flag_metrics": metrics.get("flag_metrics") or {},
        "cases_summary": cases_summary,
    }


def build_petri_drift_payload(report_data: dict[str, Any], report_sha: str) -> dict[str, Any] | None:
    """Build the petri_register_drift.json payload from multi-turn Petri records."""
    petri_cases = report_data.get("petri_cases") or []
    if not petri_cases:
        return None

    meta = report_data.get("metadata", {})
    tones: dict[str, int] = {}
    drifts = 0
    scores: list[float] = []
    conversations: dict[str, list[dict[str, Any]]] = {}
    turn_drifts: dict[int, list[int]] = {}

    for p in petri_cases:
        cid = p.get("conversation_id", "conv")
        t_idx = p.get("turn_index", 0)
        t_choice = p.get("tone_choice", "mixed")
        tones[t_choice] = tones.get(t_choice, 0) + 1

        has_drift = bool(p.get("has_register_drift"))
        if has_drift:
            drifts += 1

        reg_score = p.get("register_score")
        if reg_score is not None:
            scores.append(float(reg_score))

        turn_drifts.setdefault(t_idx, [0, 0])
        turn_drifts[t_idx][1] += 1
        if has_drift:
            turn_drifts[t_idx][0] += 1

        conversations.setdefault(cid, []).append({
            "turn_index": t_idx,
            "tone_choice": t_choice,
            "tone_confidence": p.get("tone_confidence"),
            "has_register_drift": has_drift,
            "drift_probability": p.get("drift_probability"),
            "formality_score": reg_score,
        })

    # Sort turns within each conversation by turn_index
    for cid in conversations:
        conversations[cid].sort(key=lambda t: t["turn_index"])

    drift_by_turn: list[dict[str, Any]] = []
    for t_idx in sorted(turn_drifts.keys()):
        d_cnt, tot_cnt = turn_drifts[t_idx]
        drift_by_turn.append({
            "turn_index": t_idx,
            "assistant_turns": tot_cnt,
            "drift_turns": d_cnt,
            "drift_rate": round(d_cnt / tot_cnt, 4) if tot_cnt > 0 else 0.0,
        })

    total_turns = len(petri_cases)
    overall_drift_rate = round(drifts / total_turns, 4) if total_turns > 0 else 0.0
    mean_formality = round(sum(scores) / len(scores), 2) if scores else None

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_report_sha256": report_sha,
        "model_requested": meta.get("model_requested"),
        "models_served": meta.get("models_served") or [],
        "headline_metrics": {
            "total_conversations": len(conversations),
            "total_assistant_turns": total_turns,
            "overall_drift_count": drifts,
            "overall_drift_rate": overall_drift_rate,
            "mean_formality_score": mean_formality,
            "tone_distribution": tones,
        },
        "drift_by_turn": drift_by_turn,
        "conversations": conversations,
    }


def write_json_atomic(target_path: Path, doc: dict[str, Any]) -> None:
    """Write JSON document atomically via a temporary file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f"{target_path.name}.tmp")
    tmp_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp_path.replace(target_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--report",
        default="artifacts/jev_pilot_report.json",
        help="Path to Jev audit report JSON (default: artifacts/jev_pilot_report.json)",
    )
    parser.add_argument(
        "--site",
        default="../patientwords",
        help="Path to patientwords frontend repository checkout (default: ../patientwords)",
    )
    parser.add_argument(
        "--out-calibration",
        help="Explicit path for jev_calibration.json output (defaults to <site>/data/jev_calibration.json)",
    )
    parser.add_argument(
        "--out-petri-drift",
        help="Explicit path for petri_register_drift.json output (defaults to <site>/data/petri_register_drift.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and calculate payloads without writing to disk",
    )
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    site_path = Path(args.site)

    report_data, report_sha = load_report(report_path)

    calib_payload = build_calibration_payload(report_data, report_sha)
    petri_payload = build_petri_drift_payload(report_data, report_sha)

    out_calib = Path(args.out_calibration) if args.out_calibration else site_path / "data" / "jev_calibration.json"
    out_petri = Path(args.out_petri_drift) if args.out_petri_drift else site_path / "data" / "petri_register_drift.json"

    print("=== Jev Site Export Summary ===")
    print(f"Source report: {report_path} (sha256: {report_sha[:12]}...)")
    print(f"Advice cases: {calib_payload['headline_metrics']['total_advice_cases']}")
    print(f"Exact accuracy: {calib_payload['headline_metrics']['exact_accuracy']*100:.2f}%")
    print(f"Within-1 accuracy: {calib_payload['headline_metrics']['within_one_accuracy']*100:.2f}%")
    print(f"Brier score: {calib_payload['headline_metrics']['brier_score']:.4f}")

    if petri_payload:
        p_head = petri_payload["headline_metrics"]
        print(f"Petri conversations: {p_head['total_conversations']} ({p_head['total_assistant_turns']} turns)")
        print(f"Overall drift rate: {p_head['overall_drift_rate']*100:.1f}%")
        print(f"Mean formality score: {p_head['mean_formality_score']}")

    if args.dry_run:
        print("\n[Dry Run] Validated payloads successfully; disk writes skipped.")
        return 0

    if not out_calib.parent.is_dir():
        _refuse(f"Site data directory does not exist: {out_calib.parent}")

    write_json_atomic(out_calib, calib_payload)
    print(f"\nWrote calibration payload -> {out_calib}")

    if petri_payload:
        write_json_atomic(out_petri, petri_payload)
        print(f"Wrote Petri drift payload -> {out_petri}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

