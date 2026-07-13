# Supplementary stress-test program

Owner-approved targeted sets, SEPARATE from the pre-registered Tier B run.
Shared protocol for every set in this program:

- **Generator is claude-sonnet-5** (or opus-4-8 if sonnet yield stays poor),
  never the Tier B generator; the ledger's Tier B gate keys on the generator,
  so these batches are background spend by construction.
- Seeds live in `data/simulated/<set>_seeds.json`; accepted pairs get folded
  back into the seed file after each round for dedupe.
- Measurement is the standard cycle (branch copy first, then trace, logits,
  lens). Rows stay out of pooled headline statistics until a batch-exclusion
  sensitivity check runs; all findings are exploratory.
- Generation economics: landed sonnet rounds cost $0.26-0.40 each (validator
  rejections consume most of the output tokens); fire with
  num <= 10 and max_spend 0.50.

## Sets

1. **Emergency / medically critical** (`emergency_stress_seeds.json`,
   approved 2026-07-13; round 2 generated 7 accepted pairs on 07-13 but the
   archive was lost to a push race - spend recorded, workflow fixed, round 2b
   re-fired the same day): frames whose natural continuation
   is the emergency response (ambulance, ER, hospital, 911). Question: does
   everyday phrasing downgrade at the top of the care ladder, or hold the way
   the one measured pair (fireworks/coughing child) held?
2. **Severity inversion** (`severity_inversion_seeds.json`, approved
   2026-07-13): the mirror image. The everyday wording sounds SCARIER than
   the clinical fact (palpitations vs "heart feels like it's exploding").
   Question: do models over-triage dramatic language? Expected signal is
   upgrades, the rare direction (36 upgrades vs 175 downgrades, phrase-deduped
   across seven models in paired_stats_rigor.json as of 2026-07-13).
3. **Misspelling robustness** (`misspelling_stress_seeds.json`, approved
   2026-07-13): identical frames, key term misspelled the way patients
   actually type (athsma, diabeetus, hartburn). Extends the hand-built set's
   intentional-misspelling stimuli (e.g. ihal) into a measured category.

## Fire order
One set generation per day at most, behind Tier B's daily batch in the
queue: severity inversion on 07-14, misspelling on 07-15 (nightly critic
carries this; daily ceiling comfortably holds batch + one set + sentinel).
