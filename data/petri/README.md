# data/petri — the Petri lane's published outputs

Everything under this directory is written by the `petri-audit` lane
(`.github/workflows/petri_audit.yml`) through `scripts/petri_audit/`, from a
raw Inspect `.eval` log that is **never committed** (docs/petri_integration_design.md
section 9; owner decision 8, 2026-09-16).

| Path | Written by | What it is |
|---|---|---|
| `sanitizer_allowlist.json` | hand-maintained | The allowlist projection a raw `.eval` passes through before anything is published; versioned, digested into every manifest that used it. |
| `speaker_identity_markers.draft.json` | hand-maintained | The speaker-identity manipulation check's vocabulary: per-identity clause patterns and the seeds waived from the check, read by `scripts/petri_audit/seeds.py` (`seed_problems`) so a declared `user_is` is verified against the arm's wording rather than trusted. Vocabulary lives here, never in Python. |
| `w2_register_contrast_plan.json` | hand-maintained, fixed by `docs/petri_wave2_design.md` section 10 | The fixed structure of the pre-registered wave-2 register-contrast analysis, read by `scripts/petri_w2_register_contrast.py`: the two scenario sets, the four campaign fires by journal nonce with the campaign epoch and partition each contributes, the fixed triple counts (35; 15 discovery, 20 prospective), the decomposition set, and 10.5's seed restriction. Data, because the seed ids name their scenarios. |
| `runs/<run>/manifest.json` | `petri_audit.adapter` | The closed run manifest (draft 0.2): contract checks, environment-lock digest, model roles, trees and branches, usage, spend, holdout block, artifact digests, integrity counts, hash chain. |
| `runs/<run>/transcripts.jsonl` | `petri_audit.adapter` | Transcript 0.2 records, one per trajectory node, bound to the manifest's identity digest. |
| `runs/<run>/rule_outcomes.jsonl` | `petri_audit.adapter` | Rule outcomes per record (tool invocation, order, marker echo, query text, parse errors). |
| `runs/<run>/sanitised_log.json` | `petri_audit.adapter` | The allowlist projection of the raw log: messages, events with text, usage, timeline structure; no provider request bodies, headers, base URLs or arguments. |
| `runs/<run>/judgments.jsonl` (+ `<run>.judge.report.json`) | `petri_audit.judge_runner`, bound by `petri_audit.manifest.bind_judgments` | The judge of record's per-turn annotations under both tier instruments and the outcome prompt files; null answers kept and counted. `judge` then records the file's path and digest and the judge's provenance in `manifest.json` and reseals it (identity digest unchanged, chain head line replaced), so `verify-chain` covers the judgments too. The `<run>.judge.report.json` sidecar (run-unique, because the ledger keys sidecars by basename) carries the judge's billing channel, the per-prompt token estimator the ceiling used, and the count of calls whose usage the provider omitted (charged at their worst case). |
| `runs/<run>/analysis_rows.jsonl` | `petri_audit.cli analyze` | Analysis-ready rows with protocol, tree, branch and shared-prefix flags. |
| `runs/<run>/<run>.report.json` | `petri_audit.cli adapt --report` | The cost sidecar the ledger folds into the daily spend (`scripts/ledger_update.py --petri-dir`), engine re-priced from Inspect's usage, explicit `billing_channel`. When any target call returned no usage block the sidecar imputes `max_spend` (`cost_basis: ceiling_imputed:usage_missing`) rather than booking the run below its charge. |
| `runs/manifests.chain` | `petri_audit.manifest` | One line per manifest: path and digest, each linking to the previous; `verify-chain` checks every link and every artifact a manifest names (path present, digest as recorded). The only rewrite the chain permits is the head line, when `judge` binds judgments into the head manifest. |
| `holdout_consumption.jsonl` | none yet | Append-only registry of sealed phrases whose content left the seal through a published run. The pilot uses the explore split only, so this file does not exist until a confirmatory design decides to spend a holdout. |

Raw `.eval` logs are execution artifacts: the workflow writes them under the
runner's temporary directory, uploads them as a workflow artifact with 90-day
retention, and binds them to the manifest by sha256. `.gitignore` refuses
`*.eval` and `runs/*/logs/` everywhere, and the workflow refuses to commit
while any `.eval` is inside the checkout.

The measurement outputs of a run are committed only when `commit_outputs` is
true and every prior step succeeded. The two cost sidecars of a paid run
(`<run>.report.json`, `<run>.judge.report.json`) are committed by a separate
step whatever happened to the outputs, because the ledger is the only record
of landed spend and they carry no seed or model text. A run that failed
before adaptation gets `<run>.report.json` from `cli spend-report` instead
(priced from the retained log, or the ceiling imputed for a priced target), so
the ledger never misses an attempted paid run. The judge sidecar is cumulative
over every row in `judgments.jsonl` (`cost_basis: cumulative_from_records`,
`run_cost_usd` per invocation), so a resumed pass books only its delta.

Paths inside a manifest are recorded relative to `runs/`, so the same log
adapted anywhere yields byte-identical exports (tests/petri/test_zero_cost_e2e.py).
