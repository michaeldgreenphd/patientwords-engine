# CPU-logits model matrix

Registry of every short model id accepted by `scripts/logits_eval.py` (`HF_IDS`) and the
logits-eval workflow. The first five additions were the owner-approved expansion from
`docs/fable_week_plan.md`: C1 (Llama-3.2-3B), C3 (OLMo-2), C4 (medical-tuned 7B),
B2 (gemma-2-9b), B3 (gemma-2-2b-it). All models run the same single code path —
bfloat16 on CPU, `low_cpu_mem_usage=True` — no per-model dtype or kwargs. Every load is
pinned to one exact Hugging Face commit (`HF_REVISIONS`; see *Pinned revisions* below).

## Matrix

| Short id | HF repo | Params | Family | Gate status | Role in the study |
|---|---|---|---|---|---|
| `gemma-2-2b` | `google/gemma-2-2b` | 2.6B | Gemma 2 (Google) | Gated — Gemma license (accepted; graph path already uses it) | Base/anchor model; only hosted-graph model, logits path is its backend cross-check |
| `gemma-3-4b-it` | `google/gemma-3-4b-it` | 4.3B | Gemma 3 (Google) | Gated — Gemma license (accepted; already runs in CI with `HF_TOKEN`) | Cross-generation Gemma, instruction-tuned |
| `qwen3-4b` | `Qwen/Qwen3-4B` | 4.0B | Qwen3 (Alibaba) | Ungated (Apache-2.0) | Second family. **Post-trained, thinking-enabled checkpoint, not a base model** (base: `Qwen/Qwen3-4B-Base`) |
| `qwen3-1.7b` | `Qwen/Qwen3-1.7B` | 1.7B | Qwen3 (Alibaba) | Ungated (Apache-2.0) | Second family, small scale. **Post-trained, thinking-enabled checkpoint, not a base model** (base: `Qwen/Qwen3-1.7B-Base`) |
| `llama-3.2-3b` | `meta-llama/Llama-3.2-3B` | 3.2B | Llama 3.2 (Meta) | Gated — Meta contact-info form (owner accepted 2026-07-19 on the CI `HF_TOKEN` account; probe-confirm pending) | **C1** — third model family |
| `olmo-2-1b` | `allenai/OLMo-2-0425-1B` | ~1.5B | OLMo 2 (Ai2) | Ungated (Apache-2.0) | **C3** — fully-open provenance (open data, training code, checkpoints) |
| `biomistral-7b` | `BioMistral/BioMistral-7B` | 7.2B | Mistral 7B derivative (PubMed Central continued pretraining) | **DROPPED 2026-07-13** — upstream ships pickle-only weights, incompatible with the safetensors-only posture | was **C4**; role moved to `meditron-7b` |
| `meditron-7b` | `epfl-llm/meditron-7b` | 7B | Llama-2 derivative (PubMed continued pretraining, EPFL) | **SUPERSEDED 2026-07-17** — gated (403) and two years old; kept as a record, unpinned, so it cannot be loaded | was **C4**; role moved to `meditron3-8b` and `apertus-8b-meditronfo` |
| `gemma-2-2b-it` | `google/gemma-2-2b-it` | 2.6B | Gemma 2 (Google) | Gated — Gemma license (owner confirmed access 2026-07-19 on the CI `HF_TOKEN` account; probe-confirm pending) | **B3** — instruction-tuning contrast: same base as `gemma-2-2b` ± IT |
| `gemma-2-9b` | `google/gemma-2-9b` | 9.2B | Gemma 2 (Google) | **SKIPPED 2026-07-12** — two weight-load deaths on the standard runner; revisit only with a larger runner | **B2** — scale universality (on hold) |
| `medgemma-4b-it` | `google/medgemma-4b-it` | 4.3B | MedGemma / Gemma 3 (Google, Health AI Developer Foundations) | Gated — HAI-DEF terms (owner accepted 2026-07-13 on the CI `HF_TOKEN` account) | Medical-tuned twin of `gemma-3-4b-it` (same base, same size): the paired contrast isolates what medical fine-tuning does to the colloquial-vs-clinical gap |
| `meditron3-8b` | `EPFLiGHT/Meditron3-8B` (was `OpenMeditron/Meditron3-8B`, which now HTTP-307-redirects here) | 8.0B | Meditron 3 / Llama 3.1 (EPFL), fine-tuned from `meta-llama/Llama-3.1-8B-Instruct` | Gated — Llama 3.1 license acknowledgment (owner signed 2026-07-17 on the CI `HF_TOKEN` account) | Medical-tuned, instruction-tuned 8B (C4 successor, owner 2026-07-17); 8B class: swap step and small chunks |
| `apertus-8b-meditronfo` | `EPFLiGHT/Apertus-8B-MeditronFO` | 8.1B | Apertus (Swiss AI) + MeditronFO medical tuning (EPFL), fine-tuned from an Apertus-8B instruct checkpoint | Ungated (Apache-2.0) | Medical-tuned, instruction-tuned 8B (C4 successor, owner 2026-07-17); 8B class: swap step and small chunks. **Upstream replaced the weights on 2026-10-06; the study stays pinned to the 2026-06-26 weights** (see below) |
| `gemma-4-e2b` | `google/gemma-4-E2B` | 5.1B stored (2.3B effective; per-layer embeddings plus vision and audio encoders), ~10.2 GB bf16 | Gemma 4 (Google), **base** (IT twin `google/gemma-4-E2B-it` not registered) | Ungated (Apache-2.0). **Awaiting limit-3 probe** | Post-registration exploratory addition (2026-10-09): newest Gemma generation as a base checkpoint, extending the `gemma-2-2b` → `gemma-3-4b-it` line. Loads as the full multimodal `Gemma4ForConditionalGeneration`; only the text stack runs |
| `qwen3.5-2b-base` | `Qwen/Qwen3.5-2B-Base` | 2.3B, ~4.5 GB bf16 | Qwen3.5 (Alibaba), **base** | Ungated (Apache-2.0). **Awaiting limit-3 probe** | Post-registration exploratory addition (2026-10-09): the suite's only true Qwen base (the Qwen3 entries are post-trained), with a new 248,320-entry tokenizer and a hybrid Gated-DeltaNet/attention architecture; first load of the `qwen3_5` path in CI |
| `medgemma-1.5-4b-it` | `google/medgemma-1.5-4b-it` | 4.3B, ~8.6 GB bf16 | MedGemma 1.5 / Gemma 3 (Google, HAI-DEF), **instruction-tuned** (no 1.5 PT exists) | Gated — HAI-DEF terms; the owner said on 2026-10-09 they will accept them on the CI `HF_TOKEN` account (acceptance may be per repository, so the `medgemma-4b-it` grant may not cover it). **Awaiting limit-3 probe** | Post-registration exploratory addition (2026-10-09): third medical-tune point on the Gemma 3 4B base beside `gemma-3-4b-it` and `medgemma-4b-it` |

The three 2026-10-09 additions are in the exploratory family (`docs/prereg_divergence_log.md`).
Their first fire is a limit-3 probe per model (protocol below), fired by a later session. Support in
`scripts/depth_probe.py` (interp-engine 1.5.1) and `scripts/activation_patch.py` (transformer_lens) is
unverified, and none is in `activation_patch.HF_IDS` or `backfill_planner.MODELS`. Reaching parity
with the existing models costs about 31 runner-hours per model (about 39 batch legs at roughly one
minute per pair, unmeasured for these three), on a lane that still had 125 of 390 cross-model legs
outstanding at the last coverage line in `ops/dashboard.json`.

The Gemma gate on Hugging Face is one shared license acknowledgement across `google/gemma*`
repos, so the acceptance already made for `google/gemma-3-4b-it` (the grant behind the
existing CI `HF_TOKEN`) very likely covers `gemma-2-2b-it` and `gemma-2-9b` — the limit-3
probe below confirms it either way.

## CPU runtime and chunking (7B/9B caution)

- 2–4B models run ~1 min/pair on the free public runners; a 120-pair batch is ~2 h,
  comfortably inside the workflow's 240-minute job timeout.
- **7B models (`meditron-7b`) are ~2–4× slower per pair on CPU** (~2–4 min/pair),
  so a full 120-pair run is ~4–8 h and will hit the timeout. CI fires for these two must use
  smaller chunks than the 2–4B models — set `limit` well under the timeout budget
  (≤ ~60 pairs to be safe). Full batches are covered in chunks via the `offset` trigger key
  (`scripts/logits_eval.py --offset`, part number = offset+1, wired 2026-07-10).
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
- **`medgemma-1.5-4b-it`** — open <https://huggingface.co/google/medgemma-1.5-4b-it> logged in as the `HF_TOKEN` account and accept the Health AI Developer Foundations terms before its probe; until then its leg fails with a gated-repo error.
- **`olmo-2-1b`** — ungated; nothing to accept. **`medgemma-4b-it`** — HAI-DEF terms, accepted by the owner 2026-07-13 (probe verified). **`meditron-7b`** — ungated on paper; the probe confirms.

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

1. **Official organization only.** All registry entries (eleven as of
   2026-07-13, including `epfl-llm` and the dropped-biomistral tombstone) resolve to
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
5. **Pinned revisions, enforced (since 2026-10-09).** Every load passes an exact
   40-hex commit SHA as `revision=` to both the tokenizer and the model, from
   `HF_REVISIONS` in `scripts/logits_eval.py`. The loaders refuse, with a named
   error (`UnpinnedModelError`, `RevisionMismatchError`) and a nonzero exit, to load
   a short id with no pin (the three tombstones), a repo id passed without
   `--revision <sha>`, a `--revision` that contradicts a registered pin, or a load
   whose resolved `_commit_hash` differs from the pin. A new model is pinned when
   it is added, to the commit its limit-3 probe will measure. Each summary records
   `inference.revision_pinned` beside the resolved `inference.revision`.
   (Until 2026-10-09 the pin was only recorded after the fact, and this item read
   "subsequent fires SHOULD pass that revision".)

## Pinned revisions

Every active model, with the commit its loads are pinned to. Each pin is the single
non-null `inference.revision` that model's landed logits summaries recorded
(`trace_out/*__<model>/batch_summary*.json`, and `trace_out/*/` for gemma-2-2b's logits
cross-check runs), so a new fire measures the same weights as the published numbers. No
model recorded more than one commit. Summaries written before revision capture began
(commit `100eac49`, 2026-07-12) carry no `revision` key; for each model that has them, the
pinned commit predates the study and is still the head of the repo's `main` on
2026-10-09, so those runs very probably loaded the same commit (inferred, not recorded).
Every pin was confirmed to exist on Hugging Face through the public
`/api/models/<repo>/revision/<sha>` endpoint on 2026-10-09; gated repos answer that
endpoint without authentication.

| Short id | HF repo | Pinned commit | Commit date | Summaries recording it (+ pre-capture, no key) | Head of `main` on 2026-10-09 |
|---|---|---|---|---|---|
| `gemma-2-2b` | `google/gemma-2-2b` | `c5ebcd40d208330abc697524c919956e692655cf` | 2024-08-07 | 14 (+6) | same |
| `gemma-3-4b-it` | `google/gemma-3-4b-it` | `093f9f388b31de276ce2de164bdc2081324b9767` | 2025-03-21 | 17 (+12) | same |
| `qwen3-4b` | `Qwen/Qwen3-4B` | `1cfa9a7208912126459214e8b04321603b3df60c` | 2025-07-26 | 14 (+9) | same |
| `qwen3-1.7b` | `Qwen/Qwen3-1.7B` | `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` | 2025-07-26 | 15 (+10) | same |
| `llama-3.2-3b` | `meta-llama/Llama-3.2-3B` | `13afe5124825b4f3751f836b40dafda64c1ed062` | 2024-10-24 | 20 | same |
| `olmo-2-1b` | `allenai/OLMo-2-0425-1B` | `a1847dff35000b4271fa70afc5db10fd29fedbdf` | 2025-05-28 | 19 | same |
| `gemma-2-2b-it` | `google/gemma-2-2b-it` | `299a8560bedf22ed1c72a8a11e7dce4a7f9f51f8` | 2024-08-27 | 19 (+1) | same |
| `medgemma-4b-it` | `google/medgemma-4b-it` | `290cda5eeccbee130f987c4ad74a59ae6f196408` | 2025-10-28 | 47 | same |
| `meditron3-8b` | `EPFLiGHT/Meditron3-8B` | `783c241b18b84692689e0336170b345e5732e48e` | 2026-06-25 | 104 | same (under both the old and the new org path) |
| `apertus-8b-meditronfo` | `EPFLiGHT/Apertus-8B-MeditronFO` | `ef2b141da7ccc347c2a13b2518370ba6a8a2b745` | 2026-06-26 | 102 | **no**: `dd868922fa74…` |

Models added after pinning was enforced are pinned when they are added, to the head of `main`
that day, read from the `sha` field of the public `https://huggingface.co/api/models/<repo>`
endpoint (which answered for the gated `medgemma-1.5-4b-it` without authentication). Their
limit-3 probes are the first loads at these commits:

| Short id | HF repo | Pinned commit | Repo last modified | Added |
|---|---|---|---|---|
| `gemma-4-e2b` | `google/gemma-4-E2B` | `d29ff6b45f081a49ee2733a859c9c9c2d95d1a6f` | 2026-07-15 | 2026-10-09 |
| `qwen3.5-2b-base` | `Qwen/Qwen3.5-2B-Base` | `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` | 2026-04-23 | 2026-10-09 |
| `medgemma-1.5-4b-it` | `google/medgemma-1.5-4b-it` | `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b` | 2026-04-13 | 2026-10-09 |

Tombstones (`biomistral-7b`, `meditron-7b`, `gemma-2-9b`) stay in `HF_IDS` as records,
have no pin, and are refused by every loader.

**The 2026-10-06 Apertus upstream change.** On 2026-10-06 `EPFLiGHT/Apertus-8B-MeditronFO`
committed `4409c940755421bb9b2e2e6ad8df48f52b02932f`, "Update weights to the ICLR run
(meditronfo_gptoss_v1 corpus)", followed by a model-card commit (`dd868922fa74…`). All 102
landed `apertus-8b-meditronfo` summaries measured `ef2b141d…` (2026-06-26). Before pinning
was enforced, the next fire would have loaded the new weights under the same short id. The
study stays on `ef2b141d…`; the new weights would be a new model with its own short id, which
is an owner decision, not a refresh.

**The Meditron3-8B move.** `OpenMeditron/Meditron3-8B` now redirects (HTTP 307) to
`EPFLiGHT/Meditron3-8B`; the registry names the new path. The pinned commit `783c241b…` is
the head of `main` at the new path, and the public API reports it under both paths. Nothing in
the engine or the site joins on `inference.hf_id`, so landed summaries keep the old string
and new ones record the new one.

**Activation patching and transformer_lens.** Activation patching (`scripts/activation_patch.py`) reads the
same pins for its four models and passes `revision` to transformer_lens as well; transformer_lens
3.5.1 forwards it to its one remaining Hugging Face read (a config lookup for non-Gemma, non-Llama
names), established by reading its source, not by a run.
