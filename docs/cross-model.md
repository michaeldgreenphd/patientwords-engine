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
