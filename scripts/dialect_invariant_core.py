#!/usr/bin/env python3
"""Compute each term's dialect-invariant clinical core from committed renders.

For every sweep item: the baseline panel's clinical-tagged transcoder
features, checked for presence in each framing's panel. Features that appear
under every framing form the invariant core - the part of the model's
clinical representation no dialect shift can knock out. Runs entirely on the
self-contained HTML renders (their tooltip payload carries node identity,
category, mass, and description), so no re-tracing and no API calls.

Usage:
  python scripts/dialect_invariant_core.py trace_out/dialects_<STAMP> \
      --dialects-json ../patientwords/data/dialects.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

_NORM_RE = re.compile(r"\(norm ([0-9.]+)\)")


def panels_from_render(path: str) -> list[list[dict]]:
    html = open(path, encoding="utf-8").read()
    marker = "var DATA="
    at = html.find(marker)
    if at < 0:
        raise ValueError(f"no DATA payload in {path}")
    payload, _ = json.JSONDecoder().raw_decode(html[at + len(marker):])
    return payload


def feature_identity(entry: dict) -> tuple[str, str] | None:
    """(layer, feature) for transcoder features; None for structural nodes."""
    node_id, _, ftype = entry.get("id", "").partition(" · ")
    if "transcoder" not in ftype and "lorsa" not in ftype:
        return None
    parts = node_id.split("_")
    if len(parts) < 3:
        return None
    return parts[0], parts[1]


def norm_mass(entry: dict) -> float:
    m = _NORM_RE.search(entry.get("w", ""))
    return float(m.group(1)) if m else 0.0


def core_for_item(panels: list[list[dict]], top_n: int = 8) -> dict:
    baseline, variants = panels[0], panels[1:]
    base_clinical: dict[tuple[str, str], dict] = {}
    for e in baseline:
        key = feature_identity(e)
        if key and e.get("cat", "").startswith("clinical"):
            prev = base_clinical.get(key)
            if prev is None or norm_mass(e) > norm_mass(prev):
                base_clinical[key] = e
    variant_sets = [
        {feature_identity(e) for e in panel if feature_identity(e)}
        for panel in variants
    ]
    survives = {
        key: sum(1 for vs in variant_sets if key in vs)
        for key in base_clinical
    }
    n_var = len(variant_sets)
    core = [k for k, s in survives.items() if s == n_var]
    ranked = sorted(base_clinical, key=lambda k: -norm_mass(base_clinical[k]))
    top = [
        {
            "feature": f"L{k[0]}/{k[1]}",
            "desc": (base_clinical[k].get("desc") or "")[:110],
            "survives": f"{survives[k]}/{n_var}",
            "norm_mass": norm_mass(base_clinical[k]),
        }
        for k in ranked[:top_n]
    ]
    return {
        "baseline_clinical": len(base_clinical),
        "invariant": len(core),
        "framings": n_var,
        "top": top,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace_dir")
    ap.add_argument("--dialects-json", required=True,
                    help="frontend data/dialects.json to augment in place")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    cores: dict[int, dict] = {}
    for path in sorted(glob.glob(os.path.join(args.trace_dir, "index_*.html"))):
        stem = os.path.basename(path)
        m = re.match(r"index_(\d+)\.html$", stem)
        if not m:
            continue  # edge views etc.
        idx = int(m.group(1))
        try:
            cores[idx] = core_for_item(panels_from_render(path), args.top)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"skip {stem}: {e}", file=sys.stderr)

    with open(args.dialects_json, encoding="utf-8") as f:
        data = json.load(f)
    hit = 0
    for item in data.get("items", []):
        core = cores.get(item.get("index"))
        if core:
            item["core"] = core
            hit += 1
    with open(args.dialects_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    for idx in sorted(cores):
        c = cores[idx]
        print(f"item {idx}: {c['invariant']}/{c['baseline_clinical']} clinical features "
              f"survive all {c['framings']} framings")
    print(f"augmented {hit} items in {args.dialects_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
