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
    for text in (cep.SYNTHETIC_TEXT, *cep.IDLE_SENTENCES, cep.NOT_RECORDED, cep.WINDOW_MISS, cep.NO_INTERVENTION,
                 cep.BUNDLE_SCHEMA, cep.BELOW_DISPLAY, 'id="exp-methods-body"'):
        assert text in source, text
    assert "fetch(" in source and source.count("fetch(") == 1               # one request site: the bundle
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
    for wanted in ("wrong_schema", "missing_bundle_file", "without_a_state", "traversal"):
        assert any(wanted in name for name in defects), wanted
    assert results["no_parameter_shows_the_statement_and_requests_no_data"] == "passed"
    assert receipt["browser_external_requests"] == [] and receipt["versions"]["chromium"]
    assert receipt["bundle"]["schema_version"] == "patientwords.experiment-bundle/1"
    assert [step["step"] for step in receipt["cli_steps"]][:2] == ["validate", "plan"]
    assert sorted(p.name for p in shots.iterdir()) == [
        "experiment_bundle_1280.png", "experiment_bundle_390.png", "experiment_no_parameter_1280.png"]
    assert not (SITE / "data" / "experiment_preview").exists()             # nothing reached the real site
    assert str(tmp_path) not in json.dumps(receipt) and str(ROOT) not in json.dumps(receipt)
