"""The stimulus quality codebook (pilot/codebook/) must be re-derivable from its committed inputs: the owner's review
export and the rules data file. pilot/analysis/make_codebook.py rebuilds it; it lives outside pilot/scripts/ because
every script there is hashed into each recorded run. These tests check the committed copy is current, that the
derivation refuses rather than drops a row that is not a blind label, that every cited row exists, and that the
interval and kappa helpers give known values."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CODEBOOK = ROOT / "pilot" / "codebook"
EXPORT = CODEBOOK / "review_export_pilot_real_20260930.json"
RULES = CODEBOOK / "codebook_rules.json"

_spec = importlib.util.spec_from_file_location("pilot_make_codebook_test", ROOT / "pilot" / "analysis" / "make_codebook.py")
assert _spec is not None and _spec.loader is not None, "pilot/analysis/make_codebook.py is missing"
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)


def _inputs():
    return json.loads(EXPORT.read_text(encoding="utf-8")), json.loads(RULES.read_text(encoding="utf-8"))


def test_committed_codebook_matches_its_inputs():
    assert mc.main(["--export", str(EXPORT), "--rules", str(RULES), "--out-dir", str(CODEBOOK), "--check"]) == 0


def test_codebook_carries_every_reviewed_row_and_cites_only_those():
    export, rules = _inputs()
    version = rules["version"]
    book = json.loads((CODEBOOK / f"codebook_v{version}.json").read_text(encoding="utf-8"))
    assert [r["sample_id"] for r in book["reviews"]] == sorted(r["sample_id"] for r in export["rows"])
    assert book["baseline"]["reviewed"] == len(export["rows"]) == 40
    assert mc.cited_ids(rules) <= {r["sample_id"] for r in export["rows"]}


def test_a_row_whose_verdict_was_shown_first_is_refused_not_dropped():
    export, rules = _inputs()
    bad = copy.deepcopy(export)
    bad["rows"][0]["owner"]["checker_shown_before_first_answer"] = True
    with pytest.raises(mc.CodebookError, match="not a blind label"):
        mc.build(bad, rules, b"", b"", "x", "y")


def test_a_rule_citing_an_unreviewed_row_is_refused():
    export, rules = _inputs()
    bad = copy.deepcopy(rules)
    bad["rules"][0]["examples"] = ["r999"]
    with pytest.raises(mc.CodebookError, match="absent from the export"):
        mc.build(export, bad, b"", b"", "x", "y")


def test_an_answer_outside_the_page_options_is_refused():
    export, rules = _inputs()
    bad = copy.deepcopy(export)
    bad["rows"][0]["owner"]["first_answers"]["keep"] = "maybe"
    with pytest.raises(mc.CodebookError, match="not an option the page offered"):
        mc.build(bad, rules, b"", b"", "x", "y")


def test_wilson_and_kappa_known_values():
    w = mc.wilson(18, 40)
    assert (w["p"], w["lo"], w["hi"]) == (0.45, 0.3071, 0.6017)
    assert mc.cohen_kappa([("yes", "yes"), ("no", "no")], ("yes", "no", "unclear")) == 1.0
    assert mc.cohen_kappa([("yes", "yes"), ("yes", "yes")], ("yes", "no", "unclear")) is None
    with pytest.raises(mc.CodebookError):
        mc.wilson(0, 0)
