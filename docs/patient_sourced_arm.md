# Patient-sourced phrase arm (scaffolding landed 2026-07-13; runs after review)

The owner's standing plan: the current Tier B corpus is a demonstration built
from LLM-written stimuli; the final run should build its stimuli around real
patient language, with equivalence judged by doctors and a linguist. This
document records the scaffolding that now exists and the gate that must open
before anything runs.

## What exists

1. **Source data** — the OAC Consumer Health Vocabulary flatfiles (release
   2011-02-04, uploaded by the owner 2026-07-13) live in `data/chv/`. Lay
   terms in CHV come from real consumer health queries and forum text.
   Citation: Zeng & Tse, JAMIA 2006;13(1):24-9. The repo's MIT license does
   not cover this data; CHV's open-access terms do.
2. **Derivation** — `scripts/build_patient_lexicon.py` writes
   `data/patient_lexicon.draft.json`: the best lay term per concept, ranked
   by CHV's consumer-frequency score, after the published stop-concept and
   incorrect-mapping exclusions plus purely structural filters (case/plural
   trivia, shared content tokens, shared 4-char stems). ~3.8k eligible
   concepts; the draft caps at 400 for review. Direction (which side is
   truly lay) is deliberately NOT decided by code - each entry carries both
   preferred names and the CHV/UMLS preference flags for the reviewers.
3. **Generation hook** — `medlang-generate pairs --required-phrases-file
   <json>` (or `generate_stress_pairs(required_phrases=[...])`). Each
   accepted item must contain one provided phrase verbatim inside its
   patient-side swap span; the validator rejects items that paraphrase the
   phrase, one item per phrase, and accepted items record
   `generation.source_phrase` + `generation.phrase_provenance =
   "patient_sourced_lexicon"`. Without the flag, generation is byte-for-byte
   the existing behavior (tests pin this).

## The gate (do not skip)

- The lexicon is `status: draft pending domain review`. **No entry seeds a
  paid generation run until the doctors + linguist have reviewed the
  entries** (strike bad mappings, fix direction, flag unsafe framings).
  Review happens on the draft JSON itself; the reviewed file drops the
  draft suffix and records reviewer sign-off in its `_` header.
- The arm needs a pre-registration amendment (sample size, generator model,
  endpoints, its own holdout) before firing - this corpus is the planned
  final run, not another supplementary set. Draft the amendment when the
  owner is back; owner approves the design.
- Provenance labeling on the site: "patient-sourced phrase, LLM-authored
  sentence" - a distinct tier between fully-synthetic and the hand-measured
  set, disclosed wherever these pairs appear.
- The CI workflow does not yet expose `required_phrases_file` as a trigger
  key; add it to the params heredoc + push-path defaults (every trigger key
  must appear there) in the same change that fires the first reviewed run.

## Owner to-do list (when back / off Fable)

1. Recruit the doctor + linguist pass over `data/patient_lexicon.draft.json`
   (400 entries; strike, flip, or approve each).
2. Approve the pre-registration amendment for the patient-sourced arm.
3. Decide whether to add a second source (NLM consumer-question corpus, or
   prospective collection) for multi-word idioms - CHV skews to short noun
   phrases; the study's strongest stimuli have been longer idiomatic spans.
