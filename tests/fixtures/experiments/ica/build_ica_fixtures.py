"""Regenerate the synthetic ICA fixtures in this directory.

    python tests/fixtures/experiments/ica/build_ica_fixtures.py [OUT_DIR]

SYNTHETIC. Nothing here comes from a model, a fit, a real prompt or a real corpus. Every number is a small
integer (or a quarter of one) chosen so that scores, shares and errors can be checked by hand.

Files written:

* ``toy_basis/icalens.json`` and ``toy_basis/artifacts/resid_post/layer_01.safetensors``: a basis in the saved
  ICA Lens layout, with hand-written matrices. No fit was run. Hidden size 8, layer 1, 4 components.
* ``basis_manifest.json``: the PatientWords basis manifest for that basis.
* ``pair_activations/``: an ActivationDataset with one row per token position of every variant of the families in
  ``../protocol_synthetic.json`` (24 rows).
* ``discovery_activations/``: an ActivationDataset of 48 rows (12 documents of 4 tokens) for a toy discovery
  corpus. The toy basis is not derived from it. ``tests/manual/ica_bridge.py`` and
  ``tests/test_experiments_ica_icalens.py`` fit a separate lens on it with the ``icalens`` package.
* ``fixture_index.json``: the SHA-256 of every file above and the ``ica_lens`` method block that names the basis.

Both datasets carry the writer's file pins (``provenance.patientwords_files``: SHA-256 and byte count of the layer
file and of the samples file), so each ``activations.json`` hash covers the activation values, and the basis
manifest names the discovery dataset by that hash. A change to either dataset therefore changes the basis manifest
hash; ``../protocol_synthetic_ica.json`` repeats that hash and must be updated with it
(``tests/test_experiments_slice.py`` compares the two).

The toy basis, with ``B = [[1,1,0,0],[0,1,0,0],[0,0,1,2],[0,0,0,1]]``:

    center          c = [1, 2, 0, -1, 0, 0, 0, 0]
    writing_matrix  W = [[B], [0]]             8 x 4: component j writes column j of B into coordinates 0..3
    reading_matrix  R = [inverse(B), 0]        4 x 8: inverse(B) = [[1,-1,0,0],[0,1,0,0],[0,0,1,-2],[0,0,0,1]]

A pair row is ``x = c + [B s ; t]`` for an integer score vector ``s`` and an integer residual ``t``. Then
``scores = (x - c) @ R.T = s`` exactly, the reconstruction is ``c + [B s ; 0]``, and the reconstruction error is
``||t||``. ``PAIR_LAST`` lists ``(s, t)`` for the last token position of each variant.

The binary files are written with ``scripts.experiments.activation_dataset``, which is also the code under test.
Independence comes from elsewhere: the expected numbers in ``tests/test_experiments_ica.py`` are literals worked
out from the table below, that test decodes one layer file with ``numpy.frombuffer`` alone, and
``tests/test_experiments_ica_icalens.py`` has the ``icalens`` and ``safetensors`` packages read the same bytes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from scripts.experiments.activation_dataset import (  # noqa: E402
    ROWS_SCHEMA, document_entry, write_activation_dataset, write_safetensors,
)
from scripts.experiments.adapters.ica import build_basis_manifest  # noqa: E402
from scripts.experiments.common import atomic_write_bytes, json_bytes, sha256_file  # noqa: E402

PROTOCOL = HERE.parent / "protocol_synthetic.json"
REVISION = "1" * 40
MODEL = {"repo_id": "fixture/toy-model", "revision": REVISION, "type": "base"}
TOKENIZER = {"id": "fixture/toy-tokenizer", "revision": REVISION}
HIDDEN, LAYER, COMPONENTS = 8, 1, 4
BASIS_ID = "fixture/toy-ica-basis"
CORPUS_ID = "toy-discovery-corpus-1"
VARIANT_ORDER = ("clinical", "colloquial", "normalized")

B = np.array([[1, 1, 0, 0], [0, 1, 0, 0], [0, 0, 1, 2], [0, 0, 0, 1]], dtype=np.float64)
B_INVERSE = np.array([[1, -1, 0, 0], [0, 1, 0, 0], [0, 0, 1, -2], [0, 0, 0, 1]], dtype=np.float64)
CENTER = np.array([1, 2, 0, -1, 0, 0, 0, 0], dtype=np.float64)
WRITING = np.vstack([B, np.zeros((4, 4))])
READING = np.hstack([B_INVERSE, np.zeros((4, 4))])

# (family, variant) -> (scores s, residual t) at the LAST token position. Worked values:
#   fam-1 clinical    s = [ 3,-4, 0, 0]  shares 9/25, 16/25, 0, 0                 error 0
#   fam-1 colloquial  s = [-3, 4, 0, 0]  the same shares; every sign flipped      error 0
#   fam-1 normalized  s = [ 1, 6, 2, 1]  shares 1/42, 36/42, 4/42, 1/42           x = [8,8,4,0,0,0,3,4], ||x|| = 13,
#                                        error 5, relative 5/13, cosine 12/13
#   fam-2 colloquial  s = [ 0, 0, 0, 0]  x = c: the shares are undefined          error 0
#   fam-3 clinical and colloquial share one s: their difference is exactly zero
PAIR_LAST: dict[tuple[str, str], tuple[list[int], list[int]]] = {
    ("fam-1", "clinical"): ([3, -4, 0, 0], [0, 0, 0, 0]),
    ("fam-1", "colloquial"): ([-3, 4, 0, 0], [0, 0, 0, 0]),
    ("fam-1", "normalized"): ([1, 6, 2, 1], [0, 0, 3, 4]),
    ("fam-2", "clinical"): ([2, 0, 0, -1], [0, 0, 0, 0]),
    ("fam-2", "colloquial"): ([0, 0, 0, 0], [0, 0, 0, 0]),
    ("fam-2", "normalized"): ([0, 1, 0, 0], [2, 0, 0, 0]),
    ("fam-3", "clinical"): ([1, 1, 1, 1], [0, 0, 0, 0]),
    ("fam-3", "colloquial"): ([1, 1, 1, 1], [0, 0, 0, 0]),
    ("fam-3", "normalized"): ([-1, 2, 0, 2], [0, 1, 0, 0]),
}

# The toy discovery corpus: x = offset + MIX @ source, with integer sources in -6..6 divided by 4.
DISCOVERY_DOCUMENTS, DISCOVERY_TOKENS = 12, 4
DISCOVERY_OFFSET = np.array([1, 0, -1, 2, 0, 1, 0, -2], dtype=np.float64)
MIX = np.eye(8) + np.diag([1.0] * 7, k=1) + np.diag([-1.0] * 6, k=2) + np.diag([2.0] * 4, k=4)


def pair_vector(scores: list[int], residual: list[int]) -> np.ndarray:
    return CENTER + np.concatenate([B @ np.array(scores, dtype=np.float64), np.array(residual, dtype=np.float64)])


def earlier_position(document: int, position: int) -> tuple[list[int], list[int]]:
    """``(s, t)`` of a row that is not the last position of its document."""
    return [position + 1, -(document + 1), 0, 1], [0, 0, 0, 0]


def lcg_sources(count: int, width: int) -> np.ndarray:
    """Integers in -6..6 from a linear congruential generator (a 1103515245, c 12345, m 2**31, start 20261110),
    divided by 4. Pure integer arithmetic, so the values are the same on every platform."""
    state, out = 20261110, []
    for _ in range(count * width):
        state = (1103515245 * state + 12345) % (2 ** 31)
        out.append(((state >> 16) % 13) - 6)
    return np.array(out, dtype=np.float64).reshape(count, width) / 4.0


def build_pair_dataset(out: Path, protocol: dict[str, Any], allow: list[Path]) -> Any:
    documents, rows = [], []
    number = 0
    for family in protocol["case_families"]:
        for variant in VARIANT_ORDER:
            token_ids = family["variants"][variant]["token_ids"]
            documents.append(document_entry(number, token_ids, role="protocol_variant", split=family["split"],
                                            family_id=family["family_id"], variant=variant))
            last = len(token_ids) - 1
            for position, token in enumerate(token_ids):
                scores, residual = (PAIR_LAST[(family["family_id"], variant)] if position == last
                                    else earlier_position(number, position))
                rows.append((position, number, token, pair_vector(scores, residual)))
            number += 1
    rows.sort(key=lambda row: (row[0], row[1]))  # interleave documents: a row index is not a document offset
    return write_activation_dataset(
        out / "pair_activations", model=MODEL, dtype="float32", allow_roots=allow,
        layers={LAYER: np.array([row[3] for row in rows], dtype=np.float32)},
        samples={"document_index": np.array([row[1] for row in rows], dtype=np.int64),
                 "position": np.array([row[0] for row in rows], dtype=np.int64),
                 "token_id": np.array([row[2] for row in rows], dtype=np.int64)},
        provenance={
            "synthetic": True,
            "dataset": {"description": "SYNTHETIC toy rows for the variants of tests/fixtures/experiments/"
                                       "protocol_synthetic.json. Hand-chosen integers. Not a model capture."},
            "token_scope": "all", "sampling_seed": "not_applicable_no_sampling",
            "patientwords": {"schema_version": ROWS_SCHEMA, "tokenizer": TOKENIZER, "positions": "all",
                             "documents": documents}})


def build_discovery_dataset(out: Path, allow: list[Path]) -> Any:
    values = DISCOVERY_OFFSET + lcg_sources(DISCOVERY_DOCUMENTS * DISCOVERY_TOKENS, HIDDEN) @ MIX.T
    documents, document_index, position, token_id = [], [], [], []
    for document in range(DISCOVERY_DOCUMENTS):
        token_ids = [(3 * document + 5 * place) % 8 for place in range(DISCOVERY_TOKENS)]
        documents.append(document_entry(document, token_ids, role="fit_corpus", split="discovery",
                                        corpus_id=CORPUS_ID))
        for place, token in enumerate(token_ids):
            document_index.append(document)
            position.append(place)
            token_id.append(token)
    return write_activation_dataset(
        out / "discovery_activations", model=MODEL, dtype="float32", allow_roots=allow,
        layers={LAYER: values.astype(np.float32)},
        samples={"document_index": np.array(document_index, dtype=np.int64),
                 "position": np.array(position, dtype=np.int64), "token_id": np.array(token_id, dtype=np.int64)},
        provenance={
            "synthetic": True,
            "dataset": {"description": "SYNTHETIC toy discovery corpus. Integer sources from a linear congruential "
                                       "generator, mixed by a fixed integer matrix. Not a model capture."},
            "token_scope": "all", "sampling_seed": "not_applicable_fixed_generator_start_20261110",
            "fitting_tokens": DISCOVERY_DOCUMENTS * DISCOVERY_TOKENS,
            "patientwords": {"schema_version": ROWS_SCHEMA, "tokenizer": TOKENIZER, "positions": "all",
                             "corpus_id": CORPUS_ID, "documents": documents}})


def toy_artifact_manifest(layer_file: str) -> dict[str, Any]:
    no_fit = "not_applicable_no_fit"
    return {
        "format": "icalens", "format_version": 4, "minimum_package_version": "0.3.4",
        "package_version": "not_applicable_hand_written_fixture", "synthetic": True,
        "model": dict(MODEL), "activation_site": "resid_post",
        "layer_indexing": "transformer_blocks_zero_based", "hidden_size": HIDDEN,
        "input_preprocessing": {"icalens_preprocessing": "none", "row_normalization": "none",
                                "pre_normalization_center": "none", "norm_eps": 1e-12},
        "layers": {str(LAYER): {"file": layer_file, "n_components": COMPONENTS, "fitting": {
            "algorithm": "none_hand_written_matrices",
            "implementation": "tests/fixtures/experiments/ica/build_ica_fixtures.py",
            "implementation_version": "1", "ica_algorithm": no_fit, "fun": no_fit, "max_iter": no_fit,
            "n_iter": no_fit, "stopping_criterion": no_fit, "random_state": no_fit, "n_samples": no_fit,
            "input_dtype": "float32", "fit_device": no_fit, "torch_version": no_fit, "whiten": no_fit,
            "whiten_solver": no_fit, "batch_size": no_fit, "objective_history": no_fit,
            "component_strengths": no_fit, "component_objectives": no_fit, "gaussian_objective": no_fit,
            "stored_dtype": "float32",
            "component_id_convention": "hand-written order; no sign canonicalization",
            "provenance": {"synthetic": True, "note": "No fit was run. The matrices are written by hand."}}}},
    }


def build_basis(out: Path, discovery: Any) -> dict[str, Any]:
    layer_file = f"artifacts/resid_post/layer_{LAYER:02d}.safetensors"
    root = out / "toy_basis"
    write_safetensors(root / layer_file, {"center": CENTER.astype(np.float32),
                                          "reading_matrix": READING.astype(np.float32),
                                          "writing_matrix": WRITING.astype(np.float32)})
    atomic_write_bytes(root / "icalens.json", json_bytes(toy_artifact_manifest(layer_file)))
    documents = discovery.row_map["documents"]
    return build_basis_manifest(
        root, basis_id=BASIS_ID, synthetic=True, artifact_root="toy_basis",
        description="SYNTHETIC. Hand-written matrices in the saved ICA Lens layout. No fit was run.",
        tokenizer_id=TOKENIZER["id"], tokenizer_revision=TOKENIZER["revision"],
        fit={"corpus_id": CORPUS_ID, "split": "discovery", "family_ids": [], "corpus_ids": [CORPUS_ID],
             "document_token_sha256": sorted({d["token_sha256"] for d in documents}),
             "activation_manifest_sha256": discovery.manifest_sha256,
             "description": "No fit was run. The toy discovery corpus is named as the fit corpus only so that the "
                            "split checks have a corpus to check."},
        capture_site="block_output", layer_index_base=0, model_load_precision="not_applicable_no_model",
        component_annotations=[
            {"layer": LAYER, "component": 0, "status": "hypothesis", "label": "placeholder label A",
             "source": "synthetic fixture; written by hand; no model and no profile"},
            {"layer": LAYER, "component": 1, "status": "hypothesis",
             "source": "synthetic fixture; written by hand; no model and no profile",
             "vocabulary_readout": {"method": "placeholder; no readout was computed",
                                    "source": "synthetic fixture", "tokens": ["alpha", "beta"]}}])


def build_all(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    allow = [out]
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    build_pair_dataset(out, protocol, allow)
    discovery = build_discovery_dataset(out, allow)
    manifest = build_basis(out, discovery)
    atomic_write_bytes(out / "basis_manifest.json", json_bytes(manifest))
    files = {path.relative_to(out).as_posix(): sha256_file(path)
             for path in sorted(p for p in out.rglob("*") if p.is_file())
             if path.name != "fixture_index.json" and path.suffix != ".py" and "__pycache__" not in path.parts}
    index = {
        "schema_version": "patientwords.fixture-ica-index/1", "synthetic": True,
        "note": "SYNTHETIC fixtures. Hand-written matrices and hand-chosen activations. No model, no fit, no real "
                "prompt. Regenerate with build_ica_fixtures.py.",
        "basis_manifest_sha256": files["basis_manifest.json"],
        "method_block": {"id": "ica_lens", "capture_site": "block_output", "layer_index_base": 0,
                         "layers": [LAYER], "positions": "last",
                         "basis": {"manifest_sha256": files["basis_manifest.json"], "fit_split": "discovery",
                                   "preprocessing": "none", "fit_families": [], "profile_families": [],
                                   "selection_families": []}},
        # The protocol's hash is not recorded: the pair rows depend on its token ids only, and the tests check
        # those row by row against the protocol as it is on disk.
        "protocol": "tests/fixtures/experiments/protocol_synthetic.json",
        "files": files,
    }
    atomic_write_bytes(out / "fixture_index.json", json_bytes(index))
    for name in list(files) + ["fixture_index.json"]:
        (out / name).chmod(0o644)  # the atomic writer creates 0600 files; fixtures are world-readable
    return index


def main(argv: list[str]) -> int:
    out = Path(argv[1]).resolve() if len(argv) > 1 else HERE
    index = build_all(out)
    for name in sorted(index["files"]):
        print(f"wrote {out / name}")
    print(f"wrote {out / 'fixture_index.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
