# Ops Routine — creation spec (fresh session per firing)

> **STATUS: NOT CREATED.** This is a proposal, not a description of something
> running. As of 2026-08-04 the daily cycle still fires into whatever
> orchestrator session is live. Nothing in this file takes effect until the
> owner creates the Routine on their own surface. Do not read a full lane as
> evidence it exists. (This header is here because
> `docs/backfill_accel_prompt.md` lacked one for five weeks and every reader,
> including several sessions, concluded a nonexistent Routine was running.)

## Why

The daily cycle currently fires into the main session, so a container reclaim
stops all measurement silently. Three multi-day idles so far: 2026-07-24..27,
07-30, and 08-01..02 — the last one 64.2 hours with zero fires journaled and all
eight lanes idle. Binding the cycle to a fresh session per firing removes the
dependency on any one conversation staying alive.

## Why it cannot be created from a session

`create_trigger` and even the read-only `list_triggers` return
`MCP error -32003: MCP tool call requires approval` on this owner's surface.
Four attempts across 2026-07-20, 07-26, and 08-04. **Create it in the Routines
UI directly** rather than having a session call the tool and waiting on an
approval prompt that has never arrived.

## Settings

| Field | Value |
|---|---|
| Name | `patientwords daily ops cycle` |
| Schedule | `0 13 * * *` — 13:00 UTC daily. Cron is evaluated in UTC; convert from local before entering. |
| Session mode | **Create a new session on each firing.** This is the entire point — do not bind it to an existing session. |
| Repos | `michaeldgreenphd/patientwords-engine` and `michaeldgreenphd/patientwords` |
| Branch | `claude/gemma-clinical-colloquial-interp-mavx04` on both |

## Prompt text

Paste verbatim. It is deliberately short: the cycle's real instructions live in
the repo, which is the point of a fresh session — it re-reads current state
instead of inheriting a stale memory of it.

---

You are a fresh session with the `patientwords-engine` and `patientwords` repos,
both on branch `claude/gemma-clinical-colloquial-interp-mavx04`. You have no
memory of prior sessions; the repos are your memory.

Run **exactly ONE** autonomous daily ops cycle, following
`docs/routine_standing_prompt.md` sections 1–7 in order. Read that file before
acting — it is the authority, and this message does not restate it.

Orient first from `CLAUDE.md` (both repos), `docs/HANDOFF_20260804.md`,
`ops/dashboard.json`, and `ops/trigger_journal.jsonl`. Treat repo documentation
as unreliable: a 2026-08-03 census found 56 of 74 documented claims false or
partly wrong, and `docs/HANDOFF_20260804.md` §6 carries the correction register.
Recompute any number you intend to publish or report.

All boundaries in the standing prompt are absolute: the $2/day operational and
$8 Tier B generation ceilings, the one-running + one-pending queue discipline,
resolve-only-when-terminal, append-only `data/simulated/`, no secrets in either
public repo, and the Tier B holdout stays sealed absent an explicit owner
instruction to unseal.

Fire triggers only through `scripts/fire_trigger.py`. Never `--force-evict` or
`--override-budget`. If a fire exits 1, the trigger file and journal entry are
already written — never re-fire; repair git by hand.

Exactly one cycle. Do not schedule further work, and do not create Routines.

---

## After creating it

1. Retire or rebind the existing Routine that fires into the old orchestrator
   session, or it will keep waking a conversation nobody is reading.
2. Update `ops/README.md` and `docs/routine_standing_prompt.md` §4a to describe
   the new arrangement — §4a currently documents the single-point-of-failure as
   the live condition.
3. Replace the STATUS header at the top of this file with the creation date and
   the Routine's id.
