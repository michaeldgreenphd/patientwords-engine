"""Tests for three-arm analysis (scripts/petri_three_arm.py).

Covers:
- Tool-calling arm with intermediate tool turns (asserts only final_in_exchange is compared)
- Arm missing an exchange (asserts clean refusal of that exchange by name)
- not_applicable rows (asserts counted as not compared rather than dropped or treated as a category level)
- pw-petri-w2-identity-register (2x3 arms, asserts within-identity and within-register contrasts)
- Wave 1 refusal (asserts clean refusal on run_35351739969_1)
- Ordinal direction mapping (upgrade, downgrade, same loaded from data files)
- Provenance and header invariants (no CIs or p-values)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.petri_audit.judge_runner import rubric_digest
from scripts.petri_three_arm import (
    DEFAULT_ADVICE_RUBRIC,
    DEFAULT_OUTCOME_REGISTRY,
    HEADER_NOTE,
    InputRefusalError,
    RegistryMismatchError,
    Wave1RefusalError,
    analyze_run_directories,
    analyze_seed,
    format_markdown_summary,
    load_ordinal_scales,
    main,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
WAVE_1_RUN_DIR = ROOT / "data" / "petri" / "runs" / "run_35351739969_1"


@pytest.fixture(scope="module")
def ordinal_scales() -> dict[str, list[str]]:
    return load_ordinal_scales()


JUDGE = "claude-haiku-4-5"
TIERS = load_ordinal_scales()["response_only"]
RUBRIC_DIGEST = rubric_digest(json.loads(DEFAULT_ADVICE_RUBRIC.read_text(encoding="utf-8")))


def _write_run(
    root: Path,
    name: str,
    rows: list[dict],
    *,
    seed_digests: dict[str, str] | None = None,
    registry_sha: str | None = None,
    manifest_update=None,
    write_analysis_rows: bool = True,
) -> Path:
    """A synthetic run directory shaped like the lane's output: the analysis rows as
    judge_runner.analysis_rows() derives them, the judgments they came from (bound in the
    manifest by digest), and one manifest tree per (seed, arm, epoch). Synthetic rows only."""
    run_dir = root / name
    run_dir.mkdir()
    full: list[dict] = []
    for r in rows:
        a = {"epoch": 1, "branch_id": "root", "judge_model": JUDGE, "not_applicable_reason": None,
             "judge_error": None, "shared_prefix": False, **r}
        a.setdefault("condition_id", a["arm"])
        a.setdefault("tree_id", f"{name}:{a['seed_id']}:{a['arm']}:{a['epoch']}")
        a.setdefault("conversation_id", f"{a['tree_id']}:{a['branch_id']}")
        a.setdefault("turn_id", 2 * a["exchange_index"])
        a.setdefault("assistant_turn_index", a["turn_id"] // 2)
        a.setdefault("row_eligible", a.get("value") is not None and a.get("value") != "not_applicable")
        a.setdefault("prompt_file_digest", RUBRIC_DIGEST if a.get("kind") == "tier" else "0123456789ab")
        full.append(a)
    judgments = []
    for a in full:
        j = {f: a.get(f) for f in ("conversation_id", "turn_id", "assistant_turn_index", "exchange_index",
                                   "final_in_exchange", "kind", "key", "judge_model", "not_applicable_reason",
                                   "prompt_file_digest", "seed_id", "condition_id", "branch_id", "tree_id", "epoch")}
        re_read = a.get("value_source") == "leading_line_at_analysis"
        j["value"] = None if re_read else a.get("value")
        j["judge_error"] = "synthetic out-of-vocabulary answer" if re_read else a.get("judge_error")
        judgments.append(j)
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(j) + "\n" for j in judgments), encoding="utf-8")
    trees: dict[str, dict] = {}
    for a in full:
        tree = trees.setdefault(a["tree_id"], {"tree_id": a["tree_id"], "seed_id": a["seed_id"], "arm": a["arm"],
                                               "epoch": a["epoch"], "branches": []})
        if all(b["conversation_id"] != a["conversation_id"] for b in tree["branches"]):
            tree["branches"].append({"branch_id": a["branch_id"], "condition_id": a["condition_id"],
                                     "conversation_id": a["conversation_id"], "branched_from_turn_id": None})
    manifest = {
        "run_id": name,
        "framework": {"outcome_registry_sha256": registry_sha or sha256_file(DEFAULT_OUTCOME_REGISTRY)},
        "chain": {"identity_sha256": f"ident-{name}"},
        "adapter": {"engine_sha": f"commit-{name}"},
        "seeds": [{"seed_id": s, "seed_sha256": (seed_digests or {}).get(s, "5" * 64)}
                  for s in sorted({a["seed_id"] for a in full})],
        "trees": list(trees.values()),
        "artifacts": {"judgments_path": f"{name}/judgments.jsonl",
                      "judgments_sha256": sha256_file(run_dir / "judgments.jsonl"),
                      "judge_of_record": {"judge_model": JUDGE}},
    }
    if manifest_update is not None:
        manifest_update(manifest)
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if write_analysis_rows:
        (run_dir / "analysis_rows.jsonl").write_text("".join(json.dumps(a) + "\n" for a in full), encoding="utf-8")
    return run_dir


def _cells(rows: list[dict]) -> list[dict]:
    """Direct analyze_seed callers state each row's experimental cell; these tests use one cell unless
    a row names its own."""
    return [{"run_id": "run-1", "epoch": 1, "branch_id": "root", **r} for r in rows]


def _three_arms(seed_id: str = "s1", exchanges=(1,), value=None, **extra) -> list[dict]:
    """One final response_only tier row per arm and exchange."""
    return [{"seed_id": seed_id, "arm": arm, "exchange_index": ex, "final_in_exchange": True, "kind": "tier",
             "key": "response_only", "value": TIERS[1] if value is None else value, **extra}
            for ex in exchanges for arm in ("colloquial", "clinical", "lay_careful")]


# ------------------------------------------------------------------ Wave 1 Refusal


def test_wave_1_run_cleanly_refuses_because_two_arm_and_null_exchange():
    """Wave 1 runs had only two arms and exchange_index is null on those rows.

    Quotes docs/petri_wave2_handoff.md section 6 on exchange_index.
    """
    assert WAVE_1_RUN_DIR.is_dir(), f"Expected wave 1 run directory at {WAVE_1_RUN_DIR}"

    with pytest.raises(Wave1RefusalError) as exc_info:
        analyze_run_directories([WAVE_1_RUN_DIR])

    msg = str(exc_info.value)
    assert "Wave-1 rows cannot be re-keyed from themselves" in msg
    assert "docs/petri_wave2_handoff.md section 6" in msg
    assert "exchange_index does not appear in data/petri/runs/run_35351739969_1/analysis_rows.jsonl" in msg
    assert "missing lay_careful" in msg


def test_wave_1_run_cli_returns_refusal_exit_code(capsys):
    """CLI returns exit code 2 when refusing a Wave 1 run."""
    code = main(["--run-dir", str(WAVE_1_RUN_DIR)])
    assert code == 2

    captured = capsys.readouterr()
    assert "REFUSED: Wave-1 rows cannot be re-keyed from themselves" in captured.err


# ------------------------------------------------- Tool-calling & final_in_exchange


def test_tool_calling_arm_compares_only_final_in_exchange(ordinal_scales):
    """When a tool-calling arm has multiple assistant rows sharing an exchange_index,

    only final_in_exchange=True is compared to avoid one-to-many pairing.
    """
    rows = [
        # Arm: colloquial has 2 assistant rows in exchange 1 (turn 2 is tool call, turn 4 is final)
        {
            "seed_id": "pw-petri-w2-tool-clarify",
            "arm": "colloquial",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": False,
            "kind": "tier",
            "key": "response_only",
            "value": "self_care",
            "row_eligible": True,
        },
        {
            "seed_id": "pw-petri-w2-tool-clarify",
            "arm": "colloquial",
            "exchange_index": 1,
            "turn_id": 4,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
        # Arm: clinical has 1 final row in exchange 1
        {
            "seed_id": "pw-petri-w2-tool-clarify",
            "arm": "clinical",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
        # Arm: lay_careful has 1 final row in exchange 1
        {
            "seed_id": "pw-petri-w2-tool-clarify",
            "arm": "lay_careful",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "routine",
            "row_eligible": True,
        },
    ]

    analysis = analyze_seed("pw-petri-w2-tool-clarify", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["response_only"].contrasts["colloquial_vs_clinical"]

    # Exactly 1 comparison row for exchange 1
    assert len(contrast.rows) == 1
    row = contrast.rows[0]
    assert row.exchange_index == 1
    # arm A (colloquial) should be "urgent" (turn 4, final_in_exchange=True), NOT "self_care" (turn 2)
    assert row.arm_A_value == "urgent"
    assert row.arm_B_value == "urgent"
    assert row.same_or_different is True
    assert row.comparison == "same"

    assert contrast.counts.n_compared == 1
    assert contrast.counts.n_same == 1
    assert contrast.counts.n_differing == 0
    assert contrast.counts.n_refused == 0


def test_row_missing_final_in_exchange_is_refused_by_name(ordinal_scales):
    """A row missing final_in_exchange must be refused by name, not defaulted to True."""
    rows = [
        # Arm colloquial is MISSING final_in_exchange
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "colloquial",
            "exchange_index": 1,
            "turn_id": 2,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "clinical",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "lay_careful",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
    ]

    analysis = analyze_seed("pw-petri-w2-test", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["response_only"].contrasts["colloquial_vs_clinical"]

    assert contrast.counts.n_exchanges_total == 1
    assert contrast.counts.n_compared == 0
    assert contrast.counts.n_refused == 1

    assert len(contrast.refusals) == 1
    refusal = contrast.refusals[0]
    assert refusal["exchange_index"] == 1
    assert "arm 'colloquial' row (turn 2) in exchange 1 missing 'final_in_exchange'" in refusal["reason"]

    row_0 = contrast.rows[0]
    assert row_0.comparison == "refused"
    assert row_0.same_or_different is None
    assert row_0.refusal_reason == refusal["reason"]


def test_two_final_rows_in_one_exchange_for_one_arm_refused_by_name(ordinal_scales):
    """Two final rows in one exchange for one arm must be refused by name, not resolved to latest turn."""
    rows = [
        # Arm colloquial has TWO rows with final_in_exchange=True in exchange 1
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "colloquial",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "routine",
            "row_eligible": True,
        },
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "colloquial",
            "exchange_index": 1,
            "turn_id": 4,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "clinical",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
        {
            "seed_id": "pw-petri-w2-test",
            "arm": "lay_careful",
            "exchange_index": 1,
            "turn_id": 2,
            "final_in_exchange": True,
            "kind": "tier",
            "key": "response_only",
            "value": "urgent",
            "row_eligible": True,
        },
    ]

    analysis = analyze_seed("pw-petri-w2-test", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["response_only"].contrasts["colloquial_vs_clinical"]

    assert contrast.counts.n_exchanges_total == 1
    assert contrast.counts.n_compared == 0
    assert contrast.counts.n_refused == 1

    assert len(contrast.refusals) == 1
    refusal = contrast.refusals[0]
    assert refusal["exchange_index"] == 1
    assert "arm 'colloquial' has multiple rows with final_in_exchange=True in exchange 1 (turns 2 and 4)" in refusal["reason"]

    row_0 = contrast.rows[0]
    assert row_0.comparison == "refused"
    assert row_0.same_or_different is None
    assert row_0.refusal_reason == refusal["reason"]


@pytest.mark.parametrize("broken", [
    {"exchange_index": None},
    {"exchange_index": "2"},
    {"arm": None},
    {"key": ""},
])
def test_partially_malformed_rows_are_refused_not_skipped(ordinal_scales, broken):
    """One malformed row among valid ones used to be skipped silently (only an all-null file was
    refused), so the report completed with reduced coverage. It is now refused by name with a
    count (Codex F5 on PR #30)."""
    base = {"seed_id": "s1", "final_in_exchange": True, "kind": "tier", "key": "response_only",
            "value": "v", "row_eligible": True}
    rows = [{**base, "arm": arm, "exchange_index": 1, "turn_id": 2}
            for arm in ("colloquial", "clinical", "lay_careful")]
    rows.append({**base, "arm": "clinical", "exchange_index": 2, "turn_id": 4, **broken})

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_seed("s1", _cells(rows), ordinal_scales, tier_rubric_digest=None)

    msg = str(exc_info.value)
    assert "1 of 4 rows cannot be joined and are refused, not skipped" in msg
    assert "turn 4" in msg
    assert f"lacks {next(iter(broken))}" in msg


def test_rows_without_seed_id_are_refused_not_skipped(tmp_path, capsys):
    """A row with no seed_id used to be dropped before grouping; it is refused with a count."""
    rows = _three_arms()
    rows.append({**_three_arms(exchanges=(2,))[1], "seed_id": ""})
    run_dir = _write_run(tmp_path, "run-no-seed", rows)

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir])
    assert "1 of 4 rows carry no seed_id and are refused, not skipped" in str(exc_info.value)

    assert main(["--run-dir", str(run_dir)]) == 2
    assert "REFUSED: 1 of 4 rows carry no seed_id" in capsys.readouterr().err


# --------------------------------------------------------- Missing Exchange Refusal


def test_missing_exchange_refused_by_name(ordinal_scales):
    """An arm missing an exchange must be refused by name, never silently dropped."""
    rows = [
        # Exchange 1 present in all 3 arms
        {"seed_id": "pw-petri-w2-reassurance-decay", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "pw-petri-w2-reassurance-decay", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "pw-petri-w2-reassurance-decay", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        # Exchange 2 present in colloquial and clinical, but MISSING in lay_careful
        {"seed_id": "pw-petri-w2-reassurance-decay", "arm": "colloquial", "exchange_index": 2, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "self_care", "row_eligible": True},
        {"seed_id": "pw-petri-w2-reassurance-decay", "arm": "clinical", "exchange_index": 2, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "self_care", "row_eligible": True},
    ]

    analysis = analyze_seed("pw-petri-w2-reassurance-decay", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    dim = analysis.dimensions["response_only"]

    # colloquial_vs_clinical has both exchanges present
    c_estimand = dim.contrasts["colloquial_vs_clinical"]
    assert c_estimand.counts.n_compared == 2
    assert c_estimand.counts.n_refused == 0

    # lay_careful_vs_colloquial is missing exchange 2 in lay_careful
    c_orth = dim.contrasts["lay_careful_vs_colloquial"]
    assert c_orth.counts.n_exchanges_total == 2
    assert c_orth.counts.n_compared == 1
    assert c_orth.counts.n_refused == 1

    assert len(c_orth.refusals) == 1
    refusal = c_orth.refusals[0]
    assert refusal["exchange_index"] == 2
    assert "exchange 2 refused: arm 'lay_careful' has no eligible row" in refusal["reason"]

    # In the table, exchange 2 is explicitly recorded as refused
    row_2 = next(r for r in c_orth.rows if r.exchange_index == 2)
    assert row_2.comparison == "refused"
    assert row_2.same_or_different is None
    assert row_2.refusal_reason == refusal["reason"]


# ------------------------------------------------------------- not_applicable rows


def test_not_applicable_rows_counted_as_uncompared_never_dropped_or_compared_as_level(ordinal_scales):
    """not_applicable rows must be counted as not compared / refused,

    never dropped silently and never matched as an agreement level.
    """
    rows = [
        # Exchange 1: both valid
        {"seed_id": "pw-petri-w2-referral-specificity", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "assertion_handling", "value": "qualified_or_uncertain", "row_eligible": True},
        {"seed_id": "pw-petri-w2-referral-specificity", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "assertion_handling", "value": "qualified_or_uncertain", "row_eligible": True},
        {"seed_id": "pw-petri-w2-referral-specificity", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "assertion_handling", "value": "corrected_or_rejected", "row_eligible": True},
        # Exchange 2: colloquial has not_applicable, clinical has not_applicable
        {"seed_id": "pw-petri-w2-referral-specificity", "arm": "colloquial", "exchange_index": 2, "final_in_exchange": True, "kind": "outcome", "key": "assertion_handling", "value": "not_applicable", "not_applicable_reason": "before assertion turn", "row_eligible": True},
        {"seed_id": "pw-petri-w2-referral-specificity", "arm": "clinical", "exchange_index": 2, "final_in_exchange": True, "kind": "outcome", "key": "assertion_handling", "value": "not_applicable", "not_applicable_reason": "before assertion turn", "row_eligible": True},
        {"seed_id": "pw-petri-w2-referral-specificity", "arm": "lay_careful", "exchange_index": 2, "final_in_exchange": True, "kind": "outcome", "key": "assertion_handling", "value": "accepted", "row_eligible": True},
    ]

    analysis = analyze_seed("pw-petri-w2-referral-specificity", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["assertion_handling"].contrasts["colloquial_vs_clinical"]

    assert contrast.counts.n_exchanges_total == 2
    assert contrast.counts.n_compared == 1
    assert contrast.counts.n_same == 1
    assert contrast.counts.n_differing == 0
    assert contrast.counts.n_refused == 1

    # Exchange 2 must NOT be counted as same (even though both arms are not_applicable)
    row_2 = next(r for r in contrast.rows if r.exchange_index == 2)
    assert row_2.same_or_different is None
    assert row_2.comparison == "refused"
    assert "not_applicable" in str(row_2.refusal_reason)
    assert "before assertion turn" in str(row_2.refusal_reason)


def test_repository_shaped_not_applicable_rows_keep_their_reason(ordinal_scales):
    """judge_runner.analysis_rows sets row_eligible False on every not_applicable row, so
    the not_applicable test must run before the generic ineligibility test or the reason is lost
    (Codex F7 on PR #30)."""
    base = {"seed_id": "s1", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome",
            "key": "assertion_handling"}
    rows = [
        {**base, "arm": "colloquial", "value": "not_applicable", "not_applicable_reason": "gate reason A",
         "row_eligible": False},
        {**base, "arm": "clinical", "value": None, "judge_error": "synthetic parse error", "row_eligible": False},
        {**base, "arm": "lay_careful", "value": "not_applicable", "not_applicable_reason": "gate reason A",
         "row_eligible": False},
    ]

    dim = analyze_seed("s1", _cells(rows), ordinal_scales, tier_rubric_digest=None).dimensions["assertion_handling"]

    mixed = dim.contrasts["colloquial_vs_clinical"].refusals[0]["reason"]
    assert "arm 'colloquial' is not_applicable (gate reason A)" in mixed
    assert "arm 'clinical' ineligible (synthetic parse error)" in mixed

    both_na = dim.contrasts["lay_careful_vs_colloquial"].refusals[0]["reason"]
    assert "arm 'lay_careful' is not_applicable (gate reason A)" in both_na
    assert "arm 'colloquial' is not_applicable (gate reason A)" in both_na
    assert "ineligible" not in both_na


# ------------------------------------------------- 2x3 Identity Crossed Contrasts


def test_identity_seed_emits_within_identity_and_within_register_contrasts(ordinal_scales):
    """pw-petri-w2-identity-register (2x3 arms) must emit both:

    - 3 pairwise contrasts within each identity (patient, clinician)
    - the identity contrast within each register (colloquial, clinical, lay_careful)
    Total: 6 + 3 = 9 contrasts.
    """
    rows = []
    # 6 arms, 2 exchanges each
    arms = [
        "patient_colloquial", "patient_clinical", "patient_lay_careful",
        "clinician_colloquial", "clinician_clinical", "clinician_lay_careful",
    ]
    for arm in arms:
        for ex in (1, 2):
            val = "urgent" if "clinical" in arm else "routine"
            rows.append({
                "seed_id": "pw-petri-w2-identity-register",
                "arm": arm,
                "exchange_index": ex,
                "final_in_exchange": True,
                "kind": "tier",
                "key": "response_only",
                "value": val,
                "row_eligible": True,
            })

    analysis = analyze_seed("pw-petri-w2-identity-register", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    assert analysis.is_identity_seed is True
    assert set(analysis.arms_present) == set(arms)

    dim = analysis.dimensions["response_only"]
    contrasts = dim.contrasts

    expected_contrasts = [
        # Within patient
        "patient:colloquial_vs_clinical",
        "patient:lay_careful_vs_colloquial",
        "patient:lay_careful_vs_clinical",
        # Within clinician
        "clinician:colloquial_vs_clinical",
        "clinician:lay_careful_vs_colloquial",
        "clinician:lay_careful_vs_clinical",
        # Identity contrast within each register
        "colloquial:patient_vs_clinician",
        "clinical:patient_vs_clinician",
        "lay_careful:patient_vs_clinician",
    ]

    for ec in expected_contrasts:
        assert ec in contrasts, f"Missing expected contrast {ec}"
        c = contrasts[ec]
        assert c.counts.n_compared == 2
        assert c.counts.n_refused == 0


# ---------------------------------------------------- Ordinal Scales and Direction


def test_ordinal_scale_direction_upgrade_downgrade(ordinal_scales):
    """Ordinal dimensions report upgrade/downgrade against registered order."""
    # Scale from rubric: self_care < routine < urgent < emergency
    rows = [
        # Exchange 1: colloquial urgent vs clinical routine -> upgrade (urgent > routine)
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "routine", "row_eligible": True},
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "self_care", "row_eligible": True},
        # Exchange 2: colloquial self_care vs clinical emergency -> downgrade (self_care < emergency)
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "colloquial", "exchange_index": 2, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "self_care", "row_eligible": True},
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "clinical", "exchange_index": 2, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "emergency", "row_eligible": True},
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "lay_careful", "exchange_index": 2, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "self_care", "row_eligible": True},
        # Exchange 3: colloquial routine vs clinical routine -> same
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "colloquial", "exchange_index": 3, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "routine", "row_eligible": True},
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "clinical", "exchange_index": 3, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "routine", "row_eligible": True},
        {"seed_id": "pw-petri-w2-tool-clarify", "arm": "lay_careful", "exchange_index": 3, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "routine", "row_eligible": True},
    ]

    analysis = analyze_seed("pw-petri-w2-tool-clarify", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["response_only"].contrasts["colloquial_vs_clinical"]

    assert contrast.is_ordinal is True
    assert contrast.counts.n_compared == 3
    assert contrast.counts.n_same == 1
    assert contrast.counts.n_differing == 2
    assert contrast.counts.n_upgrade == 1    # Exchange 1: urgent > routine
    assert contrast.counts.n_downgrade == 1  # Exchange 2: self_care < emergency
    assert contrast.counts.n_refused == 0

    assert contrast.rows[0].comparison == "upgrade"
    assert contrast.rows[0].same_or_different is False
    assert contrast.rows[1].comparison == "downgrade"
    assert contrast.rows[1].same_or_different is False
    assert contrast.rows[2].comparison == "same"
    assert contrast.rows[2].same_or_different is True


def test_value_off_the_ordinal_scale_is_refused_by_name(ordinal_scales):
    """A value the configured ordinal scale does not list has no rank: the exchange is refused
    by name, never counted as a direction-less "different" (Codex F10 on PR #30)."""
    tiers = ordinal_scales["response_only"]
    base = {"seed_id": "s1", "final_in_exchange": True, "kind": "tier", "key": "response_only", "row_eligible": True}
    rows = [
        # exchange 1: one arm on the scale, one off it
        {**base, "arm": "colloquial", "exchange_index": 1, "value": tiers[0]},
        {**base, "arm": "clinical", "exchange_index": 1, "value": "value_not_on_scale"},
        {**base, "arm": "lay_careful", "exchange_index": 1, "value": tiers[0]},
        # exchange 2: both arms carry the same off-scale value, which is not "same" either
        {**base, "arm": "colloquial", "exchange_index": 2, "value": "value_not_on_scale"},
        {**base, "arm": "clinical", "exchange_index": 2, "value": "value_not_on_scale"},
        {**base, "arm": "lay_careful", "exchange_index": 2, "value": tiers[1]},
    ]

    contrast = analyze_seed("s1", _cells(rows), ordinal_scales, tier_rubric_digest=None).dimensions["response_only"].contrasts["colloquial_vs_clinical"]

    c = contrast.counts
    assert (c.n_compared, c.n_differing, c.n_same, c.n_refused) == (0, 0, 0, 2)
    assert c.n_upgrade + c.n_downgrade == c.n_differing
    assert "arm 'clinical' value 'value_not_on_scale' is not on the registered ordinal scale" in contrast.refusals[0]["reason"]
    assert "arm 'colloquial' value 'value_not_on_scale'" in contrast.refusals[1]["reason"]
    assert all(r.comparison == "refused" for r in contrast.rows)


def test_recommendation_specificity_ordinal_mapping():
    """When an ordinal scale is provided, contrasts report upgrade/downgrade against that scale."""
    custom_scales = {"recommendation_specificity": ["none", "generic_deferral", "specific"]}
    rows = [
        {"seed_id": "s1", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "specific", "row_eligible": True},
        {"seed_id": "s1", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "generic_deferral", "row_eligible": True},
        {"seed_id": "s1", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "none", "row_eligible": True},
    ]

    analysis = analyze_seed("s1", _cells(rows), custom_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["recommendation_specificity"].contrasts["colloquial_vs_clinical"]

    assert contrast.is_ordinal is True
    assert contrast.counts.n_upgrade == 1
    assert contrast.counts.n_downgrade == 0
    assert contrast.rows[0].comparison == "upgrade"


def test_dimensions_without_ordinal_declaration_default_to_nominal(ordinal_scales):
    """Dimensions not declared ordinal in data files are treated as nominal (same/different only)."""
    assert "recommendation_specificity" not in ordinal_scales

    rows = [
        {"seed_id": "s1", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "specific", "row_eligible": True},
        {"seed_id": "s1", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "generic_deferral", "row_eligible": True},
        {"seed_id": "s1", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "none", "row_eligible": True},
    ]

    analysis = analyze_seed("s1", _cells(rows), ordinal_scales, tier_rubric_digest=None)
    contrast = analysis.dimensions["recommendation_specificity"].contrasts["colloquial_vs_clinical"]

    assert contrast.is_ordinal is False
    assert contrast.counts.n_upgrade is None
    assert contrast.counts.n_downgrade is None
    assert contrast.counts.n_differing == 1
    assert contrast.rows[0].comparison == "different"


# ------------------------------------------------ Provenance & Markdown Output


def test_provenance_and_header_invariants(tmp_path):
    """Analysis report carries the required header and provenance block."""
    registry_sha = sha256_file(DEFAULT_OUTCOME_REGISTRY)
    run_dir = _write_run(tmp_path, "run-synth-123", _three_arms(), seed_digests={"s1": "e" * 64})

    report = analyze_run_directories([run_dir])

    assert report.header.startswith(HEADER_NOTE)
    assert "one epoch is structure, not an estimate" in report.header
    assert "no confidence intervals or p-values emitted" in report.header
    assert "Ordinal dimensions" in report.header
    assert "Nominal dimensions" in report.header

    prov = report.provenance
    assert prov.run_ids == ["run-synth-123"]
    assert prov.manifest_identity_sha256 == ["ident-run-synth-123"]
    assert prov.engine_commits == ["commit-run-synth-123"]
    assert prov.judge_of_record == [JUDGE]
    assert prov.seed_digests == {"s1": "e" * 64}
    assert prov.outcome_registry_sha256 == registry_sha
    assert prov.manifest_outcome_registry_sha256 == {"run-synth-123": registry_sha}
    assert prov.rubric_sha256 == sha256_file(DEFAULT_ADVICE_RUBRIC)
    assert prov.rubric_canonical_digest == RUBRIC_DIGEST
    assert prov.tier_rubric_digests == {"run-synth-123": {RUBRIC_DIGEST: 3}}

    md = format_markdown_summary(report)
    assert "# " + HEADER_NOTE in md
    assert "run-synth-123" in md
    assert f"- **Judge of record**: {JUDGE}" in md
    assert "- **Outcome registry**: `docs/framework/outcome_dimensions.draft.json`" in md
    assert "colloquial_vs_clinical" in md


def test_run_with_only_raw_judgments_is_refused_with_the_derivation_step(tmp_path, capsys):
    """judge_runner writes judgments.jsonl without `arm` (analysis_rows() adds it from the manifest), so
    reading raw judgments misreported every Wave-2 run as Wave 1. The fallback is gone: the run is refused
    with the command that derives the rows (Codex F4 on PR #30)."""
    run_dir = _write_run(tmp_path, "run-raw-only", _three_arms(), write_analysis_rows=False)
    judgments = (run_dir / "judgments.jsonl").read_text(encoding="utf-8")
    assert '"arm"' not in judgments  # the labels judge_runner puts on a judgment carry no arm

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir])
    msg = str(exc_info.value)
    assert "has no analysis_rows.jsonl" in msg
    assert "python -m scripts.petri_audit.cli analyze" in msg

    assert main(["--run-dir", str(run_dir)]) == 2
    assert "REFUSED: Run directory" in capsys.readouterr().err


def test_conflicting_seed_digests_across_runs_are_refused(tmp_path, capsys):
    """Two runs that record different digests for one seed_id would be pooled under that id while the
    provenance kept only the last digest; the analysis refuses instead (Codex F9 on PR #30)."""
    run_dirs = [_write_run(tmp_path, name, _three_arms(), seed_digests={"s1": seed_sha})
                for name, seed_sha in (("run-a", "a" * 64), ("run-b", "b" * 64))]

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories(run_dirs)
    msg = str(exc_info.value)
    assert "seed 's1'" in msg and "a" * 64 in msg and "b" * 64 in msg and "run-b" in msg

    assert main(["--run-dir", *map(str, run_dirs)]) == 2
    assert "REFUSED: seed 's1' has digest" in capsys.readouterr().err


# ------------------------------------------------ experimental cells (Codex F1)


def test_two_epochs_in_one_run_are_two_cells_not_duplicate_final_rows(tmp_path):
    """Codex's reproduction: epoch-1 and epoch-2 rows for each arm at exchange 1 used to collide on the
    arm/dimension/exchange key and be refused as duplicate final rows, yielding zero comparisons."""
    rows = [*_three_arms(epoch=1, value=TIERS[1]), *_three_arms(epoch=2, value=TIERS[2])]
    run_dir = _write_run(tmp_path, "run-two-epochs", rows)

    report = analyze_run_directories([run_dir])

    contrast = report.seeds["s1"].dimensions["response_only"].contrasts["colloquial_vs_clinical"]
    assert (contrast.counts.n_exchanges_total, contrast.counts.n_compared, contrast.counts.n_refused) == (2, 2, 0)
    assert [(r.run_id, r.epoch, r.branch_id, r.exchange_index) for r in contrast.rows] == [
        ("run-two-epochs", 1, "root", 1), ("run-two-epochs", 2, "root", 1)]
    assert [r.arm_A_value for r in contrast.rows] == [TIERS[1], TIERS[2]]


def test_same_seed_in_two_runs_is_two_cells(tmp_path):
    """Every run's trees restart at epoch 1, so combining run directories needs the run in the cell key."""
    run_dirs = [_write_run(tmp_path, name, _three_arms()) for name in ("run-a", "run-b")]

    report = analyze_run_directories(run_dirs)

    contrast = report.seeds["s1"].dimensions["response_only"].contrasts["colloquial_vs_clinical"]
    assert (contrast.counts.n_compared, contrast.counts.n_refused) == (2, 0)
    assert sorted(r.run_id for r in contrast.rows) == ["run-a", "run-b"]


def test_branches_are_separate_cells(ordinal_scales):
    """A branch shares its root's exchange ordinals; its rows pair only with the same branch of the other arm."""
    base = {"seed_id": "s1", "final_in_exchange": True, "kind": "tier", "key": "response_only", "exchange_index": 3}
    rows = [{**base, "arm": arm, "branch_id": branch, "value": TIERS[i]}
            for i, branch in enumerate(("root", "pressure_branch"))
            for arm in ("colloquial", "clinical", "lay_careful")]

    analysis = analyze_seed("s1", _cells(rows), ordinal_scales, tier_rubric_digest=None)

    contrast = analysis.dimensions["response_only"].contrasts["colloquial_vs_clinical"]
    assert (contrast.counts.n_compared, contrast.counts.n_same, contrast.counts.n_refused) == (2, 2, 0)
    assert {r.branch_id for r in contrast.rows} == {"root", "pressure_branch"}


def test_same_run_given_twice_is_refused(tmp_path):
    run_dir = _write_run(tmp_path, "run-twice", _three_arms())
    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir, run_dir])
    assert "run 'run-twice' is given twice" in str(exc_info.value)


# ------------------------------------------- derived rows authenticated (Codex F2)


def _append_judgment(run_dir: Path, *, rebind: bool) -> None:
    """What a resumed judging pass does: append a row to judgments.jsonl and, when it completes, rebind."""
    jpath = run_dir / "judgments.jsonl"
    rows = [json.loads(line) for line in jpath.read_text(encoding="utf-8").splitlines()]
    extra = {**rows[-1], "turn_id": rows[-1]["turn_id"] + 2, "exchange_index": rows[-1]["exchange_index"] + 1}
    jpath.write_text(jpath.read_text(encoding="utf-8") + json.dumps(extra) + "\n", encoding="utf-8")
    if rebind:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["artifacts"]["judgments_sha256"] = sha256_file(jpath)
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_stale_analysis_rows_after_a_resumed_pass_are_refused(tmp_path):
    """A resumed pass appends and rebinds judgments; analysis_rows.jsonl derived before it would silently omit
    the new judgments, so its row count is checked against the bound file (Codex F2 on PR #30)."""
    run_dir = _write_run(tmp_path, "run-stale", _three_arms())
    _append_judgment(run_dir, rebind=True)

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir])
    msg = str(exc_info.value)
    assert "analysis_rows.jsonl has 3 rows but the bound judgments.jsonl has 4" in msg
    assert "petri_audit.cli analyze" in msg


def test_judgments_changed_after_binding_are_refused(tmp_path):
    """Rows appended to judgments.jsonl that no completed pass bound are not a basis for analysis."""
    run_dir = _write_run(tmp_path, "run-unbound", _three_arms())
    _append_judgment(run_dir, rebind=False)

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir])
    assert "judgments.jsonl digests to" in str(exc_info.value)
    assert "not the bound" in str(exc_info.value)


def test_manifest_without_bound_judgments_is_refused(tmp_path):
    run_dir = _write_run(tmp_path, "run-no-binding", _three_arms(),
                         manifest_update=lambda m: m["artifacts"].pop("judgments_sha256"))
    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir])
    assert "manifest binds no judgments" in str(exc_info.value)


@pytest.mark.parametrize("field, edit", [
    ("value", lambda r: TIERS[0] if r["value"] != TIERS[0] else TIERS[1]),
    ("arm", lambda r: "lay_careful" if r["arm"] != "lay_careful" else "clinical"),
    ("exchange_index", lambda r: r["exchange_index"] + 1),
    ("row_eligible", lambda r: not r["row_eligible"]),
])
def test_edited_analysis_row_is_refused_by_line_and_field(tmp_path, field, edit):
    """A derived row edited after derivation no longer matches its judgment or the manifest tree."""
    run_dir = _write_run(tmp_path, "run-edited", _three_arms())
    apath = run_dir / "analysis_rows.jsonl"
    rows = [json.loads(line) for line in apath.read_text(encoding="utf-8").splitlines()]
    rows[1][field] = edit(rows[1])
    apath.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    with pytest.raises(InputRefusalError) as exc_info:
        analyze_run_directories([run_dir])
    assert f"line 2: {field}" in str(exc_info.value)


def test_leading_line_reread_of_a_null_judgment_is_accepted(tmp_path):
    """analysis_rows() re-reads an out-of-vocabulary outcome answer's first line; that row's value differs from
    its null judgment by design and is not a mismatch."""
    rows = _three_arms()
    rows[0] = {**rows[0], "value_source": "leading_line_at_analysis"}
    run_dir = _write_run(tmp_path, "run-reread", rows)

    report = analyze_run_directories([run_dir])
    assert report.seeds["s1"].dimensions["response_only"].contrasts["colloquial_vs_clinical"].counts.n_compared == 1


def test_retried_judgment_is_collapsed_to_its_latest_attempt_not_refused(tmp_path):
    """A resumed pass appends a replacement for a null judgment under the same judgment key, and
    analysis_rows() emits both attempts; the latest one is authoritative, so the exchange is compared,
    not refused as having two final rows, and the superseded attempt is counted (Codex F8 on PR #30)."""
    rows = _three_arms(value=TIERS[1])
    failed = {**rows[1], "value": None, "judge_error": "synthetic parse error", "row_eligible": False}
    rows.insert(1, failed)  # the clinical arm's first attempt failed; its retry follows later in the file
    run_dir = _write_run(tmp_path, "run-retry", rows)

    report = analyze_run_directories([run_dir])

    contrast = report.seeds["s1"].dimensions["response_only"].contrasts["colloquial_vs_clinical"]
    assert contrast.counts.n_compared == 1
    assert contrast.counts.n_refused == 0
    assert contrast.rows[0].arm_B_value == TIERS[1]
    assert report.provenance.superseded_retry_rows == {"run-retry": 1}
    assert "run-retry: 1" in format_markdown_summary(report)


def test_manifest_lacking_judge_of_record_is_refused_by_name(tmp_path):
    """A run directory whose manifest lacks artifacts.judge_of_record must be refused by name."""
    run_dir = _write_run(tmp_path, "run-synth-123", _three_arms(),
                         manifest_update=lambda m: m["artifacts"].pop("judge_of_record"))

    with pytest.raises(ValueError) as exc_info:
        analyze_run_directories([run_dir])

    msg = str(exc_info.value)
    assert "lacks artifacts.judge_of_record" in msg
    assert str(run_dir) in msg


def test_manifest_outcome_registry_digest_matching_proceeds(tmp_path):
    """A run whose manifest framework.outcome_registry_sha256 matches loaded registry proceeds."""
    registry_sha = sha256_file(DEFAULT_OUTCOME_REGISTRY)
    run_dir = _write_run(tmp_path, "run-match-001", _three_arms())

    report = analyze_run_directories([run_dir])
    assert report.provenance.outcome_registry_sha256 == registry_sha
    assert report.provenance.manifest_outcome_registry_sha256["run-match-001"] == registry_sha


def test_manifest_outcome_registry_digest_mismatch_refused_by_name(tmp_path, capsys):
    """A run whose manifest outcome registry digest differs from loaded registry is refused by name with non-zero exit."""
    bogus_sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    run_dir = _write_run(tmp_path, "run-mismatch-002", _three_arms(), registry_sha=bogus_sha)

    # Direct call raises RegistryMismatchError naming run id, path, and both digests
    with pytest.raises(RegistryMismatchError) as exc_info:
        analyze_run_directories([run_dir])

    msg = str(exc_info.value)
    assert "run-mismatch-002" in msg
    assert "outcome_dimensions.draft.json" in msg
    assert bogus_sha in msg
    assert sha256_file(DEFAULT_OUTCOME_REGISTRY) in msg

    # CLI returns non-zero exit code (2) and prints REFUSED naming the details
    exit_code = main(["--run-dir", str(run_dir)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "REFUSED: Run 'run-mismatch-002' manifest framework.outcome_registry_sha256" in captured.err
    assert bogus_sha in captured.err


def test_registry_without_ordinal_flags_reports_nominal_and_names_in_header(tmp_path):
    """When a registry without ordinal flags is intentionally loaded, dimensions report as nominal

    and the output header explicitly names which dimensions were treated as ordinal and which as nominal.
    """
    # Create an intentional registry without ordinal flags
    custom_registry = tmp_path / "custom_outcome_dimensions.json"
    registry_data = {
        "schema_version": "0.1",
        "dimensions": [
            {
                "id": "recommendation_specificity",
                "name": "Specificity of the recommendation",
                "values": ["none", "generic_deferral", "specific"],
                # ordinal flag intentionally omitted / false
                "ordinal": False,
            },
            {
                "id": "safety_netting_presence",
                "name": "Safety-netting presence",
                "values": ["absent", "generic", "specific"],
                "ordinal": False,
            },
        ],
    }
    custom_registry.write_text(json.dumps(registry_data), encoding="utf-8")

    outcome = {"seed_id": "s1", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome",
               "key": "recommendation_specificity"}
    rows = _three_arms() + [
        {**outcome, "arm": "colloquial", "value": "specific"},
        {**outcome, "arm": "clinical", "value": "generic_deferral"},
        {**outcome, "arm": "lay_careful", "value": "none"},
    ]
    run_dir = _write_run(tmp_path, "run-nominal-003", rows, registry_sha=sha256_file(custom_registry))

    report = analyze_run_directories([run_dir], outcome_registry_path=custom_registry)

    # In the seed analysis, recommendation_specificity is nominal
    s1 = report.seeds["s1"]
    rec_spec = s1.dimensions["recommendation_specificity"]
    assert rec_spec.is_ordinal is False
    assert rec_spec.scale is None

    contrast = rec_spec.contrasts["colloquial_vs_clinical"]
    assert contrast.is_ordinal is False
    assert contrast.scale is None
    assert contrast.counts.n_upgrade is None
    assert contrast.counts.n_downgrade is None
    assert contrast.counts.n_differing == 1
    assert contrast.rows[0].comparison == "different"

    # response_only from rubric is ordinal
    assert s1.dimensions["response_only"].is_ordinal is True

    # Output report lists them in ordinal_dimensions and nominal_dimensions
    assert "response_only" in report.ordinal_dimensions
    assert "recommendation_specificity" not in report.ordinal_dimensions
    assert "recommendation_specificity" in report.nominal_dimensions
    assert "response_only" not in report.nominal_dimensions

    # Output header explicitly names which dimensions were treated as ordinal and which as nominal
    assert "Ordinal dimensions (1): response_only" in report.header
    assert "Nominal dimensions (1): recommendation_specificity" in report.header

    # Markdown rendering also explicitly names both in its header
    md = format_markdown_summary(report)
    assert "**Ordinal dimensions (1)**: response_only" in md
    assert "**Nominal dimensions (1)**: recommendation_specificity" in md


def test_tier_row_judged_under_another_rubric_is_refused_by_exchange(tmp_path):
    """The manifest schema has no rubric field, so the rubric is verified against the canonical digest each
    tier judgment records: a row graded under another rubric is refused by name, and the provenance
    counts tier rows by recorded digest (Codex F3 on PR #30)."""
    rows = _three_arms(exchanges=(1, 2))
    rows[1] = {**rows[1], "prompt_file_digest": "ffffffffffff"}  # clinical, exchange 1
    run_dir = _write_run(tmp_path, "run-other-rubric", rows)

    report = analyze_run_directories([run_dir])

    contrast = report.seeds["s1"].dimensions["response_only"].contrasts["colloquial_vs_clinical"]
    assert (contrast.counts.n_compared, contrast.counts.n_refused) == (1, 1)
    reason = contrast.refusals[0]["reason"]
    assert "arm 'clinical' tier row (turn 2) in exchange 1 was judged under rubric digest 'ffffffffffff'" in reason
    assert f"not the loaded rubric's '{RUBRIC_DIGEST}'" in reason
    assert report.provenance.tier_rubric_digests == {"run-other-rubric": {RUBRIC_DIGEST: 5, "ffffffffffff": 1}}


def test_rubric_edited_after_the_run_refuses_every_tier_exchange(tmp_path):
    """A later edit to the draft rubric would otherwise reinterpret historical tier rows under the new scale while
    the report said only that the rubric was not recorded (Codex F3 on PR #30)."""
    edited = json.loads(DEFAULT_ADVICE_RUBRIC.read_text(encoding="utf-8"))
    edited["synthetic_edit"] = "changes the canonical digest, not the tier list"
    edited_path = tmp_path / "edited_rubric.json"
    edited_path.write_text(json.dumps(edited), encoding="utf-8")
    run_dir = _write_run(tmp_path, "run-old-rubric", _three_arms(exchanges=(1, 2)))

    report = analyze_run_directories([run_dir], rubric_path=edited_path)

    assert report.provenance.rubric_canonical_digest == rubric_digest(edited)
    for contrast in report.seeds["s1"].dimensions["response_only"].contrasts.values():
        assert contrast.counts.n_compared == 0
        assert contrast.counts.n_refused == 2
        assert all("was judged under rubric digest" in r["reason"] for r in contrast.refusals)
    md = format_markdown_summary(report)
    assert f"canonical digest `{rubric_digest(edited)}`" in md
    assert f"run-old-rubric: `{RUBRIC_DIGEST}` 6" in md
