# medlang-circuits

Pipeline for comparing attribution graphs of two phrasings of the same next-token
prompt (standard clinical terminology vs. colloquial patient language) on
gemma-2-2b with Gemma Scope transcoders. Built on Neuronpedia's graph stack —
either the hosted neuronpedia.org generation API or a local `apps/graph`
circuit-tracer server.

## What it does

1. **Feature tagging (Task 1)** — `feature_tagger.annotate_graph` post-processes a
   graph JSON (schema: `apps/webapp/app/api/graph/graph-schema.json`): it fetches
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

## Setup

```bash
cd apps/experiments/medlang-circuits
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
| `GRAPH_SERVER_SECRET`, `GRAPH_SERVER_URL` | `--backend local` (a running `apps/graph` server) |
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

## Tests

```bash
poetry run pytest tests/ -v
```

Tests use synthetic graphs, a stubbed feature fetcher, and abstract placeholder
vocabulary — no network or API keys required.
