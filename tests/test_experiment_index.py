"""The experiment comparison index: its writer, its schema and its contract check.

``scripts/export_experiment_index.py`` writes ``data/experiments/index.json`` into a site checkout from the
bundle files under the site's ``data/``. ``scripts/experiment_index_contract.py`` checks a site that holds one.
What this file pins:

* a synthetic bundle, a bundle that is not ``public`` and a bundle with a restriction reason are never listed;
* a bundle is listed only at a path the experiments page accepts as an address, and the writer's path rule,
  the contract check's path rule and the preview check's mirror of the page rule agree on one table of cases;
* a listed bundle that exports prompt text is asked of the holdout seal first; a restricted text, or a seal
  that cannot be evaluated, stops the run with nothing written;
* the contract check fails on a missing, stale or hand-edited index and on any bundle under ``data/`` that may
  not be published;
* the index the sibling site holds validates and lists nothing (2026-11-10: no study bundle exists).

Bundles here are built from the synthetic fixture protocol. A "publishable" bundle is that fixture relabelled
by ``check_experiment_preview.relabelled_as_publishable``, written only under ``tmp_path``. Nothing in this
file is a measurement.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from scripts.experiments import bundle as bundle_module
from scripts.experiments import capabilities, planner
from scripts.experiments.store import RunStore

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"
FIXTURES = ROOT / "tests" / "fixtures" / "experiments"
PROTOCOL = FIXTURES / "protocol_synthetic.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


writer = _load("export_experiment_index", ROOT / "scripts" / "export_experiment_index.py")
contract = _load("experiment_index_contract", ROOT / "scripts" / "experiment_index_contract.py")
cep = _load("check_experiment_preview_for_index_tests", ROOT / "scripts" / "check_experiment_preview.py")
schema_adapter = _load("frontend_contract_schema_for_index_tests", ROOT / "scripts" / "frontend_contract_schema.py")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def err(self, artifact: str, path: str, message: str) -> None:
        self.errors.append(f"{artifact} :: {path} :: {message}")


def never(*row: object) -> None:
    raise AssertionError("the seal was consulted although no listed bundle exports text")


@pytest.fixture(scope="module")
def synthetic_bundle(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """One fixture bundle with exported placeholder text for fam-1, built once for this module."""
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    protocol["case_families"][0]["facts"].append(bundle_module.PROMPT_TEXT_MARKER)
    store = RunStore(tmp_path_factory.mktemp("index_run") / "run")
    store.run_fixture(planner.build_plan(protocol, capabilities.load_matrix()), "w0", fixtures_dir=FIXTURES,
                      protocol=protocol)
    store.collect()
    return bundle_module.build_bundle(store.run_dir, protocol=protocol)


def publishable(bundle: dict) -> dict:
    return cep.relabelled_as_publishable(bundle)


def site_with(tmp_path: Path, files: dict[str, object], *, page: bool = True) -> Path:
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    if page:
        (site / "experiments").mkdir()
        (site / "experiments" / "index.html").write_text("<!doctype html><title>toy</title>", encoding="utf-8")
    for relative, doc in files.items():
        path = site / "data" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
    return site


def write(site: Path, **kwargs: object) -> dict:
    index = writer.build_index(site, **kwargs)
    path = site / "data" / writer.INDEX_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index), encoding="utf-8")
    return index


def problems(site: Path) -> list[str]:
    report = Report()
    contract.check_experiment_index(report, site)
    return report.errors


# ------------------------------------------------------------------------------------------ eligibility

def test_a_synthetic_bundle_is_never_listed(synthetic_bundle: dict, tmp_path: Path) -> None:
    site = site_with(tmp_path, {"experiment_preview/bundle.json": synthetic_bundle})
    index = writer.build_index(site, row_restriction=never)
    assert index["comparisons"] == []
    assert index["not_listed"] == [{"file": "experiment_preview/bundle.json",
                                    "reasons": ["synthetic", "visibility_not_public"]}]
    assert index["totals"] == {"bundle_files": 1, "listed": 0, "not_listed": 1}
    # A synthetic bundle with every other label forged to "publishable" is still not listed: each of the four
    # places that say "synthetic" is enough on its own.
    for path, value in ((("evidence", "synthetic"), True), (("protocol", "synthetic"), True),
                        (("evidence", "evidence_class"), "synthetic_fixture")):
        forged = publishable(synthetic_bundle)
        forged[path[0]][path[1]] = value
        assert writer.ineligibility(forged, "experiments/x.json") == ["synthetic"], path
    forged = publishable(synthetic_bundle)
    forged["limitations"].insert(0, "synthetic_not_measurement")
    assert writer.ineligibility(forged, "experiments/x.json") == ["synthetic"]
    forged = publishable(synthetic_bundle)
    del forged["evidence"]["synthetic"]                                    # an absent label counts against it
    assert "synthetic" in writer.ineligibility(forged, "experiments/x.json")


@pytest.mark.parametrize("visibility, reasons, expected", [
    ("restricted", ["redistribution_limited_text"], ["visibility_not_public", "restricted"]),
    ("not_published", [], ["visibility_not_public"]),
    ("public", ["sealed_holdout"], ["restricted"]),
    (None, [], ["visibility_not_public"]),
])
def test_a_restricted_or_unpublished_bundle_is_never_listed(synthetic_bundle: dict, tmp_path: Path, visibility: object,
                                                            reasons: list[str], expected: list[str]) -> None:
    doc = publishable(synthetic_bundle)
    doc["evidence"]["visibility"], doc["evidence"]["restriction_reasons"] = visibility, reasons
    site = site_with(tmp_path, {"experiments/held.json": doc, "experiments/open.json": publishable(synthetic_bundle)})
    index = writer.build_index(site, row_restriction=never)
    assert [entry["bundle"] for entry in index["comparisons"]] == ["experiments/open.json"]
    assert index["not_listed"] == [{"file": "experiments/held.json", "reasons": expected}]
    assert "held.json" not in json.dumps(index["comparisons"])


def test_a_publishable_bundle_is_listed_with_its_own_labels_and_hash(synthetic_bundle: dict, tmp_path: Path) -> None:
    doc = publishable(synthetic_bundle)
    doc["evidence"]["analysis_memberships"] = ["exploratory-open/1"]
    site = site_with(tmp_path, {"experiments/toy-1.json": doc})
    index = writer.build_index(site, row_restriction=never)
    raw = (site / "data" / "experiments" / "toy-1.json").read_bytes()
    assert index["schema_version"] == "patientwords.experiment-index/1"
    assert index["comparisons"] == [{
        "bundle": "experiments/toy-1.json", "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "protocol": {key: doc["protocol"][key] for key in ("id", "version", "sha256")},
        "model": {"study_id": doc["protocol"]["model"]["study_id"], "hf_id": doc["protocol"]["model"]["hf_id"]},
        "evidence_class": "unclassified", "clinical_review": "domain_review_pending", "visibility": "public",
        "analysis_memberships": ["exploratory-open/1"], "cases": 3, "methods": doc["protocol"]["methods"],
        "primary_endpoint": doc["protocol"]["primary_endpoint"], "prompt_text_cases": 0}]
    assert "_provenance" not in index and writer.build_index(site, row_restriction=never) == index   # deterministic
    errors: list[str] = []
    schema = json.loads(writer.INDEX_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_adapter.check_schema_subset(lambda a, where, why: errors.append(f"{where}: {why}"), "index", index, schema)
    assert errors == []
    text = json.dumps(index)
    assert not [e["prompt"] for f in synthetic_bundle["protocol"]["families"]
                for e in f.get("variant_text", {}).values() if e["prompt"] in text]      # labels and hashes only


def test_files_that_are_not_bundles_are_ignored_and_broken_ones_are_named(synthetic_bundle: dict,
                                                                          tmp_path: Path) -> None:
    newer = dict(publishable(synthetic_bundle), schema_version="patientwords.experiment-bundle/2")
    invalid = publishable(synthetic_bundle)
    invalid["unexpected_top_level_key"] = 1
    site = site_with(tmp_path, {
        "other.json": {"note": "mentions patientwords.experiment-bundle/1 and is not a bundle"},
        "plain.json": {"schema_version": "something-else/1"},
        "experiments/v2.json": newer,
        "experiments/broken.json": '{"schema_version": "patientwords.experiment-bundle/1", ',
        "experiments/invalid.json": invalid,
    })
    index = writer.build_index(site, row_restriction=never)
    assert index["comparisons"] == []
    assert {row["file"]: row["reasons"] for row in index["not_listed"]} == {
        "experiments/broken.json": ["unreadable"], "experiments/invalid.json": ["invalid_structure"],
        "experiments/v2.json": ["not_bundle_version_1"]}
    assert index["totals"]["bundle_files"] == 3


# ------------------------------------------------------------------------------------------ the path rule

ADDRESS_CASES = (*cep.PARAM_CASES, "experiments/toy-1.json", "a/b/c-d_e.v1.json", "bundle.json", ".json",
                 "a/.json", "a b/c.json", "a/./b.json", "A/_x.JSON", "x" * 195 + ".json")


@pytest.mark.parametrize("value", ADDRESS_CASES)
def test_the_three_statements_of_the_address_rule_agree(value: str) -> None:
    accepted = cep.bundle_param_refusal(value) is None       # the mirror the browser run compares with the page
    assert writer.addressable(value) is accepted, value
    assert contract.page_accepts(value) is accepted, value


def test_a_bundle_at_a_path_the_page_refuses_is_not_listed(synthetic_bundle: dict, tmp_path: Path) -> None:
    site = site_with(tmp_path, {"experiments/two words/toy.json": publishable(synthetic_bundle)})
    index = writer.build_index(site, row_restriction=never)
    assert index["comparisons"] == [] and index["not_listed"][0]["reasons"] == ["path_not_addressable"]
    assert any("refuses this path" in error for error in problems(site))


# ------------------------------------------------------------------------------------------ exported text

def with_text(synthetic_bundle: dict) -> dict:
    """A relabelled copy that keeps the exported placeholder text of fam-1 and names a legacy row for it."""
    doc = publishable(synthetic_bundle)
    source = synthetic_bundle["protocol"]["families"][0]
    doc["protocol"]["families"][0]["variant_text"] = copy.deepcopy(source["variant_text"])
    doc["protocol"]["families"][0]["prompt_text_export"] = dict(source["prompt_text_export"],
                                                               seal_check="passed_at_export")
    doc["protocol"]["families"][0]["legacy_join"] = {"batch": "placeholder_batch", "batch_index": 4, "model": "toy"}
    return doc


def test_exported_text_is_asked_of_the_seal_before_a_bundle_is_listed(synthetic_bundle: dict, tmp_path: Path) -> None:
    site = site_with(tmp_path, {"experiments/text.json": with_text(synthetic_bundle)})
    asked: list[tuple] = []

    def open_seal(batch, index, prompt):
        asked.append((batch, index, bool(prompt)))
        return None

    index = writer.build_index(site, row_restriction=open_seal)
    assert index["comparisons"][0]["prompt_text_cases"] == 1
    assert asked == [("placeholder_batch", 4, True)] + [(None, None, True)] * 3

    sealed_variant = sorted(synthetic_bundle["protocol"]["families"][0]["variant_text"])[1]
    sealed_text = synthetic_bundle["protocol"]["families"][0]["variant_text"][sealed_variant]["prompt"]
    with pytest.raises(writer.IndexRefusal) as refused:
        writer.build_index(site, row_restriction=lambda batch, index, prompt: (
            "sealed_holdout" if prompt == sealed_text and batch is None else None))
    message = str(refused.value)
    assert "experiments/text.json" in message and f"variant {sealed_variant}" in message
    assert sealed_text not in message                                       # a refusal never repeats text

    with pytest.raises(writer.IndexRefusal, match="legacy row"):
        writer.build_index(site, row_restriction=lambda batch, index, prompt: (
            "sealed_holdout" if batch == "placeholder_batch" else None))


def test_main_writes_nothing_when_text_is_restricted_or_the_seal_cannot_be_evaluated(
        synthetic_bundle: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    site = site_with(tmp_path, {"experiments/text.json": with_text(synthetic_bundle)})
    out = site / "data" / "experiments" / "index.json"

    class SealError(RuntimeError):
        pass

    def broken(batch, index, prompt):
        raise SealError("the seal's inputs are absent")

    for stub, phrase in ((lambda *row: "sealed_holdout", "refusing, nothing written"),
                         (broken, "could not be evaluated, nothing written")):
        monkeypatch.setattr(writer, "_default_row_restriction", lambda stub=stub: stub)
        assert writer.main(["--site", str(site)]) == 2
        assert phrase in capsys.readouterr().err and not out.exists()
    monkeypatch.setattr(writer, "_default_row_restriction", lambda: (lambda *row: None))
    assert writer.main(["--site", str(site)]) == 0 and json.loads(out.read_text("utf-8"))["totals"]["listed"] == 1


# ------------------------------------------------------------------------------------------ the command

def test_main_writes_a_stamped_index_and_dry_run_writes_nothing(synthetic_bundle: dict, tmp_path: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    site = site_with(tmp_path, {"experiment_preview/bundle.json": synthetic_bundle})
    out = site / "data" / "experiments" / "index.json"
    assert writer.main(["--site", str(site), "--dry-run"]) == 0 and not out.exists()
    assert "DRY RUN" in capsys.readouterr().out
    assert writer.main(["--site", str(site)]) == 0
    printed = capsys.readouterr()
    assert "1 bundle file(s) under data/, 0 listed, 1 not listed" in printed.out
    assert "not listed - data/experiment_preview/bundle.json: synthetic" in printed.err
    index = json.loads(out.read_text(encoding="utf-8"))
    assert index["comparisons"] == [] and index["_provenance"]["generator"] == "scripts/export_experiment_index.py"
    assert set(index["_provenance"]) == {"generator", "engine_sha", "generated_utc"}
    # The index is not a bundle: a second run does not count its own output.
    assert writer.main(["--site", str(site)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["totals"]["bundle_files"] == 1
    assert writer.main(["--site", str(tmp_path / "no-such-site")]) == 2
    assert "no data/ directory" in capsys.readouterr().err


# ------------------------------------------------------------------------------------------ contract check

def test_the_contract_check_passes_the_writers_index_and_fails_a_changed_one(synthetic_bundle: dict,
                                                                             tmp_path: Path) -> None:
    site = site_with(tmp_path, {"experiments/toy-1.json": publishable(synthetic_bundle)})
    index = write(site, row_restriction=never)
    assert problems(site) == []
    path = site / "data" / "experiments" / "index.json"

    def changed(edit) -> list[str]:
        doc = copy.deepcopy(index)
        edit(doc)
        path.write_text(json.dumps(doc), encoding="utf-8")
        try:
            return problems(site)
        finally:
            path.write_text(json.dumps(index), encoding="utf-8")

    assert any("clinical_review" in e for e in changed(
        lambda d: d["comparisons"][0].update(clinical_review="reviewed")))          # a hand-edited label
    assert any("bundle_sha256" in e and "stale" in e for e in changed(
        lambda d: d["comparisons"][0].update(bundle_sha256="0" * 64)))
    assert any("is not listed" in e for e in changed(lambda d: d.update(comparisons=[])))
    assert any("failed request" in e for e in changed(
        lambda d: d["comparisons"][0].update(bundle="experiments/absent.json")))
    assert any("refuses the address" in e for e in changed(
        lambda d: d["comparisons"][0].update(bundle="../experiments/toy-1.json")))
    assert any("$.totals.listed" in e for e in changed(lambda d: d["totals"].update(listed=5)))
    assert any("listed twice" in e for e in changed(
        lambda d: d["comparisons"].append(copy.deepcopy(d["comparisons"][0]))))
    assert any("schema_version" in e for e in changed(lambda d: d.update(schema_version="other/1")))
    assert changed(lambda d: d.pop("eligibility"))                                    # the schema is applied
    path.write_text("{not json", encoding="utf-8")
    assert any("unreadable" in e for e in problems(site))


def test_the_contract_check_fails_a_bundle_that_may_not_be_published_wherever_it_lies(synthetic_bundle: dict,
                                                                                      tmp_path: Path) -> None:
    restricted = publishable(synthetic_bundle)
    restricted["evidence"].update(visibility="restricted", restriction_reasons=["redistribution_limited_text"])
    site = site_with(tmp_path, {"experiment_preview/bundle.json": synthetic_bundle, "deep/er/held.json": restricted})
    write(site, row_restriction=never)                      # the writer lists neither; the directory is still public
    errors = problems(site)
    assert any("experiment_preview/bundle.json" in e and "synthetic" in e for e in errors)
    assert any("deep/er/held.json" in e and "'restricted'" in e and "restriction reason" in e for e in errors)
    # Listing one of them by hand does not make it publishable.
    path = site / "data" / "experiments" / "index.json"
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["comparisons"].append({"bundle": "experiment_preview/bundle.json"})
    path.write_text(json.dumps(forged), encoding="utf-8")
    assert any("is listed and may not be published" in e for e in problems(site))


def test_a_missing_index_is_an_error_only_when_the_page_that_requests_it_exists(tmp_path: Path) -> None:
    with_page = site_with(tmp_path / "a", {})
    assert any("artifact missing" in e and "experiments/index.html" in e for e in problems(with_page))
    without_page = site_with(tmp_path / "b", {}, page=False)
    report = Report()
    contract.check_experiment_index(report, without_page)
    assert report.errors == [] and len(report.notes) == 1


def test_the_writer_and_the_contract_check_agree_on_which_labels_allow_publication(synthetic_bundle: dict) -> None:
    """Two statements of one rule, written apart. Structure and path are the writer's alone."""
    cases = [publishable(synthetic_bundle), synthetic_bundle]
    for key, value in (("visibility", "restricted"), ("visibility", "not_published"), ("visibility", None),
                       ("restriction_reasons", ["artifact_integrity"]), ("synthetic", True),
                       ("evidence_class", "synthetic_fixture")):
        doc = publishable(synthetic_bundle)
        doc["evidence"][key] = value
        cases.append(doc)
    for doc in cases:
        listed = writer.ineligibility(doc, "experiments/x.json") == []
        assert listed is (contract.publication_problems(doc) == []), doc["evidence"]
    assert sum(writer.ineligibility(doc, "experiments/x.json") == [] for doc in cases) == 1


# ------------------------------------------------------------------------------------------ the real site

def test_the_sites_index_validates_and_lists_nothing_today() -> None:
    path = SITE / "data" / "experiments" / "index.json"
    if not path.is_file():
        pytest.skip(f"no sibling site index at {path}; the check of the published index did not run")
    index = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    schema = json.loads(writer.INDEX_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_adapter.check_schema_subset(lambda a, where, why: errors.append(f"{where}: {why}"), "index", index, schema)
    assert errors == []
    assert index["comparisons"] == [] and index["not_listed"] == []           # 2026-11-10: no study bundle exists
    assert index["totals"] == {"bundle_files": 0, "listed": 0, "not_listed": 0}
    assert index["_provenance"]["generator"] == "scripts/export_experiment_index.py"
    assert problems(SITE) == []
    fresh = writer.build_index(SITE, row_restriction=never)                    # the file is what the writer gives
    assert {key: index[key] for key in fresh} == fresh
