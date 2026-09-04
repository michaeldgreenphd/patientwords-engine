# Negative control on the clinical-vs-patient contrast (2026-09-04)

The translation and steering paths have placebo arms. The measurement the study
rests on had none: nothing established what the language penalty reads when
there is nothing to read. This is that control.

## The confound it had to reproduce

Building it surfaced why it was needed. On `pairs_20260710T011743Z` the **patient
span is longer than the clinical span in 49 of 50 pairs, by 4.02 words on
average**. The headline effect is therefore confounded with prompt length from
the start. A control holding length constant would have been an easier test than
the treatment and would have read ~0 for the wrong reason.

So the control varies length and surface wording while holding register constant:
each clinical prompt is measured against a **longer clinical** phrasing of itself,
built by inserting a clinical-register qualifier before its `, so ` clause
(`scripts/build_control_pairs.py`, clauses in `data/control_qualifiers.draft.json`).
Achieved delta +4.20 words against the treatment's +4.02 (same median) — but see
**Length, in the unit the model sees** below: in tokens the control over-shoots.
The continuation and the target position are untouched.

Both arms measured the same way — interp-engine eager CPU float32, gemma-2-2b,
the same 50 clinical prompts, tokenization parity clean on all 100.

## Result

Every number below regenerates from `scripts/negative_control_stats.py` →
`ops/negative_control_20260904.json` (registered `cluster_bootstrap_ci`, seed
7, 10,000 resamples). The first version of this section was computed by
hand and could not be regenerated; an independent review caught that, and the
reproducibility rule this repo adopted the same day is why the script exists.

| | mean penalty | 95% CI | sign (neg/pos) | p |
|---|---|---|---|---|
| **Treatment** — clinical vs patient | **-0.0603** | [-0.1046, -0.0192] excl. 0 | 36/14 | 0.0026 |
| **Control** — clinical vs clinical +5.6 tok | **-0.0018** | [-0.0259, 0.0234] **incl. 0** | 26/24 | 0.89 |

The control reads 3.0% of the treatment mean, median -0.0002.

### Length, in the unit the model sees

The first write-up matched length in **words** (+4.02 treatment, +4.20 control).
`token_parity.n_engine` in every run records the tokenized length of each side,
so the delta the model actually saw is on disk: treatment **+4.14 tokens**
(median 5.0, range [-2, 9]), control **+5.6** (median 6.0, range
[4, 7]). The control over-shoots the treatment's length by a third and never
adds fewer than 4 tokens where 15 treatment pairs add ≤2. That is the conservative
direction — a longer-than-treatment control reading ~0 is *stronger* evidence
against length — but "matched" was only true in a unit the model does not use.

### What this licenses

**The aggregate effect survives the control, in direction.** Adding a neutral
clinical qualifier does not produce the penalty: the control's interval contains
zero and its sign split is 26/24. The treatment's direction is robust — 36 of
50 pairs negative, sign test p = 0.0026, and the near-length-matched
treatment stratum (≤1 token added, n = 12) independently shows −0.059. On this
batch and model the penalty is attributable to register rather than to length,
verbosity, or surface distance.

**The −0.06 magnitude is not robust.** The three most-negative pairs (indices
6, 20, 48) carry **45%** of the total effect. Without them the mean is
-0.0352 and the CI is **[-0.0702, 0.0002] — it includes zero**. Drop one or two and it still
excludes zero; drop three and it does not. The defensible claim is therefore the
*direction* of the effect and its rank-based significance, not −0.06 as a point
estimate. Any figure or sentence that leads with the magnitude should lead with
the sign split instead.

### What it takes away

**Per-pair penalties are noise, and so are per-pair flip labels.** The control's
per-pair sd is 0.0904 against the treatment's 0.1568 — **58% as large**
(variance ratio 0.33; the first write-up quoted only the variance ratio, which
reads smaller than it is). 20 of 50 control pairs exceed |0.05|; the extremes are
-0.2145 and +0.2766, larger than the whole mean penalty. And a neutral clause
changes the **top-1 prediction — what the site calls a redirect — in 14 of 50
pairs** (the treatment does so in 22). So the site's per-scenario penalty column
*and* its flip/downgrade labels are displays of underlying data, not estimates of
that scenario's effect.

The review also identified why: per-pair movement correlates with the clinical
baseline probability (|control penalty| vs p_clinical r = 0.49; treatment 0.67).
High-baseline pairs have room to move and low-baseline pairs do not, in both
arms. Which qualifier was inserted explains nothing (between-qualifier η² = 0.02,
permutation p = 0.92), so the effect is not the distance from the clinical term to
the target. This is bounded-scale headroom, and it is generic prompt sensitivity.

**Consequences:**

- No claim may rest on a single pair's penalty or flip label — not in page copy,
  not in a figure caption, not in an illustrative example.
- Report the aggregate as a direction with a sign test, and the magnitude with
  its outlier sensitivity stated.
- The phrase-deduplicated, cluster-bootstrapped estimate from
  `paired_stats_rigor.py` remains the only claim-grade number. On this batch all
  50 clinical prompts are distinct, so the phrase and row bootstraps coincide.

Nothing published changed on this result.

## Limitations

- **One batch, one model.** gemma-2-2b, 50 pairs.
- **Insertion, not substitution.** The real pairs swap one span for another;
  this control inserts a clause. Same register, matched length, different edit
  operation. The stronger control substitutes an LLM-authored clinical
  paraphrase of equal length — the paid `medlang-generate` path. Given the
  aggregate came back clean, that spend is not obviously warranted; given the
  per-pair spread, it would be the way to confirm the spread is generic
  prompt-sensitivity rather than an artifact of inserting a clause.
- **Qualifier clauses are draft** pending domain review, like the urgency tiers.
- The `identity` arm is an instrument check, not a control.

## Identity arm (instrument check) — passed

Each clinical prompt measured against **itself**, 50 pairs, same path. All 50
came back with the two sides byte-identical and the two measured probabilities
**exactly equal — zero pairs differed at all**, so the penalty is exactly 0.0
throughout.

That rules out a class of defect the language results could not distinguish from
a finding: state carried between the two forward passes, a mis-ordered join
between the clinical and patient sides, or a cached probability leaking across
rows. Any of those would have shown here as a non-zero penalty on identical
input. None did.

It says nothing about language, and it is not evidence the measurement is
*correct* — only that it is deterministic and correctly joined.
