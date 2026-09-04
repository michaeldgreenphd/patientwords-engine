# Demo cues (owner choices A + B) · refreshed 2026-07-17

> Note: the Answer Depth page was folded into the Technical page on 2026-07-14.
> The depth census, "the switch close up", and the translation-by-depth split now
> live at `…/technical/#data`. URLs below point there directly (the old
> `…/answer-depth/` link still redirects, but avoid the flash in a live demo).

## A · The 90-second site walk

1. `…/technical/#data` → open the fold **"The switch, close up"**
   (`#ad-examples`) → pick the lost-late case *"My heart's been racing all
   day…"*. Say: the model formed the clinical answer (*medication*) deep in the
   network, then dropped it before speaking — the winner became *mind*. Same
   complaint, everyday wording.
2. Scroll up to **"The census, set by set"** (`#ad-blocks`): one square per
   pair, three fates. The bigger sets are 50 squares. Say: kept, lost late,
   never formed; the lost-late row is the model doing the work and dropping
   the result.
3. `…/methods.html#reading-layers`. Say: the top lanes read what the model
   would answer at each of its 26 layers; the bottom lane is the causal check —
   copy the clinical state in one layer at a time and the probability comes
   back. The deep layers carry it (this pair: 0.002 → 0.108).
4. Back to `…/technical/#data`, the router table (**"Read the failure, pick
   the fix"**). Close: translation should regain most where the answer existed
   and was lost. The current read — never-formed +0.16 tiers (n 10), lost-late
   +0.16 (n 4), kept +0.13 (n 21) — is descriptive; the confirmatory test
   (Amendment 2, in force) runs at n ≥ 15 per class. The prediction is on the
   page and will be tested either way.

Exit line: "Every number on these pages traces to a committed data file,
and the whole measurement stack is public infrastructure."

## B · The live instrument (technical encore)

Pre-check (10 seconds, before the meeting, on venue wifi):
open **neuronpedia.org/gemma-2-2b/jlens** — the launch blog's URL pattern
for their supported models. If it 404s, use the confirmed demo at
**neuronpedia.org/jlens** (their launch model; the instrument is the same).

1. Paste an everyday prompt from the close-up section (copy it off our
   site — prompts end mid-sentence by design, e.g. "…so I might need to take a").
2. Point at the grid as it fills: each column is a layer, each cell what
   the model would say at that depth.
3. Their steering control: suppress or swap a concept, re-run, watch the
   answer move. Say: this is the intervention side; our patching results
   are the batch version of this, and boosting the top-5 clinical features
   recovers the answer in 5 of 20 downgrades (random features: 0 of 5).
4. Hand them the phone.

Caveat to say out loud if asked: the lens is a readout with a top-8
floor; causal claims in our study come from patching, not the lens.
