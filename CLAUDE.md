@./AGENTS.md

Read `AGENTS.md` first — it is the source of truth; nothing is repeated here so
the files cannot drift. The line above imports it into every Claude Code session.

## Claude Code specifics

- After opening a pull request, subscribe to its activity
  (`subscribe_pr_activity`) so Codex's review wakes the session, and schedule a
  fallback check-in about an hour out (`send_later`) until the PR is merged or
  closed; re-arm it silently if nothing changed. (The daily-cycle session is the
  exception: it opens no PRs and schedules nothing.)
- The procedures behind the rules in `AGENTS.md` are skills under
  `.claude/skills/`. Invoke the matching one rather than improvising its steps.
- `.claude/settings.json` installs guard hooks (`.claude/hooks/README.md`). A
  refusal is the rule working: do not route around it, and never edit
  `.claude/settings.json`, `.claude/hooks/`, or `.githooks/` from a session —
  the owner edits those by hand.

## Shared conventions (identical across my repos; edit in all three)

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
