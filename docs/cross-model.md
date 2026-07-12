# Cross-model circuit tracing

The pipeline can trace the **same phrases across several circuit-tracer models**
and the front-end can switch between them, so a reader compares how each model
behaves on identical patient-vs-clinical prompts. This is fully built; what it
shows depends on which models the hosted backend actually serves.

## Current backend reality (tested 2026-07-07)

Neuronpedia's hosted `/api/graph/generate` was probed with a 2-pair trace on
each registered model:

| Model | Result |
|---|---|
| `gemma-2-2b` | **works** — the only reliably graph-traceable model |
| `gemma-3-4b-it` | fast non-retryable error — not served |
| `qwen3-1.7b` | fast non-retryable error — not served |
| `qwen3-4b` | persistent 500 from the backend, even with no parallel load |

So a cross-model *circuit-graph* comparison isn't achievable on Neuronpedia
today — only `gemma-2-2b` renders. The other three stay in `MODEL_REGISTRY`
(`graph_client.py`) so the machinery lights up automatically if they get
enabled. Tracing itself is billed **$0** (the API key only authenticates /
rate-limits); the failures are backend availability, not cost.

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
  is gated** — add an `HF_TOKEN` repo secret and include it in `models` to run it.
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
