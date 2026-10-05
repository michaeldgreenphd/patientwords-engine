# scripts/ — index

One row per top-level `scripts/*.py`: what it is, its status, what it writes,
and who runs it. `tests/test_scripts_readme.py` fails when a script has no
row, when a row names a script that no longer exists, or when a status is not
one of the four below, so add or change the row in the same pull request as
the script.

The package `scripts/petri_audit/` is not indexed here. The `petri-audit` lane
runs it (`python -m scripts.petri_audit.cli`, plus its `readapt.py`,
`rejudge.py` and `summary.py`), and each module's docstring describes it.

Facts are as of 2026-09-30, taken from each script's docstring and from
`.github/workflows/`, `.claude/skills/`, `docs/routine_standing_prompt.md`,
the site's `.github/workflows/site_checks.yml` and git history. A date in the
table is the last commit that changed the output named.

**Status**

- **live**: runs in a current path, meaning a CI lane, the Routine's cycle
  (`docs/routine_standing_prompt.md`), the publish chain
  (`.claude/skills/publish-site-data/SKILL.md`) or the site's CI, or it is
  imported by a script that one of those runs.
- **operator tool**: current, and run by hand when the need comes up; nothing
  schedules it.
- **one-off and done**: did one dated piece of work, which is finished. Kept
  because a committed output or document cites it, or to redo that work.
- **staged**: built and tested, but the path that would run it is not live on
  `main` (for example a workflow kept in `ops/pab_ci/`), or it has never run.

**Who runs it**: the Routine (the scheduled maintenance cycle, with its
section number), a CI lane (by trigger name), the owner, a session (any agent
session, at the owner's request), or the site's CI. "Imported by" marks a
module other scripts load. "Publish chain step N" is a step of the
publish-site-data skill, which the Routine runs in §5 when new results land.

## Ops tooling and the Routine

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `fire_trigger.py` | Fires, parks, resolves and publishes push-to-run triggers with the queue, key and spend guards; `budget-gate` checks a paid fire server-side | live | `.github/trigger/<lane>.json` and a row in `ops/trigger_journal.jsonl`, committed and pushed; the `queue` block of `ops/dashboard.json`, put back unless `--keep-dashboard` | every session that fires, the Routine (§3), and `budget-gate` inside the paid lanes' workflows |
| `ledger_update.py` | Folds new cost sidecars into spend accounting | live | `ops/dashboard.json` (`spend`, Tier B costs) and one bullet per sidecar in the newest `docs/*ledger*.md` (else `docs/spend_ledger.md`) | the Routine (§2a); the only writer of spend numbers |
| `daily_brief.py` | Renders the 3-section brief and the one-line push digest from the dashboard | live | `docs/briefs/brief_<YYYYMMDD>.md` (`--out`); `--digest` prints | the Routine (§7) |
| `drift_sentinel.py` | Day-over-day stability of the hosted tracer on the three frozen sentinel pairs | live | `ops/drift_series.json`; `--site` also writes the site's `data/drift_series.json` | the Routine (§3b) |
| `lens_sentinel_check.py` | The drift sentinel's counterpart for the hosted j-lens readouts | operator tool | `ops/lens_sentinel_series.json` (2026-09-02) | owner or session after a lens sentinel readout lands; the current Routine prompt does not run it |
| `render_archive.py` | Fetches archived PNGs from GitHub Releases by HTTP Range, and reports which PNGs are archived where | live | `fetch` writes under `dist/renders/`; `coverage`, `index` and `shrink-check` print | the Routine (`coverage`, §3d); the `archive-renders` lane (`coverage --require-archived`, `shrink-check`); anyone who needs a PNG (`fetch`) |
| `seal_check.py` | Sweeps the site and the engine's `docs/`, `ops/` and `data/verification/` (the physician task bundles) for any Tier B holdout phrase; a hit is reported as path, `batch#index` and count, never the phrase | live | nothing; exit 0 clean, 1 hit, 2 configuration error | the Routine (§5), publish chain step 8b, the `petri-audit` lane, the holdout-seal-check skill; imported by `tierb_near_twins.py` and `petri_audit/seal.py` |
| `backfill_planner.py` | Printed the next $0 fire per lane for the coverage backfill | one-off and done | nothing (prints `fire_trigger.py` commands) | the Routine and the backfill accelerator (`ops/routines.md` §2) until the backfill closed on 2026-08-26 |
| `backfill_mitigation_costs.py` | Imputed cost sidecars for mitigation runs from before cost capture existed | one-off and done | `trace_out/<run>/mitigation.part_NN.report.json`, each marked `imputed: true` | session, 2026-07-31 (commit dc108c4b) |

## CI lanes

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `logits_eval.py` | CPU next-token measurement for models Neuronpedia cannot trace, in the `batch_summary` schema | live | `trace_out/<stem>__<model>/batch_summary.part_NN.json` | CI lane `logits-eval`; imported by `depth_probe.py` and `verify_probs.py` |
| `depth_probe.py` | Per-layer logit-lens care-urgency tier on CPU | live | `trace_out/depth_k<K>_<stem>__<model>/depth_probe.part_NN.json` | CI lane `logits-eval`, `mode: depth` |
| `verify_probs.py` | A third implementation of the next-token probabilities (interp-engine, float32) | live | `trace_out/verify_<stem>__<model>/verify_summary.part_NN.json` | CI lane `logits-eval`, `mode: verify` |
| `activation_patch.py` | Residual-stream activation-patching grid | live | `trace_out/<stem>__patch[_<model>]/batch_summary.part_NN.json` | CI lane `activation-patching` |
| `jlens_readout.py` | Hosted Jacobian-lens or logit-lens depth readouts per pair | live | `trace_out/<stem>__{jlens,loglens}_<model>/jlens_summary.part_NN.json`, and raw responses with `save_raw` | CI lane `jlens-readout`; imported by `export_jspace.py`, `jlens_position_scan.py` and `jlens_steer.py` |
| `jlens_steer.py` | Lens steering-swap check over a spec | live | `trace_out/<spec stem>__jsteer_<model>/` summary parts and raw responses | CI lane `jlens-readout` with a steering spec; imported by `jsteer_rebuild.py` |
| `translate_corpus.py` | Translates every unique patient sentence, holdout excluded, for the at-scale recovery test (paid) | live | `data/simulated/txcorpus_<stamp>.json` and its `.report.json` | CI lane `scenario-generation`, task `translate_corpus` |
| `advice_eval.py` | The advice arm: stimuli, elicitation, judging, analysis, archive audit and vendor reproducibility packs | live | under `data/advice/` (stimuli, hash-chained responses, judgments, analyses); `repro-pack` writes a pack under `dist/` and appends `ops/disclosure_log.jsonl` | CI lane `advice-eval` (`generate`, `elicit`, `judge`, `analyze`, `verify-chain`, `recover-archive`); owner or session for `build-stimuli`, `import-manual-responses` and `repro-pack` |
| `archive_run.py` | Zips run renders with a manifest | live | `dist/<tag>.zip` and its manifest; the lane commits `render_archives/<tag>.manifest.json` and uploads the zip to a Release | CI lane `archive-renders` |

## Publish chain

In the skill's order. Every step also runs by hand under the same skill.
Where a row says "and the site copy", the script writes the site copy by
default (`--site ../patientwords`), and `--site ''` skips it.

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `export_frontend_simulated.py` | Merges every model's trace dirs per batch into the site payload and prunes renders no export lists | live | the site's `data/simulated_scenarios.json` and `modes/simulated/` renders (adds, and deletes unlisted ones) | publish chain step 1 |
| `urgency_shift.py` | The collector: care-urgency tiers, flip classes, the translated panel's recovery | live | `urgency_shift.json` at the engine root (the row file); `--publish <site>` also writes the site's `data/urgency_shift.json` | publish chain step 2 |
| `jlens_insights.py` | Formation-depth analytics from the J-lens summaries (exploratory) | live | `ops/jlens_insights.json`; `--site` also writes the site copy | publish chain step 3; imported by `export_jlens_loglens.py` |
| `export_jlens_depth.py` | The depth-readout sections' dataset | live | `data/jlens_depth.json` and the site copy | publish chain step 3 |
| `export_jlens_transport.py` | The per-position transport dataset | live | `data/jlens_transport.json` and the site copy | publish chain step 3 |
| `export_jlens_loglens.py` | The lens-robustness dataset | live | `data/jlens_loglens.json` and the site copy | publish chain step 3 |
| `export_pair_swaps.py` | Per-pair patient swap and baseline sentence for the census table; withholds holdout rows | live | `data/jlens_swaps.json` and the site copy | publish chain step 3 |
| `export_tag_mass.py` | Mean attribution-mass shares for the tagging bars | live | `data/tag_mass.json` and the site copy | publish chain step 3 (addendum) |
| `export_jspace.py` | The J-space worked example | live | `data/jspace.json`; `--site` also writes the site copy | publish chain step 3 (addendum) |
| `export_traces_site.py` | Stamps each scenario's `trace_url`, and copies renders to the traces Pages repo | live | `trace_url` in the site's `data/simulated_scenarios.json` (`--stamp-only`, as the chain runs it); without `--stamp-only`, render copies in `../patientwords-traces` | publish chain step 4 |
| `translation_scale.py` | Per-model translation recovery from the txcorpus runs | live | `ops/translation_scale.json`; `--site` also writes the site copy | publish chain step 5, only when txcorpus results land |
| `coverage_gaps.py` | Corpus coverage by specialty and tier, and `steer_topics` for the next generation fire | live | `ops/coverage_gaps.json` | publish chain step 6 |
| `validate_frontend_contract.py` | Checks every site payload's structure against what the pages read | live | nothing; exit 0 holds, 1 violations, 2 payload missing | publish chain step 7, the Routine (§5), and the site's CI on every push and pull request |
| `claim_check.py` | Checks numbers written into site prose against their data expressions (`data/claims_manifest.json`) | live | nothing; exit 1 on drift | publish chain step 8 |
| `check_pages.py` | Loads every published page in Chromium and fails on script errors, failed requests or a visible empty table | live | nothing (`--json` writes a report) | the site's CI on every push and pull request; owner or session by hand |

`seal_check.py` (step 8b) is listed under ops tooling.

## Shared modules

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `tierb_split.py` | The single implementation of the Tier B holdout split | live | nothing | imported by the exporters, the collector, `seal_check.py` and every script that excludes holdout rows |
| `urgency_unjoinable.py` | Counts the published urgency rows that join no published scenario, by cause (counts and batch stems only), and reads the site payload it counts against | live | nothing itself | imported by `urgency_shift.py` (`--publish`, which writes the counts as `unjoinable_rows`); `validate_frontend_contract.py` keeps its own copy of the cause names, and a test checks that the two agree |
| `sign_test_exact.py` | The exact two-sided sign test shared by the urgency analyses, unrounded, None when there are no directional pairs | live | nothing | imported by `urgency_shift.py`, `tier_sensitivity.py` and `paired_stats_rigor.py` (and through it `negative_control_stats.py`) |
| `provenance_stamp.py` | Adds a `_provenance` block (script, engine commit with a `+dirty` marker, UTC time) to a payload | live | nothing itself | imported by 13 generators, among them `drift_sentinel.py`, `paired_stats_rigor.py` and `convergence_tracker.py` |
| `payload_summary.py` | The one definition of the site payload's headline `summary` | live | nothing itself | imported by `export_frontend_simulated.py` |
| `render_prune.py` | Chooses and deletes site renders that no export lists | live | deletes files under the site's `modes/simulated/` | imported by `export_frontend_simulated.py` |
| `sparse_guard.py` | Lists tracked files a checkout keeps off disk, so tools refuse a sparse site checkout | live | nothing | imported by `render_prune.py` and `seal_check.py` |

## Site data written outside the publish chain

None of these is in the publish-site-data skill. The first five ran in the
Routine's publish pass during the active study (the 2026-08-20 republish, site
commit d563f5e, ran all five); the maintenance rewrite of 2026-08-29 left them
out.

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `paired_stats_rigor.py` | The pre-registered statistics over the collector output: phrase dedupe, bootstrap intervals, sign tests, seed recorded | operator tool | `paired_stats_rigor.json` at the engine root and, by default, the site's `data/model_stats.json` (both 2026-08-29; `--site ''` skips the site file) | owner or session; imported by `negative_control_stats.py` |
| `convergence_tracker.py` | Per-model cumulative penalty estimates, batch by batch | operator tool | `data/convergence.json` and the site copy (2026-08-29) | owner or session |
| `embed_scenario_joins.py` | Embeds the urgency and depth joins, `urgency_meta`, the redirect-gallery `featured` list and the editorial pins into the site payload | operator tool | the site's `data/simulated_scenarios.json`, in place | owner or session; `export_frontend_simulated.py` rewrites the payload without these fields, so it has to run after every republish |
| `export_archive.py` | The flat per-(pair x model) collaborator CSV and JSON; withholds holdout rows | operator tool | `<out>.csv` and `<out>.json` (default `archive_export.*`); the site's `data/simulated_archive.*` came from it (2026-08-20) | owner or session |
| `retrace_consistency.py` | Test-retest spread for identical prompt pairs traced more than once | operator tool | `--out`, default `ops/retrace_consistency.json` (2026-07-17); the site's copy (2026-08-20) differs, see `ops/README.md` | owner or session |
| `specialty_breakdown.py` | Penalty by medical specialty (exploratory) | operator tool | `--out`, default `ops/specialty_breakdown.json` (2026-07-16); the site's copy (2026-07-14) differs | owner or session |
| `study_timeline.py` | The study timeline, from committed artifacts | operator tool | `data/timeline.json` and the site copy (2026-08-20) | owner or session |
| `patch_aggregate.py` | Per-layer recovery profile from the activation-patching grids | operator tool | `data/patch_profile.json`; `--site` also writes the site copy (2026-07-14) | owner or session, after a patching grid lands |
| `export_advice_scenarios.py` | The advice archive as the LLM responses page's payload; refuses on a broken hash chain | operator tool | `data/advice_scenarios.json`; `--site` also writes the site copy (2026-08-24) | owner or session, after advice runs land |
| `export_judge_agreement.py` | Inter-judge tier agreement for the methods page | operator tool | `data/judge_agreement.json`; `--site` also writes the site copy (2026-08-24) | owner or session; `docs/operators_handbook.md` lists it |
| `export_stress_featured.py` | Precomputes the home teaser's top picks into the site's `stress_pairs.json` | operator tool | the `featured` block of the site's `data/stress_pairs.json`, pairs unchanged (2026-07-21) | owner or session, whenever that file's pairs change |
| `export_dialect_matrix.py` | A dialect sweep's trace as the dialect page's dataset | operator tool | `--out`, the site's `data/dialects.json` (2026-07-30) | owner or session, after a dialect sweep lands |
| `dialect_invariant_core.py` | Adds each term's dialect-invariant clinical core, computed from committed renders | operator tool | the `--dialects-json` file, in place (the site's `data/dialects.json`) | owner or session, after `export_dialect_matrix.py` |
| `render_demo.py` | Regenerates the gallery's hand-authored demonstration figures | operator tool | the site's `modes/2panel/` and `modes/translation/` (`index.html`, `preview.png`) | owner or session |
| `advice_human_coding.py` | The blinded human-coding sample and the judge-vs-human agreement score | one-off and done | `build-sample`: `data/advice_coding_sample.json` (`--site` also writes the site copy) and `data/advice/human/coding_keymap.json`; `score`: `data/advice/human/agreement_report.json` | owner and session, 2026-07-28 |

## Analysis and checks

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `paired_stats.py` | Paired cross-model statistics on the unified phrase set, and validity against the hand-measured pairs | operator tool | `--out`, default `paired_stats.json` (the committed `paired_stats.json` and `paired_stats_out.json` are from 2026-07-08) | owner or session; the published per-model numbers come from `paired_stats_rigor.py` |
| `backend_agreement.py` | Whether two measurement backends report the same numbers for the same pairs | operator tool | `--out` (the `ops/backend_agreement_*` files, 2026-09-03 and 2026-09-04) | owner or session |
| `jlens_position_scan.py` | Per-position lens transport and top-K window sensitivity, from saved raw responses | live | `ops/jlens_position_scan.json` from its CLI (2026-07-14) | imported by `export_jlens_transport.py` (publish chain step 3); the CLI by owner or session |
| `negative_control_stats.py` | Statistics of the 2026-09-04 negative control, seed recorded | one-off and done | `--out`: `ops/negative_control_20260904.json` (seed 7) | session, 2026-09-04 |
| `advice_rerun_select.py` | Ranks earlier advice stimuli by how many models downgraded them (primary judge, Gemini arms not counted) with a seeded permutation null, and writes a post-hoc ranking report plus the selection that `advice_eval.py build-stimuli --source selection` reads; refuses malformed judgment rows | operator tool | `--report-out` and `--selection-out`, two new files under `data/advice/` that it refuses to overwrite: the report `data/advice/rerun_ranking_20261002.json` (every metric; seed 11) and the selection `data/advice/rerun_selection_20261002.json` (`rule`, `items` as `file` and `id`, `notes`) | session, 2026-10-02; owner or session to re-rank |
| `build_control_pairs.py` | Builds the negative control's pairs files from a measured batch | one-off and done | `--out`: `data/simulated/control_{identity,qualified}_20260710T011743Z.json` | session, 2026-09-04 |
| `screen_sensitivity.py` | Whether the 0.02 screening threshold moves the headline penalty | one-off and done | `ops/screen_sensitivity.json` (2026-07-14) | session, 2026-07-14 |
| `tier_sensitivity.py` | Whether the downgrade asymmetry survives re-tiering the flagged vocabulary | one-off and done | `ops/tier_sensitivity.json` (2026-07-30) | session, 2026-07-30 |
| `tierb_near_twins.py` | The frozen near-twin list for the Tier B holdout readout (Amendment 5) | one-off and done | `data/tierb_near_twins.json` (frozen 2026-09-24); `--check` recomputes and compares, writing nothing | session, 2026-09-23 and 2026-09-24; `--check` to re-verify the list |
| `interp_analyses.py` | Four post-hoc interpretability analyses behind `docs/findings_synthesis.md` | one-off and done | `--out` (the bundle that document cites, `docs/analyses_20260708.json`) | session, 2026-07-08 |
| `referral_destination.py` | Whether a question's register changes how often the reply names a specialist service | operator tool | `--out`, default `referral_destination.json`; no output committed | owner or session |
| `find_grammar_2x2.py` | Searched committed data for a grammar-only 2x2 case for the Wording Differences page | one-off and done | nothing (prints) | session, 2026-07-19 |
| `readability_report.py` | Reading-grade worklist of the site's pages | one-off and done | `docs/readability_report.md` (2026-07-13) | session |
| `extract_site_text.py` | Extracts the site's page text into one Rmd for the owner's editing | operator tool | `ops/site_text_outline.Rmd` (default) | owner or session, on request |

## Builders

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `build_floor_seed.py` | The seed file for a paraphrase-floor expansion fire, excluding landed baselines and the holdout | one-off and done | `data/seeds/floor_seed_20260723.json` and its `.meta.json` | session, 2026-07-23 |
| `build_patient_lexicon.py` | A reviewable lay-to-clinical lexicon draft from the CHV flatfiles | one-off and done | `data/patient_lexicon.draft.json`, `data/misspelling_candidates.draft.json` | session, 2026-07-13 |
| `build_steer_spec.py` | The steering-100 spec | one-off and done | `data/steer_spec_100_20260728.json` | session, 2026-07-28 |
| `derive_context_pairs.py` | Context-inoculation pairs from a 2panel batch | one-off and done | `<batch>__context.json` and `.report.json` beside the source (`data/simulated/urgency_downgrades_20260707T1__context.*`) | session, 2026-07-07 |
| `jsteer_rebuild.py` | Rebuilds lost steering summary rows from committed raw responses, never overwriting a part | operator tool | the missing `jsteer_summary` parts | owner or session, when a steering run dies before its summary flush (first used 2026-07-28) |

## PatientAgentBench integration

The PAB probe lane's workflow exists only on the PAB branch; a staged copy is
in `ops/pab_ci/`.

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `validate_pab_contract.py` | Checks a PAB run directory is fit to analyse | staged | nothing (prints); the committed `data/pab/pab_contract_*.json` are its `--json` output (2026-08-04) | the PAB probe lane's analyze stage, on the PAB branch; by hand, before any PAB analysis |
| `pab_literacy_shift.py` | Per-model behaviour change between the low- and high-literacy arms of one case | staged | `--csv` rows (`data/pab/pab_rows_*.csv`); the `data/pab/pab_literacy_shift_*.json` files are its `--json` output (2026-08-04) | the PAB probe lane's analyze stage, on the PAB branch |
| `pab_harvest_utterances.py` | Harvests paired patient utterances from PAB transcripts | one-off and done | `data/pab/pab_harvest_20260807T021948Z.json` | session, 2026-08-07 |
| `pab_build_frames.py` | Builds 2panel batch entries from harvested utterances | one-off and done | `data/pab/pabharvest_20260807T025446Z.json` and its `.build.json` | session, 2026-08-07 |
| `pab_tier_scenario.py` | The urgency analysis under a PAB-anchored tier ladder, as a sensitivity scenario | one-off and done | `ops/pab_tier_scenario.json` (2026-08-04) | session, 2026-08-04 |
| `pab_tier_crosswalk.py` | The pre-registered crosswalk between the draft urgency lexicon and PAB's triage rubric | staged | `ops/pab_crosswalk_<stamp>.json`; none has been committed on any branch | owner or session, per `docs/pab_handoff_20260804.md` |
| `pab_probe_cost.py` | Cost estimate for a PAB trait-sweep probe before it is fired | operator tool | nothing (prints) | owner or session |

## Petri wave 2

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `petri_w2_register_contrast.py` | The pre-registered register-contrast analysis (design note section 10) | one-off and done | with `--final`, `--out` (`data/petri/w2_register_contrast.json`), never overwritten | run once, 2026-09-25 (commit 03c6d375) |
| `export_petri_multiturn.py` | The Multi-turn page's data from the landed wave-2 runs and the section 10 artifact | one-off and done | the site's `data/petri_multiturn_summary.json` and `data/petri_multiturn_conversations.json` (published 2026-09-27); `--write-samples` writes their `.sample.json` fixtures | owner, once (its docstring); not part of the Routine |
| `petri_multiturn_synthetic.py` | Synthetic wave-2 runs and section 10 artifact for tests and fixtures | operator tool | nothing itself | imported by `tests/test_export_petri_multiturn.py`, and by `export_petri_multiturn.py --write-samples` when owner or session regenerates the sample fixtures; no scheduled path runs it |
| `petri_three_arm.py` | Exploratory three-arm and crossed-factorial comparisons over wave-2 runs | operator tool | an optional report file; none committed | owner or session |
| `petri_w2_power_sim.py` | Design-only power simulation for the register contrast | one-off and done | nothing (prints JSON that records its seed) | session; `docs/petri_wave2_design.md` quotes its numbers |

## Physician verification

The task bundle for the physician verification app, whose code is in the
private repository `michaeldgreenphd/patientwords-verify`, and the import of
the ratings the app exports. `docs/verification_protocol.md` is the protocol.

| Script | What it does | Status | Writes | Who runs it |
|---|---|---|---|---|
| `export_verification_tasks.py` | The items physicians rate, blind to source: pairs from each finalized version-2 pilot run named with `--pilot-run` (default Run 2's 40 traced pairs; its review sample or every non-control row, a trace result required unless `--pilot-trace-optional`, read for the graph model `--pilot-trace-model` names or else the one model with results), the published main-study pairs with the largest language penalty, the 2026-10-02 advice stimuli and the Petri wave-3 scripts, with the question wording from `data/verification/questions.json`; refuses (writing nothing) on a missing input, an unknown field, a changed text, a run that is not finalized or not version 2, a trace pairs file not named after its run (`<run id>_<name>.json`) or sharing a stem with another run's, a second trace pairs file under a run (Run 2's byte-identical copy excepted), a missing required trace, trace results for two graph models with none named, any holdout-seal hit, or (with `--previous-bundle`, for a later round) a previous round's item or question id it would drop or change, a kept question id whose scale, answer values, phase, requirement or reveal lock changed, or another notes limit | operator tool | `--out-dir`, default `data/verification/`: a new `tasks_<stamp>.json` it refuses to overwrite, its seed recorded inside | owner or session, before each upload to the app; then `seal_check.py`, whose default roots include `data/verification/` (so the daily sweep re-checks every committed bundle) |
| `import_verification_ratings.py` | Reads the app's ratings export, kept outside the repository, against the bundle it names and the questions file (refusing, writing nothing, on an export inside the checkout, a sha256 mismatch, an unknown id or value, a field outside the export schema or any identity data); derives current, first and reveal-time blind answers; computes Krippendorff's alpha (ordinal or nominal) with a seeded item-level bootstrap, a post-reveal sensitivity analysis, per-item realism flags and the proposed combined urgency tier; counts notes, never copies them | operator tool | `--out-dir`, default `data/verification/`: `ratings_<bundle_id>_<export stamp>.summary.json` and `.md`, and with `--write-proposed-adjudication` a `.proposed_adjudication.json` (the shape `advice_eval.py analyze --stimuli` reads; rater codes in `proposed_by`, not `adjudicated_by`, so `analyze` scores it `claim_grade: false`); never replaces an output silently; seed and resamples recorded | owner or session, when the owner hands over an export |
