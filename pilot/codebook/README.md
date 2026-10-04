# Stimulus codebook and the owner's blind reviews

This directory holds what the owner's blind reviews of the stimulus-generation pilot produced: each review's export,
the codebook derived from the first review, and, for a version-2 run, the owner's answers compared with the
checker's. These are pilot outputs under the `AGENTS.md` pilot exception, not measurements: their numbers check the
pilot's prompts and pipeline and are never claims about the study's stimuli or its models.

A recorded run's review lives here, not in the run's directory, because that directory is sealed:
`pilot/runs/<run_id>/HANDOFF.md` is one of the outputs `write_manifest.py finalize` hashes, and the run's summary
hashes the review sheet before it is filled.

## Files

| File | What it is | How it is made |
|---|---|---|
| `review_export_pilot_real_20260930.json` | The owner's blind review of run 1 (`pilot_real_20260930`, made on the owner's laptop and not a recorded run; see `../prompts_v2/README.md`) | Exported from the private review page's database |
| `codebook_rules.json` | The codebook's rules, lexicon rulings and settled and open questions | Hand-written |
| `codebook_v0.2.json`, `codebook_v0.2.md` | Codebook v0.2 | `pilot/analysis/make_codebook.py`, from the run 1 export and the rules; `tests/test_pilot_codebook.py` checks the committed copy is current |
| `review_export_pilot_v2_20261002.json` | The owner's blind review of run 2 (`pilot/runs/pilot_v2_20261002/`) | Exported from the review page's database on 2026-10-04 (UTC) and joined to the run's review sheet; its provenance records the sha256 of five run files at export |
| `agreement_pilot_v2_20261002.json`, `agreement_pilot_v2_20261002.md` | The owner's run 2 answers against the checker's, on the same 40 rows | `pilot/analysis/review_agreement.py`, seed 20261002, 2000 bootstrap resamples; `tests/test_pilot_review_agreement.py` checks the committed copy is current |

`review_agreement.py` writes `agreement.json` and `agreement.md` into its output directory. The committed copies
carry the run id so that a later run's agreement cannot be mistaken for this one. To rebuild them:

```bash
python pilot/analysis/review_agreement.py --run-dir pilot/runs/pilot_v2_20261002 \
  --export pilot/codebook/review_export_pilot_v2_20261002.json --out-dir <scratch dir>
# then copy <scratch dir>/agreement.json and agreement.md here as agreement_pilot_v2_20261002.json and .md
```

The two exports differ in shape. Run 2's rows carry `cell` (specialty and swap type) but no separate `specialty` and
`swap_type` fields; their `checker` block holds the verdict only, and the run's other checker answers are in its
`checked.jsonl` and `review_key.csv`. Run 2's provenance also has no `review_page_questions`, which
`make_codebook.py` reads, so that script does not run on the run 2 export as it stands. Both exports record blinding
on every row (`checker_shown_before_first_answer`).

## Review log

Sample ids (`r001` to `r040`) are per run: the same id names different pairs in the two runs.

Entry dates are in UTC, the date of the owner's first answers (run 1's export file records its local export date, 2026-10-01).

### 2026-10-02: run 1 (`pilot_real_20260930`)

Recorded as codebook v0.2's baseline (`codebook_v0.2.md`, *Baseline from the first review*), with the rules R1-R9
that review led to.

### 2026-10-04: run 2 (`pilot_v2_20261002`)

The owner reviewed all 40 sampled pairs. Every first answer was saved before the checker's answer was shown, no
answer was changed after it was first saved, and 9 rows carry a note (run 1: 19). Counts below are of first answers.

Headline measures, with 95% Wilson intervals as in codebook v0.2's baseline:

| Measure | Run 1 | Run 2 |
|---|---|---|
| Kept as is | 18/40, 45% (31-60%) | 27/40, 68% (52-80%) |
| Both sentences read naturally | 21/40, 52% (38-67%) | 25/40, 62% (47-76%) |
| Patient phrase sounds real | 19/40, 48% (33-62%) | 24/39, 62% (46-75%) |

Every answer, by question (the export's field names):

| Question | Answer | Run 1 | Run 2 |
|---|---|---|---|
| `keep` | keep / edit / drop | 18 / 13 / 9 | 27 / 11 / 2 |
| `patient_real` | real / textbook / unlikely / no answer | 19 / 15 / 6 / 0 | 24 / 15 / 0 / 1 (r006) |
| `sentence` | both / clinical_only / patient_only / neither | 21 / 5 / 7 / 7 | 25 / 6 / 5 / 4 |
| `same` | yes / no / unclear | 27 / 2 / 11 | 24 / 6 / 10 |
| `precision` (new in run 2) | as_precise / vaguer / more_specific | not asked | 12 / 28 / 0 |
| `clinical_right` | yes / close / no / no answer | 22 / 16 / 1 / 1 | 24 / 15 / 1 / 0 |

Run 2 by swap type (the second part of `cell`):

| Swap type | Rows | Kept | Patient phrase real | Both sentences natural |
|---|---|---|---|---|
| medication | 10 | 9 | 5 | 7 |
| body part | 15 | 8 | 9 | 8 |
| symptom description | 15 | 10 | 10 | 10 |

The owner against the checker (`agreement_pilot_v2_20261002.md`):

| Question | Agreement (95% CI) | Kappa (95% bootstrap CI) | Note |
|---|---|---|---|
| Same thing | 24/40, 60% (45-74%) | 0.05 (-0.09 to 0.24) | Run 1: 23/40, 57%, kappa -0.04 |
| Precision | 21/38, 55% (40-70%) | 0.17 (-0.10 to 0.43) | 2 rows not comparable (checker relation `different`); of the 26 compared pairs the owner called vaguer, the checker's relation made 14 as precise |
| Sentence | 25/40, 62% (47-76%) | 0.00 | The checker answered both on all 40 rows |
| Patient phrase real | 24/39, 62% (46-75%) | 0.00 | The checker answered real on all 40 rows; r006 has no owner answer |

The checker-side keep rule R8 (keep when `sentence_natural` is both) has sensitivity 27/27 and specificity 0/13 against
the owner's keep: it keeps all 40 rows, including the 11 the owner would edit and the 2 the owner dropped.

**Conclusion.** The checker does not discriminate on naturalness or realism: it gave one answer to every row, so its
agreement with the owner is the share of rows where the owner gave that answer too, and its kappa is zero. Its keep
rule keeps everything. It cannot gate stimuli on these questions. Its answer to whether the two phrases mean the
same thing agrees with the owner's at chance level, as in run 1.

The owner's notes, by theme (full text in the export):

- Brand-for-generic swaps are acceptable but should not make up many stimuli (r001, r033). The run's checker
  labelled 50 of its 288 generated pairs `same_brand` (`pilot/runs/pilot_v2_20261002/HANDOFF.md`).
- "Quadrant" constructions read oddly or vaguely, the clinical side included (r011, r015).
- Templates should be in the first person, as a patient speaks ("my") (r013).
- Slang must be widely known: "ticker" was unfamiliar (r025).
- Patient phrases may need laterality or other specificity, such as which eyelid (r005).
- The clinical side sometimes reads robotic (r006). That note says the owner would keep the pair; the stored keep
  answer is edit, and the counts above use the stored answer.
- If a phrase is standard medical lexicon, it can be used; the owner left that to the lexicon on this pair (r017).

**Reading.** Kept rose from 18 to 27, dropped fell from 9 to 2, and patient phrases judged unlikely fell from 6 to 0,
the directions the version-2 prompts aimed for; answers of no to the same-thing question rose from 2 to 6. None of
these is a measured effect of the prompts: each sample is 40 rows, the review page showed which run was under review,
and the two runs differ in prompts, harness version and how the sample was drawn (run 2's sample holds 40 distinct
concepts, one row each).
