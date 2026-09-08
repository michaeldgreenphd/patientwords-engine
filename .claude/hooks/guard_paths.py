#!/usr/bin/env python3
"""PreToolUse guard for Edit / Write / MultiEdit (AGENTS.md: Ops tooling,
Single-writer). Reads the tool call as JSON on stdin; exit 2 refuses and the
message on stderr reaches the session."""
import json
import os
import sys
from typing import Optional

ENGINE_MARKER = os.path.join("scripts", "fire_trigger.py")
USER_SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def engine_root_for(path: str) -> Optional[str]:
    """The engine checkout that owns `path`: its nearest ancestor holding
    scripts/fire_trigger.py. Self-locating, so the guard works whether the
    session's project directory is the engine repo or a parent folder holding
    several repos (the cloud containers), where a match relative to
    CLAUDE_PROJECT_DIR would miss every guarded file."""
    cur = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(cur, ENGINE_MARKER)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except Exception:  # malformed input: do not block, do not guess
        return 0
    path = (call.get("tool_input") or {}).get("file_path") or ""
    if not path:
        return 0
    root = (engine_root_for(path) or os.environ.get("PW_ENGINE_ROOT")
            or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    rel = os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")

    def refuse(msg: str) -> int:
        sys.stderr.write("refused: " + msg + "\n")
        return 2

    if os.path.abspath(path) == USER_SETTINGS:
        return refuse("the user-level Claude settings are written by the environment's setup script "
                      "(.claude/hooks/install_user_settings.py), never from a session.")
    if rel.startswith(".github/trigger/"):
        return refuse(".github/trigger/ is written only by scripts/fire_trigger.py "
                      "(AGENTS.md, Ops tooling). Use `fire` or `park`.")
    if rel == "ops/dashboard.json" and os.environ.get("PW_ROUTINE") != "1":
        return refuse("ops/dashboard.json is committed only by the daily Routine session "
                      "(AGENTS.md, Single-writer). This session's environment is not the Routine's.")
    if rel.startswith((".claude/hooks/", ".githooks/")) or rel in (".claude/settings.json",
                                                                    ".claude/settings.local.json"):
        return refuse("guard hooks and settings are edited by the owner by hand, never from a session "
                      "(CLAUDE.md, Claude Code specifics).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
