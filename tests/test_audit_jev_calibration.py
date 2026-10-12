"""Tests for classifier audit and calibration script (scripts/audit_jev_calibration.py)."""

from __future__ import annotations

import json

import pytest

from scripts.audit_jev_calibration import (
    compute_brier_score,
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
