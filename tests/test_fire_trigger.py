"""Tests for scripts/fire_trigger.py - the push-to-run trigger guard.

scripts/ is not a package, so the module loads via importlib from its file
path. Every CLI-level test passes --no-git against a throwaway repo layout
under tmp_path; nothing here touches git or the network.
"""

import importlib.util
import json
import os
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
    # slot freed; --ignore-settle acks the just-resolved run's still-open settle window
    assert fire(repo, params={"mode": "2panel", "_nonce": "3"}, extra=["--ignore-settle"]) == 0
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


def test_underscore_keys_always_allowed(repo):
    assert fire(repo, params={"mode": "2panel", "_note": "x", "_nonce": "y"}) == 0


def test_unknown_keys_hard_error_for_every_trigger(repo):
    # Finding 6: the warn-only tier is gone - every trigger's key set is
    # verified against its workflow heredoc and unknown keys exit 3.
    bad = {
        "circuit-trace": {"graph_modle": "g"},
        "logits-eval": {"models": ["m"], "limt": 0},
        "activation-patching": {"pairs_file": "p.json", "offset": 0},
        "scenario-generation": {"max_spend": "1", "tsak": "pairs"},
        "model-evaluation": {"max_spend": "1", "sampel_size": "8"},
        "archive-renders": {"tag": "t", "runz": "x"},
    }
    for trigger, params in bad.items():
        assert fire(repo, trigger, params) == 3, trigger
    assert not journal_path(repo).exists()


def test_exact_verified_key_sets_accepted(repo):
    # Finding 6: the full key set each workflow's params heredoc reads must pass.
    assert fire(repo, "logits-eval", params={
        "models": "qwen3-4b", "pairs_file": "p.json", "limit": "1",
        "offset": "60", "commit_outputs": True, "_nonce": "k1"}) == 0
    assert fire(repo, "archive-renders", params={
        "tag": "t", "runs": "trace_out/x", "no_pngs": False, "prune": False, "_nonce": "k2"}) == 0
    assert fire(repo, "model-evaluation", params={
        "model_selection": "claude-haiku-4-5", "scenario": "all",
        "sample_size": "8", "max_spend": "1", "_nonce": "k3"}) == 0
    assert fire(repo, "activation-patching", params={
        "pairs_file": "p.json", "limit": "5", "layers": "", "positions": "",
        "model": "gemma-2-2b", "offsets": "0,5", "commit_outputs": True, "_nonce": "k4"}) == 0


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


def test_budget_check_pure_function_returns_structured_kind():
    # Finding 3: budget_check reports "ok" | "ceiling" | "invalid", not a bool.
    assert ft.budget_check({"max_spend": "1.0"}, {}, "2026-07-09")[0] == "ok"  # default ceiling 2.0
    assert ft.budget_check({"max_spend": "2.5"}, {}, "2026-07-09")[0] == "ceiling"
    dash = {"spend": {"daily_ceiling_usd": 5.0, "today": {"date": "2026-07-09", "spent_usd": 4.5}}}
    assert ft.budget_check({"max_spend": "1.0"}, dash, "2026-07-09")[0] == "ceiling"
    assert ft.budget_check({"max_spend": "1.0"}, dash, "2026-07-10")[0] == "ok"  # stale date -> 0
    kind, reason = ft.budget_check({}, dash, "2026-07-09")
    assert kind == "invalid" and "max_spend" in reason
    assert ft.budget_check({"max_spend": "lots"}, dash, "2026-07-09")[0] == "invalid"
    assert ft.budget_check({"max_spend": float("nan")}, dash, "2026-07-09")[0] == "invalid"


def test_validate_params_pure_function():
    assert ft.validate_params("circuit-trace", {"graph_model": "g", "_note": "n"}) is None
    with pytest.raises(ValueError):
        ft.validate_params("circuit-trace", "not a dict")
    for trigger, params in [("circuit-trace", {"graph_modle": "g"}),
                            ("scenario-generation", {"tsak": "pairs"}),
                            ("logits-eval", {"limt": 0}),
                            ("activation-patching", {"pair_file": "p.json"}),
                            ("model-evaluation", {"sampel_size": 1}),
                            ("archive-renders", {"tag": "t", "surprise": 1})]:
        with pytest.raises(ValueError):
            ft.validate_params(trigger, params)


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


# --- Finding 1: the daily ceiling counts landed + in-flight max_spend ---

def test_inflight_max_spend_blocks_second_paid_fire(repo, capsys):
    # Two consecutive 1.9 fires both used to pass the $2 ceiling because only
    # dashboard-landed spend was counted.
    params = {"task": "pairs", "max_spend": "1.9", "_nonce": "i1"}
    assert fire(repo, "scenario-generation", params) == 0
    entries = ft.load_journal(journal_path(repo))
    assert entries[-1]["max_spend"] == pytest.approx(1.9)  # journaled at fire time
    capsys.readouterr()
    params = {"task": "pairs", "max_spend": "1.9", "_nonce": "i2"}
    assert fire(repo, "scenario-generation", params) == 4  # 1.9 already committed in flight
    assert "in-flight" in capsys.readouterr().err
    # resolving the landed run releases the in-flight hold (--ignore-settle acks its settle window)
    assert ft.main(["resolve", "--repo", str(repo), "--trigger", "scenario-generation"]) == 0
    assert fire(repo, "scenario-generation", params, extra=["--ignore-settle"]) == 0


def test_inflight_spend_counted_across_both_paid_triggers(repo):
    assert fire(repo, "model-evaluation",
                params={"sample_size": "8", "max_spend": "1.5", "_nonce": "m1"}) == 0
    assert fire(repo, "scenario-generation",
                params={"task": "pairs", "max_spend": "1.0", "_nonce": "s1"}) == 4


def test_budget_check_inflight_counts_only_active_entries_fired_today():
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    def entry(**overrides):
        base = {"trigger": "scenario-generation", "fired_utc": iso(now), "commit": "",
                "note": "", "resolved": False, "evicted": False, "max_spend": 1.9}
        base.update(overrides)
        return base

    kind, reason = ft.budget_check({"max_spend": "1.9"}, {}, today, entries=[entry()], now=now)
    assert kind == "ceiling" and "in-flight 1.90" in reason
    for released in (entry(resolved=True), entry(evicted=True), entry(trigger="circuit-trace")):
        assert ft.budget_check({"max_spend": "1.9"}, {}, today,
                               entries=[released], now=now)[0] == "ok"
    # active (expiry widened) but fired on a previous UTC date: not today's spend
    stale = entry(fired_utc=iso(now - timedelta(days=1)))
    assert ft.budget_check({"max_spend": "1.9"}, {}, today,
                           entries=[stale], now=now, expire_hours=100.0)[0] == "ok"


# --- Finding 2: max_spend must be a finite number > 0, never a bool ---

def test_parse_max_spend_pure():
    assert ft.parse_max_spend("1.5") == 1.5
    assert ft.parse_max_spend(2) == 2.0
    assert ft.parse_max_spend(0.25) == 0.25
    for bad in (True, False, float("nan"), float("inf"), "nan", "inf", "-inf",
                "-3", -1, 0, "0", None, [1], {"a": 1}, "lots"):
        assert ft.parse_max_spend(bad) is None, repr(bad)


def test_nonfinite_or_nonpositive_max_spend_is_hard_exit_4(repo):
    for i, bad in enumerate(("nan", "inf", "-inf", "-1", "0", True, False, None, [1])):
        params = {"task": "pairs", "max_spend": bad, "_nonce": f"bad{i}"}
        assert fire(repo, "scenario-generation", params) == 4, repr(bad)
        # never overridable: these are "invalid", not a ceiling refusal
        assert fire(repo, "scenario-generation", params, extra=["--override-budget"]) == 4, repr(bad)
    assert not trigger_path(repo, "scenario-generation").exists()
    assert not journal_path(repo).exists()


# --- Finding 3: --override-budget applies only to the "ceiling" kind ---

def test_override_budget_never_fires_unparseable_max_spend(repo):
    params = {"task": "pairs", "max_spend": "garbage", "_nonce": "g1"}
    assert fire(repo, "scenario-generation", params, extra=["--override-budget"]) == 4
    assert not trigger_path(repo, "scenario-generation").exists()
    assert not journal_path(repo).exists()
    # a genuine ceiling refusal stays overridable
    write_dashboard(repo, spent=1.9)
    params = {"task": "pairs", "max_spend": "1.0", "_nonce": "g2"}
    assert fire(repo, "scenario-generation", params) == 4
    assert fire(repo, "scenario-generation", params, extra=["--override-budget"]) == 0


# --- Finding 4: corrupt journal lines fail closed; saves are atomic ---

def test_corrupt_journal_line_is_a_hard_stop_with_line_and_content(repo):
    good = {"trigger": "circuit-trace", "fired_utc": "2026-07-09T00:00:00Z",
            "commit": "", "note": "ok", "resolved": True, "evicted": False}
    journal_path(repo).write_text(json.dumps(good) + "\n{not json\n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        fire(repo, params={"mode": "2panel", "_nonce": "c"})
    message = str(excinfo.value)
    assert "line 2" in message and "{not json" in message
    # the journal is left for the operator to repair, never rewritten
    assert "{not json" in journal_path(repo).read_text(encoding="utf-8")
    # parseable-but-not-an-entry lines fail closed too
    journal_path(repo).write_text('["not", "a", "dict"]\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        ft.load_journal(journal_path(repo))


def test_save_journal_atomic_write_via_replace(tmp_path, monkeypatch):
    calls = []
    real_replace = os.replace

    def spying_replace(src, dst):
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(ft.os, "replace", spying_replace)
    path = tmp_path / "ops" / "trigger_journal.jsonl"
    entry = {"trigger": "circuit-trace", "fired_utc": "2026-07-09T00:00:00Z",
             "commit": "", "note": "", "resolved": False, "evicted": False}
    ft.save_journal(path, [entry])
    assert calls and calls[-1][1] == str(path)  # tmp file + os.replace, not in-place truncate
    assert not list(path.parent.glob("*.tmp"))
    assert ft.load_journal(path) == [entry]


# --- Finding 5: identical trigger-file content is a hard exit 5 ---

def test_identical_params_hard_error_exit_5_no_phantom_slot(repo, capsys):
    params = {"mode": "2panel", "_nonce": "same"}
    assert fire(repo, params=params, note="first") == 0
    capsys.readouterr()
    assert fire(repo, params=params, note="rerun") == 5
    err = capsys.readouterr().err
    assert "_nonce" in err and "NOT fire" in err
    # no journal append: a fire CI never sees must not hold a queue slot
    assert len(ft.load_journal(journal_path(repo))) == 1
    dash = json.loads((repo / "ops" / "dashboard.json").read_text())
    assert dash["queue"]["circuit-trace"]["pending"] is None
    assert json.loads(trigger_path(repo).read_text())["_nonce"] == "same"


# --- Finding 7: MEDLANG_TRIGGER_EXPIRE_HOURS must be a finite float > 0 ---

def test_expire_hours_env_rejects_nonfinite_and_nonpositive(monkeypatch, capsys):
    for bad in ("nan", "inf", "-inf", "-3", "0", "wat"):
        monkeypatch.setenv("MEDLANG_TRIGGER_EXPIRE_HOURS", bad)
        assert ft.expire_hours_from_env() == ft.DEFAULT_EXPIRE_HOURS, bad
        assert "MEDLANG_TRIGGER_EXPIRE_HOURS" in capsys.readouterr().err
    monkeypatch.setenv("MEDLANG_TRIGGER_EXPIRE_HOURS", "2.5")
    assert ft.expire_hours_from_env() == 2.5
    monkeypatch.delenv("MEDLANG_TRIGGER_EXPIRE_HOURS", raising=False)
    assert ft.expire_hours_from_env() == ft.DEFAULT_EXPIRE_HOURS
    assert capsys.readouterr().err == ""  # valid or unset values warn nothing


# --- Finding 8: missing --params-file refuses cleanly ---

def test_missing_params_file_clean_refusal_exit_3(repo, capsys):
    argv = ["fire", "--repo", str(repo), "--trigger", "circuit-trace",
            "--params-file", str(repo / "nope.json"), "--no-git"]
    assert ft.main(argv) == 3
    err = capsys.readouterr().err
    assert "refused" in err and "params-file" in err
    assert not journal_path(repo).exists()


# --- Settle window: a same-trigger resolve may still hold the GitHub group (2026-07-09 seam) ---


def resolved_entry(now, trigger="circuit-trace", note="landed", resolved_ago=None, fired_ago=None):
    fired_ago = fired_ago if fired_ago is not None else timedelta(minutes=25)
    resolved_ago = resolved_ago if resolved_ago is not None else timedelta(minutes=5)
    return {"trigger": trigger, "fired_utc": iso(now - fired_ago), "commit": "", "note": note,
            "resolved": True, "evicted": False, "resolved_utc": iso(now - resolved_ago)}


def test_fire_refused_exit_6_when_same_trigger_resolved_inside_settle_window(repo, capsys):
    now = datetime.now(timezone.utc)
    ft.save_journal(journal_path(repo), [resolved_entry(now, resolved_ago=timedelta(minutes=5))])
    assert fire(repo, params={"mode": "2panel", "_nonce": "s1"}) == 6
    err = capsys.readouterr().err
    assert "settle" in err and "queue-eviction seam" in err
    # nothing written: no journal append, no trigger file
    assert len(ft.load_journal(journal_path(repo))) == 1
    assert not trigger_path(repo).exists()


def test_fire_allowed_once_settle_window_has_passed(repo):
    now = datetime.now(timezone.utc)
    # resolved 20 min ago: past the default 15-minute window
    ft.save_journal(journal_path(repo), [resolved_entry(now, resolved_ago=timedelta(minutes=20),
                                                         fired_ago=timedelta(minutes=40))])
    assert fire(repo, params={"mode": "2panel", "_nonce": "s2"}) == 0


def test_ignore_settle_bypasses_the_window(repo):
    now = datetime.now(timezone.utc)
    ft.save_journal(journal_path(repo), [resolved_entry(now, resolved_ago=timedelta(minutes=2))])
    assert fire(repo, params={"mode": "2panel", "_nonce": "s3"}) == 6
    assert fire(repo, params={"mode": "2panel", "_nonce": "s3"}, extra=["--ignore-settle"]) == 0


def test_other_triggers_recent_resolve_does_not_block(repo):
    now = datetime.now(timezone.utc)
    ft.save_journal(journal_path(repo),
                    [resolved_entry(now, trigger="logits-eval", resolved_ago=timedelta(minutes=3))])
    assert fire(repo, params={"mode": "2panel", "_nonce": "s4"}) == 0  # circuit-trace unaffected


def test_resolve_stamps_resolved_utc(repo):
    assert fire(repo, params={"mode": "2panel", "_nonce": "r1"}, note="run") == 0
    assert ft.main(["resolve", "--repo", str(repo), "--trigger", "circuit-trace"]) == 0
    entry = ft.load_journal(journal_path(repo))[0]
    assert entry["resolved"] is True
    stamp = ft.parse_utc(entry["resolved_utc"])
    assert stamp is not None
    assert abs((stamp - datetime.now(timezone.utc)).total_seconds()) < 60


def test_recently_resolved_pure_function_respects_window_and_trigger():
    now = datetime.now(timezone.utc)

    def entry(**overrides):
        base = {"trigger": "circuit-trace", "fired_utc": iso(now - timedelta(minutes=30)),
                "commit": "", "note": "", "resolved": True, "resolved_utc": iso(now - timedelta(minutes=5))}
        base.update(overrides)
        return base

    assert ft.recently_resolved([entry()], "circuit-trace", now, 15)  # inside window blocks
    # inject a later now so the same stamp falls outside the window
    assert not ft.recently_resolved([entry()], "circuit-trace", now + timedelta(minutes=20), 15)
    assert not ft.recently_resolved([entry(resolved=False)], "circuit-trace", now, 15)  # not resolved
    assert not ft.recently_resolved([entry(resolved_utc=None)], "circuit-trace", now, 15)  # no stamp
    assert not ft.recently_resolved([entry(trigger="logits-eval")], "circuit-trace", now, 15)  # other trigger


def test_settle_window_env_override_changes_refusal(repo, monkeypatch):
    now = datetime.now(timezone.utc)
    ft.save_journal(journal_path(repo), [resolved_entry(now, resolved_ago=timedelta(minutes=20),
                                                        fired_ago=timedelta(minutes=60))])
    monkeypatch.delenv("MEDLANG_TRIGGER_SETTLE_MINUTES", raising=False)
    assert fire(repo, params={"mode": "2panel", "_nonce": "e1"}) == 0  # 20 min > default 15
    monkeypatch.setenv("MEDLANG_TRIGGER_SETTLE_MINUTES", "30")  # widen past 20 min
    assert fire(repo, params={"mode": "2panel", "_nonce": "e2"}) == 6


def test_settle_minutes_env_rejects_nonfinite_and_nonpositive(monkeypatch, capsys):
    for bad in ("nan", "inf", "-inf", "-3", "0", "wat"):
        monkeypatch.setenv("MEDLANG_TRIGGER_SETTLE_MINUTES", bad)
        assert ft.settle_minutes_from_env() == ft.DEFAULT_SETTLE_MINUTES, bad
        assert "MEDLANG_TRIGGER_SETTLE_MINUTES" in capsys.readouterr().err
    monkeypatch.setenv("MEDLANG_TRIGGER_SETTLE_MINUTES", "30")
    assert ft.settle_minutes_from_env() == 30
    monkeypatch.delenv("MEDLANG_TRIGGER_SETTLE_MINUTES", raising=False)
    assert ft.settle_minutes_from_env() == ft.DEFAULT_SETTLE_MINUTES
    assert capsys.readouterr().err == ""  # valid or unset values warn nothing
