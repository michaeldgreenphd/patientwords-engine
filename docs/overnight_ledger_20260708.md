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


## 08:45 UTC harvest (experiments 1-3 COMPLETE, published)

- **#1 ablation / #2 boost (20 downgrade phrases, all steering calls ok):**
  boosting the clinical graph's top-5 clinical features on the PATIENT wording
  recovers the clinical target outright in 5/20 (antacid x2, pills, inhaler,
  blood test); ablating the patient graph's top-5 off-target features recovers
  1/20 outright but redirects several toward clinical vocabulary (cardiologist,
  sleep specialist, meds). Listener-side boost > speaker-side mute.
- **#3 context inoculation (40/40 traced):** clinical-scene prefix mean penalty
  -0.059 vs neutral-scene -0.137 vs no-context -0.092; paired clinical-minus-
  neutral +0.083 (8/14 improved). Casual context AMPLIFIES the penalty; clinical
  context roughly halves it.
- **#4 ladders:** both generated; committed traces running (sleep) + pending (digestive).
- **#5 gemma-3-4b-it:** probe queued in logits chain (awaits HF_TOKEN).
- **Publish:** gen A joined the site payload - 235 scenarios (160 measured),
  unified set 132 phrases, penalties gemma -0.070 [-0.098,-0.043] /
  qwen3-4b -0.099 [-0.149,-0.049] / qwen3-1.7b -0.089 [-0.133,-0.047];
  organic downgrades-vs-upgrades 19v3 / 15v2 / 14v4; length confound |r|<=0.07.
  Collaborator archive 961 pairs / 838 traced.


## FINAL — 11:10 UTC morning close-out

**Spend by phase (session):** Phase 0 harvest ~$0.03 (mitigation translations) ·
Phase 1 generation $2.058 (gen A $1.291 + gen B $0.767) · Experiments $0.028
(ladders; steering/context/logits $0) · **session total ≈ $2.12 of the $8.00
ceiling.** Lifetime ≈ $8.20.

**Ladder dose-response (case studies, n=1 each):** digestive — with "dyspepsia"
held verbatim in all five rungs, P(antacid) falls 0.322 (rung 1, formal clinical)
→ 0.114 (rung 2) → below the top-10 floor (rungs 3-5, where 'apple' takes the
top); register alone flips the guidance object. Sleep — 'sedative' never
surfaces at any rung; 'melatonin' appears at rungs 3-4 (0.096→0.195); the
colloquial basin is too deep for register alone to recover the clinical target.

**Decoding before/after:** gen A shipped with continuations (its qwen rows:
41 classified flips / 160); the decoded 119-batch rerun (qwen3-1.7b) changed
NO classifications (83/107 patient tops already tiered) — decoding helps
wordpiece-heavy batches, and is a no-op where tops were already whole words.

**Tier-shift instrument now has CIs (unified 132):** gemma -0.054
[-0.098,-0.012]; qwen3-4b -0.048 [-0.099,-0.000]; qwen3-1.7b -0.034
[-0.096,+0.027]. Paired model differences all straddle zero.

**Still running at close-out:** gen B trace (5 chunks, fired 11:05), 119-batch
qwen3-4b decoded leg, gemma-3-4b-it probe (pending; needs HF_TOKEN),
154345Z/201750Z decoded reruns queued next in the logits chain.

## 13:40 UTC — rigor chain (a2/a3) fired

Placebo arm shipped: `--steer-placebo K` boosts K seeded-random features at the
same positive strength as the clinical boost (top_random_features, category-blind,
auditable labels; 118 tests green). Workflow gains steer_placebo /
steer_strength / steer_boost_strength keys. Runs fired on the 5 boost-recovered
cases (`urgency_downgrades_boostgrid.json`): placebo-vs-boost comparison
(running) and boost dose-response at strength 2.5 (pending); 5.0 and 20.0 chain
next. Five of six key-example tab edits are live and browser-verified; the
dialect tab waits on the 8x8 sweep trace (72 graphs, in the queue).

## 20:15 UTC — causal receipts + titration live

Placebo control PASSED: on the 5 boost-recovered cases re-traced independently,
top-5 clinical-feature boost recovered 4/5; 5 random features at the same
strength recovered 0/5. Specificity confirmed; recoveries replicate across
independent traces. Dose-response runs firing (2.5 live, 5 queued; 10 = 4/5;
20 + rank-6-10 chain next). Translation tab rebuilt around the data: process
flow with the real translated sentence, 14-case patch gallery, flipbook tabs,
titration panel with honest pending states that auto-fill from provenance.

## 21:25 UTC — titration wake: s2.5 harvested, s20 + low-rank armed

Strength 2.5 landed: **4/4 recovered** on the pairs that traced (pair 5 dropped
to a mid-batch truncation; remeasure queued). Published to the site's
`steering_titration.strengths['2.5']` — the dose bar fills. Dose-response so
far: 2.5 → 4/4, 10 → 4/5, placebo 0/5; strength 5 running, strength 20 now
pending behind it. The low-rank faithfulness arm shipped:
`NEURONPEDIA_STEER_RANK_OFFSET` skips the top ranks in `_steer_boost`
(recorded in results when nonzero; 122 tests green), workflow key
`steer_rank_offset`, alias batches `boostgrid_s20` / `boostgrid_lowrank` staged.
Ladder n=10 (`dialects_20260708T201616Z`) and paraphrase
(`dialects_20260708T203111Z`) batches harvested from main onto the branch;
their traces fire as circuit-trace slots free. Sociolect round 2 generating:
20 measured baselines x default 8-framing grid, max_spend 4. $0 spent this
wake outside that ceiling.

## 22:05 UTC — HF_TOKEN landed; gemma-3 fired; merge-button refire contained

Owner added HF_TOKEN and merged PR #2 via the GitHub merge button. The merge
changed all four trigger files on main and refired every workflow there
(the documented merge/copy danger; API cancel returns 403 for this app).
Blast radius, assessed: scenario-generation duplicate is bounded by its own
max_spend=4 and yields an independent second sociolect batch (kept as a
replication, "round 2b"); the circuit-trace duplicate re-runs the low-rank
arm for $0 (kept as a free replication); the logits duplicate IS the
gemma-3 downgrades probe, now running with the token; the archive duplicate
just re-zips renders. Branch restarted from merged main per merged-PR
protocol (trigger-identical, no refire). gemma-3-4b-it unified-set runs
fired on the branch queue: stems 1/4 (pairs_20260706T201750Z, running) and
2/4 (pairs_20260707T154345Z, pending); 3/4 + 4/4 chain next, then the
downgrade probe harvest.

### Morning brief spec (owner's five sections, due when they log on ~11:00 UTC)
1. Findings delta incl. gemma-3-4b-it vs the other models; flag anything
   contradicting yesterday's baseline.
2. Causal verdict: final titration table + one-paragraph interpretation.
3. UI consequences: ranked, staged-vs-not, sign-off-needed flagged.
4. Pipeline status: published / harvested-unpublished / running / failed;
   truncations, re-runs, total ledger cost, blocked-on-owner list.
5. Synthesis readiness: external-ready claims vs tier-review-gated claims.
Chain continues: harvest s20 + low-rank + grandma_r2 slot, ladder +
paraphrase + sociolect traces, gemma-3 stems 3-4, finalize synthesis
(SendUserFile), assemble brief by 10:45 UTC.

## 23:00 UTC — causal panel complete; gemma-3 first light

Titration finished and published. Dose-response: 2.5 → 4/4, 5 → 5/5,
10 → 4/5, 20 → 0/1 measured — at strength 20 three steer calls 500'd and the
one landed continuation degenerated into token repetition (over-steering;
read as "breaks down", not "no effect"). Rank faithfulness: clinical ranks
6–10 at strength 10 recover 3/4 — near-parity with top-5 (4/5), so the causal
handle is distributed across the circuit, not concentrated in its top five;
placebo remains 0/5. (Low-rank result arrived via the merge-refire duplicate
on main — the accidental run delivered the arm early; the branch replication
is still running.) gemma-3-4b-it works with HF_TOKEN: stem 1/4 + the
downgrade probe landed; on the 5 stem-1 pairs common to all four models the
gemma-3 per-pair penalty tracks gemma-2 at r=0.96 — too few pairs to cite,
full table when stems 2–4 land. Fired: ladder n=10 committed trace
(5 chunks) + gemma-3 stem 3/4. Sociolect 2b batch harvested. Next slots:
paraphrase trace, sociolect traces, grandma_r2, s2.5 pair-5 + s20 remeasures.

### Addendum to morning brief spec (owner request, 23:15 UTC)
The tap-through phone format worked; deliver two decks with the brief:
(a) stimulus QC deck — DONE, published (blind 20-pair sample, artifact
'stimulus-qc'); count its verdicts into the methods when the paste arrives.
(b) morning sign-off deck — build AT the anchor from final overnight data:
one card per UI change needing sign-off (brief section 3) + one card per
synthesis claim (section 5, external-ready vs tier-gated), same
chips-and-copy-summary pattern, same file path convention (new artifact).
Owner completed the tier review on the phone but has NOT yet pasted the
summary — if it hasn't arrived by the anchor, lead the brief's
blocked-on-owner list with that paste.

## 23:45 UTC — tier review v1 applied; downgrade asymmetry strengthens

Owner's tap-through review landed and is applied end-to-end: 5 tier moves
(session→2, steroid→2, routine→1, blood→2, bottle→0), 10 drafted tiers
approved, 20 exclusions confirmed, tier-3/4 lists confirmed. Status flipped
to reviewed v1; urgency pipeline re-run and republished. Downgrades 70→109
vs upgrades 9→12 (the review unblocked previously unclassifiable flips);
gemma-2-2b now 67v4; gemma-3-4b-it enters the safety view at 8v1 (p=.039) —
the newer instruction-tuned model shows the same asymmetry. Every draft
label on the site now reads reviewed v1 (runtime + static). Synthesis
section 2 un-gated. Validity and penalty CIs unchanged (132-phrase unified
set untouched by tiers). paired_stats re-run: tier-shift CIs hold.

## 00:45 UTC — ladder does not generalize; low-rank replicates exactly

Ladder n=10 landed (all 5 chunks): with the clinical term held verbatim,
mean target probability is FLAT across the five register rungs (0.27–0.34);
rung 5 beats rung 1 as often as not (3/6). The single-case staircase
(dyspepsia 0.322→0.114→floor) is real but not representative — register
alone rarely moves the target; the penalty concentrates in the vocabulary
swap. Published to provenance (ladder_n10), corrected the syntax-page
explainer, revised synthesis §5. This is a headline item for the morning
brief's "contradicts yesterday" list. Low-rank branch replication landed:
3/4, IDENTICAL pattern to the main run (same recoveries, same miss, same
500 on pair 2) — recorded in provenance. gemma-3 stem 2 landed; stem 3
running, stem 4 queued. Paraphrase trace running; sociolect 2a queued
(offsets corrected to cover all 20 baselines after catching a chunking
gap that would have silently dropped pairs 19–20). Remaining for later
slots: grandma_r2 re-render, s2.5 pair-5 + s20 remeasures.
