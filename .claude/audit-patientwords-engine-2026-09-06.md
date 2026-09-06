# Claude Code configuration audit — patientwords-engine — 2026-09-06

Read-only audit. Nothing in this report has been applied. Token counts are
`bytes / 4` (the remote harness exposes no `/context`); treat them as ±15%.
Line numbers refer to `main` at `2185622c` + PR #10 (`02ecd531`), i.e. the
files as they load today.

---

## 1. Inventory

### 1.1 Files that load in every session (always-on)

| File | Loads how | Lines | Chars | ~Tokens |
|---|---|---|---|---|
| `./CLAUDE.md` | project instructions | 15 | 746 | 190 |
| `./AGENTS.md` | `@./AGENTS.md` import from `CLAUDE.md` (line 1) | 354 | 23,491 | 5,870 |
| six `.claude/skills/*/SKILL.md` **descriptions** (frontmatter only) | skill listing in the system prompt | — | — | 440 |
| `~/.claude/skills/session-start-hook` description (Anthropic-provided) | skill listing | — | — | 55 |
| account-synced skill descriptions (`~/.claude/skills/synced/…`: docx, pdf, xlsx, pptx, skill-creator, morning, import-memory, aact-baseline-extraction, tracked-docx-manuscript-editing) | skill listing; account-level, not this project's | — | — | ~1,100 |
| **Project-controlled always-on total** | | | | **≈ 6,500** |
| Always-on including account-level skill listings | | | | ≈ 7,600 |

Skill **bodies** load only when invoked (daily-ops-cycle 2,570 · fire-trigger-safe
1,950 · harvest-resolve 1,670 · holdout-seal-check 1,420 · pr-review-response
1,340 · publish-site-data 1,790 tokens). `.claude/settings.json` (37 lines) is
read by the harness, not placed in context.

### 1.2 Files that do not exist (nothing to load)

| Looked for | Result |
|---|---|
| `~/.claude/CLAUDE.md` | absent — no user-global instructions |
| `./.claude/CLAUDE.md`, `./CLAUDE.local.md` | absent |
| `.claude/rules/*.md`, `~/.claude/rules/*.md` | absent — no path-scoped rules anywhere |
| `.claude/commands/`, `.claude/agents/` | absent |
| Auto memory `~/.claude/projects/-home-user/memory/MEMORY.md` | absent — **no auto memory exists for this project** (the projects dir holds only session transcripts) |
| `.claude/settings.local.json`, `~/.claude/settings.json` | absent |
| `.mcp.json`, `~/.claude.json` `mcpServers` | absent / empty — MCP servers (`github`, `Claude_Code_Remote`, `Google_Drive`) are injected by the remote harness, not configured in the repo |
| hooks (`settings.json` `hooks`, `.githooks/`, `core.hooksPath`, `.pre-commit-config.yaml`) | **none anywhere** — every rule in this project is followed, never enforced |
| nested `CLAUDE.md` / `AGENTS.md` in subdirectories | none |

### 1.3 Files that exist but are NOT loaded, or load wrongly

| File | Finding | Severity |
|---|---|---|
| `~/.claude/skills/session-start-hook/SKILL.md` | frontmatter says `name: startup-hook-skill` while the directory is `session-start-hook`; the loader lists it by directory name, so it loads, but any `/startup-hook-skill` invocation fails. Anthropic-provided; not yours to fix. | cosmetic |
| `.github/copilot-instructions.md` | absent. Not a Claude file, but the other reviewer this config assumes (Copilot) reads this pointer, not `AGENTS.md` (VS Code's `AGENTS.md` support is version- and setting-gated). One line missing. | low |
| `.claude/settings.json` `permissions.allow` | lists `mcp__Claude_Code_Remote__*` and `mcp__github__*` — correct names for the remote harness; on a local VS Code install those servers do not exist, so the entries are inert there (harmless). | none |

No broken `@`-imports: `CLAUDE.md` line 1 resolves to `./AGENTS.md`, which exists.

### 1.4 `settings.json` as it stands

- **permissions.allow** (33 entries): `Artifact`, `AskUserQuestion`, `SendUserFile`; `Bash(python *)`, `Bash(python3 *)`, `Bash(ruff *)`, `Bash(git *)`, `Bash(pip install *)`, and ten read-only shell tools; six `Claude_Code_Remote` trigger tools; six read-only `github` tools. No `deny`, no `ask`.
- **hooks:** none. **env:** none. **MCP:** none.
- Consequence: `Bash(git *)` pre-approves `git push` of any kind, including a push that changes `.github/trigger/` (fires CI, possibly paid) and `git push --delete`. Nothing in the configuration stands between a session and the two actions `AGENTS.md` spends the most words forbidding. See §5.3.

---

## 2. Line-level audit of instruction files

Rows are per **rule** (a bullet, a bold-led paragraph, or a numbered item), not per
physical line; a 354-line file has ~45 rules. "Changes vs default" names what a
session would do differently without the line. Verdict vocabulary is the one you
specified.

### 2.1 `CLAUDE.md`

| # | line | rule | behavior it changes vs default | testable? | duplicate / contradiction | still true? | verdict |
|---|---|---|---|---|---|---|---|
| C1 | 1 | `@./AGENTS.md` | loads the 5.9k-token rule file; without it a Claude Code session has no project rules at all | yes ("what is the trigger-file rule?") | — | yes | **keep** |
| C2 | 3–4 | AGENTS.md is the source of truth; nothing repeated here | none behaviourally (states the design) | no; informational | consistent with AGENTS.md preamble (lines 3–8) | yes | keep |
| C3 | 8–11 | after opening a PR: `subscribe_pr_activity` + `send_later` ~1h until merged/closed; re-arm silently | without it: a session opens a PR and ends its turn; review events never wake it | yes ("open a PR for this change" → check for the subscribe call and a scheduled check-in) | duplicates pr-review-response §6 ("keep a check-in scheduled") — acceptable: this is the harness-tool half; the skill is procedure. Tension with daily-ops-cycle "Never … create Routines/reminders/crons" — resolved by scope (the cycle opens no PRs), but say so | yes | **rewrite** (one clause): "…re-arm it silently if nothing changed. (The daily-cycle session is the exception: it opens no PRs and schedules nothing.)" |
| C4 | 12–15 | the six skills are the procedures; invoke rather than improvise | without it: sessions re-derive fire/harvest/publish steps from AGENTS.md and get the settle window or single-writer rule wrong | weakly ("fire the drift sentinel" → does it invoke fire-trigger-safe?) | none | yes, but it hard-codes the skill list — drifts when a skill is added | rewrite: drop the parenthetical list ("…are skills under `.claude/skills/`; invoke the matching one…") |

### 2.2 `AGENTS.md`

| # | line | rule | behavior it changes vs default | testable? | duplicate / contradiction | still true? | verdict |
|---|---|---|---|---|---|---|---|
| A1 | 3–8 | preamble: AGENTS.md canonical, CLAUDE.md imports it and carries only harness mechanics; every rule goes here | without it: rules drift into CLAUDE.md, invisible to Codex | yes (ask to add a rule; check where it lands) | consistent with C2; pr-review-response "Never restate the rules here" agrees | yes | keep |
| A2 | 10–20 | what the project is; "nothing here produces medical advice that should be implemented" | frames outputs; without it a session might editorialize on clinical content | partly | — | yes | keep |
| A3 | 24–27 | medical vocabulary only in JSON data files, never Python | a session adding a term would otherwise hard-code it | yes ("add 'chest pain' as a synonym" → must land in `data/`) | daily-ops/publish skills echo "never correct misspellings" (A4), not this | yes | keep; **also convert to a test** (a `tests/` grep against the vocabulary files' terms in `scripts/*.py` would enforce it; no hook can) |
| A4 | 28–30 | intentional misspellings are stimuli; never correct | prevents "helpful" data edits | yes | duplicated verbatim in daily-ops-cycle §Never, harvest-resolve §Never, publish-site-data §Never | yes | keep here; **delete the three skill copies** |
| A5 | 30–32 | `data/simulated/` append-only with `.report.json` sidecar; never rewrite a landed batch | prevents regeneration/"cleanup" of archives | yes | duplicated in three skills' Never lists and in A21 | yes | keep here; delete skill copies |
| A6 | 33–43 | commands: install, pytest, ruff, entry points | without it a session guesses the test runner | yes | — | yes | keep |
| A7 | 45–56 | keys exist only as Actions secrets; nothing paid/networked runs locally; push-to-run CI | stops attempts to run generation/tracing in the sandbox | yes ("trace this pair now" → must fire CI, not run locally) | — | yes for remote sessions; **partly false locally**: your machine has a GPU and interp-engine, so "nothing runs locally" becomes a rule, not a fact, once you work in VS Code | rewrite: "…runs through push-to-run CI. A local machine that can run inference must still not commit locally produced measurements: every committed summary records `inference.environment`, and only CI-produced ones are measurements." |
| A8 | 57–67 | trigger-file → workflow table (8 lanes); "Eight lanes on this branch"; recount note | lets a session map a lane to a workflow | yes | table matches `.github/workflows/` (8 files, verified) | "on this branch" is stale phrasing since 2026-09-04 (one branch) | rewrite: "Eight lanes." |
| A9 | 69–72 | queue discipline: one running + one pending; third push evicts silently | prevents stacking fires | yes (dry-run a third fire → refusal) | fire-trigger-safe §4, harvest-resolve intro, daily-ops §4 restate it (3 copies) | yes | keep here; the skills may keep it — it is the procedure they exist for — but one copy (fire-trigger-safe) should own the exit-code table |
| A10 | 74–93 | merge/copy danger; new-ref corollary; `github.event.created` guard; consequence for `fire_trigger.py` on a new branch; resting-state rule; park | prevents the 2026-09-04 fan-out and double-spend on merges | yes ("create a branch and push" → 0 runs) | fire-trigger-safe §1.2 still says "creating a previously-absent trigger file fires the workflow… a first-ever fire on a branch" without the guard — **contradiction**, skill stale | yes | keep; **convert the "never let a merge change a trigger file" half to a hook** (§5.3) |
| A11 | 94–103 | cost discipline: four paid lanes, `PAID_TRIGGERS` is truth; per-pair costs; sidecar names | prevents unbudgeted fires; corrects the "two paid lanes" belief | yes | fire-trigger-safe §5 says "Paid triggers: scenario-generation and model-evaluation" and its description lists seven lanes without advice-eval — **contradiction**, skill stale | yes (verified against `PAID_TRIGGERS` on 2026-09-04) | keep; fix the skill |
| A12 | 104–114 | fire ONLY via `fire_trigger.py`; ledger single writer; dashboard committed only by Routine; other sessions revert it | prevents hand-edited triggers, second dashboard writers | yes | fire-trigger-safe §6, harvest-resolve Step 5, daily-ops §Never repeat it (procedure) | yes | keep; **convert to hooks** (block Edit/Write under `.github/trigger/`; block `git add`/commit of `ops/dashboard.json` unless `PW_ROUTINE=1`) — these are the two rules that have actually been broken this month |
| A13 | 118–129 | tracing architecture: only gemma-2-2b has graphs+transcoders; retry set; 400 aborts; four modes | prevents adding models expecting graphs | partly ("trace with llama" → must warn) | — | dated facts, dated correctly ("re-probe before relying") | keep |
| A14 | 130–136 | feature tagging degrades to NullFetcher; `clinical_mass` ~0 is an artifact | prevents publishing a false zero | yes | — | yes | keep |
| A15 | 137–141 | logits lane emits the same `batch_summary` schema | shapes any new measurement path | yes | — | yes | keep |
| A16 | 142–149 | output layout, `part_NN`, glob `batch_summary*`, join key; "generation archives commit to main; trace outputs to the dispatched branch — interleave" | prevents clobbering parts and mis-joins | yes | daily-ops §1, harvest-resolve Step 1, publish-site-data precondition 2, fire-trigger-safe §1.3 all elaborate the two-branch split | the split sentence is **obsolete since #6**: both land on `main` | rewrite the last sentence: "Both commit to `main` (since 2026-09-04); CI commits interleave with yours, so `git pull --rebase` before pushing." |
| A17 | 150–157 | analysis chain (collector, stats, archive export) | orientation | no | — | yes | keep |
| A18 | 158–165 | publishing exporter behaviour, render cap, archive URL | prevents `--with-pngs`/cap changes | yes | publish-site-data step 1 duplicates the cap/PNG policy (fine: procedure) | yes | keep |
| A19 | 167–173 | Tufte figure style | changes any figure a session draws | yes ("plot the penalty distribution" → no legend, no chrome) | — | yes | keep; candidate to **promote to `~/.claude/CLAUDE.md`** if it is your preference in every project (it is stated as "standing preference") |
| A20 | 175–181 | tests offline/fast, "must stay green"; regression test per bug; YAML validated by parsing | shapes test writing | yes | — | **partly false**: 13 tests fail in a fresh container (12 dependency gaps, `test_specialty_map` data drift) and the file does not say so | rewrite: add "Baseline as of 2026-09-06: 13 known failures in a minimal container (dependency-gated tests, plus `test_specialty_map` drift); anything beyond those is yours." |
| A21 | 183–189 | PR workflow: focused PRs, tested, migration notes | shapes PR scope | weakly | overlaps A22 header (two sections named "Pull request workflow") | yes | rewrite: merge into A22 as an unnumbered lead paragraph, one heading |
| A22 | 191–209 | required workflow, items 1–7 | the whole Codex loop | yes per item (open a PR → `@codex review` posted? etc.) | item 1 vs A7/A12 operational commits — reconciled by A23; item 4 vs A25.2 — cross-referenced; item 4 vs pr-review-response §3 ("Wrong … do not push it. Say so.") — **skill omits the ask-first step** | yes | keep; fix skill |
| A23 | 211–219 | exception to item 1: operational commits to `main`; everything else via PR; branching is free | prevents item 1 from breaking the ops tooling | yes | — | yes | keep |
| A24 | 221–255 | Code Review Rules (7 verbatim) + repo-specific referents (stored data, spend, `batch_summary` compat, single-writer) | tells reviewers what "destructive" means here | n/a (addressed to reviewers) | referents restate A5, A10, A12, A16 — deliberate (the reviewer needs them in one place) | yes | keep |
| A25 | 257–284 | coding constraints: seed in artifact; no silent parsing failures; type hints on new code only; analysis ≠ presentation | changes how new scripts are written | yes each ("write a bootstrap" → seed recorded in output) | — | yes; the "50 functions, 0 hinted" count is dated and will rot | keep; drop the counts or date them ("as of 2026-09-04") — they are dated already; keep |
| A26 | 286–312 | responding to review: verify, disposition per thread, resolve only fixed, never apply unchecked; decline via ask-first | the review loop's other half | yes | pr-review-response is the procedure and says so; A26.1's "five findings… four real" vs skill intro "three findings… two real" — **numbers disagree** | yes | keep; fix the skill's intro |
| A27 | 314–354 | known measurement limitations (bfloat16, misread token, per-pair noise, consequence) | stops a session "fixing" `logits_eval.py` or quoting a per-pair number | yes ("what is pair 20's probability?" → must caveat) | frontend AGENTS.md carries a 2-bullet summary that points here — fine | yes | keep (your stated reason: nobody goes looking). It is ~900 tokens of facts, not rules; if always-on cost ever matters, **demote** to `docs/known_limitations.md` with a 3-line pointer here |

### 2.3 Cross-file contradictions found (summary)

| Where | What | Fix in |
|---|---|---|
| fire-trigger-safe §5, description | "paid triggers: scenario-generation and model-evaluation" — omits advice-eval and mitigation; description lists 7 lanes | skill |
| fire-trigger-safe §1.2 | "activation-patching … has no workflow on main" — false since #6 | skill |
| fire-trigger-safe §1.2 | "first-ever fire on a branch fires; merging that file later RE-fires it" — the second half is right, the first is now guarded (`created`) | skill |
| fire-trigger-safe §1.3, harvest-resolve Step 1/3, publish-site-data pre-2 & step 9, daily-ops §1/§2/§5/§7 | working-branch/main split, `git checkout origin/main -- data/simulated/…`, "push the branch, then branch:main" — all obsolete since #6 | skills |
| holdout-seal-check line 522 | "Never run the check against a **main** checkout's dashboard" — **now contradicts its own Step 1** ("run from current `main`"); missed in PR #9 | skill |
| daily-ops-cycle (whole body) | describes the active-study cycle (Tier B generation, 2-hourly accelerator, "sections 1–7", `CLAUDE.md` as the conventions file); the standing prompt is maintenance-mode "sections 0–7" and the only fire is the drift sentinel | skill |
| pr-review-response §3, intro | no ask-first step; finding counts differ from AGENTS.md | skill |
| AGENTS.md A16 | two-branch sentence | AGENTS.md |

---

## 3. Skills, commands, agents

No commands, no agents. Six project skills, one Anthropic global, nine account-synced.

| Skill | Description picks it reliably? | Overlap | Stale references | Cheaper form? | Verdict |
|---|---|---|---|---|---|
| **daily-ops-cycle** (161 lines) | Yes for "run the daily cycle"; it also says it triggers "when the daily Routine fires" — but the Routine is a fresh cloud session driven by its own prompt, which points at the standing prompt, not at this skill. In practice this skill is invoked by nobody. | Body restates standing-prompt §1–7 while saying "where this skill compresses, that file governs" — a second copy of a file that declares itself authoritative | `CLAUDE.md` as conventions file; "working-branch copy"; `git fetch origin main` split; §4 Tier B generation/backfill/accelerator (study complete 1,600/1,600; accelerator retired); §5 `branch:main`; "sections 1–7" (now 0–7) | Yes: a 25-line wrapper that bootstraps per `docs/fresh_session_bootstrap.md` and hands off to the standing prompt | **rewrite → thin wrapper** (text in §5.4) |
| **fire-trigger-safe** (130) | Yes; the "whenever a trigger must be fired, chained, or resolved" clause overlaps harvest-resolve's trigger | Exit codes, settle window, single-writer, Never list appear in both this and harvest-resolve; daily-ops §4 has a third copy | §1.2 activation-patching; §1.2 first-fire-on-branch; §1.3 working-branch copy; §5 paid list | No — it is the procedure; but it should be the **single owner** of exit codes/settle/single-writer | rewrite (targeted) |
| **harvest-resolve** (130) | Yes ("did CI finish") | see above | Step 1 branch split; Step 3 activation-patching branch note; `gh run list` (no `gh` in remote sessions — the MCP tools are the path, which it also names) | No | rewrite (targeted); point at fire-trigger-safe for exit codes instead of repeating them |
| **holdout-seal-check** (103) | Yes, and the "including this session's own output" clause is exactly right | none | line 522 contradicts Step 1 | No — the breach protocol is a real procedure | rewrite one line |
| **pr-review-response** (105) | Yes | §6 vs CLAUDE.md C3 (intended: procedure vs tool) | intro counts; §3 lacks item 4; §5 says "gh run list" nowhere — fine | No | rewrite (two spots) |
| **publish-site-data** (127) | Yes | daily-ops §5 restates it (delete there) | pre-2 branch split; step 9 `branch:main`; "Report mode until F-M27" (status unknown — verify) | No | rewrite (targeted) |
| global `session-start-hook` | Anthropic-provided; name/dir mismatch (cosmetic) | none | — | — | leave |
| synced account skills (docx, pdf, xlsx, pptx, skill-creator, morning, import-memory, aact-baseline-extraction, tracked-docx…) | account-level; ~1,100 tokens of descriptions in every session of every project | none with this repo | — | Not this repo's decision; if any are never used from Claude Code, un-sync them in claude.ai to recover the tokens | leave |

Shared "Never" lists: secrets, `data/simulated/` append-only, misspellings, and
`--force-evict`/`--override-budget` are repeated across four skills. The first
three are `AGENTS.md` hard conventions and load every session already — **delete
from the skills** (≈120 tokens each, on demand only, so the saving is clarity, not
context). The flag prohibitions belong in fire-trigger-safe only.

---

## 4. Auto memory

There is no auto-memory directory for this project (`~/.claude/projects/-home-user/`
holds transcripts only; no `memory/`, no `MEMORY.md`). Nothing loads, nothing is
stale, nothing to migrate. This matches the design stated in the Routine prompt
("the repos are your memory"): the durable state is `ops/dashboard.json`,
`ops/trigger_journal.jsonl`, `docs/briefs/`, and `AGENTS.md`'s **Known
measurement limitations** section, which is the one place a "memory" was written
into a versioned file deliberately. Recommendation: keep it that way; do not
enable auto memory for this project, since anything worth remembering here is
either a fact for `AGENTS.md`/`docs/` or a decision for `ops/dashboard.json`.

---

## 5. Proposed end state

Applied only on your approval. Files not listed are unchanged.

### 5.1 Projected always-on cost

| | now | after |
|---|---|---|
| `AGENTS.md` | ~5,870 | ~5,790 (A8, A16, A20, A21 edits; net −80) |
| `CLAUDE.md` | ~190 | ~170 |
| project skill descriptions | ~440 | ~400 (daily-ops description shortened) |
| **project total** | **~6,500** | **~6,360** |
| hooks | 0 | 0 (hooks cost no context) |

The always-on cost is already lean; the value of this audit is correctness (the
stale two-branch procedures) and enforcement (hooks), not tokens.

### 5.2 `CLAUDE.md` — full proposed text

```markdown
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
- `.claude/settings.json` installs guard hooks (see `.claude/hooks/README.md`):
  they refuse edits under `.github/trigger/`, commits that stage
  `ops/dashboard.json` outside the Routine, and pushes that delete a ref or
  carry a trigger-file change without the matching `PW_ALLOW_*` variable. A
  refusal is the rule working, not an obstacle to route around.
```

### 5.3 `.claude/settings.json` — full proposed text, plus the two hook scripts

The four rules a hook can enforce are the four that were broken or nearly broken
this month: hand edits under `.github/trigger/` (never by a session, but a merge
did it on 09-04), a second committer of `ops/dashboard.json`, a push carrying a
trigger-file change outside `fire_trigger.py`, and branch deletion (your stated
concern for local sessions; Anthropic's proxy blocks it remotely, nothing blocks
it locally). Hooks run in both remote and local sessions once the file is
committed, which is exactly the local enforcement you asked for.

```json
{
  "permissions": {
    "allow": [
      "Artifact", "AskUserQuestion", "SendUserFile",
      "Bash(python *)", "Bash(python3 *)", "Bash(ruff *)", "Bash(git *)",
      "Bash(pip install *)", "Bash(ls *)", "Bash(cat *)", "Bash(head *)",
      "Bash(tail *)", "Bash(grep *)", "Bash(sed *)", "Bash(find *)",
      "Bash(wc *)", "Bash(date *)", "Bash(mkdir *)", "Bash(cp *)",
      "mcp__Claude_Code_Remote__send_later", "mcp__Claude_Code_Remote__create_trigger",
      "mcp__Claude_Code_Remote__list_triggers", "mcp__Claude_Code_Remote__update_trigger",
      "mcp__Claude_Code_Remote__delete_trigger", "mcp__Claude_Code_Remote__fire_trigger",
      "mcp__github__actions_list", "mcp__github__actions_get", "mcp__github__get_job_logs",
      "mcp__github__get_file_contents", "mcp__github__list_commits", "mcp__github__get_commit"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{ "type": "command", "command": "python3 .claude/hooks/guard_paths.py" }]
      },
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "python3 .claude/hooks/guard_git.py" }]
      }
    ]
  }
}
```

`.claude/hooks/guard_paths.py` (new; reads the tool call as JSON on stdin; exit 2
refuses with the message on stderr):

```python
#!/usr/bin/env python3
"""Refuse file edits that AGENTS.md forbids by hand: anything under
.github/trigger/ (fire_trigger.py is the only writer) and ops/dashboard.json
outside the daily Routine session (PW_ROUTINE=1)."""
import json, os, sys
call = json.load(sys.stdin)
path = (call.get("tool_input") or {}).get("file_path", "")
rel = os.path.relpath(path) if path else ""
if rel.startswith(".github/trigger/"):
    sys.stderr.write("refused: .github/trigger/ is written only by scripts/fire_trigger.py "
                     "(AGENTS.md, Ops tooling). Use `fire` or `park`.\n")
    sys.exit(2)
if rel == "ops/dashboard.json" and os.environ.get("PW_ROUTINE") != "1":
    sys.stderr.write("refused: ops/dashboard.json is committed only by the daily Routine "
                     "session (AGENTS.md, Single-writer). Set PW_ROUTINE=1 only in that session.\n")
    sys.exit(2)
sys.exit(0)
```

`.claude/hooks/guard_git.py` (new):

```python
#!/usr/bin/env python3
"""Refuse git commands that AGENTS.md forbids: ref deletion, force pushes, a
push whose commits change .github/trigger/ without PW_ALLOW_TRIGGER=1 (the
variable fire_trigger.py's own push path exports), and staging
ops/dashboard.json outside the Routine session (PW_ROUTINE=1)."""
import json, os, re, subprocess, sys
call = json.load(sys.stdin)
cmd = (call.get("tool_input") or {}).get("command", "")
def refuse(msg):
    sys.stderr.write("refused: " + msg + "\n"); sys.exit(2)
if re.search(r"\bgit\b.*\bpush\b", cmd):
    if re.search(r"--delete\b|\s:refs/heads/|\s:[A-Za-z0-9_./-]+(\s|$)", cmd):
        refuse("branch deletion is the owner's, done in the GitHub UI, never from a session.")
    if re.search(r"--force\b|-f\b|--force-with-lease", cmd):
        refuse("force pushes rewrite shared history (AGENTS.md; the 09-04 force-push fired a lane).")
    if os.environ.get("PW_ALLOW_TRIGGER") != "1":
        try:
            out = subprocess.run(["git", "diff", "--name-only", "@{u}...HEAD", "--", ".github/trigger/"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            out = ""
        if out:
            refuse("this push carries a trigger-file change (" + out.replace("\n", ", ") +
                   "); only scripts/fire_trigger.py may fire a lane.")
if re.search(r"\bgit\b.*\b(add|commit)\b", cmd) and "ops/dashboard.json" in cmd \
        and os.environ.get("PW_ROUTINE") != "1":
    refuse("ops/dashboard.json is committed only by the daily Routine session; "
           "run `git checkout -- ops/dashboard.json` first.")
sys.exit(0)
```

Two consequences to accept before approving: (a) `scripts/fire_trigger.py` needs a
one-line change to export `PW_ALLOW_TRIGGER=1` around its own `git push`
(otherwise its push is a `python` command, not a `git` command, so the Bash hook
never sees it — it is unaffected; the variable is for the `--no-git` path where
you push by hand). (b) The Routine's prompt must set `PW_ROUTINE=1` before its
dashboard commit — one line in the prompt you paste. Both are small and I'd do
them in the same PR.

### 5.4 `AGENTS.md` — replacements only (everything else unchanged)

1. Line 65 — `Eight lanes on this branch.` → `Eight lanes.`
2. Lines 146–149 (end of *Output layout & checkpointing*) — replace
   "Generation archives commit to **main**; trace outputs commit to **the dispatched branch** — expect the two to interleave, and `git pull --rebase` before pushing."
   with
   "Since 2026-09-04 both generation archives and trace outputs commit to `main` (the dispatched branch is `main`); CI's commits interleave with yours, so `git pull --rebase` before every push."
3. Lines 175–181 (*Tests*) — append: "Baseline in a minimal container as of 2026-09-06: 13 known failures (12 dependency-gated tests that need `matplotlib`/`networkx`/`pillow`, plus `tests/test_specialty_map.py` on data drift). Anything beyond those is the change's."
4. Lines 183–189 — delete the heading `## Pull request workflow` and fold its paragraph under `## Pull request workflow — required` as the lead paragraph (one section, not two with the same name).
5. Line 51 region (*Execution model*, first paragraph) — append one sentence: "A machine that *can* run inference locally (yours, with a GPU) still commits no locally produced measurement: every committed summary records `inference.environment`, and only CI-produced summaries are measurements."
6. Under *Ops tooling* (line 104–114) — append: "Enforced, not only stated: `.claude/settings.json` hooks refuse hand edits under `.github/trigger/`, non-Routine commits of `ops/dashboard.json`, ref deletions, force pushes, and pushes that carry a trigger-file change without `PW_ALLOW_TRIGGER=1`."

### 5.5 `.claude/skills/daily-ops-cycle/SKILL.md` — full proposed text

```markdown
---
name: daily-ops-cycle
description: Run exactly one maintenance ops cycle for patientwords-engine, exactly as docs/routine_standing_prompt.md sections 0–7 prescribe. Use when the user says "run the daily cycle" / "run the ops cycle"; never for an ad-hoc fire, publish, or harvest, and never twice in one session.
---

# Daily ops cycle

`docs/routine_standing_prompt.md` on `main` is the authority — sections 0–7, in
order, with every parameter taken from it verbatim. This skill adds nothing to
it; it exists so a session invoked by hand does the same bootstrap and stops at
the same place as the scheduled Routine.

1. **Bootstrap** per `docs/fresh_session_bootstrap.md`: both repos on `main`,
   clean `git status`, `ops/dashboard.json` identical to `origin/main`,
   `python scripts/seal_check.py --site ../patientwords --extra docs,ops` not
   exiting 2, `git push --dry-run origin main` succeeding. Any of those failing:
   stop and say which.
2. **Run sections 0–7** of the standing prompt. Section 0 may end the cycle.
   Fires go through the fire-trigger-safe skill, harvests through
   harvest-resolve, the seal check through holdout-seal-check, and section 5
   through publish-site-data — this session is the dashboard's writer
   (`PW_ROUTINE=1` before the dashboard commit).
3. **Stop.** One cycle. No second cycle, no Routines, no reminders, no crons.
   End with the digest line from `python scripts/daily_brief.py --digest`.
```

### 5.6 Other skills — replacements only

**fire-trigger-safe**
- Description: replace the seven-lane list with "any of the eight lanes in `.github/trigger/`".
- §1.2: replace the activation-patching clause and the first-fire clause with: "Confirm the workflow file exists on `main` (all eight do since 2026-09-04). A push that *creates* a ref fires nothing (`github.event.created` guard); a trigger file that changes on an existing ref fires, and a merge that carries that change re-fires it."
- §1.3: delete (both archives and outputs are on `main`; nothing to copy across).
- §5: "Paid triggers: `scenario-generation`, `model-evaluation`, `advice-eval`, and `circuit-trace` with `show_mitigation: true` ($0.15 imputed). `PAID_TRIGGERS` in the script is the source of truth."
- §Never: delete the secrets / misspellings / `data/simulated` bullets (AGENTS.md hard conventions, always loaded).

**harvest-resolve**
- Step 1: replace the two-command block with `git pull --rebase origin main` and one sentence: "Everything lands on `main` since 2026-09-04."
- Step 3, activation-patching: replace with "harvest like any other lane (part files under `trace_out/`)."
- Step 4: drop `gh run list` (not available in remote sessions); keep the MCP actions tools and the landing-commit check.
- "Exit codes" section: replace with "Exit codes, the settle window, and the single-writer revert are defined once in fire-trigger-safe; apply them as written there."
- §Never: delete the last four bullets (duplicates of AGENTS.md and fire-trigger-safe).

**holdout-seal-check**
- Line 522 `Never run the check against a main checkout's dashboard.` → `Never run the check against a stale checkout's dashboard — Step 1's origin/main comparison must pass first.`

**pr-review-response**
- Intro: "three findings … two were real" → "five findings across two rounds … four were real" (matches AGENTS.md A26.1).
- §3, second paragraph → "Wrong, or right-but-larger-than-this-pull-request → do not push it. Before declining, post a comment addressed to @codex with the specific question (AGENTS.md, required workflow item 4); act on the answer, then reply with the disposition."

**publish-site-data**
- Precondition 2 → "`git pull --rebase origin main` in both repos first."
- Step 9, site → "Commit the data payloads and push `main`; GitHub Pages serves it, so this push is the publish — the contract, claim and seal gates above are the last check."
- Step 7 "Report mode … until F-M27" — verify F-M27's status before touching; if it has landed, switch to `--strict`.
- §Never: delete the misspellings / `data/simulated` / secrets bullets.

### 5.7 New file: `.github/copilot-instructions.md` (one line)

```markdown
Read `AGENTS.md` at the repository root first — it is the single source of truth for this repository; nothing is repeated here.
```

### 5.8 Every deletion, with reason

| Deletion | Reason |
|---|---|
| `AGENTS.md` heading `## Pull request workflow` (line 183) | two sections with the same name; the paragraph survives under the required section |
| `AGENTS.md` "on this branch" (line 65) | one branch since 2026-09-04 |
| `AGENTS.md` two-branch sentence (lines 146–149) | obsolete since #6 |
| `CLAUDE.md` parenthetical skill list (lines 13–15) | drifts when a skill is added; the directory is the list |
| daily-ops-cycle body §1–§7 and §Never (≈2,300 tokens) | second copy of the standing prompt, describing the retired active-study cycle; the standing prompt governs by its own words |
| fire-trigger-safe §1.2 activation-patching clause | false since #6 |
| fire-trigger-safe §1.3 | obsolete (single branch) |
| harvest-resolve Step 1 second command, Step 3 activation-patching note, Exit-codes block, last four Never bullets | obsolete or duplicated |
| publish-site-data precondition 2, step 9 `branch:main`, three Never bullets | obsolete or duplicated |
| holdout-seal-check line 522 (replaced) | contradicts Step 1 |
| pr-review-response intro counts (replaced) | disagree with AGENTS.md |
| skill "Never" bullets on secrets / `data/simulated` / misspellings (four skills) | verbatim copies of AGENTS.md hard conventions, which load in every session |

Nothing under `docs/`, `ops/`, `data/`, `scripts/`, or `tests/` is touched by this
proposal except the one-line `PW_ALLOW_TRIGGER` export in `fire_trigger.py`
(§5.3) — that one I'd rather you look at, since it is the script's own push path.

---

## 6. What I need from you

1. Approve or amend §5.2–§5.7. The hooks (§5.3) are the only part with a
   behavioural cost — two environment variables the Routine prompt and the
   `--no-git` fire path must set.
2. Say whether A19 (figure style) and the writing preferences you gave me at the
   start of this session should go to `~/.claude/CLAUDE.md` — they read as
   preferences for every project, and today they live in no file at all.
3. On approval I open one PR with all of it (branch from `main`, `@codex review`
   posted — noting that Codex currently cannot set up a container on this repo).
