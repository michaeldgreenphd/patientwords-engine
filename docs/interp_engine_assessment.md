# interp-engine assessment (Phase 0)

Written 2026-09-02 against `michaeldgreenphd/patientwords-interp-engine` at commit
`74716092`, package version **1.5.1**, Apache-2.0. This answers the Phase 0
questions in the integration plan. Every claim below was checked by reading the
cloned repo; the two places where a claim could not be checked are marked
UNVERIFIED and say why.

Upstream is `decoderesearch/interp-engine`; this clone is the owner's fork.

## Summary

interp-engine is an **inference and capture engine**, not a circuit tracer. It
reads and writes activations at 34 standardized points across architectures, with
four backends. The headline vLLM speed story needs CUDA and does not apply to us,
but the **eager backend runs on CPU and serves all 34 points**, which is the arm
that matters for PatientWords.

Three of the plan's four opportunities survive contact with the repo. The fourth
changes shape:

- Phase 1 (hosted-migration audit) stands, unchanged and still first.
- Phase 2 (validator cross-check) stands, and is stronger than the plan assumed:
  the eager backend is a legitimate independent implementation, and interp-engine
  publishes a comparison methodology we can borrow rather than invent.
- Phase 3 (standardized hook points) stands, with one design change: patching by
  activation *replacement* has no first-class API, so it must be expressed as an
  additive delta or via the eager `HookManager`.
- Phase 4 (circuit tracing beyond gemma-2-2b) is **not served by this repo**.
  There is no attribution-graph or transcoder code here at all. interp-engine
  helps that goal only by naming the correct hook point to read a transcoder at,
  which turns out to matter more than it sounds (§7).

## 1. Backend and hardware

**Backends** (`load_model(..., backend=...)`, `interp_engine/load.py:53`):

| backend | hardware | serves |
|---|---|---|
| `eager` | CUDA, MPS, **CPU** | all 34 points, gradients, raw logits |
| `vllm` (default) | CUDA only | 28 points, chosen per request |
| `vllm-static` | CUDA only | only points declared at load; 4x-11x decode |
| `vllm-generate` | CUDA only | generation only; capture and steering refuse |

`backend="auto"` runs a ladder: hooked vLLM on CUDA for a supported
architecture, otherwise **eager on CUDA, MPS or CPU**. An explicitly requested
non-CUDA device forces eager by design (`select.py:148`), so
`load_model(hf_id, backend="eager", device="cpu", dtype="bfloat16")` is the
call for our CI.

**Install footprint.** The base install is CPU-clean:

```
pip install interp-engine          # eager backend only
pip install 'interp-engine[vllm]'  # adds vLLM, Linux/CUDA only
```

Base dependencies are `torch>=1.10`, `transformers>=4.57.1`, `einops`,
`numpy>=1.24`. vLLM is an optional extra, imported lazily, deliberately kept out
of the base deps so "the EagerModel core must install on macOS/CPU"
(`pyproject.toml`). Nothing about the base install needs CUDA.

**Version compatibility with `constraints.txt`:**

| we pin | interp-engine wants | verdict |
|---|---|---|
| torch 2.13.0 | `>=1.10` | compatible |
| transformers 5.14.1 | `>=4.57.1` | compatible |
| numpy 2.4.6 | `>=1.24` | compatible |
| Python 3.11 (CI) | `>=3.11,<3.14` | compatible |
| `pyproject.toml` `python = "^3.10"` | `>=3.11` | **conflict on 3.10** |

The last row is the only friction: our package declares 3.10 support. CI runs
3.11 so nothing breaks today, but the new dependency should be declared in an
extra (e.g. `[validate]`) rather than the base deps, so a 3.10 install of the
engine still resolves.

`einops` is a new transitive dependency and must be added to `constraints.txt`
with the version CI resolves, per the one-commit-per-bump policy.

**UNVERIFIED: no empirical install.** `pip install interp-engine` in a throwaway
venv here exhausted this container's disk allowance while downloading the torch
wheel (`OSError(28)` at ~1.4 GB free), and the dev container has no system torch.
So the CPU install and a CPU forward pass have **not** been executed. Both must
be proven in CI before anything downstream is trusted. This is also a real
warning about CI disk: `logits_evaluation.yml` already installs torch and
transformers, so adding interp-engine on top is small, but a *separate* lane with
its own venv would pay the whole torch download again.

## 2. Model coverage

interp-engine has **no model registry and no aliasing**: the identifier is the
raw HF repo id, which matches how `HF_IDS` already stores them.

Its validator publishes cross-engine results per model. Six of our ten claim-grade
models are directly validated:

| our id | HF id | in validator |
|---|---|---|
| gemma-2-2b | google/gemma-2-2b | yes |
| gemma-2-2b-it | google/gemma-2-2b-it | yes |
| gemma-3-4b-it | google/gemma-3-4b-it | yes |
| olmo-2-1b | allenai/OLMo-2-0425-1B | yes |
| qwen3-1.7b | Qwen/Qwen3-1.7B | yes |
| qwen3-4b | Qwen/Qwen3-4B | yes |
| medgemma-4b-it | google/medgemma-4b-it | no (Gemma-3 arch covered by gemma-3-4b-it/-pt) |
| llama-3.2-3b | meta-llama/Llama-3.2-3B | no (Llama-3 arch covered by Llama-3.1-8B) |
| meditron3-8b | OpenMeditron/Meditron3-8B | no (Llama-3.1-8B based per `logits_eval.py`) |
| apertus-8b-meditronfo | swiss-ai/Apertus-8B lineage | no, and no Apertus entry at all |

Architecture coverage is therefore complete for nine of ten by family, with
apertus-8b the single unknown. That is a question to answer empirically, not from
the table.

For `gemma-2-2b` specifically, the validator records interp-engine eager as the
reference and **TransformerLens v2 and v3 both agreeing on every compared point**
(36 points, cosine ~1.0, `max_abs_diff` ~5e-06). That is direct evidence our
`activation_patch.py` transformer-lens path is not wrong on our primary model.

## 3. API surface

Everything below is a top-level `interp_engine` export, which the project defines
as its API surface.

**Async by default, with a sync escape hatch.** Every model *method* is async,
including on eager. Sync free functions (`run_with_cache`, `capture_generation`,
`capture_attention`, `generate_stream`, `steer`, `layer_logits`) take either
backend, and `sync_model(model)` mirrors the whole protocol. Our scripts are
synchronous, so they use the free functions or `sync_model`. Neither can be
called from inside a running event loop; they refuse rather than deadlock.

**Next-token distribution** (what `logits_eval.py` needs). Two routes:

- `generate_stream(model, tokens, max_tokens=1, n_logprobs=k)` yields a
  `GenStep` carrying `.logprobs` and, on eager only, `.logits`. `n_logprobs` is
  honored on both backends; `.logits` is `None` on vLLM.
- Capture `resid_post.<last layer>` and call `decode_residuals`.

Route one is the closer match to our `measure()`, which takes a full softmax and
`torch.topk`. Our greedy multi-token `continuations` map has a direct equivalent
in `generate_text` / `generate_stream` with `temperature=0.0`.

**Capture.** `run_with_cache(model, tokens, ["resid_post.10"])` returns a `Cache`;
`await model.capture(token_ids, points)` returns a plain dict keyed by `Address`
objects (not strings). Shapes are `[n_prompt_tokens, width]`, on CPU, with no
batch dimension, on either backend.

**Hook-point translation.** `tlens_hook_to_point` and `point_to_tlens_hook` map
both directions. Our `blocks.<layer>.hook_resid_post` maps to `resid_post.<layer>`
cleanly. **This is not true of every hook name we might add** — see §7.

**Writes and patching.** The steering API is `AddSpec`, `ProjectionCapSpec` and
`OrthogonalDecompSpec`, applied at a layer's `resid_post`, with `PositionMask`
for position scoping. There is **no `ReplaceSpec`**: nothing in the public API
overwrites an activation with another one, which is exactly what
`patch_and_measure` does.

Two workable routes, in preference order:

1. **Additive delta.** Capture the corrupt run's activation at the position,
   capture the clean run's, and apply `AddSpec(vector=clean - corrupt, scale=1.0)`
   with a `PositionMask` on that position. Arithmetically identical to
   replacement. Costs one extra forward pass per pair (the corrupt capture),
   which we already run.
2. **Eager `HookManager`.** `interp_engine.HookManager` is exported and
   `hooks.replace_hidden` exists, giving a transformer-lens-style
   `run_with_hooks`. Lower level, eager-only, and closer to the current code.

Route 1 is backend-portable and uses only public API; route 2 is a smaller diff.
Either way the output schema is unchanged.

**Lens.** `lens.py` is titled "Logit + Jacobian-lens read-out" and
`layer_logits(model, tokens, layers_by_type, transport=...)` returns per-lens-type,
per-layer logits in one forward pass. The critical constraint is in its docstring:

> Fitting the transport matrices is an offline job that lives outside this
> package (e.g. the `jlens` fitter); the server only *applies* pre-fitted lenses
> here.

So **logit lens is fully reproducible locally; Jacobian lens is not**, because
the fitted transport matrices for gemma-2-2b are not in this repo. Neuronpedia's
hosted endpoint stays the only source of our registered Jacobian-lens instrument.
Our `jlens_readout.py` already carries `LOGIT_LENS` as a comparison arm
(referee item 7); that arm, and only that arm, can be reproduced locally.

**Provenance for the `environment` block.** `interp_engine.__version__` is
readable, and the validator's own result files record
`{interp_engine: {version, commit}, torch: {version}, transformers: {version}}`
plus device and dtype. That is the shape to copy into our summaries.

## 4. Validator

`validator/` compares interp-engine against TransformerLens v2/v3 and
nnsight/nnterp across 50+ models. Its methodology is directly reusable:

- Agreement is judged against the raw-HF eager reference by **cosine** for
  direction plus a **relative-error** gate for magnitude, because cosine alone
  cannot see a constant scale factor. Raw-HF pairs get a tight absolute tolerance
  instead. A cosine below 0.5 hard-fails in every tier.
- Per-point records carry `cos`, `cos_worst_token`, `max_abs_diff`, `rel_diff`,
  `rel_worst_token`, `worst_token`, `status`, `tier`.

Two caveats for us:

1. **It compares activations at hook points, not next-token probabilities.** Our
   published claim is about probabilities, so a Phase 2 cross-check has to be
   written by us; we borrow the metric vocabulary, not the harness.
2. **Running their sweep needs a CUDA box and three venvs** (`validator/README.md`,
   "How to run"). We are not running their sweep. We are running the eager
   backend on CPU against our own stimuli.

## 5. Hosted Neuronpedia migration

**UNVERIFIED.** Nothing in this repo names the date Neuronpedia's hosted API
switched to interp-engine, and the release post gives no date either. The repo
confirms the relationship ("powers all of Neuronpedia's inference") but not the
timing. Phase 1's first task is therefore unchanged and now has a second source
to check: the Neuronpedia changelog or API docs, plus our own drift-sentinel
series, which is the only record we control that would show a backend change as a
step in the pinned baseline.

One additional signal is now available: the validator's `gemma-2-2b` results are
dated 08/11-08/19/26, and our Neuronpedia graph outage ran 2026-08-22 to 25. The
proximity is suggestive of a deployment window and worth checking, but it is not
evidence on its own.

## 6. Licence and provenance

Apache-2.0 (`LICENSE`, `pyproject.toml:6`), compatible with both public repos.
Any published number derived from it must name the engine and version in its
provenance, per the site's every-number-traces rule.

## 7. The finding that changes how we read transcoders

`docs/PORTING.md` and `docs/ENGINE_HOOK_MAPPINGS.md` document a trap that lands
squarely on our primary model. TransformerLens has two names for the MLP output
and they are different tensors:

| TransformerLens | canonical | what it is |
|---|---|---|
| `blocks.{i}.mlp.hook_out` | `mlp_out` | raw module output, every architecture |
| `blocks.{i}.hook_mlp_out` | `mlp_out` *or* `mlp_out_post` | the residual **contribution** |

They differ only on post-sublayer ("sandwich") norm architectures, which is
**Gemma-2/3/4 and OLMo-2/3** — that is gemma-2-2b, gemma-2-2b-it, gemma-3-4b-it,
medgemma-4b-it and olmo-2-1b, five of our ten. interp-engine measured the
consequence: on `gemma-2-2b` layer 4, `gemmascope-mlp-16k` reconstructs
`mlp_out_post` at FVU 0.26 (L0 81 against a declared 85), and raw `mlp_out` at
FVU 9.8 with L0 8 — worse than predicting the mean. Their words: a source read
off `mlp_out` "is not merely noisier, it is dead".

We do not read transcoders ourselves; Neuronpedia's hosted circuit-tracer does,
and our `clinical_mass` is computed from the features it returns. So this is not
a bug in our code. It is worth recording for two reasons: it is a concrete
mechanism by which a hosted-backend change could move our feature-derived
numbers without moving our probabilities, which is exactly the question the
handbook's outage case law says to ask the vendor; and if Phase 4 ever adds a
transcoder source set of our own, this is the trap to check against both
candidates first.

## 8. Revisions to the integration plan

1. **Phase 2 scope.** Write our own comparison against our own stimuli using the
   validator's metric vocabulary (cosine + relative error + worst-token). Do not
   try to run `validator/comparison/run_all_models.sh`; it needs CUDA.
2. **Phase 3 design.** Patching is an additive delta with a `PositionMask`, or the
   eager `HookManager`. Budget one extra forward pass per pair for the delta route.
3. **Phase 4 is out of scope for this repo.** interp-engine contains no
   attribution-graph or transcoder machinery. Chasing a second graphed model still
   means circuit-tracer plus a transcoder set, with interp-engine contributing only
   the correct hook point. Re-gate that phase on Phase 1's hosted probe, not on
   anything here.
4. **New sub-item under Phase 1.** The Jacobian-lens transport matrices are not
   public. Our registered depth instrument therefore has a single hosted supplier
   and no local fallback. That is a study risk worth one line in the methods
   limitations and one question to the vendor.
5. **Dependency hygiene.** Declare interp-engine in an optional extra, not base
   deps (our floor is Python 3.10, theirs is 3.11), and add `einops` to
   `constraints.txt`.
6. **Pin `interp-engine~=1.5`.** The API is settled but not frozen: 1.1 and 1.3
   both changed signatures in a minor version, with no deprecation aliases. Note
   also that `docs/AGENT_INTEGRATION.md` still stamps itself 1.3.x while the
   package is 1.5.1, so that document may lag the code.

## 9. What Phase 1 needs, restated

Unchanged from the plan and still the first thing to do, because it is free, it
does not depend on any of the above, and it is the only item with a shelf life:

1. Annotate the drift sentinel with the backend-migration date once found.
2. Compare sentinel verdicts either side of it; log a divergence entry if the
   pinned baseline moved.
3. Re-run the `docs/cross-model.md` probe on the non-gemma MODEL_REGISTRY entries
   through `scripts/fire_trigger.py`, then re-park the lane.
4. Re-run the j-lens sentinel for the same reason.

## 10. Open questions

- The exact date Neuronpedia's hosted API moved to interp-engine.
- Whether the hosted circuit-tracer now serves models it 500'd on 2026-07-07.
- Whether apertus-8b's architecture loads on the eager backend.
- Whether a CPU eager forward on a 4B model finishes inside the existing CI
  timeouts. The vLLM speed numbers say nothing about this; only a run will.
- Whether the fitted Jacobian transports are obtainable, or whether that
  instrument is permanently vendor-only.
