# Scaling plan, 2026-11-10

Written 2026-11-10 against engine base `d8d0855d` plus the working tree of the 2026-11-10
change set. Paths are relative to the engine root.

**Answer first.** The current system can carry a larger study without a new service. What
limits it today is not compute. It is that no landed measurement records how long it took or
how much memory it used, that a re-fired chunk can overwrite a longer landed part, and that
the CPU lane runs at about 213 pair-by-model measurements a day in its scheduled form. The
plan below keeps push-to-run CI, the journal, the budgets and the single-writer rules, and
adds eight things in order. Three of them exist as offline code in this change set
(`scripts/experiments/`). None has run against a real model.

Every number in this document carries one of three labels:

- **[M] measured**: read from a committed artifact or timed in this session; the source and
  sample size are given.
- **[D] derived from measured**: arithmetic on [M] values; the arithmetic is shown.
- **[A] assumption**: chosen for the estimate; not observed.

Nothing here is a throughput, memory, price or duration that was not read or computed from a
named source. Where a quantity is not recorded, the cell says so.

## 1. What is measured today

No `trace_out/*/batch_summary*.json` part carries an elapsed-time, memory or cost field. A
walk of all 1,235 parts for timing-shaped key names found none (verified for this document by
listing the top-level and `inference` keys of sampled parts; the full walk is the mapping
pass of 2026-11-10). Runtime evidence therefore comes from journal timestamps, commit
timestamps, constants transcribed into code, and timings taken in this session.

| Quantity | Value | Label | Source and sample size |
|---|---|---|---|
| CPU-logits seconds per pair, slowest successful run, model load included | gemma-3-4b-it 160.6, qwen3-4b 155.8, llama-3.2-3b 129.4, gemma-2-2b-it 88.5, qwen3-1.7b 67.2, olmo-2-1b 44.0 | [M] | `scripts/backfill_planner.py` `SECONDS_PER_PAIR`; `RATES_SOURCE`: duration of the "Measure next-token behavior" step over the pairs the trigger asked for, runs up to 2026-10-09. The number of runs behind each value is not recorded. |
| The same, medians | 94, 76, 69, 79, 33, 37 s/pair in the same model order | [M] | `RATES_SOURCE` text only; not machine-readable; sample size not recorded. |
| First-probe rates of the 2026-10-09 models | gemma-4-e2b about 5 s/pair; qwen3.5-2b-base about 60; medgemma-1.5-4b-it about 120 | [M] | `docs/model_matrix.md` rows; run 37960095244; 3 pairs per model, one run. |
| Weight download and load in that probe | about 70 s (gemma-4-e2b, 1,951 tensors), 19 s (qwen3.5-2b-base, 320 tensors), 31 s (medgemma-1.5-4b-it, 883 tensors) | [M] | `docs/model_matrix.md`; one load each. |
| 8B-class rate | about 2 to 4 min/pair | [M], coarse | comment in `scripts/backfill_planner.py:71`; sample size not recorded. |
| No recorded rate | gemma-2-2b, medgemma-4b-it on the CPU lane | not recorded | `SECONDS_PER_PAIR` has six models; neither is among them. |
| Scheduled backfill leg, wall minutes (plan, matrix, resolve) | median 62.7, min 11.1, max 177.1 | [M] | `ops/trigger_journal.jsonl`, `fired_utc` to `resolved_utc` of the 53 clean `[scheduled_runner]` legs of 54, 2026-10-12 to 2026-11-10. Recomputed for this document. |
| Scheduled lane output | 6,185 pair-by-model measurements requested in 29.1 days; 212.5 a day | [M] count (mapping pass), [D] rate: 6,185 / 29.1 | same 54 legs. |
| Same leg shape, spread | 50 pairs x 2 models: 17.5 to 85.9 min over 12 legs | [M] | mapping pass of 2026-11-10 from the journal; not recomputed here. The cause of the factor of about 5 is not recorded anywhere. |
| Results per part | logits: median 25, max 350 (628 parts, 25,870 results); hosted: median 5, max 20 (575 parts, 3,425 results); activation patching: median 3, max 5 (32 parts, 94 results) | [M] | all 1,235 parts, recomputed. |
| Parts per run directory | median 1, max 30, over 592 directories | [M] | recomputed. |
| Summary part size | median 33.8 kB, 10th percentile 7.6, 90th 143.6; 80.8 MB in total | [M] | `os.path.getsize` over 1,235 parts, recomputed. |
| Bytes of JSON per result | logits 2,579; hosted 3,438; activation patching 24,824 | [D]: bytes / results | same parts. |
| Hosted render size | `index_NN.html` median 1,177.7 kB (n = 3,154); `index_NN_diff.html` 1,160.3 kB (n = 2,682); `index_NN*.png` 2,262.8 kB (n = 472) | [M] | recomputed. |
| `trace_out/` | 8,375 MB of file bytes (7.9 GiB by `du`), 15,653 files, all tracked; HTML renders are 7,057 MB of it | [M] | `os.path.getsize` over every file, recomputed. |
| Hosted lens raw file | median 14.9 kB (n = 7,605) | [M] | recomputed. |
| Render archives | 40 manifests; 15.15 GB of zip bytes recorded | [M] | `render_archives/*.manifest.json`, field `zip_bytes`, summed. |
| Results catalogue export | 2.4 and 2.5 s wall with writes (2 runs: 519 files, 15,865,405 bytes); 1.9 to 2.4 s as a dry run (3 runs); peak RSS 77 MB | [M] | `scripts/export_results_catalogue.py` over 747 runs and 1,235 parts, timed in this session on a 4-CPU development container. The integrator's earlier figure for the same export was about 3 s. Not a CI-runner figure. |
| Open-results migration dry run | about 75 s | [M], reported | `docs/open_results_migration_20261110.md`, same container. Not re-run for this document. |
| Offline test suite | 712.06 s wall for 6,506 passed, 4 failed, 20 skipped | [M] | baseline run of this session before the change set, same 4-CPU container. One run. |
| Hosted tracing, July 2026 | 342 pairs in 90.7 h elapsed, 49.5 h of it idle; 8.3 pairs per productive hour | [M], historical | `docs/audits/timing_forensics_20260727.json` `result.timeline.totals`. Under a 75-minute job ceiling; the ceiling is 300 minutes now. |
| Activation patching | about 10 to 15 min per pair on gemma-2-2b, about 260 forward passes | documented estimate | `.github/workflows/activation_patching.yml:128`, `docs/activation_patching_design.md:213`. No landed part records a duration. |
| Standard runner memory | 15 GiB physical, 14 GiB available | [M] | one job, `docs/exploratory/baseline_ci.md` (job 115307894442, 2026-10-13). The logits workflow adds a 12 GB swap file. |
| Paid generation cost per accepted pair | haiku $0.0017, opus $0.020, sonnet $0.060 | [M] | `docs/triggers.md`, landed sidecars as of 2026-09-04. |
| Journal | 1,225 rows; 1,045 resolved; 0 evicted; 180 neither | [M] | `ops/trigger_journal.jsonl`, recomputed. |

### Not measured

| Quantity | Why it is missing | How it would be measured |
|---|---|---|
| Model load versus inference split | The recorded rates are one step's duration over all pairs, load included. Only three first-probe loads are separated. | Time the load call and the pair loop separately in `scripts/logits_eval.py` and write both to the part's `inference` block. |
| Tokenization time and token counts | No result records `n_tokens`. Every activation estimate below depends on it. | Record `n_tokens` per prompt in each result. Tokenization time only if the load and inference split shows unexplained time. |
| Peak memory | No part records RSS. The 9B load failures are known only from exit code 137. | `resource.getrusage` maximum RSS at the end of each cell, written beside the timing. The baseline preflight already plans this for its one case. |
| Capture cost | The CPU lane keeps no activations. | First real capture run: bytes written and seconds per prompt, per layer count. |
| Fitting cost | Nothing in the engine fits anything. The ICA Lens documentation reports one run on other hardware (section 2). | First fit on project hardware: seconds per iteration, peak RSS, rows and width. |
| Intervention cost | Only the documented estimate above. | Per-pair duration and forward count in the patching summary. |
| Grading time | Paid lanes record tokens and cost, not seconds. | Wall seconds per judgment in the judge sidecar. |
| Rendering time | Rendering happens inside the tracing job. | Step-level timing in `medlang_circuits/batch_eval.py`. |
| Git and artifact transfer | Clone, checkout and push durations are not recorded; runner free disk is not recorded. | Step durations from the Actions API per run; `df` at job start. |
| Queue delay | The scheduled leg's reserve commit lands a median 327 min after the cron time (n = 54, mapping pass); the cause is not in any artifact. | Compare `run.created_at` and `run.run_started_at` from the Actions API. |
| Failure and refusal rate per lane | The journal marks resolution, not outcome. 1 of 54 scheduled legs carries `[failure]`. | An `outcome` field on the journal row at resolve. |

## 2. Stage separation

| Stage | Current mechanism | Limit evidence | Profile first |
|---|---|---|---|
| Model loading | `scripts/logits_eval.py` `load_pinned`: transformers, bfloat16, `low_cpu_mem_usage=True`, pinned revision, once per matrix cell. interp-engine eager for `depth` and `verify`. transformer_lens for patching. | 8B jobs are described as weight-load dominated (`scripts/backfill_planner.py:79`). gemma-2-9b died twice at load (`docs/model_matrix.md`). The share of a normal cell spent loading is unknown. | Load seconds and peak RSS per cell. |
| Tokenization | The tokenizer loads with the model at the same pin. One unpadded prompt per call. | Unknown. No field records it. | Token count per prompt, because storage estimates need it. |
| Inference | One forward per prompt; the legacy endpoint reads the final-position logits and the first target token's probability. | The per-pair rates in section 1. The same leg shape varies by a factor of about 5 with no recorded cause. | Seconds per forward with load excluded, with the runner image and CPU model recorded. |
| Capture | Hosted lens raw responses; interp-engine `layer_logits` in depth mode; transformer_lens hooks in patching. No lane stores residual activations. | Unknown. | Bytes and seconds per prompt at the first capture run. |
| Fitting | None in the engine. | Unknown on project hardware. The ICA Lens documentation reports, for a 9B model at width 4,096 with 1 million tokens on one GPU system: capture 50 min 57 s for 32 layers, covariance 1 min 25 s per layer, 50 iterations in 12 min 44 s per layer. That is another model on other hardware and is not a project measurement. Its fit CLI requires CUDA; the Python API is the CPU route (the mapping pass's reading of the source; not run). | Seconds per iteration and peak RSS for one layer at the project's width. |
| Intervention | `scripts/activation_patch.py`: one extra forward per layer and position. Hosted steering through the Neuronpedia API. | Documented estimate of 10 to 15 min per pair. The script writes nothing until the chunk ends, so a timeout loses the chunk. | Seconds per forward; add a per-pair flush before any long grid. |
| Grading | Judge calls in the advice and Petri lanes. | Cost is recorded; time is not. | Seconds per judgment. |
| Rendering | Hosted 2-panel HTML, about 1.2 MB per file, two per pair. | HTML renders are 84% of `trace_out/` bytes ([D]: 7,057 / 8,375 MB). Time unknown. | Bytes per pair by render kind; step timing. |
| Export | Publish chain scripts over landed summaries. | Catalogue 2.5 s, migration dry run 75 s on a development container. Not a limit today. | Nothing until part count grows tenfold. |
| Git and artifact transfer | Every part and render is a tracked file. Commit steps rebase and push with five retries. The scheduled workflow clones the whole repository in every job; the push-fired logits workflow uses a blobless sparse checkout. | Pack size 1.8 GB in a shallow clone. Runner free disk is not recorded, so the margin is unknown. | Checkout seconds and free disk per job; then move the scheduled workflow to the sparse checkout. |

The first profile to take is the cheapest and resolves the most: load seconds, loop seconds,
peak RSS and token counts written into each new part. It needs no new lane. It is a change to
`scripts/logits_eval.py` and its tests, and it changes the part's shape, so it needs the
contract check in `verify.md`.

## 3. Estimates for three grid sizes

The formulas are code: `scripts/experiments/planner.py` (`estimate_activation_bytes`,
`estimate_fit_bytes`) and `scripts/experiments/estimate.py` (time, logits storage, weights).
`python -m scripts.experiments.estimate --help` prints a grid's numbers as JSON. The tests in
`tests/test_experiments_estimate.py` check the arithmetic on toy inputs. They are not
evidence about any model.

### 3.1 CPU-logits time

Formula:

```
pair_equivalents = case_families x replicates x prompts_per_family / 2
attempted        = ceil(pair_equivalents x (1 + failed_attempt_fraction))
runner_seconds   = sum over models of attempted x seconds_per_pair(model)
legs(model)      = ceil(attempted / floor(7200 / seconds_per_pair(model)))
```

Stated assumptions:

- [A] Time scales with the number of prompts. A family with clinical and colloquial variants is
  one pair; adding a normalized variant makes it 1.5 pairs.
- [A] `failed_attempt_fraction` = 0.15. Reference points, neither of which is a failure rate:
  1 of 54 scheduled legs failed (1.9%, [M]); 180 of 1,225 journal rows ended without a
  resolve (14.7%, [M]), which mixes expiry, parks and failures.
- [M] The rates are for the legacy first-token endpoint on the CI runner and include model
  load, as their source says. A lens, capture or intervention run is not covered by them.
- The six models are the ones with a recorded rate. Sum of slowest rates: 160.6 + 67.2 + 155.8
  + 129.4 + 44.0 + 88.5 = 645.5 s per pair across the six. Sum of medians: 94 + 33 + 76 + 69 +
  37 + 79 = 388.
- 7,200 s is half the 240-minute job timeout, the rule `scripts/backfill_planner.py` sizes legs
  with ([M], `HALF_TIMEOUT_S`).
- The first-token read is deterministic on one runner, so a replicate here measures runner
  and software variation, not sampling variation. It is still a separate run with its own id.

| Grid | Families x models x replicates, prompts per family | Pair-equivalents per model, attempted | Runner hours, slowest rates | Runner hours, median rates | Model-legs (slowest) |
|---|---|---|---|---|---|
| Small | 20 x 6 x 1, 2 | 20, 23 | 23 x 645.5 = 14,847 s = 4.1 h | 23 x 388 = 8,924 s = 2.5 h | 6 |
| Medium | 200 x 6 x 1, 3 | 300, 345 | 345 x 645.5 = 222,698 s = 61.9 h | 345 x 388 = 133,860 s = 37.2 h | 35 |
| Larger | 2,000 x 6 x 2, 3 | 6,000, 6,900 | 6,900 x 645.5 = 4,453,950 s = 1,237 h | 6,900 x 388 = 2,677,200 s = 744 h | 627 |

All cells are [D] from the [M] rates under the [A] assumptions above.

Runner hours are not wall time. Three things sit between them, none of them modelled:

- Parallelism. The logits lane runs 2 cells at a time and the scheduled workflow 3
  (`max-parallel`, [M]). The lane holds one running and one pending run.
- Queueing and setup. The planner's own campaign table assumes about 90 s per cell for setup
  and load (`docs/model_matrix.md`, [A] there). Queue delay is not measured.
- Observed lane output. At the scheduled lane's 212.5 measurements a day ([D]), the larger
  grid's 6,900 x 6 = 41,400 measurements are 195 days, the medium grid's 2,070 are 9.7 days,
  and the small grid's 138 are under one day. This assumes the same leg shapes and the same
  twice-daily cron, so it is a description of today's schedule, not a capacity limit: the
  runner-hour figure for the larger grid at 2 cells in parallel is 1,237 / 2 = 619 h, or 26
  days of an always-busy lane.

Reading: the small grid fits the existing lane in a day. The medium grid fits in one to two
weeks. The larger grid does not fit a twice-daily schedule in a useful time, and the first
remedy is a denser schedule on the same lane with measured rates, not new infrastructure
(section 7).

### 3.2 Activation storage

Formula (`estimate_activation_bytes`):

```
activation_bytes = captured_positions x layers x hidden_size x bytes_per_value
bytes_per_value: float16 and bfloat16 2, float32 4, float64 8
```

Widths and depths recorded locally:

| Model | hidden_size | layers | Source | Bytes per token, all layers, float32 |
|---|---|---|---|---|
| qwen3-4b | 2,560 | 36 | `data/exploratory/method_sources.v1.json` `model_config`; `data/exploratory/qwen3_4b_one_case.v1.json` `model` | 36 x 2,560 x 4 = 368,640 [D] |
| gemma-2-2b | 2,304 | 26 | Width: the ICA fork's `experiments/reconstruction/official/results/gemma2/results.json` (`effective_k` 2304 with components set to the model hidden size) at fork head `aa3b95c`. Depth: `docs/activation_patching_design.md:69`. The engine itself records no width for this model. | 26 x 2,304 x 4 = 239,616 [D] |
| qwen3.5-2b-base | not recorded locally | not recorded locally | `docs/model_matrix.md` gives parameters and a 248,320-entry tokenizer only. | `layers x hidden_size x 4`; left as a formula |
| every other registry model | not recorded locally | not recorded locally | No config value is committed for them. | left as a formula |

Token counts per prompt are not recorded (section 1). The worked examples use [A] 128 tokens
per prompt, the input cap of the baseline preflight (`data/exploratory/baseline_preflight.v1.json`
`numerical.max_input_tokens`). It is an upper bound for that protocol, not an observed length.

| Grid (one model) | Prompts | gemma-2-2b, all positions, float32 | gemma-2-2b, last position only | qwen3-4b, all positions, float32 | qwen3-4b, last position only |
|---|---|---|---|---|---|
| Small: 20 families x 2 prompts | 40 | 5,120 tokens x 239,616 = 1.23 GB | 40 x 239,616 = 9.6 MB | 5,120 x 368,640 = 1.89 GB | 14.7 MB |
| Medium: 200 x 3 | 600 | 76,800 x 239,616 = 18.4 GB | 143.8 MB | 28.3 GB | 221.2 MB |
| Larger: 2,000 x 3 x 2 replicates | 12,000 | 1,536,000 x 239,616 = 368 GB | 2.88 GB | 566 GB | 4.42 GB |

All [D] from recorded geometry under the [A] token count. bfloat16 halves every cell. A
subset of layers scales linearly: the one-case protocol's five fixed layers are 5 / 36 of the
qwen3-4b figure.

Reading: storing every position at every layer is a small-grid practice only. From the medium
grid on, a capture plan names its positions and layers before it runs, and the plan's summed
estimate is checked against a declared byte budget (section 4, point 6).

### 3.3 ICA fitting workspace

Formula (`estimate_fit_bytes`):

```
fit_bytes = bytes_per_value x (2 x n_samples x hidden_size + 3 x hidden_size^2)
```

The terms: the `n_samples x d` sample matrix and one whitened copy of it, held only when the
fit is not streamed; and three `d x d` matrices, covariance, whitening and unmixing. The ICA
Lens fit streams batches and accumulates the covariance in float64 (the mapping pass's
reading of its source),
so its resident size is closer to the `d x d` terms plus one batch; the formula is the upper
case of an unstreamed fit.

| Case | Arithmetic | Bytes | Label |
|---|---|---|---|
| gemma-2-2b width, 10,000 rows, float32 | 4 x (2 x 10,000 x 2,304 + 3 x 2,304^2) = 4 x (46,080,000 + 15,925,248) | 248 MB | [D] |
| gemma-2-2b width, 2,305 rows (the fewest a full-width fit accepts: `hidden_size + 1`) | 4 x (2 x 2,305 x 2,304 + 15,925,248) | 106 MB | [D] |
| qwen3-4b width, 100,000 rows, float32 | 4 x (2 x 100,000 x 2,560 + 3 x 2,560^2) | 2.13 GB | [D] |
| qwen3-4b width, 1,000,000 rows, float32, not streamed | 4 x (5,120,000,000 + 19,660,800) | 20.6 GB | [D] |
| One float64 covariance | gemma-2-2b 2,304^2 x 8 = 42.5 MB; qwen3-4b 2,560^2 x 8 = 52.4 MB | | [D] |

A fit on the study's own case families is limited by rows before memory: 20 families x 2
prompts x 128 tokens is 5,120 rows at most ([A] token count), above the 2,305-row floor for
gemma-2-2b but small for 2,304 components. Whether such a fit is stable is a research
question this estimate does not answer. The fit split must be the discovery split
(`scripts/experiments/protocol.py`, refusal `ica_basis_split`).

### 3.4 Logits storage

Formula (`estimate_logits_bytes`):

```
full vocabulary: positions x vocab_size x bytes_per_value
top-k:           positions x k x (4 + bytes_per_value)      a 4-byte token id beside each value
```

| Model | vocab_size | Source | One position, float32 | One position, top-10 |
|---|---|---|---|---|
| qwen3-4b | 151,936 | `data/exploratory/baseline_preflight.v1.json` `vocab_size` | 607,744 bytes [D] | 80 bytes [D] |
| qwen3.5-2b-base | 248,320 | `docs/model_matrix.md` | 993,280 bytes [D] | 80 bytes [D] |
| gemma-2-2b and the others | not recorded locally | | `vocab_size x 4`; left as a formula | 80 bytes |

Worked examples for qwen3-4b, final position only, float32: the six forwards of the baseline
preflight are 6 x 607,744 = 3.6 MB; the small grid's 40 prompts are 24.3 MB; the medium
grid's 600 are 365 MB; the larger grid's 12,000 are 7.29 GB. All [D]. The legacy lane stores
neither: it keeps four-decimal probabilities and a top-k continuation list in JSON, at 2,579
bytes per result ([D], section 1). A full-vocabulary vector is needed once per (prompt, model)
to recompute any target's rank later; top-k cannot do that for a target outside the window.

### 3.5 Model weights

Formula (`estimate_weight_bytes`): `parameters x bytes_per_value`.

| Model | Figure | Label and source |
|---|---|---|
| qwen3-4b | 4,022,468,096 parameters x 2 = 8,044,936,192 bytes at bfloat16; 16.1 GB at float32 | [D]; `docs/exploratory/baseline_preflight.md` (derived from the pinned config, not an observed download) |
| gemma-4-e2b | about 10.2 GB at bfloat16 | `docs/model_matrix.md` |
| qwen3.5-2b-base | about 4.5 GB at bfloat16 | `docs/model_matrix.md` |
| medgemma-1.5-4b-it | about 8.6 GB at bfloat16 | `docs/model_matrix.md` |
| gemma-2-2b | "2.6B" parameters in `docs/model_matrix.md`; an exact count is not recorded | 2.6e9 x 2 = about 5.2 GB at bfloat16 and about 10.4 GB at float32, [D] from a rounded count |

Against the one measured runner (15 GiB physical, plus 12 GB swap in the logits workflow): a
2 to 4B model at bfloat16 fits in RAM; gemma-2-2b at float32 fits by the estimate and has
run (the four landed `verify_*` summaries are float32); a 9B model at bfloat16 is about 18 GB
and failed twice (`docs/model_matrix.md`). Peak RSS has not been measured for any of them.

### 3.6 Intervention passes

- One extra forward per intervention site. A full grid is `layers x positions` forwards per
  pair: the patching design counts about 260 for gemma-2-2b and estimates 10 to 15 minutes
  per pair, which is 2.3 to 3.5 s per forward ([D] from a documented estimate, not from a
  recorded duration).
- [D] At that estimate the small grid's 20 pairs are 200 to 300 runner minutes, about the
  300-minute job ceiling of the patching lane, so even the small grid needs chunking and a
  per-pair flush.
- Gradients need an eager backend constructed with `requires_grad=True`. The vLLM backends of
  interp-engine never provide gradients through the forward, and CI runners are CPU, where
  only the eager backend runs (the mapping pass's reading of the fork source at 1.14.3; the
  engine executes 1.5.1; nothing was run).
- A random or prespecified control site costs the same as a nominated one. Budget controls
  in the forward count from the start.

## 4. The modest path from the current CI system

Eight points, in order. For each: what exists in code today, what this change set adds, and
what remains. "Adds" means offline code with tests on synthetic fixtures. It does not mean a
model run was planned, executed or stored with it.

### 4.1 A deterministic offline planner with compatibility checks before any model loads

- **Exists.** `scripts/backfill_planner.py` plans legs from landed index sets and refuses to
  plan onto an existing part name. `scripts/fire_trigger.py` `validate_params` refuses an
  unknown key. Neither checks whether a model, method, backend and artifact are compatible.
- **Added.** `scripts/experiments/planner.py` `build_plan`: sorted, no clock, no randomness.
  It looks every task up in `data/experiments/capability_matrix.v1.json`
  (`scripts/experiments/capabilities.py`) and keeps unsupported and unavailable tasks in the
  plan with the reason. `scripts/experiments/protocol.py` refuses a protocol with a wrong
  hash, split leakage, a missing revision or a sealed row before anything is planned.
- **Remains.** The planner marks a task ready only on the fixture backend. There is no
  bridge from a plan to a lane leg (`{trigger, params, note}`), and a real protocol needs
  token ids from the pinned tokenizer, which a development container cannot fetch.

### 4.2 Stable spec identity, separate attempt and replicate ids

- **Exists.** A part is named for its first global index, so two chunks never collide.
  320 of 1,225 journal rows carry a `nonce` and `params_sha256` (mapping pass). No
  measurement has an idempotency key: firing the same offset twice rewrites the same part,
  and a shorter second run replaces a longer first one (`docs/operators_handbook.md`
  section 5, 2026-09-04, still open).
- **Added.** `spec_sha256` is the digest of what is computed: protocol, family, variant,
  model identity, method block, input hashes, settings. `replicate` and `attempt` are outside
  it. `scripts/experiments/store.py` reuses a result only for the same `(spec_sha256,
  replicate)` and only when the payload file still has its recorded SHA-256, the adapter
  source files have the hashes the envelope recorded, and the adapter's input identity (a
  digest of the fixture or basis files the task reads, which are outside the spec) is
  unchanged. Replicate 1 is never satisfied by replicate 0. A changed protocol input changes
  the key, so nothing stale is reused; a changed fixture file or adapter under the same key
  is executed again as a new attempt; a store built from another protocol refuses with
  `incompatible_resume`.
- **Remains.** The legacy lanes do not carry a spec id. The link is the protocol's
  `legacy_join` (`batch`, `batch_index`, `model`). The overwrite defect needs its own fix in
  the workflows: refuse to commit a part with fewer results than the one on the branch.

### 4.3 Bounded batching, model reuse, and the activation cache key

- **Exists.** Chunk sizes are constants (`LENS_CHUNK` 25, `LOGITS_CHUNK` 25, 50 or 120 by
  speed class) and a half-timeout rule. One model loads once per matrix cell and measures
  every pair of the chunk. Prompts run one at a time, unpadded. No lane caches activations.
- **Added.** `scripts/experiments/activation_dataset.py` reads and writes the ICA Lens
  ActivationDataset layout with a manifest hash, per-row alignment checks and a model
  identity that is `unknown` when a revision is missing. The plan carries a per-task byte
  estimate.
- **Remains: the cache key.** An activation may be reused only when all of these are equal,
  and each must be a recorded field, not an inference:
  1. prompt tokens (`token_sha256` over the exact id sequence, special tokens included);
  2. full context: every token before the captured position, the chat template and system
     text if any, and for a multi-turn source the whole preceding conversation;
  3. model repository and revision (40 hex);
  4. tokenizer repository and revision;
  5. precision: dtype, and quantization if any;
  6. backend and its version, with the attention implementation;
  7. hook sites: capture site, layer index base, layer list, positions;
  8. settings: `use_cache`, truncation, padding and batch composition, seed and sampling
     settings when anything is generated.

  Teacher-forced, free-generation and intervened activations are different artifacts. A
  teacher-forced capture depends on the supplied tokens only. A free-generation capture
  depends on the sampled continuation, so its key includes the sampling settings, the seed
  and the generated token ids. An intervened capture's key includes the digest of the
  intervention specification. The fixture spec of this change set has no field that names
  the capture mode. Adding one (proposal: `capture_mode` with those three values, inside
  the method block so it enters `spec_sha256`) is a prerequisite for any stored real
  activation.
  Batching stays off until one prompt measured alone and inside a batch gives equal logits
  within a stated tolerance (`docs/upgrade_checklist.md` section 4, items 5 and 7).

### 4.4 Keep trigger admission, budgets, journal, concurrency and single-writer rules

- **Exists.** `scripts/fire_trigger.py` is the only sanctioned writer of trigger files: queue
  guard, settle window, daily ceilings, campaign limits, journal row, one-shot push token.
  `scripts/backfill_chain.py` and `scripts/scheduled_backfill_leg.py` drive it or write
  journal rows through its functions. `ops/dashboard.json` has one committing writer.
- **Added.** In the run store, concurrent workers write separate shard directories and one
  collector (`collect`) assembles them deterministically, sorted by `(task_id, replicate)`.
  The store has no task claim: two workers started together both execute the same tasks and
  the collector collapses identical results and refuses conflicting ones.
- **Remains.** A CI concurrency setting is not a durable queue. A group holds one running and
  one pending run and a third push evicts the pending one silently (`docs/triggers.md`). The
  durable record of what was asked for is the journal. One known gap is open: the scheduled
  backfill shares the logits lane's concurrency group but gets its journal row only after it
  has entered the group, so it can evict a journaled pending run (inferred from the two
  workflow files by the mapping pass; no instance found; untested). The fix is a journal
  reservation before the workflow enters the group, or a separate group.
  Nothing in `scripts/experiments/` fires, journals or spends, and it must stay that way: a
  planner sits in front of `fire_trigger.py`, never beside it.

### 4.5 Crash-safe checkpoints, conflict detection, and no exactly-once claim

- **Exists.** Four of five measurement scripts rewrite their summary after every pair and
  workflows commit on `always()`. `scripts/activation_patch.py` writes once at the end.
  Completion is recorded on newer parts only: 434 of 1,235 parts are
  `completion_not_recorded` ([M], catalogue totals). `scripts/results_policy.py` records
  part hashes in an append-only ledger and lists a changed part as `changed_since_recorded`.
  The catalogue counts 90 rows with a duplicate index ([M], `totals.rows_duplicate_index`).
  Paid lanes keep the reservation when the outcome is unknown: the advice judge checkpoints
  the pass cap before each call and keeps it when no response returns; a live Jev run books
  the whole `max_spend` when it leaves no readable report (`docs/triggers.md`).
- **Added.** Every store file is written through a temporary file and fsync, then
  `os.replace`; an attempt envelope is created with `os.link`, which never replaces an
  existing file. The journal gets a `started` line before an attempt and an `ended` line
  after. The collector verifies every payload hash each time and reports
  `duplicate_identical`, refuses `duplicate_conflict`, lists planned tasks with no envelope
  as `missing`, lists a `started` without `ended` and without an envelope as `uncertain`,
  and lists attempts of one number that ended in different states in two shards as
  `attempt_outcomes_differ` while keeping the completed envelope.
- **Remains.** The store makes no exactly-once claim and must not be given one. For a paid
  call the rule is the existing one: an uncertain attempt and its reservation are kept for
  reconciliation (`cli reconcile-spend` in the Petri lane); the attempt is not retried
  automatically and its spend is not assumed to be zero. The patching script needs a
  per-pair flush. The hosted batch runner stops a chunk on the first unhandled pair error;
  the lens runner's record-and-continue pattern is the one to copy.

### 4.6 Storage and memory bounds

- **Exists.** Job timeouts (240 and 300 minutes), a 12 GB swap file, the 128-token input cap
  and 10 GB download cap of the baseline preflight, and a capacity check in that workflow
  that excludes swap. No bound on `trace_out/` growth; no recorded peak memory.
- **Added.** Per-task and summed estimates in the plan (`measured: false`), the grid
  formulas in `scripts/experiments/estimate.py`, and a store that refuses to write under
  `trace_out/`, `data/`, `pilot/` or `ops/`, and inside any Git checkout unless the caller
  names an allowed root.
- **Remains.** A declared byte budget that the planner enforces (proposal: the protocol
  states `max_activation_bytes` and `max_logits_bytes`; `build_plan` refuses with a named
  code when the summed ready estimate exceeds either). Measured peak RSS per cell, so the
  memory bound is a fact and not the 15 GiB figure from one job.

### 4.7 Compact records in Git, bulky artifacts in Releases

- **Exists.** `scripts/archive_run.py` builds a zip and a manifest with the zip's sha256;
  `.github/workflows/archive_renders.yml` uploads it to a GitHub Release and commits the
  manifest under `render_archives/`. `scripts/render_archive.py fetch` reads one member back
  by HTTP range requests, and `coverage` reports what no Release holds. A shrink guard
  refuses an upload that would lose members. Pruning removes PNGs from the branch and does
  not rewrite history (`docs/archiving.md`).
- **Added.** Content-addressed payload files (`payloads/<sha256>.json`), an envelope that
  names its payload by kind, hash and path, and the activation dataset manifest. These are
  the compact records. Nothing yet sends a tensor to a Release.
- **Remains.** Route activation tensors and full-vocabulary logits through the same lane:
  one manifest per bundle in Git with member list and sha256, the bundle in a Release, a
  restore command that verifies the hash before use. A Release asset is capped at 2 GB
  (`docs/archiving.md`). By the estimates above the small grid's all-position capture for one
  model is one asset, the medium grid's is at least ten, and the larger grid's is outside
  what this route should carry; that is the threshold in section 7. History is never
  rewritten to reclaim space.

### 4.8 Metrics

None of these is collected today except where a source is named. Each is defined so that it
can be computed from a file, not from memory.

| Metric | Definition | Source today |
|---|---|---|
| Completed case families per hour | families with every planned variant `completed`, per runner hour and per wall hour | not collected; `collected.json` counts states for fixture runs only |
| Time per stage | load, tokenization, inference, capture, fit, intervention, grading, render, export, transfer seconds | not collected (section 1) |
| Peak RAM and VRAM | process maximum RSS; device memory high-water mark | not collected; no GPU lane exists |
| Cache reuse | reused tasks / ready tasks per run | store `reused` count, fixture runs only |
| Failure and refusal rate | attempts by final state, per lane, with refusal codes | journal has no outcome field; store has `failed`, `invalid`, `unsupported`, `unavailable` |
| Spend by role and provider | target, judge, second judge, translator, generator; Anthropic, OpenRouter | cost sidecars and `ops/dashboard.json` `spend` (written by `scripts/ledger_update.py`) |
| Missingness | planned tasks with no result, and results with `not_recorded` fields | store `missing`; catalogue `penalty_missing` (752 rows, [M]) |
| Artifact volume | bytes by kind, in Git and in Releases | section 1 for today's tree |
| Release latency | section 5 | not collected |
| Proportion of shareable results published | section 5 | computable today |

## 5. Release latency and the published proportion

**Definitions.**

- A part *lands* at the committer time of the first commit on `main` that adds its path
  under `trace_out/` (`git log --diff-filter=A --format=%cI -- <path>`).
- A part is *published* at the committer time of the first commit on the site repository's
  `main` in which `../patientwords/data/results_catalogue/index.json` lists that part's
  path with that part's `sha256` (`runs[].parts[]`).
- **Release latency** of a part is published minus landed. Report the median, the 90th
  percentile and the count still unpublished, per week of landing.
- **Published proportion** = parts in the published catalogue index under `public-display/1`
  / parts on engine `main` that are intact and carry no named restriction. Intact means
  artifact integrity is not `changed_since_recorded`, `malformed` or `unreadable`.

**Baseline.** Computed for this document with `scripts/results_policy.py` `classify_part`
over all 1,235 parts:

- 1,235 parts, no integrity failure. 3 are restricted (redistribution-limited text). 1,232
  are intact and unrestricted.
- Before 2026-11-10, 284 of the 1,235 intact parts were outside everything the publish chain
  wrote (`docs/open_results_policy.md`, History; `docs/open_results_migration_20261110.md`
  section 2): 93 gap-fill parts, 78 parts of two 2026-10-09 models, 113 parts of
  hand-authored sets. None of the 284 is restricted. The published proportion was therefore
  (1,232 - 284) / 1,232 = 948 / 1,232 = 77.0% ([D]). In parts, 951 of 1,235 were readable by
  the publish chain.
- Under the open-results policy the catalogue lists 1,232 of 1,232 under `public-display/1`
  ([M], exporter dry run in this session). That is the proportion in the working tree. The
  catalogue directory is untracked in the site checkout at the time of writing, so the
  published proportion on the public site is still the baseline until that change is merged
  and deployed.
- Release latency has no baseline yet. No catalogue index has been published, so no part has
  a published time. For the 284 parts the latency under the hold was unbounded; the oldest
  of them date from the 2026-10-09 additions, 32 days before this document. Per-part landing
  times could not be computed here because the checkout is a shallow clone.

**Collection.** A read-only script over the two repositories' histories is enough. It needs
full history in both, so it belongs in the Routine's publish step or a CI job with
`fetch-depth: 0`, not in a development container.

## 6. A broad behavioural pass and a prespecified mechanistic subset

The costs in section 3 differ by three orders of magnitude between a last-position
behavioural read and an all-layer capture or a patching grid. The design that follows from
that is two tiers, fixed before any outcome is seen.

1. **Broad behavioural pass.** Every reviewed, unsealed case family, every model in the
   protocol, the legacy endpoint plus one stored full-vocabulary vector per prompt. All
   outcomes are kept and shared under the open-results policy: zero and opposite-direction
   effects are completed results.
2. **Prespecified mechanistic subset.** A list of family ids written into the protocol before
   the behavioural pass runs, chosen by design criteria that do not use the outcome (for
   example stratified by syntax and terminology cell).
3. **A comparison subset drawn without regard to outcome.** Either part of the prespecified
   list, or a random draw with a recorded seed from the families the behavioural pass
   covered. Its size is stated in advance and is at least the size of any outcome-selected
   set. Without it the mechanistic work studies only the cases that fit the story, and a
   mechanism found there cannot be distinguished from one that is present everywhere.
4. **Outcome-selected work is labelled.** A family chosen because its behavioural result was
   large or flipped is exploratory. The existing label is `outcome_selected_priority_subset`
   (the catalogue applies it to the medgemma-1.5 priority selection). A mechanism claim from
   such a set needs independent confirmation on families that were not used to select or
   tune it, on the fresh-test split, with the endpoint and controls fixed beforehand.
5. **Controls are part of the subset's budget.** Random-site, size-matched and
   reverse-direction controls cost the same forwards as the nominated sites.

`docs/protocols/protocol_template.md` is where a study states these lists. The protocol
validator already refuses a basis fitted on a non-discovery split.

## 7. What not to add, and the threshold that would justify it

Every threshold below is a proposal for the owner. None is in force.

| Not now | Why not now | Proposed threshold that would justify it |
|---|---|---|
| Kubernetes or any cluster scheduler | Work is batch, chunked and runs on hosted runners at $0. A scheduler adds an always-on system with its own credentials to two public repositories. | A measured need for more than 2 concurrent GPU jobs for more than 100 GPU-hours a month, sustained for 2 months, with the per-stage timings of section 1 showing inference, not queueing or checkout, as the limit. |
| A live web backend | The site serves static JSON; the catalogue export takes 2.5 s; `docs/architecture_decision_20261110.md` records the decision. | A published payload a browser must fetch whole exceeds 50 MB (the catalogue index is 1.1 MB today), or a required query cannot be answered from files of at most 5 MB each. |
| A database | Summaries are immutable files joined on `(batch, batch_index, model)`; the full catalogue export reads 1,235 parts in under 3 s. | The catalogue export exceeds 10 minutes on the CI runner, or part count exceeds 100,000, or two writers must update one record concurrently. |
| A new workflow service or queue | The journal is the durable record and `fire_trigger.py` is the admission point. | The journal exceeds 50,000 rows a year, or more than 5% of fires in a quarter are lost to eviction or expiry after the outcome field of section 1 exists to count them. |
| Mandatory external experiment tracking | Envelopes, manifests and sidecars are in Git and readable offline; an external tracker would hold provenance outside the public record. | A collaborator outside the owner's account must write runs, and the Git record cannot give them a scoped write path. Even then it stays optional and the Git record stays the authority. |
| External storage for tensors | Releases hold 15 GB of renders today under a 2 GB asset cap. | A single approved capture plan exceeds 50 GB in total or 25 assets, by the planner's estimate confirmed against one measured run. |
| A denser schedule before rates are measured | The planner sizes on slowest rates of unknown sample size; recent legs ran several times faster. | Not a thing to avoid, the thing to do first: record per-cell timings for two weeks, then resize legs. |

## 8. Candidate dependency-upgrade checks

Both are isolated evaluations. Neither is part of scaling and neither moves a pin. The
procedure, with every check, is `docs/upgrade_checklist.md`; this section names the checks
that decide the outcome. None was executed: the development container has no torch, no
model weights and no Inspect package.

**interp-engine 1.5.1 (the pin in `constraints.txt`) against the 1.14.x source.** The fork
head declares 1.14.3 and its package directory equals the PyPI 1.14.3 wheel (mapping pass,
`diff -rq`). All seven engine call sites accept their arguments at 1.14.3 by reading both
sources. The checks that matter:

1. A parity run on both versions with the same prompts at float32, using `mode: verify` and
   `scripts/backend_agreement.py`. The 1.5.1 reference,
   `trace_out/verify_pairs_20260710T011743Z__gemma-2-2b`, records `inference.revision` null,
   so it cannot be tied to a checkpoint commit. A new fire of that batch with
   `commit_outputs` true would write the same file name and replace the reference; use a
   batch with no landed verify summary.
2. Three Hub reads at 1.14.3 carry no revision (two `AutoConfig` reads at load, one
   `generation_config.json` read at first generation). Pass `temperature` explicitly and
   decide how the config reads are pinned or recorded.
3. `layer_logits` is textually unchanged but sits on a capture path where 307 lines changed.
   Repeat depth mode on one model per family with landed depth artifacts.
4. The offline doubles in `tests/test_model_pins.py` and `tests/test_depth_probe.py` pass
   under any version and are not evidence.
5. The upgrade gives no activation-replacement spec and ships no Jacobian matrices.

**Inspect and Scout floors for the current Petri fork.** The lock holds inspect-ai 0.3.237
and inspect-scout 0.4.39 (`docs/framework/petri_environment.lock.json`). The fork head
requires `inspect-ai>=0.3.276` and `inspect-scout>=0.5.3` (its `pyproject.toml`, lines 11 and
12), so the lock cannot host the head. The checks that matter:

1. Adapt one raw `.eval` written under the locked environment in both environments and
   compare transcripts, rule outcomes, trees, stop reasons and contract checks. Raw logs are
   90-day CI artifacts; secure one first.
2. Whether the candidate Inspect reads a 0.3.237 log at all.
3. The private import `inspect_ai.log._resolve.rebind_sample_timelines`, the seed-forwarding
   table, the stop-reason sets and the sanitiser allowlist, each written against 0.3.237.
4. A span named `branch (incomplete)` must not be exported as the surviving trajectory.
5. The judge runs in the harness environment, so a candidate lock that raises the
   `anthropic` SDK changes the judge instrument too. Judge one fixed plan under both.
6. `rejudge-rehearse` for every landed run, and the same chain head from `verify-chain`
   before and after.

A candidate is a new constraints file or a new lock file in a separate environment. The
measurement workflows read the current files by literal path, so a CI evaluation needs a
reviewed workflow change and the owner's approval to fire.

## 9. What this document did not verify

- No model was loaded and nothing was fired. Every time and size for a model run is an
  estimate from the labelled sources.
- The sample sizes behind `SECONDS_PER_PAIR` and its medians are not recorded and were not
  reconstructed from Actions run logs.
- The gemma-2-2b width comes from the ICA fork's result files, not from the model's config.
  huggingface.co is not reachable from a development container.
- Runner figures (15 GiB) come from one job. Free disk on a runner is not recorded.
- The catalogue and suite timings are from a 4-CPU development container, one to three runs
  each. They say nothing about CI runners.
- The ICA fit figures quoted from the ICA Lens documentation were not reproduced.
- The concurrency-group gap in 4.4 is inferred from workflow files and was not observed.
- Section 4's statements about how the legacy scripts checkpoint, resume and fail come from
  the 2026-11-10 mapping pass, which read the code. For this document only these were
  re-read: the workflow limits, the logits lane's commit step and output paths, the planner
  constants, the handbook's open overwrite entry, and the function names cited.
