# Handoff: disk pressure (2026-07-26, weekend babysitter)

At ~21:00 UTC Sun the dev container's disk hit 100% (74M free) and blocked a
git rebase mid-babysitter ("could not detach HEAD"; a disk-full pull had left
57 untracked trace_out render strays that then blocked the next checkout).

RECOVERY DONE: cleared /root/.cache/* (~2.9G) → 2.6G free; `git clean -fd
trace_out/` removed the stray partial-checkout renders (authoritative copies
were already committed on origin, "behind 2"); rebased + pushed the pending
fire cleanly. No data lost, branch in sync.

ROOT CAUSE: long-term bloat, not the weekend rate. `.git` = 8.8G,
`trace_out/` = 12G (weeks of committed renders). The weekend's incremental
renders (~13MB/window) only tipped an already-near-quota disk over. Remaining
weekend trace work (~150 pairs ≈ 114MB) fits inside the freed 2.6G, so this
does NOT block completion.

FOR THE NEXT CYCLE (Mon): reclaim space in a proper maintenance step —
`git gc --aggressive` on the bloated `.git` (do it with >5G free; gc needs
scratch), and consider a local `git sparse-checkout` cone excluding
`trace_out/**` render HTML/PNG (the ops work only needs `batch_summary*.json`).
CI workflows already sparse-checkout; the DEV clone does not. Not urgent; $0.

## RESOLVED 2026-07-28 — sparse-checkout excluding trace_out PNGs

Disk reached 632M free / 99% used just as the trace backfill completed, below
the 800M guard and too thin for the 13:00 republish (the same condition broke a
rebase mid-push on 07-26).

**Action:** non-cone sparse-checkout on the DEV clone excluding
`trace_out/**/*.png` (patterns: `/*` then `!/trace_out/**/*.png`).
**Result: 632M -> 9.4G free (99% -> 75%).** The PNGs were 8.8GB across 3,570
files; the 4.2GB of HTML renders and every `batch_summary*.json` are untouched.

**Why this is safe, not destructive:**
- `git status` reports **0 changes** — sparse-checkout makes git treat the files
  as intentionally absent, NOT deleted. A stray `git add -A` cannot commit their
  removal. (Plain `rm` would have been dangerous for exactly that reason.)
- The PNGs remain committed on origin and in `.git`; nothing is lost.
- Fully reversible: `git sparse-checkout disable` restores them.
- CI is unaffected — workflow runs do their own fresh checkout.
- Verified after: 19T reads back 100/100 result records, HTML renders present.

**One known, accepted degradation:** `export_frontend_simulated.py` copies a
single raster even under the default `--no-pngs` — the og:image at
`modes/simulated/preview.png` (script line ~333). With PNGs absent locally that
copy silently no-ops, so the site keeps its EXISTING preview.png rather than
refreshing it. The site does not break. To refresh it deliberately:
`git sparse-checkout disable`, re-run the export, then re-enable.

**Still outstanding:** `.git` is 9.7GB. `git gc` now has ample scratch space
(9.4G free) and should be run in a maintenance slot — it was previously unsafe
to attempt below 1G.
