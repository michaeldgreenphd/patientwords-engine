# Pre-registration amendments — registry

**Why this file exists.** `docs/preregistration_tierB.md` requires that any
deviation "must be flagged as an amendment in the analysis writeup," but until
now Amendments 1–4 existed only as citations inside code docstrings (audit
2026-07-21, P1-6). This registry consolidates them in one place, dated and
with their implementing code as evidence. It was assembled retroactively on
2026-07-21 from those citations; the amendment *dates* below are the dates
recorded in the code, not the date of this file. Nothing here creates a new
rule — where an amendment's confirmatory text has not been written yet, that
gap is flagged rather than filled.

---

## Amendment 1 — Tier B confirmatory-holdout split

- **Pre-registered:** 2026-07-09 (per the implementing module's docstring).
- **Rule:** every accepted Tier B pair is assigned by deterministic hash of its
  clinical prompt — `sha1(clinical_prompt) mod 10 == 0` (~10%) is the
  **holdout**, analyzed exactly once after collection ends. All interim
  analyses (nightly critic, dashboard deltas, synthesis drafts, published
  aggregates) use only the ~90% exploration split. Rows are never dropped from
  data files; the `tierb_split` flag keeps the split auditable. A batch counts
  as Tier B iff it is a `pairs_<STAMP>` batch at or after `tierb.start_utc`
  (2026-07-10T01:14:38Z, stamped by the go/no-go session).
- **Implementation:** `scripts/tierb_split.py` (single implementation of the
  rule); `scripts/urgency_shift.py` stamps rows; aggregate consumers exclude
  `tierb_split == "holdout"`.
- **Status:** in force.

## Amendment 2 — confirmatory versions of the J-lens formation-depth endpoints

- **Cited in:** `scripts/jlens_insights.py` (module docstring and payload `_`
  note): the formation-depth analytics — formation distributions, the
  capture-vs-hijack taxonomy, the instruction-tuning depth comparison — are
  **exploratory, with no pre-registered endpoint**; "Amendment 2 drafts the
  confirmatory versions."
- **Status:** referenced but **not yet written**. No committed document defines
  the confirmatory endpoints, their hypotheses, or their analysis plan.
- **Open item (owner):** author the Amendment 2 endpoint definitions before any
  confirmatory claim is made from the formation-depth analytics. Until then,
  every consumer correctly labels these outputs EXPLORATORY.

## Amendment 3 — phrase-keyed widening of the holdout seal

- **In force:** 2026-07-14 (per `scripts/tierb_split.py:holdout_phrases`).
- **Rule:** a phrase flagged holdout anywhere is sealed **everywhere**. The
  seal is keyed on the accepted clinical prompt, so trace-time screening probe
  extensions, alias / mitigation stems (`pairs_<STAMP>_txopus`), and
  repeatability re-run stems (`repeatability_r*`) all seal under the same
  registered phrase even though those stems do not match the Tier B batch
  pattern.
- **Context:** adopted as part of the 2026-07-14 holdout-seal remediation.
- **Implementation:** `scripts/tierb_split.py` (`holdout_phrases`), consumed by
  the J-lens exporters (`export_jlens_depth.py`, `export_jlens_transport.py`)
  and `jlens_insights.py` (`holdout_excluded` counters).
- **Status:** in force.

## Amendment 4 — confirmatory version of the steering (swap-intervention) comparison

- **Cited in:** `scripts/export_jlens_depth.py` (steering-aggregate `_` note):
  the swap intervention / rank-1 restoration comparison is an **exploratory
  pilot** (design in `docs/lens_steering_design.md`); "Amendment 4 registers
  the confirmatory version on post-adoption batches."
- **Status:** referenced but **not yet written**. The post-adoption batch set
  and the confirmatory comparison are not defined in any committed document.
- **Open item (owner):** define the Amendment 4 confirmatory protocol (which
  batches count as post-adoption, the endpoint, the success criterion) before
  any confirmatory steering claim.

---

## Bookkeeping

- Registered retroactively 2026-07-21 (audit item P1-6 / execution E8); the
  in-force dates above come from the implementing code.
- `docs/preregistration_tierB.md` remains the pre-registration of record; this
  file is the amendment log it calls for.
- Future amendments: add an entry here **in the same commit** as the
  implementing code, so the registry can never lag the practice again.
