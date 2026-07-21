"""Site depth dataset exporter (scripts/export_jlens_depth.py) - offline."""

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "export_jlens_depth.py"
_SPEC = importlib.util.spec_from_file_location("export_jlens_depth", _MODULE_PATH)
exporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exporter)


def test_contrast_labels_pick_the_differing_spans():
    c = "Since I've been dealing with insomnia for a week straight, I finally scheduled a"
    p = "Since I've been counting sheep all night for a week straight, I finally scheduled a"
    lc, lp = exporter.contrast_labels(c, p)
    assert lc == "dealing with insomnia"
    assert lp == "counting sheep all night"


def test_contrast_labels_fall_back_on_identical_prompts():
    lc, lp = exporter.contrast_labels("same words", "same words")
    assert lc and lp  # never empty; the page needs something to print


def test_rank_map_keeps_only_readable_layers():
    profile = [{"layer": 3, "target_rank": None}, {"layer": 4, "target_rank": 2},
               {"layer": 5, "target_rank": 1}]
    assert exporter.rank_map(profile) == {"4": 2, "5": 1}


def _write_patch_part(tmp_path, stem, index, clean, corrupt, matrix):
    d = tmp_path / "trace_out" / f"{stem}__patch"
    d.mkdir(parents=True)
    part = {"results": [{"index": index, "patching": {
        "clean_prob": clean, "corrupt_prob": corrupt, "patched_prob": matrix}}]}
    (d / f"batch_summary.part_{index:02d}.json").write_text(json.dumps(part))


def test_patch_join_refuses_degenerate_grids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_patch_part(tmp_path, "s", 2, clean=0.1, corrupt=0.4, matrix=[[0.2]])
    with pytest.raises(ValueError, match="degenerate"):
        exporter.patch_join("s", 2)
    _write_patch_part(tmp_path, "t", 1, clean=0.4, corrupt=0.1, matrix=[[None], [None]])
    with pytest.raises(ValueError, match="all-null"):
        exporter.patch_join("t", 1)


def test_patch_join_per_layer_max_ignores_nulls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_patch_part(tmp_path, "u", 1, clean=0.4, corrupt=0.1,
                      matrix=[[None, 0.15, 0.2], [None, None, None], [0.35, None, 0.3]])
    per_layer, clean, corrupt, _ = exporter.patch_join("u", 1)
    assert per_layer == [0.2, None, 0.35]
    assert (clean, corrupt) == (0.4, 0.1)


def test_main_exit_3_on_degenerate_exemplar(tmp_path, monkeypatch):
    # end-to-end refusal path: a bad exemplar never writes site data
    monkeypatch.chdir(tmp_path)
    lens_dir = tmp_path / "trace_out" / "s__jlens_gemma-2-2b"
    lens_dir.mkdir(parents=True)
    result = {"index": 1, "patient_depth_class": "retained", "target_token": " x",
              "prompts": {"clinical": "a", "patient": "b"},
              "depth": {"clinical": [], "patient": []}}
    (lens_dir / "jlens_summary.part_01.json").write_text(json.dumps({"results": [result]}))
    _write_patch_part(tmp_path, "s", 1, clean=0.1, corrupt=0.4, matrix=[[0.2]])
    (tmp_path / "urgency_shift.json").write_text(json.dumps({"rows": []}))
    rc = exporter.main(["--block", "s=set s", "--exemplar-stem", "s",
                        "--exemplar-index", "1", "--out", "out.json", "--site", ""])
    assert rc == 3
    assert not (tmp_path / "out.json").exists()


def test_pick_examples_rule_order_caps_and_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lens_dir = tmp_path / "trace_out" / "s__jlens_gemma-2-2b"
    lens_dir.mkdir(parents=True)

    def result(idx, cls, clin_last, pat_layers):
        return {"index": idx, "patient_depth_class": cls, "target_token": " tgt",
                "prompts": {"clinical": "was clinical wording", "patient": "was everyday words"},
                "depth": {"clinical": [{"layer": 25, "target_rank": clin_last, "top1": " x"}],
                          "patient": [{"layer": lay, "target_rank": 2, "top1": " won"}
                                      for lay in pat_layers]}}
    results = [
        result(1, "suppressed", 2, [19, 20]),
        result(2, "suppressed", 1, [18]),      # stronger hold -> first
        result(3, "absent", 1, []),
        result(4, "absent", None, []),          # no clinical hold -> excluded
        result(5, "retained", 1, [25]),         # wrong class -> excluded
        result(6, "absent", 3, []),
    ]
    (lens_dir / "jlens_summary.part_01.json").write_text(json.dumps({"results": results}))
    ex = exporter.pick_examples([("s", "set s · 6 pairs")], max_suppressed=1, max_absent=2)
    assert [(e["index"], e["class"]) for e in ex] == [
        (2, "suppressed"),                       # cap 1, strongest hold
        (3, "absent"), (6, "absent")]            # rank 1 then rank 3; index 4 excluded
    assert ex[0]["set"] == "set s"
    assert ex[0]["winner"] == "won"
    assert ex[0]["clin_last_rank"] == 1
    assert "pat_ranks" in ex[0] and "prompts" in ex[0]


def test_translation_split_joins_class_and_recovery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lens_dir = tmp_path / "trace_out" / "s__jlens_gemma-2-2b"
    lens_dir.mkdir(parents=True)
    results = [
        {"index": 1, "patient_depth_class": "retained", "target_token": " a",
         "prompts": {"clinical": "c", "patient": "p"}, "depth": {"clinical": [], "patient": []}},
        {"index": 2, "patient_depth_class": "absent", "target_token": " b",
         "prompts": {"clinical": "c", "patient": "p"}, "depth": {"clinical": [], "patient": []}},
    ]
    (lens_dir / "jlens_summary.part_01.json").write_text(json.dumps({"results": results}))
    rows = [
        {"batch": "s", "model": "gemma-2-2b", "index": 1, "urgency_recovery": 0.4},
        {"batch": "s", "model": "gemma-2-2b", "index": 1, "urgency_recovery": None},  # re-trace dupe
        {"batch": "s", "model": "gemma-2-2b", "index": 2, "urgency_recovery": 0.1},
        {"batch": "s", "model": "other-model", "index": 2, "urgency_recovery": 0.9},  # wrong model
        {"batch": "t", "model": "gemma-2-2b", "index": 2, "urgency_recovery": 0.9},   # wrong set
    ]
    (tmp_path / "urgency_shift.json").write_text(json.dumps({"rows": rows}))
    split = exporter.translation_split(["s"])
    assert split["by_class"] == {"retained": {"n": 1, "mean_recovery": 0.4},
                                 "absent": {"n": 1, "mean_recovery": 0.1}}
    assert len(split["pairs"]) == 2  # duplicate row with None recovery never wins


def test_census_groups_merge_batches_keep_reviewed_separate():
    # audit M9: pairs_* blocks merge into one leading All-Batches group; other
    # blocks stay their own groups; entries carry their set label for hovers
    blocks = [
        {"id": "pairs_a", "label": "batch of A", "pairs": [
            {"index": 1, "class": "retained", "target": "x"}]},
        {"id": "reviewed", "label": "Reviewed set", "pairs": [
            {"index": 2, "class": "absent", "target": "y"}]},
        {"id": "pairs_b", "label": "batch of B", "pairs": [
            {"index": 3, "class": "suppressed", "target": "z"}]},
    ]
    groups = exporter.census_groups(blocks)
    assert [g["label"] for g in groups] == [
        "Simulated Scenarios (All Batches)", "Reviewed set"]
    assert [(p["index"], p["set"]) for p in groups[0]["pairs"]] == [
        (1, "batch of A"), (3, "batch of B")]
    assert groups[1]["pairs"][0]["set"] == "Reviewed set"
    assert exporter.census_groups([]) == []


def test_exemplar_annotations_layer_picks_and_recovery_class():
    # audit M8: first-legible (any rank), first-rank-1, best patch layer
    # (argmax non-null over non-final layers, first on ties), 0.95 recovery
    clin = {"3": 5, "4": 1, "5": 1}
    patched = [None, 0.2, 0.8, 0.8, None, 0.9]   # layer 5 is final: excluded
    ann = exporter.exemplar_annotations(clin, patched, clean_prob=0.8, layers=6)
    assert ann["first_legible"] == 3 and ann["first_rank1"] == 4
    assert ann["best_patch_layer"] == 2            # tie with 3 -> first wins
    assert ann["patch_recovery_full"] is True      # 0.8 >= 0.8*0.95
    assert ann["recovery_threshold"] == 0.95
    none = exporter.exemplar_annotations({}, [None, None], None, layers=2)
    assert none["first_legible"] is None and none["first_rank1"] is None
    assert none["best_patch_layer"] == 0 and none["patch_recovery_full"] is None
