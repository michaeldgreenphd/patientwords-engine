#!/usr/bin/env python3
"""Offline UMLS OAC Consumer Health Vocabulary (data/chv/) lookup helper.

Usage:
  python3 drafts/slang_stress_20261120/tools/chv_lookup.py "the runs" "diarrhea" "canker sore"
  python3 drafts/slang_stress_20261120/tools/chv_lookup.py --pair "aphthous ulcer" "canker sore"
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_patient_lexicon import CONCEPTS, INCORRECT, STOP, read_incorrect, read_stop_cuis

CHV_DIR = ROOT / "data" / "chv"
CHV_FILE = CHV_DIR / CONCEPTS


def lookup_terms(terms: list[str]) -> dict[str, list[dict[str, str]]]:
    want = {t.strip().lower() for t in terms if t.strip()}
    incorrect = read_incorrect(CHV_DIR / INCORRECT)
    stop = read_stop_cuis(CHV_DIR / STOP)
    hits: dict[str, list[dict[str, str]]] = {t: [] for t in want}
    with CHV_FILE.open(encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) <= 7:
                continue
            term = row[1].strip().lower()
            if term not in want:
                continue
            cui = row[0].strip()
            disparaged = row[7].strip().lower() == "yes"
            usable = (not disparaged) and ((cui, term) not in incorrect) and (cui not in stop)
            hits[term].append(
                {
                    "cui": cui,
                    "term": row[1].strip(),
                    "chv_preferred": row[2].strip(),
                    "umls_preferred": row[3].strip(),
                    "usable": usable,
                }
            )
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="*", help="Exact terms to look up in data/chv/")
    ap.add_argument("--pair", nargs=2, metavar=("CLINICAL", "LAY"), help="Check shared usable CUI for a pair")
    args = ap.parse_args()
    query = list(args.terms)
    if args.pair:
        query.extend(args.pair)
    if not query:
        ap.error("provide at least one term or --pair CLINICAL LAY")
    res = lookup_terms(query)
    if args.pair:
        c_term, l_term = args.pair[0].strip().lower(), args.pair[1].strip().lower()
        c_cuis = {r["cui"] for r in res.get(c_term, []) if r["usable"]}
        l_cuis = {r["cui"] for r in res.get(l_term, []) if r["usable"]}
        shared = sorted(c_cuis & l_cuis)
        print(
            json.dumps(
                {
                    "clinical": args.pair[0],
                    "lay": args.pair[1],
                    "shared_usable_cuis": shared,
                    "clinical_rows": res.get(c_term, []),
                    "lay_rows": res.get(l_term, []),
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
