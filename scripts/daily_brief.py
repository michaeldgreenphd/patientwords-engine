"""Render the owner's morning brief from ops/dashboard.json in the strict 3-section format.

The dashboard (schema_version 1) is the machine-written state file of the daily
autonomous cycle. This renders the trimmed brief the owner actually reads -
Delta (what moved), Verdicts (what we now believe), Blocked on owner (what only
they can unblock) - plus the one-line push-notification digest. The old
6-section brief was cut deliberately: pipeline detail lives in the ledger, one
link away, and this script must not grow sections back.

"Recent" means fired_utc within --since-hours of <date>T23:59Z (26h default: a
full UTC day plus slack for late-evening runs). findings_delta dates are
anchored to the same end-of-day instant, so a finding dated yesterday counts
under the default window. Every field access tolerates absence - a partial or
completely empty dashboard still renders a valid, readable brief - and nothing
in the render path touches the wall clock, so an injected --date is fully
deterministic.

Usage:
  python scripts/daily_brief.py [--dashboard ops/dashboard.json]
      [--date YYYY-MM-DD] [--since-hours 26] [--out docs/brief_<date>.md]
      [--digest]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DIGEST_MAX_CHARS = 450
SEP = " · "


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dashboard", default="ops/dashboard.json")
    parser.add_argument("--date", default=None,
                        help="UTC day YYYY-MM-DD treated as 'today' (default: actual UTC today)")
    parser.add_argument("--since-hours", type=int, default=26,
                        help="window for 'recent' runs and findings, ending <date>T23:59Z")
    parser.add_argument("--out", default=None,
                        help="also write the markdown brief here (parent dirs created)")
    parser.add_argument("--digest", action="store_true",
                        help="print only the one-line push-notification digest, no markdown")
    return parser.parse_args(argv)


def money(value):
    """$-figure without trailing zeros: 9.5600 -> '9.56', 0.0 -> '0'."""
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text or "0"


def parse_ts(value):
    """Aware UTC datetime from an ISO string ('Z' accepted); None when unparseable."""
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _flat(value):
    """One physical line: every newline becomes a space, so an interpolated
    dashboard string can never break the exactly-three-H2 brief shape."""
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _list(value):
    return value if isinstance(value, list) else []


def _window(date, since_hours):
    """(start, end) aware datetimes; end is <date>T23:59Z. (None, None) on a bad date."""
    end = parse_ts(f"{date}T23:59:00Z")
    if end is None:
        return None, None
    return end - timedelta(hours=since_hours), end


def _recent_runs(dash, date, since_hours):
    start, end = _window(date, since_hours)
    if start is None:
        return []
    runs = []
    for run in _list(dash.get("runs_recent")):
        run = _dict(run)
        fired = parse_ts(run.get("fired_utc"))
        if fired is not None and start <= fired <= end:
            runs.append(run)
    return runs


def _recent_findings(dash, date, since_hours):
    start, end = _window(date, since_hours)
    findings = []
    for entry in _list(dash.get("findings_delta")):
        entry = _dict(entry)
        fdate = entry.get("date")
        if fdate == date:
            findings.append(entry)
            continue
        if start is None or not fdate:
            continue
        anchored = parse_ts(f"{fdate}T23:59:00Z")  # same end-of-day anchor as the window itself
        if anchored is not None and start <= anchored <= end:
            findings.append(entry)
    return findings


def _tierb_line(tierb):
    if not tierb:
        return None
    accepted = tierb.get("accepted_pairs") or 0
    traced = tierb.get("traced_pairs") or 0
    screened = tierb.get("screened_in_pairs") or 0
    target = tierb.get("target_pairs")
    return (f"Tier B: {accepted}/{'—' if target is None else target} accepted"
            f" · {traced} traced · {screened} screened-in")


def _spend_line(spend, date):
    if not spend:
        return None

    def m(value):
        return "—" if value is None else money(value)

    # Same guard as digest(): a stale spend.today (recorded for another date)
    # must not render as today's spend; it shows as an em-dash instead.
    today = _dict(spend.get("today"))
    spent = today.get("spent_usd") if today.get("date") == date else None
    return (f"Spend: ${m(spent)}/{m(spend.get('daily_ceiling_usd'))} today"
            f" · ${m(spend.get('generation_spent_usd'))}/{m(spend.get('generation_ceiling_usd'))}"
            f" Tier B generation · ${m(spend.get('lifetime_generation_usd'))} lifetime")


def render_brief(dash: dict, date: str, since_hours: int) -> str:
    """The full markdown brief: title + exactly three H2 sections, in order."""
    dash = _dict(dash)
    delta = []
    tierb_line = _tierb_line(_dict(dash.get("tierb")))
    if tierb_line:
        delta.append(tierb_line)
    spend_line = _spend_line(_dict(dash.get("spend")), date)
    if spend_line:
        delta.append(spend_line)
    moved = 0
    for run in _recent_runs(dash, date, since_hours):
        delta.append(f"{run.get('workflow') or '—'} · {run.get('status') or '—'} · {run.get('note') or '—'}")
        moved += 1
    for entry in _recent_findings(dash, date, since_hours):
        delta.append(f"{entry.get('date') or date} — {entry.get('text') or '—'}")
        moved += 1
    if not moved:  # status lines are standing state; "changes" means the run/finding window
        delta.append(f"no changes in the last {since_hours}h")

    verdicts = [str(v) for v in _list(dash.get("verdicts")) if v]

    blocked = []
    for decision in _list(dash.get("decisions_pending")):
        decision = _dict(decision)
        blocked.append(f"{decision.get('id') or '—'} · {decision.get('title') or '—'}"
                       f" — {decision.get('context') or '—'}")
    blocked.extend(str(b) for b in _list(dash.get("blockers")) if b)

    lines = [f"# Daily brief — {date}", "", "## Delta"]
    lines.extend(f"- {_flat(item)}" for item in delta)
    lines += ["", "## Verdicts"]
    lines.extend([f"- {_flat(v)}" for v in verdicts] or ["- no verdict changes"])
    lines += ["", "## Blocked on owner"]
    lines.extend([f"- {_flat(b)}" for b in blocked] or ["- nothing blocked on you"])
    return "\n".join(lines) + "\n"


def digest(dash: dict, date: str) -> str:
    """One plain-text push-notification line, <= 450 chars, no markdown.

    Segments whose data is absent are omitted; a non-empty decisions_pending
    count is ALWAYS included - it is the high-signal part. 'runs landed' counts
    runs_recent entries fired on <date> itself (the digest has no window arg).
    """
    dash = _dict(dash)
    segments = []
    tierb = _dict(dash.get("tierb"))
    if "accepted_pairs" in tierb or "target_pairs" in tierb:
        accepted = tierb.get("accepted_pairs") or 0
        target = tierb.get("target_pairs")
        segments.append(f"TierB {accepted}/{'—' if target is None else target}")
    spend = _dict(dash.get("spend"))
    spent = _dict(spend.get("by_day")).get(date)
    today = _dict(spend.get("today"))
    if spent is None and today.get("date") == date:
        spent = today.get("spent_usd")
    cap = spend.get("daily_ceiling_usd")
    if spent is not None or cap is not None:
        segments.append(f"${money(spent or 0.0)}/{'$' + money(cap) if cap is not None else '—'} today")
    runs = _list(dash.get("runs_recent"))
    if runs:
        landed = sum(1 for r in runs if str(_dict(r).get("fired_utc") or "")[:10] == date)
        segments.append(f"{landed} runs landed")
    decisions = _list(dash.get("decisions_pending"))
    if decisions:
        segments.append(f"{len(decisions)} decision(s) waiting")

    findings = _list(dash.get("findings_delta"))
    # newest entry wins: the dashboard appends chronologically, so pick the
    # max date and, within a date, the last-appended entry - findings[0] was
    # surfacing the OLDEST delta as the push line (caught 2026-07-10)
    newest = max(reversed(findings), key=lambda e: str(_dict(e).get("date") or "")) if findings else None
    text = str(_dict(newest).get("text") or "").replace("\n", " ").strip()
    if text:
        budget = DIGEST_MAX_CHARS - len(SEP.join(segments)) - (len(SEP) if segments else 0)
        if len(text) > budget:
            text = (text[:budget - 1].rstrip() + "…") if budget >= 12 else ""
        if text:
            segments.append(text)

    line = SEP.join(segments) or "no dashboard data"
    return line[:DIGEST_MAX_CHARS]


def main(argv=None):
    args = parse_args(argv)
    date = args.date or datetime.now(timezone.utc).date().isoformat()

    dash = {}
    path = Path(args.dashboard)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            dash = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            print(f"WARNING: unreadable dashboard, rendering from empty state: {path}", file=sys.stderr)
    else:
        print(f"WARNING: no dashboard at {path}, rendering from empty state", file=sys.stderr)

    brief = render_brief(dash, date, args.since_hours)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(brief, encoding="utf-8")
    if args.digest:
        print(digest(dash, date))
    else:
        print(brief, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
