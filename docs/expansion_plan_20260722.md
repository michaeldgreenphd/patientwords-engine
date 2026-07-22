# Sample-size expansion — staged plan (2026-07-22, owner directive)

Companion to the wording-gap rename (landed same day, isolated commits).
Binding sequencing rule: a claim-bearing sentence is renamed only if its n is
off this list or the sentence states its current n inline — satisfied by
construction, since the rename swapped terms inside the owner's sentences and
every affected count (steering 4/5-5/5-4/5, translation 8/20, placebo
+1.9 vs +0.5 on 14 pairs, dialect 27%-34%) remains stated. Page prose stays
the owner's; data payloads update as results land.

Fires ONLY via fire_trigger.py under routine queue/budget discipline. $0
lanes first; every paid piece needs explicit owner approval before firing.

## P1 (first wave)

| # | Item | Lane | Est. actual | Ceiling ask | Status |
|---|---|---|---|---|---|
| 1 | Paraphrase noise floor 9 → 50+ baselines (benchmark every page quotes — FIRES FIRST, binding) | generation (paid) + trace ($0) | ~$0.08 | 0.15 | APPROVED 2026-07-22; no floor-quoting sentence re-anchors until the new floor lands |
| 2 | Steering arms 20 → 100 pairs incl. placebo | circuit-trace steer ($0) | $0 | — | queued behind current backfill |
| 3 | Translated-downgrade recovery 20 → 100 | trace + haiku translations (paid) | ~$0.16 | 0.25 | APPROVED 2026-07-22 |
| 4 | Translation-at-scale gemma-2-2b 37 → 100+ | haiku translator (paid) | ~$0.13 | 0.25 | APPROVED 2026-07-22 |
| 5 | Dialect matrix K=3 re-traces per cell | circuit-trace ($0) | $0 | — | queued |
| 5b | Dialect: +30 terms (matrix 20 -> 50 baselines, ~$0.01/baseline observed) | generation (paid) | ~$0.30 | 0.40 | APPROVED 2026-07-22; K=3 re-traces ($0) first |

## P2

| # | Item | Lane | Est. actual | Ceiling ask | Status |
|---|---|---|---|---|---|
| 6 | Activation patching 9 → 50 | activation-patching ($0) | $0 | — | BLOCKED: restore activation_patching.yml to main first (audit item) |
| 7 | Quadrants 4 → 50 (~$0.006/item) | scenario-generation (paid) | ~$0.28 | 0.40 | APPROVED 2026-07-22 |
| 8 | Model-eval audit 10 → 100 items per model (haiku) | model-evaluation (paid) | ~$0.40 | 0.60 | HELD by owner pending item-source answer (see re-proposal in session log 2026-07-22) |
| 9 | jlens depth router classes (10/18/4) + transport census (23/side) | jlens backfill ($0) | $0 | — | already converging via the backfill loop |

## P3

Loglens arm over remaining batches ($0, unblocks the loglens exporter
wiring); retrace 72 → 100 ($0, strengthens repeatability n).

Paid total if all approved: ~$1.15 actual, ~$1.85 in ceilings — spread over
2-3 days under the $2/day guard alongside the advice arm. $0 items enter
their lanes as current work clears; no third fire ever stacks.

## Binding conditions (owner, 2026-07-22)

1. **Ledger first — CONFIRMED SATISFIED before any expansion fire:**
   `ledger_update.py --advice-dir` (default `data/advice`) folds
   `responses_*/judgments_*.report.json` sidecars into the same spend totals
   (landed 2026-07-21 with regression tests in `tests/test_ledger_update.py`;
   proven live 2026-07-22: the advice archive's cumulative sidecar is in
   `spend.entries_seen` and today's ledger line reads $0.9646→$1.26 as advice
   runs landed). Advice sidecars additionally carry
   `cost_basis: cumulative_from_records` so per-stem overwrites can never
   under-count (2026-07-22 fix).
2. **Holdout exclusion (items 3 and 4):** the pair selections for the
   recovery expansion and translation-at-scale MUST mechanically exclude
   `tierb_split == "holdout"` rows via the tierb split guard before any fire;
   selection scripts assert it and record the excluded count in the fire note.
3. **Sequencing:** item 1 (paraphrase floor) fires before any other paid
   expansion; floor-quoting site sentences are not re-anchored until the new
   floor lands.
4. **Item 1/5b seed discipline:** the dialect-baselines generator takes the
   first `num_baselines` usable seed pairs with NO dedup against landed
   dialect batches — every expansion fire uses a dedicated committed seed
   file whose pairs exclude both the already-used baselines and the Tier B
   holdout, so nothing is paid for twice.
