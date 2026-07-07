"""Paired cross-model statistics on the unified phrase set, plus instrument validity.

Consumes the row file written by scripts/urgency_shift.py (one row per
phrase x model, carrying language_penalty and tier_shift) and produces the
publication-grade comparisons:

1. UNIFIED SET - restrict to phrases measured on every requested model (the
   gemma rows exist only where screening passed, so the intersection is the
   clean head-to-head set). Report per-model means with bootstrap 95% CIs and
   PAIRED per-phrase differences between models (same phrases, so the pairing
   removes phrase-level variance).
2. VALIDITY - when a live trace of the hand-measured pairs exists
   (trace_out/<stem of --hand-pairs>/), correlate the live-traced language
   penalty against the hand-measured penalty recorded in each pair's
   provenance block (observed_prob patient - clinical). Pearson and Spearman,
   computed exactly (no scipy).

Usage:
  python scripts/urgency_shift.py --out urgency_shift.json   # collector first
  python scripts/paired_stats.py --rows urgency_shift.json
      [--models gemma-2-2b qwen3-4b qwen3-1.7b] [--boot 10000] [--seed 7]
      [--hand-pairs data/measured/imported_pairs.json]
"""

import argparse
import glob
import json
import math
import random
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--rows", default="urgency_shift.json")
parser.add_argument("--models", nargs="+",
                    default=["gemma-2-2b", "qwen3-4b", "qwen3-1.7b"])
parser.add_argument("--boot", type=int, default=10000)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--hand-pairs", default="data/measured/imported_pairs.json")
parser.add_argument("--out", default="paired_stats.json")
args = parser.parse_args()

rng = random.Random(args.seed)


def boot_ci(values, n=None):
    """Mean and bootstrap 95% CI (percentile method)."""
    if not values:
        return None
    n = n or args.boot
    means = []
    for _ in range(n):
        sample = [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return {
        "mean": round(sum(values) / len(values), 4),
        "ci95": [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)],
        "n": len(values),
    }


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 4)


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    return pearson(ranks(xs), ranks(ys))


data = json.loads(Path(args.rows).read_text(encoding="utf-8"))
by_phrase = {}
for r in data["rows"]:
    by_phrase.setdefault((r["batch"], r["index"]), {})[r["model"]] = r

unified = {k: v for k, v in by_phrase.items()
           if all(m in v and isinstance(v[m].get("language_penalty"), (int, float))
                  for m in args.models)}

out = {"unified_set": {"models": args.models, "phrases": len(unified)},
       "per_model": {}, "paired_differences": {}, "validity": None}

for m in args.models:
    pens = [v[m]["language_penalty"] for v in unified.values()]
    tss = [v[m]["tier_shift"] for v in unified.values()
           if isinstance(v[m].get("tier_shift"), (int, float))]
    out["per_model"][m] = {
        "language_penalty": boot_ci(pens),
        "tier_shift": boot_ci(tss),
        "flip_rate": round(sum(1 for v in unified.values() if v[m]["flipped"]) /
                           len(unified), 3) if unified else None,
    }

for i, a in enumerate(args.models):
    for b in args.models[i + 1:]:
        diffs = [v[a]["language_penalty"] - v[b]["language_penalty"]
                 for v in unified.values()]
        out["paired_differences"][f"{a} - {b}"] = boot_ci(diffs)

# --- validity: live-traced penalty vs hand-measured penalty -----------------
hand = Path(args.hand_pairs)
if hand.is_file():
    stem = hand.stem
    results = {}
    for part in sorted(glob.glob(f"trace_out/{stem}/batch_summary.part_*.json")):
        summary = json.loads(Path(part).read_text(encoding="utf-8"))
        for r in summary.get("results", []):
            results[r["index"]] = r
    pairs = json.loads(hand.read_text(encoding="utf-8"))
    live, handv, matched = [], [], []
    for i, pair in enumerate(pairs, start=1):
        prov = pair.get("provenance") or {}
        po = (prov.get("patient") or {}).get("observed_prob")
        co = (prov.get("clinical") or {}).get("observed_prob")
        r = results.get(i)
        lp = (r or {}).get("language_penalty")
        if isinstance(po, (int, float)) and isinstance(co, (int, float)) \
                and isinstance(lp, (int, float)):
            live.append(lp)
            handv.append(round(po - co, 4))
            matched.append(i)
    out["validity"] = {
        "hand_pairs_file": str(hand), "traced": len(results), "matched": len(matched),
        "pearson_r": pearson(live, handv), "spearman_rho": spearman(live, handv),
        "note": ("live trace of the hand-measured pairs not found in trace_out/ - "
                 "fire a 2panel trace of the file first") if not results else
                "penalty = patient - clinical on the same target token, both scales",
    }

Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
print(json.dumps(out, indent=1))
