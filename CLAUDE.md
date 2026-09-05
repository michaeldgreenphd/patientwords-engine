@./AGENTS.md

Read `AGENTS.md` first — it is the source of truth; nothing is repeated here so
the files cannot drift. The line above imports it into every Claude Code session.

## Claude Code specifics

- After opening a pull request, subscribe to its activity
  (`subscribe_pr_activity`) so Codex's review wakes the session, and schedule a
  fallback check-in about an hour out (`send_later`) until the PR is merged or
  closed; re-arm it silently if nothing changed.
- The procedures behind the rules in `AGENTS.md` are skills under
  `.claude/skills/` (`pr-review-response`, `fire-trigger-safe`,
  `harvest-resolve`, `holdout-seal-check`, `publish-site-data`,
  `daily-ops-cycle`). Invoke the matching one rather than improvising its steps.
