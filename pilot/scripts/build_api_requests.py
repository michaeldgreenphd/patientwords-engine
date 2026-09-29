"""Build the exact Messages API request bodies for the planned generation calls or checker batches. Nothing is sent.

This file replaces the earlier live laptop driver. Under the engine's execution model nothing paid or networked
runs locally, all generation goes through push-to-run CI, and spend is journaled and ceiling-gated by
scripts/fire_trigger.py (AGENTS.md, Execution model; Codex review of PR #52). The sanctioned route for a live rerun
through the API is a pilot push-to-run lane, which does not exist yet. Until it does, the Claude Code Workflow path
(workflows/*.workflow.js) is the only way this pilot has been executed.

  python3 scripts/build_api_requests.py generation --model MODEL [--effort EFFORT] [--max-tokens N]
      -> api_requests_generation.json
  python3 scripts/build_api_requests.py checker --model MODEL [--effort EFFORT] [--max-tokens N]
      -> api_requests_checker.json

Each file lists one request body per call or batch ({model, max_tokens, messages, output_config}) beside the id and
the prompt's SHA-256 from calls.json or checker_batches.json, the retry rule the protocol fixes, and the result-file
shape parse_generation.py and parse_checker.py consume, so a lane that sends these requests can hand its responses
straight to the parsers. Checker requests carry an output_config.format JSON schema; generation requests carry none,
because format validity (estimand 1) measures the raw text. The model is a required argument: this run's model is in
manifest.json, and choosing another is a decision about the execution path, not a default to bury here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from common import PILOT, REQUIRED_FIELDS

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "equivalent": {"type": "string", "enum": ["yes", "no", "unclear"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "equivalent", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

RESULT_SHAPES = {
    "generation": {"file": "workflow_generation_result.json or any name passed to parse_generation.py",
                   "shape": {"calls": [{"id": "<call id>", "arm": "<A|B>", "cell": "<cell id>",
                                        "prompt_sha256": "<this request's prompt_sha256, copied from this file>",
                                        "attempts": [{"attempt": 1, "raw": "<the response text verbatim, or null>",
                                                      "null_return": False}]}]},
                   "notes": "attempts are numbered 1..n in order with n at most 2 (one retry), and attempt 2 is "
                            "accepted only when attempt 1 met the retry rule below; prompt_sha256 must equal the "
                            "planned prompt's hash, or parse_generation.py refuses the whole file before touching "
                            "anything on disk."},
    "checker": {"file": "workflow_checker_result.json or any name passed to parse_checker.py",
                "shape": {"batches": [{"batch_id": "<batch id>",
                                       "prompt_sha256": "<this request's prompt_sha256, copied from this file>",
                                       "attempts": [{"attempt": 1,
                                                     "result": {"verdicts": [{"id": "<item id from the batch>",
                                                                              "equivalent": "yes | no | unclear",
                                                                              "reason": "<one line>"}]}}]}]},
                "notes": "result is the parsed JSON object the model returned, with one verdict object per item id; "
                         "for an unsuccessful attempt set result to null (not an empty or string-valued verdicts "
                         "list). Attempts are numbered 1..n in order with n at most 2, attempt 2 is accepted only "
                         "when attempt 1 met the retry rule below, and prompt_sha256 must equal the planned batch "
                         "prompt's hash. parse_checker.py ignores an entry that is not an object "
                         "with a known id and a verdict in {yes, no, unclear}, and records ids without a usable "
                         "verdict as missing."},
}
RETRY_RULES = {
    "generation": f"retry once, with the identical request, when the response is empty or no returned line parses as "
                  f"a JSON object carrying the keys {REQUIRED_FIELDS}; keep both attempts verbatim (PROTOCOL.md 3)",
    "checker": "retry once, with the identical request, when no verdict list, or an empty one, comes back; ids still "
               "without a usable verdict are recorded as missing (PROTOCOL.md 6)",
}


def build_request(model: str, prompt: str, max_tokens: int, effort: str | None, schema: dict | None) -> dict:
    """One Messages API request body: a single user turn holding the rendered prompt, no system prompt."""
    req: dict = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    output_config: dict = {}
    if effort:
        output_config["effort"] = effort
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    if output_config:
        req["output_config"] = output_config
    return req


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Messages API request bodies for the pilot; sends nothing.")
    ap.add_argument("which", choices=["generation", "checker"])
    ap.add_argument("--model", required=True, help="model id; the subagent run's model is in manifest.json")
    ap.add_argument("--effort", default=None, help="output_config.effort (low|medium|high|xhigh|max); omit for the default")
    ap.add_argument("--max-tokens", type=int, default=16000)
    a = ap.parse_args()
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if a.which == "generation":
        items = json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))["calls"]
        requests = [{"id": c["id"], "arm": c["arm"], "cell": c["cell"], "prompt_sha256": c["prompt_sha256"],
                     "request": build_request(a.model, c["prompt"], a.max_tokens, a.effort, None)} for c in items]
    else:
        items = json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))["batches"]
        requests = [{"batch_id": b["batch_id"], "item_ids": b["item_ids"], "prompt_sha256": b["prompt_sha256"],
                     "request": build_request(a.model, b["prompt"], a.max_tokens, a.effort, VERDICT_SCHEMA)} for b in items]
    out = {"api_meta": {"purpose": "request bodies only; nothing was sent (engine execution model: paid generation "
                                   "runs through push-to-run CI)",
                        "model_requested": a.model, "effort": a.effort, "max_tokens": a.max_tokens, "built_utc": built,
                        "retry_rule": RETRY_RULES[a.which], "result_file": RESULT_SHAPES[a.which]},
           "requests": requests}
    path = PILOT / f"api_requests_{a.which}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(requests)} request bodies built for model {a.model}; nothing sent")


if __name__ == "__main__":
    main()
