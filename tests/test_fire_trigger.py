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
    # commit_outputs must be stated explicitly wherever the workflow supports it
    # (validate_params guard); the helper builds a valid fire, and the guard has
    # its own dedicated test
    if isinstance(params, dict) and "commit_outputs" in ft.KNOWN_KEYS.get(trigger, set()):
        params = {"commit_outputs": "true", **params}
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
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    # The fire path refuses a trigger no workflow on this branch reads (exit 7),
    # so the throwaway repo needs a workflow naming each path, the way the real
    # workflows do in their `paths:` filter. pab-probe is left OUT deliberately:
    # it mirrors the real gemma branch, where the key is wired only on the PAB
    # branch, and it is what test_unwired_trigger_refused_with_exit_7 fires.
    wired = [t for t in ft.TRIGGERS if t != "pab-probe"]
    body = "on:\n  push:\n    paths:\n" + "".join(
        f'      - ".github/trigger/{name}.json"\n' for name in wired
    )
    (wf / "stub.yml").write_text(body, encoding="utf-8")
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
        "sample_size": "8", "max_spend": "1", "pairs_file": "p.json",
        "_nonce": "k3"}) == 0
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


def test_budget_dated_ceiling_override():
    # Owner-authorized dated raise (ops/budget_overrides.json): applies to exactly
    # its UTC date, carries its reason into the guard message, and a malformed
    # entry fails closed to the standing ceiling.
    ov = {"2026-07-23": {"ceiling_usd": 5.0, "reason": "build day"}}
    kind, reason = ft.budget_check({"max_spend": "4.5"}, {}, "2026-07-23", overrides=ov)
    assert kind == "ok" and "owner ceiling override" in reason and "build day" in reason
    # any other date: standing default 2.0 refuses the same fire
    assert ft.budget_check({"max_spend": "4.5"}, {}, "2026-07-24", overrides=ov)[0] == "ceiling"
    # the raised day still refuses past the raised ceiling
    assert ft.budget_check({"max_spend": "5.5"}, {}, "2026-07-23", overrides=ov)[0] == "ceiling"
    # malformed override entry -> fail closed to the standing ceiling
    bad = {"2026-07-23": {"ceiling_usd": "lots"}}
    assert ft.budget_check({"max_spend": "4.5"}, {}, "2026-07-23", overrides=bad)[0] == "ceiling"
    # loader tolerates a missing file
    assert ft.load_budget_overrides("/nonexistent/budget_overrides.json") == {}


def test_validate_params_pure_function():
    assert ft.validate_params(
        "circuit-trace", {"graph_model": "g", "commit_outputs": "true", "_note": "n"}) is None
    with pytest.raises(ValueError):
        ft.validate_params("circuit-trace", "not a dict")


def test_validate_params_requires_explicit_commit_outputs():
    # the push path defaults commit_outputs to false, which measures and then
    # discards every output (the seven lost meditron fires); the key must be
    # stated explicitly wherever the workflow supports it
    with pytest.raises(ValueError, match="commit_outputs"):
        ft.validate_params("logits-eval", {"models": "m", "limit": 1})
    assert ft.validate_params(
        "logits-eval", {"models": "m", "limit": 1, "commit_outputs": "false"}) is None
    # triggers without the key in their workflow are unaffected
    assert ft.validate_params("archive-renders", {"tag": "t"}) is None
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
    for released in (entry(resolved=True), entry(evicted=True),
                     entry(trigger="circuit-trace", max_spend=None)):
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


def test_mitigation_fire_detection_and_inflight_counting():
    import scripts.fire_trigger as ft
    assert ft.is_mitigation_fire("circuit-trace", {"show_mitigation": "true"})
    assert ft.is_mitigation_fire("circuit-trace", {"show_mitigation": "1"})
    assert not ft.is_mitigation_fire("circuit-trace", {})
    assert not ft.is_mitigation_fire("logits-eval", {"show_mitigation": "true"})
    # a mitigation circuit-trace entry with a recorded imputed commitment
    # counts toward today's in-flight spend
    from datetime import datetime, timezone
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    entry = {"trigger": "circuit-trace", "fired_utc": "2026-07-13T11:00:00Z",
             "commit": "", "note": "mitigation arm", "resolved": False,
             "evicted": False, "max_spend": ft.MITIGATION_IMPUTED_USD}
    total = ft.inflight_max_spend([entry], "2026-07-13", now, 8.0)
    assert total == ft.MITIGATION_IMPUTED_USD


# ---- advice-eval registration + judge-ceiling accounting (handoff rev 2) ----

def _advice_params(**over):
    p = {"stimuli_file": "data/advice/stimuli_x.json",
         "models": "anthropic:claude-haiku-4-5 openai google",
         "arms": "clinical,patient,translated", "samples": "3",
         "temperature": "1.0", "max_tokens": "1024",
         "translator_model": "claude-haiku-4-5", "max_spend": "1.50",
         "judge": "false", "judge_model": "claude-haiku-4-5",
         "judge_max_spend": "0.50", "rubric": "data/advice_rubric.json",
         "offset": "0", "limit": "0", "commit_outputs": "true"}
    p.update(over)
    return p


def test_advice_eval_registered_paid_with_exact_verified_keys(repo):
    assert "advice-eval" in ft.TRIGGERS
    assert "advice-eval" in ft.PAID_TRIGGERS
    write_dashboard(repo, spent=0.0)
    assert fire(repo, "advice-eval", _advice_params(_nonce="a1")) == 0
    assert trigger_path(repo, "advice-eval").exists()


def test_advice_eval_unknown_key_hard_error(repo):
    write_dashboard(repo, spent=0.0)
    assert fire(repo, "advice-eval",
                _advice_params(modles="typo", _nonce="a2")) != 0
    assert not trigger_path(repo, "advice-eval").exists()


def test_fire_commitment_sums_judge_ceiling_only_when_judging():
    assert ft.fire_commitment({"max_spend": "1.0"}) == (1.0, None)
    total, err = ft.fire_commitment(
        {"max_spend": "1.0", "judge": "true", "judge_max_spend": "0.5"})
    assert (total, err) == (1.5, None)
    # judge off: judge_max_spend present but NOT committed
    total, err = ft.fire_commitment(
        {"max_spend": "1.0", "judge": "false", "judge_max_spend": "0.5"})
    assert (total, err) == (1.0, None)
    # judge on without a usable judge ceiling: invalid, with a clear reason
    total, err = ft.fire_commitment({"max_spend": "1.0", "judge": "true"})
    assert total is None and "judge_max_spend" in err
    total, err = ft.fire_commitment(
        {"max_spend": "1.0", "judge": "true", "judge_max_spend": "nan"})
    assert total is None


def test_judged_fire_counts_both_ceilings_against_the_day(repo):
    write_dashboard(repo, spent=0.0)
    # 1.2 elicit + 0.9 judge = 2.1 > 2.0 ceiling: refused even though
    # max_spend alone would fit
    assert fire(repo, "advice-eval", _advice_params(
        max_spend="1.2", judge="true", judge_max_spend="0.9", _nonce="j1")) == 4
    assert not trigger_path(repo, "advice-eval").exists()
    # same fire un-judged fits
    assert fire(repo, "advice-eval", _advice_params(
        max_spend="1.2", judge="false", judge_max_spend="0.9", _nonce="j2")) == 0


def test_judged_fire_without_judge_ceiling_is_invalid_never_overridable(repo):
    write_dashboard(repo, spent=0.0)
    params = _advice_params(judge="true", _nonce="j3")
    del params["judge_max_spend"]
    assert fire(repo, "advice-eval", params) == 4
    assert fire(repo, "advice-eval", dict(params, _nonce="j4"),
                extra=("--override-budget",)) == 4  # invalid, not ceiling


def test_judged_fire_journal_entry_records_summed_commitment(repo):
    write_dashboard(repo, spent=0.0)
    assert fire(repo, "advice-eval", _advice_params(
        max_spend="0.60", judge="true", judge_max_spend="0.40", _nonce="j5")) == 0
    entry = json.loads(journal_path(repo).read_text().splitlines()[-1])
    assert entry["trigger"] == "advice-eval"
    assert entry["max_spend"] == pytest.approx(1.0)
    # a second paid fire the same day sees the full 1.0 in-flight: 1.2 would
    # break the 2.0 ceiling (1.0 + 1.2), 0.9 fits
    assert fire(repo, "scenario-generation", {
        "task": "pairs", "num": "5", "max_spend": "1.2", "_nonce": "j6"}) == 4
    assert fire(repo, "scenario-generation", {
        "task": "pairs", "num": "5", "max_spend": "0.9", "_nonce": "j7"}) == 0


def test_budget_ceiling_counts_anthropic_channel_only():
    """CHANNEL-SPLIT (owner 2026-08-04): the daily guard reads
    today.anthropic_usd when the ledger recorded the split, so
    separately-authorized OpenRouter spend cannot block Anthropic fires;
    dashboards without the split fall back to the pooled figure."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    split = {"spend": {"daily_ceiling_usd": 2.0,
                       "today": {"date": today, "spent_usd": 4.25,
                                 "anthropic_usd": 0.25, "openrouter_usd": 4.0}}}
    verdict, _ = ft.budget_check({"max_spend": "0.50"}, split, today)
    assert verdict == "ok"
    pooled = {"spend": {"daily_ceiling_usd": 2.0,
                        "today": {"date": today, "spent_usd": 4.25}}}
    verdict, msg = ft.budget_check({"max_spend": "0.50"}, pooled, today)
    assert verdict == "ceiling" and "4.25" in msg


def test_fire_lane_resolution():
    """Lanes minimal port 2026-08-07: only an all-OpenRouter advice-eval fire
    leaves the anthropic lane; everything ambiguous fails closed."""
    orl = "openai:openai/x,openrouter:google/y"
    assert ft.fire_lane("advice-eval", {"models": orl}) == "openrouter"
    assert ft.fire_lane("advice-eval", {"models": "anthropic:claude-x," + orl}) == "anthropic"  # mixed
    assert ft.fire_lane("advice-eval", {"models": "claude-x"}) == "anthropic"      # bare id = Anthropic
    assert ft.fire_lane("advice-eval", {"models": ""}) == "anthropic"              # workflow default
    assert ft.fire_lane("advice-eval", {}) == "anthropic"
    assert ft.fire_lane("scenario-generation", {"models": orl}) == "anthropic"     # other triggers


def test_budget_check_openrouter_lane_uses_its_own_ceiling():
    orl = {"models": "openai:openai/x,openrouter:google/y", "max_spend": "8.0"}
    # anthropic day is FULL, but the all-openrouter fire counts its own lane
    dash = {"spend": {"daily_ceiling_usd": 2.0,
                      "today": {"date": "2026-08-07", "anthropic_usd": 2.0,
                                "openrouter_usd": 0.0, "spent_usd": 2.0}}}
    kind, reason = ft.budget_check(orl, dash, "2026-08-07", trigger="advice-eval")
    assert kind == "ok" and "openrouter lane" in reason
    # the openrouter ceiling itself still refuses
    orl_big = dict(orl, max_spend="11.0")
    assert ft.budget_check(orl_big, dash, "2026-08-07", trigger="advice-eval")[0] == "ceiling"
    # a mixed-model fire stays on the (full) anthropic lane
    mixed = {"models": "anthropic:claude-x,openai:openai/x", "max_spend": "1.0"}
    assert ft.budget_check(mixed, dash, "2026-08-07", trigger="advice-eval")[0] == "ceiling"
    # missing channel split falls back pooled - fail closed on the openrouter lane too
    dash_pooled = {"spend": {"today": {"date": "2026-08-07", "spent_usd": 9.5}}}
    assert ft.budget_check(orl, dash_pooled, "2026-08-07", trigger="advice-eval")[0] == "ceiling"


def test_inflight_lane_filter_and_override_scope():
    now = ft.utc_now()
    today = now.strftime("%Y-%m-%d")
    entries = [{"trigger": "advice-eval", "fired_utc": ft.iso_utc(now), "resolved": False,
                "evicted": False, "max_spend": 8.0, "lane": "openrouter"}]
    # the openrouter in-flight hold does not block the anthropic lane
    assert ft.inflight_max_spend(entries, today, now, 8.0, lane="anthropic") == 0.0
    assert ft.inflight_max_spend(entries, today, now, 8.0, lane="openrouter") == 8.0
    # a dated owner override raises the ANTHROPIC ceiling only
    dash = {"spend": {"daily_ceiling_usd": 2.0,
                      "today": {"date": today, "anthropic_usd": 0.0, "openrouter_usd": 9.5,
                                "spent_usd": 9.5}}}
    ov = {today: {"ceiling_usd": 10.0, "reason": "owner"}}
    anth = {"models": "anthropic:claude-x", "max_spend": "5.0"}
    kind, reason = ft.budget_check(anth, dash, today, overrides=ov, trigger="advice-eval")
    assert kind == "ok" and "override" in reason
    orl = {"models": "openai:openai/x", "max_spend": "1.0"}
    assert ft.budget_check(orl, dash, today, overrides=ov, trigger="advice-eval")[0] == "ceiling"


def test_unwired_trigger_refused_with_exit_7(repo, capsys):
    """A KNOWN key with no workflow behind it must refuse, not silently no-op.

    Unknown keys already hard-error. A known-but-unwired key used to validate,
    write the trigger file, journal the fire and push - running nothing, and
    leaving a journal entry for a run that never existed (owner decision
    2026-08-15). The key stays in TRIGGERS because it is wired on another
    branch; the check is branch-local.
    """
    code = fire(repo, trigger="pab-probe",
                params={"stage": "analyze", "max_spend": "1.0", "commit_sidecar": "false"},
                note="unwired fire")
    assert code == 7
    assert "no workflow on this branch reads" in capsys.readouterr().err
    assert not trigger_path(repo, "pab-probe").exists()      # nothing written
    assert ft.load_journal(journal_path(repo)) == []          # nothing journaled


def test_workflow_reads_trigger_is_branch_local(repo):
    assert ft.workflow_reads_trigger(repo, "circuit-trace") is True
    assert ft.workflow_reads_trigger(repo, "pab-probe") is False
    # a workflow appearing on the branch flips it live, no code change needed
    (repo / ".github" / "workflows" / "pab_probe.yml").write_text(
        'on:\n  push:\n    paths:\n      - ".github/trigger/pab-probe.json"\n', encoding="utf-8")
    assert ft.workflow_reads_trigger(repo, "pab-probe") is True


def test_budget_gate_free_trigger_clears(repo, capsys):
    (repo / ".github" / "trigger" / "logits-eval.json").write_text(
        '{"models": "m", "limit": "25"}', encoding="utf-8")
    rc = ft.main(["budget-gate", "--repo", str(repo), "--trigger", "logits-eval"])
    assert rc == 0
    assert "free fire" in capsys.readouterr().out


def test_budget_gate_refuses_over_ceiling_with_exit_6(repo, capsys):
    (repo / ".github" / "trigger" / "model-evaluation.json").write_text(
        '{"model_selection": "claude-haiku-4-5", "max_spend": "999"}', encoding="utf-8")
    rc = ft.main(["budget-gate", "--repo", str(repo), "--trigger", "model-evaluation"])
    assert rc == 6
    assert "REFUSED" in capsys.readouterr().err


def test_budget_gate_clears_within_ceiling_and_reads_params_file(repo, tmp_path, capsys):
    pf = tmp_path / "params.json"
    pf.write_text('{"model_selection": "claude-haiku-4-5", "max_spend": "0.25"}',
                  encoding="utf-8")
    rc = ft.main(["budget-gate", "--repo", str(repo), "--trigger", "model-evaluation",
                  "--params-file", str(pf)])
    assert rc == 0
    assert "clear" in capsys.readouterr().out


def test_budget_gate_counts_landed_spend_from_dashboard(repo, capsys):
    today = ft.utc_now().strftime("%Y-%m-%d")
    (repo / "ops" / "dashboard.json").write_text(json.dumps({
        "spend": {"daily_ceiling_usd": 2.0,
                  "today": {"date": today, "spent_usd": 1.9, "anthropic_usd": 1.9}}}),
        encoding="utf-8")
    (repo / ".github" / "trigger" / "model-evaluation.json").write_text(
        '{"model_selection": "claude-haiku-4-5", "max_spend": "0.50"}', encoding="utf-8")
    rc = ft.main(["budget-gate", "--repo", str(repo), "--trigger", "model-evaluation"])
    assert rc == 6
    assert "REFUSED" in capsys.readouterr().err


def test_budget_gate_missing_params_file_refuses(repo, capsys):
    rc = ft.main(["budget-gate", "--repo", str(repo), "--trigger", "scenario-generation"])
    assert rc == 6
    assert "cannot read params" in capsys.readouterr().err


# ------------------------------------------------------------------ park (resting-state rule)

def test_park_defaults_all_validate():
    for trigger, params in ft.PARK_DEFAULTS.items():
        ft.validate_params(trigger, params)  # raises on any drifted key set
        if "commit_outputs" in ft.KNOWN_KEYS[trigger]:
            assert params["commit_outputs"] == "false", trigger
        if trigger in ft.PAID_TRIGGERS:
            assert ft.parse_max_spend(params.get("max_spend")) is not None, trigger


def test_park_writes_no_op_default_with_marker(repo):
    write_dashboard(repo, 0.0)
    rc = ft.main(["park", "--repo", str(repo), "--trigger", "logits-eval", "--no-git"])
    assert rc == 0
    written = json.loads(trigger_path(repo, "logits-eval").read_text())
    assert written["_parked"] == "true"
    assert written["limit"] == "1"
    assert written["commit_outputs"] == "false"
    assert "_nonce" in written
    entries = [json.loads(line) for line in journal_path(repo).read_text().splitlines()]
    assert entries[-1]["trigger"] == "logits-eval"
    assert "PARK" in entries[-1]["note"]


def test_park_all_stops_at_first_refusal(repo, capsys):
    # a full lane (two active entries) trips the queue guard mid-batch and the
    # batch stops there instead of blindly continuing past a refusal
    write_dashboard(repo, 0.0)
    fire(repo, "circuit-trace")
    fire(repo, "circuit-trace", params={"graph_model": "gemma-2-2b", "mode": "4quadrant"})
    order = sorted(ft.PARK_DEFAULTS)
    rc = ft.main(["park", "--repo", str(repo), "--all", "--no-git"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "park stopped at circuit-trace" in err
    # triggers before the refusal were parked; the refused one keeps its old content
    for t in order:
        if t == "circuit-trace":
            assert "_parked" not in json.loads(trigger_path(repo, t).read_text())
            break
        assert json.loads(trigger_path(repo, t).read_text())["_parked"] == "true"


def test_park_all_succeeds_with_budget(repo):
    write_dashboard(repo, 0.0)
    rc = ft.main(["park", "--repo", str(repo), "--all", "--no-git"])
    assert rc == 0
    for t in ft.PARK_DEFAULTS:
        assert json.loads(trigger_path(repo, t).read_text())["_parked"] == "true"
