# Research protocol template

Copy this file to `docs/protocols/<short_name>_<YYYYMMDD>.md` and fill every field before any data that
the protocol governs is collected or opened. A field that does not apply is filled with "not applicable"
and one sentence saying why. A field that is unknown is filled with "unknown" and what would settle it.
No field is left blank and no number is invented to fill one.

This is a template. It contains no results, no targets and no example values. The signed
preregistrations in this repository (`docs/preregistration_tierB.md`,
`docs/preregistration_advice_register_style.md`) show the house style for the finished document:
answers first, exact file paths, statements fixed before the data.

The protocol does not change any rule in `AGENTS.md`, `verify.md` or `docs/agent_reference.md`. Where
this template and those files disagree, those files govern and the template is wrong.

## 0. Identity and status

| Field | Fill in |
|---|---|
| Title | |
| Protocol file | `docs/protocols/<short_name>_<YYYYMMDD>.md` |
| Status | draft, signed, or amended (with the date of each change) |
| Author | |
| Signed by, and how the signature is recorded | |
| Blocks | which fires, analyses or publications may not start until this file is signed and committed |
| Does not block | what may proceed without it |
| Design sources | paths of the design notes this protocol rests on |

## 1. Research question and claim type

State the question in one sentence. Then mark exactly which of the four claims below the study addresses.
The four are separate. Evidence for one is not evidence for another, and a study may address only one.

| Claim | What it needs | Addressed here (yes or no) |
|---|---|---|
| 1. Wording sensitivity | The model's measured output differs between wordings of the same clinical information. | |
| 2. Clinical relevance | A clinically meaningful outcome, assessed independently of the model and of the study team's expectation. | |
| 3. Mechanism | A controlled intervention in one accessible model, on a behavioural endpoint fixed in advance. | |
| 4. Equity relevance | Sampling and validation appropriate to the population the claim names. | |

| Field | Fill in |
|---|---|
| Question | |
| Hypothesis, with its direction | |
| Null hypothesis | |
| Models and their pinned revisions | |

## 2. What this study cannot establish

Write these out for this study. Each of the following holds unless the design removes it, and the
protocol says which design element removes it.

- No human-comparator claim without a human comparison in the design. A model result alone says nothing
  about how clinicians or patients would respond to the same wording.
- A dialect or register label describes a wording condition. It does not establish a person's race,
  education, literacy or socioeconomic status, and no such inference is drawn from it.
- Clinical wording is not the answer key. A response is not better because it uses, or follows,
  technical terms.
- A medically named feature, component or lens token does not show that the model understands the
  concept. A name is a label attached by a tool.
- A change in a token probability is not a change in the clinical quality of a complete response.
- One pair's penalty or flip label supports no claim
  (`docs/agent_reference.md`, *Known measurement limitations*).

| Field | Fill in |
|---|---|
| Statements this study will not make, whatever the result | |
| Known measurement limitations that apply (read the section named above and list them) | |

## 3. Population and independent unit

| Field | Fill in |
|---|---|
| Case families: what one family is, and how many are planned | |
| Source of the families and the selection rule | |
| Selection is independent of model outcome (yes or no, and how this is ensured) | |
| Independent unit for every analysis | the case family, or the conversation; never the token, layer, component or turn |
| Stable identifiers used for joins | for study batches, `(batch, batch_index, model)`; never the display `index` |

## 4. Clinical facts held equal

List the facts every wording of a family must carry. Equivalence is reviewed, not assumed.

| Field | Fill in |
|---|---|
| Reference facts per family, and who established them | |
| Reviewer, and whether the reviewer saw any model output | |
| Checked for each rewrite: uncertainty | |
| Checked for each rewrite: negation | |
| Checked for each rewrite: chronology | |
| Checked for each rewrite: severity | |
| Checked for each rewrite: available facts (nothing added, nothing dropped) | |
| Review status recorded per family, and where | |
| What happens to a family that fails review | |

A rewrite that inserts a diagnosis is an information intervention. It gives the model a fact the other
wording did not carry. It is recorded as an information intervention and analysed apart from wording
contrasts. It is not relabelled as a register change.

## 5. Manipulated linguistic dimensions

Each dimension is a separate manipulation. Mark which ones vary and which are held fixed. A contrast that
varies two at once is reported as a joint contrast and is not attributed to either.

| Dimension | Varied or fixed | How it is operationalised, and the file that defines it |
|---|---|---|
| Terminology | | |
| Syntax | | |
| Spelling | | |
| Ambiguity | | |
| Discourse structure | | |
| Asserted expertise | | |
| Access barrier or context | | |

For a lexical estimate, speaker identity and task instructions are fixed across wordings. State the
fixed speaker framing and the exact instruction text or its path.

| Field | Fill in |
|---|---|
| Speaker identity (fixed value) | |
| Task instructions (fixed text or path) | |
| Intentional misspellings are preserved in the stimuli (yes or no) | |

## 6. Provenance classes

The three classes are kept in separate files, separate analyses and separate statements. A result from
one is never reported under another's name.

| Class | Used (yes or no) | Source, licence or redistribution limit, and review status |
|---|---|---|
| Synthetic patient-style language | | |
| Authentic patient language | | |
| Clinically validated pairs | | |

## 7. Controls

| Control | Included (yes or no) | Definition and the comparison it supports |
|---|---|---|
| Within-register paraphrase | | |
| Length and context | | |
| Clinically non-equivalent wording (one fact genuinely changed) | | |
| Tokenization (target and prompt token counts, first-token identity) | | |
| Both effect directions (the design can detect an effect either way) | | |

State what size of effect in the within-register paraphrase control would make the main contrast
uninterpretable, and where that size comes from.

## 8. Endpoints

Endpoints are separate. A result on one is not restated as a result on another.

| Endpoint | Used (yes or no) | Exact definition, script and output field |
|---|---|---|
| Next-token lexical proxy | | |
| Sequence log-likelihood | | |
| Concept extraction | | |
| Complete-response clinical quality | | |
| Conversation-level actions | | |

The legacy first-token endpoint is labelled as legacy wherever it appears. It reads the first encoded
token of the target and is not a whole-answer score.

| Field | Fill in |
|---|---|
| Primary endpoint (one) | |
| Multi-token targets: scoring rule fixed in advance | |
| Synonyms: the accepted set and who fixed it, in a JSON data file | |
| Exact-token read is recorded (`target_read`) and substituted reads are excluded or labelled | |
| Precision and backend, and the known error they add | |

## 9. Conversations

Fill this section only for multi-turn work.

| Field | Fill in |
|---|---|
| Controlled matched-turn condition: definition | |
| Adaptive condition: definition | |
| Information available to the model at each turn, per condition | |
| Truncation rule | |
| Stop reasons recorded | |
| Incomplete trajectories: how they are counted and reported | |
| Branch dependence: how a later turn's dependence on an earlier reply is handled | |
| Independent unit | the case family or the conversation |

The controlled condition and the adaptive condition answer different questions and are reported apart.
An earlier response is never graded using a warning sign that was disclosed in a later turn. The grader
of turn *t* sees only what the model had seen at turn *t*.

## 10. Causal experiments

Fill this section only for interventions. One accessible model, one behavioural endpoint fixed in
advance.

| Field | Fill in |
|---|---|
| Donor and recipient, and the direction of each patch | |
| Token or span alignment rule | |
| Layers and positions, fixed in advance | |
| Coordinates: native (residual, neuron) or lens coordinates | |
| Candidate-selection split | discovery only |
| Edit magnitude: how it is measured and reported | |
| Outcome | |

| Control | Included (yes or no) | Definition |
|---|---|---|
| Identity or self-patch | | |
| Matched random directions (count, seed) | | |
| Unrelated directions | | |
| Same-register patch | | |
| Ablation | | |
| Collateral-task checks | | |

Raw effects are primary. Normalized recovery is a secondary quantity. It is undefined when the baseline
gap is zero, negative or below the threshold fixed here, and it is reported as undefined in those cases.
It is not clamped and not filled.

| Field | Fill in |
|---|---|
| Baseline-gap threshold below which recovery is undefined, and its source | |
| Evidence that the intervention path reproduces the unpatched baseline | |

## 11. Splits and sealed sets

Families are split before anything is developed on them.

| Field | Fill in |
|---|---|
| Split unit | case family and phrase family |
| Splits and their sizes | discovery, validation, fresh test |
| Split is made before paraphrase generation (yes or no) | |
| Split is made before component selection (yes or no) | |
| Split is made before calibration or threshold tuning (yes or no) | |
| Where the split assignment is recorded, with its seed | |
| Sealed sets used, and the seal check that guards them | for the Tier B holdout, `scripts/tierb_split.py` and `scripts/seal_check.py` |
| Who may open a sealed set, and what records the opening | |

No sealed text is copied into a document, a brief, a fixture or a session's output.

## 12. Primary contrasts and multiplicity

| Field | Fill in |
|---|---|
| Primary contrasts, each with its direction | |
| Test for each | |
| Family of tests for the multiplicity correction | |
| Correction method and level | |

The correction family covers every model, layer, component, endpoint and subgroup that the study looks
at. Anything outside the declared family is labelled exploratory where it appears.

| Dimension | Count examined | Inside the correction family (yes or no) |
|---|---|---|
| Models | | |
| Layers | | |
| Components | | |
| Endpoints | | |
| Subgroups | | |

## 13. Uncertainty and denominators

| Field | Fill in |
|---|---|
| Pairing | which observations are paired, and on what key |
| Clustering | by case family (and by batch or topic where stimuli share a source) |
| Interval method, resample count and confidence level | |
| Random seed, recorded in every statistical output | |
| Inclusion denominators | exact counts attempted, completed, failed and excluded, per model and per contrast |
| Missing data | recorded as missing; never set to zero and never dropped without a count |

If the study argues that two conditions do not differ, it fixes a practical equivalence margin here,
before the data. A difference that is not significant is not evidence of equivalence.

## 14. Sample size

| Field | Fill in |
|---|---|
| Pilot data used, and its path | |
| Variance estimate taken from the pilot, and the unit it is per | |
| Smallest effect of interest, and who set it and why | |
| Planned number of families | |
| Sensitivity analysis: the effect detectable at the planned size, across a stated range of variance | |

The planned size comes from pilot variance and the sensitivity analysis. If no pilot exists, the study is
labelled a feasibility study and states no power. A target is never invented.

## 15. Judging

Fill this section when any endpoint is graded by a model or a person.

| Field | Fill in |
|---|---|
| Judge identities and pinned versions | |
| Rubric path and version | |
| Blinding to method | |
| Blinding to condition | |
| Calibration against independent human assessments: sample, raters, result path | |
| Disagreement: how it is recorded, and whether an adjudicated value exists | |
| Reliability statistic and the level fixed in advance | |
| Check that the judge itself does not respond to register | |

The last row is a measurement in its own right. A judge that rates the same content lower in one
register adds its own effect to the outcome. State the check, the data it uses and what size of judge
effect would change the reading of the main result.

## 16. Exclusions

| Field | Fill in |
|---|---|
| Exclusion rules, each fixed in advance | |
| Who applies them, and whether that person sees outcomes | |
| Where each exclusion is recorded, by identifier, with its reason | |
| Rules that are forbidden | exclusion on model outcome; an upstream correctness filter that removes study failures |

## 17. What would weaken the hypothesis

State the results that would count against the hypothesis, in terms of the primary endpoint and its
interval. State what each possible outcome permits the study to say, before the data.

| Result | Statement allowed |
|---|---|
| | |

Null, negative and discordant results are reported with the same prominence as positive ones. Cases are
not replaced because another case looks clearer.

## 18. Evidence class, clinical review and analysis membership

Sharing a result and letting it join a statistic are separate decisions under the open-results policy
(`docs/open_results_policy.md`, `scripts/results_policy.py`). A result is shared when its artifact is
intact and no named restriction applies. It joins an analysis only through a declared membership.

| Field | Fill in |
|---|---|
| Evidence class of the outputs | the class `scripts/results_policy.py` reports, as declared in `data/results_policy/policy.v1.json` |
| Clinical-review status of the stimuli | pending stays visible as pending |
| Visibility, and any named restriction | |
| Analysis membership | the named membership rule each output may enter, or "none" |
| A new membership or snapshot is needed (yes or no) | |
| Labels the outputs carry wherever they appear | synthetic, pilot, exploratory, draft or domain review pending |

## 19. Execution route

Nothing paid or networked runs locally, and no locally produced value is a measurement.

| Field | Fill in |
|---|---|
| CI lane | an existing lane in `docs/triggers.md`; a new lane needs its own reviewed pull request first |
| Admission | through `scripts/fire_trigger.py` only; trigger files are never edited by hand |
| Budget ceiling and billing lane | |
| Queue | one running and one pending |
| Where outputs land, and which collectors read them | |
| Approval | who approves each fire, and where the approval is recorded |
| Offline checks run before any fire | |

## 20. Deviations log

Any departure from this file is recorded before the analysis it affects, here and in
`docs/prereg_divergence_log.md`.

| Date (UTC) | Section | What changed | Why | Before or after data | Recorded by |
|---|---|---|---|---|---|
| | | | | | |
