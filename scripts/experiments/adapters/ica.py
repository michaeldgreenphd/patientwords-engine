"""Payload kind ``ica_scores/1``: one fixed, saved ICA basis applied to captured activations.

The basis is an ICA Lens artifact saved by the ``icalens`` package (``icalens.json`` plus
``artifacts/<site>/layer_NN.safetensors`` holding ``center``, ``reading_matrix``, ``writing_matrix`` and,
for one preprocessing mode, ``preprocessing_center``). This module fits nothing: fitting is done by
``icalens`` in its own environment (``tests/manual/ica_bridge.py``). It reads a saved basis through a
PatientWords basis manifest (``patientwords.ica-basis-manifest/1``) that pins every artifact file by SHA-256
and records the identity the artifact itself lacks.

Arithmetic, as defined by ``icalens`` 0.4.0 (``src/icalens/_arrays.py:11-53``, ``lens.py:302-335``,
``lens.py:549-560``)::

    x1     = x - preprocessing_center            only when the artifact holds that tensor
    x_pre  = x1 / max(||x1||, norm_eps)          only when the saved mode normalizes rows
    scores = (x_pre - center) @ reading_matrix.T                 signed
    x_hat  = scores @ writing_matrix.T + center                  in preprocessed space
    share  = score**2 / sum(score**2 over the fitted components)

One function, ``apply_basis``, has two execution paths. ``icalens`` is the reference implementation and is
used when it imports. The numpy path applies the saved matrices directly; it runs where ``torch`` is absent and
serves as an independent cross-check where ``icalens`` is present. Every payload records which path produced it.

What this adapter refuses, by code: ``basis_mismatch``, ``artifact_hash``, ``dimension_mismatch``,
``non_finite``, ``preprocessing_mismatch``, ``split_leakage``, ``sign_convention``, ``row_alignment``,
``incomplete``, ``unknown_identity``, ``identity_mismatch``, ``layer_metadata``, ``synthetic_label``,
``annotation_status``, ``path_disagreement`` and ``unsupported_operation`` (any intervention). Through the run
store, an unknown identity or an incomplete dataset is the state ``unavailable``; the other refusals are the
state ``invalid``.

Three comparisons tie the inputs together. The basis manifest's model id, type and revision are compared with
the saved artifact's own ``icalens.json``; a contradiction is ``identity_mismatch``, and a saved revision that
is absent or is the placeholder ``"unknown"`` makes the basis identity unknown whatever the manifest says. The
activation dataset's ``activation_site`` and ``layer_indexing`` must equal the values the basis artifact
records (``layer_metadata``). The dataset's layer files and samples file are verified against the SHA-256
values its manifest records, when it records them (``artifact_hash``); every payload names the dataset by its
manifest hash and by the SHA-256 of the layer bytes and sample bytes that were read, and says whether the
manifest pinned them (``file_pins``: ``verified`` or ``not_recorded``).

No statistic is computed here and no random number is drawn. The seed this module records is the fit's seed,
copied from the saved artifact.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from scripts.experiments.activation_dataset import (
    PINS_NOT_RECORDED, PINS_VERIFIED, ActivationDataset, exact_revision, open_activation_dataset, read_safetensors,
    row_index, validate_activation_dataset, variant_rows,
)
from scripts.experiments.common import (
    FIXTURE_BACKEND, FIXTURE_MODEL, HEX64, Refusal, digest, integer, read_json, require, require_structure,
    sha256_file, text,
)
from scripts.experiments.envelope import null_pointers

METHOD_ID = "ica_lens"
PAYLOAD_KIND = "ica_scores/1"
BASIS_SCHEMA = "patientwords.ica-basis-manifest/1"
ALIGNMENT_SCHEMA = "patientwords.ica-alignment/1"

# Where the offline fixtures live under context["fixtures_dir"].
FIXTURE_SUBDIR = "ica"
BASIS_MANIFEST_FILE = "basis_manifest.json"
PAIR_DATASET_DIR = "pair_activations"
FIT_DATASET_DIR = "discovery_activations"

ARTIFACT_MANIFEST = "icalens.json"
ARTIFACT_FORMAT = "icalens"
PREPROCESSING_MODES = ("none", "l2", "geometric-median-l2")
EXECUTION_PATHS = ("icalens", "numpy")
STAGES = ("fit", "profile", "selection")
NOT_APPLICABLE = "not_applicable"

SIGN_CONVENTION = "as saved; not canonicalized; not comparable across fits, layers or models"
ENERGY_LABEL = "squared-coordinate share, not a probability, not an importance"
DIAGNOSTICS_STATEMENT = (
    "A finished iteration budget does not establish stable components. The fit runs a fixed number of "
    "iterations and saves no convergence flag. Component stability needs repeated fits with other seeds and "
    "other samples; none is recorded here.")
SCORE_DEFINITION = "(preprocess(x) - center) @ reading_matrix.T; signed; one fixed basis"
ENERGY_DEFINITION = "score**2 / sum of score**2 over the fitted components of that layer and position"
RECONSTRUCTION_DEFINITION = "scores @ writing_matrix.T + center, compared with preprocess(x)"
RESTORE_NORM = ("not_applied: errors are computed in the preprocessed space. icalens restore_norm rescales a "
                "reconstruction to a reference norm for interventions, which this adapter does not perform.")
ANNOTATION_STATEMENT = ("Component labels and vocabulary readouts are hypotheses carried with their source. "
                        "None is a verified concept.")
CENTERING = ("The mean of the preprocessed fitting rows (tensor 'center') is subtracted before the reading "
             "matrix is applied.")
WHITENING = ("Recorded from the artifact's fitting block. Whitening is folded into reading_matrix and is not a "
             "separate step at scoring time.")
INTERVENTION_KEYS = ("intervention", "interventions", "clamp", "steer", "steering", "initial_steer", "ablate")
INTERVENTION_REASON = (
    "This adapter reads scores from captured activations. It does not clamp, steer or ablate. An intervention "
    "is a separate experiment with its own prespecified plan, controls and edit-size record: see the "
    "intervention_plan of the exploratory contract (scripts/exploratory_methods.py, "
    "docs/exploratory/methods_integration.md) and docs/experiment_interface/ica_adapter.md, section 'Out of scope'.")
PARITY_NOTE = ("not_established: no real model was run and no score was compared with a real-model capture. "
               "Agreement between the two execution paths is agreement of arithmetic on the same saved matrices.")
PATH_TOLERANCE = 1e-9
# validate_payload recomputes each share from the row's scores and compares within this absolute tolerance.
SHARE_TOLERANCE = 1e-9
SYNTHETIC_LIMITATION = "synthetic_not_measurement"
# What a saved artifact holds when no revision was given: nothing, or the string `icalens fit activations` writes.
PLACEHOLDER_REVISIONS = (None, "", "unknown")
LEAKAGE_STAGE_WORDS = ("checked", "no_ids_listed")
INPUT_IDENTITY_SCHEMA = "patientwords.ica-input-identity/1"
# An annotation row of a payload holds these keys and no other: a "verified" key has nowhere to sit. The basis
# manifest's schema closes the same set for the manifest.
ANNOTATION_KEYS = ("layer", "component", "status", "label", "source", "vocabulary_readout")
LIMITATIONS = (
    "signs_as_saved_not_comparable_across_fits_layers_or_models",
    "energy_share_is_a_squared_coordinate_share_not_a_probability_or_importance",
    "reconstruction_error_is_in_preprocessed_space",
    "component_labels_are_hypotheses",
    "a_finished_iteration_budget_does_not_establish_stable_components",
    "no_real_model_parity",
)


# ----------------------------------------------------------------------------------------- basis manifest

def artifact_preprocessing(artifact_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The preprocessing the saved artifact records. Nothing is taken from a paper or a default.

    A saved manifest without an ``icalens_preprocessing`` key is read the way
    ``ICALens.from_pretrained`` reads it: ``row_normalization`` decides, and the source pointer says so.
    """
    block = artifact_manifest.get("input_preprocessing")
    require(isinstance(block, dict), "preprocessing_mismatch", f"{ARTIFACT_MANIFEST} has no input_preprocessing")
    normalization = block.get("row_normalization")
    require(normalization in ("none", "l2"), "preprocessing_mismatch",
            f"{ARTIFACT_MANIFEST}: row_normalization is {normalization!r}; expected 'none' or 'l2'")
    mode = block.get("icalens_preprocessing")
    source = f"{ARTIFACT_MANIFEST}#/input_preprocessing/icalens_preprocessing"
    if mode is None:
        mode = "l2" if normalization == "l2" else "none"
        source = f"{ARTIFACT_MANIFEST}#/input_preprocessing/row_normalization (no icalens_preprocessing key)"
    require(mode in PREPROCESSING_MODES, "preprocessing_mismatch",
            f"{ARTIFACT_MANIFEST}: icalens_preprocessing is {mode!r}; expected one of {list(PREPROCESSING_MODES)}")
    require((mode == "none") == (normalization == "none"), "preprocessing_mismatch",
            f"{ARTIFACT_MANIFEST}: mode {mode!r} contradicts row_normalization {normalization!r}")
    eps = block.get("norm_eps", 1e-12)
    require(type(eps) in (int, float) and math.isfinite(eps) and eps > 0, "preprocessing_mismatch",
            f"{ARTIFACT_MANIFEST}: norm_eps must be a finite positive number")
    return {"mode": mode, "read_from": source, "row_normalization": normalization,
            "pre_normalization_center": block.get("pre_normalization_center",
                                                  "geometric_median" if mode == "geometric-median-l2" else "none"),
            "norm_eps": float(eps)}


def artifact_model(artifact_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The model block of a saved ``icalens.json`` (``model``, or ``base_model``), or an empty dict."""
    for key in ("model", "base_model"):
        block = artifact_manifest.get(key)
        if isinstance(block, dict) and block:
            return block
    return {}


def basis_identity(manifest: Mapping[str, Any], saved_model: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Model and tokenizer identity of a basis manifest. ``recorded`` needs both ids and two 40-hex revisions.

    ``saved_model`` is the model block of the saved artifact's own ``icalens.json``. When it is given and its
    revision is not a 40-hex commit (absent, null, ``"unknown"``, a branch name), the status is ``unknown`` and
    ``artifact_revision`` is listed, whatever revision the manifest states: the manifest cannot know more about
    the fit than the artifact the fit wrote.
    """
    model = manifest.get("model") if isinstance(manifest.get("model"), dict) else {}
    unknown = [key for key in ("hf_id", "tokenizer_id") if not text(model.get(key))]
    unknown += [key for key in ("revision", "tokenizer_revision") if not exact_revision(model.get(key))]
    if saved_model is not None and not exact_revision(saved_model.get("revision")):
        unknown.append("artifact_revision")
    return {"model_id": model.get("hf_id"), "model_revision": model.get("revision"),
            "tokenizer_id": model.get("tokenizer_id"), "tokenizer_revision": model.get("tokenizer_revision"),
            "status": "unknown" if unknown else "recorded", "unknown_fields": sorted(unknown),
            "parity": "not_established"}


def _common(values: Iterable[Any]) -> Any:
    """The single value shared by every layer, or the string ``differs_by_layer``."""
    seen = list(values)
    return seen[0] if all(value == seen[0] for value in seen) else "differs_by_layer"


def _stage(block: Mapping[str, Any] | None) -> dict[str, Any]:
    block = dict(block or {})
    return {"performed": bool(block.get("performed", False)), "family_ids": list(block.get("family_ids", [])),
            "corpus_ids": list(block.get("corpus_ids", [])), "description": block.get("description", "")}


def build_basis_manifest(lens_dir: Path | str, *, basis_id: str, synthetic: bool, artifact_root: str,
                         tokenizer_id: str | None, tokenizer_revision: str | None, fit: Mapping[str, Any],
                         capture_site: str, layer_index_base: int, description: str = "",
                         profile: Mapping[str, Any] | None = None, selection: Mapping[str, Any] | None = None,
                         component_annotations: Iterable[Mapping[str, Any]] = (),
                         model_load_precision: str | None = None) -> dict[str, Any]:
    """Build a basis manifest from a saved ICA Lens directory. Reads files; writes nothing.

    Read from the artifact: model id, revision and type, hidden size, the preprocessing mode, layers, each
    layer's fit settings and diagnostics, the package version, and the SHA-256 of every file in the directory.
    Supplied by the caller, because the artifact does not hold them: the tokenizer identity, the fit corpus
    description (``fit``: ``corpus_id``, ``split``, ``family_ids``, ``corpus_ids``, optional
    ``document_token_sha256``, ``activation_manifest_sha256``, ``description``), the protocol's name for the
    capture site, the layer index base, and which families the profiling and selection stages used.
    A value the artifact lacks stays null and its pointer is listed in ``not_recorded``.
    ``artifact_root`` is the artifact directory relative to the place the manifest will be stored.
    """
    root = Path(lens_dir).resolve()
    require((root / ARTIFACT_MANIFEST).is_file(), "artifact_hash", f"{root} holds no {ARTIFACT_MANIFEST}")
    saved = read_json(root / ARTIFACT_MANIFEST)
    require(isinstance(saved, dict) and saved.get("format") == ARTIFACT_FORMAT and isinstance(
        saved.get("layers"), dict) and bool(saved["layers"]), "artifact_format",
        f"{ARTIFACT_MANIFEST} is not an ICA Lens manifest with at least one layer")
    model = artifact_model(saved)
    preprocessing = artifact_preprocessing(saved)
    files = [{"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size}
             for path in sorted(p for p in root.rglob("*") if p.is_file())]
    by_path = {entry["path"]: entry for entry in files}
    layers: dict[str, Any] = {}
    for key in sorted(saved["layers"], key=int):
        entry = saved["layers"][key]
        fitting = entry.get("fitting") or {}
        require(entry.get("file") in by_path, "artifact_hash", f"layer {key}: {entry.get('file')!r} is not on disk")
        tensors = read_safetensors(root / entry["file"])
        layers[str(int(key))] = {
            "file": entry["file"], "sha256": by_path[entry["file"]]["sha256"],
            "n_components": entry.get("n_components"),
            "tensors": {name: list(tensor.shape) for name, tensor in sorted(tensors.items())},
            "fit_settings": {
                "algorithm": fitting.get("algorithm"), "ica_algorithm": fitting.get("ica_algorithm"),
                "fun": fitting.get("fun"), "max_iter": fitting.get("max_iter"), "n_iter": fitting.get("n_iter"),
                "n_components": entry.get("n_components"), "n_samples": fitting.get("n_samples"),
                "stopping_criterion": fitting.get("stopping_criterion"), "seed": fitting.get("random_state"),
                "implementation": fitting.get("implementation"),
                "implementation_version": fitting.get("implementation_version"),
                "torch_version": fitting.get("torch_version"), "fit_device": fitting.get("fit_device"),
                "input_dtype": fitting.get("input_dtype"), "whiten": fitting.get("whiten"),
                "whiten_solver": fitting.get("whiten_solver"), "batch_size": fitting.get("batch_size"),
            },
            "fit_diagnostics": {
                "objective_history": fitting.get("objective_history"),
                "component_strengths": fitting.get("component_strengths"),
                "component_objectives": fitting.get("component_objectives"),
                "gaussian_objective": fitting.get("gaussian_objective"),
            },
            "component_id_convention": fitting.get("component_id_convention"),
        }
    fit_block = dict(fit)
    manifest: dict[str, Any] = {
        "schema_version": BASIS_SCHEMA, "basis_id": basis_id, "synthetic": bool(synthetic),
        "description": description,
        "model": {"hf_id": model.get("repo_id"), "revision": model.get("revision"), "type": model.get("type"),
                  "tokenizer_id": tokenizer_id, "tokenizer_revision": tokenizer_revision,
                  "hidden_size": saved.get("hidden_size")},
        "fit": {"corpus_id": fit_block.get("corpus_id"), "split": fit_block.get("split"),
                "description": fit_block.get("description", ""),
                "family_ids": list(fit_block.get("family_ids", [])),
                "corpus_ids": list(fit_block.get("corpus_ids", [])),
                "document_token_sha256": fit_block.get("document_token_sha256"),
                "activation_manifest_sha256": fit_block.get("activation_manifest_sha256"),
                "n_samples": _common(layer["fit_settings"]["n_samples"] for layer in layers.values())},
        "profile": _stage(profile), "selection": _stage(selection),
        "capture": {"site": capture_site, "artifact_activation_site": saved.get("activation_site"),
                    "layer_index_base": layer_index_base, "artifact_layer_indexing": saved.get("layer_indexing"),
                    "layers": sorted(int(key) for key in layers),
                    "precision": _common(layer["fit_settings"]["input_dtype"] for layer in layers.values()),
                    "model_load_precision": model_load_precision},
        "seed": _common(layer["fit_settings"]["seed"] for layer in layers.values()),
        "preprocessing": {**preprocessing, "centering": CENTERING, "whitening": WHITENING},
        "artifact": {"root": artifact_root, "format": saved.get("format"),
                     "format_version": saved.get("format_version"),
                     "package_version": saved.get("package_version"), "files": files},
        "layers": layers,
        "sign_convention": SIGN_CONVENTION,
        "fit_diagnostics_statement": DIAGNOSTICS_STATEMENT,
        "annotation_statement": ANNOTATION_STATEMENT,
        "component_annotations": [dict(row) for row in component_annotations],
        "limitations": list(LIMITATIONS) + (["synthetic_not_measurement"] if synthetic else []),
    }
    manifest["not_recorded"] = sorted(null_pointers(manifest))
    validate_basis_manifest(manifest)
    return manifest


def validate_basis_manifest(manifest: Any) -> dict[str, Any]:
    """Check a basis manifest's structure, vocabularies and fixed statements. Reads no file.

    A null field is allowed only when its JSON pointer is in ``not_recorded``, as in the run envelope. The
    string ``not_applicable`` is a recorded value. An unknown identity is not refused here; ``basis_identity``
    reports it and the caller decides.
    """
    require(isinstance(manifest, dict) and manifest.get("schema_version") == BASIS_SCHEMA, "schema_version",
            f"Expected {BASIS_SCHEMA}")
    require_structure(manifest, "ica_basis_manifest", "basis_manifest")
    require(text(manifest["basis_id"]), "basis_manifest", "basis_id is required")
    nulls, listed = set(null_pointers({k: v for k, v in manifest.items() if k != "not_recorded"})), set(
        manifest["not_recorded"])
    require(nulls == listed, "silent_missing_provenance",
            f"null fields and not_recorded disagree: unlisted {sorted(nulls - listed)}, stale "
            f"{sorted(listed - nulls)}")
    require(manifest["sign_convention"] == SIGN_CONVENTION, "sign_convention",
            f"sign_convention must read {SIGN_CONVENTION!r}")
    require(manifest["fit_diagnostics_statement"] == DIAGNOSTICS_STATEMENT, "basis_manifest",
            "fit_diagnostics_statement must be the fixed statement about a finished iteration budget")
    require(manifest["annotation_statement"] == ANNOTATION_STATEMENT, "basis_manifest",
            "annotation_statement must be the fixed statement that labels are hypotheses")
    wanted = set(LIMITATIONS) | ({SYNTHETIC_LIMITATION} if manifest["synthetic"] else set())
    require(wanted <= set(manifest["limitations"]), "basis_manifest",
            f"limitations must include {sorted(wanted - set(manifest['limitations']))}")
    preprocessing = manifest["preprocessing"]
    require(preprocessing["mode"] in PREPROCESSING_MODES and text(preprocessing["read_from"])
            and preprocessing["read_from"].startswith(ARTIFACT_MANIFEST), "preprocessing_mismatch",
            f"preprocessing.mode must be one of {list(PREPROCESSING_MODES)} and read_from must point into "
            f"{ARTIFACT_MANIFEST}")
    capture = manifest["capture"]
    require(integer(capture["layer_index_base"]) and capture["layer_index_base"] == 0, "layer_metadata",
            "capture.layer_index_base must be 0")
    require(capture["layers"] == sorted(int(key) for key in manifest["layers"]) and bool(capture["layers"])
            and all(integer(layer) for layer in capture["layers"]), "layer_metadata",
            "capture.layers must list the zero-based layers that the layers object holds")
    require(manifest["fit"]["split"] == "discovery", "split_leakage",
            f"the basis must be fit on the discovery split; the manifest says {manifest['fit']['split']!r}")
    for stage in STAGES:
        block = manifest[stage]
        require(all(text(x) for x in block["family_ids"]) and all(text(x) for x in block["corpus_ids"]),
                "basis_manifest", f"{stage}.family_ids and {stage}.corpus_ids must be lists of ids")
    hashes = manifest["fit"]["document_token_sha256"]
    require(hashes is None or all(bool(HEX64.fullmatch(str(x))) for x in hashes), "basis_manifest",
            "fit.document_token_sha256 must be a list of SHA-256 values or null")
    files = manifest["artifact"]["files"]
    paths = [entry["path"] for entry in files]
    require(len(set(paths)) == len(paths) and ARTIFACT_MANIFEST in paths, "artifact_hash",
            f"artifact.files must list each file once, including {ARTIFACT_MANIFEST}")
    for entry in files:
        relative = Path(entry["path"])
        require(not relative.is_absolute() and ".." not in relative.parts and bool(
            HEX64.fullmatch(entry["sha256"])) and integer(entry["bytes"]), "artifact_hash",
            f"artifact file {entry['path']!r} needs a relative path, a SHA-256 and a byte count")
    root = Path(manifest["artifact"]["root"])
    require(not root.is_absolute() and ".." not in root.parts, "artifact_hash",
            "artifact.root must be a relative path beside the manifest")
    listed_hashes = {entry["path"]: entry["sha256"] for entry in files}
    for key, layer in manifest["layers"].items():
        require(listed_hashes.get(layer["file"]) == layer["sha256"], "artifact_hash",
                f"layer {key}: {layer['file']!r} is not in artifact.files with the same SHA-256")
        require(integer(layer["n_components"], 1), "dimension_mismatch", f"layer {key}: n_components")
    for number, row in enumerate(manifest["component_annotations"]):
        where = f"component_annotations[{number}]"
        require(row.get("status") == "hypothesis", "annotation_status",
                f"{where}: status must be 'hypothesis'; a label or vocabulary readout is never a verified concept")
        require(text(row.get("source")) and str(row.get("layer")) in manifest["layers"] and integer(
            row.get("component")), "annotation_status", f"{where}: source, a basis layer and a component are needed")
        require(row["component"] < manifest["layers"][str(row["layer"])]["n_components"], "annotation_status",
                f"{where}: component {row['component']} is outside the layer's components")
        require(text(row.get("label")) or isinstance(row.get("vocabulary_readout"), dict), "annotation_status",
                f"{where}: an annotation carries a label or a vocabulary_readout")
        readout = row.get("vocabulary_readout")
        require(readout is None or (text(readout.get("source")) and text(readout.get("method"))),
                "annotation_status", f"{where}: a vocabulary readout names its method and source")
    return manifest


# ------------------------------------------------------------------------------------------- loaded basis

@dataclass(frozen=True)
class BasisLayer:
    """The saved tensors of one layer, as float64 copies of the stored float32 values."""

    layer: int
    n_components: int
    center: np.ndarray
    reading_matrix: np.ndarray
    writing_matrix: np.ndarray
    preprocessing_center: np.ndarray | None


@dataclass(frozen=True)
class Basis:
    """A verified basis: manifest, artifact directory, saved preprocessing and per-layer tensors."""

    manifest: dict[str, Any]
    manifest_sha256: str
    root: Path
    preprocessing: dict[str, Any]
    layers: dict[int, BasisLayer]
    saved_model: dict[str, Any]     # the model block of the artifact's own icalens.json

    @property
    def mode(self) -> str:
        return self.preprocessing["mode"]

    @property
    def hidden_size(self) -> int:
        return self.manifest["model"]["hidden_size"]

    @property
    def identity(self) -> dict[str, Any]:
        return basis_identity(self.manifest, self.saved_model)


def check_manifest_against_artifact(manifest: Mapping[str, Any], saved: Mapping[str, Any]) -> None:
    """Compare what a basis manifest says about the model and the capture site with the saved ``icalens.json``.

    The manifest copies these values from the artifact (``build_basis_manifest``), so a difference means the
    manifest was edited afterwards. A manifest value that is null claims nothing and is not a contradiction; the
    identity is then unknown. Refusals: ``identity_mismatch`` when the model id, the model type or the revision
    differs from a value the artifact records; ``layer_metadata`` when the activation site or the layer-indexing
    label differs. A saved revision that is absent or ``"unknown"`` contradicts nothing here: ``basis_identity``
    then reports the identity as unknown, whatever the manifest states.
    """
    model, saved_model = manifest["model"], artifact_model(saved)
    for field, saved_key in (("hf_id", "repo_id"), ("type", "type")):
        require(model[field] is None or model[field] == saved_model.get(saved_key), "identity_mismatch",
                f"the basis manifest says model.{field} {model[field]!r}; the saved {ARTIFACT_MANIFEST} records "
                f"{saved_model.get(saved_key)!r}")
    saved_revision = saved_model.get("revision")
    require(model["revision"] is None or model["revision"] == saved_revision
            or saved_revision in PLACEHOLDER_REVISIONS, "identity_mismatch",
            f"the basis manifest says model.revision {model['revision']!r}; the saved {ARTIFACT_MANIFEST} records "
            f"{saved_revision!r}")
    capture = manifest["capture"]
    for field, saved_key in (("artifact_activation_site", "activation_site"),
                             ("artifact_layer_indexing", "layer_indexing")):
        require(capture[field] == saved.get(saved_key), "layer_metadata",
                f"the basis manifest says capture.{field} {capture[field]!r}; the saved {ARTIFACT_MANIFEST} "
                f"records {saved.get(saved_key)!r}")


def load_basis(manifest_path: Path | str) -> Basis:
    """Read a basis manifest, verify every listed file and load the tensors.

    Refuses ``artifact_hash`` when a listed file is missing or its SHA-256 differs, ``preprocessing_mismatch``
    when the manifest's mode is not the mode the saved artifact records (or a ``preprocessing_center`` tensor is
    present or absent against the mode), ``identity_mismatch`` or ``layer_metadata`` when the manifest
    contradicts the saved artifact on the model or the capture site (``check_manifest_against_artifact``),
    ``dimension_mismatch`` for a wrong tensor shape and ``non_finite`` for a NaN or infinite tensor value.
    """
    path = Path(manifest_path).resolve()
    require(path.is_file(), "artifact_hash", f"no basis manifest at {path}")
    manifest = validate_basis_manifest(read_json(path))
    root = (path.parent / manifest["artifact"]["root"]).resolve()
    for entry in manifest["artifact"]["files"]:
        file = root / entry["path"]
        require(file.is_file(), "artifact_hash", f"artifact file {entry['path']} is missing from {root}")
        actual = sha256_file(file)
        require(actual == entry["sha256"], "artifact_hash",
                f"artifact file {entry['path']} has SHA-256 {actual}; the manifest records {entry['sha256']}")
    saved = read_json(root / ARTIFACT_MANIFEST)
    require(isinstance(saved, dict) and isinstance(saved.get("layers"), dict), "artifact_format",
            f"{ARTIFACT_MANIFEST} is not an ICA Lens manifest")
    check_manifest_against_artifact(manifest, saved)
    preprocessing = artifact_preprocessing(saved)
    declared = manifest["preprocessing"]
    require(declared["mode"] == preprocessing["mode"], "preprocessing_mismatch",
            f"the manifest says preprocessing {declared['mode']!r}; the saved artifact records "
            f"{preprocessing['mode']!r} ({preprocessing['read_from']})")
    require(declared["norm_eps"] == preprocessing["norm_eps"] and declared["row_normalization"]
            == preprocessing["row_normalization"], "preprocessing_mismatch",
            "the manifest's norm_eps or row_normalization differs from the saved artifact")
    hidden = manifest["model"]["hidden_size"]
    require(integer(hidden, 1) and saved.get("hidden_size") == hidden, "dimension_mismatch",
            f"hidden_size: manifest {hidden!r}, saved artifact {saved.get('hidden_size')!r}")
    layers: dict[int, BasisLayer] = {}
    for key, entry in manifest["layers"].items():
        saved_entry = saved["layers"].get(key)
        require(isinstance(saved_entry, dict) and saved_entry.get("file") == entry["file"]
                and saved_entry.get("n_components") == entry["n_components"], "dimension_mismatch",
                f"layer {key}: file or n_components differs between the manifest and {ARTIFACT_MANIFEST}")
        tensors = read_safetensors(root / entry["file"])
        k = entry["n_components"]
        wanted = {"center": (hidden,), "reading_matrix": (k, hidden), "writing_matrix": (hidden, k)}
        centered = preprocessing["mode"] == "geometric-median-l2"
        require(("preprocessing_center" in tensors) == centered, "preprocessing_mismatch",
                f"layer {key}: mode {preprocessing['mode']!r} and the presence of a preprocessing_center tensor "
                "disagree")
        if centered:
            wanted["preprocessing_center"] = (hidden,)
        loaded = {}
        for name, shape in wanted.items():
            require(name in tensors and tensors[name].shape == shape and tensors[name].dtype.kind == "f",
                    "dimension_mismatch",
                    f"layer {key}: tensor {name!r} must be floating point with shape {shape}; found "
                    f"{tensors[name].shape if name in tensors else 'no tensor'}")
            require(bool(np.isfinite(tensors[name]).all()), "non_finite",
                    f"layer {key}: tensor {name!r} holds NaN or infinity")
            loaded[name] = tensors[name].astype(np.float64)
        layers[int(key)] = BasisLayer(layer=int(key), n_components=k, center=loaded["center"],
                                      reading_matrix=loaded["reading_matrix"],
                                      writing_matrix=loaded["writing_matrix"],
                                      preprocessing_center=loaded.get("preprocessing_center"))
    return Basis(manifest=manifest, manifest_sha256=sha256_file(path), root=root, preprocessing=preprocessing,
                 layers=layers, saved_model=dict(artifact_model(saved)))


# ----------------------------------------------------------------------------------------- execution paths

def icalens_status() -> dict[str, Any]:
    """Whether the reference implementation imports here, with its version or the import error."""
    try:
        module = importlib.import_module("icalens")
        torch = importlib.import_module("torch")
    except Exception as exc:  # ImportError, or an error raised while a dependency initializes
        return {"importable": False, "version": None, "torch_version": None,
                "import_error": f"{type(exc).__name__}: {exc}"}
    return {"importable": True, "version": getattr(module, "__version__", None),
            "torch_version": getattr(torch, "__version__", None), "import_error": None}


def preprocess(layer: BasisLayer, mode: str, norm_eps: float, activations: np.ndarray) -> np.ndarray:
    """``preprocess(x)`` of the saved artifact, in float64. Mode ``none`` returns the input values."""
    work = np.asarray(activations, dtype=np.float64)
    if layer.preprocessing_center is not None:
        work = work - layer.preprocessing_center
    if mode != "none":
        work = work / np.maximum(np.linalg.norm(work, axis=-1, keepdims=True), norm_eps)
    return work


def _numpy_path(basis: Basis, layer: BasisLayer, activations: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x_pre = preprocess(layer, basis.mode, basis.preprocessing["norm_eps"], activations)
    scores = (x_pre - layer.center) @ layer.reading_matrix.T
    return scores, scores @ layer.writing_matrix.T + layer.center


def _icalens_path(basis: Basis, layer: BasisLayer, activations: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    icalens = importlib.import_module("icalens")
    lens = icalens.ICALens.from_pretrained(basis.root)
    require(lens.icalens_preprocessing == basis.mode, "preprocessing_mismatch",
            f"icalens loaded the artifact with preprocessing {lens.icalens_preprocessing!r}; the manifest says "
            f"{basis.mode!r}")
    scores = np.asarray(lens.transform(activations, layer=layer.layer), dtype=np.float64)
    return scores, np.asarray(lens.inverse_transform(scores, layer=layer.layer), dtype=np.float64)


def _cosines(a: np.ndarray, b: np.ndarray) -> list[float | None]:
    out: list[float | None] = []
    for left, right in zip(a, b):
        norms = float(np.linalg.norm(left)) * float(np.linalg.norm(right))
        out.append(float(left @ right) / norms if norms > 0 else None)
    return out


def apply_basis(basis: Basis, activations: np.ndarray, *, layer: int, path: str = "auto") -> dict[str, Any]:
    """Scores, squared-coordinate shares and reconstruction error of ``activations`` under one layer of ``basis``.

    ``activations`` is ``[rows, hidden_size]``; it is converted to float64, which is exact for float16, float32
    and bfloat16 inputs. ``path`` is ``"auto"`` (``icalens`` when it imports, else numpy), ``"icalens"`` or
    ``"numpy"``. When ``icalens`` runs, the numpy path runs too and the two must agree within
    ``PATH_TOLERANCE`` relative to the largest absolute score (at least 1), else ``path_disagreement``.

    Returned arrays are float64: ``scores`` ``[rows, k]``; ``energy_share`` ``[rows, k]`` with NaN in a row whose
    scores are all zero (the share is undefined there, and ``energy_status`` says so; ``icalens`` returns zeros
    for such a row); ``l2_error``, ``relative_l2_error`` and ``cosine`` per row, between ``preprocess(x)`` and
    the reconstruction, with NaN where a norm is zero.
    """
    require(path in ("auto",) + EXECUTION_PATHS, "execution_path", f"path must be auto, icalens or numpy; got {path!r}")
    require(layer in basis.layers, "dimension_mismatch",
            f"the basis has no layer {layer}; it holds {sorted(basis.layers)}")
    tensors = basis.layers[layer]
    values = np.asarray(activations)
    require(values.ndim == 2 and values.shape[1] == basis.hidden_size and values.shape[0] >= 1,
            "dimension_mismatch",
            f"activations must be [rows, {basis.hidden_size}]; got shape {tuple(values.shape)}")
    require(values.dtype.kind == "f" and bool(np.isfinite(values).all()), "non_finite",
            "activations must be floating point and finite")
    values = values.astype(np.float64)
    status = icalens_status()
    require(path != "icalens" or status["importable"], "reference_unavailable",
            f"icalens is not importable here: {status['import_error']}")
    used = "icalens" if path == "icalens" or (path == "auto" and status["importable"]) else "numpy"
    numpy_scores, numpy_recon = _numpy_path(basis, tensors, values)
    cross_check = None
    if used == "icalens":
        scores, recon = _icalens_path(basis, tensors, values)
        require(scores.shape == numpy_scores.shape and recon.shape == numpy_recon.shape, "path_disagreement",
                "the two execution paths returned different shapes")
        scale = max(1.0, float(np.abs(numpy_scores).max()))
        score_gap = float(np.abs(scores - numpy_scores).max())
        recon_gap = float(np.abs(recon - numpy_recon).max())
        cosines = [c for c in _cosines(scores, numpy_scores) if c is not None]
        cross_check = {"other_path": "numpy", "max_abs_score_difference": score_gap,
                       "max_abs_reconstruction_difference": recon_gap,
                       "min_score_cosine": min(cosines) if cosines else None,
                       "tolerance": PATH_TOLERANCE, "tolerance_scale": scale,
                       "scope": "arithmetic on the same saved matrices and the same activations; not model parity"}
        require(score_gap <= PATH_TOLERANCE * scale and recon_gap <= PATH_TOLERANCE * max(
            1.0, float(np.abs(numpy_recon).max())), "path_disagreement",
            f"icalens and the numpy path differ by {score_gap:.3e} in scores and {recon_gap:.3e} in "
            f"reconstruction; the tolerance is {PATH_TOLERANCE:.0e} relative")
    else:
        scores, recon = numpy_scores, numpy_recon
    require(bool(np.isfinite(scores).all()) and bool(np.isfinite(recon).all()), "non_finite",
            "the basis produced a NaN or infinite score or reconstruction")
    x_pre = preprocess(tensors, basis.mode, basis.preprocessing["norm_eps"], values)
    squared = scores ** 2
    totals = squared.sum(axis=1)
    energy = np.full_like(scores, np.nan)
    positive = totals > 0
    energy[positive] = squared[positive] / totals[positive, None]
    error = np.linalg.norm(x_pre - recon, axis=1)
    norms = np.linalg.norm(x_pre, axis=1)
    relative = np.full_like(error, np.nan)
    relative[norms > 0] = error[norms > 0] / norms[norms > 0]
    cosine = np.array([np.nan if c is None else c for c in _cosines(x_pre, recon)], dtype=np.float64)
    return {
        "scores": scores, "energy_share": energy, "total_squared": totals,
        "energy_status": ["computed" if ok else "not_computed_zero_energy" for ok in positive.tolist()],
        "l2_error": error, "relative_l2_error": relative, "cosine": cosine, "preprocessed_l2_norm": norms,
        "execution_path": {"used": used, "requested": path, "icalens_importable": status["importable"],
                           "icalens_version": status["version"] if used == "icalens" else None,
                           "torch_version": status["torch_version"] if used == "icalens" else None,
                           "icalens_import_error": status["import_error"], "compute_dtype": "float64",
                           "cross_check": cross_check},
    }


# --------------------------------------------------------------------------------------- protocol checks

def intervention_request(method: Mapping[str, Any]) -> list[str]:
    """Keys in a method block (or its basis block) that ask for an intervention."""
    basis = method.get("basis") if isinstance(method.get("basis"), dict) else {}
    return sorted({key for key in INTERVENTION_KEYS if key in method or key in basis})


def refuse_intervention(request: Any = None) -> None:
    """Every intervention request is refused. Clamping and steering are a separately specified experiment."""
    raise Refusal("unsupported_operation", INTERVENTION_REASON)


def stage_names(manifest: Mapping[str, Any], stage: str) -> set[str]:
    """Every family id and corpus id a stage of the basis manifest names, ``fit.corpus_id`` included."""
    block = manifest[stage]
    named = set(block["family_ids"]) | set(block["corpus_ids"])
    if stage == "fit" and text(block.get("corpus_id")):
        named.add(block["corpus_id"])
    return named


def check_split_leakage(manifest: Mapping[str, Any], protocol: Mapping[str, Any], *,
                        fit_dataset: ActivationDataset | None = None,
                        scoring_dataset: ActivationDataset | None = None) -> dict[str, Any]:
    """Refuse ``split_leakage`` when fitting, profiling or selection touched a validation or fresh-test family.

    Checked against the protocol: the family ids and corpus ids each stage lists, with ``fit.corpus_id`` among
    the fit stage's ids; the fit corpus's document token hashes, when the manifest lists them; the fit dataset's
    own row map, when that dataset is supplied (split, family id, corpus id and token hash of every document,
    and the dataset-level corpus id); and whether the basis was fit on the dataset that is being scored while it
    holds held-out families. A supplied fit dataset is also verified against its recorded file hashes.

    Returns which of these checks ran, one word per check. A check that had nothing to compare says so and is
    never reported as ``checked``: a stage that names no id is ``no_ids_listed``, and a fit dataset with a
    document that carries no token hash is ``checked_without_token_hashes``.
    """
    held_out = {f["family_id"]: f["split"] for f in protocol["case_families"] if f["split"] != "discovery"}
    require(manifest["fit"]["split"] == "discovery", "split_leakage",
            f"the basis fit split is {manifest['fit']['split']!r}, not 'discovery'")
    report: dict[str, Any] = {}
    for stage in STAGES:
        named = stage_names(manifest, stage)
        leaked = sorted(named & set(held_out))
        require(not leaked, "split_leakage",
                f"the basis {stage} stage names held-out families {[(f, held_out[f]) for f in leaked]}")
        report[f"{stage}_stage_ids"] = "checked" if named else "no_ids_listed"
    held_tokens = {entry["token_sha256"]: f"{f['family_id']}:{name}" for f in protocol["case_families"]
                   if f["split"] != "discovery" for name, entry in f["variants"].items()}
    report.update({"document_token_hashes": "not_listed_in_manifest",
                   "fit_dataset_row_map": "fit_dataset_not_supplied",
                   "fit_dataset_file_pins": "fit_dataset_not_supplied",
                   "scoring_dataset_is_fit_dataset": "not_checked"})
    listed = manifest["fit"]["document_token_sha256"]
    if listed is not None:
        leaked = sorted(held_tokens[h] for h in set(listed) & set(held_tokens))
        require(not leaked, "split_leakage", f"fit corpus documents have the token ids of held-out variants {leaked}")
        report["document_token_hashes"] = "checked"
    fit_sha = manifest["fit"]["activation_manifest_sha256"]
    if fit_dataset is not None:
        require(fit_sha is None or fit_dataset.manifest_sha256 == fit_sha, "split_leakage",
                "the supplied fit dataset is not the one the basis manifest names by SHA-256")
        report["fit_dataset_file_pins"] = fit_dataset.verify_files()["file_pins"]
        block = fit_dataset.row_map or {}
        documents = block.get("documents")
        require(documents is None or (isinstance(documents, list) and all(isinstance(d, dict) for d in documents)),
                "row_alignment", "the fit dataset's row map must list its documents as objects")
        corpus = block.get("corpus_id")
        require(not (isinstance(corpus, str) and corpus in held_out), "split_leakage",
                f"the fit dataset names corpus {corpus!r}, which is the id of a held-out family")
        without_hash = 0
        for document in documents or []:
            where = f"fit dataset document {document.get('document_index')}"
            family, corpus, token_hash = (document.get(key) for key in ("family_id", "corpus_id", "token_sha256"))
            require(document.get("split") == "discovery", "split_leakage",
                    f"{where} is in split {document.get('split')!r}")
            require(not (isinstance(family, str) and family in held_out), "split_leakage",
                    f"{where} belongs to held-out family {family!r}")
            require(not (isinstance(corpus, str) and corpus in held_out), "split_leakage",
                    f"{where} names corpus {corpus!r}, which is the id of a held-out family")
            if not text(token_hash):
                without_hash += 1
                continue
            require(token_hash not in held_tokens, "split_leakage",
                    f"{where} has the token ids of held-out variant {held_tokens.get(token_hash)}")
        report["fit_dataset_row_map"] = ("fit_dataset_has_no_row_map" if not documents
                                         else "checked_without_token_hashes" if without_hash else "checked")
    if scoring_dataset is not None and fit_sha is not None:
        documents = (scoring_dataset.row_map or {}).get("documents", [])
        held = sorted({d.get("family_id") for d in documents if d.get("split") != "discovery"} - {None})
        require(scoring_dataset.manifest_sha256 != fit_sha or not held, "split_leakage",
                f"the basis was fit on the dataset being scored, which holds held-out families {held}")
        report["scoring_dataset_is_fit_dataset"] = "checked"
    return report


def _check_task_against_basis(task: Mapping[str, Any], basis: Basis, dataset: ActivationDataset) -> None:
    spec = task["spec"]
    method, model = spec["method"], spec["model"]
    declared = method["basis"]
    require(declared["manifest_sha256"] == basis.manifest_sha256, "basis_mismatch",
            f"the protocol names basis {declared['manifest_sha256'][:12]}; the manifest on disk is "
            f"{basis.manifest_sha256[:12]}")
    require(declared["preprocessing"] == basis.mode, "preprocessing_mismatch",
            f"the protocol says preprocessing {declared['preprocessing']!r}; the saved artifact records "
            f"{basis.mode!r}")
    require(declared["fit_split"] == basis.manifest["fit"]["split"], "split_leakage",
            f"the protocol says fit_split {declared['fit_split']!r}; the manifest says "
            f"{basis.manifest['fit']['split']!r}")
    capture = basis.manifest["capture"]
    require(method["capture_site"] == capture["site"] and method["layer_index_base"] == capture["layer_index_base"],
            "layer_metadata", f"capture site or layer index base differs: protocol "
            f"({method['capture_site']!r}, {method['layer_index_base']}), basis ({capture['site']!r}, "
            f"{capture['layer_index_base']})")
    # The dataset's own record of where its rows were captured must be the site the basis was fitted at. Same
    # layer number, width and model at another site are not the same activations.
    recorded = (capture["artifact_activation_site"], capture["artifact_layer_indexing"])
    captured = (dataset.activation_site, dataset.layer_indexing)
    require(all(text(value) for value in recorded) and captured == recorded, "layer_metadata",
            f"the activation dataset records activation_site {captured[0]!r} and layer_indexing {captured[1]!r}; "
            f"the basis artifact records {recorded[0]!r} and {recorded[1]!r}. Both must be recorded and equal")
    missing = sorted(set(method["layers"]) - set(basis.layers))
    require(not missing, "dimension_mismatch", f"the basis has no layers {missing}; it holds {sorted(basis.layers)}")
    missing = sorted(set(method["layers"]) - set(dataset.layers))
    require(not missing, "dimension_mismatch",
            f"the activation dataset has no layers {missing}; it holds {list(dataset.layers)}")
    require(basis.hidden_size == dataset.hidden_size == model["hidden_size"], "dimension_mismatch",
            f"hidden_size: basis {basis.hidden_size}, dataset {dataset.hidden_size}, protocol {model['hidden_size']}")
    for name, identity in (("basis manifest", basis.identity), ("activation dataset", dataset.identity)):
        require(identity["status"] == "recorded", "unknown_identity",
                f"{name}: {identity['unknown_fields']} not recorded as exact values; parity is not established "
                "and no score is produced")
        require((identity["model_id"], identity["model_revision"], identity["tokenizer_id"],
                 identity["tokenizer_revision"]) == (model["hf_id"], model["revision"], model["tokenizer_id"],
                                                     model["tokenizer_revision"]), "identity_mismatch",
                f"{name}: model or tokenizer identity differs from the protocol's")


# ------------------------------------------------------------------------------------------------ scoring

def _maybe(value: float) -> float | None:
    return None if math.isnan(value) else value


def score_task(task: Mapping[str, Any], protocol: Mapping[str, Any], *, basis: Basis, dataset: ActivationDataset,
               fit_dataset: ActivationDataset | None = None, path: str = "auto") -> dict[str, Any]:
    """The ``ica_scores/1`` payload for one planned task (one family, one variant) under ``basis``.

    The caller passes a loaded basis and an opened dataset. This function validates the dataset in full against
    the protocol (completion, sizes, finiteness, duplicates, row-by-row token ids), checks identity,
    preprocessing, layers and split leakage, then applies the one basis the protocol names. It raises ``Refusal``
    and never returns a partial payload.
    """
    spec = task["spec"]
    method = spec["method"]
    if intervention_request(method):
        refuse_intervention()
    require(basis.manifest["synthetic"] is bool(protocol["synthetic"]), "synthetic_label",
            f"the basis manifest says synthetic {basis.manifest['synthetic']!r}; the protocol says "
            f"{protocol['synthetic']!r}. A synthetic basis is never scored under a protocol that is not synthetic, "
            "nor the reverse")
    _check_task_against_basis(task, basis, dataset)
    leakage = check_split_leakage(basis.manifest, protocol, fit_dataset=fit_dataset, scoring_dataset=dataset)
    report = validate_activation_dataset(dataset, protocol=protocol)
    # The rows scored below are selected from the sample tensors and the layer bytes read here, and the payload
    # records the SHA-256 of exactly those bytes.
    samples, samples_sha256 = dataset.samples_with_hash()
    rows = variant_rows(dataset, protocol, spec["family_id"], spec["variant"], row_index(dataset, samples))
    if method.get("positions", "all") == "last":
        rows = rows[-1:]
    # A dataset captured at the last position only cannot answer a method that asks for every position.
    n_tokens = len(next(f for f in protocol["case_families"] if f["family_id"] == spec["family_id"])[
        "variants"][spec["variant"]]["token_ids"])
    wanted = [n_tokens - 1] if method.get("positions", "all") == "last" else list(range(n_tokens))
    require([row["position"] for row in rows] == wanted, "row_alignment",
            f"the method asks for positions {wanted}; the dataset holds rows for "
            f"{[row['position'] for row in rows]} of {spec['family_id']}:{spec['variant']}")
    selected = [row["row"] for row in rows]
    scores_out, energy_rows, reconstruction_rows = [], [], []
    layer_sha256: dict[str, str] = {}
    execution: dict[str, Any] | None = None
    for layer in sorted(method["layers"]):
        values, layer_sha256[str(layer)] = dataset.layer_with_hash(layer)
        result = apply_basis(basis, values[selected], layer=layer, path=path)
        require(execution is None or execution["used"] == result["execution_path"]["used"], "path_disagreement",
                "layers of one task were scored by different execution paths")
        if execution is None:
            execution = dict(result["execution_path"])
            execution["cross_check_by_layer"] = {}
        execution["cross_check_by_layer"][str(layer)] = result["execution_path"]["cross_check"]
        for number, row in enumerate(rows):
            energy_rows.append({"layer": layer, "position": row["position"],
                                "status": result["energy_status"][number],
                                "total_squared": float(result["total_squared"][number])})
            reconstruction_rows.append({
                "layer": layer, "position": row["position"],
                "l2_error": float(result["l2_error"][number]),
                "relative_l2_error": _maybe(float(result["relative_l2_error"][number])),
                "cosine": _maybe(float(result["cosine"][number])),
                "preprocessed_l2_norm": float(result["preprocessed_l2_norm"][number])})
            for component in range(basis.layers[layer].n_components):
                scores_out.append({"layer": layer, "position": row["position"], "component": component,
                                   "score": float(result["scores"][number, component]),
                                   "energy_share": _maybe(float(result["energy_share"][number, component]))})
    assert execution is not None
    execution.pop("cross_check")
    manifest = basis.manifest
    layers = sorted(method["layers"])
    annotations = [dict(row) for row in manifest["component_annotations"] if row["layer"] in layers]
    payload = {
        "kind": PAYLOAD_KIND, "synthetic": bool(protocol["synthetic"]),
        "family_id": spec["family_id"], "variant": spec["variant"], "input": dict(spec["input"]),
        "model": {"hf_id": spec["model"]["hf_id"], "revision": spec["model"]["revision"]},
        "tokenizer": {"id": spec["model"]["tokenizer_id"], "revision": spec["model"]["tokenizer_revision"]},
        "identity": {"basis": basis.identity["status"], "activation_dataset": dataset.identity["status"],
                     "parity": PARITY_NOTE},
        "basis": {
            "manifest_sha256": basis.manifest_sha256, "basis_id": manifest["basis_id"],
            "synthetic": manifest["synthetic"],
            "preprocessing_mode": basis.mode, "preprocessing_read_from": basis.preprocessing["read_from"],
            "norm_eps": basis.preprocessing["norm_eps"],
            "fit_split": manifest["fit"]["split"], "fit_corpus_id": manifest["fit"]["corpus_id"],
            "seed": manifest["seed"],
            "n_components": {str(layer): basis.layers[layer].n_components for layer in layers},
            "artifact_files": [{"path": e["path"], "sha256": e["sha256"]} for e in manifest["artifact"]["files"]],
            "sign_convention": manifest["sign_convention"],
            "fit_diagnostics_statement": manifest["fit_diagnostics_statement"],
        },
        "capture": {
            "site": method["capture_site"], "layer_index_base": method["layer_index_base"], "layers": layers,
            "positions": method.get("positions", "all"),
            # As the dataset manifest records them; _check_task_against_basis required them to equal the
            # basis artifact's values.
            "activation_site": dataset.activation_site, "layer_indexing": dataset.layer_indexing,
            # file_pins says whether the dataset manifest records hashes of its files (then they were
            # verified) or records none. The two hash fields are of the bytes this task read, in both cases.
            "activation_dataset": {"manifest_sha256": dataset.manifest_sha256, "dtype": dataset.dtype,
                                   "sample_count": dataset.sample_count, "file_pins": report["file_pins"],
                                   "samples_sha256": samples_sha256, "layer_sha256": layer_sha256},
            "precision": {"basis_fit_input_dtype": manifest["capture"]["precision"],
                          "scored_activation_dtype": dataset.dtype,
                          "match": manifest["capture"]["precision"] == dataset.dtype,
                          "model_load_precision": manifest["capture"]["model_load_precision"]
                          or "not_recorded"},
        },
        "split_leakage_checks": leakage,
        "execution_path": execution,
        "rows": [{"position": row["position"], "token_id": row["token_id"], "document_index": row["document_index"],
                  "dataset_row": row["row"]} for row in rows],
        "components_complete": True,
        "score_definition": SCORE_DEFINITION,
        "scores": scores_out,
        "energy_share": {"label": ENERGY_LABEL, "definition": ENERGY_DEFINITION, "rows": energy_rows},
        "reconstruction": {"space": "preprocessed", "definition": RECONSTRUCTION_DEFINITION,
                           "restore_norm": RESTORE_NORM, "rows": reconstruction_rows},
        "annotation_statement": ANNOTATION_STATEMENT,
        "component_annotations": annotations,
        "limitations": list(LIMITATIONS) + [x for x in manifest["limitations"] if x not in LIMITATIONS],
    }
    return payload


# ------------------------------------------------------------------------------------------- comparisons

def compare_pair(payload_a: Mapping[str, Any], payload_b: Mapping[str, Any]) -> dict[str, Any]:
    """Signed score differences (a minus b) per component for two variants scored under ONE basis.

    This is ``scripts.experiments.compare.ica_block``; it refuses ``basis_mismatch`` when the two payloads name
    different basis manifest hashes. No alignment record lifts that refusal: the two members of a pair are
    always scored under the same basis.
    """
    from scripts.experiments.compare import ica_block  # imported here: compare imports the run store

    return ica_block(payload_a, payload_b)


def validate_alignment(record: Any, *, basis_a: str, basis_b: str, layer: int) -> dict[int, tuple[int, int]]:
    """Check an alignment record and return ``{component_a: (component_b, sign)}``.

    An alignment record (``patientwords.ica-alignment/1``) states, for one layer of two named bases, which
    component of fit b corresponds to which component of fit a and with what sign, how that was decided
    (``method``) and where the evidence is (``source``). This module does not derive one.
    """
    require(isinstance(record, dict) and record.get("schema_version") == ALIGNMENT_SCHEMA, "sign_convention",
            f"an alignment record must be a {ALIGNMENT_SCHEMA} object")
    require(record.get("basis_a") == basis_a and record.get("basis_b") == basis_b and integer(record.get("layer"))
            and record["layer"] == layer, "sign_convention",
            "the alignment record names other bases or another layer than the ones compared")
    require(text(record.get("method")) and text(record.get("source")), "sign_convention",
            "an alignment record states its method and its source")
    pairs = record.get("pairs")
    require(isinstance(pairs, list) and bool(pairs) and all(
        isinstance(p, dict) and integer(p.get("component_a")) and integer(p.get("component_b"))
        and p.get("sign") in (1, -1) and type(p.get("sign")) is int for p in pairs), "sign_convention",
        "each alignment pair needs component_a, component_b and sign (+1 or -1)")
    require(len({p["component_a"] for p in pairs}) == len(pairs) and len({p["component_b"] for p in pairs})
            == len(pairs), "sign_convention", "a component may appear in one alignment pair only")
    return {p["component_a"]: (p["component_b"], p["sign"]) for p in pairs}


def compare_across_fits(block_a: Mapping[str, Any], block_b: Mapping[str, Any],
                        alignment: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compare one pair's signed score differences as read by two different fits.

    ``block_a`` and ``block_b`` are ``compare_pair`` results for the same family and comparison under two bases.
    Component indices and signs are local to a fit, so without an explicit alignment record this refuses
    ``sign_convention``. With one, each aligned component of fit b is mapped to its component of fit a and
    multiplied by the recorded sign. Components the record does not list are reported as unaligned; they are
    not compared and not treated as zero.
    """
    basis_a, basis_b = block_a["basis_manifest_sha256"], block_b["basis_manifest_sha256"]
    require(basis_a != basis_b or alignment is None, "sign_convention",
            "both blocks come from one basis; an alignment record applies to two different fits")
    layers_a = {row["layer"]: row for row in block_a["layers"]}
    layers_b = {row["layer"]: row for row in block_b["layers"]}
    require(set(layers_a) == set(layers_b), "sign_convention",
            f"components are not comparable across layers: fit a has layers {sorted(layers_a)}, fit b "
            f"{sorted(layers_b)}")
    if basis_a != basis_b:
        require(alignment is not None, "sign_convention",
                f"the two blocks come from different fits ({basis_a[:12]} and {basis_b[:12]}). Component indices "
                "and signs are not comparable across fits without an explicit alignment record")
        require(len(layers_a) == 1, "sign_convention", "an alignment record covers one layer; compare one layer")
    out_layers = []
    for layer in sorted(layers_a):
        diff_a = {c["component"]: c["difference_a_minus_b"] for c in layers_a[layer]["components"]}
        diff_b = {c["component"]: c["difference_a_minus_b"] for c in layers_b[layer]["components"]}
        mapping = ({component: (component, 1) for component in diff_a} if basis_a == basis_b else
                   validate_alignment(alignment, basis_a=basis_a, basis_b=basis_b, layer=layer))
        unknown = sorted(c for c in mapping if c not in diff_a) + sorted(
            c for c, _ in mapping.values() if c not in diff_b)
        require(not unknown, "sign_convention", f"the alignment record names components outside the bases: {unknown}")
        components = []
        for component_a in sorted(mapping):
            component_b, sign = mapping[component_a]
            a, b = diff_a[component_a], diff_b[component_b]
            mapped = None if b is None else sign * b
            components.append({
                "component_a": component_a, "component_b": component_b, "sign": sign,
                "difference_fit_a": a, "difference_fit_b_as_saved": b, "difference_fit_b_aligned": mapped,
                "aligned_difference_gap": None if a is None or mapped is None else a - mapped})
        out_layers.append({"layer": layer, "components": components,
                           "unaligned_components_a": sorted(set(diff_a) - set(mapping)),
                           "unaligned_components_b": sorted(set(diff_b) - {b for b, _ in mapping.values()})})
    return {"status": "computed", "basis_a": basis_a, "basis_b": basis_b,
            "alignment": "identity_same_basis" if basis_a == basis_b else {
                "method": alignment["method"], "source": alignment["source"]},
            "sign_convention": SIGN_CONVENTION, "layers": out_layers}


# ------------------------------------------------------------------------------------------------ adapter

class IcaAdapter:
    """Adapter for method ``ica_lens``. Offline fixtures only; no model, no fit, no intervention."""

    method_ids: tuple[str, ...] = (METHOD_ID,)
    payload_kinds: tuple[str, ...] = (PAYLOAD_KIND,)
    # The scoring arithmetic reads datasets through this module, so a change to it must stop reuse of an
    # earlier payload (the run store hashes these into environment.source_files_sha256).
    source_files: tuple[Path, ...] = (Path(__file__).resolve().parents[1] / "activation_dataset.py",)

    def capabilities(self) -> list[dict]:
        return [{
            "model": dict(FIXTURE_MODEL), "method": METHOD_ID, "backend": FIXTURE_BACKEND, "dtype": None,
            "artifact": None, "status": "runtime_verified_offline_fixture",
            "evidence": [{"source": "tests/test_experiments_ica.py", "date": "2026-11-10"}],
            "status_note": ("A hand-written toy basis applied to synthetic activations by "
                            "scripts/experiments/adapters/ica.py. Verified by the offline tests only. No fit and "
                            "no model run; it says nothing about any real model or any released basis."),
        }]

    @staticmethod
    def _paths(context: Mapping[str, Any]) -> tuple[Path, Path, Path]:
        root = Path(context["fixtures_dir"]) / FIXTURE_SUBDIR
        return root / BASIS_MANIFEST_FILE, root / PAIR_DATASET_DIR, root / FIT_DATASET_DIR

    @staticmethod
    def _saved_model(manifest_path: Path, manifest: Mapping[str, Any]) -> dict[str, Any] | None:
        """The model block of the artifact's ``icalens.json``, or None when it cannot be read here (execution
        then refuses with the named code)."""
        try:
            saved = read_json(manifest_path.parent / manifest["artifact"]["root"] / ARTIFACT_MANIFEST)
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return artifact_model(saved) if isinstance(saved, dict) else None

    def input_identity(self, task: dict, context: dict | None = None) -> str | None:
        """The run store's optional reuse hook (``scripts.experiments.adapters.input_identity``): one SHA-256.

        It is ``common.digest`` of ``input_identity_record(task, context)``. None, meaning "the inputs cannot be
        identified now", when the fixtures directory is not given, when the basis manifest or the pair dataset's
        manifest cannot be read, or when a file one of them names cannot be read. It never raises for an absent
        file and never executes the task.
        """
        record = self.input_identity_record(task, context)
        if record is None or record["basis"] is None or record["activation_dataset"] is None:
            return None
        basis, dataset = record["basis"], record["activation_dataset"]
        hashes = [basis["manifest_sha256"], dataset["manifest_sha256"], dataset["samples_sha256"],
                  *dataset["layer_sha256"].values()]
        hashes += [None] if basis["artifact_files"] is None else [e["sha256"] for e in basis["artifact_files"]]
        return None if any(value is None for value in hashes) else digest(record)

    def input_identity_record(self, task: dict, context: dict | None = None) -> dict | None:
        """The inputs outside the task spec that determine this task's payload, as a JSON-serializable dict.

        Holds the SHA-256 of the basis manifest and of every artifact file it lists, as they are on disk now;
        the SHA-256 of the pair dataset's manifest, of its samples file and of the layer files this task reads;
        the same for the fit dataset when the fixtures hold one (its row map and file pins enter the
        split-leakage report); the SHA-256 of this adapter's two source files; and the installed versions of
        the packages whose arithmetic the payload records. Files are hashed, never decoded: no array is loaded,
        no package is imported and nothing is written. A file that cannot be read is recorded as null, so two
        calls differ when a file appears, disappears or changes. ``context`` supplies ``fixtures_dir`` (and
        optionally ``ica_path``); without it only the source hashes and versions can be read. Returns None only
        when nothing at all can be read.
        """
        def file_hash(base: Path, relative: Any = "") -> str | None:
            """SHA-256 of ``base / relative``; None for a name that is not a relative path inside ``base`` and
            for a file that cannot be read."""
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
                return None
            try:
                return sha256_file(base / relative)
            except OSError:
                return None

        def json_or_none(path: Path) -> Any:
            try:
                return read_json(path)
            except (OSError, ValueError):
                return None

        def dataset_block(root: Path, layers: Iterable[Any] | None) -> dict[str, Any] | None:
            manifest = json_or_none(root / "activations.json")
            if not isinstance(manifest, dict):
                return None
            entries = manifest.get("layers") if isinstance(manifest.get("layers"), dict) else {}
            keys = sorted(entries) if layers is None else [str(layer) for layer in layers]
            files = {key: entries[key].get("file") if isinstance(entries.get(key), dict) else None for key in keys}
            samples = manifest.get("samples_file")
            return {"manifest_sha256": file_hash(root, "activations.json"),
                    "samples_sha256": file_hash(root, samples) if text(samples) else None,
                    "layer_sha256": {key: file_hash(root, name) if text(name) else None
                                     for key, name in files.items()}}

        here = Path(__file__).resolve()
        sources = {"scripts/experiments/adapters/ica.py": file_hash(here),
                   "scripts/experiments/activation_dataset.py": file_hash(here.parents[1] / "activation_dataset.py")}
        versions: dict[str, str | None] = {"numpy": np.__version__}
        for name in ("icalens", "torch"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        identity: dict[str, Any] = {
            "schema_version": INPUT_IDENTITY_SCHEMA, "adapter_source_sha256": sources,
            "execution": {"requested_path": (context or {}).get("ica_path", "auto"), "package_versions": versions},
            "basis": None, "activation_dataset": None, "fit_dataset": None}
        if context is not None and context.get("fixtures_dir") is not None:
            manifest_path, pair_dir, fit_dir = self._paths(context)
            manifest = json_or_none(manifest_path)
            if manifest_path.is_file():
                artifact = manifest.get("artifact") if isinstance(manifest, dict) else None
                listed = artifact.get("files") if isinstance(artifact, dict) else None
                root = artifact.get("root") if isinstance(artifact, dict) else None
                files = None
                if isinstance(listed, list) and text(root) and not Path(root).is_absolute() and ".." not in Path(
                        root).parts:
                    files = [{"path": entry.get("path"),
                              "sha256": file_hash(manifest_path.parent / root, entry.get("path"))
                              if text(entry.get("path")) else None}
                             for entry in listed if isinstance(entry, dict)]
                identity["basis"] = {"manifest_sha256": file_hash(manifest_path), "artifact_files": files}
            layers = task["spec"]["method"].get("layers")
            identity["activation_dataset"] = dataset_block(pair_dir, sorted(layers) if isinstance(layers, list)
                                                           else None)
            identity["fit_dataset"] = dataset_block(fit_dir, None)
        readable = any(sources.values()) or any(identity[key] for key in ("basis", "activation_dataset",
                                                                           "fit_dataset"))
        return identity if readable else None

    def preflight(self, task: dict, context: dict) -> tuple[str, str | None]:
        method = task["spec"]["method"]
        asked = intervention_request(method)
        if asked:
            return "unsupported", f"unsupported_operation: {asked} requested. {INTERVENTION_REASON}"
        manifest_path, pair_dir, _ = self._paths(context)
        if not manifest_path.is_file():
            return "unavailable", f"no basis manifest {FIXTURE_SUBDIR}/{BASIS_MANIFEST_FILE} in the fixtures"
        on_disk = sha256_file(manifest_path)
        if on_disk != method["basis"]["manifest_sha256"]:
            return "unavailable", (f"the basis the protocol names ({method['basis']['manifest_sha256'][:12]}) is "
                                   f"not in the fixtures; the manifest there is {on_disk[:12]}")
        try:
            manifest = read_json(manifest_path)
        except ValueError:
            return "ready", None  # execution refuses with the parse error
        if isinstance(manifest, dict):
            identity = basis_identity(manifest, self._saved_model(manifest_path, manifest))
            if identity["status"] != "recorded":
                return "unavailable", (f"unknown_identity: the basis manifest or its saved artifact does not "
                                       f"record {identity['unknown_fields']} as exact values; parity is not "
                                       "established")
        if not (pair_dir / "activations.json").is_file():
            return "unavailable", f"no activation dataset {FIXTURE_SUBDIR}/{PAIR_DATASET_DIR} in the fixtures"
        try:
            dataset = open_activation_dataset(pair_dir)
        except Refusal as exc:
            if exc.code == "incomplete":
                return "unavailable", f"incomplete: {exc}"
            return "ready", None  # execution refuses with the named code
        identity = dataset.identity
        if identity["status"] != "recorded":
            return "unavailable", (f"unknown_identity: the activation dataset does not record "
                                   f"{identity['unknown_fields']} as exact values; parity is not established")
        return "ready", None

    def _load(self, context: dict) -> tuple[Basis, ActivationDataset, ActivationDataset | None]:
        manifest_path, pair_dir, fit_dir = self._paths(context)
        cache = context.setdefault("_cache", {})
        key = ("ica", str(manifest_path))
        if key not in cache:
            fit_dataset = open_activation_dataset(fit_dir) if (fit_dir / "activations.json").is_file() else None
            cache[key] = (load_basis(manifest_path), open_activation_dataset(pair_dir), fit_dataset)
        return cache[key]

    def execute_fixture(self, task: dict, context: dict) -> dict:
        if intervention_request(task["spec"]["method"]):
            refuse_intervention()
        basis, dataset, fit_dataset = self._load(context)
        return score_task(task, context["protocol"], basis=basis, dataset=dataset, fit_dataset=fit_dataset,
                          path=context.get("ica_path", "auto"))

    def validate_payload(self, payload: dict, task: dict, context: dict) -> None:
        """Check a filed payload against its task. Reads no file.

        Beyond structure and the task's own identity: every fixed statement must equal this module's constant
        (``payload_labels``); ``limitations`` must include every entry of ``LIMITATIONS``, and
        ``synthetic_not_measurement`` for a synthetic payload; the basis's synthetic flag must equal the
        payload's; the fit split and the capture site must be the task's; the dataset's file hashes must be
        present; and every squared-coordinate share is recomputed from the row's scores
        (``energy_share_mismatch``), so a payload whose shares were edited is refused, not only one whose shares
        fail to sum to 1.
        """
        spec = task["spec"]
        method = spec["method"]
        require(isinstance(payload, dict) and payload.get("kind") == PAYLOAD_KIND, "payload_kind",
                f"expected {PAYLOAD_KIND}")
        require_structure(payload, "ica_scores", "payload_structure")
        require(payload["synthetic"] is bool(context["protocol"]["synthetic"]), "synthetic_label",
                "the payload's synthetic flag differs from the protocol's")
        require(payload["family_id"] == spec["family_id"] and payload["variant"] == spec["variant"]
                and payload["input"] == spec["input"], "row_alignment",
                "the payload's family, variant or input hashes differ from the planned task")
        require(payload["model"] == {"hf_id": spec["model"]["hf_id"], "revision": spec["model"]["revision"]}
                and payload["tokenizer"] == {"id": spec["model"]["tokenizer_id"],
                                             "revision": spec["model"]["tokenizer_revision"]},
                "identity_mismatch", "the payload was produced for another model or tokenizer")
        basis = payload["basis"]
        require(basis["manifest_sha256"] == method["basis"]["manifest_sha256"], "basis_mismatch",
                "the payload was scored under another basis than the one the protocol names")
        require(basis["preprocessing_mode"] == method["basis"]["preprocessing"], "preprocessing_mismatch",
                "the payload's preprocessing mode differs from the protocol's")
        require(basis["sign_convention"] == SIGN_CONVENTION and payload["energy_share"]["label"] == ENERGY_LABEL
                and payload["reconstruction"]["space"] == "preprocessed", "payload_labels",
                "the sign convention, the energy-share label or the reconstruction space was changed")
        fixed = {
            "identity.parity": (payload["identity"]["parity"], PARITY_NOTE),
            "basis.fit_diagnostics_statement": (basis["fit_diagnostics_statement"], DIAGNOSTICS_STATEMENT),
            "annotation_statement": (payload["annotation_statement"], ANNOTATION_STATEMENT),
            "score_definition": (payload["score_definition"], SCORE_DEFINITION),
            "energy_share.definition": (payload["energy_share"]["definition"], ENERGY_DEFINITION),
            "reconstruction.definition": (payload["reconstruction"]["definition"], RECONSTRUCTION_DEFINITION),
            "reconstruction.restore_norm": (payload["reconstruction"]["restore_norm"], RESTORE_NORM),
        }
        changed = sorted(name for name, (found, wanted) in fixed.items() if found != wanted)
        require(not changed, "payload_labels", f"fixed statements were changed: {changed}")
        require(payload["identity"]["basis"] == "recorded" and payload["identity"]["activation_dataset"]
                == "recorded", "unknown_identity", "a payload exists only for a recorded basis and dataset identity")
        wanted_limits = set(LIMITATIONS) | ({SYNTHETIC_LIMITATION} if payload["synthetic"] else set())
        require(wanted_limits <= set(payload["limitations"]), "payload_labels",
                f"limitations lack {sorted(wanted_limits - set(payload['limitations']))}")
        require(basis["synthetic"] is payload["synthetic"], "synthetic_label",
                "the basis's synthetic flag differs from the payload's")
        require(basis["fit_split"] == method["basis"]["fit_split"] == "discovery", "split_leakage",
                "the payload's fit split is not the protocol's discovery split")
        stage_words = {key: value for key, value in payload["split_leakage_checks"].items()
                       if key.endswith("_stage_ids")}
        require(set(stage_words) == {f"{stage}_stage_ids" for stage in STAGES}
                and set(stage_words.values()) <= set(LEAKAGE_STAGE_WORDS), "split_leakage",
                f"split_leakage_checks must say {list(LEAKAGE_STAGE_WORDS)} for each of the stages {list(STAGES)}")
        require(payload["execution_path"]["used"] in EXECUTION_PATHS, "execution_path",
                f"execution_path.used must be one of {list(EXECUTION_PATHS)}")
        require((payload["execution_path"]["used"] == "icalens") == text(
            payload["execution_path"]["icalens_version"]), "execution_path",
            "icalens_version is recorded exactly when the icalens path produced the payload")
        layers = sorted(method["layers"])
        capture = payload["capture"]
        require(capture["layers"] == layers and capture["positions"] == method.get("positions", "all"),
                "layer_metadata", "layers or positions differ from the task")
        require(capture["site"] == method["capture_site"] and capture["layer_index_base"]
                == method["layer_index_base"] and text(capture["activation_site"])
                and text(capture["layer_indexing"]), "layer_metadata",
                "the capture site or layer index base differs from the task, or the dataset's activation_site "
                "or layer_indexing is not recorded")
        dataset = capture["activation_dataset"]
        require(dataset["file_pins"] in (PINS_VERIFIED, PINS_NOT_RECORDED) and all(
            bool(HEX64.fullmatch(value)) for value in (dataset["manifest_sha256"], dataset["samples_sha256"],
                                                       *dataset["layer_sha256"].values()))
                and sorted(dataset["layer_sha256"]) == sorted(str(layer) for layer in layers), "artifact_hash",
                "the payload must name the dataset by its manifest SHA-256, the SHA-256 of the samples file and "
                "of each layer file that was read, and say whether the manifest pinned them")
        family = next(f for f in context["protocol"]["case_families"] if f["family_id"] == spec["family_id"])
        token_ids = family["variants"][spec["variant"]]["token_ids"]
        rows = payload["rows"]
        positions = [row["position"] for row in rows]
        wanted = [len(token_ids) - 1] if method.get("positions", "all") == "last" else list(range(len(token_ids)))
        require(positions == wanted, "row_alignment", f"positions {positions} are not the task's {wanted}")
        require(all(row["token_id"] == token_ids[row["position"]] for row in rows), "row_alignment",
                "a row's token id is not the protocol's token id at that position")
        expected = [(layer, position, component) for layer in layers for position in positions
                    for component in range(basis["n_components"][str(layer)])]
        got = [(row["layer"], row["position"], row["component"]) for row in payload["scores"]]
        require(got == expected and payload["components_complete"] is True, "dimension_mismatch",
                "scores must list every component of every layer and position once, in order")
        cells = [(layer, position) for layer in layers for position in positions]
        for name in ("energy_share", "reconstruction"):
            require([(row["layer"], row["position"]) for row in payload[name]["rows"]] == cells,
                    "dimension_mismatch", f"{name}.rows must list every layer and position once, in order")
        for row in payload["scores"]:
            require(type(row["score"]) is float and math.isfinite(row["score"]), "non_finite",
                    f"score at {row['layer']}/{row['position']}/{row['component']} is not a finite float")
            share = row["energy_share"]
            require(share is None or (type(share) is float and 0.0 <= share <= 1.0), "non_finite",
                    "an energy share must be null or a float in [0, 1]")
        energy = {(row["layer"], row["position"]): row for row in payload["energy_share"]["rows"]}
        for layer, position in cells:
            group = [row for row in payload["scores"] if row["layer"] == layer and row["position"] == position]
            shares = [row["energy_share"] for row in group]
            total = math.fsum(row["score"] ** 2 for row in group)
            where = f"layer {layer}, position {position}"
            recorded = energy[(layer, position)]
            if recorded["status"] == "computed":
                require(all(s is not None for s in shares) and abs(sum(shares) - 1.0) <= 1e-9,
                        "non_finite", f"energy shares at {where} do not sum to 1")
            else:
                require(recorded["status"] == "not_computed_zero_energy" and all(s is None for s in shares),
                        "non_finite", "a row without computed energy must carry null shares, never zeros")
            # Recomputed from the scores of the same row: status, total and every share.
            require((recorded["status"] == "computed") == (total > 0.0), "energy_share_mismatch",
                    f"{where}: status {recorded['status']!r} does not follow from the scores, whose squares sum "
                    f"to {total!r}")
            require(type(recorded["total_squared"]) is float and abs(recorded["total_squared"] - total)
                    <= SHARE_TOLERANCE * max(1.0, total), "energy_share_mismatch",
                    f"{where}: total_squared {recorded['total_squared']!r} is not the sum of the squared scores "
                    f"{total!r}")
            if total > 0.0:
                gaps = [abs(row["energy_share"] - row["score"] ** 2 / total) for row in group]
                require(max(gaps) <= SHARE_TOLERANCE, "energy_share_mismatch",
                        f"{where}: a share differs from score**2 / sum(score**2) by {max(gaps):.3e}")
        for row in payload["reconstruction"]["rows"]:
            where = f"layer {row['layer']}, position {row['position']}"
            error, norm, relative, cosine = (row[key] for key in ("l2_error", "preprocessed_l2_norm",
                                                                  "relative_l2_error", "cosine"))
            require(all(type(v) is float and math.isfinite(v) and v >= 0.0 for v in (error, norm)), "non_finite",
                    f"{where}: l2_error and preprocessed_l2_norm must be finite floats at or above zero")
            require((relative is None) == (norm == 0.0) and (relative is None or (
                type(relative) is float and abs(relative - error / norm) <= SHARE_TOLERANCE * max(1.0, error / norm))),
                "reconstruction_mismatch", f"{where}: relative_l2_error is not l2_error / preprocessed_l2_norm")
            require(cosine is None or (type(cosine) is float and abs(cosine) <= 1.0 + SHARE_TOLERANCE),
                    "reconstruction_mismatch", f"{where}: cosine must be null or a float in [-1, 1]")
        for row in payload["component_annotations"]:
            require(set(row) <= set(ANNOTATION_KEYS) and row.get("status") == "hypothesis"
                    and text(row.get("source")), "annotation_status",
                    f"a component annotation must be a hypothesis with its source and hold only "
                    f"{list(ANNOTATION_KEYS)}")
            require(integer(row.get("layer")) and row["layer"] in layers and integer(row.get("component"))
                    and row["component"] < basis["n_components"][str(row["layer"])], "annotation_status",
                    "a component annotation names a scored layer and one of its components")


ADAPTER = IcaAdapter()
