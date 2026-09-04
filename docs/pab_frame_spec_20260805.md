# Frame-construction spec — PAB utterances into the interpretability core

**Status: methodology pre-committed 2026-08-05, before any harvested frame has
been built or traced.** Companion to `docs/pab_crosswalk_spec_20260804.md`
(same discipline) and the Tier-2 design in
`docs/patientagentbench_integration_design.md`, whose caveat this spec
implements: harvested conversations yield **independent phrasing with our
probe framing** — probe construction remains this study's instrument, stated
as such wherever results appear.

## Input

`scripts/pab_harvest_utterances.py` output: paired patient utterances (low vs
high literacy arms of the same case, joined by the contract's scenario key).
Engine-side only; CC-BY-NC-derived text never ships to the site.

## Construction rules (fixed here)

1. **Span extraction.** From each arm's utterances, extract the
   symptom/need-description span — the contiguous clause describing the
   clinical situation, excluding greetings, logistics, and tool-directed
   requests. Both arms of a pair must describe the same clinical need (the
   sweep holds the case fixed); a pair whose spans describe different needs is
   excluded and counted, never silently dropped.
2. **Carrier frames.** Each span is embedded in the study's standard
   next-token carrier frames (the `…so I need/might need…` family already used
   by the 2panel corpus), identical frame for both arms of a pair. The frame
   inventory is data (`data/pab_frames.json`, to be authored WITH this spec's
   rules before first use); no frame is invented per-pair.
3. **Targets.** Selected by the existing screening mechanism (clinical side
   first, `screen_targets 0.02`), exactly as Tier B pairs are screened. No
   hand-picked targets.
4. **Batch identity.** Harvest-derived batches use a `pabharvest_` stem —
   outside the `pairs_` observational regex by construction, so they can never
   enter the confirmatory population; they are exploratory and labeled so.

## Measures (per pair, both arms)

- **Circuit tracing (gemma-2-2b, hosted):** attribution graph; clinical
  feature mass; next-token probability of the screened target → language
  penalty between arms; flip class under the draft tier ladder (and the
  PAB-anchored collapse as sensitivity, per `ops/pab_tier_scenario.json`).
- **Jacobian lens (gemma-2-2b, hosted, `save_raw`):** per-layer rank of the
  target concept → formation depth (first legible layer, first rank-1 layer,
  persistence), capture/hijack/unreadable class per the published taxonomy.

## Endpoints (exploratory, direction declared)

1. Harvested low-literacy spans show a **negative mean language penalty**
   relative to their paired high-literacy spans (the study's core effect, on
   externally-generated phrasing).
2. Formation depth is **later/weaker** for low-literacy spans (higher
   first-rank-1 layer or absence), mirroring the published exemplar pattern.

## Disclosures fixed in advance

The utterances are written by an LLM patient simulator conditioned on
personality traits; the current corpus's simulator runs on Claude-family and
OpenRouter-hosted models, so provenance is not fully independent of the
generator family until a sweep runs the simulator on a non-Claude model
(design-note Tier 2 caveat). Frames, targets, and screening are this study's
instrument. All outputs are $0 (hosted lanes); nothing publishes without a
clean `seal_check` and an explicit owner decision.
