"""Record a Workflow-tool run in manifest.json under runs.<name>: run id, transcript directory, agent counts, and the
model ids the agent transcripts report (evidence of which model served the subagents).

  python3 scripts/record_run.py generation <run_id> <transcript_dir> ['<extra json>'] [--replace]

The directory must be a run's transcripts (journal.jsonl and at least one agent-*.jsonl), or nothing is recorded;
a run already recorded under the name is never written over without --replace. The record is bound to the stage's
recorded result: the directory's name must be the run id (the Workflow tool names it so), and its journal's hash must
be the `source_sha256` of workflow_<stage>_result.json, so an unrelated run's id and model evidence cannot be
recorded as the provenance of the stored responses; `journal_sha256` is recorded and finalize compares it again.
The transcripts are matched to the journal's started agents: every started agent must have its agent-<id>.jsonl
and no transcript may belong to an agent the journal did not start, so one unrelated transcript cannot stand as the
model evidence for every agent; the model ids are counted per agent, and agents whose transcript reports none are
listed for finalize to refuse. The record also carries the hash of workflows/<stage>.workflow.js, the script that
ran, which finalize compares with the file again. The extra JSON may not carry any key the script computes (they are
the evidence),
and every record write clears the manifest's finalization, since a replaced record is unverified until the next
finalize (Codex review of PR #52).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import PILOT, sha256_file

MODEL_RE = re.compile(r'"model":"([^"]+)"')
STAGES = ("generation", "checker")
RESERVED = ("run_id", "transcript_dir", "journal_sha256", "workflow_script_sha256", "agents_started",
            "agent_transcripts", "agents_without_model_id", "journal_record_types", "model_evidence")


def main(name: str, run_id: str, transcript_dir: str, extra_json: str, replace: bool = False) -> None:
    if name not in STAGES:
        raise SystemExit(f"record_run: stage must be one of {list(STAGES)}, not {name!r}; nothing was recorded")
    tdir = Path(transcript_dir)
    journal = tdir / "journal.jsonl"
    transcripts = {p.name[len("agent-"):-len(".jsonl")]: p for p in tdir.glob("agent-*.jsonl")} if tdir.is_dir() else {}
    if not tdir.is_dir() or not journal.exists() or not transcripts:
        raise SystemExit(f"record_run: {tdir} is not a run's transcript directory (it needs journal.jsonl and at "
                         f"least one agent-*.jsonl); nothing was recorded")
    if tdir.name != run_id:
        raise SystemExit(f"record_run: run id {run_id!r} is not the transcript directory's name {tdir.name!r}; the "
                         f"Workflow tool names the directory by run id; nothing was recorded")
    result_path = PILOT / f"workflow_{name}_result.json"
    if not result_path.exists():
        raise SystemExit(f"record_run: {result_path.name} does not exist; extract the {name} journal first; nothing "
                         f"was recorded")
    recorded = json.loads(result_path.read_text(encoding="utf-8")).get("source_sha256")
    journal_sha = sha256_file(journal)
    if recorded != journal_sha:
        raise SystemExit(f"record_run: {journal} (sha256 {journal_sha[:12]}) is not the journal {result_path.name} was "
                         f"extracted from (source_sha256 {str(recorded)[:12]!r}); a run record must describe the run "
                         f"that produced the recorded result (re-extract with --replace if the result predates the "
                         f"binding); nothing was recorded")
    script = PILOT / "workflows" / f"{name}.workflow.js"
    if not script.exists():  # the script that ran is part of the run's record (Codex review of PR #52)
        raise SystemExit(f"record_run: {script} does not exist; the run's workflow script is part of its record; "
                         f"nothing was recorded")
    script_sha = sha256_file(script)
    extra = json.loads(extra_json or "{}")
    if not isinstance(extra, dict) or any(k in RESERVED for k in extra):
        raise SystemExit(f"record_run: the extra JSON must be an object without the computed keys {list(RESERVED)}; "
                         f"got {sorted(extra) if isinstance(extra, dict) else type(extra).__name__}; nothing was recorded")
    path = PILOT / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    if name in m.get("runs", {}) and not replace:
        raise SystemExit(f"record_run: manifest runs.{name} already records run "
                         f"{m['runs'][name].get('run_id')!r}; pass --replace to write over it")
    types = Counter()
    started: list[str] = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            types[o.get("type")] += 1
            if o.get("type") == "started":
                if not isinstance(o.get("agentId"), str) or not o["agentId"]:
                    raise SystemExit(f"record_run: a started record in {journal} has no agentId; the transcripts cannot "
                                     f"be matched to the run's agents; nothing was recorded")
                started.append(o["agentId"])
    # every started agent's transcript, and no other: one unrelated transcript reporting the declared model would
    # otherwise stand as the evidence for every response-producing agent (Codex review of PR #52)
    missing = sorted(set(started) - set(transcripts))
    foreign = sorted(set(transcripts) - set(started))
    if not started or missing or foreign:
        raise SystemExit(f"record_run: the transcripts in {tdir} do not match the journal's started agents "
                         f"({len(started)} started; missing transcripts {missing[:3]}{'...' if len(missing) > 3 else ''}; "
                         f"transcripts of agents the journal did not start {foreign[:3]}"
                         f"{'...' if len(foreign) > 3 else ''}); nothing was recorded")
    models = Counter()
    without = []
    for agent_id in started:
        found = MODEL_RE.findall(transcripts[agent_id].read_text(encoding="utf-8", errors="replace"))
        if not found:
            without.append(agent_id)
        for mm in found:
            models[mm] += 1
    m.setdefault("runs", {})[name] = {**extra,  # the computed evidence last, so nothing in the extras can shadow it
                                       "run_id": run_id, "transcript_dir": str(tdir), "journal_sha256": journal_sha,
                                       "workflow_script_sha256": script_sha,
                                       "agents_started": len(started), "agent_transcripts": len(started),
                                       "agents_without_model_id": without,
                                       "journal_record_types": dict(types),
                                       "model_evidence": {"model_strings_in_transcripts": dict(models),
                                                          "note": "counts of \"model\":\"...\" strings across the "
                                                                  "started agents' transcripts; API response records"}}
    cleared = m.get("finalized_utc") is not None or "output_hashes" in m
    m["finalized_utc"] = None  # a replaced record is unverified until the next finalize (Codex review of PR #52)
    m.pop("output_hashes", None)
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest runs.{name}: {len(started)} agents with transcripts, models {dict(models)}, "
          f"agents without a model id {without}, journal {dict(types)}"
          + ("; finalization cleared, re-run write_manifest.py finalize" if cleared else ""))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], next((a for a in sys.argv[4:] if not a.startswith("--")), "{}"),
         replace="--replace" in sys.argv[4:])
