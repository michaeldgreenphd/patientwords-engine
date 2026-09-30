"""Turn a Workflow-tool journal (journal.jsonl in the run's transcript directory) into the result file the parsers
consume, without the raw text passing through anyone's hands. The journal holds one "started" record per agent
(label "<id> attempt <n>", key, agentId) and one "result" record per finished agent (key, agentId, result).

  python3 scripts/extract_workflow_journal.py generation <journal.jsonl> [--replace] [--allow-missing-results]
      -> workflow_generation_result.json
  python3 scripts/extract_workflow_journal.py checker    <journal.jsonl> [--replace] [--allow-missing-results]
      -> workflow_checker_result.json

An existing result file is never written over without --replace. The plan files are read through common.load_calls
and load_checker_batches, which refuse a plan whose stored prompt hashes are not the hashes of its prompts.

A started agent with no result record at all (a journal truncated before the workflow finished) is not a null
return: the journal is refused unless --allow-missing-results is passed, which leaves those attempts out of the items
(their calls then read as no response) and lists the agents under `agents_without_result_record`; that check comes
before the label is read, so a truncated record with a malformed label is listed too. A started record whose label
is not in the run's form refuses the journal, since every agent of a run is labelled by the workflow script (Codex
review of PR #52). Every record type seen is counted so an unexpected journal shape is visible rather than silently
dropped. Two agents carrying one `<id> attempt <n>`
label, or two result records for one agent, would collapse into one attempt and the overwritten response would
leave the provenance unseen, so such a journal is refused before anything is written; so is one in which two
"started" records reuse one agent id (whatever their keys), or a "started" record lacks key or agentId, since one
agent's response and transcript would then stand for two independent calls (Codex review of PR #52).

A checker result that is not an object (a string that is not JSON, or another value) is kept verbatim as
`raw_return` with its type and counted (`non_object_results`), never folded into a null return; the parser logs it as
a malformed return. The result file records `source_sha256`, the journal's hash, which record_run.py requires of the
transcript directory it records for the stage (Codex review of PR #52).

A label of the form `<id> attempt <n> sha256=<hash> protocol=<hash>` (workflow scripts generated since the bindings
were added) yields the item's `prompt_sha256`, which the parsers check against the plan, and the run's
`protocol_sha256`, which they check against the frozen protocol; every labelled agent of a run carries the same
protocol hash, so differing ones refuse the journal. A label without the hashes yields null, and such a result
parses only with the parsers' --unbound flag, which accepts only the recorded run's own journals (Codex review of
PR #52).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import PILOT, load_calls, load_checker_batches, sha256_file

LABEL = re.compile(r"^(?P<id>.+?) attempt (?P<n>\d+)(?: sha256=(?P<sha>[0-9a-f]{64}))?(?: protocol=(?P<proto>[0-9a-f]{64}))?$")


def extract(which: str, journal_path: str, allow_missing: bool = False) -> dict:
    """The result document a journal yields, pure: nothing is written. main writes it; rederive.py extracts it again
    from the copied journal under workflows/ and refuses a result file that differs, so a result edited while keeping
    its source_sha256 cannot be sealed (Codex review of PR #52)."""
    started: list[dict] = []
    results: dict[tuple, object] = {}
    types: Counter = Counter()
    repeated_results = []
    repeated_agents = []
    seen_agents: set[str] = set()
    for line in Path(journal_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        types[o.get("type")] += 1
        if o.get("type") == "started":
            ident = (o.get("key"), o.get("agentId"))
            if None in ident:  # a result could match no such agent, and its label would read as no response
                raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: a started record lacks "
                                 f"key or agentId ({o.get('label')!r}) (Codex review of PR #52)")
            if o["agentId"] in seen_agents:  # one agent, one transcript: two started records reusing an agent id
                repeated_agents.append(o["agentId"])  # would read one response as two calls (Codex review of PR #52)
            seen_agents.add(o["agentId"])
            started.append(o)
        elif o.get("type") == "result":
            k = (o.get("key"), o.get("agentId"))
            if k in results:
                repeated_results.append(k)
            results[k] = o.get("result")
    per_item: dict[str, dict[int, dict]] = {}
    shas: dict[str, set] = {}
    protos: set = set()
    agents_by_label: dict[tuple[str, int], list] = {}
    no_result: list[dict] = []
    non_text = non_object = 0
    for s in started:
        if (s["key"], s["agentId"]) not in results:
            # absent, not null: the workflow never recorded a result for this agent, whatever its label says
            # (Codex review of PR #52)
            no_result.append({"agent_id": s["agentId"], "label": s.get("label")})
            continue
        m = LABEL.match(s.get("label") or "")
        if not m:  # every agent of a run is labelled in the run's form; anything else is not this run's journal
            raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: a started record's label "
                             f"{s.get('label')!r} is not in the form '<id> attempt <n> [sha256=<hash>] "
                             f"[protocol=<hash>]' (Codex review of PR #52)")
        item_id, n = m.group("id"), int(m.group("n"))
        agents_by_label.setdefault((item_id, n), []).append(s["agentId"])
        shas.setdefault(item_id, set()).add(m.group("sha"))
        protos.add(m.group("proto"))
        res = results[(s["key"], s["agentId"])]
        if which == "generation":
            # the model's raw text is the input to estimand 1; a result that is not text is recorded as no text,
            # never serialized into a response that never existed (Codex review of PR #52)
            text = res if isinstance(res, str) else None
            entry = {"attempt": n, "raw": text, "null_return": res is None, "agent_id": s.get("agentId")}
            if res is not None and text is None:
                entry["unexpected_result_type"] = type(res).__name__
                non_text += 1
            per_item.setdefault(item_id, {})[n] = entry
        else:
            obj = res
            if isinstance(res, str):
                try:
                    obj = json.loads(res)
                except ValueError:
                    obj = None
            entry = {"attempt": n, "result": obj if isinstance(obj, dict) else None, "null_return": res is None,
                     "agent_id": s.get("agentId")}
            if res is not None and not isinstance(obj, dict):
                # a non-JSON string or a non-object value: kept verbatim and counted, never recorded as a null
                # return, which would make a format failure read as no response (Codex review of PR #52)
                entry["raw_return"] = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
                entry["unexpected_result_type"] = type(res).__name__
                non_object += 1
            per_item.setdefault(item_id, {})[n] = entry
    unused = sorted(str(k) for k in set(results) - {(s.get("key"), s.get("agentId")) for s in started})
    if unused:  # a truncated or malformed journal would otherwise read as no response for that item
        raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: {len(unused)} result record(s) "
                         f"have no started agent (first: {unused[0]}) (Codex review of PR #52)")
    repeated = {f"{i} attempt {n}": a for (i, n), a in agents_by_label.items() if len(a) > 1}
    if repeated or repeated_results or repeated_agents:
        raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: agents sharing one label "
                         f"{repeated}; agents with more than one result record {repeated_results}; started records "
                         f"reusing an agent id {repeated_agents}")
    conflicting = {i: sorted(str(x) for x in v) for i, v in shas.items() if len(v) > 1}
    if conflicting:
        raise SystemExit(f"{journal_path}: an item's attempts carry different prompt hashes, which no single run "
                         f"produces: {conflicting}")
    if len(protos) > 1:
        raise SystemExit(f"{journal_path}: the agent labels carry different protocol hashes, which no single run "
                         f"produces: {sorted(str(p) for p in protos)}")
    if no_result and not allow_missing:
        raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: {len(no_result)} started agent(s) "
                         f"have no result record (first: {no_result[0]['label']!r}); the workflow did not finish or "
                         f"the journal is truncated; resume the run, or pass --allow-missing-results to leave those "
                         f"attempts out and list the agents (Codex review of PR #52)")
    protocol = next(iter(protos)) if protos else None

    def sha_of(i: str) -> str | None:
        return next(iter(shas[i])) if i in shas else None
    if which == "generation":
        meta = {c["id"]: c for c in load_calls()["calls"]}
        planned_ids = set(meta)
        items = [{"id": i, "arm": meta[i]["arm"], "cell": meta[i]["cell"], "prompt_sha256": sha_of(i),
                  "attempts": [per_item[i][n] for n in sorted(per_item[i])]} for i in meta if i in per_item]
        out = {"source": journal_path, "source_sha256": sha256_file(Path(journal_path)), "protocol_sha256": protocol,
               "record_types": dict(types), "non_text_results": non_text,
               "agents_without_result_record": no_result, "calls": items}
        missing = [i for i in meta if i not in per_item]
    else:
        ids = [b["batch_id"] for b in load_checker_batches()["batches"]]
        planned_ids = set(ids)
        items = [{"batch_id": i, "prompt_sha256": sha_of(i), "attempts": [per_item[i][n] for n in sorted(per_item[i])]}
                 for i in ids if i in per_item]
        out = {"source": journal_path, "source_sha256": sha256_file(Path(journal_path)), "protocol_sha256": protocol,
               "record_types": dict(types), "non_object_results": non_object,
               "agents_without_result_record": no_result, "batches": items}
        missing = [i for i in ids if i not in per_item]
    out["items_without_any_agent"] = missing
    foreign = sorted(set(per_item) - planned_ids)
    if foreign:  # a misspelled or foreign id would otherwise vanish and its planned item read as no response
        raise SystemExit(f"{journal_path}: refusing the journal; nothing was written: {len(foreign)} labelled "
                         f"agent(s) belong to no planned item (first: {foreign[0]!r}) (Codex review of PR #52)")
    return out


def main(which: str, journal_path: str, replace: bool = False, allow_missing: bool = False) -> None:
    out = extract(which, journal_path, allow_missing)
    path = PILOT / f"workflow_{which}_result.json"
    if path.exists() and not replace:  # a partial extraction must not replace a complete one (Codex review of PR #52)
        raise SystemExit(f"{path.name} exists from a previous extraction; pass --replace to write over it (the journal "
                         f"was read and checked; nothing was written)")
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    items = out["calls" if which == "generation" else "batches"]
    n_attempts = sum(len(x["attempts"]) for x in items)
    n_bound = sum(1 for x in items if x["prompt_sha256"])
    print(f"{path.name}: {len(items)} items, {n_attempts} attempts, record types {out['record_types']}, "
          f"non-text results {out.get('non_text_results', 0)}, non-object results "
          f"{out.get('non_object_results', 0)}, missing {out['items_without_any_agent']}, agents without a result "
          f"record {len(out['agents_without_result_record'])}, items with a prompt hash {n_bound}, protocol "
          f"{str(out['protocol_sha256'])[:12]}"
          + ("" if n_bound == len(items) else " (the parsers need --unbound for the rest)"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], replace="--replace" in sys.argv[3:],
         allow_missing="--allow-missing-results" in sys.argv[3:])
