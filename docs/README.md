# docs/ — index

What is in this folder and which files must stay where they are. Paths are
relative to the repository root. Written 2026-09-30; add a line here when you
add a document.

## Start here

| File | What it is |
|---|---|
| `AGENTS.md` (repository root) | The rules every agent and reviewer works from. |
| `verify.md` (repository root) | Canonical developer setup, change-specific verification and evidence requirements. |
| `docs/agent_reference.md` | Detailed architecture, operational rules, research limitations and review decisions linked from AGENTS.md. |
| `docs/start_here.md` | One route into the project: reading paths for a new researcher, a frontend contributor, a method developer and an operator; the offline quickstart; the pointer path for model execution; known stale navigation. |
| `docs/ecosystem.md` | Current map of the repositories, forks and external services (2026-11-10): what the engine consumes from each and as what type, the recorded heads against the executed pins, two identifier traces (one real result; the synthetic boundary check), test coverage, and a prioritised findings table with evidence and status. Machine-readable form: `data/ecosystem/repositories.v1.json`, checked by `scripts/ecosystem_status.py`. |
| `docs/upgrade_checklist.md` | Repeatable procedure for syncing a fork without losing local patches and for evaluating a runtime pin change in isolation (interp-engine, Petri and Inspect): the checks to run, the parity record, one pin per commit, and the manifest update. States that the 2026-11-10 fork sync was not a runtime migration. |
| `docs/contributing_a_method.md` | The contribution path for a new interpretability or behavioural method: metadata, a typed result, capability declarations with evidence, a fixture, verification, publication eligibility, isolated dependencies and attribution. |
| `docs/architecture_decision_20261110.md` | Decision record: a coordinated multi-repository workspace with the engine owning the workflow, the alternatives considered, and when to revisit. |
| `docs/migration_record_20261110.md` | Paths and interfaces the 2026-11-10 change set adds, their consumers and rollback, and the checks that legacy commands and URLs still work. |
| `docs/scaling_plan_20261110.md` | Scaling plan (2026-11-10): every measured rate with its source and sample size, what is not measured and how to measure it, stage separation, labelled estimates for three grid sizes (CPU-logits time, activation, ICA-fit, logits and weight storage), the eight-point path from the current CI system, the release-latency metric and its baseline, what not to add with proposed thresholds, and the candidate dependency-upgrade checks. No model was run. |
| `docs/exploratory/first_model_run_packet_20261110.md` | Pending execution packet, not run: `gemma-2-2b` on the existing `logits-eval` lane (fresh float32 parity at the pinned revision, then the one reviewed case under the pilot root). Exact inputs by `(batch, batch_index)` and prompt SHA-256; model and artifact identities with where each was read; the committed stage A protocol (`data/experiments/protocols/`, 3 of 10 rows) with its plan preview pinned by `tests/test_first_run_packet.py`; parity criteria written before any run; the resource estimate; the changes needed before the run; the route and approvals; the smallest next step for a real activation capture and an ICA basis; the decisions for the owner. Authorizes nothing. |
| `docs/experiment_interface/README.md` | The shared experiment interface (`scripts/experiments/`): one run envelope around typed payloads, the deterministic planner, the run store with resume and reuse, the capability matrix, and what was and was not verified. With `docs/experiment_interface/ica_adapter.md` (the optional ICA adapter on the ActivationDataset interchange) and `docs/experiment_interface/neuronpedia.md` (the Neuronpedia identity and link boundary: the representation registry with its verification and reference statuses, exact links and reference links, the offline fallback, the graph-interchange contract plan, and the list of sources that could not be read on 2026-11-10) and `docs/experiment_interface/preview.md` (the browser preview of the synthetic experiment bundle: procedure, what `scripts/check_experiment_preview.py` verifies and does not, findings, and what a real bundle needs before it is publishable). |
| `docs/open_results_policy.md` | Current rule for what is shared and what an analysis reads: six independent facts per part, the three memberships, the restrictions that remain, the catalogue and the snapshots. Replaces the 2026-10-09 publication hold. |
| `docs/open_results_migration_20261110.md` | Dated record of the move to the open-results policy: counts of what became visible and what stays restricted, the byte-identity check of the collector, and what the statistics would become under the exploratory membership. |
| `docs/corrections/payload_summary_dedupe_20261110.md` | Correction record for the gallery payload's `summary.penalty` (2026-11-10): every difference a full re-export makes, in three kinds (bug correction, changed inputs, expanded population); why the site's published model statistics file differs from a recomputation; the 11 legacy payload rows; the two releases (the correction alone, then the full re-export) and the owner decisions. Since 2026-11-11 section 8 is the decision record for D1 to D4, with the D4 choices in numbers, and section 7 names the check that refuses the undecided differences (`scripts/payload_dispositions.py`, `data/results_policy/payload_dispositions.v1.json`). |
| `docs/exploratory/frontend_boundary.md` | Existing synthetic exporter-to-HTTP-to-browser slice, schema/client authority and evidence limits. |
| `docs/exploratory/action_transport.md` | Single-attempt transport, raw receipt contract and remaining CI admission requirements; no active execution route. |
| `docs/exploratory/action_annotations.md` | Offline evidence-linked action annotation contract, synthetic rehearsal and separately gated API pilot plan. |
| `docs/exploratory/method_readiness_20261024.md` | Dated method wiring/pin check and remaining gates; no upgrade or retrospective remeasurement. |
| `docs/exploratory/judge_register_sensitivity_20261106.md` | Exploratory: wave 2's registered register contrast re-run under the GPT-5.4 mini and Haiku 5.5 re-grades, and single-turn judge agreement with the human coder and with Jev split by arm (`scripts/judge_register_sensitivity.py`). |
| `docs/exploratory/register_style_results_20261108.md` | Exploratory: results of the style-vs-vocabulary sub-study (files A and B, seven models, 2026-11-08): no difference detected after Holm; sensitivity analyses and the added truncation analysis (`scripts/register_style_analysis.py`). |
| `docs/exploratory/comma_test_plan_20261109.md` | Exploratory: the comma test's analysis plan, fixed before any trace (engine #158). |
| `docs/exploratory/comma_test_results_20261109.md` | Exploratory: comma test results (18 pairs, 13 clinical-sentence units, seven models, 2026-11-09): no difference detected (`scripts/comma_test_analysis.py`). |
| `docs/preregistration_advice_register_style.md` | Signed 2026-11-08: preregistration of the single-turn style-vs-vocabulary test (clinical, careful lay, colloquial wordings of 56 situations); stimulus files A and B are named in its Procedure. |
| `docs/exploratory/structured_lay_design_20261106.md` | Draft design, not run: a colloquial third wording for the 56 rewrite-style advice situations (corrected 2026-11-06: their patient bodies are already careful lay), to separate style from vocabulary in single-turn advice, with an analysis plan to preregister and a cost estimate. |
| `docs/exploratory/pab_endpoints_20261106.md` | Exploratory: the PAB frame spec's two preregistered endpoints on the 52 traced entries (neither supported on 13 pairs), and the census guard that keeps harvested text out of exemplars (`scripts/pab_endpoints.py`). |
| `docs/exploratory/pab_followup_design_20261106.md` | Draft design, not run: report the PAB frame spec's preregistered endpoints on the 52 traced entries, then the logits lane and a cumulative-context amendment. |
| `docs/exploratory/xjudge_20261031.md` | Exploratory cross-vendor judging (campaign `xjudge-v1`) and the equity v2 pilot on Claude Haiku 4.5 and GPT-5.4 mini: judge agreement, the judge-by-target shift, advice after the warning sign, and owner decisions. |
| `docs/exploratory/review_preparation_20261016.md` | Final review heads, push/PR safety audit, tests and remaining execution blockers. |
| `docs/exploratory/baseline_ci.md` | Manual-only baseline wiring, blocked readiness, owner/default-branch prerequisites and later dispatch inputs. |
| `docs/exploratory/communication_plan.md` | Draft public question, endpoint-safe explanations, selection policy and later comprehension checklist. |
| `docs/exploratory/case_report_mapping.md` | Communication sections mapped to existing manifests and exact metric fields. |
| `docs/exploratory/one_case_storyboard.md` | Text-only walkthrough of the frozen reviewed case, with every real-model stage not run. |
| `docs/exploratory/local_preparation_20261015.md` | Bounded local installation and complete lens-integrity receipt; separate provenance, compatibility and parity readiness. |
| `docs/exploratory/baseline_preflight.md` | Prepared lens-independent one-case CI baseline check, prospective gates and future execution commands; not launched. |
| `docs/exploratory/lens_fit_provenance_question.md` | Unsent question requesting historical released-lens fit records. |
| `docs/operators_handbook.md` | Procedures and case law for running the ops system. |
| `docs/triggers.md` | Every push-to-run lane, its trigger keys and what it spends. |
| `docs/routine_standing_prompt.md` | The scheduled maintenance Routine's instructions, read at every firing. |
| `docs/fresh_session_bootstrap.md` | Repairing a checkout a cloud container materialized badly. |
| `docs/archiving.md` | Render archives: GitHub Releases, manifests, fetching one render back. |
| `docs/pilot_runs.md` | How the pilot scripts select, guard and re-seal a run directory: the mechanics behind `AGENTS.md`'s pilot exception. |

## Read by code, records or the site: do not move

Moving or renaming any of these breaks a program or a test, or leaves a landed
record, a message or a public link pointing at nothing. Verified 2026-09-30 by
`git grep` in both repositories.

| Path | What reads or cites it |
|---|---|
| `docs/framework/` (all of it) | `.github/workflows/petri_audit.yml` names the seeds file and reads the environment lock, and `PARK_DEFAULTS` in `scripts/fire_trigger.py` names the seeds file; `scripts/petri_audit/`, `scripts/petri_three_arm.py` and the tests read its seeds, prompts and schemas; landed Petri records under `data/petri/` cite its paths and hashes; the site's Multi-turn page cites `docs/framework/outcome_dimensions.draft.json`. |
| `docs/petri_repro_pack_readme_template.md`, `docs/petri_repro_pack_disclosure_note_template.md` | `scripts/petri_audit/repro_pack.py` renders both and records their sha256 in every pack. |
| `docs/repro_pack_readme_template.md`, `docs/repro_pack_disclosure_note_template.md` | `scripts/advice_eval.py` (`PACK_README_TEMPLATE`) and `tests/test_repro_pack.py`. |
| `docs/readability_report.md` | Written by `scripts/readability_report.py` (its default `--out`). |
| `docs/petri_wave2_design.md` | `scripts/export_petri_multiturn.py` parses its sections 10.2 and 10.3 and refuses to export without it; read by `tests/test_export_petri_multiturn.py`, `tests/test_petri_audit_core.py`, `tests/test_petri_framework_data.py` and `tests/test_petri_repro_pack.py`; cited by the landed `data/petri/w2_*.json` records. |
| `docs/petri_wave2_handoff.md` | Quoted in a refusal message of `scripts/petri_three_arm.py`, which `tests/test_petri_three_arm.py` checks. |
| `docs/petri_integration_design.md` | `tests/test_petri_framework_data.py`; cited by `data/petri/README.md` and `data/petri/sanitizer_allowlist.json`. |
| `docs/petri_adaptive_design.md` | `scripts/petri_audit/adaptive.py` writes the path into the adaptive seed file it builds (`docs/framework/petri_seeds_adaptive.draft.json`); named in `scripts/petri_audit/cli.py` help text and the petri-audit workflow's input descriptions. |
| `docs/preregistration_advice.md` | `tests/test_petri_openrouter_prices.py`; cited by `data/advice_providers.json`, `data/petri/publication_deviations.json` and the site's `docs/agent_reference.md`. Also a preregistration. |
| `docs/preregistration_tierB.md` | `scripts/study_timeline.py` runs `git log --follow` on it; the site's `data/provenance.json` cites it. Also a preregistration. |
| `docs/prereg_amendment5_near_twins.md` | `scripts/tierb_near_twins.py` writes the path into its output. Also a preregistration amendment. |
| `docs/prereg_divergence_log.md` | The site's technical page; `data/seal_allowlist.json`. |
| `docs/tier_review_checklist.md` | The site's clinical page; `data/tier_sensitivity_spec.draft.json`. |
| `docs/lens_steering_design.md` | The site's `data/jlens_depth.json`; `data/steer_pilot_spec.json`; landed steering summaries under `trace_out/`. |
| `docs/critic/critic_20260821.md` | The site's `data/jlens_depth.json` and `data/jlens_insights.json`. |
| `docs/backend_agreement_20260903.md` | `docs/agent_reference.md` in both repositories, linked from their AGENTS.md files. |
| `docs/decisions_20260804_pab.md` | `scripts/pab_build_frames.py` and `scripts/pab_harvest_utterances.py` write the path into their outputs; landed records under `data/pab/` cite it. Also a decision record. |
| `docs/pab_crosswalk_spec_20260804.md` | `scripts/pab_tier_crosswalk.py` writes the path into its output. |
| `docs/interp_engine_assessment.md` | Named in a message of `scripts/verify_probs.py`. |
| `docs/triggers.md` | `tests/test_trigger_docs.py` and `tests/test_petri_audit_rejudge_fire.py`. |
| `docs/routine_standing_prompt.md` | `tests/test_routine_standing_prompt.py`; the scheduled Routine reads it at every firing. |
| `docs/overnight_ledger_20260708.md` | `scripts/ledger_update.py` writes spend to the last top-level `docs/*ledger*.md` in name order, which is this file. See the naming rule at the end. |

Code comments and docstrings cite many more design notes (for example
`docs/activation_patching_design.md`, `docs/cross-model.md`,
`docs/model_matrix.md`). Moving one of those breaks no program, but update the
comments in the same change. Before moving any file here, `git grep` both
repositories for its path and its name.

## Study records: never moved or rewritten

| Kind | Files |
|---|---|
| Preregistrations | `docs/preregistration_tierB.md`, `docs/preregistration_advice.md` (signed), `docs/repeatability_sample.md` (pre-declared 2026-07-13) |
| Amendments | `docs/preregistration_amendments.md` (the registry), `docs/prereg_amendment2_depth.md`, `docs/prereg_amendment3_holdout.md`, `docs/prereg_amendment4_steering.md`, `docs/prereg_amendment5_near_twins.md` |
| Divergence log | `docs/prereg_divergence_log.md` |
| Owner decisions | `docs/decisions_20260804_pab.md`, `docs/decisions_20260808_owner.md`, `docs/decisions_20260815_owner.md`, `docs/decisions_20260816_owner.md`, `docs/decisions_20260819_owner.md`, `docs/decisions_20260821_owner.md`, `docs/decisions_20261014_owner.md` |
| Spend ledger | `docs/overnight_ledger_20260708.md` |
| Checklists | `docs/tier_review_checklist.md`, `docs/tierb_freeze_checklist.md` |

## Designs and plans, by arm

| Arm | Files |
|---|---|
| Circuits, lenses and models | `docs/activation_patching_design.md`, `docs/feature_experiments_design.md`, `docs/lens_steering_design.md`, `docs/jlens_evaluation.md`, `docs/equivalence_screen_design.md`, `docs/cross-model.md`, `docs/model_matrix.md`, `docs/interp_engine_assessment.md` |
| Stimulus sets | `docs/supplementary_stress_sets.md`, `docs/emergency_stress_set.md`, `docs/patient_sourced_arm.md`, `docs/expansion_plan_20260722.md` |
| Advice arm | `docs/advice_arm_handoff.md` (the advice preregistration's design source; see Historical), `docs/advice_arm_extensions.md`, `docs/advice_multiturn_design.md`, `docs/advice_vignette_anchor_notes.md`, `docs/advice_manual_vignettes.md` with `docs/advice_manual_vignettes.template.json`, `docs/open_advice_arm_design.md`, `docs/advice_fire_plan_20261002.md` (the costed fire plan for the advice preregistration's proposed Amendment 6) |
| Multi-turn (Petri) | `docs/framework_design.md`, `docs/framework/`, `docs/petri_integration_design.md`, `docs/petri_wave2_design.md`, `docs/petri_wave2_handoff.md`, `docs/petri_adaptive_design.md`, `docs/petri_wave3_design.md` (draft, 2026-10-01) |
| Physician verification | `docs/verification_protocol.md` (draft, 2026-10-03): what physicians rate, the questions, assignment, blinding and the seal, and how ratings are imported and analysed; the questions are data in `data/verification/questions.json`, the bundles are `data/verification/tasks_<stamp>.json` and `scripts/import_verification_ratings.py` writes the imported ratings summaries (`ratings_<bundle_id>_<stamp>.summary.json`) to `data/verification/`; the app itself is in the private repository michaeldgreenphd/patientwords-verify |
| PatientAgentBench | `docs/patientagentbench_integration_design.md`, `docs/pab_integration_layers.md`, `docs/pab_handoff_20260804.md` (its §1 carries its own superseded note), `docs/pab_crosswalk_spec_20260804.md`, `docs/pab_frame_spec_20260805.md`, `docs/pab_first_probe_costing.md` |
| Research protocols and instrument validity | `docs/protocols/protocol_template.md` (reusable research protocol template, 2026-11-10), `docs/protocols/instrument_validity_benchmark.md` (specification of the interpretability-instrument validity benchmark; proposed, nothing measured with it), with schema `schemas/protocols/instrument_validity.v1.schema.json`, draft rubric `data/protocols/instrument_validity_rubric.draft.json` and offline scorer `scripts/instrument_validity.py`; `docs/protocols/instrument_register_experiment_20261111.md` (draft protocol of the first bounded experiment: behaviour, instrument presentation, internal differences and the intervention a causal claim would need, kept as four separate questions; unsigned, nothing run) |
| Reproduction packs | `docs/repro_pack_readme_template.md`, `docs/repro_pack_disclosure_note_template.md`, `docs/petri_repro_pack_readme_template.md`, `docs/petri_repro_pack_disclosure_note_template.md` |

## Findings and analyses

`docs/findings_synthesis.md` (with its 2026-07-13 draft,
`docs/findings_synthesis_DRAFT_20260713.md`), `docs/backend_agreement_20260903.md`,
`docs/negative_control_20260904.md`, `docs/depth_probe_findings_20260902.md`,
`docs/analyses_20260708.json`, `docs/stimulus_qc_v1.json`, and
`docs/readability_report.md` (the site readability worklist, generated).

## Audits and reviews

- `docs/exploratory/methods_integration.md`: audited Causalab/J++ compatibility,
  isolated synthetic adapters, blocked one-case protocol and staged follow-on plan.

- `docs/audits/`: doc-accuracy sweeps, the seal incident, timing forensics,
  evidence power, and `docs/audits/claude_config_audit_20260906.md` (moved from
  `.claude/` on 2026-09-30).
- `docs/audit1_report.md` with `docs/audit1_read_maps.json`,
  `docs/referee_panel_20260714.md`, and `docs/skeptic_read_20260709.md` (see
  Historical).
- `docs/review_packet_clinician.md`, the clinician review packet.
- `docs/review/`: rater and owner review material; its README lists every file.

## Ops records

`docs/briefs/` (cycle briefs), `docs/critic/` (critic reports, 2026-07-10 to
2026-08-28), `docs/coordination/` (cross-session notes) and
`docs/experiments/` (queued or closed experiment notes). Dated records: leave them as written.

## Historical

Kept in place, with a one-line "Superseded by" banner at the top, because
records, tests or other docs cite their paths: `docs/HANDOFF_20260804.md`,
`docs/ops_routine_spec_20260804.md`, `docs/critic_standing_prompt.md`,
`docs/fable_week_plan.md`, `docs/handoff_20260726_disk.md`,
`docs/skeptic_read_20260709.md`.

`docs/advice_arm_handoff.md` has no banner on purpose:
`docs/preregistration_advice.md` names it as its design source, so whether to
mark it superseded is the owner's decision.

Moved: `docs/archive/` holds superseded files that nothing reads, and its README
maps each one's old path to its new one.

## Elsewhere

The traces site build is `.github/workflows/build.yml` in
`michaeldgreenphd/patientwords-traces`; this repository keeps no copy.

## Naming rule for new files

Never give a top-level file in `docs/` a name containing `ledger`:
`scripts/ledger_update.py` takes the last `docs/*ledger*.md` in name order as
the spend ledger, so such a file could split the spend history. Subfolders are
not matched.
