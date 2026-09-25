# PatientWords multi-turn (Petri) arm — reproduction pack for {vendor}

Pack {pack_version}. Every file here is copied byte for byte from the study's
public repository (michaeldgreenphd/patientwords-engine); nothing in this
bundle is private. It exists so your team can verify, in your own logs and
with your own tools, every call this arm of the study made to your model,
every judgment attached to a reply, and the analysis every public claim from
this arm rests on. A public claim about your model from this arm cites this
pack version.

## What this pack contains

{run_count} runs of scripted ten-turn conversations with `{target_model}`:
{conversations} conversations and {target_calls} target calls to your model. Served
build strings: {served_target}. Each run's directory under `runs/` holds the
files the repository holds for it:

{run_list}

- `manifest.json` — the run manifest: models, seeds, spend, the digest of
  every artifact, and the run's link in the hash chain.
- `sanitised_log.json` — the harness log after the sanitiser's allowlist
  projection.
- `transcripts.jsonl` — one record per conversation.
- `judgments.jsonl` — {judgments} judgments of the replies: {judges}
- `rule_outcomes.jsonl` — the deterministic rule outcomes per conversation.
- `*.report.json` — the cost sidecars: the target run's, and the judge's (a
  re-adapted run keeps its source run's target sidecar beside the judge
  sidecar of the re-adaptation).
- `analysis_rows.jsonl` — the analysis rows as each run committed them. The
  analysis reads them only for its block labelled "as first written".

{request_ids}

Also here:

- `analysis/{analysis_name}` — the output of the pre-registered analysis
  (design note section 10), sha256 `{analysis_sha256}`, and
  `analysis/{plan_name}`, the plan it read.
- `CLAIMS.json` — the claims this pack supports and their caveats, as below.
- `prompts/` — the advice rubric (digest `{rubric_digest}`) and every judge
  prompt file the judgments name, at their repository paths. Each judgment
  records the digest of the file it was judged under. {prompt_note}
- `seeds.json` — the {seed_count} seeds these runs used and each seed's
  digest; every run manifest records the same digest.
- {lock_note}
- `MANIFEST.json` — the exact state this pack was built from; `SHA256SUMS` —
  the sha256 of every other file in the pack.

## Verify the records are unaltered

From a checkout of the public repository:

    python -m scripts.petri_audit.cli verify-chain --data-dir {runs_dir}

It prints `chain intact (<head>)`. When this pack was built the head was
`{chain_head}`. Runs that land later append lines after these runs' lines and
move the head without touching them. These runs' lines in
`{runs_dir}/manifests.chain`:

{chain_lines}

Each run directory also verifies on its own, in the repository:

{verify_run_commands}

and in this pack, with `--run-dir runs/<run>`.

## Reproduce the analysis

{analysis_commands}

`--final` never overwrites an artifact, so it writes to a new path. Compare
the result sections (`triples`, `section_10_2` to `section_10_5`,
`as_first_written`) with `analysis/{analysis_name}`; they should be
identical. `identity` records when, where and from which commit each run of
the analysis ran. {analysis_identity_note}

## Claims this pack supports

{claims}

## Caveats we hold ourselves to

{limitations}

- The replies are graded by the same model that wrote them, acting as a
  grader, against a DRAFT rubric. There is no clinical reference standard:
  "less urgent" means one wording's reply was graded at a lower tier than the
  other's, not that either grading is medically correct.
- The user turns are scripted: they are fixed in advance and cannot answer a
  question the model asks.
- API access is a proxy for your consumer product: no product-layer wrapper
  and no memory.
- Nothing in this study is medical advice; the replies were elicited strictly
  for measurement.

Questions, corrections, or disputes about any record, judgment or claim: open
an issue on the public repository.
