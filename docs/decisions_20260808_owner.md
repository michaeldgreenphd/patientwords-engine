# Owner decisions — 2026-08-08 (recorded by the interactive session)

Owner reviewed the six `decisions_pending` entries from the 2026-08-08 deck in the
interactive session and ruled on three; this doc is the durable record. The daily
Routine folds these into `ops/dashboard.json` on its next cycle (single-writer rule;
this session touched no dashboard prose).

## MEDICAL-FINETUNE-FRAMING-20260808 — APPROVED AS DRAFTED

The sanctioned replacement for every "the two medical fine-tunes are the study's null
cases" sentence (dashboard verdicts, briefs, handoffs), verbatim:

> both medical fine-tunes show a negative mean penalty, and apertus's interval now
> excludes zero; their flip-direction tests remain underpowered (5 and 5 flips) and
> neither supports a claim about downgrade behavior.

Deployment: next daily cycle, per the standing no-self-deploy protocol. No other
phrasing about the medical models is sanctioned.

## JLENS-DEPTH-PINS-20260808 — APPROVED: ADD THE BLOCK

`pairs_20260707T171223Z` (119-pair lens set, completed 2026-08-08) joins the depth
figure as a seventh `--block` pin. Implemented this session; site `data/jlens_depth.json`
regenerated and pushed (branch + main), gates green (contract 0 errors, claim_check
verified, seal CLEAN).

Scope note the owner should know (found during implementation, fixed under the repo's
no-silent-truncation rule with a regression test): `export_jlens_depth.load_summary`
read only `jlens_summary.part_01.json`, so multi-part lens batches were silently
truncated to their first 25 pairs — including two of the six EXISTING pins
(`pairs_20260713T050939Z` 23→92 pairs, `pairs_20260712T163501Z` 23→93). With every part
read and the new block added, the published depth census grows 178 → 436 pairs
(267 retained / 131 absent / 38 suppressed). No site prose hardcoded the old counts
(claim gate verified); the audit's C11 row cites the old 178-pair census and should be
annotated on the next audit pass. Canonical pin list is now the seven blocks in the
committed payload; exemplar unchanged (`pairs_20260711T051145Z` #19).

## OPENROUTER-LANE-UNCEILINGED-20260808 — APPROVED BOTH FIXES, $10/DAY

- `fire_trigger` already enforces a per-lane OpenRouter guard (ported 2026-08-04);
  the $10/day ceiling is now explicit: `ledger_update` writes
  `spend.openrouter_daily_ceiling_usd: 10.0` into the dashboard spend block.
- `ledger_update.check_ceilings` now reports per lane (anthropic vs its
  `daily_ceiling_usd`, openrouter vs `openrouter_daily_ceiling_usd`), with
  dedup-stable sentences.
- First-sight folds of sidecars with `cost_basis='cumulative_from_records'` book
  `run_cost_usd` to the run day; the prior-runs balance folds to lifetime only with a
  ledger bullet (it has no single day, and charging it to one poisoned the daily guard
  on 2026-08-08: a $17.89 campaign total booked to one day). `entries_folded` keeps the
  cumulative baseline so the growth pass's deltas stay exact.
- All under regression tests (`tests/test_ledger_update.py`, 29 pass).

## Not ruled on this session

- `dialect-prose-date-drift-20260730`: resolved in substance since 2026-07-30; entry
  ages out.
- `OPS-CADENCE-SINGLE-POINT`: overtaken by events — the owner-created UI Routine ran a
  full cycle 2026-08-08 13:04Z on the study branch (verified end-to-end). Routine may
  close it citing that run.
- `AUDIT-DECIDED-EXECUTION`: stale as written (prereg signed 2026-07-28; 25 judge items
  coded). One act remains: the pooled-33% caveat sentence — candidates presented to the
  owner 2026-08-08, choice pending.
