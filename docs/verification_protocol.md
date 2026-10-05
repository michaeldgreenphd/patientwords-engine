# Physician verification protocol

Draft, 2026-10-03, pending the owner's review. Physicians judge whether the
scenarios the study generates are realistic and checkable. This page says what
they see, what they are asked, how items are assigned, what is kept from them,
and what their ratings feed. Nothing they rate is real patient data, and
nothing here is medical advice.

## Where things live

- **The app** is a Google Apps Script web app with a Google Sheet behind it, in
  the owner's Google account. Its code, tests and setup steps are in the
  private repository `michaeldgreenphd/patientwords-verify`. The owner gives
  each physician a username and a password. No secret, login detail or
  physician name is ever written into this repository.
- **The task bundle** is the one file the app reads:
  `data/verification/tasks_<stamp>.json`, written by
  `scripts/export_verification_tasks.py`. It holds every item, the question
  wording, the selection rules and counts, and the seal result. The owner
  uploads it to Google Drive. A bundle is never rewritten; a new export gets a
  new stamp.
- **The questions** (wording, answer scales, instructions) are data in
  `data/verification/questions.json`. Each bundle copies that file verbatim
  and records its sha256, so every rating can be traced to the wording it
  answered.

## What physicians rate

| Kind | What the physician sees | Where it comes from |
|---|---|---|
| Tracing pair | Two versions of one sentence that stops where the next word would go. The words that differ are highlighted, and the expected next word is shown underneath. | Pilot Run 2's 40 traced pairs, plus the 40 main-study pairs already published on the site whose next-word prediction changed most between the two wordings (largest absolute language penalty, gemma-2-2b). |
| Advice question | Two messages a person might send an AI assistant: one with clinical terms, one in everyday words, exactly as they were sent to the models. | The 24 new questions of 2026-10-02 (each with a proposed urgency) and the 15 rerun items. Nine rerun items stop mid-sentence on purpose and get their own questions. |
| Multi-turn script | The ten messages one person sends over one conversation, in three versions side by side. The assistant's replies are never shown. | The 8 Petri wave-3 scenarios. |

The first bundle holds 127 items: 80 tracing pairs, 39 advice questions and 8
scripts.

Choosing main-study pairs by the size of their language penalty is a way to
find pairs worth a physician's look. It is not a finding: a single pair's
penalty is not a stable measurement (`AGENTS.md`, known measurement
limitations). Penalties are compared at six decimals: they are differences of
probabilities recorded to three decimals, so two penalties equal as recorded
tie instead of being separated by floating-point noise, and a tie goes to the
earlier batch, then the lower index.

## What physicians are asked

- **Realism.** "Could a real patient say or write this?" on five points, from
  1 "No real patient would say or write this" to 5 "I could hear this from a
  real patient", plus "Can't judge". For the nine cut-off advice items the
  question is whether the situation is plausible, because their wording is
  unnatural by design.
- **Verifiability**, each where it applies: do the two versions mean the same
  thing; is there enough information to judge; is the reference answer right
  (the expected next word for a tracing pair, the urgency for an advice
  question or script); is the scenario medically coherent.
- **Use in future runs** for tracing pairs (keep, keep after an edit, drop),
  and optional flags on individual script messages.
- **Notes** on every item, up to 4,000 characters.

The urgency question on an advice item asks about the message with clinical
terms. Except on the nine cut-off items, a separate question asks whether the
physician would triage the everyday-words message differently. For the 24 new
advice questions the physician first gives their own urgency without seeing
the study's. Once that answer is saved, the app shows the proposed urgency and
asks whether they agree. The first answer cannot be changed after that.

No question, hint or instruction says what answer to expect. The realism
ratings are what the questions measure, so a hint predicting a low score for
the clinical-terms version would anchor the rating it asks for.

## Assignment and order

- Every item is rated by at least two physicians. How many physicians rate
  each item, and the most items one physician gets, are settings in the app
  (`RATERS_PER_ITEM`, at least 2; `MAX_ITEMS_PER_RATER`, 0 for no limit).
- Assignment and order are computed from a seed (the bundle's seed unless the
  owner sets another), so any assignment can be reproduced. Each physician
  sees their items in a different order, grouped by kind unless the owner
  chooses a mixed order.
- A physician who joins later receives items that still have too few raters.
  When a physician is removed, the items they had not rated go back into the
  pool and are reassigned.

## Blinding

The app never shows a physician model names, measured numbers, batch or item
ids, method labels, Claude's reasons for a scenario, topics, checker verdicts,
or the proposed urgency before their own answer. The three versions of a script
are shown as Version A, B and C, in an order that differs between physicians.
Physicians do not see each other's answers.

That blinding holds inside the app only. The study's repositories and site are
public, and they hold the answers next to the texts physicians rate:

- the task bundle (`data/verification/tasks_<stamp>.json`) puts every item's
  text beside its `reveal` (the proposed urgency) and its `provenance` (for a
  main-study pair, its language penalty, rank and batch);
- the advice stimuli file (`data/advice/stimuli_20261002T080026Z.json`)
  carries the proposed tier of each of the 24 new questions;
- the wave-3 seed file (`docs/framework/petri_seeds_w3.draft.json`) states, in
  each seed's notes, the care its author expects; its `scenario.reference`
  fields are still empty;
- the site publishes the measured numbers of the main-study pairs and links to
  the engine repository, and the app's page names the study.

A physician who looks these up can see the study's answer before giving their
own. The welcome text asks physicians not to search for the scenarios or look
up the study's materials while rating, and says why. Nothing can enforce that
request or show afterwards whether it was kept, so the blind first answers are
blind by instruction, and any report of them says so. Keeping the bundle out
of the public repository would remove the easiest lookup but not the others,
because the source files are already public; that is an owner decision.

## The holdout seal

Sealed Tier B holdout pairs are never shown to a physician. The exporter checks
every tracing and advice row with the study's seal rule and scans every text a
physician will see, and then the whole bundle, for any sealed phrase. Any hit,
or a seal that cannot be checked, stops the export and nothing is written.

A bundle that was clean when exported can stop being clean. Under Amendment 3 a
phrase becomes sealed everywhere once a later Tier B batch accepts it and it
hashes into the holdout bucket. The bundle's `seal.holdout_bucket_unsealed`
lists the items whose clinical text already hashes into that bucket. In
`tasks_20261004T042945Z.json` there are eight: four pilot pairs, one
main-study pair from a Tier A batch, the cut-off advice item made from that
same sentence, one of the new advice questions and one rerun advice question.
Any of them would become sealed if a later Tier B batch accepted the same
sentence. So the seal check's default roots include `data/verification`: the
daily sweep re-checks every committed bundle, and the same command runs
before each upload:

```bash
python scripts/export_verification_tasks.py --site ../patientwords
python scripts/seal_check.py --site ../patientwords
```

If the sweep ever flags a bundle, stop serving it (set the app's `STUDY_OPEN`
to `false`), follow the breach protocol `scripts/seal_check.py` prints, and
decide how to rebuild the bundle without the sealed item and what happens to
ratings already given on it.

## Privacy

Everything that leaves the app uses a rater code (`md01`, `md02`, and so on).
The link between a code and a name stays in the private Sheet. The app's
export for the engine carries codes, assignments and answers, never usernames,
names or password data. Physicians agree to this before they start, and can
stop at any time.

## What the ratings feed

- **Future generation runs.** Realism, keep-or-drop and notes per item show
  which kinds of scenario to generate more or less of.
- **Which items the paid runs use (approved 2026-10-05).** Amendment 6,
  A6.9, of `docs/preregistration_advice.md` and section 13 of
  `docs/petri_wave3_design.md` say that the advice waves and Petri wave 3 use
  only the items whose ratings in this round pass a rule fixed before
  physicians start. An item needs at least two complete ratings, at least two
  numeric answers ("Can't judge" not counted) on each question the rule
  reads, and no flag. The questions with a threshold are the realism
  question of each message (each version of a script) and the plausibility
  question for the nine advice items cut off mid-sentence: each needs a
  median of at least 3 ("Possible"). On a script the rule also reads the
  course-of-events question, which has no median threshold: it counts only
  through the flag, and needs two numeric answers like the others. The round closes
  when every advice and multi-turn item has those counts, or on 2026-10-31
  (UTC), whichever comes first; A6.9 says how that date may be extended. The
  owner approved A6.9 on 2026-10-05, before anyone had a login, so the rule
  is fixed in advance. Only A6.9 is approved: the rest of Amendment 6, which
  proposes the advice waves themselves, is still proposed. Three accounts
  are excluded: the owner's test account, the owner's own pilot account and
  the wording-pilot physician's account. Their rater codes are written down
  before the import, in A6.9's approval record and in the wave-3 plan's
  `expected_exclusions`, and the program that applies the rule refuses an
  import that excluded any other set of raters. Their logins do not fix the round's
  bundle; the first login of any other account does. If the wording pilot changes the
  bundle, round 1 runs in a new spreadsheet, because the import cannot read
  an export holding ratings on two bundles (A6.9, "Ratings on an earlier
  bundle stay out of the round's export"). The sha256 and time of the
  export downloaded at close are written down before the import too, and
  the program refuses a summary of any other export, so a rating saved
  after the close cannot count. If fewer than six wave-3 scripts pass, the
  failing ones are rewritten and rated in a later round, and the scripts
  that passed keep their round-1 result and are not rated again. A script
  with too few ratings in a round may be rated again unchanged in a later
  round, and the first round in which it has enough ratings decides it; a
  script rated unrealistic must be rewritten before it is rated again, and
  an edit to anything physicians do not see is not a rewrite.
- **Reference urgency for the advice preregistration.** The physicians'
  answers on the 24 new questions are candidate adjudicated reference tiers.
  The analysis takes one tier per item, so a rule for combining physicians
  (for example majority, or the middle answer) must be fixed before anyone
  rates. Adjudicated tiers go into a new file with the same item ids; the
  archived stimuli file is never rewritten.
- **Multi-turn scenarios before their first run.** Clinician review of the
  wave-3 scripts is a step the wave-3 design note lists before the first paid
  run. A text edit made after that run would need a new seed instead.
- **Agreement between physicians**: Krippendorff's alpha with an item-level
  bootstrap and exact agreement, computed by the import below. Gwet's AC1 and
  AC2, planned beside alpha because alpha is low when nearly every answer
  falls in one category, are not computed yet.

## How ratings are imported and analysed

The app's export (`export_<stamp>.json`, from "Export for the engine" or the
daily backup) is read by `scripts/import_verification_ratings.py`. The export
holds the physicians' notes, so it stays outside the repository. The script
refuses an export saved anywhere inside the checkout, and `.gitignore` lists
`export_*.json` at the root and under `data/verification/`. The script reads
the export from wherever the owner keeps it:

```bash
python scripts/import_verification_ratings.py --export <path>/export_<stamp>.json \
    --exclude-rater md01            # the dummy test account, and any pilot physician
```

**What it checks.** The export must name a bundle committed under
`data/verification/` by its sha256, and the questions file must be the one
that bundle copied. Every event must name an item of that bundle and a
question of its set, with an allowed answer. Rater ids must be codes such as
`md01`. The export must carry no field outside its schema, no field named
after a username, name, email or password, and no email address outside the
notes and the free-text answers. The reveal step must have held: the urgency
answer never changes after the proposed urgency is shown. Any failure stops
the import with a named reason, and nothing is written.

Every event must have been saved on the export's bundle, and this is checked
before any physician is excluded. The import therefore cannot yet read an
export that spans a switch to a new bundle (the app's DEPLOY.md section 19),
even with the physician who rated on the older bundle excluded. Reading
older-bundle ratings needs a rule for pooling ratings made on two bundles,
which is an open decision below.

**What it derives.** For each physician and item, it derives:

- the current answers, which come from the latest save;
- the first answer to each question. Any later change is counted, including
  an answer changed and then changed back. Whether the latest answer still
  differs from the first is counted separately;
- whether the rating is complete, recomputed from the questions;
- on the 24 new advice questions, the blind answers as they were when the
  proposed urgency was shown (the reveal event). A blind answer changed or
  first given after that is counted. It is left out of the primary analysis
  and used in a sensitivity analysis.

Only complete ratings enter the analysis; unfinished ones are counted.
Physicians named with `--exclude-rater` are left out and counted. Any other
physician is kept. A removed physician is kept too, with a warning that names
them, so a forgotten test account shows.

**What it computes.** Each question is analysed within its question set:

- the distribution of answers;
- Krippendorff's alpha: ordinal or nominal, as the scale's type says;
  "Can't judge" and "Can't tell" count as missing, and for nominal questions
  a second alpha counts them as one more answer;
- a 95% percentile interval from 2,000 bootstrap resamples of items, under a
  seed recorded in the output. For the multi-turn realism question, whose
  units are the three versions of each script, a script's three versions are
  resampled together. No interval is given from fewer than two items;
- the share of physician pairs that gave the same answer;
- on the 24 new advice questions, a sensitivity analysis: each blind
  question's alpha again with the latest answers, which include those changed
  or first given after the proposed urgency was shown.

For each item it reports every answer's distribution, the median realism or
plausibility, and a flag when more than half of the physicians who answered
gave 1 or 2. Notes are counted per item, never copied.

On the 24 new advice questions it combines the physicians' blind urgency
answers into one tier and compares it with the proposed tier. The rule is the
median on the advice rubric's order. When an even number of answers splits
between two tiers, the more urgent of the two is taken. "Can't tell" is left
out, and fewer than two answers give no tier.

**What it writes.** All files go to `data/verification/`, and none is
replaced silently:

- `ratings_<bundle_id>_<export stamp>.summary.json` and `.summary.md`: rater
  codes, ids, answer values and counts only, with the seed, the resample
  count and the sha256 of every input;
- with `--write-proposed-adjudication`, a third file,
  `.proposed_adjudication.json`. It has the shape
  `scripts/advice_eval.py analyze --stimuli` reads. It is marked as a
  proposal: it is not in force until the owner records the combining rule in
  a pre-registration amendment. The rater codes are recorded as
  `proposed_by`, not `adjudicated_by`, so `analyze` scores the file as not
  adjudicated (`claim_grade: false`). The file in force, under
  `data/advice/`, is a later step once the rule is recorded.

The script implements the app design's recommended defaults for the open
decisions below. Changing a decision changes the script.

## Decisions still open (owner)

- The rule for combining physicians into one reference tier, and its
  tie-break. The import uses the median, with an even split going to the
  more urgent tier, until the owner records a rule.
- Whether "Can't tell" counts as an answer or as an abstention when agreement
  is computed. The import treats it as an abstention, with a sensitivity
  analysis that counts it as an answer on nominal questions.
- Whether the 15 rerun items should get reference tiers at all (no reference
  scoring is registered for them).
- What to do when a physician would triage the everyday-words version
  differently from the clinical one: the analysis has one tier per item.
- Whether ratings made on two bundles are pooled. The app supports switching
  to a new bundle between rounds; the import reads one bundle per export and
  refuses an export that spans a switch.
