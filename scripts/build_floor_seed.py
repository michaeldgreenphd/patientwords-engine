"""Build the dedicated seed file for a paraphrase-floor expansion fire.

Binding condition 4 of docs/expansion_plan_20260722.md: the dialect-baselines
generator takes the first num_baselines usable seed pairs with NO dedup against
landed batches, so every expansion fire uses a committed seed file whose pairs
already exclude (a) every baseline_prompt used by any landed dialects_* batch
and (b) the Tier B holdout (phrase-keyed seal; scripts/tierb_split.py is the
single implementation - never reimplement the hash). Usability mirrors the
generator's own precheck (clean swap span), so "first N usable" equals
"first N" on this file. The seed is a bare JSON array (the generator's loader
requires that); exclusion counts land in a .meta.json sidecar for the fire note.

Usage:
  python scripts/build_floor_seed.py --out data/seeds/floor_seed_<STAMP>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from medlang_circuits.scenario_gen import _swap_span  # noqa: E402
from tierb_split import holdout_phrases, tierb_start_stamp  # noqa: E402


def _norm(s: str) -> str:
    return " ".join(str(s).split()).lower()


def usable(pair: dict) -> bool:
    phrase = str(pair.get("top_prompt") or "").strip()
    other = str(pair.get("bottom_prompt") or "").strip()
    if not phrase or not other:
        return False
    term = _swap_span(phrase, other)
    return bool(term) and term != phrase and len(term) >= 3 and term in phrase


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--simulated", default="data/simulated")
    parser.add_argument("--min-usable", type=int, default=60,
                        help="refuse to write a seed thinner than this (headroom over num_baselines)")
    args = parser.parse_args(argv)

    if not tierb_start_stamp():
        print("refused: sealed set computes empty (null tierb.start_utc - wrong branch?)")
        return 2
    sealed = {_norm(p) for p in holdout_phrases(args.simulated)}
    if not sealed:
        print("refused: holdout_phrases returned empty - not a valid state on the ops branch")
        return 2

    sim = Path(args.simulated)
    used = set()
    for f in sorted(sim.glob("dialects_*.json")):
        if f.name.endswith(".report.json"):
            continue
        batch = json.loads(f.read_text(encoding="utf-8"))
        rows = batch if isinstance(batch, list) else batch.get("items", [])
        for r in rows:
            if isinstance(r, dict) and r.get("baseline_prompt"):
                used.add(_norm(r["baseline_prompt"]))

    seeds, seen = [], set()
    excluded = {"holdout": 0, "used_baseline": 0, "unusable": 0, "duplicate": 0}
    sources = []
    for f in sorted(sim.glob("pairs_*.json")):
        if f.name.endswith(".report.json"):
            continue
        batch = json.loads(f.read_text(encoding="utf-8"))
        rows = batch if isinstance(batch, list) else batch.get("items", [])
        took = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            key = _norm(r.get("top_prompt") or "")
            if not key:
                excluded["unusable"] += 1
                continue
            if key in sealed:
                excluded["holdout"] += 1
                continue
            if key in used:
                excluded["used_baseline"] += 1
                continue
            if key in seen:
                excluded["duplicate"] += 1
                continue
            if not usable(r):
                excluded["unusable"] += 1
                continue
            seen.add(key)
            seeds.append({"top_prompt": r["top_prompt"], "bottom_prompt": r["bottom_prompt"]})
            took += 1
        if took:
            sources.append({"batch": f.name, "pairs": took})

    # the mechanical assert the binding condition requires
    assert not any(_norm(p["top_prompt"]) in sealed for p in seeds), "holdout leaked into seed"
    if len(seeds) < args.min_usable:
        print(f"refused: only {len(seeds)} usable seeds after exclusions (< {args.min_usable})")
        return 3

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seeds, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    meta = {"n_seeds": len(seeds), "excluded": excluded, "sources": sources,
            "sealed_phrases_checked": len(sealed), "used_baselines_checked": len(used)}
    Path(str(out).replace(".json", ".meta.json")).write_text(
        json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(seeds)} seeds -> {out}")
    print(f"excluded: {excluded} (sealed set n={len(sealed)}, used baselines n={len(used)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
