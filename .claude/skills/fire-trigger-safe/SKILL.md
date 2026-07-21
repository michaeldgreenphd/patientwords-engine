---
name: fire-trigger-safe
description: Use whenever a push-to-run CI trigger must be fired, chained, or resolved in patientwords-engine (circuit-trace, logits-eval, jlens-readout, scenario-generation, model-evaluation, archive-renders, activation-patching) — enforces the queue, settle-window, budget, and dashboard single-writer rules before any fire.
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
2. Confirm the trigger's workflow file exists on the current branch
   (`ls .github/workflows/`). Hard-stop on `activation-patching` where its workflow is
   absent (it is on the script's TRIGGERS list but has no workflow on main): the fire
   would be a silent no-op plus a phantom journal entry blocking the queue slot for 8h.
   Warn before a first-ever fire of a trigger on a branch — creating a previously-absent
   trigger file fires the workflow, and merging that file later RE-fires it.
3. **Measurement fires (circuit-trace, logits-eval, jlens-readout, activation-patching)
   need the batch's pairs file on the working branch first.** Generation archives land on
   main; measurement workflows check out the dispatched branch. If the file is missing:
   `git checkout origin/main -- data/simulated/<batch>.json data/simulated/<batch>.report.json`
   and include it in the fire's push. (All three batch-7 measurement runs failed on this,
   2026-07-12.)
4. Compose params only from the trigger's allowed keys (the `KNOWN_KEYS` set in
   `scripts/fire_trigger.py`, each verified against its workflow's params heredoc).
   Underscore-prefixed keys (`_nonce`, `_note`) are pass-through metadata. Never rename a
   rejected key to an underscore form to bypass validation — fix the key.
5. Rehearse with `--dry-run` first; fire only when the dry-run output is exactly what you
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

- Paid triggers: `scenario-generation` and `model-evaluation`. Their params MUST include
  `max_spend` (finite number > 0); a missing/invalid `max_spend` is never overridable.
- Daily operational ceiling: $2 (from `ops/dashboard.json` `spend.daily_ceiling_usd`,
  default 2.0). The guard counts committed spend = landed today + in-flight `max_spend`
  of active paid entries fired today.
- A `circuit-trace` fire with `show_mitigation: true` is ALSO a paid path (translation
  calls): the guard imputes a flat $0.15 commitment per fire and applies the same ceiling.
- Exit 4 ends the attempt. Record the refusal; do not retry, split, or override.

## 6 · Dashboard single-writer + git hygiene

The daily Routine session is the ONLY writer of `ops/dashboard.json`. The fire command
rewrites the dashboard's queue section as a side effect, so:

- **In the daily Routine session:** the default fire (script does add/commit/push) is fine.
- **In ANY other session:** fire with `--no-git`, then revert the dashboard side effect
  and commit only the trigger file and the journal:

```
python scripts/fire_trigger.py fire --trigger <name> --params '...' --note '...' --no-git
git checkout -- ops/dashboard.json
git add .github/trigger/<name>.json ops/trigger_journal.jsonl
git commit -m "Fire <name>: <note>"
git pull --rebase && git push
```

- **ONE FIRE PER PUSH.** Never run a second `--no-git` fire before the first is pushed:
  the second write replaces the trigger-file content, the eventual push carries only the
  last version, CI fires once — the first fire is silently dropped while its journal
  entry occupies a queue slot for 8h. (Learned 2026-07-21.) Sequence is always: fire →
  revert dashboard → commit → push → only then the next fire.

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
- Never write `ops/dashboard.json` from a non-Routine session — always revert the side
  effect before committing.
- Never run two `--no-git` fires before one push.
- Never let a merge or revert change a trigger file — restore the target branch's
  trigger files before committing the merge, or you re-fire runs and double-spend.
- Never write secrets, keys, or tokens into params, notes, or any file — both repos are
  public.

