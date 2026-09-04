# First prompt — fresh session, 2026-08-04

Paste the block below as the first message in a new session with both repos
attached (`michaeldgreenphd/patientwords-engine` and `michaeldgreenphd/patientwords`).
It is written to be self-sufficient: everything else it needs, it reads from the
repos.

---

You are taking over an active mechanistic-interpretability study. Two public
repos, sibling checkouts, both on branch `claude/gemma-clinical-colloquial-interp-mavx04`:

- `/home/user/patientwords-engine` — measurement, analysis, exporters, ops
- `/home/user/patientwords` — the public GitHub Pages site (presentation only)

**Read `patientwords-engine/docs/HANDOFF_20260804.md` first, end to end, before
doing anything else.** It is the orientation written for you: current results
with commands to recompute them, a per-area map of both repos, the traps that
have actually cost sessions time, and a register of everything the repos
document that is false. A 12-agent census checked 74 documented claims and found
56 false or partly wrong — so default to distrusting the docs and trusting the
artifacts, including that handoff. Then read `CLAUDE.md` in both repos and
`ops/dashboard.json` with `ops/README.md` beside it.

These rules are in force from this message, before you read anything:

1. Both repos are PUBLIC. Never write a secret, key, or token into any file.
2. Never reveal a Tier B holdout phrase — not in chat, a brief, a commit
   message, a filename, or your own summary of a seal check. Not partially.
   `python scripts/seal_check.py --site ../patientwords` must be CLEAN before
   any publish push, and must be run from the working branch (on `main` it
   computes an empty set and passes vacuously).
3. `data/simulated/` is append-only. Never rewrite a landed batch or sidecar.
4. Never hand-edit `.github/trigger/`. Fire only via `scripts/fire_trigger.py`.
   Never `--force-evict` or `--override-budget`. One running + one pending per
   lane; a third push evicts the pending run silently and leaves no record.
   If a fire exits 1, the trigger file is already written — never re-fire.
5. Ceilings are absolute: $2/day operational, $8 Tier B generation.
   `scripts/ledger_update.py` is the only writer of spend numbers.
6. Intentional misspellings in phrase data are stimuli. Medical vocabulary lives
   only in JSON data files, never in Python source.
7. The Tier B holdout unseals only on my explicit instruction — never on a
   schedule, never as part of a cycle.

First tasks, in order:

1. Orient from the handoff, then verify its headline numbers yourself with the
   recompute commands in §2. Tell me anything that no longer holds.
2. Tell me what state the lanes and the queue are actually in — from GitHub and
   the trigger journal, not from `dashboard.queue`, which is a lossy mirror.
3. Then answer this, which is the one thing I need to decide: the daily 13:00
   UTC ops Routine currently fires into whatever session is live, so a container
   reclaim silently stops all measurement (three multi-day idles so far, worst
   64 hours). §8 of the handoff recommends binding the daily cycle to a fresh
   session per firing so it cannot die with an interactive session. That needs
   me to approve the Routine in-client. Walk me through what you'd have it run
   and what changes for you, then wait for my answer before creating anything.

Do not fire anything paid, publish site data, or touch the holdout until I say so.
Ask before anything irreversible or outward-facing.
