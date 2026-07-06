# patientwords-engine

Backend engine for [patientwords](https://github.com/michaeldgreenphd/patientwords)
(`medlang-circuits` Python package): a pipeline for comparing attribution graphs of
two phrasings of the same next-token prompt (standard clinical terminology vs.
colloquial patient language) on gemma-2-2b with Gemma Scope transcoders. Built on
Neuronpedia's graph stack — either the hosted neuronpedia.org generation API or a
local graph server run from a Neuronpedia checkout.

## Provenance & acknowledgments

Built on top of [Neuronpedia](https://github.com/hijohnnylin/neuronpedia)
(MIT license, © Johnny Lin), whose hosted APIs this engine consumes for
attribution-graph generation (`/api/graph/generate`, powered by
[circuit-tracer](https://github.com/safety-research/circuit-tracer)) and feature
autointerp descriptions (`/api/feature/...`). No Neuronpedia source files are
vendored here; the coupling is the HTTP contract only.

- Developed July 2026 inside a fork of the Neuronpedia monorepo
  ([michaeldgreenphd/neuronpedia](https://github.com/michaeldgreenphd/neuronpedia),
  branch `claude/medical-language-circuit-trace-1dge1c`, under
  `apps/experiments/medlang-circuits/`), forked from upstream commit `458cb46`
  ("package updates", 2026-06-17).
- Ported to this standalone repository on 2026-07-06 with `git filter-repo`
  (full commit history of the package preserved; branch tip at port time:
  `64eb1df`).
- To pull later work from the fork: re-run the same filter on the updated
  branch and compare/cherry-pick, e.g.
  `git filter-repo --path apps/experiments/medlang-circuits --path .github/workflows/model_evaluation.yml --path-rename apps/experiments/medlang-circuits/:''`.
- Related repositories: [patientwords](https://github.com/michaeldgreenphd/patientwords)
  (the public frontend/gallery this engine generates figures for) ·
  [Neuronpedia](https://github.com/hijohnnylin/neuronpedia) ·
  [circuit-tracer](https://github.com/safety-research/circuit-tracer) ·
  [Gemma Scope](https://huggingface.co/google/gemma-scope-2b-pt-transcoders).

## What it does

1. **Feature tagging (Task 1)** — `feature_tagger.annotate_graph` post-processes a
   graph JSON (schema: `apps/webapp/app/api/graph/graph-schema.json` in the Neuronpedia repo): it fetches
   each transcoder feature's autointerp description + top activating tokens from
   Neuronpedia (disk-cached), classifies it into `clinical` / `off_target` /
   `structural` via keyword matching (with an optional Anthropic LLM fallback),
   and appends `node["medlang"]` metadata plus a graph-level
   `metadata["medlang_summary"]`. The extra keys are additive, so tagged graphs
   still load in the standard Neuronpedia viewer.
2. **Stacked comparison viz (Task 2)** — `compare_viz` renders two tagged graphs
   stacked vertically (clinical wording top, patient wording bottom; tokens on
   the x-axis, layers on the y-axis). Clinical features are blue, off-target
   orange, structural gray; edge width/opacity scales with |attribution weight|
   (negative edges dashed red). Outputs a self-contained HTML file (hover
   tooltips, no external assets) and a matplotlib/networkx PNG.
3. **Auto-translation pipeline (Task 3)** — `pipeline.run_comparison` takes a
   patient sentence, translates it to clinical terminology (Anthropic Messages
   API when configured, offline phrase table otherwise), traces both prompts,
   tags both graphs, renders the stacked comparison, and writes a divergence
   summary (per-category node counts, attribution-mass shares, and clinical
   feature overlap between the two traces).
4. **Target-token forcing** — `targets.AttributionTargets` names substantive
   next tokens (e.g. `[" therapist"]`) so attribution isn't read off a
   grammatical article: generation widens the salient-logit set (with a
   `force_target_tokens` passthrough for circuit-tracer forks that support
   native forcing on the graph server), and `retarget_graph` prunes the
   generated graph's logit set down to the named targets.
5. **Batch evaluation harness** — `batch_eval.run_batch` consumes a JSON array
   of pair objects, traces/tags/retargets each sequentially, and writes
   numbered `index_01.html` / `index_01.png` outputs plus `batch_summary.json`.
   Three isolated visualization modes via `--mode`:
   - **`2panel`** (default) — direct lexical swap: the polished two-panel
     stack with the **Language Penalty** badge (Δ = p_patient − p_clinical
     for the target medical token). `--show-mitigation` appends the legacy
     third translated panel.
   - **`4quadrant`** — the syntax-vs-terminology matrix: a 2×2 grid crossing
     core medical keyword (clinical/patient term) with surrounding frame
     syntax (physician/patient style). Target probability printed prominently
     in each box; **Vocabulary Δ** badges (term swap: A→B, C→D) in the column
     gutters and **Syntax Δ** badges (frame swap: A→C, B→D) in the row gutter.
     Box C (patient frame + clinical term) isolates syntactic-framing bias.
   - **`translation`** — organic downstream mitigation: the patient prompt is
     translated by the Anthropic API and the *raw* LLM output is traced
     natively (no template). Renders patient prompt → [LLM translation
     interstitial] → natively traced translation, with per-panel target-
     probability headlines and a **Recovered target probability** badge.

## Setup

```bash
git clone https://github.com/michaeldgreenphd/patientwords-engine
cd patientwords-engine
poetry install            # or: pip install -e ".[llm]"
```

**Keyword config (required for classification):** term lists are data, not code.
Copy `keyword_config.example.json` to `keyword_config.json` (or point
`MEDLANG_KEYWORD_CONFIG` at your file) and populate the three category lists
with your vocabulary. An optional `"translations"` key maps colloquial phrases
to standard phrasing for the offline translation fallback. Without a config,
keyword matching is a no-op and features fall through to the LLM fallback /
default bucket.

**Environment variables:**

| Variable | Needed for |
| --- | --- |
| `NEURONPEDIA_API_KEY` | hosted graph generation + feature-description fetching |
| `GRAPH_SERVER_SECRET`, `GRAPH_SERVER_URL` | `--backend local` (a running graph server from a Neuronpedia checkout, `apps/graph`) |
| `ANTHROPIC_API_KEY` | LLM translation and the `--llm-classifier` fallback |
| `MEDLANG_ANTHROPIC_MODEL` | override the default Anthropic model |
| `MEDLANG_KEYWORD_CONFIG` | custom keyword-config path |

## Usage

```bash
# Full pipeline: translate the patient phrasing, trace both, tag, visualize
medlang-compare --patient "I've got the blues, so I need to talk to a"

# Explicit prompt pair against a local graph server
medlang-compare \
  --patient "I've got the blues, so I need to talk to a" \
  --clinical "I have depression, so I need to talk to a" \
  --backend local

# Tag an existing graph JSON in place (no generation)
medlang-compare tag path/to/graph.json

# Batch evaluation over paired prompts (three modes)
medlang-batch-eval pairs.json --mode 2panel --out batch_out
medlang-batch-eval matrix.json --mode 4quadrant --out batch_out
medlang-batch-eval patient.json --mode translation --out batch_out
```

Pair formats (`target_clinical_token` / `force_target_tokens` optional on all):

```json
// --mode 2panel
[{"top_prompt": "Clinical framing...", "bottom_prompt": "Patient framing...",
  "target_clinical_token": " therapist", "force_target_tokens": [" therapist"]}]

// --mode 4quadrant (or explicit "quadrants": {"A": ..., "B": ..., "C": ..., "D": ...})
[{"frames": {"clinical": "I have{term}, so I need to talk to a",
             "patient":  "I've got{term}, so I need to talk to a"},
  "terms":  {"clinical": " depression", "patient": " the blues"},
  "target_clinical_token": " therapist"}]

// --mode translation
[{"patient_prompt": "I've got the blues, so I need to talk to a",
  "target_clinical_token": " therapist"}]
```

Outputs land in `medlang_out/`: `clinical_graph.tagged.json`,
`patient_graph.tagged.json`, `comparison.html`, `comparison.png`, `summary.json`.

From Python:

```python
from medlang_circuits import run_comparison

result = run_comparison(
    patient_prompt="I've got the blues, so I need to talk to a",
    backend="hosted",
    use_llm_classifier=True,
)
print(result["summary"]["clinical_feature_overlap"])
```

## Model evaluation

`evaluate_models.py` benchmarks the two Anthropic-backed pipeline steps —
patient→clinical translation and feature-description classification — across
multiple Claude models, with per-model accuracy, token consumption, and cost
tracking under a hard spend ceiling:

```bash
export ANTHROPIC_API_KEY=...
medlang-evaluate --models claude-opus-4-8 claude-sonnet-5 claude-haiku-4-5 \
  --scenario both --sample-size 8 --max-spend 5 --out eval_out
```

Scenarios: `translation` and `classification` are single-call checks;
`--scenario two_step` (included in `all`) runs the dual-stage conversion &
re-evaluation pipeline — **Stage A** scores a concept-extraction task on the
raw patient phrasing, **Stage B** translates that exact phrasing into
clinician language with the production prompt, and **Stage C** re-scores the
identical task on the generated clinician text. The report compares patient
vs. clinician accuracy per model (the delta) and audit-flags every
problematic item: `patient_phrasing_failure` (the patient wording alone broke
the model; translation mitigates), `translation_regression` (the conversion
lost the concept), or `unresolved_failure` (both missed).

Writes `eval_out/results.json` (full per-item log), `eval_out/summary.md`
(accuracy/cost tables, including the patient-vs-clinician comparison), and
appends every run to `eval_out/audit_registry_log.json` — a cumulative
registry entry per execution with the ISO timestamp, the original patient
text, the intermediate clinician translation, per-stage token counts and
cost, the comparative metrics, and all flagged cases. Evaluation items live
in `medlang_circuits/data/eval_pairs.json`; pass `--pairs` to use your own set.
Retired model names (e.g. `claude-3-5-sonnet`, `claude-3-haiku`) are remapped
to their current equivalents with a warning. Every Anthropic-calling entry
point (`run_comparison`, `medlang-batch-eval --llm-model`, `medlang-evaluate`)
also honors the `MEDLANG_ANTHROPIC_MODEL` environment variable.

The same evaluation runs on demand from GitHub Actions
(`.github/workflows/model_evaluation.yml`, *Model Evaluation* in the Actions
tab): pick the model, spend ceiling, sample size, and scenario from the
`workflow_dispatch` form. The job reads `ANTHROPIC_API_KEY` from repository
secrets, prints the summary to the run page, and uploads `eval_out/` as an
artifact.

## Tests

```bash
poetry run pytest tests/ -v
```

Tests use synthetic graphs, a stubbed feature fetcher, and abstract placeholder
vocabulary — no network or API keys required.
