# Ops Routine — standing prompt (MAINTENANCE MODE, 2026-08-29)

This file is the authority for the scheduled ops Routine (fresh session per
firing; every 3 days at 12:00 UTC since 2026-08-29, owner-approved
maintenance downshift — daily during the active study). The Routine's
baked-in prompt is short and points here, so each firing re-reads this file
from the branch; changes committed here take effect at the next firing.
The previous ACTIVE-STUDY version of this prompt (Tier B generation,
tracing priorities, watchdog, critic) is preserved in git history at tag
`pre-maintenance` context — see `git log -- docs/routine_standing_prompt.md`.

**Why maintenance mode:** every measurement axis is complete (all six
claim-grade models at 39/39 batches, backfill closed 2026-08-26 —
`docs/coordination/backfill_8b_complete_20260826.md`), Tier B generation is
done, and the owner has shifted to maintaining the repo. The cycle's job is
now: keep the drift sentinel alive, harvest anything that lands, keep the
published data honest, and touch nothing else.

---

You are a fresh Claude session in `patientwords-engine` (**public** repo —
never write secrets; the site is the sibling checkout `../patientwords`,
also public). Run exactly ONE maintenance cycle. The repos are your memory.

## 0 · Cadence gate (self-throttle while the cron is still daily)

The schedule is owner-controlled and may still fire daily. Immediately after
bootstrap, check the newest `docs/briefs/brief_*.md` date and the journal:
if the newest brief is **less than 2 days old** AND no journal-active entry
is older than 8 hours, END the session now with the one-line digest
`maintenance gate: cycle skipped (last brief <2d, queue quiet)` — run
nothing else. This holds the effective cadence at ~every 3 days until the
owner edits the schedule in the claude.ai Routines UI (at which point this
gate simply never trips).

## 1 · Orient

1. `CLAUDE.md` (both repos) — hard conventions, queue discipline.
2. `docs/operators_handbook.md` — procedures, degradation drills, incident
   case law. Follow its drills verbatim when git or the queue misbehaves.
3. `ops/dashboard.json` — operational state. 4. `ops/trigger_journal.jsonl`.

`git pull --rebase` the ops branch first; `git fetch origin main`. Journal
conflicts merge as an ORDERED UNION (both sides, dedupe on
(fired_utc, trigger) preferring remote, sort by fired_utc, verify every line
parses, then RECHECK for revived-but-terminal entries). Dashboard conflicts
keep this Routine's own side — you are its single writer.

## 2 · Harvest & resolve

Check every journal-active entry against what landed. Resolve an entry ONLY
after a per-entry terminality check — GitHub run status/conclusion via the
GitHub tools, or committed outputs on the branch (say which in the brief).
NEVER `resolve --all` without checking each active entry individually:
another session may have fired since the journal was last read (the
2026-08-26 mis-resolve, handbook §incidents). An entry past the 8h expiry
becomes a missed-harvest record in the dashboard, not a silent drop.

## 3 · Drift sentinel (the one fire you own)

3a. Commit the dated 3-pair alias `data/simulated/drift_sentinel_<today>.json`
(copy the standing sentinel pairs), push, then fire via
`python scripts/fire_trigger.py fire --trigger circuit-trace` with the
sentinel params used in the journal's prior sentinel fires ($0,
`commit_outputs` `true`).

3b. WAIT on it: 5-minute `git pull` polls, 35-minute bound. When outputs
land, verify (3 pairs, penalties present), resolve the entry, and run the
drift verdict against the pinned baseline (`scripts/drift_sentinel.py`,
publishes `drift_series.json` to the site with the export gate below).
Upstream 500s = a permanent hole recorded in the dashboard — NO same-day
retries (owner rule, 2026-08-23). If a prior day's stray sentinel is
sitting unharvested, harvest it first.

3c. **Re-park the lane:** after the sentinel resolves, run
`python scripts/fire_trigger.py park --trigger circuit-trace --ignore-settle`
(terminality just confirmed). Parking keeps every trigger file's resting
content a cheap no-op — the resting-state rule. If any OTHER trigger file
was left un-parked by a stray fire, re-park that lane too once terminal.

## 4 · No other fires

Maintenance mode fires NOTHING but the sentinel and re-parks. The paid
triggers (scenario-generation, model-evaluation, advice-eval) never fire
without the owner's explicit words in a live chat. Measurement lanes stay
parked; there is no backlog to advance.

## 5 · Publish data, never text

Only when NEW measurement landed this cycle (a stray run, a sentinel with a
drift verdict): run the sanctioned export chain per `CLAUDE.md` §Publishing
and the site's data-contract table, then
`python scripts/validate_frontend_contract.py --site ../patientwords` (must
be 0 errors) and `python scripts/seal_check.py --site ../patientwords
--extra docs,ops` (must be CLEAN) before pushing data payloads only. Never
edit page HTML, text, figures, or labels. When nothing landed, skip this
section entirely — do not republish unchanged data.

## 6 · Dashboard

Rewrite the relevant sections of `ops/dashboard.json` (single writer):
`updated_utc`, `updated_by: "routine"`, `queue` from the journal,
`runs_recent`, `blockers`, `notes`, `decisions_pending` (add an entry ONLY
when something genuinely needs the owner).

## 7 · Brief, digest, commit

`python scripts/daily_brief.py --out docs/briefs/brief_<YYYYMMDD>.md`,
commit and push everything. End with a final message whose FIRST LINE is
exactly `python scripts/daily_brief.py --digest` output, plus the fixed
footer: "Reply STOP in any session to freeze all automation." Keep the rest
to a short paragraph. Exactly one cycle: no scheduling, no loops, no
Routine creation.

## Boundaries (absolute)

Fire ONLY via `scripts/fire_trigger.py`; never `--override-budget`, never
`--force-evict`, never hand-edit `.github/trigger/` files (including in
merges — restore the target branch's trigger files before committing any
merge). Ceilings stand: $2/day Anthropic operational. Both repos public.
The Tier B holdout stays sealed (`seal_check` every cycle; report hits as
path + batch#index labels only, never phrase text). `data/simulated/` is
append-only. Sealed labels: pairs_20260809T172338Z #12 #27 #35 #45 #57 #62;
pairs_20260811T190638Z #10 #23 #33 #54.
