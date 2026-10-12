"""Tests for classifier audit and calibration script (scripts/audit_jev_calibration.py)."""

from __future__ import annotations

import json

import pytest

from scripts.audit_jev_calibration import (
    compute_brier_score,
    evaluate_petri_classifier,
    load_advice_archive_with_judgments,
    main,
)


TIER_ORDER = ["self_care", "routine", "urgent", "emergency"]


def test_compute_brier_score_perfect():
    preds = [{"self_care": 1.0, "routine": 0.0, "urgent": 0.0, "emergency": 0.0}]
    truth = ["self_care"]
    assert compute_brier_score(preds, truth, TIER_ORDER) == 0.0


def test_compute_brier_score_imperfect():
    preds = [{"self_care": 0.8, "routine": 0.2, "urgent": 0.0, "emergency": 0.0}]
    truth = ["self_care"]
    # (0.8 - 1)^2 + (0.2 - 0)^2 = 0.04 + 0.04 = 0.08
    assert pytest.approx(compute_brier_score(preds, truth, TIER_ORDER), 1e-4) == 0.08


def test_audit_calibration_main_mock(tmp_path):
    out_md = tmp_path / "report.md"
    out_json = tmp_path / "report.json"

    ret = main([
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0
    assert out_md.is_file()
    assert out_json.is_file()

    md_text = out_md.read_text(encoding="utf-8")
    assert "Classifier Calibration & Benchmark Audit Report" in md_text
    assert "Tier Confusion Matrix" in md_text
    assert "Binary Flag Performance" in md_text

    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert doc["metrics"]["exact_accuracy"] == 1.0
    assert len(doc["cases"]) == 6
    assert "rubric" in doc["metadata"]
    assert "golden_benchmark" in doc["metadata"]


def test_audit_calibration_refusals(tmp_path, monkeypatch):
    # 1. --ci-live outside GitHub Actions
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert main(["--ci-live"]) == 1

    # 2. Missing archive
    assert main(["--archive", str(tmp_path / "nonexistent.jsonl")]) == 1

    # 3. Missing petri transcripts
    assert main(["--petri-transcripts", str(tmp_path / "nonexistent.jsonl")]) == 1

    # 4. Missing golden
    assert main(["--golden", str(tmp_path / "nonexistent.json")]) == 1

    # 5. Empty golden cases
    empty_golden = tmp_path / "empty_golden.json"
    empty_golden.write_text(json.dumps({"cases": []}), encoding="utf-8")
    assert main(["--golden", str(empty_golden)]) == 1

    # 6. Rubric with no valid tier IDs
    no_id_rubric = tmp_path / "no_id_rubric.json"
    no_id_rubric.write_text(json.dumps({"tiers": [{}]}), encoding="utf-8")
    assert main(["--rubric", str(no_id_rubric)]) == 1

    # 7. Broken hash chain in response archive
    broken_arch = tmp_path / "broken_arch.jsonl"
    broken_arch.write_text(json.dumps({"record_type": "advice", "record_sha256": "bad", "prev_sha256": "none"}) + "\n", encoding="utf-8")
    assert main(["--archive", str(broken_arch)]) == 1

    # 8. Petri transcript with no assistant turns
    user_only_petri = tmp_path / "user_only.jsonl"
    user_only_petri.write_text(json.dumps({"conversation_id": "c1", "turns": [{"role": "user", "text": "hello"}]}) + "\n", encoding="utf-8")
    assert main(["--petri-transcripts", str(user_only_petri)]) == 1

    # 9. Negative archive samples CLI refusal
    assert main(["--archive-samples", "-1"]) == 1

    # 10. Negative petri conversations CLI refusal
    assert main(["--petri-conversations", "-1"]) == 1

    # 11. Function-level negative limit validation
    with pytest.raises(ValueError, match="non-negative"):
        load_advice_archive_with_judgments(tmp_path / "dummy.jsonl", max_samples=-1)

    with pytest.raises(ValueError, match="non-negative"):
        evaluate_petri_classifier(tmp_path / "dummy.jsonl", classifier=None, max_conversations=-1)  # type: ignore


def test_audit_calibration_archive_and_petri(tmp_path):
    out_md = tmp_path / "report_combined.md"
    out_json = tmp_path / "report_combined.json"

    ret = main([
        "--archive", "data/advice/responses_stimuli_20260721T235403Z.jsonl",
        "--archive-samples", "3",
        "--petri-transcripts", "data/petri/runs/run_35937014168_1/transcripts.jsonl",
        "--petri-conversations", "2",
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0
    assert out_md.is_file()
    assert out_json.is_file()

    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert doc["metadata"]["parameters"]["petri_conversations"] == 2
    assert doc["metadata"]["parameters"]["archive_samples"] == 3
    assert "advice_archive" in doc["metadata"]
    assert "advice_judgments" in doc["metadata"]
    assert "petri_transcripts" in doc["metadata"]
    assert "register_rubric" in doc["metadata"]
    assert len(doc["cases"]) == 3

    # Check preserved flags from judgments file
    assert any(c["flags"] for c in doc["cases"])

    # Check that exactly 2 distinct Petri conversations were evaluated
    petri_cases = doc["petri_cases"]
    assert len(petri_cases) > 0
    conv_ids = {p["conversation_id"] for p in petri_cases}
    assert len(conv_ids) == 2

    # Check that total tokens include both advice and petri
    total_tokens = doc["metrics"]["total_input_tokens"]
    advice_tokens = sum(180 for _ in doc["cases"])  # 180 per case in mock
    petri_tokens = sum(p.get("input_tokens", 0) for p in petri_cases)
    assert total_tokens == advice_tokens + petri_tokens


def test_audit_calibration_all_mode(tmp_path):
    out_md = tmp_path / "report_all.md"
    out_json = tmp_path / "report_all.json"

    ret = main([
        "--archive", "data/advice/responses_stimuli_20260721T235403Z.jsonl",
        "--archive-samples", "0",
        "--petri-transcripts", "data/petri/runs/run_35937014168_1/transcripts.jsonl",
        "--petri-conversations", "0",
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0
    assert out_md.is_file()
    assert out_json.is_file()

    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert doc["metadata"]["parameters"]["petri_conversations"] == "all"
    assert doc["metadata"]["parameters"]["archive_samples"] == "all"
    assert doc["metadata"]["petri_transcripts"]["max_conversations"] == "all"
    assert len(doc["cases"]) > 1000
    assert doc["metadata"]["advice_archive"]["unmatched_responses_omitted"] >= 0
    conv_ids = {p["conversation_id"] for p in doc["petri_cases"]}
    assert len(conv_ids) == 30


def test_load_advice_archive_joined_by_response_sha256(tmp_path):
    from scripts.advice_eval import canonical_json, sha256_text

    def make_record(rec_data: dict, prev_sha: str | None) -> dict:
        body = dict(rec_data)
        body["prev_sha256"] = prev_sha
        body["record_sha256"] = sha256_text(canonical_json(body))
        return body

    rec1 = make_record({
        "record_type": "advice",
        "stimulus_id": "stim_01",
        "arm": "patient",
        "sample_k": 1,
        "model_requested": "vendor/model-a",
        "response_text": "Response text A from model A",
        "response_sha256": "aaaa1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
    }, None)

    rec2 = make_record({
        "record_type": "advice",
        "stimulus_id": "stim_01",
        "arm": "patient",
        "sample_k": 1,
        "model_requested": "vendor/model-b",
        "response_text": "Response text B from model B",
        "response_sha256": "bbbb1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
    }, rec1["record_sha256"])

    rec3 = make_record({
        "record_type": "advice",
        "stimulus_id": "stim_01",
        "arm": "patient",
        "sample_k": 1,
        "model_requested": "vendor/model-c",
        "response_text": "Response text C from model C (unparseable judgment)",
        "response_sha256": "cccc1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
    }, rec2["record_sha256"])

    resp_file = tmp_path / "responses.jsonl"
    resp_file.write_text(
        "\n".join(json.dumps(r) for r in [rec1, rec2, rec3]) + "\n",
        encoding="utf-8",
    )

    # Synthetic judgments file keyed by response_sha256
    j1 = {
        "response_sha256": rec1["response_sha256"],
        "tier": "routine",
        "flags": {"safety_netting": True},
    }
    j2 = {
        "response_sha256": rec2["response_sha256"],
        "tier": "emergency",
        "flags": {"safety_netting": False},
    }
    j3 = {
        "response_sha256": rec3["response_sha256"],
        "tier": None,
        "judge_error": "unparseable or unknown tier",
    }
    judg_file = tmp_path / "judgments.jsonl"
    judg_file.write_text(
        "\n".join(json.dumps(j) for j in [j1, j2, j3]) + "\n",
        encoding="utf-8",
    )

    cases, unmatched = load_advice_archive_with_judgments(resp_file, judgments_path=judg_file, max_samples=0)
    assert len(cases) == 2
    assert unmatched == 1

    # Verify each case was paired strictly with its OWN judgment
    assert cases[0]["model_requested"] == "vendor/model-a"
    assert cases[0]["expected_tier"] == "routine"
    assert cases[0]["expected_flags"]["safety_netting"] is True
    assert "aaaa1111" in cases[0]["id"]

    assert cases[1]["model_requested"] == "vendor/model-b"
    assert cases[1]["expected_tier"] == "emergency"
    assert cases[1]["expected_flags"]["safety_netting"] is False
    assert "bbbb1111" in cases[1]["id"]

    # Verify refusal when no responses match judgments
    mismatched_judg = tmp_path / "mismatched_judg.jsonl"
    mismatched_judg.write_text(
        json.dumps({"response_sha256": "nonexistent_sha", "tier": "routine"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="No advice responses matched judgments"):
        load_advice_archive_with_judgments(resp_file, judgments_path=mismatched_judg, max_samples=0)


def test_audit_calibration_checkpoint_save_and_resume(tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    out_md = tmp_path / "report_cp.md"
    out_json = tmp_path / "report_cp.json"

    # Initial run with checkpoint argument
    ret = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--checkpoint", str(checkpoint_file),
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0
    assert checkpoint_file.is_file()

    cp_doc = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert len(cp_doc["advice_cases"]) == 6

    # Second run resumes using the checkpoint file
    out_md2 = tmp_path / "report_cp2.md"
    out_json2 = tmp_path / "report_cp2.json"
    ret2 = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--checkpoint", str(checkpoint_file),
        "--out-markdown", str(out_md2),
        "--out-json", str(out_json2),
    ])
    assert ret2 == 0
    doc2 = json.loads(out_json2.read_text(encoding="utf-8"))
    assert doc2["metadata"]["checkpoint"]["resumed_advice_count"] == 6


def test_audit_calibration_interrupted_warning_report(tmp_path):
    from unittest.mock import patch
    from scripts.audit_jev_calibration import EvaluationInterruptedError

    out_md = tmp_path / "interrupted.md"
    out_json = tmp_path / "interrupted.json"
    checkpoint_file = tmp_path / "interrupted_checkpoint.json"

    # Simulate an interruption during advice evaluation that raises EvaluationInterruptedError
    with patch("scripts.audit_jev_calibration.evaluate_advice_classifier") as mock_eval:
        mock_eval.side_effect = EvaluationInterruptedError(
            "Live spend $0.150000 exceeded max_spend ceiling $0.100000",
            exit_code=6,
            metrics=None,
            case_reports=[],
        )
        ret = main([
            "--golden", "data/classifier_benchmark_golden.json",
            "--checkpoint", str(checkpoint_file),
            "--out-markdown", str(out_md),
            "--out-json", str(out_json),
        ])
        assert ret == 6


def test_secondary_judge_rows_ignored_and_primary_preserved(tmp_path):
    from scripts.advice_eval import canonical_json, sha256_text

    rec = {
        "record_type": "advice",
        "stimulus_id": "stim_01",
        "arm": "patient",
        "sample_k": 1,
        "model_requested": "vendor/model-a",
        "response_text": "Response text A from model A",
        "response_sha256": "aaaa1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
        "prev_sha256": None,
    }
    rec["record_sha256"] = sha256_text(canonical_json(rec))

    resp_file = tmp_path / "responses.jsonl"
    resp_file.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    # Primary judge row followed by secondary judge row for the same response_sha256
    j_primary = {
        "response_sha256": rec["response_sha256"],
        "judge_model": "claude-haiku-4-5",
        "tier": "routine",
        "flags": {"safety_netting": True},
    }
    j_secondary = {
        "response_sha256": rec["response_sha256"],
        "judge_model": "openrouter:stealth/ox-alpha",
        "tier": "emergency",
        "flags": {"safety_netting": False},
    }
    judg_file = tmp_path / "judgments.jsonl"
    judg_file.write_text(
        json.dumps(j_primary) + "\n" + json.dumps(j_secondary) + "\n",
        encoding="utf-8",
    )

    # By default, primary judge claude-haiku-4-5 is selected; secondary is ignored
    cases, unmatched = load_advice_archive_with_judgments(resp_file, judgments_path=judg_file, max_samples=0)
    assert len(cases) == 1
    assert unmatched == 0
    assert cases[0]["expected_tier"] == "routine"
    assert cases[0]["expected_flags"]["safety_netting"] is True

    # When explicit judge_model is specified, that judge is loaded
    cases_sec, _ = load_advice_archive_with_judgments(
        resp_file,
        judgments_path=judg_file,
        max_samples=0,
        judge_model="openrouter:stealth/ox-alpha",
    )
    assert len(cases_sec) == 1
    assert cases_sec[0]["expected_tier"] == "emergency"
    assert cases_sec[0]["expected_flags"]["safety_netting"] is False


def test_checkpoint_metadata_validation_refusal(tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    out_md = tmp_path / "report_cp.md"
    out_json = tmp_path / "report_cp.json"

    # Initial run creates checkpoint with metadata
    ret = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--checkpoint", str(checkpoint_file),
        "--model", "typesafe/jev-1.13",
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0
    assert checkpoint_file.is_file()

    cp_doc = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert cp_doc["metadata"]["model"] == "typesafe/jev-1.13"
    assert "rubric_sha256" in cp_doc["metadata"]
    assert "input_sha256" in cp_doc["metadata"]

    # Attempting to resume with a different model must refuse with exit code 1
    ret_mismatched_model = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--checkpoint", str(checkpoint_file),
        "--model", "typesafe/different-model",
        "--out-markdown", str(tmp_path / "bad.md"),
        "--out-json", str(tmp_path / "bad.json"),
    ])
    assert ret_mismatched_model == 1

    # Attempting to resume with a modified golden file must refuse with exit code 1
    modified_golden = tmp_path / "modified_golden.json"
    modified_golden.write_text(json.dumps({"cases": [{"id": "diff", "text": "diff"}]}), encoding="utf-8")
    ret_mismatched_input = main([
        "--golden", str(modified_golden),
        "--checkpoint", str(checkpoint_file),
        "--model", "typesafe/jev-1.13",
        "--out-markdown", str(tmp_path / "bad2.md"),
        "--out-json", str(tmp_path / "bad2.json"),
    ])
    assert ret_mismatched_input == 1


def test_advice_checkpoint_persists_input_tokens(tmp_path):
    checkpoint_file = tmp_path / "checkpoint_tokens.json"
    out_md = tmp_path / "report_tokens.md"
    out_json = tmp_path / "report_tokens.json"

    ret = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--checkpoint", str(checkpoint_file),
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0

    cp_doc = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    for case_rep in cp_doc["advice_cases"]:
        assert "input_tokens" in case_rep
        assert case_rep["input_tokens"] > 0

    # Resume run also correctly counts input tokens from the checkpoint
    out_json2 = tmp_path / "report_tokens2.json"
    ret2 = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--checkpoint", str(checkpoint_file),
        "--out-markdown", str(tmp_path / "report_tokens2.md"),
        "--out-json", str(out_json2),
    ])
    assert ret2 == 0
    doc2 = json.loads(out_json2.read_text(encoding="utf-8"))
    assert doc2["metrics"]["total_input_tokens"] > 0
    assert doc2["metrics"]["total_input_tokens"] == sum(c["input_tokens"] for c in doc2["cases"])


def test_interrupted_provenance_samples_evaluated_accuracy(tmp_path):
    from unittest.mock import patch
    from scripts.audit_jev_calibration import EvaluationInterruptedError

    out_md = tmp_path / "interrupted_prov.md"
    out_json = tmp_path / "interrupted_prov.json"
    checkpoint_file = tmp_path / "interrupted_prov_cp.json"

    # Simulate an interruption with partial case reports
    partial_case = {
        "id": "c1",
        "text": "test",
        "gold_tier": "routine",
        "predicted_tier": "routine",
        "tier_confidence": 0.9,
        "tier_probabilities": {"routine": 0.9},
        "flags": {},
        "technicality_score": 1.0,
        "served_model": "typesafe/jev-1.13",
        "input_tokens": 100,
        "cost_usd": None,
        "estimated_cost_usd": 0.001,
    }
    with patch("scripts.audit_jev_calibration.evaluate_advice_classifier") as mock_eval:
        from scripts.audit_jev_calibration import EvaluationMetrics
        partial_metrics = EvaluationMetrics(
            total_cases=1,
            has_ground_truth=True,
            exact_tier_matches=1,
            exact_accuracy=1.0,
            within_one_tier_matches=1,
            within_one_accuracy=1.0,
            brier_score=0.01,
            flag_metrics={},
            total_cost_usd=0.0,
            total_estimated_cost_usd=0.001,
            total_input_tokens=100,
            confusion_matrix=None,
            tier_order=["routine"],
            served_models=["typesafe/jev-1.13"],
            unbilled_calls_count=0,
        )
        mock_eval.side_effect = EvaluationInterruptedError(
            "Ceiling reached",
            exit_code=6,
            metrics=partial_metrics,
            case_reports=[partial_case],
        )
        ret = main([
            "--golden", "data/classifier_benchmark_golden.json",
            "--checkpoint", str(checkpoint_file),
            "--out-markdown", str(out_md),
            "--out-json", str(out_json),
        ])
        assert ret == 6

    # Verify that in interrupted output, cases_evaluated is 1 (len(case_reports)), not 6
    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert doc["metadata"]["golden_benchmark"]["cases_evaluated"] == 1
    assert doc["metadata"]["golden_benchmark"]["cases_requested"] == 6


def test_empty_selected_judge_set_refused(tmp_path):
    from scripts.advice_eval import canonical_json, sha256_text

    rec = {
        "record_type": "advice",
        "stimulus_id": "stim_01",
        "arm": "patient",
        "sample_k": 1,
        "model_requested": "vendor/model-a",
        "response_text": "Response text A from model A",
        "response_sha256": "aaaa1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
        "prev_sha256": None,
    }
    rec["record_sha256"] = sha256_text(canonical_json(rec))

    resp_file = tmp_path / "responses.jsonl"
    resp_file.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    # Judgments file containing only non-matching judge
    j_other = {
        "response_sha256": rec["response_sha256"],
        "judge_model": "some-other-judge",
        "tier": "routine",
        "flags": {},
    }
    judg_file = tmp_path / "judgments.jsonl"
    judg_file.write_text(json.dumps(j_other) + "\n", encoding="utf-8")

    # Calling with default judge_model (claude-haiku-4-5) must refuse
    with pytest.raises(ValueError, match="refusing empty judge set"):
        load_advice_archive_with_judgments(resp_file, judgments_path=judg_file, max_samples=0, judge_model="claude-haiku-4-5")

    # In main(), it should return exit code 1
    ret = main([
        "--archive", str(resp_file),
        "--judgments", str(judg_file),
        "--judge-model", "claude-haiku-4-5",
        "--archive-samples", "1",
    ])
    assert ret == 1


def test_petri_transcript_mismatch_refused_on_resume(tmp_path):
    transcripts_file1 = tmp_path / "transcripts1.jsonl"
    conv1 = {
        "conversation_id": "conv-1",
        "turns": [
            {
                "role": "assistant",
                "content": "You should check with a doctor.",
            }
        ],
    }
    transcripts_file1.write_text(json.dumps(conv1) + "\n", encoding="utf-8")

    checkpoint_file = tmp_path / "checkpoint_petri.json"
    out_md = tmp_path / "petri.md"
    out_json = tmp_path / "petri.json"

    ret = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--petri-transcripts", str(transcripts_file1),
        "--petri-conversations", "1",
        "--checkpoint", str(checkpoint_file),
        "--out-markdown", str(out_md),
        "--out-json", str(out_json),
    ])
    assert ret == 0

    cp_doc = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert "petri_transcripts_sha256" in cp_doc["metadata"]
    assert len(cp_doc["petri_cases"]) > 0

    # Resume with modified transcripts content must refuse
    transcripts_file2 = tmp_path / "transcripts2.jsonl"
    conv2 = {
        "conversation_id": "conv-1",
        "turns": [
            {
                "role": "assistant",
                "content": "Different response content entirely.",
            }
        ],
    }
    transcripts_file2.write_text(json.dumps(conv2) + "\n", encoding="utf-8")

    ret_mismatch = main([
        "--golden", "data/classifier_benchmark_golden.json",
        "--petri-transcripts", str(transcripts_file2),
        "--petri-conversations", "1",
        "--checkpoint", str(checkpoint_file),
        "--out-markdown", str(tmp_path / "petri2.md"),
        "--out-json", str(tmp_path / "petri2.json"),
    ])
    assert ret_mismatch == 1


