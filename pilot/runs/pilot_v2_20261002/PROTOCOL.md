# Protocol: stimulus-generation pilot, run 2 (version-2 prompts and harness)

Written 2026-10-02 before any generation call of this run. Frozen after writing: its SHA-256 is recorded in manifest.json at the plan-time write and checked again at finalize. Deviations are recorded in HANDOFF.md, never here.

## 1. Purpose and scope

This run measures whether the version-2 generation loop produces stimulus pairs the owner judges usable and that the circuit-trace lane can measure. It repeats run 1 (`pilot_real_20260930`) with three changes: the generation prompt encodes the owner's review rules and standard medical terminology and asks for a traceable ending and target word; the checker judges what drove the owner's keep decisions (sentence naturalness and patient realism) as well as meaning; and the harness enforces and reports the new design. It reports properties of the generated rows and of the checker. It is not an effect analysis: nothing here is a measurement of the study's models.

## 2. Inputs

- Seed cases: `seeds.json`, the same 26 cases run 1 used (converted from the engine's `data/measured/imported_pairs.json`; specialty and swap type are "unlabelled"; provenance is stated in the file). SHA-256 recorded in the manifest.
- Exemplars per call: K = 8.
- Known-good rows for checker validation: the first 10 seed cases.
- Design: `design.json` with `harness_version: 2` (the version-2 run kit's file), the same 3 specialties x 3 swap types as run 1.
- Prompts: `prompts/generation_prompt.txt` and `prompts/checker_prompt.txt`, copied unchanged from `pilot/prompts_v2/` at the commit recorded in HANDOFF.md.

## 3. Design

- Cells, arms and calls as in run 1: 9 cells (specialty-major order), arms A (K seed exemplars sampled per call) and B (the same fixed K exemplars in every call), 18 calls.
- Each call asks for 20 rows with five keys (`clinical_term`, `patient_term`, `template`, `next_word`, `control`): 16 rows with `control: "none"` covering 12 concepts, 4 of which carry a second, vaguer or slangier patient phrasing on the next line (same clinical term, template and next word), and 4 negative controls.
- Templates end right after an article or possessive, and `next_word` is the single common word expected next after the clinical sentence (the study generator's target rule).
- Execution: each call is a separate Claude Code subagent launched through the Workflow tool in the owner's session on the owner's laptop, with no access to any other call; the subagents inherit the session model recorded in manifest_model.json. The harness's system prompt and the repository instructions it injects are outside this run's control; prompt hashes cover only the user-turn prompt. Generation uses no output schema, so format validity measures the model's raw text.
- Retry and no-repair rules exactly as run 1 (one retry of a call that returns nothing usable; invalid lines are counted, never repaired).

## 4. Row format and validity

As run 1, plus: `next_word` is required on every row and must be a non-empty lowercase word of letters (one internal hyphen or apostrophe allowed). A row failing that is a format failure, tagged in the harness's first-failing-condition order. Ending at a probe point (an article or possessive) is reported as compliance, not as a format condition.

## 5. Estimands

Estimands 1-5 and the secondary descriptives are those of run 1, computed by the same code paths (Wilson intervals, the seeded bootstrap, Newcombe differences). Two estimands move by design and are reported as computed, with the cause named: estimand 3 (template similarity) reads higher than in run 1 because 4 templates per call are reused by the second phrasings; and in estimand 2 the clinical-term-only novelty of up to 4 of the 16 non-control rows per call cannot count as novel, because each second phrasing repeats its concept's clinical term (pair novelty and patient-term novelty are unaffected). The version-2 additions below are descriptives that `compute_summary.py` reports outside the estimands:

- Variant-design compliance: per call, adjacent pairs sharing clinical term, template and next word with a different patient term (expected 4), distinct concepts (expected 12), calls compliant over all calls with a Wilson interval, by arm.
- Probe-point compliance: the share of rows whose template ends on an article or possessive, by arm and cell.
- Next words: the number of distinct words and the most common ones.
- Checker relation, from the version-2 structured output: same, same_brand, broader, narrower, different, for generated, known-good and broken items; the yes-rate by relation; the count of entries whose `equivalent` contradicts their relation (kept and flagged); the precision view (as precise, vaguer, more specific) derived from relation.
- Checker sentence naturalness and patient realism: distributions for generated rows, by arm.

## 6. Checker validation with known truth

As run 1: the checker set is every format-valid generated row with `control: "none"`, the 10 known-good seed rows, and 20 deliberately broken pairs (a target row's clinical term and template with another row's patient term from the same cell); blinded, shuffled, batches of 30, each a separate subagent; sensitivity on known-good and specificity on broken, with `unclear` counted as a miss and excluded. The checker answers per item: `equivalent`, `relation`, `sentence_natural`, `patient_realism` and a one-line reason, through the version-2 structured-output schema; an entry with a value outside a field's set is invalid and its item is missing, as for an invalid reason in run 1.

Decisions taken before this run, recorded in codebook v0.2 (`pilot/codebook/`): whether two phrases name the same thing is settled by standard medical terminology on the owner's instruction of 2026-10-02 (rules L0-L6); a broader patient phrase counts as equivalent for a stimulus and is labelled vaguer (L3, R6); a brand name of a single-ingredient drug is the same thing (L2); "unclear" means undecidable meaning only (R9). A patient's description of a diagnosis is not equivalent until the owner decides otherwise (codebook O1).

## 7. Human review sheet

40 checked generated rows, at most one per concept (concept = call, surface form of the clinical term, template), allocated to arms in proportion to their concepts by largest remainder, drawn with the `review` stream (concepts first, then one row of each), then shuffled and relabelled r001 to r040, with the checker's answers withheld in `review_sheet.csv` and kept in `review_key.csv`. The owner reviews them blind on the private review page, which stores this run's answers under its own run id. Agreement between the owner and the checker is computed after the review, outside this run's summary (the summary hashes the review sheet before it is filled).

## 8. Randomness

Master seed 20260929, the harness constant, with the same named streams as run 1. With the same seed file, arm A draws the same exemplars as run 1, so the two runs differ in the prompts and the harness, not in the exemplars. Generation and checker subagents are language-model calls and are not reproducible bit for bit; their raw outputs are kept verbatim.

## 9. Order of operations

Every script runs with `PILOT_DIR` set to this run directory (`pilot/runs/pilot_v2_20261002/` in the repository working copy), under Python 3.13.4: the harness refuses to recompute a sealed run across the Python 3.12 change to `sum()`, so the same interpreter seals and later re-checks this run.

1. Write this protocol and HANDOFF.md (with its results markers) and manifest_model.json.
2. `plan_calls.py`; `write_manifest.py` (freezes this protocol, the model facts, the inputs and the scripts).
3. `make_workflow_scripts.py generation`; run the generation workflow; `extract_workflow_journal.py generation`; copy the journal to `workflows/generation.journal.jsonl`; `parse_generation.py`.
4. `build_checker_set.py`; `make_workflow_scripts.py checker`; run the checker workflow; `extract_workflow_journal.py checker`; copy the journal; `parse_checker.py`.
5. `make_review_sheet.py`; `compute_summary.py`; `record_run.py` for both stages; `write_manifest.py finalize`.
6. Holdout seal check over this run directory; it must be CLEAN before anything leaves the laptop.

After finalize, two downstream consumers read this run without changing it: the review page bundle, and `pilot/analysis/trace_pairs.py`, which turns the review sample into a circuit-trace pairs file. Tracing those pairs on the circuit-trace lane (output root `pilot/traces/`) is a pipeline check of traceability: what share of the pairs keep a measurable target at a 0.02 screen. Its numbers are never measurements of the study's models.

## 10. Limitations fixed in advance

- The generator and the checker are subagents of the same model family in the same session; the checker is independent in information, not in model identity.
- Subagent execution adds a harness system prompt and injected repository instructions that a bare API call would not carry; numbers characterise this execution path.
- Several things change at once relative to run 1 (prompt rules, terminology guidance, probe-point endings, the second phrasings, the checker's questions); a difference between the runs cannot be assigned to one of them.
- The checker's new judgements (relation, naturalness, realism) have no truth set in this run other than the owner's later review of 40 rows.
- The terminology rulings rest on standard terminologies, not on a clinician; clinician review is pending (codebook O2).
