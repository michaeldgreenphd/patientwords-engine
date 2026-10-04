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
limitations).

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

For the 24 new advice questions the physician first gives their own urgency
without seeing the study's. Once that answer is saved, the app shows the
proposed urgency and asks whether they agree. The first answer cannot be
changed after that.

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

Physicians never see model names, measured numbers, batch or item ids, method
labels, Claude's reasons for a scenario, topics, checker verdicts, or the
proposed urgency before their own answer. The three versions of a script are
shown as Version A, B and C, in an order that differs between physicians.
Physicians do not see each other's answers.

## The holdout seal

Sealed Tier B holdout pairs are never shown to a physician. The exporter checks
every tracing and advice row with the study's seal rule and scans every text a
physician will see, and then the whole bundle, for any sealed phrase. Any hit,
or a seal that cannot be checked, stops the export and nothing is written. Run
the seal check over the bundle again before uploading it:

```bash
python scripts/export_verification_tasks.py --site ../patientwords
python scripts/seal_check.py --site ../patientwords --extra data/verification
```

## Privacy

Everything that leaves the app uses a rater code (`md01`, `md02`, and so on).
The link between a code and a name stays in the private Sheet. The app's
export for the engine carries codes, assignments and answers, never usernames,
names or password data. Physicians agree to this before they start, and can
stop at any time.

## What the ratings feed

- **Future generation runs.** Realism, keep-or-drop and notes per item show
  which kinds of scenario to generate more or less of.
- **Reference urgency for the advice preregistration.** The physicians'
  answers on the 24 new questions are candidate adjudicated reference tiers.
  The analysis takes one tier per item, so a rule for combining physicians
  (for example majority, or the middle answer) must be fixed before anyone
  rates. Adjudicated tiers go into a new file with the same item ids; the
  archived stimuli file is never rewritten.
- **Multi-turn scenarios before their first run.** Clinician review of the
  wave-3 scripts is a step the wave-3 design note lists before the first paid
  run. A text edit made after that run would need a new seed instead.
- **Agreement between physicians**, planned: Krippendorff's alpha (ordinal)
  with Gwet's AC2 for the five-point scales, nominal alpha with Gwet's AC1 for
  yes/no answers, exact and within-one agreement, and an item-level bootstrap
  with its seed recorded. The engine has no import script for ratings yet.

## Decisions still open (owner)

- The rule for combining physicians into one reference tier, and its
  tie-break.
- Whether "Can't tell" counts as an answer or as an abstention when agreement
  is computed.
- Whether the 15 rerun items should get reference tiers at all (no reference
  scoring is registered for them).
- What to do when a physician would triage the everyday-words version
  differently from the clinical one: the analysis has one tier per item.
