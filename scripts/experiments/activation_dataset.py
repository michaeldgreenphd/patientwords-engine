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

* ``dataset_format``      the manifest, the dtype or a container file is not what the format defines
* ``incomplete``          the dataset or one of its layers is not ``complete``, or a ``.partial`` file remains
* ``dimension_mismatch``  a layer file's byte count, a declared shape or a sample tensor's length is wrong
* ``non_finite``          a layer holds NaN or infinity
* ``row_alignment``       duplicate ``(document_index, position)`` rows, an unmapped document, a missing row, or
  a row whose token id differs from the protocol's token id at that position

Model and tokenizer identity are never invented. The format has no tokenizer field, so this module reads the
tokenizer from ``provenance.patientwords.tokenizer`` when a PatientWords writer put it there. A dataset that
lacks a full model revision or a tokenizer identity is read with ``identity.status == "unknown"``.

What the format cannot say: byte order (the reference writer emits native order; this module writes and reads
little-endian), the precision the model was loaded in, and the source text of a row.

Nothing here loads a model or opens a socket.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from scripts.experiments.common import (
    HEX40, Refusal, atomic_write_bytes, check_output_path, digest, integer, require, sha256_bytes, text,
)

FORMAT = "icalens.activations"
FORMAT_VERSION = 1
MANIFEST_NAME = "activations.json"
SAMPLES_NAME = "samples.safetensors"
REQUIRED_SAMPLE_TENSORS = ("document_index", "position", "token_id")
ROWS_SCHEMA = "patientwords.activation-rows/1"
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


def parse_safetensors(data: bytes, where: str = "safetensors") -> dict[str, np.ndarray]:
    """Decode a safetensors container. Every offset, shape and byte count is checked; nothing is trusted."""
    require(len(data) >= 8, "dataset_format", f"{where}: shorter than the 8-byte header length")
    (length,) = struct.unpack("<Q", data[:8])
    require(0 < length <= MAX_SAFETENSORS_HEADER and 8 + length <= len(data), "dataset_format",
            f"{where}: header length {length} does not fit the file")
    try:
        header = json.loads(data[8:8 + length].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise Refusal("dataset_format", f"{where}: header is not JSON: {exc}") from exc
    require(isinstance(header, dict), "dataset_format", f"{where}: header must be a JSON object")
    body = memoryview(data)[8 + length:]
    tensors: dict[str, np.ndarray] = {}
    spans: list[tuple[int, int, str]] = []
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        require(isinstance(entry, dict) and entry.get("dtype") in SAFETENSORS_DTYPES, "dataset_format",
                f"{where}: tensor {name!r} has a dtype outside {sorted(SAFETENSORS_DTYPES)}")
        shape, offsets = entry.get("shape"), entry.get("data_offsets")
        require(isinstance(shape, list) and all(integer(n) for n in shape) and isinstance(offsets, list)
                and len(offsets) == 2 and all(integer(n) for n in offsets), "dataset_format",
                f"{where}: tensor {name!r} needs an integer shape and two integer data_offsets")
        begin, end = offsets
        dtype = np.dtype(SAFETENSORS_DTYPES[entry["dtype"]])
        count = int(np.prod(shape, dtype=np.int64)) if shape else 1
        require(begin <= end <= len(body) and end - begin == count * dtype.itemsize, "dataset_format",
                f"{where}: tensor {name!r} spans bytes {begin}..{end}, which does not match shape {shape} of "
                f"{entry['dtype']} inside a {len(body)}-byte buffer")
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

    def layer(self, layer: int) -> np.ndarray:
        """One layer as a ``[sample_count, hidden_size]`` array in its stored dtype (bfloat16 as float32).

        Refuses ``dimension_mismatch`` when the file's byte count is not
        ``sample_count * hidden_size * itemsize`` and ``non_finite`` when a value is NaN or infinite.
        """
        entry = self.manifest["layers"].get(str(layer))
        require(entry is not None, "dimension_mismatch", f"layer {layer} is not in the dataset; it holds "
                f"{list(self.layers)}")
        path = self.root / entry["file"]
        expected = self.sample_count * self.hidden_size * ITEMSIZE[self.dtype]
        actual = path.stat().st_size if path.is_file() else -1
        require(actual == expected, "dimension_mismatch",
                f"layer {layer}: {entry['file']} has {actual} bytes; sample_count {self.sample_count} x "
                f"hidden_size {self.hidden_size} x {ITEMSIZE[self.dtype]} bytes is {expected}")
        raw = path.read_bytes()
        if self.dtype == "bfloat16":
            values = (np.frombuffer(raw, dtype="<u2").astype("<u4") << 16).view("<f4")
        else:
            values = np.frombuffer(raw, dtype=LAYER_DTYPES[self.dtype])
        values = values.reshape(self.sample_count, self.hidden_size).copy()
        require(bool(np.isfinite(values).all()), "non_finite",
                f"layer {layer}: {int((~np.isfinite(values)).sum())} values are NaN or infinite")
        return values

    def samples(self) -> dict[str, np.ndarray]:
        """The three required sample tensors as int64 arrays of length ``sample_count``, plus any extras."""
        path = self.root / self.manifest["samples_file"]
        tensors = read_safetensors(path)
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


def _check_manifest(manifest: Any, root: Path) -> None:
    require(isinstance(manifest, dict), "dataset_format", f"{MANIFEST_NAME} must hold a JSON object")
    require(manifest.get("format") == FORMAT and manifest.get("format_version") == FORMAT_VERSION,
            "dataset_format", f"expected format {FORMAT!r} version {FORMAT_VERSION}; got "
            f"{manifest.get('format')!r} version {manifest.get('format_version')!r}")
    require(manifest.get("dtype") in ITEMSIZE, "dataset_format",
            f"dtype must be one of {sorted(ITEMSIZE)}; got {manifest.get('dtype')!r}")
    require(integer(manifest.get("sample_count"), 1) and integer(manifest.get("hidden_size"), 1),
            "dataset_format", "sample_count and hidden_size must be positive integers")
    layers = manifest.get("layers")
    require(isinstance(layers, dict) and bool(layers), "dataset_format", "the dataset names no layers")
    for key, entry in layers.items():
        require(key.isdigit() and str(int(key)) == key and isinstance(entry, dict) and text(entry.get("file")),
                "dataset_format", f"layers[{key!r}] must be keyed by a decimal layer number and name a file")
        relative = Path(entry["file"])
        require(not relative.is_absolute() and ".." not in relative.parts, "dataset_format",
                f"layers[{key!r}].file must be a relative path inside the dataset: {entry['file']!r}")
    samples_file = manifest.get("samples_file")
    require(text(samples_file) and not Path(samples_file).is_absolute() and ".." not in Path(samples_file).parts,
            "dataset_format", "samples_file must be a relative path inside the dataset")
    require(isinstance(manifest.get("provenance"), dict), "dataset_format", "provenance must be a JSON object")
    require(manifest.get("model") is None or isinstance(manifest["model"], dict), "dataset_format",
            "model must be an object when present")
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


def open_activation_dataset(root: Path | str) -> ActivationDataset:
    """Open a dataset directory and check its manifest. Layer files and sample tensors are read on demand."""
    directory = Path(root).resolve()
    manifest_path = directory / MANIFEST_NAME
    require(manifest_path.is_file(), "dataset_format", f"no {MANIFEST_NAME} in {directory}")
    data = manifest_path.read_bytes()
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise Refusal("dataset_format", f"{MANIFEST_NAME} is not JSON: {exc}") from exc
    _check_manifest(manifest, directory)
    return ActivationDataset(root=directory, manifest=manifest, manifest_sha256=sha256_bytes(data))


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
        if entry["role"] == "protocol_variant":
            require(text(entry.get("family_id")) and text(entry.get("variant")), "row_alignment",
                    f"document {entry['document_index']}: a protocol_variant document names family_id and variant")
        else:
            require(text(entry.get("corpus_id")), "row_alignment",
                    f"document {entry['document_index']}: a fit_corpus document names its corpus_id")
        documents[entry["document_index"]] = entry
    return documents


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
    finiteness (unless ``check_values`` is false), the sample tensors' type and length, and duplicate
    ``(document_index, position)`` rows. With a PatientWords row map: every row belongs to a listed document.
    With ``protocol``: every ``protocol_variant`` document is checked row by row against the protocol's token
    ids. Identity is reported, never refused here: the caller decides what an unknown identity means.
    """
    dataset = root if isinstance(root, ActivationDataset) else open_activation_dataset(root)
    for layer in dataset.layers:
        if check_values:
            dataset.layer(layer)
        else:
            entry = dataset.manifest["layers"][str(layer)]
            path = dataset.root / entry["file"]
            expected = dataset.sample_count * dataset.hidden_size * ITEMSIZE[dataset.dtype]
            actual = path.stat().st_size if path.is_file() else -1
            require(actual == expected, "dimension_mismatch",
                    f"layer {layer}: {entry['file']} has {actual} bytes; expected {expected}")
    samples = dataset.samples()
    index = row_index(dataset, samples)
    report: dict[str, Any] = {
        "status": "validated", "format": FORMAT, "format_version": FORMAT_VERSION,
        "manifest_sha256": dataset.manifest_sha256, "sample_count": dataset.sample_count,
        "hidden_size": dataset.hidden_size, "dtype": dataset.dtype, "layers": list(dataset.layers),
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


def write_activation_dataset(root: Path | str, *, model: Mapping[str, Any], layers: Mapping[int, np.ndarray],
                             samples: Mapping[str, np.ndarray], provenance: Mapping[str, Any],
                             dtype: str = "float32", activation_site: str = "resid_post",
                             layer_indexing: str = "transformer_blocks_zero_based",
                             allow_roots: Iterable[Path | str] = ()) -> ActivationDataset:
    """Write a complete dataset and return it, validated.

    ``layers`` maps a zero-based layer number to a ``[sample_count, hidden_size]`` array; every layer must have
    the same shape. ``samples`` must hold ``document_index``, ``position`` and ``token_id``. Values are cast to
    ``dtype`` (float16, float32 or float64; bfloat16 is read-only here) and written little-endian. Layer files
    and the sample file are written first and the manifest last, each through a temporary file and
    ``os.replace``, so a reader never sees a manifest that points at a half-written layer.

    The target must pass ``common.check_output_path``: never under a protected root, and inside a Git checkout
    only under a directory named in ``allow_roots``.
    """
    directory = check_output_path(root, allow_roots)
    require(dtype in LAYER_DTYPES, "dataset_format",
            f"this writer emits {sorted(LAYER_DTYPES)}; {dtype!r} is not one of them")
    require(bool(layers) and all(integer(layer) for layer in layers), "dataset_format",
            "layers must map non-negative integer layer numbers to arrays")
    arrays = {layer: np.asarray(value) for layer, value in layers.items()}
    shapes = {array.shape for array in arrays.values()}
    require(len(shapes) == 1 and len(next(iter(shapes))) == 2 and min(next(iter(shapes))) >= 1,
            "dimension_mismatch", f"every layer must be one [sample_count, hidden_size] array; got {sorted(shapes)}")
    sample_count, hidden_size = next(iter(shapes))
    for layer, array in arrays.items():
        require(array.dtype.kind == "f" and bool(np.isfinite(array).all()), "non_finite",
                f"layer {layer} must be a floating-point array of finite values")
    missing = sorted(set(REQUIRED_SAMPLE_TENSORS) - set(samples))
    require(not missing, "dataset_format", f"samples lacks {missing}")
    sample_tensors = {}
    for name, value in samples.items():
        tensor = np.asarray(value)
        require(tensor.dtype.kind == "i" and tensor.ndim == 1 and tensor.shape[0] == sample_count,
                "dimension_mismatch", f"samples[{name!r}] must be a 1-D integer array of length {sample_count}")
        sample_tensors[name] = tensor.astype("<i8")
    try:
        stored_provenance = json.loads(json.dumps(provenance, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise Refusal("dataset_format", f"provenance must be finite JSON: {exc}") from exc
    entries = {}
    for layer in sorted(arrays):
        relative = f"layers/layer_{layer:02d}.{dtype}.bin"
        atomic_write_bytes(directory / relative,
                           np.ascontiguousarray(arrays[layer], dtype=LAYER_DTYPES[dtype]).tobytes())
        entries[str(layer)] = {"file": relative, "shape": [int(sample_count), int(hidden_size)],
                               "status": "complete"}
    write_safetensors(directory / SAMPLES_NAME, sample_tensors)
    manifest = {
        "format": FORMAT, "format_version": FORMAT_VERSION, "status": "complete", "model": dict(model),
        "activation_site": activation_site, "layer_indexing": layer_indexing,
        "sample_count": int(sample_count), "hidden_size": int(hidden_size), "dtype": dtype,
        "samples_file": SAMPLES_NAME, "layers": entries, "provenance": stored_provenance,
    }
    atomic_write_bytes(directory / MANIFEST_NAME, manifest_bytes(manifest))
    return read_activation_dataset(directory)
