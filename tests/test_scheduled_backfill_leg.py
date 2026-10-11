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


def test_has_active_entries_with_expiry(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ops").mkdir()
    (repo / "scripts").mkdir()
    # Copy fire_trigger stub
    (repo / "scripts" / "fire_trigger.py").write_text(
        (ROOT / "scripts" / "fire_trigger.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    j_path = repo / "ops" / "trigger_journal.jsonl"

    # Empty journal
    j_path.write_text("", encoding="utf-8")
    assert not sbl.has_active_entries(repo, "logits-eval")

    # Add old unresolved entry (older than 8h -> expired)
    old_entry = {
        "trigger": "logits-eval",
        "fired_utc": "2020-01-01T00:00:00Z",
        "resolved": False,
        "evicted": False,
        "nonce": "old",
    }
    j_path.write_text(json.dumps(old_entry) + "\n", encoding="utf-8")
    assert not sbl.has_active_entries(repo, "logits-eval")

    # Add fresh unresolved entry (recent -> active)
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh_entry = {
        "trigger": "logits-eval",
        "fired_utc": now_str,
        "resolved": False,
        "evicted": False,
        "nonce": "fresh",
    }
    j_path.write_text(json.dumps(fresh_entry) + "\n", encoding="utf-8")
    assert sbl.has_active_entries(repo, "logits-eval")


def test_reserve_and_resolve(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ops").mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts" / "fire_trigger.py").write_text(
        (ROOT / "scripts" / "fire_trigger.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    j_path = repo / "ops" / "trigger_journal.jsonl"
    j_path.write_text("", encoding="utf-8")

    # Reserve
    sbl.reserve_leg(repo, "test note", "nonce-123", {"models": "m1"})
    assert sbl.has_active_entries(repo, "logits-eval")

    # Resolve
    sbl.resolve_leg(repo, "nonce-123")
    assert not sbl.has_active_entries(repo, "logits-eval")

    entries = [json.loads(line) for line in j_path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    assert entries[0]["resolved"] is True
    assert "resolved_utc" in entries[0]


def test_cmd_plan_dry_run(monkeypatch, tmp_path: Path):
    out_file = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    rc = sbl.cmd_plan(ROOT, dry_run=True)
    assert rc == 0
    content = out_file.read_text(encoding="utf-8")
    assert "should_run=true" in content
    assert "models=" in content
    assert "pairs_file=" in content
