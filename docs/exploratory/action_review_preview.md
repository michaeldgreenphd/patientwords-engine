# Private PI evidence preview

Owner direction (2026-10-28): a private preview in the physician verification app,
with **clinical appropriateness and classifier extraction judged as separate tasks**.
The public website and original round-1 instrument are unchanged.

`scripts/export_action_review.py` prepares a new external package:

```bash
python -m scripts.export_action_review \
  --artifact /absolute/path/to/retained/ci-artifact \
  --run-id 40510625603 --out /new/external/evidence-pack
```

It verifies the landed sidecar's artifact report hash and every artifact file,
re-admits all 14 frozen source texts/joins and the current seal, and replays original
raw replies without repair. A changed parser result refuses. Clinical question
text is joined from the original source stimulus and wording arm, not reconstructed
by a model. New output is excluded from existing measurement collectors.

- `clinical.json`: four archived responses with original questions; classifier
  suggestions and source-model/arm labels are absent. Human ratings not collected.
- `extraction.json`: only structurally valid, semantics-unverified annotations.
  The present run has six, all authored software challenges; none is a clinical
  archive response. Unsupported, failed and unattempted cases are not relabeled.
- `receipt.json`: owner-only run/source/annotation joins and complete coverage,
  including the failed seventh reply and seven unattempted sources. Keep it out
  of the rater interface. Counts are pipeline coverage, not accuracy.

New bundle schema: `patientwords-evidence-review/1`, with `preview_only:true`,
`purpose: clinical|extraction`, one corresponding `evidence_*_v1` question set,
versioned question/instruction data, and `evidence_review` display. Required-nullable
`annotation` is null for clinical tasks. It is the unchanged normalized action
annotation for extraction tasks. `prompt` is required for archived responses and
null for standalone synthetic challenges. Span units remain Unicode code points.
The private app independently validates the shape, labels and exact source spans.
Draft questions are data in `review_questions_{clinical,extraction}.v1.json`; a
question/display change changes the deterministic item and bundle identities.

Use the app's `tools/build_evidence_pack.py` to render the package into its actual
page plus an in-tab fake backend. This local preview has no access control and no
network requests. Practice feedback exports are explicitly not study ratings.
The existing round-1 importer rejects this schema; a focused new importer and
approved collection protocol remain prerequisites for real clinician collection.
Never weaken the old importer or mix these answers into realism/reference-tier data.

The PI approves the questions, workload and adjudication plan. Close and preserve
the independent clinical round before releasing classifier suggestions for the
same responses to the same reviewers. Separate files alone cannot enforce blinding.
Neither these four selected responses nor the six software challenges establish
representative performance, a health-equity effect, a causal mechanism or safety.
Prior owner labels are partial independent selections, not exhaustive gold labels.

The merged structured-output correction prepares new wire bytes but does not admit
a fresh campaign. A later real classifier pass still needs its reviewed campaign
identity, preserved prior receipts/reservations, current prices, existing daily and
monthly ceilings and the CI trigger route. This preview neither spends nor bypasses
that gate. Jev/OpenRouter, Causalab/Linux and J++ historical provenance remain separate.
