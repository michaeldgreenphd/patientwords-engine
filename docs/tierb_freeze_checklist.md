# Tier B freeze checklist

Owner-committed items that execute AT the Tier B freeze (collection complete,
lanes quiesced), consolidated 2026-07-21. Nothing here runs before the owner
declares the freeze.

1. **E10 branch consolidation** (owner decision 2026-07-21 R2: at freeze) —
   the audit §6.4 migration: quiesce -> trigger-safe merge of the working
   branch onto main (trigger files restored, ops state carried) -> repoint
   Routines -> hygiene (paid-workflow concurrency stanzas,
   activation-patching resolution, jlens trigger via sanctioned fire,
   CLAUDE.md corrections) -> decommission the working branch -> canary cycle.
2. **DOI / versioned data release** (DATA_LICENSE.md commitment) — tagged
   release of code + data, deposited for a DOI; cite-by-commit ends.
3. **Holdout confirmatory analysis** (Amendment 1: analyzed exactly once) —
   REQUIRES Amendment 2 and Amendment 4 confirmatory definitions to be
   authored and committed FIRST (docs/preregistration_amendments.md flags).
4. **Ratings quarantine release** — the 8 quarantined packet rows
   (docs/review/ratings_quarantine.json) become usable in the confirmatory
   pass only.
5. **Traces-site branch swap** — patientwords-traces build.yml
   ENGINE_RENDER_BRANCH env flips to main once consolidation lands.
6. **History decision record** — the 2026-07-21 seal incident's leave-history
   decision (docs/audits/seal_incident_20260721.md) is re-affirmed or
   revisited once, here, with the corpus frozen.
