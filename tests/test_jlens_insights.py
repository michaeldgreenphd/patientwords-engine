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
    # 2026-07-14 rescope: capture/hijack condition on clinical readability
    held = {"pat_final_rank": 2, "pat_formed": 10, "clin_formed": 9}
    hijack = {"pat_final_rank": None, "pat_formed": 12, "clin_formed": 9}
    capture = {"pat_final_rank": None, "pat_formed": None, "clin_formed": 9}
    unreadable = {"pat_final_rank": None, "pat_formed": None, "clin_formed": None}
    assert classify(held) == "held"
    assert classify(hijack) == "hijack"
    assert classify(capture) == "capture"
    assert classify(unreadable) == "unreadable"


def write_summary(root: Path, dataset, model, results):
    d = root / f"{dataset}__jlens_{model}"
    d.mkdir(parents=True)
    (d / "jlens_summary.part_01.json").write_text(json.dumps(
        {"graph_model": model, "results": results}), encoding="utf-8")


def result(index, clin_spec, pat_spec, status="ok", prompts=None):
    r = {"index": index, "parse_status": {"clinical": status, "patient": status},
         "depth": {"clinical": layers(clin_spec), "patient": layers(pat_spec)}}
    if prompts is not None:
        r["prompts"] = prompts
    return r


def test_exemplars_carry_prompts_and_prefer_rendered(tmp_path):
    from scripts.jlens_insights import render_map_from_scenarios
    root = tmp_path / "trace_out"
    # two hijack candidates; only #2 has a committed render -> exemplar prefers it
    write_summary(root, "pairs_R", "gemma-2-2b", [
        result(1, [(None, "x"), (1, "y"), (1, "y"), (1, "y")],
               [(None, "x"), (5, "y"), (4, "y"), (None, "z")],
               prompts={"clinical": "first clinical", "patient": "first patient"}),
        result(2, [(None, "x"), (1, "y"), (1, "y"), (1, "y")],
               [(None, "x"), (5, "y"), (4, "y"), (None, "z")],
               prompts={"clinical": "rendered clinical", "patient": "rendered patient"}),
    ])
    per_model, _ = collect(root)
    rmap = {("pairs_R", 2): "modes/simulated/pairs_R/index_02.html"}
    out = analyze(per_model, "gemma-2-2b", "gemma-2-2b-it", 3, render_map=rmap)
    hij = next(e for e in out["exemplars"] if e["class"] == "hijack")
    assert hij["index"] == 2                                    # preferred the rendered pair
    assert hij["prompts"] == {"clinical": "rendered clinical", "patient": "rendered patient"}
    assert hij["render"] == "modes/simulated/pairs_R/index_02.html"
    # scenarios -> {(batch, index): html}
    scen = tmp_path / "s.json"
    scen.write_text(json.dumps({"scenarios": [{"batch": "b", "batch_index": 5, "html": "H"}]}))
    assert render_map_from_scenarios(str(scen)) == {("b", 5): "H"}


def test_collect_and_analyze_end_to_end(tmp_path):
    root = tmp_path / "trace_out"
    write_summary(root, "setA", "gemma-2-2b", [
        result(1, [(None, "x"), (2, "y"), (1, "y")], [(None, "x"), (4, "y"), (2, "y")]),  # held
        # hijack under the persistence rule needs two consecutive readable
        # layers before the loss (2026-07-14)
        result(2, [(None, "x"), (1, "y"), (1, "y"), (1, "y")],
               [(None, "x"), (5, "y"), (4, "y"), (None, "z")]),  # hijack
        result(3, [(2, "y"), (1, "y"), (1, "y")], [(None, "z"), (None, "z"), (None, "z")]),  # capture
        result(4, [(1, "y")] * 3, [(1, "y")] * 3, status="error"),  # filtered out
        result(5, [(None, "z")] * 3, [(None, "z")] * 3),  # unreadable (both-null)
    ])
    write_summary(root, "setA", "gemma-2-2b-it", [
        result(1, [(None, "x"), (1, "y"), (1, "y")], [(None, "x"), (3, "y"), (3, "y")]),
    ])
    per_model, _holdout_excluded = collect(root)
    assert len(per_model["gemma-2-2b"]) == 4  # error row filtered
    out = analyze(per_model, "gemma-2-2b", "gemma-2-2b-it", 3)
    assert out["n_pairs"] == 4
    assert {k: v["n"] for k, v in out["taxonomy"].items()} == {
        "held": 1, "hijack": 1, "capture": 1, "unreadable": 1}
    assert out["formation"]["patient_never"] == 2   # capture + unreadable rows
    assert out["formation"]["clinical_never"] == 1  # unreadable row
    # pre-computed never-formed shares (count / n_pairs=4)
    assert out["formation"]["clinical_never_pct"] == 25.0
    assert out["formation"]["patient_never_pct"] == 50.0
    # the top-8 window column must equal the headline taxonomy
    assert out["window_sensitivity"]["8"]["hijack"] == 1
    assert out["window_sensitivity"]["8"]["unreadable"] == 1
    it = out["instruction_tuning"]
    assert it["n_paired"] == 1 and it["pairs"][0] == {"index": 1, "base": 1, "it": 1}
    assert len(out["exemplars"]) >= 2  # hijack + capture found (held needs clin_formed too)


def test_featured_exemplar_index_first_hijack_else_zero_else_none():
    from scripts.jlens_insights import featured_exemplar_index
    assert featured_exemplar_index([{"class": "capture"}, {"class": "hijack"},
                                    {"class": "hijack"}]) == 1
    assert featured_exemplar_index([{"class": "capture"}, {"class": "held"}]) == 0
    assert featured_exemplar_index([]) is None
