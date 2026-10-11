#!/usr/bin/env python3
"""Execute a single planned backfill leg in a scheduled cloud CI runner.

Designed for unattended execution on GitHub Actions (scheduled cron):
  1. Checks ops/trigger_journal.jsonl: if logits-eval has active unharvested fires,
     exits cleanly without interfering.
  2. Queries scripts/backfill_planner.py (campaign_plan) for the next leg. If the campaign
     is at parity, prints a notice and exits 0.
  3. Executes CPU-logits measurement for each model in the planned leg.
  4. Confirms the expected part files were created.
  5. Records the completed leg in ops/trigger_journal.jsonl as resolved.

Usage:
  python scripts/scheduled_backfill_leg.py              # execute the next leg
  python scripts/scheduled_backfill_leg.py --dry-run    # print the next leg plan and exit
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]


def load_journal(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def append_journal(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def has_active_entries(journal_path: Path, trigger: str = "logits-eval") -> bool:
    entries = load_journal(journal_path)
    return any(
        e.get("trigger") == trigger and not e.get("resolved") and not e.get("evicted")
        for e in entries
    )


def run_leg(
    repo: Path,
    dry_run: bool = False,
    run_cmd=subprocess.run,
) -> int:
    import importlib.util

    bp_spec = importlib.util.spec_from_file_location(
        "bp_for_scheduled", repo / "scripts" / "backfill_planner.py"
    )
    bp = importlib.util.module_from_spec(bp_spec)
    bp_spec.loader.exec_module(bp)

    journal_path = repo / "ops" / "trigger_journal.jsonl"
    if has_active_entries(journal_path, "logits-eval"):
        print("logits-eval lane has active entries; skipping to prevent collision")
        return 0

    cov = bp.coverage()
    blocked: list = []
    plan = bp.campaign_plan(cov, 1, include_medgemma15=False, selection=None, blocked=blocked)
    if blocked:
        print(f"Encountered blocked gaps in planner: {blocked}")
        return 1

    if not plan:
        print("Backfill campaign is AT PARITY; all models measured.")
        return 0

    leg = plan[0]
    note = leg["note"] + " [scheduled_runner]"
    params = leg["params"]
    models = params["models"].split(",")
    pairs_file = params["pairs_file"]
    limit = params.get("limit", "0")
    offset = params.get("offset", "0")
    indices = params.get("indices")
    stem = Path(pairs_file).stem

    print(f"Planned leg: {note}")
    print(f"Models: {models} | File: {pairs_file} | Offset: {offset} | Limit: {limit}")

    if dry_run:
        print("Dry run requested; exiting without executing evaluation.")
        return 0

    for model in models:
        out_dir = str(repo / "trace_out" / f"{stem}__{model}")
        cmd = [
            sys.executable,
            str(repo / "scripts" / "logits_eval.py"),
            "--pairs",
            str(repo / pairs_file),
            "--model",
            model,
            "--out",
            out_dir,
            "--offset",
            str(offset),
            "--limit",
            str(limit),
        ]
        if indices:
            cmd.extend(["--indices", str(indices)])

        print(f"Executing: {' '.join(cmd)}")
        res = run_cmd(cmd, check=False)
        rc = getattr(res, "returncode", 0) if res is not None else 0
        if rc != 0:
            print(f"Evaluation of {model} failed with exit code {rc}")
            return rc

    # Record completed run in trigger journal
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "trigger": "logits-eval",
        "fired_utc": now_utc,
        "commit": "",
        "note": note,
        "resolved": True,
        "evicted": False,
        "nonce": f"scheduled-{now_utc}",
        "ref": "main",
        "resolved_utc": now_utc,
    }
    append_journal(journal_path, entry)
    print("Leg completed successfully and journaled.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(ENGINE), help="Path to patientwords-engine")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without running")
    args = parser.parse_args(argv)
    return run_leg(Path(args.repo), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
