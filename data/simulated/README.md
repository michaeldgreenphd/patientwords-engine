# Simulated scenario archive

Claude-generated stress-test scenarios, committed here by the **Scenario
Generation** GitHub Action (`.github/workflows/scenario_generation.yml`) so
every generated batch is preserved and reproducible.

- `pairs_<UTC timestamp>.json` — patient-vs-clinical stress pairs
  (batch-ready 2panel schema; each pair carries a `generation` block with the
  swapped terms, expected continuations, rationale, and generating model).
- `dialects_<UTC timestamp>.json` — dialect/register variant sets around a
  fixed term (`--mode dialect` batch schema).

These are **simulated data**: LLM-authored phrasings that passed the
programmatic validators in `medlang_circuits/scenario_gen.py` (single
contiguous term swap, probe-boundary endings, term-verbatim checks, dedupe).
They are not patient statements and contain no real personal or clinical
data. The hand-built measured dataset stays outside the repository; its
imported form can be traced locally via `medlang-generate import-sheet`.

Trace any archived file directly:

```bash
medlang-batch-eval data/simulated/pairs_<stamp>.json    --mode 2panel  --out out
medlang-batch-eval data/simulated/dialects_<stamp>.json --mode dialect --out out
```
