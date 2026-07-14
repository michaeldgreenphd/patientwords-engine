# Independent replication comparison — per-model statistics (2026-07-14)

Comparator run over eight blind replicator outputs
(`/home/user/patientwords-engine/ops/replication/repl_*.json`) against the published
site statistics (`/home/user/patientwords/data/model_stats.json`).

**What the published `n_phrases` counts.** The published file's own metadata states
`dedupe: "one record per (model, clinical_prompt); mean penalty, majority flip label"`
and each per-model `penalty` block reports `n_rows_with_penalty`,
`n_phrases_with_penalty`, and `n_phrases` (the last two are equal in every block).
So published `penalty.n_phrases` counts **deduped unique clinical phrases with a
measurable (non-null) language penalty**, after excluding rows tagged
`tierb_split == "holdout"`. It is neither the row count (`n_rows`) nor the full
unique-phrase count (`n_unique_phrases`); for gemma-2-2b those are 1027 and 816
respectively while `penalty.n_phrases` is 687. Published `penalty.mean` is a
fraction; multiplied by 100 below for percentage points (pp).

## Verdict table

| Model | Pub n (penalty) | Repl n | Pub pp | Repl pp | Δpp | Pub dg/ug | Repl dg/ug | Verdict |
|---|---|---|---|---|---|---|---|---|
| gemma-2-2b | 687 | 811 total / 683 w. penalty | −3.48 | −3.5 | 0.02 | 55 / 13 | 55 / 13 | **NEAR** — holdout-exclusion scope (row-level vs phrase-level); reproduces exactly under matching population |
| gemma-2-2b-it | 122 | 122 | −6.23 | −6.2 | 0.03 | 6 / 2 | 6 / 2 | **MATCH** |
| gemma-3-4b-it | 682 | 682 | −4.65 | −4.6 | 0.05 | 42 / 8 | 42 / 8 | **MATCH** |
| llama-3.2-3b | 122 | 122 | −5.03 | −5.0 | 0.03 | 9 / 0 | 9 / 0 | **MATCH** |
| medgemma-4b-it | 119 | 108 | −3.39 | −3.3 | 0.09 | 9 / 2 | 7 / 2 | **NEAR** — replicator applied the Tier B holdout hash to Tier A phrases (documented), dropping 11 |
| olmo-2-1b | 122 | 122 | −7.23 | −7.2 | 0.03 | 9 / 1 | 9 / 1 | **MATCH** |
| qwen3-1.7b | 677 | 677 | −4.87 | −4.9 | 0.03 | 42 / 16 | 42 / 16 | **MATCH** |
| qwen3-4b | 677 | 677 | −4.90 | −4.9 | 0.00 | 46 / 7 | 46 / 7 | **MATCH** |

Tally: **6 MATCH, 2 NEAR, 0 DIVERGENT.** All penalty deltas ≤ 0.09 pp (the replicators
report at 1-decimal pp, so the residuals are rounding, not method drift). Both NEAR
cases are count deltas fully explained by a documented choice in the replicator's
`choices[]`; neither needs engine investigation of the numbers themselves.

## Per-model notes

### gemma-2-2b (NEAR — special attention)

A note on the task framing first: the published gemma-2-2b `penalty.n_phrases` is
**687**, not 677 — 677 is the qwen3-1.7b / qwen3-4b population. The question is which
population 687 corresponds to.

The replicator used the maximal population: all 1083 `model=="gemma-2-2b"` rows in
`urgency_shift.json`, **including** the steered/QC batches (`repeatability_r1-3`,
translation re-runs `txopus`/`txplacebo`/`txhaiku`, `boostgrid_*`, `*_steer`,
`ci_pairs_2panel`), holdout excluded, phrase-deduped: 811 unique phrases, of which
**683** have a measurable penalty (128 phrases are null-penalty in all rows —
clinical target unmeasurable under patient wording — so they count in flip
classification but not the penalty mean). Result: −3.5 pp, 55 downgrades, 13 upgrades.

Reconciliation with the published numbers is exact once the holdout-exclusion scope
is matched:

- **Row arithmetic.** Published `n_rows` = 1027 = 1083 − 56 holdout-tagged rows,
  i.e. the published pipeline excludes **holdout rows**, not holdout phrases. (Same
  56-row exclusion is visible for gemma-3-4b-it: 762→706, and both qwen models:
  742→686 — all exact.)
- **Phrase arithmetic.** The replicator dropped a holdout phrase *entirely*,
  including its rows in split-less re-run batches (5 such phrases). Their documented
  sensitivity — excluding holdout rows only, as the engine does — gives **816
  phrases with identical −3.5 pp and 55/13**, which equals the published
  `n_unique_phrases` = 816 exactly. The published 687 = replicator's 683 + the 4 of
  those 5 re-entering holdout phrases that have a measurable penalty.
- **Batch population.** The replicator's second sensitivity (dropping
  boostgrid/steer/ci batches) gives 810 phrases, −3.5 pp, **54**/13. The published
  downgrade count is 55, which matches only the batch-*inclusive* population — so
  the published statistics **do include steered/QC batch rows**.
- **Statistic definition.** Phrase-level unweighted mean confirmed: the replicator's
  pooled row-level mean is −4.9 pp; the published −3.48 pp matches the phrase-level
  −3.5 pp, consistent with the file's `dedupe` metadata.

**Conclusion for gemma-2-2b: the published penalty, downgrades, and upgrades
reproduce exactly under the matching population** (holdout excluded at row level,
all batches included). The only residual is a deliberate, documented replication
choice about holdout scope, worth an engine look for a different reason (see
Conclusions): 5 sealed-holdout phrases re-enter the published population through
re-run batches that carry no `tierb_split` field.

Two findings incidental to the diff: (a) the replicator independently re-derived the
holdout hash (`sha1(clinical_prompt) % 10 == 0`) and reproduced all 2037 committed
`tierb_split` labels with 0 disagreements; (b) they verified `language_penalty` =
`probabilities.patient − probabilities.clinical` of the clinical target token
against raw traces, distinguishing it from the top-1 fields.

### gemma-2-2b-it (MATCH)
122/122 phrases (no duplicates, 0 holdout exclusions — its 3 Tier B rows hash to
explore), −6.2 vs −6.23 pp (raw −6.2251, so Δ ≈ 0.005 pp), flips 6/2 exact.
Replicator noted 11 Tier A phrases hash to 0 mod 10 but correctly retained them per
the preregistration's Tier B scope; the unscoped reading would have given n=111.

### gemma-3-4b-it (MATCH)
Row-holdout exclusion 762→706 rows, dedup 706→682 phrases — both exactly match
published `n_rows`/`n_phrases`. −4.6 vs −4.65 pp. Flips 42/8 exact, including the
correct handling of a tied phrase (uninformative-vs-downgrade tie left unclassified,
matching the published 42 rather than 43).

### llama-3.2-3b (MATCH)
122/122, −5.0 vs −5.03 pp (raw −5.0347), 9/0 exact. Replicator explicitly avoided
all `*stats*` outputs and worked only from raw rows, traces, the methods text, and
the preregistration.

### medgemma-4b-it (NEAR)
Replicator: 108 phrases, −3.3 pp, 7/2. Published: 119, −3.39 pp, 9/2. Cause is
documented verbatim in their `choices[]`: this replicator applied the holdout hash
to the Tier A phrases "anyway" (per their reading of the instruction), excluding 11
of 119 — the other seven replicators, and the preregistration Amendment 1 they cite,
scope the holdout to Tier B only. All medgemma rows are Tier A, so the published
pipeline correctly excludes nothing: 108 + 11 = 119 exact, and the 2 missing
downgrades sit among the 11 dropped phrases. Penalty still agrees to 0.09 pp even
across the population mismatch. This is a replicator protocol deviation, not an
engine discrepancy.

### olmo-2-1b (MATCH)
122/122, −7.2 vs −7.23 pp (raw −7.234), 9/1 exact. Their documented alternative
(unscoped hash → n=111, −6.7 pp) confirms the published number sits on the
prereg-correct scope.

### qwen3-1.7b (MATCH)
742 rows → 56 holdout rows excluded → 686 rows → 677 phrases: all three published
counts (`n_rows` 686, `n_phrases` 677) exact. −4.9 vs −4.87 pp (raw −4.8723), 42/16
exact. Their sensitivity (unscoped hash → 656 phrases, 39 downgrades) again
confirms the published scope.

### qwen3-4b (MATCH)
Same population arithmetic as qwen3-1.7b (742→686→677, exact). −4.9 vs −4.90 pp
(raw −4.903, Δ 0.003), 46/7 exact. Replicator disclosed incidental exposure to the
collector's row-level `summary` block; it is neither deduped nor phrase-voted, so it
could not have supplied the deduped answers.

## Raw-layer sample checks

Every replicator ran a seeded 15-phrase spot-check joining rows back to the original
trace outputs (`trace_out/<batch>[__<model>]/batch_summary.part_*.json` via
`results[i]["index"]`), verifying `p_top_clinical` / `p_top_patient` against the
top-1 `predictive_spread` entries and `language_penalty` against
`probabilities.patient − probabilities.clinical`, with rounding-aware tolerance
(rows store 3–4 decimals).

**Total: 120 phrases sampled across the 8 models, 120 matched, 0 mismatches.**
(Some sampled phrases had re-trace duplicates, so slightly more than 120 underlying
rows were verified — e.g. 16 rows each for the qwen models.) All initially
suspicious cases were exact rounding-boundary artifacts (e.g. trace 0.0455 stored as
0.045; 0.3815 half-up to 0.382), resolved under the stated tolerance. The collector
row file is faithful to the raw trace layer everywhere it was probed.

## Conclusions

1. **The published pipeline reproduces.** Six of eight models match exactly at the
   replicators' reported precision (counts identical; penalties within 0.05 pp).
   The two NEAR cases are population-definition deltas, each documented in the
   replicator's own `choices[]`, and both reconcile to the published numbers
   arithmetically (gemma-2-2b: 683+4=687 / 811+5=816 / 1083−56=1027;
   medgemma: 108+11=119). No model is DIVERGENT; nothing in the numbers requires
   engine investigation.

2. **Causes of the deltas.** (a) *Holdout-exclusion scope, gemma-2-2b*: the engine
   excludes rows tagged `tierb_split=="holdout"`, so re-traced copies of 5 sealed
   holdout phrases re-enter through split-less re-run batches; the replicator's
   phrase-level exclusion removes them. Impact at published precision: none
   (−3.5 pp and 55/13 identical either way). (b) *Replicator deviation, medgemma*:
   holdout hash misapplied to Tier A, contrary to preregistration Amendment 1 —
   published value is on the prereg-correct scope.

3. **What should change.**
   - **Engine (`paired_stats_rigor.py` / collector): make the holdout exclusion
     phrase-keyed, not row-tag-keyed** — exclude any row whose `clinical_prompt`
     hashes to the holdout split when the phrase has any Tier B membership, so
     re-run/QC batches without `tierb_split` cannot leak sealed-holdout phrases
     back into published statistics. Today the leak is 5 phrases with zero effect
     at reported precision, but it is a latent integrity hole as re-run batches
     accumulate.
   - **Document the gemma-2-2b population.** The published stats include
     steered/QC/repeatability/translation-rerun batches (confirmed by the 55 vs 54
     downgrade sensitivity). That is defensible (phrase-dedup collapses re-traces),
     but it should be stated explicitly in the methods text / file metadata, and it
     is worth an owner decision whether `*_steer` / `boostgrid_*` rows — traces
     collected under intervention — belong in observational per-model statistics
     at all. The replicator's sensitivity shows the headline numbers are robust to
     dropping them (−3.5 pp; 54/13 vs 55/13).
   - **Label the count semantics.** `penalty.n_phrases` (measurable-penalty phrases)
     differs from `n_unique_phrases` by 129 phrases for gemma-2-2b; any site copy
     showing "n phrases" should say which it is (the 128 all-null-penalty phrases
     still participate in flip/downgrade counts).
   - No change needed to the holdout hash, the penalty definition, the dedup/majority
     rules, or the collector's row file — all were independently re-derived and
     verified against raw traces (2037/2037 split labels; 120/120 sample checks).
