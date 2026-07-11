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
    rc = exporter.main(["--units-batch", "s", "--exemplar-stem", "s",
                        "--exemplar-index", "1", "--out", "out.json", "--site", ""])
    assert rc == 3
    assert not (tmp_path / "out.json").exists()
