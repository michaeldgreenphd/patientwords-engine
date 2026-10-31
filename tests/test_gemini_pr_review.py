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
def workflow(request: pytest.FixtureRequest) -> dict:
    root = ROOT
    if request.param == "frontend":
        explicit = os.environ.get("PW_SITE_ROOT")
        root = Path(explicit) if explicit is not None else ROOT.parent / "patientwords"
        if explicit is None and not root.exists():
            pytest.skip("companion patientwords checkout is absent")
        assert explicit is None or explicit, "PW_SITE_ROOT must not be empty"
        assert root.is_dir(), f"missing companion checkout: {root}"
    return yaml.safe_load((root / WORKFLOW).read_text())


@pytest.fixture
def review_job(workflow: dict) -> dict:
    return workflow["jobs"]["review"]


def _step(job: dict, *, step_id: str | None = None, name: str | None = None) -> dict:
    return next(s for s in job["steps"] if (step_id and s.get("id") == step_id) or (name and s.get("name") == name))


PUBLISHER = "Create or update the sticky PR review comment"


def test_review_budget_and_failure_do_not_publish_success(review_job: dict) -> None:
    """Every model turn is one request, and an uncapped session (up to 80 turns before be476d3a) could spend a
    20-request allowance in one review, so the session is capped. The cap was 8 until 2026-10-31, when a three-file
    review ended in FatalTurnLimitedError before writing; it is now 14. The job limit covers setup and the publisher
    as well as both review steps, so it must keep a reserve beyond them, or a slow setup lets GitHub cancel the job
    before the publisher reports the failure (Codex on patientwords#21)."""
    settings = json.loads(review_job["env"]["GEMINI_SETTINGS"])
    assert settings == {
        "tools": {"core": ["read_file", "read_many_files", "list_directory", "glob", "grep_search"]},
        "mcp": {"allowed": []}, "hooksConfig": {"enabled": False}, "skills": {"enabled": False},
        "advanced": {"ignoreLocalEnv": True}, "model": {"maxSessionTurns": 14},
    }
    primary, fallback = _step(review_job, step_id="gemini"), _step(review_job, step_id="gemini_fallback")
    for step in (primary, fallback):
        assert step["uses"] == "google-github-actions/run-gemini-cli@v0"
        assert step["with"]["settings"] == "${{ env.GEMINI_SETTINGS }}"
        assert step["with"]["prompt"] == "${{ env.GEMINI_REVIEW_PROMPT }}"
        # the publisher reports a failure and fails the job; continuing lets it and the fallback run
        assert step["continue-on-error"] is True
    assert primary["timeout-minutes"] == 10 and fallback["timeout-minutes"] == 3
    assert review_job["timeout-minutes"] == 20
    assert review_job["timeout-minutes"] - (primary["timeout-minutes"] + fallback["timeout-minutes"]) >= 5
    # opt-in, no default model: the live run of 2026-10-31 found the requested default, gemini-2.5-flash, refused
    # as "no longer available to new users", so a hard-coded ID can silently break the fallback
    assert fallback["with"]["gemini_model"] == "${{ vars.GEMINI_FALLBACK_MODEL }}"
    # the fallback spends a call only after a quota or availability error, never after e.g. a bad key
    condition = fallback["if"]
    assert "vars.GEMINI_FALLBACK_MODEL != ''" in condition
    assert "steps.gemini.outcome == 'failure'" in condition
    assert all(f"contains(steps.gemini.outputs.error, '{code}')" in condition
               for code in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"))
    publisher = review_job["steps"][-1]
    assert publisher["name"] == PUBLISHER
    # !cancelled(), not always(): a superseded run, cancelled by the concurrency group, posted a misleading "no error
    # output" diagnostic on 2026-10-31 (run 41198275188); a failed or step-timed-out review is still reported
    assert publisher["if"] == "${{ !cancelled() && steps.pr.outputs.eligible == 'true' }}"
    assert condition.startswith("${{ !cancelled() &&") and "always()" not in condition
    assert "capped at 14 model turns" in review_job["env"]["GEMINI_REVIEW_PROMPT"]
    assert "by the thirteenth turn" in review_job["env"]["GEMINI_REVIEW_PROMPT"]


def test_review_triggers_match_the_agents_review_request(workflow: dict) -> None:
    """Agents post `@codex review` on every PR open and push (docs/agent_reference.md), often on drafts, and never
    `@gemini-cli`; and the owner may mark a draft ready and merge seconds later, before the ready_for_review run
    starts. So the authorized comment trigger accepts either mention, and the comment path reviews drafts."""
    on = workflow[True]
    assert set(on["pull_request"]["types"]) == {"opened", "synchronize", "reopened", "ready_for_review"}
    assert on["issue_comment"]["types"] == ["created"]
    job_if = workflow["jobs"]["review"]["if"]
    assert "contains(github.event.comment.body, '@gemini-cli') ||" in job_if
    assert "contains(github.event.comment.body, '@codex review')" in job_if
    assert "github.event.comment.user.type != 'Bot'" in job_if
    assert '["OWNER", "MEMBER", "COLLABORATOR"]' in job_if
    resolve = _step(workflow["jobs"]["review"], step_id="pr")["run"]
    assert '($event != "pull_request" or .draft != true)' in resolve, "only automatic reviews skip drafts"


def test_ripgrep_is_ensured_before_the_cli(review_job: dict) -> None:
    names = [s.get("id") or s["name"] for s in review_job["steps"]]
    rg = names.index("Ensure ripgrep for the CLI's search tool")
    assert rg < names.index("gemini") < names.index("gemini_fallback") < names.index(PUBLISHER)
    assert "apt-get install -y -qq ripgrep" in review_job["steps"][rg]["run"]


_FAKE_GH = r"""#!/usr/bin/env bash
set -euo pipefail
args="$*"
input=$(sed -n 's#.*--input \([^ ]*\).*#\1#p' <<< "$args")
case "$args" in
  *"--method PATCH"*) id=$(sed -n 's#.*issues/comments/\([0-9]*\).*#\1#p' <<< "$args"); cp "$input" "$FAKE/patched_$id.json" ;;
  *"--method POST"*) cp "$input" "$FAKE/posted.json" ;;
  *"/comments"*) cat "$FAKE/comments.json" ;;
  *"/pulls/"*) cat "$FAKE/pr.json" ;;
  *) echo "unexpected gh call: $args" >&2; exit 9 ;;
esac
"""
_FAKE_GIT = """#!/usr/bin/env bash
[[ "$1" == "ls-remote" ]] || { echo "unexpected git call: $*" >&2; exit 9; }
printf '%s\trefs/heads/main\n' "cccccccccccccccccccccccccccccccccccccccc"
"""
HEAD = "a" * 40
MARKER = "<!-- gemini-macro-review -->"


def _bot(comment_id: int, body: str, user: str = "github-actions[bot]", kind: str = "Bot") -> dict:
    return {"id": comment_id, "body": body, "user": {"login": user, "type": kind}}


def _run_step(script: str, tmp_path: Path, *, comments: list, pr: dict, env: dict) -> tuple[int, Path]:
    if shutil.which("jq") is None:
        pytest.skip("workflow shell regression requires jq")
    fake = tmp_path / "fake"
    fake.mkdir(exist_ok=True)
    for name, body in (("gh", _FAKE_GH), ("git", _FAKE_GIT)):
        (fake / name).write_text(body)
        (fake / name).chmod(0o755)
    (fake / "comments.json").write_text(json.dumps([comments]))
    (fake / "pr.json").write_text(json.dumps(pr))
    output = tmp_path / "github_output"
    output.write_text("")
    full_env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "FAKE": str(fake), "RUNNER_TEMP": str(tmp_path),
                "GITHUB_REPOSITORY": "owner/repo", "PR_NUMBER": "7", "GITHUB_OUTPUT": str(output),
                "REVIEW_MARKER": MARKER, "COMPANION_REPO": "owner/companion", **env}
    proc = subprocess.run(["bash", "-c", script], env=full_env, text=True, capture_output=True)
    return proc.returncode, fake


def _publish(review_job: dict, tmp_path: Path, comments: list, **outcomes: str) -> tuple[int, Path]:
    env = {"GITHUB_EVENT_NAME": "issue_comment", "REVIEWED_SHA": HEAD, "FALLBACK_MODEL": "fallback-model-x",
           "PRIMARY_OUTCOME": "", "PRIMARY_SUMMARY": "", "PRIMARY_ERROR": "",
           "FALLBACK_OUTCOME": "", "FALLBACK_SUMMARY": "", "FALLBACK_ERROR": "", **outcomes}
    pr = {"state": "open", "draft": False, "head": {"sha": HEAD}}
    return _run_step(_step(review_job, name=PUBLISHER)["run"], tmp_path, comments=comments, pr=pr, env=env)


def _body(path: Path) -> str:
    return json.loads(path.read_text())["body"]


def test_publisher_posts_the_review_and_records_its_head(review_job: dict, tmp_path: Path) -> None:
    rc, fake = _publish(review_job, tmp_path, [], PRIMARY_OUTCOME="success",
                        PRIMARY_SUMMARY=f"{MARKER}\n\nNo cross-file regressions found.")
    assert rc == 0
    body = _body(fake / "posted.json")
    assert body.startswith(MARKER) and f"<!-- gemini-reviewed-sha: {HEAD} -->" in body
    assert body.endswith("No cross-file regressions found.") and "fallback" not in body


def test_publisher_uses_a_successful_fallback_and_says_so(review_job: dict, tmp_path: Path) -> None:
    old = _bot(11, f"{MARKER}\n<!-- gemini-reviewed-sha: {'b' * 40} -->\n\nolder review")
    rc, fake = _publish(review_job, tmp_path, [old], PRIMARY_OUTCOME="failure",
                        PRIMARY_ERROR='{"code":429,"message":"quota"}', FALLBACK_OUTCOME="success",
                        FALLBACK_SUMMARY="Fallback review text.")
    assert rc == 0
    body = _body(fake / "patched_11.json")
    assert "fallback model `fallback-model-x`" in body and body.endswith("Fallback review text.")
    assert f"<!-- gemini-reviewed-sha: {HEAD} -->" in body


def test_publisher_reports_a_failure_on_the_pr_and_fails_the_job(review_job: dict, tmp_path: Path) -> None:
    """503/429/timeout failures used to skip the publisher, leaving nothing on the PR thread."""
    old = _bot(11, f"{MARKER}\n<!-- gemini-reviewed-sha: {'b' * 40} -->\n\nreview of an older head")
    reason = '{"code":503,"message":"UNAVAILABLE: high demand ```injected``` ' + "x" * 3000 + '"}'
    rc, fake = _publish(review_job, tmp_path, [old], PRIMARY_OUTCOME="failure", PRIMARY_ERROR=reason,
                        FALLBACK_OUTCOME="failure", FALLBACK_ERROR=reason)
    assert rc == 1
    body = _body(fake / "patched_11.json")
    assert body.startswith(MARKER) and f"<!-- gemini-review-failed: {HEAD} -->" in body
    assert "gemini-reviewed-sha" not in body, "a failure must not mark the head as reviewed"
    assert "did not complete" in body and "UNAVAILABLE: high demand" in body and "@gemini-cli" in body
    assert body.count("```") == 4, "error text cannot close either code block"
    assert len(body) < 2200


# What the first live run (patientwords-engine run 41159982695, 2026-10-31) returned: CLI noise, the error line and
# a stack, from a primary quota failure and a fallback whose model ID Google had retired.
_LIVE_NOISE = ("Warning: 256-color support not detected.\nYOLO mode is enabled. All tool calls will be automatically "
               "approved.\n[STARTUP] Phase 'cleanup_ops' was started but never ended. Skipping metrics.\n")
_STACK = "\n    at classifyGoogleError (file:///bundle/chunk.js:1:2)\n    at retryWithBackoff (file:///bundle/chunk.js:3:4)"


def test_diagnostic_reports_both_errors_without_cli_noise(review_job: dict, tmp_path: Path) -> None:
    primary = _LIVE_NOISE + "TerminalQuotaError: You have exhausted your daily quota on this model." + _STACK
    fallback = _LIVE_NOISE + ("ModelNotFoundError: This model models/old-model is no longer available to new "
                              "users.") + _STACK
    rc, fake = _publish(review_job, tmp_path, [], PRIMARY_OUTCOME="failure", PRIMARY_ERROR=primary,
                        FALLBACK_OUTCOME="failure", FALLBACK_ERROR=fallback)
    assert rc == 1
    body = _body(fake / "posted.json")
    assert "exhausted your daily quota" in body and "no longer available to new users" in body
    assert "Fallback model `fallback-model-x`" in body
    assert all(noise not in body for noise in ("256-color", "YOLO mode", "[STARTUP]", "classifyGoogleError"))


def test_diagnostic_says_when_no_fallback_model_is_configured(review_job: dict, tmp_path: Path) -> None:
    rc, fake = _publish(review_job, tmp_path, [], PRIMARY_OUTCOME="failure", PRIMARY_ERROR="429 quota",
                        FALLBACK_MODEL="", FALLBACK_OUTCOME="")
    assert rc == 1
    assert "GEMINI_FALLBACK_MODEL is not set" in _body(fake / "posted.json")


def test_publisher_keeps_a_completed_review_of_the_same_head(review_job: dict, tmp_path: Path) -> None:
    done = _bot(11, f"{MARKER}\n<!-- gemini-reviewed-sha: {HEAD} -->\n\ncompleted review")
    rc, fake = _publish(review_job, tmp_path, [done], PRIMARY_OUTCOME="failure", PRIMARY_ERROR="429 quota")
    assert rc == 1
    assert not list(fake.glob("patched_*.json")) and not (fake / "posted.json").exists()


def test_publisher_never_overwrites_a_human_comment(review_job: dict, tmp_path: Path) -> None:
    human = _bot(5, f"{MARKER} quoted by a person", user="owner", kind="User")
    rc, fake = _publish(review_job, tmp_path, [human], PRIMARY_OUTCOME="success", PRIMARY_SUMMARY="Review.")
    assert rc == 0 and (fake / "posted.json").exists() and not list(fake.glob("patched_*.json"))


def test_publisher_treats_an_empty_review_as_a_failure(review_job: dict, tmp_path: Path) -> None:
    rc, fake = _publish(review_job, tmp_path, [], PRIMARY_OUTCOME="success", PRIMARY_SUMMARY=f"  {MARKER}  ")
    assert rc == 1
    assert "did not complete" in _body(fake / "posted.json")


def _resolve(review_job: dict, tmp_path: Path, body: str, comments: list, draft: bool = False) -> tuple[int, str]:
    pr = {"state": "open", "draft": draft, "head": {"sha": HEAD, "ref": "feature", "repo": {"full_name": "owner/repo"}},
          "base": {"sha": "b" * 40}, "user": {"type": "User"}}
    env = {"GITHUB_EVENT_NAME": "issue_comment", "EVENT_HEAD_SHA": "", "COMMENT_BODY": body}
    rc, _ = _run_step(_step(review_job, step_id="pr")["run"], tmp_path, comments=comments, pr=pr, env=env)
    return rc, (tmp_path / "github_output").read_text()


def test_codex_review_comment_reviews_once_per_head(review_job: dict, tmp_path: Path) -> None:
    """`@codex review` after every push starts Gemini too, but not again for a head it already reviewed; a failed
    attempt does not count as a review, and `@gemini-cli` always reviews. Drafts are reviewed on request."""
    rc, out = _resolve(review_job, tmp_path, "@codex review", [], draft=True)
    assert rc == 0 and "eligible=true" in out and f"head_sha={HEAD}" in out
    reviewed = _bot(11, f"{MARKER}\n<!-- gemini-reviewed-sha: {HEAD} -->\n\nreview")
    rc, out = _resolve(review_job, tmp_path, "@codex review please", [reviewed])
    assert rc == 0 and "eligible=true" not in out
    failed = _bot(11, f"{MARKER}\n<!-- gemini-review-failed: {HEAD} -->\n\nfailed")
    rc, out = _resolve(review_job, tmp_path, "@codex review", [failed])
    assert rc == 0 and "eligible=true" in out
    rc, out = _resolve(review_job, tmp_path, "@gemini-cli", [reviewed])
    assert rc == 0 and "eligible=true" in out


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
