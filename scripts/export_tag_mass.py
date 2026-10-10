"""Mean attribution-mass shares for the methods Step-3 tagging bars: data/tag_mass.json.

Aggregates, across the measured gemma-2-2b corpus and split by phrasing (clinical vs
patient wording), the mean THREE-WAY split of circuit attribution mass:

  clin   = clinical-tagged feature mass
  off    = off-target (non-clinical) feature mass
  struct = MLP reconstruction-error ("structural"/unexplained residual) mass

Each pair's split is reconstructed from the two committed batch_summary scalars:
  C = clinical_mass[phrasing]   (clinical share of FEATURE mass; features only)
  E = error_share[phrasing]     (error-node share of feature+error mass)
  clin = (1 - E) * C,  off = (1 - E) * (1 - C),  struct = E     (sums to 1).

clinical_mass is aggregated only for calibrated feature models
(feature_models.clinical_mass_publishable: the summary's exact (graph_model, source_set) pair
is in CALIBRATED_FEATURE_SOURCES, today gemma-2-2b with gemmascope-transcoder-16k alone). A NullFetcher summary's mass is ~0, an
artifact; qwen3-4b's summaries name source set transcoder-hp since 2026-10-09, but its labels
are not yet calibrated against gemma-2-2b's, so it stays out until the owner rules. Tier B
holdout pairs are excluded (Amendment 1/3 seal). $0, offline - reads only committed batch_summary parts.

empirical:true is emitted ONLY when real per-pair means are aggregated; when no measured
featured pair is found the committed placeholder (empirical:false) is left untouched, so
the page keeps its illustrative Step-3 bars.

Usage:
  python scripts/export_tag_mass.py [--trace-root trace_out] [--out data/tag_mass.json] \
      [--site ../patientwords]
"""

import argparse
import glob
import json
import sys
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_models import clinical_mass_publishable  # noqa: E402
from tierb_split import SealError, seal_config_error, sealed_pair  # noqa: E402


def three_way(c, e):
    """(clin, off, struct) fractions from clinical-feature share c and error share e."""
    feat = max(0.0, 1.0 - e)
    return feat * c, feat * (1.0 - c), e


def collect(trace_root):
    """{'clinical': [(clin,off,struct),...], 'patient': [...]} over every calibrated
    feature model's (clinical_mass_publishable), non-holdout pair with both scalars for
    that phrasing.

    The holdout seal is tierb_split.sealed_pair (stamp_rows' rule, Amendments 1
    and 3), asked only of rows that would add a value; it raises SealError when
    the rule cannot be evaluated, and main then writes nothing."""
    acc = {"clinical": [], "patient": []}
    for path in glob.glob(str(Path(trace_root) / "*" / "batch_summary*.json")):
        try:
            summ = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not clinical_mass_publishable(summ.get("graph_model"), summ.get("source_set")):
            continue  # NullFetcher artifact, or labels not yet calibrated (qwen3-4b)
        batch = Path(path).parent.name
        for r in summ.get("results", []):
            cmass = r.get("clinical_mass") or {}
            eshare = r.get("error_share") or {}
            triples = {}
            for phrasing in ("clinical", "patient"):
                c, e = cmass.get(phrasing), eshare.get(phrasing)
                if isinstance(c, (int, float)) and isinstance(e, (int, float)):
                    triples[phrasing] = three_way(c, e)
            if not triples:
                continue
            if sealed_pair(batch, r.get("index"), (r.get("prompts") or {}).get("clinical")):
                continue
            for phrasing, triple in triples.items():
                acc[phrasing].append(triple)
    return acc


def mean_shares(triples):
    """Mean (clin, off, struct) as percentages summing to ~100, or None if empty.
    The last share absorbs rounding so the three always sum to exactly 100."""
    if not triples:
        return None
    n = len(triples)
    clin = round(100 * sum(t[0] for t in triples) / n, 1)
    off = round(100 * sum(t[1] for t in triples) / n, 1)
    struct = round(100 - clin - off, 1)
    return {"clin": clin, "off": off, "struct": struct}


def build_payload(acc):
    """The data/tag_mass.json payload, or None when no measured pair was found."""
    clinical = mean_shares(acc["clinical"])
    patient = mean_shares(acc["patient"])
    if clinical is None or patient is None:
        return None
    return {
        "_": ("mean three-way attribution-mass split (clin=clinical-tagged features, "
              "off=off-target features, struct=reconstruction-error residual) per phrasing, "
              "gemma-2-2b only, Tier B holdout excluded; each object sums to ~100"),
        "empirical": True,
        "n_pairs": {"clinical": len(acc["clinical"]), "patient": len(acc["patient"])},
        "clinical": clinical,
        "patient": patient,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--out", default="data/tag_mass.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    try:
        acc = collect(args.trace_root)
    except SealError as exc:
        return seal_config_error(exc)  # exit 2: the publish chain stops
    payload = build_payload(acc)
    if payload is None:
        print("note: no measured featured pairs; leaving the empirical:false placeholder untouched")
        return 0
    payload["_provenance"] = provenance("export_tag_mass.py")
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"tag_mass: clinical {payload['clinical']} · patient {payload['patient']} "
          f"(n clin={payload['n_pairs']['clinical']}, pat={payload['n_pairs']['patient']}) -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "tag_mass.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(text, encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
