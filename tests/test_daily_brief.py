"""Tests for scripts/daily_brief.py — the 3-section morning brief and its digest line.

render_brief/digest are pure (dict in, string out) and --date is injected
everywhere, so nothing here touches the wall clock or the network.
"""
import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_brief.py"
_SPEC = importlib.util.spec_from_file_location("daily_brief", _SCRIPT)
daily_brief = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(daily_brief)

DATE = "2026-07-09"

FULL = {
    "schema_version": 1,
    "updated_utc": "2026-07-09T13:00:00Z",
    "updated_by": "routine",
    "queue": {"circuit-trace": {"running": {"fired_utc": "2026-07-09T09:00:00Z",
                                            "commit": "abc1234", "note": "offsets 1-40"},
                                "pending": None}},
    "runs_recent": [
        {"workflow": "circuit_trace_evaluation", "fired_utc": "2026-07-09T09:00:00Z",
         "status": "success", "note": "offsets 1-40 landed"},
        {"workflow": "scenario_generation", "fired_utc": "2026-07-08T22:30:00Z",
         "status": "success", "note": "pairs batch landed"},
        {"workflow": "logits_evaluation", "fired_utc": "2026-07-08T21:00:00Z",
         "status": "success", "note": "before the 26h window"},
        {"workflow": "model_evaluation", "fired_utc": "2026-07-10T00:30:00Z",
         "status": "queued", "note": "after the window end"},
    ],
    "spend": {
        "generation_ceiling_usd": 8.0, "generation_spent_usd": 1.2,
        "lifetime_generation_usd": 10.76,
        "daily_ceiling_usd": 2.0, "today": {"date": DATE, "spent_usd": 0.42},
        "by_day": {DATE: 0.42, "2026-07-08": 0.3},
        "entries_seen": ["pairs_a.report.json"], "last_scan_utc": "2026-07-09T12:00:00Z",
        "alerts": [],
    },
    "tierb": {"target_pairs": 1600, "generator": "claude-haiku-4-5",
              "start_utc": "2026-07-09T00:00:00Z", "accepted_pairs": 120,
              "traced_pairs": 80, "screened_in_pairs": 60,
              "batches": [{"file": "pairs_b.json", "accepted": 50,
                           "cost_usd": 0.0985, "status": "landed"}]},
    "verdicts": ["haiku generation quality holds at 1/8 the opus cost"],
    "findings_delta": [
        {"date": DATE, "text": "downgrade concordance holds on the new batch"},
        {"date": "2026-07-05", "text": "old finding outside every window"},
    ],
    "decisions_pending": [{"id": "tierb-go", "title": "Approve Tier B start",
                           "context": "ceiling $8, haiku generator"}],
    "blockers": ["waiting on tier vocabulary review"],
    "notes": ["hand note"],
}


def render(dash=FULL, date=DATE, since_hours=26):
    return daily_brief.render_brief(dash, date, since_hours)


def test_golden_shape_title_and_three_sections_in_order():
    brief = render()
    lines = brief.splitlines()
    assert lines[0] == f"# Daily brief — {DATE}"
    headings = [ln for ln in lines if ln.startswith("#")]
    assert headings == [f"# Daily brief — {DATE}", "## Delta", "## Verdicts", "## Blocked on owner"]
    # Delta carries the tierb and spend status lines in the documented shape
    assert "- Tier B: 120/1600 accepted · 80 traced · 60 screened-in" in lines
    assert "- Spend: $0.42/2 today · $1.2/8 Tier B generation · $10.76 lifetime" in lines
    # one bullet per in-window run and finding
    assert "- circuit_trace_evaluation · success · offsets 1-40 landed" in lines
    assert f"- {DATE} — downgrade concordance holds on the new batch" in lines
    # verdicts and blocked bullets
    assert "- haiku generation quality holds at 1/8 the opus cost" in lines
    assert "- tierb-go · Approve Tier B start — ceiling $8, haiku generator" in lines
    assert "- waiting on tier vocabulary review" in lines
    # no fallback bullets when data is present
    assert "no changes in the last" not in brief
    assert "no verdict changes" not in brief
    assert "nothing blocked on you" not in brief


def test_empty_dashboard_renders_all_three_fallback_bullets():
    brief = render({})
    lines = brief.splitlines()
    assert lines[0] == f"# Daily brief — {DATE}"
    for heading, fallback in [("## Delta", "- no changes in the last 26h"),
                              ("## Verdicts", "- no verdict changes"),
                              ("## Blocked on owner", "- nothing blocked on you")]:
        assert heading in lines
        assert lines[lines.index(heading) + 1] == fallback
    # absent tierb/spend means no status lines, not placeholder ones
    assert "Tier B:" not in brief
    assert "Spend:" not in brief


def test_window_filtering_includes_and_excludes_by_fired_utc():
    brief = render()  # 26h window: [2026-07-08T21:59Z, 2026-07-09T23:59Z]
    assert "offsets 1-40 landed" in brief
    assert "pairs batch landed" in brief          # 07-08T22:30Z, inside
    assert "before the 26h window" not in brief   # 07-08T21:00Z, before start
    assert "after the window end" not in brief    # 07-10T00:30Z, after end
    # a tighter window (ending <date>T23:59Z) drops yesterday's run but keeps today's 09:00Z one
    tight = render(since_hours=15)
    assert "offsets 1-40 landed" in tight
    assert "pairs batch landed" not in tight
    assert "no changes in the last" not in tight


def test_findings_window_same_day_always_yesterday_only_within_hours():
    dash = {"findings_delta": [{"date": DATE, "text": "same-day finding"},
                               {"date": "2026-07-08", "text": "yesterday finding"},
                               {"date": "2026-07-05", "text": "stale finding"}]}
    brief = render(dash)
    assert "same-day finding" in brief
    assert "yesterday finding" in brief           # 07-08T23:59Z anchor inside 26h window
    assert "stale finding" not in brief
    tight = render(dash, since_hours=2)
    assert "same-day finding" in tight            # date == <date> is always in
    assert "yesterday finding" not in tight


def test_empty_window_fallback_coexists_with_status_lines():
    dash = {"tierb": {"accepted_pairs": 5, "target_pairs": 1600},
            "runs_recent": [{"workflow": "scenario_generation",
                             "fired_utc": "2026-06-01T00:00:00Z", "status": "success", "note": "old"}]}
    lines = render(dash).splitlines()
    assert "- Tier B: 5/1600 accepted · 0 traced · 0 screened-in" in lines
    assert "- no changes in the last 26h" in lines
    assert "old" not in "".join(lines)


def test_render_is_deterministic_no_wall_clock():
    assert render() == render()
    other_day = render(date="1999-01-01")
    assert other_day.splitlines()[0] == "# Daily brief — 1999-01-01"
    assert "offsets 1-40 landed" not in other_day  # window moved with the injected date


def test_digest_full_dashboard_shape():
    line = daily_brief.digest(FULL, DATE)
    assert "\n" not in line and "#" not in line
    assert line == ("TierB 120/1600 · $0.42/$2 today · 1 runs landed"
                    " · 1 decision(s) waiting · downgrade concordance holds on the new batch")
    assert len(line) <= 450


def test_digest_length_bound_with_very_long_finding():
    dash = {"findings_delta": [{"date": DATE, "text": "x" * 2000}],
            "decisions_pending": [{"id": f"d{i}"} for i in range(3)]}
    line = daily_brief.digest(dash, DATE)
    assert len(line) <= 450
    assert line.startswith("3 decision(s) waiting · ")
    assert line.endswith("…")


def test_digest_always_counts_pending_decisions_and_omits_absent_segments():
    line = daily_brief.digest({"decisions_pending": [{"id": "a"}, {"id": "b"}]}, DATE)
    assert line == "2 decision(s) waiting"
    # empty dashboard still yields a single readable plain-text line
    empty = daily_brief.digest({}, DATE)
    assert empty and "\n" not in empty and len(empty) <= 450


def test_main_out_writes_markdown_creating_parent_dirs(tmp_path, capsys):
    dash_path = tmp_path / "ops" / "dashboard.json"
    dash_path.parent.mkdir(parents=True)
    dash_path.write_text(json.dumps(FULL), encoding="utf-8")
    out = tmp_path / "docs" / "briefs" / "brief.md"

    assert daily_brief.main(["--dashboard", str(dash_path), "--date", DATE,
                             "--out", str(out)]) == 0

    assert out.read_text(encoding="utf-8") == render()
    assert capsys.readouterr().out == render()  # stdout carries the same markdown


def test_main_digest_prints_only_the_digest_line(tmp_path, capsys):
    dash_path = tmp_path / "dashboard.json"
    dash_path.write_text(json.dumps(FULL), encoding="utf-8")

    assert daily_brief.main(["--dashboard", str(dash_path), "--date", DATE, "--digest"]) == 0

    out = capsys.readouterr().out
    assert out == daily_brief.digest(FULL, DATE) + "\n"
    assert "##" not in out


def test_main_missing_dashboard_renders_empty_brief_exit_zero(tmp_path, capsys):
    assert daily_brief.main(["--dashboard", str(tmp_path / "nope.json"), "--date", DATE]) == 0
    captured = capsys.readouterr()
    assert "- no changes in the last 26h" in captured.out
    assert "WARNING" in captured.err  # warning goes to stderr, never into the brief
