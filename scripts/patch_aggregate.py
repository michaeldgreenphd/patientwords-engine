"""P3: aggregate activation-patching recovery grids into a per-layer profile.

Reads every ``trace_out/<stem>__patch/batch_summary.part_*.json`` and answers
the two pre-registered questions from the patching design
(docs/activation_patching_design.md): at which LAYERS does patching the
everyday run with the clinical state restore the answer, and does the effect
sit at the wording-swap site or downstream?

Screens (recorded, never silent):
- inverted pairs (clean_prob <= corrupt_prob): the normalized-recovery
  denominator is meaningless there (the 2026-07-11 chunk-1 seam);
- all-null grids (nothing was patchable).

Position vocabulary: the grid is defined over the corrupt run's positions and
only aligned suffix positions carry values; the divergent (swapped) span is
never patchable. "term_adjacent" = the FIRST aligned position after the
divergence, the closest patchable cell to the swap site; "downstream" = every
later position. The split is exploratory and defined here, before any batch
is read.

Usage:
  python scripts/patch_aggregate.py --stem urgency_downgrades_20260707T1
      [--out data/patch_profile.json] [--site ../patientwords]

No medical vocabulary lives in this file.
"""

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path


def load_pairs(stem):
    """Per-pair patching blocks from every part file, keyed by index."""
    pairs = {}
    for part in sorted(glob.glob(f"trace_out/{stem}__patch/batch_summary.part_*.json")):
        summary = json.loads(Path(part).read_text(encoding="utf-8"))
        for r in summary.get("results", []):
            if "patching" in r:
                pairs[r["index"]] = r["patching"]
    return pairs


def screen(patching):
    """Reason string when a grid cannot enter the aggregate, else None."""
    clean, corrupt = patching.get("clean_prob"), patching.get("corrupt_prob")
    if clean is None or corrupt is None or clean <= corrupt:
        return f"inverted (clean={clean}, corrupt={corrupt})"
    grid = patching.get("recovery") or []
    if not any(v is not None for row in grid for v in row):
        return "all-null grid"
    return None


def patched_columns(grid):
    """Sorted position indices that carry at least one value."""
    cols = set()
    for row in grid:
        cols.update(i for i, v in enumerate(row) if v is not None)
    return sorted(cols)


def per_layer_max(grid):
    """Max recovery over positions, per layer; None where a layer is empty."""
    out = []
    for row in grid:
        vals = [v for v in row if v is not None]
        out.append(max(vals) if vals else None)
    return out


def aggregate(pairs):
    """Profile + term-adjacent split across the unscreened pairs."""
    used, screened = {}, {}
    for idx, p in sorted(pairs.items()):
        reason = screen(p)
        if reason:
            screened[idx] = reason
        else:
            used[idx] = p

    layer_lists = {}
    per_pair = []
    best_site = {"term_adjacent": 0, "downstream": 0}
    for idx, p in used.items():
        grid = p["recovery"]
        cols = patched_columns(grid)
        first = cols[0]
        pl = per_layer_max(grid)
        for layer, v in enumerate(pl):
            if v is not None:
                layer_lists.setdefault(layer, []).append(v)
        best = max(((v, layer, col) for layer, row in enumerate(grid)
                    for col, v in enumerate(row) if v is not None))
        term_best = max((v for row in grid for i, v in enumerate(row)
                         if v is not None and i == first), default=None)
        down_best = max((v for row in grid for i, v in enumerate(row)
                         if v is not None and i > first), default=None)
        site = "term_adjacent" if best[2] == first else "downstream"
        best_site[site] += 1
        per_pair.append({
            "index": idx,
            "best": {"recovery": round(best[0], 3), "layer": best[1],
                     "position": best[2], "site": site},
            "term_adjacent_best": None if term_best is None else round(term_best, 3),
            "downstream_best": None if down_best is None else round(down_best, 3),
        })

    profile = [
        {"layer": layer, "mean_max_recovery": round(sum(vs) / len(vs), 3), "n": len(vs)}
        for layer, vs in sorted(layer_lists.items())
    ]
    return {
        "pairs_used": sorted(used),
        "pairs_screened": {str(k): v for k, v in sorted(screened.items())},
        "per_layer": profile,
        "best_cell_site": best_site,
        "per_pair": per_pair,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stem", required=True)
    parser.add_argument("--out", default="data/patch_profile.json")
    parser.add_argument("--site", default="", help="frontend repo root; '' skips the site copy")
    args = parser.parse_args(argv)

    pairs = load_pairs(args.stem)
    if not pairs:
        print(f"refused: no patching parts under trace_out/{args.stem}__patch/")
        return 3
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stem": args.stem,
        "metric": ("normalized recovery (p_patched - p_corrupt) / (p_clean - p_corrupt), "
                   "max over positions per layer; exploratory"),
        "term_adjacent_rule": ("first aligned position after the divergent span; "
                               "the swapped span itself is never patchable"),
    }
    payload.update(aggregate(pairs))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out} ({len(payload['pairs_used'])} pairs used, "
          f"{len(payload['pairs_screened'])} screened)")
    if args.site:
        site = Path(args.site) / "data" / "patch_profile.json"
        site.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
