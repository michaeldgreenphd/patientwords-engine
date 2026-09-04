"""Internals-drift sentinel: did the hosted j-lens readout change under us?

The output-drift sentinel (drift_sentinel.py) watches next-token probabilities.
This is its internals counterpart: the same 3 reviewed pairs are re-read daily
through the hosted Jacobian lens for both served host ids
(trace_out/drift_sentinel_YYYYMMDD__jlens_<model>/), and this script compares
every dated readout against BOTH neighbours it can drift away from:

  * the previous measured day for the same host id (day-over-day), and
  * the day-1 baseline for the same host id (cumulative).

It also reports whether the two served host ids agree with each other on each
day. `docs/routine_standing_prompt.md` §3d recorded the two ids as returning
byte-identical readouts and treated the day they diverge as the day Neuronpedia
separates the hosts; nothing computed that comparison, so the separation
(2026-07-31) and a later joint step (2026-08-14) both went unreported for
weeks. Every daily cycle's per-host day-over-day reading was individually
true and collectively blind — hence this check.

No medical vocabulary lives in this file. $0, offline, read-only.

Exit 0 = no new step since the previous measured day; exit 1 = a step landed
on the latest day (the DRIFT headline the brief must carry); exit 2 = nothing
to compare.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance

DIR_PATTERN = re.compile(r"drift_sentinel_(\d{8})__jlens_(.+)$")


def _fingerprint(run_dir: Path):
    """(canonical-json, target_rank_hits, layers_read) for one dated readout.

    The canonical form drops nothing from `results`: a host-side change to any
    per-layer top1 token is exactly the signal we are watching for. Summary
    metadata (generated_utc and friends) is excluded by only reading `results`.
    """
    rows = []
    for part in sorted(run_dir.glob("jlens_summary*.json")):
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.extend(summary.get("results", []))
    if not rows:
        return None
    hits = layers = 0
    for row in rows:
        for side in ("clinical", "patient"):
            for layer in (row.get("depth") or {}).get(side, []):
                layers += 1
                if layer.get("target_rank") is not None:
                    hits += 1
    return json.dumps(rows, sort_keys=True), hits, layers


def collect(trace_root: Path):
    """{model_id: {YYYYMMDD: (fingerprint, hits, layers)}} from dated lens dirs."""
    days: dict[str, dict[str, tuple]] = {}
    for run_dir in sorted(trace_root.glob("drift_sentinel_*__jlens_*")):
        match = DIR_PATTERN.search(run_dir.name)
        if not match or not run_dir.is_dir():
            continue
        date, model = match.group(1), match.group(2)
        fingerprint = _fingerprint(run_dir)
        if fingerprint:
            days.setdefault(model, {})[date] = fingerprint
    return days


def steps(days: dict):
    """Per host id, the dates whose readout differs from the previous day."""
    found = {}
    for model, by_date in days.items():
        ordered = sorted(by_date)
        moves = []
        for prev_day, day in zip(ordered, ordered[1:]):
            before, now = by_date[prev_day], by_date[day]
            if before[0] != now[0]:
                moves.append({"date": day, "prev": prev_day,
                              "target_rank_hits": now[1],
                              "target_rank_hits_prev": before[1],
                              "layers_read": now[2]})
        found[model] = {"days_measured": ordered, "steps": moves,
                        "baseline": ordered[0] if ordered else None,
                        "matches_baseline": bool(ordered) and by_date[ordered[-1]][0] == by_date[ordered[0]][0]}
    return found


def cross_host(days: dict):
    """Per date, whether every served host id returned the same readout."""
    dates = sorted({date for by_date in days.values() for date in by_date})
    agreement = {}
    for date in dates:
        seen = {model: by_date[date][0] for model, by_date in days.items() if date in by_date}
        if len(seen) < 2:
            continue
        agreement[date] = len(set(seen.values())) == 1
    return agreement


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--out", default="ops/lens_sentinel_series.json")
    args = parser.parse_args()

    days = collect(Path(args.trace_root))
    if not days:
        print("lens sentinel: no dated lens readouts found")
        return 2

    per_model = steps(days)
    agreement = cross_host(days)
    all_dates = sorted({date for by_date in days.values() for date in by_date})
    latest = all_dates[-1]

    payload = {"pairs_file": "data/simulated/drift_sentinel.json",
               "models": sorted(days),
               "days_measured": all_dates,
               "per_model": per_model,
               "cross_host_identical": agreement,
               "_provenance": provenance("lens_sentinel_check.py")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    new_steps = [(model, move) for model, info in per_model.items()
                 for move in info["steps"] if move["date"] == latest]
    all_steps = [(model, move) for model, info in per_model.items() for move in info["steps"]]

    if new_steps:
        detail = "; ".join(
            f"{model} {move['prev']} -> {move['date']} "
            f"(target-rank hits {move['target_rank_hits_prev']} -> {move['target_rank_hits']})"
            for model, move in new_steps)
        print(f"lens sentinel: DRIFT on {latest} — {detail}")
        return 1

    history = (f"; {len(all_steps)} historical step(s): "
               + ", ".join(f"{model}@{move['date']}" for model, move in all_steps)) if all_steps else ""
    split = [date for date, same in agreement.items() if not same]
    hosts = ""
    if agreement:
        hosts = ("; served host ids agree on every measured day" if not split
                 else f"; served host ids DIVERGE since {min(split)} ({len(split)}/{len(agreement)} days)")
    print(f"lens sentinel: no new step on {latest} ({len(all_dates)} days){history}{hosts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
