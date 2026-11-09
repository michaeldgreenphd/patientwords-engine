# Comma test on 18 hand-authored pairs: analysis plan (exploratory)

Written 2026-11-09, before any trace of `data/simulated/agscen_commas_20261109.json` exists. The owner asked whether
commas matter after excluding 18 scale-round pairs for "perfect comma grammar" alongside misspellings ("I feel like
people are more likely to not have commas at all in terms of how they type").

## Stimuli

`data/simulated/agscen_commas_20261109.json`: the 18 owner-excluded scale-round pairs
(`drafts/antigravity_scenarios_20261107/scale_20261108/candidates_v2.json` at `765459e3`), each twice.

- `<id>-comma`: as written. Every pair has 3 commas on each side.
- `<id>-nocomma`: every comma deleted, nothing else changed. The builder asserts the same words in the same order.

The round-5 rewrites (`data/simulated/agscen_r5_20261108.json`, `<id>-r5`, already traced) removed the commas and
also replaced one of them with "and" or "with"; sc-029-r5 also changed "eighty-one" to "81" and "outward-turned leg"
to "leg turned out". So `-comma` against `-r5` mixes punctuation and wording, which is why this file exists.

## Measures

Seven models, as for the earlier agscen rounds: hosted gemma-2-2b (2panel traces) and six logits models
(gemma-3-4b-it, qwen3-1.7b, qwen3-4b, llama-3.2-3b, olmo-2-1b, gemma-2-2b-it). Per pair and model:

- `penalty`: the engine's `language_penalty`, the clinical target's probability on the everyday side minus on the
  clinical side;
- `p_clinical`: the clinical target's probability on the clinical side;
- `class`: downgrade, upgrade, lateral or uninformative, by the tier rules in the agscen measured files
  (`data/urgency_tiers.draft.json`).

A model's row counts only when both variants of the pair have a numeric value for that measure.

## Contrasts

1. **Commas (primary).** For each pair, the mean over models of penalty(comma) − penalty(nocomma). Two-sided exact
   sign test over the 18 pairs; ties (a mean of exactly 0) are dropped and counted.
2. **Commas on the clinical baseline.** The same for p_clinical(comma) − p_clinical(nocomma).
3. **Commas on the class.** Pairs and model rows that downgrade, comma against nocomma. Descriptive only.
4. **Connective wording (secondary).** Contrasts 1 and 3 for `-nocomma` against `-r5`. sc-029 is reported, then
   left out of contrast 4, because its rewrite changed more than one connective.

No correction across contrasts; nothing here is confirmatory. The wording for a null result is "no difference was
detected on these 18 pairs", not "commas have no effect". One sample per pair and model; small models only.

## Reproduce

The comparison script is written after the traces land and committed with the results; it reads only
`trace_out/agscen_commas_20261109*/` and `trace_out/agscen_r5_20261108*/`. These parts are exploratory and
publication_hold refuses them by stem.
