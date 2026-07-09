# Design note — activation patching as the primary causal experiment

Chosen by the owner (2026-07-09) as the study's primary interpretability
experiment. Skeleton landed: `scripts/activation_patch.py` (CLI, pair loading,
output scaffold) plus `tests/test_activation_patch.py`. The real hooking is
stubbed — `patch_and_measure()` raises `NotImplementedError` until the CI
hooking dependency is added (see *CI dependency* below). This note fixes the
method, the grid, the output schema, and the pre-registration rules **before**
any recovery numbers are collected, so the grid and metric cannot be
reverse-fit to the effect.

## What it is

Run the model twice on a paired stimulus:

- **clean** = the clinical phrasing (`top_prompt`) — target-token probability is
  high;
- **corrupt** = the patient phrasing (`bottom_prompt`) — target-token
  probability is lower (the *language penalty* the study already measures).

Then copy the clean run's activation into the corrupt run at one site
(`layer`, `position`) and re-decode. If the target-token probability moves back
toward the clean value, that site carries the penalty. Sweep every site and the
recovery values form a **heatmap over (layer × position)** — a map of *where*
the penalty lives.

## Why it beats the API steering already done

The boost arms (`steering_boost`) perturb a hand-picked feature by a set
magnitude and watch the output shift. That is suggestive but the causal claim is
indirect: you nudged a feature you chose, and the output moved.

Activation patching is the field-standard causal localization and improves on
steering on two axes:

1. **Direct causal.** It transplants the actual clean computation into the
   corrupt run — a counterfactual substitution, not a hand-set feature value.
   Recovery is interventional evidence that the patched site is on the causal
   path, not a correlational read of an attribution graph.
2. **It localizes.** Steering answers "does this feature matter?"; patching
   answers "*which layer and which token position* does the penalty live in?"
   Sweeping the grid yields the layer depth and the position (is it on the
   swapped span, or does it propagate to the probe?) that steering cannot give.

## How it maps onto this pipeline

- **Execution.** Runs on **gemma-2-2b** by direct CPU inference in CI, exactly
  like `scripts/logits_eval.py`: open weights, bf16, forward passes only, no
  Neuronpedia, $0 compute. Like logits eval it cannot run in the sandbox (egress
  proxy blocks huggingface.co) — it is a push-to-run CI job on open weights.
- **CI dependency (new).** logits eval needs only `transformers` forward passes.
  Patching additionally needs to *read* a residual-stream activation at
  (layer, position) on the clean run and *write* it into a second forward pass.
  That requires a hooking library — **nnsight** or **transformer-lens** — added
  to the CI extra (not to the sandbox dev install). Until it lands,
  `patch_and_measure()` raises; `--scaffold` still emits the schema shape.
- **Stimuli.** clean = `top_prompt`, corrupt = `bottom_prompt`, target =
  `target_clinical_token`, identical to the fields logits eval reads.
- **Downstream.** Emits the **same `batch_summary` schema** as logits eval
  (`backend: "activation_patch"`, `source_set: null`, `results[i]["index"]` the
  1-based join key), so the existing collectors merge it unchanged. The
  per-(layer, position) recovery map rides in a new `patching` block per result
  (schema below); consumers that do not know the block ignore it.

## The experiment grid

- **Site.** Residual stream after each layer (`resid_post`), the standard
  patching site. `--hook-point` records which stream was patched.
- **Axes.** `layer` in `0 .. num_hidden_layers-1` (26 for gemma-2-2b) ×
  `position` over the corrupt run's token positions. Fixed and exhaustive — no
  cherry-picked sites.
- **Population.** The **downgrade set** — the safety-relevant flips
  `scripts/urgency_shift.py` already classifies (a redirect that drops a
  care-urgency tier). Patching the pairs where the penalty changed the
  prediction is where localization is worth the compute.
- **Position alignment (the sharp edge).** clean and corrupt differ only in the
  swapped span, but the swap need not be token-length-matched, so positions do
  not line up 1:1. The grid is defined over the **corrupt run's** positions; the
  clean activation copied in must come from the aligned clean position. Fix one
  alignment rule and pre-register it. Options, in preference order: (a) restrict
  the grid to the shared probe region after the swap, where both runs share a
  suffix and alignment is exact; (b) require length-matched swaps at generation
  time; (c) align by a fixed rule (e.g. last-token / right-anchored) and mark
  the divergent span as not-aligned. The skeleton records positions from the
  corrupt run and leaves the aligned clean index to the real implementation.
- **Output.** A recovery heatmap (layers × positions) per pair, plus a
  set-level mean map. Rendered Tufte-style: hairline grid, direct-labeled axes,
  a single sequential ramp for recovery, muted so the hot cells carry the story;
  every cell must survive thumbnail scale.

## Metric

Normalized recovery per cell:

```
recovery = (p_patched - p_corrupt) / (p_clean - p_corrupt)
```

`0` = the patch did nothing; `1` = the patch fully restored the clinical
probability; values may fall outside `[0, 1]`. Report the raw `patched_prob`
alongside the normalized value so an unstable denominator is visible.

## Output schema (extends `batch_summary`)

Top level adds `backend: "activation_patch"` and a `patching_grid` descriptor;
each result adds a `patching` block. Shape (as `scripts/activation_patch.py`
emits it):

```jsonc
{
  "mode": "2panel",
  "backend": "activation_patch",
  "graph_model": "gemma-2-2b",
  "source_set": null,                 // no transcoder -> features=false downstream
  "start_index": 1,
  "patching_grid": {                  // the fixed pre-registered grid
    "hook_point": "resid_post",
    "layers": 26,
    "align": "corrupt-run token positions",
    "metric": "normalized_recovery"
  },
  "inference": {"method": "activation_patch", "hf_id": "...",
                "dtype": "bfloat16", "measured": false},
  "results": [
    {
      "index": 1,
      "mode": "2panel",
      "prompts": {"clinical": "...", "patient": "..."},
      "target_token": " ...",
      "probabilities": {"clinical": <p_clean>, "patient": <p_corrupt>},
      "language_penalty": <p_corrupt - p_clean>,
      "patching": {
        "hook_point": "resid_post",
        "metric": "normalized_recovery",
        "placeholder": true,          // true until real hooking lands
        "clean_prob": <p_clean>,
        "corrupt_prob": <p_corrupt>,
        "layers": [0, 1, ..., 25],    // grid axis 0
        "positions": [{"index": 0, "token": "..."}, ...],  // grid axis 1
        "recovery":    [[<float|null>, ...], ...],  // len(layers) x len(positions)
        "patched_prob":[[<float|null>, ...], ...],  // same shape, raw prob
        "corrected": null             // BH-corrected significance map, see below
      }
    }
  ]
}
```

`recovery` and `patched_prob` are row-major `layers × positions` grids. In a
scaffold run every numeric field is `null` and `placeholder` is `true`: the grid
**shape** is real so downstream rendering and joins can be wired, but no numbers
are fabricated (consistent with the study's never-invent-a-number rule).

## Pre-registration hooks

- **Blind.** The grid (sites, axes) and the metric are fixed in this note before
  any recovery value is seen; changing them after data collection is a
  documented amendment, visible in git history.
- **Fixed grid.** All layers × all aligned positions, exhaustive. No post-hoc
  selection of "the layer that worked".
- **Report raw and corrected.** Publish the raw normalized-recovery map **and** a
  multiple-comparisons correction across the `L × P` cells (Benjamini-Hochberg
  over the grid) so a hot cell is not just the max of hundreds of draws; the
  corrected significance map is the `corrected` field. Screen out pairs whose
  denominator `p_clean - p_corrupt` is below a pre-set floor (recovery is
  unstable when the penalty is tiny) and report that floor.
- **Placebo / null.** Patch a control activation — a random unrelated prompt, or
  a non-swap position — as a null baseline, mirroring the placebo arm the
  steering experiment already carries. A localization claim stands only against
  the null map.
- **Denominator caveat.** Every per-cell recovery inherits paraphrase noise from
  its pair; report set-level mean maps with bootstrap CIs (cluster = phrase, as
  `paired_stats.py` already does), never a single pair's cell as a finding.
