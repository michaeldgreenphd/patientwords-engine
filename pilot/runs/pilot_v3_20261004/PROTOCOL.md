# Protocol: stimulus-generation pilot, run 3 (version-3 prompts, harness version 2)

Written 2026-10-04 before any generation call of this run. Frozen after writing: its SHA-256 is recorded in manifest.json at the plan-time write and checked again at finalize. Deviations are recorded in HANDOFF.md, never here.

## 1. Purpose and scope

This run measures whether the version-3 generation prompt (`pilot/prompts_v3/`, merged in pull request #80) addresses the owner's notes from the blind review of run 2 (`pilot_v2_20261002`, reviewed 2026-10-04) without losing what version 2 achieved: rows the owner judges usable and that the circuit-trace lane can measure. It repeats run 2 with the same seeds, design, harness and checker prompt. What changes is the generation prompt's rule text and one example in `design.json`:

- Rule 3, first person only: both sentences are the patient speaking or writing about themselves, about their own body, symptoms and medicines. Version 2 also allowed a relative speaking about the patient.
- Rule 4, the clinical phrase as a clinician says it: the standard term where one exists, rather than a description, written as a clinician would say it out loud, in its usual word order, not in the shorthand of a clinical note and not as a stiff phrase built to fit the blank.
- Rule 5, common slang only: slang that most adult patients would recognise, never regional, dated or rare slang. A variant's second, slangier phrasing is held to the same limit.
- Rule 6 (new), the brand cap: at most one concept per call may pair a drug's generic name with one of its brand names. One per call is the kit's provisional number, which the owner accepted by merging pull request #80. Version 2's brand sentences (a brand name only for a single-ingredient drug, never a combination product's) moved into this rule unchanged.
- Rule 8 (new), keep the side, the place and the number: when the clinical phrase says which side, which limb or place, or how many, the patient phrase says it too; where a patient would naturally say which side or which one, both phrases say it.
- Rule 9 (new), no grid names for a region: neither phrase names a region by its sector of an imaginary grid laid over part of the body; the clinical side uses the standard anatomical term for the part.
- `design.json` keeps only the first of version 2's two patient-phrase examples for rule 5, because the second left out the side that rule 8 requires.

Version 2's rules 6 and 7 are now rules 7 and 10, with their text unchanged. Three instructions around the rules change with them: a row's template is "one sentence that the patient says or writes about themselves", negative controls follow rules 3 and 10, and the header of the seed exemplars says they were written before these rules and some are not in the first person. `pilot/prompts_v3/README.md` gives the review note behind each change.

The checker's role also changes, by the owner's decision D1 of 2026-10-04 (codebook v0.3, `pilot/codebook/codebook_v0.3.md`): physician review in the verification app (a private app outside this repository) decides which stimuli are kept, and the checker does not. The checker runs with version 2's prompt, byte for byte, and its answers are computed and reported as a same-meaning screen. No step of this run keeps or drops a row on them.

The run reports properties of the generated rows and of the checker. It is not an effect analysis: nothing here is a measurement of the study's models.

## 2. Inputs

- Seed cases: `seeds.json`, the same 26 cases runs 1 and 2 used, byte-identical to run 2's file (converted from the engine's `data/measured/imported_pairs.json`; specialty and swap type are "unlabelled"; provenance is stated in the file). SHA-256 recorded in the manifest.
- Exemplars per call: K = 8.
- Known-good rows for checker validation: the first 10 seed cases.
- Design: `design.json`, copied unchanged from `pilot/prompts_v3/design.json` (`harness_version: 2`): the same 3 specialties x 3 swap types as runs 1 and 2, and version 2's probe endings, variant design and example negative control.
- Prompts: `prompts/generation_prompt.txt` and `prompts/checker_prompt.txt`, copied unchanged from `pilot/prompts_v3/` at engine main 0404b10c (the kit as merged in pull request #80). The checker prompt is version 2's and run 2's, byte for byte.

## 3. Design

- Cells, arms and calls as in runs 1 and 2: 9 cells (specialty-major order), arms A (K seed exemplars sampled per call) and B (the same fixed K exemplars in every call), 18 calls.
- Each call asks for 20 rows with five keys (`clinical_term`, `patient_term`, `template`, `next_word`, `control`): 16 rows with `control: "none"` covering 12 concepts, 4 of which carry a second, vaguer or slangier patient phrasing on the next line (same clinical term, template and next word), and 4 negative controls.
- Templates end right after an article or possessive, and `next_word` is the single common word expected next after the clinical sentence.
- Execution: each call is a separate Claude Code subagent launched through the Workflow tool in the owner's interactive session on the owner's laptop, with no access to any other call; the subagents inherit the session model recorded in `manifest_model.json`. The harness's system prompt and the repository instructions it injects are outside this run's control; prompt hashes cover only the user-turn prompt. Generation uses no output schema, so format validity measures the model's raw text.
- Retry and no-repair rules exactly as runs 1 and 2 (one retry of a call that returns nothing usable; invalid lines are counted, never repaired).

## 4. Row format and validity

As run 2: `next_word` is required on every row and must pass the harness's next-word check (`common.next_word_ok`; a non-empty lowercase word of letters with one internal hyphen or apostrophe allowed, and the further characters run 2's HANDOFF.md, Deviations item 2, lists). A row failing it is a format failure, tagged in the harness's first-failing-condition order. Ending at a probe point (an article or possessive) is reported as compliance, not as a format condition.

## 5. Estimands

### 5.1 As run 2

Estimands 1-5 and the secondary descriptives are those of run 2, computed by the same code (harness version 2: Wilson intervals, the seeded bootstrap, Newcombe differences). The variant design is unchanged, so run 2's two design caveats still apply and are reported with the numbers: estimand 3 (template similarity) reads higher than in run 1 because 4 templates per call are reused by the second phrasings; and in estimand 2, up to 4 of the 16 non-control rows per call cannot count as novel by clinical term alone, because each second phrasing repeats its concept's clinical term (pair novelty and patient-term novelty are unaffected). The intervals of estimands 1-5 are computed over rows, and the rows are not independent draws (the rows of one call come from a single generation, and 8 of every 16 non-control rows belong to 4 two-row concepts), so they are read as descriptive.

The version-2 descriptives are reported outside the estimands, as in run 2: variant-design compliance per call and by arm; probe-point compliance by arm and cell; next-word counts; the checker's relation for generated, known-good and broken items with the precision view, the yes-rate by relation and the inconsistent answers; and the checker's sentence naturalness and patient realism by arm.

### 5.2 Counts that bear on the new rules

- **Rule 6, the brand cap.** Two counts, both from the checker's `relation` answer `same_brand`, over generated rows whose verdict is yes or no (an unclear verdict's relation is not counted, as in the summary):
  - The run total is the summary's checker relation count `same_brand` for generated rows. The summary reports it for the run as a whole, not by arm or by call. Run 2: 50 of 288.
  - Per call, read from `checked.jsonl` after `parse_checker.py` and recorded in HANDOFF.md, because no pilot script reports it: for each of the 18 calls (arm and cell), the number of such rows and the number of concepts holding at least one of them, a concept being the harness's `common.concept_key` (the call, the clinical term's surface form and the template). A call complies with rule 6 when it has at most one such concept. Reported: the counts per call, the complying calls over 18 overall and by arm, each with a Wilson interval, and the row totals by arm. Run 2's baseline under the same count: 7, 8 and 8 brand concepts of 12 in arm A's three medication calls, 8, 10 and 9 in arm B's, and none in the other twelve calls (50 rows, 23 in arm A and 27 in arm B), so 12 of its 18 calls would have complied, all of them non-medication calls.
  - Both counts are the checker's reading, not a verified tally. A brand pair the checker labels `same` is not counted, and a pair it labels `same_brand` in error is. The checker's relation answers have no truth set in this run other than the owner's review of 40 rows.
- **Rules 4 and 5.** The summary's checker answers on sentence naturalness and patient realism are reported as in run 2. By D1 they decide nothing, and on run 2 they could not separate the pairs the owner found natural or real (kappa 0.00 for each), so they are not read as evidence that rules 4 and 5 worked.
- **Rules 3, 4, 5, 8 and 9.** No pilot script counts them. They are judged in the owner's blind review of the 40-row sample (section 7) and in physician review. The run 2 counts the kit's README quotes for rules 3 and 9 (42 of 288 rows about another person, 7 of 288 rows naming a region by a grid sector) were made by reading every template after the fact. This protocol fixes no procedure for repeating them, so any such count made on this run is a post-hoc reading, reported in HANDOFF.md as one, and not an estimand.

### 5.3 The owner's blind review against runs 1 and 2

After the owner's review, outside this run's summary: the owner's first answers on the 40 sampled rows (kept as is, dropped, both sentences read naturally, patient phrase sounds real, patient phrase unlikely, the two phrases name the same thing), each with a 95% Wilson interval, overall and by swap type, set against the table in `pilot/prompts_v3/README.md` (*What to compare against runs 1 and 2*). Agreement between the owner and the checker is computed with `pilot/analysis/review_agreement.py`, as for run 2. Three cautions are fixed now: with 40 rows only a large change can be told apart from noise; six rules change together, so a difference from run 2 cannot be credited to any one of them; and the brand cap removes most brand pairs, which the owner kept at a high rate in run 2 (5 of 6 sampled), so the medication keep rate may fall for that reason alone.

## 6. Checker validation with known truth

As run 2: the checker set is every format-valid generated row with `control: "none"`, the 10 known-good seed rows, and 20 deliberately broken pairs (a target row's clinical term and template with another row's patient term from the same cell); blinded, shuffled, batches of 30, each a separate subagent; sensitivity on known-good and specificity on broken, with `unclear` counted as a miss and excluded. The checker answers per item: `equivalent`, `relation`, `sentence_natural`, `patient_realism` and a one-line reason, through the version-2 structured-output schema; an entry with a value outside a field's set is invalid and its item is missing.

By D1 these answers are reported and decide nothing: no pilot script keeps or drops a row on them, the review draw ignores them, and a not-equivalent answer marks a pair for a closer look without showing that it is broken. The lexicon rulings of codebook v0.2 (rules L0-L6) still define what the checker is asked; codebook v0.3 changes none of them.

## 7. Human review sheet and the keep decision

As run 2: 40 checked generated rows, at most one per concept, allocated to arms in proportion to their concepts by largest remainder, drawn with the `review` stream (concepts first, then one row of each), then shuffled and relabelled r001 to r040, with the checker's answers withheld in `review_sheet.csv` and kept in `review_key.csv`. The owner reviews them blind on the private review page, which stores this run's answers under its own run id. Agreement between the owner and the checker is computed after the review, outside this run's summary (the summary hashes the review sheet before it is filled).

Which of this run's pairs are kept as stimuli is decided by physician review in the verification app (D1). That review happens outside the pilot harness; this run's summary neither reads it nor reports it.

## 8. Randomness

Master seed 20260929, the harness constant, with the same named streams as runs 1 and 2. With the same seed file, arm A draws the same exemplars as runs 1 and 2 and arm B shows the same fixed exemplars, so runs 2 and 3 differ in the generation prompt's rule text and one example, not in the exemplars. The checker prompt is unchanged, but its batches hold this run's rows. Generation and checker subagents are language-model calls and are not reproducible bit for bit; their raw outputs are kept verbatim.

## 9. Order of operations

Every script runs with `PILOT_DIR` set to this run directory (`pilot/runs/pilot_v3_20261004/` in the repository working copy), under the engine checkout's virtual-environment interpreter, Python 3.12.14. The harness refuses to recompute a sealed run across the Python 3.12 change to `sum()`; 3.12.14 is on the same side as the 3.13.4 that sealed runs 1 and 2. This run is planned and sealed under 3.12.14, and any interpreter from 3.12 on can re-finalize it.

1. Write this protocol, HANDOFF.md (with its results markers) and manifest_model.json.
2. `plan_calls.py`; `write_manifest.py` (freezes this protocol, the model facts, the inputs and the scripts).
3. `make_workflow_scripts.py generation`; run the generation workflow; `extract_workflow_journal.py generation`; copy the journal to `workflows/generation.journal.jsonl`; `parse_generation.py`.
4. `build_checker_set.py`; `make_workflow_scripts.py checker`; run the checker workflow; `extract_workflow_journal.py checker`; copy the journal; `parse_checker.py`; the per-call brand count of section 5.2.
5. `make_review_sheet.py`; `compute_summary.py`; `record_run.py` for both stages; `write_manifest.py finalize`.
6. Holdout seal check over this run directory; it must be CLEAN before anything leaves the laptop.

After finalize, the same downstream consumers as run 2 read this run without changing it: the review page bundle, and `pilot/analysis/trace_pairs.py --review-sample`, which turns the 40-row review sample into a circuit-trace pairs file whatever the checker said. Tracing those pairs on the circuit-trace lane (output root `pilot/traces/`) is a pipeline check of traceability: what share of the pairs keep a measurable target at a 0.02 screen. Its numbers are never measurements of the study's models.

## 10. Execution path

The run executes under the pilot exception in `AGENTS.md` (*Execution model*). Each generation call and each checker batch is a Claude Code subagent launched through the Workflow tool in the owner's interactive session (Claude Code in VS Code on the owner's laptop), on that session's subscription and with no repository key. The planning steps may run in a subagent of the session; the session launches the workflows. No script in this repository calls a paid provider API for this run; subscription usage in the owner's session is not provider spend, so `fire_trigger.py`'s journal and ceiling do not apply to it. Nothing the run produces is written under `data/` or `trace_out/`, counted as a measurement, or published to the site, and the holdout seal check must be CLEAN over this run directory before each commit of it.

## 11. What is recorded

The run directory keeps every input (the seed file, the design, both prompt templates, the model facts and this protocol); both plans, with a SHA-256 per rendered prompt; both workflow scripts and the copied journals; the raw response of every attempt, the parsed rows and the format failures; the checker set, key, batches, answers and log; the review sheet, key and map; the summary (`summary.json` and `summary.md`, with the results block in HANDOFF.md); and `manifest.json`, with the input, prompt, script and output hashes, the interpreter, and a record per stage that binds the journal to the result file and carries the model ids the subagents' transcripts report. HANDOFF.md records the execution, the per-call brand count, any post-hoc reading, and every deviation from this protocol.

## 12. Limitations fixed in advance

- The generator and the checker are subagents of the same model family in the same session; the checker is independent in information, not in model identity.
- Subagent execution adds a harness system prompt and injected repository instructions that a bare API call would not carry; numbers characterise this execution path.
- Six rules change at once relative to run 2; a difference between the runs cannot be assigned to one of them.
- The brand cap's number is provisional. A run under another number would be a new run.
- The checker's judgements of relation, naturalness and realism have no truth set in this run other than the owner's later review of 40 rows; on run 2 its naturalness and realism answers sat at the ceiling and its same-meaning answers agreed with the owner's at chance level.
- The terminology rulings rest on standard terminologies, not on a clinician; clinician review is pending (codebook O2).

## 13. What is not claimed

- No number here is a measurement of the study's models or a claim about the study's stimuli; these are checks of the generation pipeline.
- A difference between runs 2 and 3 in the owner's review is a direction, not a proven effect, and is not credited to any single rule.
- Structural compliance (format validity, the variant design, the probe point) shows that the generator followed the format, not that the pairs are good stimuli.
- The brand counts are the checker's reading of the rows, not a verified count of brand pairs.
- The checker's naturalness and realism answers are not evidence that rules 4 and 5 worked, and its same-meaning answers are not a keep decision.
- The owner's review is one non-clinician reviewer's judgement; which pairs are kept is the physicians' decision (D1).
