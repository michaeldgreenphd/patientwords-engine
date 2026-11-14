# Reviewer notes

These notes come from an independent review of each pushed batch. They contain no measured result. Apply them to every later batch. Where a note changes a rule of `SPEC.md`, the note is right. `SPEC.md` itself stays unedited.

## After batch 01 (commit fa68f2e4f), reviewed 2026-11-14

### What was checked and what held

- **Gates G2 and G3.** Rerun independently with the exact commands of SPEC section 8. Both reproduce byte for byte: 60 pairs, 0 errors, 3 number warnings on the controls; intake 0 errors.
- **Citations.** 42 PubMed rows. All 42 records exist, and every title and DOI matches. For 40 rows the evidence sentence was found in the abstract or the PMC full text. The other 2 (r11-001, PMID 11976241) could not be checked: the PMC record returned no body text.
- **Rules.**
  - No family has a stated negative; round 10 had 15. Keep doing this.
  - No plain family uses a dialect form.
  - Every dialect paraphrase keeps its form.
  - Every explanation clause is a single inserted clause stating a belief.
  - Composition matches SPEC section 3.
- **Files.** Nothing outside `round11_20261114/` changed, and `SPEC.md` is unchanged.

### Corrections to batch 01: do these first

Keep each family's id. Change only what is listed below. Record every change in `revisions.json` with the text before and after. Rerun gates G1 to G8 on the changed families, then commit and push the corrections as one commit, before batch 02 starts.

**1. Controls that move to an unrelated case (8 families).** In these families the control replaces the main symptom with one from another body system. The other facts no longer fit the case, so the control reads as a different situation:

| Family | Current control |
|---|---|
| r11-004 | a teenager after a workout, then "white pus on his tonsils" |
| r11-005 | farsightedness, then "pus draining beside my right thumbnail" |
| r11-006 | a long flight on the pill, then "blood in my urine" |
| r11-010 | sleepless nights and rapid speech, then "collapsed unconscious" |
| r11-012 | one-sided hearing loss, then "slurring my words" |
| r11-015 | sores around the mouth, then "hard to wake up" |
| r11-016 | vaginal itching after cream, then "fainted 2 times" |
| r11-024 | ferry queasiness, then "start wheezing" |

Your own auditors flagged two of these (r11-004-c1, r11-005-c1) but could not block them, because SPEC allowed "one present symptom against a different present symptom". That wording was too loose; rule A below replaces it. Rewrite each of these controls under rule A.

**2. Sources that do not show the wording in use (4 families, 5 rows).** Either find a source that meets rule B below, or set the row to `"source": "none"`. Then update `sources.md`, `source_fit.json` and the family file.

| Family | Row | Problem |
|---|---|---|
| r11-001 | "crushing pressure behind my breastbone" | The evidence says heart attacks were reported *instead* of as "crushing chest pain". It shows patients did not use the wording. |
| r11-001 | "and I think it is heartburn" | The patient's words are "I thought this can't be heartburn". The patient rejected the explanation the clause states. |
| r11-008 | "and I think it is just teething" | The evidence is a clinical statement that pericoronitis occurs during eruption, not a patient's belief. |
| r11-009 | "and I think it is poor hygiene" | The evidence is about clinicians' misdiagnoses, not a patient's belief. |
| r11-012 | "and I think it is from getting older" | The evidence is the definition of presbycusis, not a patient's belief. |

### Rules for batches 02 to 06

**A. The changed-fact control stays inside the same case.**

- First choice: change a property of the same symptom. That means its onset, duration, frequency, severity, count, or a measured value.
  - Batch 01 examples to follow: r11-021, "3 brief fits each month" becomes "3 brief fits this hour"; r11-023, "dry peeling skin" becomes "oozing thick yellow pus".
- A different symptom is allowed only at the same body site or in the same organ system, and only when every other fact still fits the changed text.
  - Batch 01 examples that meet this: r11-001's dry cough two weeks after starting blood pressure medicine; r11-014's 40 C fever with the swollen toe joint.
- Read the whole control text aloud. If a clinician would ask "why did you mention the other facts?", the control has left the case.
- `@level` and `@adversary` check this and return a family that fails it, under G6 and G8.

**B. Evidence must show the wording in use.**

- The evidence sentence must show patients or carers using the expression in that sense, or the authors reporting that they do. For an explanation clause, it must show a patient or carer giving that explanation, or the authors reporting that patients give it.
- These do not support a row:
  - a sentence that mentions the expression to say patients did not use it;
  - a patient quote that rejects the explanation;
  - a clinical statement that the cause exists or is common.
- When only such a sentence exists, the row is `"source": "none"`. An unsourced row is acceptable.
- `@sources` checks this under G7.

**C. Wording to watch.** These are not corrections. They are logged for the patient-language reviewer, and later batches should avoid the same pattern.

- r11-002's everyday "blocking the field of view" is not how most patients describe it.
- r11-017's "with right foot arch tightness" stacks nouns where a patient would say "my right arch feels tight".
- r11-018's medical "ciliary crusting" can be read as the ciliary body. "Crusting of the eyelashes" is unambiguous.

Write a plain everyday stretch the way a patient would say it, even if it then needs a different construction from the medical stretch. The 2-word length rule still applies.

When the batch 01 corrections are pushed, continue with batch 02.

## After the batch 01 corrections (commit 7fc15b689), reviewed 2026-11-14

Accepted.

- Only the listed fields changed, and all 11 changes are in `revisions.json`.
- G2 and G3 reproduce exactly.
- All 37 remaining PubMed citations verify (record, title, DOI and evidence sentence).
- The 8 controls now stay inside their cases. r11-024 ("mild queasiness" becomes "throw up repeatedly") is the first choice under rule A.

Two things to fix when you commit batch 02:

1. **Two control levels for the clinician.** Add these to `batch_01/concerns_selfreported.json` as `control_level_disputed`, `pending_clinical_review`:
   - r11-012, "painful swelling behind my left ear" at level 4;
   - r11-016, "severe lower belly pain" at level 4.

   Both are plausible. Whether each needs emergency care rather than a same-day doctor is a clinician's call. r11-006 and r11-015 are already recorded.
2. **Withdraw concerns; never delete them.** Three records (r11-004-c1, r11-004-c2, r11-005-c1) were removed when their controls changed. From now on:
   - keep the record;
   - set its disposition to `withdrawn`, with `by` and `by_kind` matching `raised_by` and `raised_by_kind`;
   - add a note naming the revision that made the concern moot.

   Restore the three records that way in the same commit.
