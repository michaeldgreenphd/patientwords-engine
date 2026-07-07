"""Score urgency shift: does patient phrasing move predictions toward less urgent care?

Not all prediction flips are equal. A flip from "dermatologist" to "doctor" changes
the urgency of the recommended action; a flip between two synonyms does not. This
scores every traced scenario against an urgency-tier vocabulary (a reviewed JSON
data file - no medical vocabulary lives in this script):

  expected tier   probability-weighted mean tier over the tier-assigned tokens in a
                  side's spread (renormalized; requires >= --min-coverage of spread
                  mass to be tier-assigned, else null)
  tier shift      patient expected tier - clinical expected tier (negative = patient
                  wording points at less urgent care)
  flip class      compares the literal top-1 tokens: downgrade / upgrade / lateral
                  (same tier) / uninformative (either top-1 unassigned)

Usage:
  python scripts/urgency_shift.py [--tiers data/urgency_tiers.draft.json]
      [--frontend ../patientwords] [--min-coverage 0.3] [--out urgency_shift.json]
"""

import argparse
import glob
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--tiers", default="data/urgency_tiers.draft.json")
parser.add_argument("--frontend", default="../patientwords")
parser.add_argument("--min-coverage", type=float, default=0.3,
                    help="minimum share of a spread's mass that must be tier-assigned")
parser.add_argument("--out", default="urgency_shift.json")
args = parser.parse_args()

vocab = json.loads(Path(args.tiers).read_text(encoding="utf-8"))["tokens"]


def tier(token):
    if not token:
        return None
    e = vocab.get(str(token).strip().lower())
    return e["tier"] if e else None


def bare(label):
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def expected_tier(spread, min_cov):
    """Probability-weighted mean tier; None when too little mass is tier-assigned."""
    total = wsum = cov = 0.0
    for token, prob in spread or []:
        total += prob
        tr = tier(token)
        if tr is not None:
            cov += prob
            wsum += prob * tr
    if not total or cov / total < min_cov:
        return None, (cov / total if total else 0.0)
    return wsum / cov, cov / total


def classify(top_c, top_p):
    tc, tp = tier(top_c), tier(top_p)
    if tc is None or tp is None:
        return "uninformative"
    if tp < tc:
        return "downgrade"
    if tp > tc:
        return "upgrade"
    return "lateral"


rows = []


def add(model, name, index, prompts, spread_c, spread_p):
    if not spread_c or not spread_p:
        return
    et_c, cov_c = expected_tier(spread_c, args.min_coverage)
    et_p, cov_p = expected_tier(spread_p, args.min_coverage)
    top_c = spread_c[0][0] if spread_c else None
    top_p = spread_p[0][0] if spread_p else None
    flipped = bool(top_c and top_p and top_c != top_p)
    rows.append({
        "model": model, "batch": name, "index": index,
        "clinical_prompt": (prompts or {}).get("clinical"),
        "top_clinical": top_c, "top_patient": top_p,
        "tier_top_clinical": tier(top_c), "tier_top_patient": tier(top_p),
        "flipped": flipped,
        "flip_class": classify(top_c, top_p) if flipped else None,
        "expected_tier_clinical": None if et_c is None else round(et_c, 3),
        "expected_tier_patient": None if et_p is None else round(et_p, 3),
        "tier_shift": None if (et_c is None or et_p is None) else round(et_p - et_c, 3),
        "coverage": [round(cov_c, 2), round(cov_p, 2)],
    })


# site payload (bare-token spreads, per model)
site = Path(args.frontend) / "data/simulated_scenarios.json"
if site.is_file():
    payload = json.loads(site.read_text(encoding="utf-8"))
    for s in payload.get("scenarios", []):
        for mid, m in (s.get("models") or {}).items():
            add(mid, s.get("batch"), s.get("batch_index"),
                {"clinical": s.get("clinical_prompt")},
                m.get("spread_clinical"), m.get("spread_patient"))

# engine trace_out summaries not yet published (labels need stripping)
seen = {(r["model"], r["batch"], r["index"]) for r in rows}
for part in sorted(glob.glob("trace_out/pairs_*/batch_summary.part_*.json")):
    run_dir = Path(part).parent.name
    stem, _, model_suffix = run_dir.partition("__")
    summary = json.loads(Path(part).read_text(encoding="utf-8"))
    model = summary.get("graph_model") or model_suffix or "gemma-2-2b"
    for r in summary.get("results", []):
        if (model, stem, r["index"]) in seen:
            continue
        sp = r.get("predictive_spread") or {}
        clean = lambda side: [[bare(t), p] for t, p in (sp.get(side) or []) if bare(t)]
        add(model, stem, r["index"], r.get("prompts"), clean("clinical"), clean("patient"))

flips = [r for r in rows if r["flipped"]]
down = [r for r in flips if r["flip_class"] == "downgrade"]
up = [r for r in flips if r["flip_class"] == "upgrade"]
shifts = [r["tier_shift"] for r in rows if r["tier_shift"] is not None]

summary = {
    "measurements": len(rows),
    "flips": len(flips),
    "flip_classes": {
        "downgrade": len(down), "upgrade": len(up),
        "lateral": sum(1 for r in flips if r["flip_class"] == "lateral"),
        "uninformative": sum(1 for r in flips if r["flip_class"] == "uninformative"),
    },
    "mean_tier_shift": round(sum(shifts) / len(shifts), 4) if shifts else None,
    "tier_shift_n": len(shifts),
    "per_model": {},
}
for model in sorted({r["model"] for r in rows}):
    mr = [r for r in rows if r["model"] == model]
    ms = [r["tier_shift"] for r in mr if r["tier_shift"] is not None]
    mf = [r for r in mr if r["flipped"]]
    summary["per_model"][model] = {
        "n": len(mr), "flips": len(mf),
        "downgrades": sum(1 for r in mf if r["flip_class"] == "downgrade"),
        "upgrades": sum(1 for r in mf if r["flip_class"] == "upgrade"),
        "mean_tier_shift": round(sum(ms) / len(ms), 4) if ms else None,
    }

Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n",
                          encoding="utf-8")
print(json.dumps(summary, indent=1))
print(f"\nDowngrade flips ({len(down)}):")
for r in sorted(down, key=lambda r: (r["tier_top_patient"] or 0) - (r["tier_top_clinical"] or 0))[:20]:
    print(f"  [{r['model']}] {r['batch']}#{r['index']}: "
          f"{r['top_clinical']!r}(t{r['tier_top_clinical']}) -> {r['top_patient']!r}(t{r['tier_top_patient']}) | "
          f"{(r['clinical_prompt'] or '')[:56]}")
print(f"-> {args.out}")
