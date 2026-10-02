"""Join the checker's verdicts to the truth key. Writes checked.jsonl and checker_log.jsonl.

Input: a JSON file {"batches": [{"batch_id", "prompt_sha256", "attempts": [{"attempt", "result": {"verdicts":
[...]} | null}]}]}. A verdict outside {yes, no, unclear}, a reason that is missing or not text, a duplicate id, or
an id outside the batch is logged and ignored (never coerced); an item with no usable verdict is recorded as verdict
"missing". An attempt the extractor recorded with a
`raw_return` (a result that was not an object) is logged as `malformed_return`, distinct from a null return (Codex
review of PR #52).

  python3 scripts/parse_checker.py <result file> [--replace] [--unbound]

Every checked row and log entry carries `checker_plan_sha256`, the hash of the checker_batches.json the result was
parsed against, so compute_summary.py and write_manifest.py can refuse a checked.jsonl that belongs to another
plan. A previous parse on disk is refused unless --replace is passed: a result as small as {"batches": []} is a
valid file (every planned batch absent, recorded as no response) and must not silently replace a complete parse
(Codex review of PR #52).

Under harness version 2 (recorded in checker_batches.json) every answer also carries relation, sentence_natural and
patient_realism. An answer with any of them missing or outside its set is invalid exactly as one with an invalid
verdict or reason is: counted in n_invalid_value, and its item recorded as missing. An answer whose `equivalent`
contradicts its relation (yes with narrower or different, no with same, same_brand or broader) is kept as given and
flagged `inconsistent: true`, counted in n_inconsistent; it is never corrected. checked.jsonl rows carry relation,
sentence_natural, patient_realism and inconsistent (all null for a missing item). A version-1 parse is
byte-identical to the recorded run's.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import (
    CHECKER_V2_FIELDS,
    CHECKER_VERDICTS,
    MAX_ATTEMPTS,
    PILOT,
    checker_attempt_failed,
    load_checker_batches,
    plan_version,
    read_jsonl,
    resolve_input,
    result_binding_problems,
    sha256_file,
    verdict_inconsistent,
    write_jsonl,
)

VALID = CHECKER_VERDICTS


def validate_result(result: object, planned: dict[str, str], unbound: bool = False) -> dict[str, dict]:
    """The result contract, checked in full before anything is written: an object with a `batches` list whose
    entries are objects with a string batch_id that is planned and appears exactly once, an `attempts` list of
    objects with a `result` that is an object or null, numbered 1..n in order with n at most MAX_ATTEMPTS, and a
    `prompt_sha256` equal to the planned batch prompt's. A planned batch may be absent (recorded as no response); a
    duplicate or unplanned batch id, a repeated or out-of-order attempt number, or a foreign prompt hash is refused,
    never overwritten or ignored. The result's `protocol_sha256` must be the frozen protocol on disk; --unbound
    skips the prompt-hash and protocol checks only for the recorded run's own result file
    (common.LEGACY_UNBOUND_SOURCES), and the checker log says so (Codex review of PR #52)."""
    if not isinstance(result, dict) or not isinstance(result.get("batches"), list):
        raise SystemExit("parse_checker: the result must be an object with a 'batches' list; nothing was written")
    by_id: dict[str, dict] = {}
    problems = result_binding_problems(result, unbound, planned)
    for i, b in enumerate(result["batches"]):
        if not isinstance(b, dict) or not isinstance(b.get("batch_id"), str):
            problems.append(f"batches[{i}]: not an object with a string batch_id")
            continue
        bid = b["batch_id"]
        attempts = b.get("attempts")
        if bid not in planned:
            problems.append(f"batches[{i}]: batch_id {bid!r} is not a planned batch")
        elif bid in by_id:
            problems.append(f"batches[{i}]: batch_id {bid!r} appears more than once")
        elif not isinstance(attempts, list) or not attempts or not all(
                isinstance(a, dict) and isinstance(a.get("attempt"), int) and not isinstance(a.get("attempt"), bool)
                and (a.get("result") is None or isinstance(a.get("result"), dict)) for a in attempts):
            # an empty list is not "no response" (an absent batch is), and a boolean is not an attempt number
            # (Codex review of PR #52)
            problems.append(f"batches[{i}] ({bid}): attempts must be a non-empty list of objects with an integer "
                            f"attempt (not a boolean) and an object or null result")
        elif any(null_flag_problem(a, "result") for a in attempts):
            problems.append(f"batches[{i}] ({bid}): "
                            f"{next(p for p in (null_flag_problem(a, 'result') for a in attempts) if p)}")
        elif [a["attempt"] for a in attempts] != list(range(1, len(attempts) + 1)) or len(attempts) > MAX_ATTEMPTS:
            problems.append(f"batches[{i}] ({bid}): attempts must be numbered 1..n in order with n <= {MAX_ATTEMPTS}; "
                            f"got {[a['attempt'] for a in attempts]}")
        elif len(attempts) == MAX_ATTEMPTS and not checker_attempt_failed(attempts[0].get("result")):
            problems.append(f"batches[{i}] ({bid}): attempt 2 recorded although attempt 1 returned a verdict list "
                            f"(PROTOCOL.md 6: only a batch returning nothing is retried)")
        elif not unbound and b.get("prompt_sha256") != planned[bid]:
            problems.append(f"batches[{i}] ({bid}): prompt_sha256 {str(b.get('prompt_sha256'))[:12]!r} is not the "
                            f"planned batch prompt's {planned[bid][:12]!r}; a result answers one plan (pass "
                            f"--unbound only for a result recorded before the binding existed)")
        else:
            by_id[bid] = b
    if problems:
        raise SystemExit("parse_checker: refusing the result file; nothing was written:\n  " + "\n  ".join(problems))
    return by_id


def null_flag_problem(attempt: dict, field: str) -> str | None:
    """Why an attempt's `null_return` does not describe its `field`: a boolean, true exactly when the field is null
    and no non-object return is recorded (`unexpected_result_type`, with `raw_return` holding it verbatim), false
    otherwise (Codex review of PR #52). None when the flag describes the field."""
    flag, unexpected = attempt.get("null_return"), attempt.get("unexpected_result_type")
    if not isinstance(flag, bool):
        return f"attempt {attempt.get('attempt')}: null_return must be a boolean, got {flag!r}"
    if unexpected is not None and (not isinstance(unexpected, str) or not unexpected):
        return f"attempt {attempt.get('attempt')}: unexpected_result_type must be a non-empty string when present"
    if (unexpected is None) != ("raw_return" not in attempt):
        return f"attempt {attempt.get('attempt')}: raw_return and unexpected_result_type must be recorded together"
    expected = attempt.get(field) is None and unexpected is None
    if flag != expected:
        return (f"attempt {attempt.get('attempt')}: null_return {flag} does not describe {field} "
                f"({'null' if attempt.get(field) is None else 'present'}"
                f"{', non-object return ' + unexpected if unexpected else ''})")
    return None


def previous_outputs() -> list[Path]:
    """Files an earlier parse left: never written over unless --replace says so (Codex review of PR #52)."""
    return [p for p in (PILOT / "checked.jsonl", PILOT / "checker_log.jsonl") if p.exists()]


def binding_label(unbound: bool) -> str:
    """The `plan_binding` every log entry records."""
    return "prompt_sha256" if not unbound else "none (--unbound: result recorded before the binding existed)"


def v2_answer_valid(e: dict) -> bool:
    """Whether a version-2 answer carries each further answer (relation, sentence_natural, patient_realism) as one
    of its allowed values."""
    return all(e.get(f) in values for f, values in CHECKER_V2_FIELDS.items())


def derive(by_id: dict[str, dict], batches: list[dict], blind: dict[str, dict], truth: list[dict], binding: str,
           plan_sha: str, *, version: int) -> tuple[list[dict], list[dict]]:
    """The join itself, pure: (checked rows in key order, checker log) for a validated result. main writes these;
    write_manifest.py finalize derives them again from the recorded result file and refuses a bundle whose files
    differ (Codex review of PR #52). `version` is the checker plan's harness version (see the module docstring)."""
    v2 = version >= 2
    verdicts, log = {}, []
    for meta in batches:
        b = by_id.get(meta["batch_id"])
        attempts = b["attempts"] if b else []
        if not attempts:
            log.append({"batch_id": meta["batch_id"], "attempt": 0, "status": "no_response_recorded",
                        "plan_binding": binding, "checker_plan_sha256": plan_sha})
            continue
        for idx, a in enumerate(attempts):
            is_final = idx == len(attempts) - 1
            res = a.get("result")
            entries = res.get("verdicts") if isinstance(res, dict) else None
            n_ok = n_bad = n_dup = n_foreign = n_incons = 0
            if isinstance(entries, list) and is_final:
                for e in entries:
                    if not isinstance(e, dict):
                        n_bad += 1
                        continue
                    iid, eq = e.get("id"), e.get("equivalent")
                    if iid not in meta["item_ids"]:
                        n_foreign += 1
                    elif eq not in VALID or not isinstance(e.get("reason"), str) or (v2 and not v2_answer_valid(e)):
                        n_bad += 1  # a missing or non-text reason is a malformed entry, not a blank (Codex, PR #52)
                    elif iid in verdicts:
                        n_dup += 1
                    elif v2:
                        incons = verdict_inconsistent(eq, e["relation"])  # kept as given, flagged and counted
                        verdicts[iid] = {"verdict": eq, "reason": e["reason"],
                                         **{f: e[f] for f in CHECKER_V2_FIELDS}, "inconsistent": incons,
                                         "batch_id": meta["batch_id"]}
                        n_ok += 1
                        n_incons += incons
                    else:
                        verdicts[iid] = {"verdict": eq, "reason": e["reason"], "batch_id": meta["batch_id"]}
                        n_ok += 1
            log.append({"batch_id": meta["batch_id"], "attempt": a["attempt"], "is_final": is_final,
                        "null_return": res is None and "raw_return" not in a, "malformed_return": "raw_return" in a,
                        "n_items": len(meta["item_ids"]),
                        "n_entries": len(entries) if isinstance(entries, list) else 0,
                        "n_used": n_ok, "n_invalid_value": n_bad, "n_duplicate_id": n_dup, "n_foreign_id": n_foreign,
                        **({"n_inconsistent": n_incons} if v2 else {}),
                        "status": "ok" if isinstance(entries, list) else "failed", "plan_binding": binding,
                        "checker_plan_sha256": plan_sha})
    checked = []
    missing = ({"verdict": "missing", "reason": "", **{f: None for f in CHECKER_V2_FIELDS}, "inconsistent": None,
                "batch_id": None} if v2 else {"verdict": "missing", "reason": "", "batch_id": None})
    for t in truth:
        v = verdicts.get(t["id"], missing)
        checked.append({**t, **blind[t["id"]], **v, "checker_plan_sha256": plan_sha})
    return checked, log


def main(result_path: str, replace: bool = False, unbound: bool = False) -> None:
    result = json.loads(resolve_input(result_path, "parse_checker").read_text(encoding="utf-8"))
    plan_path = PILOT / "checker_batches.json"
    plan = load_checker_batches()  # every prompt verified against its stored hash, the plan against its inputs
    batches = plan["batches"]
    by_id = validate_result(result, {b["batch_id"]: b["prompt_sha256"] for b in batches}, unbound)
    stale = previous_outputs()
    if stale and not replace:
        raise SystemExit(f"parse_checker: {' and '.join(p.name for p in stale)} from a previous parse exist; pass "
                         f"--replace to write over them (the result file passed validation; nothing was written)")
    blind = {x["id"]: x for x in read_jsonl(PILOT / "checker_set.jsonl")}
    truth = read_jsonl(PILOT / "checker_key.jsonl")
    # every row and log entry names the plan it was parsed against
    checked, log = derive(by_id, batches, blind, truth, binding_label(unbound), sha256_file(plan_path),
                          version=plan_version(plan))
    write_jsonl(PILOT / "checked.jsonl", checked)
    write_jsonl(PILOT / "checker_log.jsonl", log)
    counts = {}
    for c in checked:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    n_incons = sum(1 for c in checked if c.get("inconsistent"))
    print(f"checked.jsonl: {len(checked)} items; verdict counts {counts}; batches={len(batches)} attempts={len(log)}"
          + (f"; {n_incons} answer(s) flagged inconsistent" if plan_version(plan) >= 2 else "")
          + (f"; --replace wrote over {' and '.join(p.name for p in stale)}" if stale else ""))


if __name__ == "__main__":
    main(sys.argv[1], replace="--replace" in sys.argv[2:], unbound="--unbound" in sys.argv[2:])
