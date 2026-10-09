# Cross-model circuit tracing

The pipeline can trace the **same phrases across several circuit-tracer models**
and the front-end can switch between them, so a reader compares how each model
behaves on identical patient-vs-clinical prompts. This is fully built; what it
shows depends on which models the hosted backend actually serves.

## Current backend reality (re-probed 2026-09-02)

Neuronpedia's hosted `/api/graph/generate` was probed with a 2-pair trace on
each registered model. The 2026-09-02 re-probe (run 33628534916) followed
Neuronpedia's move to the open-sourced `interp-engine` backend and **changed one
verdict**:

| Model | 2026-07-07 | 2026-09-02 |
|---|---|---|
| `gemma-2-2b` | works | works — and the only model with a transcoder source set |
| `gemma-3-4b-it` | fast non-retryable error | unchanged — still not served |
| `qwen3-1.7b` | fast non-retryable error | unchanged — still not served |
| `qwen3-4b` | persistent 500, even unloaded | **serves graphs** — 2/2 pairs in ~4 min |

The `qwen3-4b` probe returned real spreads and language penalties
(`trace_out/pairs_20260706T201750Z__qwen3-4b/batch_summary.part_01.json`), but
its `source_set` is null, so every feature is untagged and its `clinical_mass`
comes back 0.0. That is the documented `NullFetcher` artifact, not a finding:
graphs and probabilities are real, attribution mass is not. Scaling this model
therefore buys graph structure and next-token behavior, and buys nothing for the
clinical/off-target feature contrast until Neuronpedia publishes transcoders for
it.

A two-model *circuit-graph* comparison is now achievable for the first time:
`gemma-2-2b` and `qwen3-4b` both render. The other two stay in `MODEL_REGISTRY`
(`graph_client.py`) so the machinery lights up automatically if they get
enabled. Tracing itself is billed **$0** (the API key only authenticates /
rate-limits); the failures are backend availability, not cost.

Scaling `qwen3-4b` past the probe is an owner decision, not an automatic
follow-on: it is a new measurement axis on a model whose behavioral arm is
already complete, so it needs the step-2/step-3 sequence below and a note in
`docs/prereg_divergence_log.md` recording that graphs became available
mid-study.

## Why gemma-3-4b-it and qwen3-1.7b fail (confirmed 2026-10-09)

Until PR #90 the client discarded the body of a hosted error, so the "fast
non-retryable error" above had no recorded cause. A $0 two-pair re-probe on
2026-10-09 (run 37960184793, `commit_outputs: false`) logged both bodies:

| Date | Run | Model | Status | Body |
|---|---|---|---|---|
| 2026-10-09 | 37960184793 | `gemma-3-4b-it` | HTTP 400 | `{"error":"Source Set Missing","message":"The model gemma-3-4b-it has no default graph source set, so you must provide one in the sourceSetName parameter."}` |
| 2026-10-09 | 37960184793 | `qwen3-1.7b` | HTTP 400 | `{"error":"Prompt Too Long","message":"Max tokens supported is 10, your prompt was 17 tokens."}` |

- **gemma-3-4b-it** fails because this study never sends `sourceSetName`, and
  the model has no server default to fall back on. Neuronpedia's gemma-3-4b-it
  page offers the transcoder set `gemmascope-2-transcoder-262k`; its labels are
  sparse (1 of 3 features sampled on 2026-10-09 had one). The circuit-trace
  lane's `source_set` key (2026-10-09, `docs/triggers.md`) passes a set
  through `medlang-batch-eval --source-set`, which sends it as `sourceSetName`
  and tags features from the same set. The next step is a $0 two-pair probe
  with `graph_models: ["gemma-3-4b-it"]`, `source_set:
  "gemmascope-2-transcoder-262k"` and `commit_outputs: false`. Whatever it
  returns, gemma-3-4b-it's `clinical_mass` stays unpublished: the exporters
  null it for every model outside `FEATURED`, and the fire path and the
  workflow refuse a `source_set` fire with `commit_outputs: true`, so no
  summary of it reaches `trace_out/`, where `scripts/export_tag_mass.py`
  would otherwise aggregate it.
- **qwen3-1.7b** refused the probe's first prompt, which was 17 tokens,
  because its hosted graphs cap a prompt at 10 tokens. That is all the run
  shows: a 400 aborts the batch, so the second pair was never sent. Most of
  the study's prompts are longer than the cap allows. Across the archived
  pairs under `data/simulated/` (excluding the control files), the median
  prompt is 14 words, and 1.9% of 9,806 prompts have 8 words or fewer
  (word counts, measured 2026-10-09; token counts, which are usually higher,
  were not measured). So most study pairs would be refused. Shorter pairs do
  exist: the control files
  (`control_identity_20260710T011743Z.json`,
  `control_qualified_20260710T011743Z.json`) hold prompts of 5 words and up,
  15% of them 8 words or fewer. None of them has been tried on this model.
  Tracing qwen3-1.7b on study material would mean choosing or writing
  prompts that fit the cap, which changes the stimuli; that is a
  study-design decision, not a fix, and nothing here makes it.

## What's built (dormant until >1 model traces)

- **Workflow** — `circuit_trace_evaluation.yml` takes a `graph_models` list (or
  `"all"`) and fans the trace out over a model × offset matrix; a single
  `graph_model` still behaves exactly as before. Each model writes to its own
  dir: `trace_out/<stem>` for gemma, `trace_out/<stem>__<model>` for the rest.
- **Export** — `export_frontend_simulated.py` merges every model's trace dir
  into `scenario.models[<id>]`, mirrors gemma to the top level for backward
  compatibility, and emits `payload.models_meta` (the selector's source of
  truth). `clinical_mass` is nulled for non-featured models (they trace under
  NullFetcher and would otherwise report a false 0%).
- **UI** — the simulated-scenarios index and per-scenario page grow a **model**
  chip row that swaps which model's measurements the view shows. Suppressed when
  only one model is present, so today's page is unchanged.
- **Collaborator data** — `export_archive.py` emits one flat row per
  `(pair × model)`; the render bundle goes to a GitHub Release (see
  `archiving.md`).

## Re-checking / scaling when a model becomes available

1. **Probe** (2 pairs, $0) — push a trigger and read the run:
   ```json
   {"graph_models":["qwen3-4b"],"mode":"2panel",
    "pairs_file":"data/simulated/pairs_20260706T201750Z.json",
    "offsets":[0],"sample_size":"2","max_feature_nodes":"2500",
    "commit_outputs":true}
   ```
   A committed `trace_out/pairs_..__<model>/batch_summary.part_01.json` with 2
   results means it works.
2. **Scale** — trace all 13 pairs. If the model 500s under load, keep it to a
   **single sequential cell** (`"offsets":[0],"sample_size":"13"`) so there is
   no concurrent Neuronpedia load; if it is robust, use `offsets:[0,3,6,9,12]`
   with `sample_size:3`. Leave gemma out of the trigger — its base dir already
   exists and the export merges it in.
3. **Publish** — archive the run dirs to a Release (`archive-renders` trigger),
   then re-export with `--archive-url <release>`. The model buttons appear the
   moment `models_meta` lists more than one available model.

## Behavior without graphs (the logits path)

Because the hosted tracer can't render the other models, their **next-token
behavior** is measured directly instead — the cross-model comparison the graphs
can't give. `scripts/logits_eval.py` loads the open weights (CPU, bf16), reads
the target token's probability under each phrasing plus the top-k spread, and
writes the *same* `batch_summary.part_01.json` schema, so the export merges each
model into `scenario.models[<id>]` with no changes. There is no transcoder, so
`clinical_mass` and the circuit render are absent (`models_meta.graphs = false`);
the front end labels these models "next-token behavior only".

- **Workflow** — `logits_evaluation.yml`, fired by `.github/trigger/logits-eval.json`:
  ```json
  {"models":["qwen3-4b","qwen3-1.7b"],
   "pairs_file":"data/simulated/pairs_20260706T201750Z.json",
   "limit":13,"commit_outputs":true}
  ```
  It installs CPU torch + transformers, runs one model per matrix cell, and
  commits the tiny per-model summary. The Qwen models are open; **gemma-3-4b-it
  is gated** — covered by the existing CI `HF_TOKEN` (runs routinely since 2026-07-08).
- **Publish** — after the summaries land, `git pull`, then re-export with all
  stamps and models:
  ```
  python scripts/export_frontend_simulated.py --frontend ../patientwords \
    --stamps <all stamps> --models gemma-2-2b,qwen3-4b,qwen3-1.7b --no-pngs \
    [--archive-url <gemma render release>]
  ```
  gemma's numbers stay graph-derived; the Qwen numbers are raw next-token logits.
  That method difference is the one caveat of comparing them side by side.

## Probe-extension outcomes (2026-07-12)

The 07-11 five-model probe (3 pairs each through the logits path) triaged as:

- **Landed and usable:** llama-3.2-3b, olmo-2-1b, gemma-2-2b-it. Unified-set
  runs are queued; `inference.revision` pins fill from each model's next run.
- **gemma-2-9b: skipped.** Died twice loading weights on the standard runner,
  the second time (07-12) with the 12G swap step in place — the host kills the
  runner before the load completes. Protocol says two deaths = skip; revisit
  only if Tier B2 justifies a larger runner.
- **biomistral-7b: dropped.** The upstream repository publishes pickle `.bin`
  shards only, no `model.safetensors`. This study's supply-chain posture loads
  safetensors exclusively (`use_safetensors=True`), and transformers' automatic
  conversion path failed server-side (07-12 run). Loading pickled weights is
  not an acceptable workaround, so the model is structurally out of scope.
