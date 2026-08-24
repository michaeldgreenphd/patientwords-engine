# Owner decisions — 2026-08-21 (critic findings)

The 2026-08-21 daily cycle's critic pass surfaced four instrument findings
(`docs/critic/critic_20260821.md`; dashboard ids LENS-HOST-SEPARATION-20260731,
JLENS-SENTINEL-CONTAMINATION-20260821, DRIFT-SECOND-BREACH-20260814,
CLAIM-MANIFEST-PROPERTY-GAP-20260821), plus the standing question of the
drift-series holes. The owner answered all five via the "Instrument Calls"
picker; reply received verbatim in the babysitter session, 2026-08-21:

> D1 (lens eras): label eras AND re-measure core batch
> D2 (inflated comparison): fix code, republish, Claude rewrites the 3 sentences
> D3 (drift alarm): print every breach + note Aug 14 on methods page
> D4 (new gate checks): turn on right after the Card-2 fix (start green)
> D5 (missing days): yes, annotate the three holes

## Implementation (this session, 2026-08-21)

- **D1** — `host_state_provenance` block added to `jlens_insights.py` and
  `export_jlens_depth.py` payloads (era boundaries 2026-07-31 / 2026-08-14);
  methods-page era note (site, owner-directed); census batch
  `pairs_20260711T051145Z` re-measured under the current host state, both
  served host ids, via two chained jlens-readout fires ($0). Old-era parts
  remain in git history. The tx-variant and txcorpus lens dirs stay era-mixed
  and are covered by the payload note.
- **D2** — `drift_sentinel_` stems excluded from the `jlens_insights.py`
  census glob (+ regression test); j-lens payloads regenerated and
  republished after the re-measure; the three prose spots in
  `patientwords/technical/index.html` (L523 aria-label, L1354, L1356)
  rewritten to match the corrected payload (owner-directed site-text edit).
- **D3** — `drift_sentinel.py` prints every breach chronologically plus a
  total line when more than one (+ regression test); methods page notes
  2026-08-14 as a confirmed host-side instrument change (both sentinels
  stepped on the same date, byte-identical request parameters).
- **D4** — the two property claims from critic Finding 4 landed in
  `data/claims_manifest.json` immediately after the D2 fix and republish, so
  they enter green: instruction_tuning has zero base≠it rows asserted only if
  true post-fix, and n_paired must equal the count of distinct phrase indices.
- **D5** — methods page notes the three permanent drift-series holes
  (2026-08-08 lane full; 2026-08-12 alias deliberately not created under the
  429-starvation blocker; 2026-08-19 no cycle ran).

Site-text edits above are owner-authorized by this reply (the standing
"site text is owner-only" rule is satisfied by direction, not by the owner
typing the words).

## Addendum 2026-08-22: Pilot Forty verdict (owner reply, verbatim intent)

Owner reviewed the 40 ox-alpha-generated pairs ("Pilot Forty" artifact) and replied:
interesting, but the pairs should ideally be only MINOR VERBIAGE CHANGES; hold onto
these; re-steer the stealth model to the same style changes the owner made in the
others (the owner-selected advice_mc register family).

Disposition:
- The 40 v1/v2-era pairs (`data/advice/genpilot_oxalpha_20260821T225739Z.json`) are
  **HELD**: archived, sidecar stays `pilot-unreviewed`, nothing consumes them, no
  scaling of that case-report style.
- v3 config `data/advice/gen_config_oxpilot_mc_20260822.json` steers to the owner's
  advice_mc transform: one first-person utterance rendered twice, patient side
  degraded by named register cues only (10-cue vocabulary from the owner-selected
  set), identical facts in identical order, never third-person/case-report framing.
  Exemplars are three owner-selected advice_mc pairs quoted verbatim.
- `generate()` now passes through model-declared `cues`/`facts` into each pair's
  generation block (absent when a config doesn't request them).

## Addendum 2026-08-22 (evening): v3 verdict and the v4 re-steer

Owner reviewed the v3 register-transform forty: "interesting differences... changing
between proper grammar and improper grammar, that's a fine comparison but using
specific clinical language for a condition vs. how a patient describes a symptom is
a better comparison."

Disposition:
- v3 forty (`genpilot_oxalpha_mc_20260822T011924Z.json`) **HELD** beside the v2-era
  forty: archived, `pilot-unreviewed`, unconsumed. The grammar-register axis is noted
  as a "fine comparison" but not the one to scale.
- v4 config `data/advice/gen_config_oxpilot_term_20260822.json` makes the contrast
  LEXICAL: the clinical version names symptoms/conditions with precise clinical
  vocabulary; the patient version describes the same experience in everyday words;
  grammar stays mostly clean on both sides so terminology carries the contrast.
  Each pair must declare >=2 `term_swaps` (exact substrings); exemplars are two
  owner-selected advice_mc pairs annotated with the swaps inside them.
- `generate()` passes `term_swaps` through to the generation block.

## Addendum 2026-08-23: v4 terminology-contrast pilot — PASSED, scale-up authorized

Owner, 2026-08-23 (in chat, after reading the 18 v4 pairs on Pilot Forty round 3):
"Pass it, although these aren't one for one word swaps they're still interesting
simulations."

Actions taken on the pass:
- Scale config `data/advice/gen_config_oxterm_scale_20260823.json`: same
  vocabulary-contrast task and exemplars as v4, target 80 pairs, and the nested
  `term_swaps` output schema is dropped (it broke the generator's JSON on 10/16
  v4 calls; the >=2-swaps rule stays as prose, the annotation layer goes).
- Labeling per the owner's caveat: the family is recorded as terminology-contrast
  SIMULATIONS, not one-for-one lexical swaps
  (`advice_gen_oxalpha_term_scale`, stem `gen_oxalpha_term`).
- Output stays pilot-isolated and owner-reviewed before anything consumes it.
- Fired inside the free window (closes 2026-08-24); $0, 0.25 safety ceiling.

## Addendum 2026-08-24: stealth model removed from the pipeline (owner-directed)

Owner, 2026-08-24: "Now that its Monday and the steal model is no longer free,
can you remove it from the pipeline."

- `data/advice_providers.json`: the `stealth/ox-alpha` 0/0 pricing entry is
  REMOVED (per the entry's own standing instruction). Any accidental
  post-window call now bills at the GPT-tier catch-all and the spend ceiling
  stops it immediately, instead of booking $0 against real charges.
- The ox judging program had already been declared complete earlier today
  (OpenRouter rate-limiting; final pooled agreement n=3,426, 75.6% exact,
  97.7% within one tier). No ox fires of any kind after this point.
- Archived window records keep their 0/0 cost_usd (append-only).
