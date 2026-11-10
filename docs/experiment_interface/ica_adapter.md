# ICA adapter: one saved basis, signed scores (2026-11-10)

Status: optional adapter, offline fixtures only. No model was run, no real corpus was read and no
released basis was downloaded. The only fits behind this page are toy fits on 48 synthetic rows of
width 8.

Code: `scripts/experiments/adapters/ica.py` (payload kind `ica_scores/1`) and
`scripts/experiments/activation_dataset.py` (ActivationDataset v1 reader, writer and validator).
Schemas: `schemas/experiments/ica_scores.v1.schema.json`,
`schemas/experiments/ica_basis_manifest.v1.schema.json`. Fixtures:
`tests/fixtures/experiments/ica/`. Tests: `tests/test_experiments_ica.py` (numpy only) and
`tests/test_experiments_ica_icalens.py` (needs the `icalens` package; skips without it).

## What the adapter does

It applies one saved ICA basis to captured residual-stream activations of the two members of a
pair and reports, per layer, token position and component:

- a signed score, `(preprocess(x) - center) @ reading_matrix.T`;
- a squared-coordinate share, `score**2 / sum(score**2)` over the fitted components;
- a reconstruction error in preprocessed space: `scores @ writing_matrix.T + center` against
  `preprocess(x)`, as an L2 error, a relative L2 error and a cosine.

The arithmetic is the one `icalens` 0.4.0 defines (`src/icalens/_arrays.py:11-53`,
`src/icalens/lens.py:302-335`, `src/icalens/lens.py:549-560`). Every `src/icalens/...` path on this
page is relative to the fork `michaeldgreenphd/patientwords-ica-lens-paper` at head
`aa3b95c9e755e4374f8c9645a064e3f51d96066e`.

The adapter fits nothing. A basis is fitted by `icalens` in its own environment and reaches the
adapter as a saved directory:
`icalens.json` plus `artifacts/<site>/layer_NN.safetensors` with `center`, `reading_matrix`,
`writing_matrix` and, for the `geometric-median-l2` mode only, `preprocessing_center`.

## What it does not do

- It does not fit, refit, profile or select components. There is no second FastICA here.
- It does not load a model or capture activations. Activations arrive as an ActivationDataset.
- It does not steer, clamp or ablate. See *Out of scope*.
- It does not name concepts. A component label or a vocabulary readout, when a manifest carries
  one, is copied with `status: "hypothesis"` and its source. A manifest whose annotation says
  anything else is refused (`annotation_status`).
- It does not compare components across two fits unless the caller supplies an alignment record,
  and never across layers. See *Signs*.
- It does not produce a summary number. The comparison block (`scripts/experiments/compare.py`)
  lists per-component differences and nothing else.

ICA is a compact representation tool: at most `hidden_size` components per layer, obtained by a
linear change of basis. It is not a drop-in substitute for a transcoder attribution graph, which
describes computation between layers, or for an overcomplete sparse autoencoder, which has more
latents than dimensions and a sparsity objective. A score here says how far an activation lies
along one saved direction. It does not say that the direction is a feature of the model.

## Identity fields

The saved lens records the model repository id, an optional model revision, the activation site, a
layer-indexing label, the preprocessing mode and the fit settings. It records no tokenizer
identity, no content hash of its tensor files and no model-load precision (read at
`src/icalens/lens.py:807-856`; the absence is what was verified). The basis manifest
(`patientwords.ica-basis-manifest/1`) adds what is missing and pins what exists:

| Field | Source |
|---|---|
| `model.hf_id`, `model.revision`, `model.type`, `model.hidden_size` | copied from `icalens.json` |
| `model.tokenizer_id`, `model.tokenizer_revision` | supplied by whoever builds the manifest; the artifact has none |
| `fit.corpus_id`, `fit.split`, `fit.family_ids`, `fit.corpus_ids`, `fit.document_token_sha256`, `fit.activation_manifest_sha256` | supplied; the last equals the hash `icalens` stores in a lens fitted from an ActivationDataset |
| `profile`, `selection` | supplied: which families or corpora those stages used |
| `capture.site`, `capture.layer_index_base` | supplied: the protocol's name for the site, and 0 |
| `capture.artifact_activation_site`, `capture.artifact_layer_indexing` | copied; the second is a free-text label in the artifact and is not relied on |
| `capture.precision` | the dtype of the activations given to the fit (`fitting.input_dtype`) |
| `capture.model_load_precision` | supplied, or null and listed in `not_recorded` |
| `seed` and per-layer `fit_settings` (algorithm, contrast function, `max_iter`, `n_iter`, `n_components`, `n_samples`, stopping criterion, device, torch version) | copied from each layer's `fitting` block |
| `preprocessing.mode`, `row_normalization`, `norm_eps` | read from `icalens.json#/input_preprocessing` |
| `artifact.files[*].sha256` | SHA-256 of every file in the saved directory, computed when the manifest is built |
| `layers.<k>.fit_diagnostics` (objective history, component strengths and objectives) | copied |
| `sign_convention`, `fit_diagnostics_statement` | fixed sentences; a manifest that alters them is refused |

A value the artifact lacks stays null and its JSON pointer is listed in `not_recorded`. An unlisted
null is refused (`silent_missing_provenance`). The manifest's own SHA-256 is the basis hash that a
protocol names in `methods[].basis.manifest_sha256` and that every payload repeats.

Identity is `recorded` only when the model id, a 40-hex model revision, the tokenizer id and a
40-hex tokenizer revision are all present, in the basis manifest and in the activation dataset
(the dataset's tokenizer sits in `provenance.patientwords.tokenizer`, because the format has no
tokenizer field). Anything else is `unknown`. The string `"unknown"`, which
`icalens fit activations` writes for a missing revision (`src/icalens/cli/fit_activations.py:77`),
counts as unknown. With an unknown identity the adapter produces no score: through the run store
the task ends `unavailable` with a reason that starts `unknown_identity`, not `failed`. Parity with
a real model is reported as not established in every payload, whatever the identity status.

## The fixed-basis rule

Both members of a pair are scored under one basis, identified by the manifest hash.

- The protocol names the hash. A manifest with another hash is not that basis: the task is
  `unavailable` when the named basis is absent, and `basis_mismatch` when a caller passes a
  different loaded basis.
- A file listed in the manifest whose bytes changed is refused before any tensor is used
  (`artifact_hash`). The test flips one bit of one matrix entry.
- Two payloads with different basis hashes are never differenced (`basis_mismatch`), in
  `compare.py` and in `ica.compare_pair`. No alignment record lifts this.

## Fitting uses the discovery split only

The manifest lists the family ids and corpus ids that fitting, profiling and selection used. The
adapter checks them against the protocol and refuses `split_leakage` when:

- `fit.split` is not `discovery`;
- any stage names a family whose split is `validation` or `fresh_test`;
- a listed fit-document token hash equals the token hash of a held-out variant;
- the fit dataset (when it is supplied) has a row-map document outside `discovery`;
- the basis was fit on the dataset that is being scored while that dataset holds held-out families.

Each payload records which of these checks ran (`split_leakage_checks`). A check that could not run
says so: for example `document_token_hashes: "not_listed_in_manifest"`. These checks compare ids
and hashes that the manifest declares. They cannot detect a corpus that overlaps the held-out
families under other ids; that is a limit of declared provenance, and it is not tested.

The fixtures keep the fit corpus and the scored rows in two separate datasets
(`discovery_activations/` and `pair_activations/`). Reason: `icalens fit activations` fits on every
row of the dataset it is given, so a dataset that also held validation rows would leak them into
the fit.

## Signs

Scores are signed, as saved. `icalens` orders components by absolute deviation of the contrast from
its Gaussian value and does not canonicalize signs (`src/icalens/lens.py:286-289`). A sign and a
component index mean something only inside one saved fit and one layer. They are not comparable
across fits, layers or models. The manifest and every payload carry that sentence.

`ica.compare_across_fits` therefore refuses `sign_convention` when asked to compare two fits
without an alignment record (`patientwords.ica-alignment/1`: the two basis hashes, one layer, the
method, the source, and pairs of `component_a`, `component_b`, `sign`). With a record, each listed
component of the second fit is mapped and multiplied by the recorded sign; unlisted components are
reported as unaligned and are not compared. The adapter does not derive an alignment and does not
check that a supplied one is right: the test shows that a record with wrong signs yields non-zero
gaps, which is the only signal. A record names two bases by hash. The function does not look up
which model each basis belongs to, so a record that pairs bases of two models would be applied as
written; that claim rests with whoever writes the record.

## What a squared-coordinate share is not

`score**2 / sum(score**2)` is labelled "squared-coordinate share, not a probability, not an
importance" in every payload.

- It is not a probability. It sums to 1 by construction, over the fitted components only.
- It is not an importance or an attribution. Nothing was intervened on.
- It discards sign and overall magnitude. The fixture's clinical and colloquial rows have opposite
  scores and identical shares.
- With `n_components < hidden_size` the denominator ignores the part of the activation outside the
  fitted subspace. Read it next to the reconstruction error.
- For a row whose scores are all zero the share is undefined. The payload records null with the
  status `not_computed_zero_energy`. `icalens` returns zeros for such a row
  (`src/icalens/lens.py:324`, `:330-335`); a zero would read as a measured value here, so the
  adapter does not copy it.

## Preprocessing is read from the artifact

The normalization default depends on the entry point. `ICALens(...)` without a mode normalizes
each row to unit L2 norm (`src/icalens/lens.py:75-76`). The three fitting commands default to
`none` (`src/icalens/cli/fit_activations.py:27`, `cli/fit_text.py:91-93`, `cli/fit_chat.py:72-74`).
Two of the package's own doc pages call L2 the default
(`patientwords-ica-lens-paper/docs/scores-and-energy.md:16`,
`patientwords-ica-lens-paper/docs/reconstruction.md:26`). A mode taken from a paper, a doc page or
a default can therefore be wrong for a given artifact.

The adapter takes the mode from `icalens.json#/input_preprocessing/icalens_preprocessing` of the
saved artifact and from nowhere else. When a saved manifest has no such key, `row_normalization`
of the same block is read, which is what `ICALens.from_pretrained` does
(`src/icalens/lens.py:653-655`). The basis manifest records the pointer the mode was read from. Three
places must agree, or the task is refused with `preprocessing_mismatch`: the saved artifact, the
manifest, and the protocol's `basis.preprocessing`. A `geometric-median-l2` artifact without its
`preprocessing_center` tensor is refused with the same code.

Reconstruction error is computed in the preprocessed space, because `inverse_transform` returns the
preprocessed activation (`src/icalens/lens.py:554-560`). For a normalized mode this is an error
between unit-norm vectors. `restore_norm` is not applied; the payload says so.

## Two execution paths

`ica.apply_basis` is the one entry point. It uses `icalens` when the package imports and the numpy
path otherwise. Both compute in float64 on the stored float32 matrices. When `icalens` runs, the
numpy path runs as well and the two must agree within `1e-9` relative to the largest absolute score
(at least 1), else the task is refused (`path_disagreement`). The payload records the path used, the
`icalens` and torch versions when that path ran, the import error when it did not, and the measured
gap.

Agreement between the two paths is agreement of arithmetic on the same saved matrices and the same
activations. It is not evidence about a model.

## ActivationDataset v1

`scripts/experiments/activation_dataset.py` writes and reads the format defined by
`patientwords-ica-lens-paper/docs/activation-dataset-format.md`: `activations.json`, `samples.safetensors` (int64
`document_index`, `position`, `token_id`) and one headerless row-major file per layer. It includes
a minimal safetensors reader and writer, because the engine environment has neither `torch` nor
`safetensors`.

The validator refuses more than the reference reader checks:

| Refusal | Condition |
|---|---|
| `incomplete` | top-level or per-layer status is not `complete`, or a `*.partial` file remains |
| `dimension_mismatch` | a layer file is not `sample_count * hidden_size * itemsize` bytes; a declared shape or a sample tensor's length is wrong |
| `non_finite` | NaN or infinity in a layer |
| `row_alignment` | a duplicate `(document_index, position)`; a row whose document is not in the row map; a required position with no row; a row whose token id differs from the protocol's token id at that position |
| `dataset_format` | wrong format name, version or dtype; a damaged safetensors container |

Row identity: the format carries no text and no prompt hash. A PatientWords writer adds
`provenance.patientwords` (`patientwords.activation-rows/1`): the tokenizer, the position policy
and one entry per document with its role (`fit_corpus` or `protocol_variant`), split, token count
and token hash, plus the family and variant for a protocol row. One misaligned row refuses the
whole dataset, not only the affected task.

Limits of this module: it writes float16, float32 and float64 and reads bfloat16 without writing
it; it assumes little-endian bytes, which the format does not declare (the reference writer emits
native order, `src/icalens/_activation_dataset.py:240`); it reads a layer file whole into memory,
which is right for fixtures and wrong for a 1M-row capture.

## Verified and not verified

Verified by running the reference implementation, in an isolated environment, on 2026-11-10
(Python 3.12.3; torch 2.13.0+cu130, the PyPI build, run on CPU; `icalens` 0.4.0 installed from a
`git archive` export of `aa3b95c`; numpy 2.4.6; safetensors 0.8.0). Command and result:
`/home/user/.venvs/ica/bin/python -m pytest -q -p no:cacheprovider tests/test_experiments_ica_icalens.py`,
13 passed.

| Statement | How |
|---|---|
| The reference reader reads the datasets this repository writes (float32 fixtures; float16 and float64 written in the test). Layer values, sample tensors, model block and manifest SHA-256 agree. | `icalens.ActivationDataset(...)`, `.layer(1)`, `.samples()`, `.provenance` |
| This repository's safetensors bytes equal the `safetensors` writer's bytes for the fixture files and for a mixed int64/int32/float16/float32/float64 file. | byte comparison with `safetensors.numpy.save` |
| This repository's reader reads what the reference writer produces, bfloat16 included. | `icalens._activation_dataset.ActivationDatasetWriter`, 3 rows of width 3 |
| `icalens` loads the hand-written toy basis and returns the hand-computed scores, shares and reconstruction. | `ICALens.from_pretrained`, `transform`, `energy`, `inverse_transform` |
| For a lens fitted by `icalens` on the 48 toy rows (4 components, 50 iterations, seed 7, CPU), in each of the three preprocessing modes, the numpy path and `icalens` agree on the 24 toy pair rows. | Largest absolute score difference: 0 against the package's numpy code path (it repeats the same float64 operations, so zero is expected and shows only that the formula is the same); at most 4.4e-16 against its torch code path; at most 4.8e-7 when `icalens` is given the stored float32 rows and computes in float32. The largest absolute score was 3.7, 2.5 and 1.4 in the three modes. Row cosines at least 1 - 1e-9. Asserted tolerances: 1e-9 (float64) and 1e-4 (float32 input), relative to the largest absolute score. |
| The manifest's preprocessing mode equals what the saved `icalens.json` records, in all three modes and for the constructor default (`l2`). | field comparison after `save` |
| A CPU fit repeats exactly with the same seed in one process and differs with another seed. | two fits compared entry by entry |

Verified only by reading the fork's source, not by running it: the per-layer `status` and `shape`
entries (the reference reader ignores them, `src/icalens/_activation_dataset.py:75-95`); the
`*.partial` convention (`:222-224`, `:258-260`); that `icalens fit activations` accepts these
datasets (that command needs CUDA, `src/icalens/cli/fit_activations.py:39-40`, and was not run);
byte order on a big-endian host.

Not verified, and not claimed:

- **No real-model parity.** No activation here came from a model. Whether scores computed from this
  project's own captures match scores from `icalens`'s capture path for the same model, tokenizer
  and precision is untested. The fork loads the model in bfloat16 on CUDA and in default precision
  on CPU (`src/icalens/analysis.py:884-904`), and a lens stores neither fact.
- **No released basis.** The four `sida/icalens-*` repositories were not read. The engine's
  `AGENTS.md` states that `huggingface.co` is blocked from development containers; the download
  was not attempted here. Their layers, revisions and preprocessing modes are unknown here. The capability matrix lists them as `artifact_available_identity_unknown`.
- **No convergence claim.** `fit_fastica` runs exactly `max_iter` iterations and saves no
  convergence flag (`src/icalens/_fastica.py:414-464`; `stopping_criterion: "fixed_iterations"`).
  A finished iteration budget does not establish stable components. The manifest copies the
  objective history and component strengths so that a reader can inspect them; nothing here
  judges them.
- **No speed claim.** The paper's benchmark speedups are not promised for this hardware. A real run
  must measure capture time, activation storage and fit memory itself. The planner's
  `estimate_activation_bytes` and `estimate_fit_bytes` are formulas, marked as estimates. The toy
  fit took about 0.02 s of wall time on CPU. The peak resident set size of the process was
  0.76 GB before the fit, almost all of it from importing torch, and 0.80 GB after. Those numbers
  describe 48 rows of width 8 and say nothing about a real model.
- **No component meaning.** No profile, label or vocabulary readout was produced or checked.

## Known problems in the fork that matter here

Read at `aa3b95c`. None was executed against a real model.

1. **Clamp on a `geometric-median-l2` lens omits the median offset.** `inverse_transform` returns
   the centered, normalized vector and does not add `preprocessing_center` back
   (`src/icalens/lens.py:554-560`). `generate(clamp=...)` writes
   `restore_norm(inverse_transform(scores), reference=hidden)` into the residual stream
   (`src/icalens/analysis.py:668-683`). Additive steering refuses a lens with a preprocessing
   center (`analysis.py:568-571`); the clamp path has no such guard. Failure path: fit with
   `geometric-median-l2`, call `generate(..., clamp=(c, v))`, and every position's residual is
   replaced by a vector that lacks the median shift. This adapter performs no clamp. The defect is a
   reason to keep interventions out of it.
2. **`icalens fit activations` does not validate the sample metadata.** `ActivationDataset.samples()`
   is the only place the sample tensors are checked, and the fitting command never calls it
   (`src/icalens/cli/fit_activations.py:49`, `:85`; callers of `.samples()` are `cli/integrity.py`,
   `cli/capture.py:304`, `cli/profile.py:393` and `:686`). Failure path: a dataset whose
   `samples.safetensors` is missing or misaligned fits without error, and the lens then records a
   manifest hash for rows that cannot be traced. Run
   `activation_dataset.validate_activation_dataset` before any fit.
3. **The same seed gives different initial matrices on CPU and CUDA (inferred, not run).** The
   initial unmixing matrix is drawn from `torch.Generator(device=fit_device)`
   (`src/icalens/_fastica.py:172-180`), and torch's CPU and CUDA generators are different streams.
   Consequence: component order and signs from a CUDA fit are not reproduced by a CPU fit with the
   same seed. No CUDA device was available to confirm it. The manifest records `fit_device` for
   this reason.
4. **A missing revision becomes the string `"unknown"`** (`cli/fit_activations.py:77`). The adapter
   treats it as an unknown identity.
5. **No tokenizer identity, tensor hashes or model-load precision in the lens** (`lens.py:807-856`).
   The basis manifest exists to carry them.

## Out of scope: interventions

Steering, clamping and ablation are not implemented and are refused: a method block that contains
`intervention`, `interventions`, `clamp`, `steer`, `steering`, `initial_steer` or `ablate` (at the
top level or inside `basis`) ends in the state `unsupported` with the code `unsupported_operation`.
An intervention is a separate experiment with its own prespecified plan, controls and edit-size
record. The existing contract for one is the `intervention_plan` of `scripts/exploratory_methods.py`
(`docs/exploratory/methods_integration.md`). Problem 1 above is one concrete reason not to reach an
intervention through a read-only adapter.

## Running the reference checks

The engine environment runs the numpy tests and skips the reference tests with an explicit reason:

```bash
python -m pytest -q -p no:cacheprovider tests/test_experiments_ica.py tests/test_experiments_ica_icalens.py
```

The reference tests run in an isolated environment that is not the engine environment and is not
inside either repository. Nothing is downloaded from a model host and no model is loaded:

```bash
python3.12 -m venv /home/user/.venvs/ica
/home/user/.venvs/ica/bin/python -m pip install torch==2.13.0 numpy==2.4.6 safetensors huggingface_hub tqdm pytest
git -C /path/to/patientwords-ica-lens-paper archive --format=tar HEAD pyproject.toml LICENSE \
  THIRD_PARTY_NOTICES.md README.md model_framing.json src | tar -x -C /path/to/scratch/icalens_src
/home/user/.venvs/ica/bin/python -m pip install --no-deps /path/to/scratch/icalens_src
/home/user/.venvs/ica/bin/python -m pytest -q -p no:cacheprovider tests/test_experiments_ica_icalens.py
/home/user/.venvs/ica/bin/python tests/manual/ica_bridge.py --out /path/outside/the/checkout/ica_bridge
```

The package is installed from a `git archive` export of the fork's head, so the fork's working tree
is not written to. `--no-deps` leaves out `transformers`, `datasets`, `gb10-load-llm` and
`matplotlib`; the Python API used here (`ActivationDataset`, `ICALens.fit`, `transform`,
`inverse_transform`, `save`, `from_pretrained` on a local directory) imports none of them.
The CPU wheel index (`https://download.pytorch.org/whl/cpu`) returned 403 through the sandbox proxy
on 2026-11-10, so the PyPI build of torch 2.13.0 was installed. It brings the CUDA libraries (the
environment is 4.8 GB) and runs on CPU here; `torch.cuda.is_available()` is false. torch 2.13.0 and
numpy 2.4.6 are the versions `constraints.txt` pins for the engine's CI.

`tests/manual/ica_bridge.py` writes a receipt with versions, fit settings, wall time, process peak
RSS and the path gaps. It refuses an output directory inside a Git checkout or under a protected
root.

## Regenerating the fixtures

```bash
python tests/fixtures/experiments/ica/build_ica_fixtures.py
```

Every fixture is synthetic and says so: `synthetic: true` in each JSON file, hand-written matrices
in the basis, hand-chosen integers in the activations. `tests/test_experiments_ica.py` rebuilds the
fixtures in a temporary directory and compares them byte for byte with the committed files.

## Citation, licence and attribution

Paper: Sida Liu, Feijiang Han, Sarah Wiegreffe and Furong Huang, "Non-Gaussianity Reveals
Interpretable Directions in Language Models", arXiv:2606.11722v2, 2026-10-19. This title, author
list and date are the owner's statement of the v2 record; the arXiv page was not fetched in this
work. The fork's `patientwords-ica-lens-paper/README.md:185-190`, its
`patientwords-ica-lens-paper/docs/index.md` and the model card it generates still cite the earlier
title, "ICA Lens: Interpreting Language Models Without Training Another Dictionary", with two
authors (Liu and Han); `patientwords-ica-lens-paper/pyproject.toml` lists the same two. That
citation is stale. The only place the fork names the v2 title is
`patientwords-ica-lens-paper/demo/paper-fitting-trajectories.ipynb`, which names no authors. Cite
the arXiv id with the version.

Software: `icalens` 0.4.0, MIT licence, "Copyright (c) 2026 Sida Liu and Feijiang Han"
(`patientwords-ica-lens-paper/LICENSE`).
Its `src/icalens/_fastica.py` is adapted from FastICA_torch
(`https://github.com/liusida/FastICA_torch`), copyright 2024 Richard Hakim, MIT
(`patientwords-ica-lens-paper/THIRD_PARTY_NOTICES.md`).

This repository copies no `icalens` source. `activation_dataset.py` and `adapters/ica.py` restate
a documented file layout and three published equations, and use the package as an installed
dependency in the isolated environment. If `_fastica.py` or any other part of the package is ever
copied here, both notices must travel with it. The licence of the released `sida/icalens-*` weights
and of their fitting corpora is not stated in the fork and was not read.
