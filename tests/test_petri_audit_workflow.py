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
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "petri_audit.yml"
LOCK = ROOT / "docs" / "framework" / "petri_environment.lock.json"
TRIGGER = "petri-audit"
RUN_STEM_EXPR = ("${{ needs.params.outputs.mode == 'readapt' && format('run_{0}_1', needs.params.outputs.source_run_id) "
                 "|| format('run_{0}_{1}', github.run_id, github.run_attempt) }}")


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
                judge_model="claude-haiku-4-5", judge_max_spend="0.01", _nonce="n1")  # a paid fire carries a nonce (PR #28)
    for bad in ("three-hundred", "0", "-5", ""):
        assert any("judge_max_tokens must be a positive integer" in p
                   for p in ft.petri_params_problems(dict(base, judge_max_tokens=bad))), bad
    assert ft.petri_params_problems(dict(base, judge_max_tokens="300")) == []
    assert ft.petri_params_problems(dict(base, judge_max_tokens=300)) == []


def test_every_attempt_gets_its_own_run_directory_and_the_judge_fallback_records_its_tokens(workflow):
    """Codex round 7: a re-run keeps github.run_id, so the paid attempt reused
    the previous attempt's run directory and sidecar names."""
    # one definition, on the audit job, so no step can drift from it; every mode but readapt keeps a directory per
    # attempt, and a readapt writes into its source run's (mode readapt, 2026-09-24)
    stems = [step["env"]["RUN_STEM"] for job in workflow["jobs"].values() for step in job.get("steps", [])
             if "RUN_STEM" in (step.get("env") or {})]
    assert stems == [], "RUN_STEM is defined once, on the audit job"
    assert workflow["jobs"]["audit"]["env"]["RUN_STEM"] == RUN_STEM_EXPR
    upload = _step(workflow, "Upload the raw .eval")
    assert "github.run_attempt" in upload["with"]["name"]
    report = _step(workflow, "Spend report")
    assert report["env"]["JUDGE_MAX_TOKENS"] == "${{ needs.params.outputs.judge_max_tokens }}"
    assert '--judge-max-tokens "$JUDGE_MAX_TOKENS"' in report["run"]


def test_only_mode_run_is_a_paid_petri_fire(tmp_path, capsys):
    """Codex round 8: counting preflight and dry_run as paid refused the park
    once the daily ceiling was reached, leaving a paid configuration at rest."""
    assert ft.is_paid_fire(TRIGGER, {"mode": "run", "target": "anthropic/claude-haiku-4-5"}) is True
    assert ft.is_paid_fire(TRIGGER, {"mode": "preflight"}) is False and ft.is_paid_fire(TRIGGER, {"mode": "dry_run"}) is False
    assert ft.is_paid_fire(TRIGGER, {}) is False, "no mode is the workflow's preflight default"
    assert ft.is_paid_fire(TRIGGER, ft.PARK_DEFAULTS[TRIGGER]) is False, "the park is a free fire"
    assert ft.is_paid_fire("advice-eval", {}) is True and ft.is_paid_fire("logits-eval", {}) is False
    assert ft.is_paid_fire("circuit-trace", {"show_mitigation": "true"}) is True
    params_file = tmp_path / "park_params.json"
    params_file.write_text(json.dumps(ft.PARK_DEFAULTS[TRIGGER]), encoding="utf-8")
    args = type("Args", (), {"repo": str(ROOT), "trigger": TRIGGER, "params_file": str(params_file)})()
    assert ft.cmd_budget_gate(args) == 0 and "free fire" in capsys.readouterr().out


def test_a_paid_run_is_admitted_from_a_push_fire_on_its_first_attempt_only(raw, workflow):
    """Codex round 8: a workflow_dispatch and an Actions-tab re-run carry no
    journal reservation, so the daily ceiling could be passed twice."""
    block = raw[raw.index("Resolve parameters"):raw.index("Daily-ceiling gate")]
    assert 'if p["mode"] in ("run", "readapt") and os.environ["EVENT_NAME"] != "push":' in block
    assert 'if p["mode"] in ("run", "readapt") and os.environ.get("RUN_ATTEMPT", "1") != "1":' in block
    params = _step(workflow, "Resolve parameters", job="params")
    assert params["env"]["RUN_ATTEMPT"] == "${{ github.run_attempt }}" and params["env"]["EVENT_NAME"] == "${{ github.event_name }}"


def _run_the_run_step(workflow: dict, tmp_path: Path, *, mode: str, attempt: str) -> tuple:
    """The Run step's shell body, executed as the runner executes it (`bash -e`), with `python` stubbed to record
    its arguments and exit 0: the step's own gating runs for real and no model is called. Returns the process, the
    target-start marker path and the file the stub records calls in."""
    step = _step(workflow, "Run (mode dry_run or run")
    case = tmp_path / f"{mode}-{attempt or 'none'}"
    bindir, runner_temp = case / "bin", case / "runner-temp"
    bindir.mkdir(parents=True)
    runner_temp.mkdir()
    calls = case / "python_calls.txt"
    stub = bindir / "python"
    # the stub writes the marker it is handed, as `cli run --started-marker FILE` does once the target model is built
    # (PR #37 moved the marker from the shell into the CLI; merged here with PR #29's attempt check)
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\nprev=""\n'
                    'for a in "$@"; do if [ "$prev" = "--started-marker" ]; then : > "$a"; fi; prev="$a"; done\n'
                    'exit 0\n', encoding="utf-8")
    stub.chmod(0o755)
    env = {"PATH": os.pathsep.join([str(bindir), "/usr/bin", "/bin"]), "RUNNER_TEMP": str(runner_temp),
           "MODE": mode, "RUN_ATTEMPT": attempt, "SEEDS_FILE": "seeds.json", "SEED_IDS": "", "WAVE": "2",
           "TARGET": "anthropic/claude-haiku-4-5", "MAX_SPEND": "6.10", "JUDGE": "true", "JUDGE_MODEL": "claude-haiku-4-5",
           "JUDGE_MAX_SPEND": "2.50", "EPOCHS": "1", "TOKEN_LIMIT": "40000", "LOG_MODEL_API": "true",
           "JOURNAL_NONCE": "n1"}
    proc = subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True, timeout=60)
    return proc, runner_temp / "petri-run" / "target_started", calls


def test_a_re_run_of_the_audit_job_alone_cannot_call_the_target_again(workflow, tmp_path):
    """The Actions tab's "Re-run failed jobs" and "Re-run this job" re-run the audit job alone, at the next attempt,
    reusing the params job's outputs, so the params job's attempt refusal and the budget gate never run for it. Before this
    check the Run step called the target again into run_<id>_2 with no journal reservation of its own (w2e3's
    failed run 35937014168 was one click from it). The Run step now refuses mode run on any attempt but the first,
    before the target-start marker, so the always()-gated spend report imputes nothing either."""
    step = _step(workflow, "Run (mode dry_run or run")
    assert step["env"]["MODE"] == "${{ needs.params.outputs.mode }}"
    assert step["env"]["RUN_ATTEMPT"] == "${{ github.run_attempt }}"
    # the refusal precedes the CLI, which writes the target-start marker itself (--started-marker, PR #37), so a
    # refused re-run leaves no marker for the spend report to impute from
    body = "\n".join(ln for ln in step["run"].splitlines() if not ln.lstrip().startswith("#"))
    assert body.index('"$RUN_ATTEMPT" != "1"') < body.index("scripts.petri_audit.cli run") < body.index("target_started")
    for attempt in ("2", "3", ""):
        proc, marker, calls = _run_the_run_step(workflow, tmp_path, mode="run", attempt=attempt)
        assert proc.returncode != 0 and "mode run cannot be re-run from the Actions tab" in proc.stderr, proc.stderr
        assert not marker.exists(), "no marker: the spend report must impute nothing for a refused re-run"
        assert not calls.exists(), "the target was called"
    proc, marker, calls = _run_the_run_step(workflow, tmp_path, mode="run", attempt="1")
    assert proc.returncode == 0, proc.stderr
    assert marker.exists() and calls.read_text(encoding="utf-8").startswith("-m scripts.petri_audit.cli run ")
    # a dry run costs nothing and may re-run
    proc, marker, calls = _run_the_run_step(workflow, tmp_path, mode="dry_run", attempt="2")
    assert proc.returncode == 0 and marker.exists() and calls.exists(), proc.stderr


def test_defaults_cover_every_trigger_key_and_dispatch_input(workflow, defaults):
    on = workflow.get("on") or workflow.get(True)
    inputs = set(on["workflow_dispatch"]["inputs"])
    assert set(defaults) == set(ft.KNOWN_KEYS[TRIGGER]) == inputs
    # the park is unchanged by modes readapt and rejudge and by the adaptive auditor: source_run_id, source_runs and
    # auditor_model are read by some modes only, empty by default, and not keys of the park, so the committed park
    # file still equals PARK_DEFAULTS exactly (docs/petri_adaptive_design.md)
    mode_only_keys = ("source_run_id", "source_runs", "auditor_model")
    for mode_only in mode_only_keys:
        assert defaults[mode_only] == "" and mode_only not in ft.PARK_DEFAULTS[TRIGGER], mode_only
    assert {k: v for k, v in defaults.items() if k not in mode_only_keys} == ft.PARK_DEFAULTS[TRIGGER], \
        "the heredoc defaults are the park: a bare re-fire is a no-op"
    assert defaults["mode"] == "preflight" and defaults["commit_outputs"] == "false" and defaults["judge"] == "false"
    assert defaults["target"] == "mockllm/model"
    assert TRIGGER in ft.PAID_TRIGGERS and TRIGGER in ft.TRIGGERS


def test_the_trigger_file_is_absent_or_parked_so_a_branch_operation_re_fires_nothing():
    """The resting-state rule (AGENTS.md): a trigger file at rest is a loaded
    default any branch operation can pull, so it is either absent or the park.

    It was absent while the lane was unmerged; the owner parked the lane on
    2026-09-18 (fire_trigger.py park), so `main` now carries the park default
    and a branch cut before it still carries none. Either state is correct; a
    file holding anything else - a paid `mode: run` left at rest - is not, and
    would re-fire that configuration on the next merge, rebase or cherry-pick.
    """
    path = ROOT / ".github" / "trigger" / f"{TRIGGER}.json"
    if not path.exists():
        return
    params = json.loads(path.read_text(encoding="utf-8"))
    at_rest = {k: v for k, v in params.items() if not k.startswith("_")}
    assert at_rest == ft.PARK_DEFAULTS[TRIGGER], (
        "the trigger file at rest must be the park default, written by fire_trigger.py park, never by hand")
    assert not ft.is_paid_fire(TRIGGER, params), "a file at rest that would spend is the resting-state defect"


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
    assert run["if"] == "${{ needs.params.outputs.mode == 'dry_run' || needs.params.outputs.mode == 'run' }}"
    assert "$RUNNER_TEMP/petri-run" in run["run"]
    assert "LOG_MODEL_API" in run["env"] and '--log-model-api "$LOG_MODEL_API"' in run["run"], (
        "the log_model_api input must reach the CLI (Codex round 1: it was accepted and ignored)")
    judge = _step(workflow, "Judge of record")
    assert "mode == 'run'" in judge["if"] and "judge == 'true'" in judge["if"]
    adapt = _step(workflow, "Adapt")
    assert "--custody \"github_actions_artifact:90d\"" in adapt["run"] and "data/petri/runs/" in adapt["run"]
    upload = _step(workflow, "Upload the raw .eval")
    assert str(upload.get("uses", "")).startswith("actions/upload-artifact")
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
                             "Commit cost sidecars of a paid run (mode run or readapt; independent of commit_outputs)",
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
    assert judge_env == set(run["env"]) & judge_env | {"JUDGE_MODEL", "JUDGE_MAX_SPEND", "JUDGE_MAX_TOKENS", "SEEDS_FILE"}
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


def test_a_dry_run_uploads_its_seal_cleared_exports_and_the_summary_reads_the_run(workflow, raw):
    """Tenth-pass review (2026-09-17): a dry run's sanitised exports were
    destroyed with the runner (the commit path is mode run only) and the
    summary printed four manifest fields, so the structural measurements the
    pilot design waits on (design memo section 14) were never observable."""
    steps = _steps(workflow, "audit")
    names = [s.get("name", "") for s in steps]
    exports = _step(workflow, "Upload the seal-cleared sanitised exports (dry run or paid run; never a raw log)")
    # PR B (2026-09-18): a paid run's seal-cleared outputs are uploaded too, before the commit steps, so a commit that
    # fails after the spend leaves a recoverable copy; preflight has nothing to upload
    assert exports["if"] == "${{ needs.params.outputs.mode != 'preflight' }}"
    assert exports["with"]["name"] == "petri-audit-exports-${{ github.run_id }}-${{ github.run_attempt }}"
    assert names.index(exports["name"]) < names.index("Commit sanitised outputs to the branch (mode run or readapt; requires every prior step green)")
    assert "always()" not in exports["if"], "must depend on every prior step, the seal check and verify-chain included"
    # Non-blocking only where a committed copy follows it. Codex round 1 (PR #28): on a paid run that commits,
    # the recovery upload's OWN failure must not skip the commit step behind it (default success gating), or the
    # measurement is neither committed nor recoverable while the always()-gated sidecar step books the spend.
    # Codex rounds 3 and 5: where nothing is committed - a dry run, or a paid run with commit_outputs false -
    # this artifact is the only seal-cleared copy, so its failure stays fatal.
    assert exports["continue-on-error"] == ("${{ (needs.params.outputs.mode == 'run' || needs.params.outputs.mode == "
                                           "'readapt') && needs.params.outputs.commit_outputs == 'true' }}")
    commit = _step(workflow, "Commit sanitised outputs to the branch")
    assert "continue-on-error" not in commit, "only the recovery upload is non-blocking"
    assert str(exports["uses"]).startswith("actions/upload-artifact")
    assert "data/petri/runs/${{ env.RUN_STEM }}/" in exports["with"]["path"]
    # Codex (PR #27): the cumulative chain file references every earlier committed run, which the artifact does not
    # carry, so the run directory is uploaded alone and must verify on its own (verify-run runs before the upload)
    assert "manifests.chain" not in exports["with"]["path"]
    seal = _step(workflow, "Holdout seal check")
    assert 'verify-run --run-dir "data/petri/runs/$RUN_STEM"' in seal["run"] and "env" not in seal
    assert names.index(seal["name"]) < names.index(exports["name"])
    assert "petri-run/logs" not in exports["with"]["path"], "the raw .eval is never in this artifact"
    assert exports["with"]["if-no-files-found"] == "error" and exports["with"]["retention-days"] == 30
    assert "!data/petri/runs/**/*.eval" in exports["with"]["path"], "a raw log is excluded from the artifact by pattern"
    assert names.index("Holdout seal check over every publishable Petri output (fails closed)") < names.index(exports["name"])
    # Codex (PR #27): an artifact cannot be retracted, so the raw-log refusal must run before the upload, and the
    # upload (no always()) then never runs after that refusal failed the job
    assert names.index("Refuse to publish a raw log (belt and braces)") < names.index(exports["name"])
    # the summary step reads the run through the CLI, with the resolved params, the raw log location and the seeds
    summary = _step(workflow, "Job summary")
    assert "always()" in summary["if"] and "run-summary" in summary["run"]
    assert summary["env"]["RESOLVED_PARAMS"] == "${{ toJSON(needs.params.outputs) }}"
    assert summary["env"]["SEEDS_FILE"] == "${{ needs.params.outputs.seeds_file }}"
    for flag in ('--run-dir "data/petri/runs/$RUN_STEM"', '--mode "$MODE"', '--raw-eval-dir "$RUNNER_TEMP/petri-run/logs"',
                 '--seeds "$SEEDS_FILE"', '--params-file "$RUNNER_TEMP/resolved_params.json"', '>> "$GITHUB_STEP_SUMMARY"'):
        assert flag in summary["run"], flag
    # independent review of PR #27: the step is always(), so what it prints passes the holdout seal first
    assert '--seal-scan >> "$GITHUB_STEP_SUMMARY"' in summary["run"], "the rendered summary is scanned before it is published"
    # Codex (PR #27, eleventh round): the judge-start marker is evidence the summary must see
    assert '--judge-started-marker "$RUNNER_TEMP/petri-run/judge_started"' in summary["run"]
    assert "run-summary failed" in summary["run"], "a failed summary is reported, never a silent blank"


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
    base = dict(ft.PARK_DEFAULTS[TRIGGER], mode="run", judge="true", judge_max_spend="0.01", _nonce="n1")
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
    # a judge billed through a third key (google:, GEMINI_API_KEY) is refused before the push: it would be booked to the
    # anthropic lane while its vendor bills its own account (review of 2026-09-23, F-TH1). Every spec that bills
    # ANTHROPIC_API_KEY or OPENROUTER_API_KEY still passes, and an unknown provider is left to the workflow's
    # judge_spec_problems, as before
    for google in ("google:gemini-2.5-flash", "google"):
        with pytest.raises(ValueError, match="bills GEMINI_API_KEY"):
            ft.validate_params(TRIGGER, dict(base, target="anthropic/claude-haiku-4-5", judge_model=google))
    assert ft.petri_judge_key_env(dict(base, judge_model="google:x")) == "GEMINI_API_KEY"
    assert ft.petri_judge_key_env(dict(base, judge_model="claude-haiku-4-5")) == "ANTHROPIC_API_KEY"
    assert ft.petri_judge_key_env(dict(base, judge_model="openai:gpt-5.4-mini")) == "OPENROUTER_API_KEY"
    assert ft.petri_judge_key_env(dict(base, judge_model="nosuch:model")) is None
    assert ft.petri_judge_key_env(dict(base, judge="false", judge_model="google:x")) is None
    ft.validate_params(TRIGGER, dict(base, target=orl, judge_model="openrouter:google/gemini-2.5-flash"))
    ft.validate_params(TRIGGER, dict(base, target="anthropic/claude-haiku-4-5", judge_model="anthropic:claude-haiku-4-5"))
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


def test_the_fire_nonce_reaches_the_run_the_manifest_and_the_fallback_sidecar(workflow, raw):
    """PR B (2026-09-18): nothing tied a landed cost sidecar to the journal entry
    that reserved its spend. The params job now emits the trigger file's
    `_nonce` (metadata, never a trigger key), the run records it, and the
    fallback spend report carries it, so `reconcile-spend` can join the two."""
    params = workflow["jobs"]["params"]
    assert params["outputs"]["_nonce"] == "${{ steps.params.outputs._nonce }}"
    resolve = _step(workflow, "Resolve parameters", job="params")["run"]
    assert 'nonce = str(cfg.get("_nonce") or "")' in resolve and 'f.write("_nonce=" + nonce + "\\n")' in resolve
    assert '"_nonce"' not in resolve.split("defaults = {")[1].split("}")[0], "the nonce is not a trigger key"
    run = _step(workflow, "Run (mode dry_run or run; the raw .eval is written OUTSIDE the checkout)")
    assert run["env"]["JOURNAL_NONCE"] == "${{ needs.params.outputs._nonce }}" and '--journal-nonce "$JOURNAL_NONCE"' in run["run"]
    fallback = _step(workflow, "Spend report for an attempted run that produced no adapted report")
    assert fallback["env"]["JOURNAL_NONCE"] == "${{ needs.params.outputs._nonce }}"
    assert '--journal-nonce "$JOURNAL_NONCE"' in fallback["run"]
    # the adapter reads the nonce from run_params.json, which the run step writes; the adapt step passes that file
    adapt = _step(workflow, "Adapt (sanitised export, transcripts 0.2, rule outcomes, manifest, cost sidecar)")
    assert '--run-params "$RUNNER_TEMP/petri-run/run_params.json"' in adapt["run"]


def test_the_fallback_spend_report_waits_for_a_target_start_marker(workflow):
    """The always()-gated spend report runs even when a step BEFORE the run failed
    - seed validation, the environment lock, preflight - and with no eval log it
    imputes the FULL target ceiling. Since PR B binds the journal nonce into that
    sidecar, the ledger would fold a cost for a run that made no provider call and
    reconciliation would accept it as this fire's landed spend (Codex round 8)."""
    run_step = _step(workflow, "Run (mode dry_run or run")
    # the CLI writes the marker once the target model is built, immediately before the eval (2026-09-23): touched by
    # the shell before the CLI, a missing key or an unknown provider, which fail in get_model with no provider call,
    # booked the whole max_spend through this report
    body = "\n".join(ln for ln in run_step["run"].splitlines() if not ln.lstrip().startswith("#"))
    assert '--started-marker "$RUNNER_TEMP/petri-run/target_started"' in body, \
        "the run step must hand the CLI the marker the spend report keys off"
    assert "touch" not in body and body.count("target_started") == 1, "the shell must not create the marker itself"
    assert body.index("scripts.petri_audit.cli run") < body.index("--started-marker")
    spend = _step(workflow, "Spend report for an attempted run")
    assert '[ ! -f "$RUNNER_TEMP/petri-run/target_started" ]' in spend["run"], \
        "the target sidecar must not be imputed for a run that never started"
    # the judge's own marker is untouched: a judge that started and died is still booked at its ceiling
    assert '[ -f "$RUNNER_TEMP/petri-run/judge_started" ]' in spend["run"]
