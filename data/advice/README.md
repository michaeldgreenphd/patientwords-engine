# data/advice/ — frontier-model advice archive (append-only)

Outputs of `scripts/advice_eval.py`. Elicitation against hosted frontier models is
inherently unrepeatable, so this archive is designed to be **auditable instead**:
nothing here is ever rewritten, and every response record is hash-chained.

## Files

| Pattern | Written by | Contents |
|---|---|---|
| `stimuli_<STAMP>.json` | `build-stimuli` | paired vignettes: clinical/patient bodies + assembled messages (identical ask suffix on both sides preserves the minimal pair), per-text sha256, source provenance, engine sha |
| `responses_<stem>.jsonl` | `elicit` | one record per API call, append-only, hash-chained (see below) |
| `responses_<stem>.report.json` | `elicit` | cost sidecar: spend vs `--max-spend`, per-model token usage, records appended, truncation reason, **chain_head** |
| `judgments_<stem>.jsonl` | `judge` | tier + flags per response, keyed by `response_sha256` + `rubric_sha256` + judge model — never mutates the response archive, re-runnable forever |
| `judgments_<stem>.report.json` | `judge` | judge cost sidecar |
| `analysis_<stem>.json` | `analyze` | offline paired stats: modal tiers, rank diffs, downgrade/upgrade classes, translation recovery, within-prompt variance, cluster bootstrap CIs |

## The audit chain

Each `responses_*.jsonl` record carries `prev_sha256` (the previous record's hash)
and `record_sha256` (sha256 of the record's canonical JSON including `prev_sha256`).
The final hash is committed as `chain_head` in the sidecar, in the same commit as
the data, on a public repo. You cannot re-run the model, but anyone can prove the
archive has not been altered since it landed:

```bash
python scripts/advice_eval.py verify-chain \
    --responses data/advice/responses_<stem>.jsonl \
    --sidecar   data/advice/responses_<stem>.report.json
```

Every record also stores the full request (message text verbatim, temperature,
max_tokens), the full raw provider response, the exact `model` version string the
API returned, send/receive UTC timestamps, latency, token usage, per-call cost,
and the engine git sha.

## Rules

- **Append-only.** Never rewrite, reorder, or delete a landed record or file; the
  chain makes any edit detectable, and `elicit` refuses to append to a broken chain.
- **Holdout seal.** Stimuli built from the published payload are holdout-safe by
  construction (the payload withholds sealed rows). The `--source pairs` path
  excludes holdout pairs via `tierb_split.py` and hard-errors when the holdout set
  cannot be computed (null `tierb.start_utc` — use the ops-truth dashboard copy).
- **Judge blinding.** The judge sees response text only — never the prompt or arm.
- **Vocabulary is data.** Tier definitions and judge wording live in the rubric
  JSON (`data/advice_rubric.json`, domain-reviewed; `.example` is the skeleton).
- This arm **evaluates** model advice for measurement. It never dispenses advice.
