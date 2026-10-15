"""Two independently bounded judge passes occupy one journal reservation."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess

import pytest

from scripts.fire_trigger import fire_commitment, secondary_judge_reservation
from scripts.judge_pair import allocation


def test_ratio_bounds_both_token_prices_and_rounds_up() -> None:
    result = allocation("first", 0.123456, (3.0, 10.0), (0.1, 0.5), "anthropic/first")
    assert result["price_ratio"] == 0.05
    assert result["max_spend_usd"] == 0.006173


@pytest.mark.parametrize("spec", ["claude-haiku-5-5", "anthropic:claude-haiku-5-5"])
def test_already_selected_second_judge_is_not_charged_twice(spec: str) -> None:
    params = {"mode": "rejudge", "judge": True, "judge_model": spec, "judge_max_spend": "0.3"}
    assert secondary_judge_reservation(params)["reason"] == "already_selected"
    assert fire_commitment(params) == (0.3, None)


def test_judge_pair_total_is_the_sum_of_independent_caps() -> None:
    params = {"mode": "run", "max_spend": "0.4", "judge": True, "judge_model": "claude-haiku-4-5",
              "judge_max_spend": "0.5"}
    assert fire_commitment(params)[0] == pytest.approx(0.95)
    assert secondary_judge_reservation(params)["max_spend_usd"] == 0.05


def test_petri_openrouter_second_judge_preserves_the_billing_account() -> None:
    params = {"mode": "rejudge", "judge": True, "judge_model": "openrouter:openai/gpt-5.4-mini",
              "judge_max_spend": "0.5"}
    second = secondary_judge_reservation(params)
    assert second["judge_model"] == "openrouter:anthropic/claude-haiku-5.5"
    assert second["secondary_price_per_mtok"] == [0.106, 0.53]
    assert second["max_spend_usd"] > 0


def test_openrouter_second_judge_disables_reasoning_and_requires_parameter_support(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace
    from typing import Any
    from scripts.petri_audit.judge_runner import RegistryJudge, _advice_eval_module

    _advice_eval_module()  # Load real pricing imports before replacing the HTTP transport.

    bodies: list[dict] = []

    def post(url: str, **kwargs: Any) -> SimpleNamespace:
        bodies.append(kwargs["json"])
        return SimpleNamespace(status_code=200, headers={}, raise_for_status=lambda: None,
                               json=lambda: {"choices": [{"message": {"content": "placeholder"}}],
                                             "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-never-sent")
    judge = RegistryJudge("openrouter:anthropic/claude-haiku-5.5")
    reply = judge.complete("placeholder", max_tokens=300, temperature=0)
    assert bodies[0]["reasoning"] == {"effort": "none"}
    assert bodies[0]["provider"] == {"require_parameters": True}
    assert "temperature" not in bodies[0]
    assert bodies[0]["messages"] == [{"role": "user", "content": "placeholder"}]
    assert "reasoning.effort none" in reply.thinking_disabled


def test_advice_pair_refuses_local_paid_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.judge_pair import require_advice_reservation

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(ValueError, match="dual_judge_ci_only"):
        require_advice_reservation(tmp_path, "claude-haiku-4-5", 1.0, {})


def test_secondary_petri_disables_hidden_sdk_retries_and_keeps_the_metered_gate(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any
    from scripts.petri_audit import secondary
    from scripts.petri_audit.judge_runner import _advice_eval_module

    ae = _advice_eval_module()
    options: list[dict] = []
    attempts: list[str] = []
    gates: list[int] = []

    def client(**kwargs: Any) -> object:
        options.append(kwargs)
        return object()

    def send(*args: Any, **kwargs: Any) -> None:
        attempts.append("sent")
        error = RuntimeError("response_unavailable")
        error.status_code = 503
        raise error

    def gate(attempt: int) -> bool:
        gates.append(attempt)
        return False

    monkeypatch.setattr(ae, "_client", client)
    monkeypatch.setattr(ae, "_send", send)
    judge = secondary.default_client("anthropic:claude-haiku-5-5", [])
    with pytest.raises(RuntimeError, match="response_unavailable"):
        judge.complete("placeholder", max_tokens=300, temperature=0.0, attempt_gate=gate)
    assert options == [{"max_retries": 0}]
    assert attempts == ["sent"] and gates == [1]


@pytest.mark.parametrize("failed_output_commit", [False, True])
@pytest.mark.parametrize("kind", ["advice", "petri_primary", "petri_secondary"])
def test_cost_only_push_preserves_unpublished_outputs(tmp_path: Path, failed_output_commit: bool, kind: str) -> None:
    """Execute the workflow shell with tracked dirty outputs and with an unpushed output commit."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    filename = "advice_evaluation.yml" if kind == "advice" else "petri_audit.yml"
    workflow = yaml.safe_load((root / ".github/workflows" / filename).read_text())
    prefix = {"advice": "Commit each judge pass cost", "petri_primary": "Commit cost sidecars of a paid run",
              "petri_secondary": "Commit the secondary pass and its cost"}[kind]
    step = next(item for item in workflow["jobs"]["advice" if kind == "advice" else "audit"]["steps"]
                if item.get("name", "").startswith(prefix))
    remote = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    scratch = tmp_path / "scratch"
    checkout.mkdir()
    scratch.mkdir()
    (checkout / "scripts").mkdir()
    shutil.copyfile(root / "scripts/ci_publish_judge_files.sh", checkout / "scripts/ci_publish_judge_files.sh")

    def git(*args: str, cwd: Path = checkout) -> str:
        return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                              capture_output=True).stdout

    git("init", "--bare", str(remote))
    git("init", "-b", "main")
    git("config", "user.name", "Test Runner")
    git("config", "user.email", "test@example.invalid")
    judgments = checkout / ("data/advice/judgments_example.jsonl" if kind == "advice"
                            else "data/petri/runs/manifests.chain")
    judgments.parent.mkdir(parents=True)
    judgments.write_text("original\n")
    git("add", ".")
    git("commit", "-m", "baseline")
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "HEAD:main")
    judgments.write_text("original\nnew result\n")
    report = checkout / {"advice": "data/advice/judgments_example.judge_20261015T120000Z.report.json",
                         "petri_primary": "data/petri/runs/run_777_1/run_777_1.report.json",
                         "petri_secondary": "data/petri/rejudge/second/run_777_1/"
                         "run_777_1.rejudge_777_secondary.judge.report.json"}[kind]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('{"cost_usd": 0.01}\n')
    relative = str(report.relative_to(checkout))
    (scratch / "advice-judge-reports.txt").write_text(relative + "\n")
    if failed_output_commit:
        git("add", ".")
        git("commit", "-m", "outputs whose push failed")
    subprocess.run(["bash", "-c", step["run"]], cwd=checkout, check=True, capture_output=True, text=True,
                   env={**os.environ, "RUNNER_TEMP": str(scratch), "BRANCH": "main", "GITHUB_RUN_ID": "777",
                        "RUN_STEM": "run_777_1", "COMMIT_OUTPUTS": "false", "VERIFIED": "success"})
    assert judgments.read_text() == "original\nnew result\n"
    assert report.read_text() == '{"cost_usd": 0.01}\n'
    assert git("--git-dir", str(remote), "show", "main:" + relative) == report.read_text()
    assert git("--git-dir", str(remote), "show", "main:" + str(judgments.relative_to(checkout))) == "original\n"


@pytest.mark.parametrize("job", ["audit", "rejudge"])
def test_failed_primary_publication_blocks_secondary_calls(tmp_path: Path, job: str) -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/petri_audit.yml").read_text())
    step = next(item for item in workflow["jobs"][job]["steps"]
                if item.get("name", "").startswith("Haiku 5.5 second judge"))
    assert "steps.primary_commit.outcome == 'success'" in step["env"]["SOURCE_PRESERVED"]
    assert "steps.primary_upload.outcome == 'success'" in step["env"]["SOURCE_PRESERVED"]
    stub = tmp_path / "python"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$RUNNER_TEMP/argv.txt"\n')
    stub.chmod(0o755)
    subprocess.run(["bash", "-c", step["run"]], check=True, capture_output=True, text=True,
                   env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
                        "RUNNER_TEMP": str(tmp_path), "RESOLVED_PARAMS": "{}", "PRIMARY_STATUS": "success",
                        "SOURCE_PRESERVED": "false", "RUN_STEM": "run_777_1"})
    arguments = (tmp_path / "argv.txt").read_text().splitlines()
    assert arguments[arguments.index("--primary-status") + 1] == "failure"


@pytest.mark.parametrize("directory", [False, True])
def test_clean_publisher_refuses_differing_remote_output(tmp_path: Path, directory: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    remote = tmp_path / "origin.git"
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=checkout, check=True, capture_output=True, text=True).stdout

    git("init", "--bare", str(remote))
    git("init", "-b", "main")
    git("config", "user.name", "Test Runner")
    git("config", "user.email", "test@example.invalid")
    artifact = checkout / "data/petri/rejudge/second/run_777_1/judgments.jsonl"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("remote original\n")
    git("add", ".")
    git("commit", "-m", "existing output")
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "HEAD:main")
    artifact.write_text("local different result\n")
    listing = tmp_path / "list.txt"
    listing.write_text(str((artifact.parent if directory else artifact).relative_to(checkout)) + "\n")
    outcome = subprocess.run(["bash", str(root / "scripts/ci_publish_judge_files.sh"), "costs", str(listing)],
                             cwd=checkout, capture_output=True, text=True,
                             env={**os.environ, "RUNNER_TEMP": str(tmp_path), "BRANCH": "main"})
    assert outcome.returncode != 0 and "judge_publish_remote_collision:" in outcome.stderr
    assert artifact.read_text() == "local different result\n"
    assert git("--git-dir", str(remote), "show", "main:" + str(artifact.relative_to(checkout))) == "remote original\n"
