"""Three-arm analysis for Wave-2 Petri audit runs.

Conducts cross-arm comparisons across three arms (colloquial, clinical, lay_careful)
and 2x3 crossed factorial arms (patient/clinician x 3 registers).

Cross-arm comparisons join on (exchange_index, final_in_exchange), refusing
by name any exchange where an arm has no eligible row or is not_applicable.

Per Section 5 of docs/petri_wave2_design.md:
One epoch is structure, not an estimate. No confidence intervals or p-values are emitted.
Ordinal scales (tiers, recommendation_specificity, safety_netting_presence) are loaded
dynamically from repository data files, never hardcoded in source.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADVICE_RUBRIC = REPO_ROOT / "data" / "advice_rubric.draft.json"
DEFAULT_URGENCY_TIERS = REPO_ROOT / "data" / "urgency_tiers.draft.json"
DEFAULT_OUTCOME_REGISTRY = REPO_ROOT / "docs" / "framework" / "outcome_dimensions.draft.json"

HEADER_NOTE = (
    "Petri Audit Three-Arm Analysis "
    "(one epoch is structure, not an estimate; no confidence intervals or p-values emitted)"
)


class Wave1RefusalError(ValueError):
    """Raised when three-arm analysis is attempted on Wave 1 runs."""



@dataclass
class ExchangeComparisonRow:
    exchange_index: int
    arm_A_value: str | None
    arm_B_value: str | None
    same_or_different: bool | None  # True if same, False if different, None if refused/uncompared
    comparison: str                 # "same", "different", "upgrade", "downgrade", or "refused"
    refusal_reason: str | None = None


@dataclass
class ContrastCounts:
    n_exchanges_total: int
    n_compared: int
    n_differing: int
    n_same: int
    n_refused: int
    n_upgrade: int | None = None    # for ordinal dimensions only
    n_downgrade: int | None = None  # for ordinal dimensions only


@dataclass
class ContrastResult:
    contrast_name: str
    arm_A: str
    arm_B: str
    is_ordinal: bool
    scale: list[str] | None
    counts: ContrastCounts
    refusals: list[dict[str, Any]]
    rows: list[ExchangeComparisonRow]


@dataclass
class DimensionAnalysis:
    dimension_key: str
    kind: str  # "tier" or "outcome"
    is_ordinal: bool
    scale: list[str] | None
    contrasts: dict[str, ContrastResult]


@dataclass
class SeedAnalysis:
    seed_id: str
    is_identity_seed: bool
    arms_present: list[str]
    dimensions: dict[str, DimensionAnalysis]


@dataclass
class RunProvenance:
    run_ids: list[str]
    manifest_identity_sha256: list[str]
    engine_commits: list[str]
    judge_of_record: list[str]
    seed_digests: dict[str, str]


@dataclass
class ThreeArmReport:
    header: str
    provenance: RunProvenance
    seeds: dict[str, SeedAnalysis]


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_ordinal_scales(
    rubric_path: Path | str | None = None,
    outcome_registry_path: Path | str | None = None,
    urgency_tiers_path: Path | str | None = None,
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
            # Ordinal dimensions declared in outcome registry
            if dim_id == "recommendation_specificity":
                # Values: ["none", "generic_deferral", "specific"] (low to high specificity)
                scales[dim_id] = list(dim.get("values", []))
            elif dim_id == "safety_netting_presence":
                # Values: ["absent", "generic", "specific"] (absent to explicit)
                scales[dim_id] = list(dim.get("values", []))
            elif dim.get("scale") and isinstance(dim["scale"], list):
                scales[dim_id] = list(dim["scale"])

    return scales


def load_run_rows(run_dir: Path | str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Loads manifest and analysis rows from a run directory.

    If analysis_rows.jsonl does not exist, judgments.jsonl is read.
    Validates that the run is eligible for three-arm analysis, cleanly refusing
    Wave 1 runs where exchange_index is null or only 2 arms are present.
    """
    rdir = Path(run_dir)
    manifest_path = rdir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run directory {rdir} lacks manifest.json")

    manifest = load_json(manifest_path)

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

    if val_A == val_B:
        return True, "same"

    if scale is not None and val_A in scale and val_B in scale:
        idx_A = scale.index(val_A)
        idx_B = scale.index(val_B)
        if idx_A > idx_B:
            return False, "upgrade"
        elif idx_A < idx_B:
            return False, "downgrade"
        else:
            return True, "same"

    return False, "different"


def analyze_contrast(
    contrast_name: str,
    arm_A: str,
    arm_B: str,
    rows_by_arm: Mapping[str, Mapping[int, dict[str, Any]]],
    exchanges: Sequence[int],
    scale: list[str] | None,
) -> ContrastResult:
    """Analyzes a single pairwise contrast (arm_A vs arm_B) across all exchanges.

    Joins on (exchange_index, final_in_exchange=True).
    Refuses by name any exchange where an arm is missing, ineligible, or not_applicable.
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

        if row_A is None and row_B is None:
            refusal_reason = f"exchange {ex} refused: neither arm '{arm_A}' nor '{arm_B}' has an eligible row"
        elif row_A is None:
            refusal_reason = f"exchange {ex} refused: arm '{arm_A}' has no eligible row"
        elif row_B is None:
            refusal_reason = f"exchange {ex} refused: arm '{arm_B}' has no eligible row"
        else:
            # Check eligibility and not_applicable
            na_A = row_A.get("value") == "not_applicable" or row_A.get("not_applicable_reason") is not None
            na_B = row_B.get("value") == "not_applicable" or row_B.get("not_applicable_reason") is not None
            inelig_A = row_A.get("row_eligible") is False or row_A.get("judge_error") is not None
            inelig_B = row_B.get("row_eligible") is False or row_B.get("judge_error") is not None

            if inelig_A or inelig_B:
                err_parts = []
                if inelig_A:
                    err_parts.append(f"arm '{arm_A}' ineligible ({row_A.get('judge_error') or 'ineligible row'})")
                if inelig_B:
                    err_parts.append(f"arm '{arm_B}' ineligible ({row_B.get('judge_error') or 'ineligible row'})")
                refusal_reason = f"exchange {ex} refused: {', '.join(err_parts)}"
            elif na_A or na_B:
                na_parts = []
                if na_A:
                    na_parts.append(f"arm '{arm_A}' is not_applicable ({row_A.get('not_applicable_reason')})")
                if na_B:
                    na_parts.append(f"arm '{arm_B}' is not_applicable ({row_B.get('not_applicable_reason')})")
                refusal_reason = f"exchange {ex} refused: {', '.join(na_parts)}"
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
    arms_present = sorted({r["arm"] for r in seed_rows if r.get("arm")})
    is_identity_seed = (
        seed_id == "pw-petri-w2-identity-register"
        or any(arm.startswith(("patient_", "clinician_")) for arm in arms_present)
    )

    # Group rows: dim_key -> arm -> exchange_index -> row
    # ONLY consider rows where final_in_exchange is True
    # (intermediate tool rounds where final_in_exchange is False are excluded from exchange comparisons)
    dim_data: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
    dim_kinds: dict[str, str] = {}
    seed_exchanges: set[int] = set()

    for r in seed_rows:
        ex = r.get("exchange_index")
        if ex is None:
            continue
        seed_exchanges.add(ex)

        # Skip intermediate assistant turns (e.g. tool-calling rows that are not final in exchange)
        if not r.get("final_in_exchange", True):
            continue

        key = r.get("key")
        arm = r.get("arm")
        if not key or not arm:
            continue

        dim_kinds[key] = r.get("kind", "outcome")
        if key not in dim_data:
            dim_data[key] = {}
        if arm not in dim_data[key]:
            dim_data[key][arm] = {}

        # If duplicate final_in_exchange row occurs, retain the latest turn
        existing = dim_data[key][arm].get(ex)
        if existing is None or r.get("turn_id", 0) >= existing.get("turn_id", 0):
            dim_data[key][arm][ex] = r

    exchanges = sorted(seed_exchanges)
    analyzed_dimensions: dict[str, DimensionAnalysis] = {}

    for key, arm_rows in sorted(dim_data.items()):
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
            )
            # 2. Orthography decomposition: lay_careful vs colloquial
            contrasts["lay_careful_vs_colloquial"] = analyze_contrast(
                contrast_name="lay_careful_vs_colloquial",
                arm_A="lay_careful",
                arm_B="colloquial",
                rows_by_arm=arm_rows,
                exchanges=exchanges,
                scale=scale,
            )
            # 3. Terminology decomposition: lay_careful vs clinical
            contrasts["lay_careful_vs_clinical"] = analyze_contrast(
                contrast_name="lay_careful_vs_clinical",
                arm_A="lay_careful",
                arm_B="clinical",
                rows_by_arm=arm_rows,
                exchanges=exchanges,
                scale=scale,
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
            )
            contrasts["patient:lay_careful_vs_colloquial"] = analyze_contrast(
                contrast_name="patient:lay_careful_vs_colloquial",
                arm_A="patient_lay_careful",
                arm_B="patient_colloquial",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            contrasts["patient:lay_careful_vs_clinical"] = analyze_contrast(
                contrast_name="patient:lay_careful_vs_clinical",
                arm_A="patient_lay_careful",
                arm_B="patient_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            # (b) Within clinician:
            contrasts["clinician:colloquial_vs_clinical"] = analyze_contrast(
                contrast_name="clinician:colloquial_vs_clinical",
                arm_A="clinician_colloquial",
                arm_B="clinician_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            contrasts["clinician:lay_careful_vs_colloquial"] = analyze_contrast(
                contrast_name="clinician:lay_careful_vs_colloquial",
                arm_A="clinician_lay_careful",
                arm_B="clinician_colloquial",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            contrasts["clinician:lay_careful_vs_clinical"] = analyze_contrast(
                contrast_name="clinician:lay_careful_vs_clinical",
                arm_A="clinician_lay_careful",
                arm_B="clinician_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            # (c) Identity contrasts within each register:
            contrasts["colloquial:patient_vs_clinician"] = analyze_contrast(
                contrast_name="colloquial:patient_vs_clinician",
                arm_A="patient_colloquial",
                arm_B="clinician_colloquial",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            contrasts["clinical:patient_vs_clinician"] = analyze_contrast(
                contrast_name="clinical:patient_vs_clinician",
                arm_A="patient_clinical",
                arm_B="clinician_clinical",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
            )
            contrasts["lay_careful:patient_vs_clinician"] = analyze_contrast(
                contrast_name="lay_careful:patient_vs_clinician",
                arm_A="patient_lay_careful",
                arm_B="clinician_lay_careful",
                rows_by_arm=arm_rows,
                scale=scale,
                exchanges=exchanges,
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
    judge_of_record: str = DEFAULT_JUDGE_OF_RECORD,
) -> ThreeArmReport:
    """Performs three-arm analysis across one or more run directories."""
    if not run_dirs:
        raise ValueError("No run directories provided")

    active_scales = scales if scales is not None else load_ordinal_scales()

    all_rows: list[dict[str, Any]] = []
    run_ids: list[str] = []
    manifest_identities: list[str] = []
    engine_commits: list[str] = []
    seed_digests: dict[str, str] = {}

    for rdir in run_dirs:
        manifest, rows = load_run_rows(rdir)
        run_id = manifest.get("run_id")
        if run_id:
            run_ids.append(run_id)

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
                seed_digests[sid] = s_sha

        all_rows.extend(rows)

    # Group rows by seed_id
    rows_by_seed: dict[str, list[dict[str, Any]]] = {}
    for r in all_rows:
        sid = r.get("seed_id")
        if sid:
            rows_by_seed.setdefault(sid, []).append(r)

    analyzed_seeds: dict[str, SeedAnalysis] = {}
    for sid, srows in sorted(rows_by_seed.items()):
        analyzed_seeds[sid] = analyze_seed(sid, srows, active_scales)

    provenance = RunProvenance(
        run_ids=run_ids,
        manifest_identity_sha256=manifest_identities,
        engine_commits=engine_commits,
        judge_of_record=judge_of_record,
        seed_digests=seed_digests,
    )

    return ThreeArmReport(
        header=HEADER_NOTE,
        provenance=provenance,
        seeds=analyzed_seeds,
    )


def format_markdown_summary(report: ThreeArmReport) -> str:
    """Renders human-readable markdown summary tables of the analysis report."""
    lines: list[str] = [
        f"# {report.header}",
        "",
        "## Provenance",
        f"- **Run IDs**: {', '.join(report.provenance.run_ids) or 'None'}",
        f"- **Manifest identities**: {', '.join(report.provenance.manifest_identity_sha256) or 'None'}",
        f"- **Engine commits**: {', '.join(report.provenance.engine_commits) or 'None'}",
        f"- **Judge of record**: {report.provenance.judge_of_record}",
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
    parser.add_argument(
        "--judge-model",
        type=str,
        default=DEFAULT_JUDGE_OF_RECORD,
        help="Judge model of record for wave-2 epoch",
    )

    args = parser.parse_args(argv)

    scales = load_ordinal_scales(
        rubric_path=args.rubric,
        outcome_registry_path=args.outcomes,
    )

    try:
        report = analyze_run_directories(
            run_dirs=args.run_dir,
            scales=scales,
            judge_of_record=args.judge_model,
        )
    except Wave1RefusalError as exc:
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
