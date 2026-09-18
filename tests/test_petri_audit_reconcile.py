"""Journal-to-ledger reconciliation for the petri-audit lane
(scripts/petri_audit/reconcile.py): paid journal entries are joined to the
landed cost sidecars on the fire nonce, and every gap is named. 3.11-safe."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, framework, reconcile  # noqa: E402


def _entry(fired: str, nonce: str | None, max_spend: float | None = None, **extra) -> dict:
    e = {"trigger": "petri-audit", "fired_utc": fired, "commit": "", "note": "t", "resolved": False, "evicted": False, "nonce": nonce}
    if max_spend is not None:
        e["max_spend"] = max_spend
        e["lane"] = "anthropic"
    e.update(extra)
    return e


def _sidecar(runs: Path, run: str, cost: float, nonce: str | None, judge_cost: float | None = None) -> None:
    d = runs / run
    d.mkdir(parents=True, exist_ok=True)
    framework.write_json(d / f"{run}.report.json", {"run_id": run, "cost_usd": cost, "cost_basis": "engine_repriced_from_inspect_model_usage",
                                                   "billing_channel": "anthropic", "journal_nonce": nonce, "max_spend_usd": 1.0})
    if judge_cost is not None:
        framework.write_json(d / f"{run}.judge.report.json", {"judge_model": "claude-haiku-4-5", "cost_usd": judge_cost,
                                                             "cost_basis": "cumulative_from_records", "billing_channel": "anthropic"})


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
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"]}})
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
    assert "**Problems (3)**" in text and "Not yet folded into the ledger" in text


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


def test_cli_reconcile_spend_renders_writes_json_and_is_strict_on_request(tmp_path, capsys):
    journal, runs, dashboard = _layout(tmp_path)
    journal.write_text(json.dumps(_entry("2026-09-18T10:00:00Z", "n1", 1.0, resolved=True)) + "\n", encoding="utf-8")
    _sidecar(runs, "run_1", 0.3, "n1")
    framework.write_json(dashboard, {"spend": {"entries_seen": ["run_1.report.json"]}})
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
