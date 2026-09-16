"""The petri-audit lane's workflow wiring, read from the YAML the way CLAUDE.md
prescribes for CI-side behaviour (modelled on tests/test_pab_ci_staged.py):
the push-path defaults cover every trigger key, the interpreter is the locked
one, the fork is installed at the locked commit, the raw .eval never enters
the checkout, the artifact custody is 90 days, the paid steps are gated on
mode, and no secret is echoed. The lane is parked in `preflight` and has no
trigger file on this branch, so nothing here can fire."""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "petri_audit.yml"
LOCK = ROOT / "docs" / "framework" / "petri_environment.lock.json"
TRIGGER = "petri-audit"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")


@pytest.fixture(scope="module")
def raw() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow(raw) -> dict:
    return yaml.safe_load(raw)


@pytest.fixture(scope="module")
def defaults(raw) -> dict:
    block = re.search(r"defaults = (\{.*?\})\n", raw, re.DOTALL)
    assert block, "could not find the defaults dict in the params heredoc"
    return ast.literal_eval(re.sub(r"\n\s*#[^\n]*", "", block.group(1)))


def _steps(workflow: dict, job: str) -> list[dict]:
    return workflow["jobs"][job]["steps"]


def _step(workflow: dict, prefix: str, job: str = "audit") -> dict:
    for step in _steps(workflow, job):
        if step.get("name", "").startswith(prefix):
            return step
    raise AssertionError(f"no step named {prefix!r} in job {job!r}")


def test_shape_and_entry_paths(workflow):
    on = workflow.get("on") or workflow.get(True)
    assert "workflow_dispatch" in on and on["push"]["paths"] == [f".github/trigger/{TRIGGER}.json"]
    assert workflow["concurrency"] == {"group": "petri-audit-${{ github.ref }}", "cancel-in-progress": False}
    for name, job in workflow["jobs"].items():
        assert "!github.event.created" in str(job.get("if")), name


def test_defaults_cover_every_trigger_key_and_dispatch_input(workflow, defaults):
    on = workflow.get("on") or workflow.get(True)
    inputs = set(on["workflow_dispatch"]["inputs"])
    assert set(defaults) == set(ft.KNOWN_KEYS[TRIGGER]) == inputs
    assert defaults == ft.PARK_DEFAULTS[TRIGGER], "the heredoc defaults are the park: a bare re-fire is a no-op"
    assert defaults["mode"] == "preflight" and defaults["commit_outputs"] == "false" and defaults["judge"] == "false"
    assert defaults["target"] == "mockllm/model"
    assert TRIGGER in ft.PAID_TRIGGERS and TRIGGER in ft.TRIGGERS


def test_no_trigger_file_exists_so_nothing_can_fire():
    assert not (ROOT / ".github" / "trigger" / f"{TRIGGER}.json").exists(), (
        "the trigger file is created by fire_trigger.py park after the lane merges, never by hand")


def test_interpreter_and_harness_are_the_locked_ones(workflow, raw):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    setup = next(s for s in _steps(workflow, "audit") if str(s.get("uses", "")).startswith("actions/setup-python"))
    assert setup["with"]["python-version"] == lock["python"]["version"]
    install = _step(workflow, "Install the locked environment")
    assert "petri_environment.lock.json" in install["run"]
    assert "github.com/michaeldgreenphd/patientwords-inspect_petri@" in install["run"] and "--no-deps" in install["run"]
    assert "petri-lock-requirements.txt" in install["run"]
    verify = _step(workflow, "Verify the environment lock")
    assert "verify-lock" in verify["run"] and "--no-harness-commit" not in verify["run"]


def test_paid_steps_are_gated_on_mode_and_the_raw_log_stays_outside_the_checkout(workflow):
    run = _step(workflow, "Run (mode dry_run or run")
    assert "mode != 'preflight'" in run["if"] and "$RUNNER_TEMP/petri-run" in run["run"]
    assert "LOG_MODEL_API" in run["env"] and '--log-model-api "$LOG_MODEL_API"' in run["run"], (
        "the log_model_api input must reach the CLI (Codex round 1: it was accepted and ignored)")
    judge = _step(workflow, "Judge of record")
    assert "mode == 'run'" in judge["if"] and "judge == 'true'" in judge["if"]
    adapt = _step(workflow, "Adapt")
    assert "--custody \"github_actions_artifact:90d\"" in adapt["run"] and "data/petri/runs/" in adapt["run"]
    upload = next(s for s in _steps(workflow, "audit") if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert upload["with"]["retention-days"] == 90 and "petri-run/logs" in upload["with"]["path"]
    guard = _step(workflow, "Refuse to publish a raw log")
    assert "*.eval" in guard["run"] and "exit 1" in guard["run"]
    commit = _step(workflow, "Commit sanitised outputs")
    assert "mode == 'run'" in commit["if"] and "commit_outputs == 'true'" in commit["if"]
    assert "always()" not in commit["if"], (
        "the commit step must depend on every prior step succeeding, or outputs the seal check rejected get pushed "
        "(Codex round 1)")
    assert "*.eval" in commit["run"] and "git add -f data/petri/runs/" in commit["run"]
    steps = _steps(workflow, "audit")
    names = [s.get("name", "") for s in steps]
    assert names.index("Holdout seal check over every publishable Petri output (fails closed)") < names.index(commit["name"])
    unconditional = [s["name"] for s in steps if "always()" in str(s.get("if", ""))]
    assert unconditional == ["Refuse to publish a raw log (belt and braces)",
                             "Upload the raw .eval as a workflow artifact (90-day custody; never committed)",
                             "Job summary"]
    seal = _step(workflow, "Holdout seal check")
    assert "seal_check.py" in seal["run"] and "verify-chain" in seal["run"]
    gate = _step(workflow, "Daily-ceiling gate", job="params")
    assert f"budget-gate --trigger {TRIGGER}" in gate["run"]


def test_secrets_reach_only_env_blocks_and_are_never_echoed(workflow, raw):
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            run = step.get("run") or ""
            assert "${{ secrets." not in run, step.get("name")
            assert not re.search(r"echo[^\n]*(API_KEY|secrets\.)", run), step.get("name")
    assert raw.count("secrets.ANTHROPIC_API_KEY") >= 1


def test_gitignore_keeps_raw_logs_out():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.eval" in ignore and "data/petri/runs/*/logs/" in ignore


def test_fire_lane_classifies_the_petri_target_and_judge_specs():
    """Codex round 1: fire_lane booked every petri-audit fire to the anthropic
    lane while the landed sidecar could classify the same spend as OpenRouter,
    so concurrent OpenRouter fires never saw the commitment."""
    orl = "openrouter/openai/gpt-5.5"
    assert ft.fire_lane(TRIGGER, {"target": orl, "judge": "false"}) == "openrouter"
    assert ft.fire_lane(TRIGGER, {"target": orl, "judge": "true", "judge_model": "openrouter:google/gemini-2.5-flash"}) == "openrouter"
    assert ft.fire_lane(TRIGGER, {"target": orl, "judge": "true", "judge_model": "claude-haiku-4-5"}) == "anthropic"  # mixed
    assert ft.fire_lane(TRIGGER, {"target": orl, "judge": "true"}) == "anthropic"           # judge model unstated
    assert ft.fire_lane(TRIGGER, {"target": "anthropic/claude-haiku-4-5", "judge": "false"}) == "anthropic"
    assert ft.fire_lane(TRIGGER, {"target": "mockllm/model"}) == "anthropic"
    assert ft.fire_lane(TRIGGER, {}) == "anthropic"
    # the lane agrees with the sidecar's classification of the same run
    from scripts.petri_audit import spend
    assert spend.billing_channel([orl]) == "openrouter" and spend.judge_billing_channel("openrouter:google/x") == "openrouter"


def test_park_default_validates_and_is_a_true_no_op():
    ft.validate_params(TRIGGER, ft.PARK_DEFAULTS[TRIGGER])
    commitment, err = ft.fire_commitment(ft.PARK_DEFAULTS[TRIGGER])
    assert err is None and commitment == 0.01
    assert ft.fire_lane(TRIGGER, ft.PARK_DEFAULTS[TRIGGER]) == "anthropic"
    judged = dict(ft.PARK_DEFAULTS[TRIGGER], judge="true", judge_max_spend="0.50", max_spend="1.00")
    commitment, err = ft.fire_commitment(judged)
    assert err is None and commitment == pytest.approx(1.50), "the judge ceiling is counted, as for advice-eval"
