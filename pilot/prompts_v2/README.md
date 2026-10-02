# Pilot run kit, version 2

The inputs for the second run of the stimulus-generation pilot: `generation_prompt.txt`, `checker_prompt.txt` and
`design.json`. They were revised from the owner's blind review of run `pilot_real_20260930` (40 pairs, reviewed
2026-10-01). That run was made on the owner's laptop, outside the repository, and is not a recorded run under the
AGENTS.md pilot exception. The kit encodes the rules of `../codebook/codebook_v0.2.md`: the stimulus rules R1-R9 and
the lexicon rules L0-L6, which decide whether two phrases name the same thing from standard terminologies.

These files do not replace `../prompts/` or `../design.json`. Those belong to the run recorded in `pilot/`, whose
manifest hashes them, and that run stays at harness version 1.

## What version 2 changes

### Prompts

Generation prompt:

- Rules 1-6 restate the codebook: start from a real clinical situation (R4); a one-for-one swap that keeps both
  sentences grammatical with no other word changed (R1); first-person, conversational sentences in the active voice
  (R2); the clinical phrase is the standard term (the preferred term in SNOMED CT or MeSH, or a drug's generic name)
  at a clinician's level of detail (R3); the patient phrase is how patients talk, not leaflet wording, and a brand
  name only for a single-ingredient drug (R5, L2); the patient phrase names the same thing or a broader everyday
  version of it, never something narrower or different (R6, L3-L5).
- Rule 7 is new: the template ends right after an article or a possessive (a, an, the, my, his, her, their, your,
  our), where the next word names who the speaker will see, what they will take or do, or where they will go. The
  row gives that word as `next_word`. This is the probe point a later circuit trace reads.
- Every row has five keys: `clinical_term`, `patient_term`, `template`, `next_word`, `control`.
- Variant design (R7): the 16 non-control rows cover 12 concepts, and 4 of them get a second, vaguer or slangier
  patient phrasing on the next line, with the same clinical term, template and next word.

Checker prompt: four answers per item, based on standard terminologies rather than impression.

- `relation`: `same`, `same_brand`, `broader`, `narrower` or `different` (L1-L5).
- `equivalent`: `yes` for same, same_brand and broader; `no` for narrower and different; `unclear` only when the
  meaning of a phrase cannot be decided (R9).
- `sentence_natural`: `both`, `clinical_only`, `patient_only` or `neither` (R1, R2).
- `patient_realism`: `real`, `textbook` or `unlikely` (R5).

The last two are the questions the owner answered on the review page, so the checker's answers can later be compared
with the owner's on the same rows.

### Harness

`design.json` sets `"harness_version": 2`. `pilot/scripts/common.py` reads it (absent means 1) and the scripts then
work as follows. A run without the key behaves exactly as before: every version-1 output is byte-identical.

- **Rows.** `next_word` is required. It must be a lowercase word of letters, with at most one internal hyphen or
  apostrophe. A row with a bad `next_word` is the format failure `next_word_invalid`; a row without one is
  `missing_field:next_word`. `generated/all_rows.jsonl` keeps `next_word`. The retry rule counts the five keys.
- **Checker.** The structured-output schema requires the three further answers. An answer with any of them missing
  or outside its set is invalid, and its item becomes `missing`, as an invalid verdict does now. An answer whose
  `equivalent` contradicts its `relation` (yes with narrower or different, no with same, same_brand or broader) is
  kept as given and flagged `inconsistent: true`; the checker log and the summary count these. The harness refuses
  a version-2 checker prompt that does not offer every allowed value, so the prompt and the schema cannot drift
  apart.
- **Summary.** `compute_summary.py` adds descriptives that are outside the protocol's estimands. They are:
  - the relation counts for generated, known-good and broken items, and the precision view derived from them
    (same and same_brand are as precise, broader is vaguer, narrower is more specific);
  - the yes-rate by relation, and the count of inconsistent answers;
  - the checker's `sentence_natural` and `patient_realism` answers, by arm;
  - probe-point compliance: whether a template ends on one of the probe endings. This is reported, not counted
    as a format failure;
  - variant-design compliance per call: exact adjacent variant pairs, distinct concepts, non-adjacent repeats,
    runs of three or more, compliant calls with a Wilson interval, and the ids of non-compliant calls;
  - `next_word` statistics: the number of distinct words and the 10 most common.

  The handoff's results block gets matching lines.
- **Review sheet.** At most one row per concept, where a concept is the call, the clinical term's surface form and
  the template. The 40 rows are allocated to arms in proportion to their concepts, and the same seeded stream
  draws the concepts and then one row of each. `review_key.csv` also carries the checker's relation,
  `sentence_natural` and `patient_realism`. The owner opens the key only after reviewing.
- **Plans.** `calls.json`, `checker_batches.json`, the manifest's design block and `summary.json` record
  `harness_version` (version 2 only). Changing the version after planning is refused, and
  `write_manifest.py --refactor-inputs` refuses a change of version.

### Design

`design.json` is `../design.json` with the same cells in the same order, plus five changes:

- `harness_version: 2`;
- `probe_endings`;
- `concepts_per_call: 12`;
- `variant_pairs_per_call: 4`;
- `review_sampling: "one_row_per_concept"`.

Its example negative control (what the prompt's `{{CONTROL_EXAMPLE}}` shows) was rewritten: it carries `next_word`,
it is spoken in the first person, and its template ends on a probe ending, as the version-2 prompt asks of every row.

`design.json`'s `harness_version` is the pilot scripts' version. It is unrelated to the `harness_version` string in
`manifest_model.json`, which records the Claude Code version that ran the subagents.

## How a run uses it

1. Make a fresh run directory and set `PILOT_DIR` to it for every script call. A run that is later committed lives
   at `pilot/runs/<run_id>/`.
2. Before planning, copy the kit into the run directory:
   - `generation_prompt.txt` and `checker_prompt.txt` into `<run>/prompts/`;
   - `design.json` into `<run>/design.json`.

   Then add the seed file, a `manifest_model.json` stating the session's facts, the run's own `PROTOCOL.md`, and a
   `HANDOFF.md` that carries the two results-block marker lines.
3. Run the chain as for version 1: `plan_calls.py`, `write_manifest.py`, the two workflow stages (copy each journal
   to `workflows/<stage>.journal.jsonl`), `make_review_sheet.py`, `compute_summary.py`, `record_run.py` for each
   stage, and `write_manifest.py finalize`.

Safeguards:

- The version-2 prompts are refused under the version-1 `design.json`, because that combination would drop
  `next_word` and the further checker answers.
- The planning, batching, rendering, review-draw and request-body scripts (`plan_calls.py`, `build_checker_set.py`,
  `make_workflow_scripts.py`, `make_review_sheet.py`, `build_api_requests.py`) refuse to write into a directory
  whose manifest is finalized, unless `--replace` is passed. `compute_summary.py` and `write_manifest.py` have no
  such guard: run with `PILOT_DIR` unset, they rewrite the recorded run's summary, results block and manifest in
  `pilot/`. Set `PILOT_DIR` for every call; if one slips, restore those files from git
  (`git checkout -- pilot/summary.json pilot/summary.md pilot/HANDOFF.md pilot/manifest.json`).
- `compute_summary.py` and `write_manifest.py` (except with `--reset`) refuse a finalized run directory sealed on the
  other side of Python 3.12 from the running interpreter, because 3.12 changed `sum()` over floats and the
  summary's float sums would differ in the last bit. The recorded run in `pilot/` is sealed under 3.13.4, so
  re-finalizing it needs Python 3.12 or later.

With the seed file run `pilot_real_20260930` used, Arm A draws the same exemplars that run drew, because the master
seed is a constant. A comparison with that run then differs in the prompts and the harness version, not in the
exemplars.

The variant design changes two estimands for reasons of design, not of the generator, and the run's protocol should
say so:

- **Estimand 3** (mean template similarity) will read higher than in run 1, because each call reuses 4 templates.
- **Estimand 2's `clinical_term_only` novelty** will read lower. The second row of each variant pair repeats the
  first row's clinical term exactly, and novelty counts a clinical term only the first time it appears in the arm.
  Up to 4 of a call's 16 non-control rows (25%) therefore cannot count as novel. Pair novelty and
  `patient_term_only` novelty are not affected, because the pair's patient terms differ.

## What to compare against run 1

The owner reviews the new run's 40-row sample on the same review page. The baseline is the codebook's, from the
first review:

| Measure | Run 1 (`pilot_real_20260930`, codebook v0.2 baseline) |
|---|---|
| Kept as is | 18/40, 45% (95% CI 31-60%) |
| Both sentences read naturally | 21/40, 52% (38-67%) |
| Patient phrase sounds real | 19/40, 48% (33-62%) |
| Owner and checker agree on "same thing?" | 23/40, 57% (42-71%); kappa -0.04 |

With 40 reviews, only a large change can be told apart from noise: the intervals above are about 30 points wide.

Version 2 also makes possible three comparisons that run 1 could not support:

- the owner's `sentence_natural` and `patient_realism` answers against the checker's on the same rows;
- the review sample now holds 40 distinct concepts, so no concept is reviewed twice;
- probe-point and variant-design compliance can be read from the summary.

The agreement computation needs the completed review, so it runs after the summary, outside `pilot/scripts/`.

## What is still the owner's

- **Codebook O1.** Should a patient's description of a diagnosis become its own, separately labelled stimulus class?
  Until it is decided, such pairs count as `different` (L5). The generation prompt forbids them (rule 6), and the
  checker answers `different` for them.
- **Codebook O2.** Clinician confirmation of the lexicon rulings is pending. Three rulings rest on general knowledge
  for the lay phrase and one on a dictionary.
- **The run's protocol.** It is written and frozen before planning. It states:
  - the execution path;
  - the seed file and K;
  - that the version-2 descriptives are reported outside the estimands;
  - the estimand 2 and estimand 3 caveats above.
- **Committing the run.** Whether to commit the run under `pilot/runs/<run_id>/`, after the holdout seal check
  over that directory returns CLEAN.
