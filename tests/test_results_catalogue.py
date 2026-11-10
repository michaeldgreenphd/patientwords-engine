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
            "language_penalty": penalty, "target_token": 'Output " alpha"', "clinical_mass": 0.42, **extra}


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
