"""The git-level guards under .githooks/, run by real git in a throwaway repo:
pre-commit (dashboard and trigger files) and pre-push (deletions and trigger
files). This is the layer that runs for any caller once core.hooksPath is set,
which scripts/fire_trigger.py does on every invocation."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *argv, env=None, check=False):
    full = {k: v for k, v in os.environ.items() if k not in ("PW_ROUTINE", "PW_FIRE_TOKEN")}
    if env:
        full.update(env)
    return subprocess.run(["git", "-C", str(repo), *argv], capture_output=True, text=True, env=full, check=check)


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "work"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main", check=True)
    git(repo, "config", "user.email", "t@example.com", check=True)
    git(repo, "config", "user.name", "t", check=True)
    git(repo, "remote", "add", "origin", str(remote), check=True)
    shutil.copytree(ROOT / ".githooks", repo / ".githooks")
    git(repo, "config", "core.hooksPath", ".githooks", check=True)
    (repo / "ops").mkdir()
    (repo / ".github" / "trigger").mkdir(parents=True)
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "README.md", check=True)
    git(repo, "commit", "-q", "-m", "init", check=True)
    git(repo, "push", "-q", "-u", "origin", "main", check=True)   # creates the remote ref: not a trigger push
    return repo


def _stage(repo, rel, text="{}\n"):
    path = repo / rel
    path.write_text(text)
    git(repo, "add", rel, check=True)


def test_pre_commit_refuses_the_dashboard_outside_the_routine(repo):
    _stage(repo, "ops/dashboard.json")
    r = git(repo, "commit", "-q", "-m", "dash")
    assert r.returncode != 0 and "Single-writer" in r.stderr
    r = git(repo, "commit", "-q", "-m", "dash", env={"PW_ROUTINE": "1"})
    assert r.returncode == 0, r.stderr


def test_pre_commit_and_pre_push_admit_a_trigger_change_only_under_the_token(repo):
    _stage(repo, ".github/trigger/circuit-trace.json")
    r = git(repo, "commit", "-q", "-m", "fire")
    assert r.returncode != 0 and "fire_trigger.py" in r.stderr
    tok = "deadbeef" * 4
    (repo / ".git" / "pw_fire_token").write_text(tok)
    assert git(repo, "commit", "-q", "-m", "fire", env={"PW_FIRE_TOKEN": "wrong"}).returncode != 0
    assert git(repo, "commit", "-q", "-m", "fire", env={"PW_FIRE_TOKEN": tok}).returncode == 0
    (repo / ".git" / "pw_fire_token").unlink()
    r = git(repo, "push", "-q", "origin", "main")
    assert r.returncode != 0 and "fires CI" in r.stderr
    (repo / ".git" / "pw_fire_token").write_text(tok)
    assert git(repo, "push", "-q", "origin", "main", env={"PW_FIRE_TOKEN": tok}).returncode == 0


def test_pre_push_refuses_a_ref_deletion(repo):
    git(repo, "checkout", "-q", "-b", "scratch", check=True)
    git(repo, "push", "-q", "-u", "origin", "scratch", check=True)
    r = git(repo, "push", "-q", "origin", "--delete", "scratch")
    assert r.returncode != 0 and "deletion" in r.stderr
    assert "scratch" in git(repo, "ls-remote", "--heads", "origin").stdout


def test_fire_trigger_publish_passes_both_hooks_in_a_real_repo(repo):
    import importlib
    ft = importlib.import_module("scripts.fire_trigger") if (ROOT / "scripts" / "__init__.py").exists() else None
    if ft is None:
        spec = importlib.util.spec_from_file_location("fire_trigger", ROOT / "scripts" / "fire_trigger.py")
        ft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ft)
    (repo / ".github" / "trigger" / "circuit-trace.json").write_text('{"a": 1}\n')
    (repo / "ops" / "trigger_journal.jsonl").write_text("")
    ok = ft.git_publish(repo, [Path(".github/trigger/circuit-trace.json"), Path("ops/trigger_journal.jsonl")],
                        "Fire circuit-trace: test", backoff=())
    assert ok is True
    assert not (repo / ".git" / "pw_fire_token").exists()
    assert ".github/trigger/circuit-trace.json" in git(repo, "show", "--stat", "--format=", "origin/main").stdout
