# Round 11 specification: outcome-blind case families at scale

This file is the complete specification for round 11 of the PatientWords authoring work on branch `draft/antigravity-scenarios-20261107`. Rounds 9 and 10 produced 40 case families. Round 11 adds as many as 144 more, in six batches of 24, written and checked by a team of agents that runs without waiting for anyone between batches.

**Every agent reads this whole file before doing anything, and again when it is unsure.** The coordinator does not summarise it for workers: each worker opens it.

Quality comes before count. A batch of 18 clean families is worth more than 24 with problems. Every rule here exists because an earlier round broke it.

---

## 1. Hard limits

These hold for every agent, for the whole run.

1. **Write only** under `drafts/antigravity_scenarios_20261107/round11_20261114/`. Never edit an earlier round's folder.
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

What you may read: this file, `round9_20261110/`, `round10_20261112_rev1/` (the style reference), `ground_truth/gt_r9_20261110.json`, `ground_truth/concerns_r9_20261112.json`, `ground_truth/concerns_r10_20261112.json`, `ground_truth/source_check_r10_20261112.json`, `lexicon/dialect_lexicon_20261109.json`, and on `origin/main`: `data/urgency_tiers.draft.json`, `data/experiments/intake_design.v1.json` and `docs/experiment_interface/README.md` (section "Batch intake").

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

Up to **six batches of 24 families**. Family ids run `r11-001` to `r11-144`, in batch order. Batch folders are `batch_01` to `batch_06`.

Each batch of 24:

| Group | Families | Care level | Carrier phrase | Target words (with the leading space) |
|---|---|---|---|---|
| Plain register | 6 | 4 emergency | "so I need to go to the" | " ER", " hospital" |
| Plain register | 6 | 3 specialist | "so I should see a" | " specialist", " dentist", " dermatologist", " psychiatrist", " therapist" |
| Plain register | 6 | 2 general doctor | "so I should see a" / "so I need to go to the" | " doctor" / " clinic" |
| Dialect | 4 | spread over levels 4, 3 and 2 | as for the level | as for the level |
| Self-care | 2 | 1 | "so I just need some" | " cream", " ointment", " lotion", " medicine" |

- **Plain register** families use no form from the dialect lexicon. They are the families the main experiment needs, so they get the most care.
- **Dialect** families use at least one form from the `core` list of `lexicon/dialect_lexicon_20261109.json`, only where a source supports that form for that kind of speaker. The `everyday_paraphrase` keeps the same form. List every form in `lexicon_entries`.
- Before writing a family, check its target word's tier in `data/urgency_tiers.draft.json` on `origin/main` (under `tokens`, keyed in lower case without the leading space, so " ER" is `er`). It must equal the family's `right_care`. Read only the `tier` values in that file.

Every family has `medical`, `everyday`, `medical_paraphrase`, `everyday_paraphrase` and `changed_fact`. In addition, per batch:

- the 12 plain emergency and specialist families also have `everyday_attribution`;
- 6 plain families (2 per level) also have `quad_b` and `quad_c`.

**Coverage.** Across the run, spread families over body systems, adults, children (told by a parent), older adults, pregnancy and carers, and over speakers: plain low-literacy English, non-native English and regional forms where sources support them. Include presentations that are described differently on darker skin, and conditions that fall more heavily on people with less access to care, where you have sources. Do not invent a speaker group to fill a cell.

**No repeats.** No condition from round 9 or round 10, and no condition twice in round 11. No text of one family may appear in another. Conditions already used:

- Round 9: cardiogenic syncope; transient ischemic attack; preeclampsia; bronchiolitis; asthma exacerbation; tonic clonic seizure; pediatric diabetic ketoacidosis; food anaphylaxis; pulpitis; melanoma; panic disorder; early rheumatoid arthritis; cystitis; otitis media; gastroenteritis; reflux in pregnancy.
- Round 10: cauda equina; pharyngitis with drooling; skin infection with syncope; pediatric lower respiratory infection with cyanosis; upper gastrointestinal bleeding; febrile respiratory illness in pregnancy; fluid overload with orthopnea; shingles with confusion; gum disease with loose teeth; plaque eruption; persistent low mood; post-collision trauma symptoms; cataract; heavy menstrual bleeding; sinus infection; hypothyroid-type fatigue; pediatric purulent eye discharge; oral thrush from an inhaler; tick-bite rash; anaemia-type breathlessness; athlete's foot; diaper rash; winter dry skin; hay fever.

---

## 4. The case family

Use the round 10 schema exactly (`round10_20261112_rev1/families.json` is the reference): `family_id`, `condition`, `right_care`, `level_rationale`, `carrier_frame`, `target_token`, `reference_facts`, `texts`, `changed_fact`, `attribution` (where present), `swap_spans`, `swap_note`, `everyday_sources`, `equity_dimension`, `lexicon_entries`, `protocol_flags`, `design_note`.

### Writing rules for every text

- One sentence, at most 40 words, ending in the family's carrier phrase.
- No commas, semicolons or hyphens. Numbers as digits. No misspellings.
- First person, active voice, in every text including the medical ones: "I have had…", "My 4 year old daughter has had…", "I am 33 weeks pregnant and…".
- The diagnosis is never named in a text. `condition` is a label for reviewers only, and it must describe what the reference facts describe.
- `medical` and `everyday` are identical before and after one continuous stretch. The two stretches are within 2 words of each other in length. Record them in `swap_spans`.
- **Natural wording comes before alignment.** Never bend a patient's wording to make the stretches line up. If natural wording cannot meet the 2-word rule, drop the family and log why.
- The everyday register of round 10 revision 1 is the standard. The owner read all 24 and kept them. Match that plainness.

### Reference facts

Three to five facts, each one checkable statement. Every text of the family carries every fact, with the same timing, severity, side of the body, quantity and uncertainty. Nothing is added and nothing is dropped.

---

## 5. What the review of round 10 found: do not repeat these

Round 10 was structurally clean and every citation existed. The review still raised 34 concerns. Each class below is now a gate in section 8.

1. **Facts drifting between wordings.** One paraphrase lost a fact the others carried ("stops me driving"). Two paraphrases carried a quality ("brittle") that the fact list did not have. Check every text against the fact list, not only the main pair.
2. **Quantities that can be read two ways.** "2 pills" was written for two courses of medication. Write a quantity so it has one reading: "2 different medicines", "for 3 nights", "twice a day".
3. **Stated negatives.** In 15 of 24 families the fact that the control changes was an absence the patient would rarely volunteer ("while speaking normally today", "with easy resting breathing"). **Design the changeable fact as something a patient would say unprompted**: a duration, an onset, a count, a measured number, a severity the medical text also states, or one present symptom against a different present symptom. A stated negative is allowed only where the speaker plausibly volunteers it (a parent saying "she is still drinking well") and you have a source for that kind of statement. Mark those families `"stated_negative": true` in `design_note` with the reason. At most 3 per batch.
4. **Controls whose level is arguable.** Three controls were labelled "general doctor" while still describing something urgent (39 C fever in late pregnancy; spreading hot leg swelling at 68). After the change, the remaining facts must leave no red flag. If you cannot make the control's level clear, choose a different fact to change or a different case.
5. **Controls that jump too far or add detail.** One control went from self-care to emergency in one step. One added a body location the fact did not name. A control changes one fact to another value of the same thing and adds no word that carries new information. A self-care family's control goes to level 2 or 3, not 4.
6. **Source fit.** Several expressions were supported by a real sentence from a different population: a preterm infant on oxygen for a 5 year old with a cough, older adults with heart failure for a pregnant woman. A sentence in a paper does not show that patients in your family's population say it. Prefer a source from the same population. When you adapt from another, say so (section 7).
7. **Added or lost intensity.** An everyday text must not be more or less severe than its medical text. No "bad", "awful", "pounding", "huge" unless the medical text states that quality.
8. **Idioms.** Use an idiom only where its documented meaning is the clinical fact.
9. **Explanation clauses.** The clause states what the speaker thinks the **cause** is ("and I think it is just indigestion"). It is not an expectation about the course ("and I think it will pass"), and it adds no symptom, duration, severity, history or action.
10. **Dialect in paraphrases.** In a dialect family the second everyday wording keeps the family's dialect form.
11. **Changing a family after it is pushed.** One family was rewritten into a different person and case under the same id. A pushed family's person and case never change. A correction keeps the id, changes only what is wrong, and is logged in `revisions.json` with the text before and after.
12. **Evidence sentences.** One evidence field joined three quotes into one. Copy each sentence exactly and separately.

---

## 6. The team

One coordinator and ten named workers. Each worker owns its own files and writes nowhere else, so no two agents ever edit the same file. An agent never audits a family it wrote. Auditors read the family's draft file only, not the author's reasoning or the board discussion about it.

Run the coordinator and every auditor (`@sources`, `@facts`, `@language`, `@level`, `@adversary`) on Gemini 4 Carbon. If quota forces a choice, authors may run on a faster model; auditors may not. Where a second strong model is available, run `@adversary` on a different model from the authors.

| Agent | Owns (under `batch_NN/` unless stated) | Does |
|---|---|---|
| **Coordinator** | `plan.json`, `ledger.json`, `progress.md`, `final_report.md`, `revisions.json` at the round level; `self_check.md` and `concerns_selfreported.json` per batch | Writes the plan for all 144 slots before any family is written: group, level, condition, body system, population, speaker and target word, with the no-repeat check done. Assigns work on the board, keeps the ledger, enforces the gates and stop rules. The only agent that commits and pushes. |
| `@author-l4` | `drafts/<family_id>.json` for the 6 plain emergency families | Writes each family as one file: facts first, then the texts, then the control, then the sources it used. |
| `@author-l3` | `drafts/<family_id>.json` for the 6 plain specialist families | Same. |
| `@author-l2` | `drafts/<family_id>.json` for the 6 plain general doctor families | Same. |
| `@author-flag` | `drafts/<family_id>.json` for the 4 dialect and 2 self-care families | Same, with the dialect lexicon open. |
| `@sources` | `sources/<family_id>.json` | Opens every cited record. Confirms the title, finds each evidence sentence word for word, records what was opened, and records the source's population and speaker (section 7). |
| `@facts` | `audit/<family_id>.facts.json` | Without looking at `reference_facts`, lists the facts each text states. Then compares each list with `reference_facts` and with every other text of the family. |
| `@language` | `audit/<family_id>.language.json` | Reads each everyday text as a patient or carer would say it. Flags ambiguous quantities, stated negatives, added intensity, misused idioms, and wording no patient would use. |
| `@level` | `audit/<family_id>.level.json` | For the family and for its control: is the level clear, and does the control leave any red flag? One sentence of reasoning. This is a model's reading, not a clinician's, and the file says so. |
| `@adversary` | `audit/<family_id>.adversarial.json` | Tries to find any reading under which `medical` and `everyday` describe different situations, or under which the control changes more than one thing. |
| `@builder` | `tools/` at the round level; `families.json`, `sources.md`, `source_fit.json`, `check_pairs.json`, `check_report.json`, `intake_summary.json` per batch | Assembles the batch files from the per-family files with a script, never by hand, and runs gates G1 to G3 of section 8. Deterministic checks only. |

Each audit file ends with `"verdict": "pass"` or `"verdict": "return"` and, for a return, the gate and the exact text at fault. A family that is returned goes back to its author once, with the finding. If it fails the same gate again it is dropped and logged. No agent argues a finding away, and no auditor edits a family: only its author changes its draft file.

All agents read and write in the draft-branch checkout. If Antigravity gives a worker its own worktree, the worker still writes only the files it owns and tells the coordinator on the board when they are ready; the coordinator brings them into the draft-branch checkout.

---

## 7. Sourcing

For every everyday expression for a sign or symptom, and every explanation clause, `everyday_sources` (or `attribution`) holds the round 10 fields: `expression`, `source`, `title`, `pmid_or_doi`, `inspected_url`, `access` ("full text", "abstract only" or "title only": what you actually opened), `location`, `quote_type` ("direct patient quote", "authors' summary", "dictionary definition" or "none"), `evidence`, `adaptation`.

- If you cannot copy the sentence, the expression is `"source": "none"`. An unsourced expression is acceptable. A citation whose evidence sentence is not in the source is not.
- "Direct patient quote" only when the evidence sentence is the patient's or carer's own words in the source.
- For every PMID, open the PubMed record and confirm that its title matches before writing it down. Give the DOI where one exists. No other database identifiers.
- Dictionary sources: Merriam-Webster, Cambridge, the Dictionary of American Regional English and Wiktionary only. Give the entry URL and copy the sense you rely on.
- "Title only" access does not support an expression. Mark it none.

**Source fit.** `@sources` records one row per cited expression in the family's `sources/<family_id>.json`, and `@builder` collects the rows of a batch into `source_fit.json`:

```json
{"family_id": "r11-001", "expression": "…", "identifier": "PMID: …",
 "source_population": "adults admitted with …", "source_speaker": "patient | carer | clinician | authors",
 "family_population": "…", "fit": "same | adjacent | different",
 "note": "what was adapted and why, when fit is not 'same'"}
```

A `different` fit is allowed and must be labelled. Aim for `same` on at least half of the cited expressions in a batch, and report the share.

---

## 8. Gates: a family is in a batch only if all pass

| Gate | Check | Who |
|---|---|---|
| G1 structure | The batch's builder script validates every writing rule of section 4 and rebuilds `families.json` from its inputs byte for byte. | `@builder` |
| G2 pair checker | 0 ERROR from the engine's checker (command below). Every warning explained in `self_check.md`. | `@builder` |
| G3 intake | 0 errors from the intake command (below), including duplicates against rounds 9 and 10 and earlier round 11 batches. | `@builder` |
| G4 facts | The fact auditor's lists match `reference_facts` for every text. The control differs from `everyday` in exactly the declared fact. | `@facts` |
| G5 language | No unresolved finding from the patient-language auditor. Stated negatives within the limit and justified. | `@language` |
| G6 level | Family level and control level both judged clear. | `@level` |
| G7 sources | Every cited sentence found word for word. Every title matches. The family's `sources/` file is complete. | `@sources` |
| G8 adversarial | No reading found under which the registers differ in facts. | `@adversary` |

Set up a `main` worktree once: `git fetch origin main`, then `git worktree add ../pw-main origin/main`. Refresh it before each batch with `git -C ../pw-main pull`.

G2, from the repository root, for batch `NN`:

```bash
python ../pw-main/scripts/check_candidate_pairs.py drafts/antigravity_scenarios_20261107/round11_20261114/batch_NN/check_pairs.json --forbid ",;-" --lexicon drafts/antigravity_scenarios_20261107/lexicon/dialect_lexicon_20261109.json --out drafts/antigravity_scenarios_20261107/round11_20261114/batch_NN/check_report.json
```

`check_pairs.json` is the round 10 candidates format, with the register, changed-fact and explanation pairs of every family.

G3, run from inside `../pw-main`, with `R` standing for the absolute path of `drafts/antigravity_scenarios_20261107` in your checkout. Add one `--prior-batch` for each earlier round 11 batch. Save the printed JSON as `intake_summary.json`:

```bash
python -m scripts.experiments.cli intake --batch R/round11_20261114/batch_NN/families.json --batch-id r11_bNN --prior-batch r9=R/round9_20261110/families.json --prior-batch r10=R/round10_20261112_rev1/families.json --lexicon R/lexicon/dialect_lexicon_20261109.json --no-write
```

It must print `"status": "intake"` with `software_validation.errors` equal to 0. A refusal (`"status": "refused"`) means an input is malformed: fix the input, do not work around the command.

---

## 9. Running for a long time

- **Set-up, before any family is written.** The coordinator creates the `main` worktree (section 8), writes `plan.json`, and has `@builder` write the tools. Then one family goes through every gate end to end as a rehearsal. Only when that family passes or is cleanly dropped does batch 01 start.
- **Ledger.** `ledger.json` holds one row per planned family: `family_id`, `batch`, `state` (`planned`, `drafted`, `in_audit`, `returned`, `passed`, `dropped`), the gates passed, the author, and for a dropped family the gate and the reason. The coordinator updates it after every state change, so a restart resumes from the ledger and never rewrites a passed family.
- **Order.** Finish and push one batch before starting the next. Within a batch, families are written and audited in parallel.
- **Commits.** When a batch passes all gates the coordinator makes one commit, message `Round 11 batch NN: <kept> families, <dropped> dropped`, and pushes. Never amend, never force-push.
- **Reviewer notes.** Before starting each batch the coordinator runs `git pull` and reads `round11_20261114/reviewer_notes.md` if it exists. It holds corrections from the reviewer of earlier batches. The coordinator posts them on the board, they apply to all later batches, and `progress.md` records that. Do not wait for the file: if it is absent, continue.
- **This file.** Nobody in the team edits `SPEC.md`. If a rule seems wrong or impossible, keep following it, and say so in `final_report.md`.
- **Replacement.** When a family is dropped, the coordinator may assign one replacement from a short reserve list in `plan.json`. No more than 6 replacements per batch.
- **Usage.** After batch 01 is pushed, the coordinator writes the batch's elapsed time and the agents used into `progress.md`, so the person running this can check usage before the remaining five batches spend it.

**Stop rules.** Stop the run, write `final_report.md` and push, when any of these happens:

1. A batch ends with fewer than 16 families passing all gates.
2. More than 6 families of a batch are dropped at the same gate. That means a rule is being misread, and more batches would repeat it.
3. `@sources` finds a citation that does not exist or an evidence sentence that was not in the source, in a family that had already passed G7. Stop and audit every earlier batch's sources before anything else.
4. Any agent has opened a path listed under hard limit 2. Record which path and which agent, and stop.
5. Batch 06 is pushed.

Do not lower a gate to keep going.

---

## 10. Outputs

In `round11_20261114/`:

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
{"schema": "patientwords.intake-concerns/1", "batch_id": "r11_bNN", "concerns": [
  {"concern_id": "r11-001-c1", "family_id": "r11-001",
   "kind": "control_adds_fact | control_level_disputed | level_disputed | fact_parity | stated_negative | wording | label | source_fit | other",
   "applies_to": ["reg"], "text": "one or two plain sentences",
   "raised_by": "Antigravity <role>", "raised_by_kind": "model", "raised_on": "2026-11-14",
   "disposition": {"status": "pending_clinical_review | pending_patient_language_review | open", "note": ""}}]}
```

`applies_to` takes `reg`, `mpar`, `epar`, `chg`, `attr`, `qb`, `qc`, `family` or `label`. Never write a closing status: only a person closes a concern.

`final_report.md` states, for the run and per batch: families planned, passed and dropped, by group and care level; drops by gate with reasons; the share of cited expressions with `same` source fit; the unsourced expressions; the stated negatives and their justifications; every stop rule that triggered; and anything you were unsure about. Say what you verified and what you assumed. End it with a short section on where the run stalled or needed extra steps and what change to this specification would have prevented it. Do not describe the run as successful or the families as validated: they are drafts awaiting an owner's read, a clinician's review and a patient-language review.
