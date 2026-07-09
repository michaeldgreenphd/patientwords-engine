"""Fire a push-to-run CI trigger safely: queue guard, key validation, spend ceiling ($0, local).

Every paid or networked workflow in this repo starts when its file under
.github/trigger/ changes on a pushed branch. Each workflow has a per-branch
concurrency group with cancel-in-progress: false - one running + one pending
run - so pushing a THIRD trigger change silently evicts the pending run. This
script is the only sanctioned way for agent sessions to fire triggers: it
journals every fire to ops/trigger_journal.jsonl, refuses a third stacked fire,
validates parameter keys against the workflow inputs (CI silently ignores
unknown keys, so a typo means a run with defaults - catching it locally is the
whole point), and enforces the daily spend ceiling from ops/dashboard.json for
the paid triggers (scenario-generation, model-evaluation).

Usage:
  python scripts/fire_trigger.py fire --trigger circuit-trace \
      --params '{"graph_model": "gemma-2-2b", "mode": "2panel", "_nonce": "x1"}' \
      --note "why this run fires"
  python scripts/fire_trigger.py resolve --trigger circuit-trace    # after the run lands
  python scripts/fire_trigger.py status

A journal entry is ACTIVE while resolved and evicted are both false and it is
younger than MEDLANG_TRIGGER_EXPIRE_HOURS (default 8; chunked workflow runs
never exceed ~6h, so expiry is a safety valve for entries nobody resolved).

Exit codes: 0 fired/ok, 2 queue refusal, 3 bad params, 4 budget refusal,
1 git failure. No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRIGGERS = (
    "circuit-trace",
    "logits-eval",
    "scenario-generation",
    "model-evaluation",
    "archive-renders",
)
PAID_TRIGGERS = frozenset({"scenario-generation", "model-evaluation"})
DEFAULT_EXPIRE_HOURS = 8.0
DEFAULT_DAILY_CEILING_USD = 2.0
JOURNAL_RELPATH = Path("ops") / "trigger_journal.jsonl"
DASHBOARD_RELPATH = Path("ops") / "dashboard.json"
TRIGGER_DIR_RELPATH = Path(".github") / "trigger"
PUSH_BACKOFF_SECONDS = (2, 4, 8, 16)

# Keys verified against the workflow dispatch inputs; unknown keys are a hard error
# because these two workflows are where typos cost money or evict queued runs.
VERIFIED_KEYS = {
    "circuit-trace": frozenset({
        "graph_model", "graph_models", "mode", "pairs_file", "offsets", "sample_size",
        "screen_targets", "show_mitigation", "commit_outputs", "max_n_logits",
        "desired_logit_prob", "node_threshold", "edge_threshold", "max_feature_nodes",
        "generate_explanations", "steer_validate", "steer_boost", "steer_placebo",
        "steer_strength", "steer_boost_strength", "steer_rank_offset", "translation_model",
    }),
    "scenario-generation": frozenset({
        "task", "num", "topics", "seed_pairs", "feedback", "phrase", "term",
        "target_token", "num_baselines", "dialects", "anthropic_model", "max_spend",
        "graph_models", "trace_sample_size",
    }),
}

# Best-known key lists for the remaining triggers (unverified against the YAML,
# so unknown keys only warn).
BEST_KNOWN_KEYS = {
    "logits-eval": frozenset({"models", "pairs_file", "limit", "commit_outputs"}),
    "model-evaluation": frozenset({"model_selection", "scenario", "sample_size", "max_spend"}),
    "archive-renders": frozenset({"tag", "runs", "no_pngs", "prune"}),
}


def utc_now():
    return datetime.now(timezone.utc)


def iso_utc(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(stamp):
    """Datetime for an iso8601Z stamp, or None when it does not parse."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def expire_hours_from_env():
    raw = os.environ.get("MEDLANG_TRIGGER_EXPIRE_HOURS", "")
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_EXPIRE_HOURS


def load_journal(path):
    """Journal entries from a JSON Lines file. Blank lines are skipped; unknown
    fields ride along untouched; malformed lines are dropped."""
    entries = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return entries
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def save_journal(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def entry_is_active(entry, now, expire_hours):
    """Active = not resolved, not evicted, and younger than expire_hours."""
    if entry.get("resolved") or entry.get("evicted"):
        return False
    fired = parse_utc(entry.get("fired_utc"))
    if fired is None:
        return False
    return (now - fired) < timedelta(hours=expire_hours)


def active_entries(entries, trigger, now, expire_hours):
    """Active entries for one trigger, oldest first (journal order breaks ties)."""
    active = [e for e in entries if e.get("trigger") == trigger and entry_is_active(e, now, expire_hours)]
    return sorted(active, key=lambda e: parse_utc(e["fired_utc"]))


def validate_params(trigger, params):
    """Warnings for best-known-only key lists; ValueError on hard errors
    (non-dict params, unknown key for a verified trigger)."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; expected one of {', '.join(TRIGGERS)}")
    if not isinstance(params, dict):
        raise ValueError(f"params must be a JSON object (dict), got {type(params).__name__}")
    keys = {str(k) for k in params if not str(k).startswith("_")}
    if trigger in VERIFIED_KEYS:
        unknown = sorted(keys - VERIFIED_KEYS[trigger])
        if unknown:
            raise ValueError(
                f"unknown {trigger} key(s) {unknown}: CI silently ignores unknown keys, so a typo "
                f"means a run with defaults; allowed keys: {sorted(VERIFIED_KEYS[trigger])}"
            )
        return []
    unknown = sorted(keys - BEST_KNOWN_KEYS[trigger])
    return [
        f"key {k!r} is not in the best-known {trigger} list (list unverified) - double-check the workflow inputs"
        for k in unknown
    ]


def budget_check(params, dashboard, today):
    """(ok, reason) against the daily spend ceiling for a paid trigger.

    Tolerates a missing/partial dashboard: ceiling defaults to
    DEFAULT_DAILY_CEILING_USD and spend counts only when spend.today.date
    equals `today` (a YYYY-MM-DD UTC date string).
    """
    if "max_spend" not in params:
        return False, "paid trigger params must include max_spend"
    try:
        max_spend = float(params["max_spend"])
    except (TypeError, ValueError):
        return False, f"max_spend does not parse as a number: {params['max_spend']!r}"
    spend = dashboard.get("spend") if isinstance(dashboard, dict) else None
    if not isinstance(spend, dict):
        spend = {}
    try:
        ceiling = float(spend.get("daily_ceiling_usd", DEFAULT_DAILY_CEILING_USD))
    except (TypeError, ValueError):
        ceiling = DEFAULT_DAILY_CEILING_USD
    today_rec = spend.get("today")
    spent = 0.0
    if isinstance(today_rec, dict) and today_rec.get("date") == today:
        try:
            spent = float(today_rec.get("spent_usd", 0.0))
        except (TypeError, ValueError):
            spent = 0.0
    if max_spend + spent > ceiling:
        return False, (
            f"max_spend {max_spend:.2f} + today's spent {spent:.2f} "
            f"would exceed the daily ceiling {ceiling:.2f} USD"
        )
    return True, f"max_spend {max_spend:.2f} + today's spent {spent:.2f} within the daily ceiling {ceiling:.2f} USD"


def queue_view(entries, now, expire_hours):
    """Dashboard-shaped queue: {group: {running, pending}} from active journal
    entries, oldest active first."""
    view = {}
    for trigger in TRIGGERS:
        active = active_entries(entries, trigger, now, expire_hours)
        slots = [
            {"fired_utc": e.get("fired_utc", ""), "commit": e.get("commit", ""), "note": e.get("note", "")}
            for e in active[:2]
        ]
        view[trigger] = {
            "running": slots[0] if slots else None,
            "pending": slots[1] if len(slots) > 1 else None,
        }
    return view


def load_dashboard(path):
    """Dashboard dict; {} when the file is missing or does not parse."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def update_dashboard_queue(dash_path, trigger, entries, now, expire_hours):
    """Rewrite this trigger's queue group in ops/dashboard.json from the journal."""
    dashboard = load_dashboard(dash_path)
    dashboard.setdefault("schema_version", 1)
    queue = dashboard.get("queue")
    if not isinstance(queue, dict):
        queue = {}
    queue[trigger] = queue_view(entries, now, expire_hours)[trigger]
    dashboard["queue"] = queue
    dashboard["updated_utc"] = iso_utc(now)
    dashboard["updated_by"] = "session"
    dash_path = Path(dash_path)
    dash_path.parent.mkdir(parents=True, exist_ok=True)
    dash_path.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")


def _git(repo, *argv):
    return subprocess.run(["git", "-C", str(repo), *argv], capture_output=True, text=True)


def git_publish(repo, paths, message, backoff=PUSH_BACKOFF_SECONDS):
    """git add + commit + push -u origin <current branch>, retrying the push
    with backoff on nonzero exit. Returns True on success. The only function
    that touches git - the --no-git path never reaches it."""
    proc = _git(repo, "add", "--", *[str(p) for p in paths])
    if proc.returncode != 0:
        print(f"git add failed: {proc.stderr.strip()}", file=sys.stderr)
        return False
    proc = _git(repo, "commit", "-m", message)
    if proc.returncode != 0:
        print(f"git commit failed: {proc.stderr.strip() or proc.stdout.strip()}", file=sys.stderr)
        return False
    proc = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if proc.returncode != 0:
        print(f"git rev-parse failed: {proc.stderr.strip()}", file=sys.stderr)
        return False
    branch = proc.stdout.strip()
    for attempt, delay in enumerate((0,) + tuple(backoff)):
        if delay:
            print(f"push retry {attempt}/{len(backoff)} in {delay}s", file=sys.stderr)
            time.sleep(delay)
        proc = _git(repo, "push", "-u", "origin", branch)
        if proc.returncode == 0:
            return True
        print(f"git push failed: {proc.stderr.strip()}", file=sys.stderr)
    return False


def cmd_fire(args):
    repo = Path(args.repo).resolve()
    expire_hours = expire_hours_from_env()
    now = utc_now()

    # 1-2. Parse and validate params (trigger name already constrained by argparse choices).
    raw = Path(args.params_file).read_text(encoding="utf-8") if args.params_file else args.params
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"refused: params are not valid JSON ({exc})", file=sys.stderr)
        return 3
    try:
        warnings = validate_params(args.trigger, params)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    # 3. Queue guard: one running + one pending; a third push evicts the pending run.
    journal_path = repo / JOURNAL_RELPATH
    entries = load_journal(journal_path)
    actives = active_entries(entries, args.trigger, now, expire_hours)
    to_evict = None
    if len(actives) >= 2:
        if not args.force_evict:
            print(
                f"refused: {len(actives)} active journal entries for {args.trigger}. The workflow's "
                "concurrency group holds one running + one pending run; pushing a third trigger change "
                "silently evicts the pending run. Wait and `resolve` the landed run, or pass "
                "--force-evict to deliberately replace the pending one. Active entries:",
                file=sys.stderr,
            )
            for e in actives:
                print(f"  fired {e.get('fired_utc', '?')}  note={e.get('note', '')!r}", file=sys.stderr)
            return 2
        to_evict = actives[-1]  # newest active = the pending run this push will replace

    # 4. Budget guard for the paid triggers.
    if args.trigger in PAID_TRIGGERS:
        dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
        ok, reason = budget_check(params, dashboard, now.strftime("%Y-%m-%d"))
        if not ok:
            overridable = "max_spend" in params and reason.startswith("max_spend ")
            if args.override_budget and overridable:
                print(f"warning: budget override in effect ({reason})", file=sys.stderr)
            else:
                print(f"refused: {reason}", file=sys.stderr)
                return 4
        else:
            print(reason)

    # 5. Write trigger file + journal entry + dashboard queue (or describe, with --dry-run).
    entry = {
        "trigger": args.trigger,
        "fired_utc": iso_utc(now),
        "commit": "",
        "note": args.note,
        "resolved": False,
        "evicted": False,
    }
    trigger_path = repo / TRIGGER_DIR_RELPATH / f"{args.trigger}.json"
    content = json.dumps(params, separators=(",", ":")) + "\n"
    try:
        unchanged = trigger_path.read_text(encoding="utf-8") == content
    except OSError:
        unchanged = False
    if unchanged:
        print(
            f"warning: {trigger_path} already holds exactly this content - a push will not change the "
            "file, so the workflow will NOT fire; add a _nonce key to force a change",
            file=sys.stderr,
        )
    if args.dry_run:
        print(f"[dry-run] would write {trigger_path}: {content.strip()}")
        if to_evict is not None:
            print(f"[dry-run] would mark evicted: fired {to_evict.get('fired_utc', '?')} "
                  f"note={to_evict.get('note', '')!r}")
        print(f"[dry-run] would append to {journal_path}: {json.dumps(entry)}")
        print(f"[dry-run] would update queue group {args.trigger!r} in {repo / DASHBOARD_RELPATH}")
        if not args.no_git:
            print(f"[dry-run] would git add/commit/push ('Fire {args.trigger}: {args.note}')")
        return 0
    if to_evict is not None:
        to_evict["evicted"] = True
        print(f"evicted pending entry: fired {to_evict.get('fired_utc', '?')} note={to_evict.get('note', '')!r}")
    entries.append(entry)
    trigger_path.parent.mkdir(parents=True, exist_ok=True)
    trigger_path.write_text(content, encoding="utf-8")
    save_journal(journal_path, entries)
    update_dashboard_queue(repo / DASHBOARD_RELPATH, args.trigger, entries, now, expire_hours)

    # 6. Publish, unless --no-git.
    if not args.no_git:
        if not git_publish(repo, [trigger_path, journal_path, repo / DASHBOARD_RELPATH],
                           f"Fire {args.trigger}: {args.note}"):
            print("fire written locally but git publish failed - resolve by hand", file=sys.stderr)
            return 1
    slot = "pending" if len(active_entries(entries, args.trigger, now, expire_hours)) > 1 else "running"
    print(f"fired {args.trigger} ({slot} slot); `resolve --trigger {args.trigger}` once the run lands")
    return 0


def cmd_resolve(args):
    repo = Path(args.repo).resolve()
    expire_hours = expire_hours_from_env()
    now = utc_now()
    journal_path = repo / JOURNAL_RELPATH
    entries = load_journal(journal_path)
    actives = active_entries(entries, args.trigger, now, expire_hours)
    if not actives:
        print(f"no active journal entries for {args.trigger}; nothing to resolve")
        return 0
    targets = actives if args.all else actives[:1]
    for entry in targets:
        entry["resolved"] = True
        print(f"resolved: fired {entry.get('fired_utc', '?')} note={entry.get('note', '')!r}")
    save_journal(journal_path, entries)
    if (repo / DASHBOARD_RELPATH).exists():
        update_dashboard_queue(repo / DASHBOARD_RELPATH, args.trigger, entries, now, expire_hours)
    return 0


def cmd_status(args):
    repo = Path(args.repo).resolve()
    expire_hours = expire_hours_from_env()
    now = utc_now()
    entries = load_journal(repo / JOURNAL_RELPATH)
    for trigger in TRIGGERS:
        actives = active_entries(entries, trigger, now, expire_hours)
        print(f"{trigger}: {len(actives)} active")
        for e in actives:
            fired = parse_utc(e.get("fired_utc"))
            age = f"{(now - fired).total_seconds() / 3600:.1f}h ago" if fired else "unparseable stamp"
            print(f"  fired {e.get('fired_utc', '?')} ({age})  note={e.get('note', '')!r}")
    print("dashboard queue view:")
    print(json.dumps(queue_view(entries, now, expire_hours), indent=2))
    dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
    if dashboard:
        print(f"dashboard last updated {dashboard.get('updated_utc', '?')} by {dashboard.get('updated_by', '?')}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]),
                        help="repo root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    fire = sub.add_parser("fire", parents=[common], help="write a trigger file, journal it, and push")
    fire.add_argument("--trigger", required=True, choices=TRIGGERS)
    params = fire.add_mutually_exclusive_group(required=True)
    params.add_argument("--params", help="workflow parameters as a JSON object string")
    params.add_argument("--params-file", help="path to a JSON file holding the parameters object")
    fire.add_argument("--note", default="", help="why this run fires (journal + commit message)")
    fire.add_argument("--force-evict", action="store_true",
                      help="deliberately replace the pending run when two entries are already active")
    fire.add_argument("--dry-run", action="store_true", help="print what would happen; write nothing")
    fire.add_argument("--no-git", action="store_true", help="write files but skip git add/commit/push")
    fire.add_argument("--override-budget", action="store_true",
                      help="proceed past a daily-ceiling refusal (max_spend still required)")
    fire.set_defaults(func=cmd_fire)

    resolve = sub.add_parser("resolve", parents=[common], help="mark the oldest active entry resolved")
    resolve.add_argument("--trigger", required=True, choices=TRIGGERS)
    resolve.add_argument("--all", action="store_true", help="resolve every active entry for the trigger")
    resolve.set_defaults(func=cmd_resolve)

    status = sub.add_parser("status", parents=[common], help="per-trigger active counts and queue view")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
