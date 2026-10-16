# Case-report mapping to existing artifacts — proposal, 2026-10-16 UTC

This is a reading contract, not a second result schema or an implemented public
exporter. It leaves experiment IDs, stimuli, endpoints and existing payloads
unchanged. The current exploratory report builder accepts **synthetic evidence
only**; real paired-readout ingestion needs a reviewed follow-up. The separate
baseline preflight may eventually produce implementation-agreement evidence.
Neither path currently contains a real-model result from this integration.

## Artifact identity and joins

The aliases below are documentation shorthand, not new artifact names or IDs:

| Alias | Existing artifact and identity |
|---|---|
| `S` | [`qwen3_4b_one_case.v1.json`](../../data/exploratory/qwen3_4b_one_case.v1.json), schema `patientwords.exploratory/1`; case selected by `cases[].id = pw_exploratory_candidate_r001` |
| `C` | That selected case object in `S`; never identify it only by array order |
| `P` | [`baseline_preflight.v1.json`](../../data/exploratory/baseline_preflight.v1.json), schema `patientwords.baseline-preflight/1`; `source_spec.path` and byte-file `sha256` bind `S` |
| `I` | [`jpp_artifact_inspection.v1.json`](../../data/exploratory/jpp_artifact_inspection.v1.json), schema `lens-artifact-inspection/1`; `artifact_sha256` identifies the inspected checkpoint |
| `E`, `A`, `B` | Future baseline `engine.json`, `causalab.json`, `comparison.json` in the external `exploratory_methods/baseline_preflight/` run directory; **not present as study results** |
| `K`, `R` | An exploratory evidence packet and `exploratory_methods/exploratory_report.<id>.json` from [`exploratory_methods.py`](../../scripts/exploratory_methods.py); presently synthetic only |

`C.join` preserves batch/index/study-model/source-kind/run/item joins. `C.source_refs`
preserves the original bundle, review and pair identities and file hashes; do not
replace pilot provenance with a main-study label. `S.model` and `P.model` name
model/tokenizer revisions; `S.implementations` are historical base commits, not
current executable pins. A future baseline execution record's `commits`, capture
`code`, `execution_sha256`, `versions`, `environment` and `plan_sha256` identify
actual execution. See [baseline_preflight.md](baseline_preflight.md).

Do not mix digest conventions: source file SHA-256 hashes bytes; `R.spec_sha256`
and `R.packet_sha256` hash canonical JSON using the exploratory module's `digest`;
`B.capture_sha256` and the preflight plan/execution digests use the baseline
module's `digest`. Resolve the artifact by the producing implementation's rule.

## Required explanation sections

| Section | Existing fields and required interpretation |
|---|---|
| Comparison | `C.variants.{source,recipient}.prompt`, `prompt_sha256`, `register`, `source_field`, `source_bundle_sha256`; preserve exact bytes and original labels. `C.review.answers`, `checker_verdict`, `scope`, `source_note`, recorded review time and `source_refs` give actual review, not universal clinical certification. `C.split`, `family_id`, `template_family`, `holdout_status` retain scope. |
| Intended unchanged information and origin | Describe only what these exact prompts and review support. This case's shared request/context and brand/generic substitution come from `C.variants` and `C.review.scope`. The [source pilot manifest](../../pilot/runs/pilot_v2_20261002/manifest.json) `model.execution_path` and [protocol](../../pilot/runs/pilot_v2_20261002/PROTOCOL.md) record Claude generation. Do not infer patient authorship from the register label. |
| Observed original behavior | `E/A.variants[variant]` retain full original-output logits and target/token identities. In `R`, select `model_outputs[]` by `case_id` and `variant`; require `probability_kind=original_model_softmax` and `extraction=model.logits[0,-1]`. These are next-token scores, not generated answers. No sequence score, full continuation or independent answer assessment is currently collected here. |
| Internal readout | Select `R.readouts[]` by case/variant/method/layer/position; retain `probability_kind=lens_readout_softmax`. `R.provenance.methods`, `capture_site`, `layer_index_base`, `final_norm`, `common_layers`, `fixed_layers`, `filter_audit` and score matching fields define the readout. Displayed target words resolve through `C.targets[].id/text`; other displayed tokens require the packet vocabulary plus explicit token IDs. A top-k miss means not observed in that window. Never use the last fitted layer as model output. |
| Intervention evidence | Join `R.interventions[].id` to `R.provenance.intervention_plan[].id`. Keep donor/recipient, kind, component, layer, positions, channels, control, seed, nomination split and edit magnitude. Separate observed replacement from zero ablation. Read `effects[]` by target ID/role. `C` currently has no nominated channels or executable intervention rows; planned controls are not completed controls. |
| Controls and collateral | Show which planned controls returned valid rows and which did not. Distinguish self, same-register, seeded random, unrelated, full-component and reverse-direction checks. No real collateral prompt outcomes exist here; this remains untested. Future collateral data need reviewed case/target joins, not a fabricated field or an inference from a successful main patch. |
| Interpretation | Preserve `R.limitations`, planned endpoints and `B.interpretation`; explicitly list untested alternatives and failed checks. A readable word is not proof of a native neuron or clinically correct interpretation. Do not infer unique causation from a single intervention. |

## Quantitative statement requirements

A numerical sentence or figure must carry the source artifact's path/hash and
exact selected field, model/revisions, case/variant, endpoint/matching rule,
units and denominator. Include method/layer/position or intervention ID when
relevant. Keep raw and derived quantities distinguishable. These are field
mappings, **not observations**:

| Source field | Metric, units, scope and denominator |
|---|---|
| `R.model_outputs[case_id,variant].scores[target_id].full_vocab_probability` | Unitless next-token probability from original-model softmax; one target token at the final input position for that case/variant/model. Denominator is the entire output vocabulary. `matching=first_wordpiece_proxy` is not a whole-word or sequence probability. |
| `R.readouts[case_id,variant,method,layer,position].scores[target_id].full_vocab_probability` | Unitless lens-readout softmax score over the entire vocabulary at the stated readout location; not the original model's answer probability. Filtering does not alter this denominator. |
| The same score's `raw_rank` / `filtered_rank` | Integer rank, best rank first, ties by `R.rank_tie_rule`; population is respectively all vocabulary entries / entries retained by `R.filter_audit`. State vocabulary and exclusion counts from `K.vocabulary` and the audit, and the target's exclusion flag. An excluded candidate has no filtered rank. |
| `R.interventions[id].effects[target_id].raw_probability_delta` | Unitless probability difference: patched recipient minus original recipient for that target. State all case/model/intervention identities; not a percentage improvement in answer quality. |
| The same effect's `normalized_recovery` | Dimensionless ratio to the recorded `baseline_gap`; report only with `recovery_status=computable` and the explicit threshold. A nonpositive/near-zero gap is not computable, not zero recovery. Prefer the raw delta. |
| `R.interventions[id].edit_l2` | Euclidean norm in the specified component's activation coordinates, not a cross-model standardized score. Scope includes layer, channels and aligned positions. |
| `B.rows[variant].{legacy_vs_aligned,aligned_vs_causalab}.{max_abs_logit,rms_logit}` | Logit-unit implementation differences across the full output vocabulary. RMS divides squared differences by vocabulary size `P.vocab_size`; maximum has no averaging denominator. It is not a phrasing effect. |
| Those comparison objects' `max_abs_probability` / `target_probability` | Absolute unitless probability differences: respectively maximum over vocabulary / original first target token. Both softmax denominators are full vocabulary. `passed` and `top1_equal` are Boolean checks, not effect sizes. |
| `E/A.runtime_seconds_including_load`, `peak_process_rss_bytes` | Seconds and bytes, for that worker process; not a population result or estimate of fitting capacity. |

If a later summary displays percentages, explicitly document multiplication by
one hundred and label probability percentage points versus relative percent.
Do not invent a whole-answer outcome. `exact_sequence_score=null` with
`sequence_status=not_scored` stays **not scored**. Missing review, coverage or
collateral evidence must be stated before making the corresponding claim.

## Independent statuses and refusal behavior

| Dimension | Current evidence or future rule |
|---|---|
| Execution | `P.status=prepared_not_executed`; `S.planned_experiment.status=blocked_before_model_execution`. `I.status=inspected` is artifact inspection only. `R.execution_status=synthetic` must remain visible everywhere. |
| Compatibility | `I.transport_authorized=false`, `model_fit_compatibility=not_evaluated`; exact historical fit remains unknown. A successful load or baseline pass does not resolve lens-fit identity. |
| Review | `C.review` records an owner review with its scope; it does not imply a completed independent clinician panel, future PR approval or execution authorization. |
| Observed effect | There is no effect observation for this integration's real case. A future measured numeric zero is a valid zero; a failed or unrun stage has no effect estimate. |

Never collapse these into one green/red badge. An artifact can be inspected
successfully while compatibility remains unknown. An authorized experiment can
complete with zero effect. JSON `null`, missing fields, `not_scored`,
`nonpositive_or_near_zero_gap` and named refusals retain distinct explanations;
none defaults to zero. On missing provenance or metric fields, show **unavailable**
with the reason and withhold the numerical claim. A future rendering layer must
reject unsupported real packets, missing method/layer metadata, wrong identities
and incomplete grids rather than label them as findings. The existing semantic
validators, not structural schemas alone, enforce these experimental boundaries.
