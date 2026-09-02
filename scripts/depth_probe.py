"""Depth probe: at what layer does the care-urgency decision get made, and does
the phrasing swap change WHERE it happens or only the final answer?

The published behavioral finding is about the model's output: under colloquial
patient phrasing the predicted continuation tends to sit lower on the care
ladder. This script asks the same question of the model's *internals*, one layer
at a time, on models the hosted Jacobian lens does not serve.

Method (logit lens): capture the residual stream after every block, decode each
layer through the model's own final norm and unembed, take the top-k spread at
the last prompt position, and score it with the SAME probability-weighted mean
tier the published analysis uses (`scripts/urgency_shift.py: expected_tier`,
reading the reviewed vocabulary from `data/urgency_tiers.draft.json`). Two
curves per pair - clinical and patient - and their per-layer gap.

This is a logit lens, NOT the registered Jacobian lens. Its transport matrices
are fitted offline and are not public, so a local Jacobian readout is not
available (docs/interp_engine_assessment.md section 3). Anything published from
this script must be labelled as a logit-lens measurement and kept separate from
the gemma-2-2b j-lens depth series.

Backend: interp-engine's eager path (CPU, all 34 points, one forward pass per
prompt via `layer_logits`). Model weights download from Hugging Face, so this
runs in CI, not in the sandbox (whose egress proxy blocks huggingface.co).

Usage:
  python scripts/depth_probe.py --pairs data/simulated/drift_sentinel.json \
      --model gemma-2-2b --tiers data/urgency_tiers.draft.json \
      --out trace_out/depth_<STAMP>__gemma-2-2b [--limit 3] [--layers all]
"""

import argparse
import json
import os
import platform
import re
import subprocess
from pathlib import Path

# How much of a layer's top-k mass must carry a tier before its expected tier is
# reported. Matches urgency_shift.py's default so the two instruments agree.
DEFAULT_MIN_COVERAGE = 0.30
DEFAULT_TOPK = 10


def _engine_sha():
    """Commit of the running checkout (git, else CI env, else None)."""
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        env = os.environ.get("GITHUB_SHA", "")
        return env[:12] if env else None


def environment():
    """Versions that produced these curves, so later drift is attributable
    between service changes and dependency changes. Lazy + tolerant: heavy ML
    imports resolve to None offline (tests), real versions in CI."""
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "engine_sha": _engine_sha(),
        "runner_image": os.environ.get("ImageVersion"),
    }
    for mod in ("torch", "transformers", "interp_engine"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:
            env[mod] = None
    return env


def load_vocab(path):
    """Reviewed tier vocabulary: {token: {"tier": int|None, ...}}. Medical terms
    live in the data file, never in this source (CLAUDE.md hard convention)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))["tokens"]


def bare(token):
    """Strip the graph path's 'Output " x"' wrapper if present."""
    if not isinstance(token, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', token)
    return (m.group(1) if m else token).strip() or None


def tier_of(token, vocab):
    """Tier for a single bare token, or None when unassigned/excluded.

    Deliberately has no continuation argument: a layer's residual decodes to a
    distribution, not to a generated phrase, so the head-noun rescue that
    urgency_shift.py applies to greedy continuations has nothing to read here.
    """
    if not token:
        return None
    entry = vocab.get(str(token).strip().lower())
    return entry["tier"] if entry else None


def expected_tier(spread, vocab, min_cov=DEFAULT_MIN_COVERAGE):
    """Probability-weighted mean tier over a top-k spread of bare tokens.

    Same arithmetic as urgency_shift.expected_tier (tests/test_depth_probe.py
    asserts the two agree on shared input); returns (tier, coverage) with tier
    None when too little of the mass carries a tier at all.
    """
    total = wsum = cov = 0.0
    for token, prob in spread or []:
        total += prob
        tr = tier_of(bare(token), vocab)
        if tr is not None:
            cov += prob
            wsum += prob * tr
    if not total or cov / total < min_cov:
        return None, round(cov / total if total else 0.0, 4)
    return round(wsum / cov, 4), round(cov / total, 4)


def depth_curve(spreads_by_layer, vocab, min_cov=DEFAULT_MIN_COVERAGE):
    """[{layer, expected_tier, coverage, top}] over layers, ascending."""
    curve = []
    for layer in sorted(spreads_by_layer, key=int):
        spread = spreads_by_layer[layer]
        et, cov = expected_tier(spread, vocab, min_cov)
        curve.append({
            "layer": int(layer),
            "expected_tier": et,
            "coverage": cov,
            "top": bare(spread[0][0]) if spread else None,
        })
    return curve


def curve_gap(curve_c, curve_p):
    """Per-layer patient-minus-clinical tier gap, None where either side is
    uninformative. Negative = the patient reading sits LOWER on the care ladder
    at that depth, which is the published behavioral finding's direction."""
    by_layer = {row["layer"]: row["expected_tier"] for row in curve_c}
    gap = []
    for row in curve_p:
        c = by_layer.get(row["layer"])
        p = row["expected_tier"]
        gap.append({"layer": row["layer"],
                    "gap": None if (c is None or p is None) else round(p - c, 4)})
    return gap


def first_divergence(gap, threshold):
    """Shallowest layer whose gap magnitude reaches `threshold`, else None.

    The headline number: 'the two phrasings part company at layer N'.
    """
    for row in gap:
        if row["gap"] is not None and abs(row["gap"]) >= threshold:
            return row["layer"]
    return None


def build_result(index, pair, curves, threshold):
    """One depth-probe record for a pair. `curves` is (clinical, patient)."""
    curve_c, curve_p = curves
    gap = curve_gap(curve_c, curve_p)
    informative = [r["gap"] for r in gap if r["gap"] is not None]
    return {
        "index": index,
        "prompts": {"clinical": pair["top_prompt"], "patient": pair["bottom_prompt"]},
        "curves": {"clinical": curve_c, "patient": curve_p},
        "gap": gap,
        "first_divergence_layer": first_divergence(gap, threshold),
        "final_gap": gap[-1]["gap"] if gap else None,
        "max_abs_gap": max((abs(g) for g in informative), default=None),
        "layers_informative": len(informative),
        "layers_measured": len(gap),
    }


def build_summary(model_id, hf_id, results, start_index=1, *, min_cov, topk,
                  threshold, tiers_path, tiers_status, revision=None):
    return {
        "mode": "depth_probe",
        "backend": "interp-engine-eager",
        "lens": "logit_lens",
        "graph_model": model_id,
        "source_set": None,
        "start_index": start_index,
        "pairs_requested": len(results),
        "completed": True,          # overwritten by main()'s flush
        "instrument": {
            "tiers_file": str(tiers_path),
            "tiers_status": tiers_status,
            "min_coverage": min_cov,
            "topk": topk,
            "divergence_threshold": threshold,
            "note": "logit lens, not the registered Jacobian lens; publish separately",
        },
        "inference": {"method": "logit_lens", "hf_id": hf_id, "dtype": "bfloat16",
                      "device": "cpu", "revision": revision,
                      "environment": environment()},
        "results": results,
    }


def measure_depth(model, prompt, layers, topk):
    """{layer: [[bare_token, prob], ...]} at the last prompt position.

    One forward pass for all layers: interp-engine's `layer_logits` captures the
    residual stream once and decodes each requested layer through the model's own
    final norm and lm_head, applying the family's post-unembed arithmetic
    (Gemma's softcap) so the rows are comparable to the model's real logits.
    """
    import torch
    from interp_engine import layer_logits

    tokens = model.to_tokens(prompt)
    out = layer_logits(model, tokens, {"logit_lens": list(layers)})
    spreads = {}
    for layer, logits in out["logit_lens"].items():
        probs = torch.softmax(logits[-1].float(), dim=-1)
        top = torch.topk(probs, topk)
        spreads[int(layer)] = [
            [model.to_string(int(idx)), round(float(p), 4)]
            for p, idx in zip(top.values.tolist(), top.indices.tolist())
        ]
    return spreads


def resolve_layers(spec, n_layers):
    """'all' | 'every:N' | '0,5,10' -> a sorted list of layer indices."""
    if spec in (None, "", "all"):
        return list(range(n_layers))
    if spec.startswith("every:"):
        step = max(1, int(spec.split(":", 1)[1]))
        return list(range(0, n_layers, step))
    out = sorted({int(x) for x in spec.split(",") if x.strip() != ""})
    bad = [x for x in out if x < 0 or x >= n_layers]
    if bad:
        raise ValueError(f"layers out of range for a {n_layers}-layer model: {bad}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--model", required=True,
                        help="short model id (logits_eval.HF_IDS) or a Hugging Face repo id")
    parser.add_argument("--tiers", default="data/urgency_tiers.draft.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--topk", type=int, default=DEFAULT_TOPK)
    parser.add_argument("--layers", default="all",
                        help="'all', 'every:N', or a comma list")
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    parser.add_argument("--divergence-threshold", type=float, default=0.25,
                        help="tier gap magnitude that counts as the curves parting")
    args = parser.parse_args()

    from interp_engine import load_model, sync_model

    from logits_eval import HF_IDS  # same short-id table; one place to add models

    model_id = args.model
    hf_id = HF_IDS.get(model_id, model_id)
    tiers_doc = json.loads(Path(args.tiers).read_text(encoding="utf-8"))
    vocab = tiers_doc["tokens"]
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    if args.offset:
        pairs = pairs[args.offset:]
    if args.limit:
        pairs = pairs[:args.limit]

    print(f"Loading {hf_id} via interp-engine eager (cpu, bfloat16) ...", flush=True)
    # Eager on CPU is the only backend that serves every point without CUDA, and
    # trust_remote_code stays off: we never execute checkpoint-bundled code.
    model = sync_model(load_model(hf_id, backend="eager", device="cpu",
                                  dtype="bfloat16", trust_remote_code=False))
    model.warmup()
    layers = resolve_layers(args.layers, model.n_layers)
    print(f"  {model.n_layers} layers; probing {len(layers)}", flush=True)

    start_index = args.offset + 1   # global 1-based join key, matching the trace path
    results = []
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / f"depth_probe.part_{start_index:02d}.json"

    def flush(completed):
        # Flushed after every pair so the workflow's always() commit step lands
        # the measured prefix even when a slow CPU run is killed mid-batch.
        summary = build_summary(
            model_id, hf_id, results, start_index,
            min_cov=args.min_coverage, topk=args.topk,
            threshold=args.divergence_threshold,
            tiers_path=args.tiers, tiers_status=tiers_doc.get("status"))
        summary["completed"] = completed
        if not completed:
            summary["_partial"] = "in-progress flush (crash/timeout protection)"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    try:
        for i, pair in enumerate(pairs, start=start_index):
            curves = tuple(
                depth_curve(measure_depth(model, pair[key], layers, args.topk),
                            vocab, args.min_coverage)
                for key in ("top_prompt", "bottom_prompt"))
            results.append(build_result(i, pair, curves, args.divergence_threshold))
            flush(completed=False)
            r = results[-1]
            print(f"  [{i}/{args.offset + len(pairs)}] first_divergence="
                  f"{r['first_divergence_layer']} final_gap={r['final_gap']} "
                  f"informative={r['layers_informative']}/{r['layers_measured']}", flush=True)
        flush(completed=True)
    finally:
        model.shutdown()
    print(f"Wrote {len(results)} results -> {summary_path}")


if __name__ == "__main__":
    main()
