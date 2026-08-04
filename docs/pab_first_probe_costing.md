# PatientAgentBench first live probe — costed plan (2026-08-04)

**Nothing here is approved, registered, or fired.** This is the cost and shape a
first live probe would take, put in front of the decision rather than after it.
Every figure comes from `scripts/pab_probe_cost.py`, which runs offline at $0 and
is pinned by `tests/test_pab_probe_cost.py`; re-cost any variant with
`python scripts/pab_probe_cost.py --cases N --turns T --jury-model M`.

Prerequisites, none of them satisfied yet: a pre-registration amendment or an
explicitly labelled exploratory arm (adopting an external rubric *after* seeing
that it agrees better than ours would be instrument shopping), a decision on where
derived artifacts may land given CC-BY-NC-4.0, and AWS Bedrock credentials, which
this study does not currently hold.

## What the probe is for

Not to estimate the effect precisely. To answer, in order:

1. **Does the manipulation take?** Setting `health_literacy` alone may produce a
   persona the simulator partly ignores. Costs under a dollar to find out, and
   nothing else is worth paying for until it is answered.
2. **Does the benchmark's most discriminating dimension move with it?** If triage
   quality does not shift when literacy alone shifts, the paper's persona result is
   attributable to clarity and cooperation — which is what its own text implies but
   cannot show — and the register hypothesis does not survive contact with a
   multi-turn tool-using agent.
3. **How large is the effect, for powering a real study?**

## The design

Four arms, one factor. Sweeping `health_literacy` from the `confused` preset base:

| arm | `personality` label | role |
|---|---|---|
| 1 | `confused` | external anchor: upstream's own preset, rendered by upstream's own function |
| 2 | `pw:base=confused` | internal control: same seven traits, rendered by the adapter |
| 3 | `pw:base=confused;health_literacy=medium` | sweep |
| 4 | `pw:base=confused;health_literacy=high` | sweep |

Why this base rather than the neutral all-`medium` one: `confused` is the only
preset carrying `health_literacy: low`, and it carries `clarity: low` and `urgency:
low` with it — exactly the bundle that makes the paper's own headline
(`confused` 3.15 > `skeptical` 2.52 on triage quality) unattributable to any single
trait. Sweeping literacy from that base holds the other six at levels upstream
validated. The neutral base is cleaner in principle but is itself off-manifold: no
preset combines `cooperation: medium` with `anxiety: medium`, so a neutral-base
sweep compares three unvalidated personas against an unvalidated baseline. See
`docs/pab_integration_layers.md` for the numbers.

Arms 2–4 are the single-factor contrast, and
`scripts/validate_pab_contract.py` checks that exactly one trait varies across
them before any analysis runs. **Arm 1 against arm 2 is free information**: the two
render identical trait text and differ only in the block's `type` attribute
(`"confused"` vs `"custom"`). A gap there is a label effect in their harness — a
result worth reporting upstream, and a caveat this study would otherwise carry
unknowingly.

**Per-arm n = 13.** Sized to the effect the paper reports, not to a round number: a
paired test detects their observed 0.79-point persona spread on triage quality with
80% power at α = 0.05 when the paired SD is 1.0 (n = (2.80 × 1.0 / 0.79)² ≈ 13).
Arms share cases, so the analysis is paired by construction. This n is honest about
what it buys — a large effect and an effect-size estimate, not a precise one; a
0.5-point effect would need n ≈ 32.

**Models.**

| role | model | why |
|---|---|---|
| patient simulator | `qwen3-235b-bedrock` | Non-Claude, so the patient language is not Claude-written and Claude-graded — the provenance limitation the design note flags for Tier 2. Large enough for reliable persona adherence, which matters: a small model ignoring the persona is indistinguishable from an incoherent persona, and that is the exact question stage 1 asks. $0.22/$0.88 per 1M. |
| assistant (system under test) | `claude-haiku-4.5-bedrock` | Mid-tier deployed-assistant class, in the range where the paper reports triage pass rates spreading (32%–88%) rather than flooring or ceiling. Ties back to this study's own model matrix. $1/$5. |
| jury | `claude-opus-4.8-bedrock` | Their shipped default, and the validated instrument. **Do not substitute.** A cheaper jury would cut total cost by two-thirds and would also discard the clinician-agreement figure that is a headline reason to use this benchmark at all. |

**Turns: 3** (the framework's `BenchConfig` default; the shipped config uses 10).
Cost grows faster than linearly in turns because every call re-sends the context so
far — 3 → 6 turns is +43% per conversation, 3 → 10 is +107%. Three turns is enough
for the triage rubric's "asked a clarifying question before recommending"
distinction, which is the graded behaviour. If stage 1 shows conversations
truncating mid-triage, re-cost at 6.

## The money

Per-conversation cost splits roughly 1% patient / 14% assistant / **85% jury**. The
six rubric prompts total ~12k tokens before a transcript is added, and every jury
model re-reads all six on every conversation. That ratio is what makes the probe
worth staging.

### Stage 1 — manipulation check, generation only

4 arms × 8 cases × 3 turns = **32 conversations**, no evaluation.

| | |
|---|---|
| patient | $0.061 |
| assistant | $0.879 |
| jury | $0.000 |
| **total** | **$0.940** |

**Fits inside one day at the $2/day ceiling, with $1.06 to spare.** Run with
`patient-agent-bench generate` (through `python -m patientwords_pab.run`), then
read the patient turns. The register check is $0 and uses instruments this repo
already owns: the clinical-term lexicon and the readability report, over the
first-person patient utterances, low arm against high arm.

**Gate.** If the arms' patient language does not separate on register, stop. The
persona instruction is not driving the simulator, and no amount of jury spend will
make the sweep mean anything. Sunk cost at that point: **$0.94**.

### Stage 2 — outcome pilot

Extend to 4 arms × 13 cases = **52 conversations** and score them.

| | |
|---|---|
| generation (52 conversations) | $1.528 |
| jury (opus-4.8, six rubrics) | $8.476 |
| **total** | **$10.004** |
| incremental after stage 1 | $9.06 |

**$10.00 total, which is 6 days at the $2/day ceiling.** The ceiling is a daily
operational limit, not a total budget: a probe larger than it is scheduled, not
refused. `patient-agent-bench evaluate --run-dir` scores an existing run and the
runner caches conversations by signature, so stage 1's 32 conversations are reused
and the work splits across days without re-generating anything.

A note on the ceiling's mechanics: `scripts/fire_trigger.py` enforces $2/day over
this repo's CI triggers. A Bedrock probe does not pass through that guard, so the
limit has to be honoured by construction and recorded by hand in the session ledger
alongside the CI spend. That is a discipline gap the probe would introduce, and it
should be closed before the first fire rather than after.

### What the pilot buys an option on

| next step | conversations | cost | days at ceiling |
|---|---|---|---|
| second anchor: same sweep from `base=skeptical` (high-literacy preset) | 52 | $10.00 | 6 |
| second trait: `communication` sweep, same shape | 52 | $10.00 | 6 |
| powered single-trait study, n=32, two assistants | 256 | $46.24 | 24 |

The `base=skeptical` replication is the one that matters most: the same trait swept
from the opposite anchor. Same sign from both bases means the effect generalises
across personas; different signs mean it is persona-dependent, which is a finding
in itself and one the preset system could never have produced.

## Cost assumptions, stated so they can be attacked

- Token counts are characters ÷ 3.6, measured from the shipped artifacts on
  2026-08-04 (prompt templates, the 20-scenario sample's stories and profile XML,
  the 15 sandbox tool schemas, the six rubric prompts). `tiktoken` was unavailable —
  it fetches its encoding file over a network this sandbox blocks — so the divisor
  is a conservative estimate for prose mixed with XML and JSON, which tokenise
  denser than prose alone.
- 1.6 assistant model calls per turn (a tool call and an answer), 500 tokens of
  dialogue growth per turn, 200-token assistant replies, 100-token patient replies,
  150-token rubric verdicts. Deliberately generous; a probe that fits at these
  numbers fits at the real ones.
- Prices are AWS Bedrock on-demand list, matching the benchmark's own registry.
  They move; `PRICES` in `scripts/pab_probe_cost.py` is where to check.
- Retries and failed conversations are not modelled. Budget ~10% headroom.

## Decisions needed before a single call

1. Amendment or explicitly labelled exploratory arm — fixed in advance, not after
   seeing the result.
2. Where derived artifacts may land, given CC-BY-NC-4.0 on both their code and
   their data. Nothing derived should reach either public repo until that is settled.
3. Whether $10 across six days is the right use of the ceiling against the Tier B
   work already queued.
4. Bedrock credentials, and how their spend is journalled next to the CI ledger.
