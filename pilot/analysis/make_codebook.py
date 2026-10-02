"""Build the stimulus quality codebook from the owner's review export and the rules data file.

Inputs (both committed, both data):
- a review export (pilot/codebook/review_export_<run>.json): every row of one blind review sample, the owner's
  stored answers, the checker's verdict, and the hashes of the run files the rows came from;
- a rules file (pilot/codebook/codebook_rules.json): the rules, the settled and open questions and the lexicon
  rulings, written as text. All vocabulary lives there, never in this script.

Output: codebook_v<version>.json (the baseline numbers, the rules, every review row) and codebook_v<version>.md, a
reading copy. Every number is computed here from the export, so the codebook can be re-derived from its own inputs:
`--check` rebuilds both files in memory and exits 1 when either differs from the committed copy.

Methodology. The owner answered five questions per pair on the review page (see the export's provenance block for
the option sets). Only first answers are used: the answers saved first, before the checker's verdict was shown for
that row. A row whose checker verdict was on screen before its first answer is refused, not dropped: it would no
longer be a blind label. Proportions carry 95% Wilson score intervals (z = 1.959964, the harness's value).
Agreement with the checker is on the "same" question only, the only question the checker answers; kappa is Cohen's
unweighted kappa over the three labels. No randomness is involved, so there is no seed.

Usage: make_codebook.py --export <file> --rules <file> --out-dir <dir> [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

Z = 1.959964
SAME_LABELS = ("yes", "no", "unclear")
QUESTIONS = ("same", "patient_real", "clinical_right", "sentence", "keep")


class CodebookError(ValueError):
    """An input that cannot produce a faithful codebook; the message names the row or field."""


def wilson(x: int, n: int) -> dict:
    """x successes of n with a 95% Wilson score interval, rounded to 4 places; n must be positive."""
    if n <= 0:
        raise CodebookError(f"wilson: empty denominator ({x}/{n})")
    p = x / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return {"x": x, "n": n, "p": round(p, 4), "lo": round(max(0.0, c - h), 4), "hi": round(min(1.0, c + h), 4)}


def cohen_kappa(pairs: list[tuple[str, str]], labels: tuple[str, ...]) -> float | None:
    """Unweighted Cohen's kappa; None when chance agreement is 1 (both raters used one label only)."""
    n = len(pairs)
    if not n:
        raise CodebookError("kappa: no pairs")
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n) for lab in labels)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 4)


def first_answers(row: dict) -> dict:
    """The blind answers of one export row, after checking the row can carry them."""
    owner = row.get("owner") or {}
    sid = row.get("sample_id")
    if owner.get("checker_shown_before_first_answer") is not False:
        raise CodebookError(f"{sid}: checker_shown_before_first_answer is not false; not a blind label")
    fa = owner.get("first_answers")
    if not isinstance(fa, dict) or fa.get("same") not in SAME_LABELS:
        raise CodebookError(f"{sid}: first_answers.same missing or not one of {SAME_LABELS}")
    return fa


def baseline(rows: list[dict], allowed: dict[str, list[str]]) -> dict:
    """Every number the codebook states, from first answers only."""
    if not rows:
        raise CodebookError("export has no rows")
    fas = [first_answers(r) for r in rows]
    for r, fa in zip(rows, fas):
        for q in QUESTIONS:
            v = fa.get(q)
            if v is not None and v not in allowed.get(q, []):
                raise CodebookError(f"{r['sample_id']}: {q}={v!r} is not an option the page offered")
        verdict = (r.get("checker") or {}).get("verdict")
        if verdict not in SAME_LABELS:
            raise CodebookError(f"{r['sample_id']}: checker verdict {verdict!r} is not one of {SAME_LABELS}")
    n = len(rows)
    ck = [r["checker"]["verdict"] for r in rows]
    same = [fa["same"] for fa in fas]
    def get(q: str) -> list:
        return [fa.get(q) for fa in fas]

    keep, sent, real = get("keep"), get("sentence"), get("patient_real")
    kept = [i for i in range(n) if keep[i] == "keep"]
    both = [i for i in range(n) if sent[i] == "both"]
    both_real = [i for i in both if real[i] == "real"]
    unanswered = {q: sum(v is None for v in get(q)) for q in QUESTIONS}
    return {
        "reviewed": n,
        "unanswered": unanswered,
        "keep": wilson(len(kept), n),
        "sentence_both": wilson(len(both), n),
        "patient_real": wilson(sum(v == "real" for v in real), n),
        "same_yes": wilson(sum(v == "yes" for v in same), n),
        "agreement_with_checker_same": wilson(sum(a == b for a, b in zip(same, ck)), n),
        "kappa_with_checker_same": cohen_kappa(list(zip(same, ck)), SAME_LABELS),
        "confusion_owner_rows_checker_cols": {a: {b: sum(x == a and y == b for x, y in zip(same, ck))
                                                  for b in SAME_LABELS} for a in SAME_LABELS},
        "sentence_both_given_keep": wilson(sum(sent[i] == "both" for i in kept), len(kept)),
        "keep_given_sentence_both": wilson(sum(keep[i] == "keep" for i in both), len(both)),
        "keep_given_sentence_both_and_real": wilson(sum(keep[i] == "keep" for i in both_real), len(both_real)),
        "patient_real_counts_among_kept": dict(sorted(Counter(real[i] for i in kept).items())),
        "counts": {q: dict(sorted(Counter(str(v) for v in get(q)).items())) for q in QUESTIONS},
    }


def cited_ids(rules: dict) -> set[str]:
    out: set[str] = set()
    for part in ("rules", "settled_questions", "open_questions", "lexicon_rulings"):
        for entry in rules.get(part, []):
            out.update(entry.get("examples", []))
    return out


def build(export: dict, rules: dict, export_bytes: bytes, rules_bytes: bytes, export_name: str,
          rules_name: str) -> tuple[dict, str]:
    rows = sorted(export["rows"], key=lambda r: r["sample_id"])
    ids = [r["sample_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise CodebookError("export repeats a sample_id")
    missing = sorted(cited_ids(rules) - set(ids))
    if missing:
        raise CodebookError(f"rules cite sample ids absent from the export: {missing}")
    allowed = export["provenance"]["review_page_questions"]
    book = {
        "version": rules["version"],
        "date_utc": rules["date_utc"],
        "status": rules["status"],
        "method": rules["method"],
        "source": {
            "run": export["run"],
            "export_file": export_name,
            "export_sha256": hashlib.sha256(export_bytes).hexdigest(),
            "rules_file": rules_name,
            "rules_sha256": hashlib.sha256(rules_bytes).hexdigest(),
            "run_file_sha256": export["provenance"]["sha256"],
            "lessons": export.get("lessons", []),
        },
        "baseline": baseline(rows, allowed),
        "rules": rules["rules"],
        "settled_questions": rules.get("settled_questions", []),
        "open_questions": rules.get("open_questions", []),
        "lexicon_rulings": rules.get("lexicon_rulings", []),
        "reviews": rows,
    }
    return book, render_md(book)


def _pct(w: dict) -> str:
    return f"{w['x']}/{w['n']} ({100 * w['p']:.0f}%, 95% CI {100 * w['lo']:.0f}-{100 * w['hi']:.0f}%)"


def _row_line(r: dict) -> str:
    fa = r["owner"]["first_answers"]
    line = (f"- **{r['sample_id']}** `{r['clinical_term']}` / `{r['patient_term']}` in \"{r['template']}\": "
            f"same {fa.get('same')}, real {fa.get('patient_real')}, sentence {fa.get('sentence')}, "
            f"keep {fa.get('keep')}; checker {r['checker']['verdict']}")
    note = r["owner"].get("notes")
    return line + (f"\n\n  > Your note, verbatim: {note}\n" if note else "")


def render_md(book: dict) -> str:
    b = book["baseline"]
    rows = {r["sample_id"]: r for r in book["reviews"]}
    md = [f"# Stimulus quality codebook v{book['version']} ({book['date_utc']})", "", book["status"], "",
          book["method"], "", "## Baseline from the first review", "",
          f"- Kept as is: {_pct(b['keep'])}",
          f"- Both sentences read naturally: {_pct(b['sentence_both'])}",
          f"- Patient phrase sounds real: {_pct(b['patient_real'])}",
          (f"- Owner and checker agree on \"same thing?\": {_pct(b['agreement_with_checker_same'])}; "
           f"kappa {b['kappa_with_checker_same']}"),
          f"- Kept pairs whose sentences both read naturally: {_pct(b['sentence_both_given_keep'])}",
          (f"- Pairs reading naturally with a real patient phrase that were kept: "
           f"{_pct(b['keep_given_sentence_both_and_real'])}"),
          "- Patient-phrase ratings among kept pairs: "
          + ", ".join(f"{n} {k}" for k, n in b["patient_real_counts_among_kept"].items()),
          "", "## Rules", ""]
    for r in book["rules"]:
        md += [f"**{r['id']} ({r['criterion']}).** {r['rule']}", "", f"Basis: {r['basis']}", ""]
        md += [_row_line(rows[s]) for s in r.get("examples", [])] + ([""] if r.get("examples") else [])
    if book["lexicon_rulings"]:
        md += ["## Lexicon rulings", "", "| Rows | Relation | Same concept | Precision | Source |", "|---|---|---|---|---|"]
        for x in book["lexicon_rulings"]:
            md.append(f"| {', '.join(x['examples'])} | {x['relation']} | {x['same_concept']} | {x['precision']} "
                      f"| {x['source']} |")
        md.append("")
    for title, key in (("Settled questions", "settled_questions"), ("Open questions", "open_questions")):
        if book[key]:
            md += [f"## {title}", ""]
            for q in book[key]:
                md += [f"**{q['id']}. {q['question']}** {q.get('ruling', q.get('your_rulings', ''))}", ""]
                if q.get("basis"):
                    md += [f"Basis: {q['basis']}", ""]
                md += [_row_line(rows[s]) for s in q.get("examples", [])] + ([""] if q.get("examples") else [])
    md += ["## Lessons recorded on the review page", ""]
    md += [f"> {x['text']}" for x in book["source"]["lessons"]] + [""]
    md += ["## All reviewed rows", "", "| Row | Clinical | Patient | Same | Real | Sentence | Keep | Checker |",
           "|---|---|---|---|---|---|---|---|"]
    for r in book["reviews"]:
        fa = r["owner"]["first_answers"]
        md.append(f"| {r['sample_id']} | {r['clinical_term']} | {r['patient_term']} | {fa.get('same')} | "
                  f"{fa.get('patient_real')} | {fa.get('sentence')} | {fa.get('keep')} | {r['checker']['verdict']} |")
    return "\n".join(md) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--export", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    a = ap.parse_args(argv)
    export_path, rules_path, out = Path(a.export), Path(a.rules), Path(a.out_dir)
    export_bytes, rules_bytes = export_path.read_bytes(), rules_path.read_bytes()
    try:
        book, md = build(json.loads(export_bytes), json.loads(rules_bytes), export_bytes, rules_bytes,
                         export_path.name, rules_path.name)
    except CodebookError as e:
        print(f"make_codebook: refused: {e}", file=sys.stderr)
        return 2
    json_text = json.dumps(book, ensure_ascii=False, indent=1) + "\n"
    stem = f"codebook_v{book['version']}"
    targets = {out / f"{stem}.json": json_text, out / f"{stem}.md": md}
    if a.check:
        stale = [str(p) for p, text in targets.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("make_codebook: out of date: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("make_codebook: committed codebook matches its inputs")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    for p, text in targets.items():
        p.write_text(text, encoding="utf-8")
    print(f"make_codebook: wrote {', '.join(str(p) for p in targets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
