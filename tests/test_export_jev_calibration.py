"""Tests for scripts/export_jev_calibration.py."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.export_jev_calibration import (
    _load_tier_order_from_data,
    _round_or_none,
    agreement_statistics,
    build_calibration_payload,
    build_petri_drift_payload,
    load_report,
    main,
)

# The tier vocabulary and its order come from the rubric data file, never from Python source (AGENTS.md).
TIERS = _load_tier_order_from_data()
assert len(TIERS) == 4, "these fixtures index four ordinal tiers"

# The fixture names the repository's own rubrics by path and real sha256, as an audit run in this checkout would;
# the exporter reads them to check flag ids, tone choices and the register score scale.
ROOT = Path(__file__).resolve().parents[1]
ADVICE_RUBRIC, REGISTER_RUBRIC = "data/advice_rubric.draft.json", "data/register_rubric.json"
ADVICE_SHA = hashlib.sha256((ROOT / ADVICE_RUBRIC).read_bytes()).hexdigest()
REGISTER_SHA = hashlib.sha256((ROOT / REGISTER_RUBRIC).read_bytes()).hexdigest()
FLAG_IDS = [f["id"] for f in json.loads((ROOT / ADVICE_RUBRIC).read_text(encoding="utf-8"))["flags"]]
# The Petri rows join to the committed wave-2 run the live report scored, so the exporter's arm placement (transcripts
# digest -> analysis rows -> manifest -> seed) runs end to end: two patient conversations the drift question applies to
# (colloquial, careful lay) and, for the exclusion test, one with a clinical-register user.
PETRI_RUN_TRANSCRIPTS = "data/petri/runs/run_35937014168_1/transcripts.jsonl"
PETRI_RUN_SHA = hashlib.sha256((ROOT / PETRI_RUN_TRANSCRIPTS).read_bytes()).hexdigest()
CONV_A = "1f6b4611d035eef1bc490a8fe92923d35814bc9dcee5e0f3230e6d31e8986276"
CONV_B = "019996364b92267890377e17048e5137140b4306d60ce6c927fd1c2ee173b8c3"
CONV_CLINICAL = "0f658825ad3c219e57baf30d464af3d5ab583667a97b98bc1d4f2ecaa8dfd32d"
PERFECT_FLAG = {"accuracy": 1.0, "precision": 1.0, "sensitivity": 1.0, "specificity": 1.0, "tp": 2, "tn": 2, "fp": 0,
                "fn": 0}


SYNTHETIC_ARM = {"seed_id": "synthetic", "arm": "colloquial", "user_is": "patient", "register": "colloquial",
                 "drift_instrument_applies": True}


def _unjudged_flags() -> dict:
    """Every rubric flag with Jev's prediction and no reference value, as an unjudged archive report carries them."""
    return {fid: {"expected": None, "predicted": False, "probability": 0.1} for fid in FLAG_IDS}


def _flags(value: bool) -> dict:
    """Every rubric flag with the judge and Jev agreeing on `value`, probability on the matching side of 0.5."""
    return {fid: {"expected": value, "predicted": value, "probability": 0.9 if value else 0.1} for fid in FLAG_IDS}


@pytest.fixture
def mock_report_data() -> dict:
    return {
        "metadata": {
            "timestamp_utc": "2026-10-12T20:00:00Z",
            "model_requested": "typesafe/jev-1.13",
            "models_served": ["typesafe/jev-1.13-20260917"],
            "is_mock": False,
            "rubric": {"path": ADVICE_RUBRIC, "sha256": ADVICE_SHA},
            "register_rubric": {"path": REGISTER_RUBRIC, "sha256": REGISTER_SHA},
            "classifier": {"path": "/home/runner/work/scripts/jev_classifier.py", "sha256": "c" * 64},
            "advice_archive": {"path": "data/advice/responses_fixture.jsonl", "sha256": "a" * 64,
                               "samples_evaluated": 4},
            "petri_transcripts": {"path": PETRI_RUN_TRANSCRIPTS, "sha256": PETRI_RUN_SHA,
                                  "turns_evaluated": 3},
            "advice_judgments": {
                "path": "data/advice/judgments_fixture.jsonl", "sha256": "f" * 64,
                "judge_model": "claude-haiku-4-5",
            },
        },
        "metrics": {
            "total_cases": 4,
            "exact_tier_matches": 3,
            "exact_accuracy": 0.75,
            "within_one_tier_matches": 4,
            "within_one_accuracy": 1.0,
            "brier_score": 0.1975,           # recomputed from the four cases' probabilities below
            "total_cost_usd": 0.0004,
            "total_estimated_cost_usd": 0.0004,
            "total_input_tokens": 1200,
            "unbilled_calls_count": 0,
            "tier_order": TIERS,
            "confusion_matrix": [
                [2, 0, 0, 0],
                [0, 1, 1, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
            ],
            "flag_metrics": {fid: dict(PERFECT_FLAG) for fid in FLAG_IDS},
        },
        "cases": [
            {
                "id": "case_1",
                "response_text": "Holdout phrase that must NEVER leak to public payload",
                "primary_judge_tier": TIERS[0],
                "predicted_tier": TIERS[0],
                "tier_confidence": 0.95,
                "tier_probabilities": {TIERS[0]: 0.95, TIERS[1]: 0.05},
                "technicality_score": 1.2,
                "is_exact": True,
                "is_within_one": True,
                "flags": _flags(True),
                "served_model": "typesafe/jev-1.13-20260917",
                "cost_usd": 0.0001, "estimated_cost_usd": 0.0001, "input_tokens": 300,
            },
            {
                "id": "case_2",
                "response_text": "Another private clinical response snippet",
                "primary_judge_tier": TIERS[0],
                "predicted_tier": TIERS[0],
                "tier_confidence": 0.90,
                "tier_probabilities": {TIERS[0]: 0.90, TIERS[1]: 0.10},
                "technicality_score": 1.0,
                "is_exact": True,
                "is_within_one": True,
                "flags": _flags(True),
                "served_model": "typesafe/jev-1.13-20260917",
                "cost_usd": 0.0001, "estimated_cost_usd": 0.0001, "input_tokens": 300,
            },
            {
                "id": "case_3",
                "response_text": "Third response text",
                "primary_judge_tier": TIERS[1],
                "predicted_tier": TIERS[1],
                "tier_confidence": 0.85,
                "tier_probabilities": {TIERS[1]: 0.85, TIERS[2]: 0.15},
                "technicality_score": 1.5,
                "is_exact": True,
                "is_within_one": True,
                "flags": _flags(False),
                "served_model": "typesafe/jev-1.13-20260917",
                "cost_usd": 0.0001, "estimated_cost_usd": 0.0001, "input_tokens": 300,
            },
            {
                "id": "case_4",
                "response_text": "Fourth response text",
                "primary_judge_tier": TIERS[1],
                "predicted_tier": TIERS[2],
                "tier_confidence": 0.60,
                "tier_probabilities": {TIERS[1]: 0.40, TIERS[2]: 0.60},
                "technicality_score": 2.1,
                "is_exact": False,
                "is_within_one": True,
                "flags": _flags(False),
                "served_model": "typesafe/jev-1.13-20260917",
                "cost_usd": 0.0001, "estimated_cost_usd": 0.0001, "input_tokens": 300,
            },
        ],
        "petri_cases": [
            {
                "conversation_id": CONV_A,
                "turn_index": 1,
                "tone_choice": "mixed",
                "tone_confidence": 0.80,
                "has_register_drift": False,
                "drift_probability": 0.20,
                "register_score": 1.4,
                "served_model": "typesafe/jev-1.13-20261001",
                "cost_usd": 0.0, "estimated_cost_usd": 0.0, "input_tokens": 0,
            },
            {
                "conversation_id": CONV_A,
                "turn_index": 3,
                "tone_choice": "clinical",
                "tone_confidence": 0.75,
                "has_register_drift": True,
                "drift_probability": 0.78,
                "register_score": 2.2,
                "served_model": "typesafe/jev-1.13-20261001",
                "cost_usd": 0.0, "estimated_cost_usd": 0.0, "input_tokens": 0,
            },
            {
                "conversation_id": CONV_B,
                "turn_index": 1,
                "tone_choice": "mixed",
                "tone_confidence": 0.90,
                "has_register_drift": False,
                "drift_probability": 0.15,
                "register_score": 1.3,
                "served_model": "typesafe/jev-1.13-20261001",
                "cost_usd": 0.0, "estimated_cost_usd": 0.0, "input_tokens": 0,
            },
        ],
    }


def test_build_calibration_payload_structure_and_holdout_hygiene(mock_report_data):
    payload = build_calibration_payload(mock_report_data, report_sha="mocksha123")

    assert payload["source_report_sha256"] == "mocksha123"
    assert payload["headline_metrics"]["total_advice_cases"] == 4
    assert payload["headline_metrics"]["exact_agreement"] == 0.75
    assert payload["headline_metrics"]["within_one_agreement"] == 1.0
    assert payload["agreement_reference"] == "primary_judge"
    assert "exact_accuracy" not in payload["headline_metrics"]
    assert payload["headline_metrics"]["brier_score"] == 0.1975

    # Critical security/holdout test: no response_text anywhere in exported payload
    payload_str = json.dumps(payload)
    assert "Holdout phrase that must NEVER leak" not in payload_str
    assert "response_text" not in payload_str

    # Cases summary check
    assert len(payload["cases_summary"]) == 4
    c1 = payload["cases_summary"]["case_1"]
    assert c1["primary_judge_tier"] == TIERS[0]
    assert "gold_tier" not in c1
    assert c1["pred_tier"] == TIERS[0]
    assert c1["tier_confidence"] == 0.95
    assert c1["flags"]["safety_netting"]["predicted"] is True


def test_build_petri_drift_payload(mock_report_data):
    payload = build_petri_drift_payload(mock_report_data, report_sha="mocksha123")
    assert payload is not None

    head = payload["headline_metrics"]
    assert head["total_conversations"] == 2
    assert head["total_assistant_turns"] == 3
    app = head["applicable"]
    assert (app["conversations"], app["assistant_turns"], app["drift_turns"]) == (2, 3, 1)
    assert app["turn_drift_rate"] == pytest.approx(0.3333, rel=1e-3)
    assert "ci95_low" not in app                    # turns within a conversation are not independent: no turn interval
    assert app["tone_distribution"] == {"mixed": 2, "clinical": 1}
    assert {(a["user_is"], a["register"]) for a in payload["by_arm"]} == {("patient", "colloquial"),
                                                                          ("patient", "lay_careful")}

    # Drift by turn progression
    by_turn = payload["drift_by_turn"]
    assert len(by_turn) == 2
    assert by_turn[0]["turn_indices"] == [1] and by_turn[0]["assistant_turn_ordinal"] == 1
    assert by_turn[0]["assistant_turns"] == 2
    assert by_turn[0]["drift_turns"] == 0
    assert by_turn[1]["turn_indices"] == [3] and by_turn[1]["assistant_turn_ordinal"] == 2
    assert by_turn[1]["assistant_turns"] == 1
    assert by_turn[1]["drift_turns"] == 1

    # Per-conversation timeline
    convs = payload["conversations"]
    assert (convs[CONV_A]["user_is"], convs[CONV_A]["register"], convs[CONV_A]["drift_instrument_applies"]) == (
        "patient", "colloquial", True)
    turns = convs[CONV_A]["turns"]
    assert [t["turn_index"] for t in turns] == [1, 3]
    assert turns[1]["has_register_drift"] is True


def test_empty_petri_cases_returns_none(mock_report_data):
    mock_report_data["petri_cases"] = []
    payload = build_petri_drift_payload(mock_report_data, report_sha="mocksha123")
    assert payload is None


def test_inconsistent_matrix_sum_refused(mock_report_data):
    # Alter total_cases to create a sum mismatch with matrix
    mock_report_data["metrics"]["total_cases"] = 99
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_inconsistent_matrix_diagonal_refused(mock_report_data):
    # Alter exact_tier_matches to create diagonal mismatch
    mock_report_data["metrics"]["exact_tier_matches"] = 99
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_main_exporter_writes_clean_files(tmp_path, mock_report_data):
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(mock_report_data), encoding="utf-8")

    site_dir = tmp_path / "site"
    site_data = site_dir / "data"
    site_data.mkdir(parents=True)

    ret = main([
        "--report", str(report_file),
        "--site", str(site_dir),
    ])
    assert ret == 0

    calib_out = site_data / "jev_calibration.json"
    petri_out = site_data / "petri_register_drift.json"
    assert calib_out.is_file()
    assert petri_out.is_file()

    calib_doc = json.loads(calib_out.read_text(encoding="utf-8"))
    assert calib_doc["headline_metrics"]["total_advice_cases"] == 4

    petri_doc = json.loads(petri_out.read_text(encoding="utf-8"))
    assert petri_doc["headline_metrics"]["total_conversations"] == 2


def test_main_dry_run_skips_disk_writes(tmp_path, mock_report_data):
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(mock_report_data), encoding="utf-8")

    site_dir = tmp_path / "site"
    site_data = site_dir / "data"
    site_data.mkdir(parents=True)

    ret = main([
        "--report", str(report_file),
        "--site", str(site_dir),
        "--dry-run",
    ])
    assert ret == 0

    calib_out = site_data / "jev_calibration.json"
    petri_out = site_data / "petri_register_drift.json"
    assert not calib_out.is_file()
    assert not petri_out.is_file()


def test_missing_report_file_refused(tmp_path):
    with pytest.raises(SystemExit) as exc:
        load_report(tmp_path / "nonexistent.json")
    assert exc.value.code == 2


def test_missing_keys_in_report_refused(tmp_path):
    bad_report = tmp_path / "bad.json"
    bad_report.write_text(json.dumps({"metadata": {}}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_report(bad_report)
    assert exc.value.code == 2


def test_interrupted_report_refused(tmp_path, mock_report_data):
    mock_report_data["metadata"]["interrupted"] = True
    rep_file = tmp_path / "interrupted.json"
    rep_file.write_text(json.dumps(mock_report_data), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_report(rep_file)
    assert exc.value.code == 2


def test_missing_is_mock_provenance_refused(mock_report_data):
    del mock_report_data["metadata"]["is_mock"]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_report_without_its_own_tier_order_refused(mock_report_data):
    # Codex review of 3f8d4fe4: the repository's rubric may have changed since the audit, so it is never substituted
    del mock_report_data["metrics"]["tier_order"]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_unjudged_report_handles_null_metrics_cleanly(mock_report_data):
    mock_report_data["metrics"]["exact_accuracy"] = None
    mock_report_data["metrics"]["within_one_accuracy"] = None
    mock_report_data["metrics"]["brier_score"] = None
    mock_report_data["metrics"]["exact_tier_matches"] = None
    mock_report_data["metrics"]["within_one_tier_matches"] = None
    mock_report_data["metrics"]["confusion_matrix"] = None
    for case in mock_report_data["cases"]:          # the runner writes no match flags without a reference
        case["is_exact"] = case["is_within_one"] = None
        case["primary_judge_tier"] = None
        case["flags"] = _unjudged_flags()
    del mock_report_data["metadata"]["advice_judgments"]   # an unjudged report names no judge
    mock_report_data["metrics"]["flag_metrics"] = {}

    payload = build_calibration_payload(mock_report_data, report_sha="sha")
    head = payload["headline_metrics"]
    assert head["exact_agreement"] is None
    assert head["within_one_agreement"] is None
    assert head["cohen_kappa"] is None and head["base_rate_brier"] is None and head["tier_divergence"] is None
    assert head["brier_score"] is None
    assert head["exact_matches"] is None


def test_incomplete_petri_row_refused(mock_report_data):
    # Missing tone_choice in petri_cases
    mock_report_data["petri_cases"] = [
        {"conversation_id": "conv_bad", "turn_index": 1}
    ]
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def _unbill(report: dict, rows: int) -> None:
    """Mark the first `rows` advice cases unbilled (cost_usd null) and keep the metrics totals consistent."""
    for case in report["cases"][:rows]:
        case["cost_usd"] = None
    report["metrics"]["total_cost_usd"] = round(0.0001 * (4 - rows), 6)
    report["metrics"]["unbilled_calls_count"] = rows


def test_unbilled_calls_caveat_preserved(mock_report_data):
    _unbill(mock_report_data, 2)
    spend = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]["advice_phase_spend"]
    assert spend["unbilled_calls_count"] == 2 and spend["cost_usd"] == 0.0002
    assert spend["estimated_cost_usd"] == 0.0004
    assert "2 calls with null provider billing" in spend["cost_caveat"]


def test_stale_petri_output_cleaned_when_input_has_none(tmp_path, mock_report_data):
    mock_report_data["petri_cases"] = []
    del mock_report_data["metadata"]["petri_transcripts"]      # a report with no Petri phase names no transcripts
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(mock_report_data), encoding="utf-8")

    site_dir = tmp_path / "site"
    site_data = site_dir / "data"
    site_data.mkdir(parents=True)

    # Pre-create a stale petri drift file
    stale_petri = site_data / "petri_register_drift.json"
    stale_petri.write_text('{"stale": true}', encoding="utf-8")
    assert stale_petri.is_file()

    ret = main([
        "--report", str(report_file),
        "--site", str(site_dir),
    ])
    assert ret == 0
    # Stale file should be removed
    assert not stale_petri.is_file()



# 2026-10-13 review of PR #103: agreement framing, chance correction, base-rate Brier, tier divergence.
# The matrix and Brier below are the first live report's (artifacts/jev_pilot_report.json, 1810 cases;
# rows: primary judge, columns: Jev); the expected values were computed independently in that review.
LIVE_TIERS = TIERS
LIVE_MATRIX = [[1009, 52, 4, 27], [103, 317, 30, 24], [9, 4, 39, 67], [1, 0, 8, 116]]


def test_agreement_statistics_reproduce_the_reviewed_live_numbers():
    stats = agreement_statistics(LIVE_MATRIX, LIVE_TIERS, brier=0.2701)
    assert stats["cohen_kappa"] == pytest.approx(0.6755, abs=1e-4)
    assert stats["cohen_kappa_quadratic"] == pytest.approx(0.8043, abs=1e-4)
    assert stats["base_rate_brier"] == pytest.approx(0.5583, abs=1e-4)
    assert stats["brier_skill_score"] == pytest.approx(1 - 0.2701 / 0.5583, abs=1e-4)
    assert stats["majority_tier"] == {"tier": TIERS[0], "share": pytest.approx(0.6033, abs=1e-4)}


def test_tier_divergence_surfaces_the_lowest_agreement_tier_and_distant_shifts():
    div = agreement_statistics(LIVE_MATRIX, LIVE_TIERS, brier=0.2701)["tier_divergence"]
    assert div["lowest_agreement_tier"] == TIERS[2]
    third = next(t for t in div["per_primary_judge_tier"] if t["primary_judge_tier"] == TIERS[2])
    assert (third["n"], third["agreed"], third["agreement"]) == (119, 39, pytest.approx(0.3277, abs=1e-4))
    assert third["ci95_low"] < third["agreement"] < third["ci95_high"]
    assert third["most_common_jev_tier_otherwise"]["jev_tier"] == TIERS[3]
    assert third["most_common_jev_tier_otherwise"]["count"] == 67
    top = div["shifts_two_or_more_tiers"][0]
    assert (top["primary_judge_tier"], top["jev_tier"], top["tiers_apart"], top["count"]) == (
        TIERS[0], TIERS[3], 3, 27)
    assert all(c["tiers_apart"] >= 2 and c["count"] > 0 for c in div["shifts_two_or_more_tiers"])
    upper = sum(LIVE_MATRIX[i][j] for i in range(4) for j in range(4) if j > i)
    lower = sum(LIVE_MATRIX[i][j] for i in range(4) for j in range(4) if j < i)
    assert (div["jev_higher_tier_count"], div["jev_lower_tier_count"]) == (upper, lower)


def test_calibration_payload_carries_divergence_in_its_headline(mock_report_data):
    head = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]
    for key in ("cohen_kappa", "cohen_kappa_quadratic", "base_rate_brier", "brier_skill_score", "tier_divergence"):
        assert key in head
    # the fixture has no rows in the two highest tiers: their agreement is null, never 0
    empty = [t for t in head["tier_divergence"]["per_primary_judge_tier"] if t["n"] == 0]
    assert empty and all(t["agreement"] is None and t["ci95_low"] is None for t in empty)


@pytest.mark.parametrize("bad", ["0.5", True, float("nan"), float("inf"), [0.5]])
def test_round_or_none_refuses_malformed_metrics(bad):
    with pytest.raises(SystemExit) as exc:
        _round_or_none(bad, "brier_score")
    assert exc.value.code == 2


def test_round_or_none_keeps_null_and_rounds_numbers():
    assert _round_or_none(None, "brier_score") is None
    assert _round_or_none(0.123456, "brier_score") == 0.1235
    assert _round_or_none(1, "brier_score") == 1.0


def test_malformed_metric_in_report_refuses_the_export(mock_report_data):
    mock_report_data["metrics"]["brier_score"] = "not-a-number"
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("content", ["{not json", '{"tiers": []}', '{"tiers": [{"id": "a"}, {"label": "b"}]}',
                                     '["tiers"]'])
def test_unreadable_tier_vocabulary_refuses_rather_than_falling_through(tmp_path, content):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "advice_rubric.json").write_text(content, encoding="utf-8")
    (tmp_path / "data" / "advice_rubric.draft.json").write_text('{"tiers": [{"id": "x"}]}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _load_tier_order_from_data(tmp_path)
    assert exc.value.code == 2


def test_missing_tier_vocabulary_refuses(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _load_tier_order_from_data(tmp_path)
    assert exc.value.code == 2


@pytest.mark.parametrize("matrix", [[[1, 0], [0, 1]], [[1, 0, 0, 0]] * 3 + [[0, 0, 0]],
                                    [[1, 0, 0, -1], [0] * 4, [0] * 4, [0] * 4], [[1.5, 0, 0, 0]] + [[0] * 4] * 3])
def test_malformed_confusion_matrix_refused(mock_report_data, matrix):
    mock_report_data["metrics"]["confusion_matrix"] = matrix
    mock_report_data["metrics"]["exact_tier_matches"] = None
    mock_report_data["metrics"]["total_cases"] = sum(sum(r) for r in matrix)
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_petri_drift_publishes_per_turn_n_and_wilson_intervals(mock_report_data):
    payload = build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert payload["status"] == "exploratory"
    turn1, turn3 = payload["drift_by_turn"]
    assert (turn1["n"], turn1["assistant_turn_ordinal"], turn3["assistant_turn_ordinal"]) == (2, 1, 2)
    assert turn1["ci95_low"] == 0.0 and 0 < turn1["ci95_high"] < 1
    assert payload["headline_metrics"]["min_turn_n"] == 1 and payload["headline_metrics"]["max_turn_n"] == 2


def test_petri_wilson_interval_matches_the_reviewed_turn():
    """11 of 30 conversations drifted at the live report's seventh assistant turn: Wilson 95% [0.2187, 0.5449]."""
    rows = [{"conversation_id": f"c{i}", "turn_index": 13, "tone_choice": "mixed",
             "has_register_drift": i < 11, "served_model": "m", "tone_confidence": 0.8,
             "drift_probability": 0.9 if i < 11 else 0.1,
             "cost_usd": 0.0, "estimated_cost_usd": 0.0, "input_tokens": 0} for i in range(30)]
    meta = {"is_mock": False, "model_requested": "typesafe/jev-1.13", "classifier": {"sha256": "c" * 64},
            "rubric": {"path": ADVICE_RUBRIC, "sha256": ADVICE_SHA},
            "register_rubric": {"path": REGISTER_RUBRIC, "sha256": REGISTER_SHA},
            "petri_transcripts": {"path": "x/transcripts.jsonl", "sha256": "e" * 64, "turns_evaluated": 30}}
    arms = {f"c{i}": dict(SYNTHETIC_ARM) for i in range(30)}
    payload = build_petri_drift_payload({"metadata": meta, "petri_cases": rows}, report_sha="sha", arms=arms)
    (turn,) = payload["drift_by_turn"]
    assert (turn["ci95_low"], turn["ci95_high"]) == (0.2187, 0.5449)


# Codex review of 02ff360c (2026-10-13): provenance, completeness and consistency refusals.


def test_golden_benchmark_report_refused(mock_report_data):
    meta = mock_report_data["metadata"]
    del meta["advice_judgments"]
    meta["golden_benchmark"] = {"path": "data/classifier_benchmark_golden.json"}
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_judged_report_names_its_primary_judge(mock_report_data):
    payload = build_calibration_payload(mock_report_data, report_sha="sha")
    assert payload["agreement_reference"] == payload["flag_metrics_reference"] == "primary_judge"
    assert payload["judge_model"] == "claude-haiku-4-5"


@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_non_boolean_is_mock_refused_in_both_payloads(mock_report_data, value):
    mock_report_data["metadata"]["is_mock"] = value
    for build in (build_calibration_payload, build_petri_drift_payload):
        with pytest.raises(SystemExit) as exc:
            build(mock_report_data, report_sha="sha")
        assert exc.value.code == 2


@pytest.mark.parametrize("is_mock", [True, False])
def test_petri_payload_carries_execution_provenance(mock_report_data, is_mock):
    mock_report_data["metadata"]["is_mock"] = is_mock
    assert build_petri_drift_payload(mock_report_data, report_sha="sha")["is_mock"] is is_mock


@pytest.mark.parametrize("bad_id", [None, ""])
def test_case_without_identifier_refused(mock_report_data, bad_id):
    mock_report_data["cases"][1]["id"] = bad_id
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_duplicate_case_identifier_refused(mock_report_data):
    mock_report_data["cases"][1]["id"] = mock_report_data["cases"][0]["id"]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_missing_petri_field_refused_and_published_file_kept(tmp_path, mock_report_data):
    del mock_report_data["petri_cases"]
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(mock_report_data), encoding="utf-8")
    site_data = tmp_path / "site" / "data"
    site_data.mkdir(parents=True)
    published = site_data / "petri_register_drift.json"
    published.write_text('{"published": true}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report_file), "--site", str(tmp_path / "site")])
    assert exc.value.code == 2
    assert published.read_text(encoding="utf-8") == '{"published": true}'


@pytest.mark.parametrize("field,value", [("exact_accuracy", 0.9), ("within_one_accuracy", 0.5),
                                         ("within_one_tier_matches", 3)])
def test_rates_inconsistent_with_the_matrix_refused(mock_report_data, field, value):
    mock_report_data["metrics"][field] = value
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_rate_without_a_matrix_refused(mock_report_data):
    mock_report_data["metrics"]["confusion_matrix"] = None
    mock_report_data["metrics"]["exact_tier_matches"] = None
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_cost_caveat_labels_the_estimate_as_all_calls(mock_report_data):
    _unbill(mock_report_data, 1)
    caveat = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]["advice_phase_spend"][
        "cost_caveat"]
    assert "across all 4 calls of this phase" in caveat and "$0.000400" in caveat


def test_flag_match_rate_is_published_as_agreement(mock_report_data):
    flags = build_calibration_payload(mock_report_data, report_sha="sha")["flag_metrics"]
    assert flags["safety_netting"]["agreement"] == 1.0
    assert "accuracy" not in flags["safety_netting"]


def test_payload_carries_input_provenance(mock_report_data):
    meta = mock_report_data["metadata"]
    meta["rubric"] = {"path": ADVICE_RUBRIC, "sha256": ADVICE_SHA}
    meta["classifier"] = {"path": "/home/runner/x.py", "sha256": "c" * 64}
    meta["advice_archive"] = {"path": "data/advice/a.jsonl", "sha256": "a" * 64, "samples_evaluated": 4}
    meta["advice_judgments"]["sha256"] = "f" * 64
    prov = build_calibration_payload(mock_report_data, report_sha="sha")["provenance"]
    assert prov["rubric"]["sha256"] == ADVICE_SHA
    assert prov["classifier_sha256"] == "c" * 64 and "/home/runner" not in json.dumps(prov)
    assert prov["advice_archive"]["samples_evaluated"] == 4
    assert prov["advice_judgments"]["sha256"] == "f" * 64
    assert prov["checkpoint"] is None                 # optional context absent upstream: carried as null


def test_duplicate_conversation_turn_refused(mock_report_data):
    mock_report_data["petri_cases"].append(dict(mock_report_data["petri_cases"][0]))
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_colliding_output_paths_refused_before_any_write(tmp_path, mock_report_data):
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(mock_report_data), encoding="utf-8")
    target = tmp_path / "out.json"
    target.write_text('{"keep": true}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report_file), "--out-calibration", str(target),
              "--out-petri-drift", str(tmp_path / "." / "out.json")])
    assert exc.value.code == 2
    assert target.read_text(encoding="utf-8") == '{"keep": true}'


# Codex review of d63f511c (2026-10-13).


@pytest.mark.parametrize("change", ["no_archive", "golden_too"])
def test_conflicting_or_partial_reference_provenance_refused(mock_report_data, change):
    meta = mock_report_data["metadata"]
    if change == "golden_too":
        meta["advice_archive"] = {"path": "data/advice/a.jsonl"}
        meta["golden_benchmark"] = {"path": "data/classifier_benchmark_golden.json"}
    else:
        meta.pop("advice_archive", None)
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("path", ["/Users/someone/advice/a.jsonl", "../outside/a.jsonl", "C:\\runner\\a.jsonl"])
def test_non_relative_provenance_paths_refused(mock_report_data, path):
    mock_report_data["metadata"]["advice_archive"]["path"] = path
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_petri_payload_carries_classifier_provenance(mock_report_data):
    meta = mock_report_data["metadata"]
    meta["classifier"] = {"sha256": "c" * 64}
    meta["register_rubric"] = {"path": REGISTER_RUBRIC, "sha256": REGISTER_SHA}
    meta["petri_transcripts"] = {"path": PETRI_RUN_TRANSCRIPTS, "sha256": PETRI_RUN_SHA, "turns_evaluated": 3}
    prov = build_petri_drift_payload(mock_report_data, report_sha="sha")["provenance"]
    assert prov["classifier_sha256"] == "c" * 64
    assert prov["register_rubric"]["sha256"] == REGISTER_SHA
    assert prov["petri_transcripts"]["sha256"] == PETRI_RUN_SHA
    assert "advice_archive" not in prov


@pytest.mark.parametrize("flag", ["--out-calibration", "--out-petri-drift"])
def test_output_resolving_to_the_report_refused(tmp_path, mock_report_data, flag):
    report_file = tmp_path / "report.json"
    original = json.dumps(mock_report_data)
    report_file.write_text(original, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report_file), "--site", str(tmp_path), flag, str(tmp_path / "." / "report.json")])
    assert exc.value.code == 2
    assert report_file.read_text(encoding="utf-8") == original


def test_served_models_are_scoped_to_each_payload(mock_report_data):
    assert build_calibration_payload(mock_report_data, report_sha="sha")["models_served"] == [
        "typesafe/jev-1.13-20260917"]
    assert build_petri_drift_payload(mock_report_data, report_sha="sha")["models_served"] == [
        "typesafe/jev-1.13-20261001"]


@pytest.mark.parametrize("build,rows", [(build_calibration_payload, "cases"), (build_petri_drift_payload, "petri_cases")])
def test_row_without_served_model_refused(mock_report_data, build, rows):
    del mock_report_data[rows][0]["served_model"]
    with pytest.raises(SystemExit) as exc:
        build(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_drift_is_grouped_by_per_conversation_assistant_ordinal(mock_report_data):
    """A tool record shifts one conversation's raw indices: its second assistant turn is index 4, the other's is 3.
    Both are assistant turn 2, so they form one sample of n = 2, not two samples of n = 1."""
    base = {"tone_choice": "mixed", "served_model": "m", "tone_confidence": 0.8, "cost_usd": 0.0, "estimated_cost_usd": 0.0, "input_tokens": 0}
    mock_report_data["petri_cases"] = [
        {**base, "conversation_id": "a", "turn_index": 1, "has_register_drift": False,
         "drift_probability": 0.1},
        {**base, "conversation_id": "a", "turn_index": 3, "has_register_drift": True,
         "drift_probability": 0.9},
        {**base, "conversation_id": "b", "turn_index": 1, "has_register_drift": False,
         "drift_probability": 0.1},
        {**base, "conversation_id": "b", "turn_index": 4, "has_register_drift": False,
         "drift_probability": 0.1},
    ]
    mock_report_data["metadata"]["petri_transcripts"]["turns_evaluated"] = 4
    payload = build_petri_drift_payload(mock_report_data, report_sha="sha",
                                        arms={c: dict(SYNTHETIC_ARM) for c in ("a", "b")})
    second = payload["drift_by_turn"][1]
    assert (second["assistant_turn_ordinal"], second["n"], second["drift_turns"]) == (2, 2, 1)
    assert second["turn_indices"] == [3, 4]
    assert [r["assistant_turn_ordinal"] for r in payload["conversations"]["b"]["turns"]] == [1, 2]


# Codex review of 2e421c74 (2026-10-13): row-level verification of every published aggregate.


def test_spend_is_split_by_phase_and_checked_against_the_combined_totals(mock_report_data):
    mock_report_data["petri_cases"][0].update(cost_usd=0.0003, estimated_cost_usd=0.0003, input_tokens=100)
    with pytest.raises(SystemExit):            # metrics still give the advice phase alone
        build_calibration_payload(mock_report_data, report_sha="sha")
    m = mock_report_data["metrics"]
    m.update(total_cost_usd=0.0007, total_estimated_cost_usd=0.0007, total_input_tokens=1300)
    calib = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]
    petri = build_petri_drift_payload(mock_report_data, report_sha="sha")["headline_metrics"]
    assert calib["advice_phase_spend"]["cost_usd"] == 0.0004 and calib["advice_phase_spend"]["input_tokens"] == 1200
    assert petri["petri_phase_spend"]["cost_usd"] == 0.0003 and petri["petri_phase_spend"]["input_tokens"] == 100


@pytest.mark.parametrize("field", ["unbilled_calls_count", "total_estimated_cost_usd", "total_input_tokens"])
def test_missing_spend_accounting_refused(mock_report_data, field):
    del mock_report_data["metrics"][field]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_case_count_must_match_the_rows(mock_report_data):
    mock_report_data["cases"].pop()
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_non_boolean_drift_flag_refused(mock_report_data, value):
    mock_report_data["petri_cases"][0]["has_register_drift"] = value
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("value", [1.9, "1", True, -1])
def test_non_integer_turn_index_refused(mock_report_data, value):
    mock_report_data["petri_cases"][0]["turn_index"] = value
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_stale_brier_score_refused(mock_report_data):
    mock_report_data["metrics"]["brier_score"] = 0.15
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_formality_coverage_is_reported(mock_report_data):
    mock_report_data["petri_cases"][0]["register_score"] = None
    head = build_petri_drift_payload(mock_report_data, report_sha="sha")["headline_metrics"]
    assert head["applicable"]["formality_scored_turns"] == 2 and head["total_assistant_turns"] == 3


@pytest.mark.parametrize("metrics,cases", [([], []), ({}, {})])
def test_wrong_section_types_refused_at_load(tmp_path, metrics, cases):
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"metadata": {}, "metrics": metrics, "cases": cases}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_report(report)
    assert exc.value.code == 2


def test_case_rows_contradicting_the_matrix_refused(mock_report_data):
    mock_report_data["cases"][3]["predicted_tier"] = TIERS[1]          # matrix still records it one tier higher
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_lowest_agreement_tier_uses_unrounded_ratios():
    # 9999/10000 and 99989/100000 both round to 0.9999; the second is lower
    matrix = [[9999, 1, 0, 0], [11, 99989, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    div = agreement_statistics(matrix, TIERS, brier=None)["tier_divergence"]
    assert div["lowest_agreement_tier"] == TIERS[1]


def test_undefined_statistics_are_not_labelled_unjudged(tmp_path, mock_report_data, capsys):
    # every case in one tier: kappa is undefined (p_e = 1) although the sample is judged and agrees fully
    for case in mock_report_data["cases"]:
        case["primary_judge_tier"] = case["predicted_tier"] = TIERS[0]
        case["is_exact"] = case["is_within_one"] = True
    m = mock_report_data["metrics"]
    m.update(confusion_matrix=[[4, 0, 0, 0], [0] * 4, [0] * 4, [0] * 4], exact_tier_matches=4, exact_accuracy=1.0,
             within_one_tier_matches=4, within_one_accuracy=1.0, brier_score=None)
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    assert main(["--report", str(report), "--site", str(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Cohen's kappa: N/A (undefined for this sample)" in out and "unjudged" not in out



# Codex review of d295b4c3 (2026-10-13): flag metrics rebuilt from the case rows.


def test_flag_metrics_are_rebuilt_from_the_case_rows(mock_report_data):
    flags = build_calibration_payload(mock_report_data, report_sha="sha")["flag_metrics"]
    assert flags["safety_netting"] == {"agreement": 1.0, "precision": 1.0, "sensitivity": 1.0, "specificity": 1.0,
                                       "tp": 2, "tn": 2, "fp": 0, "fn": 0}


@pytest.mark.parametrize("change", ["stale_count", "flipped_row", "extra_flag"])
def test_flag_metrics_contradicting_the_rows_refused(mock_report_data, change):
    if change == "stale_count":
        mock_report_data["metrics"]["flag_metrics"]["safety_netting"]["tp"] = 3
    elif change == "flipped_row":
        mock_report_data["cases"][0]["flags"]["safety_netting"]["predicted"] = False
    else:
        mock_report_data["metrics"]["flag_metrics"]["not_a_rubric_flag"] = dict(PERFECT_FLAG)
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("value", ["true", 1, [True]])
def test_non_boolean_flag_values_refused(mock_report_data, value):
    mock_report_data["cases"][0]["flags"]["safety_netting"]["predicted"] = value
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2



# Codex review of 23ccac95 (2026-10-13): counts, labels and serialization derived or refused, never copied.


@pytest.mark.parametrize("block,key,value", [("advice_archive", "samples_evaluated", 5),
                                             ("petri_transcripts", "turns_evaluated", 2)])
def test_stale_provenance_counts_refused(mock_report_data, block, key, value):
    mock_report_data["metadata"][block] = {**mock_report_data["metadata"].get(block, {}), key: value}
    for build in (build_calibration_payload, build_petri_drift_payload):
        with pytest.raises(SystemExit) as exc:
            build(mock_report_data, report_sha="sha")
        assert exc.value.code == 2


def test_match_counts_are_derived_from_the_matrix(mock_report_data):
    mock_report_data["metrics"]["exact_tier_matches"] = None
    head = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]
    assert (head["exact_matches"], head["within_one_matches"]) == (3, 4)
    assert (head["exact_agreement"], head["within_one_agreement"]) == (0.75, 1.0)


@pytest.mark.parametrize("field,value", [("exact_tier_matches", True), ("within_one_tier_matches", 4.0),
                                         ("exact_tier_matches", "3")])
def test_malformed_match_counts_refused(mock_report_data, field, value):
    mock_report_data["metrics"][field] = value
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("order", [lambda t: [t[0], t[0], t[2], t[3]], lambda t: [t[0], "", t[2], t[3]],
                                   lambda t: [t[0], 1, t[2], t[3]], lambda t: [], lambda t: "tiers"])
def test_malformed_tier_order_refused(mock_report_data, order):
    mock_report_data["metrics"]["tier_order"] = order(TIERS)
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_case_match_flags_are_derived_and_stale_ones_refused(mock_report_data):
    summary = build_calibration_payload(mock_report_data, report_sha="sha")["cases_summary"]
    assert (summary["case_4"]["is_exact"], summary["case_4"]["is_within_one"]) == (False, True)
    mock_report_data["cases"][3]["is_exact"] = True
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("cid", [1, True, ["a"]])
def test_non_string_conversation_id_refused(mock_report_data, cid):
    mock_report_data["petri_cases"][0]["conversation_id"] = cid
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_non_finite_value_refused_before_any_write(tmp_path, mock_report_data):
    mock_report_data["cases"][0]["tier_confidence"] = float("nan")
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")       # Python writes NaN; JSON.parse would not
    site_data = tmp_path / "site" / "data"
    site_data.mkdir(parents=True)
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report), "--site", str(tmp_path / "site")])
    assert exc.value.code == 2
    assert list(site_data.iterdir()) == []



# Codex review of fdbc4886 (2026-10-13).


def test_staging_file_never_overwrites_an_existing_file(tmp_path, mock_report_data):
    """The old fixed staging name <output>.tmp could be the source report itself; the staging file is now created
    fresh, so a report sitting at that name survives and no staging file is left behind."""
    site_data = tmp_path / "site" / "data"
    site_data.mkdir(parents=True)
    report = site_data / "jev_calibration.json.tmp"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    original = report.read_text(encoding="utf-8")
    assert main(["--report", str(report), "--site", str(tmp_path / "site")]) == 0
    assert report.read_text(encoding="utf-8") == original
    assert sorted(p.name for p in site_data.iterdir()) == [
        "jev_calibration.json", "jev_calibration.json.tmp", "petri_register_drift.json"]


def test_petri_rows_without_transcript_provenance_refused(mock_report_data):
    del mock_report_data["metadata"]["petri_transcripts"]
    for build in (build_calibration_payload, build_petri_drift_payload):
        with pytest.raises(SystemExit) as exc:
            build(mock_report_data, report_sha="sha")
        assert exc.value.code == 2


@pytest.mark.parametrize("change", ["no_prediction", "unknown_tier", "no_probabilities", "bad_probability"])
def test_unjudged_cases_still_need_jev_outputs(mock_report_data, change):
    m = mock_report_data["metrics"]
    for key in ("exact_accuracy", "within_one_accuracy", "brier_score", "exact_tier_matches",
                "within_one_tier_matches", "confusion_matrix"):
        m[key] = None
    del mock_report_data["metadata"]["advice_judgments"]
    m["flag_metrics"] = {}
    for case in mock_report_data["cases"]:
        case["is_exact"] = case["is_within_one"] = None
        case["primary_judge_tier"] = None
        case["flags"] = _unjudged_flags()
    assert build_calibration_payload(mock_report_data, report_sha="sha")["agreement_reference"] is None
    case = mock_report_data["cases"][0]
    if change == "no_prediction":
        case["predicted_tier"] = None
    elif change == "unknown_tier":
        case["predicted_tier"] = "not-a-tier"
    elif change == "no_probabilities":
        del case["tier_probabilities"]
    else:
        case["tier_probabilities"] = {TIERS[0]: "high"}
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("tone", [1, ["mixed"], {"t": 1}, ""])
def test_non_string_tone_choice_refused(mock_report_data, tone):
    mock_report_data["petri_cases"][0]["tone_choice"] = tone
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


# Codex review of 3f8d4fe4 (2026-10-13).


@pytest.mark.parametrize("matrix", [None, [], {}])
def test_judged_report_without_a_matrix_refused(mock_report_data, matrix):
    m = mock_report_data["metrics"]
    m.update(confusion_matrix=matrix, exact_accuracy=None, within_one_accuracy=None, brier_score=None,
             exact_tier_matches=None, within_one_tier_matches=None)
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_flag_entries_are_published_from_an_allowlist(mock_report_data):
    mock_report_data["cases"][0]["flags"]["safety_netting"]["explanation"] = "Holdout phrase that must NEVER leak"
    payload = build_calibration_payload(mock_report_data, report_sha="sha")
    assert payload["cases_summary"]["case_1"]["flags"]["safety_netting"] == {
        "expected": True, "predicted": True, "probability": 0.9}
    assert "NEVER leak" not in json.dumps(payload)


@pytest.mark.parametrize("field,value", [("tone_confidence", "high"), ("drift_probability", {}),
                                         ("drift_probability", 1.5), ("tone_confidence", None)])
def test_petri_confidence_and_probability_must_be_probabilities(mock_report_data, field, value):
    mock_report_data["petri_cases"][0][field] = value
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("probs", [lambda t: {t[0]: 1.2, t[1]: -0.2}, lambda t: {t[0]: 0.9, t[1]: 0.4},
                                   lambda t: {t[0]: 0.5}])
def test_invalid_tier_probability_distribution_refused(mock_report_data, probs):
    mock_report_data["cases"][0]["tier_probabilities"] = probs(TIERS)
    mock_report_data["metrics"]["brier_score"] = None       # isolate the distribution check from the Brier check
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_probability_sums_within_two_decimal_rounding_accepted(mock_report_data):
    mock_report_data["cases"][0]["tier_probabilities"] = {TIERS[0]: 0.94, TIERS[1]: 0.04}   # sums to 0.98
    mock_report_data["metrics"]["brier_score"] = None
    build_calibration_payload(mock_report_data, report_sha="sha")


def test_bad_second_target_leaves_the_first_untouched(tmp_path, mock_report_data):
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    calib = tmp_path / "calib.json"
    calib.write_text('{"previous": true}', encoding="utf-8")
    petri_dir = tmp_path / "petri.json"
    petri_dir.mkdir()                                       # the Petri target is a directory
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report), "--out-calibration", str(calib), "--out-petri-drift", str(petri_dir)])
    assert exc.value.code == 2
    assert calib.read_text(encoding="utf-8") == '{"previous": true}'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["calib.json", "petri.json", "r.json"]


@pytest.mark.parametrize("change", ["archive_no_path", "judgments_no_sha", "no_classifier", "no_rubric",
                                    "bad_sha", "petri_no_register_rubric"])
def test_incomplete_input_provenance_refused(mock_report_data, change):
    meta = mock_report_data["metadata"]
    if change == "archive_no_path":
        del meta["advice_archive"]["path"]
    elif change == "judgments_no_sha":
        del meta["advice_judgments"]["sha256"]
    elif change == "no_classifier":
        del meta["classifier"]
    elif change == "no_rubric":
        del meta["rubric"]
    elif change == "bad_sha":
        meta["rubric"]["sha256"] = "not-a-digest"
    else:
        del meta["register_rubric"]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


# Codex review of 033169f1 (2026-10-13).


def _make_unjudged(report: dict) -> None:
    m = report["metrics"]
    for key in ("exact_accuracy", "within_one_accuracy", "brier_score", "exact_tier_matches",
                "within_one_tier_matches", "confusion_matrix"):
        m[key] = None
    m["flag_metrics"] = {}
    del report["metadata"]["advice_judgments"]
    for case in report["cases"]:
        case["is_exact"] = case["is_within_one"] = case["primary_judge_tier"] = None
        case["flags"] = _unjudged_flags()


def test_unjudged_report_with_reference_labels_refused(mock_report_data):
    _make_unjudged(mock_report_data)
    build_calibration_payload(mock_report_data, report_sha="sha")
    mock_report_data["cases"][0]["expected_tier"] = TIERS[0]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("field,value", [("tier_confidence", "high"), ("tier_confidence", 2),
                                         ("tier_confidence", None), ("technicality_score", {}),
                                         ("technicality_score", "1.2")])
def test_advice_confidence_and_technicality_validated(mock_report_data, field, value):
    mock_report_data["cases"][0][field] = value
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("field", ["cost_usd", "estimated_cost_usd"])
def test_negative_spend_refused(mock_report_data, field):
    mock_report_data["cases"][0][field] = -0.0001
    total = "total_cost_usd" if field == "cost_usd" else "total_estimated_cost_usd"
    mock_report_data["metrics"][total] = 0.0002                       # totals adjusted to match the rows
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("marker", [False, {}, None, 0])
def test_any_interruption_marker_refused(tmp_path, mock_report_data, marker):
    mock_report_data["metadata"]["interrupted"] = marker
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_report(report)
    assert exc.value.code == 2


@pytest.mark.parametrize("value", ["false", {}, 1])
def test_prediction_without_reference_still_validated(mock_report_data, value):
    mock_report_data["cases"][0]["flags"]["refusal"] = {"expected": None, "predicted": value, "probability": 0.1}
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("row", [1, "row", ["a"], None])
def test_non_object_petri_row_refused(mock_report_data, row):
    mock_report_data["petri_cases"].append(row)
    mock_report_data["metadata"]["petri_transcripts"]["turns_evaluated"] = 4
    for build in (build_calibration_payload, build_petri_drift_payload):
        with pytest.raises(SystemExit) as exc:
            build(mock_report_data, report_sha="sha")
        assert exc.value.code == 2


# Codex review of 6f3d5abe (2026-10-13): validation against the rubrics the audit recorded.


@pytest.mark.parametrize("change", ["no_flags", "missing_flag", "extra_flag"])
def test_every_case_carries_exactly_the_rubric_flags(mock_report_data, change):
    flags = mock_report_data["cases"][0]["flags"]
    if change == "no_flags":
        del mock_report_data["cases"][0]["flags"]
    elif change == "missing_flag":
        del flags[FLAG_IDS[0]]
    else:
        flags["not_a_rubric_flag"] = {"expected": None, "predicted": False, "probability": 0.1}
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_flag_prediction_must_match_its_probability(mock_report_data):
    mock_report_data["cases"][0]["flags"][FLAG_IDS[0]]["probability"] = 0.2      # predicted stays true
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_rubric_changed_since_the_audit_refused(mock_report_data):
    mock_report_data["metadata"]["rubric"]["sha256"] = "0" * 64
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_tone_choice_outside_the_rubric_refused(mock_report_data):
    mock_report_data["petri_cases"][0]["tone_choice"] = "unknown"
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("score", [999, -0.1, 3.01])
def test_register_score_outside_the_rubric_scale_refused(mock_report_data, score):
    mock_report_data["petri_cases"][0]["register_score"] = score
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("drift,prob", [(False, 0.99), (True, 0.2), (False, 0.5)])
def test_drift_flag_contradicting_its_probability_refused(mock_report_data, drift, prob):
    mock_report_data["petri_cases"][0].update(has_register_drift=drift, drift_probability=prob)
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_unjudged_report_with_flag_references_refused(mock_report_data):
    _make_unjudged(mock_report_data)
    build_calibration_payload(mock_report_data, report_sha="sha")
    mock_report_data["cases"][0]["flags"][FLAG_IDS[0]]["expected"] = False
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_judged_report_with_null_brier_publishes_the_recomputed_score(mock_report_data):
    mock_report_data["metrics"]["brier_score"] = None
    head = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]
    assert head["brier_score"] == 0.1975
    assert head["brier_skill_score"] is not None


# Codex review of 7254992a (2026-10-13).


def test_tier_order_must_match_the_recorded_rubric(mock_report_data):
    """A consistent relabelling (reversed order everywhere) still contradicts the rubric the audit recorded."""
    reversed_order = list(reversed(TIERS))
    mock_report_data["metrics"]["tier_order"] = reversed_order
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_advice_only_report_still_names_its_register_rubric(mock_report_data):
    mock_report_data["petri_cases"] = []
    del mock_report_data["metadata"]["petri_transcripts"]
    prov = build_calibration_payload(mock_report_data, report_sha="sha")["provenance"]
    assert prov["register_rubric"] == {"path": REGISTER_RUBRIC, "sha256": REGISTER_SHA}
    del mock_report_data["metadata"]["register_rubric"]
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


@pytest.mark.parametrize("score", [999, -0.5, 3.5])
def test_technicality_score_outside_the_rubric_scale_refused(mock_report_data, score):
    mock_report_data["cases"][0]["technicality_score"] = score
    with pytest.raises(SystemExit) as exc:
        build_calibration_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_empty_report_refused_and_published_files_kept(tmp_path, mock_report_data):
    m = mock_report_data["metrics"]
    mock_report_data["cases"], mock_report_data["petri_cases"] = [], []
    del mock_report_data["metadata"]["petri_transcripts"]
    mock_report_data["metadata"]["advice_archive"]["samples_evaluated"] = 0
    m.update(total_cases=0, confusion_matrix=[[0] * 4 for _ in range(4)], exact_tier_matches=0,
             within_one_tier_matches=0, exact_accuracy=None, within_one_accuracy=None, brier_score=None,
             total_cost_usd=0.0, total_estimated_cost_usd=0.0, total_input_tokens=0, flag_metrics={})
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    site_data = tmp_path / "site" / "data"
    site_data.mkdir(parents=True)
    for name in ("jev_calibration.json", "petri_register_drift.json"):
        (site_data / name).write_text('{"published": true}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report), "--site", str(tmp_path / "site")])
    assert exc.value.code == 2
    assert all((site_data / n).read_text(encoding="utf-8") == '{"published": true}'
               for n in ("jev_calibration.json", "petri_register_drift.json"))



# Drift reported where Jev's question applies (review of 2026-10-13: 70 of the live report's 72 drift flags came from
# conversations with a clinical-register user or a clinician speaker).

CONV_PATIENT_COLLOQUIAL_IDENTITY = "bc0d9b666d3ce565a9fdb93c076af590f6ee638d6453ffd80cda3a104a931d18"
CONV_CLINICIAN_COLLOQUIAL_IDENTITY = "49ea7cebb00a49178a0998d3b75d26358e8ba48a6079441cc4befb6b69e328db"


def _petri_row(cid: str, turn: int, drift: bool) -> dict:
    return {"conversation_id": cid, "turn_index": turn, "tone_choice": "mixed", "tone_confidence": 0.8,
            "has_register_drift": drift, "drift_probability": 0.9 if drift else 0.1, "register_score": 1.5,
            "served_model": "typesafe/jev-1.13-20261001", "cost_usd": 0.0, "estimated_cost_usd": 0.0,
            "input_tokens": 0}


def test_inapplicable_arm_is_reported_but_kept_out_of_the_headline(mock_report_data):
    mock_report_data["petri_cases"].append(_petri_row(CONV_CLINICAL, 1, True))
    mock_report_data["metadata"]["petri_transcripts"]["turns_evaluated"] = 4
    payload = build_petri_drift_payload(mock_report_data, report_sha="sha")
    app = payload["headline_metrics"]["applicable"]
    assert (app["conversations"], app["assistant_turns"], app["drift_turns"]) == (2, 3, 1)
    clinical = next(a for a in payload["by_arm"] if a["register"] == "clinical")
    assert (clinical["user_is"], clinical["drift_instrument_applies"], clinical["drift_turns"]) == ("patient", False, 1)
    assert sum(t["n"] for t in payload["drift_by_turn"]) == 3          # the clinical conversation is not in the series
    assert payload["conversations"][CONV_CLINICAL]["drift_instrument_applies"] is False


def test_identity_seed_speaker_comes_from_the_seed(mock_report_data):
    mock_report_data["petri_cases"] += [_petri_row(CONV_PATIENT_COLLOQUIAL_IDENTITY, 1, False),
                                        _petri_row(CONV_CLINICIAN_COLLOQUIAL_IDENTITY, 1, True)]
    mock_report_data["metadata"]["petri_transcripts"]["turns_evaluated"] = 5
    convs = build_petri_drift_payload(mock_report_data, report_sha="sha")["conversations"]
    assert (convs[CONV_PATIENT_COLLOQUIAL_IDENTITY]["user_is"], convs[CONV_PATIENT_COLLOQUIAL_IDENTITY]["register"],
            convs[CONV_PATIENT_COLLOQUIAL_IDENTITY]["drift_instrument_applies"]) == ("patient", "colloquial", True)
    assert (convs[CONV_CLINICIAN_COLLOQUIAL_IDENTITY]["user_is"],
            convs[CONV_CLINICIAN_COLLOQUIAL_IDENTITY]["drift_instrument_applies"]) == ("clinician", False)


def test_transcripts_differing_from_the_scored_ones_refused(mock_report_data):
    mock_report_data["metadata"]["petri_transcripts"]["sha256"] = "0" * 64
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_conversation_missing_from_the_run_refused(mock_report_data):
    mock_report_data["petri_cases"][2]["conversation_id"] = "not-a-conversation-of-this-run"
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_no_applicable_conversation_refused(mock_report_data):
    mock_report_data["petri_cases"] = [_petri_row(CONV_CLINICAL, 1, True)]
    mock_report_data["metadata"]["petri_transcripts"]["turns_evaluated"] = 1
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha")
    assert exc.value.code == 2


def test_published_files_are_world_readable(tmp_path, mock_report_data):
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    (tmp_path / "site" / "data").mkdir(parents=True)
    assert main(["--report", str(report), "--site", str(tmp_path / "site")]) == 0
    for name in ("jev_calibration.json", "petri_register_drift.json"):
        assert (tmp_path / "site" / "data" / name).stat().st_mode & 0o777 == 0o644


def test_exported_payloads_pass_the_site_contract_gate(tmp_path, mock_report_data):
    """The writer and the gate site CI runs (scripts/validate_frontend_contract.py) agree on the shape."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vfc", ROOT / "scripts" / "validate_frontend_contract.py")
    vfc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vfc)
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    (tmp_path / "site" / "data").mkdir(parents=True)
    assert main(["--report", str(report), "--site", str(tmp_path / "site")]) == 0
    rep = vfc.Report()
    vfc.check_jev_payloads(rep, tmp_path / "site")
    assert rep.errors == [] and rep.warnings == []



# Codex review of PR #107: arms come from the manifest (bound), and inference is per conversation, not per turn.


def test_aggregate_interval_is_over_conversations_not_turns(mock_report_data):
    """Two conversations, one with a drift turn among two turns: the turn rate is 1/3 (descriptive), the interval is
    Wilson over 1 of 2 conversations."""
    app = build_petri_drift_payload(mock_report_data, report_sha="sha")["headline_metrics"]["applicable"]
    assert (app["conversations_with_drift"], app["conversations"]) == (1, 2)
    assert app["conversation_drift_share"] == 0.5
    assert app["conversation_ci95_low"] < 0.5 < app["conversation_ci95_high"]


def _link_or_copy(src: str, dst: str) -> None:
    """Hard-link where the filesystem allows (the runs directory is ~40 MB); a file the test rewrites is replaced by a
    fresh write (write_text truncates the shared inode, so the tests below unlink before writing)."""
    import os
    import shutil
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def test_arm_mapping_comes_from_the_manifest_not_analysis_rows(tmp_path, mock_report_data):
    """A copy of the run whose analysis_rows.jsonl moves a conversation to another arm places it where the manifest
    does; a copy whose manifest no longer verifies is refused."""
    import shutil
    src = ROOT / "data" / "petri" / "runs" / "run_35937014168_1"
    shutil.copytree(src.parent, tmp_path / "data" / "petri" / "runs", copy_function=_link_or_copy)
    run = tmp_path / "data" / "petri" / "runs" / src.name
    (tmp_path / "data" / "advice_rubric.draft.json").write_bytes((ROOT / ADVICE_RUBRIC).read_bytes())
    (tmp_path / "data" / "register_rubric.json").write_bytes((ROOT / REGISTER_RUBRIC).read_bytes())
    shutil.copytree(ROOT / "docs" / "framework", tmp_path / "docs" / "framework")
    rows = [json.loads(line) for line in (run / "analysis_rows.jsonl").read_text(encoding="utf-8").splitlines()]
    for r in rows:
        if r["conversation_id"] == CONV_A:
            r["arm"] = "clinical"
    (run / "analysis_rows.jsonl").unlink()
    (run / "analysis_rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    payload = build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)
    assert payload["conversations"][CONV_A]["register"] == "colloquial"
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    manifest["trees"][0]["arm"] = "tampered"
    (run / "manifest.json").unlink()
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)
    assert exc.value.code == 2



def test_resealed_manifest_with_altered_trees_refused(tmp_path, mock_report_data):
    """Altering a tree's arm and resealing the manifest keeps verify_run happy and the transcripts digest unchanged,
    but the scored transcripts still name the old manifest identity, so the trees are refused (Codex review of
    PR #107)."""
    import shutil
    from scripts.petri_audit.manifest import seal_manifest
    src = ROOT / "data" / "petri" / "runs" / "run_35937014168_1"
    shutil.copytree(src.parent, tmp_path / "data" / "petri" / "runs", copy_function=_link_or_copy)
    run = tmp_path / "data" / "petri" / "runs" / src.name
    (tmp_path / "data" / "advice_rubric.draft.json").write_bytes((ROOT / ADVICE_RUBRIC).read_bytes())
    (tmp_path / "data" / "register_rubric.json").write_bytes((ROOT / REGISTER_RUBRIC).read_bytes())
    shutil.copytree(ROOT / "docs" / "framework", tmp_path / "docs" / "framework")
    build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)      # the untouched copy passes
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    for tree in manifest["trees"]:
        if any(b["conversation_id"] == CONV_B for b in tree["branches"]):
            tree["arm"] = "colloquial"
    resealed = seal_manifest({k: v for k, v in manifest.items() if k != "chain"}, manifest["chain"]["prev_sha256"])
    (run / "manifest.json").unlink()
    (run / "manifest.json").write_text(json.dumps(resealed), encoding="utf-8")
    from scripts.petri_audit.manifest import verify_run
    assert verify_run(run) == []                                                            # the reseal verifies
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)
    assert exc.value.code == 2



def test_initial_only_arm_register_is_its_first_turns():
    """An initial_only seed's later turns may carry `not_applicable`; the arm's register is its first turn's, as the
    seed validator defines it, so its two arms stay distinct (Codex review of PR #107). The committed wave-1 run holds
    such a seed (pw-petri-example-h3-tools)."""
    import hashlib as _h
    from scripts.export_jev_calibration import conversation_arms
    path = "data/petri/runs/run_35351739969_1/transcripts.jsonl"
    meta = {"petri_transcripts": {"path": path, "sha256": _h.sha256((ROOT / path).read_bytes()).hexdigest()}}
    arms = conversation_arms(meta)
    h3 = {a["arm"]: a["register"] for a in arms.values() if a["seed_id"] == "pw-petri-example-h3-tools"}
    assert h3 and all(r is not None for r in h3.values())
    assert len(set(h3.values())) == len(h3)                 # one register per arm, none collapsed



@pytest.mark.parametrize("value", [None, "", 3])
def test_report_without_a_requested_model_refused_before_writing(tmp_path, mock_report_data, value):
    mock_report_data["metadata"]["model_requested"] = value
    report = tmp_path / "r.json"
    report.write_text(json.dumps(mock_report_data), encoding="utf-8")
    site_data = tmp_path / "site" / "data"
    site_data.mkdir(parents=True)
    with pytest.raises(SystemExit) as exc:
        main(["--report", str(report), "--site", str(tmp_path / "site")])
    assert exc.value.code == 2
    assert list(site_data.iterdir()) == []


def test_run_not_named_by_the_manifest_chain_refused(tmp_path, mock_report_data):
    """The exporter trusts a run's trees only when the repository's manifest chain names that manifest at its digest
    and verifies through it (Codex review of PR #107)."""
    import shutil
    src = ROOT / "data" / "petri" / "runs"
    shutil.copytree(src, tmp_path / "data" / "petri" / "runs", copy_function=_link_or_copy)
    (tmp_path / "data" / "advice_rubric.draft.json").write_bytes((ROOT / ADVICE_RUBRIC).read_bytes())
    (tmp_path / "data" / "register_rubric.json").write_bytes((ROOT / REGISTER_RUBRIC).read_bytes())
    shutil.copytree(ROOT / "docs" / "framework", tmp_path / "docs" / "framework")
    build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)      # named and intact: passes
    chain = tmp_path / "data" / "petri" / "runs" / "manifests.chain"
    kept = [ln for ln in chain.read_text(encoding="utf-8").splitlines() if "run_35937014168_1" not in ln]
    chain.unlink()
    chain.write_text("\n".join(kept) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)
    assert exc.value.code == 2


def test_malformed_manifest_chain_line_refused_cleanly(tmp_path, mock_report_data):
    import shutil
    src = ROOT / "data" / "petri" / "runs"
    shutil.copytree(src, tmp_path / "data" / "petri" / "runs", copy_function=_link_or_copy)
    (tmp_path / "data" / "advice_rubric.draft.json").write_bytes((ROOT / ADVICE_RUBRIC).read_bytes())
    (tmp_path / "data" / "register_rubric.json").write_bytes((ROOT / REGISTER_RUBRIC).read_bytes())
    shutil.copytree(ROOT / "docs" / "framework", tmp_path / "docs" / "framework")
    chain = tmp_path / "data" / "petri" / "runs" / "manifests.chain"
    lines = chain.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].rsplit(" ", 1)[0]                                 # a line without its digest
    chain.unlink()
    chain.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        build_petri_drift_payload(mock_report_data, report_sha="sha", repo_root=tmp_path)
    assert exc.value.code == 2


# Several runs in one export (owner decision D3, 2026-10-14): one advice report plus Petri-only reports
# (audit_jev_calibration.py --skip-advice), pooled as conversations. The second run is the committed equity run eq02,
# so its arm placement also runs end to end; its two conversations here are a colloquial and a careful-lay patient.
EQ02_TRANSCRIPTS = "data/petri/runs/run_38434195912_1/transcripts.jsonl"
EQ02_SHA = hashlib.sha256((ROOT / EQ02_TRANSCRIPTS).read_bytes()).hexdigest()
EQ02_A = "85726acbafe748de9fb0024d071f9da94c192a61fd7c908c4e82afda1f9756bd"
EQ02_B = "3d1e05bc3b41d0c9b2c6650ba42da9b63c85dc6d068a2b20ee03d4f8668c9201"
# Combining resolves each report's classifier digest to the files behind it (resolve_classifier), so these reports
# carry the digest of this checkout's three files, as an audit run here would record it.
CLASSIFIER_FILES = ("scripts/jev_classifier.py", "medlang_circuits/jev_client.py", "scripts/audit_jev_calibration.py")
WORKTREE_CLASSIFIER = hashlib.sha256(b"".join((ROOT / f).read_bytes() for f in CLASSIFIER_FILES)).hexdigest()
# The first live report (2026-10-12) ran at this commit; its digest is the one it recorded
LIVE_REPORT_COMMIT, LIVE_REPORT_CLASSIFIER = ("8a29a30f82", "a38069f85f0dbd4f0a084f404bb52914cb0e4590386b11b2d91f427bc9b6f145")


@pytest.fixture
def advice_report(mock_report_data) -> dict:
    report = json.loads(json.dumps(mock_report_data))
    report["metadata"]["classifier"]["sha256"] = WORKTREE_CLASSIFIER
    return report


def _petri_only(base: dict) -> dict:
    """A Petri-only report over eq02 with the same instrument as `base`, as --skip-advice writes it."""
    meta = {k: v for k, v in json.loads(json.dumps(base["metadata"])).items()
            if k not in ("advice_archive", "advice_judgments")}
    meta["timestamp_utc"] = "2026-10-14T01:00:00Z"
    meta["petri_transcripts"] = {"path": EQ02_TRANSCRIPTS, "sha256": EQ02_SHA, "turns_evaluated": 3}
    row = dict(base["petri_cases"][0], cost_usd=0.0002, estimated_cost_usd=0.0002, input_tokens=100)
    rows = [dict(row, conversation_id=EQ02_A, turn_index=1),
            dict(row, conversation_id=EQ02_A, turn_index=3, has_register_drift=True, drift_probability=0.7),
            dict(row, conversation_id=EQ02_B, turn_index=1)]
    metrics = {"total_cases": 0, "total_cost_usd": 0.0006, "total_estimated_cost_usd": 0.0006,
               "total_input_tokens": 300, "unbilled_calls_count": 0, "tier_order": TIERS}
    return {"metadata": meta, "metrics": metrics, "cases": [], "petri_cases": rows}


def _write_reports(tmp_path: Path, *docs: dict) -> list[str]:
    paths = []
    for i, doc in enumerate(docs):
        path = tmp_path / f"r{i}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        paths.append(str(path))
    return paths


def _export(tmp_path: Path, paths: list[str], *extra: str) -> int:
    (tmp_path / "site" / "data").mkdir(parents=True, exist_ok=True)
    return main([arg for p in paths for arg in ("--report", p)] + ["--site", str(tmp_path / "site"), *extra])


def _site(tmp_path: Path, name: str) -> dict:
    return json.loads((tmp_path / "site" / "data" / name).read_text(encoding="utf-8"))


def test_a_combined_export_pools_the_petri_runs_and_keeps_the_advice_report(tmp_path, advice_report):
    paths = _write_reports(tmp_path, advice_report, _petri_only(advice_report))
    shas = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]
    assert _export(tmp_path, paths) == 0
    calib, petri = _site(tmp_path, "jev_calibration.json"), _site(tmp_path, "petri_register_drift.json")
    combined = hashlib.sha256("".join(f"{s}\n" for s in sorted(shas)).encode("ascii")).hexdigest()
    assert calib["source_report_sha256"] == petri["source_report_sha256"] == combined
    assert [e["sha256"] for e in calib["source_reports"]] == shas and calib["source_reports"] == petri["source_reports"]
    assert calib["headline_metrics"]["total_advice_cases"] == 4        # the advice report's, unchanged
    head = petri["headline_metrics"]
    assert (head["total_conversations"], head["total_assistant_turns"]) == (4, 6)
    assert head["petri_phase_spend"]["cost_usd"] == pytest.approx(0.0006)
    assert [(r["run"], r["conversations"]) for r in petri["provenance"]["petri_runs"]] == [
        ("run_35937014168_1", 2), ("run_38434195912_1", 2)]
    assert petri["provenance"]["petri_transcripts"] is None             # several runs: named in petri_runs
    assert petri["conversations"][EQ02_A]["run"] == "run_38434195912_1"
    assert petri["conversations"][CONV_A]["run"] == "run_35937014168_1"
    app = head["applicable"]
    assert (app["conversations"], app["conversations_with_drift"]) == (4, 2)


def test_the_combined_identifier_does_not_depend_on_report_order(tmp_path, advice_report):
    paths = _write_reports(tmp_path, advice_report, _petri_only(advice_report))
    assert _export(tmp_path, paths) == 0
    first = _site(tmp_path, "petri_register_drift.json")["source_report_sha256"]
    assert _export(tmp_path, paths[::-1]) == 0
    assert _site(tmp_path, "petri_register_drift.json")["source_report_sha256"] == first


def test_a_single_report_export_names_its_report_and_run(tmp_path, advice_report):
    (path,) = _write_reports(tmp_path, advice_report)
    assert _export(tmp_path, [path]) == 0
    petri = _site(tmp_path, "petri_register_drift.json")
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert petri["source_report_sha256"] == sha and [e["sha256"] for e in petri["source_reports"]] == [sha]
    assert petri["provenance"]["petri_transcripts"]["path"] == PETRI_RUN_TRANSCRIPTS     # unchanged for one report
    assert [r["run"] for r in petri["provenance"]["petri_runs"]] == ["run_35937014168_1"]


def test_combined_payloads_pass_the_site_contract_gate(tmp_path, advice_report):
    import importlib.util
    spec = importlib.util.spec_from_file_location("vfc", ROOT / "scripts" / "validate_frontend_contract.py")
    vfc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vfc)
    assert _export(tmp_path, _write_reports(tmp_path, advice_report, _petri_only(advice_report))) == 0
    rep = vfc.Report()
    vfc.check_jev_payloads(rep, tmp_path / "site")
    assert rep.errors == [] and rep.warnings == []
    # the gate recomputes the identifier from the listed reports, and holds the two payloads' lists equal
    petri_path = tmp_path / "site" / "data" / "petri_register_drift.json"
    petri = json.loads(petri_path.read_text(encoding="utf-8"))
    petri["source_reports"] = petri["source_reports"][:1]
    petri_path.write_text(json.dumps(petri), encoding="utf-8")
    rep = vfc.Report()
    vfc.check_jev_payloads(rep, tmp_path / "site")
    assert any("source_report_sha256" in str(e) for e in rep.errors)
    assert any("different source reports" in str(e) for e in rep.errors)
    # one payload listing its reports and the other not is a partial pair (Codex review of PR #111)
    del petri["source_reports"]
    petri_path.write_text(json.dumps(petri), encoding="utf-8")
    rep = vfc.Report()
    vfc.check_jev_payloads(rep, tmp_path / "site")
    assert any("only one of the two Jev payloads" in str(e) for e in rep.errors)


def _refused(tmp_path: Path, docs: list[dict], fragment: str, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        _export(tmp_path, _write_reports(tmp_path, *docs), "--dry-run")
    assert exc.value.code == 2
    assert fragment in capsys.readouterr().err


def test_combining_refuses_two_advice_reports(tmp_path, advice_report, capsys):
    other = json.loads(json.dumps(advice_report))
    other["metadata"]["timestamp_utc"] = "2026-10-13T00:00:00Z"
    del other["metadata"]["petri_transcripts"]          # advice only, so only the advice rule applies
    other["petri_cases"] = []
    _refused(tmp_path, [advice_report, other], "2 of the reports carry advice cases", capsys)


def test_combining_refuses_the_same_report_twice_and_no_advice_report(tmp_path, advice_report, capsys):
    only = _petri_only(advice_report)
    _refused(tmp_path, [only, only], "same report", capsys)
    other = json.loads(json.dumps(only))
    path = "data/petri/runs/run_36076994201_1/transcripts.jsonl"
    other["metadata"]["petri_transcripts"] = {"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                                              "turns_evaluated": 3}
    _refused(tmp_path, [only, other], "0 of the reports carry advice cases", capsys)


@pytest.mark.parametrize("change, fragment", [
    (lambda m: m["metadata"].update(model_requested="typesafe/jev-2"), "one instrument"),
    (lambda m: m["metadata"].update(is_mock=True), "one instrument"),
    (lambda m: m["metadata"]["classifier"].update(sha256="d" * 64), "matches no commit"),
    (lambda m: m["metadata"]["register_rubric"].update(sha256="e" * 64), "one instrument"),
    (lambda m: m["metadata"].update(golden_benchmark={"path": "x", "sha256": "a" * 64}), "golden_benchmark"),
    (lambda m: m["metrics"].update(total_cost_usd=0.5), "does not equal the sum of its rows"),
    (lambda m: m["metadata"].update(petri_transcripts={"path": PETRI_RUN_TRANSCRIPTS, "sha256": PETRI_RUN_SHA,
                                                       "turns_evaluated": 3}), "same Petri transcripts"),
])
def test_combining_refuses_reports_that_are_not_one_instrument_or_overlap(tmp_path, advice_report, capsys,
                                                                         change, fragment):
    other = _petri_only(advice_report)
    change(other)
    _refused(tmp_path, [advice_report, other], fragment, capsys)


def test_a_conversation_in_two_reports_is_refused(advice_report):
    from scripts.export_jev_calibration import build_combined_petri_drift_payload
    other = _petri_only(advice_report)
    other["petri_cases"][0]["conversation_id"] = CONV_A
    arms = [{c: SYNTHETIC_ARM for c in (CONV_A, CONV_B)}, {c: SYNTHETIC_ARM for c in (CONV_A, EQ02_A, EQ02_B)}]
    with pytest.raises(SystemExit):
        build_combined_petri_drift_payload([(advice_report, "a" * 64), (other, "b" * 64)], arms=arms)


def test_a_runner_change_combines_only_with_a_reviewed_equivalence(tmp_path, advice_report, monkeypatch, capsys):
    """Codex review of PR #111: the recorded digest covers the runner, so a new runner gave every new report another
    digest; the scoring files are compared through resolve_classifier. The runner also selects the scored turns and
    builds their context (round 3), so two runner versions combine only when a reviewed entry links them."""
    import scripts.export_jev_calibration as ex
    other = _petri_only(advice_report)
    other["metadata"]["classifier"]["sha256"] = "9" * 64
    real = ex.resolve_classifier
    same_scoring = real(WORKTREE_CLASSIFIER)
    monkeypatch.setattr(ex, "resolve_classifier", lambda digest, repo_root=ex.REPO_ROOT, hint=None: (
        {**same_scoring, "commit": "f" * 40, "evaluator_sha256": "e" * 64} if digest == "9" * 64
        else real(digest, repo_root, hint)))
    _refused(tmp_path, [advice_report, other], "audit runner version", capsys)
    monkeypatch.setattr(ex, "evaluator_classes", lambda repo_root=ex.REPO_ROOT: {
        "e" * 64: same_scoring["evaluator_sha256"], same_scoring["evaluator_sha256"]: same_scoring["evaluator_sha256"]})
    assert _export(tmp_path, _write_reports(tmp_path, advice_report, other)) == 0
    entries = _site(tmp_path, "petri_register_drift.json")["source_reports"]
    assert [e["evaluator_sha256"] == "e" * 64 for e in entries] == [False, True]
    assert entries[0]["scoring_sha256"] == entries[1]["scoring_sha256"]
    # the pooled payload names each run's classifier digest, not the first run's for all (Codex review of PR #111)
    prov = _site(tmp_path, "petri_register_drift.json")["provenance"]
    assert prov["classifier_sha256"] is None
    assert [r["classifier_sha256"] for r in prov["petri_runs"]] == [WORKTREE_CLASSIFIER, "9" * 64]
    # and the dated models that scored each run (round 3)
    assert all(r["models_served"] == ["typesafe/jev-1.13-20261001"] for r in prov["petri_runs"])


def test_the_equivalence_file_is_a_reviewed_union(tmp_path):
    import scripts.export_jev_calibration as ex
    (tmp_path / "data" / "jev").mkdir(parents=True)
    path = tmp_path / ex.EVALUATOR_EQUIVALENCE
    a, b, c = "a" * 64, "b" * 64, "c" * 64
    entry = {"reason": "flags and spend accounting only", "reviewed_utc": "2026-10-14T00:00:00Z"}
    path.write_text(json.dumps({"equivalences": [{"evaluator_sha256": a, "equivalent_to": b, **entry},
                                                 {"evaluator_sha256": b, "equivalent_to": c, **entry}]}))
    classes = ex.evaluator_classes(tmp_path)
    assert classes[a] == classes[b] == classes[c]
    path.write_text(json.dumps({"equivalences": [{"evaluator_sha256": a, "equivalent_to": b}]}))
    with pytest.raises(SystemExit):
        ex.evaluator_classes(tmp_path)
    assert ex.evaluator_classes(ROOT) == {}            # the committed file lists no equivalence yet


def test_another_scoring_implementation_is_refused(tmp_path, advice_report, monkeypatch, capsys):
    import scripts.export_jev_calibration as ex
    other = _petri_only(advice_report)
    other["metadata"]["classifier"]["sha256"] = "9" * 64
    real = ex.resolve_classifier
    monkeypatch.setattr(ex, "resolve_classifier", lambda digest, repo_root=ex.REPO_ROOT, hint=None: (
        {"commit": "f" * 40, "scoring_sha256": "5" * 64, "evaluator_sha256": "e" * 64} if digest == "9" * 64
        else real(digest, repo_root, hint)))
    _refused(tmp_path, [advice_report, other], "scoring implementation", capsys)


@pytest.mark.skipif(subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{LIVE_REPORT_COMMIT}^{{commit}}"],
                                   capture_output=True).returncode != 0,
                    reason="this clone lacks the commit the first live report ran at (a shallow clone)")
def test_the_first_live_reports_digest_resolves_to_its_commit():
    """The first live report's recorded digest is found in history, at the commit it ran, with the scoring files that
    this checkout's main carried at the time."""
    from scripts.export_jev_calibration import resolve_classifier
    found = resolve_classifier(LIVE_REPORT_CLASSIFIER)
    assert found is not None and found["commit"].startswith(LIVE_REPORT_COMMIT)


def test_one_unreadable_object_does_not_hide_the_commit_a_report_ran_at(monkeypatch):
    """Codex review of PR #111: `git log --all` stops at the first unreadable object, which discarded every candidate.
    The search keeps the partial output and walks each ref on its own, skipping one that cannot be read."""
    import scripts.export_jev_calibration as ex
    files = (*ex.JEV_SCORING_FILES, ex.JEV_EVALUATOR_FILE)
    body = {f: f"content of {f}".encode() for f in files}
    digest = hashlib.sha256(b"".join(body[f] for f in files)).hexdigest()

    def fake_git(repo_root, *args):
        ok = lambda out: subprocess.CompletedProcess(args, 0, out.encode(), b"")   # noqa: E731
        bad = subprocess.CompletedProcess(args, 128, b"", b"fatal: missing tree")
        if args[:2] == ("log", "--all"):
            return bad
        if args[0] == "for-each-ref":
            return ok("refs/heads/broken\nrefs/heads/main\n")
        if args[:2] == ("log", "refs/heads/broken"):
            return bad
        if args[:2] == ("log", "refs/heads/main"):
            return ok("goodcommit\n")
        if args[0] == "show" and args[1].startswith("goodcommit:"):
            return subprocess.CompletedProcess(args, 0, body[args[1].split(":", 1)[1]], b"")
        return bad
    monkeypatch.setattr(ex, "_git", fake_git)
    found = ex.resolve_classifier(digest, repo_root=Path("/nonexistent"))
    assert found is not None and found["commit"] == "goodcommit"
    assert ex.resolve_classifier(digest, repo_root=Path("/nonexistent"), hint="goodcommit")["commit"] == "goodcommit"


def test_the_recorded_commit_is_kept_when_the_worktree_also_matches():
    """Codex review of PR #111: a new report that names its commit keeps it, even when this checkout's three files
    give the same digest (the worktree match has no commit to name)."""
    import scripts.export_jev_calibration as ex
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    files = (*ex.JEV_SCORING_FILES, ex.JEV_EVALUATOR_FILE)
    at_head = [subprocess.run(["git", "-C", str(ROOT), "show", f"{head}:{f}"], capture_output=True).stdout for f in files]
    digest = hashlib.sha256(b"".join(at_head)).hexdigest()
    found = ex.resolve_classifier(digest, hint=head)
    assert found is not None and found["commit"] == head


def test_the_gate_reconciles_run_attribution(tmp_path, advice_report):
    """Codex review of PR #111, round 3: a combined payload whose petri_runs is missing or whose conversations name
    another run is refused by the site gate."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vfc", ROOT / "scripts" / "validate_frontend_contract.py")
    vfc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vfc)
    assert _export(tmp_path, _write_reports(tmp_path, advice_report, _petri_only(advice_report))) == 0
    path = tmp_path / "site" / "data" / "petri_register_drift.json"
    good = json.loads(path.read_text(encoding="utf-8"))

    def errors(doc: dict) -> list:
        path.write_text(json.dumps(doc), encoding="utf-8")
        rep = vfc.Report()
        vfc.check_jev_payloads(rep, tmp_path / "site")
        return [str(e) for e in rep.errors]
    assert errors(good) == []
    no_runs = json.loads(json.dumps(good))
    del no_runs["provenance"]["petri_runs"]
    assert any("petri_runs" in e and "missing" in e for e in errors(no_runs))
    moved = json.loads(json.dumps(good))
    moved["conversations"][EQ02_A]["run"] = "run_00000000000_1"
    assert any("not a run listed" in e for e in errors(moved))
    short = json.loads(json.dumps(good))
    short["provenance"]["petri_runs"][1]["conversations"] = 1
    assert any("lists 1 conversation" in e for e in errors(short))
    # Codex review of PR #111, round 4: deleting the row counts as well cannot make it pass as a legacy payload
    stripped = json.loads(json.dumps(good))
    del stripped["provenance"]["petri_runs"]
    for entry in stripped["source_reports"]:
        del entry["petri_turns"]
    assert any("petri_turns" in e and "non-negative integer" in e for e in errors(stripped))
    # round 5: a count set to zero, with petri_runs removed, no longer passes as a single-run payload
    zeroed = json.loads(json.dumps(good))
    del zeroed["provenance"]["petri_runs"]
    zeroed["source_reports"][1]["petri_turns"] = 0
    assert any("sum to" in e and "total_assistant_turns" in e for e in errors(zeroed))
