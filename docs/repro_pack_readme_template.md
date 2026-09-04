# PatientWords advice arm — reproduction pack for {vendor}

Pack {pack_version}. Every file here is assembled from the study's public
repository (michaeldgreenphd/patientwords-engine); nothing in this bundle is
private. It exists so your team can verify, in your own logs and with your own
tools, every call this study made to your model and every judgment we attached
to a response.

## What this pack contains

- `records.jsonl` — all {n_records} archived calls to your model between
  {window}: assembled prompt, request parameters, timestamp, latency,
  request id where captured, the exact model string your API returned
  ({builds}), and the full raw response body. Your infrastructure team can
  correlate each call by request id and timestamp.
- `records.csv` — the same calls, flat, for spreadsheets.
- `judgments.jsonl` — {n_judgments} tier codings of those responses by a
  blinded judge (response text only; no model name, no wording label), each
  stamped with the rubric sha it was coded under.
- `rubric.json` — the coding rubric, version {rubric_version}.
- `MANIFEST.json` — the exact archive state this pack was built from.

## Verify the records are unaltered

The archive is append-only and hash-chained: each record carries the sha256
of the previous record and of its own content. From a checkout of the public
repository:

    python scripts/advice_eval.py verify-chain --responses {responses_file}

Expected chain head: `{chain_head}`. If the recomputed head matches, no
record in this pack has been altered since it was written.

## Reproduce the analysis

    python scripts/advice_eval.py analyze --stimuli {stimuli_file} --seed {seed}

The seed makes the bootstrap deterministic; the paired table for your model
regenerates from the public files alone.

## Caveats we hold ourselves to

- Tier codings are machine-coded against a DRAFT rubric ({rubric_version})
  and are provisional until clinician review; a clinician-reviewed rubric and
  a blinded human-coded agreement sample replace them through the same files.
- There is no clinical reference standard yet: "downgrade" means the patient
  wording was coded less urgent than the clinical wording of the same
  situation, not that either coding is medically correct.
- n is small (pilot scale) and API access is a proxy for your consumer
  product: no product system prompt, no product-layer wrapper, no memory.
- Nothing in this study is medical advice; responses were elicited strictly
  for measurement.

Questions, corrections, or disputes about any record or coding: open an
issue on the public repository.
