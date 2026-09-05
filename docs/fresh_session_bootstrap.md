# Fresh-session bootstrap — repairing the materialized checkout

Written 2026-08-04 after the daily ops Routine's first two fresh-session
firings (13:03 scheduled, 14:58 on-demand) both died without a single push.
Root-cause evidence: the 2026-08-04 interactive takeover session booted in the
same environment and found the engine checkout **broken on arrival** — this
recipe is the repair it used. Every fresh container in this environment should
assume the same state until the environment itself is fixed.

## Symptom

- `git status` in `/home/user/patientwords-engine` shows **thousands of staged
  deletions** (all ~12,900 tracked files marked `D`) plus a handful of `??`
  untracked entries — the git index is empty and only a partial working tree
  (~900 files) was materialized. The bulk of what is missing is `trace_out/`
  (~12,300 render files); the clone is blobless, so nothing is lost.
- `/home/user/patientwords` (the site sibling checkout) may be missing
  entirely.
- HEAD is typically detached at the correct branch tip.

## DO NOT

- **Never `git add -A` / commit / push in this state** — you would commit the
  deletion of the entire repository. If a stop-hook complains about
  uncommitted changes, repair first; the "changes" are phantoms.
- Never `git pull --rebase` before the index is repaired.
- Do not restore all of `trace_out/` — ~12k render files through the blobless
  proxy wastes the session; analysis needs only the `batch_summary*.json`
  files.

## Repair (engine repo)

```bash
cd /home/user/patientwords-engine
pgrep -a git || rm -f .git/index.lock          # clear a stale lock if no git runs
git reset -q                                    # rebuild the index from HEAD
git restore --source=HEAD --worktree -- . ':(exclude)trace_out' ':(exclude)render_archives'
git ls-tree -r HEAD --name-only trace_out | grep -E 'batch_summary[^/]*\.json$' \
  | xargs -d '\n' git restore --source=HEAD --worktree --
git checkout -B main origin/main 2>/dev/null || true
git pull --rebase origin main
```

## Variant B — clean checkout, WRONG or STALE ref (observed 2026-08-11; rewritten 2026-09-04)

A fresh container can also arrive with both repos present, `git status` clean,
and **no staged deletions at all** — but sitting on a session branch (e.g.
`claude/nice-tesla-vemyql`) or on a `main` that predates the last cycle. The
Variant A repair above does not apply and its symptom check passes, so the
trap is silent: `ops/dashboard.json` reads stale, and `seal_check.py` would
exit 2 on an empty sealed set if `tierb.start_utc` is null. Orient from a stale
checkout and every number is wrong. (Until 2026-09-04 the live state lived on
the ops branch `claude/gemma-clinical-colloquial-interp-mavx04` and a `main`
checkout was the wrong branch by definition; engine PR #6 merged that branch
into `main` and retired it, so `main` is now the only working branch in both
repos.)

**Detect it before acting:**

```bash
git rev-parse --abbrev-ref HEAD                       # must be main
git fetch --filter=blob:none --no-tags origin main
git diff --quiet origin/main -- ops/dashboard.json && echo current || echo STALE
python -c "import json;d=json.load(open('ops/dashboard.json'));print(d['updated_utc'],d['tierb']['start_utc'])"
```

A `start_utc` of `None`, or a dashboard that differs from `origin/main`, means
you are not on current `main`. Stop and repair.

**Repair — blobless fetch FIRST, then sparse patterns, then checkout.** A plain
`git fetch` of the working branch is not slow, it is unusable: measured on
2026-08-11 at 2 min and 9.5 min, both killed with the server still compressing
(49% of 12,145 objects). The blobless fetch completed in **1.9 seconds**.

```bash
cd /home/user/patientwords-engine
git fetch --filter=blob:none --no-tags origin main
git sparse-checkout set --no-cone \
  '/*' '!/trace_out/*' '!/render_archives/*' \
  '/trace_out/*/*.json' '/trace_out/*/*.html' \
  '/trace_out/*/jlens_raw/*' \
  '/trace_out/pairs_20260711T051145Z__jlens_gemma-2-2b/*' \
  '/trace_out/pairs_20260711T051145Z__loglens_gemma-2-2b/*' \
  '/trace_out/pairs_20260711T051145Z_txopus*/*' \
  '/trace_out/pairs_20260711T051145Z_txplacebo*/*' \
  '/trace_out/txcorpus_priority*__jlens_gemma-2-2b/*'
git checkout -B main origin/main                         # ~2m45s on 2026-08-11
```

The census-batch `jlens_raw/` patterns on the last five lines are **not
optional**: `export_jspace.py` and the transport/loglens exporters read
`jlens_raw/*.json.gz`, and without them `export_jspace.py` refuses (exit 3) as
it did on 2026-08-09. With them, the full publish chain ran clean on
2026-08-11, `export_jspace.py` included.

The **global** `'/trace_out/*/jlens_raw/*'` line is equally not optional, for a
different reason (added 2026-08-16; blocker `planner-lens-sparse-miscount-20260815`).
`backfill_planner.py:77` measures LENS coverage by globbing that path in the
**working tree**, so whitelisting raw for the census batch alone makes the planner
see 0 raw pairs everywhere else and report `lens+save_raw 3/39` when the git tree
actually holds 39/39 COMPLETE. The planner then re-picks an already-complete batch
(`pairs_20260706T172135Z` 1-2/2 was fired on 08-11 and again on 08-14 for this
reason). With the global pattern the planner reports `lens+save_raw 39/39` and
`[jlens-readout] COMPLETE - no gaps`, which is the truth. Cost: 6,835 `.gz` blobs
across 92 dirs, materialized in well under a minute; `trace_out` goes 3.3G -> 6.6G.
Verified on the 2026-08-16 cycle, which avoided a third wasted fire because of it.

The site sibling needs no such care — it is small, and its working branch is
`main`.

`docs/routine_standing_prompt.md` on `main` is the authoritative copy (since
2026-09-04; before that `main` carried a stale snapshot and the ops branch the
live one). Re-read it after checkout, not before.

## Site repo (when `../patientwords` is missing)

Clone through the same git proxy the engine remote uses, blobless, without the
466 engine-generated renders under `modes/`:

```bash
cd /home/user
git clone --filter=blob:none --no-checkout \
  "$(git -C patientwords-engine remote get-url origin | sed 's|/patientwords-engine|/patientwords|')" patientwords
cd patientwords
git sparse-checkout set --no-cone '/*' '!/modes/'
git checkout main
```

**But re-materialize `modes/` before running the contract gate** (2026-08-16).
`validate_frontend_contract.py` resolves every scenario's `html` field against the
site working tree, so with `modes/` excluded it emits one
`render path missing on disk: modes/simulated/<batch>/index_NN.html` FAIL per
published render — 153 of them on the 08-16 cycle, every one a checkout artifact
(each path was present in `git ls-tree HEAD`). A session that trusts that output
reads a healthy contract as broken, and "repairing" the payload from it would
corrupt a good file. Run `git -C ../patientwords sparse-checkout disable` (925M,
under a minute) before the gate; the true reading that cycle was 0 errors and the
single known orphan-row warning. Verify a suspected FAIL against
`git ls-tree -r HEAD <path>` before believing it.

## Verify before doing anything else

```bash
cd /home/user/patientwords-engine
git status --porcelain | head -3        # must be empty (or a few ' D trace_out/…' renders only)
find trace_out -name 'batch_summary*.json' | wc -l   # ~580+
test -f ../patientwords/data/model_stats.json && echo site OK
```

Only then proceed with the daily cycle (`docs/routine_standing_prompt.md`).
The full test suite additionally needs `pip install pytest matplotlib networkx
pillow` in a fresh container.
