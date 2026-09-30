---
name: harvest-resolve
description: Harvest landed push-to-run CI outputs and resolve ops/trigger_journal.jsonl entries — use for "harvest the runs", "did CI finish", before resolving or chaining any fire, or during the daily cycle's harvest step.
---

# Harvest landed CI runs and resolve journal entries

Resolving is a queue action, not bookkeeping. A journal entry is ACTIVE while
`resolved` and `evicted` are both false and it is younger than 8h. `resolve`
stamps `resolved_utc` (opening a 15-minute settle window) and frees the queue
slot. It does **not** release a paid entry's `max_spend` from the daily ceiling:
since 2026-09-23 a paid fire's commitment counts for the whole UTC day it was
fired, resolved or not, because nothing else counts its cost until the ledger
folds the sidecar (`fire_trigger.py`, `entry_holds_spend`). That holds even for
a run that never spent: skipped because its push created the branch, refused by
the CI gate, or failed before any provider call. Nothing in this procedure
releases such a hold before 00:00 UTC. Record it, and plan the day's remaining
paid fires around it; do not look for a way to free it (docs/operators_handbook.md
§6). Resolving a run that has not fully landed re-opens the 2026-07-09
queue-eviction seam: the resolved run may still occupy the GitHub concurrency
group, so a subsequent same-trigger fire can enter as a third run and silently
supersede the still-pending run.

## Step 1 — Sync (outputs interleave by design)

```bash
git pull --rebase origin main    # everything lands on main since 2026-09-04
```

## Step 2 — Enumerate active fires

```bash
python scripts/fire_trigger.py status
```

For each active entry, reconstruct exactly what the run owes: the newest fire's
params are in `.github/trigger/<name>.json`; an older active fire's params come
from `git log -p -- .github/trigger/<name>.json`. Note the pairs file, the
model list, and every offset/chunk fired.

## Step 3 — What landing looks like, per lane

- **circuit-trace / logits-eval**: part files under
  `trace_out/<pairs-stem>/` (non-default models: `trace_out/<stem>__<model>/`).
  CI renames each chunk's summary to `batch_summary.part_NN.json`, NN = 1-based
  start offset. Expect ONE part per fired offset, per model. Always glob
  `batch_summary*.json`; `results[i]["index"]` is the global 1-based join key
  back into the batch file — use it to confirm per-pair coverage (mid-batch
  failures truncate `results` with no per-pair error records).
- **jlens-readout**: part files under
  `trace_out/<stem>__jlens_<model>/` for each fired offset/limit chunk. The
  part is written only at chunk end — a missing part means the whole chunk was
  lost; refire that chunk, do not hunt for partial output.
- **scenario-generation** (paid): `data/simulated/<batch>.json`
  PLUS its `<batch>.report.json` cost sidecar — both must exist on `main`.
- **model-evaluation** (paid; `model_evaluation.yml`) writes no batch. It commits a
  cost sidecar `data/simulated/modeleval_<stamp>.report.json` straight to `main`
  (`Model-evaluation cost sidecar`), even when the run crashed, in which case the
  sidecar books `max_spend` and carries an `estimated` note; and, when the run
  produced results, it updates `data/evaluations/model_evaluations_frontend.json`
  (`Model evaluation frontend export (<stamp>)`) when the table changed. Both
  steps run with `always()`, so neither commit proves success: landed = the sidecar
  on `main` without the `estimated` note, and a `success` conclusion (Step 4).
- **archive-renders**: the workflow commits
  `render_archives/<tag>.manifest.json` with the Release URL filled in, and the
  Release holds the zip. Manifest committed + Release present = landed.
- **activation-patching**: harvest like any other lane (part files under `trace_out/`).
- **advice-eval** (paid; `advice_evaluation.yml`). With `commit_outputs: true` one
  CI commit, `Advice eval: <stimuli stem> (append-only archive + sidecars)`, stages
  all of `data/advice/`: for an elicitation fire the archive
  `responses_<stem>.jsonl` and its cost sidecar `responses_<stem>.report.json`, and
  with `judge: true` also `judgments_<stem>.jsonl`, `judgments_<stem>.report.json`
  and `analysis_<stem>.json` (`data/advice/README.md`); a `gen_config` fire skips
  elicitation and commits the stimuli it generated, with their cost sidecar. The archive is append-only and
  shared by every fire on the same stimuli file, so the files existing proves
  nothing: look for this run's commit after the fire commit. That commit step runs
  with `always()`, so a run that failed mid-elicitation still commits what it
  appended: landed = this run's commit AND a `success` conclusion (Step 4). With
  `commit_outputs: false` nothing is committed, the cost sidecar included; the
  run's `data/advice/` is kept only as its `advice-eval-outputs` artifact, which a
  recovery fire merges back with `restore_artifact_run_id`. The park plans zero
  calls, so its landing is its conclusion alone.
- **petri-audit** (`petri_audit.yml`; paid in `mode: run`, `readapt`, and
  `rejudge` with a real judge). What lands depends on the fire's `mode`, `judge`
  and `commit_outputs`, and on the workflow run id (Step 4 finds the run). A paid
  run is refused on any attempt but the first, so its directory is
  `data/petri/runs/run_<run id>_1/`.
  - `preflight` (the park) commits and uploads nothing: landed = its conclusion.
    `dry_run` commits nothing either; when every gate passed it uploads the
    artifact `petri-audit-exports-<run id>-<attempt>` (30 days) beside the raw log
    artifact: landed = `success` and the exports artifact present.
  - `run`: the cost sidecars `run_<id>_1.report.json` (once the target run started)
    and `run_<id>_1.judge.report.json` (once the judge started) are committed
    even when the run failed, either inside the outputs commit or on their own as
    `Petri audit: run_<id>_1 cost sidecars`, so a sidecar alone is not a
    landing. With `commit_outputs: true` the outputs commit,
    `Petri audit: run_<id>_1 (sanitised export, transcripts, manifest)`, is made
    only when every earlier step passed (the seal check, `verify-chain` and
    `verify-run` included) and adds `manifest.json` and the other adapted files
    (`PETRI_ADAPTED_FILES` in `scripts/fire_trigger.py`): landed = that commit and
    `success`. With `commit_outputs: false` only the sidecars are committed and the
    outputs survive as the 30-day exports artifact: landed = sidecars, `success`,
    and that artifact.
  - `readapt` writes into the SOURCE run's directory,
    `data/petri/runs/run_<source_run_id>_1/`, beside its landed target sidecar,
    which is never rewritten. Its own judge sidecar,
    `run_<source_run_id>_1.readapt_<this run id>.judge.report.json`, is committed
    once its judge started, failure or not; with `commit_outputs: true` the adapted
    files commit as `Petri audit: run_<source_run_id>_1 (sanitised export,
    transcripts, manifest; re-adapted by workflow run <this run id>)`. Landed =
    that commit, the readapt's judge sidecar, and `success` (with
    `commit_outputs: false`: the judge sidecar, `success`, and the exports
    artifact).
  - `rejudge` with a real judge writes one directory per stem in `source_runs`:
    `data/petri/rejudge/<judge slug>/<stem>/` with `judgments.jsonl`,
    `analysis_rows.jsonl`, `rejudge_manifest.json` and the judge sidecar
    `<stem>.rejudge_<run id>.judge.report.json`. The sidecars are committed
    whenever a judge started (`Petri rejudge: cost sidecars (workflow run <id>)`).
    With `commit_outputs: true` the verified re-grades commit as
    `Petri rejudge (exploratory): <judge> over <stems> (workflow run <id>)`; that
    step runs with `always()` once verification passed, so it can land some stems
    after a later stem's judge aborted. Landed = a `rejudge_manifest.json` for EVERY
    stem the fire named, and `success`; fewer is partial landing. With
    `commit_outputs: false` only the sidecars are committed and the verified
    re-grades survive as the 30-day artifact `petri-audit-rejudge-<run id>-<attempt>`:
    landed = the sidecars, `success`, and that artifact.
  - `rejudge` with `judge_model: mockllm/judge` (the free rehearsal) commits
    nothing: landed = `success` and the artifact
    `petri-audit-rejudge-<run id>-<attempt>`.

## Step 4 — Verify terminality before resolving

Landed-locally is not terminal. Confirm the GitHub run itself concluded. The run
for a fire is the push run created just after the entry's `fired_utc`, on the
lane's workflow (`docs/triggers.md` names it); its head commit is the fire commit
(`git log -n 5 --format='%H %s' -- .github/trigger/<name>.json`), or the journal
correction that `fire_trigger.py publish` pushed on top of it. Check it via:

- the GitHub CLI, where it is installed: `gh run list --workflow <workflow>.yml
  --branch main --event push --limit 10 --json
  databaseId,headSha,status,conclusion,createdAt` finds the run, `gh run view
  <databaseId>` shows its status, conclusion and jobs, and `gh api
  repos/{owner}/{repo}/actions/runs/<databaseId>/artifacts` lists its artifacts; or
- the GitHub Actions API through the `actions_list` / `actions_get` MCP tools, in
  remote sessions, where `gh` is not installed: the same run, `completed`; or
- the landing commit — `git log origin/<branch> -- 'trace_out/<stem>*'` shows
  the CI commit containing the LAST expected part (the final offset). Not for
  advice-eval, petri-audit or model-evaluation: their cost-sidecar commits (and
  advice-eval's and model-evaluation's output commits, and a petri rejudge's
  re-grade commit) run under `always()` and are made even when the run failed, so
  for those lanes only the run's conclusion shows that it succeeded.

Resolve ONLY when ALL expected outputs for that fire have landed — every offset
times every model. Partial landing: do NOT resolve, AND do not fire anything new
into that group this cycle. Wait.

## Step 5 — Resolve

```bash
python scripts/fire_trigger.py resolve --trigger <name>   # oldest active entry
```

- Exits 0 even when there is nothing to resolve — read stdout; "no active
  journal entries" means nothing changed.
- `--all` only when EVERY active entry for the trigger is verified terminal.
- Name the landed artifacts that justified the resolve in your commit/notes.
- The settle window now applies: a same-trigger fire within 15 min is refused
  (exit 6). That refusal is correct — wait it out. `--ignore-settle` is
  legitimate ONLY after Step 4's GitHub-side confirmation; never to rush a
  still-running group.
- `resolve` updates the queue group in `ops/dashboard.json` and restores the file
  unless `--keep-dashboard` (daily Routine only); commit the journal change.

## Step 6 — Missing outputs are blockers, never silence

A silent queue is not success. If an expected output has not landed and the run
failed, vanished, or never appeared: leave the entry active and record the gap —
in `ops/dashboard.json:blockers` if this session is the dashboard writer,
otherwise in the handoff/digest for the Routine session — naming the trigger,
`fired_utc`, and exactly which offsets/artifacts are missing. Never resolve to
clear it.

## Expiry (8h) is a safety valve, not process

Entries drop from the active set after 8h (`MEDLANG_TRIGGER_EXPIRE_HOURS`,
default 8; chunked runs never exceed ~6h). Never wait for expiry instead of
resolving, and never read an expired entry as "it must have landed" — an expired
unresolved entry means a harvest was missed. Verify its outputs now and record
the result.

## Exit codes, settle window, journal repair

Defined once, in fire-trigger-safe (§3–§4); apply them as written there. The only
permitted hand edits to `ops/trigger_journal.jsonl` are repairing the single corrupt
line the script names, exactly as its error message instructs, and the ORDERED UNION
that resolves a pull, rebase or merge conflict (fire-trigger-safe §8); record either.

## Never

- Never resolve on partial landing — that is the eviction seam.
- Never resolve to free a queue slot. (Resolving cannot free budget either: a paid
  fire holds its commitment for its whole UTC day.)
- Never hand-edit `ops/trigger_journal.jsonl` (beyond the two exceptions above),
  anything under `.github/trigger/`, or spend numbers (`fire_trigger.py` and
  `ledger_update.py` are the only writers).
- Never treat a silent queue or an expired entry as success.
