"""Offline gates for the manual-only baseline preparation route."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import exploratory_ci_preflight as ci

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


@pytest.fixture
def plan() -> dict[str, Any]:
    return ci.read_json(ROOT / "data/exploratory/baseline_preflight.v1.json")


@pytest.fixture
def ready(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ci.READINESS_SCHEMA, "status": "reviewed_ready_for_owner_dispatch",
        "causalab_commit": "a" * 40,
        "runner": {"id": 123, "name": "fixture-runner", "labels": ["self-hosted", "Linux", "X64", "bounded-cpu"],
                   "capacity_evidence": "synthetic fixture only"},
        "runner_budget": {"billable": False, "total_budget_usd": 0, "provider_budget_usd": 0,
                          "approval_reference": "synthetic fixture only"},
        "linux_runtime_reviewed": True, "expected_runtime_versions": deepcopy(plan["environments"]),
        "current_seal_attestation": {"checked_at_utc": "2026-10-16T11:00:00Z", "status": "clean",
                                     "source_spec_sha256": plan["source_spec"]["sha256"],
                                     "artifact_sha256": "1" * 64, "review_reference": "synthetic fixture only"},
    }


def context() -> dict[str, str]:
    return {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": ci.ENGINE_REPO, "GITHUB_REF": "refs/heads/main", "GITHUB_ACTOR": ci.OWNER, "GITHUB_TRIGGERING_ACTOR": ci.OWNER,
            "GITHUB_WORKFLOW_REF": f"{ci.ENGINE_REPO}/.github/workflows/exploratory_baseline_preflight.yml@refs/heads/main",
            "GITHUB_SHA": "b" * 40}


def test_actual_record_blocks_all_execution_prerequisites(plan: dict[str, Any]) -> None:
    record = ci.read_json(ROOT / "data/exploratory/baseline_ci_readiness.v1.json")
    assert set(ci.readiness(record, plan, NOW)) == {
        "execution_not_approved", "reviewed_causalab_commit_missing", "suitable_existing_runner_unestablished",
        "zero_cost_runner_budget_unestablished", "linux_runtime_setup_not_reviewed", "current_seal_attestation_missing",
    }


def test_complete_synthetic_record_has_no_missing_fields(ready: dict[str, Any], plan: dict[str, Any]) -> None:
    assert ci.readiness(ready, plan, NOW) == []


@pytest.mark.parametrize("key", ["causalab_commit", "runner", "runner_budget", "current_seal_attestation"])
def test_missing_readiness_never_defaults_to_approval(key: str, ready: dict[str, Any], plan: dict[str, Any]) -> None:
    del ready[key]
    assert ci.readiness(ready, plan, NOW)


@pytest.mark.parametrize("changes", [
    {"billable": True}, {"total_budget_usd": 1}, {"provider_budget_usd": 1}, {"approval_reference": None},
])
def test_runner_budget_must_be_established_zero(changes: dict[str, Any], ready: dict[str, Any],
                                               plan: dict[str, Any]) -> None:
    ready["runner_budget"].update(changes)
    assert "zero_cost_runner_budget_unestablished" in ci.readiness(ready, plan, NOW)


@pytest.mark.parametrize("stamp", ["2026-10-14T11:00:00Z", "2026-10-17T11:00:00Z", "2026-10-16T11:00:00", "bad"])
def test_stale_future_or_naive_attestation_refuses(stamp: str, ready: dict[str, Any], plan: dict[str, Any]) -> None:
    ready["current_seal_attestation"]["checked_at_utc"] = stamp
    assert "current_seal_attestation_missing" in ci.readiness(ready, plan, NOW)


@pytest.mark.parametrize("key,value", [
    ("GITHUB_ACTIONS", "false"), ("GITHUB_EVENT_NAME", "pull_request_target"),
    ("GITHUB_REPOSITORY", "another/engine"), ("GITHUB_REF", "refs/heads/topic"),
    ("GITHUB_ACTOR", "another"), ("GITHUB_TRIGGERING_ACTOR", "another"), ("GITHUB_WORKFLOW_REF", "topic"), ("GITHUB_SHA", "main"),
])
def test_untrusted_context_refuses(key: str, value: str) -> None:
    env = context()
    env[key] = value
    with pytest.raises(ci.Refusal):
        ci.dispatch_context(env)


def test_exact_owner_manual_context() -> None:
    assert ci.dispatch_context(context()) == "b" * 40


@pytest.mark.parametrize("status,merge,accepted", [("ahead", "a" * 40, True), ("identical", "a" * 40, True),
                                                    ("behind", "a" * 40, False), ("diverged", "b" * 40, False)])
def test_code_must_be_an_ancestor_of_owner_main(monkeypatch: pytest.MonkeyPatch, status: str,
                                              merge: str, accepted: bool) -> None:
    responses = iter([{"default_branch": "main"}, {"status": status, "base_commit": {"sha": "a" * 40},
                                                   "merge_base_commit": {"sha": merge}}])
    monkeypatch.setattr(ci, "api_json", lambda _: next(responses))
    if accepted:
        assert ci.trusted_commit(ci.CAUSALAB_REPO, "a" * 40)["default_branch_ancestry"] == "verified"
    else:
        with pytest.raises(ci.Refusal, match=ci.CAUSALAB_REPO):
            ci.trusted_commit(ci.CAUSALAB_REPO, "a" * 40)


@pytest.mark.parametrize("repo,commit", [("upstream/repo", "a" * 40), (ci.CAUSALAB_REPO, "branch")])
def test_arbitrary_code_sources_refuse_before_network(monkeypatch: pytest.MonkeyPatch, repo: str, commit: str) -> None:
    monkeypatch.setattr(ci, "api_json", lambda _: pytest.fail("network must not run"))
    with pytest.raises(ci.Refusal):
        ci.trusted_commit(repo, commit)


@pytest.mark.parametrize("limits", [[(16 << 30, 0, None)], [(None, None, 4.0)], [(64 << 30, 40 << 30, None)]])
def test_container_limit_overrides_large_physical_host(limits: list[tuple[int | None, int | None, float | None]],
                                                      plan: dict[str, Any]) -> None:
    with pytest.raises(ci.Refusal) as error:
        ci.effective_capacity(128 << 30, 100 << 30, 32, 100 << 30, limits, plan["resources"])
    assert error.value.code == "insufficient_capacity"


def test_capacity_preserves_swap_exclusion_and_nested_limits(plan: dict[str, Any]) -> None:
    actual = ci.effective_capacity(128 << 30, 100 << 30, 32, 100 << 30,
                                   [(96 << 30, 10 << 30, 16.0), (64 << 30, 2 << 30, 8.0)], plan["resources"])
    assert actual == {"effective_ram_bytes": 64 << 30, "available_ram_bytes": 62 << 30,
                      "effective_logical_cpus": 8, "free_disk_bytes": 100 << 30, "swap_counted": False}


def metadata(plan: dict[str, Any]) -> dict[str, Any]:
    files = [{"rfilename": name, "size": 8} for name in ("config.json", "tokenizer.json", "tokenizer_config.json")]
    files.extend([{"rfilename": "model.safetensors", "size": 100, "lfs": {"size": 100, "sha256": "c" * 64}},
                  {"rfilename": "pytorch_model.bin", "size": 1000}, {"rfilename": "README.md", "size": 1000}])
    return {"sha": plan["model"]["revision"], "id": plan["model"]["id"], "siblings": files}


def test_download_inventory_only_pinned_safe_files(plan: dict[str, Any]) -> None:
    rows = ci.model_files(metadata(plan), plan)
    assert {row["path"] for row in rows} == {"config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors"}
    assert sum(row["size"] for row in rows) == 124


@pytest.mark.parametrize("mutation,code", [
    ("revision", "model_metadata_mismatch"), ("size", "unknown_download_size"),
    ("digest", "missing_weight_digest"), ("cap", "download_cap_exceeded"),
    ("missing", "incomplete_download_inventory"), ("duplicate", "incomplete_download_inventory"),
])
def test_download_refusals(mutation: str, code: str, plan: dict[str, Any]) -> None:
    value = metadata(plan)
    if mutation == "revision":
        value["sha"] = "a" * 40
    elif mutation == "size":
        value["siblings"][0]["size"] = None
    elif mutation == "digest":
        value["siblings"][3]["lfs"] = {}
    elif mutation == "cap":
        plan["resources"]["maximum_model_download_bytes"] = 123
    elif mutation == "missing":
        del value["siblings"][0]
    else:
        value["siblings"].append(deepcopy(value["siblings"][0]))
    with pytest.raises(ci.Refusal) as error:
        ci.model_files(value, plan)
    assert error.value.code == code


def test_external_receipts_are_exclusive_and_refuse_checkout_alias(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("fixture")
    link = tmp_path / "alias"
    link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(ci.Refusal):
        ci.write_receipt(link / "report.json", {})
    out = tmp_path / "external" / "receipt.json"
    ci.write_receipt(out, {"status": "synthetic"})
    assert json.loads(out.read_text())["status"] == "synthetic"
    with pytest.raises(FileExistsError):
        ci.write_receipt(out, {})


def test_workflow_is_manual_read_only_and_gates_before_setup_and_download() -> None:
    text = (ROOT / ".github/workflows/exploratory_baseline_preflight.yml").read_text()
    workflow = yaml.safe_load(text)
    events = workflow.get("on", workflow.get(True))
    assert set(events) == {"workflow_dispatch"}
    assert events["workflow_dispatch"]["inputs"]["execute"]["default"] is False
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in text and "pull_request_target" not in text
    assert workflow["concurrency"]["cancel-in-progress"] is False
    gate, model = workflow["jobs"]["readiness"], workflow["jobs"]["model"]
    for job in (gate, model):
        assert "github.actor == github.repository_owner" in job["if"]
        assert "github.triggering_actor == github.repository_owner" in job["if"]
        assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "needs.readiness.outputs.ready == 'true'" in model["if"]
    assert model["timeout-minutes"] == 60
    steps = model["steps"]
    runs = [(index, step.get("run", "")) for index, step in enumerate(steps)]
    capacity = next(index for index, run in runs if "--mode capacity" in run)
    setup = next(index for index, run in runs if "pip install" in run)
    download = next(index for index, run in runs if "--mode stage-model" in run)
    capture = next(index for index, run in runs if "--mode capture" in run)
    environment = next(index for index, run in runs if "--mode environment" in run)
    assert capacity < setup < environment < download < capture
    for step in steps:
        if step.get("uses", "").startswith("actions/checkout"):
            assert step["with"]["persist-credentials"] is False
    assert "--require-hashes" in text and "build-args=--locked" in text
    assert "--signal=TERM --kill-after=30s 900s" in text
    assert steps[-1]["if"] == "always()"


@pytest.mark.parametrize("backend", ["engine", "causalab"])
def test_runtime_checks_preserve_exact_build_versions(backend: str, plan: dict[str, Any]) -> None:
    versions = deepcopy(plan["environments"][backend])
    record = ci.runtime_receipt(plan, backend, versions, plan["runtime_python_version"])
    assert record["versions"] == versions
    versions["torch"] += "+different"
    with pytest.raises(ci.Refusal) as error:
        ci.runtime_receipt(plan, backend, versions, plan["runtime_python_version"])
    assert error.value.code == "runtime_build_mismatch"


def test_cpu_build_is_never_normalized_to_base_version(plan: dict[str, Any]) -> None:
    assert plan["environments"]["engine"]["torch"] == "2.13.0+cpu"
    versions = deepcopy(plan["environments"]["engine"])
    versions["torch"] = "2.13.0"
    with pytest.raises(ci.Refusal, match="2.13.0"):
        ci.runtime_receipt(plan, "engine", versions, plan["runtime_python_version"])


def test_both_matching_runtime_receipts_required_before_staging(tmp_path: Path, plan: dict[str, Any]) -> None:
    for backend in ("engine", "causalab"):
        with pytest.raises(ci.Refusal) as error:
            ci.require_runtime_receipts(plan, tmp_path)
        assert error.value.code == "runtime_check_missing"
        record = ci.runtime_receipt(plan, backend, plan["environments"][backend], plan["runtime_python_version"])
        ci.write_receipt(tmp_path / f"{backend}.runtime.json", {"runtime": record})
    ci.require_runtime_receipts(plan, tmp_path)
    altered = deepcopy(plan)
    altered["tolerances"]["max_abs_logit"] /= 2
    with pytest.raises(ci.Refusal) as error:
        ci.require_runtime_receipts(altered, tmp_path)
    assert error.value.code == "runtime_receipt_mismatch"


def test_readiness_build_declaration_tracks_plan(ready: dict[str, Any], plan: dict[str, Any]) -> None:
    ready["expected_runtime_versions"]["engine"]["torch"] = "2.13.0"
    assert "runtime_build_declaration_mismatch" in ci.readiness(ready, plan, NOW)



def test_missing_runtime_checks_prevent_model_metadata_access(monkeypatch: pytest.MonkeyPatch,
                                                              tmp_path: Path, plan: dict[str, Any]) -> None:
    monkeypatch.setattr(ci, "dispatch_context", lambda _: "a" * 40)
    monkeypatch.setattr(ci, "measure_capacity", lambda *_: {})
    monkeypatch.setattr(ci, "api_json", lambda _: pytest.fail("model metadata must not be requested"))
    with pytest.raises(ci.Refusal) as error:
        ci.stage_model(plan, tmp_path / "cache", tmp_path / "download.json")
    assert error.value.code == "runtime_check_missing"
