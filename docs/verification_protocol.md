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
- **The questions** (wording, answer scales, instructions, and any examples
  shown before the first item) are data in
  `data/verification/questions.json`. Each bundle copies that file verbatim
  and records its sha256, so every rating can be traced to the wording it
  answered.

## What physicians rate

| Kind | What the physician sees | Where it comes from |
|---|---|---|
| Tracing pair | Two versions of one sentence that stops where the next word would go. The words that differ are underlined (the app shows them bold and underlined), and the expected next word is shown underneath. | Pairs from the pilot runs the export names (in the first bundle, Run 2's 40 traced pairs; see below), plus the 40 main-study pairs already published on the site whose next-word prediction changed most between the two wordings (largest absolute language penalty, gemma-2-2b). |
| Advice question | Two messages a person might send an AI assistant: one with clinical terms, one in everyday words, exactly as they were sent to the models. | The 24 new questions of 2026-10-02 (each with a proposed urgency) and the 15 rerun items. Nine rerun items stop mid-sentence on purpose and get their own questions. |
| Multi-turn script | The ten messages one person sends over one conversation, in three versions side by side. The assistant's replies are never shown. | The 8 Petri wave-3 scenarios. |

The first bundle holds 127 items: 80 tracing pairs, 39 advice questions and 8
scripts. A later round's bundle adds pilot runs (see *Rounds*).

Choosing main-study pairs by the size of their language penalty is a way to
find pairs worth a physician's look. It is not a finding: a single pair's
penalty is not a stable measurement (`AGENTS.md`, known measurement
limitations). Penalties are compared at six decimals: they are differences of
probabilities recorded to three decimals, so two penalties equal as recorded
tie instead of being separated by floating-point noise, and a tie goes to the
earlier batch, then the lower index.

### Pilot pairs: which runs, which rows, and their traces

A bundle takes pilot pairs from each pilot run named with `--pilot-run <run id>`
(a directory under `pilot/runs/`; the option can be repeated). With none named
it takes `pilot_v2_20261002` (Run 2) alone, as the first bundle did, so the
first bundle's command still gives that bundle's items unchanged (see
*Reproducing the first bundle* below).

- **Which runs.** A run must be finalized (its `manifest.json` has
  `finalized_utc`) and version 2 (`design.json` has `harness_version` 2, the
  version that records the expected next word). Every run file the exporter
  reads (`design.json`, `generated/all_rows.jsonl`, `review_map.json`) must
  still hash as the finalized manifest records. Anything else stops the export.
- **Which rows.** By default a run gives its blind review sample, the rows its
  `review_map.json` names (for Run 2, the 40 pairs the owner reviewed). With
  `--pilot-all-rows <run id>` it gives every generated row that is not a
  control row instead; negative controls are left out and counted. Every row
  exported must have an expected next word that follows the version-2 rule:
  one lowercase word of letters, with at most one internal hyphen or
  apostrophe. This is the check the parser and `pilot/analysis/trace_pairs.py`
  apply, and the export uses the latter's. A row that breaks it stops the
  export (`bad_next_word`), whether or not the run's trace is required.
- **Traces.** By default every pilot pair must have a trace result: the run's
  trace pairs file must hold the row, and the run's trace results must carry it
  with the same prompts. The export reads them where the circuit-trace lane
  writes them (see *Where a run's traces are*): for gemma-2-2b in
  `pilot/traces/<run id>/<that file's name without .json>/`, and for another
  graph model in `.../<name without .json>__<model>/`.
  `--pilot-trace-model <run id> <model>` reads that model's directory and no
  other. With no model named, the export reads the one model whose directory
  holds results. It stops if there are none (`missing_trace`), or if results
  are in more than one directory (`ambiguous_trace`), so it never chooses
  between models for you. Every trace summary it reads must also name that model in its
  `graph_model` field, which the circuit-trace lane records in every summary; a
  summary that names another model, or none, stops the export
  (`trace_model_mismatch`), so a summary copied into the wrong model's
  directory is never credited to that model. The selection block records the
  model it read. Physicians rate the
  sentences, not the trace, so a pair does not need its trace to be rated; the
  trace matters when ratings are later compared with trace measures. A run's
  traces may land after its bundle is wanted, so
  `--pilot-trace-optional <run id>` exports that run without requiring a trace
  or reading trace results. Its items are then the same before and after the
  traces land, and a rating joins its trace later by run and row id. Such a
  run reads no trace file at all, except Run 2: its item ids are keyed on its
  trace pairs file (see *Labels and ids*), so that file is still read, for the
  sha256 its items record, and must exist.
- **Which trace pairs file a selection needs.** `pilot/analysis/trace_pairs.py`
  builds a run's trace pairs file in one of three ways. With `--review-sample`
  it holds exactly the review sample and records each pair's review id, which
  must match `review_map.json`; this is the file the default selection needs,
  as Run 2's is. Its default holds the rows the checker judged equivalent, and
  `--include-controls` adds the negative controls; neither records review ids.
  A review-sample row the checker did not judge equivalent is missing from
  those, so the export stops (`missing_trace`). `--pilot-all-rows` takes every
  non-control row, whatever the checker said, and none of the three files holds
  all of them once the checker has said no to any row. In practice
  `--pilot-all-rows` therefore goes with `--pilot-trace-optional` for the same
  run.
- **Where a run's traces are.** This follows PR #85's layout, which must be
  merged before this export is used on a new fire. Since 2026-10-05 the
  circuit-trace lane writes each run's traces in a folder of its own,
  `pilot/traces/<run id>/<pairs file name without .json>/` (with `__<model>`
  added for a model other than gemma-2-2b). `<run id>` is the directory
  directly under `pilot/runs/` that holds the pairs file. Before that, the lane
  named the folder after the pairs file alone. Two runs were traced that way,
  and their results stay where they are:
  - Run 2's in `pilot/traces/trace_pairs/`;
  - Run 3's in `pilot/traces/pilot_v3_20261004_trace_pairs/`.

  The export reads each of these two folders for its own run only, and only
  while the run still holds the pairs file the folder is named after. It never
  reads any other folder directly under `pilot/traces/`. A run that has one
  graph model's results in both its legacy folder and its own folder stops the
  export (`trace_layout_conflict`), whichever model is named. The two sets
  would be two traces of one pairs file by one model, and the export never
  chooses between them. A person decides which set stands; moving or removing
  committed results is a decision, made in a pull request. Until then
  `--pilot-trace-optional <run id>` exports the run without reading either
  set. Different models in different layouts are not a conflict: a run traced
  again with another model keeps its gemma-2-2b results where they were, and
  the model rules above apply across both layouts. Name the model with
  `--pilot-trace-model`; with none named, two models stop the export
  (`ambiguous_trace`). A run id that is one of the two legacy folder names is refused
  (`bad_input`), as the lanes refuse it, because that run's own folder would
  sit inside the old one.
- **Name the pairs file after the run.** A run's trace pairs file must be named
  `<run id>_<name>.json`, where `<name>` is not empty, so a results folder's
  name says which run it holds. This is the rule the circuit-trace and
  logits-eval lanes apply to a pairs file under their pilot roots
  (`scripts/fire_trigger.py`'s `pilot_pairs_run_name_problem`, added by
  PR #85), so a run the export accepts is one the lane will trace. A bare run
  id, or the run id followed by anything but `_`, is refused by both. Run 3's
  file is `trace/pilot_v3_20261004_trace_pairs.json`. Run 2's
  `trace_pairs.json` predates the rule and keeps its name, because its items'
  ids are keyed on that file. The export stops (`bad_input`) on a trace pairs
  file that is not named after its run, and on one whose name holds `__` (the
  lane's model separator). It checks every file under each exported run's
  `trace/`, including a run exported with `--pilot-trace-optional`, because
  that run's trace may still be fired. For such a run it reads only the file
  names, not the files. Two runs' files may share a name, since each run's
  results are in its own folder. Build a run's file with
  `pilot/analysis/trace_pairs.py --out pilot/runs/<run id>/trace/<run id>_trace_pairs.json`
  before its trace is fired.
- **Tracing Run 2 again.** Under PR #85's rule the lanes refuse Run 2's
  `trace_pairs.json` for a new fire. Re-running
  `pilot/analysis/trace_pairs.py --run-dir pilot/runs/pilot_v2_20261002 --review-sample`
  writes a byte-identical `pilot_v2_20261002_trace_pairs.json` beside it, and
  copying the file there does the same. Leave it byte for byte the same.
  Run 2's finalized manifest records no hash for any file under `trace/`, so
  the copy leaves the finalized run as it was. The copy alone changes nothing:
  the export still reads `trace_pairs.json`, which Run 2's item ids are keyed
  on, and its results in `pilot/traces/trace_pairs/`. Results traced from the
  copy land in Run 2's own folder,
  `pilot/traces/pilot_v2_20261002/pilot_v2_20261002_trace_pairs[__<model>]/`.
  They are results of the same pairs, so the export reads them as Run 2's.
  Traced with another graph model, they sit beside the legacy gemma-2-2b
  results without conflict. A command that names no model then finds two
  models and stops (`ambiguous_trace`). That is why the reproduction command
  below names `--pilot-trace-model pilot_v2_20261002 gemma-2-2b`, which still
  gives the first bundle's items unchanged. Traced with gemma-2-2b, they are a
  second gemma-2-2b trace of Run 2 beside the legacy one, and the export stops
  (`trace_layout_conflict`) until the owner decides which set stands. When a
  run's trace is required, any other second file under its `trace/`, including
  a copy that differs, stops the export (`bad_input`). A run exported with
  `--pilot-trace-optional` reads no trace pairs file (Run 2 reads only
  `trace_pairs.json`, for its id key), so for such a run the second-file and
  copy checks wait until its trace is required; the names of its files are
  still checked.
- **Labels and ids.** Each item's provenance names its run: `pilot_run2` for
  Run 2, as in the first bundle, and `pilot:<run id>` for any other run.
  Physicians never see it. A later run's item ids are keyed on its generated
  rows file and row id, so a row keeps one id whichever rows and trace option
  a bundle uses. Run 2's stay keyed on its trace pairs file, as in the first
  bundle, because the app stores every rating under the item id.
- **Repeats.** A pair whose two sentences repeat an earlier pilot pair in the
  same bundle is kept, since each row is its run's output, and counted in its
  run's selection block.
- **Reproducing the first bundle.** This command rebuilds the first bundle,
  `data/verification/tasks_20261004T042945Z.json`, from the committed files.
  Write it to a scratch directory, since the export never overwrites a bundle:

  ```bash
  python scripts/export_verification_tasks.py --site ../patientwords \
      --stamp 20261004T042945Z \
      --pilot-trace-model pilot_v2_20261002 gemma-2-2b \
      --out-dir <scratch directory>
  ```

  It names Run 2's graph model because Run 2's first traces are gemma-2-2b's.
  Once Run 2 is traced again with another model (see *Tracing Run 2 again*), a
  command that names no model finds two models and stops (`ambiguous_trace`).
  Naming gemma-2-2b reads the traces the first bundle was built from, so the
  command keeps working after any such trace. Naming the model changes no
  item: no item records the model, only the selection block does, and it is
  gemma-2-2b either way. The first bundle was exported before this option
  existed, without it.

  Compare from `"items": [` to the end of the file. Those bytes come out
  identical to the committed bundle's while the site payload and the engine
  inputs it recorded are unchanged, and
  `test_the_recorded_command_reproduces_the_first_bundles_items_byte_for_byte`
  checks exactly that. The rest of the file differs by design. The exporter
  has changed since the first bundle: `sources` has more entries and new role
  names, and `selection` has per-run blocks.

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

### Examples before the first item

The questions file may hold examples (`instructions.examples`) that the app
shows before a physician's first item, so they know what each kind of item
looks like. Each example names the question set whose items it imitates
(`tracing_pair`, `advice_new`, `advice_rerun`, `advice_rerun_truncated` or
`multiturn_script`; that set's `family` gives its family instructions), a
label, a one-sentence caption saying what the physician judges, and a display
of exactly the shape that set's items have, so the app draws it as it draws an
item. Examples are invented. They carry no answer, no proposed urgency and no
rating, and they are none of the study's items.

The exporter checks each example and stops, naming the example, on any
problem:

- **Shape** (`bad_example`): a question set that is not one of the five, a
  missing or extra field, or a display that is not the set's. For a sentence
  pair the marked words must be exactly the ones the exporter would mark, the
  words where the two sentences differ, and the next word must follow the
  version-2 rule. A message pair must have the set's cut-off setting. A
  conversation's versions must all have `n_turns` messages, and a message
  that repeats an earlier version word for word must say so (`same_as`), as
  an item's does.
- **What a physician may not see** (`example_not_blind`): a model or vendor
  name from any of the engine's model registries, found even inside another
  word (BioMistral, MedGemma, ChatGPT; a test fails when a registered model
  is not matched); a batch, run or item id; a decimal number or a percentage, which is
  how a measured value is written; or the name of any urgency level the
  study can propose, read from the questions file. An item's display is
  built only from the texts physicians rate, so it carries none of the
  study's own models, ids, measurements or answers. An example is written by
  hand, so its text is checked instead, and more strictly than an item's
  could be: a patient's message in an item may contain a decimal number, but
  an example may not.
- **The holdout seal** (`seal_hit`): every string of every example is
  scanned for sealed phrases, as an item's texts are.

The bundle copies the questions file, examples included, unchanged. A
questions file without examples is still valid.

Version 1.2-draft of the questions holds three examples, drafts for the
owner and the wording-pilot physician to review. Each uses an ordinary, mild
condition that no scenario of the study uses, so none can be mistaken for an
item:

- a sentence pair, "singultus" against "hiccups", stopping before the next
  word "ten";
- a message pair about a splinter in a fingertip, one message with a
  clinical description and one in everyday words (the layout of the 24 new
  advice questions, without the proposed urgency);
- a conversation about itchy mosquito bites after camping, shortened to three
  messages in three versions, with one message that repeats another
  version's word for word, so the "same as" marking is shown.

Version 1.2-draft also calls the marked words of a sentence pair underlined
rather than highlighted (the owner's request of 2026-10-06), in the family
instructions and in the realism question and its hint. A bundle copies the
questions file when it is exported, so the committed round-1 bundle,
`tasks_20261004T042945Z.json`, keeps version 1.1-draft; version 1.2-draft
reaches physicians only in a bundle exported after it.

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
  (UTC), whichever comes first; A6.9 says how that date may be extended.
  The round ends at the end of that date in UTC, 23:59:59Z, which is
  18:59:59 CDT in US Central time, and the program that applies the rule
  refuses an export downloaded after then, unless an extension recorded
  before the date moved it. An export downloaded before that date counts
  only if every advice and multi-turn item already has both counts;
  otherwise the program refuses it, because the round has not closed. The
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
  that passed keep their round-1 result and are not rated again. Once six
  pass there is no later round, and the program that applies the rule
  refuses one. A script
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

## Rounds

Each physician round uses one bundle. The import reads one bundle per export:
every event in an export must have been saved on the bundle the export names,
or the import stops (`event_bundle_mismatch`).

**Round 1** is `tasks_20261004T042945Z.json`: Run 2's 40 pairs, the 40
main-study pairs, the 39 advice questions and the 8 scripts. Before round 2
starts, take round 1's final export and import it. That summary is round 1's
result.

**Round 2** adds pilot Run 3 (`pilot/runs/pilot_v3_20261004/`). Run 3 and
its trace results must be finalized, seal-checked and committed first, since
the exporter reads them from the repository. Its bundle is round 1's command
with Run 3 added, under a new stamp:

```bash
python scripts/export_verification_tasks.py --site ../patientwords \
    --pilot-run pilot_v2_20261002 --pilot-run pilot_v3_20261004 \
    --previous-bundle data/verification/tasks_20261004T042945Z.json
python scripts/seal_check.py --site ../patientwords
```

- Keep `--pilot-run pilot_v2_20261002` and every other default (the seed,
  `--main-pairs 40`, the advice and seed files), so every round 1 item keeps
  its item id. The app needs every item a physician already holds to be in
  the bundle it switches to, and stores answers under item and question ids
  (the app's DEPLOY.md section 19). `--previous-bundle` checks this: the
  export stops, naming item ids, if any round 1 item is missing
  (`previous_item_missing`), shows another text, proposed urgency or question
  set under its id (`previous_item_changed`), or if a question id round 1 used is gone
  (`previous_question_missing`). It also stops, naming question ids, if a
  kept question id has another scale type, other answer values or another
  order of them, another "can't judge" value, another length limit, phase,
  required or optional setting, per-version setting or reveal lock
  (`previous_question_changed`). The app checks a stored answer against all of
  these when a physician saves the item again, and uses whether a question is
  required to decide when the proposed urgency may be revealed and when an item
  is complete. After such a change, an answer given in round 1 would be
  refused, read on another scale, or counted as complete or incomplete
  differently. Answer values are compared with their JSON types, as the app and
  the import compare them, so `true` in place of `1` is another value. A new
  question may be added to a question set that round 1 items use only as
  optional: the export stops, naming question ids, on a new required one
  (`previous_required_question_added`), because no round 1 rating answers it,
  so the app and the import would count a completed item as incomplete, and the
  import would refuse a stored reveal that lacks a required blind answer. A set
  that no round 1 item uses may gain required questions. The
  export also stops if the notes length limit changed
  (`previous_notes_changed`): the app and the import refuse a note longer than
  the bundle's limit. Wording may change. The main-study pairs are ranked again from
  the site payload at export time, so a pair published since round 1 can push
  a round 1 pair out of the top 40. The export then stops and names its item
  id, and a larger `--main-pairs` keeps it while it is still published.
- The command above takes Run 3's review sample and requires its gemma-2-2b
  traces. Run 3's trace pairs file, `trace/pilot_v3_20261004_trace_pairs.json`,
  was built with `pilot/analysis/trace_pairs.py --review-sample` and named after
  the run. Its traces were fired before PR #85's per-run layout and are in
  `pilot/traces/pilot_v3_20261004_trace_pairs/`, beside Run 2's
  `pilot/traces/trace_pairs/` (see *Which trace pairs file a selection needs*
  and *Where a run's traces are*). Tracing Run 3 again writes
  `pilot/traces/pilot_v3_20261004/`. If that is another graph model, add
  `--pilot-trace-model pilot_v3_20261004 gemma-2-2b` (or the other model) to
  say whose traces the bundle requires. If it is gemma-2-2b again, the export
  stops (`trace_layout_conflict`) until the owner decides which set stands.
- Add `--pilot-trace-optional pilot_v3_20261004` if Run 3's traces have not
  landed when the bundle is wanted.
- Add `--pilot-all-rows pilot_v3_20261004` to send every Run 3 pair rather than
  its review sample, together with `--pilot-trace-optional pilot_v3_20261004`:
  no trace pairs file `trace_pairs.py` builds holds every non-control row once
  the checker has said no to one, so a required trace would stop the export
  (`missing_trace`). Every added item needs at least two physicians.
- Commit the bundle through a pull request, as the first was, then switch the
  app to it between rounds (DEPLOY.md section 19). **Assign items** gives the
  new items to physicians.

**Reading round 2's ratings.** The app keeps every rating in one Ratings tab,
and round 1's events carry round 1's bundle. An export taken after the switch
therefore spans two bundles, and the import refuses it, even with round 1's
physicians excluded. Reading round 2 needs one of two things: a rule for
pooling ratings made on two bundles, built into the import, or round 2 run on
its own Sheet (a separate deployment of the app), whose export holds round 2's
events only. A separate Sheet's bundle need not keep round 1's items, but
every bundle carries the advice questions and scripts, so they would be rated
again. Until the owner chooses, round 2's ratings stay in the app and its
backups and are not imported.

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
  refuses an export that spans a switch, so round 2's ratings cannot be
  imported until this is decided or round 2 runs on its own Sheet (*Rounds*).
