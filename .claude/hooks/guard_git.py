#!/usr/bin/env python3
"""PreToolUse guard for Bash (AGENTS.md: Ops tooling, Single-writer, Pull request
workflow item 1's exception). Reads the tool call as JSON on stdin; exit 2
refuses with the message on stderr. It inspects the command's text, so it is a
guard against mistakes and ordinary prompts — .githooks/pre-push and the GitHub
rulesets are the layers behind it (see README.md)."""
import json
import os
import re
import subprocess
import sys

BYPASS_TOKENS = ("--no-verify", "core.hooksPath", "hooksPath", "PW_FIRE_TOKEN", "PW_ROUTINE")
GUARDED_WRITE_PATHS = (".github/trigger/", ".claude/hooks/", ".githooks/", ".claude/settings")
WRITE_HINTS = (">", ">>", "tee ", "sed -i", "cp ", "mv ", "rm ", "truncate", "python -c", "python3 -c",
               "perl -", "install ")
ENGINE_MARKER = os.path.join("scripts", "fire_trigger.py")
ENGINE_DIRNAME = "patientwords-engine"


def is_engine(path: str) -> bool:
    return bool(path) and os.path.isfile(os.path.join(path, ENGINE_MARKER))


def engine_root(cmd: str) -> str:
    """The engine checkout the command acts on. In order: a `git -C <dir>` or
    `cd <dir>` in the command whose target is an engine checkout; PW_ENGINE_ROOT
    (set by the user-level install in containers whose project directory is a
    parent folder holding several repos); CLAUDE_PROJECT_DIR or the cwd, or their
    `patientwords-engine` child. Falls back to the project directory, where the
    git checks return nothing and only the text checks apply."""
    for m in re.finditer(r"(?:\bgit\s+-C\s+|\bcd\s+)([\"']?)([^\s;&|\"']+)\1", cmd):
        cand = os.path.expanduser(m.group(2))
        if is_engine(cand):
            return os.path.abspath(cand)
    for var in ("PW_ENGINE_ROOT", "CLAUDE_PROJECT_DIR"):
        val = os.environ.get(var)
        if val and is_engine(val):
            return os.path.abspath(val)
    for base in (os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()):
        if base:
            for cand in (base, os.path.join(base, ENGINE_DIRNAME)):
                if is_engine(cand):
                    return os.path.abspath(cand)
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def refuse(msg: str) -> int:
    sys.stderr.write("refused: " + msg + "\n")
    return 2


def git_out(root: str, *argv: str) -> str:
    try:
        return subprocess.run(["git", "-C", root, *argv], capture_output=True, text=True,
                              timeout=15).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (call.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    root = engine_root(cmd)
    is_fire_trigger = re.search(r"\bpython3?\s+(\S*/)?scripts/fire_trigger\.py\b", cmd) is not None

    for tok in BYPASS_TOKENS:
        if tok in cmd:
            return refuse(f"`{tok}` is a guard-bypass token; nothing a session runs may name it.")

    if re.search(r"\bgit\b[^|;&]*\bpush\b", cmd):
        if re.search(r"--delete\b|\s:refs/heads/|\s:[A-Za-z0-9_./-]+(\s|$)", cmd):
            return refuse("branch deletion is the owner's, in the GitHub UI, never from a session.")
        if re.search(r"--force(-with-lease)?\b|(^|\s)-f\b", cmd):
            return refuse("force pushes rewrite shared history (the 2026-09-04 force-push fired a lane).")
        upstream = git_out(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        base = upstream or "origin/main"
        changed = git_out(root, "diff", "--name-only", f"{base}...HEAD", "--", ".github/trigger/")
        if changed:
            return refuse("this push carries a trigger-file change (" + changed.replace("\n", ", ")
                          + "); only scripts/fire_trigger.py pushes a trigger change, and it pushes itself.")

    if os.environ.get("PW_ROUTINE") != "1":
        if re.search(r"\bgit\b[^|;&]*\b(add|commit)\b", cmd):
            names_dashboard = "ops/dashboard.json" in cmd
            sweeping = re.search(r"\badd\b[^|;&]*(\s-A\b|\s--all\b|\s\.(\s|$))", cmd) or \
                re.search(r"\bcommit\b[^|;&]*(\s-a\b|\s--all\b|\s-am\b)", cmd)
            dirty = "ops/dashboard.json" in git_out(root, "status", "--porcelain", "--", "ops/dashboard.json")
            if names_dashboard or (sweeping and dirty):
                return refuse("ops/dashboard.json is committed only by the daily Routine session "
                              "(AGENTS.md, Single-writer). Run `git checkout -- ops/dashboard.json` first.")

    if not is_fire_trigger and any(p in cmd for p in GUARDED_WRITE_PATHS) \
            and any(h in cmd for h in WRITE_HINTS):
        return refuse("shell writes into .github/trigger/, .claude/hooks/, .githooks/ or .claude/settings*"
                      " are not allowed from a session; fire_trigger.py owns the first, the owner the rest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
