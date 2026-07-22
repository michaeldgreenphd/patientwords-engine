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

### Morning brief spec, section 6 (owner request, 01:15 UTC): rigor, scale, cost, hosting
Ground everything in these computed numbers (from paired_stats_out.json and
urgency_shift.json, 2026-07-09):
- Effect sizes: penalty cohen_d ≈ 0.43/0.34/0.36 (gemma-2/qwen3-4b/qwen3-1.7b)
  → 80% power needs n ≈ 42/69/63. Unified set is 132: THE PENALTY IS ALREADY
  ADEQUATELY POWERED. Scale is for the proportion-level claims:
- P(downgrade) = 0.118 of 920 measurements. Downgrade rate to ±2% needs
  n≈1,004; ±1.5% needs 1,784. Detecting a rate DIFFERENCE (.10 vs .05,
  80% power) needs ≈434 per condition.
- Tier proposal (behavioral scale decoupled from mechanistic depth — key
  design point: behavioral n scales via $0 CPU logits for ALL models incl.
  gemma-2-2b open weights; hosted tracing reserved for a graphed subsample):
  A) Confirmatory core, n=500 balanced, pre-registered: gen ~$7.50 (opus,
     observed $0.015/pair) or ~$1.50 (cheaper generator); traces on a ~100
     stratified subsample; ~3-4 days mostly queue time.
  B) Condition-resolved, n=1,600 (200×8 conditions): gen ~$24 opus / ~$5
     cheap; behavioral via CPU in days; hosted tracing subsample only
     (full 1,600 hosted would take 1-2 weeks on the single queue).
  C) Dialect grid at power: 50 baselines × 8 framings × 4 models,
     behavioral-first, same pattern.
  Recommend a timed 20-pair throughput probe before committing (hosted
  rate limits at scale are unverified).
- Additional rigor tests to propose: pre-registration doc committed before
  generation; second-generator replication batch (different LLM family) to
  rule out generator artifacts; non-medical register-swap NEGATIVE CONTROL
  (is the penalty medical-specific or register-general — framing-critical);
  trace-retrace stability probe (probability jitter, cheap); mixed-effects
  model with per-topic random intercepts + Holm/BH across conditions;
  human-reader baseline (do people interpret the patient phrasing where
  models don't); larger open models via logits for a scale trend; expand
  the blind stimulus QC beyond n=20.
- Hosting/presentation at scale (site currently: payload 1.8MB, renders
  89MB, table 235 rows): shard the payload per batch with a small index +
  lazy fetch (page JS reads precomputed aggregates first); paginate/
  virtualize the scenario table (~50 rows/page); KEEP the 25-render cap on
  Pages — full render sets stay on GitHub Releases via the existing archive
  workflow (renders are ~1.1MB each; thousands would blow the 1GB Pages
  budget); CSV/Parquet for collaborators on Releases. GitHub Pages limits:
  ~1GB site, 100MB/file, 10 builds/hr — sharding keeps everything far under.

### Brief additions (owner, 01:55 UTC): power-added, stats audit, interp suggestions, week runway
OWNER CONTEXT: on vacation ~1 week from Friday; long unattended queue time is
AVAILABLE and cheap. Recompute recommendations under that runway.
- Power added by scale (computed): penalty CI half-width 0.028 @132 →
  0.014 @500 → 0.008 @1600. Downgrade-rate precision ±0.021 @920 →
  ±0.013 @2500 → ±0.009 @5000. Minimum detectable condition DIFFERENCE
  (80% power, two-prop): ±0.16 @62/cell (n=500/8) → ±0.09 @200/cell →
  ±0.06 @434/cell → ±0.05 @625/cell. State plainly: scale buys the
  proportion claims, penalty already powered.
- Cost/time at scale: generation $0.015/pair opus ($24 @1600, $75 @5000)
  or ~$0.003/pair cheaper generator ($5/$15). Hosted tracing ≈8–12
  pairs/hr single queue (VERIFY with a timed 20-pair probe) → a vacation
  week ≈ 1,300–2,000 traced pairs unattended; CPU logits: thousands/day,
  $0, all 4 models. Recommended vacation plan: pre-register, generate
  Tier B (1,600 balanced), behavioral-complete on CPU all models, hosted
  traces continuously in the background all week (~full coverage if probe
  confirms ≥10/hr, else stratified 500), chain wakes manage everything.
- Stats audit (double-check requested): (1) FLAG pseudoreplication — the
  920-measurement downgrade tallies pool re-traces of the same phrases
  (steering/context/alias batches); inferential claims must dedupe by
  phrase or use mixed-effects; relabel site counts as measurement tallies.
  (2) Cluster structure (topics/templates) → cluster bootstrap or
  (1|topic) random intercepts; (3) report Clopper-Pearson CIs on all
  steering fractions + Fisher exact for boost 4/5 vs placebo 0/5;
  (4) BH/Holm across per-model tests; (5) paraphrase noise now measured
  (mean |delta| 0.064 — same order as the penalty): at scale, measure each
  pair under 2–3 paraphrases and average (halves item noise); single-pair
  claims are illustrations only. Sign tests + bootstrap CIs themselves:
  appropriate; keep.
- Interp-research suggestions to include: activation patching
  clinical↔patient (layer/position localization; stronger causal standard
  than API steering); steering-vector (residual mean-diff) vs SAE-feature
  steering comparison; cross-pair feature transfer (boost pair A's
  features on pair B — shared circuit or idiosyncratic?); feature
  universality on gemma-2-9b (Gemma Scope exists; check tracer support);
  tuned-lens trajectories as $0 depth complement; surface error-node
  share as graph-faithfulness caveat.
- Paraphrase robustness landed and published (provenance
  paraphrase_robustness; synthesis §7 bullet). Include in findings delta.
- Text-reduction second pass done tonight + fresh full outline
  (docs/site_text_outline_v2.md) sent to owner for personal slimming;
  note in brief.

## 10:42 UTC — final titration cells; stem-3 refire
Remeasures landed: s2.5 final 4/5 (pair 5 'blood' resists at every strength);
s20 remeasure shows the three 500s were server flake — final 1/4 with
occasional degeneration. Final dose-response: 2.5→4/5 · 5→5/5 · 10→4/5 ·
20→1/4 — a genuine decline curve, not total collapse. gemma-3: stems 1,2,4
landed; stem 3 was EVICTED overnight by my stem-4 trigger push (queue
discipline slip — own it in the brief) and is re-fired now. Sociolect 2a:
6/7 chunks (pairs 10-12 chunk failed; 17/20 baselines measured). Owner is
awake — brief anchor fires 10:45; use THESE final numbers.

## 11:5x UTC — haiku-generator justification (owner question, daytime)
Owner asked: retain existing results and use them to justify haiku for
generation + translation in the week-long run; wants cost + timing.
Discovery: the 0707 cross-model generator test ALREADY ran haiku twice
(pairs_20260707T023706Z, pairs_20260707T025842Z; $0.0985/$0.0996 for 50
accepted each = $0.002/pair vs opus $0.0164-0.0202/pair). Batch 1 was traced
under screen 0.02: haiku beats opus on validator yield (76% vs 60%), screen-in
rate (27/49 = 55% vs 24/50 = 48%), and shows the penalty at least as strongly
(mean -0.046 CI [-0.084,-0.012] n=27 vs opus -0.036 CI [-0.080,+0.006] n=24).
Actions: (1) added translation_model param to circuit-trace workflow
(MEDLANG_ANTHROPIC_MODEL passthrough; translate_to_clinical + both result
schemas now record which model translated; +2 regression tests, 124 green);
(2) fired run 64 = haiku-translator arm on downgrades_txhaiku (alias of the
20-downgrade set) to compare against opus 8/20 recovery; (3) queued run 65 =
trace of the second (untraced) haiku batch, same screening, doubles
equivalence n. Both $0 tracing + ~$0.01 haiku translation. Circuit-trace
queue FULL (64 running, 65 pending) — no trace pushes until 64 completes.
gemma-3 stem-3 logits (run 14) still in progress. Owner plan: Fable
interactive today; tonight fire the week-long evaluation based on findings.

## 12:2x UTC — owner sign-off received (deck paste)
SIGN-OFF 2026-07-09: A1 approve; A2 cheaper (haiku); A3 hold; A4 hold;
B1 approve; B2 approve; B3 after feedback; B4 keep split; C1-C5 release;
C6 release when final. Consequences: draft Tier B pre-registration today
(1,600 pairs, haiku generator, 20-pair throughput probe first), fire tonight
pending the haiku translation arm + equivalence recheck; implement B1
(pair-17 retrace caption preference) and B2 (dose-curve chart replaces the
four bars) now; C6 auto-releases when gemma-3 stem 3 lands. A3/A4 stay
unfired. Owner also asked for a decision-point map to author a new
process/dashboard improvement prompt.

## 12:5x UTC — PM decision deck returned (17/17 decided)
DECISIONS 2026-07-09 PM: A1 both-private-first; A2 engine-repo html;
A3 per-occasion decks; A4 routine + daily digest push; A5 <=$2/day;
A6 process-as-code approved; B1 lead with one concrete case; B2 add fenced
why-this-matters; B3 add plain abstract; B4 activation patching is the
week's primary interp experiment; B5 unify glossary; C1 keep three
differences pages; C2 fold model-evaluations into methods; C3 re-render
stale dialect tiles (queue full — chain after run 65); C4 build translation
flow chart; C5 keep synthesis at 8; C6 cut morning brief to 3 sections.
Scope split: A section = the owner's NEW prompt (context pack written to
docs/prompt_context_20260709.md for a second-eyes LLM review); B + C
execute in THIS session. B4 needs engine work (patching runs via logits-eval
path or new workflow) — design before vacation.

## 12:3x UTC — owner corrections + Tier B authority
(1) VISIBILITY: patientwords-engine is PUBLIC (both repos are). Scrubbed
"private" from HANDOFF, routine standing prompt, prompt context pack, site
CLAUDE.md; secret-pattern scan of ops/ + docs/ clean; no-secrets rule
restated in HANDOFF and standing prompt. (2) Rmd artifact moves to THIS
repo: ops/site_text_outline.Rmd (not the site repo) — highest priority,
due 19:00 UTC. (3) UI status delivered: five full-page screenshots of main
(zero console errors), zero open PRs in either repo — all UI changes ship
by direct push to main. (4) Timezone CONFIRMED America/New_York (EDT);
Routine crons written in UTC from EDT anchors (daily fire 11:30 UTC =
07:30 EDT). (5) Tier B: standing approval to fire batch 1 tonight IFF the
haiku translation verdict is clean (recovery within noise of opus 8/20 AND
equivalence n holding); any ambiguity → hold and flag; go/no-go rationale
must be written here either way. Early read of the translator arm (12/20
landed): translation_model recorded correctly; several strong recoveries
(inhal 0.04→0.48, derma 0.22→0.68) and misses, pattern resembling opus arm;
full classification at the 13:45 harvest.

## Spend log (auto)

- boostgrid_lowrank.report.json · $0.0000 · alias · accepted — · —
- boostgrid_s20.report.json · $0.0000 · alias · accepted — · —
- boostgrid_s2p5.report.json · $0.0000 · alias · accepted — · —
- boostgrid_s5.report.json · $0.0000 · alias · accepted — · —
- dialects_20260706T232102Z.report.json · $0.0099 · claude-opus-4-8 · accepted 6 · 2026-07-06T23:21:08.764022+00:00
- dialects_20260707T000923Z.report.json · $0.0831 · claude-opus-4-8 · accepted 48 · 2026-07-07T00:10:21.352373+00:00
- dialects_20260707T023223Z.report.json · $0.0836 · claude-opus-4-8 · accepted 48 · 2026-07-07T02:33:12.593104+00:00
- dialects_20260707T155124Z.report.json · $0.0536 · claude-opus-4-8 · accepted 24 · 2026-07-07T15:51:59.740778+00:00
- dialects_20260707T235906Z.report.json · $0.0134 · claude-sonnet-5 · accepted 5 · 2026-07-07T23:59:14.457187+00:00
- dialects_20260708T011831Z.report.json · $0.0149 · claude-sonnet-5 · accepted 5 · 2026-07-08T01:18:40.804492+00:00
- dialects_20260708T120729Z.report.json · $0.1893 · claude-sonnet-5 · accepted 64 · 2026-07-08T12:09:26.638462+00:00
- dialects_20260708T201616Z.report.json · $0.1498 · claude-sonnet-5 · accepted 50 · 2026-07-08T20:17:52.110848+00:00
- dialects_20260708T203111Z.report.json · $0.2521 · claude-sonnet-5 · accepted 46 · 2026-07-08T20:33:50.267654+00:00
- dialects_20260708T212709Z.report.json · $0.4651 · claude-sonnet-5 · accepted 158 · 2026-07-08T21:31:55.552073+00:00
- dialects_20260708T215356Z.report.json · $0.4131 · claude-sonnet-5 · accepted 160 · 2026-07-08T21:57:57.785683+00:00
- downgrades_txhaiku.report.json · $0.0000 · alias · accepted — · —
- featured_sim85.report.json · $0.0000 · alias · accepted — · —
- featured_sim85_r2.report.json · $0.0000 · alias · accepted — · —
- grandma_r2.report.json · $0.0000 · alias · accepted — · —
- pairs_20260706T175614Z.report.json · $0.1238 · claude-opus-4-8 · accepted 10 · 2026-07-06T17:56:54.001287+00:00
- pairs_20260706T201750Z.report.json · $0.1940 · claude-opus-4-8 · accepted 13 · 2026-07-06T20:18:40.180501+00:00
- pairs_20260706T210703Z.report.json · $0.1635 · claude-opus-4-8 · accepted 6 · 2026-07-06T21:07:32.593245+00:00
- pairs_20260707T023656Z.report.json · $0.8207 · claude-opus-4-8 · accepted 50 · 2026-07-07T02:40:59.823842+00:00
- pairs_20260707T023704Z.report.json · $1.4362 · claude-sonnet-5 · accepted 28 · 2026-07-07T02:50:44.600929+00:00
- pairs_20260707T023706Z.report.json · $0.0985 · claude-haiku-4-5 · accepted 50 · 2026-07-07T02:38:37.713618+00:00
- pairs_20260707T025842Z.report.json · $0.0996 · claude-haiku-4-5 · accepted 50 · 2026-07-07T03:00:16.620540+00:00
- pairs_20260707T154345Z.report.json · $0.4099 · claude-opus-4-8 · accepted 23 · 2026-07-07T15:45:42.691193+00:00
- pairs_20260707T171223Z.report.json · $2.4055 · claude-opus-4-8 · accepted 119 · 2026-07-07T17:23:02.607590+00:00
- pairs_20260707T215921Z.report.json · $1.2911 · claude-opus-4-8 · accepted 80 · 2026-07-07T22:05:49.231826+00:00
- pairs_20260707T221438Z.report.json · $0.7671 · claude-opus-4-8 · accepted 60 · 2026-07-07T22:18:39.713960+00:00
- quadrants_20260706T191617Z.report.json · $0.0254 · claude-opus-4-8 · accepted 4 · 2026-07-06T19:16:32.333244+00:00
- urgency_downgrades_20260707T1__context.report.json · $0.0000 · alias · accepted — · —
- urgency_downgrades_20260707T1_steer.report.json · $0.0000 · alias · accepted — · —
- urgency_downgrades_boostgrid.report.json · $0.0000 · alias · accepted — · —

## 13:5x UTC — harvest: haiku-translator verdict (run 64)
Run 64 complete (15/20 pairs landed; pairs 4,5,15,19,20 lost to hosted-tracer
chunk truncation — server flake, translations themselves all method=llm).
Method-identical comparison via urgency_shift on the same phrases/tiers:
PAIRED (n=12 both classifiable): haiku restored-top-tier 8/12 vs opus 10/12
(haiku loses idx 2,9,11; WINS idx 14 where opus worsened prescription→topical);
paired urgency_recovery haiku +0.119 vs opus +0.150, mean diff -0.031
(sd 0.205, |t|≈0.5) — WITHIN NOISE. Owner condition 1 (recovery within noise
of opus) = MET on landed data. Fired filler re-trace of the 5 missing pairs
via scripts/fire_trigger.py (first production use; offsets 3,4,14,18,19).
Condition 2 (equivalence n holding) awaits run 65, landing this afternoon.
Go/no-go executes tonight; rationale will be logged here.

## 14:2x UTC — owner's text trim applied site-wide
Owner returned the trimmed outline (66 of 203 blocks changed, no deletions).
Applied block-by-block with markup preserved (links, em, spans, fold-meta/
flip-cap JS hooks); verified by re-extraction: 192/203 byte-identical, the
11 exceptions being flagged typo fixes reported to the owner. Added the
reviewed-v1 tier-vocabulary note to methods.b025 and (owner's own edit)
sim-scenarios.b011. All 10 pages browser-checked clean; deployed to main.
ops/site_text_outline.Rmd regenerated to match the live site.

## 14:4x UTC — tier table + plain-language references (owner request)
Publisher now emits tier_examples (measured example words per tier, base
model only, vocabulary-note fragment filter, top 3); homepage safety view
renders a tier table (tier · meaning · measured examples) from the fetched
data. All reader-visible file paths replaced with plain language across the
10 pages; JS fetches untouched. Browser-verified, deployed to main.
FLAG for tonight's unified recompute: republished urgency data now pools
the alias re-traces (txhaiku etc.) into per-model measurement counts —
gemma-2 downgrades read 78 (was 67) at measurement level. Prereg analysis
rule "dedupe by phrase before any pooled count" must land in the collector
with the gemma-3 recompute; site cards say "measurements" so they are
accurate as labeled, but phrase-level counts are the claim-grade numbers.

## 15:0x UTC — nav reorder + percentage display (owner request)
Masthead order on all 11 pages: Start Here · Methods · Overview (Home
renamed) · rest unchanged. Dialect + translation pages now display all
probabilities as % (deltas as signed percentage points; attribution mass
left decimal). Browser-verified incl. dynamic caption paths; deployed to
main. Outline regenerated.

## 14:5x UTC — owner away-deck answers; session switched to Opus 4.8
AWAY 2026-07-09: Q1 switching to Opus now (done — session is Opus 4.8);
Q2 fire Tier B tonight IF haiku equivalence clean (standing, reconfirmed);
Q3 daily digest 9am EDT = 13:00 UTC; Q4 (Friday 7am) SUPERSEDED by owner
note -> run the handoff Friday 4am EDT = 08:00 UTC (early flight); Q5 idle
filler approved (sociolect r2 trace when slack, $0); Q6 blind QC pending
(owner will paste during travel). Note also: recreate the QC as a phone app
(done — republished, offline-capable). Standing prompt gained: start_utc
bootstrap rule (item 1) + sociolect filler (item 4). Scheduled: tonight
01:00 UTC go/no-go + Routine creation; Friday 08:00 UTC handoff. Both
this-session durable wakes. Fresh-session Routine created tonight after
Tier B start so start_utc is clean (matches Thursday-create plan).

## 15:2x UTC — blind stimulus QC returned (Q6)
Owner tapped the 20-pair blind QC: 15 sound / 2 unsure / 3 flawed (75% sound).
Note: "flawed ones didn't really feel like clinical equivalents." Crosstab
vs flip status: ALL 3 flawed are flips (0/10 non-flips flawed) — failure mode
is condition-equivalence drift on the patient side, concentrated in the flip
half. BUT the 3 flawed flips are low-signal (pen -0.022, -0.088, one
unmeasured target; none are confident downgrades p>=0.2), so the load-bearing
confident-downgrade claim is largely insulated. Recorded docs/stimulus_qc_v1.json;
added a located-caveat bullet to synthesis §7. Q6 cleared. Soft flag for
tonight's go/no-go: consider a condition-equivalence screen for Tier B at
scale — owner-decision, not an autonomous design change. Does NOT change the
fire-if-clean verdict (that gate is behavioral equivalence of the haiku
generator, independent of this stimulus-design finding).

## 19:0x UTC — Checkpoint 1 (async) + run-65 eviction recovery
Infra all green: 191 tests, ruff clean; dashboard/guard/ledger/brief done +
hardened + live-seeded; Rmd regenerated (204 blocks, engine ops/, verified
verbatim x3, none in site repo); secret scan clean (public repo). gemma-3
all 4 stems have summaries. ROOT-CAUSE: run 65 (equivalence-n batch)
concluded "failure" = EVICTION not data — params job cancelled, trace
skipped, because the filler (run 66) was a third-push into circuit-trace
while run 64 was still finishing; the guard allowed it because run 64's
journal entry was resolved (partial landing) before GitHub finished it.
Journal-vs-GitHub divergence = documented seam. Fix: resolve only on FULL
landing + settle; one trace/cycle; never a third fire (added to standing
prompt). Recovery: resolved stale entries, re-fired batch-2 clean into the
free queue ~19:00 UTC; expected to land before 01:00 go/no-go. Go/no-go
readiness: (a) translation recovery within noise = MET; (b) doubled-n
equivalence = pending the re-fire (batch-1 equivalence holds regardless).
Standing instruction unchanged: fire if clean, HOLD + flag if the re-fire
truly fails.

## 19:3x UTC — vacation autonomy batch 1 launched (Fable usage, owner-approved)
Owner (Fable reset) approved 3 autonomous streams: Functionality & scale,
Skeptic's read, Analysis depth (NOT Clarity/message — owner owns voice).
Launched background workflow wf_8eff2840-10a: 2 read-only auditors
(skeptic claim/number audit of site+synthesis → report+caveats; a11y/
functionality static audit of 10 pages → fix-list) + 3 sequential builders
on disjoint files (scripts/paired_stats_rigor.py stats rigor; fire_trigger.py
SETTLE-window guard hardening vs the run-65 eviction; activation_patch.py +
design doc). Agents do NOT commit/fire; I integrate + verify (full suite,
browser before/after) + commit only if green, then fold audits into an
owner report. Safety: reports/drafts for anything touching voice; objective
functionality fixed live with verification; scale-sharding to be done with
graceful fallback so it can't break existing pages. Pipeline/go-no-go
untouched. Weekly cadence: Routine runs the stats scripts on new Tier B data;
digest surfaces progress; further batches chain.

## 20:xx UTC — autonomy batch 1 integrated
Workflow wf_8eff2840-10a done (5 agents). Code: paired_stats_rigor.py +
settle-window guard + patching skeleton, 216 tests green, committed. Skeptic
+ a11y audits found real issues. FIXED LIVE: dialect page/homepage false
prose (8/6/48 + fake depression→therapist example vs real 5/8/40 25%-flip
data); synthesis overstatement (gemma-3 "8v1 p=.039 significant" -> real
11v4 p=.12 NOT significant; gemma-2 downgrades 25 deduped not 67 pooled) via
the rigor script; tier status -> "owner-reviewed v1 · domain review pending";
scenario.html masthead regression. REPORTED for owner (docs/skeptic_read_
20260709.md): single-case framing caveats, word-diff example mismatch,
model-eval softening, QC caveat on site, translation 45/41, Pair 15/16.
QUEUED next batch: site pseudoreplication (collector dedupe -> lowers
headline downgrade counts, owner should see it land), a11y micro-fixes.
Pipeline untouched; go/no-go still armed.

## 20:5x UTC — FABLE PLAN received; batch 2 launched (Fable agents)
Owner paste: A1 nightly critic / A2 verify-before-commit / A3 weekly
synthesis draft / A4 ops stays light / B1-B4 all approved / C: add
llama-3.2-3b, olmo-2-1b, biomistral-7b (skip phi). Note: Fable through
Tuesday 2026-07-14 then downshift batches to Opus 4.8 (owner wrote "llama"
— interpreted as the non-Fable fallback = Opus; flagged for correction).
Armed: nightly critic 05:00 UTC (self-chaining), Monday synthesis draft
06:00 UTC, Tuesday downshift 03:30 UTC Wed. Plan doc:
docs/fable_week_plan.md (incl. HF gate/cost truth: acceptance + downloads
free, no card, free public-repo CI; probe-first protocol so owner only gets
pinged for models that actually 401). Batch 2 (wf_92c08dc9-407, Fable):
site pseudoreplication dedupe (per_model_deduped + cards), 4 a11y fixes,
HF_IDS expansion (5 models), activation-patching CI (workflow + trigger +
KNOWN_KEYS + real transformer-lens patch_and_measure w/ offline-mocked
tests), B4 experiment designs — then 2 adversarial verifiers (A2 policy).
Integration at completion notification; site changes browser-verified
before deploy.

## 21:xx UTC — batch 2 integrated + deployed
7 Fable agents, 0 errors, verify stage caught 5 real items, all fixed
before integration: urgency_shift seen-marking now requires a landed row
(patching outputs can't shadow real summaries); site deduped headline only
sums when every model has a record; absent deduped fields render em-dash;
dialect accordion semantics moved to a real <button> (row semantics
restored); patching yml normalizes layers lists. Synthesis reconciled to
the committed rigor record: gemma-2 downgrades = 26 v 4 (p 6e-5, BH 2.4e-4).
SITE now shows phrase-deduped per-model counts everywhere (gemma-2 26v4,
gemma-3 11v4, qwen1.7 18v5, qwen4 16v2) — the pseudoreplicated 78/124
tallies are gone from public view. Engine: 9-model logits registry +
docs/model_matrix.md (HF gate/click-paths), activation-patching CI live
(real transformer-lens implementation), B4 designs pre-registered
(docs/feature_experiments_design.md). Suite 228 green. Fired the $0
1-pair patching smoke via fire_trigger (new group, running slot).
Owner also enabled promptless artifacts (user settings allow-list) and
received the headroom deck (H1-H6, pending).

## 22:xx UTC — HEADROOM approved (H1-H5); model supply-chain hardened (W5)
Owner approved H1-H5 (H6 held); queue in fable_week_plan.md, critic executes.
Gaps closed on "anything missing": W3 prereg Amendment 1 (10% confirmatory
holdout by sha1 hash + seed provenance, committed BEFORE tierb.start_utc was
set — verified null at commit); W1 Routine watchdog on the orchestrator's
wake chain; W4 STOP protocol in the digest footer; W2 deployed-site health
folded into H1. Owner also asked for protection against compromised HF
models → W5: use_safetensors=True + trust_remote_code=False enforced in
logits_eval with a source-level tripwire test (suite 229 green); vetting
policy in model_matrix.md (official orgs only, ephemeral CI execution,
revision pinning after first probe). Owner's rhythm: ONE morning check-in
— all new ideas go into the 9am EDT digest, no extra pings.

## 2026-07-10 01:1x UTC — TIER B GO/NO-GO: **GO** (rationale)
Standing approval condition (owner, 2026-07-09): fire Tier B batch 1 tonight
ONLY IF the haiku translation verdict is clean (recovery within the noise of
opus AND equivalence n holding); any ambiguity or structural failure = HOLD.

**Condition (a) — translator recovery, FINALIZED with the filler landed
(all 20 txhaiku records, translation_model=claude-haiku-4-5):**
paired n=17 (both arms classifiable): haiku restored-top-tier 11/17 vs opus
12/17 (haiku-only restores idx 14,16; opus-only idx 2,9,11 — same
win/loss pattern as the 13:5x interim read, plus new haiku win at 16).
Paired urgency_recovery haiku +0.127 vs opus +0.209, mean diff −0.082
(sd 0.219, |t|≈1.55, n.s. at n=17). Verdict: WITHIN NOISE — near-parity on
tier restoration; haiku recovers somewhat less probability mass on average
but the difference is not statistically distinguishable. Condition MET.

**Condition (b) — haiku equivalence on doubled n (run 67 harvest,
pairs_20260707T025842Z, 40/50 traced — indices 6–10 & 26–30 lost to a
~45-min CI step timeout on two matrix jobs, mechanical missingness only):**
- validator yield: batch-2 50/66 = 75.8% — IDENTICAL to batch-1 75.8%
  (opus comparator 60.2%). Stopping rule (<50% twice) nowhere near tripped.
- measurable-pair rate: batch-2 22/40 = 55.0% vs batch-1 27/49 = 55.1%
  (opus 48%). (Screening-passed rate: 75% vs 71% vs opus 64%.)
- penalty, screened-in pairs, pair bootstrap seed 7×5000:
  batch-2 alone −0.039 CI[−0.100,+0.014] n=22 (wide at this n, crosses zero);
  haiku POOLED −0.043 CI[−0.077,−0.012] n=49 — excludes zero and overlaps
  opus −0.036 CI[−0.080,+0.007] n=24. Condition MET; no structural failure
  (rejection reasons same category as batch 1; screening normal).

**VERDICT: GO.** tierb.start_utc stamped; batch 1 fired via fire_trigger
(haiku, num=50, max_spend=$0.25). The 10 untraced batch-2 indices get a $0
gap-fill trace (offsets 5,25 × sample 5) — chunked smaller because the two
lost jobs were ~45-min step timeouts at sample_size 10.

**Also found at harvest (queued fixes, $0):** (1) logits run 14
(gemma-3-4b-it on 119-pair stem 171223Z) hit the 4h workflow timeout with
no partial output — logits_eval.py needs offset support to chunk big
batches; until it lands, the released synthesis header's "all four
measurement batches landed" for gemma-3 is WRONG (its n=133 rests on
201750Z/154345Z/215921Z + downgrade set; the committed numbers themselves
are correct as computed) — header corrected this session. (2) activation-
patching smoke run 1 = failure; diagnosis below after log pull.
- pairs_20260710T011743Z.report.json · $0.0816 · claude-haiku-4-5 · accepted 50 · 2026-07-10T01:19:25.620281+00:00
- pairs_20260710T050657Z.report.json · $0.0718 · claude-haiku-4-5 · accepted 50 · 2026-07-10T05:08:26.072914+00:00
- pairs_20260710T092635Z.report.json · $0.0988 · claude-haiku-4-5 · accepted 50 · 2026-07-10T09:28:43.980736+00:00
- pairs_20260710T133708Z.report.json · $0.0671 · claude-haiku-4-5 · accepted 50 · 2026-07-10T13:38:46.352639+00:00
- pairs_20260710T163230Z.report.json · $0.0870 · claude-haiku-4-5 · accepted 50 · 2026-07-10T16:34:18.454866+00:00
- pairs_20260711T051145Z.report.json · $0.0713 · claude-haiku-4-5 · accepted 50 · 2026-07-11T05:13:15.738664+00:00
- pairs_20260711T051145Z.mitigation.report.json · $0.0200 · claude-haiku-4-5 · accepted — · 2026-07-12T05:30:00+00:00
- pairs_20260711T131752Z.report.json · $0.0711 · claude-haiku-4-5 · accepted 50 · 2026-07-11T13:19:16.321760+00:00
- pairs_20260712T051903Z.report.json · $0.0653 · claude-haiku-4-5 · accepted 50 · 2026-07-12T05:20:22.926599+00:00
- drift_sentinel.report.json · $0.0000 · alias · accepted — · 2026-07-12T17:30:00+00:00
- pairs_20260711T051145Z_txopus.mitigation.report.json · $0.0750 · claude-opus-4-8 · accepted — · 2026-07-13T02:00:00+00:00
- pairs_20260711T051145Z_txopus.report.json · $0.0000 · alias · accepted — · 2026-07-12T17:00:00+00:00
- pairs_20260711T051145Z_txplacebo.mitigation.report.json · $0.0310 · claude-haiku-4-5 · accepted — · 2026-07-13T02:00:00+00:00
- pairs_20260711T051145Z_txplacebo.report.json · $0.0000 · alias · accepted — · 2026-07-12T17:45:00+00:00
- pairs_20260712T163501Z.report.json · $0.1750 · claude-haiku-4-5 · accepted 100 · 2026-07-12T16:38:19.647329+00:00
- pairs_20260713T031252Z.report.json · $0.2612 · claude-sonnet-5 · accepted 2 · 2026-07-13T03:15:34.597742+00:00
- pairs_20260713T050937Z.report.json · $0.3969 · claude-sonnet-5 · accepted 7 · 2026-07-13T05:13:29+00:00
- pairs_20260713T050939Z.report.json · $0.1728 · claude-haiku-4-5 · accepted 100 · 2026-07-13T05:12:57.766407+00:00
- pairs_20260713T135755Z.report.json · $0.3966 · claude-sonnet-5 · accepted 5 · 2026-07-13T14:02:09.029909+00:00
- txcorpus_20260714T224455Z.report.json · $0.1970 · claude-haiku-4-5 · accepted — · 2026-07-14T22:58:54Z
- pairs_20260714T135150Z.report.json · $0.2102 · claude-haiku-4-5 · accepted 100 · 2026-07-14T13:56:15.801806+00:00
- quadrants_20260715T142413Z.report.json · $0.0627 · claude-opus-4-8 · accepted 10 · 2026-07-15T14:24:47.203606+00:00
- pairs_20260715T132350Z.report.json · $0.1810 · claude-haiku-4-5 · accepted 100 · 2026-07-15T13:27:42.588359+00:00
- pairs_20260716T133552Z.report.json · $0.4994 · claude-sonnet-5 · accepted 8 · 2026-07-16T13:41:22.596044+00:00
- pairs_20260717T132235Z.report.json · $0.2406 · claude-haiku-4-5 · accepted 100 · 2026-07-17T13:27:19.405134+00:00
- pairs_20260718T133020Z.report.json · $0.1836 · claude-haiku-4-5 · accepted 100 · 2026-07-18T13:33:55.127194+00:00
- quadrants_20260719T191948Z.report.json · $0.1015 · claude-opus-4-8 · accepted 14 · 2026-07-19T19:20:37.521407+00:00
- pairs_20260719T132706Z.report.json · $0.1434 · claude-haiku-4-5 · accepted 100 · 2026-07-19T13:29:52.144664+00:00
- responses_stimuli_20260721T235403Z.report.json · $0.9646 · alias · accepted — · —
