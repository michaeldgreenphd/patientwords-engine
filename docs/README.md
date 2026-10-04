# docs/ — index

What is in this folder and which files must stay where they are. Paths are
relative to the repository root. Written 2026-09-30; add a line here when you
add a document.

## Start here

| File | What it is |
|---|---|
| `AGENTS.md` (repository root) | The rules every agent and reviewer works from. |
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
| `docs/preregistration_advice.md` | `tests/test_petri_openrouter_prices.py`; cited by `data/advice_providers.json`, `data/petri/publication_deviations.json` and the site's `AGENTS.md`. Also a preregistration. |
| `docs/preregistration_tierB.md` | `scripts/study_timeline.py` runs `git log --follow` on it; the site's `data/provenance.json` cites it. Also a preregistration. |
| `docs/prereg_amendment5_near_twins.md` | `scripts/tierb_near_twins.py` writes the path into its output. Also a preregistration amendment. |
| `docs/prereg_divergence_log.md` | The site's technical page; `data/seal_allowlist.json`. |
| `docs/tier_review_checklist.md` | The site's clinical page; `data/tier_sensitivity_spec.draft.json`. |
| `docs/lens_steering_design.md` | The site's `data/jlens_depth.json`; `data/steer_pilot_spec.json`; landed steering summaries under `trace_out/`. |
| `docs/critic/critic_20260821.md` | The site's `data/jlens_depth.json` and `data/jlens_insights.json`. |
| `docs/backend_agreement_20260903.md` | `AGENTS.md` in both repositories. |
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
| Owner decisions | `docs/decisions_20260804_pab.md`, `docs/decisions_20260808_owner.md`, `docs/decisions_20260815_owner.md`, `docs/decisions_20260816_owner.md`, `docs/decisions_20260819_owner.md`, `docs/decisions_20260821_owner.md` |
| Spend ledger | `docs/overnight_ledger_20260708.md` |
| Checklists | `docs/tier_review_checklist.md`, `docs/tierb_freeze_checklist.md` |

## Designs and plans, by arm

| Arm | Files |
|---|---|
| Circuits, lenses and models | `docs/activation_patching_design.md`, `docs/feature_experiments_design.md`, `docs/lens_steering_design.md`, `docs/jlens_evaluation.md`, `docs/equivalence_screen_design.md`, `docs/cross-model.md`, `docs/model_matrix.md`, `docs/interp_engine_assessment.md` |
| Stimulus sets | `docs/supplementary_stress_sets.md`, `docs/emergency_stress_set.md`, `docs/patient_sourced_arm.md`, `docs/expansion_plan_20260722.md` |
| Advice arm | `docs/advice_arm_handoff.md` (the advice preregistration's design source; see Historical), `docs/advice_arm_extensions.md`, `docs/advice_multiturn_design.md`, `docs/advice_vignette_anchor_notes.md`, `docs/advice_manual_vignettes.md` with `docs/advice_manual_vignettes.template.json`, `docs/open_advice_arm_design.md`, `docs/advice_fire_plan_20261002.md` (the costed fire plan for the advice preregistration's proposed Amendment 6) |
| Multi-turn (Petri) | `docs/framework_design.md`, `docs/framework/`, `docs/petri_integration_design.md`, `docs/petri_wave2_design.md`, `docs/petri_wave2_handoff.md`, `docs/petri_adaptive_design.md`, `docs/petri_wave3_design.md` (draft, 2026-10-01) |
| Physician verification | `docs/verification_protocol.md` (draft, 2026-10-03): what physicians rate, the questions, assignment, blinding and the seal; the questions are data in `data/verification/questions.json` and the bundles are `data/verification/tasks_<stamp>.json`; the app itself is in the private repository michaeldgreenphd/patientwords-verify |
| PatientAgentBench | `docs/patientagentbench_integration_design.md`, `docs/pab_integration_layers.md`, `docs/pab_handoff_20260804.md` (its §1 carries its own superseded note), `docs/pab_crosswalk_spec_20260804.md`, `docs/pab_frame_spec_20260805.md`, `docs/pab_first_probe_costing.md` |
| Reproduction packs | `docs/repro_pack_readme_template.md`, `docs/repro_pack_disclosure_note_template.md`, `docs/petri_repro_pack_readme_template.md`, `docs/petri_repro_pack_disclosure_note_template.md` |

## Findings and analyses

`docs/findings_synthesis.md` (with its 2026-07-13 draft,
`docs/findings_synthesis_DRAFT_20260713.md`), `docs/backend_agreement_20260903.md`,
`docs/negative_control_20260904.md`, `docs/depth_probe_findings_20260902.md`,
`docs/analyses_20260708.json`, `docs/stimulus_qc_v1.json`, and
`docs/readability_report.md` (the site readability worklist, generated).

## Audits and reviews

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
