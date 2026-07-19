"""Per-position transport exporter (scripts/export_jlens_transport.py) - offline.

Pins the pure grid/transport/census functions against fake raw responses in the
CONFIRMED hosted schema (tokens[i].results = [{type, top_tokens:[[strings] per
layer]}], layer numbers from meta.layers_by_type), the rule-based exemplar
choice, and the empty-input refusal (a sparse checkout must never overwrite the
published transport payload with an empty one).
"""

import importlib.util
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
