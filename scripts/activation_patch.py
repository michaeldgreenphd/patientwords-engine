"""Activation patching: WHERE the language penalty lives ($0, CPU, push-to-run CI).

The study's primary causal experiment. Run gemma-2-2b twice on a pair - the
clinical phrasing (clean) and the patient phrasing (corrupt) - then copy the
clean activation into the corrupt run at one (layer, position) site and
re-decode. If the target token's probability recovers, that site carries the
penalty. Sweeping every site yields a recovery heatmap over (layer x position):
a map of where the penalty lives, a stronger causal standard than the API
steering already done. Full method, grid, and pre-registration:
``docs/activation_patching_design.md``.

Runs by direct CPU inference in CI exactly like ``scripts/logits_eval.py``
(open weights, forward passes only, no Neuronpedia) and emits the same
``batch_summary`` schema so downstream collectors merge it unchanged - plus a
per-result ``patching`` block carrying the recovery grid.

The real hooking (``patch_and_measure``) runs on transformer_lens, a CI-only
extra installed by ``.github/workflows/activation_patching.yml`` next to CPU
torch. The sandbox dev install stays without it (the egress proxy blocks model
hosts anyway), so the import is guarded and raises ImportError locally;
``--scaffold`` still emits the documented schema shape from placeholder data
(grid shape real, numbers null) fully offline.

Position alignment (the pre-registered rule, option (a) of the design note):
the grid is the CORRUPT run's token grid; only positions inside the longest
common token suffix of the two prompts - counted from the end - are patched,
each from its aligned clean position. The rule (``ALIGN_RULE``) and every
position's ``aligned_clean_index`` are recorded in the output; cells outside
the shared suffix stay null.

Usage:
  # scaffold the schema shape offline (no model, no network):
  python scripts/activation_patch.py --pairs data/simulated/pairs_<STAMP>.json \
      --out trace_out/pairs_<STAMP>__patch --scaffold [--layers 26] [--limit 13]
  # real run (CI): drop --scaffold; chunk with --limit / --start-index, restrict
  # the grid with --layers N (0 = all) / --positions "3,4,5" ('' = shared suffix).
"""

import argparse
import json
import math
from pathlib import Path

# Short id -> Hugging Face repo. Mirrors logits_eval.HF_IDS; patching needs only
# open weights (no transcoder), so any of these can run - gemma-2-2b is the base.
# transformer_lens must support the architecture (it does for all four).
HF_IDS = {
    "gemma-2-2b": "google/gemma-2-2b",
    "gemma-3-4b-it": "google/gemma-3-4b-it",
    "qwen3-4b": "Qwen/Qwen3-4B",
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",
}

# gemma-2-2b depth; the real run reads ``model.cfg.n_layers`` instead.
DEFAULT_LAYERS = 26
# Standard patching site: the residual stream after each block. Expands to the
# transformer_lens hook name ``blocks.<layer>.hook_<hook_point>``.
DEFAULT_HOOK_POINT = "resid_post"

# Pre-registered alignment rule (design-note option (a)), recorded verbatim in
# every measured patching block so the output is self-describing.
ALIGN_RULE = (
    "shared-suffix: the grid is the corrupt run's token grid; only positions in "
    "the longest common token suffix of the clean and corrupt prompts (counted "
    "from the end) are patched, each from its aligned clean position "
    "(aligned_clean_index; null = outside the shared suffix, cells stay null)")

# The hooking library is a CI-only extra: .github/workflows/activation_patching.yml
# installs it next to CPU torch; the offline sandbox never has it.
_TL_IMPORT_ERROR = (
    "activation patching needs transformer_lens, which is not installed here. "
    "It is a CI-only extra: the activation-patching workflow "
    "(.github/workflows/activation_patching.yml) installs `pip install "
    "transformer-lens` next to CPU torch; the sandbox dev install deliberately "
    "stays without it (the egress proxy blocks model hosts). Run with --scaffold "
    "to emit the documented schema shape from placeholder data instead.")


def load_pairs(path, limit=0, start_index=1):
    """Load a pairs_<STAMP>.json list; keep `limit` pairs from `start_index` (1-based).

    The caller is expected to pass the downgrade-filtered subset (the
    safety-relevant flips) as the pairs file - this script does not classify.
    `start_index` is the chunking knob: pairs before it are skipped and result
    numbering continues from it, so ``results[i]["index"]`` stays the global
    1-based join key back into the batch file.
    """
    pairs = json.loads(Path(path).read_text(encoding="utf-8"))
    if start_index > 1:
        pairs = pairs[start_index - 1:]
    if limit:
        pairs = pairs[:limit]
    return pairs


def synthetic_positions(prompt):
    """Placeholder token positions for the corrupt (patched-into) run.

    A whitespace split standing in for the real tokenizer positions, so the
    scaffold can emit a grid of the right *shape* without loading a model. The
    real ``patch_and_measure`` replaces these with tokenizer positions plus each
    position's ``aligned_clean_index`` under the shared-suffix rule (ALIGN_RULE).
    """
    return [{"index": i, "token": tok} for i, tok in enumerate(prompt.split())]


def shared_suffix_alignment(clean_tokens, corrupt_tokens):
    """(corrupt_index, clean_index) pairs for the longest common token suffix.

    The pre-registered alignment rule (ALIGN_RULE): the two prompts differ in
    the swapped span, which need not be token-length-matched, so positions only
    align exactly where both runs share a trailing region. Counted from the
    end; an empty list means the prompts share no trailing tokens and nothing
    is patchable.
    """
    k = 0
    limit = min(len(clean_tokens), len(corrupt_tokens))
    while k < limit and clean_tokens[-1 - k] == corrupt_tokens[-1 - k]:
        k += 1
    return [(len(corrupt_tokens) - k + i, len(clean_tokens) - k + i) for i in range(k)]


def resolve_layer_ids(layers, n_layers):
    """Grid rows. None/0 = every layer (0..n_layers-1); an int caps the depth
    (first N layers, clipped to the model); an iterable is an explicit subset
    (ValueError outside 0..n_layers-1)."""
    if not layers:
        return list(range(n_layers))
    if isinstance(layers, int):
        return list(range(min(layers, n_layers)))
    ids = sorted({int(x) for x in layers})
    bad = [i for i in ids if i < 0 or i >= n_layers]
    if bad:
        raise ValueError(f"layer ids {bad} outside 0..{n_layers - 1}")
    return ids


def parse_positions(spec):
    """Corrupt-run position indices from a CLI/CI string; None = the default
    rule (every shared-suffix position). Accepts comma/space separation."""
    if spec is None:
        return None
    text = str(spec).strip()
    if not text:
        return None
    return sorted({int(x) for x in text.replace(",", " ").split()})


def _target_prob(logits, target_id):
    """P(target_id) at the final position of a [1, seq, vocab] logits tensor.

    Softmax runs in pure Python over a ``.tolist()`` copy so a real torch tensor
    and the tests' plain-nested-list fake take the same code path (this module
    never imports torch).
    """
    vec = logits[0][-1]
    if hasattr(vec, "float"):
        vec = vec.float()
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    peak = max(vec)
    exps = [math.exp(v - peak) for v in vec]
    return exps[int(target_id)] / sum(exps)


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


def build_summary(model_id, hf_id, results, layers, hook_point, measured, start_index=1):
    """Top-level ``batch_summary`` for a patching run, in the logits-path schema."""
    return {
        "mode": "2panel",
        "backend": "activation_patch",   # not "logits", not the hosted graph
        "graph_model": model_id,         # export keys models_meta off this
        "source_set": None,              # no transcoder -> features=False downstream
        "generation_params": {},
        "start_index": start_index,
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
    """Write ``batch_summary.part_01.json`` under `out_dir` (part_NN convention;
    CI restamps NN to the chunk's 1-based start offset before committing)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "batch_summary.part_01.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path


def load_model(model_name):
    """HookedTransformer for the real run (CI only; guarded transformer_lens import).

    transformer_lens resolves both official short names ('gemma-2-2b') and the
    Hugging Face repo ids HF_IDS maps to. bfloat16 on CPU matches the logits
    path; gated weights (gemma) need HF_TOKEN in the environment.
    """
    try:
        import torch
        from transformer_lens import HookedTransformer
    except ImportError as exc:
        raise ImportError(_TL_IMPORT_ERROR) from exc
    model = HookedTransformer.from_pretrained(model_name, dtype=torch.bfloat16)
    model.eval()
    return model


def target_token_id(model, target):
    """First token id of the target string under the run's tokenizer, or None
    when the target is empty/untokenizable (the row stays a placeholder)."""
    if not target:
        return None
    ids = model.to_tokens(target, prepend_bos=False)
    row = ids[0]
    if hasattr(row, "tolist"):
        row = row.tolist()
    row = list(row)
    return int(row[0]) if row else None


def patch_and_measure(model, clean_prompt, corrupt_prompt, target_id,
                      layers=None, positions=None, hook_point=DEFAULT_HOOK_POINT):
    """Real activation patch over the (layer x position) grid for one pair.

    `model` is a transformer_lens.HookedTransformer - or a model id string
    ('gemma-2-2b'-style / a Hugging Face repo id), loaded here via
    ``HookedTransformer.from_pretrained``. The transformer_lens import is
    guarded inside this function: it is a CI-only extra (_TL_IMPORT_ERROR names
    the workflow that installs it), and tests pass a fake object exposing the
    same small surface (to_tokens / to_str_tokens / run_with_cache /
    run_with_hooks / cfg.n_layers).

    Method:
      1. Forward the clean (clinical) prompt once with ``run_with_cache``,
         keeping ``blocks.<layer>.hook_<hook_point>`` at every layer;
         ``clean_prob`` = P(target_id) at the final position.
      2. Forward the corrupt (patient) prompt once for ``corrupt_prob``.
      3. For each grid cell (layer, corrupt position) inside the shared-suffix
         alignment (``shared_suffix_alignment``; `positions` restricts the
         columns, `layers` the rows), re-forward the corrupt prompt via
         ``run_with_hooks`` with the cached clean activation written in at that
         site, and record ``patched_prob``.
      4. ``recovery = (p_patched - p_corrupt) / max(p_clean - p_corrupt, 1e-9)``
         per cell. The 1e-9 floor keeps a vanishing or inverted penalty from
         dividing by zero; such pairs are screened downstream per the design
         note's denominator floor. Values outside [0, 1] are reported as-is.

    Returns a ``patching`` block in the ``build_patching_scaffold`` shape with
    real numbers and ``placeholder: False``, plus the recorded alignment rule
    (``align`` = ALIGN_RULE) and each position's ``aligned_clean_index``
    (null = outside the shared suffix, so never patched).
    """
    if isinstance(model, str):
        try:
            from transformer_lens import HookedTransformer
        except ImportError as exc:
            raise ImportError(_TL_IMPORT_ERROR) from exc
        model = HookedTransformer.from_pretrained(model)

    clean_strs = model.to_str_tokens(clean_prompt)
    corrupt_strs = model.to_str_tokens(corrupt_prompt)
    clean_tokens = model.to_tokens(clean_prompt)
    corrupt_tokens = model.to_tokens(corrupt_prompt)

    clean_logits, clean_cache = model.run_with_cache(clean_tokens)
    corrupt_logits = model.run_with_hooks(corrupt_tokens, fwd_hooks=[])
    clean_prob = _target_prob(clean_logits, target_id)
    corrupt_prob = _target_prob(corrupt_logits, target_id)
    denom = max(clean_prob - corrupt_prob, 1e-9)

    aligned = dict(shared_suffix_alignment(clean_strs, corrupt_strs))
    columns = sorted(aligned if positions is None else set(positions) & set(aligned))
    layer_ids = resolve_layer_ids(layers, model.cfg.n_layers)

    n_pos = len(corrupt_strs)
    recovery = [[None] * n_pos for _ in layer_ids]
    patched = [[None] * n_pos for _ in layer_ids]
    for row, layer in enumerate(layer_ids):
        name = f"blocks.{layer}.hook_{hook_point}"
        clean_act = clean_cache[name]
        for pos in columns:
            def write_clean(act, hook=None, _pos=pos, _src=aligned[pos], _clean=clean_act):
                act[0][_pos] = _clean[0][_src]
                return act

            logits = model.run_with_hooks(corrupt_tokens, fwd_hooks=[(name, write_clean)])
            prob = _target_prob(logits, target_id)
            patched[row][pos] = round(prob, 6)
            recovery[row][pos] = round((prob - corrupt_prob) / denom, 6)

    return {
        "hook_point": hook_point,
        "metric": "normalized_recovery",
        "placeholder": False,
        "clean_prob": round(clean_prob, 6),
        "corrupt_prob": round(corrupt_prob, 6),
        "layers": layer_ids,
        "positions": [{"index": i, "token": tok, "aligned_clean_index": aligned.get(i)}
                      for i, tok in enumerate(corrupt_strs)],
        "recovery": recovery,
        "patched_prob": patched,
        "corrected": None,   # BH-corrected significance map lands set-level, later
        "align": ALIGN_RULE,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True,
                        help="pairs_<STAMP>.json (downgrade subset) to patch")
    parser.add_argument("--model", default="gemma-2-2b",
                        help="short model id (%s) or a Hugging Face repo id" % "/".join(HF_IDS))
    parser.add_argument("--out", required=True,
                        help="output dir, e.g. trace_out/pairs_<STAMP>__patch")
    parser.add_argument("--limit", type=int, default=0,
                        help="patch only the first N pairs of the chunk (0 = all)")
    parser.add_argument("--start-index", type=int, default=1,
                        help="global 1-based index of the first pair (chunking: earlier pairs "
                             "are skipped; result numbering stays global)")
    parser.add_argument("--layers", type=int, default=0,
                        help="grid depth: patch layers 0..N-1 (0 = every layer from the model "
                             "config; the scaffold falls back to %d)" % DEFAULT_LAYERS)
    parser.add_argument("--positions", default="",
                        help="comma/space-separated corrupt-run token positions to patch "
                             "('' = every shared-suffix position)")
    parser.add_argument("--hook-point", default=DEFAULT_HOOK_POINT,
                        help="residual-stream site to patch (default: %s)" % DEFAULT_HOOK_POINT)
    parser.add_argument("--scaffold", action="store_true",
                        help="emit the schema shape from placeholder data without loading a model")
    args = parser.parse_args(argv)

    model_id = args.model
    hf_id = HF_IDS.get(model_id, model_id)
    pairs = load_pairs(args.pairs, args.limit, args.start_index)

    if args.scaffold:
        grid_layers = args.layers or DEFAULT_LAYERS
        results = [build_result(i, pair, grid_layers, args.hook_point)
                   for i, pair in enumerate(pairs, start=args.start_index)]
        measured = False
    else:
        print(f"Loading {hf_id} as a HookedTransformer (cpu, bfloat16) ...", flush=True)
        model = load_model(hf_id)
        grid_layers = args.layers or model.cfg.n_layers
        positions = parse_positions(args.positions)
        results = []
        for i, pair in enumerate(pairs, start=args.start_index):
            target_id = target_token_id(model, pair.get("target_clinical_token") or "")
            if target_id is None:
                # empty/untokenizable target: nothing measurable; keep the
                # placeholder block so the row still joins downstream.
                patching = build_patching_scaffold(
                    pair["top_prompt"], pair["bottom_prompt"], grid_layers, args.hook_point)
            else:
                patching = patch_and_measure(
                    model, pair["top_prompt"], pair["bottom_prompt"], target_id,
                    layers=args.layers or None, positions=positions,
                    hook_point=args.hook_point)
            results.append(assemble_result(i, pair, patching))
            r = results[-1]
            cells = sum(1 for grid_row in (r["patching"]["recovery"] or [])
                        for cell in grid_row if cell is not None)
            print(f"  [{i}] clin={r['probabilities']['clinical']} "
                  f"pat={r['probabilities']['patient']} cells={cells}", flush=True)
        measured = True

    summary = build_summary(model_id, hf_id, results, grid_layers, args.hook_point,
                            measured, args.start_index)
    path = write_summary(args.out, summary)
    print(f"Wrote {len(results)} results -> {path}"
          f"{' (scaffold: placeholder numbers)' if not measured else ''}")
    return 0


if __name__ == "__main__":
    main()
