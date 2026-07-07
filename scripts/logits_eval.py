"""Cross-model next-token behavior WITHOUT attribution graphs.

Neuronpedia's hosted circuit tracer only renders gemma-2-2b (see
docs/cross-model.md). To still compare how OTHER models respond to the same
patient-vs-clinical swap, this runs the open weights directly and measures the
same next-token quantities the graph path produces - the target token's
probability under each phrasing, the language penalty, and the top-k spread -
then writes a batch_eval-compatible ``batch_summary.part_01.json``. The existing
frontend export merges that into ``scenario.models[<model>]`` unchanged.

There is no transcoder, so there is no feature attribution (clinical_mass) and
no circuit render - those fields are null and the model's chip greys the
Med-circuit meter, exactly like any non-featured model.

Runs on CPU (bf16); a 4B model needs a few GB of RAM and a single forward pass
per prompt. Model weights download from Hugging Face, so this runs in CI, not in
the sandbox (whose egress proxy blocks huggingface.co).

Usage:
  python scripts/logits_eval.py --pairs data/simulated/pairs_<STAMP>.json \
      --model qwen3-4b --out trace_out/pairs_<STAMP>__qwen3-4b [--limit 13] [--topk 10]
"""

import argparse
import json
from pathlib import Path

# Short id -> Hugging Face repo. Mirrors graph_client.MODEL_REGISTRY but kept
# local so this script has no dependency on the graph stack.
HF_IDS = {
    "gemma-2-2b": "google/gemma-2-2b",
    "gemma-3-4b-it": "google/gemma-3-4b-it",
    "qwen3-4b": "Qwen/Qwen3-4B",
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",
}


def label(tokenizer, token_id):
    """Match the graph path's logit-label format: 'Output " sleeping"'."""
    return 'Output "' + tokenizer.decode([int(token_id)]) + '"'


def measure(model, tokenizer, prompt, target_id, topk, decode_top=4, decode_steps=2):
    """Next-token probability of target_id after `prompt`, plus the top-k spread.

    Also greedily decodes `decode_steps` extra tokens for the top `decode_top`
    candidates ("continuations"): a top-1 of ' new' alone is uninformative, but
    its continuation 'new sleeping pill' is classifiable by the urgency tiers.
    The 4 sequences share one length (prompt + 1 candidate), so decoding runs
    as 2 batched forward passes, not 8 singles.
    """
    import torch

    input_ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=True).input_ids
    with torch.no_grad():
        logits = model(input_ids).logits[0, -1]
    probs = torch.softmax(logits.float(), dim=-1)
    target_prob = round(float(probs[target_id]), 4)
    top = torch.topk(probs, topk)
    spread = [[label(tokenizer, idx), round(float(p), 4)]
              for p, idx in zip(top.values.tolist(), top.indices.tolist())]

    continuations = {}
    cand = top.indices.tolist()[:decode_top]
    if cand:
        batch = torch.cat([
            torch.cat([input_ids, torch.tensor([[c]])], dim=1) for c in cand
        ], dim=0)
        with torch.no_grad():
            for _ in range(decode_steps):
                nxt = model(batch).logits[:, -1].argmax(dim=-1, keepdim=True)
                batch = torch.cat([batch, nxt], dim=1)
        start = input_ids.shape[1]
        for row, c in zip(batch.tolist(), cand):
            text = tokenizer.decode(row[start:]).strip()
            key = tokenizer.decode([c]).strip()
            if key and text and text != key:
                continuations[key] = text
    return target_prob, spread, continuations


def build_result(index, pair, tokenizer, measure_fn, topk):
    """One batch_summary result for a pair, in the graph path's schema."""
    clinical = pair["top_prompt"]
    patient = pair["bottom_prompt"]
    target = pair.get("target_clinical_token") or ""
    target_ids = tokenizer(target, add_special_tokens=False).input_ids
    if not target_ids:
        # empty/whitespace target - nothing measurable; record prompts only
        return {
            "index": index, "mode": "2panel",
            "prompts": {"clinical": clinical, "patient": patient},
            "target_token": None, "probabilities": {"clinical": None, "patient": None},
            "language_penalty": None, "predictive_spread": {"clinical": [], "patient": []},
            "forced_targets": [], "circuit_diff": None, "screening": None,
        }
    target_id = target_ids[0]
    prob_c, spread_c, cont_c = measure_fn(clinical, target_id, topk)
    prob_p, spread_p, cont_p = measure_fn(patient, target_id, topk)
    penalty = round(prob_p - prob_c, 4) if (prob_c is not None and prob_p is not None) else None
    return {
        "index": index, "mode": "2panel",
        "prompts": {"clinical": clinical, "patient": patient},
        "target_token": label(tokenizer, target_id),
        "probabilities": {"clinical": prob_c, "patient": prob_p},
        "language_penalty": penalty,
        "predictive_spread": {"clinical": spread_c, "patient": spread_p},
        "forced_targets": [],
        # bare-token -> greedy multi-token completion, for urgency classification
        "continuations": {"clinical": cont_c, "patient": cont_p},
        "circuit_diff": None,   # no graph -> no circuit diff
        "screening": None,      # measured directly, not screened
    }


def build_summary(model_id, hf_id, results):
    return {
        "mode": "2panel",
        "backend": "logits",          # not the hosted graph backend
        "graph_model": model_id,      # export keys models_meta off this
        "source_set": None,           # no transcoder -> features=False downstream
        "generation_params": {},
        "start_index": 1,
        "screen_targets": None,
        "inference": {"method": "logits", "hf_id": hf_id, "dtype": "bfloat16"},
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True, help="pairs_<STAMP>.json to measure")
    parser.add_argument("--model", required=True,
                        help="short model id (%s) or a Hugging Face repo id" % "/".join(HF_IDS))
    parser.add_argument("--out", required=True, help="output dir, e.g. trace_out/pairs_<STAMP>__<model>")
    parser.add_argument("--limit", type=int, default=0, help="measure only the first N pairs (0 = all)")
    parser.add_argument("--topk", type=int, default=10, help="spread size per phrasing")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = args.model
    hf_id = HF_IDS.get(model_id, model_id)
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    if args.limit:
        pairs = pairs[:args.limit]

    print(f"Loading {hf_id} (cpu, bfloat16) ...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(hf_id)
    # low_cpu_mem_usage keeps a 4B model within a 16 GB runner during load.
    model = AutoModelForCausalLM.from_pretrained(
        hf_id, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    model.eval()

    def measure_fn(prompt, target_id, topk):
        return measure(model, tokenizer, prompt, target_id, topk)

    results = []
    for i, pair in enumerate(pairs, start=1):
        results.append(build_result(i, pair, tokenizer, measure_fn, args.topk))
        r = results[-1]
        print(f"  [{i}/{len(pairs)}] clin={r['probabilities']['clinical']} "
              f"pat={r['probabilities']['patient']} pen={r['language_penalty']}", flush=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "batch_summary.part_01.json"
    summary_path.write_text(
        json.dumps(build_summary(model_id, hf_id, results), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} results -> {summary_path}")


if __name__ == "__main__":
    main()
