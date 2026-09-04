# Doc-accuracy sweep — 2026-08-10 (Monday, standing prompt §2b)

Mechanical cross-checks only; drift is reported, not fixed here.

## 1 · fire_trigger TRIGGERS ↔ .github/trigger/ ↔ workflows — DRIFT (1 key)

8 of the 9 keys in `fire_trigger.TRIGGERS` have both a trigger file and a
workflow that reads it, and there are no orphan trigger files.

**`pab-probe` has neither** — no `.github/trigger/pab-probe.json`, and no
workflow references that path. A `fire --trigger pab-probe` would pass the
key validation (it is a known key), write a new trigger file, journal the
fire, and push — and nothing in CI would run. That is the failure mode the
key-validation exists to prevent, inverted: an unknown key hard-errors, but a
known key with no workflow fails silently. Not urgent (nothing fires it
today; the dashboard shows the lane at 0 active), but it is a live trap.

## 2 · KNOWN_KEYS ↔ push-path `defaults` — CLEAN (7/9), two N/A

Every key in `fire_trigger.KNOWN_KEYS` appears in its workflow's push-path
`defaults` dict for activation-patching, advice-eval, circuit-trace,
jlens-readout, logits-eval, model-evaluation, scenario-generation.
`archive-renders` has no defaults dict (different workflow shape); `pab-probe`
has no workflow at all (item 1).

**Method note carried forward from 2026-08-03:** resolve trigger→workflow by
searching each workflow for the literal `trigger/<key>.json` path, and check
the push-path `defaults` dict, NOT `workflow_dispatch.inputs`. Filename-
similarity matching mis-assigns logits-eval to `scenario_generation.yml` and
reports five phantom missing keys.

## 3 · Site data inventory ↔ frontend CLAUDE.md data contracts — CLEAN

31 files in `../patientwords/data/`; every non-sample file is named in the
frontend CLAUDE.md, either in the "Data contracts" prose or the by-consuming-
page table. (`simulated_archive.csv`/`.json` are covered by the brace form
`data/simulated_archive.{csv,json}` — a literal-name matcher reports these two
as missing; they are not.)

This closes the largest finding of the 2026-08-03 sweep (21 published files
absent from the frontend CLAUDE.md). Fixed in the interim by the by-consuming-
page table.

## 4 · extract_site_text.py PAGES ↔ live pages — DRIFT (2 substantive pages)

`PAGES` lists 10 pages. The site has 19 non-`modes/` HTML files. Of the 9 not
extracted, 7 are correctly out of scope — five redirect stubs (`answer-depth/`,
`model-evaluations/`, `llm/natural.html`, `syntax-differences/`,
`word-differences/`, all ≤431 B) plus `404.html` and `share/card.html`.

Two are substantive prose pages that the extractor does not see:

| Page | Size | What it is |
|---|---|---|
| `simulated-scenarios/scenario.html` | 29.3 KB | per-scenario detail page (collaborator download UI) |
| `llm/code.html` | 14.6 KB | human-coding worksheet |

Impact: ~44 KB of live page text is invisible to every downstream consumer of
`extract_site_text.py` — text review, prose diffing, and any claim sweep that
starts from the extractor's block set. The 2026-08-03 sweep recorded this check
as CLEAN ("10 pages, 371 blocks, matching the deployed set"), so either the
criterion was the extractor's own list rather than the deployed tree, or both
pages post-date it. Reported, not fixed.

## 5 · Amendments cited in code ↔ amendment docs — CLEAN, with a stale path

Amendments 1–4 are all declared (in `docs/prereg_amendment2_depth.md`,
`prereg_amendment3_holdout.md`, `prereg_amendment4_steering.md`, and
`prereg_divergence_log.md`) and all four are cited in code
(`tierb_split.py`, `seal_check.py`, `export_tag_mass.py`,
`convergence_tracker.py`, `translation_scale.py`, `jlens_insights.py`,
`retrace_consistency.py`, `export_archive.py`, `export_jlens_depth.py`).
Nothing is cited that is not declared.

**Stale path in the standing prompt:** §2b names
`docs/preregistration_amendments.md` as the sweep target. That file does not
exist on this working branch — it exists only on `main`, and the branch
replaced it with the per-amendment files above. A session following §2b
literally gets a `FileNotFoundError` and could mis-read that as "no amendments
declared". Owner/orchestrator fix (the standing prompt is not this cycle's to
edit).

## 6 · Handoff docs ↔ the tree — CLEAN

`docs/HANDOFF_20260804.md` (the orientation target) and
`docs/fresh_session_bootstrap.md` (the container-materialization procedure)
both exist. Root `HANDOFF.md` still exists and is still superseded — already
disclosed in the standing prompt §1 item 6, so not new drift.

## Items for `decisions_pending`

- **`pab-probe` trigger key with no CI target** (item 1). Either wire the
  workflow or drop the key from `TRIGGERS`; a session-side "fix" would mean
  hand-creating a trigger file or editing a workflow, both forbidden here.
- **Standing prompt §2b cites a path that does not exist on the ops branch**
  (item 5).
- **`extract_site_text.py` misses two live prose pages** (item 4).
