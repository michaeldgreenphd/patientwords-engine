# One-case storyboard — draft, 2026-10-16 UTC

**Preparation only. All PatientWords real-model stages below are not run.**
This is a text walkthrough of the existing reviewed, unsealed specification,
not a case result or a proposed public release.

## Plain-language opening

We want to learn whether a model responds consistently to different ways of
expressing the same concern, and how to test possible reasons for differences.
Before interpreting a model's internal readouts, we must check that the software
implementations agree when running the unchanged model. That check is **not
run**. It checks implementation agreement, not whether an answer is medically
correct. This integration has produced no real-model PatientWords findings.

## The wording comparison

Case `pw_exploratory_candidate_r001` is linked to source bundle item
`vt_216a7dd64eee`, review `r001`, pilot run `pilot_v2_20261002`, and the original
batch/index/model joins. The authoritative exact wording remains in
[`qwen3_4b_one_case.v1.json`](../../data/exploratory/qwen3_4b_one_case.v1.json),
selected by `cases[].id`; no text is rewritten for this explanation.

- **Source wording:** read `variants.source.prompt` verbatim. Its original
  register label is `clinical`; its bytes are checked by `prompt_sha256`.
- **Recipient wording:** read `variants.recipient.prompt` verbatim. Its original
  register label is `patient`; its bytes are checked by `prompt_sha256`.

For a later view, place those two unchanged strings here, with their source
labels and links. This document references the JSON instead of making another
copy of the study wording. The shared context and refill request are intended
to stay unchanged; the reviewed substitution uses a generic name and a brand
name. This narrow contrast does not stand for everyday-versus-technical wording
in general. No approved normalized version exists (`normalized_variant.status`
is `unavailable`), so none is added.

The source is Claude-generated pilot material, not an attributed patient
quotation. The source [manifest](../../pilot/runs/pilot_v2_20261002/manifest.json)
`model.execution_path` and [protocol](../../pilot/runs/pilot_v2_20261002/PROTOCOL.md)
record the generation route. The case's `review` records the owner's keep and
same-meaning judgments, also recording `precision=vaguer` and a brand/generic
scope limitation. This is intended equivalence within that review scope, not
certified equivalence by a new clinician panel. Nothing here infers literacy
or demographic group from the wording.

## Why this case stays in the report

It is the first kept, owner-reviewed, unsealed pilot item in the existing
[selection record](methods_integration.md#one-case-protocol-and-exact-commands),
chosen without selecting on model outcome. Its split is `discovery`, not fresh
confirmation. Retain it if the next check fails or later effects are absent,
negative or difficult to interpret. A later illustration from a cohort must be
linked to the full inventory and selection rule, not presented as representative
merely because it is memorable.

## Implementation agreement — not run

Planned model and tokenizer identities are `model.id`, `model.revision`,
`model.tokenizer_id` and `model.tokenizer_revision` in the
[baseline plan](../../data/exploratory/baseline_preflight.v1.json). It reuses this
case and its prompt hashes. The unchanged engine output, the engine output with
explicit aligned forward arguments, and Causalab's original-model output will
be compared at the same output position with the same token IDs and numerical
settings. Prospective thresholds and failure criteria are in the
[baseline preflight](baseline_preflight.md).

**Observation: not run.** There are no real-case baseline capture or comparison
artifacts from this integration. Matching only the leading token would be
insufficient; full output differences must meet the declared gates. Failure
would be reported as failed agreement, not evidence that wording changes
clinical understanding. Agreement would support only the bounded software
comparison, not clinical accuracy or lens compatibility.

## Original-model behavior — not run

The legacy endpoint is the probability of the first encoded target token at
the end of the prompt. The answer target remains
`targets[id=legacy_next_token_target]`; the intermediate lexical annotation is
`targets[id=source_lexical_concept]`. These are different roles. Tokenization is
pending in this specification, so this storyboard supplies no target-token
score or displayed model output.

**Observation: not run.** No generated complete answer, continuation score or
independent assessment of answer quality was collected by this integration.
Those cannot be inferred from a future next-token score. Any eventual number
must follow the [artifact/field, units and scope mapping](case_report_mapping.md).

## Internal readouts — not run; fit compatibility unresolved

Logit Lens, J-Lens and J++ are intended as separate readouts of internal states,
with explicit locations and raw versus filtered ranks. They would not show
"what the AI was thinking." An intermediate word is not the requested answer
or an identified native neuron.

**Observation: not run.** The J++ file was safely inspected, but its historical
model/tokenizer fit revisions remain unknown; see
[`jpp_artifact_inspection.v1.json`](../../data/exploratory/jpp_artifact_inspection.v1.json)
`transport_authorized` and `model_fit_compatibility`, and the
[provenance handoff](local_preparation_20261015.md). Inspection success does not
make transport compatible. No fitted-layer score substitutes for actual output.

## Controlled changes — not run

A later controlled test could replace an observed activation in one wording
with its counterpart from the other wording at declared aligned positions,
then compare the same endpoint. Reverse direction, separate ablation and
controls would help test specificity. A layer readout cannot by itself nominate
individual channels. Candidate selection would use discovery evidence only.

**Interventions, controls and collateral effects: not run.** The current
`intervention_plan` is empty; no component has been nominated. Self/no-op,
matched seeded random groups, same-register and unrelated controls, and
full-component references remain plans, not completed comparisons. Existing
synthetic software fixtures are not evidence for this real case. No rescue,
general repair or clinical safety improvement is claimed.

## What could change the explanation

There is no measured effect to explain yet. Future discrepancies could reflect
measurement or implementation differences, different concept readouts,
transport failure, or response selection; these remain competing hypotheses.
A failed baseline check would weaken a comparison across implementations.
Missing fit records would continue to limit lens claims. An intervention effect
also appearing in matched random or unrelated controls would weaken a specific
mechanistic explanation. A zero or negative result remains informative and is
not replaced with a more favorable case.

The next bounded step would be the baseline comparison, after separate execution
authorization and after its review and runner prerequisites are met. Neither software tests nor this
storyboard answer the public research question. The intended benefit is models
that handle ordinary communication better, not an obligation for patients to
change how they speak.
