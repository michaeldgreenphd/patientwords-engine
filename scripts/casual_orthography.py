"""Deterministic casual-typing pass over a colloquial rewrite batch (owner feedback, 2026-11-08).

The owner's read of the second colloquial set (rewrite_colloquial_v2_*): people type numbers as digits ("6", not
"six"), do not hyphenate ages ("78-year-old"), and do not type dashes. These are fixed spelling habits, so they are
applied by rule rather than by another generation: the same input always gives the same output, and no word's
meaning changes.

Rules, in order:
1. A dash used as punctuation (em dash, en dash, or a hyphen with spaces around it) becomes a space.
2. An age or duration compound loses its hyphens: "78-year-old" -> "78 year old", "seven-year-old" -> "seven year
   old" (then rule 3 makes it "7 year old").
3. Number words from two to ninety-nine become digits: "two weeks" -> "2 weeks", "forty five minutes" -> "45
   minutes", "ten to fifteen seconds" -> "10 to 15 seconds". Kept as words: "one" (it is often not a count: "the
   other one", "each one"), "half", "a couple", and "or two" / "or three" after another quantity ("an hour or two"),
   which people type as words.
4. Runs of spaces become one space.

Usage:
    python scripts/casual_orthography.py --in data/advice/rewrite_colloquial_v2_20261107T231002Z.json \\
        --out-dir data/advice

writes rewrite_colloquial_v3_<stamp>.json. Each pair keeps every field of its source pair. Its bottom_prompt is
the transformed text, and generation.postprocess records the rule set, the source file and its sha256, and the
text before the pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RULES_VERSION = "casual-orthography-1"

_UNITS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_ONES = {"one": 1, **{k: v for k, v in _UNITS.items() if v < 10}}

_DASH = re.compile(r"\s*[—–]\s*|\s+-\s+")
_AGE = re.compile(r"\b(\w+)-(year|month|week|day)s?-old\b", re.IGNORECASE)
_TENS_ONES = re.compile(r"\b(%s)[\s-](%s)\b" % ("|".join(_TENS), "|".join(_ONES)), re.IGNORECASE)
_SINGLE = re.compile(r"\b(%s)\b" % "|".join(list(_UNITS) + list(_TENS)), re.IGNORECASE)
_OR_SMALL = re.compile(r"\bor (two|three)\b", re.IGNORECASE)


def _age(m: re.Match) -> str:
    unit = m.group(2).lower()
    plural = m.group(0).lower().endswith(unit + "s-old")
    return f"{m.group(1)} {unit}{'s' if plural else ''} old"


def to_casual(text: str) -> str:
    """Apply the rules above to one text."""
    out = _DASH.sub(" ", text)
    out = _AGE.sub(_age, out)
    out = _TENS_ONES.sub(lambda m: str(_TENS[m.group(1).lower()] + _ONES[m.group(2).lower()]), out)
    kept = {m.start(1) for m in _OR_SMALL.finditer(out)}
    out = _SINGLE.sub(lambda m: m.group(0) if m.start(1) in kept else
                      str(_UNITS.get(m.group(1).lower()) or _TENS[m.group(1).lower()]), out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def transform_batch(pairs: list[dict], source_path: str, source_sha256: str) -> list[dict]:
    """Every pair of the batch, with the pass applied to its bottom_prompt and recorded under postprocess."""
    out = []
    for p in pairs:
        q = json.loads(json.dumps(p))
        before = q["bottom_prompt"]
        q["bottom_prompt"] = to_casual(before)
        q.setdefault("generation", {})["postprocess"] = {
            "rules": RULES_VERSION,
            "source_batch": source_path,
            "source_sha256": source_sha256,
            "before": before,
            "changed": q["bottom_prompt"] != before,
        }
        out.append(q)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", required=True, help="a rewrite_colloquial_* pairs file")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--stem", default="rewrite_colloquial_v3")
    args = ap.parse_args(argv)
    raw = Path(args.inp).read_bytes()
    pairs = json.loads(raw)
    if not isinstance(pairs, list) or not all(isinstance(p, dict) and "bottom_prompt" in p for p in pairs):
        print(f"{args.inp}: not a pairs list with bottom_prompt", file=sys.stderr)
        return 2
    out = transform_batch(pairs, args.inp, hashlib.sha256(raw).hexdigest())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(args.out_dir) / f"{args.stem}_{stamp}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    changed = sum(1 for p in out if p["generation"]["postprocess"]["changed"])
    print(f"wrote {path}: {len(out)} pairs, {changed} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
