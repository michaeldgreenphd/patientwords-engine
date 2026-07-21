---
name: harvest-resolve
description: Harvest landed push-to-run CI outputs and resolve ops/trigger_journal.jsonl entries — use for "harvest the runs", "did CI finish", before resolving or chaining any fire, or during the daily cycle's harvest step.
---

# Harvest landed CI runs and resolve journal entries

Resolving is a queue action, not bookkeeping. A journal entry is ACTIVE while
`resolved` and `evicted` are both false and it is younger than 8h. `resolve`
stamps `resolved_utc` (opening a 15-minute settle window) and, for paid entries,
releases the in-flight `max_spend` hold. Resolving a run that has not fully
landed re-opens the 2026-07-09 queue-eviction seam: the resolved run may still
occupy the GitHub concurrency group, so a subsequent same-trigger fire can enter
as a third run and silently supersede the still-pending run.

## Step 1 — Sync (outputs interleave by design)

```bash
git pull --rebase        # working branch: trace outputs land here
git fetch origin main    # generation archives land on main
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

- **circuit-trace / logits-eval** (dispatched branch): part files under
  `trace_out/<pairs-stem>/` (non-default models: `trace_out/<stem>__<model>/`).
  CI renames each chunk's summary to `batch_summary.part_NN.json`, NN = 1-based
  start offset. Expect ONE part per fired offset, per model. Always glob
  `batch_summary*.json`; `results[i]["index"]` is the global 1-based join key
  back into the batch file — use it to confirm per-pair coverage (mid-batch
  failures truncate `results` with no per-pair error records).
- **jlens-readout** (dispatched branch): part files under
  `trace_out/<stem>__jlens_<model>/` for each fired offset/limit chunk. The
  part is written only at chunk end — a missing part means the whole chunk was
  lost; refire that chunk, do not hunt for partial output.
- **scenario-generation / model-evaluation** (**main**; paid):
  `data/simulated/<batch>.json` PLUS its `<batch>.report.json` cost sidecar —
  both must exist. Check via `git diff --stat HEAD...origin/main -- data/simulated/`.
  When measurement needs the batch on this branch:
  `git checkout origin/main -- data/simulated/<batch>.json data/simulated/<batch>.report.json`.
- **archive-renders**: the workflow commits
  `render_archives/<tag>.manifest.json` with the Release URL filled in, and the
  Release holds the zip. Manifest committed + Release present = landed.
- **activation-patching**: branch-relative — check whether the DISPATCHED branch
  carries `activation_patching.yml` (`git ls-tree --name-only <branch> .github/workflows/`).
  Absent (e.g. main): the entry is a phantom that will never land — record a blocker.
  Present (the working branch): harvest it like any other lane (part files under
  `trace_out/`).

## Step 4 — Verify terminality before resolving

Landed-locally is not terminal. Confirm the GitHub run itself concluded, via:

- the GitHub API — `gh run list --branch <branch> --limit 10` (or the GitHub
  MCP actions tools): the run for this fire shows `completed`; or
- the landing commit — `git log origin/<branch> -- 'trace_out/<stem>*'` shows
  the CI commit containing the LAST expected part (the final offset).

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
- Single-writer rule: `resolve` rewrites the queue group in
  `ops/dashboard.json`. If this session is NOT the daily Routine session,
  revert that dashboard side effect and commit the journal change only.

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

## Exit codes (`fire_trigger.py`)

0 ok/fired · 1 git failure · 2 queue refusal (2 active — never add a third) ·
3 bad params · 4 budget refusal · 5 no-op fire · 6 settle refusal. A hard stop naming a corrupt journal line: the ONLY permitted hand edit to
`ops/trigger_journal.jsonl` is repairing that single named line, exactly as the
error message instructs; record the repair in blockers/notes. (Identical policy in
fire-trigger-safe.)

## Never

- Never resolve on partial landing — that is the eviction seam.
- Never resolve to free a queue slot or to release an in-flight budget hold.
- Never hand-edit `ops/trigger_journal.jsonl`, anything under
  `.github/trigger/`, or spend numbers (`fire_trigger.py` and
  `ledger_update.py` are the only writers).
- Never use `--force-evict` or `--override-budget`; `--ignore-settle` only
  after GitHub-confirmed terminality.
- Never rewrite or delete anything under `data/simulated/` (append-only), and
  never correct intentional misspellings in landed batches.
- Never treat a silent queue or an expired entry as success.
- Never write secrets, keys, or holdout phrases into any file — both repos are
  public.
