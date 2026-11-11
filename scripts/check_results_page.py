"""Check the results catalogue page in Chromium against the site's own catalogue files. No model, no measurement.

    python scripts/check_results_page.py --site ../patientwords [--browser CHROMIUM] [--port PORT]
        [--receipt FILE] [--shots DIR]

What runs, in order:

1. The site's ``data/results_catalogue/index.json`` is read. Every expectation that depends on data (the number
   of runs, the search term, the filter values, the run that is opened, its row count and its sealed-row count)
   is worked out from that file and from the rows file of the opened run. Nothing of the kind is written in this
   script, so a regenerated catalogue is checked against itself.
2. The site checkout is served in place over HTTP on a loopback port (an ephemeral one unless ``--port`` is
   given), under ``/patientwords/`` as GitHub Pages publishes it. The server answers GET and HEAD only and
   nothing is copied or written: the site is read where it is.
3. Chromium opens the real page, ``results/index.html``, with its real JavaScript, at 1280 x 720 and at
   390 x 844. A request to any other origin is blocked and counted; the count must be zero.
4. The checks in ``CHECKS`` run. A failed check does not stop the later ones.

What the checks are about: what a reader is told and can do. Labels, units and the order of a subtraction; a
zero against a missing value; what is stated once for all runs and what a row adds; the order of the page
(search, runs, downloads, then Methods & source); selection, filters and addresses; the keyboard path and its
focus outline; sideways scrolling at 390 px, also with the text at twice its size. No check requires a number
of rows inside a window, and the floor for visible text is 12 px.

What a check may print or record: check names, run ids, file names, hashes and counts. The page shows published
prompt text in an open run; this script never prints it and never puts it in the receipt. A screenshot taken
with ``--shots`` is a picture of the page, so it shows what a reader sees, published prompt text included. The
seal check runs the engine's own matcher (``scripts/seal_check.py``) over what the open run renders and
reports labels and counts only.

Results of one check: ``passed``; ``failed``; ``not_applicable`` (the catalogue holds no run of the kind the
check needs, for example no partial run; the reason is printed); ``blocked`` (the check could not run, for
example the sealed registry computes empty in this checkout).

Exit codes: 0 no check failed and none was blocked; 1 a check failed; 2 the check could not run (no Chromium,
no page, no catalogue data, the page or the index changed during the run, or one check was blocked). Exit 2 is
a blocked check, not a pass.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import math
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

PAGE = "results/index.html"
CATALOGUE = "data/results_catalogue"
INDEX_FILE = f"{CATALOGUE}/index.json"
DOWNLOADS = ("rows.csv", "stimuli.csv", "index.json")
MOUNT = "/patientwords"
RECEIPT_SCHEMA = "patientwords.results-page-check-receipt/1"
EVIDENCE = "browser check of a static page against the catalogue files it reads"
EXIT_PASS, EXIT_FAILED, EXIT_SETUP = 0, 1, 2
DESKTOP, PHONE = (1280, 720), (390, 844)
WAIT_MS = 8_000
MIN_TEXT_PX = 12

# What the page prints and how it pages. The checks compare rendered text, so these are reader-visible strings;
# tests/test_check_results_page.py fails offline when one of them is no longer in the page source.
PAGE_SIZE = 100
COLUMNS = ("experiment", "model", "measurements", "run status", "study context")
ORDER_DEFAULT, ORDER_DATE, ORDER_NEVER = "run id, A to Z", "batch date, newest first", "never by effect"
SEALED_IN_RUN = "withheld by the Tier B seal (counted, never shown)"
METHODS_SOURCE = "Methods & source"
# An open run states its own labels. Until 2026-11-11 a fifth label read "a listing, not a claim"; the statement is
# made once, in About this catalogue (ABOUT_STATEMENTS), and an open run prints whether an analysis includes it.
RUN_LABELS = ("simulated stimuli", "evidence:", "clinical review:", "sampling:")
# The wordings, as the page names them, and the order of the difference it prints. The files call the two
# wordings clinical and patient; ``language_penalty`` is the patient value minus the clinical one.
ROW_HEADS = ("index", "medical wording", "everyday wording", "target token", "target-token probability",
             "target-token probability", "difference", "notes")
PROBABILITY_SIDES = ("medical wording", "everyday wording")
DIFFERENCE_ORDER = "everyday − medical, in probability"
DIFFERENCE_NOTE = ("minus the medical wording", "0.01 is one percentage point")
NOT_MEASURED = "— not measured"
SHARED_STATUS = ("Simulated stimuli", "not statements from patients", "Clinical review of the stimuli is pending for")
# The primary navigation, and what its disclosure lists.
NAV_PRIMARY = (("Start here", "../start-here/"), ("Scenarios", "../simulated-scenarios/"), ("Results", "./"),
               ("Methods", "../methods.html"))
NAV_MORE = ("Wording differences", "Dialect differences", "Translation", "LLM responses", "Multi-turn",
            "Phrase dataset", "Technical", "Clinical brief", "GitHub")
# The colour the page keeps for a file that failed to load. Nothing may show it while nothing has failed.
ALERT_COLOUR = "rgb(180, 72, 61)"
WORDING_COLOURS = {"medical": "rgb(21, 128, 61)", "everyday": "rgb(17, 24, 39)"}
JOIN_AND_FIELDS = ("join on stem and index", "own_clinical_prompt", "language_penalty", "completion_not_recorded",
                   "recorded_match")
ABOUT_STATEMENTS = ("not a claim", "first encoded target token", "not statements from patients")
EXPLAINED_ONCE = "first encoded target token"
EXCLUDED_PHRASES = ("answer accuracy", "clinical risk", "patient understanding")
STUDY_VERSION = "Study version"
ROWS_FAILED = "could not be loaded (HTTP 404)"
INDEX_FAILED = "HTTP 404"
# What a run's Measurements cell says when the run has no public row, by the run's own index record.
NO_ROWS_RESTRICTED, NO_ROWS_SEALED_ONLY, NO_ROWS_NONE = "no rows published", "0 public rows", "no rows listed"
# Ids the checks read. All must be in the static HTML of the page.
PAGE_IDS = ("main", "about", "cat-loading", "cat-error", "cat-content", "runs", "cat-filters", "f-q", "cat-views",
            "more-btn", "more-filters", "f-evidence", "f-membership", "f-state", "f-rows", "f-review", "f-stimulus",
            "f-visibility", "f-sort", "cat-count", "cat-order", "f-reset", "cat-body", "downloads", "cat-legend",
            "methods-source", "totals", "tot-figs", "restrictions", "restr-body")
# Class names and generated ids the checks read. Each is written by the page's script.
PAGE_HOOKS = ("cat-run", "cat-x", "cat-detail", "c-status", "c-meas", "det-labels", "det-status", "det-src",
              "src-id", "part-sha", "row-table", "sum-dl", "chip-ct", "'view-'+v.id")
# The page's search rule, as written in the page. ``search_text`` below mirrors it; the offline test fails when
# the page's line changes, so that the mirror is changed with it.
PAGE_SEARCH_RULE = ("return (str(r.run_dir)+' '+str(r.stem)+' '+str(r.model)+' '+str(r.instrument)+' '+x.title+' '+",
                    "human(r.evidence_class)+' '+Object.keys(obj(r.execution_states)).map(human).join(' ')).toLowerCase();")

# The check names, in the order they run. The run stops with an error if what was recorded differs from this.
CHECKS: tuple[str, ...] = (
    "search_input_is_inside_the_first_viewport_at_1280x720",
    "search_runs_downloads_and_methods_and_source_are_in_that_order",
    "run_table_has_the_five_columns",
    "count_reads_all_runs_of_the_index",
    "ordering_is_stated_and_never_by_effect",
    "default_order_is_the_index_order",
    "first_page_of_runs_is_rendered",
    "no_filter_is_set_by_default",
    "download_links_stand_before_the_run_table_and_are_shown_on_load",
    "shared_status_is_stated_once_and_a_row_adds_only_its_exception",
    "navigation_marks_this_page_and_its_disclosure_opens_from_the_keyboard",
    "main_controls_are_reached_by_tab_and_show_a_focus_outline",
    "search_narrows_the_list_and_the_count_updates",
    "reset_restores_the_full_list_and_clears_the_search",
    "more_filters_starts_closed",
    "more_filters_opens_from_the_keyboard",
    "a_detailed_filter_narrows_the_list_and_is_shown_as_set",
    "more_filters_closes_from_the_keyboard",
    "partial_view_lists_the_runs_with_a_partial_part",
    "no_rows_view_lists_the_runs_without_public_rows",
    "restricted_view_lists_the_restricted_runs",
    "view_for_empty_unreadable_or_changed_parts_shows_its_count",
    "a_run_opens_from_the_keyboard",
    "rows_load_and_their_number_is_the_index_count",
    "sealed_row_count_is_shown_in_the_open_run",
    "sealed_row_count_is_shown_in_the_run_row",
    "rendered_rows_are_exactly_the_public_rows_of_the_rows_file",
    "open_run_carries_its_stimulus_evidence_review_and_sampling_labels",
    "wordings_are_named_and_every_difference_is_everyday_minus_medical_with_its_sign",
    "difference_and_status_text_is_neutral_and_no_alert_colour_is_shown",
    "open_run_has_a_closed_methods_and_source",
    "run_methods_and_source_opens_from_the_keyboard",
    "run_methods_and_source_shows_the_full_run_id",
    "run_methods_and_source_shows_a_part_sha256",
    "run_methods_and_source_shows_a_part_file_name",
    "no_sealed_phrase_in_what_the_open_run_renders",
    "downloads_are_plain_links",
    "download_target_rows_csv_answers_200",
    "download_target_stimuli_csv_answers_200",
    "download_target_index_json_answers_200",
    "downloads_link_leads_to_the_downloads_section",
    "join_instructions_and_field_definitions_open_beside_the_downloads",
    "page_methods_and_source_starts_closed",
    "methods_and_source_link_opens_it_and_lists_every_restriction",
    "methods_and_source_holds_the_policy_hash_and_release_conditions",
    "about_opens_from_the_keyboard_and_states_the_shared_context",
    "target_token_probability_is_explained_once",
    "page_does_not_say_answer_accuracy",
    "page_does_not_say_clinical_risk",
    "page_does_not_say_patient_understanding",
    "smallest_visible_text_at_1280_is_at_least_12_px",
    "address_parameter_state_is_honoured",
    "address_parameters_evidence_rows_and_membership_are_honoured",
    "address_parameters_q_visibility_and_stimulus_are_honoured",
    "address_parameter_run_opens_a_run_without_rows",
    "anchor_restrictions_opens_methods_and_source",
    "anchor_totals_shows_the_inventory",
    "address_parameter_sort_selects_a_stated_neutral_order",
    "missing_index_shows_the_error_state_and_no_runs",
    "failing_rows_file_shows_the_failure_with_a_retry_and_no_rows",
    "search_input_is_inside_the_first_viewport_at_390x844",
    "no_horizontal_scroll_at_390_as_loaded",
    "no_horizontal_scroll_at_390_with_about_and_more_filters_open",
    "no_horizontal_scroll_at_390_with_a_run_and_its_source_open",
    "no_horizontal_scroll_at_390_with_page_source_and_field_definitions_open",
    "smallest_visible_text_at_390_is_at_least_12_px",
    "no_horizontal_scroll_at_390_with_text_at_200_percent",
    "no_console_error_page_error_or_failed_request",
    "no_request_left_the_test_server",
)


class SetupProblem(Exception):
    """The check could not run. Reported with exit 2; never counted as a pass or as a page failure."""


class NotApplicable(Exception):
    """The catalogue holds no run of the kind one check needs. Recorded with its reason; not a failure."""


class Blocked(Exception):
    """One check could not run in this checkout. Recorded as blocked; the run then exits 2, not 0."""


# ------------------------------------------------------------------------------------------ the page's rules

CLASS_LABEL = {"study_batch": "Study batch", "hand_authored_exploratory": "Hand-authored set",
               "redistribution_limited_text": "Third-party text set"}
_STEM_DATE = re.compile(r"(?:^|_)(\d{4})(\d{2})(\d{2})(T\d*Z?)?(?=_|\Z)", re.ASCII)
_STEM_TIME = re.compile(r"T(\d{2})(\d{2})(\d{2})Z", re.ASCII)
_ROWS_FILE = re.compile(r"rows/[A-Za-z0-9._-]+\.json")
_SHA256 = re.compile(r"[0-9a-f]{64}")
DASH = "—"


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _count(value: Any) -> float:
    """A JSON number, or 0 for anything else, as the page's ``int`` helper reads a count."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def human(value: Any) -> str:
    """How the page prints a schema value: underscores as spaces, a dash for a missing value."""
    return value.replace("_", " ") if isinstance(value, str) and value else DASH


def experiment_title(run: Mapping[str, Any]) -> str:
    """The experiment label the page derives from a run's stem and stimulus class (``experiment`` in the page):
    a family name, then the batch date the stem carries. Mirrored here because the page's search reads it."""
    stem = _text(run.get("stem")) or _text(run.get("run_dir"))
    date, rest = "", stem
    found = _STEM_DATE.search(stem)
    if found and 2000 <= int(found[1]) < 2100 and 1 <= int(found[2]) <= 12 and 1 <= int(found[3]) <= 31:
        date = f"{found[1]}-{found[2]}-{found[3]}"
        clock = _STEM_TIME.fullmatch(found[4] or "")
        if clock and int(clock[1]) < 24 and int(clock[2]) < 60:
            date += f" {clock[1]}:{clock[2]} UTC"
        rest = stem[:found.start()] + "_" + stem[found.end():]
    tokens = [token for token in rest.split("_") if token]
    known = CLASS_LABEL.get(_text(run.get("stimulus_class")), "")
    if known:
        name = known + (" " + " ".join(tokens[1:]) if len(tokens) > 1 else "")
    else:
        name = " ".join(tokens) or stem
        name = name[:1].upper() + name[1:]
    return name + (f" · {date}" if date else "")


def search_text(run: Mapping[str, Any]) -> str:
    """The text the page's search box is matched against for one run (``searchText`` in the page)."""
    states = " ".join(human(key) for key in _mapping(run.get("execution_states")))
    return " ".join([_text(run.get("run_dir")), _text(run.get("stem")), _text(run.get("model")),
                     _text(run.get("instrument")), experiment_title(run), human(run.get("evidence_class")),
                     states]).lower()


def search_matches(run: Mapping[str, Any], query: str) -> bool:
    """Whether the page lists ``run`` for ``query``: every whitespace-separated term is in the run's text."""
    hay = search_text(run)
    return all(term in hay for term in query.lower().split())


def has_rows(run: Mapping[str, Any]) -> bool:
    return _count(_mapping(run.get("counts")).get("rows_public")) > 0


def has_issue(run: Mapping[str, Any]) -> bool:
    """A run with an empty or unreadable part, or a part whose integrity is neither a recorded match nor
    unrecorded (``hasIssue`` in the page)."""
    states = _mapping(run.get("execution_states"))
    if _count(states.get("empty")) > 0 or _count(states.get("unreadable")) > 0:
        return True
    parts = run.get("parts") if isinstance(run.get("parts"), list) else []
    return any(_text(_mapping(part).get("artifact_integrity")) not in ("", "recorded_match", "unrecorded")
               for part in parts)


def no_rows_statement(run: Mapping[str, Any]) -> str:
    """What the Measurements cell of a run without public rows must say, from the run's own record."""
    if run.get("visibility") == "restricted":
        return NO_ROWS_RESTRICTED
    if _count(_mapping(run.get("counts")).get("rows_withheld_sealed")) > 0:
        return NO_ROWS_SEALED_ONLY
    return NO_ROWS_NONE


def count_text(shown: int, total: int) -> str:
    """The start of the count line: the page prints both numbers with thousands separators."""
    return f"{shown:,} of {total:,} runs"


def listed_runs(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The runs the page lists: the index entries that are objects with a non-empty ``run_dir``."""
    runs = index.get("runs") if isinstance(index, dict) else None
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict) and isinstance(run.get("run_dir"), str) and run["run_dir"]]


def public_row_indices(rows_doc: Mapping[str, Any]) -> list[str]:
    """The first-column text of every row of a rows file, sorted: the index, or a dash where it is null."""
    out = []
    for part in rows_doc["parts"]:
        for row in part.get("rows") or []:
            out.append(DASH if row.get("index") is None else str(row["index"]))
    return sorted(out)


def fmt_number(value: float) -> str:
    """Four decimals of the magnitude, as the page's ``fmtNum`` prints a stored value. A magnitude that would
    print as 0.0000 without being zero is printed with an exponent instead."""
    magnitude = abs(value)
    rounded = math.floor(magnitude * 1e4 + 0.5) / 1e4
    if rounded == 0 and value != 0:
        mantissa, exponent = f"{magnitude:.2e}".split("e")
        return f"{mantissa}e{int(exponent)}"
    return f"{rounded:.4f}"


def difference_text(row: Mapping[str, Any]) -> str:
    """What the Difference cell of one row must read: the stored ``language_penalty`` with its sign and the
    sign in words, or the not-measured statement when the row stores none. The page does not recompute the
    value and does not change its sign; zero and missing never share a form."""
    value = row.get("language_penalty")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return NOT_MEASURED
    sign = "−" if value < 0 else "+" if value > 0 else ""
    return f"{sign}{fmt_number(value)} {'negative' if value < 0 else 'positive' if value > 0 else 'zero'}"


def sign_agrees(row: Mapping[str, Any]) -> bool | None:
    """Whether the stored difference has the sign of the everyday (patient) value minus the medical (clinical)
    value. None when the row does not store all three numbers."""
    values = [row.get(name) for name in ("language_penalty", "prob_patient", "prob_clinical")]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        return None
    return abs(values[0] - (values[1] - values[2])) < 1e-9


def shared_review(runs: Sequence[Mapping[str, Any]]) -> str:
    """The clinical-review status most runs record; of two as frequent, the one the index lists first. The
    page states it once above the list (``SHARED_REVIEW`` in the page)."""
    counts: Counter[str] = Counter()
    order: list[str] = []
    for run in runs:
        key = _text(run.get("clinical_review")) or "not recorded"
        if key not in counts:
            order.append(key)
        counts[key] += 1
    return max(order, key=lambda key: (counts[key], -order.index(key))) if order else ""


# ------------------------------------------------------------------------------------------ expectations

def load_catalogue(site: Path) -> dict[str, Any]:
    """The site's catalogue index. ``SetupProblem`` when it is absent, unreadable or lists no run."""
    path = site / INDEX_FILE
    if not path.is_file():
        raise SetupProblem(f"the site has no {INDEX_FILE}; there is no catalogue data to check the page against")
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupProblem(f"{INDEX_FILE} could not be read as JSON ({type(exc).__name__})") from exc
    if not listed_runs(index):
        raise SetupProblem(f"{INDEX_FILE} lists no run; there is no catalogue data to check the page against")
    return index


def pick_search_term(runs: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]] | None:
    """A search term that narrows the list, and the run ids the page must then list, in index order.

    The term is the model name that selects the most runs while leaving at least one out (ties: the first
    name). When no model name does that, a stem and then a run id is tried. None when no term narrows the list.
    """
    total = len(runs)
    for key in ("model", "stem", "run_dir"):
        best: tuple[int, str, list[str]] | None = None
        for term in sorted({_text(run.get(key)) for run in runs}):
            if not term or term != term.strip() or len(term.split()) != 1:
                continue
            matched = [run["run_dir"] for run in runs if search_matches(run, term)]
            if 0 < len(matched) < total and (best is None or len(matched) > best[0]):
                best = (len(matched), term, matched)
        if best is not None:
            return best[1], best[2]
    return None


def pick_open_run(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The run the check opens: public, one part with a recorded SHA-256, public rows in a rows file, and a
    run id that the page's search matches for this run alone. A run with sealed rows is preferred, so that the
    sealed count has something to show. ``SetupProblem`` when the catalogue holds no such run."""
    def usable(run: Mapping[str, Any]) -> bool:
        parts = run.get("parts") if isinstance(run.get("parts"), list) else []
        return (has_rows(run) and run.get("visibility") != "restricted" and run.get("n_parts") == 1
                and len(parts) == 1 and isinstance(parts[0], dict) and bool(_text(parts[0].get("name")))
                and bool(_SHA256.fullmatch(_text(parts[0].get("sha256"))))
                and bool(_ROWS_FILE.fullmatch(_text(run.get("rows_file"))))
                and len(run["run_dir"].split()) == 1
                and sum(1 for other in runs if search_matches(other, run["run_dir"])) == 1)

    fallback = None
    for run in runs:
        if not has_rows(run):
            continue
        sealed = _count(_mapping(run.get("counts")).get("rows_withheld_sealed")) > 0
        if (sealed or fallback is None) and usable(run):
            if sealed:
                return dict(run)
            fallback = dict(run)
    if fallback is None:
        raise SetupProblem("the catalogue has no public run with one part, public rows and a run id that selects "
                           "it alone; the open-run checks cannot run")
    return fallback


def pick_evidence_class(runs: Sequence[Mapping[str, Any]], default_membership: str) -> tuple[str, int, int]:
    """``(evidence class, runs of that class, runs of that class with public rows inside the default
    membership)``. The class with the most runs of the third kind is taken, then the most runs, then the name,
    so that the combined address-parameter check has runs to list where the catalogue has any."""
    classes = Counter(_text(run.get("evidence_class")) for run in runs if _text(run.get("evidence_class")))
    if not classes:
        raise SetupProblem("no run of the catalogue records an evidence class")
    def combined(name: str) -> int:
        return sum(1 for run in runs if run.get("evidence_class") == name and has_rows(run)
                   and _count(_mapping(run.get("analysis_parts")).get(default_membership)) > 0)
    name = sorted(classes, key=lambda key: (-combined(key), -classes[key], key))[0]
    return name, classes[name], combined(name)


def pick_run_without_rows(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """A run with no rows file whose first part records a SHA-256: a partial run when there is one, else any."""
    def usable(run: Mapping[str, Any]) -> bool:
        parts = run.get("parts") if isinstance(run.get("parts"), list) else []
        return (not run.get("rows_file") and bool(parts) and isinstance(parts[0], dict)
                and bool(_SHA256.fullmatch(_text(parts[0].get("sha256")))))
    candidates = [run for run in runs if usable(run)]
    partial_runs = [run for run in candidates if _count(_mapping(run.get("execution_states")).get("partial")) > 0]
    chosen = (partial_runs or candidates or [None])[0]
    return dict(chosen) if chosen is not None else None


@dataclass
class Expected:
    """Everything the checks expect, worked out from the site's index before the browser starts."""
    index: dict[str, Any]
    runs: list[dict[str, Any]]
    search: tuple[str, list[str]] | None
    evidence: tuple[str, int, int]
    partial: list[str]
    no_rows: list[str]
    restricted: list[str]
    issue: int
    open_run: dict[str, Any]
    sealed: int
    run_without_rows: dict[str, Any] | None
    query_filter: tuple[str, str, int] | None

    @property
    def total(self) -> int:
        return len(self.runs)

    @property
    def run_ids(self) -> list[str]:
        return [run["run_dir"] for run in self.runs]

    def summary(self) -> dict[str, Any]:
        """Keys and counts for the receipt. No row content."""
        return {
            "runs": self.total,
            "search_term": self.search[0] if self.search else None,
            "search_runs": len(self.search[1]) if self.search else None,
            "evidence_class": self.evidence[0], "evidence_runs": self.evidence[1],
            "evidence_runs_with_rows_in_the_default_membership": self.evidence[2],
            "partial_runs": len(self.partial), "runs_without_public_rows": len(self.no_rows),
            "restricted_runs": len(self.restricted), "runs_with_an_empty_unreadable_or_changed_part": self.issue,
            "opened_run": self.open_run["run_dir"], "opened_run_rows_file": self.open_run["rows_file"],
            "opened_run_public_rows": _count(self.open_run["counts"]["rows_public"]),
            "opened_run_sealed_rows": self.sealed,
            "run_without_rows": self.run_without_rows["run_dir"] if self.run_without_rows else None,
        }


def expectations(index: dict[str, Any]) -> Expected:
    runs = listed_runs(index)
    search = pick_search_term(runs)
    default_membership = _text(_mapping(index.get("policy")).get("default_membership"))
    open_run = pick_open_run(runs)
    query_filter = None
    if search is not None:
        by_id = {run["run_dir"]: run for run in runs}
        pairs = Counter((_text(by_id[name].get("visibility")), _text(by_id[name].get("stimulus_class")))
                        for name in search[1])
        usable = sorted((pair for pair in pairs if all(pair)), key=lambda pair: (-pairs[pair], pair))
        if usable:
            query_filter = (usable[0][0], usable[0][1], pairs[usable[0]])
    return Expected(
        index=index, runs=runs, search=search, evidence=pick_evidence_class(runs, default_membership),
        partial=[run["run_dir"] for run in runs if _count(_mapping(run.get("execution_states")).get("partial")) > 0],
        no_rows=[run["run_dir"] for run in runs if not has_rows(run)],
        restricted=[run["run_dir"] for run in runs if run.get("visibility") == "restricted"],
        issue=sum(1 for run in runs if has_issue(run)), open_run=open_run,
        sealed=int(_count(_mapping(open_run.get("counts")).get("rows_withheld_sealed"))),
        run_without_rows=pick_run_without_rows(runs), query_filter=query_filter)


# ------------------------------------------------------------------------------------------ receipt

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def identity(root: Path, excluded: Path | None = None) -> dict[str, Any]:
    """HEAD and tracked-diff identity of a checkout. Paths never enter the result. A directory that is not a
    Git checkout, or a failing ``git``, gives ``head: None`` with the reason; nothing is guessed."""
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)
    try:
        if Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() != root.resolve():
            return {"head": None, "not_recorded": "this directory is not the root of a Git checkout"}
        head = git("rev-parse", "HEAD").decode().strip()
        exclusions = ["."]
        if excluded is not None and excluded.is_relative_to(root):
            exclusions.append(f":(exclude){excluded.relative_to(root)}")
        diff = git("diff", "--binary", "HEAD", "--", *exclusions)
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"head": None, "not_recorded": f"git could not describe this directory: {type(exc).__name__}"}
    return {"head": head, "tracked_diff_sha256": sha256_bytes(diff), "tracked_files_differ_from_head": bool(diff)}


def input_hashes(site: Path) -> dict[str, str | None]:
    """SHA-256 of the two files every check depends on. Compared before and after the browser run."""
    return {name: sha256_file(site / name) if (site / name).is_file() else None for name in (PAGE, INDEX_FILE)}


def new_receipt(site: Path, receipt_path: Path | None) -> dict[str, Any]:
    tools = [Path(__file__).resolve(), ROOT / "scripts" / "seal_check.py"]
    return {
        "schema": RECEIPT_SCHEMA,
        "evidence": EVIDENCE,
        "statement": "The results catalogue page was opened in Chromium from a local server and compared with the "
                     "catalogue files of the same site. Nothing was measured, written, published or deployed.",
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "python scripts/check_results_page.py --site SITE [--browser CHROMIUM] [--port PORT] "
                   "[--receipt RECEIPT] [--shots SHOTS]",
        "engine": identity(ROOT, receipt_path),
        "frontend": identity(site, receipt_path),
        "input_sha256": input_hashes(site),
        "tool_sha256": {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in tools if path.is_file()},
        "versions": {"python": sys.version.split()[0], "playwright": None, "chromium": None},
        "viewports": {"desktop": list(DESKTOP), "phone": list(PHONE)},
        "catalogue": None,
        "checks": [],
        "screenshots": [],
        "browser_external_requests": [],
        "result": "not_run",
    }


@dataclass
class Recorder:
    """Runs named checks and files each result in the receipt. A failed check does not stop the later ones."""
    receipt: dict[str, Any]
    failed: int = 0
    blocked: int = 0
    not_applicable: int = 0

    def _file(self, name: str, result: str, mark: str, detail: Mapping[str, Any], note: str = "") -> None:
        self.receipt["checks"].append({"name": name, "result": result, **detail})
        print(f"{mark} {name}" + (f": {note}" if note else ""))

    def run(self, name: str, action: Callable[[], Mapping[str, Any] | None]) -> bool:
        try:
            detail = dict(action() or {})
        except SetupProblem:
            raise
        except NotApplicable as exc:
            self.not_applicable += 1
            self._file(name, "not_applicable", "n/a ", {"reason": str(exc)}, str(exc))
            return True
        except Blocked as exc:
            self.blocked += 1
            self._file(name, "blocked", "BLOCKED", {"reason": str(exc)}, str(exc))
            return False
        except Exception as exc:  # an assertion, or a browser timeout while waiting for a state
            self.fail(name, type(exc).__name__, str(exc))
            return False
        self._file(name, "passed", "ok  ", detail)
        return True

    def fail(self, name: str, exception: str, message: str) -> None:
        """File a failure. Only the first line of the message is kept."""
        self.failed += 1
        first = message.strip().splitlines()[0][:400] if message.strip() else ""
        self._file(name, "failed", "FAIL", {"exception": exception, "message": first}, f"{exception}: {first}")


def exit_code(failed: int, blocked: int) -> int:
    """1 when a check failed; else 2 when a check was blocked; else 0. A blocked check is never a pass."""
    return EXIT_FAILED if failed else EXIT_SETUP if blocked else EXIT_PASS


# ------------------------------------------------------------------------------------------ HTTP

class Handler(http.server.SimpleHTTPRequestHandler):
    """Static, read-only HTTP for one site checkout, mounted at ``MOUNT``. A path outside the mount is 404.
    Conditional requests are answered in full and nothing is cacheable."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def send_head(self) -> Any:
        route = urlsplit(self.path).path
        if route != MOUNT and not route.startswith(MOUNT + "/"):
            self.send_error(404, "outside the served site")
            return None
        for name in ("If-Modified-Since", "If-None-Match"):
            if name in self.headers:
                del self.headers[name]
        return super().send_head()

    def translate_path(self, path: str) -> str:
        return super().translate_path(path[len(MOUNT):] or "/")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(site: Path, port: int) -> http.server.ThreadingHTTPServer:
    """A server for ``site`` on 127.0.0.1. ``port`` 0 asks the system for a free port."""
    try:
        return http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(site)))
    except OSError as exc:
        raise SetupProblem(f"could not listen on 127.0.0.1 port {port}: {exc}") from exc


def head_status(url: str) -> int:
    """The status of a HEAD request to the test server. No proxy is used for it."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url, method="HEAD"), timeout=20) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


# ------------------------------------------------------------------------------------------ browser helpers

LOAD_STATE = """() => {
    const top = (node) => node.getBoundingClientRect().top + scrollY;
    const bottom = (node) => node.getBoundingClientRect().bottom + scrollY;
    const text = (id) => { const node = document.getElementById(id); return node ? node.innerText.trim() : null; };
    const query = document.getElementById('f-q'), links = document.querySelector('.sum-dl');
    const more = document.getElementById('more-filters'), restrictions = document.getElementById('restrictions');
    const rows = Array.from(document.querySelectorAll('#cat-body tr.cat-run'));
    const before = (a, b) => !!a && !!b && !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const shown = (node) => !!node && node.checkVisibility();
    const shared = document.getElementById('cat-review');
    return {
        search: query ? [top(query), bottom(query)] : null,
        page_order: {
            search_before_runs: before(query, rows[0]),
            runs_before_downloads: before(rows[rows.length - 1], document.getElementById('downloads')),
            downloads_before_methods_and_source: before(document.getElementById('downloads'),
                                                       document.getElementById('methods-source')),
            shared_status_before_search: before(shared, query),
        },
        tops: {search: query ? Math.round(top(query)) : null, first_run: rows[0] ? Math.round(top(rows[0])) : null},
        first_run_shown: shown(rows[0]),
        downloads: links ? [top(links), bottom(links)] : null,
        downloads_before_table: before(links, document.getElementById('cat-body')),
        downloads_shown: shown(links),
        shared: shared && shown(shared) ? shared.innerText.trim() : null,
        context: rows.map((row) => {
            const cell = row.querySelector('td.c-ctx');
            const own = cell.querySelector('[data-exception="review"]');
            return [row.getAttribute('data-run'), own ? own.innerText.trim() : null, row.innerText];
        }),
        heads: Array.from(document.querySelectorAll('.cat-table > thead th')).map(
            (th) => th.innerText.split('\\n')[0].trim().toLowerCase()),
        count: text('cat-count'),
        order: text('cat-order'),
        runs: rows.map((row) => row.getAttribute('data-run')),
        selects: Array.from(document.querySelectorAll('#cat-filters select')).map((select) => select.value),
        query: query ? query.value : null,
        more_filters_hidden: more ? more.getClientRects().length === 0 : null,
        restrictions_hidden: restrictions ? restrictions.getClientRects().length === 0 : null,
        scroll: [document.documentElement.scrollWidth, document.documentElement.clientWidth],
    };
}"""

RUN_IDS = "() => Array.from(document.querySelectorAll('#cat-body tr.cat-run')).map((row) => row.getAttribute('data-run'))"

SMALLEST_TEXT = """() => {
    let smallest = 999, where = '';
    const seen = (px, label) => { if (px < smallest) { smallest = px; where = label; } };
    for (const node of document.querySelectorAll('body *')) {
        if (node.closest('svg') || !node.checkVisibility()) continue;        // a closed fold's content is not shown
        const style = getComputedStyle(node), box = node.getBoundingClientRect();
        if (style.visibility === 'hidden' || box.right <= 0) continue;        // parked off screen for a screen reader
        const name = node.tagName.toLowerCase() + (typeof node.className === 'string' && node.className
            ? '.' + node.className.split(' ')[0] : '');
        if (Array.from(node.childNodes).some((child) => child.nodeType === 3 && child.textContent.trim())) {
            seen(parseFloat(style.fontSize), name);
        }
        // labels a stylesheet prints, such as the label above a value in the narrow layout
        for (const pseudo of ['::before', '::after']) {
            const part = getComputedStyle(node, pseudo);
            if (part.content && part.content !== 'none' && part.content !== 'normal' && part.display !== 'none'
                && /[A-Za-z0-9]/.test(part.content)) seen(parseFloat(part.fontSize), name + pseudo);
        }
    }
    return {smallest, where};
}"""


# Text only, twice the size: every element's computed font size is doubled in place and the window keeps its
# width. This is what a reader's 200 % text setting asks of the layout.
DOUBLE_TEXT = """() => {
    const nodes = Array.from(document.body.querySelectorAll('*')).filter((node) => !(node instanceof SVGElement));
    const sizes = nodes.map((node) => parseFloat(getComputedStyle(node).fontSize));
    nodes.forEach((node, i) => node.style.setProperty('font-size', (sizes[i] * 2) + 'px', 'important'));
    return nodes.length;
}"""

NAV_STATE = """() => {
    const nav = document.querySelector('.masthead nav'), more = nav.querySelector('details.nav-more');
    const list = more.querySelector('.nav-more-list'), box = list.getBoundingClientRect();
    const first = document.body.firstElementChild;
    return {
        primary: Array.from(nav.children).filter((n) => n.tagName === 'A').map((a) => [a.textContent.trim(),
            a.getAttribute('href'), a.getAttribute('aria-current')]),
        open: more.open,
        summary: more.querySelector('summary').textContent.trim(),
        more: Array.from(list.querySelectorAll('a')).map((a) => [a.textContent.trim(), a.getAttribute('href'),
            a.checkVisibility()]),
        list_inside_window: !list.checkVisibility() || (box.left >= 0 && box.right <= window.innerWidth + 0.5),
        focus_in_list: !!document.activeElement.closest('.nav-more-list'),
        skip: [first.className, first.getAttribute('href')],
    };
}"""

FOCUS = """() => {
    const node = document.activeElement, style = getComputedStyle(node), box = node.getBoundingClientRect();
    return {
        tag: node.tagName, id: node.id || null, cls: typeof node.className === 'string' ? node.className : '',
        text: (node.innerText || node.value || '').trim().split('\\n')[0].slice(0, 60),
        parent: node.parentElement ? (node.parentElement.id || node.parentElement.className || '') : '',
        in_nav: !!node.closest('.masthead nav'), download: node.hasAttribute('download'),
        outline: style.outlineStyle, width: parseFloat(style.outlineWidth),
        in_view: box.bottom > 0 && box.top < window.innerHeight && box.right > 0 && box.left < window.innerWidth,
    };
}"""
# The controls a reader of the catalogue uses, in Tab order: name, and how the focused element is known.
MAIN_CONTROLS: tuple[tuple[str, Callable[[Mapping[str, Any]], bool]], ...] = (
    ("skip link", lambda stop: stop["cls"] == "skip"),
    ("first navigation link", lambda stop: stop["in_nav"] and stop["tag"] == "A"),
    ("navigation disclosure", lambda stop: stop["tag"] == "SUMMARY" and stop["parent"] == "nav-more"),
    ("About this catalogue", lambda stop: stop["tag"] == "SUMMARY" and stop["parent"] == "about"),
    ("search box", lambda stop: stop["id"] == "f-q"),
    ("view of all runs", lambda stop: stop["id"] == "view-all"),
    ("More filters", lambda stop: stop["id"] == "more-btn"),
    ("Reset", lambda stop: stop["id"] == "f-reset"),
    ("download link", lambda stop: stop["download"]),
    ("first run", lambda stop: stop["tag"] == "BUTTON" and "cat-x" in stop["cls"].split()),
)


def tab_stops(page: Any, limit: int = 40) -> list[dict[str, Any]]:
    """Press Tab up to ``limit`` times from the top of a fresh page and describe each element that takes focus."""
    stops = []
    for _ in range(limit):
        page.keyboard.press("Tab")
        stop = page.evaluate(FOCUS)
        if stop["tag"] in ("BODY", "HTML"):
            break
        stops.append(stop)
    return stops


def assert_focus(stops: Sequence[Mapping[str, Any]],
                 controls: Sequence[tuple[str, Callable[[Mapping[str, Any]], bool]]]) -> dict[str, Any]:
    """Every named control is reached by Tab, in the order given, and shows a focus outline when it is: a solid
    outline at least 2 CSS px wide, read from the focused element after a real key press, on an element that is
    inside the window."""
    position, reached = 0, {}
    for name, known in controls:
        index = next((i for i in range(position, len(stops)) if known(stops[i])), None)
        assert index is not None, f"Tab does not reach the {name} (after {position} of {len(stops)} stops)"
        stop = stops[index]
        assert stop["outline"] == "solid" and stop["width"] >= 2, (
            f"the {name} shows no focus outline: {stop['outline']} {stop['width']} px")
        assert stop["in_view"], f"the {name} takes focus outside the window"
        reached[name], position = index + 1, index + 1
    unmarked = [stop["text"] or stop["tag"] for stop in stops if stop["outline"] != "solid" or stop["width"] < 2]
    assert not unmarked, f"{len(unmarked)} Tab stop(s) show no focus outline; first: {unmarked[:2]}"
    return {"tab_stops_read": len(stops), "reached_at_tab_press": reached}


OPEN_RUN_ROWS = """() => {
    const detail = document.querySelector('#cat-body tr.cat-detail');
    const table = detail.querySelector('table.row-table');
    return {
        heads: Array.from(table.querySelectorAll(':scope > thead th')).map((th) => th.innerText.trim().split('\\n').map(
            (line) => line.trim())),
        rows: Array.from(table.querySelectorAll(':scope > tbody > tr')).map((tr) => {
            const cells = Array.from(tr.children);
            return {index: cells[0].innerText.trim(), medical: cells[4].innerText.trim(),
                    everyday: cells[5].innerText.trim(), difference: cells[6].innerText.trim().replace(/\\s+/g, ' '),
                    sign: cells[6].querySelector('[data-sign]') ? cells[6].querySelector('[data-sign]').dataset.sign : null,
                    labels: cells.map((cell) => cell.getAttribute('data-l'))};
        }),
        note: detail.querySelector('.det-foot') ? detail.querySelector('.det-foot').innerText : '',
    };
}"""

COLOURS = """(alert) => {
    const shown = (node) => node.checkVisibility();
    const main = document.querySelector('main');
    const alerts = [];
    for (const node of main.querySelectorAll('*')) {
        if (!shown(node)) continue;
        const style = getComputedStyle(node);
        const border = parseFloat(style.borderTopWidth) > 0 || parseFloat(style.borderLeftWidth) > 0;
        if (style.color === alert || (border && (style.borderTopColor === alert || style.borderLeftColor === alert))
            || style.backgroundColor === alert) {
            alerts.push(node.tagName.toLowerCase() + (typeof node.className === 'string' && node.className
                ? '.' + node.className.split(' ')[0] : ''));
        }
    }
    const colour = (selector) => Array.from(new Set(Array.from(main.querySelectorAll(selector)).filter(shown).map(
        (node) => getComputedStyle(node).color)));
    return {
        alerts,
        ink: getComputedStyle(document.body).color,
        difference: colour('table.row-table td.r-pen, table.row-table td.r-pen *'),
        probability: colour('table.row-table td.num, table.row-table td.num *'),
        signs: colour('#cat-body td.c-meas .sg, #cat-body td.c-meas .sg *'),
        status: colour('#cat-body td.c-status, #cat-body td.c-status *'),
        medical: colour('table.row-table td.r-c .r-prompt'),
        everyday: colour('table.row-table td.r-p .r-prompt'),
    };
}"""


@dataclass
class Session:
    base: str
    site: Path
    expected: Expected
    desktop: Any
    phone: Any
    receipt: dict[str, Any]
    shots: Path | None
    errors: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{self.base}/results/"

    def page(self, context: Any, *, watched: bool = True) -> Any:
        """A new page. With ``watched`` its console errors, page errors and HTTP errors count against the
        last-but-one check; the two error-state pages are opened without it, because their errors are wanted."""
        page = context.new_page()
        if watched:
            page.on("pageerror", lambda error: self.errors.append("page error: " + str(error).splitlines()[0][:200]))
            page.on("console", lambda message: self.errors.append("console error: " + message.text[:200])
                    if message.type == "error" else None)
            page.on("response", lambda response: self.errors.append(f"HTTP {response.status} {response.url}")
                    if response.status >= 400 else None)
            page.on("requestfailed", lambda request: self.errors.append(f"request failed: {request.url}"))
        return page

    def load(self, page: Any, query: str = "") -> None:
        page.goto(self.url + query, wait_until="networkidle", timeout=45_000)
        page.wait_for_selector("#cat-body tr")

    def wait_count(self, page: Any, shown: int) -> None:
        """Wait until the count line starts with ``shown`` of all runs. A timeout is the failure."""
        page.wait_for_function("(text) => document.getElementById('cat-count').textContent.indexOf(text) === 0",
                               arg=count_text(shown, self.expected.total))

    def shot(self, page: Any, name: str) -> None:
        if self.shots is None:
            return
        self.shots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(self.shots / name))
        self.receipt["screenshots"].append({"file": name, "sha256": sha256_file(self.shots / name),
                                            "device_scale_factor": 2})


def shown_runs(page: Any) -> list[str]:
    return page.evaluate(RUN_IDS)


def first_page(run_ids: Sequence[str]) -> list[str]:
    return list(run_ids[:PAGE_SIZE])


def need(scope: Any, *selectors: str) -> None:
    """Fail at once, with the selector, when an element a check is about to use is not on the page. Without
    this a missing element is reported only as a timeout of the action that needed it."""
    missing = [selector for selector in selectors if scope.locator(selector).count() == 0]
    assert not missing, f"the page has no element for {missing}"


def no_horizontal_scroll(page: Any) -> dict[str, Any]:
    scroll, client = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert scroll <= client, f"the page scrolls sideways: scrollWidth {scroll}, clientWidth {client}"
    return {"scroll_width": scroll, "client_width": client}


def opened(recorder: Recorder, names: Sequence[str], opener: Callable[[], Any]) -> Any:
    """Open the page of a group of checks. When it does not load, every check of the group is filed as failed
    with that reason, and None is returned."""
    try:
        return opener()
    except SetupProblem:
        raise
    except Exception as exc:
        for name in names:
            recorder.fail(name, type(exc).__name__, "not reached: the page of this group did not load: "
                               + (str(exc).strip().splitlines()[0][:200] if str(exc).strip() else ""))
        return None


def group(start: str, end: str) -> tuple[str, ...]:
    """The check names from ``start`` to ``end``, both included, in ``CHECKS`` order."""
    return CHECKS[CHECKS.index(start):CHECKS.index(end) + 1]


# ------------------------------------------------------------------------------------------ checks: the list

def check_first_view(s: Session, recorder: Recorder) -> None:
    names = group("search_input_is_inside_the_first_viewport_at_1280x720",
                  "main_controls_are_reached_by_tab_and_show_a_focus_outline")
    x, height = s.expected, DESKTOP[1]

    def start() -> Any:
        page = s.page(s.desktop)
        s.load(page)
        return page
    page = opened(recorder, names, start)
    if page is None:
        return
    try:
        state = page.evaluate(LOAD_STATE)

        def search_in_view() -> dict[str, Any]:
            assert state["search"] is not None, "the page has no #f-q search input"
            assert state["search"][1] <= height, f"the search input ends at {state['search'][1]:.0f} px, below {height}"
            return {"top": round(state["search"][0]), "bottom": round(state["search"][1])}

        def page_order() -> dict[str, Any]:
            # Until 2026-11-11 this check required the first three rows to end inside a 720 px window, which
            # paid for small text. It now requires the order of the page, and that the first run is shown on
            # load without opening anything. Positions go into the receipt; none is required.
            wrong = [name.replace("_", " ") for name, holds in state["page_order"].items() if not holds]
            assert not wrong, f"document order does not hold: {wrong}"
            assert state["first_run_shown"], "the first run is not shown when the page loads"
            return {"order": "shared status, search, runs, downloads, methods and source",
                    "top_in_css_px_at_1280": state["tops"]}

        def columns() -> dict[str, Any]:
            assert state["heads"] == list(COLUMNS), f"column heads: {state['heads']}"
            return {"columns": state["heads"]}

        def count() -> dict[str, Any]:
            assert state["count"] is not None and state["count"].startswith(count_text(x.total, x.total)), (
                f"the count line does not start with {count_text(x.total, x.total)!r}")
            return {"count": state["count"]}

        def ordering() -> dict[str, Any]:
            order = state["order"] or ""
            assert ORDER_DEFAULT in order and ORDER_NEVER in order, "the ordering line does not state the order"
            return {"order": order}

        def default_order() -> dict[str, Any]:
            assert state["runs"] == first_page(x.run_ids), "the rows are not in the order of the index"
            return {"first_run": state["runs"][0], "rows_compared": len(state["runs"])}

        def one_page() -> dict[str, Any]:
            assert len(state["runs"]) == min(PAGE_SIZE, x.total), f"{len(state['runs'])} rows rendered"
            return {"rows": len(state["runs"])}

        def defaults() -> dict[str, Any]:
            assert state["selects"] and all(value == "" for value in state["selects"]) and state["query"] == "", (
                "a filter is set when the page loads")
            return {"selects": len(state["selects"])}

        def downloads_before_table() -> dict[str, Any]:
            # Until 2026-11-11: the download line had to end inside a 720 px window. Now: it stands before the
            # run table, beside the count, and is shown on load.
            assert state["downloads"] is not None, "the page has no .sum-dl download line"
            assert state["downloads_before_table"] and state["downloads_shown"], (
                "the download line is not before the run table, or is not shown on load")
            return {"top": round(state["downloads"][0])}

        def shared_status() -> dict[str, Any]:
            runs = x.runs
            pending = sum(1 for run in runs if _text(run.get("clinical_review")).endswith("pending"))
            shared = state["shared"] or ""
            missing = [text for text in SHARED_STATUS if text not in shared]
            assert not missing, f"the shared status above the list lacks {missing}"
            wanted = f"all {len(runs):,} runs" if pending == len(runs) else f"{pending:,} of {len(runs):,} runs"
            assert wanted in shared, f"the shared status does not say that review is pending for {wanted}"
            common = shared_review(runs)
            by_id = {run["run_dir"]: run for run in runs}
            exceptions = repeated = 0
            for name, own, text in state["context"]:
                differs = (_text(by_id[name].get("clinical_review")) or "not recorded") != common
                if differs:
                    assert own == "review: " + human(by_id[name].get("clinical_review")), (
                        f"the row of {name} does not state its own review status")
                    exceptions += 1
                else:
                    assert own is None, f"the row of {name} repeats the review status every run shares"
                repeated += any(word in text.lower() for word in ("simulated", "not statements from patients"))
            assert repeated == 0, f"{repeated} row(s) repeat the status stated once above the list"
            return {"review_pending_runs": pending, "shared_review_status": common, "rows_read": len(state["context"]),
                    "rows_with_their_own_review_status": exceptions}

        def navigation() -> dict[str, Any]:
            found = page.evaluate(NAV_STATE)
            assert [tuple(item[:2]) for item in found["primary"]] == list(NAV_PRIMARY), found["primary"]
            current = [label for label, _href, mark in found["primary"] if mark == "page"]
            assert current == ["Results"], f"aria-current marks {current}"
            assert not found["open"] and found["summary"] == "More", "the disclosure is open on load"
            assert [label for label, _href, _shown in found["more"]] == list(NAV_MORE), found["more"]
            assert not any(shown for _label, _href, shown in found["more"]), "a closed disclosure shows its links"
            assert not [href for _l, href, _s in found["more"] if "experiments" in href], "the navigation links experiments"
            assert found["skip"] == ["skip", "#main"], f"the first element of the page is {found['skip']}"
            page.focus(".masthead nav details.nav-more > summary")
            page.keyboard.press("Enter")
            opened = page.evaluate(NAV_STATE)
            assert opened["open"] and all(shown for _label, _href, shown in opened["more"]), (
                "Enter on the summary did not show the supporting pages")
            assert opened["list_inside_window"], "the open list leaves the window"
            page.keyboard.press("Tab")
            assert page.evaluate(NAV_STATE)["focus_in_list"], "Tab does not enter the open list"
            page.focus(".masthead nav details.nav-more > summary")
            page.keyboard.press("Enter")
            assert not page.evaluate(NAV_STATE)["open"], "Enter did not close the disclosure"
            return {"primary": [label for label, _href in NAV_PRIMARY], "supporting": len(NAV_MORE)}

        def focus() -> dict[str, Any]:
            # A fresh page: Tab must start from the top of the document.
            fresh = s.page(s.desktop)
            try:
                s.load(fresh)
                return assert_focus(tab_stops(fresh), MAIN_CONTROLS)
            finally:
                fresh.close()

        for name, action in zip(names, (search_in_view, page_order, columns, count, ordering, default_order,
                                        one_page, defaults, downloads_before_table, shared_status, navigation,
                                        focus), strict=True):
            recorder.run(name, action)
    finally:
        page.close()


def check_filters(s: Session, recorder: Recorder) -> None:
    names = group("search_narrows_the_list_and_the_count_updates",
                  "view_for_empty_unreadable_or_changed_parts_shows_its_count")
    x = s.expected

    def start() -> Any:
        page = s.page(s.desktop)
        s.load(page)
        return page
    page = opened(recorder, names, start)
    if page is None:
        return

    def show_all() -> None:
        need(page, "#view-all")
        page.locator("#view-all").click()
        s.wait_count(page, x.total)

    def search() -> dict[str, Any]:
        if x.search is None:
            raise NotApplicable(f"no model name, stem or run id narrows a list of {x.total} run(s)")
        term, wanted = x.search
        need(page, "#f-q", "#cat-count")
        page.locator("#f-q").focus()
        page.keyboard.type(term)
        s.wait_count(page, len(wanted))
        assert shown_runs(page) == first_page(wanted), "the rows listed are not the runs the search rule selects"
        s.shot(page, "results_search_1280.png")
        return {"term": term, "runs": len(wanted)}

    def reset() -> dict[str, Any]:
        if x.search is None:
            raise NotApplicable("no search was made, so there is nothing to reset")
        need(page, "#f-reset")
        page.locator("#f-reset").focus()
        page.keyboard.press("Enter")
        s.wait_count(page, x.total)
        assert page.locator("#f-q").input_value() == "", "the search box still holds text"
        assert shown_runs(page) == first_page(x.run_ids), "the full list did not come back in index order"
        return {"runs": x.total}

    def more_closed() -> dict[str, Any]:
        need(page, "#more-filters", "#more-btn")
        assert page.locator("#more-filters").is_hidden(), "More filters is open before it was asked for"
        assert page.locator("#more-btn").get_attribute("aria-expanded") == "false", "aria-expanded is not false"
        return {}

    def more_opens() -> dict[str, Any]:
        need(page, "#more-filters", "#more-btn")
        page.locator("#more-btn").focus()
        page.keyboard.press("Enter")
        assert page.locator("#more-filters").is_visible(), "Enter on More filters did not show the filters"
        assert page.locator("#more-btn").get_attribute("aria-expanded") == "true", "aria-expanded is not true"
        return {"key": "Enter"}

    def detailed_filter() -> dict[str, Any]:
        name, wanted, _combined = x.evidence
        need(page, "#f-evidence", "#more-btn")
        page.locator("#f-evidence").focus()
        page.locator("#f-evidence").select_option(name)
        s.wait_count(page, wanted)
        assert "1 set" in page.locator("#more-btn").inner_text(), "More filters does not say that one filter is set"
        return {"evidence_class": name, "runs": wanted}

    def more_closes() -> dict[str, Any]:
        need(page, "#more-filters", "#more-btn")
        if page.locator("#more-filters").is_hidden():
            page.locator("#more-btn").click()
        page.locator("#more-btn").focus()
        page.keyboard.press("Space")
        assert page.locator("#more-filters").is_hidden(), "Space on More filters did not hide the filters"
        assert page.locator("#more-btn").get_attribute("aria-expanded") == "false", "aria-expanded is not false"
        return {"key": "Space"}

    def partial_view() -> dict[str, Any]:
        if not x.partial:
            raise NotApplicable("the catalogue has no run with a partial part")
        need(page, "#view-partial")
        show_all()
        page.locator("#view-partial").focus()
        page.keyboard.press("Space")
        s.wait_count(page, len(x.partial))
        assert shown_runs(page) == first_page(x.partial), "the rows listed are not the runs with a partial part"
        cells = page.locator("#cat-body tr.cat-run td.c-status").all_inner_texts()
        assert len(cells) == min(PAGE_SIZE, len(x.partial)) and all("partial" in cell for cell in cells), (
            "a listed run does not show a partial part in its Run status")
        assert page.locator("#view-partial").get_attribute("aria-pressed") == "true", "aria-pressed is not true"
        return {"runs": len(x.partial), "key": "Space"}

    def no_rows_view() -> dict[str, Any]:
        if not x.no_rows:
            raise NotApplicable("every run of the catalogue has public rows")
        need(page, "#view-norows")
        show_all()
        page.locator("#view-norows").click()
        s.wait_count(page, len(x.no_rows))
        listed = shown_runs(page)
        assert listed == first_page(x.no_rows), "the rows listed are not the runs without public rows"
        by_id = {run["run_dir"]: run for run in x.runs}
        cells = page.locator("#cat-body tr.cat-run td.c-meas").all_inner_texts()
        wrong = [name for name, cell in zip(listed, cells) if no_rows_statement(by_id[name]) not in cell]
        assert len(cells) == len(listed) and not wrong, (
            f"{len(wrong)} listed run(s) do not state that they have no public rows; first: {wrong[:1]}")
        return {"runs": len(x.no_rows), "statements": dict(Counter(no_rows_statement(by_id[name]) for name in listed))}

    def restricted_view() -> dict[str, Any]:
        need(page, "#view-restricted")
        show_all()
        page.locator("#view-restricted").click()
        s.wait_count(page, len(x.restricted))
        assert shown_runs(page) == first_page(x.restricted), "the rows listed are not the restricted runs"
        return {"runs": len(x.restricted)}

    def issue_view() -> dict[str, Any]:
        need(page, "#view-issue", "#view-issue .chip-ct")
        assert page.locator("#view-issue").is_visible(), "the view is not shown"
        shown = page.locator("#view-issue .chip-ct").inner_text().strip()
        assert shown.replace(",", "").isdigit(), "the view shows no count"
        assert int(shown.replace(",", "")) == x.issue, f"the view counts {shown}, the index gives {x.issue}"
        return {"runs": x.issue}

    try:
        for name, action in zip(names, (search, reset, more_closed, more_opens, detailed_filter, more_closes,
                                        partial_view, no_rows_view, restricted_view, issue_view)):
            recorder.run(name, action)
    finally:
        page.close()


# ------------------------------------------------------------------------------------------ checks: one run

def sealed_hits(texts: Mapping[str, str]) -> dict[str, Any]:
    """Run the engine's seal matcher over rendered text and markup. Returns labels and counts, never text.

    ``texts`` maps a view name to its content: ``text`` (what a reader sees) and ``html`` (the markup, which
    also holds title attributes). A label found in the visible text counts as allowlisted only when the markup
    scan allowlists it, because the allowlist masks whole fields and a field has its delimiters in the markup.
    ``Blocked`` when the sealed registry computes empty: the matcher then has nothing to match.
    """
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import seal_check
    except ImportError as exc:
        raise Blocked(f"scripts/seal_check.py could not be imported ({exc}); the seal matcher was not run") from exc
    simulated = ROOT / "data" / "simulated"
    registry = seal_check.sealed_registry(str(simulated), str(ROOT / "ops" / "dashboard.json"))
    if not registry:
        raise Blocked("the sealed registry computes empty in this engine checkout (data/simulated or the "
                      "Tier B start in ops/dashboard.json is absent); the seal matcher was not run")
    allow = seal_check.resolve_allowlist(seal_check.load_allowlist(ROOT / "data" / "seal_allowlist.json"),
                                         registry, simulated)
    html_hits, html_allowed = seal_check.scan_text(texts["html"], registry, allow, ".html")
    text_hits, _text_allowed = seal_check.scan_text(texts["text"], registry, allow)
    hits = sorted(set(html_hits) | (set(text_hits) - set(html_allowed)))
    return {"sealed_phrases_checked": len(registry), "hits": hits, "allowlisted": len(set(html_allowed)),
            "matcher": "scripts/seal_check.py scan_text over the rendered text and the markup of main"}


def check_open_run(s: Session, recorder: Recorder) -> None:
    names = group("a_run_opens_from_the_keyboard", "smallest_visible_text_at_1280_is_at_least_12_px")
    x, run = s.expected, s.expected.open_run
    part = run["parts"][0]

    def start() -> Any:
        page = s.page(s.desktop)
        s.load(page)
        return page
    page = opened(recorder, names, start)
    if page is None:
        return
    detail = page.locator("#cat-body tr.cat-detail").first
    source = detail.locator("details.det-src")

    def opens() -> dict[str, Any]:
        need(page, "#f-q", "#cat-count")
        page.locator("#f-q").fill(run["run_dir"])
        s.wait_count(page, 1)
        need(page, "#cat-body tr.cat-run .cat-x")
        button = page.locator("#cat-body tr.cat-run .cat-x").first
        button.focus()
        page.keyboard.press("Enter")
        detail.wait_for(state="visible")
        assert button.get_attribute("aria-expanded") == "true", "aria-expanded is not true on the open run"
        return {"run": run["run_dir"], "key": "Enter"}

    def rows_load() -> dict[str, Any]:
        page.wait_for_selector("#cat-body tr.cat-detail table.row-table tbody tr")
        shown, wanted = detail.locator("table.row-table tbody tr").count(), _count(run["counts"]["rows_public"])
        assert shown == wanted, f"{shown} rows rendered, the index counts {wanted} public rows"
        return {"rows": shown}

    def sealed_in_run() -> dict[str, Any]:
        if not x.sealed:
            raise NotApplicable("no run that this check can open has a sealed row")
        need(detail, ".det > dl.kv")
        assert f"{x.sealed:,} {SEALED_IN_RUN}" in detail.locator(".det > dl.kv").inner_text(), (
            f"the open run does not state its {x.sealed} sealed rows")
        return {"sealed_rows": x.sealed}

    def sealed_in_row() -> dict[str, Any]:
        if not x.sealed:
            raise NotApplicable("no run that this check can open has a sealed row")
        need(page, "#cat-body tr.cat-run td.c-meas")
        assert f"{x.sealed:,} sealed" in page.locator("#cat-body tr.cat-run td.c-meas").first.inner_text(), (
            f"the run row does not state its {x.sealed} sealed rows")
        return {"sealed_rows": x.sealed}

    def only_public_rows() -> dict[str, Any]:
        rows_file = s.site / CATALOGUE / run["rows_file"]
        assert rows_file.is_file(), f"the index names {run['rows_file']}, which is not in the site"
        wanted = public_row_indices(json.loads(rows_file.read_text(encoding="utf-8")))
        cells = detail.locator("table.row-table tbody tr td:first-child").all_inner_texts()
        assert sorted(cell.strip() for cell in cells) == wanted, (
            f"the rendered row indices are not those of the rows file ({len(cells)} rendered, {len(wanted)} in "
            "the file)")
        return {"rows": len(wanted), "rows_file": run["rows_file"]}

    def labels() -> dict[str, Any]:
        need(detail, ".det-labels")
        text = detail.locator(".det-labels").inner_text()
        missing = [label for label in RUN_LABELS if label not in text]
        assert not missing, f"the open run lacks the labels {missing}"
        boxed = detail.locator(".det-labels .bdg").evaluate_all(
            "(nodes) => nodes.filter((n) => parseFloat(getComputedStyle(n).borderTopWidth) > 0).length")
        assert boxed == 0, f"{boxed} label(s) of the open run are drawn as boxes"
        s.shot(page, "results_open_run_1280.png")
        return {"labels": list(RUN_LABELS)}

    def wordings_and_differences() -> dict[str, Any]:
        rows_file = s.site / CATALOGUE / run["rows_file"]
        stored = [row for part in json.loads(rows_file.read_text(encoding="utf-8"))["parts"]
                  for row in part.get("rows") or []]
        found = page.evaluate(OPEN_RUN_ROWS)
        heads = [head[0].lower() for head in found["heads"]]
        assert heads == list(ROW_HEADS), f"the columns of the rows are {heads}"
        sides = [head[1].lower() if len(head) > 1 else "" for head in found["heads"]]
        assert (sides[4], sides[5]) == PROBABILITY_SIDES and sides[6] == DIFFERENCE_ORDER, (
            f"the probability columns are for {sides[4:6]} and the difference is headed {sides[6]!r}")
        missing = [text for text in DIFFERENCE_NOTE if text not in found["note"]]
        assert not missing, f"the note above the rows does not state the order and unit of a difference: {missing}"
        # The narrow layout prints a label above each value; it must name the same wording and order.
        labels = found["rows"][0]["labels"]
        assert "medical wording" in labels[4].lower() and "everyday wording" in labels[5].lower() and (
            "everyday \u2212 medical" in labels[6].lower()), f"labels of the narrow layout: {labels[4:7]}"
        # Every row: the difference shown is the stored one with its sign, and a row without one says so.
        def value(v: Any) -> str:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            return ("\u2212" if v < 0 else "") + fmt_number(v) if ok else NOT_MEASURED

        wanted = sorted((DASH if row.get("index") is None else str(row["index"]), value(row.get("prob_clinical")),
                         value(row.get("prob_patient")), difference_text(row)) for row in stored)
        shown = sorted((row["index"], row["medical"], row["everyday"], row["difference"]) for row in found["rows"])
        assert len(shown) == len(wanted), f"{len(shown)} rows rendered, {len(wanted)} stored"
        wrong = sum(1 for got, want in zip(shown, wanted) if got != want)
        assert wrong == 0, f"{wrong} of {len(wanted)} rows do not show their stored values with the stored sign"
        agree = [sign_agrees(row) for row in stored]
        assert False not in agree, "a stored difference is not the everyday value minus the medical value"
        counts = Counter("missing" if text == NOT_MEASURED else text.rsplit(" ", 1)[1]
                         for _i, _m, _e, text in wanted)
        signs = Counter(row["sign"] for row in found["rows"])
        assert dict(signs) == dict(counts), f"signs marked {dict(signs)}, stored {dict(counts)}"
        zero_like = [text for _i, _m, _e, text in wanted if text != NOT_MEASURED and text.endswith(" zero")]
        assert all(any(ch.isdigit() for ch in text) for text in zero_like) and not any(
            ch.isdigit() for ch in NOT_MEASURED), "a zero and a missing difference share a form"
        return {"rows": len(wanted), "by_sign": dict(counts), "order": "everyday minus medical, in probability",
                "rows_with_all_three_numbers_whose_sign_was_recomputed": sum(1 for a in agree if a)}

    def neutral_colours() -> dict[str, Any]:
        found = page.evaluate(COLOURS, ALERT_COLOUR)
        assert not found["alerts"], f"the alert colour is shown while nothing has failed: {found['alerts'][:4]}"
        muted = {found["ink"], "rgb(109, 108, 102)"}
        for name in ("difference", "probability", "signs", "status"):
            assert found[name] and set(found[name]) <= muted, f"{name} text is coloured {found[name]}"
        assert found["medical"] == [WORDING_COLOURS["medical"]] and found["everyday"] == [WORDING_COLOURS["everyday"]], (
            f"the wordings are coloured {found['medical']} and {found['everyday']}")
        return {"alert_colour_elements": 0, "difference_colour": found["difference"],
                "wording_colours": {"medical": found["medical"][0], "everyday": found["everyday"][0]}}

    def source_closed() -> dict[str, Any]:
        need(detail, "details.det-src", "details.det-src summary")
        assert source.locator("summary").inner_text().strip() == METHODS_SOURCE, "the disclosure has another name"
        assert source.evaluate("(node) => node.open") is False, "the disclosure is open before it was asked for"
        return {}

    def source_opens() -> dict[str, Any]:
        need(detail, "details.det-src", "details.det-src summary")
        source.locator("summary").focus()
        page.keyboard.press("Enter")
        assert source.evaluate("(node) => node.open") is True, "Enter did not open the disclosure"
        return {"key": "Enter"}

    def run_id() -> dict[str, Any]:
        need(detail, "details.det-src .src-id")
        assert source.locator(".src-id").inner_text().strip() == run["run_dir"], "the run id shown is not the full id"
        return {"run": run["run_dir"]}

    def part_hash() -> dict[str, Any]:
        need(detail, "details.det-src .part-sha")
        assert part["sha256"] in source.locator(".part-sha").first.inner_text(), "the part's SHA-256 is not shown"
        return {"sha256": part["sha256"]}

    def part_name() -> dict[str, Any]:
        need(detail, "details.det-src")
        assert part["name"] in source.inner_text(), "the part's file name is not shown"
        s.shot(page, "results_methods_source_1280.png")
        return {"part": part["name"]}

    def seal() -> dict[str, Any]:
        main = page.locator("main")
        found = sealed_hits({"text": main.inner_text(), "html": main.evaluate("(node) => node.outerHTML")})
        assert not found["hits"], f"{len(found['hits'])} sealed phrase(s) are in the open run: labels {found['hits']}"
        return found

    def plain_downloads() -> dict[str, Any]:
        links = page.evaluate("""() => Array.from(document.querySelectorAll('a[download]')).map((a) => ({
            tag: a.tagName, href: a.getAttribute('href'), handler: a.onclick !== null}))""")
        hrefs = {link["href"] for link in links}
        assert links and all(link["tag"] == "A" and link["href"] and not link["handler"] for link in links), (
            "a download is not a plain link")
        missing = [name for name in DOWNLOADS if f"../{CATALOGUE}/{name}" not in hrefs]
        assert not missing, f"no download link for {missing}"
        assert any(href.endswith(run["rows_file"]) for href in hrefs), "the open run does not link its rows file"
        return {"links": len(links)}

    def target(name: str) -> Callable[[], dict[str, Any]]:
        def action() -> dict[str, Any]:
            status = head_status(f"{s.base}/{CATALOGUE}/{name}")
            assert status == 200, f"{name} answers HTTP {status}"
            return {"file": name, "status": status}
        return action

    def downloads_section() -> dict[str, Any]:
        need(page, '.jump a[href="#downloads"]', "#downloads")
        page.locator('.jump a[href="#downloads"]').click()
        assert page.evaluate("() => location.hash") == "#downloads", "the link did not move to #downloads"
        assert page.locator("#downloads").is_visible(), "the Downloads section is not shown"
        return {}

    def join_and_fields() -> dict[str, Any]:
        need(page, "#cat-legend > summary")
        page.locator("#cat-legend > summary").focus()
        page.keyboard.press("Enter")
        text = page.locator("#cat-legend").inner_text()
        missing = [wanted for wanted in JOIN_AND_FIELDS if wanted not in text]
        assert not missing, f"the join instructions or definitions lack {missing}"
        return {"key": "Enter", "strings": len(JOIN_AND_FIELDS)}

    def page_source_closed() -> dict[str, Any]:
        need(page, "#methods-source", "#restrictions")
        assert page.locator("#restrictions").is_hidden(), "the page-level Methods & source is open"
        return {}

    def page_source_opens() -> dict[str, Any]:
        restrictions = _mapping(x.index.get("restrictions"))
        need(page, '.jump a[href="#methods-source"]', "#methods-source")
        page.locator('.jump a[href="#methods-source"]').click()
        assert page.locator("#methods-source").evaluate("(node) => node.open"), "the link did not open the section"
        listed = page.locator("#restr-body tr").count()
        assert listed == len(restrictions), f"{listed} restrictions listed, the index has {len(restrictions)}"
        return {"restrictions": listed}

    def page_source_content() -> dict[str, Any]:
        policy, restrictions = _mapping(x.index.get("policy")), _mapping(x.index.get("restrictions"))
        pin = _mapping(policy.get("analysis_pin"))
        assert _text(policy.get("sha256")) and _text(pin.get("release_condition")), (
            "the index records no policy hash or no release condition of the study version")
        conditions = [_text(_mapping(entry).get("release_condition")) for entry in restrictions.values()]
        assert all(conditions), "a restriction of the index records no release condition"
        need(page, "#methods-source")
        text = page.locator("#methods-source").text_content()
        assert policy["sha256"] in text, "the policy hash is not shown"
        assert STUDY_VERSION in text and pin["release_condition"] in text, (
            "the study version or its release condition is not shown")
        assert all(condition in text for condition in conditions), "a restriction's release condition is not shown"
        return {"policy_sha256": policy["sha256"], "release_conditions": len(conditions) + 1}

    def about() -> dict[str, Any]:
        need(page, "#about > summary")
        page.locator("#about > summary").focus()
        page.keyboard.press("Enter")
        text = page.locator("#about").inner_text()
        missing = [wanted for wanted in ABOUT_STATEMENTS if wanted not in text]
        assert not missing, f"About this catalogue lacks {missing}"
        return {"key": "Enter"}

    def explained_once() -> dict[str, Any]:
        seen = page.locator("main").inner_text().lower().count(EXPLAINED_ONCE)
        assert seen == 1, f"the explanation is on the page {seen} times with every section open"
        return {"occurrences": seen}

    def excluded(phrase: str) -> Callable[[], dict[str, Any]]:
        def action() -> dict[str, Any]:
            main = page.locator("main")
            assert phrase not in main.inner_text().lower(), f"the page says {phrase!r}"
            assert phrase not in (main.text_content() or "").lower(), f"a hidden part of the page says {phrase!r}"
            return {"phrase": phrase}
        return action

    def text_size() -> dict[str, Any]:
        # every section of the page is open by now: the run, both Methods & source, the fields and About
        text = page.evaluate(SMALLEST_TEXT)
        assert text["smallest"] >= MIN_TEXT_PX, (
            f"the smallest visible text is {text['smallest']} px ({text['where']}), below {MIN_TEXT_PX}")
        return {"smallest_px": text["smallest"], "floor_px": MIN_TEXT_PX}

    actions = (opens, rows_load, sealed_in_run, sealed_in_row, only_public_rows, labels, wordings_and_differences,
               neutral_colours, source_closed, source_opens,
               run_id, part_hash, part_name, seal, plain_downloads, *(target(name) for name in DOWNLOADS),
               downloads_section, join_and_fields, page_source_closed, page_source_opens, page_source_content,
               about, explained_once, *(excluded(phrase) for phrase in EXCLUDED_PHRASES), text_size)
    try:
        for name, action in zip(names, actions, strict=True):
            recorder.run(name, action)
    finally:
        page.close()


# ------------------------------------------------------------------------------------------ checks: addresses

def check_addresses(s: Session, recorder: Recorder) -> None:
    names = group("address_parameter_state_is_honoured", "address_parameter_sort_selects_a_stated_neutral_order")
    x = s.expected
    page = opened(recorder, names, lambda: s.page(s.desktop))
    if page is None:
        return

    def count_starts(shown: int) -> None:
        text = page.locator("#cat-count").inner_text().strip()
        assert text.startswith(count_text(shown, x.total)), (
            f"the count line does not start with {count_text(shown, x.total)!r}")

    def state() -> dict[str, Any]:
        if not x.partial:
            raise NotApplicable("the catalogue has no run with a partial part")
        s.load(page, "?state=partial")
        need(page, "#cat-count", "#view-partial")
        count_starts(len(x.partial))
        assert page.locator("#view-partial").get_attribute("aria-pressed") == "true", "the partial view is not set"
        return {"runs": len(x.partial)}

    def evidence_rows_membership() -> dict[str, Any]:
        name, _runs, combined = x.evidence
        s.load(page, f"?evidence={quote(name, safe='')}&rows=1&membership=inside")
        need(page, "#cat-count", "#more-filters")
        count_starts(combined)
        assert page.locator("#more-filters").is_visible(), "the filters of the address are not shown"
        return {"evidence_class": name, "runs": combined}

    def q_visibility_stimulus() -> dict[str, Any]:
        if x.search is None or x.query_filter is None:
            raise NotApplicable("no search term narrows the list, so there is no address to build")
        visibility, stimulus, wanted = x.query_filter
        s.load(page, f"?q={quote(x.search[0], safe='')}&visibility={quote(visibility, safe='')}"
                     f"&stimulus={quote(stimulus, safe='')}")
        count_starts(wanted)
        return {"term": x.search[0], "visibility": visibility, "stimulus_class": stimulus, "runs": wanted}

    def run_without_rows() -> dict[str, Any]:
        run = x.run_without_rows
        if run is None:
            raise NotApplicable("every run of the catalogue has a rows file, or none without one records a part hash")
        s.load(page, "?run=" + quote(run["run_dir"], safe=""))
        detail = page.locator("#cat-body tr.cat-detail").first
        detail.wait_for(state="visible")
        need(detail, ".det-status", "details.det-src")
        shown = detail.locator(".det-status").get_attribute("data-state")
        assert shown in ("norows", "restricted"), f"the run's status box is in the state {shown!r}"
        source = detail.locator("details.det-src")
        assert source.evaluate("(node) => node.open"), "Methods & source of a run without rows is closed"
        assert run["parts"][0]["sha256"] in detail.inner_text(), "the part's SHA-256 is not shown"
        text = source.inner_text()
        states = sorted({human(_mapping(part).get("execution_state")) for part in run["parts"]})
        missing = [state for state in states if state not in text]
        assert not missing, f"the run status {missing} of a part is not shown"
        return {"run": run["run_dir"], "status_box": shown, "part_states": states}

    def restrictions() -> dict[str, Any]:
        s.load(page, "#restrictions")
        need(page, "#methods-source", "#restrictions")
        assert page.locator("#methods-source").evaluate("(node) => node.open"), "#restrictions did not open the section"
        assert page.locator("#restrictions").is_visible(), "the restrictions are not shown"
        return {}

    def totals() -> dict[str, Any]:
        s.load(page, "#totals")
        need(page, "#tot-figs")
        assert page.locator("#tot-figs").is_visible(), "the inventory is not shown"
        return {}

    def sort() -> dict[str, Any]:
        s.load(page, "?sort=date")
        need(page, "#cat-order")
        order = page.locator("#cat-order").inner_text()
        assert ORDER_DATE in order and ORDER_NEVER in order, "the ordering line does not state the date order"
        return {"order": order}

    try:
        for name, action in zip(names, (state, evidence_rows_membership, q_visibility_stimulus, run_without_rows,
                                        restrictions, totals, sort), strict=True):
            recorder.run(name, action)
    finally:
        page.close()


def check_error_states(s: Session, recorder: Recorder) -> None:
    """A missing index and a rows file that fails to load. Their console errors are wanted, so these two pages
    are not watched for errors. Requests to another origin are still blocked and counted."""
    run = s.expected.open_run

    def missing_index() -> dict[str, Any]:
        page = s.page(s.desktop, watched=False)
        try:
            page.route("**/results_catalogue/index.json", lambda route: route.fulfill(status=404, body="missing"))
            page.goto(s.url, wait_until="networkidle", timeout=45_000)
            box = page.locator("#cat-error")
            assert box.is_visible() and INDEX_FAILED in box.inner_text(), "the error state does not name the status"
            assert page.locator("#cat-content").is_hidden(), "the run list is shown without an index"
            assert page.locator("#cat-body tr").count() == 0, "a row is rendered without an index"
            return {"status_shown": INDEX_FAILED}
        finally:
            page.close()

    def failing_rows() -> dict[str, Any]:
        page = s.page(s.desktop, watched=False)
        try:
            page.route("**/results_catalogue/rows/*.json", lambda route: route.fulfill(status=404, body="missing"))
            s.load(page, "?run=" + quote(run["run_dir"], safe=""))
            status = page.locator("#cat-body tr.cat-detail .det-status").first
            status.wait_for(state="visible")
            page.wait_for_function("() => document.querySelector('#cat-body tr.cat-detail .det-status')"
                                   ".getAttribute('data-state') === 'fail'")
            assert ROWS_FAILED in status.inner_text(), "the failure does not name the status"
            assert status.locator("button").count() == 1, "the failure offers no retry control"
            assert page.locator("#cat-body tr.cat-detail table.row-table").count() == 0, "rows are shown"
            return {"run": run["run_dir"], "retry_controls": 1}
        finally:
            page.close()

    recorder.run("missing_index_shows_the_error_state_and_no_runs", missing_index)
    recorder.run("failing_rows_file_shows_the_failure_with_a_retry_and_no_rows", failing_rows)


def check_phone(s: Session, recorder: Recorder) -> None:
    names = group("search_input_is_inside_the_first_viewport_at_390x844",
                  "no_horizontal_scroll_at_390_with_text_at_200_percent")
    run, height = s.expected.open_run, PHONE[1]

    def start() -> Any:
        page = s.page(s.phone)
        s.load(page)
        return page
    page = opened(recorder, names, start)
    if page is None:
        return

    def search_in_view() -> dict[str, Any]:
        state = page.evaluate(LOAD_STATE)
        assert state["search"] is not None, "the page has no #f-q search input"
        assert state["search"][1] <= height, f"the search input ends at {state['search'][1]:.0f} px, below {height}"
        s.shot(page, "results_390.png")
        return {"top": round(state["search"][0]), "bottom": round(state["search"][1])}

    def as_loaded() -> dict[str, Any]:
        return no_horizontal_scroll(page)

    def about_and_filters() -> dict[str, Any]:
        need(page, "#more-btn", "#more-filters", "#about > summary")
        page.locator("#more-btn").click()
        page.locator("#about > summary").click()
        assert page.locator("#more-filters").is_visible() and page.locator("#about").evaluate("(node) => node.open")
        return no_horizontal_scroll(page)

    def run_and_source() -> dict[str, Any]:
        need(page, "#f-q", "#cat-count")
        page.locator("#f-q").fill(run["run_dir"])
        s.wait_count(page, 1)
        need(page, "#cat-body tr.cat-run .cat-x")
        page.locator("#cat-body tr.cat-run .cat-x").first.click()
        page.wait_for_selector("#cat-body tr.cat-detail table.row-table tbody tr")
        need(page, "#cat-body tr.cat-detail details.det-src > summary")
        page.locator("#cat-body tr.cat-detail details.det-src > summary").click()
        assert page.locator("#cat-body tr.cat-detail details.det-src").evaluate("(node) => node.open")
        return no_horizontal_scroll(page)

    def page_source_and_fields() -> dict[str, Any]:
        need(page, '.jump a[href="#methods-source"]', "#methods-source", "#cat-legend > summary")
        page.locator('.jump a[href="#methods-source"]').click()
        page.locator("#cat-legend > summary").click()
        assert page.locator("#methods-source").evaluate("(node) => node.open")
        assert page.locator("#cat-legend").evaluate("(node) => node.open")
        return no_horizontal_scroll(page)

    def text_size() -> dict[str, Any]:
        # Until 2026-11-11 the floor was 10 px and only the text of main was read. Now: 12 px, the masthead
        # too, and the labels a stylesheet prints above a value in the narrow layout.
        text = page.evaluate(SMALLEST_TEXT)
        assert text["smallest"] >= MIN_TEXT_PX, (
            f"the smallest visible text is {text['smallest']} px ({text['where']}), below {MIN_TEXT_PX}")
        return {"smallest_px": text["smallest"], "floor_px": MIN_TEXT_PX}

    def text_zoom() -> dict[str, Any]:
        # the page as the earlier checks left it: a run, both Methods & source, the fields and About are open
        changed = page.evaluate(DOUBLE_TEXT)
        assert changed > 100, f"only {changed} elements were resized"
        return {"text_scale": 2, **no_horizontal_scroll(page)}

    try:
        for name, action in zip(names, (search_in_view, as_loaded, about_and_filters, run_and_source,
                                        page_source_and_fields, text_size, text_zoom), strict=True):
            recorder.run(name, action)
    finally:
        page.close()


def run_browser_checks(s: Session, recorder: Recorder, blocked: list[str]) -> None:
    check_first_view(s, recorder)
    check_filters(s, recorder)
    check_open_run(s, recorder)
    check_addresses(s, recorder)
    check_error_states(s, recorder)
    check_phone(s, recorder)

    def no_errors() -> dict[str, Any]:
        assert not s.errors, f"{len(s.errors)} error(s); first: {s.errors[:3]}"
        return {"errors": 0}
    recorder.run("no_console_error_page_error_or_failed_request", no_errors)

    def no_outside_request() -> dict[str, Any]:
        assert not blocked, f"the page tried to reach {sorted(set(blocked))}"
        return {"external_requests": 0}
    recorder.run("no_request_left_the_test_server", no_outside_request)


# ------------------------------------------------------------------------------------------ the run

def launch(playwright: Any, browser_path: str | None) -> Any:
    try:
        return playwright.chromium.launch(**({"executable_path": browser_path} if browser_path else {}),
                                          args=["--disable-background-networking"])
    except Exception as exc:
        raise SetupProblem("no Chromium could be started; this check is blocked, not passed: "
                           f"{str(exc).strip().splitlines()[0][:300]}") from exc


def new_context(browser: Any, origin: str, blocked: list[str], size: tuple[int, int]) -> Any:
    """A browser context that can reach the test server and nothing else."""
    context = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=2,
                                  service_workers="block")
    context.set_default_timeout(WAIT_MS)

    def route_request(route: Any) -> None:
        url = urlsplit(route.request.url)
        if f"{url.scheme}://{url.netloc}" == origin or url.scheme == "data":
            route.continue_()
        else:
            blocked.append(f"{url.scheme}://{url.netloc}")
            route.abort()
    context.route("**/*", route_request)
    return context


def run(site: Path, browser_path: str | None, port: int, shots: Path | None, receipt: dict[str, Any]) -> Recorder:
    """Run every check and return the recorder. Raises ``SetupProblem`` when the check cannot run."""
    try:
        import importlib.metadata

        from playwright.sync_api import sync_playwright
        receipt["versions"]["playwright"] = importlib.metadata.version("playwright")
    except ImportError as exc:
        raise SetupProblem("the playwright package is not importable; this check is blocked, not passed: "
                           f"{exc}") from exc

    expected = expectations(load_catalogue(site))
    receipt["catalogue"] = expected.summary()
    before = input_hashes(site)
    recorder = Recorder(receipt)
    blocked: list[str] = receipt["browser_external_requests"]

    server = serve(site, port)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            browser = launch(playwright, browser_path)
            receipt["versions"]["chromium"] = browser.version
            session = Session(base=origin + MOUNT, site=site, expected=expected,
                              desktop=new_context(browser, origin, blocked, DESKTOP),
                              phone=new_context(browser, origin, blocked, PHONE), receipt=receipt, shots=shots)
            run_browser_checks(session, recorder, blocked)
            session.desktop.close()
            session.phone.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)

    recorded = tuple(check["name"] for check in receipt["checks"])
    if recorded != CHECKS:
        raise RuntimeError(f"the checks recorded are not the checks listed: {len(recorded)} recorded, "
                           f"{len(CHECKS)} listed")
    if input_hashes(site) != before:
        raise SetupProblem("the page or the catalogue index changed while the check ran; the results describe "
                           "neither version. Run it again")
    return recorder


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", type=Path, required=True, help="the patientwords site checkout")
    parser.add_argument("--browser", help="an installed Chromium executable (default: CHROMIUM, then Playwright's own)")
    parser.add_argument("--port", type=int, default=0, help="loopback port to serve on (default: an ephemeral port)")
    parser.add_argument("--receipt", type=Path, help="write the JSON receipt here")
    parser.add_argument("--shots", type=Path, help="write screenshots into this directory")
    args = parser.parse_args(argv)
    site = args.site.resolve()
    receipt_path = args.receipt.resolve() if args.receipt else None
    browser = args.browser or os.environ.get("CHROMIUM") or None

    def finish(receipt: dict[str, Any] | None, code: int, message: str) -> int:
        if receipt is not None and receipt_path is not None:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(message, file=sys.stderr if code else sys.stdout)
        return code

    if not (site / PAGE).is_file():
        return finish(None, EXIT_SETUP, f"setup problem: {site} has no {PAGE}; nothing was checked")
    receipt = new_receipt(site, receipt_path)

    def blocked(reason: str, message: str) -> int:
        receipt["result"], receipt["blocked_by"] = "blocked", reason.splitlines()[0][:400]
        return finish(receipt, EXIT_SETUP, message)

    if browser and not Path(browser).is_file():
        return blocked("the --browser path is not a file",
                       f"setup problem: no Chromium at {browser}; this check is blocked, not passed")
    try:
        recorder = run(site, browser, args.port, args.shots.resolve() if args.shots else None, receipt)
    except SetupProblem as exc:
        return blocked(str(exc), f"setup problem: {exc}")
    except Exception as exc:  # the run stopped before every check could be filed
        receipt["result"] = "failed"
        first_line = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else ""
        receipt["failure"] = f"{type(exc).__name__}: {first_line}"
        return finish(receipt, EXIT_FAILED, f"results page check stopped: {receipt['failure']}")
    total, code = len(receipt["checks"]), exit_code(recorder.failed, recorder.blocked)
    passed = total - recorder.failed - recorder.blocked - recorder.not_applicable
    counts = (f"{passed} passed, {recorder.failed} failed, {recorder.blocked} blocked, "
              f"{recorder.not_applicable} not applicable")
    receipt["counts"] = {"checks": total, "passed": passed, "failed": recorder.failed, "blocked": recorder.blocked,
                         "not_applicable": recorder.not_applicable}
    if code == EXIT_FAILED:
        receipt["result"] = "failed"
        return finish(receipt, code, f"results page check: {recorder.failed} of {total} checks failed ({counts})")
    if code == EXIT_SETUP:
        receipt["result"], receipt["blocked_by"] = "blocked", f"{recorder.blocked} check(s) could not run"
        return finish(receipt, code, f"results page check: blocked, not passed: {recorder.blocked} of {total} "
                                     f"checks could not run ({counts})")
    receipt["result"] = "passed"
    return finish(receipt, code, f"results page check: {total} checks, {counts}")


if __name__ == "__main__":
    sys.exit(main())
