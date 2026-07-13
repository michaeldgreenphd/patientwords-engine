# Designed repeatability sample (pre-declared 2026-07-13, before any run fired)

Purpose: upgrade the instrument-repeatability record from opportunistic
(52 pairs that happened to be re-traced) to designed. The claim under test:
the hosted tracer reproduces probabilities, top-five lists, and same-settings
clinical-mass shares at recorded precision on repeated input.

## Design, frozen before firing
- 20 pairs, stratified random, seed 7 (`repeatability_sample_manifest.json`):
  5 gemma-2-2b downgrades, 5 other flips, 5 holds with p_clinical >= 0.5,
  5 holds with p_clinical < 0.2. Pair objects copied verbatim from their
  source archives.
- 3 fresh traces per pair in three separate CI runs (aliases
  `repeatability_r1/r2/r3.json`, distinct output dirs), standard 2panel
  settings, no screening. The daily sentinel separately covers the
  across-days axis.
- Analysis: `scripts/retrace_consistency.py`, unchanged, at recorded
  precision (3 decimals). Reported number: differences observed out of 60
  designed repeat-traces, with the rule-of-three 95% upper bound on the
  per-trace difference rate, pooled with the opportunistic record and also
  reported alone. Any nonzero difference publishes as-is.
