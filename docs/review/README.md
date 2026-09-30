# docs/review — owner and rater review material

Every file in this folder, with what it holds and what refers to it. These are
records: the phrase text they contain is stimulus data, so quote them by path,
key or count, never by content.

| File | What it is | Referred to by |
|---|---|---|
| `README.md` | This index, and the rater instructions for the packet below. | `docs/README.md` |
| `stimulus_review_packet_20260712.csv` | Rater packet, 2026-07-12: 152 sampled pairs, described in the next section. Eight rows carrying phrases sealed as Tier B holdout were redacted on 2026-07-21 (commit a2c8dd04). | `ratings_quarantine.json`, `docs/audits/seal_incident_20260721.md` |
| `ratings_quarantine.json` | Owner decision of 2026-07-21 (R2): the 8 packet `sample_id`s whose ratings, if any are returned, stay out of every interim analysis until the one-time Tier B confirmatory analysis. No ratings had been returned when it was written. | `docs/audits/seal_incident_20260721.md`, `docs/tierb_freeze_checklist.md` |
| `downgrade_screen_20260809.json` | The owner's screen of 52 multi-tier downgrade rows on 2026-08-09: 40 strong, 12 screened out. The criterion was grammatical stimuli and completions that make sense, not clinical severity. | (none) |
| `downgrade_validated_seeds_20260809.json` | The 35 pairs that survived that screen (its 40 strong rows are 35 distinct pairs), used as few-shot `seed_pairs` for the steered scenario-generation fires. | the scenario-generation trigger's history |
| `downgrade_screen_feedback_20260809.json` | 10 counterexample entries built from that screen, the `feedback` input of the first steered generation fire. | the scenario-generation trigger's history |
| `downgrade_screen_feedback_20260811.json` | The same feedback grown to 15 entries for round 2, adding five round-1 pairs whose continuation slot was an object or treatment noun (commit 9e069417, which fired it). | the scenario-generation trigger's history |

## Stimulus review packet

`stimulus_review_packet_20260712.csv`: 152 sentence pairs, 8 sampled from each
generated batch (seed 7), order shuffled. No model measurements are included;
raters judge the language only.

Columns for the rater:

- `naturalness_1to5` - would a real person plausibly say the everyday sentence?
  (1 = never, 5 = completely natural)
- `clinical_accuracy_1to5` - does the clinical sentence say the same thing in
  correct clinical terms? (1 = wrong concept, 5 = faithful equivalent)
- `register_mismatch_yn` - y if the "everyday" sentence still reads as
  clinical/formal, else n
- `notes` - free text

`sample_id` is `<batch>#<index>`, joinable back to `data/simulated/<batch>.json`.
Intentional misspellings are stress-test stimuli; rate naturalness as written.

(Owner: instructions, rater recruitment, and framing are yours - this file is
just the mechanical skeleton. A subset is fine if 152 is too many; the sample
is shuffled, so truncating from the top keeps it stratified in expectation.)
