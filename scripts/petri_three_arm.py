"""Three-arm analysis for Wave-2 Petri audit runs.

Conducts cross-arm comparisons across three arms (colloquial, clinical, lay_careful)
and 2x3 crossed factorial arms (patient/clinician x 3 registers).

Cross-arm comparisons join on (exchange_index, final_in_exchange), refusing
by name any exchange where an arm has no eligible row or is not_applicable.

Per Section 5 of docs/petri_wave2_design.md:
One epoch is structure, not an estimate. No confidence intervals or p-values are emitted.
Ordinal scales (e.g. rubric tiers or dimensions declared ordinal in registries) are loaded
dynamically from repository data files, never hardcoded in source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADVICE_RUBRIC = REPO_ROOT / "data" / "advice_rubric.draft.json"
DEFAULT_URGENCY_TIERS = REPO_ROOT / "data" / "urgency_tiers.draft.json"
DEFAULT_OUTCOME_REGISTRY = REPO_ROOT / "docs" / "framework" / "outcome_dimensions.draft.json"
NOT_APPLICABLE = "not_applicable"

HEADER_NOTE = (
    "Three-Arm Petri Audit Analysis "
    "(one epoch is structure, not an estimate; no confidence intervals or p-values emitted)"
)


class Wave1RefusalError(ValueError):
    """Raised when three-arm analysis is attempted on Wave 1 runs."""


class RegistryMismatchError(ValueError):
    """Raised when loaded registry or rubric digest mismatches the run manifest."""


class InputRefusalError(ValueError):
    """Raised when the input rows cannot be analysed as they stand (malformed rows,
    conflicting provenance); the message names what was refused and how many rows."""


def _row_label(r: Mapping[str, Any]) -> str:
    """A row's identity for a refusal message: ids and ordinals only, never text."""
    return (f"(seed {r.get('seed_id')!r}, arm {r.get('arm')!r}, key {r.get('key')!r}, "
            f"conversation {str(r.get('conversation_id'))[:12]!r}, turn {r.get('turn_id')!r})")


def _malformed_row_problems(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every row that cannot be placed in the join: no arm, no key, or no integer exchange_index.

    Such a row used to be skipped silently, so a partially malformed file still produced a
    report with reduced coverage and no sign of the loss (Codex F5 on PR #30).
    """
    problems: list[str] = []
    for r in rows:
        missing = [f for f in ("arm", "key") if not r.get(f)]
        ex = r.get("exchange_index")
        if ex is None or isinstance(ex, bool) or not isinstance(ex, int):
            missing.append("exchange_index")
        if missing:
            problems.append(f"{_row_label(r)} lacks {', '.join(missing)}")
    return problems


def sha256_file(path: Path | str) -> str:
    """Computes SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(p: Path | str) -> str:
    """Returns repository-relative path if inside REPO_ROOT, otherwise str(path)."""
    path = Path(p)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class ExchangeComparisonRow:
    exchange_index: int
    arm_A_value: str | None
    arm_B_value: str | None
    same_or_different: bool | None
    comparison: str
    refusal_reason: str | None = None


@dataclass(frozen=True)
class ContrastCounts:
    n_exchanges_total: int
    n_compared: int
    n_differing: int
    n_same: int
    n_refused: int
    n_upgrade: int | None
    n_downgrade: int | None


@dataclass(frozen=True)
class ContrastResult:
    contrast_name: str
    arm_A: str
    arm_B: str
    is_ordinal: bool
    scale: list[str] | None
    counts: ContrastCounts
    refusals: list[dict[str, Any]]
    rows: list[ExchangeComparisonRow]


@dataclass(frozen=True)
class DimensionAnalysis:
    dimension_key: str
    kind: str
    is_ordinal: bool
    scale: list[str] | None
    contrasts: dict[str, ContrastResult]


@dataclass(frozen=True)
class SeedAnalysis:
    seed_id: str
    is_identity_seed: bool
    arms_present: list[str]
    dimensions: dict[str, DimensionAnalysis]


@dataclass(frozen=True)
class RunProvenance:
    run_ids: list[str]
    manifest_identity_sha256: list[str]
    engine_commits: list[str]
    judge_of_record: list[str]
    seed_digests: dict[str, str]
    outcome_registry_path: str
    outcome_registry_sha256: str
    manifest_outcome_registry_sha256: dict[str, str]
    rubric_path: str
    rubric_sha256: str
    rubric_manifest_status: str


@dataclass(frozen=True)
class ThreeArmReport:
    header: str
    provenance: RunProvenance
    ordinal_dimensions: list[str]
    nominal_dimensions: list[str]
    seeds: dict[str, SeedAnalysis]


def load_json(path: Path | str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_ordinal_scales(
    rubric_path: Path | str | None = None,
    outcome_registry_path: Path | str | None = None,
) -> dict[str, list[str]]:
    """Loads ordinal scales dynamically from repository data files.

    Scale values and their relative rankings must live in JSON data files,
    never in Python source.
    """
    rubric_file = Path(rubric_path or DEFAULT_ADVICE_RUBRIC)
    outcomes_file = Path(outcome_registry_path or DEFAULT_OUTCOME_REGISTRY)

    scales: dict[str, list[str]] = {}

    if rubric_file.is_file():
        rubric_data = load_json(rubric_file)
        # Advice rubric lists tiers least-urgent to most-urgent (e.g. self_care < routine < urgent < emergency)
        tier_ids = [t["id"] for t in rubric_data.get("tiers", [])]
        if tier_ids:
            scales["response_only"] = tier_ids
            scales["contextual"] = tier_ids

    if outcomes_file.is_file():
        outcomes_data = load_json(outcomes_file)
        for dim in outcomes_data.get("dimensions", []):
            dim_id = dim.get("id")
            if not dim_id:
                continue
            if dim.get("ordinal") and isinstance(dim.get("values"), list):
                scales[dim_id] = list(dim["values"])
            elif dim.get("scale") and isinstance(dim.get("scale"), list):
                scales[dim_id] = list(dim["scale"])

    return scales


def load_run_rows(
    run_dir: Path | str,
    outcome_registry_path: Path | str | None = None,
    rubric_path: Path | str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Loads manifest and analysis rows from a run directory.

    If analysis_rows.jsonl does not exist, judgments.jsonl is read.
    Validates that the run is eligible for three-arm analysis, cleanly refusing
    Wave 1 runs where exchange_index is null or only 2 arms are present,
    and verifying outcome registry and rubric digests against the manifest.
    """
    rdir = Path(run_dir)
    manifest_path = rdir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run directory {rdir} lacks manifest.json")

    manifest = load_json(manifest_path)
    run_id = manifest.get("run_id", str(rdir))

    # Invariant: manifest outcome_registry_sha256 must match loaded outcome registry
    outcomes_file = Path(outcome_registry_path or DEFAULT_OUTCOME_REGISTRY)
    if not outcomes_file.is_file():
        raise FileNotFoundError(f"Outcome registry file not found: {outcomes_file}")
    loaded_outcome_sha = sha256_file(outcomes_file)
    manifest_outcome_sha = manifest.get("framework", {}).get("outcome_registry_sha256")
    if not manifest_outcome_sha:
        raise RegistryMismatchError(
            f"Run '{run_id}' manifest.json lacks framework.outcome_registry_sha256"
        )
    if loaded_outcome_sha != manifest_outcome_sha:
        raise RegistryMismatchError(
            f"Run '{run_id}' manifest framework.outcome_registry_sha256 ({manifest_outcome_sha}) "
            f"does not match loaded outcome registry {_display_path(outcomes_file)} ({loaded_outcome_sha})"
        )

    # Invariant: manifest rubric digest (if recorded) must match loaded rubric
    rubric_file = Path(rubric_path or DEFAULT_ADVICE_RUBRIC)
    manifest_rubric_sha = (
        manifest.get("framework", {}).get("rubric_sha256")
        or manifest.get("framework", {}).get("advice_rubric_sha256")
        or manifest.get("artifacts", {}).get("rubric_sha256")
    )
    if manifest_rubric_sha:
        if not rubric_file.is_file():
            raise RegistryMismatchError(
                f"Run '{run_id}' manifest records rubric digest ({manifest_rubric_sha}), "
                f"but loaded rubric {_display_path(rubric_file)} does not exist"
            )
        loaded_rubric_sha = sha256_file(rubric_file)
        if loaded_rubric_sha != manifest_rubric_sha:
            raise RegistryMismatchError(
                f"Run '{run_id}' manifest rubric digest ({manifest_rubric_sha}) "
                f"does not match loaded advice rubric {_display_path(rubric_file)} ({loaded_rubric_sha})"
            )

    analysis_rows_path = rdir / "analysis_rows.jsonl"
    judgments_path = rdir / "judgments.jsonl"

    rows: list[dict[str, Any]] = []
    if analysis_rows_path.is_file():
        for line in analysis_rows_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    elif judgments_path.is_file():
        for line in judgments_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    else:
        raise FileNotFoundError(f"Run directory {rdir} has neither analysis_rows.jsonl nor judgments.jsonl")

    if not rows:
        raise ValueError(f"Run directory {rdir} contains no rows")

    # Check for Wave 1 runs
    arms_in_run = {r.get("arm") for r in rows if r.get("arm")}
    has_lay_careful = any("lay_careful" in arm for arm in arms_in_run)
    all_exchange_null = all(r.get("exchange_index") is None for r in rows)

    if all_exchange_null or not has_lay_careful:
        raise Wave1RefusalError(
            f"Wave-1 rows cannot be re-keyed from themselves: exchange_index does not appear in "
            f"rows in {rdir} ({sum(1 for r in rows if r.get('exchange_index') is None)}/{len(rows)} null) "
            f"and only arms {sorted(arms_in_run)} are present (missing lay_careful). "
            "(docs/petri_wave2_handoff.md section 6: 'Wave-1 rows cannot be re-keyed from themselves. "
            "exchange_index does not appear in data/petri/runs/run_35351739969_1/analysis_rows.jsonl; "
            "those rows predate the field and record it as null by design rather than being back-filled.')"
        )

    # Manifest must carry artifacts.judge_of_record
    artifacts = manifest.get("artifacts") or {}
    judge_rec = artifacts.get("judge_of_record")
    if not judge_rec:
        raise ValueError(f"Run {rdir} manifest.json lacks artifacts.judge_of_record")
    if isinstance(judge_rec, dict):
        if not judge_rec.get("judge_model"):
            raise ValueError(f"Run {rdir} manifest.json artifacts.judge_of_record lacks 'judge_model'")
    elif not isinstance(judge_rec, str):
        raise TypeError(f"Run {rdir} manifest.json artifacts.judge_of_record is {type(judge_rec).__name__}")

    return manifest, rows


def _compare_values(
    val_A: str | None,
    val_B: str | None,
    scale: list[str] | None,
) -> tuple[bool | None, str]:
    """Compares two values on an ordinal or nominal scale.

    Returns:
        (same_or_different, comparison_str)
        where same_or_different is True (same), False (different), or None (uncompared/refused)
        and comparison_str is "same", "different", "upgrade", or "downgrade".
    """
    if val_A is None or val_B is None:
        return None, "refused"

    if scale is not None:
        # a value off the scale has no rank, so neither a direction nor "same" can be read; the caller refuses
        # such an exchange by name first (Codex F10 on PR #30), and this guard keeps it from ever becoming a count
        off_scale = [v for v in (val_A, val_B) if v not in scale]
        if off_scale:
            raise ValueError(f"values {off_scale!r} are not on the ordinal scale")
        idx_A = scale.index(val_A)
        idx_B = scale.index(val_B)
        if idx_A > idx_B:
            return False, "upgrade"
        elif idx_A < idx_B:
            return False, "downgrade"
        else:
            return True, "same"

    if val_A == val_B:
        return True, "same"
    return False, "different"


def _row_problem(arm: str, row: Mapping[str, Any]) -> str | None:
    """Why one arm's final row cannot enter a comparison, or None when it can.

    not_applicable is tested first. `judge_runner.analysis_rows` derives `row_eligible` from
    `value != not_applicable`, so every repository-produced not_applicable row is also
    ineligible; testing ineligibility first would report such a row as merely ineligible and
    drop the dimension-specific `not_applicable_reason` the refusal exists to carry.
    """
    if row.get("value") == NOT_APPLICABLE or row.get("not_applicable_reason") is not None:
        reason = row.get("not_applicable_reason") or "the judge answered not_applicable"
        return f"arm '{arm}' is not_applicable ({reason})"
    if row.get("judge_error") is not None:
        return f"arm '{arm}' ineligible ({row['judge_error']})"
    if row.get("shared_prefix") is True:
        return f"arm '{arm}' ineligible (shared-prefix turn, judged on the root record)"
    if row.get("value") is None:
        return f"arm '{arm}' ineligible (null value)"
    if row.get("row_eligible") is False:
        return f"arm '{arm}' ineligible (row_eligible is false)"
    return None


def analyze_contrast(
    contrast_name: str,
    arm_A: str,
    arm_B: str,
    rows_by_arm: Mapping[str, Mapping[int, dict[str, Any]]],
    exchanges: Sequence[int],
    scale: list[str] | None,
    errors_by_arm: Mapping[str, Mapping[int, str]] | None = None,
) -> ContrastResult:
    """Analyzes a single pairwise contrast (arm_A vs arm_B) across all exchanges.

    Joins on (exchange_index, final_in_exchange=True).
    Refuses by name any exchange where an arm is missing, ineligible, not_applicable,
    missing final_in_exchange, or has duplicate final rows.
    """
    is_ordinal = scale is not None
    rows_A = rows_by_arm.get(arm_A, {})
    rows_B = rows_by_arm.get(arm_B, {})

    comparison_rows: list[ExchangeComparisonRow] = []
    refusals: list[dict[str, Any]] = []

    n_compared = 0
    n_differing = 0
    n_same = 0
    n_upgrade = 0 if is_ordinal else None
    n_downgrade = 0 if is_ordinal else None
    n_refused = 0

    for ex in sorted(exchanges):
        row_A = rows_A.get(ex)
        row_B = rows_B.get(ex)

        refusal_reason: str | None = None
        val_A: str | None = None
        val_B: str | None = None

        err_A = errors_by_arm.get(arm_A, {}).get(ex) if errors_by_arm else None
        err_B = errors_by_arm.get(arm_B, {}).get(ex) if errors_by_arm else None

        if err_A or err_B:
            err_parts = [e for e in (err_A, err_B) if e]
            refusal_reason = f"exchange {ex} refused: {'; '.join(err_parts)}"
        elif row_A is None and row_B is None:
            refusal_reason = f"exchange {ex} refused: neither arm '{arm_A}' nor '{arm_B}' has an eligible row"
        elif row_A is None:
            refusal_reason = f"exchange {ex} refused: arm '{arm_A}' has no eligible row"
        elif row_B is None:
            refusal_reason = f"exchange {ex} refused: arm '{arm_B}' has no eligible row"
        else:
            problems = [p for p in (_row_problem(arm_A, row_A), _row_problem(arm_B, row_B)) if p]
            if not problems and scale is not None:
                problems = [
                    f"arm '{arm}' value {str(row['value'])!r} is not on the registered ordinal scale"
                    for arm, row in ((arm_A, row_A), (arm_B, row_B))
                    if str(row["value"]) not in scale
                ]
            if problems:
                refusal_reason = f"exchange {ex} refused: {', '.join(problems)}"
            else:
                val_A = str(row_A["value"])
                val_B = str(row_B["value"])

        if refusal_reason is not None:
            n_refused += 1
            refusals.append({"exchange_index": ex, "reason": refusal_reason})
            comparison_rows.append(
                ExchangeComparisonRow(
                    exchange_index=ex,
                    arm_A_value=val_A,
                    arm_B_value=val_B,
                    same_or_different=None,
                    comparison="refused",
                    refusal_reason=refusal_reason,
                )
            )
        else:
            same_diff, comp_str = _compare_values(val_A, val_B, scale)
            n_compared += 1
            if same_diff is True:
                n_same += 1
            elif same_diff is False:
                n_differing += 1

            if comp_str == "upgrade" and n_upgrade is not None:
                n_upgrade += 1
            elif comp_str == "downgrade" and n_downgrade is not None:
                n_downgrade += 1

            comparison_rows.append(
                ExchangeComparisonRow(
                    exchange_index=ex,
                    arm_A_value=val_A,
                    arm_B_value=val_B,
                    same_or_different=same_diff,
                    comparison=comp_str,
                    refusal_reason=None,
                )
            )

    counts = ContrastCounts(
        n_exchanges_total=len(exchanges),
        n_compared=n_compared,
        n_differing=n_differing,
        n_same=n_same,
        n_refused=n_refused,
        n_upgrade=n_upgrade,
        n_downgrade=n_downgrade,
    )

    return ContrastResult(
        contrast_name=contrast_name,
        arm_A=arm_A,
        arm_B=arm_B,
        is_ordinal=is_ordinal,
        scale=scale,
        counts=counts,
        refusals=refusals,
        rows=comparison_rows,
    )


def analyze_seed(
    seed_id: str,
    seed_rows: list[dict[str, Any]],
    scales: Mapping[str, list[str]],
) -> SeedAnalysis:
    """Analyzes all judged dimensions and tier instruments for one seed.

    Identifies standard 3-arm seeds vs 2x3 identity seeds and builds the required contrasts:
    - Standard 3-arm:
        1. colloquial vs clinical (registered estimand)
        2. lay_careful vs colloquial (orthography decomposition)
        3. lay_careful vs clinical (terminology decomposition)
    - Identity seed (pw-petri-w2-identity-register):
        Within patient: (colloquial vs clinical, lay_careful vs colloquial, lay_careful vs clinical)
        Within clinician: (colloquial vs clinical, lay_careful vs colloquial, lay_careful vs clinical)
        Within colloquial: patient vs clinician
        Within clinical: patient vs clinician
        Within lay_careful: patient vs clinician
    """
    malformed = _malformed_row_problems(seed_rows)
    if malformed:
        raise InputRefusalError(
            f"seed '{seed_id}': {len(malformed)} of {len(seed_rows)} rows cannot be joined and are refused, "
            f"not skipped: " + "; ".join(malformed[:5]) + (" ..." if len(malformed) > 5 else "")
        )

    arms_present = sorted({r["arm"] for r in seed_rows if r.get("arm")})
    is_identity_seed = (
        seed_id == "pw-petri-w2-identity-register"
        or any(arm.startswith(("patient_", "clinician_")) for arm in arms_present)
    )

    # Group rows: dim_key -> arm -> exchange_index -> row
    # dim_data: dim_key -> arm -> exchange_index -> row (only final_in_exchange=True rows)
    dim_data: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
    # dim_errors: dim_key -> arm -> exchange_index -> refusal message
    dim_errors: dict[str, dict[str, dict[int, str]]] = {}
    dim_kinds: dict[str, str] = {}
    seed_exchanges: set[int] = set()

    for r in seed_rows:
        key = r.get("key")
        arm = r.get("arm")
        ex = r.get("exchange_index")

        # arm, key and an integer exchange_index are guaranteed by _malformed_row_problems above
        seed_exchanges.add(ex)

        dim_kinds[key] = r.get("kind", "outcome")
        if key not in dim_data:
            dim_data[key] = {}
        if arm not in dim_data[key]:
            dim_data[key][arm] = {}

        if key not in dim_errors:
            dim_errors[key] = {}
        if arm not in dim_errors[key]:
            dim_errors[key][arm] = {}

        turn_id = r.get("turn_id") if r.get("turn_id") is not None else r.get("assistant_turn_index", "unknown")

        # Invariant 1: Missing or non-boolean final_in_exchange must be refused by name, not defaulted to True.
        if "final_in_exchange" not in r or r.get("final_in_exchange") is None:
            err = f"arm '{arm}' row (turn {turn_id}) in exchange {ex} missing 'final_in_exchange'"
            dim_errors[key][arm][ex] = err
            dim_data[key][arm].pop(ex, None)
            continue
        elif not isinstance(r["final_in_exchange"], bool):
            err = (
                f"arm '{arm}' row (turn {turn_id}) in exchange {ex} has non-boolean 'final_in_exchange': "
                f"{r['final_in_exchange']!r}"
            )
            dim_errors[key][arm][ex] = err
            dim_data[key][arm].pop(ex, None)
            continue

        # Invariant 2: Intermediate assistant turns (final_in_exchange=False) are excluded from exchange outcomes.
        if not r["final_in_exchange"]:
            continue

        # Invariant 3: Two final rows in one exchange for one arm must be refused by name, not resolved to latest turn.
        if ex in dim_errors[key][arm]:
            continue

        if ex in dim_data[key][arm]:
            existing = dim_data[key][arm][ex]
            prev_turn = (
                existing.get("turn_id")
                if existing.get("turn_id") is not None
                else existing.get("assistant_turn_index", "unknown")
            )
            err = (
                f"arm '{arm}' has multiple rows with final_in_exchange=True in exchange {ex} "
                f"(turns {prev_turn} and {turn_id})"
            )
            dim_errors[key][arm][ex] = err
            dim_data[key][arm].pop(ex, None)
            continue

        dim_data[key][arm][ex] = r

    exchanges = sorted(seed_exchanges)
    analyzed_dimensions: dict[str, DimensionAnalysis] = {}
    all_dim_keys = sorted(set(dim_data.keys()) | set(dim_errors.keys()))

    for key in all_dim_keys:
        arm_rows = dim_data.get(key, {})
        arm_errors = dim_errors.get(key, {})
        kind = dim_kinds.get(key, "outcome")
        scale = scales.get(key)
        is_ordinal = scale is not None

        contrasts: dict[str, ContrastResult] = {}

        if not is_identity_seed:
            # Standard three-arm contrasts
            # 1. Registered estimand: colloquial vs clinical
            contrasts["colloquial_vs_clinical"] = analyze_contrast(
                contrast_name="colloquial_vs_clinical",
                arm_A="colloquial",
                arm_B="clinical",
                rows_by_arm=arm_rows,
                exchanges=exchanges,
                scale=scale,
                errors_by_arm=arm_errors,
            )
            # 2. Orthography decomposition: lay_careful vs colloquial
            contrasts["lay_careful_vs_colloquial"] = analyze_contrast(
                contrast_name="lay_careful_vs_colloquial",
                arm_A="lay_careful",
                arm_B="colloquial",
                rows_by_arm=arm_rows,
                exchanges=exchanges,
                scale=scale,
                errors_by_arm=arm_errors,
            )
            # 3. Terminology decomposition: lay_careful vs clinical
            contrasts["lay_careful_vs_clinical"] = analyze_contrast(
                contrast_name="lay_careful_vs_clinical",
                arm_A="lay_careful",
                arm_B="clinical",
                rows_by_arm=arm_rows,
                exchanges=exchanges,
                scale=scale,
                errors_by_arm=arm_errors,
            )
        else:
            # 2x3 identity crossed contrasts
            # (a) Within patient:
            contrasts["patient:colloquial_vs_clinical"] = analyze_contrast(
                contrast_name="patient:colloquial_vs_clinical",
                arm_A="patient_colloquial",
                arm_B="patient_clinical",
                rows_by_arm=arm_rows,
                exchanges=exchanges,
                scale=scale,
                errors_by_arm=arm_errors,
            )
            contrasts["patient:lay_careful_vs_colloquial"] = analyze_contrast(
                contrast_name="patient:lay_careful_vs_colloquial",
                arm_A="patient_lay_careful",
                arm_B="patient_colloquial",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            contrasts["patient:lay_careful_vs_clinical"] = analyze_contrast(
                contrast_name="patient:lay_careful_vs_clinical",
                arm_A="patient_lay_careful",
                arm_B="patient_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            # (b) Within clinician:
            contrasts["clinician:colloquial_vs_clinical"] = analyze_contrast(
                contrast_name="clinician:colloquial_vs_clinical",
                arm_A="clinician_colloquial",
                arm_B="clinician_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            contrasts["clinician:lay_careful_vs_colloquial"] = analyze_contrast(
                contrast_name="clinician:lay_careful_vs_colloquial",
                arm_A="clinician_lay_careful",
                arm_B="clinician_colloquial",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            contrasts["clinician:lay_careful_vs_clinical"] = analyze_contrast(
                contrast_name="clinician:lay_careful_vs_clinical",
                arm_A="clinician_lay_careful",
                arm_B="clinician_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            # (c) Identity contrasts within each register:
            contrasts["colloquial:patient_vs_clinician"] = analyze_contrast(
                contrast_name="colloquial:patient_vs_clinician",
                arm_A="patient_colloquial",
                arm_B="clinician_colloquial",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            contrasts["clinical:patient_vs_clinician"] = analyze_contrast(
                contrast_name="clinical:patient_vs_clinician",
                arm_A="patient_clinical",
                arm_B="clinician_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )
            contrasts["lay_careful:patient_vs_clinician"] = analyze_contrast(
                contrast_name="lay_careful:patient_vs_clinician",
                arm_A="patient_lay_careful",
                arm_B="clinician_lay_careful",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
                errors_by_arm=arm_errors,
            )

        analyzed_dimensions[key] = DimensionAnalysis(
            dimension_key=key,
            kind=kind,
            is_ordinal=is_ordinal,
            scale=scale,
            contrasts=contrasts,
        )

    return SeedAnalysis(
        seed_id=seed_id,
        is_identity_seed=is_identity_seed,
        arms_present=arms_present,
        dimensions=analyzed_dimensions,
    )


def analyze_run_directories(
    run_dirs: Sequence[Path | str],
    scales: Mapping[str, list[str]] | None = None,
    rubric_path: Path | str | None = None,
    outcome_registry_path: Path | str | None = None,
) -> ThreeArmReport:
    """Performs three-arm analysis across one or more run directories."""
    if not run_dirs:
        raise ValueError("No run directories provided")

    rubric_file = Path(rubric_path or DEFAULT_ADVICE_RUBRIC)
    outcomes_file = Path(outcome_registry_path or DEFAULT_OUTCOME_REGISTRY)

    active_scales = (
        scales
        if scales is not None
        else load_ordinal_scales(
            rubric_path=rubric_file,
            outcome_registry_path=outcomes_file,
        )
    )

    all_rows: list[dict[str, Any]] = []
    run_ids: list[str] = []
    manifest_identities: list[str] = []
    engine_commits: list[str] = []
    seed_digests: dict[str, str] = {}
    judges_of_record: list[str] = []
    manifest_outcome_digests: dict[str, str] = {}
    manifest_rubric_digests: dict[str, str | None] = {}

    for rdir in run_dirs:
        manifest, rows = load_run_rows(
            rdir,
            outcome_registry_path=outcomes_file,
            rubric_path=rubric_file,
        )
        run_id = manifest.get("run_id") or str(rdir)
        if manifest.get("run_id"):
            run_ids.append(manifest["run_id"])

        manifest_outcome_digests[run_id] = manifest.get("framework", {}).get("outcome_registry_sha256", "")
        manifest_rub_sha = (
            manifest.get("framework", {}).get("rubric_sha256")
            or manifest.get("framework", {}).get("advice_rubric_sha256")
            or manifest.get("artifacts", {}).get("rubric_sha256")
        )
        manifest_rubric_digests[run_id] = manifest_rub_sha

        identity_sha = manifest.get("chain", {}).get("identity_sha256")
        if identity_sha:
            manifest_identities.append(identity_sha)

        engine_sha = manifest.get("adapter", {}).get("engine_sha")
        if engine_sha:
            engine_commits.append(engine_sha)

        for s in manifest.get("seeds", []):
            sid = s.get("seed_id")
            s_sha = s.get("seed_sha256")
            if sid and s_sha:
                # rows are pooled by seed_id across runs, so one id with two digests would pool two different
                # stimuli under one name while the provenance kept only the last digest (Codex F9 on PR #30)
                if sid in seed_digests and seed_digests[sid] != s_sha:
                    raise InputRefusalError(
                        f"seed '{sid}' has digest {seed_digests[sid]} in an earlier run but {s_sha} in run "
                        f"'{run_id}'; runs with different stimuli under one seed_id are not pooled"
                    )
                seed_digests[sid] = s_sha

        judge_rec = manifest.get("artifacts", {}).get("judge_of_record")
        judge_name = judge_rec["judge_model"] if isinstance(judge_rec, dict) else str(judge_rec)
        if judge_name not in judges_of_record:
            judges_of_record.append(judge_name)

        all_rows.extend(rows)

    # Group rows by seed_id
    rows_by_seed: dict[str, list[dict[str, Any]]] = {}
    no_seed = [r for r in all_rows if not r.get("seed_id")]
    if no_seed:
        raise InputRefusalError(
            f"{len(no_seed)} of {len(all_rows)} rows carry no seed_id and are refused, not skipped: "
            + "; ".join(_row_label(r) for r in no_seed[:5])
        )
    for r in all_rows:
        rows_by_seed.setdefault(r["seed_id"], []).append(r)

    analyzed_seeds: dict[str, SeedAnalysis] = {}
    for sid, srows in sorted(rows_by_seed.items()):
        analyzed_seeds[sid] = analyze_seed(sid, srows, active_scales)

    loaded_outcome_sha = sha256_file(outcomes_file) if outcomes_file.is_file() else ""
    loaded_rubric_sha = sha256_file(rubric_file) if rubric_file.is_file() else ""

    if all(v is not None for v in manifest_rubric_digests.values()):
        rubric_status = "verified against manifest"
    elif any(v is not None for v in manifest_rubric_digests.values()):
        rubric_status = "partially recorded in manifest"
    else:
        rubric_status = "not recorded in manifest"

    ordinal_dims: list[str] = sorted({
        d_key
        for s in analyzed_seeds.values()
        for d_key, d_analysis in s.dimensions.items()
        if d_analysis.is_ordinal
    })
    nominal_dims: list[str] = sorted({
        d_key
        for s in analyzed_seeds.values()
        for d_key, d_analysis in s.dimensions.items()
        if not d_analysis.is_ordinal
    })

    header = (
        f"{HEADER_NOTE}\n"
        f"Ordinal dimensions ({len(ordinal_dims)}): {', '.join(ordinal_dims) if ordinal_dims else 'none'}\n"
        f"Nominal dimensions ({len(nominal_dims)}): {', '.join(nominal_dims) if nominal_dims else 'none'}"
    )

    provenance = RunProvenance(
        run_ids=run_ids,
        manifest_identity_sha256=manifest_identities,
        engine_commits=engine_commits,
        judge_of_record=judges_of_record,
        seed_digests=seed_digests,
        outcome_registry_path=_display_path(outcomes_file),
        outcome_registry_sha256=loaded_outcome_sha,
        manifest_outcome_registry_sha256=manifest_outcome_digests,
        rubric_path=_display_path(rubric_file),
        rubric_sha256=loaded_rubric_sha,
        rubric_manifest_status=rubric_status,
    )

    return ThreeArmReport(
        header=header,
        provenance=provenance,
        ordinal_dimensions=ordinal_dims,
        nominal_dimensions=nominal_dims,
        seeds=analyzed_seeds,
    )


def format_markdown_summary(report: ThreeArmReport) -> str:
    """Renders human-readable markdown summary tables of the analysis report."""
    lines: list[str] = [
        f"# {HEADER_NOTE}",
        "",
        f"**Ordinal dimensions ({len(report.ordinal_dimensions)})**: {', '.join(report.ordinal_dimensions) if report.ordinal_dimensions else 'none'}",
        f"**Nominal dimensions ({len(report.nominal_dimensions)})**: {', '.join(report.nominal_dimensions) if report.nominal_dimensions else 'none'}",
        "",
        "## Provenance",
        f"- **Run IDs**: {', '.join(report.provenance.run_ids) or 'None'}",
        f"- **Manifest identities**: {', '.join(report.provenance.manifest_identity_sha256) or 'None'}",
        f"- **Engine commits**: {', '.join(report.provenance.engine_commits) or 'None'}",
        f"- **Judge of record**: {', '.join(report.provenance.judge_of_record) or 'None'}",
        f"- **Outcome registry**: `{report.provenance.outcome_registry_path}` (`{report.provenance.outcome_registry_sha256[:12]}`)",
        f"- **Rubric**: `{report.provenance.rubric_path}` ({report.provenance.rubric_manifest_status})",
        f"- **Seeds analyzed**: {len(report.seeds)}",
        "",
    ]

    for seed_id, seed_analysis in sorted(report.seeds.items()):
        lines.append(f"## Seed: `{seed_id}` (arms: {', '.join(seed_analysis.arms_present)})")
        lines.append("")

        for dim_key, dim_analysis in sorted(seed_analysis.dimensions.items()):
            scale_desc = f"scale: {' < '.join(dim_analysis.scale)}" if dim_analysis.scale else "nominal"
            lines.append(f"### Instrument / Dimension: `{dim_key}` ({dim_analysis.kind}, {scale_desc})")
            lines.append("")

            for c_name, contrast in sorted(dim_analysis.contrasts.items()):
                c = contrast.counts
                direction_str = ""
                if c.n_upgrade is not None and c.n_downgrade is not None:
                    direction_str = f", Upgrade ({contrast.arm_A} > {contrast.arm_B}): {c.n_upgrade}, Downgrade: {c.n_downgrade}"

                lines.append(
                    f"#### Contrast: `{contrast.arm_A}` vs `{contrast.arm_B}` ({c_name})\n"
                    f"**Total exchanges**: {c.n_exchanges_total} | "
                    f"**Compared**: {c.n_compared} | **Differing**: {c.n_differing} | **Same**: {c.n_same}"
                    f"{direction_str} | **Refused**: {c.n_refused}"
                )
                lines.append("")

                if contrast.refusals:
                    lines.append("**Named Refusals:**")
                    for ref in contrast.refusals:
                        lines.append(f"- Exchange {ref['exchange_index']}: {ref['reason']}")
                    lines.append("")

                lines.append(f"| Exchange | `{contrast.arm_A}` | `{contrast.arm_B}` | Comparison |")
                lines.append("|---|---|---|---|")
                for r in contrast.rows:
                    val_a = r.arm_A_value or "—"
                    val_b = r.arm_B_value or "—"
                    comp = r.comparison
                    if r.refusal_reason:
                        comp = f"refused ({r.refusal_reason})"
                    lines.append(f"| {r.exchange_index} | {val_a} | {val_b} | {comp} |")
                lines.append("")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Three-arm analysis for Wave-2 Petri audit runs.",
    )
    parser.add_argument(
        "--run-dir",
        nargs="+",
        required=True,
        help="One or more Petri audit run directories (must contain manifest.json and analysis_rows.jsonl/judgments.jsonl)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw structured JSON instead of markdown tables",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write output file (defaults to stdout)",
    )
    parser.add_argument(
        "--rubric",
        type=Path,
        default=None,
        help="Optional path to advice rubric data file",
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=None,
        help="Optional path to outcome dimensions data file",
    )

    args = parser.parse_args(argv)

    rubric_path = args.rubric or DEFAULT_ADVICE_RUBRIC
    outcome_registry_path = args.outcomes or DEFAULT_OUTCOME_REGISTRY

    scales = load_ordinal_scales(
        rubric_path=rubric_path,
        outcome_registry_path=outcome_registry_path,
    )

    try:
        report = analyze_run_directories(
            run_dirs=args.run_dir,
            scales=scales,
            rubric_path=rubric_path,
            outcome_registry_path=outcome_registry_path,
        )
    except (Wave1RefusalError, RegistryMismatchError, InputRefusalError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (KeyError, ValueError, TypeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        output_text = json.dumps(asdict(report), indent=2, ensure_ascii=False)
    else:
        output_text = format_markdown_summary(report)

    if args.out:
        args.out.write_text(output_text, encoding="utf-8")
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
