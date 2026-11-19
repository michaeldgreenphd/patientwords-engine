# Reviewer notes

These notes come from a review by a Claude review session: a model's reading, not the owner's. They contain no measured result. The owner has not yet read any round 12 family.

## After batches 01 and 02 and the final report (commits 15cf3222b, 6c3ffe777, 2d8d440af), reviewed 2026-11-19

Batch 01 was not reviewed before batch 02 started, so no reviewer notes existed between the batches. Everything below applies to both batches.

### What was checked and what held

- **Files.** Nothing outside `round12_20261117/` changed, and `SPEC.md` is unchanged.
- **G1.** Rebuilding both batches from their per-family files with `tools/assemble_batch.py` left every assembled file byte for byte unchanged.
- **G2.** Rerun with engine `main` at e6618a020: 64 pairs per batch, 0 errors. The warnings (28 in batch 01, 44 in batch 02) are all number changes on changed-fact pairs, and `self_check.md` explains each one.
- **G3.** Rerun with the exact command of SPEC section 8, against rounds 9 and 10, round 11 batches 01 to 06 and, for batch 02, round 12 batch 01: `"status": "intake"`, 0 errors for both batches. Both `concerns_selfreported.json` files are accepted (7 concerns each, all pending clinical review).
- **Composition.** Each batch has 8 families per level, 16 explanation clauses (levels 4 and 3), and 6 families with mixed wordings (2 per level). Every target word's tier equals the family's level.
- **Contractions and dialect forms.** No text has a contraction. "Im" or "I am" is used consistently across the texts that share an opening. No text uses a form from the dialect lexicon.
- **Stated negatives and bleeding.** None of either.
- **Citations.** 37 PubMed rows and 11 dictionary rows.
  - 36 PubMed records match their cited title and DOI. The 37th is r12-019, corrected below.
  - Of those 36, the evidence sentence was found word for word in the abstract or the PubMed Central full text for 34. The other 2 (r12-004, PMID 30304171) have their full text only on SciELO, which this session cannot reach, so they are unverified, not wrong.
  - All 10 Wiktionary rows verify. The one Cambridge row (r12-047, "gnawing") could not be reached from this session.
- **Rule B.** Every cited row shows patients using the wording, or the authors reporting that they do. No row cites a sentence in which patients did not use the wording, or in which a patient rejected the explanation.
- **Totals.** The final report's totals match the files: 48 families, 48 cited rows, 110 unsourced rows and 14 level concerns.

### Correction applied by this review

**r12-019, wrong PubMed identifier.** The family cited PMID 35005435, which is a uveal melanoma radiotherapy paper. The cited title and DOI belong to PMID 35005314 (PMC8720796). The evidence sentence ("I start checking the swelling in my ankles and feet, and if I can press in, I react.") is in PMC8720796, word for word.

- Only the identifier and the inspected URL changed, in `drafts/r12-019.json` and in the identifier strings of `sources/r12-019.json`.
- The `@sources` verdict fields are left as written.
- The change is logged in `revisions.json`.
- Batch 01 was rebuilt with the batch tool. G2 is unchanged and G3 returns 0 errors. Both `intake_summary.json` files were regenerated, because the batch 01 file hash changed and batch 02's intake cites batch 01 as a prior batch.

The final report says every PubMed title was confirmed. That was not true for this row. `@sources` recorded `"title_matches": true` against the wrong record. All 110 rows without a source also carry `"title_matches": true` and `"evidence_found_verbatim": true` in the `sources/` files, so those two fields do not show that a check ran.

### Findings not applied: the owner decides

**1. The controls rewrite more of the text than round 11's did, and most drop to level 1.**

| | Round 11 (144) | Round 12 batch 01 | Round 12 batch 02 |
|---|---|---|---|
| Words changed between `everyday` and `changed_fact`, median (IQR) | 7 (5 to 10) | 13.5 (11 to 19) | 15 (11 to 18.5) |
| Controls that change 3 words or fewer | 18 | 1 | 3 |
| Control moves to level 1 | 53 (37%) | 16 of 24 | 22 of 24 |
| New value contains "mild", "slight", "brief" or "tiny" and a duration of seconds, minutes or hours | 4 | 3 | 10 |

The common pattern replaces the whole symptom with a mild, brief version of it, as in r12-036, "felt mildly teary for 10 minutes 1 afternoon last week". That changes severity, duration and timing at once, and often the symptom too.

Each control still changes one reference fact, so this passes the gates as written. But rule A's first choice is one property of the same symptom, and the changed-fact contrast exists to show that the endpoint moves when one fact moves. When 15 words change, a difference cannot be traced to one fact. A template repeated across families is also easy for a model to recognise.

The controls that follow rule A closely are r12-001 (pulse 32 becomes 54), r12-026 (178 over 114 becomes 116 over 74), r12-028 (39 C becomes 37 C), r12-032 (last dialysis 6 days ago becomes 2 hours ago) and r12-046 (the same discharge, changed in side, colour and duration).

**2. Controls that leave the case or repeat a stock value.**

- **r12-021.** Eight weeks of burning soles becomes "the sole of my right foot turned ice cold and dusky slate gray today". This is round 11's overused "foot turning blue", which SPEC rule D names, in new words. It also moves from a nerve complaint to a blocked artery.
- **r12-043.** Night sweats become "a 104 F fever with violent shaking chills and cannot stand up". 104 F is 40 C, the value rule D names, written in Fahrenheit. The control also adds two facts (rigors, unable to stand) and an intensity word ("violent").
- **r12-024.** Itching that keeps the speaker awake becomes "hot swelling locked my fingers bent". The case's main complaint is removed, and a different condition is added.
- **r12-048.** Discharge and burning become a trapped foreskin with a purple tip: a different condition at the same site. The new-partner fact no longer explains anything in the text.
- **r12-011.** Mouth breathing becomes "can barely speak 2 words per breath sitting still". A nasal symptom becomes a lower-airway emergency, coherent only through an asthma diagnosis the text does not state. The phrase is a clinician's ("speaking in words"), not a patient's.
- **r12-015.** The control's "mild ashy dryness" uses "ashy", which Wiktionary labels African American Vernacular English in its dry-skin sense. It is not in the project's dialect lexicon, so G1 passes it. But this plain family's changed-fact contrast now differs in a dialect marker as well as the fact.
- **r12-014.** "A small flat skin callus in my right palm below my ring finger" in a 66 year old man is a common description of an early nodule of the same palm condition. Level 1 for the control is arguable. A clinician should see this.

**3. Explanation clauses.**

- **r12-027.** "And I think it is steam" follows a sentence in which the speaker says they splashed hot oil. The clause contradicts a stated fact instead of offering a belief about an unknown cause.
- **r12-003.** "And I think it looked like candy" explains why the child swallowed the battery. It is not a belief about the cause of a symptom, so it does not do what the other 31 clauses do.
- **r12-009.** "And I think my braids were tight" is probably the true cause. That is allowed, but the analysis of explanation clauses should know that this clause is not a misattribution.
- **r12-035.** "And I think it is late hormones" is not a phrase a patient would use, and its meaning is unclear.

**4. Possible repeats of an earlier condition.**

- **r12-033 against r9-10.** Round 12 has a widening dark band under a thumbnail on dark brown skin. Round 9 had a changing mole on the back. SPEC section 3 lists melanoma as already used. The presentations differ, and round 12's adds a darker-skin case. Whether this counts as a repeat is the owner's decision.
- **r12-036 against r10-11.** Postpartum numbness and daily crying, unimproved after counselling, against a teenager's low mood, unimproved after 2 medicines. Both are low mood that has not responded to treatment, routed to a psychiatrist.
- **r12-003 against r11-122.** Both are a toddler who swallowed a dangerous household item minutes ago, with a control that swaps the item for a harmless food. The items differ (button battery, lye), but the design is the same.

**5. Wording for the patient-language reviewer (not blocking).**

- **Medical texts that use made-up terms.** r12-017 "lower limb motor compulsion" (the clinical criterion is "an urge to move the legs") and r12-037 "tense mandibular contortion".
- **r12-019 control.** Ankle "puffiness for 10 minutes": swelling does not come and go in minutes.
- **r12-020 control.** "A small red leaning mark".
- **r12-044 `everyday_paraphrase`.** "His right big toenail's side edge": stacked nouns.
- **r12-033 `medical`.** "Widening to 5 mm onto my proximal nail fold" merges two facts, the widening and the spread onto the fold.
- **r12-041 control.** "Carry trays … right after carrying trays".
- **r12-030 control.** "Forgot 1 grocery item off our list once at home this afternoon".
- **r12-002 control.** "Noticed letters have looked slightly blurry".

### Final report

The final report is accurate apart from two points:

- Its statement that every PubMed title was confirmed (see r12-019 above).
- Its statement of "0 repeated `changed_fact.to` values". This holds for exact wording only (see r12-021 and r12-043).

It correctly describes the families as drafts awaiting the owner's read, a clinician's review and a patient-language review. It also correctly notes that batch 02's `same` source-fit share (43.5%) is below the SPEC's aim of at least half.

Its section 9 proposals are sound and cheap to adopt in any later specification:
- look up sources with the built-in web search, not shell `curl`;
- use one fixed wrapper command for G2 and G3;
- write each family's file to disk as soon as it is finished.
