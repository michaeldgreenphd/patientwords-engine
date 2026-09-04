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

## Result (2026-07-13, per the frozen analysis above)

All 60 designed traces landed (20 pairs x 3 independent CI runs). Two
operational notes, disclosed: runs r1 and r2 required fill-in chunks after
the workflow's 45-minute chunk timeout truncated chunk-final pairs (the
timeout is now 75 minutes; commit daa46fb), and where a chunk was re-run
the analysis uses one measurement per run as designed.

- Differences observed: **0 of 60 designed repeat-traces.** Probabilities
  (at the recorded 3-decimal precision), top words, full top-k spread
  lists, and clinical_mass under identical graph parameters were identical
  across all three runs for all 20 pairs.
- Rule-of-three 95% upper bound on the per-trace difference rate,
  designed sample alone: 3/60 = 5.0%.
- Pooled with the opportunistic record: 68 distinct pairs now traced 2-12
  times with zero differences on every compared quantity
  (ops/retrace_consistency.json).

The pre-declared commitment was that any nonzero difference publishes
as-is; the observed difference count is zero, and that publishes as-is
too. The claim stays scoped: determinism at recorded precision on the
frozen model via the hosted tracer, not a guarantee against future
service-side change (the daily sentinel watches for that).
