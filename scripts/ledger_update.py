"""Fold new generation cost sidecars into the ops dashboard and the human ledger.

Every paid CI generation run archives a batch to data/simulated/<batch>.json with
a <batch>.report.json cost sidecar (alias sidecars are zero-cost bookkeeping
copies). This is the accounting step of the daily autonomous cycle: scan the
sidecars, fold anything not yet listed in spend.entries_seen into
ops/dashboard.json (lifetime and per-day spend, Tier B attribution, ceiling
alerts), and append one bullet per new sidecar to the ledger markdown under a
trailing "## Spend log (auto)" heading.

Strictly idempotent: a sidecar filename already in spend.entries_seen is never
counted twice, and a run that finds nothing new rewrites nothing at all. The
dashboard is read-modify-write - fields this script does not understand are
preserved untouched. Ceiling breaches are reported (WARNING + spend.alerts),
never blocking: the exit code stays 0, enforcement lives in the fire step.

Usage:
  python scripts/ledger_update.py [--simulated-dir data/simulated]
      [--dashboard ops/dashboard.json] [--ledger docs/<file>.md]
      [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

LEDGER_HEADING = "## Spend log (auto)"
DAY_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--simulated-dir", default="data/simulated",
                        help="directory holding <batch>.report.json cost sidecars")
    parser.add_argument("--dashboard", default="ops/dashboard.json")
    parser.add_argument("--ledger", default=None,
                        help="ledger markdown file (default: lexicographically newest docs/*ledger*.md)")
    parser.add_argument("--date", default=None,
                        help="UTC day YYYY-MM-DD treated as 'today' (default: actual UTC today)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the would-be changes and write nothing")
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


def load_dashboard(path: Path):
    """Existing dashboard as-is (unknown fields kept), or a minimal skeleton."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1}


def resolve_ledger(arg):
    if arg:
        return Path(arg)
    matches = sorted(Path("docs").glob("*ledger*.md"))
    return matches[-1] if matches else None


def scan_new_sidecars(sim_dir: Path, seen: set):
    """(path, parsed sidecar) for every unseen *.report.json, sorted by filename."""
    for path in sorted(sim_dir.glob("*.report.json"), key=lambda p: p.name):
        if path.name in seen:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(f"WARNING: unreadable sidecar skipped (will retry next run): {path.name}")
            continue
        if not isinstance(report, dict):
            print(f"WARNING: unexpected sidecar shape skipped: {path.name}")
            continue
        yield path, report


def attribute_tierb(dashboard, spend, report, filename, cost):
    """Count a sidecar toward the Tier B campaign when it belongs to it.

    Gate: tierb.start_utc set, task == 'pairs', model == tierb.generator, and
    run_timestamp at or after start_utc. Everything else is background spend.
    """
    tierb = dashboard.get("tierb")
    if not isinstance(tierb, dict) or not tierb.get("start_utc"):
        return False
    if report.get("task") != "pairs":
        return False
    model = report.get("model")
    if not model or model != tierb.get("generator"):
        return False
    start = parse_ts(tierb.get("start_utc"))
    run_ts = parse_ts(report.get("run_timestamp"))
    if start is None or run_ts is None or run_ts < start:
        return False
    accepted = int(report.get("accepted") or 0)
    tierb["accepted_pairs"] = int(tierb.get("accepted_pairs") or 0) + accepted
    spend["generation_spent_usd"] = round(float(spend.get("generation_spent_usd") or 0.0) + cost, 4)
    tierb.setdefault("batches", []).append(
        {"file": filename, "accepted": accepted, "cost_usd": cost, "status": "landed"})
    return True


def ledger_bullet(filename, cost, report):
    accepted = report.get("accepted")
    return (f"- {filename} · ${cost:.4f} · {report.get('model') or 'alias'}"
            f" · accepted {accepted if accepted is not None else '—'}"
            f" · {report.get('run_timestamp') or '—'}")


def check_ceilings(spend):
    """Append stable, deduplicated alert sentences; True when the list changed.

    Reporting only - the exit code stays 0. Blocking lives in the fire step.
    """
    alerts = spend.setdefault("alerts", [])
    sentences = []
    ceiling = spend.get("generation_ceiling_usd")
    spent = spend.get("generation_spent_usd")
    if ceiling is not None and spent is not None and float(spent) > float(ceiling):
        sentences.append(f"Tier B generation spend has exceeded the ${money(ceiling)} run ceiling.")
    daily = spend.get("daily_ceiling_usd")
    today = spend.get("today") or {}
    today_spent = today.get("spent_usd")
    if daily is not None and today_spent is not None and float(today_spent) > float(daily):
        sentences.append(f"Daily spend on {today.get('date', '?')} has exceeded the ${money(daily)} daily ceiling.")
    changed = False
    for sentence in sentences:
        print(f"WARNING: {sentence}")
        if sentence not in alerts:
            alerts.append(sentence)
            changed = True
    return changed


def append_ledger(path: Path, bullets):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    if LEDGER_HEADING not in text:
        text += ("\n" if text else "") + LEDGER_HEADING + "\n\n"
    text += "".join(bullet + "\n" for bullet in bullets)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_dashboard(path: Path, dashboard):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    date = args.date or datetime.now(timezone.utc).date().isoformat()
    dashboard_path = Path(args.dashboard)
    ledger_path = resolve_ledger(args.ledger)

    dashboard = load_dashboard(dashboard_path)
    spend = dashboard.setdefault("spend", {})
    entries_seen = spend.setdefault("entries_seen", [])
    by_day = spend.setdefault("by_day", {})

    bullets = []
    for path, report in scan_new_sidecars(Path(args.simulated_dir), set(entries_seen)):
        cost = float(report.get("cost_usd") or 0.0)
        stamp = report.get("run_timestamp")
        day = stamp[:10] if isinstance(stamp, str) and DAY_PREFIX.match(stamp) else date
        spend["lifetime_generation_usd"] = round(float(spend.get("lifetime_generation_usd") or 0.0) + cost, 4)
        by_day[day] = round(float(by_day.get(day) or 0.0) + cost, 4)
        entries_seen.append(path.name)
        attribute_tierb(dashboard, spend, report, path.name, cost)
        bullets.append(ledger_bullet(path.name, cost, report))

    if bullets:
        spend["today"] = {"date": date, "spent_usd": float(by_day.get(date) or 0.0)}
        spend["last_scan_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    alerts_changed = check_ceilings(spend)

    dashboard_dirty = bool(bullets) or alerts_changed or not dashboard_path.exists()
    if args.dry_run:
        if dashboard_dirty:
            print(f"DRY RUN: would write {dashboard_path}")
        for bullet in bullets:
            print(f"DRY RUN: would append to {ledger_path}: {bullet}")
    else:
        if dashboard_dirty:
            write_dashboard(dashboard_path, dashboard)
        if bullets:
            if ledger_path is None:
                print("WARNING: no docs/*ledger*.md found; ledger append skipped")
            else:
                append_ledger(ledger_path, bullets)

    gen_ceiling = spend.get("generation_ceiling_usd")
    daily_ceiling = spend.get("daily_ceiling_usd")
    print(f"{len(bullets)} new sidecars"
          f" · lifetime ${money(spend.get('lifetime_generation_usd') or 0.0)}"
          f" · tierB ${money(spend.get('generation_spent_usd') or 0.0)}"
          f"/{'$' + money(gen_ceiling) if gen_ceiling is not None else '—'}"
          f" · today ${money(by_day.get(date) or 0.0)}"
          f"/{'$' + money(daily_ceiling) if daily_ceiling is not None else '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
