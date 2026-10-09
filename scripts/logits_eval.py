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
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, NoReturn


def _engine_sha():
    """Commit of the running checkout (git, else CI env, else None)."""
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        env = os.environ.get("GITHUB_SHA", "")
        return env[:12] if env else None


def environment():
    """Measurement environment record (audit 2026-07-21 E3/P0-3): the versions
    that produced these probabilities, so future drift is attributable between
    service changes and dependency changes. Lazy + tolerant: heavy ML imports
    resolve to None offline (tests), real versions in CI."""
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "engine_sha": _engine_sha(),
        "runner_image": os.environ.get("ImageVersion"),  # GitHub Actions image tag
    }
    for mod in ("torch", "transformers", "accelerate"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:
            env[mod] = None
    return env

# Short id -> Hugging Face repo. Mirrors graph_client.MODEL_REGISTRY but kept
# local so this script has no dependency on the graph stack.
HF_IDS = {
    "gemma-2-2b": "google/gemma-2-2b",
    "gemma-3-4b-it": "google/gemma-3-4b-it",
    "qwen3-4b": "Qwen/Qwen3-4B",
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",
    # Expanded matrix (owner-approved; see docs/model_matrix.md for gate
    # status, roles, and the limit-3 probe protocol). All run the same
    # bfloat16-CPU path; the 7B/9B entries are ~2-4x slower per pair, so CI
    # fires for them must use smaller chunks than the 2-4B models.
    "llama-3.2-3b": "meta-llama/Llama-3.2-3B",
    "olmo-2-1b": "allenai/OLMo-2-0425-1B",
    "biomistral-7b": "BioMistral/BioMistral-7B",  # DROPPED 2026-07-13: pickle-only upstream
    "meditron-7b": "epfl-llm/meditron-7b",  # SUPERSEDED 2026-07-17: gated (403) and 2 years old; kept for the record
    # Meditron successors (owner 2026-07-17): the same EPFL lineage, current.
    # Meditron3-8B is Llama-3.1-8B based (owner signed the license
    # acknowledgment 2026-07-17); Apertus-8B-MeditronFO is Apertus-8B based
    # and carries no acknowledgment gate. 8B class: swap step required,
    # small chunks only. Meditron3-8B moved from OpenMeditron/ to EPFLiGHT/
    # (the old path HTTP-307s to the new one, which serves the same pinned
    # commit; checked against the public HF API 2026-10-09).
    "meditron3-8b": "EPFLiGHT/Meditron3-8B",
    "apertus-8b-meditronfo": "EPFLiGHT/Apertus-8B-MeditronFO",
    # Same base as gemma-3-4b-it with medical tuning - the paired contrast
    # isolates what medical fine-tuning does to the register gap. Gated by
    # HAI-DEF terms (owner accepted 2026-07-13).
    "medgemma-4b-it": "google/medgemma-4b-it",

    "gemma-2-2b-it": "google/gemma-2-2b-it",
    "gemma-2-9b": "google/gemma-2-9b",
}

# Ids kept in HF_IDS as records only. They have no pin, so resolve_pinned_model
# refuses them and no trigger can select them: biomistral-7b (pickle-only
# upstream), meditron-7b (superseded by meditron3-8b), gemma-2-9b (two load
# deaths on the standard runner). Re-admitting one means adding a pin.
TOMBSTONES = frozenset({"biomistral-7b", "meditron-7b", "gemma-2-9b"})

# Short id -> the exact Hugging Face commit every load is pinned to (pinning
# enforced since 2026-10-09; docs/model_matrix.md "Pinned revisions" has the
# provenance of each). Always a full 40-hex commit SHA, never a branch or tag,
# because branches move: EPFLiGHT/Apertus-8B-MeditronFO replaced its weights on
# 2026-10-06 (commit 4409c9407554), after every landed measurement of that id.
# Each pin is the revision the model's landed summaries recorded in
# `inference.revision`, so a new fire measures the weights already published.
# A new model gets its pin when it is added; an id in HF_IDS without one must
# be in TOMBSTONES (tests/test_logits_registry.py checks both).
HF_REVISIONS = {
    "gemma-2-2b": "c5ebcd40d208330abc697524c919956e692655cf",
    "gemma-3-4b-it": "093f9f388b31de276ce2de164bdc2081324b9767",
    "qwen3-4b": "1cfa9a7208912126459214e8b04321603b3df60c",
    "qwen3-1.7b": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    "llama-3.2-3b": "13afe5124825b4f3751f836b40dafda64c1ed062",
    "olmo-2-1b": "a1847dff35000b4271fa70afc5db10fd29fedbdf",
    "meditron3-8b": "783c241b18b84692689e0336170b345e5732e48e",
    # The 2026-06-26 weights every landed apertus measurement used, NOT the
    # 2026-10-06 replacement on upstream main.
    "apertus-8b-meditronfo": "ef2b141da7ccc347c2a13b2518370ba6a8a2b745",
    "medgemma-4b-it": "290cda5eeccbee130f987c4ad74a59ae6f196408",
    "gemma-2-2b-it": "299a8560bedf22ed1c72a8a11e7dce4a7f9f51f8",
}

FULL_SHA = re.compile(r"[0-9a-f]{40}")


class PinError(RuntimeError):
    """A model load refused because its weights are not pinned to one exact commit."""


class UnpinnedModelError(PinError):
    """No exact commit to load: a tombstone or unpinned short id, a repo id
    passed without --revision, or a --revision that is not a full commit SHA."""


class RevisionMismatchError(PinError):
    """The commit asked for or loaded differs from the pin: a --revision that
    contradicts a registry pin, or a resolved `_commit_hash` that is not the pin."""


def resolve_pinned_model(model_id: str, revision: str | None = None,
                         registry: dict[str, str] | None = None) -> tuple[str, str]:
    """(hf_repo_id, pinned_commit) for a --model value, or a PinError.

    Runs before anything is imported or downloaded. A short id in `registry`
    (default HF_IDS) loads its HF_REVISIONS pin; `revision`, if given, must
    equal it. Any other value is taken as a Hugging Face repo id and needs an
    explicit full-SHA `revision`; a repo that a registered short id already
    names must use that id's pin, so other weights never land under a name the
    study has already published.
    """
    registry = HF_IDS if registry is None else registry
    if revision is not None and not FULL_SHA.fullmatch(revision):
        raise UnpinnedModelError(
            f"--revision {revision!r} is not a full 40-hex commit SHA; branch and tag names "
            f"move, so they cannot pin weights")
    if model_id in registry:
        hf_id = registry[model_id]
        pin = HF_REVISIONS.get(model_id)
        if pin is None:
            why = "a tombstone kept as a record" if model_id in TOMBSTONES else "not pinned"
            raise UnpinnedModelError(
                f"{model_id} ({hf_id}) has no pinned revision in logits_eval.HF_REVISIONS ({why}); "
                f"add a full commit SHA there before loading it")
        if revision is not None and revision != pin:
            raise RevisionMismatchError(
                f"--revision {revision} contradicts the pin {pin} for {model_id}; measuring other "
                f"weights under a published short id is refused, so register a new short id instead")
        return hf_id, pin
    if revision is None:
        raise UnpinnedModelError(
            f"{model_id!r} is not a short id in the registry ({'/'.join(sorted(registry))}); "
            f"a Hugging Face repo id needs --revision <40-hex commit SHA>")
    for short_id, repo in HF_IDS.items():
        pin = HF_REVISIONS.get(short_id)
        if repo == model_id and pin is not None and pin != revision:
            raise RevisionMismatchError(
                f"{model_id} is registered as {short_id}, pinned to {pin}; --revision {revision} "
                f"would measure other weights under the same repo, so register a new short id instead")
    return model_id, revision


def check_resolved_revision(hf_id: str, pinned: str, resolved: str | None) -> None:
    """Refuse a load whose resolved commit is not the pin (RevisionMismatchError).

    `resolved` is the loaded config's `_commit_hash`. A missing hash is refused
    too: the load could not then be tied to the commit it was meant to be.
    """
    if resolved != pinned:
        raise RevisionMismatchError(
            f"{hf_id} resolved to commit {resolved!r}, not the pin {pinned}; "
            f"refusing to measure weights other than the pinned ones")


def refuse(exc: PinError) -> NoReturn:
    """Exit nonzero (status 1) with the refusal's class name and message on stderr."""
    raise SystemExit(f"refused: {type(exc).__name__}: {exc}")


def loaded_commit(hf_id: str, revision: str, config: Any) -> str | None:
    """The commit a pinned load resolved to: the loaded config's `_commit_hash`.

    A composite (multimodal) checkpoint loaded through its text-only class has
    none there: transformers 5.14.1's AutoModelForCausalLM narrows the config
    to its `text_config`, which is built from a dict without the hash (read
    from its auto_factory and configuration_utils, 2026-10-09; Qwen3.5's
    Qwen3_5ForCausalLM is such a class). The top-level config at the same
    revision carries it, so that is read instead (no weights are fetched).
    """
    commit = getattr(config, "_commit_hash", None)
    if commit is None:
        from transformers import AutoConfig

        top = AutoConfig.from_pretrained(hf_id, revision=revision, trust_remote_code=False)
        commit = getattr(top, "_commit_hash", None)
    return commit


def engine_revision(model: Any, hf_id: str, revision: str) -> str | None:
    """The resolved HF commit of an interp-engine model (its hf_model's config; see loaded_commit)."""
    return loaded_commit(hf_id, revision, getattr(getattr(model, "hf_model", None), "config", None))


def load_pinned_tokenizer(hf_id: str, revision: str) -> Any:
    """The tokenizer at exactly `revision` (remote code off)."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(hf_id, revision=revision, trust_remote_code=False)


def load_pinned(hf_id: str, revision: str) -> tuple[Any, Any, str]:
    """(tokenizer, model, resolved commit) at exactly `revision`, refused if the load resolves elsewhere.

    Supply-chain posture: never execute repo code, never deserialize pickle
    weights. use_safetensors=True hard-fails on repos without safetensors
    (every registry model ships them) instead of falling back to .bin.
    low_cpu_mem_usage keeps a 4B model within a 16 GB runner during load.
    """
    import torch
    from transformers import AutoModelForCausalLM

    tokenizer = load_pinned_tokenizer(hf_id, revision)
    model = AutoModelForCausalLM.from_pretrained(
        hf_id, revision=revision, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
        trust_remote_code=False, use_safetensors=True)
    resolved = loaded_commit(hf_id, revision, model.config)
    check_resolved_revision(hf_id, revision, resolved)
    model.eval()
    return tokenizer, model, resolved


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


def build_summary(model_id, hf_id, results, start_index=1, revision=None, revision_pinned=None):
    return {
        "mode": "2panel",
        "backend": "logits",          # not the hosted graph backend
        "graph_model": model_id,      # export keys models_meta off this
        "source_set": None,           # no transcoder -> features=False downstream
        "generation_params": {},
        "start_index": start_index,
        "pairs_requested": len(results),
        "completed": True,   # overwritten by main()'s flush: False until the loop finishes
        "screen_targets": None,
        # revision = the resolved HF commit hash, for the W5 pin table;
        # revision_pinned (added 2026-10-09) = the commit the load was pinned
        # to. main() refuses to measure unless the two are equal.
        "inference": {"method": "logits", "hf_id": hf_id, "dtype": "bfloat16",
                      "revision": revision, "revision_pinned": revision_pinned,
                      "environment": environment()},
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True, help="pairs_<STAMP>.json to measure")
    parser.add_argument("--model", required=True,
                        help="short model id (%s) or a Hugging Face repo id" % "/".join(HF_IDS))
    parser.add_argument("--out", required=True, help="output dir, e.g. trace_out/pairs_<STAMP>__<model>")
    parser.add_argument("--limit", type=int, default=0, help="measure only the first N pairs (0 = all)")
    parser.add_argument("--offset", type=int, default=0,
                        help="skip the first N pairs before applying --limit (chunking for models "
                             "too slow to finish a big batch inside the CI timeout; result indices "
                             "and the part filename stay global, matching the trace path)")
    parser.add_argument("--topk", type=int, default=10, help="spread size per phrasing")
    parser.add_argument("--revision", default=None,
                        help="exact 40-hex Hugging Face commit: required for a repo id outside HF_IDS; "
                             "for a short id it may only repeat that id's HF_REVISIONS pin")
    args = parser.parse_args(argv)

    model_id = args.model
    try:  # before anything is imported or downloaded
        hf_id, pinned = resolve_pinned_model(model_id, args.revision)
    except PinError as exc:
        refuse(exc)
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    if args.offset:
        pairs = pairs[args.offset:]
    if args.limit:
        pairs = pairs[:args.limit]

    print(f"Loading {hf_id} @ {pinned} (cpu, bfloat16) ...", flush=True)
    try:
        tokenizer, model, resolved = load_pinned(hf_id, pinned)
    except PinError as exc:
        refuse(exc)

    def measure_fn(prompt, target_id, topk):
        return measure(model, tokenizer, prompt, target_id, topk)

    start_index = args.offset + 1  # global 1-based join key, matching the trace path
    results = []
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / f"batch_summary.part_{start_index:02d}.json"

    def flush(completed):
        # Flushed after every pair so the workflow's always() commit step lands
        # the measured prefix even when the job ceiling kills a slow (8B/CPU)
        # run mid-batch - the third script to learn the 2026-07-28 lesson
        # (jlens_readout d36f944, jlens_steer 2989d4c).
        summary = build_summary(model_id, hf_id, results, start_index,
                                revision=resolved, revision_pinned=pinned)
        summary["completed"] = completed
        if not completed:
            summary["_partial"] = "in-progress flush (crash/timeout protection)"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    for i, pair in enumerate(pairs, start=start_index):
        results.append(build_result(i, pair, tokenizer, measure_fn, args.topk))
        flush(completed=False)
        r = results[-1]
        print(f"  [{i}/{args.offset + len(pairs)}] clin={r['probabilities']['clinical']} "
              f"pat={r['probabilities']['patient']} pen={r['language_penalty']}", flush=True)

    flush(completed=True)
    print(f"Wrote {len(results)} results -> {summary_path}")


if __name__ == "__main__":
    main()
