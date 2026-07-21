"""stress_pairs.json featured block — the home teaser's pick as data (audit M3 tail).

The home page's phrase-dataset teaser re-derives "most consequential" in JS:
consequence = flip*10 + |observed prob gap| (flip = both observed next tokens
present and different), sorted descending with dataset order as the tiebreak
(the JS relies on stable sort), top 5. This script computes that ranking ONCE
and rewrites the site's data/stress_pairs.json as {pairs, featured} — the page
already reads both the bare-list and object shapes, and keeps its own
computation as fallback. Pair content is preserved verbatim; idempotent.
Single writer for the featured block. No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FEATURED_N = 5
METRIC = "flip*10+abs_prob_gap"


def consequence(pair: dict):
    prov = pair.get("provenance") or {}
    if not isinstance(prov, dict):
        prov = {}
    p, c = prov.get("patient") or {}, prov.get("clinical") or {}
    flip = bool(p.get("observed_next_token") and c.get("observed_next_token")
                and p["observed_next_token"] != c["observed_next_token"])
    gap = (abs(c["observed_prob"] - p["observed_prob"])
           if isinstance(p.get("observed_prob"), (int, float))
           and isinstance(c.get("observed_prob"), (int, float)) else 0.0)
    return flip * 10 + gap, flip, gap


def build_featured(pairs: list[dict], n: int = FEATURED_N) -> dict:
    scored = [(i, *consequence(p)) for i, p in enumerate(pairs)]
    # stable sort on -score => dataset order breaks ties, matching the page
    scored.sort(key=lambda t: -t[1])
    rows = []
    for i, score, flip, gap in scored[:n]:
        prov = pairs[i].get("provenance") or {}
        rows.append({"row": i,
                     "source_row": prov.get("source_row") if isinstance(prov, dict) else None,
                     "consequence": round(score, 6),
                     "flip": flip, "gap": round(gap, 6)})
    return {"n": len(rows), "metric": METRIC, "tiebreak": "dataset order",
            "rows": rows}


def rewrap(data) -> dict:
    """List shape -> {pairs, featured}; object shape -> featured refreshed."""
    if isinstance(data, list):
        out = {"pairs": data}
    else:
        out = dict(data)
    out["featured"] = build_featured(out.get("pairs") or [])
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords")
    args = parser.parse_args(argv)
    path = Path(args.site) / "data" / "stress_pairs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"refused: no readable {path} - nothing touched")
        return 3
    out = rewrap(data)
    if not out.get("pairs"):
        print(f"refused: no pairs in {path} - nothing touched")
        return 3
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    top = ", ".join(f"#{r['source_row'] if r['source_row'] is not None else r['row'] + 1}"
                    for r in out["featured"]["rows"])
    print(f"featured {out['featured']['n']} of {len(out['pairs'])} pairs -> {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
