"""Three-arm analysis for Wave-2 Petri audit runs.

Conducts cross-arm comparisons across three arms (colloquial, clinical, lay_careful)
and 2x3 crossed factorial arms (patient/clinician x 3 registers).

Cross-arm comparisons join on (exchange_index, final_in_exchange) within one
experimental cell, (run_id, epoch, branch_id): two arms are paired only when they
answered the same scripted exchange in the same run, epoch and branch. Any
exchange where an arm has no eligible row or is not_applicable is refused by name.

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
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.petri_audit.framework import load_prompt, prompt_canonical
    from scripts.petri_audit.judge_runner import dedupe_key, rubric_digest
except ModuleNotFoundError:  # run as a file path: the repository root is not on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.petri_audit.framework import load_prompt, prompt_canonical
    from scripts.petri_audit.judge_runner import dedupe_key, rubric_digest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADVICE_RUBRIC = REPO_ROOT / "data" / "advice_rubric.draft.json"
DEFAULT_URGENCY_TIERS = REPO_ROOT / "data" / "urgency_tiers.draft.json"
DEFAULT_OUTCOME_REGISTRY = REPO_ROOT / "docs" / "framework" / "outcome_dimensions.draft.json"
NOT_APPLICABLE = "not_applicable"

# One experimental cell, (run_id, epoch, branch_id), and one scripted exchange within it. Arms are paired only inside
# a cell: a run holds one tree per (seed, arm, epoch), the tree epoch restarts at 1 in every run, and branch_id names
# the same branch in every arm's tree (condition_id carries the arm, so it cannot pair anything).
CellKey = tuple[str, int, str]
ExchangeKey = tuple[str, int, str, int]

HEADER_NOTE = (
    "Three-Arm Petri Audit Analysis "
    "(one epoch is structure, not an estimate; no confidence intervals or p-values emitted)"
)


class Wave1RefusalError(ValueError):
    """Raised when three-arm analysis is attempted on Wave 1 runs."""


class RegistryMismatchError(ValueError):
    """Raised when the loaded outcome registry's digest mismatches the run manifest."""


class InputRefusalError(ValueError):
    """Raised when the input rows cannot be analysed as they stand (malformed rows,
    conflicting provenance); the message names what was refused and how many rows."""


def _row_label(r: Mapping[str, Any]) -> str:
    """A row's identity for a refusal message: ids and ordinals only, never text."""
    return (f"(seed {r.get('seed_id')!r}, arm {r.get('arm')!r}, key {r.get('key')!r}, "
            f"conversation {str(r.get('conversation_id'))[:12]!r}, turn {r.get('turn_id')!r})")


def _malformed_row_problems(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every row that cannot be placed in the join: no arm, key, run_id or branch_id, or a
    non-integer epoch or exchange_index.

    Such a row used to be skipped silently, so a partially malformed file still produced a
    report with reduced coverage and no sign of the loss (Codex F5 on PR #30).
    """
    problems: list[str] = []
    for r in rows:
        missing = [f for f in ("arm", "key", "run_id", "branch_id") if not isinstance(r.get(f), str) or not r.get(f)]
        missing += [f for f in ("epoch", "exchange_index")
                    if isinstance(r.get(f), bool) or not isinstance(r.get(f), int)]
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
    run_id: str
    epoch: int
    branch_id: str
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
    # the loaded rubric's canonical digest, in the form every tier judgment records as prompt_file_digest
    # (judge_runner.rubric_digest); tier rows recording another digest are refused per exchange
    rubric_canonical_digest: str
    # per run: tier judgment digest -> count of tier rows recording it
    tier_rubric_digests: dict[str, dict[str, int]]
    superseded_retry_rows: dict[str, int]
    # per run: the bound judgments.jsonl (verified equal to the manifest's binding) and the analysis_rows.jsonl read
    judgments_sha256: dict[str, str]
    analysis_rows_sha256: dict[str, str]


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


# Fields judge_runner.analysis_rows() copies from each judgment row unchanged.
FIELDS_FROM_JUDGMENT = (
    "conversation_id", "turn_id", "assistant_turn_index", "exchange_index", "final_in_exchange",
    "kind", "key", "judge_model", "not_applicable_reason",
)
# Fields it takes from the manifest tree and branch the judgment's conversation belongs to.
FIELDS_FROM_MANIFEST = ("seed_id", "tree_id", "epoch", "arm", "branch_id", "condition_id")
LEADING_LINE_AT_ANALYSIS = "leading_line_at_analysis"
# judge_runner's error for an outcome answer that is not one of the prompt's declared values (parse_answer). A null
# outcome judgment recorded with it, and carrying the judge's raw answer, is the one judgment analysis_rows() re-reads
# at analysis time (judge_runner._read_value, PR #29); tests/test_petri_three_arm.py ties the string to parse_answer.
OUT_OF_VOCABULARY = "answer is not one of the declared values"
# judge_runner.parse_outcome_answer's error (PR #29) for an answer whose later line revises its leading-line value.
# A re-read that refuses such an answer records this error in place of the vocabulary miss the judgment recorded.
CONFLICTING_VALUES = "answer names more than one declared value"
# every error a re-read that yields no value can record; a failed re-read keeps the value null on both sides
REREAD_REFUSAL_ERRORS = (OUT_OF_VOCABULARY, CONFLICTING_VALUES)
# the characters judge_runner.parse_outcome_answer (PR #29) trims from both ends of a candidate answer line
_ANSWER_TRIM = "`'\"* .:;,"


def _rereadable(j: Mapping[str, Any]) -> bool:
    """Whether analysis_rows() may re-read this judgment's answer at analysis time: a null outcome judgment (not a
    planner not_applicable) recorded as out of vocabulary, with the judge's raw answer. judge_runner._read_value copies
    every other judgment's value and error unchanged."""
    return (j.get("kind") == "outcome" and j.get("value") is None and not j.get("not_applicable_reason")
            and j.get("judge_error") == OUT_OF_VOCABULARY and isinstance(j.get("judge_raw"), str)
            and bool(j["judge_raw"]))


def _leading_line(text: str) -> str:
    """The answer's first non-empty line, trimmed and lower-cased: the only value a leading-line re-read can take
    (an answer that is the value alone is one line, so the same rule covers it)."""
    for line in text.splitlines():
        if line.strip():
            return line.strip().strip(_ANSWER_TRIM).lower()
    return ""


def _declared_values(j: Mapping[str, Any], cache: dict[tuple[str, str], list[str] | None]) -> list[str] | None:
    """The value list of the prompt the judge was shown: the file at the judgment's prompt_ref, used only when it
    digests to the judgment's prompt_file_digest, as judge_runner._read_value requires. None when the file cannot be
    read or has changed since, in which case that reader leaves the judgment null."""
    ref, digest = j.get("prompt_ref"), j.get("prompt_file_digest")
    if not isinstance(ref, str) or not ref or not isinstance(digest, str):
        return None
    if (ref, digest) not in cache:
        try:
            prompt = load_prompt(ref)
            same = hashlib.sha256(prompt_canonical(prompt).encode("utf-8")).hexdigest()[:12] == digest
            cache[(ref, digest)] = list(prompt["values"]) if same else None
        except (OSError, ValueError, KeyError, TypeError):
            cache[(ref, digest)] = None
    return cache[(ref, digest)]


def _value_problems(
    a: Mapping[str, Any],
    j: Mapping[str, Any],
    prompt_values: dict[tuple[str, str], list[str] | None],
) -> list[str]:
    """Where a derived row's value and judge_error depart from what analysis_rows() can derive from its judgment.

    Value and error are copied unchanged, except for a judgment `_rereadable` admits. For that judgment, a row marked
    value_source leading_line_at_analysis carries the answer's leading line with no error, and that line must be a
    declared value of the prompt the judge was shown, at the recorded digest. Any other judgment marked as re-read is
    refused (Codex review of the F2 fix on PR #30: a tier row, or an outcome row with another error, was accepted with
    any value). The later-line revision check (a CONFLICTING_VALUES answer) lives in PR #29's parse_outcome_answer and
    is not repeated here.

    A re-read that yields no value names its own reason (a revised answer is CONFLICTING_VALUES, not the recorded
    vocabulary miss), so for a judgment `_rereadable` admits, a row with a null value, no value_source and one of
    REREAD_REFUSAL_ERRORS is what analysis_rows() writes (Codex review of the F2 fix on PR #30: run_35801345137_1
    line 509 re-derived that way was refused, refusing the whole run).
    """
    if a.get("value_source") != LEADING_LINE_AT_ANALYSIS:
        bad = ["value"] if a.get("value") != j.get("value") else []
        failed_reread = (_rereadable(j) and a.get("value") is None and a.get("value_source") is None
                         and a.get("judge_error") in REREAD_REFUSAL_ERRORS)
        if a.get("judge_error") != j.get("judge_error") and not failed_reread:
            bad.append("judge_error")
        return bad
    if not _rereadable(j):
        return ["value_source (marked as re-read, but the judgment is not a null out-of-vocabulary outcome answer "
                "with a recorded answer)"]
    bad: list[str] = []
    value = a.get("value")
    allowed = _declared_values(j, prompt_values)
    if value is None or value != _leading_line(j["judge_raw"]):
        bad.append("value (not the leading line of the judge's recorded answer)")
    elif allowed is None:
        bad.append("value (the prompt at the recorded prompt_ref and digest is not available to confirm it)")
    elif value not in allowed and value != NOT_APPLICABLE:
        bad.append("value (not a declared value of the prompt the judge was shown)")
    if a.get("judge_error") is not None:
        bad.append("judge_error")
    return bad


def _bound_judgments(rdir: Path, manifest: Mapping[str, Any], run_id: str) -> list[dict[str, Any]]:
    """The run's judgments.jsonl, refused unless it digests to the value the manifest binds.

    A resumed judging pass appends rows and then rebinds, so a file that no longer matches the binding
    holds rows no completed pass vouched for (or was edited)."""
    bound = (manifest.get("artifacts") or {}).get("judgments_sha256")
    jpath = rdir / "judgments.jsonl"
    if not bound:
        raise InputRefusalError(
            f"Run '{run_id}' manifest binds no judgments (artifacts.judgments_sha256 is absent), so its "
            "analysis_rows.jsonl cannot be authenticated"
        )
    if not jpath.is_file():
        raise InputRefusalError(f"Run '{run_id}' manifest binds judgments but {jpath} is missing")
    actual = sha256_file(jpath)
    if actual != bound:
        raise InputRefusalError(
            f"Run '{run_id}' judgments.jsonl digests to {actual}, not the bound {bound}: rows were appended or "
            "edited after the last completed judging pass bound it"
        )
    return [json.loads(line) for line in jpath.read_text(encoding="utf-8").splitlines() if line.strip()]


def _derived_row_problems(
    rows: Sequence[Mapping[str, Any]],
    judgments: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> list[str]:
    """Where analysis_rows.jsonl departs from what analysis_rows() derives from the bound judgments.

    analysis_rows() emits exactly one row per judgment, in file order, so the two files align line for
    line. A stale file (derived before a resumed pass appended judgments) fails the count; an edited one
    fails the field comparison. Checked per line: every field copied from the judgment, the instrument
    digest where the row carries it, the value and judge error (equal, or the one re-read `_value_problems`
    admits), the eligibility flags, and every field taken from the manifest tree.
    """
    if len(rows) != len(judgments):
        return [f"analysis_rows.jsonl has {len(rows)} rows but the bound judgments.jsonl has {len(judgments)}; "
                "the derived rows are stale or edited"]
    by_conv: dict[str, dict[str, Any]] = {}
    for tree in manifest.get("trees") or []:
        for b in tree.get("branches") or []:
            by_conv[b.get("conversation_id")] = {
                "seed_id": tree.get("seed_id"), "tree_id": tree.get("tree_id"), "epoch": tree.get("epoch"),
                "arm": tree.get("arm"), "branch_id": b.get("branch_id"), "condition_id": b.get("condition_id"),
                "branched_from_turn_id": b.get("branched_from_turn_id"),
            }
    problems: list[str] = []
    prompt_values: dict[tuple[str, str], list[str] | None] = {}
    for line_no, (a, j) in enumerate(zip(rows, judgments), start=1):
        bad = [f for f in FIELDS_FROM_JUDGMENT if a.get(f) != j.get(f)]
        if "prompt_file_digest" in a and a["prompt_file_digest"] != j.get("prompt_file_digest"):
            bad.append("prompt_file_digest")
        bad.extend(_value_problems(a, j, prompt_values))
        info = by_conv.get(a.get("conversation_id"))
        if info is None:
            bad.append("conversation_id not in the manifest's trees")
        else:
            bad.extend(f for f in FIELDS_FROM_MANIFEST if a.get(f) != info[f])
            anchor = info["branched_from_turn_id"]
            shared = anchor is not None and isinstance(a.get("turn_id"), int) and a["turn_id"] <= anchor
            if a.get("shared_prefix", False) != shared:
                bad.append("shared_prefix")
            eligible = (not shared) and a.get("value") is not None and a.get("value") != NOT_APPLICABLE
            if "row_eligible" in a and a["row_eligible"] != eligible:
                bad.append("row_eligible")
        if bad:
            problems.append(f"line {line_no}: {', '.join(bad)}")
    return problems


def collapse_retries(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """The latest row per judgment key, and how many earlier attempts it superseded.

    A resumed judging pass appends a replacement for a null judgment under the same key
    (`judge_runner.dedupe_key`), and the pipeline treats the latest row per key as authoritative
    (`judge_runner.cumulative_counts`); `analysis_rows()` still emits every attempt. Collapsing
    here, before the one-final-row-per-exchange check, keeps a recovered retry from being refused
    as a duplicate final row (Codex F8 on PR #30). A non-null judgment is never retried, so the
    latest row is the one the pipeline counts. The superseded count is reported, not hidden.
    """
    latest: dict[tuple, int] = {}
    for i, r in enumerate(rows):
        latest[dedupe_key(r)] = i
    keep = sorted(latest.values())
    return [rows[i] for i in keep], len(rows) - len(keep)


def load_run_rows(
    run_dir: Path | str,
    outcome_registry_path: Path | str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Loads manifest and analysis rows from a run directory.

    Returns the manifest, the authenticated rows with retried judgments collapsed to the latest
    attempt per judgment key, and the number of superseded attempts.

    analysis_rows.jsonl is required; raw judgments.jsonl rows are never read in its place.
    Validates that the run is eligible for three-arm analysis, cleanly refusing
    Wave 1 runs where exchange_index is null or only 2 arms are present,
    and verifying the outcome registry digest against the manifest.
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

    # The rubric is verified against the digest every tier judgment records (prompt_file_digest), in
    # analyze_seed: the manifest schema has no rubric field, so a manifest check could never fire (Codex F3 on PR #30).

    analysis_rows_path = rdir / "analysis_rows.jsonl"

    # Raw judgments.jsonl rows are not a fallback: judge_runner writes them without `arm` (analysis_rows() adds it
    # from the manifest tree) and without the analysis-time leading-line value read, so reading them unchanged
    # left every Wave-2 run looking like Wave 1 (Codex F4 on PR #30). The derived rows are required.
    if not analysis_rows_path.is_file():
        raise InputRefusalError(
            f"Run directory {rdir} has no analysis_rows.jsonl; derive it from the bound judgments with "
            f"`python -m scripts.petri_audit.cli analyze --seeds <seed file of record> --run-dir {rdir}` "
            "(raw judgments.jsonl rows carry no arm and are not analysed directly)"
        )
    rows: list[dict[str, Any]] = []
    for line in analysis_rows_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    if not rows:
        raise ValueError(f"Run directory {rdir} contains no rows")

    # analysis_rows.jsonl is derived and unbound: authenticate every row against the judgments the manifest binds and
    # the manifest's own tree before any count is made from it (Codex F2 on PR #30)
    judgments = _bound_judgments(rdir, manifest, run_id)
    problems = _derived_row_problems(rows, judgments, manifest)
    if problems:
        raise InputRefusalError(
            f"Run '{run_id}' analysis_rows.jsonl does not match its bound judgments.jsonl and manifest "
            f"({len(problems)} problem(s)): " + "; ".join(problems[:5]) + (" ..." if len(problems) > 5 else "")
            + f". Re-derive it with `python -m scripts.petri_audit.cli analyze --seeds <seed file of record> "
            f"--run-dir {rdir}`"
        )
    for row, judgment in zip(rows, judgments):
        # rows derived before analysis_rows() carried the instrument digest take it from the bound judgment they
        # were derived from (checked equal above wherever the row does carry it)
        if "prompt_file_digest" not in row:
            row["prompt_file_digest"] = judgment.get("prompt_file_digest")
    # the run is part of the experimental cell (tree epochs restart at 1 in every run); analysis rows do not carry
    # it, so it is taken from the manifest, and a row that carries a different one is refused
    foreign = sum(1 for row in rows if row.get("run_id") not in (None, run_id))
    if foreign:
        raise InputRefusalError(f"Run '{run_id}' analysis_rows.jsonl has {foreign} rows naming another run_id")
    for row in rows:
        row["run_id"] = run_id

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

    rows, n_superseded = collapse_retries(rows)
    return manifest, rows, n_superseded


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
    rows_by_arm: Mapping[str, Mapping[ExchangeKey, dict[str, Any]]],
    exchanges: Sequence[ExchangeKey],
    scale: list[str] | None,
    errors_by_arm: Mapping[str, Mapping[ExchangeKey, str]] | None = None,
) -> ContrastResult:
    """Analyzes a single pairwise contrast (arm_A vs arm_B) across all exchanges of all cells.

    Joins on (run_id, epoch, branch_id, exchange_index) with final_in_exchange=True.
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

    for xk in sorted(exchanges):
        run_id, epoch, branch_id, ex = xk
        row_A = rows_A.get(xk)
        row_B = rows_B.get(xk)
        where = f"run '{run_id}' epoch {epoch} branch '{branch_id}': exchange {ex} refused"

        refusal_reason: str | None = None
        val_A: str | None = None
        val_B: str | None = None

        err_A = errors_by_arm.get(arm_A, {}).get(xk) if errors_by_arm else None
        err_B = errors_by_arm.get(arm_B, {}).get(xk) if errors_by_arm else None

        if err_A or err_B:
            err_parts = [e for e in (err_A, err_B) if e]
            refusal_reason = f"{where}: {'; '.join(err_parts)}"
        elif row_A is None and row_B is None:
            refusal_reason = f"{where}: neither arm '{arm_A}' nor '{arm_B}' has an eligible row"
        elif row_A is None:
            refusal_reason = f"{where}: arm '{arm_A}' has no eligible row"
        elif row_B is None:
            refusal_reason = f"{where}: arm '{arm_B}' has no eligible row"
        else:
            problems = [p for p in (_row_problem(arm_A, row_A), _row_problem(arm_B, row_B)) if p]
            if not problems and scale is not None:
                problems = [
                    f"arm '{arm}' value {str(row['value'])!r} is not on the registered ordinal scale"
                    for arm, row in ((arm_A, row_A), (arm_B, row_B))
                    if str(row["value"]) not in scale
                ]
            if problems:
                refusal_reason = f"{where}: {', '.join(problems)}"
            else:
                val_A = str(row_A["value"])
                val_B = str(row_B["value"])

        if refusal_reason is not None:
            n_refused += 1
            refusals.append({"run_id": run_id, "epoch": epoch, "branch_id": branch_id, "exchange_index": ex,
                             "reason": refusal_reason})
            comparison_rows.append(
                ExchangeComparisonRow(
                    run_id=run_id,
                    epoch=epoch,
                    branch_id=branch_id,
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
                    run_id=run_id,
                    epoch=epoch,
                    branch_id=branch_id,
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
    *,
    tier_rubric_digest: str | None,
) -> SeedAnalysis:
    """Analyzes all judged dimensions and tier instruments for one seed.

    `tier_rubric_digest` is the loaded rubric's canonical digest (`judge_runner.rubric_digest`): a final
    tier row that recorded any other digest was graded on a different scale and its exchange is refused by
    name. It must be passed explicitly; None is only for a caller that has verified the digest itself.

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

    # Group rows by (run_id, epoch, branch_id, exchange_index): each arm has at most one final row per exchange
    # within one cell, while several epochs, runs or branches legitimately give it one each (Codex F1 on PR #30).
    # dim_data: dim_key -> arm -> exchange key -> row (only final_in_exchange=True rows)
    dim_data: dict[str, dict[str, dict[ExchangeKey, dict[str, Any]]]] = {}
    # dim_errors: dim_key -> arm -> exchange key -> refusal message
    dim_errors: dict[str, dict[str, dict[ExchangeKey, str]]] = {}
    dim_kinds: dict[str, str] = {}
    # the exchanges each dimension was judged at, in any arm: the denominator for that dimension's contrasts. A
    # seed-wide union charged every dimension with exchanges it is never planned at (the contextual tier starts at
    # the second assistant message, so exchange 1 was reported as a refusal; Codex F6 on PR #30).
    dim_exchanges: dict[str, set[ExchangeKey]] = {}

    for r in seed_rows:
        key = r.get("key")
        arm = r.get("arm")
        ex = r.get("exchange_index")
        # arm, key, the cell fields and an integer exchange_index are guaranteed by _malformed_row_problems above
        xk: ExchangeKey = (r["run_id"], r["epoch"], r["branch_id"], ex)
        dim_exchanges.setdefault(key, set()).add(xk)

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
            dim_errors[key][arm][xk] = err
            dim_data[key][arm].pop(xk, None)
            continue
        elif not isinstance(r["final_in_exchange"], bool):
            err = (
                f"arm '{arm}' row (turn {turn_id}) in exchange {ex} has non-boolean 'final_in_exchange': "
                f"{r['final_in_exchange']!r}"
            )
            dim_errors[key][arm][xk] = err
            dim_data[key][arm].pop(xk, None)
            continue

        # Invariant 2: Intermediate assistant turns (final_in_exchange=False) are excluded from exchange outcomes.
        if not r["final_in_exchange"]:
            continue

        # Invariant 3: Two final rows in one exchange for one arm must be refused by name, not resolved to latest turn.
        if xk in dim_errors[key][arm]:
            continue

        # Invariant 4: a tier row graded under another rubric is not on the loaded scale; a later edit to the draft
        # rubric would otherwise reinterpret historical rows under the new tiers (Codex F3 on PR #30).
        if (tier_rubric_digest is not None and r.get("kind") == "tier"
                and r.get("prompt_file_digest") != tier_rubric_digest):
            dim_errors[key][arm][xk] = (
                f"arm '{arm}' tier row (turn {turn_id}) in exchange {ex} was judged under rubric digest "
                f"{r.get('prompt_file_digest')!r}, not the loaded rubric's {tier_rubric_digest!r}"
            )
            dim_data[key][arm].pop(xk, None)
            continue

        if xk in dim_data[key][arm]:
            existing = dim_data[key][arm][xk]
            prev_turn = (
                existing.get("turn_id")
                if existing.get("turn_id") is not None
                else existing.get("assistant_turn_index", "unknown")
            )
            err = (
                f"arm '{arm}' has multiple rows with final_in_exchange=True in exchange {ex} "
                f"(turns {prev_turn} and {turn_id})"
            )
            dim_errors[key][arm][xk] = err
            dim_data[key][arm].pop(xk, None)
            continue

        dim_data[key][arm][xk] = r

    analyzed_dimensions: dict[str, DimensionAnalysis] = {}
    all_dim_keys = sorted(set(dim_data.keys()) | set(dim_errors.keys()))

    for key in all_dim_keys:
        arm_rows = dim_data.get(key, {})
        arm_errors = dim_errors.get(key, {})
        kind = dim_kinds.get(key, "outcome")
        exchanges = sorted(dim_exchanges.get(key, set()))
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

    if not rubric_file.is_file():
        raise FileNotFoundError(f"Advice rubric file not found: {rubric_file}")
    loaded_rubric_digest = rubric_digest(load_json(rubric_file))

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
    tier_rubric_digests: dict[str, dict[str, int]] = {}
    superseded_retry_rows: dict[str, int] = {}
    judgments_digests: dict[str, str] = {}
    analysis_rows_digests: dict[str, str] = {}

    for rdir in run_dirs:
        manifest, rows, n_superseded = load_run_rows(rdir, outcome_registry_path=outcomes_file)
        run_id = manifest.get("run_id") or str(rdir)
        if run_id in manifest_outcome_digests:
            raise InputRefusalError(
                f"run '{run_id}' is given twice; its rows would be paired against themselves as a second cell"
            )
        if manifest.get("run_id"):
            run_ids.append(manifest["run_id"])

        manifest_outcome_digests[run_id] = manifest.get("framework", {}).get("outcome_registry_sha256", "")
        tier_rubric_digests[run_id] = dict(sorted(Counter(
            str(r.get("prompt_file_digest")) for r in rows if r.get("kind") == "tier"
        ).items()))

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

        superseded_retry_rows[run_id] = n_superseded
        judgments_digests[run_id] = manifest["artifacts"]["judgments_sha256"]
        analysis_rows_digests[run_id] = sha256_file(Path(rdir) / "analysis_rows.jsonl")
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
        analyzed_seeds[sid] = analyze_seed(sid, srows, active_scales, tier_rubric_digest=loaded_rubric_digest)

    loaded_outcome_sha = sha256_file(outcomes_file) if outcomes_file.is_file() else ""
    loaded_rubric_sha = sha256_file(rubric_file)

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
        rubric_canonical_digest=loaded_rubric_digest,
        tier_rubric_digests=tier_rubric_digests,
        superseded_retry_rows=superseded_retry_rows,
        judgments_sha256=judgments_digests,
        analysis_rows_sha256=analysis_rows_digests,
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
    prov = report.provenance
    lines: list[str] = [
        f"# {HEADER_NOTE}",
        "",
        f"**Ordinal dimensions ({len(report.ordinal_dimensions)})**: {', '.join(report.ordinal_dimensions) if report.ordinal_dimensions else 'none'}",
        f"**Nominal dimensions ({len(report.nominal_dimensions)})**: {', '.join(report.nominal_dimensions) if report.nominal_dimensions else 'none'}",
        "",
        "## Provenance",
        # Every digest is printed in full: the default output must identify the exact inputs by itself
        # (Codex F11 on PR #30); the --json output carries the same fields.
        f"- **Run IDs**: {', '.join(prov.run_ids) or 'None'}",
        f"- **Manifest identities**: {', '.join(prov.manifest_identity_sha256) or 'None'}",
        f"- **Engine commits**: {', '.join(prov.engine_commits) or 'None'}",
        f"- **Judge of record**: {', '.join(prov.judge_of_record) or 'None'}",
        f"- **Outcome registry**: `{prov.outcome_registry_path}` (sha256 `{prov.outcome_registry_sha256}`)",
        f"- **Rubric**: `{prov.rubric_path}` (sha256 `{prov.rubric_sha256}`; canonical digest "
        f"`{prov.rubric_canonical_digest}`, checked against every tier judgment's recorded digest)",
        f"- **Seeds analyzed**: {len(report.seeds)}",
        "",
        "### Per run",
    ]
    for rid in prov.manifest_outcome_registry_sha256:
        tiers = ", ".join(f"`{d}` {n}" for d, n in prov.tier_rubric_digests.get(rid, {}).items()) or "none"
        lines.append(
            f"- `{rid}`: manifest outcome registry sha256 `{prov.manifest_outcome_registry_sha256[rid]}`; "
            f"judgments.jsonl sha256 `{prov.judgments_sha256.get(rid)}` (bound); "
            f"analysis_rows.jsonl sha256 `{prov.analysis_rows_sha256.get(rid)}`; "
            f"tier rows by recorded rubric digest: {tiers}; "
            f"superseded retry attempts (a null judgment replaced by a later attempt under the same key): "
            f"{prov.superseded_retry_rows.get(rid, 0)}"
        )
    lines += ["", "### Seed digests"]
    lines += [f"- `{sid}`: `{sha}`" for sid, sha in sorted(prov.seed_digests.items())] or ["- None recorded"]
    lines.append("")

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
                        lines.append(f"- {ref['reason']}")
                    lines.append("")

                lines.append(f"| Run | Epoch | Branch | Exchange | `{contrast.arm_A}` | `{contrast.arm_B}` | Comparison |")
                lines.append("|---|---|---|---|---|---|---|")
                for r in contrast.rows:
                    val_a = r.arm_A_value or "—"
                    val_b = r.arm_B_value or "—"
                    comp = "refused" if r.refusal_reason else r.comparison
                    lines.append(
                        f"| {r.run_id} | {r.epoch} | {r.branch_id} | {r.exchange_index} | {val_a} | {val_b} | {comp} |"
                    )
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
        help="One or more Petri audit run directories (each must contain manifest.json and analysis_rows.jsonl)",
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
