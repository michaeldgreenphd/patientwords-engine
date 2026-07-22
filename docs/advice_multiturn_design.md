# B6 — multi-turn advice protocol: design (NO implementation without owner sign-off)

Status: design document only (2026-07-22). The extensions spec marks B6 as the
one item requiring real `elicit` surgery; per the owner's direction it is
designed first and implemented only after explicit sign-off.

## What it measures

Two scripted second turns, both ordinary consumer behavior:

1. **Clarifier follow-through.** When a model's first response asks a
   clarifying question (the `clarifying_question` flag), send a scripted vague
   answer. Measures: does the model still triage correctly on incomplete
   information, or does the question turn out to be theater?
2. **Pushback persistence.** After any escalation recommendation, send a
   scripted cost/access pushback ("can't I just wait?" class). Measures: does
   the recommended urgency hold under social pressure? Sycophancy under
   pushback is documented to vary widely across vendors.

## Interface (spec sketch, refined)

```
elicit --follow-up-script data/advice_followups.json
```

Script file (data — turn text is owner-authored, never Python):

```json
[
  {"trigger": "if_clarifying_question", "id": "vague_answer",
   "user_turn": "<owner-authored vague reply>"},
  {"trigger": "if_escalation", "id": "cost_pushback",
   "user_turn": "<owner-authored pushback>"}
]
```

Triggers: `always` | `if_clarifying_question` | `if_escalation`.

- `if_clarifying_question` needs a turn-1 classification BEFORE the judge
  runs. Design choice: a cheap mechanical heuristic is NOT acceptable
  (question-mark counting misclassifies rhetorical questions), so trigger
  evaluation uses the judge model on turn 1 with the rubric's
  `clarifying_question` flag only — a paid micro-judgment inside elicit,
  counted against `max_spend` like any call, recorded as its own
  `record_type: "turn_trigger"` record for auditability. Same for
  `if_escalation` (tier at-or-above a data-named threshold).
- Turn-2 request carries the full turn-1 conversation (user msg, model reply,
  scripted user turn); the raw request in the record shows exactly what was
  sent, as always.

## Record schema

Records gain `conversation_id` (stimulus_id + arm + model + k) and `turn`
(1, 2). The hash chain is unchanged — each turn is one record, appended in
completion order. Resume keys extend to (stimulus, arm, model, k, turn).

## Analysis (phase-2 companion)

- Clarifier follow-through: tier of turn 2 vs reference (A2) among
  conversations where turn 1 asked a question — "correct triage on
  incomplete information" rate.
- Pushback persistence: P(turn-2 tier < turn-1 tier | pushback) per model —
  the capitulation rate — plus its patient-vs-clinical difference (does
  pushback hurt colloquial askers more?).

## Cost shape

Turn 2 roughly doubles per-conversation cost where triggered; the trigger
micro-judgments add ~one haiku call per conversation. A K=1 pilot subset
(~25 conversations x 2 providers) fits inside ~$0.50. Ceilings and sidecars
per the standing discipline.

## Open questions for the owner before implementation

1. Approve the trigger set and supply the two scripted user turns (data).
2. Escalation threshold tier for `if_escalation` (data).
3. K for multi-turn (K=1 proposed for the pilot subset).
4. Whether turn-2 runs on every provider or the cheap subset first.
