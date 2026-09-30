# Handoff: dialect small-multiples renders — embed on the dialect page

*For the site-legibility session, 2026-07-30. From the ops/orchestrating session.*

## What landed (deployed to site `main` 2026-07-30)

Every term in the published dialect sweep now has a **small-multiples companion
render**: `modes/dialect/sweep/multi_NN.html` (+ `multi_NN.png`), one per term,
NN = the item's index in `data/dialects.json`. Each is a self-contained page
(same conventions as the sweep renders): baseline + the 3 most consequential
framings side by side, per-panel "Δ vs. baseline" badges in a strip above the
row, structural scaffolding stripped (error/bias nodes hidden, embedding
anchors fully dimmed) so the clinical/off-target contrast carries the story.
Roughly a third of the ink of the full sweep render, same evidence.

`data/dialects.json` items now carry two new fields:

- `multi_render` — the companion's filename (e.g. `"multi_07.html"`), or
  `null` on payloads older than this export;
- `multi_variants` — the framings shown, most consequential first (answer-stem
  flips weigh 2, any flip 1, ties by |Δ|; the featured-specimen weighting).

## The embed ask (owner-directed)

On `dialect-differences/`, where each term currently links only its full sweep
render, embed or link the term's small-multiples view. A natural fit: the
compact per-term view is the small multiple; "full sweep →" stays as the
deep link. Owner has also floated swapping the page's big sweep iframe for the
featured term's multi row — your call on layout.

## Do not break

- **`multi_render: null` must degrade to the current behavior** (link the full
  `render` only). Older payload shapes stay valid.
- Never edit files under `modes/` — the multi renders are engine exports,
  replaced wholesale on re-render.
- The dialects payload was re-exported 2026-07-30 from a full re-trace; the
  page's numbers (headline 160 cells / 72 flips / 4 func-flips) come from the
  payload as always. One prose sentence now drifts: the page says "traced
  July 16 and 17, 2026" — claim_check flagged it; the owner has the rewrite
  decision (`decisions_pending: dialect-prose-date-drift-20260730`). Don't
  ship new framing prose without owner approval.
- Draft labels ("draft pending domain review") stay verbatim.

## Provenance

Renders traced 2026-07-29/30 on gemma-2-2b via Neuronpedia hosted circuit
tracing, engine commit `da4792b` (compare_viz engine 3,
`render_multiples_html/png`). Trace dir: `trace_out/dialects_20260708T215356Z`
(engine repo, clean 20/20 partition: parts 01/04/09/11/14/18; overlapping
indices dedupe first-wins in the exporter).
