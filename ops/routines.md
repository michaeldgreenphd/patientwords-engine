# Automation routines — registry

Registry of every scheduled automation that touches these repos (audit
2026-07-21, E9 / drift-register 9). Maintenance rule: any change to a
schedule or a standing prompt updates this file **in the same commit**,
including recomputed hashes.

State note (drift-register 1): live ops **state** (`ops/dashboard.json`,
`ops/trigger_journal.jsonl`) is maintained on the working branch
(`claude/gemma-clinical-colloquial-interp-mavx04`), not main, until the
branch consolidation (audit E10) lands. This registry documents the
routines themselves and lives on main.

---

## 1 · Daily ops cycle ("daily Routine")

- **Schedule:** 13:00 UTC daily (= 09:00 America/New_York in DST). Observed
  fires land 13:00–13:15 UTC. Fires **into the main orchestrator session**
  (owner request 2026-07-10 — the earlier fresh-session Routine deep-linked
  its push notification to an empty session).
- **What it does:** exactly one ops cycle per `docs/routine_standing_prompt.md`
  sections 1–7 (orient → harvest → account → advance Tier B → publish site
  data only → update dashboard → brief), then delivers the owner digest as a
  push notification plus a chat message ending "Reply STOP here to freeze all
  automation." Exactly one cycle per firing; the cron re-fires itself daily.
- **Standing prompt of record:** `docs/routine_standing_prompt.md` on the
  **working branch** governs the cycle until E10 consolidates branches.
  - working-branch copy (operative), sha256:
    `cef1cfa92deaa332da8b5e29b86863fbf9698be1111fbf579f8c5d4e5c39b8c2`
  - main copy (jlens-wired; its transport/loglens publish lines are
    aspirational until those inputs land on the working branch — see
    dashboard `decisions_pending: TRANSPORT-LOGLENS-WIRING`), sha256:
    `6799ee34502ed10c39dd918c270d4976488afdc0c7a414bf671816aadb477a26`
- **Single-writer rule:** the daily Routine session is the only writer of
  `ops/dashboard.json`. Any other session that fires a trigger reverts the
  dashboard side effect and commits the journal entry only.
- **Cron history (reconciliation of the 11:30-vs-13:00 discrepancy):** the
  2026-07-08 ledger recorded the then-current anchor "daily fire 11:30 UTC =
  07:30 EDT" and confirmed the owner timezone America/New_York. The schedule
  was subsequently moved to 13:00 UTC (= 09:00 EDT); the ledger line is
  historical record (append-only), not the current spec. **Current spec:
  13:00 UTC.**

## 2 · Backfill accelerator (2-hourly, session-local)

- **Schedule:** cron `7 8-20/2 * * *` in the owner's local timezone
  (America/New_York, confirmed 2026-07-08) — minute 7 of every second hour
  from 08:00 through 20:00. Created 2026-07-20 at owner request ("every 2
  hours 8am–8pm so I don't have to do anything while asleep").
- **Mechanism & lifetime:** a **session-local** scheduled task (harness
  CronCreate, id `8f7d53bf`) firing into the orchestrator session. It does
  **not** survive that session's end and expires after ~7 days — it is not a
  server-side Routine. The persistent replacement could not be created
  because the create-trigger approval channel repeatedly fails on the owner's
  surface (dashboard `decisions_pending: BACKFILL-ACCEL-BLOCKED`).
- **What it does:** runs `scripts/backfill_planner.py` and fires its
  recommended $0 measurement legs (trace / lens / logits) through
  `scripts/fire_trigger.py`, respecting the one-running + one-pending queue
  and the settle window; resolves landed runs; never touches paid lanes. The
  8B-medical models are deferred until all other coverage completes
  (planner `DEFERRED_LAST`), then auto-released.

## 3 · Not routines (for completeness)

- **Push-to-run CI workflows** (`.github/workflows/*`) are event-driven, not
  scheduled: each fires when its file under `.github/trigger/` changes on a
  pushed branch. `scripts/fire_trigger.py` is the only sanctioned way to fire
  them.
- **The Mon/Wed/Fri critic pass** runs inside the daily cycle (owner decision
  2026-07-19, "interim critic is the permanent mechanism"); it has no
  separate schedule.
