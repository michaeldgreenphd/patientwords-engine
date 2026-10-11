#!/usr/bin/env python3
"""Execute and coordinate a planned backfill leg in a scheduled cloud CI runner.

Designed for unattended execution on GitHub Actions (scheduled cron):
  1. Checks ops/trigger_journal.jsonl: if logits-eval has active unharvested fires
     (using fire_trigger.active_entries with standard expiry), exits cleanly.
  2. Queries scripts/backfill_planner.py (campaign_plan) for the next leg.
  3. Supports reserving the lane before matrix inference begins and resolving it upon completion.
  4. Exports leg parameters for GitHub Actions matrix execution.

Usage:
  python scripts/scheduled_backfill_leg.py --plan                 # print plan and export outputs
  python scripts/scheduled_backfill_leg.py --reserve --nonce ...   # reserve lane in journal
  python scripts/scheduled_backfill_leg.py --resolve --nonce ...   # resolve lane in journal
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_fire_trigger(repo: Path):
    return load_module("ft_for_scheduled", repo / "scripts" / "fire_trigger.py")


def load_backfill_planner(repo: Path):
    return load_module("bp_for_scheduled", repo / "scripts" / "backfill_planner.py")


def has_active_entries(repo: Path, trigger: str = "logits-eval") -> bool:
    ft = load_fire_trigger(repo)
    journal_path = repo / "ops" / "trigger_journal.jsonl"
    entries = ft.load_journal(journal_path)
    now = datetime.now(timezone.utc)
    active = ft.active_entries(entries, trigger, now, ft.expire_hours_from_env())
    return bool(active)


def get_next_leg(repo: Path) -> tuple[dict | None, str]:
    """Returns (leg_dict, reason_str). If leg_dict is None, reason_str explains why."""
    if has_active_entries(repo, "logits-eval"):
        return None, "logits-eval lane has active entries; skipping to prevent collision"

    bp = load_backfill_planner(repo)
    cov = bp.coverage()
    blocked: list = []
    plan = bp.campaign_plan(cov, 1, include_medgemma15=False, medgemma15_selection=None, blocked=blocked)
    if blocked:
        raise RuntimeError(f"Encountered blocked gaps in planner: {blocked}")
    if not plan:
        return None, "Backfill campaign is AT PARITY; all models measured."

    return plan[0], "ok"


def reserve_leg(repo: Path, note: str, nonce: str, params: dict) -> bool:
    ft = load_fire_trigger(repo)
    journal_path = repo / "ops" / "trigger_journal.jsonl"
    entries = ft.load_journal(journal_path)
    now = datetime.now(timezone.utc)
    for e in entries:
        if e.get("nonce") == nonce:
            print(f"Nonce {nonce} already present in journal; skipping duplicate reserve")
            return True
    if ft.active_entries(entries, "logits-eval", now, ft.expire_hours_from_env()):
        print(f"Notice: logits-eval lane has active entries; refusing to reserve nonce {nonce}", file=sys.stderr)
        return False
    now_utc = ft.iso_utc(now)
    params_content = json.dumps(params, sort_keys=True)
    entry = {
        "trigger": "logits-eval",
        "fired_utc": now_utc,
        "commit": "",
        "note": note,
        "resolved": False,
        "evicted": False,
        "nonce": nonce,
        "ref": "main",
        "params_sha256": ft.params_digest(params_content),
    }
    entries.append(entry)
    ft.save_journal(journal_path, entries)
    print(f"Reserved lane with nonce {nonce}")
    return True


def resolve_leg(repo: Path, nonce: str, status: str = "success") -> None:
    ft = load_fire_trigger(repo)
    journal_path = repo / "ops" / "trigger_journal.jsonl"
    entries = ft.load_journal(journal_path)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = False
    for e in entries:
        if e.get("nonce") == nonce and not e.get("resolved"):
            e["resolved"] = True
            e["resolved_utc"] = now_utc
            if status and status != "success":
                e["note"] = (e.get("note", "") + f" [{status}]").strip()
            found = True
            break
    if found:
        ft.save_journal(journal_path, entries)
        print(f"Resolved entry with nonce {nonce} (status={status})")
    else:
        print(f"Notice: active entry with nonce {nonce} not found in journal")


def set_github_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def cmd_plan(repo: Path, dry_run: bool = False) -> int:
    leg, reason = get_next_leg(repo)
    if leg is None:
        print(f"Notice: {reason}")
        set_github_output("should_run", "false")
        set_github_output("models", "[]")
        return 0

    params = leg["params"]
    models = [m.strip() for m in params["models"].replace(",", " ").split() if m.strip()]
    pairs_file = params["pairs_file"]
    limit = str(params.get("limit", "0"))
    offset = str(params.get("offset", "0"))
    indices = str(params.get("indices") or "")
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nonce = f"scheduled-{now_stamp}"
    note = leg["note"] + " [scheduled_runner]"

    print(f"Next planned leg: {note}")
    print(f"Models: {models} | File: {pairs_file} | Offset: {offset} | Limit: {limit}")

    set_github_output("should_run", "true")
    set_github_output("models", json.dumps(models))
    set_github_output("pairs_file", pairs_file)
    set_github_output("limit", limit)
    set_github_output("offset", offset)
    set_github_output("indices", indices)
    set_github_output("nonce", nonce)
    set_github_output("note", note)
    set_github_output("params_json", json.dumps(params))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(ENGINE), help="Path to patientwords-engine")
    parser.add_argument("--plan", action="store_true", help="Compute plan and export outputs")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without reserving lane")
    parser.add_argument("--reserve", action="store_true", help="Reserve lane with --note and --nonce")
    parser.add_argument("--resolve", action="store_true", help="Resolve lane with --nonce")
    parser.add_argument("--note", default="", help="Note for reservation")
    parser.add_argument("--nonce", default="", help="Nonce identifier")
    parser.add_argument("--params", default="{}", help="Params JSON string for reservation")
    parser.add_argument("--status", default="success", help="Status of run ('success', 'failure', etc.)")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    if args.plan or args.dry_run:
        return cmd_plan(repo, dry_run=args.dry_run)
    elif args.reserve:
        if not args.nonce:
            print("Error: --reserve requires --nonce", file=sys.stderr)
            return 1
        ok = reserve_leg(repo, args.note, args.nonce, json.loads(args.params))
        return 0 if ok else 2
    elif args.resolve:
        if not args.nonce:
            print("Error: --resolve requires --nonce", file=sys.stderr)
            return 1
        resolve_leg(repo, args.nonce, status=args.status)
        return 0

    # Default to plan dry-run if no action given
    return cmd_plan(repo, dry_run=True)


if __name__ == "__main__":
    sys.exit(main())
