"""The model-evaluation lane's frontend-export step fails when its commit does not reach the branch.

Audit finding tests-04 (2026-09-30): the step "Export frontend table + commit to the dispatched branch" ended with
a three-attempt `pull --rebase && push && break` loop whose last command was `sleep`, so after three failed pushes
the step exited 0 and data/evaluations/model_evaluations_frontend.json was lost with a green run. The loop now
matches advice_evaluation.yml's commit step: five attempts, `git rebase --abort` after a failed attempt, `exit 1`
when none pushed.

CI-side behaviour cannot run offline, so the step's shell body is executed here as the runner executes it
(`bash -e`, the pattern of tests/test_petri_audit_workflow.py), with `git`, `python` and `sleep` stubbed on PATH:
the stub `git` records its arguments and fails `pull` or `push` on demand, and nothing touches a repository or the
network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "model_evaluation.yml"
PUSH = 'git push origin HEAD:"refs/heads/$BRANCH"'

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="the step body is a bash script")

# `git` stub: logs each call's arguments, one line per call; `pull` fails while PULL_FAILS is 1; `push` fails for
# its first PUSH_FAILURES calls; `commit` fails when COMMIT_FAILS is 1 (git's exit when there is nothing to commit).
GIT_STUB = """#!/bin/sh
echo "$@" >> "$STUB_LOG"
case "$1" in
  pull) [ "${PULL_FAILS:-0}" = 1 ] && exit 1; exit 0 ;;
  push)
    n=$(( $(cat "$PUSH_COUNT" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$PUSH_COUNT"
    [ "$n" -le "${PUSH_FAILURES:-0}" ] && exit 1
    exit 0 ;;
  commit) [ "${COMMIT_FAILS:-0}" = 1 ] && exit 1; exit 0 ;;
esac
exit 0
"""


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _export_step(workflow: dict) -> dict:
    steps = [s for s in workflow["jobs"]["evaluate"]["steps"] if PUSH in str(s.get("run", ""))]
    assert len(steps) == 1, f"expected one step pushing to the dispatched branch, found {len(steps)}"
    return steps[0]


def _run_export(workflow: dict, tmp_path: Path, *, results: bool = True, **fail: str) -> tuple[
        subprocess.CompletedProcess, list[str]]:
    """Execute the export step's shell body in a scratch directory with stubbed `git`, `python` and `sleep`.
    Returns the process and the stub `git`'s calls, one argument string per call."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("git", GIT_STUB),
                       ("python", '#!/bin/sh\ncat > /dev/null\nexit 0\n'),
                       ("sleep", '#!/bin/sh\nexit 0\n')):
        stub = bindir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    work = tmp_path / "work"
    (work / "eval_out").mkdir(parents=True)
    if results:
        (work / "eval_out" / "results.json").write_text("{}\n", encoding="utf-8")
    log = tmp_path / "git_calls.txt"
    env = {"PATH": os.pathsep.join([str(bindir), "/usr/bin", "/bin"]), "BRANCH": "main",
           "STUB_LOG": str(log), "PUSH_COUNT": str(tmp_path / "push_count.txt"), **fail}
    proc = subprocess.run(["bash", "-e", "-c", _export_step(workflow)["run"]], cwd=work, env=env,
                          capture_output=True, text=True, timeout=60)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


def _count(calls: list[str], prefix: str) -> int:
    return sum(1 for c in calls if c.startswith(prefix))


def test_the_step_fails_when_no_attempt_pushes(workflow: dict, tmp_path: Path) -> None:
    """The regression: every push is rejected, so the step must exit non-zero after five attempts, aborting any
    rebase left in progress after each one, and say why in an error annotation."""
    proc, calls = _run_export(workflow, tmp_path, PUSH_FAILURES="99")
    assert proc.returncode != 0, "the step passed although no push landed"
    assert _count(calls, "push origin HEAD:refs/heads/main") == 5
    assert _count(calls, "pull --rebase origin main") == 5
    assert _count(calls, "rebase --abort") == 5
    assert "::error::frontend export push to main failed after 5 attempts" in proc.stdout


def test_a_failed_rebase_is_aborted_and_the_step_fails(workflow: dict, tmp_path: Path) -> None:
    """A conflicting `pull --rebase` never reaches the push; each attempt aborts it, and five of them fail the step."""
    proc, calls = _run_export(workflow, tmp_path, PULL_FAILS="1")
    assert proc.returncode != 0
    assert _count(calls, "pull --rebase origin main") == 5
    assert _count(calls, "push ") == 0
    assert _count(calls, "rebase --abort") == 5


def test_a_push_that_lands_on_a_later_attempt_passes(workflow: dict, tmp_path: Path) -> None:
    proc, calls = _run_export(workflow, tmp_path, PUSH_FAILURES="2")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _count(calls, "push origin HEAD:refs/heads/main") == 3
    assert _count(calls, "rebase --abort") == 2


def test_a_first_push_that_lands_stops_the_loop(workflow: dict, tmp_path: Path) -> None:
    proc, calls = _run_export(workflow, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _count(calls, "push ") == 1 and _count(calls, "rebase --abort") == 0


def test_nothing_to_commit_still_passes_without_pushing(workflow: dict, tmp_path: Path) -> None:
    """Unchanged behaviour: when the export equals the committed file, `git commit` fails and the step exits 0."""
    proc, calls = _run_export(workflow, tmp_path, COMMIT_FAILS="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _count(calls, "commit ") == 1 and _count(calls, "push ") == 0


def test_a_run_without_results_still_passes_without_git(workflow: dict, tmp_path: Path) -> None:
    """Unchanged behaviour: a run that wrote no eval_out/results.json exports nothing and touches no git."""
    proc, calls = _run_export(workflow, tmp_path, results=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no results" in proc.stdout and calls == []


def test_the_step_wiring_is_unchanged(workflow: dict) -> None:
    """The step still runs after a failed evaluation, pushes to the ref that fired it, and the job keeps its
    ref-creation guard."""
    step = _export_step(workflow)
    assert step["if"] == "always()"
    assert step["env"]["BRANCH"] == "${{ github.ref_name }}"
    assert step["run"].lstrip().startswith("set -euo pipefail")
    assert workflow["jobs"]["evaluate"]["if"] == "${{ !github.event.created }}"
