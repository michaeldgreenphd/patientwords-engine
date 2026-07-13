# Supplementary set: emergency and medically critical scenarios

Owner-approved 2026-07-13. A targeted stress-test set, SEPARATE from the
pre-registered Tier B dataset, asking one question: when the natural next
word is an emergency response (ambulance, hospital, ER, 911), does everyday
phrasing still downgrade it? The one measured emergency-tier pair to date
(fireworks/coughing kid) HELD across all models; the one apparent downgrade
had an unusable continuation. This set makes the top rung a studied
category instead of a hunt for specimens.

## Separation from Tier B (mechanical, not just labeled)
- Generator is `claude-sonnet-5`; the ledger's Tier B gate keys on the Tier B
  generator (`claude-haiku-4-5`), so this batch is background spend and never
  joins `tierb.accepted_pairs` or the pre-registered counts.
- The batch archive is identified by its report sidecar (`model`,
  `topics`) and this doc; the seeds live in
  `data/simulated/emergency_stress_seeds.json`.
- Claim-grade statistics (`paired_stats_rigor`) pool measured batches; when
  this set's measurements land, the nightly critic adds a batch-exclusion
  sensitivity check so headline numbers are reported with and without it
  until the owner decides its standing. Exploratory labeling applies
  site-wide, as with all urgency-tier content.

## Measurement
Standard cycle after generation lands on main: copy the archive to the
working branch (measurement guard), then trace (gemma-2-2b), logits
(4 models), lens readout. Results join the collector's urgency rows like
any other batch; the Start Here ladder can then reference measured
emergency-tier pairs directly.
