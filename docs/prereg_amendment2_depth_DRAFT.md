# DRAFT · Pre-registration Amendment 2: depth-readout endpoints

**Status: DRAFT, pending owner approval. Nothing in this document takes effect,
and no depth claim upgrades past "exploratory," until the owner approves and
this file loses its DRAFT marker. Written 2026-07-12, before any data it
governs exists.**

## Motivation
The Jacobian-lens depth readout (exploratory since 2026-07-11) classifies each
pair's everyday wording as kept / lost late / never formed and suggested two
regularities: translation regains more care-urgency where the answer existed in
depth, and patching recovery concentrates in deep layers. Both were observed
post hoc on small samples. This amendment pre-registers their confirmatory
tests on data that does not yet exist.

## Sample
- Pairs from Tier B generation batches whose stamps postdate the approval
  commit of this amendment ("post-A2 batches"), measured by the standard cycle
  (gemma-2-2b trace + hosted lens + haiku translated panel).
- Amendment 1 rules apply unchanged: exploration split only until the sealed
  holdout analysis day; the holdout is never touched by interim looks.
- Exclusions, fixed in advance: pairs with unmeasurable targets (existing
  screening), lens parse failures (parse_status != ok), inverted patch grids
  (clean_prob <= corrupt_prob), and translated panels that fail to parse.

## Measurement rules (frozen as implemented 2026-07-11/12)
- Depth class: hosted Jacobian lens, top-8 readout per layer, prefix matching
  with MIN_PREFIX_CHARS = 4 (`scripts/jlens_readout.py` at approval commit).
- Recovery: probability-weighted expected care-urgency tier of the translated
  panel minus the everyday wording (`urgency_recovery`, collector at approval
  commit), reviewed v1 tier vocabulary.
- Patch profile: per-layer max normalized recovery
  (`scripts/patch_aggregate.py` at approval commit).

## Endpoints
- **H-D1 (translation-by-kind).** Among post-A2 pairs with a translated panel,
  mean urgency recovery is greater for lost-late pairs than never-formed pairs.
  Test: one-sided Mann-Whitney U, alpha 0.05, reported with cluster-aware
  sensitivity check (phrase-level dedupe as in paired_stats_rigor). Minimum
  n = 15 per class before the test runs; until then the comparison stays
  descriptive.
- **H-D2 (deep-layer concentration).** Among post-A2 downgrade pairs entering
  the patching grid, the layer of maximum recovery (excluding the trivial
  output layer) lies in the deep half (layer >= 13) more often than chance.
  Test: exact binomial vs 0.5, one-sided, alpha 0.05, minimum n = 12 pairs.
- Both endpoints report effect sizes with 95% bootstrap CIs (seed 7, 5000
  resamples), consistent with the study's existing rigor pipeline.

## Reporting
Results publish to the site regardless of direction, with the same class
labels and units the Answer Depth page already defines. A null on H-D1 is
informative: it would mean translation's benefit does not track whether the
model computed the answer, and the site text would say so.

## What this amendment does NOT change
Tier B primary endpoints, the Amendment 1 holdout, the $8/$2 ceilings, and
the one-model lens reporting rule (instruct id pending the Neuronpedia
aliasing answer) all stand.
