"""pilot/analysis/trace_pairs.py turns a finished version-2 pilot run into a circuit-trace pairs file. These tests
build a small fake run directory and check selection, ordering, targets, provenance, the refusals, and that its
surface key matches the harness's."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None, f"{rel} is missing"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tp = _load("pilot_trace_pairs_test", "pilot/analysis/trace_pairs.py")


def _row(rid, control="none", template="My knee hurts, so I am going to call my ___ and ask my", word="doctor",
         clinical="orthopedic surgeon", patient="bone doctor"):
    return {"id": rid, "call_id": "A__x__y", "arm": "A", "cell": "x__y", "line_index": int(rid[-2:]),
            "clinical_term": clinical, "patient_term": patient, "template": template, "next_word": word,
            "control": control, "prompt_sha256": "p" * 64}


def _run(tmp_path: Path, rows: list[dict], verdicts: dict[str, str], version=2, finalized=True) -> Path:
    run = tmp_path / "pilot_test_run"
    (run / "generated").mkdir(parents=True)
    design = {"specialties": ["x"], "swap_types": [{"name": "y", "definition": "d"}], "probe_endings": ["my", "the"]}
    if version is not None:
        design["harness_version"] = version
    (run / "design.json").write_text(json.dumps(design), encoding="utf-8")
    (run / "manifest.json").write_text(json.dumps({"finalized_utc": "2026-10-02T00:00:00Z" if finalized else None}),
                                       encoding="utf-8")
    (run / "generated" / "all_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    checked = [{"source": "generated", "row_id": rid, "verdict": v, "relation": "same", "sentence_natural": "both",
                "patient_realism": "real"} for rid, v in verdicts.items()]
    checked.append({"source": "seed", "row_id": None, "verdict": "yes"})
    (run / "checked.jsonl").write_text("".join(json.dumps(c) + "\n" for c in checked), encoding="utf-8")
    return run


def test_selects_checker_yes_rows_in_run_order_with_spaced_targets(tmp_path):
    rows = [_row("r01"), _row("r02"), _row("r03", control="negative"), _row("r04", word="pharmacist")]
    run = _run(tmp_path, rows, {"r01": "yes", "r02": "no", "r04": "yes"})
    pairs, meta = tp.build(run)
    assert [p["pilot"]["row_id"] for p in pairs] == ["r01", "r04"]
    assert pairs[0]["top_prompt"] == "My knee hurts, so I am going to call my orthopedic surgeon and ask my"
    assert pairs[0]["bottom_prompt"] == "My knee hurts, so I am going to call my bone doctor and ask my"
    assert [p["target_clinical_token"] for p in pairs] == [" doctor", " pharmacist"]
    assert all(p["pilot"]["probe_point"] for p in pairs)
    assert meta["counts"]["not_selected"] == {"checker equivalent 'no'": 1, "negative control (not requested)": 1}
    with_controls, _ = tp.build(run, include_controls=True)
    assert [p["pilot"]["row_id"] for p in with_controls] == ["r01", "r03", "r04"]


def test_probe_point_flag_is_false_when_the_template_ends_elsewhere(tmp_path):
    run = _run(tmp_path, [_row("r01", template="My knee hurts after ___ so I went")], {"r01": "yes"})
    pairs, meta = tp.build(run)
    assert pairs[0]["pilot"]["probe_point"] is False and meta["counts"]["at_probe_point"] == 0


@pytest.mark.parametrize("version,finalized,match", [(None, True, "harness_version"), (1, True, "harness_version"),
                                                     (2, False, "not finalized")])
def test_refuses_runs_that_are_not_finished_version_2(tmp_path, version, finalized, match):
    run = _run(tmp_path, [_row("r01")], {"r01": "yes"}, version=version, finalized=finalized)
    with pytest.raises(tp.TraceInputError, match=match):
        tp.build(run)


def test_refuses_rather_than_drops_untraceable_or_unjudged_rows(tmp_path):
    with pytest.raises(tp.TraceInputError, match="no checker verdict"):
        tp.build(_run(tmp_path / "a", [_row("r01"), _row("r02")], {"r01": "yes"}))
    with pytest.raises(tp.TraceInputError, match="exactly one"):
        tp.build(_run(tmp_path / "b", [_row("r01", template="___ and ___")], {"r01": "yes"}))
    with pytest.raises(tp.TraceInputError, match="not one word"):
        tp.build(_run(tmp_path / "c", [_row("r01", word="family doctor")], {"r01": "yes"}))
    with pytest.raises(tp.TraceInputError, match="nothing to trace"):
        tp.build(_run(tmp_path / "d", [_row("r01")], {"r01": "no"}))


def test_main_writes_the_pairs_and_a_sidecar_with_the_output_hash(tmp_path):
    run = _run(tmp_path, [_row("r01")], {"r01": "yes"})
    assert tp.main(["--run-dir", str(run)]) == 0
    out = run / "trace" / "trace_pairs.json"
    meta = json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["output"]["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert json.loads(out.read_text(encoding="utf-8"))[0]["target_clinical_token"] == " doctor"
    assert tp.main(["--run-dir", str(tmp_path / "missing")]) == 2


def test_surface_key_matches_the_harness():
    common = _load("pilot_common_trace_test", "pilot/scripts/common.py")
    for s in ["Blood-pressure Pills!", "  ACE inhibitor ", "Lactaid pill", "mitral valve", "naïve", "x"]:
        assert tp.surface_key(s) == common.surface_key(s)


def test_review_sample_selects_the_sampled_rows_in_review_order_whatever_the_checker_said(tmp_path):
    rows = [_row("r01"), _row("r02"), _row("r03", control="negative"), _row("r04")]
    run = _run(tmp_path, rows, {"r01": "yes", "r02": "no", "r04": "unclear"})
    (run / "review_map.json").write_text(json.dumps({"map": {"r001": "r04", "r002": "r02"}}), encoding="utf-8")
    pairs, meta = tp.build(run, review_sample=True)
    assert [(p["pilot"]["review_id"], p["pilot"]["row_id"]) for p in pairs] == [("r001", "r04"), ("r002", "r02")]
    assert [p["pilot"]["checker"]["verdict"] for p in pairs] == ["unclear", "no"]
    assert meta["selection"].startswith("exactly the blind review sample")
    with pytest.raises(tp.TraceInputError, match="select different rows"):
        tp.build(run, include_controls=True, review_sample=True)
    (run / "review_map.json").write_text(json.dumps({"map": {"r001": "r99"}}), encoding="utf-8")
    with pytest.raises(tp.TraceInputError, match="absent from all_rows"):
        tp.build(run, review_sample=True)
