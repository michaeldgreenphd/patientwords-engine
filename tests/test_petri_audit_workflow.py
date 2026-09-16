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


def test_params_heredoc_canonicalises_booleans_before_any_paid_step(raw):
    block = raw[raw.index("Resolve parameters"):raw.index("Daily-ceiling gate")]
    assert 'for k in ("judge", "log_model_api", "commit_outputs"):' in block
    assert "must be true or false" in block and 'p[k] = v' in block
    # every numeric key is parsed before a paid step, the judge's token allowance included (Codex round 6)
    for key in ("max_spend", "judge_max_spend", "epochs", "token_limit", "judge_max_tokens"):
        assert f'p["{key}"]' in block, key
    assert 'int(p["judge_max_tokens"]) <= 0' in block and "judge_max_tokens must be a positive integer" in block


def test_fire_path_refuses_a_bad_judge_token_allowance(capsys):
    """Codex round 6: judge_max_tokens was the one numeric key no entry point
    parsed before the paid run."""
    base = dict(ft.PARK_DEFAULTS[TRIGGER], mode="run", target="anthropic/claude-haiku-4-5", judge="true",
                judge_model="claude-haiku-4-5", judge_max_spend="0.01")
    for bad in ("three-hundred", "0", "-5", ""):
        assert any("judge_max_tokens must be a positive integer" in p
                   for p in ft.petri_params_problems(dict(base, judge_max_tokens=bad))), bad
    assert ft.petri_params_problems(dict(base, judge_max_tokens="300")) == []
    assert ft.petri_params_problems(dict(base, judge_max_tokens=300)) == []


def test_every_attempt_gets_its_own_run_directory_and_the_judge_fallback_records_its_tokens(workflow):
    """Codex round 7: a re-run keeps github.run_id, so the paid attempt reused
    the previous attempt's run directory and sidecar names."""
    stems = [step["env"]["RUN_STEM"] for job in workflow["jobs"].values() for step in job.get("steps", [])
             if "RUN_STEM" in (step.get("env") or {})]
    assert len(stems) >= 6 and all(s == "run_${{ github.run_id }}_${{ github.run_attempt }}" for s in stems), stems
    upload = _step(workflow, "Upload the raw .eval")
    assert "github.run_attempt" in upload["with"]["name"]
    report = _step(workflow, "Spend report")
    assert report["env"]["JUDGE_MAX_TOKENS"] == "${{ needs.params.outputs.judge_max_tokens }}"
    assert '--judge-max-tokens "$JUDGE_MAX_TOKENS"' in report["run"]


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
                             "Spend report for an attempted run that produced no adapted report",
                             "Upload the raw .eval as a workflow artifact (90-day custody; never committed)",
                             "Commit cost sidecars of a paid run (mode run; independent of commit_outputs)",
                             "Job summary"]
    # the cost sidecars of a paid run are booked whatever happened to the outputs (Codex round 2); nothing else
    # is staged by that step, and it runs after the gated outputs commit
    sidecars = _step(workflow, "Commit cost sidecars")
    assert "mode == 'run'" in sidecars["if"] and "commit_outputs" not in sidecars["if"]
    assert "*.report.json" in sidecars["run"] and "git add -f data/petri/runs/" not in sidecars["run"]
    assert "*.eval" in sidecars["run"]
    assert names.index(commit["name"]) < names.index(sidecars["name"])
    # the judge step sees the same provider keys as the run step, and preflight resolves the judge spec first
    judge_env = set(judge["env"])
    assert {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"} <= judge_env
    assert judge_env == set(run["env"]) & judge_env | {"JUDGE_MODEL", "JUDGE_MAX_SPEND", "JUDGE_MAX_TOKENS", "SEEDS_FILE", "RUN_STEM"}
    preflight = _step(workflow, "Preflight")
    assert "--judge-model $JUDGE_MODEL" in preflight["run"] and "--judge-model $JUDGE_MODEL" in run["run"]
    # round 3: the limits the run passed reach the manifest, an attempted run without an adapted report still gets a
    # spend report before the sidecar commit, the params heredoc refuses non-canonical booleans, and the sidecar step
    # measures against the remote rather than trusting a clean index
    assert '--run-params "$RUNNER_TEMP/petri-run/run_params.json"' in adapt["run"]
    spend_report = _step(workflow, "Spend report for an attempted run")
    assert "always()" in spend_report["if"] and "mode != 'preflight'" in spend_report["if"]
    assert "spend-report" in spend_report["run"] and names.index(spend_report["name"]) < names.index(sidecars["name"])
    assert names.index(adapt["name"]) < names.index(spend_report["name"])
    assert 'git fetch origin "$BRANCH"' in sidecars["run"] and 'git reset --soft "origin/$BRANCH"' in sidecars["run"]
    # round 4: a judge that started and left no sidecar is booked from its rows or at its ceiling; one that never
    # started books nothing (the marker distinguishes them)
    assert 'touch "$RUNNER_TEMP/petri-run/judge_started"' in judge["run"]
    assert "judge-spend-report" in spend_report["run"] and 'judge_started" ] && [ ! -f' in spend_report["run"]
    assert "JUDGE_MODEL" in spend_report["env"]
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
    # a mixed-channel fire is refused outright: one journal entry carries one commitment on one account
    base = dict(ft.PARK_DEFAULTS[TRIGGER], mode="run", judge="true", judge_max_spend="0.01")
    with pytest.raises(ValueError, match="mixed-channel"):
        ft.validate_params(TRIGGER, dict(base, target=orl, judge_model="claude-haiku-4-5"))
    with pytest.raises(ValueError, match="mixed-channel"):
        ft.validate_params(TRIGGER, dict(base, target="anthropic/claude-haiku-4-5", judge_model="openrouter:google/y"))
    ft.validate_params(TRIGGER, dict(base, target=orl, judge_model="openrouter:google/y"))
    ft.validate_params(TRIGGER, dict(base, target="anthropic/claude-haiku-4-5", judge_model="claude-haiku-4-5"))
    ft.validate_params(TRIGGER, dict(base, target=orl, judge="false", judge_model="claude-haiku-4-5"))
    assert ft.petri_channels({"target": orl, "judge": "true", "judge_model": "claude-x"}) == ("openrouter", "anthropic")
    # the judge's channel is the registry's key_env (Codex round 3): an openai: judge bills OpenRouter, so it pairs
    # with an OpenRouter target and not with an Anthropic one; a google: judge fails closed to the anthropic lane
    assert ft.petri_channels({"target": orl, "judge": "true", "judge_model": "openai:gpt-5.4-mini"}) == ("openrouter", "openrouter")
    ft.validate_params(TRIGGER, dict(base, target=orl, judge_model="openai:gpt-5.4-mini"))
    with pytest.raises(ValueError, match="mixed-channel"):
        ft.validate_params(TRIGGER, dict(base, target="anthropic/claude-haiku-4-5", judge_model="deepseek:deepseek-chat"))
    assert ft.petri_channels({"target": orl, "judge": "true", "judge_model": "google:gemini-2.5-flash"}) == ("openrouter", "anthropic")
    # a bare provider the registry knows is that provider (Codex round 4): `openai` bills OpenRouter
    assert ft.petri_channels({"target": orl, "judge": "true", "judge_model": "openai"}) == ("openrouter", "openrouter")
    with pytest.raises(ValueError, match="mixed-channel"):
        ft.validate_params(TRIGGER, dict(base, target="anthropic/claude-haiku-4-5", judge_model="openai"))
    assert ft.petri_channels({"target": orl, "judge": "true", "judge_model": "claude-haiku-4-5"})[1] == "anthropic"
    # boolean keys must be spelled the one way the workflow compares against (Codex round 3)
    for bad in ("True", "yes", "1", ""):
        with pytest.raises(ValueError, match="must be true or false"):
            ft.validate_params(TRIGGER, dict(ft.PARK_DEFAULTS[TRIGGER], commit_outputs=bad))
    ft.validate_params(TRIGGER, dict(ft.PARK_DEFAULTS[TRIGGER], commit_outputs=False, judge=True, judge_max_spend="0.01"))
    assert ft.lane_params_problems("advice-eval", {"models": "x", "commit_outputs": "True"}) == []


def test_budget_gate_enforces_the_lane_invariants_a_dispatch_never_sends_through_fire_trigger(tmp_path, capsys):
    """Codex round 3: workflow_dispatch reaches budget-gate without
    validate_params, so the server-side gate applies the lane invariants."""
    params = dict(ft.PARK_DEFAULTS[TRIGGER], mode="run", target="openrouter/openai/gpt-5.5", judge="true",
                  judge_model="claude-haiku-4-5", judge_max_spend="0.01")
    params_file = tmp_path / "gate_params.json"
    params_file.write_text(json.dumps(params), encoding="utf-8")
    args = type("Args", (), {"repo": str(ROOT), "trigger": TRIGGER, "params_file": str(params_file)})()
    assert ft.cmd_budget_gate(args) == 6
    assert "mixed-channel" in capsys.readouterr().err
    params_file.write_text(json.dumps(dict(params, commit_outputs="True", judge="false")), encoding="utf-8")
    assert ft.cmd_budget_gate(args) == 6
    assert "must be true or false" in capsys.readouterr().err


def test_park_default_validates_and_is_a_true_no_op():
    ft.validate_params(TRIGGER, ft.PARK_DEFAULTS[TRIGGER])
    commitment, err = ft.fire_commitment(ft.PARK_DEFAULTS[TRIGGER])
    assert err is None and commitment == 0.01
    assert ft.fire_lane(TRIGGER, ft.PARK_DEFAULTS[TRIGGER]) == "anthropic"
    judged = dict(ft.PARK_DEFAULTS[TRIGGER], judge="true", judge_max_spend="0.50", max_spend="1.00")
    commitment, err = ft.fire_commitment(judged)
    assert err is None and commitment == pytest.approx(1.50), "the judge ceiling is counted, as for advice-eval"
