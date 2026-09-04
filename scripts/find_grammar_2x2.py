#!/usr/bin/env python3
"""Step A — source a stronger "swap the grammar" 2x2 for the Wording Differences page.

Scans committed data for a 2x2 (lexicon x grammar) or grammar-only case where the GRAMMAR
shift alone changes the *top* next token, or where all four quadrants land on distinct tops.
Read-only. Run with patientwords/ and patientwords-engine/ as siblings.
"""
import glob
import json
import os

FE = os.environ.get("PW_FE", "/home/user/patientwords")
ENG = os.environ.get("PW_ENG", "/home/user/patientwords-engine")


def top_tok(spread):
    return spread[0][0] if spread else "?"


def scan_4quadrant():
    print("\n=== (1) 2x2 lexicon×grammar batches (engine trace_out) ===")
    hits = []
    for summ in glob.glob(f"{ENG}/trace_out/*/batch_summary*.json"):
        try:
            d = json.load(open(summ))
        except Exception:
            continue
        if not (isinstance(d, dict) and d.get("mode") == "4quadrant"):
            continue
        for r in d.get("results", []):
            sp = r.get("predictive_spread", {})
            tops = {q: top_tok(sp.get(q, [])) for q in "ABCD"}
            if not all(tops.values()):
                continue
            gram_flip = (tops["A"] != tops["B"]) or (tops["C"] != tops["D"])
            distinct = len(set(tops.values()))
            if gram_flip or distinct == 4:
                hits.append((distinct, gram_flip, os.path.basename(os.path.dirname(summ)),
                             r.get("index"), tops))
    if not hits:
        print("  none. committed 4quadrant items keep one top token across the grammar axis.")
    for h in sorted(hits, key=lambda x: (-x[0], -x[1])):
        print(f"  {h[2]} #{h[3]} | distinct_tops={h[0]} grammar_flip={h[1]} | {h[4]}")


def scan_sim_grammar_axis():
    print("\n=== (2) simulated_scenarios.json — grammar axis? ===")
    d = json.load(open(f"{FE}/data/simulated_scenarios.json"))
    keys = set(d.get("scenarios", [{}])[0].keys())
    gram = [k for k in keys if any(t in k for t in ("gramm", "register", "dialect", "morph", "nonstd", "frame"))]
    print(f"  fields hinting a grammar axis: {gram or 'NONE'} -> sim pairs are single-word swaps only.")


def scan_dialect_flips():
    print("\n=== (3) dialects.json — grammar/dialect shift ALONE flips the top (term held constant) ===")
    d = json.load(open(f"{FE}/data/dialects.json"))
    rows = []
    for it in d["items"]:
        distinct = sorted(set(v["top_token"] for v in it["variants"]))
        flips = [v for v in it["variants"] if v.get("flip")]
        if flips:
            rows.append((len(distinct), len(flips), it["index"], it["term"],
                         it["target_token"], it["baseline_prompt"], distinct))
    for r in sorted(rows, key=lambda x: (-x[0], -x[1]))[:10]:
        print(f"  #{r[2]:>2} [{r[3]}] target={r[4]!r} | {r[0]} distinct tops {r[6]} | {r[1]} flips")
        print(f"        base: {r[5]!r}")


if __name__ == "__main__":
    scan_4quadrant()
    scan_sim_grammar_axis()
    scan_dialect_flips()
