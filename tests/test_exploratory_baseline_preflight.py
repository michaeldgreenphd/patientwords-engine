"""Offline baseline-contract tests use abstract strings and numeric vectors."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from types import SimpleNamespace

import pytest

from scripts import exploratory_baseline_preflight as baseline


EXECUTION = {"schema_version": "patientwords.baseline-execution/1",
             "commits": {"engine": "0" * 40, "causalab": "1" * 40}}


@pytest.fixture
def inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = json.loads((baseline.ROOT / "data/exploratory/baseline_preflight.v1.json").read_text())
    original = {
        "model": plan["model"].copy(), "input_settings": plan["input_settings"].copy(),
        "cases": [{"id": plan["case_id"], "holdout_status": "unsealed_reviewed", "variants": {
            name: {"prompt": text, "prompt_sha256": hashlib.sha256(text.encode()).hexdigest()}
            for name, text in (("source", "alpha beta"), ("recipient", "gamma beta"))
        }}], "methods": {"jpp": {"model_revision": None}},
    }
    plan["vocab_size"] = 3
    return plan, original


def captures(plan: dict[str, Any], original: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    base = {
        "schema_version": baseline.CAPTURE_SCHEMA, "plan_sha256": baseline.digest(plan), "model": plan["model"],
        "numerical": plan["numerical"], "variants": {
            name: {"prompt_sha256": item["prompt_sha256"], "token_ids": [0, 1], "target_token_ids": [2, 1],
                   "aligned_logits": [0.0, 1.0, 2.0], "aligned_inputs": baseline.aligned_inputs([0, 1])}
            for name, item in original["cases"][0]["variants"].items()
        },
        "tokenizer_provenance": {"repository": plan["model"]["tokenizer_id"],
                                 "revision": plan["model"]["tokenizer_revision"], "config_sha256": "a" * 64},
    }
    engine, other = copy.deepcopy(base), copy.deepcopy(base)
    engine["backend"], other["backend"] = "engine", "causalab"
    for record in (engine, other):
        backend = record["backend"]
        names = ("engine",) if backend == "engine" else ("engine", "causalab")
        record.update(versions=plan["environments"][backend], environment="github_actions", interventions=[],
                      lens_used=False, execution_sha256=baseline.digest(EXECUTION),
                      code={name: {"commit": EXECUTION["commits"][name]} for name in names})
    for variant in engine["variants"].values():
        variant["legacy_logits"] = variant["aligned_logits"].copy()
    return engine, other


def test_unknown_lens_provenance_does_not_block_original_outputs(inputs: tuple) -> None:
    baseline.validate(*inputs)
    result = baseline.protocol(*inputs)
    assert set(result["data"]) == {"base", "counterfactual"}
    assert result["method"]["intervened_models"]["source"]["input"] == "counterfactual"
    assert result["method"]["intervened_models"]["recipient"]["input"] == "base"
    assert "writes" not in result["method"]
    assert all("writes" not in model for model in result["method"]["intervened_models"].values())
    assert result["method"]["sites"] == {"head": {"component": "lm_head"}}
    assert result["method"]["reads"] == {"output": {"site": "head", "pos": {"all": True}}}


def test_unchanged_complete_outputs_pass(inputs: tuple) -> None:
    plan, original = inputs
    result = baseline.compare(plan, original, *captures(plan, original), EXECUTION)
    assert result["status"] == "passed"
    assert len(result["rows"]) == 2


@pytest.mark.parametrize("path,value,code", [
    (("schema_version",), "wrong", "capture_schema_mismatch"),
    (("plan_sha256",), "wrong", "capture_provenance_mismatch"),
    (("model", "revision"), "a" * 40, "capture_provenance_mismatch"),
    (("variants", "source", "prompt_sha256"), "wrong", "prompt_hash_mismatch"),
    (("variants", "source", "token_ids"), [1, 0], "token_ids_mismatch"),
    (("variants", "source", "target_token_ids"), [1], "target_ids_mismatch"),
    (("variants", "source", "aligned_logits"), [1.0], "incomplete_vocabulary"),
    (("variants", "source", "aligned_logits"), [1.0, float("nan"), 1.0], "nonfinite_logits"),
])
def test_misaligned_or_incomplete_capture_refuses(inputs: tuple, path: tuple, value: Any, code: str) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    target = other
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == code


@pytest.mark.parametrize("which", ["legacy", "causalab"])
def test_each_required_comparison_can_fail(inputs: tuple, which: str) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    if which == "legacy":
        engine["variants"]["source"]["legacy_logits"][0] = 20.0
    else:
        other["variants"]["source"]["aligned_logits"][0] = 20.0
    assert baseline.compare(plan, original, engine, other, EXECUTION)["status"] == "failed"


def test_probabilities_use_complete_vocabulary(inputs: tuple) -> None:
    limits = inputs[0]["tolerances"]
    result = baseline.compare_vectors([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 2, limits)
    assert result["passed"]
    assert result["max_abs_probability"] == 0
    assert baseline._softmax([0.0, 0.0, 0.0]) == [1 / 3] * 3


@pytest.mark.parametrize("target", [True, -1, 3, None])
def test_invalid_target_is_not_defaulted(inputs: tuple, target: Any) -> None:
    with pytest.raises(baseline.Refusal, match="original first"):
        baseline.compare_vectors([0.0] * 3, [0.0] * 3, target, inputs[0]["tolerances"])


@pytest.mark.parametrize("field", ["revision", "tokenizer_revision"])
def test_unpinned_revision_refuses(inputs: tuple, field: str) -> None:
    plan, original = inputs
    plan["model"][field] = original["model"][field] = "main"
    with pytest.raises(baseline.Refusal) as error:
        baseline.validate(plan, original)
    assert error.value.code == "unpinned_revision"


def test_holdout_status_is_a_hard_boundary(inputs: tuple) -> None:
    inputs[1]["cases"][0]["holdout_status"] = "sealed"
    with pytest.raises(baseline.Refusal) as error:
        baseline.validate(*inputs)
    assert error.value.code == "unreviewed_source"


def test_local_capture_refuses_before_import_or_download(inputs: tuple, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(baseline.Refusal) as error:
        baseline.capture(*inputs, "engine", tmp_path / "never.json")
    assert error.value.code == "ci_only"
    assert not list(tmp_path.iterdir())


def test_source_hash_must_match_before_reading_case(inputs: tuple, tmp_path: Path) -> None:
    plan, original = inputs
    (tmp_path / "source.json").write_text(json.dumps(original))
    plan["source_spec"] = {"path": "source.json", "sha256": "0" * 64}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(baseline.Refusal) as error:
        baseline.read_plan(path, tmp_path)
    assert error.value.code == "source_hash_mismatch"


def test_outputs_do_not_enter_existing_collectors_or_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "exploratory_methods" / "baseline_preflight" / "result.json"
    baseline.write_new(path, {"synthetic": True})
    with pytest.raises(FileExistsError):
        baseline.write_new(path, {"synthetic": False})
    with pytest.raises(baseline.Refusal):
        baseline.write_new(tmp_path / "trace_out" / "exploratory_methods" / "result.json", {})
    assert not list(tmp_path.rglob("batch_summary*.json"))
    assert not list(tmp_path.rglob("verify_summary*.json"))


def test_validate_cli_never_imports_runtime(capsys: pytest.CaptureFixture) -> None:
    assert baseline.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "prepared_not_executed"
    assert result["lens_provenance_required"] is False


@pytest.mark.parametrize("change,code", [
    ({"training": True}, "runtime_model_mismatch"),
    ({"vocab_size": 4}, "runtime_model_mismatch"),
    ({"device": "cuda"}, "runtime_numerics_mismatch"),
    ({"dtype": "torch.float32"}, "runtime_numerics_mismatch"),
    ({"requires_grad": True}, "runtime_numerics_mismatch"),
    ({"use_cache": False}, "legacy_cache_mismatch"),
])
def test_actual_model_state_is_checked(inputs: tuple, change: dict, code: str) -> None:
    values = {"training": False, "vocab_size": 3, "device": "cpu", "dtype": "torch.bfloat16",
              "requires_grad": False, "use_cache": True, **change}
    parameter = SimpleNamespace(device=SimpleNamespace(type=values["device"]), dtype=values["dtype"],
                                requires_grad=values["requires_grad"])
    model = SimpleNamespace(training=values["training"], parameters=lambda: [parameter],
                            config=SimpleNamespace(vocab_size=values["vocab_size"], use_cache=values["use_cache"]))
    with pytest.raises(baseline.Refusal) as error:
        baseline.check_prepared_model(model, inputs[0])
    assert error.value.code == code


@pytest.mark.parametrize("field,value,code", [
    ("versions", {}, "capture_environment_mismatch"),
    ("environment", "local", "capture_environment_mismatch"),
    ("interventions", [{"kind": "replacement"}], "nonbaseline_capture"),
    ("lens_used", True, "nonbaseline_capture"),
    ("code", {}, "capture_code_mismatch"),
    ("execution_sha256", "wrong", "capture_code_mismatch"),
])
def test_execution_provenance_cannot_be_inferred(inputs: tuple, field: str, value: Any, code: str) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    other[field] = value
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == code


@pytest.mark.parametrize("ids", [[True], [-1], [3], [], [0] * 129])
def test_equal_invalid_token_lists_still_refuse(inputs: tuple, ids: list) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    engine["variants"]["source"]["token_ids"] = other["variants"]["source"]["token_ids"] = ids
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == "invalid_token_ids"


def test_pending_code_is_not_an_executable_pin(inputs: tuple) -> None:
    plan, original = inputs
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, *captures(plan, original))
    assert error.value.code == "missing_execution_pins"


@pytest.mark.parametrize("field,value", [
    ("attention_mask", [0, 1]), ("position_ids", [1, 2]), ("output_position", 0),
    ("batch_size", 2), ("use_cache", True), ("input_ids", [1, 0]),
])
def test_equal_logits_cannot_hide_different_forward_inputs(inputs: tuple, field: str, value: Any) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    other["variants"]["source"]["aligned_inputs"][field] = value
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == "aligned_input_mismatch"


def test_missing_actual_input_receipt_refuses(inputs: tuple) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    del other["variants"]["source"]["aligned_inputs"]
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == "aligned_input_mismatch"


@pytest.mark.parametrize("change", [
    {"token_ids": ((9, 0, 1),), "attention_mask": ((0, 1, 1),)},
    {"attention_mask": ((0, 1),)}, {"prefix_lengths": (1,)},
])
def test_protocol_checks_complete_frame_not_only_unmasked_ids(change: dict) -> None:
    frame = SimpleNamespace(token_ids=((0, 1),), attention_mask=((1, 1),), prefix_lengths=(0,))
    baseline.check_protocol_frame(frame, [0, 1])
    for key, value in change.items():
        setattr(frame, key, value)
    with pytest.raises(baseline.Refusal) as error:
        baseline.check_protocol_frame(frame, [0, 1])
    assert error.value.code == "protocol_input_mismatch"


def fake_tensor(rows: list) -> Any:
    return SimpleNamespace(tolist=lambda: rows)


def fake_forward_model() -> tuple[Any, dict, list]:
    hooks: dict[str, Any] = {}
    removed: list[str] = []

    def register(key: str, callback: Any, *, with_kwargs: bool) -> Any:
        assert with_kwargs
        hooks[key] = callback
        return SimpleNamespace(remove=lambda: removed.append(key))

    model = SimpleNamespace(register_forward_pre_hook=lambda callback, **kwargs: register("before", callback, **kwargs),
                            register_forward_hook=lambda callback, **kwargs: register("after", callback, **kwargs))
    return model, hooks, removed


class FakeLogits:
    shape = (1, 2, 3)

    def __getitem__(self, key: tuple[int, int]) -> Any:
        assert key == (0, 1)
        return SimpleNamespace(float=lambda: fake_tensor([0.0, 1.0, 2.0]))


def test_forward_audit_records_observed_kwargs_and_final_output_and_cleans_up() -> None:
    model, hooks, removed = fake_forward_model()
    kwargs = {name: fake_tensor([value]) for name, value in {
        "input_ids": [0, 1], "attention_mask": [1, 1], "position_ids": [0, 1]}.items()}
    kwargs["use_cache"] = False
    with baseline.audit_aligned_forwards(model, [[0, 1]]) as observed:
        hooks["before"](model, (), kwargs)
        hooks["after"](model, (), kwargs, SimpleNamespace(logits=FakeLogits()))
    assert removed == ["before", "after"]
    assert baseline.observed_forward(observed, [0, 1], [0.0, 1.0, 2.0]) == baseline.aligned_inputs([0, 1])
    with pytest.raises(baseline.Refusal) as error:
        baseline.observed_forward(observed, [0, 1], [0.0, 1.0, 1.5])
    assert error.value.code == "forward_output_mismatch"


def test_forward_audit_rejects_actual_mask_before_forward_and_cleans_up() -> None:
    model, hooks, removed = fake_forward_model()
    kwargs = {name: fake_tensor([value]) for name, value in {
        "input_ids": [0, 1], "attention_mask": [0, 1], "position_ids": [0, 1]}.items()}
    kwargs["use_cache"] = False
    with pytest.raises(baseline.Refusal) as error:
        with baseline.audit_aligned_forwards(model, [[0, 1]]) as observed:
            hooks["before"](model, (), kwargs)
    assert error.value.code == "aligned_input_mismatch"
    assert observed == []
    assert removed == ["before", "after"]


def test_missing_forward_cannot_be_inferred_from_declared_settings() -> None:
    with pytest.raises(baseline.Refusal) as error:
        baseline.observed_forward([], [0, 1], [0.0, 1.0, 2.0])
    assert error.value.code == "missing_forward_observation"


@pytest.mark.parametrize("shape", [(1, 2, 3), (2, 3)])
def test_full_sequence_read_selects_only_final_output(shape: tuple) -> None:
    class Tensor:
        def __init__(self) -> None:
            self.shape = shape

        def __getitem__(self, key: Any) -> Any:
            assert key == ((0, -1) if len(shape) == 3 else -1)
            return SimpleNamespace(float=lambda: fake_tensor([0.0, 1.0, 2.0]))

    assert baseline.final_output(Tensor(), [0, 1], 3) == [0.0, 1.0, 2.0]


def test_selected_position_tensor_cannot_impersonate_full_forward() -> None:
    with pytest.raises(baseline.Refusal) as error:
        baseline.final_output(SimpleNamespace(shape=(1, 1, 3)), [0, 1], 3)
    assert error.value.code == "unexpected_output_shape"


def fake_tokenizer_hub(monkeypatch: pytest.MonkeyPatch, path: Path | None, revision: str | None) -> list:
    calls = []

    def cached_file(repository: str, filename: str, **kwargs: Any) -> str | None:
        calls.append((repository, filename, kwargs))
        return str(path) if path is not None else None

    monkeypatch.setitem(sys.modules, "transformers.utils.hub",
                        SimpleNamespace(cached_file=cached_file, extract_commit_hash=lambda path, prior: revision))
    return calls


def test_consumed_tokenizer_revision_uses_offline_snapshot_provenance(inputs: tuple, tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    plan, _ = inputs
    config = tmp_path / "tokenizer_config.json"
    config.write_text('{}\n')
    calls = fake_tokenizer_hub(monkeypatch, config, plan["model"]["tokenizer_revision"])
    tokenizer = SimpleNamespace(name_or_path=plan["model"]["tokenizer_id"], init_kwargs={})
    observed = baseline.tokenizer_provenance(tokenizer, plan)
    assert observed == {"repository": plan["model"]["tokenizer_id"],
                        "revision": plan["model"]["tokenizer_revision"],
                        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest()}
    assert calls == [(plan["model"]["tokenizer_id"], "tokenizer_config.json",
                      {"revision": plan["model"]["tokenizer_revision"], "local_files_only": True})]


@pytest.mark.parametrize("revision", [None, "f" * 40])
def test_tokenizer_missing_or_different_snapshot_revision_refuses(inputs: tuple, tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch,
                                                                revision: str | None) -> None:
    plan, _ = inputs
    fake_tokenizer_hub(monkeypatch, tmp_path / "config.json", revision)
    tokenizer = SimpleNamespace(name_or_path=plan["model"]["tokenizer_id"], init_kwargs={})
    with pytest.raises(baseline.Refusal) as error:
        baseline.tokenizer_provenance(tokenizer, plan)
    assert error.value.code == "tokenizer_revision_mismatch"


def test_missing_offline_tokenizer_config_refuses(inputs: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, _ = inputs
    fake_tokenizer_hub(monkeypatch, None, None)
    tokenizer = SimpleNamespace(name_or_path=plan["model"]["tokenizer_id"], init_kwargs={})
    with pytest.raises(baseline.Refusal) as error:
        baseline.tokenizer_provenance(tokenizer, plan)
    assert error.value.code == "tokenizer_provenance_unavailable"


@pytest.mark.parametrize("value", [None, {}, {"config_sha256": "invalid"}])
def test_capture_requires_tokenizer_snapshot_receipt(inputs: tuple, value: Any) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    other["tokenizer_provenance"] = value
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == "tokenizer_provenance_mismatch"


def test_equal_token_ids_cannot_hide_different_tokenizer_config_bytes(inputs: tuple) -> None:
    plan, original = inputs
    engine, other = captures(plan, original)
    other["tokenizer_provenance"]["config_sha256"] = "b" * 64
    with pytest.raises(baseline.Refusal) as error:
        baseline.compare(plan, original, engine, other, EXECUTION)
    assert error.value.code == "tokenizer_provenance_mismatch"


def test_loader_does_not_claim_a_separately_pinned_tokenizer(inputs: tuple) -> None:
    plan, original = inputs
    plan["model"]["tokenizer_revision"] = original["model"]["tokenizer_revision"] = "b" * 40
    with pytest.raises(baseline.Refusal) as error:
        baseline.validate(plan, original)
    assert error.value.code == "unsupported_tokenizer_pin"


@pytest.mark.parametrize("worktree", [False, True])
def test_output_namespace_must_stay_outside_git_even_in_worktrees(tmp_path: Path, worktree: bool) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    if worktree:
        (checkout / ".git").write_text("gitdir: elsewhere\n")
    else:
        (checkout / ".git").mkdir()
    path = checkout / "exploratory_methods" / "baseline.json"
    with pytest.raises(baseline.Refusal) as error:
        baseline.write_new(path, {"synthetic": True})
    assert error.value.code == "output_in_repository"
    assert not path.parent.exists()


def test_output_symlink_cannot_enter_a_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    target = checkout / "exploratory_methods"
    target.mkdir()
    linked = tmp_path / "exploratory_methods"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(baseline.Refusal) as error:
        baseline.write_new(linked / "result.json", {"synthetic": True})
    assert error.value.code == "output_in_repository"
    assert not list(target.iterdir())


def test_missing_source_checkout_has_named_identity_refusal(tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> str:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(baseline.subprocess, "check_output", unavailable)
    with pytest.raises(baseline.Refusal) as error:
        baseline._code_identity(tmp_path)
    assert error.value.code == "code_identity_unavailable"
