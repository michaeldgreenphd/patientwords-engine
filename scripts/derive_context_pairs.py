"""Derive context-inoculation pairs from an existing 2panel batch.

For every source pair, emit one derived pair per context condition: the
condition's prefix sentence prepended to BOTH prompts. The prefixes live in
a data file (data/context_prefixes.json) and are register-parallel, so the
comparison isolates whether preceding context of one register shifts the
language penalty of the sentence that follows. Costs nothing to build; the
derived file traces like any other batch.

Pairs are interleaved (source pair 1 under condition A, then condition B,
then source pair 2, ...) so a truncated trace run still yields complete
condition sets for the phrases it reached.

Usage:
  python scripts/derive_context_pairs.py data/simulated/<batch>.json \
      [--prefixes data/context_prefixes.json] [--out <derived>.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("batch", help="Source 2panel batch JSON (array of pair objects)")
parser.add_argument("--prefixes", default="data/context_prefixes.json",
                    help="Context-condition prefix data file")
parser.add_argument("--out", default=None,
                    help="Output path (default: <batch stem>__context.json alongside the source)")
args = parser.parse_args()

batch_path = Path(args.batch)
pairs = json.loads(batch_path.read_text(encoding="utf-8"))
prefix_data = json.loads(Path(args.prefixes).read_text(encoding="utf-8"))
conditions = prefix_data["conditions"]

derived = []
for i, pair in enumerate(pairs, start=1):
    for name, cond in conditions.items():
        prefix = cond["prefix"].rstrip() + " "
        derived.append({
            "top_prompt": prefix + pair["top_prompt"],
            "bottom_prompt": prefix + pair["bottom_prompt"],
            "target_clinical_token": pair.get("target_clinical_token"),
            **({"force_target_tokens": pair["force_target_tokens"]}
               if pair.get("force_target_tokens") else {}),
            "generation": {
                "derived_from": {"batch": batch_path.name, "index": i},
                "context_condition": name,
                "context_prefix": cond["prefix"],
                "prefix_words": len(cond["prefix"].split()),
                "method": "programmatic prefix composition (scripts/derive_context_pairs.py)",
                "source_generation": pair.get("generation") or {},
            },
        })

out_path = Path(args.out) if args.out else batch_path.with_name(batch_path.stem + "__context.json")
out_path.write_text(json.dumps(derived, indent=2) + "\n", encoding="utf-8")

report = {
    "derived_from": batch_path.name,
    "pairs": len(derived),
    "conditions": {name: cond["prefix"] for name, cond in conditions.items()},
    "cost_usd": 0.0,
    "note": "programmatic derivation; no API calls",
}
report_path = out_path.with_suffix(".report.json")
report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(f"{len(derived)} derived pairs -> {out_path}\nreport -> {report_path}")
