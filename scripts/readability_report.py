"""Readability worklist for the public site: which pages read hardest?

Strips tags/script/style from every site page, scores the visible prose with
Flesch-Kincaid grade level and average sentence length, and writes a ranked
markdown report. Health-communication guidance targets roughly grade 6-8;
pages above the threshold are flagged for the owner's editorial pass. The
scoring is heuristic (syllable counting is approximate) - treat the ranking
as a worklist, not a grade card. No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

DEFAULT_THRESHOLD = 9.0
VOWEL_RUN = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    count = len(VOWEL_RUN.findall(word))
    if word.endswith("e") and count > 1 and not word.endswith(("le", "ee")):
        count -= 1
    return max(1, count)


def visible_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z#0-9]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def score(text: str) -> dict | None:
    sentences = [s for s in re.split(r"[.!?]+(?:\s|$)", text) if len(s.split()) >= 3]
    words = [w for s in sentences for w in s.split()]
    if len(words) < 50:
        return None
    syl = sum(syllables(w) for w in words)
    wps = len(words) / len(sentences)
    spw = syl / len(words)
    grade = 0.39 * wps + 11.8 * spw - 15.59
    return {"words": len(words), "sentences": len(sentences),
            "words_per_sentence": round(wps, 1), "fk_grade": round(grade, 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--out", default="docs/readability_report.md")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    site = Path(args.site)
    pages = sorted(site.glob("*.html")) + sorted(site.glob("*/index.html"))
    rows = []
    for page in pages:
        rel = page.relative_to(site)
        if str(rel).startswith("modes/") or "share/" in str(rel):
            continue
        result = score(visible_text(page.read_text(encoding="utf-8")))
        if result:
            rows.append((str(rel), result))
    rows.sort(key=lambda r: -r[1]["fk_grade"])

    lines = ["# Site readability worklist", "",
             f"Flesch-Kincaid grade per page, hardest first. Flag threshold: grade {args.threshold}",
             "(health-communication guidance targets roughly grade 6-8). Heuristic scoring;",
             "use as a ranked editing worklist. Regenerate: `python scripts/readability_report.py`.", "",
             "| page | FK grade | words/sentence | words | flag |", "|---|---|---|---|---|"]
    for rel, r in rows:
        flag = "REVISE" if r["fk_grade"] > args.threshold else ""
        lines.append(f"| {rel} | {r['fk_grade']} | {r['words_per_sentence']} | {r['words']} | {flag} |")
    out = Path(args.out)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines[6:]:
        print(line)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
