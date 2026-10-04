"""Codebook decision D1 (pilot/codebook/codebook_rules.json, codebook v0.3) quotes numbers from the owner's blind
review of run pilot_v2_20261002. make_codebook.py does not compute them, because that review is not the codebook's
input, so its --check cannot catch a wrong one (Codex review of PR #80). This test ties each number to the committed
file it comes from:

- pilot/codebook/review_export_pilot_v2_20261002.json, the review itself, whose sha256 D1's basis names;
- pilot/codebook/agreement_pilot_v2_20261002.json, review_agreement.py's output over that export
  (tests/test_pilot_review_agreement.py checks it is what the script derives from the export and the run);
- the run's review_key.csv (the checker's answers on the 40 sampled rows) and summary.json (block E4: the checker's
  answers on the deliberately broken pairs and on the known-good seed rows).

Each statement in D1 that carries a number is rendered here from those files and must appear in D1's ruling or basis
word for word, and no other bare number may appear there. Changing, dropping or adding a quoted number therefore
fails; the last test proves it by changing every digit of every quoted statement in turn. Identifiers that contain
digits (R8, E4, the run id, file names) and dates are not quoted numbers and are not checked here."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEBOOK = ROOT / "pilot" / "codebook"
RULES = CODEBOOK / "codebook_rules.json"
EXPORT = CODEBOOK / "review_export_pilot_v2_20261002.json"
AGREEMENT = CODEBOOK / "agreement_pilot_v2_20261002.json"
RUN2 = ROOT / "pilot" / "runs" / "pilot_v2_20261002"

TOKEN = re.compile(r"[\w./-]*\d[\w./-]*")  # any run of word characters, dots, slashes or hyphens holding a digit
BARE_NUMBER = re.compile(r"[\d./-]+")  # a token with no letter or underscore: a count, ratio or decimal (or a date)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def d1_entry(rules: dict) -> dict:
    found = [q for q in rules["settled_questions"] if q["id"] == "D1"]
    assert len(found) == 1, "codebook_rules.json must hold exactly one settled question D1"
    return found[0]


def _only_answer(values: list[str], field: str) -> str:
    distinct = sorted(set(values))
    assert len(distinct) == 1, f"D1 says the checker gave one {field} answer on every sampled row; it gave {distinct}"
    return distinct[0]


def quoted_statements() -> dict[str, str]:
    """Every statement D1 makes that carries a number, keyed by what it states, rendered from the committed files.
    The asserts check what the wording claims beyond the numbers: that the agreement file was computed from this
    export, that every row was blind, that R8 kept every row, that one kappa holds for both comparisons, and that
    the same-meaning kappa's interval includes zero (D1 calls it chance level)."""
    export_bytes = EXPORT.read_bytes()
    export = json.loads(export_bytes)
    agreement = json.loads(AGREEMENT.read_text(encoding="utf-8"))
    summary = json.loads((RUN2 / "summary.json").read_text(encoding="utf-8"))
    with (RUN2 / "review_key.csv").open(encoding="utf-8", newline="") as f:
        key = list(csv.DictReader(f))
    rows = export["rows"]
    n = len(rows)
    sha = hashlib.sha256(export_bytes).hexdigest()
    assert export["run"] == agreement["run"] == RUN2.name
    assert agreement["export_sha256"] == sha, "the committed agreement file was not computed from the committed export"
    assert all(r["owner"]["checker_shown_before_first_answer"] is False for r in rows)
    assert sorted(r["id"] for r in key) == sorted(r["sample_id"] for r in rows)

    comparisons = agreement["comparisons"]
    sentence, realism = comparisons["sentence"]["agreement"], comparisons["realism"]["agreement"]
    same = comparisons["same"]
    kappa_sentence, kappa_realism = f"{comparisons['sentence']['kappa']:.2f}", f"{comparisons['realism']['kappa']:.2f}"
    assert kappa_sentence == kappa_realism, "D1 gives one kappa 'for each' of the naturalness and realism comparisons"
    lo, hi = same["kappa_ci95_bootstrap"]
    assert lo <= 0 <= hi, "D1 calls the same-meaning agreement chance level, but its kappa interval excludes zero"

    r8, specificity = agreement["keep_rule_r8"]["counts"], agreement["keep_rule_r8"]["specificity"]
    keep = Counter(r["owner"]["first_answers"]["keep"] for r in rows)
    assert set(keep) <= {"keep", "edit", "drop"}, keep
    assert agreement["keep_rule_r8"]["n"] == n and r8["tp"] + r8["fp"] == n and r8["fn"] == 0, "R8 did not keep all"
    assert (r8["tp"], r8["fp"]) == (keep["keep"], keep["edit"] + keep["drop"]), (r8, keep)

    e4 = summary["E4"]
    broken = Counter(e4["checker_specificity_broken"]["counts"])  # the summary leaves out zero counts
    good = Counter(e4["checker_sensitivity_known_good"]["counts"])
    n_broken, n_good = e4["checker_set"]["n_broken"], e4["checker_set"]["n_known_good"]
    assert sum(broken.values()) == n_broken and sum(good.values()) == n_good

    natural = _only_answer([r["checker_sentence_natural"] for r in key], "sentence_natural")
    real = _only_answer([r["checker_patient_realism"] for r in key], "patient_realism")
    return {
        "blind rows": f"({n} rows, every one answered before the checker's answer was shown)",
        "export hash": f"review_export_pilot_v2_20261002.json (sha256 {sha})",
        "bootstrap": f"(bootstrap seed {agreement['seed']}, {agreement['resamples']} resamples)",
        "one checker answer": (f"on the {n} sampled rows of the second review the checker answered {natural} and "
                               f"{real} on every row"),
        "naturalness and realism": (f"(agreement {sentence['x']}/{sentence['n']} and {realism['x']}/{realism['n']}, "
                                    f"kappa {kappa_sentence} for each)"),
        "R8": (f"kept all {n} rows: the {r8['tp']} the owner kept and the {r8['fp']} the owner would edit or drop "
               f"(specificity {specificity['x']}/{specificity['n']})"),
        "broken pairs": (f"on the run's {n_broken} deliberately broken pairs (patient phrases re-paired across rows) "
                         f"it answered not equivalent on {broken['no']}"),
        "known-good seed rows": (f"on the {n_good} seed rows the run's protocol treats as known-good it answered "
                                 f"equivalent on only {good['yes']} (not equivalent on {good['no']}, unclear on "
                                 f"{good['unclear']})"),
        "same meaning": (f"on the {n} sampled rows they agreed with the owner's at chance level "
                         f"({same['agreement']['x']}/{same['agreement']['n']}, kappa {same['kappa']:.2f})"),
    }


def d1_problems(entry: dict, statements: dict[str, str]) -> list[str]:
    """Why D1's ruling and basis do not quote exactly the committed numbers: a statement that is not there word for
    word, or a bare number left over once every statement is taken out."""
    text = entry["ruling"] + "\n" + entry["basis"]
    problems = [f"D1 does not state {what} as the committed files give it: {s!r}"
                for what, s in statements.items() if s not in text]
    for s in statements.values():
        text = text.replace(s, " ")
    stray = [t for t in (m.rstrip("./-") for m in TOKEN.findall(text)) if BARE_NUMBER.fullmatch(t)
             and not DATE.fullmatch(t)]
    if stray:
        problems.append(f"D1 quotes numbers that no committed file is checked for: {stray}")
    return problems


def test_every_number_d1_quotes_is_the_committed_value():
    entry = d1_entry(json.loads(RULES.read_text(encoding="utf-8")))
    assert d1_problems(entry, quoted_statements()) == []


def test_changing_any_quoted_digit_or_adding_a_number_to_d1_fails():
    entry = d1_entry(json.loads(RULES.read_text(encoding="utf-8")))
    statements = quoted_statements()
    changed = 0
    for what, s in statements.items():
        for i, ch in enumerate(s):
            if not ch.isdigit():
                continue
            wrong = s[:i] + str((int(ch) + 1) % 10) + s[i + 1:]
            bad = {**entry, "ruling": entry["ruling"].replace(s, wrong), "basis": entry["basis"].replace(s, wrong)}
            assert d1_problems(bad, statements), (what, wrong)
            changed += 1
    assert changed == sum(ch.isdigit() for s in statements.values() for ch in s) > 0
    added = {**entry, "ruling": entry["ruling"] + " The checker's precision agreed on 21/38."}
    assert d1_problems(added, statements) == ["D1 quotes numbers that no committed file is checked for: ['21/38']"]
