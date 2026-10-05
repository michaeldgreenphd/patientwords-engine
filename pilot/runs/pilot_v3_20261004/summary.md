# Pilot summary (computed by scripts/compute_summary.py)

Seeds: 26 (provenance as the seed file states it: hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 10; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 11; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 12; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 13; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 14; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 15; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 16; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 18; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 20; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 21; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 22; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 23; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 24; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 25; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 26; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 27; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 28; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 29; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 2; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 3; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 4; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 5; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 6; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 7; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 8; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered; hand-built dataset from real patient language: engine data/measured/imported_pairs.json, source_row 9; converted mechanically to term + template form (shared prefix and suffix become the template), text unaltered). Exemplars per call: 8 used, 8 requested. Proportions carry 95% Wilson intervals; means carry 95% percentile bootstrap intervals (2000 resamples, stream random.Random('20260929:bootstrap')); differences of proportions carry Newcombe score intervals. Master seed 20260929; every named stream is listed under seeds in summary.json. Values are shown to 3 decimals.

Harness version 2: rows carry next_word, the checker also answers relation, sentence_natural and patient_realism, and the sections marked version 2 report descriptives outside the protocol's estimands.

Intervals under the variant design (version 2): the intervals of estimands 1 to 5 are computed over rows, as the protocol fixes them (Wilson and Newcombe intervals count rows; the estimand 3 bootstrap resamples rows within cells). The rows are not independent draws: the rows of one call come from a single generation, and by design 8 of every 16 non-control rows of a call belong to 4 two-row concepts, whose two rows share the clinical term and the template. Read these intervals as descriptive. This run's non-control rows cover 216 concepts in 288 rows (Arm A 108 in 144, Arm B 108 in 144).

## Run overview

| Quantity | Value |
|---|---|
| Generation calls | 18 |
| Attempts (including retries) | 18 |
| Calls retried | 0 |
| Calls with at least one valid row | 18 / 18 (Wilson [0.824, 1.000]) |
| Calls with no response record | 0 |

| Call | Attempt | Lines | Valid | Invalid | Controls | Non-control | Failure reasons |
|---|---|---|---|---|---|---|---|
| A__cardiology__symptom_description | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__cardiology__symptom_description | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__cardiology__body_part | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__cardiology__body_part | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__cardiology__medication | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__cardiology__medication | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__neurology__symptom_description | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__neurology__symptom_description | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__neurology__body_part | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__neurology__body_part | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__neurology__medication | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__neurology__medication | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__gastroenterology__symptom_description | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__gastroenterology__symptom_description | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__gastroenterology__body_part | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__gastroenterology__body_part | 1 | 20 | 20 | 0 | 4 | 16 | none |
| A__gastroenterology__medication | 1 | 20 | 20 | 0 | 4 | 16 | none |
| B__gastroenterology__medication | 1 | 20 | 20 | 0 | 4 | 16 | none |

## Estimand 1: format validity (final attempts)

| Scope | Valid / lines | Proportion | 95% Wilson |
|---|---|---|---|
| All calls | 360 / 360 | 1.000 | [0.989, 1.000] |
| Arm A | 180 / 180 | 1.000 | [0.979, 1.000] |
| Arm B | 180 / 180 | 1.000 | [0.979, 1.000] |
| Cell cardiology__symptom_description | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell cardiology__body_part | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell cardiology__medication | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell neurology__symptom_description | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell neurology__body_part | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell neurology__medication | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell gastroenterology__symptom_description | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell gastroenterology__body_part | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell gastroenterology__medication | 40 / 40 | 1.000 | [0.912, 1.000] |
| All attempts pooled (secondary) | 360 / 360 | 1.000 | [0.989, 1.000] |

Failure reasons (final attempts): none

## Negative controls (secondary)

Control rows returned and valid: 72 (expected 72).
Controls with no lexical content in a term (no letter or digit after normalization; excluded from the fidelity denominator and counted): 0.

| Scope | Faithful (surface form only) / controls | Proportion | 95% Wilson |
|---|---|---|---|
| Both arms | 72 / 72 | 1.000 | [0.949, 1.000] |
| Arm A | 36 / 36 | 1.000 | [0.904, 1.000] |
| Arm B | 36 / 36 | 1.000 | [0.904, 1.000] |

## Probe point (version 2, descriptive; not a format failure)

A template meets the probe point when, stripped, its last word is one of a, an, the, my, his, her, their, your, our (case-insensitive). Population: format-valid rows of the final attempts, controls included.

| Scope | Ending on a probe word / rows | Proportion | 95% Wilson |
|---|---|---|---|
| All rows | 360 / 360 | 1.000 | [0.989, 1.000] |
| Control none | 288 / 288 | 1.000 | [0.987, 1.000] |
| Control negative | 72 / 72 | 1.000 | [0.949, 1.000] |
| Arm A | 180 / 180 | 1.000 | [0.979, 1.000] |
| Arm B | 180 / 180 | 1.000 | [0.979, 1.000] |
| Cell cardiology__symptom_description | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell cardiology__body_part | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell cardiology__medication | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell neurology__symptom_description | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell neurology__body_part | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell neurology__medication | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell gastroenterology__symptom_description | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell gastroenterology__body_part | 40 / 40 | 1.000 | [0.912, 1.000] |
| Cell gastroenterology__medication | 40 / 40 | 1.000 | [0.912, 1.000] |

## Variant design (version 2, descriptive)

Definition: per call, over the final attempt's format-valid control none rows ordered by line_index: compliant when the rows number exactly 16 and cover exactly 12 concepts (clinical_term surface key and template), exactly 4 adjacent pairs share clinical_term, template and next_word with different patient_term surface keys, no concept's rows are separated by another concept's row, and no concept runs over three or more rows.

| Scope | Compliant calls / calls | Proportion | 95% Wilson |
|---|---|---|---|
| All calls | 18 / 18 | 1.000 | [0.824, 1.000] |
| Arm A | 9 / 9 | 1.000 | [0.701, 1.000] |
| Arm B | 9 / 9 | 1.000 | [0.701, 1.000] |

Adjacent variant pairs: 72 with the clinical term exact, 72 with it equal in surface form (expected 4 per call). Same-concept rows that are not adjacent: 0. Runs of three or more rows of one concept: 0. Flagged calls: none.

| Call | Rows (control none) | Concepts | Pairs (exact) | Pairs (surface) | Non-adjacent repeats | Runs of 3+ | Compliant |
|---|---|---|---|---|---|---|---|
| A__cardiology__symptom_description | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__cardiology__symptom_description | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__cardiology__body_part | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__cardiology__body_part | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__cardiology__medication | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__cardiology__medication | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__neurology__symptom_description | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__neurology__symptom_description | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__neurology__body_part | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__neurology__body_part | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__neurology__medication | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__neurology__medication | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__gastroenterology__symptom_description | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__gastroenterology__symptom_description | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__gastroenterology__body_part | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__gastroenterology__body_part | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| A__gastroenterology__medication | 16 | 12 | 4 | 4 | 0 | 0 | yes |
| B__gastroenterology__medication | 16 | 12 | 4 | 4 | 0 | 0 | yes |

## next_word (version 2)

Population: format-valid rows of the final attempts, controls included: 360 rows, 44 distinct words.

| next_word | Rows |
|---|---|
| doctor | 168 |
| hospital | 51 |
| pharmacy | 20 |
| bathroom | 12 |
| pharmacist | 9 |
| specialist | 9 |
| ambulance | 6 |
| cardiologist | 6 |
| emergency | 6 |
| antacid | 5 |

## Estimand 2: novelty (non-control rows)

| Scope | Key | Novel / rows | Proportion | 95% Wilson |
|---|---|---|---|---|
| Arm A | (clinical_term, patient_term) pair | 141 / 144 | 0.979 | [0.941, 0.993] |
| Arm A | clinical_term | 106 / 144 | 0.736 | [0.659, 0.801] |
| Arm A | patient_term | 138 / 144 | 0.958 | [0.912, 0.981] |
| Arm B | (clinical_term, patient_term) pair | 144 / 144 | 1.000 | [0.974, 1.000] |
| Arm B | clinical_term | 107 / 144 | 0.743 | [0.666, 0.807] |
| Arm B | patient_term | 142 / 144 | 0.986 | [0.951, 0.996] |
| Pooled (secondary) | (clinical_term, patient_term) pair | 237 / 288 | 0.823 | [0.775, 0.863] |

Rows that exactly duplicate a seed pair (case-insensitive): 0.

## Estimand 3: diversity (mean pairwise TF-IDF cosine of templates; lower means more diverse)

TF-IDF fitted on 314 templates (all non-control generated rows plus the seeds).
Templates with no TF-IDF token (no measurable similarity; excluded from every cosine and counted): 0 generated (Arm A 0, Arm B 0), 0 seed.

| Arm | Cell | Rows | Pairs | Mean cosine |
|---|---|---|---|---|
| A | cardiology__symptom_description | 16 | 120 | 0.103 |
| A | cardiology__body_part | 16 | 120 | 0.134 |
| A | cardiology__medication | 16 | 120 | 0.105 |
| A | neurology__symptom_description | 16 | 120 | 0.133 |
| A | neurology__body_part | 16 | 120 | 0.150 |
| A | neurology__medication | 16 | 120 | 0.111 |
| A | gastroenterology__symptom_description | 16 | 120 | 0.160 |
| A | gastroenterology__body_part | 16 | 120 | 0.100 |
| A | gastroenterology__medication | 16 | 120 | 0.084 |
| B | cardiology__symptom_description | 16 | 120 | 0.132 |
| B | cardiology__body_part | 16 | 120 | 0.145 |
| B | cardiology__medication | 16 | 120 | 0.102 |
| B | neurology__symptom_description | 16 | 120 | 0.151 |
| B | neurology__body_part | 16 | 120 | 0.110 |
| B | neurology__medication | 16 | 120 | 0.125 |
| B | gastroenterology__symptom_description | 16 | 120 | 0.126 |
| B | gastroenterology__body_part | 16 | 120 | 0.082 |
| B | gastroenterology__medication | 16 | 120 | 0.108 |

| Arm | Mean of cell means | 95% bootstrap | Rows | Cells with pairs | Replicates used | Undefined replicates |
|---|---|---|---|---|---|---|
| A | 0.120 | [0.104, 0.137] | 144 | 9 | 2000 | 0 |
| B | 0.120 | [0.104, 0.138] | 144 | 9 | 2000 | 0 |

The cell set is fixed across replicates (cells with at least two rows). A replicate in which a cell resamples to copies of one row has no within-cell statistic; it is skipped and counted, never computed over fewer cells.

| Arm | Generated vs seed templates, mean cosine | 95% bootstrap | Pairs |
|---|---|---|---|
| A | 0.035 | [0.032, 0.037] | 3744 |
| B | 0.035 | [0.033, 0.037] | 3744 |

## Estimand 4: semantic equivalence (checker), reported with the checker's own validation

Checker set: 318 items = 288 generated + 10 known-good seed rows + 20 broken pairs. Notes: none.

| Checker validation | Hits / answered | Proportion | 95% Wilson | Verdict counts |
|---|---|---|---|---|
| Sensitivity on known-good (unclear counts as miss) | 5 / 10 | 0.500 | [0.237, 0.763] | {'no': 5, 'yes': 5} |
| Sensitivity on known-good (unclear excluded) | 5 / 10 | 0.500 | [0.237, 0.763] | {'no': 5, 'yes': 5} |
| Specificity on broken (unclear counts as miss) | 20 / 20 | 1.000 | [0.839, 1.000] | {'no': 20} |
| Specificity on broken (unclear excluded) | 20 / 20 | 1.000 | [0.839, 1.000] | {'no': 20} |

| Scope | Judged equivalent / answered | Proportion | 95% Wilson | Unclear / answered | Missing | Counts |
|---|---|---|---|---|---|---|
| All generated | 273 / 288 | 0.948 | [0.916, 0.968] | 0 / 288 | 0 | {'yes': 273, 'no': 15} |
| Arm A | 136 / 144 | 0.944 | [0.894, 0.972] | 0 / 144 | 0 | {'yes': 136, 'no': 8} |
| Arm B | 137 / 144 | 0.951 | [0.903, 0.976] | 0 / 144 | 0 | {'yes': 137, 'no': 7} |
| Cell cardiology__symptom_description | 29 / 32 | 0.906 | [0.758, 0.968] | 0 / 32 | 0 | {'yes': 29, 'no': 3} |
| Cell cardiology__body_part | 28 / 32 | 0.875 | [0.719, 0.950] | 0 / 32 | 0 | {'yes': 28, 'no': 4} |
| Cell cardiology__medication | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell neurology__symptom_description | 30 / 32 | 0.938 | [0.799, 0.983] | 0 / 32 | 0 | {'yes': 30, 'no': 2} |
| Cell neurology__body_part | 28 / 32 | 0.875 | [0.719, 0.950] | 0 / 32 | 0 | {'no': 4, 'yes': 28} |
| Cell neurology__medication | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell gastroenterology__symptom_description | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell gastroenterology__body_part | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell gastroenterology__medication | 30 / 32 | 0.938 | [0.799, 0.983] | 0 / 32 | 0 | {'yes': 30, 'no': 2} |

## Checker relation, precision, sentence and realism (version 2, descriptive)

Population: answered items (verdict not missing); relation, precision and the yes-rate by relation count only answers with a yes or no verdict; answered generated 288, known-good 10, broken 20; with a yes or no verdict generated 288, known-good 10, broken 20.

| Items | Relation counts (yes or no verdicts) | Precision (derived from relation) |
|---|---|---|
| generated | same 140, same_brand 6, broader 127, narrower 3, different 12 | as_precise 146, vaguer 127, more_specific 3, not_applicable 12 |
| known-good | same 3, same_brand 0, broader 2, narrower 1, different 4 | as_precise 3, vaguer 2, more_specific 1, not_applicable 4 |
| broken | same 0, same_brand 0, broader 0, narrower 0, different 20 | as_precise 0, vaguer 0, more_specific 0, not_applicable 20 |

The version-2 schema requires a relation with every answer, so an answer whose verdict is unclear (the checker could not decide what a phrase means) still carries one. Such a relation describes no decided meaning: it is left out of the relation, precision and yes-rate counts and listed here. Unclear verdicts: 0 (generated 0, known-good 0, broken 0).

| Items | Relations given with an unclear verdict (not counted above) |
|---|---|
| generated | same 0, same_brand 0, broader 0, narrower 0, different 0 |
| known-good | same 0, same_brand 0, broader 0, narrower 0, different 0 |
| broken | same 0, same_brand 0, broader 0, narrower 0, different 0 |

| Relation (generated) | Judged equivalent / judged yes or no | Proportion | 95% Wilson |
|---|---|---|---|
| same | 140 / 140 | 1.000 | [0.973, 1.000] |
| same_brand | 6 / 6 | 1.000 | [0.610, 1.000] |
| broader | 127 / 127 | 1.000 | [0.971, 1.000] |
| narrower | 0 / 3 | 0.000 | [0.000, 0.561] |
| different | 0 / 12 | 0.000 | [0.000, 0.242] |

Answers whose equivalent contradicts their relation (kept as given, flagged inconsistent): 0 (generated 0, known-good 0, broken 0).

| Scope (generated) | sentence_natural | patient_realism |
|---|---|---|
| All | both 286, clinical_only 1, patient_only 1, neither 0 | real 280, textbook 7, unlikely 1 |
| Arm A | both 143, clinical_only 1, patient_only 0, neither 0 | real 140, textbook 3, unlikely 1 |
| Arm B | both 143, clinical_only 0, patient_only 1, neither 0 | real 140, textbook 4, unlikely 0 |

## Estimand 5: exemplar sensitivity, Arm A (random exemplars) minus Arm B (fixed exemplars)

| Estimand | Arm A | Arm B | A minus B | 95% interval for the difference |
|---|---|---|---|---|
| 2 novelty (pair) | 0.979 | 1.000 | -0.021 | [-0.059, 0.009] (Newcombe) |
| 3 within-cell diversity (mean cosine) | 0.120 | 0.120 | -0.000 | [-0.024, 0.024] (bootstrap, 2000 replicates, 0 undefined) |
| 3 generated vs seeds (mean cosine) | 0.035 | 0.035 | -0.000 | [-0.004, 0.003] (bootstrap) |
| 4 equivalence (yes / answered) | 0.944 | 0.951 | -0.007 | [-0.063, 0.048] (Newcombe) |

## Human review sample

review_sheet.csv holds 40 rows; allocation by arm {'A': 20, 'B': 20} from checked rows by arm {'A': 144, 'B': 144}. Agreement is not computed here.

Version 2 sampling: one_row_per_concept (a concept is the call, the clinical term's surface key and the template); concepts by arm {'A': 108, 'B': 108}; 40 distinct concepts among the 40 rows. review_key.csv also carries the checker's relation, sentence_natural and patient_realism.
