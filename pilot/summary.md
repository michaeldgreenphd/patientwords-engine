# Pilot summary (computed by scripts/compute_summary.py)

Seeds: 6 (provenance as the seed file states it: synthetic placeholder, not study data). Exemplars per call: 6 used, 8 requested. Proportions carry 95% Wilson intervals; means carry 95% percentile bootstrap intervals (2000 resamples, stream random.Random('20260929:bootstrap')); differences of proportions carry Newcombe score intervals. Master seed 20260929; every named stream is listed under seeds in summary.json. Values are shown to 3 decimals.

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

| Scope | Faithful (surface form only) / controls | Proportion | 95% Wilson |
|---|---|---|---|
| Both arms | 72 / 72 | 1.000 | [0.949, 1.000] |
| Arm A | 36 / 36 | 1.000 | [0.904, 1.000] |
| Arm B | 36 / 36 | 1.000 | [0.904, 1.000] |

## Estimand 2: novelty (non-control rows)

| Scope | Key | Novel / rows | Proportion | 95% Wilson |
|---|---|---|---|---|
| Arm A | (clinical_term, patient_term) pair | 143 / 144 | 0.993 | [0.962, 0.999] |
| Arm A | clinical_term | 143 / 144 | 0.993 | [0.962, 0.999] |
| Arm A | patient_term | 143 / 144 | 0.993 | [0.962, 0.999] |
| Arm B | (clinical_term, patient_term) pair | 144 / 144 | 1.000 | [0.974, 1.000] |
| Arm B | clinical_term | 142 / 144 | 0.986 | [0.951, 0.996] |
| Arm B | patient_term | 143 / 144 | 0.993 | [0.962, 0.999] |
| Pooled (secondary) | (clinical_term, patient_term) pair | 251 / 288 | 0.872 | [0.828, 0.905] |

Rows that exactly duplicate a seed pair (case-insensitive): 0.

## Estimand 3: diversity (mean pairwise TF-IDF cosine of templates; lower means more diverse)

TF-IDF fitted on 294 templates (all non-control generated rows plus the seeds).

| Arm | Cell | Rows | Pairs | Mean cosine |
|---|---|---|---|---|
| A | cardiology__symptom_description | 16 | 120 | 0.047 |
| A | cardiology__body_part | 16 | 120 | 0.088 |
| A | cardiology__medication | 16 | 120 | 0.054 |
| A | neurology__symptom_description | 16 | 120 | 0.072 |
| A | neurology__body_part | 16 | 120 | 0.080 |
| A | neurology__medication | 16 | 120 | 0.039 |
| A | gastroenterology__symptom_description | 16 | 120 | 0.108 |
| A | gastroenterology__body_part | 16 | 120 | 0.064 |
| A | gastroenterology__medication | 16 | 120 | 0.083 |
| B | cardiology__symptom_description | 16 | 120 | 0.069 |
| B | cardiology__body_part | 16 | 120 | 0.072 |
| B | cardiology__medication | 16 | 120 | 0.088 |
| B | neurology__symptom_description | 16 | 120 | 0.069 |
| B | neurology__body_part | 16 | 120 | 0.072 |
| B | neurology__medication | 16 | 120 | 0.072 |
| B | gastroenterology__symptom_description | 16 | 120 | 0.081 |
| B | gastroenterology__body_part | 16 | 120 | 0.081 |
| B | gastroenterology__medication | 16 | 120 | 0.072 |

| Arm | Mean of cell means | 95% bootstrap | Rows | Cells with pairs | Replicates used | Undefined replicates |
|---|---|---|---|---|---|---|
| A | 0.070 | [0.061, 0.081] | 144 | 9 | 2000 | 0 |
| B | 0.075 | [0.065, 0.087] | 144 | 9 | 2000 | 0 |

The cell set is fixed across replicates (cells with at least two rows). A replicate in which a cell resamples to copies of one row has no within-cell statistic; it is skipped and counted, never computed over fewer cells.

| Arm | Generated vs seed templates, mean cosine | 95% bootstrap | Pairs |
|---|---|---|---|
| A | 0.060 | [0.055, 0.065] | 864 |
| B | 0.065 | [0.060, 0.072] | 864 |

## Estimand 4: semantic equivalence (checker), reported with the checker's own validation

Checker set: 314 items = 288 generated + 6 known-good seed rows + 20 broken pairs. Notes: known-good rows: 6 seeds available, 10 requested.

| Checker validation | Hits / answered | Proportion | 95% Wilson | Verdict counts |
|---|---|---|---|---|
| Sensitivity on known-good (unclear counts as miss) | 6 / 6 | 1.000 | [0.610, 1.000] | {'yes': 6} |
| Sensitivity on known-good (unclear excluded) | 6 / 6 | 1.000 | [0.610, 1.000] | {'yes': 6} |
| Specificity on broken (unclear counts as miss) | 19 / 20 | 0.950 | [0.764, 0.991] | {'no': 19, 'yes': 1} |
| Specificity on broken (unclear excluded) | 19 / 20 | 0.950 | [0.764, 0.991] | {'no': 19, 'yes': 1} |

| Scope | Judged equivalent / answered | Proportion | 95% Wilson | Unclear / answered | Missing | Counts |
|---|---|---|---|---|---|---|
| All generated | 280 / 288 | 0.972 | [0.946, 0.986] | 5 / 288 | 0 | {'yes': 280, 'no': 3, 'unclear': 5} |
| Arm A | 142 / 144 | 0.986 | [0.951, 0.996] | 1 / 144 | 0 | {'yes': 142, 'no': 1, 'unclear': 1} |
| Arm B | 138 / 144 | 0.958 | [0.912, 0.981] | 4 / 144 | 0 | {'yes': 138, 'no': 2, 'unclear': 4} |
| Cell cardiology__symptom_description | 31 / 32 | 0.969 | [0.843, 0.994] | 0 / 32 | 0 | {'yes': 31, 'no': 1} |
| Cell cardiology__body_part | 30 / 32 | 0.938 | [0.799, 0.983] | 0 / 32 | 0 | {'yes': 30, 'no': 2} |
| Cell cardiology__medication | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell neurology__symptom_description | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell neurology__body_part | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell neurology__medication | 30 / 32 | 0.938 | [0.799, 0.983] | 2 / 32 | 0 | {'yes': 30, 'unclear': 2} |
| Cell gastroenterology__symptom_description | 32 / 32 | 1.000 | [0.893, 1.000] | 0 / 32 | 0 | {'yes': 32} |
| Cell gastroenterology__body_part | 31 / 32 | 0.969 | [0.843, 0.994] | 1 / 32 | 0 | {'yes': 31, 'unclear': 1} |
| Cell gastroenterology__medication | 30 / 32 | 0.938 | [0.799, 0.983] | 2 / 32 | 0 | {'yes': 30, 'unclear': 2} |

## Estimand 5: exemplar sensitivity, Arm A (random exemplars) minus Arm B (fixed exemplars)

| Estimand | Arm A | Arm B | A minus B | 95% interval for the difference |
|---|---|---|---|---|
| 2 novelty (pair) | 0.993 | 1.000 | -0.007 | [-0.038, 0.020] (Newcombe) |
| 3 within-cell diversity (mean cosine) | 0.070 | 0.075 | -0.005 | [-0.019, 0.009] (bootstrap, 2000 replicates, 0 undefined) |
| 3 generated vs seeds (mean cosine) | 0.060 | 0.065 | -0.005 | [-0.013, 0.002] (bootstrap) |
| 4 equivalence (yes / answered) | 0.986 | 0.958 | 0.028 | [-0.014, 0.075] (Newcombe) |

## Human review sample

review_sheet.csv holds 40 rows; allocation by arm {'A': 20, 'B': 20} from checked rows by arm {'A': 144, 'B': 144}. Agreement is not computed here.
