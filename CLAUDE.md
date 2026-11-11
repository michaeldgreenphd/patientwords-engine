@./AGENTS.md

Read `AGENTS.md` first — it is the source of truth; nothing is repeated here so
the files cannot drift. The line above imports it into every Claude Code session.

## Claude Code specifics

- After opening a pull request, follow it through its events until it is merged
  or closed. How depends on whether the session has the cloud tools
  `subscribe_pr_activity` and `send_later`. (The daily-cycle session is the
  exception: it opens no PRs and schedules nothing.)
  - Cloud session (it has both): subscribe to the PR's activity
    (`subscribe_pr_activity`). Reviews, review comments, CI results and the
    merge or close then wake the session; keep the subscription until the PR
    is merged or closed, then unsubscribe. A fallback check-in (`send_later`,
    about an hour out) covers a Codex review or CI result that produced no
    wake. Schedule at most two per pull request: one after opening it, and
    one more only if the first found something to act on. A check-in that
    finds nothing changed ends the turn without a message and schedules
    nothing further. Never schedule a recurring check-in, and never start a
    turn only to report an unchanged status. If the subscription result says
    another session holds the PR's events, tell the owner instead of polling.
  - Local session (it has neither, so no PR event wakes it): before ending a
    turn, read all of the PR's feedback and its CI, then tell the owner when to
    check again. Run all three commands; none of them replaces another:
    `gh pr view <n> --json reviews,comments,headRefOid,mergeStateStatus`
    (review bodies, conversation comments, head commit, merge state);
    `gh api --paginate 'repos/{owner}/{repo}/pulls/<n>/comments'` (inline
    review comments, which `gh pr view` does not return; `gh` fills in
    `{owner}` and `{repo}` from the checkout); and `gh pr checks <n>` (CI).
- The procedures behind the rules in `AGENTS.md` are skills under
  `.claude/skills/`. Invoke the matching one rather than improvising its steps.
- `.claude/settings.json` installs guard hooks (`.claude/hooks/README.md`) that
  refuse some tool calls. A refusal is the rule working: do not route around
  it. From a session, never edit the guard files (`.claude/settings.json`,
  `.claude/hooks/`, `.githooks/`) or the user-level `~/.claude/settings.json`
  the environment writes; the owner edits those by hand.

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
