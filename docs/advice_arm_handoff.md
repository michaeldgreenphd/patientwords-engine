# Frontier-advice arm — handoff (2026-07-21)

Standalone handoff for the session integrating the new **advice evaluation arm**.
It assumes the 2026-07-21 audit handoff (`docs/audit_2026-07-21.md`, Appendix B
queue) has been worked; nothing here depends on unmerged audit items except where
marked. Everything below landed on branch
`claude/patientwords-audit-reflection-alwovz`; the code is complete and tested
(297-test suite green, ruff clean), but the arm is **deliberately not wired into
the firing path** — steps 1–4 below do that, in order, with owner sign-off where
marked.

## What this arm is

The next-token study measures probabilities. This arm measures the **advice**
deployed assistant models actually give for the same clinical situation phrased
two ways, with three run modes matching the owner's design:

1. **Stress-test known-good situations** — stimuli built from the published site
   payload (screened-in, measured, holdout-withheld by construction), e.g. the
   200 measured flips.
2. **Manual paired vignettes** — owner-authored clinical + patient scripts.
3. **Translation-recovery arm** — an LLM patient→clinical translation step runs
   before elicitation, so recovery of the advice (not just the token) is
   measured, mirroring the study's translation-mitigation panel.

Elicitation is unrepeatable by nature, so the design goal is **auditable, not
reproducible**: an append-only JSONL archive, one record per API call with the
full request, full raw response, exact returned model version string, UTC
timestamps, latency, per-call cost, engine sha, and a per-record sha256 hash
chain whose head is committed in the cost sidecar in the same commit as the data
(public repo ⇒ third-party timestamps). Judging and analysis are fully
reproducible from the archive forever.

## What exists on this branch

| Path | What |
|---|---|
| `scripts/advice_eval.py` | the pipeline: `build-stimuli` / `elicit` / `judge` / `analyze` / `verify-chain` |
| `.github/workflows/advice_evaluation.yml` | CI workflow (dispatch form + push-path on `.github/trigger/advice-eval.json`; per-branch concurrency group, `cancel-in-progress: false`) |
| `data/advice_rubric.example.json` | rubric skeleton (tiers, flags, judge instructions) — **example only, needs domain review** |
| `data/advice/README.md` | archive schema + audit-chain contract + rules |
| `tests/test_advice_eval.py` | 15 offline tests: stimulus validation, holdout guard (incl. the null-`start_utc` trap), chain/resume/tamper/ceiling, judge idempotence, analysis classes, workflow defaults-dict wiring |

Deliberately **absent**, by design:

- `.github/trigger/advice-eval.json` — a hand-committed trigger file fires the
  paid workflow on push (including merges). The first sanctioned
  `fire_trigger.py` fire creates it. Never create it by hand.
- `fire_trigger.py` registration — step 2 below, applied by the integrating
  session so it composes with whatever the audit's E10 hygiene work did to that
  file.
- `data/advice_rubric.json` — only the reviewed copy may carry that name.

## Integration steps (in order)

### 1. Land the code

Bring this branch's five paths onto the working branch/main per the current
branch strategy. This branch touches **no trigger files**, so merging it cannot
fire anything.

### 2. Register the trigger in `scripts/fire_trigger.py`

Three edits (then extend `tests/test_fire_trigger.py`'s key-set/paid coverage to
match — the repo convention is that KNOWN_KEYS is verified against the workflow
heredoc, so cite `advice_evaluation.yml` and today's date in the comment):

```python
# in TRIGGERS, after "archive-renders":
    "advice-eval",

# PAID_TRIGGERS — this arm spends Anthropic tokens on elicit AND judge:
PAID_TRIGGERS = frozenset({"scenario-generation", "model-evaluation", "advice-eval"})

# in KNOWN_KEYS (verified against advice_evaluation.yml `defaults` dict, 2026-07-21):
    "advice-eval": frozenset({
        "stimuli_file", "models", "arms", "samples", "temperature", "max_tokens",
        "translator_model", "max_spend", "judge", "judge_model", "judge_max_spend",
        "rubric", "offset", "limit", "commit_outputs",
    }),
```

Note the budget guard counts `max_spend` for paid triggers; `judge_max_spend` is
a second ceiling the guard does not see — keep `max_spend + judge_max_spend`
inside the day's remaining headroom when firing with `judge: true` (or extend
the guard to sum both keys — cleaner; add a regression test if so).

### 3. Rubric domain review (owner + domain reviewer — blocking for judged runs)

Copy `data/advice_rubric.example.json` → `data/advice_rubric.json` after review.
The judge records `rubric_sha256` and version on every judgment, so later rubric
revisions never contaminate earlier codings — re-judging under a new rubric is a
new, distinguishable pass over the same archive. Un-judged elicitation (steps
5–6) may proceed before review; judged/claim-grade output may not.

### 4. Pre-register before the first paid fire (owner sign-off)

Write `docs/preregistration_advice.md` in the Tier B document's style. Minimum
contents: endpoints (mean tier rank difference patient−clinical; advice
downgrade rate; disclaimer/refusal rate difference by arm; translation recovery
rate; within-prompt variance by arm), direction and refutation criteria
(register the null explicitly: no phrasing-dependent advice difference in
frontier models is a reportable result), models and exact snapshot policy, K,
temperature, stimulus source and n, rubric version, judge model, exclusion
rules, and analysis code pointer (`advice_eval.py analyze`, seed recorded).
Sign-off note: the engine README's "nothing here generates or evaluates medical
advice" line needs an owner-approved amendment ("…evaluates assistant advice for
measurement; it never dispenses advice") — owner prose, redline it.

### 5. Build and review stimuli ($0, local)

```bash
# Mode 1 — situations the study has already validated (holdout-safe by construction):
python scripts/advice_eval.py build-stimuli --source payload --only-flips --max-items 25

# Mode 2 — owner-authored pairs:
#   my_situations.json: [{"id": "...", "clinical": "...", "patient": "...", "notes": "..."}]
python scripts/advice_eval.py build-stimuli --source manual --manual-in my_situations.json

# (also available: --source pairs <batch.json> — excludes Tier B holdout via tierb_split
#  and HARD-ERRORS if the dashboard's tierb.start_utc is null; point --dashboard at the
#  ops-truth copy, never a stale main checkout)
```

**Review the assembled messages by eye before eliciting** — payload-sourced
vignettes are probe prompts finished with a fixed ask suffix ("… — anyway, what
should I do?"), which reads conversationally but is not hand-polished; the same
suffix goes on both sides verbatim so the minimal-pair property holds. Manual
mode is where polished vignettes come from. Commit the stimuli file (the
workflow reads it from the repo).

### 6. Pilot fire (paid — the arm's first live run)

```bash
python scripts/fire_trigger.py fire --trigger advice-eval --params '{
  "stimuli_file": "data/advice/stimuli_<STAMP>.json",
  "models": "claude-haiku-4-5",
  "arms": "clinical,patient,translated",
  "samples": "3", "max_spend": "0.50",
  "judge": "false",
  "commit_outputs": "true",
  "_note": "advice arm pilot — rubric pending review, elicit only"
}'
```

This first fire **creates** `.github/trigger/advice-eval.json` (the jlens
pattern) — thereafter the merge/copy danger rule applies to it like the other
five. After the run lands: harvest, `fire_trigger.py resolve --trigger
advice-eval`, then verify the archive locally:

```bash
python scripts/advice_eval.py verify-chain \
  --responses data/advice/responses_stimuli_<STAMP>.jsonl \
  --sidecar   data/advice/responses_stimuli_<STAMP>.report.json
```

Once the rubric is reviewed: fire again with `"judge": "true"` (same stimuli —
elicit resumes/skips everything already archived and only the judge pass runs),
or run judge+analyze locally in CI-less form only if a key ever becomes
available locally (it should not; keys live in Actions secrets only).

### 7. Scale run

Only after: pilot chain verified, judge validated against a human-coded sample
(`judge --human-sample 25` exports the blinded CSV; report agreement), and the
pre-registration committed. Chunk with `offset`/`limit` per the queue
discipline; elicit resume makes re-fires idempotent.

## Budget arithmetic (size ceilings with headroom)

Per-call cost ≈ (in_tokens × in_price + out_tokens × out_price)/1e6; the
script's pre-call check reserves the **worst case** (max_tokens full), so runs
stop early rather than breach — a ceiling of $X guarantees spend < $X.

| Run | Calls | Est. actual | Suggested max_spend |
|---|---|---|---|
| Pilot: 25 stimuli × 3 arms × K=3, haiku + haiku translator | 25 + 225 | ~$0.55 | 1.00 |
| Judge pass on that pilot (haiku) | 225 | ~$0.20 | 0.50 |
| Scale: 100 stimuli × 3 arms × K=5, sonnet-class | 100 + 1500 | ~$13 | 15 — **needs an owner-approved daily-ceiling plan; $2/day will refuse it** (chunk across days or raise the ceiling deliberately) |

## Guardrails (absolute, inherited + arm-specific)

- Fire ONLY via `scripts/fire_trigger.py`; never touch `.github/trigger/` by
  hand; never `--force-evict`/`--override-budget`; chain, never stack.
- `data/advice/` is **append-only**; `elicit` refuses to append to a broken
  chain; a tampered archive is reported to the owner, never repaired in place.
- Holdout seal: never quote or paraphrase Tier B holdout phrases anywhere —
  the `--source pairs` guard is mechanical, but reports and chat replies are on
  you. Payload-sourced stimuli are safe by construction.
- Judge blinding: the judge sees response text only; keep it that way.
- No medical vocabulary in Python — stimuli, tiers, and judge wording are data.
- Both repos public: no secrets, ever; keys exist only as Actions secrets.
- This arm **evaluates** advice for measurement; it never dispenses advice, and
  published framing must say so (owner-approved prose).
- Model endpoints drift: every record logs the returned model version string;
  when the arm becomes routine, add a small pinned weekly probe (the advice
  drift sentinel) before making cross-week comparisons.
