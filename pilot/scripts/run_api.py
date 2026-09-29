"""Laptop driver: run the planned generation calls or checker batches through the Anthropic Messages API and write
result files in the exact shape parse_generation.py and parse_checker.py consume.

UNTESTED AGAINST THE LIVE API. This environment holds no API key, so only --dry-run (which builds every request
without sending it) has been executed. The pilot run itself used Claude Code subagents (workflows/*.js), which is
a different execution path: no system prompt of ours, but the harness's own. Numbers from this driver and from the
subagent run are not interchangeable; record which path produced a result in HANDOFF.md.

  python3 scripts/run_api.py generation --model MODEL [--effort EFFORT] [--dry-run]
      -> api_generation_result.json  (then: python3 scripts/parse_generation.py api_generation_result.json)
  python3 scripts/run_api.py checker --model MODEL [--effort EFFORT] [--dry-run]
      -> api_checker_result.json     (then: python3 scripts/parse_checker.py api_checker_result.json)

Design choices that matter for the estimands:
- No server-side fallbacks. A refusal is recorded as a failed attempt (stop_reason "refusal") and retried once like
  any other failed call; routing a refused request to a different model would mix models within an arm.
- No output schema on generation calls: format validity (estimand 1) measures the raw text. The checker uses
  output_config.format (json_schema), as the subagent run used structured output.
- Retry rule identical to the workflow scripts: retry once when no returned line carries the four required keys
  (generation) or when no verdict list comes back (checker).
- The model is a required argument. The subagent run inherited the session model recorded in manifest.json; pass
  that id to match it, or another id to change the execution deliberately.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

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


def n_valid_lines(text: str | None) -> int:
    if not text:
        return 0
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            o = json.loads(s)
        except ValueError:
            o = None
        if isinstance(o, dict) and all(k in o for k in REQUIRED_FIELDS):
            n += 1
    return n


def build_request(model: str, prompt: str, max_tokens: int, effort: str | None, schema: dict | None) -> dict:
    req = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    output_config = {}
    if effort:
        output_config["effort"] = effort
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    if output_config:
        req["output_config"] = output_config
    return req


def send(client, req: dict) -> dict:
    """One Messages API call. Returns {text, stop_reason, model, usage, request_id, error}."""
    import anthropic
    try:
        resp = client.messages.create(**req)
    except anthropic.APIStatusError as e:  # 4xx/5xx after the SDK's own retries
        return {"text": None, "error": f"APIStatusError {e.status_code}: {e.message}"}
    except anthropic.APIConnectionError as e:
        return {"text": None, "error": f"APIConnectionError: {e}"}
    text = "".join(b.text for b in resp.content if b.type == "text")
    out = {"text": text if resp.stop_reason != "refusal" else None, "stop_reason": resp.stop_reason,
           "model": resp.model, "usage": resp.usage.to_dict() if hasattr(resp.usage, "to_dict") else None,
           "request_id": getattr(resp, "_request_id", None), "error": None}
    if resp.stop_reason == "refusal":
        sd = getattr(resp, "stop_details", None)
        out["error"] = f"refusal: {getattr(sd, 'category', None)}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["generation", "checker"])
    ap.add_argument("--model", required=True, help="model id; the subagent run's model is in manifest.json")
    ap.add_argument("--effort", default=None, help="output_config.effort (low|medium|high|xhigh|max); omit for the default")
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--dry-run", action="store_true", help="build every request, send nothing")
    a = ap.parse_args()
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client = None
    if not a.dry_run:
        import anthropic  # resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile
        client = anthropic.Anthropic()

    if a.which == "generation":
        calls = json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))["calls"]
        results = []
        for c in calls:
            req = build_request(a.model, c["prompt"], a.max_tokens, a.effort, None)
            attempts = []
            for attempt in (1, 2):
                if a.dry_run:
                    attempts.append({"attempt": attempt, "raw": None, "null_return": True, "dry_run": True,
                                     "request_chars": len(json.dumps(req))})
                    break
                r = send(client, req)
                v = n_valid_lines(r["text"])
                attempts.append({"attempt": attempt, "raw": r["text"], "null_return": r["text"] is None,
                                 "n_valid_lines": v, "stop_reason": r.get("stop_reason"), "model": r.get("model"),
                                 "usage": r.get("usage"), "request_id": r.get("request_id"), "error": r.get("error")})
                print(f"{c['id']} attempt {attempt}: {'error ' + r['error'] if r['error'] else str(v) + ' lines with the four keys'}")
                if v > 0:
                    break
            results.append({"id": c["id"], "arm": c["arm"], "cell": c["cell"], "attempts": attempts})
        out = {"api_meta": {"path": "anthropic messages API via scripts/run_api.py", "model_requested": a.model,
                            "effort": a.effort, "max_tokens": a.max_tokens, "started_utc": started, "dry_run": a.dry_run},
               "calls": results}
        (PILOT / "api_generation_result.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"api_generation_result.json: {len(results)} calls{' (dry run)' if a.dry_run else ''}")
    else:
        batches = json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))["batches"]
        results = []
        for b in batches:
            req = build_request(a.model, b["prompt"], a.max_tokens, a.effort, VERDICT_SCHEMA)
            attempts = []
            for attempt in (1, 2):
                if a.dry_run:
                    attempts.append({"attempt": attempt, "result": None, "null_return": True, "dry_run": True,
                                     "request_chars": len(json.dumps(req))})
                    break
                r = send(client, req)
                parsed = None
                if r["text"]:
                    try:
                        parsed = json.loads(r["text"])
                    except ValueError:
                        parsed = None
                ok = isinstance(parsed, dict) and isinstance(parsed.get("verdicts"), list) and bool(parsed["verdicts"])
                attempts.append({"attempt": attempt, "result": parsed if ok else None, "null_return": r["text"] is None,
                                 "stop_reason": r.get("stop_reason"), "model": r.get("model"), "usage": r.get("usage"),
                                 "request_id": r.get("request_id"), "error": r.get("error")})
                print(f"{b['batch_id']} attempt {attempt}: {'error ' + r['error'] if r['error'] else (str(len(parsed['verdicts'])) + ' verdicts' if ok else 'no usable verdicts')}")
                if ok:
                    break
            results.append({"batch_id": b["batch_id"], "attempts": attempts})
        out = {"api_meta": {"path": "anthropic messages API via scripts/run_api.py", "model_requested": a.model,
                            "effort": a.effort, "max_tokens": a.max_tokens, "started_utc": started, "dry_run": a.dry_run},
               "batches": results}
        (PILOT / "api_checker_result.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"api_checker_result.json: {len(results)} batches{' (dry run)' if a.dry_run else ''}")


if __name__ == "__main__":
    sys.exit(main())
