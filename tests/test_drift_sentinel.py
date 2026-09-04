"""Drift sentinel: day-over-day comparison of the hosted tracer's probabilities."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "drift_sentinel.py"


def write_day(root: Path, day: str, probs: dict, tops: dict | None = None):
    run_dir = root / f"drift_sentinel_{day}"
    run_dir.mkdir(parents=True)
    results = []
    for index, panels in probs.items():
        row = {"index": index, "probabilities": panels}
        if tops and index in tops:
            row["predictive_spread"] = {
                panel: [[token, panels.get(panel)]]
                for panel, token in tops[index].items()}
        results.append(row)
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


def test_top_words_tracked_alongside_probabilities(tmp_path):
    # 2026-07-15: the first real drift day moved probabilities but held every
    # top word; the series must record both so the site claim stays checkable.
    root = tmp_path / "trace_out"
    write_day(root, "20260714", {1: {"clinical": 0.50, "patient": 0.20}},
              tops={1: {"clinical": 'Output " a"', "patient": 'Output " b"'}})
    write_day(root, "20260715", {1: {"clinical": 0.47, "patient": 0.20}},
              tops={1: {"clinical": 'Output " a"', "patient": 'Output " c"'}})
    verdict, payload = run(tmp_path)
    delta = payload["deltas"][0]
    assert delta["top_words_tracked"] == 2
    assert delta["top_word_changes"] == ["pair 1 patient"]
    assert "top words CHANGED: pair 1 patient" in verdict
    # unchanged tops say so in the verdict
    root2 = tmp_path / "t2" / "trace_out"
    write_day(root2, "20260714", {1: {"clinical": 0.50, "patient": 0.20}},
              tops={1: {"clinical": 'Output " a"', "patient": 'Output " b"'}})
    write_day(root2, "20260715", {1: {"clinical": 0.47, "patient": 0.20}},
              tops={1: {"clinical": 'Output " a"', "patient": 'Output " b"'}})
    verdict2, payload2 = run(tmp_path / "t2")
    assert payload2["deltas"][0]["top_word_changes"] == []
    assert "top words unchanged" in verdict2


def test_missing_pair_on_one_day_is_skipped(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260712", {1: {"clinical": 0.5, "patient": 0.2},
                                 2: {"clinical": 0.4, "patient": 0.1}})
    write_day(root, "20260713", {1: {"clinical": 0.5, "patient": 0.2}})
    verdict, payload = run(tmp_path)
    assert payload["stable"] is True
    assert payload["deltas"][0]["max_abs_delta"] == 0.0


def test_every_breach_prints_not_only_the_largest(tmp_path):
    # DRIFT-SECOND-BREACH-20260814 (owner-approved 2026-08-21): a smaller,
    # earlier breach used to be computed and stored but never printed.
    root = tmp_path / "trace_out"
    write_day(root, "20260712", {1: {"clinical": 0.50, "patient": 0.20}})
    write_day(root, "20260713", {1: {"clinical": 0.48, "patient": 0.20}})  # 0.02 breach
    write_day(root, "20260714", {1: {"clinical": 0.53, "patient": 0.20}})  # 0.05 breach (larger)
    out = tmp_path / "drift_series.json"
    cmd = [sys.executable, str(SCRIPT), "--trace-root", str(root), "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    drift_lines = [line for line in proc.stdout.splitlines()
                   if line.startswith("drift sentinel: DRIFT max")]
    assert len(drift_lines) == 2, proc.stdout
    assert "20260713" in drift_lines[0] and "20260714" in drift_lines[1]  # chronological
    assert "DRIFT on 2 days total" in proc.stdout
