# data/petri — the Petri lane's published outputs

Everything under this directory is written by the `petri-audit` lane
(`.github/workflows/petri_audit.yml`) through `scripts/petri_audit/`, from a
raw Inspect `.eval` log that is **never committed** (docs/petri_integration_design.md
section 9; owner decision 8, 2026-09-16).

| Path | Written by | What it is |
|---|---|---|
| `sanitizer_allowlist.json` | hand-maintained | The allowlist projection a raw `.eval` passes through before anything is published; versioned, digested into every manifest that used it. |
| `runs/<run>/manifest.json` | `petri_audit.adapter` | The closed run manifest (draft 0.2): contract checks, environment-lock digest, model roles, trees and branches, usage, spend, holdout block, artifact digests, integrity counts, hash chain. |
| `runs/<run>/transcripts.jsonl` | `petri_audit.adapter` | Transcript 0.2 records, one per trajectory node, bound to the manifest's identity digest. |
| `runs/<run>/rule_outcomes.jsonl` | `petri_audit.adapter` | Rule outcomes per record (tool invocation, order, marker echo, query text, parse errors). |
| `runs/<run>/sanitised_log.json` | `petri_audit.adapter` | The allowlist projection of the raw log: messages, events with text, usage, timeline structure; no provider request bodies, headers, base URLs or arguments. |
| `runs/<run>/judgments.jsonl` (+ `.report.json`) | `petri_audit.judge_runner` | The judge of record's per-turn annotations under both tier instruments and the outcome prompt files; null answers kept and counted. |
| `runs/<run>/analysis_rows.jsonl` | `petri_audit.cli analyze` | Analysis-ready rows with protocol, tree, branch and shared-prefix flags. |
| `runs/<run>/<run>.report.json` | `petri_audit.cli adapt --report` | The cost sidecar the ledger folds into the daily spend (`scripts/ledger_update.py --petri-dir`), engine re-priced from Inspect's usage, explicit `billing_channel`. |
| `runs/manifests.chain` | `petri_audit.manifest` | One line per manifest: path and digest, each linking to the previous; `verify-chain` checks it. |
| `holdout_consumption.jsonl` | none yet | Append-only registry of sealed phrases whose content left the seal through a published run. The pilot uses the explore split only, so this file does not exist until a confirmatory design decides to spend a holdout. |

Raw `.eval` logs are execution artifacts: the workflow writes them under the
runner's temporary directory, uploads them as a workflow artifact with 90-day
retention, and binds them to the manifest by sha256. `.gitignore` refuses
`*.eval` and `runs/*/logs/` everywhere, and the workflow refuses to commit
while any `.eval` is inside the checkout.

Paths inside a manifest are recorded relative to `runs/`, so the same log
adapted anywhere yields byte-identical exports (tests/petri/test_zero_cost_e2e.py).
