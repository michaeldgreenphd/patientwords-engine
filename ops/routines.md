# Automation routines — registry

Registry of every scheduled automation that touches these repos (audit
2026-07-21, E9 / drift-register 9). Maintenance rule: any change to a
schedule or a standing prompt updates this file **in the same commit**,
including recomputed hashes.

State note (drift-register 1, closed 2026-09-04): live ops **state**
(`ops/dashboard.json`, `ops/trigger_journal.jsonl`) is maintained on `main`.
Until 2026-09-04 it lived on the working branch
`claude/gemma-clinical-colloquial-interp-mavx04`; the branch consolidation
(audit E10) landed as engine PR #6 and that branch is retired. This registry
documents the routines themselves.

---

## 1 · Daily ops cycle ("daily Routine")

- **Schedule:** Tuesdays and Fridays 12:00 UTC (cron `0 12 * * 2,5`;
  fires land ~12:07 UTC), a **fresh session per firing** — the owner-approved
  maintenance downshift of 2026-08-29. During the active study it fired
  13:00 UTC daily into the main orchestrator session (owner request
  2026-07-10 — the earlier fresh-session Routine deep-linked its push
  notification to an empty session).
- **What it does:** exactly one maintenance cycle per
  `docs/routine_standing_prompt.md` sections 0–7 (cadence gate → orient →
  harvest → drift sentinel with a bounded wait → re-park → publish site data
  only when new measurement landed → dashboard → brief), then delivers the
  owner digest as a push notification. Exactly one cycle per firing.
  Measured wall-clock: 75 min (2026-08-29) to 2h21m (2026-09-04); the
  Neuronpedia sentinel itself is 14–39 min of that, the rest is bootstrap,
  orientation, gates and the brief.
- **Standing prompt of record:** `docs/routine_standing_prompt.md` on
  `main`, sha256 `fd27e2bf9212f075a74f6a477b6b7c126086ed8706ecb7cca6e5913668c66456` (recompute with `sha256sum` after any edit and
  update this line in the same commit).
- **Wrapper prompt:** lives in the claude.ai Routines UI (created there, so
  the API cannot edit it); it names `main` in both repos and points here.
 the daily Routine session is the only writer of
  `ops/dashboard.json`. Any other session that fires a trigger reverts the
  dashboard side effect and commits the journal entry only.
- **Cron history (reconciliation of the 11:30-vs-13:00 discrepancy):** the
  2026-07-08 ledger recorded the then-current anchor "daily fire 11:30 UTC =
  07:30 EDT" and confirmed the owner timezone America/New_York. The schedule
  was subsequently moved to 13:00 UTC (= 09:00 EDT); the ledger line is
  historical record (append-only), not the current spec. **Current spec:
  Tuesdays and Fridays 12:00 UTC, since 2026-08-29.**

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
