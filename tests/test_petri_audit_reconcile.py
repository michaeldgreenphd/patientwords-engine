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
    assert "run_1/run_1.report.json: cost_usd is missing or not a number" in "\n".join(result["problems"])
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
