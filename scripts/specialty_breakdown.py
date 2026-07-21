"""EXPLORATORY: language penalty broken down by medical specialty.

Is the penalty uniform across specialties, or concentrated where lay idiom is
richest? Groups the published scenario payload by the specialty taxonomy and
reports phrase-deduped mean penalty + downgrade counts per (specialty, model).
Owner-facing decision data (ops/, not the site): not pre-registered, no
multiplicity control across specialties - treat as hypothesis-generating only,
and the payload says so. No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

try:  # imported as scripts.specialty_breakdown (tests) vs run from scripts/ (CLI)
    from scripts.coverage_gaps import topic_lookup
except ImportError:
    from coverage_gaps import topic_lookup

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance


def penalties_by_specialty(map_payload: dict, scenarios: list, urgency_rows: list):
    lookup = topic_lookup(map_payload)

    def spec_of(s):
        t = (s.get("topic") or (s.get("generation") or {}).get("topic") or "").strip().lower()
        return lookup.get(t, ("Other", "Other"))[0]

    downgrades = defaultdict(lambda: defaultdict(int))
    for r in urgency_rows:
        if r.get("flip_class") == "downgrade":
            downgrades[(r.get("batch"), r.get("index"))][r.get("model")] += 1

    # one record per (model, clinical prompt): last measurement wins, matching
    # the rigor script's dedupe unit
    per_key = {}
    for s in scenarios:
        spec = spec_of(s)
        phrase = (s.get("prompts") or {}).get("clinical") or f"{s.get('batch')}#{s.get('batch_index')}"
        models = {"gemma-2-2b": s}
        for mid, m in (s.get("models") or {}).items():
            models[mid] = m
        for mid, m in models.items():
            pc, pp = m.get("prob_clinical"), m.get("prob_patient")
            if pc is None or pp is None:
                continue
            per_key[(mid, phrase)] = {
                "spec": spec, "penalty": pp - pc,
                "downgrade": downgrades.get((s.get("batch"), s.get("batch_index")), {}).get(mid, 0) > 0,
            }

    agg = defaultdict(lambda: defaultdict(lambda: {"n": 0, "sum": 0.0, "downgrades": 0}))
    for (mid, _phrase), rec in per_key.items():
        cell = agg[rec["spec"]][mid]
        cell["n"] += 1
        cell["sum"] += rec["penalty"]
        cell["downgrades"] += 1 if rec["downgrade"] else 0
    table = {}
    for spec, models in agg.items():
        table[spec] = {}
        for mid, c in models.items():
            table[spec][mid] = {"n_phrases": c["n"],
                                "mean_penalty": round(c["sum"] / c["n"], 4),
                                "downgrades": c["downgrades"]}
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--map", default="data/specialty_map.draft.json")
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--min-n", type=int, default=10,
                        help="suppress (specialty, model) cells under this phrase count")
    parser.add_argument("--out", default="ops/specialty_breakdown.json")
    args = parser.parse_args()

    map_payload = json.loads(Path(args.map).read_text(encoding="utf-8"))
    site = Path(args.site)
    scenarios = json.loads((site / "data" / "simulated_scenarios.json")
                           .read_text(encoding="utf-8")).get("scenarios", [])
    urgency = json.loads((site / "data" / "urgency_shift.json")
                         .read_text(encoding="utf-8")).get("rows", [])
    table = penalties_by_specialty(map_payload, scenarios, urgency)
    shown = {spec: {mid: cell for mid, cell in models.items() if cell["n_phrases"] >= args.min_n}
             for spec, models in table.items()}
    shown = {spec: models for spec, models in shown.items() if models}
    payload = {
        "_": ("EXPLORATORY, owner decision data - phrase-deduped per (specialty, model), no "
              "multiplicity control across specialties, cells under min_n suppressed. "
              "Hypothesis-generating only; nothing here publishes without pre-registration."),
        "min_n": args.min_n,
        "specialties": dict(sorted(shown.items())),
    }
    payload["_provenance"] = provenance("specialty_breakdown.py")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"specialty breakdown: {len(shown)} specialties with cells >= n{args.min_n} -> {out}")


if __name__ == "__main__":
    main()
