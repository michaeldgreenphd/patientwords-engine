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
   - The advice phase's spend (billed, estimated, input tokens, unbilled calls), summed from its
     own rows; the Petri payload carries the Petri phase's. Their sum is checked against the
     report's combined totals.

2. `data/petri_register_drift.json`:
   - Multi-turn register drift summary (total conversations, assistant turns, drift rate).
   - Drift rate by assistant turn (ranked within each conversation), with each turn's n and
     a Wilson 95% interval; exploratory.
   - Per-conversation tone choices, drift flags, probabilities, and formality scores.

Methods (all deterministic; no sampling, so no seed):
- Tiers are ordinal in the order the report itself records (metrics.tier_order, required);
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

Several runs in one export (2026-10-14, owner decision D3): `--report` may be repeated. Exactly one report carries
advice cases and the calibration payload is that report's; the others are Petri-only reports
(`audit_jev_calibration.py --skip-advice`) over other Petri runs. All must be one instrument (requested model,
execution mode, classifier digest, both rubrics), no report or Petri run may appear twice, and a conversation in two
reports is refused (check_combinable, build_combined_petri_drift_payload). The Petri payload pools the conversations,
names each run in `provenance.petri_runs` and each conversation's `run`, and with several Petri runs carries
`provenance.petri_transcripts` as null. Both payloads list every report in `source_reports` and carry one
`source_report_sha256`: the report's digest for one report, and for several the sha256 of the sorted digests, one per
line (combined_report_sha256), which the site contract recomputes.

Safety properties (matching other site exporters):
- Refuses (exit 2, site files untouched) when report is missing, invalid, or inconsistent.
- Strips all raw patient and response text to prevent any holdout phrase leakage.
- Validates that confusion matrix trace equals exact matches and cell sum equals total cases.
- Supports `--dry-run` to validate without writing to disk.

Usage:
  python scripts/export_jev_calibration.py \\
      [--report artifacts/jev_pilot_report.json [--report petri_only_report.json ...]] \\
      [--site ../patientwords] \\
      [--dry-run]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import tempfile
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _refuse(reason: str) -> None:
    print(f"Refused: {reason} (site files left untouched)", file=sys.stderr)
    sys.exit(2)


Z95 = 1.959963984540054
PROBABILITY_SUM_TOLERANCE = 0.02 + 1e-9     # four tiers each rounded to 2 dp: at most 4 x 0.005 off


def _load_tier_order_from_data(repo_root: Path = REPO_ROOT) -> list[str]:
    """Load the repository's current tier vocabulary from its JSON data file, never hardcoded in source. The exporter
    does not use it in place of a report's own tier order (which may predate a rubric change); the tests read the
    vocabulary through it.

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
        tiers = [t["id"] for t in tiers_raw if isinstance(t, dict) and "id" in t]
        if not tiers or len(tiers) != len(tiers_raw):
            _refuse(f"Tier vocabulary file {p} lists {len(tiers_raw)} tier(s) but {len(tiers)} carry an 'id'")
        return _validate_tier_order(tiers, str(p))
    _refuse("Could not load tier order vocabulary from data/advice_rubric.json or draft")
    return []


def _validate_tier_order(tiers: Any, source: str) -> list[str]:
    """At least two unique, non-empty string tier ids: duplicates would route every occurrence through the first
    index and make the ordinal distances and per-tier rows ambiguous."""
    if (not isinstance(tiers, list) or len(tiers) < 2 or any(not isinstance(t, str) or not t for t in tiers)
            or len(set(tiers)) != len(tiers)):
        _refuse(f"Tier order from {source} must be at least two unique non-empty strings, got {tiers!r}")
    return tiers


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
    # chosen on the unrounded ratios: two tiers can round to the same four decimals
    judged = [i for i in range(k) if rows[i]]
    lowest = per_tier[min(judged, key=lambda i: matrix[i][i] / rows[i])] if judged else None
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
    if not isinstance(data["metrics"], dict):
        _refuse(f"Report metrics must be a JSON object (got {type(data['metrics']).__name__})")
    if not isinstance(data["cases"], list):
        _refuse(f"Report cases must be a JSON list (got {type(data['cases']).__name__})")
    # the runner adds this key only to reports it wrote after an interruption, so its presence refuses, whatever
    # its value
    if "interrupted" in meta:
        _refuse("Report is marked as interrupted (partial audit); refusing to export partial calibration results.")

    return data, report_sha


def _require_model_requested(meta: dict[str, Any]) -> str:
    """Both payloads publish the requested Jev model, and the site contract requires it as a string; a report without
    one is refused here rather than written and then rejected by site CI."""
    model = meta.get("model_requested")
    if not isinstance(model, str) or not model:
        _refuse(f"Report metadata 'model_requested' must be a non-empty string, got {model!r}")
    return model


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


def _require_count(val: Any, field: str) -> int:
    """A non-negative JSON integer (not a bool, not a float); anything else refuses."""
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        _refuse(f"'{field}' must be a non-negative integer, got {val!r}")
    return val


def _phase_spend(rows: list[dict[str, Any]], what: str) -> dict[str, Any]:
    """Spend of one audit phase, summed from its own rows. The report's metrics block folds the advice and Petri
    phases together (audit_jev_calibration.update_metrics_with_petri), so each payload publishes its own phase and
    the combined total is checked against the metrics block instead. A row with cost_usd null is an unbilled call."""
    billed, estimated, tokens, unbilled = 0.0, 0.0, 0, 0
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            _refuse(f"{what} at index {idx} is not an object")
        for key in ("cost_usd", "estimated_cost_usd", "input_tokens"):
            if key not in row:
                _refuse(f"{what} at index {idx} has no '{key}'; cannot account for its spend")
        if row["cost_usd"] is None:
            unbilled += 1
        else:
            cost = _round_or_none(row["cost_usd"], f"{what}[{idx}].cost_usd", 12)
            if cost < 0:
                _refuse(f"{what} at index {idx} has negative cost_usd {cost}; a provider cost cannot be negative")
            billed += cost
        est = _round_or_none(row["estimated_cost_usd"], f"{what}[{idx}].estimated_cost_usd", 12)
        if est is None or est < 0:
            _refuse(f"{what} at index {idx} has estimated_cost_usd {row['estimated_cost_usd']!r}; it must be a "
                    "non-negative number")
        estimated += est
        tokens += _require_count(row["input_tokens"], f"{what}[{idx}].input_tokens")
    caveat = None
    if unbilled:
        caveat = (f"Known spend ${billed:.6f} excludes {unbilled} calls with null provider billing; the estimated "
                  f"list-price spend across all {len(rows)} calls of this phase, billed or not, is ${estimated:.6f}")
    return {"calls": len(rows), "cost_usd": round(billed, 6), "estimated_cost_usd": round(estimated, 6),
            "input_tokens": tokens, "unbilled_calls_count": unbilled, "cost_caveat": caveat}


def _check_combined_spend(metrics: dict[str, Any], phases: list[dict[str, Any]]) -> None:
    """The metrics block's totals must equal the sum of the phases' rows (to the runner's 6-decimal rounding)."""
    for field, key, tol in (("total_cost_usd", "cost_usd", 2e-6), ("total_estimated_cost_usd", "estimated_cost_usd", 2e-6),
                            ("total_input_tokens", "input_tokens", 0), ("unbilled_calls_count", "unbilled_calls_count", 0)):
        if field not in metrics:
            _refuse(f"Report metrics have no '{field}'; cannot verify the audit's spend accounting")
        reported = metrics[field]
        if tol:
            reported = _round_or_none(reported, field, 6)
            if reported is None or reported < 0:
                _refuse(f"Report metrics '{field}' must be a non-negative number, got {metrics[field]!r}")
        else:
            reported = _require_count(reported, field)
        summed = sum(ph[key] for ph in phases)
        if abs(reported - summed) > tol:
            _refuse(f"Report metrics '{field}' ({reported}) does not equal the sum of its rows ({summed})")


def _reference_tier(case: dict[str, Any]) -> Any:
    return case.get("primary_judge_tier") or case.get("expected_tier")


def _check_cases_against_aggregates(cases: list[dict[str, Any]], matrix: list[list[int]], tier_order: list[str],
                                    brier: float | None) -> float | None:
    """Rebuild the confusion matrix and the Brier score from the case rows and refuse any mismatch, so the headline
    cannot contradict cases_summary. The Brier score follows the runner's definition (audit_jev_calibration.
    compute_brier_score): a tier absent from a case's probabilities counts as probability 0. Returns the Brier score
    to publish: the reported one when it agrees, the recomputed one when the report left it null (a judged sample
    determines it)."""
    k = len(tier_order)
    rebuilt = [[0] * k for _ in range(k)]
    sq_err = 0.0
    for idx, case in enumerate(cases):
        ref, pred = _reference_tier(case), case.get("predicted_tier")
        if ref not in tier_order or pred not in tier_order:
            _refuse(f"Case at index {idx} has reference tier {ref!r} and Jev tier {pred!r}; both must be in the tier "
                    "order for the confusion matrix to describe it")
        rebuilt[tier_order.index(ref)][tier_order.index(pred)] += 1
        probs = case.get("tier_probabilities")
        if not isinstance(probs, dict):
            _refuse(f"Case at index {idx} has no tier_probabilities object; cannot verify the Brier score")
        for t in tier_order:
            pv = _round_or_none(probs.get(t, 0.0), f"cases[{idx}].tier_probabilities.{t}", 12)
            sq_err += (pv - (1.0 if t == ref else 0.0)) ** 2
    if rebuilt != matrix:
        _refuse("The confusion matrix does not match the matrix rebuilt from the case rows")
    if not cases:
        return brier
    recomputed = sq_err / len(cases)
    if brier is not None and abs(recomputed - brier) > 5.1e-5:
        _refuse(f"Reported brier_score {brier} does not match the score recomputed from the case rows "
                f"({recomputed:.6f})")
    return brier if brier is not None else round(recomputed, 4)


def _recorded_rubric(meta: dict[str, Any], block: str, repo_root: Path) -> dict[str, Any]:
    """The rubric the report says the audit used, read from the repository and accepted only if its sha256 still
    equals the recorded one: the vocabularies below (flag ids, tone choices, score scale) are the audit's, and a
    rubric edited since then would validate the report against the wrong ones."""
    entry = meta.get(block)
    if not isinstance(entry, dict):
        _refuse(f"Report metadata has no '{block}' block; cannot read the rubric the audit used")
    _require_relative_path(entry.get("path"))
    recorded = _require_sha256(entry.get("sha256"), f"{block}.sha256")
    path = repo_root / entry["path"]
    if not path.is_file():
        _refuse(f"The {block} the audit used ({entry['path']}) is not in this checkout")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != recorded:
        _refuse(f"{entry['path']} has changed since the audit (sha256 differs from the recorded {recorded[:12]}...); "
                "refusing to validate the report against a different rubric")
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _refuse(f"{entry['path']} could not be read as JSON ({exc})")
    if not isinstance(doc, dict):
        _refuse(f"{entry['path']} is not a JSON object")
    return doc


def _rubric_flag_ids(rubric: dict[str, Any]) -> list[str]:
    flags = rubric.get("flags")
    ids = [f.get("id") for f in flags] if isinstance(flags, list) and all(isinstance(f, dict) for f in flags) else []
    if not ids or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        _refuse("The recorded advice rubric lists no valid flag ids")
    return ids


def _rubric_tier_ids(rubric: dict[str, Any]) -> list[str]:
    tiers = rubric.get("tiers")
    ids = [t.get("id") for t in tiers] if isinstance(tiers, list) and all(isinstance(t, dict) for t in tiers) else []
    return _validate_tier_order(ids, "the recorded advice rubric")


def _technicality_top(rubric: dict[str, Any]) -> float:
    """Top of the advice technicality scale in the recorded register rubric; the scale runs 0..len(criteria)-1."""
    block = rubric.get("technicality_score")
    criteria = block.get("criteria") if isinstance(block, dict) else None
    if not isinstance(criteria, list) or len(criteria) < 2:
        _refuse("The recorded register rubric has no technicality_score scale")
    return float(len(criteria) - 1)


def _register_vocabulary(rubric: dict[str, Any]) -> tuple[set[str], float]:
    """(tone choices, top of the severity scale) from the recorded register rubric; the scale runs 0..len-1."""
    register = rubric.get("petri_register")
    tone = register.get("tone") if isinstance(register, dict) else None
    severity = register.get("severity_score") if isinstance(register, dict) else None
    tones = tone.get("criteria") if isinstance(tone, dict) else None
    scale = severity.get("criteria") if isinstance(severity, dict) else None
    if not isinstance(tones, dict) or not tones or not isinstance(scale, list) or len(scale) < 2:
        _refuse("The recorded register rubric has no petri_register tone choices or severity scale")
    return set(tones), float(len(scale) - 1)


def _scaled(val: Any, top: float, field: str) -> float | None:
    """A finite number on the rubric's 0..top scale, or null."""
    out = _round_or_none(val, field, 6)
    if out is not None and not 0.0 <= out <= top:
        _refuse(f"'{field}' is {out}, outside the recorded rubric's 0-{top:g} scale")
    return out


def _unit_interval(val: Any, field: str) -> float:
    """A finite number in [0, 1]; anything else refuses."""
    out = _round_or_none(val, field, 12)
    if out is None or not 0.0 <= out <= 1.0:
        _refuse(f"'{field}' must be a number in [0, 1], got {val!r}")
    return out


def _published_flags(case: dict[str, Any], cid: str, flag_ids: list[str], judged: bool) -> dict[str, Any]:
    """Each flag rebuilt from an allowlist (expected, predicted, probability), never copied: an extra field such as
    an explanation could carry raw response text into the public payload. Every case must carry exactly the
    recorded rubric's flags, each with Jev's boolean prediction and its probability, related as the classifier
    derives them (predicted = probability >= 0.5, scripts/jev_classifier.py). A reference value (`expected`) is
    allowed only when the report names the judge that supplied it."""
    flags = case.get("flags")
    if not isinstance(flags, dict) or set(flags) != set(flag_ids):
        got = sorted(flags) if isinstance(flags, dict) else flags
        _refuse(f"Case {cid!r} has flags {got!r}; the recorded rubric's flags are {flag_ids!r}")
    out: dict[str, Any] = {}
    for fid in flag_ids:
        entry = flags[fid]
        if not isinstance(entry, dict):
            _refuse(f"Case {cid!r} flag {fid!r} must be an object")
        predicted = entry.get("predicted")
        prob = _unit_interval(entry.get("probability"), f"case {cid} flag {fid} probability")
        if not isinstance(predicted, bool) or predicted != (prob >= 0.5):
            _refuse(f"Case {cid!r} flag {fid!r} has predicted {predicted!r} with probability {prob}; the classifier "
                    "sets predicted = probability >= 0.5")
        if entry.get("expected") is not None and not judged:
            _refuse(f"Case {cid!r} flag {fid!r} carries a reference value but the report names no judge")
        out[fid] = {"expected": entry.get("expected"), "predicted": predicted, "probability": prob}
    return out


def _flag_metrics_from_cases(cases: list[dict[str, Any]], reported: Any) -> dict[str, Any]:
    """Rebuild each flag's TP/TN/FP/FN and derived rates from the case rows, as audit_jev_calibration.py computes
    them (a flag counts on a case when its reference value `expected` is present; a missing `predicted` counts as
    false), and refuse a report whose flag_metrics differ, so the payload cannot contradict cases_summary. The
    published values are the rebuilt ones. The reference values are the same primary judge's, so the match rate is
    published as agreement; precision, sensitivity and specificity are read against flag_metrics_reference."""
    if reported is None:
        reported = {}
    if not isinstance(reported, dict):
        _refuse(f"flag_metrics must be an object, got {type(reported).__name__}")
    counts: dict[str, dict[str, int]] = {}
    for idx, case in enumerate(cases):
        flags = case.get("flags")
        if flags is None:
            continue
        if not isinstance(flags, dict):
            _refuse(f"Case at index {idx} has flags that are not an object")
        for fid, entry in flags.items():
            if not isinstance(entry, dict):
                _refuse(f"Case at index {idx} flag {fid!r} must be an object with 'expected' and 'predicted'")
            expected, predicted = entry.get("expected"), entry.get("predicted")
            # Jev's prediction is published whether or not the judge gave this flag a reference value
            if not (predicted is None or isinstance(predicted, bool)):
                _refuse(f"Case at index {idx} flag {fid!r} has non-boolean predicted {predicted!r}")
            if expected is None:
                continue
            if not isinstance(expected, bool):
                _refuse(f"Case at index {idx} flag {fid!r} has non-boolean expected {expected!r} or predicted "
                        f"{predicted!r}")
            c = counts.setdefault(fid, {"tp": 0, "tn": 0, "fp": 0, "fn": 0})
            c["tp" if expected and predicted else "tn" if not expected and not predicted
              else "fp" if predicted else "fn"] += 1
    rebuilt: dict[str, Any] = {}
    for fid, c in counts.items():
        tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]
        rebuilt[fid] = {
            "accuracy": round((tp + tn) / max(1, tp + tn + fp + fn), 4),
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "sensitivity": round(tp / (tp + fn), 4) if tp + fn else None,
            "specificity": round(tn / (tn + fp), 4) if tn + fp else None,
            **c,
        }
    if rebuilt != reported:
        differing = sorted(f for f in set(rebuilt) | set(reported) if rebuilt.get(f) != reported.get(f))
        _refuse(f"flag_metrics do not match the counts rebuilt from the case rows (flags: {', '.join(differing)})")
    return {fid: {("agreement" if k == "accuracy" else k): v for k, v in stats.items()} for fid, stats in rebuilt.items()}


def _case_match_flags(case: dict[str, Any], idx: int, tier_order: list[str], judged: bool) -> dict[str, bool | None]:
    """is_exact and is_within_one, derived from the case's two tiers (already verified against the matrix) when the
    report is judged; a reported value that disagrees is refused. An unjudged report has neither, so both are null
    and a reported value is refused."""
    derived: dict[str, bool | None] = {"is_exact": None, "is_within_one": None}
    if judged:
        i, j = tier_order.index(_reference_tier(case)), tier_order.index(case["predicted_tier"])
        derived = {"is_exact": i == j, "is_within_one": abs(i - j) <= 1}
    for key, value in derived.items():
        reported = case.get(key)
        if reported is not None and reported is not value:
            _refuse(f"Case at index {idx} reports {key} {reported!r} but its tiers give {value!r}")
    return derived


def _check_provenance_counts(meta: dict[str, Any], cases: list[Any], petri_cases: list[Any]) -> None:
    """The runner sets advice_archive.samples_evaluated to the number of case rows and petri_transcripts.
    turns_evaluated to the number of Petri rows; a stale count would contradict the payload's own totals."""
    if petri_cases and not isinstance(meta.get("petri_transcripts"), dict):
        _refuse("Report has Petri rows but no metadata.petri_transcripts block; the published drift statistics could "
                "not name their transcript input")
    for block, key, rows in (("advice_archive", "samples_evaluated", cases),
                             ("petri_transcripts", "turns_evaluated", petri_cases)):
        if isinstance(meta.get(block), dict) and len(rows) != _require_count(meta[block].get(key), f"{block}.{key}"):
            _refuse(f"Report metadata {block}.{key} is {meta[block].get(key)!r} but the report holds {len(rows)} rows")


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


def _require_sha256(val: Any, field: str) -> str:
    if not isinstance(val, str) or len(val) != 64 or any(ch not in "0123456789abcdef" for ch in val):
        _refuse(f"Provenance '{field}' must be a lowercase hex sha256, got {val!r}")
    return val


def _publishable_provenance(meta: dict[str, Any], *, has_advice: bool, has_petri: bool) -> dict[str, Any]:
    """The report's input and classifier provenance, so the public payload alone names what produced it after the
    source report expires. The inputs that produced published numbers must be identified by repository-relative path
    and sha256: the tier rubric, the classifier, the advice archive (and its judgments when judged), and, when Petri
    rows exist, the transcripts and the register rubric; a block or field missing there refuses. Optional context
    (timestamp, parameters, checkpoint resumes, sample counts) is carried as null when absent. The classifier's
    local file paths are runner paths and are not carried; its digest is."""
    def pick(name: str, keys: tuple[str, ...], required: bool) -> dict[str, Any] | None:
        block = meta.get(name)
        if not isinstance(block, dict):
            if required:
                _refuse(f"Report metadata has no '{name}' block; the payload could not name that input")
            return None
        out = {k: block.get(k) for k in keys}
        _require_relative_path(out["path"])
        _require_sha256(out["sha256"], f"{name}.sha256")
        return out

    classifier = meta.get("classifier")
    if not isinstance(classifier, dict):
        _refuse("Report metadata has no 'classifier' block; the payload could not name the classifier")
    return {
        "audit_timestamp_utc": meta.get("timestamp_utc"),
        "rubric": pick("rubric", ("path", "sha256"), True),
        "register_rubric": pick("register_rubric", ("path", "sha256"), has_advice or has_petri),
        "classifier_sha256": _require_sha256(classifier.get("sha256"), "classifier.sha256"),
        "parameters": meta.get("parameters") if isinstance(meta.get("parameters"), dict) else None,
        "advice_archive": pick("advice_archive", ("path", "sha256", "samples_requested", "samples_evaluated",
                                                  "unmatched_responses_omitted"), has_advice),
        "advice_judgments": pick("advice_judgments", ("path", "sha256", "judge_model"), False),
        "petri_transcripts": pick("petri_transcripts", ("path", "sha256", "max_conversations", "turns_evaluated"),
                                  has_petri),
        "checkpoint": ({k: meta["checkpoint"].get(k) for k in ("resumed_advice_count", "resumed_petri_count")}
                       if isinstance(meta.get("checkpoint"), dict) else None),
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
    advice_rubric = _recorded_rubric(meta, "rubric", repo_root)
    flag_ids = _rubric_flag_ids(advice_rubric)
    # every advice case's technicality_score was scored on the register rubric's scale, so it is required here too
    technicality_top = _technicality_top(_recorded_rubric(meta, "register_rubric", repo_root))

    total_cases = _require_count(metrics.get("total_cases"), "total_cases")
    if total_cases == 0 or not cases:
        _refuse("Report has no advice cases; the audit runner refuses an empty input, and an empty export would "
                "replace the published payload")
    if total_cases != len(cases):
        _refuse(f"Report metrics give total_cases {total_cases} but the report holds {len(cases)} case rows")
    matrix = metrics.get("confusion_matrix")
    if reference is not None and cases and not matrix:
        _refuse("Report names a primary judge but has no confusion matrix; refusing to publish its reference labels "
                "with every agreement statistic null")
    matrix = matrix or []
    tier_order = metrics.get("tier_order")
    # the report must name the order that produced it: the repository's rubric may have changed since the audit
    if tier_order is None:
        _refuse("Report metrics have no tier_order; refusing to substitute the repository's current rubric, which "
                "may differ from the one the audit used")
    tier_order = _validate_tier_order(tier_order, "the report's metrics.tier_order")
    rubric_tiers = _rubric_tier_ids(advice_rubric)
    if tier_order != rubric_tiers:
        _refuse(f"The report's tier_order {tier_order} differs from the recorded advice rubric's {rubric_tiers}; the "
                "audit runner takes its order from that rubric")
    if matrix:
        _validate_matrix(matrix, tier_order)

    # Mathematical consistency checks
    if matrix:
        matrix_sum = sum(sum(row) for row in matrix)
        if matrix_sum != total_cases:
            _refuse(f"Confusion matrix sum ({matrix_sum}) does not match total cases ({total_cases})")
        # the matrix (verified against the case rows below) determines both counts and both rates: they are derived
        # from it and published, and a reported value that is present must be a count or rate that agrees
        k = len(tier_order)
        n = matrix_sum
        diag = sum(matrix[i][i] for i in range(k))
        band = sum(matrix[i][j] for i in range(k) for j in range(k) if abs(i - j) <= 1)
        for field, count in (("exact_tier_matches", diag), ("within_one_tier_matches", band)):
            reported = metrics.get(field)
            if reported is not None and _require_count(reported, field) != count:
                _refuse(f"Report gives {field} {reported} but the confusion matrix gives {count}")
        for field, count in (("exact_accuracy", diag), ("within_one_accuracy", band)):
            reported = metrics.get(field)
            if reported is not None and n and abs(_round_or_none(reported, field, 6) - count / n) > 5.1e-5:
                _refuse(f"Reported {field} {reported} does not match the confusion matrix ({count}/{n})")
        exact_matches, within_matches = diag, band
        exact_rate = round(diag / n, 4) if n else None
        within_rate = round(band / n, 4) if n else None
    else:
        for field in ("exact_accuracy", "within_one_accuracy", "brier_score", "exact_tier_matches",
                      "within_one_tier_matches"):
            if metrics.get(field) is not None:
                _refuse(f"Report gives {field} but no confusion matrix to check it against")
        exact_matches = within_matches = exact_rate = within_rate = None
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
        if reference is None and primary_judge_tier is not None:
            _refuse(f"Case {cid!r} carries a reference tier {primary_judge_tier!r} but the report names no judge; "
                    "unverified reference labels are not published")
        # Jev's own outputs are required on every case, judged or not: an unjudged report has no matrix to catch a
        # missing prediction, and an incomplete evaluation must not look complete
        if c.get("predicted_tier") not in tier_order:
            _refuse(f"Case {cid!r} has Jev tier {c.get('predicted_tier')!r}, which is not in the tier order")
        probs = c.get("tier_probabilities")
        if not isinstance(probs, dict) or not probs:
            _refuse(f"Case {cid!r} has no tier_probabilities object")
        for t, v in probs.items():
            pv = _round_or_none(v, f"case {cid} tier_probabilities.{t}", 12)
            if t not in tier_order or pv is None or not 0.0 <= pv <= 1.0:
                _refuse(f"Case {cid!r} has tier probability {t!r}: {v!r}; tiers must be in the tier order and "
                        "values probabilities in [0, 1]")
        # the classifier reports each tier to two decimals, so the four can sum to 1 +/- 0.02 by rounding alone
        if abs(sum(probs.values()) - 1.0) > PROBABILITY_SUM_TOLERANCE:
            _refuse(f"Case {cid!r} tier probabilities sum to {sum(probs.values())}, not 1 within "
                    f"{PROBABILITY_SUM_TOLERANCE}")
        cases_summary[cid] = {
            "primary_judge_tier": primary_judge_tier,
            "pred_tier": c.get("predicted_tier"),
            "tier_confidence": _unit_interval(c.get("tier_confidence"), f"case {cid} tier_confidence"),
            "tier_probabilities": probs,
            "technicality_score": _scaled(c.get("technicality_score"), technicality_top, f"case {cid} technicality_score"),
            **_case_match_flags(c, idx, tier_order, judged=bool(matrix)),
            "flags": _published_flags(c, cid, flag_ids, judged=reference is not None),
        }

    brier = _round_or_none(metrics.get("brier_score"), "brier_score", 4)
    if matrix:
        brier = _check_cases_against_aggregates(cases, matrix, tier_order, brier)
    agreement = agreement_statistics(matrix, tier_order, brier) if matrix else agreement_statistics([], [], None)

    advice_spend = _phase_spend(cases, "Advice case")
    petri_rows = report_data.get("petri_cases")
    if not isinstance(petri_rows, list):
        _refuse("Report has no 'petri_cases' list; cannot separate the advice phase's spend from the Petri phase's")
    _check_combined_spend(metrics, [advice_spend, _phase_spend(petri_rows, "Petri case")])
    _check_provenance_counts(meta, cases, petri_rows)

    flag_metrics = _flag_metrics_from_cases(cases, metrics.get("flag_metrics"))

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_report_sha256": report_sha,
        "model_requested": _require_model_requested(meta),
        "models_served": _served_models(cases, "Advice case"),
        "judge_model": judge_model,
        "agreement_reference": reference,
        "is_mock": is_mock,
        "headline_metrics": {
            "total_advice_cases": total_cases,
            "exact_matches": exact_matches,
            "exact_agreement": exact_rate,
            "within_one_matches": within_matches,
            "within_one_agreement": within_rate,
            "cohen_kappa": agreement["cohen_kappa"],
            "cohen_kappa_quadratic": agreement["cohen_kappa_quadratic"],
            "majority_tier": agreement["majority_tier"],
            "brier_score": brier,
            "base_rate_brier": agreement["base_rate_brier"],
            "brier_skill_score": agreement["brier_skill_score"],
            "tier_divergence": agreement["tier_divergence"],
            "advice_phase_spend": advice_spend,
        },
        "tier_order": tier_order,
        "confusion_matrix": matrix,
        "flag_metrics_reference": reference,
        "flag_metrics": flag_metrics,
        "provenance": _publishable_provenance(meta, has_advice=True, has_petri=bool(petri_rows)),
        "cases_summary": cases_summary,
    }


# Jev's drift question (data/register_rubric.json, petri_register.drift.instructions) asks whether the reply "drift[ed]
# into formal clinical jargon ... that substantially departs from the patient's colloquial framing". It presupposes a
# patient writing in a lay register, so it is reported for those conversations and not pooled with the others: on the
# first live report 70 of the 72 drift flags came from conversations with a clinical-register user or a clinician
# speaker, where clinical wording in the reply matches the user rather than departing from them (review 2026-10-13).
# The speaker and register values are the seed schema's (`user_is`) and the framing registry's register values; both
# are checked against the data when used.
DRIFT_SPEAKER = "patient"
DRIFT_REGISTERS = ("colloquial", "lay_careful")


def conversation_arms(meta: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, dict[str, Any]]:
    """Each Petri conversation's seed, arm, speaker and register, read from the run the report scored, through bound
    artifacts only: the transcripts file the report recorded (sha256 verified), the run's manifest, which must pass
    `manifest.verify_run`, bind those same transcripts, and carry the identity every transcript record names, its
    trees (conversation -> seed and arm; the manifest binds
    them, unlike analysis_rows.jsonl, which repro_pack.py notes is not manifest-bound), and the seed itself, digest
    verified (the arm's `user_is`, and the register its texts declare). Refuses when any link is missing or disagrees,
    so no conversation is placed in an arm by guesswork."""
    from scripts.petri_audit.framework import FRAMING_REGISTRY
    from scripts.petri_audit.manifest import CHAIN_FILE, verify_chain, verify_run
    from scripts.petri_audit.seeds import seed_digest

    registers = set()
    for dim in json.loads(Path(FRAMING_REGISTRY).read_text(encoding="utf-8")).get("dimensions", []):
        registers |= set((dim.get("value_definitions") or {}).keys())
    if not set(DRIFT_REGISTERS) <= registers:
        _refuse(f"Drift registers {DRIFT_REGISTERS} are not all register values of the framing registry")

    entry = meta.get("petri_transcripts")
    if not isinstance(entry, dict):
        _refuse("Report metadata has no 'petri_transcripts' block; cannot place its conversations in arms")
    _require_relative_path(entry.get("path"))
    recorded = _require_sha256(entry.get("sha256"), "petri_transcripts.sha256")
    transcripts = repo_root / entry["path"]
    if not transcripts.is_file() or hashlib.sha256(transcripts.read_bytes()).hexdigest() != recorded:
        _refuse(f"{entry['path']} is missing or differs from the transcripts the audit scored")
    run_dir = transcripts.parent
    problems = verify_run(run_dir)
    if problems:
        _refuse(f"{run_dir.relative_to(repo_root)} does not verify: {'; '.join(problems[:3])}")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    # the repository's manifest chain must name this run's manifest at its digest and verify through that line, so a
    # run whose transcripts and manifest were rewritten together (each still self-consistent) is refused
    chain_path = run_dir.parent / CHAIN_FILE
    chain = [ln for ln in chain_path.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if chain_path.is_file() else []
    for n, ln in enumerate(chain, 1):
        parts = ln.rsplit(" ", 1)
        if len(parts) != 2 or not parts[0] or len(parts[1]) != 64:
            _refuse(f"{CHAIN_FILE} line {n} is not '<manifest path> <sha256>': {ln[:80]!r}")
    rel = f"{run_dir.name}/manifest.json"
    line_no = next((i for i, ln in enumerate(chain, 1) if ln.rsplit(" ", 1)[0] == rel), None)
    if line_no is None or chain[line_no - 1].rsplit(" ", 1)[1] != (manifest.get("chain") or {}).get("manifest_sha256"):
        _refuse(f"{rel} is not named at its digest by {run_dir.parent.relative_to(repo_root)}/{CHAIN_FILE}")
    try:
        intact, why = verify_chain(run_dir.parent, lines=line_no)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        intact, why = False, f"{type(exc).__name__}: {exc}"
    if not intact:
        _refuse(f"the manifest chain does not verify through {rel}: {why}")
    if (manifest.get("artifacts") or {}).get("transcripts_sha256") != recorded:
        _refuse(f"{run_dir.relative_to(repo_root)}/manifest.json binds other transcripts than the ones the audit scored")
    # the scored transcripts name the manifest identity they were written under (provenance.run_manifest.sha256), and
    # verify_run has checked that identity against the manifest body, trees included: a manifest whose trees were
    # altered and resealed carries a new identity the scored transcripts do not name (Codex review of PR #107)
    identity = (manifest.get("chain") or {}).get("identity_sha256")
    for line_no, line in enumerate(transcripts.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        named = ((json.loads(line).get("provenance") or {}).get("run_manifest") or {}).get("sha256")
        if named != identity:
            _refuse(f"{entry['path']} record {line_no} names manifest identity {str(named)[:12]}..., not the run "
                    f"manifest's {str(identity)[:12]}...; the manifest's trees are not the ones the transcripts carry")

    placed: dict[str, tuple[str, str]] = {}
    for tree in manifest.get("trees", []):
        seed_id, arm = tree.get("seed_id"), tree.get("arm")
        for branch in tree.get("branches", []):
            cid = branch.get("conversation_id")
            if not all(isinstance(v, str) and v for v in (cid, seed_id, arm)):
                _refuse(f"Manifest tree {tree.get('tree_id')!r} lacks a conversation_id, seed_id or arm")
            if placed.setdefault(cid, (seed_id, arm)) != (seed_id, arm):
                _refuse(f"Conversation {cid} is placed in two arms by the manifest")

    seeds: dict[str, dict[str, Any]] = {}
    for rec in manifest.get("seeds", []):
        doc = json.loads((repo_root / rec["file"]).read_text(encoding="utf-8"))
        seed = next((sd for sd in doc.get("seeds", []) if sd.get("seed_id") == rec["seed_id"]), None)
        if seed is None or seed_digest(seed) != rec.get("seed_sha256"):
            _refuse(f"Seed {rec.get('seed_id')} in {rec.get('file')} is missing or differs from the run's recorded "
                    "digest")
        seeds[rec["seed_id"]] = seed

    out: dict[str, dict[str, Any]] = {}
    for cid, (seed_id, arm_id) in placed.items():
        seed = seeds.get(seed_id)
        arm = next((a for a in (seed or {}).get("protocol", {}).get("arms", []) if a.get("id") == arm_id), None)
        if arm is None:
            _refuse(f"Conversation {cid}: seed {seed_id} has no arm {arm_id!r}")
        texts = {t["key"]: t for t in seed["texts"]}
        # the arm's register is its first turn's, as the seed validator defines it (seeds.py, register exposure): an
        # initial_only seed's later turns may be `not_applicable`, which is not a register of the arm
        first = arm["turns"][0] if arm.get("turns") else None
        register = texts[first["text_ref"]].get("register") if first else None
        if register not in registers:
            _refuse(f"Conversation {cid}: register {register!r} is not a framing-registry register value")
        out[cid] = {"seed_id": seed_id, "arm": arm_id, "user_is": arm.get("user_is"), "register": register,
                    "drift_instrument_applies": arm.get("user_is") == DRIFT_SPEAKER and register in DRIFT_REGISTERS}
    return out


def _drift_summary(by_conversation: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Drift and register for a set of conversations. A conversation's turns are not independent observations, so the
    turn rate is descriptive and carries no interval; the inferential unit is the conversation: how many had any drift
    turn, with a Wilson interval over conversations (Codex review of PR #107)."""
    rows = [r for turns in by_conversation.values() for r in turns]
    n = len(rows)
    k = sum(r["has_register_drift"] for r in rows)
    convs = len(by_conversation)
    with_drift = sum(any(r["has_register_drift"] for r in turns) for turns in by_conversation.values())
    lo, hi = _wilson(with_drift, convs)
    scores = [r["formality_score"] for r in rows if r["formality_score"] is not None]
    tones: dict[str, int] = {}
    for r in rows:
        tones[r["tone_choice"]] = tones.get(r["tone_choice"], 0) + 1
    return {"conversations": convs, "assistant_turns": n, "drift_turns": k,
            "turn_drift_rate": round(k / n, 4) if n else None,
            "conversations_with_drift": with_drift,
            "conversation_drift_share": round(with_drift / convs, 4) if convs else None,
            "conversation_ci95_low": lo, "conversation_ci95_high": hi,
            "mean_formality_score": round(sum(scores) / len(scores), 3) if scores else None,
            "formality_scored_turns": len(scores), "tone_distribution": tones}


def _petri_report_rows(report_data: dict[str, Any], repo_root: Path) -> tuple[dict[str, list[dict[str, Any]]],
                                                                            list[dict[str, Any]]]:
    """One report's Petri rows, validated and grouped by conversation: ({conversation id: turn rows}, the raw rows).
    Both are empty when the report scored no Petri conversation."""
    # the audit runner always writes petri_cases (an empty list when it ran no Petri conversations), so a missing
    # or non-list field is a malformed report, not an empty dataset: refused, so it cannot delete a published file
    if "petri_cases" not in report_data or not isinstance(report_data["petri_cases"], list):
        _refuse("Report has no 'petri_cases' list; refusing rather than treating a malformed report as empty")
    petri_cases = report_data["petri_cases"]
    if not petri_cases:
        return {}, []

    meta = report_data.get("metadata", {})
    _require_is_mock(meta)
    tone_choices, score_top = _register_vocabulary(_recorded_rubric(meta, "register_rubric", repo_root))
    cases = report_data.get("cases")
    _check_provenance_counts(meta, cases if isinstance(cases, list) else [], petri_cases)
    seen: set[tuple[str, int]] = set()
    conversations: dict[str, list[dict[str, Any]]] = {}

    for idx, p in enumerate(petri_cases):
        if not isinstance(p, dict):
            _refuse(f"Petri case at index {idx} is not an object")
        cid = p.get("conversation_id")
        if not isinstance(cid, str) or not cid:
            _refuse(f"Petri case at index {idx} missing required 'conversation_id'")
        if "turn_index" not in p or p["turn_index"] is None:
            _refuse(f"Petri case {cid} missing required 'turn_index'")
        t_idx = _require_count(p["turn_index"], f"Petri case {cid} turn_index")
        if (cid, t_idx) in seen:
            _refuse(f"Petri conversation {cid} has more than one row for turn {t_idx}; the sampling unit is one "
                    "row per conversation per turn")
        seen.add((cid, t_idx))

        t_choice = p.get("tone_choice")
        if not isinstance(t_choice, str) or not t_choice:
            _refuse(f"Petri case {cid} turn {t_idx} missing required 'tone_choice'")
        if t_choice not in tone_choices:
            _refuse(f"Petri case {cid} turn {t_idx} has tone_choice {t_choice!r}; the recorded register rubric "
                    f"allows {sorted(tone_choices)}")

        if "has_register_drift" not in p or p["has_register_drift"] is None:
            _refuse(f"Petri case {cid} turn {t_idx} missing required 'has_register_drift'")
        if not isinstance(p["has_register_drift"], bool):
            _refuse(f"Petri case {cid} turn {t_idx} has_register_drift must be true or false, got "
                    f"{p['has_register_drift']!r}")
        has_drift = p["has_register_drift"]
        drift_prob = _unit_interval(p.get("drift_probability"), f"Petri case {cid} turn {t_idx} drift_probability")
        if has_drift != (drift_prob >= 0.5):
            _refuse(f"Petri case {cid} turn {t_idx} has has_register_drift {has_drift} with drift_probability "
                    f"{drift_prob}; the classifier sets the flag as probability >= 0.5")

        reg_score = _round_or_none(p.get("register_score"), f"Petri case {cid} turn {t_idx} register_score", 6)
        if reg_score is not None and not 0.0 <= reg_score <= score_top:
            _refuse(f"Petri case {cid} turn {t_idx} has register_score {reg_score}, outside the recorded rubric's "
                    f"0-{score_top:g} scale")

        conversations.setdefault(cid, []).append({
            "turn_index": t_idx,
            "tone_choice": t_choice,
            "tone_confidence": _unit_interval(p.get("tone_confidence"), f"Petri case {cid} turn {t_idx} tone_confidence"),
            "has_register_drift": has_drift,
            "drift_probability": drift_prob,
            "formality_score": reg_score,
        })

    return conversations, petri_cases


def _petri_run_entry(meta: dict[str, Any], report_sha: str, n_conversations: int) -> dict[str, Any]:
    """One scored Petri run as the payload names it: its transcripts (path and sha256, as the report recorded them),
    the report that scored it, when, and how much of it was scored."""
    entry = meta["petri_transcripts"]
    return {"path": entry["path"], "sha256": entry["sha256"], "run": PurePosixPath(entry["path"]).parent.name,
            "max_conversations": entry.get("max_conversations"), "turns_evaluated": entry.get("turns_evaluated"),
            "conversations": n_conversations, "audit_timestamp_utc": meta.get("timestamp_utc"),
            "source_report_sha256": report_sha}


def build_petri_drift_payload(report_data: dict[str, Any], report_sha: str, repo_root: Path = REPO_ROOT,
                              arms: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Build the petri_register_drift.json payload from one report's multi-turn Petri records
    (build_combined_petri_drift_payload with a single report). `arms` maps conversation ids to their arm; by default
    it is read from the run the report scored (conversation_arms)."""
    return build_combined_petri_drift_payload([(report_data, report_sha)], repo_root,
                                              arms=None if arms is None else [arms])


def build_combined_petri_drift_payload(reports: list[tuple[dict[str, Any], str]], repo_root: Path = REPO_ROOT,
                                       arms: list[dict[str, dict[str, Any]]] | None = None,
                                       source_report_sha256: str | None = None) -> dict[str, Any] | None:
    """Build the petri_register_drift.json payload from the Petri records of one or more reports, each of which may
    have scored a different Petri run. Drift is reported per arm (speaker and register) and, as the headline and the
    per-turn series, only for the conversations the drift question applies to (DRIFT_SPEAKER, DRIFT_REGISTERS).

    Each report's rows are validated on their own, and each report's conversations are placed in arms from the run
    that report scored (conversation_arms; `arms`, one map per report, replaces that in tests). The reports are then
    pooled as conversations: a conversation id found in two reports is refused, because a conversation scored twice
    would be counted twice. Reports with no Petri rows contribute nothing; None when no report has any. The caller
    checks that the reports share one classifier, register rubric, requested model and execution mode
    (check_combinable). `source_report_sha256` defaults to the single report's digest."""
    conversations: dict[str, list[dict[str, Any]]] = {}
    placed: dict[str, dict[str, Any]] = {}
    run_of: dict[str, str] = {}
    all_rows: list[dict[str, Any]] = []
    petri_reports: list[tuple[dict[str, Any], str]] = []
    runs: list[dict[str, Any]] = []
    for i, (report_data, report_sha) in enumerate(reports):
        convs, rows = _petri_report_rows(report_data, repo_root)
        if not rows:
            continue
        meta = report_data.get("metadata", {})
        report_arms = arms[i] if arms is not None else conversation_arms(meta, repo_root)
        unplaced = sorted(set(convs) - set(report_arms))
        if unplaced:
            _refuse(f"{len(unplaced)} Petri conversation(s) are not in the scored run's analysis rows "
                    f"(first: {unplaced[0]}); cannot place them in an arm")
        twice = sorted(set(convs) & set(conversations))
        if twice:
            _refuse(f"{len(twice)} Petri conversation(s) appear in more than one report (first: {twice[0]}); a "
                    "conversation scored twice would be counted twice")
        conversations.update(convs)
        placed.update({cid: report_arms[cid] for cid in convs})
        all_rows.extend(rows)
        petri_reports.append((report_data, report_sha))
        runs.append(_petri_run_entry(meta, report_sha, len(convs)))
        run_of.update({cid: runs[-1]["run"] for cid in convs})
    if not petri_reports:
        return None
    arms_by_cid = placed

    # turn_index is the row's raw position in its own transcript (tool and other records included), so the same
    # assistant position can carry different indices in different conversations. Rows are therefore ranked within
    # each conversation, and the per-turn series is aggregated by that per-conversation assistant ordinal. The series
    # covers only the conversations the drift question applies to.
    by_ordinal: dict[int, list[int]] = {}
    indices_at: dict[int, set[int]] = {}
    for cid in conversations:
        conversations[cid].sort(key=lambda t: t["turn_index"])
        for ordinal, row in enumerate(conversations[cid], 1):
            row["assistant_turn_ordinal"] = ordinal
            if not arms_by_cid[cid]["drift_instrument_applies"]:
                continue
            counts = by_ordinal.setdefault(ordinal, [0, 0])
            counts[1] += 1
            counts[0] += int(row["has_register_drift"])
            indices_at.setdefault(ordinal, set()).add(row["turn_index"])
    if not by_ordinal:
        _refuse(f"No Petri conversation has a {DRIFT_SPEAKER} speaker in a {' or '.join(DRIFT_REGISTERS)} register; "
                "the drift question applies to none of them")

    groups: dict[tuple[Any, Any], list[str]] = {}
    for cid in conversations:
        groups.setdefault((arms_by_cid[cid]["user_is"], arms_by_cid[cid]["register"]), []).append(cid)
    by_arm = [{"user_is": user_is, "register": register,
               "drift_instrument_applies": arms_by_cid[cids[0]]["drift_instrument_applies"],
               **_drift_summary({c: conversations[c] for c in cids})}
              for (user_is, register), cids in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))]
    applicable = [c for c in conversations if arms_by_cid[c]["drift_instrument_applies"]]

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


    meta = petri_reports[0][0].get("metadata", {})
    if len(petri_reports) == 1:
        provenance = {k: v for k, v in _publishable_provenance(
            meta, has_advice=bool(petri_reports[0][0].get("cases")), has_petri=True).items()
            if k in ("audit_timestamp_utc", "register_rubric", "classifier_sha256", "parameters",
                     "petri_transcripts", "checkpoint")}
    else:
        # several runs: what they share is published once; what differs per run is in petri_runs
        shared = _publishable_provenance(meta, has_advice=False, has_petri=True)
        provenance = {"audit_timestamp_utc": None, "register_rubric": shared["register_rubric"],
                      "classifier_sha256": shared["classifier_sha256"], "parameters": None,
                      "petri_transcripts": None, "checkpoint": None}
        for report_data, _ in petri_reports[1:]:
            _publishable_provenance(report_data.get("metadata", {}), has_advice=False, has_petri=True)
    provenance["petri_runs"] = runs

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_report_sha256": source_report_sha256 or petri_reports[0][1],
        "model_requested": _require_model_requested(meta),
        "models_served": _served_models(all_rows, "Petri case"),
        "is_mock": _require_is_mock(meta),
        "provenance": provenance,
        "status": "exploratory",
        "per_turn_interval": "wilson_95; per-turn marginal, not a test of trend (the same conversations recur)",
        "aggregate_interval": "wilson_95 over conversations (conversations_with_drift); turn_drift_rate is descriptive",
        "drift_instrument": {"applies_to": {"user_is": DRIFT_SPEAKER, "registers": list(DRIFT_REGISTERS)},
                             "question_source": "register_rubric petri_register.drift.instructions"},
        "headline_metrics": {
            "total_conversations": len(conversations),
            "total_assistant_turns": len(all_rows),
            # drift where the question applies; the per-arm table carries every arm, the others included
            "applicable": _drift_summary({c: conversations[c] for c in applicable}),
            "petri_phase_spend": _phase_spend(all_rows, "Petri case"),
            "min_turn_n": min(t["n"] for t in drift_by_turn),
            "max_turn_n": max(t["n"] for t in drift_by_turn),
        },
        "by_arm": by_arm,
        "drift_by_turn": drift_by_turn,
        "conversations": {cid: {"seed_id": arms_by_cid[cid]["seed_id"], "arm": arms_by_cid[cid]["arm"],
                                "user_is": arms_by_cid[cid]["user_is"], "register": arms_by_cid[cid]["register"],
                                "drift_instrument_applies": arms_by_cid[cid]["drift_instrument_applies"],
                                "run": run_of[cid], "turns": turns} for cid, turns in conversations.items()},
    }


def combined_report_sha256(shas: list[str]) -> str:
    """The identifier both payloads carry as source_report_sha256: the report's own digest when there is one report;
    for several, the sha256 of their digests sorted and joined, each followed by a newline, so the same set of
    reports gives the same identifier whatever order they were passed in."""
    if len(shas) == 1:
        return shas[0]
    return hashlib.sha256("".join(f"{sha}\n" for sha in sorted(shas)).encode("ascii")).hexdigest()


def source_report_entries(reports: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    """Every report the export read, in the order given: its digest, how many advice and Petri rows it holds, and the
    Petri transcripts it scored (null when it scored none)."""
    out = []
    for data, sha in reports:
        petri = (data.get("metadata") or {}).get("petri_transcripts")
        out.append({"sha256": sha, "advice_cases": len(data.get("cases") or []),
                    "petri_turns": len(data.get("petri_cases") or []),
                    "petri_transcripts": petri.get("path") if isinstance(petri, dict) else None})
    return out


def check_combinable(reports: list[tuple[dict[str, Any], str]]) -> int:
    """Refuse a set of reports that cannot be pooled into one export; return the index of the one advice report.

    Pooled reports must be one instrument: the same requested model, execution mode (all live or all mock),
    classifier digest, advice rubric and register rubric. No report may appear twice, and no Petri run may be
    scored by two reports (its conversations would be counted twice). Exactly one report carries advice cases: the
    calibration payload is that report's, unchanged. Advice runs are not pooled, because two runs over one archive
    score overlapping responses; the others are Petri-only (audit_jev_calibration.py --skip-advice), with no advice
    rows, no advice or golden-benchmark provenance, and spend totals that equal their Petri rows."""
    shas = [sha for _, sha in reports]
    if len(set(shas)) != len(shas):
        _refuse("The same report was passed more than once")

    def ident(data: dict[str, Any]) -> tuple[Any, ...]:
        meta = data.get("metadata") or {}
        return (_require_model_requested(meta), _require_is_mock(meta),
                (meta.get("classifier") or {}).get("sha256"), (meta.get("rubric") or {}).get("sha256"),
                (meta.get("register_rubric") or {}).get("sha256"))
    first = ident(reports[0][0])
    for data, sha in reports[1:]:
        if ident(data) != first:
            _refuse(f"Report {sha[:12]}... differs from {shas[0][:12]}... in requested model, execution mode, "
                    "classifier or rubric; reports pooled into one export must be one instrument")
    seen_runs: dict[str, str] = {}
    for data, sha in reports:
        petri = (data.get("metadata") or {}).get("petri_transcripts")
        if isinstance(petri, dict) and data.get("petri_cases"):
            run = _require_sha256(petri.get("sha256"), "petri_transcripts.sha256")
            if run in seen_runs:
                _refuse(f"Reports {seen_runs[run][:12]}... and {sha[:12]}... scored the same Petri transcripts "
                        f"({petri.get('path')}); its conversations would be counted twice")
            seen_runs[run] = sha
    advice = [i for i, (data, _) in enumerate(reports) if data.get("cases")]
    if len(advice) != 1:
        _refuse(f"{len(advice)} of the reports carry advice cases; exactly one must (the calibration payload is that "
                "report's). Score further Petri runs with audit_jev_calibration.py --skip-advice")
    for i, (data, sha) in enumerate(reports):
        if i == advice[0]:
            continue
        meta, metrics = data.get("metadata") or {}, data.get("metrics") or {}
        for block in ("advice_archive", "advice_judgments", "golden_benchmark"):
            if block in meta:
                _refuse(f"Report {sha[:12]}... has no advice cases but records {block} provenance; a Petri-only "
                        "report records neither")
        if _require_count(metrics.get("total_cases"), "total_cases") != 0:
            _refuse(f"Report {sha[:12]}... gives total_cases {metrics.get('total_cases')} with no case rows")
        rows = data.get("petri_cases")
        if not isinstance(rows, list) or not rows:
            _refuse(f"Report {sha[:12]}... has neither advice cases nor Petri rows")
        _check_combined_spend(metrics, [_phase_spend(rows, "Petri case")])
    return advice[0]


def serialize_payload(doc: dict[str, Any], name: str) -> str:
    """Strict JSON: NaN and infinities (which Python's parser accepts and its encoder would emit) are not JSON, and
    the site's JSON.parse would reject the whole file, so they refuse the export before anything is written."""
    try:
        return json.dumps(doc, indent=2, allow_nan=False)
    except ValueError as exc:
        _refuse(f"{name} holds a non-finite number ({exc}); refusing to write invalid JSON")
        return ""


def _stage(target_path: Path, text: str) -> Path:
    """Write `text` to a staging file created fresh and exclusively (mkstemp) beside the target, so it can never be
    an existing file such as the source report or a link to it. Returns the staging path; nothing is replaced."""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target_path.name}.", suffix=".tmp", dir=target_path.parent)
    try:
        # mkstemp creates the file owner-only (0600) and os.replace keeps that mode; a published file is world-readable
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return Path(tmp_name)


def write_payloads(writes: list[tuple[Path, str]], remove: Path | None) -> None:
    """Publish the pair together: every target is checked (its directory exists; it is absent or a regular file)
    and every payload staged before any target is replaced, so a bad second target cannot leave the site holding
    a calibration file and a Petri file from different reports. `remove` is a stale Petri file deleted last."""
    for target, _ in writes:
        if not target.parent.is_dir():
            _refuse(f"Output directory does not exist: {target.parent}")
        if target.exists() and not target.is_file():
            _refuse(f"Output {target} exists and is not a regular file")
    if remove is not None and remove.exists() and not remove.is_file():
        _refuse(f"Stale Petri output {remove} exists and is not a regular file")
    staged: list[tuple[Path, Path]] = []
    try:
        for target, text in writes:
            staged.append((_stage(target, text), target))
    except BaseException:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise
    for tmp, target in staged:
        os.replace(tmp, target)
    if remove is not None and remove.is_file():
        remove.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--report",
        action="append",
        help="Path to a Jev audit report JSON (default: artifacts/jev_pilot_report.json). Repeat to combine several "
             "runs: exactly one report carries the advice cases, the others are Petri-only (--skip-advice), and the "
             "Petri payload pools every report's conversations (check_combinable has the rules)",
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

    report_paths = [Path(r) for r in (args.report or ["artifacts/jev_pilot_report.json"])]
    site_path = Path(args.site)

    out_calib = Path(args.out_calibration) if args.out_calibration else site_path / "data" / "jev_calibration.json"
    out_petri = Path(args.out_petri_drift) if args.out_petri_drift else site_path / "data" / "petri_register_drift.json"
    if out_calib.resolve() == out_petri.resolve():
        _refuse(f"--out-calibration and --out-petri-drift resolve to the same file ({out_calib.resolve()})")
    for name, out in (("--out-calibration", out_calib), ("--out-petri-drift", out_petri)):
        for report_path in report_paths:
            if out.resolve() == report_path.resolve():
                _refuse(f"{name} resolves to a source report ({report_path.resolve()}); it would be overwritten "
                        "or deleted")

    reports = [load_report(path) for path in report_paths]
    advice_index = check_combinable(reports) if len(reports) > 1 else 0
    source_sha = combined_report_sha256([sha for _, sha in reports])
    sources = source_report_entries(reports)

    calib_payload = build_calibration_payload(reports[advice_index][0], source_sha)
    petri_payload = build_combined_petri_drift_payload(reports, source_report_sha256=source_sha)
    calib_payload["source_reports"] = sources
    if petri_payload:
        petri_payload["source_reports"] = sources

    print("=== Jev Site Export Summary ===")
    for path, (_, sha) in zip(report_paths, reports):
        print(f"Source report: {path} (sha256: {sha[:12]}...)")
    if len(reports) > 1:
        print(f"Combined export identifier: {source_sha[:12]}... ({len(reports)} reports)")
    print(f"Advice cases: {calib_payload['headline_metrics']['total_advice_cases']}")
    head = calib_payload["headline_metrics"]

    unjudged = calib_payload["agreement_reference"] is None

    def fmt(v: float | None, pct: bool = False) -> str:
        if v is None:
            return "N/A (unjudged)" if unjudged else "N/A (undefined for this sample)"
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
        app = p_head["applicable"]
        print(f"Petri conversations: {p_head['total_conversations']} ({p_head['total_assistant_turns']} turns)")
        print(f"Drift where the question applies: {app['drift_turns']}/{app['assistant_turns']} turns "
              f"({app['turn_drift_rate']*100:.1f}%, descriptive); {app['conversations_with_drift']}/"
              f"{app['conversations']} conversations with any drift (Wilson 95% {app['conversation_ci95_low']}-"
              f"{app['conversation_ci95_high']})")
        for arm in petri_payload["by_arm"]:
            print(f"  {arm['user_is']} / {arm['register']}: drift {arm['drift_turns']}/{arm['assistant_turns']}, "
                  f"mean formality {arm['mean_formality_score']}"
                  + ("" if arm["drift_instrument_applies"] else "  (question does not apply)"))

    # both payloads are serialized before anything is written, so a refusal leaves both site files untouched
    calib_text = serialize_payload(calib_payload, "The calibration payload")
    petri_text = serialize_payload(petri_payload, "The Petri drift payload") if petri_payload else None

    if args.dry_run:
        if not petri_payload and out_petri.is_file():
            print(f"\n[Dry Run] Validated payloads successfully; stale Petri file {out_petri} would be removed.")
        else:
            print("\n[Dry Run] Validated payloads successfully; disk writes skipped.")
        return 0

    writes = [(out_calib, calib_text)] + ([(out_petri, petri_text)] if petri_text is not None else [])
    stale = out_petri if petri_text is None and out_petri.is_file() else None
    write_payloads(writes, remove=stale)
    print(f"\nWrote calibration payload -> {out_calib}")
    if petri_text is not None:
        print(f"Wrote Petri drift payload -> {out_petri}")
    elif stale is not None:
        print(f"Removed stale Petri drift payload -> {out_petri}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

