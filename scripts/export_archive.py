"""Flatten the simulated-data archive into analysis-ready CSV + JSON.

Walks every batch in data/simulated/ (pairs_*.json + .report.json sidecars) and
joins each pair with its trace results across every circuit-tracer model that
traced it - gemma-2-2b from trace_out/<batch-stem>/ and the others from
trace_out/<batch-stem>__<model>/. Writes one flat row per (pair x model):
generation provenance, the traced graph_model, screening verdicts,
probabilities, penalties, flips, and clinical-mass metrics (populated only for
the featured model with a transcoder source set). Pairs that no model traced
still get one "untraced" row, so the export is the complete archive, not just
the measured subset. This is the collaborator download that pairs with the
GitHub Release render bundle.

Usage:
  python scripts/export_archive.py [--engine .] [--out archive_export]
  -> archive_export.csv + archive_export.json
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

try:
    from scripts.tierb_split import holdout_phrases, is_holdout, is_tierb_batch, tierb_start_stamp
except ImportError:  # direct invocation from repo root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tierb_split import holdout_phrases, is_holdout, is_tierb_batch, tierb_start_stamp

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--engine", default=".", help="engine repo root (default: cwd)")
parser.add_argument("--out", default="archive_export", help="output path prefix")
args = parser.parse_args()

ENGINE = Path(args.engine)

# The circuit-tracer models. gemma-2-2b keeps the bare trace_out stem; the
# others write to trace_out/<stem>__<model>. Only gemma has a transcoder source
# set, so clinical_mass is meaningful for it alone (nulled for the rest).
MODELS = ["gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b"]
BASE_MODEL = "gemma-2-2b"
FEATURED = {"gemma-2-2b"}

COLUMNS = [
    "batch", "batch_index", "graph_model", "has_features",
    "generated_model", "generated_at", "generation_cost_usd",
    "topic", "topics", "clinical_prompt", "patient_prompt", "patient_term", "clinical_term",
    "intended_target", "rationale", "status", "screening_reason", "probe_extension",
    "measured_target", "prob_clinical", "prob_patient", "language_penalty",
    "top_clinical", "top_patient", "flipped",
    "clinical_mass_clinical", "clinical_mass_patient",
]


def tok(label):
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def model_trace_dir(stem, model):
    return ENGINE / "trace_out" / (stem if model == BASE_MODEL else f"{stem}__{model}")


def read_model_results(stem, model):
    """Return (results_by_index, graph_model) for a model's trace dir, or None."""
    tdir = model_trace_dir(stem, model)
    if not tdir.is_dir():
        return None
    results = {}
    graph_model = None
    for part in sorted(tdir.glob("batch_summary.part_*.json")):
        summary = json.loads(part.read_text(encoding="utf-8"))
        graph_model = summary.get("graph_model") or graph_model
        for r in summary.get("results", []):
            results[r["index"]] = r
    return (results, graph_model or model) if results else None


rows = []
_TIERB_START = tierb_start_stamp(str(ENGINE / "ops/dashboard.json"))
# Phrase-keyed seal (Amendment 3, 2026-07-14): a Tier B holdout phrase is
# withheld wherever it re-appears, including alias/mitigation stems such as
# pairs_<STAMP>_txopus that do not fullmatch the Tier B batch pattern.
_HOLDOUT_PHRASES = holdout_phrases(str(ENGINE / "data/simulated"),
                                   str(ENGINE / "ops/dashboard.json"))
withheld_holdout = 0
for batch_path in sorted(ENGINE.glob("data/simulated/pairs_*.json")):
    if batch_path.name.endswith(".report.json"):
        continue
    stem = batch_path.stem
    report_path = batch_path.with_suffix(".report.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    batch = json.loads(batch_path.read_text(encoding="utf-8"))

    per_model = {m: r for m in MODELS if (r := read_model_results(stem, m)) is not None}

    for i, pair in enumerate(batch, start=1):
        # confirmatory holdout stays sealed: withheld from every public export
        # until the pre-registered endpoint (amendment 1; 2026-07-14 decision).
        # Phrase-keyed so alias/mitigation stems cannot leak a holdout phrase.
        if ((is_tierb_batch(stem, _TIERB_START) and is_holdout(pair.get("top_prompt")))
                or pair.get("top_prompt") in _HOLDOUT_PHRASES):
            withheld_holdout += 1
            continue
        gen = pair.get("generation", {})
        base_row = {
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
            "graph_model": None,
            "has_features": None,
        }
        traced = [m for m in MODELS if m in per_model and i in per_model[m][0]]
        if not traced:
            rows.append({col: base_row.get(col) for col in COLUMNS})
            continue
        for model in traced:
            results, graph_model = per_model[model]
            r = results[i]
            sc = r.get("screening") or {}
            spread = r.get("predictive_spread") or {}
            probs = r.get("probabilities") or {}
            # clinical_mass is only meaningful with a transcoder source set;
            # NullFetcher models report ~0.0, so drop it for non-featured models.
            mass = r.get("clinical_mass") or {} if model in FEATURED else {}
            top_c = (spread.get("clinical") or [[None]])[0][0]
            top_p = (spread.get("patient") or [[None]])[0][0]
            row = dict(base_row)
            row.update({
                "graph_model": graph_model,
                "has_features": model in FEATURED,
                "status": sc.get("status", "measured"),
                "screening_reason": sc.get("reason"),
                "probe_extension": sc.get("probe_extension"),
                "clinical_prompt": (r.get("prompts") or {}).get("clinical", base_row["clinical_prompt"]),
                "patient_prompt": (r.get("prompts") or {}).get("patient", base_row["patient_prompt"]),
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
      f"({traced} traced) -> {csv_path} + {json_path}"
      + (f" ({withheld_holdout} confirmatory-holdout pairs withheld)" if withheld_holdout else ""))
