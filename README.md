# patientwords-engine

Backend engine for [patientwords](https://github.com/michaeldgreenphd/patientwords)
(`medlang-circuits` Python package): a pipeline for comparing attribution graphs of
two phrasings of the same next-token prompt (standard clinical terminology vs.
colloquial patient language) on gemma-2-2b with Gemma Scope transcoders by default
(other hosted models selectable — see *Choosing the traced model*). Built on
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
| `MEDLANG_GRAPH_MODEL` | override the default traced model (`gemma-2-2b`) |
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

## Choosing the traced model

Both CLIs (`medlang-compare`, `medlang-batch-eval`) and the corresponding Python
entry points (`run_comparison`, `run_batch`, `evaluate_pair`, …,
`generate_graph`) accept `--graph-model` / `graph_model` to pick which model the
circuit tracer runs on. The registry (`graph_client.MODEL_REGISTRY`, a
module-level dict — extend it as more models are enabled for hosted generation)
maps Neuronpedia IDs to the TransformerLens IDs used by the local backend:

| Neuronpedia ID | TransformerLens ID (local backend) | Notes |
| --- | --- | --- |
| `gemma-2-2b` (default) | `google/gemma-2-2b` | default feature source set: `gemmascope-transcoder-16k` |
| `gemma-3-4b-it` | `google/gemma-3-4b-it` | requires `--source-set` (see caveat below) |
| `qwen3-4b` | `Qwen/Qwen3-4B` | requires `--source-set` (see caveat below) |
| `qwen3-1.7b` | `Qwen/Qwen3-1.7B` | requires `--source-set`; supports LORSA/QK tracing (`--qk-*`) |

The default resolves as: explicit argument → `MEDLANG_GRAPH_MODEL` environment
variable → `gemma-2-2b`.

**Request parameters** (validated client-side against neuronpedia.org's schema —
out-of-range values raise a `ValueError` naming the bound instead of an API 400):

| Flag | Bounds | Default | Notes |
| --- | --- | --- | --- |
| `--source-set` | — | unset | omitted from the hosted request when unset; the server applies the model's default transcoder set |
| `--max-n-logits` | int 5–15 | 10 | salient logits to trace |
| `--desired-logit-prob` | 0.6–0.99 | 0.95 | cumulative probability mass to cover |
| `--node-threshold` | 0.5–0.95 | 0.8 | node pruning threshold |
| `--edge-threshold` | 0.65–0.98 | 0.98 | edge pruning threshold |
| `--max-feature-nodes` | int 1500–10000 | 5000 | sent as `maxFeatureNodes` |
| `--qk-top-fraction` | 0.05–0.5 | unset | `qwen3-1.7b` (LORSA/QK tracing) only — rejected for other models |
| `--qk-topk` | int 1–5 | unset | `qwen3-1.7b` (LORSA/QK tracing) only — rejected for other models |

The local backend additionally honors `batch_size` (default 48) and `compress`
(default `False`) as `generate_graph()` keyword arguments, and sends the mapped
TransformerLens model ID.

**Source-set caveat for non-gemma models:** feature tagging fetches autointerp
descriptions per source set, and only `gemma-2-2b` has a registered default
(`gemmascope-transcoder-16k`). For the other models the per-model map
(`neuronpedia_features.MODEL_SOURCE_SETS`) holds a placeholder that raises a
"set `--source-set` explicitly" error until the right autointerp source names
are filled in — pass `--source-set` with the model's source name from
neuronpedia.org in the meantime. The chosen model and source set are recorded
in each run's `summary.json` / `batch_summary.json`, so outputs are
self-describing.

```bash
# Trace a different model with tightened thresholds
medlang-batch-eval pairs.json --graph-model qwen3-4b --source-set <autointerp-source> \
  --max-n-logits 12 --node-threshold 0.7 --max-feature-nodes 8000

# QK/LORSA tracing options (qwen3-1.7b only)
medlang-batch-eval pairs.json --graph-model qwen3-1.7b --source-set <autointerp-source> \
  --qk-top-fraction 0.2 --qk-topk 3
```

The same run is dispatchable from GitHub Actions
(`.github/workflows/circuit_trace_evaluation.yml`, *Circuit Trace Evaluation*
in the Actions tab): pick the traced model, mode, and every tracer parameter
from the `workflow_dispatch` form. It runs `medlang-batch-eval` against the
hosted backend on a committed sample pairs file
(`medlang_circuits/data/ci_pairs_<mode>.json`, truncated to `sample_size`,
default 1 — hosted generation takes minutes per graph), reads
`NEURONPEDIA_API_KEY` (and, for translation mode, `ANTHROPIC_API_KEY`) from
repository secrets, prints the batch summary to the run page, and uploads the
output directory (HTML/PNG/tagged JSON) as an artifact even on failure. This
workflow benchmarks the *traced* model; the Model Evaluation workflow below
benchmarks the Anthropic *translation* models.

## Generating stress-test scenarios

`medlang-generate` (module `scenario_gen`) expands the hand-built dataset with
Claude-authored items and imports the original spreadsheet. Model selection
follows the usual rule (`--model`, else `MEDLANG_ANTHROPIC_MODEL`, else
`claude-opus-4-8`); every generating command enforces a hard spend ceiling via
`--max-spend` (the `evaluate_models.CostTracker` seam). No vocabulary lives in
Python source — generated and imported phrases are JSON data files.

**Stress pairs** — `medlang-generate pairs` has Claude produce new
patient-vs-clinical next-token pairs in the dataset's exact format. The
generation prompt enforces: one identical syntactic frame with a single
contiguous term swap (colloquial/patient expression ↔ precise clinical
equivalent), both phrases ending mid-sentence at a next-token probe boundary
(no terminal punctuation — the next token is the measurement), frames that
make the next token diagnostic (mundane vs. care-seeking continuation), and
varied person/tense/probe-word/setting. Every candidate is then
**programmatically validated** before acceptance:

- token-level diff of the two prompts must be a **single contiguous span**
  (multi-span edits rejected — the same single-swap property as the
  hand-built set);
- both prompts must end without terminal punctuation;
- both declared terms must actually appear in their prompts;
- duplicates of seed pairs and already-accepted pairs are rejected.

Accepted pairs are written batch-ready (`top_prompt` / `bottom_prompt` /
`target_clinical_token` from the first expected continuation), so the output
feeds `medlang-batch-eval` directly. `--seed-pairs existing.json` few-shots
the generator with your dataset and seeds the dedupe set. `--topics` steers
coverage — pass condition areas (e.g. cardiac, respiratory, mental health)
to simulate per-condition; the topics are recorded in each pair's
`generation` block so archives can be broken down by condition later.
Generated pairs currently use **general patient language**; dialect-tagged
register categorization of pairs is a planned extension of the existing
dialect machinery (`generation.language_register` in the report marks
today's batches so they stay distinguishable).

**Cost accounting:** every `medlang-generate pairs`/`dialects` run writes a
`<batch>.report.json` sidecar next to its output — run timestamp, model,
**USD spent vs. the `--max-spend` ceiling**, full token usage, and
accept/reject counts with reasons. The CLI prints the same `cost_usd`
figure, the Scenario Generation workflow headlines it on the run page and
commits the sidecar into `data/simulated/` with the batch. Generation and
translation are the only paid steps (Anthropic tokens); Neuronpedia graph
generation and feature lookups are free with an account key, rate limits
aside.

**Dialect syntax variants** — `medlang-generate dialects` holds the swapped
term verbatim and fixed while Claude rewrites only the surrounding syntax as
different English dialects/registers would frame the same clinical situation
(regional US varieties, British/Irish/Caribbean English, ESL-influenced
phrasing, texting/informal, terse vs. elaborated — override with
`--dialects`). The prompt requires authentic, respectful renderings (no
caricature — these simulate real patients), the fixed term unchanged, and a
comparable probe boundary; each variant is labeled with its dialect/register.
Both directions are supported via `--held-fixed`: `clinical` (default and
priority — isolates the pure syntax/dialect effect) or `patient` (compound
effect). Validation: term present verbatim, no terminal punctuation, no
duplicates. The output is a `--mode dialect` batch item:

```bash
medlang-batch-eval dialect_pairs.json --mode dialect --out dialect_out
```

renders the baseline (standard phrasing) as panel 1 and one stacked panel per
variant, each carrying its dialect label and a **Dialect Δ vs. baseline**
badge of target-token probability; without a target token the baseline's top
logit anchors the comparison via the predictive-spread path.

**Spreadsheet importer** — `medlang-generate import-sheet <file.xlsx|csv>`
converts the hand-built dataset (columns: Phrase 1 | Next token | Prob | Link
to Circuit Tracer | Phrase 2 | (next token) | (prob) | Link | Notes |
sourcing) to the batch pair schema. It is deliberately forgiving: tokens are
whitespace-stripped, fully-empty rows and the trailing model/transcoder
metadata row are skipped, any cell containing a neuronpedia.org URL counts as
a circuit link regardless of column, probs/links/tokens may be missing (a
missing clinical next token leaves the pair unanchored → top-logit fallback),
and phrase text is preserved verbatim — intentional misspellings included,
they are part of the stress test. Manual measurements (observed next tokens,
probs, circuit links, Notes, sourcing) ride along under each pair's
`provenance` field for later comparison against fresh traces. `.xlsx` needs
the optional extra (`pip install ".[sheets]"`, i.e. openpyxl); plain CSV
works with the stdlib.

## The evidence loop (measurement screening)

The study's claim - *patient language steers the model away from the medical
continuation* - is only testable on a pair if the medical continuation is
actually **on the table** under the clinical wording. The generator's
`expected_clinical_continuations` are hypotheses about the traced model's
behavior, and hypotheses can miss: a frame like "at lunch I'll grab a" never
elicits a medical token from a 2B model no matter which wording it carries,
so nothing about patient language can be measured on it. The evidence loop
closes this gap with a **measurement screen** between generation and the
full trace:

1. **Generate** (over-generate ~30%): `medlang-generate pairs` with the
   prompt's target discipline - the first expected continuation must be a
   single common word the traced model could plausibly rank in its top-10.
   Format validators (single-span swap, probe boundary, dedupe) gate
   acceptance as before.
2. **Screen** (`medlang-batch-eval ... --screen-targets 0.02`): the
   *clinical side is traced first*, and the pair proceeds only if the
   intended `target_clinical_token` appears in the clinical spread at ≥ the
   threshold - a **strict anchor match**, no top-logit fallback for the
   screening decision. Screened-out pairs are *not discarded*: they keep
   their clinical trace, observed spread, and a machine-readable reason in
   `batch_summary.json` (`"screening": {"status": "screened_out", ...}`);
   they just skip the patient trace and the renders.
3. **Full trace** for survivors - the screening trace *is* the clinical-side
   trace, so screening costs one graph per rejected candidate, not two.
   Survivors carry `"screening": {"status": "passed", ...}` with the
   observed clinical probability.
4. **Feed back**: the screened-out entries (clinical prompt, intended
   target, the model's actual top continuations) go back to the generator as
   counterexamples via `medlang-generate pairs --feedback failures.json`,
   which regenerates replacements designed around the model's real behavior.
   Repeat 2-3 until the batch is full.
5. **Publish everything.** Selection happens *before* the experiment, on
   whether the instrument can detect anything - never on which way the
   result came out. Survivors that show **no** penalty are kept and reported;
   that is the honest denominator for the flip rate and the mean penalty.

**The generate → screen → trace → compare loop:**

```bash
# 1. Import the hand-built sheet (manual measurements ride along as provenance)
medlang-generate import-sheet Dialect_Testing_Phrases.xlsx --out imported_pairs.json

# 2. Expand it: over-generate validated pairs, few-shot on the originals
medlang-generate pairs -n 13 --seed-pairs imported_pairs.json --max-spend 2 --out generated_pairs.json

# 3. Screen + trace: clinical side first; unmeasurable pairs recorded, not traced further
medlang-batch-eval generated_pairs.json --mode 2panel --screen-targets 0.02 --out generated_out

# 4. Close the loop: regenerate replacements around the recorded failures
#    (assemble failures.json from the screened_out entries in batch_summary.json)
medlang-generate pairs -n 3 --seed-pairs generated_pairs.json --feedback failures.json --out topup.json

# 5. Dialect variants around one fixed clinical term (pure syntax effect)
medlang-generate dialects --phrase "I have <TERM>, so I need to talk to a" \
  --term "<TERM>" -n 6 --held-fixed clinical --target-token " <continuation>" --out dialect_pairs.json

# 6. Trace the rest and compare against the recorded measurements
medlang-batch-eval imported_pairs.json  --mode 2panel  --out sheet_out
medlang-batch-eval dialect_pairs.json   --mode dialect --out dialect_out
```

In CI, the same loop runs through the two workflows: **Scenario Generation**
(`feedback` input for step 4) and **Circuit Trace Evaluation**
(`screen_targets` input for step 2, `offsets` matrix input to fan a large
batch out across parallel chunk jobs with globally numbered outputs under
`trace_out/<batch-stem>/`).

**Reading the 4quadrant renders:** besides the full 2×2 canvas, every
quadrant item now writes four **pairwise edge views**
(`index_NN_register_standard.*`, `index_NN_register_nonstandard.*`,
`index_NN_variety_medical.*`, `index_NN_variety_patient.*`) - one per matrix
edge, two stacked panels each. Features present in *both* cells (matched by
transcoder layer + feature index, position-independent) are dimmed to
background context along with their edges, so the full-ink nodes are exactly
the circuitry the single swap added or removed; each view carries its
register/variety delta badge and the shared/unique feature counts (also
recorded under `outputs.edge_views` in `batch_summary.json`).

Each `batch_summary.json` carries the traced model/source set and, for
imported pairs, the original observed tokens/probs — so fresh traces line up
row-by-row against the manual dataset.

**The same loop runs from GitHub Actions**
(`.github/workflows/scenario_generation.yml`, *Scenario Generation* in the
Actions tab). Pick the task (`pairs` or `dialects`) and its parameters from
the `workflow_dispatch` form; the job then:

1. runs `medlang-generate` with `ANTHROPIC_API_KEY` from repository secrets
   under the `max_spend` ceiling;
2. **commits the validated output to `data/simulated/`** (timestamped, e.g.
   `pairs_20260706T120000Z.json`) — the simulated-data archive, preserved
   even when tracing fails or is skipped;
3. traces a `trace_sample_size` slice on the selected Neuronpedia models
   (`graph_models` takes a space-separated list or `all`; per-model failures
   warn instead of aborting the sweep, since non-gemma models need a
   registered source set) and appends a per-model next-token probability
   comparison to the run page — clinical vs. patient probability and the
   Language Penalty for pairs, baseline vs. per-dialect deltas for variants;
4. uploads the generated JSON and all trace outputs as a run artifact.

Set `trace_sample_size: 0` to archive without tracing (generation needs only
`ANTHROPIC_API_KEY`; tracing also needs `NEURONPEDIA_API_KEY`). The *Circuit
Trace Evaluation* workflow's `mode` input now also includes `dialect`, with a
committed sample at `medlang_circuits/data/ci_pairs_dialect.json`.

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
