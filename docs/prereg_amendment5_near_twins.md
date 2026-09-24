# Tier B Amendment 5 — near-twin sensitivity readout for the holdout endpoint

Status: **REGISTERED 2026-09-23, before unsealing.** Owner ruling 4 of
2026-09-23 (in chat): pre-register, before unsealing, a near-twin sensitivity
readout of the Tier B endpoint's consistency check, with no post-hoc pruning.
The holdout is still sealed; nothing in this amendment unseals, re-splits or
reassigns a row. **The primary endpoint is unchanged.**

Numbering: this is the fifth amendment to the Tier B pre-registration
(`docs/preregistration_amendments.md` lists 1–4). The advice-arm
pre-registration numbers its own amendments separately; its "Amendment 5"
(`docs/preregistration_advice.md`, the natural-question family) is unrelated.

## Why

Amendment 3 frames the holdout as a bias check on the interim-analysis
process: it passes if the interim process did not overfit the explore split.
That check is only as independent as the holdout items are of what interim
analysis saw. The seal is registered on exact phrases, so a near-copy of a
holdout phrase in the explore split, or on the public site, breaches nothing
but weakens the independence the check relies on.

On 2026-09-23 the seal review found that the sealed phrase of
`pairs_20260712T163501Z#17` lies inside the accepted prompt of explore row
`pairs_20260806T135728Z#9`, ruled not a leak (divergence log, 2026-09-23), and
that it is one case of a pattern: 38 of the 183 sealed phrases have a
comparison phrase at character ratio 0.90 or more. That count was computed
from phrase text alone. No measurement, outcome or holdout-row value was read
to compute it or to choose the threshold.

## What is registered

1. **Primary endpoint unchanged.** Amendment 3's endpoint analysis stands as
   adopted on 2026-07-14: the primary consistency readout (item 2), the
   gemma-2-2b significance test (item 2b), the reconciliation rule (item 3),
   the descriptive flip counts (item 4), on the population it defines (item 1,
   with the option-B exclusions recorded in `docs/prereg_divergence_log.md`).

2. **Sensitivity readout, added.** At the one endpoint run, the primary
   consistency readout (per pre-registered model: the holdout mean penalty has
   the registered sign, and it falls inside the explore split's 95% CI widened
   to the four-model simultaneous level) is computed twice, with the same
   pipeline (`paired_stats_rigor.py`, seed 7), models and explore-split
   reference interval, and both are reported side by side:
   - **(a) all sealed phrases** of the registered holdout population;
   - **(b) twin-pruned:** the same population minus every phrase whose label is
     in the frozen list `data/tierb_near_twins.json`. A label stands for its
     phrase (the accepted clinical prompt of that row), so, as under Amendment
     3, every holdout row carrying that phrase is removed.

   **Which phrases (a) covers.** Owner ruling 4 names "all 183 sealed
   phrases" (38 twins, 145 remain). 183 is the whole sealed registry. The
   endpoint population is narrower, and this amendment does not widen it:
   Amendment 3 item 1 (observational `pairs_<STAMP>` batches, phrase-deduped,
   the `paired_stats_rigor.py` pipeline) with the option-B exclusions. On
   2026-09-23, 20 of the 183 fall outside what that population can measure:
   - 10 are in the outcome-selected steered batches `pairs_20260809T172338Z`
     (6) and `pairs_20260811T190638Z` (4). Option B excludes them
     (`_SUPPLEMENTARY_STAMPS`; divergence log, 2026-08-12). 1 is a twin.
   - 10 are in `pairs_20260721T132205Z`, an observational batch that was never
     traced, so it has no measurement to report. 2 are twins.

   So (a) covers **163 phrases, and (b) covers 128 (35 twins removed)**. These
   are the 163 sealed phrases of the 20 batches in `tierb.batches` of
   `ops/dashboard.json`, every one of them traced. Each model's readout covers
   the subset that model measured. If `pairs_20260721T132205Z` is traced before
   unsealing, it joins by the population's own rule: 173 phrases, 37 twins,
   136 remain. The frozen list covers all 183, so it applies unchanged
   whichever of these the endpoint population turns out to be. This reading of
   the ruling's "all 183" is for the owner to confirm before the endpoint run.

   The explore split is not pruned: the reference interval is the registered
   one. Items 2b, 3 and 4 are not repeated on (b).

3. **Reading the two.** (a) is the endpoint result and the only input to the
   reconciliation rule. (b) is reported next to it for every model. Where the
   two agree, the writeup says the consistency result does not depend on the
   near twins; where they differ, both are reported and the difference goes
   into the limitations. Neither is dropped.

4. **The near-twin definition, fixed now** (implemented once, in
   `scripts/tierb_near_twins.py`):
   - Sealed set: `scripts/seal_check.py` `sealed_registry()`, the Amendment 1
     hash of the accepted clinical prompt over the Tier B `pairs_<STAMP>`
     batches (183 phrases).
   - Comparison set: every non-sealed phrase in the explore split or published
     on the site, that is, (i) the accepted `top_prompt` of every Tier B
     `pairs_<STAMP>` pair not in the sealed set, and (ii) every
     `clinical_prompt` in the site's `data/simulated_scenarios.json` and
     `data/simulated_archive.json`, less the sealed phrases themselves.
   - Normalization: `seal_check.norm()` on both sides (lowercase, whitespace
     runs to one space, stripped); the comparison set is deduplicated after it.
   - Metric: `difflib.SequenceMatcher(None, a, b).ratio()` with difflib's
     defaults, `a` the sealed phrase and `b` the comparison phrase (the order
     is part of the definition; the ratio is not symmetric in general).
   - Rule: a sealed phrase is a near twin iff its highest ratio against the
     comparison set is **0.90 or more**.
   - Deterministic, no seed. The frozen file records the inputs it was
     computed from: `tierb.start_utc` 2026-07-10T01:14:38Z; the sha256 of
     every Tier B batch file it read (29), of `ops/dashboard.json` and of that
     file's `tierb` block; the sha256 of both site files (byte-identical at
     site `main` `0756f2a` and at site PR #8's head, `f13d192`, from which it
     was computed); and the engine commit. The list was first computed at
     engine `6830d590`. It was recomputed on 2026-09-23 at engine `e1bc7646`,
     before unsealing, only to add the input hashes (Codex review of PR #32).
     The 29 batch files and the dashboard are byte-identical at both commits,
     and the 38 labels and every count are unchanged.

5. **No post-hoc pruning.** The list in `data/tierb_near_twins.json` is frozen
   by this registration. It is not recomputed, extended or re-thresholded after
   unsealing, and no other metric, threshold or list is used at the endpoint.
   Before the endpoint run, `python scripts/tierb_near_twins.py --site
   ../patientwords --check` is run and its result reported; if the inputs have
   changed so that the list would differ, the frozen list still governs and the
   difference is reported.

6. **Alternatives computed before registration, disclosed.** Against the same
   comparison set, on 2026-09-23: exact containment, 1 sealed phrase inside a
   comparison phrase (the #17 case) and 3 sealed phrases that contain a whole
   comparison phrase; ratio 0.95 or more, 7 sealed phrases; token-set Jaccard
   (the project's near-duplicate metric, `data/model_stats.json`) 0.9 or more,
   6, and 0.8 or more, 24. The comparison set does not move the ratio-0.90
   result: the explore split alone, the site files alone, and every non-sealed
   `pairs_*` row in the engine each give the same 38 labels.

## What this does not change

- Which rows are holdout, the hash, the seal, or the withholding of holdout
  rows from public files.
- The endpoint date rule: the holdout is analyzed once, on the owner's explicit
  "unseal" instruction.
- Any published number. No interim aggregate includes a holdout row, and the
  explore population is unchanged.
