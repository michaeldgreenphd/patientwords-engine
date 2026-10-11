"""Tests for scripts/dialect_invariant_core.py offline."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dialect_invariant_core", ROOT / "scripts" / "dialect_invariant_core.py"
)
dic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dic)


def _setup_dialect_case(tmp_path: Path, model: str, source_set: str | None) -> tuple[Path, Path]:
    trace_dir = tmp_path / "trace_out" / "dialects_TEST"
    trace_dir.mkdir(parents=True)
    summary = {
        "graph_model": model,
        "source_set": source_set,
        "results": [{"index": 1}],
    }
    (trace_dir / "batch_summary.part_01.json").write_text(json.dumps(summary), encoding="utf-8")

    # Write a minimal self-contained render with var DATA=
    baseline_node = {"id": "1_10_0 · cross layer transcoder", "cat": "clinical", "w": "(norm 1.5)", "desc": "cardiac"}
    variant_node = {"id": "1_10_0 · cross layer transcoder", "cat": "clinical", "w": "(norm 1.2)", "desc": "cardiac"}
    data_payload = json.dumps([[baseline_node], [variant_node]])
    render_html = f"<html><body><script>var DATA={data_payload};</script></body></html>"
    (trace_dir / "index_01.html").write_text(render_html, encoding="utf-8")

    dialects_json = tmp_path / "dialects.json"
    dialects_data = {
        "updated": "2026-10-11",
        "batch": "dialects_TEST",
        "graph_model": model,
        "source_set": source_set,
        "items": [{"index": 1, "term": "heart problem"}],
    }
    dialects_json.write_text(json.dumps(dialects_data, indent=1), encoding="utf-8")
    return trace_dir, dialects_json


def test_refuses_uncalibrated_qwen_dialects(tmp_path: Path):
    # Regression (Codex review of PR #93, thread 4236354647): uncalibrated qwen3-4b
    # labels must be refused by dialect_invariant_core before augmenting dialects.json.
    trace_dir, dialects_json = _setup_dialect_case(tmp_path, "qwen3-4b", "transcoder-hp")
    with pytest.raises(SystemExit, match="refusing: dialect-invariant clinical core cannot be published"):
        dic.main([str(trace_dir), "--dialects-json", str(dialects_json)])

    # Ensure dialects.json was not modified
    content = json.loads(dialects_json.read_text(encoding="utf-8"))
    assert "core" not in content["items"][0]


def test_refuses_uncalibrated_null_source_set(tmp_path: Path):
    trace_dir, dialects_json = _setup_dialect_case(tmp_path, "gemma-2-2b", None)
    with pytest.raises(SystemExit, match="refusing: dialect-invariant clinical core cannot be published"):
        dic.main([str(trace_dir), "--dialects-json", str(dialects_json)])

    content = json.loads(dialects_json.read_text(encoding="utf-8"))
    assert "core" not in content["items"][0]


def test_accepts_calibrated_gemma_dialects_and_augments(tmp_path: Path):
    trace_dir, dialects_json = _setup_dialect_case(tmp_path, "gemma-2-2b", "gemmascope-transcoder-16k")
    rc = dic.main([str(trace_dir), "--dialects-json", str(dialects_json)])
    assert rc == 0

    content = json.loads(dialects_json.read_text(encoding="utf-8"))
    item = content["items"][0]
    assert "core" in item
    assert item["core"]["invariant"] == 1
    assert item["core"]["baseline_clinical"] == 1

