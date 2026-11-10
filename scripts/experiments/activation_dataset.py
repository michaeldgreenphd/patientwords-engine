"""Write, read and validate an ICA Lens ActivationDataset (format ``icalens.activations``, version 1).

The format is defined by the ``icalens`` package (``docs/activation-dataset-format.md`` and
``src/icalens/_activation_dataset.py`` in ``michaeldgreenphd/patientwords-ica-lens-paper``, head ``aa3b95c``).
This module restates the byte layout with numpy and the standard library, because the engine environment has
neither ``torch`` nor ``safetensors``. It copies no source from that package.

Directory layout::

    <root>/activations.json                manifest, written last
    <root>/samples.safetensors             int64 tensors document_index, position, token_id (one entry per row)
    <root>/layers/layer_NN.<dtype>.bin     headerless, row-major, little-endian [sample_count, hidden_size]

This reader checks more than the reference reader does. The reference reader checks the format name, the
version, the dtype name, the top-level status, and a layer file's byte count when that layer is opened. It does
not check per-layer status, sample metadata (unless ``samples()`` is called), finiteness, duplicate rows or any
identity field. Every one of those is checked here, and a failure is a named ``Refusal``:

* ``dataset_format``      the manifest, the dtype or a container file is not what the format defines; every
  malformed input ends here, and sizes are computed with Python integers, so a declared shape cannot overflow
* ``incomplete``          the dataset or one of its layers is not ``complete``, or a ``.partial`` file remains
* ``dimension_mismatch``  a layer file's byte count, a declared shape or a sample tensor's length is wrong
* ``non_finite``          a layer holds NaN or infinity
* ``row_alignment``       duplicate ``(document_index, position)`` rows, an unmapped document, a missing row, or
  a row whose token id differs from the protocol's token id at that position
* ``artifact_hash``       a layer file or the samples file differs from the SHA-256 or byte count that the
  manifest records for it

File pins. The format itself records no hash of a layer file or of the samples file. The writer in this module
records the SHA-256 and byte count of every layer file and of the samples file under the provenance key
``patientwords_files`` (``patientwords.activation-files/1``); the manifest is written last, so its own SHA-256
then covers the values. The reader verifies those pins whenever it reads a file. A dataset without the key (one
written by the reference writer) is accepted and reported with ``file_pins: "not_recorded"``: such a dataset is
identified by its manifest only, and nothing here fills the missing pins in.

The writer. ``write_activation_dataset`` stages a dataset inside the target, validates it and moves it into
place. It writes only through real directories inside the target that ``common.check_output_path`` accepted
(a symbolic link at the target, at ``layers`` or at a destination file is ``protected_root``), and it keeps the
files it replaces until the new dataset has validated, so a failed overwrite puts the previous dataset back.
Its docstring states what a killed process leaves.

Model and tokenizer identity are never invented. The format has no tokenizer field, so this module reads the
tokenizer from ``provenance.patientwords.tokenizer`` when a PatientWords writer put it there. A dataset that
lacks a full model revision or a tokenizer identity is read with ``identity.status == "unknown"``.

What the format cannot say: byte order (the reference writer emits native order; this module writes and reads
little-endian), the precision the model was loaded in, and the source text of a row.

Nothing here loads a model or opens a socket.
"""
from __future__ import annotations

import functools
import json
import math
import os
import shutil
import stat
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, TypeVar

import numpy as np

from scripts.experiments.common import (
    HEX40, HEX64, Refusal, atomic_write_bytes, check_output_path, digest, integer, require, sha256_bytes, text,
)

FORMAT = "icalens.activations"
FORMAT_VERSION = 1
MANIFEST_NAME = "activations.json"
SAMPLES_NAME = "samples.safetensors"
REQUIRED_SAMPLE_TENSORS = ("document_index", "position", "token_id")
ROWS_SCHEMA = "patientwords.activation-rows/1"
# File pins written by this module's writer: provenance[FILES_KEY] = {schema_version, samples, layers}.
FILES_KEY = "patientwords_files"
FILES_SCHEMA = "patientwords.activation-files/1"
PINS_VERIFIED, PINS_NOT_RECORDED = "verified", "not_recorded"
# The writer stages a dataset in <target>/.staging-XXXXXXXX and, while it replaces an existing dataset, keeps the
# files it replaces in a subdirectory of that staging directory until every replacement has succeeded.
STAGING_PREFIX = ".staging-"
REPLACED_DIR = ".replaced"
DOCUMENT_ROLES = ("fit_corpus", "protocol_variant")
POSITION_POLICIES = ("all", "last")

# numpy dtype strings are explicit little-endian. bfloat16 has no numpy dtype: it is decoded on read (the high
# 16 bits of an IEEE float32) and is not written by this module.
LAYER_DTYPES = {"float16": "<f2", "float32": "<f4", "float64": "<f8"}
READ_ONLY_DTYPES = ("bfloat16",)
ITEMSIZE = {"bfloat16": 2, "float16": 2, "float32": 4, "float64": 8}

# safetensors dtype names for the subset this module reads and writes, with the order the reference writer
# sorts by (descending dtype rank, then ascending name).
SAFETENSORS_DTYPES = {"F16": "<f2", "I32": "<i4", "F32": "<f4", "F64": "<f8", "I64": "<i8"}
_SAFETENSORS_RANK = {"F16": 0, "I32": 1, "F32": 2, "F64": 3, "I64": 4}
_SAFETENSORS_NAMES = {np.dtype(code).newbyteorder("=").str.lstrip("<>=|"): name
                      for name, code in SAFETENSORS_DTYPES.items()}
MAX_SAFETENSORS_HEADER = 100_000_000

_F = TypeVar("_F", bound=Callable[..., Any])


def _format_guard(function: _F) -> _F:
    """Turn an error raised by a malformed input into ``Refusal('dataset_format')``; pass a ``Refusal`` through.

    The explicit checks below name what is wrong. This guard is the second line: an input shape nobody thought
    of still ends in a named refusal, never in a ``ValueError`` or ``TypeError`` from numpy or the JSON module.
    """
    @functools.wraps(function)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except Refusal:
            raise
        except (KeyError, TypeError, AttributeError, ValueError, OverflowError, IndexError, RecursionError,
                struct.error) as exc:
            raise Refusal("dataset_format", f"malformed input: {type(exc).__name__}: {exc}") from exc
    return run  # type: ignore[return-value]


# --------------------------------------------------------------------------------------------- safetensors

def _safetensors_name(array: np.ndarray) -> str:
    key = array.dtype.newbyteorder("=").str.lstrip("<>=|")
    require(key in _SAFETENSORS_NAMES, "dataset_format",
            f"dtype {array.dtype} is outside the safetensors subset {sorted(SAFETENSORS_DTYPES)}")
    return _SAFETENSORS_NAMES[key]


def safetensors_bytes(tensors: Mapping[str, np.ndarray]) -> bytes:
    """The safetensors container for ``tensors``, as bytes.

    Layout: an unsigned 64-bit little-endian header length, a compact JSON header padded with spaces to a
    multiple of 8 bytes, then the tensor bytes. The header maps each name to ``dtype``, ``shape`` and
    ``data_offsets`` (begin and end, relative to the first byte after the header). Tensors are ordered by
    descending dtype rank and then by name, which is the order the reference writer uses. No ``__metadata__``
    entry is written.
    """
    require(bool(tensors), "dataset_format", "a safetensors file needs at least one tensor")
    entries = []
    for name, value in tensors.items():
        require(text(name) and name.isascii() and name != "__metadata__", "dataset_format",
                f"tensor name {name!r} must be non-empty ASCII and not '__metadata__'")
        array = np.asarray(value)
        code = _safetensors_name(array)
        entries.append((name, code, np.ascontiguousarray(array, dtype=SAFETENSORS_DTYPES[code])))
    entries.sort(key=lambda entry: (-_SAFETENSORS_RANK[entry[1]], entry[0]))
    header: dict[str, Any] = {}
    offset = 0
    for name, code, array in entries:
        header[name] = {"dtype": code, "shape": list(array.shape), "data_offsets": [offset, offset + array.nbytes]}
        offset += array.nbytes
    encoded = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encoded += b" " * ((8 - len(encoded) % 8) % 8)
    return struct.pack("<Q", len(encoded)) + encoded + b"".join(array.tobytes() for _, _, array in entries)


def write_safetensors(path: Path | str, tensors: Mapping[str, np.ndarray]) -> str:
    """Write ``tensors`` atomically and return the file's SHA-256. The caller has checked the path."""
    data = safetensors_bytes(tensors)
    atomic_write_bytes(path, data)
    return sha256_bytes(data)


@_format_guard
def parse_safetensors(data: bytes, where: str = "safetensors") -> dict[str, np.ndarray]:
    """Decode a safetensors container. Every offset, shape and byte count is checked; nothing is trusted.

    Element counts are products of Python integers, so a declared shape cannot overflow into a small number.
    Every malformed container is ``dataset_format``."""
    require(len(data) >= 8, "dataset_format", f"{where}: shorter than the 8-byte header length")
    (length,) = struct.unpack("<Q", data[:8])
    require(0 < length <= MAX_SAFETENSORS_HEADER and 8 + length <= len(data), "dataset_format",
            f"{where}: header length {length} does not fit the file")
    try:
        header = json.loads(data[8:8 + length].decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise Refusal("dataset_format", f"{where}: header is not JSON: {exc}") from exc
    require(isinstance(header, dict), "dataset_format", f"{where}: header must be a JSON object")
    body = memoryview(data)[8 + length:]
    tensors: dict[str, np.ndarray] = {}
    spans: list[tuple[int, int, str]] = []
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        require(isinstance(entry, dict) and isinstance(entry.get("dtype"), str)
                and entry["dtype"] in SAFETENSORS_DTYPES, "dataset_format",
                f"{where}: tensor {name!r} has a dtype outside {sorted(SAFETENSORS_DTYPES)}")
        shape, offsets = entry.get("shape"), entry.get("data_offsets")
        require(isinstance(shape, list) and all(integer(n) for n in shape) and isinstance(offsets, list)
                and len(offsets) == 2 and all(integer(n) for n in offsets), "dataset_format",
                f"{where}: tensor {name!r} needs an integer shape and two integer data_offsets")
        begin, end = offsets
        dtype = np.dtype(SAFETENSORS_DTYPES[entry["dtype"]])
        count = math.prod(shape)  # Python integers: exact for any declared shape; the empty shape gives 1
        require(begin <= end <= len(body) and end - begin == count * dtype.itemsize, "dataset_format",
                f"{where}: tensor {name!r} spans bytes {begin}..{end}, which does not match shape {shape} of "
                f"{entry['dtype']} inside a {len(body)}-byte buffer")
        # A zero-size tensor can still declare a dimension no array holds, e.g. [2**70, 0].
        require(all(n < 2 ** 63 for n in shape), "dataset_format",
                f"{where}: tensor {name!r} declares a dimension beyond 2**63 - 1 in shape {shape}")
        spans.append((begin, end, name))
        tensors[name] = np.frombuffer(body[begin:end], dtype=dtype).reshape(shape).copy()
    position = 0
    for begin, end, name in sorted(spans):
        require(begin == position, "dataset_format",
                f"{where}: tensor {name!r} starts at byte {begin}; the buffer must be covered without gaps or "
                f"overlaps (expected {position})")
        position = end
    require(position == len(body), "dataset_format",
            f"{where}: {len(body) - position} bytes of the buffer belong to no tensor")
    return tensors


def read_safetensors(path: Path | str) -> dict[str, np.ndarray]:
    """``parse_safetensors`` of a file. A missing file is ``dataset_format``."""
    file = Path(path)
    require(file.is_file(), "dataset_format", f"{file} is not a file")
    return parse_safetensors(file.read_bytes(), file.name)


# ------------------------------------------------------------------------------------------------ identity

def exact_revision(value: Any) -> bool:
    """True for a full 40-hex commit. ``"unknown"``, ``"main"``, null and a short hash are not exact."""
    return isinstance(value, str) and bool(HEX40.fullmatch(value))


def dataset_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Model and tokenizer identity as the manifest records them. Missing parts stay null and are listed.

    ``status`` is ``"recorded"`` only when the model id, a 40-hex model revision, the tokenizer id and a
    40-hex tokenizer revision are all present. Anything else is ``"unknown"``. Parity with a real model is
    never established by this module, whatever the status.
    """
    def mapping(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, dict) else {}

    model = mapping(manifest.get("model"))
    tokenizer = mapping(mapping(mapping(manifest.get("provenance")).get("patientwords")).get("tokenizer"))
    values = {
        "model_id": model.get("repo_id") if text(model.get("repo_id")) else None,
        "model_revision": model.get("revision") if text(model.get("revision")) else None,
        "tokenizer_id": tokenizer.get("id") if text(tokenizer.get("id")) else None,
        "tokenizer_revision": tokenizer.get("revision") if text(tokenizer.get("revision")) else None,
    }
    unknown = [key for key in ("model_id", "tokenizer_id") if values[key] is None]
    unknown += [key for key in ("model_revision", "tokenizer_revision") if not exact_revision(values[key])]
    return {**values, "model_type": model.get("type") if text(model.get("type")) else None,
            "status": "unknown" if unknown else "recorded", "unknown_fields": sorted(unknown),
            "parity": "not_established"}


# -------------------------------------------------------------------------------------------------- reader

@dataclass(frozen=True)
class ActivationDataset:
    """An opened dataset. ``open_activation_dataset`` checks the manifest; ``validate`` checks everything."""

    root: Path
    manifest: dict[str, Any]
    manifest_sha256: str

    @property
    def sample_count(self) -> int:
        return self.manifest["sample_count"]

    @property
    def hidden_size(self) -> int:
        return self.manifest["hidden_size"]

    @property
    def dtype(self) -> str:
        return self.manifest["dtype"]

    @property
    def layers(self) -> tuple[int, ...]:
        return tuple(sorted(int(key) for key in self.manifest["layers"]))

    @property
    def identity(self) -> dict[str, Any]:
        return dataset_identity(self.manifest)

    @property
    def row_map(self) -> dict[str, Any] | None:
        """``provenance.patientwords`` when a PatientWords writer recorded it, else None."""
        block = self.manifest["provenance"].get("patientwords")
        return block if isinstance(block, dict) else None

    @property
    def activation_site(self) -> str | None:
        """The manifest's ``activation_site`` when it is a non-empty string, else None. Never filled in."""
        value = self.manifest.get("activation_site")
        return value if text(value) else None

    @property
    def layer_indexing(self) -> str | None:
        """The manifest's ``layer_indexing`` when it is a non-empty string, else None. Never filled in."""
        value = self.manifest.get("layer_indexing")
        return value if text(value) else None

    @property
    def file_pins(self) -> dict[str, Any] | None:
        """``provenance.patientwords_files`` when a PatientWords writer recorded it, else None.

        ``open_activation_dataset`` has checked its shape. None means the manifest records no hash of its files;
        it never means that a hash was checked."""
        block = self.manifest["provenance"].get(FILES_KEY)
        return block if isinstance(block, dict) else None

    def _pinned_bytes(self, relative: str, pin: Mapping[str, Any] | None, what: str) -> tuple[bytes, str]:
        """The bytes of one file and their SHA-256. With a pin, a wrong size or hash is ``artifact_hash``."""
        data = (self.root / relative).read_bytes()
        actual = sha256_bytes(data)
        if pin is not None:
            require(len(data) == pin["bytes"] and actual == pin["sha256"], "artifact_hash",
                    f"{what}: {relative} has {len(data)} bytes and SHA-256 {actual}; the manifest records "
                    f"{pin['bytes']} bytes and {pin['sha256']}")
        return data, actual

    def _layer_bytes(self, layer: int) -> tuple[bytes, str]:
        """Raw bytes of one layer file and their SHA-256, after the size check and the pin check."""
        require(integer(layer), "dimension_mismatch", f"a layer is a non-negative integer; got {layer!r}")
        entry = self.manifest["layers"].get(str(layer))
        require(entry is not None, "dimension_mismatch", f"layer {layer} is not in the dataset; it holds "
                f"{list(self.layers)}")
        path = self.root / entry["file"]
        expected = self.sample_count * self.hidden_size * ITEMSIZE[self.dtype]
        actual = path.stat().st_size if path.is_file() else -1
        require(actual == expected, "dimension_mismatch",
                f"layer {layer}: {entry['file']} has {actual} bytes; sample_count {self.sample_count} x "
                f"hidden_size {self.hidden_size} x {ITEMSIZE[self.dtype]} bytes is {expected}")
        pins = self.file_pins
        return self._pinned_bytes(entry["file"], pins["layers"][str(layer)] if pins else None, f"layer {layer}")

    def _samples_bytes(self) -> tuple[bytes, str]:
        relative = self.manifest["samples_file"]
        require((self.root / relative).is_file(), "dataset_format", f"{self.root / relative} is not a file")
        pins = self.file_pins
        return self._pinned_bytes(relative, pins["samples"] if pins else None, "samples")

    def verify_files(self, layers: Iterable[int] | None = None) -> dict[str, Any]:
        """Hash the named layer files (every layer by default) and the samples file without decoding them.

        Returns ``{"file_pins": "verified" | "not_recorded", "samples_sha256": ..., "layer_sha256": {layer: ...}}``.
        The hashes are of the bytes on disk now. ``verified`` means the manifest records a SHA-256 and a byte
        count for each of these files and all of them matched; a mismatch is ``artifact_hash``.
        ``not_recorded`` means the manifest records none, so nothing was compared.
        """
        wanted = self.layers if layers is None else tuple(sorted(layers))
        layer_hashes = {str(layer): self._layer_bytes(layer)[1] for layer in wanted}
        return {"file_pins": PINS_VERIFIED if self.file_pins else PINS_NOT_RECORDED,
                "samples_sha256": self._samples_bytes()[1], "layer_sha256": layer_hashes}

    def layer_with_hash(self, layer: int) -> tuple[np.ndarray, str]:
        """``layer(layer)`` and the SHA-256 of the bytes that were decoded."""
        raw, sha256 = self._layer_bytes(layer)
        if self.dtype == "bfloat16":
            values = (np.frombuffer(raw, dtype="<u2").astype("<u4") << 16).view("<f4")
        else:
            values = np.frombuffer(raw, dtype=LAYER_DTYPES[self.dtype])
        values = values.reshape(self.sample_count, self.hidden_size).copy()
        require(bool(np.isfinite(values).all()), "non_finite",
                f"layer {layer}: {int((~np.isfinite(values)).sum())} values are NaN or infinite")
        return values, sha256

    def layer(self, layer: int) -> np.ndarray:
        """One layer as a ``[sample_count, hidden_size]`` array in its stored dtype (bfloat16 as float32).

        Refuses ``dimension_mismatch`` when the file's byte count is not
        ``sample_count * hidden_size * itemsize``, ``artifact_hash`` when the manifest pins the file and its
        bytes differ, and ``non_finite`` when a value is NaN or infinite.
        """
        return self.layer_with_hash(layer)[0]

    def samples_with_hash(self) -> tuple[dict[str, np.ndarray], str]:
        """``samples()`` and the SHA-256 of the samples file that was decoded."""
        raw, sha256 = self._samples_bytes()
        return self._sample_tensors(raw), sha256

    def samples(self) -> dict[str, np.ndarray]:
        """The three required sample tensors as int64 arrays of length ``sample_count``, plus any extras.

        Refuses ``artifact_hash`` when the manifest pins the samples file and its bytes differ."""
        return self.samples_with_hash()[0]

    @_format_guard
    def _sample_tensors(self, raw: bytes) -> dict[str, np.ndarray]:
        path = self.root / self.manifest["samples_file"]
        tensors = parse_safetensors(raw, path.name)
        missing = sorted(set(REQUIRED_SAMPLE_TENSORS) - set(tensors))
        require(not missing, "dataset_format", f"{path.name} lacks the required tensors {missing}")
        for name in REQUIRED_SAMPLE_TENSORS:
            tensor = tensors[name]
            require(tensor.dtype.kind == "i", "dataset_format", f"{path.name}: {name} must be an integer tensor")
            require(tensor.ndim == 1 and tensor.shape[0] == self.sample_count, "dimension_mismatch",
                    f"{path.name}: {name} has shape {tuple(tensor.shape)}; expected ({self.sample_count},)")
            require(bool((tensor >= 0).all()), "row_alignment", f"{path.name}: {name} holds a negative value")
            tensors[name] = tensor.astype(np.int64)
        return tensors


def _check_file_pins(manifest: Mapping[str, Any]) -> None:
    """Shape of ``provenance.patientwords_files`` when the key is present. A present block that is malformed or
    that leaves a file out is ``dataset_format``: it must not read as 'no pins recorded'."""
    if FILES_KEY not in manifest["provenance"]:
        return
    block = manifest["provenance"][FILES_KEY]

    def pin(entry: Any, file: str) -> bool:
        return (isinstance(entry, dict) and set(entry) == {"file", "sha256", "bytes"} and entry["file"] == file
                and isinstance(entry["sha256"], str) and bool(HEX64.fullmatch(entry["sha256"]))
                and integer(entry["bytes"]))

    require(isinstance(block, dict) and set(block) == {"schema_version", "samples", "layers"}
            and block["schema_version"] == FILES_SCHEMA, "dataset_format",
            f"provenance.{FILES_KEY} must be a {FILES_SCHEMA} object with samples and layers")
    require(pin(block["samples"], manifest["samples_file"]), "dataset_format",
            f"provenance.{FILES_KEY}.samples must record file, sha256 and bytes of {manifest['samples_file']!r}")
    layers = manifest["layers"]
    require(isinstance(block["layers"], dict) and set(block["layers"]) == set(layers) and all(
        pin(block["layers"][key], layers[key]["file"]) for key in layers), "dataset_format",
        f"provenance.{FILES_KEY}.layers must record file, sha256 and bytes of every layer file, and of no other")


def _check_manifest(manifest: Any, root: Path) -> None:
    require(isinstance(manifest, dict), "dataset_format", f"{MANIFEST_NAME} must hold a JSON object")
    require(manifest.get("format") == FORMAT and manifest.get("format_version") == FORMAT_VERSION,
            "dataset_format", f"expected format {FORMAT!r} version {FORMAT_VERSION}; got "
            f"{manifest.get('format')!r} version {manifest.get('format_version')!r}")
    require(isinstance(manifest.get("dtype"), str) and manifest["dtype"] in ITEMSIZE, "dataset_format",
            f"dtype must be one of {sorted(ITEMSIZE)}; got {manifest.get('dtype')!r}")
    require(integer(manifest.get("sample_count"), 1) and integer(manifest.get("hidden_size"), 1),
            "dataset_format", "sample_count and hidden_size must be positive integers")
    layers = manifest.get("layers")
    require(isinstance(layers, dict) and bool(layers), "dataset_format", "the dataset names no layers")
    for key, entry in layers.items():
        # isascii first: str.isdigit accepts characters such as a superscript two, which int() refuses.
        require(key.isascii() and key.isdigit() and str(int(key)) == key and isinstance(entry, dict)
                and text(entry.get("file")), "dataset_format",
                f"layers[{key!r}] must be keyed by an ASCII decimal layer number and name a file")
        relative = Path(entry["file"])
        require(not relative.is_absolute() and ".." not in relative.parts, "dataset_format",
                f"layers[{key!r}].file must be a relative path inside the dataset: {entry['file']!r}")
    samples_file = manifest.get("samples_file")
    require(text(samples_file) and not Path(samples_file).is_absolute() and ".." not in Path(samples_file).parts,
            "dataset_format", "samples_file must be a relative path inside the dataset")
    require(isinstance(manifest.get("provenance"), dict), "dataset_format", "provenance must be a JSON object")
    require(manifest.get("model") is None or isinstance(manifest["model"], dict), "dataset_format",
            "model must be an object when present")
    _check_file_pins(manifest)
    # Completion is checked after the shape of the manifest, so an unfinished capture is told apart from a
    # malformed one.
    partial = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.partial"))
    require(manifest.get("status") == "complete", "incomplete",
            f"dataset status is {manifest.get('status')!r}, not 'complete'")
    pending = sorted(key for key, entry in layers.items() if entry.get("status") != "complete")
    require(not pending, "incomplete", f"layers {pending} are not marked complete")
    require(not partial, "incomplete", f"partial capture files remain: {partial}")
    for key, entry in layers.items():
        require(entry.get("shape") == [manifest["sample_count"], manifest["hidden_size"]], "dimension_mismatch",
                f"layers[{key!r}].shape is {entry.get('shape')}; the manifest says "
                f"[{manifest['sample_count']}, {manifest['hidden_size']}]")


@_format_guard
def open_activation_dataset(root: Path | str) -> ActivationDataset:
    """Open a dataset directory and check its manifest. Layer files and sample tensors are read on demand."""
    directory = Path(root).resolve()
    manifest_path = directory / MANIFEST_NAME
    require(manifest_path.is_file(), "dataset_format", f"no {MANIFEST_NAME} in {directory}")
    data = manifest_path.read_bytes()
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise Refusal("dataset_format", f"{MANIFEST_NAME} is not JSON: {exc}") from exc
    _check_manifest(manifest, directory)
    return ActivationDataset(root=directory, manifest=manifest, manifest_sha256=sha256_bytes(data))


@_format_guard
def _documents(dataset: ActivationDataset) -> dict[int, dict[str, Any]]:
    block = dataset.row_map
    require(block is not None and block.get("schema_version") == ROWS_SCHEMA and isinstance(
        block.get("documents"), list), "row_alignment",
        f"provenance.patientwords ({ROWS_SCHEMA}) is absent, so no row can be traced to a source document")
    require(block.get("positions") in POSITION_POLICIES, "row_alignment",
            f"provenance.patientwords.positions must be one of {list(POSITION_POLICIES)}")
    documents: dict[int, dict[str, Any]] = {}
    for entry in block["documents"]:
        require(isinstance(entry, dict) and integer(entry.get("document_index")) and entry.get("role")
                in DOCUMENT_ROLES and integer(entry.get("n_tokens"), 1) and text(entry.get("split")),
                "row_alignment", "each document needs document_index, role, split and n_tokens")
        require(entry["document_index"] not in documents, "row_alignment",
                f"document_index {entry['document_index']} is listed twice in the row map")
        # An id is a string or is not there. A list or a number under an id key would pass a membership test
        # against a set of held-out ids without ever being compared with one.
        for key in ("family_id", "corpus_id", "variant"):
            named = entry.get(key)
            require(named is None or isinstance(named, str), "row_alignment",
                    f"document {entry['document_index']}: {key} must be a string, null or absent; found "
                    f"{type(named).__name__}")
        token_hash = entry.get("token_sha256")
        require(token_hash is None or (isinstance(token_hash, str) and bool(HEX64.fullmatch(token_hash))),
                "row_alignment", f"document {entry['document_index']}: token_sha256 must be 64 lower-case hex "
                "digits, null or absent")
        if entry["role"] == "protocol_variant":
            require(text(entry.get("family_id")) and text(entry.get("variant")), "row_alignment",
                    f"document {entry['document_index']}: a protocol_variant document names family_id and variant")
        else:
            require(text(entry.get("corpus_id")), "row_alignment",
                    f"document {entry['document_index']}: a fit_corpus document names its corpus_id")
        documents[entry["document_index"]] = entry
    return documents


def row_map_documents(dataset: ActivationDataset) -> dict[int, dict[str, Any]]:
    """The dataset's row-map documents by ``document_index``, after the structural check every reader of a row
    map goes through: the ``patientwords.activation-rows/1`` block with a position policy, and per document an
    integer index listed once, a known role, a split, a token count, ids that are strings (or absent) and a
    token hash that is 64 hex digits (or absent). Refuses ``row_alignment``. The scored dataset and a supplied
    fit dataset are both read through this function."""
    return _documents(dataset)


def row_index(dataset: ActivationDataset, samples: Mapping[str, np.ndarray] | None = None
              ) -> dict[int, dict[int, tuple[int, int]]]:
    """``{document_index: {position: (row, token_id)}}``. Refuses duplicate ``(document_index, position)``."""
    samples = dataset.samples() if samples is None else samples
    index: dict[int, dict[int, tuple[int, int]]] = {}
    for row, (document, position, token) in enumerate(zip(
            samples["document_index"].tolist(), samples["position"].tolist(), samples["token_id"].tolist())):
        positions = index.setdefault(document, {})
        require(position not in positions, "row_alignment",
                f"duplicate row: document_index {document}, position {position} occurs at rows "
                f"{positions.get(position, (None,))[0]} and {row}")
        positions[position] = (row, token)
    return index


def variant_rows(dataset: ActivationDataset, protocol: Mapping[str, Any], family_id: str, variant: str,
                 index: Mapping[int, Mapping[int, tuple[int, int]]] | None = None) -> list[dict[str, int]]:
    """The dataset rows of one protocol variant, in position order, checked against the protocol's token ids.

    Refuses ``row_alignment`` when the variant has no document, when a required position has no row, when a row
    sits beyond the variant's tokens, or when a row's token id is not the protocol's token id at that position.
    """
    documents = _documents(dataset)
    index = row_index(dataset) if index is None else index
    matches = [d for d in documents.values() if d["role"] == "protocol_variant"
               and d["family_id"] == family_id and d["variant"] == variant]
    require(len(matches) == 1, "row_alignment",
            f"{family_id}:{variant}: the row map lists {len(matches)} documents; exactly one is required")
    document = matches[0]
    family = next((f for f in protocol["case_families"] if f["family_id"] == family_id), None)
    require(family is not None and variant in family["variants"], "row_alignment",
            f"{family_id}:{variant} is not a variant of the protocol")
    entry = family["variants"][variant]
    token_ids = entry["token_ids"]
    where = f"{family_id}:{variant} (document_index {document['document_index']})"
    require(document.get("token_sha256") == entry["token_sha256"] and document["n_tokens"] == len(token_ids),
            "row_alignment", f"{where}: the row map's token hash or token count is not the protocol's")
    require(document["split"] == family["split"], "row_alignment",
            f"{where}: the row map says split {document['split']!r}; the protocol says {family['split']!r}")
    positions = index.get(document["document_index"], {})
    beyond = sorted(p for p in positions if p >= len(token_ids))
    require(not beyond, "row_alignment", f"{where}: rows at positions {beyond} lie beyond {len(token_ids)} tokens")
    policy = dataset.row_map["positions"]
    wanted = list(range(len(token_ids))) if policy == "all" else [len(token_ids) - 1]
    missing = [p for p in wanted if p not in positions]
    require(not missing, "row_alignment", f"{where}: no activation row for positions {missing}")
    rows = []
    for position in sorted(positions):
        row, token = positions[position]
        require(token == token_ids[position], "row_alignment",
                f"{where}: row {row} at position {position} holds token id {token}; the protocol's token id "
                f"there is {token_ids[position]}")
        rows.append({"row": row, "position": position, "token_id": token,
                     "document_index": document["document_index"]})
    return rows


def validate_activation_dataset(root: Path | str | ActivationDataset, *, protocol: Mapping[str, Any] | None = None,
                                check_values: bool = True) -> dict[str, Any]:
    """Check a dataset end to end and return a report. Raises ``Refusal`` on the first violated rule.

    Always checked: manifest shape, completion markers, declared layer shapes, each layer file's byte count,
    the SHA-256 and byte count of every layer file and of the samples file when the manifest pins them
    (``artifact_hash``), finiteness (unless ``check_values`` is false), the sample tensors' type and length, and
    duplicate ``(document_index, position)`` rows. With a PatientWords row map: every row belongs to a listed
    document. With ``protocol``: every ``protocol_variant`` document is checked row by row against the
    protocol's token ids. Identity is reported, never refused here: the caller decides what an unknown identity
    means. A manifest without file pins is accepted and the report says ``file_pins: "not_recorded"``.
    """
    dataset = root if isinstance(root, ActivationDataset) else open_activation_dataset(root)
    layer_hashes: dict[str, str] = {}
    for layer in dataset.layers:
        # Both branches check the byte count and the pin; only the first decodes the values.
        layer_hashes[str(layer)] = (dataset.layer_with_hash(layer) if check_values
                                    else dataset._layer_bytes(layer))[1]
    samples, samples_sha256 = dataset.samples_with_hash()
    index = row_index(dataset, samples)
    report: dict[str, Any] = {
        "status": "validated", "format": FORMAT, "format_version": FORMAT_VERSION,
        "manifest_sha256": dataset.manifest_sha256, "sample_count": dataset.sample_count,
        "hidden_size": dataset.hidden_size, "dtype": dataset.dtype, "layers": list(dataset.layers),
        "activation_site": dataset.activation_site, "layer_indexing": dataset.layer_indexing,
        "file_pins": PINS_VERIFIED if dataset.file_pins else PINS_NOT_RECORDED,
        "samples_sha256": samples_sha256, "layer_sha256": layer_hashes,
        "identity": dataset.identity, "values_checked_finite": check_values,
        "byte_order": "little-endian assumed; the format does not declare it",
        "row_map": "absent", "protocol_alignment": "not_checked_no_protocol",
    }
    if dataset.row_map is not None:
        documents = _documents(dataset)
        unmapped = sorted(set(index) - set(documents))
        require(not unmapped, "row_alignment", f"rows name document_index values the row map does not list: "
                f"{unmapped[:10]}")
        empty = sorted(set(documents) - set(index))
        require(not empty, "row_alignment", f"the row map lists documents with no activation row: {empty[:10]}")
        report["row_map"] = "present"
        report["documents_by_role"] = {role: sum(1 for d in documents.values() if d["role"] == role)
                                       for role in DOCUMENT_ROLES}
        report["documents_by_split"] = {}
        for document in documents.values():
            report["documents_by_split"][document["split"]] = report["documents_by_split"].get(
                document["split"], 0) + 1
        if protocol is not None:
            checked = 0
            for document in sorted(documents.values(), key=lambda d: d["document_index"]):
                if document["role"] == "protocol_variant":
                    variant_rows(dataset, protocol, document["family_id"], document["variant"], index)
                    checked += 1
            report["protocol_alignment"] = "checked"
            report["protocol_variants_checked"] = checked
    else:
        require(protocol is None, "row_alignment",
                "a protocol was supplied but the dataset has no provenance.patientwords row map to align with")
    return report


def read_activation_dataset(root: Path | str, *, protocol: Mapping[str, Any] | None = None) -> ActivationDataset:
    """Open and fully validate a dataset. Use this before any value is read from it."""
    dataset = open_activation_dataset(root)
    validate_activation_dataset(dataset, protocol=protocol)
    return dataset


# -------------------------------------------------------------------------------------------------- writer

def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """The manifest bytes, in the serialization the reference writer uses: two-space indent, sorted keys,
    ASCII escapes, NaN refused, one final newline."""
    return (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def document_entry(document_index: int, token_ids: Iterable[int], *, role: str, split: str,
                   corpus_id: str | None = None, family_id: str | None = None,
                   variant: str | None = None) -> dict[str, Any]:
    """One row-map document entry. ``token_sha256`` is ``exploratory_methods.digest`` of the token id list."""
    ids = list(token_ids)
    entry: dict[str, Any] = {"document_index": document_index, "role": role, "split": split,
                             "n_tokens": len(ids), "token_sha256": digest(ids)}
    if role == "fit_corpus":
        entry["corpus_id"] = corpus_id
    else:
        entry["family_id"], entry["variant"] = family_id, variant
    return entry


def _entry_kind(path: Path) -> str:
    """``absent``, ``directory``, ``file``, ``link`` or ``other`` for the entry at ``path`` itself (a link is
    never followed)."""
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return "absent"
    if stat.S_ISLNK(mode):
        return "link"
    return "directory" if stat.S_ISDIR(mode) else "file" if stat.S_ISREG(mode) else "other"


def _check_destinations(given: Path, directory: Path, relatives: Iterable[str]) -> None:
    """Refuse a target through which a write would leave the directory ``check_output_path`` checked.

    ``directory`` is the resolved target. Every destination ``directory / relative`` must be reached through
    real directories inside it: the target itself, each directory between it and the file, and the file's own
    entry may be absent, and may not be a symbolic link. A link at ``layers`` would send ``os.replace`` to the
    directory the link names, which was never checked against the protected roots or the Git-checkout rule.
    A link is refused with ``protected_root``, the code of the path guard it would get around; an entry of
    another unexpected kind (a directory where a file goes, a file where a directory goes) is ``dataset_format``.
    """
    link = ("is a symbolic link. The writer does not write through a link: the path that was checked against "
            "the protected roots would not be the path that is written")
    require(_entry_kind(Path(os.path.abspath(given))) != "link" and _entry_kind(directory) != "link",
            "protected_root", f"the target {given} {link}")
    require(_entry_kind(directory) in ("absent", "directory"), "dataset_format",
            f"{directory} exists and is not a directory")
    for relative in relatives:
        parts = Path(relative).parts
        node = directory
        for part in parts[:-1]:
            node = node / part
            kind = _entry_kind(node)
            require(kind != "link", "protected_root", f"{node} {link}")
            require(kind in ("absent", "directory"), "dataset_format", f"{node} exists and is not a directory")
        kind = _entry_kind(directory / relative)
        require(kind != "link", "protected_root", f"{directory / relative} {link}")
        require(kind in ("absent", "file"), "dataset_format",
                f"{directory / relative} exists and is not a regular file")
        # One more statement of the same rule, on the resolved path: the file's directory is inside the target.
        parent = (directory / relative).parent
        require(parent.resolve() == parent, "protected_root",
                f"{parent} does not resolve to itself; a component of it {link}")


def _install(staging: Path, directory: Path, relatives: list[str]) -> "ActivationDataset":
    """Move the staged files into ``directory``, validate the result, and put everything back if a step fails.

    ``relatives`` ends with the manifest. Each file that is already in ``directory`` is first moved to
    ``staging / REPLACED_DIR`` under its relative name, the old manifest before any other file; then the new
    files are moved in, the new manifest last; then the installed dataset is read and validated. So at every
    moment the directory holds either a manifest with exactly the files it was written with, or no manifest.
    On an exception (an I/O error, an interrupt, a refusal of the installed dataset) the new files that were
    moved in are removed, the directories this call created are removed, and the old files are moved back, the
    old manifest last; the exception is then raised again. If moving back fails as well, the staging directory
    is kept and the error names it, because it holds the old files.
    """
    kept = staging / REPLACED_DIR
    ordered = [relatives[-1], *relatives[:-1]]       # the old manifest leaves first
    aside: list[str] = []
    installed: list[str] = []
    created: list[Path] = []
    try:
        for relative in ordered:
            if _entry_kind(directory / relative) != "absent":
                (kept / relative).parent.mkdir(parents=True, exist_ok=True)
                os.replace(directory / relative, kept / relative)
                aside.append(relative)
        for relative in relatives:
            parent = (directory / relative).parent
            missing = [node for node in (parent, *parent.parents) if directory in node.parents
                       and _entry_kind(node) == "absent"]
            for node in reversed(missing):
                node.mkdir()
                created.append(node)
            os.replace(staging / relative, directory / relative)
            installed.append(relative)
        return read_activation_dataset(directory)
    except BaseException as error:
        try:
            for relative in reversed(installed):
                (directory / relative).unlink(missing_ok=True)
            for node in reversed(created):
                node.rmdir()
            for relative in reversed(aside):          # the old manifest returns last
                os.replace(kept / relative, directory / relative)
        except OSError as second:
            raise Refusal("incomplete",
                          f"the write to {directory} failed ({type(error).__name__}: {error}) and the previous "
                          f"files could not be moved back ({type(second).__name__}: {second}). They are in "
                          f"{kept}; the target has no complete dataset until they are moved back") from error
        raise


def write_activation_dataset(root: Path | str, *, model: Mapping[str, Any], layers: Mapping[int, np.ndarray],
                             samples: Mapping[str, np.ndarray], provenance: Mapping[str, Any],
                             dtype: str = "float32", activation_site: str = "resid_post",
                             layer_indexing: str = "transformer_blocks_zero_based",
                             allow_roots: Iterable[Path | str] = ()) -> ActivationDataset:
    """Write a complete dataset and return it, validated.

    ``layers`` maps a zero-based layer number to a ``[sample_count, hidden_size]`` array; every layer must have
    the same shape. ``samples`` must hold ``document_index``, ``position`` and ``token_id``. Values are cast to
    ``dtype`` (float16, float32 or float64; bfloat16 is read-only here) and written little-endian. Finiteness
    is checked on the cast values, so a float64 value that overflows float32 is refused (``non_finite``).

    The manifest records the SHA-256 and byte count of every layer file and of the samples file under
    ``provenance.patientwords_files``. The writer computes that block; a block of that name in ``provenance`` is
    replaced, never copied.

    Nothing is put in place until the whole dataset has passed this module's own validation. Every check on the
    arguments runs before a file is created. The files are then written to a staging directory inside the
    target (``.staging-*``), validated there with ``read_activation_dataset``, and moved into place, the
    manifest last (``_install``). A malformed argument is a ``Refusal``.

    What is guaranteed when the write does not complete:

    * A write that is refused, or that fails with an error, before the move into place leaves the target as it
      was: no new directory, no changed file, no staging directory.
    * A failure during the move into place that Python can handle (an I/O error on one file, an interrupt)
      puts the previous dataset back: the files that were replaced are kept inside the staging directory until
      every replacement has succeeded and the installed dataset has validated, and they are moved back
      otherwise. The previous dataset then reads byte for byte as before. If moving back fails as well, the
      staging directory is kept and the refusal (``incomplete``) names it.
    * A process that is killed during the move into place (or a power loss) runs no handler. The old manifest
      is moved away before any other file and the new manifest arrives last, so the target then has no
      ``activations.json``, and ``open_activation_dataset`` refuses the directory (``dataset_format``): a
      reader never sees a manifest beside files it was not written with. The files that had been replaced are
      under ``<target>/.staging-*/.replaced/`` with their relative names and can be moved back by hand. A kill
      after the new manifest is in place leaves the complete new dataset and a leftover staging directory.
      A later write to a target that holds a ``.staging-*`` directory is refused (``incomplete``) until a
      person has dealt with it. The moves are renames inside one directory tree; they are not fsynced, so
      nothing is claimed about what a power loss leaves on a filesystem that reorders them.

    A file of the previous dataset that the new dataset does not name (a layer the new one lacks) is left in
    place; the new manifest does not list it.

    The target must pass ``common.check_output_path``: never under a protected root, and inside a Git checkout
    only under a directory named in ``allow_roots``. The files are written only through real directories inside
    that target: a symbolic link at the target, at ``layers`` or at a destination file is refused
    (``protected_root``) before anything is created, because a move through it would land outside the path
    that was checked. This is a check of the entries right before the move, not a descriptor-relative write:
    a link that another process puts in place between the check and the move is not covered.
    """
    directory = check_output_path(root, allow_roots)
    require(isinstance(dtype, str) and dtype in LAYER_DTYPES, "dataset_format",
            f"this writer emits {sorted(LAYER_DTYPES)}; {dtype!r} is not one of them")
    require(isinstance(layers, Mapping) and bool(layers) and all(integer(layer) for layer in layers),
            "dataset_format", "layers must map non-negative integer layer numbers to arrays")
    require(isinstance(samples, Mapping) and isinstance(model, Mapping) and isinstance(provenance, Mapping)
            and text(activation_site) and text(layer_indexing), "dataset_format",
            "samples, model and provenance must be mappings; activation_site and layer_indexing must be text")
    try:
        arrays = {layer: np.asarray(value) for layer, value in layers.items()}
        sample_arrays = {name: np.asarray(value) for name, value in samples.items()}
    except (TypeError, ValueError) as exc:
        raise Refusal("dataset_format", f"a layer or a sample tensor is not an array: {exc}") from exc
    shapes = {array.shape for array in arrays.values()}
    require(len(shapes) == 1 and len(next(iter(shapes))) == 2 and min(next(iter(shapes))) >= 1,
            "dimension_mismatch", f"every layer must be one [sample_count, hidden_size] array; got {sorted(shapes)}")
    sample_count, hidden_size = (int(n) for n in next(iter(shapes)))
    layer_bytes: dict[str, bytes] = {}
    entries: dict[str, Any] = {}
    for layer in sorted(arrays):
        array = arrays[layer]
        require(array.dtype.kind == "f" and bool(np.isfinite(array).all()), "non_finite",
                f"layer {layer} must be a floating-point array of finite values")
        with np.errstate(over="ignore"):
            cast = np.ascontiguousarray(array, dtype=LAYER_DTYPES[dtype])
        # Checked again after the cast: 1e300 is finite as float64 and infinite as float32.
        require(bool(np.isfinite(cast).all()), "non_finite",
                f"layer {layer}: {int((~np.isfinite(cast)).sum())} values are not finite after the cast to {dtype}")
        relative = f"layers/layer_{layer:02d}.{dtype}.bin"
        layer_bytes[relative] = cast.tobytes()
        entries[str(layer)] = {"file": relative, "shape": [sample_count, hidden_size], "status": "complete"}
    missing = sorted(set(REQUIRED_SAMPLE_TENSORS) - set(sample_arrays))
    require(not missing, "dataset_format", f"samples lacks {missing}")
    sample_tensors = {}
    for name, tensor in sample_arrays.items():
        require(tensor.dtype.kind == "i" and tensor.ndim == 1 and tensor.shape[0] == sample_count,
                "dimension_mismatch", f"samples[{name!r}] must be a 1-D integer array of length {sample_count}")
        sample_tensors[name] = tensor.astype("<i8")
    samples_bytes = safetensors_bytes(sample_tensors)
    try:
        stored_provenance = json.loads(json.dumps(dict(provenance), allow_nan=False))
        stored_model = json.loads(json.dumps(dict(model), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise Refusal("dataset_format", f"provenance and model must be finite JSON: {exc}") from exc
    stored_provenance[FILES_KEY] = {
        "schema_version": FILES_SCHEMA,
        "samples": {"file": SAMPLES_NAME, "sha256": sha256_bytes(samples_bytes), "bytes": len(samples_bytes)},
        "layers": {key: {"file": entry["file"], "sha256": sha256_bytes(layer_bytes[entry["file"]]),
                         "bytes": len(layer_bytes[entry["file"]])} for key, entry in entries.items()},
    }
    manifest = {
        "format": FORMAT, "format_version": FORMAT_VERSION, "status": "complete", "model": stored_model,
        "activation_site": activation_site, "layer_indexing": layer_indexing,
        "sample_count": sample_count, "hidden_size": hidden_size, "dtype": dtype,
        "samples_file": SAMPLES_NAME, "layers": entries, "provenance": stored_provenance,
    }
    files = {**layer_bytes, SAMPLES_NAME: samples_bytes, MANIFEST_NAME: manifest_bytes(manifest)}  # manifest last

    _check_destinations(Path(root), directory, files)
    existed = directory.exists()
    if existed:
        partial = sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*.partial"))
        require(not partial, "incomplete", f"the target holds partial capture files: {partial}")
        stale = sorted(path.name for path in directory.glob(f"{STAGING_PREFIX}*"))
        require(not stale, "incomplete",
                f"the target holds {stale} from a write that did not finish. A {REPLACED_DIR} directory inside "
                "one holds the files that write had replaced; move them back or remove the directory, then "
                "write again")
    directory.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=directory, prefix=STAGING_PREFIX))
    try:
        for relative, data in files.items():
            atomic_write_bytes(staging / relative, data)
        read_activation_dataset(staging)
        # Checked again right before the target is changed: staging and validation took time.
        _check_destinations(Path(root), directory, files)
        written = _install(staging, directory, list(files))
    except BaseException as error:
        # _install keeps the staging directory only when it could not move the previous files back.
        if not (isinstance(error, Refusal) and error.code == "incomplete" and (staging / REPLACED_DIR).is_dir()
                and any(path.is_file() for path in (staging / REPLACED_DIR).rglob("*"))):
            shutil.rmtree(staging, ignore_errors=True)
        if not existed:
            for leftover in (directory / "layers", directory):
                if leftover.is_dir() and not any(leftover.iterdir()):
                    leftover.rmdir()
        raise
    # The files that were replaced were inside the staging directory until here: the installed dataset has
    # validated, so they go now.
    shutil.rmtree(staging)
    return written
