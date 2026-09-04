# Clinician review packet — PatientWords

Prepared 2026-08-29 for a domain reviewer. Everything referenced is public;
no patient data is involved anywhere in the study — every "patient" text is
a synthetic vignette. Estimated total time: **2–4 hours**, in three
independent parts (any one part alone is valuable).

## What the study measures, in one paragraph

PatientWords measures how language models change their behavior when the
same clinical situation is phrased in precise clinical vocabulary versus
everyday patient language: next-token probabilities across ten open models,
internal circuit evidence on one, and the advice eight deployed assistants
give. The headline behavioral finding — when an assistant's answer changes
under patient phrasing, it usually moves DOWN the care ladder — depends on
two instruments that have owner review but **no clinical review yet**, and
the site labels every dependent claim "draft pending domain review" until
that changes. Your review is what removes those caps.

## Part 1 — Care-urgency tier vocabulary (~1–2 h)

- **The instrument:** `data/urgency_tiers.draft.json` (this repo) — a token
  vocabulary mapping next-word predictions (e.g. "doctor", "ER",
  "monitor") to care-urgency tiers 0–3. It decides which prediction flips
  count as downgrades.
- **The task:** work through `docs/tier_review_checklist.md` — Section A is
  ten decision-critical tokens (each currently decides at least one
  published downgrade/upgrade call); Section B is high-frequency unassigned
  tokens blocking flip classification. Per item: confirm the draft tier,
  move it, or exclude it, with a one-line rationale where the call is
  non-obvious.
- **Format:** reply item-by-item ("1,2,4 yes; 3 → tier 2; 11 exclude").
  The maintainer flips `status` to `reviewed v1` and the site's draft
  flags clear automatically.

## Part 2 — Advice rubric v1.1-draft (~30–60 min)

- **The instrument:** `data/advice_rubric.draft.json` — four tiers
  (self_care / routine / urgent / emergency) with definitions keyed to the
  response's PRIMARY recommendation, five behavioral flags
  (professional_referral, disclaimer, refusal, safety_netting,
  clarifying_question), and the judge instructions given to the grading
  model.
- **The task:** read the tier definitions and boundaries (especially
  routine↔urgent and urgent↔emergency), the flag definitions, and the judge
  instructions. Flag anything a triage professional would draw differently.
  Approving this rubric (with or without edits) upgrades it from
  "1.1-draft" and removes the "clinician review pending" caveat that
  currently bounds every tier-based claim.

## Part 3 (optional but highest value) — blinded re-grade (~1 h)

- Grade a blinded sample of archived assistant responses with the same
  rubric, using the self-contained worksheet page:
  `patientwords` site → `llm/code.html` (loads
  `data/advice_coding_sample.json`; no setup, runs in the browser, exports
  your codes as a file to send back).
- Current judge–human agreement is n=25 with a single non-clinician coder
  (raw 0.889 clinical-arm / 0.625 patient / 0.500 translated) and one
  model-to-model check (75.6% exact over 3,426 responses). A clinician
  coding even 25–50 responses becomes the study's reference agreement
  number and is disclosed as such.

## What your sign-off changes

- Site urgency-tier content drops its "draft pending domain review" labels
  (they are load-bearing until then).
- Tier-based statistics graduate from "machine-coded, provisional" to
  reviewed-instrument status in the stats files and any manuscript.
- Your name/role is credited (or kept anonymous, your choice) in the
  provenance notes.

## Ground rules

- The intentional misspellings and casual grammar in patient-side texts are
  stress-test stimuli — do not correct them; they are the experiment.
- Nothing in this packet asks for medical advice; every judgment is about
  how to CLASSIFY a model's text, never about what a real person should do.
- Contact / return route: reply to the owner (Michael D. Green) with the
  item-by-item verdicts; files land in this repo with your review recorded
  in the data files' `status` fields and the divergence log.
