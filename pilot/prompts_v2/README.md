# Pilot prompts, version 2

Prompt templates for the next run of the stimulus-generation pilot, revised from the owner's blind review of
run `pilot_real_20260930` (40 pairs, reviewed 2026-10-01). The rules they encode, and the review numbers behind
them, are in `../codebook/codebook_v0.1.md`.

These files do not replace `../prompts/`: that folder belongs to the run recorded in this directory, and its
manifest hashes those exact files. A new run copies these two files into its own `prompts/` folder before
planning; the harness reads `<PILOT_DIR>/prompts/` and needs no other change (same markers, same output format,
same checker schema; `tests/test_pilot_prompts_v2.py` checks that).

## What changed from version 1

Generation prompt:

- Six rules from the codebook: start from a real clinical situation (R4); a one-for-one swap that keeps both
  sentences grammatical without changing any other word (R1); conversational first-person sentences in the
  active voice (R2); clinical terms at a clinician's level of detail and never jargon for its own sake (R3);
  patient phrases in the words patients use rather than leaflet wording (R5); vaguer patient phrases welcome (R6).
- Design change (R7): the 16 pairs per call cover 12 concepts, and 4 of them get a second, vaguer or slangier
  patient phrasing on the next line, with the same clinical term and template. This reuses 4 templates per call,
  so the diversity estimand (mean template similarity) will read somewhat higher than in version 1 for reasons
  of design, not of the generator; the next run's protocol should say so, or measure diversity over distinct
  templates.

Checker prompt (same output schema):

- A vaguer everyday phrase that a patient in the sentence would use for the same thing counts as the same
  concept. This follows the owner's notes (R6) and most of the owner's rulings, but the rulings were split
  (codebook Q2); settle Q2 before freezing the protocol and edit this sentence if the answer is different.
- "Unclear" is for undecidable meaning only, not for a pair that reads badly (codebook Q4).
- Every reason starts with a precision tag, `[as precise]`, `[vaguer]` or `[more specific]`, so the run can
  report agreement separately for vaguer pairs without a schema change.

## What the next run should compare

The owner reviews the next run's 40-pair sample on the same review page. Against version 1:

| Measure | Version 1 (run `pilot_real_20260930`) |
|---|---|
| Kept as is | 18/40, 45% (95% CI 31-60%) |
| Both sentences read naturally | 21/40, 52% (38-67%) |
| Patient phrase sounds real | 19/40, 48% (33-62%) |
| Owner and checker agree on "same thing?" | 23/40, 57% (42-71%); kappa -0.04 |

With 40 reviews, only a large change is distinguishable from noise: the intervals above are about 30 points wide.

## What version 2 still does not do

The checker judges only whether the two phrases name the same thing. The owner's keep decisions followed
sentence quality and patient realism instead (every kept pair had both sentences reading naturally). Judging
those automatically needs a change to the checker's output schema, the parser and the summary, which is a
separate pull request.
