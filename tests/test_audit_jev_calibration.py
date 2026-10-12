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
    conv_ids = {p["conversation_id"] for p in doc["petri_cases"]}
    assert len(conv_ids) == 30

