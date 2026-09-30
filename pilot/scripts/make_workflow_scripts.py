"""Generate the two Workflow-tool scripts from the planned prompts, so that every prompt a subagent receives is the
byte-identical text whose SHA-256 is recorded in calls.json and checker_batches.json.

  python3 scripts/make_workflow_scripts.py generation   -> workflows/generation.workflow.js
  python3 scripts/make_workflow_scripts.py checker      -> workflows/checker.workflow.js

The generation script runs one subagent per call with no output schema (format validity is an estimand), retries a
call once when no returned line carries the four required keys, and returns every attempt verbatim. The checker
script runs one subagent per batch with a structured-output schema and retries once on an empty return.

Every agent label carries the prompt's SHA-256 (`<id> attempt <n> sha256=<hash>`), which the run's journal records
and extract_workflow_journal.py copies into the result file, so parse_generation.py and parse_checker.py can bind
a result to the plan it answered (Codex review of PR #52). The scripts under workflows/ that produced the recorded
run predate this label and carry no hash.
"""
from __future__ import annotations

import json
import sys

from common import PILOT, REQUIRED_FIELDS, load_calls, load_checker_batches

GENERATION = """export const meta = {
  name: 'pilot-generation',
  description: 'Stimulus pilot: one isolated subagent per (cell, arm) generation call, retry once on failure',
  phases: [{ title: 'Generate', detail: 'one subagent per call, no shared outputs, retry once' }],
}
const REQUIRED = __REQUIRED__
const CALLS = __CALLS__
function nValid(text) {
  if (typeof text !== 'string') return 0
  let n = 0
  for (const line of text.split('\\n')) {
    const s = line.trim()
    if (!s) continue
    try {
      const o = JSON.parse(s)
      if (o && typeof o === 'object' && !Array.isArray(o) && REQUIRED.every(k => k in o)) n++
    } catch (e) {}
  }
  return n
}
phase('Generate')
const results = await pipeline(CALLS, async (call) => {
  const attempts = []
  for (let attempt = 1; attempt <= 2; attempt++) {
    const raw = await agent(call.prompt, { label: `${call.id} attempt ${attempt} sha256=${call.prompt_sha256}`, phase: 'Generate' })
    const text = typeof raw === 'string' ? raw : null
    const v = nValid(text)
    const lines = text === null ? 0 : text.split('\\n').filter(l => l.trim()).length
    attempts.push({ attempt, raw: text, null_return: raw === null, n_lines: lines, n_valid_lines: v })
    log(`${call.id} attempt ${attempt}: ${text === null ? 'null return' : lines + ' lines'}, ${v} with the four keys`)
    if (v > 0) break
  }
  return { id: call.id, arm: call.arm, cell: call.cell, prompt_sha256: call.prompt_sha256, attempts }
})
return { calls: results.filter(Boolean) }
"""

CHECKER = """export const meta = {
  name: 'pilot-checker',
  description: 'Stimulus pilot: blind semantic-equivalence checker, one isolated subagent per batch of 30',
  phases: [{ title: 'Check', detail: 'one subagent per batch, structured output, retry once' }],
}
const BATCHES = __BATCHES__
const SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          equivalent: { type: 'string', enum: ['yes', 'no', 'unclear'] },
          reason: { type: 'string' },
        },
        required: ['id', 'equivalent', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}
phase('Check')
const results = await pipeline(BATCHES, async (b) => {
  const attempts = []
  for (let attempt = 1; attempt <= 2; attempt++) {
    const res = await agent(b.prompt, { label: `${b.batch_id} attempt ${attempt} sha256=${b.prompt_sha256}`, phase: 'Check', schema: SCHEMA })
    const ok = !!(res && Array.isArray(res.verdicts) && res.verdicts.length)
    attempts.push({ attempt, result: ok ? res : null, null_return: res === null })
    log(`${b.batch_id} attempt ${attempt}: ${ok ? res.verdicts.length + ' verdicts' : 'no usable return'}`)
    if (ok) break
  }
  return { batch_id: b.batch_id, prompt_sha256: b.prompt_sha256, attempts }
})
return { batches: results.filter(Boolean) }
"""


def main(which: str) -> None:
    out_dir = PILOT / "workflows"
    if which == "generation":
        calls = load_calls()["calls"]  # refused unless every prompt hashes to its stored prompt_sha256
        payload = [{"id": c["id"], "arm": c["arm"], "cell": c["cell"], "prompt_sha256": c["prompt_sha256"],
                    "prompt": c["prompt"]} for c in calls]
        text = GENERATION.replace("__REQUIRED__", json.dumps(REQUIRED_FIELDS)).replace(
            "__CALLS__", json.dumps(payload, ensure_ascii=False))
        path = out_dir / "generation.workflow.js"
    elif which == "checker":
        batches = load_checker_batches()["batches"]
        payload = [{"batch_id": b["batch_id"], "prompt_sha256": b["prompt_sha256"], "prompt": b["prompt"]}
                   for b in batches]
        text = CHECKER.replace("__BATCHES__", json.dumps(payload, ensure_ascii=False))
        path = out_dir / "checker.workflow.js"
    else:
        raise SystemExit("usage: make_workflow_scripts.py generation|checker")
    out_dir.mkdir(exist_ok=True)  # only once the plan has loaded: a refused plan writes nothing
    path.write_text(text, encoding="utf-8")
    print(f"{path} ({len(payload)} items, {len(text)} bytes)")


if __name__ == "__main__":
    main(sys.argv[1])
