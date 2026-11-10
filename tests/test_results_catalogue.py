"""The results catalogue and analysis snapshots (scripts/export_results_catalogue.py, scripts/results_snapshot.py).

The catalogue is the public, evolving record: every run, in whatever state, with its evidence class, review
status and analysis membership. A snapshot is the immutable record of what one analysis was computed from.
These tests run both over a synthetic engine root and check the distinctions end to end, in the files a reader
would download:

* a post-registration result and a hand-authored example are in the catalogue with rows and labels, and in no
  study snapshot;
* a null result, an opposite-direction result, a partial run and an empty part are all discoverable;
* a sealed row is in no written file (index, rows, stimuli, either CSV), and an unevaluable seal writes nothing;
* a redistribution-limited family and a part changed after its hash was recorded are listed without rows;
* the ledger records each part once and never rewrites a hash;
* a snapshot cannot be overwritten, detects a changed input, and a later snapshot names what it supersedes.

All phrases are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import export_results_catalogue as cat  # noqa: E402
import results_policy as rp  # noqa: E402
import results_snapshot as snap  # noqa: E402
import tierb_split  # noqa: E402
from frontend_contract_schema import check_schema_subset  # noqa: E402

BATCH = "pairs_20200101T000000Z"
SEALED = next(f"alpha prompt {i}" for i in range(1, 500) if tierb_split.is_holdout(f"alpha prompt {i}"))
OPEN = [f"alpha prompt {i}" for i in range(1, 500) if not tierb_split.is_holdout(f"alpha prompt {i}")][:3]
CLINICAL = [OPEN[0], SEALED, OPEN[1], OPEN[2]]                 # pair 2 is the sealed one
PATIENT = [f"beta wording {i}" for i in (1, 2, 3, 4)]
_SPREAD = {"clinical": [['Output " alpha"', 0.6], ['Output " beta"', 0.2], ["gamma", 0.1], ["delta", 0.05]],
           "patient": [['Output " beta"', 0.5], ['Output " alpha"', 0.3]]}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _result(index: int, penalty: float = -0.3, **extra):
    return {"index": index, "prompts": {"clinical": CLINICAL[index - 1], "patient": PATIENT[index - 1]},
            "probabilities": {"clinical": 0.6, "patient": 0.6 + penalty}, "predictive_spread": _SPREAD,
            "language_penalty": penalty, "target_token": 'Output " alpha"',
            "clinical_mass": {"clinical": 0.42, "patient": 0.31}, **extra}      # an object per phrasing, as landed


def _summary(results, graph_model, backend="logits", **extra):
    return {"graph_model": graph_model, "backend": backend, "source_set": None, "completed": True,
            "pairs_requested": len(results), "results": results, **extra}


def _part(root: Path, run_dir: str, summary, name="batch_summary.part_01.json") -> Path:
    path = root / "trace_out" / run_dir / name
    _write(path, summary)
    return path


@pytest.fixture
def engine(tmp_path):
    root = tmp_path / "engine"
    _write(root / "ops" / "dashboard.json", {"tierb": {"start_utc": "2019-12-31T00:00:00Z"}})
    _write(root / "data" / "simulated" / f"{BATCH}.json", [{"top_prompt": p} for p in CLINICAL])
    _write(root / "data" / "selections" / "medgemma15_priority_20261009.json",
           {"pairs": [{"batch": BATCH, "index": 3}]})
    _part(root, BATCH, _summary([_result(i) for i in (1, 2, 3)], "gemma-2-2b", "hosted"))
    pinned = _part(root, f"{BATCH}__qwen3-4b", _summary([_result(i) for i in (1, 2, 3)], "qwen3-4b"))
    _write(root / rp.RELEASE_MANIFEST, {"schema": rp.MANIFEST_SCHEMA, "parts": {
        pinned.relative_to(root).as_posix(): hashlib.sha256(pinned.read_bytes()).hexdigest()}})
    # what the hold could not show: a post-registration model, a gap-fill part, a hand-authored example
    _part(root, f"{BATCH}__gemma-4-e2b", _summary(
        [_result(1, 0.0), _result(2), _result(3, 0.25), _result(4, -0.1)], "gemma-4-e2b"))
    _part(root, f"{BATCH}__qwen3-4b", _summary([_result(4)], "qwen3-4b"), "batch_summary.part_04.json")
    _part(root, "agscen_20990101__qwen3-4b", _summary([_result(1), _result(3)], "qwen3-4b"))
    _part(root, f"{BATCH}__medgemma-1.5-4b-it", _summary([_result(3)], "medgemma-1.5-4b-it"))
    # diagnostics: a partial run, an empty part, a screened-out row
    _part(root, f"{BATCH}__llama-3.2-3b", _summary([_result(1)], "llama-3.2-3b", completed=False,
                                                    _partial="in-progress flush"))
    _part(root, f"{BATCH}__olmo-2-1b", _summary([], "olmo-2-1b"))
    _part(root, f"{BATCH}__gemma-2-2b-it", _summary(
        [_result(1, screening={"status": "screened_out", "reason": "target below threshold"})], "gemma-2-2b-it"))
    # restricted and instrument runs
    _part(root, "pabharvest_20200101T000000Z", _summary([_result(1)], "gemma-2-2b", "hosted"))
    _write(root / "trace_out" / f"{BATCH}__jlens_gemma-2-2b" / "jlens_summary.part_01.json", {"results": []})
    return root


def _seal(root: Path) -> dict:
    return {"dashboard_path": root / "ops" / "dashboard.json", "simulated_dir": root / "data" / "simulated"}


def _export(root: Path, out: Path, *extra: str) -> int:
    return cat.main(["--engine", str(root), "--out", str(out), "--dashboard", str(_seal(root)["dashboard_path"]),
                     "--simulated", str(_seal(root)["simulated_dir"]), *extra])


def _runs(out: Path) -> dict[str, dict]:
    return {r["run_dir"]: r for r in json.loads((out / "index.json").read_text(encoding="utf-8"))["runs"]}


def _rows(out: Path, run_dir: str) -> list[dict]:
    doc = json.loads((out / "rows" / f"{run_dir}.json").read_text(encoding="utf-8"))
    return [row for part in doc["parts"] for row in part["rows"]]


def test_a_post_registration_result_is_listed_with_rows_and_labels_and_no_study_membership(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    run = _runs(out)[f"{BATCH}__gemma-4-e2b"]
    assert run["visibility"] == "public" and run["evidence_class"] == "exploratory_post_registration"
    assert run["clinical_review"] == "domain_review_pending" and run["sampling"] == "observational"
    assert run["analysis_parts"] == {rp.STUDY_INTERIM: 0, rp.EXPLORATORY_OPEN: 1, rp.PUBLIC_DISPLAY: 1}
    assert "cohort post_registration_20261009" in run["parts"][0]["outside"][rp.STUDY_INTERIM]
    doc = json.loads((out / "rows" / f"{BATCH}__gemma-4-e2b.json").read_text(encoding="utf-8"))
    assert doc["parts"][0]["analysis_memberships"] == [rp.EXPLORATORY_OPEN]
    assert "first encoded target token" in doc["endpoint"]


def test_null_opposite_direction_partial_and_empty_results_are_all_discoverable(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    runs = _runs(out)
    counts = runs[f"{BATCH}__gemma-4-e2b"]["counts"]
    assert (counts["penalty_zero"], counts["penalty_positive"], counts["penalty_negative"]) == (1, 1, 1)
    penalties = sorted(r["language_penalty"] for r in _rows(out, f"{BATCH}__gemma-4-e2b"))
    assert penalties == [-0.1, 0.0, 0.25]                       # signed, as measured, nothing dropped but the seal
    assert runs[f"{BATCH}__llama-3.2-3b"]["execution_states"] == {"partial": 1}
    assert runs[f"{BATCH}__llama-3.2-3b"]["counts"]["rows_public"] == 1      # its landed row is still a row
    empty = runs[f"{BATCH}__olmo-2-1b"]
    assert empty["execution_states"] == {"empty": 1} and empty["rows_file"] is None and empty["rows_reason"]
    screened = runs[f"{BATCH}__gemma-2-2b-it"]
    assert screened["counts"]["rows_screened_out"] == 1
    assert _rows(out, f"{BATCH}__gemma-2-2b-it")[0]["screening"] == {
        "status": "screened_out", "reason": "target below threshold"}
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["totals"]["execution_state"] == {"completed": 8, "empty": 1, "partial": 1}
    assert any("not a sample" in note for note in index["notes"])


def test_a_hand_authored_example_is_labelled_pending_review_and_joins_no_analysis(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    run = _runs(out)["agscen_20990101__qwen3-4b"]
    assert run["evidence_class"] == "exploratory_hand_authored" and run["sampling"] == "other"
    assert run["clinical_review"] == "owner_read_equivalence_and_domain_review_pending"
    assert run["analysis_parts"] == {rp.STUDY_INTERIM: 0, rp.EXPLORATORY_OPEN: 0, rp.PUBLIC_DISPLAY: 1}
    doc = json.loads((out / "rows" / "agscen_20990101__qwen3-4b.json").read_text(encoding="utf-8"))
    assert doc["parts"][0]["analysis_memberships"] == [] and len(doc["parts"][0]["rows"]) == 2
    stimuli = json.loads((out / "stimuli" / "agscen_20990101.json").read_text(encoding="utf-8"))
    assert stimuli["clinical_review"] == "owner_read_equivalence_and_domain_review_pending"


def test_a_sealed_row_is_in_no_written_file_and_is_counted(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    written = [p for p in out.rglob("*") if p.is_file()]
    assert len(written) >= 8
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert SEALED not in text and PATIENT[1] not in text, path
    runs = _runs(out)
    assert runs[f"{BATCH}__gemma-4-e2b"]["counts"]["rows_withheld_sealed"] == 1
    assert runs[BATCH]["counts"] == {**runs[BATCH]["counts"], "rows_public": 2, "rows_withheld_sealed": 1}
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["restrictions"]["sealed_holdout"]["count"] == index["totals"]["rows_withheld_sealed"] == 3
    assert index["restrictions"]["sealed_holdout"]["release_condition"]
    assert "2" not in json.loads((out / "stimuli" / f"{BATCH}.json").read_text(encoding="utf-8"))["pairs"]
    rows = list(csv.DictReader(io.StringIO((out / "rows.csv").read_text(encoding="utf-8"))))
    assert rows and all(r["index"] != "2" for r in rows if r["stem"] == BATCH)


def test_an_unevaluable_seal_writes_nothing(engine, tmp_path):
    _write(engine / "ops" / "dashboard.json", {"tierb": {"start_utc": None}})
    out = tmp_path / "out"
    assert _export(engine, out) == rp.seal_config_error.__globals__["SEAL_CONFIG_EXIT"] == 2
    assert not out.exists()


def test_restricted_and_instrument_runs_are_listed_without_rows(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    runs = _runs(out)
    pab = runs["pabharvest_20200101T000000Z"]
    assert pab["visibility"] == "restricted" and pab["restriction_reasons"] == ["redistribution_limited_text"]
    assert pab["rows_file"] is None and "licence review" in pab["rows_reason"]
    assert not (out / "stimuli" / "pabharvest_20200101T000000Z.json").exists()
    lens = runs[f"{BATCH}__jlens_gemma-2-2b"]
    assert lens["instrument"] == "jlens" and lens["n_parts"] == 0 and lens["rows_file"] is None
    assert lens["model"] is None
    assert lens["other_artifacts"] == {"jlens_summary": 1} and "typed artifact" in lens["rows_reason"]


def test_uncalibrated_clinical_mass_is_never_written(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    row_parts = 0
    for row_file in (out / "rows").glob("*.json"):
        doc = json.loads(row_file.read_text(encoding="utf-8"))
        for part in doc["parts"]:
            row_parts += 1
            assert part["clinical_mass"].startswith("not published")
            assert all("clinical_mass" not in row for row in part["rows"])
    restriction = json.loads((out / "index.json").read_text(encoding="utf-8"))["restrictions"]
    assert restriction["uncalibrated_clinical_mass"]["count"] == row_parts > 0       # counted, with its unit
    assert restriction["uncalibrated_clinical_mass"]["count_unit"] == "parts"
    assert restriction["sealed_holdout"]["count_unit"] == "rows"


def test_a_double_suffix_instrument_directory_is_not_read_as_a_model(engine, tmp_path):
    """Found 2026-11-10: ``<stem>__lenspairs__jlens_<model>`` was listed as a model named by its whole suffix."""
    _write(engine / "trace_out" / f"{BATCH}__lenspairs__jlens_gemma-2-2b" / "jlens_summary.part_01.json",
           {"results": []})
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    run = _runs(out)[f"{BATCH}__lenspairs__jlens_gemma-2-2b"]
    assert run["instrument"] == "jlens" and run["model"] is None and "typed artifact" in run["rows_reason"]
    assert rp.instrument_of("lenspairs__jlens_gemma-2-2b") == "jlens" and rp.instrument_of("context") == "context"
    assert rp.instrument_of("qwen3-4b") is None and rp.instrument_of(None) is None


def test_an_outcome_selected_subset_is_labelled_on_its_rows(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    rows = _rows(out, f"{BATCH}__medgemma-1.5-4b-it")
    assert [r.get("sampling") for r in rows] == ["outcome_selected_priority_subset"]
    assert all("sampling" not in r for r in _rows(out, f"{BATCH}__gemma-4-e2b"))


def test_the_ledger_records_each_part_once_and_a_changed_part_loses_its_rows(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out, "--record") == 0
    ledger = rp.load_ledger(engine)
    assert len(ledger) == 10 and all(len(v) == 64 for v in ledger.values())
    before = (engine / rp.LEDGER_PATH).read_bytes()
    assert _export(engine, out, "--record") == 0
    assert (engine / rp.LEDGER_PATH).read_bytes() == before                  # nothing new: nothing rewritten

    target = engine / "trace_out" / f"{BATCH}__gemma-4-e2b" / "batch_summary.part_01.json"
    recorded = ledger[target.relative_to(engine).as_posix()]
    _write(target, _summary([_result(1, -0.9)], "gemma-4-e2b"))
    assert _export(engine, out, "--record") == 0
    run = _runs(out)[f"{BATCH}__gemma-4-e2b"]
    assert run["visibility"] == "restricted" and run["rows_file"] is None
    assert run["restriction_reasons"] == ["artifact_integrity:changed_since_recorded"]
    assert run["parts"][0]["artifact_integrity"] == "changed_since_recorded"
    assert not (out / "rows" / f"{BATCH}__gemma-4-e2b.json").exists()       # the stale row file is removed
    assert rp.load_ledger(engine)[target.relative_to(engine).as_posix()] == recorded


def test_a_dry_run_writes_nothing(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out, "--dry-run", "--record") == 0
    assert not out.exists() and not (engine / rp.LEDGER_PATH).exists()


def test_the_written_files_match_their_schemas(engine, tmp_path):
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    schemas = json.loads((ROOT / "scripts" / "contracts" / "results_catalogue.v1.schema.json").read_text(encoding="utf-8"))
    problems: list[str] = []

    def check(name: str, value, definition: str) -> None:
        check_schema_subset(lambda artifact, where, why: problems.append(f"{artifact} {where}: {why}"), name,
                            value, {**schemas["definitions"][definition], "definitions": schemas["definitions"]})

    check("index", json.loads((out / "index.json").read_text(encoding="utf-8")), "index")
    for path in sorted((out / "rows").glob("*.json")):
        check(path.name, json.loads(path.read_text(encoding="utf-8")), "rows")
    for path in sorted((out / "stimuli").glob("*.json")):
        check(path.name, json.loads(path.read_text(encoding="utf-8")), "stimuli")
    assert not problems, problems[:5]


# ---------------------------------------------------------------- snapshots

def test_a_snapshot_fixes_the_study_membership_and_cannot_be_rewritten(engine):
    seal = _seal(engine)
    path = snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first snapshot", seal_paths=seal,
                       created_utc="2020-01-01T00:00:00Z")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["membership"] == rp.STUDY_INTERIM and doc["supersedes"] is None
    assert sorted(doc["inputs"]["parts"]) == [
        "trace_out/pabharvest_20200101T000000Z/batch_summary.part_01.json",
        f"trace_out/{BATCH}/batch_summary.part_01.json",
        f"trace_out/{BATCH}__qwen3-4b/batch_summary.part_01.json"]
    assert doc["inputs"]["by_backend"] == {"hosted": 2, "logits": 1}        # hosted bytes are pinned too
    assert doc["families"]["registered_cohort"] == ["gemma-2-2b", "qwen3-4b"]
    assert doc["families"]["post_registration"] == []
    assert doc["denominators"]["study_rows_by_model"] == {"gemma-2-2b": 2, "qwen3-4b": 2}
    assert doc["exclusions"]["study_rows_withheld_by_seal"] == {"gemma-2-2b": 1, "qwen3-4b": 1}
    assert sum(doc["exclusions"]["parts_outside_membership"].values()) == 7
    assert doc["policy"]["version"] == "open-results/1" and "not been run" in doc["evidence_status"]
    with pytest.raises(snap.SnapshotError, match="never rewritten"):
        snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "again", seal_paths=seal)
    assert snap.verify(engine, "study-interim-20200101")["ok"] is True


def test_a_snapshot_detects_a_changed_input_and_reports_later_parts_without_failing(engine):
    snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first snapshot", seal_paths=_seal(engine))
    _part(engine, "repeatability_r9", _summary([_result(1)], "gemma-2-2b", "hosted"))     # lands afterwards
    report = snap.verify(engine, "study-interim-20200101")
    assert report["ok"] is True
    assert report["admitted_now_but_not_in_snapshot"] == ["trace_out/repeatability_r9/batch_summary.part_01.json"]
    _part(engine, BATCH, _summary([_result(1, -0.9)], "gemma-2-2b", "hosted"))            # a pinned input changes
    report = snap.verify(engine, "study-interim-20200101")
    assert report["ok"] is False and report["changed"] == [f"trace_out/{BATCH}/batch_summary.part_01.json"]
    assert snap.main(["--engine", str(engine), "verify", "--id", "study-interim-20200101"]) == 1


def test_an_edited_snapshot_file_fails_verification(engine):
    path = snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first snapshot",
                       seal_paths=_seal(engine))
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["denominators"]["study_rows_by_model"]["qwen3-4b"] = 999
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    report = snap.verify(engine, "study-interim-20200101")
    assert report["snapshot_file_unchanged"] is False and report["ok"] is False


def test_a_separately_declared_analysis_is_its_own_snapshot_with_its_own_family(engine):
    seal = _seal(engine)
    snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first snapshot", seal_paths=seal)
    snap.create(engine, "exploratory-open-20200101", rp.EXPLORATORY_OPEN,
                "adds the 2026-10-09 models and unpinned parts as a separate exploratory analysis", seal_paths=seal)
    with pytest.raises(snap.SnapshotError, match="not a recorded snapshot"):
        snap.create(engine, "study-interim-20200102", rp.STUDY_INTERIM, "x", supersedes="nope", seal_paths=seal)
    index = snap.load_index(engine)
    assert index["current"] == {rp.STUDY_INTERIM: "study-interim-20200101",
                                rp.EXPLORATORY_OPEN: "exploratory-open-20200101"}
    delta = snap.diff(engine, "study-interim-20200101", "exploratory-open-20200101")
    assert delta["models"]["added"] == ["gemma-2-2b-it", "gemma-4-e2b", "llama-3.2-3b", "medgemma-1.5-4b-it",
                                        "olmo-2-1b"]
    assert delta["parts"]["only_in_from"] == 0 and delta["parts"]["in_both_different_bytes"] == []
    assert delta["post_registration_family_size"] == {"from": 0, "to": 5}
    assert delta["study_rows_by_model"]["qwen3-4b"] == {"from": 2, "to": 3}
    open_doc = snap.load_snapshot(engine, "exploratory-open-20200101")
    assert not any("agscen" in p for p in open_doc["inputs"]["parts"])       # examples join no analysis
    # the study snapshot is untouched by the new one
    assert snap.verify(engine, "study-interim-20200101")["ok"] is True


def test_a_display_rule_cannot_be_snapshotted_and_a_change_record_is_required(engine):
    with pytest.raises(snap.SnapshotError, match="display rule"):
        snap.create(engine, "display-20200101", rp.PUBLIC_DISPLAY, "x", seal_paths=_seal(engine))
    with pytest.raises(snap.SnapshotError, match="change record"):
        snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "  ", seal_paths=_seal(engine))


# ---------------------------------------------------------------- the site contract gate

def _published_site(engine: Path, tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    assert cat.main(["--engine", str(engine), "--site", str(site), "--dashboard",
                     str(_seal(engine)["dashboard_path"]), "--simulated", str(_seal(engine)["simulated_dir"])]) == 0
    return site


def _gate(site: Path) -> list[str]:
    import validate_frontend_contract as vfc
    rep = vfc.Report()
    vfc.check_results_catalogue(rep, site)
    return rep.errors


def test_the_contract_gate_accepts_a_whole_catalogue_and_a_site_without_one(engine, tmp_path):
    assert _gate(_published_site(engine, tmp_path)) == []
    bare = tmp_path / "bare"
    (bare / "data").mkdir(parents=True)
    assert _gate(bare) == []                                  # optional: older sites have none


def test_the_contract_gate_refuses_a_missing_row_file_an_orphan_and_edited_totals(engine, tmp_path):
    site = _published_site(engine, tmp_path)
    root = site / "data" / "results_catalogue"
    (root / "rows" / f"{BATCH}__gemma-4-e2b.json").unlink()
    assert any("named by the index but not published" in e for e in _gate(site))

    site = _published_site(engine, tmp_path / "second")
    root = site / "data" / "results_catalogue"
    (root / "rows" / "left_behind.json").write_text("{}", encoding="utf-8")
    assert any("published but not named by the index" in e for e in _gate(site))
    (root / "rows" / "left_behind.json").unlink()

    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    index["totals"]["rows_withheld_sealed"] = 0                # hide the seal count
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    assert any("$.totals.rows_withheld_sealed" in e for e in _gate(site))

    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    index["totals"]["rows_withheld_sealed"] = 3
    restricted = next(r for r in index["runs"] if r["visibility"] == "restricted")
    restricted["rows_file"], restricted["stimuli_file"] = f"rows/{BATCH}.json", f"stimuli/{BATCH}.json"
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    assert any("a restricted run lists a rows file" in e for e in _gate(site))


def test_the_exporter_refuses_a_site_argument_that_is_not_a_site(engine, tmp_path):
    assert cat.main(["--engine", str(engine), "--site", str(tmp_path / "nowhere")]) == 2


def test_calibrated_clinical_mass_is_written_per_phrasing_and_passes_the_contract(engine, tmp_path):
    """Regression (2026-11-10): landed summaries carry clinical_mass as an object per phrasing; the first
    schema declared a number, so the contract gate failed on every calibrated row of the real catalogue."""
    calibrated = _summary([_result(1), _result(3)], "gemma-2-2b", "hosted")
    calibrated["source_set"] = "gemmascope-transcoder-16k"
    _part(engine, "repeatability_r9", calibrated)                 # an unclassified family: listed without rows
    _part(engine, BATCH, calibrated, "batch_summary.part_09.json")
    site = _published_site(engine, tmp_path)
    doc = json.loads((site / "data" / "results_catalogue" / "rows" / f"{BATCH}.json").read_text(encoding="utf-8"))
    part = next(p for p in doc["parts"] if p["name"] == "batch_summary.part_09.json")
    assert part["clinical_mass"] == "per row"
    assert all(row["clinical_mass"] == {"clinical": 0.42, "patient": 0.31} for row in part["rows"])
    assert _gate(site) == []


# ---------------------------------------------------------------- the seal is decided per pair (review, 2026-11-10)

def test_a_pair_sealed_through_one_runs_trace_time_prompt_is_withheld_in_every_run(engine, tmp_path):
    """Regression: three real Tier B pairs are sealed only because one run traced them with a probe extension
    that hashes holdout. Deciding row by row published the pair's prompts and its rows from every other run."""
    extended = next(f"{OPEN[2]} ext{i}" for i in range(1, 500) if tierb_split.is_holdout(f"{OPEN[2]} ext{i}"))
    assert not tierb_split.is_holdout(OPEN[2])                    # the accepted prompt itself is not holdout
    probe = _result(4)
    probe["prompts"] = {"clinical": extended, "patient": PATIENT[3]}
    _part(engine, f"{BATCH}__llama-3.2-3b", _summary([probe], "llama-3.2-3b"), "batch_summary.part_04.json")
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    runs = _runs(out)
    # pair 4 was public in the gemma-4-e2b and qwen3-4b runs before; it is now withheld in all three
    for run_dir, withheld in ((f"{BATCH}__gemma-4-e2b", 2), (f"{BATCH}__qwen3-4b", 2), (f"{BATCH}__llama-3.2-3b", 1)):
        assert runs[run_dir]["counts"]["rows_withheld_sealed"] == withheld, run_dir
        if runs[run_dir]["rows_file"]:
            assert all(row["index"] != 4 for row in _rows(out, run_dir)), run_dir
    stimuli = json.loads((out / "stimuli" / f"{BATCH}.json").read_text(encoding="utf-8"))
    assert "4" not in stimuli["pairs"] and "2" not in stimuli["pairs"]
    for path in (p for p in out.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8")
        assert extended not in text and OPEN[2] not in text and PATIENT[3] not in text, path


def test_a_registered_phrase_in_another_case_or_spacing_on_a_hand_authored_set_is_withheld(engine, tmp_path):
    """On a stem outside Tier B the row-level seal is an exact string test. The exporter also applies the
    publish gate's matcher, so it never writes what scripts/seal_check.py would then refuse."""
    variant = _result(1)
    variant["prompts"] = {"clinical": f"  {SEALED.upper()}   and a probe extension", "patient": "beta wording 9"}
    _part(engine, "agscen_20990102__qwen3-4b", _summary([variant, _result(3)], "qwen3-4b"))
    out = tmp_path / "out"
    assert _export(engine, out) == 0
    run = _runs(out)["agscen_20990102__qwen3-4b"]
    assert run["counts"]["rows_withheld_sealed"] == 1 and run["counts"]["rows_public"] == 1
    for path in (p for p in out.rglob("*") if p.is_file()):
        assert SEALED.upper() not in path.read_text(encoding="utf-8").upper(), path


@pytest.mark.parametrize("mutate", ["index_string", "index_none", "prompts_list", "result_string"])
def test_a_malformed_exported_result_refuses_the_export_and_writes_nothing(engine, tmp_path, mutate):
    bad = _result(1)
    if mutate == "index_string":
        bad["index"] = "1"
    elif mutate == "index_none":
        bad["index"] = None
    elif mutate == "prompts_list":
        bad["prompts"] = [CLINICAL[0], PATIENT[0]]
    summary = _summary(["not an object"] if mutate == "result_string" else [bad], "qwen3-4b")
    _part(engine, "agscen_20990103__qwen3-4b", summary)
    out = tmp_path / "out"
    assert _export(engine, out) == 2 and not out.exists()


def test_a_run_with_one_failed_part_and_one_intact_part_lists_the_intact_rows_and_passes_the_gate(engine, tmp_path):
    """Regression: such a run was marked restricted while it listed rows, and the contract gate then rejected
    the whole catalogue."""
    _part(engine, f"{BATCH}__gemma-4-e2b", {"graph_model": "gemma-4-e2b", "results": [_result(1)]},
          "batch_summary.part_09.json")                                        # no backend key: malformed
    site = _published_site(engine, tmp_path)
    run = _runs(site / "data" / "results_catalogue")[f"{BATCH}__gemma-4-e2b"]
    assert run["visibility"] == "public" and run["restricted_parts"] == 1 and run["rows_file"]
    assert run["restriction_reasons"] == ["artifact_integrity:malformed"]
    states = {p["name"]: p["artifact_integrity"] for p in run["parts"]}
    assert states == {"batch_summary.part_01.json": "unrecorded", "batch_summary.part_09.json": "malformed"}
    assert _gate(site) == []


# ---------------------------------------------------------------- snapshot and ledger integrity (review, 2026-11-10)

def _git(root: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *argv], check=True, capture_output=True, text=True)


def _commit_all(root: Path, message: str = "base") -> None:
    if not (root / ".git").exists():
        _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)


def test_a_snapshot_denominator_excludes_a_pair_sealed_through_another_runs_prompt(engine):
    """Regression: the snapshot decided the seal row by row while the catalogue decided it per pair, so a
    committed snapshot counted 30 rows at pairs the catalogue withholds."""
    extended = next(f"{OPEN[2]} ext{i}" for i in range(1, 500) if tierb_split.is_holdout(f"{OPEN[2]} ext{i}"))
    probe = _result(3)
    probe["prompts"] = {"clinical": extended, "patient": PATIENT[2]}
    # an unpinned part of another model seals pair 3; the study membership does not even read this part
    _part(engine, f"{BATCH}__llama-3.2-3b", _summary([probe], "llama-3.2-3b"), "batch_summary.part_03.json")
    path = snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first snapshot", seal_paths=_seal(engine))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["denominators"]["study_rows_by_model"] == {"gemma-2-2b": 1, "qwen3-4b": 1}
    assert doc["exclusions"]["study_rows_withheld_by_seal"] == {"gemma-2-2b": 2, "qwen3-4b": 2}


def test_a_snapshot_refuses_untracked_or_modified_inputs_and_a_preview_never_becomes_current(engine):
    """Regression: the dirty check ignored untracked files, and a hosted part needs no pin, so an untracked
    part entered a snapshot that said its inputs were committed."""
    _commit_all(engine)
    seal = _seal(engine)
    _part(engine, "repeatability_r9", _summary([_result(1)], "gemma-2-2b", "hosted"))        # untracked
    with pytest.raises(snap.SnapshotError, match="untracked files included"):
        snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=seal)
    assert not (engine / snap.SNAPSHOT_DIR).exists() or not list((engine / snap.SNAPSHOT_DIR).glob("*.json"))
    preview = snap.create(engine, "study-interim-preview", rp.STUDY_INTERIM, "preview", seal_paths=seal,
                          allow_dirty=True)
    assert json.loads(preview.read_text(encoding="utf-8"))["inputs_committed"] is False
    index = snap.load_index(engine)
    assert index["current"] == {} and index["snapshots"][0]["preview"] is True
    _commit_all(engine, "landed")
    snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=seal)
    assert snap.load_index(engine)["current"] == {rp.STUDY_INTERIM: "study-interim-20200101"}


def test_a_new_snapshot_names_the_current_one_of_its_own_membership(engine):
    seal = _seal(engine)
    snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=seal)
    snap.create(engine, "exploratory-open-20200101", rp.EXPLORATORY_OPEN, "separate analysis", seal_paths=seal)
    with pytest.raises(snap.SnapshotError, match="already has a current snapshot"):
        snap.create(engine, "study-interim-20200102", rp.STUDY_INTERIM, "second", seal_paths=seal)
    with pytest.raises(snap.SnapshotError, match="supersedes one of its own membership"):
        snap.create(engine, "study-interim-20200102", rp.STUDY_INTERIM, "second", seal_paths=seal,
                    supersedes="exploratory-open-20200101")
    with pytest.raises(snap.SnapshotError, match="not 'index'"):
        snap.create(engine, "index", rp.STUDY_INTERIM, "x", seal_paths=seal)
    snap.create(engine, "study-interim-20200102", rp.STUDY_INTERIM, "second", seal_paths=seal,
                supersedes="study-interim-20200101")
    assert snap.load_index(engine)["current"][rp.STUDY_INTERIM] == "study-interim-20200102"
    assert sorted(p.name for p in (engine / snap.SNAPSHOT_DIR).iterdir()) == [
        "exploratory-open-20200101.json", "index.json", "study-interim-20200101.json",
        "study-interim-20200102.json"]                                    # no temporary file is left behind


def test_verify_fails_the_current_snapshot_when_a_recorded_input_file_or_the_pin_changes(engine, capsys):
    """Regression: verify compared the parts only, so a changed tiers file or manifest printed OK."""
    seal = _seal(engine)
    tiers = engine / "data" / "urgency_tiers.draft.json"
    _write(tiers, {"tiers": ["a"]})
    snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=seal)
    assert snap.verify(engine, "study-interim-20200101")["ok"] is True
    _write(tiers, {"tiers": ["a", "b"]})
    report = snap.verify(engine, "study-interim-20200101")
    assert report["ok"] is False and report["stale"] is True
    assert report["config_changed"] == ["data/urgency_tiers.draft.json"]
    assert snap.main(["--engine", str(engine), "verify"]) == 1
    assert "no longer describes this checkout" in capsys.readouterr().out
    # a superseding snapshot records the new file; the old one then reports the difference without failing
    snap.create(engine, "study-interim-20200102", rp.STUDY_INTERIM, "tiers changed", seal_paths=seal,
                supersedes="study-interim-20200101")
    old = snap.verify(engine, "study-interim-20200101")
    assert old["ok"] is True and old["current"] is False and old["config_changed"]
    assert snap.main(["--engine", str(engine), "verify"]) == 0
    manifest = engine / rp.RELEASE_MANIFEST
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["parts"]["trace_out/x__qwen3-4b/batch_summary.part_01.json"] = "0" * 64
    _write(manifest, doc)
    assert snap.verify(engine, "study-interim-20200102")["config_changed"] == [str(rp.RELEASE_MANIFEST)]


def test_a_snapshot_file_the_index_does_not_list_fails_verify_and_blocks_create(engine, capsys):
    """An interrupted create could leave a snapshot file with no index entry that verify and list never saw."""
    seal = _seal(engine)
    path = snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=seal)
    orphan = path.with_name("study-interim-20200102.json")
    orphan.write_text(path.read_text(encoding="utf-8")[:200], encoding="utf-8")            # truncated, unindexed
    assert snap.main(["--engine", str(engine), "verify"]) == 1
    assert "the index does not list: study-interim-20200102.json" in capsys.readouterr().out
    assert snap.main(["--engine", str(engine), "list"]) == 0
    assert "NOT INDEXED: study-interim-20200102.json" in capsys.readouterr().out
    with pytest.raises(snap.SnapshotError, match="the index does not list"):
        snap.create(engine, "study-interim-20200103", rp.STUDY_INTERIM, "x", seal_paths=seal,
                    supersedes="study-interim-20200101")
    assert snap.main(["--engine", str(engine), "verify", "--id", "study-interim-20200102"]) == 2   # no traceback


def test_a_snapshot_reads_the_committed_policy_whatever_the_preview_variable_says(engine, tmp_path, monkeypatch,
                                                                                    capsys):
    """Regression: with PW_RESULTS_POLICY still exported, a snapshot recorded a candidate rule under the
    study membership's name and became current."""
    candidate = json.loads((rp.ENGINE / rp.POLICY_PATH).read_text(encoding="utf-8"))
    candidate["memberships"][rp.STUDY_INTERIM]["exclude_model_cohorts"] = []
    candidate["memberships"][rp.STUDY_INTERIM]["logits_manifest"] = None
    _write(tmp_path / "candidate.json", candidate)
    monkeypatch.setenv(rp.POLICY_ENV, str(tmp_path / "candidate.json"))
    path = snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=_seal(engine))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "gemma-4-e2b" not in doc["families"]["models"] and doc["inputs"]["n_parts"] == 3
    assert doc["policy"]["sha256"] == hashlib.sha256((rp.ENGINE / rp.POLICY_PATH).read_bytes()).hexdigest()
    assert "is set and is ignored here" in capsys.readouterr().err


def test_a_snapshot_records_whether_the_published_statistics_equal_a_recomputation(engine, tmp_path):
    """Regression: a snapshot paired today's parts with a statistics file generated earlier and said nothing
    about whether one reproduces from the other."""
    site = tmp_path / "site"
    published = {"seed": 7, "boot": 100, "per_model": {"qwen3-4b": {"penalty": {"mean": -0.0466}, "n_rows": 3}},
                 "_provenance": {"generator": "g", "engine_sha": "abc+dirty", "generated_utc": "2020-01-01T00:00:00Z"}}
    _write(site / "data" / "model_stats.json", published)
    same, moved = tmp_path / "same.json", tmp_path / "moved.json"
    _write(same, {**published, "_provenance": {"generated_utc": "later"}})
    _write(moved, {"seed": 7, "boot": 100, "per_model": {"qwen3-4b": {"penalty": {"mean": -0.0465}, "n_rows": 3}}})
    seal = _seal(engine)
    doc = json.loads(snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "first", seal_paths=seal,
                                 site=site).read_text(encoding="utf-8"))
    assert doc["outputs"]["reproduces_from_inputs"] == "not_checked"
    assert doc["outputs"]["stated_provenance"]["data/model_stats.json"]["engine_sha"] == "abc+dirty"
    assert doc["outputs"]["stated_provenance"]["data/timeline.json"] is None
    assert doc["inputs"]["site_payload"]["path"] == "data/simulated_scenarios.json"
    doc = json.loads(snap.create(engine, "study-interim-20200102", rp.STUDY_INTERIM, "checked", seal_paths=seal,
                                 site=site, supersedes="study-interim-20200101",
                                 recomputed_statistics=moved).read_text(encoding="utf-8"))
    check = doc["outputs"]["reproduces_from_inputs"]
    assert check["identical"] is False and check["differing_fields"] == ["/per_model/qwen3-4b/penalty/mean"]
    assert snap.reproduction_check(site, same)["identical"] is True
    _write(moved, {"seed": 8, "boot": 100, "per_model": {}})
    with pytest.raises(snap.SnapshotError, match="like for like"):
        snap.reproduction_check(site, moved)


def test_every_committed_snapshot_verifies_and_the_directory_holds_nothing_unindexed():
    """The committed snapshots are checked by the suite, not only when someone runs verify."""
    index = snap.load_index(rp.ENGINE)
    assert snap.unindexed_files(rp.ENGINE) == []
    for entry in index["snapshots"]:
        report = snap.verify(rp.ENGINE, entry["id"])
        assert report["ok"], (entry["id"], report["missing"][:3], report["changed"][:3], report["config_changed"])


def test_record_does_not_store_the_hash_of_a_part_that_already_fails_its_pin(engine, tmp_path, capsys):
    """Regression: --record stored the hash of a pinned part whose bytes had changed. After the part was
    restored, the manifest wanted the original and the ledger the changed bytes, for good."""
    out = tmp_path / "out"
    target = engine / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_01.json"
    rel = target.relative_to(engine).as_posix()
    original = target.read_bytes()
    _write(target, _summary([_result(1, -0.9)], "qwen3-4b"))                     # differs from the manifest
    assert _export(engine, out, "--record") == 0
    assert "1 part(s) differ from their recorded hash (not recorded" in capsys.readouterr().out
    assert rel not in rp.load_ledger(engine)
    target.write_bytes(original)                                                 # the release condition
    assert _export(engine, out, "--record") == 0
    assert "0 part(s) differ from their recorded hash" in capsys.readouterr().out
    assert rp.load_ledger(engine)[rel] == hashlib.sha256(original).hexdigest()
    part = next(p for p in _runs(out)[f"{BATCH}__qwen3-4b"]["parts"] if p["name"].endswith("part_01.json"))
    assert part["artifact_integrity"] == "recorded_match"
