"""Tests for scripts/export_jev_calibration.py."""

from __future__ import annotations

import hashlib
import json
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
PERFECT_FLAG = {"accuracy": 1.0, "precision": 1.0, "sensitivity": 1.0, "specificity": 1.0, "tp": 2, "tn": 2, "fp": 0,
                "fn": 0}


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
            "petri_transcripts": {"path": "data/petri/runs/run_fixture_1/transcripts.jsonl", "sha256": "e" * 64,
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
                "conversation_id": "conv_a",
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
                "conversation_id": "conv_a",
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
                "conversation_id": "conv_b",
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
    assert head["overall_drift_count"] == 1
    assert head["overall_drift_rate"] == pytest.approx(0.3333, rel=1e-3)
    assert head["tone_distribution"] == {"mixed": 2, "clinical": 1}

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
    assert len(convs["conv_a"]) == 2
    assert convs["conv_a"][0]["turn_index"] == 1
    assert convs["conv_a"][1]["turn_index"] == 3
    assert convs["conv_a"][1]["has_register_drift"] is True


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
    meta = {"is_mock": False, "classifier": {"sha256": "c" * 64},
            "rubric": {"path": ADVICE_RUBRIC, "sha256": ADVICE_SHA},
            "register_rubric": {"path": REGISTER_RUBRIC, "sha256": REGISTER_SHA},
            "petri_transcripts": {"path": "x/transcripts.jsonl", "sha256": "e" * 64, "turns_evaluated": 30}}
    payload = build_petri_drift_payload({"metadata": meta, "petri_cases": rows}, report_sha="sha")
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
    meta["petri_transcripts"] = {"path": "data/petri/runs/run_1_1/transcripts.jsonl", "sha256": "e" * 64,
                                 "turns_evaluated": 3}
    prov = build_petri_drift_payload(mock_report_data, report_sha="sha")["provenance"]
    assert prov["classifier_sha256"] == "c" * 64
    assert prov["register_rubric"]["sha256"] == REGISTER_SHA
    assert prov["petri_transcripts"]["sha256"] == "e" * 64
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
    payload = build_petri_drift_payload(mock_report_data, report_sha="sha")
    second = payload["drift_by_turn"][1]
    assert (second["assistant_turn_ordinal"], second["n"], second["drift_turns"]) == (2, 2, 1)
    assert second["turn_indices"] == [3, 4]
    assert [r["assistant_turn_ordinal"] for r in payload["conversations"]["b"]] == [1, 2]


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
    assert head["formality_scored_turns"] == 2 and head["total_assistant_turns"] == 3


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
