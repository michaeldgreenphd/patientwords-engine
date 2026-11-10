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
  within-register paraphrase result. The paper does not vary register.
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
a design choice measures what this file says it measures. The rubric, the scorer and the fixture are
unchanged. These are for the owner to decide.

1. **The held-artifact manipulation has no control showing that the scorer reads the description.** This
   file calls the manipulation the strongest test in the benchmark. Chen (arXiv:2610.37676v1) shows that
   a rule that never reads the explanation can outscore the stored LLM scorers on the items a standard
   pipeline builds. A scorer that ignores both descriptions gives them the same score, and
   `scripts/instrument_validity.py` then returns `equivalent_within_margin` for a set with enough
   families. The changed-fact control guards the recovery endpoint against an instrument that responds to
   nothing. Nothing guards the held-artifact endpoint. Question: should the manipulation require a third,
   mismatched description of the same artifact, and give no equivalence verdict unless the mismatched
   description scores lower?
2. **The held-artifact description pairs have no rule for formatting and length.** Soumik
   (arXiv:2604.23178v2) reports that four of five judge models prefer markdown to the same content in
   plain prose, and that three of five prefer an expanded answer to its base answer. This file asks only
   that the two descriptions mean the same thing, and notes that version 1 of the bundle has no field for
   token counts or formatting. Inference: if the everyday description of a fact is longer than the
   medical one, which has not been measured here, a length effect would be reported as a
   medical-minus-everyday difference. Question: should the pairs be matched on formatting and bounded in
   length ratio, or should both be recorded per description and reported with the difference?
3. **The `label` stage has no input-only arm for a verbalizer.** Li et al. (arXiv:2509.13316v4) report
   that a verbalizer model given only the input text is competitive with verbalization methods given the
   target model's activations, and that the input can be reconstructed from those activations. The
   benchmark's reference facts are facts stated in the input. Inference: a verbalizer can earn recovery
   credit by restating the input, and a register difference in its recovery can come from how the
   verbalizer model reads the two wordings. That is still a property of the instrument. But this file
   separates a difference in the representation from a difference in the labeler, and for a verbalizer
   that separation needs an arm in which the verbalizer sees the input text and no activation. Question:
   should the `label` stage require that arm when the instrument is a verbalizer?
4. **The "representation changed" fact does not use within-register variation.** The four-cell report
   calls a family's representation changed when the medical-minus-everyday difference in
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
3. The margins, with their reasons.
4. Whether real bundles are admitted, and through which CI lane.
5. Where real outputs would live and which analysis membership, if any, they may enter
   (`docs/open_results_policy.md`).
