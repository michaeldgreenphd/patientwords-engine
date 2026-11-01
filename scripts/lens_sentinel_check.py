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
to compare; exit 3 = the latest reading is incomplete (fewer pairs than the
day's input data/simulated/drift_sentinel_<date>.json asked for, an unreadable
input, or a side that failed to parse) and no complete reading that day shows
a step: no verdict. Incomplete readings stay on disk and are listed in the
series file, but never enter a comparison; a step in another model's complete
reading that day is still a DRIFT exit 1, with the incomplete one noted.
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


def _status_ok(status) -> bool:
    """A pair's parse_status: per-side dict, one string, or absent (pre-status readouts)."""
    if status is None:
        return True
    if isinstance(status, dict):
        return bool(status) and all(v == "ok" for v in status.values())
    return status == "ok"


def _fingerprint(run_dir: Path):
    """(canonical-json, target_rank_hits, layers_read, n_pairs, all_ok) for one dated readout.

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
    n_pairs = len({row.get("index") for row in rows})
    all_ok = all(_status_ok(row.get("parse_status")) for row in rows)
    return json.dumps(rows, sort_keys=True), hits, layers, n_pairs, all_ok


def expected_pairs(pairs_root: Path, date: str) -> int | None:
    """How many pairs the day's sentinel input asked for (data/simulated/drift_sentinel_<date>.json), or None when
    the input is missing or unreadable. Taken from the input, never from the outputs, which may themselves have
    failed (Codex on engine#143: a majority of partial days must not redefine complete)."""
    try:
        pairs = json.loads((pairs_root / f"drift_sentinel_{date}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return len(pairs) if isinstance(pairs, list) else None


def split_incomplete(days: dict, pairs_root: Path):
    """(complete_days, incomplete) — a reading is complete when it covers every pair the day's sentinel input
    asked for and every pair parsed on both sides; a day whose input cannot be read is incomplete. The workflow
    commits outputs even when a readout fails partway, so a partial reading must not enter any comparison: as the
    latest day it would read as a step, and as history it would make the next complete day read as one (Codex on
    engine#143)."""
    complete, incomplete = {}, {}
    for model, by_date in days.items():
        for date, fp in by_date.items():
            expected = expected_pairs(pairs_root, date)
            if expected is not None and fp[3] == expected and fp[4]:
                complete.setdefault(model, {})[date] = fp
            else:
                incomplete.setdefault(model, {})[date] = {"pairs": fp[3], "expected_pairs": expected,
                                                           "all_parsed": fp[4]}
    return complete, incomplete


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
    parser.add_argument("--pairs-root", default="data/simulated",
                        help="where the dated sentinel inputs drift_sentinel_<date>.json live")
    args = parser.parse_args()

    every = collect(Path(args.trace_root))
    if not every:
        print("lens sentinel: no dated lens readouts found")
        return 2
    days, incomplete = split_incomplete(every, Path(args.pairs_root))
    latest_any = max(date for by_date in every.values() for date in by_date)

    per_model = steps(days)
    agreement = cross_host(days)
    all_dates = sorted({date for by_date in days.values() for date in by_date})
    latest = all_dates[-1] if all_dates else None

    payload = {"pairs_file": "data/simulated/drift_sentinel.json",
               "models": sorted(days),
               "days_measured": all_dates,
               "per_model": per_model,
               "cross_host_identical": agreement,
               "incomplete": incomplete,
               "_provenance": provenance("lens_sentinel_check.py")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    late = {model: by_date[latest_any] for model, by_date in incomplete.items() if latest_any in by_date}
    late_note = ("; INCOMPLETE on " + latest_any + ": " + "; ".join(
        f"{model} {info['pairs']}/{info['expected_pairs'] if info['expected_pairs'] is not None else '?'} pairs"
        f"{'' if info['all_parsed'] else ', a side failed to parse'}" for model, info in late.items())) if late else ""

    # A step in any COMPLETE reading on the latest day is reported even when another model's reading that day is
    # incomplete: suppressing it would let the step pass into history unannounced (Codex on engine#143).
    new_steps = [(model, move) for model, info in per_model.items()
                 for move in info["steps"] if move["date"] == latest_any]
    all_steps = [(model, move) for model, info in per_model.items() for move in info["steps"]]

    if new_steps:
        detail = "; ".join(
            f"{model} {move['prev']} -> {move['date']} "
            f"(target-rank hits {move['target_rank_hits_prev']} -> {move['target_rank_hits']})"
            for model, move in new_steps)
        print(f"lens sentinel: DRIFT on {latest_any} — {detail}{late_note}")
        return 1
    if late:
        print(f"lens sentinel: no verdict for {latest_any}{late_note} (an incomplete measurement, not a lens step)")
        return 3

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
