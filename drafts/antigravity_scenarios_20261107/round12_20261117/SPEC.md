# Round 12 specification: 48 plain register families

This file is the complete specification for round 12 of the PatientWords authoring work on branch `draft/antigravity-scenarios-20261107`. Rounds 9 to 11 produced 184 case families, 132 of them plain register families. Round 12 adds up to 48 more plain register families, in two batches of 24, written and checked by a team of agents that runs without waiting for anyone between batches.

Round 12 is round 11 with three changes:

1. Every family is a plain register family. There are no dialect or self-care families.
2. The rules the round 11 review added (A to D, concern withdrawal, the level-concern standard, searching before marking a row unsourced) are written into this file instead of a separate notes file.
3. No contractions, after the owner's read of round 11 (section 4, "Contractions").

**Every agent reads this whole file before doing anything, and again when it is unsure.** The coordinator does not summarise it for workers: each worker opens it.

Quality comes before count. A batch of 18 clean families is worth more than 24 with problems. Every rule here exists because an earlier round broke it.

---

## 1. Hard limits

These hold for every agent, for the whole run.

1. **Write only** under `drafts/antigravity_scenarios_20261107/round12_20261117/`. Never edit an earlier round's folder.
2. **Outcome-blind.** Do not open any measured result or anything derived from one:
   - `trace_out/`, `pilot/`, `data/pab/`, `data/simulated/pairs_*.json`, `data/simulated/agscen_*`;
   - `drafts/antigravity_scenarios_20261107/ground_truth/gt_measured_*.json`, `analysis.md`, and the round 5 to round 8 folders;
   - any path with `holdout` or `sealed` in its name;
   - the `patientwords` site repository.
3. **Nothing paid, nothing fired.** No API calls to any model provider. Do not edit anything under `.github/`, `ops/`, `scripts/` or `data/`, and no trigger file. Do not run any study model or tokenizer.
4. **No splits and no predictions.** Do not assign families to discovery, validation or test. Do not write what you expect a model to do.
5. **Web access is for sources only:** PubMed, DOI resolvers, PubMed Central and publisher pages, and the dictionaries named in section 7. Search terms are the expression and the condition, nothing about this project.
6. **Only the coordinator commits and pushes, and only to the draft branch.** No worker runs `git commit`, `git push`, `git merge` or `git rebase`. Nobody merges, force-pushes or opens a pull request.
7. No suicide or self-harm cases. No real names. No identifiable person.

What you may read: this file; `round9_20261110/`, `round10_20261112_rev1/` and `round11_20261114/` (including its `reviewer_notes.md` and `revisions.json`); `ground_truth/gt_r9_20261110.json`, `ground_truth/gt_r10_20261113.json`, `ground_truth/gt_r11_sample_20261117.json`; `ground_truth/concerns_r9_20261112.json`, `ground_truth/concerns_r10_20261112.json`, `ground_truth/source_check_r10_20261112.json`; `lexicon/dialect_lexicon_20261109.json` (only to confirm a plain family uses none of its forms); and on `origin/main`: `data/urgency_tiers.draft.json`, `data/experiments/intake_design.v1.json` and `docs/experiment_interface/README.md` (section "Batch intake").

---

## 2. What the families are for

Each text is the start of a sentence that ends in a fixed carrier phrase, and the measurement is the model's next word. All comparisons are made **inside one family**. That decides how each text is written:

| Comparison | Texts | Rule |
|---|---|---|
| Register (the main one) | `medical` against `everyday` | Same reference facts. They differ in one continuous stretch of words. |
| Paraphrase controls | `medical` against `medical_paraphrase`; `everyday` against `everyday_paraphrase` | Same facts, same register, different wording. |
| Changed-fact control | `everyday` against `changed_fact` | Exactly one reference fact changes, so the right care changes. Nothing else. |
| Patient explanation (separate analysis) | `everyday` against `everyday_attribution` | One inserted clause stating a belief about the cause. No new fact. |
| Mixed wordings (separate analysis) | `medical` against `quad_b` and `quad_c` | Clinical terms in everyday sentence structure, and the reverse. |

Families at different care levels are never compared with each other, so you do not need to balance wording across levels.

---

## 3. Target and composition

Two batches of 24 families. Family ids run `r12-001` to `r12-048`, in batch order. Batch folders are `batch_01` and `batch_02`.

Each batch of 24:

| Families | Care level | Carrier phrase | Target words (with the leading space) |
|---|---|---|---|
| 8 | 4 emergency | "so I need to go to the" | " ER", " hospital" |
| 8 | 3 specialist | "so I should see a" | " specialist", " dentist", " dermatologist", " psychiatrist", " therapist" |
| 8 | 2 general doctor | "so I should see a" / "so I need to go to the" | " doctor" / " clinic" |

- Every family is a **plain register** family: it uses no form from the dialect lexicon. There are no dialect and no self-care families in this round.
- Before writing a family, check its target word's tier in `data/urgency_tiers.draft.json` on `origin/main` (under `tokens`, keyed in lower case without the leading space, so " ER" is `er`). It must equal the family's `right_care`. Read only the `tier` values in that file.

Every family has `medical`, `everyday`, `medical_paraphrase`, `everyday_paraphrase` and `changed_fact`. In addition, per batch:

- the 16 emergency and specialist families also have `everyday_attribution`;
- 6 families (2 per level) also have `quad_b` and `quad_c`.

**Coverage.** Across the run, spread families over body systems, adults, children (told by a parent), older adults, pregnancy and carers, and over speakers: plain low-literacy English and non-native English, written without dialect lexicon forms. Include presentations that are described differently on darker skin, and conditions that fall more heavily on people with less access to care, where you have sources. Do not invent a speaker group to fill a cell.

**No repeats.** No condition from rounds 9, 10 or 11, and no condition twice in round 12. No text of one family may appear in another. The used conditions are:

- Round 9: cardiogenic syncope; transient ischemic attack; preeclampsia; bronchiolitis; asthma exacerbation; tonic clonic seizure; pediatric diabetic ketoacidosis; food anaphylaxis; pulpitis; melanoma; panic disorder; early rheumatoid arthritis; cystitis; otitis media; gastroenteritis; reflux in pregnancy.
- Round 10: cauda equina; pharyngitis with drooling; skin infection with syncope; pediatric lower respiratory infection with cyanosis; upper gastrointestinal bleeding; febrile respiratory illness in pregnancy; fluid overload with orthopnea; shingles with confusion; gum disease with loose teeth; plaque eruption; persistent low mood; post-collision trauma symptoms; cataract; heavy menstrual bleeding; sinus infection; hypothyroid-type fatigue; pediatric purulent eye discharge; oral thrush from an inhaler; tick-bite rash; anaemia-type breathlessness; athlete's foot; diaper rash; winter dry skin; hay fever.
- Round 11: the `condition` of every family in `round11_20261114/batch_01/families.json` to `batch_06/families.json` (144 conditions).

Compare clinical pictures, not label strings. A round 12 family whose facts describe the same presentation as an earlier family, under a different label, is a repeat.

---

## 4. The case family

Use the round 11 schema exactly (`round11_20261114/batch_06/families.json` is the reference): `family_id`, `condition`, `right_care`, `level_rationale`, `carrier_frame`, `target_token`, `reference_facts`, `texts`, `changed_fact`, `attribution` (where present), `swap_spans`, `swap_note`, `everyday_sources`, `equity_dimension`, `lexicon_entries` (an empty list), `protocol_flags`, `design_note`.

### Writing rules for every text

- One sentence, at most 40 words, ending in the family's carrier phrase.
- No commas, semicolons or hyphens. Numbers as digits. No misspellings.
- First person, active voice, in every text including the medical ones: "I have had…", "My 4 year old daughter has had…", "I am 33 weeks pregnant and…".
- The diagnosis is never named in a text. `condition` is a label for reviewers only, and it must describe what the reference facts describe.
- `medical` and `everyday` are identical before and after one continuous stretch. The two stretches are within 2 words of each other in length. Record them in `swap_spans`.
- **Natural wording comes before alignment.** Never bend a patient's wording to make the stretches line up. If natural wording cannot meet the 2-word rule, drop the family and log why.
- Write a plain everyday stretch the way a patient would say it, even if it then needs a different construction from the medical stretch. Round 11's examples of what to avoid: "blocking the field of view" (not how most patients describe it); "with right foot arch tightness" (stacked nouns where a patient would say "my right arch feels tight").
- A medical term must have one reading. Round 11's "ciliary crusting" could be read as the ciliary body; "crusting of the eyelashes" could not.

### Contractions

No text uses an apostrophe contraction. This is the owner's decision of 2026-11-18, after the owner's read of round 11 excluded 7 of 24 sampled families for "I'm" ("I'm would be Im"), with the note "for the patient speak it should not have contractions".

- Write "Im" where a speaker would say "I'm", in every text of the family, the clinical ones included, because the opening is shared between the clinical and everyday wordings. "I am" is also allowed.
- Write the other contractions in full: "it is", "I have", "cannot", "they are", "do not". Keep the text within 40 words in its full form.
- Possessives ("my doctor's office", "the baby's skin") are not contractions and keep the apostrophe.

### Reference facts

Three to five facts, each one checkable statement. Every text of the family carries every fact, with the same timing, severity, side of the body, quantity and uncertainty. Nothing is added and nothing is dropped.

### The changed-fact control

The control changes one reference fact to another value of the same thing, so that the right care changes. It adds no word that carries new information. These rules came out of round 11, where 8 of the first 24 controls had to be rewritten.

**Rule A. The control stays inside the same case.**

- First choice: change a property of the same symptom: its onset, duration, frequency, severity, count, or a measured value. Round 11 examples: "3 brief fits each month" becomes "3 brief fits this hour"; eye pressure 28 becomes 15 mmHg; resting pulse 78 becomes 210; oximeter 95 becomes 79 percent; 18 months of trying for a baby becomes 2 months.
- A different symptom is allowed only at the same body site or in the same organ system, and only when every other fact still fits the changed text. Round 11 example: a dry cough two weeks after starting blood pressure medicine.
- Never replace the main symptom with one from another body system. Round 11 examples of what failed: one-sided hearing loss, then "slurring my words"; ferry queasiness, then "start wheezing".
- Read the whole control text aloud. If a clinician would ask "why did you mention the other facts?", the control has left the case.

**Rule D. Vary the control's new value.**

- No control's new value may repeat the wording of a new value already used in round 11 or earlier in round 12, apart from the plain words of the symptom itself. Round 11 overused "40 C fever", "painful swelling behind the ear" and "foot turning blue".
- Heavy bleeding became a default emergency control in round 11 (4 families in one batch). At most 1 emergency control per batch may move to level 4 through bleeding.
- Prefer measured-value and same-symptom changes, because those differ from family to family by their nature.

**Level of the control.**

- After the change, the remaining facts must leave no red flag at the control's level. If you cannot make the control's level clear, choose a different fact to change or a different case.

**Stated negatives.** Design the changeable fact as something a patient would say unprompted: a duration, an onset, a count, a measured number, a severity the medical text also states, or a property of the same symptom. A stated negative ("while speaking normally today") is allowed only where the speaker plausibly volunteers it and you have a source for that kind of statement. Mark those families `"stated_negative": true` in `design_note` with the reason. At most 3 per batch. Round 11 used none; keep it that way where you can.

---

## 5. What earlier reviews found: do not repeat these

Each class below is a gate in section 8.

1. **Facts drifting between wordings.** A paraphrase loses a fact, or carries a quality the fact list does not have. Check every text against the fact list, not only the main pair.
2. **Quantities that can be read two ways.** "2 pills" for two courses of medication. Write "2 different medicines", "for 3 nights", "twice a day".
3. **Controls that leave the case or repeat stock values.** Rules A and D, section 4.
4. **Controls whose level is arguable.** After the change, no red flag may remain.
5. **Source fit.** A sentence about a preterm infant on oxygen does not show how a parent of a 5 year old with a cough speaks. Prefer a source from the same population; label an adaptation (section 7).
6. **Added or lost intensity.** An everyday text must not be more or less severe than its medical text. No "bad", "awful", "pounding", "huge" unless the medical text states that quality.
7. **Idioms.** Use an idiom only where its documented meaning is the clinical fact.
8. **Explanation clauses.** The clause states what the speaker thinks the **cause** is ("and I think it is just indigestion"). It is not an expectation about the course ("and I think it will pass"), and it adds no symptom, duration, severity, history or action.
9. **Changing a family after it is pushed.** A pushed family's person and case never change. A correction keeps the id, changes only what is wrong, and is logged in `revisions.json` with the text before and after.
10. **Evidence sentences.** Copy each sentence exactly and separately. Never join quotes.
11. **Evidence that does not show the wording in use.** Rule B, section 7.

---

## 6. The team

One coordinator and nine named workers. Each worker owns its own files and writes nowhere else, so no two agents ever edit the same file. An agent never audits a family it wrote. Auditors read the family's draft file only, not the author's reasoning or the board discussion about it.

Run the coordinator and every auditor (`@sources`, `@facts`, `@language`, `@level`, `@adversary`) on Gemini 4 Carbon. If quota forces a choice, authors may run on a faster model; auditors may not. Where a second strong model is available, run `@adversary` on a different model from the authors.

| Agent | Owns (under `batch_NN/` unless stated) | Does |
|---|---|---|
| **Coordinator** | `plan.json`, `ledger.json`, `progress.md`, `final_report.md`, `revisions.json` at the round level; `self_check.md` and `concerns_selfreported.json` per batch | Writes the plan for all 48 slots before any family is written: level, condition, body system, population, speaker and target word, with the no-repeat check against rounds 9 to 11 done. Assigns work on the board, keeps the ledger, enforces the gates and stop rules. The only agent that commits and pushes. |
| `@author-l4` | `drafts/<family_id>.json` for the 8 emergency families | Writes each family as one file: facts first, then the texts, then the control, then the sources it used. |
| `@author-l3` | `drafts/<family_id>.json` for the 8 specialist families | Same. |
| `@author-l2` | `drafts/<family_id>.json` for the 8 general doctor families | Same. |
| `@sources` | `sources/<family_id>.json` | Opens every cited record. Confirms the title, finds each evidence sentence word for word, checks rule B, records what was opened, and records the source's population and speaker (section 7). |
| `@facts` | `audit/<family_id>.facts.json` | Without looking at `reference_facts`, lists the facts each text states. Then compares each list with `reference_facts` and with every other text of the family. |
| `@language` | `audit/<family_id>.language.json` | Reads each everyday text as a patient or carer would say it. Flags ambiguous quantities, stated negatives, added intensity, misused idioms, contractions (section 4), and wording no patient would use. |
| `@level` | `audit/<family_id>.level.json` | For the family and for its control: is the level clear, does the control leave any red flag, and does the control stay inside the case (rule A)? One sentence of reasoning. This is a model's reading, not a clinician's, and the file says so. |
| `@adversary` | `audit/<family_id>.adversarial.json` | Tries to find any reading under which `medical` and `everyday` describe different situations, under which the control changes more than one thing, or under which the control has left the case. Checks rule D against round 11 and earlier round 12 controls. |
| `@builder` | `tools/` at the round level; `families.json`, `sources.md`, `source_fit.json`, `check_pairs.json`, `check_report.json`, `intake_summary.json` per batch | Assembles the batch files from the per-family files with a script, never by hand, and runs gates G1 to G3 of section 8. Deterministic checks only. May copy round 11's `tools/` as a starting point. |

Each audit file ends with `"verdict": "pass"` or `"verdict": "return"` and, for a return, the gate and the exact text at fault. A family that is returned goes back to its author once, with the finding. If it fails the same gate again it is dropped and logged. No agent argues a finding away, and no auditor edits a family: only its author changes its draft file.

All agents read and write in the draft-branch checkout. If Antigravity gives a worker its own worktree, the worker still writes only the files it owns and tells the coordinator on the board when they are ready; the coordinator brings them into the draft-branch checkout.

---

## 7. Sourcing

For every everyday expression for a sign or symptom, and every explanation clause, `everyday_sources` (or `attribution`) holds these fields: `expression`, `source`, `title`, `pmid_or_doi`, `inspected_url`, `access` ("full text", "abstract only" or "title only": what you actually opened), `location`, `quote_type` ("direct patient quote", "authors' summary", "dictionary definition" or "none"), `evidence`, `adaptation`.

- If you cannot copy the sentence, the expression is `"source": "none"`. An unsourced expression is acceptable. A citation whose evidence sentence is not in the source is not.
- "Direct patient quote" only when the evidence sentence is the patient's or carer's own words in the source.
- For every PMID, open the PubMed record and confirm that its title matches before writing it down. Give the DOI where one exists. No other database identifiers.
- Dictionary sources: Merriam-Webster, Cambridge, the Dictionary of American Regional English and Wiktionary only. Give the entry URL and copy the sense you rely on. In the final report, name only the dictionaries actually cited.
- "Title only" access does not support an expression. Mark it none.

**Rule B. Evidence must show the wording in use.**

- The evidence sentence must show patients or carers using the expression in that sense, or the authors reporting that they do. For an explanation clause, it must show a patient or carer giving that explanation, or the authors reporting that patients give it.
- These do not support a row: a sentence that mentions the expression to say patients did not use it; a patient quote that rejects the explanation; a clinical statement that the cause exists or is common.
- When only such a sentence exists, the row is `"source": "none"`.

**Search before marking a row unsourced.** In round 11 the share of cited everyday expressions fell from 41% to 19% before recovering to 45%. Where a study of how patients describe a symptom exists (qualitative interview studies, symptom-description surveys, patient-reported outcome development papers), `@sources` and the author look for it before marking a row `none`. Prefer an expression a source supports over an equally plain one it does not. Do not stretch a source to fit. Report the cited share per batch; there is no target.

**Source fit.** `@sources` records one row per cited expression in the family's `sources/<family_id>.json`, and `@builder` collects the rows of a batch into `source_fit.json`:

```json
{"family_id": "r12-001", "expression": "…", "identifier": "PMID: …",
 "source_population": "adults admitted with …", "source_speaker": "patient | carer | clinician | authors",
 "family_population": "…", "fit": "same | adjacent | different",
 "note": "what was adapted and why, when fit is not 'same'"}
```

A `different` fit is allowed and must be labelled. Aim for `same` on at least half of the cited expressions in a batch, and report the share.

---

## 8. Gates: a family is in a batch only if all pass

| Gate | Check | Who |
|---|---|---|
| G1 structure | The batch's builder script validates every writing rule of section 4 (including no contraction and no dialect lexicon form) and rebuilds `families.json` from its inputs byte for byte. | `@builder` |
| G2 pair checker | 0 ERROR from the engine's checker (command below). Every warning explained in `self_check.md`. | `@builder` |
| G3 intake | 0 errors from the intake command (below), including duplicates against rounds 9 to 11 and the earlier round 12 batch. | `@builder` |
| G4 facts | The fact auditor's lists match `reference_facts` for every text. The control differs from `everyday` in exactly the declared fact. | `@facts` |
| G5 language | No unresolved finding from the patient-language auditor. Stated negatives within the limit and justified. | `@language` |
| G6 level | Family level and control level both judged clear. The control stays inside the case (rule A). | `@level` |
| G7 sources | Every cited sentence found word for word. Every title matches. Every row meets rule B. The family's `sources/` file is complete. | `@sources` |
| G8 adversarial | No reading found under which the registers differ in facts. The control changes one thing and repeats no earlier new value (rule D). | `@adversary` |

**Level concerns are recorded, not only blocked.** Whenever emergency care against a same-day doctor is a judgement call, for the family or for its control, `@level` records a concern of kind `level_disputed` or `control_level_disputed` with status `pending_clinical_review`, even when it passes G6. Round 11 recorded about 7 per batch at this standard.

Set up a `main` worktree once: `git fetch origin main`, then `git worktree add ../pw-main origin/main`. Refresh it before each batch with `git -C ../pw-main pull`.

G2, from the repository root, for batch `NN`:

```bash
python ../pw-main/scripts/check_candidate_pairs.py drafts/antigravity_scenarios_20261107/round12_20261117/batch_NN/check_pairs.json --forbid ",;-" --lexicon drafts/antigravity_scenarios_20261107/lexicon/dialect_lexicon_20261109.json --out drafts/antigravity_scenarios_20261107/round12_20261117/batch_NN/check_report.json
```

`check_pairs.json` is the round 11 candidates format, with the register, changed-fact and explanation pairs of every family.

G3, run from inside `../pw-main`, with `R` standing for the absolute path of `drafts/antigravity_scenarios_20261107` in your checkout. For batch 02 add `--prior-batch r12_b01=R/round12_20261117/batch_01/families.json`. Save the printed JSON as `intake_summary.json`:

```bash
python -m scripts.experiments.cli intake --batch R/round12_20261117/batch_NN/families.json --batch-id r12_bNN --prior-batch r9=R/round9_20261110/families.json --prior-batch r10=R/round10_20261112_rev1/families.json --prior-batch r11_b01=R/round11_20261114/batch_01/families.json --prior-batch r11_b02=R/round11_20261114/batch_02/families.json --prior-batch r11_b03=R/round11_20261114/batch_03/families.json --prior-batch r11_b04=R/round11_20261114/batch_04/families.json --prior-batch r11_b05=R/round11_20261114/batch_05/families.json --prior-batch r11_b06=R/round11_20261114/batch_06/families.json --lexicon R/lexicon/dialect_lexicon_20261109.json --no-write
```

It must print `"status": "intake"` with `software_validation.errors` equal to 0. A refusal (`"status": "refused"`) means an input is malformed: fix the input, do not work around the command.

---

## 9. Running for a long time

- **Set-up, before any family is written.** The coordinator creates the `main` worktree (section 8), writes `plan.json`, and has `@builder` write the tools. Then one family goes through every gate end to end as a rehearsal. Only when that family passes or is cleanly dropped does batch 01 start.
- **Permissions.** The run pauses whenever the host asks to approve a command. Before starting, approve these for the session where the host allows it: the Python interpreter used for G2 and G3 (round 11 used `.venv/bin/python`), reads in `../pw-main`, and `git add`, `git commit` and `git push` for the coordinator.
- **Ledger.** `ledger.json` holds one row per planned family: `family_id`, `batch`, `state` (`planned`, `drafted`, `in_audit`, `returned`, `passed`, `dropped`), the gates passed, the author, and for a dropped family the gate and the reason. The coordinator updates it after every state change, so a restart resumes from the ledger and never rewrites a passed family.
- **Order.** Finish and push batch 01 before starting batch 02. Within a batch, families are written and audited in parallel.
- **Staggered auditors.** Do not dispatch all five auditors on the same model at once. Round 11 hit capacity errors that way. Dispatch 2 or 3 at a time.
- **Commits.** When a batch passes all gates the coordinator makes one commit, message `Round 12 batch NN: <kept> families, <dropped> dropped`, and pushes. Never amend, never force-push.
- **Reviewer notes.** Before starting batch 02 the coordinator runs `git pull` and reads `round12_20261117/reviewer_notes.md` if it exists. It holds corrections from a review of batch 01, written by a Claude review session: a model's reading, not the owner's. The coordinator posts them on the board, they apply to batch 02, and `progress.md` records that. Do not wait for the file: if it is absent, continue.
- **This file.** Nobody in the team edits `SPEC.md`. If a rule seems wrong or impossible, keep following it, and say so in `final_report.md`.
- **Replacement.** When a family is dropped, the coordinator may assign one replacement from a short reserve list in `plan.json`. No more than 6 replacements per batch.

**Stop rules.** Stop the run, write `final_report.md` and push, when any of these happens:

1. A batch ends with fewer than 16 families passing all gates.
2. More than 6 families of a batch are dropped at the same gate. That means a rule is being misread, and the next batch would repeat it.
3. `@sources` finds a citation that does not exist or an evidence sentence that was not in the source, in a family that had already passed G7. Stop and audit the other batch's sources before anything else.
4. Any agent has opened a path listed under hard limit 2. Record which path and which agent, and stop.
5. Batch 02 is pushed.

Do not lower a gate to keep going.

---

## 10. Outputs

In `round12_20261117/`:

- `SPEC.md` (this file, read-only), and `reviewer_notes.md` if the reviewer adds one;
- `plan.json`, `ledger.json`, `progress.md` (one dated line per event), `final_report.md`;
- `tools/`: the builder and any helper scripts, runnable from the folder with no network;
- `revisions.json`: every correction to a pushed family, with the text before and after and the reason.

In each `batch_NN/`:

- `drafts/`, `sources/` and `audit/`: the per-family files, kept for dropped families too;
- `families.json`, `sources.md`, `source_fit.json`, `self_check.md`: assembled from the per-family files, holding only the families that passed every gate;
- `check_pairs.json`, `check_report.json`, `intake_summary.json`;
- `concerns_selfreported.json`: anything an auditor noticed that did not fail a gate but a clinician or patient-language reviewer should see. Use this exact shape so it can be read by the intake command:

```json
{"schema": "patientwords.intake-concerns/1", "batch_id": "r12_bNN", "concerns": [
  {"concern_id": "r12-001-c1", "family_id": "r12-001",
   "kind": "control_adds_fact | control_level_disputed | level_disputed | fact_parity | stated_negative | wording | label | source_fit | other",
   "applies_to": ["reg"], "text": "one or two plain sentences",
   "raised_by": "Antigravity <role>", "raised_by_kind": "model", "raised_on": "YYYY-MM-DD",
   "disposition": {"status": "pending_clinical_review | pending_patient_language_review | open", "note": ""}}]}
```

`applies_to` takes `reg`, `mpar`, `epar`, `chg`, `attr`, `qb`, `qc`, `family` or `label`.

**Concerns are withdrawn, never deleted.** When a revision makes a concern moot, keep the record and set its disposition to `{"status": "withdrawn", "by": <same as raised_by>, "by_kind": <same as raised_by_kind>, "date": "YYYY-MM-DD", "note": "<the revision that made it moot>"}`. Only the agent role that raised a concern may withdraw it. No agent writes any other closing status: only a person closes a concern.

`final_report.md` states, for the run and per batch: families planned, passed and dropped, by care level; drops by gate with reasons; the share of cited expressions, and of those the share with `same` source fit; the unsourced expressions; the stated negatives and their justifications; the level concerns recorded; every stop rule that triggered; and anything you were unsure about. Say what you verified and what you assumed. Describe reviewer notes as a model's review, not the owner's. End with a short section on where the run stalled or needed extra steps and what change to this specification would have prevented it. Do not describe the run as successful or the families as validated: they are drafts awaiting an owner's read, a clinician's review and a patient-language review.
