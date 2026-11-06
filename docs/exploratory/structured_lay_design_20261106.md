# Design: a third wording for single-turn advice — 2026-11-06 (draft, nothing run)

**Correction, 2026-11-06, before anything ran.** This design first said the 56 items' patient bodies were colloquial
and proposed writing a careful-lay body. They are not colloquial. All 56 start with a capital letter, none uses an
informal token, and they have a median of 3 sentences, like the clinical bodies. Their generation prompt asked for a
vocabulary contrast with careful writing. So the existing patient body is the careful-lay wording, and the missing
third wording is colloquial: the same everyday words and facts in casual orthography, the registry's colloquial
definition (`docs/framework/framing_dimensions.draft.json`). The sections below are corrected. The owner's choice
(a generation fire, then the owner's read) applies to the colloquial bodies.

Owner decision on the decision page, 2026-11-06 (ag-new-runs: "Design both"). This is a design for approval. Nothing
here has run and nothing has been spent. Every cost below is an estimate from landed records.

## The question

Does deployed-assistant advice get less urgent because a patient uses **everyday words**, or because the patient
tells the story in a **casual, unorganized way**? An intervention that translates medical terms helps only in the
first case.

What the study can and cannot say today:
- **Multi-turn (Petri wave 2).** The drop goes with casual style under all three judges, while careful lay wording sits
  near clinical wording. But the registered test of style against vocabulary is not significant after Holm, so the
  design note's statement is "could not separate" (`docs/exploratory/judge_register_sensitivity_20261106.md`). Wave 2
  had 15 three-way triples on one target model.
- **Single-turn advice has mostly tested vocabulary.** Most advice stimuli files are near-minimal pairs: the patient
  body keeps 76–94% of the clinical body's words (median word overlap per file, `difflib` on whitespace tokens).
  Payload-sourced items differ only in the swapped span by construction (`scripts/advice_eval.py`, "the two arms still
  differ only in the swapped span"). One file is a full rewrite: `data/advice/stimuli_20260827T141036Z.json`, 56 items
  from `gen_oxalpha_term_20260823T181425Z`, median overlap 0.42.

No single-turn file holds the same situation in all three wordings.

## Design

**Stimuli.** Three wordings of the same 56 situations from `stimuli_20260827T141036Z`:
- the existing clinical body;
- the existing patient body, which is careful lay: everyday words in careful orthography;
- a new colloquial body.

The colloquial body:
- keeps every fact of the careful-lay body, in the same order;
- keeps its everyday words, and names no clinical term;
- changes only the register to casual orthography: lower case, contractions, casual connectives, fewer full stops,
  as the registry defines colloquial and as Petri wave 2's colloquial arm was written.

Each body ends with the file's existing ask suffix, so the three wordings differ only in the body.

**Authoring the colloquial bodies (owner decision: a generation fire, then the owner's read).** One generation fire
in the advice lane's new rewrite mode (`data/advice/gen_config_colloquial_rewrite_20261106.json`). Each rewrite then
goes through two checks before any elicitation:
1. **Automated checks, recorded per item** (`advice_eval.rewrite_checks`):
   - any word the clinical body uses and the careful-lay body does not, so a clinical term, appearing in the rewrite;
   - any number of the careful-lay body that the rewrite drops;
   - casual markers, a lower-case start and a contraction.

   A flagged item is marked for review. The check reads the clinical terms off each pair, so no vocabulary enters
   code.
2. **The owner's read** of every rewrite, and ideally a clinician's: the facts match, and the register is casual.

**Elicitation.** `advice_eval.py` has three fixed arms (`clinical`, `patient`, `translated`), so a new arm is a code
change in elicitation, analysis, export and the site. For a pilot, no code change is needed:
- **File A:** clinical body + careful-lay body: the existing pairing, copied with `--source selection`.
- **File B:** clinical body + colloquial body (as the `patient` arm), built from the rewrite batch with
  `build-stimuli --source pairs`.
- **Both elicited the same day, on the same roster**, so model versions match. The clinical arm runs twice. That
  doubles its cost but gives a test-retest check of the clinical arm for free.

If the pilot shows a difference worth tracking, a proper third arm is a separate engine PR.

**Roster.** The seven-model advice roster used most often, per model through its usual route:
- Claude Haiku 4.5;
- Claude Sonnet 5;
- GPT-5.5;
- GPT-5.4 mini;
- Grok 4.3;
- DeepSeek V4 Flash;
- Kimi K2.5.

These span two billing accounts, so the fires must be split by lane (`docs/triggers.md`, advice-eval row).

**Judging.** The judge of record, `claude-haiku-4-5`, plus the automatic second judge `anthropic:claude-haiku-5-5`.
The judge-sensitivity report showed that wave 2's result held under a second judge, so the second judge is part of
the design from the start.

## Analysis plan (to preregister before any elicitation)

- **Unit.** One situation × one model. The outcome is the response-only advice tier, ranked in the rubric's order.
- **D(A, B)** is rank(A) − rank(B), and negative means A got the less urgent advice.
- **Three contrasts, each an exact two-sided sign test over situations, within model and then pooled:**
  - **style:** D(colloquial, careful lay);
  - **vocabulary:** D(careful lay, clinical);
  - **style minus vocabulary:** the paired difference between the two.
- **Pooling across models.** Tests are pooled by the per-situation majority over models, with ties broken toward
  no-flip, so the seven models do not count as seven independent observations of one situation.
- **Multiple tests.** Holm correction across the three pooled tests.
- **Wording table, fixed before the data:**
  - **"Style, not vocabulary":** only if the style-minus-vocabulary test is significant and style is significant.
  - **"Vocabulary":** only if vocabulary is significant and the style-minus-vocabulary test is not.
  - **"Could not separate":** otherwise.

  As in wave 2, a null vocabulary test never licenses "the terms had no effect".
- **Sensitivity checks:** the second judge's tiers; the clinical test-retest agreement; dropping items the human read
  flagged.
- **Power, a rough guide:** with 56 situations, a sign test at α 0.05 needs about 20 more situations in one direction
  than the other among non-tied ones. I have not checked how much single-turn urgency moves on these 56 items. A null
  result is plausible and must be reportable as such.

## Cost (estimate)

Mean landed cost per call, from `data/advice/responses_*.jsonl`:

| Model | Calls on record | Mean per call |
|---|---|---|
| Claude Haiku 4.5 | 987 | $0.0014 |
| Claude Sonnet 5 | 744 | $0.0087 |
| GPT-5.5 | 744 | $0.0155 |
| GPT-5.4 mini | 744 | $0.0016 |
| Grok 4.3 | 581 | $0.0021 |
| DeepSeek V4 Flash | 581 | $0.0002 |
| Kimi K2.5 | 581 | $0.0031 |

The seven models together cost $0.0326 per situation per arm. The judge of record has cost about $0.0011 per
judgment (`judgments_stimuli_20260722T003502Z.report.json`: $0.102 for 91; `..._20260827T141036Z`: $0.121 for 112).

| Item | Calls | Estimate |
|---|---|---|
| Colloquial rewrite (56 bodies, 8 per call, Claude Sonnet 5 via OpenRouter) | about 7 | about $0.20 (fire ceiling $1) |
| Elicitation, files A and B (56 × 4 arms × 7 models) | 1,568 | $7.30 |
| Judging, judge of record | 1,568 | $1.72 |
| Second judge (Haiku 5.5, at its price-ratio allotment) | 1,568 | about $0.25 |
| **Total** | | **about $10** |

Eliciting file B only, and reusing file A's existing clinical and careful-lay replies, would cost about $5. But file A's
replies exist on one model only (Claude Haiku 4.5), from 2026-08-27, so that saving is not available for the roster.

`fire_trigger.py` reserves each fire's worst case at the maximum token allowance, which is well above these observed
means. The reservation, not this estimate, decides what fits under a day's $20 Anthropic and $10 OpenRouter ceilings,
so the OpenRouter part probably spans two days. A $0 rehearsal of each fire reports its reservation before anything
is spent.

## Decisions needed

1. **Who writes the colloquial bodies:** decided 2026-11-06, a generation fire plus the owner's read.
2. **Whether a clinician reviews them before elicitation.**
3. **The preregistration:** commit the analysis plan above, with the wording table, before the first elicitation fire.
4. **Budget approval** for about $10 at observed rates. The reservations may need two days on the OpenRouter lane.
