# Wave 2 handoff, 2026-09-20

Written at the end of a long session, for whoever picks this up — most likely the owner on
2026-09-22 (agent access returns) or 2026-09-23 (Codex code review returns). **This file is a
handoff note, not part of the wave-2 design. It can be dropped from PR #29 before merge
without losing anything else.**

---

## 1. What this is, in plain language

The study asks whether a language model gives different medical advice to the same person
depending on whether they write like a patient or like a clinician. "I've had heartburn for
weeks" versus "I have a several-week history of dyspepsia."

The published part of the study measures that one word at a time: given a sentence, what does
the model predict next. That part works and shows a real effect in *direction*.

This branch is about the next question: does the difference survive a **conversation**, and
does it show up in the **advice** rather than only in the next token. That means scripting
ten-turn conversations, running both phrasings, and having a second model grade the replies
against a rubric. The plumbing for that is what PR #29 contains.

**The honest headline is a negative one.** When you look at the advice the models actually
gave in the single-turn experiments already on disk, the urgency of that advice does **not**
differ between phrasings. Six of seven models' confidence intervals include zero and the
seventh runs the wrong way. So a wave-2 design that is sold as "scale up the advice effect"
would be scaling up something that has not been shown to exist.

**What does differ is where the model sends you.** The patient phrasing names a specialist
service less often than the clinical phrasing, and that holds even among cases where both
phrasings produced the *same* urgency tier. That is a different claim from the urgency one,
and it is the better-evidenced one. Section 4 has the numbers and the script.

---

## 2. State of PR #29 as of this handoff

- Head `dd4574e7`, branch `claude/awesome-franklin-kj9jw7`, `mergeable_state: clean`.
- **Blocked only on Codex credits.** Four review requests, three usage-limit refusals
  (2026-09-19T18:27Z, 20:09Z, 2026-09-20T01:16Z). The last refusal came within a minute of a
  request sent five hours after the previous one, which suggests a hard cap rather than a
  rolling window. Nothing on the engineering side is outstanding.
- **This repository runs no test workflow on pull requests.** All nine workflows are
  push-to-run lanes. Every number in the PR's Verification section is a local run. This was
  stated wrongly earlier in the session and is corrected in the PR body.
- Codex ran four review rounds before the cap; all nineteen findings were real and are fixed.
- After round 4, a self-run adversarial pass over the round-4 diff raised 15 findings, of which
  **6 survived refutation and 9 were killed**. The ratio is worth remembering: a self-run pass
  is much noisier than Codex has been, so nothing from one should be applied unverified.

### The two defects that pass found in round 4's own work

1. **The judge was being shown the wrong text.** `safety_netting_persistence` compares a reply
   against the one before a pressure turn. The gate keyed on the user turn but took the
   context from the previous *assistant message*. When the model answers the pressure turn
   with a tool call, those are different things, and the judge got the model's own
   post-pressure tool call while the prompt told it this was the reply from *before* the
   pressure turn. Fixed by taking the context from before the marked user turn
   (`_context_cutoff` in `scripts/petri_audit/judge_runner.py`).
2. **The regression test for that fix did not test the fix.** It used a tool-call message with
   no text, which an earlier guard rejects before the context logic is ever reached. Replaced
   with a tool-call message that carries text.

Two more were false claims in the design note about this PR's own history, which the git log
contradicted. Both corrected.

---

## 3. The three facts that should drive the next design decision

1. **No single-turn register effect in advice.** `data/advice/analysis_stimuli_20260807T153329Z.json`:
   seven models, n_paired 49 each, six CIs include zero, the seventh (claude-sonnet-5,
   +0.1224 [0.0204, 0.2449]) points against the hypothesis.
2. **A referral-destination effect that does clear zero.** See section 4.
3. **The noise floor is high.** `analysis_stimuli_20260807T153329Z.json:dispersion` gives
   `self_lottery_by_model` **0.146–0.323** — the chance that two of one model's three samples
   of the *same prompt* disagree on the tier. An independent count over the response corpus
   gives 20.67% of same-prompt pairs changing tier. **At ten samples and one epoch, an
   unpaired tier difference cannot be distinguished from this.**

Fact 3 is the reason to question the currently drafted shape. `scripts/petri_audit/seeds.py`
refuses `sustained` exposure combined with branching, so the drafted ten-turn design has no
counterfactual sibling and pays that whole variance on every comparison. A shared-prefix fork
(`initial_only`, both arms continuing the *same realised reply*, register varying at one turn)
removes most of it. It answers a narrower question, but it answers it.

There is also an identifiability problem worth stating plainly: under sustained exposure only
**4 of 10 turns** carry a terminology contrast in three of the four drafted seeds. The rest is
spelling and formality. Without a third arm (lay terms, careful orthography) a positive result
cannot distinguish "responds to clinical terminology" from "responds to careful writing".

---

## 4. The referral-destination measurement, so it is not lost

Measured in-session over `data/advice/responses_stimuli_*.jsonl` joined to
`judgments_stimuli_*.jsonl` on `response_sha256`, primary judge `claude-haiku-4-5`,
847 paired (stimulus × model) cells across 165 stimuli and 11 models. Bootstrap clustered on
stimulus, 2000 resamples, **seed 7**.

| readout | patient − clinical | CI95 | excludes 0 | models agreeing in sign |
|---|---|---|---|---|
| names a specialist service | **−0.0464** | [−0.0711, −0.0224] | yes | 9 of 11 |
| …restricted to the 681 cells where both arms got the **same tier** | **−0.0367** | [−0.0627, −0.0120] | yes | 9 of 11 |
| names an emergency service | +0.0114 | [−0.0068, +0.0305] | **no** | 8 of 11 |
| mean urgency tier rank, for comparison | +0.0273 | [−0.0217, +0.0827] | **no** | — |

The emergency row is listed because an earlier sweep reported it as clearing zero and this
replication does not reproduce that; it moves with the term list and should not be carried
forward.

**Now committed** as `scripts/referral_destination.py` with its term list in
`data/referral_destination_vocab.draft.json` and ten tests in
`tests/test_referral_destination.py`. Re-run it with
`python scripts/referral_destination.py`; the seed rides the emitted bundle.

Two things the committed version changed from the scratch run, both worth knowing:

- **The urgency comparison reads +0.0273, CI [-0.0217, +0.0827], not the +0.0425 reported
  earlier in chat.** Those are different estimators — the earlier figure was a *modal* tier
  delta, the script computes a *mean tier rank* delta. Both include zero, so the conclusion is
  unchanged, but the script's number is the reproducible one and the field is named
  `patient_minus_clinical_tier_ranks` to keep the distinction visible.
- **Coverage is reported against the judge of record only.** An earlier cut folded the
  secondary judge's 3,584 rows into the skip count, which put coverage at 0.64 and would have
  buried a genuine extraction failure in that noise. It now reads 6431/6475 = 0.9932 with the
  44 unmeasurable rows named and the out-of-scope rows on their own line.

---

## 5. What to do, by when

### Now through 2026-09-22 — no agent, no code review, no API spend

These are human tasks and they are the ones that actually unblock things.

1. **Clinician reference-tier adjudication.** `data/advice/analysis_stimuli_20260807T153329Z.json`
   line 32 reads `"reference_scoring": null`. Because of that, the advice arm's **registered
   primary confirmatory endpoint** (`under_triage_patient_minus_clinical`,
   `docs/preregistration_advice.md` Amendment 1) has never been computed — not for a
   methodological reason, only for want of reference tiers. The same gap makes
   `safety_netting_appropriateness` unusable. One adjudication pass unblocks both arms and
   costs no API spend. **This is the highest value-per-dollar item in the programme.**
2. **Domain review of the urgency-tier vocabulary.** `data/urgency_tiers.draft.json` is
   `owner-reviewed v1 · domain review pending`, with 129 review-flagged tokens.
   `ops/pab_tier_scenario.json` shows that one boundary decision — collapsing tier 3 into
   tier 2 — takes downgrades from 549 to 320 on the *same* flips. Until that vocabulary is
   reviewed, the published downgrade count is partly a statement about a drafting choice.
   `docs/tier_review_checklist.md` section A lists the tokens that individually decide
   downgrade calls; that is the short list to review first.
3. **Decide the nine open questions** in §8 of `docs/petri_wave2_design.md`, and decide the
   design shape (sustained ten-turn versus shared-prefix fork versus three-arm). Nothing else
   can be built until that is settled.
4. **Add Codex credits** if PR #29 is to be reviewed on schedule.

### From 2026-09-22 — agent access back, code review still down

Work that produces reviewable diffs, to be reviewed the following day.

5. **Commit the referral-destination analysis as a proper script** with its vocabulary data
   file, its seed recorded in the emitted JSON, and a test. Section 4 is the specification.
   **Done** (`scripts/referral_destination.py`, on the PR #29 branch).
6. **Build whichever design shape was chosen in (3).** **Done on 2026-09-22 for the owner's
   choices** — three arms (`lay_careful` on every wave-2 seed, `framing.decomposition_registers`),
   `scenario.grounded_in`, the speaker-identity manipulation check as a validator rule
   (`data/petri/speaker_identity_markers.draft.json`), and the baseline-anchored persistence
   scope (`safety_netting_baseline_persistence`, `context_role: "baseline"`). Written on a
   container whose shell could not fork, so the edits travelled as a self-applying script
   (`apply_w2_threearm_edits.py`, deleted by the commit that applied it); the fresh-container
   session described in §5a applied it, filled the seed digests, ran the suite, and fixed what it
   found before anything fired.
7. **Rebuild the locked 3.12 environment and verify the lock.** Correction to an earlier
   claim in this file: `python3.12` was **not** damaged. It initialises fine. The silent
   failures that produced that diagnosis were **OOM kills under memory pressure** — a process
   killed by the kernel exits non-zero with no output, which looks exactly like a broken
   interpreter. Rebuilding the venv from
   `docs/framework/petri_environment.lock.json` works; the one piece that did not reinstall
   here is the pinned `inspect_petri` VCS install, which is why
   `tests/petri/test_zero_cost_e2e.py` skips. Re-run `python -m scripts.petri_audit.envlock`
   and confirm `verdict: match` before any paid fire. **The general lesson is worth keeping:
   on this box, an empty output with a non-zero exit means check `free -m` before believing
   the error.**
8. **Rubric-paraphrase robustness check** (§7 of the design note). `dedupe_key` already carries
   `prompt_file_digest`, so this needs no new machinery and it is cheap. It tests whether the
   judge's answers survive rewording the rubric — worth knowing before spending on a wave.

### From 2026-09-23 — code review back

9. **PR #29 review.** Expect findings; every Codex round so far has produced real ones. Verify
   each against the diff before changing anything.
10. Review the PRs from (5) and (6).
11. **Firing.** The design shape is settled (owner, 2026-09-22) and the owner authorised a
    $15/day ceiling for 2026-09-23 to -25 (`ops/budget_overrides.json`) for one epoch per day:
    each epoch is one `petri-audit` fire from the PR #29 branch with `mode: run`, `seed_ids`
    naming the four `pw-petri-w2-*` seeds, `epochs: 1`, `token_limit: 40000`,
    `max_spend: 3.00`, `judge_max_spend: 1.00`, `judge: true`, `commit_outputs: true`
    (15 samples; §5 of the design note has the revised costing). Preconditions, in order:
    the suite green on the head, `cli validate-seeds` clean, the environment lock verified,
    and a `dry_run` fire of the same params landed. Epochs 2 and 3 fire only if the previous
    one landed clean; re-park the lane after the last one.

### 5a. The fresh-container session (2026-09-22, evening)

The container that wrote the three-arm edits had a fork storm (13,000 threads, `sed` on a
small file timing out) and could not run Python or git, so the edits were committed through
the GitHub API as a self-applying script and were **unverified** at that point. A fresh session
in the same environment was started to: apply the script (which fills the 64-zero sha256
placeholders in `docs/framework/petri_seeds.draft.json` from the text and deletes itself), run
`ruff check .` and the suite, fix what fails, run the four wave-2 seeds under `mockllm` and
record the planned-judgment counts, commit, push, post `@codex review`, and — once the UTC
date is 2026-09-23 and the preconditions in item 11 hold — fire epoch 1. If that session did
not finish, its transcript says where it stopped; everything it was asked to do is listed here
so it can be redone by hand.

**What happened (written by that session as it went; the epoch-1 entries are appended at the end).**

- `python apply_w2_threearm_edits.py` applied all 45 replacements on the first try, wrote the
  two new files, filled 49 placeholder digests, and its own in-script validation reported 10
  seeds and 0 problems. `ruff check .` clean; `cli validate-seeds` clean (four wave-2 seeds at 3,
  3, 3 and 6 conditions).
- **One defect in the staged edits, fixed here:** the framing registry gained the `lay_careful`
  value but `docs/framework/judge_prompts/register.draft.json` did not, and
  `tests/test_framework_schemas.py::test_judge_method_resolves_to_a_versioned_prompt` requires
  the judge prompt to define every registry value. Added a `lay_careful` definition to the
  prompt, worded from the registry's `value_definitions`. This changes that prompt's file digest;
  no landed run records it (no judgment in `data/petri/runs/` references the register prompt),
  so nothing goes stale.
- Suite after the fix, before commit: 1290 passed, 3 skipped, 1 failed — the failure being
  `test_blob_matches_reads_the_file_at_the_recorded_commit`, which compares the outcome
  registry in the checkout with HEAD and so fails by construction while the edits are
  uncommitted; it passes on the commit. The known `test_specialty_map` failure AGENTS.md lists
  did **not** reproduce on this branch (3 passed). `tests/petri/test_zero_cost_e2e.py` skips
  under the 3.11 dev install (no `inspect_petri`).
- **The mock structure run, three arms.** A locked 3.12 environment was built from
  `docs/framework/petri_environment.lock.json` in the scratchpad (`verify-lock: match`; the
  pinned `inspect_petri` requires Python ≥ 3.12, which is why it cannot install into the 3.11
  dev environment). One environment hazard, not a code problem: `inspect_ai`'s token estimator
  fetches the `o200k_base` tiktoken encoding from an Azure blob host the sandbox proxy blocks,
  and every mock sample failed at its first target call until the encoding file was seeded into
  `TIKTOKEN_CACHE_DIR` (sha256 verified against tiktoken's own expected digest). CI's runners
  are not behind that proxy. With that in place, `cli run --target mockllm/model` on the four
  wave-2 seeds, `adapt`, and the planner (no judge call) measured: **15 samples, 15 trees, 150
  target calls, 795 planned judgments, 114 planned as `not_applicable`, 681 calls**. Per seed:
  `tool-clarify` 147 / 30 n/a, `referral-specificity` 177 / 18, `reassurance-decay` 177 / 30
  (27 `safety_netting_persistence`, 3 `safety_netting_baseline_persistence` — the baseline
  exchange's own reply, one per arm), `identity-register` 294 / 36. Each is exactly 1.5× the
  two-arm count in the design note's §5, plus the 30 new baseline-persistence plans; the
  design note §5 now carries these numbers. Contract checks: six pass; `generation_config_pinned`
  fails as the documented mock artifact.
- Committed as `0480ca3b` (the script's deletion included), pushed, `@codex review` posted
  (comment 5777150083). **Codex refused again on usage limits** (comment 5777152205, within a
  minute), so the three-arm edits have had no Codex review as of this push; the review request
  stands for whenever credits return.
- **Dry run fired and landed:** `fire_trigger.py fire` from this branch, nonce `w2e1-dry`
  (commit `c8ba8923`), run **35732045435** (attempt 1), conclusion `success` in 1m 42s; every
  step of the `audit` job green, the judge and commit steps skipped as `dry_run` prescribes;
  two artifacts uploaded, `petri-audit-exports-35732045435-1` (129,796 bytes zipped) and
  `petri-audit-raw-eval-35732045435-1` (114,470 bytes). **Its job summary could not be read
  from this container**: the log and artifact downloads redirect to an Azure blob host the
  sandbox egress proxy refuses, the public run page hides logs without sign-in, and the
  check-run annotations carry only runner deprecation notices. What was verified instead: the
  artifact sizes sit within 2–4% of the local 15-record mock run's (exports zipped 132,284
  bytes; raw `.eval` 119,474 bytes) and well away from a run whose samples fail (the local
  all-refused attempt's `.eval` was 212,994 bytes of tracebacks). The 15-sample count is
  therefore established by the local locked-environment run on the same seed file and harness
  commit, and consistent with, not read from, the CI artifact. Journal entry resolved and
  committed (`52cf2b4b`). Lane empty after the resolve.
- Epoch 1 is scheduled for after the UTC day roll (wake at 2026-09-23T00:10Z), with
  `max_spend 3.10` rather than the 3.00 in item 11: the pre-flight bound is exactly $3.00 and
  the check is `bound <= max_spend`, so 3.00 would pass, but the fire is placed above the bound
  rather than on it; $4.10 committed against the $15 override.

---

## 6. Things that will bite whoever picks this up

- **Wave-1 rows cannot be re-keyed from themselves.** `exchange_index` does not appear in
  `data/petri/runs/run_35351739969_1/analysis_rows.jsonl`; those rows predate the field and
  record it as null by design rather than being back-filled. Any re-analysis of wave 1 by
  exchange has to go back to `transcripts.jsonl`.
- **Wave 1 is $0.10 of data and the design note says in terms that it is not a result.** One
  epoch, one target model, no repeats, a judge from the same family as the target.
- **The wave-1 tool-calling seed is confounded.** Its clinical arm writes as a clinician about
  someone else and its colloquial arm writes as the patient, while both declare
  `user_is: "unknown"`. The validator compared the declarations, not the wording. PR #29 adds
  the crossing requirement that catches it, but the wave-1 finding itself stays confounded.
- **Trigger files fire on push.** Any branch operation that touches `.github/trigger/` fires
  that lane, including merges and cherry-picks. Five lanes spend money. This is the sharpest
  edge in the repo.
- **A standing ops Routine fires Tuesdays and Fridays at 12:00 UTC** (next: 2026-09-22). It is
  the owner's, not this session's, and was left running. If usage is still constrained on
  Tuesday, consider pausing it.
