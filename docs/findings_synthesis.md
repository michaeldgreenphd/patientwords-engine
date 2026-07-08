# What we found: patient words make small language models worse at medicine

**Status: near-final — the causal panel is complete. Remaining: the gemma-3-4b-it cross-model column (runs in queue overnight). Every number traces to a committed artifact.**

One-line summary: when the same medical situation is phrased the way patients
actually talk instead of in clinical terms, small open models become measurably
less likely to continue toward the clinical action — and we can see, name, and
causally manipulate the circuit responsible.

Everything below is next-token probability on gemma-2-2b (with attribution
graphs) and qwen3-4b / qwen3-1.7b (behavior only). Nothing here measures harm
in deployed systems; see Limits.

## 1. The penalty is real, and it is not one model's quirk

Across the unified set of 132 phrase pairs measured on all three models, patient
wording costs probability on the same target token:

| model | mean penalty | 95% CI | n |
|---|---|---|---|
| gemma-2-2b | −0.070 | [−0.098, −0.043] | 132 |
| qwen3-4b | −0.099 | [−0.149, −0.049] | 132 |
| qwen3-1.7b | −0.089 | [−0.133, −0.047] | 132 |

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

- gemma-2-2b: 67 downgrades vs 4 upgrades (sign test p ≈ 0)
- gemma-3-4b-it: 8 vs 1 (p = 0.039) — a newer, instruction-tuned model,
  same asymmetry
- qwen3-4b: 16 vs 2 (p = 0.001)
- qwen3-1.7b: 18 vs 5 (p = 0.011)

These counts use the tier vocabulary the study owner reviewed and approved
item-by-item (v1, 2026-07-09); the review unblocked previously unclassifiable
flips, which is why they exceed the draft-era counts.

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
  strength): 2.5 → 4/4 landed, 5 → 5/5, 10 → 4/5, 20 → **breaks down** (of
  five calls, three failed server-side and the one measured continuation
  degenerated into token repetition). The curve is an inverted U: recovery
  saturates at the lowest dose we tried and collapses into incoherence at the
  highest. The circuit needs a nudge; a shove breaks the model.
- **Rank faithfulness**: boosting clinical ranks 6–10 instead of 1–5 at the
  same strength recovers **3/4 measured — near-parity with the top-5 arm
  (4/5)**. This revises the naive prediction: attribution rank does not
  concentrate the causal handle in a privileged top five. The steerable mass
  is distributed across at least the circuit's top ten features. The placebo
  (0/5) still rules out "steering anything works" — what is causal is the
  clinical feature *family*, not any particular handful of it. (A second,
  independent run of this arm is in flight as a replication.)

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

The register ladder shows the same thing as a staircase: with the clinical
term held verbatim in every rung, P(antacid-class target) falls 0.322 (formal
clinical) → 0.114 (one everyday word) → below the top-10 floor by the middle
rung, where a fruit takes the top slot. Register alone, without touching the
key term, flips the guidance object. (n = 1 case study; the n = 10 ladder
batch is traced next.)
(Sources: ledger `docs/overnight_ledger_20260708.md` 20:15 entry;
`data/provenance.json:ladder_digestive`.)

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
