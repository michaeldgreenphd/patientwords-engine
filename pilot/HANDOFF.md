# HANDOFF: stimulus-generation pilot (measurement validity), run 2026-09-29

## Assumptions made (every one of them)

1. **No seed cases were attached.** The task said to fall back to 6 clearly labeled synthetic placeholders, so `seeds.json` holds 6 cases written by the agent, each marked `provenance: synthetic placeholder, not study data`. Every number in this run is a check of the pipeline, not a result about the study's stimuli. The field mapping is the identity (`clinical_term`, `patient_term`, `template`, blank marker `___`); the extra fields `id`, `specialty`, `swap_type` label the seeds only.
2. **Exemplars per call: K = min(8, number of seeds) = 6.** With 6 seeds, 8 cannot be sampled without replacement, so both arms show all six seeds and differ only in exemplar order (Arm A: a seeded random order per call; Arm B: file order in every call). Estimand 5 in this run therefore measures order sensitivity, not exemplar-set sensitivity. The scripts sample 8 unchanged once 8 or more seeds exist (checked in `scripts/selftest.py`).
3. **Known-good rows: 6, not 10**, for the same reason. The sensitivity interval is correspondingly wide.
4. **"20 rows each, including 4 negative controls"** was read as 20 rows in total: 16 with `control: "none"` and 4 with `control: "negative"`.
5. **A row is one non-empty line of the response.** A row is format-valid when it is a JSON object with the keys `clinical_term`, `patient_term`, `template`, `control`, the three text fields are non-empty strings, the template holds exactly one `___`, and `control` is `none` or `negative`. Code fences, commentary, and numbering would count as rows and as format failures. No line was repaired.
6. **Failed call = the subagent returned nothing, or no line carried the four required keys.** Retry once with the identical prompt; the final attempt is analysed and the first is logged. A call with fewer than 20 rows or some invalid rows is not retried.
7. **Negative controls are excluded** from novelty, diversity, and the checker set; they are reported separately (count, and fidelity: whether the two terms are identical after removing casing, punctuation, and spacing).
8. **Novelty key** is the (clinical_term, patient_term) pair, compared exactly after lowercasing. Primary reporting is per arm (each arm against the seeds and its own earlier rows, cells in fixed order, then line position), so the arm comparison is symmetric; the pooled number (cells in order, Arm A before Arm B) is secondary. Single-field novelty is also reported.
9. **TF-IDF** is scikit-learn's default re-implemented in the standard library (tokens of two or more word characters, lowercase, raw counts, smooth idf, L2 norm), the blank marker removed before tokenising, fitted once on all non-control generated templates from both arms plus the seed templates.
10. **Intervals.** Wilson for proportions; Newcombe method 10 for differences of proportions; a Wilson interval does not apply to a mean, so estimand 3 carries a 95% percentile bootstrap interval (2000 resamples). In the bootstrap of within-cell similarity, only pairs of distinct original rows are counted (a resample repeats rows; a pair of copies is not a pair of distinct rows). See Deviations, item 1.
11. **The checker** returns verdicts through a structured-output schema, because its format is not an estimand. It sees only opaque ids and the three fields, in shuffled batches of 30, one fresh subagent per batch. A batch returning nothing would be retried once; ids without a usable verdict would be `missing`.
12. **Broken pairs** re-pair a target row's `patient_term` with a donor from the same cell (both arms pooled) whose clinical and patient terms both differ from the target's. "Known mismatch" holds by construction only; it was not verified by a person. This mattered once (Results, specificity).
13. **Execution path.** Generation and checking ran as Claude Code subagents launched by the Workflow tool, inheriting the session model `claude-fable-5-1` (the subagent transcripts report only that model id: 36 occurrences across the 18 generation transcripts, 22 across the 11 checker transcripts). The harness adds its own system prompt and injects the three repositories' `AGENTS.md`; the recorded prompt hashes cover only the user-turn prompt. This is not the same as a bare Messages API call, and numbers from one path should not be assumed to transfer to the other.
14. **Randomness.** Exemplar sampling used `random.Random(20260929)` exactly. Broken-pair construction, checker shuffling, review sampling, and the bootstrap use named streams `random.Random("20260929:<purpose>")`. Model outputs are not bit-reproducible; every raw response is kept verbatim under `generated/raw/`.
15. **Model for the request builder** (`scripts/build_api_requests.py`) is a required argument with no default. This run's model is in `manifest.json`; choosing another is a decision about the execution path, not a default to bury in a script. The builder sends nothing (Review round 1, item 8).
16. **Human review sheet** draws from the checked generated rows, 20 per arm (proportional allocation of 40 across two equal arms), in a seeded random order relabelled `r001` to `r040`. `review_key.csv` has exactly the four columns asked for; `review_map.json` holds the review-id to row-id map so the two files can be joined later.
17. **Sensitivity and specificity** are reported with `unclear` counted as a miss (primary) and excluded (secondary); this run produced no `unclear` on the known-good or broken rows, so both readings coincide.
18. **Concurrency.** The container has 4 CPUs, so the Workflow tool ran two subagents at a time. Each subagent still saw only its own prompt; the order of completion does not enter any estimand.
19. **Location.** `pilot/` sits outside the three repository checkouts. Nothing was committed or pushed anywhere; the deliverable is this directory and its zip.
20. **Holdout seal.** Because the generated rows are medical phrases produced inside a session that also holds the study's repositories, the engine's holdout seal check was run over `pilot/` (with the engine's `docs/` and `ops/`): CLEAN, 183 sealed phrases, no hits.

## What ran

| Step | Detail |
|---|---|
| Protocol | `PROTOCOL.md` written 21:41 UTC before any call; SHA-256 recorded in `manifest.json` and unchanged at finalisation (`protocol_unchanged: true`). |
| Plan | `scripts/plan_calls.py`: 18 calls, 6 exemplars each, prompt SHA-256 per call in `calls.json`. The workflow script embeds the prompts; every embedded prompt was checked against its recorded hash before launch. |
| Generation | Workflow run `wf_028d99f0-c28`: 18 subagents, 18 done, 0 errors, 0 empty results, 0 tool uses, 524 s, 1,164,513 subagent tokens. Every call returned exactly 20 lines on the first attempt; 0 retries. |
| Parse | `scripts/parse_generation.py`: 360 lines, 360 format-valid rows, 0 failures; 72 negative controls, 72 faithful. |
| Checker set | `scripts/build_checker_set.py`: 288 generated + 6 known-good + 20 broken = 314 blind items in 11 batches. |
| Checker | Workflow run `wf_453aa937-aff`: 11 subagents, 11 done, 0 errors, 260 s, 710,273 subagent tokens, one structured-output call each. 314 of 314 ids received a valid verdict; 0 foreign, duplicate, or invalid entries. |
| Review sheet | `scripts/make_review_sheet.py`: 40 rows, 20 per arm. |
| Summary | `scripts/compute_summary.py` wrote `summary.json` and `summary.md`. No number in this handoff was typed from memory; each is copied from those files. |

## Results in brief (all from `summary.md`)

- **Estimand 1, format validity:** 360 / 360, Wilson [0.989, 1.000]; identical in both arms and every cell.
- **Negative controls:** 72 returned (72 expected), 72 / 72 faithful, [0.949, 1.000].
- **Estimand 2, novelty (pair key):** Arm A 143 / 144 = 0.993 [0.962, 0.999]; Arm B 144 / 144 = 1.000 [0.974, 1.000]; 0 rows duplicate a seed pair. Pooled across arms 251 / 288 = 0.872 [0.828, 0.905]: 36 pairs recur, nearly all the same pair generated by both arms of the same cell (for example `myocardium | heart muscle` first in both cardiology body-part calls).
- **Estimand 3, diversity (mean pairwise TF-IDF cosine of templates, lower is more diverse):** Arm A 0.070 [0.061, 0.081]; Arm B 0.075 [0.065, 0.087]. Generated versus seed templates: A 0.060 [0.055, 0.065]; B 0.065 [0.060, 0.072].
- **Estimand 4, semantic equivalence:** 280 / 288 judged `yes` = 0.972 [0.946, 0.986]; 3 `no`, 5 `unclear`, 0 missing. Arm A 142 / 144 = 0.986 [0.951, 0.996]; Arm B 138 / 144 = 0.958 [0.912, 0.981]. Checker sensitivity on the 6 known-good rows 6 / 6 = 1.000 [0.610, 1.000]; specificity on the 20 broken rows 19 / 20 = 0.950 [0.764, 0.991].
- **Estimand 5, Arm A minus Arm B:** novelty -0.007 [-0.038, 0.020]; within-cell similarity -0.005 [-0.019, 0.009]; similarity to seeds -0.005 [-0.013, 0.002]; equivalence +0.028 [-0.014, 0.075]. Every interval includes zero; no decision rule was applied.

Things in the data worth your attention, with the reason each matters:

- **Both arms produce the same concepts.** 36 of 144 Arm B pairs also appear in Arm A, and the first row of each cell is often identical across arms. With identical exemplar sets (assumption 2) and one prompt per cell, the model converges on the canonical concepts of the cell. Two consequences: the arm contrast in this run is close to null by construction, and repeated calls per cell will show falling novelty. Before scaling to more rows per cell, measure novelty across repeated calls of one cell.
- **`unclear` verdicts cluster in medication cells** (neurology 2, gastroenterology 2, plus 1 body part): the lay term names a purpose (`my nerve pain pills`, `a heartburn tablet`) rather than the drug. That is a property of the register, not of the checker: lay medication vocabulary is often indication-level. The study needs a stated rule on whether indication-level equivalence counts as the same concept; the checker prompt currently leaves it to the checker.
- **The one specificity miss** (`a bulk-forming laxative | fiber powder`, c0066) is a broken pair whose donor row named the same drug class, so the pair was not in fact a mismatch. The construction guarantees different generated rows, not different concepts (assumption 12). A donor from a different cell, or a person confirming each broken pair, would give a cleaner specificity number.
- **Two "no" verdicts are one pair generated by both arms** (`mitral valve | valve on the left side of the heart`): the checker held that the lay phrase does not distinguish mitral from aortic. Whether that is a generation error or an acceptable lay approximation is the same rule question as above.
- **Format validity of 1.000 belongs to this execution path.** The harness prompt may contribute to the model returning clean JSON lines; do not assume the bare API path matches it without measuring.

## Failures

None. 0 retries, 0 null returns, 0 format failures, 0 missing verdicts, 0 subagent errors.

## Deviations from PROTOCOL.md and from the task

1. **Analysis-code correction after the first computation (script only; the protocol text is unchanged, hash verified).** The first version of `compute_summary.py` counted pairs of copies of the same row in the bootstrap resamples, which put the within-cell similarity intervals above their point estimates (Arm A [0.114, 0.145] against 0.070). The protocol defines the statistic over pairs of distinct rows, so the bootstrap now counts only pairs of distinct original rows. Point estimates did not change; only the estimand 3 intervals did. No prompt was changed at any point after a result was seen.
2. **6 exemplars and 6 known-good rows instead of 8 and 10** (assumptions 2 and 3), forced by the 6-seed fallback and recorded in the protocol before generation.
3. **`review_map.json`** is an extra file beside the two review files asked for, so the review ids can be joined back to rows.

## First three things to do on your laptop

1. **Replace `seeds.json` with the real seed cases** (8 or more; 10 or more gives the full known-good set), keeping the field names or editing the `field_mapping` note. Then run `python3 scripts/selftest.py`, `python3 scripts/plan_calls.py`, and `python3 scripts/write_manifest.py`; confirm `calls.json` shows `k_exemplars_used: 8` and that the seal check, if the seeds are study data, is run on the whole directory before anything leaves the machine.
2. **A rerun needs a sanctioned execution path first.** This run was executed as Claude Code subagents (assumption 13), which is outside the engine's push-to-run lanes; under the execution model (nothing paid or networked runs locally, all generation through push-to-run CI) the sanctioned route for any rerun, generation or checker, is a pilot push-to-run lane, which does not exist yet. `python3 scripts/build_api_requests.py generation --model <id>` writes the exact request bodies, the retry rule and the result-file shape such a lane needs, and sends nothing. Until the lane exists there is no sanctioned way to rerun generation or the checker; the scripts under `workflows/` document how this run was produced, not a route to repeat it.
3. **Once results arrive from the lane**, run `python3 scripts/parse_generation.py <result file> --replace`, `build_checker_set.py`, then `build_api_requests.py checker --model <id>` for the checker's requests through the same lane, `parse_checker.py <result file>`, `make_review_sheet.py` and `compute_summary.py`. Fill in `review_sheet.csv` before opening `review_key.csv`.

## Layout

- `PROTOCOL.md` (frozen), `manifest.json` (model, dates, seeds, prompt and script hashes, run records, output hashes), `manifest_model.json` (the session facts the manifest reads).
- `seeds.json`, `prompts/`, `calls.json` (rendered prompts and hashes), `checker_batches.json`.
- `scripts/`: `common.py`, `plan_calls.py`, `make_workflow_scripts.py`, `extract_workflow_journal.py`, `parse_generation.py`, `build_checker_set.py`, `parse_checker.py`, `make_review_sheet.py`, `compute_summary.py`, `write_manifest.py`, `record_run.py`, `build_api_requests.py` (request bodies only, nothing sent), `selftest.py`.
- `workflows/`: the two Workflow scripts as run, and the two run journals copied from the transcript directory.
- `generated/`: one JSONL per call (valid rows), `all_rows.jsonl`, `format_failures.jsonl` (empty), `raw/` (verbatim responses).
- `call_log.jsonl`, `workflow_generation_result.json`, `workflow_checker_result.json`, `checker_set.jsonl` (blind), `checker_key.jsonl` (truth), `checked.jsonl`, `checker_log.jsonl`, `review_sheet.csv`, `review_key.csv`, `review_map.json`, `summary.json`, `summary.md`.
- Not included: the subagent transcripts (they carry the harness prompt and the injected repository instructions); their directory paths are in `manifest.json`.

## Post-run edits (2026-09-29, before code review)

After the run, and before this directory was committed for review, the scripts were linted against the engine repository's ruff configuration: import order, `ValueError` instead of a blind `Exception` around JSON parsing, file reads through `pathlib`, one dictionary iteration, one unused variable, and an explicit `check` flag on `subprocess.run`. The bootstrap correction of Deviations item 1 gained a regression check in `scripts/selftest.py` (each bootstrap interval must contain its point estimate), `tests/test_pilot_selftest.py` runs the self-test inside the engine's pytest suite with `PILOT_N_BOOT=200`, and `common.py` reads that variable (default 2000, the protocol's value). No computation changed: `summary.md` was recomputed after the edits and is byte-identical to the run's, and `manifest.json` was re-finalized so its script hashes match the committed files.

## Review round 1 (PR #52, Codex on 4f6c028e)

Seven findings were verified against the files and fixed; every number in `summary.json` is unchanged (checked field by field), and `summary.md` differs only by the lines the fixes add.

1. The design factors (specialties, swap types and their prompt definitions) moved from `scripts/common.py` to `design.json`, which `common.py` loads; the rendered prompts and their hashes in `calls.json` are byte-identical. `manifest.json` records the file's hash.
2. A planned call with no response record is now a final, failed call in `call_log.jsonl` (zero lines, status `no_response_recorded`), so it stays in the call-level denominators and appears in the per-call table; `compute_summary.py` refuses a call log whose final records do not match the planned calls.
3. `summary.json` records the master seed and every named random stream (`seeds`), and `summary.md` names the bootstrap stream.
4. `parse_generation.py` refuses to write over outputs of a previous parse unless `--replace` is passed, which deletes them first and reports the count; a stale attempt file can no longer be hashed into a later manifest.
5. Broken-pair targets are sampled only from rows that have an eligible donor; this run's checker set, key and batches are byte-identical under the new rule.
6. The bootstrap for estimand 3 keeps the cell set fixed (cells with at least two rows); a replicate in which a cell resamples to copies of one row is skipped and counted (`n_undefined_replicates`, reported in the summary) instead of being averaged over fewer cells. In this run every cell has 16 rows and no replicate was undefined.
7. The summary's markdown helpers carry type annotations.

Each fix has a check in `scripts/selftest.py` (design factors load from data; a call left out of the result counts 17 / 18; a second parse is refused without `--replace`; the eligible-target rule on a three-row example; a two-row cell producing undefined replicates that are counted, with the cell set fixed).

8. The live Messages API path was removed. Codex's answer to the direct question: under the engine's execution model (nothing paid or networked runs locally; all generation through push-to-run CI; spend journaled by `fire_trigger.py`) a laptop driver is not compliant, and an opt-in gate with a provenance stamp would not make it so; only an amendment to `AGENTS.md` could. `scripts/run_api.py` became `scripts/build_api_requests.py`, which writes the exact request bodies and the result-file shape for a future pilot push-to-run lane and sends nothing. The task that produced this pilot asked for a laptop rerun; the owner can still choose that route by amending `AGENTS.md`, in which case the removed send path is in the PR's history (commit 819b67ba).

## Review round 2 (PR #52, Codex on 64c3844d)

9. The manifest and the summary header no longer state the seeds' provenance as a fixed string: both read the `provenance` field of every seed in `seeds.json` (a seed without one is reported as MISSING, never assumed) and the manifest keeps the file's own note, so a rerun with real seeds records theirs.
10. `surface_key` keeps letters and digits of every script (Unicode-aware) and removes only casing, punctuation and spacing, as the protocol states; for this run's ASCII rows nothing changes (control fidelity and the checker set are byte-identical).
11. The checker result-file contract in `build_api_requests.py` shows the verdict objects the parser needs and says an unsuccessful attempt sets `result` to null.
12. Steps 2 and 3 above no longer present a local Workflow rerun as a route: this run's execution path is recorded as a fact (assumption 13), and any rerun waits for a pilot push-to-run lane. Whether the run already recorded here is acceptable as a pilot artifact under the execution model is a question put to Codex on the PR; the owner decides.
