"""Tests for scripts/scheduled_backfill_leg.py offline."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "scheduled_backfill_leg", ROOT / "scripts" / "scheduled_backfill_leg.py"
)
sbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sbl)


def test_has_active_entries(tmp_path: Path):
    j_path = tmp_path / "trigger_journal.jsonl"
    assert not sbl.has_active_entries(j_path, "logits-eval")

    # Add resolved entry
    sbl.append_journal(j_path, {"trigger": "logits-eval", "resolved": True})
    assert not sbl.has_active_entries(j_path, "logits-eval")

    # Add unresolved entry
    sbl.append_journal(j_path, {"trigger": "logits-eval", "resolved": False, "evicted": False})
    assert sbl.has_active_entries(j_path, "logits-eval")


def test_run_leg_dry_run(tmp_path: Path):
    rc = sbl.run_leg(ROOT, dry_run=True)
    assert rc == 0


def test_run_leg_skips_when_busy(tmp_path: Path):
    # Setup temporary repo with active journal
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "ops").mkdir()
    (repo / "ops" / "trigger_journal.jsonl").write_text(
        json.dumps({"trigger": "logits-eval", "resolved": False, "evicted": False}) + "\n",
        encoding="utf-8",
    )
    # Copy backfill planner stub
    shutil_copy = (ROOT / "scripts" / "backfill_planner.py").read_text(encoding="utf-8")
    (repo / "scripts" / "backfill_planner.py").write_text(shutil_copy, encoding="utf-8")

    called = []
    rc = sbl.run_leg(repo, run_cmd=lambda cmd, **kw: called.append(cmd))
    assert rc == 0
    assert called == []  # Skipped because busy
