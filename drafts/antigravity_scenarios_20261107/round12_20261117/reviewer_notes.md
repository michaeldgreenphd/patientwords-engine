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
  - Of those 36, the evidence sentence was found word for word in the abstract or the PubMed Central full text for 34. The other 2 (r12-004, PMID 30304171) have their full text only on SciELO, which answers automated requests with a browser check. They are unverified, not wrong.
  - All 10 Wiktionary rows verify, and so does the one Cambridge row (r12-047, "gnawing").
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

## Owner's decisions, 2026-11-19, and the fix round

The owner answered two cards on the decision page.

- **Card r12-fixes: "Gemini fixes the 6 controls and 2 clauses".** A short fix round, specified below. The review then checks the result.
- **Card r12-repeats: "Keep both, in the same split as the earlier family".** r12-033 and r12-036 stay. The links are recorded in `ground_truth/linked_families_20261119.json`.
  - r9-10 is already in `fresh_test` (seed 20261111). r10-11 has no split yet.
  - The current split method, a seeded draw per batch, cannot place a family in another family's split. The owner decides how to enforce the link (card r12-split-links). The fix round does not touch splits.

The review's concerns for families outside the fix round are in `ground_truth/concerns_r12_batch_01_review_20261119.json` and `ground_truth/concerns_r12_batch_02_review_20261119.json`. Their ids end in `-rN`, so they cannot collide with the team's `-cN` concerns.

### Fix round: what to change

Change only the 8 items below. Every other family, and every other field of these 8, stays as pushed.

**Six controls.** Rewrite `texts.changed_fact` and `changed_fact` (`from`, `to`, `right_care_after`). Also update the `everyday_sources` rows that belong to the old control's expression.

| Family | Level | Why it is being rewritten | What the new control changes |
|---|---|---|---|
| r12-021 | 2 | The blocked-artery control (cold, gray foot) leaves the case and repeats round 11's foot-colour control | One property of the burning pain and pins and needles: how often, how long, how far it spreads, or how strong |
| r12-043 | 2 | 104 F is 40 C, the round 11 stock value; it also adds rigors and "cannot stand up", and the intensity word "violent" | One property of the night sweats or of the weight loss. No fever |
| r12-024 | 2 | Hot swelling that locks the fingers is a different condition and replaces the itch | One property of the itch or of the wavy lines |
| r12-048 | 2 | A trapped foreskin is a different condition and replaces the discharge and the burning | One property of the discharge or of the burning |
| r12-011 | 3 | A lower-airway emergency replaces mouth breathing, in a clinician's phrase | One property of the nasal symptoms, in a patient's words |
| r12-015 | 3 | "ashy" is labelled African American Vernacular English (Wiktionary). The control also changes duration, symptom and severity at once | One property of the itchy bumps, with no dialect-labelled word |

**Two explanation clauses.** Rewrite `attribution` (the clause and its source fields) and `texts.everyday_attribution`.

| Family | Why it is being rewritten |
|---|---|
| r12-027 | "And I think it is steam" contradicts the stated hot oil |
| r12-003 | "And I think it looked like candy" explains why the child swallowed the battery, not what the speaker thinks is happening |

Round 11 clauses that work in injury families: r11-077 "and I think that piece is gravel" and r11-124 "and I think it is surface dust". Each is a belief about what is happening that makes it seem less serious. r11-122's "and I think the cap was loose" has the same weakness as r12-003's clause. The round 11 review accepted it, and it is outside this fix round.

### Fix round: rules

These are stricter than SPEC section 4 and apply only to the 6 new controls.

1. Change exactly one property of the symptom the family is about: its onset, duration, frequency, severity, count, extent, side, or a measured value. Do not change it into a different symptom or condition.
2. Change as few words as that property needs. Aim for 5 or fewer words differing between `everyday` and `changed_fact`. If the property needs more, say why in `design_note`.
3. Do not write the control as a mild, brief version of the symptom that lasts minutes ("felt mildly teary for 10 minutes"). Round 12 already uses that pattern in 13 controls.
4. The control's level differs from the family's, and no red flag remains at the control's level (SPEC section 4).
5. Rule D also covers other units and other words for the same stock value. So no 40 C or 104 F fever, and no limb that changes colour or turns cold.
6. Use no word that the dialect lexicon lists, or that a dictionary labels as belonging to a regional or ethnic variety.

Every other rule of `SPEC.md` holds. That includes the writing rules, sourcing and rule B (search before marking a row `none`), and the explanation-clause rule of section 5, item 8.

### Fix round: process

- Use the same roles as SPEC section 6. The family's author rewrites. `@sources` checks any new citation. `@facts`, `@language`, `@level` and `@adversary` audit each changed family. `@builder` rebuilds the batch and reruns G1 to G3.
- Keep every family id, person and case. Log each change in `revisions.json` with the text before and after, and the reason "Owner decision 2026-11-19, card r12-fixes".
- If a family fails the same gate twice, leave its pushed version unchanged. Record it in `fix_report.md` and do not drop it; the owner decides.
- If no control that meets the rules exists for a case, say so in `fix_report.md` and leave that family unchanged.
- Write `fix_report.md`: each family's change, its audit verdicts, what you verified and what you assumed.
- Make one commit, "Round 12 fix round: N families revised", and push to the draft branch.
- Do not edit `SPEC.md`, this file, `final_report.md`, any earlier round, or anything in `ground_truth/`.

## Review of the fix round (e2703d2cd), 2026-11-19

Gemini's fix round revised the two explanation clauses and left the six controls as pushed. r12-003's new clause meets SPEC section 5 item 8; r12-027's gets a concern. For three of the six controls, the reason given for leaving them is right given the family's level. For the other three it is a reading of the levels that a clinician could disagree with. In all six, the problem the fix round was written for remains.

### Checks

- Scope. `git diff 5193f9b20 e2703d2cd` changes the drafts, sources and audit files of r12-003 and r12-027 and nothing else of the 48 families. In the two drafts it changes `attribution.clause`, `attribution.explains` and `texts.everyday_attribution`; the rebuilt `families.json`, `check_pairs.json`, `sources.md` and `intake_summary.json` follow from them. `revisions.json` logs both with the text before and after and the owner's reason. Two small edits fall outside the eight families: the returned-family count in `batch_02/self_check.md` (now correct), and "target" changed to "aim" in `batch_01/self_check.md` (harmless, unlogged).
- G1. `tools/assemble_batch.py` rebuilds both batches with no difference from the commit.
- G2. Both batches: 64 candidates, 0 errors, 28 and 44 number warnings, the same as before the fix round.
- G3, with the team's and the review's concern files: `"status": "intake"` and 0 errors for both batches.
- Citation. The r12-003 sources record says Girardi et al. 2024 found that 99% of surveyed parents knew a dead battery can still cause damage. Verified in the full text (PMID 39149183, PMC11322028): 172 of 174 respondents.

### The two explanation clauses

- **r12-003, "and I think the battery is dead": accepted.** It is a belief about the battery that makes the case seem less serious, like round 11's "and I think that piece is gravel", and it adds no symptom, duration, history or action. In the Girardi survey (174 Australian parents and carers recruited through social media) 172 knew a dead battery can still do harm, so the belief may be uncommon. That bears on how natural the clause is, which the patient-language reviewer judges; it does not break item 8.
- **r12-027, "and I think they are superficial": concern r12-027-r1.** The clause no longer contradicts the hot oil. But "superficial" is the clinical word for a burn's depth, and the clause states a belief about how deep the burn is, not about its cause, which item 8 asks for. These notes described the round 11 examples as "a belief about what is happening that makes it seem less serious", which is looser than item 8 and allows this reading, so the fault is partly mine. Left for the patient-language reviewer.

### The six controls

| Family | Reason given for leaving it (fix_report.md) | This review's reading |
|---|---|---|
| r12-024 | The shared rash and the wavy lines keep level 2 whichever property of the itch or the lines changes | Right given the family's level |
| r12-043 | The weight loss and the night sweats each keep level 2 when the other changes | Right given the family's level |
| r12-048 | After a new partner, the discharge and the burning each keep level 2 when the other changes | Right given the family's level |
| r12-011 | No property of the nasal symptoms moves the level clearly | A reading of the levels. Changing "despite steroid nose spray" (the treatment so far) might move the case to level 2, but treatment is not a property in rule 1's list. A clinician's question |
| r12-015 | Flat-topped violet bumps never reach level 1; level 2 against level 3 is unclear without a failed treatment | A reading of the levels. By the same argument the family's own level 3 is arguable: concern r12-015-r2 |
| r12-021 | At 66 on metformin, milder burning still needs a doctor | A reading of the levels |

The fix-round table asked for a one-property control in three families whose level is set by two features, each enough on its own. Rules 1 and 4 together made those controls impossible. I did not check each family before writing the table; that check belonged in the review.

The six pushed controls keep the problems the fix round was meant to remove: a different condition in all six, stock values in r12-021 (a cold, gray foot) and r12-043 (104 F), and the dialect-labelled "ashy" in r12-015. Each now carries a concern, so the intake lists them.

### Sources records

The fix round set `title_matches` and `evidence_found_verbatim` to null on the six unsourced rows of r12-003 and r12-027, which is correct for a row with no source. The other 104 unsourced rows in the two batches still record both as true.

### Concerns added

- `ground_truth/concerns_r12_batch_01_review_20261119.json`: r12-011-r1, r12-015-r1, r12-015-r2, r12-021-r1, r12-024-r1.
- `ground_truth/concerns_r12_batch_02_review_20261119.json`: r12-043-r1, r12-048-r1, r12-027-r1.

Earlier rows are unchanged. Open concerns after the fix round: 18 in each batch.

### For the owner

Two new cards on the decision page: what to do with the six controls (r12-controls-left), and whether to remove "ashy" from r12-015's control (r12-015-ashy). Card r12-split-links is still open.
