"""Offline tests of the ActivationDataset reader/writer and the ICA adapter (numpy only).

Everything here is synthetic: a hand-written basis and hand-chosen activations. The expected numbers below are
literals worked out from ``B = [[1,1,0,0],[0,1,0,0],[0,0,1,2],[0,0,0,1]]``, ``center = [1,2,0,-1,0,0,0,0]`` and
``x = center + [B s ; t]`` (see ``tests/fixtures/experiments/ica/build_ica_fixtures.py``). A passing run shows
that the arithmetic and the refusals behave as specified on a toy. It shows nothing about a real model, a real
basis or parity with one; ``tests/test_experiments_ica_icalens.py`` compares against the ``icalens`` package.
"""
from __future__ import annotations

import copy
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


def samples_with(edit: Callable[[dict], None]) -> Callable[[Path], None]:
    def apply(root: Path) -> None:
        tensors = ad.read_safetensors(root / "samples.safetensors")
        edit(tensors)
        (root / "samples.safetensors").write_bytes(ad.safetensors_bytes(tensors))
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
    assert report == {"stage_ids": "checked", "document_token_hashes": "checked",
                      "fit_dataset_row_map": "checked", "scoring_dataset_is_fit_dataset": "checked"}
    unlisted = score(matrix, "fam-1", "clinical", manifest=plain, fit=None)["split_leakage_checks"]
    assert unlisted["document_token_hashes"] == "not_listed_in_manifest"
    assert unlisted["fit_dataset_row_map"] == "fit_dataset_not_supplied"


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
    assert refused(lambda p: p.update(understanding_score=1.0)) == "payload_structure"
    assert refused(lambda p: p.update(kind="lens_readout_report/1")) == "payload_kind"


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

    store, _, _ = run(tmp_path / "c", ica_protocol(steer={"component": 1, "offset": 2.0}), matrix)
    envelopes = ica_envelopes(store)
    assert {e["status"]["execution"] for e in envelopes.values()} == {"unsupported"}
    assert all("unsupported_operation" in e["status"]["reason"] and e["payload"] is None for e in envelopes.values())
