"""The pull-request workflow stays an offline check and reports what it tested.

`.github/workflows/pr_checks.yml` is the one workflow in this repository that a pull
request starts. Every other workflow here is a measurement or operations lane, so the
properties that keep this one apart from them are checked from the parsed file:

* its triggers are exactly `pull_request` and `workflow_dispatch`;
* its permissions are `contents: read`, it names no secret and no deployment environment;
* its text holds none of the commands that fire a lane, write to a branch, publish or
  verify a release (the comments are searched too, so the file cannot drift into
  describing a step it must not have);
* its actions are pinned to commits another workflow here already uses;
* both jobs run the install, lint and suite commands of `verify.md` as written there;
* the paired job resolves the site revision before any checkout and checks out that SHA;
* a failing check fails its job: no job and no step has `continue-on-error`, every step
  carries the `if` written for it in `EXPECTED_STEPS`, and no check command is followed
  by `||` or by anything else on its line.

The step bodies that decide what a run reports are executed here as the runner executes
them (`bash -eo pipefail`, the pattern of `tests/test_model_evaluation_workflow.py`):
the step that resolves the site revision, against a local git repository that stands in
for the site; the steps that record the tested commits, against small local
repositories; the steps that list the skips, against a short pytest summary; the
whitespace gate, against small local merges; the boundary report, against receipts
with the fields `scripts/check_frontend_boundary.py` writes; and each check step,
with a stand-in for `python` and `git` that fails on request, to show that the step's
exit status is the check's. Nothing contacts GitHub.

Not exercised here: the event payload, the merge ref, `actions/checkout`, the runner's
disk and time limits, the browser download, and the checks themselves (the stand-in
runs no linter, no test and no gate). These tests say nothing about any model.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "pr_checks.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")
DOC = yaml.safe_load(TEXT)
ON = DOC.get(True, DOC.get("on"))  # YAML 1.1 reads a bare `on:` key as boolean True
JOBS = DOC["jobs"]
SITE = "michaeldgreenphd/patientwords"
Repos = tuple[Path, dict[str, str]]  # a fixture's directory and the commits it made there, by name

needs_bash_and_git = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                        reason="the step bodies are bash scripts that call git")

# Substrings the file must not hold, comments included. Each is a way to fire a lane, write
# to a repository, publish, verify a release, or run on an event other than the two allowed.
FORBIDDEN = (
    "fire_trigger", "git push", "gh workflow run", "repository_dispatch", ".github/trigger",
    "pull_request_target", "workflow_run", "schedule", "cron",
    "git commit", "git tag", "gh release", "gh api", "gh pr ", "curl ",
    "upload-artifact", "upload-pages-artifact", "deploy-pages",
    "results_snapshot", "check-release", "export_frontend_simulated", "publication_release",
    "ledger_update", "harvest", "medlang-batch-eval", "medlang-generate", "medlang-evaluate",
)


def _runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def _checkouts(job: dict) -> list[tuple[int, dict]]:
    return [(i, step) for i, step in enumerate(job["steps"]) if step.get("uses", "").startswith("actions/checkout@")]


def _step(job: str, wanted: str) -> dict:
    """The one step of `job` whose name starts with `wanted`."""
    found = [step for step in JOBS[job]["steps"] if step.get("name", "").startswith(wanted)]
    assert len(found) == 1, f"{job}: expected one step named {wanted!r}..., found {len(found)}"
    return found[0]


# ------------------------------------------------------------------ what the file may and may not be

def test_the_triggers_are_exactly_pull_request_and_workflow_dispatch() -> None:
    assert set(ON) == {"pull_request", "workflow_dispatch"}
    assert ON["pull_request"] in (None, {}), "no branch or path filter: every pull request is checked"
    inputs = ON["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"site_ref"}
    assert inputs["site_ref"]["required"] is False and inputs["site_ref"]["default"] == ""


def test_permissions_are_read_only_and_no_job_widens_them() -> None:
    assert DOC["permissions"] == {"contents": "read"}
    for name, job in JOBS.items():
        assert job.get("permissions", {"contents": "read"}) == {"contents": "read"}, name
        assert "environment" not in job, f"{name}: a deployment environment can carry secrets"


def test_no_secret_or_token_is_referenced() -> None:
    lowered = TEXT.lower()
    for needle in ("secrets.", "secrets[", "github.token", "github_token", "id-token"):
        assert needle not in lowered, needle


@pytest.mark.parametrize("needle", FORBIDDEN)
def test_the_file_holds_no_forbidden_command_or_event(needle: str) -> None:
    assert needle not in TEXT, f"{needle!r} must not appear in {WORKFLOW.name}, in a step or in a comment"


def test_no_run_script_interpolates_an_expression() -> None:
    """A branch name or an input reaches a script through `env`, never by text substitution into it."""
    for name, job in JOBS.items():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), f"{name}: {step.get('name')}"


def test_every_action_is_pinned_to_a_commit_another_workflow_here_uses() -> None:
    others = "\n".join(p.read_text(encoding="utf-8") for p in sorted(WORKFLOWS.glob("*.yml")) if p != WORKFLOW)
    uses = [step["uses"] for job in JOBS.values() for step in job["steps"] if "uses" in step]
    assert uses
    for ref in uses:
        assert re.fullmatch(r"actions/(checkout|setup-python)@[0-9a-f]{40}", ref), ref
        assert f"uses: {ref} # v" in others, f"{ref} is not a pin an existing workflow uses"
        assert re.search(rf"uses: {re.escape(ref)} # v\d+$", TEXT, re.M), f"{ref}: the version comment is missing"


def test_superseded_runs_of_one_pull_request_are_cancelled() -> None:
    concurrency = DOC["concurrency"]
    assert concurrency["cancel-in-progress"] is True
    assert concurrency["group"].startswith("pr-checks-") and "github.event.pull_request.number" in concurrency["group"]


# ------------------------------------------------------------------ the two jobs

def test_there_are_two_jobs_and_each_has_a_timeout() -> None:
    assert set(JOBS) == {"standalone", "paired"}
    assert "Standalone" in JOBS["standalone"]["name"] and "Paired" in JOBS["paired"]["name"]
    for name, job in JOBS.items():
        assert job["runs-on"] == "ubuntu-latest", name
        assert isinstance(job["timeout-minutes"], int) and 0 < job["timeout-minutes"] <= 60, name
        assert "needs" not in job and "if" not in job, f"{name}: each job reports on its own"


def test_the_standalone_job_checks_out_the_engine_and_nothing_else() -> None:
    job = JOBS["standalone"]
    checkouts = _checkouts(job)
    assert len(checkouts) == 1 and "repository" not in checkouts[0][1]["with"]
    assert "../patientwords" not in _runs(job) and "playwright" not in _runs(job)
    assert "python -m ruff check ." in _runs(job)
    assert "git -c core.whitespace=cr-at-eol diff --check 'HEAD^1' HEAD" in _runs(job)


def test_both_jobs_install_and_run_the_suite_as_verify_md_writes_them() -> None:
    verify = (ROOT / "verify.md").read_text(encoding="utf-8")
    install = [line.strip() for line in verify.splitlines() if line.startswith("python -m pip install -e ")]
    assert len(install) == 1, "verify.md's setup block should hold one editable-install line"
    assert "python -m pytest -q -ra\n" in verify
    for name, job in JOBS.items():
        assert install[0] in _runs(job), f"{name}: the install line differs from verify.md's setup block"
        assert "python -m pytest -q -ra " in _runs(job), name


def test_each_job_reports_its_skips_whether_or_not_the_suite_passed() -> None:
    for name in JOBS:
        report = _step(name, "Report the suite result and every skip")
        assert "always()" in report["if"], name
        assert "GITHUB_STEP_SUMMARY" in report["run"] and "SKIPPED" in report["run"] and "BLOCKED" in report["run"]


def test_the_site_commit_is_resolved_before_any_checkout_and_checked_out_by_sha() -> None:
    job = JOBS["paired"]
    resolve = [i for i, step in enumerate(job["steps"]) if step.get("id") == "site"]
    checkouts = _checkouts(job)
    assert len(resolve) == 1 and len(checkouts) == 2
    assert resolve[0] < min(i for i, _ in checkouts), "the site SHA must be known before anything is checked out"
    site = [step["with"] for _, step in checkouts if "repository" in step["with"]]
    assert len(site) == 1
    assert DOC["env"]["SITE_REPOSITORY"] == SITE and site[0]["repository"] == "${{ env.SITE_REPOSITORY }}"
    assert site[0]["ref"] == "${{ steps.site.outputs.sha }}"
    assert "sparse-checkout" not in site[0], "the seal check refuses a site checkout that hides tracked files"
    for _, step in checkouts:
        assert step["with"]["persist-credentials"] is False


def test_the_paired_job_runs_the_paired_gates_and_the_synthetic_boundary() -> None:
    script = _runs(JOBS["paired"])
    for command in ('python scripts/validate_frontend_contract.py --site "$PW_SITE_ROOT" --engine .',
                    'python scripts/claim_check.py --site "$PW_SITE_ROOT"',
                    'python scripts/seal_check.py --site "$PW_SITE_ROOT"',
                    'python scripts/check_pages.py --site "$PW_SITE_ROOT" --port 8901',
                    '"$PW_BOUNDARY_PY" scripts/boundary_client/generate.py --check',
                    '"$PW_BOUNDARY_PY" scripts/check_frontend_boundary.py --site "$PW_SITE_ROOT"',
                    "scripts/boundary_client/requirements.lock"):
        assert command in script, command
    assert "--strict" not in script, "report mode, as the site's own CI runs the contract check"


# ------------------------------------------------------------------ a failing check fails its job

INSTALLED = "${{ !cancelled() && steps.install.outcome == 'success' }}"
WITH_BROWSER = "${{ !cancelled() && steps.install.outcome == 'success' && steps.browser.outcome == 'success' }}"
BROWSER_ONLY = "${{ !cancelled() && steps.browser.outcome == 'success' }}"

# Every step of each job, in order: the start of its name (or the action it uses) and its `if`. None is no
# `if`, so the step runs only while every earlier step has succeeded. A condition written here holds in every
# run that is not cancelled, or names a step that must have succeeded. So a check that one of them keeps from
# running is in a job that an earlier step has already failed.
EXPECTED_STEPS: dict[str, tuple[tuple[str, str | None], ...]] = {
    "standalone": (
        ("Check out the engine commit under test", None),
        ("Record the tested commit", None),
        ("actions/setup-python@", None),
        ("Install (verify.md, Setup and sources of truth)", None),
        ("Lint (ruff)", INSTALLED),
        ("Whitespace gate on the pull request's diff", "${{ !cancelled() }}"),
        ("Test suite, standalone", INSTALLED),
        ("Report the suite result and every skip", "${{ always() }}"),
    ),
    "paired": (
        ("Resolve the site revision to a commit SHA", None),
        ("Check out the engine commit under test", None),
        ("Check out the site at the resolved commit", None),
        ("Record the tested commits", None),
        ("actions/setup-python@", None),
        ("Install (verify.md, Setup and sources of truth)", None),
        ("Install Playwright and Chromium", None),
        ("Test suite, paired", WITH_BROWSER),
        ("Report the suite result and every skip", "${{ always() }}"),
        ("Paired gate, contract", INSTALLED),
        ("Paired gate, claims", INSTALLED),
        ("Paired gate, holdout seal", INSTALLED),
        ("Paired gate, pages in Chromium", WITH_BROWSER),
        ("actions/setup-python@", BROWSER_ONLY),
        ("Install the boundary environment", BROWSER_ONLY),
        ("Synthetic exporter-to-browser boundary", "${{ !cancelled() && steps.boundary_env.outcome == 'success' }}"),
        ("Report the boundary result", "${{ always() }}"),
    ),
}

# Each check: its job, the start of its step's name, and its command as one whole line of the step's script.
CHECKS: tuple[tuple[str, str, str], ...] = (
    ("standalone", "Lint (ruff)", "python -m ruff check ."),
    ("standalone", "Whitespace gate", "git -c core.whitespace=cr-at-eol diff --check 'HEAD^1' HEAD"),
    ("standalone", "Test suite, standalone",
     'python -m pytest -q -ra 2>&1 | tee "$RUNNER_TEMP/pytest_standalone.log"'),
    ("paired", "Test suite, paired", 'python -m pytest -q -ra 2>&1 | tee "$RUNNER_TEMP/pytest_paired.log"'),
    ("paired", "Paired gate, contract",
     'python scripts/validate_frontend_contract.py --site "$PW_SITE_ROOT" --engine .'),
    ("paired", "Paired gate, claims", 'python scripts/claim_check.py --site "$PW_SITE_ROOT"'),
    ("paired", "Paired gate, holdout seal", 'python scripts/seal_check.py --site "$PW_SITE_ROOT"'),
    ("paired", "Paired gate, pages in Chromium", 'python scripts/check_pages.py --site "$PW_SITE_ROOT" --port 8901'),
    ("paired", "Synthetic exporter-to-browser boundary",
     '"$PW_BOUNDARY_PY" scripts/boundary_client/generate.py --check'),
    ("paired", "Synthetic exporter-to-browser boundary",
     '"$PW_BOUNDARY_PY" scripts/check_frontend_boundary.py --site "$PW_SITE_ROOT" --receipt "$PW_BOUNDARY_RECEIPT"'),
)
CHECK_IDS = ("ruff", "whitespace", "suite-standalone", "suite-paired", "contract", "claims", "seal", "pages",
             "boundary-generate", "boundary")

# Stands in for `python` and for `git` in a check step. It records its arguments and exits 3 when they hold
# $STUB_FAIL_ON. It runs no linter, no test and no gate: it shows what the step does with an exit status.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_LOG"
if [ -n "$STUB_FAIL_ON" ] && [[ "$*" == *"$STUB_FAIL_ON"* ]]; then exit 3; fi
exit 0
"""


def _label(step: dict) -> str:
    return step.get("name") or step["uses"]


def _logical_lines(script: str) -> list[str]:
    """The script's lines, with a backslash continuation joined to its line and runs of blanks made one."""
    return [re.sub(r"\s+", " ", line).strip() for line in script.replace("\\\n", " ").splitlines()]


def test_no_job_and_no_step_may_fail_without_failing_the_run() -> None:
    assert "continue-on-error" not in TEXT
    assert DOC["defaults"] == {"run": {"shell": "bash"}}, "a declared bash shell runs each script with -eo pipefail"
    for name, job in JOBS.items():
        extra = set(job) - {"name", "runs-on", "timeout-minutes", "permissions", "steps"}
        assert not extra, f"{name}: {sorted(extra)}"
        for step in job["steps"]:
            extra = set(step) - {"name", "id", "if", "uses", "with", "env", "run", "working-directory"}
            assert not extra, f"{name}: {_label(step)}: {sorted(extra)}"


def test_every_step_carries_the_condition_written_for_it() -> None:
    """A check whose `if` is false does not run and does not fail. So the `if` of every step is written out."""
    assert set(EXPECTED_STEPS) == set(JOBS)
    for name, job in JOBS.items():
        found = [(_label(step), step.get("if")) for step in job["steps"]]
        expected = EXPECTED_STEPS[name]
        assert len(found) == len(expected), f"{name}: {[label for label, _ in found]}"
        for (label, condition), (wanted, wanted_condition) in zip(found, expected):
            assert label.startswith(wanted), f"{name}: found the step {label!r} where {wanted!r} is expected"
            assert condition == wanted_condition, f"{name}: {label}: its `if` is {condition!r}"


@pytest.mark.parametrize(("job", "wanted", "command"), CHECKS, ids=CHECK_IDS)
def test_a_check_command_is_a_whole_line_and_nothing_on_it_masks_the_exit_status(job: str, wanted: str,
                                                                                 command: str) -> None:
    step = _step(job, wanted)
    script, lines = step["run"], _logical_lines(step["run"])
    assert command in lines, f"{wanted}: {command!r} is not one whole line of the script: {lines}"
    assert "||" not in script, f"{wanted}: `||` after a check discards the check's exit status"
    assert "set +" not in script, f"{wanted}: the script turns a shell option off"
    assert step["working-directory"] == "patientwords-engine"
    if len(lines) > 1:
        assert lines[0] == "set -euo pipefail", f"{wanted}: the script does not start with set -euo pipefail"
    if "|" in command:
        assert command.count("|") == 1 and "2>&1 | tee " in command, "the one pipe is to tee, under pipefail"


def _check_layout(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """<work>/patientwords-engine, <work>/patientwords, a runner temp directory and a directory of stand-ins."""
    work = tmp_path.resolve() / "checks"
    engine, site, temp, stubs = (work / name for name in ("patientwords-engine", "patientwords", "temp", "stubs"))
    for made in (engine, site, stubs, temp / "pw-boundary-venv" / "bin"):
        made.mkdir(parents=True)
    for stub in (stubs / "python", stubs / "git", temp / "pw-boundary-venv" / "bin" / "python"):
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(0o755)
    return engine, site, temp, stubs


def _stub_arguments(command: str, site: Path, temp: Path) -> str:
    """What the stand-in receives for `command`: the words after the program, as the shell passes them."""
    values = {"$PW_SITE_ROOT": str(site), "$PW_BOUNDARY_RECEIPT": str(temp / "frontend-boundary-receipt.json")}
    words = shlex.split(command.split(" 2>&1 | tee ")[0])
    return " ".join(values.get(word, word) for word in words[1:])


def _run_check_step(job: str, wanted: str, layout: tuple[Path, Path, Path, Path],
                    fail_on: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    engine, _, temp, stubs = layout
    log = temp / "stub.log"
    log.write_text("", encoding="utf-8")
    env = {"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "RUNNER_TEMP": str(temp),
           "GITHUB_STEP_SUMMARY": str(temp / "summary.md"), "EVENT_NAME": "pull_request",
           "STUB_LOG": str(log), "STUB_FAIL_ON": fail_on}
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step(job, wanted)["run"]],
                          cwd=engine, env=env, capture_output=True, text=True, timeout=60)
    return proc, log.read_text(encoding="utf-8").splitlines()


@needs_bash_and_git
@pytest.mark.parametrize(("job", "wanted", "command"), CHECKS, ids=CHECK_IDS)
def test_a_check_that_fails_fails_its_step_and_nothing_runs_after_it(tmp_path: Path, job: str, wanted: str,
                                                                     command: str) -> None:
    """The step is run twice with the stand-in: once with every command succeeding, once with the check failing."""
    layout = _check_layout(tmp_path)
    arguments = _stub_arguments(command, layout[1], layout[2])
    proc, calls = _run_check_step(job, wanted, layout, fail_on="")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert arguments in calls, f"{wanted}: the step did not run {command!r}: {calls}"
    proc, calls = _run_check_step(job, wanted, layout, fail_on=arguments)
    assert proc.returncode != 0, f"{wanted}: the step passed although {command!r} failed\n{proc.stdout}"
    assert calls[-1] == arguments, f"{wanted}: a command ran after the failed check: {calls}"


# ------------------------------------------------------------------ the site revision rule, executed

def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main",
                           *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name + "\n", encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def remote(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    """A local repository at <base>/michaeldgreenphd/patientwords, and the commits its refs name."""
    base = tmp_path_factory.mktemp("remote")
    repo = base / SITE
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    shas = {"first": _commit(repo, "first")}
    _git(repo, "tag", "-a", "v1", "-m", "an annotated tag")
    shas["main"] = _commit(repo, "second")
    for branch in ("feature/x", "archive/only-here"):
        _git(repo, "checkout", "-q", "-b", branch, "main")
        shas[branch] = _commit(repo, branch.replace("/", "_"))
    _git(repo, "checkout", "-q", "main")
    assert len(set(shas.values())) == 4
    return base, shas


def _resolve(base: Path, tmp_path: Path, *, branch: str,
             site_ref: str = "") -> tuple[subprocess.CompletedProcess, dict]:
    """Run the resolving step's body. https://github.com/ is rewritten to the local `base` directory."""
    out = tmp_path / f"output_{len(list(tmp_path.iterdir()))}"
    out.touch()
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "1",
           "GIT_CONFIG_KEY_0": f"url.{base.as_uri()}/.insteadOf", "GIT_CONFIG_VALUE_0": "https://github.com/",
           "SITE_REPOSITORY": DOC["env"]["SITE_REPOSITORY"], "INPUT_SITE_REF": site_ref, "ENGINE_BRANCH": branch,
           "GITHUB_OUTPUT": str(out)}
    step = next(step for step in JOBS["paired"]["steps"] if step.get("id") == "site")
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=120)
    outputs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())
    return proc, outputs


@needs_bash_and_git
@pytest.mark.parametrize(("branch", "site_ref", "ref", "sha_of", "rule"), [
    # rule 1: the manual input wins over a same-named branch, as a branch, an annotated tag or a commit
    ("feature/x", "main", "main", "main", "1: "),
    ("feature/x", "v1", "v1", "first", "1: "),
    ("main", "feature/x", "feature/x", "feature/x", "1: "),
    # rule 2: the same-named site branch
    ("feature/x", "", "refs/heads/feature/x", "feature/x", "2: "),
    # rule 3: no such branch. `only-here` must not match the site's `archive/only-here`
    ("no-such-branch", "", "refs/heads/main", "main", "3: FALLBACK"),
    ("only-here", "", "refs/heads/main", "main", "3: FALLBACK"),
])
def test_the_site_revision_rules_apply_in_order(remote: Repos, tmp_path: Path, branch: str, site_ref: str, ref: str,
                                                sha_of: str, rule: str) -> None:
    base, shas = remote
    proc, outputs = _resolve(base, tmp_path, branch=branch, site_ref=site_ref)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert outputs["sha"] == shas[sha_of] and outputs["ref"] == ref and outputs["rule"].startswith(rule), outputs
    for printed in (f"site SHA:  {shas[sha_of]}", f"site ref:  {ref}", f"chosen by: rule {rule}"):
        assert printed in proc.stdout, proc.stdout


@needs_bash_and_git
def test_a_full_commit_sha_given_as_the_input_is_used_as_written(remote: Repos, tmp_path: Path) -> None:
    base, shas = remote
    proc, outputs = _resolve(base, tmp_path, branch="feature/x", site_ref=shas["first"])
    assert proc.returncode == 0 and outputs["sha"] == shas["first"] and outputs["rule"].startswith("1: ")


@needs_bash_and_git
def test_an_explicit_site_ref_that_does_not_exist_blocks_the_job_and_never_falls_back(
        remote: Repos, tmp_path: Path) -> None:
    base, _ = remote
    proc, outputs = _resolve(base, tmp_path, branch="feature/x", site_ref="no-such-ref")
    assert proc.returncode == 1 and outputs == {}
    assert "BLOCKED" in proc.stdout and "no fallback" in proc.stdout and "FALLBACK to site main" not in proc.stdout


@needs_bash_and_git
def test_a_failed_lookup_blocks_the_job_and_is_not_read_as_a_missing_branch(tmp_path: Path) -> None:
    """Without the exit-code distinction an unreachable site would resolve to the fallback, or to nothing."""
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    for site_ref in ("", "main"):
        proc, outputs = _resolve(empty, tmp_path, branch="feature/x", site_ref=site_ref)
        assert proc.returncode != 0 and outputs == {}, proc.stdout + proc.stderr
        assert "BLOCKED: git ls-remote could not query the site repository" in proc.stderr


# ------------------------------------------------------------------ the recorded commits, executed

@pytest.fixture(scope="module")
def checkouts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    """<work>/patientwords-engine at a merge of a head commit into a base commit, and <work>/patientwords."""
    work = tmp_path_factory.mktemp("work")
    engine, site = work / "patientwords-engine", work / "patientwords"
    for repo in (engine, site):
        repo.mkdir()
        _git(repo, "init", "-q")
    shas = {"base": _commit(engine, "base")}
    _git(engine, "checkout", "-q", "-b", "topic")
    shas["head"] = _commit(engine, "head")
    _git(engine, "checkout", "-q", "main")
    _git(engine, "merge", "-q", "--no-ff", "-m", "merge", "topic")
    shas["merge"] = _git(engine, "rev-parse", "HEAD")
    shas["site"] = _commit(site, "site")
    return work, shas


def _record(job: str, work: Path, tmp_path: Path, shas: dict[str, str], **override: str) -> tuple[
        subprocess.CompletedProcess, str]:
    summary = tmp_path / f"summary_{len(list(tmp_path.iterdir()))}.md"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_SHA": shas["merge"],
           "EVENT_NAME": "pull_request", "PR_HEAD_SHA": shas["head"], "PR_BASE_SHA": shas["base"],
           "SITE_REF": "refs/heads/feature/x",
           "SITE_SHA": shas["site"], "SITE_RULE": "2: the site branch with the same name as the engine branch"}
    env.update(override)
    step = _step(job, "Record the tested commit")
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]], cwd=work, env=env,
                          capture_output=True, text=True, timeout=120)
    return proc, summary.read_text(encoding="utf-8") if summary.exists() else ""


@needs_bash_and_git
def test_the_paired_job_prints_both_commits_and_the_rule_to_the_log_and_the_summary(
        checkouts: Repos, tmp_path: Path) -> None:
    work, shas = checkouts
    proc, summary = _record("paired", work, tmp_path, shas)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for text in (proc.stdout, summary):
        for line in (f"- engine head SHA: {shas['head']}",
                     f"- tested merge SHA: {shas['merge']} (parents: base {shas['base']}, head {shas['head']})",
                     f"- base SHA: {shas['base']}",
                     "- site ref: refs/heads/feature/x",
                     f"- site SHA: {shas['site']}",
                     "- site revision chosen by rule 2: the site branch with the same name as the engine branch",
                     "- provider keys in the environment: none"):
            assert line in text, line


@needs_bash_and_git
def test_a_manual_run_says_it_has_no_merge_and_no_base(checkouts: Repos, tmp_path: Path) -> None:
    work, shas = checkouts
    proc, summary = _record("paired", work, tmp_path, shas, EVENT_NAME="workflow_dispatch", PR_HEAD_SHA="",
                            PR_BASE_SHA="")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"- engine head SHA: {shas['merge']}" in summary
    assert "- tested merge SHA: none (manual run on a branch, not a pull request)" in summary
    assert "- base SHA: none (manual run on a branch, not a pull request)" in summary


@needs_bash_and_git
@pytest.mark.parametrize(("override", "message"), [
    ({"GITHUB_SHA": "0" * 40}, "the engine checkout is at"),
    ({"SITE_SHA": "0" * 40}, "the site checkout is at"),
    ({"PR_HEAD_SHA": "0" * 40}, "the tested merge holds head"),
    ({"OPENROUTER_API_KEY": "x"}, "OPENROUTER_API_KEY is set in this job"),
])
def test_a_commit_that_is_not_the_expected_one_or_a_provider_key_fails_the_paired_job(
        checkouts: Repos, tmp_path: Path, override: dict[str, str], message: str) -> None:
    work, shas = checkouts
    proc, summary = _record("paired", work, tmp_path, shas, **override)
    assert proc.returncode == 1 and message in proc.stdout and "Tested commits" not in summary, proc.stdout


@needs_bash_and_git
def test_the_standalone_job_refuses_a_site_checkout_and_says_it_has_none(checkouts: Repos, tmp_path: Path) -> None:
    work, shas = checkouts
    proc, _ = _record("standalone", work, tmp_path, shas)
    assert proc.returncode == 1 and "a site checkout is present in the standalone job" in proc.stdout
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copytree(work / "patientwords-engine", alone / "patientwords-engine")
    proc, summary = _record("standalone", alone, tmp_path, shas)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"- engine head SHA: {shas['head']}" in summary and f"- tested merge SHA: {shas['merge']}" in summary
    assert "- site: none. This job has no site checkout; tests that need one skip." in summary
    proc, _ = _record("standalone", alone, tmp_path, shas, PW_SITE_ROOT=str(work / "patientwords"))
    assert proc.returncode == 1 and "a site checkout is present in the standalone job" in proc.stdout


# ------------------------------------------------------------------ the skip report, executed

def _report(job: str, tmp_path: Path, log_text: str | None) -> tuple[subprocess.CompletedProcess, str]:
    name = "pytest_standalone.log" if job == "standalone" else "pytest_paired.log"
    if log_text is not None:
        (tmp_path / name).write_text(log_text, encoding="utf-8")
    summary = tmp_path / "summary.md"
    env = {"PATH": os.environ["PATH"], "RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(summary),
           "SUITE_OUTCOME": "success" if log_text is not None else "skipped"}
    step = _step(job, "Report the suite result and every skip")
    # the runner sets what the step's `env` declares and nothing else: an undeclared name is unbound under set -u
    env.update({name: value for name, value in SITE_ENV.items() if name in step["env"]})
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=60)
    return proc, summary.read_text(encoding="utf-8")


SITE_ENV = {"SITE_REF": "refs/heads/main", "SITE_SHA": "c" * 40,
            "SITE_RULE": "3: FALLBACK to site main (the site has no branch named like the engine branch)"}
# The reason tests/test_check_site_links.py gives when the site checkout is present and predates the test.
OLDER_SITE_SKIP = ("SKIPPED [1] tests/test_check_site_links.py:465: the sibling site checkout has no "
                   "docs/site_routes.json: it is a revision from before the definition was added, and the paired "
                   "check is blocked there (exit 2), not passed")
SITE_OR_BROWSER_SKIPS = (
    OLDER_SITE_SKIP,
    "SKIPPED [6] tests/test_start_here_page.py:110: the sibling site checkout is not on disk",
    "SKIPPED [1] tests/test_shared_conventions.py:277: site checkout not found at /w/patientwords; set PW_SITE_ROOT",
    "SKIPPED [1] tests/test_experiment_index.py:380: no sibling site index at /w/patientwords/data/x.json",
    "SKIPPED [1] tests/test_check_pages_browser.py:102: could not import 'playwright': No module named 'playwright'",
    "SKIPPED [1] tests/test_check_results_page.py:506: no Chromium executable found (CHROMIUM, /opt/pw-browsers)",
)
OTHER_SKIP = "SKIPPED [1] tests/test_petri_equity_pair_seeds.py:193: this study does not judge barrier_help"


@needs_bash_and_git
@pytest.mark.parametrize("skip", SITE_OR_BROWSER_SKIPS)
def test_a_skip_that_names_the_site_or_the_browser_fails_the_paired_job_only(tmp_path: Path, skip: str) -> None:
    """Both jobs list the skip. The standalone job expects it; the paired job provides the site and Chromium.

    The paired job's message states what the log shows and no cause: the first skip line here comes from a site
    checkout that is present and older than the test requires, which "for want of the site checkout" misnamed."""
    log = f"..s\n=== short test summary info ===\n{skip}\n{OTHER_SKIP}\n2 passed, 2 skipped in 0.10s\n"
    for job, code in (("standalone", 0), ("paired", 1)):
        proc, summary = _report(job, tmp_path, log)
        assert proc.returncode == code, (job, proc.stdout, proc.stderr)
        assert skip in summary and OTHER_SKIP in summary and "2 passed, 2 skipped in 0.10s" in summary, job
    printed = proc.stdout.splitlines()
    assert printed[0] == "Skip lines whose reason names the site or the browser:" and printed[1] == skip
    assert OTHER_SKIP not in proc.stdout, "only the matching skip lines are listed"
    assert printed[2:5] == [f"site ref:  {SITE_ENV['SITE_REF']}", f"site SHA:  {SITE_ENV['SITE_SHA']}",
                            f"chosen by: rule {SITE_ENV['SITE_RULE']}"]
    assert len(printed) == 6 and printed[5].startswith("::error::"), printed
    for needle in ("A test skipped for a reason that names the site or the browser",
                   "it did not run in this job",
                   "The paired site commit may be older than the test requires",
                   f"site ref {SITE_ENV['SITE_REF']}", f"site SHA {SITE_ENV['SITE_SHA']}",
                   f"chosen by rule {SITE_ENV['SITE_RULE']}"):
        assert needle in printed[5], needle
    assert "for want of" not in proc.stdout and "which this job provides" not in proc.stdout


@needs_bash_and_git
def test_other_skips_are_listed_and_do_not_fail_either_job_and_a_missing_log_is_blocked(tmp_path: Path) -> None:
    for job in JOBS:
        proc, summary = _report(job, tmp_path, f"{OTHER_SKIP}\n1 passed, 1 skipped in 0.10s\n")
        assert proc.returncode == 0 and OTHER_SKIP in summary, (job, proc.stdout, proc.stderr)
    empty = tmp_path / "empty"
    empty.mkdir()
    for job in JOBS:
        proc, summary = _report(job, empty, None)
        assert proc.returncode == 0 and "BLOCKED: the suite did not run" in summary
        assert "Step outcome: skipped." in summary


# ------------------------------------------------------------------ the whitespace gate, executed

def _merge_adding(tmp_path: Path, name: str, content: bytes) -> Path:
    """A repository at a merge whose second parent adds one file with exactly these bytes."""
    repo = tmp_path / "merge"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / name).write_bytes(content)
    _git(repo, "-c", "core.autocrlf=false", "add", name)
    _git(repo, "commit", "-q", "-m", name)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "topic")
    assert _git(repo, "cat-file", "-s", f"HEAD:{name}") == str(len(content)), "the bytes were changed on the way in"
    return repo


def _whitespace_gate(repo: Path, tmp_path: Path, event: str) -> tuple[subprocess.CompletedProcess, str]:
    summary = tmp_path / "summary.md"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GITHUB_STEP_SUMMARY": str(summary), "EVENT_NAME": event}
    step = _step("standalone", "Whitespace gate")
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=60)
    return proc, summary.read_text(encoding="utf-8") if summary.exists() else ""


@needs_bash_and_git
@pytest.mark.parametrize(("name", "content", "reported"), [
    # a recorded CSV with CRLF line endings: plain `git diff --check` reports each line as trailing whitespace
    ("record.csv", b"phrase,count\r\nalpha,1\r\n", None),
    ("clean.txt", b"clean\n", None),
    # every other whitespace error is still an error, with or without a carriage return after it
    ("notes.txt", b"clean\ntrailing space \n", "notes.txt:2: trailing whitespace."),
    ("both.csv", b"phrase,count \r\nalpha,1\r\n", "both.csv:1: trailing whitespace."),
    ("indent.txt", b"x\n \tspace before a tab\n", "indent.txt:2: space before tab in indent."),
    ("tail.txt", b"x\n\n\n", "tail.txt:2: new blank line at EOF."),
], ids=["crlf-csv", "clean", "trailing-space", "trailing-space-before-cr", "space-before-tab", "blank-line-at-eof"])
def test_the_whitespace_gate_passes_crlf_line_endings_and_fails_every_other_whitespace_error(
        tmp_path: Path, name: str, content: bytes, reported: str | None) -> None:
    repo = _merge_adding(tmp_path, name, content)
    proc, _ = _whitespace_gate(repo, tmp_path, "pull_request")
    if reported is None:
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "git diff --check: clean between " in proc.stdout
    else:
        assert proc.returncode != 0 and reported in proc.stdout, proc.stdout + proc.stderr
        assert "clean between" not in proc.stdout


@needs_bash_and_git
def test_the_whitespace_gate_of_a_manual_run_says_not_run(tmp_path: Path) -> None:
    repo = _merge_adding(tmp_path, "notes.txt", b"trailing space \n")
    proc, summary = _whitespace_gate(repo, tmp_path, "workflow_dispatch")
    assert proc.returncode == 0 and "NOT RUN: a manual run has no pull request base" in summary


# ------------------------------------------------------------------ the boundary report, executed

needs_python3 = pytest.mark.skipif(shutil.which("python3") is None, reason="the boundary report step runs python3")
RECEIPT_SKIPS = [
    "SKIPPED [1] tests/test_validate_frontend_contract.py:1203: the sibling checkout lacks the reviewed revision",
    "SKIPPED [1] tests/test_frontend_boundary.py:148: not a git checkout (the boundary's own temporary layout)",
]


def _receipt(**changed: object) -> dict:
    """A receipt with the field names scripts/check_frontend_boundary.py writes. Every value is made up."""
    receipt = {
        "schema": "patientwords.frontend-boundary-receipt/1", "evidence": "local synthetic software test only",
        "engine": {"head": "a" * 40}, "frontend": {"head": "b" * 40}, "fixture_sha256": "c" * 64, "result": "passed",
        "checks": [
            {"name": "layout_absent_input_named", "result": "unrun",
             "reason": "the engine checkout holds no file outside the layout"},
            {"name": "affected_offline_checks_in_sparse_layout", "result": "passed",
             "command": "python -m pytest tests/test_x.py -q -rs", "summary": "399 passed, 2 skipped in 5.52s",
             "skipped": RECEIPT_SKIPS},
            {"name": "real_exporter_cli_in_sparse_layout", "result": "passed"},
        ]}
    receipt.update(changed)
    return receipt


def _boundary_report(tmp_path: Path, receipt_text: str | None) -> tuple[subprocess.CompletedProcess, str]:
    if receipt_text is not None:
        (tmp_path / "frontend-boundary-receipt.json").write_text(receipt_text, encoding="utf-8")
    summary = tmp_path / "summary.md"
    env = {"PATH": os.environ["PATH"], "RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(summary),
           "BOUNDARY_OUTCOME": "success" if receipt_text is not None else "skipped"}
    step = _step("paired", "Report the boundary result")
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=60)
    return proc, summary.read_text(encoding="utf-8")


def test_the_boundary_report_reads_field_names_the_receipt_writer_writes() -> None:
    writer = (ROOT / "scripts" / "check_frontend_boundary.py").read_text(encoding="utf-8")
    report = _step("paired", "Report the boundary result")["run"]
    for name in ("checks", "result", "failure", "failure_message", "evidence", "engine", "frontend", "head",
                 "fixture_sha256", "name", "summary", "skipped", "reason"):
        assert f'"{name}"' in writer, f"scripts/check_frontend_boundary.py writes no field {name!r}"
        assert re.search(rf"""['"]{name}['"]""", report), f"the report step does not read {name!r}"
    for name in sorted(set(_receipt()) | {key for check in _receipt()["checks"] for key in check}):
        assert f'"{name}"' in writer, f"the receipt of these tests uses {name!r}, which the writer does not write"


@needs_bash_and_git
@needs_python3
def test_the_boundary_report_prints_each_check_with_its_summary_and_its_skips(tmp_path: Path) -> None:
    proc, summary = _boundary_report(tmp_path, json.dumps(_receipt()))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert summary == proc.stdout
    for line in ("Step outcome: success.", "- result: passed (3 checks recorded)",
                 f"- engine HEAD in the receipt: {'a' * 40}", f"- site HEAD in the receipt: {'b' * 40}",
                 "A skipped test is not a passed test.",
                 "layout_absent_input_named: unrun", "  reason: the engine checkout holds no file outside the layout",
                 "affected_offline_checks_in_sparse_layout: passed", "  summary: 399 passed, 2 skipped in 5.52s",
                 *(f"  {skip}" for skip in RECEIPT_SKIPS), "real_exporter_cli_in_sparse_layout: passed"):
        assert line in summary.splitlines(), line
    assert "- failure:" not in summary


@needs_bash_and_git
@needs_python3
def test_the_boundary_report_of_a_failed_run_names_the_failure(tmp_path: Path) -> None:
    failed = _receipt(result="failed", failure="LayoutError", failure_message="stage offline_tests asked for ENGINE/x",
                      checks=_receipt()["checks"][:1])
    proc, summary = _boundary_report(tmp_path, json.dumps(failed))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "- result: failed (1 checks recorded)" in summary
    assert "- failure: LayoutError stage offline_tests asked for ENGINE/x" in summary


@needs_bash_and_git
@needs_python3
@pytest.mark.parametrize(("receipt_text", "printed"), [
    ("{}", "- result: not recorded (0 checks recorded)"),
    (json.dumps({"result": "passed", "checks": [{"name": "x"}, 7, {"result": "passed", "skipped": "text"}],
                 "engine": 3}), "x: not recorded"),
    ("[]", "BLOCKED: the receipt is not a JSON object."),
    ('{"checks": [', "BLOCKED: the receipt could not be read as JSON (JSONDecodeError)."),
    (None, "BLOCKED: the boundary wrote no receipt, so it did not run."),
], ids=["empty-object", "odd-shapes", "a-list", "truncated", "no-receipt"])
def test_the_boundary_report_does_not_fail_on_a_receipt_that_lacks_a_field(tmp_path: Path, receipt_text: str | None,
                                                                           printed: str) -> None:
    """The report step reports. The boundary step's own exit status is what fails the job."""
    proc, summary = _boundary_report(tmp_path, receipt_text)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "### Synthetic exporter-to-browser boundary" in summary and printed in summary.splitlines()


# ------------------------------------------------------------------ the guide names what the workflow runs

def test_verify_md_names_the_workflow_and_each_site_revision_rule() -> None:
    verify = (ROOT / "verify.md").read_text(encoding="utf-8")
    assert "`.github/workflows/pr_checks.yml`" in verify
    section = verify[verify.index("## Pull-request checks"):]
    section = " ".join(section[:section.index("\n## ", 1)].split())  # a needle may span a line break of the guide
    for needle in ("site_ref", "same name", "fallback", "check-release", "skip",
                   "older than the test requires", "a site branch of the same name",
                   "core.whitespace=cr-at-eol", "`CI=true`", "`GITHUB_ACTIONS=true`"):
        assert needle in section, needle
