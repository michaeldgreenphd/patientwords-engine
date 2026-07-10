"""Study timeline reconstructed from committed artifacts, for reader-facing timing.

P2 (owner request 2026-07-10). Answers "how long did this take, and when was
each number measured" with receipts: every entry derives from a committed
artifact - batch cost sidecars (run_timestamp, model, accepted, cost),
pre-registration/amendment commit dates from git history, and the Tier B
start stamp from ops/dashboard.json. Nothing is typed in by hand.

Usage:
  python scripts/study_timeline.py [--out data/timeline.json]
      [--site ../patientwords]
"""

import argparse
import glob
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MILESTONE_FILES = [
    ("docs/preregistration_tierB.md", "Tier B pre-registration committed"),
]


def first_commit_utc(path):
    try:
        out = subprocess.run(
            ["git", "log", "--follow", "--format=%cI", "--", path],
            capture_output=True, text=True, check=True).stdout.strip().splitlines()
        return out[-1] if out else None
    except subprocess.CalledProcessError:
        return None


def batch_entries():
    entries = []
    for p in sorted(glob.glob("data/simulated/*.report.json")):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except ValueError:
            continue
        stem = Path(p).name.replace(".report.json", "")
        kind = stem.split("_")[0]
        accepted = d.get("accepted")
        cost = d.get("cost_usd")
        ts = d.get("run_timestamp")
        if ts is None and cost in (0, 0.0):
            continue  # alias sidecars carry no generation event
        entries.append({
            "batch": stem, "utc": ts, "kind": kind,
            "generator": d.get("model"),
            "accepted": accepted, "cost_usd": cost,
        })
    entries.sort(key=lambda e: e["utc"] or "")
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="data/timeline.json")
    parser.add_argument("--site", default="../patientwords",
                        help="frontend repo root; '' skips the site copy")
    args = parser.parse_args(argv)

    batches = batch_entries()
    tierb_start = None
    try:
        dash = json.loads(Path("ops/dashboard.json").read_text(encoding="utf-8"))
        tierb_start = (dash.get("tierb") or {}).get("start_utc")
    except (OSError, ValueError):
        pass

    for b in batches:
        stamp = re.sub(r"[-:]", "", tierb_start) if tierb_start else None
        m = re.search(r"_(\d{8}T\d{6}Z)$", b["batch"])
        b["tierb"] = bool(stamp and m and b["kind"] == "pairs" and m.group(1) >= stamp)

    milestones = []
    for path, label in MILESTONE_FILES:
        utc = first_commit_utc(path)
        if utc:
            milestones.append({"utc": utc, "label": label})
    if tierb_start:
        milestones.append({"utc": tierb_start, "label": "Tier B collection started"})
    milestones.sort(key=lambda m: m["utc"])

    gen_batches = [b for b in batches if isinstance(b.get("cost_usd"), (int, float))
                   and b["cost_usd"] > 0]
    trace_parts = len(glob.glob("trace_out/*/batch_summary.part_*.json"))
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": ("every entry derives from a committed artifact: batch cost "
                       "sidecars (data/simulated/*.report.json), git commit dates for "
                       "milestone documents, tierb.start_utc from ops/dashboard.json"),
        "milestones": milestones,
        "batches": batches,
        "totals": {
            "generation_usd": round(sum(b["cost_usd"] for b in gen_batches), 4),
            "generation_batches": len(gen_batches),
            "accepted_pairs": sum(b["accepted"] for b in gen_batches
                                  if isinstance(b.get("accepted"), int)),
            "tierb_accepted": sum(b["accepted"] for b in gen_batches
                                  if b.get("tierb") and isinstance(b.get("accepted"), int)),
            "trace_summary_parts": trace_parts,
            "first_utc": batches[0]["utc"] if batches else None,
            "last_utc": batches[-1]["utc"] if batches else None,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out}")
    if args.site:
        site = Path(args.site) / "data" / "timeline.json"
        site.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site}")
    return 0


if __name__ == "__main__":
    main()
