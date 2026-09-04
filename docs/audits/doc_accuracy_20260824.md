# Doc-accuracy sweep — 2026-08-24 (Monday)

Mechanical cross-checks per `docs/routine_standing_prompt.md` §2b. Findings are
recorded, not repaired: the sweep does not "fix" drift.

## 1 · Trigger three-way parity (fire_trigger TRIGGERS ↔ `.github/trigger/` ↔ workflows)

| Source | Keys |
|---|---|
| `fire_trigger.py` TRIGGERS | 9 |
| `.github/trigger/*.json` | 8 |
| referenced by a workflow on this branch | 8 |

- `pab-probe` registered in TRIGGERS with no trigger file and no workflow here —
  unchanged since the 08-17 sweep, benign, branch-scoped by
  `workflow_reads_trigger()`. No action.
- The other eight keys map 1:1 to a trigger file and to exactly one workflow:
  activation-patching→activation_patching.yml, advice-eval→advice_evaluation.yml,
  archive-renders→archive_renders.yml, circuit-trace→circuit_trace_evaluation.yml,
  jlens-readout→jlens_readout.yml, logits-eval→logits_evaluation.yml,
  model-evaluation→model_evaluation.yml, scenario-generation→scenario_generation.yml.
- **NEW — `CLAUDE.md`'s trigger table lists seven of the eight live triggers.**
  `advice-eval` / `advice_evaluation.yml` is absent from the table even though it
  is a live key on this branch and a **paid** one (`PAID_TRIGGERS` in
  `fire_trigger.py:67`; it bills OpenRouter/Anthropic and carries its own $10/day
  OpenRouter ceiling). A reader orienting from CLAUDE.md alone would not learn
  that the repo has a fourth paid lane. Cosmetic for the gates, misleading for
  cost orientation. Left for the owner.

## 2 · Site data contracts vs `data/` inventory vs engine script inventory

Clean, matching both spellings per the 08-17 note (bare filename in the table,
`data/`-prefixed in the prose, plus the `{csv,json}` brace form used for
`simulated_archive`).

- Every payload named in `../patientwords/CLAUDE.md` exists in the site `data/`
  directory.
- Every file on disk is cited, except the two `*.sample.json` development
  fixtures, which that document explicitly excludes ("not fetched by any page").
- Every engine writer script named in the contract table exists under `scripts/`.

## 3 · `extract_site_text.py` PAGES vs live pages

Forward direction clean: all **12** PAGES entries resolve to a file on the site.
(The 08-17 sweep recorded 5 entries; the list has grown since.)

Reverse direction checked for the first time — 20 `.html` files live on the site
outside `modes/`, so 8 are not in PAGES:

| Page | Bytes | Verdict |
|---|---|---|
| `clinical/index.html` | 20,418 | **NEW finding — substantive page, no redirect meta, not extracted** |
| `share/card.html` | 3,290 | share/OG card, not prose; benign |
| `404.html` | 5,099 | error page; benign |
| `answer-depth/index.html` | 390 | redirect stub |
| `llm/natural.html` | 429 | redirect stub |
| `model-evaluations/index.html` | 390 | redirect stub (2026-07-14 consolidation) |
| `syntax-differences/index.html` | 431 | redirect stub |
| `word-differences/index.html` | 427 | redirect stub |

`clinical/index.html` is the only real gap: any prose claim on that page is
outside whatever `extract_site_text.py` feeds. Not a `claim_check` failure — the
claims manifest is a separate mechanism — but a page the text-extraction path
does not see. Recorded, not repaired.

## 4 · Amendments cited in code vs the amendment docs

- Present and resolvable: `prereg_amendment2_depth.md`,
  `prereg_amendment3_holdout.md`, `prereg_amendment4_steering.md`,
  `prereg_divergence_log.md`.
- `docs/preregistration_amendments.md` still main-only, now cited from **seven**
  files (`ops/dashboard.json`, `docs/decisions_20260815_owner.md`,
  `docs/routine_standing_prompt.md`, `docs/HANDOFF_20260804.md`,
  `docs/tierb_freeze_checklist.md`, and the 08-10 and 08-17 sweep reports
  themselves). The 08-17 finding stands unchanged: `tierb_freeze_checklist.md:17`
  is still the one citation that presents it as a live source rather than a
  caveat.
- No standalone amendment-1 document; §4b's "Amendments 1-3" citation still has
  no direct target for amendment 1. Unchanged from 08-17.

## 5 · Handoff docs vs the actual tree

`docs/HANDOFF_20260804.md`, `HANDOFF.md`, `docs/ops_routine_spec_20260804.md`,
`docs/critic_standing_prompt.md`, `ops/README.md` and
`docs/fresh_session_bootstrap.md` are all present. The two absences the 08-17
sweep recorded (`docs/preregistration_amendments.md`,
`docs/site_text_outline.md`) are unchanged.

## Summary

No blocking drift; no gate and no published number is affected. Two findings are
new this week and both are left for the owner rather than repaired here:

1. `CLAUDE.md`'s trigger table omits the live, paid `advice-eval` lane.
2. `clinical/index.html` (20 KB of prose) is outside `extract_site_text.py` PAGES.

The three carried-over items from 08-17 are unchanged: the
`tierb_freeze_checklist.md:17` stale citation, the missing `site_text_outline.md`,
and the amendment-1 citation with no target file.
