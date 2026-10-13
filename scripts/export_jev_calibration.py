"""Export Jev calibration and multi-turn register drift data into the site payload.

Reads the Jev audit report (default: artifacts/jev_pilot_report.json), verifies
mathematical consistency of calibration metrics, and emits two sanitized JSON
payloads into the frontend repository (<site>/data/):

1. `data/jev_calibration.json`:
   - Tier AGREEMENT between Jev and the primary judge (the advice lane's judge of
     record). The primary judge's tier is a reference label, not ground truth, so
     every rate here is inter-rater agreement, never accuracy (2026-10-13 review).
   - Exact and within-1 agreement, Cohen's kappa (unweighted and quadratic-weighted),
     the Brier score against the primary judge's tier, the base-rate Brier and the
     Brier skill score.
   - `headline_metrics.tier_divergence`: agreement per primary-judge tier with Wilson
     95% intervals, the tier with the lowest agreement, the direction of
     disagreements, and every shift of two or more tiers.
   - 4x4 tier confusion matrix (rows: primary judge; columns: Jev) and tier order.
   - Binary flag performance metrics (safety netting, clarifying questions, referrals).
   - Per-case probabilities, confidences, and technicality scores.
   - Cost and input token efficiency disclosures.

2. `data/petri_register_drift.json`:
   - Multi-turn register drift summary (total conversations, assistant turns, drift rate).
   - Drift rate by assistant turn (ranked within each conversation), with each turn's n and
     a Wilson 95% interval; exploratory.
   - Per-conversation tone choices, drift flags, probabilities, and formality scores.

Methods (all deterministic; no sampling, so no seed):
- Tiers are ordinal in the order the report (or data/advice_rubric*.json) lists them;
  the quadratic weights and "tiers apart" use that order.
- Cohen's kappa: (p_o - p_e) / (1 - p_e), p_e from the row and column marginals.
  Quadratic-weighted kappa: 1 - sum(w*O) / sum(w*E), w_ij = (i - j)^2 / (k - 1)^2,
  E_ij = row_i * col_j / n. Null when its denominator is zero.
- The Brier score is the report's: per case, the sum over tiers of the squared gap
  between Jev's probability and the one-hot primary-judge tier (range 0-2), averaged
  over cases. The base-rate Brier scores a forecaster that always states the primary
  judge's tier frequencies, computed from the confusion matrix's row totals (so it is
  in-sample, which flatters the reference slightly). Skill = 1 - brier / base-rate.
- Wilson score intervals at z = 1.96. Per-turn Petri intervals treat each turn's
  conversations as a binomial sample; the same conversations contribute to every turn,
  so the intervals are per-turn marginals, not a test of trend across turns.

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
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _refuse(reason: str) -> None:
    print(f"Refused: {reason} (site files left untouched)", file=sys.stderr)
    sys.exit(2)


Z95 = 1.959963984540054


def _load_tier_order_from_data(repo_root: Path = REPO_ROOT) -> list[str]:
    """Load canonical tier order from JSON data file, never hardcoded in source.

    The first rubric file that exists is the one used: one that cannot be read, or
    that lists no tier ids, refuses the export rather than falling through to the
    next file, which could carry a different vocabulary."""
    for rubric_name in ("advice_rubric.json", "advice_rubric.draft.json"):
        p = repo_root / "data" / rubric_name
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _refuse(f"Tier vocabulary file {p} could not be read as JSON ({exc})")
        tiers_raw = doc.get("tiers") if isinstance(doc, dict) else None
        if not isinstance(tiers_raw, list):
            _refuse(f"Tier vocabulary file {p} has no 'tiers' list")
        tiers = [str(t["id"]) for t in tiers_raw if isinstance(t, dict) and "id" in t]
        if not tiers or len(tiers) != len(tiers_raw):
            _refuse(f"Tier vocabulary file {p} lists {len(tiers_raw)} tier(s) but {len(tiers)} carry an 'id'")
        return tiers
    _refuse("Could not load tier order vocabulary from data/advice_rubric.json or draft")
    return []


def _round_or_none(val: Any, field: str, digits: int = 4) -> float | None:
    """Round a report metric. None stays None: the audit writes null for a metric it
    could not compute (an unjudged archive). Anything else that is not a finite
    number (a string, a bool, NaN, an infinity) is malformed input and refuses the
    export, naming the field, rather than being published as null."""
    if val is None:
        return None
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        _refuse(f"Metric '{field}' must be a number or null, got {type(val).__name__} {val!r}")
    if not math.isfinite(val):
        _refuse(f"Metric '{field}' must be finite, got {val!r}")
    return round(float(val), digits)


def _wilson(successes: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion; (None, None) when n is 0."""
    if n <= 0:
        return None, None
    ph = successes / n
    denom = 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / denom
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def _validate_matrix(matrix: Any, tier_order: list[str]) -> list[list[int]]:
    """A k x k matrix of non-negative integers, k = len(tier_order); refuses anything else."""
    k = len(tier_order)
    if not isinstance(matrix, list) or len(matrix) != k:
        _refuse(f"Confusion matrix must have {k} rows (one per tier), got {matrix!r:.80}")
    for i, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != k:
            _refuse(f"Confusion matrix row {i} must have {k} cells")
        for j, cell in enumerate(row):
            if isinstance(cell, bool) or not isinstance(cell, int) or cell < 0:
                _refuse(f"Confusion matrix cell [{i}][{j}] must be a non-negative integer, got {cell!r}")
    return matrix


def agreement_statistics(matrix: list[list[int]], tier_order: list[str], brier: float | None) -> dict[str, Any]:
    """Chance-corrected agreement, the base-rate Brier and the tier divergence, from the confusion matrix
    (rows: primary judge; columns: Jev). Definitions are in the module docstring."""
    k = len(tier_order)
    n = sum(sum(row) for row in matrix)
    rows = [sum(matrix[i]) for i in range(k)]
    cols = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    out: dict[str, Any] = {"cohen_kappa": None, "cohen_kappa_quadratic": None, "base_rate_brier": None,
                           "brier_skill_score": None, "majority_tier": None, "tier_divergence": None}
    if n == 0:
        return out
    p_o = sum(matrix[i][i] for i in range(k)) / n
    p_e = sum(rows[i] * cols[i] for i in range(k)) / (n * n)
    out["cohen_kappa"] = round((p_o - p_e) / (1 - p_e), 4) if p_e < 1 else None
    if k > 1:
        w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
        observed = sum(w[i][j] * matrix[i][j] for i in range(k) for j in range(k)) / n
        expected = sum(w[i][j] * rows[i] * cols[j] for i in range(k) for j in range(k)) / (n * n)
        out["cohen_kappa_quadratic"] = round(1 - observed / expected, 4) if expected > 0 else None
    base = [r / n for r in rows]
    sum_sq = sum(b * b for b in base)
    base_rate_brier = sum(rows[t] * (sum_sq - 2 * base[t] + 1) for t in range(k)) / n
    out["base_rate_brier"] = round(base_rate_brier, 4)
    if brier is not None and base_rate_brier > 0:
        out["brier_skill_score"] = round(1 - brier / base_rate_brier, 4)
    top = max(range(k), key=lambda i: rows[i])
    out["majority_tier"] = {"tier": tier_order[top], "share": round(rows[top] / n, 4)}

    per_tier = []
    for i, tier in enumerate(tier_order):
        lo, hi = _wilson(matrix[i][i], rows[i])
        others = [(matrix[i][j], j) for j in range(k) if j != i and matrix[i][j] > 0]
        top_other = max(others, key=lambda c: (c[0], -c[1])) if others else None
        per_tier.append({
            "primary_judge_tier": tier, "n": rows[i], "agreed": matrix[i][i],
            "agreement": round(matrix[i][i] / rows[i], 4) if rows[i] else None,
            "ci95_low": lo, "ci95_high": hi,
            "most_common_jev_tier_otherwise": (
                {"jev_tier": tier_order[top_other[1]], "count": top_other[0],
                 "share_of_primary_judge_tier": round(top_other[0] / rows[i], 4)} if top_other else None),
        })
    judged = [t for t in per_tier if t["agreement"] is not None]
    lowest = min(judged, key=lambda t: t["agreement"]) if judged else None
    distant = sorted(
        ({"primary_judge_tier": tier_order[i], "jev_tier": tier_order[j], "tiers_apart": abs(i - j),
          "count": matrix[i][j], "share_of_primary_judge_tier": round(matrix[i][j] / rows[i], 4)}
         for i in range(k) for j in range(k) if abs(i - j) >= 2 and matrix[i][j] > 0),
        key=lambda c: (-c["count"], tier_order.index(c["primary_judge_tier"]), tier_order.index(c["jev_tier"])))
    out["tier_divergence"] = {
        "per_primary_judge_tier": per_tier,
        "lowest_agreement_tier": lowest["primary_judge_tier"] if lowest else None,
        "jev_higher_tier_count": sum(matrix[i][j] for i in range(k) for j in range(k) if j > i),
        "jev_lower_tier_count": sum(matrix[i][j] for i in range(k) for j in range(k) if j < i),
        "shifts_two_or_more_tiers": distant,
    }
    return out


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

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        _refuse(f"Report metadata must be a JSON object (got {type(meta).__name__})")
    if meta.get("interrupted"):
        _refuse("Report is marked as interrupted (partial audit); refusing to export partial calibration results.")

    return data, report_sha


def _require_is_mock(meta: dict[str, Any]) -> bool:
    """Execution provenance must be a JSON boolean; a number or string would be coerced into an invented answer."""
    if "is_mock" not in meta or not isinstance(meta["is_mock"], bool):
        _refuse(f"Report metadata 'is_mock' must be true or false, got {meta.get('is_mock')!r}; "
                "refusing to infer execution provenance")
    return meta["is_mock"]


def _agreement_reference(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    """(reference, judge_model). An advice-archive report graded by the advice lane's judge of record is
    agreement with that primary judge; an advice-archive report without judgments has no reference (its
    agreement metrics must all be null). Any other report (the runner's golden-benchmark default, or one
    whose provenance is unrecognised) is refused: its labels are not a primary judge's, and this payload
    describes only that comparison."""
    has_archive = isinstance(meta.get("advice_archive"), dict)
    if "golden_benchmark" in meta and (has_archive or "advice_judgments" in meta):
        _refuse("Report metadata names both a golden benchmark and an advice archive or judgments; the audit runner "
                "writes one or the other, so the reference is ambiguous")
    judgments = meta.get("advice_judgments")
    if judgments is not None and not (isinstance(judgments, dict) and has_archive):
        _refuse("Report metadata has advice_judgments without an advice_archive (or judgments that are not an "
                "object); the runner writes judgments only beside the archive they grade")
    if isinstance(judgments, dict):
        judge_model = judgments.get("judge_model")
        if not isinstance(judge_model, str) or not judge_model:
            _refuse("Report metadata advice_judgments has no judge_model; cannot name the primary judge")
        return "primary_judge", judge_model
    if isinstance(meta.get("advice_archive"), dict):
        return None, None
    kind = "a golden-benchmark" if "golden_benchmark" in meta else "an unrecognised"
    _refuse(f"Report is {kind} report (no advice_archive or advice_judgments provenance); this exporter "
            "publishes Jev's agreement with the advice lane's primary judge only")
    return None, None


def _require_relative_path(path: Any) -> None:
    """The audit runner stores its input paths verbatim; an absolute or parent-escaping path would publish the
    machine's directory layout (a username, a runner workspace), so it is refused rather than rewritten."""
    if not isinstance(path, str) or not path:
        _refuse(f"Provenance path must be a non-empty string, got {path!r}")
    posix, win = PurePosixPath(path), PureWindowsPath(path)
    if posix.is_absolute() or win.is_absolute() or win.drive or ".." in posix.parts or ".." in win.parts:
        _refuse(f"Provenance path {path!r} is not repository-relative; re-run the audit with repository-relative "
                "inputs before publishing")


def _served_models(rows: list[dict[str, Any]], what: str) -> list[str]:
    """The models that produced these rows, from the rows themselves: the report's metadata list folds the advice
    and Petri phases together, so it would attribute one phase's routed models to the other's results."""
    served: set[str] = set()
    for idx, row in enumerate(rows):
        model = row.get("served_model") if isinstance(row, dict) else None
        if not isinstance(model, str) or not model:
            _refuse(f"{what} at index {idx} has no served_model; cannot name the model that produced it")
        served.add(model)
    return sorted(served)


def _publishable_provenance(meta: dict[str, Any]) -> dict[str, Any]:
    """The report's input and classifier provenance, so the public payload alone names what produced it.
    Hashes, repository-relative paths and parameters only; absent fields are carried as null, never dropped.
    The classifier's local file paths are runner paths and are not carried; its digest is."""
    def pick(block: Any, keys: tuple[str, ...]) -> dict[str, Any] | None:
        if not isinstance(block, dict):
            return None
        out = {k: block.get(k) for k in keys}
        if out.get("path") is not None:
            _require_relative_path(out["path"])
        return out

    return {
        "audit_timestamp_utc": meta.get("timestamp_utc"),
        "rubric": pick(meta.get("rubric"), ("path", "sha256")),
        "register_rubric": pick(meta.get("register_rubric"), ("path", "sha256")),
        "classifier_sha256": (meta.get("classifier") or {}).get("sha256") if isinstance(meta.get("classifier"), dict)
        else None,
        "parameters": meta.get("parameters") if isinstance(meta.get("parameters"), dict) else None,
        "advice_archive": pick(meta.get("advice_archive"), ("path", "sha256", "samples_requested",
                                                             "samples_evaluated", "unmatched_responses_omitted")),
        "advice_judgments": pick(meta.get("advice_judgments"), ("path", "sha256", "judge_model")),
        "petri_transcripts": pick(meta.get("petri_transcripts"), ("path", "sha256", "max_conversations",
                                                                   "turns_evaluated")),
        "checkpoint": pick(meta.get("checkpoint"), ("resumed_advice_count", "resumed_petri_count")),
    }


def build_calibration_payload(
    report_data: dict[str, Any],
    report_sha: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Build the jev_calibration.json payload with safety checks."""
    meta = report_data.get("metadata", {})
    metrics = report_data.get("metrics", {})
    cases = report_data.get("cases", [])

    is_mock = _require_is_mock(meta)
    reference, judge_model = _agreement_reference(meta)

    total_cases = metrics.get("total_cases", len(cases))
    exact_matches = metrics.get("exact_tier_matches")
    matrix = metrics.get("confusion_matrix") or []
    tier_order = metrics.get("tier_order")
    if not tier_order or not isinstance(tier_order, list):
        tier_order = _load_tier_order_from_data(repo_root)
    if matrix:
        _validate_matrix(matrix, tier_order)

    # Mathematical consistency checks
    if matrix:
        matrix_sum = sum(sum(row) for row in matrix)
        if matrix_sum != total_cases:
            _refuse(f"Confusion matrix sum ({matrix_sum}) does not match total cases ({total_cases})")
        if exact_matches is not None:
            diag_sum = sum(matrix[i][i] for i in range(min(len(matrix), len(tier_order))))
            if diag_sum != exact_matches:
                _refuse(f"Confusion matrix diagonal sum ({diag_sum}) does not match exact matches ({exact_matches})")
        # the matrix determines both published rates; a stale or corrupted rate is refused, not copied
        k = len(tier_order)
        n = matrix_sum
        band = sum(matrix[i][j] for i in range(k) for j in range(k) if abs(i - j) <= 1)
        within_matches = metrics.get("within_one_tier_matches")
        if within_matches is not None and within_matches != band:
            _refuse(f"Confusion matrix within-one band ({band}) does not match within_one_tier_matches "
                    f"({within_matches})")
        for field, count in (("exact_accuracy", sum(matrix[i][i] for i in range(k))), ("within_one_accuracy", band)):
            reported = metrics.get(field)
            if reported is not None and n and abs(_round_or_none(reported, field, 6) - count / n) > 5.1e-5:
                _refuse(f"Reported {field} {reported} does not match the confusion matrix ({count}/{n})")
    else:
        for field in ("exact_accuracy", "within_one_accuracy", "brier_score", "exact_tier_matches",
                      "within_one_tier_matches"):
            if metrics.get(field) is not None:
                _refuse(f"Report gives {field} but no confusion matrix to check it against")
    if reference is None and matrix:
        _refuse("Report has agreement metrics but no advice_judgments provenance naming the reference")

    cases_summary: dict[str, Any] = {}
    for idx, c in enumerate(cases):
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not cid:
            _refuse(f"Case at index {idx} has no identifier; every case must appear in cases_summary")
        if cid in cases_summary:
            _refuse(f"Case identifier {cid!r} appears more than once")
        primary_judge_tier = c.get("primary_judge_tier") or c.get("expected_tier")
        cases_summary[cid] = {
            "primary_judge_tier": primary_judge_tier,
            "pred_tier": c.get("predicted_tier"),
            "tier_confidence": c.get("tier_confidence"),
            "tier_probabilities": c.get("tier_probabilities") or {},
            "technicality_score": c.get("technicality_score"),
            "is_exact": c.get("is_exact"),
            "is_within_one": c.get("is_within_one"),
            "flags": c.get("flags") or {},
        }

    total_cost_rounded = _round_or_none(metrics.get("total_cost_usd"), "total_cost_usd", 6)
    est_cost_rounded = _round_or_none(metrics.get("total_estimated_cost_usd"), "total_estimated_cost_usd", 6)
    brier = _round_or_none(metrics.get("brier_score"), "brier_score", 4)
    agreement = agreement_statistics(matrix, tier_order, brier) if matrix else agreement_statistics([], [], None)
    unbilled_calls = int(metrics.get("unbilled_calls_count", 0) or 0)

    cost_caveat = None
    if unbilled_calls > 0:
        known_str = f"${total_cost_rounded:.6f}" if total_cost_rounded is not None else "$0.000000"
        est_str = f"${est_cost_rounded:.6f}" if est_cost_rounded is not None else "unknown"
        cost_caveat = (
            f"Total known spend {known_str} excludes {unbilled_calls} calls with null provider billing; "
            f"the estimated list-price spend across all calls, billed or not, is {est_str}"
        )

    raw_flags = metrics.get("flag_metrics") or {}
    if not isinstance(raw_flags, dict):
        _refuse(f"flag_metrics must be an object, got {type(raw_flags).__name__}")
    flag_metrics: dict[str, Any] = {}
    for flag, stats in raw_flags.items():
        if not isinstance(stats, dict):
            _refuse(f"flag_metrics[{flag!r}] must be an object")
        # the flag reference values are the same primary judge's, so the match rate is agreement too; precision,
        # sensitivity and specificity keep their names and are read against flag_metrics_reference
        flag_metrics[flag] = {("agreement" if key == "accuracy" else key): val for key, val in stats.items()}

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_report_sha256": report_sha,
        "model_requested": meta.get("model_requested"),
        "models_served": _served_models(cases, "Advice case"),
        "judge_model": judge_model,
        "agreement_reference": reference,
        "is_mock": is_mock,
        "headline_metrics": {
            "total_advice_cases": total_cases,
            "exact_matches": exact_matches,
            "exact_agreement": _round_or_none(metrics.get("exact_accuracy"), "exact_accuracy", 4),
            "within_one_matches": metrics.get("within_one_tier_matches"),
            "within_one_agreement": _round_or_none(metrics.get("within_one_accuracy"), "within_one_accuracy", 4),
            "cohen_kappa": agreement["cohen_kappa"],
            "cohen_kappa_quadratic": agreement["cohen_kappa_quadratic"],
            "majority_tier": agreement["majority_tier"],
            "brier_score": brier,
            "base_rate_brier": agreement["base_rate_brier"],
            "brier_skill_score": agreement["brier_skill_score"],
            "tier_divergence": agreement["tier_divergence"],
            "total_cost_usd": total_cost_rounded,
            "total_estimated_cost_usd": est_cost_rounded,
            "unbilled_calls_count": unbilled_calls,
            "cost_caveat": cost_caveat,
            "total_input_tokens": metrics.get("total_input_tokens", 0),
        },
        "tier_order": tier_order,
        "confusion_matrix": matrix,
        "flag_metrics_reference": reference,
        "flag_metrics": flag_metrics,
        "provenance": _publishable_provenance(meta),
        "cases_summary": cases_summary,
    }


def build_petri_drift_payload(report_data: dict[str, Any], report_sha: str) -> dict[str, Any] | None:
    """Build the petri_register_drift.json payload from multi-turn Petri records."""
    # the audit runner always writes petri_cases (an empty list when it ran no Petri conversations), so a missing
    # or non-list field is a malformed report, not an empty dataset: refused, so it cannot delete a published file
    if "petri_cases" not in report_data or not isinstance(report_data["petri_cases"], list):
        _refuse("Report has no 'petri_cases' list; refusing rather than treating a malformed report as empty")
    petri_cases = report_data["petri_cases"]
    if not petri_cases:
        return None

    meta = report_data.get("metadata", {})
    is_mock = _require_is_mock(meta)
    seen: set[tuple[str, int]] = set()
    tones: dict[str, int] = {}
    drifts = 0
    scores: list[float] = []
    conversations: dict[str, list[dict[str, Any]]] = {}

    for idx, p in enumerate(petri_cases):
        cid = p.get("conversation_id")
        if not cid:
            _refuse(f"Petri case at index {idx} missing required 'conversation_id'")
        if "turn_index" not in p or p["turn_index"] is None:
            _refuse(f"Petri case {cid} missing required 'turn_index'")
        t_idx = int(p["turn_index"])
        if (cid, t_idx) in seen:
            _refuse(f"Petri conversation {cid} has more than one row for turn {t_idx}; the sampling unit is one "
                    "row per conversation per turn")
        seen.add((cid, t_idx))

        t_choice = p.get("tone_choice")
        if not t_choice:
            _refuse(f"Petri case {cid} turn {t_idx} missing required 'tone_choice'")
        tones[t_choice] = tones.get(t_choice, 0) + 1

        if "has_register_drift" not in p or p["has_register_drift"] is None:
            _refuse(f"Petri case {cid} turn {t_idx} missing required 'has_register_drift'")
        has_drift = bool(p["has_register_drift"])
        if has_drift:
            drifts += 1

        reg_score = p.get("register_score")
        if reg_score is not None:
            scores.append(float(reg_score))

        conversations.setdefault(cid, []).append({
            "turn_index": t_idx,
            "tone_choice": t_choice,
            "tone_confidence": p.get("tone_confidence"),
            "has_register_drift": has_drift,
            "drift_probability": p.get("drift_probability"),
            "formality_score": reg_score,
        })

    # turn_index is the row's raw position in its own transcript (tool and other records included), so the same
    # assistant position can carry different indices in different conversations. Rows are therefore ranked within
    # each conversation, and the per-turn series is aggregated by that per-conversation assistant ordinal.
    by_ordinal: dict[int, list[int]] = {}
    indices_at: dict[int, set[int]] = {}
    for cid in conversations:
        conversations[cid].sort(key=lambda t: t["turn_index"])
        for ordinal, row in enumerate(conversations[cid], 1):
            row["assistant_turn_ordinal"] = ordinal
            counts = by_ordinal.setdefault(ordinal, [0, 0])
            counts[1] += 1
            counts[0] += int(row["has_register_drift"])
            indices_at.setdefault(ordinal, set()).add(row["turn_index"])

    drift_by_turn: list[dict[str, Any]] = []
    for ordinal in sorted(by_ordinal):
        d_cnt, tot_cnt = by_ordinal[ordinal]
        lo, hi = _wilson(d_cnt, tot_cnt)
        drift_by_turn.append({
            "assistant_turn_ordinal": ordinal,
            "turn_indices": sorted(indices_at[ordinal]),
            "n": tot_cnt,
            "assistant_turns": tot_cnt,
            "drift_turns": d_cnt,
            "drift_rate": round(d_cnt / tot_cnt, 4),
            "ci95_low": lo,
            "ci95_high": hi,
        })

    total_turns = len(petri_cases)
    overall_drift_rate = round(drifts / total_turns, 4) if total_turns > 0 else 0.0
    mean_formality = round(sum(scores) / len(scores), 2) if scores else None

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_report_sha256": report_sha,
        "model_requested": meta.get("model_requested"),
        "models_served": _served_models(petri_cases, "Petri case"),
        "is_mock": is_mock,
        "provenance": {k: v for k, v in _publishable_provenance(meta).items()
                       if k in ("audit_timestamp_utc", "register_rubric", "classifier_sha256", "parameters",
                                "petri_transcripts", "checkpoint")},
        "status": "exploratory",
        "per_turn_interval": "wilson_95; per-turn marginal, not a test of trend (the same conversations recur)",
        "headline_metrics": {
            "total_conversations": len(conversations),
            "total_assistant_turns": total_turns,
            "overall_drift_count": drifts,
            "overall_drift_rate": overall_drift_rate,
            "mean_formality_score": mean_formality,
            "tone_distribution": tones,
            "min_turn_n": min(t["n"] for t in drift_by_turn),
            "max_turn_n": max(t["n"] for t in drift_by_turn),
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

    out_calib = Path(args.out_calibration) if args.out_calibration else site_path / "data" / "jev_calibration.json"
    out_petri = Path(args.out_petri_drift) if args.out_petri_drift else site_path / "data" / "petri_register_drift.json"
    if out_calib.resolve() == out_petri.resolve():
        _refuse(f"--out-calibration and --out-petri-drift resolve to the same file ({out_calib.resolve()})")
    for name, out in (("--out-calibration", out_calib), ("--out-petri-drift", out_petri)):
        if out.resolve() == report_path.resolve():
            _refuse(f"{name} resolves to the source report ({report_path.resolve()}); it would be overwritten "
                    "or deleted")

    report_data, report_sha = load_report(report_path)

    calib_payload = build_calibration_payload(report_data, report_sha)
    petri_payload = build_petri_drift_payload(report_data, report_sha)

    print("=== Jev Site Export Summary ===")
    print(f"Source report: {report_path} (sha256: {report_sha[:12]}...)")
    print(f"Advice cases: {calib_payload['headline_metrics']['total_advice_cases']}")
    head = calib_payload["headline_metrics"]

    def fmt(v: float | None, pct: bool = False) -> str:
        if v is None:
            return "N/A (unjudged)"
        return f"{v*100:.2f}%" if pct else f"{v:.4f}"

    print(f"Exact agreement with primary judge: {fmt(head['exact_agreement'], pct=True)}")
    print(f"Within-1 agreement: {fmt(head['within_one_agreement'], pct=True)}")
    print(f"Cohen's kappa: {fmt(head['cohen_kappa'])} (quadratic-weighted {fmt(head['cohen_kappa_quadratic'])})")
    print(f"Brier score: {fmt(head['brier_score'])} vs base rate {fmt(head['base_rate_brier'])} "
          f"(skill {fmt(head['brier_skill_score'])})")
    div = head["tier_divergence"]
    if div:
        for t in div["per_primary_judge_tier"]:
            other = t["most_common_jev_tier_otherwise"]
            print(f"  primary judge {t['primary_judge_tier']}: n={t['n']} agreement {fmt(t['agreement'], pct=True)}"
                  + (f"; most often otherwise Jev {other['jev_tier']} ({other['count']})" if other else ""))
        for c in div["shifts_two_or_more_tiers"]:
            print(f"  shift {c['primary_judge_tier']} -> {c['jev_tier']} ({c['tiers_apart']} tiers): {c['count']}")

    if petri_payload:
        p_head = petri_payload["headline_metrics"]
        print(f"Petri conversations: {p_head['total_conversations']} ({p_head['total_assistant_turns']} turns)")
        print(f"Overall drift rate: {p_head['overall_drift_rate']*100:.1f}%")
        print(f"Mean formality score: {p_head['mean_formality_score']}")

    if args.dry_run:
        if not petri_payload and out_petri.is_file():
            print(f"\n[Dry Run] Validated payloads successfully; stale Petri file {out_petri} would be removed.")
        else:
            print("\n[Dry Run] Validated payloads successfully; disk writes skipped.")
        return 0

    if not out_calib.parent.is_dir():
        _refuse(f"Site data directory does not exist: {out_calib.parent}")

    write_json_atomic(out_calib, calib_payload)
    print(f"\nWrote calibration payload -> {out_calib}")

    if petri_payload:
        write_json_atomic(out_petri, petri_payload)
        print(f"Wrote Petri drift payload -> {out_petri}")
    else:
        if out_petri.is_file():
            out_petri.unlink()
            print(f"Removed stale Petri drift payload -> {out_petri}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

