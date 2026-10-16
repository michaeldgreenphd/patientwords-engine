"""Synthetic tensor arithmetic through the lens adapter and engine report API.

No pretrained weights, tokenizer download, fitting, or study execution occurs.
The three-block toy below exists only to exercise the interchange contract.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch

from lens_interop import load_verified_lens, paired_readouts
from scripts.exploratory_methods import build_report, digest

ENGINE = Path(__file__).resolve().parents[2]


def write_json(directory: Path, name: str, value: Any) -> Path:
    """Write new synthetic evidence exclusively, never replace a prior run."""
    path = directory / name
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return path


def main() -> None:
    """Generate every comparison row from deterministic toy input IDs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jpp-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    jpp_root, output = args.jpp_root.resolve(), args.out.resolve()
    forbidden = {"data", "trace_out", "pilot", "ops", ".github", ".claude", ".githooks", ".git", "modes"}
    if output.name != "exploratory_methods" or forbidden.intersection(output.parts):
        parser.error("Use a new exploratory_methods directory outside protected trees")
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    spec = json.loads((ENGINE / "tests/fixtures/exploratory/synthetic_spec.json").read_text())
    packet = json.loads((ENGINE / "tests/fixtures/exploratory/synthetic_packet.json").read_text())
    spec["model"]["precision"] = "float32"
    torch.manual_seed(spec["seed"])
    model_identity = {
        "id": spec["model"]["id"], "revision": spec["model"]["revision"],
        "tokenizer_id": spec["model"]["tokenizer_id"],
        "tokenizer_revision": spec["model"]["tokenizer_revision"],
        "width": 2, "num_layers": 3,
    }
    template = json.loads((jpp_root / "examples/interop/synthetic-manifest.json").read_text())
    template["model"] = model_identity
    lenses = {}
    manifest_files = {}
    for method, file_format in (("j_lens", "released_J"), ("jpp", "base_lens_parameters")):
        matrices = {0: torch.eye(2), 1: torch.eye(2)}
        if file_format == "released_J":
            checkpoint = {
                "J": matrices, "source_layers": [0, 1], "d_model": 2,
                "provenance": {"method": "jlens", "source": "synthetic identity toy"},
            }
        else:
            checkpoint = {
                "parameters": {"jacobians": matrices}, "source_layers": [0, 1],
                "config": {
                    "lens_type": "jacobian", "lrp_mode": "none", "hf_model_name": model_identity["id"],
                    "d_model": 2, "source_layers": [0, 1], "relative_end_transport_layer": -1,
                },
            }
        artifact = output / f"synthetic_lens.adapter_bridge.{method}.pt"
        with artifact.open("xb") as handle:
            torch.save(checkpoint, handle)
        manifest = copy.deepcopy(template)
        manifest["method"] = method
        manifest["artifact"]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest["artifact"]["path"] = artifact.name
        lenses[method] = load_verified_lens(artifact, manifest, model_identity)
        assert lenses[method].serialization_format == file_format
        spec["methods"][method]["artifact_sha256"] = manifest["artifact"]["sha256"]
        spec["methods"][method]["repository_revision"] = manifest["artifact"]["revision"]
        manifest_files[method] = str(write_json(output, f"synthetic_lens.adapter_bridge.{method}.json", manifest))

    embedding = torch.tensor([[0.8, -0.2], [-0.5, 0.7], [0.6, 0.1], [0.2, -0.3], [0.1, 0.4], [-0.3, -0.2]])
    gate = torch.tensor([[0.4, -0.2, 0.3, -0.5], [0.1, 0.6, -0.4, 0.2]])
    value = torch.tensor([[0.3, 0.2, -0.2, 0.4], [-0.1, 0.5, 0.3, -0.2]])
    down = torch.tensor([[0.3, -0.1], [0.2, 0.4], [-0.2, 0.3], [0.1, -0.5]])
    head = torch.tensor([[1.0, 0.2], [-0.3, 0.9], [0.5, -0.7], [-0.1, 0.1], [0.2, 0.5], [-0.6, -0.2]])

    def unembed(state: torch.Tensor) -> torch.Tensor:
        normalized = state * torch.rsqrt(state.square().mean(dim=-1, keepdim=True) + 1e-6)
        return (normalized * torch.tensor([1.0, 1.2])) @ head.T

    clean = {}

    def toy(ids: list[int], edit: dict[str, Any] | None = None) -> dict[str, Any]:
        state = embedding[torch.tensor(ids)].unsqueeze(0)
        blocks, products = {}, {}
        edit_l2 = 0.0
        for layer in range(3):
            context = state + 0.15 * torch.cumsum(state, dim=1)
            product = torch.nn.functional.silu(context @ gate) * (context @ value)
            for component in ("mlp_neuron_output", "block_output"):
                current = product if component == "mlp_neuron_output" else context + 0.2 * product @ down
                if edit is not None and edit["layer"] == layer and edit["component"] == component:
                    donor_cache = clean[edit["donor"]]
                    donor = donor_cache["products" if component == "mlp_neuron_output" else "blocks"][layer]
                    dims = list(range(current.shape[-1])) if edit["channels"] is None else edit["channels"]
                    delta_squared = 0.0
                    current = current.clone()
                    for recipient_pos, source_pos in edit["positions"]:
                        before = current[0, recipient_pos, dims].clone()
                        after = donor[0, source_pos, dims] if edit["kind"] == "observed_replacement" else torch.zeros_like(before)
                        current[0, recipient_pos, dims] = after
                        delta_squared += float((after - before).square().sum())
                    edit_l2 = delta_squared ** 0.5
                if component == "mlp_neuron_output":
                    product = current
                else:
                    state = current
            products[layer], blocks[layer] = product.clone(), state.clone()
        return {"blocks": blocks, "products": products, "output": SimpleNamespace(logits=unembed(state)), "edit_l2": edit_l2}

    case = spec["cases"][0]
    for variant, entry in case["variants"].items():
        clean[variant] = toy(entry["token_ids"])
    readouts = {}
    outputs = {}
    for variant, entry in case["variants"].items():
        cached = clean[variant]
        selected_blocks = {layer: cached["blocks"][layer] for layer in spec["fixed_layers"]}
        for method, lens in lenses.items():
            result = paired_readouts(lens, selected_blocks, cached["output"], positions=entry["positions"], native_unembed=unembed)
            for layer, logits in result["lens_logits"].items():
                torch.testing.assert_close(logits, unembed(selected_blocks[layer][0]))
                for offset, position in enumerate(result["positions"]):
                    readouts[variant, method, layer, position] = logits[offset].tolist()
                    readouts[variant, "logit_lens", layer, position] = unembed(selected_blocks[layer][0, position]).tolist()
            outputs[variant] = result["actual_output_logits"][-1].tolist()
    for row in packet["readouts"]:
        row["logits"] = readouts[row["variant"], row["method"], row["layer"], row["position"]]
    for row in packet["model_outputs"]:
        row["logits"] = outputs[row["variant"]]
    for row in packet["interventions"]:
        edited = toy(case["variants"][row["recipient"]]["token_ids"], edit=row)
        row["logits"] = edited["output"].logits[0, -1].tolist()
        row["edit_l2"] = edited["edit_l2"]
        if row["control"] == "self":
            assert row["edit_l2"] == 0.0 and row["logits"] == outputs[row["recipient"]]
    packet["model"] = copy.deepcopy(spec["model"])
    packet["spec_sha256"] = digest(spec)
    packet["environment"].update({
        "tensor_arithmetic": "deterministic synthetic three-block toy, not a pretrained model",
        "torch_version": torch.__version__, "seed": spec["seed"],
        "adapter": "lens_interop.load_verified_lens + paired_readouts",
        "adapter_source_sha256": hashlib.sha256((jpp_root / "src/lens_interop/artifact.py").read_bytes()).hexdigest(),
        "engine_source_sha256": hashlib.sha256((ENGINE / "scripts/exploratory_methods.py").read_bytes()).hexdigest(),
        "demo_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "causalab_protocol_executed": False,
        "control_labels": "synthetic fixture plan; no discovered channels or scientific interpretation",
    })
    packet["runtime_seconds"] = time.perf_counter() - started
    report = build_report(spec, packet)
    spec_path = write_json(output, "synthetic_spec.adapter_bridge.json", spec)
    packet_path = write_json(output, "synthetic_packet.adapter_bridge.json", packet)
    report_path = write_json(output, "exploratory_report.adapter_bridge.json", report)
    print(json.dumps({
        "status": "synthetic_adapter_bridge_passed", "report": str(report_path),
        "spec": str(spec_path), "packet": str(packet_path), "lens_manifests": manifest_files,
        "readout_rows": len(report["readouts"]), "model_outputs": len(report["model_outputs"]),
        "interventions": len(report["interventions"]), "real_model_executions": 0,
        "runtime_seconds": packet["runtime_seconds"], "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
