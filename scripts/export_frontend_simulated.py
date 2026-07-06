"""Merge engine trace outputs into the frontend's Simulated Scenarios section.

Reads (engine repo):
  data/simulated/pairs_<STAMP>.json + .report.json   - batch + cost sidecar
  <trace-dir>/batch_summary.part_*.json              - per-chunk trace summaries
  <trace-dir>/index_NN.html / index_NN.png           - per-pair renders

Writes (frontend repo working tree; review before committing):
  modes/simulated/index_NN.html / index_NN.png
  data/simulated_scenarios.json

Usage:
  python scripts/export_frontend_simulated.py --stamp 20260706T175614Z \
      --frontend ../patientwords [--engine .] [--trace-dir trace_out]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--engine", default=".", help="engine repo root (default: cwd)")
parser.add_argument("--frontend", required=True, help="frontend repo root")
parser.add_argument("--stamp", required=True, help="batch UTC stamp, e.g. 20260706T175614Z")
parser.add_argument("--trace-dir", default=None,
                    help="trace output dir relative to the engine root "
                         "(default: trace_out/pairs_<stamp>, falling back to trace_out)")
args = parser.parse_args()


def tok(label):
    """Logit labels arrive as 'Output \" nap\"' - return the bare token."""
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def top(spread_side):
    entry = (spread_side or [None])[0]
    if not entry:
        return None
    return [tok(entry[0]), entry[1]]


def clean_spread(spread_side):
    """Full candidate list with bare tokens, ordered as traced (desc prob)."""
    return [[tok(label), prob] for label, prob in (spread_side or []) if tok(label)]

ENGINE = Path(args.engine)
FRONTEND = Path(args.frontend)
STAMP = args.stamp

batch_path = ENGINE / f"data/simulated/pairs_{STAMP}.json"
report_path = ENGINE / f"data/simulated/pairs_{STAMP}.report.json"
if args.trace_dir:
    trace_dir = ENGINE / args.trace_dir
else:
    trace_dir = ENGINE / f"trace_out/pairs_{STAMP}"
    if not trace_dir.is_dir():
        trace_dir = ENGINE / "trace_out"

batch = json.loads(batch_path.read_text(encoding="utf-8"))
report = json.loads(report_path.read_text(encoding="utf-8"))

results = {}
graph_model = source_set = mode = backend = None
for part in sorted(trace_dir.glob("batch_summary.part_*.json")):
    summary = json.loads(part.read_text(encoding="utf-8"))
    graph_model = summary.get("graph_model") or graph_model
    source_set = summary.get("source_set") or source_set
    mode = summary.get("mode") or mode
    backend = summary.get("backend") or backend
    for r in summary.get("results", []):
        results[r["index"]] = r

if not results:
    sys.exit("no batch_summary.part_*.json found - pull the engine branch first")

out_modes = FRONTEND / "modes/simulated"
out_modes.mkdir(parents=True, exist_ok=True)

scenarios = []
copied = 0
for index in sorted(results):
    r = results[index]
    pair = batch[index - 1]
    gen = pair.get("generation", {})
    spread = r.get("predictive_spread", {})
    top_c = top(spread.get("clinical"))
    top_p = top(spread.get("patient"))
    probs = r.get("probabilities", {})
    measured = tok(r.get("target_token"))
    intended = (pair.get("target_clinical_token") or "").strip()

    html = trace_dir / f"index_{index:02d}.html"
    png = trace_dir / f"index_{index:02d}.png"
    entry = {
        "index": index,
        "clinical_prompt": r["prompts"]["clinical"],
        "patient_prompt": r["prompts"]["patient"],
        "target_token": measured,
        "intended_target": intended,
        # A measured token that is a leading wordpiece of the intended target
        # (" ant" for " antacid") is normal tokenization. Anything else means
        # the intended anchor fell below the traced logit spread and the
        # measurement anchored on the clinical panel's top prediction.
        "anchor_fallback": bool(
            measured and intended and not intended.lower().startswith(measured.lower())
        ),
        "prob_clinical": probs.get("clinical"),
        "prob_patient": probs.get("patient"),
        "language_penalty": r.get("language_penalty"),
        "top_clinical": top_c,
        "top_patient": top_p,
        "spread_clinical": clean_spread(spread.get("clinical")),
        "spread_patient": clean_spread(spread.get("patient")),
        "flipped": bool(top_c and top_p and top_c[0] != top_p[0]),
        "rationale": gen.get("rationale"),
        "patient_term": gen.get("patient_term"),
        "clinical_term": gen.get("clinical_term"),
        "topics": gen.get("topics", []),
        "screening": r.get("screening"),
    }
    for src, key in ((html, "html"), (png, "png")):
        if src.is_file():
            shutil.copy2(src, out_modes / src.name)
            entry[key] = f"modes/simulated/{src.name}"
            copied += 1
    scenarios.append(entry)

payload = {
    "batch": f"pairs_{STAMP}",
    "generated": {
        "model": report.get("model"),
        "run_timestamp": report.get("run_timestamp"),
        "cost_usd": report.get("cost_usd"),
        "max_spend_usd": report.get("max_spend_usd"),
        "accepted": report.get("accepted"),
        "rejected": report.get("rejected"),
        "rejection_reasons": report.get("rejection_reasons", []),
        "topics": report.get("topics", []),
        "language_register": report.get("language_register"),
        "sidecar": f"data/simulated/pairs_{STAMP}.report.json",
    },
    "traced": {
        "graph_model": graph_model,
        "source_set": source_set,
        "mode": mode,
        "backend": backend,
    },
    "scenarios": scenarios,
}

out_data = FRONTEND / "data/simulated_scenarios.json"
out_data.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"{len(scenarios)} scenarios -> {out_data} ({copied} render files copied)")
