# Guard hooks

Two PreToolUse hooks and one SessionStart hook, declared in `.claude/settings.json`.
They enforce the rules in `AGENTS.md` that were broken, or nearly broken, by hand
in September 2026. A refusal prints the rule it is enforcing.

| Hook | Refuses |
|---|---|
| `guard_paths.py` (Edit / Write / MultiEdit) | any edit under `.github/trigger/`; `ops/dashboard.json` unless the session's environment carries `PW_ROUTINE=1`; edits to `.claude/settings*.json`, `.claude/hooks/`, `.githooks/` |
| `guard_git.py` (Bash) | `git push` that deletes a ref, force-pushes, or carries a `.github/trigger/` change; `git add`/`commit` that would commit `ops/dashboard.json` outside the Routine environment; any Bash command that names `--no-verify`, `core.hooksPath`, `PW_FIRE_TOKEN`, or `PW_ROUTINE` (the bypass tokens); shell writes into the guarded paths |
| SessionStart | installs `.githooks/` as `core.hooksPath` so `pre-commit` and `pre-push` run inside git for every caller (`scripts/fire_trigger.py` sets it too, on every invocation) |
| `.githooks/pre-commit` (git, any caller) | a commit that stages `ops/dashboard.json` without `PW_ROUTINE=1` in git's environment; a commit that stages a `.github/trigger/` file without `fire_trigger.py`'s one-shot token |
| `.githooks/pre-push` (git, any caller) | ref deletions; a push that changes `.github/trigger/` without the token |

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

## Containers that hold several repos: install the hooks user-level

Claude Code loads `.claude/settings.json` only from the session's project
directory. The cloud containers that hold both study repos start with the
parent folder above the two checkouts as that directory, so the engine's
project settings never load and none of the hooks above run. Found 2026-09-08:
the Routine's cycle committed `ops/dashboard.json` with no hook in the way, and
a probe in an interactive session in the same layout ran a command naming two
bypass tokens without objection.

User-level settings (`~/.claude/settings.json`) load in every session whatever
the project directory. The environment's setup script, which the owner controls
and which runs before any session starts, is the place to write them.
`ops/environment_setup.sh` is that script — paste its contents into the
environment's setup script field and keep the two identical. Besides the
installer it does the dev install from `AGENTS.md` (*Commands*), sets the git
hooks path directly, and writes a one-line checkout diagnosis per repo to
`/home/user/.pw_setup_report.txt` for the session's bootstrap. The installer
alone is:

```bash
python3 /home/user/patientwords-engine/.claude/hooks/install_user_settings.py
```

It replaces the `hooks` key of `~/.claude/settings.json`, keeps every other
key, and writes each hook with the guard script's absolute path plus
`PW_ENGINE_ROOT`, which the guards use to check paths against the engine
checkout rather than the parent folder (both guards also locate the engine on
their own: `guard_paths.py` from the edited file's ancestors, `guard_git.py`
from a `cd` or `git -C` in the command or from the project directory's
`patientwords-engine` child). A planted `env.PW_ROUTINE` in that file is
removed on install: the Routine's identity is set on its own environment.

Two behaviours to know:

- **A missing guard script does not pass silently.** If the checkout is
  incomplete (`docs/fresh_session_bootstrap.md`), the hook prints that the guard
  is NOT active and exits 1: the tool call proceeds, so the repair can be run,
  and the message is visible.
- **The Routine needs `PW_ROUTINE=1` in its own environment.** With the hooks
  loading and the git layer installed, a dashboard commit without it is
  refused, by `guard_git.py` and again by `pre-commit`. Set the variable on the
  Routine's environment (a dedicated one: setting it on an environment that
  interactive sessions also use would make every session the Routine), never on
  the shared environment and never in a settings file.

**Verify after changing the setup script.** Start a session in the
environment and run `git -C /home/user/patientwords-engine config --get
core.hooksPath` through the Bash tool: `.githooks` means the SessionStart hook
ran, so the user-level settings loaded. Then run a Bash command that names
`--no-verify`; it must be refused.

**What the git layer cannot see.** `pre-commit` runs on `git commit`; `git
merge`, `rebase` and `cherry-pick` create commits without it, which is one more
reason the merge rule in `AGENTS.md` (keep the target's trigger files) stays a
rule and not a hook. `pre-push` still checks every push.
