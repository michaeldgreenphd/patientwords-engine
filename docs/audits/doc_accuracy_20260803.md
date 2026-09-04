# Doc-accuracy sweep — 2026-08-03 (Monday, standing prompt §2b)

Mechanical cross-checks only; drift is reported, not fixed here.

## 1 · fire_trigger TRIGGERS ↔ .github/trigger/ ↔ workflows — CLEAN
All 8 trigger keys have a trigger file and a workflow that reads it; no orphans
either way.

## 2 · KNOWN_KEYS ↔ push-path defaults — CLEAN (7/8), one N/A
Every key in `fire_trigger.KNOWN_KEYS` appears in its workflow's push-path
`defaults` dict for activation-patching, advice-eval, circuit-trace,
jlens-readout, logits-eval, model-evaluation, scenario-generation.
`archive-renders` has no defaults dict (different workflow shape) — not drift,
but it means the CLAUDE.md pitfall note ("push-path defaults must contain every
trigger key") does not apply uniformly. **Method note for future sweeps:** check
the push-path `defaults` dict, NOT `workflow_dispatch.inputs`. Checking the
latter reports ~10 false positives on circuit-trace alone (the steer_*,
translation_*, graph_models keys are push-path only).

## 3 · Site data inventory ↔ frontend CLAUDE.md data contracts — DRIFT (21 files)
These live in `../patientwords/data/` and are consumed by page JS, but are not
named in the frontend CLAUDE.md "Data contracts" section:

advice_coding_sample.json, advice_coding_sample.sample.json,
advice_scenarios.json, advice_scenarios.sample.json, advice_scenarios_nat.json,
display_vocab.json, drift_series.json, jlens_depth.json, jlens_insights.json,
jlens_loglens.json, jlens_swaps.json, jspace.json, model_provenance.json,
patch_profile.json, retrace_consistency.json, simulated_archive.json,
specialties.json, specialty_breakdown.json, tag_mass.json,
translation_scale.json

Impact: a new session reading the frontend CLAUDE.md would not learn that the
advice arm, the j-lens chain, or the drift series have published contracts —
the exact "which files does a page depend on" question the section exists to
answer. Not urgent (nothing is broken), but it is the single largest doc gap in
either repo. Fix belongs in a normal work session, not a sweep.

## 4 · extract_site_text.py PAGES ↔ live pages — CLEAN
10 pages extracted, 371 blocks, matching the deployed set.
