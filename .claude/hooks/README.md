# Guard hooks

Two PreToolUse hooks and one SessionStart hook, declared in `.claude/settings.json`.
They enforce the rules in `AGENTS.md` that were broken, or nearly broken, by hand
in September 2026. A refusal prints the rule it is enforcing.

| Hook | Refuses |
|---|---|
| `guard_paths.py` (Edit / Write / MultiEdit) | any edit under `.github/trigger/`; `ops/dashboard.json` unless the session's environment carries `PW_ROUTINE=1`; edits to `.claude/settings*.json`, `.claude/hooks/`, `.githooks/` |
| `guard_git.py` (Bash) | `git push` that deletes a ref, force-pushes, or carries a `.github/trigger/` change; `git add`/`commit` that would commit `ops/dashboard.json` outside the Routine environment; any Bash command that names `--no-verify`, `core.hooksPath`, `PW_FIRE_TOKEN`, or `PW_ROUTINE` (the bypass tokens); shell writes into the guarded paths |
| SessionStart | installs `.githooks/` as `core.hooksPath` so `pre-push` runs inside git for every caller |

**Why `PW_ROUTINE` is read from the hook's own environment and not from the
command.** Hook processes are spawned by the Claude Code CLI with the CLI's
environment. An `export PW_ROUTINE=1` or an inline `PW_ROUTINE=1 git commit`
inside a Bash tool call changes the environment of that shell command, not of
the hook process, so a prompt cannot satisfy the check. The variable is set only
in the Routine's own environment configuration (a dedicated cloud environment
for the Routine, or `PW_ROUTINE=1 claude` launched by a human). Editing
`.claude/settings.json` to add an `env` entry is the one in-session route to it,
which is why the path hook refuses that edit.

**What a hook cannot catch.** Both hooks read the *text* of a Bash command. A
command that wraps git inside Python, or builds a path from pieces, evades them.
Three layers sit behind: `.githooks/pre-push` runs inside git for any caller and
refuses deletions and unsanctioned trigger changes; GitHub rulesets refuse
deletions and force pushes server-side; and each paid lane's own workflow runs
`fire_trigger.py budget-gate` before spending. The hooks are the guard against
mistakes and against an ordinary prompt, not against a determined adversary.

Verify on a new machine with a one-line probe before trusting the environment
claim: add `echo "hook sees PW_ROUTINE=${PW_ROUTINE:-unset}" >&2` to a temporary
Bash hook, run `PW_ROUTINE=1 true` through the Bash tool, and confirm the hook
reports `unset`.
