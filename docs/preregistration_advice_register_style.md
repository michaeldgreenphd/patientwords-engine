# Pre-registration — single-turn advice, writing style against medical terms (DRAFT, UNSIGNED)

**Status.** Drafted 2026-11-06 from the owner's decisions on the decision page (ag-new-runs "Design both";
structured-lay-go "Generation fire, then your read"). Unsigned.
- **Blocks:** this file must be signed by the study owner, and committed, before the first elicitation fire on the
  stimuli it governs.
- **Does not block:** the generation fire that writes the colloquial bodies, which only produces stimuli for the
  owner's review.
- **Design source:** `docs/exploratory/structured_lay_design_20261106.md`.
- **Style:** follows `docs/preregistration_advice.md`.

## What is being measured

Whether deployed assistants recommend a different level of care for the same situation when a patient writes:
- with clinical terms;
- with everyday words in careful writing (careful lay);
- with the same everyday words in casual writing (colloquial).

It is measured, never dispensed. It separates two causes of a lower-urgency reply that the study's earlier designs
confound: missing medical terms, and casual style. Petri wave 2 pointed at style, but its registered decomposition could
not separate the two (`docs/exploratory/judge_register_sensitivity_20261106.md`).

## Stimuli

- **Situations.** The 56 items of `data/advice/stimuli_20260827T141036Z.json`: one first-person situation each, with
  a clinical body and a careful-lay body that differ in vocabulary.
- **The third wording.** A colloquial body per item, written by one generation fire
  (`data/advice/gen_config_colloquial_rewrite_20261106.json`). It keeps the careful-lay body's words, facts and order,
  and changes only the orthography and formality, as the registry defines colloquial
  (`docs/framework/framing_dimensions.draft.json`).
- **Review before elicitation.** The owner reads every rewrite. An item is excluded, before any elicitation, if any
  of these holds:
  - its rewrite adds, drops or changes a fact;
  - it uses a clinical term;
  - it does not read as casual.

  Exclusions are recorded by item id with the reason. A flag from `rewrite_checks` (a leaked clinical term, a
  dropped number) must be resolved in that review, by exclusion or by a recorded owner judgment that the flag is a
  false alarm.
- **The ask.** Each body is sent with the file's ask suffix, identical across the three wordings.

## Procedure

- **File A:** clinical and careful-lay bodies, copied from the source file with `build-stimuli --source selection`.
- **File B:** clinical and colloquial bodies, built from the reviewed rewrite batch with `build-stimuli --source
  pairs`.
- **Same day, same roster.** Both files are elicited on the same UTC day, on the same seven-model roster, at the
  roster's registered settings, K = 1 sample per stimulus × arm × model:
  - Claude Haiku 4.5;
  - Claude Sonnet 5;
  - GPT-5.5;
  - GPT-5.4 mini;
  - Grok 4.3;
  - DeepSeek V4 Flash;
  - Kimi K2.5.

  Fires are split by billing lane as `docs/triggers.md` requires. A model whose fire does not complete on that day is
  reported as missing, never filled from another day.
- **Judging.** Response-only tiers under the advice rubric, by the judge of record `claude-haiku-4-5`. The automatic
  second judge `anthropic:claude-haiku-5-5` grades the same replies and is used only in the sensitivity analysis.

## Outcome and contrasts

- **Outcome:** the response-only advice tier, ranked in the rubric's order (self-care < routine < urgent <
  emergency).
- **Unit:** one situation × one model. For two wordings A and B, D(A, B) = rank(A) − rank(B), so negative means A got
  the less urgent advice. The clinical arm is elicited in both files: D uses each file's own clinical reply against
  its own other arm, and the two clinical replies are compared only as a test-retest check.
- **The three registered contrasts:**
  1. **Style:** D(colloquial, careful lay), estimated as D(colloquial, clinical)_B − D(careful lay, clinical)_A, per
     situation and model;
  2. **Vocabulary:** D(careful lay, clinical), from file A;
  3. **Style minus vocabulary:** the paired difference of 1 and 2.
- **Tests.**
  - **Within each model:** an exact two-sided sign test over situations, dropping ties and counting them.
  - **Pooled:** each situation's label is its majority sign across the models that measured it, with ties broken
    toward zero. Then an exact two-sided sign test over situations, so seven models never count as seven
    observations of one situation.
  - **Multiple tests:** Holm across the three pooled tests, α = 0.05.

## What each outcome permits (fixed before the data)

| Result (pooled, after Holm) | Statement allowed |
|---|---|
| Style significant **and** style minus vocabulary significant, both negative | "In single-turn advice, casual writing style lowered recommended urgency more than replacing medical terms with everyday words did." |
| Vocabulary significant, negative, **and** style minus vocabulary not significant | "Replacing medical terms with everyday words lowered recommended urgency; this design could not show an added effect of casual style." |
| Neither style nor vocabulary significant | "No difference in recommended urgency was detected between these wordings." This is never "the wording has no effect". |
| Any other pattern, or a significant result in the positive direction | "Could not separate style from vocabulary"; the pattern is reported in full. |

A null vocabulary test never licenses "medical terms had no effect", as in wave 2's design note.

## Sensitivity analyses (reported beside the registered result, never replacing it)

1. The three contrasts under the second judge's tiers.
2. Each model alone (the within-model tests above).
3. Clinical test-retest: agreement between file A's and file B's clinical replies (exact share, weighted κ). This
   bounds how much of any arm difference is resampling noise.
4. Situations flagged in review but kept by owner judgment: the result without them.

## Data handling

- **Archives.** The advice archives under `data/advice/` are append-only and hash-chained, as for the advice arm.
- **Holdout.** No Tier B holdout text enters the stimuli; the rewrite mode drops any collision and counts it.
- **Exploratory.** This sub-study is exploratory relative to the advice arm's registered endpoints and is labelled so
  wherever it appears.
- **Deviations.** Any departure from this file is recorded in `docs/prereg_divergence_log.md` before the analysis it
  affects.
