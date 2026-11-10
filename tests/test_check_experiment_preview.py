"""Tests for ``scripts/check_experiment_preview.py``.

The unit tests cover the parts that need no browser: the expected values the checker recomputes from the fixture
logits, the hand-computed ICA table, the mirror of the page's address-parameter rule, the number formats and the
receipt. One test runs the whole checker in Chromium when a Chromium executable and the sibling site checkout are
present, and skips with the reason otherwise. A skip is a check that did not run, not a pass.

Everything here is a toy fixture. Nothing in this file says anything about a model.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"
FX = ROOT / "tests" / "fixtures" / "experiments"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cep = _load("check_experiment_preview", ROOT / "scripts" / "check_experiment_preview.py")
PROTOCOL = json.loads(cep.PROTOCOL.read_text(encoding="utf-8"))
LOGITS = json.loads(cep.LOGITS.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------ expected values

def test_softmax_of_the_fixture_logits_is_weights_over_their_sum() -> None:
    # The fixture states logits[i] = ln(weights[i]). The checker reads the logits; this test reads the weights.
    for row in LOGITS["rows"]:
        got = cep.softmax(row["logits"])
        total = sum(row["weights"])
        assert abs(sum(got) - 1.0) < 1e-12
        for value, weight in zip(got, row["weights"]):
            assert abs(value - weight / total) < 1e-12


def test_softmax_refuses_an_empty_or_non_finite_list() -> None:
    for bad in ([], [0.0, float("nan")], [float("inf")], ["1"]):
        with pytest.raises(ValueError):
            cep.softmax(bad)


def _exact(family: str, variant: str, token: int) -> Fraction:
    row = next(r for r in LOGITS["rows"] if (r["family_id"], r["variant"]) == (family, variant))
    return Fraction(row["weights"][token], sum(row["weights"]))


def test_expected_behaviour_agrees_with_exact_fractions_and_marks_only_exact_ties() -> None:
    expected = cep.expected_behavior(PROTOCOL, LOGITS)
    assert abs(expected["variants"][("fam-1", "clinical", "t1")] - 1 / 3) < 1e-12
    first = expected["differences"][("fam-1", "clinical_vs_colloquial", "t1")]
    assert abs(first["difference"] - 1 / 6) < 1e-12 and (first["a_name"], first["b_name"]) == ("clinical", "colloquial")
    tokens = {t["id"]: t["token_ids"][0] for t in PROTOCOL["case_families"][0]["targets"]}
    ties = 0
    for (family, comparison_id, target), want in expected["differences"].items():
        comparison = next(c for c in PROTOCOL["comparisons"] if c["id"] == comparison_id)
        exact = _exact(family, comparison["a"], tokens[target]) - _exact(family, comparison["b"], tokens[target])
        assert want["tie"] is (exact == 0), (family, comparison_id, target)
        if exact != 0:
            assert (want["difference"] > 0) is (exact > 0) and abs(want["difference"] - float(exact)) < 1e-12
        ties += exact == 0
    assert len(expected["differences"]) == 12 and len(expected["variants"]) == 18
    assert ties >= 2          # the fixture holds exact ties, so the valid-zero display has something to show


def test_expected_behaviour_refuses_a_missing_fixture_row() -> None:
    short = dict(LOGITS, rows=LOGITS["rows"][1:])
    with pytest.raises(ValueError, match="no row"):
        cep.expected_behavior(PROTOCOL, short)


def test_the_hand_computed_ica_table_is_the_fixture_builders_table() -> None:
    pytest.importorskip("numpy", reason="the ICA fixture builder imports numpy")
    builder = _load("build_ica_fixtures_for_preview_test", FX / "ica" / "build_ica_fixtures.py")
    assert {key: tuple(scores) for key, (scores, _residual) in builder.PAIR_LAST.items()} == cep.ICA_LAST_SCORES
    assert builder.LAYER == cep.ICA_LAYER


def test_expected_ica_values_and_undefined_shares() -> None:
    expected = cep.expected_ica(PROTOCOL)
    assert len(expected) == 3 * 2 * 4
    first = expected[("fam-1", "clinical_vs_colloquial", 0)]
    assert (first["score_a"], first["score_b"], first["difference"]) == (3.0, -3.0, 6.0)
    assert first["share_a"] == pytest.approx(9 / 25) and first["share_b"] == pytest.approx(9 / 25)
    assert expected[("fam-1", "colloquial_vs_normalized", 1)]["share_b"] == pytest.approx(36 / 42)
    zero_vector = expected[("fam-2", "clinical_vs_colloquial", 0)]
    assert zero_vector["share_b"] is None and zero_vector["share_a"] == pytest.approx(4 / 5)   # undefined, not 0
    assert all(expected[("fam-3", "clinical_vs_colloquial", k)]["difference"] == 0.0 for k in range(4))
    assert cep.energy_shares([0, 0]) == [None, None]


# ------------------------------------------------------------------------------------------ added bundle fields

def test_expected_variant_inputs_come_from_the_fixture_protocol_and_hold_no_text() -> None:
    expected = cep.expected_variant_inputs(PROTOCOL)
    assert len(expected) == 9 and set(expected[("fam-1", "clinical")]) == {"prompt_sha256", "token_sha256", "n_tokens"}
    entry = PROTOCOL["case_families"][0]["variants"]["clinical"]
    assert expected[("fam-1", "clinical")] == {"prompt_sha256": entry["prompt_sha256"],
                                               "token_sha256": entry["token_sha256"],
                                               "n_tokens": str(len(entry["token_ids"]))}
    prompts = [e["prompt"] for f in PROTOCOL["case_families"] for e in f["variants"].values()]
    assert not [prompt for prompt in prompts if prompt in json.dumps(sorted(map(str, expected.items())))]


def test_expected_preprocessing_is_the_protocols_ica_block() -> None:
    index = json.loads(cep.ICA_INDEX.read_text(encoding="utf-8"))
    assert cep.expected_preprocessing(PROTOCOL) == index["method_block"]["basis"]["preprocessing"]
    without = dict(PROTOCOL, methods=[m for m in PROTOCOL["methods"] if m["id"] != "ica_lens"])
    with pytest.raises(ValueError, match="ica_lens"):
        cep.expected_preprocessing(without)


def test_expected_journal_counts_sum_the_run_summaries() -> None:
    steps = [{"step": "validate"}, {"step": "run-fixture --stop-after 5", "executed": 5, "reused": 0},
             {"step": "run-fixture (resume)", "executed": 22, "reused": 5}, {"step": "collect --require-complete"}]
    assert cep.expected_journal_counts(steps) == {"executed": 27, "reused": 5}
    with pytest.raises(ValueError, match="no run-fixture step"):
        cep.expected_journal_counts(steps[:1])


def _toy_bundle() -> dict:
    return {
        "protocol": {"synthetic": True, "families": [{
            "family_id": "fam-1", "variants": ["clinical"],
            "variant_inputs": {"clinical": {"prompt_sha256": "a" * 64, "token_sha256": "b" * 64, "n_tokens": 3}},
            "variant_text": {"clinical": {"prompt": "placeholder wording", "prompt_sha256": "a" * 64}},
            "prompt_text_export": {"basis": "protocol_marker", "marker": cep.PROMPT_TEXT_MARKER,
                                   "seal_check": "not_applicable_synthetic"}}]},
        "evidence": {"synthetic": True, "evidence_class": "synthetic_fixture",
                     "clinical_review": "not_applicable_synthetic", "visibility": "not_published",
                     "restriction_reasons": [], "analysis_memberships": []},
        "limitations": ["synthetic_not_measurement", "no_real_model_was_loaded_and_no_parity_with_one_was_tested",
                        "fixture_timings_say_nothing_about_model_runs", "first_target_token_only_no_sequence_scoring"],
        "comparisons": [{"family_id": "fam-1", "comparisons": [
            {"comparison_id": "c", "behavior": {"status": "computed", "vocabulary_size": 8},
             "ica": {"status": "computed", "preprocessing_mode": "placeholder-mode",
                     "preprocessing_read_from": "placeholder.json#/mode"}},
            {"comparison_id": "d"}]}],
        "execution": {"counts": {"planned": 1, "executed_attempts": 1, "reused_events": 0}},
    }


def test_without_added_fields_removes_exactly_the_additions() -> None:
    bundle = _toy_bundle()
    older = cep.without_added_fields(bundle)
    assert older["protocol"]["families"] == [{"family_id": "fam-1", "variants": ["clinical"]}]
    first = older["comparisons"][0]["comparisons"][0]
    assert first["ica"] == {"status": "computed"} and first["behavior"] == {"status": "computed"}
    assert older["execution"]["counts"] == {"planned": 1}
    assert "placeholder wording" not in json.dumps(older)                 # exported prompt text is an addition
    assert "variant_inputs" in bundle["protocol"]["families"][0]          # the input is not changed
    assert "variant_text" in bundle["protocol"]["families"][0]
    with pytest.raises(ValueError, match="none of the fields"):
        cep.without_added_fields(older)                                  # nothing to remove: not a silent pass


def test_marked_protocol_adds_the_marker_to_the_named_families_only() -> None:
    marked = cep.marked_protocol(PROTOCOL)
    facts = {family["family_id"]: family["facts"] for family in marked["case_families"]}
    assert cep.TEXT_FAMILIES == ("fam-1", "fam-2") and cep.PROMPT_TEXT_MARKER == "publication:prompt_text_approved"
    assert [fid for fid, listed in facts.items() if cep.PROMPT_TEXT_MARKER in listed] == list(cep.TEXT_FAMILIES)
    assert not [f for f in PROTOCOL["case_families"] if cep.PROMPT_TEXT_MARKER in f["facts"]]   # input unchanged
    assert cep.marked_protocol(marked) == marked                          # adding twice changes nothing
    with pytest.raises(ValueError, match="no family"):
        cep.marked_protocol(PROTOCOL, ("fam-9",))
    # The marker is the one the bundle writer reads: a renamed marker must fail here, offline.
    sys.path.insert(0, str(ROOT))
    try:
        from scripts.experiments import bundle as bundle_module
    finally:
        sys.path.remove(str(ROOT))
    assert bundle_module.PROMPT_TEXT_MARKER == cep.PROMPT_TEXT_MARKER


def test_expected_prompt_text_is_the_protocols_text_for_marked_families_and_none_elsewhere() -> None:
    marked = cep.marked_protocol(PROTOCOL)
    expected = cep.expected_prompt_text(marked)
    assert len(expected) == 9
    for family in marked["case_families"]:
        for name, entry in family["variants"].items():
            wanted = entry["prompt"] if family["family_id"] in cep.TEXT_FAMILIES else None
            assert expected[(family["family_id"], name)] == wanted
    assert set(cep.expected_prompt_text(PROTOCOL).values()) == {None}     # no marker: no text is expected


def test_a_relabelled_copy_says_it_is_publishable_and_carries_no_text() -> None:
    bundle = _toy_bundle()
    copy_ = cep.relabelled_as_publishable(bundle)
    assert copy_["protocol"]["synthetic"] is False and copy_["evidence"]["synthetic"] is False
    assert (copy_["evidence"]["visibility"], copy_["evidence"]["restriction_reasons"]) == ("public", [])
    assert copy_["evidence"]["evidence_class"] != "synthetic_fixture"
    assert copy_["limitations"] == ["first_target_token_only_no_sequence_scoring"]
    assert "placeholder wording" not in json.dumps(copy_) and "variant_inputs" in copy_["protocol"]["families"][0]
    assert bundle["evidence"]["synthetic"] is True                        # the input is not changed


def test_a_disagreeing_copy_changes_one_wording_in_the_second_comparison_only() -> None:
    def entry(comparison_id: str, a: str, b: str) -> dict:
        return {"comparison_id": comparison_id, "a": a, "b": b,
                "behavior": {"status": "computed", "targets": [{"target_id": "t1", "a": 0.25, "b": 0.5}]},
                "readout": {"logit_lens": {"status": "computed", "layers": [{"layer": 0, "targets": [
                    {"target_id": "t1", "a": {"raw_rank": 2}, "b": {"raw_rank": 3}}]}]}},
                "ica": {"status": "computed", "layers": [{"layer": 1, "components": [
                    {"component": 0, "score_a": 1.0, "score_b": 2.0}]}]}}

    bundle = {"comparisons": [{"family_id": "fam-1", "comparisons": [entry("c1", "clinical", "colloquial"),
                                                                     entry("c2", "colloquial", "normalized")]}]}
    changed, what = cep.disagreeing_bundle(bundle)
    first, second = changed["comparisons"][0]["comparisons"]
    assert first == bundle["comparisons"][0]["comparisons"][0]
    assert second["behavior"]["targets"][0]["a"] != 0.25 and second["behavior"]["targets"][0]["b"] == 0.5
    assert second["readout"]["logit_lens"]["layers"][0]["targets"][0]["a"]["raw_rank"] == 3
    assert second["ica"]["layers"][0]["components"][0]["score_a"] == 2.0
    assert what == {"family": "fam-1", "wording": "colloquial", "target": "t1", "method": "logit_lens",
                    "layer": "0", "readout_target": "t1", "component": "0"}
    bundle["comparisons"][0]["comparisons"][1]["a"] = "normalized"
    with pytest.raises(ValueError, match="no longer share a wording"):
        cep.disagreeing_bundle(bundle)


# ------------------------------------------------------------------------------------------ number formats

def test_number_formats_mirror_the_page() -> None:
    assert cep.fmt_plain(1 / 3) == "0.3333" and cep.fmt_plain(0.0) == "0.0000" and cep.fmt_plain(0.25) == "0.2500"
    assert cep.fmt_signed(0.0) == "0" and cep.fmt_signed(-0.0) == "0"             # a zero carries no sign
    assert cep.fmt_signed(1 / 6) == "+0.1667" and cep.fmt_signed(-1 / 12) == "−0.0833"
    assert cep.fmt_signed(6.0) == "+6.0000"
    assert cep.fmt_signed(0.03125) == "+0.0313"                                   # an exact tie rounds away from zero
    assert cep.fmt_signed(1.3877787807814457e-17) == "+1.39e-17"                  # never printed as +0.0000
    assert cep.fmt_signed(-0.00001) == "−1.00e-5"


def test_sign_text_distinguishes_zero_direction_and_below_display() -> None:
    assert cep.sign_text(0.0, "clinical", "colloquial") == "no difference"
    assert cep.sign_text(0.2, "clinical", "colloquial") == "clinical higher"
    assert cep.sign_text(-0.2, "clinical", "colloquial") == "colloquial higher"
    assert cep.sign_text(1e-17, "clinical", "colloquial") == "clinical higher, below the 4 decimals shown"


# ------------------------------------------------------------------------------------------ address parameter

REFUSAL_PHRASE = {
    "": "empty",
    "../data/experiment_preview/bundle.json": 'contains ".."',
    "experiment_preview/../experiment_preview/bundle.json": 'contains ".."',
    "experiment_preview/..bundle.json": 'contains ".."',
    "/experiment_preview/bundle.json": "absolute path",
    "\\experiment_preview\\bundle.json": "absolute path",
    "//registry-fixture.invalid/bundle.json": "absolute path",
    "https://registry-fixture.invalid/bundle.json": "scheme",
    "javascript:alert(1)": "scheme",
    "data:application/json,{}": "scheme",
    "experiment_preview/bundle.json?x=1": "character outside",
    "experiment_preview/bundle.json#part": "character outside",
    "experiment preview/bundle.json": "character outside",
    "%2e%2e/experiment_preview/bundle.json": "character outside",
    "experiment_preview//bundle.json": "empty or dot-leading path segment",
    "experiment_preview/.bundle.json": "empty or dot-leading path segment",
    "experiment_preview/bundle.txt": "does not name a .json file",
    "x" * 196 + ".json": "longer than 200",
}


def test_every_parameter_case_has_an_expectation() -> None:
    assert set(cep.PARAM_CASES) == set(REFUSAL_PHRASE) | {cep.BUNDLE_PARAM}


@pytest.mark.parametrize("value", sorted(REFUSAL_PHRASE))
def test_bundle_parameter_refusals(value: str) -> None:
    reason = cep.bundle_param_refusal(value)
    assert reason is not None and REFUSAL_PHRASE[value] in reason


def test_bundle_parameter_accepts_a_relative_json_path() -> None:
    for value in (cep.BUNDLE_PARAM, "bundle.json", "a/b/c-d_e.v1.json", "x" * 195 + ".json"):
        assert cep.bundle_param_refusal(value) is None, value


def test_an_accepted_parameter_can_never_leave_the_data_directory() -> None:
    probes = ["..", "a/../b.json", "/a.json", "\\a.json", "a:b.json", "a/./b.json", "a\\..\\b.json", "a/..%2fb.json",
              "‥/a.json", "a/../b.json", ".json", "a/.json"]
    for value in probes:
        assert cep.bundle_param_refusal(value) is not None, value


# ------------------------------------------------------------------------------------------ receipt and exits

def _toy_site(tmp_path: Path) -> Path:
    site = tmp_path / "toy_site"
    (site / "experiments").mkdir(parents=True)
    (site / cep.PAGE).write_text("<!doctype html><title>toy</title>", encoding="utf-8")
    return site


def test_receipt_binds_checkouts_fixtures_and_tools_without_private_paths(tmp_path: Path) -> None:
    site = _toy_site(tmp_path)
    receipt = cep.new_receipt(site, None)
    assert receipt["schema"] == "patientwords.experiment-preview-receipt/1"
    assert receipt["evidence"] == "local synthetic software test only" and receipt["result"] == "not_run"
    assert set(receipt["engine"]) >= {"head"} and len(receipt["engine"]["head"] or "") in (0, 40)
    # A directory that is not a checkout has no HEAD; that is recorded as missing with its reason, not invented.
    assert receipt["frontend"]["head"] is None and "not_recorded" in receipt["frontend"]
    assert receipt["page_sha256"][cep.PAGE] == cep.sha256_file(site / cep.PAGE)
    assert "tests/fixtures/experiments/behavior_logits.json" in receipt["fixture_sha256"]
    assert "tests/fixtures/experiments/ica/fixture_index.json" in receipt["fixture_sha256"]
    assert "scripts/check_experiment_preview.py" in receipt["tool_sha256"]
    assert "scripts/experiments/bundle.py" in receipt["tool_sha256"]
    assert not any("__pycache__" in name for name in receipt["fixture_sha256"])
    text = json.dumps(receipt)
    assert str(ROOT) not in text and str(tmp_path) not in text


def test_recorder_files_each_result_and_keeps_going(tmp_path: Path) -> None:
    receipt = {"checks": []}
    recorder = cep.Recorder(receipt)

    def failing() -> None:
        raise AssertionError("first line\nsecond line")

    assert recorder.run("holds", lambda: {"n": 1}) is True
    assert recorder.run("breaks", failing) is False
    assert recorder.run("defect", lambda: None, result="detected_then_restored_pass") is True
    assert recorder.failed == 1
    assert [c["result"] for c in receipt["checks"]] == ["passed", "failed", "detected_then_restored_pass"]
    assert receipt["checks"][0]["n"] == 1 and receipt["checks"][1]["message"] == "first line"
    with pytest.raises(cep.SetupProblem):
        recorder.run("blocked", lambda: (_ for _ in ()).throw(cep.SetupProblem("no browser")))


def test_a_deliberate_defect_must_actually_fail() -> None:
    def failing() -> None:
        raise AssertionError("caught")

    assert cep.rejected(failing) == "caught"
    with pytest.raises(AssertionError, match="not detected"):
        cep.rejected(lambda: None)


def test_exit_2_when_the_site_has_no_viewer_page(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt = tmp_path / "receipt.json"
    assert cep.main(["--site", str(tmp_path), "--receipt", str(receipt)]) == cep.EXIT_SETUP
    assert "setup problem" in capsys.readouterr().err and not receipt.exists()


def test_exit_2_and_a_blocked_receipt_when_chromium_is_absent(tmp_path: Path,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    site, receipt = _toy_site(tmp_path), tmp_path / "receipt.json"
    code = cep.main(["--site", str(site), "--browser", str(tmp_path / "no-such-chromium"), "--receipt", str(receipt)])
    assert code == cep.EXIT_SETUP
    assert "blocked, not passed" in capsys.readouterr().err
    written = json.loads(receipt.read_text(encoding="utf-8"))
    assert written["result"] == "blocked" and written["checks"] == []      # a blocked check records no pass


def test_the_page_carries_the_strings_the_checker_reads() -> None:
    page = SITE / cep.PAGE
    if not page.is_file():
        pytest.skip(f"no sibling site page at {page}; the string check did not run")
    source = page.read_text(encoding="utf-8")
    for text in (cep.SYNTHETIC_TEXT, cep.EMPTY_HEAD, cep.NOT_RECORDED, cep.WINDOW_MISS, cep.NO_INTERVENTION,
                 cep.BUNDLE_SCHEMA, cep.BELOW_DISPLAY, 'id="exp-methods-body"', cep.INDEX_SCHEMA, cep.INDEX_FILE,
                 cep.OPEN_ALL, cep.CLOSE_ALL, cep.CONFLICT, cep.ENDPOINT_LABEL, cep.ENDPOINT_FIRST_TOKEN,
                 cep.SHARE_LABEL.split(",")[0], cep.SCORE_LABEL, *(f'href="{route}"' for route in cep.EMPTY_ROUTES)):
        assert text in source, text
    # The empty statement and its two routes are static HTML: a reader without JavaScript sees them.
    static = source.split("<script>")[0]
    assert cep.EMPTY_HEAD in static and all(f'href="{route}"' in static for route in cep.EMPTY_ROUTES)
    for name in cep.STABLE_IDS:
        assert f'id="{name}"' in static, name
    # Reader-facing labels are in the page; each schema term they stand for is still there, in Methods & source.
    for label, term in cep.READER_LABELS.items():
        assert label.replace("&", "&amp;") in static and term.lower() in static.lower(), (label, term)
    for term in cep.SCHEMA_TERMS:
        assert term in static, term
    assert "<h1>Compare methods</h1>" in static and "<h1>Method-comparison bundles</h1>" not in source
    # The address syntax and the path rules are developer documentation now (docs/experiment_interface/preview.md).
    for syntax in ("?bundle=&lt;", "for example ?bundle=", "<code>?bundle", "A path that is absolute"):
        assert syntax not in source, syntax
    assert "bundleRefusal" in source                                        # the page still enforces the rule
    preview_doc = (ROOT / "docs" / "experiment_interface" / "preview.md").read_text(encoding="utf-8")
    assert "?bundle=<relative path under data/>" in preview_doc and "contains `..`" in preview_doc
    # The fields added to bundle version 1 on 2026-11-10: the page reads each by the name the bundle writer
    # uses, keeps the fallback text for a bundle without them, and marks the cells the checker reads.
    assert f"var NOT_IN_BUNDLE='{cep.NOT_IN_BUNDLE}'" in source
    assert "variant_text" in source and "prompt_text_export" in source and "vocabulary_size" in source
    for prefix in (cep.PROMPT_TEXT_ABSENT, cep.EXECUTED_ABSENT, cep.REUSED_ABSENT):
        assert prefix[len(cep.MISS):-len(cep.NOT_IN_BUNDLE)] + "'+NOT_IN_BUNDLE" in source, prefix
    for name in ("variant_inputs", "preprocessing_mode", "preprocessing_read_from", "executed_attempts",
                 "reused_events", "'data-col':'executed'", "'data-col':'reused'", "'data-col':'ica_preprocessing'",
                 "'data-col':'ica_preprocessing_source'", "['token_sha256',"):
        assert name in source, name
    assert "fetch(" in source and source.count("fetch(") == 1               # one request site, for both files
    for forbidden in ("http://", "<script src", "<link rel=\"stylesheet\"", "@import"):
        assert forbidden not in source.replace("http://www.w3.org/2000/svg", ""), forbidden


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


def test_the_preview_check_passes_in_chromium(tmp_path: Path) -> None:
    pytest.importorskip("playwright", reason="the playwright package is not installed; the browser check did not run")
    if not (SITE / cep.PAGE).is_file():
        pytest.skip(f"no sibling site checkout with {cep.PAGE} at {SITE}; the browser check did not run")
    browser = _chromium()
    if browser is None:
        pytest.skip("no Chromium executable found (CHROMIUM, PLAYWRIGHT_BROWSERS_PATH, /opt/pw-browsers, Playwright's "
                    "own); the browser check did not run")
    receipt_path, shots = tmp_path / "receipt.json", tmp_path / "shots"
    code = cep.main(["--site", str(SITE), "--browser", browser, "--receipt", str(receipt_path), "--shots", str(shots)])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    failed = [check for check in receipt["checks"] if check["result"] == "failed"]
    assert code == cep.EXIT_PASS and receipt["result"] == "passed", failed
    assert receipt["evidence"] == "local synthetic software test only"
    results = {check["name"]: check["result"] for check in receipt["checks"]}
    assert set(results.values()) == {"passed", "detected_then_restored_pass"}
    defects = [name for name, result in results.items() if result == "detected_then_restored_pass"]
    for wanted in ("wrong_schema", "missing_bundle_file", "without_a_state", "traversal",
                   "older_bundle_without_the_added_fields", "two_blocks_that_disagree"):
        assert any(wanted in name for name in defects), wanted
    assert len(receipt["checks"]) == 37                                     # 28 before 2026-11-10; none removed
    added = next(check for check in receipt["checks"]
                 if check["name"] == "prompt_hashes_token_counts_preprocessing_and_run_counts_equal_the_fixture")
    assert (added["result"], added["variant_rows"], added["executed_attempts"], added["reused_events"]) == (
        "passed", 9, 27, 5)
    assert added["prompt_text_on_page"] == 0 and added["prompt_text_exported_by_the_protocol_marker"] == 6
    checks = {check["name"]: check for check in receipt["checks"]}
    empty = checks["no_parameter_shows_the_empty_statement_and_requests_only_the_index"]
    assert (empty["result"], empty["data_requests"], empty["bundle_requests"]) == ("passed", 1, 0)
    assert empty["empty_statement"] == "No experiment comparisons published yet"
    assert empty["routes"] == ["../results/", "../methods.html"]
    assert checks["index_writer_never_lists_the_synthetic_bundle"]["not_listed_reasons"] == [
        "synthetic", "visibility_not_public"]
    assert checks["index_lists_a_publishable_bundle_and_its_link_opens_it"]["listed"] == 1
    dots = checks["dot_plot_values_and_positions_equal_the_bundle_and_the_fixture_logits"]
    assert (dots["result"], dots["panels"], dots["dots"]) == ("passed", 6, 18) and dots["largest_offset_px"] <= 1.0
    text = checks["prompt_text_shown_only_for_marked_cases_and_absent_state_for_the_rest"]
    assert (text["wording_rows_with_exported_text"], text["wording_rows_that_say_text_is_absent"]) == (6, 3)
    for name in ("reader_labels_shown_schema_terms_kept_and_endpoint_explained_once",
                 "section_ids_section_links_and_download_link_are_stable",
                 "old_section_link_opens_the_fold_it_now_sits_in", "forged_or_unreadable_index_links_nothing"):
        assert results[name] == "passed", name
    assert receipt["cli_steps"][-1]["prompt_text_families"] == ["fam-1", "fam-2"]
    assert receipt["browser_external_requests"] == [] and receipt["versions"]["chromium"]
    assert receipt["bundle"]["schema_version"] == "patientwords.experiment-bundle/1"
    assert [step["step"] for step in receipt["cli_steps"]][:2] == ["validate", "plan"]
    assert sorted(p.name for p in shots.iterdir()) == [
        "experiment_bundle_1280.png", "experiment_bundle_390.png", "experiment_no_parameter_1280.png"]
    assert not (SITE / "data" / "experiment_preview").exists()             # nothing reached the real site
    assert not (SITE / "data" / cep.RELABELLED_PARAM).exists()
    assert str(tmp_path) not in json.dumps(receipt) and str(ROOT) not in json.dumps(receipt)
