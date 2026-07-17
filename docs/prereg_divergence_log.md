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

Owner reviews this log at endpoint time; anything confirmatory built on a
diverged element moves to an amendment first.
