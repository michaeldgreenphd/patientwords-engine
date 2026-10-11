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

## qwen3-4b feature labels (registered 2026-10-09)

The paragraph above was true on 2026-09-02 and is no longer. Neuronpedia now
serves an autointerp-labelled transcoder source set for `qwen3-4b`,
**`transcoder-hp`** (Hanna & Piotrowski's `mwhanna/qwen3-4b-transcoders`, ~164k
features per layer; labels by `gemini-2.0-flash`, explanation type
`np_max-act`). Found by the owner's model survey of 2026-10-09 (kept outside
the repository; Step 2, "Transcoders and labels") and registered the same day
in `neuronpedia_features.MODEL_SOURCE_SETS`, so the next qwen3-4b trace tags
its features and records `source_set: "transcoder-hp"`.

Evidence, all public and checked 2026-10-09:

- **It is the set the graphs already use.** Neuronpedia's model record for
  `qwen3-4b` (embedded in https://www.neuronpedia.org/qwen3-4b/graph) has
  `defaultGraphSourceSetName: "transcoder-hp"`; the generate route
  (`apps/webapp/app/api/graph/generate/route.ts`) applies that default when a
  request omits `sourceSetName`, which is how this study requests every graph.
  The graph server labels `mwhanna/qwen3-4b-transcoders` graphs with
  `neuronpedia.org/qwen3-4b/transcoder-hp`
  (`apps/graph/neuronpedia_graph/server.py`), and Neuronpedia's own
  ground-truth fixture is `apps/graph/tests/fixtures/graphs/123-qwen3-4b-transcoder-hp.json`.
- **Node ids map to feature pages as for gemma.** qwen3-4b graphs are schema 1:
  a node's `feature` is the Cantor pairing of (layer, index), and its `layer` is
  the plain layer number. The fixture's node `1_19591_1` (feature 191952619)
  decodes to layer 1, index 19591, and
  `GET /api/feature/qwen3-4b/1-transcoder-hp/19591` returns its label ("URLs").
  Two more fixture nodes (`0-transcoder-hp/116505`, `1-transcoder-hp/82024`)
  and one of the survey's spot checks (`10-transcoder-hp/5`) resolved the same
  way, each with one `gemini-2.0-flash` `np_max-act` explanation.
- **The graph request is unchanged.** Registration selects the feature fetcher
  only; `sourceSetName` is sent only with an explicit `--source-set`, which the
  workflow never passes. A test pins this
  (`tests/test_qwen3_4b_source_set.py`).

**qwen3-4b's clinical mass is exploratory and unpublished.** Its labels differ
from gemma-2-2b's in kind: the two gemma-2-2b features sampled on 2026-10-09
carry two explanations each (`oai_token-act-pair`, a phrase, and `np_max-act`, a
token or two), the four qwen3-4b features one short `np_max-act` label each. Both
come from `gemini-2.0-flash`; the difference is in how many explanations, and of
which type, each feature has. A sample this small shows the difference exists,
not how large it is. The keyword rule may
therefore tag a different share of features clinical for reasons that are about
the labels, not the model. The exporters keep nulling qwen3-4b's
`clinical_mass` (`scripts/feature_models.py`, `CALIBRATED_FEATURE_SOURCES`) until
the owner decides, after `scripts/feature_label_calibration.py` has compared the
two models' labels and clinical mass on the same pairs. The divergence is logged
in `docs/prereg_divergence_log.md` (2026-10-09).

`gemma-3-4b-it` and `qwen3-1.7b` stay unregistered: the first has sparse labels
(1 of 3 sampled features labelled) and hosted graphs that still fail for this
study, pending a re-probe; the second is a LORSA model whose hosted graphs are
capped at 10 prompt tokens, shorter than the study's prompts.

## Two-model comparison

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

## What's built (dormant until >1 model traces)

- **Workflow** — `circuit_trace_evaluation.yml` takes a `graph_models` list (or
  `"all"`) and fans the trace out over a model × offset matrix; a single
  `graph_model` still behaves exactly as before. Each model writes to its own
  dir: `trace_out/<stem>` for gemma, `trace_out/<stem>__<model>` for the rest.
- **Export** — `export_frontend_simulated.py` merges every model's trace dir
  into `scenario.models[<id>]`, mirrors gemma to the top level for backward
  compatibility, and emits `payload.models_meta` (the selector's source of
  truth). `clinical_mass` is nulled for every model outside
  calibrated (model, source set) pair, `feature_models.CALIBRATED_FEATURE_SOURCES`
  (gemma-2-2b with `gemmascope-transcoder-16k` alone), checked per row: NullFetcher
  models would otherwise report a false 0%, and qwen3-4b's labels are not yet
  calibrated against gemma-2-2b's.
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
