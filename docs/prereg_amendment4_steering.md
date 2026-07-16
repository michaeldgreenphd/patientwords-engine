# Amendment 4 — Swap-based steering-by-class endpoint

Status: **SIGNED AS DRAFTED, in force.** Commissioned by the owner 2026-07-15;
signed by the owner 2026-07-17 ("amendment 4: sign as drafted"). Decision
points resolved at sign-off: layers frozen at 19 and 21; pair-level
either-layer restoration is the primary outcome; the 15-per-class floor is
confirmed. Post-A4 = observational batches generated after the adoption
commit of this rename. Written after the 2026-07-14/15 exploratory pilot and
before any data this amendment governs existed.

## Motivation (what the pilot measured)

The lens taxonomy separates patient-side failures into capture (the clinical
answer never forms) and hijack (it forms mid-network and is lost late). The
exploratory steering pilot (docs/lens_steering_design.md; 27 items, gemma-2-2b)
found:

- **Additive injection cannot test the taxonomy.** Injecting the clinical
  target's readout direction restores rank 1 on essentially every resolvable
  item at strength 0.5+ regardless of class, and the dose-response below that
  (8% of items at 0.05, ~40% at 0.1, ~67% at 0.15) climbs the same way for
  both classes. A lever that restores everything cannot separate anything.
- **The swap intervention is where the classes hinted at separating.**
  Replacing the patient-side winner's readout with the clinical target
  restored hijack pairs in 21/24 layer-cases but capture pairs in only 3/6.
- **The capture arm was truncated** to n=3 of 12 because the endpoint steers
  single vocab tokens only and 9 capture targets were multi-wordpiece; any
  confirmatory design must screen for resolvability BEFORE class assignment,
  or the truncation itself confounds the comparison.

## Hypothesis

**H-S1.** Among post-A4 pairs with single-token clinical targets, classified
hijack or capture by the frozen taxonomy, the swap intervention restores the
clinical target to rank 1 at the final prompt position for a higher
proportion of hijack pairs than capture pairs.

Directional rationale: a hijack pair computed the answer and lost it late, so
removing the winner's readout should let the already-computed answer surface;
a capture pair never computed it, so removing the winner leaves nothing to
surface.

## Design (frozen on sign-off)

- **Population:** pairs from observational `pairs_*` batches generated after
  the adoption commit of this file, measured by the standard cycle
  (gemma-2-2b trace + hosted lens), exploration split only; holdout untouched.
- **Resolvability screen first:** each candidate pair's clinical target is
  probed once for steer-token resolvability (the endpoint's own 400 is the
  oracle). Unresolvable pairs are excluded BEFORE classification, and the
  excluded count is reported. No other target substitution (no first-wordpiece
  fallback: it would change what is being steered).
- **Classification second:** the adopted taxonomy (top-8 window, 2-layer
  persistence, clinical-readable conditioning) assigns hijack/capture from
  the plain lens readout, before any steering call.
- **Intervention:** one swap call per pair per layer, layers frozen at 19 and
  21 (the pilot's formation and lock-in medians). Source = the patient-side
  final-layer top-1 token; target = the clinical target. No steerStrength.
- **Outcome:** pair-level restoration = the target reads out at rank 1 at the
  final prompt position under the swap at EITHER layer (per-layer rates
  reported as secondary). Parse failures excluded and counted.
- **Test:** one-sided two-proportion exact test (Boschloo or Fisher), alpha
  0.05, hijack restoration > capture restoration.
- **Minimum n:** 15 classified, resolvable pairs per class before the test
  runs; until then the comparison stays descriptive. Power note: detecting
  the pilot's point estimates (~10/12 vs ~1/3 pair-level) needs roughly 12-15
  per class at 80% power; 15 is the floor, not the target - accumulation
  continues while batches flow.
- **Analysis code:** the pilot's parser and summary path
  (`scripts/jlens_steer.py` at the adoption commit), seed-free (no sampling).

## Reporting

Results publish to the technical page regardless of direction, in the lens
sections, labeled with this amendment. A null is informative: it would mean
the depth taxonomy does not carve steering-relevant joints, and the site's
capture/hijack language would be softened to descriptive-only.

## What this does NOT change

Tier B primary endpoints, amendments 1-3, ceilings, queue discipline, and the
one-model lens scope all stand. The 2026-07-14/15 pilot remains exploratory
and is never pooled into H-S1.

## Owner decision points at sign-off

- Approve layers frozen at 19/21, or re-derive from the census at adoption.
- Approve pair-level either-layer restoration as primary.
- Confirm the 15-per-class floor.
