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


def stem(token) -> str:
    """First 3 chars, trimmed + lowercased; missing tokens map to '' (the
    page's `String(t||'')` guard — audit M3 verified-spec minor correction)."""
    return str(token or "").strip().lower()[:3]


def specimen_stats(item: dict) -> dict:
    """cross_flips / flips_total / spread for one dialect item, exactly as the
    home-page specimen picker computes them (audit M3 rules 1-2)."""
    variants = item.get("variants") or []
    tstem = stem(item.get("target_token"))
    cross = sum(1 for v in variants
                if v.get("flip") and stem(v.get("top_token")) != tstem)
    flips = sum(1 for v in variants if v.get("flip"))
    spread = max([abs(v.get("delta") or 0) for v in variants] + [0])
    return {"cross_flips": cross, "flips_total": flips, "spread": round(spread, 6)}


def featured_specimen(items: list[dict], show_n: int = 4):
    """The home dialect-variance specimen pick + its displayed variants.

    Item pick: sort descending by (cross_flips, flips_total, spread), stable so
    file order breaks ties. Shown variants: weight 2 for cross-answer flips,
    1 for flips, 0 otherwise; ties by |delta| descending; top `show_n`.
    """
    if not items:
        return None
    stats = [specimen_stats(it) for it in items]
    order = sorted(range(len(items)),
                   key=lambda i: (-stats[i]["cross_flips"], -stats[i]["flips_total"],
                                  -stats[i]["spread"]))
    pick = order[0]
    it = items[pick]
    tstem = stem(it.get("target_token"))

    def weight(v):
        if v.get("flip") and stem(v.get("top_token")) != tstem:
            return 2
        return 1 if v.get("flip") else 0

    variants = sorted(it.get("variants") or [],
                      key=lambda v: (-weight(v), -abs(v.get("delta") or 0)))
    return {"item": pick,
            "show_variants": [v.get("dialect") for v in variants[:show_n]],
            "stats": stats[pick]}


def function_word_set(vocab_path):
    """Function-word target vocabulary from the site's display_vocab.json
    (single definition, shared with the page); None when unavailable."""
    try:
        with open(vocab_path, encoding="utf-8") as f:
            tokens = json.load(f)["function_word_targets"]["tokens"]
        return {str(t).strip().lower() for t in tokens}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def classify_function_targets(items: list[dict], func_words: set) -> None:
    """Mark each item whose target is a function word (audit M5): those rows
    measure the sentence frame, not the clinical concept, and leave the
    headline flip count. Exact case-insensitive match on the trimmed token."""
    for it in items:
        tok = str(it.get("target_token") or "").strip().lower()
        it["target_is_function"] = tok in func_words


def headline_counts(items: list[dict]) -> dict:
    """The matrix page's headline tallies: framing cells, concept-target
    flips, and function-word-target flips (kept out of the headline)."""
    cells = concept = func = 0
    for it in items:
        isf = bool(it.get("target_is_function"))
        for v in it.get("variants") or []:
            cells += 1
            if v.get("flip"):
                if isf:
                    func += 1
                else:
                    concept += 1
    return {"cells": cells, "flips": concept, "func_flips": func}


def featured_term(items: list[dict], pattern: str | None):
    """The dialect-differences featured-term pick: first item whose term
    matches the pins-file pattern (case-insensitive substring, mirroring the
    page's regex), items[0] fallback — the term string itself stays in data."""
    if not items:
        return None
    pick = 0
    if pattern:
        needle = pattern.lower()
        for i, it in enumerate(items):
            if needle in str(it.get("term") or "").lower():
                pick = i
                break
    return {"item": pick, "term": items[pick].get("term")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace_dir", help="trace_out/<dialects batch> directory")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--updated", default=None, help="ISO date stamp for the export")
    ap.add_argument("--pins",
                    default=os.path.join(os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__))), "data", "editorial_pins.json"),
                    help="editorial pins file (dialect_featured_term_pattern)")
    ap.add_argument("--vocab", default=None,
                    help="display_vocab.json path (default: alongside --out)")
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
    # function-word target classification + headline tallies as data (audit
    # M5): vocabulary comes from the site's display_vocab.json, never this
    # script. The page keeps its inline FUNC set + counting as fallback.
    vocab_path = args.vocab or os.path.join(os.path.dirname(args.out),
                                            "display_vocab.json")
    fw = function_word_set(vocab_path)
    if fw is not None:
        classify_function_targets(items, fw)
        payload["headline"] = headline_counts(items)

    # featured picks as data (audit M3 tail): the home specimen is computed,
    # the featured-term pattern comes from the pins data file (vocabulary
    # never lives in this script). Pages keep their in-JS picks as fallback.
    spec = featured_specimen(items)
    if spec:
        payload["featured_specimen"] = spec
    try:
        with open(args.pins, encoding="utf-8") as f:
            pattern = json.load(f).get("dialect_featured_term_pattern")
    except (OSError, ValueError):
        pattern = None
    term = featured_term(items, pattern)
    if term:
        payload["featured_term"] = term
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    flips = sum(1 for it in items for v in it["variants"] if v["flip"])
    cells = sum(len(it["variants"]) for it in items)
    print(f"exported {len(items)} baselines, {cells} framing cells, {flips} top-pick flips -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
