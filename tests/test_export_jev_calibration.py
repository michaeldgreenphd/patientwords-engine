"""Tests for scripts/export_jev_calibration.py."""

from __future__ import annotations

import json
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
            "tier_order": TIERS,
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
                "primary_judge_tier": TIERS[0],
                "predicted_tier": TIERS[0],
                "tier_confidence": 0.95,
                "tier_probabilities": {TIERS[0]: 0.95, TIERS[1]: 0.05},
                "technicality_score": 1.2,
                "is_exact": True,
                "is_within_one": True,
                "flags": {"safety_netting": True},
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
                "flags": {"safety_netting": True},
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
                "flags": {"safety_netting": False},
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
    assert payload["headline_metrics"]["exact_agreement"] == 0.75
    assert payload["headline_metrics"]["within_one_agreement"] == 1.0
    assert payload["agreement_reference"] == "primary_judge"
    assert "exact_accuracy" not in payload["headline_metrics"]
    assert payload["headline_metrics"]["brier_score"] == 0.15

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


def test_tier_order_loaded_from_data_when_missing_in_report(mock_report_data):
    del mock_report_data["metrics"]["tier_order"]
    payload = build_calibration_payload(mock_report_data, report_sha="sha")
    assert isinstance(payload["tier_order"], list)
    assert len(payload["tier_order"]) >= 4


def test_unjudged_report_handles_null_metrics_cleanly(mock_report_data):
    mock_report_data["metrics"]["exact_accuracy"] = None
    mock_report_data["metrics"]["within_one_accuracy"] = None
    mock_report_data["metrics"]["brier_score"] = None
    mock_report_data["metrics"]["exact_tier_matches"] = None
    mock_report_data["metrics"]["within_one_tier_matches"] = None
    mock_report_data["metrics"]["confusion_matrix"] = None

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


def test_unbilled_calls_caveat_preserved(mock_report_data):
    mock_report_data["metrics"]["unbilled_calls_count"] = 5
    mock_report_data["metrics"]["total_estimated_cost_usd"] = 0.0012
    payload = build_calibration_payload(mock_report_data, report_sha="sha")
    head = payload["headline_metrics"]
    assert head["unbilled_calls_count"] == 5
    assert head["total_estimated_cost_usd"] == 0.0012
    assert head["cost_caveat"] is not None
    assert "5 calls with null provider billing" in head["cost_caveat"]


def test_stale_petri_output_cleaned_when_input_has_none(tmp_path, mock_report_data):
    mock_report_data["petri_cases"] = []
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
    urgent = next(t for t in div["per_primary_judge_tier"] if t["primary_judge_tier"] == TIERS[2])
    assert (urgent["n"], urgent["agreed"], urgent["agreement"]) == (119, 39, pytest.approx(0.3277, abs=1e-4))
    assert urgent["ci95_low"] < urgent["agreement"] < urgent["ci95_high"]
    assert urgent["most_common_jev_tier_otherwise"]["jev_tier"] == TIERS[3]
    assert urgent["most_common_jev_tier_otherwise"]["count"] == 67
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
    # the fixture has no urgent or emergency rows: their agreement is null, never 0
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
             "has_register_drift": i < 11} for i in range(30)]
    payload = build_petri_drift_payload({"metadata": {"is_mock": False}, "petri_cases": rows}, report_sha="sha")
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
    mock_report_data["metrics"]["unbilled_calls_count"] = 2
    mock_report_data["metrics"]["total_estimated_cost_usd"] = 0.0012
    caveat = build_calibration_payload(mock_report_data, report_sha="sha")["headline_metrics"]["cost_caveat"]
    assert "across all calls" in caveat and "$0.001200" in caveat


def test_flag_match_rate_is_published_as_agreement(mock_report_data):
    flags = build_calibration_payload(mock_report_data, report_sha="sha")["flag_metrics"]
    assert flags["safety_netting"]["agreement"] == 1.0
    assert "accuracy" not in flags["safety_netting"]


def test_payload_carries_input_provenance(mock_report_data):
    meta = mock_report_data["metadata"]
    meta["rubric"] = {"path": "data/advice_rubric.draft.json", "sha256": "r" * 64}
    meta["classifier"] = {"path": "/home/runner/x.py", "sha256": "c" * 64}
    meta["advice_archive"] = {"path": "data/advice/a.jsonl", "sha256": "a" * 64, "samples_evaluated": 4}
    meta["advice_judgments"]["sha256"] = "j" * 64
    prov = build_calibration_payload(mock_report_data, report_sha="sha")["provenance"]
    assert prov["rubric"]["sha256"] == "r" * 64
    assert prov["classifier_sha256"] == "c" * 64 and "/home/runner" not in json.dumps(prov)
    assert prov["advice_archive"]["samples_evaluated"] == 4
    assert prov["advice_judgments"]["sha256"] == "j" * 64
    assert prov["register_rubric"] is None            # absent upstream: carried as null, not dropped


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
