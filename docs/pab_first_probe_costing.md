# PatientAgentBench first live probe — costed plan (rev 3, OpenRouter, 2026-08-04)

**Nothing here is approved, registered, or fired.** Rev 1 (2026-08-04) priced this
probe for AWS Bedrock, whose registry carries the only Qwen entry the plan wanted.
There are no Bedrock credentials; there *is* an approved prepaid OpenRouter key.
This revision re-targets the pilot to OpenRouter and re-costs it.

Every figure comes from `scripts/pab_probe_cost.py`, which runs offline at $0 and
is pinned by `tests/test_pab_probe_cost.py`. Re-cost any variant:

```bash
python scripts/pab_probe_cost.py                       # this plan
python scripts/pab_probe_cost.py --preset bedrock      # rev 1, for the diff
python scripts/pab_probe_cost.py --balance <prepaid>   # check the key's balance
```

## Answering the budget question first

The prepaid OpenRouter balance is **$9**. It is not the binding constraint, and
the reason matters: **the jury bills Anthropic, not OpenRouter.** Splitting the
plan by who invoices:

| stage | OpenRouter | Anthropic | total |
|---|---|---|---|
| Stage 0 — tool-calling smoke test | $0.025 | — | $0.025 |
| Stage 1 — manipulation check (32 conversations) | $1.187 | — | $1.187 |
| Stage 2 — outcome pilot (52 conversations, scored) | $1.929 | $8.476 | $10.405 |
| **whole programme** (Stage 1's conversations are reused) | **$1.95** | **$8.48** | **$10.43** |

So $9 covers the entire programme's OpenRouter side about **4.6× over**, and
Stages 0 and 1 together draw **$1.21**, leaving **$7.79**. What actually
constrains the pilot is Anthropic jury spend and the $2/day operational ceiling.

Check any shape against the balance directly:

```bash
python scripts/pab_probe_cost.py --openrouter-balance 9
python scripts/pab_probe_cost.py --arms 2 --cases 13 --openrouter-balance 9
```

## What changed from rev 1

Three things, and only one of them is the channel.

**1. The channel.** Patient, assistant and sandbox now run through OpenRouter
(`provider="openai-protocol-api"`, `auth="api_key"`, `OPENROUTER_API_KEY`), using
model specs the fork injects into the benchmark's registry without editing it.
Registry keys are the engine's own `openrouter:vendor/model` names, so the
benchmark config, the transcript, and the ledger all say the same string.

**2. The jury stays where it was.** It runs on the direct Anthropic API
(`ANTHROPIC_API_KEY`, an existing secret) rather than through OpenRouter — a mixed
setup, which `docs/advice_arm_handoff.md` already treats as reasonable. Two
reasons. The rubric is the *validated instrument*, and Opus 4.8 is the benchmark's
shipped default; routing it through an aggregator adds an intermediary to the one
leg whose fidelity the whole exercise depends on. And no verified OpenRouter price
exists in this repo for any Anthropic slug — registering one would mean guessing
either the slug or the price. So the jury is priced from
`medlang_circuits/evaluate_models.py :: PRICING` at the same $5/$25 as Bedrock,
and the jury cost does not move at all.

**3. A leg was missing from rev 1.** Every conversation makes a **sandbox
generation call** — one LLM call that invents the offices and doctors the tools
operate on. It is easy to miss because `ConversationRunner` creates that client
internally and discards its response, and it is per *conversation*, not per run.
It is now costed. On this shape it is ~2% of the total, but it is real, and it is
the leg the tool-calling smoke test had to be restructured to meter.

## Prices, and where each came from

Never guessed. `resolve_price()` resolves every model against a named in-repo
source and returns `None` for anything unverified; an unpriced plan renders **N/A**
and exits non-zero rather than reporting a number.

| model | role | $/1M in | $/1M out | source |
|---|---|---|---|---|
| `openrouter:openai/gpt-5.4-mini` | assistant, sandbox | 0.80 | 4.75 | `data/advice_providers.json :: openai.pricing` |
| `openrouter:x-ai/grok-4.3` | patient | 1.32 | 2.63 | `data/advice_providers.json :: xai.default_pricing` |
| `claude-opus-4-8` | jury | 5.00 | 25.00 | `medlang_circuits/evaluate_models.py :: PRICING` |

`data/advice_providers.json` is this repo's **reviewed** provider registry, verified
against vendor docs on 2026-07-21 and carrying at least one correction from a live
400 (`openai/gpt-5.5-mini` does not exist on OpenRouter; `openai/gpt-5.4-mini`
does) — so the slugs are evidence-backed rather than recalled. Its own header
states the convention: prices are worst-case, cache-miss rates used for
spend-ceiling math, and the true bill is the provider's. OpenRouter entries carry
list price plus roughly a 5% aggregator margin.

**Every number below is therefore an upper bound, not a quote.** One caveat this
session could not close: OpenRouter is unreachable from this sandbox (the egress
proxy denies the host), so slugs and prices could not be re-verified live. Do that
before the first fire.

One model the plan wanted and did not get: **Qwen**. Rev 1's patient simulator was
`qwen3-235b-bedrock`. There is no verified OpenRouter price for any Qwen slug in
this repo, so rather than invent one the patient moved to `x-ai/grok-4.3` — still
non-Claude, so the provenance argument for a non-Claude patient survives.

## The design (unchanged from rev 1)

Four arms, one factor, sweeping `health_literacy` from the `confused` preset base:

| arm | `personality` label | role |
|---|---|---|
| 1 | `confused` | external anchor: upstream's preset via upstream's own function |
| 2 | `pw:base=confused;health_literacy=low` | internal control: same seven traits, adapter-rendered |
| 3 | `pw:base=confused;health_literacy=medium` | sweep |
| 4 | `pw:base=confused;health_literacy=high` | sweep |

`confused` is the only preset carrying `health_literacy: low`, and it carries
`clarity: low` and `urgency: low` with it — the bundle that makes the paper's own
headline (`confused` 3.15 > `skeptical` 2.52 on triage) unattributable to any
single trait. Arms 2–4 are the identified contrast;
`scripts/validate_pab_contract.py` checks that exactly one trait varies before any
analysis runs. Arm 1 against arm 2 is free information about whether the persona
*label* moves scores in their harness: the two render identical trait text and
differ only in the block's `type` attribute.

The stimulus sets are built and committed at
`PatientAgentBench-patientwords/pw_pilot/`, with the runbook in its README. They
were produced by `build_sweep`, which refuses to write a file whose arms differ in
anything but `personality`, and each was read back through upstream's own loader
before being accepted.

**Per-arm n = 13**, sized to the effect the paper reports: a paired test detects
their 0.79-point persona spread at 80% power with a paired SD of 1.0
(n = (2.80 × 1.0 / 0.79)² ≈ 13). Arms share cases, so the analysis is paired by
construction. **Turns: 3.**

**Models.**

| role | model | why |
|---|---|---|
| patient | `openrouter:x-ai/grok-4.3` | Non-Claude, so patient language is not Claude-written and Claude-graded. Frontier-class, which matters more than its price: a small model that ignores personas is indistinguishable from an incoherent persona, and telling those apart *is* Stage 1. |
| assistant | `openrouter:openai/gpt-5.4-mini` | Mid-tier, in the band where the paper reports triage pass rates spreading (32%–88%) rather than flooring or ceiling. Mature tool-calling, which is the risk the smoke test exists to retire. |
| sandbox | `openrouter:openai/gpt-5.4-mini` | Emits JSON only; shares the assistant's model for simplicity. Invalid JSON is retried up to 3×, so a reliable generator is worth more than the ~2% it costs. |
| jury | `claude-opus-4-8` (direct Anthropic API) | The validated instrument, benchmark default. **Do not substitute** — see above. |

## The money

Per-conversation cost splits roughly 2% sandbox / 5% patient / 11% assistant /
**81% jury**. The six rubric prompts total ~12k tokens before a transcript is
added, and every jury model re-reads all six on every conversation. That ratio is
why the probe is staged.

### Stage 0 — tool-calling smoke test

One conversation, 2 turns, no jury. **Estimated $0.025**, ceiling `--max-spend
0.10`.

PatientAgentBench is agentic and the paper omits models "solely because they
lacked reliable native tool-calling for agentic workflows". A model that narrates
tool use instead of emitting calls produces transcripts that look fine and score
meaningless, so this runs before anything else:

```bash
python -m patientwords_pab.toolcall_smoke --dry-run     # $0
python -m patientwords_pab.toolcall_smoke \
    --assistant openrouter:openai/gpt-5.4-mini \
    --report ../patientwords-engine/data/pab/toolcall_smoke.report.json
```

It asserts the transcript holds ≥1 tool call, that every call names a registered
tool, carries dict arguments, and is answered by a matching result. Without the key
it skips and exits 0. **Gate:** if it fails, escalate the assistant to
`openrouter:openai/gpt-5.5` (which takes Stage 2 from $10.41 to $16.99) and re-run;
if that also fails, the OpenRouter path is not viable for the assistant role and
the plan needs a different channel. Only the assistant carries this risk — the
patient agent has no tools.

**Actual spend so far: $0.00.** `OPENROUTER_API_KEY` is not present in the
development environment, so the live check has not run. The estimate above is
what it will cost when it does.

### Stage 1 — manipulation check, generation only

4 arms × 8 cases × 3 turns = **32 conversations**, no evaluation.

| leg | OpenRouter | rev 1 (Bedrock) |
|---|---|---|
| sandbox | $0.119 | $0.128 |
| patient | $0.342 | $0.061 |
| assistant | $0.726 | $0.879 |
| jury | $0.000 | $0.000 |
| **total** | **$1.187** | $1.068 |

**Fits inside one day at the $2/day ceiling, with $0.81 to spare.** Run
`generate` through `python -m patientwords_pab.run`, then read the patient turns.
The register check is $0 and uses instruments this repo already owns: the
clinical-term lexicon and the readability report, over the first-person patient
utterances, low arm against high arm.

**Gate.** If the arms' patient language does not separate on register, stop — the
persona instruction is not driving the simulator and no jury spend will make the
sweep mean anything. Sunk cost at that point: **$1.21** including the smoke test.

Cheaper patients exist if Stage 1 needs repeating: Kimi K2.5 $1.03,
Gemini 3.5 Flash $0.96, DeepSeek V4 Flash $0.88. All are worse choices for the
*first* run, for the reason in the model table.

### Stage 2 — outcome pilot

4 arms × 13 cases = **52 conversations**, scored.

| leg | OpenRouter | rev 1 (Bedrock) |
|---|---|---|
| sandbox | $0.193 | $0.207 |
| patient | $0.556 | $0.100 |
| assistant | $1.180 | $1.429 |
| jury | $8.476 | $8.476 |
| **total** | **$10.405** | $10.211 |
| per conversation | $0.2001 | $0.1964 |
| days at the $2 ceiling | 6 | 6 |

**The channel switch is close to cost-neutral: +$0.19, or +1.9%.** That is the
headline of this revision and it is not a coincidence — the jury is 81% of the
bill and did not move. The patient leg is 5.6× dearer (grok-4.3 against
qwen3-235b) and the assistant leg is 17% cheaper (gpt-5.4-mini against
haiku-4.5), and the two nearly cancel.

The $2/day limit is a daily operational ceiling, not a total budget: a probe
larger than it is scheduled, not refused. `patient-agent-bench evaluate --run-dir`
scores an existing run and the runner caches conversations by signature, so
Stage 1's 32 conversations are reused and the work splits across days without
re-generating anything. Inside a single day the ceiling buys n=2/arm with the Opus
jury (n=3 on Sonnet 5, n=7 on Haiku 4.5) — which is why Stage 2 is scheduled
rather than shrunk.

**Programme total: $10.43** ($0.025 + $1.187 + the $9.22 increment to reach 52
scored conversations), across 6 days at the ceiling, with a stop-gate after
Stage 0 costing $0.03 and another after Stage 1 costing $1.21.

### Smaller versions of Stage 2

Stage 2's shape is `arms × cases`, and cost is linear in both. Every option below
keeps the validated instrument (Opus 4.8, all six rubrics) and n at or near the
powered 13:

| option | arms | n | conversations | OpenRouter | Anthropic | total | days |
|---|---|---|---|---|---|---|---|
| A — as planned | 4 | 13 | 52 | $1.93 | $8.48 | $10.40 | 6 |
| B — drop the preset anchor | 3 | 13 | 39 | $1.45 | $6.36 | $7.80 | 4 |
| **C — low vs high only** | **2** | **13** | **26** | **$0.96** | **$4.24** | **$5.20** | **3** |
| D — low vs high, n=8 | 2 | 8 | 16 | $0.59 | $2.61 | $3.20 | 2 |
| E — four arms, n=6 | 4 | 6 | 24 | $0.89 | $3.91 | $4.80 | 3 |

**Option C is the recommended smaller Stage 2.** It halves the arms, not the
instrument: the identified contrast (literacy low vs high, everything else held
at `confused`'s levels) survives intact at full power. What it gives up is the
`confused` preset anchor — so no external comparison to published preset numbers,
and no measurement of the persona-label effect — and the medium midpoint, so no
monotonicity check. The stimulus set is already built:
`pw_pilot/sweep_health_literacy_2arm_n13.json`.

Option D is cheaper still but underpowered: n=8 detects roughly a 1.0-point
effect, so it estimates an effect size rather than testing for one. Prefer C.

**A better lever than shrinking: buy the two purchases separately.** Generation
and scoring are independent, and scoring is repeatable on stored transcripts
(`evaluate --run-dir`). Generating all 52 conversations costs **$1.93, entirely
OpenRouter** — comfortably inside the $9 — and produces the artifact that is
expensive to make and free to keep. The jury can then be bought in whatever size
the evidence justifies: score 26 first, look, score the rest only if it is worth
it. Nothing about the transcripts changes in the meantime.

A screening jury is possible but is a different instrument: Haiku 4.5 scores all
52 for $1.70 instead of $8.48. That buys a look at whether the effect is visible
at all, not a result — the clinician-agreement figure that justifies using this
benchmark belongs to the panel the paper validated, not to Haiku. If used, score
the same transcripts again with Opus before reporting anything.

### What the pilot buys an option on

| next step | conversations | cost | days at ceiling |
|---|---|---|---|
| second anchor: same sweep from `base=skeptical` | 52 | $10.41 | 6 |
| second trait: `communication` sweep, same shape | 52 | $10.41 | 6 |
| assistant escalated to `openrouter:openai/gpt-5.5` | 52 | $16.99 | 9 |
| powered single-trait study, n=32, two assistants | 256 | ~$51 | 26 |

The `base=skeptical` replication matters most: the same trait from the opposite
anchor. Same sign from both bases means the effect generalises across personas;
different signs mean it is persona-dependent — itself a finding the preset system
could never have produced.

## Where the spend is recorded

The probe is billed by OpenRouter and Anthropic, not fired through a CI trigger,
so `scripts/fire_trigger.py`'s guard never sees it. Two mechanisms close that gap:

* The smoke test writes a `.report.json` sidecar in this repo's established shape
  (`run_timestamp`, `model`, `max_spend_usd`, `cost_usd`,
  `usage.per_model{calls, input_tokens, output_tokens, cost}`).
* `scripts/ledger_update.py` now scans `data/pab/*.report.json` alongside
  `data/simulated/` and `data/advice/`, so that cost folds into `spend.by_day` and
  the $2/day guard. `ledger_update.py` remains the only writer of spend numbers;
  `ops/dashboard.json` is never hand-edited. Its Tier B attribution gates on
  `task == "pairs"`, so probe sidecars count as background spend and never touch
  Tier B counters — pinned by a regression test.

The sidecar's cost is a **list-price reconstruction** from reported token usage,
not the provider's invoice, and says so in a `cost_basis` field. The prepaid
balance is the hard external ceiling above all of this.

## Cost assumptions, stated so they can be attacked

- Token counts are characters ÷ 3.6, measured from the shipped artifacts on
  2026-08-04 (prompt templates, the sample's stories and profile XML, the 15
  sandbox tool schemas, the sandbox generation prompt, the six rubric prompts).
  `tiktoken` fetches its encoding over a network this sandbox blocks.
- 1.6 assistant calls per turn, 500 tokens of dialogue growth per turn, 200-token
  assistant replies, 100-token patient replies, 150-token rubric verdicts, one
  sandbox call per conversation at 483 in / 700 out. Deliberately generous.
- Prices are ceiling-side (list + ~5% aggregator margin for OpenRouter).
- Retries and failed conversations are not modelled — the sandbox generator alone
  retries up to 3× on invalid JSON. Budget ~10% headroom.

## What is already known good

An offline full-pipeline rehearsal (`tests/test_pw_sweep_rehearsal.py` in the fork)
runs this exact config and stimulus set through the real `ExperimentRunner`,
`ConversationRunner` and `OutputManager` with every model mocked, then checks the
resulting run directory against the invariants this repo's Layer-2 validator
enforces. Registry resolution, agent selection, arm labels reaching the transcript,
tool calls surviving, evaluations joining slot-for-slot, arms staying balanced —
all tested. The only untested thing before a live pilot is whether the models
themselves behave, which is exactly what Stage 0 buys.

That rehearsal found one bug worth recording. `initialize_sandbox()` attaches a
generated PCP to the patient profile *before* the transcript records it, so
`user_profile` differs between arms of the same case and differs between runs —
two distinct renderings per case across repeated rehearsals, while the scenario
stayed byte-stable. This repo's pair key included `user_profile`, so every case
would have looked absent from every arm and a perfectly good run would have been
reported as a broken design. `data/pab_transcript_contract.json` now keys on the
scenario alone, with regression tests on both sides.

## Go / no-go on Stage 1

**Go, conditional on Stage 0.** At $1.19 Stage 1 fits inside a single day's
ceiling with $0.81 to spare, needs no amendment because it produces no scored
outcome — it only asks whether the persona instruction changes the patient's
language, which is a property of text this repo can measure for $0 — and its
whole downside is bounded at $1.21 including the smoke test. The re-costing found
no reason to hesitate: OpenRouter is 1.9% dearer than the Bedrock plan overall and
11% dearer at Stage 1, on prices that are upper bounds. What gates it is not
money but tool-calling: run the $0.03 smoke test first, because if
`openrouter:openai/gpt-5.4-mini` cannot drive the sandbox tools then all 32 Stage 1
conversations are degenerate and the $1.19 buys nothing. Stage 2, at $10.41 over
six days of ceiling, is a separate decision that should not be taken until Stage 1
has shown the manipulation takes — and it still needs the pre-registration posture
fixed in advance, since adopting an external rubric after seeing it agrees better
than ours would be instrument shopping.

---

## Rev 4 (2026-08-04): what the live run actually cost

Rev 3 was an estimate from a token model. Stage 0 measured the real thing, so
the numbers below are observed, not projected.

**Measured, one 3-turn conversation** (`data/pab/toolcall_smoke_20260804T042921Z.report.json`,
gpt-5.4-mini assistant, grok-4.3 patient, gpt-5.4-mini sandbox): **$0.035342**.
Rev 3's generation-only estimate was $1.929/52 = $0.0371 per conversation — 5%
high, which is the right direction for a ceiling model.

Per-leg tokens, which is what makes the per-model arithmetic possible:

| leg | calls | input | output |
|---|---|---|---|
| assistant | 5 | 20,079 | 635 |
| patient | 3 | 6,779 | 1,082 |
| sandbox | 1 | 468 | 862 |

The assistant's input:output ratio is **32:1** — the system prompt, patient
profile and tool schemas are re-sent on every call. That, not output length, is
what sets the cost of a model, and it is why the per-model spread tracks input
price far more than output price.

**Prices are now live, not ceiling-side.** The catalogue lookup ran in CI
against OpenRouter's own `/models` endpoint and is committed dated
(`data/pab/openrouter_catalogue_*.json`). All three previously transcribed
prices were confirmed as genuine upper bounds. Two of the paper's slugs were
found only on a second, narrower search — the first run's 12-result cap had
hidden them: `openai/gpt-5.4` (2.5/15) and `qwen/qwen3-235b-a22b-2507`
(0.1495/0.598).

**Cost per conversation by assistant, at the measured token mix** (assistant leg
+ $0.0163 fixed for patient and sandbox):

| model | $/conv | | model | $/conv |
|---|---|---|---|---|
| gpt-5.5 | 0.1417 | | claude-haiku-4.5 | 0.0396 |
| claude-opus-4.8 | 0.1326 | | gemini-3-flash | 0.0282 |
| gpt-5.4 | 0.0760 | | qwen3-235b | 0.0197 |
| gemini-3.1-pro | 0.0641 | | qwen3-next-80b | 0.0188 |
| claude-sonnet-5 | 0.0628 | | gpt-oss-120b | 0.0172 |

The top two models are **8× the bottom two**. Ordering the config most-expensive
first is a direct consequence: the guard aborts hard, generation is sequential,
so whatever a ceiling trip loses is the tail — and the tail should be the models
that are cheap to buy again.

**Wall clock, which rev 3 did not cost at all.** Generation ran at ~43 s per
conversation on the frontier models (18 conversations in 13 minutes). Sixty
conversations is therefore ~45 minutes, not the few minutes the spend figure
might suggest. A run is bounded by GitHub's 360-minute job limit long before it
is bounded by $4, which is why generation now stops itself with `timeout
--signal=INT` rather than being cancelled with its transcripts unsaved.

**The ceiling is now enforced.** Rev 3 wrote `max_spend` into the trigger and
the ledger, and nothing stopped the run. `patientwords_pab.budget_guard` meters
every call through upstream's single model factory and aborts at the limit; an
unpriced leg refuses to start, because a ceiling that cannot see a leg is not a
ceiling. Upstream registers its whole direct-API channel unpriced, so the
Anthropic jury needed priced `pw:`-prefixed variants before its own $2 could be
enforced at all.
