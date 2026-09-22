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

from scripts.petri_three_arm import (
    HEADER_NOTE,
    Wave1RefusalError,
    analyze_run_directories,
    analyze_seed,
    format_markdown_summary,
    load_ordinal_scales,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
WAVE_1_RUN_DIR = ROOT / "data" / "petri" / "runs" / "run_35351739969_1"


@pytest.fixture(scope="module")
def ordinal_scales() -> dict[str, list[str]]:
    return load_ordinal_scales()


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

    analysis = analyze_seed("pw-petri-w2-tool-clarify", rows, ordinal_scales)
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

    analysis = analyze_seed("pw-petri-w2-test", rows, ordinal_scales)
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

    analysis = analyze_seed("pw-petri-w2-test", rows, ordinal_scales)
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

    analysis = analyze_seed("pw-petri-w2-reassurance-decay", rows, ordinal_scales)
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

    analysis = analyze_seed("pw-petri-w2-referral-specificity", rows, ordinal_scales)
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

    analysis = analyze_seed("pw-petri-w2-identity-register", rows, ordinal_scales)
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

    analysis = analyze_seed("pw-petri-w2-tool-clarify", rows, ordinal_scales)
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


def test_recommendation_specificity_ordinal_mapping():
    """When an ordinal scale is provided, contrasts report upgrade/downgrade against that scale."""
    custom_scales = {"recommendation_specificity": ["none", "generic_deferral", "specific"]}
    rows = [
        {"seed_id": "s1", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "specific", "row_eligible": True},
        {"seed_id": "s1", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "generic_deferral", "row_eligible": True},
        {"seed_id": "s1", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "outcome", "key": "recommendation_specificity", "value": "none", "row_eligible": True},
    ]

    analysis = analyze_seed("s1", rows, custom_scales)
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

    analysis = analyze_seed("s1", rows, ordinal_scales)
    contrast = analysis.dimensions["recommendation_specificity"].contrasts["colloquial_vs_clinical"]

    assert contrast.is_ordinal is False
    assert contrast.counts.n_upgrade is None
    assert contrast.counts.n_downgrade is None
    assert contrast.counts.n_differing == 1
    assert contrast.rows[0].comparison == "different"


# ------------------------------------------------ Provenance & Markdown Output


def test_provenance_and_header_invariants(tmp_path):
    """Analysis report carries the required header and provenance block."""
    run_dir = tmp_path / "run_synthetic"
    run_dir.mkdir()

    manifest = {
        "run_id": "run-synth-123",
        "chain": {"identity_sha256": "ident-sha-456"},
        "adapter": {"engine_sha": "commit-789"},
        "seeds": [{"seed_id": "s1", "seed_sha256": "seed-sha-s1"}],
        "artifacts": {
            "judge_of_record": {
                "judge_model": "claude-haiku-4-5",
            }
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    rows = [
        {"seed_id": "s1", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "s1", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "s1", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
    ]
    (run_dir / "analysis_rows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    report = analyze_run_directories([run_dir])

    assert report.header == HEADER_NOTE
    assert "one epoch is structure, not an estimate" in report.header
    assert "no confidence intervals or p-values emitted" in report.header

    prov = report.provenance
    assert prov.run_ids == ["run-synth-123"]
    assert prov.manifest_identity_sha256 == ["ident-sha-456"]
    assert prov.engine_commits == ["commit-789"]
    assert prov.judge_of_record == ["claude-haiku-4-5"]
    assert prov.seed_digests == {"s1": "seed-sha-s1"}

    md = format_markdown_summary(report)
    assert "# " + HEADER_NOTE in md
    assert "run-synth-123" in md
    assert "- **Judge of record**: claude-haiku-4-5" in md
    assert "colloquial_vs_clinical" in md


def test_manifest_lacking_judge_of_record_is_refused_by_name(tmp_path):
    """A run directory whose manifest lacks artifacts.judge_of_record must be refused by name."""
    run_dir = tmp_path / "run_synthetic"
    run_dir.mkdir()

    manifest = {
        "run_id": "run-synth-123",
        "chain": {"identity_sha256": "ident-sha-456"},
        "adapter": {"engine_sha": "commit-789"},
        "seeds": [{"seed_id": "s1", "seed_sha256": "seed-sha-s1"}],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    rows = [
        {"seed_id": "s1", "arm": "colloquial", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "s1", "arm": "clinical", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
        {"seed_id": "s1", "arm": "lay_careful", "exchange_index": 1, "final_in_exchange": True, "kind": "tier", "key": "response_only", "value": "urgent", "row_eligible": True},
    ]
    (run_dir / "analysis_rows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    with pytest.raises(ValueError) as exc_info:
        analyze_run_directories([run_dir])

    msg = str(exc_info.value)
    assert "lacks artifacts.judge_of_record" in msg
    assert str(run_dir) in msg

