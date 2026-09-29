"""Turn a Workflow-tool journal (journal.jsonl in the run's transcript directory) into the result file the parsers
consume, without the raw text passing through anyone's hands. The journal holds one "started" record per agent
(label "<id> attempt <n>", key, agentId) and one "result" record per finished agent (key, agentId, result).

  python3 scripts/extract_workflow_journal.py generation <journal.jsonl> -> workflow_generation_result.json
  python3 scripts/extract_workflow_journal.py checker    <journal.jsonl> -> workflow_checker_result.json

An agent that started but has no result record is recorded as a null return. Every record type seen is counted so
an unexpected journal shape is visible rather than silently dropped. Two agents carrying one `<id> attempt <n>`
label, or two result records for one agent, would collapse into one attempt and the overwritten response would
leave the provenance unseen, so such a journal is refused before anything is written (Codex review of PR #52).

A label of the form `<id> attempt <n> sha256=<hash>` (workflow scripts generated since the binding was added) yields
the item's `prompt_sha256`, which the parsers check against the plan; a label without it yields null, and such a
result parses only with the parsers' --unbound flag (Codex review of PR #52).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import PILOT

LABEL = re.compile(r"^(?P<id>.+?) attempt (?P<n>\d+)(?: sha256=(?P<sha>[0-9a-f]{64}))?$")


def main(which: str, journal_path: str) -> None:
    started: list[dict] = []
    results: dict[tuple, object] = {}
    types: Counter = Counter()
    repeated_results = []
    for line in Path(journal_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        types[o.get("type")] += 1
        if o.get("type") == "started":
            started.append(o)
        elif o.get("type") == "result":
            k = (o.get("key"), o.get("agentId"))
            if k in results:
                repeated_results.append(k)
            results[k] = o.get("result")
    per_item: dict[str, dict[int, dict]] = {}
    shas: dict[str, set] = {}
    agents_by_label: dict[tuple[str, int], list] = {}
    unlabeled = 0
    for s in started:
        m = LABEL.match(s.get("label") or "")
        if not m:
            unlabeled += 1
            continue
        item_id, n = m.group("id"), int(m.group("n"))
        agents_by_label.setdefault((item_id, n), []).append(s.get("agentId"))
        shas.setdefault(item_id, set()).add(m.group("sha"))
        res = results.get((s.get("key"), s.get("agentId")))
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
    repeated = {f"{i} attempt {n}": a for (i, n), a in agents_by_label.items() if len(a) > 1}
    if repeated or repeated_results:
        raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: agents sharing one label "
                         f"{repeated}; agents with more than one result record {repeated_results}")
    conflicting = {i: sorted(str(x) for x in v) for i, v in shas.items() if len(v) > 1}
    if conflicting:
        raise SystemExit(f"{journal_path}: an item's attempts carry different prompt hashes, which no single run "
                         f"produces: {conflicting}")

    def sha_of(i: str) -> str | None:
        return next(iter(shas[i])) if i in shas else None
    if which == "generation":
        meta = {c["id"]: c for c in json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))["calls"]}
        items = [{"id": i, "arm": meta[i]["arm"], "cell": meta[i]["cell"], "prompt_sha256": sha_of(i),
                  "attempts": [per_item[i][n] for n in sorted(per_item[i])]} for i in meta if i in per_item]
        out = {"source": journal_path, "record_types": dict(types), "unlabeled_agents": unlabeled, "calls": items}
        path = PILOT / "workflow_generation_result.json"
        missing = [i for i in meta if i not in per_item]
    else:
        ids = [b["batch_id"] for b in json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))["batches"]]
        items = [{"batch_id": i, "prompt_sha256": sha_of(i), "attempts": [per_item[i][n] for n in sorted(per_item[i])]}
                 for i in ids if i in per_item]
        out = {"source": journal_path, "record_types": dict(types), "unlabeled_agents": unlabeled, "batches": items}
        path = PILOT / "workflow_checker_result.json"
        missing = [i for i in ids if i not in per_item]
    out["items_without_any_agent"] = missing
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_attempts = sum(len(x["attempts"]) for x in items)
    n_bound = sum(1 for x in items if x["prompt_sha256"])
    print(f"{path.name}: {len(items)} items, {n_attempts} attempts, record types {dict(types)}, "
          f"unlabeled {unlabeled}, missing {missing}, items with a prompt hash {n_bound}"
          + ("" if n_bound == len(items) else " (the parsers need --unbound for the rest)"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
