---
name: fire-trigger-safe
description: Use whenever a push-to-run CI trigger must be fired, chained, parked, or resolved in patientwords-engine (any lane in `.github/trigger/`), and before any merge, rebase or cherry-pick that could carry a trigger file — enforces the queue, settle-window, budget, resting-state and dashboard single-writer rules before any fire.
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
2. Confirm that a workflow on the branch you fire from reads the trigger's file
   (`ls .github/workflows/`; `docs/triggers.md` maps each trigger file to its workflow,
   and `fire` refuses with exit 7 when no workflow on the branch reads it). A push that
   *creates* a ref fires nothing (the `github.event.created` guard); a trigger file that
   changes on an existing ref fires, and a merge that carries that change re-fires it
   (§8).
3. Compose params only from the trigger's allowed keys (the `KNOWN_KEYS` set in
   `scripts/fire_trigger.py`, each verified against its workflow's params heredoc).
   Underscore-prefixed keys (`_nonce`, `_note`) are pass-through metadata. Never rename a
   rejected key to an underscore form to bypass validation — fix the key.
4. A pilot-root fire (circuit-trace `output_root: pilot/traces`, logits-eval
   `output_root: pilot/logits`) reads a pairs file named for its run:
   `pilot/runs/<run_id>/.../<run_id>_<name>.json`. Both lanes name the output folder by
   the file's stem alone, so the run id in the name keeps two runs' parts out of one
   folder; `fire` refuses any other name with exit 3 (as the params jobs do).
   `pilot/analysis/trace_pairs.py` writes that name by default. Run 2's legacy
   `trace/trace_pairs.json` is refused: copy it under
   `pilot_v2_20261002_trace_pairs.json` to fire it again. `docs/triggers.md` has the
   rest of the pilot rules.
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
- **1** git publish failed after local writes (main moved; the push was non-fast-forward) — run `python scripts/fire_trigger.py publish`, which rebases the fire and pushes it under the fire token; do NOT re-fire, and do not hand `git push` (the guards refuse a trigger change from anything but the script). It re-runs the queue, settle and budget guards against the rebased journal and dashboard before pushing, so it can refuse with 2, 4 or 6 like `fire`. A conflict is aborted for you; resolve it (journal: ORDERED UNION), then `publish` again.
- **2** queue refusal: two active entries. Wait, harvest, `resolve` the landed run. Never `--force-evict`.
- **3** bad params (invalid JSON or unknown key). Fix the params; never bypass.
- **4** budget refusal. The attempt ENDS here: record why (dashboard `blockers`/notes). Never `--override-budget`.
- **5** no-op: the trigger file already holds exactly these params, so a push would not fire CI. Add/change `_nonce`.
- **6** settle refusal (see §4). Wait out the window, or confirm terminal state first.
- **7** no workflow on this branch reads the trigger; fire from the branch that has one.
- **8** archive-renders only: the tag's manifest is already on this branch or on its fetched
  remote tip, so the fire would re-upload over an existing Release with `--clobber` (the
  2026-09-08 duplicate p3 fire); also when git cannot answer (the guard fails closed) or origin
  cannot be fetched. Use a fresh tag; `--reuse-tag` only for a deliberate re-archive, and the CI
  shrink guard still checks it. `prune_only` fires and the `park` command are exempt (neither
  uploads); the `_parked` param exempts nothing.

## 4 · Queue discipline: chain, never stack

The concurrency group holds one running + one pending run per branch; pushing a third
trigger change **silently evicts the pending run**. So: at most two active fires per
lane, and advance by chaining — resolve the landed run, then fire the next.

- `python scripts/fire_trigger.py resolve --trigger <name>` — ONLY when the run is truly
  terminal and ALL expected outputs landed (every expected
  `trace_out/<stem>/batch_summary.part_NN.json` offset, or
  `pilot/traces/<stem>/batch_summary.part_NN.json` for a fire with
  `output_root: pilot/traces`, or
  `pilot/logits/<stem>__<model>/batch_summary.part_NN.json` for a logits-eval fire with
  `output_root: pilot/logits`; for generation, the batch file
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

- **Which fires are paid.** `PAID_TRIGGERS` in `scripts/fire_trigger.py` is the source of
  truth for the lanes, and `is_paid_fire` decides each fire; read the script, not a list
  copied here (copies have gone stale). Two rules sit outside the bare lane list:
  petri-audit counts as paid only in `mode: run`, `mode: readapt`, and `mode: rejudge`
  with a real judge (its `mockllm/judge` rehearsal is free), and a `circuit-trace` fire
  with `show_mitigation: true` is paid although circuit-trace is not in
  `PAID_TRIGGERS`. `docs/triggers.md` states what each lane costs.
- **A paid fire declares its own ceiling:** `max_spend` (a finite number > 0), plus
  `judge_max_spend` when `judge` is true; a petri-audit `readapt` or `rejudge` commits
  `judge_max_spend` alone (`fire_commitment`). A missing or invalid ceiling is refused
  and is never overridable.
- **A mitigation fire takes NO `max_spend`.** `KNOWN_KEYS["circuit-trace"]` has no such
  key, so adding one is an unknown-key refusal (exit 3). The guard imputes a flat $0.15
  per fire instead (`MITIGATION_IMPUTED_USD`, for its Anthropic translation calls) and
  applies the same ceiling.
- **Daily ceiling, per billing lane** (`fire_lane`). The Anthropic lane's is
  `spend.daily_ceiling_usd` in `ops/dashboard.json` (default $2). A dated entry in
  `ops/budget_overrides.json` (`{"YYYY-MM-DD": {"ceiling_usd": N, "reason": "..."}}`)
  replaces it for that one UTC day; a malformed entry leaves the standing ceiling in
  force. Every entry is an owner authorization that quotes the owner's words in its
  `reason` (`docs/operators_handbook.md` §6): never add one without them. A fire that
  bills only OpenRouter counts against `spend.openrouter_daily_ceiling_usd` (default
  $10), which the overrides file never raises.
- The guard counts committed spend = landed today on that lane + the commitment held by
  every paid entry fired today on it, resolved or expired alike; only eviction releases
  one (since 2026-09-23 — resolving no longer frees budget). That includes a fire whose
  run never spent: skipped at ref creation, refused by the CI gate, or failed before
  any call. So a corrected re-fire the same day needs room for both commitments
  (docs/operators_handbook.md §6). Spend the ledger has already folded into today is
  then counted twice; that is deliberate and fails closed.
- Exit 4 ends the attempt. Record the refusal; do not retry, split, or override.
- The one exception is a `park`. A full day's ceiling does not refuse the lane's
  exact park content (`park_passes_ceiling`); an invalid `max_spend` still refuses.
  The park's entry still holds its `max_spend`. The CI gate has no waiver, so on that
  day it refuses the park's own run, which spends nothing. That red run is expected;
  resolve it like any other.

## 6 · Dashboard single-writer + git hygiene

`fire_trigger.py` writes the trigger file and the journal, commits and pushes exactly
those two, and restores `ops/dashboard.json` afterwards — its queue-block update is a
side effect that only the daily Routine keeps (`--keep-dashboard`, which the Routine's
prompt passes; the Routine commits the dashboard itself, in its §2a spend fold and its
step 6, and the guard hooks refuse those commits outside the Routine's environment). No
other session commits the dashboard, and none needs to revert it any more.

`--no-git` writes the files without committing; it is for inspection. A hand `git push`
that carries a trigger-file change is refused by the guard hooks and by
`.githooks/pre-push`, so a real fire is always `fire` in its default git mode, then
`resolve` once the run lands; when `fire` exits 1 because the push was rejected,
`publish` is the sanctioned re-push (rebase onto the moved branch, tokened push,
refuses anything beyond one known trigger file and the journal, requires the trigger file to differ from origin in the final tree, and corrects the entry's stamp and paid commitment from the pushed params). One fire per invocation; never a second `fire` before the
first has pushed (a second write replaces the trigger content, CI fires once, and the
first fire's journal entry occupies a slot for 8h — 2026-07-21).

## 7 · Park (after every real fire lands)

A trigger file at rest is a loaded default that any merge, rebase or cherry-pick can
re-fire (the resting-state rule in `AGENTS.md`), so its committed content must be the
lane's cheapest no-op: its entry in `PARK_DEFAULTS` in the script. Once a real fire's
run has landed and its entry is resolved (harvest-resolve), park that lane:

```
python scripts/fire_trigger.py park --trigger <name> --ignore-settle
```

- `--ignore-settle` is legitimate here only because that resolve followed a
  confirmed-terminal check in GitHub Actions (§4; harvest-resolve Step 4). Without
  one, wait out the settle window and park without the flag.
- A park is a real fire. It writes the lane's `PARK_DEFAULTS` entry plus `_parked` and
  a fresh `_nonce`, goes through `fire`'s guards (queue, settle, keys, budget),
  journals an entry, and runs the lane's no-op once. Resolve that entry like any other.
  Most parks commit nothing (`commit_outputs` is false wherever the lane has the key),
  so their landing is the run's conclusion in GitHub Actions. Three lanes have no
  commit flag, so their parks land what those lanes always land (harvest-resolve
  Step 3): `scenario-generation` a one-pair batch with its sidecar,
  `model-evaluation` a cost sidecar and the evaluation export, and `archive-renders`
  the `park-noop` Release zip plus `render_archives/park-noop.manifest.json`,
  committed when it changed.
- A full day's ceiling does not refuse a park (§5, the one exception).
- Park only a lane that is not parked already (§8 step 4 lists them): the fresh
  `_nonce` makes every park a change, so parking a parked lane runs its no-op again
  for nothing.
- `park --all` parks every parkable lane in turn and stops at the first refusal; it is
  for cold starts. `pab-probe` has no park default (its workflow lives only on the PAB
  branch).
- `--keep-dashboard` is the Routine's alone (§6).

## 8 · Merges, rebases and cherry-picks

Merging is the owner's (`AGENTS.md`, *Pull request workflow*); this is the procedure
when the owner asks a session to merge by hand. A commit that changes a trigger file
fires that lane when it reaches an existing ref, and `git merge`, `rebase` and
`cherry-pick` can make commits that `pre-commit` never sees (`.claude/hooks/README.md`).
For a merge into `main`, or into whichever branch you will push:

1. **Trigger files: the target's, unchanged.** Merge onto a freshly fetched tip, from a
   clean tree (`git checkout -- ops/dashboard.json` drops any queue side effect a
   `--keep-dashboard` run left). Before committing the merge, run
   `git checkout HEAD -- .github/trigger/`; then
   `git diff --cached --name-status HEAD -- .github/trigger/` must print nothing.
   A line starting `A` is a trigger file only the other side has: stop and ask the owner
   rather than deleting it.
2. **Journal: ORDERED UNION** (`docs/operators_handbook.md` §4, *Journal conflict*):
   every entry of both sides once, deduplicated on `(fired_utc, trigger)` preferring the
   target's copy (the handbook's "remote" copy: the branch you will push to), sorted by
   `fired_utc`, every line valid JSON. Never lose a resolution:
   `resolved` and `evicted` only go from false to true and `resolved_utc` never changes
   (`journal_drops_remote_entries`), so where two copies of one entry differ, keep those
   fields from the copy that set them. Afterwards `python scripts/fire_trigger.py status`
   must show no entry you know to be terminal as active.
3. **Dashboard: the Routine's copy, wholesale.** `git checkout HEAD -- ops/dashboard.json`
   when the target is `main`; never merge its contents by hand (single writer, §6).
4. **Re-check the parks** once the merge is committed. `git diff ORIG_HEAD HEAD --
   .github/trigger/` must print nothing, and every lane the target had parked must still
   be parked:
   ```
   python - <<'EOF'
   import json
   from scripts.fire_trigger import PARK_DEFAULTS, TRIGGER_DIR_RELPATH, is_park_params
   for t in sorted(PARK_DEFAULTS):
       path = TRIGGER_DIR_RELPATH / f"{t}.json"
       params = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
       print(t, "parked" if isinstance(params, dict) and is_park_params(t, params) else "NOT PARKED")
   EOF
   ```
   A lane NOT PARKED with no active journal entry holds a real config at rest: park it
   (§7) once its last run is confirmed terminal. `archive-renders` is unparked by design
   from the Routine cycle that fires its PNG sweep until the next cycle re-parks it.
5. **Push; a refusal is the signal.** `.githooks/pre-push` and the Bash guard refuse a
   push that changes `.github/trigger/` on an existing ref unless `fire_trigger.py`
   makes it. After a merge, that refusal is the expected sign that step 1 was missed:
   never route around it. The merge commit has not left this checkout, so drop it
   (`git reset --keep ORIG_HEAD`, which refuses rather than discard uncommitted work)
   and merge again from step 1. If the target moved before your push, redo the merge on
   the new tip; do not `pull --rebase` over a merge, which replays the merged branch's
   commits one by one.

Three cases those steps do not cover:

- **A pull request merged in the GitHub UI** runs no hook. A trigger file in the pull
  request's own diff fires that lane on `main` when it merges, and a dashboard in it
  overwrites the Routine's. Before asking for a merge, `git fetch origin main` and check
  that `git diff --name-only origin/main...HEAD -- .github/trigger/ ops/dashboard.json`
  prints nothing.
- **Merging `main` into a PR branch** to bring it up to date cannot be made safe by the
  steps above once `main`'s trigger files have moved since the branch point: keeping the
  branch's files puts its older content into the pull request's diff (the check above
  catches it), and taking `main`'s fires those lanes on the branch (pre-push refuses the
  push). Ask the owner instead.
- **Rebases and cherry-picks** replay commits, and one that changes a trigger file
  re-fires it when pushed. Never replay a fire commit by hand; `fire_trigger.py publish`
  is the only re-push of one (§3, exit 1).

## Never

- Never fire a trigger any way other than `scripts/fire_trigger.py` (no hand edits to
  `.github/trigger/`, no direct workflow dispatch, no editing `.github/workflows/`).
- Never use `--force-evict` or `--override-budget`, and never use `--ignore-settle`
  without a confirmed-terminal check in GitHub Actions.
- Never stack a third fire into a lane, and never fire into a group with a mid-flight
  run whose expected outputs are incomplete.
- Never resolve a journal entry on partial landing; never hand-edit
  `ops/trigger_journal.jsonl` (the exceptions: repairing a corrupt line the script
  hard-stops on, by hand, as its error message instructs; and the ORDERED UNION that
  resolves a rebase or merge conflict, §3 and §8).
- Never pass `--keep-dashboard` outside the daily Routine session.
- Never let a merge or revert change a trigger file — restore the target branch's
  trigger files before committing the merge (§8), or you re-fire runs and double-spend.
