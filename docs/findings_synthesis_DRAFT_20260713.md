# What we found: patient words make small language models worse at medicine

**Status: DRAFT (weekly deep refresh, 2026-07-13). This is a from-scratch
rewrite against every artifact landed through Tier B batch 9; the released
synthesis (`docs/findings_synthesis.md`, owner-signed 2026-07-09) is
untouched and remains the citable version until the owner rewrites this in
their own voice. All counts and estimates below are the phrase-deduped
claim-grade numbers (`paired_stats_rigor.json`: one record per
(model, clinical phrase), cluster bootstrap for penalties, Clopper–Pearson
for rates, BH-corrected sign tests). The Amendment-1 confirmatory holdout
(sha1 rule, ~11% of Tier B phrases) is excluded upstream of every number
here and stays sealed until the pre-registered endpoint. The current corpus
is LLM-written stress stimuli — the owner classifies this run as a
demonstration pending patient-sourced exemplars and clinician review.
Every number below was recomputed from its committed artifact today.**

One-line summary: when the same medical situation is phrased the way
patients actually talk instead of in clinical terms, small open models
become measurably less likely to continue toward the clinical action — the
effect persists at 4× the sample of the released synthesis (smaller than
first estimated, see §1), it is asymmetric toward less-urgent care, and we
can see, name, causally steer, and now layer-localize the circuit
responsible.

Everything below is next-token probability on gemma-2-2b (with attribution
graphs) and gemma-3-4b-it / qwen3-4b / qwen3-1.7b (behavior only). Three
further models (llama-3.2-3b, olmo-2-1b, gemma-2-2b-it) have 3-pair probes
only — no claims; biomistral-7b was excluded on supply-chain grounds
(pickle-only upstream weights). Nothing here measures harm in deployed
systems; see Limits.

## 1. The penalty survives scale — and honest accounting shrinks it

Interim Tier B numbers (holdout excluded), one record per phrase:

| model | mean penalty | 95% CI | n phrases | source |
|---|---|---|---|---|
| gemma-2-2b | −0.034 | [−0.046, −0.023] | 553 | `paired_stats_rigor.json` |
| gemma-3-4b-it | −0.053 | [−0.074, −0.032] | 545 | 〃 |
| qwen3-4b | −0.060 | [−0.081, −0.039] | 540 | 〃 |
| qwen3-1.7b | −0.052 | [−0.070, −0.034] | 540 | 〃 |

Every CI excludes zero; two model families and two measurement backends
agree. The most important change since release is the direction of the
point estimates: at n = 132 the per-model means ran −0.07 to −0.10; at
n ≈ 540+ they run −0.034 to −0.060. The effect is real but roughly half
the size the early corpus suggested — the early phrase set was enriched
for strong items. This shrinkage is exactly what the accumulation curves
show (`convergence.json`), and the endpoint analysis on the sealed holdout
is the number that should be quoted as final. Convergence also ordered the
models: the gemma-3-4b-it downgrade pattern was still chance-plausible at
36 phrases (4 down / 1 up, sign p = 0.375) and stopped being so by 155
(17 / 2, p = 0.0007).

Cross-model per-pair correlations (gemma-2 vs qwen3-4b r = 0.62, vs
qwen3-1.7b r = 0.52, ~70% sign agreement) were computed on the earlier
unified 132-pair set (`paired_stats_out.json`) and are due for an endpoint
refresh; treat them as provisional.

## 2. The failure that matters is a changed answer, and it points down

Phrase-deduped flip counts on the owner-reviewed tier vocabulary
(v1, 2026-07-09; domain review pending):

- gemma-2-2b: 47 downgrades vs 11 upgrades (BH q < 10⁻⁴); downgrades are
  17.3% of its 271 deduped flips (CP 95% [13.0%, 22.4%])
- gemma-3-4b-it: 35 vs 7 (q = 3×10⁻⁵); 13.9% of 252 flips [9.9%, 18.8%]
- qwen3-4b: 36 vs 5 (q < 10⁻⁴); 15.0% of 240 flips [10.7%, 20.2%]
- qwen3-1.7b: 33 vs 10 (q = 6×10⁻⁴); 13.5% of 245 flips [9.5%, 18.4%]

Every model, including the newest instruction-tuned one, redirects toward
less-urgent care several times more often than toward more-urgent care.
Pooled tallies that count re-traced phrases run higher and are
pseudoreplicated (gemma-2's raw row count is 820 vs 678 unique phrases) —
do not cite them. Concrete live-trace cases are unchanged: "urinary tract …
blocked up" calls a urologist at 0.20; "her water was blocked up" calls a
**plumber** at 0.68 (`data/urgency_shift.json`).

## 3. Mechanism: the wording swaps which circuit runs, late in the model

From the attribution-graph corpus (`docs/analyses_20260708.json`, computed
on the pre-Tier-B corpus, n = 365 pairs): a clinical/patient pair of the
same sentence shares only ~47% of its traced circuit (median 0.467);
clinical phrasing recruits named medical-language features, patient
phrasing replaces much of that stack with features for the idiom's surface
topic (sleep, food, plumbing, money), and both stacks live at the same
depth (mean layer ~20 of 26).

New since release, activation patching localizes where the divergence is
decided (`data/patch_profile.json`, exploratory, 7 usable downgrade pairs,
1 screened out for an inverted denominator): patching a single clean-run
activation into the corrupt run recovers little in layers 0–6 (mean max
normalized recovery ≤ 0.18), jumps at layers 7–10 (~0.46–0.51), and
approaches full recovery at layers 17–25 (0.9–1.0). The best single patch
sits at layer ≥ 13 in 6 of 7 pairs, and at a *downstream* position rather
than term-adjacent in 6 of 7. Consistent with the graph picture: the
penalty is not decided at the swapped words, it is decided late, where the
two readings compete.

## 4. The circuit is causal, and it behaves like a dose

Unchanged from release, re-verified against `data/provenance.json`
(`steering`, `steering_titration`): boosting the clinical circuit's top-5
features while the model reads the patient words recovers 5/20 downgrades
(muting the idiom's features: 1/20; random-feature placebo: 0/5).
Dose-response on the recovered subset: strength 2.5 → 4/5, 5 → 5/5,
10 → 4/5, 20 → 1/4 — saturation at the lowest dose, degeneration at the
highest, one pair resistant in every arm. Boosting ranks 6–10 instead of
1–5 recovers 3/4 — the causal handle is the clinical feature family, not a
privileged top five.

## 5. Translation helps, and we now know why: it is the vocabulary

The three-arm comparison landed (same 15 batch-6 downgrade pairs, all arms
re-traced natively on gemma-2-2b; recomputed today from
`data/urgency_shift.json` rows):

| arm | mean care-urgency tiers regained |
|---|---|
| haiku translation (clinical rewrite) | 0.091 |
| opus translation (clinical rewrite) | 0.102 |
| placebo (same pipeline, paraphrase without clinical vocabulary) | 0.033 |

The placebo controls for paraphrase, fluency, and the rewriting act
itself: about two-thirds of translation's benefit is attributable to the
clinical vocabulary specifically. Opus adds ~0.011 tiers over haiku —
haiku remains the right default translator at ~1/8 the cost. Depth classes
(`data/jlens_depth.json:translation.by_class`, 35 joined pairs): recovery
appears both where the clinical answer survived in the residual stream
(retained: 0.13, n = 21) and where it never formed (absent: 0.163,
n = 10) — translation is not merely re-amplifying a signal that was
already there. The original case-level classification stands: 8 of 20
downgrades recover outright, 7 do not, 5 are unclassifiable
(`data/provenance.json:translation_cases`). A patch, not a cure.

## 6. The instrument is reliable at recorded precision (new)

Test–retest over every phrase the pipeline happened to trace more than
once (`ops/retrace_consistency.json`): 52 pairs traced 2–10×, probability
spread 0.0 at the recorded 3-decimal precision, top word stable 52/52,
full top-k spread lists identical 52/52, clinical_mass identical between
runs sharing graph parameters (52/52; cross-parameter runs differ by
design, 20 pairs). The hosted tracer behaves deterministically for the
frozen model. Caveats and hardening: this was an opportunistic sample, so
a designed repeatability sample is pre-declared and running — 20 pairs,
seed-7 stratified across downgrades/flips/holds, 3 independent CI runs,
rule-of-three 95% bound 3/20, any nonzero difference publishes as-is
(`docs/repeatability_sample.md`; run 1 of 3 landed). A daily three-pair
drift sentinel now watches for service-side change
(`ops/drift_series.json`; day-1 baseline 2026-07-13).

## 7. What it is not

Re-verified where artifacts changed, carried forward otherwise:

- **Not sentence length**: |r| ≤ 0.07 (`paired_stats_out.json:length_confound`).
- **Not tokenization**: first-piece length vs penalty r = 0.09 (n = 290).
- **Not measurement noise**: the instrument reproduces exactly (§6), and
  hand-measured penalties from real patient language correlate with traced
  penalties at r = 0.687 (n = 14 matched; censored bounds agree,
  `paired_stats_out.json:validity`).
- **Not single-sentence-reliable — an aggregate claim by design**:
  innocuous paraphrases move single measurements by ~0.064 on average, the
  same order as the penalty; only the paired aggregate carries evidence.
- **Human-validated with a located caveat**: blind owner QC of 20 pairs
  rated 15 sound / 2 unsure / 3 flawed, flaws concentrated in low-signal
  flips (condition-equivalence drift, not register;
  `docs/stimulus_qc_v1.json`). The confident-downgrade tier is largely
  insulated.
- Intentional misspellings in the stress set are stimuli, not errors.

## 8. Scale, spend, and supplementary program (ops context)

Tier B: 500 of 1,600 pre-registered haiku-written pairs accepted across 9
batches for $0.789 of generation spend (sidecar sum, `ops/dashboard.json`);
tracing and CPU behavior measurement are $0. Supplementary stress sets
(emergency-critical scenarios, severity inversion, misspellings) use a
different generator (claude-sonnet-5) and are excluded from Tier B counts
by construction; emergency round 1 accepted 2/20 candidates at $0.261
(`data/simulated/pairs_20260713T031252Z.report.json`) — the acceptance
pipeline, not the model, is the current bottleneck there, and a watch item.

## 9. Limits, plainly

One 2-billion-parameter model carries all circuit evidence; the other
three columns are behavior only, and three more models are probes with no
claims. Attribution graphs prune heavily and their feature labels are
machine-written. Steering and patching n's are small (4–20 and 7).
Probabilities are a point-in-time measurement against a hosted service
(§6 bounds the instrument, not the service's future). The urgency-tier
vocabulary is owner-reviewed v1, domain review pending — every tier-based
count inherits that draft status. The corpus is LLM-written stress
stimuli, not collected patient language; the hand-measured set (n = 14
matched) is the only bridge so far, and the owner has classified this run
as a demonstration pending patient-sourced exemplars. Effect sizes shrank
by roughly half as the sample quadrupled (§1) — quote the endpoint
holdout, not the interim. None of this measures deployed clinical
systems, and nothing here is medical advice.

The defensible claim, updated: on the models measured, patient phrasing
measurably suppresses the clinical continuation (3–6 points of
probability on average, several-fold downgrade asymmetry when the answer
changes); the suppression runs through a nameable, late-layer feature
circuit; and modest amplification of that circuit, clinical context, or
clinical-vocabulary translation partially restores it — with the placebo
arm now showing the restoration is specifically the vocabulary.

## Reproduce it

Engine: `michaeldgreenphd/patientwords-engine` (pipeline, workflows,
tests). Site with every figure and number: `michaeldgreenphd/patientwords`.
Key artifacts for this draft: `paired_stats_rigor.json`,
`paired_stats_out.json`, `ops/retrace_consistency.json`,
`ops/drift_series.json`, site `data/urgency_shift.json`,
`data/jlens_depth.json`, `data/patch_profile.json`,
`data/provenance.json`, `data/convergence.json`,
`docs/analyses_20260708.json`, `docs/stimulus_qc_v1.json`,
`trace_out/*/batch_summary.part_*.json`.
