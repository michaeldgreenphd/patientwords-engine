"""Parse the raw generation responses. Never repairs a line: a line either validates or is logged as a format failure.

Input: a JSON file {"calls": [{"id", "arm", "cell", "attempts": [{"attempt", "raw", "null_return"}]}]}.
Writes generated/raw/<call>__attempt<N>.txt (verbatim), generated/<call>.jsonl (format-valid rows of the final
attempt), generated/all_rows.jsonl (the same rows in protocol order), generated/format_failures.jsonl, call_log.jsonl.

Every call-log entry, row and format failure carries `prompt_sha256`, the planned prompt's hash from the calls.json
it was parsed against, so build_checker_set.py, compute_summary.py and write_manifest.py can refuse a parse that
belongs to another plan; a second attempt is accepted only when the first met the protocol's retry rule (Codex
review of PR #52).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from common import (
    CONTROLS_PER_CALL,
    MAX_ATTEMPTS,
    PILOT,
    ROWS_PER_CALL,
    attempt_failed,
    cell_id,
    cells,
    control_is_faithful,
    lines_of,
    load_calls,
    resolve_input,
    result_binding_problems,
    validate_line,
    write_jsonl,
)


def previous_outputs(gen_dir: Path) -> list[Path]:
    """Files an earlier parse left under generated/: the manifest hashes every one of them, so a rerun must not
    leave a stale attempt file beside the new ones (Codex review of PR #52)."""
    return sorted(gen_dir.glob("*.jsonl")) + sorted((gen_dir / "raw").glob("*.txt"))


def validate_result(result: object, planned: dict[str, dict], unbound: bool = False) -> dict[str, dict]:
    """The result contract, checked in full before anything on disk is touched: an object with a `calls` list whose
    entries are objects with a string id that is planned and appears exactly once, an `attempts` list of objects
    with a `raw` that is a string or null, numbered 1..n in order with n at most MAX_ATTEMPTS (the protocol's one
    retry), and a `prompt_sha256` equal to the planned prompt's, so a result answers the plan it was run from and
    not an earlier one with the same ids. A planned call may be absent (it is recorded as no response); a duplicate
    or unplanned id, a repeated or out-of-order attempt number, or a foreign prompt hash is refused, never
    overwritten or ignored. The result's `protocol_sha256` must be the frozen protocol on disk; --unbound skips the
    prompt-hash and protocol checks only for the recorded run's own result file (common.LEGACY_UNBOUND_SOURCES),
    and the call log says so (Codex review of PR #52)."""
    if not isinstance(result, dict) or not isinstance(result.get("calls"), list):
        raise SystemExit("parse_generation: the result must be an object with a 'calls' list; nothing on disk was changed")
    by_id: dict[str, dict] = {}
    problems = result_binding_problems(result, unbound)
    for i, c in enumerate(result["calls"]):
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            problems.append(f"calls[{i}]: not an object with a string id")
            continue
        cid = c["id"]
        attempts = c.get("attempts")
        if cid not in planned:
            problems.append(f"calls[{i}]: id {cid!r} is not a planned call")
        elif cid in by_id:
            problems.append(f"calls[{i}]: id {cid!r} appears more than once")
        elif not isinstance(attempts, list) or not all(
                isinstance(a, dict) and isinstance(a.get("attempt"), int) and (a.get("raw") is None
                                                                                or isinstance(a.get("raw"), str))
                for a in attempts):
            problems.append(f"calls[{i}] ({cid}): attempts must be a list of objects with an integer attempt and a "
                            f"string or null raw")
        elif [a["attempt"] for a in attempts] != list(range(1, len(attempts) + 1)) or len(attempts) > MAX_ATTEMPTS:
            problems.append(f"calls[{i}] ({cid}): attempts must be numbered 1..n in order with n <= {MAX_ATTEMPTS}; "
                            f"got {[a['attempt'] for a in attempts]}")
        elif len(attempts) == MAX_ATTEMPTS and not attempt_failed(attempts[0]["raw"]):
            problems.append(f"calls[{i}] ({cid}): attempt 2 recorded although attempt 1 met no retry condition "
                            f"(PROTOCOL.md 3: only an empty response, or one with no line carrying the required "
                            f"keys, is retried); the final attempt would replace a valid first response")
        elif not unbound and c.get("prompt_sha256") != planned[cid]["prompt_sha256"]:
            problems.append(f"calls[{i}] ({cid}): prompt_sha256 {str(c.get('prompt_sha256'))[:12]!r} is not the "
                            f"planned prompt's {planned[cid]['prompt_sha256'][:12]!r}; a result answers one plan "
                            f"(pass --unbound only for a result recorded before the binding existed)")
        else:
            by_id[cid] = c
    if problems:
        raise SystemExit("parse_generation: refusing the result file; nothing on disk was changed:\n  "
                         + "\n  ".join(problems))
    return by_id


def binding_label(unbound: bool) -> str:
    """The `plan_binding` every log entry records."""
    return "prompt_sha256" if not unbound else "none (--unbound: result recorded before the binding existed)"


def derive(by_id: dict[str, dict], calls_meta: dict[str, dict],
           binding: str) -> tuple[list[dict], list[dict], list[dict], dict[str, str]]:
    """The parse itself, pure: (rows in protocol order, format failures, call log, raw response text by file name)
    for a validated result. main writes these; write_manifest.py finalize derives them again from the recorded
    result file and refuses a bundle whose files differ (Codex review of PR #52)."""
    cell_order = {cell_id(s, t): i for i, (s, t) in enumerate(cells())}
    all_rows, failures, log, raw_texts = [], [], [], {}
    for cid, meta in calls_meta.items():  # protocol order: cell order, A before B
        call = by_id.get(cid)
        attempts = call["attempts"] if call else []
        if not attempts:
            # a planned call with no response record is a final, failed call with zero lines: it stays in every
            # denominator that counts calls, and the run's call-level success rate shows it (Codex review of PR #52)
            log.append({"call_id": cid, "arm": meta["arm"], "cell": meta["cell"], "attempt": 0, "is_final": True,
                        "null_return": True, "n_lines": 0, "n_valid": 0, "n_invalid": 0, "n_control": 0,
                        "n_noncontrol": 0, "expected_lines": ROWS_PER_CALL, "expected_controls": CONTROLS_PER_CALL,
                        "reasons": {}, "status": "no_response_recorded", "plan_binding": binding,
                        "prompt_sha256": meta["prompt_sha256"]})
            continue
        for a in attempts:
            raw = a.get("raw")
            raw_texts[f"{cid}__attempt{a['attempt']}.txt"] = raw if raw is not None else ""
        for idx, a in enumerate(attempts):
            is_final = idx == len(attempts) - 1
            lines = lines_of(a.get("raw"))
            reasons = Counter()
            rows = []
            for li, line in enumerate(lines):
                row, reason = validate_line(line)
                reasons[reason] += 1
                if row is not None:
                    rows.append({"id": f"{cid}__L{li + 1:02d}", "call_id": cid, "arm": meta["arm"],
                                 "specialty": meta["specialty"], "swap_type": meta["swap_type"],
                                 "cell": meta["cell"], "cell_index": cell_order[meta["cell"]], "line_index": li + 1,
                                 "attempt": a["attempt"], "clinical_term": row["clinical_term"],
                                 "patient_term": row["patient_term"], "template": row["template"],
                                 "control": row["control"],
                                 "control_faithful": control_is_faithful(row) if row["control"] == "negative" else None,
                                 "prompt_sha256": meta["prompt_sha256"]})
                elif is_final:
                    failures.append({"call_id": cid, "arm": meta["arm"], "cell": meta["cell"], "attempt": a["attempt"],
                                     "line_index": li + 1, "reason": reason, "line": line,
                                     "prompt_sha256": meta["prompt_sha256"]})
            n_ctrl = sum(1 for r in rows if r["control"] == "negative")
            log.append({"call_id": cid, "arm": meta["arm"], "cell": meta["cell"], "attempt": a["attempt"],
                        "is_final": is_final, "null_return": bool(a.get("null_return")), "n_lines": len(lines),
                        "n_valid": len(rows), "n_invalid": len(lines) - len(rows), "n_control": n_ctrl,
                        "n_noncontrol": len(rows) - n_ctrl, "expected_lines": ROWS_PER_CALL,
                        "expected_controls": CONTROLS_PER_CALL, "reasons": dict(reasons),
                        "status": "ok" if rows else "failed", "plan_binding": binding,
                        "prompt_sha256": meta["prompt_sha256"]})
            if is_final:
                all_rows.extend(rows)
    return all_rows, failures, log, raw_texts


def main(result_path: str, replace: bool = False, unbound: bool = False) -> None:
    result = json.loads(resolve_input(result_path, "parse_generation").read_text(encoding="utf-8"))
    calls_meta = {c["id"]: c for c in load_calls()["calls"]}  # every prompt verified against its stored hash
    by_id = validate_result(result, calls_meta, unbound)  # checked in full before any previous output is removed
    gen_dir = PILOT / "generated"
    raw_dir = gen_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stale = previous_outputs(gen_dir)
    if stale and not replace:
        raise SystemExit(f"parse_generation: {len(stale)} file(s) from a previous parse exist under generated/ "
                         f"(first: {stale[0].relative_to(PILOT)}); pass --replace to delete them before parsing")
    for p in stale:
        p.unlink()
    if stale:
        print(f"parse_generation: --replace removed {len(stale)} file(s) from the previous parse")
    all_rows, failures, log, raw_texts = derive(by_id, calls_meta, binding_label(unbound))
    for name, text in raw_texts.items():
        (raw_dir / name).write_text(text, encoding="utf-8")
    for cid in calls_meta:  # one file per planned call, empty for a call with no response
        write_jsonl(gen_dir / f"{cid}.jsonl", [r for r in all_rows if r["call_id"] == cid])
    write_jsonl(gen_dir / "all_rows.jsonl", all_rows)
    write_jsonl(gen_dir / "format_failures.jsonl", failures)
    write_jsonl(PILOT / "call_log.jsonl", log)
    finals = [e for e in log if e.get("is_final")]
    print(f"calls={len(calls_meta)} attempts={len(log)} retried={sum(1 for e in log if not e.get('is_final'))} "
          f"final_lines={sum(e['n_lines'] for e in finals)} valid_rows={len(all_rows)} "
          f"failures={len(failures)} calls_with_zero_valid={sum(1 for e in finals if e['n_valid'] == 0)} "
          f"no_response={sum(1 for e in finals if e['status'] == 'no_response_recorded')}")


if __name__ == "__main__":
    main(sys.argv[1], replace="--replace" in sys.argv[2:], unbound="--unbound" in sys.argv[2:])
