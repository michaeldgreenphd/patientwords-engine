"""Tests for scripts/activation_patch.py - the activation-patching skeleton.

Everything here stays offline: the --scaffold path and every builder are pure
(no torch, no network), and patch_and_measure raises before it would touch a
model. The real hooking is not tested here (it is a CI-side dependency); what is
tested is that the CLI parses, the scaffold writes the documented schema shape
from a tiny synthetic input, and the unimplemented measurement stub raises.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "activation_patch.py"
_SPEC = importlib.util.spec_from_file_location("activation_patch", _SCRIPT)
activation_patch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(activation_patch)

# Two synthetic pairs - abstract placeholders, no medical vocabulary.
PAIRS = [
    {"top_prompt": "clean phrasing reached for an",
     "bottom_prompt": "corrupt phrasing here reached for an",
     "target_clinical_token": " widget"},
    {"top_prompt": "second clean run",
     "bottom_prompt": "second corrupt run",
     "target_clinical_token": " gadget"},
]


def _write_pairs(tmp_path, pairs=PAIRS):
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(pairs), encoding="utf-8")
    return p


def _run_scaffold(tmp_path, layers=3, extra=None):
    pairs_path = _write_pairs(tmp_path)
    out_dir = tmp_path / "trace_out" / "pairs__patch"
    argv = ["--pairs", str(pairs_path), "--out", str(out_dir),
            "--scaffold", "--layers", str(layers)]
    if extra:
        argv += extra
    rc = activation_patch.main(argv)
    summary = json.loads((out_dir / "batch_summary.part_01.json").read_text(encoding="utf-8"))
    return rc, summary


def test_cli_parses_args_and_writes_part_file(tmp_path):
    rc, summary = _run_scaffold(tmp_path)
    assert rc == 0
    # part_NN checkpoint convention, so chunks never clobber
    assert (tmp_path / "trace_out" / "pairs__patch" / "batch_summary.part_01.json").exists()
    assert len(summary["results"]) == len(PAIRS)


def test_limit_truncates_and_hook_point_flows_through(tmp_path):
    _, summary = _run_scaffold(tmp_path, extra=["--limit", "1", "--hook-point", "resid_mid"])
    assert len(summary["results"]) == 1
    assert summary["patching_grid"]["hook_point"] == "resid_mid"
    assert summary["results"][0]["patching"]["hook_point"] == "resid_mid"


def test_summary_carries_documented_batch_summary_keys(tmp_path):
    _, summary = _run_scaffold(tmp_path)
    # logits-path envelope so downstream collectors merge unchanged
    assert summary["mode"] == "2panel"
    assert summary["backend"] == "activation_patch"
    assert summary["graph_model"] == "gemma-2-2b"
    assert summary["source_set"] is None          # no transcoder -> features=False
    assert summary["start_index"] == 1
    assert summary["inference"]["measured"] is False   # scaffold, not a real run
    assert summary["inference"]["method"] == "activation_patch"
    # the fixed pre-registered grid descriptor
    grid = summary["patching_grid"]
    assert grid["hook_point"] == activation_patch.DEFAULT_HOOK_POINT
    assert grid["layers"] == 3
    assert grid["metric"] == "normalized_recovery"


def test_result_patching_block_has_grid_shaped_placeholder(tmp_path):
    _, summary = _run_scaffold(tmp_path, layers=4)
    r = summary["results"][0]
    # result envelope keys shared with the logits path (index is the join key)
    for key in ("index", "mode", "prompts", "target_token", "probabilities",
                "language_penalty", "patching"):
        assert key in r
    assert r["index"] == 1
    assert r["target_token"] == " widget"
    assert r["probabilities"] == {"clinical": None, "patient": None}
    assert r["language_penalty"] is None

    patching = r["patching"]
    for key in ("hook_point", "metric", "placeholder", "clean_prob", "corrupt_prob",
                "layers", "positions", "recovery", "patched_prob", "corrected"):
        assert key in patching
    assert patching["placeholder"] is True
    assert patching["metric"] == "normalized_recovery"
    # grid axes: 4 layers x (whitespace-token) positions of the corrupt prompt
    n_pos = len(PAIRS[0]["bottom_prompt"].split())
    assert patching["layers"] == [0, 1, 2, 3]
    assert len(patching["positions"]) == n_pos
    assert patching["positions"][0] == {"index": 0, "token": "corrupt"}
    # recovery / patched_prob are row-major layers x positions grids of nulls
    assert len(patching["recovery"]) == 4
    assert all(len(row) == n_pos for row in patching["recovery"])
    assert all(cell is None for row in patching["recovery"] for cell in row)
    assert len(patching["patched_prob"]) == 4
    assert all(len(row) == n_pos for row in patching["patched_prob"])


def test_language_penalty_computes_when_both_probs_present():
    # assemble_result derives the penalty from a measured patching block
    pair = {"top_prompt": "a", "bottom_prompt": "b", "target_clinical_token": " x"}
    patching = {"clean_prob": 0.8, "corrupt_prob": 0.5}
    r = activation_patch.assemble_result(3, pair, patching)
    assert r["index"] == 3
    assert r["probabilities"] == {"clinical": 0.8, "patient": 0.5}
    assert r["language_penalty"] == -0.3


def test_patch_and_measure_raises_not_implemented():
    with pytest.raises(NotImplementedError) as excinfo:
        activation_patch.patch_and_measure(
            model=None, tokenizer=None,
            clean_prompt="clean", corrupt_prompt="corrupt",
            target_id=1, layers=3)
    msg = str(excinfo.value)
    assert "hooking" in msg
    assert "--scaffold" in msg
