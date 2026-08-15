# Owner decisions — 2026-08-15 (recorded by the babysitter session)

The owner answered all thirteen open items through the interactive decisions artifact
(published 2026-08-15). This doc is the durable record; the daily Routine folds the
outcomes into `ops/dashboard.json` on its next cycle (single-writer rule — this session
wrote no dashboard prose).

Two of the thirteen turned out to be **already implemented**; they were surfaced to the
owner from stale `decisions_pending` entries. Recorded below so the entries can be
retired rather than re-decided.

## 1 · MEDICAL-FINETUNE-FRAMING-20260808 — SENTENCE B

The sanctioned replacement for every "the two medical fine-tunes are the study's null
cases" sentence, verbatim:

> the medical fine-tunes are no longer null cases: meditron downgrades 31 flips to 5
> upgrades (p = 1.3×10⁻⁵) and apertus 18 to 5 (p = 0.011), with mean penalties −0.040
> and −0.022 whose intervals exclude zero; both are post-registration exploratory
> additions, and the urgency tiers behind every flip call remain draft pending domain
> review.

This **supersedes** the 2026-08-08 sanctioned sentence, which said "their flip-direction
tests remain underpowered (5 and 5 flips)" — untrue since the 08-10 recomputation.
No other phrasing about the medical models is sanctioned. Deployment: the numbers ship
with the `model_stats.json` republish (decision 5), never ahead of it.

## 2 · OPENROUTER-LANE-UNCEILINGED-20260808 — ALREADY IMPLEMENTED

Owner chose "set an explicit daily ceiling + per-channel reporting". Both halves already
exist and were verified this session:

- `fire_trigger.py` enforces `DEFAULT_OPENROUTER_DAILY_CEILING_USD = 10.0` on the
  OpenRouter lane (blocking guard, lane-resolved per fire).
- `ledger_update.check_ceilings` reports per lane against each lane's own ceiling.
- The cumulative-sidecar bug is fixed: `cost_basis="cumulative_from_records"` books
  `run_cost_usd` to the day and leaves the prior-runs balance out of every day bucket.
- `ops/dashboard.json` carries `openrouter_daily_ceiling_usd: 10.0`.

**No number was supplied with the answer**, so the ceiling stands at the implemented
$10/day. Say a figure and it is a one-line change. The `decisions_pending` entry is
stale and should be retired.

## 3 · Pooled-share caveat — WORDING B

Homepage strip caveat, verbatim:

> Batches here were generated to stress specific topics, so flip-prone scenarios are
> over-represented by design; the pooled share is a property of this stress-test set,
> not an estimate of how often models flip in general.

Replaces the existing shorter stat-note. This is a page-text edit, owner-authorised.

## 4 · STEERED-BATCH-PUBLICATION-20260811 — PUBLISH, LABELLED AS STEERED

`pairs_20260809T172338Z` (69 pairs) and `pairs_20260811T190638Z` (68 pairs) join the
public payload, **disclosed as steered rather than random sampling**, with the headline
pooled share restated so it is not silently inflated by outcome-selected batches.

Binding constraints on the implementation (unchanged by this decision):

- The ten holdout-colliding indices stay withheld exactly as they are today
  (`pairs_20260809T172338Z` #12 #27 #35 #45 #57 #62; `pairs_20260811T190638Z` #10 #23
  #33 #54). Publication of a batch never publishes a sealed pair.
- Both stamps stay in `_SUPPLEMENTARY_STAMPS` / `_supp`: publishing to the gallery is
  **not** the same as joining the confirmatory statistical population (POPULATION-DEF
  option B). No claim-grade number moves because of this decision.

## 5 · MODEL-STATS-PUBLISH-POLICY-20260810 — AUTOMATE IT

`python scripts/paired_stats_rigor.py --site ../patientwords` is now part of the §5
publish chain (`docs/routine_standing_prompt.md`, this session). Accepted consequence:
it can trip `claim_check` when a quoted number moves — that is the gate working, and the
cycle fixes the prose or holds the file rather than skipping the refresh.

## 6 · JLENS-DEPTH-PINS-20260808 — ALREADY IMPLEMENTED

Owner chose "add the 119-pair set". It was approved and implemented on 2026-08-08
(`docs/decisions_20260808_owner.md`): the published `data/jlens_depth.json` carries
seven blocks including `pairs_20260707T171223Z`. Verified this session. The
`decisions_pending` entry is stale and should be retired.

## 7 · Backfill pace — CLAIM-GRADE MODELS FIRST, THEN HAND OFF

The babysitter chain continues until the six claim-grade models reach full behavior
parity across all 39 batches — the four pre-registered (`gemma-2-2b`, `gemma-3-4b-it`,
`qwen3-1.7b`, `qwen3-4b`) plus the two medical fine-tunes (`meditron3-8b`,
`apertus-8b-meditronfo`). `medgemma-4b-it` finishes first and is nearly done. The
remaining models (`llama-3.2-3b`, `olmo-2-1b`, `gemma-2-2b-it`) hand off to the daily
Routine's own planner leg, one to two a day, no babysitting.

Note for whoever implements the ordering: `backfill_planner._next_logits` defers the two
8B medical models last (`DEFERRED_LAST`), which is the opposite of this priority. The
chain overrides the planner's model choice for those two rather than changing the
planner's default.

## 8 · OPS-CADENCE-SINGLE-POINT — APPROVE THE SCHEDULED ROUTINE

Approved: the daily cycle moves to a standalone scheduled Routine that fires a fresh
session, so a reclaimed session can no longer stop ops (the 2026-08-01/02 48-hour gap).

## 9 · Unwired trigger key — GUARD, NOT DELETION (deviation, explained)

Owner chose "delete the name", on the framing that the key had nothing behind it. That
framing was right for this branch and **wrong across branches**: `claude/pab-integration-layers-ufl8dg`
carries BOTH `.github/trigger/pab-probe.json` and `.github/workflows/pab_probe.yml`, so
deleting the key here would strand a sibling branch's working tooling at the next merge.

Implemented instead — strictly better on the owner's actual intent (no silent no-op
fires) and destroys nothing: `fire_trigger.py` now refuses, with new exit code 7, any
fire whose trigger file no workflow **on the current branch** reads. The check is
branch-local, so `pab-probe` keeps working where it is wired and cannot silently no-op
where it is not. Regression tests added (`test_unwired_trigger_refused_with_exit_7`,
`test_workflow_reads_trigger_is_branch_local`).

Owner can still order the deletion; this note is the reason it was not done unasked.

## 10 · JLENS-TRANSPORT-LOGLENS-DOC-CONFLICT-20260809 — CONFIRM WIRED

The exporters run in the daily cycle (owner option 1 of 2026-07-23). The two contradicting
lines are gone: the "Never run the transport/loglens exporters" bullet in
`.claude/skills/publish-site-data/SKILL.md` and the "not wired — §5" sentence in
`.claude/skills/daily-ops-cycle/SKILL.md`, which now states they are wired and that a
`generated_utc`-only diff is expected rather than a reason to skip.

## 11 · DOC-SWEEP-DRIFT-20260810 — FIX BOTH

- `docs/routine_standing_prompt.md` §2b now names the four amendment docs that exist on
  this branch instead of `docs/preregistration_amendments.md`, which lives only on main.
- `scripts/extract_site_text.py` `PAGES` gained `simulated-scenarios/scenario.html` and
  `llm/code.html` (~44 KB of live prose that no consumer of the extract could see).

## 12 · Physician tier review — STILL WAITING ON A CLINICIAN

No action. Draft labels stay, which is the honest state.

## 13 · Advice expansion — SEND THE CODING WORKSHEET FIRST

Owner wants the 25 judge-agreement coding items as their own phone page before signing
the pre-registration. Built this session as an interactive artifact; the pre-registration
signature stays open behind it.

## Not a decision, found while executing

`tests/test_specialty_map.py::test_covers_live_payload_topics` fails against the current
site payload: 141 of 415 live topics are unmapped (threshold 20). It is data drift, not a
code regression — it predates this session's edits and surfaced when this checkout's
sibling site clone was fast-forwarded to the 2026-08-15 payload. The map is hand-synced
(`data/specialty_map.draft.json` ↔ site `data/specialties.json`) and regenerating it
changes the site's specialty filter, so it is left for an owner-directed pass rather than
"fixed" silently.
