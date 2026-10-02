# Advice lane fire plan, 2026-10-02 (for owner approval; nothing has been fired)

This plan runs the advice lane's next experiment in two waves, as proposed in
Amendment 6 of `docs/preregistration_advice.md`:

- **Wave A** asks the 24 new questions (`data/advice/stimuli_20261002T074150Z.json`)
  of each vendor's current model plus the Haiku cost floor.
- **Wave R** reruns the 15 earlier questions selected in
  `data/advice/rerun_selection_20261002.json`, with each vendor's original
  model beside its newest one.

Estimated cost for both waves: **$17.46 at measured response lengths** ($4.92
Anthropic, $12.54 OpenRouter) and **$26.10 in the high case** ($6.28 Anthropic,
$19.83 OpenRouter). The work is 17 fires over about four UTC days. Each fire
below gives its exact parameters, its billing lane, the cost arithmetic, a
runtime estimate, a $0 local plan check, the sentence that authorises it, and
its place in the order. Approving Amendment 6 does not authorise any fire.
Each fire runs only after the owner types its authorisation sentence with the
dollar figure in it.

## 0. Conditions that must all hold before the first fire

1. The pull request carrying this plan is merged, so the stimuli file, the
   probe file, the selection file and the proposed Amendment 6 are on `main`
   (the lane fires on `main`).
2. The owner has approved Amendment 6 in writing, and its approval record is
   filled.
3. The roster pull request (October 2026 roster: reviewed prices and
   per-model minimum `max_tokens`) is merged. Without it the spend meter
   prices `x-ai/grok-4.7` at the `xai` default of $1.32/$2.63 per million
   tokens (list $2/$6), `moonshotai/kimi-k3` at $0.63/$3.15 (list
   $2.70/$13.50) and `deepseek/deepseek-v4.1-flash` at $0.15/$0.30 (list
   output $0.75), so `max_spend` would not bound the bill. It would also price
   `claude-sonnet-5-5` at the $10/$50 fallback, five times its list price, so
   fire A1 would stop after about 41 of its 144 Sonnet calls. If the roster
   pull request sets per-model minimums other than 4096 for the three
   reasoning arms, the `max_tokens`, costs and `max_spend` of A0b, A3 and R3
   change; recompute them before approving those fires.
4. Wave R only: the selection-source pull request
   (`build-stimuli --source selection --selection <file>`) is merged, and the
   rerun stimuli file built from `data/advice/rerun_selection_20261002.json`
   is merged through a pull request. It must hold 15 items with unique ids,
   each item's messages byte for byte equal to the original (same
   `clinical_sha256` and `patient_sha256`). Check with the R1 plan check below:
   it must report 270 calls. Fewer means two items share an id
   (`pairs_20260706T201750Z#10` is selected twice, from two files), and
   `elicit` would treat the second as already done.
5. `python scripts/fire_trigger.py status` shows no active `advice-eval`
   entry, and the trigger is parked.

Fires are sent by the operator with
`python scripts/fire_trigger.py fire --trigger advice-eval --params-file <file holding the JSON below> --note "<fire id> of docs/advice_fire_plan_20261002.md"`,
one at a time: wait for each run to land, resolve it
(`python scripts/fire_trigger.py resolve --trigger advice-eval`), then wait out
the 15-minute settle window before the next fire. Never stack a second pending
fire. This session ran none of these commands.

## 1. Summary

| Fire | Lane | What | max_tokens | Calls | Typical | High | max_spend (commitment) | Runtime (min) | Day |
|---|---|---|---|---|---|---|---|---|---|
| A0a | OpenRouter | probe: gpt-chat-latest, grok-4.7 | 1024 | 2 | $0.019 | $0.025 | $0.10 | <1 | A-1 |
| A0b | OpenRouter | probe: gemini-3.8-flash, deepseek-v4.1-flash, kimi-k3 | 4096 | 3 | $0.026 | $0.048 | $0.15 | 2-3 | A-1 |
| A0c | Anthropic | probe: claude-sonnet-5-5 | 1024 | 1 | $0.006 | $0.007 | $0.05 | <1 | A-1 |
| A1 | Anthropic | new set: haiku-4-5, sonnet-5-5 | 1024 | 288 | $1.033 | $1.269 | $1.30 | 29-36 | A-1 |
| A3a | OpenRouter | new set items 1-8: gemini, deepseek, kimi | 4096 | 144 | $1.247 | $2.327 | $2.55 | 87-144 | A-1 |
| A3b | OpenRouter | new set items 9-16 | 4096 | 144 | $1.247 | $2.327 | $2.55 | 87-144 | A-1 |
| A3c | OpenRouter | new set items 17-24 | 4096 | 144 | $1.247 | $2.327 | $2.55 | 87-144 | A-2 |
| A2 | OpenRouter | new set: gpt-chat-latest, grok-4.7 | 1024 | 288 | $2.782 | $3.639 | $3.90 | 48-66 | A-2 |
| A4 | Anthropic | judge all 1008 Wave A responses | n/a | 0 + 1008 judgments | $1.129 | $1.613 | $0.01 + $1.80 = $1.81 | 42-67 | A-2 |
| R0a | OpenRouter | probe: the five original OpenRouter ids | 1024 | 5 | $0.021 | $0.027 | $0.10 | 1-2 | R-1 |
| R0b | Anthropic | probe: claude-sonnet-5 | 1024 | 1 | $0.009 | $0.011 | $0.05 | <1 | R-1 |
| R1 | Anthropic | rerun: haiku-4-5, sonnet-5, sonnet-5-5 | 1024 | 270 | $1.430 | $1.764 | $1.80 | 30-38 | R-1 |
| R2a | OpenRouter | rerun items 1-8: 7 models | 1024 | 336 | $1.926 | $2.529 | $2.80 | 83-135 | R-1 |
| R2b | OpenRouter | rerun items 9-15: 7 models | 1024 | 294 | $1.685 | $2.213 | $2.45 | 73-118 | R-1 |
| R3a | OpenRouter | rerun items 1-8: gemini, deepseek, kimi | 4096 | 144 | $1.247 | $2.327 | $2.55 | 87-144 | R-2 |
| R3b | OpenRouter | rerun items 9-15 | 4096 | 126 | $1.091 | $2.036 | $2.25 | 76-126 | R-2 |
| R4 | Anthropic | judge all 1170 Wave R responses | n/a | 0 + 1170 judgments | $1.310 | $1.613 | $0.01 + $1.80 = $1.81 | 49-78 | R-2 |

Totals: Wave A $8.74 typical ($2.17 Anthropic, $6.57 OpenRouter), $13.58 high;
Wave R $8.72 typical ($2.75 Anthropic, $5.97 OpenRouter), $12.52 high. The
probes (A0a, A0b, A0c, R0a, R0b) run against a separate one-item probe file
(section 3), so every full fire elicits all of its cells and each call is
counted once.

## 2. How the estimates were made

**Per-response cost.** For the July arms, "typical" is the measured mean cost
per response in `data/advice/responses_*.jsonl` (OpenRouter's own bill,
`response_raw.usage.cost`, where it exists; the meter's figure for Anthropic).
For new arms, cost = mean input tokens x input price + output tokens x output
price, at the October list prices (OpenRouter catalogue of 2026-10-01; per
million tokens), with the token counts of the arm's July predecessor. "High"
uses the predecessor's 90th-percentile output length. For the three reasoning
arms at 4096 tokens nothing measured applies (their predecessors were cut off
at 1024), so typical assumes 2000, 1100 and 1300 output tokens and high 3500,
2000 and 2500. Those six numbers are guesses; the A0b probe gives the first
measurements.

| Arm | Input tok | Output tok (typical / high) | Price in / out ($/M) | Typical $/response | High $/response |
|---|---|---|---|---|---|
| anthropic:claude-haiku-4-5 | 42 | 264 / 315 | 1 / 5 | 0.00136 (measured) | 42x1 + 315x5 = 0.00162 |
| anthropic:claude-sonnet-5 | 47 | 572 / 710 | 3 / 15 (meter) | 0.00872 (measured) | 47x3 + 710x15 = 0.01079 |
| anthropic:claude-sonnet-5-5 | 47 | 572 / 710 | 2 / 10 | 47x2 + 572x10 = 0.00581 | 0.00719 |
| openai:openai/gpt-5.5 | 34 | 488 / 654 | 5 / 30 | 0.01480 (measured) | 0.01979 |
| openai:openai/gpt-5.4-mini | 34 | 330 / 449 | 0.75 / 4.5 | 0.00151 (measured) | 0.00205 |
| openai:openai/gpt-chat-latest | 34 | 488 / 654 | 5 / 30 | 34x5 + 488x30 = 0.01481 | 0.01979 |
| xai:x-ai/grok-4.3 | 216 | 679 / 842 | 1.25 / 2.5 | 0.00180 (measured) | 0.00237 |
| xai:x-ai/grok-4.7 | 216 | 679 / 842 | 2 / 6 | 216x2 + 679x6 = 0.00451 | 0.00548 |
| deepseek:deepseek/deepseek-v4-flash | 33 | 792 / 1025 | 0.15 / 0.3 | 0.00020 (measured) | 0.00031 |
| deepseek:deepseek/deepseek-v4.1-flash | 33 | 1100 / 2000 | 0.03 / 0.75 | 33x0.03 + 1100x0.75 = 0.00083 | 0.00150 |
| moonshot:moonshotai/kimi-k2.5 | 33 | 990 / 1275 | 0.45 / 2.25 | 0.00249 (measured) | 0.00288 |
| moonshot:moonshotai/kimi-k3 | 33 | 1300 / 2500 | 2.7 / 13.5 | 33x2.7 + 1300x13.5 = 0.01764 | 0.03384 |
| openrouter:google/gemini-3.8-flash | 28 | 2000 / 3500 | 0.75 / 3.75 | 28x0.75 + 2000x3.75 = 0.00752 | 0.01315 |

(Products in the formulas are in millionths of a dollar: 572 x 10 means 572
tokens at $10 per million, $0.00572.)

**Judge.** The Haiku judge's measured cost is $0.00112 per judgment (0.102289 /
91 in `judgments_stimuli_20260722T003502Z.report.json`). Responses from the
three 4096-token arms will be longer, so the high case charges them $0.00224.
Wave A: 1008 judgments = 576 short + 432 long; typical 1008 x 0.00112 = $1.129,
high 576 x 0.00112 + 432 x 0.00224 = $1.613. Wave R: 1170 = 900 + 270; typical
$1.310, high $1.613. `judge_max_spend` is the high case plus 10%, rounded up to
$0.05: $1.80 for both.

**max_spend.** The meter stops a fire before any call whose worst case (400
input tokens and the full `max_tokens` of output, at the registry rate) would
take spending past `max_spend`. Each fire's `max_spend` is the metered high
case plus one worst-case call, rounded up to $0.05. The meter rates assumed
are the roster pull request's reviewed prices (list x 1.06 for OpenRouter
slugs, as the existing entries are; list for Anthropic) and today's registry
rates for the July arms. Worst-case calls: $0.0347 for gpt-chat-latest at
1024 (400 x 5.3 + 1024 x 31.8), $0.0598 for kimi-k3 at 4096 (400 x 2.862 +
4096 x 14.31), $0.0110 for sonnet-5-5 and $0.0166 for sonnet-5 at 1024.

**Runtime.** Elicitation is sequential, and the job limit is 300 minutes.
Typical uses each arm's mean latency in the archives, high its 90th
percentile (seconds per call: haiku 3.7/4.5, sonnet 8.3/10.3, gpt-5.5 and
gpt-chat-latest 12.1/16.4, gpt-5.4-mini 4.9/7.9, grok 7.7/11.2,
deepseek-v4-flash 31.2/62.1, kimi-k2.5 28.0/43.6). The new reasoning arms at
4096 are assumed 1.5 times their predecessor (deepseek-v4.1-flash 46.8/93.2,
kimi-k3 42.0/65.4), and gemini-3.8-flash 20/22, because the July Gemini
latencies were cut short at 1024. Every fire's high case stays under 150
minutes, half the limit, which is why A3, R2 and R3 are split by
`offset`/`limit`.

## 3. The fires

Every fire uses arms `clinical,patient` (probes: `clinical` only),
temperature 1.0 (the workflow default), the default rubric
`data/advice_rubric.draft.json`, and `commit_outputs: "true"`. In fires with
`judge: "false"`, `judge_model` and `judge_max_spend` are not used. The plan
check is `scripts/advice_eval.py elicit --dry-run` with the same arguments; it
calls nothing and writes nothing. The outputs below were run on this branch
on 2026-10-02, before any record exists.

**The probe file.** The five probes (A0a, A0b, A0c, R0a, R0b) do not run
against a stimuli file that is analysed. They run against
`data/advice/stimuli_20261002T074159Z.json`, a one-item file built with the
same command from `data/advice/manual_probe_20261002.json`; its one item,
`advprobe_20261002#01`, repeats the messages of item #01 of the new set. The
probes write `data/advice/responses_stimuli_20261002T074159Z.jsonl` and its
cost sidecar, which commit like any other archive (so the ledger books the
probes' spend), and that archive is never judged, analysed, exported or pooled
with any set. The reason: `elicit` resumes by (stimulus, arm, model, sample)
and not by `max_tokens`, so a probe record inside an analysed archive would
make the full fire skip that cell even if the arm's limit changed after the
probe, leaving one sample of the arm at the old limit and inside its
truncation share. A probe with `commit_outputs: "false"` would also stay out
of the analysed archive, but it commits no cost sidecar, so
`scripts/ledger_update.py` would never book its spend, and its uploaded
artifact is what a `restore_artifact_run_id` recovery fire merges into the
stimuli file that fire names.

### Wave A: the 24 new questions

Order: A0a, A0b, A0c, A1, A3a, A3b (day A-1), then A3c, A2, A4 (day A-2);
section 4 gives the reason for this order. After each probe, look at its
landed records in `data/advice/responses_stimuli_20261002T074159Z.jsonl`
before the next fire: `stop_reason` (a length stop on a probe means the limit
is too low for that arm), `model_returned` (which build the slug resolved to;
for `gpt-chat-latest` this is the build the alias served) and
`request.max_tokens` (the limit the call was sent with). If a probe fails with
a 400, that id is wrong or not served: drop it from every later fire of this
plan and record the drop in Amendment 6 before going on. If a probe leads to a
different `max_tokens` for an arm, that is a new decision, recorded in
Amendment 6 before the arm's full fire; because the probe record is not in the
new set's archive, the full fire then elicits every one of its cells at the
new limit.

**A0a. Probe, OpenRouter 1024 arms.** OpenRouter lane, bills
`OPENROUTER_API_KEY`. 2 calls (the probe item, clinical, k=1).
```json
{"stimuli_file": "data/advice/stimuli_20261002T074159Z.json", "models": "openai:openai/gpt-chat-latest xai:x-ai/grok-4.7", "arms": "clinical", "samples": "1", "max_tokens": "1024", "max_spend": "0.10", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "1", "commit_outputs": "true"}
```
Cost: 0.01481 + 0.00451 = $0.019 (high $0.025). Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074159Z.json --models "openai:openai/gpt-chat-latest xai:x-ai/grok-4.7" --arms clinical --samples 1 --max-tokens 1024 --max-spend 0.10 --offset 0 --limit 1 --dry-run`
→ `plan: 2 call(s) over 1 stimuli x arms ['clinical'] x models ['openai:openai/gpt-chat-latest', 'xai:x-ai/grok-4.7'] x K=1`.
Authorise: "I authorise fire A0a of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $0.10, on <YYYY-MM-DD> UTC."

**A0b. Probe, OpenRouter 4096 arms.** OpenRouter lane. 3 calls.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074159Z.json", "models": "openrouter:google/gemini-3.8-flash deepseek:deepseek/deepseek-v4.1-flash moonshot:moonshotai/kimi-k3", "arms": "clinical", "samples": "1", "max_tokens": "4096", "max_spend": "0.15", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "1", "commit_outputs": "true"}
```
Cost: 0.00752 + 0.00083 + 0.01764 = $0.026 (high $0.048). Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074159Z.json --models "openrouter:google/gemini-3.8-flash deepseek:deepseek/deepseek-v4.1-flash moonshot:moonshotai/kimi-k3" --arms clinical --samples 1 --max-tokens 4096 --max-spend 0.15 --offset 0 --limit 1 --dry-run`
→ `plan: 3 call(s) over 1 stimuli x arms ['clinical'] x models [...3 models...] x K=1`.
The output-token counts of these three records replace the guesses in
section 2; recompute A3 and R3 if any is above 3500.
Authorise: "I authorise fire A0b of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $0.15, on <YYYY-MM-DD> UTC."

**A0c. Probe, claude-sonnet-5-5.** Anthropic lane, bills `ANTHROPIC_API_KEY`.
1 call. It also shows whether the model accepts the `temperature` the advice
path sends.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074159Z.json", "models": "anthropic:claude-sonnet-5-5", "arms": "clinical", "samples": "1", "max_tokens": "1024", "max_spend": "0.05", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "1", "commit_outputs": "true"}
```
Cost: $0.006 (high $0.007). Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074159Z.json --models "anthropic:claude-sonnet-5-5" --arms clinical --samples 1 --max-tokens 1024 --max-spend 0.05 --offset 0 --limit 1 --dry-run`
→ `plan: 1 call(s) over 1 stimuli x arms ['clinical'] x models ['anthropic:claude-sonnet-5-5'] x K=1`.
Authorise: "I authorise fire A0c of docs/advice_fire_plan_20261002.md: advice-eval, Anthropic lane, max_spend $0.05, on <YYYY-MM-DD> UTC."

**A1. Anthropic arms.** Anthropic lane. 288 calls.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074150Z.json", "models": "anthropic:claude-haiku-4-5 anthropic:claude-sonnet-5-5", "arms": "clinical,patient", "samples": "3", "max_tokens": "1024", "max_spend": "1.30", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "0", "commit_outputs": "true"}
```
Cost: 144 x 0.00136 + 144 x 0.00581 = 0.196 + 0.837 = $1.033; high 144 x
0.00162 + 144 x 0.00719 = $1.269; max_spend $1.269 + $0.011 → $1.30. Runtime
144 x (3.7 + 8.3) s = 29 min; high 36 min. Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074150Z.json --models "anthropic:claude-haiku-4-5 anthropic:claude-sonnet-5-5" --arms clinical,patient --samples 3 --max-tokens 1024 --max-spend 1.30 --dry-run`
→ `plan: 288 call(s) over 24 stimuli x arms ['clinical', 'patient'] x models ['anthropic:claude-haiku-4-5', 'anthropic:claude-sonnet-5-5'] x K=3`.
Authorise: "I authorise fire A1 of docs/advice_fire_plan_20261002.md: advice-eval, Anthropic lane, max_spend $1.30, on <YYYY-MM-DD> UTC."

**A2. OpenRouter 1024 arms.** OpenRouter lane. 288 calls.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074150Z.json", "models": "openai:openai/gpt-chat-latest xai:x-ai/grok-4.7", "arms": "clinical,patient", "samples": "3", "max_tokens": "1024", "max_spend": "3.90", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "0", "commit_outputs": "true"}
```
Cost: 144 x 0.01481 + 144 x 0.00451 = 2.133 + 0.649 = $2.782; high 144 x
0.01979 + 144 x 0.00548 = $3.639; metered high $3.858 + $0.0347 → $3.90.
Runtime 144 x (12.1 + 7.7) s = 48 min; high 66 min. Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074150Z.json --models "openai:openai/gpt-chat-latest xai:x-ai/grok-4.7" --arms clinical,patient --samples 3 --max-tokens 1024 --max-spend 3.90 --dry-run`
→ `plan: 288 call(s) over 24 stimuli x arms ['clinical', 'patient'] x models ['openai:openai/gpt-chat-latest', 'xai:x-ai/grok-4.7'] x K=3`.
Authorise: "I authorise fire A2 of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $3.90, on <YYYY-MM-DD> UTC."

**A3a, A3b, A3c. OpenRouter 4096 arms, eight items each.** OpenRouter lane.
144 calls each. The three differ only in `offset` (0, 8, 16).
```json
{"stimuli_file": "data/advice/stimuli_20261002T074150Z.json", "models": "openrouter:google/gemini-3.8-flash deepseek:deepseek/deepseek-v4.1-flash moonshot:moonshotai/kimi-k3", "arms": "clinical,patient", "samples": "3", "max_tokens": "4096", "max_spend": "2.55", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "8", "commit_outputs": "true"}
```
(A3b: `"offset": "8"`; A3c: `"offset": "16"`.) Cost per chunk: 48 x 0.00752 +
48 x 0.00083 + 48 x 0.01764 = 0.361 + 0.040 + 0.847 = $1.247; high 48 x
(0.01315 + 0.00150 + 0.03384) = $2.327; metered high $2.467 + $0.0598 →
$2.55. Runtime 48 x (20 + 46.8 + 42.0) s = 87 min; high 48 x (22 + 93.2 +
65.4) s = 144 min. Plan check (offset 0, 8 and 16):
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074150Z.json --models "openrouter:google/gemini-3.8-flash deepseek:deepseek/deepseek-v4.1-flash moonshot:moonshotai/kimi-k3" --arms clinical,patient --samples 3 --max-tokens 4096 --max-spend 2.55 --offset 0 --limit 8 --dry-run`
→ `plan: 144 call(s) over 8 stimuli x arms ['clinical', 'patient'] x models [...3 models...] x K=3` for each of the three offsets.
Authorise (one per chunk): "I authorise fire A3a of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $2.55, on <YYYY-MM-DD> UTC." (and the same for A3b and A3c).

**A4. Judge Wave A.** Anthropic lane: its `models` is the Haiku arm, already
complete after A1, so its elicitation plans 0 calls and the fire guard books
the judge's Anthropic spend on the Anthropic lane. The judge step judges every
response in `responses_stimuli_20261002T074150Z.jsonl` (all seven models),
then runs `analyze`. Run it after A2, the last Wave A elicitation, lands.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074150Z.json", "models": "anthropic:claude-haiku-4-5", "arms": "clinical,patient", "samples": "3", "max_tokens": "1024", "max_spend": "0.01", "judge": "true", "judge_model": "claude-haiku-4-5", "judge_max_spend": "1.80", "offset": "0", "limit": "0", "commit_outputs": "true"}
```
Cost: section 2, typical $1.129, high $1.613; commitment $0.01 + $1.80 =
$1.81. Runtime 1008 judgments at 2.5-4 s: 42-67 min. Plan checks (both must
pass before firing):
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074150Z.json --models "anthropic:claude-haiku-4-5" --arms clinical,patient --samples 3 --max-tokens 1024 --max-spend 0.01 --dry-run`
must print `plan: 0 call(s)` once A1 has landed (on this branch today it
prints 144, because nothing is archived yet), and
`python scripts/advice_eval.py judge --responses data/advice/responses_stimuli_20261002T074150Z.jsonl --rubric data/advice_rubric.draft.json --judge-model claude-haiku-4-5 --judge-max-tokens 300 --max-spend 1.80 --dry-run`
must print `judging 1008 response(s)` (today: `judging 0 response(s)`, no
archive yet). A different number means an elicitation fire stopped early or a
record failed; stop and look before judging.
Authorise: "I authorise fire A4 of docs/advice_fire_plan_20261002.md: advice-eval judge pass, Anthropic lane, max_spend $0.01 and judge_max_spend $1.80, on <YYYY-MM-DD> UTC."

### Wave R: the 15 selected earlier questions

`<RERUN>` below is the rerun stimuli file from condition 4, for example
`data/advice/stimuli_<stamp>.json`. It does not exist on this branch, so the
plan checks of R1 to R4 were run against a 15-item placeholder file in the
session's scratch directory (placeholder text, same item count), which
confirms that every model spec resolves and gives the counts. Rerun those
checks on `<RERUN>` before approving; the counts must match. The two probes
run against the probe file, not `<RERUN>`, so their checks below are real.

Order: R0a, R0b, R1, R2a, R2b, R3a, R3b, R4. The original arms run at 1024
tokens, the July protocol. The reasoning arms run at 4096 (Amendment 6,
A6.2). Read each probe's records as after the Wave A probes.

**R0a. Probe, the original OpenRouter ids.** OpenRouter lane. 5 calls. These
ids have not been called since August.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074159Z.json", "models": "openai:openai/gpt-5.5 openai:openai/gpt-5.4-mini xai:x-ai/grok-4.3 deepseek:deepseek/deepseek-v4-flash moonshot:moonshotai/kimi-k2.5", "arms": "clinical", "samples": "1", "max_tokens": "1024", "max_spend": "0.10", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "1", "commit_outputs": "true"}
```
Cost: 0.01480 + 0.00151 + 0.00180 + 0.00020 + 0.00249 = $0.021 (high $0.027).
Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074159Z.json --models "openai:openai/gpt-5.5 openai:openai/gpt-5.4-mini xai:x-ai/grok-4.3 deepseek:deepseek/deepseek-v4-flash moonshot:moonshotai/kimi-k2.5" --arms clinical --samples 1 --max-tokens 1024 --max-spend 0.10 --offset 0 --limit 1 --dry-run`
→ `plan: 5 call(s) over 1 stimuli x arms ['clinical'] x models [...5 models...] x K=1`.
Authorise: "I authorise fire R0a of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $0.10, on <YYYY-MM-DD> UTC."

**R0b. Probe, claude-sonnet-5.** Anthropic lane. 1 call.
```json
{"stimuli_file": "data/advice/stimuli_20261002T074159Z.json", "models": "anthropic:claude-sonnet-5", "arms": "clinical", "samples": "1", "max_tokens": "1024", "max_spend": "0.05", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "1", "commit_outputs": "true"}
```
Cost $0.009 (high $0.011). Plan check:
`python scripts/advice_eval.py elicit --stimuli data/advice/stimuli_20261002T074159Z.json --models "anthropic:claude-sonnet-5" --arms clinical --samples 1 --max-tokens 1024 --max-spend 0.05 --offset 0 --limit 1 --dry-run`
→ `plan: 1 call(s) over 1 stimuli x arms ['clinical'] x models ['anthropic:claude-sonnet-5'] x K=1`.
Authorise: "I authorise fire R0b of docs/advice_fire_plan_20261002.md: advice-eval, Anthropic lane, max_spend $0.05, on <YYYY-MM-DD> UTC."

**R1. Anthropic arms.** Anthropic lane. 270 calls.
```json
{"stimuli_file": "<RERUN>", "models": "anthropic:claude-haiku-4-5 anthropic:claude-sonnet-5 anthropic:claude-sonnet-5-5", "arms": "clinical,patient", "samples": "3", "max_tokens": "1024", "max_spend": "1.80", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "0", "commit_outputs": "true"}
```
Cost: 90 x 0.00136 + 90 x 0.00872 + 90 x 0.00581 = 0.122 + 0.785 + 0.523 =
$1.430; high 90 x (0.00162 + 0.01079 + 0.00719) = $1.764; max_spend $1.764 +
$0.0166 → $1.80. Runtime 90 x (3.7 + 8.3 + 8.3) s = 30 min; high 38 min.
Plan check → `plan: 270 call(s) over 15 stimuli x arms ['clinical', 'patient'] x models ['anthropic:claude-haiku-4-5', 'anthropic:claude-sonnet-5', 'anthropic:claude-sonnet-5-5'] x K=3`.
Authorise: "I authorise fire R1 of docs/advice_fire_plan_20261002.md: advice-eval, Anthropic lane, max_spend $1.80, on <YYYY-MM-DD> UTC."

**R2a and R2b. OpenRouter 1024 arms, original and newest.** OpenRouter lane.
R2a: items 1-8, 336 calls. R2b: items 9-15, 294.
```json
{"stimuli_file": "<RERUN>", "models": "openai:openai/gpt-5.5 openai:openai/gpt-5.4-mini xai:x-ai/grok-4.3 deepseek:deepseek/deepseek-v4-flash moonshot:moonshotai/kimi-k2.5 openai:openai/gpt-chat-latest xai:x-ai/grok-4.7", "arms": "clinical,patient", "samples": "3", "max_tokens": "1024", "max_spend": "2.80", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "8", "commit_outputs": "true"}
```
(R2b: `"offset": "8"`, `"limit": "7"`, `"max_spend": "2.45"`.) Cost R2a: 48 x
(0.01480 + 0.00151 + 0.00180 + 0.00020 + 0.00249 + 0.01481 + 0.00451) = 48 x
0.04012 = $1.926; high $2.529; metered high $2.716 + $0.0347 → $2.80. R2b:
42 x 0.04012 = $1.685; high $2.213; metered high $2.376 + $0.0347 → $2.45.
Runtime per item-arm-sample 103.7 s typical, 168.8 s high: R2a 83-135 min,
R2b 73-118 min. Plan checks → `plan: 336 call(s) over 8 stimuli ...` and
`plan: 294 call(s) over 7 stimuli ...`.
Authorise: "I authorise fire R2a of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $2.80, on <YYYY-MM-DD> UTC." and "I authorise fire R2b ...: max_spend $2.45 ...".

**R3a and R3b. OpenRouter 4096 arms.** OpenRouter lane. R3a items 1-8, 144
calls; R3b items 9-15, 126.
```json
{"stimuli_file": "<RERUN>", "models": "openrouter:google/gemini-3.8-flash deepseek:deepseek/deepseek-v4.1-flash moonshot:moonshotai/kimi-k3", "arms": "clinical,patient", "samples": "3", "max_tokens": "4096", "max_spend": "2.55", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01", "offset": "0", "limit": "8", "commit_outputs": "true"}
```
(R3b: `"offset": "8"`, `"limit": "7"`, `"max_spend": "2.25"`.) Cost R3a as
A3a: $1.247, high $2.327, max_spend $2.55. R3b: 42 x 0.02599 = $1.091; high
42 x 0.04849 = $2.036; metered high $2.159 + $0.0598 → $2.25. Runtime R3a
87-144 min, R3b 76-126 min. Plan checks → `plan: 144 call(s) over 8 stimuli ...`
and `plan: 126 call(s) over 7 stimuli ...`.
Optional (owner decision, not costed above): add
`openrouter:google/gemini-3.5-flash` to R3a and R3b so the Gemini arm has a
non-truncated original beside 3.8; at its list price of $1.50/$9.00 and 2000
output tokens that is about 90 x $0.018 = $1.62 more.
Authorise: "I authorise fire R3a of docs/advice_fire_plan_20261002.md: advice-eval, OpenRouter lane, max_spend $2.55, on <YYYY-MM-DD> UTC." and "I authorise fire R3b ...: max_spend $2.25 ...".

**R4. Judge Wave R.** Anthropic lane, as A4. Run after R3b lands.
```json
{"stimuli_file": "<RERUN>", "models": "anthropic:claude-haiku-4-5", "arms": "clinical,patient", "samples": "3", "max_tokens": "1024", "max_spend": "0.01", "judge": "true", "judge_model": "claude-haiku-4-5", "judge_max_spend": "1.80", "offset": "0", "limit": "0", "commit_outputs": "true"}
```
Cost: typical $1.310, high $1.613; commitment $1.81. Runtime 49-78 min. Plan
checks: `elicit --dry-run` with these arguments must print `plan: 0 call(s)`
after R1 has landed, and `judge --dry-run` on `<RERUN>`'s responses file must
print `judging 1170 response(s)`.
Authorise: "I authorise fire R4 of docs/advice_fire_plan_20261002.md: advice-eval judge pass, Anthropic lane, max_spend $0.01 and judge_max_spend $1.80, on <YYYY-MM-DD> UTC."

## 4. Days and the daily ceilings

The fire guard (`budget_check` in `scripts/fire_trigger.py`) refuses a fire
when its commitment plus the day's committed spend on its lane exceeds the
ceiling. The day's committed spend has two terms:

- **held**: the `max_spend` (plus `judge_max_spend` for a judged fire) of
  every fire sent that UTC day on the lane, landed or failed, resolved or not;
- **landed**: the lane's `spend.today` figure in `ops/dashboard.json`, which
  is non-zero once `scripts/ledger_update.py` (run by the daily Routine) has
  folded that day's landed cost sidecars. The ledger books each sidecar to
  its own run day, so a fold never moves one day's cost onto another day.

The two overlap on purpose: once the ledger has folded a fire, that fire
counts twice for the rest of its day (AGENTS.md). So the plan is checked
against the worst case: before each fire, every earlier fire of the same day
and lane has landed at its high cost and been folded. The Anthropic lane
allows $2 a day unless the owner dates an override in
`ops/budget_overrides.json`; an OpenRouter-only fire counts against $10 a
day.

| Day | Lane | Fires in order | Held after the last fire | Worst-case landed before the last fire | Worst case |
|---|---|---|---|---|---|
| A-1 | Anthropic | A0c, A1 | 0.05 + 1.30 = $1.35 | A0c 0.007 | $1.36 |
| A-1 | OpenRouter | A0a, A0b, A3a, A3b | 0.10 + 0.15 + 2.55 + 2.55 = $5.35 | 0.025 + 0.048 + 2.327 = $2.40 | $7.75 |
| A-2 | OpenRouter | A3c, A2 | 2.55 + 3.90 = $6.45 | A3c 2.327 | $8.78 |
| A-2 | Anthropic | A4 | $1.81 | none | $1.81 |
| R-1 | Anthropic | R0b, R1 | 0.05 + 1.80 = $1.85 | R0b 0.011 | $1.86 |
| R-1 | OpenRouter | R0a, R2a, R2b | 0.10 + 2.80 + 2.45 = $5.35 | 0.027 + 2.529 = $2.56 | $7.91 |
| R-2 | OpenRouter | R3a, R3b | 2.55 + 2.25 = $4.80 | R3a 2.327 | $7.13 |
| R-2 | Anthropic | R4 | $1.81 | none | $1.81 |

Every day stays under both ceilings in the worst case, with no override.
An earlier draft of this plan put A2 and A3a on day A-1 after A0a and A0b:
held $6.70, and with A0a, A0b and A2 landed at their high cost and folded
before A3a, $6.70 + $3.71 = $10.41, over the $10 ceiling. Hence the order
above, with A2 last on day A-2 (A3c before A2: the other way round,
$6.45 + $3.64 = $10.09 would also exceed it). Do not move a fire to another
day without redoing this column; before each fire,
`python scripts/fire_trigger.py status` shows the guard's own landed and held
figures.

Each judge fires on the Anthropic lane after the last elicitation of its
wave. The queue is one per branch for all `advice-eval` fires, whatever their
lane, so a day's fires run one after another: day A-1 is about four and a
half to seven hours including the 15-minute settle windows (high case: A0a 1,
A0b 3, A0c 1, A1 36, A3a 144, A3b 144 minutes, five settle windows), day A-2
about three and a half to five hours (high case: A3c 144, A2 66, A4 67
minutes, two settle windows). A chain that crosses
00:00 UTC books its later fires on the next day; check `fire_trigger.py
status` before each fire. Wave R starts only after condition 4 holds, which
can be days after Wave A.

**Re-park.** When a day's chain pauses and after the last fire of each wave
(A4, R4) lands and is resolved, re-park the lane:
`python scripts/fire_trigger.py park --trigger advice-eval`. The park default
elicits over fully covered cells of `stimuli_20260827T141036Z` (0 calls,
`max_spend` $0.01, journaled on the Anthropic lane).

## 5. If something goes wrong

- A probe returns a 400: the id is wrong or retired. Drop it from the later
  fires, record the drop in Amendment 6, and do not substitute a different
  model without the owner's decision.
- A model has to be probed again (for example at a raised `max_tokens`): fire
  it on the probe file with `samples` one above that model's highest
  `sample_k` in the probe archive, because `elicit` skips the (stimulus, arm,
  model, k) cells already archived. Each record's `request.max_tokens` says
  which limit it was sent with.
- A fire stops early on its `max_spend` (`stopped_reason` in the responses
  sidecar): do not raise `max_spend` on the same day. The same parameters
  fired again resume past the archived cells, but that is a new fire and needs
  a new authorisation for the remaining spend.
- A fire dies on an error: the archive keeps what landed and the next fire
  resumes. Its commitment still counts for the rest of that UTC day.
- More than 5% of a newest arm's responses stop at the token limit: report
  the arm as truncated and keep it out of per-model comparisons (Amendment 6,
  A6.2 rule 1); raising its limit is a new decision. The original DeepSeek
  v4-flash and Kimi k2.5 arms at 1024 are exempt (A6.2 rule 2): report their
  share and keep them in.

## 6. After the waves land ($0, local)

- Reference scoring for Wave A, exploratory only:
  `python scripts/advice_eval.py analyze --judgments data/advice/judgments_stimuli_20261002T074150Z.jsonl --rubric data/advice_rubric.draft.json --stimuli data/advice/stimuli_20261002T074150Z.json --out <scratch path>`.
  Its `reference_scoring` uses non-claim-grade tiers, carries
  `claim_grade: false` with all 24 ids in `not_adjudicated_ids`, and is
  reported as exploratory.
- The replication readout for Wave R compares, per original (stimulus, model)
  cell, the rerun downgrade against the original one (archives of July and
  August 2026) and against the null expectation recorded per cell in
  `data/advice/rerun_selection_20261002.json`. Over the 87 re-elicitable
  cells (the 88 less `openrouter:stealth/ox-alpha` on item #7, which is not
  re-elicited) the original count is 36 against 17.3 expected under the null;
  the pre-specified sensitivity without DeepSeek v4-flash and Kimi k2.5 is 23
  over 59 cells against 9.9 (Amendment 6, A6.4). Both readings are reported.
- The probe archive, `data/advice/responses_stimuli_20261002T074159Z.jsonl`,
  is in neither readout and is never judged or exported, and no truncation
  share counts it. `scripts/referral_destination.py` reads every
  `responses_stimuli_*` archive but builds its cells from judgments, so the
  unjudged probe records appear only in its list of input files and its count
  of indexed responses, never in an estimate.
- Before anything reaches the site: the vendor packs (Amendment 6, A6.7);
  `scripts/export_advice_scenarios.py` with `--rubric data/advice_rubric.draft.json`
  (its default rubric path does not exist, which is why the published payload
  has `tier_order` null); and two exporter limits that affect these files. The
  exporter labels a stimuli file "natural_questions" only when its
  `source.paths` names an `advnat_` batch, so the manual-source new set would
  be labelled "sentence_completions". It also groups samples by stimulus id
  across every file in one export call, so a rerun file that keeps the
  original ids must never be exported in the same call as the files it was
  selected from.

## 7. Decisions for the owner

1. Approve, change or reject Amendment 6 (it is proposed, not in force).
2. Each fire, by its authorisation sentence and dollar figure.
3. Moonshot arm: `kimi-k3` ($2.70/$13.50, costed here) or the cheaper
   `kimi-k2.6` ($0.434/$1.83). k2.6 would cut about $3.57 from the typical
   total (234 responses at $0.0176 against about $0.0024).
4. Whether to add the optional `gemini-3.5-flash` arm to R3 (about $1.62).
5. For the selected situation that appears twice (`pairs_20260706T201750Z#10`,
   ranks 2 and 13), keep both forms (as costed) or drop one.
