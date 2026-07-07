#!/usr/bin/env python3
"""Export a dialect-sweep trace into the frontend's data/dialects.json.

Reads every batch_summary.part_*.json under trace_out/<batch>/ and emits one
compact JSON: per baseline term, the baseline probability plus each framing's
probability, delta, and top prediction (with a flip flag when the top pick
moved off the baseline's target). Also lists each item's render file so the
frontend can link per-term standalone pages.

Usage:
  python scripts/export_dialect_matrix.py trace_out/dialects_<STAMP> \
      --out ../patientwords/data/dialects.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

_OUTPUT_RE = re.compile(r'^Output\s+"(.*)"$', re.S)


def bare(label: str | None) -> str:
    if not label:
        return ""
    m = _OUTPUT_RE.match(label.strip())
    return (m.group(1) if m else label).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace_dir", help="trace_out/<dialects batch> directory")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--updated", default=None, help="ISO date stamp for the export")
    args = ap.parse_args()

    parts = sorted(glob.glob(os.path.join(args.trace_dir, "batch_summary.part_*.json")))
    if not parts:
        print(f"no batch_summary parts under {args.trace_dir}", file=sys.stderr)
        return 1

    items = []
    graph_model = source_set = None
    for part in parts:
        with open(part, encoding="utf-8") as f:
            summary = json.load(f)
        graph_model = summary.get("graph_model") or graph_model
        source_set = summary.get("source_set") or source_set
        for r in summary.get("results", []):
            baseline_p = r.get("baseline_probability")
            target_bare = bare(r.get("target_token"))
            spread_variants = (r.get("predictive_spread") or {}).get("variants") or []
            variants = []
            for i, v in enumerate(r.get("variants", [])):
                spread = spread_variants[i] if i < len(spread_variants) else []
                top_token, top_p = (spread[0] if spread else (None, None))
                variants.append({
                    "dialect": v.get("dialect"),
                    "prompt": v.get("prompt"),
                    "p": v.get("probability"),
                    "delta": v.get("delta_vs_baseline"),
                    "top_token": bare(top_token),
                    "top_p": top_p,
                    "flip": bool(top_token) and bare(top_token) != target_bare,
                })
            render = os.path.basename((r.get("outputs") or {}).get("html") or "")
            items.append({
                "index": r.get("index"),
                "term": r.get("term"),
                "baseline_prompt": r.get("baseline_prompt"),
                "target_token": target_bare,
                "baseline_p": baseline_p,
                "render": render,
                "variants": variants,
            })

    items.sort(key=lambda it: it.get("index") or 0)
    batch = os.path.basename(os.path.normpath(args.trace_dir))
    payload = {
        "updated": args.updated,
        "batch": batch,
        "graph_model": graph_model,
        "source_set": source_set,
        "items": items,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    flips = sum(1 for it in items for v in it["variants"] if v["flip"])
    cells = sum(len(it["variants"]) for it in items)
    print(f"exported {len(items)} baselines, {cells} framing cells, {flips} top-pick flips -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
