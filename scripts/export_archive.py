"""Flatten the simulated-data archive into analysis-ready CSV + JSON.

Walks every batch in data/simulated/ (pairs_*.json + .report.json sidecars),
joins each pair with its trace results from trace_out/<batch-stem>/ when
present, and writes one flat row per pair - generation provenance, screening
verdicts, probabilities, penalties, flips, and clinical-mass metrics
included. Pairs that were generated but never traced still get a row
(status "untraced"), so the export is the complete archive, not just the
measured subset.

Usage:
  python scripts/export_archive.py [--engine .] [--out archive_export]
  -> archive_export.csv + archive_export.json
"""

import argparse
import csv
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--engine", default=".", help="engine repo root (default: cwd)")
parser.add_argument("--out", default="archive_export", help="output path prefix")
args = parser.parse_args()

ENGINE = Path(args.engine)

COLUMNS = [
    "batch", "batch_index", "generated_model", "generated_at", "generation_cost_usd",
    "topic", "topics", "clinical_prompt", "patient_prompt", "patient_term", "clinical_term",
    "intended_target", "rationale", "status", "screening_reason", "probe_extension",
    "measured_target", "prob_clinical", "prob_patient", "language_penalty",
    "top_clinical", "top_patient", "flipped",
    "clinical_mass_clinical", "clinical_mass_patient", "graph_model",
]


def tok(label):
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


rows = []
for batch_path in sorted(ENGINE.glob("data/simulated/pairs_*.json")):
    if batch_path.name.endswith(".report.json"):
        continue
    stem = batch_path.stem
    report_path = batch_path.with_suffix(".report.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    batch = json.loads(batch_path.read_text(encoding="utf-8"))

    results = {}
    graph_model = None
    trace_dir = ENGINE / "trace_out" / stem
    parts = sorted(trace_dir.glob("batch_summary.part_*.json")) if trace_dir.is_dir() else []
    for part in parts:
        summary = json.loads(part.read_text(encoding="utf-8"))
        graph_model = summary.get("graph_model") or graph_model
        for r in summary.get("results", []):
            results[r["index"]] = r

    for i, pair in enumerate(batch, start=1):
        gen = pair.get("generation", {})
        r = results.get(i)
        row = {
            "batch": stem,
            "batch_index": i,
            "generated_model": report.get("model"),
            "generated_at": report.get("run_timestamp"),
            "generation_cost_usd": report.get("cost_usd"),
            "topic": gen.get("topic"),
            "topics": " | ".join(report.get("topics", [])),
            "clinical_prompt": pair.get("top_prompt"),
            "patient_prompt": pair.get("bottom_prompt"),
            "patient_term": gen.get("patient_term"),
            "clinical_term": gen.get("clinical_term"),
            "intended_target": pair.get("target_clinical_token"),
            "rationale": gen.get("rationale"),
            "status": "untraced",
            "graph_model": graph_model,
        }
        if r is not None:
            sc = r.get("screening") or {}
            spread = r.get("predictive_spread") or {}
            probs = r.get("probabilities") or {}
            mass = r.get("clinical_mass") or {}
            top_c = (spread.get("clinical") or [[None]])[0][0]
            top_p = (spread.get("patient") or [[None]])[0][0]
            row.update({
                "status": sc.get("status", "measured"),
                "screening_reason": sc.get("reason"),
                "probe_extension": sc.get("probe_extension"),
                "clinical_prompt": (r.get("prompts") or {}).get("clinical", row["clinical_prompt"]),
                "patient_prompt": (r.get("prompts") or {}).get("patient", row["patient_prompt"]),
                "measured_target": tok(r.get("target_token")),
                "prob_clinical": probs.get("clinical"),
                "prob_patient": probs.get("patient"),
                "language_penalty": r.get("language_penalty"),
                "top_clinical": tok(top_c),
                "top_patient": tok(top_p),
                "flipped": (tok(top_c) != tok(top_p)) if top_c and top_p else None,
                "clinical_mass_clinical": mass.get("clinical"),
                "clinical_mass_patient": mass.get("patient"),
            })
        rows.append({col: row.get(col) for col in COLUMNS})

csv_path = Path(args.out + ".csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
json_path = Path(args.out + ".json")
json_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
traced = sum(1 for r in rows if r["status"] != "untraced")
print(f"{len(rows)} pairs across {len({r['batch'] for r in rows})} batches "
      f"({traced} traced) -> {csv_path} + {json_path}")
