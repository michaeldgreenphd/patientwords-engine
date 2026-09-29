"""Join the checker's verdicts to the truth key. Writes checked.jsonl and checker_log.jsonl.

Input: a JSON file {"batches": [{"batch_id", "prompt_sha256", "attempts": [{"attempt", "result": {"verdicts":
[...]} | null}]}]}. A verdict outside {yes, no, unclear}, a duplicate id, or an id outside the batch is logged and
ignored; an item with no usable verdict is recorded as verdict "missing".

  python3 scripts/parse_checker.py <result file> [--replace] [--unbound]

Every checked row and log entry carries `checker_plan_sha256`, the hash of the checker_batches.json the result was
parsed against, so compute_summary.py and write_manifest.py can refuse a checked.jsonl that belongs to another
plan. A previous parse on disk is refused unless --replace is passed: a result as small as {"batches": []} is a
valid file (every planned batch absent, recorded as no response) and must not silently replace a complete parse
(Codex review of PR #52).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import MAX_ATTEMPTS, PILOT, read_jsonl, sha256_file, write_jsonl

VALID = ("yes", "no", "unclear")


def validate_result(result: object, planned: dict[str, str], unbound: bool = False) -> dict[str, dict]:
    """The result contract, checked in full before anything is written: an object with a `batches` list whose
    entries are objects with a string batch_id that is planned and appears exactly once, an `attempts` list of
    objects with a `result` that is an object or null, numbered 1..n in order with n at most MAX_ATTEMPTS, and a
    `prompt_sha256` equal to the planned batch prompt's. A planned batch may be absent (recorded as no response); a
    duplicate or unplanned batch id, a repeated or out-of-order attempt number, or a foreign prompt hash is refused,
    never overwritten or ignored. --unbound skips the hash check only for a result recorded before the binding
    existed, and the checker log says so (Codex review of PR #52)."""
    if not isinstance(result, dict) or not isinstance(result.get("batches"), list):
        raise SystemExit("parse_checker: the result must be an object with a 'batches' list; nothing was written")
    by_id: dict[str, dict] = {}
    problems = []
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
        elif not isinstance(attempts, list) or not all(
                isinstance(a, dict) and isinstance(a.get("attempt"), int)
                and (a.get("result") is None or isinstance(a.get("result"), dict)) for a in attempts):
            problems.append(f"batches[{i}] ({bid}): attempts must be a list of objects with an integer attempt and "
                            f"an object or null result")
        elif [a["attempt"] for a in attempts] != list(range(1, len(attempts) + 1)) or len(attempts) > MAX_ATTEMPTS:
            problems.append(f"batches[{i}] ({bid}): attempts must be numbered 1..n in order with n <= {MAX_ATTEMPTS}; "
                            f"got {[a['attempt'] for a in attempts]}")
        elif not unbound and b.get("prompt_sha256") != planned[bid]:
            problems.append(f"batches[{i}] ({bid}): prompt_sha256 {str(b.get('prompt_sha256'))[:12]!r} is not the "
                            f"planned batch prompt's {planned[bid][:12]!r}; a result answers one plan (pass "
                            f"--unbound only for a result recorded before the binding existed)")
        else:
            by_id[bid] = b
    if problems:
        raise SystemExit("parse_checker: refusing the result file; nothing was written:\n  " + "\n  ".join(problems))
    return by_id


def previous_outputs() -> list[Path]:
    """Files an earlier parse left: never written over unless --replace says so (Codex review of PR #52)."""
    return [p for p in (PILOT / "checked.jsonl", PILOT / "checker_log.jsonl") if p.exists()]


def main(result_path: str, replace: bool = False, unbound: bool = False) -> None:
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    plan_path = PILOT / "checker_batches.json"
    batches = json.loads(plan_path.read_text(encoding="utf-8"))["batches"]
    by_id = validate_result(result, {b["batch_id"]: b["prompt_sha256"] for b in batches}, unbound)
    stale = previous_outputs()
    if stale and not replace:
        raise SystemExit(f"parse_checker: {' and '.join(p.name for p in stale)} from a previous parse exist; pass "
                         f"--replace to write over them (the result file passed validation; nothing was written)")
    plan_sha = sha256_file(plan_path)  # every row and log entry names the plan it was parsed against
    binding = "prompt_sha256" if not unbound else "none (--unbound: result recorded before the binding existed)"
    blind = {x["id"]: x for x in read_jsonl(PILOT / "checker_set.jsonl")}
    truth = read_jsonl(PILOT / "checker_key.jsonl")
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
            n_ok = n_bad = n_dup = n_foreign = 0
            if isinstance(entries, list) and is_final:
                for e in entries:
                    if not isinstance(e, dict):
                        n_bad += 1
                        continue
                    iid, eq = e.get("id"), e.get("equivalent")
                    if iid not in meta["item_ids"]:
                        n_foreign += 1
                    elif eq not in VALID:
                        n_bad += 1
                    elif iid in verdicts:
                        n_dup += 1
                    else:
                        verdicts[iid] = {"verdict": eq, "reason": str(e.get("reason", "")), "batch_id": meta["batch_id"]}
                        n_ok += 1
            log.append({"batch_id": meta["batch_id"], "attempt": a["attempt"], "is_final": is_final,
                        "null_return": res is None, "n_items": len(meta["item_ids"]),
                        "n_entries": len(entries) if isinstance(entries, list) else 0,
                        "n_used": n_ok, "n_invalid_value": n_bad, "n_duplicate_id": n_dup, "n_foreign_id": n_foreign,
                        "status": "ok" if isinstance(entries, list) else "failed", "plan_binding": binding,
                        "checker_plan_sha256": plan_sha})
    checked = []
    for t in truth:
        v = verdicts.get(t["id"], {"verdict": "missing", "reason": "", "batch_id": None})
        checked.append({**t, **blind[t["id"]], **v, "checker_plan_sha256": plan_sha})
    write_jsonl(PILOT / "checked.jsonl", checked)
    write_jsonl(PILOT / "checker_log.jsonl", log)
    counts = {}
    for c in checked:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    print(f"checked.jsonl: {len(checked)} items; verdict counts {counts}; batches={len(batches)} attempts={len(log)}"
          + (f"; --replace wrote over {' and '.join(p.name for p in stale)}" if stale else ""))


if __name__ == "__main__":
    main(sys.argv[1], replace="--replace" in sys.argv[2:], unbound="--unbound" in sys.argv[2:])
