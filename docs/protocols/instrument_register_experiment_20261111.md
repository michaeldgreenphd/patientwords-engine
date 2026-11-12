# Wording, model and instrument: the first bounded experiment (protocol draft, 2026-11-11)

**Status: draft, not signed. Nothing in it has been run on a model. It fixes a design; it reports no
result.** It fills `docs/protocols/protocol_template.md` for one experiment and uses
`docs/protocols/instrument_validity_benchmark.md` (the benchmark), the experiment runner under
`scripts/experiments/` and the scorer `scripts/instrument_validity.py`. It adds no runner and no lane.

Answer first. The experiment asks four separate questions, A to D, and never adds their answers into one
number. A and B can each be answered without the other. C is read only against the controls named below.
D is not run here: it names the intervention a causal statement would need. The smallest real step that
can run today is the operation check of section 19, which is 10 public rows on one model and answers
none of A to D.

## 0. Identity and status

| Field | Value |
|---|---|
| Title | Wording, model and instrument: the first bounded experiment |
| Protocol file | `docs/protocols/instrument_register_experiment_20261111.md` |
| Status | draft, 2026-11-11 |
| Author | written in the coordinating session for the owner's review |
| Signed by | not signed. The owner signs by a commit that changes the status line and fills section 14 |
| Blocks | any real bundle for parts B and C, any fire for them, any publication of their outputs |
| Does not block | the operation check of section 19 (it has its own approval), synthetic software checks |
| Design sources | the benchmark; `docs/exploratory/first_model_run_packet_20261110.md` (the run packet); `docs/experiment_interface/README.md`; `docs/open_results_policy.md` |

## 1. Research questions and claim types

| Part | Question | Quantity | Level of evidence | Where it is computed |
|---|---|---|---|---|
| A | Does wording change the selected behavioural endpoint? | For one family: the full-vocabulary probability of the first token of the declared target under the medical wording minus the same under the everyday wording. A probability difference, in probability units; reported in percentage points only where labelled so | a change in a defined probability | `behavior_next_token` through the runner; `comparisons[].behavior` in a bundle |
| B | With the activation artifact held fixed, do an instrument's descriptions or scoring change its conclusion, and is what it reports recoverable from the wording alone? | (B1) held-artifact score difference between a medical-register and an everyday-register description of one artifact; (B2) fact-recovery rate with the actual artifact minus the rate with the wording alone, and minus the rate with a control artifact | a difference in an instrument's readout | the scorer: `held_artifact`, `description_controls`, `verbalizer_arms` |
| C | Do internal differences between the two wordings exceed within-register variation, respond to a changed fact, and go with the behaviour difference of A across families? | per stage: medical-minus-everyday difference in `representation_value` against the calibration threshold; changed-fact sensitivity; the four-cell table of behaviour by representation | a difference in an internal representation, and an association with behaviour | the scorer: `behaviour_by_representation`, `changed_fact_sensitivity`, `paraphrase_consistency` |
| D | Which intervention would a causal explanation need? | none in this experiment | none: D is a plan | section 10 |

Not asked here, and not answerable from these data: whether an answer is clinically better or worse
(clinically judged answer quality), and whether anything affects patients or populations.

## 2. What this experiment cannot establish

- That two wordings are clinically equivalent. That is an input, established by the review of section 4,
  and an unreviewed pair stays labelled unreviewed in every table.
- Anything about a whole answer. The endpoint of A is the probability of one token, the first token of
  the target. Where a target spans more than one token the endpoint is partial and is labelled so.
- That an internal difference causes a behaviour difference. C is an association across families.
- That a model "understands" one wording better. No field of a bundle states that.
- That a null on one endpoint means the two wordings are handled identically.
- Anything about a model, basis or scorer other than the ones named in the bundle's identities.
- Any equity effect. Equity motivates the question. These data cannot show an effect on people.

## 3. Population and independent unit

The unit is the **case family**: one clinical situation with a fixed set of reference facts, its medical
wording, its everyday wording, at least one within-register paraphrase per register and at least one
changed-fact control. Statistics resample families.

A phrase is one unit. A clinical phrase that recurs in several source rows forms one family and its rows
are averaged before any statistic. The scorer refuses the same medical or everyday text in two families
(`repeated_phrase`), and the published payload summary counts distinct clinical phrases
(`scripts/payload_summary.py`, corrected 2026-11-10). Rows are never treated as independent observations.

Source of families: public, unrestricted rows, or newly written families. No Tier B holdout row is read,
and the confirmatory holdout is not unsealed for this experiment.

## 4. Clinical facts held equal, and who reviews what

Reference facts are established by clinical review of the case, independently of every instrument. The
medical wording is not the answer key.

Each pair gets an equivalence review on six dimensions, recorded per family in the form
`pair_equivalence_review` of `data/protocols/instrument_validity_rubric.draft.json`: clinical facts,
negation, timing, uncertainty, severity, urgency.

| Reviewer | Decides |
|---|---|
| Clinician | Whether the two wordings state the same clinical facts on all six dimensions; the reference facts; the one fact changed in each changed-fact control |
| Patient-language reviewer | Whether the everyday wording is language a patient would plausibly use, and whether a lay reader takes the same meaning from it. Everyday wording is not treated as defective medical wording |

A model's statement that two wordings are equivalent is not a review and is not recorded as one. A family
without both reviews keeps `review_status: domain_review_pending`, is reported in its own row, and enters
no confirmatory statement.

## 5. Manipulated dimension

Register only: medical terminology against everyday patient language, with the facts of section 4 held
equal. Dialect, grammar and spelling are not manipulated here. A rewrite that adds a diagnosis the base
wording did not state is an information intervention and is excluded.

**Other manipulations in authored batches (added 2026-11-12).** Draft rounds 9 and 10 hold texts that
change something other than register. None of them is part of this experiment. The intake command
(`python -m scripts.experiments.cli intake`, rules in `data/experiments/intake_design.v1.json`) puts each
in a named exploratory stratum, and no stratum is pooled with another:

| Text or property | Stratum | Why it is not the register contrast |
|---|---|---|
| Everyday wording plus the speaker's explanation ("I think it is just ...") | `patient_explanation` | the clause adds a belief, so the information differs; analysed within everyday wording, everyday against everyday plus the clause |
| Mixed wordings (medical terms in everyday syntax and the reverse) | `syntax_crossing` | a second dimension is crossed with register |
| A family whose everyday wording uses a dialect or regional form | `register_with_dialect` | register and dialect change together |
| A family that ends on a carrier phrase with no earlier measurement | `new_carrier` | the endpoint's behaviour on that carrier is unknown |

A confirmatory statement about any of these needs an extension of this protocol, written before the
families are measured. Comparisons are within family. Care tiers are not compared with each other: families
at different tiers end on different carrier phrases and target words, so their endpoints are probabilities
of different tokens in different contexts.

## 6. Provenance classes

Simulated scenario pairs and newly written families are labelled as such. Real patient language is not
used. A synthetic fixture is labelled `synthetic_fixture` and is never a measurement.

## 7. Controls

| Control | Part | What a failure means |
|---|---|---|
| Within-register paraphrase | A, C | the endpoint moves as much when the register does not change; a cross-register difference of that size is not attributed to register |
| Changed-fact control | A, C | the endpoint or instrument does not respond to a real change of clinical content; an "equivalent" result is then uninformative |
| Shuffled description, irrelevant description, explanation-free baseline | B1 | the scorer was not shown to read the description; the held-artifact verdict is withheld and the named control state is reported |
| Wording alone (`input_only`) | B2 | no demonstrated advantage of the actual artifact over the wording alone; the stage's result is then not attributed to the artifact |
| Control artifact (`control_artifact`) | B2 | no demonstrated advantage over another family's artifact; specificity to the artifact is then not shown |
| Cue checks (length, formatting, order, span position and marking) | B1 | a cue that a scorer could use without reading the description is associated with the score |

A failed or missing control is reported under its own state name. It is never folded into another score,
and no table says that an instrument "passes" because a different score exists. A control that is not
beaten shows no demonstrated advantage. It does not establish a cause, and an arm that recovered nothing
is not evidence about the artifact or the wording.

## 8. Endpoints

Intrinsic scoring and instrument controls are separate tables.

- **Intrinsic (A).** The behaviour difference per family, with the family-clustered bootstrap interval
  over held-out families. Missing values are excluded with a reason and never entered as zero.
- **Intrinsic (C).** Fact-recovery rate difference per stage (clinical scoring of what a stage's output
  conveys, by the rubric), changed-fact sensitivity, and the four-cell table.
- **Instrument controls (B).** The held-artifact difference with its control state; the two arm
  comparisons with the arm state.

Verdicts use the benchmark's three outcomes: `equivalent_within_margin`, `different_beyond_margin`,
`inconclusive`. `inconclusive` is kept as an outcome. So are the control and arm states that withhold a
reading. A difference that is not significant is never reported as equivalence.

## 9. Conversations

Not applicable: single-turn sentence-completion prompts only.

## 10. Causal experiments (part D, not run)

A causal statement about a component found in C would need, on held-out families and declared before
those families are opened: an intervention on that component at a named hook and layer of a pinned model
revision (patching from the other wording, or ablation); the predicted direction and minimum size of the
change in the endpoint of A; a matched control component that is expected to change nothing; and a dose
or position series. The existing `activation-patching` lane is the candidate route. No part of this
experiment is such an intervention, and no result of A to C is described as causal.

## 11. Splits and sealed sets

Families are split by underlying case, never by surface wording, into calibration (`discovery`),
`validation` and `fresh_test`. All wordings of a case are in one split. The scorer refuses a family or a
text in two splits (`split_leakage`). The Tier B holdout stays sealed.

For an authored batch the split is drawn by the intake command: per family, per care level, from a recorded
seed, once, before any measurement of the batch. A recorded split is read and never redrawn, and the
command refuses to draw a split or a mechanistic subset for a batch whose stem already has a directory
under `trace_out/`. The mechanistic subset (scaling plan, section 6) is a seeded draw from owner-kept,
unflagged discovery families; token alignment is recorded from real token ids as `position_aligned` or
`suffix_aligned`, and a family is never rewritten to reach a class.

**Calibration before evaluation.** Thresholds and margins are fixed on calibration families only:

1. Build a bundle that holds calibration families only and run
   `python scripts/instrument_validity.py --bundle <calibration bundle> --calibrate --quantile <Q>`. The
   command refuses a bundle with any family outside `discovery` (`calibration_reads_held_out`). `Q` is
   written in section 14 before that bundle exists; the command has no default.
2. Each stage's representation-change threshold is that record's
   `representation_value_abs_difference.quantile`: a cross-register difference counts as a change only
   when it exceeds what within-register paraphrases produce.
3. Each margin (the equivalence margins, the three control margins, the two arm margins) is stated in
   section 14 with its reason, beside the within-register variation of the record. A margin is a
   judgement of practical importance. The record does not compute one.
4. The thresholds, margins, the record's digest and `Q` are copied into the study bundle
   (`thresholds.*.selected_on_split: "discovery"`, `prespecified: true`) before any held-out family is
   scored. The scorer refuses a threshold selected on another split.

## 12. Primary contrasts and multiplicity

Primary: part A on the held-out set, one model, one target per family. Parts B and C are reported per
stage with their intervals and states and without a pooled test. No correction is applied because no
pooled claim is made; each stage's result is read alone.

## 13. Uncertainty and denominators

Family-clustered percentile bootstrap with a recorded seed, as the scorer implements it. Every table
gives families planned, families included and families excluded with reasons. Uncertainty is shown only
where it was computed.

## 14. Sample size, thresholds and margins: to be fixed before data

None of these has a value yet. Section 14.1 holds recommendations for the owner; a recommendation is not
a value, and the table changes only by the owner's decision.

| Field | Value | Fixed when |
|---|---|---|
| Families per split | not fixed | before families are written; needs the calibration variance |
| Calibration quantile `Q` | not fixed | before the calibration bundle exists |
| Equivalence margins (fact recovery, held artifact) | not fixed | after calibration, before held-out scoring |
| Control margins (three) and arm margins (two) | not fixed | the same |
| Behaviour-change threshold | not fixed | the same |

### 14.1 Recommendations awaiting the owner's decision (2026-11-12)

No outcome-blind family has been measured, so no variance estimate exists for this design. Each
recommendation states the assumption it rests on. The arithmetic was checked; the assumptions were not
tested.

| Open item | Recommendation | Basis and assumption |
|---|---|---|
| Calibration quantile `Q` | 0.90 | The calibration record takes one value per family and a nearest-rank quantile over families. With `Q` = 0.90 and 30 families the sample maximum exceeds the true 0.90 quantile with probability 1 - 0.9^30 = 0.958, so the estimate has an upper bound inside the sample. `Q` = 0.95 needs 59 families for the same statement (1 - 0.95^59 = 0.952). Assumes families are independent draws |
| Discovery families | at least 30, unflagged, register stratum | the row above |
| Validation and fresh-test families | at least 24 each | A 95% interval for a mean within-family difference with 24 families has half-width 2.07 x s / sqrt(24) = 0.42 s, where s is the between-family standard deviation of the difference; with 15 families it is 0.55 s. For a proportion of families near 0.5 the Wilson 95% half-width is about 0.19 at 24 and 0.23 at 15. s is unknown until the pilot of section 19 |
| Total under the recorded split rule (half, quarter, quarter per care level) | 96 unflagged families: 48, 24, 24 | 24 held-out families per split forces 96 in total; 48 discovery families exceed the 30 that `Q` needs. Stock on 2026-11-12: 10 owner-kept unflagged families in round 9 (4 in discovery). Round 10 is not landed |
| Whether to fix the total now | fix it after the pilot | The pilot gives the first s on discovery families only. Fixing the total before it rests on a guess; fixing it after uses no held-out value |
| Equivalence and control margins | per model, not smaller than the calibrated paraphrase quantile of that model; the number is written after calibration | A register difference smaller than what a same-register paraphrase produces cannot be attributed to register (section 7). A margin is still a judgement of practical importance; the quantile is its lower bound, not its value |
| Behaviour-change threshold | the same quantile, on the absolute probability difference of the paraphrase controls | the same reason; uses only discovery families |
| Review before the split | for a batch meant for the held-out sets: intake without a split seed, both reviews recorded, then the split | Section 4 removes a family on any "different" before the split. Round 9's split was recorded before any domain review, so its families stay exploratory unless the owner records a deviation in section 20 |
| Reviewers | one clinician and one patient-language reviewer per family; a second clinician on a seeded quarter of the families, with agreement reported | The rubric's minimum is one of each. A second reading of a sample is the only way to report agreement. Minutes per family are not recorded; time the first 8 families and plan from that |
| Models in the behavioural pass | the primary model (section 12) plus the six pinned logits models as exploratory rows | $0 provider spend on every one; see the cost rows of section 19 |

## 15. Judging

Fact-recovery ratings by trained annotators with the draft rubric, blind to register where the output
allows. Rubric agreement has not been measured. Any model judge is an instrument under test in part B and
is not a reviewer.

## 16. Exclusions

A family is excluded from a table when a value it needs is missing, with the reason listed. A family
whose equivalence review fails on any dimension is removed from the family list before the split and the
count is reported.

## 17. What would weaken each hypothesis

- A: a difference no larger than the within-register paraphrase difference.
- B1: a score difference that survives only while the controls are not passed.
- B2: the arm state `no_advantage_over_control_artifact` or `no_advantage_over_wording_alone`, in a set
  where an interval was computed and some arm recovered a fact. Only `artifact_contributes` supports B2.
  `arms_not_run`, `arms_incomplete`, the two `not_shown` states and a set in which no arm recovered
  anything neither support nor weaken it.
- C: representation differences below the calibration threshold, a changed-fact control that is not
  detected, or behaviour changes that occur equally with and without a detected representation change.

## 18. Evidence class, clinical review and analysis membership

Evidence class of every output until the owner decides otherwise: exploratory. Clinical review: per
family, as in section 4. No output joins `study-interim/1` or any published statistic.

## 19. Execution route, and the one step that can run today

**Identity that every real output must carry** (the runner and the Neuronpedia registry already require
it): model repository and revision, tokenizer revision, hook and layer with the layer-index base, basis
or SAE identifier and version with its normalization or preprocessing mode, dtype and backend. Outputs
from different spaces are not pooled, and two features with a similar label are not treated as the same
feature. A Neuronpedia page is linked as a reference unless `verified_exact` holds for the entry
(`docs/experiment_interface/neuronpedia.md`); today no entry does.

**Prerequisites that are not met.** Part C with an ICA basis needs the ICA adapter's parity work and the
basis identity of the run packet's section 11 (repository commit, file hashes, fit model revision,
preprocessing mode). Parts B and C need reviewed families (section 4) and a CI lane that produces bundles;
the scorer admits synthetic bundles only (`real_bundle_not_admitted`).

**The step that can run today: the run packet's stage A, an operation check.**

| | |
|---|---|
| Workload | one `logits-eval` job, `mode: verify`, 10 public rows of `data/simulated/pairs_20260706T175614Z.json` (file SHA-256 `67b74e6e…f2b832`), both wordings: 20 prompts |
| Measured endpoint | full-vocabulary probability of the first target token, float32, interp-engine 1.5.1 on CPU |
| Model and inputs | `google/gemma-2-2b` at `c5ebcd40d208330abc697524c919956e692655cf`; tokenizer from the same commit; no lens, basis or transcoder is read |
| Budget basis | $0 provider spend; one job of at most 240 runner minutes; estimate 17.7 minutes from a proxy rate of 88.5 s per pair measured on another model, so the estimate is an assumption |
| Acceptance | the parity criteria of the run packet's section 6.2, fixed before the fire, computed by `scripts/backend_agreement.py` |
| What it shows | that the pinned model, the lane and the comparison work end to end on real weights |
| What it cannot show | the ICA hypothesis, any of A to D, clinical validity (the batch is `domain_review_pending`), or throughput at scale |

It needs the owner's approval as the run packet states (its section 14, decision 1). It is fired only
through `scripts/fire_trigger.py`.

**The smallest pilot on authored families: proposed, not approved, not fired (2026-11-12).** It follows
the operation check above and needs the same kind of approval.

| | |
|---|---|
| Families | the 8 owner-kept discovery families of round 9 (`r9-01`, `-04`, `-05`, `-06`, `-11`, `-12`, `-13`, `-15`); no validation or fresh-test family is measured |
| Workload | 38 contrasts, 46 distinct prompts: 16 in the register stratum (4 unflagged families: register, two paraphrase controls, changed fact), 16 in `register_with_dialect`, 6 syntax crossings. Rows of `data/simulated/agscen_r9_20261110.json` selected with the `indices` parameter of `logits-eval`; the intake manifest's `lane_input.index_of` gives the row of each contrast |
| Model | `google/gemma-2-2b` at `c5ebcd40d208330abc697524c919956e692655cf`, the model of the operation check |
| Estimate | 38 x 88.5 s = 56 runner minutes, one job, $0 provider spend. 88.5 s per pair is the proxy rate of the operation check, measured on another model, so the estimate is an assumption until the operation check records a rate |
| Optional second step | the same 38 rows on the six pinned logits models: 24,529 runner seconds (6.8 runner hours) at the slowest recorded rates of `scripts/backfill_planner.py`, $0 |
| What it gives | the first within-family paraphrase differences and register differences on outcome-blind families, on discovery only: the input the sample-size decision of section 14.1 lacks; and a check that manifest, lane and harvest join on `(batch, batch_index, model)` |
| What it cannot give | a threshold (4 unflagged families give 4 calibration values, far below the 30 of section 14.1), any held-out result, any statement about care tiers, clinical validity (every family is `domain_review_pending`) |
| Evidence class | exploratory; shared under `public-display/1` with its labels whatever the result |
| Prerequisites | the pairs file on `main` (pull request 173, unmerged on 2026-11-12); the owner's approval; the operation check landed first if its measured rate is wanted for the estimate |
| Mechanistic subset | recorded before any measurement: `r9-04`, `r9-11`, `r9-12`, `r9-13` (seed 20261112; the draw had 4 candidates, so it took all 4). Activation patching on them with three controls per site is estimated at 160 to 240 runner minutes from the documented 10 to 15 minutes per pair; no landed part records a duration. Not proposed for now |

The full round 9 behavioural pass (15 owner-kept families, 70 contrasts) on the six logits models is
estimated at 45,185 runner seconds (12.6 runner hours), $0. At the same rates a 96-family set with the four
register-stratum contrasts per family (384 pairs) is 384 x 645.5 s = 68.9 runner hours on the six logits
models, plus 9.4 runner hours on `gemma-2-2b` at the proxy rate. These are sums of slowest recorded rates,
not measurements of this workload.

**Measuring a real run.** No real timing exists for this model on this lane. A bounded real run records:

| Quantity | Source | Status |
|---|---|---|
| Wall time of the job | the workflow run's start and completion times | recorded by the platform today |
| Load seconds and measurement seconds | `inference.wall_seconds` of the landed summary (`load`, `measure`, `pairs_measured`) | recorded by the verify path since 2026-11-11; no run has produced a value yet. The logits path does not record them |
| Throughput | `seconds_per_pair`: measurement seconds divided by pairs measured, with the pair count | derived in the same record; reported with its sample size |
| Peak memory | the lane | not recorded today |
| Provider cost | the cost sidecar; $0 on the CPU lanes | recorded as 0 with its basis, not as an estimate |
| Per-task runtime in the runner | `resources.runtime_seconds` of an envelope with `measured: true` | implemented; filled only by a real adapter |

A synthetic fixture's timings and a $0 estimate are not measurements of a model run and are never
reported as throughput.

**Reuse, interruption, resume and collection** are properties of the existing runner. They were exercised
for this document on the synthetic slice (45 planned tasks, 27 ready), with no model:

```bash
python -m scripts.experiments.cli plan --protocol tests/fixtures/experiments/protocol_synthetic_ica.json --out PLAN
python -m scripts.experiments.cli run-fixture --plan PLAN --fixtures tests/fixtures/experiments --run-dir RUN --stop-after 5
python -m scripts.experiments.cli run-fixture --plan PLAN --fixtures tests/fixtures/experiments --run-dir RUN
python -m scripts.experiments.cli run-fixture --plan PLAN --fixtures tests/fixtures/experiments --run-dir RUN
python -m scripts.experiments.cli collect --run-dir RUN --require-complete
```

Observed on 2026-11-11: the first run executed 5 tasks and stopped with 22 ready tasks remaining; the
second executed those 22 and reused 5; the third executed 0 and reused 27; `collect` reported 27
completed, 9 unavailable, 9 unsupported and nothing missing. These are counts of a software path on
placeholder data. They say nothing about a model.

## 20. Deviations log

None. Nothing has been run under this protocol.
