# Design: an open-weights advice arm with internals (Route B)

Drafted 2026-09-02 at the owner's request, as a design only. Nothing here is
registered, fired, or published until the owner signs off and the amendment in
§8 is filed. Companion to `docs/interp_engine_assessment.md` (what the engine
can do) and `scripts/depth_probe.py` (Route A, the cheaper cousin already built).

## 1. The gap this closes

The study currently has two arms that never meet:

| arm | what it measures | can we see inside? |
|---|---|---|
| next-token (10 open models) | probability of a continuation | partly: graphs on gemma-2-2b, now qwen3-4b; logit-lens depth via Route A |
| advice (8 deployed assistants) | the recommendation a real assistant gives | **no, and never** |

The headline behavioral claim lives in the second arm: when an assistant's
answer changes under patient phrasing, it usually moves DOWN the care ladder.
That claim has no mechanistic account, and cannot get one, because GPT-5.5,
Grok, Kimi and the rest are closed APIs.

Route B builds a third arm: a model that **gives real advice** and whose
**internals are readable**. It cannot explain what the deployed assistants do.
It can show that the effect appears in a system where the mechanism is visible,
which is a different and weaker claim, stated as such.

## 2. Candidate models

Three of the ten claim-grade models are genuine instruct models that will answer
a health question:

| model | why | risk |
|---|---|---|
| `medgemma-4b-it` | medically tuned; most likely to produce clinically shaped triage text | Gemma-3 arch, sandwich norms (see §7) |
| `gemma-3-4b-it` | same architecture, general tuning — the natural control for "is the effect medical tuning or just instruction tuning?" | may hedge or refuse more |
| `gemma-2-2b-it` | smallest, and the only instruct model that ALSO has hosted graphs and a transcoder source set | 2B advice quality is the weakest |

**Recommendation: all three, in that order of priority.** medgemma is the
primary; gemma-3-4b-it is the tuning control at matched architecture and size;
gemma-2-2b-it is the one where a downstream circuit trace is possible, which no
other candidate offers.

`interp-engine`'s validator covers gemma-2-2b-it and gemma-3-4b-it directly and
medgemma by architecture (`docs/interp_engine_assessment.md` §2).

## 3. Stimuli

Reuse the existing advice stimuli unchanged. Do not author new ones.

- Source: the three registered stimuli files already in `data/advice/`
  (sentence completions 20260721T235403Z, natural questions 20260728T194624Z,
  multi-cue 20260807T153329Z).
- The multi-cue nine are labelled `register_rewrite`, not `natural_questions`,
  per the audit finding — fix `export_advice_scenarios.py:66 _family_of` first
  or this arm inherits the mislabel.
- Same `ask_suffix` as the deployed arm so the prompts are identical modulo the
  chat template.
- **Sealed pairs stay sealed.** Run `scripts/seal_check.py` before any stimulus
  set is committed; the Tier B holdout (186 rows) is out.

Sample size: start with the 25 sentence completions plus 25 natural questions,
one sample per cell, three models. 150 generations total. That is the smallest
set that supports a paired comparison per family.

## 4. What gets measured, per prompt

Three layers of evidence from ONE generation, which is the point of the design:

1. **The advice itself.** `capture_generation` returns the completion and the
   activations together, so the text and the internals come from the same
   forward pass — not a second, re-run one.
2. **The judged tier.** Grade the generated text with the existing
   `data/advice_rubric.draft.json` and the existing judge configuration, so the
   open arm's tiers are commensurable with the deployed arm's. Note this is the
   one paid component (§6).
3. **The internals.** Per-layer logit-lens tier curves over the *generated*
   positions, not just the prompt — `capture_generation` captures at prompt and
   generated positions. Route A's `depth_probe.py` scoring functions apply
   unchanged; only the capture call differs.

The three together answer: does the model's internal urgency estimate diverge
between phrasings *before* it commits to a recommendation, and at what depth?

## 5. Design (2x2 within-model)

Per model, per scenario: clinical phrasing and patient phrasing, each in the
chat template. Paired by scenario, so every comparison is within-item.

Primary endpoint, matching the deployed arm's registered endpoint: **mean tier
shift (patient minus clinical) over paired scenarios**, per model, with a
bootstrap CI over scenarios.

Secondary endpoints:
- Direction counts: downgrades, upgrades, lateral, uninformative.
- **First divergence layer**: shallowest layer where the internal tier curves
  part by the threshold. This is the new quantity no existing arm has.
- Whether the internal divergence *precedes* the behavioral one, i.e. the curves
  separate at a layer where the top prediction is still the same word.

Controls:
- gemma-3-4b-it against medgemma-4b-it isolates medical tuning at matched
  architecture and size.
- A scrambled-phrasing control (patient wording with the symptom span replaced
  by a matched-length neutral span) separates "colloquial register" from "this
  particular symptom vocabulary". Cheap and worth having.

## 6. Cost

| component | cost |
|---|---|
| generation (3 models x 50 scenarios x 2 phrasings, CPU CI) | $0 |
| depth capture (same forward pass) | $0 |
| judging 300 responses with the existing haiku judge | ~$0.60 at the observed per-response rate |

Under the $2/day ceiling, but it IS a paid fire, so it needs the owner's explicit
words in a live chat and a `max_spend` matching the quote. A zero-cost variant
exists: hand-code a 50-response subsample instead, which also feeds the
clinician packet's Part 3.

**Runtime is the real cost.** Generation on CPU is far slower than a single
forward pass: a 4B model producing ~150 tokens takes minutes per response, so
300 responses will need chunking well inside the 240-minute job ceiling.
Budget one model per fire, chunked by offset like the 8B backfill.

## 7. The trap to avoid

All three candidates are **sandwich-norm architectures** (Gemma-2/3/4). Per
`interp-engine`'s own measurement, reading a transcoder off `mlp_out` instead of
`mlp_out_post` on gemma-2-2b gives FVU 9.8 — worse than predicting the mean —
against 0.26 on the right one. This arm reads `resid_post`, which is unambiguous,
so it is not affected. But if the arm is ever extended to MLP points or to a
transcoder source, check both candidates first
(`docs/interp_engine_assessment.md` §7).

Second trap: `apply_chat_template` must build the prompt. Hand-writing the chat
format silently changes what the model sees, and
`tokenizer.chat_template` is `None` for families that define their format in
code. Use `model.tok.has_chat_template()` and `message_partition`, never string
concatenation.

## 8. Registration

This is a new measurement axis and needs an amendment BEFORE any stimulus runs,
filed as the next number in `docs/prereg_amendment*.md`, naming:

- the three models and their HF revisions;
- the stimuli files and the exact subset;
- the primary endpoint (mean tier shift) and its test, matching the deployed
  arm's registered test so the two are comparable;
- the secondary endpoints, explicitly including first-divergence-layer as
  **exploratory** — no prior exists for it;
- the rubric version and judge configuration;
- that the lens is a logit lens and not the registered Jacobian lens.

Also required, and separately: the advice preregistration currently has two
undocumented divergences (the stealth second judge and the ~7x budget overrun,
audit findings). Those belong in `docs/prereg_divergence_log.md` before a new
amendment is layered on top.

## 9. How it would be published

- New data file `advice_open_arm.json`, new row in the site's data-contract
  table, a shape check in `validate_frontend_contract.py`.
- The LLM page gains a clearly separated section. The open arm must NOT be
  pooled into the eight-arm figures: different models, different scale,
  different provenance. The `_family_of` pooling bug is exactly the failure mode
  to avoid repeating.
- Every claim carries the caveat that a 2-4B open model is not a proxy for a
  frontier assistant, and that the lens is a logit lens.

## 10. Build order

1. Land Route A's pilot and confirm the CPU path works at all. **Blocks everything.**
2. Fix `_family_of` so the multi-cue nine stop being labelled natural questions.
3. File the amendment; owner signs.
4. `scripts/open_advice_arm.py`: chat-template prompts, `capture_generation`,
   depth curves over generated positions, one JSONL per model.
5. New `mode=advice_depth` branch of the logits-eval lane (same pattern as
   Route A: no new trigger file, no new lane to park).
6. Generate on the 50-scenario subset, one model per fire.
7. Judge with the existing pipeline (paid, owner-approved, `max_spend` quoted).
8. Analysis + export + site section.

Steps 1 to 3 are the gate. Nothing after step 3 should start before the
amendment is signed.
