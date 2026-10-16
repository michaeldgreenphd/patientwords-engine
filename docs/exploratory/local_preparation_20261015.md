# Bounded local preparation — 2026-10-15

This is the historical receipt of the initial local preparation pass. Final review
changes, source identities and push/PR status are in
[review_preparation_20261016.md](review_preparation_20261016.md); earlier source hashes
below remain evidence of the versions actually checked at that time.

Local date: 2026-10-15 (America/New_York); execution continued after 00:00 UTC on
2026-10-16. This is installation and artifact inspection, not a PatientWords
real-model experiment. The originals, tiny-model outputs and environment inventories
are outside Git. No push, merge, publication, trigger, workflow dispatch, compute
rental, study-weight download or study-model forward occurred.

## Separate readiness states

| Boundary | Actual state |
|---|---|
| Local runtime installation | Causalab's pinned Rust extension built and imported; all 84 platform-applicable locked base dependencies conform. Documented tiny-random CPU installation run passed. J++ safe-inspection environment works, but is not a full locked fitting/evaluation installation. Engine environment unchanged. |
| Downloaded-artifact integrity | Complete J++ checkpoint and adjacent YAML at the authorized immutable release verified; originals read-only outside Git. |
| Historical lens-fit provenance | **Unknown** model-fit revision, tokenizer repository and tokenizer-fit revision, after inspecting the complete authoritative embedded provenance. No current revision substituted. |
| Compatibility with study pin | Name, geometry and capture convention are consistent with the study model; exact fit compatibility is **unestablished**. Checksum matching is not compatibility evidence. Transport gate still refuses. |
| Original-model baseline parity | **Not run.** The lens-independent one-case CI plan, prospective tolerances and commands are in [baseline_preflight.md](baseline_preflight.md). Missing lens provenance does not block this preparation. |

## Preserved checkouts and machine

All three trees were clean at entry and matched the reported starting points:

| Repository/branch | Starting and retained HEAD |
|---|---|
| engine: `codex/exploratory-methods-contracts` | `e816cd123b926e2e35c27c31b0cd64da7250bf08` |
| Causalab: `codex/paired-intervention-adapter` | `c153200275c9ceed070f396b3d3445d22bd5b2bd` |
| J++: `codex/lens-interop-contracts` | `6fd02c6f2787eeec4321d1356ddf2ce1d511b98e` |

Current source-file hashes are recorded in
[`local_preparation_sources.v1.json`](../../data/exploratory/local_preparation_sources.v1.json).
Those content hashes identify the local code; they do not make it fetchable by CI.
The continuation is intentionally uncommitted on those existing branches. The
reviewed one-case JSON, its prompts, and all established measurements are unchanged.
The original one-case file retains the initial adapter hashes; those are historical
pins, not a claim that its J++ adapter hash covers the new inspection helper.

The machine is arm64 macOS, 16 GiB RAM, 10 logical CPUs; free disk was about 220 GiB
before preparation and about 218 GiB afterwards. CUDA is unavailable; MPS is built/available outside the sandbox
but was not used. The sandbox's MPS query returned false, so it is not used as a
hardware conclusion. Apple Command Line Tools already existed. `uv` is 0.12.17
at `~/.local/bin/uv`; Python interpreters are engine 3.12.14, Causalab 3.12.14,
J++ inspection 3.13.4. No Rust toolchain was initially on PATH. Existing uv/pip
caches were about 2.2 GiB/603 MiB; the inspected default HF cache had no model
snapshot. No preexisting complete copy of the requested lens was found.

Environment/resource inventories are under
`/private/tmp/patientwords-local-preparation/`. Causalab's isolated Rust/cache/build
and installation evidence are under `/private/tmp/pw-causal-runtime/`.
No shell profile or system toolchain was changed.

## Authorized artifact download and full safe inspection

Exactly two release files were downloaded. The full repository and Qwen weights
were not downloaded. `curl -fsSI` checked the immutable commit, LFS size and digest
first; following the YAML redirect confirmed its size. A Python `urllib.request`
stream then fetched the two exact URLs, enforced the previewed byte counts and
SHA-256 values before renaming `.partial` files, and marked originals read-only.
The previously cached YAML had the same digest; the small fresh fetch establishes
the pinned URL's bytes directly.

External cache directory:
`~/Library/Caches/patientwords-exploratory/e166deb5ad540932100ef803c8c9bcc2a5453694/`

| File | Bytes | Verified SHA-256 |
|---|---:|---|
| `Qwen3-4B_jpp_lens.pt` | 458,763,919 | `893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d` |
| `config.yaml` | 2,496 | `6cf51651e2dfaab696cf86ce9e183738b53c9d6f4e3e7add428b6b20c451f957` |

The YAML says the checkpoint's own provenance is authoritative. The J++ fork now
exposes `inspect_verified_artifact(path, expected_sha256)` without requiring a
fabricated fit identity. Inspection and transport share the same open-file hash
check and CPU `torch.load(weights_only=True)`, with no unsafe fallback. Inspection
returns metadata only and explicitly does **not** authorize transport. The existing
`load_verified_lens` still refuses unknown fit identity before loading.

Actual full inspection used that Python API in the isolated tensor environment;
the CLI equivalent is:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../patient-words-jpp_lens/src \
/private/tmp/pw-methods-tensor-venv/bin/python -m lens_interop \
  --inspect "$HOME/Library/Caches/patientwords-exploratory/e166deb5ad540932100ef803c8c9bcc2a5453694/Qwen3-4B_jpp_lens.pt" \
  --sha256 893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d
```

The complete receipt, with every raw field and matrix shape, is
[`data/exploratory/jpp_artifact_inspection.v1.json`](../../data/exploratory/jpp_artifact_inspection.v1.json),
SHA-256 `4da53e8a51721d4b1f8e669dc19c13b3c48cac16be02ba85e46688e652221a30`.
This is artifact metadata, not a measurement collector input. Inspection took
0.946645 seconds including safe load; process maximum RSS was 687,521,792 bytes.
That is not model inference or fitting capacity.

Known from the complete file:

- Torch ZIP serialization, top-level `J`, `source_layers`, `d_model`, `n_prompts`,
  `provenance`; `J` has integer keys 0 through 34, each dense CPU float16
  `[2560,2560]`, all finite. Source-layer metadata matches those keys.
- Embedded `method=jpp`, `lrp_mode=rlens`, `capture_point=block_output`,
  `stream_reduce=none`, `stream_index=null`. Algebraic `lens_type=jacobian` does
  not change the method to J-Lens or R-Lens.
- `source_config.hf_model_name=Qwen/Qwen3-4B`, 96 trained prompts,
  `max_seq_len=128`, `skip_first_n_positions=16`, `jacobian_rows_per_pass=64`,
  `checkpoint_every_n_prompts=4`, `next_prompt_idx=0`, zero clusters/projection
  dimension, creation time `2026-10-07_01-38-11`, relative target −1.
- YAML explicitly gives absolute target 35 and FP16 conversion relative-error
  record `0.00023359624901786447`. Interpreting embedded −1 as block 35 is consistent
  with the 36-block model, but that geometry is not a historical revision record.
- Embedded source names `koayon/jpp_lens`; YAML source names
  `safety-research/jpp_lens`. Both are preserved, not silently reconciled.

Missing: model-fit commit, tokenizer repository/commit, fitting code commit,
complete dependency and data-selection records. The adjacent YAML's dataset
configuration and split are null. The intended study pin remains
`Qwen/Qwen3-4B@1cfa9a7208912126459214e8b04321603b3df60c` for model and tokenizer.
The [focused publisher question](lens_fit_provenance_question.md) is drafted,
**not sent**. Unknown provenance blocks compatible lens transport, not original
model baseline checks or synthetic intervention development.

## Causalab installation commands and evidence

The repository's `docs/standalone_install.md` path was followed in the existing
isolated environment, with `rust-toolchain.toml` selecting Rust/Cargo 1.98.1 and
`Cargo.lock` enforced. Official rustup bootstrap digest was verified before running
it with `--no-modify-path --profile minimal --default-toolchain 1.98.1` and the
repo's rustfmt/clippy components. `CARGO_HOME` and `RUSTUP_HOME` were scoped to
`/private/tmp/pw-causal-runtime/`, so no system install was needed.

Actual principal commands, from the Causalab checkout (the build also had the
isolated Cargo bin on PATH, its external target directory and two build jobs):

```bash
/private/tmp/pw-methods-causal-venv/bin/python scripts/export_requirements_lock.py --check
/Users/michaelgreen/.local/bin/uv build --wheel \
  --python /private/tmp/pw-methods-causal-venv/bin/python \
  --out-dir /private/tmp/pw-causal-runtime/wheels --config-setting build-args=--locked
/private/tmp/pw-methods-causal-venv/bin/python -m pip install \
  --require-hashes -r requirements.lock.txt --disable-pip-version-check \
  --cache-dir /private/tmp/pw-causal-runtime/pip-cache
/private/tmp/pw-methods-causal-venv/bin/python -m pip install --no-deps \
  --disable-pip-version-check \
  /private/tmp/pw-causal-runtime/wheels/causalab-0.0.1-cp310-abi3-macosx_11_0_arm64.whl
/private/tmp/pw-methods-causal-venv/bin/python -m pip check
/private/tmp/pw-methods-causal-venv/bin/causalab run \
  demos/methods/protocols/minimal_cpu.json --engine auto --device cpu \
  --data-root tests/protocol/fixtures/data \
  --artifacts-root tests/protocol/fixtures/artifacts \
  --out /private/tmp/pw-causal-runtime/installation-check/minimal_cpu
```

The actual smoke ran from `/private/tmp` with absolute checkout paths, two CPU
threads, an isolated HF cache and implicit-token/telemetry/Xet disabled. Full
commands, including scoped environment assignments, are in
`/private/tmp/pw-causal-runtime-handoff.md`. The external
`installation-check/manifest.json` labels the outputs `installation_check`,
`research_result=false` and records their hashes. No metrics enter any study
collector. The downloaded fixture is
`hf-internal-testing/tiny-random-LlamaForCausalLM@9fb191250dd56d0ba7ec9785a025ed29c03d5998`;
its model/config/tokenizer files total 6,476,958 bytes (model 4,131,280 bytes).

| Installation artifact | SHA-256 |
|---|---|
| `rust-toolchain.toml` | `c516d7668c46619d3628e48d52c37d13f470a85fcbd7f1e92bd643edcd9ec04d` |
| `Cargo.lock` | `d4774090736f0fab149fc125da766423e3e78ab88b96ba387eac8db5280369f9` |
| `uv.lock` | `ece3489fd35bc07658ae782d67bc1a8dabfddb1e750b1cc4197cc52a3608e8ac` |
| `requirements.lock.txt` | `4da30fc82f80f4a082b37a9a943dd0276fe39d2461ce2b5efcc00ecdb5dcea0c` |
| Built macOS arm64 wheel | `f0672b333f1198eafa8dffe0fd862e47962fd4e2b03856b0e90355bd26614068` |
| Imported `_core.abi3.so` | `511a0e68a5a5d6ba2d897d5e1db12a2e0b0b2e041abf9d64ce26b7ab1c1cbc77` |

Build: 61.61 seconds wall, max process RSS 368,050,176 bytes. Tiny CPU smoke:
26.15 seconds including downloads, max RSS 496,320,512 bytes, 2/2 eligible cells
and both expected output artifacts. These are installation timings, not Qwen
inference estimates. Existing matching dependencies were reused; all 84 applicable
versions match the hash-locked requirements. Full optional/dev groups were not
installed. The macOS wheel must be rebuilt for a future Linux runner.

The fixture's `pad_token_id=-1` warning is retained. A smoke-helper selection of
`minimal_cpu` found no document because that helper selects workflows; the direct
protocol command passed, as did a subsequent workflow smoke (1 document, 2 verbs,
0 failures). These warnings/initial selection failure are not research findings.

## Synthetic baseline integration check

The durable `tests/manual/baseline_protocol_smoke.py` constructs a random tiny
Qwen3 architecture and a local abstract tokenizer; it never reads the study
prompt file or downloads weights. It exercises the exact new public read-only
protocol builder. The first runtime attempt exposed unsupported input role names;
the builder was corrected to Causalab's `base`/`counterfactual` data roles while
preserving source/recipient output identities. Both bf16 `[1,1,16]` outputs now
exactly equal direct aligned forwards, and no hooks remain.

Actual portable command, run from `/private/tmp`:

```bash
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
/private/tmp/pw-methods-causal-venv/bin/python \
  /Users/michaelgreen/patientwords-engine-exploratory/tests/manual/baseline_protocol_smoke.py \
  --out-root /private/tmp/pw-causal-runtime/installation_checks/baseline_protocol_smoke_v1
```

Runtime body was 0.155624 seconds; process max RSS 428,081,152 bytes. Three output
refusal checks passed (existing output, repository path, wrong namespace).
The helper and output identify these as synthetic installation checks, not
released-model parity. Its source SHA-256 is
`7098890fca94d728930363f6da36de08d2091ce6a5f4bd54f8f63f961d709270`.

## Checks and next authorization

| Check actually run | Result |
|---|---|
| Engine full offline suite with external fresh bytecode cache | **5,099 passed, 9 skipped**, 261.85 seconds |
| New baseline contract tests (included above) | **42 passed** |
| Engine `ruff check --no-cache .` | Clean |
| J++ interop plus existing HF-layout tests | **55 passed**, 2.08 seconds; Ruff clean |
| Causalab adapter, native probe, public runtime, registry/capability tests | **208 passed**, 3.88 seconds, no skip; all three previously skipped compiled-runtime checks executed |
| Tiny downloaded random-model CPU installation check | Pass, 2/2 cells; installation outputs only |
| Portable random tiny Qwen3 read-only protocol smoke | Both exact-output comparisons and hook cleanup pass; three output refusal checks pass |
| Existing live-site contract validator | **0 errors, 1 existing warning**: 1,728/13,652 urgency rows lack published-scenario joins |
| Expanded seal sweep | **CLEAN: 183 sealed phrases, no new hits across 9 roots / 857 files**; existing allowlist unchanged |
| Engine package inventory before/after | Identical SHA-256 `73d8dcba59eeb50f22abe77eda2474954526ca5f66a30479c13aeb6079aa96d5` |
| Branch heads, source-hash receipt, original artifact digests and `git diff --check` | Match / clean |

The first full suite finished with 5,098 passed, 9 skipped and one source-inspection
failure: retained pytest bytecode pointed to the removed `/private/tmp/pw-methods-engine`
checkout. The source-inspection regression passed with a fresh external bytecode
cache, then the complete suite passed under that same cache. No package or source
change was needed. The successful command was:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/patientwords-local-preparation/fresh-bytecode \
/Users/michaelgreen/patientwords-engine/.venv/bin/python -m pytest -q -rs -p no:cacheprovider
/Users/michaelgreen/patientwords-engine/.venv/bin/ruff check --no-cache .
/Users/michaelgreen/patientwords-engine/.venv/bin/python scripts/validate_frontend_contract.py --site ../patientwords
```

Nine engine skips remain: two missing `inspect_petri`, three missing Playwright,
two missing `inspect_ai`, one PAB workflow not landed, and one scheduled workflow
without a push trigger. They are not passes. Full upstream J++ and Causalab suites,
Linux wheel installation, GPU execution, Qwen3-4B loading/parity and fitting were
not run. The model download-size estimate remains derived, not a measured transfer.

The seal check retained the existing exploratory branch as requested: remote
`main` was verified at `31ee9268c70a2c56d51aef9bd5412fb53f2e769c`, and the seal's
dashboard/source files are byte-identical to it with a non-null start stamp.
The expanded sweep included the prepared but unexecuted one-case protocol and
both installation-output directories. No sealed text was inspected or selected
for the experiment. Logs are outside Git under
`/private/tmp/patientwords-local-preparation/` and
`/private/tmp/pw-local-preparation-seal-final.log`.


The companion baseline plan records the exact future commands, numerical failure
criteria and clean-commit acquisition requirements. It is not wired to a trigger;
there is no authorized production fire command yet. No provisional API, trigger
key or workflow dispatch is invented.

The next authorization is to finalize and push the focused local branches for
review and add reviewed CI wiring. A subsequent, separate execution authorization
would permit the one-case baseline parity check on an existing suitable CPU runner.
That check needs no lens artifact or fit provenance. It requires identical pinned
model/tokenizer files, prompt bytes and token IDs, and retains both forward-call
argument parity and cross-environment parity as separate tests.
