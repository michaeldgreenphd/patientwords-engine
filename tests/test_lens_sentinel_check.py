"""Lens sentinel: day-over-day and cross-host comparison of hosted j-lens readouts.

Regression coverage for the blind spot found 2026-08-21: every daily cycle
compared each served host id only against the previous measured day, so a
host-side step (2026-07-31) and the resulting divergence between the two ids
went unreported for three weeks even though the data was committed all along.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lens_sentinel_check.py"


def write_day(root: Path, day: str, model: str, tops: list[str], ranks: list[int | None]):
    run_dir = root / f"drift_sentinel_{day}__jlens_{model}"
    run_dir.mkdir(parents=True)
    layers = [{"layer": i, "top1": token, "target_rank": rank, "match": None}
              for i, (token, rank) in enumerate(zip(tops, ranks))]
    results = [{"index": 1, "target_token": " placeholder",
                "depth": {"clinical": layers, "patient": layers}}]
    (run_dir / "jlens_summary.part_01.json").write_text(
        json.dumps({"results": results}), encoding="utf-8")


def run(tmp_path: Path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--trace-root", str(tmp_path / "trace_out"),
         "--out", str(tmp_path / "lens_series.json")],
        capture_output=True, text=True)
    payload = json.loads((tmp_path / "lens_series.json").read_text()) \
        if (tmp_path / "lens_series.json").exists() else None
    return proc.returncode, proc.stdout.strip(), payload


def test_no_readouts_exits_2(tmp_path):
    (tmp_path / "trace_out").mkdir()
    code, out, _ = run(tmp_path)
    assert code == 2
    assert "no dated lens readouts" in out


def test_stable_readouts_report_no_step(tmp_path):
    root = tmp_path / "trace_out"
    for day in ("20260714", "20260715"):
        write_day(root, day, "gemma-2-2b", ["a", "b"], [None, 1])
    code, out, payload = run(tmp_path)
    assert code == 0
    assert "no new step" in out
    assert payload["per_model"]["gemma-2-2b"]["steps"] == []
    assert payload["per_model"]["gemma-2-2b"]["matches_baseline"] is True


def test_step_on_latest_day_is_drift(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260714", "gemma-2-2b", ["a", "b"], [None, 1])
    write_day(root, "20260715", "gemma-2-2b", ["a", "zzz"], [None, None])
    code, out, payload = run(tmp_path)
    assert code == 1
    assert "DRIFT on 20260715" in out
    step = payload["per_model"]["gemma-2-2b"]["steps"][0]
    assert step["target_rank_hits_prev"] == 2 and step["target_rank_hits"] == 0


def test_historical_step_survives_a_quiet_latest_day(tmp_path):
    """The exact 2026-08-21 blind spot: a step three weeks back must stay visible
    even though the newest day equals the day before it."""
    root = tmp_path / "trace_out"
    write_day(root, "20260714", "gemma-2-2b", ["a", "b"], [None, 1])
    write_day(root, "20260731", "gemma-2-2b", ["a", "zzz"], [None, None])
    write_day(root, "20260821", "gemma-2-2b", ["a", "zzz"], [None, None])
    code, out, payload = run(tmp_path)
    assert code == 0
    assert "1 historical step(s): gemma-2-2b@20260731" in out
    assert payload["per_model"]["gemma-2-2b"]["matches_baseline"] is False


def test_cross_host_divergence_is_reported(tmp_path):
    root = tmp_path / "trace_out"
    write_day(root, "20260714", "gemma-2-2b", ["a", "b"], [None, 1])
    write_day(root, "20260714", "gemma-2-2b-it", ["a", "b"], [None, 1])
    write_day(root, "20260731", "gemma-2-2b", ["a", "zzz"], [None, None])
    write_day(root, "20260731", "gemma-2-2b-it", ["a", "b"], [None, 1])
    # a later quiet day, so the divergence is reported on the no-new-step path
    # rather than being masked by that day's own DRIFT line
    write_day(root, "20260821", "gemma-2-2b", ["a", "zzz"], [None, None])
    write_day(root, "20260821", "gemma-2-2b-it", ["a", "b"], [None, 1])
    code, out, payload = run(tmp_path)
    assert code == 0
    assert "DIVERGE since 20260731" in out
    assert payload["cross_host_identical"] == {
        "20260714": True, "20260731": False, "20260821": False}
