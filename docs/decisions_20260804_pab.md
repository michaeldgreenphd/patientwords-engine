# Owner decisions — PAB integration program (2026-08-04)

Recorded verbatim from the owner's deck reply (deck artifact published this
session; format per `ops/decks/` convention). This doc is the authorization
record for the fires and builds below; the daily Routine session owns folding
these into `ops/dashboard.json:decisions_log`.

```
DECISIONS 2026-08-04 COMORBID-SEED: approve
DECISIONS 2026-08-04 PROMPT-FIX: approve-4-models
DECISIONS 2026-08-04 MULTITURN-N: approve-exploratory
DECISIONS 2026-08-04 SIM-FIDELITY: approve-build
DECISIONS 2026-08-04 TIER-VOCAB-SENS: engine-side-only
DECISIONS 2026-08-04 HARVEST-TRACE: harvest-existing
```

Owner modification, same message: **cut D3 (MULTITURN-N) spend in half.**
Implementation of the cut: keep all 10 cases × 2 literacy arms (pairing power),
drop 8 models → the same 4 models as D2 (PROMPT-FIX) — 2 frontier + 2 mid,
≈80 conversations ≈ $8. Sharing the model set makes D2/D3/D4 directly
comparable and lets the D4 fidelity A/B piggyback on either sweep.

Also approved earlier the same day, already in the build queue:

- **A · Tier crosswalk** — agreement pilot: draft urgency lexicon vs PAB's
  clinician-validated triage rubric on the same transcripts. $0.
  Spec pre-committed in `docs/pab_crosswalk_spec_20260804.md` BEFORE any
  agreement number is computed.
- **B · Dual-judge toggle** — both judge columns carried in the data; site
  displays either with its own provenance label. Pilot on already-scored
  transcripts $0; any advice-arm re-scoring is priced per slice and
  re-authorized before firing.

## Authorized spend under these decisions

| Item | Channel | Ceiling basis |
|---|---|---|
| D1 COMORBID-SEED | Anthropic (haiku), scenario-generation lane, this branch | ≈$0.25, `max_spend` 0.50 |
| D2 PROMPT-FIX | OpenRouter, pab-probe lane (PAB branch) | ≈$8, enforced budget_guard |
| D3 MULTITURN-N | OpenRouter, pab-probe lane (PAB branch) | ≈$8 (halved per owner), enforced budget_guard |

Everything else in the program is $0. All standing ceilings unchanged
($2/day operational Anthropic, $8 Tier B generation); OpenRouter items carry
their own per-run enforced ceilings, per the 2026-08-04 probe precedent.
Cost basis: measured sidecars (≈$0.07/conversation all-in; $0.15–0.24 per
100-pair haiku batch).

## Registration and boundary terms (owner-set)

- D2/D3 are **post-registration exploratory**, labeled as such everywhere.
- D5 tier-vocabulary sensitivity is **engine-side only** — no PAB-derived
  vocabulary ships to the site. The site's draft urgency label stays until
  domain review lands, unconditionally.
- D6 harvested utterances (CC-BY-NC-derived text) stay engine-side; seal check
  before anything derived becomes public in any form.
- Holdout remains sealed; nothing here touches it.

## Execution split

- **This branch / this session:** decisions record, crosswalk spec + analysis
  (A), D1 fire (after the daily cycle's lane use is known — the cycle fired
  ~13:03 UTC and has priority on the generation lane), D5, D6 harvest +
  $0 trace fires (Tier B outranks in every lane).
- **PAB branch (`claude/pab-integration-layers-ufl8dg`) — the parallel
  session's lane:** B fork-side wiring, D2, D3, D4. This session prepares
  configs, prompt variants, and specs as files on this branch under
  `docs/pab_handoff/`; execution on the PAB branch is coordinated with the
  session that owns it, not pushed from here (branch map rule,
  `HANDOFF_20260804.md`).

## Addendum — contingency authorizations (owner, 2026-08-04 evening)

Owner granted all four proposed contingency authorizations verbatim ("Why not
1-4? I have Fable access now so you can monitor, assess, and patch these in
the background"):

1. **INTERIM-CYCLE** — if fresh-session Routine firings keep failing, the
   2026-08-04 takeover session runs the daily cycle inline (exactly one per
   day, `docs/routine_standing_prompt.md` verbatim, all ceilings enforced)
   until the Routine is proven. While invoked, that session holds the
   dashboard/journal writer role through the same three sanctioned paths.
2. **CHANNEL-SPLIT** — spend accounting books Anthropic and OpenRouter as
   separate channels; the $2/day operational guard counts the Anthropic
   channel only (OpenRouter runs keep their own per-run enforced ceilings).
   Implemented same evening: `ledger_update.py` (`by_day_by_channel`,
   `today.<channel>_usd`), `fire_trigger.py` (guard reads `anthropic_usd`,
   pooled fallback fails closed), regression tests in both suites,
   `ops/README.md` contract note.
3. **COMPLETION-FIRES** — a ceiling-stopped PAB sweep's finishing fire for
   unreached cells is pre-approved within the same already-approved total.
4. **D1-RETRY** — one re-fire of the comorbid seed batch within the same
   $0.50 cap if the scheduled fire fails mechanically.

Unchanged and explicitly outside every grant: holdout unsealing, site text,
draft-label rules, and the ceilings themselves.

## Addendum 2 — owner authorizations, 2026-08-07

1. **UN-DEFER-8B** (owner: "undefer the 8B models"): the 2026-07-20 planner
   hold on `meditron3-8b` and `apertus-8b-meditronfo` is LIFTED. Backfill
   planner invocations now pass `--include-8b-medical`; standing prompt §4a
   updated the same day. 8B fires stay chunked small (50-pair legs).
2. **PAB-LANE-PUSH** (owner: "I explicitly authorize you to do this"): this
   session may push to `claude/pab-integration-layers-ufl8dg` for exactly the
   §3 analyze stages of `docs/pab_handoff_20260804.md` — copy the harvest/
   crosswalk scripts + data files over, fire the $0 harvest and crosswalk
   stages on the pab-probe lane, and copy the resulting statistics/harvest
   outputs back to the study branch. Then frame-building + gemma traces +
   j-lens on the study branch's $0 lanes per docs/pab_frame_spec_20260805.md.
   No OpenRouter or Anthropic spend is authorized under this grant.
