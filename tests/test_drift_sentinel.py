"""Drift sentinel: day-over-day comparison of the hosted tracer's probabilities."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "drift_sentinel.py"


def write_day(root: Path, day: str, probs: dict):
    run_dir = root / f"drift_sentinel_{day}"
    run_dir.mkdir(parents=True)
    results = [{"index": index, "probabilities": panels}
               for index, panels in probs.items()]
    (run_dir / "batch_summary.part_01.json").write_text(
        json.dumps({"results": results}), encoding="utf-8")


def run(tmp_path: Path, threshold=None):
    out = tmp_path / "drift_series.json"
    cmd = [sys.executable, str(SCRIPT), "--trace-root", str(tmp_path / "trace_out"),
           "--out", str(out)]
    if threshold is not None:
        cmd += ["--threshold", str(threshold)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout.strip().splitlines()[-1], json.loads(out.read_text())


def test_stable_days(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260712", {1: {"clinical": 0.50, "patient": 0.20}})
    write_day(root, "20260713", {1: {"clinical": 0.502, "patient": 0.199}})
    verdict, payload = run(tmp_path)
    assert payload["stable"] is True
    assert verdict.startswith("drift sentinel: stable")
    assert payload["deltas"][0]["max_abs_delta"] == 0.002


def test_drift_breaches_threshold(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260712", {1: {"clinical": 0.50, "patient": 0.20}})
    write_day(root, "20260713", {1: {"clinical": 0.40, "patient": 0.20}})
    verdict, payload = run(tmp_path)
    assert payload["stable"] is False
    assert "DRIFT" in verdict
    assert payload["deltas"][0]["worst"] == "pair 1 clinical"


def test_baseline_only(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260712", {1: {"clinical": 0.5, "patient": 0.2}})
    verdict, payload = run(tmp_path)
    assert payload["stable"] is True
    assert "baseline only" in verdict


def test_missing_pair_on_one_day_is_skipped(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260712", {1: {"clinical": 0.5, "patient": 0.2},
                                 2: {"clinical": 0.4, "patient": 0.1}})
    write_day(root, "20260713", {1: {"clinical": 0.5, "patient": 0.2}})
    verdict, payload = run(tmp_path)
    assert payload["stable"] is True
    assert payload["deltas"][0]["max_abs_delta"] == 0.0
