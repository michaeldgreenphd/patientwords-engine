"""Record a Workflow-tool run in manifest.json under runs.<name>: run id, transcript directory, agent counts, and the
model ids the agent transcripts report (evidence of which model served the subagents).

  python3 scripts/record_run.py generation <run_id> <transcript_dir> '<extra json>'
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import PILOT

MODEL_RE = re.compile(r'"model":"([^"]+)"')


def main(name: str, run_id: str, transcript_dir: str, extra_json: str) -> None:
    tdir = Path(transcript_dir)
    models = Counter()
    n_transcripts = 0
    for p in sorted(tdir.glob("agent-*.jsonl")):
        n_transcripts += 1
        for m in MODEL_RE.findall(p.read_text(encoding="utf-8", errors="replace")):
            models[m] += 1
    journal = tdir / "journal.jsonl"
    types = Counter()
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            if line.strip():
                types[json.loads(line).get("type")] += 1
    path = PILOT / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    m.setdefault("runs", {})[name] = {"run_id": run_id, "transcript_dir": str(tdir), "agent_transcripts": n_transcripts,
                                       "journal_record_types": dict(types),
                                       "model_evidence": {"model_strings_in_transcripts": dict(models),
                                                          "note": "counts of \"model\":\"...\" strings across the "
                                                                  "subagent transcripts; API response records"},
                                       **json.loads(extra_json or "{}")}
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest runs.{name}: {n_transcripts} transcripts, models {dict(models)}, journal {dict(types)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "{}")
