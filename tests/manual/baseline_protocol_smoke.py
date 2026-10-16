"""Exercise the read-only protocol on random tiny weights and abstract strings.

Requires the installed Causalab runtime in its separate environment. No Hub
files, study input text, pretrained weights, or paid APIs are used. Outputs are
installation checks and must remain outside repositories and collectors.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time
from types import ModuleType
from typing import Any


class SmokeRefusal(ValueError):
    """A named refusal before an installation check can produce a false pass."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_builder(engine_root: Path) -> ModuleType:
    """Import the exact checkout's stdlib-only builder by file path."""
    path = engine_root / "scripts/exploratory_baseline_preflight.py"
    spec = importlib.util.spec_from_file_location("_baseline_installation_check", path)
    if spec is None or spec.loader is None:
        raise SmokeRefusal("builder_unavailable", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_output(path: Path, engine_root: Path) -> Path:
    """Require a fresh external installation namespace, including resolved links."""
    output = path.resolve()
    forbidden = {"data", "trace_out", "pilot", "ops", ".github", ".git", "modes"}
    if "installation_checks" not in output.parts or forbidden.intersection(output.parts):
        raise SmokeRefusal("output_namespace", "Use a new external installation_checks directory")
    if output.is_relative_to(engine_root.resolve()) or any((parent / ".git").exists() for parent in output.parents):
        raise SmokeRefusal("output_in_repository", "Installation artifacts must stay outside Git")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise SmokeRefusal("output_exists", str(output)) from error
    return output


def run(engine_root: Path, output: Path) -> dict[str, Any]:
    """Compile and run the public protocol, then compare untouched output rows."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import causalab
    import torch
    from causalab.io.env import file_env
    from causalab.neural.engines.pytorch_hooks import ModelBundle, PytorchHooksEngine
    from causalab.protocol import run_protocol
    from causalab.protocol.registry import model_info_from_hf_config, register_model
    from safetensors.torch import load_file
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import PreTrainedTokenizerFast, Qwen3Config, Qwen3ForCausalLM

    started = time.perf_counter()
    torch.manual_seed(7)
    torch.set_num_threads(2)
    key, revision = "synthetic/tiny-qwen3-pair", "0" * 40
    config = Qwen3Config(
        vocab_size=16, hidden_size=8, intermediate_size=12, num_hidden_layers=2,
        num_attention_heads=2, num_key_value_heads=1, head_dim=4,
    )
    config._name_or_path, config._commit_hash, config._attn_implementation = key, revision, "sdpa"
    model = Qwen3ForCausalLM(config).eval().requires_grad_(False).to(dtype=torch.bfloat16)
    raw = Tokenizer(WordLevel({"[PAD]": 0, "[UNK]": 1, "alpha": 2, "beta": 3}, unk_token="[UNK]"))
    raw.pre_tokenizer = Whitespace()
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=raw, pad_token="[PAD]", unk_token="[UNK]", padding_side="left",
    )
    tokenizer.name_or_path = key
    tokenizer.init_kwargs["revision"] = revision
    register_model(model_info_from_hf_config(key, config))
    builder = load_builder(engine_root)
    plan = json.loads((engine_root / "data/exploratory/baseline_preflight.v1.json").read_text())
    plan["model"].update(id=key, revision=revision, tokenizer_id=key, tokenizer_revision=revision, width=8, num_layers=2)
    plan["case_id"], plan["vocab_size"] = "synthetic_installation_fixture", 16
    variants = {
        name: {"prompt": text, "prompt_sha256": hashlib.sha256(text.encode()).hexdigest()}
        for name, text in (("source", "alpha beta"), ("recipient", "beta alpha"))
    }
    original = {
        "model": plan["model"].copy(), "input_settings": plan["input_settings"].copy(),
        "cases": [{"id": plan["case_id"], "holdout_status": "unsealed_reviewed", "variants": variants}],
    }
    document = builder.protocol(plan, original)
    if "writes" in document["method"]:
        raise SmokeRefusal("unexpected_writes", "The baseline protocol must be read-only")
    (output / "protocol.json").write_text(json.dumps(document, indent=2) + "\n")
    bundle = ModelBundle.from_model(model, tokenizer, key=key, revision=revision, dtype="bf16")
    token_ids = {name: tokenizer(item["prompt"], add_special_tokens=True).input_ids
                 for name, item in variants.items()}
    with builder.audit_aligned_forwards(model, list(token_ids.values())) as observations:
        run_protocol(
            document, file_env(output, output),
            PytorchHooksEngine(bundle=bundle, device="cpu", batch_rows=1), output, record=True,
        )
    rows = []
    for name, item in variants.items():
        values = load_file(str(output / f"{name}.safetensors"))
        if len(values) != 1:
            raise SmokeRefusal("unexpected_tensor_count", name)
        actual = next(iter(values.values()))
        ids = token_ids[name]
        final = builder.final_output(actual, ids, 16)
        receipt = builder.observed_forward(observations, ids, final)
        batch = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            direct = model(
                batch, attention_mask=torch.ones_like(batch),
                position_ids=torch.arange(len(ids)).unsqueeze(0), use_cache=False,
            ).logits[0]
        if not torch.equal(actual.reshape(len(ids), 16), direct):
            raise SmokeRefusal("original_output_mismatch", name)
        rows.append({"variant": name, "shape": list(actual.shape), "dtype": str(actual.dtype),
                     "equal_to_direct_forward": True, "full_sequence_logits_equal": True,
                     "actual_aligned_inputs": receipt})
    if any(module._forward_hooks or module._forward_pre_hooks for module in model.modules()):
        raise SmokeRefusal("hooks_remaining", "The protocol left hooks on the fixture model")
    return {
        "kind": "installation_check", "research_result": False, "status": "passed",
        "builder_sha256": hashlib.sha256(Path(builder.__file__).read_bytes()).hexdigest(),
        "smoke_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "installed_package": causalab.__file__, "rows": rows, "hooks_remaining": False,
        "fixture": "random_tiny_architecture_no_weight_download", "seed": 7, "threads": 2,
        "runtime_seconds": time.perf_counter() - started,
        "max_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
    }


def main() -> int:
    """Run only this synthetic installation check, never a study specification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    output = None
    try:
        output = prepare_output(args.out_root, args.engine_root)
        result = run(args.engine_root.resolve(), output)
    except (SmokeRefusal, ImportError, OSError, ValueError, RuntimeError) as error:
        result = {"kind": "installation_check", "research_result": False, "status": "failed",
                  "code": getattr(error, "code", type(error).__name__), "message": str(error)}
    if output is not None:
        with (output / "installation_check.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
