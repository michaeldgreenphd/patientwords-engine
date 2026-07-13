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

Owner reviews this log at endpoint time; anything confirmatory built on a
diverged element moves to an amendment first.
