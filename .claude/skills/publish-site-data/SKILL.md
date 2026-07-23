---
name: publish-site-data
description: Use when new engine results need publishing to the patientwords site ("publish the data", "republish site data", section 5 of the daily cycle): runs the sanctioned exporter/collector/gate chain in order and pushes data files only — never page text.
---

# publish-site-data

Republish the public site's data payloads after new measurement results land. This is
section 5 of the daily ops cycle ("Publish data, never text"). You publish **data files
only** — the owner edits site text personally; any text edit from this chain collides
with theirs.

## Preconditions

1. Run from the engine repo root. The site must exist as the sibling checkout
   `../patientwords`. If it is missing, stop — do not clone or improvise paths.
2. `git pull --rebase` the working branch and `git fetch origin main` first
   (generation archives land on main; trace outputs land on the branch — they interleave).
3. Only run if new results actually landed (new `trace_out/*/batch_summary.part_*.json`,
   new lens parts, new txcorpus runs). No new results → no republish this cycle.

## The chain (run in this exact order)

**1. Exporter.**
```
python scripts/export_frontend_simulated.py --frontend ../patientwords \
    --stamps <comma-list of batch stamps> \
    --archive-url https://github.com/michaeldgreenphd/patientwords-engine/releases
```
- `--archive-url` is mandatory — it keeps `payload.archive` populated so data-only rows
  link the full render sets on GitHub Releases.
- Do NOT pass `--max-renders` or `--with-pngs`. The current defaults ARE the policy
  (2026-07-21): cap 200 most consequential renders, HTML-only (`--with-pngs` would
  restore rasters — owner-instruction only).
- `--stamps`: every stamp already in `../patientwords/data/simulated_scenarios.json`
  plus newly landed ones. Omitting a published stamp silently drops its scenarios —
  never shrink the list.

**2. Urgency collector.**
```
python scripts/urgency_shift.py --publish ../patientwords
```
Writes the site's `data/urgency_shift.json`. Tier vocabulary is a draft data file; the
site's "draft pending domain review" labels stay exactly as they are.

**3. Wired j-lens exporters — these four ONLY, in this order.**
```
python scripts/jlens_insights.py --site ../patientwords
python scripts/export_jlens_depth.py --block ... --exemplar-stem ... --exemplar-index ... --site ../patientwords
python scripts/export_jlens_transport.py --site ../patientwords
python scripts/export_pair_swaps.py --site ../patientwords --depth ../patientwords/data/jlens_depth.json
```
- For `export_jlens_depth.py`, reuse the pins of the committed
  `../patientwords/data/jlens_depth.json` (same `--block` stems, same exemplar
  stem/index). Pins change only on explicit owner instruction — an ad-hoc pin change
  silently churns the published figure and breaks manifest-guarded prose.
- Exit 3 from `export_jlens_depth.py` = degenerate-exemplar refusal; the good file is
  untouched. Treat any exporter refusal as success-with-no-change. Never hand-patch a
  payload past a refusal.
- `export_pair_swaps.py` runs AFTER depth/insights so its `<batch>#<index>` join is
  current; new batches show target-only until it re-runs. That is expected.
- **Transport wired 2026-07-23 (owner option 1):** the census batch's 25/25 `save_raw`
  runs landed on this branch and a regen reproduced the committed file byte-identically
  except `generated_utc` (identical census numbers and exemplars). It now runs in the
  cycle, after depth and before pair swaps.
- **NOT wired — do not run in the cycle:** `export_jlens_loglens.py`. Its `__loglens_`
  comparison runs are still landing on this branch (first LOGIT_LENS fire 2026-07-23);
  leave the site file as its committed snapshot until a regen is verified to reproduce
  the live structure, same procedure as transport.

**4. Trace-URL restamp.** `python scripts/export_traces_site.py --stamp-only`
Re-stamps every scenario's `trace_url` in the payload for the self-building
patientwords-traces Pages repo (its own Action mirrors nightly at 15:00 UTC).
Stamp-only needs no traces-repo checkout.

**5. Translation at scale — only when txcorpus logits or lens readouts landed.**
`python scripts/translation_scale.py --site ../patientwords`
**Scale-framing gate (owner, 2026-07-15):** the at-scale TABLE auto-updates from data —
sanctioned. Any framing SENTENCE about the scale result is NOT: draft it, put it in the
digest and `decisions_pending`, and wait for owner approval. Never deploy it yourself.

**6. Coverage.** `python scripts/coverage_gaps.py`
Its `steer_topics` block feeds the `topics` param of the next generation fire — corpus
balance is a sampling decision, not an afterthought.

**7. Contract gate.** `python scripts/validate_frontend_contract.py --site ../patientwords`
Exit 0 = holds; 1 = violations; 2 = payload missing/unreadable. Report mode (no
`--strict`) until F-M27's orphan-row trim lands. New ERRORS mean an export broke the
page contract: fix the export and re-run before pushing the site. Never push over errors.

**8. Claim gate.** `python scripts/claim_check.py`
Exit 1 = refreshed data invalidated a hardcoded sentence on the site. Do NOT edit the
prose. Put the exact FAIL line in the digest headline and in `decisions_pending`; the
owner (or the orchestrating session, which holds text-edit sanction) rewrites it. A
`warn:` line means prose was edited and the manifest needs updating — flag it the same
way, do not fix it here.

**8b. Holdout-seal gate (mandatory — also before any ad-hoc export push).**
`python scripts/seal_check.py --site ../patientwords` — exit 0 required to proceed.
Exit 1: ABORT the publish, follow the holdout-seal-check skill's breach protocol.
Exit 2 (empty sealed set): config error (wrong branch), never a pass.

**9. Commit and push.**
- Site: `git -C ../patientwords status` first. Only `data/*.json` and exporter-written
  `modes/simulated/` render files may have changed. Anything else changed → abort,
  revert, investigate. Commit the data payloads, push the branch, then push
  `branch:main` as sanctioned.
- Engine: commit the chain's engine-side outputs (`ops/*.json`, `data/jlens_*.json`)
  to the working branch; `git pull --rebase` before pushing.

## Never

- Never edit page HTML, page text, figures, or labels — data files only, without exception.
- Never run the transport/loglens exporters as part of the cycle (snapshot files).
- Never publish a scale-framing sentence, or any new prose, without explicit owner approval.
- Never remove or soften "draft pending domain review" labels.
- Never hand-edit an exported payload, invent a number, or patch past an exporter refusal.
- Never change depth-exporter pins or render-cap/PNG defaults without owner instruction.
- Never "correct" intentional misspellings in phrase data; never rewrite `data/simulated/`.
- Never write secrets into either repo (both public) and never let holdout phrase text
  reach any output or committed file.
