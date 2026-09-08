#!/usr/bin/env python3
"""Install the guard hooks into the user-level Claude Code settings.

Claude Code loads `.claude/settings.json` only from the session's project
directory. In the cloud containers that hold both study repos, that directory
is the parent folder above the two checkouts, so the engine's project settings
never load and none of the guards run (found 2026-09-08: the Routine committed
`ops/dashboard.json` with no hook in the way). User-level settings load in
every session regardless of the project directory, and the environment's
setup script is the owner-controlled place that can write them before any
session starts:

    python3 /home/user/patientwords-engine/.claude/hooks/install_user_settings.py

Idempotent. Replaces the `hooks` key of ~/.claude/settings.json and keeps
every other key; drops an `env.PW_ROUTINE` entry if one has been planted, since
the Routine's identity comes from its own environment configuration, never from
a settings file a session could write. Each hook command names the guard script
by absolute path and passes PW_ENGINE_ROOT so the guards check paths against
the engine checkout, not the parent folder. A missing guard script (an
incomplete checkout, see docs/fresh_session_bootstrap.md) makes the hook exit 1:
the tool call proceeds, and the message says the guard is not active, so a
guard that did not run never reads like one that passed.
"""
import argparse
import json
import sys
from pathlib import Path

GUARD_SCRIPTS = (("Edit|Write|MultiEdit", "guard_paths.py"), ("Bash", "guard_git.py"))


def hook_command(root: Path, script: str) -> str:
    script_path = root / ".claude" / "hooks" / script
    return (f'f="{script_path}"; if [ -f "$f" ]; then PW_ENGINE_ROOT="{root}" python3 "$f"; '
            f'else echo "{script} missing: the engine checkout at {root} is incomplete '
            f'(docs/fresh_session_bootstrap.md); this guard is NOT active" >&2; exit 1; fi')


def build_hooks(root: Path) -> dict:
    return {
        "SessionStart": [{"hooks": [{"type": "command",
                                     "command": f'git -C "{root}" config core.hooksPath .githooks'}]}],
        "PreToolUse": [{"matcher": matcher,
                        "hooks": [{"type": "command", "command": hook_command(root, script)}]}
                       for matcher, script in GUARD_SCRIPTS],
    }


def install(root: Path, settings_path: Path) -> dict:
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{settings_path} is not valid JSON ({exc}); not touching it") from exc
        if not isinstance(settings, dict):
            raise SystemExit(f"{settings_path} is not a JSON object; not touching it")
    settings["hooks"] = build_hooks(root)
    env = settings.get("env")
    if isinstance(env, dict) and env.pop("PW_ROUTINE", None) is not None:
        print("removed env.PW_ROUTINE from user settings: the Routine's identity is set on its "
              "environment, not in a settings file", file=sys.stderr)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine-root", default=str(Path(__file__).resolve().parents[2]),
                        help="engine checkout the hooks guard (default: the one this file is in)")
    parser.add_argument("--settings-path", default=str(Path.home() / ".claude" / "settings.json"),
                        help="user-level settings file to write (default: ~/.claude/settings.json)")
    args = parser.parse_args(argv)
    root = Path(args.engine_root).resolve()
    if not (root / "scripts" / "fire_trigger.py").is_file():
        print(f"refused: {root} is not an engine checkout (no scripts/fire_trigger.py)", file=sys.stderr)
        return 2
    install(root, Path(args.settings_path))
    print(f"guard hooks installed in {args.settings_path} for {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
