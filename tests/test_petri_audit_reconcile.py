"""Journal-to-ledger reconciliation for the petri-audit lane
(scripts/petri_audit/reconcile.py): paid journal entries are joined to the
landed cost sidecars on the fire nonce, and every gap is named. 3.11-safe."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ledger_update  # noqa: E402
from scripts.petri_audit import cli, framework, reconcile  # noqa: E402


def _entry(fired: str, nonce: str | None, max_spend: float | None = None, **extra) -> dict:
    e = {"trigger": "petri-audit", "fired_utc": fired, "commit": "", "note": "t", "resolved": False, "evicted": False, "nonce": nonce}
    if max_spend is not None:
        e["max_spend"] = max_spend
        e["lane"] = "anthropic"
    e.update(extra)
    return e


def _sidecar(runs: Path, run: str, cost: float, nonce: str | None, judge_cost: float | None = None) -> None:
    """What the production writers leave in a run directory.

    Kept in step with them deliberately: every round of review has added a check
    that reads a field the writers emit, and a fixture thinner than the real
    thing turns those checks into fixture failures. `run_id`/`eval_id` come from
    the manifest for both files (judge_runner's `sidecar_extra`, `adapt --report`),
    the judge is cumulative with its component costs accounting for `cost_usd`,
    and a target that had a judge pass records the ceiling it reserved.
    """
    d = runs / run
    d.mkdir(parents=True, exist_ok=True)
    # the writers record run_utc (spend.write_report_sidecar) and the ledger books the cost to the day it names
    framework.write_json(d / f"{run}.report.json", {"run_id": run, "eval_id": f"ev_{run}", "cost_usd": cost,
                                                   "cost_basis": "engine_repriced_from_inspect_model_usage",
                                                   "billing_channel": "anthropic", "journal_nonce": nonce, "max_spend_usd": 1.0,
                                                   "judge_max_spend_usd": 0.5 if judge_cost is not None else None,
                                                   # `reprice_usage` returns the per-model rows it summed, and
                                                   # `write_report_sidecar` records both, so a repriced cost_usd
                                                   # always has rows behind it (Codex round 8 on PR #28)
                                                   "models": [{"model": "anthropic/claude-haiku-4-5",
                                                               "cost_usd": cost, "usage_missing": False,
                                                               "calls": 20, "calls_without_usage": 0}],
                                                   "run_utc": "2026-09-18T10:05:00Z"})
    if judge_cost is not None:
        framework.write_json(d / f"{run}.judge.report.json", {"judge_model": "claude-haiku-4-5", "cost_usd": judge_cost,
                                                             "run_cost_usd": judge_cost, "prior_cost_usd": 0.0,
                                                             "run_id": run, "eval_id": f"ev_{run}",
                                                             "max_spend_usd": 0.5,
                                                             "cost_basis": "cumulative_from_records", "billing_channel": "anthropic",
                                                             "run_utc": "2026-09-18T10:07:00Z"})


def _layout(tmp_path: Path):
    journal = tmp_path / "trigger_journal.jsonl"
    runs = tmp_path / "runs"
    runs.mkdir()
    dashboard = tmp_path / "dashboard.json"
    return journal, runs, dashboard


def test_paid_fires_are_joined_to_their_sidecars_on_the_nonce(tmp_path):
    journal, runs, dashboard = _layout(tmp_path)
    entries = [
        _entry("2026-09-18T10:00:00Z", "n1", 1.5, resolved=True),          # landed: target 0.4 + judge 0.3
        _entry("2026-09-18T11:00:00Z", "n2", 0.8),                          # fired, nothing landed
        _entry("2026-09-18T12:00:00Z", "n3", 0.5, evicted=True),           # evicted before it ran
        _entry("2026-09-18T13:00:00Z", "park-1"),                           # a park or dry run: not paid, ignored
        {"trigger": "advice-eval", "fired_utc": "2026-09-18T14:00:00Z", "commit": "", "note": "x", "resolved": False,
         "evicted": False, "max_spend": 0.6, "nonce": "other-lane"},        # another lane, ignored
    ]
    journal.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.3)
    _sidecar(runs, "run_9", 0.2, "n9")                                       # a sidecar no fire accounts for
    _sidecar(runs, "run_0", 0.1, None)                                       # a sidecar without a nonce
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"],
                                               "entries_folded": {"run_1.report.json": 0.4}}})
    result = reconcile.reconcile(journal, runs, dashboard)
    rows = {r["nonce"]: r for r in result["paid_fires"]}
    assert set(rows) == {"n1", "n2", "n3"}
    assert rows["n1"]["status"] == "landed" and rows["n1"]["run"] == "run_1"
    assert (rows["n1"]["cost_usd"], rows["n1"]["judge_cost_usd"], rows["n1"]["total_usd"]) == (0.4, 0.3, 0.7)
    assert rows["n1"]["folded"] is True and rows["n1"]["judge_folded"] is False, "the judge sidecar is not folded yet"
    assert rows["n2"]["status"] == "no sidecar landed" and rows["n3"]["status"] == "evicted before it ran"
    assert result["sidecars"] == {"target": 3, "judge": 1}
    assert result["unfolded_sidecars"] == ["run_0.report.json", "run_1.judge.report.json", "run_9.report.json"]
    problems = "\n".join(result["problems"])
    assert "paid fire 2026-09-18T11:00:00Z (nonce 'n2'): no cost sidecar carries its nonce" in problems
    assert "run_9/run_9.report.json: journal_nonce 'n9' matches no paid petri-audit journal entry" in problems
    assert "run_0/run_0.report.json: sidecar carries no journal_nonce" in problems
    assert "n3" not in problems, "an evicted fire never ran; nothing to book"
    text = reconcile.render_markdown(result)
    assert "| 2026-09-18T10:00:00Z | n1 | 1.5000 | run_1 | 0.4000 | 0.3000 | 0.7000 | engine_repriced_from_inspect_model_usage | no | landed |" in text
    assert "**Problems (6)**" in text and "Not yet folded into the ledger" in text
    # every unfolded sidecar is a problem in its own right, joined to a fire or not, so --strict cannot pass
    # while one is listed and the list can never hold a gap nothing names
    for name in result["unfolded_sidecars"]:
        assert f"/{name}: the ledger has not folded it yet" in problems, name


def test_a_landed_cost_above_the_commitment_and_a_bad_sidecar_are_named(tmp_path):
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 0.5)) + "\n"
                       + json.dumps(_entry("2026-09-18T11:00:00Z", None, 0.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.45, "n1", judge_cost=0.2)                     # 0.65 > 0.5
    (runs / "run_2").mkdir()
    (runs / "run_2" / "run_2.report.json").write_text("{not json", encoding="utf-8")
    result = reconcile.reconcile(journal, runs)                              # no dashboard: folded is unknown, never False
    rows = {r["nonce"]: r for r in result["paid_fires"]}
    assert rows["n1"]["total_usd"] == 0.65 and rows["n1"]["folded"] is None
    problems = "\n".join(result["problems"])
    assert "run_1: landed cost 0.6500 exceeds the fire's commitment 0.5000" in problems
    assert "run_2/run_2.report.json: sidecar unreadable" in problems
    assert "paid fire 2026-09-18T11:00:00Z: the journal entry records no nonce" in problems
    assert rows[None]["status"] == "no nonce recorded"
    # a sidecar whose cost is not a number is a named gap, never a zero
    (runs / "run_1" / "run_1.report.json").write_text(json.dumps({"cost_usd": "0.45", "journal_nonce": "n1"}), encoding="utf-8")
    result = reconcile.reconcile(journal, runs)
    assert "run_1/run_1.report.json: cost_usd '0.45' is missing or not a finite non-negative number" \
        in "\n".join(result["problems"])
    assert {r["nonce"]: r for r in result["paid_fires"]}["n1"]["total_usd"] is None


def test_a_journal_line_that_does_not_parse_is_an_error_not_a_skipped_fire(tmp_path):
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 0.5)) + "\n{oops\n", encoding="utf-8")
    try:
        reconcile.reconcile(journal, runs)
    except ValueError as exc:
        assert "line 2 does not parse" in str(exc)
    else:
        raise AssertionError("a corrupt journal line must not be skipped")


def test_a_judge_sidecar_without_its_target_sidecar_is_named(tmp_path):
    # the judge sidecar joins the journal through its run directory's target sidecar, so one standing alone is
    # folded by the ledger and accounted for by nothing; the workflow's fallback spend-report writes a target
    # sidecar for every attempted run, so this state means that step did not run either
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, resolved=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.3)
    (runs / "run_2").mkdir()
    framework.write_json(runs / "run_2" / "run_2.judge.report.json",
                         {"judge_model": "claude-haiku-4-5", "cost_usd": 0.12, "billing_channel": "anthropic"})
    result = reconcile.reconcile(journal, runs)
    problems = "\n".join(result["problems"])
    assert "run_2/run_2.judge.report.json: judge sidecar with no target sidecar in its run directory" in problems
    assert "run_1/run_1.judge.report.json" not in problems, "a judge sidecar beside its target is accounted for"
    assert result["sidecars"] == {"target": 1, "judge": 2}
    # an unreadable judge sidecar beside a matched target is named as unreadable, not as a missing number
    (runs / "run_1" / "run_1.judge.report.json").write_text("{not json", encoding="utf-8")
    result = reconcile.reconcile(journal, runs)
    assert "run_1/run_1.judge.report.json: judge sidecar unreadable" in "\n".join(result["problems"])
    row = result["paid_fires"][0]
    assert row["judge_cost_usd"] is None and row["total_usd"] is None, "a cost that cannot be read is never a zero"


def test_a_dashboard_that_cannot_be_read_is_a_named_problem_not_an_empty_fold_set(tmp_path):
    # folded=set() would report every landed sidecar as unbooked, which reads exactly like real underbooking
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, resolved=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1")
    for content, expected in [("{not json", "unreadable"),
                              ("[]", "no spend block"),
                              (json.dumps({"spend": {}}), "spend.entries_seen is missing or not a list"),
                              (json.dumps({"spend": {"entries_seen": "run_1.report.json"}}),
                               "spend.entries_seen is missing or not a list")]:
        dashboard.write_text(content, encoding="utf-8")
        result = reconcile.reconcile(journal, runs, dashboard)
        assert expected in "\n".join(result["problems"]), content
        assert result["paid_fires"][0]["folded"] is None, "unknown, never False"
        assert result["unfolded_sidecars"] == [], "nothing may be reported unfolded on an unreadable ledger"


def test_money_that_is_not_money_is_named_rather_than_counted(tmp_path):
    # json.loads accepts NaN and Infinity, and every comparison with NaN is False, so a NaN total sailed past
    # the over-commitment check; a negative cost lowered the total instead of being named (Codex round 1, PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 0.5)) + "\n"
                       + json.dumps(_entry("2026-09-18T11:00:00Z", "n2", float("nan"))) + "\n", encoding="utf-8")
    d = runs / "run_1"
    d.mkdir()
    (d / "run_1.report.json").write_text('{"cost_usd": NaN, "journal_nonce": "n1"}', encoding="utf-8")
    result = reconcile.reconcile(journal, runs)
    rows = {r["nonce"]: r for r in result["paid_fires"]}
    problems = "\n".join(result["problems"])
    assert rows["n1"]["cost_usd"] is None and rows["n1"]["total_usd"] is None
    assert "run_1/run_1.report.json: cost_usd nan is missing or not a finite non-negative number" in problems
    assert "paid fire 2026-09-18T11:00:00Z: max_spend nan is not a finite non-negative number" in problems
    assert rows["n2"]["max_spend"] is None
    # a negative cost is not a discount
    (d / "run_1.report.json").write_text(json.dumps({"cost_usd": -0.4, "journal_nonce": "n1"}), encoding="utf-8")
    framework.write_json(d / "run_1.judge.report.json", {"cost_usd": 0.9, "cost_basis": "cumulative_from_records"})
    result = reconcile.reconcile(journal, runs)
    rows = {r["nonce"]: r for r in result["paid_fires"]}
    assert rows["n1"]["cost_usd"] is None and rows["n1"]["total_usd"] is None, "0.9 - 0.4 must not read as under the ceiling"
    assert "cost_usd -0.4 is missing or not a finite non-negative number" in "\n".join(result["problems"])


def test_two_judge_sidecars_in_one_run_directory_are_refused_not_silently_reduced(tmp_path):
    # the comprehension used to keep whichever sorted last, dropping the other's cost from the reconciliation
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.2)
    framework.write_json(runs / "run_1" / "second.judge.report.json",
                         {"judge_model": "claude-haiku-4-5", "cost_usd": 0.3, "billing_channel": "anthropic"})
    result = reconcile.reconcile(journal, runs)
    row = result["paid_fires"][0]
    problems = "\n".join(result["problems"])
    assert "run_1: 2 judge sidecars (run_1.judge.report.json, second.judge.report.json)" in problems
    assert row["judge_cost_usd"] is None, "neither cost may be silently chosen"
    assert row["total_usd"] == 0.4, "the target cost still stands on its own"


def test_a_dashboard_path_that_does_not_exist_is_named(tmp_path):
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.3, "n1")
    missing = tmp_path / "typo.json"
    result = reconcile.reconcile(journal, runs, missing)
    assert f"{missing}: no such file" in "\n".join(result["problems"]), "strict must not pass having checked half"
    assert reconcile.reconcile(journal, runs)["problems"] == [], "no dashboard asked for is not a problem"
    assert not dashboard.exists()


def test_a_cumulative_sidecar_that_grew_since_its_fold_is_not_counted_as_booked(tmp_path):
    # ledger_update keeps two records: entries_seen (ever folded) and entries_folded (HOW MUCH is booked). A
    # judge sidecar is cumulative, so a resumed pass grows a file whose name is already in entries_seen; the
    # name alone said booked while the delta had not reached the dashboard (Codex round 2 on PR #28).
    journal, runs, dashboard = _layout(tmp_path)
    # the commitment is what fire_commitment computes for a judged fire: max_spend + judge_max_spend, which is
    # what the fixture's two sidecars declare (1.0 + 0.5), so the round-4 ceilings check stays silent here
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5, resolved=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.40, "n1", judge_cost=0.30)
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json", "run_1.judge.report.json"],
                                               "entries_folded": {"run_1.report.json": 0.40,
                                                                  "run_1.judge.report.json": 0.18}}})
    result = reconcile.reconcile(journal, runs, dashboard)
    row = result["paid_fires"][0]
    problems = "\n".join(result["problems"])
    assert row["folded"] is True, "the target sidecar is fully booked"
    assert row["judge_folded"] is False, "0.18 of 0.30 is not booked"
    assert "run_1/run_1.judge.report.json: the ledger has booked 0.1800 of its 0.3000, so 0.1200 of landed " \
           "spend is not in the daily totals" in problems
    assert result["unfolded_sidecars"] == ["run_1.judge.report.json"]
    # a residual below the ledger's four-decimal booking resolution waits legitimately and is not a gap
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json", "run_1.judge.report.json"],
                                               "entries_folded": {"run_1.report.json": 0.40,
                                                                  "run_1.judge.report.json": 0.29999}}})
    clean = reconcile.reconcile(journal, runs, dashboard)
    assert clean["problems"] == [] and clean["unfolded_sidecars"] == []
    # `ledger_update` writes the name and the amount in the same fold, and this lane postdates that watermark,
    # so a name in entries_seen with no amount is a truncated or edited dashboard, not a legacy record
    # (Codex round 5 on PR #28)
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json", "run_1.judge.report.json"]}})
    result = reconcile.reconcile(journal, runs, dashboard)
    problems = "\n".join(result["problems"])
    assert "run_1/run_1.report.json: the ledger lists it as folded but records no amount for it in " \
           "spend.entries_folded" in problems
    assert result["paid_fires"][0]["folded"] is False and result["paid_fires"][0]["judge_folded"] is False


def test_two_journal_entries_sharing_a_nonce_are_refused_not_both_landed(tmp_path):
    # each iteration matched the one sidecar independently, so both fires read "landed" and one cost was booked
    # against two commitments; fire_trigger refuses a repeat at the fire, this refuses it in the record
    journal, runs, _ = _layout(tmp_path)
    journal.write_text("".join(json.dumps(e) + "\n" for e in [
        _entry("2026-09-18T10:00:00Z", "dup", 1.0, resolved=True),
        _entry("2026-09-18T11:00:00Z", "dup", 1.0),
        _entry("2026-09-18T12:00:00Z", "solo", 1.0)]), encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "dup")
    _sidecar(runs, "run_2", 0.2, "solo")
    result = reconcile.reconcile(journal, runs)
    statuses = [r["status"] for r in result["paid_fires"]]
    assert statuses == ["duplicate nonce", "duplicate nonce", "landed"]
    assert all(r["total_usd"] is None for r in result["paid_fires"] if r["nonce"] == "dup")
    problems = "\n".join(result["problems"])
    assert "nonce 'dup' is on 2 paid petri-audit journal entries (2026-09-18T10:00:00Z, 2026-09-18T11:00:00Z)" in problems
    assert problems.count("nonce 'dup' is on") == 1, "named once, not once per row"


def test_a_sidecar_that_books_another_account_than_the_fire_reserved_is_named(tmp_path):
    # the ledger books by the sidecar's billing_channel while the ceiling reserved the journal's lane, so a
    # mismatch moves spend between the $2 Anthropic and $10 OpenRouter ceilings unseen
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.2)
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "billing_channel": "openrouter"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.report.json: the sidecar books the openrouter account but the fire reserved its " \
           "commitment on anthropic" in problems
    # a sidecar that states no channel at all cannot be checked, and says so
    framework.write_json(path, {k: v for k, v in framework.load_json(path).items() if k != "billing_channel"})
    assert "run_1/run_1.report.json: the sidecar states no billing_channel" in \
        "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_flag_that_is_not_a_boolean_cannot_excuse_a_fire(tmp_path):
    # bool("false") is True, which classified a paid fire with no sidecar as evicted and dropped it from every check
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, evicted="false")) + "\n", encoding="utf-8")
    result = reconcile.reconcile(journal, runs)
    row = result["paid_fires"][0]
    problems = "\n".join(result["problems"])
    assert row["evicted"] is False and row["status"] == "no sidecar landed"
    assert "evicted is 'false', not true or false; read as false" in problems
    assert "no cost sidecar carries its nonce" in problems


def test_a_runs_directory_that_does_not_exist_is_named(tmp_path, monkeypatch):
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, evicted=True)) + "\n", encoding="utf-8")
    missing = tmp_path / "no_such_runs"
    # a path the caller named that is not there: a mistyped --runs, scanned nothing, said nothing
    result = reconcile.reconcile(journal, missing)
    assert f"{missing}: no such directory, so no landed sidecar was scanned at all" in "\n".join(result["problems"])
    assert reconcile.reconcile(journal, runs)["problems"] == [], "an existing but empty archive is not a problem"
    # ...but the DEFAULT archive before the lane's first landed run is the normal state, not a defect: nothing
    # has created it and no paid fire is waiting on it. It is stated in the report and left out of problems,
    # so `--strict` does not fail a lane that has simply never run (found by running the CLI on this repo).
    monkeypatch.setattr(reconcile, "DEFAULT_RUNS_DIR", missing)
    empty_journal = tmp_path / "empty.jsonl"
    empty_journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "park-1")) + "\n", encoding="utf-8")
    quiet = reconcile.reconcile(empty_journal, missing)
    assert quiet["problems"] == []
    assert quiet["runs_dir_note"] == f"{missing}: no such directory (no run has landed here)"
    assert quiet["runs_dir_note"] in reconcile.render_markdown(quiet), "the absence is stated, never hidden"
    # one paid fire is waiting on it, so the same absent default IS a problem
    assert f"{missing}: no such directory, so no landed sidecar was scanned at all" in \
        "\n".join(reconcile.reconcile(journal, missing)["problems"])


def test_a_sidecar_that_shrank_below_the_ledger_watermark_is_named(tmp_path):
    # growth-only comparison read a truncated or rewritten sidecar as fully booked, hiding exactly the archive
    # alteration this command exists to surface (Codex round 3 on PR #28)
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 2.0, resolved=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.50, "n1")
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"],
                                               "entries_folded": {"run_1.report.json": 1.00}}})
    result = reconcile.reconcile(journal, runs, dashboard)
    assert result["paid_fires"][0]["folded"] is False
    assert "run_1/run_1.report.json: the ledger has booked 1.0000 but the sidecar now records 0.5000: a landed " \
           "cost record cannot shrink" in "\n".join(result["problems"])


def test_a_paid_entry_whose_commitment_is_missing_is_still_reconciled(tmp_path):
    # filtering on `max_spend is not None` dropped an entry carrying the paid-only `lane` with a null
    # commitment, so a paid fire with no sidecar went unmentioned entirely (Codex round 3 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    broken = {"trigger": "petri-audit", "fired_utc": "2026-09-18T10:00:00Z", "commit": "", "note": "t",
              "resolved": False, "evicted": False, "nonce": "n1", "lane": "anthropic", "max_spend": None}
    journal.write_text(json.dumps(broken) + "\n"
                       + json.dumps(_entry("2026-09-18T11:00:00Z", "park-1")) + "\n", encoding="utf-8")
    result = reconcile.reconcile(journal, runs)
    assert [r["nonce"] for r in result["paid_fires"]] == ["n1"], "the park is still not a paid fire"
    problems = "\n".join(result["problems"])
    assert "paid fire 2026-09-18T10:00:00Z: max_spend None is not a finite non-negative number" in problems
    assert "no cost sidecar carries its nonce" in problems


def test_two_target_sidecars_in_one_run_directory_join_nothing(tmp_path):
    # each nonce matched one sidecar cleanly, so both fires read "landed" while the directory's single judge
    # sidecar was attached to both rows and its cost counted twice (Codex round 3 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n"
                       + json.dumps(_entry("2026-09-18T11:00:00Z", "n2", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.3)
    framework.write_json(runs / "run_1" / "second.report.json",
                         {"run_id": "run_1", "cost_usd": 0.2, "billing_channel": "anthropic", "journal_nonce": "n2"})
    result = reconcile.reconcile(journal, runs)
    problems = "\n".join(result["problems"])
    assert "run_1: 2 target sidecars (run_1.report.json, second.report.json); one run directory is one run" in problems
    assert [r["status"] for r in result["paid_fires"]] == ["no sidecar landed", "no sidecar landed"]
    assert all(r["total_usd"] is None for r in result["paid_fires"]), "one judge cost may not be booked twice"


def test_a_fire_journaled_evicted_that_landed_a_sidecar_is_a_contradiction(tmp_path):
    # eviction released the in-flight commitment, so a replacement fire was admitted without counting this one;
    # a sidecar proves the run went ahead anyway (Codex round 4 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, evicted=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1")
    result = reconcile.reconcile(journal, runs)
    assert result["paid_fires"][0]["status"] == "landed", "the cost is still attributed"
    assert "is journaled evicted but landed run_1" in "\n".join(result["problems"])


def test_a_requested_judge_pass_with_no_sidecar_is_not_read_as_zero(tmp_path):
    # the target sidecar records the judge ceiling the run reserved; no judge sidecar beside it hides up to that
    # amount rather than proving it was zero (Codex round 4 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1")                       # no judge sidecar
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": 0.5})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: the run reserved 0.5000 for a judge pass and no judge sidecar landed beside it" in problems
    # a run that reserved nothing for a judge is not missing one
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": None})
    assert "reserved" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])
    # nor is a run that never produced an adapted report: `spend_report_reason` is written only by the workflow's
    # fallback spend-report step, which runs when no adapted report exists - and the judge step is gated on adapt
    # succeeding, so it never started and wrote nothing. The artifacts prove the zero (self-review, 2026-09-18).
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": 0.5,
                                "spend_report_reason": "run attempted; no adapted report exists"})
    assert "no judge sidecar landed beside it" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])
    # an empty or non-string reason is not that marker, so the check still applies
    for not_a_reason in ("", None, 0):
        framework.write_json(path, {**framework.load_json(path), "spend_report_reason": not_a_reason})
        assert "no judge sidecar landed beside it" in "\n".join(reconcile.reconcile(journal, runs)["problems"]), \
            not_a_reason


def test_ceilings_the_run_carried_are_checked_against_what_the_fire_reserved(tmp_path):
    # the daily guard counted the journal's commitment; ceilings on the sidecar summing higher mean CI ran with
    # more headroom than was reserved, and a low actual cost hides it (Codex round 4 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.05, "n1")                      # a small actual cost
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": 1.0, "judge_max_spend_usd": 0.5})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: the run carried ceilings summing to 1.5000 but the fire reserved 1.0000" in problems
    # ceilings that match the commitment are silent
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": 0.5, "judge_max_spend_usd": 0.5})
    assert "authorised" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_sidecar_whose_run_timestamp_does_not_parse_is_named(tmp_path):
    # ledger_update books to the day the stamp names and falls back to the scan date when it cannot parse one,
    # which puts the spend in the wrong daily bucket (Codex round 4 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.2)
    path = runs / "run_1" / "run_1.report.json"
    # a padded stamp is in this list because `datetime.fromisoformat` rejects surrounding whitespace, so
    # `ledger_update.parse_ts` falls back to the scan date on it: stripping here before parsing would have
    # passed the very stamp the ledger mis-books (found in self-review, 2026-09-18)
    for bad in ("", "  ", "yesterday", None, " 2026-09-18T10:00:00Z", "2026-09-18T10:00:00Z\n"):
        framework.write_json(path, {**framework.load_json(path), "run_utc": bad})
        assert f"run_1/run_1.report.json: the stamp `run_timestamp or run_utc` resolves to {bad!r}" in \
            "\n".join(reconcile.reconcile(journal, runs)["problems"]), bad
        assert ledger_update.parse_ts(bad) is None, f"the ledger must agree that {bad!r} does not parse"
    # the judge sidecar is checked too, and the writers' own format parses
    framework.write_json(path, {**framework.load_json(path), "run_utc": "2026-09-18T10:05:00Z"})
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(jpath, {**framework.load_json(jpath), "run_utc": "not a time"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.judge.report.json: the stamp `run_timestamp or run_utc` resolves to 'not a time'" in problems
    assert "run_1/run_1.report.json: the stamp" not in problems
    # run_timestamp is the older field name and satisfies the same check
    framework.write_json(jpath, {k: v for k, v in framework.load_json(jpath).items() if k != "run_utc"}
                         | {"run_timestamp": "2026-09-18T10:07:00+00:00"})
    assert "the stamp" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_both_of_the_ledgers_stamp_precedences_must_parse(tmp_path):
    """`ledger_update` reads the stamp in two orders: its first-fold loop takes
    `run_timestamp or run_utc` (scripts/ledger_update.py:385) and its growth loop
    `run_utc or run_timestamp` (:442). With both fields present and one malformed,
    the two paths disagree and whichever hits the bad value books the cost to the
    scan date, so checking only one order passed the mis-booking (Codex round 7)."""
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1")
    path = runs / "run_1" / "run_1.report.json"
    good = "2026-09-18T10:05:00Z"

    # a valid run_utc beside a malformed run_timestamp: the growth loop is happy, the first fold is not
    framework.write_json(path, {**framework.load_json(path), "run_utc": good, "run_timestamp": "not a time"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "the stamp `run_timestamp or run_utc` resolves to 'not a time'" in problems
    assert ledger_update.parse_ts("not a time") is None
    # ...and the other way round, which the growth loop is the one to mis-book
    framework.write_json(path, {**framework.load_json(path), "run_utc": "also not a time", "run_timestamp": good})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "the stamp `run_utc or run_timestamp` resolves to 'also not a time'" in problems
    # both valid, in either field order: silent
    framework.write_json(path, {**framework.load_json(path), "run_utc": good, "run_timestamp": good})
    assert "the stamp" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_landed_and_booked_fire_that_was_never_resolved_is_named(tmp_path):
    # until `resolve` runs, entry_is_active keeps counting the whole commitment as in-flight ON TOP of the
    # landed cost and the entry holds a queue slot until it expires (Codex round 5 on PR #28)
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1")
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"],
                                               "entries_folded": {"run_1.report.json": 0.4}}})
    problems = "\n".join(reconcile.reconcile(journal, runs, dashboard)["problems"])
    assert "landed and is fully booked but the journal entry is still unresolved" in problems
    assert "fire_trigger.py resolve --trigger petri-audit" in problems
    # resolved: silent. And before the fold it is the ordinary gap between landing and resolving, not a problem.
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, resolved=True)) + "\n", encoding="utf-8")
    assert reconcile.reconcile(journal, runs, dashboard)["problems"] == []
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    framework.write_json(dashboard, {"spend": {"entries_seen": [], "entries_folded": {}}})
    assert "still unresolved" not in "\n".join(reconcile.reconcile(journal, runs, dashboard)["problems"])


def test_a_ceiling_that_is_present_but_unusable_is_named_not_skipped(tmp_path):
    # _money returning None had the comprehension drop the value, so the authorisation check silently could not
    # verify and a malformed judge ceiling also suppressed the required-judge-sidecar check (Codex round 5)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.2, "n1")
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": -0.5})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.report.json: judge_max_spend_usd -0.5 is not a finite non-negative number" in problems
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": "1.0", "judge_max_spend_usd": None})
    assert "run_1/run_1.report.json: max_spend_usd '1.0' is not a finite non-negative number" in \
        "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_the_judge_report_s_own_ceiling_is_what_the_run_actually_carried(tmp_path):
    # the target report declares what was requested; the judge report records what the judge loop ran under,
    # and the two can differ (Codex round 5 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.05, "n1", judge_cost=0.02)
    path = runs / "run_1" / "run_1.report.json"
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": 0.5, "judge_max_spend_usd": 0.5})
    framework.write_json(jpath, {**framework.load_json(jpath), "max_spend_usd": 2.0})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: the judge ran under a ceiling of 2.0000 but the run declared 0.5000" in problems
    # and the ACTUAL ceiling is what the authorisation sum uses: 0.5 + 2.0 against a 1.0 commitment
    assert "run_1: the run carried ceilings summing to 2.5000 but the fire reserved 1.0000" in problems
    # agreeing records within the commitment are silent
    framework.write_json(jpath, {**framework.load_json(jpath), "max_spend_usd": 0.5})
    assert "ceiling" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_cli_reconcile_spend_renders_writes_json_and_is_strict_on_request(tmp_path, capsys):
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, resolved=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.3, "n1")
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"],
                                               "entries_folded": {"run_1.report.json": 0.3}}})
    out = tmp_path / "reconcile.json"
    args = ["reconcile-spend", "--journal", str(journal), "--runs", str(runs), "--dashboard", str(dashboard), "--json-out", str(out)]
    assert cli.main(args + ["--strict"]) == 0
    printed = capsys.readouterr().out
    assert "No problems" in printed and "| run_1 | 0.3000 | — | 0.3000 |" in printed
    assert framework.load_json(out)["problems"] == []
    _sidecar(runs, "run_7", 0.1, "n7")
    assert cli.main(args) == 0, "without --strict a problem is reported, never a failure"
    assert cli.main(args + ["--strict"]) == 1
    assert "matches no paid petri-audit journal entry" in capsys.readouterr().out


# ---------------------------------------------------------------- Codex round 6 on PR #28

def test_a_judge_sidecar_beside_a_run_that_reserved_no_judge_is_named(tmp_path):
    # the mirror of round 4's missing-judge check: with judge=false the workflow never runs the judge step, never
    # touches its marker and never writes a judge sidecar, so one that exists is stray or drifted paid spend, and
    # its ceiling was being read out of its own file into the authorisation sum
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.2, "n1", judge_cost=0.1)
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": None})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: a judge sidecar landed but the run reserved nothing for a judge pass" in problems
    # a run that did reserve one is silent, and so is a run with no judge sidecar at all
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": 0.5})
    assert "reserved nothing" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_each_cost_is_checked_against_its_own_ceiling_not_only_the_commitment(tmp_path):
    # a target that overspends its own max_spend_usd while the judge underspends stays under the journal's total,
    # so the aggregate check passed though CI let one side spend past what it was authorised
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.60, "n1", judge_cost=0.10)
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": 0.5})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.report.json: target cost 0.6000 exceeds the ceiling 0.5000" in problems
    assert "landed cost" not in problems, "the pair is still inside the commitment; only the component is over"
    # and the judge side, against the ceiling its own report records
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": 1.0})
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(jpath, {**framework.load_json(jpath), "cost_usd": 0.60, "run_cost_usd": 0.60})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: judge cost 0.6000 exceeds the judge ceiling 0.5000" in problems
    # a sidecar booked exactly at its ceiling (the imputed writers do this) is not over it
    framework.write_json(jpath, {**framework.load_json(jpath), "cost_usd": 0.50, "run_cost_usd": 0.50})
    assert "exceeds the judge ceiling" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_sidecar_basename_repeated_across_run_directories_is_named(tmp_path):
    # `ledger_update.sidecar_key` keys a Petri sidecar on its bare filename, so two directories holding the same
    # name are one entry to the ledger: it folds the first, the second never reaches the daily totals, and a
    # watermark covering the first covered the second too
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text("".join(json.dumps(e) + "\n" for e in [
        _entry("2026-09-18T10:00:00Z", "n1", 1.0), _entry("2026-09-18T11:00:00Z", "n2", 1.0)]), encoding="utf-8")
    _sidecar(runs, "run_1", 0.3, "n1")
    (runs / "run_2").mkdir()
    # the same basename under a second directory: a copied or renamed file, which the writers never produce
    (runs / "run_2" / "run_1.report.json").write_text(
        (runs / "run_1" / "run_1.report.json").read_text(encoding="utf-8").replace('"n1"', '"n2"'), encoding="utf-8")
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"],
                                               "entries_folded": {"run_1.report.json": 0.3}}})
    result = reconcile.reconcile(journal, runs, dashboard)
    problems = "\n".join(result["problems"])
    assert "run_1.report.json: the same sidecar basename is in 2 run directories (run_1, run_2)" in problems
    assert "the ledger keys Petri sidecars by bare filename" in problems
    # neither fire may read as booked on a name the ledger cannot tell apart
    assert all(row["folded"] is None for row in result["paid_fires"]), result["paid_fires"]


def test_a_billing_channel_outside_the_two_accounts_is_named(tmp_path):
    # ledger_update.billing_channel honours an explicit field only for anthropic and openrouter and books
    # everything else to Anthropic, so a sidecar and a journal entry agreeing on "stripe" agree about nothing
    journal, runs, _ = _layout(tmp_path)
    entry = _entry("2026-09-18T10:00:00Z", "n1", 1.0)
    entry["lane"] = "stripe"
    journal.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.3, "n1")
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "billing_channel": "stripe"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "lane 'stripe' is not an account this study bills" in problems
    assert "run_1/run_1.report.json: the sidecar books billing_channel 'stripe'" in problems
    assert "the two ceilings disagree about this spend" not in problems, "equality is not the finding here"
    # the two real accounts stay silent
    entry["lane"] = "openrouter"
    journal.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    framework.write_json(path, {**framework.load_json(path), "billing_channel": "openrouter"})
    assert "is not an account" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_judge_sidecar_from_another_run_is_named(tmp_path):
    # sharing a directory is not identity: a copied or renamed judge report joins on the directory alone and its
    # cost and judgments are attributed to this fire
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.2, "n1", judge_cost=0.1)
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(jpath, {**framework.load_json(jpath), "eval_id": "ev_run_9"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: the judge sidecar records eval_id 'ev_run_9' and the target sidecar 'ev_run_1'" in problems
    # the fallback writer records no eval_id and the run DIRECTORY as run_id, which is not a mismatch
    fallback = {k: v for k, v in framework.load_json(jpath).items() if k != "eval_id"}
    framework.write_json(jpath, {**fallback, "run_id": "run_1",
                                 "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar"})
    assert "belongs to another run" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])
    # ...but a fallback sidecar naming a different directory is
    framework.write_json(jpath, {**fallback, "run_id": "run_9",
                                 "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar"})
    assert "this judge report was written for another run" in \
        "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_cost_basis_the_writers_do_not_emit_is_named(tmp_path):
    # the basis is read by the ledger: on a first fold a cumulative sidecar books run_cost_usd to the run's day
    # and the whole cost_usd to the watermark, so a target claiming it leaves the day understated while the
    # watermark check reads the file as fully booked
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.4, "n1", judge_cost=0.1)
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "cost_basis": "cumulative_from_records",
                                "run_cost_usd": 0.0, "prior_cost_usd": 0.4})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.report.json: cost_basis 'cumulative_from_records' is not one this lane's target writer " \
           "emits" in problems
    # and a judge whose components do not account for its cost
    framework.write_json(path, {**framework.load_json(path),
                                "cost_basis": "engine_repriced_from_inspect_model_usage"})
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(jpath, {**framework.load_json(jpath), "run_cost_usd": 0.0, "prior_cost_usd": 0.0})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.judge.report.json: cost_basis is cumulative_from_records with run_cost_usd 0.00000000" in \
        problems
    assert "the day's figure does not follow from this record" in problems
    # the writers' own shapes are silent
    framework.write_json(jpath, {**framework.load_json(jpath), "run_cost_usd": 0.1, "prior_cost_usd": 0.0})
    assert "cost_basis" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


# ---------------------------------------------------------------- Codex round 7 on PR #28

def test_an_absent_ceiling_is_not_an_optional_one(tmp_path):
    # round 5 named a ceiling that was present and unusable; an ABSENT key slipped through the `is not None`
    # guard and read as nothing to check, so a low-cost sidecar passed --strict with its authorisation
    # unverifiable. Both writers always emit max_spend_usd (Codex round 7 on PR #28).
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.05, "n1", judge_cost=0.02)
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {k: v for k, v in framework.load_json(path).items() if k != "max_spend_usd"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.report.json: max_spend_usd is absent; the target writer always records it" in problems
    # the judge sidecar is held to the same rule, by the same reasoning about its two writers
    framework.write_json(path, {**framework.load_json(path), "max_spend_usd": 1.0})
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(jpath, {k: v for k, v in framework.load_json(jpath).items() if k != "max_spend_usd"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.judge.report.json: max_spend_usd is absent; both judge writers record it" in problems
    # present and usable: silent
    framework.write_json(jpath, {**framework.load_json(jpath), "max_spend_usd": 0.5})
    assert "max_spend_usd is absent" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_judge_sidecar_carrying_no_identity_at_all_is_named(tmp_path):
    # the fallback branch rejected only a PRESENT run_id naming another directory, so a truncated or copied
    # report with neither eval_id nor run_id was attributed to this run (Codex round 7 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.2, "n1", judge_cost=0.1)
    jpath = runs / "run_1" / "run_1.judge.report.json"
    stripped = {k: v for k, v in framework.load_json(jpath).items() if k not in ("eval_id", "run_id")}
    framework.write_json(jpath, {**stripped, "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: the judge sidecar records neither eval_id nor run_id" in problems
    # the fallback writer's real shape - run_id naming its own directory, no eval_id - stays silent
    framework.write_json(jpath, {**stripped, "run_id": "run_1",
                                 "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar"})
    assert "neither eval_id nor run_id" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_target_sidecar_with_no_identity_cannot_vouch_for_its_judge(tmp_path):
    # every comparison in _judge_identity_problem is conditional on the TARGET's field being present, so a target
    # carrying neither left a copied judge report - with any identity it likes - joined on the directory alone
    # (Codex round 8 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.5)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.2, "n1", judge_cost=0.1)
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {k: v for k, v in framework.load_json(path).items()
                                if k not in ("eval_id", "run_id")})
    jpath = runs / "run_1" / "run_1.judge.report.json"
    framework.write_json(jpath, {**framework.load_json(jpath), "eval_id": "ev_somewhere_else",
                                 "run_id": "run_somewhere_else"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1: the target sidecar records neither eval_id nor run_id" in problems
    # one identity field is enough to compare against
    framework.write_json(path, {**framework.load_json(path), "run_id": "run_1"})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "the target sidecar records neither" not in problems
    assert "belongs to another run" in problems, "and the copied judge is then caught"


def test_a_judge_ceiling_of_zero_is_not_the_absence_of_one(tmp_path):
    # _money accepts 0 and the truthiness test read it as "no judge requested", so an edited sidecar could erase
    # the evidence that a judge pass and its spend are missing (Codex round 8 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.2, "n1")                        # no judge sidecar
    path = runs / "run_1" / "run_1.report.json"
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": 0})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "run_1/run_1.report.json: judge_max_spend_usd is 0, which no fire produces" in problems
    # null is what the writer records when judging is off, and is silent
    framework.write_json(path, {**framework.load_json(path), "judge_max_spend_usd": None})
    assert "judge_max_spend_usd is 0" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])


def test_a_repriced_cost_must_match_the_rows_it_was_priced_from(tmp_path):
    # the basis NAME was all that was checked, so a sidecar could claim the repriced basis while its rows summed
    # to eight times its cost_usd, and the ledger folds cost_usd (Codex round 8 on PR #28)
    journal, runs, _ = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.10, "n1")
    path = runs / "run_1" / "run_1.report.json"
    rows = [{"model": "anthropic/claude-haiku-4-5", "cost_usd": 0.80, "usage_missing": False}]
    framework.write_json(path, {**framework.load_json(path), "models": rows})
    problems = "\n".join(reconcile.reconcile(journal, runs)["problems"])
    assert "prices from per-model rows summing to 0.80000000, but cost_usd is 0.10000000" in problems

    # a repriced basis must not carry an unpriced row: that path imputes the ceiling instead
    framework.write_json(path, {**framework.load_json(path), "cost_usd": 0.10,
                                "models": [{"model": "m", "cost_usd": None, "usage_missing": True}]})
    assert "a row records no usable cost_usd" in "\n".join(reconcile.reconcile(journal, runs)["problems"])

    # ...and a ceiling-imputed cost must be the ceiling it records
    framework.write_json(path, {**framework.load_json(path), "cost_basis": "ceiling_imputed:usage_missing",
                                "cost_usd": 0.10, "max_spend_usd": 1.0})
    assert "books the ceiling, but cost_usd 0.10000000 is not the max_spend_usd 1.00000000" in \
        "\n".join(reconcile.reconcile(journal, runs)["problems"])
    framework.write_json(path, {**framework.load_json(path), "cost_usd": 1.0})
    assert "books the ceiling" not in "\n".join(reconcile.reconcile(journal, runs)["problems"])
