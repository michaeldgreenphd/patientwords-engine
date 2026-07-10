# What we found: patient words make small language models worse at medicine

**Status: released for external readers by owner sign-off (2026-07-09). The
gemma-3-4b-it column completed on 2026-07-10 (its largest batch's run had
exceeded a CI timeout; re-run in chunks and landed): with the full set
(n = 240 phrases, deduped) both its mean penalty AND its downgrade asymmetry
are significant — the asymmetry was not established at the earlier n = 133,
and this update is reported as such below. Downgrade counts here are
phrase-deduped per the pre-registration (`paired_stats_rigor.py`); pooled
tallies that count re-traced phrases run several-fold higher and are
pseudoreplicated — do not cite them. Every number traces to a committed
artifact.**

One-line summary: when the same medical situation is phrased the way patients
actually talk instead of in clinical terms, small open models become measurably
less likely to continue toward the clinical action — and we can see, name, and
causally manipulate the circuit responsible.

Everything below is next-token probability on gemma-2-2b (with attribution
graphs) and qwen3-4b / qwen3-1.7b / gemma-3-4b-it (behavior only). Nothing
here measures harm in deployed systems; see Limits.

## 1. The penalty is real, and it is not one model's quirk

Across the unified set of 132 phrase pairs measured on all three models, patient
wording costs probability on the same target token:

| model | mean penalty | 95% CI | n |
|---|---|---|---|
| gemma-2-2b | −0.070 | [−0.098, −0.043] | 132 |
| qwen3-4b | −0.099 | [−0.149, −0.049] | 132 |
| qwen3-1.7b | −0.089 | [−0.133, −0.047] | 132 |
| gemma-3-4b-it | −0.044 | [−0.073, −0.016] | 240 (deduped) |

With every gemma-3-4b-it batch landed (all four pair batches + the downgrade
set, completed 2026-07-10), its penalty CI excludes zero (n = 240 phrases,
deduped); the point estimate came down from −0.071 at n = 133 as the largest
batch was added, and the conclusion is unchanged. Its per-pair penalties
track gemma-2's at r = 0.60 (64% sign agreement, computed on the earlier
n = 133 subset). That row uses the full landed set with the pre-registered
phrase-dedupe; the other three rows are the unified 132-pair cross-model set. Per-model phrase-deduped statistics for all four models —
mean penalty (cluster bootstrap), downgrade rate (Clopper–Pearson exact),
and BH-corrected sign tests — are in `paired_stats_rigor.json`.

No CI crosses zero. The models also agree pair by pair, not just on average:
gemma's per-pair penalty correlates with qwen3-4b's at r = 0.62 and with
qwen3-1.7b's at r = 0.52, with ~70% sign agreement (n = 132 each). Two model
families, two measurement backends (hosted traces vs. local logits), same
phrase-level effect. The penalty belongs to the phrasing, not the model.
(Sources: `paired_stats_out.json`, `docs/analyses_20260708.json`.)

## 2. The failure that matters is a changed answer, not a hedge

Often the model keeps its top answer and just loses confidence. The dangerous
case is when the top continuation changes — and when it changes, it goes down
the care ladder far more often than up:

- gemma-2-2b: 27 downgrades vs 5 upgrades (sign test p = 0.00011, BH q = 0.0004)
- gemma-3-4b-it: 22 vs 5 (p = 0.0015, BH q = 0.002) — at n = 133 this did not
  reach significance (11 vs 4, p = 0.12); with its largest batch landed
  (2026-07-10, n = 240) the newer instruction-tuned model shows the same
  asymmetry as the others
- qwen3-4b: 16 vs 2 (p = 0.0013, BH q = 0.002)
- qwen3-1.7b: 18 vs 5 (p = 0.011, BH q = 0.011)

These are phrase-deduped counts (each clinical phrase once, per the
pre-registration's dedupe rule; `paired_stats_rigor.py`) on the tier
vocabulary the study owner reviewed item-by-item (owner-reviewed v1,
2026-07-09; clinician equivalence review still pending). Pooled tallies that
count re-traced phrases run several-fold higher and are pseudoreplicated — do
not cite them.

Concrete cases from live traces: "urinary tract … blocked up" calls a
urologist at 0.20; "her water was blocked up" calls a **plumber** at 0.68.
"Constipated … took a" continues with *laxative*; "all bunged up" continues
with *nap*. The advice object changes, not just its probability.
(Source: `data/urgency_shift.json`; tier vocabulary reviewed v1, 2026-07-09.)

## 3. Mechanism: the wording swaps which circuit runs

The attribution graphs show why. Clinical phrasing recruits a stack of
medical-language features; patient phrasing replaces much of that stack with
features about the surface topic of the idiom.

- Named clinical features (most frequent in top attribution paths): "language
  related to medical care, including doctors…" (56 paths), "language related
  to doctor's visits…" (44), "medical procedures related to the arterial and
  respiratory…" (32).
- Named hijackers on the patient side: features for sleep words, food and
  drink, coffee, tea, beds, money/legal conflict — the literal reading of the
  idiom, crowding out the medical reading.
- Depth: clinical and off-target features live at the same depth (mean layer
  ~20 and ~20.6 of 26). This is not "shallow idiom vs deep medicine" — the two
  readings compete side by side in the late layers.
- Overlap: a clinical/patient pair of the same sentence shares only ~47% of
  its traced circuit (median 0.467, n = 365 pairs). More than half the
  computation changes when the wording changes.

(Source: `docs/analyses_20260708.json`; feature labels are machine-generated
autointerp text — see Limits.)

## 4. The circuit is causal, and it behaves like a dose

We steered the model over the API (Neuronpedia `/api/steer`) on the 20
downgrade phrases:

- **Muting the idiom's features** (ablate the patient graph's top-5
  off-target) recovers the clinical target outright in only 1/20.
- **Amplifying the clinical circuit** (boost the clinical graph's top-5
  clinical features while the model reads the *patient* words) recovers it in
  5/20, and replicates 4/5 on independent re-traces of the recovered subset.
- **Placebo** (5 random features, same strength, same prompts): 0/5. The
  effect is the clinical circuit, not steering itself.
- **Dose-response** on the recovered subset (recoveries at each boost
  strength, all cells final after remeasures): **2.5 → 4/5, 5 → 5/5,
  10 → 4/5, 20 → 1/4**. Recovery saturates at the lowest dose tried and
  declines sharply at the highest, where continuations occasionally
  degenerate. The circuit needs a nudge; a shove hurts. One pair resists
  at every strength — the same pair, every arm.
- **Rank faithfulness**: boosting clinical ranks 6–10 instead of 1–5 at the
  same strength recovers **3/4 measured — near-parity with the top-5 arm
  (4/5)**, and an independent second run reproduced the identical pattern
  (same recoveries, same miss). This revises the naive prediction:
  attribution rank does not concentrate the causal handle in a privileged
  top five; the steerable mass is distributed across at least the circuit's
  top ten features. The placebo (0/5) still rules out "steering anything
  works" — what is causal is the clinical feature *family*, not any
  particular handful of it.

Listener-side amplification beats speaker-side muting: you get more back by
strengthening the medical reading than by suppressing the idiom.
(Sources: `data/provenance.json:steering`, `steering_titration`;
`trace_out/boostgrid_*`.)

## 5. Context changes the penalty in both directions

Prefixing the same sentence with a clinical scene (a chart note register)
cuts the mean penalty to −0.059; a neutral casual scene amplifies it to
−0.137; no context sits between at −0.092. Paired, the clinical prefix beats
the neutral one by +0.083 (8/14 pairs improved). Where you say it moves the
number as much as how you say it — casual framing makes patient wording
*worse*, clinical framing roughly halves the cost.

The register ladder complicates this in a useful way. In one case study,
with the clinical term held verbatim, the target fell 0.322 → 0.114 → below
the top-10 floor as the sentence slid from formal to casual register. But
the n = 10 sweep did not replicate the staircase: across ten baselines,
mean target probability is flat over the five rungs (0.27–0.34), and the
casual end beats the formal end about as often as not. Register alone —
with the term held fixed — rarely moves the target. Put together with the
prefix result above: added clinical *context* helps, but the penalty itself
concentrates in the vocabulary swap, not the surrounding register. We report
the single case as an illustration, not a law.
(Sources: `data/provenance.json:ladder_digestive`, `ladder_n10`.)

## 6. Translation is a real but imperfect patch

An LLM rewriting the patient sentence into clinical terms, re-traced natively:
8 of 20 downgrades recover, 7 do not, 5 are unclassifiable. When it works it
can overshoot the original clinical phrasing (laxative: 0.26 clinical → 0.45
after translation). When it fails it can make things worse (one case replaced
the correct continuation at 0.38 with a weaker one at 0.15). A patch, not a
cure. (Source: `data/provenance.json:translation_cases`.)

## 7. What it is not

- **Not sentence length**: |r| ≤ 0.07 between length difference and penalty.
- **Not tokenization**: target first-piece length vs penalty r = 0.09
  (n = 290). The tokenizer isn't creating the effect.
- **Not measurement noise**: hand-measured penalties from real patient
  language correlate with the pipeline's traced penalties at r = 0.687
  (n = 14 matched; 8 further pairs are censored bounds that point the same
  way, sensitivity r = 0.370).
- **Not single-sentence-reliable — by design an aggregate claim**: innocuous
  paraphrases (meaning preserved, term held fixed) move a single measurement
  by ~0.064 on average — the same order as the penalty itself. No individual
  pair is evidence; the penalty is a paired aggregate over 132 pairs, where
  bidirectional paraphrase noise contributes only ~0.009 to the standard
  error. Featured examples are illustrations of a distribution, not proofs.
- **Human-validated, with a caveat located**: a blind owner review of 20
  pairs (10 flips / 10 non, unlabeled) rated 15 sound, 2 unsure, 3 flawed.
  All 3 flawed pairs fell in the flip half — the failure mode is
  condition-equivalence drift on the patient side ("didn't feel like
  clinical equivalents"), not register. But those 3 are low-signal flips
  (penalties −0.02, −0.09, and one unmeasured target; none are confident
  downgrades at p ≥ 0.2), so the load-bearing downgrade claim — which rests
  on the confident tier — is largely insulated. The honest reading: a
  minority of raw flips are stimulus artifacts, concentrated where the
  measurement is weakest. (Source: `docs/stimulus_qc_v1.json`.)
- The intentional misspellings in the stress set are stimuli, not errors.

## 8. Limits, plainly

One 2-billion-parameter model carries all circuit evidence; the qwen checks
are behavior only. Attribution graphs prune heavily and their feature labels
are machine-written — a mislabeled feature shifts category masses. Steering
n's are small (5–20). Probabilities are a point-in-time measurement against a
hosted service. The urgency-tier vocabulary is owner-reviewed (v1); its
residual low-frequency tokens default to excluded.
None of this measures deployed clinical systems, and nothing here is medical
advice. The defensible claim: on the models measured, patient phrasing
measurably suppresses the clinical continuation, the suppression runs through
a nameable feature circuit, and modest amplification of that circuit — or
clinical context, or translation — partially restores it.

## Reproduce it

Engine: `michaeldgreenphd/patientwords-engine` (pipeline, workflows, tests).
Site with every figure and number: `michaeldgreenphd/patientwords`.
Key artifacts: `paired_stats_out.json`, `docs/analyses_20260708.json`,
`data/provenance.json` (site), `data/urgency_shift.json` (site),
`trace_out/*/batch_summary.part_*.json`.
