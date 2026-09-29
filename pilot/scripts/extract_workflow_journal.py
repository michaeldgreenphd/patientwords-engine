"""Turn a Workflow-tool journal (journal.jsonl in the run's transcript directory) into the result file the parsers
consume, without the raw text passing through anyone's hands. The journal holds one "started" record per agent
(label "<id> attempt <n>", key, agentId) and one "result" record per finished agent (key, agentId, result).

  python3 scripts/extract_workflow_journal.py generation <journal.jsonl> -> workflow_generation_result.json
  python3 scripts/extract_workflow_journal.py checker    <journal.jsonl> -> workflow_checker_result.json

An agent that started but has no result record is recorded as a null return. Every record type seen is counted so
an unexpected journal shape is visible rather than silently dropped.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import PILOT

LABEL = re.compile(r"^(?P<id>.+?) attempt (?P<n>\d+)$")


def main(which: str, journal_path: str) -> None:
    started, results, types = {}, {}, Counter()
    for line in Path(journal_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        types[o.get("type")] += 1
        if o.get("type") == "started":
            started[(o.get("key"), o.get("agentId"))] = o
        elif o.get("type") == "result":
            results[(o.get("key"), o.get("agentId"))] = o.get("result")
    per_item: dict[str, dict[int, dict]] = {}
    unlabeled = 0
    for k, s in started.items():
        m = LABEL.match(s.get("label") or "")
        if not m:
            unlabeled += 1
            continue
        item_id, n = m.group("id"), int(m.group("n"))
        res = results.get(k)
        if which == "generation":
            text = res if isinstance(res, str) else (json.dumps(res) if res is not None else None)
            per_item.setdefault(item_id, {})[n] = {"attempt": n, "raw": text, "null_return": res is None,
                                                   "agent_id": s.get("agentId")}
        else:
            obj = res
            if isinstance(res, str):
                try:
                    obj = json.loads(res)
                except ValueError:
                    obj = None
            per_item.setdefault(item_id, {})[n] = {"attempt": n, "result": obj if isinstance(obj, dict) else None,
                                                   "null_return": res is None, "agent_id": s.get("agentId")}
    if which == "generation":
        meta = {c["id"]: c for c in json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))["calls"]}
        items = [{"id": i, "arm": meta[i]["arm"], "cell": meta[i]["cell"],
                  "attempts": [per_item[i][n] for n in sorted(per_item[i])]} for i in meta if i in per_item]
        out = {"source": journal_path, "record_types": dict(types), "unlabeled_agents": unlabeled, "calls": items}
        path = PILOT / "workflow_generation_result.json"
        missing = [i for i in meta if i not in per_item]
    else:
        ids = [b["batch_id"] for b in json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))["batches"]]
        items = [{"batch_id": i, "attempts": [per_item[i][n] for n in sorted(per_item[i])]} for i in ids if i in per_item]
        out = {"source": journal_path, "record_types": dict(types), "unlabeled_agents": unlabeled, "batches": items}
        path = PILOT / "workflow_checker_result.json"
        missing = [i for i in ids if i not in per_item]
    out["items_without_any_agent"] = missing
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_attempts = sum(len(x["attempts"]) for x in items)
    print(f"{path.name}: {len(items)} items, {n_attempts} attempts, record types {dict(types)}, "
          f"unlabeled {unlabeled}, missing {missing}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
