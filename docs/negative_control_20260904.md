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
Achieved delta **+4.20 words against the treatment's +4.02**, same median. The
continuation and the target position are untouched.

Both arms measured the same way — interp-engine eager CPU float32, gemma-2-2b,
the same 50 clinical prompts, tokenization parity clean on all 100.

## Result

| | mean penalty | 95% CI (10k bootstrap, seed 7) | |
|---|---|---|---|
| **Treatment** — clinical vs patient | **−0.0603** | [−0.1051, −0.0183] | excludes 0 |
| **Control** — clinical vs clinical +4 words | **−0.0018** | [−0.0269, +0.0236] | **includes 0** |

The control reads **2.9% of the treatment mean**, with a median of −0.0002.

### What this licenses

**The aggregate effect survives the control.** Adding four words of neutral
clinical qualifier to a prompt does not produce the language penalty; the
treatment's interval excludes zero and the control's contains it. On this batch
and this model, the penalty is attributable to register rather than to prompt
length, verbosity, or surface-wording distance. That is the claim the study
needed and did not previously have.

### What it takes away

**Per-pair penalties are noise.** The control's per-pair spread is large:
sd 0.0895, which is **33% of the treatment's variance**, with **20 of 50 control
pairs exceeding |0.05|** and individual pairs reaching ±0.28 — larger in
magnitude than the study's entire mean penalty.

So adding four semantically neutral clinical words to a prompt moves that pair's
measured penalty by more than the effect being studied, in a third of cases.
Combined with the bfloat16 term measured the same day (up to 0.031 per pair),
the per-pair number is not a measurement of anything stable.

**Consequences:**

- No claim may rest on a single pair's penalty. Not in page copy, not in a
  figure caption, not in an example chosen to illustrate.
- The site's per-scenario penalty column is a display of the underlying data,
  not an estimate of that scenario's effect, and should not be read as one.
- The aggregate, phrase-deduplicated, cluster-bootstrapped estimate that
  `paired_stats_rigor.py` produces remains the only defensible number.

Nothing published changed on this result. The bootstrap above resamples rows for
a quick read; the registered analysis clusters by phrase and is unchanged.

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
- The `identity` arm (clinical vs itself, penalty must be exactly 0) is an
  instrument check, not a control; it is built by the same script.
