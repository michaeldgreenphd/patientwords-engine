"""Offline regressions for review setup cost and immutable diff evidence.

Exercise each real workflow against a local filtered Git remote. No GitHub write,
provider call, measurement generation or published artifact is involved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = Path(".github/workflows/gemini-pr-review.yml")


@pytest.fixture(params=["engine", "frontend"])
def review_job(request: pytest.FixtureRequest) -> dict:
    root = ROOT
    if request.param == "frontend":
        explicit = os.environ.get("PW_SITE_ROOT")
        root = Path(explicit) if explicit is not None else ROOT.parent / "patientwords"
        if explicit is None and not root.exists():
            pytest.skip("companion patientwords checkout is absent")
        assert explicit is None or explicit, "PW_SITE_ROOT must not be empty"
        assert root.is_dir(), f"missing companion checkout: {root}"
    return yaml.safe_load((root / WORKFLOW).read_text())["jobs"]["review"]


def test_review_budget_and_failure_do_not_publish_success(review_job: dict) -> None:
    """80 turns can exhaust the observed 20-request allowance in one review."""
    gemini = next(step for step in review_job["steps"] if step.get("id") == "gemini")
    settings = json.loads(gemini["with"]["settings"])
    assert 0 < settings["model"]["maxSessionTurns"] <= 8
    assert review_job["timeout-minutes"] <= 10
    assert not gemini.get("continue-on-error", False)
    # The default success() guard must remain: quota/turn-limit errors cannot
    # cause the publisher to overwrite an earlier review with partial output.
    publisher = review_job["steps"][-1]
    assert publisher["name"] == "Create or update the sticky PR review comment"
    assert publisher["if"] == "steps.pr.outputs.eligible == 'true'"


def test_filtered_history_keeps_true_pr_diff(review_job: dict, tmp_path: Path) -> None:
    """An independently advanced base must not appear as a deletion in the PR.

    Old artifact blobs stay absent, while the exact head, unmodified consumers,
    merge-base content and full changed-path inventory remain available.
    """
    if shutil.which("jq") is None:
        pytest.skip("workflow shell regression requires jq")
    checkout_step = next(step for step in review_job["steps"] if step.get("uses") == "actions/checkout@v4")
    options = checkout_step["with"]
    assert options["fetch-depth"] == 0, "merge-base needs full history"
    assert options["filter"] == "blob:none", "avoid downloading old measurement blobs"
    assert options["persist-credentials"] is False
    script = next(step["run"] for step in review_job["steps"] if step["name"] == "Prepare immutable diff evidence")

    remote = tmp_path / "origin"
    checkout = tmp_path / "checkout"
    remote.mkdir()

    def git(*args: str, cwd: Path = remote) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True, check=True,
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Review fixture")
    git("config", "commit.gpgsign", "false")
    git("config", "uploadpack.allowFilter", "true")
    old_artifact = remote / "old-render.html"
    old_artifact.write_text("historical render not needed by this review\n")
    historical_blob = git("hash-object", str(old_artifact))
    git("add", ".")
    git("commit", "-m", "historical artifact")
    git("rm", "old-render.html")
    (remote / "changed.txt").write_text("before\n")
    (remote / "consumer.txt").write_text("untouched consumer\n")
    excluded = [
        "package-lock.json", "nested/pnpm-lock.yaml", "poetry.lock", "nested/bun.lockb",
        "docs/framework/petri_environment.lock.json", "npm-shrinkwrap.json",
        "assets/site.min.js", "site.min.css", "nested/client.min.mjs", "nested/client.min.cjs",
        "assets/site.min.js.map",
    ]
    for name in excluded:
        path = remote / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated before\n")
    git("add", ".")
    git("commit", "-m", "base")
    merge_base = git("rev-parse", "HEAD")
    git("switch", "-c", "feature")
    (remote / "changed.txt").write_text("after\n")
    for name in excluded:
        (remote / name).write_text("generated after\n")
    git("commit", "-am", "PR")
    head = git("rev-parse", "HEAD")
    git("switch", "main")
    (remote / "unrelated.txt").write_text("base advanced\n")
    git("add", ".")
    git("commit", "-m", "main advanced")
    base = git("rev-parse", "HEAD")

    # file:// exercises upload-pack filtering, unlike Git's local-copy shortcut.
    git("clone", "--no-checkout", f"--filter={options['filter']}", remote.as_uri(), str(checkout), cwd=tmp_path)
    git("checkout", head, cwd=checkout)
    assert git("rev-parse", "--is-shallow-repository", cwd=checkout) == "false"
    assert f"?{historical_blob}" in git("rev-list", "--objects", "--all", "--missing=print", cwd=checkout)
    assert (checkout / "consumer.txt").read_text() == "untouched consumer\n"
    (tmp_path / "gemini-pr.json").write_text(json.dumps({
        "number": 123, "head": {"sha": head, "ref": "feature"},
        "base": {"sha": base, "repo": {"full_name": "owner/repo"}},
    }))
    env = {
        **os.environ, "HEAD_SHA": head, "BASE_SHA": base, "COMPANION_SHA": "a" * 40,
        "COMPANION_BRANCH": "main", "COMPANION_REPO": "owner/companion", "RUNNER_TEMP": str(tmp_path),
    }
    subprocess.run(["bash", "-c", script], cwd=checkout, env=env, text=True, capture_output=True, check=True)
    context = checkout / "review-context"
    assert set((context / "changed-files.txt").read_text().splitlines()) == {"changed.txt", *excluded}
    diff = (context / "pr.diff").read_text()
    assert "-before\n+after\n" in diff
    assert "unrelated.txt" not in diff
    assert all(name not in diff for name in excluded)
    assert json.loads((context / "metadata.json").read_text())["diff_base_sha"] == merge_base
    assert git("rev-parse", "HEAD", cwd=checkout) == head
    assert git("diff", "HEAD", cwd=checkout) == "", "inspection must not change tracked files"
    assert f"?{historical_blob}" in git("rev-list", "--objects", "--all", "--missing=print", cwd=checkout)
