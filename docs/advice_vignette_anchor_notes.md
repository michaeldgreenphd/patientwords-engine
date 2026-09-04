# B1 — standardized-vignette anchor set: verification notes (2026-07-22)

Status: preparation only. **No vignette text is committed** — licensing must be
confirmed first, then owner + domain reviewer adjudicate the tier mapping.

## The set, verified

- **Citation (verified 2026-07-22):** Semigran HL, Linder JA, Gidengil C,
  Mehrotra A. *Evaluation of symptom checkers for self diagnosis and triage:
  audit study.* BMJ 2015;351:h3480. doi:10.1136/bmj.h3480.
- **Shape:** 45 standardized patient vignettes, 15 per triage category —
  *emergent care required*, *non-emergent care reasonable*, *self care
  reasonable* — published in the article's supplementary appendix.
- **Reuse precedent (verified):** the set is a standing benchmark; later
  symptom-checker and LLM-triage studies reuse the vignettes as published
  (one study dropped a single vignette after clinical review and used the
  remaining 44 verbatim), with published baselines for symptom checkers,
  laypeople, and physicians — exactly the comparability B1 wants.

## Still to confirm BEFORE any vignette text lands in this repo

1. **Licensing:** the article's rights statement (BMJ research articles of
   that era are typically open access under CC BY-NC 4.0, but this must be
   read off the article page itself, not assumed). Both repos are public, so
   the supplementary vignette text may only be committed if its license
   permits redistribution with attribution; otherwise we store our own
   paraphrase-free tier mapping + IDs and fetch text at run time locally, or
   seek permission.
2. **Which appendix file** carries the vignette text and whether BMJ hosts it
   without a paywall.

## Tier-mapping proposal (for owner + domain-reviewer adjudication)

The Semigran 3-way maps onto the draft rubric's 4 tiers in one of two ways —
the reviewer picks:

| Semigran category | Option 1 (leave `urgent` unmapped) | Option 2 (collapse for anchor scoring) |
|---|---|---|
| emergent | `emergency` | `emergency` |
| non-emergent | `routine` | `routine` OR `urgent` scored as correct |
| self care | `self_care` | `self_care` |

Option 1 is stricter (an `urgent` response to a non-emergent vignette counts
as over-triage); option 2 credits either middle tier. Precedent in the
symptom-checker literature is closer to option 2's lenient middle band.
Decision is data: it lands in each vignette's `reference` block
(`{"tier": ..., "source": "semigran_2015", "adjudicated_by": ..., "date": ...}`),
never in Python.

## Integration path once cleared

Vignettes land as a manual-source stimuli data file (provenance recorded per
item), the register manipulation is applied ON TOP under the single-swap
discipline (each vignette rewritten in consumer language, owner-approved), and
`build-stimuli --source manual` + the A2 reference plumbing (already landed)
do the rest.
