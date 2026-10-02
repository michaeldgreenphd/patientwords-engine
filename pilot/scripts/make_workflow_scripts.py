"""Generate the two Workflow-tool scripts from the planned prompts, so that every prompt a subagent receives is the
byte-identical text whose SHA-256 is recorded in calls.json and checker_batches.json.

  python3 scripts/make_workflow_scripts.py generation [--replace]  -> workflows/generation.workflow.js
  python3 scripts/make_workflow_scripts.py checker [--replace]     -> workflows/checker.workflow.js

The arguments are parsed by argparse (parse_args), so --replace may stand before or after the stage, as in
build_api_requests.py (Copilot review of PR #69).

A run directory whose manifest.json is finalized is not written into without --replace (common.finalized_run_guard):
with PILOT_DIR unset the scripts would otherwise replace the recorded run's own workflow scripts.

The generation script runs one subagent per call with no output schema (format validity is an estimand), retries a
call once when no returned line carries the four required keys, and returns every attempt verbatim. The checker
script runs one subagent per batch with a structured-output schema and retries once on an empty return. Under
harness version 2 the generation retry test counts the five version-2 keys and the checker schema requires relation,
sentence_natural and patient_realism; a version-1 render is byte-identical to the recorded run's form.

Every agent label carries the prompt's SHA-256 and the frozen protocol's (`<id> attempt <n> sha256=<hash> protocol=<hash>`), which the run's journal records
and extract_workflow_journal.py copies into the result file, so parse_generation.py and parse_checker.py can bind
a result to the plan it answered (Codex review of PR #52). The scripts under workflows/ that produced the recorded
run predate this label and carry no hash.
"""
from __future__ import annotations

import argparse
import json

from common import (
    PILOT,
    checker_output_schema,
    finalized_run_guard,
    load_calls,
    load_checker_batches,
    plan_version,
    required_fields,
    sha256_file,
)

GENERATION = """export const meta = {
  name: 'pilot-generation',
  description: 'Stimulus pilot: one isolated subagent per (cell, arm) generation call, retry once on failure',
  phases: [{ title: 'Generate', detail: 'one subagent per call, no shared outputs, retry once' }],
}
const REQUIRED = __REQUIRED__
const PROTOCOL = __PROTOCOL__
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
    const raw = await agent(call.prompt, { label: `${call.id} attempt ${attempt} sha256=${call.prompt_sha256} protocol=${PROTOCOL}`, phase: 'Generate' })
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
const PROTOCOL = __PROTOCOL__
const BATCHES = __BATCHES__
const SCHEMA = __SCHEMA__
phase('Check')
const results = await pipeline(BATCHES, async (b) => {
  const attempts = []
  for (let attempt = 1; attempt <= 2; attempt++) {
    const res = await agent(b.prompt, { label: `${b.batch_id} attempt ${attempt} sha256=${b.prompt_sha256} protocol=${PROTOCOL}`, phase: 'Check', schema: SCHEMA })
    const ok = !!(res && Array.isArray(res.verdicts) && res.verdicts.length)
    attempts.push({ attempt, result: ok ? res : null, null_return: res === null })
    log(`${b.batch_id} attempt ${attempt}: ${ok ? res.verdicts.length + ' verdicts' : 'no usable return'}`)
    if (ok) break
  }
  return { batch_id: b.batch_id, prompt_sha256: b.prompt_sha256, attempts }
})
return { batches: results.filter(Boolean) }
"""


# the version-1 checker schema exactly as the recorded run's script carried it: a version-1 render must stay
# byte-identical, since finalize renders the script again and compares it with the one that ran
CHECKER_SCHEMA_V1 = """{
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
}"""


def checker_schema_js(version: int) -> str:
    """The checker's structured-output schema as the workflow script declares it: the version-1 literal, or for
    version 2 the schema common.checker_output_schema builds from the enums (relation, sentence_natural,
    patient_realism, each required), as a JSON object literal."""
    return CHECKER_SCHEMA_V1 if version < 2 else json.dumps(checker_output_schema(version, closed=False), indent=2)


def render(which: str) -> tuple[str, int]:
    """The workflow script for a stage, pure: (text, item count). main writes it; write_manifest.py finalize renders
    it again and refuses a script on disk that differs (Codex review of PR #52)."""
    if which == "generation":
        plan = load_calls()  # refused unless it is the plan the inputs on disk derive
        version = plan_version(plan)
        payload = [{"id": c["id"], "arm": c["arm"], "cell": c["cell"], "prompt_sha256": c["prompt_sha256"],
                    "prompt": c["prompt"]} for c in plan["calls"]]
        template = GENERATION if version < 2 else GENERATION.replace("with the four keys", "with the required keys")
        text = template.replace("__REQUIRED__", json.dumps(required_fields(version))).replace(
            "__CALLS__", json.dumps(payload, ensure_ascii=False))
    elif which == "checker":
        plan = load_checker_batches()
        payload = [{"batch_id": b["batch_id"], "prompt_sha256": b["prompt_sha256"], "prompt": b["prompt"]}
                   for b in plan["batches"]]
        # the schema goes in before the batches, so no item text can be read as the placeholder
        text = CHECKER.replace("__SCHEMA__", checker_schema_js(plan_version(plan))).replace(
            "__BATCHES__", json.dumps(payload, ensure_ascii=False))
    else:
        raise SystemExit("usage: make_workflow_scripts.py generation|checker")
    # the frozen protocol's hash rides in every agent label, so the run's journal records which protocol it ran
    # under and the parsers refuse a result from another (Codex review of PR #52)
    return text.replace("__PROTOCOL__", json.dumps(sha256_file(PILOT / "PROTOCOL.md"))), len(payload)


STAGES = ("generation", "checker")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The command line, in one place: the stage and --replace, in either order."""
    ap = argparse.ArgumentParser(description="Render a stage's Workflow-tool script from its plan into "
                                             "workflows/<stage>.workflow.js.")
    ap.add_argument("which", choices=STAGES, help="the stage whose plan to render")
    ap.add_argument("--replace", action="store_true", help="write into a run directory whose manifest is finalized")
    return ap.parse_args(argv)


def main(which: str, replace: bool = False) -> None:
    if which not in STAGES:
        raise SystemExit("usage: make_workflow_scripts.py generation|checker [--replace]")
    finalized_run_guard("make_workflow_scripts", replace)  # never re-render over a sealed run's scripts
    text, n_items = render(which)
    out_dir = PILOT / "workflows"
    out_dir.mkdir(exist_ok=True)  # only once the plan has loaded: a refused plan writes nothing
    path = out_dir / f"{which}.workflow.js"
    path.write_text(text, encoding="utf-8")
    print(f"{path} ({n_items} items, {len(text)} bytes)")


if __name__ == "__main__":
    args = parse_args()
    main(args.which, replace=args.replace)
