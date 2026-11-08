# Pre-registration — single-turn advice, writing style against medical terms (DRAFT, UNSIGNED)

**Status.** Drafted 2026-11-06 from the owner's decisions on the decision page (ag-new-runs "Design both";
structured-lay-go "Generation fire, then your read"). Revised 2026-11-07, before signing, from two more decisions:
colloquial-strength "Accept as casual orthography" and colloquial-drops "Fix the guard, then regenerate the 3".
Unsigned.
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
- with the same everyday words in casual orthography (colloquial): lower case, apostrophes dropped, casual
  connectives.

It is measured, never dispensed. It separates two causes of a lower-urgency reply that the study's earlier designs
confound: missing medical terms, and casual style. Petri wave 2 pointed at style, but its registered decomposition could
not separate the two (`docs/exploratory/judge_register_sensitivity_20261106.md`).

**Scope: casual orthography, not casual word choice.** The colloquial bodies keep the careful-lay body's words,
facts and order. The 2026-11-06 generation did exactly that: every rewrite lower-cases the text and drops the
apostrophes. 31 of 53 change no word: the same letters and digits in the same order. Of the other 22, 12 only add
a casual connective ("ok so", "so", "idk") and 10 swap a word ("tho", "cause", "this" for "a"). Petri wave 2's colloquial arm also changed non-medical words and formality ("approximately two months"
against "about 2 months"). So "style" here means orthography only. A null result here does not count against wave 2's
pattern, and no result here licenses a statement about casual word choice or unorganized storytelling.

## Stimuli

- **Situations.** The 56 items of `data/advice/stimuli_20260827T141036Z.json`: one first-person situation each, with
  a clinical body and a careful-lay body that differ in vocabulary.
- **The third wording.** A colloquial body per item, written by one generation fire
  (`data/advice/gen_config_colloquial_rewrite_20261106.json`, 53 items). It keeps the careful-lay body's words,
  facts and order, and changes only the orthography, as the registry defines colloquial
  (`docs/framework/framing_dimensions.draft.json`).
- **The second set, which replaces the first (owner decision colloquial-realism, 2026-11-07).** In the owner's read the
  first set did not look like real typing: 14 of 56 opened with "ok so", and the rewrites kept the careful-lay
  punctuation (a median of 3 commas and 3 sentences). A second generation
  (`data/advice/gen_config_colloquial_rewrite_v2_20261107.json`, same model, system prompt and source) asks for phone
  typing: lower case, at most one comma and one full stop inside a message, no stock opener, and every word kept.
  `style_checks` records each rule per item, and the owner reads the second set as the first. File B is built from
  the second set; the first set stays in the archive and is not elicited.
- **The casual-typing pass on the second set (owner feedback, 2026-11-08).** The owner read the second set (53
  accepted, 3 excluded, all three for hyphenated ages or dashes) and noted that people type numbers as digits.
  `scripts/casual_orthography.py` applies fixed rules to the second set: number words from two to ninety-nine become
  digits; hyphenated ages lose their hyphens; punctuation dashes become spaces. "one", "half" and "a couple" stay as
  words. The output, `rewrite_colloquial_v3_*`, records each text before the pass, and file B is built from it.
- **The three regenerated items (first set).** That run's holdout guard was the bare Tier B hash, which marks about 1 in 10 texts
  of any content, and it dropped three rewrites (items 14, 37 and 41), none of them a registered holdout phrase.
  After the guard was corrected, these three are written by one more fire under the same model, system prompt and
  template (`data/advice/gen_config_colloquial_rewrite_regen_20261107.json`). They were written in a call of their
  own, not alongside the other 53, and on a later day; both are recorded, and they go through the same review.
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
- **File B:** clinical and colloquial bodies, built from the two reviewed rewrite batches with `build-stimuli
  --source pairs`.
- **Matching situations across files.** `build-stimuli --source pairs` names each file-B item `<rewrite batch>#<index>`
  and does not carry the source item id. The analysis therefore joins file A and file B on the clinical body. It is
  distinct for all 56 situations and copied unchanged into every rewrite pair (`top_prompt`). Each rewrite also
  records its source id (`generation.source_ref.id`) as a cross-check. A situation that does not join one-to-one is
  reported and left out.
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
  1. **Style (casual orthography):** D(colloquial, careful lay), estimated as D(colloquial, clinical)_B − D(careful lay, clinical)_A, per
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
| Style significant **and** style minus vocabulary significant, both negative | "In single-turn advice, casual orthography (lower case, dropped apostrophes, casual connectives) lowered recommended urgency more than replacing medical terms with everyday words did." |
| Vocabulary significant, negative, **and** style minus vocabulary not significant | "Replacing medical terms with everyday words lowered recommended urgency; this design could not show an added effect of casual orthography." |
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
