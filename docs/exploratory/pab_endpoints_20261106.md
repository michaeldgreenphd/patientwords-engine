# PatientAgentBench utterances: the preregistered endpoints — 2026-11-06 (exploratory)

Owner decision on the decision page, 2026-11-06 (pab-step1: "Yes, write the report"). Step 1 of
`docs/exploratory/pab_followup_design_20261106.md`.

The endpoints come from `docs/pab_frame_spec_20260805.md`, fixed before any frame was built. They are tested on the
52 entries of `data/pab/pabharvest_20260807T025446Z.json`: 13 low/high health-literacy pairs × 4 carrier frames, traced
and lens-read on gemma-2-2b on 2026-08-07. The harvested utterances are CC-BY-NC-4.0-derived. This report and the
script carry counts and pair hashes only. Reproduce with:

```
python scripts/pab_endpoints.py --out /tmp/pab_endpoints.json
```

## Answers first

1. **Neither preregistered endpoint is supported.**
   - **Endpoint 1 (language penalty).** 8 of 13 pairs lose probability on the clinical target under the low-literacy
     wording and 5 gain it (exact two-sided sign test p = 0.58).
   - **Endpoint 2 (formation depth, the spec's first rank-1 layer).** The low-literacy side reaches rank 1 later in 6
     pairs and earlier in 3 (p = 0.51). That is the preregistered direction, but not significant. Under the census's
     own formation rule, a secondary reading, it is 3 later and 5 earlier (p = 0.73).
2. **The typical PAB pair looks like the typical study pair.**
   - The median pair penalty is −0.019; for the study's own observational pairs on the same model it is −0.012.
   - 62% of PAB pairs are negative, against 61% of study phrases.
   - The PAB mean is +0.078, because three pairs gain a lot of probability (+0.18, +0.52, +0.61).
   - With 13 pairs, this cannot show either that the effect transfers to externally written phrasing or that it does
     not.
3. **A license guard was missing, and is added here.**
   - The lens census counts these 52 entries and stores each row's prompts for exemplar sentences.
   - Without the site's render map, today's census code picks two PAB rows as its hijack and capture exemplars, which
     would print the harvested sentences on the site.
   - The published census avoided this only because rendered study pairs win the preference ordering when the publish
     step passes `--site`.
   - `scripts/jlens_insights.py` now keeps PAB rows in the counts but strips their prompt text and never picks one as
     an exemplar. With `--site`, the regenerated census is identical to the published one: same 2,155 pairs, same
     exemplars.
   - No harvested text is on the site today: none of the 26 span texts appears in the published census or urgency
     files.

## Endpoint 1: language penalty

The penalty is p(target | low-literacy wording) − p(target | high-literacy wording), in the same carrier frame;
negative is the preregistered direction. The pair is the unit: each pair's value is the mean over its entries that
have a penalty.

| | Value |
|---|---|
| Pairs with at least one penalty | 13 of 13 (2 or 3 entries each) |
| Entries with a penalty | 32 of 52 |
| Pairs negative / positive | 8 / 5 |
| Exact two-sided sign test | p = 0.58 |
| Median pair penalty | −0.019 |
| Mean pair penalty | +0.078 |
| Study pairs, gemma-2-2b, one mean per phrase (1,364 phrases) | median −0.012, quartiles [−0.089, +0.024], 61% negative |

Every one of the 32 penalties was read on exactly the entry's anchor token. These traces predate the 2026-10-07
exact-read change, and the target-read audit found no PAB row reading another token.

**The 20 entries without a penalty.** They are counted here, never treated as zero.

| Frame | Penalty | Screened out at 0.02 | Passed screening, no low-literacy value |
|---|---|---|---|
| `see_a` | 13 | 0 | 0 |
| `talk_to_a` | 13 | 0 | 0 |
| `go_to_the` | 6 | 6 | 1 |
| `take_a` | 0 | 13 | 0 |

- **Screened out.** At the preregistered threshold the target was below 0.02 on the high-literacy side, so the
  low-literacy side was never traced. The `take_a` frame's anchor screened out on every pair.
- **Passed, no value.** Entry 17 passed screening (p = 0.025 on the high-literacy side) but recorded no low-literacy
  probability.

## Endpoint 2: formation depth

**Correction (Codex review of PR #146).** The first version of this report used the census's formation rule as
endpoint 2. The spec defines the endpoint as "higher first-rank-1 layer or absence". That measure is now the endpoint;
the census rule is reported beside it as a secondary reading.

**The registered measure.** It is the first layer at which the target is the lens's top token. A pair counts as
"later or weaker" when the low-literacy side reaches rank 1 later than the high-literacy side, or never where the high
side does.

| | Count |
|---|---|
| Entries: low later or weaker / earlier or stronger / same layer / neither reaches rank 1 | 10 / 6 / 14 / 22 |
| Pairs whose majority is later or weaker / earlier or stronger / neither | 6 / 3 / 4 |
| Exact two-sided sign test on pairs | p = 0.51 |

**Secondary: the census's formation rule.** The census's own rules (`scripts/jlens_insights.py`):
- **Formation** means the target is readable for two consecutive layers in the top-8 window.
- **Classes**, on the low-literacy side, conditioned on the high-literacy side:
  - *held:* the target still ranks at the final layer;
  - *capture:* it never enters;
  - *hijack:* it forms, then is pushed out;
  - *unreadable:* the high-literacy side never forms either.

All 52 entries have usable lens readouts.

| | Count |
|---|---|
| Low-literacy class: held / unreadable / capture / hijack | 35 / 11 / 3 / 3 |
| Entries (census formation): low later or weaker / earlier or stronger / same layer / neither forms | 9 / 14 / 18 / 11 |
| Pairs whose majority is later or weaker / earlier or stronger / neither | 3 / 5 / 5 |
| Exact two-sided sign test on pairs | p = 0.73 |

**These readouts are from the middle lens era.** They landed on 2026-08-07, between the two known host-side changes
(2026-07-31 and 2026-08-14), and the 2026-10-31 re-measure covered July readouts only.

I did not re-read them. A re-read through the lens workflow writes its part by offset, so re-reading entries 1–8
would overwrite the August `part_01`, which holds all 52 readouts, with an 8-entry part. The census would then read
the truncated part.

A safe re-read needs either a copy of the batch under its own stem, which then also needs a census decision so its
rows are not counted twice, or an output that is not committed. The endpoint is not significant in this era. Whether it would be
null in today's era is not known.

## What these numbers can and cannot carry

- **13 pairs is very few.** A sign test needs 11 of 13 in one direction to reach p < 0.05. A real effect the size of
  the study's median would usually not show here.
- **The utterances come from an LLM patient simulator.** It runs on Claude-family and OpenRouter-hosted models, so
  the phrasing is not fully independent of the study's own generator family (spec, "Disclosures fixed in advance").
- **The frames, the targets and the screening are this study's instrument.** The harvest changes who wrote the span,
  not how it is measured.
- **The pairs are not minimal pairs.** The simulator rewrites the whole utterance, and the high-literacy span tends to
  be longer and more specific. So the contrast mixes literacy with detail.
- **Exploratory only.** The `pabharvest_` stem keeps these rows out of every confirmatory population by construction.

## What next

The follow-up design's step 2 (the three other preregistered models on the CPU logits lane, $0) would add models,
but the same 13 pairs. Step 3 (cumulative conversation context) needs a spec amendment. Given a null on 13 pairs,
neither changes what can be concluded about external phrasing. More harvested pairs would: a larger PAB sweep with
the simulator on a non-Claude model, which the spec names as the provenance fix.
