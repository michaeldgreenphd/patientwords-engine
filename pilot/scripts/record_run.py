"""Record a Workflow-tool run in manifest.json under runs.<name>: run id, transcript directory, agent counts, and the
model ids the agent transcripts report (evidence of which model served the subagents).

  python3 scripts/record_run.py generation <run_id> <transcript_dir> ['<extra json>'] [--replace]

The directory must be a run's transcripts (journal.jsonl and at least one agent-*.jsonl), or nothing is recorded;
a run already recorded under the name is never written over without --replace. The record is bound to the stage's
recorded result: the directory's name must be the run id (the Workflow tool names it so), and its journal's hash must
be the `source_sha256` of workflow_<stage>_result.json, so an unrelated run's id and model evidence cannot be
recorded as the provenance of the stored responses; `journal_sha256` is recorded and finalize compares it again
(Codex review of PR #52).
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


def main(name: str, run_id: str, transcript_dir: str, extra_json: str, replace: bool = False) -> None:
    if name not in STAGES:
        raise SystemExit(f"record_run: stage must be one of {list(STAGES)}, not {name!r}; nothing was recorded")
    tdir = Path(transcript_dir)
    journal = tdir / "journal.jsonl"
    transcripts = sorted(tdir.glob("agent-*.jsonl")) if tdir.is_dir() else []
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
    path = PILOT / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    if name in m.get("runs", {}) and not replace:
        raise SystemExit(f"record_run: manifest runs.{name} already records run "
                         f"{m['runs'][name].get('run_id')!r}; pass --replace to write over it")
    models = Counter()
    n_transcripts = 0
    for p in transcripts:
        n_transcripts += 1
        for mm in MODEL_RE.findall(p.read_text(encoding="utf-8", errors="replace")):
            models[mm] += 1
    types = Counter()
    for line in journal.read_text(encoding="utf-8").splitlines():
        if line.strip():
            types[json.loads(line).get("type")] += 1
    m.setdefault("runs", {})[name] = {"run_id": run_id, "transcript_dir": str(tdir), "journal_sha256": journal_sha,
                                       "agent_transcripts": n_transcripts,
                                       "journal_record_types": dict(types),
                                       "model_evidence": {"model_strings_in_transcripts": dict(models),
                                                          "note": "counts of \"model\":\"...\" strings across the "
                                                                  "subagent transcripts; API response records"},
                                       **json.loads(extra_json or "{}")}
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest runs.{name}: {n_transcripts} transcripts, models {dict(models)}, journal {dict(types)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], next((a for a in sys.argv[4:] if not a.startswith("--")), "{}"),
         replace="--replace" in sys.argv[4:])
