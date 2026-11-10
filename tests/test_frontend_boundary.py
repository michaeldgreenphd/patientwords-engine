"""The synthetic boundary check's own offline tests: layout, probe, fixture arithmetic, summary oracle.

No browser, no network, no model. Every string is an abstract placeholder. The run that
uses these pieces is scripts/check_frontend_boundary.py; it needs its own Python 3.13
environment (docs/exploratory/frontend_boundary.md) and is not started from here.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import timedelta
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from boundary_client import layout, layout_probe  # noqa: E402
from boundary_client.assertions import assert_summary_penalty  # noqa: E402
import validate_frontend_contract as vfc  # noqa: E402

FIXTURE = json.loads((ROOT / "tests/fixtures/frontend_boundary.json").read_text(encoding="utf-8"))
EXPECTED = FIXTURE["expected"]
BASE = "gemma-2-2b"

WORKFLOW = """\
jobs:
  checks:
    steps:
      - name: Check out the site
        uses: actions/checkout@0000000000000000000000000000000000000000 # v4
        with:
          path: site
      - name: Check out the engine
        uses: actions/checkout@0000000000000000000000000000000000000000 # v4
        with:
          repository: owner/patientwords-engine
          path: patientwords-engine
          filter: blob:none
          sparse-checkout: |
            scripts
            data
            ops
            docs

      - name: Next step
        run: |
          echo done
"""


def workflow(tmp_path: Path, text: str = WORKFLOW) -> Path:
    path = tmp_path / "site_checks.yml"
    path.write_text(text, encoding="utf-8")
    return path


def checkout(tmp_path: Path, files: dict[str, str]) -> Path:
    """A throwaway git checkout under tmp_path holding `files`. Nothing is committed; none is needed."""
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


# ---- the layout is derived from the site workflow ----

def test_the_sparse_checkout_block_is_read_from_the_workflow(tmp_path):
    assert layout.sparse_checkout(workflow(tmp_path)) == (["scripts", "data", "ops", "docs"], True)


def test_cone_mode_off_means_no_root_files(tmp_path):
    text = WORKFLOW.replace("          filter: blob:none\n",
                            "          filter: blob:none\n          sparse-checkout-cone-mode: false\n")
    assert layout.sparse_checkout(workflow(tmp_path, text)) == (["scripts", "data", "ops", "docs"], False)


@pytest.mark.parametrize("text, says", [
    (WORKFLOW.replace("          sparse-checkout: |\n            scripts\n            data\n            ops\n"
                      "            docs\n", ""), "holds 0"),
    (WORKFLOW + WORKFLOW.split("    steps:\n", 1)[1], "holds 2"),
    (WORKFLOW.replace("owner/patientwords-engine", "owner/another-repository"), "does not check out"),
    (WORKFLOW.replace("            docs\n", "            docs/*.md\n"), "plain directory names"),
    (WORKFLOW.replace("            scripts\n", "            !scripts\n"), "plain directory names"),
])
def test_a_workflow_the_layout_cannot_be_derived_from_is_refused_by_name(tmp_path, text, says):
    path = workflow(tmp_path, text)
    with pytest.raises(layout.LayoutError) as caught:
        layout.sparse_checkout(path)
    assert says in str(caught.value) and str(path) in str(caught.value)


def test_a_missing_workflow_is_refused_by_name(tmp_path):
    with pytest.raises(layout.LayoutError) as caught:
        layout.sparse_checkout(tmp_path / "absent.yml")
    assert "absent.yml" in str(caught.value)


def test_select_takes_whole_directories_and_root_files_only():
    files = ["README.txt", "scripts/a.py", "scripts/deep/b.py", "data/x.json", "datafile/y.json",
             "tests/test_a.py", "other/z.json"]
    assert layout.select(files, ["scripts", "data"], True) == ["README.txt", "scripts/a.py", "scripts/deep/b.py",
                                                               "data/x.json"]
    assert layout.select(files, ["scripts", "data"], False) == ["scripts/a.py", "scripts/deep/b.py", "data/x.json"]


def test_committable_files_are_untracked_or_tracked_and_never_ignored(tmp_path):
    root = checkout(tmp_path, {".gitignore": "cache/\n*.tmp\n", "scripts/a.py": "", "data/x.json": "{}",
                               "cache/big.bin": "x", "data/scratch.tmp": "x"})
    assert sorted(layout.committable_files(root)) == [".gitignore", "data/x.json", "scripts/a.py"]
    if (ROOT / ".git").exists():   # the tracked half, on the real checkout: a tracked file and no ignored one
        real = set(layout.committable_files(ROOT))
        assert "scripts/check_frontend_boundary.py" in real
        assert not any("__pycache__" in name or name.startswith(".pytest_cache/") for name in real)


def test_build_copies_the_selection_and_refuses_a_stale_test_support_entry_by_name(tmp_path):
    root = checkout(tmp_path, {"scripts/a.py": "A", "data/x.json": "{}", "tests/test_a.py": "T"})
    target = tmp_path / "layout"
    built = layout.build(root, target, ["scripts/a.py", "data/x.json"], ["tests/test_a.py"])
    assert built == {"files": 3, "bytes": 4}
    assert sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()) == [
        "data/x.json", "scripts/a.py", "tests/test_a.py"]
    with pytest.raises(layout.LayoutError) as caught:
        layout.build(root, tmp_path / "second", ["scripts/a.py"], ["tests/test_gone.py"])
    assert "tests/test_gone.py" in str(caught.value)
    assert not (tmp_path / "second").exists()


def test_the_real_layout_holds_the_files_whose_absence_failed_the_boundary():
    """Regression for the failure this layout replaced. The earlier layout copied one file from data/
    (data/petri/publication_deviations.json); the validator's legacy-report registry and the open-results
    policy were absent and sixteen selected tests failed in it. Both are in site CI's sparse checkout."""
    site_workflow = ROOT.parent / "patientwords" / layout.WORKFLOW
    if not site_workflow.is_file():
        pytest.skip("no sibling site checkout with the site workflow")
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout (the boundary's own temporary layout): the file list comes from git")
    directories, root_files = layout.sparse_checkout(site_workflow)
    held = set(layout.select(layout.committable_files(ROOT), directories, root_files))
    for name in ("data/jev/legacy_frontend_reports.json", "data/results_policy/policy.v1.json",
                 "data/petri/publication_deviations.json", "scripts/validate_frontend_contract.py",
                 "scripts/contracts/simulated_scenarios.v1.schema.json", "pyproject.toml"):
        assert name in held, name
    assert not any(name.startswith(("tests/", "trace_out/", "medlang_circuits/")) for name in held)


# ---- a file a stage asks for and the layout lacks is named ----

ASKS = """
import os, sys
from pathlib import Path
root = Path(sys.argv[1])
(root / "data/present.json").read_text()
os.path.exists(root / "extra/outside.json")            # existence test, never opened
Path(root / "extra/also_outside.json").is_file()
try:
    open(root / "tests/fixtures/needed.json").close()   # opened without a test first
except OSError:
    pass
try:
    os.listdir(root / "extra/folder")
except OSError:
    pass
os.path.exists(root / "nowhere/optional.json")          # no checkout has it
os.path.exists(root / "cache/ignored.bin")              # the checkout has it, git ignores it
os.path.exists(Path(sys.argv[2]) / "elsewhere.json")    # outside the layout root
"""


def probe_run(tmp_path: Path, root: Path, target: Path, code: str = ASKS) -> Path:
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "sitecustomize.py").write_text(
        (ROOT / "scripts/boundary_client/layout_probe.py").read_text(encoding="utf-8"), encoding="utf-8")
    log = tmp_path / "asked.log"
    environment = {**os.environ, "PYTHONPATH": str(probe), layout_probe.ROOT_ENV: str(target),
                   layout_probe.LOG_ENV: str(log)}
    subprocess.run([sys.executable, "-c", code, str(target), str(tmp_path)], check=True, env=environment,
                   cwd=target)
    return log


def test_a_file_the_checkout_holds_and_the_layout_lacks_is_named(tmp_path):
    root = checkout(tmp_path, {
        ".gitignore": "cache/\n", "data/present.json": "{}", "extra/outside.json": "{}",
        "extra/also_outside.json": "{}", "extra/folder/inner.json": "{}", "tests/fixtures/needed.json": "{}",
        "cache/ignored.bin": "x"})
    target = tmp_path / "layout"
    layout.build(root, target, ["data/present.json"], [])
    log = probe_run(tmp_path, root, target)
    assert layout.absent_inputs(root, log) == ["extra/also_outside.json", "extra/folder", "extra/outside.json",
                                               "tests/fixtures/needed.json"]
    asked = set(log.read_text(encoding="utf-8").splitlines())
    assert {"nowhere/optional.json", "cache/ignored.bin"} <= asked    # recorded, and judged harmless
    assert not any("elsewhere.json" in line or "present.json" in line for line in asked)


def test_a_complete_layout_reports_nothing(tmp_path):
    root = checkout(tmp_path, {"data/present.json": "{}"})
    target = tmp_path / "layout"
    layout.build(root, target, ["data/present.json"], [])
    code = "import sys; from pathlib import Path; Path(sys.argv[1], 'data/present.json').read_text()"
    assert layout.absent_inputs(root, probe_run(tmp_path, root, target, code)) == []
    assert layout.absent_inputs(root, tmp_path / "no-such.log") == []


def test_the_probe_does_nothing_without_its_two_variables(tmp_path):
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "sitecustomize.py").write_text(
        (ROOT / "scripts/boundary_client/layout_probe.py").read_text(encoding="utf-8"), encoding="utf-8")
    environment = {k: v for k, v in os.environ.items() if k not in (layout_probe.ROOT_ENV, layout_probe.LOG_ENV)}
    done = subprocess.run([sys.executable, "-c", "import os; print(os.stat.__module__)"], check=True,
                          env={**environment, "PYTHONPATH": str(probe)}, capture_output=True, text=True)
    assert done.stdout.strip() in ("posix", "nt")


# ---- disk and temporary-directory rules ----

def test_too_little_free_space_is_refused_before_any_copy(tmp_path, monkeypatch):
    usage = type(shutil.disk_usage(tmp_path))
    monkeypatch.setattr(layout.shutil, "disk_usage", lambda where: usage(10 * 2**20, 7 * 2**20, 3 * 2**20))
    with pytest.raises(layout.LayoutError) as caught:
        layout.require_free_space(tmp_path, 2 * 2**20, "the copy")
    assert "3 MiB free" in str(caught.value) and "2 MiB" in str(caught.value)
    assert layout.require_free_space(tmp_path, 1 * 2**20, "the copy") == 3 * 2**20


def test_tree_bytes_skips_named_top_level_directories(tmp_path):
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep/a").write_text("12345")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/b").write_text("1234567")
    assert layout.tree_bytes(tmp_path, skip=(".git",)) == 5
    assert layout.tree_bytes(tmp_path) == 12


def test_the_browser_gets_a_short_tmpdir_only_when_the_runs_own_is_too_long():
    assert layout.browser_tmpdir("/tmp") is None
    assert layout.browser_tmpdir("/tmp/" + "d" * 40) is None
    assert layout.browser_tmpdir("/tmp/" + "d" * 80) == "/tmp"


# ---- the repeated-phrase fixture: arithmetic, oracle and deliberate defects ----

def scored_rows() -> list[tuple[str, int, str, Fraction]]:
    """(batch, index, clinical prompt, penalty) of every base-model result with a numeric penalty, read from
    the fixture's synthetic trace summaries. Exact fractions; no producer or validator code."""
    rows = []
    for name, part in FIXTURE["engine_files"].items():
        if not name.startswith("trace_out/") or part["graph_model"] != BASE:
            continue
        batch = name.split("/")[1]
        for result in part["results"]:
            if result["language_penalty"] is not None:
                rows.append((batch, result["index"], result["prompts"]["clinical"],
                             Fraction(str(result["language_penalty"]))))
    return rows


def test_the_fixture_repeats_one_clinical_phrase_across_two_batches():
    rows = scored_rows()
    repeated = EXPECTED["repeated_phrase"]
    carriers = [[batch, index] for batch, index, prompt, _ in rows if prompt == repeated["clinical_prompt"]]
    assert sorted(carriers) == sorted(repeated["rows"])
    assert len({batch for batch, _ in carriers}) == 2
    patient = {FIXTURE["expected"]["scenarios"][str(n)]["patient_prompt"]
               for n, key in enumerate(EXPECTED["scenario_keys"], start=1) if key in repeated["rows"]}
    assert len(patient) == 2, "the two rows must differ in the patient prompt, or keying on it would also pass"


def test_the_fixtures_typed_summary_agrees_with_exact_arithmetic_on_its_own_rows():
    """The literals in expected.summary were typed by hand. This recomputes them here with exact fractions
    from the fixture's inputs, so a typing slip in either place fails. It imports no producer or validator."""
    rows = scored_rows()
    summary = EXPECTED["summary"]
    by_phrase: dict[str, list[Fraction]] = {}
    for _, _, prompt, penalty in rows:
        by_phrase.setdefault(prompt, []).append(penalty)
    phrase_means = [sum(values) / len(values) for values in by_phrase.values()]
    assert summary["n_scored_rows"] == len(rows) == 3
    assert summary["n_phrases"] == len(phrase_means) == 2
    assert Fraction(str(summary["mean_rows_raw"])) == sum(p for *_, p in rows) / len(rows) == Fraction(-8, 100)
    assert Fraction(str(summary["mean_phrase_deduped"])) == sum(phrase_means) / len(phrase_means) == Fraction(-6, 100)
    assert summary["ci95"] is None and len(phrase_means) < 3
    assert summary["derivation"], "the arithmetic is written out in the fixture"


def test_the_fixture_tells_phrases_from_rows_at_every_stage_that_prints_them():
    """The phrase count, the phrase-level mean and the row mean are three different numbers, and they stay
    different after the pages' rounding to whole percentage points."""
    summary = EXPECTED["summary"]
    assert summary["n_phrases"] != summary["n_scored_rows"]
    assert round(abs(summary["mean_phrase_deduped"]) * 100) != round(abs(summary["mean_rows_raw"]) * 100)
    wrong = FIXTURE["summary_defects"]["pre_correction_form"]
    assert wrong["n_phrases"] == summary["n_scored_rows"] and wrong["mean_phrase_deduped"] == summary["mean_rows_raw"]
    shown = {item["selector"]: item["text"] for item in EXPECTED["summary_sentences"]}
    before = {item["selector"]: item["text"] for item in FIXTURE["summary_defects"]["pre_correction_sentences"]}
    assert shown.keys() == before.keys() and len(shown) == 3
    for selector, text in shown.items():
        assert " 2 distinct " in text and "−6" in text, selector
        assert " 3 distinct " in before[selector] and "−8" in before[selector], selector


def payload() -> dict:
    """The smallest payload carrying what the summary checks read, typed from the fixture's expectations."""
    rows = []
    for number, (batch, index) in enumerate(EXPECTED["scenario_keys"], start=1):
        measured = EXPECTED["models"][BASE]["rows"][str(number)]
        rows.append({"index": number, "batch": batch, "batch_index": index,
                     "clinical_prompt": EXPECTED["scenarios"][str(number)]["clinical_prompt"],
                     "language_penalty": measured["language_penalty"]})
    return {"scenarios": rows,
            "summary": {"penalty": {field: EXPECTED["summary"][field] for field in
                                    ("n_scored_rows", "n_phrases", "mean_rows_raw", "mean_phrase_deduped", "ci95")}}}


def test_the_oracle_accepts_the_hand_calculated_summary():
    assert_summary_penalty(payload(), EXPECTED)


@pytest.mark.parametrize("defect, says", [
    ("pre_correction_form", "summary penalty n_phrases: expected 2, got 3"),
    ("wrong_values", "summary penalty n_phrases: expected 2, got 5"),
])
def test_the_oracle_rejects_both_deliberate_defects_on_every_date(defect, says):
    broken = payload()
    broken["summary"]["penalty"].update(FIXTURE["summary_defects"][defect])
    with pytest.raises(AssertionError, match=says):
        assert_summary_penalty(broken, EXPECTED)


@pytest.mark.parametrize("field, value", [("mean_phrase_deduped", -0.08), ("mean_rows_raw", -0.06),
                                          ("n_scored_rows", 2), ("ci95", [-0.12, 0.0])])
def test_the_oracle_rejects_one_wrong_field(field, value):
    broken = payload()
    broken["summary"]["penalty"][field] = value
    with pytest.raises(AssertionError, match=f"summary penalty {field}"):
        assert_summary_penalty(broken, EXPECTED)


def test_the_oracle_rejects_a_payload_that_lost_the_repetition():
    """Right numbers over rows that no longer repeat a phrase are not the regression this fixture is for."""
    broken = payload()
    broken["scenarios"][-1]["clinical_prompt"] = "Synthetic placeholder other"
    with pytest.raises(AssertionError, match="rows carrying the repeated clinical prompt"):
        assert_summary_penalty(broken, EXPECTED)
    same_batch = copy.deepcopy(EXPECTED)
    same_batch["repeated_phrase"]["rows"] = [same_batch["repeated_phrase"]["rows"][0]]
    one_row = payload()
    one_row["scenarios"][-1]["clinical_prompt"] = "Synthetic placeholder other"
    with pytest.raises(AssertionError, match="must span different batches"):
        assert_summary_penalty(one_row, same_batch)


def summary_report(penalty_changes: dict, today) -> vfc.Report:
    checked = payload()
    checked["summary"]["penalty"].update(penalty_changes)
    report = vfc.Report()
    vfc.check_summary_penalty(report, "simulated_scenarios.json", checked, today)
    return report


@pytest.mark.parametrize("today", [vfc.LEGACY_SUMMARY_ACCEPTED_THROUGH,
                                   vfc.LEGACY_SUMMARY_ACCEPTED_THROUGH + timedelta(days=1)])
def test_the_validator_rejects_the_wrong_values_defect_on_both_sides_of_the_transition(today):
    """The boundary's defect 3 must be one the dated transition cannot excuse."""
    report = summary_report(FIXTURE["summary_defects"]["wrong_values"], today)
    assert [error.split(" :: ")[1] for error in report.errors] == ["$.summary.penalty.n_phrases",
                                                                 "$.summary.penalty.mean_phrase_deduped"]
    assert report.notes == []
    assert summary_report({}, today).errors == []


def test_the_pre_correction_defect_is_the_form_the_transition_names():
    """The boundary's defect 4 is the validator's legacy form: a note through the date, an error after it.
    The fixture's oracle rejects it on both dates (test_the_oracle_rejects_both_deliberate_defects...)."""
    form = FIXTURE["summary_defects"]["pre_correction_form"]
    before = summary_report(form, vfc.LEGACY_SUMMARY_ACCEPTED_THROUGH)
    assert before.errors == [] and len(before.notes) == 1 and "$.summary.penalty :: legacy" in before.notes[0]
    after = summary_report(form, vfc.LEGACY_SUMMARY_ACCEPTED_THROUGH + timedelta(days=1))
    assert len(after.errors) == 1 and "$.summary.penalty :: legacy" in after.errors[0]
