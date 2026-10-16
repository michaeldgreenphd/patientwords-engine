# Exploratory communication plan — draft, 2026-10-16 UTC

This is an explanation plan for review, not a public report or a new study
endpoint. **No real-model PatientWords findings have yet been produced by this
integration.** The local installation and synthetic checks establish software
behavior only. See the [technical handoff](local_preparation_20261015.md).

## Purpose and audience

Draft purpose statement:

> Does an AI respond consistently when the same health concern is expressed
> in everyday language rather than medical terminology? When it does not,
> can we identify and test what contributed to the difference?

The aim is to improve models' handling of ordinary communication. Patients do
not owe a model medical jargon to deserve a reliable answer. A dataset label
such as `patient` describes a wording condition; it does not establish literacy,
demographics, authorship by a patient, or clinical equivalence. Preserve the
stimulus's recorded origin, intended equivalence and actual review scope.

Patients and other nontechnical readers need the question, observation and
limits; clinicians also need the wording, information intended to remain
constant, and review status; researchers need exact endpoints and reproducible
provenance. These are layers of the same evidence, not different conclusions.

## Minimal future layout

1. **Short summary:** question, observed endpoint and limitation, with an
   explicit status if no observation exists. Every number links to its artifact
   and field using the [case-report mapping](case_report_mapping.md).
2. **Annotated walkthrough:** comparison wording; original-model behavior;
   internal readouts; interventions and controls; interpretation and alternatives.
   Keep these visibly separate. The [text storyboard](one_case_storyboard.md)
   demonstrates the layout with every unrun stage marked **not run**.
3. **Linked technical detail:** source/review joins, model and tokenizer pins,
   code/artifact hashes, execution environment, filter and matching definitions,
   planned and completed controls, failures, coverage and exclusions.

No dashboard, formatter, public export, generated figure, recruitment, or new
schema is needed now. These documents map the existing contracts. A later
renderer must pass the acceptance checklist below before it is used; this
proposal does not claim that a renderer exists. Neither display work nor a
comprehension review is a prerequisite for the bounded baseline check.

Use "the readout ranked the target highly" or "the intervention changed this
case's measured target-token probability." Never turn a lens word into "what
the AI was thinking," a token probability into the probability of a medically
correct answer, or a score change into a better complete response. A patch is
not a general fix. Explain researcher labels such as `capture_site`, `rescue`
and `clinical_mass` rather than treating them as public conclusions. The next
baseline step checks agreement between implementations, not clinical accuracy.

## Selection and missingness

Freeze the existing choice before new outcomes: the first kept, owner-reviewed,
unsealed pilot item in the selection record, with no selection on model outcome.
Its brand/generic contrast is narrower than the broad public question. Keep it
if implementations disagree, effects are zero or negative, compatibility stays
unknown, or a check fails. Replacing it because another case looks clearer or
more dramatic would introduce showcase selection bias. Preserve the study and
holdout boundaries; do not create a clearer stimulus for the storyboard.

A future cohort report must retain the full prespecified inventory, family and
template splits, attempted/completed/failed/excluded counts, reasons and missing
rates, with each denominator explicit. Link any illustrated case to that inventory
and explain its selection; do not call it representative without evidence.
Use family-level uncertainty rather than treating tokens or layers as independent
samples. Do not remove failures via an upstream correctness filter.

## Later figure specification

Use a descriptive title naming the endpoint and scope. Label axes with units,
model, case, variant and position/layer where applicable; include denominators
and uncertainty definitions. Give raw and filtered ranks separate labels and
show filter exclusions. Use direct labels or readable legends and a text
alternative plus an accessible data table with the same source references.
Distinguish methods and statuses with text/line styles or symbols as well as
color. Preserve legibility at small sizes and avoid decorative ink. An unrun or
blocked stage gets text, never a zero-height bar. No safety gauge or composite
"understanding" score is permitted.

## Acceptance and later comprehension review

Before any future summary generation, verify with synthetic fixtures and real
artifact contracts that:

- Missing, refused, blocked and unrun stages cannot render as measured findings;
  an observed zero remains a measured zero and an absent value remains absent.
- Synthetic output is labeled **synthetic software fixture — not a research
  result** in every view, including copied summaries and accessible tables.
- Metric kind, matching rule, scope, denominator and limitations survive summary
  generation. Each numerical statement resolves to its cited source field and
  hash; any transformation is stated. Do not supply absent sequence scores.
- Execution, compatibility, review status and effect remain independent. A
  completed inspection does not establish model-fit compatibility.
- Agreement, disagreement, failed checks, null effects and unknown compatibility
  are equally representable; selected layers or cases cannot silently disappear.

Plan a later review with a nontechnical reader and a clinician; do not recruit
or conduct it now. Ask each reader to explain, in their own words:

- Which text is actual model output and which is a lens readout?
- Is a technical score change also a clinically evaluated improvement here?
- Which evidence is observational, and which comes from a controlled intervention?
- Is this a single-case observation or a general finding?
- What does the study show, and what remains unknown?
- **Does this explanation wrongly suggest that patients should change how they
  speak to deserve a reliable answer?**

Record misunderstandings and revise explanations around them. Judge success by
understanding the evidence and its limits, not by whether the explanation seems
impressive or trustworthy. The future frontend and audience work require their
own review and authorization.
