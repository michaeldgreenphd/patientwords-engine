"""Tests for ``scripts/check_results_page.py``.

The unit tests cover the parts that need no browser: the mirror of the page's label and search rules, the choices
the checker makes from a catalogue index, the recorder and its exit codes, the read-only server and the exits of a
run that cannot start. The page's label tables exist once, in the page: the checker reads them from the page
source, and the unit tests here give it an invented page source with tables of the same form. Two tests compare
the real page source with the ids, strings and tables the checker reads. One test runs the whole checker in
Chromium against the sibling site checkout; it skips with the reason when Chromium or the site is absent. A skip
is a check that did not run, not a pass.

The toy runs and the toy label tables here are invented. No stimulus text is in this file.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


crp = _load("check_results_page", ROOT / "scripts" / "check_results_page.py")
SHA = "ab" * 32

# An invented page source: the label tables in the form the page writes them, one JSON object per table.
TOY_TABLES: dict[str, dict[str, str]] = {
    "CLASS_LABEL": {"study_batch": "Study batch", "hand_authored_exploratory": "Hand-authored set",
                    "redistribution_limited_text": "Third-party text set"},
    "FAMILY_LABEL": {"pairs": "Study batch", "pairs_extra_v2": "Study batch, second extra arm",
                     "handset": "Hand-authored set", "thirdparty": "Third-party text set"},
    "EVIDENCE_LABEL": {"registered_cohort": "registered cohort", "exploratory_set": "exploratory, toy set"},
    "STATE_LABEL": {"completed": "completed", "partial": "partial",
                    "completion_not_recorded": "completion not recorded"},
    "REVIEW_LABEL": {"a_pending": "review A pending"},
    "SAMPLING_LABEL": {"other": "other stimulus family"},
    "SCREENING_LABEL": {"screened_out": "screened out"},
    "RESTRICTION_LABEL": {"sealed_holdout": "Sealed holdout"},
    "INSTRUMENT_LABEL": {"toy-lens": "Toy-lens readout"},
    "SUFFIX_LABEL": {"lenspairs": "lens reader pairs"},
    "RULE_LABEL": {"study/1": "study analysis"},
}


def _toy_page(tables: dict[str, Any] | None = None, class_other: str = '"Other stimulus set"') -> str:
    tables = TOY_TABLES if tables is None else tables
    lines = [f"  var {name}={json.dumps(table, indent=1)};" for name, table in tables.items()]
    return "<script>\n" + "\n".join(lines) + f"\n  var CLASS_OTHER={class_other};\n</script>\n"


LABELS = crp.page_labels(_toy_page())


def _run(run_dir: str, **fields: Any) -> dict[str, Any]:
    """A toy index entry: public, one completed part, 4 public rows, no sealed row, unless ``fields`` say else."""
    run: dict[str, Any] = {
        "run_dir": run_dir, "stem": run_dir.split("__")[0], "model": "toy-a", "instrument": None,
        "stimulus_class": "study_batch", "evidence_class": "registered_cohort", "visibility": "public",
        "execution_states": {"completed": 1}, "n_parts": 1, "analysis_parts": {"study/1": 1},
        "rows_file": f"rows/{run_dir}.json",
        "counts": {"rows_public": 4, "rows_withheld_sealed": 0},
        "parts": [{"name": "batch_summary.json", "sha256": SHA, "execution_state": "completed",
                   "artifact_integrity": "recorded_match"}],
    }
    run.update(fields)
    return run


def _toy_runs() -> list[dict[str, Any]]:
    return [
        _run("pairs_20260101T010203Z__toy-a"),
        _run("pairs_20260101T010203Z__toy-b", model="toy-b", counts={"rows_public": 3, "rows_withheld_sealed": 2}),
        _run("pairs_20260202__toy-b", model="toy-b", evidence_class="exploratory_set", analysis_parts={"study/1": 0}),
        _run("handset_20260303", model=None, instrument="toy-lens", stimulus_class="hand_authored_exploratory",
             evidence_class="exploratory_set", execution_states={"completed": 1, "partial": 1}, n_parts=2,
             rows_file=None, counts={"rows_public": 0, "rows_withheld_sealed": 0},
             parts=[{"name": "p1.json", "sha256": SHA, "execution_state": "completed"},
                    {"name": "p2.json", "sha256": None, "execution_state": "partial", "artifact_integrity": "changed"}]),
        _run("thirdparty_20260404", visibility="restricted", rows_file=None, stimulus_class="redistribution_limited_text",
             counts={"rows_public": 0, "rows_withheld_sealed": 0}),
    ]


# ------------------------------------------------------------------------------------------ the page's rules

def test_the_label_tables_are_read_from_the_page_source_and_a_malformed_table_is_refused() -> None:
    assert dict(LABELS.tables) == TOY_TABLES and LABELS.class_other == "Other stimulus set"
    assert set(LABELS.tables) == set(crp.LABEL_TABLES)                       # every table the checker names
    assert LABELS.table("FAMILY_LABEL")["pairs"] == "Study batch"
    without = {name: table for name, table in TOY_TABLES.items() if name != "FAMILY_LABEL"}
    with pytest.raises(crp.SetupProblem, match="no label table FAMILY_LABEL"):
        crp.page_labels(_toy_page(without))
    with pytest.raises(crp.SetupProblem, match="no label table CLASS_LABEL"):
        crp.page_labels("<script>var CLASS_LABEL={study_batch:'Study batch'};</script>")     # not at a line start
    # The earlier form of the page, a JavaScript object with bare keys, is not a JSON object: it is refused, so a
    # table the checker cannot read is never replaced by a guess.
    bare = _toy_page().replace(json.dumps(TOY_TABLES["RULE_LABEL"], indent=1), "{study:'study analysis'}")
    with pytest.raises(crp.SetupProblem, match="RULE_LABEL .* is not a JSON object"):
        crp.page_labels(bare)
    for bad, reason in (({"a": 1}, "does not map each stored value"), ({"a": ""}, "does not map each stored value")):
        with pytest.raises(crp.SetupProblem, match=reason):
            crp.page_labels(_toy_page({**TOY_TABLES, "SUFFIX_LABEL": bad}))
    twice = _toy_page().replace('"a_pending": "review A pending"', '"a_pending": "one", "a_pending": "two"')
    with pytest.raises(crp.SetupProblem, match="REVIEW_LABEL .* lists a stored value twice"):
        crp.page_labels(twice)
    with pytest.raises(crp.SetupProblem, match="no label CLASS_OTHER"):
        crp.page_labels(_toy_page(class_other="'Other stimulus set'"))                 # not a JSON string


def test_experiment_title_is_the_family_label_and_the_date_the_stem_carries() -> None:
    def title(run: dict[str, Any]) -> str:
        return crp.experiment_title(run, LABELS)

    assert title({"run_dir": "r", "stem": "pairs_20260710T011743Z", "stimulus_class": "study_batch"}) == (
        "Study batch · 2026-07-10 01:17 UTC")
    assert title({"run_dir": "r", "stem": "handset_20261108", "stimulus_class": "hand_authored_exploratory"}) == (
        "Hand-authored set · 2026-11-08")
    # The family is the stem with its date stamp removed, wherever the stamp stands; its label is the table's.
    assert crp.stem_family("pairs_extra_20260710_v2") == ("pairs_extra_v2", "2026-07-10")
    assert title({"run_dir": "r", "stem": "pairs_extra_20260710_v2", "stimulus_class": "study_batch"}) == (
        "Study batch, second extra arm · 2026-07-10")
    assert crp.stem_family("pairs") == ("pairs", "") and crp.stem_family("pairs_20260710T011743Z")[0] == "pairs"
    assert title({"run_dir": "r", "stem": "pairs"}) == "Study batch"                  # no date in the stem: none shown
    assert title({"run_dir": "pairs_20260101"}) == "Study batch · 2026-01-01"         # no stem: the run id is read
    assert crp.stem_family("set_19991231") == ("set_19991231", "")                    # a year the page does not read
    assert crp.stem_family("set_20261341") == ("set_20261341", "")                    # not a month
    assert title({"run_dir": "r", "stem": "pairs_20260710T996100Z", "stimulus_class": "study_batch"}) == (
        "Study batch · 2026-07-10")                                              # not a time of day
    assert crp.stem_family("20260710") == ("", "2026-07-10")                          # the stamp alone: no family


def test_a_family_with_no_label_gets_its_class_label_keeps_its_stem_line_and_nothing_is_made_from_the_stem() -> None:
    known = _run("pairs_20260101T010203Z__toy-a")
    extra = _run("pairs_boostgrid_s2p5_20260101__toy-a")                          # study class, family with no entry
    other = _run("zzfam_lowrank_r2_20260202", stimulus_class="unclassified")       # neither family nor class entry
    undated = _run("featured_sim85", stimulus_class=None)
    runs = [known, extra, other, undated]
    stems = crp.title_stems(runs, LABELS)
    assert [crp.family_is_labelled(run, LABELS) for run in runs] == [True, False, False, False]
    # The label of the stimulus class, or the page's label for any other set; then the date. Never a stem token.
    assert crp.experiment_title(extra, LABELS) == "Study batch · 2026-01-01"
    assert crp.experiment_title(other, LABELS) == "Other stimulus set · 2026-02-02"
    assert crp.experiment_title(undated, LABELS) == "Other stimulus set"
    for run in (extra, other, undated):
        title = crp.experiment_title(run, LABELS).lower()
        tokens = [token for token in run["stem"].lower().split("_") if not token.isdigit()]
        assert tokens and not [token for token in tokens if token in title], (run["stem"], title)
    # The row of an unlabelled family keeps its stimulus set name; a labelled one does not print it.
    assert [crp.stem_line_shown(run, LABELS, stems) for run in runs] == [False, True, True, True]
    # Two labelled sets with one title (made in the same minute): both rows keep the name, to tell them apart.
    twins = [_run("pairs_20260101T010203Z__toy-a"), _run("pairs_20260101T010259Z__toy-a"),
             _run("pairs_20260101T010300Z__toy-a")]
    stems = crp.title_stems(twins, LABELS)
    assert stems["Study batch · 2026-01-01 01:02 UTC"] == {"pairs_20260101T010203Z", "pairs_20260101T010259Z"}
    assert [crp.stem_line_shown(run, LABELS, stems) for run in twins] == [True, True, False]


def test_a_stored_value_with_no_table_entry_is_printed_as_stored() -> None:
    evidence = LABELS.table("EVIDENCE_LABEL")
    assert crp.label_of(evidence, "exploratory_set") == "exploratory, toy set"       # an entry: its label
    for unmapped in ("exploratory_post_registration", "a_b_c", "Mixed_Case-value/1", "two  spaces"):
        assert crp.label_of(evidence, unmapped) == unmapped                          # no entry: exactly as stored
    assert crp.label_of(evidence, None) == crp.label_of(evidence, "") == crp.label_of(evidence, 3) == crp.DASH
    assert crp.label_of({}, "completion_not_recorded") == "completion_not_recorded"   # no underscore is replaced
    assert crp.stored("recorded_match") == "recorded_match" and crp.stored(None) == crp.stored("") == "not recorded"
    # An instrument with an entry is named by it; one without keeps its stored code.
    assert crp.instrument_label({"instrument": "toy-lens"}, LABELS) == "Toy-lens readout"
    assert crp.instrument_label({"instrument": "new_probe"}, LABELS) == "instrument: new_probe"
    assert crp.instrument_label({"instrument": None}, LABELS) == crp.instrument_label({}, LABELS) == ""


def test_search_text_holds_what_the_page_searches_and_matches_every_term() -> None:
    run = _toy_runs()[3]
    text = crp.search_text(run, LABELS)
    assert text == ("handset_20260303 handset_20260303  toy-lens hand-authored set · 2026-03-03  toy-lens readout "
                    "exploratory, toy set completed partial")

    def matches(query: str, of: dict[str, Any] = run) -> bool:
        return crp.search_matches(of, query, LABELS)

    assert matches("TOY-LENS partial") and matches("  hand-authored  ") and matches("readout")
    assert matches("") and not matches("toy-lens toy-b")
    assert matches("exploratory, toy") and not matches("exploratory_set")     # the label is searched, not the value
    unmapped = _run("handset_20260303__x", evidence_class="new_class", execution_states={"new_state": 1})
    assert matches("new_class new_state", unmapped)                           # a value with no entry: as stored


def test_the_second_line_of_a_model_cell_is_read_from_the_run_id_and_is_searched() -> None:
    """Regression (2026-11-12, review of patientwords#33): the page printed a label on the second line of a Model
    cell (``lens reader pairs``) and did not search it. ``second_line`` mirrors the page's rule, and the search
    text holds it beside the stored run id."""
    models = crp.model_ids([_run("pairs_20260101T010203Z__toy-b", model="toy-b"), _run("x", model=None)])
    assert models == frozenset({"toy-b"})
    run = _run("pairs_20260101T010203Z__lenspairs__toy-lens_toy-b", instrument="toy-lens", model=None)
    assert crp.second_line(run, LABELS, models) == "toy-b · lens reader pairs"
    assert crp.second_line(run, LABELS) == "lens reader pairs · toy-lens_toy-b"            # no model id listed: as stored
    assert crp.second_line(_run("pairs_20260101T010203Z__toy-lens", instrument="toy-lens", model=None), LABELS) == ""
    assert crp.second_line(_run("pairs_20260101T010203Z__toy-b", model="toy-b"), LABELS, models) == ""
    assert crp.second_line(_run("pairs_20260101T010203Z__odd_piece", model=None), LABELS) == "odd_piece"
    assert crp.search_matches(run, "lens reader pairs", LABELS, models)                    # the label a row shows
    assert crp.search_matches(run, "lenspairs", LABELS, models)                            # the stored code
    assert not crp.search_matches(_run("pairs_20260101T010203Z__toy-b", model="toy-b"), "reader", LABELS, models)


def test_search_still_matches_stems_run_ids_and_instrument_codes() -> None:
    def matches(run: dict[str, Any], query: str) -> bool:
        return crp.search_matches(run, query, LABELS)

    labelled = _run("pairs_20260101T010203Z__toy-b", model="toy-b")
    assert crp.experiment_title(labelled, LABELS) == "Study batch · 2026-01-01 01:02 UTC"   # no stem in the label
    assert matches(labelled, "pairs_20260101T010203Z")                        # the stimulus set name (stem)
    assert matches(labelled, "pairs_20260101T010203Z__toy-b")                 # the run id
    assert matches(labelled, "toy-b") and matches(labelled, "PAIRS_2026")
    # An instrument run: the stored code and the run id match, and so does the instrument's label.
    lens = _run("zzfam_r2_20260202__lenspairs__toy-lens_toy-b", model=None, instrument="toy-lens",
                stimulus_class="unclassified")
    assert crp.experiment_title(lens, LABELS) == "Other stimulus set · 2026-02-02"
    for query in ("toy-lens", "zzfam_r2_20260202", "zzfam_r2_20260202__lenspairs__toy-lens_toy-b", "lenspairs",
                  "readout", "other stimulus set"):
        assert matches(lens, query), query
    coded = _run("zzfam_20260202__new_probe", model=None, instrument="new_probe", stimulus_class="unclassified")
    assert matches(coded, "new_probe") and matches(coded, "instrument:")      # no entry: the stored code is shown
    assert not matches(labelled, "toy-lens") and not matches(lens, "pairs_20260101T010203Z")


def test_listed_runs_has_rows_has_issue_and_the_no_rows_statement() -> None:
    runs = _toy_runs()
    index = {"runs": [*runs, {"model": "no run id"}, "text", {"run_dir": ""}, {"run_dir": 7}]}
    assert crp.listed_runs(index) == runs and crp.listed_runs({"runs": None}) == [] and crp.listed_runs([]) == []
    assert [crp.has_rows(run) for run in runs] == [True, True, True, False, False]
    assert not crp.has_rows({"counts": {"rows_public": "4"}}) and not crp.has_rows({"counts": {"rows_public": True}})
    assert [crp.has_issue(run) for run in runs] == [False, False, False, True, False]
    assert crp.has_issue(_run("x", execution_states={"empty": 1})) and crp.has_issue(
        _run("x", execution_states={"unreadable": 2}))
    assert not crp.has_issue(_run("x", parts=[{"artifact_integrity": "unrecorded"}, {}]))
    assert crp.no_rows_statement(runs[3]) == "no rows listed" and crp.no_rows_statement(runs[4]) == "no rows published"
    assert crp.no_rows_statement(_run("x", counts={"rows_public": 0, "rows_withheld_sealed": 5})) == "0 public rows"


def test_count_text_and_public_row_indices() -> None:
    assert crp.count_text(41, 747) == "41 of 747 runs" and crp.count_text(1234, 5678) == "1,234 of 5,678 runs"
    assert crp.count_text(1, 1) == "1 of 1 runs"                   # the page does not write a singular
    doc = {"parts": [{"rows": [{"index": 12}, {"index": 3}]}, {"rows": [{"index": None}]}, {"rows": None}, {}]}
    assert crp.public_row_indices(doc) == sorted(["12", "3", crp.DASH])


def test_fmt_number_and_difference_text_keep_sign_zero_and_missing_apart() -> None:
    assert crp.fmt_number(0.692) == "0.6920" and crp.fmt_number(-0.649) == "0.6490" and crp.fmt_number(0) == "0.0000"
    assert crp.fmt_number(0.00005) == "0.0001" and crp.fmt_number(0.00004) == "4.00e-5"     # never 0.0000 unless zero
    assert crp.fmt_number(1.3877787807814457e-17) == "1.39e-17"
    assert crp.difference_text({"language_penalty": -0.649}) == "\u22120.6490 negative"
    assert crp.difference_text({"language_penalty": 0.25}) == "+0.2500 positive"
    assert crp.difference_text({"language_penalty": 0.0}) == "0.0000 zero"                  # a zero is a result
    assert crp.difference_text({"language_penalty": None}) == crp.NOT_MEASURED == "\u2014 not measured"
    assert crp.difference_text({}) == crp.NOT_MEASURED and crp.difference_text({"language_penalty": True}) == crp.NOT_MEASURED
    assert crp.difference_text({"language_penalty": float("nan")}) == crp.NOT_MEASURED
    assert not any(ch.isdigit() for ch in crp.NOT_MEASURED)                              # a missing value has no digit


def test_sign_agrees_is_everyday_minus_medical_and_none_without_all_three_numbers() -> None:
    row = {"prob_patient": 0.043, "prob_clinical": 0.692, "language_penalty": 0.043 - 0.692}
    assert crp.sign_agrees(row) is True
    assert crp.sign_agrees(dict(row, language_penalty=0.692 - 0.043)) is False            # the other order
    assert crp.sign_agrees(dict(row, language_penalty=-(0.043 - 0.692))) is False         # the other sign
    assert crp.sign_agrees({"prob_patient": 0.5, "prob_clinical": 0.5, "language_penalty": 0.0}) is True
    assert crp.sign_agrees(dict(row, prob_patient=None)) is None and crp.sign_agrees({"language_penalty": 0.1}) is None


def test_shared_review_is_the_most_frequent_status_and_the_first_of_a_tie() -> None:
    def run(review: str | None) -> dict[str, Any]:
        return {"clinical_review": review}

    assert crp.shared_review([run("a_pending"), run("b_pending"), run("b_pending")]) == "b_pending"
    assert crp.shared_review([run("a_pending"), run("b_pending")]) == "a_pending"         # a tie: the first listed
    assert crp.shared_review([run(None), run(None), run("a_pending")]) == "not recorded"
    assert crp.shared_review([]) == ""


def _stop(**fields: Any) -> dict[str, Any]:
    stop = {"tag": "A", "id": None, "cls": "", "text": "a link", "parent": "", "in_nav": False, "download": False,
            "outline": "solid", "width": 2.0, "in_view": True}
    stop.update(fields)
    return stop


def test_assert_focus_needs_every_control_in_order_with_an_outline() -> None:
    stops = [_stop(cls="skip"), _stop(in_nav=True), _stop(tag="SUMMARY", parent="nav-more"),
             _stop(tag="SUMMARY", parent="about"), _stop(tag="INPUT", id="f-q"), _stop(tag="BUTTON", id="view-all"),
             _stop(tag="BUTTON", id="more-btn"), _stop(tag="BUTTON", id="f-reset"), _stop(download=True),
             _stop(tag="BUTTON", cls="cat-x")]
    found = crp.assert_focus(stops, crp.MAIN_CONTROLS)
    assert found["reached_at_tab_press"]["search box"] == 5 and found["tab_stops_read"] == 10
    with pytest.raises(AssertionError, match="does not reach the search box"):
        crp.assert_focus([stop for stop in stops if stop["id"] != "f-q"], crp.MAIN_CONTROLS)
    with pytest.raises(AssertionError, match="does not reach the download link"):
        crp.assert_focus(stops[:7] + [stops[8], stops[7], stops[9]], crp.MAIN_CONTROLS)   # the two out of order
    bare = [dict(stop) for stop in stops]
    bare[4]["outline"] = "none"
    with pytest.raises(AssertionError, match="search box shows no focus outline"):
        crp.assert_focus(bare, crp.MAIN_CONTROLS)
    thin = [dict(stop) for stop in stops] + [_stop(text="a stray control", width=1.0)]
    with pytest.raises(AssertionError, match="show no focus outline"):
        crp.assert_focus(thin, crp.MAIN_CONTROLS)


# ------------------------------------------------------------------------------------------ expectations

def test_the_search_term_is_the_model_name_that_selects_the_most_runs_and_not_all() -> None:
    runs = _toy_runs()
    term, matched = crp.pick_search_term(runs, LABELS)
    # "toy-a" and "toy-b" each select two runs; of two terms that select as many, the first name is taken.
    counts = {name: sum(crp.search_matches(run, name, LABELS) for run in runs) for name in ("toy-a", "toy-b")}
    assert counts == {"toy-a": 2, "toy-b": 2}
    assert term == "toy-a" and matched == ["pairs_20260101T010203Z__toy-a", "thirdparty_20260404"]     # index order
    more = [*runs, _run("pairs_20260505__toy-b", model="toy-b")]
    assert crp.pick_search_term(more, LABELS)[0] == "toy-b"                                       # the most runs
    assert len(crp.pick_search_term(more, LABELS)[1]) == 3
    same = [_run("a__m"), _run("b__m")]
    for run in same:
        run["model"] = "m"
    assert crp.pick_search_term(same, LABELS)[0] in ("a", "a__m")   # every run has the model: a stem is taken
    assert crp.pick_search_term([_run("only")], LABELS) is None     # one run: nothing narrows the list


def test_the_opened_run_prefers_sealed_rows_and_is_selected_alone_by_its_run_id() -> None:
    runs = _toy_runs()
    assert crp.pick_open_run(runs, LABELS)["run_dir"] == "pairs_20260101T010203Z__toy-b"  # the run with sealed rows
    unsealed = [run for run in runs if run["counts"]["rows_withheld_sealed"] == 0]
    assert crp.pick_open_run(unsealed, LABELS)["run_dir"] == "pairs_20260101T010203Z__toy-a"   # else the first usable
    # A run id that is also the start of another run id is not selected alone, so it is not opened.
    prefix = [_run("pairs_2026"), _run("pairs_2026__toy-b", model="toy-b")]
    assert crp.pick_open_run(prefix, LABELS)["run_dir"] == "pairs_2026__toy-b"
    for unusable in ({"n_parts": 2}, {"rows_file": None}, {"rows_file": "../rows/x.json"}, {"visibility": "restricted"},
                     {"parts": [{"name": "p", "sha256": "short"}]}, {"counts": {"rows_public": 0}}):
        with pytest.raises(crp.SetupProblem, match="open-run checks cannot run"):
            crp.pick_open_run([_run("solo", **unusable)], LABELS)


def test_the_evidence_class_the_filter_checks_use() -> None:
    runs = _toy_runs()
    # registered_cohort: 3 runs, 2 with rows inside study/1. exploratory_set: 2 runs, none inside.
    assert crp.pick_evidence_class(runs, "study/1") == ("registered_cohort", 3, 2)
    assert crp.pick_evidence_class(runs, "another/1") == ("registered_cohort", 3, 0)       # then the most runs
    with pytest.raises(crp.SetupProblem, match="evidence class"):
        crp.pick_evidence_class([_run("x", evidence_class=None)], "study/1")


def test_the_run_without_rows_is_a_partial_one_when_there_is_one() -> None:
    runs = _toy_runs()
    assert crp.pick_run_without_rows(runs)["run_dir"] == "handset_20260303"
    assert crp.pick_run_without_rows([runs[4], runs[0]])["run_dir"] == "thirdparty_20260404"   # none partial: any
    assert crp.pick_run_without_rows(runs[:3]) is None
    assert crp.pick_run_without_rows([_run("x", rows_file=None, parts=[{"sha256": None}])]) is None


def test_expectations_are_read_from_the_index_and_hold_keys_and_counts_only() -> None:
    index = {"runs": _toy_runs(), "policy": {"default_membership": "study/1"}}
    expected = crp.expectations(index, LABELS)
    assert expected.labels is LABELS and expected.total == 5 and expected.run_ids[0] == "pairs_20260101T010203Z__toy-a"
    assert expected.partial == ["handset_20260303"] and expected.restricted == ["thirdparty_20260404"]
    assert expected.no_rows == ["handset_20260303", "thirdparty_20260404"] and expected.issue == 1
    assert expected.sealed == 2 and expected.evidence == ("registered_cohort", 3, 2)
    term, matched = expected.search
    visibility, stimulus, wanted = expected.query_filter
    by_id = {run["run_dir"]: run for run in index["runs"]}
    assert wanted == sum(1 for name in matched if (by_id[name]["visibility"], by_id[name]["stimulus_class"])
                         == (visibility, stimulus)) > 0
    summary = expected.summary()
    assert summary["runs"] == 5 and summary["opened_run"] == "pairs_20260101T010203Z__toy-b"
    assert summary["opened_run_sealed_rows"] == 2 and summary["run_without_rows"] == "handset_20260303"
    assert all(not isinstance(value, (list, dict)) for value in summary.values())


def test_load_catalogue_is_a_setup_problem_without_usable_data(tmp_path: Path) -> None:
    with pytest.raises(crp.SetupProblem, match="has no data/results_catalogue/index.json"):
        crp.load_catalogue(tmp_path)
    index = tmp_path / crp.INDEX_FILE
    index.parent.mkdir(parents=True)
    index.write_text("{not json", encoding="utf-8")
    with pytest.raises(crp.SetupProblem, match="could not be read as JSON"):
        crp.load_catalogue(tmp_path)
    index.write_text(json.dumps({"runs": []}), encoding="utf-8")
    with pytest.raises(crp.SetupProblem, match="lists no run"):
        crp.load_catalogue(tmp_path)
    index.write_text(json.dumps({"runs": _toy_runs()}), encoding="utf-8")
    assert len(crp.load_catalogue(tmp_path)["runs"]) == 5


# ------------------------------------------------------------------------------------------ recorder and exits

def test_the_check_list_is_69_distinct_names_and_groups_follow_its_order() -> None:
    # 62 until 2026-11-11. Then: two placement checks were replaced in place by checks of the page's order, and
    # seven were added (shared status, navigation, focus, wordings and differences, colour, text at 1280, text
    # at twice its size).
    assert len(crp.CHECKS) == len(set(crp.CHECKS)) == 69
    first = crp.group("search_input_is_inside_the_first_viewport_at_1280x720",
                      "main_controls_are_reached_by_tab_and_show_a_focus_outline")
    assert first == crp.CHECKS[:12] and crp.CHECKS[-1] == "no_request_left_the_test_server"
    assert sum(1 for name in crp.CHECKS if name.startswith("page_does_not_say_")) == len(crp.EXCLUDED_PHRASES) == 3
    assert sum(1 for name in crp.CHECKS if name.startswith("download_target_")) == len(crp.DOWNLOADS) == 3
    # No check requires a number of rows inside a window, and the floor for visible text is 12 px.
    assert not [name for name in crp.CHECKS if "rows_are_inside" in name or "10_px" in name]
    assert crp.MIN_TEXT_PX == 12 and sum(1 for name in crp.CHECKS if name.endswith("at_least_12_px")) == 2


def test_recorder_keeps_passed_failed_not_applicable_and_blocked_apart(capsys: pytest.CaptureFixture[str]) -> None:
    receipt: dict[str, Any] = {"checks": []}
    recorder = crp.Recorder(receipt)

    def raising(exc: Exception):
        def action() -> None:
            raise exc
        return action

    assert recorder.run("holds", lambda: {"rows": 3}) is True
    assert recorder.run("breaks", raising(AssertionError("first line\nsecond line"))) is False
    assert recorder.run("no_such_run", raising(crp.NotApplicable("the catalogue has no partial run"))) is True
    assert recorder.run("no_registry", raising(crp.Blocked("the sealed registry computes empty"))) is False
    assert (recorder.failed, recorder.not_applicable, recorder.blocked) == (1, 1, 1)
    assert [check["result"] for check in receipt["checks"]] == ["passed", "failed", "not_applicable", "blocked"]
    assert receipt["checks"][0]["rows"] == 3 and receipt["checks"][1]["message"] == "first line"
    assert receipt["checks"][2]["reason"] == "the catalogue has no partial run"
    with pytest.raises(crp.SetupProblem):
        recorder.run("stopped", raising(crp.SetupProblem("no browser")))
    printed = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in printed] == ["ok", "FAIL", "n/a", "BLOCKED"]


def test_exit_code_never_calls_a_blocked_check_a_pass() -> None:
    assert crp.exit_code(0, 0) == crp.EXIT_PASS == 0
    assert crp.exit_code(1, 0) == crp.exit_code(3, 2) == crp.EXIT_FAILED == 1
    assert crp.exit_code(0, 1) == crp.EXIT_SETUP == 2


def test_a_group_whose_page_does_not_load_files_every_check_as_failed() -> None:
    receipt: dict[str, Any] = {"checks": []}
    recorder = crp.Recorder(receipt)

    def no_page() -> None:
        raise TimeoutError("navigation timed out")

    assert crp.opened(recorder, ("one", "two"), no_page) is None
    assert [(check["name"], check["result"]) for check in receipt["checks"]] == [("one", "failed"), ("two", "failed")]
    assert all("not reached" in check["message"] for check in receipt["checks"]) and recorder.failed == 2
    assert crp.opened(recorder, ("three",), lambda: "page") == "page" and len(receipt["checks"]) == 2


def _toy_site(tmp_path: Path, *, index: bool = True) -> Path:
    site = tmp_path / "toy_site"
    (site / "results").mkdir(parents=True)
    (site / crp.PAGE).write_text("<!doctype html><title>toy</title>", encoding="utf-8")
    if index:
        (site / crp.CATALOGUE).mkdir(parents=True)
        (site / crp.INDEX_FILE).write_text(json.dumps({"runs": _toy_runs()}), encoding="utf-8")
    return site


def test_the_server_serves_the_site_under_its_project_path_and_nothing_else(tmp_path: Path) -> None:
    site = _toy_site(tmp_path)
    (tmp_path / "outside.txt").write_text("outside the site", encoding="utf-8")
    before = sorted(str(path.relative_to(site)) for path in site.rglob("*"))
    server = crp.serve(site, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def status(path: str, method: str = "GET") -> int:
        try:
            with opener.open(urllib.request.Request(base + path, method=method), timeout=10) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)

    try:
        assert status("/patientwords/results/") == 200 and status("/patientwords/results/index.html") == 200
        assert crp.head_status(f"{base}/patientwords/{crp.INDEX_FILE}") == 200
        assert crp.head_status(f"{base}/patientwords/{crp.CATALOGUE}/absent.csv") == 404
        assert status("/results/index.html") == 404                 # only the project path is served
        assert status("/patientwords-other/results/") == 404
        assert status("/patientwords/../outside.txt") == 404        # the site directory cannot be left
        assert status("/patientwords/%2e%2e/outside.txt") == 404
        assert status("/patientwords/results/index.html", "POST") == 501     # read-only: no writing method
        with opener.open(base + "/patientwords/results/", timeout=10) as response:
            assert response.headers["Cache-Control"] == "no-store"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)
    assert sorted(str(path.relative_to(site)) for path in site.rglob("*")) == before        # nothing was written


def test_receipt_binds_checkouts_inputs_and_tools_without_private_paths(tmp_path: Path) -> None:
    site = _toy_site(tmp_path)
    receipt = crp.new_receipt(site, None)
    assert receipt["schema"] == "patientwords.results-page-check-receipt/1" and receipt["result"] == "not_run"
    assert receipt["frontend"]["head"] is None and "not_recorded" in receipt["frontend"]     # not a checkout
    assert receipt["input_sha256"] == {crp.PAGE: crp.sha256_file(site / crp.PAGE),
                                       crp.INDEX_FILE: crp.sha256_file(site / crp.INDEX_FILE)}
    assert set(receipt["tool_sha256"]) == {"scripts/check_results_page.py", "scripts/seal_check.py"}
    assert receipt["viewports"] == {"desktop": [1280, 720], "phone": [390, 844]} and receipt["checks"] == []
    text = json.dumps(receipt)
    assert str(ROOT) not in text and str(tmp_path) not in text


def test_exit_2_when_the_site_has_no_results_page(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt = tmp_path / "receipt.json"
    assert crp.main(["--site", str(tmp_path), "--receipt", str(receipt)]) == crp.EXIT_SETUP
    assert "setup problem" in capsys.readouterr().err and not receipt.exists()


def test_exit_2_and_a_blocked_receipt_when_chromium_is_absent(tmp_path: Path,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    site, receipt = _toy_site(tmp_path), tmp_path / "receipt.json"
    code = crp.main(["--site", str(site), "--browser", str(tmp_path / "no-such-chromium"), "--receipt", str(receipt)])
    assert code == crp.EXIT_SETUP
    assert "blocked, not passed" in capsys.readouterr().err
    written = json.loads(receipt.read_text(encoding="utf-8"))
    assert written["result"] == "blocked" and written["checks"] == []      # a blocked check records no pass


def test_exit_2_and_a_blocked_receipt_when_the_site_has_no_catalogue(tmp_path: Path,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("playwright", reason="the playwright package is not installed; the no-catalogue exit is "
                                             "reached after it is imported, so this test did not run")
    site, receipt = _toy_site(tmp_path, index=False), tmp_path / "receipt.json"
    assert crp.main(["--site", str(site), "--receipt", str(receipt)]) == crp.EXIT_SETUP
    assert "no catalogue data" in capsys.readouterr().err
    written = json.loads(receipt.read_text(encoding="utf-8"))
    assert written["result"] == "blocked" and written["checks"] == [] and written["catalogue"] is None


# ------------------------------------------------------------------------------------------ the page source

def test_the_page_carries_the_ids_and_strings_the_checker_reads() -> None:
    page = SITE / crp.PAGE
    if not page.is_file():
        pytest.skip(f"no sibling site page at {page}; the string check did not run")
    source = page.read_text(encoding="utf-8")
    static, script = source.split("<script>")[0], source.split("<script>")[1]
    for name in crp.PAGE_IDS:
        assert f'id="{name}"' in static, name
    for hook in crp.PAGE_HOOKS:
        assert hook in script, hook
    for view in ("all", "partial", "norows", "restricted", "issue"):       # the ids the page builds as view-<id>
        assert f"id:'{view}'" in script, view
    # The search rule and the label rules the checker mirrors: a change to one of these lines fails here, so that
    # the mirror is changed with it. The label tables are not mirrored: the checker reads them from this source.
    for line in (*crp.PAGE_SEARCH_RULE, *crp.PAGE_LABEL_RULES):
        assert line in script, line
    labels = crp.page_labels(source)
    assert set(labels.tables) == set(crp.LABEL_TABLES) and labels.class_other
    assert "replace(/_/g" not in script and "toUpperCase()" not in script        # no label is made from an identifier
    assert f"var PAGE_SIZE={crp.PAGE_SIZE};" in script
    assert "fmtInt(filtered.length)+' of '+fmtInt(RUNS.length)+' runs'" in script        # count_text
    # Reader-visible strings the checks compare.
    for column in crp.COLUMNS:
        assert f'">{column[:1].upper()}{column[1:]}' in static, column
    for text in (crp.ORDER_DEFAULT, crp.ORDER_DATE, crp.ORDER_NEVER, crp.SEALED_IN_RUN, "'Methods & source'",
                 crp.NO_ROWS_RESTRICTED, crp.NO_ROWS_NONE, "' public '+(nPub===1?'row':'rows')", "' sealed'",
                 "could not be loaded ('+failLabel(e)+')", "'HTTP '+r.status", *crp.RUN_LABELS[:1],
                 "'evidence: '", "'clinical review: '", "'sampling: '"):
        assert text in script, text
    # The wordings, the order of the difference and the shared status, as the checks compare them.
    for text in ("'Medical wording'", "'Everyday wording'", "['Target-token probability','num','medical wording']",
                 "['Target-token probability','num','everyday wording']", f"['Difference','','{crp.DIFFERENCE_ORDER}']",
                 *crp.SHARED_STATUS, *crp.DIFFERENCE_NOTE, "DASH+' not measured'", "'data-exception','review'",
                 "el('span','ln',labelOf(REVIEW_LABEL,r.clinical_review))"):
        assert text in script.replace("\u2019s", "").replace("\u2019", ""), text
    assert "'Clinical wording'" not in script and "'Patient wording'" not in script
    assert "var(--penalty)" not in source and "bdg-restricted" not in source and "draft-flag" not in source
    # The alert colour is declared once and used for a file that failed to load, and for nothing else.
    assert static.count("#b4483d") == 1 and f"--alert:{'#b4483d'}" in static
    uses = [line.strip().split("{")[0] for line in static.splitlines() if "var(--alert)" in line]
    assert uses == [".cat-err", ".det-status.is-fail"], uses
    # Nothing a reader must read is set below 13 px, and no label is set in capitals with letter-spacing.
    assert "text-transform:uppercase" not in static and "letter-spacing:.1" not in static
    assert "--t-meta:13px" in static and not [size for size in ("font-size:10px", "font-size:10.5px", "font-size:11px",
                                                                "font-size:11.5px", "font-size:12px") if size in static]
    # The navigation: four links for the journey, the rest in one details element; this page is the current one.
    nav = static[static.index('<nav aria-label="Site">'):static.index("</nav>")]
    for label, href in crp.NAV_PRIMARY:
        assert f'<a href="{href}"' in nav and f">{label}</a>" in nav, label
    assert '<a href="./" aria-current="page">Results</a>' in nav and '<details class="nav-more">' in nav
    assert all(f">{label}</a>" in nav for label in crp.NAV_MORE) and "experiments" not in nav
    for text in (*crp.ABOUT_STATEMENTS, crp.STUDY_VERSION, "join on <code>stem</code> and <code>index</code>",
                 "own_clinical_prompt", "language_penalty", 'href="#downloads"', 'href="#methods-source"'):
        assert text in static, text
    assert static.count(crp.EXPLAINED_ONCE) == 1 and crp.EXPLAINED_ONCE not in script
    for phrase in crp.EXCLUDED_PHRASES:
        assert phrase not in source.lower(), phrase
    for name in crp.DOWNLOADS:
        assert static.count(f'href="../{crp.CATALOGUE}/{name}" download="{name}"') == 2, name
    # The address parameters and anchors the checks open.
    for parameter in ("state", "evidence", "rows", "membership", "visibility", "stimulus", "sort"):
        assert f"{parameter}:'f-{parameter}'" in script, parameter
    assert "p.get('q')" in script and "p.get('run')" in script


def test_the_pages_label_tables_cover_the_sites_index_and_the_fallback_is_the_class_label() -> None:
    """The real page's tables against the real index. What is fixed here is the rule, not the catalogue: a
    family that lands without a table entry passes, with its class label and its stimulus set name on the row."""
    page, index_file = SITE / crp.PAGE, SITE / crp.INDEX_FILE
    if not page.is_file() or not index_file.is_file():
        pytest.skip(f"no sibling site checkout with {crp.PAGE} and {crp.INDEX_FILE} at {SITE}; the table check "
                    "did not run")
    labels = crp.page_labels(page.read_text(encoding="utf-8"))
    runs = crp.listed_runs(json.loads(index_file.read_text(encoding="utf-8")))
    family, classes = labels.table("FAMILY_LABEL"), labels.table("CLASS_LABEL")
    # A label is words: none carries the underscore of an identifier.
    assert not [label for table in labels.tables.values() for label in table.values() if "_" in label]
    stems = crp.title_stems(runs, labels)
    explicit = set(family.values()) | set(classes.values()) | {labels.class_other}
    unlabelled = 0
    for run in runs:
        title = crp.experiment_title(run, labels)
        date = crp.stem_family(run["stem"])[1]
        name = title[:-len(f" · {date}")] if date else title
        assert name in explicit, (run["run_dir"], name)                         # a label of a table, word for word
        if not crp.family_is_labelled(run, labels):
            unlabelled += 1
            assert name == classes.get(run.get("stimulus_class") or "", labels.class_other), run["run_dir"]
            assert crp.stem_line_shown(run, labels, stems), run["run_dir"]       # the set's name stays on the row
        # Identifiers stay searchable whatever the row shows.
        for term in (run["run_dir"], run["stem"], run.get("instrument") or run["run_dir"]):
            assert crp.search_matches(run, term, labels), (run["run_dir"], term)
    # Rows that share a title belong to one stimulus set, or print the set's name.
    for title, names in stems.items():
        if len(names) > 1:
            shared = [run for run in runs if crp.experiment_title(run, labels) == title]
            assert all(crp.stem_line_shown(run, labels, stems) for run in shared), title
    assert unlabelled < len(runs)
    # Every stored value the rows above show through a table is either in its table or printed as stored.
    for key, name in (("evidence_class", "EVIDENCE_LABEL"), ("clinical_review", "REVIEW_LABEL")):
        for value in sorted({run.get(key) for run in runs if isinstance(run.get(key), str)}):
            assert crp.label_of(labels.table(name), value) in (labels.table(name).get(value), value)


# ------------------------------------------------------------------------------------------ the browser run

def _chromium() -> str | None:
    candidates = [os.environ.get("CHROMIUM")]
    for base in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers"):
        if base:
            candidates += sorted(glob.glob(os.path.join(base, "chromium-*", "chrome-linux*", "chrome")), reverse=True)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            path = playwright.chromium.executable_path
        return path if path and Path(path).is_file() else None
    except Exception:
        return None


def opened_rows(site: Path, catalogue: dict[str, Any]) -> int:
    """The number of rows in the rows file of the run the check opened."""
    doc = json.loads((site / crp.CATALOGUE / catalogue["opened_run_rows_file"]).read_text(encoding="utf-8"))
    return sum(len(part.get("rows") or []) for part in doc["parts"])


def test_the_results_page_check_passes_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright", reason="the playwright package is not installed; the browser check did not run")
    if not (SITE / crp.PAGE).is_file() or not (SITE / crp.INDEX_FILE).is_file():
        pytest.skip(f"no sibling site checkout with {crp.PAGE} and {crp.INDEX_FILE} at {SITE}; the browser check "
                    "did not run")
    browser = _chromium()
    if browser is None:
        pytest.skip("no Chromium executable found (CHROMIUM, PLAYWRIGHT_BROWSERS_PATH, /opt/pw-browsers, Playwright's "
                    "own); the browser check did not run")
    before = crp.input_hashes(SITE)
    receipt_path, shots = tmp_path / "receipt.json", tmp_path / "shots"
    code = crp.main(["--site", str(SITE), "--browser", browser, "--receipt", str(receipt_path), "--shots", str(shots)])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    failed = [check for check in receipt["checks"] if check["result"] in ("failed", "blocked")]
    assert code == crp.EXIT_PASS and receipt["result"] == "passed", failed
    assert tuple(check["name"] for check in receipt["checks"]) == crp.CHECKS
    # A check is passed, or not applicable with its reason. Which ones apply depends on the catalogue, so the
    # test does not fix that; it requires the checks that every catalogue supports to have passed.
    results = {check["name"]: check for check in receipt["checks"]}
    assert {check["result"] for check in receipt["checks"]} <= {"passed", "not_applicable"}
    assert all(check["reason"] for check in receipt["checks"] if check["result"] == "not_applicable")
    counts = receipt["counts"]
    assert counts["checks"] == 69 and counts["failed"] == counts["blocked"] == 0
    assert counts["passed"] + counts["not_applicable"] == 69
    for name in ("count_reads_all_runs_of_the_index", "default_order_is_the_index_order",
                 "search_runs_downloads_and_methods_and_source_are_in_that_order",
                 "download_links_stand_before_the_run_table_and_are_shown_on_load",
                 "shared_status_is_stated_once_and_a_row_adds_only_its_exception",
                 "navigation_marks_this_page_and_its_disclosure_opens_from_the_keyboard",
                 "main_controls_are_reached_by_tab_and_show_a_focus_outline",
                 "a_run_opens_from_the_keyboard", "rendered_rows_are_exactly_the_public_rows_of_the_rows_file",
                 "wordings_are_named_and_every_difference_is_everyday_minus_medical_with_its_sign",
                 "difference_and_status_text_is_neutral_and_no_alert_colour_is_shown",
                 "no_sealed_phrase_in_what_the_open_run_renders", "downloads_are_plain_links",
                 "missing_index_shows_the_error_state_and_no_runs",
                 "failing_rows_file_shows_the_failure_with_a_retry_and_no_rows",
                 "no_horizontal_scroll_at_390_as_loaded", "smallest_visible_text_at_1280_is_at_least_12_px",
                 "smallest_visible_text_at_390_is_at_least_12_px", "no_horizontal_scroll_at_390_with_text_at_200_percent",
                 "no_console_error_page_error_or_failed_request", "no_request_left_the_test_server"):
        assert results[name]["result"] == "passed", name
    # The rows of the opened run were compared with the rows file: counts by sign, no row content.
    rows = results["wordings_are_named_and_every_difference_is_everyday_minus_medical_with_its_sign"]
    assert rows["rows"] == opened_rows(SITE, receipt["catalogue"]) and sum(rows["by_sign"].values()) == rows["rows"]
    assert set(rows["by_sign"]) <= {"negative", "zero", "positive", "missing"}
    shared = results["shared_status_is_stated_once_and_a_row_adds_only_its_exception"]
    assert shared["rows_read"] == min(crp.PAGE_SIZE, receipt["catalogue"]["runs"])
    listed = results["first_page_of_runs_is_rendered"]
    assert listed["experiment_labels_compared"] == listed["rows"] == shared["rows_read"]
    assert 0 <= listed["rows_with_the_stimulus_set_name"] <= listed["rows"]
    assert results["join_instructions_and_field_definitions_open_beside_the_downloads"]["stored_values_listed"] > 0
    assert min(results[name]["smallest_px"] for name in ("smallest_visible_text_at_1280_is_at_least_12_px",
                                                         "smallest_visible_text_at_390_is_at_least_12_px")) >= 12
    # The expectations came from the site's own files.
    index = json.loads((SITE / crp.INDEX_FILE).read_text(encoding="utf-8"))
    runs = crp.listed_runs(index)
    catalogue = receipt["catalogue"]
    assert catalogue["runs"] == len(runs)
    opened = next(run for run in runs if run["run_dir"] == catalogue["opened_run"])
    assert results["rows_load_and_their_number_is_the_index_count"]["rows"] == opened["counts"]["rows_public"]
    assert catalogue["opened_run_sealed_rows"] == opened["counts"]["rows_withheld_sealed"]
    seal = results["no_sealed_phrase_in_what_the_open_run_renders"]
    assert seal["hits"] == [] and seal["sealed_phrases_checked"] > 0
    assert receipt["browser_external_requests"] == [] and receipt["versions"]["chromium"]
    assert sorted(path.name for path in shots.iterdir()) == [
        "results_390.png", "results_methods_source_1280.png", "results_open_run_1280.png", "results_search_1280.png"]
    # Keys and counts only: no path of this machine, and no prompt of the opened run, is in the receipt.
    text = receipt_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in text and str(ROOT) not in text and str(SITE) not in text
    stimuli = SITE / crp.CATALOGUE / str(opened.get("stimuli_file"))
    if stimuli.is_file():
        pairs = json.loads(stimuli.read_text(encoding="utf-8")).get("pairs", {})
        prompts = [value for pair in pairs.values() if isinstance(pair, dict) for value in pair.values()
                   if isinstance(value, str) and len(value) > 20]
        # Counts only, so that a failure of this assertion cannot print a prompt either.
        compared, found = len(prompts), sum(1 for prompt in prompts if prompt in text)
        assert compared > 0 and found == 0
    assert crp.input_hashes(SITE) == before                                # the site was read, not written
