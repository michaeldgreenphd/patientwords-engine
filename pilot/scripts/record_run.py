"""Record a Workflow-tool run in manifest.json under runs.<name>: run id, transcript directory, agent counts, and the
model ids the agent transcripts report (evidence of which model served the subagents).

  python3 scripts/record_run.py generation <run_id> <transcript_dir> ['<extra json>'] [--replace]

The directory must be a run's transcripts (journal.jsonl and at least one agent-*.jsonl), or nothing is recorded;
a run already recorded under the name is never written over without --replace (Codex review of PR #52).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import PILOT

MODEL_RE = re.compile(r'"model":"([^"]+)"')


def main(name: str, run_id: str, transcript_dir: str, extra_json: str, replace: bool = False) -> None:
    tdir = Path(transcript_dir)
    journal = tdir / "journal.jsonl"
    transcripts = sorted(tdir.glob("agent-*.jsonl")) if tdir.is_dir() else []
    if not tdir.is_dir() or not journal.exists() or not transcripts:
        raise SystemExit(f"record_run: {tdir} is not a run's transcript directory (it needs journal.jsonl and at "
                         f"least one agent-*.jsonl); nothing was recorded")
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
    m.setdefault("runs", {})[name] = {"run_id": run_id, "transcript_dir": str(tdir), "agent_transcripts": n_transcripts,
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
