# Pre-registration — Tier B scale run (vacation week)

Registered 2026-07-09, before any Tier B data collection. Owner sign-off:
deck card A1 (approve) and A2 (cheaper generator), 2026-07-09. This file is
committed before the first Tier B trigger fires; any later edit is visible in
git history and must be flagged as an amendment in the analysis writeup.

## Question

Does patient (colloquial) phrasing reduce a small language model's next-token
probability of the clinical continuation, relative to clinical phrasing of the
same situation — at a scale that gives tight interval estimates of the
downgrade *rate*, not just the mean penalty?

## What is already established (Tier A, n = 132 unified pairs)

The mean penalty is real and cross-model (all CIs exclude zero); flips are
asymmetric toward care-urgency downgrades under the owner-reviewed v1 tier
vocabulary; the mechanism (gemma-2-2b feature circuit) is named and causally
manipulable with placebo control. Tier B is powered for **proportions**:
downgrade rate to ±2% needs ~1,000 usable pairs; condition contrasts at
~200–450 per cell give ±9%–±6% MDE.

## Design

- **Generation**: `claude-haiku-4-5` authors all Tier B pairs
  (`medlang-generate pairs`, standard validators). Basis: 2026-07-07
  generator test — haiku matched/beat opus on validator yield (76% vs 60%),
  behavioral screen-in (55% vs 48%), and penalty magnitude on screened-in
  pairs, at ~8–10x lower cost. Generator is recorded in every batch sidecar
  and treated as a covariate wherever Tier A and Tier B pool.
- **Target**: 1,600 accepted pairs in ~50-pair batches, topics balanced
  across the eight standing topic areas; every batch archived append-only
  with cost sidecar.
- **Throughput probe first**: one timed 20-pair batch (generation +
  screening + logits) to calibrate real batch cadence before committing the
  full schedule.
- **Measurement**:
  - CPU logits (free, all four models: gemma-2-2b, gemma-3-4b-it, qwen3-4b,
    qwen3-1.7b) on every accepted pair — the primary Tier B measurement.
  - Hosted gemma-2-2b traces (free, ~8–12 pairs/hr) run continuously all
    week on the screened subset, most-consequential first; whatever lands
    (expected 1,300–2,000 trace-pairs) feeds circuit-level secondary
    analyses.
  - Screening: `--screen-targets 0.02` (unchanged from Tier A).
- **Translation panel**: only on flagged downgrades, translator model per
  the 2026-07-09 haiku-translator arm result (recorded per-result as
  `translation_model`).

## Endpoints

Primary (confirmatory, decided before data):
1. **Downgrade rate** among prediction flips on gemma-2-2b, with
   Clopper-Pearson 95% CI; asymmetry tested by exact sign test
   (downgrades vs upgrades), tier vocabulary frozen at reviewed v1.
2. **Mean language penalty** per model with cluster bootstrap CIs
   (cluster = phrase; re-traced phrases never pool as independent).

Secondary (exploratory, labeled as such): per-topic penalty heterogeneity;
cross-model sign agreement at scale; per-model downgrade asymmetry with
BH correction across models; tokenization and length checks repeated at
scale; paraphrase-averaged item scores where paraphrase variants exist.

Analysis rules fixed in advance: dedupe by phrase before any pooled count;
generator (haiku vs opus/sonnet Tier A) enters as a fixed effect in pooled
models; no per-pair claim is reported without its paraphrase-noise caveat.

## Stopping and spend rules

- Generation ceiling: **$8 total** for Tier B (expected ~$3.20 at
  $0.002/pair; ceiling covers re-rolls). Each batch carries `max_spend`.
- Queue discipline unchanged: one running + one pending per workflow;
  chained fires only.
- If validator yield drops below 50% for two consecutive batches, pause
  generation and diagnose before spending further.
- Hosted tracing and logits are $0; they stop when the week ends,
  wherever they are.

## What would count against the hypothesis

A downgrade rate whose CI includes the upgrade rate; penalty CIs crossing
zero at n≈1,600 on any model that showed the effect at n=132; or a
generator main effect large enough that haiku-authored pairs do not
independently show the Tier A effects — any of these gets reported as
prominently as confirmations.

## Amendment 1 — 2026-07-09, before any Tier B data collection

Registered before batch 1 fired (verifiable: `tierb.start_utc` is still null
in `ops/dashboard.json` at this commit). Two additions that only restrict
the analysts, added on review of the week's autonomous-analysis plan:

1. **Confirmatory holdout.** On acceptance, every Tier B pair is assigned to
   an analysis split by deterministic hash: pairs where
   `sha1(clinical_prompt)` mod 10 == 0 (~10%) form the **holdout**. Interim
   analyses during the collection week (nightly critic runs, dashboard
   deltas, synthesis drafts) use ONLY the ~90% exploration split. The
   holdout is analyzed exactly once, after collection ends, against the
   §Endpoints as written — a garden-of-forking-paths guard for a week of
   automated interim looks.
2. **Generator-seed provenance.** Each batch's report sidecar already
   records the generator model; analyses must additionally record which
   seed-pairs file the generator saw, and the primary endpoints exclude any
   accepted pair that duplicates a seed pair verbatim (the existing dedupe
   validator makes this a no-op in expectation; the rule makes it explicit).
