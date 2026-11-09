#!/usr/bin/env python3
"""Mechanical checks for hand-authored 2panel candidate pairs, run before anyone reads them.

Exploratory tooling. Reads a candidates file in the hand-authored format (a JSON list of objects with ``id``,
``top_prompt``, ``bottom_prompt``, ``target_clinical_token``, ``swap_spans``, ``carrier_frame`` and
``clinical_tier_expected``) or a committed pairs file (the same fields under ``generation``, with ``tier_given``).
It changes nothing and calls nothing; it writes a report.

Errors: the pair cannot be used as written.
  shape            a required field is missing or empty, the id repeats, or the target lacks its leading space
  boundary         a side does not end mid-sentence (scenario_gen.ends_at_probe_boundary) or not with carrier_frame
  single_swap      swap_spans is missing, or the edits it declares do not turn the clinical side into the
                   everyday side. Edits: a clinical_span/patient_span swap (the clinical span occurs once), then
                   any {correct, misspelled} words (each occurs once). An empty clinical span is an insertion: the
                   everyday side minus the patient span, once, must be the clinical side (a sentence-initial
                   insertion may lowercase the old first letter).
  original         variant_of names a committed pair whose clinical side, target or everyday side
                   (original_bottom_prompt) this candidate does not copy exactly
  duplicate        the (clinical, everyday) pair repeats another candidate or a committed agscen pair
  holdout          a prompt is a Tier B holdout phrase (scripts/tierb_split.sealed_pair; the phrase is not printed)
  style            a side uses a character the round forbids (--forbid, e.g. ",;-" for the comma-free rounds);
                   a variant's clinical side is the original's and is not checked
  tier             the target has a tier in data/urgency_tiers.draft.json that differs from the expected tier

Warnings: a person should look before the pair is kept.
  punctuation      the swapped span changes the count of , ; : or - (the comma rounds); for a variant, the
                   everyday side's counts differ from the original everyday side's
  number           the everyday span drops a number the clinical span has, or adds one (a possible change of
                   clinical fact; often a word rendered as a digit, "bilateral" as "2 legs")
  target_vocab     the target has no tier in the vocabulary, or is more than one word (penalty is read from a
                   piece of it; the class is read from the top token and is unaffected)
  lexicon          a lexicon_entries item is not in the --lexicon file
  prediction       an expected_patient_continuations token has no tier, or a tier not below the expected tier

    python scripts/check_candidate_pairs.py CANDIDATES.json [--lexicon LEXICON.json] [--forbid ",;"]
                                            [--out report.json]

Exit status 1 when any candidate has an error, else 0.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from medlang_circuits.scenario_gen import ends_at_probe_boundary  # noqa: E402

PUNCT = ",;:-"
REQUIRED = ("id", "top_prompt", "bottom_prompt", "target_clinical_token", "carrier_frame")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def normalise(item: dict[str, Any]) -> dict[str, Any]:
    """A candidate or a committed pair (fields under ``generation``) as one flat dict."""
    if isinstance(item.get("generation"), dict):
        flat = dict(item["generation"])
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            flat[key] = item.get(key)
        flat.setdefault("clinical_tier_expected", flat.get("tier_given"))
        return flat
    return dict(item)


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def committed_pairs(root: Path, exclude: Path | None = None) -> dict[str, dict[str, Any]]:
    """generation.id -> flat pair, from every committed data/simulated/agscen_*.json except ``exclude``."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(str(root / "data" / "simulated" / "agscen_*.json"))):
        p = Path(path)
        if p.name.endswith(".report.json") or (exclude and p.resolve() == exclude.resolve()):
            continue
        for item in json.loads(p.read_text(encoding="utf-8")):
            flat = normalise(item)
            flat["_file"] = p.name
            out.setdefault(str(flat.get("id")), flat)
    return out


def load_vocab(root: Path) -> dict[str, Any]:
    return json.loads((root / "data" / "urgency_tiers.draft.json").read_text(encoding="utf-8"))["tokens"]


def vocab_tier(vocab: dict[str, Any], token: Any) -> int | None:
    entry = vocab.get(str(token or "").strip().lower())
    return entry.get("tier") if entry else None


def punct_counts(text: str) -> dict[str, int]:
    return {c: text.count(c) for c in PUNCT if text.count(c)}


def misspellings(spans: Any) -> list[dict[str, Any]] | None:
    """The {correct, misspelled} edits in swap_spans (one dict, a list of them, or keys beside a span)."""
    items = spans if isinstance(spans, list) else [spans] if isinstance(spans, dict) and "correct" in spans else []
    if not all(isinstance(e, dict) and isinstance(e.get("correct"), str) and isinstance(e.get("misspelled"), str)
               and e["correct"] for e in items):
        return None
    return items


def swap_problem(top: str, bottom: str, spans: Any) -> str | None:
    """None when the declared edits turn top into bottom. Edits apply in order to the clinical side: the span
    swap, then each misspelling. Spans are required: a word-level diff (scenario_gen.single_span_swap) splits a
    hand-written span that shares a word with the text it replaces, so it cannot stand in for them."""
    if spans is None:
        return "no swap_spans declared"
    if (typos := misspellings(spans)) is None:
        return "a misspelling edit needs string correct and misspelled values"
    has_span = isinstance(spans, dict) and ("clinical_span" in spans or "patient_span" in spans)
    if not has_span and not typos:
        return "swap_spans declares no edit"
    text = top
    if has_span:
        clin, pat = spans.get("clinical_span"), spans.get("patient_span")
        if not isinstance(clin, str) or not isinstance(pat, str) or not pat:
            return "swap_spans needs a string clinical_span and a non-empty patient_span"
        if clin == "":   # an insertion: compare by removing the inserted span from the everyday side
            if not typos and (bottom.replace(pat, "", 1) == top or (
                    bottom.startswith(pat) and top and bottom[len(pat):] == top[0].lower() + top[1:])):
                return None
            return "removing the inserted patient span once does not give the clinical side"
        if top.count(clin) != 1:
            return f"clinical_span occurs {top.count(clin)} times in the clinical side"
        text = top.replace(clin, pat)
        typos = [e for e in typos if (e["correct"], e["misspelled"]) != (clin, pat)]   # the span, recorded twice
    for e in typos:
        pattern = re.compile(r"\b" + re.escape(e["correct"]) + r"\b")
        if len(pattern.findall(text)) != 1:
            return f"the word {e['correct']!r} does not occur exactly once to misspell"
        text = pattern.sub(e["misspelled"], text)
    if text != bottom:
        return "applying the declared edits to the clinical side does not give the everyday side"
    return None


def check(candidates: list[dict[str, Any]], *, root: Path = ROOT, exclude: Path | None = None,
          lexicon: set[str] | None = None, forbid: str = "",
          sealed: Callable[[str], bool] | None = None) -> dict[str, dict[str, list[str]]]:
    """id -> {"errors": [...], "warnings": [...]} for every candidate (empty lists when it passes)."""
    vocab = load_vocab(root)
    committed = committed_pairs(root, exclude)
    committed_keys = {(norm_text(p["top_prompt"]), norm_text(p["bottom_prompt"])): pid
                      for pid, p in committed.items() if p.get("top_prompt") and p.get("bottom_prompt")}
    if sealed is None:
        sys.path.insert(0, str(root / "scripts"))
        import tierb_split  # noqa: PLC0415  (reads data/simulated and ops/dashboard.json)

        def sealed(text: str) -> bool:
            return bool(tierb_split.sealed_pair(None, None, text))

    report: dict[str, dict[str, list[str]]] = {}
    ids = collections.Counter(str(normalise(c).get("id")) for c in candidates)
    seen: dict[tuple[str, str], str] = {}
    for n, raw in enumerate(candidates, 1):
        c = normalise(raw) if isinstance(raw, dict) else {}
        cid = str(c.get("id") or f"#{n}")
        errors: list[str] = []
        warnings: list[str] = []
        report[cid] = {"errors": errors, "warnings": warnings}

        missing = [k for k in REQUIRED if not (isinstance(c.get(k), str) and c[k].strip())]
        if missing:
            errors.append(f"shape: missing or empty {missing}")
            continue
        if ids[cid] > 1:
            errors.append(f"shape: id appears {ids[cid]} times")
        top, bottom, target = c["top_prompt"], c["bottom_prompt"], c["target_clinical_token"]
        if not target.startswith(" ") or not target.strip():
            errors.append("shape: target_clinical_token needs a leading space and a word")
        if top == bottom:
            errors.append("shape: the two sides are identical")

        for side, text in (("clinical", top), ("everyday", bottom)):
            if not ends_at_probe_boundary(text):
                errors.append(f"boundary: the {side} side ends with terminal punctuation")
            if not text.endswith(c["carrier_frame"]):
                errors.append(f"boundary: the {side} side does not end with carrier_frame")
            if (side == "everyday" or not c.get("variant_of")) and (used := sorted(set(text) & set(forbid))):
                errors.append(f"style: the {side} side uses {''.join(used)!r}, which this round forbids")

        spans = c.get("swap_spans")
        if (problem := swap_problem(top, bottom, spans)) is not None:
            errors.append(f"single_swap: {problem}")

        if c.get("variant_of"):
            orig = committed.get(str(c["variant_of"]))
            if orig is None:
                errors.append(f"original: variant_of {c['variant_of']} is not a committed agscen pair")
            else:
                if top != orig["top_prompt"]:
                    errors.append("original: the clinical side is not the original's")
                if target != orig["target_clinical_token"]:
                    errors.append("original: the target is not the original's")
                if "original_bottom_prompt" in c and c["original_bottom_prompt"] != orig["bottom_prompt"]:
                    errors.append("original: original_bottom_prompt is not the original's everyday side")
                if bottom == orig["bottom_prompt"]:
                    errors.append("original: the everyday side is the original's (not a new wording)")
                if punct_counts(bottom) != punct_counts(orig["bottom_prompt"]):
                    warnings.append(f"punctuation: everyday side {punct_counts(bottom)} vs original "
                                    f"{punct_counts(orig['bottom_prompt'])}")

        key = (norm_text(top), norm_text(bottom))
        if key in seen:
            errors.append(f"duplicate: same pair as {seen[key]}")
        elif key in committed_keys and committed_keys[key] != cid:   # the same id is this item, re-checked
            errors.append(f"duplicate: same pair as committed {committed_keys[key]}")
        seen.setdefault(key, cid)

        if sealed(top) or sealed(bottom):
            errors.append("holdout: a prompt is a Tier B holdout phrase")

        expected = c.get("clinical_tier_expected")
        t_tier = vocab_tier(vocab, target)
        if t_tier is not None and expected is not None and t_tier != expected:
            errors.append(f"tier: target tier {t_tier} in the vocabulary, expected {expected}")
        if t_tier is None:
            warnings.append("target_vocab: the target has no tier in the vocabulary")
        if len(target.split()) > 1:
            warnings.append("target_vocab: the target is more than one word")

        if isinstance(spans, dict) and isinstance(spans.get("clinical_span"), str) \
                and isinstance(spans.get("patient_span"), str):
            clin, pat = spans["clinical_span"], spans["patient_span"]
            if clin and punct_counts(clin) != punct_counts(pat):
                warnings.append(f"punctuation: the span changes {punct_counts(clin)} to {punct_counts(pat)}")
            n_clin, n_pat = collections.Counter(NUMBER.findall(clin)), collections.Counter(NUMBER.findall(pat))
            if clin and (gone := sorted((n_clin - n_pat).elements())):
                warnings.append(f"number: the everyday span drops {gone}")
            if clin and (added := sorted((n_pat - n_clin).elements())):
                warnings.append(f"number: the everyday span adds {added}")

        if lexicon is not None:
            unknown = [e for e in c.get("lexicon_entries") or [] if e not in lexicon]
            if unknown:
                warnings.append(f"lexicon: not in the lexicon file: {unknown}")

        for token in c.get("expected_patient_continuations") or []:
            tier = vocab_tier(vocab, token)
            if tier is not None and expected is not None and tier >= expected:
                warnings.append(f"prediction: {token!r} is tier {tier}, not below {expected}")
    return report


def load_lexicon(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {e["expression"] for part in ("core", "folk_meaning") for e in data.get(part) or []}


def summary(report: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    def kinds(field: str) -> dict[str, int]:
        return dict(collections.Counter(m.split(":", 1)[0] for r in report.values() for m in r[field]))
    return {"candidates": len(report),
            "with_errors": sum(bool(r["errors"]) for r in report.values()),
            "with_warnings": sum(bool(r["warnings"]) for r in report.values()),
            "errors_by_check": kinds("errors"), "warnings_by_check": kinds("warnings")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--lexicon", type=Path)
    ap.add_argument("--forbid", default="", help="characters neither side may use, e.g. ',;-'")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    items = json.loads(a.candidates.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        print("the candidates file must be a JSON list", file=sys.stderr)
        return 1
    report = check(items, root=a.root, exclude=a.candidates,
                   lexicon=load_lexicon(a.lexicon) if a.lexicon else None, forbid=a.forbid)
    result = {"summary": summary(report), "candidates": report}
    if a.out:
        a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for cid, r in report.items():
        for m in r["errors"]:
            print(f"ERROR   {cid}  {m}")
        for m in r["warnings"]:
            print(f"warning {cid}  {m}")
    print(json.dumps(result["summary"]))
    return 1 if result["summary"]["with_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
