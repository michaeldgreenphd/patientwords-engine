"""Formation-depth analytics: trajectory metrics and the failure taxonomy."""
import json
from pathlib import Path

from scripts.jlens_insights import analyze, classify, collect, formation_layer, lock_in_layer


def layers(spec):
    """[(rank_or_None, top1), ...] -> depth records."""
    return [{"layer": i, "target_rank": r, "top1": t} for i, (r, t) in enumerate(spec)]


def test_formation_and_lock_in():
    ls = layers([(None, "a"), (None, "b"), (3, "b"), (1, "c"), (None, "c")])
    assert formation_layer(ls) == 2
    assert lock_in_layer(ls) == 3  # top1 'c' holds from layer 3 on
    assert formation_layer(layers([(None, "x")])) is None


def test_classify_taxonomy():
    held = {"pat_final_rank": 2, "pat_formed": 10}
    hijack = {"pat_final_rank": None, "pat_formed": 12}
    capture = {"pat_final_rank": None, "pat_formed": None}
    assert classify(held) == "held"
    assert classify(hijack) == "hijack"
    assert classify(capture) == "capture"


def write_summary(root: Path, dataset, model, results):
    d = root / f"{dataset}__jlens_{model}"
    d.mkdir(parents=True)
    (d / "jlens_summary.part_01.json").write_text(json.dumps(
        {"graph_model": model, "results": results}), encoding="utf-8")


def result(index, clin_spec, pat_spec, status="ok"):
    return {"index": index, "parse_status": {"clinical": status, "patient": status},
            "depth": {"clinical": layers(clin_spec), "patient": layers(pat_spec)}}


def test_collect_and_analyze_end_to_end(tmp_path):
    root = tmp_path / "trace_out"
    write_summary(root, "setA", "gemma-2-2b", [
        result(1, [(None, "x"), (2, "y"), (1, "y")], [(None, "x"), (4, "y"), (2, "y")]),  # held
        result(2, [(None, "x"), (1, "y"), (1, "y")], [(None, "x"), (5, "y"), (None, "z")]),  # hijack
        result(3, [(2, "y"), (1, "y"), (1, "y")], [(None, "z"), (None, "z"), (None, "z")]),  # capture
        result(4, [(1, "y")] * 3, [(1, "y")] * 3, status="error"),  # filtered out
    ])
    write_summary(root, "setA", "gemma-2-2b-it", [
        result(1, [(None, "x"), (1, "y"), (1, "y")], [(None, "x"), (None, "x"), (3, "y")]),
    ])
    per_model = collect(root)
    assert len(per_model["gemma-2-2b"]) == 3  # error row filtered
    out = analyze(per_model, "gemma-2-2b", "gemma-2-2b-it", 3)
    assert out["n_pairs"] == 3
    assert {k: v["n"] for k, v in out["taxonomy"].items()} == {"held": 1, "hijack": 1, "capture": 1}
    assert out["formation"]["patient_never"] == 1
    it = out["instruction_tuning"]
    assert it["n_paired"] == 1 and it["pairs"][0] == {"index": 1, "base": 1, "it": 2}
    assert len(out["exemplars"]) >= 2  # hijack + capture found (held needs clin_formed too)
