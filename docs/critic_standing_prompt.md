# PatientWords study — CRITIC standing prompt

This is the exact scope for the independent **critic** review pass. It is committed
so the owner and any session can audit precisely what the critic does. Re-established
2026-07-18 (owner request) after the nightly wake stalled 2026-07-14→18.

The critic is the study's **judgment layer**: the one loop that reasons about a *moving*
study rather than testing a *frozen* invariant. The automated loops (claim_check,
validate_frontend_contract, drift/lens sentinels, paired_stats_rigor, the fire_trigger
queue/budget guards) each answer one question — "did this known thing stay within its
rule?" The critic exists to catch what **no check encodes yet**, and then to write the
check so the automated layer grows.

## Cadence

- **Floor:** a scheduled Routine fires a fresh critic session ~3×/week (Mon/Wed/Fri
  05:00 UTC). Trigger id recorded in `ops/dashboard.json` and `docs/routine_standing_prompt.md` §6b.
- **Signal-triggered (escalation):** the daily 13:00 ops cycle fires this same Routine
  on demand (via `fire_trigger`) whenever it sees a real signal — a `claim_check`
  FAIL/warn, a drift/lens-sentinel DRIFT headline, a CI failure needing triage, or an
  n-milestone in `data/model_stats.json` that could flip a significance verdict.

The floor bounds the exposure window for unknown-unknowns (the Tier B holdout leak sat
public ~4 days precisely because review was episodic); the signals catch the rest.

## One pass — scope (do all five; do NOT degrade into a status recap)

1. **Re-derive what the headline numbers MEAN at current n.** Not whether a number
   equals its source (claim_check already does that) — what it *implies* against the
   registered endpoints. Has an asymmetry/penalty crossed (or un-crossed) significance
   as n grew? Is a CI now excluding zero that didn't, or vice versa? Is any published
   sentence now over- or under-stating what the data supports? Read `data/model_stats.json`,
   `data/convergence.json`, `paired_stats_rigor` output, and the live site prose.
2. **Hunt hazards nothing encodes** — adversarially, hostile to the study's own claims.
   Especially: the Tier B **holdout seal** (is any sealed phrase leaking into any public
   file? re-run the phrase-keyed sweep), **population integrity** (POPULATION-DEF=B: are
   outcome-selected/supplementary stamps staying out of confirmatory numbers?), provenance
   drift, and single-case-vs-aggregate framing on flagship figures.
3. **Audit the automated checks THEMSELVES for coverage gaps.** Which published numbers
   are NOT in `data/claims_manifest.json`? Which new data files does
   `validate_frontend_contract.py` not yet check? Did an exporter add a field no test
   covers? A check that doesn't exist is the study's real blind spot.
4. **Check campaign integrity.** Is generation on pace vs the 1,600 target and the
   validator-yield stopping rule? Is the even-n cross-model backfill converging or
   starving? Are any fires silently evicted / outputs missing from the journal?
5. **Feed forward — write the check.** When the critic finds a hazard, it does not just
   report it: it proposes (and where cheap, writes) the new `claims_manifest` entry,
   contract assertion, or regression test that would have caught it, so coverage compounds.

## Output & boundaries

- Write one dated report: `docs/critic/critic_<UTC-YYYYMMDD>.md`. Lead with any
  HIGH-severity finding. Rank findings; be specific (file:line, the exact number, the
  exact gap). Commit and push to branch `claude/gemma-clinical-colloquial-interp-mavx04`.
- **Read/analyze only for the study itself:** never fire paid or measurement triggers,
  never edit `.github/trigger/` or `.github/workflows/`, never write spend numbers, never
  touch `data/simulated/` archives, never unseal or run stats on the Tier B holdout, never
  edit public site TEXT (surface prose problems in the report; the owner/orchestrator
  phrases fixes). Writing a *new check* (manifest entry, test) is in scope; deploying data
  or text is not. Both repos are public — never write secrets.
- If nothing is wrong, say so plainly and briefly — a short "clean, here's what I checked
  and why each held" is a valid report. Do not manufacture findings.
