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
``incomplete``, ``unknown_identity``, ``identity_mismatch``, ``annotation_status``, ``path_disagreement`` and
``unsupported_operation`` (any intervention). Through the run store, an unknown identity or an incomplete
dataset is the state ``unavailable``; the other refusals are the state ``invalid``.

No statistic is computed here and no random number is drawn. The seed this module records is the fit's seed,
copied from the saved artifact.
"""
from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from scripts.experiments.activation_dataset import (
    ActivationDataset, exact_revision, open_activation_dataset, read_safetensors, validate_activation_dataset,
    variant_rows,
)
from scripts.experiments.common import (
    FIXTURE_BACKEND, FIXTURE_MODEL, HEX64, Refusal, integer, read_json, require, require_structure, sha256_file,
    text,
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


def basis_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Model and tokenizer identity of a basis manifest. ``recorded`` needs both ids and two 40-hex revisions."""
    model = manifest.get("model") if isinstance(manifest.get("model"), dict) else {}
    unknown = [key for key in ("hf_id", "tokenizer_id") if not text(model.get(key))]
    unknown += [key for key in ("revision", "tokenizer_revision") if not exact_revision(model.get(key))]
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
    model = saved.get("model") or saved.get("base_model") or {}
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

    @property
    def mode(self) -> str:
        return self.preprocessing["mode"]

    @property
    def hidden_size(self) -> int:
        return self.manifest["model"]["hidden_size"]

    @property
    def identity(self) -> dict[str, Any]:
        return basis_identity(self.manifest)


def load_basis(manifest_path: Path | str) -> Basis:
    """Read a basis manifest, verify every listed file and load the tensors.

    Refuses ``artifact_hash`` when a listed file is missing or its SHA-256 differs, ``preprocessing_mismatch``
    when the manifest's mode is not the mode the saved artifact records (or a ``preprocessing_center`` tensor is
    present or absent against the mode), ``dimension_mismatch`` for a wrong tensor shape and ``non_finite`` for
    a NaN or infinite tensor value.
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
                 layers=layers)


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


def check_split_leakage(manifest: Mapping[str, Any], protocol: Mapping[str, Any], *,
                        fit_dataset: ActivationDataset | None = None,
                        scoring_dataset: ActivationDataset | None = None) -> dict[str, Any]:
    """Refuse ``split_leakage`` when fitting, profiling or selection touched a validation or fresh-test family.

    Checked against the protocol: the family ids and corpus ids each stage lists; the fit corpus's document
    token hashes, when the manifest lists them; the fit dataset's own row map, when that dataset is supplied;
    and whether the basis was fit on the dataset that is being scored while it holds held-out families.
    Returns which of these checks ran. A check that could not run is reported, not passed silently.
    """
    held_out = {f["family_id"]: f["split"] for f in protocol["case_families"] if f["split"] != "discovery"}
    require(manifest["fit"]["split"] == "discovery", "split_leakage",
            f"the basis fit split is {manifest['fit']['split']!r}, not 'discovery'")
    for stage in STAGES:
        named = set(manifest[stage]["family_ids"]) | set(manifest[stage]["corpus_ids"])
        leaked = sorted(named & set(held_out))
        require(not leaked, "split_leakage",
                f"the basis {stage} stage names held-out families {[(f, held_out[f]) for f in leaked]}")
    held_tokens = {entry["token_sha256"]: f"{f['family_id']}:{name}" for f in protocol["case_families"]
                   if f["split"] != "discovery" for name, entry in f["variants"].items()}
    report = {"stage_ids": "checked", "document_token_hashes": "not_listed_in_manifest",
              "fit_dataset_row_map": "fit_dataset_not_supplied", "scoring_dataset_is_fit_dataset": "not_checked"}
    listed = manifest["fit"]["document_token_sha256"]
    if listed is not None:
        leaked = sorted(held_tokens[h] for h in set(listed) & set(held_tokens))
        require(not leaked, "split_leakage", f"fit corpus documents have the token ids of held-out variants {leaked}")
        report["document_token_hashes"] = "checked"
    fit_sha = manifest["fit"]["activation_manifest_sha256"]
    if fit_dataset is not None:
        require(fit_sha is None or fit_dataset.manifest_sha256 == fit_sha, "split_leakage",
                "the supplied fit dataset is not the one the basis manifest names by SHA-256")
        block = fit_dataset.row_map or {}
        for document in block.get("documents", []):
            where = f"fit dataset document {document.get('document_index')}"
            require(document.get("split") == "discovery", "split_leakage",
                    f"{where} is in split {document.get('split')!r}")
            require(document.get("family_id") not in held_out, "split_leakage",
                    f"{where} belongs to held-out family {document.get('family_id')!r}")
            require(document.get("token_sha256") not in held_tokens, "split_leakage",
                    f"{where} has the token ids of held-out variant {held_tokens.get(document.get('token_sha256'))}")
        report["fit_dataset_row_map"] = "checked" if block else "fit_dataset_has_no_row_map"
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
    _check_task_against_basis(task, basis, dataset)
    leakage = check_split_leakage(basis.manifest, protocol, fit_dataset=fit_dataset, scoring_dataset=dataset)
    validate_activation_dataset(dataset, protocol=protocol)
    rows = variant_rows(dataset, protocol, spec["family_id"], spec["variant"])
    if method.get("positions", "all") == "last":
        rows = rows[-1:]
    selected = [row["row"] for row in rows]
    scores_out, energy_rows, reconstruction_rows = [], [], []
    execution: dict[str, Any] | None = None
    for layer in sorted(method["layers"]):
        result = apply_basis(basis, dataset.layer(layer)[selected], layer=layer, path=path)
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
            "activation_dataset": {"manifest_sha256": dataset.manifest_sha256, "dtype": dataset.dtype,
                                   "sample_count": dataset.sample_count},
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
        "limitations": list(manifest["limitations"]),
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
    require(record.get("basis_a") == basis_a and record.get("basis_b") == basis_b and record.get("layer") == layer,
            "sign_convention", "the alignment record names other bases or another layer than the ones compared")
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
            identity = basis_identity(manifest)
            if identity["status"] != "recorded":
                return "unavailable", (f"unknown_identity: the basis manifest does not record "
                                       f"{identity['unknown_fields']} as exact values; parity is not established")
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
        require(payload["execution_path"]["used"] in EXECUTION_PATHS, "execution_path",
                f"execution_path.used must be one of {list(EXECUTION_PATHS)}")
        require((payload["execution_path"]["used"] == "icalens") == text(
            payload["execution_path"]["icalens_version"]), "execution_path",
            "icalens_version is recorded exactly when the icalens path produced the payload")
        layers = sorted(method["layers"])
        require(payload["capture"]["layers"] == layers and payload["capture"]["positions"]
                == method.get("positions", "all"), "layer_metadata", "layers or positions differ from the task")
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
        for row in payload["scores"]:
            require(type(row["score"]) is float and math.isfinite(row["score"]), "non_finite",
                    f"score at {row['layer']}/{row['position']}/{row['component']} is not a finite float")
            share = row["energy_share"]
            require(share is None or (type(share) is float and 0.0 <= share <= 1.0), "non_finite",
                    "an energy share must be null or a float in [0, 1]")
        status = {(row["layer"], row["position"]): row["status"] for row in payload["energy_share"]["rows"]}
        for layer in layers:
            for position in positions:
                shares = [row["energy_share"] for row in payload["scores"]
                          if row["layer"] == layer and row["position"] == position]
                if status.get((layer, position)) == "computed":
                    require(all(s is not None for s in shares) and abs(sum(shares) - 1.0) <= 1e-9,
                            "non_finite", f"energy shares at layer {layer}, position {position} do not sum to 1")
                else:
                    require(status.get((layer, position)) == "not_computed_zero_energy" and all(
                        s is None for s in shares), "non_finite",
                        "a row without computed energy must carry null shares, never zeros")
        for row in payload["component_annotations"]:
            require(row.get("status") == "hypothesis" and text(row.get("source")), "annotation_status",
                    "a component annotation must be a hypothesis with its source")


ADAPTER = IcaAdapter()
