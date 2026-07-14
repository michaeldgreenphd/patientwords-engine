# Lens steering-swap causal check — design (pilot approved 2026-07-14)

Owner approval (decision deck, evening 2026-07-14): "approve the lens
steering-swap causal check and per-position transport design: exploratory
pilot on landed downgrade pairs, design doc with fresh pre-registered
endpoints before any confirmatory claim, results on the technical page only."

## Question

The lens taxonomy is correlational: hijack-class pairs (clinical answer forms
mid-network, lost late) versus capture-class pairs (clinical-readable pairs
where it never forms under patient wording). If the taxonomy tracks a real
mechanistic difference, a minimal intervention should separate the classes:

- **Prediction P1.** Swapping the clinical token's direction into the
  residual stream at a late layer under patient phrasing restores the
  clinical answer at LOWER strength on hijack pairs (the concept was
  computed; the intervention re-asserts it) than on capture pairs (nothing
  was computed; the intervention must inject it).
- **Prediction P2.** On held-class pairs (positive controls) the same swap
  is nearly free: the answer is already present.

This uses the hosted lens endpoint's steering fields
(`steerTokens`/`steerLayers`/`steerStrength`/`swapToken`, schema read from
the open-source webapp 2026-07-11, never yet exercised by this project). It
complements, not replaces, the transcoder-feature titration: different
lever (lens-basis token direction vs named circuit feature), same $0 hosted
pattern, gemma-2-2b only.

## Status and discipline

- **Exploratory.** No confirmatory claim from this pilot. A confirmatory
  version requires fresh pre-registered endpoints ON FUTURE BATCHES, written
  and owner-signed before those runs (amendment 4 candidate). The pilot's
  job is effect-size and feasibility measurement to size that design.
- **Results live on the technical page only** (owner placement decision).
- **Correlational framing stays for the lens itself**; the swap is the
  intervention arm. Site text never says "workspace".
- Holdout untouched. Tier B cycle keeps queue priority.

## Pilot sample (landed downgrade + observational pairs, current taxonomy)

From `ops/jlens_insights.json` (rescoped taxonomy, persistence rule,
2026-07-14: 12 hijack / 16 capture / 102 held / 43 unreadable on 173 pairs):

- all hijack pairs (~12),
- capture pairs matched to the same count (~12, first by dataset order),
- 3 held pairs as positive controls.

Patient-side prompts only. Baseline lens call per pair, then a swap grid.

## Grid

- **Swap token:** the pair's clinical target token.
- **Layers:** the hijack class's lock-in median and formation median from
  the live taxonomy (currently ~19 and ~21-25), applied to every class the
  same way so classes are compared under identical interventions.
- **Strengths:** 2, 4, 8 (endpoint units; the feature-steering titration's
  recovery knee sat at 5-10 in its own units, so this brackets low).
- **Readout:** target rank at the final position across layers (same parser
  as the lens readout) plus one completion token
  (`numCompletionTokens: 1`) as the behavioral check.

## Schema risk gate (step 0)

The steering fields have never been exercised here; the response shape under
steering is unverified. Step 0 is a 2-pair probe with `save_raw` on,
parse_status recorded per call, and the parser pinned against the committed
raw before the full grid fires. Persistent 4xx/5xx on steering fields =
capability not served; record it and stop (same probe-negative pattern as
model support discovery).

## Outputs

`trace_out/<spec-stem>__jsteer_gemma-2-2b/jsteer_summary.part_NN.json`:
per (pair, layer, strength): baseline final rank, steered final rank,
steered completion token, parse status. Raw always saved for the probe.
Analysis script joins classes and renders the recovery-by-class figure for
the technical page after the pilot lands. Spec file:
`data/steer_pilot_spec.json` (prompts and targets are data, not code).

## Cost

$0 (hosted lens endpoint, NEURONPEDIA_API_KEY, no Anthropic calls).
Approximately 27 pairs x (1 baseline + 2 layers x 3 strengths) = ~189 calls,
seconds each; well inside one CI hour.
