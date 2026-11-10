"""Offline tests of the ActivationDataset reader/writer and the ICA adapter (numpy only).

Everything here is synthetic: a hand-written basis and hand-chosen activations. The expected numbers below are
literals worked out from ``B = [[1,1,0,0],[0,1,0,0],[0,0,1,2],[0,0,0,1]]``, ``center = [1,2,0,-1,0,0,0,0]`` and
``x = center + [B s ; t]`` (see ``tests/fixtures/experiments/ica/build_ica_fixtures.py``). A passing run shows
that the arithmetic and the refusals behave as specified on a toy. It shows nothing about a real model, a real
basis or parity with one; ``tests/test_experiments_ica_icalens.py`` compares against the ``icalens`` package.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import struct
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from scripts.experiments import adapters, capabilities, common, planner
from scripts.experiments import activation_dataset as ad
from scripts.experiments.adapters import ica
from scripts.experiments.common import Refusal, json_bytes, sha256_file
from scripts.experiments.envelope import null_pointers, validate_envelope
from scripts.experiments.store import RunStore

FX = Path(__file__).resolve().parent / "fixtures" / "experiments"
ICA = FX / "ica"
MANIFEST = ICA / "basis_manifest.json"
PAIRS = ICA / "pair_activations"
DISCOVERY = ICA / "discovery_activations"
LAYER_FILE = "artifacts/resid_post/layer_01.safetensors"

# Written out again here, not imported from the builder, so the expectations stand on their own.
B = np.array([[1, 1, 0, 0], [0, 1, 0, 0], [0, 0, 1, 2], [0, 0, 0, 1]], dtype=np.float64)
B_INVERSE = np.array([[1, -1, 0, 0], [0, 1, 0, 0], [0, 0, 1, -2], [0, 0, 0, 1]], dtype=np.float64)
CENTER = np.array([1, 2, 0, -1, 0, 0, 0, 0], dtype=np.float64)
WRITING = np.vstack([B, np.zeros((4, 4))])
READING = np.hstack([B_INVERSE, np.zeros((4, 4))])


def load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("build_ica_fixtures", ICA / "build_ica_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = load_builder()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def code_of(call: Callable[[], Any]) -> str:
    with pytest.raises(Refusal) as caught:
        call()
    return caught.value.code


@pytest.fixture(scope="module")
def matrix() -> dict:
    return capabilities.load_matrix()


def ica_protocol(manifest_path: Path = MANIFEST, **basis: Any) -> dict:
    """The synthetic protocol plus one ica_lens method that names the basis manifest at ``manifest_path``."""
    protocol = read(FX / "protocol_synthetic.json")
    method = copy.deepcopy(read(ICA / "fixture_index.json")["method_block"])
    method["basis"]["manifest_sha256"] = sha256_file(manifest_path)
    positions = basis.pop("positions", None)
    if positions:
        method["positions"] = positions
    method["basis"].update(basis)
    protocol["methods"].append(method)
    return protocol


def task_for(protocol: dict, matrix: dict, family: str, variant: str) -> dict:
    plan = planner.build_plan(protocol, matrix)
    return next(t for t in plan["tasks"] if (t["spec"]["family_id"], t["spec"]["variant"],
                                             t["spec"]["method"]["id"]) == (family, variant, "ica_lens"))


def score(matrix: dict, family: str, variant: str, *, manifest: Path = MANIFEST, pairs: Path = PAIRS,
          fit: Path | None = DISCOVERY, protocol: dict | None = None, path: str = "numpy", **basis: Any) -> dict:
    protocol = protocol or ica_protocol(manifest, **basis)
    return ica.score_task(task_for(protocol, matrix, family, variant), protocol, basis=ica.load_basis(manifest),
                          dataset=ad.open_activation_dataset(pairs),
                          fit_dataset=ad.open_activation_dataset(fit) if fit else None, path=path)


def values(payload: dict, key: str = "score") -> list:
    return [row[key] for row in payload["scores"]]


def make_basis(root: Path, *, reading: np.ndarray = READING, writing: np.ndarray = WRITING,
               center: np.ndarray = CENTER, mode: str = "none", pre_center: np.ndarray | None = None,
               saved: Callable[[dict], None] | None = None, edit: Callable[[dict], None] | None = None,
               fit: dict | None = None, annotations: list | None = None, basis_id: str = "fixture/other-basis",
               **stage: Any) -> Path:
    """Write a synthetic basis under ``root`` and return its manifest path.

    ``saved`` edits icalens.json before the manifest is built from it; ``edit`` edits the built manifest."""
    lens = root / "toy_basis"
    tensors = {"center": center.astype(np.float32), "reading_matrix": reading.astype(np.float32),
               "writing_matrix": writing.astype(np.float32)}
    if pre_center is not None:
        tensors["preprocessing_center"] = pre_center.astype(np.float32)
    ad.write_safetensors(lens / LAYER_FILE, tensors)
    artifact = BUILDER.toy_artifact_manifest(LAYER_FILE)
    artifact["input_preprocessing"] = {
        "icalens_preprocessing": mode, "row_normalization": "none" if mode == "none" else "l2",
        "pre_normalization_center": "geometric_median" if mode == "geometric-median-l2" else "none",
        "norm_eps": 1e-12}
    artifact["layers"]["1"]["n_components"] = int(reading.shape[0])
    if saved:
        saved(artifact)
    (lens / "icalens.json").write_bytes(json_bytes(artifact))
    manifest = ica.build_basis_manifest(
        lens, basis_id=basis_id, synthetic=True, artifact_root="toy_basis", description="SYNTHETIC test basis.",
        tokenizer_id="fixture/toy-tokenizer", tokenizer_revision="1" * 40,
        fit=fit or {"corpus_id": "toy-discovery-corpus-1", "split": "discovery",
                    "corpus_ids": ["toy-discovery-corpus-1"]},
        capture_site="block_output", layer_index_base=0, model_load_precision="not_applicable_no_model",
        component_annotations=annotations or [], **stage)
    if edit:
        edit(manifest)
    path = root / "basis_manifest.json"
    path.write_bytes(json_bytes(manifest))
    return path


def copy_fixtures(tmp_path: Path) -> Path:
    target = tmp_path / "fixtures"
    shutil.copytree(FX, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def rewrite_json(path: Path, edit: Callable[[dict], None]) -> None:
    doc = read(path)
    edit(doc)
    path.write_bytes(ad.manifest_bytes(doc) if path.name == "activations.json" else json_bytes(doc))


# -------------------------------------------------------------------------------------------- fixtures

def test_fixtures_are_marked_synthetic_and_regenerate_byte_for_byte(tmp_path: Path) -> None:
    index = BUILDER.build_all(tmp_path / "regenerated")
    committed = read(ICA / "fixture_index.json")
    assert index == committed and committed["synthetic"] is True
    for name, sha in committed["files"].items():
        assert sha256_file(ICA / name) == sha, name
        assert (tmp_path / "regenerated" / name).read_bytes() == (ICA / name).read_bytes(), name
    assert read(MANIFEST)["synthetic"] is True and "synthetic_not_measurement" in read(MANIFEST)["limitations"]
    assert read(ICA / "toy_basis" / "icalens.json")["synthetic"] is True
    for directory in (PAIRS, DISCOVERY):
        assert read(directory / "activations.json")["provenance"]["synthetic"] is True
    # The committed pair rows still match the protocol on disk, token id by token id.
    assert ad.validate_activation_dataset(PAIRS, protocol=read(FX / "protocol_synthetic.json"))[
        "protocol_variants_checked"] == 9


def test_layer_file_is_headerless_row_major_little_endian_and_rows_align_with_the_sample_tensors() -> None:
    """Decoded here with numpy.frombuffer and struct only, without the module under test."""
    manifest = read(PAIRS / "activations.json")
    assert (manifest["format"], manifest["format_version"]) == ("icalens.activations", 1)
    assert manifest["status"] == "complete"
    assert (manifest["sample_count"], manifest["hidden_size"], manifest["dtype"]) == (24, 8, "float32")
    assert manifest["layers"] == {"1": {"file": "layers/layer_01.float32.bin", "shape": [24, 8], "status": "complete"}}
    raw = (PAIRS / "layers" / "layer_01.float32.bin").read_bytes()
    assert len(raw) == 24 * 8 * 4
    layer = np.frombuffer(raw, dtype="<f4").reshape(24, 8)
    data = (PAIRS / "samples.safetensors").read_bytes()
    (length,) = struct.unpack("<Q", data[:8])
    header = json.loads(data[8:8 + length])
    assert length % 8 == 0 and sorted(header) == ["document_index", "position", "token_id"]
    columns = {}
    for name, entry in header.items():
        assert entry["dtype"] == "I64" and entry["shape"] == [24]
        begin, end = entry["data_offsets"]
        columns[name] = np.frombuffer(data[8 + length + begin:8 + length + end], dtype="<i8")
    # fam-1 normalized is document 2 with token ids [2, 4]; its last position holds x = [8,8,4,0,0,0,3,4].
    row = next(i for i in range(24) if (columns["document_index"][i], columns["position"][i]) == (2, 1))
    assert columns["token_id"][row] == 4 and layer[row].tolist() == [8, 8, 4, 0, 0, 0, 3, 4]
    assert layer[row].tolist() == (CENTER + np.concatenate([B @ [1, 6, 2, 1], [0, 0, 3, 4]])).tolist()
    # Rows are interleaved by position, so a row index is not a document offset.
    assert columns["document_index"][:9].tolist() == list(range(9)) and set(columns["position"][:9]) == {0}


def test_safetensors_container_bytes_and_order() -> None:
    raw = b'{"a":{"dtype":"I64","shape":[2],"data_offsets":[0,16]}}'
    padded = raw + b" " * (-len(raw) % 8)
    assert ad.safetensors_bytes({"a": np.array([1, 2], dtype=np.int64)}) == (
        struct.pack("<Q", len(padded)) + padded + struct.pack("<2q", 1, 2))
    mixed = ad.safetensors_bytes({"z": np.zeros((2, 3), dtype=np.float32), "b": np.array([7], dtype=np.int64),
                                  "a": np.ones(4, dtype=np.float32)})
    (length,) = struct.unpack("<Q", mixed[:8])
    header = json.loads(mixed[8:8 + length])
    # Descending dtype rank (I64 before F32), then name.
    assert list(header) == ["b", "a", "z"] and header["z"]["data_offsets"] == [24, 48]
    back = ad.parse_safetensors(mixed)
    assert back["b"].tolist() == [7] and back["z"].shape == (2, 3) and back["a"].dtype == np.dtype("<f4")


@pytest.mark.parametrize("damage", [
    lambda d: d[:5],
    lambda d: struct.pack("<Q", 10 ** 9) + d[8:],
    lambda d: d[:-8],                                             # tensor bytes cut short
    lambda d: d + b"\x00" * 8,                                    # bytes that belong to no tensor
    lambda d: d[:8] + d[8:].replace(b'"I64"', b'"X64"', 1),
    lambda d: d[:8] + d[8:].replace(b"[0,16]", b"[8,24]", 1),     # a gap before the first tensor
])
def test_a_damaged_safetensors_container_refuses(damage: Callable[[bytes], bytes]) -> None:
    good = ad.safetensors_bytes({"a": np.array([1, 2], dtype=np.int64), "b": np.array([3, 4], dtype=np.int64)})
    assert code_of(lambda: ad.parse_safetensors(damage(good))) == "dataset_format"


def crafted(header: dict, body: bytes = b"") -> bytes:
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    raw += b" " * (-len(raw) % 8)
    return struct.pack("<Q", len(raw)) + raw + body


@pytest.mark.parametrize("header,body", [
    # 2**32 * 2**32 is 2**64: zero in int64 arithmetic, so the byte-count check used to pass and reshape raised.
    ({"a": {"dtype": "I64", "shape": [2 ** 32, 2 ** 32], "data_offsets": [0, 0]}}, b""),
    ({"a": {"dtype": ["I64"], "shape": [1], "data_offsets": [0, 8]}}, b"\x00" * 8),      # unhashable dtype
    ({"a": {"dtype": "I64", "shape": [2 ** 70, 0], "data_offsets": [0, 0]}}, b""),       # a dimension no array holds
    ({"a": {"dtype": "I64", "shape": [1.0], "data_offsets": [0, 8]}}, b"\x00" * 8),
    ({"a": ["I64"]}, b""),
    ([], b""),
])
def test_a_malformed_safetensors_header_is_a_refusal_never_a_numpy_error(header: Any, body: bytes) -> None:
    assert code_of(lambda: ad.parse_safetensors(crafted(header, body))) == "dataset_format"


# ------------------------------------------------------------------------------------- activation dataset

def toy_write(root: Path, **changes: Any) -> ad.ActivationDataset:
    source = ad.open_activation_dataset(PAIRS)
    arguments = {"model": source.manifest["model"], "layers": {1: source.layer(1)}, "samples": source.samples(),
                 "provenance": source.manifest["provenance"], "dtype": "float32"}
    arguments.update(changes)
    return ad.write_activation_dataset(root, **arguments)


def test_write_then_read_round_trip_and_report(tmp_path: Path) -> None:
    protocol = read(FX / "protocol_synthetic.json")
    written = toy_write(tmp_path / "copy")
    for name in ("activations.json", "samples.safetensors", "layers/layer_01.float32.bin"):
        assert (tmp_path / "copy" / name).read_bytes() == (PAIRS / name).read_bytes()
    report = ad.validate_activation_dataset(written, protocol=protocol)
    assert report["status"] == "validated" and report["protocol_alignment"] == "checked"
    assert report["protocol_variants_checked"] == 9 and report["documents_by_split"] == {
        "discovery": 3, "validation": 3, "fresh_test": 3}
    assert report["identity"] == {
        "model_id": "fixture/toy-model", "model_revision": "1" * 40, "tokenizer_id": "fixture/toy-tokenizer",
        "tokenizer_revision": "1" * 40, "model_type": "base", "status": "recorded", "unknown_fields": [],
        "parity": "not_established"}
    assert written.manifest_sha256 == sha256_file(PAIRS / "activations.json")
    rows = ad.variant_rows(written, protocol, "fam-2", "clinical")
    assert [(r["position"], r["token_id"]) for r in rows] == [(0, 0), (1, 1), (2, 4)]
    discovery = ad.read_activation_dataset(DISCOVERY)
    assert (discovery.sample_count, discovery.hidden_size, discovery.layers) == (48, 8, (1,))
    assert np.linalg.matrix_rank(discovery.layer(1) - discovery.layer(1).mean(axis=0)) == 8


@pytest.mark.parametrize("dtype,code", [("float16", "<f2"), ("float64", "<f8")])
def test_other_dtypes_round_trip(tmp_path: Path, dtype: str, code: str) -> None:
    written = toy_write(tmp_path / dtype, dtype=dtype)
    raw = np.frombuffer((tmp_path / dtype / f"layers/layer_01.{dtype}.bin").read_bytes(), dtype=code)
    assert raw.size == 24 * 8 and written.layer(1).dtype == np.dtype(code)
    assert np.array_equal(written.layer(1), ad.open_activation_dataset(PAIRS).layer(1))


def test_bfloat16_is_decoded_on_read_and_not_written(tmp_path: Path) -> None:
    # bfloat16 is the high 16 bits of a float32: 1.0 = 0x3F80, -2.0 = 0xC000, 0.5 = 0x3F00, 0.0 = 0x0000.
    root = tmp_path / "bf16"
    (root / "layers").mkdir(parents=True)
    (root / "layers" / "layer_00.bfloat16.bin").write_bytes(struct.pack("<4H", 0x3F80, 0xC000, 0x3F00, 0x0000))
    (root / "samples.safetensors").write_bytes(ad.safetensors_bytes(
        {name: np.array([0, 1], dtype=np.int64) for name in ad.REQUIRED_SAMPLE_TENSORS}))
    (root / "activations.json").write_bytes(ad.manifest_bytes({
        "format": "icalens.activations", "format_version": 1, "status": "complete", "sample_count": 2,
        "hidden_size": 2, "dtype": "bfloat16", "samples_file": "samples.safetensors",
        "model": {"repo_id": "fixture/toy-model", "type": "base"}, "provenance": {"synthetic": True},
        "layers": {"0": {"file": "layers/layer_00.bfloat16.bin", "shape": [2, 2], "status": "complete"}}}))
    dataset = ad.open_activation_dataset(root)
    assert dataset.layer(0).tolist() == [[1.0, -2.0], [0.5, 0.0]]
    assert code_of(lambda: toy_write(tmp_path / "out", dtype="bfloat16")) == "dataset_format"


def test_missing_identity_is_recorded_as_unknown_and_never_filled_in(tmp_path: Path) -> None:
    shutil.copytree(PAIRS, tmp_path / "no_revision")
    rewrite_json(tmp_path / "no_revision" / "activations.json", lambda d: d["model"].pop("revision"))
    identity = ad.read_activation_dataset(tmp_path / "no_revision").identity
    assert identity["status"] == "unknown" and identity["unknown_fields"] == ["model_revision"]
    assert identity["model_revision"] is None and identity["parity"] == "not_established"
    shutil.copytree(PAIRS, tmp_path / "placeholder")
    rewrite_json(tmp_path / "placeholder" / "activations.json", lambda d: d["model"].update(revision="unknown"))
    assert ad.open_activation_dataset(tmp_path / "placeholder").identity["unknown_fields"] == ["model_revision"]
    shutil.copytree(PAIRS, tmp_path / "no_tokenizer")
    rewrite_json(tmp_path / "no_tokenizer" / "activations.json",
                 lambda d: d["provenance"]["patientwords"].pop("tokenizer"))
    identity = ad.open_activation_dataset(tmp_path / "no_tokenizer").identity
    assert identity["status"] == "unknown" and identity["unknown_fields"] == ["tokenizer_id", "tokenizer_revision"]


def repin(root: Path) -> None:
    """Record the file hashes again after a deliberate edit, as a writer that produced these bytes would have.

    The damage cases below aim at the checks that sit behind the pin check (finiteness, row alignment). Without
    this step every one of them is refused earlier, as ``artifact_hash``: see
    ``test_file_pins_detect_changed_layer_and_sample_bytes``. The hashes are computed with hashlib here, not
    with the module under test."""
    def edit(doc: dict) -> None:
        pins = doc["provenance"].get("patientwords_files")
        for entry in [pins["samples"], *pins["layers"].values()] if pins else []:
            data = (root / entry["file"]).read_bytes()
            entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    rewrite_json(root / "activations.json", edit)


def samples_with(edit: Callable[[dict], None], pinned: bool = True) -> Callable[[Path], None]:
    def apply(root: Path) -> None:
        tensors = ad.read_safetensors(root / "samples.safetensors")
        edit(tensors)
        (root / "samples.safetensors").write_bytes(ad.safetensors_bytes(tensors))
        if pinned:
            repin(root)
    return apply


def set_value(name: str, row: int, value: int) -> Callable[[dict], None]:
    def edit(tensors: dict) -> None:
        tensors[name][row] = value
    return edit


def truncate_layer(root: Path) -> None:
    path = root / "layers" / "layer_01.float32.bin"
    path.write_bytes(path.read_bytes()[:-4])


def poison_layer(root: Path) -> None:
    path = root / "layers" / "layer_01.float32.bin"
    values = np.frombuffer(path.read_bytes(), dtype="<f4").copy()
    values[5] = np.nan
    path.write_bytes(values.tobytes())
    repin(root)


def reverse_layer_rows(root: Path) -> None:
    """Reverse the row order of the layer file: the same size, finite values, the manifest untouched."""
    path = root / "layers" / "layer_01.float32.bin"
    path.write_bytes(np.frombuffer(path.read_bytes(), dtype="<f4").reshape(24, 8)[::-1].tobytes())


def manifest_with(edit: Callable[[dict], None]) -> Callable[[Path], None]:
    return lambda root: rewrite_json(root / "activations.json", edit)


DATASET_REFUSALS = [
    (manifest_with(lambda d: d.update(status="capturing")), "incomplete", "not 'complete'"),
    (manifest_with(lambda d: d["layers"]["1"].update(status="pending")), "incomplete", "not marked complete"),
    (lambda root: (root / "layers" / "layer_01.float32.bin.partial").write_bytes(b""), "incomplete", "partial"),
    (truncate_layer, "dimension_mismatch", "764 bytes"),
    (manifest_with(lambda d: d["layers"]["1"].update(shape=[24, 7])), "dimension_mismatch", "shape"),
    (manifest_with(lambda d: d.update(sample_count=23)), "dimension_mismatch", "shape"),
    (samples_with(lambda t: t.update(position=t["position"][:-1])), "dimension_mismatch", "position has shape"),
    (poison_layer, "non_finite", "NaN or infinite"),
    (samples_with(set_value("position", 9, 0)), "row_alignment", "duplicate row"),
    (samples_with(set_value("token_id", 0, 3)), "row_alignment", "holds token id 3"),
    (samples_with(set_value("document_index", 0, 40)), "row_alignment", "does not list"),
    (manifest_with(lambda d: d["provenance"]["patientwords"]["documents"][0].update(variant="colloquial")),
     "row_alignment", "exactly one is required"),
    (manifest_with(lambda d: d["provenance"]["patientwords"]["documents"][0].update(split="validation")),
     "row_alignment", "split"),
    (manifest_with(lambda d: d.update(format_version=2)), "dataset_format", "version"),
    (manifest_with(lambda d: d.update(dtype="int8")), "dataset_format", "dtype"),
    (lambda root: (root / "samples.safetensors").unlink(), "dataset_format", "not a file"),
    # Malformed inputs that used to raise TypeError or ValueError.
    (manifest_with(lambda d: d.update(dtype=["float32"])), "dataset_format", "dtype"),
    (manifest_with(lambda d: d["layers"].update({"\u00b2": d["layers"].pop("1")})), "dataset_format",
     "ASCII decimal layer number"),
    (manifest_with(lambda d: d.update(layers=[1])), "dataset_format", "names no layers"),
    (manifest_with(lambda d: d.update(sample_count=2 ** 70)), "dimension_mismatch", "shape"),
    # File pins: a changed file, and a pin block that is present but leaves a file out.
    (reverse_layer_rows, "artifact_hash", "layer 1"),
    (samples_with(set_value("token_id", 0, 3), pinned=False), "artifact_hash", "samples"),
    (manifest_with(lambda d: d["provenance"]["patientwords_files"]["layers"].clear()), "dataset_format",
     "every layer file"),
    (manifest_with(lambda d: d["provenance"].update(patientwords_files=None)), "dataset_format",
     "patientwords_files"),
    (manifest_with(lambda d: d["provenance"]["patientwords_files"]["samples"].update(sha256="abc")),
     "dataset_format", "samples"),
]


@pytest.mark.parametrize("damage,code,detail", DATASET_REFUSALS)
def test_dataset_validation_refusals(tmp_path: Path, damage: Callable[[Path], None], code: str, detail: str) -> None:
    root = tmp_path / "pairs"
    shutil.copytree(PAIRS, root)
    damage(root)
    protocol = read(FX / "protocol_synthetic.json")
    with pytest.raises(Refusal) as caught:
        ad.read_activation_dataset(root, protocol=protocol)
    assert caught.value.code == code and detail in str(caught.value)


def test_a_missing_row_is_detected(tmp_path: Path) -> None:
    source = ad.open_activation_dataset(PAIRS)
    samples = source.samples()
    # Drop the last-position row of fam-1 clinical (document 0, position 1).
    keep = [i for i in range(24) if (samples["document_index"][i], samples["position"][i]) != (0, 1)]
    root = tmp_path / "short"
    with pytest.raises(Refusal) as caught:
        ad.write_activation_dataset(root, model=source.manifest["model"], layers={1: source.layer(1)[keep]},
                                    samples={k: v[keep] for k, v in samples.items()},
                                    provenance=source.manifest["provenance"])
        ad.read_activation_dataset(root, protocol=read(FX / "protocol_synthetic.json"))
    assert caught.value.code == "row_alignment" and "no activation row for positions [1]" in str(caught.value)


def test_writer_refuses_protected_roots_and_git_checkouts(tmp_path: Path) -> None:
    assert code_of(lambda: toy_write(tmp_path / "trace_out" / "x")) == "protected_root"
    inside = Path(__file__).resolve().parent / "fixtures" / "experiments" / "ica" / "never_written"
    assert code_of(lambda: toy_write(inside)) == "git_checkout" and not inside.exists()
    assert code_of(lambda: toy_write(tmp_path / "bad", layers={1: np.zeros((24, 8), dtype=np.int64)})) == "non_finite"


def test_the_writer_records_file_pins_and_a_dataset_without_them_is_reported_as_not_recorded(
        tmp_path: Path, matrix: dict) -> None:
    written = toy_write(tmp_path / "copy")
    pins = written.manifest["provenance"]["patientwords_files"]
    assert pins == {"schema_version": "patientwords.activation-files/1",
                    "samples": {"file": "samples.safetensors", "bytes": 784,
                                "sha256": hashlib.sha256((PAIRS / "samples.safetensors").read_bytes()).hexdigest()},
                    "layers": {"1": {"file": "layers/layer_01.float32.bin", "bytes": 768, "sha256": hashlib.sha256(
                        (PAIRS / "layers" / "layer_01.float32.bin").read_bytes()).hexdigest()}}}
    report = ad.validate_activation_dataset(written)
    assert report["file_pins"] == "verified" and report["layer_sha256"] == {"1": pins["layers"]["1"]["sha256"]}
    # A pin block handed in with the provenance is replaced by the writer's own, never copied.
    stale = copy.deepcopy(written.manifest["provenance"])
    stale["patientwords_files"]["layers"]["1"]["sha256"] = "0" * 64
    assert toy_write(tmp_path / "again", provenance=stale).manifest["provenance"]["patientwords_files"] == pins

    # A dataset whose manifest has no pins (what the reference writer produces) is accepted. The absence is
    # reported; nothing is written back into the manifest.
    shutil.copytree(PAIRS, tmp_path / "unpinned")
    rewrite_json(tmp_path / "unpinned" / "activations.json", lambda d: d["provenance"].pop("patientwords_files"))
    before = (tmp_path / "unpinned" / "activations.json").read_bytes()
    report = ad.validate_activation_dataset(tmp_path / "unpinned", protocol=read(FX / "protocol_synthetic.json"))
    assert report["file_pins"] == "not_recorded" and ad.open_activation_dataset(tmp_path / "unpinned").file_pins is None
    payload = score(matrix, "fam-2", "clinical", pairs=tmp_path / "unpinned")
    assert payload["capture"]["activation_dataset"]["file_pins"] == "not_recorded"
    assert (tmp_path / "unpinned" / "activations.json").read_bytes() == before
    # Without pins a changed layer file cannot be refused. The payload still differs in identity: it records
    # the SHA-256 of the bytes it read.
    reverse_layer_rows(tmp_path / "unpinned")
    changed = score(matrix, "fam-2", "clinical", pairs=tmp_path / "unpinned")
    assert values(changed) != values(payload)
    assert changed["capture"]["activation_dataset"]["manifest_sha256"] == payload["capture"]["activation_dataset"][
        "manifest_sha256"]
    assert changed["capture"]["activation_dataset"]["layer_sha256"] != payload["capture"]["activation_dataset"][
        "layer_sha256"]


def test_file_pins_detect_changed_layer_and_sample_bytes(tmp_path: Path, matrix: dict) -> None:
    """The reviewer's case: reverse the rows of the layer file, leave activations.json and samples untouched.
    Byte count, finiteness, row map and token ids all still hold; before the pins this scored other numbers
    under identical identity fields."""
    baseline = score(matrix, "fam-2", "clinical")
    assert values(baseline) == [2.0, 0.0, 0.0, -1.0]
    assert baseline["capture"]["activation_dataset"] == {
        "manifest_sha256": sha256_file(PAIRS / "activations.json"), "dtype": "float32", "sample_count": 24,
        "file_pins": "verified",
        "samples_sha256": hashlib.sha256((PAIRS / "samples.safetensors").read_bytes()).hexdigest(),
        "layer_sha256": {"1": hashlib.sha256((PAIRS / "layers" / "layer_01.float32.bin").read_bytes()).hexdigest()}}
    shutil.copytree(PAIRS, tmp_path / "reversed")
    reverse_layer_rows(tmp_path / "reversed")
    assert sha256_file(tmp_path / "reversed" / "activations.json") == sha256_file(PAIRS / "activations.json")
    with pytest.raises(Refusal) as caught:
        score(matrix, "fam-2", "clinical", pairs=tmp_path / "reversed")
    assert caught.value.code == "artifact_hash" and "layers/layer_01.float32.bin" in str(caught.value)
    assert code_of(lambda: ad.open_activation_dataset(tmp_path / "reversed").layer(1)) == "artifact_hash"
    assert code_of(lambda: ad.validate_activation_dataset(tmp_path / "reversed", check_values=False)) == (
        "artifact_hash")
    shutil.copytree(PAIRS, tmp_path / "samples")
    samples_with(lambda t: t.update(token_id=t["token_id"][::-1].copy()), pinned=False)(tmp_path / "samples")
    assert code_of(lambda: ad.open_activation_dataset(tmp_path / "samples").samples()) == "artifact_hash"
    # The fit dataset is verified too: its manifest hash is what the basis manifest names.
    shutil.copytree(DISCOVERY, tmp_path / "fit")
    path = tmp_path / "fit" / "layers" / "layer_01.float32.bin"
    path.write_bytes(np.frombuffer(path.read_bytes(), dtype="<f4").reshape(48, 8)[::-1].tobytes())
    assert code_of(lambda: score(matrix, "fam-2", "clinical", fit=tmp_path / "fit")) == "artifact_hash"


def test_a_refused_write_leaves_no_dataset_on_disk(tmp_path: Path) -> None:
    source = ad.open_activation_dataset(PAIRS)
    huge = source.layer(1).astype(np.float64)
    huge[3, 2] = 1e300                               # finite as float64, infinite once cast to float32
    with pytest.raises(Refusal) as caught:
        toy_write(tmp_path / "overflow", layers={1: huge})
    assert caught.value.code == "non_finite" and "after the cast to float32" in str(caught.value)
    assert not (tmp_path / "overflow").exists()
    assert toy_write(tmp_path / "wide", layers={1: huge}, dtype="float64").layer(1)[3, 2] == 1e300

    # A dataset that only the closing validation refuses (a duplicate row) is not left behind either.
    samples = source.samples()
    samples["position"][9] = 0
    assert code_of(lambda: toy_write(tmp_path / "duplicate", samples=samples)) == "row_alignment"
    assert not (tmp_path / "duplicate").exists()

    # A refused write over an existing dataset leaves that dataset as it was, byte for byte.
    good = toy_write(tmp_path / "kept")
    before = {path.relative_to(good.root).as_posix(): path.read_bytes()
              for path in sorted(good.root.rglob("*")) if path.is_file()}
    assert code_of(lambda: toy_write(tmp_path / "kept", samples=samples)) == "row_alignment"
    assert code_of(lambda: toy_write(tmp_path / "kept", layers={1: huge})) == "non_finite"
    after = {path.relative_to(good.root).as_posix(): path.read_bytes()
             for path in sorted(good.root.rglob("*")) if path.is_file()}
    assert after == before and sorted(before) == ["activations.json", "layers/layer_01.float32.bin",
                                                  "samples.safetensors"]
    assert not [path for path in good.root.rglob("*") if path.name.startswith(".staging-")]
    # An accepted write over it replaces all three files, and the result validates.
    replaced = toy_write(tmp_path / "kept", dtype="float32", activation_site="mlp_out")
    assert replaced.manifest["activation_site"] == "mlp_out"
    assert ad.validate_activation_dataset(replaced)["file_pins"] == "verified"


def tree(root: Path) -> dict[str, bytes]:
    """Every regular file under ``root`` (links followed, as a reader would) by relative name."""
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*"))
            if path.is_file()}


def test_the_writer_refuses_to_write_through_a_symbolic_link_inside_the_target(tmp_path: Path) -> None:
    """Review, 2026-11-10: with ``layers`` a link to another directory, ``mkdir(exist_ok=True)`` accepted it and
    ``os.replace`` moved the layer file to the directory the link names, which no path rule had checked."""
    # A scratch directory named like a protected root, holding a file that must stay as it is.
    outside = tmp_path / "elsewhere" / "trace_out"
    outside.mkdir(parents=True)
    (outside / "layer_01.float32.bin").write_bytes(b"a landed measurement")
    assert common.protected_root(outside) == "trace_out" and common.protected_root(tmp_path / "target") is None

    # 1. An existing dataset whose layers directory was replaced by a link to that directory.
    target = toy_write(tmp_path / "target").root
    kept = (target / "layers" / "layer_01.float32.bin").read_bytes()
    shutil.rmtree(target / "layers")
    (target / "layers").symlink_to(outside, target_is_directory=True)
    before = tree(target)
    with pytest.raises(Refusal) as caught:
        toy_write(target, activation_site="mlp_out")
    assert caught.value.code == "protected_root" and "symbolic link" in str(caught.value)
    assert tree(outside) == {"layer_01.float32.bin": b"a landed measurement"}       # nothing went through the link
    assert tree(target) == before and (target / "layers").is_symlink()
    assert not list(target.glob(".staging-*")) and kept != b"a landed measurement"

    # 2. A directory that holds only the link, and a link that points at nothing.
    for name, destination in (("bare", outside), ("dangling", tmp_path / "absent")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "layers").symlink_to(destination, target_is_directory=True)
        assert code_of(lambda: toy_write(tmp_path / name)) == "protected_root", name
        assert sorted(path.name for path in (tmp_path / name).iterdir()) == ["layers"], name
        assert not (tmp_path / "absent").exists()
    assert tree(outside) == {"layer_01.float32.bin": b"a landed measurement"}

    # 3. A link at a destination file, and a link at the target itself.
    for name in ("samples.safetensors", "activations.json", "layers/layer_01.float32.bin"):
        linked = toy_write(tmp_path / f"file_{name.split('/')[-1]}").root
        (linked / name).unlink()
        (linked / name).symlink_to(outside / "layer_01.float32.bin")
        assert code_of(lambda: toy_write(linked)) == "protected_root", name
        assert (linked / name).is_symlink() and not list(linked.glob(".staging-*"))
    real = toy_write(tmp_path / "real").root
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    before = tree(real)
    assert code_of(lambda: toy_write(tmp_path / "alias", activation_site="mlp_out")) == "protected_root"
    assert tree(real) == before and tree(outside) == {"layer_01.float32.bin": b"a landed measurement"}
    # 4. An entry of another kind in the way is named as such, and the path rules themselves are unchanged.
    blocked = toy_write(tmp_path / "blocked").root
    (blocked / "samples.safetensors").unlink()
    (blocked / "samples.safetensors").mkdir()
    assert code_of(lambda: toy_write(blocked)) == "dataset_format"
    (tmp_path / "plain_file").write_bytes(b"x")
    assert code_of(lambda: toy_write(tmp_path / "plain_file")) == "dataset_format"
    assert ad.validate_activation_dataset(toy_write(real, activation_site="mlp_out"))["activation_site"] == "mlp_out"


def failing_replace(monkeypatch: pytest.MonkeyPatch, fail_from: int, error: BaseException, only: int | None = None
                    ) -> list[int]:
    """Make the Nth move of the install step raise (and every later one, unless ``only`` says how many).

    ``atomic_write_bytes`` also calls ``os.replace``, from a temporary file whose name ends in ``.tmp``; those
    calls write the staged files and are let through uncounted."""
    real_replace, calls = ad.os.replace, [0]

    def replace(source: Any, destination: Any, **keywords: Any) -> None:
        if str(source).endswith(".tmp"):
            return real_replace(source, destination, **keywords)
        calls[0] += 1
        if calls[0] >= fail_from and (only is None or calls[0] < fail_from + only):
            raise error
        return real_replace(source, destination, **keywords)
    monkeypatch.setattr(ad.os, "replace", replace)
    return calls


class CountedReplace:
    """``os.replace`` with a count of the install step's moves (see ``failing_replace``)."""

    def __init__(self, real_replace: Callable[..., None]) -> None:
        self.real_replace, self.moves = real_replace, 0

    def __call__(self, source: Any, destination: Any, **keywords: Any) -> None:
        self.moves += 0 if str(source).endswith(".tmp") else 1
        return self.real_replace(source, destination, **keywords)


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("error", [OSError(28, "No space left on device"), KeyboardInterrupt()])
def test_a_failed_overwrite_puts_the_previous_dataset_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                           fail_at: int, error: BaseException) -> None:
    """Review, 2026-11-10: the old manifest was unlinked and the files were replaced one by one, so an I/O error
    after the first step left the previous dataset destroyed and the target holding a mixture.

    Overwriting a three-file dataset takes six moves: three old files aside (the manifest first), three new
    files in (the manifest last). Each of the six is made to fail here once."""
    good = toy_write(tmp_path / "kept")
    before = tree(good.root)
    assert sorted(before) == ["activations.json", "layers/layer_01.float32.bin", "samples.safetensors"]
    calls = failing_replace(monkeypatch, fail_at, error, only=1)
    original = good.layer(1)
    doubled = {1: original * 2}                                      # other layer bytes under the same file name
    with pytest.raises(type(error)):
        toy_write(tmp_path / "kept", activation_site="mlp_out", layers=doubled)
    monkeypatch.undo()
    assert calls[0] >= fail_at                                       # the injected failure was reached
    assert tree(good.root) == before                                 # byte for byte, and no other file
    assert not list(good.root.glob(".staging-*")) and not list(good.root.rglob(".replaced"))
    report = ad.validate_activation_dataset(tmp_path / "kept")
    assert report["file_pins"] == "verified" and report["manifest_sha256"] == good.manifest_sha256
    assert report["activation_site"] == "resid_post" and report["dtype"] == "float32"
    # The same write then succeeds, in all six moves.
    monkeypatch.setattr(ad.os, "replace", counted := CountedReplace(ad.os.replace))
    replaced = toy_write(tmp_path / "kept", activation_site="mlp_out", layers=doubled)
    assert counted.moves == 6 and replaced.manifest["activation_site"] == "mlp_out"
    assert np.array_equal(replaced.layer(1), original * 2) and not list(replaced.root.glob(".staging-*"))


def test_a_failed_first_write_leaves_no_directory_and_a_failed_restore_keeps_the_old_files(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A new target: three moves in. A failure at any of them leaves nothing behind.
    for fail_at in (1, 2, 3):
        failing_replace(monkeypatch, fail_at, OSError(5, "Input/output error"), only=1)
        with pytest.raises(OSError):
            toy_write(tmp_path / "fresh")
        monkeypatch.undo()
        assert not (tmp_path / "fresh").exists(), fail_at

    # The disk keeps failing, so the old files cannot be moved back either. They stay in the staging directory,
    # the refusal names it, the target has no manifest and no reader accepts it, and a later write is refused.
    good = toy_write(tmp_path / "kept")
    before = tree(good.root)
    failing_replace(monkeypatch, 5, OSError(5, "Input/output error"))
    with pytest.raises(Refusal) as caught:
        toy_write(tmp_path / "kept", activation_site="mlp_out")
    monkeypatch.undo()
    assert caught.value.code == "incomplete" and ".replaced" in str(caught.value)
    staging = list(good.root.glob(".staging-*"))
    assert len(staging) == 1 and tree(staging[0] / ".replaced") == before
    assert not (good.root / "activations.json").exists()
    assert code_of(lambda: ad.open_activation_dataset(good.root)) == "dataset_format"
    with pytest.raises(Refusal) as again:
        toy_write(tmp_path / "kept")
    assert again.value.code == "incomplete" and "did not finish" in str(again.value)
    # Moved back by hand, the previous dataset is whole again.
    for relative in before:
        (staging[0] / ".replaced" / relative).replace(good.root / relative)
    shutil.rmtree(staging[0])
    assert tree(good.root) == before and ad.validate_activation_dataset(good.root)["file_pins"] == "verified"


@pytest.mark.parametrize("changes", [
    {"layers": {1: [[1.0, 2.0], [3.0]]}},            # ragged rows
    {"layers": {"1": np.zeros((24, 8), dtype=np.float32)}},
    {"layers": []},
    {"samples": [1, 2, 3]},
    {"model": "fixture/toy-model"},
    {"provenance": {"when": object()}},
    {"provenance": {"value": float("nan")}},
    {"dtype": ["float32"]},
    {"activation_site": None},
])
def test_malformed_writer_arguments_are_refusals(tmp_path: Path, changes: dict) -> None:
    assert code_of(lambda: toy_write(tmp_path / "bad", **changes)) in ("dataset_format", "dimension_mismatch")
    assert not (tmp_path / "bad").exists()


# ------------------------------------------------------------------------------ hand-computed expectations

def test_signed_scores_shares_and_reconstruction_match_the_hand_computed_values(matrix: dict) -> None:
    clinical, colloquial, normalized = (score(matrix, "fam-1", name) for name in ("clinical", "colloquial",
                                                                                 "normalized"))
    assert values(clinical) == [3.0, -4.0, 0.0, 0.0]
    assert values(colloquial) == [-3.0, 4.0, 0.0, 0.0]            # every sign flipped
    assert values(clinical, "energy_share") == values(colloquial, "energy_share") == [0.36, 0.64, 0.0, 0.0]
    assert values(normalized) == [1.0, 6.0, 2.0, 1.0]
    assert values(normalized, "energy_share") == pytest.approx([1 / 42, 36 / 42, 4 / 42, 1 / 42], abs=1e-15)
    assert sum(values(normalized, "energy_share")) == pytest.approx(1.0, abs=1e-15)
    for payload in (clinical, colloquial):
        (row,) = payload["reconstruction"]["rows"]
        assert row["l2_error"] == 0.0 and row["relative_l2_error"] == 0.0 and row["cosine"] == pytest.approx(1.0)
    (row,) = normalized["reconstruction"]["rows"]
    assert row["preprocessed_l2_norm"] == 13.0 and row["l2_error"] == 5.0
    assert row["relative_l2_error"] == pytest.approx(5 / 13, abs=1e-15)
    assert row["cosine"] == pytest.approx(12 / 13, abs=1e-15)
    assert normalized["reconstruction"]["space"] == "preprocessed"
    assert normalized["reconstruction"]["restore_norm"].startswith("not_applied")
    assert normalized["rows"] == [{"position": 1, "token_id": 4, "document_index": 2, "dataset_row": 11}]
    assert normalized["energy_share"]["label"] == "squared-coordinate share, not a probability, not an importance"
    assert normalized["basis"]["sign_convention"] == (
        "as saved; not canonicalized; not comparable across fits, layers or models")


def test_an_all_zero_score_row_has_undefined_shares_recorded_as_null_not_zero(matrix: dict) -> None:
    payload = score(matrix, "fam-2", "colloquial")
    assert values(payload) == [0.0, 0.0, 0.0, 0.0] and values(payload, "energy_share") == [None] * 4
    assert payload["energy_share"]["rows"] == [
        {"layer": 1, "position": 2, "status": "not_computed_zero_energy", "total_squared": 0.0}]
    # x equals the center here, so the reconstruction is exact and its direction is defined.
    assert payload["reconstruction"]["rows"][0]["l2_error"] == 0.0


def test_all_positions_are_scored_when_the_method_asks_for_them(matrix: dict) -> None:
    payload = score(matrix, "fam-2", "normalized", positions="all")
    assert [row["position"] for row in payload["rows"]] == [0, 1, 2]
    by_position = {p: [r["score"] for r in payload["scores"] if r["position"] == p] for p in (0, 1, 2)}
    # Earlier positions: s = [position + 1, -(document + 1), 0, 1]; fam-2 normalized is document 5.
    assert by_position == {0: [1.0, -6.0, 0.0, 1.0], 1: [2.0, -6.0, 0.0, 1.0], 2: [0.0, 1.0, 0.0, 0.0]}
    assert [row["l2_error"] for row in payload["reconstruction"]["rows"]] == [0.0, 0.0, 2.0]


def test_a_dataset_captured_at_the_last_position_cannot_answer_a_method_that_asks_for_all(matrix: dict,
                                                                                         tmp_path: Path) -> None:
    source = ad.open_activation_dataset(PAIRS)
    samples = source.samples()
    tokens = {d["document_index"]: d["n_tokens"] for d in source.row_map["documents"]}
    keep = [i for i in range(24) if samples["position"][i] == tokens[int(samples["document_index"][i])] - 1]
    provenance = copy.deepcopy(source.manifest["provenance"])
    provenance["patientwords"]["positions"] = "last"
    ad.write_activation_dataset(tmp_path / "last", model=source.manifest["model"], layers={1: source.layer(1)[keep]},
                                samples={name: tensor[keep] for name, tensor in samples.items()},
                                provenance=provenance)
    assert values(score(matrix, "fam-2", "clinical", pairs=tmp_path / "last")) == [2.0, 0.0, 0.0, -1.0]
    with pytest.raises(Refusal) as caught:
        score(matrix, "fam-2", "clinical", pairs=tmp_path / "last", positions="all")
    assert caught.value.code == "row_alignment" and "positions [0, 1, 2]" in str(caught.value)


def test_within_pair_differences_use_one_basis(matrix: dict) -> None:
    block = ica.compare_pair(score(matrix, "fam-1", "clinical"), score(matrix, "fam-1", "colloquial"))
    assert [c["difference_a_minus_b"] for c in block["layers"][0]["components"]] == [6.0, -8.0, 0.0, 0.0]
    same = ica.compare_pair(score(matrix, "fam-3", "clinical"), score(matrix, "fam-3", "colloquial"))
    assert [c["difference_a_minus_b"] for c in same["layers"][0]["components"]] == [0.0, 0.0, 0.0, 0.0]


def test_the_two_paths_sit_behind_one_function_and_the_payload_says_which_ran(matrix: dict) -> None:
    status = ica.icalens_status()
    basis = ica.load_basis(MANIFEST)
    x = np.array([[8, 8, 4, 0, 0, 0, 3, 4]], dtype=np.float32)
    numpy_result = ica.apply_basis(basis, x, layer=1, path="numpy")
    assert numpy_result["execution_path"]["used"] == "numpy" and numpy_result["scores"].tolist() == [[1, 6, 2, 1]]
    assert numpy_result["execution_path"]["icalens_version"] is None
    auto = score(matrix, "fam-1", "normalized", path="auto")
    if status["importable"]:
        assert auto["execution_path"]["used"] == "icalens" and auto["execution_path"]["icalens_version"]
        assert auto["execution_path"]["cross_check_by_layer"]["1"]["max_abs_score_difference"] <= 1e-9
    else:
        assert auto["execution_path"]["used"] == "numpy" and auto["execution_path"]["icalens_version"] is None
        assert auto["execution_path"]["icalens_import_error"] and auto["execution_path"]["cross_check_by_layer"] == {
            "1": None}
        assert code_of(lambda: ica.apply_basis(basis, x, layer=1, path="icalens")) == "reference_unavailable"
    assert values(auto) == [1.0, 6.0, 2.0, 1.0]
    assert code_of(lambda: ica.apply_basis(basis, x, layer=1, path="torch")) == "execution_path"


# ------------------------------------------------------------------------------------------ basis manifest

@pytest.mark.parametrize("name,schema_id", [("ica_basis_manifest", "patientwords.ica-basis-manifest/1"),
                                            ("ica_scores", "patientwords.ica-scores/1")])
def test_schemas_use_only_the_keywords_the_repository_validator_executes(name: str, schema_id: str) -> None:
    from scripts.frontend_contract_schema import check_schema_subset

    schema = common.load_schema(name)
    assert schema["$id"] == schema_id and schema["additionalProperties"] is False
    errors: list = []
    check_schema_subset(lambda _a, where, why: errors.append((where, why)), name, {}, schema)   # audits keywords
    assert {where for where, _ in errors} == {f"$.{key}" for key in schema["required"]}


def test_manifest_identifies_the_basis_and_reads_preprocessing_from_the_artifact() -> None:
    manifest = ica.validate_basis_manifest(read(MANIFEST))
    assert manifest["model"] == {"hf_id": "fixture/toy-model", "revision": "1" * 40, "type": "base",
                                 "tokenizer_id": "fixture/toy-tokenizer", "tokenizer_revision": "1" * 40,
                                 "hidden_size": 8}
    assert manifest["preprocessing"]["mode"] == "none"
    assert manifest["preprocessing"]["read_from"] == "icalens.json#/input_preprocessing/icalens_preprocessing"
    assert manifest["capture"] == {"site": "block_output", "artifact_activation_site": "resid_post",
                                   "layer_index_base": 0,
                                   "artifact_layer_indexing": "transformer_blocks_zero_based", "layers": [1],
                                   "precision": "float32", "model_load_precision": "not_applicable_no_model"}
    assert manifest["fit"]["split"] == "discovery" and manifest["fit"]["corpus_ids"] == ["toy-discovery-corpus-1"]
    assert manifest["fit"]["activation_manifest_sha256"] == sha256_file(DISCOVERY / "activations.json")
    assert {entry["path"]: entry["sha256"] for entry in manifest["artifact"]["files"]} == {
        "icalens.json": sha256_file(ICA / "toy_basis" / "icalens.json"),
        LAYER_FILE: sha256_file(ICA / "toy_basis" / LAYER_FILE)}
    layer = manifest["layers"]["1"]
    assert layer["tensors"] == {"center": [8], "reading_matrix": [4, 8], "writing_matrix": [8, 4]}
    assert set(layer["fit_settings"]) >= {"algorithm", "fun", "max_iter", "n_components", "n_samples",
                                          "stopping_criterion", "seed"}
    assert set(layer["fit_diagnostics"]) == {"objective_history", "component_strengths", "component_objectives",
                                             "gaussian_objective"}
    assert manifest["sign_convention"] == ica.SIGN_CONVENTION
    assert "does not establish stable components" in manifest["fit_diagnostics_statement"]
    assert manifest["not_recorded"] == [] and ica.basis_identity(manifest)["status"] == "recorded"
    assert common.structural_errors(manifest, "ica_basis_manifest") == []


def test_a_legacy_artifact_without_the_mode_key_is_read_from_row_normalization(tmp_path: Path) -> None:
    def legacy(saved: dict) -> None:
        saved["input_preprocessing"] = {"row_normalization": "l2", "norm_eps": 1e-12}
    manifest = read(make_basis(tmp_path, saved=legacy))
    assert manifest["preprocessing"]["mode"] == "l2"
    assert "row_normalization (no icalens_preprocessing key)" in manifest["preprocessing"]["read_from"]


def test_a_value_the_artifact_lacks_stays_null_and_is_listed(tmp_path: Path) -> None:
    def drop(saved: dict) -> None:
        saved["layers"]["1"]["fitting"].pop("max_iter")
        saved["model"]["revision"] = None
    path = make_basis(tmp_path, saved=drop)
    manifest = read(path)
    assert manifest["layers"]["1"]["fit_settings"]["max_iter"] is None and manifest["model"]["revision"] is None
    # The default test basis also leaves the two optional fit-corpus hashes unrecorded.
    assert manifest["not_recorded"] == ["/fit/activation_manifest_sha256", "/fit/document_token_sha256",
                                        "/layers/1/fit_settings/max_iter", "/model/revision"]
    assert ica.basis_identity(manifest) == {
        "model_id": "fixture/toy-model", "model_revision": None, "tokenizer_id": "fixture/toy-tokenizer",
        "tokenizer_revision": "1" * 40, "status": "unknown", "unknown_fields": ["revision"],
        "parity": "not_established"}
    manifest["not_recorded"] = []
    assert code_of(lambda: ica.validate_basis_manifest(manifest)) == "silent_missing_provenance"


def test_annotations_are_carried_as_hypotheses_with_their_source(matrix: dict, tmp_path: Path) -> None:
    payload = score(matrix, "fam-1", "clinical")
    assert [(a["component"], a["status"]) for a in payload["component_annotations"]] == [(0, "hypothesis"),
                                                                                       (1, "hypothesis")]
    assert all(a["source"] for a in payload["component_annotations"])
    assert "None is a verified concept" in payload["annotation_statement"]
    verified = [{"layer": 1, "component": 0, "status": "verified", "label": "placeholder", "source": "a claim"}]
    assert code_of(lambda: make_basis(tmp_path / "a", annotations=verified)) == "annotation_status"
    unsourced = [{"layer": 1, "component": 0, "status": "hypothesis", "label": "placeholder", "source": ""}]
    assert code_of(lambda: make_basis(tmp_path / "b", annotations=unsourced)) == "annotation_status"
    marked = [{"layer": 1, "component": 0, "status": "hypothesis", "label": "placeholder", "source": "a claim",
               "verified": True}]
    assert code_of(lambda: make_basis(tmp_path / "c", annotations=marked)) == "basis_manifest"   # closed by schema


# ----------------------------------------------------------------------------------------------- refusals

def test_artifact_hash_detects_altered_bytes(tmp_path: Path) -> None:
    fixtures = copy_fixtures(tmp_path)
    layer = fixtures / "ica" / "toy_basis" / LAYER_FILE
    data = bytearray(layer.read_bytes())
    data[-1] ^= 0x01                                               # one bit of one matrix entry
    layer.write_bytes(bytes(data))
    with pytest.raises(Refusal) as caught:
        ica.load_basis(fixtures / "ica" / "basis_manifest.json")
    assert caught.value.code == "artifact_hash" and LAYER_FILE in str(caught.value)
    fixtures = copy_fixtures(tmp_path / "second")
    rewrite_json(fixtures / "ica" / "toy_basis" / "icalens.json", lambda d: d.update(hidden_size=9))
    assert code_of(lambda: ica.load_basis(fixtures / "ica" / "basis_manifest.json")) == "artifact_hash"
    fixtures = copy_fixtures(tmp_path / "third")
    (fixtures / "ica" / "toy_basis" / LAYER_FILE).unlink()
    assert code_of(lambda: ica.load_basis(fixtures / "ica" / "basis_manifest.json")) == "artifact_hash"


def test_dimension_and_finiteness_refusals(tmp_path: Path) -> None:
    basis = ica.load_basis(MANIFEST)
    assert code_of(lambda: ica.apply_basis(basis, np.zeros((2, 7), dtype=np.float32), layer=1)) == "dimension_mismatch"
    assert code_of(lambda: ica.apply_basis(basis, np.zeros(8, dtype=np.float32), layer=1)) == "dimension_mismatch"
    assert code_of(lambda: ica.apply_basis(basis, np.zeros((2, 8), dtype=np.float32), layer=2)) == "dimension_mismatch"
    bad = np.zeros((2, 8), dtype=np.float32)
    bad[1, 3] = np.inf
    assert code_of(lambda: ica.apply_basis(basis, bad, layer=1, path="numpy")) == "non_finite"
    assert code_of(lambda: ica.apply_basis(basis, np.zeros((2, 8), dtype=np.int64), layer=1)) == "non_finite"
    # A saved matrix of the wrong shape, pinned by a manifest that hashes it correctly.
    narrow = make_basis(tmp_path / "narrow", reading=READING[:, :7])
    assert code_of(lambda: ica.load_basis(narrow)) == "dimension_mismatch"
    poisoned = READING.copy()
    poisoned[0, 0] = np.nan
    assert code_of(lambda: ica.load_basis(make_basis(tmp_path / "nan", reading=poisoned))) == "non_finite"


def test_preprocessing_mismatch_between_manifest_artifact_and_protocol(matrix: dict, tmp_path: Path) -> None:
    def claim_none(manifest: dict) -> None:
        manifest["preprocessing"]["mode"] = "none"
        manifest["preprocessing"]["row_normalization"] = "none"
    wrong = make_basis(tmp_path / "wrong", mode="l2", edit=claim_none)
    with pytest.raises(Refusal) as caught:
        ica.load_basis(wrong)
    assert caught.value.code == "preprocessing_mismatch" and "saved artifact records 'l2'" in str(caught.value)
    # The protocol says l2; the saved artifact says none.
    assert code_of(lambda: score(matrix, "fam-1", "clinical", preprocessing="l2")) == "preprocessing_mismatch"
    # A geometric-median artifact without its preprocessing_center tensor.
    assert code_of(lambda: ica.load_basis(make_basis(tmp_path / "gm", mode="geometric-median-l2"))) == (
        "preprocessing_mismatch")


def test_the_saved_mode_decides_the_scores_l2_against_none(matrix: dict, tmp_path: Path) -> None:
    """Same matrices, two saved modes. x = [8,8,4,0,0,0,3,4] has norm 13.

    none: scores [1, 6, 2, 1]. l2: x/13 - center = [-5/13, -18/13, 4/13, 1, ...], so
    scores = [d0 - d1, d1, d2 - 2 d3, d3] = [1, -18/13, -22/13, 1]."""
    normalized = make_basis(tmp_path / "l2", mode="l2")
    payload = score(matrix, "fam-1", "normalized", manifest=normalized, fit=None, preprocessing="l2")
    assert payload["basis"]["preprocessing_mode"] == "l2"
    assert values(payload) == pytest.approx([1.0, -18 / 13, -22 / 13, 1.0], abs=1e-12)
    assert values(payload) != values(score(matrix, "fam-1", "normalized"))
    (row,) = payload["reconstruction"]["rows"]
    # In the normalized space the residual is [0,0,3,4]/13: error 5/13 against a unit-norm row.
    assert row["preprocessed_l2_norm"] == pytest.approx(1.0) and row["l2_error"] == pytest.approx(5 / 13)
    assert row["cosine"] == pytest.approx(12 / 13)


def test_geometric_median_mode_subtracts_the_saved_center_first(tmp_path: Path) -> None:
    """g = [8,8,4,0,0,0,0,0]: x - g = [0,0,0,0,0,0,3,4], norm 5, x_pre = [0,0,0,0,0,0,0.6,0.8].
    x_pre - center = [-1,-2,0,1,...] so scores = [1,-2,-2,1]; the reconstruction is the zero vector, so the
    error is 1, the relative error is 1 and the cosine is undefined (null)."""
    g = np.array([8, 8, 4, 0, 0, 0, 0, 0], dtype=np.float64)
    basis = ica.load_basis(make_basis(tmp_path, mode="geometric-median-l2", pre_center=g))
    result = ica.apply_basis(basis, np.array([[8, 8, 4, 0, 0, 0, 3, 4]], dtype=np.float32), layer=1, path="numpy")
    assert result["scores"][0] == pytest.approx([1.0, -2.0, -2.0, 1.0], abs=1e-12)
    assert result["l2_error"][0] == pytest.approx(1.0) and result["relative_l2_error"][0] == pytest.approx(1.0)
    assert np.isnan(result["cosine"][0])


def leak(path: tuple[str, ...], value: Any) -> Callable[[dict], None]:
    def edit(manifest: dict) -> None:
        node = manifest
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        manifest["not_recorded"] = sorted(null_pointers({k: v for k, v in manifest.items() if k != "not_recorded"}))
    return edit


def test_split_leakage_refusals(matrix: dict, tmp_path: Path) -> None:
    protocol = read(FX / "protocol_synthetic.json")
    held_out_tokens = protocol["case_families"][2]["variants"]["clinical"]["token_sha256"]
    cases = {
        "fit_family": leak(("fit", "family_ids"), ["fam-1", "fam-2"]),
        "profile_family": leak(("profile", "family_ids"), ["fam-3"]),
        "selection_corpus": leak(("selection", "corpus_ids"), ["fam-2"]),
        "token_hash": leak(("fit", "document_token_sha256"), [held_out_tokens]),
        # Fit on the dataset that is being scored, which holds validation and fresh-test families.
        "fit_on_scored": leak(("fit", "activation_manifest_sha256"), sha256_file(PAIRS / "activations.json")),
    }
    for name, edit in cases.items():
        manifest = make_basis(tmp_path / name, edit=edit)
        with pytest.raises(Refusal) as caught:
            score(matrix, "fam-1", "clinical", manifest=manifest, fit=None)
        assert caught.value.code == "split_leakage", name
    # A discovery family may be used for fitting.
    allowed = make_basis(tmp_path / "ok", edit=leak(("fit", "family_ids"), ["fam-1"]))
    assert values(score(matrix, "fam-1", "clinical", manifest=allowed, fit=None)) == [3.0, -4.0, 0.0, 0.0]
    # A manifest that names a non-discovery fit split is refused before anything is read.
    assert code_of(lambda: make_basis(tmp_path / "split", fit={"corpus_id": "c", "split": "validation"})) == (
        "split_leakage")
    # The supplied fit dataset holds held-out rows: its row map is checked as well.
    plain = make_basis(tmp_path / "plain")
    assert code_of(lambda: score(matrix, "fam-1", "clinical", manifest=plain, fit=PAIRS)) == "split_leakage"
    report = score(matrix, "fam-1", "clinical")["split_leakage_checks"]
    assert report == {"fit_stage_ids": "checked", "profile_stage_ids": "no_ids_listed",
                      "selection_stage_ids": "no_ids_listed", "document_token_hashes": "checked",
                      "fit_dataset_row_map": "checked", "fit_dataset_file_pins": "verified",
                      "scoring_dataset_is_fit_dataset": "checked"}
    unlisted = score(matrix, "fam-1", "clinical", manifest=plain, fit=None)["split_leakage_checks"]
    assert unlisted["document_token_hashes"] == "not_listed_in_manifest"
    assert unlisted["fit_dataset_row_map"] == "fit_dataset_not_supplied"
    assert unlisted["fit_dataset_file_pins"] == "fit_dataset_not_supplied"


def test_split_leakage_covers_the_fit_corpus_id_and_says_when_nothing_was_listed(matrix: dict,
                                                                                tmp_path: Path) -> None:
    # 1. fit.corpus_id (singular) names a validation family; the two id lists are empty.
    singular = make_basis(tmp_path / "singular", fit={"split": "discovery", "corpus_id": "fam-2"})
    with pytest.raises(Refusal) as caught:
        score(matrix, "fam-2", "clinical", manifest=singular, fit=None)
    assert caught.value.code == "split_leakage" and "fam-2" in str(caught.value)

    # 2. A manifest that names no family, no corpus and no hash: zero ids were compared, and the report says so.
    silent = make_basis(tmp_path / "silent", fit={"split": "discovery"})
    report = score(matrix, "fam-2", "clinical", manifest=silent, fit=None)["split_leakage_checks"]
    assert report == {"fit_stage_ids": "no_ids_listed", "profile_stage_ids": "no_ids_listed",
                      "selection_stage_ids": "no_ids_listed", "document_token_hashes": "not_listed_in_manifest",
                      "fit_dataset_row_map": "fit_dataset_not_supplied",
                      "fit_dataset_file_pins": "fit_dataset_not_supplied",
                      "scoring_dataset_is_fit_dataset": "not_checked"}
    assert "checked" not in report.values()
    named = make_basis(tmp_path / "named", profile={"performed": True, "family_ids": ["fam-1"]})
    assert score(matrix, "fam-1", "clinical", manifest=named, fit=None)["split_leakage_checks"][
        "profile_stage_ids"] == "checked"

    # 3. The held-out pair rows relabelled as a fit corpus: role fit_corpus, split discovery, the family id
    #    moved to corpus_id, the token hash dropped.
    def relabel(doc: dict) -> None:
        for document in doc["provenance"]["patientwords"]["documents"]:
            family = document.pop("family_id")
            document.pop("variant")
            document.pop("token_sha256")
            document.update(role="fit_corpus", split="discovery", corpus_id=family)
    shutil.copytree(PAIRS, tmp_path / "relabelled")
    rewrite_json(tmp_path / "relabelled" / "activations.json", relabel)
    ad.validate_activation_dataset(tmp_path / "relabelled")         # a well-formed dataset in its own right
    disguised = make_basis(tmp_path / "disguised", fit={
        "split": "discovery", "corpus_id": "c", "corpus_ids": ["c"],
        "activation_manifest_sha256": sha256_file(tmp_path / "relabelled" / "activations.json")})
    with pytest.raises(Refusal) as caught:
        score(matrix, "fam-2", "clinical", manifest=disguised, fit=tmp_path / "relabelled")
    assert caught.value.code == "split_leakage" and "held-out family" in str(caught.value)

    # 4. The same rows under corpus ids that are not family ids, still without token hashes: no id is refused,
    #    and the report does not say "checked".
    def rename(doc: dict) -> None:
        relabel(doc)
        for document in doc["provenance"]["patientwords"]["documents"]:
            document["corpus_id"] = "other-corpus"
    shutil.copytree(PAIRS, tmp_path / "renamed")
    rewrite_json(tmp_path / "renamed" / "activations.json", rename)
    quiet = make_basis(tmp_path / "quiet", fit={
        "split": "discovery", "corpus_id": "c", "corpus_ids": ["c"],
        "activation_manifest_sha256": sha256_file(tmp_path / "renamed" / "activations.json")})
    report = score(matrix, "fam-2", "clinical", manifest=quiet, fit=tmp_path / "renamed")["split_leakage_checks"]
    assert report["fit_dataset_row_map"] == "checked_without_token_hashes"

    # 5. A dataset-level corpus id that is a held-out family id.
    shutil.copytree(DISCOVERY, tmp_path / "level")
    rewrite_json(tmp_path / "level" / "activations.json",
                 lambda d: d["provenance"]["patientwords"].update(corpus_id="fam-3"))
    level = make_basis(tmp_path / "level_basis")
    assert code_of(lambda: score(matrix, "fam-1", "clinical", manifest=level, fit=tmp_path / "level")) == (
        "split_leakage")


def relabelled_as_fit_corpus(doc: dict) -> None:
    """The held-out pair rows presented as a fit corpus under ids that name no family, with no token hash."""
    for document in doc["provenance"]["patientwords"]["documents"]:
        document.pop("family_id")
        document.pop("variant")
        document.pop("token_sha256")
        document.update(role="fit_corpus", split="discovery", corpus_id="other-corpus")


@pytest.mark.parametrize("name,damage", [
    # The verifier's two cases: a list where an id or a hash belongs. Before the first fix round these stopped
    # with a TypeError; after it they completed with fit_dataset_row_map "checked_without_token_hashes".
    ("family_id_list", lambda document: document.update(family_id=["fam-2"])),
    ("token_sha256_list", lambda document: document.update(token_sha256=["0" * 64])),
    ("corpus_id_list", lambda document: document.update(corpus_id=["fam-2"])),
    ("corpus_id_number", lambda document: document.update(corpus_id=2)),
    ("family_id_object", lambda document: document.update(family_id={"id": "fam-2"})),
    ("variant_list", lambda document: document.update(variant=["clinical"])),
    ("token_sha256_short", lambda document: document.update(token_sha256="0" * 63)),
    ("token_sha256_upper_case", lambda document: document.update(token_sha256="A" * 64)),
    ("token_sha256_number", lambda document: document.update(token_sha256=7)),
    ("token_sha256_empty", lambda document: document.update(token_sha256="")),
    ("not_an_object", None),
])
def test_a_fit_dataset_document_with_a_malformed_id_or_token_hash_is_refused(
        matrix: dict, tmp_path: Path, name: str, damage: Callable[[dict], None] | None) -> None:
    def edit(doc: dict) -> None:
        relabelled_as_fit_corpus(doc)
        documents = doc["provenance"]["patientwords"]["documents"]
        if damage is None:
            documents[2] = "fam-2"
        else:
            damage(documents[2])
    shutil.copytree(PAIRS, tmp_path / "fit")
    rewrite_json(tmp_path / "fit" / "activations.json", edit)
    manifest = make_basis(tmp_path / "basis", fit={
        "split": "discovery", "corpus_id": "c", "corpus_ids": ["c"],
        "activation_manifest_sha256": sha256_file(tmp_path / "fit" / "activations.json")})
    with pytest.raises(Refusal) as caught:
        score(matrix, "fam-2", "clinical", manifest=manifest, fit=tmp_path / "fit")
    assert caught.value.code == "row_alignment", name
    # The same structural check serves the scored dataset, also where the leakage check reads its row map
    # (a basis manifest that names a fit dataset by hash): a refusal, where a list-valued id used to end in a
    # TypeError.
    assert code_of(lambda: ad.validate_activation_dataset(tmp_path / "fit")) == "row_alignment"
    assert code_of(lambda: ad.row_map_documents(ad.open_activation_dataset(tmp_path / "fit"))) == "row_alignment"
    assert code_of(lambda: ica.check_split_leakage(read(manifest), read(FX / "protocol_synthetic.json"),
                                                   scoring_dataset=ad.open_activation_dataset(tmp_path / "fit"))
                   ) == "row_alignment"


def test_the_fit_dataset_row_map_gets_the_structural_check_of_the_scored_dataset(matrix: dict,
                                                                                tmp_path: Path) -> None:
    def fit_with(name: str, edit: Callable[[dict], None]) -> tuple[Path, Path]:
        shutil.copytree(DISCOVERY, tmp_path / name)
        rewrite_json(tmp_path / name / "activations.json", edit)
        return make_basis(tmp_path / f"{name}_basis"), tmp_path / name

    def rows(doc: dict) -> dict:
        return doc["provenance"]["patientwords"]

    refused = {
        "dataset_corpus_id_list": lambda d: rows(d).update(corpus_id=["fam-3"]),
        "dataset_corpus_id_number": lambda d: rows(d).update(corpus_id=3),
        "documents_not_a_list": lambda d: rows(d).update(documents={"0": {}}),
        "document_listed_twice": lambda d: rows(d)["documents"].append(dict(rows(d)["documents"][0])),
        "unknown_role": lambda d: rows(d)["documents"][0].update(role="held_out_copy"),
        "no_split": lambda d: rows(d)["documents"][0].pop("split"),
        "other_rows_schema": lambda d: rows(d).update(schema_version="patientwords.activation-rows/0"),
    }
    for name, edit in refused.items():
        manifest, fit = fit_with(name, edit)
        assert code_of(lambda: score(matrix, "fam-1", "clinical", manifest=manifest, fit=fit)) == (
            "row_alignment"), name
    # Accepted as before, each with its own word: an id or a hash that is null or absent, an empty document
    # list, and a provenance block that lists no documents at all.
    accepted = {
        "hash_null": (lambda d: [doc.update(token_sha256=None) for doc in rows(d)["documents"]],
                      "checked_without_token_hashes"),
        "hash_absent": (lambda d: rows(d)["documents"][0].pop("token_sha256"), "checked_without_token_hashes"),
        "family_null": (lambda d: rows(d)["documents"][0].update(family_id=None), "checked"),
        "no_documents": (lambda d: rows(d).update(documents=[]), "fit_dataset_has_no_row_map"),
        "documents_null": (lambda d: rows(d).update(documents=None), "fit_dataset_has_no_row_map"),
        "documents_absent": (lambda d: rows(d).pop("documents"), "fit_dataset_has_no_row_map"),
    }
    for name, (edit, word) in accepted.items():
        manifest, fit = fit_with(name, edit)
        report = score(matrix, "fam-1", "clinical", manifest=manifest, fit=fit)["split_leakage_checks"]
        assert report["fit_dataset_row_map"] == word, name
        assert set(report) == set(ica.LEAKAGE_WORDS)
        assert all(report[key] in words for key, words in ica.LEAKAGE_WORDS.items()), name


def test_a_supplied_fit_dataset_must_be_captured_at_the_site_of_the_basis_artifact(matrix: dict,
                                                                                  tmp_path: Path) -> None:
    """A copy of the discovery fixture that records another site, named by its hash in the basis manifest, was
    accepted as the fit dataset of a basis whose icalens.json records resid_post."""
    cases = {
        "site": lambda d: d.update(activation_site="mlp_out"),
        "indexing": lambda d: d.update(layer_indexing="hidden_states"),
        "site_absent": lambda d: d.pop("activation_site"),
        "indexing_null": lambda d: d.update(layer_indexing=None),
        "site_upper_case": lambda d: d.update(activation_site="RESID_POST"),
        "site_list": lambda d: d.update(activation_site=["resid_post"]),
    }
    for name, edit in cases.items():
        shutil.copytree(DISCOVERY, tmp_path / name)
        rewrite_json(tmp_path / name / "activations.json", edit)
        ad.validate_activation_dataset(tmp_path / name)             # a well-formed dataset in its own right
        for label, fit in (("named", {"activation_manifest_sha256": sha256_file(tmp_path / name / "activations.json")}),
                           ("unnamed", {})):
            manifest = make_basis(tmp_path / f"{name}_{label}", fit={
                "split": "discovery", "corpus_id": "toy-discovery-corpus-1", **fit})
            with pytest.raises(Refusal) as caught:
                score(matrix, "fam-2", "clinical", manifest=manifest, fit=tmp_path / name)
            assert caught.value.code == "layer_metadata" and "the fit dataset records" in str(caught.value), name
    # A basis whose artifact records no site cannot be matched with a fit dataset either.
    siteless = make_basis(tmp_path / "siteless", saved=lambda saved: saved.pop("layer_indexing"))
    basis = ica.load_basis(siteless)
    assert code_of(lambda: ica.check_split_leakage(basis.manifest, read(FX / "protocol_synthetic.json"),
                                                   fit_dataset=ad.open_activation_dataset(DISCOVERY))) == (
        "layer_metadata")
    # Through the run store: the fixtures' fit dataset edited to another site gives no payload.
    fixtures = copy_fixtures(tmp_path / "store")
    rewrite_json(fixtures / "ica" / "discovery_activations" / "activations.json",
                 lambda d: d.update(activation_site="mlp_out"))

    def rename_fit(manifest: dict) -> None:
        manifest["fit"]["activation_manifest_sha256"] = sha256_file(
            fixtures / "ica" / "discovery_activations" / "activations.json")
    rewrite_json(fixtures / "ica" / "basis_manifest.json", rename_fit)
    store, _, _ = run(tmp_path / "store", ica_protocol(fixtures / "ica" / "basis_manifest.json"), matrix, fixtures)
    envelopes = ica_envelopes(store)
    assert {(e["status"]["execution"], e["status"]["reason"].split(":")[0]) for e in envelopes.values()} == {
        ("invalid", "layer_metadata")}
    assert all(e["payload"] is None for e in envelopes.values())


def test_the_dataset_capture_site_and_layer_indexing_must_equal_the_basis_artifact(matrix: dict,
                                                                                   tmp_path: Path) -> None:
    baseline = score(matrix, "fam-2", "clinical")
    assert (baseline["capture"]["activation_site"], baseline["capture"]["layer_indexing"]) == (
        "resid_post", "transformer_blocks_zero_based")
    assert baseline["capture"]["site"] == "block_output"            # the protocol's own name for the site
    cases = {
        "site": lambda d: d.update(activation_site="mlp_out"),
        "indexing": lambda d: d.update(layer_indexing="hidden_states"),
        "both": lambda d: d.update(activation_site="mlp_out", layer_indexing="hidden_states"),
        "site_absent": lambda d: d.pop("activation_site"),
        "indexing_null": lambda d: d.update(layer_indexing=None),
    }
    for name, edit in cases.items():
        shutil.copytree(PAIRS, tmp_path / name)
        rewrite_json(tmp_path / name / "activations.json", edit)
        ad.validate_activation_dataset(tmp_path / name)             # still a well-formed dataset
        with pytest.raises(Refusal) as caught:
            score(matrix, "fam-2", "clinical", pairs=tmp_path / name)
        assert caught.value.code == "layer_metadata" and "basis artifact records" in str(caught.value), name
    # A basis whose artifact records no site cannot be matched with any dataset.
    siteless = make_basis(tmp_path / "siteless", saved=lambda saved: saved.pop("activation_site"))
    assert read(siteless)["capture"]["artifact_activation_site"] is None
    assert code_of(lambda: score(matrix, "fam-2", "clinical", manifest=siteless, fit=None)) == "layer_metadata"
    # A manifest edited to disagree with the pinned icalens.json on the site is refused when the basis loads.
    edited = make_basis(tmp_path / "edited", edit=leak(("capture", "artifact_activation_site"), "mlp_out"))
    assert code_of(lambda: ica.load_basis(edited)) == "layer_metadata"


def test_the_basis_manifest_identity_is_compared_with_the_saved_icalens_json(matrix: dict, tmp_path: Path) -> None:
    def saved_model(**changes: Any) -> Callable[[dict], None]:
        def edit(saved: dict) -> None:
            for key, value in changes.items():
                if value is None:
                    saved["model"].pop(key)
                else:
                    saved["model"][key] = value
        return edit

    def claim(manifest: dict) -> None:
        """Hand-set the manifest's model block to the protocol's model, as the reviewer's case does."""
        manifest["model"].update(hf_id="fixture/toy-model", revision="1" * 40, type="base")
        manifest["not_recorded"] = sorted(null_pointers({k: v for k, v in manifest.items() if k != "not_recorded"}))

    # Another model in the artifact, the protocol's model in the manifest: a contradiction.
    other = make_basis(tmp_path / "other", saved=saved_model(repo_id="fixture/other-model"), edit=claim)
    with pytest.raises(Refusal) as caught:
        ica.load_basis(other)
    assert caught.value.code == "identity_mismatch" and "fixture/other-model" in str(caught.value)
    # Another exact revision, or another model type.
    assert code_of(lambda: ica.load_basis(make_basis(tmp_path / "rev", saved=saved_model(revision="2" * 40),
                                                     edit=claim))) == "identity_mismatch"
    assert code_of(lambda: ica.load_basis(make_basis(tmp_path / "type", saved=saved_model(type="chat"),
                                                     edit=claim))) == "identity_mismatch"
    assert code_of(lambda: ica.load_basis(make_basis(tmp_path / "branch", saved=saved_model(revision="main"),
                                                     edit=claim))) == "identity_mismatch"

    # The artifact holds the placeholder "unknown" (what `icalens fit activations` writes) or no revision at
    # all, and the manifest states a 40-hex revision: the identity is unknown and no score is produced.
    for name, change in (("placeholder", "unknown"), ("absent", None)):
        path = make_basis(tmp_path / name, saved=saved_model(revision=change), edit=claim)
        assert read(path)["model"]["revision"] == "1" * 40
        basis = ica.load_basis(path)
        assert ica.basis_identity(basis.manifest)["status"] == "recorded"       # the manifest alone says so
        assert basis.identity["status"] == "unknown" and basis.identity["unknown_fields"] == ["artifact_revision"]
        with pytest.raises(Refusal) as caught:
            score(matrix, "fam-1", "clinical", manifest=path, fit=None)
        assert caught.value.code == "unknown_identity" and "artifact_revision" in str(caught.value), name

    # Through the run store that task is unavailable, as for any other unknown identity: not invalid, not failed.
    fixtures = copy_fixtures(tmp_path / "store")
    rewrite_json(fixtures / "ica" / "toy_basis" / "icalens.json", lambda d: d["model"].update(revision="unknown"))

    def repin_artifact(manifest: dict) -> None:
        for entry in manifest["artifact"]["files"]:
            entry["sha256"] = sha256_file(fixtures / "ica" / "toy_basis" / entry["path"])
            entry["bytes"] = (fixtures / "ica" / "toy_basis" / entry["path"]).stat().st_size
    rewrite_json(fixtures / "ica" / "basis_manifest.json", repin_artifact)
    assert ica.load_basis(fixtures / "ica" / "basis_manifest.json").identity["status"] == "unknown"
    store, _, summary = run(tmp_path / "store", ica_protocol(fixtures / "ica" / "basis_manifest.json"), matrix,
                            fixtures)
    reasons = {e["status"]["execution"]: e["status"]["reason"] for e in ica_envelopes(store).values()}
    assert list(reasons) == ["unavailable"] and reasons["unavailable"].startswith("unknown_identity: the basis")
    assert "artifact_revision" in reasons["unavailable"]
    assert summary["by_state"]["invalid"] == 0 and summary["by_state"]["failed"] == 0


def test_the_model_block_is_the_one_icalens_reads_and_two_differing_blocks_are_refused(matrix: dict,
                                                                                      tmp_path: Path) -> None:
    """icalens 0.4.0 reads ``base_model`` when ``format_version`` is 1 and ``model`` otherwise (lens.py:651-652).
    ``artifact_model`` used to take ``model`` first whatever the version, so a version-1 artifact with a matching
    ``model`` block and a ``base_model`` block naming another model scored as the first while icalens loaded it
    as the second."""
    protocol_model = {"repo_id": "fixture/toy-model", "revision": "1" * 40, "type": "base"}
    other = {"repo_id": "some-org/other-model", "revision": "3" * 40, "type": "base"}
    assert BUILDER.toy_artifact_manifest(LAYER_FILE)["model"] == protocol_model

    # Which block is read.
    assert ica.artifact_model({"format_version": 4, "model": protocol_model}) == protocol_model
    assert ica.artifact_model({"format_version": 1, "base_model": other}) == other
    for version in (1, "1", 1.0, True):                                 # icalens applies int() to the value
        assert ica.artifact_model({"format_version": version, "model": protocol_model}) == {}
        assert ica.artifact_model({"format_version": version, "base_model": other}) == other
    for version in (2, 4, "4", None, "one", [1], float("nan"), float("inf")):
        assert ica.artifact_model({"format_version": version, "base_model": other}) == {}, version
        assert ica.artifact_model({"format_version": version, "model": protocol_model}) == protocol_model
    assert ica.artifact_model({"model": protocol_model}) == protocol_model      # no version: not version 1
    assert ica.artifact_model({"format_version": 4, "model": "fixture/toy-model", "base_model": other}) == {}
    assert ica.artifact_model({"format_version": 1, "model": protocol_model, "base_model": {}}) == {}
    assert ica.artifact_model({}) == {}
    # Both blocks, different contents: refused whatever the version. Equal blocks are one statement.
    for version in (1, 4, None):
        assert code_of(lambda: ica.artifact_model({"format_version": version, "model": protocol_model,
                                                   "base_model": other})) == "identity_mismatch"
        assert code_of(lambda: ica.artifact_model({"format_version": version, "model": other,
                                                   "base_model": {**other, "type": "chat"}})) == "identity_mismatch"
        assert ica.artifact_model({"format_version": version, "model": other, "base_model": dict(other)}) == other

    def claim(manifest: dict) -> None:
        manifest["model"].update(hf_id="fixture/toy-model", revision="1" * 40, type="base")
        manifest["not_recorded"] = sorted(null_pointers({k: v for k, v in manifest.items() if k != "not_recorded"}))

    # The verifier's artifact is refused when a manifest is built from it, with either version.
    for name, version in (("as_built", 4), ("legacy", 1)):
        assert code_of(lambda: make_basis(tmp_path / name, saved=lambda a: a.update(
            format_version=version, base_model=dict(other)), edit=claim)) == "identity_mismatch", name
    # A version-1 artifact whose base_model is another model, under a manifest that claims the protocol's model.
    moved = make_basis(tmp_path / "moved", edit=claim, saved=lambda a: (
        a.update(format_version=1, base_model=dict(other)), a.pop("model")))
    with pytest.raises(Refusal) as caught:
        ica.load_basis(moved)
    assert caught.value.code == "identity_mismatch" and "some-org/other-model" in str(caught.value)
    # A version-1 artifact with only a "model" block: icalens reads no model from it, and neither does this.
    orphan = make_basis(tmp_path / "orphan", saved=lambda a: a.update(format_version=1))
    assert read(orphan)["model"]["hf_id"] is None and "/model/hf_id" in read(orphan)["not_recorded"]
    assert ica.load_basis(orphan).identity["status"] == "unknown"
    assert code_of(lambda: ica.load_basis(make_basis(tmp_path / "orphan_claimed", edit=claim, saved=lambda a: a.update(
        format_version=1)))) == "identity_mismatch"
    # A version-1 artifact that names the protocol's model under base_model scores as before.
    legacy = make_basis(tmp_path / "legacy_ok", saved=lambda a: a.update(format_version=1, base_model=a.pop("model")))
    assert ica.load_basis(legacy).identity["status"] == "recorded"
    assert values(score(matrix, "fam-1", "clinical", manifest=legacy, fit=None)) == [3.0, -4.0, 0.0, 0.0]

    # A manifest built before the artifact gained a second block: load_basis refuses, and through the run
    # store every task is invalid with no payload.
    fixtures = copy_fixtures(tmp_path / "store")
    rewrite_json(fixtures / "ica" / "toy_basis" / "icalens.json",
                 lambda d: d.update(format_version=1, base_model=dict(other)))

    def repin_artifact(manifest: dict) -> None:
        for entry in manifest["artifact"]["files"]:
            entry["sha256"] = sha256_file(fixtures / "ica" / "toy_basis" / entry["path"])
            entry["bytes"] = (fixtures / "ica" / "toy_basis" / entry["path"]).stat().st_size
    rewrite_json(fixtures / "ica" / "basis_manifest.json", repin_artifact)
    assert code_of(lambda: ica.load_basis(fixtures / "ica" / "basis_manifest.json")) == "identity_mismatch"
    store, _, _ = run(tmp_path / "store", ica_protocol(fixtures / "ica" / "basis_manifest.json"), matrix, fixtures)
    envelopes = ica_envelopes(store)
    assert {(e["status"]["execution"], e["status"]["reason"].split(":")[0]) for e in envelopes.values()} == {
        ("invalid", "identity_mismatch")}
    assert all(e["payload"] is None for e in envelopes.values())


def test_basis_mismatch_between_protocol_manifest_and_pair_members(matrix: dict, tmp_path: Path) -> None:
    other = make_basis(tmp_path)
    protocol = ica_protocol(other)                                 # the protocol names the other basis
    with pytest.raises(Refusal) as caught:
        ica.score_task(task_for(protocol, matrix, "fam-1", "clinical"), protocol, basis=ica.load_basis(MANIFEST),
                       dataset=ad.open_activation_dataset(PAIRS))
    assert caught.value.code == "basis_mismatch"
    a = score(matrix, "fam-1", "clinical")
    b = score(matrix, "fam-1", "colloquial", manifest=other, fit=None)
    assert a["basis"]["manifest_sha256"] != b["basis"]["manifest_sha256"]
    assert code_of(lambda: ica.compare_pair(a, b)) == "basis_mismatch"


def test_identity_refusals_in_the_direct_api(matrix: dict, tmp_path: Path) -> None:
    def forget(manifest: dict) -> None:
        manifest["model"]["tokenizer_revision"] = None
        manifest["not_recorded"] = sorted(manifest["not_recorded"] + ["/model/tokenizer_revision"])
    unknown = make_basis(tmp_path / "unknown", edit=forget)
    with pytest.raises(Refusal) as caught:
        score(matrix, "fam-1", "clinical", manifest=unknown, fit=None)
    assert caught.value.code == "unknown_identity" and "parity is not established" in str(caught.value)
    other_model = make_basis(tmp_path / "other", edit=leak(("model", "revision"), "2" * 40))
    assert code_of(lambda: score(matrix, "fam-1", "clinical", manifest=other_model, fit=None)) == "identity_mismatch"
    shutil.copytree(PAIRS, tmp_path / "pairs")
    rewrite_json(tmp_path / "pairs" / "activations.json", lambda d: d["model"].pop("revision"))
    assert code_of(lambda: score(matrix, "fam-1", "clinical", pairs=tmp_path / "pairs")) == "unknown_identity"


def test_row_alignment_and_incomplete_refusals_in_the_direct_api(matrix: dict, tmp_path: Path) -> None:
    shutil.copytree(PAIRS, tmp_path / "tokens")
    samples_with(set_value("token_id", 20, 0))(tmp_path / "tokens")
    assert code_of(lambda: score(matrix, "fam-1", "clinical", pairs=tmp_path / "tokens")) == "row_alignment"
    shutil.copytree(PAIRS, tmp_path / "capturing")
    rewrite_json(tmp_path / "capturing" / "activations.json", lambda d: d.update(status="capturing"))
    assert code_of(lambda: score(matrix, "fam-1", "clinical", pairs=tmp_path / "capturing")) == "incomplete"


def test_interventions_are_refused_with_a_pointer(matrix: dict) -> None:
    protocol = ica_protocol(clamp={"component": 0, "value": 4.0})
    task = task_for(protocol, matrix, "fam-1", "clinical")
    context = {"fixtures_dir": FX, "protocol": protocol}
    state, reason = ica.ADAPTER.preflight(task, context)
    assert state == "unsupported" and "separate experiment" in reason and "intervention_plan" in reason
    with pytest.raises(Refusal) as caught:
        ica.ADAPTER.execute_fixture(task, context)
    assert caught.value.code == "unsupported_operation"
    assert code_of(lambda: ica.refuse_intervention({"steer": (1, 2.0)})) == "unsupported_operation"
    for key in ("steer", "intervention", "ablate"):
        assert ica.intervention_request({"id": "ica_lens", key: 1}) == [key]


# ------------------------------------------------------------------------------------- signs across fits

PERMUTATION = [2, 0, 3, 1]          # component j of the second fit is component PERMUTATION[j] of the first
SIGNS = [-1, 1, -1, 1]              # and carries this sign


def flipped_basis(root: Path) -> Path:
    signs = np.array(SIGNS, dtype=np.float64)
    return make_basis(root, reading=signs[:, None] * READING[PERMUTATION], writing=WRITING[:, PERMUTATION] * signs,
                      basis_id="fixture/flipped-permuted-basis")


def alignment(first: str, second: str, signs: list[int] = SIGNS) -> dict:
    return {"schema_version": "patientwords.ica-alignment/1", "synthetic": True, "basis_a": first,
            "basis_b": second, "layer": 1, "method": "known by construction in a synthetic test",
            "source": "tests/test_experiments_ica.py",
            "pairs": [{"component_a": PERMUTATION[j], "component_b": j, "sign": signs[j]} for j in range(4)]}


def test_a_sign_flipped_permuted_basis_needs_an_alignment_record(matrix: dict, tmp_path: Path) -> None:
    second = flipped_basis(tmp_path)
    first_payloads = [score(matrix, "fam-1", name) for name in ("clinical", "normalized")]
    second_payloads = [score(matrix, "fam-1", name, manifest=second, fit=None) for name in ("clinical", "normalized")]
    # clinical s = [3,-4,0,0] becomes [-s2, s0, -s3, s1] = [0, 3, 0, -4]; normalized [1,6,2,1] becomes [-2, 1, -1, 6].
    assert values(second_payloads[0]) == [0.0, 3.0, 0.0, -4.0]
    assert values(second_payloads[1]) == [-2.0, 1.0, -1.0, 6.0]
    assert values(second_payloads[1], "energy_share") == pytest.approx([4 / 42, 1 / 42, 1 / 42, 36 / 42], abs=1e-15)
    # The same subspace is spanned, so the reconstruction and its error do not change.
    assert second_payloads[1]["reconstruction"]["rows"][0]["l2_error"] == 5.0
    block_one = ica.compare_pair(*first_payloads)                  # differences [2, -10, -2, -1]
    block_two = ica.compare_pair(*second_payloads)                 # differences [2, 2, 1, -10]
    assert [c["difference_a_minus_b"] for c in block_one["layers"][0]["components"]] == [2.0, -10.0, -2.0, -1.0]
    assert [c["difference_a_minus_b"] for c in block_two["layers"][0]["components"]] == [2.0, 2.0, 1.0, -10.0]
    with pytest.raises(Refusal) as caught:
        ica.compare_across_fits(block_one, block_two)
    assert caught.value.code == "sign_convention" and "alignment record" in str(caught.value)
    first, other = block_one["basis_manifest_sha256"], block_two["basis_manifest_sha256"]
    aligned = ica.compare_across_fits(block_one, block_two, alignment(first, other))
    assert [c["aligned_difference_gap"] for c in aligned["layers"][0]["components"]] == [0.0, 0.0, 0.0, 0.0]
    assert [(c["component_a"], c["component_b"], c["sign"]) for c in aligned["layers"][0]["components"]] == [
        (0, 1, 1), (1, 3, 1), (2, 0, -1), (3, 2, -1)]
    # A record with the wrong signs is used as written: the gaps show the disagreement, nothing is corrected.
    wrong = ica.compare_across_fits(block_one, block_two, alignment(first, other, [1, 1, 1, 1]))
    assert [c["aligned_difference_gap"] for c in wrong["layers"][0]["components"]] == [0.0, 0.0, -4.0, -2.0]
    for broken in (alignment(other, first), {**alignment(first, other), "layer": 2},
                   {**alignment(first, other), "layer": True},     # True == 1 in Python; it is not a layer
                   {**alignment(first, other), "source": ""},
                   {**alignment(first, other), "pairs": [{"component_a": 0, "component_b": 1, "sign": 2}]}):
        assert code_of(lambda record=broken: ica.compare_across_fits(block_one, block_two, record)) == (
            "sign_convention")
    partial = alignment(first, other)
    partial["pairs"] = partial["pairs"][:2]
    layer = ica.compare_across_fits(block_one, block_two, partial)["layers"][0]
    assert layer["unaligned_components_a"] == [1, 3] and layer["unaligned_components_b"] == [2, 3]
    same = ica.compare_across_fits(block_one, block_one)
    assert same["alignment"] == "identity_same_basis"


# ------------------------------------------------------------------------- registry, planner and run store

def test_the_adapter_registers_and_declares_only_a_fixture_capability(matrix: dict) -> None:
    assert adapters.adapter_status("ica_lens") == ("present", None)
    assert adapters.ADAPTERS["ica_lens"] is ica.ADAPTER and isinstance(ica.ADAPTER, adapters.Adapter)
    assert ica.ADAPTER.method_ids == ("ica_lens",) and ica.ADAPTER.payload_kinds == ("ica_scores/1",)
    assert set(ica.ADAPTER.payload_kinds) <= set(common.METHOD_PAYLOAD_KINDS["ica_lens"])
    (row,) = capabilities.check_adapter_rows(ica.ADAPTER.capabilities(), "scripts.experiments.adapters.ica")
    assert (row["status"], row["backend"], row["model"]["hf_id"]) == (
        "runtime_verified_offline_fixture", "fixture", "fixture/toy-model")
    assert "says nothing about any real model" in row["status_note"]
    plan = planner.build_plan(ica_protocol(), matrix)
    rows = [t for t in plan["tasks"] if t["spec"]["method"]["id"] == "ica_lens"]
    assert len(rows) == 9 and {t["planned_state"] for t in rows} == {"ready"}
    assert {t["capability"]["declared_by"] for t in rows} == {"scripts.experiments.adapters.ica"}
    # positions "last": one captured position per task, 1 layer x 8 wide x 4 bytes.
    assert {t["estimate"]["activation_bytes"] for t in rows} == {32}
    # The real-model rows of the matrix are untouched by the adapter's own row.
    real = [r for r in matrix["rows"] if r["method"] == "ica_lens" and r["backend"] != "fixture"]
    assert real and all(r["status"] in ("architecture_supported", "artifact_available_identity_unknown")
                        for r in real)


def run(tmp_path: Path, protocol: dict, matrix: dict, fixtures: Path = FX) -> tuple[RunStore, dict, dict]:
    plan = planner.build_plan(protocol, matrix)
    store = RunStore(tmp_path / "run")
    summary = store.run_fixture(plan, "w1", fixtures_dir=fixtures, protocol=protocol)
    return store, plan, summary


def ica_envelopes(store: RunStore) -> dict[tuple[str, str], dict]:
    docs = [read(path) for path in store.envelope_files()]
    return {(d["source"]["family_id"], d["source"]["variant"]): d for d in docs if d["method"]["id"] == "ica_lens"}


def test_a_planned_ica_task_runs_through_the_core_path_and_yields_a_valid_envelope(tmp_path: Path,
                                                                                    matrix: dict) -> None:
    protocol = ica_protocol()
    store, plan, summary = run(tmp_path, protocol, matrix)
    envelopes = ica_envelopes(store)
    assert len(envelopes) == 9
    for (family, variant), envelope in envelopes.items():
        assert validate_envelope(envelope, payload_root=store.run_dir) == {
            "status": "validated", "execution": "completed", "payload_verified": True}
        assert envelope["payload"]["kind"] == "ica_scores/1"
        assert envelope["method"]["representation_type"] == "ica_component"
        assert envelope["method"]["preprocessing"] == "none" and envelope["method"]["positions"] == "last"
        assert envelope["method"]["fitted_artifact"]["sha256"] == sha256_file(MANIFEST)
        assert envelope["evidence"]["synthetic"] is True and envelope["evidence"]["visibility"] == "not_published"
        payload = store.read_payload(envelope["payload"])
        assert common.structural_errors(payload, "ica_scores") == []
        assert payload["kind"] == "ica_scores/1" and payload["synthetic"] is True
        assert (payload["family_id"], payload["variant"]) == (family, variant)
        assert payload["execution_path"]["used"] == ("icalens" if ica.icalens_status()["importable"] else "numpy")
        assert "no real model was run" in payload["identity"]["parity"]
    assert values(store.read_payload(envelopes[("fam-1", "clinical")]["payload"])) == [3.0, -4.0, 0.0, 0.0]
    again = store.run_fixture(plan, "w1", fixtures_dir=FX, protocol=protocol)
    assert again["executed"] == 0 and again["reused"] == summary["by_state"]["completed"]
    collected = store.collect()
    done = [r for r in collected["assembly"]["tasks"] if r["method"] == "ica_lens"]
    assert len(done) == 9 and {r["execution"] for r in done} == {"completed"}
    from scripts.experiments.compare import compare_run

    comparison = compare_run(store.run_dir)
    block = comparison["families"][0]["comparisons"][0]["ica"]     # fam-1, clinical against colloquial
    assert block["basis_manifest_sha256"] == sha256_file(MANIFEST)
    assert [c["difference_a_minus_b"] for c in block["layers"][0]["components"]] == [6.0, -8.0, 0.0, 0.0]


def test_a_payload_filed_for_another_task_or_edited_is_refused(matrix: dict) -> None:
    protocol = ica_protocol()
    context = {"fixtures_dir": FX, "protocol": protocol}
    task = task_for(protocol, matrix, "fam-1", "clinical")
    payload = ica.ADAPTER.execute_fixture(task, context)
    ica.ADAPTER.validate_payload(payload, task, context)

    def refused(edit: Callable[[dict], None], other_task: dict | None = None) -> str:
        changed = copy.deepcopy(payload)
        edit(changed)
        return code_of(lambda: ica.ADAPTER.validate_payload(changed, other_task or task, context))

    assert refused(lambda p: None, task_for(protocol, matrix, "fam-1", "colloquial")) == "row_alignment"
    assert refused(lambda p: p["basis"].update(manifest_sha256="0" * 64)) == "basis_mismatch"
    assert refused(lambda p: p["basis"].update(preprocessing_mode="l2")) == "preprocessing_mismatch"
    assert refused(lambda p: p["energy_share"].update(label="probability")) == "payload_labels"
    assert refused(lambda p: p["basis"].update(sign_convention="canonical")) == "payload_labels"
    assert refused(lambda p: p["rows"][0].update(token_id=0)) == "row_alignment"
    assert refused(lambda p: p["scores"].pop()) == "dimension_mismatch"
    assert refused(lambda p: p["scores"][0].update(energy_share=None)) == "non_finite"
    assert refused(lambda p: p["scores"][0].update(score=float("nan"))) == "non_finite"
    assert refused(lambda p: p["execution_path"].update(used="guess")) == "execution_path"
    assert refused(lambda p: p["component_annotations"][0].update(status="verified")) == "annotation_status"
    assert refused(lambda p: p["component_annotations"][0].update(verified=True)) == "annotation_status"
    assert refused(lambda p: p["component_annotations"][0].update(component=9)) == "annotation_status"
    assert refused(lambda p: p.update(understanding_score=1.0)) == "payload_structure"
    assert refused(lambda p: p.update(kind="lens_readout_report/1")) == "payload_kind"

    # Fixed statements must equal the module's constants. Each replacement below keeps the type and used to pass.
    statements = {
        "parity": lambda p: p["identity"].update(parity="established: scores match the real model"),
        "diagnostics": lambda p: p["basis"].update(fit_diagnostics_statement="The fit converged."),
        "annotation": lambda p: p.update(annotation_statement="Labels are verified."),
        "score_definition": lambda p: p.update(score_definition="importance of each component"),
        "energy_definition": lambda p: p["energy_share"].update(definition="probability of each component"),
        "reconstruction_definition": lambda p: p["reconstruction"].update(definition="exact"),
        "restore_norm": lambda p: p["reconstruction"].update(restore_norm="applied"),
        "limitations_emptied": lambda p: p.update(limitations=[]),
        "limitation_dropped": lambda p: p["limitations"].remove("no_real_model_parity"),
        "synthetic_limitation_dropped": lambda p: p["limitations"].remove("synthetic_not_measurement"),
    }
    for name, edit in statements.items():
        assert refused(edit) == "payload_labels", name
    extra = copy.deepcopy(payload)
    extra["limitations"].append("one_more_limit_named_by_the_manifest")          # a superset is accepted
    ica.ADAPTER.validate_payload(extra, task, context)
    assert refused(lambda p: p["basis"].update(synthetic=False)) == "synthetic_label"
    assert refused(lambda p: p["basis"].update(fit_split="validation")) == "split_leakage"
    assert refused(lambda p: p["identity"].update(basis="unknown")) == "unknown_identity"
    assert refused(lambda p: p["capture"].update(site="mlp_out")) == "layer_metadata"
    assert refused(lambda p: p["capture"].update(activation_site="")) == "layer_metadata"
    assert refused(lambda p: p["capture"]["activation_dataset"].update(layer_sha256={})) == "artifact_hash"
    assert refused(lambda p: p["capture"]["activation_dataset"].update(file_pins="trusted")) == "artifact_hash"
    assert refused(lambda p: p["capture"]["activation_dataset"].pop("samples_sha256")) == "payload_structure"
    assert refused(lambda p: p["split_leakage_checks"].update(fit_stage_ids="fine")) == "split_leakage"
    assert refused(lambda p: p["split_leakage_checks"].pop("profile_stage_ids")) == "split_leakage"
    # The exact key set of check_split_leakage and, per key, its closed list of words. Each edit below keeps
    # the type (a string under a string key) and used to pass: only the three stage keys were constrained.
    checks = payload["split_leakage_checks"]
    assert set(checks) == set(ica.LEAKAGE_WORDS) and len(ica.LEAKAGE_WORDS) == 7
    assert all(checks[key] in words for key, words in ica.LEAKAGE_WORDS.items())
    for key, words in ica.LEAKAGE_WORDS.items():
        assert refused(lambda p: p["split_leakage_checks"].update({key: "passed"})) == "split_leakage", key
        assert refused(lambda p: p["split_leakage_checks"].update({key: ""})) == "split_leakage", key
        assert refused(lambda p: p["split_leakage_checks"].pop(key)) == "split_leakage", key
        foreign = next(word for other in ica.LEAKAGE_WORDS.values() for word in other if word not in words)
        assert refused(lambda p: p["split_leakage_checks"].update({key: foreign})) == "split_leakage", key
    assert refused(lambda p: p["split_leakage_checks"].update(holdout_overlap="checked")) == "split_leakage"
    assert refused(lambda p: p["split_leakage_checks"].update(fit_dataset_row_map="fit_dataset_not_supplied")) == (
        "split_leakage")                                # the file pins say a fit dataset was supplied
    for word in ("checked_without_token_hashes", "fit_dataset_has_no_row_map"):     # words the adapter reports
        reworded = copy.deepcopy(payload)
        reworded["split_leakage_checks"]["fit_dataset_row_map"] = word
        ica.ADAPTER.validate_payload(reworded, task, context)

    # Shares are recomputed from the scores. The scores here are [3, -4, 0, 0]: shares [0.36, 0.64, 0, 0].
    assert values(payload) == [3.0, -4.0, 0.0, 0.0] and values(payload, "energy_share") == [0.36, 0.64, 0.0, 0.0]

    def shares(*new: float | None) -> Callable[[dict], None]:
        def edit(p: dict) -> None:
            for row, share in zip(p["scores"], new):
                row["energy_share"] = share
        return edit

    assert refused(shares(1.0, 0.0, 0.0, 0.0)) == "energy_share_mismatch"       # sums to 1, and is invented
    assert refused(shares(0.64, 0.36, 0.0, 0.0)) == "energy_share_mismatch"     # the right numbers, swapped
    assert refused(shares(0.36 + 1e-6, 0.64 - 1e-6, 0.0, 0.0)) == "energy_share_mismatch"
    assert refused(lambda p: p["energy_share"]["rows"][0].update(total_squared=1.0)) == "energy_share_mismatch"
    assert refused(lambda p: p["scores"][0].update(score=4.0)) == "energy_share_mismatch"

    def zeroed(p: dict) -> None:
        shares(None, None, None, None)(p)
        p["energy_share"]["rows"][0]["status"] = "not_computed_zero_energy"
    assert refused(zeroed) == "energy_share_mismatch"                           # non-zero scores, "undefined" shares
    assert refused(lambda p: p["energy_share"]["rows"].clear()) == "dimension_mismatch"
    assert refused(lambda p: p["reconstruction"]["rows"].clear()) == "dimension_mismatch"

    # fam-1 normalized has a residual: error 5, norm 13, relative 5/13.
    other_task = task_for(protocol, matrix, "fam-1", "normalized")
    other = ica.ADAPTER.execute_fixture(other_task, context)
    ica.ADAPTER.validate_payload(other, other_task, context)
    hidden = copy.deepcopy(other)
    hidden["reconstruction"]["rows"][0]["relative_l2_error"] = 0.0
    assert code_of(lambda: ica.ADAPTER.validate_payload(hidden, other_task, context)) == "reconstruction_mismatch"
    # The all-zero row of fam-2 colloquial keeps null shares, and zeros in their place are refused.
    zero_task = task_for(protocol, matrix, "fam-2", "colloquial")
    zero = ica.ADAPTER.execute_fixture(zero_task, context)
    ica.ADAPTER.validate_payload(zero, zero_task, context)
    filled = copy.deepcopy(zero)
    shares(0.0, 0.0, 0.0, 0.0)(filled)
    assert code_of(lambda: ica.ADAPTER.validate_payload(filled, zero_task, context)) == "non_finite"


def test_a_basis_manifest_with_changed_statements_or_missing_limitations_is_refused(tmp_path: Path) -> None:
    manifest = read(MANIFEST)
    assert code_of(lambda: ica.validate_basis_manifest({**manifest, "limitations": []})) == "basis_manifest"
    assert code_of(lambda: ica.validate_basis_manifest(
        {**manifest, "limitations": [x for x in manifest["limitations"] if x != "synthetic_not_measurement"]})) == (
        "basis_manifest")
    assert code_of(lambda: ica.validate_basis_manifest(
        {**manifest, "annotation_statement": "Labels are verified concepts."})) == "basis_manifest"


def test_a_synthetic_basis_is_not_scored_under_a_protocol_that_is_not_synthetic(matrix: dict) -> None:
    protocol = ica_protocol()
    task = task_for(protocol, matrix, "fam-1", "clinical")
    real = {**protocol, "synthetic": False}
    with pytest.raises(Refusal) as caught:
        ica.score_task(task, real, basis=ica.load_basis(MANIFEST), dataset=ad.open_activation_dataset(PAIRS))
    assert caught.value.code == "synthetic_label"


# ---------------------------------------------------------------------------------------- input identity

def test_input_identity_names_every_input_outside_the_task_spec(tmp_path: Path, matrix: dict,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    protocol = ica_protocol()
    task = task_for(protocol, matrix, "fam-1", "clinical")
    fixtures = copy_fixtures(tmp_path)
    context = {"fixtures_dir": fixtures, "protocol": protocol}
    listing = sorted(path.relative_to(fixtures).as_posix() for path in fixtures.rglob("*"))

    def no_decoding(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("input_identity decoded an array; it must only hash files")
    with monkeypatch.context() as patch:
        patch.setattr(np, "frombuffer", no_decoding)
        patch.setattr(ad, "parse_safetensors", no_decoding)
        record = ica.ADAPTER.input_identity_record(task, context)
        digest = ica.ADAPTER.input_identity(task, context)

    def sha(relative: str) -> str:
        return hashlib.sha256((fixtures / "ica" / relative).read_bytes()).hexdigest()

    engine = Path(ica.__file__).resolve().parents[3]
    assert json.loads(json.dumps(record)) == record                  # JSON-serializable as it stands
    assert record["schema_version"] == "patientwords.ica-input-identity/1"
    assert record["adapter_source_sha256"] == {
        name: hashlib.sha256((engine / name).read_bytes()).hexdigest()
        for name in ("scripts/experiments/adapters/ica.py", "scripts/experiments/activation_dataset.py")}
    assert record["basis"] == {"manifest_sha256": sha("basis_manifest.json"), "artifact_files": [
        {"path": LAYER_FILE, "sha256": sha(f"toy_basis/{LAYER_FILE}")},
        {"path": "icalens.json", "sha256": sha("toy_basis/icalens.json")}]}
    assert record["activation_dataset"] == {
        "manifest_sha256": sha("pair_activations/activations.json"),
        "samples_sha256": sha("pair_activations/samples.safetensors"),
        "layer_sha256": {"1": sha("pair_activations/layers/layer_01.float32.bin")}}
    assert record["fit_dataset"] == {
        "manifest_sha256": sha("discovery_activations/activations.json"),
        "samples_sha256": sha("discovery_activations/samples.safetensors"),
        "layer_sha256": {"1": sha("discovery_activations/layers/layer_01.float32.bin")}}
    assert record["execution"]["requested_path"] == "auto" and set(record["execution"]["package_versions"]) == {
        "numpy", "icalens", "torch"}
    assert common.HEX64.fullmatch(digest) and digest == common.digest(record)
    assert ica.ADAPTER.input_identity(task, context) == digest       # the same inputs give the same value
    # Nothing was written and nothing was cached in the context.
    assert sorted(path.relative_to(fixtures).as_posix() for path in fixtures.rglob("*")) == listing
    assert set(context) == {"fixtures_dir", "protocol"}

    # Each input changes the value: layer bytes under an unchanged manifest, a basis tensor, the fit dataset.
    seen = {digest}
    reverse_layer_rows(fixtures / "ica" / "pair_activations")
    layer = fixtures / "ica" / "toy_basis" / LAYER_FILE
    for change in (lambda: None,                                     # the reversed layer file above
                   lambda: layer.write_bytes(layer.read_bytes()[:-1] + b"\x01"),
                   lambda: rewrite_json(fixtures / "ica" / "discovery_activations" / "activations.json",
                                        lambda d: d["provenance"].update(note="edited")),
                   lambda: rewrite_json(fixtures / "ica" / "basis_manifest.json",
                                        lambda d: d.update(description="edited"))):
        change()
        value = ica.ADAPTER.input_identity(task, context)
        assert value not in seen and common.HEX64.fullmatch(value)
        seen.add(value)
    assert ica.ADAPTER.input_identity(task, {**context, "ica_path": "numpy"}) not in seen

    # Absent inputs: no exception. The hook value is None; the record keeps what could be read.
    (fixtures / "ica" / "pair_activations" / "layers" / "layer_01.float32.bin").unlink()
    assert ica.ADAPTER.input_identity(task, context) is None
    assert ica.ADAPTER.input_identity_record(task, context)["activation_dataset"]["layer_sha256"] == {"1": None}
    shutil.rmtree(fixtures / "ica")
    assert ica.ADAPTER.input_identity(task, context) is None
    bare = ica.ADAPTER.input_identity_record(task, context)
    assert (bare["basis"], bare["activation_dataset"], bare["fit_dataset"]) == (None, None, None)
    assert ica.ADAPTER.input_identity(task) is None
    assert ica.ADAPTER.input_identity_record(task)["adapter_source_sha256"] == record["adapter_source_sha256"]


def test_unknown_identity_and_incomplete_data_are_unavailable_not_failed(tmp_path: Path, matrix: dict) -> None:
    fixtures = copy_fixtures(tmp_path / "a")
    rewrite_json(fixtures / "ica" / "pair_activations" / "activations.json", lambda d: d["model"].pop("revision"))
    store, _, summary = run(tmp_path / "a", ica_protocol(), matrix, fixtures)
    envelopes = ica_envelopes(store)
    assert {e["status"]["execution"] for e in envelopes.values()} == {"unavailable"}
    assert all(e["status"]["reason"].startswith("unknown_identity: the activation dataset")
               and e["payload"] is None for e in envelopes.values())
    assert summary["by_state"]["failed"] == 0 and summary["by_state"]["invalid"] == 0

    fixtures = copy_fixtures(tmp_path / "b")

    def forget(manifest: dict) -> None:
        manifest["model"]["revision"] = None
        manifest["not_recorded"] = ["/model/revision"]
    rewrite_json(fixtures / "ica" / "basis_manifest.json", forget)
    store, _, _ = run(tmp_path / "b", ica_protocol(fixtures / "ica" / "basis_manifest.json"), matrix, fixtures)
    reasons = {e["status"]["execution"]: e["status"]["reason"] for e in ica_envelopes(store).values()}
    assert list(reasons) == ["unavailable"] and reasons["unavailable"].startswith("unknown_identity: the basis")

    fixtures = copy_fixtures(tmp_path / "c")
    rewrite_json(fixtures / "ica" / "pair_activations" / "activations.json", lambda d: d.update(status="capturing"))
    store, _, _ = run(tmp_path / "c", ica_protocol(), matrix, fixtures)
    reasons = {e["status"]["execution"]: e["status"]["reason"] for e in ica_envelopes(store).values()}
    assert list(reasons) == ["unavailable"] and reasons["unavailable"].startswith("incomplete: ")

    # The protocol names a basis that is not in the fixtures.
    store, _, _ = run(tmp_path / "d", ica_protocol(manifest_sha256="a" * 64), matrix)
    reasons = {e["status"]["execution"]: e["status"]["reason"] for e in ica_envelopes(store).values()}
    assert list(reasons) == ["unavailable"] and "is not in the fixtures" in reasons["unavailable"]


def test_altered_artifacts_misaligned_rows_and_interventions_through_the_store(tmp_path: Path, matrix: dict) -> None:
    fixtures = copy_fixtures(tmp_path / "a")
    layer = fixtures / "ica" / "toy_basis" / LAYER_FILE
    data = bytearray(layer.read_bytes())
    data[-3] ^= 0x40
    layer.write_bytes(bytes(data))
    store, _, _ = run(tmp_path / "a", ica_protocol(), matrix, fixtures)
    states = {(e["status"]["execution"], e["status"]["reason"].split(":")[0]) for e in ica_envelopes(store).values()}
    assert states == {("invalid", "artifact_hash")}

    fixtures = copy_fixtures(tmp_path / "b")
    samples_with(set_value("token_id", 20, 0))(fixtures / "ica" / "pair_activations")
    store, _, _ = run(tmp_path / "b", ica_protocol(), matrix, fixtures)
    states = {(e["status"]["execution"], e["status"]["reason"].split(":")[0]) for e in ica_envelopes(store).values()}
    assert states == {("invalid", "row_alignment")}                # the whole dataset is refused, not one row

    # Layer rows reversed under an unchanged manifest: refused through the store, with no payload.
    fixtures = copy_fixtures(tmp_path / "d")
    reverse_layer_rows(fixtures / "ica" / "pair_activations")
    store, _, _ = run(tmp_path / "d", ica_protocol(), matrix, fixtures)
    envelopes = ica_envelopes(store)
    assert {(e["status"]["execution"], e["status"]["reason"].split(":")[0]) for e in envelopes.values()} == {
        ("invalid", "artifact_hash")}
    assert all(e["payload"] is None for e in envelopes.values())

    # A dataset captured at another site than the basis, with the same layer number, width and model.
    fixtures = copy_fixtures(tmp_path / "e")
    rewrite_json(fixtures / "ica" / "pair_activations" / "activations.json",
                 lambda d: d.update(activation_site="mlp_out", layer_indexing="hidden_states"))
    store, _, _ = run(tmp_path / "e", ica_protocol(), matrix, fixtures)
    states = {(e["status"]["execution"], e["status"]["reason"].split(":")[0]) for e in ica_envelopes(store).values()}
    assert states == {("invalid", "layer_metadata")}

    store, _, _ = run(tmp_path / "c", ica_protocol(steer={"component": 1, "offset": 2.0}), matrix)
    envelopes = ica_envelopes(store)
    assert {e["status"]["execution"] for e in envelopes.values()} == {"unsupported"}
    assert all("unsupported_operation" in e["status"]["reason"] and e["payload"] is None for e in envelopes.values())


def test_the_adapter_lists_the_dataset_module_among_the_sources_that_stop_reuse() -> None:
    """Review, 2026-11-10: envelopes recorded ica.py only, so a change to activation_dataset.py, which the
    scoring reads every dataset through, did not stop reuse of an earlier payload."""
    from scripts.experiments import store

    hashes = store._source_hashes(ica.IcaAdapter())
    assert "scripts/experiments/activation_dataset.py" in hashes
    assert "scripts/experiments/adapters/ica.py" in hashes
