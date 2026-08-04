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
git checkout -B claude/gemma-clinical-colloquial-interp-mavx04 \
  origin/claude/gemma-clinical-colloquial-interp-mavx04 2>/dev/null || true
git pull --rebase origin claude/gemma-clinical-colloquial-interp-mavx04
```

## Site repo (when `../patientwords` is missing)

Clone through the same git proxy the engine remote uses, blobless, without the
466 engine-generated renders under `modes/`:

```bash
cd /home/user
git clone --filter=blob:none --no-checkout \
  "$(git -C patientwords-engine remote get-url origin | sed 's|/patientwords-engine|/patientwords|')" patientwords
cd patientwords
git sparse-checkout set --no-cone '/*' '!/modes/'
git checkout claude/gemma-clinical-colloquial-interp-mavx04
```

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
