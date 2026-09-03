# Cross-backend agreement: hosted vs. local gemma-2-2b

2026-09-03. Offline arithmetic over committed artifacts, $0, no re-measurement.
Generator: `scripts/backend_agreement.py`. Report:
`ops/backend_agreement_20260903.json`. Reproduce with:

```bash
python scripts/backend_agreement.py \
    --reference trace_out/pairs_20260710T011743Z \
    --candidate trace_out/pairs_20260710T011743Z__gemma-2-2b \
    --out ops/backend_agreement_20260903.json
```

## Why this was not already known

`scripts/retrace_consistency.py` and `docs/repeatability_sample.md` establish
that the hosted tracer **reproduces itself**: 60 designed repeat-traces, same
inputs, differences reported at recorded precision. That is a within-backend
question.

Nothing had asked the between-backend question — *do the hosted tracer and the
local forward pass report the same numbers for the same model on the same
prompts?* — even though one batch has been measured both ways since 2026-07-10.
`docs/audit1_report.md` F-M24 found a related cross-backend defect (spread depth
10 vs 5 feeding different denominators into the tier math) but did not compare
probabilities.

## The one batch that supports the comparison

`pairs_20260710T011743Z`, 50 pairs, measured twice on **gemma-2-2b**:

| run dir | backend | how |
|---|---|---|
| `trace_out/pairs_20260710T011743Z` | `hosted` | Neuronpedia graph endpoint, `max_n_logits: 10` |
| `trace_out/pairs_20260710T011743Z__gemma-2-2b` | `logits` | CPU forward pass, bfloat16, full softmax |

All 50 indices join and **all 50 prompt pairs are byte-identical** across the
two runs, so this is the same stimulus measured two ways, not two datasets.

## Result 1 — the aggregate claim survives; the per-pair numbers do not agree

Over the 71 side-measurements both backends reported:

| quantity | mean | median | max | > 0.01 | > 0.02 |
|---|---|---|---|---|---|
| per-side \|Δp\| | 0.0062 | 0.0037 | **0.0315** | 11/71 | 6/71 |
| per-pair \|Δ penalty\| | 0.0096 | 0.0064 | **0.0286** | 10/29 | 4/29 |

But the aggregate is nearly identical:

| | mean language penalty (n = 29 pairs both measured) |
|---|---|
| hosted | **−0.0648** |
| local | **−0.0653** |

**Read it this way.** The published headline is a paired aggregate, and the
aggregate agrees across two independent implementations to 0.0005 — that is a
genuine, previously unrecorded validity check in the study's favour. The
per-pair numbers are a different matter: the worst single disagreement (0.0315
at index 32 clinical) is roughly half the study's mean penalty, and 10 of 29
per-pair penalties move by more than 0.01 depending on which backend you ask.
The site's own limits already say no individual pair is evidence; this puts a
measured number on how much a featured pair's displayed 3-decimal probability
can move under a backend change.

**The cause is not identified.** Candidates, none ruled out here: the local run
is bfloat16 while the hosted dtype is unknown; hosted probabilities are recorded
to 3 decimals; and any hosted-side preprocessing is not visible to us. bfloat16
relative precision (~0.4%) accounts for roughly ±0.002 at p ≈ 0.5, not ±0.03,
so dtype alone is not an obvious explanation — but it has not been tested.

## Result 2 — hosted censoring is asymmetric, in the direction of the effect

The hosted path reads probabilities off a top-10 logit list, so a target below
that floor is recorded as null. The local softmax has no floor. Counting rows
where the hosted run reported null and the local run reported a value:

| side | censored | rate |
|---|---|---|
| clinical | 8/50 | 16% |
| patient | **21/50** | **42%** |

The patient side is censored **2.6× as often**. This follows mechanically from
the effect under study — patient phrasing pushes the clinical target down the
ranking, and down is where the top-10 floor is — but it means the hosted backend
systematically loses measurements exactly where the penalty is largest.

`scripts/paired_stats.py` already treats those as censored bounds rather than
dropping them, so this is not an unhandled bias. What is new is the magnitude:
on this batch, 42% of patient-side hosted measurements are bounds rather than
values, and the analyses that use only both-measured pairs are selecting on a
variable correlated with the outcome.

## What this does and does not license

- It **does** support a methods sentence that the aggregate penalty replicates
  across two independent measurement implementations on one 50-pair batch.
- It **does not** support any claim about a specific pair's probability to three
  decimals across backends.
- It is **one batch, one model**. Nothing here generalises to the other stems or
  to the models measured only one way.
- Nothing in it is a reason to change a published number, and nothing was
  changed.

## Next measurement this argues for

Run the same 50 prompts through **interp-engine's eager CPU backend in float32**
(`docs/interp_engine_assessment.md`; the depth probe already proved the install,
load and teardown path works in CI for four models at $0). That is a third
implementation, independently validated against TransformerLens and raw HF, and
it splits the residual disagreement cleanly:

- if the interp-engine fp32 numbers land on the local bf16 numbers, the gap is
  the hosted service's;
- if they land on the hosted numbers, the gap is our dtype;
- if they land on neither, the assumption that any of the three is exact is
  wrong, and that is worth knowing before the next claim rests on it.

Either way the comparison metric and the disagreement threshold should be
written down before the run, per the study's own pre-registration discipline.

## The verification lane (built 2026-09-03, not yet run)

`scripts/verify_probs.py` is that third implementation, wired into the existing
logits lane as `mode: verify` rather than a new trigger. The lane already
installs interp-engine for `mode: depth`, so the verify path adds a step, not a
queue.

Run it (per `docs/operators_handbook.md` §3 and the `fire-trigger-safe` skill —
this lane's fire discipline is unchanged):

```json
{"models":"gemma-2-2b","pairs_file":"data/simulated/pairs_20260706T201750Z.json",
 "limit":"50","offset":"0","mode":"verify","dtype":"float32","commit_outputs":"true"}
```

Then compare, reference first:

```bash
python scripts/backend_agreement.py \
  --reference trace_out/pairs_20260706T201750Z__gemma-2-2b \
  --candidate trace_out/verify_pairs_20260706T201750Z__gemma-2-2b \
  --out ops/backend_agreement_interp_<STAMP>.json
```

`load_run` infers which summary family a directory holds, so no extra flag is
needed; it refuses a directory holding both rather than picking one.

### Written down before the run, per the pre-registration discipline

- **Metric:** the same `max_abs_penalty_delta` and per-pair penalty deltas the
  hosted-vs-local report used. Nothing new is being scored, so nothing new is
  being tuned.
- **Threshold:** the hosted-vs-local run measured a 0.0315 maximum per-pair
  penalty disagreement. Interp-engine fp32 vs local bf16 **at or below 0.0315**
  reproduces the existing gap and leaves the cause unidentified; **materially
  below it** (call it under 0.005, roughly the rounding floor of the hosted
  numbers) points at the hosted service; **above it** means the disagreement is
  larger than either pairing so far and no implementation should be treated as
  exact.
- **Decided in advance:** none of these outcomes changes a published number.
  The only claim in scope is the methods sentence about aggregate replication.

### Two things the run records rather than assumes

1. **Tokenization parity** (`token_parity` per pair). `logits_eval.py` tokenizes
   with the raw HF tokenizer; this path goes through interp-engine's
   `to_tokens`. If those ever disagree, the row measures a different token
   sequence, and its probability gap is not attributable to the engine. The
   script prints the failing indices and the field is in the output, so a parity
   failure cannot be silently averaged into the agreement number.
2. **An uncensored target probability.** `GenStep.logits` is the full vocab
   vector on the eager backend, so the target's probability is read from the
   whole softmax. This is the same uncensored basis `logits_eval.py` uses and
   deliberately *not* the hosted path's truncated top-10 — the censoring
   documented above is a property of the hosted measurement, and reproducing it
   here would hide the thing being measured.

The output lands in its own directory under a `verify_summary.part_NN.json`
name, with `backend: "interp-engine"`. Nothing downstream globs that prefix, so
a verification run cannot be collected as a second published measurement of
prompts the study has already measured once.
