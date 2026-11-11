# Interpretability-instrument validity benchmark: specification

**Status: proposed PatientWords contribution; no register bias has been measured with it.**

Written 2026-11-10. This file specifies a benchmark. It reports no result. The only thing that has been
run is an offline software check on two synthetic fixtures, described under
[What is verified](#what-is-verified-and-what-is-not).

## Question

PatientWords asks whether a model responds consistently when the same health concern is written in
everyday language and in medical terminology. The project reads model internals with interpretability
instruments: raw component comparisons, lens readouts, generated feature labels and verbalizations, and
explanation scorers. Each instrument has its own vocabulary, fitting corpus or judge.

This benchmark asks a question about the instruments, not about the model:

> When two inputs carry the same clinical information, does an interpretability instrument recover that
> information equally well from the medical wording and from the everyday wording?

It is a measurement-validity question. An instrument that recovers information more readily from medical
wording would make a model look as if it "understood" clinical text better, when part of the difference
was produced by the instrument.

## Hypothesis and null

- **Hypothesis under test.** At one or more measurement stages, an instrument recovers clinically
  equivalent reference facts at a higher rate from medical wording than from everyday wording, by more
  than the practical equivalence margin fixed in advance.
- **Null.** At that stage, the paired difference in recovery lies inside the margin.
- **Direction.** The test is two-sided. An instrument that favours everyday wording is the same kind of
  measurement error and is reported the same way.

The hypothesis is a possibility to test. It is not an assumed flaw of any tool. A verdict of "equivalent
within margin" is a real outcome of this benchmark and is reported as one.

## What the benchmark keeps apart

Evidence about the model and evidence about the instrument are different things and are stored in
different fields.

| Evidence about | What it is | Where it lives in a bundle |
|---|---|---|
| The model | The original model's output on a behavioural endpoint fixed in advance | `behaviour_value` |
| The measured representation | A stage's scalar summary of what the instrument measured | `representation_value` |
| The instrument's reading | Which reference facts the stage's output conveys | `fact_recovery`, `unsupported_facts` |
| A lexical proxy | The rank of one exact token | `raw_rank`, `filtered_rank` |

No field mixes two of these. The scorer refuses a bundle in which a variant's `behaviour_value` differs
between stages, because behaviour belongs to the model and cannot depend on the stage that looked at it.

## Matched-information design

The unit is the **case family**: one clinical situation with a fixed set of reference facts.

1. **Reference facts.** A set of the relevant facts of the case, established independently of every
   interpretability instrument, by clinical review of the case itself. The reference set is the answer
   key. Clinical wording is not the answer key.
2. **Medical variant.** The case written with medical terminology.
3. **Everyday variant.** The same case, with the same facts, written in everyday patient language.
   Equivalence is reviewed fact by fact: uncertainty, negation, chronology, severity and the set of
   available facts. The review status is stored per family.
4. **Within-register paraphrases.** A second wording in the same register as its base variant. These
   measure how much an instrument's reading moves when the register does not change. A cross-register
   difference is read against this within-register variation.
5. **Changed-fact controls.** A variant in which exactly one reference fact is genuinely changed, with
   the register of its base variant kept. These measure whether the instrument responds to a real change
   in clinical content. An instrument that reads both registers "equally" because it responds to nothing
   would pass an equivalence test and fail this control.

A rewrite that inserts a diagnosis the base variant did not state is an information intervention. It is
not an everyday or medical variant of the same family.

Every family has one medical variant, one everyday variant and at least one changed-fact control. The
scorer refuses a bundle that lacks any of them.

## Measurement stages, evaluated one at a time

| Stage | What is measured | Typical instrument |
|---|---|---|
| `activation` | Raw activation or component differences between variants | residual or neuron comparison, a fixed component basis |
| `readout` | What a lens decodes from an activation | logit lens, Jacobian lens, J++ |
| `label` | A generated label or verbalization of a component or activation | automatic labeler, activation verbalizer |
| `score` | A downstream score given to a label or explanation | explanation scorer, model judge |

Each stage is scored separately. A difference at the `label` stage is not attributed to the `readout`
stage below it, and a null at one stage says nothing about another. A stage that a bundle does not
supply is reported as `not_supplied`.

### The held-artifact manipulation

A difference between variants at the `label` or `score` stage has two possible sources. The underlying
representation may differ between the two inputs. Or the labeler or scorer may treat descriptions
differently by their register.

Where a labeler or scorer accepts alternative descriptions, the benchmark separates the two:

1. Hold the underlying artifact fixed: one component, one activation set, one explanation target, with
   one digest.
2. Supply two descriptions of it that mean the same thing, one in medical register and one in everyday
   register. Their equivalence is reviewed like any other pair.
3. Record the score each description receives.

The artifact did not change, so a score difference cannot come from the representation. It is a
presentation or scoring effect. The scorer refuses a record set in which one artifact id carries two
digests (`artifact_not_held_fixed`).

This is the strongest test in the benchmark, because it is a controlled manipulation of one variable.

The manipulation shows nothing when the scorer does not read the description: two descriptions then get the
same score whatever they say. Its verdict is therefore issued only when the controls in
[Description controls and cue checks](#description-controls-and-cue-checks) are passed.

## Endpoints

All endpoints are fixed before data. The semantic endpoints are primary.

| Endpoint | Definition | Reported as |
|---|---|---|
| Recovery of reference facts | Per variant and stage: mean credit over the family's reference facts. Recovered counts 1, partially counts the partial credit fixed in the plan, not recovered and contradicted count 0. | Paired medical-minus-everyday difference per family; mean, interval and verdict |
| Unsupported inferred facts | Count of statements in the instrument's output that the reference set does not support | Mean count per description, by register; paired difference |
| Sensitivity to genuinely changed facts | For each changed-fact control: whether credit for the changed fact fell below its base variant's credit | Share detected, by base register, with a Wilson interval. Controls whose base variant earned no credit are counted apart |
| Consistency across equivalent phrasings | Per-fact agreement between a within-register paraphrase and its base variant | Mean agreement share and mean absolute rate difference, by base register |
| Held-artifact score difference | Score of the medical-register description minus score of the everyday-register description, artifact fixed | Mean over families and interval, with the length, formatting and order cues of the pairs beside them. A verdict only in the control state `controls_passed` |
| Exact-token rank | Rank of one prespecified token | A **lexical** endpoint, recorded next to the semantic ones, never in place of them |

Rules for exact-token ranks:

- Full-vocabulary rank (`raw_rank`) and filtered rank (`filtered_rank`) are reported separately. A
  filter changes which candidates are ranked; it is declared and the two numbers are not merged.
- A token that a top-k interface did not return is recorded as `not_observed_in_window`. It is never
  read as absent, never given a rank and never enters a median.
- A rank for a medical term measures how readily the instrument emits that term. An everyday variant can
  carry the same fact without the term ranking highly. This is why the rank is a lexical endpoint and
  why the semantic assessment sits beside it.

The annotation rules for the semantic endpoints are in
`data/protocols/instrument_validity_rubric.draft.json`. The rubric is a draft. It has not been used by
any annotator and no human calibration has been run.

## Equivalence margins and uncertainty

- A practical equivalence margin is fixed for each endpoint that receives a verdict, before any data. The
  bundle records the margins, a statement of where and when they were fixed, and `prespecified: true`.
  The scorer refuses a bundle without them (`missing_margins`, `margins_not_prespecified`).
- The interval is a family-clustered percentile bootstrap of the mean paired difference. Families are
  resampled, never facts, tokens, layers or components. The seed, resample count and confidence level are
  in the bundle and are copied into the report.
- The verdict has three outcomes:
  - `equivalent_within_margin`: the whole interval lies inside (−margin, +margin);
  - `different_beyond_margin`: the whole interval lies above +margin or below −margin;
  - `inconclusive`: anything else.
- **A non-significant difference is not evidence of equivalence.** An interval that includes zero and
  also crosses the margin is inconclusive. Equivalence is claimed only when the interval excludes every
  difference as large as the margin.
- A set with fewer families than the plan's minimum gets no interval and is inconclusive, even when all
  its differences are zero.
- Binomial shares carry Wilson intervals.
- The margin is a judgement about what size of instrument difference would change a conclusion drawn
  with the instrument. It needs a stated reason. This specification does not supply a value.

## Description controls and cue checks

Decided by the owner on 2026-11-10. This section is part of the design. It settles open design question 1
and the recording half of question 2.

**Motivation.** A primary source reports structural shortcuts in explanation evaluation: on the stored
items of a standard pipeline, a rule that never reads the explanation scored higher than the stored
scorers (Chen, arXiv:2610.37676v1; the entry under [Related work](#related-work-sources-read)). Its
reported result is a reason to test these controls in PatientWords, not evidence that PatientWords already
has that failure. No PatientWords scorer has been run under these controls.

**What they guard.** A scorer that does not read the description gives the medical and the everyday
description of one artifact the same score. Before this change `scripts/instrument_validity.py` returned
`equivalent_within_margin` for such a set. The changed-fact control guards the recovery endpoint against
an instrument that responds to nothing. These controls guard the held-artifact endpoint in the same way.

**What stays.** The controls are added to the design and replace no part of it: reference facts
established independently of every instrument; within-register paraphrases; changed-fact controls;
held-out families, split before development; equivalence margins fixed before data; and the held-artifact
manipulation, in which one fixed artifact receives descriptions in two registers. The equivalence margins
are not changed.

### What the scoring task supplies

The controls apply to a scorer that receives a description and a fixed set of **evaluation items** for one
artifact, and returns a yes or no verdict for each item. Each item has a truth label: positive when the
artifact is active on the scored span. The bundle carries the items in `evaluation_items`, with the label,
the cues below, and the scorer's verdict under each description condition.

A score in this section is **balanced accuracy** over one artifact's items: the mean of the share of
positive items given yes and the share of negative items given no. Every condition and every rule is
scored on the same items of the same artifact. Where an artifact's items carry the verdicts of a matched
description, the record's declared `score` must equal their balanced accuracy, or the bundle is refused
(`score_not_reproduced_from_items`).

Version 1 knows this one metric. A scorer that returns one number per description and exposes no items
cannot be given an explanation-free baseline. Its held-artifact endpoint reports `control_not_run`.

### The three controls

All three are specified before data and scored on the same items as the matched description.

1. **Shuffled description.** Each artifact is also scored with the description written for another
   artifact of the same stage, in the same register. The other artifact is fixed by a seeded derangement:
   the stage's artifact ids are sorted, and copies are shuffled by
   `random.Random("<shuffle seed>:shuffle:<stage>")` until no artifact is paired with an artifact of its own
   case family. That rules out its own description and the description of another artifact of its family.
   The seed and the mapping are stored in the bundle. The scorer recomputes the mapping and refuses a
   bundle whose mapping differs (`shuffle_mapping_not_reproducible`) or whose shuffled description has the
   artifact's own text (`shuffle_identical_description`).
2. **Irrelevant description.** Each artifact is also scored with one fixed placeholder description that is
   about nothing in the items. The placeholder is defined in the rubric
   (`description_controls.irrelevant_description`); a bundle that uses another text is refused
   (`irrelevant_description`). It has one wording and no register. The study protocol records, before data,
   a check that no item is about the placeholder's subject.
3. **Explanation-free baseline.** The best rule that does not read the description. A rule reads only how
   an item was built. The family is closed, and a bundle that declares another list is refused
   (`explanation_free_rule_family`):

   | Rule | Verdict |
   |---|---|
   | `always_positive` | yes for every item |
   | `always_negative` | no for every item |
   | `majority_class` | the more frequent label among the discovery items, for every item; a tie gives yes |
   | `span_position` | yes when the item's `span_position` value is more frequent among positive discovery items than among negative ones |
   | `span_marking` | the same, on `span_marking` |
   | `window_length` | yes when `window_token_count` is at least, or at most, a threshold |
   | `presentation_order` | yes when `presentation_index` is at least, or at most, a threshold |

   Under balanced accuracy the first three rules score 0.5 on any artifact with items of both classes.
   They are listed so that the score of a rule that uses no cue is stated. A threshold rule tries
   "at least" and then "at most" over the sorted cue values and keeps the first candidate with the highest
   balanced accuracy, so a cue that carries nothing gives a rule that says yes to every item. A rule whose
   cue the task does not expose is not in the candidate set.

   **How "best" is chosen.** Each rule is fitted on the pooled discovery items of the stage. The rule with
   the highest mean balanced accuracy over discovery families is the baseline; a tie goes to the earliest
   rule in the list. The baseline and its fitted values are frozen before any validation or fresh-test
   item is scored. Without discovery items of both classes no baseline exists and the control is not run.

   **Reporting.** The score of the real description is always reported beside the baseline's score, and
   beside every rule's score on the same items. The report also names the rule that scores highest on each
   analysis set. That rule was chosen after seeing those items; it is reported and the verdict rule does
   not use it.

### The verdict rule

For one description stage, one analysis set and one register, a control is compared with the matched
description through the family-clustered bootstrap interval of the mean of (matched score − control
score), with the family as the unit. There are three control margins: `matched_minus_shuffled`,
`matched_minus_irrelevant` and `matched_minus_explanation_free`.

| Comparison outcome | Condition |
|---|---|
| `control_beaten` | the whole interval lies above the control margin |
| `control_not_beaten` | the whole interval lies at or below the control margin |
| `advantage_not_shown` | the interval contains the margin, or the set has fewer families than the plan's minimum and no interval is computed |

**The held-artifact endpoint gets a verdict only when, in each register, the matched description beats the
shuffled description, the irrelevant description and the frozen baseline.** In every other case the scorer
returns a named state in place of the verdict. The states, in the order in which the first that applies
is returned:

| State | Meaning |
|---|---|
| `control_not_run` | The bundle has no control plan, no evaluation items, no shuffle mapping for the stage, no fitted baseline, or no score at all for one of the three controls in this set |
| `control_incomplete` | A control, or an item cue, is recorded for some of the set's artifacts or items and missing for others |
| `no_advantage_over_control_description` | In some register the shuffled or the irrelevant description is `control_not_beaten`: the matched description did not outscore it by the margin. The state names the comparison and does not establish why (it was named `scorer_does_not_read_description` until 2026-11-11) |
| `baseline_not_beaten` | In some register the frozen baseline is `control_not_beaten` |
| `description_reading_not_shown` | The advantage over the shuffled or the irrelevant description is `advantage_not_shown` |
| `baseline_advantage_not_shown` | The advantage over the frozen baseline is `advantage_not_shown` |
| `controls_passed` | All six comparisons are `control_beaten`; the three-outcome verdict of [Equivalence margins and uncertainty](#equivalence-margins-and-uncertainty) is issued |

- Missing control data is recorded as missing, with the reason, and blocks the verdict. A missing verdict
  on one item makes that condition's score missing for the artifact. It is never read as "no", as zero or
  as a pass.
- A withheld verdict is not a null result. The mean difference, its interval and every control comparison
  are still reported. Only the verdict is replaced, by the state, and `verdict_issued` is false.
- The state replaces all three outcomes, not only `equivalent_within_margin`. A score that a rule can
  reach without the description is not used as evidence of a difference either.
- **The `label` and `score` stages get no "passes" verdict.** The report has no field that says a stage
  passes. Each of these stages carries its description-control state per analysis set, and the primary
  fact-recovery result of the stage prints that state beside the verdict. A `label` or `score` stage is
  described as showing register equivalence only where the state is `controls_passed`. The fact-recovery
  verdict is computed as before and is not changed by the state. For a labeler that accepts no description
  the manipulation and its controls do not apply, and the state stays `control_not_run`.

**The control margins are placeholders.** The rubric names the three margins, with the draft status of the
rest of the rubric, and holds no value for them. Each is fixed in the study protocol before data, with a
stated reason, and copied into the bundle with `prespecified: true`; the scorer refuses a plan that is not
prespecified (`control_margins_not_prespecified`) or lacks a margin (`missing_control_margins`). The value
0.125 in the synthetic fixtures was written to exercise the scorer. It is not a proposal.

### Cue checks

A cue is a property of how an item or a description was built that a scorer could use without reading
what the description says. Each cue is checked where the scoring task exposes it. Every bundle field
below is optional.

| Cue | Bundle field | Check |
|---|---|---|
| Position of the scored span in its window | `evaluation_items[].span_position` | The `span_position` rule's score on the same items |
| How the span is marked | `evaluation_items[].span_marking` | The `span_marking` rule's score on the same items |
| Length of the window | `evaluation_items[].window_token_count` | The `window_length` rule's score on the same items; and, over families, the association between mean window length and the matched score |
| Presentation order of the items | `evaluation_items[].presentation_index` | The `presentation_order` rule's score on the same items |
| Length of the description | `held_artifact[].description_token_count` | Per pair, the medical-minus-everyday token difference and a `length_confounded` flag when the two counts differ; over families, the association between that difference and the score difference |
| Formatting of the description | `held_artifact[].formatting_class` | Per pair, a `formatting_differs` flag when the two classes differ |
| Presentation order of the two descriptions | `held_artifact[].presentation_order` | Over families, the association between the medical description being scored first and the score difference |

- **States.** `exposed`: the bundle records the cue for every item or pair in scope, and the check is
  computed. `not_exposed`: it records the cue for none of them. `partly_recorded`: it records the cue for
  some only; the data are missing, the check is not computed, and for an item cue the control state is
  `control_incomplete`.
- **`not_exposed` is never a pass.** The scorer cannot tell a task that has no such cue from a bundle that
  did not record it. `not_exposed` means the cue was not checked. The control state can be
  `controls_passed` with unexposed cues; the report then names them beside the verdict.
- **Association.** The statistic is the Pearson correlation between the cue and the score over the
  families of the analysis set. The p-value comes from a permutation test: the cue values are shuffled
  among the families by `random.Random("<seed>:cue:<stage>:<cue>:<analysis set>")`, and
  p = (1 + number of shuffles whose |r| is at least the observed |r|) / (1 + permutations). The number of
  permutations and the level `alpha` are fixed in the bundle. `association_detected` means p ≤ alpha.
  `association_not_detected` is not evidence that the cue has no effect. `not_computable` is returned, with
  the reason, for fewer than three families or when the cue or the score takes one value. With few
  families the test can detect only a near-perfect association: four families allow 24 orderings.
- **Reported with every difference.** Each held-artifact result, in every analysis set, carries the
  description cues of its pairs: the number of pairs whose lengths differ and their artifact ids, the mean
  token difference, the mean score difference among length-matched pairs and among the others, the pairs
  whose formatting differs, and the two associations. A reader sees the length and formatting difference
  next to each medical-minus-everyday difference.
- **A flag does not block.** A `length_confounded` pair stays in the analysis, and a detected association
  does not change the control state. Whether pairs are matched or bounded, and whether a detected
  association should withhold the verdict, is the open half of design question 2.
- **Not computed.** No association is computed between item order and a score, because a description has
  one score and item order does not vary between the descriptions of an artifact. The association between
  a cue and the scorer's item-level verdicts is not computed.

### How this differs from the source

Checked on 2026-11-10 against arXiv:2610.37676v1: the abstract page and, in the full-text HTML, the
definitions of the explanation-free rule and the estimand, the sections on the scorer comparisons and on
the trained scorer, the limitations, the conclusion and the appendix passages on the shuffled-explanation
control.

- The paper defines an explanation-free rule as a function of the item's construction alone, reports a
  score beside the maximum over a pre-specified family of such rules on the same items, and calls a score
  evidence about an explanation only when it exceeds that maximum and a shuffled explanation brings the
  scorer down to or below it. It flags rules chosen after seeing the data as optimistic.
- This design freezes one rule on discovery families and compares the matched description with that rule.
  The maximum over the family on each analysis set is reported and is not used. Inference: a cue that
  carries the label on held-out items and not on discovery items would not be selected; the report shows
  it, and the verdict rule does not withhold the verdict for it.
- This design requires the matched description to beat the shuffled description and the baseline, each by
  a margin. It does not require the shuffled description to fall to the baseline. Both means are in the
  report.
- The irrelevant-description control is the owner's instruction. The paper does not use one. Its nearest
  arm is a blank explanation, which it reports as out of distribution for the small scorer it trained on
  stored snippets.
- The paper's rules read token positions, mark sets and sequence membership in token-level tasks, and it
  also scores simulation tasks by correlation. This design reads one position class, one marking class,
  one window length and one presentation index per item, and scores by balanced accuracy only.

### Adjacent work: feature sensitivity

Tian, Tian and Hu (arXiv:2509.23717v1) was re-read on 2026-11-10 for this section: the abstract page and,
in the full-text HTML, the method, the comparison with standard metrics, the human evaluation and the
limitations. The paper measures how often a feature fires on new text of the same kind as its activating
examples, without writing a description of the feature. It reports that among 1,347 features with an
automated-interpretability score of at least 0.9, 82 have a sensitivity of 0.5 or lower. It states that
many features fail to fire on their own truncated examples, and it kept only features that fire on at
least 90% of them and occur at least 15 times in 2 million tokens. It reports excluding 35% of features
on average for its narrower autoencoders and 51% to 79% for the GemmaScope ones.

- Inference: the description controls test whether a scorer reads the description. They do not test
  whether the artifact responds to every input the description denotes. A description can pass all three
  controls while its artifact stays silent on part of the text it describes.
- Inference, for the `activation` stage: a component that is silent on an everyday variant may be
  insensitive, with register playing no part. The design's check for that is the within-register
  paraphrase endpoint. Open design question 4 asks whether the "representation changed" threshold should
  use it. This change does not alter the `activation` stage.
- Inference, for the `activation` stage: the paper's truncation finding shows that a feature's firing can
  depend on how much context it is given. A length difference between the medical and the everyday variant
  could therefore move an activation-stage value. This change records token counts for descriptions only.
  Variant token counts have no bundle field and stay in the study protocol's control section.
- The paper's human evaluation uses a mismatched item as a negative control, a text generated for a random
  other feature. That is the same kind of control as the shuffled description, applied to texts.

### Specified, implemented, not tested

- **Specified:** the three controls, the closed rule family, the selection rule, the verdict rule with its
  states, the seven cue checks and their states.
- **Implemented on synthetic fixtures:** all of the above, in `scripts/instrument_validity.py`, checked by
  `tests/test_instrument_validity.py` against `tests/fixtures/instrument_validity/synthetic_bundle.v1.json`
  (controls passed) and `tests/fixtures/instrument_validity/synthetic_control_states.v1.json` (one cell per
  other state). The fixtures' verdicts, cues and scores are placeholders written by hand to reach each
  state. They are not results and describe no scorer.
- **Not tested:** any real scorer. Whether descriptions taken from another case family are different
  enough to make the shuffled control informative. Whether the placeholder is irrelevant to real items.
  Whether the closed family covers the cues a real scoring task exposes; a rule outside the family is not
  excluded when the controls are passed. Which control margins are defensible. Whether a scoring task that
  does not return item verdicts can be given these controls at all.

## Input-only and control-artifact arms

Added on 2026-11-11, at the owner's decision on open design question 3. They apply to a `label` or `score`
stage whose instrument reads an activation artifact: an activation verbalizer, or a scorer that is given
activations. The question they answer: is what the instrument reports recoverable from the wording alone?

The reference facts of a family are facts stated in its input. A verbalizer model that restates the input
earns recovery credit without reading any activation, and a register difference in its recovery can then
come from how that model reads the two wordings. Three arms separate these:

| Arm | What the system is given | Where it lives in a bundle |
|---|---|---|
| actual artifact | the activation artifact of the family's variant | the stage's own `observations` |
| `input_only` | the variant's wording and no activation | `verbalizer_arms.stages.<stage>.observations`, `arm: "input_only"` |
| `control_artifact` | the same-register artifact of another family, and not the wording | the same list, `arm: "control_artifact"`, with `control_family_id` |

The system, its prompt and its settings are the same in all three arms. The other family of the
`control_artifact` arm is fixed before data by `seeded_derangement` over the sorted family ids with the
label `"<seed>:control_artifact:<stage>"`, so no family is given its own artifact; the scorer recomputes the
assignment and refuses a bundle that differs (`control_artifact_mapping_not_reproducible`). The study
protocol states how a control artifact is matched (model revision, hook, layer, position class, register)
in `control_artifact_rule`.

Every arm is scored against the family's own reference facts, with the same fact-recovery rate as the
stage. Per register and analysis set, the family-clustered bootstrap interval of the mean of (rate with the
actual artifact − rate of the arm) is compared with the arm's margin, `artifact_minus_input_only` or
`artifact_minus_control_artifact`, exactly as a description control is compared with the matched
description. The stage then carries one state per analysis set, the first that applies:

| State | Meaning |
|---|---|
| `arms_not_run` | The bundle has no arm rows for the stage, or no row at all for one of the two arms in this set |
| `arms_incomplete` | An arm row, a fact status, or the actual-artifact row it is compared with is missing for some family of the set |
| `no_advantage_over_control_artifact` | In some register the control artifact is `control_not_beaten`: the actual artifact did not outperform another family's artifact by the margin |
| `no_advantage_over_wording_alone` | In some register the wording alone is `control_not_beaten`: the actual artifact did not outperform the wording alone by the margin |
| `artifact_specificity_not_shown` | The advantage over the control artifact is `advantage_not_shown` |
| `artifact_contribution_not_shown` | The advantage over the wording alone is `advantage_not_shown` |
| `artifact_contributes` | All four comparisons are `control_beaten` |

- A stage's fact recovery is described as coming from the artifact only in the state
  `artifact_contributes`. Every other state says that the advantage was not demonstrated at the margin,
  and nothing more. It does not establish that the system ignores the artifact, and it does not establish
  that the output comes from the wording. When no arm recovers any fact, every difference is zero: the
  state is `no_advantage_over_control_artifact` where an interval is computed, and
  `artifact_specificity_not_shown` where the set has too few families for one. Where every family of the
  set has a rate in every arm and every rate is zero, the report sets `no_fact_recovered_in_any_arm` and
  says the comparison is uninformative; a set with an arm that was not run or is partly recorded does not
  get the flag. A missing or unsuccessful measurement is not evidence for either explanation. (Until 2026-11-11 the two `no_advantage` states were named `system_does_not_read_artifact`
  and `recoverable_from_wording_alone`, which stated a cause the comparison cannot show.)
- The report gives each arm's mean rate (`mean_rates`) beside the state, the medical-minus-everyday
  difference under each arm, and the artifact arm's difference minus the `input_only` arm's difference
  with its interval. A register difference that is equally large with the wording alone is not evidence
  about the representation. That last quantity gets no verdict.
- The state does not replace the stage's fact-recovery verdict, which is computed as before. It is printed
  beside it (`artifact_arm_state`), as the description-control state is.
- Missing arm data is recorded as missing with its reason. It is never read as zero or as a pass.
- The two arm margins are fixed in the study protocol before data, on calibration families, and copied
  into the bundle with `prespecified: true`. The scorer refuses arms that are not prespecified
  (`arm_margins_not_prespecified`) or lack a margin (`missing_arm_margins`). The value 0.125 in the tests
  exercises the scorer. It is not a proposal.
- For an instrument that reads no activation (a labeler given text only) the arms do not apply and the
  state stays `arms_not_run`.

**One unit per phrase.** A medical or everyday text that occurs in two families is refused
(`repeated_phrase`). A phrase that recurs in several source rows is one family, and its rows are averaged
before scoring, so that a repeated phrase is not counted as several independent observations.

Implemented in `scripts/instrument_validity.py` and checked on synthetic rows by
`tests/test_instrument_validity_arms.py`. Not tested: any real verbalizer or scorer; whether another
family's artifact is a fair control for a given capture site; which arm margins are defensible.

## Controls and independence

- **Surface confounds.** Tokenization, length, position and formatting differ between registers. Record
  token counts and target-token identity per variant. Report the main difference alongside the
  within-register paraphrase result and the length and context control, so that a register effect can be
  told apart from a length or tokenization effect. For the descriptions of the held-artifact manipulation
  the bundle records the token count, the formatting class and the presentation order
  ([Cue checks](#cue-checks)). For the variants it has no field for token counts or formatting; they are
  recorded in the study protocol's control section.
- **Pinned identities.** Model, tokenizer, method and artifact identities are pinned and stored: the
  model and tokenizer revisions once, and a method id, method revision, artifact id and artifact digest
  per stage.
- **Split before development.** Families are assigned to `discovery`, `validation` or `fresh_test` by
  case family, before label development, threshold selection or scorer calibration. The bundle declares
  the split each threshold was selected on and the split labels and scorers were developed on. Each must
  be `discovery`; anything else refuses (`threshold_split`, `development_split`). A family in two splits,
  or one text in two splits, refuses (`split_leakage`).
- **Primary analysis set.** The plan names it: `validation`, `fresh_test`, or `held_out` (both). A set
  that contains discovery families cannot be primary. Results on discovery families are reported and
  marked as such.
- **All cases and the comparable-behaviour subset.** Report every family. Where the plan prespecifies
  it, also report the subset of families whose model behaviour is comparable between the two registers
  (behaviour difference determined and not above the behaviour threshold). In that subset an instrument
  difference cannot be explained by the model behaving differently. The subset never replaces the
  all-cases result.
- **Agreement is not replication.** Two methods that share a vocabulary, a fitting corpus or a judge can
  agree because they share it. Their agreement is reported as agreement between dependent methods. It is
  not counted as independent replication.

## The four-cell report

Per stage, each family is placed by two binary facts, each defined by a threshold selected on discovery
families only:

- **behaviour changed:** the absolute medical-minus-everyday difference in `behaviour_value` is above the
  behaviour threshold;
- **measured representation changed:** the absolute medical-minus-everyday difference in that stage's
  `representation_value` is above the stage's representation threshold.

The report gives the count, the share and a Wilson interval for each cell, and lists the families in it.
A family with a missing input is listed as undetermined with the missing field named. A stage with no
declared representation threshold gets an undetermined table. Nothing missing is counted in a cell.

| | Representation changed | Representation unchanged |
|---|---|---|
| **Behaviour changed** | Consistent with the model handling the two wordings differently and the instrument detecting a difference. It does not show that the detected difference caused the behaviour. | **May be limited method coverage.** The instrument may not read the place, the direction or the quantity where the difference lives. It does not show that no internal difference exists. |
| **Behaviour unchanged** | **May be register encoding.** A model can represent how something was said without that changing what it does. It does not show a fault in the model or in the instrument. | Consistent with equivalence at this stage and this endpoint. It does not show equivalence at another stage, layer or endpoint. |

Neither off-diagonal cell, alone, establishes tool bias. No cell establishes the model's true internal
understanding. The table is descriptive.

Equal behaviour on a measured endpoint does not imply identical hidden states, and it does not establish
instrument bias. It is one measured endpoint of the model's output, at one threshold.

Stronger evidence of instrument bias needs one of two things:

1. a **systematic measurement error against an independently justified reference**: the instrument's
   reading departs from the reference facts in one direction for one register, across held-out families,
   beyond the margin, while the changed-fact control shows the instrument does respond to content; or
2. the same departure **under a controlled manipulation**, which here is the held-artifact manipulation.

## Null and discordant cases

Null and discordant families are kept and listed by id. They are not dropped, averaged away or replaced.

- **Null family (per stage):** paired fact-recovery difference of exactly zero.
- **Null family (whole bundle):** zero difference in every stage that scored the family, behaviour
  determined and unchanged, and no detected representation change in any determined table.
- **Direction-discordant family (per stage):** a paired difference whose sign is opposite to the stage's
  mean difference.
- **Cross-stage sign-discordant family:** a positive difference at one stage and a negative difference at
  another.

A family excluded for missing data is listed with its reason and counted in the denominator line
(`n_families`, `n_included`, `excluded`). Missing is never zero.

## Cautions specific to ICA components

These apply when the `activation` stage uses an independent component basis.

- **One fixed fitted basis for both members of a pair.** Both variants are projected on the same fitted
  unmixing matrix, with one artifact digest. A basis fitted separately per variant or per register is a
  different coordinate system and the scores are not comparable.
- **Scores are signed.** A component score has a sign. Do not take absolute values before pairing; a
  sign flip between variants is a difference.
- **Energy shares are not probabilities.** The share of variance or squared score on a component is a
  descriptive ratio. It is not the probability that a concept is present and is not compared to a model
  probability.
- **Sign, order and scale do not align across fits.** ICA recovers components up to sign, permutation
  and scale. Component 12 of one fit is unrelated to component 12 of another fit, seed or model. Any
  cross-fit comparison needs an explicit matching step with its own error, declared before data.
- **A component label is a `label`-stage output.** A medically named component is subject to the same
  test as any other label, including the held-artifact manipulation.

## Contract and files

| File | Role |
|---|---|
| `schemas/protocols/instrument_validity.v1.schema.json` | Structural schema of one bundle, `patientwords.instrument-validity/1`. Written in the keyword subset `scripts/frontend_contract_schema.py` executes, so the schema is run, not only read |
| `scripts/instrument_validity.py` | Offline validator and scorer. `--bundle PATH [--out PATH]` |
| `data/protocols/instrument_validity_rubric.draft.json` | Annotation rubric, `patientwords.instrument-validity-rubric/1`, draft |
| `tests/fixtures/instrument_validity/synthetic_bundle.v1.json` | Synthetic fixture with abstract placeholder facts and wordings; its description controls are passed |
| `tests/fixtures/instrument_validity/synthetic_control_states.v1.json` | Synthetic fixture for the description controls: one cell per control state, abstract placeholder items and verdicts, no stage observations |
| `tests/test_instrument_validity.py` | Hand-computed expectations for the fixture, and the refusals |
| `tests/test_instrument_validity_arms.py` | The input-only and control-artifact arms: one test per arm state, the refusals, and the repeated-phrase refusal |
| `docs/protocols/instrument_register_experiment_20261111.md` | The first bounded experiment that uses this benchmark: its design, calibration rule and execution packet |
| `docs/protocols/protocol_template.md` | The protocol a real run of this benchmark would fill in first |

```bash
python scripts/instrument_validity.py \
  --bundle tests/fixtures/instrument_validity/synthetic_bundle.v1.json
# exit 0; prints a report with execution_status "synthetic"

python scripts/instrument_validity.py \
  --bundle tests/fixtures/instrument_validity/synthetic_control_states.v1.json
# exit 0; the held-artifact results carry the control states

python -m pytest -q -p no:cacheprovider tests/test_instrument_validity.py
```

The scorer prints the report. With `--out` it creates
`instrument_validity/instrument_validity_report.<id>.json` exclusively, outside every Git checkout and
outside the protected data trees. A refusal prints `{"status": "refused", "code", "detail"}` and exits 2.
The file name matches no collector pattern (`batch_summary*`, `verify_summary*`).

The report repeats the status line of this file, the seed, the bundle digest, the margins, the
thresholds, the verdict rule and the control rule. It keeps `model_behaviour` and the per-stage
instrument results in separate objects. Every random step writes its seed label: the bootstrap intervals,
the shuffle of the descriptions and the cue permutation tests.

`description_controls`, `evaluation_items`, `verbalizer_arms` and the three per-description cue fields are
optional. A bundle without them is still valid; without `verbalizer_arms` a description stage reports
`arms_not_run`. Its held-artifact endpoint then reports `control_not_run` and gets no
verdict; before 2026-11-10 it got one.

**Version 1 admits synthetic bundles only.** A bundle with `synthetic: false` refuses
(`real_bundle_not_admitted`), and a synthetic bundle that declares any `execution_status` other than
`synthetic` refuses (`synthetic_claims_measurement`). Reason: this repository counts only CI-produced
outputs as measurements, and no CI lane produces these bundles. Admitting real bundles is a later
change that needs a reviewed lane, provenance fields and its own tests.

## What is verified and what is not

**Verified offline, on the synthetic fixtures, 2026-11-10:**

- The schema file is inside the executed keyword subset and both fixtures conform to it.
- The scorer reproduces hand-computed values for: per-family recovery rates and paired differences in
  four stages; partial credit and contradiction; means per analysis set; changed-fact sensitivity with
  Wilson intervals; unsupported-fact means by register; paraphrase consistency; rank medians with one
  `not_observed_in_window`; both four-cell tables; the held-artifact difference with two artifacts in one
  family.
- The bootstrap interval equals an independent re-implementation under the same seed label. The same
  seed reproduces the report; a different seed is recorded as different.
- All three verdict outcomes occur, and a set below the minimum family count is never called equivalent.
- One absent observation is excluded with its reason and is not scored as zero.
- The named refusals fire: missing or non-prespecified margins, a family or a text in two splits, a
  threshold or a development step on a non-discovery split, a missing register, a missing changed-fact
  control, non-finite values, an unknown stage, a synthetic bundle claiming to be a measurement, a
  missing seed, inconsistent behaviour across stages, an artifact not held fixed.
- Description controls: every condition's balanced accuracy on each artifact's own items equals the hand
  computation; the shuffle mapping equals an independent re-implementation of the seeded derangement and
  pairs no artifact with its own family; the rules are fitted and selected on discovery items only and do
  not move when held-out items change.
- Each control state occurs on a fixture and replaces the verdict: a scorer whose verdicts ignore the
  description, a cue-only rule that reaches the matched score, an absent control, a control or a cue
  recorded in part, and an advantage the interval does not settle. In six of those fixture cells the
  interval is [0, 0]. The scorer source of the commit before this change, run on the same bundle with the
  new schema, reported each of the six as `equivalent_within_margin`. Where every control is beaten, the
  verdict is issued.
- Cue checks: an unexposed cue is reported as `not_exposed`; a pair of unequal length is flagged beside
  the difference; the permutation p-value equals an independent re-implementation, lies within 0.012 of
  the exactly computed value in two cases and is exactly 1 in two others.
- The control refusals fire: a plan that is not prespecified, a missing, unknown or non-positive control
  margin, another metric, another rule family, another irrelevant description, a shuffle mapping that is
  not the seeded derangement, an item for an unknown artifact, a declared score that the item verdicts do
  not reproduce.
- Input-only and control-artifact arms (2026-11-11, `tests/test_instrument_validity_arms.py`): each of the
  seven arm states is reached from hand-worked rows; a bundle without the arms reports `arms_not_run` and
  every earlier result is unchanged; a missing arm row, a missing fact status and a missing
  actual-artifact row are `arms_incomplete`; the control assignment equals a re-run of the seeded
  derangement; thirteen named refusals fire; the same phrase in two families is refused.

These checks establish that the software computes what this file says. The fixtures' numbers were
written by hand to exercise code paths. They describe no model, no instrument and no scorer.

**Not verified. Each needs real data or people:**

- Whether any instrument shows a register difference. Nothing has been measured.
- Whether reference facts can be established reliably and independently for real case families.
- Whether the rubric gives acceptable agreement between annotators, and whether annotators agree equally
  on outputs from the two registers.
- Whether annotators can stay blind to the source register when an output echoes the input wording.
- What margin is defensible for each endpoint, and how many families a given margin needs. This needs
  pilot variance and a sensitivity analysis.
- Whether a scalar `representation_value` is an adequate summary at each stage, and how its threshold
  behaves on discovery families.
- Whether meaning-equivalent description pairs for the held-artifact manipulation can be written and
  reviewed at scale.
- Whether any real scorer passes or fails the description controls, and everything listed as not tested
  under [Description controls and cue checks](#specified-implemented-not-tested).
- Whether any real verbalizer or scorer earns its fact recovery from the artifact or from the wording
  alone. The arms were exercised on placeholder rows only.
- Whether the hosted and local instruments expose what the bundle needs. A top-k interface cannot supply
  full-vocabulary ranks (`docs/exploratory/methods_integration.md`).
- The lens-fit provenance questions that already block real readouts
  (`docs/exploratory/lens_fit_provenance_question.md`).

## Related work: sources read

Read on 2026-11-10 from arxiv.org. For each paper below, the abstract page and the full-text HTML of the
latest arXiv version were opened. The abstract and the sections on method, validation, text sources and
limitations were read. An appendix was read only where an entry reports something from it. Each entry
gives the arXiv identifier with the version read and the date read. A sentence that begins "Inference:"
is this file's reading of how the paper bears on the benchmark. It is not a claim the paper makes. The
twelve papers are the arXiv leads of an earlier web search. This is not a literature review, and this
file makes no novelty claim.

### Explanations and their scores: the `label` and `score` stages

- Huang, Geiger, D'Oosterlinck, Wu and Potts 2023, "Rigorously Assessing Natural Language Explanations of
  Neurons" (arXiv:2309.10312v1, <https://arxiv.org/abs/2309.10312v1>; read 2026-11-10). The paper tests
  whether a neuron activates on all and only the strings its explanation denotes. For 300 GPT-2 XL
  neurons whose GPT-4 explanations had a simulation score of at least 0.8, it reports an F1 "around 0.6"
  and a causal effect similar to a random baseline on most tasks. Inference: a high score for a label
  does not show the label is right, which supports assessing outputs against reference facts established
  without the instrument and scoring the `label` and `score` stages apart. The paper also reports that
  more than 30% of the explanations in its source set contain "related to"; that bears on the rubric's
  open question about applying `partially` consistently.
- Paulo, Mallen, Juang and Belrose 2024, "Automatically Interpreting Millions of Features in Large
  Language Models" (arXiv:2410.13928v3, <https://arxiv.org/abs/2410.13928v3>; read 2026-11-10). The paper
  builds an open pipeline that writes and scores explanations of sparse-autoencoder features. It finds
  that explanations written from top-activating examples have higher specificity and lower sensitivity,
  and that this "would not be seen" if scoring used only the most activating examples. Inference: a
  `score`-stage number depends on which contexts the scorer is shown, so the held-artifact manipulation's
  rule of one activation set per artifact is necessary for two descriptions to be comparable.
- Chen 2026, "Scoring Explanations Without Reading Them: Structural Shortcuts in
  Automated-Interpretability Evaluation Data" (arXiv:2610.37676v1, <https://arxiv.org/abs/2610.37676v1>;
  read 2026-11-10). On Neuronpedia's stored fuzzing runs for 500 random GPT-2 small features, a rule that
  never reads the explanation reaches balanced accuracy 0.979, against 0.838 for the stored LLM scorers,
  on marks rebuilt from the pipeline's code. The paper recommends reporting each score beside the best
  explanation-free rule on the same items. This bears on the held-artifact manipulation: open design
  question 1. The paper's scorer on cue-free windows is Jev, requested as `jev-1.13.0`; this repository
  records its Jev classifier as `typesafe/jev-1.13` (`docs/triggers.md`). Inference: the name and version
  match, so it is the same product. The paper uses it to predict feature activations from an explanation,
  not for the decisions classification this repository audits, and its result says nothing about that
  use.
- Soumik 2026, "Judging the Judges: A Systematic Evaluation of Bias Mitigation Strategies in
  LLM-as-a-Judge Pipelines" (arXiv:2604.23178v2, <https://arxiv.org/abs/2604.23178v2>; read 2026-11-10).
  The paper's "style bias" is a preference for markdown over the same content in plain prose. On pairs
  built so that an unbiased judge should say "tie", four of five judge models prefer markdown (signed
  bias 0.40 to 0.76), and three of five prefer an expanded answer to its base answer. The paper states
  that formal against casual register was not measured. Inference: it is evidence that a model judge's
  verdict moves with presentation when content is fixed, which is the logic of the held-artifact
  manipulation and a reason to control formatting and length in it (open design question 2). It is not
  evidence about register. This repository's own check of a behavioural judge is
  `docs/exploratory/judge_register_sensitivity_20261106.md`.
- Li, Ceballos Arroyo, Rogers, Saphra and Wallace 2025, "Do Activation Verbalization Methods Convey
  Privileged Information?" (arXiv:2509.13316v4, <https://arxiv.org/abs/2509.13316v4>; read 2026-11-10;
  version 1 was titled "Do Natural Language Descriptions of Model Activations Convey Privileged
  Information?"). On tasks used in earlier verbalizer evaluations, the verbalizer model given only the
  input text is "competitive" with two verbalization methods given the target model's activations. With a
  target model fine-tuned on fabricated personas, neither method exceeds zero accuracy on the fully
  fabricated set. This bears on the `label` stage when the instrument is a verbalizer: open design
  question 3. The held-artifact manipulation does not address it, because a verbalizer's output is the
  description.

### Component activations: the `activation` stage

- Tian, Tian and Hu 2025, "Measuring Sparse Autoencoder Feature Sensitivity" (arXiv:2509.23717v1,
  <https://arxiv.org/abs/2509.23717v1>; read 2026-11-10). A language model writes new text of the same
  kind as a feature's activating examples, and the paper measures how often the feature fires on it: on
  average 0.92 to 0.94 for 65K-width GemmaScope autoencoders and 0.85 to 0.87 for 1M-width ones. Blinded
  annotators rated 79% of 62 generated texts that failed to activate their feature "indistinguishable"
  from the activating examples. Inference: a feature can stay silent on text of the kind it is labelled
  for with no change of register, which supports reading a cross-register difference against the
  within-register paraphrase result. The paper does not vary register. Inference: the description
  controls added on 2026-11-10 do not measure sensitivity; what follows for the `activation` stage is
  stated under [Adjacent work: feature sensitivity](#adjacent-work-feature-sensitivity).
- Li, Srinivas, Bhalla and Lakkaraju 2025, "Evaluating Adversarial Robustness of Concept Representations
  in Sparse Autoencoders" (arXiv:2505.16004v2, <https://arxiv.org/abs/2505.16004v2>; read 2026-11-10;
  version 1 was titled "Interpretability Illusions with Sparse Autoencoders: Evaluating Robustness of
  Concept Representations"). The paper searches for one-token input changes that alter a sparse
  autoencoder's active latents. In a test without adversarial search, replacing one word with a synonym
  lowers the overlap of the top-k active latents by "roughly 30%" and does not change whether the
  individually selected latents are active. Inference: a same-meaning rewording inside one register
  already moves a set-level summary, and a set-level and a single-latent summary give different answers.
  This bears on the four-cell report: open design question 4.
- Kantamneni, Engels, Rajamanoharan, Tegmark and Nanda 2025, "Are Sparse Autoencoders Useful? A Case
  Study in Sparse Probing" (arXiv:2502.16681v1, <https://arxiv.org/abs/2502.16681v1>; read 2026-11-10).
  On eight test sets with a covariate shift, logistic regression on activations often generalizes better
  than a probe on sparse-autoencoder latents. In one case a latent that detects "living room" has a test
  AUC of 0.99 on English prompts and 0.64 on prompts translated to French, and does not fire on the
  French phrase. Inference: this is a measured case of an instrument component that reads a concept in
  one surface form and not in another, which is the kind of failure the benchmark tests for. The shift is
  language, not register, so it is not an instance of the benchmark's hypothesis.
- Sadanandan and Behzadan 2026, "PSF-Med: Measuring and Explaining Paraphrase Sensitivity in Medical
  Vision Language Models" (arXiv:2602.21428v2, <https://arxiv.org/abs/2602.21428v2>; read 2026-11-10).
  Across nine models, 3% to 37% of yes/no answers to chest X-ray questions flip under meaning-preserving
  paraphrase. For one model, a sparse-autoencoder feature is high for formal clinical phrasing and low
  for casual phrasing of the same question, and removing its contribution recovers 44.8% of the answer
  margin on average over 158 flip cases. Of the twelve papers this is the closest to the benchmark's
  subject. It reports a property of the model, read through the autoencoder; it does not test whether the
  autoencoder reads the two registers equally well. Its register comparison is a small grid of phrasings,
  and its paraphrases were validated by a model judge without human adjudication. The 158 flip cases are
  pairs of a question and its paraphrase, selected by answer flip, embedding similarity and unambiguous
  answer parsing. They are not medical and everyday pairs, and the paper applies no threshold to a
  representation difference. Inference: the paper does not place any case in a cell of the four-cell
  report. A flip case would fall in the "behaviour changed, representation changed" cell only if its two
  questions differed in register and the feature difference exceeded a threshold declared for that stage.
- Liu, Han, Wiegreffe and Huang 2026, "Non-Gaussianity Reveals Interpretable Directions in Language
  Models" (arXiv:2606.11722v2, <https://arxiv.org/abs/2606.11722v2>; read 2026-11-10; version 1 was
  titled "ICA Lens: Interpreting Language Models Without Training Another Dictionary"). The paper fits
  FastICA per layer to one million token activations collected on Pile-10k. It states that a component is
  fixed only up to sign and that a coherent pattern is "often concentrated in one tail", and it labels
  the tail selected by skewness. Across five seeds on one layer of GPT-2 Small, the median cosine between
  matched components is about 0.82 to 0.85 at the iteration budget its main experiments use. Inference:
  this supports the cautions that scores are signed and that a comparison across fits needs a matching
  step with its own error. Two points are not in the cautions: a label describes one tail of a component,
  and the paper's error analysis shows a label written from unrelated contexts when the corpus did not
  reach the tail. Whether Pile-10k holds enough everyday health wording for that is not known. The paper
  does not vary register.

### Lens readouts: the `readout` stage

- Belrose, Ostrovsky, McKinney, Furman, Smith, Halawi, Biderman and Steinhardt 2023, "Eliciting Latent
  Predictions from Transformers with the Tuned Lens" (arXiv:2303.08112v6,
  <https://arxiv.org/abs/2303.08112v6>; read 2026-11-10). The paper reports that the logit lens
  "systematically puts more probability mass on certain vocabulary items than the final layer does", by
  about 4 to 5 bits at most layers of GPT-Neo-2.7B. Its tuned lens is an affine map per layer, trained on
  a validation corpus (the model's pretraining validation set where available, otherwise the Pile's), and
  causal experiments show that the directions that most influence the tuned lens also influence the
  model's output. Inference: a full-vocabulary rank read through a logit lens partly measures the lens's
  own preference among vocabulary items, which supports keeping the exact-token rank as a lexical
  endpoint beside the semantic ones. A trained lens has a fitting corpus, one of the shared dependencies
  named under "Agreement is not replication". The paper does not test whether the bias differs between
  medical and everyday tokens.
- Gupta, Yeung, Anumanchipalli and Ivanova 2025, "How Do LLMs Use Their Depth?" (arXiv:2510.18871v2,
  <https://arxiv.org/abs/2510.18871v2>; read 2026-11-10). Read through the tuned lens on English
  Wikipedia prefixes, the top-ranked token at the first layer of Pythia-6.9B is one of the ten most
  frequent tokens more than 75% of the time, against 33% of the model's final predictions. The paper
  tests whether the lens produces this and concludes that it reflects the early-layer representations;
  with the logit lens the pattern reverses. Inference: at early layers an exact-token rank depends on the
  target token's corpus frequency and on which lens is used. The surface-confound list in this file names
  tokenization, length, position and formatting. It does not name token frequency.

### Leads dropped

- Bills et al. 2023, "Language models can explain neurons in language models": dropped. An arXiv title
  search on 2026-11-10 returned no result, and openai.com was not reachable from the session. What Huang
  et al. report about its simulation score is given under that entry as their account.
- The informal post "J-Lens: a failed replication on GPT-2": dropped. It is not on arXiv, and
  lesswrong.com was not reachable from the session.

### What these sources do not cover

None of the twelve papers tests whether an interpretability instrument recovers matched information
equally well from two registers. PSF-Med is the only one that varies register, and it reports a property
of the model. Soumik names formal against casual register as a dimension it did not measure. The other
ten do not study register or dialect; the word "dialect" occurs in none of the twelve full texts. This is
a statement about twelve papers. It is not a statement that no such work exists.

The earlier version of this section listed five searches that returned nothing relevant. That list is
removed, because a search result is not a source that was read. One of its lines said that no medical
sparse-autoencoder paper compared lay with clinical wording. PSF-Med, which was already among the leads,
compares formal clinical and casual phrasings of one question for one feature.

Not done: citation chasing; searching venues; reading the two dropped leads; reading every appendix. An
arXiv title search for "Jacobian lens" on 2026-11-10 returned five papers, and none was opened. A proper
review is needed before any statement about prior work appears outside this file.

## Open design questions

Raised on 2026-11-10 by the sources above. Each names a place where a source gives a reason to doubt that
a design choice measures what this file says it measures. The owner decided question 1 and part of
question 2 on 2026-11-10; the rubric, the schema, the scorer and the fixtures were changed for those two
only. On 2026-11-11 the owner decided question 3; the scorer, the schema and the tests were changed for it.
The rest of question 2, and question 4 as a general rule, are for the owner to decide.

1. **Decided by the owner, 2026-11-10: yes.** A mismatched-description control is required, together with
   an irrelevant description and an explanation-free baseline on the same items. The design is in
   [Description controls and cue checks](#description-controls-and-cue-checks). The question as raised:
   **The held-artifact manipulation has no control showing that the scorer reads the description.** This
   file calls the manipulation the strongest test in the benchmark. Chen (arXiv:2610.37676v1) shows that
   a rule that never reads the explanation can outscore the stored LLM scorers on the items a standard
   pipeline builds. A scorer that ignores both descriptions gives them the same score, and
   `scripts/instrument_validity.py` then returns `equivalent_within_margin` for a set with enough
   families. The changed-fact control guards the recovery endpoint against an instrument that responds to
   nothing. Nothing guards the held-artifact endpoint. Question: should the manipulation require a third,
   mismatched description of the same artifact, and give no equivalence verdict unless the mismatched
   description scores lower?
2. **Partly decided by the owner, 2026-11-10.** Decided: the token count, the formatting class and the
   presentation order of each description are recorded and checked, and reported with every
   medical-minus-everyday difference ([Cue checks](#cue-checks)). Still open: whether the pairs are
   matched on formatting and bounded in length ratio, and whether a detected length association withholds
   the verdict. The question as raised:
   **The held-artifact description pairs have no rule for formatting and length.** Soumik
   (arXiv:2604.23178v2) reports that four of five judge models prefer markdown to the same content in
   plain prose, and that three of five prefer an expanded answer to its base answer. This file asks only
   that the two descriptions mean the same thing, and notes that version 1 of the bundle has no field for
   token counts or formatting. Inference: if the everyday description of a fact is longer than the
   medical one, which has not been measured here, a length effect would be reported as a
   medical-minus-everyday difference. Question: should the pairs be matched on formatting and bounded in
   length ratio, or should both be recorded per description and reported with the difference?
3. **Decided by the owner, 2026-11-11: yes.** The same system is compared when given the wording alone,
   the actual artifact, and a matched control artifact. The design is in
   [Input-only and control-artifact arms](#input-only-and-control-artifact-arms). The question as raised:
   **The `label` stage has no input-only arm for a verbalizer.** Li et al. (arXiv:2509.13316v4)
   report that a verbalizer model given only the input text is competitive with verbalization methods
   given the target model's activations, and that the input can be reconstructed from those activations. The
   benchmark's reference facts are facts stated in the input. Inference: a verbalizer can earn recovery
   credit by restating the input, and a register difference in its recovery can come from how the
   verbalizer model reads the two wordings. That is still a property of the instrument. But this file
   separates a difference in the representation from a difference in the labeler, and for a verbalizer
   that separation needs an arm in which the verbalizer sees the input text and no activation. Question:
   should the `label` stage require that arm when the instrument is a verbalizer?
4. **Open as a general rule; fixed for the first experiment.** The owner's instruction of 2026-11-11 is that
   within-register paraphrases and changed-fact controls are included and that thresholds are set on a
   separate calibration set. `docs/protocols/instrument_register_experiment_20261111.md` therefore sets each
   stage's representation threshold on calibration families from the within-register paraphrase
   differences. The scorer's four-cell definition is unchanged: it takes the threshold as a value selected
   on discovery families. The question as raised:
   **The "representation changed" fact does not use within-register variation.** The four-cell
   report calls a family's representation changed when the medical-minus-everyday difference in
   `representation_value` is above a threshold selected on discovery families. Li et al.
   (arXiv:2505.16004v2) report that a one-word synonym replacement lowers the overlap of the top-k active
   latents by about 30% and leaves the individually selected latents unchanged. Tian et al.
   (arXiv:2509.23717v1) report that features fail to fire on some text that blinded annotators rate
   indistinguishable from their activating examples. Inference: a threshold that takes no account of
   same-meaning variation inside a register can place most families in a "representation changed" cell
   for one summary and few for another. This file says a cross-register difference is read against
   within-register variation, and the four-cell definition does not apply that. Question: should the
   representation threshold be set relative to the family's within-register paraphrase difference, and
   should the plan name each stage's scalar summary before data?

## Open decisions

These are the owner's, and nothing here presumes them.

1. Whether to pursue the benchmark at all, and on which model and instruments first.
2. Who establishes and reviews reference facts, and under what clinical-review status.
3. The margins, with their reasons: the equivalence margins, the three control margins of
   [Description controls and cue checks](#description-controls-and-cue-checks) and the two arm margins of
   [Input-only and control-artifact arms](#input-only-and-control-artifact-arms). All are placeholders.
4. Whether real bundles are admitted, and through which CI lane.
5. Where real outputs would live and which analysis membership, if any, they may enter
   (`docs/open_results_policy.md`).
6. The open half of design question 2, and design question 4 as a general rule.
7. Whether the verdict rule should also require the matched description to beat the highest-scoring rule
   of the closed family on each analysis set, as the source's criterion does, and not only the rule frozen
   on discovery families.
