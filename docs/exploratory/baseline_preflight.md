# Original-model baseline parity preflight — prepared, not executed

Prepared 2026-10-15. This is independent of lens-fit provenance. A missing lens
revision prevents transport claims, but does not prevent comparing two unchanged
implementations of the study-pinned model. Passing this check would establish only
bounded numerical compatibility for one case, not a mechanistic interpretation,
clinical correctness, or general backend equivalence.

## Scope and predeclared engineering gates

`data/exploratory/baseline_preflight.v1.json` pins the existing reviewed, unsealed
one-case specification by SHA256. It uses exactly its two original prompts, with
no new wording, target annotation, selection, filtering, or fitting. It does not
change that source specification or its separate lens-provenance gates.

Model and tokenizer are `Qwen/Qwen3-4B` at
`1cfa9a7208912126459214e8b04321603b3df60c`. Both workers use raw prompt UTF-8
bytes, special tokens, no chat template, no thinking mode, no truncation, batch
size one, CPU bfloat16, SDPA, seed 7, eight threads, evaluation mode, frozen
parameters and deterministic algorithms. Inputs over 128 tokens refuse.

There are **six forwards**, sequentially, with only one model resident at a time:

1. The engine environment runs the unchanged `logits_eval.load_pinned` loader
   and legacy `model(input_ids).logits[0,-1]` expression on each prompt.
2. The same model runs each prompt with Causalab's prefill arguments: explicit
   all-one attention mask, zero-based positions, and `use_cache=False`.
3. The separate Causalab environment loads the same pinned safetensors, verifies
   tokenizer IDs against the engine capture, and runs the public v4 protocol
   through `ModelBundle.from_model`, `PytorchHooksEngine` and `run_protocol`.
   Its protocol reads the original `lm_head` over all input positions; the worker
   selects the final input position for the unchanged endpoint. Whole-sequence
   capture is necessary because Causalab optimizes a position-selected head read
   by skipping the head during the forward and projecting selected normalized
   states afterwards. The public all-position read preserves the original full
   forward. It has no writes, interventions, activation transport, or learned
   components.

This extra argument-parity check matters: the legacy engine leaves cache and
mask defaults implicit; Causalab supplies them. Both legacy-versus-aligned and
aligned-versus-Causalab comparisons must pass, separately for both prompts.
The final-normalization behavior is whatever the untouched model actually runs;
no lens unembedding, extra normalization, or inferred final layer is used.

Temporary read-only hooks observe the actual aligned forward's token IDs,
attention mask, position IDs, cache flag, batch size, and final output index in
both environments. Each receipt must match the declared complete single-row
input, and the saved final vector must exactly equal that forward's final output.
Hooks are removed on success and failure. The Causalab plain position frame is
also checked in full; dropping padding with `real_ids` is insufficient evidence
of matching masks. Comparison refuses missing or different input receipts even
when the saved logit vectors agree.

Transformers consumes the tokenizer's `revision` load argument instead of
retaining it in `init_kwargs`. The unchanged pinned loader still loads model and
tokenizer together. The worker resolves the pinned `tokenizer_config.json` from
the offline Hub cache, verifies its snapshot commit, and records its SHA-256.
Both captures must carry the same snapshot/config receipt; an absent snapshot
identity refuses rather than borrowing the model's reported commit.

All 151,936 output logits are retained. Full-vocabulary probabilities use a
stable softmax with the entire denominator. The comparator uses Python floating-point
arithmetic on saved logits, before the legacy export's four-decimal rounding; no
existing output is rewritten. The unchanged legacy target is the
first token of `tokenizer(target, add_special_tokens=False)`; the entire target
sequence remains recorded, without claiming sequence-level correctness.

Predeclared gates, all required:

| Comparison metric | Maximum difference |
|---|---:|
| Maximum absolute full-vocabulary logit difference | 0.125 |
| RMS full-vocabulary logit difference | 0.02 |
| Maximum absolute full-vocabulary probability difference | 0.001 |
| Original first-target-token probability difference | 0.0001 |
| Top-1 token identity | Must agree |

These are prospective engineering stopping rules, **not measured Qwen error
bounds**, a power calculation, or thresholds for a study claim. They reflect
that bfloat16 logit spacing is coarse while target-probability agreement is the
endpoint of interest. A failed rule stops subsequent lens/intervention work.
Do not relax it after observing this case; investigate precision, kernels,
versions, tokenization and argument behavior, then review a new protocol.
Token/model/revision/prompt/provenance mismatch, missing or nonfinite logits,
incomplete vocabulary, unexpected output shapes, leftover hooks, an unprepared
model, or missing code pins also fail closed. Zero differences are valid.

## Resources and cost before authorization

Use an owner-approved **existing Linux x86_64 CPU runner**, at least 64 GiB RAM,
8 logical CPUs, and 40 GiB free disk. No GPU, rented runner, paid provider call,
or fitting is required. The provider budget is **$0**; if existing runner quota
is unavailable, stop rather than purchase capacity. Neither runtime nor peak
memory for this real model has been measured by this preparation pass.

The pinned configuration implies 4,022,468,096 tied-embedding parameters:
8,044,936,192 bytes at bfloat16, before safetensors headers, tokenizer and config
files. This is a **derived download estimate**, not observed Hub transfer size.
Preview the exact pinned file list and sizes from Hub metadata before staging
weights; refuse if model files exceed 10,000,000,000 bytes or any size is unknown.
The 64 GiB runner requirement is a conservative envelope for loader/transient
allocations and two independent environments, not an assertion that inference
needs 64 GiB. Workers are sequential and release the process between loads.

Bound each worker to 900 seconds, including model loading from an already staged
cache; bound the whole job, including environment setup/download, to 60 minutes.
A timeout or OOM is a failed capacity preflight, not missing-at-random data.
Capture reports runtime including loading and Linux process maximum RSS. Outputs
are CI artifacts under `exploratory_methods/baseline_preflight/`, never committed
measurements and never names matching `batch_summary*` or `verify_summary*`.

The engine keeps its existing constraints, declaring the verified Linux CPU
distribution as Torch **2.13.0+cpu**, Transformers 5.14.1, Accelerate 1.14.0.
The CPU build suffix is retained in the plan, readiness record and runtime
metadata; it is never normalized away. Both isolated environments must pass an
exact distribution-version and Python-version check before any model download.
The engine constraints do not fully lock all transitive dependencies.
Causalab uses its own hash-locked base dependencies: Torch 2.9.0,
Transformers 5.16.1, Accelerate 1.14.0, plus the compiled extension. The difference
between stacks is part of what is being checked. Do not resolve one shared
installation, upgrade the engine environment, or substitute a wheel after a
lock failure. J++ is not installed or loaded by this preflight.

## Commands that are safe during local preparation

From the engine exploratory checkout, with the existing engine interpreter:

```bash
python scripts/exploratory_baseline_preflight.py
python scripts/exploratory_baseline_preflight.py --mode protocol \
  --out /tmp/exploratory_methods/baseline_preflight/original_protocol.json
python -m pytest -q tests/test_exploratory_baseline_preflight.py
ruff check scripts/exploratory_baseline_preflight.py tests/test_exploratory_baseline_preflight.py
```

Validation prints `prepared_not_executed` and execution prerequisites; it never
imports Torch, tokenizes prompts, or downloads anything. Protocol construction
writes an executable Causalab document but runs no model. Choose a fresh output
path: all writers refuse overwrites. Local `--mode capture` refuses `ci_only`
before importing a runtime. Do not spoof the CI environment to bypass it.

## Future CI commands — not authorized or run in this pass

The owner authorized preparing a **manual-only** route for this check on
2026-10-16. The narrowly scoped workflow and readiness gates are documented in
[baseline_ci.md](baseline_ci.md). This is an explicit exception for the prepared
preflight, not a new production trigger lane or permission to dispatch now.
Ordinary pushes/PRs cannot start its jobs. The committed readiness record remains
blocked: no suitable existing runner, established runner budget, reviewed Linux
setup, current seal attestation or final default-branch Causalab pin is supplied.

The workflow must first reach the engine's default branch through owner merge.
The model job accepts no arbitrary source SHA input: the engine is the exact
default-branch dispatch SHA, and Causalab is a full SHA from the reviewed readiness
record that must already be an ancestor of its owner fork's `main`. GitHub checks
that relationship before checking out the fork. Until the owner merges reviewed
code and separately authorizes execution, the draft PR heads remain review
artifacts, not runnable approvals. No merge or execution has occurred here.

After those prerequisites pass, the manual readiness helper writes the following
external execution record with actual full SHAs (the worker rejects placeholders)
and preserves it alongside the plan:

```json
{
  "schema_version": "patientwords.baseline-execution/1",
  "commits": {
    "engine": "REPLACE_WITH_FULL_REVIEWED_REMOTE_ENGINE_COMMIT",
    "causalab": "REPLACE_WITH_FULL_REVIEWED_REMOTE_CAUSALAB_COMMIT"
  }
}
```

The placeholders intentionally refuse. CI checks out precisely these commits;
each capture records its actual clean commit(s) and the execution-record digest.
The comparison requires these identities, exact package versions, a CI execution
label, no interventions, and no lens use. It rejects a different engine commit
between the two captures. Record full dependency freezes and hashes of
`constraints.txt`, `uv.lock`, `Cargo.lock`, the source specification, plan and
worker in the CI artifact. The current seal check must pass before execution; the old bundle attestation
is insufficient.

The CI preparation stage previews **only** pinned model/tokenizer files from
`https://huggingface.co/api/models/Qwen/Qwen3-4B/revision/1cfa9a7208912126459214e8b04321603b3df60c?blobs=true`,
checks the declared byte cap and disk budget, then stages safetensors weights,
`config.json`, `generation_config.json`, tokenizer JSON/config, vocabulary and
merges files. Exclude pickle weights and all unrelated artifacts. Keep the model
cache outside each repository and share it read-only between sequential workers.
The manual workflow implements this bounded staging path for review; it has
**not run**. Its reviewed-readiness and capacity gates precede all weight staging.

Once these prerequisites and authorization are satisfied, the exact worker steps
inside that CI job are below. `PW_ENGINE_PYTHON` and `PW_CAUSALAB_PYTHON` point to
the two independently pinned Python executables; `PW_ENGINE_ROOT` is the exact
engine checkout, and `PW_RUN_DIR` is a new directory under the external
`exploratory_methods/baseline_preflight/` namespace. The Causalab package must use an editable/source installation from the separately
checked-out pinned fork, with its compiled extension built in that installation.
Verify that `causalab.__file__` resolves inside that exact checkout before capture;
a wheel installed only under site-packages cannot establish its Git identity and
will refuse. The draft workflow prepares an editable installation using the
Causalab hash lock and existing pinned Rust toolchain; the Linux runtime review
remains blocked. The actual CI environment supplies `GITHUB_ACTIONS=true`; do not set it by hand locally.

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
cd "$PW_ENGINE_ROOT"
timeout --signal=TERM --kill-after=30s 900s "$PW_ENGINE_PYTHON" \
  scripts/exploratory_baseline_preflight.py --mode capture --backend engine \
  --execution "$PW_EXECUTION_RECORD" --out "$PW_RUN_DIR/engine.json"
timeout --signal=TERM --kill-after=30s 900s "$PW_CAUSALAB_PYTHON" \
  scripts/exploratory_baseline_preflight.py --mode capture --backend causalab \
  --execution "$PW_EXECUTION_RECORD" --engine "$PW_RUN_DIR/engine.json" \
  --out "$PW_RUN_DIR/causalab.json"
"$PW_ENGINE_PYTHON" scripts/exploratory_baseline_preflight.py --mode compare \
  --execution "$PW_EXECUTION_RECORD" --engine "$PW_RUN_DIR/engine.json" \
  --causalab "$PW_RUN_DIR/causalab.json" --out "$PW_RUN_DIR/comparison.json"
```

The worker refuses a non-Linux or undersized host and requires offline-cache
mode before loading weights. The draft manual workflow additionally checks its container/cgroup memory and
CPU allocation, enforces timeouts, stages the exact cache, uses shell failure
propagation, and uploads partial receipts/logs on failure when the runner remains
available. It does not continue after a failed capture or comparison.

After this smallest preflight passes, the next numerical experiment is the
unprocessed TransformerLens residual baseline on these same frozen inputs.
That third implementation is intentionally deferred, not claimed covered by a
two-stack output check. Lens transport still waits for sufficient historical
fit provenance; native residual baselines can proceed independently after review.

## Offline installation smoke for the public protocol

`tests/manual/baseline_protocol_smoke.py` tests the same builder against random
tiny Qwen3 weights and an abstract local tokenizer, with Hub offline mode. Run
it from an external working directory with the isolated installed Causalab Python:

```bash
/private/tmp/pw-methods-causal-venv/bin/python \
  /Users/michaelgreen/patientwords-engine-exploratory/tests/manual/baseline_protocol_smoke.py \
  --out-root /tmp/new-installation-check/installation_checks/baseline
```

The output path must be new and outside repositories. The actual completed smoke
passed both exact-output comparisons and hook cleanup. The original installation
receipt is in [local_preparation_20261015.md](local_preparation_20261015.md); the
whole-sequence refinement and final test inventory are in
[review_preparation_20261016.md](review_preparation_20261016.md). It demonstrates
protocol wiring on synthetic inputs, not released-model baseline parity.
