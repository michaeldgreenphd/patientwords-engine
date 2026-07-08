# Overnight session ledger — 2026-07-07/08

Hard ceiling this session: **$8.00** Anthropic credits. Tracing/logits/CI: $0.

| Phase | Item | Status | Cost |
|---|---|---|---|
| 0 | Validity correlation (27 hand pairs) | DONE — r=0.687 / ρ=0.665 (n=14 matched; 12/14 within ±0.08; outlier #17) | $0 |
| 0 | Mitigation trace (20 downgrade phrases) | DONE — 8 recovered / 7 unrecoverable / 5 unclassifiable | ~$0.03 |
| 0 | Continuation decoding (Qwen path) | code shipped; 119-pair re-run firing | $0 |
| 1 | Gen A: 80 pairs, digestive+sleep 2x (40/40) | DONE | $1.291 |
| 1 | Gen B: 60 pairs, other 6 topics | DONE | $0.767 |
| 1 | New-batch gemma trace + Qwen logits | after gen lands | $0 |
| 2 | Safety cards + hedging/redirecting vocab | DONE, browser-verified, pushed | $0 |
| 3 | Review checklist + one-line findings flip | DONE (docs/tier_review_checklist.md) | $0 |

**Session paid total: $2.09 committed (gen A $1.29 + gen B $0.77 + translations ~$0.03). No further paid work planned. Ceiling $8.00.**
Project lifetime spend before tonight: $6.08.

Updated at each check-in; final numbers in the morning report.

**GitHub Actions minutes event (2026-07-08 ~00:00):** user reports ~90% of the monthly Actions quota consumed (private-repo CI: trace runners waiting on hosted generation + CPU logits runs). All queued/chained CI halted; two live runs need a manual cancel. Remaining planned logits re-runs (154345Z, 201750Z), gen A trace chunks 8-20, gen A logits, and gen B trace are DEFERRED pending a quota decision (public repo / paid minutes / monthly reset). Data already landed is checkpointed and safe.

**Resolution (2026-07-07 ~23:20 UTC):** repo made public — standard GitHub-hosted runners
are free for public repositories and do not draw on the 3,000 included private-repo
minutes. The 100%-of-minutes email (3,014/3,000, delivered ~00:17 UTC) reflects
private-repo usage from before the flip; the block-at-cap behavior we observed (queued
runs stalling ~22:56 UTC) is what prevents overage billing. Chain restarted: gen A trace
completed post-flip on free runners.

## Experiment suite added post-restart (user-approved, all five)

| # | Experiment | Mechanism | Status | Cost |
|---|---|---|---|---|
| 1 | Causal ablation on downgrade flips | `--steer-validate 5` (suppress top off-target features, patient graph) | RUNNING (01:20 UTC, stem-alias out dir) | $0 |
| 2 | Positive clinical steering ("fix the listener") | new `--steer-boost 5` (amplify clinical-graph features on patient prompt) | RUNNING (same pass as #1) | $0 |
| 3 | Context inoculation | 40 derived pairs: {clinical, neutral} scene prefix x 20 downgrade phrases (`scripts/derive_context_pairs.py`) | PENDING behind #1/#2 in the trace queue | $0 |
| 4 | Dose-response colloquialism ladder | dialects task, 5 graded register rungs, term held fixed; sleep + digestive baselines | both GENERATED (sleep $0.013 + digestive $0.015); committed dialect-mode traces queued in chain | $0.028 |
| 5 | gemma-3-4b-it instruct logits | logits path; needs user's HF_TOKEN secret (fails cheap without) | queued in logits chain after the two decoded re-runs | $0 |

Chain note (01:25 UTC): gen A gemma trace complete 20/20 chunks. The redundant
gen A remainder run failed only at its COMMIT step (re-traced bytes differ from
already-landed parts -> rebase conflict) - no data lost; all parts landed from
the primary run. Steering pass therefore traces under a stem alias
(`urgency_downgrades_20260707T1_steer.json`) to guarantee a collision-free out dir.

Hardening shipped alongside: source_set threaded into steering calls (audit fix, regression
tests), length-confound check (penalty vs word-count diff: |r| <= 0.16, n=91 — not a length
artifact), censored-pair validity sensitivity (8 hand pairs with patient-side target below
the top-k floor now reported as bounds instead of dropped).

**Session paid total after experiments: ~$2.12 of $8.00** (adds ladder 4a $0.013 + 4b ~<=$0.02 when it lands).
