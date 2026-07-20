"""Per-position transport exporter (scripts/export_jlens_transport.py) - offline.

Pins the pure grid/transport/census functions against fake raw responses in the
CONFIRMED hosted schema (tokens[i].results = [{type, top_tokens:[[strings] per
layer]}], layer numbers from meta.layers_by_type), the rule-based exemplar
choice, and the empty-input refusal (a sparse checkout must never overwrite the
published transport payload with an empty one).
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_jlens_transport", _ROOT / "scripts" / "export_jlens_transport.py")
ext = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ext)


def _resp(per_position_top_tokens, positions_tokens):
    """A raw lens response in the confirmed schema.

    per_position_top_tokens: one entry per prompt position; each is the
    per-layer list of top-token-string lists (top_tokens). positions_tokens:
    (position, token_str) per position.
    """
    n_layers = len(per_position_top_tokens[0]) if per_position_top_tokens else 0
    tokens = []
    for (pos, tok), top_tokens in zip(positions_tokens, per_position_top_tokens):
        tokens.append({"kind": "token", "position": pos, "token": tok,
                       "results": [{"type": "JACOBIAN_LENS", "top_tokens": top_tokens}]})
    return {"meta": {"layers_by_type": {"JACOBIAN_LENS": list(range(n_layers))}},
            "tokens": tokens, "done": {}}


def test_pos_readout_final_layer_top3_per_position():
    from scripts.export_jlens_transport import pos_readout
    # two positions, two layers each; the FINAL layer's tokens drive the marginalia
    resp = _resp(
        [[["junk", "j2"], ["cat", "dog", "fish", "bird"]],   # pos0 final -> cat/dog/fish
         [["k1"], ["red", "blue", "green"]]],                # pos1 final -> red/blue/green
        [(0, "<bos>"), (1, "word")],
    )
    pr = pos_readout(resp)
    assert pr[0] == ["cat", "dog", "fish"]   # top-3, final layer only
    assert pr[1] == ["red", "blue", "green"]
    assert pos_readout({}) == {}             # graceful on empty


def test_position_layer_grid_ranks_and_first_layer():
    # 3 layers; target " tgt" enters at pos1 (layer1 rank1, layer2 rank2) and
    # at the final pos (layer2 rank1). pos0 never reads it out.
    resp = _resp(
        [
            [[" a", " b"], [" a", " b"], [" a", " b"]],          # pos0: never
            [[" a", " b"], [" tgt", " a"], [" a", " tgt"]],      # pos1: L1 r1, L2 r2
            [[" a", " b"], [" a", " b"], [" tgt", " a"]],        # pos2 (final): L2 r1
        ],
        [(0, "x"), (1, " need"), (2, " my")],
    )
    grid = ext.position_layer_grid(resp, "tgt", topn=8)
    assert grid["layers"] == [0, 1, 2]
    assert grid["answer_position"] == 2
    assert grid["grid"][0] == [None, None, None]
    assert grid["grid"][1] == [None, 1, 2]
    assert grid["grid"][2] == [None, None, 1]
    assert grid["first_layer"] == [None, 1, 2]
    assert [t["token"] for t in grid["tokens"]] == ["x", " need", " my"]


def test_side_transport_gap_true_when_midsentence_only():
    # target readable at a non-final position (pos1) but NOT at the final (pos2)
    resp = _resp(
        [
            [[" a"], [" a"]],
            [[" tgt"], [" a"]],   # pos1 readable
            [[" a"], [" a"]],     # pos2 (final) never
        ],
        [(0, "x"), (1, " y"), (2, " z")],
    )
    t = ext.side_transport(resp, "tgt")
    assert t["final_readable"] is False
    assert t["n_mid_readable"] == 1
    assert t["transport_gap"] is True


def test_side_transport_gap_false_when_reaches_answer():
    resp = _resp(
        [
            [[" a"], [" a"]],
            [[" tgt"], [" a"]],   # pos1 readable
            [[" a"], [" tgt"]],   # pos2 (final) readable at L1
        ],
        [(0, "x"), (1, " y"), (2, " z")],
    )
    t = ext.side_transport(resp, "tgt")
    assert t["final_readable"] is True
    assert t["transport_gap"] is False


def test_side_transport_never_readable():
    resp = _resp([[[" a"]], [[" a"]]], [(0, "x"), (1, " y")])
    t = ext.side_transport(resp, "tgt")
    assert t == {"final_readable": False, "n_mid_readable": 0, "transport_gap": False,
                 "windows_first_layer": {"1": None, "2": None, "4": None, "8": None}}


def test_summarize_side_counts():
    records = [
        {"final_readable": True, "transport_gap": False, "n_mid_readable": 3},
        {"final_readable": False, "transport_gap": True, "n_mid_readable": 2},
        {"final_readable": False, "transport_gap": False, "n_mid_readable": 0},
    ]
    out = ext.summarize_side(records)
    assert out == {"n": 3, "reaches_answer": 1, "transport_gap": 1,
                   "never_readable": 1, "mid_readable_any": 2}


def _pair(idx, clin, pat, batch="b"):
    return {"batch": batch, "index": idx, "target": "t", "clinical": clin, "patient": pat}


def test_pick_exemplar_prefers_transport_gap():
    gap = {"final_readable": False, "transport_gap": True, "n_mid_readable": 1}
    plain = {"final_readable": True, "transport_gap": False, "n_mid_readable": 0}
    per_pair = [_pair(1, plain, plain), _pair(2, plain, gap)]
    assert ext.pick_exemplar_index(per_pair) == ("b", 2)


def test_pick_exemplar_absent_contrast_when_no_gap():
    clin_reads = {"final_readable": True, "transport_gap": False, "n_mid_readable": 1}
    pat_absent = {"final_readable": False, "transport_gap": False, "n_mid_readable": 0}
    plain = {"final_readable": True, "transport_gap": False, "n_mid_readable": 0}
    per_pair = [_pair(1, plain, plain), _pair(2, clin_reads, pat_absent)]
    assert ext.pick_exemplar_index(per_pair) == ("b", 2)


def test_pick_exemplar_falls_back_to_most_midsentence():
    a = {"final_readable": True, "transport_gap": False, "n_mid_readable": 1}
    b = {"final_readable": True, "transport_gap": False, "n_mid_readable": 4}
    per_pair = [_pair(1, a, a), _pair(2, b, b)]
    assert ext.pick_exemplar_index(per_pair) == ("b", 2)


def test_rank_exemplars_orders_dedupes_and_limits():
    gap = {"final_readable": False, "transport_gap": True, "n_mid_readable": 1}
    absent = {"final_readable": False, "transport_gap": False, "n_mid_readable": 0}
    reads = {"final_readable": True, "transport_gap": False, "n_mid_readable": 2}
    def e(idx, target, clin, pat):
        return {"batch": "b", "index": idx, "target": target, "clinical": clin, "patient": pat}
    per_pair = [
        e(1, "alpha", reads, reads),    # both read -> weakest
        e(2, "beta", reads, absent),    # absence contrast -> strong
        e(3, "gamma", reads, gap),      # transport gap -> strongest
        e(4, "beta", reads, absent),    # duplicate target beta -> dropped
        e(5, "delta", absent, absent),  # no clinical signal -> excluded
    ]
    ranked = ext.rank_exemplars(per_pair, limit=5)
    assert ranked == [("b", 3), ("b", 2), ("b", 1)]   # gap, absence, both; dedup + signal filter
    assert ext.rank_exemplars(per_pair, limit=1) == [("b", 3)]


def _resp_with_probs(final_top_tokens, final_top_probs):
    return {
        "meta": {"layers_by_type": {"JACOBIAN_LENS": list(range(len(final_top_tokens)))}},
        "tokens": [
            {"kind": "token", "position": 0, "token": "<bos>", "results": []},
            {"kind": "token", "position": 1, "token": " x", "results": [
                {"type": "JACOBIAN_LENS", "top_tokens": final_top_tokens,
                 "top_probs": final_top_probs}]},
        ],
    }


def test_answer_prediction_final_layer_token_prob_and_target():
    resp = _resp_with_probs([[" a", " b"], [" tgt", " a"]], [[0.5, 0.3], [0.71, 0.1]])
    ans = ext.answer_prediction(resp, "tgt", "gemma-2-2b")
    assert ans["token"] == "tgt" and ans["prob"] == 0.71 and ans["on_target"] is True
    assert ans["trace_url"].startswith("https://www.neuronpedia.org/gemma-2-2b/jlens?prompt=")


def test_answer_prediction_off_target():
    resp = _resp_with_probs([[" a"], [" other", " tgt"]], [[0.9], [0.6, 0.2]])
    ans = ext.answer_prediction(resp, "tgt", "gemma-2-2b")
    assert ans["token"] == "other" and ans["prob"] == 0.6 and ans["on_target"] is False


def test_answer_prediction_none_without_top_tokens():
    assert ext.answer_prediction({"tokens": []}, "tgt", "gemma-2-2b") is None


def test_lens_trace_url_encodes_prompt():
    u = ext.lens_trace_url("gemma-2-2b", "I have angina, so I need a")
    assert u.startswith("https://www.neuronpedia.org/gemma-2-2b/jlens?prompt=")
    assert "%20" in u and " " not in u          # spaces/commas percent-encoded


def test_collect_pairs_groups_sides_and_respects_seal(monkeypatch):
    # two pairs, both sides each; seal drops index 1 entirely.
    monkeypatch.setattr(ext, "_sealed", lambda batch, index: index == 1)
    scans = []
    for idx in (1, 2):
        for side in ("clinical", "patient"):
            scans.append({"batch": "b", "index": idx, "side": side, "model": "m",
                          "target_token": " tgt",
                          "final_readable": True, "n_non_final_readable_positions": 0,
                          "transport_gap": False,
                          "windows_first_layer": {"1": 1, "2": 1, "4": 1, "8": 1}})
    per_pair = ext.collect_pairs({"scans": scans}, "m")
    assert [e["index"] for e in per_pair] == [2]          # index 1 sealed out
    assert per_pair[0]["clinical"] and per_pair[0]["patient"]
    assert per_pair[0]["target"] == "tgt"


def test_collect_pairs_filters_by_model(monkeypatch):
    monkeypatch.setattr(ext, "_sealed", lambda batch, index: False)
    scans = [{"batch": "b", "index": 1, "side": "clinical", "model": "other",
              "target_token": " t", "final_readable": True,
              "n_non_final_readable_positions": 0, "transport_gap": False,
              "windows_first_layer": {}}]
    assert ext.collect_pairs({"scans": scans}, "m") == []


def test_load_render_map_from_scenarios(tmp_path):
    p = tmp_path / "sc.json"
    p.write_text(json.dumps({"scenarios": [
        {"batch": "b1", "batch_index": 7, "html": "modes/simulated/b1/index_07.html"},
        {"batch": "b1", "batch_index": 9},                       # no render
        {"batch": "b2", "batch_index": 3, "html": "modes/simulated/b2/index_03.html"},
    ]}), encoding="utf-8")
    assert ext.load_render_map(str(p)) == {
        ("b1", 7): "modes/simulated/b1/index_07.html",
        ("b2", 3): "modes/simulated/b2/index_03.html"}
    assert ext.load_render_map(str(tmp_path / "missing.json")) == {}


def test_build_payload_census_batch_and_render_restriction(monkeypatch):
    def side(final, mid):
        return {"final_readable": final, "n_mid_readable": mid, "transport_gap": False}
    per_pair = [
        {"batch": "rep", "index": 1, "target": "a", "clinical": side(True, 1), "patient": side(False, 0)},
        {"batch": "rep", "index": 2, "target": "b", "clinical": side(True, 0), "patient": side(True, 0)},
        {"batch": "trace", "index": 1, "target": "c", "clinical": side(True, 2), "patient": side(False, 0)},
    ]
    monkeypatch.setattr(ext.jps, "scan", lambda root: {"scans": [], "windows": ["1"]})
    monkeypatch.setattr(ext, "collect_pairs", lambda scan, model: per_pair)
    monkeypatch.setattr(ext, "load_summary_meta", lambda tr, b, m: ("credit", 8))
    monkeypatch.setattr(ext, "build_exemplar",
                        lambda tr, b, i, m, tn, tg: {"batch": b, "index": i, "target": tg, "sides": {}})
    payload = ext.build_payload("trace_out", "gemma-2-2b",
                                render_map={("trace", 1): "modes/simulated/trace/index_01.html"},
                                census_batch="rep")
    assert payload["n_pairs"] == 2 and payload["census_batch"] == "rep"     # census: rep only
    assert [e["target"] for e in payload["exemplars"]] == ["c"]             # only the rendered pair
    assert payload["exemplars"][0]["render"] == "modes/simulated/trace/index_01.html"
    assert "exemplar" not in payload                                        # dropped: exemplars[] is canonical
    assert [(e["batch"], e["index"]) for e in payload["per_pair"]] == [("rep", 1), ("rep", 2)]  # census cohort only


def _side(final, mid):
    return {"final_readable": final, "n_mid_readable": mid, "transport_gap": False}


def test_build_payload_pins_override_ranking_and_skip_missing_raw(monkeypatch):
    per_pair = [
        {"batch": "rep", "index": 1, "target": "a", "clinical": _side(True, 1), "patient": _side(False, 0)},
        {"batch": "trace", "index": 5, "target": "c", "clinical": _side(True, 2), "patient": _side(False, 0)},
        {"batch": "trace", "index": 9, "target": "d", "clinical": _side(True, 3), "patient": _side(True, 0)},
    ]
    monkeypatch.setattr(ext.jps, "scan", lambda root: {"scans": [], "windows": ["1"]})
    monkeypatch.setattr(ext, "collect_pairs", lambda scan, model: per_pair)
    monkeypatch.setattr(ext, "load_summary_meta", lambda tr, b, m: ("credit", 8))
    # pair 5 has no committed raw (build_exemplar returns None) -> skipped
    monkeypatch.setattr(ext, "build_exemplar",
                        lambda tr, b, i, m, tn, tg: None if i == 5 else {"batch": b, "index": i, "target": tg, "sides": {}})
    # pins select these exact pairs, in order, regardless of render_map / score
    payload = ext.build_payload("trace_out", "gemma-2-2b", census_batch="rep",
                                exemplar_pins=[("trace", 9), ("trace", 5), ("rep", 1)])
    assert [(e["batch"], e["index"]) for e in payload["exemplars"]] == [("trace", 9), ("rep", 1)]


def test_build_payload_refuses_when_census_batch_uncovered(monkeypatch):
    per_pair = [{"batch": "trace", "index": 1, "target": "c",
                 "clinical": _side(True, 2), "patient": _side(False, 0)}]
    monkeypatch.setattr(ext.jps, "scan", lambda root: {"scans": [], "windows": ["1"]})
    monkeypatch.setattr(ext, "collect_pairs", lambda scan, model: per_pair)
    # census batch has no committed coverage -> refuse rather than widen to every batch
    assert ext.build_payload("trace_out", "gemma-2-2b", census_batch="missing") is None


def test_build_exemplar_side_is_slim(monkeypatch):
    resp = _resp([[[" a"], [" a"]], [[" tgt"], [" a"]]], [(0, "<bos>"), (1, " x")])
    monkeypatch.setattr(ext, "load_raw", lambda tr, b, m, i, side: resp)
    ex = ext.build_exemplar("tr", "b", 1, "gemma-2-2b", 8, "tgt")
    assert set(ex) == {"batch", "index", "target", "layers", "sides"}       # no per-exemplar transport
    for side in ("clinical", "patient"):
        s = ex["sides"][side]
        assert set(s) == {"tokens", "grid", "answer_position", "answer", "readout", "pos_readout"}
        assert isinstance(s["grid"], list) and s["answer_position"] == 1
        assert isinstance(s["readout"], list)


def test_readout_layer_idxs_final_first_and_bounded():
    idxs = ext._readout_layer_idxs(26)
    assert idxs and idxs[0] == 25                      # final layer first
    assert idxs == sorted(idxs, reverse=True)
    assert all(0 <= i <= 25 for i in idxs) and len(idxs) <= len(ext._READOUT_FRACS)
    assert ext._readout_layer_idxs(0) == []            # degenerate axis


def test_answer_readout_open_vocab_ladder():
    # 6 layers at the final position: generic "doctor" until the top layer flips
    # to "cardio" - the paper-style trajectory the readout table shows.
    final_layers = [[" doctor"], [" doctor"], [" doctor"],
                    [" doctor"], [" doctor"], [" cardio", " doctor"]]
    resp = _resp([[[" a"]] * 6, final_layers], [(0, "<bos>"), (1, " a")])
    ro = ext.answer_readout(resp, topk=2)
    assert ro and ro[0]["final"] is True and ro[0]["layer"] == 5    # final row first
    assert ro[0]["tokens"][0] == "cardio"                          # decoded, target-agnostic
    assert all(set(r) == {"layer", "final", "tokens"} for r in ro)
    assert [r["layer"] for r in ro] == sorted([r["layer"] for r in ro], reverse=True)


def test_build_payload_refuses_empty(monkeypatch):
    monkeypatch.setattr(ext.jps, "scan", lambda root: {"scans": [], "windows": ["1"]})
    assert ext.build_payload("trace_out", "gemma-2-2b") is None


def test_main_refuses_without_overwriting(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ext.jps, "scan", lambda root: {"scans": [], "windows": ["1"]})
    out = tmp_path / "jlens_transport.json"
    out.write_text('{"n_pairs": 7}', encoding="utf-8")
    rc = ext.main(["--trace-root", str(tmp_path / "missing"), "--model", "gemma-2-2b",
                   "--out", str(out), "--site", ""])
    assert rc == 3
    assert "refused" in capsys.readouterr().out
    assert out.read_text() == '{"n_pairs": 7}'      # untouched
