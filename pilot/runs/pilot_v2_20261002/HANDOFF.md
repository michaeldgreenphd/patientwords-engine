# Handoff: pilot run 2 (version-2 prompts and harness), 2026-10-02

This file describes the run in this directory as it proceeds. The protocol (`PROTOCOL.md`) was written and frozen before any generation call; deviations from it are recorded here.

## Execution path

Claude Code in VS Code on the owner's laptop, in the owner's interactive session, which the owner asked on 2026-10-02 to set forward a second pilot stimulus run and its circuit tracing while they slept. Generation and checker calls are Workflow tool subagents; the scripts are the pilot harness at version 2 (commit 58e487db on branch claude/pilot-prompts-v2, pull request #69), run from branch claude/pilot-run2. No repository script called a paid provider API for this run: subscription usage in the owner's session is not provider spend.

## Assumptions and notes, in order

1. Seeds: the 26 cases of run 1, byte-identical (sha256 095820fe...).
2. The run kit was copied from `pilot/prompts_v2/` unchanged: `design.json` (harness_version 2), `prompts/generation_prompt.txt`, `prompts/checker_prompt.txt`.
3. Model facts are in `manifest_model.json`; the running Claude Code version is not certain (see its source field).
4. Planning: `plan_calls.py` and the plan-time `write_manifest.py` ran at 2026-10-02T07:10Z (protocol unchanged; 18 calls, K = 8, harness_version 2). The seeds and the master seed are run 1's, so arm A drew the same exemplars as run 1.
5. Generation: Workflow run `wf_27c0be1e-c6e`, launched with the run directory's own `workflows/generation.workflow.js` (the Workflow tool accepted the scratchpad worktree path, so no copy was needed). 18 subagents, no retries, no tool use, 755,332 subagent tokens, about 24 minutes wall clock at the tool's concurrency limit of 8 (not measured further). The subagents inherit the session's reasoning-effort setting, which this session cannot read; the long per-call times suggest a high setting (unverified). `extract_workflow_journal.py` found 18 items and 18 results; the journal was copied byte-identical to `workflows/generation.journal.jsonl`; `parse_generation.py` validated 360 of 360 lines with no format failure.
6. Checker: Workflow run `wf_1ff11e4c-10f` over 318 items (288 generated, 10 known-good, 20 broken) in 11 batches: 11 subagents, no retries, 472,789 subagent tokens, about 9 minutes. The journal was copied byte-identical to `workflows/checker.journal.jsonl`; `parse_checker.py` accepted all 318 answers under the version-2 schema (none missing, none flagged inconsistent).
7. Model evidence: `record_run.py` matched every started agent to its transcript; all 29 report `claude-opus-5-5` (36 model records for generation, 22 for the checker).
8. Review sample: drawn one row per concept, 20 per arm from 108 concepts per arm (9 calls x 12 concepts), 40 distinct concepts.

## Reading of the results (hand-written, outside the results block)

- Every structural requirement of version 2 held: 360 of 360 rows valid, 72 of 72 controls faithful, every template ending on a probe word, and all 18 calls with exactly 4 adjacent second phrasings and 12 concepts.
- The checker's new answers sit at the ceiling: it called every generated sentence natural with both phrases (288 of 288) and every patient phrase but one real (287 of 288). On run 1 the owner judged 52% of sentences natural with both phrases and 48% of patient phrases real. Either version 2 closed that gap, or the checker cannot tell good from poor on these two questions. The owner's blind review of this run's 40 sampled pairs is the test; `pilot/analysis/review_agreement.py` computes the agreement once the review is exported.
- The checker's sensitivity on the 10 real seed pairs is again 5 of 10, as in run 1: it still rejects half of the hand-built patient-language pairs.
- 50 of the 288 generated pairs swap a single-ingredient brand name for its generic (relation same_brand), about half of the medication rows. Rule L2 counts them as the same thing; whether brand-for-generic pairs should be capped is a design question for the owner, because such a pair may measure brand-versus-generic wording rather than register.
- Targets are concentrated: `doctor` is the next word of 136 of 360 rows, then hospital (53), ambulance (21) and pharmacy (19). These are care-seeking words, which suits the study's urgency measures, but a trace of these pairs mostly measures one or two target words.

## What happens next (downstream consumers; they do not change this run)

- The review page shows this run's 40-row sample under its own run id.
- `pilot/analysis/trace_pairs.py --review-sample` turns the 40 sampled pairs into a circuit-trace pairs file (target = a space plus `next_word`), traced at $0 under the circuit-trace lane's pilot output root as a pipeline check of traceability. Its results are never measurements.

## Results

<!-- results:begin -->
(written by `scripts/compute_summary.py` from `summary.json`; finalize refuses a handoff whose block differs)

- **Run:** 18 calls, 18 attempts, 0 retried, 0 without a response record; calls with a valid row 18 / 18 = 1.000 [0.824, 1.000].
- **Estimand 1, format validity (final attempts):** 360 / 360 = 1.000 [0.989, 1.000]; Arm A 180 / 180 = 1.000 [0.979, 1.000]; Arm B 180 / 180 = 1.000 [0.979, 1.000].
- **Negative controls:** 72 returned (72 expected), 0 unmeasurable; faithful 72 / 72 = 1.000 [0.949, 1.000].
- **Estimand 2, novelty (pair key):** Arm A 144 / 144 = 1.000 [0.974, 1.000]; Arm B 142 / 144 = 0.986 [0.951, 0.996]; pooled 220 / 288 = 0.764 [0.712, 0.809]; 0 rows duplicate a seed pair.
- **Estimand 3, diversity (mean pairwise TF-IDF cosine of templates; lower is more diverse):** within cells Arm A 0.116 [0.102, 0.133], Arm B 0.122 [0.105, 0.139]; generated versus seed templates Arm A 0.041 [0.038, 0.043], Arm B 0.038 [0.035, 0.040]; 2000 bootstrap resamples.
- **Estimand 4, semantic equivalence:** judged yes 280 / 288 = 0.972 [0.946, 0.986]; verdict counts {"no": 8, "yes": 280}; missing 0; Arm A 139 / 144 = 0.965 [0.921, 0.985]; Arm B 141 / 144 = 0.979 [0.941, 0.993]. Checker sensitivity on known-good rows 5 / 10 = 0.500 [0.237, 0.763]; specificity on broken pairs 19 / 20 = 0.950 [0.764, 0.991] (unclear counts as a miss).
- **Estimand 5, Arm A minus Arm B:** novelty +0.014 [-0.014, +0.049] (Newcombe); within-cell similarity -0.006 [-0.030, +0.019] (bootstrap); similarity to seeds +0.003 [-0.000, +0.007] (bootstrap); equivalence -0.014 [-0.060, +0.030] (Newcombe).
- **Checker relation (version 2), generated rows:** {"same": 121, "same_brand": 50, "broader": 109, "narrower": 1, "different": 7}; precision as precise 171, vaguer 109, more specific 1, not applicable 7; answers whose equivalent contradicts their relation (kept, flagged inconsistent) 0.
- **Checker sentence and realism (version 2), generated rows:** sentence_natural {"both": 288, "clinical_only": 0, "patient_only": 0, "neither": 0}; patient_realism {"real": 287, "textbook": 1, "unlikely": 0}.
- **Probe point (descriptive, not a format failure):** templates ending on a probe word 360 / 360 = 1.000 [0.989, 1.000]; Arm A 180 / 180 = 1.000 [0.979, 1.000]; Arm B 180 / 180 = 1.000 [0.979, 1.000].
- **Variant design (descriptive):** calls with exactly 4 adjacent variant pairs and 12 concepts 18 / 18 = 1.000 [0.824, 1.000]; Arm A 9 / 9 = 1.000 [0.701, 1.000]; Arm B 9 / 9 = 1.000 [0.701, 1.000]; adjacent variant pairs 72 (clinical term exact), 72 (clinical term equal in surface form); 0 call(s) flagged.
- **next_word:** 50 distinct words over 360 rows; most common: doctor (136), hospital (53), ambulance (21), pharmacy (19), bathroom (15), antacid (8), dentist (8), pharmacist (8), appointment (6), surgeon (6).
<!-- results:end -->

## Deviations

None so far.
