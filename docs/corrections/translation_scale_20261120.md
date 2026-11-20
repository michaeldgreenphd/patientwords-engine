# Correction record: `translation_scale.py` compared the wrong pair of sentences

Dated 2026-11-20. Nothing in this record was published. No model was called and no
measurement was made. The candidate numbers come from one run of the corrected script
into a scratch file, from the landed summaries, at engine `5050080a` plus this change;
the published file is the site's `data/translation_scale.json` on `main` at `8e5b661`
(generated 2026-08-29, producer revision `6884692f0a15+dirty`). No stimulus text appears here.

## 1. The defect

`scripts/translate_corpus.py` writes each txcorpus row with the source pair's clinical
sentence as `top_prompt` and the rewrite of its patient sentence as `bottom_prompt`. The
patient sentence is not a prompt of the row. From the 2026-07-19 rewrite on,
`scripts/translation_scale.py` read the clinical side of a txcorpus run as the rewrite
and its patient side as the patient sentence. Its "recovery" was therefore

    p(target | clinical sentence) - p(target | rewrite)

which is how far the rewrite falls short of the clinical sentence. The translation page
describes the column as what the clinical answer gains under the translated sentence
versus the patient one. The published per-model figures do not measure that.

Checked on the three committed corpora (1,031, 352 and 352 rows): `top_prompt` equals
the source pair's clinical sentence in every row, and `bottom_prompt` equals the source
pair's patient sentence in 26, 9 and 9 rows.

A second defect is in the lens count. The two priority corpora hold the same 352 source
pairs, and each has its own lens pull. A pair read in both was counted twice.

## 2. The correction

    recovery = p(target | rewrite) - p(target | patient sentence)

The rewrite's probability is the txcorpus run's patient side. The patient sentence's
probability is the patient side of the source pair's own run, joined on
`generation.source_batch` and `generation.source_index`, the same model and the same
backend. A pair is counted only when both runs recorded the sentences the corpus names
and the same target. Every measured pair that is not counted is listed under `coverage`
with its reason. A pair in more than one corpus is counted once per model, and once in
the lens count. The join reads source runs, so each row is asked of
`tierb_split.sealed_pair`; no committed corpus row is sealed today.

## 3. Published and candidate values

| Model (backend) | Published: n, mean, median, share positive, top restored / lost | Candidate: n, mean, median, share positive, top restored / lost |
|---|---|---|
| gemma-2-2b (hosted) | 37, +0.0360, +0.0330, 62%, 10 / 6 | 31, +0.1189, +0.0800, 81%, 14 / 0 |
| gemma-3-4b-it (logits) | 350, +0.0312, +0.0002, 53%, 30 / 24 | 154, +0.0054, 0.0000, 49%, 15 / 14 |
| qwen3-1.7b (logits) | 350, +0.0315, +0.0001, 50%, 40 / 18 | 290, +0.0267, +0.0002, 51%, 24 / 11 |

Mean wording gap on the counted pairs (`mean_gap`, clinical minus patient sentence in the
source run): 0.1644, 0.0294 and 0.0601.

Pairs not counted in the candidate: gemma-2-2b 17 of 48 (rewrite probability not
recorded 11, patient probability not recorded 5, target differs between the runs 1);
gemma-3-4b-it 196 of 350 and qwen3-1.7b 60 of 350, all because the source part is
landed but outside the pinned logits manifest of the analysis membership. Those counts
rise when a later manifest pins the parts.

Lens count: published 377 paired, 159 never formed under patient wording, 43 recovered,
195 formed under both, 23 lost. Candidate: 352 paired, 162, 43, 178, 12. The second
lens pull agrees with the first on formed or not formed for all 352 pairs. The
published 377 could not be reproduced from the current tree.

## 4. Limits of the candidate values

- The gemma-2-2b rows are the hosted run of one priority corpus. Their mean wording gap
  is 16.4 points; the model's mean gap over its 1,364 published phrases is 3.2 points
  (the site's `data/model_stats.json`). These 31 pairs are not a sample of the corpus.
- For gemma-3-4b-it the txcorpus run and the source runs disagree on the identical
  clinical sentence: up to 4.8 points, more than 1 point in 17 of 154 pairs, mean signed
  difference +0.04 points. The mean recovery (+0.5 points) is of the same size as that
  run-to-run difference per pair, so the per-pair columns (share positive, top restored,
  top lost) for this model carry that noise. Both runs record dtype bfloat16 and the
  same model revision; the older source parts record no environment, so the cause was
  not identified. qwen3-1.7b agrees exactly on all 290 pairs.
- The rewording control applies here as elsewhere: a neutral rewording moves the target
  probability by 6.6 points on average (`paraphrase_robustness_floor_v2`).

## 5. What is not changed, and the owner's decisions

Not changed by the correcting commit: any site file, any landed summary, any trigger.
The published file keeps its values until it is regenerated.

1. Regenerate `data/translation_scale.json` (`python scripts/translation_scale.py --site
   ../patientwords`). It is a published statistic, so it goes out with a superseding
   snapshot (publish chain step 9c).
2. The translation page's wording. The table and the per-model sentences are built from
   the file and stay accurate in form (checked by rendering the page with the candidate
   file). Four pieces of fixed wording need a decision once the numbers change:
   "the same rewrite produces a small average lift" (gemma-2-2b would read +11.9 points);
   "At scale (n cases) translation lifts the clinical answer's probability by a mean of
   ..." (it would be read from 31 selected hosted pairs); "applied to every measured
   phrase (n so far)" (it would name the counted pairs of one model); and the caption
   "measured by CPU next-word inference" (the gemma-2-2b row is the hosted run, which was
   already so in the published file; `per_model[m].backends` now records it).
3. `mean_gap_closed` stays null. A txcorpus run does carry the clinical baseline, so the
   statistic can be defined; its form is a research decision.
4. Whether gemma-3-4b-it should be compared within runs (the rewrite's shortfall against
   the clinical sentence in the txcorpus run, set against the wording gap in the source
   run) so that a difference between runs cancels. That changes the definition of
   recovery and is not done here.
