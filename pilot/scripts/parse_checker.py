"""Join the checker's verdicts to the truth key. Writes checked.jsonl and checker_log.jsonl.

Input: a JSON file {"batches": [{"batch_id", "attempts": [{"attempt", "result": {"verdicts": [...]} | null}]}]}.
A verdict outside {yes, no, unclear}, a duplicate id, or an id outside the batch is logged and ignored; an item
with no usable verdict is recorded as verdict "missing".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import PILOT, read_jsonl, write_jsonl

VALID = ("yes", "no", "unclear")


def main(result_path: str) -> None:
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    batches = json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))["batches"]
    blind = {x["id"]: x for x in read_jsonl(PILOT / "checker_set.jsonl")}
    truth = read_jsonl(PILOT / "checker_key.jsonl")
    verdicts, log = {}, []
    by_id = {b["batch_id"]: b for b in result["batches"] if b}
    for meta in batches:
        b = by_id.get(meta["batch_id"])
        attempts = b["attempts"] if b else []
        if not attempts:
            log.append({"batch_id": meta["batch_id"], "attempt": 0, "status": "no_response_recorded"})
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
                        "status": "ok" if isinstance(entries, list) else "failed"})
    checked = []
    for t in truth:
        v = verdicts.get(t["id"], {"verdict": "missing", "reason": "", "batch_id": None})
        checked.append({**t, **blind[t["id"]], **v})
    write_jsonl(PILOT / "checked.jsonl", checked)
    write_jsonl(PILOT / "checker_log.jsonl", log)
    counts = {}
    for c in checked:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    print(f"checked.jsonl: {len(checked)} items; verdict counts {counts}; batches={len(batches)} attempts={len(log)}")


if __name__ == "__main__":
    main(sys.argv[1])
