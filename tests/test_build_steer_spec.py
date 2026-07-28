import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_steer_spec", Path(__file__).resolve().parents[1] / "scripts" / "build_steer_spec.py")
bss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bss)


def _result(index, target, clin_top, pat_top, patient_prompt):
    return {
        "index": index,
        "target_token": f'Output "{target}"',
        "prompts": {"clinical": "c", "patient": patient_prompt},
        "predictive_spread": {
            "clinical": [[f'Output "{clin_top}"', 0.5]],
            "patient": [[f'Output "{pat_top}"', 0.4]],
        },
    }


def _write_batch(root, stem, results):
    d = root / stem
    d.mkdir(parents=True)
    (d / "batch_summary.part_01.json").write_text(json.dumps({"results": results}), encoding="utf-8")


def test_collect_selects_strict_flips_dedupes_and_joins_class(tmp_path):
    _write_batch(tmp_path, "pairs_20260701T000000Z", [
        _result(1, " alpha", " alpha", " beta", "p one"),    # eligible flip
        _result(2, " alpha", " alpha", " alpha", "p two"),   # patient hits target - out
        _result(3, " alpha", " gamma", " beta", "p three"),  # clinical misses target - out
        _result(4, " alpha", " alpha", " beta", "p one"),    # duplicate prompt - out
    ])
    lens_dir = tmp_path / "pairs_20260701T000000Z__jlens_gemma-2-2b"
    lens_dir.mkdir()
    (lens_dir / "jlens_summary.part_01.json").write_text(
        json.dumps({"results": [{"index": 1, "patient_depth_class": "suppressed"}]}), encoding="utf-8")
    items = bss.collect_candidates(tmp_path)
    assert [(i["index"], i["class"], i["target"], i["winner"]) for i in items] == \
        [(1, "suppressed", " alpha", " beta")]


def test_population_def_b_stamps_are_excluded(tmp_path):
    _write_batch(tmp_path, "pairs_20260713T031252Z", [_result(1, " a", " a", " b", "x")])
    assert bss.collect_candidates(tmp_path) == []


def test_stratified_sample_takes_all_suppressed_first_and_is_seed_stable(tmp_path):
    items = ([{"dataset": "d", "index": i, "class": "suppressed"} for i in range(3)]
             + [{"dataset": "d", "index": 100 + i, "class": "retained"} for i in range(20)]
             + [{"dataset": "d", "index": 200 + i, "class": "absent"} for i in range(20)])
    picked = bss.stratified_sample(items, 10, seed=7)
    assert len(picked) == 10
    assert sum(1 for i in picked if i["class"] == "suppressed") == 3
    again = bss.stratified_sample(items, 10, seed=7)
    assert picked == again
