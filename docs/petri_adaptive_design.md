# The adaptive-auditor lane: Petri used the way Anthropic scoped it, for exploration

Status: built 2026-09-26 under the owner's authorization of 2026-09-25 (about 21:15 EDT), verbatim: "lets explictly
raise it to $30, you have been a great partner on this so i trust you to set this up overnight while i am asleep and
to dillegently puruse this experiement in parallell as the other experiments run". **Exploratory by construction.**
Nothing here changes, reruns or is pooled with the pre-registered wave-2 analysis (design note section 10), whose
result is final.

## Why

Anthropic built Petri so an AI auditor improvises each conversation, adapting to what the model says, and a judge
flags the transcripts worth reading. Wave 2 used Petri differently: every user turn was scripted, so the three
wordings received identical treatment, which is what a registered register contrast needs. The price is that the
scripted user cannot respond to the model. Two registered hypotheses need a user who can (H2, asymmetric
sycophancy; H6, correction after contradictory evidence), and a scripted conversation cannot show whether the
wording effect survives a person who answers the model's questions. This lane asks that question, as exploration.

## What it does

- **Seeds** (`docs/framework/petri_seeds_adaptive.draft.json`, derived by
  `python -m scripts.petri_audit.cli build-adaptive-seeds`, never edited by hand): one autonomous copy of each
  unbranched wave-2 seed, `pw-petri-w2a-*`, with the casual (`colloquial`) and clinical arms only. Same scenario,
  texts, tools and generation block as the scripted seed. 8 seeds, 20 conditions per pass.
- **Turn 1** is the arm's own stimulus, staged from the seed exactly as the scripted controller stages it.
- **Turns 2..N** are written by the model bound to the `auditor` role (`auditor_model`), from
  `docs/framework/auditor_prompts/adaptive_user.draft.json`: the arm's scripted user turns as a numbered agenda in the
  arm's own register, the arm's register directive, and the conversation the person has seen (the model's visible
  replies; tool traffic is not shown to the person). It answers the model's questions from the agenda, pushes back
  where the agenda does, and moves through the agenda one point per message. The two arms' instructions differ only
  by the agenda and the register directive (tested).
- **Tools** are answered from the seed's results table, as in wave 2; the auditor has no tools at all.
- **The judge** grades every reply on the advice tier (response only and in context) and classifies every user turn
  under `docs/framework/judge_prompts/register.draft.json`: the manipulation check. Turn 1's rows measure the
  classifier on a known label; turns 2..N measure whether the auditor kept the arm's register.
- **The control**: each condition runs for several epochs, so two independent casual conversations can be compared
  with each other exactly as a casual one is compared with a clinical one. Differences between same-wording pairs are
  the noise the auditor alone produces (the negative-control logic of 2026-09-04).

## Why not Petri's own auditor

Petri's auditor tool `send_message` asks the auditor for typos and informal language (design memo section 2), which
is the manipulation this study varies; its other tools can set a system prompt, author tool results, prefill, roll
back or end the conversation, and two auditor-facing strings cannot be replaced by any parameter (section 12). The
lane instead passes a custom Agent to `audit_solver`, Petri's documented extension path, which calls the auditor
model directly with instructions held as data. This covers the adaptive half of Petri's design; Petri's
whole-conversation judge (`audit_judge`) is not attached, and the realism approver applies only to Petri's own
auditor loop, so realism rests on the agenda being the study's real stimuli and on the register check.

## Integrity and spend

- The adapter recomputes turns 2..N from the auditor's own logged outputs under the one text rule
  (`adaptive.auditor_turn_text`: surrounding whitespace removed) and runs every existing stimulus check on the result
  (`adaptive.effective_seed`), so it proves the target received exactly what the auditor wrote.
- An empty or unfinished auditor answer stops the conversation with a recorded limit, and the tree is refused.
- The auditor's calls are counted and priced under their own role (`usage.by_role`); a call without usage is never
  priced as zero. They count against the same per-sample token and cost limits and `max_spend` as the target's, and
  the pre-flight bound prices every token at the dearer model's rate (`spend.dearest_price`).
- The auditor bills the target's channel (the params job, `cli preflight` and `fire_trigger.py` all refuse a mixed
  fire), so the fire's lane and commitment are the target's.
- The manifest records `execution.mode: autonomous`, `models.auditor`, and
  `execution.auditor_instruction_sha256` (the prompt file's digest; each sample's rendered system message is digested
  on the controller's condition event). The export seal scan covers the auditor's turns.
- **Budget**: $30 for the lane in total, owner-authorized, recorded for UTC 2026-09-26 in `ops/budget_overrides.json`
  (the anthropic lane; no other fire on that lane is planned that day). Commitments are worst cases, so the spend
  itself will be well below them.

## Plan (UTC 2026-09-26)

1. `dry_run` at $0 in CI: mock target and mock auditor through the whole job.
2. A small paid pilot (Claude Haiku 4.5 as auditor, target and judge; 2 seeds, 4 conditions, one epoch) to measure
   tokens per conversation, cost, and the auditor's realism by reading the transcripts.
3. The main run, sized from the pilot's measured tokens: every seed, both wordings, three epochs (60 conversations),
   within the $30 including the pilot.

Haiku as auditor, target and judge is Claude grading Claude talking to Claude; it was chosen because the worst-case
commitment of a Sonnet auditor (three times Haiku's output rate) would leave room for one epoch and no control.

## Analysis (exploratory; not the section 10 estimand)

Per (seed, speaker) triple and per epoch pair: D, the mean over comparable exchanges of the casual reply's tier rank
minus the clinical reply's, beside the same statistic for casual-versus-casual pairs. Report the directions, the
spread of the control, the register check's agreement with each arm's register (per turn index), and the tool rule
outcomes. Cite directions only; no claim rests on this lane.

## Compatibility

- One new `petri-audit` trigger key, `auditor_model`, empty by default and not part of the park, so the park file and
  every scripted fire are unchanged (`docs/triggers.md`).
- The scripted path is unchanged: a scripted seed with an auditor, an autonomous seed without one, and a selection
  mixing the two are refused before any call.
- New judgment rows have `kind: "register"`, `assistant_turn_index: 0` and `final_in_exchange: false`; consumers that
  filter on `kind`/`key` (the section 10 analysis, the exporter, the comparison scripts) never read them, and the
  lane's runs live on a runs branch, outside every published export.
- The scripted controller's staging events now carry `source: "seed"`; nothing reads the field on scripted runs.
