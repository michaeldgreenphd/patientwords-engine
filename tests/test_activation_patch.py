"""Tests for scripts/activation_patch.py - offline activation patching.

Everything here stays offline: the --scaffold path and every builder are pure
(no torch, no network), and the real measurement (patch_and_measure) is
unit-tested against a tiny fake of the transformer_lens HookedTransformer
surface with deterministic activations and logits - the recovery arithmetic,
the shared-suffix position alignment, and the output schema are exercised
without the library. transformer_lens itself is a CI-only extra that is NOT
installed in the sandbox, so the guarded import is asserted to raise a helpful
ImportError naming the workflow that installs it.
"""
import importlib.util
import json
import math
import types
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "activation_patch.py"
_SPEC = importlib.util.spec_from_file_location("activation_patch", _SCRIPT)
activation_patch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(activation_patch)

_TL_MISSING = importlib.util.find_spec("transformer_lens") is None

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


def test_start_index_chunks_and_keeps_global_numbering(tmp_path):
    # chunking: --start-index skips earlier pairs and result indices stay the
    # global 1-based join key (results[i]["index"]) back into the batch file
    _, summary = _run_scaffold(tmp_path, extra=["--start-index", "2"])
    assert summary["start_index"] == 2
    assert [r["index"] for r in summary["results"]] == [2]
    assert summary["results"][0]["target_token"] == " gadget"


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


# --- the real measurement, against a fake transformer_lens surface -------------


class FakeHookedModel:
    """Deterministic stand-in for the small HookedTransformer surface
    patch_and_measure uses (to_tokens / to_str_tokens / run_with_cache /
    run_with_hooks / cfg.n_layers).

    Tokenization is a whitespace split behind a <bos> sentinel. Activations are
    ("clean"|"corrupt", layer, position) triples, so the test can see exactly
    which clean vector a hook wrote where (recorded in ``writes``).
    Final-position logits over a 2-token vocabulary come from a per-cell table
    (``patched_logits``), so the expected probability is an exact function of
    the patched cell; target_id 0 indexes the varying logit.
    """

    def __init__(self, n_layers=2, clean_logit=2.0, corrupt_logit=-1.0, patched_logits=None):
        self.cfg = types.SimpleNamespace(n_layers=n_layers)
        self.clean_logit = clean_logit
        self.corrupt_logit = corrupt_logit
        self.patched_logits = patched_logits or {}   # (layer, corrupt_pos) -> logit
        self.writes = []                             # (layer, corrupt_pos, value written)

    def to_str_tokens(self, prompt):
        return ["<bos>"] + prompt.split()

    def to_tokens(self, prompt, prepend_bos=True):
        toks = self.to_str_tokens(prompt) if prepend_bos else prompt.split()
        return [toks]   # [1, seq] "tensor"

    @staticmethod
    def _logits(logit):
        return [[[logit, 0.0]]]   # [1, final position, vocab=2]

    def run_with_cache(self, tokens):
        cache = {}
        for layer in range(self.cfg.n_layers):
            cache[f"blocks.{layer}.hook_resid_post"] = [
                [("clean", layer, pos) for pos in range(len(tokens[0]))]]
        return self._logits(self.clean_logit), cache

    def run_with_hooks(self, tokens, fwd_hooks=()):
        if not fwd_hooks:
            return self._logits(self.corrupt_logit)
        (name, fn), = fwd_hooks
        layer = int(name.split(".")[1])
        assert name == f"blocks.{layer}.hook_resid_post"
        act = [[("corrupt", layer, pos) for pos in range(len(tokens[0]))]]
        fn(act, hook=None)
        changed = [pos for pos, v in enumerate(act[0]) if v != ("corrupt", layer, pos)]
        assert len(changed) == 1, "a patch hook must write exactly one position"
        pos = changed[0]
        self.writes.append((layer, pos, act[0][pos]))
        return self._logits(self.patched_logits.get((layer, pos), self.corrupt_logit))


def prob(logit):
    """The probability _target_prob assigns token 0 of a [logit, 0.0] vocab."""
    return math.exp(logit) / (math.exp(logit) + 1.0)


def test_patch_and_measure_recovery_arithmetic_and_schema():
    fake = FakeHookedModel(n_layers=2, clean_logit=2.0, corrupt_logit=-1.0, patched_logits={
        (0, 2): 2.0,    # full recovery -> ~1.0
        (0, 3): -1.0,   # no movement -> 0.0
        (1, 2): 0.5,    # partial recovery
        (1, 3): 3.5,    # overshoot -> > 1, reported as-is
    })
    block = activation_patch.patch_and_measure(
        fake, "swap tail probe", "swop tail probe", target_id=0)
    p_clean, p_corrupt = prob(2.0), prob(-1.0)
    denom = p_clean - p_corrupt
    assert block["placeholder"] is False
    assert block["clean_prob"] == pytest.approx(p_clean, abs=2e-6)
    assert block["corrupt_prob"] == pytest.approx(p_corrupt, abs=2e-6)
    # str tokens: <bos> swop tail probe; shared suffix = (tail, probe) = pos 2, 3
    assert block["layers"] == [0, 1]
    assert [p["aligned_clean_index"] for p in block["positions"]] == [None, None, 2, 3]
    rec = block["recovery"]
    assert rec[0][0] is None and rec[0][1] is None      # outside the shared suffix
    assert rec[0][2] == pytest.approx(1.0, abs=1e-5)
    assert rec[0][3] == pytest.approx(0.0, abs=1e-5)
    assert rec[1][2] == pytest.approx((prob(0.5) - p_corrupt) / denom, abs=1e-5)
    assert rec[1][3] > 1.0
    assert block["patched_prob"][1][2] == pytest.approx(prob(0.5), abs=2e-6)
    # every scaffold key survives (same schema, real numbers), plus the rule
    scaffold = activation_patch.build_patching_scaffold(
        "a b", "a b", 2, activation_patch.DEFAULT_HOOK_POINT)
    assert set(scaffold) <= set(block)
    assert "shared-suffix" in block["align"]


def test_alignment_unequal_lengths_patches_shared_suffix_from_the_end():
    # clean: <bos> probe now (3 tokens); corrupt: <bos> one two probe now (5):
    # the shared suffix is (probe, now), counted from the end, so corrupt
    # positions 3, 4 align to clean positions 1, 2 - nothing else is patched.
    fake = FakeHookedModel(n_layers=1)
    block = activation_patch.patch_and_measure(fake, "probe now", "one two probe now", target_id=0)
    assert [p["index"] for p in block["positions"]] == [0, 1, 2, 3, 4]
    assert [p["aligned_clean_index"] for p in block["positions"]] == [None, None, None, 1, 2]
    # the hook wrote the CLEAN vector from the aligned index
    assert (0, 3, ("clean", 0, 1)) in fake.writes
    assert (0, 4, ("clean", 0, 2)) in fake.writes
    assert len(fake.writes) == 2
    # unpatched columns stay null across the row
    assert block["recovery"][0][:3] == [None, None, None]


def test_positions_subset_restricts_columns():
    fake = FakeHookedModel(n_layers=2)
    block = activation_patch.patch_and_measure(
        fake, "probe now", "one two probe now", target_id=0, positions=[1, 4])
    # 1 is outside the shared suffix -> not patchable, stays null; only 4 runs
    assert {(layer, pos) for layer, pos, _ in fake.writes} == {(0, 4), (1, 4)}
    assert block["recovery"][0][1] is None
    assert block["recovery"][0][3] is None
    assert block["recovery"][0][4] is not None


def test_layer_restriction_and_resolver():
    fake = FakeHookedModel(n_layers=4)
    block = activation_patch.patch_and_measure(fake, "a probe", "b probe", target_id=0, layers=2)
    assert block["layers"] == [0, 1]
    assert len(block["recovery"]) == 2
    fake2 = FakeHookedModel(n_layers=4)
    block = activation_patch.patch_and_measure(fake2, "a probe", "b probe", target_id=0, layers=[1, 3])
    assert block["layers"] == [1, 3]
    assert {layer for layer, _, _ in fake2.writes} == {1, 3}
    # the pure resolver: None/0 = all, int caps at the model depth, subsets validate
    assert activation_patch.resolve_layer_ids(None, 3) == [0, 1, 2]
    assert activation_patch.resolve_layer_ids(0, 3) == [0, 1, 2]
    assert activation_patch.resolve_layer_ids(5, 3) == [0, 1, 2]
    with pytest.raises(ValueError):
        activation_patch.resolve_layer_ids([7], 3)


def test_denominator_floor_keeps_recovery_finite():
    # clean == corrupt: the penalty vanished; max(denom, 1e-9) keeps the
    # normalized metric finite instead of raising ZeroDivisionError
    fake = FakeHookedModel(n_layers=1, clean_logit=0.0, corrupt_logit=0.0,
                           patched_logits={(0, 1): 1.0})
    block = activation_patch.patch_and_measure(fake, "same probe", "same probe", target_id=0)
    moved = block["recovery"][0][1]
    assert moved is not None and math.isfinite(moved) and moved > 0
    assert block["recovery"][0][0] == 0.0   # patch that changed nothing -> exactly 0
    assert block["recovery"][0][2] == 0.0


def test_shared_suffix_alignment_pure_function():
    align = activation_patch.shared_suffix_alignment
    assert align(list("abc"), list("abc")) == [(0, 0), (1, 1), (2, 2)]   # identical
    assert align(["x", "s", "t"], ["y", "z", "s", "t"]) == [(2, 1), (3, 2)]
    assert align(["a"], ["b"]) == []                                     # nothing shared
    assert align([], ["a"]) == []


def test_parse_positions():
    pp = activation_patch.parse_positions
    assert pp("") is None            # '' = the shared-suffix default rule
    assert pp(None) is None
    assert pp("3,5 7,3") == [3, 5, 7]


@pytest.mark.skipif(not _TL_MISSING, reason="transformer_lens installed; the guard cannot fire")
def test_patch_and_measure_import_error_names_the_ci_extra():
    # transformer_lens is deliberately NOT a sandbox dependency; passing a model
    # id string reaches the guarded import, which must fail with a message that
    # names the CI workflow installing the extra and the offline fallback.
    with pytest.raises(ImportError) as excinfo:
        activation_patch.patch_and_measure(
            "gemma-2-2b", clean_prompt="clean", corrupt_prompt="corrupt", target_id=1)
    msg = str(excinfo.value)
    assert "transformer_lens" in msg
    assert "transformer-lens" in msg
    assert "activation_patching.yml" in msg
    assert "--scaffold" in msg


@pytest.mark.skipif(not _TL_MISSING, reason="transformer_lens installed; the guard cannot fire")
def test_load_model_raises_the_same_guarded_import_error():
    with pytest.raises(ImportError) as excinfo:
        activation_patch.load_model("gemma-2-2b")
    assert "transformer-lens" in str(excinfo.value)
