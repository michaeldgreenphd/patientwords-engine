"""Derive a reviewable patient-language lexicon from the OAC CHV flatfiles.

Input: the Open Access Consumer Health Vocabulary distribution the owner
placed under data/chv/ (concepts+terms flatfile plus its two published
exclusion lists). Output: data/patient_lexicon.draft.json - lay phrase ->
clinical name mappings ranked by CHV's own familiarity scores, capped to a
reviewable size. The draft is exactly that: stimulus validity is judged by
the study's doctors and linguist, not by this script and not by an LLM.

Flatfile columns (CHV 20110204, 15 tab-separated fields, no header):
  0 CUI · 1 term · 2 CHV preferred name · 3 UMLS preferred name ·
  4 explanation · 5 UMLS-preferred flag · 6 CHV-preferred flag ·
  7 disparaged flag · 8 frequency score · 9 context score · 10 CUI score ·
  11 term score · 12 combo score · 13-14 ids.  Missing scores are -1.

No medical vocabulary lives in this file; terms stay in the data files.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

CHV_DIR = Path("data/chv")
CONCEPTS = "CHV_concepts_terms_flatfile_20110204.tsv"
STOP = "stop_concepts_flat_file_2005-Dec-19.tsv"
INCORRECT = "incorrect_mappings_flat_file_2006-Aug-15.tsv"

CITATION = ("Zeng QT, Tse T. Exploring and developing consumer health vocabularies. "
            "J Am Med Inform Assoc. 2006;13(1):24-9. Open Access Collaborative (OAC) CHV "
            "flatfile release 2011-02-04.")


def read_stop_cuis(path: Path) -> set:
    """CUIs the CHV maintainers marked as not consumer-health concepts."""
    cuis = set()
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        for i, row in enumerate(csv.reader(f, delimiter="\t")):
            if not row or (i == 0 and row[0].strip().upper() == "CUI"):
                continue
            cuis.add(row[0].strip().rstrip("\r"))
    return cuis


def read_incorrect(path: Path) -> set:
    """(CUI, lowercased term) pairs published as incorrect mappings."""
    pairs = set()
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        for i, row in enumerate(csv.reader(f, delimiter="\t")):
            if len(row) < 3 or (i == 0 and row[0].strip().upper() == "CUI"):
                continue
            pairs.add((row[0].strip(), row[2].strip().lower()))
    return pairs


def normalize(term: str) -> str:
    """Collapse case/punctuation/trailing plural so trivial variants match."""
    t = "".join(ch for ch in term.lower() if ch.isalnum() or ch == " ").strip()
    if t.endswith("s"):
        t = t[:-1]
    if t.endswith("ie"):  # bodies -> bodie -> body
        t = t[:-2] + "y"
    return t


def edit_distance_le2(a: str, b: str) -> int | None:
    """Levenshtein distance if <= 2, else None (banded, cheap for 158k rows)."""
    if abs(len(a) - len(b)) > 2:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > 2:
            return None
        prev = cur
    return prev[-1] if prev[-1] <= 2 else None


def score(value: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return -1.0
    return v


def build(chv_dir: Path, top: int):
    stop_cuis = read_stop_cuis(chv_dir / STOP)
    incorrect = read_incorrect(chv_dir / INCORRECT)
    best_per_cui: dict[str, dict] = {}
    misspellings: list[dict] = []
    rows = kept = 0
    with (chv_dir / CONCEPTS).open(encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 13:
                continue
            rows += 1
            cui, term, chv_pref, umls_pref = (row[0].strip(), row[1].strip(),
                                              row[2].strip(), row[3].strip())
            disparaged = row[7].strip().lower() == "yes"
            combo = score(row[12])
            frequency = score(row[8])
            if not cui or not term or not umls_pref:
                continue
            if cui in stop_cuis or (cui, term.lower()) in incorrect:
                continue
            # real observed misspellings: a consumer term a 1-2 character edit
            # from its own concept's CHV preferred name, beyond case/plural
            # trivia. These feed the misspelling stress set (as data, after
            # review) - CHV recorded them from actual consumer queries.
            if (chv_pref and len(term) >= 4 and term.lower() != chv_pref.lower()
                    and normalize(term) != normalize(chv_pref)):
                dist = edit_distance_le2(term.lower(), chv_pref.lower())
                lo, plo = term.lower(), chv_pref.lower()
                inflection = (lo.startswith(plo) and lo[len(plo):] in ("d", "ed", "ing", "s", "es")) or \
                             (plo.startswith(lo) and plo[len(lo):] in ("d", "ed", "ing", "s", "es"))
                if dist and not inflection:
                    misspellings.append({"cui": cui, "misspelling": term,
                                         "standard": chv_pref, "distance": dist,
                                         "frequency": score(row[8])})
            if disparaged or combo <= 0:
                continue
            # a lay mapping only when the consumer term differs beyond
            # case/plural trivia (that difference is the study's object),
            # and the two sides share no content token - shared-token pairs
            # ("tested"/"test method" shapes) are wording trivia, not the
            # vocabulary gap this study measures. Purely structural rule;
            # no term judgment happens in code.
            if normalize(term) == normalize(umls_pref):
                continue
            lay_tokens = {w for w in normalize(term).split() if len(w) > 2}
            clin_tokens = {w for w in normalize(umls_pref).split() if len(w) > 2}
            if not lay_tokens or not clin_tokens or lay_tokens & clin_tokens:
                continue
            # morphological variants ("tested"/"test") share a stem even when
            # the exact tokens differ; a shared 4-char prefix between any
            # token pair is the structural stand-in for a stemmer
            if any(a[:4] == b[:4] for a in lay_tokens for b in clin_tokens
                   if len(a) >= 4 and len(b) >= 4):
                continue
            kept += 1
            # direction is NOT decided here: UMLS sometimes prefers the lay
            # form itself. Reviewers see both names + flags and decide.
            entry = {"cui": cui, "lay": term, "clinical": umls_pref,
                     "chv_preferred": chv_pref,
                     "flags": {"umls_preferred_term": row[5].strip().lower() == "yes",
                               "chv_preferred_term": row[6].strip().lower() == "yes"},
                     "scores": {"frequency": frequency, "combo": combo}}
            cur = best_per_cui.get(cui)
            if cur is None or (frequency, combo) > (cur["scores"]["frequency"], cur["scores"]["combo"]):
                best_per_cui[cui] = entry
    ranked = sorted(best_per_cui.values(),
                    key=lambda e: (-e["scores"]["frequency"], -e["scores"]["combo"]))
    misspellings.sort(key=lambda e: -e["frequency"])
    return ranked[:top], misspellings, {"flatfile_rows": rows, "eligible_rows": kept,
                                        "concepts_with_lay_term": len(best_per_cui),
                                        "misspelling_candidates": len(misspellings),
                                        "stop_cuis": len(stop_cuis),
                                        "incorrect_pairs": len(incorrect)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chv-dir", default=str(CHV_DIR))
    parser.add_argument("--top", type=int, default=400,
                        help="entries in the reviewable draft (ranked by CHV combo score)")
    parser.add_argument("--out", default="data/patient_lexicon.draft.json")
    parser.add_argument("--misspellings-out", default="data/misspelling_candidates.draft.json")
    parser.add_argument("--misspellings-top", type=int, default=200)
    args = parser.parse_args()

    entries, misspellings, counts = build(Path(args.chv_dir), args.top)
    payload = {
        "_": ("DRAFT pending doctor + linguist review - no entry seeds generation until the "
              "reviewers approve it. Lay phrases are real consumer language from the OAC CHV; "
              "the repo's MIT license does not cover this derived data, the CHV's open-access "
              "terms do."),
        "status": "draft pending domain review",
        "source": CITATION,
        "derivation": ("best lay term per concept by CHV consumer-frequency score (combo score "
                       "tie-break); stop concepts and published incorrect mappings excluded; "
                       "disparaged terms and case/plural-trivial variants excluded. Direction "
                       "(which side is lay) is left to reviewers - flags carry both preferences."),
        "counts": counts,
        "entries": entries,
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mis_payload = {
        "_": ("DRAFT pending review - real misspellings observed in consumer queries (OAC CHV): "
              "terms a 1-2 character edit from their concept's CHV preferred name. Candidate "
              "stimuli for the misspelling stress set; nothing fires until reviewed."),
        "status": "draft pending domain review",
        "source": CITATION,
        "entries": misspellings[:args.misspellings_top],
        "total_candidates": len(misspellings),
    }
    mis_out = Path(args.misspellings_out)
    mis_out.write_text(json.dumps(mis_payload, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"{len(entries)} entries -> {out} (from {counts['concepts_with_lay_term']} eligible "
          f"concepts, {counts['flatfile_rows']} flatfile rows); "
          f"{len(misspellings)} misspelling candidates -> {mis_out}")


if __name__ == "__main__":
    main()
