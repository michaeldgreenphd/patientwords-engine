# Protocol: stimulus-generation pilot (measurement validity)

Written 2026-09-29 before any generation call. Frozen after writing: its SHA-256 is recorded in manifest.json at write time and checked again at the end of the run. Deviations from this protocol are recorded in HANDOFF.md, never here.

## 1. Purpose and scope

This pilot measures whether a stimulus-generation loop produces usable clinical-versus-lay stimulus pairs. It reports properties of the generated rows and of the checker that judges them. It is not an effect analysis: no next-token measurement, no layer tracing, no jlens, and no decision rules. Results are described, not adjudicated.

## 2. Inputs

- Seed cases: `seeds.json`. Nothing was attached to the task, so the file holds 6 synthetic placeholder cases written by the agent, each labeled `provenance: synthetic placeholder, not study data`. Field mapping is the identity: `clinical_term`, `patient_term`, `template` with the blank marker `___`. The extra fields `id`, `specialty`, `swap_type` label the seeds and are not shown to the generator beyond the three content fields.
- Exemplars per call: 8 requested. K = min(8, number of seeds). With 6 seeds, K = 6 (see section 10).

## 3. Design

- Cells: specialty {cardiology, neurology, gastroenterology} x swap type {symptom description, body part, medication} = 9 cells. Cell order is fixed as listed (specialty-major).
- Arms: A = K seed exemplars sampled without replacement per call; B = the same fixed K exemplars in every call (the first K seeds in file order).
- Calls: one per cell per arm, 18 in total, each asking for 20 rows: 16 rows with `control: "none"` and 4 negative-control rows with `control: "negative"`. A negative-control row holds the same concept in the same register in both term fields, differing only in casing, punctuation, or spacing.
- Prompts: one generation prompt template (`prompts/generation_prompt.txt`) rendered per call with the cell, the swap-type definition, and the arm's exemplars rendered as JSON lines; one checker prompt template (`prompts/checker_prompt.txt`) rendered per batch. Template and rendered-prompt SHA-256 values are recorded in `calls.json`, `checker_batches.json`, and `manifest.json` before the calls run. Prompts are not changed after any result is seen.
- Execution: each call is a separate Claude Code subagent launched through the Workflow tool, with no access to any other call's prompt or output. The subagent inherits the session model recorded in `manifest.json`. The subagent's system prompt and any repository instructions injected by the harness are outside this pilot's control; the recorded prompt hashes cover only the user-turn prompt. Generation calls use no output schema, so format validity measures the model's raw text.
- Retry rule: a call has failed when the subagent returns nothing, or when no returned line parses as a JSON object carrying the four required keys. A failed call is retried once with the identical prompt. Both attempts are logged verbatim; the final attempt is the one analysed. A call with fewer than 20 rows, or with some invalid rows, is not a failed call and is not retried.
- No repair: a line that does not validate is counted as a format failure and kept verbatim in `generated/format_failures.jsonl`. Code fences, commentary, and numbering lines are lines and therefore count.

## 4. Row format and validity

A row is one non-empty line of the response (surrounding whitespace stripped). A row is format-valid when all of the following hold: it parses as a JSON object; it has the keys `clinical_term`, `patient_term`, `template`, `control`; the three text fields are non-empty strings; `template` contains the blank marker `___` exactly once; `control` is `"none"` or `"negative"`. Extra keys are ignored. Each failed row is tagged with the first failing condition in that order.

## 5. Estimands

Proportions are reported with 95% Wilson score intervals (z = 1.959964). Means are reported with 95% percentile bootstrap intervals (2000 resamples, seeded, see section 8); the Wilson interval does not apply to a mean and is not used for estimand 3. Differences of proportions are reported with Newcombe (1998) method 10 intervals. All numbers come from `scripts/compute_summary.py`.

1. Format validity. Numerator: format-valid rows. Denominator: all rows of the final attempt of every call. Reported overall, by arm, and by cell, with the count of each failure reason. Secondary: the same proportion pooled over all attempts including retried first attempts.
2. Novelty. Population: format-valid rows with `control: "none"`. Duplicate key: the pair (`clinical_term`, `patient_term`), compared exactly after lowercasing both strings. A row is novel when its key matches no seed pair and no earlier row. Order: within an arm, rows are ordered by cell (fixed order), then by line position in the response. Primary reporting is per arm, each arm compared with the seeds and with that arm's own earlier rows, so the arm comparison in estimand 5 is symmetric. Secondary: pooled over both arms with rows ordered by cell, then Arm A before Arm B, then line position; and single-field novelty (`clinical_term` alone, `patient_term` alone) per arm.
3. Diversity. Population: templates of format-valid rows with `control: "none"`. Representation: word-unigram TF-IDF (tokens of two or more word characters, lowercased, the blank marker removed before tokenising; raw term counts; idf = ln((1 + N) / (1 + df)) + 1; L2-normalised), fitted once on all such templates from both arms plus the seed templates. Within-cell diversity: for each cell and arm, the mean cosine similarity over all unordered pairs of distinct rows (cells with fewer than 2 rows report no value). Arm summary: the unweighted mean of the cell means over cells with at least 2 rows. Generated-versus-seed similarity: for each arm, the mean cosine over all (generated row, seed) pairs. Bootstrap: rows are resampled with replacement within each cell, jointly for both arms in each iteration, and the same iterations give the arm intervals and the interval for the A minus B difference. Lower similarity means more diverse; the pilot reports the similarity itself.
4. Semantic equivalence. Population: format-valid rows with `control: "none"` that received a checker verdict. Numerator: verdict `yes`. Denominator: verdicts in {yes, no, unclear}; items with no usable verdict are counted and reported as missing, not in the denominator. Also reported: the proportion `unclear`. This estimand is reported only alongside the checker's sensitivity on the known-good rows and specificity on the broken rows (section 6), each with a Wilson interval, both with `unclear` counted as a miss and with `unclear` excluded.
5. Exemplar sensitivity. Arm A minus Arm B on estimand 2 (pair novelty, Newcombe interval), estimand 3 (within-cell mean similarity and generated-versus-seed similarity, bootstrap intervals from section 5.3), and estimand 4 (proportion `yes`, Newcombe interval). Per-arm values are shown beside each difference. No threshold is applied.

Secondary descriptives, reported in the same document: the number of negative-control rows returned and the proportion whose two terms are identical after removing casing, punctuation, and spacing (control fidelity); the proportion of calls that returned at least one valid row; lines returned per call against the 20 requested; per-cell tables for estimands 1, 3, and 4.

## 6. Checker validation with known truth

- Checker set: every format-valid generated row with `control: "none"` from both arms; the known-good rows, which are the first min(10, number of seeds) seed cases (with 6 seeds, 6 rows); and 20 deliberately broken pairs. Negative-control rows are excluded from the checker set.
- Broken pairs: 20 rows are allocated across the 9 cells as 2 per cell plus 2 cells drawn at random for a third. Within each cell, target rows are drawn at random from that cell's generated non-control rows (both arms pooled); each target keeps its `clinical_term` and `template` and takes the `patient_term` of a donor row drawn at random from the same cell whose `clinical_term` and `patient_term` both differ from the target's after removing casing, punctuation, and spacing. "Known mismatch" is by construction (the donor was generated for a different concept); it is not human-verified. If a cell has too few rows or no eligible donor, fewer than 20 are built and the shortfall is recorded.
- Blinding: items are shuffled with a seeded stream and given opaque ids `c0001`, `c0002`, ... in shuffled order. The checker receives only `id`, `clinical_term`, `patient_term`, `template`. The truth key is written to a separate file never shown to the checker.
- Batches: 30 items per batch in shuffled order; each batch is a separate subagent with no access to other batches. The checker returns, per id, `equivalent` in {yes, no, unclear} and a one-line reason, through a structured-output schema (the checker's format is not an estimand). A batch whose subagent returns nothing is retried once; ids still without a usable verdict are recorded as `missing`.
- Sensitivity = proportion of known-good rows with verdict `yes`. Specificity = proportion of broken rows with verdict `no`. Both reported with `unclear` counted as a miss (denominator: answered rows) and with `unclear` excluded.

## 7. Human review sheet

40 checked generated rows (`control: "none"`) are drawn at random, allocated to arms in proportion to each arm's number of checked rows (largest-remainder rounding), then shuffled, and relabelled `r001` to `r040`. `review_sheet.csv` (id, clinical_term, patient_term, template, my_label, my_notes) withholds the checker verdict, arm, and cell; `review_key.csv` (id, arm, cell, checker_verdict) holds them; `review_map.json` maps review ids to generated row ids. Agreement is not computed in this pilot.

## 8. Randomness

Master seed 20260929. Exemplar sampling for Arm A uses `random.Random(20260929)` exactly, consuming one draw of K seeds per cell in fixed cell order. Every other draw uses a named stream `random.Random("20260929:<purpose>")` with purposes `broken`, `checker_shuffle`, `review`, `bootstrap`. Generation and checker subagents are language-model calls and are not reproducible bit for bit; their raw outputs are kept verbatim so every downstream number can be recomputed from them.

## 9. Order of operations

1. Write this protocol; hash it into `manifest.json`.
2. `scripts/plan_calls.py`: sample exemplars, render and hash the 18 prompts.
3. Run the 18 generation subagents (Workflow tool), with the retry rule of section 3.
4. `scripts/parse_generation.py`: validate rows without repair; write raw and parsed files and the call log.
5. `scripts/build_checker_set.py`: build, blind, shuffle, and batch the checker set.
6. Run the checker subagents (Workflow tool); `scripts/parse_checker.py`.
7. `scripts/make_review_sheet.py`; `scripts/compute_summary.py`.
8. Write `HANDOFF.md`, finalise `manifest.json`, verify the protocol hash, zip.

## 10. Limitations fixed in advance

- With 6 seeds, K = 6: both arms show all six seeds, so the arms differ only in exemplar order. Estimand 5 in this run measures order sensitivity, not exemplar-set sensitivity. With 8 or more real seeds the scripts sample 8 as specified without change.
- Known-good rows number 6, not 10, for the same reason; the sensitivity interval will be wide.
- The generator and the checker are subagents of the same model family in the same session. The checker is independent in information (it sees no provenance, cell, arm, or generator output beyond the three fields) but not in model identity.
- Subagent execution adds a harness system prompt and injected repository instructions that a bare API call would not carry. Numbers from this run characterise this execution path.
- The synthetic seeds make every number in this run a pipeline check, not a study result.
