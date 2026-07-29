# Steering-100: lens-steering at n=100 (analysis, 2026-07-29 ~05:10 UTC)

Owner-approved expansion (audit item 3, decisions 2026-07-28). Protocol
identical to the 2026-07-14 pilot (data/steer_pilot_spec.json): patient-side
prompts of strict flips; ADDITIVE arm injects the clinical target's readout
direction at layers 19/21 at strengths 0.25/0.5/1/2; SWAP arm replaces the
patient-side winner's readout with the target once per layer. 100 items
(spec data/steer_spec_100_20260728.json: all 16 lens-suppressed flips +
28/28/28 retained/absent/unknown), measured across 2026-07-28 chunks +
offline raw salvage (parts 01/20/26/51/76; salvage rows marked).

## Results (behavioral criterion: emitted completion token == clinical target)

- Baseline already emits the target: 12/100 (excluded from recovery).
- **Additive recovery: 87/88 steer-eligible items (98.9%)** under at least
  one grid configuration.
- Dose-response (per-call hit rate): s=0.25 -> 91%, s=0.5 -> 98%,
  s=1 -> 99%, s=2 -> 99%.
- **Swap arm: 110/170 calls (65%)** flip the completion to the target -
  the more selective intervention.
- By lens class: absent 26/26, suppressed 14/14, unknown 24/24,
  retained 23/24. Class-uniform.
- Readout-rank criterion gives the same picture (86/87) and is
  near-saturated at every strength; the behavioral criterion carries the
  dose-response signal.

## Reading, with the caveats that keep it honest

1. Injecting the target's own readout direction is a strong, aimed
   intervention - near-ceiling recovery says the patient-wording state is
   *close enough* for a small nudge to flip the output, NOT that the model
   "knows the answer" in a deployment-relevant sense. The informative part
   is the dose floor: even 0.25 x residual norm flips 91% of calls - the
   medical continuation is marginally displaced, not deeply buried. This is
   CONSISTENT with the lens census (a majority of flips remain
   retained-class in readout space).
2. Class-uniformity is the surprise: 'absent'-class flips (reading never
   rank-1 at any layer) recover as easily as suppressed ones. An externally
   supplied direction suffices even where the lens says the reading never
   formed - so lens class does NOT predict steerability at these strengths.
   At the pilot's n=20 this looked like it might; at n=100 it does not.
3. No placebo direction ran in this grid (a random-direction arm is the
   obvious control); the swap arm is the closest internal comparison.
4. EXPLORATORY, single model (gemma-2-2b), readout-space protocol, hosted
   endpoint. Distinct from the 2026-07-09 FEATURE-steering block in
   data/provenance.json (boosts 5/20, ablation 1/20) - different
   intervention, do not merge or compare the numbers directly.

Site export: as a new versioned provenance block + technical-page data in
the next publish cycle; the feature-steering v1 block stays untouched.
