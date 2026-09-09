"""Tests for scripts/fire_trigger.py - the push-to-run trigger guard.

scripts/ is not a package, so the module loads via importlib from its file
path. Every CLI-level test passes --no-git against a throwaway repo layout
under tmp_path; nothing here touches git or the network.
"""

import importlib.util
import json
import subprocess
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
    assert fire(repo, params={"mode": "2panel", "_nonce": "2"}, note="second",
                extra=("--keep-dashboard",)) == 0
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
    assert fire(repo, "archive-renders", params={
        "tag": "prune-a", "runs": "trace_out/x", "prune_only": True, "_nonce": "k2b"}) == 0
    # a third archive fire would be a queue refusal (two active), so the newest
    # key is checked at the validator
    assert ft.validate_params("archive-renders", {"tag": "t2", "runs": "trace_out/x", "prune": True,
                                                  "allow_shrink": True}) is None
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
    assert fire(repo, params=params, note="first", extra=("--keep-dashboard",)) == 0
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


# --- dashboard single-writer: the script never commits the dashboard and restores
# --- its side effect unless --keep-dashboard (AGENTS.md, Single-writer; 2026-09-06)

def test_fire_restores_dashboard_unless_keep(repo):
    write_dashboard(repo, 0.0)
    before = (repo / "ops" / "dashboard.json").read_bytes()
    assert fire(repo) == 0
    assert (repo / "ops" / "dashboard.json").read_bytes() == before, "side effect leaked"
    assert fire(repo, params={"graph_model": "gemma-2-2b", "mode": "2panel", "_nonce": "k1"},
                extra=("--keep-dashboard",)) == 0
    after = json.loads((repo / "ops" / "dashboard.json").read_text(encoding="utf-8"))
    assert after["updated_by"] == "session" and "circuit-trace" in after["queue"]


def test_fire_without_dashboard_creates_none(repo):
    assert not (repo / "ops" / "dashboard.json").exists()
    assert fire(repo) == 0
    assert not (repo / "ops" / "dashboard.json").exists()


def test_resolve_restores_dashboard_unless_keep(repo):
    write_dashboard(repo, 0.0)
    assert fire(repo) == 0
    before = (repo / "ops" / "dashboard.json").read_bytes()
    assert ft.main(["resolve", "--repo", str(repo), "--trigger", "circuit-trace"]) == 0
    assert (repo / "ops" / "dashboard.json").read_bytes() == before
    assert fire(repo, params={"graph_model": "gemma-2-2b", "mode": "2panel", "_nonce": "k2"},
                extra=("--keep-dashboard", "--ignore-settle")) == 0  # resolved seconds ago; run is terminal here
    assert ft.main(["resolve", "--repo", str(repo), "--trigger", "circuit-trace", "--keep-dashboard"]) == 0
    after = json.loads((repo / "ops" / "dashboard.json").read_text(encoding="utf-8"))
    assert after["queue"]["circuit-trace"]["running"] is None


def test_git_publish_never_stages_the_dashboard(repo, monkeypatch):
    staged = []

    def fake_git(repo_, *argv, env=None):
        class P:
            returncode = 0
            stdout = "main\n"
            stderr = ""
        if argv and argv[0] == "add":
            staged.extend(argv[2:])
        return P()

    monkeypatch.setattr(ft, "_git", fake_git)
    monkeypatch.setattr(ft, "_push_with_token", lambda repo_, branch, env=None: fake_git(repo_, "push"))
    write_dashboard(repo, 0.0)
    (repo / "ops" / "trigger_journal.jsonl").write_text("", encoding="utf-8")
    argv = ["fire", "--repo", str(repo), "--trigger", "circuit-trace",
            "--params", json.dumps({"commit_outputs": "true", "graph_model": "gemma-2-2b", "mode": "2panel"}),
            "--note", "publish path"]
    assert ft.main(argv) == 0
    assert staged, "git add was not called"
    assert not any(s.endswith("dashboard.json") for s in staged), staged


def _git_init(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)


def test_ensure_git_hooks_sets_hookspath_only_in_a_git_checkout(tmp_path):
    plain = tmp_path / "plain"
    (plain / ".githooks").mkdir(parents=True)
    assert ft.ensure_git_hooks(plain) is False          # not a work tree: left alone
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    assert ft.ensure_git_hooks(repo) is False           # no .githooks/ to point at
    (repo / ".githooks").mkdir()
    assert ft.ensure_git_hooks(repo) is True
    got = subprocess.run(["git", "-C", str(repo), "config", "--get", "core.hooksPath"],
                         capture_output=True, text=True).stdout.strip()
    assert got == ".githooks"


def test_git_publish_commits_and_pushes_under_one_fire_token(repo, monkeypatch):
    seen = {}

    def fake_git(repo_, *argv, env=None):
        class P:
            returncode = 0
            stdout = "main\n"
            stderr = ""
        if argv and argv[0] in ("commit", "push"):
            seen[argv[0]] = (env or {}).get("PW_FIRE_TOKEN")
        return P()

    monkeypatch.setattr(ft, "_git", fake_git)
    assert ft.git_publish(repo, [repo / "ops" / "trigger_journal.jsonl"], "msg", backoff=()) is True
    assert seen["commit"] and seen["commit"] == seen["push"], seen


# ---------------------------------------------------------------------------
# archive-renders: a tag whose manifest is already on the branch is refused
# (the 2026-09-08 duplicate p3 fire), unless --reuse-tag says the reuse is meant
# ---------------------------------------------------------------------------


def _archive_params(tag, **extra):
    return {"tag": tag, "runs": ["trace_out/pairs_x"], "prune": "true", **extra}


def test_archive_fire_refuses_a_tag_whose_manifest_is_on_the_branch(repo, capsys):
    (repo / "render_archives").mkdir()
    (repo / "render_archives" / "renders-20260908-p3.manifest.json").write_text("{}", encoding="utf-8")
    assert fire(repo, "archive-renders", _archive_params("renders-20260908-p3")) == 8
    err = capsys.readouterr().err
    assert "already on this branch" in err and "--reuse-tag" in err and "duplicate-fire" in err
    assert not (repo / ".github" / "trigger" / "archive-renders.json").exists()   # nothing written
    assert not (repo / "ops" / "trigger_journal.jsonl").exists()


def test_archive_fire_with_a_fresh_tag_or_reuse_tag_proceeds(repo):
    (repo / "render_archives").mkdir()
    (repo / "render_archives" / "renders-20260908-p3.manifest.json").write_text("{}", encoding="utf-8")
    assert fire(repo, "archive-renders", _archive_params("renders-20260908-p4")) == 0
    assert fire(repo, "archive-renders", _archive_params("renders-20260908-p3", _nonce="again"),
                extra=["--reuse-tag", "--ignore-settle"]) == 0


def test_park_is_exempt_from_the_reused_tag_refusal(repo):
    (repo / "render_archives").mkdir()
    (repo / "render_archives" / "park-noop.manifest.json").write_text("{}", encoding="utf-8")
    assert ft.main(["park", "--repo", str(repo), "--trigger", "archive-renders", "--no-git"]) == 0


def test_archive_tag_has_manifest_reads_head_when_the_sparse_checkout_hides_the_file(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git_init(repo)
    (repo / "render_archives").mkdir()
    (repo / "render_archives" / "renders-x.manifest.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "m"], check=True)
    (repo / "render_archives" / "renders-x.manifest.json").unlink()   # as a sparse cone leaves it
    assert ft.archive_tag_has_manifest(repo, "renders-x") is True
    assert ft.archive_tag_has_manifest(repo, "renders-y") is False
    (tmp_path / "not-a-repo").mkdir()
    assert ft.archive_tag_has_manifest(tmp_path / "not-a-repo", "renders-x") is False   # filesystem only


def test_archive_tag_guard_fails_closed_on_a_git_error_inside_a_work_tree(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "r"
    repo.mkdir()
    _git_init(repo)
    (repo / "x").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "m"], check=True)
    real = ft._git

    def broken_git(repo_, *argv, env=None):
        if argv and argv[0] == "ls-tree":
            class P:
                returncode = 128
                stdout = ""
                stderr = "fatal: unable to read tree"
            return P()
        return real(repo_, *argv, env=env)

    monkeypatch.setattr(ft, "_git", broken_git)
    assert ft.archive_tag_has_manifest(repo, "renders-x") is None
    rc = ft.refuse_reused_archive_tag(repo, "archive-renders", _archive_params("renders-x"), reuse_tag=False, parked=False)
    assert rc == 8 and "fails closed" in capsys.readouterr().err


def test_archive_fire_prune_only_is_exempt_but_a_parked_param_is_not(repo, capsys):
    (repo / "render_archives").mkdir()
    (repo / "render_archives" / "renders-20260721-pt5.manifest.json").write_text("{}", encoding="utf-8")
    # the _parked param is metadata: only the park command path is exempt
    assert fire(repo, "archive-renders", _archive_params("renders-20260721-pt5", _parked="true")) == 8
    assert "already on this branch" in capsys.readouterr().err
    assert fire(repo, "archive-renders", _archive_params("renders-20260721-pt5", prune_only="false")) == 8
    assert not (repo / "ops" / "trigger_journal.jsonl").exists()      # refusals journal nothing
    # prune_only reuses the tag whose Release holds the PNGs by design and uploads nothing
    assert fire(repo, "archive-renders", _archive_params("renders-20260721-pt5", prune_only="true")) == 0
    assert fire(repo, "archive-renders", _archive_params("renders-20260721-pt5", prune_only=True, _nonce="2"),
                extra=["--ignore-settle"]) == 0


def test_archive_fire_checks_the_fetched_remote_tip_not_only_the_local_head(tmp_path, capsys):
    """CI's manifest commit can land on the remote after the local HEAD was cut:
    the tag is a duplicate even though HEAD and the sparse tree show nothing."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    _git_init(clone)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", "main"], check=True)
    (clone / ".github" / "trigger").mkdir(parents=True)
    (clone / ".github" / "workflows").mkdir()
    (clone / ".github" / "workflows" / "stub.yml").write_text(
        'on:\n  push:\n    paths:\n      - ".github/trigger/archive-renders.json"\n', encoding="utf-8")
    (clone / "ops").mkdir()
    (clone / "README.md").write_text("base", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(clone), "commit", "-q", "-m", "base"], check=True)
    subprocess.run(["git", "-C", str(clone), "push", "-q", "-u", "origin", "main"], check=True)
    other = tmp_path / "ci"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git_init(other)
    (other / "render_archives").mkdir()
    (other / "render_archives" / "renders-20260908-p9.manifest.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "Archive renders: p9"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "main"], check=True)
    assert ft.archive_tag_has_manifest(clone, "renders-20260908-p9") is False       # HEAD alone cannot see it
    assert fire(clone, "archive-renders", _archive_params("renders-20260908-p9")) == 8
    assert "remote tip origin/main" in capsys.readouterr().err
    assert fire(clone, "archive-renders", _archive_params("renders-20260908-p10")) == 0



# ---------------------------------------------------------------------------
# publish: re-push a fire whose push was rejected (docs/operators_handbook.md, 4)
# ---------------------------------------------------------------------------

PUBLISH_PARAMS = {"commit_outputs": "true", "graph_model": "gemma-2-2b", "mode": "2panel"}


def _publish_fixture(tmp_path):
    """A bare origin, a clone with one pushed commit (a workflow stub reading every
    trigger, a parked trigger file, a one-line journal, a README), on main with
    origin/main tracked. Returns (origin, clone)."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", "main"], check=True)
    (clone / "ops").mkdir()
    (clone / ".github" / "trigger").mkdir(parents=True)
    wf = clone / ".github" / "workflows"
    wf.mkdir()
    (wf / "stub.yml").write_text("on:\n  push:\n    paths:\n" + "".join(
        f'      - ".github/trigger/{t}.json"\n' for t in ft.TRIGGERS if t != "pab-probe"), encoding="utf-8")
    (clone / "ops" / "trigger_journal.jsonl").write_text(
        json.dumps({"trigger": "circuit-trace", "fired_utc": "2026-01-01T00:00:00Z", "commit": "", "note": "old",
                    "resolved": True, "evicted": False, "resolved_utc": "2026-01-01T01:00:00Z"}) + "\n",
        encoding="utf-8")
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text('{"a": 1}\n', encoding="utf-8")
    (clone / "README.md").write_text("base\n", encoding="utf-8")
    _commit(clone, "base")
    subprocess.run(["git", "-C", str(clone), "push", "-q", "-u", "origin", "main"], check=True)
    return origin, clone


def _commit(repo, message):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True)


def _journal_line(trigger, fired_utc, **extra):
    entry = {"trigger": trigger, "fired_utc": fired_utc, "commit": "", "note": f"{trigger} fire",
             "resolved": False, "evicted": False, **extra}
    return json.dumps(entry) + "\n"


def _fire_locally(clone, trigger="circuit-trace", params=None, fired_utc=None, journal=True):
    """What cmd_fire leaves behind when its push is rejected: the trigger file and
    the journal entry committed on the local branch."""
    params = PUBLISH_PARAMS if params is None else params
    fired_utc = fired_utc or ft.iso_utc(ft.utc_now())
    (clone / ".github" / "trigger" / f"{trigger}.json").write_text(json.dumps(params) + "\n", encoding="utf-8")
    if journal:
        with (clone / "ops" / "trigger_journal.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(_journal_line(trigger, fired_utc))
    _commit(clone, f"Fire {trigger}: local")
    return fired_utc


def _advance_origin(origin, tmp_path, name, write):
    """Push a commit to origin from a second clone, as another session or CI would."""
    other = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    subprocess.run(["git", "-C", str(other), "config", "user.email", "o@example.com"], check=True)
    subprocess.run(["git", "-C", str(other), "config", "user.name", "o"], check=True)
    write(other)
    _commit(other, f"{name} moved main")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "main"], check=True)


def _append_journal(path, *lines):
    with path.open("a", encoding="utf-8") as fh:
        fh.write("".join(lines))


def _origin_main_files(origin, tmp_path):
    check = tmp_path / f"check{len(list(tmp_path.iterdir()))}"
    subprocess.run(["git", "clone", "-q", str(origin), str(check)], check=True)
    return {p.relative_to(check).as_posix(): p.read_text(encoding="utf-8")
            for p in check.rglob("*") if p.is_file() and ".git" not in p.parts}


def _resolve_journal_union(clone):
    """The handbook's journal rule, as an operator applies it inside a stopped
    rebase: both sides, deduped on (fired_utc, trigger) preferring the remote
    (stage 2 during a rebase), sorted by fired_utc, then continue."""
    j = "ops/trigger_journal.jsonl"
    ours = subprocess.run(["git", "-C", str(clone), "show", f":2:{j}"], capture_output=True, text=True).stdout
    theirs = subprocess.run(["git", "-C", str(clone), "show", f":3:{j}"], capture_output=True, text=True).stdout
    seen = {}
    for line in theirs.splitlines() + ours.splitlines():      # remote side last, so it wins
        if line.strip():
            e = json.loads(line)
            seen[(e["fired_utc"], e["trigger"])] = line
    lines = sorted(seen.values(), key=lambda ln: json.loads(ln)["fired_utc"])
    (clone / j).write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", j], check=True)
    subprocess.run(["git", "-C", str(clone), "-c", "core.editor=true", "rebase", "--continue"], check=True)


def _pull_conflicts_then_union(clone):
    """Two sessions appending to the journal always conflict on rebase; the
    operator resolves it by hand and then runs `publish`, which is the state the
    revalidation guards exist for."""
    pulled = subprocess.run(["git", "-C", str(clone), "pull", "--rebase", "origin", "main"],
                            capture_output=True, text=True)
    assert pulled.returncode != 0 and "trigger_journal" in pulled.stdout + pulled.stderr
    _resolve_journal_union(clone)


def _head(clone):
    return subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def test_publish_reports_nothing_when_origin_has_every_commit(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    assert "nothing to publish" in capsys.readouterr().out


def test_publish_rebases_a_rejected_fire_onto_the_moved_branch_and_pushes(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    _advance_origin(origin, tmp_path, "other", lambda r: (r / "README.md").write_text("moved\n", encoding="utf-8"))
    rejected = subprocess.run(["git", "-C", str(clone), "push", "origin", "main"], capture_output=True, text=True)
    assert rejected.returncode != 0 and "rejected" in rejected.stderr  # the exit-1 situation

    assert ft.main(["publish", "--repo", str(clone), "--dry-run"]) == 0
    assert "would rebase 1 commit" in capsys.readouterr().out
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    out = capsys.readouterr().out
    assert "published 1 commit" in out and "circuit-trace.json" in out

    files = _origin_main_files(origin, tmp_path)
    assert files["README.md"] == "moved\n"                                       # the other session's commit kept
    assert json.loads(files[".github/trigger/circuit-trace.json"]) == PUBLISH_PARAMS   # the fire landed on top
    assert files["ops/trigger_journal.jsonl"].count("\n") == 2
    log = subprocess.run(["git", "-C", str(clone), "log", "--format=%s", "origin/main"],
                         capture_output=True, text=True).stdout.split("\n")
    assert log[0] == "Fire circuit-trace: local" and log[1] == "other moved main"   # rebased, not merged
    assert not (clone / ".git" / "rebase-merge").exists()


def test_publish_refuses_unpushed_commits_outside_the_fire_paths(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    (clone / "README.md").write_text("also edited\n", encoding="utf-8")
    _fire_locally(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "README.md" in err and "re-publishes a fire and nothing else" in err
    assert _origin_main_files(origin, tmp_path)["README.md"] == "base\n"   # nothing pushed


def test_publish_refuses_a_trigger_change_that_no_journal_entry_accompanies(tmp_path, capsys):
    """A trigger-only commit (made while the hooks were absent) must not get the
    token: it would bypass every guard and leave no record of the run."""
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone, journal=False)
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "no journal entry" in capsys.readouterr().err
    assert _origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"] == '{"a": 1}\n'


def test_publish_refuses_a_journal_only_or_two_trigger_change(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _append_journal(clone / "ops" / "trigger_journal.jsonl", _journal_line("logits-eval", "2026-09-09T00:00:00Z"))
    _commit(clone, "journal only")
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "plain `git push`" in capsys.readouterr().err
    (clone / ".github" / "trigger" / "logits-eval.json").write_text("{}", encoding="utf-8")
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text("{}", encoding="utf-8")
    _commit(clone, "two triggers")
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "exactly one known trigger file" in capsys.readouterr().err


def test_publish_refuses_a_dirty_checkout_instead_of_autostashing(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    _append_journal(clone / "ops" / "trigger_journal.jsonl", _journal_line("jlens-readout", "2026-09-09T00:00:00Z"))
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "uncommitted changes" in err and "trigger_journal.jsonl" in err
    _commit(clone, "the resolve")          # committed, the journal-only commit rides along with the fire
    assert ft.main(["publish", "--repo", str(clone)]) == 0


def test_publish_revalidates_the_queue_against_the_rebased_journal(tmp_path, capsys):
    """Two other fires filled the lane while this one sat unpublished: pushing it
    would enter the concurrency group as a third run (AGENTS.md, queue discipline)."""
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    now = ft.utc_now()
    stamps = [ft.iso_utc(now - timedelta(minutes=m)) for m in (20, 10)]
    _advance_origin(origin, tmp_path, "other", lambda r: _append_journal(
        r / "ops" / "trigger_journal.jsonl", *[_journal_line("circuit-trace", s) for s in stamps]))
    _pull_conflicts_then_union(clone)
    before = _head(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 2
    err = capsys.readouterr().err
    assert "2 other circuit-trace entries are active" in err and "third run" in err
    assert _head(clone) == before                    # kept local, ready for a later publish
    assert ".github/trigger/circuit-trace.json" in _origin_main_files(origin, tmp_path)
    assert json.loads(_origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"]) == {"a": 1}


def test_publish_revalidates_the_settle_window_unless_told_the_run_is_terminal(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    resolved = ft.iso_utc(ft.utc_now() - timedelta(minutes=2))
    _advance_origin(origin, tmp_path, "other", lambda r: _append_journal(
        r / "ops" / "trigger_journal.jsonl",
        _journal_line("circuit-trace", ft.iso_utc(ft.utc_now() - timedelta(minutes=30)),
                      resolved=True, resolved_utc=resolved)))
    _pull_conflicts_then_union(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 6
    assert "settle window" in capsys.readouterr().err
    assert ft.main(["publish", "--repo", str(clone), "--ignore-settle"]) == 0


def test_publish_rechecks_the_budget_with_the_rebased_dashboard(tmp_path, capsys):
    """Spend landed while the paid fire sat unpublished: the headroom cmd_fire saw
    is gone, and the delayed push must be refused (or explicitly overridden)."""
    origin, clone = _publish_fixture(tmp_path)
    write_dashboard(clone, spent=0.5)
    _commit(clone, "dashboard")
    subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "main"], check=True)
    _fire_locally(clone, "scenario-generation", {"task": "pairs", "num": "5", "max_spend": "1.0"})
    _advance_origin(origin, tmp_path, "routine", lambda r: write_dashboard(r, spent=1.5))
    assert ft.main(["publish", "--repo", str(clone)]) == 4
    assert "refused:" in capsys.readouterr().err
    assert ".github/trigger/scenario-generation.json" not in _origin_main_files(origin, tmp_path)
    assert ft.main(["publish", "--repo", str(clone), "--override-budget"]) == 0
    assert "budget override" in capsys.readouterr().err


def test_publish_refuses_a_trigger_file_that_no_longer_validates(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone, params={"graph_model": "gemma-2-2b", "surprise": "1"})
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "does not hold a valid fire" in capsys.readouterr().err


def test_publish_aborts_a_conflicting_rebase_and_leaves_the_checkout_clean(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    _advance_origin(origin, tmp_path, "other",
                    lambda r: (r / ".github" / "trigger" / "circuit-trace.json").write_text('{"a": 3}\n',
                                                                                             encoding="utf-8"))
    head_before = _head(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 1
    err = capsys.readouterr().err
    assert "aborted" in err and "ORDERED UNION" in err and "Never re-fire" in err
    assert not (clone / ".git" / "rebase-merge").exists() and not (clone / ".git" / "rebase-apply").exists()
    assert _head(clone) == head_before
    assert _origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"] == '{"a": 3}\n'


def test_publish_refuses_a_detached_head(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", "--detach"], check=True)
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "detached" in capsys.readouterr().err


def test_is_publishable_covers_exactly_the_fire_paths():
    assert ft.is_publishable(".github/trigger/archive-renders.json")
    assert ft.is_publishable("ops/trigger_journal.jsonl")
    assert not ft.is_publishable("ops/dashboard.json")
    assert not ft.is_publishable(".github/workflows/archive_renders.yml")
    assert not ft.is_publishable("README.md")
    # exact paths only: the tokened push publishes every commit it carries, and
    # the repository is public
    assert not ft.is_publishable(".github/trigger/private/token.txt")
    assert not ft.is_publishable(".github/trigger/private/circuit-trace.json")
    assert not ft.is_publishable(".github/trigger/README.md")
    assert not ft.is_publishable(".github/trigger/not-a-lane.json")
    assert not ft.is_publishable("ops/trigger_journal.jsonl.bak")
    assert not ft.is_publishable("ops/private/trigger_journal.jsonl")


def test_publish_refuses_a_file_nested_under_the_trigger_directory(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    nested = clone / ".github" / "trigger" / "private" / "token.txt"
    nested.parent.mkdir()
    nested.write_text("not a trigger\n", encoding="utf-8")
    _commit(clone, "stray file")
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "change files outside" in err and ".github/trigger/private/token.txt" in err
    assert not _origin_main_files(origin, tmp_path).get(".github/trigger/private/token.txt")


def test_publish_commits_a_fire_whose_own_commit_failed_and_pushes_it(tmp_path, capsys):
    """git_publish exits 1 before the commit too (a failed add or commit): the
    trigger file and journal entry are written and uncommitted, nothing is ahead
    of origin, and the fire has not run. `publish` commits it under the token, as
    cmd_fire would have, then pushes."""
    origin, clone = _publish_fixture(tmp_path)
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(PUBLISH_PARAMS) + "\n",
                                                                       encoding="utf-8")
    _append_journal(clone / "ops" / "trigger_journal.jsonl", _journal_line("circuit-trace", ft.iso_utc(ft.utc_now())))
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    out = capsys.readouterr().out
    assert "committed the uncommitted circuit-trace fire" in out and "published 1 commit" in out
    log = subprocess.run(["git", "-C", str(clone), "log", "--format=%s", "-1", "origin/main"],
                         capture_output=True, text=True).stdout.strip()
    assert log == "Fire circuit-trace: circuit-trace fire"
    assert json.loads(_origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"]) == PUBLISH_PARAMS
    assert not subprocess.run(["git", "-C", str(clone), "status", "--porcelain"], capture_output=True,
                              text=True).stdout.strip()


def test_publish_refuses_an_uncommitted_trigger_change_without_its_journal_entry(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(PUBLISH_PARAMS) + "\n",
                                                                       encoding="utf-8")
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "not one fire's trigger file plus its journal entry" in capsys.readouterr().err
    assert _origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"] == '{"a": 1}\n'


def test_publish_refuses_two_unpublished_fires_of_one_trigger(tmp_path, capsys):
    """One push runs the lane once with the last trigger content; the earlier
    journaled fire would never run while holding a queue slot."""
    origin, clone = _publish_fixture(tmp_path)
    first = _fire_locally(clone, fired_utc=ft.iso_utc(ft.utc_now() - timedelta(minutes=5)))
    _fire_locally(clone, params={**PUBLISH_PARAMS, "_nonce": "second"})
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "2 active circuit-trace fires" in err and "evicted" in err
    assert ".github/trigger/circuit-trace.json" in _origin_main_files(origin, tmp_path)
    assert _origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"] == '{"a": 1}\n'
    # the operator marks the superseded entry evicted by hand and commits; one fire remains
    j = clone / "ops" / "trigger_journal.jsonl"
    lines = j.read_text(encoding="utf-8").splitlines()
    fixed = []
    for line in lines:
        e = json.loads(line)
        if e["fired_utc"] == first:
            e["evicted"] = True
        fixed.append(json.dumps(e))
    j.write_text("\n".join(fixed) + "\n", encoding="utf-8")
    _commit(clone, "evict the superseded fire")
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    files = _origin_main_files(origin, tmp_path)
    assert json.loads(files[".github/trigger/circuit-trace.json"])["_nonce"] == "second"
    entries = [json.loads(ln) for ln in files["ops/trigger_journal.jsonl"].splitlines() if ln.strip()]
    assert [e["evicted"] for e in entries if e["fired_utc"] == first] == [True]


def _resolve_taking_local_side(clone):
    """The mistake the preserve check exists for: the operator ends the journal
    conflict by keeping only the local side (stage 3 during a rebase)."""
    j = "ops/trigger_journal.jsonl"
    theirs = subprocess.run(["git", "-C", str(clone), "show", f":3:{j}"], capture_output=True, text=True).stdout
    (clone / j).write_text(theirs, encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", j], check=True)
    subprocess.run(["git", "-C", str(clone), "-c", "core.editor=true", "rebase", "--continue"], check=True)


def test_publish_restamps_a_fire_published_long_after_it_was_made(tmp_path, capsys):
    """Budget counts in-flight entries fired today and the queue expires entries
    older than expire_hours, so a fire published a day late must carry the
    publication time as its fired_utc, with the original kept alongside."""
    origin, clone = _publish_fixture(tmp_path)
    old = ft.iso_utc(ft.utc_now() - timedelta(hours=26))
    _fire_locally(clone, fired_utc=old)
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    out = capsys.readouterr().out
    assert "corrected the circuit-trace fire's journal record: fired_utc" in out and "published 2 commit" in out
    entries = [json.loads(ln) for ln in _origin_main_files(origin, tmp_path)["ops/trigger_journal.jsonl"].splitlines()
               if ln.strip()]
    mine = [e for e in entries if e.get("fired_utc_original") == old]
    assert len(mine) == 1
    assert mine[0]["fired_utc"][:10] == ft.iso_utc(ft.utc_now())[:10] and mine[0]["published_utc"] == mine[0]["fired_utc"]
    assert ft.active_entries(entries, "circuit-trace", ft.utc_now(), 8.0), "the published run must count as active"
    # a fire published within the hour keeps its stamp
    origin2, clone2 = _publish_fixture(tmp_path / "second")
    recent = _fire_locally(clone2)
    assert ft.main(["publish", "--repo", str(clone2)]) == 0
    assert "corrected the" not in capsys.readouterr().out
    entries2 = [json.loads(ln) for ln in _origin_main_files(origin2, tmp_path / "second")["ops/trigger_journal.jsonl"]
                .splitlines() if ln.strip()]
    assert any(e["fired_utc"] == recent and "fired_utc_original" not in e for e in entries2)


def test_publish_dry_run_reports_an_uncommitted_fire_without_committing_it(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(PUBLISH_PARAMS) + "\n",
                                                                       encoding="utf-8")
    _append_journal(clone / "ops" / "trigger_journal.jsonl", _journal_line("circuit-trace", ft.iso_utc(ft.utc_now())))
    head = _head(clone)
    assert ft.main(["publish", "--repo", str(clone), "--dry-run"]) == 0
    assert "would commit the uncommitted circuit-trace fire" in capsys.readouterr().out
    assert _head(clone) == head                                                  # nothing committed
    assert subprocess.run(["git", "-C", str(clone), "status", "--porcelain"], capture_output=True,
                          text=True).stdout.strip()                             # still dirty, as found


def test_publish_refuses_a_journal_that_dropped_a_remote_entry(tmp_path, capsys):
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone)
    live = ft.iso_utc(ft.utc_now() - timedelta(minutes=30))
    _advance_origin(origin, tmp_path, "other", lambda r: _append_journal(
        r / "ops" / "trigger_journal.jsonl", _journal_line("circuit-trace", live)))
    pulled = subprocess.run(["git", "-C", str(clone), "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
    assert pulled.returncode != 0
    _resolve_taking_local_side(clone)                       # the remote's live run is now gone locally
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "does not preserve" in err and f"missing remote entry circuit-trace fired {live}" in err
    assert _origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"] == '{"a": 1}\n'


def test_publish_inspects_every_unpublished_commit_not_only_the_final_tree(tmp_path, capsys):
    """A foreign file added in one commit and deleted in a later one is absent
    from the merge-base diff but would be pushed, and this repository is public."""
    origin, clone = _publish_fixture(tmp_path)
    (clone / "secret.txt").write_text("token\n", encoding="utf-8")
    _commit(clone, "oops")
    (clone / "secret.txt").unlink()
    _commit(clone, "remove it")
    _fire_locally(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    assert "secret.txt" in capsys.readouterr().err
    assert ".github/trigger/circuit-trace.json" in _origin_main_files(origin, tmp_path)
    assert _origin_main_files(origin, tmp_path)[".github/trigger/circuit-trace.json"] == '{"a": 1}\n'


def test_publish_reruns_the_reused_tag_guard_after_the_rebase(tmp_path, capsys):
    """The race the pre-push guard cannot close: CI commits the tag's manifest
    after the fire was cut and before its push, the push is rejected, and the
    rebased retry now carries the manifest at HEAD. `publish` must see it."""
    origin, clone = _publish_fixture(tmp_path)
    _fire_locally(clone, "archive-renders", {"tag": "renders-20260908-p9", "runs": ["trace_out/pairs_x"],
                                             "prune": "true"})
    _advance_origin(origin, tmp_path, "ci", lambda r: (
        (r / "render_archives").mkdir(),
        (r / "render_archives" / "renders-20260908-p9.manifest.json").write_text("{}", encoding="utf-8")))
    assert ft.main(["publish", "--repo", str(clone)]) == 8
    err = capsys.readouterr().err
    assert "renders-20260908-p9" in err and "already on this branch" in err
    assert ".github/trigger/archive-renders.json" not in _origin_main_files(origin, tmp_path)
    assert ft.main(["publish", "--repo", str(clone), "--reuse-tag"]) == 0          # the deliberate override
    assert ".github/trigger/archive-renders.json" in _origin_main_files(origin, tmp_path)


def test_publish_keeps_the_park_exemption_when_the_park_push_was_rejected(tmp_path, monkeypatch, capsys):
    """A park re-fires the lane's no-op tag, whose manifest is always on main. If
    its push is rejected, the retry through `publish` must still recognise it as
    a park (by content: PARK_DEFAULTS exactly, plus _parked) or the lane stays
    unparked behind an unrelated --reuse-tag demand."""
    origin, clone = _publish_fixture(tmp_path)
    monkeypatch.setattr(ft, "PUSH_BACKOFF_SECONDS", ())
    (clone / "render_archives").mkdir()
    (clone / "render_archives" / "park-noop.manifest.json").write_text("{}", encoding="utf-8")
    _commit(clone, "the park's manifest, as on main")
    subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "main"], check=True)
    _advance_origin(origin, tmp_path, "other", lambda r: (r / "README.md").write_text("moved\n", encoding="utf-8"))
    assert ft.main(["park", "--repo", str(clone), "--trigger", "archive-renders", "--ignore-settle"]) == 1
    assert "publish failed" in capsys.readouterr().err                     # rejected: origin moved
    params = json.loads((clone / ".github" / "trigger" / "archive-renders.json").read_text(encoding="utf-8"))
    assert ft.is_park_params("archive-renders", params)
    assert not ft.is_park_params("archive-renders", {**params, "tag": "renders-x"})
    assert not ft.is_park_params("archive-renders", {k: v for k, v in params.items() if k != "_parked"})
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    assert "published" in capsys.readouterr().out
    assert json.loads(_origin_main_files(origin, tmp_path)[".github/trigger/archive-renders.json"]) == params
def test_publish_refuses_when_a_later_commit_restored_the_trigger_file(tmp_path, capsys):
    """The workflow's paths filter sees the push as a whole: with the trigger file
    back to its origin content in the final tree, the push fires nothing while
    the journal entry holds a queue slot."""
    origin, clone = _publish_fixture(tmp_path)
    # a valid resting-state file at origin, as a parked lane holds
    resting = dict(PUBLISH_PARAMS, mode="4quadrant")
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(resting) + "\n", encoding="utf-8")
    _commit(clone, "park")
    subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "main"], check=True)
    _fire_locally(clone)
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(resting) + "\n", encoding="utf-8")
    _commit(clone, "undo the fire")
    head = _head(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "identical at origin/main and HEAD" in err and '"evicted": true by hand' in err
    assert _head(clone) == head
    assert "circuit-trace fire" not in _origin_main_files(origin, tmp_path)["ops/trigger_journal.jsonl"]


def test_publish_recomputes_a_paid_fires_commitment_from_the_final_params(tmp_path, capsys):
    """inflight_max_spend counts the entry's max_spend and lane for the running
    job, so they must equal what cmd_fire derives from the trigger file that is
    actually pushed - not what a hand edit during conflict recovery left."""
    origin, clone = _publish_fixture(tmp_path)
    write_dashboard(clone, spent=0.0)
    _commit(clone, "dashboard")
    subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "main"], check=True)
    params = {"task": "pairs", "num": "5", "max_spend": "1.0"}
    (clone / ".github" / "trigger" / "scenario-generation.json").write_text(json.dumps(params) + "\n",
                                                                            encoding="utf-8")
    fired = ft.iso_utc(ft.utc_now())
    _append_journal(clone / "ops" / "trigger_journal.jsonl",
                    _journal_line("scenario-generation", fired, max_spend=0.1, lane="openrouter"))
    _commit(clone, "Fire scenario-generation: local, commitment altered")
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    out = capsys.readouterr().out
    assert "max_spend 0.1 -> 1.0, lane 'openrouter' -> 'anthropic'" in out and "published 2 commit" in out
    entries = [json.loads(ln) for ln in _origin_main_files(origin, tmp_path)["ops/trigger_journal.jsonl"].splitlines()
               if ln.strip()]
    mine = [e for e in entries if e.get("fired_utc") == fired]
    assert len(mine) == 1 and mine[0]["max_spend"] == 1.0 and mine[0]["lane"] == "anthropic"
    assert "fired_utc_original" not in mine[0]                                 # fresh: no restamp
    assert ft.inflight_max_spend(entries, ft.utc_now().strftime("%Y-%m-%d"), ft.utc_now(), 8.0) == 1.0

    # the converse: a stray commitment on an unpaid fire is removed
    origin2, clone2 = _publish_fixture(tmp_path / "unpaid")
    (clone2 / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(PUBLISH_PARAMS) + "\n",
                                                                       encoding="utf-8")
    fired2 = ft.iso_utc(ft.utc_now())
    _append_journal(clone2 / "ops" / "trigger_journal.jsonl", _journal_line("circuit-trace", fired2, max_spend=5.0))
    _commit(clone2, "Fire circuit-trace: local, stray commitment")
    assert ft.main(["publish", "--repo", str(clone2)]) == 0
    assert "max_spend/lane removed: not a paid fire" in capsys.readouterr().out
    entries2 = [json.loads(ln) for ln in _origin_main_files(origin2, tmp_path / "unpaid")["ops/trigger_journal.jsonl"]
                .splitlines() if ln.strip()]
    assert all("max_spend" not in e for e in entries2 if e.get("fired_utc") == fired2)


def test_publish_restamp_threshold_follows_the_expiry_window(tmp_path, capsys, monkeypatch):
    """The queue guard expires entries older than MEDLANG_TRIGGER_EXPIRE_HOURS, so
    a fire published later than half that window (not only an hour) would land
    already expired: with a 0.5-hour window a 20-minute-old stamp is restamped."""
    monkeypatch.setenv("MEDLANG_TRIGGER_EXPIRE_HOURS", "0.5")
    origin, clone = _publish_fixture(tmp_path)
    old = ft.iso_utc(ft.utc_now() - timedelta(minutes=20))
    _fire_locally(clone, fired_utc=old)
    assert ft.main(["publish", "--repo", str(clone)]) == 0
    assert "fired_utc_original" in capsys.readouterr().out
    entries = [json.loads(ln) for ln in _origin_main_files(origin, tmp_path)["ops/trigger_journal.jsonl"].splitlines()
               if ln.strip()]
    assert [e for e in entries if e.get("fired_utc_original") == old]
    assert ft.active_entries(entries, "circuit-trace", ft.utc_now(), 0.5), "the published run must count as active"
    # the same 20-minute-old stamp keeps under the default window
    monkeypatch.delenv("MEDLANG_TRIGGER_EXPIRE_HOURS", raising=False)
    origin2, clone2 = _publish_fixture(tmp_path / "default")
    old2 = ft.iso_utc(ft.utc_now() - timedelta(minutes=20))
    _fire_locally(clone2, fired_utc=old2)
    assert ft.main(["publish", "--repo", str(clone2)]) == 0
    assert "fired_utc_original" not in capsys.readouterr().out


def test_publish_refuses_when_the_remote_journal_has_a_line_it_cannot_read(tmp_path, capsys):
    """A remote line that is not JSON is exactly what a local rewrite would
    silently drop; the preserve check names the line rather than skipping it."""
    origin, clone = _publish_fixture(tmp_path)
    _advance_origin(origin, tmp_path, "corrupter",
                    lambda r: _append_journal(r / "ops" / "trigger_journal.jsonl", "{not json\n"))
    subprocess.run(["git", "-C", str(clone), "pull", "-q", "--rebase", "origin", "main"], check=True)
    # the operator "repairs" the journal locally by dropping the bad line, then fires
    journal = clone / "ops" / "trigger_journal.jsonl"
    kept = [ln for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip() and ln != "{not json"]
    journal.write_text("\n".join(kept) + "\n" + _journal_line("circuit-trace", ft.iso_utc(ft.utc_now())),
                       encoding="utf-8")
    (clone / ".github" / "trigger" / "circuit-trace.json").write_text(json.dumps(PUBLISH_PARAMS) + "\n",
                                                                       encoding="utf-8")
    _commit(clone, "Fire circuit-trace: local")
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert "origin/main journal line 2 is not JSON" in err and "repair it by hand" in err
    assert "{not json" in _origin_main_files(origin, tmp_path)["ops/trigger_journal.jsonl"]   # untouched


def test_publish_refuses_a_hand_resolve_that_carries_no_resolved_utc(tmp_path, capsys):
    """resolved: true without a parseable resolved_utc leaves the queue and the
    settle guard at once, which cmd_resolve never does."""
    origin, clone = _publish_fixture(tmp_path)
    live = ft.iso_utc(ft.utc_now() - timedelta(minutes=5))
    _advance_origin(origin, tmp_path, "other",
                    lambda r: _append_journal(r / "ops" / "trigger_journal.jsonl", _journal_line("circuit-trace", live)))
    subprocess.run(["git", "-C", str(clone), "pull", "-q", "--rebase", "origin", "main"], check=True)
    journal = clone / "ops" / "trigger_journal.jsonl"
    entries = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for e in entries:
        if e["fired_utc"] == live:
            e["resolved"] = True                                             # no resolved_utc
    ft.save_journal(journal, entries)
    _fire_locally(clone)
    assert ft.main(["publish", "--repo", str(clone)]) == 3
    err = capsys.readouterr().err
    assert f"circuit-trace fired {live}: resolved without a parseable resolved_utc" in err
    remote = _origin_main_files(origin, tmp_path)["ops/trigger_journal.jsonl"]
    assert '"resolved": false' in remote and "circuit-trace fire" in remote     # nothing published

