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
| 1 | Paraphrase noise floor 9 → 50+ baselines (benchmark every page quotes — EARLY) | generation (paid) + trace ($0) | ~$0.08 | 0.15 | AWAITING APPROVAL |
| 2 | Steering arms 20 → 100 pairs incl. placebo | circuit-trace steer ($0) | $0 | — | queued behind current backfill |
| 3 | Translated-downgrade recovery 20 → 100 | trace + haiku translations (paid) | ~$0.16 | 0.25 | AWAITING APPROVAL |
| 4 | Translation-at-scale gemma-2-2b 37 → 100+ | haiku translator (paid) | ~$0.13 | 0.25 | AWAITING APPROVAL |
| 5 | Dialect matrix K=3 re-traces per cell | circuit-trace ($0) | $0 | — | queued |
| 5b | Dialect: additional terms | generation (paid) | ~$0.10 | 0.20 | AWAITING APPROVAL (scope: how many terms?) |

## P2

| # | Item | Lane | Est. actual | Ceiling ask | Status |
|---|---|---|---|---|---|
| 6 | Activation patching 9 → 50 | activation-patching ($0) | $0 | — | BLOCKED: restore activation_patching.yml to main first (audit item) |
| 7 | Quadrants 4 → 50 (~$0.006/item) | scenario-generation (paid) | ~$0.28 | 0.40 | AWAITING APPROVAL |
| 8 | Model-eval audit 10 → 100 items per model (haiku) | model-evaluation (paid) | ~$0.40 | 0.60 | AWAITING APPROVAL (sizing to confirm) |
| 9 | jlens depth router classes (10/18/4) + transport census (23/side) | jlens backfill ($0) | $0 | — | already converging via the backfill loop |

## P3

Loglens arm over remaining batches ($0, unblocks the loglens exporter
wiring); retrace 72 → 100 ($0, strengthens repeatability n).

Paid total if all approved: ~$1.15 actual, ~$1.85 in ceilings — spread over
2-3 days under the $2/day guard alongside the advice arm. $0 items enter
their lanes as current work clears; no third fire ever stacks.
