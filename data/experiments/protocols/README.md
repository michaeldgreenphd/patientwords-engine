# Experiment protocols for proposed real-model runs

Nothing in this directory has been run against a model. A file here is an input to a
proposal, not a result.

| File | What it is | Written by |
|---|---|---|
| `first_run_stage_a.protocol.v1.json` | A `patientwords.experiment-protocol/1` document for stage A of `docs/exploratory/first_model_run_packet_20261110.md`, restricted to the rows whose token ids are all on a landed record (3 of the 10 rows of `pairs_20260706T175614Z`). It holds the prompt text of those rows, because the protocol validator requires it; the text is byte-identical to `data/simulated/pairs_20260706T175614Z.json`. No family carries the prompt-text publication marker. | `python tests/test_first_run_packet.py --write` |
| `first_run_stage_a.preview.v1.json` | The reproducible preview: selection of rows with the reason for each, where every token id was read, the plan's task counts with reasons and SHA-256, the resource estimates with their inputs, and the parity comparison sets and thresholds proposed before any run. It holds no prompt text. | the same command |

Neither file is edited by hand. `tests/test_first_run_packet.py` rebuilds both from the
batch file, the landed parts, the landed hosted-lens records and the capability matrix,
and fails when a committed file differs.

Check them:

```bash
python -m scripts.experiments.cli validate --protocol data/experiments/protocols/first_run_stage_a.protocol.v1.json
python -m pytest -q -p no:cacheprovider tests/test_first_run_packet.py
```

The capability matrix is one of the preview's inputs. After a reviewed change to
`data/experiments/capability_matrix.v1.json`, run the `--write` command again in the same
change; it also rewrites the generated block of the packet.

Token ids. No tokenizer file is available in a development container. The prompt token
ids are the hosted lens service's record for each exact prompt
(`trace_out/pairs_20260706T175614Z__jlens_gemma-2-2b/jlens_raw/`). Each target id is the
id that a landed hosted-lens record of an exploration-period study batch holds for a
token with the target's exact string. That the hosted service's tokenizer equals the
tokenizer at the pinned model revision is not verified here. The run described in the
packet must check it before any value is compared.
