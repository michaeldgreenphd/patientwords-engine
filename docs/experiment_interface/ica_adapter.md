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
| `capture.artifact_activation_site`, `capture.artifact_layer_indexing` | copied from `icalens.json`. The activation dataset's own `activation_site` and `layer_indexing` must equal them (see *Capture site*). The second is a free-text label in the artifact; it is compared as a string and not interpreted |
| `capture.precision` | the dtype of the activations given to the fit (`fitting.input_dtype`) |
| `capture.model_load_precision` | supplied, or null and listed in `not_recorded` |
| `seed` and per-layer `fit_settings` (algorithm, contrast function, `max_iter`, `n_iter`, `n_components`, `n_samples`, stopping criterion, device, torch version) | copied from each layer's `fitting` block |
| `preprocessing.mode`, `row_normalization`, `norm_eps` | read from `icalens.json#/input_preprocessing` |
| `artifact.files[*].sha256` | SHA-256 of every file in the saved directory, computed when the manifest is built |
| `layers.<k>.fit_diagnostics` (objective history, component strengths and objectives) | copied |
| `sign_convention`, `fit_diagnostics_statement`, `annotation_statement` | fixed sentences; a manifest that alters them is refused |
| `limitations` | must include the adapter's fixed list, and `synthetic_not_measurement` for a synthetic basis; a manifest may add entries |

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

The manifest's model block is compared with the saved artifact's own `icalens.json` when the basis
is loaded (`ica.check_manifest_against_artifact`). `icalens.json` is one of the pinned files, so a
difference means the manifest was edited after it was built.

- A model id, model type or revision in the manifest that differs from a value the artifact
  records is refused (`identity_mismatch`). The capture site and the layer-indexing label are
  compared in the same place (`layer_metadata`).
- The artifact's model block is the one `icalens` itself reads: `base_model` when
  `int(format_version) == 1`, `model` otherwise (`src/icalens/lens.py:651-652`,
  `ICALens.from_pretrained`; confirmed in the installed 0.4.0 package). `ica.artifact_model` makes
  the same choice and never falls back to the other block, so the adapter and the reference name
  the same model for one artifact. An artifact that holds both blocks with different contents is
  refused (`identity_mismatch`) when a manifest is built from it and when a basis is loaded: no
  `icalens` writer produces one, and which model it belongs to would depend on the reader.
- On the `icalens` execution path the lens that `icalens` loaded must carry the manifest's model
  id and revision (`identity_mismatch` otherwise). `icalens` fills in the string `"unknown"` for a
  revision the artifact lacks; that and a null manifest revision both mean "not recorded" and
  count as equal, so the arithmetic can still be run on such a basis through `apply_basis`, while
  `score_task` produces no payload from it (`unknown_identity`).
- When the artifact's revision is absent, null or the placeholder `"unknown"`, the basis identity
  is `unknown` whatever revision the manifest states, and `artifact_revision` is listed among the
  unknown fields. The manifest cannot know more about the fit than the artifact the fit wrote.
  Through the run store such a task ends `unavailable` with a reason that starts
  `unknown_identity`, as for any other unknown identity.
- A manifest value that is null claims nothing and is not a contradiction; the identity is then
  unknown for the usual reason.

The reference makes the corresponding comparison between a cached dataset and a lens, on model id
and, when the lens has one, revision (`src/icalens/cli/profile.py:618-626`).

## Capture site

The activation dataset records where its rows were captured: `activation_site` and
`layer_indexing` in `activations.json`. Both must be recorded and must equal the basis artifact's
values, or the task is refused (`layer_metadata`). The same layer number, width and model at
another site are different activations, and a score computed from them would carry the basis's
site name without having been captured there. The reference refuses the same case in its profile
command (`src/icalens/cli/profile.py:627-630`, "activation site differs", "layer indexing
differs"). The payload records the dataset's two values under `capture.activation_site` and
`capture.layer_indexing`, beside `capture.site`, which is the protocol's own name for the site.

A fit dataset, when one is supplied, is held to the same rule: its `activation_site` and
`layer_indexing` must be recorded and equal the basis artifact's (`layer_metadata`). A basis
manifest that names, by hash, a dataset captured at another site does not describe where the basis
was fitted, and the split-leakage report on that dataset would say `checked` about the wrong
rows.

This is a comparison of two recorded strings. It does not establish that the capture code read the
site those strings name.

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
- any stage names a family whose split is `validation` or `fresh_test`, in `family_ids`, in
  `corpus_ids` or, for the fit stage, in the singular `fit.corpus_id`;
- a listed fit-document token hash equals the token hash of a held-out variant;
- the fit dataset (when it is supplied) has a row-map document outside `discovery`, a document
  whose `family_id` or `corpus_id` is a held-out family id, a document whose token hash is a
  held-out variant's, or a dataset-level `corpus_id` that is a held-out family id;
- the basis was fit on the dataset that is being scored while that dataset holds held-out families.

The fit dataset's row map is read through the structural check the scored dataset gets
(`activation_dataset.row_map_documents`) before any document is compared. A document that is not
an object, a `family_id`, `corpus_id` or `variant` that is not a string (null and absent are
allowed), a `token_sha256` that is not 64 lower-case hex digits (null and absent are allowed), a
document index listed twice, an unknown role and a dataset-level `corpus_id` that is not a string
are refused (`row_alignment`). The reason: a list such as `["fam-2"]` under `family_id` equals no
held-out id, so a membership test would pass it as if it named nothing. A provenance block that
lists no documents (`documents` null or absent, or an empty list) is reported as
`fit_dataset_has_no_row_map`.

Each payload records which of these checks ran (`split_leakage_checks`), one word per check. A
check that had nothing to compare says so and is never reported as `checked`. The object holds
exactly these seven keys, and each key holds one of the words listed for it; `validate_payload`
refuses any other key set and any other word (`split_leakage`), and refuses a payload that says
`fit_dataset_not_supplied` under one of the two fit-dataset keys and not under the other. The list
is `ica.LEAKAGE_WORDS`:

| Key | Words |
|---|---|
| `fit_stage_ids`, `profile_stage_ids`, `selection_stage_ids` | `checked`, or `no_ids_listed` when the stage names no family and no corpus |
| `document_token_hashes` | `checked`, or `not_listed_in_manifest` |
| `fit_dataset_row_map` | `checked`; `checked_without_token_hashes` when a document of the fit dataset carries no token hash; `fit_dataset_has_no_row_map`; `fit_dataset_not_supplied` |
| `fit_dataset_file_pins` | `verified`, `not_recorded`, or `fit_dataset_not_supplied` (see *ActivationDataset v1*) |
| `scoring_dataset_is_fit_dataset` | `checked`, or `not_checked` when the manifest names no fit dataset hash |

These checks compare ids and hashes that the manifest and the fit dataset declare. They cannot
detect a corpus that overlaps the held-out families under other ids and without token hashes: the
test shows that such a fit dataset passes with `checked_without_token_hashes`. That is a limit of
declared provenance.

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

The validator refuses more than the reference reader checks. (The reference's profile command
makes further checks on a cached dataset, `src/icalens/cli/profile.py:618-637`; the adapter makes
the corresponding ones in `ica.py`, see *Identity fields* and *Capture site*.)

| Refusal | Condition |
|---|---|
| `incomplete` | top-level or per-layer status is not `complete`, or a `*.partial` file remains |
| `dimension_mismatch` | a layer file is not `sample_count * hidden_size * itemsize` bytes; a declared shape or a sample tensor's length is wrong |
| `non_finite` | NaN or infinity in a layer |
| `row_alignment` | a duplicate `(document_index, position)`; a row whose document is not in the row map; a required position with no row; a row whose token id differs from the protocol's token id at that position |
| `dataset_format` | wrong format name, version or dtype; a damaged safetensors container; any other malformed input, for example a dtype that is not a string, a layer key that is not an ASCII decimal number, a declared tensor shape whose element count does not match its bytes (counted with Python integers, so a shape such as `[2**32, 2**32]` cannot overflow to zero), or a file-pin block that is present and malformed |
| `artifact_hash` | a layer file or the samples file differs from the SHA-256 or byte count the manifest records for it |

Row identity: the format carries no text and no prompt hash. A PatientWords writer adds
`provenance.patientwords` (`patientwords.activation-rows/1`): the tokenizer, the position policy
and one entry per document with its role (`fit_corpus` or `protocol_variant`), split, token count
and token hash, plus the family and variant for a protocol row. One misaligned row refuses the
whole dataset, not only the affected task. A dataset whose position policy is `last` cannot answer
a method block that asks for `positions: "all"`: the task is refused (`row_alignment`), not scored
at the one position the dataset holds.

File pins. The format records no hash of a layer file or of the samples file, so two datasets
with the same manifest and different activation values were indistinguishable. The writer in this
repository records the SHA-256 and byte count of every layer file and of the samples file under
the provenance key `patientwords_files` (`patientwords.activation-files/1`). The manifest is
written last, so the manifest's own SHA-256 then covers the values, and that hash is what a basis
manifest names in `fit.activation_manifest_sha256`. The reader verifies a pinned file every time
it reads one. `icalens` 0.4.0 reads a manifest that carries this key (the reference tests below
read both fixture datasets, which carry it).

A dataset without the key, which is what the reference writer produces, is accepted. Its
validation report and the payload say `file_pins: "not_recorded"`, and nothing fills the pins in:
the manifest is not rewritten. Such a dataset is identified by its manifest alone, so a changed
layer file cannot be refused. The payload still records the SHA-256 of the sample bytes and of
each layer file the task read (`capture.activation_dataset.samples_sha256`, `layer_sha256`), in
both cases. With `file_pins: "verified"` those hashes equal the manifest's record. With
`not_recorded` they describe what this run read and are not a statement by the dataset's writer.

Writing. Every check on the arguments runs before a file is created; finiteness is checked on the
values after the cast, so a float64 value that overflows float32 is refused (`non_finite`). The
files are written to a staging directory inside the target (`.staging-*`), validated there in
full, and moved into place with the manifest last.

Where the writer writes. The target passes `common.check_output_path`, and the files are then
moved only through real directories inside that target. A symbolic link at the target, at
`layers` or at a destination file is refused (`protected_root`, the code of the path guard such a
link would get around) before anything is created. Before this check, a target whose `layers` was
a link to another directory had its layer file moved into that directory, which no path rule had
looked at. The check reads the directory entries right before the move. It is not a
descriptor-relative write, so a link that another process creates between the check and the move
is not covered.

What a write that does not complete leaves behind:

- Refused, or failed, before the move into place: the target is as it was. No new directory, no
  changed file, no staging directory.
- A failure during the move into place that Python can handle (an I/O error on one file, an
  interrupt): the previous dataset is put back. Each file being replaced is first moved into
  `.staging-*/.replaced/`, the old manifest before any other file; the new files are then moved
  in, the new manifest last; the installed dataset is validated; only then are the old files
  removed. On a failure at any of those steps the new files are removed and the old ones moved
  back, and the previous dataset reads byte for byte as before. The test fails each of the six
  moves of a three-file overwrite in turn, with an `OSError` and with a `KeyboardInterrupt`.
- The moves back fail as well (the disk keeps failing): the staging directory is kept, the
  refusal (`incomplete`) names it, and the old files are in its `.replaced` directory.
- The process is killed during the move into place, or power is lost: no handler runs. The old
  manifest left first and the new one arrives last, so the target has no `activations.json` and
  every reader refuses the directory (`dataset_format`); a reader never sees a manifest beside
  files it was not written with. The replaced files are under `.staging-*/.replaced/` with their
  relative names and can be moved back by hand. A kill after the new manifest is in place leaves
  the complete new dataset and a leftover staging directory. A later write to a target that holds
  a `.staging-*` directory is refused (`incomplete`) until a person has dealt with it. The moves
  are renames and are not fsynced; nothing is claimed about a filesystem that reorders them across
  a power loss. This case was not tested: no test kills the process.

A file of the previous dataset that the new dataset does not name (a layer the new one lacks, or a
layer file of another dtype) is left in place; the new manifest does not list it.

Limits of this module: it writes float16, float32 and float64 and reads bfloat16 without writing
it; it assumes little-endian bytes, which the format does not declare (the reference writer emits
native order, `src/icalens/_activation_dataset.py:240`); it reads a layer file whole into memory,
which is right for fixtures and wrong for a 1M-row capture.

## What a filed payload must satisfy

`IcaAdapter.validate_payload` checks a payload against its task before the run store files it. It
reads no file. Beyond structure, family, variant, model, tokenizer, basis hash, layers, positions
and token ids, it requires:

- every fixed statement to equal the adapter's constant: `identity.parity`, the sign convention,
  the energy-share label and definition, the score definition, the reconstruction space, definition
  and `restore_norm` note, the fit-diagnostics statement and the annotation statement
  (`payload_labels`);
- `limitations` to include the adapter's fixed list, and `synthetic_not_measurement` for a
  synthetic payload (`payload_labels`); a longer list is accepted;
- the basis's synthetic flag to equal the payload's (`synthetic_label`), the fit split to be the
  protocol's discovery split (`split_leakage`), and the capture site and layer index base to be the
  task's (`layer_metadata`);
- `split_leakage_checks` to hold exactly the seven keys `check_split_leakage` returns and, under
  each, one of the words of the table in *Fitting uses the discovery split only*
  (`split_leakage`). A filed payload cannot say `passed`, and cannot turn
  `checked_without_token_hashes` into a word the adapter never reports. It can still be edited from
  one listed word to another (for example to `checked`); see the last paragraph of this section;
- the dataset's manifest hash, sample hash and one layer hash per scored layer, with `file_pins`
  one of its two words (`artifact_hash`);
- every squared-coordinate share to equal `score**2 / sum(score**2)` recomputed from the scores of
  the same row within `1e-9`, the recorded total to equal the sum of squares, and the status to
  follow from that sum (`energy_share_mismatch`). A payload whose shares sum to 1 and were not
  computed from its scores is refused;
- `relative_l2_error` to equal `l2_error / preprocessed_l2_norm` (`reconstruction_mismatch`);
- every component annotation to be a hypothesis with a source, to name a scored layer and one of its
  components, and to hold only `layer`, `component`, `status`, `label`, `source` and
  `vocabulary_readout` (`annotation_status`).

Scores and reconstruction errors themselves cannot be recomputed from a payload: that needs the
activations. A payload with edited scores and consistently edited shares passes this check. What
ties scores to inputs is the run store's hash of the payload file and the input identity below.

## Input identity for reuse

`IcaAdapter.input_identity(task, context)` is the run store's optional reuse hook. It returns one
SHA-256: the canonical digest of `IcaAdapter.input_identity_record(task, context)`, a JSON object
that holds the SHA-256 of the basis manifest and of every artifact file it lists, of the pair
dataset's manifest, samples file and the layer files the task reads, of the fit dataset's files
when the fixtures hold one, of the adapter's two source files, and the installed versions of
numpy, `icalens` and torch with the requested execution path. Files are hashed and never decoded;
nothing is written. A file that cannot be read gives a null in the record and `None` from the
hook, which the store treats as "cannot be identified now".

## Verified and not verified

Verified by running the reference implementation, in an isolated environment, on 2026-11-10
(Python 3.12.3; torch 2.13.0+cu130, the PyPI build, run on CPU; `icalens` 0.4.0 installed from a
`git archive` export of `aa3b95c`; numpy 2.4.6; safetensors 0.8.0). Command and result:
`/home/user/.venvs/ica/bin/python -m pytest -q -p no:cacheprovider tests/test_experiments_ica_icalens.py`,
14 passed.

| Statement | How |
|---|---|
| The reference reader reads the datasets this repository writes (float32 fixtures; float16 and float64 written in the test). Layer values, sample tensors, model block and manifest SHA-256 agree. | `icalens.ActivationDataset(...)`, `.layer(1)`, `.samples()`, `.provenance` |
| This repository's safetensors bytes equal the `safetensors` writer's bytes for the fixture files and for a mixed int64/int32/float16/float32/float64 file. | byte comparison with `safetensors.numpy.save` |
| This repository's reader reads what the reference writer produces, bfloat16 included. | `icalens._activation_dataset.ActivationDatasetWriter`, 3 rows of width 3 |
| `icalens` loads the hand-written toy basis and returns the hand-computed scores, shares and reconstruction. | `ICALens.from_pretrained`, `transform`, `energy`, `inverse_transform` |
| For a lens fitted by `icalens` on the 48 toy rows (4 components, 50 iterations, seed 7, CPU), in each of the three preprocessing modes, the numpy path and `icalens` agree on the 24 toy pair rows. | Largest absolute score difference: 0 against the package's numpy code path (it repeats the same float64 operations, so zero is expected and shows only that the formula is the same); at most 4.4e-16 against its torch code path; at most 4.8e-7 when `icalens` is given the stored float32 rows and computes in float32. The largest absolute score was 3.7, 2.5 and 1.4 in the three modes. Row cosines at least 1 - 1e-9. Asserted tolerances: 1e-9 (float64) and 1e-4 (float32 input), relative to the largest absolute score. |
| The manifest's preprocessing mode equals what the saved `icalens.json` records, in all three modes and for the constructor default (`l2`). | field comparison after `save` |
| A CPU fit repeats exactly with the same seed in one process and differs with another seed. | two fits compared entry by entry |
| `icalens` 0.4.0 reads `base_model` from an artifact whose `format_version` is 1 and `model` otherwise, and fills in `"unknown"` for a missing revision. The adapter refuses the icalens path when the loaded lens's model id or revision is not the manifest's. | `ICALens.from_pretrained(...).model_id`, `.model_revision` on a fitted lens, on a copy with `format_version` 1 and two differing blocks, and on a copy with no revision |

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

The hashes chain: each dataset manifest records the SHA-256 of its layer file and samples file, the
basis manifest names the discovery dataset by its manifest hash, and the method block names the
basis by the basis manifest's hash. A change to a dataset therefore changes the basis hash.
`tests/fixtures/experiments/protocol_synthetic_ica.json` repeats the method block and has to be
updated in the same change; `tests/test_experiments_slice.py` compares the two.

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
