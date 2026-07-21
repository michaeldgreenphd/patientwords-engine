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

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance

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
                entry = {"clinical": clin, "patient": pat}
                spread = row.get("predictive_spread") or {}
                tops = {}
                for panel in ("clinical", "patient"):
                    ranked = spread.get(panel) or []
                    if ranked and isinstance(ranked[0], (list, tuple)) and ranked[0]:
                        tops[panel] = ranked[0][0]
                if tops:
                    entry["top"] = tops
                pairs[int(row["index"])] = entry
        if pairs:
            days[match.group(1)] = pairs
    return days


def day_over_day(days: dict):
    """[{date, prev, max_abs_delta, worst}] for consecutive measured days."""
    deltas = []
    ordered = sorted(days)
    for prev_day, day in zip(ordered, ordered[1:]):
        worst, worst_label = None, None
        top_changes, top_tracked = [], 0
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
                top_now = (panels.get("top") or {}).get(panel)
                top_before = (prev_panels.get("top") or {}).get(panel)
                if top_now is not None and top_before is not None:
                    top_tracked += 1
                    if top_now != top_before:
                        top_changes.append(f"pair {index} {panel}")
        if worst is not None:
            deltas.append({"date": day, "prev": prev_day,
                           "max_abs_delta": round(worst, 6), "worst": worst_label,
                           "top_words_tracked": top_tracked,
                           "top_word_changes": top_changes})
    return deltas


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--out", default="ops/drift_series.json")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="max |delta p| that still counts as stable")
    parser.add_argument("--site", default=None,
                        help="site repo root; also writes data/drift_series.json there")
    args = parser.parse_args()

    days = collect_days(Path(args.trace_root))
    deltas = day_over_day(days)
    breached = [d for d in deltas if d["max_abs_delta"] > args.threshold]
    # first movement as data (audit M8): the earliest day the sentinel moved
    # at all — the methods page's "largest daily delta on the day the drift
    # sentinel first moved" figure. None while every delta is zero.
    first_moved = next((d for d in deltas if d["max_abs_delta"] > 0), None)
    payload = {"pairs_file": "data/simulated/drift_sentinel.json",
               "threshold": args.threshold,
               "days_measured": sorted(days),
               "series": {day: days[day] for day in sorted(days)},
               "deltas": deltas,
               "first_moved": ({"date": first_moved["date"],
                                "max_abs_delta": first_moved["max_abs_delta"]}
                               if first_moved else None),
               "stable": not breached}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload["_provenance"] = provenance("drift_sentinel.py")
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.site:
        site_copy = Path(args.site) / "data" / "drift_series.json"
        site_copy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"site copy -> {site_copy}")

    if not days:
        print("drift sentinel: no runs found")
    elif not deltas:
        print(f"drift sentinel: baseline only ({sorted(days)[-1]}), nothing to compare")
    elif breached:
        worst = max(breached, key=lambda d: d["max_abs_delta"])
        tops = ""
        if worst.get("top_words_tracked"):
            changed = worst.get("top_word_changes") or []
            tops = ("; top words unchanged" if not changed
                    else f"; top words CHANGED: {', '.join(changed)}")
        print(f"drift sentinel: DRIFT max |dp| {worst['max_abs_delta']} at {worst['worst']} "
              f"({worst['prev']} -> {worst['date']}, threshold {args.threshold}{tops})")
    else:
        latest = deltas[-1]
        print(f"drift sentinel: stable, max |dp| {latest['max_abs_delta']} "
              f"({latest['prev']} -> {latest['date']}, {len(days)} days)")


if __name__ == "__main__":
    main()
