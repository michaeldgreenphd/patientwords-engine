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

Owner reviews this log at endpoint time; anything confirmatory built on a
diverged element moves to an amendment first.
