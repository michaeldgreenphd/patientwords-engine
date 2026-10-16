"""Prepare and compare a bounded, lens-independent original-output check.

Validation is stdlib-only. Capture is an explicit future CI operation, never a
local preparation step. Existing collectors and measurement writers are unused.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import time
from typing import Any, Iterator

SCHEMA = "patientwords.baseline-preflight/1"
CAPTURE_SCHEMA = "patientwords.baseline-capture/1"
ROOT = Path(__file__).resolve().parents[1]


class Refusal(ValueError):
    """An explicit preparation, provenance, or execution refusal."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def digest(value: Any) -> str:
    """Hash a JSON value using the recorded canonical encoding."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_plan(path: Path, root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read only the predeclared source specification, not any stimulus archive."""
    plan = json.loads(path.read_text())
    source = root / plan["source_spec"]["path"]
    if not source.resolve().is_relative_to(root.resolve()):
        raise Refusal("source_path_escape", "source specification must be inside the checkout")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != plan["source_spec"]["sha256"]:
        raise Refusal("source_hash_mismatch", "the reviewed specification changed")
    original = json.loads(raw)
    validate(plan, original)
    return plan, original


def validate(plan: dict[str, Any], original: dict[str, Any]) -> None:
    """Validate this one-case preflight independently of all lens-fit metadata."""
    if plan.get("schema_version") != SCHEMA:
        raise Refusal("schema_mismatch", SCHEMA)
    for field, value in plan["model"].items():
        if original["model"].get(field) != value:
            raise Refusal("model_mismatch", field)
    for field in ("revision", "tokenizer_revision"):
        value = plan["model"][field]
        if not isinstance(value, str) or len(value) != 40 or any(x not in "0123456789abcdef" for x in value):
            raise Refusal("unpinned_revision", field)
    if (plan["model"]["tokenizer_id"] != plan["model"]["id"]
            or plan["model"]["tokenizer_revision"] != plan["model"]["revision"]):
        raise Refusal("unsupported_tokenizer_pin", "the existing loader pins model and tokenizer together")
    if plan["input_settings"] != original["input_settings"]:
        raise Refusal("format_mismatch", "input settings differ")
    if plan["input_settings"] != {
        "chat_template": None, "thinking": "not_applied_raw_prompt", "add_special_tokens": True, "truncation": False
    }:
        raise Refusal("unsupported_format", "only plain, untruncated prompts are prepared")
    cases = original["cases"]
    if len(cases) != 1 or cases[0]["id"] != plan["case_id"]:
        raise Refusal("case_mismatch", "exactly the selected case is required")
    case = cases[0]
    if case["holdout_status"] != "unsealed_reviewed":
        raise Refusal("unreviewed_source", "source must already be reviewed and unsealed")
    if plan["variants"] != ["source", "recipient"] or set(case["variants"]) != set(plan["variants"]):
        raise Refusal("variant_mismatch", "both original variants are required")
    for variant in case["variants"].values():
        if hashlib.sha256(variant["prompt"].encode()).hexdigest() != variant["prompt_sha256"]:
            raise Refusal("prompt_hash_mismatch", "prompt bytes changed")
    expected = {
        "device": "cpu", "dtype": "bfloat16", "attention_implementation": "sdpa", "seed": 7,
        "threads": 8, "batch_size": 1, "max_input_tokens": 128, "eval": True, "gradients": False,
        "aligned_use_cache": False, "aligned_mask": "all_ones", "aligned_positions": "zero_based_arange",
    }
    if plan["numerical"] != expected:
        raise Refusal("unsupported_numerics", "numerical settings require a separately reviewed preflight")
    if plan["comparisons"] != ["engine_legacy_vs_engine_aligned", "engine_aligned_vs_causalab"]:
        raise Refusal("missing_comparison", "legacy argument parity is required")
    for name in ("max_abs_logit", "rms_logit", "max_abs_probability", "target_probability"):
        value = plan["tolerances"].get(name)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise Refusal("invalid_tolerance", name)
    if plan["tolerances"].get("top1_equal") is not True:
        raise Refusal("invalid_tolerance", "top-1 equality is required")
    if plan["resources"]["provider_budget_usd"] != 0:
        raise Refusal("unsupported_budget", "this check never calls a paid provider")


def protocol(plan: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    """Build a public v4 read-only protocol: no writes, fitting, or interventions."""
    validate(plan, original)
    variants = original["cases"][0]["variants"]
    return {
        "header": {"protocol_version": "4", "description": "Exploratory original-model baseline preflight."},
        "model": {"key": plan["model"]["id"], "revision": plan["model"]["revision"], "dtype": "bf16"},
        "data": {role: {"inputs": [variants[name]["prompt"]]}
                 for name, role in (("source", "counterfactual"), ("recipient", "base"))},
        "method": {
            "intervened_models": {name: {"input": role, "reads": ["output"]}
                                  for name, role in (("source", "counterfactual"), ("recipient", "base"))},
            "sites": {"head": {"component": "lm_head"}},
            "reads": {"output": {"site": "head", "pos": {"all": True}}},
            "save": [{"read": "output", "model": name, "file_path": f"{name}.safetensors"}
                     for name in plan["variants"]],
        },
    }


def _softmax(vector: list[float]) -> list[float]:
    high = max(vector)
    values = [math.exp(x - high) for x in vector]
    total = sum(values)
    return [x / total for x in values]


def compare_vectors(left: list[float], right: list[float], target: int, limits: dict[str, Any]) -> dict[str, Any]:
    """Compare full vectors; probabilities always use the entire vocabulary."""
    if not left or len(left) != len(right):
        raise Refusal("logit_shape_mismatch", "two complete equally sized vectors are required")
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in left + right):
        raise Refusal("nonfinite_logits", "finite numeric logits are required")
    if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < len(left):
        raise Refusal("target_out_of_bounds", "the original first target token is required")
    a, b = _softmax(left), _softmax(right)
    diffs = [abs(x - y) for x, y in zip(left, right)]
    result = {
        "max_abs_logit": max(diffs), "rms_logit": math.sqrt(sum(x * x for x in diffs) / len(diffs)),
        "max_abs_probability": max(abs(x - y) for x, y in zip(a, b)),
        "target_probability": abs(a[target] - b[target]),
        "top1_equal": max(range(len(left)), key=left.__getitem__) == max(range(len(right)), key=right.__getitem__),
    }
    result["passed"] = result["top1_equal"] and all(result[k] <= limits[k] for k in limits if k != "top1_equal")
    return result


def execution_pins(record: dict[str, Any] | None) -> dict[str, Any]:
    """Require prospective remotely available code commits, never reported starting points."""
    if not isinstance(record, dict) or record.get("schema_version") != "patientwords.baseline-execution/1":
        raise Refusal("missing_execution_pins", "a reviewed future execution record is required")
    for name in ("engine", "causalab"):
        value = record.get("commits", {}).get(name)
        if not isinstance(value, str) or len(value) != 40 or any(x not in "0123456789abcdef" for x in value):
            raise Refusal("missing_execution_pins", f"{name} requires the full executable commit")
    return record


def _ids(values: Any, plan: dict[str, Any], label: str) -> None:
    if not isinstance(values, list) or not 0 < len(values) <= plan["numerical"]["max_input_tokens"] or any(
        isinstance(x, bool) or not isinstance(x, int) or not 0 <= x < plan["vocab_size"] for x in values
    ):
        raise Refusal("invalid_token_ids", label)


def aligned_inputs(ids: list[int]) -> dict[str, Any]:
    """The complete single-row forward contract, separate from numerical labels."""
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "position_ids": list(range(len(ids))),
            "output_position": len(ids) - 1, "batch_size": 1, "use_cache": False}


def _check_aligned_inputs(value: Any, ids: list[int]) -> None:
    if value != aligned_inputs(ids):
        raise Refusal("aligned_input_mismatch", "actual mask, positions, output position or call settings differ")


def check_protocol_frame(frame: Any, ids: list[int]) -> None:
    """Refuse padding or masked positions instead of comparing only real_ids."""
    if (frame.token_ids != (tuple(ids),) or frame.attention_mask != (tuple([1] * len(ids)),)
            or frame.prefix_lengths != (0,)):
        raise Refusal("protocol_input_mismatch", "the complete plain single-row frame must match")


def _actual_forward_inputs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    if len(args) > 1 or (args and "input_ids" in kwargs) or kwargs.get("inputs_embeds") is not None:
        raise Refusal("forward_input_unavailable", "one explicit input_ids batch is required")
    batch = args[0] if args else kwargs.get("input_ids")
    rows = {}
    for name, tensor in (("input_ids", batch), ("attention_mask", kwargs.get("attention_mask")),
                         ("position_ids", kwargs.get("position_ids"))):
        if tensor is None or not hasattr(tensor, "tolist"):
            raise Refusal("forward_input_unavailable", name)
        values = tensor.tolist()
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], list):
            raise Refusal("forward_input_shape", name)
        rows[name] = values[0]
    return {**rows, "output_position": len(rows["input_ids"]) - 1,
            "batch_size": 1, "use_cache": kwargs.get("use_cache")}


@contextmanager
def audit_aligned_forwards(model: Any, expected_ids: list[list[int]]) -> Iterator[list[dict[str, Any]]]:
    """Observe real root forwards without modifying their inputs or outputs."""
    observations: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    def before(module: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        actual = _actual_forward_inputs(args, kwargs)
        if actual["input_ids"] not in expected_ids:
            raise Refusal("forward_token_ids_mismatch", "the protocol forwarded an unexpected input")
        _check_aligned_inputs(actual, actual["input_ids"])
        pending.append(actual)

    def after(module: Any, args: tuple[Any, ...], kwargs: dict[str, Any], output: Any) -> None:
        actual = pending.pop()
        logits = getattr(output, "logits", None)
        if logits is None or len(logits.shape) != 3 or tuple(logits.shape[:2]) != (1, len(actual["input_ids"])):
            raise Refusal("forward_output_unavailable", "the complete actual forward logits are required")
        observations.append({"inputs": actual, "logits": logits[0, actual["output_position"]].float().tolist()})

    first = model.register_forward_pre_hook(before, with_kwargs=True)
    second = None
    try:
        second = model.register_forward_hook(after, with_kwargs=True)
        yield observations
    finally:
        first.remove()
        if second is not None:
            second.remove()


def observed_forward(observations: list[dict[str, Any]], ids: list[int], logits: list[float]) -> dict[str, Any]:
    """Bind saved output to an observed final position, including the Causalab read."""
    matches = [row for row in observations if row["inputs"]["input_ids"] == ids]
    if not matches:
        raise Refusal("missing_forward_observation", "no actual forward matches this variant")
    if any(row["logits"] != logits for row in matches):
        raise Refusal("forward_output_mismatch", "saved output differs from the actual final forward output")
    return matches[0]["inputs"]


def final_output(tensor: Any, ids: list[int], vocab_size: int) -> list[float]:
    """Select the unchanged endpoint from a whole-sequence native head read."""
    shape = tuple(tensor.shape)
    if shape == (1, len(ids), vocab_size):
        selected = tensor[0, -1]
    elif shape == (len(ids), vocab_size):
        selected = tensor[-1]
    else:
        raise Refusal("unexpected_output_shape", str(shape))
    return selected.float().tolist()


def tokenizer_provenance(tokenizer: Any, plan: dict[str, Any]) -> dict[str, str]:
    """Verify the pinned cached config; Transformers consumes revision at load time."""
    if tokenizer.name_or_path != plan["model"]["tokenizer_id"]:
        raise Refusal("tokenizer_mismatch", "tokenizer identity differs")
    from transformers.utils.hub import cached_file, extract_commit_hash
    try:
        path = cached_file(plan["model"]["tokenizer_id"], "tokenizer_config.json",
                           revision=plan["model"]["tokenizer_revision"], local_files_only=True)
    except (OSError, ValueError) as error:
        raise Refusal("tokenizer_provenance_unavailable", "pinned tokenizer config is unavailable offline") from error
    if path is None:
        raise Refusal("tokenizer_provenance_unavailable", "pinned tokenizer config is unavailable offline")
    resolved = extract_commit_hash(path, None)
    if resolved != plan["model"]["tokenizer_revision"]:
        raise Refusal("tokenizer_revision_mismatch", "cached tokenizer config has no matching snapshot revision")
    return {"repository": plan["model"]["tokenizer_id"], "revision": resolved,
            "config_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def _capture_provenance(plan: dict[str, Any], capture: dict[str, Any], backend: str,
                        expected: dict[str, Any]) -> None:
    if capture.get("schema_version") != CAPTURE_SCHEMA or capture.get("backend") != backend:
        raise Refusal("capture_schema_mismatch", backend)
    for field, value in (("plan_sha256", digest(plan)), ("model", plan["model"]),
                            ("numerical", plan["numerical"])):
        if capture.get(field) != value:
            raise Refusal("capture_provenance_mismatch", field)
    if capture.get("versions") != plan["environments"][backend] or capture.get("environment") != "github_actions":
        raise Refusal("capture_environment_mismatch", backend)
    if capture.get("interventions") != [] or capture.get("lens_used") is not False:
        raise Refusal("nonbaseline_capture", backend)
    tokenizer = capture.get("tokenizer_provenance", {})
    checksum = tokenizer.get("config_sha256") if isinstance(tokenizer, dict) else None
    if (not isinstance(checksum, str) or len(checksum) != 64 or any(x not in "0123456789abcdef" for x in checksum)
            or tokenizer != {"repository": plan["model"]["tokenizer_id"],
                             "revision": plan["model"]["tokenizer_revision"], "config_sha256": checksum}):
        raise Refusal("tokenizer_provenance_mismatch", backend)
    names = ("engine",) if backend == "engine" else ("engine", "causalab")
    if capture.get("execution_sha256") != digest(expected) or capture.get("code") != {
        name: {"commit": expected["commits"][name]} for name in names
    }:
        raise Refusal("capture_code_mismatch", backend)
    if set(capture["variants"]) != set(plan["variants"]):
        raise Refusal("variant_mismatch", backend)


def compare(plan: dict[str, Any], original: dict[str, Any], engine: dict[str, Any], other: dict[str, Any],
            execution: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refuse missing/misaligned observations before assessing numerical agreement."""
    validate(plan, original)
    expected = execution_pins(execution)
    for capture, backend in ((engine, "engine"), (other, "causalab")):
        _capture_provenance(plan, capture, backend, expected)
    if engine["tokenizer_provenance"] != other["tokenizer_provenance"]:
        raise Refusal("tokenizer_provenance_mismatch", "the cached tokenizer config bytes differ")
    rows = []
    for name in plan["variants"]:
        a, b = engine["variants"][name], other["variants"][name]
        expected_hash = original["cases"][0]["variants"][name]["prompt_sha256"]
        if a["prompt_sha256"] != expected_hash or b["prompt_sha256"] != expected_hash:
            raise Refusal("prompt_hash_mismatch", name)
        for row in (a, b):
            _ids(row["token_ids"], plan, name)
            _ids(row["target_token_ids"], plan, name)
        if a["token_ids"] != b["token_ids"] or not a["token_ids"]:
            raise Refusal("token_ids_mismatch", name)
        if a["target_token_ids"] != b["target_token_ids"] or not a["target_token_ids"]:
            raise Refusal("target_ids_mismatch", name)
        for row in (a, b):
            _check_aligned_inputs(row.get("aligned_inputs"), row["token_ids"])
        for values in (a["legacy_logits"], a["aligned_logits"], b["aligned_logits"]):
            if len(values) != plan["vocab_size"]:
                raise Refusal("incomplete_vocabulary", name)
        target = a["target_token_ids"][0]
        rows.append({"variant": name, "token_ids_sha256": digest(a["token_ids"]),
                     "legacy_vs_aligned": compare_vectors(a["legacy_logits"], a["aligned_logits"],
                                                          target, plan["tolerances"]),
                     "aligned_vs_causalab": compare_vectors(a["aligned_logits"], b["aligned_logits"],
                                                            target, plan["tolerances"])})
    passed = all(row[key]["passed"] for row in rows for key in ("legacy_vs_aligned", "aligned_vs_causalab"))
    return {"schema_version": SCHEMA, "status": "passed" if passed else "failed", "plan_sha256": digest(plan),
            "rows": rows, "capture_sha256": {"engine": digest(engine), "causalab": digest(other)},
            "interpretation": "Original-output compatibility only; no lens or intervention validation."}


def _code_identity(path: Path) -> dict[str, str]:
    try:
        head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.PIPE).strip()
        dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"],
                                        text=True, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as error:
        raise Refusal("code_identity_unavailable", "execution needs source installed from a Git checkout") from error
    if dirty:
        raise Refusal("uncommitted_execution_code", "future execution requires a clean committed checkout")
    return {"commit": head}


def check_prepared_model(model: Any, plan: dict[str, Any]) -> None:
    """Verify loaded numerical state, rather than merely labeling the result."""
    if model.training or getattr(model.config, "vocab_size", None) != plan["vocab_size"]:
        raise Refusal("runtime_model_mismatch", "evaluation mode or vocabulary geometry differs")
    parameters = list(model.parameters())
    if not parameters or any(
        parameter.device.type != "cpu" or str(parameter.dtype) != "torch.bfloat16" or parameter.requires_grad
        for parameter in parameters
    ):
        raise Refusal("runtime_numerics_mismatch", "all weights must be frozen CPU bfloat16")
    if getattr(model.config, "use_cache", None) is not True:
        raise Refusal("legacy_cache_mismatch", "the legacy raw forward expects the pinned default cache setting")


def capture(plan: dict[str, Any], original: dict[str, Any], backend: str, out: Path,
            reference: dict[str, Any] | None = None, execution: dict[str, Any] | None = None) -> dict[str, Any]:
    """Future CI-only worker; never called by validation or the offline test suite."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise Refusal("ci_only", "real-model capture is not a local preparation command")
    validate(plan, original)
    expected = execution_pins(execution)
    _output_path(out)
    if out.exists():
        raise Refusal("output_exists", "capture never overwrites")
    if platform.system() != "Linux":
        raise Refusal("unsupported_runner", "the prepared runtime requires Linux")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise Refusal("cache_not_prepared", "preview and stage pinned files first; capture itself must be offline")
    limits = plan["resources"]
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    if memory < limits["minimum_ram_bytes"] or (os.cpu_count() or 0) < limits["minimum_logical_cpus"]:
        raise Refusal("insufficient_runner", "runner memory or CPU count is below the declared minimum")
    parent = out.parent
    while not parent.exists():
        parent = parent.parent
    if shutil.disk_usage(parent).free < limits["minimum_free_disk_bytes"]:
        raise Refusal("insufficient_disk", "runner free disk is below the declared minimum")
    versions = {name: importlib.metadata.version(name) for name in plan["environments"][backend]}
    if versions != plan["environments"][backend]:
        raise Refusal("environment_mismatch", "use the separately pinned environment")
    identity = {"engine": _code_identity(ROOT)}
    if backend == "causalab":
        if reference is None or reference.get("plan_sha256") != digest(plan):
            raise Refusal("missing_reference", "the engine capture freezes token IDs before Causalab runs")
        _capture_provenance(plan, reference, "engine", expected)
        import causalab
        identity["causalab"] = _code_identity(Path(causalab.__file__).resolve().parents[1])
    if any(row["commit"] != expected["commits"][name] for name, row in identity.items()):
        raise Refusal("execution_code_mismatch", "checked-out code differs from prospective execution pins")
    import torch
    try:
        from scripts.logits_eval import load_pinned
    except ModuleNotFoundError:
        from logits_eval import load_pinned
    torch.manual_seed(plan["numerical"]["seed"])
    torch.set_num_threads(plan["numerical"]["threads"])
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    tokenizer, model, resolved = load_pinned(plan["model"]["id"], plan["model"]["revision"])
    if resolved != plan["model"]["revision"] or model.config._attn_implementation != "sdpa":
        raise Refusal("runtime_model_mismatch", "resolved revision or default attention backend differs")
    tokenizer_record = tokenizer_provenance(tokenizer, plan)
    model.requires_grad_(False)
    check_prepared_model(model, plan)
    variants = {}
    targets = [x for x in original["cases"][0]["targets"] if x["id"] == "legacy_next_token_target"]
    if len(targets) != 1:
        raise Refusal("missing_target", "the unchanged legacy target must be explicit")
    target_ids = tokenizer(targets[0]["text"], add_special_tokens=False).input_ids
    _ids(target_ids, plan, "target")
    for name, item in original["cases"][0]["variants"].items():
        ids = tokenizer(item["prompt"], add_special_tokens=True, truncation=False).input_ids
        if not ids or len(ids) > plan["numerical"]["max_input_tokens"]:
            raise Refusal("input_length", "input is empty or exceeds the declared token cap")
        variants[name] = {"prompt_sha256": item["prompt_sha256"], "token_ids": ids, "target_token_ids": target_ids}
        if backend == "engine":
            batch = torch.tensor([ids], dtype=torch.long)
            with torch.no_grad():
                variants[name]["legacy_logits"] = model(batch).logits[0, -1].float().tolist()
                with audit_aligned_forwards(model, [ids]) as observations:
                    variants[name]["aligned_logits"] = model(
                        batch, attention_mask=torch.ones_like(batch),
                        position_ids=torch.arange(len(ids)).unsqueeze(0), use_cache=False,
                    ).logits[0, -1].float().tolist()
                variants[name]["aligned_inputs"] = observed_forward(
                    observations, ids, variants[name]["aligned_logits"])
        elif ids != reference["variants"][name]["token_ids"]:
            raise Refusal("token_ids_mismatch", name)
    if backend == "causalab":
        from causalab.io.env import file_env
        from causalab.neural.engines.pytorch_hooks import ModelBundle, PytorchHooksEngine
        from causalab.protocol import run_protocol
        from causalab.protocol.positions.encoding import encode
        from safetensors.torch import load_file
        tokenizer.padding_side = "left"
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        for name, item in original["cases"][0]["variants"].items():
            check_protocol_frame(encode(tokenizer, [item["prompt"]]), variants[name]["token_ids"])
        bundle = ModelBundle.from_model(model, tokenizer, key=plan["model"]["id"],
                                        revision=plan["model"]["revision"], dtype="bf16")
        tensor_dir = out.parent / "causalab_original_outputs"
        tensor_dir.parent.mkdir(parents=True, exist_ok=True)
        tensor_dir.mkdir(exist_ok=False)
        with audit_aligned_forwards(model, [row["token_ids"] for row in variants.values()]) as observations:
            run_protocol(protocol(plan, original), file_env(tensor_dir, tensor_dir),
                         PytorchHooksEngine(bundle=bundle, device="cpu", batch_rows=1), tensor_dir, record=True)
        for name in plan["variants"]:
            values = load_file(str(tensor_dir / f"{name}.safetensors"))
            if len(values) != 1:
                raise Refusal("unexpected_tensor_count", name)
            tensor = next(iter(values.values()))
            variants[name]["aligned_logits"] = final_output(tensor, variants[name]["token_ids"], plan["vocab_size"])
            variants[name]["aligned_inputs"] = observed_forward(
                observations, variants[name]["token_ids"], variants[name]["aligned_logits"])
        if any(m._forward_hooks or m._forward_pre_hooks for m in model.modules()):
            raise Refusal("hooks_not_removed", "baseline capture left active hooks")
    for row in variants.values():
        for field in ("legacy_logits", "aligned_logits") if backend == "engine" else ("aligned_logits",):
            values = row[field]
            if len(values) != plan["vocab_size"]:
                raise Refusal("incomplete_vocabulary", field)
            compare_vectors(values, values, row["target_token_ids"][0], plan["tolerances"])
    return {"schema_version": CAPTURE_SCHEMA, "backend": backend, "plan_sha256": digest(plan),
            "model": plan["model"], "numerical": plan["numerical"], "versions": versions,
            "code": identity, "execution_sha256": digest(expected), "variants": variants, "environment": "github_actions",
            "tokenizer_provenance": tokenizer_record,
            "runtime_seconds_including_load": time.perf_counter() - started,
            "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "platform": platform.platform(), "interventions": [], "lens_used": False}


def _output_path(path: Path) -> None:
    resolved = path.resolve()
    if "exploratory_methods" not in resolved.parts or any(
        part in resolved.parts for part in ("trace_out", "pilot", "data", ".github")
    ):
        raise Refusal("output_namespace", "use an external exploratory_methods directory")
    if resolved.is_relative_to(ROOT.resolve()) or any((parent / ".git").exists() for parent in resolved.parents):
        raise Refusal("output_in_repository", "baseline artifacts must stay outside Git checkouts")


def write_new(path: Path, value: dict[str, Any]) -> None:
    """Write only to a distinct exploratory namespace, without overwriting evidence."""
    _output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "data/exploratory/baseline_preflight.v1.json")
    parser.add_argument("--mode", choices=("validate", "protocol", "capture", "compare"), default="validate")
    parser.add_argument("--backend", choices=("engine", "causalab"))
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--causalab", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execution", type=Path)
    args = parser.parse_args(argv)
    try:
        plan, original = read_plan(args.plan)
        execution = json.loads(args.execution.read_text()) if args.execution else None
        if args.mode == "validate":
            value = {"schema_version": SCHEMA, "status": "prepared_not_executed", "plan_sha256": digest(plan),
                     "lens_provenance_required": False, "prerequisites": plan["prerequisites"]}
        elif args.mode == "protocol":
            value = protocol(plan, original)
        elif args.mode == "capture":
            if args.backend is None or args.out is None:
                raise Refusal("missing_arguments", "capture needs --backend and --out")
            if args.out.exists():
                raise Refusal("output_exists", "capture never overwrites")
            reference = json.loads(args.engine.read_text()) if args.engine else None
            value = capture(plan, original, args.backend, args.out, reference, execution)
        else:
            if args.engine is None or args.causalab is None:
                raise Refusal("missing_arguments", "compare needs both captures")
            value = compare(plan, original, json.loads(args.engine.read_text()),
                            json.loads(args.causalab.read_text()), execution)
        if args.out:
            write_new(args.out, value)
        else:
            print(json.dumps(value, indent=2, allow_nan=False))
        return 1 if value.get("status") == "failed" else 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "refused", "code": getattr(error, "code", "invalid_input"), "message": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
