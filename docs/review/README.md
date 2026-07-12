# Stimulus review packet

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
