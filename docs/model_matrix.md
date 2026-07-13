# CPU-logits model matrix

Registry of every short model id accepted by `scripts/logits_eval.py` (`HF_IDS`) and the
logits-eval workflow. The five additions are the owner-approved expansion from
`docs/fable_week_plan.md`: C1 (Llama-3.2-3B), C3 (OLMo-2), C4 (medical-tuned 7B),
B2 (gemma-2-9b), B3 (gemma-2-2b-it). All models run the same single code path —
bfloat16 on CPU, `low_cpu_mem_usage=True` — no per-model dtype or kwargs.

## Matrix

| Short id | HF repo | Params | Family | Gate status | Role in the study |
|---|---|---|---|---|---|
| `gemma-2-2b` | `google/gemma-2-2b` | 2.6B | Gemma 2 (Google) | Gated — Gemma license (accepted; graph path already uses it) | Base/anchor model; only hosted-graph model, logits path is its backend cross-check |
| `gemma-3-4b-it` | `google/gemma-3-4b-it` | 4.3B | Gemma 3 (Google) | Gated — Gemma license (accepted; already runs in CI with `HF_TOKEN`) | Cross-generation Gemma, instruction-tuned |
| `qwen3-4b` | `Qwen/Qwen3-4B` | 4.0B | Qwen3 (Alibaba) | Ungated (Apache-2.0) | Second family |
| `qwen3-1.7b` | `Qwen/Qwen3-1.7B` | 1.7B | Qwen3 (Alibaba) | Ungated (Apache-2.0) | Second family, small scale |
| `llama-3.2-3b` | `meta-llama/Llama-3.2-3B` | 3.2B | Llama 3.2 (Meta) | Gated — Meta contact-info form (free) | **C1** — third model family |
| `olmo-2-1b` | `allenai/OLMo-2-0425-1B` | ~1.5B | OLMo 2 (Ai2) | Ungated (Apache-2.0) | **C3** — fully-open provenance (open data, training code, checkpoints) |
| `biomistral-7b` | `BioMistral/BioMistral-7B` | 7.2B | Mistral 7B derivative (PubMed Central continued pretraining) | Ungated (Apache-2.0) | **C4** — medical-domain-tuned contrast |
| `gemma-2-2b-it` | `google/gemma-2-2b-it` | 2.6B | Gemma 2 (Google) | Gated — Gemma license (likely already granted; verify via probe) | **B3** — instruction-tuning contrast: same base as `gemma-2-2b` ± IT |
| `gemma-2-9b` | `google/gemma-2-9b` | 9.2B | Gemma 2 (Google) | Gated — Gemma license (likely already granted; verify via probe) | **B2** — scale universality within one family (2.6B → 9.2B) |
| `medgemma-4b-it` | `google/medgemma-4b-it` | 4.3B | MedGemma / Gemma 3 (Google, Health AI Developer Foundations) | Gated — HAI-DEF terms (owner accepted 2026-07-13 on the CI `HF_TOKEN` account) | Medical-tuned twin of `gemma-3-4b-it` (same base, same size): the paired contrast isolates what medical fine-tuning does to the colloquial-vs-clinical gap |

The Gemma gate on Hugging Face is one shared license acknowledgement across `google/gemma*`
repos, so the acceptance already made for `google/gemma-3-4b-it` (the grant behind the
existing CI `HF_TOKEN`) very likely covers `gemma-2-2b-it` and `gemma-2-9b` — the limit-3
probe below confirms it either way.

## CPU runtime and chunking (7B/9B caution)

- 2–4B models run ~1 min/pair on the free public runners; a 120-pair batch is ~2 h,
  comfortably inside the workflow's 240-minute job timeout.
- **7B/9B (`biomistral-7b`, `gemma-2-9b`) are ~2–4× slower per pair on CPU** (~2–4 min/pair),
  so a full 120-pair run is ~4–8 h and will hit the timeout. CI fires for these two must use
  smaller chunks than the 2–4B models — set `limit` well under the timeout budget
  (≤ ~60 pairs to be safe). The logits trigger currently exposes `limit` only (a prefix of
  the batch); covering a full batch in chunks needs an `--offset` added to
  `scripts/logits_eval.py` and the workflow (mirroring the circuit-trace `offsets` matrix
  and its `batch_summary.part_NN.json` naming) before firing the remainder.
- RAM: a 9B model in bf16 is ~18 GB of weights; `low_cpu_mem_usage=True` keeps the load
  peak near that, which fits the 16 GB + swap envelope of `ubuntu-latest` only barely —
  if a 9B probe is OOM-killed (exit 137 in the job log), that is a runner-memory finding,
  not a license problem.

## Probe protocol (before any full run on a new model)

Fire `logits-eval` with `limit: 3` per new model first, via `scripts/fire_trigger.py`
(the required path — it journals the fire and enforces the one-running + one-pending
queue discipline). All five new models can share **one** fire: the workflow fans them out
as a matrix with `fail-fast: false` (`max-parallel: 2`), so a gated 401/403 on one leg
does not stop the others, and one fire occupies only one slot in the concurrency group.

Example trigger payload (`.github/trigger/logits-eval.json`):

```json
{"models": ["llama-3.2-3b", "olmo-2-1b", "biomistral-7b", "gemma-2-2b-it", "gemma-2-9b"],
 "pairs_file": "data/simulated/pairs_20260707T171223Z.json",
 "limit": 3, "commit_outputs": false, "_nonce": "probe-matrix-expansion"}
```

Read the result per matrix leg in the Actions run:

- **Success:** the "Measure next-token behavior" step prints three
  `clin=… pat=… pen=…` lines and the job summary shows the three pairs. The model is
  cleared for full-size fires (with the 7B/9B chunking caveat above).
- **401/403 gated-repo failure:** `huggingface_hub` raises a `GatedRepoError` /
  `Access to model <repo> is restricted` during `from_pretrained` in that step. This means
  the license has not been accepted **by the account that owns the CI `HF_TOKEN`**. Accept
  it (click-paths below), then re-probe that model alone.
- A 401 `Invalid credentials` (as opposed to a restricted-access message) means the
  `HF_TOKEN` secret itself is broken/expired — a different problem; fix the token first.

### License click-paths (do these logged in as the `HF_TOKEN` account)

- **`llama-3.2-3b`** — open <https://huggingface.co/meta-llama/Llama-3.2-3B>. The page
  shows a gate panel ("You need to agree to share your contact information to access this
  model"). Click **Expand to review and access**, fill Meta's form (legal name, date of
  birth, affiliation, country), and click **Submit / Agree and access repository**.
  Approval is usually granted within minutes but can take hours; check status at
  <https://huggingface.co/settings/gated-repos>. One acceptance covers the whole
  Llama-3.2 collection.
- **`gemma-2-2b-it`** — open <https://huggingface.co/google/gemma-2-2b-it>. If it already
  says "You have been granted access to this model", nothing to do (the gemma-3 grant
  propagated). Otherwise click **Acknowledge license**, review Google's Gemma Terms of
  Use, and confirm. Instant grant, no review queue.
- **`gemma-2-9b`** — same click-path at <https://huggingface.co/google/gemma-2-9b>.
- **`olmo-2-1b`**, **`biomistral-7b`** — ungated; nothing to accept.

If the token is fine-grained rather than classic, it also needs the
"Read access to contents of all public gated repos you can access" permission, or gated
downloads fail even after acceptance.

### Cost truth

License acceptance is free. Weight downloads are free. No card exists on the Hugging Face
account, so nothing can be charged; HF bills only optional subscriptions and hosted
inference endpoints, which this pipeline never uses. CI compute is GitHub's free
public-repo runners. Logits evals spend $0 Anthropic credits — `fire_trigger.py`'s $2/day
paid ceiling is untouched by any fire in this matrix. Charge risk: none.

## Model vetting policy (supply-chain, added 2026-07-09 on owner request)

Every model in the matrix must satisfy ALL of:

1. **Official organization only.** All nine registry entries resolve to
   verified first-party orgs: `google` (Gemma), `meta-llama` (Llama),
   `Qwen`, `allenai` (OLMo), `BioMistral` (the project's own org). No
   community re-uploads, no fine-tune mirrors, no lookalike names — a
   registry change means re-checking the org page by hand.
2. **safetensors only.** `logits_eval.py` loads with `use_safetensors=True`,
   which HARD-FAILS instead of falling back to pickle `.bin` weights
   (pickle deserialization is arbitrary code execution). Enforced by a
   tripwire test (`test_model_loading_supply_chain_posture`).
3. **No remote code, ever.** `trust_remote_code` is explicitly False in all
   loaders and the tripwire test fails the suite if any script sets it True.
   A model that "requires" remote code is rejected from the matrix.
4. **Ephemeral execution.** Weights are only ever loaded on throwaway GitHub
   CI runners whose only secret is the read-scoped HF token — never on the
   owner's machine or a dev container. Worst case for a hostile repo is a
   burned read token, which is rotatable and grants nothing.
5. **Pin after probe.** The first successful probe run of each model records
   the resolved commit SHA in this file; subsequent fires SHOULD pass that
   revision so a later force-push to the repo cannot silently swap weights.
   (Nightly critic task: fill the table below as probes land.)

| short id | pinned revision | probe date |
|---|---|---|
| (fills in as probes land) | | |
