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
