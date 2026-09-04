# Owner decisions — 2026-08-16

Follow-on to `docs/decisions_20260815_owner.md`. Three items answered.

## 1 · Recreate the daily Routine with GitHub connected (approved)

**Decision.** The owner recreates the daily Routine from the claude.ai Routines
UI, where connectors can be attached, replacing
`trig_01DnZa9YRmHsrXJ56or3Sx1m` (created 2026-08-15 via `meta_mcp`, whose fired
sessions carry no GitHub MCP tools).

**Why it matters.** `docs/routine_standing_prompt.md` §2 requires a run be
confirmed terminal in GitHub before its journal entry is resolved. A session
without GitHub tools cannot do that; it can only infer terminality from
committed outputs. Observed live on the first firing (2026-08-16): the Routine
resolved the 10:28Z backfill entry at 13:31:57Z without GitHub confirmation. It
was correct in that instance — the run had succeeded — but output-based
inference cannot distinguish a finished run from one that committed a chunk and
then failed, which is the exact case the confirm rule exists to catch.

**Until the replacement exists**, the old Routine keeps running and keeps
inferring. That is a known, accepted gap, not a silent one.

**Repositories the new Routine must have attached** (both, both writable — the
cycle commits to both):

| Repository | Branch | Why the cycle needs it |
|---|---|---|
| `michaeldgreenphd/patientwords-engine` | `claude/gemma-clinical-colloquial-interp-mavx04` | fires triggers, harvests `trace_out/`, writes `ops/dashboard.json`, the journal, briefs and ledger |
| `michaeldgreenphd/patientwords` | `claude/gemma-clinical-colloquial-interp-mavx04` | publish step writes the site's `data/*.json` payloads |

Connector required: **GitHub**. No others — the cycle spends nothing and calls
no third-party service.

Schedule: daily, 13:00 UTC. Fresh session per firing (no persistent session).

Prompt text: `docs/ops_routine_spec_20260804.md` § "Prompt text", verbatim. It is
deliberately short and points at `docs/routine_standing_prompt.md`, so the cycle
re-reads current instructions from the branch at each firing rather than
inheriting a stale copy baked into the trigger.

**After the new Routine exists:** delete `trig_01DnZa9YRmHsrXJ56or3Sx1m`, or two
cycles will run each day — both writing `ops/dashboard.json`, which has a
single-writer rule.

## 2 · Coding worksheet rendering (approved)

Responses arrive as assistant markdown and the worksheet displayed the literal
`**`, `*`, `` ` `` and `###` marks. Now rendered — bold, italic, code, bullets,
headings — by building DOM nodes, never `innerHTML`: the text is model-authored
and both repos are public. Landed in `../patientwords/llm/code.html` (commits
`f5ee2db`, `420047c`), verified at 390 px in both themes.

A phone artifact carrying the same 25 items was published for the owner at their
request. It shares the worksheet's rubric, export shape and `rubric_sha256`, but
**cannot write a file** — the artifact sandbox blocks downloads — so it returns
codings as a copyable JSON block instead. The site worksheet remains the path
that produces a committable file directly.

## 3 · Anthropic API ceiling: $2/day (confirmed, no change)

The owner names **$2.00/day** for the Anthropic API. This is already the
enforced value: `scripts/fire_trigger.py:78`
`DEFAULT_DAILY_CEILING_USD = 2.0`, counting landed and in-flight `max_spend`.
No code change was needed and none was made.

**Still unnamed:** the OpenRouter ceiling is a separate pot,
`DEFAULT_OPENROUTER_DAILY_CEILING_USD = 10.0`
(`scripts/fire_trigger.py:82`). The 2026-08-15 question conflated the two and
quoted the $10 figure; the owner's answer addresses Anthropic only, so
OpenRouter stands at $10/day pending a separate instruction.
