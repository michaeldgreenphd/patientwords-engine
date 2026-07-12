"""Instrument-drift sentinel: is the hosted tracer stable day over day?

The same 3 reviewed pairs (data/simulated/drift_sentinel.json, frozen) are
re-traced daily through dated alias stems (drift_sentinel_YYYYMMDD.json ->
trace_out/drift_sentinel_YYYYMMDD/). This script collects every dated run,
compares each day's clinical/patient probabilities against the previous day,
and writes ops/drift_series.json. The printed last line is the daily brief's
sentinel verdict.

Neuronpedia is a hosted service that can change underneath a multi-week study;
a quiet sentinel is evidence the instrument held still for the whole run.
No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIR_PATTERN = re.compile(r"drift_sentinel_(\d{8})$")
DEFAULT_THRESHOLD = 0.01


def collect_days(trace_root: Path):
    """{YYYYMMDD: {pair_index: {"clinical": p, "patient": p}}} from dated dirs."""
    days = {}
    for run_dir in sorted(trace_root.glob("drift_sentinel_*")):
        match = DIR_PATTERN.search(run_dir.name)
        if not match or not run_dir.is_dir():
            continue
        pairs = {}
        for part in sorted(run_dir.glob("batch_summary*.json")):
            try:
                summary = json.loads(part.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for row in summary.get("results", []):
                probs = row.get("probabilities") or {}
                clin, pat = probs.get("clinical"), probs.get("patient")
                if clin is None and pat is None:
                    continue
                pairs[int(row["index"])] = {"clinical": clin, "patient": pat}
        if pairs:
            days[match.group(1)] = pairs
    return days


def day_over_day(days: dict):
    """[{date, prev, max_abs_delta, worst}] for consecutive measured days."""
    deltas = []
    ordered = sorted(days)
    for prev_day, day in zip(ordered, ordered[1:]):
        worst, worst_label = None, None
        for index, panels in days[day].items():
            prev_panels = days[prev_day].get(index)
            if not prev_panels:
                continue
            for panel in ("clinical", "patient"):
                now, before = panels.get(panel), prev_panels.get(panel)
                if now is None or before is None:
                    continue
                delta = abs(float(now) - float(before))
                if worst is None or delta > worst:
                    worst, worst_label = delta, f"pair {index} {panel}"
        if worst is not None:
            deltas.append({"date": day, "prev": prev_day,
                           "max_abs_delta": round(worst, 6), "worst": worst_label})
    return deltas


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--out", default="ops/drift_series.json")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="max |delta p| that still counts as stable")
    args = parser.parse_args()

    days = collect_days(Path(args.trace_root))
    deltas = day_over_day(days)
    breached = [d for d in deltas if d["max_abs_delta"] > args.threshold]
    payload = {"pairs_file": "data/simulated/drift_sentinel.json",
               "threshold": args.threshold,
               "days_measured": sorted(days),
               "series": {day: days[day] for day in sorted(days)},
               "deltas": deltas,
               "stable": not breached}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not days:
        print("drift sentinel: no runs found")
    elif not deltas:
        print(f"drift sentinel: baseline only ({sorted(days)[-1]}), nothing to compare")
    elif breached:
        worst = max(breached, key=lambda d: d["max_abs_delta"])
        print(f"drift sentinel: DRIFT max |dp| {worst['max_abs_delta']} at {worst['worst']} "
              f"({worst['prev']} -> {worst['date']}, threshold {args.threshold})")
    else:
        latest = deltas[-1]
        print(f"drift sentinel: stable, max |dp| {latest['max_abs_delta']} "
              f"({latest['prev']} -> {latest['date']}, {len(days)} days)")


if __name__ == "__main__":
    main()
