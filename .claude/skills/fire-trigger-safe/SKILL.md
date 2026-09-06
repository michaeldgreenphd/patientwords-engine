---
name: fire-trigger-safe
description: Use whenever a push-to-run CI trigger must be fired, chained, or resolved in patientwords-engine (any of the eight lanes in `.github/trigger/`) — enforces the queue, settle-window, budget, and dashboard single-writer rules before any fire.
---

# Fire a push-to-run CI trigger safely

Every workflow in this repo fires when its file under `.github/trigger/` changes on a
pushed branch. `scripts/fire_trigger.py` is the ONLY sanctioned way to fire one: it
journals every fire to `ops/trigger_journal.jsonl`, validates params against the exact
per-workflow key sets (CI silently ignores unknown keys — a typo means a run with
defaults), enforces the one-running + one-pending queue, and enforces the daily spend
ceiling. Follow these steps in order; every failure mode here is silent.

## 1 · Preflight (before every fire)

1. `python scripts/fire_trigger.py status` — read the active entries for your trigger.
   Two active entries means the lane is full: STOP. Do not fire; do not force.
2. Confirm the trigger's workflow file exists on `main` (`ls .github/workflows/`; all
   eight do since 2026-09-04). A push that *creates* a ref fires nothing (the
   `github.event.created` guard); a trigger file that changes on an existing ref fires,
   and a merge that carries that change re-fires it.
3. Compose params only from the trigger's allowed keys (the `KNOWN_KEYS` set in
   `scripts/fire_trigger.py`, each verified against its workflow's params heredoc).
   Underscore-prefixed keys (`_nonce`, `_note`) are pass-through metadata. Never rename a
   rejected key to an underscore form to bypass validation — fix the key.
4. Rehearse with `--dry-run` first; fire only when the dry-run output is exactly what you
   intend.

## 2 · Fire

```
python scripts/fire_trigger.py fire --trigger <name> \
    --params '{"<key>": "<value>", "_nonce": "x1"}' \
    --note "why this run fires"
```

## 3 · Exit codes — handle every one

- **0** fired (or dry-run ok). Note which slot ("running" or "pending") it reports.
- **1** git publish failed after local writes — resolve the git state by hand; do NOT re-fire.
- **2** queue refusal: two active entries. Wait, harvest, `resolve` the landed run. Never `--force-evict`.
- **3** bad params (invalid JSON or unknown key). Fix the params; never bypass.
- **4** budget refusal. The attempt ENDS here: record why (dashboard `blockers`/notes). Never `--override-budget`.
- **5** no-op: the trigger file already holds exactly these params, so a push would not fire CI. Add/change `_nonce`.
- **6** settle refusal (see §4). Wait out the window, or confirm terminal state first.

## 4 · Queue discipline: chain, never stack

The concurrency group holds one running + one pending run per branch; pushing a third
trigger change **silently evicts the pending run**. So: at most two active fires per
lane, and advance by chaining — resolve the landed run, then fire the next.

- `python scripts/fire_trigger.py resolve --trigger <name>` — ONLY when the run is truly
  terminal and ALL expected outputs landed (every expected
  `trace_out/<stem>/batch_summary.part_NN.json` offset; for generation, the batch file
  plus `.report.json` sidecar on main). Resolving on partial landing lets a subsequent
  fire supersede a still-pending run (the 2026-07-09 eviction seam).
- **Settle window:** resolving stamps `resolved_utc`; a same-trigger fire within 15
  minutes (`MEDLANG_TRIGGER_SETTLE_MINUTES`) is refused with exit 6, because the resolved
  run may still occupy the GitHub concurrency group even though its output landed locally
  — firing now can enter as a third run and silently supersede the pending one.
- `--ignore-settle` is legitimate ONLY after you have confirmed in GitHub Actions itself
  (Actions UI or `gh run list`) that the prior run is terminal (completed/failed/
  cancelled) and nothing of that workflow is still queued on the branch. Never use it to
  rush a still-running group.
- Journal entries expire after 8h (`MEDLANG_TRIGGER_EXPIRE_HOURS`) as a safety valve; a
  missing expected output is a blocker to record, never a reason to assume success.

## 5 · Budget (paid fires)

- Paid triggers: `scenario-generation`, `model-evaluation`, `advice-eval`, and
  `circuit-trace` with `show_mitigation: true`; `PAID_TRIGGERS` in the script is the
  source of truth. Their params MUST include `max_spend` (finite number > 0); a
  missing/invalid `max_spend` is never overridable.
- Daily operational ceiling: $2 (from `ops/dashboard.json` `spend.daily_ceiling_usd`,
  default 2.0). The guard counts committed spend = landed today + in-flight `max_spend`
  of active paid entries fired today.
- A `circuit-trace` fire with `show_mitigation: true` is ALSO a paid path (translation
  calls): the guard imputes a flat $0.15 commitment per fire and applies the same ceiling.
- Exit 4 ends the attempt. Record the refusal; do not retry, split, or override.

## 6 · Dashboard single-writer + git hygiene

`fire_trigger.py` writes the trigger file and the journal, commits and pushes exactly
those two, and restores `ops/dashboard.json` afterwards — its queue-block update is a
side effect that only the daily Routine keeps (`--keep-dashboard`, which the Routine's
prompt passes; the Routine commits the dashboard itself in its step 6, and the guard
hooks refuse that commit outside the Routine's environment). No other session commits
the dashboard, and none needs to revert it any more.

`--no-git` writes the files without committing; it is for inspection. A hand `git push`
that carries a trigger-file change is refused by the guard hooks and by
`.githooks/pre-push`, so a real fire is always `fire` in its default git mode, then
`resolve` once the run lands. One fire per invocation; never a second `fire` before the
first has pushed (a second write replaces the trigger content, CI fires once, and the
first fire's journal entry occupies a slot for 8h — 2026-07-21).

## Never

- Never fire a trigger any way other than `scripts/fire_trigger.py` (no hand edits to
  `.github/trigger/`, no direct workflow dispatch, no editing `.github/workflows/`).
- Never use `--force-evict` or `--override-budget`, and never use `--ignore-settle`
  without a confirmed-terminal check in GitHub Actions.
- Never stack a third fire into a lane, and never fire into a group with a mid-flight
  run whose expected outputs are incomplete.
- Never resolve a journal entry on partial landing; never hand-edit
  `ops/trigger_journal.jsonl` (sole exception: repairing a corrupt line the script
  hard-stops on, by hand, as its error message instructs).
- Never pass `--keep-dashboard` outside the daily Routine session.
- Never let a merge or revert change a trigger file — restore the target branch's
  trigger files before committing the merge, or you re-fire runs and double-spend.

