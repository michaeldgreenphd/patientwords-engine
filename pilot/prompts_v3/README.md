# Pilot run kit, version 3

The inputs for the third run of the stimulus-generation pilot: `generation_prompt.txt`, `checker_prompt.txt` and
`design.json`. They were revised from the owner's blind review of run 2, `pilot_v2_20261002` (recorded at
`../runs/pilot_v2_20261002/`): 40 sampled pairs, every one answered on 2026-10-04 (UTC) before the checker's answer
was shown, 9 with notes. Nothing has been run with this kit.

The kit runs under harness version 2, on the same pilot scripts as run 2. It does not replace `../prompts_v2/` (run
2's kit) or `../prompts/` and `../design.json` (run 1's). The harness, the run procedure and the version-2 safeguards
are as `../prompts_v2/README.md` describes them; this file covers only what version 3 changes.

## What changed from version 2

The generation prompt's rule text changed, and one example in `design.json`:

- `checker_prompt.txt` is version 2's, byte for byte (see *The checker's role* below).
- `design.json` is version 2's except its `_note` and one example. Rule 5's patient-phrase examples
  (`prompt_examples.patient_phrases`) keep only version 2's first, "the left side of my heart"; version 2's second,
  "my heart", left out a side that rule 8 now requires (see *Rule 8*). The cells, the example negative control, the
  other prompt examples, `probe_endings` and the variant design (12 concepts, 4 of them with a second patient
  phrasing) are unchanged.
- `generation_prompt.txt` has ten rules instead of seven. Each change below names the review row whose note
  motivated it. Row ids are run 2's review ids (`../runs/pilot_v2_20261002/review_map.json` maps them to rows); run 1's
  review used the same ids for different pairs.

The new rules are written as rule text, without example words. Version 2 moved every example word out of the
template into `design.json`'s `prompt_examples` (Codex review of PR #69), and the harness renders only the markers
`pilot/scripts/common.py` lists (`generation_markers`), refusing any other. A new example, or a rendered setting such
as the brand-name cap, would need a new marker, which is a change to a pilot script. A change to any pilot script
alters the script hashes both recorded runs seal, so both would have to be recomputed and re-finalized. This kit
avoids that. Editing the value of an existing example is different: it renders through the marker the example
already has, so it is a data change. The dropped rule 5 example is one.

### Rule 6 (new): at most one brand-name concept per call (provisional number)

At most one of a call's concepts may pair a drug's generic name with one of its brand names. The call's other
medicine concepts change register in any way the other rules allow. The brand-name sentences of version 2's rule 5
(single-ingredient drugs only, never a combination product's brand) moved into this rule unchanged.

- **Notes.** r001: a generic-for-brand swap "is okay but also not quite the same as using slang instead of the drug
  name". r033: generic against brand "is interesting but would not build all stimuli on these examples".
- **Owner approval, no number.** After the review, on 2026-10-04 in chat, the owner approved capping brand-for-generic
  pairs as a step for run 3 and set no number. One per call is this kit's provisional default. The number is the
  owner's to set before run 3 (see *Decisions left to the owner*).
- **No list of alternatives.** The rule does not say what the call's other medicine concepts use instead; rules 5 and
  7 govern them as they govern every row. An earlier draft limited them to common slang or a broader everyday name
  for the kind of medicine. The notes do not ask for that, so it was dropped (Codex review of PR #80).
- **Run 2.** 50 of the 288 generated rows were brand pairs (checker relation `same_brand`), all in medication cells:
  50 of the 96 medication rows. Each of the 6 medication calls had 7 to 10 brand concepts out of 12. In the review
  sample, 6 of the 10 medication rows were brand pairs, and the owner kept 5 of them. The other 4 medication rows were
  all kept, too few to predict how the cap will move the medication keep rate.
- **Why the number is in the template, not in `design.json`.** The cap is written into rule 6's text as "at most
  one". The version-2 harness puts a `design.json` value into the prompt only through a marker `common.py` lists, and
  `prompt_examples` must hold exactly the fields `common.py` names. A cap stored in `design.json` would therefore not
  reach the prompt without a new marker, which is a script change (see above). Setting another number is an edit to
  rule 6's text and to its pinned line in `tests/fixtures/pilot_v3_changed_lines.json`.
- **Effect.** A run has 6 medication calls (3 specialties, 2 arms), so it can hold at most 6 brand concepts there.
  Whether the generator obeyed can be read from `checked.jsonl` (relation `same_brand`, per call); the summary's
  relation counts give the totals per arm.

### Rule 3 (changed): first person only

Both sentences are the patient speaking or writing about themselves, in the first person. The speaker is never a
relative, a clinician or a narrator, and talks about their own body, symptoms and medicines as their own ("my" where
a patient would say it). Version 2 also allowed "a relative speaking about the patient".

- **Note.** r013: the template said "The doctor said the ___ is inflamed". The note asked to "make it personal" with
  "my", and said "Important that these are kinda things that are said in first person because we are simulating
  something a patient would say".
- **Not taken from the note.** Its last sentence, "Patient would also probably say \"sac\"", is about that pair's
  patient phrase, which already contains the word. No rule was added for it: rule 5 already asks for the words
  patients actually use, and one note does not show a general preference for shorter phrases.
- **Run 2.** 42 of the 288 generated rows were about another person's condition or medicine, usually the
  speaker's parent, partner or child: 21 in each arm, and by swap type 8 body part, 18 medication and
  16 symptom description. 20 of the 42 have no first-person singular word. The other 22 are in the first person but
  about someone else (for example `A__gastroenterology__symptom_description__L11` and
  `B__neurology__medication__L05`). The count comes from reading all 288 templates in `checked.jsonl`. In the review
  sample, 5 of the 40 rows were about someone else, and the owner kept 3 of them.
- **Related changes.**
  - "What one row is" now calls the template "one sentence that the patient says or writes about themselves".
  - The negative-control instruction now says controls follow rules 3 and 10. The example negative control in
    `design.json` was already in the first person.
  - The exemplar header now says the seed rows "were written before these rules, some are not in the first person".
    Several of run 2's seeds are in the third person.

### Rule 5 (changed): common slang only

The patient phrase may use "common slang", and only slang that most adult patients would recognise; regional, dated
or rare slang is out. The second phrasing of a variant pair is now "a vaguer or slangier one (slang only as rule 5
allows)".

- **Note.** r025: the patient phrase was slang for the heart, standing in for one of its chambers, and the note said
  "ticker is not something i am familiar with". It suggested the left side of the heart instead, which is now rule
  5's only patient-phrase example (see *Rule 8*).
- **Limit.** The prompt names no speaker group (no country or dialect), so "most adult patients" is not narrowed
  further. See *Decisions left to the owner*.

### Rule 8 (new): keep the side, the place and the number

When the clinical phrase says which side, which limb or place, or how many (one or both), the patient phrase says it
too, in everyday words. The patient phrase may be vaguer about what the thing is (rule 7), but never about where it is
or how many. When a patient would naturally say which side or which one, it goes in both phrases, so that neither
phrase is more specific than the other.

- **Note.** r005: "would someone be more specific and say something about being one eyelid or the other?"
- **Why the side goes in both phrases.** That row's clinical term named no side. A patient phrase that named one would
  have been narrower than the clinical term, which codebook rule L4 counts as not equivalent.
- **Rule 5's example.** Version 2's rule 5 set two patient phrases against the leaflet wording "main pumping chamber",
  which describes the left ventricle: "the left side of my heart" and "my heart". The second drops the side, which
  this rule forbids, and run 2 paired the left ventricle with the bare word "heart" twice
  (`A__cardiology__body_part__L01`, `B__cardiology__body_part__L08`). Version 3's `design.json` keeps only the first.

### Rule 9 (new): no grid names for a region

Neither phrase may name a region by its sector of an imaginary grid laid over part of the body ("such as one quarter
of it"). The patient phrase names the part a patient would name, and the clinical phrase uses the standard anatomical
term for that part. When a place's only clinical name is its grid name, the generator picks a different body part.

- **Notes.** r011: "quadrant of what for clinical? kinda vague". r015: "again quadrant feels weird to say". Both
  clinical terms named a quadrant of the abdomen.
- **Run 2.** 7 of the 288 generated rows named a quadrant. Body-part rows were the weakest family in the review: 8 of
  15 kept, against 9 of 10 for medication and 10 of 15 for symptom descriptions.
- **Wording.** The rule does not use the word "quadrant", because the template holds no example words (see above).

### Rule 4 (changed): the clinical phrase as a clinician says it

Two sentences were added:

- Where a standard term exists, use it rather than a description.
- Write the clinical phrase as a clinician would say it out loud, in its usual word order, not in the shorthand of a
  clinical note and not as a stiff phrase built to fit the blank. The sentence around it stays the patient's own
  words.

The rule already asked for the preferred term in SNOMED CT or MeSH, or a drug's generic name (codebook R3 and L1), as
a patient would repeat it after hearing it from their clinician, and as specific as a clinician would be.

- **Notes.** r006: "The clinical one feels a little robotic but I would keep". r017: "I dont know medical lexicon but
  if this is that maybe you can use it?"
- **Reading of r006.** This is the kit's reading, not the owner's. The note says the clinical side "feels a little
  robotic", which the kit reads as a term in the form a chart uses, set into a spoken sentence. So the rule asks for
  the term as a clinician says it. That is also what the rule's first sentence (the term as a patient repeats it)
  and rule 3's ban on clinical-note prose imply. Asking instead for the form a clinician writes in a note, with the
  details a note adds, could make the clinical phrase stiffer, the opposite of what the note asks for. Detail is
  still required: the rule ends "be as specific as a clinician would be", and rule 8 keeps the side. See *Decisions
  left to the owner*.
- **Scope.** The rule governs the clinical phrase only. The template is one sentence shared by both phrases, and it
  is the patient speaking (rule 3).

### Renumbering

Version 2's rules 1 to 5 keep their numbers. Its rule 6 (same thing or broader) is now rule 7, and its rule 7 (the
probe point) is now rule 10. `design.json`'s `prompt_examples` illustrate rules 3, 4, 5, 7 and 10. The comments in
`common.py`'s `V2_PROMPT_EXAMPLES` give version 2's numbers (3, 4, 5, 6 and 7). They were left as they are, because
editing `common.py` is a script change.

## The checker's role (owner decision of 2026-10-04)

**Decision.** Physicians decide which stimuli are kept, in the verification app (a private app outside this
repository); the checker does not. This is recorded as decision D1 in codebook v0.3 (`../codebook/codebook_v0.3.md`).

**Evidence from the run 2 review.** The numbers come from `pilot/analysis/review_agreement.py` (seed 20261002, 2000
resamples) and the run's summary. The review and the script's output are committed in `../codebook/`
(`review_export_pilot_v2_20261002.json` and `agreement_pilot_v2_20261002.json`), and `tests/test_pilot_codebook_d1.py`
checks every number D1 quotes against them and against the run's `review_key.csv` and `summary.json`.

- **Naturalness and realism.** On all 40 sampled rows the checker answered `both` to `sentence_natural` and `real` to
  `patient_realism`, so it could not tell the pairs the owner found natural or real from the rest:
  - agreement on naturalness was 25/40, kappa 0.00;
  - agreement on realism was 24/39, kappa 0.00.

  Across the whole run it answered `both` on all 288 generated rows and `real` on 287.
- **The keep rule.** The checker-side keep rule R8 (keep when `sentence_natural` is `both`) kept all 40 rows. That
  covered the 27 the owner kept, and it caught none of the 13 the owner would edit or drop: specificity 0/13.
- **Same meaning.** The checker's same-meaning answers agreed with the owner's at chance level: 24/40, kappa 0.05.
  The run's summary (estimand 4) shows it rejects nearly every broken pair but also many good ones:
  - it answered not equivalent on 19 of the run's 20 deliberately broken pairs;
  - on the 10 seed rows the run's protocol treats as known-good, it answered equivalent on only 5 (not equivalent on
    4, unclear on 1).

  So a not-equivalent answer marks a pair for a closer look; it does not show that the pair is broken.

**What stays.** The checker remains a same-meaning screen whose answers are computed and reported.

- No pilot script keeps or drops a row on its answers. The review draw ignores them, and the summary reports them.
- The one place a checker answer still selects rows is `pilot/analysis/trace_pairs.py`. By default it traces only
  the generated rows the checker judged equivalent; `--review-sample` ignores the checker.
- Format errors in a generated row are caught by the harness's parser, not by the checker.

**Why the checker prompt is unchanged.** It is version 2's, byte for byte, for two reasons:

- Run 3's checker answers can then be compared with run 2's.
- The version-2 harness requires the `sentence_natural` and `patient_realism` answers: its output schema demands
  them, and `common.checker_enum_problems` refuses a checker prompt that does not offer every value. Removing them
  would be a script change.

**R8 in run 2.** The codebook's R8 was inferred from run 1: every pair the owner kept there had both sentences
reading naturally. It did not hold exactly in run 2. The owner kept 27 rows, and for 2 of them only the clinical
sentence read naturally.

## What did not change

- **Pilot scripts.** No pilot script changed (`pilot/scripts/`, `pilot/analysis/trace_pairs.py`,
  `pilot/analysis/review_agreement.py`), so no recorded run's script hashes changed.
- **Harness version.** It is 2: rows, checker answers, the summary's descriptives and the review draw work as in run
  2.
- **Recorded runs.** No file of a recorded run changed (`pilot/` and `pilot/runs/pilot_v2_20261002/`).
- **Codebook.** Version 0.2's files (`../codebook/codebook_v0.2.json` and `.md`) are unchanged. The rules file
  `../codebook/codebook_rules.json` is now version 0.3, so `make_codebook.py` rebuilds v0.3. The rules file v0.2 was
  built from is the one whose SHA-256 `codebook_v0.2.json` records, and it is in the git history.
- **Codebook stimulus rules.** The six run 2 rules above are in this kit only, not yet in the codebook. The codebook
  is built from run 1's review export, and its examples cite review ids in that export. Run 2's notes cite the same
  ids for different pairs, so adding these rules with their examples needs `make_codebook.py` to read a second
  export.

## How a run uses it

As for version 2 (`../prompts_v2/README.md`, *How a run uses it*): make a fresh run directory and set `PILOT_DIR` to
it for every script call. Before planning, copy:

- `generation_prompt.txt` and `checker_prompt.txt` into `<run>/prompts/`;
- `design.json` into `<run>/design.json`.

Then add the seed file, `manifest_model.json`, the run's own `PROTOCOL.md` and `HANDOFF.md`, and run the same chain.

The run's protocol should state:

- the six rule changes and the dropped rule 5 example;
- that the checker is not a gate;
- version 2's estimand 2 and estimand 3 caveats, which still apply because the variant design is unchanged.

## What to compare against runs 1 and 2

The owner's blind answers on each run's 40-row sample, with 95% Wilson intervals:

| Measure | Run 1 (`pilot_real_20260930`) | Run 2 (`pilot_v2_20261002`) |
|---|---|---|
| Kept as is | 18/40, 45% (31-60%) | 27/40, 68% (52-80%) |
| Dropped | 9/40 | 2/40 |
| Both sentences read naturally | 21/40, 52% (38-67%) | 25/40, 62% (47-76%) |
| Patient phrase sounds real | 19/40, 48% (33-62%) | 24/39, 62% (46-75%) |
| Patient phrase unlikely | 6/40 | 0/39 |
| The two phrases name the same thing | 27/40 (no 2, can't tell 11) | 24/40 (no 6, can't tell 10) |

Run 2 by swap type: medication 10 rows (kept 9, real 5, natural 7), body part 15 (kept 8, real 9, natural 8), symptom
description 15 (kept 10, real 10, natural 10). Rules 8 and 9 are aimed at body-part rows, and rule 6 at medication
rows, so these per-family numbers are the baseline to watch. With 10 to 15 rows per family, though, only a large
change will show.

Three cautions:

- **Sample size.** With 40 rows per run, the run 1 to run 2 improvement is a direction, not a proven effect. The
  intervals overlap.
- **Six changes at once.** Run 3 changes six rules together, so a difference between runs 2 and 3 cannot be credited
  to any one rule.
- **Brand pairs.** At the provisional cap of one per call, rule 6 removes most brand pairs, which the owner kept at a
  high rate in run 2 (5 of 6 sampled), so the medication keep rate may fall for that reason alone.

## Decisions left to the owner

- **The brand cap's number (to set before run 3).** The owner approved capping brand-for-generic pairs for run 3
  and set no number. The template carries one per call as a provisional default. Run 2's counts bear on the choice:
  50 of its 288 generated pairs were brand pairs, all among the 96 medication rows, with 7 to 10 of the 12 concepts
  in each of the 6 medication calls; the owner kept 5 of the 6 brand pairs in the review sample. The alternatives
  include zero, another per-call number, or a per-run total. Changing the number is an edit to rule 6's text.
- **Rule 4's reading of r006.** The rule asks for the clinical phrase as a clinician says it, not as a clinician
  writes it in a note (see *Rule 4*). If the owner meant the written form, that sentence should ask for it instead.
- **The speaker group for slang.** Rule 5 says "most adult patients" and names no country or dialect. Naming one
  (US English, for example) would make the rule easier to check.
- **When run 3 runs.** Before physician review of run 2's pairs in the verification app, or after it, so that the
  physicians' notes can shape the prompt first.
- **Trace selection.** Whether `pilot/analysis/trace_pairs.py` should keep selecting rows by the checker's
  same-meaning verdict by default, given its chance-level agreement with the owner on run 2 (kappa 0.05) and its 5
  of 10 on the known-good seed rows.
- **R8.** Whether to revise it, given the 2 kept rows in run 2 whose patient sentence the owner did not find natural.
- **Codebook rules.** Whether the six run 2 rules become codebook rules, which needs `make_codebook.py` to read
  more than one review export.
- **Still open from version 2.** Codebook O1 (a separate class for a patient's description of a diagnosis) and O2
  (clinician confirmation of the lexicon rulings).
