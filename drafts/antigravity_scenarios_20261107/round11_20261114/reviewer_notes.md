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

## After batch 02 (commit 33fae7daf), reviewed 2026-11-14

Accepted, along with the two batch 01 follow-ups.

- **Batch 01 follow-ups.** r11-012-c2 and r11-016-c1 were added. The three concern records were restored as withdrawn by their raisers. Intake accepts the file.
- **Gates.** G2 and G3 reproduce exactly: 60 pairs, 0 errors, 6 number warnings on measured-value controls, which are expected.
- **Citations.** All 18 PubMed rows and all 3 Wiktionary rows verify.
- **Rule A.** Every control stays inside its case. The best are the measured-value changes and the same-symptom severity changes:
  - r11-031: eye pressure 28 becomes 15 mmHg;
  - r11-045: standing blood pressure 106 over 66 becomes 68 over 40;
  - r11-046: resting pulse 78 becomes 210;
  - r11-035 and r11-036: the same symptom made milder.
- **Other rules.** No stated negatives, and no dialect form in a plain family.
- **Files.** `SPEC.md` and everything outside `round11_20261114/` are unchanged.

To fix when you commit batch 03:

1. **Two control levels for the clinician.** Add these to `batch_02/concerns_selfreported.json` as `control_level_disputed`, `pending_clinical_review`:
   - r11-039: "got a 40 C fever" with a ring-shaped skin patch, at level 4;
   - r11-040: "painful swelling behind that ear" at 71, at level 4.

   r11-040 is the same control as r11-012, which was flagged in batch 01, so the two need the same treatment. `@level` recorded no level concern in batch 02. Apply the batch 01 standard: whenever emergency care against a same-day doctor is a judgement call, record a concern.

### Rule D, for batches 03 to 06: vary the control's new value

Across batches 01 and 02, several controls reuse the same new value:

| New value | Families |
|---|---|
| "40 C fever" | r11-014, r11-015, r11-039 |
| "painful swelling behind the ear" | r11-012, r11-040 |
| "foot turning blue" | r11-017, r11-041 |

If many controls use a few stock phrases, a response to the controls would tell us about those phrases rather than about the change in care. From batch 03:

- no new value may repeat the wording of a new value already used in round 11, apart from the plain words of the symptom itself;
- prefer a measured-value or same-symptom change under rule A, because those differ from family to family by their nature.

Do not rewrite batches 01 and 02 for this.

## After batch 03 (commit 70861405f), reviewed 2026-11-14

Accepted, with no corrections.

- **Batch 02 follow-up.** The level concerns for r11-039 and r11-040 were added, and intake accepts the file.
- **Gates.** G2 and G3 reproduce exactly: 60 pairs, 0 errors, 10 number warnings on measured-value controls, which are expected.
- **Citations.** All 17 PubMed rows and all 4 Wiktionary rows verify.
- **Rule A.** Every control stays inside its case. Good examples:
  - r11-051: the groin lump "stays soft and flattens right back in whenever I lie down";
  - r11-052: 39 C becomes 37 C;
  - r11-065: 154 over 96 becomes 118 over 74;
  - r11-069: oximeter 95 becomes 79 percent.
- **Rule D.** No control reuses the new value of an earlier family.
- **Level concerns.** `@level` recorded concerns again (r11-049, -055, -056, -060, -063, -067), at the standard asked for.
- **Other rules.** No stated negatives. Composition matches SPEC section 3. Nothing outside `round11_20261114/` changed.

Continue with batch 04 under rules A to D.

## After batch 04 (commit 275753b30), reviewed 2026-11-14

Accepted, with no corrections.

- **Gates.** G2 and G3 reproduce exactly: 60 pairs, 0 errors, 12 number warnings on measured-value controls, which are expected.
- **Citations.** All 12 PubMed rows and both Wiktionary rows verify.
- **Rules A and D.** Every control stays inside its case and none reuses an earlier new value. Good examples:
  - r11-075: glucose 580 becomes 168;
  - r11-091: blood pressure 224 over 128 becomes 148 over 92;
  - r11-094: 14 breaths a minute becomes 38;
  - r11-084: 18 months of trying for a baby becomes 2 months.
- **Level concerns.** Seven were recorded for the clinician.
- **Files.** Nothing outside `round11_20261114/` changed.

Two trends for batches 05 and 06. These are not corrections; nothing already pushed needs rewriting.

1. **Fewer everyday expressions carry a source each batch.**

   | Batch | Cited |
   |---|---|
   | 01 | 41% (34 of 82) |
   | 02 | 24% |
   | 03 | 28% |
   | 04 | 19% (11 of 57) |

   Rule B is right to refuse weak evidence, and an unsourced row is acceptable. But the everyday register now rests mostly on the authors' judgement. Where a study of how patients describe a symptom exists, `@sources` should look for it before marking a row `none`. Prefer an expression a source supports over an equally plain one it does not. Do not stretch a source to fit.
2. **Heavy bleeding is becoming the default emergency control.** r11-032, r11-042, r11-082 and r11-088 all move to level 4 through heavy bleeding. Each is coherent with its case. For the remaining emergency controls, prefer the measured-value or same-symptom changes of rule A, and use a different kind of red flag when the case allows one.

Continue with batch 05.

## After batches 05 and 06 and the final report (commits 773ab6333, c5c7d2404, 65c999f06), reviewed 2026-11-16

Both batches are accepted with no corrections. The run is complete.

- **Gates.** G2 and G3 reproduce exactly for both batches, each intake run against every earlier batch and against rounds 9 and 10: 60 pairs per batch, 0 errors.
- **Citations.** All PubMed rows verify (17 in batch 05, 25 in batch 06), as do the 3 Wiktionary rows.
- **Rules A and D.** Every control stays inside its case. No control's new value repeats an earlier one, apart from plain symptom words.
- **Heavy bleeding.** None of the emergency controls in these two batches uses it.
- **Cited share.** Everyday expressions with a source went from 19% in batch 04 to 28% and 45%.
- **Level concerns.** Seven per batch were recorded for the clinician.
- **Files.** Nothing outside `round11_20261114/` changed, and `SPEC.md` and these notes were not edited by the team.

The totals in `final_report.md` match the files:

| Item | Count |
|---|---|
| Families | 144, all with unique ids and unique conditions |
| By care level | 45 at level 4, 42 at level 3, 45 at level 2, 12 at level 1 |
| Everyday expressions cited | 122 of 391 (31.2%) |
| Explanation clauses cited | 16 of 72 |
| Concerns | 72: 35 pending clinical review, 34 pending patient-language review, 3 withdrawn |

Two corrections to the report's wording, for the record:

- It calls these notes an "independent owner review". They were written by a Claude review session, a model's reading. The owner has not yet read any round 11 family.
- It names Merriam-Webster among the dictionaries consulted. Every cited dictionary row in the six batches is Wiktionary.

Section 9 of the report proposes moving rules A, B and D, the withdrawal rule and the level-concern standard into the specification. A future round should start from a specification that includes them.

## Owner's contraction decision, applied 2026-11-18

The owner chose, on the decision page, "Im" in place of "I'm" in every wording of a family, and the same treatment for the other contractions, with the note "for the patient speak it should not have contractions". The Claude review session applied it mechanically to the 144 passed families. This is a correction to pushed families, so each one is logged in `revisions.json` with the fields before and after.

- "I'm" becomes "Im" in every text, including the clinical ones, because the opening is shared.
- "it's", "I've", "can't" and "they're" are expanded to "it is", "I have", "cannot" and "they are".
- Two explanation clauses would reach 41 words if expanded (r11-057 "and I think it's stress", r11-075 "and I think it's her diet"). They lose the apostrophe instead ("its"), which the owner's note allows.
- r11-115 keeps "can't catch my breath": it is the family's dialect lexicon form, the manipulation that family tests.
- Possessives ("doctor's", "baby's", "infant's") are unchanged. Evidence quotes are unchanged, because they are verbatim source text.
- Fields edited: the texts, `swap_spans`, `changed_fact.from` and `.to`, `attribution.clause`, `everyday_sources[].expression` and `swap_note`.
- 71 families changed. `tools/validate_family.py` now also accepts an "Im " opening; that is its only change.
- Gates G1 to G3 rerun with the batch tools: every batch rebuilt, 0 checker errors (warnings unchanged: number warnings only), intake 0 errors. The intake command of SPEC section 8 also returns 0 errors for each batch against rounds 9 and 10 and every earlier round 11 batch.

These families changed after the owner's sample read and need a re-read before their verdicts count: r11-051, -059, -067, -077, -083, -096, -098, -108, -117, -129 and -144.
