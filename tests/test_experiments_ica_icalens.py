"""Checks against the real ``icalens`` package (the reference implementation), on toy data.

These tests need ``torch``, ``safetensors`` and ``icalens``, which the engine environment does not have. They
skip there with the reason below. They run in an isolated environment (see ``docs/experiments/ica_adapter.md``,
section "Running the reference checks")::

    /home/user/.venvs/ica/bin/python -m pytest -q -p no:cacheprovider tests/test_experiments_ica_icalens.py

What a pass shows: the reference reader reads the ActivationDataset bytes this repository writes; this
repository's safetensors bytes equal the ``safetensors`` writer's; this repository's reader reads what the
reference writer produces (bfloat16 included); and, for a small lens fitted by ``icalens`` on 48 synthetic rows,
the numpy path and ``icalens`` give the same scores and reconstructions within the stated tolerances.

What a pass does not show: anything about a real model, a real corpus, a released basis, convergence of a fit,
or speed. The fit here has 48 rows of width 8.
"""
from __future__ import annotations

import json
import resource
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.experiments import activation_dataset as ad
from scripts.experiments import capabilities, planner
from scripts.experiments.adapters import ica
from scripts.experiments.common import json_bytes, sha256_file
from scripts.experiments.store import RunStore

STATUS = ica.icalens_status()
pytestmark = pytest.mark.skipif(
    not STATUS["importable"],
    reason=("icalens and torch are not importable in this environment "
            f"({STATUS['import_error']}). The reference checks run in an isolated environment: "
            "/home/user/.venvs/ica/bin/python -m pytest tests/test_experiments_ica_icalens.py"))

FX = Path(__file__).resolve().parent / "fixtures" / "experiments"
ICA = FX / "ica"
PAIRS = ICA / "pair_activations"
DISCOVERY = ICA / "discovery_activations"

# Stated tolerances.
FLOAT64_TOLERANCE = 1e-9      # both paths in float64: absolute, relative to max(1, largest |value|)
FLOAT32_TOLERANCE = 1e-4      # icalens given float32 rows (it then computes in float32), same scale
MIN_COSINE = 1.0 - 1e-9
FIT = {"n_components": 4, "max_iter": 50, "random_state": 7}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fit_lens(mode: str | None, **changes: Any) -> Any:
    """Fit a small lens on the toy discovery rows through the Python API, on CPU, with explicit settings."""
    import icalens

    dataset = icalens.ActivationDataset(DISCOVERY)
    arguments = {"model_id": dataset.model["repo_id"], "model_revision": dataset.model["revision"],
                 "model_type": dataset.model["type"], "activation_site": "resid_post",
                 "layer_indexing": "transformer_blocks_zero_based"}
    if mode is not None:
        arguments["icalens_preprocessing"] = mode
    lens = icalens.ICALens(**arguments)
    lens.fit(dataset.layer(1), layer=1, device="cpu", provenance=dataset.provenance, **{**FIT, **changes})
    return lens


def manifest_for(lens_dir: Path, artifact_root: str) -> dict:
    discovery = ad.open_activation_dataset(DISCOVERY)
    return ica.build_basis_manifest(
        lens_dir, basis_id="fixture/toy-fitted-basis", synthetic=True, artifact_root=artifact_root,
        description="SYNTHETIC. A lens fitted by icalens on 48 toy rows, for a path comparison only.",
        tokenizer_id="fixture/toy-tokenizer", tokenizer_revision="1" * 40,
        fit={"corpus_id": "toy-discovery-corpus-1", "split": "discovery", "corpus_ids": ["toy-discovery-corpus-1"],
             "document_token_sha256": sorted({d["token_sha256"] for d in discovery.row_map["documents"]}),
             "activation_manifest_sha256": discovery.manifest_sha256,
             "description": "The toy discovery corpus of tests/fixtures/experiments/ica."},
        capture_site="block_output", layer_index_base=0, model_load_precision="not_applicable_no_model")


def save_with_manifest(lens: Any, root: Path) -> Path:
    lens.save(root / "lens")
    path = root / "basis_manifest.json"
    path.write_bytes(json_bytes(manifest_for(root / "lens", "lens")))
    return path


def gaps(left: np.ndarray, right: np.ndarray) -> tuple[float, float, float]:
    """``(max abs difference, scale, min row cosine)``: a magnitude check and a direction check."""
    cosines = [float(a @ b) / (float(np.linalg.norm(a)) * float(np.linalg.norm(b)))
               for a, b in zip(left, right) if np.linalg.norm(a) > 0 and np.linalg.norm(b) > 0]
    return float(np.abs(left - right).max()), max(1.0, float(np.abs(right).max())), min(cosines)


# ------------------------------------------------------------------------------------------------- format

@pytest.mark.parametrize("root", [DISCOVERY, PAIRS])
def test_the_reference_reader_reads_the_dataset_this_writer_produced(root: Path) -> None:
    import icalens
    import torch

    mine = ad.read_activation_dataset(root)
    theirs = icalens.ActivationDataset(root)
    assert theirs.available_layers == mine.layers == (1,)
    assert (theirs.sample_count, theirs.hidden_size, theirs.dtype) == (mine.sample_count, 8, torch.float32)
    layer = theirs.layer(1)
    assert tuple(layer.shape) == (mine.sample_count, 8) and layer.dtype == torch.float32
    assert np.array_equal(layer.numpy(), mine.layer(1))
    samples = theirs.samples()                                     # the reference reader's own validation
    assert set(samples) == set(ad.REQUIRED_SAMPLE_TENSORS)
    for name, tensor in samples.items():
        assert tensor.dtype == torch.int64 and np.array_equal(tensor.numpy(), mine.samples()[name])
    # A lens fitted through icalens records this hash, so the two readers must agree on it.
    assert theirs.provenance["activation_dataset"]["manifest_sha256"] == mine.manifest_sha256
    assert theirs.model == mine.manifest["model"]


@pytest.mark.parametrize("dtype", ["float16", "float64"])
def test_the_reference_reader_reads_the_other_dtypes_this_writer_emits(tmp_path: Path, dtype: str) -> None:
    import icalens

    source = ad.open_activation_dataset(PAIRS)
    written = ad.write_activation_dataset(
        tmp_path / dtype, model=source.manifest["model"], layers={1: source.layer(1)}, samples=source.samples(),
        provenance=source.manifest["provenance"], dtype=dtype)
    theirs = icalens.ActivationDataset(tmp_path / dtype)
    assert str(theirs.dtype) == f"torch.{dtype}"
    assert np.array_equal(theirs.layer(1).numpy(), written.layer(1))


def test_this_reader_reads_what_the_reference_writer_produces_including_bfloat16(tmp_path: Path) -> None:
    import torch
    from icalens._activation_dataset import ActivationDataset, ActivationDatasetWriter

    values = torch.tensor([[1.0, -2.0, 0.3], [4.5, 1e-3, -7.25], [100.0, 0.0, 3.14159]], dtype=torch.bfloat16)
    samples = {"document_index": torch.tensor([0, 0, 1]), "position": torch.tensor([0, 1, 0]),
               "token_id": torch.tensor([5, 6, 7])}
    writer = ActivationDatasetWriter(
        tmp_path / "theirs", model={"repo_id": "fixture/toy-model", "revision": "1" * 40, "type": "base"},
        activation_site="resid_post", layer_indexing="transformer_blocks_zero_based", layers=(0,), sample_count=3,
        hidden_size=3, dtype=torch.bfloat16, provenance={"synthetic": True}, samples=samples)
    with writer.group((0,)) as sink:
        sink.append({0: values})
    writer.finish()
    ActivationDataset(tmp_path / "theirs").samples()
    mine = ad.read_activation_dataset(tmp_path / "theirs")
    assert mine.dtype == "bfloat16" and mine.layer(0).dtype == np.dtype("<f4")
    assert np.array_equal(mine.layer(0), values.float().numpy())   # bfloat16 to float32 is exact
    assert {k: v.tolist() for k, v in mine.samples().items()} == {k: v.tolist() for k, v in samples.items()}
    # No tokenizer is recorded by the reference writer, so identity is unknown here, not guessed.
    assert mine.identity["status"] == "unknown" and mine.row_map is None


def test_safetensors_bytes_equal_the_reference_writer_and_both_readers_agree(tmp_path: Path) -> None:
    from safetensors.numpy import load_file, save

    samples = ad.open_activation_dataset(PAIRS).samples()
    assert save(samples) == ad.safetensors_bytes(samples) == (PAIRS / "samples.safetensors").read_bytes()
    layer_file = ICA / "toy_basis" / "artifacts" / "resid_post" / "layer_01.safetensors"
    tensors = load_file(layer_file)                                # the reference reader on this writer's bytes
    assert save(tensors) == layer_file.read_bytes()
    mixed = {"z": np.arange(6, dtype=np.float32).reshape(2, 3), "b": np.array([7, 8], dtype=np.int64),
             "a": np.linspace(0, 1, 5, dtype=np.float64), "h": np.ones(3, dtype=np.float16),
             "i": np.array([1, -1], dtype=np.int32)}
    assert save(mixed) == ad.safetensors_bytes(mixed)
    back = ad.parse_safetensors(save(mixed))                       # this reader on the reference writer's bytes
    assert all(np.array_equal(back[name], value) and back[name].dtype == value.dtype
               for name, value in mixed.items())


# ---------------------------------------------------------------------------------------- the toy basis

def test_icalens_loads_the_hand_written_basis_and_gives_the_hand_computed_values() -> None:
    import icalens

    lens = icalens.ICALens.from_pretrained(ICA / "toy_basis")
    assert lens.icalens_preprocessing == "none" and lens.available_layers == (1,)
    x = np.array([[0, -2, 0, -1, 0, 0, 0, 0], [8, 8, 4, 0, 0, 0, 3, 4]], dtype=np.float64)
    scores = lens.transform(x, layer=1)
    assert scores.tolist() == [[3.0, -4.0, 0.0, 0.0], [1.0, 6.0, 2.0, 1.0]]
    assert np.allclose(lens.energy(scores), [[0.36, 0.64, 0, 0], [1 / 42, 36 / 42, 4 / 42, 1 / 42]], atol=1e-15)
    assert lens.inverse_transform(scores, layer=1).tolist() == [[0, -2, 0, -1, 0, 0, 0, 0], [8, 8, 4, 0, 0, 0, 0, 0]]
    result = ica.apply_basis(ica.load_basis(ICA / "basis_manifest.json"), x, layer=1, path="icalens")
    assert result["execution_path"]["used"] == "icalens"
    assert result["execution_path"]["icalens_version"] == icalens.__version__
    assert result["execution_path"]["cross_check"]["max_abs_score_difference"] == 0.0
    assert result["l2_error"].tolist() == [0.0, 5.0]
    # icalens returns zeros for the shares of an all-zero score row; this adapter records them as undefined.
    zero = ica.apply_basis(ica.load_basis(ICA / "basis_manifest.json"),
                           np.array([[1, 2, 0, -1, 0, 0, 0, 0]], dtype=np.float64), layer=1, path="icalens")
    assert lens.energy(np.zeros((1, 4))).tolist() == [[0.0] * 4] and np.isnan(zero["energy_share"]).all()
    assert zero["energy_status"] == ["not_computed_zero_energy"]


# ------------------------------------------------------------------------- fit, save, manifest and parity

@pytest.mark.parametrize("mode", ["none", "l2", "geometric-median-l2"])
def test_numpy_path_and_icalens_agree_on_a_lens_fitted_by_icalens(tmp_path: Path, mode: str,
                                                                  record_property: Any) -> None:
    import icalens
    import torch

    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    clock = time.perf_counter()
    lens = fit_lens(mode)
    seconds = time.perf_counter() - clock
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    manifest_path = save_with_manifest(lens, tmp_path)
    saved, manifest = read(tmp_path / "lens" / "icalens.json"), read(manifest_path)

    # The mode is read from the saved artifact, and it is the one passed explicitly to the constructor.
    assert manifest["preprocessing"]["mode"] == saved["input_preprocessing"]["icalens_preprocessing"] == mode
    assert manifest["preprocessing"]["read_from"] == "icalens.json#/input_preprocessing/icalens_preprocessing"
    settings = manifest["layers"]["1"]["fit_settings"]
    assert {k: settings[k] for k in ("algorithm", "ica_algorithm", "fun", "max_iter", "n_iter", "n_components",
                                     "n_samples", "stopping_criterion", "seed", "fit_device", "input_dtype")} == {
        "algorithm": "fastica", "ica_algorithm": "parallel", "fun": "logcosh", "max_iter": 50, "n_iter": 50,
        "n_components": 4, "n_samples": 48, "stopping_criterion": "fixed_iterations", "seed": 7,
        "fit_device": "cpu", "input_dtype": "float32"}
    assert settings["torch_version"] == torch.__version__ and manifest["seed"] == 7
    diagnostics = manifest["layers"]["1"]["fit_diagnostics"]
    assert diagnostics["objective_history"]["iterations"] == list(range(1, 51))
    assert len(diagnostics["component_strengths"]) == 4 and len(diagnostics["component_objectives"]) == 4
    assert manifest["artifact"]["package_version"] == saved["package_version"]
    assert manifest["fit"]["activation_manifest_sha256"] == saved["layers"]["1"]["fitting"]["provenance"][
        "activation_dataset"]["manifest_sha256"]
    assert {e["path"]: e["sha256"] for e in manifest["artifact"]["files"]} == {
        p.relative_to(tmp_path / "lens").as_posix(): sha256_file(p)
        for p in (tmp_path / "lens").rglob("*") if p.is_file()}
    assert ("preprocessing_center" in manifest["layers"]["1"]["tensors"]) == (mode == "geometric-median-l2")

    basis = ica.load_basis(manifest_path)
    rows = ad.open_activation_dataset(PAIRS).layer(1)              # the 24 toy pair rows, float32
    numpy_result = ica.apply_basis(basis, rows, layer=1, path="numpy")
    reference = icalens.ICALens.from_pretrained(tmp_path / "lens")
    scores64 = np.asarray(reference.transform(rows.astype(np.float64), layer=1))
    recon64 = np.asarray(reference.inverse_transform(scores64, layer=1))
    gap, scale, cosine = gaps(numpy_result["scores"], scores64)
    assert gap <= FLOAT64_TOLERANCE * scale and cosine >= MIN_COSINE
    x_pre = ica.preprocess(basis.layers[1], basis.mode, basis.preprocessing["norm_eps"], rows)
    error64 = np.linalg.norm(x_pre - recon64, axis=1)
    assert np.abs(numpy_result["l2_error"] - error64).max() <= FLOAT64_TOLERANCE * max(1.0, float(error64.max()))
    # icalens given the stored float32 rows computes in float32: the same values to float32 accuracy.
    scores32 = np.asarray(reference.transform(rows, layer=1), dtype=np.float64)
    gap32, scale32, cosine32 = gaps(numpy_result["scores"], scores32)
    assert gap32 <= FLOAT32_TOLERANCE * scale32 and cosine32 >= 1.0 - 1e-6
    # The numpy code path of icalens repeats the same float64 operations, so a gap of exactly zero is expected
    # there. Its torch code path is a different numerical backend on the same matrices.
    scores_torch = reference.transform(torch.from_numpy(rows.astype(np.float64)), layer=1).numpy()
    gap_torch, _, cosine_torch = gaps(numpy_result["scores"], scores_torch)
    assert gap_torch <= FLOAT64_TOLERANCE * scale and cosine_torch >= MIN_COSINE
    through = ica.apply_basis(basis, rows, layer=1, path="auto")
    assert through["execution_path"]["used"] == "icalens"
    assert through["execution_path"]["cross_check"]["max_abs_score_difference"] <= FLOAT64_TOLERANCE * scale
    # A full-rank reconstruction is not expected: 4 components of 8 dimensions leave a residual.
    assert float(numpy_result["l2_error"].max()) > 0.0
    for name, value in (("fit_wall_seconds", seconds), ("peak_rss_kb_before_fit", before),
                        ("peak_rss_kb_after_fit", after), ("float64_max_abs_score_gap", gap),
                        ("float64_min_cosine", cosine), ("float64_torch_backend_max_abs_score_gap", gap_torch),
                        ("float32_max_abs_score_gap", gap32),
                        ("score_scale", scale)):
        record_property(f"{mode}:{name}", value)
    print(f"\n[toy fit, mode={mode}] wall {seconds:.3f}s; process peak RSS {before} -> {after} kB; "
          f"float64 gap {gap:.3e} (scale {scale:.3g}), min cosine {cosine:.12f}; torch-backend float64 gap "
          f"{gap_torch:.3e}; float32-input gap {gap32:.3e}")


def test_the_constructor_default_is_l2_so_the_mode_must_be_passed_and_read_back(tmp_path: Path) -> None:
    """``ICALens(...)`` without a mode normalizes rows; the fitting CLIs default to ``none``. The adapter
    therefore never assumes a mode: the manifest carries whatever the saved artifact records."""
    lens = fit_lens(None)
    manifest = read(save_with_manifest(lens, tmp_path))
    assert read(tmp_path / "lens" / "icalens.json")["input_preprocessing"]["icalens_preprocessing"] == "l2"
    assert manifest["preprocessing"]["mode"] == "l2"


def test_a_cpu_fit_repeats_with_the_same_seed_and_differs_with_another() -> None:
    first, again, other = fit_lens("none"), fit_lens("none"), fit_lens("none", random_state=8)
    one, two, three = (lens._get_layer(1).reading_matrix for lens in (first, again, other))
    assert np.array_equal(one, two)                               # same seed, same device, same process
    assert not np.allclose(one, three)                            # another seed: other signs, order or values


def test_a_fitted_lens_runs_through_the_adapter_and_the_payload_names_the_icalens_path(tmp_path: Path) -> None:
    import icalens

    fixtures = tmp_path / "fixtures"
    shutil.copytree(FX, fixtures, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.rmtree(fixtures / "ica" / "toy_basis")
    fit_lens("none").save(fixtures / "ica" / "lens")
    manifest_path = fixtures / "ica" / "basis_manifest.json"
    manifest_path.write_bytes(json_bytes(manifest_for(fixtures / "ica" / "lens", "lens")))
    protocol = read(FX / "protocol_synthetic.json")
    method = read(ICA / "fixture_index.json")["method_block"]
    method["basis"]["manifest_sha256"] = sha256_file(manifest_path)
    protocol["methods"].append(method)
    plan = planner.build_plan(protocol, capabilities.load_matrix())
    store = RunStore(tmp_path / "run")
    store.run_fixture(plan, "w1", fixtures_dir=fixtures, protocol=protocol)
    payloads = [store.read_payload(doc["payload"]) for doc in map(read, store.envelope_files())
                if doc["method"]["id"] == "ica_lens" and doc["status"]["execution"] == "completed"]
    assert len(payloads) == 9
    for payload in payloads:
        path = payload["execution_path"]
        assert path["used"] == "icalens" and path["icalens_version"] == icalens.__version__
        assert path["cross_check_by_layer"]["1"]["max_abs_score_difference"] <= (
            FLOAT64_TOLERANCE * path["cross_check_by_layer"]["1"]["tolerance_scale"])
        assert payload["basis"]["seed"] == 7 and payload["basis"]["preprocessing_mode"] == "none"
        assert payload["split_leakage_checks"]["fit_dataset_row_map"] == "checked"
        assert "no real model was run" in payload["identity"]["parity"]
