# Doc-accuracy sweep — 2026-08-17 (Monday)

Mechanical cross-checks per `docs/routine_standing_prompt.md` §2b. Findings are
recorded, not repaired: the sweep does not "fix" drift.

## 1 · Trigger three-way parity (fire_trigger TRIGGERS ↔ `.github/trigger/` ↔ workflows)

| Source | Keys |
|---|---|
| `fire_trigger.py` TRIGGERS | 9 |
| `.github/trigger/*.json` | 8 |
| referenced by a workflow | 8 |

- **`pab-probe` is registered in TRIGGERS but has no trigger file and no workflow
  on this branch.** Benign: `fire_trigger.workflow_reads_trigger()` checks
  per-branch, so a `pab-probe` fire here is refused rather than silently ignored.
  The key is live on the PAB branch only. No action.
- No trigger file lacks a TRIGGERS entry; no workflow references a missing
  trigger file. Parity otherwise clean.

## 2 · Site data contracts vs `data/` inventory vs engine script inventory

Clean. Every payload cited in `../patientwords/CLAUDE.md` exists in the site
`data/` directory (31 files), every file on disk is cited somewhere in that
document, and every engine writer script named in the contract table exists
under `scripts/`.

Note for future sweeps: the contract table backticks bare filenames while the
prose section writes them `data/`-prefixed. A sweep regex that matches only one
spelling reports 11 false "uncited" payloads. Match both.

## 3 · `extract_site_text.py` PAGES vs live pages

Clean. All 5 PAGES entries resolve to a file on the site.

## 4 · Amendments cited in code vs the amendment docs

- Present: `prereg_amendment2_depth.md`, `prereg_amendment3_holdout.md`,
  `prereg_amendment4_steering.md`, `prereg_divergence_log.md`.
- **No standalone amendment-1 document exists.** §4b of the standing prompt
  cites "Amendments 1-3"; amendment 1's content is carried inside
  `HANDOFF_20260804.md` and `prereg_amendment2_depth.md` rather than its own
  file. Not a contradiction, but the citation has no direct target.
- `docs/preregistration_amendments.md` (main-only) is referenced in five places.
  Four are explicit "this file does not exist" caveats. The fifth,
  **`docs/tierb_freeze_checklist.md:17`, cites it as a live source of flags** —
  the one reference that would mislead a reader who followed it.

## 5 · Handoff docs vs the actual tree

Of 19 repo paths named in `docs/HANDOFF_20260804.md`, 2 are absent:

- `docs/preregistration_amendments.md` — known and self-documented (§ above).
- **`docs/site_text_outline.md` — absent and not previously flagged.**

## Summary

No blocking drift. Three items are cosmetic-but-real and are left for the owner
rather than repaired here: the `tierb_freeze_checklist.md:17` stale citation,
the missing `site_text_outline.md`, and the amendment-1 citation with no target
file. None affects a published number or a gate.
