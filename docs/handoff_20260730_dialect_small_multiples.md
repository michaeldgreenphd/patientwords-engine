# Handoff — dialect small-multiples render (owner-directed, 2026-07-30)

Requested by the owner through the site-legibility session on 2026-07-30.
This is a **renderer feature request** for whichever engine session does
development work — it is *not* a task for the daily Tier B ops Routine and
must not displace any pre-registered work.

## What the site wants

The Dialect Differences page's attribution view currently embeds the
per-term sweep render (`modes/dialect/sweep/<render>`): one tall file, all
framing panels stacked, every node category drawn. The owner wants a
**small-multiples** view for visual comparison across framings:

- Per term: 3–4 simplified attribution mini-panels **side by side** —
  the standard-English baseline plus a small set of framings (selection
  driven by data, e.g. the framings with the largest |Δ| or a flip; do not
  hardcode dialect names in Python — framing labels are data).
- **Structural-tagged nodes hidden** (or fully dimmed to background), so the
  clinical-vs-off-target contrast carries each panel. Same idea as the
  4quadrant pairwise edge views, which already dim shared features.
- House figure style applies: Tufte, hairline structure, direct labels,
  site palette (clinical `#15803d`, off-target `#111827`/penalty `#b4483d`,
  structural `#c3c9d2`, paper `#faf9f5`), marks legible at thumbnail scale.
- Self-contained HTML per the modes/ convention; no external assets.

## Implementation notes (implementer's choice)

- `compare_viz.py` is the renderer; the dialect mode already renders the
  stacked sweep. A `--small-multiples` variant (or a post-pass) could emit
  `modes/dialect/sweep/<stem>_sm.html` (or similar) next to the existing
  renders.
- If tagged graph JSONs for the sweep are not retained, the committed-render
  route is proven: `scripts/dialect_invariant_core.py` already recovers
  feature/category structure from the committed HTML renders, $0, offline.
- Export the finished files to the site's `modes/dialect/` via the normal
  export path (renders are replaced wholesale, never patched in the site
  repo).

## What happens after it lands

Tell the owner (or the site-legibility session) the output filenames; the
site session will embed the small multiples on
`dialect-differences/index.html` in place of / alongside the current
full-sweep fold. The site session cannot build this itself: `modes/` renders
are engine-generated and off-limits to site-side editing.

## Cost

$0 — offline rendering from committed artifacts; no generation, no tracing,
no Anthropic calls.
