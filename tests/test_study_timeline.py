"""Timeline dataset (scripts/study_timeline.py) — offline, receipts-only.

Pins sidecar harvesting (alias sidecars skipped, malformed skipped), the
Tier B flagging against dashboard start_utc, and the totals block. No network.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "study_timeline", _ROOT / "scripts" / "study_timeline.py")
tl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tl)


def sidecar(tmp_path, stem, **fields):
    d = tmp_path / "data" / "simulated"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.report.json").write_text(json.dumps(fields), encoding="utf-8")


def test_batch_entries_skips_alias_and_malformed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sidecar(tmp_path, "pairs_20260710T010000Z", run_timestamp="2026-07-10T01:00:00Z",
            model="claude-haiku-4-5", accepted=100, cost_usd=0.18)
    sidecar(tmp_path, "drift_sentinel_20260712", cost_usd=0.0)     # $0 alias: no event
    (tmp_path / "data" / "simulated" / "broken.report.json").write_text("{not json")
    entries = tl.batch_entries()
    assert [e["batch"] for e in entries] == ["pairs_20260710T010000Z"]
    assert entries[0]["kind"] == "pairs" and entries[0]["cost_usd"] == 0.18


def test_main_tierb_flag_and_totals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sidecar(tmp_path, "pairs_20260709T000000Z", run_timestamp="2026-07-09T00:00:00Z",
            model="m", accepted=50, cost_usd=0.10)                  # pre-start: not Tier B
    sidecar(tmp_path, "pairs_20260711T000000Z", run_timestamp="2026-07-11T00:00:00Z",
            model="m", accepted=100, cost_usd=0.20)                 # post-start: Tier B
    sidecar(tmp_path, "quadrants_20260712T000000Z", run_timestamp="2026-07-12T00:00:00Z",
            model="m", accepted=8, cost_usd=0.05)                   # non-pairs: never Tier B
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "dashboard.json").write_text(
        json.dumps({"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}), encoding="utf-8")

    rc = tl.main(["--out", "out.json", "--site", ""])
    assert rc == 0
    payload = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    flags = {b["batch"]: b["tierb"] for b in payload["batches"]}
    assert flags == {"pairs_20260709T000000Z": False,
                     "pairs_20260711T000000Z": True,
                     "quadrants_20260712T000000Z": False}
    t = payload["totals"]
    assert t["generation_batches"] == 3
    assert t["accepted_pairs"] == 158
    assert t["tierb_accepted"] == 100
    assert t["generation_usd"] == 0.35
    # no git repo in tmp -> milestone lookup degrades; Tier B start still present
    assert any(m["label"] == "Tier B collection started" for m in payload["milestones"])
