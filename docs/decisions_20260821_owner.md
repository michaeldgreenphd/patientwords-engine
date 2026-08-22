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
