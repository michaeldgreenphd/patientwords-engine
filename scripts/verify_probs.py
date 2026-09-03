"""Third-implementation check on the study's next-token probabilities ($0, CPU).

``docs/backend_agreement_20260903.md`` measured what two of the study's
backends say about the same 50 prompts on gemma-2-2b. The AGGREGATE agrees
(mean penalty -0.0648 hosted vs -0.0653 local); individual pairs do not, by up
to 0.0315 - about half the study's mean penalty. The cause was not identified:
the local path runs bfloat16, the hosted dtype is unknown, and hosted
probabilities are rounded to three decimals.

This script measures the same prompts a THIRD way, through interp-engine's
eager CPU backend, and defaults to **float32** so dtype is removed as a
candidate rather than repeated:

- if these numbers land on the local bfloat16 numbers, the residual gap is the
  hosted service's;
- if they land on the hosted numbers, the gap is our dtype;
- if they land on neither, none of the three is exact, which is worth knowing
  before another claim rests on one of them.

Two things it records rather than assumes, because either would otherwise show
up as a small disagreement instead of as a different measurement:

1. **Tokenization parity.** ``scripts/logits_eval.py`` tokenizes with the raw HF
   tokenizer and ``add_special_tokens=True``; this path goes through
   interp-engine's ``to_tokens``. Every pair records whether the two produce the
   same id sequence (``token_parity``), so a BOS or normalization difference can
   never be mistaken for an engine difference.
2. **The full softmax.** ``GenStep.logits`` is the whole vocab vector on the
   eager backend (it is ``None`` on vLLM, which is why this path is eager-only),
   so the target's probability is never censored by a top-k floor the way the
   hosted top-10 list censors it.

Output goes to ``<out>/verify_summary.part_NN.json`` with ``backend:
"interp-engine"``. The filename deliberately differs from ``batch_summary*`` so
the behavioral collectors, which glob that prefix, never ingest a verification
run as a published measurement. Compare with ``scripts/backend_agreement.py``.

Model weights download from Hugging Face, so this runs in CI, not in the sandbox
(whose egress proxy blocks huggingface.co).

Usage:
  python scripts/verify_probs.py --pairs data/simulated/pairs_<STAMP>.json \
      --model gemma-2-2b --out trace_out/verify_pairs_<STAMP>__gemma-2-2b \
      [--limit 50] [--offset 0] [--topk 10] [--dtype float32]

No medical vocabulary lives in this file.
"""

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path

DEFAULT_TOPK = 10
DEFAULT_DTYPE = "float32"


def _engine_sha():
    """Commit of the running checkout (git, else CI env, else None)."""
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        env = os.environ.get("GITHUB_SHA", "")
        return env[:12] if env else None


def environment():
    """Versions that produced these numbers. Lazy + tolerant: heavy ML imports
    resolve to None offline (tests), real versions in CI."""
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


def label(tokenizer, token_id):
    """The graph path's logit-label format: 'Output " sleeping"'."""
    return 'Output "' + tokenizer.decode([int(token_id)]) + '"'


def token_parity(model, tokenizer, prompt):
    """Do interp-engine's to_tokens and the raw HF tokenizer agree on this prompt?

    Recorded per pair rather than asserted once, because the answer can differ
    by prompt (a normalization rule that only fires on some strings), and a
    silent divergence here would be read as an engine disagreement.
    """
    engine_ids = [int(t) for t in model.to_tokens(prompt)[0].tolist()]
    hf_ids = list(tokenizer(prompt, add_special_tokens=True).input_ids)
    return {"match": engine_ids == hf_ids,
            "n_engine": len(engine_ids), "n_hf": len(hf_ids)}


def measure(model, tokenizer, prompt, target_id, topk):
    """Next-token probability of target_id after `prompt`, plus the top-k spread.

    Uses the FULL logit vector from the eager backend, so the target's
    probability is never censored by the spread depth - unlike the hosted path,
    whose probabilities are read off a truncated top-N logit list.
    """
    import torch
    from interp_engine import generate_stream

    tokens = model.to_tokens(prompt)
    step = next(iter(generate_stream(model, tokens, max_tokens=1, n_logprobs=topk)))
    if step.logits is None:
        raise SystemExit(
            "GenStep.logits is None: this is the vLLM backend, which never ships the "
            "logit tensor out of the worker. Load with backend='eager' (see "
            "docs/interp_engine_assessment.md section 1).")
    probs = torch.softmax(step.logits.float(), dim=-1)
    target_prob = round(float(probs[target_id]), 4)
    top = torch.topk(probs, topk)
    spread = [[label(tokenizer, idx), round(float(p), 4)]
              for p, idx in zip(top.values.tolist(), top.indices.tolist())]
    return target_prob, spread


def build_result(index, pair, model, tokenizer, measure_fn, topk):
    """One result in the graph path's schema, plus this path's parity record."""
    clinical = pair["top_prompt"]
    patient = pair["bottom_prompt"]
    target = pair.get("target_clinical_token") or ""
    target_ids = tokenizer(target, add_special_tokens=False).input_ids
    parity = {"clinical": token_parity(model, tokenizer, clinical),
              "patient": token_parity(model, tokenizer, patient)}
    if not target_ids:
        # empty/whitespace target - nothing measurable; record prompts only
        return {
            "index": index, "mode": "2panel",
            "prompts": {"clinical": clinical, "patient": patient},
            "target_token": None, "probabilities": {"clinical": None, "patient": None},
            "language_penalty": None, "predictive_spread": {"clinical": [], "patient": []},
            "token_parity": parity, "circuit_diff": None, "screening": None,
        }
    target_id = target_ids[0]
    prob_c, spread_c = measure_fn(clinical, target_id, topk)
    prob_p, spread_p = measure_fn(patient, target_id, topk)
    return {
        "index": index, "mode": "2panel",
        "prompts": {"clinical": clinical, "patient": patient},
        "target_token": label(tokenizer, target_id),
        "probabilities": {"clinical": prob_c, "patient": prob_p},
        "language_penalty": round(prob_p - prob_c, 4),
        "predictive_spread": {"clinical": spread_c, "patient": spread_p},
        "token_parity": parity,
        "circuit_diff": None,   # no graph -> no circuit diff
        "screening": None,      # measured directly, not screened
    }


def build_summary(model_id, hf_id, results, start_index=1, dtype=DEFAULT_DTYPE,
                  topk=DEFAULT_TOPK, completed=True, revision=None):
    return {
        "mode": "2panel",
        # Distinct from both "hosted" and "logits": this is a verification run,
        # not a published measurement, and nothing downstream should merge it.
        "backend": "interp-engine",
        "graph_model": model_id,
        "source_set": None,
        "generation_params": {},
        "start_index": start_index,
        "pairs_requested": len(results),
        "completed": completed,
        "screen_targets": None,
        "inference": {"method": "interp-engine-eager", "hf_id": hf_id, "dtype": dtype,
                      "device": "cpu", "topk": topk, "revision": revision,
                      "environment": environment()},
        "results": results,
    }


def write_summary(out_dir, summary, start_index):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"verify_summary.part_{start_index:02d}.json"
    path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--model", required=True,
                        help="short model id (logits_eval.HF_IDS) or a Hugging Face repo id")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--topk", type=int, default=DEFAULT_TOPK)
    parser.add_argument("--dtype", default=DEFAULT_DTYPE,
                        help="float32 (default, removes dtype as a candidate cause) or bfloat16 "
                             "(matches logits_eval.py, to isolate the engine alone)")
    args = parser.parse_args()

    from interp_engine import load_model, sync_model

    from logits_eval import HF_IDS  # same short-id table; one place to add models

    model_id = args.model
    hf_id = HF_IDS.get(model_id, model_id)
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    if args.offset:
        pairs = pairs[args.offset:]
    if args.limit:
        pairs = pairs[:args.limit]

    print(f"Loading {hf_id} via interp-engine eager (cpu, {args.dtype}) ...", flush=True)
    # Eager is the only backend that ships the full logit vector, and the only
    # one that runs without CUDA. trust_remote_code stays off: we never execute
    # checkpoint-bundled code.
    model = load_model(hf_id, backend="eager", device="cpu",
                       dtype=args.dtype, trust_remote_code=False)
    # sync_model is ONLY for the async lifecycle methods; the raw model goes to
    # generate_stream, which is itself a sync free function (depth_probe.py).
    lifecycle = sync_model(model)
    lifecycle.warmup()
    tokenizer = model.tokenizer

    start_index = args.offset + 1   # global 1-based join key, matching the trace path
    results = []

    def flush(completed):
        # Flushed after every pair so the workflow's always() commit step lands
        # the measured prefix even when a slow CPU run is killed mid-batch.
        write_summary(args.out, build_summary(
            model_id, hf_id, results, start_index, dtype=args.dtype,
            topk=args.topk, completed=completed), start_index)

    def measure_fn(prompt, target_id, topk):
        return measure(model, tokenizer, prompt, target_id, topk)

    for offset, pair in enumerate(pairs):
        index = start_index + offset
        results.append(build_result(index, pair, model, tokenizer, measure_fn, args.topk))
        flush(False)
        print(f"  [{index}] {results[-1]['probabilities']}", flush=True)

    flush(True)
    mismatched = [r["index"] for r in results
                  if not all(s["match"] for s in r["token_parity"].values())]
    if mismatched:
        print(f"TOKENIZATION PARITY FAILED on indices {mismatched}: these rows measure a "
              f"different token sequence than logits_eval.py would, so their disagreement "
              f"is not attributable to the engine.", flush=True)
    print(f"wrote {args.out}/verify_summary.part_{start_index:02d}.json "
          f"({len(results)} pairs)", flush=True)


if __name__ == "__main__":
    main()
