@./AGENTS.md

Read `AGENTS.md` first — it is the source of truth; nothing is repeated here so
the files cannot drift. The line above imports it into every Claude Code session.

## Claude Code specifics

- After opening a pull request, follow it until it is merged or closed. How
  depends on whether the session has the cloud tools `subscribe_pr_activity`
  and `send_later`. (The daily-cycle session is the exception: it opens no PRs
  and schedules nothing.)
  - Cloud session (it has both): subscribe to the PR's activity
    (`subscribe_pr_activity`) so Codex's review wakes the session, and schedule
    a fallback check-in about an hour out (`send_later`) until the PR is merged
    or closed; re-arm it silently if nothing changed.
  - Local session (it has neither, so no PR event wakes it): before ending a
    turn, check the PR with
    `~/.local/bin/gh pr view <n> --json reviews,comments,headRefOid,mergeStateStatus`
    (or `~/.local/bin/gh pr checks <n>`), and tell the owner when to check again.
- The procedures behind the rules in `AGENTS.md` are skills under
  `.claude/skills/`. Invoke the matching one rather than improvising its steps.
- `.claude/settings.json` installs guard hooks (`.claude/hooks/README.md`) that
  refuse some tool calls. A refusal is the rule working: do not route around
  it. From a session, never edit the guard files (`.claude/settings.json`,
  `.claude/hooks/`, `.githooks/`) or the user-level `~/.claude/settings.json`
  the environment writes; `AGENTS.md` says who changes them.

## Shared conventions (identical in patientwords-engine and patientwords; edit both)

Writing to the owner:

- Lead with the answer; qualifiers follow it. Say what was verified and what is
  inferred, and never fill a gap with a low-confidence guess presented as fact.
- Criticism is welcome when it carries its reason; praise only when the work is
  clearly good. Address the owner as a research partner, not a student.
- Say what you mean in literal words. Where a plain phrase exists, use it — "a
  parameter worth varying", not "a dial worth turning"; "this point still
  matters", not "this point earns its keep". Metaphor drags in connotations the
  writer did not choose.

Figures: the Tufte rule lives in `AGENTS.md` (*Figure style*), not here, because
reviewers grade figure code against it.
