# Pre-registration divergence log (Tier B)

The pre-registration (`docs/preregistration_tierB.md`) is frozen; this log
records where practice diverged so the endpoint writeup and any amendment can
disclose each item. Divergences are recorded when they happen, never
retro-edited into the frozen document.

| date | divergence | pre-registered | actual | disposition |
|---|---|---|---|---|
| 2026-07-10 | no 20-pair throughput probe | one timed 20-pair calibration batch before the schedule | cadence calibrated from the first full 50-pair batch (go/no-go night) | disclose in writeup |
| 2026-07-12 | batch size doubled | ~50-pair batches | batches 8+ accepted 100 pairs each (owner: "go 100", same spend ceilings) | disclose in writeup; ceilings unchanged |
| 2026-07-11 → | measurement matrix expanded | CPU logits on four models | seven models measured (llama-3.2-3b, olmo-2-1b, gemma-2-2b-it added; medgemma-4b-it probed 07-13) | extra models are secondary/exploratory; primary endpoints stay on the pre-registered four |
| 2026-07-14 | interim analysis population made explicit | registration named no row filter for interim summaries | interim (site) statistics restricted to observational `pairs_*` generation batches; steered, screened, imported, and re-traced rows moved to a labeled sensitivity analysis | precision, not a change of endpoint; referee worklist item 1 |
| 2026-07-14 | BH correction family split | one BH family implied across "the four models" | BH run within registration family (pre-registered four; post-registration additions as a separate exploratory family); the merged 8-model view kept in the statistics file for comparison | precision; both views published |
| 2026-07-14 | holdout exclusion made phrase-keyed | holdout defined per pair at assignment | exclusion keyed on clinical phrase so split-less re-run rows of a holdout phrase cannot leak into interim numbers; holdout phrases also withheld from the public site data files | strengthens the seal; amendment 3 adopted 2026-07-14 (`docs/prereg_amendment3_holdout.md`) |
| 2026-07-13 → 07-17 | holdout seal gaps in several exporters (Audit 2 F2-H01/02/03/04/05/06/07/09) | Amendment 3: holdout withheld from every public file | `jlens_insights.py`, `export_jlens_depth.py`, `retrace_consistency.py` had no holdout filter; the batch-name gate rejected alias/re-run stems (`_txopus`, `repeatability_r*`), so `export_archive.py`/`urgency_shift.py` leaked suffixed-batch holdout; sealed phrase-keyed across all exporters and republished every public file holdout-clean (full sweep = 0) | corrective; no endpoint change. Sealed rows/phrase-text were public 2026-07-13→17 and are now purged; disclose the exposure window in the endpoint writeup |
| 2026-07-17 | split hashed on trace-time prompt for probe-extended pairs (Audit 2 F2-H08) | split assigned on the ACCEPTED clinical prompt (`sha1(clinical_prompt)`) | a screening probe extension made 6 Tier B pairs' trace-time prompt hash differ from the accepted one, flipping split membership; now sealed under EITHER string (conservative union), so the 6 are all withheld. The registered assignment is NOT re-split (Amendment 3 forbids it) | disclose; the 6 pairs stay conservatively sealed pending owner/amendment review before any unsealing |
| 2026-07-16 | registered holdout endpoint date passed without the endpoint run (Audit 2 F2-M31) | endpoint analysis on 2026-07-16 | owner-directed deferral: the holdout stays sealed until an explicit "unseal" instruction; no interim look touched it | disclose; deferral is owner-directed and logged here |
| 2026-07-17 | confirmatory population made explicit — POPULATION-DEF option B (owner decision) | registration named no explicit supplementary-set exclusion | the outcome-selected supplementary sets (emergency/severity, `claude-sonnet-5`, 2026-07-13: `pairs_20260713T031252Z`, `_135755Z`, `_050937Z`) share the `pairs_<STAMP>` stem; excluded from the confirmatory population by explicit stamp and reported sensitivity-only | precision, not an endpoint change; immaterial (gemma-2-2b −3.13pp vs −3.08pp all-in), no significance flip |
| 2026-07-12 → 2026-09-23 (site PR michaeldgreenphd/patientwords#8, merged 19:48Z as `d04ab5a`) | a render of holdout row `pairs_20260710T163230Z#44` stayed served on the site | Amendment 3: holdout phrases withheld from every public file | `modes/simulated/pairs_20260710T163230Z/index_44.html` carried the row's sealed clinical phrase and its patient sentence; withholding took the row out of the payload on 2026-07-14, but the exporter never deleted renders and the seal check skipped `modes/`, so the file stayed live, unlinked, until its removal. The 2026-07-13 → 07-17 row above ("every public file holdout-clean") was wrong about this file | **breach** (owner ruling 2, 2026-09-23); removed by site PR #8; the exporter now prunes unlisted renders; disclose the window in the endpoint writeup. Detail below |
| 2026-09-23 (on the site since 2026-08-08) | the sealed phrase of `pairs_20260712T163501Z#17` occurs inside the accepted clinical prompt of explore row `pairs_20260806T135728Z#9` | the seal is the exact accepted clinical prompt (Amendment 1 hash; Amendment 3 phrase-keyed) | #9's prompt is a different, longer phrase that hashes explore; it is published in three site data files and one traces-site render; the two are near-duplicates | **not a leak** under the registered exact-phrase seal (owner ruling 1, 2026-09-23); allowlisted by the containing field's full sha256 in `data/seal_allowlist.json`; covered by the near-twin readout (Tier B Amendment 5). No number changes. Detail below |
| 2026-07-19 → removal: first site publish after the engine PR "Make the Tier B seal hold on the public site" merges (date: ____) | patient-side text of holdout rows published in site `data/jlens_swaps.json` | Amendment 3 withholds holdout phrases from public data files; the registered seal covers the clinical phrase only | `scripts/export_pair_swaps.py` had no holdout filter, so the file carried, keyed by label, the verbatim patient sentence, patient-side swap span and target token of holdout rows (34 keys in its first version, 32 by the accepted prompt and 2 by the trace-time prompt; 187 at site `0756f2a`, 184 and 3) | not a breach of the seal's letter (patient side); withheld from now on (owner ruling 3, 2026-09-23); disclose. Detail below |
| 2026-07-21 → 2026-09-23 | the daily seal check did not read most of the site | a seal check over every published artifact (holdout-seal-check skill; Routine publish gate) | `scripts/seal_check.py` skipped any path whose string contained `data/simulated`, `modes`, `.git` or `trace_out`, and matched raw text only; on the site that left 468 of 524 scannable files unread, including the three per-row data files and every render, and it could not see an HTML-escaped phrase | corrective (2026-09-23): excludes only the engine's own `data/simulated/` and `trace_out/` by resolved path and `.git` by path component, decodes HTML entities and JSON escapes, reads a hash-keyed allowlist; every daily "CLEAN" in the window is qualified accordingly. Detail below |

Owner reviews this log at endpoint time; anything confirmatory built on a
diverged element moves to an amendment first.

## 2026-08-12 — steered generation stamps added to the option-B exclusion

`pairs_20260809T172338Z` and `pairs_20260811T190638Z` (steered generation
rounds 1-2: seeded from owner-validated downgrade pairs with counterexample
steering, round 2 slot-constrained) are outcome-selected by construction and
join `_SUPPLEMENTARY_STAMPS` in `paired_stats_rigor.py` (and the mirror in
`convergence_tracker.py`) as sensitivity-only, per POPULATION-DEF option B
(owner decision 2026-07-17). Caught before any confirmatory number using the
leaked population was published: the stale site `model_stats.json` (2026-08-08)
predates both batches, and the leaked-population preview run of 2026-08-12 was
scratch-only. Regression test added
(`test_steered_generation_stamps_are_sensitivity_only`).

## 2026-09-23 — the holdout seal on the public site: owner rulings 1–4

Labels, lengths, hash prefixes and counts only; this entry quotes no sealed
phrase and no holdout-row text. Evidence: the seal and disclosure briefs of
2026-09-23 (engine `6830d590`, site `0756f2a`, traces site `91b1a6a`), checked
by a second agent and a third review; the checker runs below were repeated for
this entry.

**(i) Breach: the `pairs_20260710T163230Z#44` render (ruling 2).**
`modes/simulated/pairs_20260710T163230Z/index_44.html` (file sha256
`53df594085a4`) holds one occurrence of the row's sealed clinical phrase (43
characters, sha256 `59173b4f0156`) and one of its patient sentence. It was
added at site `e7d32f3` on 2026-07-12, when the row was a listed scenario; the
payload stopped listing it at `b0f8ef7` on 2026-07-14, and no page has linked
it since, but it answered HTTP 200 at its github.io path on 2026-09-23. It was
the only holdout-row render among the site's renders, and no holdout row has a
render on the traces site (0 of 194). Exposure window: 2026-07-12 to 2026-09-23.
Site PR michaeldgreenphd/patientwords#8 merged at 19:48:28Z as `d04ab5a`,
GitHub Pages finished building `d04ab5a` at 19:50:35Z, and the github.io path
answered HTTP 404 at 21:09:53Z. Git history is left as it is (2026-07-21 precedent). Two changes stop a
repeat: `scripts/export_frontend_simulated.py` now deletes exporter-named renders
that no export or site file lists (`scripts/render_prune.py`; a dry run against
site `0756f2a` lists 236 such files, this one among them), and the seal check
now reads `modes/`. Both refuse over a site checkout that keeps tracked files
off disk (the cloud containers' sparse clone leaves `modes/` out), where the
prune would otherwise delete nothing and the check would read nothing there.

**(ii) Not a leak: `pairs_20260712T163501Z#17` inside `pairs_20260806T135728Z#9`
(ruling 1).** The sealed phrase of #17 (64 characters, sha256 `d8ab8d650bef`,
sha1 mod 10 = 0) lies inside the accepted clinical prompt of #9 (66 characters,
sha256 `6b5a904e3cce`, sha1 mod 10 = 5, explore). The seal is registered on exact
accepted prompts, and Amendment 3 widened it to the same phrase anywhere, not to
phrases that contain it. #9 came from campaign batch 20 (fired 2026-08-06),
25 days after #17, from the same term pair; the generator deduplicates only
against its seed file and its own run, and the run's prompt size makes it
unlikely it saw #17 (an inference: the fire's seed parameters were not
recorded). It is a different next-token measurement: the prompts differ,
and so do the targets. #9 is published in site
`data/simulated_scenarios.json` (1 occurrence), `data/simulated_archive.json`
and `.csv` (3 each) since 2026-08-08 (`4854f7d`, `2544d90`), and HTML-escaped
in the traces-site render `t/pairs_20260806T135728Z/index_09.html` since
2026-08-10. #17's own row was never on the site under its label, apart from
the patient-side text in (iii) and one label-only row in three versions of
site `data/urgency_shift.json` on 2026-07-14, inside the window row
2026-07-13 → 07-17 already discloses. `data/seal_allowlist.json` records the
ruling keyed on #9's full `top_prompt` sha256 plus label, containing row and
field; the checker suppresses #17 only where that exact field appears whole,
between field delimiters (a JSON or CSV string's quotes, an HTML element's `>`
and `<`, a CSV cell's commas and line ends), so a bare occurrence, or the
field's text run on into other words, still fails. The pair is a near-duplicate (character
ratio 0.985), one of 38 sealed phrases with an explore or published twin at
0.90 or more; Tier B Amendment 5 registers the sensitivity readout for all 38.
No analysis used #17; #9 stays in the explore population as registered; no
number changes.

**(iii) Patient-side exposure: site `data/jlens_swaps.json` (ruling 3).** The
file is keyed by label and gives, per pair, the target token, the patient-side
swap span and the verbatim patient sentence. `scripts/export_pair_swaps.py` had
no holdout filter. Counted by the rule this entry applies (the accepted prompt
or, the conservative reading of row 2026-07-17, any trace-time prompt), its
first version (site `b1f58c2`, 2026-07-19; 370 keys) carried 34 holdout keys:
32 whose accepted prompt hashes holdout and 2 whose trace-time prompt does
(`pairs_20260712T163501Z#19`, `pairs_20260712T163501Z#48`). Site `0756f2a`
carries 187: 184 by the accepted prompt and 3 by the trace-time prompt (those
two and `pairs_20260710T092635Z#8`). It carries no clinical phrase and no
measurement, and the census it serves excludes holdout rows, so the page drew
none of them; the entries were downloadable. The engine copy
`data/jlens_swaps.json` carried the same. The exporter now applies the same
rule as the other exporters, publishes `holdout_withheld`, and refuses when the
sealed set computes empty. Regenerated from the current inputs: 2,263 entries
become 2,076, 187 withheld, 0 holdout keys left, every remaining entry
byte-identical. Removal: the first site publish after the engine PR merges.

**(iv) The checker's blind spots, 2026-07-21 → 2026-09-23.** From its first
commit (`c7be99ad`, 2026-07-21) `scripts/seal_check.py` skipped every path
whose string contained `data/simulated`, `modes`, `.git` or `trace_out`,
meaning to skip only the engine's registry sources. On the site that also
skipped `data/simulated_scenarios.json` and `data/simulated_archive.{json,csv}`
(`data/simulated` is a prefix of their paths), every file under `modes/`, and
`.github/` (`.git` is a prefix of it): 468 of the site's 524 scannable text
files at `0756f2a`. It also matched raw text only, and 72 of the 183 sealed
phrases contain an apostrophe, which a rendered page escapes. What that hid:
#17 inside #9 in the three data files since 2026-08-08 (ruled not a leak) and
the #44 render since 2026-07-12 (the breach). HTML decoding finds nothing
further on the site; the traces site was never a checker root. Every daily
"seal check: CLEAN" in the window, and the 2026-08-25 hand scan recorded as
`SEAL-REGISTRY-COVERAGE-20260825` in `ops/dashboard.json` (which, by inference,
used the same exclusion), therefore covered only the files it read. Checker
runs on 2026-09-23 (site root only): the shipped checker on site `0756f2a`
reports CLEAN; the fixed checker with the allowlist reports the #44 render
(exit 1) on `0756f2a` and CLEAN on site PR #8's branch, where without the
allowlist it reports #17 in the three data files. The analysis-side seal is
unaffected: no interim aggregate included a holdout row.
