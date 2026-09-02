# Depth probe, first cross-model run: a negative result about the instrument

2026-09-02. Route A of the interp-engine integration
(`docs/interp_engine_assessment.md`). Owner-approved scale run after the pilot.
Batch `pairs_20260706T201750Z` (13 pairs) x four models x every layer, $0,
logit lens via interp-engine's eager CPU backend.

Outputs: `trace_out/depth_pairs_20260706T201750Z__<model>/depth_probe.part_01.json`.

## What ran

| model | layers | informative layers per pair (min/med/max) | median first measurable layer |
|---|---|---|---|
| gemma-2-2b | 26 | 0 / **1** / 6 | 22.5 (87% depth) |
| llama-3.2-3b | 28 | 0 / 3 / 14 | 18 (64% depth) |
| qwen3-1.7b | 28 | 0 / 3 / 10 | 21 (75% depth) |
| qwen3-4b | 36 | 0 / 7 / 10 | 26 (72% depth) |

## The finding: the instrument cannot answer the question as configured

**The care-urgency tier vocabulary does not transfer to mid-stack logit-lens
readouts.** Mean tier-assigned mass in the top-10 spread:

| model | mid-stack (< 70% depth) | late (>= 70% depth) |
|---|---|---|
| gemma-2-2b | 0.002 | 0.28 |
| llama-3.2-3b | 0.085 | 0.433 |
| qwen3-1.7b | 0.027 | 0.469 |
| qwen3-4b | 0.042 | 0.57 |

Mid-stack coverage is one to eight percent, far below the 0.30 floor the
published analysis uses, so the expected tier is undefined for most of the
stack. On gemma-2-2b - the model carrying all the study's circuit evidence -
the median pair has **one** informative layer out of 26. The depth question
cannot be asked there at all with this configuration.

This is expected behavior for a logit lens rather than a bug: early and middle
residuals do not decode to the kind of everyday care vocabulary the tier file
was built from. The tier vocabulary was designed for final next-token
predictions, and that is where it works.

## No directional signal in the layers that are measurable

Pooled over 27 pairs with a defined final gap: **9 negative, 16 positive, mean
+0.013**. If the published behavioral downgrade had a mechanistic correlate
visible in this readout, negative gaps should dominate; they do not, and the
mean is indistinguishable from zero.

Eight pairs exceed the 0.25 divergence threshold, but in both directions
(-0.867 to +0.646), including opposite signs on adjacent pairs within one model
(gemma-2-2b #10 = -0.527, #11 = +0.646). That pattern is what noise looks like
at this sample size, not a finding.

**Nothing from this run should be published.** It is recorded here as a
methods result: the instrument runs, and it does not answer the question.

## The validity check did not get to run

gemma-2-2b was included specifically to compare its logit-lens curve against
the registered hosted j-lens depth series. With a median of one informative
layer per pair there is nothing to compare, so the logit lens remains
unvalidated against the j-lens. That check is still owed before any
logit-lens depth claim is made anywhere.

## What would have to change

1. ~~**Widen the readout window.**~~ **RUN AND SETTLED, 2026-09-02, see
   the section below: the mass is not below rank 10.**
2. **A mid-stack vocabulary.** Extending the tier file for intermediate
   representations would be a change to a reviewed instrument
   (`data/urgency_tiers.draft.json`, currently "owner-reviewed v1, domain
   review pending") and should not happen before the clinician review lands.
3. **A different readout entirely.** Tracking the target token's own
   probability by layer, or tier *mass* rather than expected tier, avoids the
   coverage floor. This is a new design, not a parameter change.

## What the run did establish

- interp-engine's eager CPU path works in CI end to end: install, load,
  `layer_logits`, teardown, four models, three architecture families, $0.
- The mode=depth branch of the logits-eval lane behaves: separate output
  directory and filename, no contamination of the behavioral
  `batch_summary` set, lane re-parked after.
- Runtime is not a constraint: 13 pairs x every layer finishes in minutes per
  model on a CPU runner.

The capability is real and reusable. The first scientific question put to it
came back negative, for a reason that is now documented.


## Step 1 result: widening the window does not help (settled)

Re-ran the identical measurement at `--topk 200` - same four models, same 13
pairs, same tier file, same 0.30 coverage floor, only the readout window
changed (`trace_out/depth_k200_pairs_20260706T201750Z__<model>/`).

| model | mid-stack coverage k=10 -> k=200 | late coverage k=10 -> k=200 | informative layers (median) |
|---|---|---|---|
| gemma-2-2b | 0.002 -> 0.003 | 0.280 -> 0.256 | 1 -> 1 |
| llama-3.2-3b | 0.085 -> 0.067 | 0.433 -> 0.389 | 3 -> 3 |
| qwen3-1.7b | 0.027 -> 0.025 | 0.469 -> 0.450 | 3 -> 3 |
| qwen3-4b | 0.042 -> 0.037 | 0.570 -> 0.540 | 7 -> 7 |

Pooled over 1,105 mid-stack layer readouts: **0.0394 -> 0.0339**. Coverage did
not rise; it fell slightly, and the median number of informative layers is
unchanged in every model.

The mechanism is arithmetic. Coverage is tier-assigned mass divided by total
mass **within the window**. Widening the window adds to both, and the tokens
between rank 10 and rank 200 are almost entirely not tier-carrying, so the
denominator grows faster than the numerator. The care vocabulary is not hiding
below rank 10; it is not in the mid-stack distribution at all.

**Conclusion: the care-urgency tier vocabulary cannot read intermediate
representations, and no window width fixes that.** Option 1 is exhausted. The
remaining choices are option 2 (a mid-stack vocabulary, which edits a reviewed
instrument and should wait for the clinician review) or option 3 (a different
readout that does not depend on tier-carrying tokens appearing in a spread).

Of those, option 3 is the more promising: tracking the *target token's own*
probability by layer has no coverage floor, because the target is fixed by the
pair rather than discovered in the distribution. That is a new design and is
not proposed here.
