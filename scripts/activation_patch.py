"""Activation patching: WHERE the language penalty lives (skeleton, $0/offline scaffold).

The study's primary causal experiment. Run gemma-2-2b twice on a pair - the
clinical phrasing (clean) and the patient phrasing (corrupt) - then copy the
clean activation into the corrupt run at one (layer, position) site and
re-decode. If the target token's probability recovers, that site carries the
penalty. Sweeping every site yields a recovery heatmap over (layer x position):
a map of where the penalty lives, a stronger causal standard than the API
steering already done. Full method, grid, and pre-registration:
``docs/activation_patching_design.md``.

Runs by direct CPU inference in CI exactly like ``scripts/logits_eval.py``
(open weights, bf16, forward passes only, no Neuronpedia) and emits the same
``batch_summary`` schema so downstream collectors merge it unchanged - plus a
per-result ``patching`` block carrying the recovery grid.

The real hooking (``patch_and_measure``) needs a residual-stream hooking
library (nnsight or transformer-lens) that is not yet a CI dependency, so it
raises ``NotImplementedError``. Until it lands, ``--scaffold`` emits the
documented schema shape from placeholder data (grid shape real, numbers null)
so the exporter, collector, and heatmap renderer can be wired against it.

Usage:
  # scaffold the schema shape offline (no model, no network):
  python scripts/activation_patch.py --pairs data/simulated/pairs_<STAMP>.json \
      --out trace_out/pairs_<STAMP>__patch --scaffold [--layers 26] [--limit 13]
  # real run (CI, once the hooking dep lands): drop --scaffold.
"""

import argparse
import json
from pathlib import Path

# Short id -> Hugging Face repo. Mirrors logits_eval.HF_IDS; patching needs only
# open weights (no transcoder), so any of these can run - gemma-2-2b is the base.
HF_IDS = {
    "gemma-2-2b": "google/gemma-2-2b",
    "gemma-3-4b-it": "google/gemma-3-4b-it",
    "qwen3-4b": "Qwen/Qwen3-4B",
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",
}

# gemma-2-2b depth; the real run overrides from ``model.config.num_hidden_layers``.
DEFAULT_LAYERS = 26
# Standard patching site: the residual stream after each block.
DEFAULT_HOOK_POINT = "resid_post"


def load_pairs(path, limit=0):
    """Load a pairs_<STAMP>.json list; optionally keep only the first `limit`.

    The caller is expected to pass the downgrade-filtered subset (the
    safety-relevant flips) as the pairs file - this script does not classify.
    """
    pairs = json.loads(Path(path).read_text(encoding="utf-8"))
    if limit:
        pairs = pairs[:limit]
    return pairs


def synthetic_positions(prompt):
    """Placeholder token positions for the corrupt (patched-into) run.

    A whitespace split standing in for the real tokenizer positions, so the
    scaffold can emit a grid of the right *shape* without loading a model. The
    real ``patch_and_measure`` replaces these with tokenizer positions and their
    aligned clean-run index (see the alignment rule in the design note).
    """
    return [{"index": i, "token": tok} for i, tok in enumerate(prompt.split())]


def build_patching_scaffold(clean_prompt, corrupt_prompt, layers, hook_point):
    """A ``patching`` block with a real grid shape but null (placeholder) numbers.

    ``recovery`` and ``patched_prob`` are row-major ``layers x positions`` grids.
    Every numeric field is None and ``placeholder`` is True: nothing is invented,
    only the structure downstream code iterates is fixed.
    """
    positions = synthetic_positions(corrupt_prompt)
    layer_ids = list(range(layers))
    empty_grid = [[None for _ in positions] for _ in layer_ids]
    return {
        "hook_point": hook_point,
        "metric": "normalized_recovery",
        "placeholder": True,
        "clean_prob": None,
        "corrupt_prob": None,
        "layers": layer_ids,
        "positions": positions,
        "recovery": empty_grid,
        "patched_prob": [[None for _ in positions] for _ in layer_ids],
        "corrected": None,
    }


def assemble_result(index, pair, patching):
    """One ``batch_summary`` result carrying a ``patching`` block.

    Same envelope as the logits path (index join key, prompts, target,
    probabilities, language_penalty) so downstream merges unchanged.
    """
    clean = patching.get("clean_prob")
    corrupt = patching.get("corrupt_prob")
    penalty = (round(corrupt - clean, 4)
               if isinstance(clean, (int, float)) and isinstance(corrupt, (int, float))
               else None)
    return {
        "index": index,
        "mode": "2panel",
        "prompts": {"clinical": pair["top_prompt"], "patient": pair["bottom_prompt"]},
        "target_token": (pair.get("target_clinical_token") or "") or None,
        "probabilities": {"clinical": clean, "patient": corrupt},
        "language_penalty": penalty,
        "patching": patching,
    }


def build_result(index, pair, layers, hook_point):
    """Scaffold result for a pair (no model): schema shape from placeholder data."""
    patching = build_patching_scaffold(
        pair["top_prompt"], pair["bottom_prompt"], layers, hook_point)
    return assemble_result(index, pair, patching)


def build_summary(model_id, hf_id, results, layers, hook_point, measured):
    """Top-level ``batch_summary`` for a patching run, in the logits-path schema."""
    return {
        "mode": "2panel",
        "backend": "activation_patch",   # not "logits", not the hosted graph
        "graph_model": model_id,         # export keys models_meta off this
        "source_set": None,              # no transcoder -> features=False downstream
        "generation_params": {},
        "start_index": 1,
        "screen_targets": None,
        # the fixed, pre-registered grid (see docs/activation_patching_design.md)
        "patching_grid": {
            "hook_point": hook_point,
            "layers": layers,
            "align": "corrupt-run token positions",
            "metric": "normalized_recovery",
        },
        "inference": {
            "method": "activation_patch",
            "hf_id": hf_id,
            "dtype": "bfloat16",
            "measured": measured,   # False for a --scaffold run
        },
        "results": results,
    }


def write_summary(out_dir, summary):
    """Write ``batch_summary.part_01.json`` under `out_dir` (part_NN convention)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "batch_summary.part_01.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path


def load_model(hf_id):
    """Load open weights on CPU in bf16, exactly like logits_eval (CI only).

    Imported lazily so the offline scaffold path never touches torch.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(hf_id)
    model = AutoModelForCausalLM.from_pretrained(
        hf_id, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    model.eval()
    return model, tokenizer


def patch_and_measure(model, tokenizer, clean_prompt, corrupt_prompt,
                      target_id, layers, hook_point=DEFAULT_HOOK_POINT):
    """Real activation patch over the (layer x position) grid for one pair.

    Intended behavior once the CI hooking dependency lands:
      1. Forward the clean (clinical) prompt, caching the `hook_point`
         activation at every (layer, position); record ``clean_prob`` =
         P(target_id) at the final position.
      2. Forward the corrupt (patient) prompt once for ``corrupt_prob``.
      3. For each (layer, position) in the grid, re-forward the corrupt prompt
         with the cached clean activation written in at that site (aligning the
         clean-run position per the design note), and record ``patched_prob``.
      4. ``recovery = (patched - corrupt) / (clean - corrupt)`` per cell.
    Returns a ``patching`` block in the ``build_patching_scaffold`` shape with
    real numbers and ``placeholder: False``.

    Raises NotImplementedError until a residual-stream hooking library
    (nnsight or transformer-lens) is added as a CI dependency; run with
    ``--scaffold`` to emit the schema shape from placeholder data instead.
    """
    raise NotImplementedError(
        "activation patching needs a residual-stream hooking library "
        "(nnsight or transformer-lens) that is not yet a CI dependency; "
        "see docs/activation_patching_design.md. Run with --scaffold to emit "
        "the documented schema shape from placeholder data.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True,
                        help="pairs_<STAMP>.json (downgrade subset) to patch")
    parser.add_argument("--model", default="gemma-2-2b",
                        help="short model id (%s) or a Hugging Face repo id" % "/".join(HF_IDS))
    parser.add_argument("--out", required=True,
                        help="output dir, e.g. trace_out/pairs_<STAMP>__patch")
    parser.add_argument("--limit", type=int, default=0,
                        help="patch only the first N pairs (0 = all)")
    parser.add_argument("--layers", type=int, default=DEFAULT_LAYERS,
                        help="grid depth; the real run overrides from model config")
    parser.add_argument("--hook-point", default=DEFAULT_HOOK_POINT,
                        help="residual-stream site to patch (default: %s)" % DEFAULT_HOOK_POINT)
    parser.add_argument("--scaffold", action="store_true",
                        help="emit the schema shape from placeholder data without loading a model")
    args = parser.parse_args(argv)

    model_id = args.model
    hf_id = HF_IDS.get(model_id, model_id)
    pairs = load_pairs(args.pairs, args.limit)

    if args.scaffold:
        results = [build_result(i, pair, args.layers, args.hook_point)
                   for i, pair in enumerate(pairs, start=1)]
        measured = False
    else:
        # Real path (CI, once the hooking dep lands). patch_and_measure currently
        # raises NotImplementedError - deliberate until the dependency is added.
        print(f"Loading {hf_id} (cpu, bfloat16) ...", flush=True)
        model, tokenizer = load_model(hf_id)
        results = []
        for i, pair in enumerate(pairs, start=1):
            target = pair.get("target_clinical_token") or ""
            target_ids = tokenizer(target, add_special_tokens=False).input_ids
            target_id = target_ids[0] if target_ids else None
            patching = patch_and_measure(
                model, tokenizer, pair["top_prompt"], pair["bottom_prompt"],
                target_id, args.layers, args.hook_point)
            results.append(assemble_result(i, pair, patching))
        measured = True

    summary = build_summary(model_id, hf_id, results, args.layers, args.hook_point, measured)
    path = write_summary(args.out, summary)
    print(f"Wrote {len(results)} results -> {path}"
          f"{' (scaffold: placeholder numbers)' if not measured else ''}")
    return 0


if __name__ == "__main__":
    main()
