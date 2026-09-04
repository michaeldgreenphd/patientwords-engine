# Skeptic's read + functionality audit — 2026-07-09 (autonomous batch 1)

Two adversarial agents audited every claim/number on the 10 site pages and
the synthesis. Below: what I already fixed (objective correctness), what
needs your voice/decision, and what's queued for the next autonomous batch.
Nothing here was published in your voice.

## Fixed live (objective — verified in browser, deployed)

1. **Live factual contradiction on the dialect page + homepage teaser.** The
   static prose claimed "8 terms / 6 framings / 48 sentences," "most framings
   move the top word," and a "clinical depression → therapist → doctor under
   Southern US & British" example — none of which exist in the live
   `dialects.json` (5 terms / 8 framings / 40 sentences, 25% flip rate;
   featured term "clinically depressed" → "break"). The page's own JS
   rendered the true counts right next to the false prose. Prose now defers
   to the live matrix; false example removed. (This is engine task #13's
   root — the data is current, the prose was frozen.)
2. **Synthesis honesty correction (the big one).** Ran the new
   `paired_stats_rigor.py` (dedupe-by-phrase, cluster bootstrap,
   Clopper–Pearson, BH). The claim-grade, phrase-deduped numbers are far more
   sober than the pooled tallies that were in the doc and are on the site:

   | model | downgrades vs upgrades (deduped) | sign test | BH q | significant? |
   |---|---|---|---|---|
   | gemma-2-2b | 25 vs 4 | p = 0.0001 | 0.0004 | yes |
   | gemma-3-4b-it | 11 vs 4 | p = 0.12 | 0.12 | **no** |
   | qwen3-4b | 16 vs 2 | p = 0.001 | 0.003 | yes |
   | qwen3-1.7b | 18 vs 5 | p = 0.011 | 0.014 | yes |

   The synthesis said "gemma-2: 67 downgrades" (pseudoreplicated; the site
   now shows 78 with re-traces) and "gemma-3: 8 vs 1, p = 0.039" (an
   overstatement — it is 11 vs 4, p = 0.12, **not significant**). Synthesis
   §1/§2 now use the deduped numbers and flag pooled tallies as
   pseudoreplicated. gemma-3's mean penalty IS real (n = 133, CI excludes
   zero) — only its downgrade asymmetry fails to reach significance.
3. **Tier provenance.** Status changed from "reviewed v1" (reads as
   clinician-reviewed) to **"owner-reviewed v1 · domain review pending"** —
   true, and restores the pending-domain-review disclosure the site CLAUDE.md
   requires until the clinician equivalence review lands. One-line revert if
   you'd rather phrase it differently.
4. **Masthead regression I introduced:** `simulated-scenarios/scenario.html`
   still had the old nav (missing "Start Here", "Home" not "Overview") —
   fixed to match the reorder.
5. **Code (batch 1 builders, 216 tests green):** `paired_stats_rigor.py`,
   the settle-window guard hardening (`fire_trigger.py`, closes the eviction
   seam), and the activation-patching harness skeleton.

## Needs your voice/decision (drafts/flags — NOT changed)

These touch framing or your prose, so I left them for you:

- **Single-case "Language Penalty" framing.** The hero, Word-Differences,
  Syntax, and Translation pages lead with tail extremes (−65%, −51%,
  20%→68%) labeled as the metric, while the aggregate is mean −7% / median
  −2% and only 5/132 pairs reach |0.5|; a single measurement moves ~0.064
  under paraphrase (same size as the effect). Suggest a one-line caveat
  riding along with the flagship figures. (Your voice.)
- **Word-Differences page mismatch.** Its subtitle/explainer/meta describe a
  "depression vs the blues → therapist 86%→35%" example, but the embedded
  figure is the scenario-85 asthma/inhaler swap. Pick which example leads and
  reconcile the prose + meta/OG/Twitter to it.
- **Model-evaluations "read perfectly / translation hurts"** rests on a
  10-item probe with deltas of 1–2 items; suggest stating n and softening
  "read perfectly."
- **Blind stimulus QC caveat** (condition-drift in the flip half) is in the
  synthesis but nowhere on the site — consider a limitations line.
- **Small-n labels** on the titration/dose-response (cells n=4–5) and a
  one-line "all circuit evidence is one 2B model" pointer on the mechanism
  pages.
- **Translation page 45% vs 41%** (study measurement vs re-trace) still reads
  inconsistently in one spot; and a **"Pair 15" vs "Pair 16"** citation on
  Word-Differences I could not confirm — verify against how the phrase
  dataset numbers that row.

## Queued for the next autonomous batch (objective, bigger)

- **Site pseudoreplication.** The safety-view cards and the "124 vs 15"
  provenance strip pool flip counts across models and re-traces (same phrase
  counted up to 4×). The honest per-model deduped numbers are in the table
  above / `paired_stats_rigor.json`. Fix = make the collector/exporter
  publish phrase-deduped counts, which will LOWER the headline downgrade
  numbers on the site — I want you to see that change land rather than do it
  unannounced. High priority.
- **Accessibility micro-fixes** (all objective, safe): translation trace
  "tabs" use role=tab without tabpanels (→ plain buttons); syntax quad modal
  doesn't trap/restore focus; dialect accordion rows need role="button";
  model-eval slope SVGs need role=img + aria-label. Contrast was checked and
  passes AA — no change needed there.

Full finding list (29 items, with severities and locations) is in the
workflow journal; this file is the actionable digest.
