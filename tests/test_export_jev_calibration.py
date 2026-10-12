"""Tests for scripts/export_jev_calibration.py."""

from __future__ import annotations

import json
import pytest

from scripts.export_jev_calibration import (
    build_calibration_payload,
    build_petri_drift_payload,
    load_report,
    main,
)


@pytest.fixture
def mock_report_data() -> dict:
    return {
        "metadata": {
            "timestamp_utc": "2026-10-12T20:00:00Z",
            "model_requested": "typesafe/jev-1.13",
            "models_served": ["typesafe/jev-1.13-20260917"],
            "is_mock": False,
            "advice_judgments": {
                "judge_model": "claude-haiku-4-5",
            },
        },
        "metrics": {
            "total_cases": 4,
            "exact_tier_matches": 3,
            "exact_accuracy": 0.75,
            "within_one_tier_matches": 4,
            "within_one_accuracy": 1.0,
            "brier_score": 0.15,
            "total_cost_usd": 0.0004,
            "total_input_tokens": 1200,
            "tier_order": ["self_care", "routine", "urgent", "emergency"],
            "confusion_matrix": [
                [2, 0, 0, 0],
                [0, 1, 1, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
            ],
            "flag_metrics": {
                "safety_netting": {
                    "accuracy": 1.0,
                    "precision": 1.0,
                    "sensitivity": 1.0,
                    "specificity": 1.0,
                    "tp": 2,
                    "tn": 2,
                    "fp": 0,
                    "fn": 0,
                }
            },
        },
        "cases": [
            {
                "id": "case_1",
                "response_text": "Holdout phrase that must NEVER leak to public payload",
                "primary_judge_tier": "self_care",
                "predicted_tier": "self_care",
                "tier_confidence": 0.95,
                "tier_probabilities": {"self_care": 0.95, "routine": 0.05},
                "technicality_score": 1.2,
                "is_exact": True,
                "is_within_one": True,
                "flags": {"safety_netting": True},
            },
            {
                "id": "case_2",
                "response_text": "Another private clinical response snippet",
                "primary_judge_tier": "self_care",
                "predicted_tier": "self_care",
                "tier_confidence": 0.90,
                "tier_probabilities": {"self_care": 0.90, "routine": 0.10},
                "technicality_score": 1.0,
                "is_exact": True,
                "is_within_one": True,
                "flags": {"safety_netting": True},
            },
            {
                "id": "case_3",
                "response_text": "Third response text",
                "primary_judge_tier": "routine",
                "predicted_tier": "routine",
                "tier_confidence": 0.85,
                "tier_probabilities": {"routine": 0.85, "urgent": 0.15},
                "technicality_score": 1.5,
                "is_exact": True,
                "is_within_one": True,
                "flags": {"safety_netting": False},
            },
            {
                "id": "case_4",
                "response_text": "Fourth response text",
                "primary_judge_tier": "routine",
                "predicted_tier": "urgent",
                "tier_confidence": 0.60,
                "tier_probabilities": {"routine": 0.40, "urgent": 0.60},
                "technicality_score": 2.1,
                "is_exact": False,
                "is_within_one": True,
                "flags": {"safety_netting": False},
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
            },
            {
                "conversation_id": "conv_a",
                "turn_index": 3,
                "tone_choice": "clinical",
                "tone_confidence": 0.75,
                "has_register_drift": True,
                "drift_probability": 0.78,
                "register_score": 2.2,
            },
            {
                "conversation_id": "conv_b",
                "turn_index": 1,
                "tone_choice": "mixed",
                "tone_confidence": 0.90,
                "has_register_drift": False,
                "drift_probability": 0.15,
                "register_score": 1.3,
            },
        ],
    }


def test_build_calibration_payload_structure_and_holdout_hygiene(mock_report_data):
    payload = build_calibration_payload(mock_report_data, report_sha="mocksha123")

    assert payload["source_report_sha256"] == "mocksha123"
    assert payload["headline_metrics"]["total_advice_cases"] == 4
    assert payload["headline_metrics"]["exact_accuracy"] == 0.75
    assert payload["headline_metrics"]["within_one_accuracy"] == 1.0
    assert payload["headline_metrics"]["brier_score"] == 0.15

    # Critical security/holdout test: no response_text anywhere in exported payload
    payload_str = json.dumps(payload)
    assert "Holdout phrase that must NEVER leak" not in payload_str
    assert "response_text" not in payload_str

    # Cases summary check
    assert len(payload["cases_summary"]) == 4
    c1 = payload["cases_summary"]["case_1"]
    assert c1["gold_tier"] == "self_care"
    assert c1["pred_tier"] == "self_care"
    assert c1["tier_confidence"] == 0.95
    assert c1["flags"]["safety_netting"] is True


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
    assert by_turn[0]["turn_index"] == 1
    assert by_turn[0]["assistant_turns"] == 2
    assert by_turn[0]["drift_turns"] == 0
    assert by_turn[1]["turn_index"] == 3
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
