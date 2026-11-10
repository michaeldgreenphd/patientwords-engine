"""Manual integration run: fit a toy ICA Lens with the real ``icalens`` package and compare the two paths.

    /home/user/.venvs/ica/bin/python tests/manual/ica_bridge.py --out /path/outside/the/checkout/ica_bridge

Needs ``torch``, ``safetensors`` and ``icalens`` (version 0.4.0, from
``michaeldgreenphd/patientwords-ica-lens-paper``). The engine environment has none of them, so this script is
not collected by pytest and is not part of the offline path. It downloads nothing and loads no model.

Steps: the ``icalens`` reader opens the synthetic discovery ActivationDataset that this repository's writer
produced; ``ICALens.fit`` fits a small lens on its 48 rows on CPU with an explicit preprocessing mode, component
count, iteration budget and seed; the lens is saved; a basis manifest is built from the saved artifact; the numpy
path and ``icalens`` score the 24 synthetic pair rows; a receipt is written.

The receipt records wall time and process peak RSS for the fit. Both are measured on 48 rows of width 8. They
say nothing about a real model, a real corpus or the hardware a real fit needs.
"""
from __future__ import annotations

import argparse
import platform
import resource
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

ENGINE = Path(__file__).resolve().parents[2]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from scripts.experiments import activation_dataset as ad  # noqa: E402
from scripts.experiments.adapters import ica  # noqa: E402
from scripts.experiments.common import (  # noqa: E402
    Refusal, check_output_path, json_bytes, read_json, sha256_file,
)

FIXTURES = ENGINE / "tests" / "fixtures" / "experiments" / "ica"
MODES = ("none", "l2", "geometric-median-l2")


def installed(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not_installed_as_a_distribution"


def peak_rss_bytes() -> int:
    """Peak resident set size of this process so far. Linux reports kilobytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def run(out: Path, *, mode: str, n_components: int, max_iter: int, seed: int) -> dict[str, Any]:
    import icalens
    import torch

    discovery_path, pairs_path = FIXTURES / "discovery_activations", FIXTURES / "pair_activations"
    mine = ad.read_activation_dataset(discovery_path)
    theirs = icalens.ActivationDataset(discovery_path)
    theirs.samples()
    values = theirs.layer(1)
    format_agrees = bool(np.array_equal(values.numpy(), mine.layer(1))) and (
        theirs.provenance["activation_dataset"]["manifest_sha256"] == mine.manifest_sha256)

    lens = icalens.ICALens(model_id=theirs.model["repo_id"], model_revision=theirs.model["revision"],
                           model_type=theirs.model["type"], activation_site="resid_post",
                           layer_indexing="transformer_blocks_zero_based", icalens_preprocessing=mode)
    rss_before = peak_rss_bytes()
    clock = time.perf_counter()
    lens.fit(values, layer=1, n_components=n_components, max_iter=max_iter, random_state=seed, device="cpu",
             provenance=theirs.provenance)
    fit_seconds = time.perf_counter() - clock
    rss_after = peak_rss_bytes()
    lens_dir = lens.save(out / "lens")

    manifest = ica.build_basis_manifest(
        lens_dir, basis_id="fixture/toy-fitted-basis", synthetic=True, artifact_root="lens",
        description="SYNTHETIC. A lens fitted by icalens on 48 toy rows, for a path comparison only.",
        tokenizer_id="fixture/toy-tokenizer", tokenizer_revision="1" * 40,
        fit={"corpus_id": "toy-discovery-corpus-1", "split": "discovery", "corpus_ids": ["toy-discovery-corpus-1"],
             "document_token_sha256": sorted({d["token_sha256"] for d in mine.row_map["documents"]}),
             "activation_manifest_sha256": mine.manifest_sha256,
             "description": "The toy discovery corpus of tests/fixtures/experiments/ica."},
        capture_site="block_output", layer_index_base=0, model_load_precision="not_applicable_no_model")
    manifest_path = out / "basis_manifest.json"
    manifest_path.write_bytes(json_bytes(manifest))

    basis = ica.load_basis(manifest_path)
    rows = ad.read_activation_dataset(pairs_path).layer(1)
    numpy_result = ica.apply_basis(basis, rows, layer=1, path="numpy")
    reference = icalens.ICALens.from_pretrained(lens_dir)
    scores = np.asarray(reference.transform(rows.astype(np.float64), layer=1))
    recon = np.asarray(reference.inverse_transform(scores, layer=1))
    x_pre = ica.preprocess(basis.layers[1], basis.mode, basis.preprocessing["norm_eps"], rows)
    cosines = [float(a @ b) / (float(np.linalg.norm(a)) * float(np.linalg.norm(b)))
               for a, b in zip(numpy_result["scores"], scores) if np.linalg.norm(a) > 0 and np.linalg.norm(b) > 0]
    scores32 = np.asarray(reference.transform(rows, layer=1), dtype=np.float64)
    saved_mode = read_json(lens_dir / "icalens.json")["input_preprocessing"]["icalens_preprocessing"]
    return {
        "schema_version": "patientwords.ica-bridge-receipt/1", "synthetic": True,
        "statement": "Toy data: 48 fit rows and 24 scored rows of width 8. No model was loaded. The timings and "
                     "memory figures say nothing about a real model or a real fit.",
        "versions": {"python": platform.python_version(), "torch": torch.__version__,
                     "icalens": icalens.__version__, "icalens_distribution": installed("icalens"),
                     "numpy": np.__version__, "safetensors": installed("safetensors")},
        "icalens_source": str(Path(icalens.__file__).resolve().parent),
        "format": {"reference_reader_read_this_writers_dataset": format_agrees,
                   "activation_manifest_sha256": mine.manifest_sha256,
                   # "verified" when the manifest records the SHA-256 of its files and they matched.
                   "activation_file_pins": mine.verify_files()["file_pins"]},
        "fit": {"preprocessing_passed": mode, "preprocessing_saved": saved_mode, "n_components": n_components,
                "max_iter": max_iter, "seed": seed, "device": "cpu", "n_samples": int(values.shape[0]),
                "hidden_size": int(values.shape[1]), "wall_seconds": fit_seconds,
                "process_peak_rss_bytes_before_fit": rss_before, "process_peak_rss_bytes_after_fit": rss_after,
                "peak_rss_note": "ru_maxrss of the whole process, which includes importing torch."},
        "manifest": {"path": manifest_path.name, "sha256": sha256_file(manifest_path),
                     "preprocessing_mode": manifest["preprocessing"]["mode"],
                     "mode_equals_saved_artifact": manifest["preprocessing"]["mode"] == saved_mode},
        "path_comparison": {
            "rows": int(rows.shape[0]), "compute_dtype": "float64",
            "max_abs_score_difference": float(np.abs(numpy_result["scores"] - scores).max()),
            "max_abs_score": float(np.abs(scores).max()),
            "min_row_cosine": min(cosines),
            "max_abs_reconstruction_error_difference": float(np.abs(
                numpy_result["l2_error"] - np.linalg.norm(x_pre - recon, axis=1)).max()),
            "max_abs_score_difference_when_icalens_gets_float32_rows": float(
                np.abs(numpy_result["scores"] - scores32).max()),
            "scope": "arithmetic on one saved lens and the same rows; not model parity",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="a new directory outside the Git checkout")
    parser.add_argument("--mode", choices=MODES, default="none", help="preprocessing mode, passed explicitly")
    parser.add_argument("--n-components", type=int, default=4)
    parser.add_argument("--max-iter", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    try:
        out = check_output_path(args.out)
    except Refusal as exc:
        print(f"refused: {exc.code}: {exc}", file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()):
        print(f"refused: {out} exists and is not empty; choose a new directory", file=sys.stderr)
        return 2
    status = ica.icalens_status()
    if not status["importable"]:
        print(f"refused: icalens is not importable here: {status['import_error']}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    receipt = run(out, mode=args.mode, n_components=args.n_components, max_iter=args.max_iter, seed=args.seed)
    (out / "ica_bridge_receipt.json").write_bytes(json_bytes(receipt))
    sys.stdout.write(json_bytes(receipt).decode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
