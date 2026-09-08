"""The Claude Code guard hooks under .claude/hooks/ and the user-level installer.

Run as the CLI runs them: JSON on stdin, environment from the caller, exit 2 to
refuse. The layout under test is the cloud container's — a parent folder holding
several repos, with CLAUDE_PROJECT_DIR pointing at the parent — because that is
where the guards were found not to run on 2026-09-08."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(script, call, env):
    full = {k: v for k, v in os.environ.items() if k not in ("PW_ROUTINE", "PW_ENGINE_ROOT", "CLAUDE_PROJECT_DIR")}
    full.update(env)
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(call), capture_output=True,
                          text=True, env=full, timeout=30)


@pytest.fixture
def layout(tmp_path):
    """parent/patientwords-engine (marker present) beside parent/patientwords."""
    engine = tmp_path / "patientwords-engine"
    (engine / "scripts").mkdir(parents=True)
    (engine / "scripts" / "fire_trigger.py").write_text("# marker\n")
    (engine / "ops").mkdir()
    (engine / "ops" / "dashboard.json").write_text("{}\n")
    (engine / ".github" / "trigger").mkdir(parents=True)
    site = tmp_path / "patientwords"
    (site / "data").mkdir(parents=True)
    return tmp_path, engine, site


def test_guard_paths_finds_the_engine_from_the_file_itself(layout):
    parent, engine, site = layout
    gp = _load("guard_paths")
    assert gp.engine_root_for(str(engine / "ops" / "dashboard.json")) == str(engine)
    assert gp.engine_root_for(str(site / "data" / "x.json")) is None


def test_guard_paths_refuses_engine_files_when_project_dir_is_the_parent(layout):
    parent, engine, site = layout
    env = {"CLAUDE_PROJECT_DIR": str(parent)}
    dash = {"tool_name": "Edit", "tool_input": {"file_path": str(engine / "ops" / "dashboard.json")}}
    r = _run("guard_paths.py", dash, env)
    assert r.returncode == 2 and "Single-writer" in r.stderr
    trig = {"tool_name": "Write", "tool_input": {"file_path": str(engine / ".github" / "trigger" / "x.json")}}
    assert _run("guard_paths.py", trig, env).returncode == 2
    # The Routine's environment may edit the dashboard; the trigger file stays refused.
    assert _run("guard_paths.py", dash, {**env, "PW_ROUTINE": "1"}).returncode == 0
    assert _run("guard_paths.py", trig, {**env, "PW_ROUTINE": "1"}).returncode == 2
    # A sibling repo's file is not the engine's.
    other = {"tool_name": "Edit", "tool_input": {"file_path": str(site / "data" / "ops" / "dashboard.json")}}
    assert _run("guard_paths.py", other, env).returncode == 0


def test_guard_paths_refuses_the_user_level_settings_file(layout, tmp_path):
    parent, engine, site = layout
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    call = {"tool_name": "Write", "tool_input": {"file_path": str(home / ".claude" / "settings.json")}}
    r = _run("guard_paths.py", call, {"CLAUDE_PROJECT_DIR": str(parent), "HOME": str(home)})
    assert r.returncode == 2 and "setup script" in r.stderr


def test_guard_git_locates_the_engine_from_the_command_or_the_layout(layout, monkeypatch):
    parent, engine, site = layout
    gg = _load("guard_git")
    monkeypatch.delenv("PW_ENGINE_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(parent))
    assert gg.engine_root(f"cd {engine} && git push") == str(engine)
    assert gg.engine_root(f'git -C "{engine}" status') == str(engine)
    assert gg.engine_root("git status") == str(engine)            # parent's patientwords-engine child
    monkeypatch.setenv("PW_ENGINE_ROOT", str(engine))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(site))
    assert gg.engine_root("git status") == str(engine)            # the install's variable wins over a non-engine dir


def test_guard_git_text_rules_hold_in_the_parent_layout(layout):
    parent, engine, site = layout
    env = {"CLAUDE_PROJECT_DIR": str(parent)}
    for cmd in ("git push --no-verify", "git config core.hooksPath x", "git push origin --delete b",
                "git push -f origin main", "git add ops/dashboard.json", "echo x > .github/trigger/a.json"):
        r = _run("guard_git.py", {"tool_name": "Bash", "tool_input": {"command": cmd}}, env)
        assert r.returncode == 2, (cmd, r.stderr)
    ok = {"tool_name": "Bash", "tool_input": {"command": "python3 scripts/fire_trigger.py status"}}
    assert _run("guard_git.py", ok, env).returncode == 0


def test_installer_writes_absolute_hooks_and_keeps_other_keys(layout, tmp_path):
    parent, engine, site = layout
    inst = _load("install_user_settings")
    settings = tmp_path / "home" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]},
                                    "env": {"PW_ROUTINE": "1", "OTHER": "x"}}))
    out = inst.install(engine, settings)
    assert out["permissions"] == {"allow": ["Bash(ls *)"]}
    assert out["env"] == {"OTHER": "x"}                      # a planted PW_ROUTINE is dropped
    cmds = [h["command"] for group in out["hooks"]["PreToolUse"] for h in group["hooks"]]
    assert all(str(engine / ".claude" / "hooks") in c and f'PW_ENGINE_ROOT="{engine}"' in c for c in cmds)
    assert all("NOT active" in c for c in cmds)              # a missing script says so
    assert str(engine) in out["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    again = inst.install(engine, settings)
    assert again == json.loads(settings.read_text())         # idempotent


def test_installer_refuses_a_non_engine_root(tmp_path):
    inst = _load("install_user_settings")
    assert inst.main(["--engine-root", str(tmp_path), "--settings-path", str(tmp_path / "s.json")]) == 2
    assert not (tmp_path / "s.json").exists()
