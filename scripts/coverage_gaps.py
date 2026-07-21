"""Corpus coverage by specialty x care-urgency tier, with generation steering.

Joins the specialty taxonomy (data/specialty_map.draft.json) against the
published scenario payload and urgency rows, and reports where the corpus is
thin: scenarios per specialty, and per (specialty, clinical-side tier). The
`steer_topics` block lists topic strings from the thinnest specialties in the
map's own vocabulary, ready to paste into a generation fire's `topics` param -
the taxonomy drives sampling instead of just labeling it. Analysis only;
no medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance


def topic_lookup(map_payload: dict) -> dict:
    lookup = {}
    for spec, subs in map_payload.get("specialties", {}).items():
        for sub, topics in subs.items():
            for t in topics:
                lookup[t] = (spec, sub)
    return lookup


def build(map_payload: dict, scenarios: list, urgency_rows: list, base_model: str,
          steer_n: int, thin_threshold: int):
    lookup = topic_lookup(map_payload)

    def spec_of(topic):
        return lookup.get((topic or "").strip().lower(), ("Other", "Other"))

    per_spec = defaultdict(int)
    tier_matrix = defaultdict(lambda: defaultdict(int))
    tiers_by_key = {}
    for r in urgency_rows:
        if r.get("model") == base_model and r.get("tier_top_clinical") is not None:
            tiers_by_key[(r.get("batch"), r.get("index"))] = r["tier_top_clinical"]
    for s in scenarios:
        spec, _sub = spec_of(s.get("topic") or (s.get("generation") or {}).get("topic"))
        per_spec[spec] += 1
        tier = tiers_by_key.get((s.get("batch"), s.get("batch_index")))
        if tier is not None:
            tier_matrix[spec][str(tier)] += 1

    thin = sorted((sp for sp, n in per_spec.items() if n < thin_threshold and sp != "Other"),
                  key=lambda sp: per_spec[sp])
    steer = {}
    for sp in thin[:steer_n]:
        steer[sp] = sorted({t for t, (s2, _) in lookup.items() if s2 == sp})
    return {
        "_": ("coverage report - counts are corpus composition, not findings. steer_topics "
              "lists the thinnest specialties' topic vocabulary for generation `topics` params."),
        "base_model": base_model,
        "scenarios_total": len(scenarios),
        "per_specialty": dict(sorted(per_spec.items(), key=lambda kv: -kv[1])),
        "tier_matrix": {sp: dict(v) for sp, v in sorted(tier_matrix.items())},
        "thin_threshold": thin_threshold,
        "thin_specialties": thin,
        "steer_topics": steer,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--map", default="data/specialty_map.draft.json")
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--base-model", default="gemma-2-2b")
    parser.add_argument("--thin-threshold", type=int, default=20,
                        help="specialties under this many scenarios count as thin")
    parser.add_argument("--steer-n", type=int, default=4,
                        help="thinnest specialties to emit steering topics for")
    parser.add_argument("--out", default="ops/coverage_gaps.json")
    args = parser.parse_args()

    map_payload = json.loads(Path(args.map).read_text(encoding="utf-8"))
    site = Path(args.site)
    scenarios = json.loads((site / "data" / "simulated_scenarios.json")
                           .read_text(encoding="utf-8")).get("scenarios", [])
    urgency = json.loads((site / "data" / "urgency_shift.json")
                         .read_text(encoding="utf-8")).get("rows", [])
    payload = build(map_payload, scenarios, urgency, args.base_model,
                    args.steer_n, args.thin_threshold)
    payload["_provenance"] = provenance("coverage_gaps.py")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    thin = payload["thin_specialties"]
    print(f"coverage: {payload['scenarios_total']} scenarios over "
          f"{len(payload['per_specialty'])} specialties · thin (<{args.thin_threshold}): "
          f"{', '.join(thin) if thin else 'none'} -> {out}")


if __name__ == "__main__":
    main()
