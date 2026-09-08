#!/usr/bin/env bash
# Environment setup script for the study's claude.ai cloud environments
# ("Patient Words Front and Back" and the Routine's own environment). Paste
# this file's contents into the environment's setup script; keep the two
# identical, this copy is the reviewed one.
#
# Runs once per fresh container, before the session starts and after the
# platform has cloned the repositories into /home/user. Every step is guarded
# so an absent or incomplete checkout logs a line and moves on: the session's
# own bootstrap (docs/fresh_session_bootstrap.md) is where repair happens, and
# a setup script that fails outright may keep the session from starting at all.
# Nothing here needs a secret, and nothing here fires, publishes, or commits.
set -u
export PIP_ROOT_USER_ACTION=ignore
ENGINE=/home/user/patientwords-engine
SITE=/home/user/patientwords
REPORT=/home/user/.pw_setup_report.txt
log() { echo "[pw-setup] $*"; }

{
# 1. Python toolchain for the engine (AGENTS.md, Commands): the package with its
#    declared dependencies (requests, matplotlib, networkx), the llm extra, the
#    dev tools, and pyyaml, which tests/ imports but pyproject does not declare.
#    Without this a fresh container shows 12 ModuleNotFoundError failures that
#    are the environment's, not the code's (AGENTS.md, Tests).
if [ -f "$ENGINE/pyproject.toml" ]; then
  if python3 -m pip install -q -e "$ENGINE[llm]" pytest ruff pillow pyyaml; then
    log "engine installed: $(python3 -m pip show medlang-circuits 2>/dev/null | awk '/^Version/{print $2}' || echo '?')"
  else
    log "pip install FAILED: the suite will show ModuleNotFoundError until it is rerun"
  fi
else
  log "no engine checkout at $ENGINE: nothing installed"
fi

# 2. Guard hooks, user-level. Claude Code loads .claude/settings.json only from
#    the session's project directory, which in these containers is /home/user,
#    so the engine's project hooks never load here. The installer writes the
#    same three hooks into ~/.claude/settings.json (.claude/hooks/README.md).
f="$ENGINE/.claude/hooks/install_user_settings.py"
if [ -f "$f" ]; then
  python3 "$f" || log "guard installer FAILED (exit $?)"
else
  log "guard installer not present: main predates engine PR #13, or the checkout is incomplete"
fi

# 3. The git layer, set directly as well, so it holds even before a session's
#    SessionStart hook runs (fire_trigger.py also sets it on every call).
if [ -d "$ENGINE/.githooks" ] && git -C "$ENGINE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ENGINE" config core.hooksPath .githooks && log "engine core.hooksPath=.githooks"
fi

# 4. Checkout diagnostics, one line per repo, for the session's bootstrap
#    (docs/fresh_session_bootstrap.md: staged deletions = Variant A, a stale
#    HEAD = Variant B, shallow=true = Variant C - never deepen that one).
for r in "$ENGINE" "$SITE"; do
  name=$(basename "$r")
  if git -C "$r" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    branch=$(git -C "$r" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
    head=$(git -C "$r" log -1 --format='%h %cd' --date=short 2>/dev/null || echo '?')
    shallow=$(git -C "$r" rev-parse --is-shallow-repository 2>/dev/null || echo '?')
    if [ -n "$(git -C "$r" config --get remote.origin.promisor 2>/dev/null)" ]; then blobless=yes; else blobless=no; fi
    deleted=$(git -C "$r" diff --cached --name-only --diff-filter=D 2>/dev/null | wc -l | tr -d ' ')
    log "$name: branch=$branch head=$head shallow=$shallow blobless=$blobless staged_deletions=$deleted"
  else
    log "$name: not a git checkout"
  fi
done
log "done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} 2>&1 | tee "$REPORT"
exit 0
