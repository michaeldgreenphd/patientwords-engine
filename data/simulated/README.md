# Simulated scenario archive

Claude-generated stress-test scenarios, committed here by the **Scenario
Generation** GitHub Action (`.github/workflows/scenario_generation.yml`) so
every generated batch is preserved and reproducible.

- `pairs_<UTC timestamp>.json` — patient-vs-clinical stress pairs
  (batch-ready 2panel schema; each pair carries a `generation` block with the
  swapped terms, expected continuations, rationale, steering topics, and
  generating model).
- `quadrants_<UTC timestamp>.json` — 4-quadrant items for the generic
  morphosyntax-×-lexicon matrix: a standard/nonstandard frame pair with a
  single `{term}` slot crossed with a medical/patient term pair
  (`--mode 4quadrant` batch schema; A prestige form, B variety shift only,
  C register shift only, D both axes shifted).
- `dialects_<UTC timestamp>.json` — dialect/register variant sets around a
  fixed term (`--mode dialect` batch schema).
- `*.report.json` — the cost/provenance sidecar for each batch: run
  timestamp, Anthropic model, **USD spent vs. the ceiling**, token usage,
  accept/reject counts with rejection reasons, and the run's steering
  parameters. Sum the `cost_usd` fields across sidecars for the archive's
  total generation cost. (Neuronpedia tracing itself is free — account rate
  limits only.)

These are **simulated data**: LLM-authored phrasings that passed the
programmatic validators in `medlang_circuits/scenario_gen.py` (single
contiguous term swap, probe-boundary endings, term-verbatim checks, dedupe).
They are not patient statements and contain no real personal or clinical
data. The hand-built measured dataset (imported from the spreadsheet via
`medlang-generate import-sheet`, manual measurements under `provenance`)
lives separately in `data/measured/imported_pairs.json`.

Trace any archived file directly:

```bash
medlang-batch-eval data/simulated/pairs_<stamp>.json    --mode 2panel  --out out
medlang-batch-eval data/simulated/dialects_<stamp>.json --mode dialect --out out
```
