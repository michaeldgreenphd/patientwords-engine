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
