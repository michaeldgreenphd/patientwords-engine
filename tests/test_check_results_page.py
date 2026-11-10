"""Tests for ``scripts/check_results_page.py``.

The unit tests cover the parts that need no browser: the mirror of the page's search rule, the choices the
checker makes from a catalogue index, the recorder and its exit codes, the read-only server and the exits of a
run that cannot start. One test compares the page source with the ids and strings the checker reads. One test
runs the whole checker in Chromium against the sibling site checkout; it skips with the reason when Chromium or
the site is absent. A skip is a check that did not run, not a pass.

The toy runs here are invented. No stimulus text is in this file.
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

def test_experiment_title_follows_the_pages_derivation() -> None:
    title = crp.experiment_title
    assert title({"run_dir": "r", "stem": "pairs_20260710T011743Z", "stimulus_class": "study_batch"}) == (
        "Study batch · 2026-07-10 01:17 UTC")
    assert title({"run_dir": "r", "stem": "agscen_20261108", "stimulus_class": "hand_authored_exploratory"}) == (
        "Hand-authored set · 2026-11-08")
    assert title({"run_dir": "r", "stem": "pairs_extra_20260710_v2", "stimulus_class": "study_batch"}) == (
        "Study batch extra v2 · 2026-07-10")
    assert title({"run_dir": "r", "stem": "dialects_20260708T215356Z", "stimulus_class": "unclassified"}) == (
        "Dialects · 2026-07-08 21:53 UTC")
    assert title({"run_dir": "r", "stem": "no_date_here", "stimulus_class": None}) == "No date here"
    assert title({"run_dir": "r", "stem": "set_19991231"}) == "Set 19991231"          # a year the page does not read
    assert title({"run_dir": "r", "stem": "set_20261341"}) == "Set 20261341"          # not a month
    assert title({"run_dir": "run_only"}) == "Run only"                               # no stem: the run id is used
    assert title({"run_dir": "r", "stem": "pairs_20260710T996100Z", "stimulus_class": "study_batch"}) == (
        "Study batch · 2026-07-10")                                              # not a time of day


def test_search_text_holds_what_the_page_searches_and_matches_every_term() -> None:
    run = _toy_runs()[3]
    text = crp.search_text(run)
    assert text == ("handset_20260303 handset_20260303  toy-lens hand-authored set · 2026-03-03 "
                    "exploratory set completed partial")
    assert crp.search_matches(run, "TOY-LENS partial") and crp.search_matches(run, "  hand-authored  ")
    assert crp.search_matches(run, "") and not crp.search_matches(run, "toy-lens toy-b")
    assert not crp.search_matches(run, "exploratory_set")          # the page searches the printed form, with a space
    assert crp.human("a_b_c") == "a b c" and crp.human(None) == crp.human("") == crp.DASH


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


# ------------------------------------------------------------------------------------------ expectations

def test_the_search_term_is_the_model_name_that_selects_the_most_runs_and_not_all() -> None:
    runs = _toy_runs()
    term, matched = crp.pick_search_term(runs)
    # "toy-a" and "toy-b" each select two runs; of two terms that select as many, the first name is taken.
    counts = {name: sum(crp.search_matches(run, name) for run in runs) for name in ("toy-a", "toy-b")}
    assert counts == {"toy-a": 2, "toy-b": 2}
    assert term == "toy-a" and matched == ["pairs_20260101T010203Z__toy-a", "thirdparty_20260404"]     # index order
    more = [*runs, _run("pairs_20260505__toy-b", model="toy-b")]
    assert crp.pick_search_term(more)[0] == "toy-b" and len(crp.pick_search_term(more)[1]) == 3   # the most runs
    same = [_run("a__m"), _run("b__m")]
    for run in same:
        run["model"] = "m"
    assert crp.pick_search_term(same)[0] in ("a", "a__m")           # every run has the model: a stem is taken
    assert crp.pick_search_term([_run("only")]) is None             # one run: nothing narrows the list


def test_the_opened_run_prefers_sealed_rows_and_is_selected_alone_by_its_run_id() -> None:
    runs = _toy_runs()
    assert crp.pick_open_run(runs)["run_dir"] == "pairs_20260101T010203Z__toy-b"          # the run with sealed rows
    unsealed = [run for run in runs if run["counts"]["rows_withheld_sealed"] == 0]
    assert crp.pick_open_run(unsealed)["run_dir"] == "pairs_20260101T010203Z__toy-a"      # else the first usable
    # A run id that is also the start of another run id is not selected alone, so it is not opened.
    prefix = [_run("pairs_2026"), _run("pairs_2026__toy-b", model="toy-b")]
    assert crp.pick_open_run(prefix)["run_dir"] == "pairs_2026__toy-b"
    for unusable in ({"n_parts": 2}, {"rows_file": None}, {"rows_file": "../rows/x.json"}, {"visibility": "restricted"},
                     {"parts": [{"name": "p", "sha256": "short"}]}, {"counts": {"rows_public": 0}}):
        with pytest.raises(crp.SetupProblem, match="open-run checks cannot run"):
            crp.pick_open_run([_run("solo", **unusable)])


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
    expected = crp.expectations(index)
    assert expected.total == 5 and expected.run_ids[0] == "pairs_20260101T010203Z__toy-a"
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

def test_the_check_list_is_62_distinct_names_and_groups_follow_its_order() -> None:
    assert len(crp.CHECKS) == len(set(crp.CHECKS)) == 62            # 61 of the scratch script, and the request count
    first = crp.group("search_input_is_inside_the_first_viewport_at_1280x720",
                      "download_links_are_inside_the_first_viewport_at_1280x720")
    assert first == crp.CHECKS[:9] and crp.CHECKS[-1] == "no_request_left_the_test_server"
    assert sum(1 for name in crp.CHECKS if name.startswith("page_does_not_say_")) == len(crp.EXCLUDED_PHRASES) == 3
    assert sum(1 for name in crp.CHECKS if name.startswith("download_target_")) == len(crp.DOWNLOADS) == 3


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
    # The search rule the checker mirrors, and the label rule it reads: a change to either line fails here.
    for line in crp.PAGE_SEARCH_RULE:
        assert line in script, line
    for value, label in crp.CLASS_LABEL.items():
        assert f"{value}:'{label}'" in script, value
    assert f"var PAGE_SIZE={crp.PAGE_SIZE};" in script
    assert "fmtInt(filtered.length)+' of '+fmtInt(RUNS.length)+' runs'" in script        # count_text
    # Reader-visible strings the checks compare.
    for column in crp.COLUMNS:
        assert f'">{column[:1].upper()}{column[1:]}' in static, column
    for text in (crp.ORDER_DEFAULT, crp.ORDER_DATE, crp.ORDER_NEVER, crp.SEALED_IN_RUN, "'Methods & source'",
                 crp.NO_ROWS_RESTRICTED, crp.NO_ROWS_NONE, "' public '+(nPub===1?'row':'rows')", "' sealed'",
                 "could not be loaded ('+failLabel(e)+')", "'HTTP '+r.status", *crp.RUN_LABELS[:1],
                 "'evidence: '", "'clinical review: '", "a listing, not a claim"):
        assert text in script, text
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
    assert counts["checks"] == 62 and counts["failed"] == counts["blocked"] == 0
    assert counts["passed"] + counts["not_applicable"] == 62
    for name in ("count_reads_all_runs_of_the_index", "default_order_is_the_index_order",
                 "a_run_opens_from_the_keyboard", "rendered_rows_are_exactly_the_public_rows_of_the_rows_file",
                 "no_sealed_phrase_in_what_the_open_run_renders", "downloads_are_plain_links",
                 "missing_index_shows_the_error_state_and_no_runs",
                 "failing_rows_file_shows_the_failure_with_a_retry_and_no_rows",
                 "no_horizontal_scroll_at_390_as_loaded", "smallest_visible_text_at_390_is_at_least_10_px",
                 "no_console_error_page_error_or_failed_request", "no_request_left_the_test_server"):
        assert results[name]["result"] == "passed", name
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
