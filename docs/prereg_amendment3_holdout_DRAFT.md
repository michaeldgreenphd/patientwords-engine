# Amendment 3 (DRAFT) — Holdout analysis plan, precision, and reconciliation

Status: **DRAFT, not in force.** Written 2026-07-14 in response to the referee
panel (`docs/referee_panel_20260714.md`, worklist item 4). Nothing here is
binding until the owner signs off; the sign-off date and channel get recorded
in this header, as with amendments 1 and 2. The holdout stays sealed while
this is a draft.

## What this amends

Amendment 1 created the Tier B holdout: 10% of Tier B phrases, assigned by
`sha1(clinical_prompt) % 10 == 0` (`scripts/tierb_split.py`), excluded from
every interim analysis until a pre-registered endpoint run. Amendment 1 did
not specify (a) what the endpoint analysis of the holdout is, (b) what
precision the holdout can actually deliver, or (c) what happens when the
holdout and the exploration split disagree. This draft fixes all three, and
discloses two integrity corrections made on 2026-07-14.

## Disclosures (already in effect, logged in the divergence log)

1. **Phrase-keyed sealing.** The original exclusion was row-tag-keyed; re-run
   batches produced split-less rows of holdout phrases that could leak into
   interim numbers (5 phrases / 11 rows found by the replication check).
   Exclusion is now keyed on the clinical phrase: a phrase flagged holdout
   anywhere is excluded everywhere.
2. **Publication-side withholding.** Until 2026-07-14 holdout rows were
   excluded from aggregates but individually public in the site payloads.
   From 2026-07-14 the exporter and the urgency publisher withhold holdout
   phrases from the public data files. Rows published before that date were
   visible in git history; the seal that matters for inference is
   analysis-side (no interim aggregate has ever included them), and that seal
   held. The writeup discloses this history rather than claiming the rows
   were never visible.

## Sealed inventory (as of this draft)

53 holdout phrases, each measured on all four pre-registered models
(gemma-2-2b, gemma-3-4b-it, qwen3-1.7b, qwen3-4b). The count grows with new
Tier B batches (10% of accepted phrases by hash).

## Honest achievable precision

Derived from the exploration split's per-phrase spread (implied SD from the
2026-07-14 bundle), the holdout mean-penalty CI half-width at today's n=53 is:

| model | implied per-phrase SD | half-width at n=53 |
|---|---|---|
| gemma-2-2b | 0.141 | ±3.8 pp |
| qwen3-1.7b | 0.206 | ±5.6 pp |
| qwen3-4b | 0.247 | ±6.6 pp |
| gemma-3-4b-it | 0.260 | ±7.0 pp |

With exploration means between −3.4 and −4.9 pp, a holdout-only significance
test of the mean penalty is adequately powered on gemma-2-2b only, and
marginal to underpowered elsewhere. For the flip-asymmetry endpoint the
holdout is far weaker still: the exploration flip rate implies roughly 5
flips among 53 holdout phrases, so no sign test on the holdout alone can be
informative. The holdout is therefore specified below as a **bias check on
the interim-analysis process**, not as an independently powered replication.

## Endpoint analysis (proposed, binding on sign-off)

1. **One run.** The holdout is analyzed once, at the pre-registered endpoint
   (end of the Tier B collection week), by the same pipeline
   (`paired_stats_rigor.py`, seed 7), on the four pre-registered models,
   observational `pairs_*` batches only, phrase-deduped.
2. **Primary readout: consistency, not significance.** For each
   pre-registered model, the holdout passes if (a) the holdout mean penalty
   has the registered sign, and (b) it falls inside the exploration split's
   95% CI widened to the four-model simultaneous level. Expected pass
   probability is high if and only if the interim process did not overfit
   the exploration split; that is what the holdout is for.
3. **Reconciliation rule.**
   - All four models pass: the endpoint writeup reports pooled all-Tier-B
     estimates as the headline, with the holdout check disclosed as passed.
   - Any model fails on sign: the writeup headline for that model is the
     holdout estimate, the discrepancy is reported prominently, and no
     pooled estimate is claimed for it.
   - Any model fails only on interval: both estimates are reported side by
     side, the pooled estimate is labeled "holdout-discrepant", and the
     discrepancy is carried into the limitations section.
   In no case is the holdout re-analyzed, re-split, or extended after
   unsealing to change an outcome.
4. **Flip asymmetry.** Holdout down-vs-up counts are reported descriptively
   with no test (expected ~5 flips); the asymmetry endpoint remains a
   full-Tier-B analysis as registered.
5. **No interim peeks.** Until the endpoint run, holdout phrases stay
   excluded from every published aggregate and withheld from public data
   files. This draft does not unseal anything.

## Owner decision points

- Approve the consistency-not-significance framing (§ Endpoint 2), or
  require a holdout-only significance test on gemma-2-2b (the one model
  powered for it).
- Approve the reconciliation rule as written, or tighten it.
- Confirm the endpoint date (end of Tier B collection, 2026-07-16 as
  currently planned).
