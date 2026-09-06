---
name: daily-ops-cycle
description: Run exactly one maintenance ops cycle for patientwords-engine, exactly as docs/routine_standing_prompt.md sections 0–7 prescribe. Use when the user says "run the daily cycle" / "run the ops cycle"; never for an ad-hoc fire, publish, or harvest, and never twice in one session.
---

# Daily ops cycle

`docs/routine_standing_prompt.md` on `main` is the authority — sections 0–7, in
order, with every parameter taken from it verbatim. This skill adds nothing to
it; it exists so a session invoked by hand does the same bootstrap and stops at
the same place as the scheduled Routine.

1. **Bootstrap** per `docs/fresh_session_bootstrap.md`: both repos on `main`,
   clean `git status`, `ops/dashboard.json` identical to `origin/main`,
   `python scripts/seal_check.py --site ../patientwords --extra docs,ops` not
   exiting 2, `git push --dry-run origin main` succeeding. Any of those failing:
   stop and say which.
2. **Run sections 0–7** of the standing prompt. Section 0 may end the cycle.
   Fires go through the fire-trigger-safe skill (with `--keep-dashboard`: this
   session is the dashboard's writer), harvests through harvest-resolve, the
   seal check through holdout-seal-check, and section 5 through
   publish-site-data. The dashboard commit in section 6 succeeds only in the
   Routine's environment (`PW_ROUTINE=1`); anywhere else the guard hook refuses
   it, which means this session is not the Routine — stop and say so.
3. **Stop.** One cycle. No second cycle, no Routines, no reminders, no crons.
   End with the digest line from `python scripts/daily_brief.py --digest`.
