"""Tests for scripts/fire_trigger.py - the push-to-run trigger guard.

scripts/ is not a package, so the module loads via importlib from its file
path. Every CLI-level test passes --no-git against a throwaway repo layout
under tmp_path; nothing here touches git or the network.
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fire_trigger.py"
_SPEC = importlib.util.spec_from_file_location("fire_trigger", _MODULE_PATH)
ft = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ft)


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def journal_path(repo):
    return repo / "ops" / "trigger_journal.jsonl"


def trigger_path(repo, name="circuit-trace"):
    return repo / ".github" / "trigger" / f"{name}.json"


def fire(repo, trigger="circuit-trace", params=None, extra=(), note="test fire"):
    if params is None:
        params = {"graph_model": "gemma-2-2b", "mode": "2panel"}
    argv = ["fire", "--repo", str(repo), "--trigger", trigger,
            "--params", json.dumps(params), "--note", note, "--no-git", *extra]
    return ft.main(argv)


def write_dashboard(repo, spent, date=None, ceiling=2.0):
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {"schema_version": 1,
               "spend": {"daily_ceiling_usd": ceiling, "today": {"date": date, "spent_usd": spent}}}
    (repo / "ops").mkdir(exist_ok=True)
    (repo / "ops" / "dashboard.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".github" / "trigger").mkdir(parents=True)
    (tmp_path / "ops").mkdir()
    return tmp_path


def test_third_fire_refused_with_exit_2(repo, capsys):
    assert fire(repo, params={"mode": "2panel", "_nonce": "1"}, note="first") == 0
    assert fire(repo, params={"mode": "2panel", "_nonce": "2"}, note="second") == 0
    assert fire(repo, params={"mode": "2panel", "_nonce": "3"}, note="third") == 2
    assert "one running + one pending" in capsys.readouterr().err
    entries = ft.load_journal(journal_path(repo))
    assert len(entries) == 2  # the refused fire was never journaled
    assert json.loads(trigger_path(repo).read_text())["_nonce"] == "2"  # nor written
    dash = json.loads((repo / "ops" / "dashboard.json").read_text())
    assert dash["updated_by"] == "session"
    group = dash["queue"]["circuit-trace"]
    assert group["running"]["note"] == "first"
    assert group["pending"]["note"] == "second"


def test_force_evict_marks_newest_active_and_proceeds(repo):
    assert fire(repo, params={"mode": "2panel", "_nonce": "1"}) == 0
    assert fire(repo, params={"mode": "2panel", "_nonce": "2"}) == 0
    assert fire(repo, params={"mode": "2panel", "_nonce": "3"}, extra=["--force-evict"]) == 0
    entries = ft.load_journal(journal_path(repo))
    assert [e["evicted"] for e in entries] == [False, True, False]
    active = ft.active_entries(entries, "circuit-trace", datetime.now(timezone.utc), 8)
    assert len(active) == 2
    assert json.loads(trigger_path(repo).read_text())["_nonce"] == "3"


def test_expired_entry_frees_a_queue_slot(repo):
    now = datetime.now(timezone.utc)
    stale = {"trigger": "circuit-trace", "fired_utc": iso(now - timedelta(hours=9)),
             "commit": "", "note": "stale", "resolved": False, "evicted": False}
    fresh = {"trigger": "circuit-trace", "fired_utc": iso(now - timedelta(minutes=5)),
             "commit": "", "note": "fresh", "resolved": False, "evicted": False}
    ft.save_journal(journal_path(repo), [stale, fresh])
    assert fire(repo, params={"mode": "2panel", "_nonce": "x"}) == 0
    entries = ft.load_journal(journal_path(repo))
    assert len(entries) == 3
    assert len(ft.active_entries(entries, "circuit-trace", now, 8)) == 2


def test_expire_hours_env_override(repo, monkeypatch):
    now = datetime.now(timezone.utc)
    two_hours_old = [
        {"trigger": "circuit-trace", "fired_utc": iso(now - timedelta(hours=2)),
         "commit": "", "note": f"n{i}", "resolved": False, "evicted": False}
        for i in range(2)
    ]
    ft.save_journal(journal_path(repo), two_hours_old)
    monkeypatch.delenv("MEDLANG_TRIGGER_EXPIRE_HOURS", raising=False)
    assert fire(repo, params={"mode": "2panel", "_nonce": "a"}) == 2  # default 8h: both active
    monkeypatch.setenv("MEDLANG_TRIGGER_EXPIRE_HOURS", "1")
    assert fire(repo, params={"mode": "2panel", "_nonce": "b"}) == 0  # 1h: both expired


def test_resolve_clears_oldest_then_all(repo):
    assert fire(repo, params={"mode": "2panel", "_nonce": "1"}, note="oldest") == 0
    assert fire(repo, params={"mode": "2panel", "_nonce": "2"}, note="newer") == 0
    assert ft.main(["resolve", "--repo", str(repo), "--trigger", "circuit-trace"]) == 0
    entries = ft.load_journal(journal_path(repo))
    assert [e["resolved"] for e in entries] == [True, False]
    assert fire(repo, params={"mode": "2panel", "_nonce": "3"}) == 0  # slot freed
    assert ft.main(["resolve", "--repo", str(repo), "--trigger", "circuit-trace", "--all"]) == 0
    assert all(e["resolved"] for e in ft.load_journal(journal_path(repo)))


def test_unknown_circuit_trace_key_is_hard_error(repo):
    assert fire(repo, params={"graph_model": "gemma-2-2b", "sampel_size": "10"}) == 3
    assert not journal_path(repo).exists()
    assert not trigger_path(repo).exists()


def test_params_must_be_a_dict(repo):
    assert fire(repo, params=["not", "a", "dict"]) == 3
    argv = ["fire", "--repo", str(repo), "--trigger", "circuit-trace",
            "--params", "{not json", "--no-git"]
    assert ft.main(argv) == 3


def test_underscore_keys_always_allowed_and_unverified_lists_only_warn(repo, capsys):
    assert fire(repo, params={"mode": "2panel", "_note": "x", "_nonce": "y"}) == 0
    rc = fire(repo, "logits-eval", params={"models": ["m"], "limt": 0})
    assert rc == 0
    assert "best-known" in capsys.readouterr().err


def test_budget_refusal_and_pass(repo):
    write_dashboard(repo, spent=1.5)
    params = {"task": "pairs", "num": "5", "max_spend": "1.0", "_nonce": "b1"}
    assert fire(repo, "scenario-generation", params) == 4  # 1.0 + 1.5 > 2.0
    assert not trigger_path(repo, "scenario-generation").exists()
    params = {"task": "pairs", "num": "5", "max_spend": "0.5", "_nonce": "b2"}
    assert fire(repo, "scenario-generation", params) == 0  # 0.5 + 1.5 == 2.0, not over


def test_budget_missing_max_spend_is_exit_4_even_with_override(repo):
    params = {"task": "pairs", "num": "5"}
    assert fire(repo, "scenario-generation", params) == 4
    assert fire(repo, "scenario-generation", params, extra=["--override-budget"]) == 4


def test_budget_override_and_stale_date(repo):
    write_dashboard(repo, spent=1.5)
    params = {"task": "pairs", "max_spend": "1.0", "_nonce": "o1"}
    assert fire(repo, "scenario-generation", params, extra=["--override-budget"]) == 0
    write_dashboard(repo, spent=1.9, date="2026-01-01")  # not today: counts as 0
    params = {"task": "pairs", "max_spend": "1.0", "_nonce": "o2"}
    assert fire(repo, "scenario-generation", params) == 0


def test_budget_defaults_when_dashboard_missing(repo):
    assert fire(repo, "model-evaluation", params={"sample_size": "10", "max_spend": "3"}) == 4
    assert fire(repo, "model-evaluation", params={"sample_size": "10", "max_spend": "1"}) == 0


def test_dry_run_writes_nothing(repo, capsys):
    assert fire(repo, params={"mode": "2panel", "_nonce": "d"}, extra=["--dry-run"]) == 0
    assert "[dry-run]" in capsys.readouterr().out
    assert not journal_path(repo).exists()
    assert not trigger_path(repo).exists()
    assert not (repo / "ops" / "dashboard.json").exists()


def test_journal_round_trip_tolerates_blanks_and_unknown_fields(tmp_path):
    path = tmp_path / "trigger_journal.jsonl"
    first = {"trigger": "circuit-trace", "fired_utc": "2026-07-09T00:00:00Z", "commit": "",
             "note": "a", "resolved": False, "evicted": False, "operator": "night-shift"}
    second = {"trigger": "logits-eval", "fired_utc": "2026-07-09T01:00:00Z", "commit": "abc123",
              "note": "b", "resolved": True, "evicted": False}
    path.write_text("\n" + json.dumps(first) + "\n\n   \n" + json.dumps(second) + "\n\n", encoding="utf-8")
    entries = ft.load_journal(path)
    assert len(entries) == 2
    assert entries[0]["operator"] == "night-shift"  # unknown field preserved
    ft.save_journal(path, entries)
    assert ft.load_journal(path) == entries


def test_budget_check_pure_function():
    assert ft.budget_check({"max_spend": "1.0"}, {}, "2026-07-09")[0] is True  # default ceiling 2.0
    assert ft.budget_check({"max_spend": "2.5"}, {}, "2026-07-09")[0] is False
    dash = {"spend": {"daily_ceiling_usd": 5.0, "today": {"date": "2026-07-09", "spent_usd": 4.5}}}
    assert ft.budget_check({"max_spend": "1.0"}, dash, "2026-07-09")[0] is False
    assert ft.budget_check({"max_spend": "1.0"}, dash, "2026-07-10")[0] is True  # stale date -> 0
    ok, reason = ft.budget_check({}, dash, "2026-07-09")
    assert ok is False and "max_spend" in reason
    assert ft.budget_check({"max_spend": "lots"}, dash, "2026-07-09")[0] is False


def test_validate_params_pure_function():
    assert ft.validate_params("circuit-trace", {"graph_model": "g", "_note": "n"}) == []
    with pytest.raises(ValueError):
        ft.validate_params("circuit-trace", {"graph_modle": "g"})
    with pytest.raises(ValueError):
        ft.validate_params("scenario-generation", {"tsak": "pairs"})
    with pytest.raises(ValueError):
        ft.validate_params("circuit-trace", "not a dict")
    warnings = ft.validate_params("archive-renders", {"tag": "t", "surprise": 1})
    assert len(warnings) == 1 and "surprise" in warnings[0]


def test_queue_view_shape():
    now = datetime.now(timezone.utc)
    entries = [
        {"trigger": "circuit-trace", "fired_utc": iso(now - timedelta(hours=1)),
         "commit": "", "note": "older", "resolved": False, "evicted": False},
        {"trigger": "circuit-trace", "fired_utc": iso(now - timedelta(minutes=5)),
         "commit": "", "note": "newer", "resolved": False, "evicted": False},
    ]
    view = ft.queue_view(entries, now, 8)
    assert set(view) == set(ft.TRIGGERS)
    assert view["circuit-trace"]["running"]["note"] == "older"
    assert view["circuit-trace"]["pending"]["note"] == "newer"
    assert view["logits-eval"] == {"running": None, "pending": None}


def test_status_reports_counts(repo, capsys):
    assert fire(repo, params={"mode": "2panel", "_nonce": "s"}, note="visible") == 0
    capsys.readouterr()
    assert ft.main(["status", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "circuit-trace: 1 active" in out
    assert "logits-eval: 0 active" in out
    assert "visible" in out
