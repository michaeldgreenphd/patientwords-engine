"""A logit node kept for the read and the render changes no metric (review finding N1, 2026-10-07).

Since 2026-10-07 ``_trace`` keeps the node of the token the read measures even when it ranks below the top-K
display cut, so a target measured at rank 6-10 appears in the rendered graph. That node and its links would move
clinical_mass, error_share, top_path, the steering feature choice and the predictive spread - exactly on the pairs
where the wording pushed the target below the cut. Every metric is computed on ``metric_view``, the top-K pruned
graph as before. These tests run each mode with and without the keep and require identical metrics, and require the
node to be kept where the read measured it. Tokens are abstract stand-ins.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import TEST_KEYWORD_CONFIG, build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval

TARGET = " xab"
LOW = [(f" q{i}z", round(0.3 - i * 0.04, 3)) for i in range(6)] + [(TARGET, 0.04)]  # the target at rank 7
TOP = [(TARGET, 0.5), (" q1z", 0.2)]


def weighted_graph(logits: list[tuple[str, float]]) -> dict[str, Any]:
    """The fixture graph with hosted logits, each fed by a tagged feature with its own weight, so a kept extra node
    moves the feature masses."""
    g = make_graph()
    g["nodes"] = [n for n in g["nodes"] if n["feature_type"] != "logit"]
    g["links"] = [link for link in g["links"] if link["target"] != "L_999_3"]
    for i, (tok, p) in enumerate(logits):
        nid = f"L_{i}"
        g["nodes"].append({"node_id": nid, "feature": 2000 + i, "layer": "26", "ctx_idx": 3, "feature_type": "logit",
                           "jsNodeId": f"{nid}-3", "clerp": f'Output "{tok}" (p={p})'})
        g["links"].append({"source": "3_00042_1" if i % 2 else "7_00007_2", "target": nid, "weight": 1.0 + 5 * i})
        g["links"].append({"source": "err_5_2", "target": nid, "weight": 0.5 * (i + 1)})
    return g


def run(tmp_path: Path, monkeypatch, mode: str, pair: dict[str, Any], keep: bool, **kwargs: Any) -> dict[str, Any]:
    config = tmp_path / "keyword_config.json"
    config.write_text(json.dumps(TEST_KEYWORD_CONFIG), encoding="utf-8")
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(config))
    monkeypatch.setattr(batch_eval, "generate_graph", lambda prompt, slug=None, backend="hosted", **params:
                        # reference prompts ("ref ...", a translation "tx ...") get TOP; anything naming
                        # "low", including the translation "tx low ...", gets LOW, with the target below the cut
                        weighted_graph(TOP if prompt.startswith(("ref", "tx")) and "low" not in prompt else LOW))
    monkeypatch.setattr(batch_eval, "translate_to_clinical",
                        lambda text, use_llm=True, model=None: {"text": "tx " + text, "method": "stub"})
    monkeypatch.setattr(batch_eval, "steer_ablate", lambda prompt, features, **kw: {"features": features})
    if not keep:  # main's behaviour: prune to the top K only
        trace = batch_eval._trace
        monkeypatch.setattr(batch_eval, "_trace", lambda *a, intended=None, measured=None: trace(*a))
    out = tmp_path / ("keep" if keep else "plain") / mode
    pairs = tmp_path / f"{mode}_{keep}.json"
    pairs.write_text(json.dumps([pair]), encoding="utf-8")
    result = batch_eval.run_batch(str(pairs), out_dir=str(out), mode=mode, dpi=40, fetcher=build_fetcher(),
                                  **kwargs)[0]
    result["_out"] = out
    return result


def logit_clerps(out: Path, role: str) -> list[str]:
    tagged = json.loads((out / f"pair_01_{role}.tagged.json").read_text(encoding="utf-8"))
    return [n["clerp"] for n in tagged["nodes"] if n["feature_type"] == "logit"]


METRICS = ("clinical_mass", "error_share", "top_path", "predictive_spread", "steering", "steering_boost",
           "steering_placebo", "circuit_diff", "multiples", "register_shift_deltas")
KEPT = f'Output "{TARGET}" (p=0.04)'


@pytest.mark.parametrize("mode,pair,kwargs,role", [
    ("2panel", {"top_prompt": "ref one", "bottom_prompt": "pat one", "target_clinical_token": TARGET},
     {"steer_validate": 2, "steer_boost": 2, "steer_placebo": 2}, "patient"),
    ("translation", {"patient_prompt": "pat one", "target_clinical_token": TARGET}, {}, "patient"),
    ("dialect", {"baseline_prompt": "ref one", "target_clinical_token": TARGET,
                 "variants": [{"dialect": "d1", "prompt": "var one"}]}, {}, "variant_01"),
    ("4quadrant", {"quadrants": {"A": "ref a", "B": "var b", "C": "var c", "D": "var d"},
                   "target_clinical_token": TARGET}, {}, "quad_b"),
    # the reference side itself measures the target below the cut: its kept node changes no metric either
    ("2panel", {"top_prompt": "low one", "bottom_prompt": "pat one", "target_clinical_token": TARGET},
     {"steer_validate": 2, "steer_boost": 2, "steer_placebo": 2}, "clinical"),
    ("dialect", {"baseline_prompt": "low one", "target_clinical_token": TARGET,
                 "variants": [{"dialect": "d1", "prompt": "var one"}]}, {}, "baseline"),
    # translation's reference is the translated side ("tx low one"): its kept node changes no metric
    ("translation", {"patient_prompt": "low one", "target_clinical_token": TARGET}, {}, "translated"),
    ("4quadrant", {"quadrants": {"A": "low a", "B": "var b", "C": "var c", "D": "var d"},
                   "target_clinical_token": TARGET}, {}, "quad_a"),
])
def test_a_kept_node_changes_no_metric(tmp_path, monkeypatch, mode, pair, kwargs, role):
    kept = run(tmp_path, monkeypatch, mode, pair, keep=True, **kwargs)
    plain = run(tmp_path, monkeypatch, mode, pair, keep=False, **kwargs)
    # the node is kept where the read measured it below the cut...
    assert KEPT in logit_clerps(kept["_out"], role) and KEPT not in logit_clerps(plain["_out"], role)
    # ...and no metric moves
    for key in METRICS:
        assert kept.get(key) == plain.get(key), key
    if mode == "2panel" and role == "patient":
        assert kept["probabilities"]["patient"] == 0.04 and kept["clinical_mass"]["patient"] is not None
        assert kept["steering"]["ablated_features"]  # the steering choice was made, and made identically
