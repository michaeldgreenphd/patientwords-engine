# Queued experiment: lens depth on euphemism-literalization cases

Opened 2026-07-27 (owner conversation). Status: QUEUED, not started.
Runs when the jlens-readout lane reopens — i.e. after the 17T/18T/19T trace
backfill completes. All $0.

## The finding this tests

Circuit tracing (gemma-2-2b, 2panel) shows a recurring pattern: when a patient
euphemism replaces a clinical term, the model's top next-token leaves medicine
entirely and lands on the euphemism's *literal* sense. Plumbing -> vehicles and
pipes; water -> ponds; visitor -> houseguest. Clusters in urology and
gynecology, the domains where embarrassment most drives euphemism.

Exemplars (all UNSEALED — holdout pairs excluded), ranked by clinical-mass drop:

| pair | clinical top -> patient top | clin_mass drop |
|---|---|---|
| pairs_20260718T133020Z#19 | antibiotic -> algae | +0.386 |
| pairs_20260717T132235Z#69 | UTI -> problem | +0.314 |
| pairs_20260718T133020Z#67 | thyroid -> car | +0.298 |
| pairs_20260718T133020Z#42 | antibiotic -> opportunity | +0.279 |
| pairs_20260718T133020Z#60 | uro[logist] -> mechanic | +0.261 |
| pairs_20260717T132235Z#4 | (hedge) -> pictures | +0.252 |
| pairs_20260714T135150Z#30 | bladder -> car | +0.189 |
| pairs_20260714T135150Z#76 | cold -> solution | +0.200 |

Note 135150Z#30 (leaks -> car) and 133020Z#60 (leaks -> mechanic) are the same
euphemism collapsing the same way in independent batches — a replication.

## The question

At the output we only see where the model landed. The lens distinguishes three
internally different stories that look identical from outside:

1. **absent / never formed** — the medical reading is never rank-1 at any layer.
   True comprehension failure; needs training-data or retrieval remedies.
2. **suppressed / lost late** — the medical reading forms mid-stack, then is
   overwritten before the output layer. The knowledge IS present.
3. **present but outranked** — medical reading still near the top at the end,
   losing narrowly to the literal frame. Cheapest to remedy.

(2) and (3) are what would justify a lightweight mitigation — a translation step
or steering — because the understanding already exists inside the model. (1)
would not. The committed depth exemplar (pairs_20260711T051145Z#19) is a clean
case of (3): clinical reaches rank-1 at layer 19; patient never reaches rank-1
but holds rank 2 throughout.

## Why it isn't answered already

The standing depth census (N=178: 103 retained / 61 absent / 14 suppressed) was
computed over batches in general, NOT over the frame-collapse subset. So the
classification of the algae/mechanic/car cases specifically is unknown.

## Method

Fire jlens-readout (LENS + save_raw, JACOBIAN_LENS) against the batches above,
then classify each exemplar index by the existing retained/suppressed/absent
scheme and report the distribution for the frame-collapse subset against the
178-pair baseline. Chunk ~25 pairs per fire per standing lane rules.

## Companion instrumentation gap (same theme, separate fix)

The strict specificity control — does SAME-REGISTER rewording ever produce a
non-medical target? — is not runnable today. Dialect mode records only the fixed
target token's probability per variant, not each variant's top token
(`predictive_spread` is computed but not persisted per variant). Adding it lets
us compare, head to head: rate of non-medical targets under plain rewording vs
under euphemism substitution.

What the floor CAN say today (dialects_20260723T001434Z, 208 variants, complete):
same-register rewording moves the target's probability by a median of -0.011,
and halves it in only 10% of variants. Indirect but reassuring — a model quietly
wandering to nonsense under rewording would show larger drops.

Engineering task: persist per-variant `predictive_spread` in dialect mode; add a
regression test; re-run the floor batch afterward.

## Caveats to carry into any writeup

- The lens is a correlational readout, not proof of causation. The one causal
  check (single-layer activation patch) recovered ~61%, below the 0.95 bar.
- gemma-2-2b next-token behavior is NOT deployed-assistant advice; do not
  conflate with the advice arm.
- The exemplar table is the extreme tail ranked by clinical-mass drop; typical
  redirects are milder (specialist -> generic clinician).
- Newer batches show higher redirect rates (17T 55%, 18T 50% vs 135150Z 44%) but
  generation was topic-steered, so treat these as batch-specific, not population
  estimates.

## First denominator cut (2026-07-28 daily cycle, 17T lens still pending)

Joining every gemma-2-2b urgency-collector row to landed lens depth classes
(893 of 1,781 rows lens-covered; row-level, not phrase-deduped):

| class | flips (n=430) | non-flips (n=463) |
|---|---|---|
| retained | 58.4% | 68.9% |
| absent | 32.1% | 25.1% |
| suppressed | 9.5% | 6.0% |

Flip pairs are ~10 pp less likely to retain the medical reading and
correspondingly more likely to be absent- or suppressed-class — but the
majority of flips are still retained-class: the medical reading usually
remains rank-competitive in readout space even when the output flips. The
hand-picked tail exemplars (algae/mechanic/car) are therefore not
representative of flips at large; they sit in the absent/suppressed minority.
Recompute with 17T when its lens chunk lands, and phrase-deduped before any
external use.

**17T folded in (same day, ~14:00 UTC — hardened run landed 100/100, zero
errors):** 993 rows covered; flips (n=485) 55.7% retained / 34.0% absent /
10.3% suppressed vs non-flips (n=508) 69.7% / 23.8% / 6.5%. The picture holds:
flips are enriched ~10 pp for absent and ~4 pp for suppressed readings, yet a
majority of flips remain retained-class. All flip-enriched batches now carry
lens rows; remaining uncovered rows are 16T, 221438Z, and pre-0710 stems.
