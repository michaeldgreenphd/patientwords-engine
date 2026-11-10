# Interpretability-instrument validity benchmark: specification

**Status: proposed PatientWords contribution; no register bias has been measured with it.**

Written 2026-11-10. This file specifies a benchmark. It reports no result. The only thing that has been
run is an offline software check on a synthetic fixture, described under
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

## Endpoints

All endpoints are fixed before data. The semantic endpoints are primary.

| Endpoint | Definition | Reported as |
|---|---|---|
| Recovery of reference facts | Per variant and stage: mean credit over the family's reference facts. Recovered counts 1, partially counts the partial credit fixed in the plan, not recovered and contradicted count 0. | Paired medical-minus-everyday difference per family; mean, interval and verdict |
| Unsupported inferred facts | Count of statements in the instrument's output that the reference set does not support | Mean count per description, by register; paired difference |
| Sensitivity to genuinely changed facts | For each changed-fact control: whether credit for the changed fact fell below its base variant's credit | Share detected, by base register, with a Wilson interval. Controls whose base variant earned no credit are counted apart |
| Consistency across equivalent phrasings | Per-fact agreement between a within-register paraphrase and its base variant | Mean agreement share and mean absolute rate difference, by base register |
| Held-artifact score difference | Score of the medical-register description minus score of the everyday-register description, artifact fixed | Mean over families, interval and verdict |
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

## Controls and independence

- **Surface confounds.** Tokenization, length, position and formatting differ between registers. Record
  token counts and target-token identity per variant. Report the main difference alongside the
  within-register paraphrase result and the length and context control, so that a register effect can be
  told apart from a length or tokenization effect. Version 1 of the bundle has no field for token counts
  or formatting; until it does, they are recorded in the study protocol's control section.
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
| `tests/fixtures/instrument_validity/synthetic_bundle.v1.json` | Synthetic fixture with abstract placeholder facts and wordings |
| `tests/test_instrument_validity.py` | Hand-computed expectations for the fixture, and the refusals |
| `docs/protocols/protocol_template.md` | The protocol a real run of this benchmark would fill in first |

```bash
python scripts/instrument_validity.py \
  --bundle tests/fixtures/instrument_validity/synthetic_bundle.v1.json
# exit 0; prints a report with execution_status "synthetic"

python -m pytest -q -p no:cacheprovider tests/test_instrument_validity.py
```

The scorer prints the report. With `--out` it creates
`instrument_validity/instrument_validity_report.<id>.json` exclusively, outside every Git checkout and
outside the protected data trees. A refusal prints `{"status": "refused", "code", "detail"}` and exits 2.
The file name matches no collector pattern (`batch_summary*`, `verify_summary*`).

The report repeats the status line of this file, the seed, the bundle digest, the margins, the
thresholds and the verdict rule. It keeps `model_behaviour` and the per-stage instrument results in
separate objects.

**Version 1 admits synthetic bundles only.** A bundle with `synthetic: false` refuses
(`real_bundle_not_admitted`), and a synthetic bundle that declares any `execution_status` other than
`synthetic` refuses (`synthetic_claims_measurement`). Reason: this repository counts only CI-produced
outputs as measurements, and no CI lane produces these bundles. Admitting real bundles is a later
change that needs a reviewed lane, provenance fields and its own tests.

## What is verified and what is not

**Verified offline, on the synthetic fixture, 2026-11-10:**

- The schema file is inside the executed keyword subset and the fixture conforms to it.
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

These checks establish that the software computes what this file says. The fixture's numbers were
written by hand to exercise code paths. They describe no model and no instrument.

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
- Whether the hosted and local instruments expose what the bundle needs. A top-k interface cannot supply
  full-vocabulary ranks (`docs/exploratory/methods_integration.md`).
- The lens-fit provenance questions that already block real readouts
  (`docs/exploratory/lens_fit_provenance_question.md`).

## Related work: search leads, not yet read

Checked on 2026-11-10 with fourteen web-search queries from a session whose network could not reach
arxiv.org. The entries below come from search-result titles and summaries. **The papers themselves were
not opened or read**, so each one-sentence description is the search summary's account, not a verified
reading. arXiv links are given in their canonical `abs` form; the search returned `pdf`, `html` or
versioned forms of the same identifiers. This is a short check, not a literature review, and this file
makes no novelty claim.

Found, and relevant to a stage of this benchmark:

- Bills et al. 2023, "Language models can explain neurons in language models"
  (<https://openai.com/index/language-models-can-explain-neurons-in-language-models/>). Introduces
  simulation scoring of generated neuron explanations and notes that a high-scoring explanation
  describes a correlation and may fail on out-of-distribution text. Relevant to the `label` and `score`
  stages.
- Huang et al. 2023, "Rigorously Assessing Natural Language Explanations of Neurons"
  (<https://aclanthology.org/2023.blackboxnlp-1.24>). Evaluates such explanations in an observational and
  an intervention mode and reports high error rates even for confident explanations. Relevant to scoring
  validity.
- Paulo et al. 2024, "Automatically Interpreting Millions of Features in Large Language Models"
  (<https://arxiv.org/abs/2410.13928>). An open pipeline for generating and scoring feature explanations,
  with several scoring techniques and a discussion of pitfalls in existing scoring. Relevant to the
  `score` stage.
- Chen 2026, "Scoring Explanations Without Reading Them: Structural Shortcuts in
  Automated-Interpretability Evaluation Data" (<https://papers.cool/arxiv/2610.37676>). Argues that
  standard evaluation data for explanation scoring can be scored without reading the explanation.
  Relevant to whether a `score`-stage number reflects the description at all. The search summary names a
  scorer called Jev; whether it is the classifier this repository audits was not checked.
- Tian, Tian and Hu 2025, "Measuring Sparse Autoencoder Feature Sensitivity"
  (<https://arxiv.org/abs/2509.23717>). Tests whether a feature activates on generated text with the same
  semantic properties as its top examples and reports that many interpretable features do not. Closest
  found work to the consistency-across-phrasings endpoint at the `activation` stage; the search summary
  does not mention register or dialect.
- Li, Srinivas, Bhalla and Lakkaraju 2025, "Interpretability Illusions with Sparse Autoencoders:
  Evaluating Robustness of Concept Representations" (<https://arxiv.org/abs/2505.16004>). Reports that
  crafted input perturbations can change sparse-autoencoder concept labels. Adversarial perturbation, not
  natural register variation.
- "Are Sparse Autoencoders Useful? A Case Study in Sparse Probing" (<https://arxiv.org/abs/2502.16681>).
  Reports that probes built on sparse-autoencoder latents generalize poorly under covariate shift.
- Belrose et al. 2023, "Eliciting Latent Predictions from Transformers with the Tuned Lens"
  (<https://arxiv.org/abs/2303.08112>). Describes the logit lens as brittle and biased toward some
  vocabulary items, and uses causal experiments to argue the tuned lens uses features the model uses.
  Relevant to the `readout` stage and to the vocabulary dependence of exact-token ranks.
- "How Do LLMs Use Their Depth?" (<https://arxiv.org/abs/2510.18871>). Per the search summary, evaluates
  tuned-lens faithfulness in early layers and notes its outputs are dominated by high-frequency tokens.
  Relevant to the tokenization and frequency confound.
- "Do Natural Language Descriptions of Model Activations Convey Privileged Information?"
  (<https://arxiv.org/abs/2509.13316>). Reports that activation verbalizers often reflect the
  verbalizer's own knowledge, not the target model's activations, and that earlier verbalizer benchmarks
  can be solved without the activations. Relevant to the `label` stage and a reason for the
  held-artifact manipulation.
- Sadanandan and Behzadan 2026, "PSF-Med: Measuring and Explaining Paraphrase Sensitivity in Medical
  Vision Language Models" (<https://arxiv.org/abs/2602.21428>). Measures answer flips under
  meaning-preserving paraphrases and uses sparse autoencoders to explain them. It studies the model's
  paraphrase sensitivity, with the instrument as the explaining tool, not the instrument's own
  sensitivity.
- Soumik 2026, "Judging the Judges: A Systematic Evaluation of Bias Mitigation Strategies in
  LLM-as-a-Judge Pipelines" (<https://arxiv.org/abs/2604.23178>). Reports style bias as the largest bias
  among those it tests in controlled pairs. Relevant to the `score` stage when the scorer is a model
  judge. This repository's own check of a behavioural judge is
  `docs/exploratory/judge_register_sensitivity_20261106.md`.
- "ICA Lens: Interpreting Language Models Without Training Another Dictionary"
  (<https://arxiv.org/abs/2606.11722>). Describes independent component analysis as a training-free way
  to find interpretable directions. The search found no evaluation of it across registers.
- An informal post, "J-Lens: a failed replication on GPT-2"
  (<https://www.lesswrong.com/posts/tgn3pD2gLpZvepkWk/j-lens-a-failed-replication-on-gpt-2>). Reports a
  Jacobian lens underperforming the logit lens on GPT-2. Not peer reviewed; relevant only as a reminder
  that lens faithfulness is contested.

Searches that returned nothing relevant to the direct question (does an interpretability instrument read
matched information differently by register or dialect):

- register or dialect sensitivity of interpretability methods and sparse-autoencoder features, with
  African American English and lay language as terms: results were dialect detection in speech and text,
  not interpretability instruments;
- mechanistic interpretability and African American English dialect: no dialect study; one adjacent
  result on sparse-autoencoder latents associated with demographic terms;
- sparse autoencoders, medical concepts, lay or patient language against clinical terminology: medical
  sparse-autoencoder papers, none comparing lay with clinical wording;
- robustness of interpretability tools to non-standard English, informal text or typos: adversarial and
  covariate-shift robustness only;
- independent component analysis of language-model activations with register, dialect or lay language:
  the ICA Lens paper only.

Not done: opening any paper; citation chasing; searching venues or preprint servers directly. A proper
review is needed before any statement about prior work appears outside this file.

## Open decisions

These are the owner's, and nothing here presumes them.

1. Whether to pursue the benchmark at all, and on which model and instruments first.
2. Who establishes and reviews reference facts, and under what clinical-review status.
3. The margins, with their reasons.
4. Whether real bundles are admitted, and through which CI lane.
5. Where real outputs would live and which analysis membership, if any, they may enter
   (`docs/open_results_policy.md`).
