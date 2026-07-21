"""Evidence-convergence dataset: per-model cumulative penalty estimates batch by batch.

P1 (owner request 2026-07-10). As measurement accumulates, does each model's
mean language penalty stay negative and does its interval tighten? The output
is the data behind the methods-page convergence figure: one point per
(model, cumulative batch prefix), carrying the phrase-deduped mean penalty
with a bootstrap 95% CI and the deduped downgrade/upgrade counts at that n.

Scope rules (recorded in the output):
- rows come from the collector bundle (urgency_shift.json) and use ONLY the
  Tier B exploration split (Amendment 1: holdout rows never enter interim
  analyses; the collector flags them);
- only ``pairs_<STAMP>`` batches enter, ordered by stamp - the primary
  generated stimuli, so cumulative n grows in generation order (alias
  re-trace sets and dialect sweeps are excluded);
- phrase-deduped before any estimate (cluster = clinical_prompt): penalties
  average within a phrase; flip labels take the majority vote with the
  least-alarming tie-break, mirroring paired_stats_rigor.py.

Usage:
  python scripts/convergence_tracker.py [--rows urgency_shift.json]
      [--out data/convergence.json] [--site ../patientwords]
      [--boot 2000] [--seed 7]
"""

import argparse
import json
import random
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance

BATCH_RE = re.compile(r"pairs_(\d{8}T\d{6}Z)")
NONFLIP = "none"
TIE_ORDER = [NONFLIP, "uninformative", "lateral", "upgrade", "downgrade"]
# display order: established models first, then any newly measured model
# (llama, biomistral, olmo, gemma variants) appended automatically as its
# rows land - nothing here needs editing when the matrix grows
PREFERRED_ORDER = ["gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b"]


def phrase_groups(rows):
    """clinical_prompt -> that phrase's rows (fallback key keeps orphans distinct)."""
    groups = {}
    for r in rows:
        key = r.get("clinical_prompt") or f"{r['batch']}#{r['index']}"
        groups.setdefault(key, []).append(r)
    return groups


def phrase_label(group):
    votes = Counter((g.get("flip_class") or NONFLIP) if g.get("flipped") else NONFLIP
                    for g in group)
    top = max(votes.values())
    tied = [lab for lab, c in votes.items() if c == top]
    return next((lab for lab in TIE_ORDER if lab in tied), sorted(tied)[0])


def boot_ci(vals, seed, n_boot):
    if len(vals) < 3:
        return None, None
    rng = random.Random(seed)
    k = len(vals)
    means = sorted(sum(vals[rng.randrange(k)] for _ in range(k)) / k for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def cumulative_points(rows, stamps, seed, n_boot):
    """One estimate per cumulative batch prefix, phrase-deduped."""
    points = []
    for i, stamp in enumerate(stamps):
        prefix = {s for s in stamps[:i + 1]}
        sub = [r for r in rows if BATCH_RE.fullmatch(r["batch"])
               and BATCH_RE.fullmatch(r["batch"]).group(1) in prefix]
        groups = phrase_groups(sub)
        pens = []
        labels = []
        for group in groups.values():
            vals = [g["language_penalty"] for g in group
                    if isinstance(g.get("language_penalty"), (int, float))]
            if vals:
                pens.append(sum(vals) / len(vals))
            labels.append(phrase_label(group))
        if not pens:
            continue
        lo, hi = boot_ci(pens, seed, n_boot)
        points.append({
            "through_batch": f"pairs_{stamp}",
            "stamp": stamp,
            "n_phrases": len(pens),
            "mean_penalty": round(sum(pens) / len(pens), 4),
            "ci95": [None if lo is None else round(lo, 4),
                     None if hi is None else round(hi, 4)],
            "downgrades": labels.count("downgrade"),
            "upgrades": labels.count("upgrade"),
        })
    return points


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", default="urgency_shift.json")
    parser.add_argument("--out", default="data/convergence.json")
    parser.add_argument("--site", default="../patientwords",
                        help="frontend repo root; '' skips the site copy")
    parser.add_argument("--boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    bundle = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    # Phrase-keyed holdout seal + POPULATION-DEF option B (outcome-selected
    # supplementary sets excluded from the confirmatory population), matching
    # scripts/paired_stats_rigor.py.
    _supp = {"pairs_20260713T031252Z", "pairs_20260713T135755Z", "pairs_20260713T050937Z"}
    _held = {r["clinical_prompt"] for r in bundle["rows"] if r.get("tierb_split") == "holdout"}
    rows = [r for r in bundle["rows"]
            if r.get("clinical_prompt") not in _held and r.get("batch") not in _supp]

    stamps = sorted({m.group(1) for r in rows
                     if (m := BATCH_RE.fullmatch(r["batch"]))})
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": ("pairs_* batches only, ordered by generation stamp; phrase-deduped; "
                  "Tier B exploration split only (Amendment 1 holdout excluded); "
                  f"bootstrap 95 pct CI seed {args.seed} x {args.boot}"),
        "models": {},
    }
    present = sorted({r["model"] for r in rows})
    models = ([m for m in PREFERRED_ORDER if m in present]
              + [m for m in present if m not in PREFERRED_ORDER])
    for model in models:
        mrows = [r for r in rows if r["model"] == model]
        pts = cumulative_points(mrows, stamps, args.seed, args.boot)
        if pts:
            payload["models"][model] = {"points": pts}

    payload["_provenance"] = provenance("convergence_tracker.py")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out}")
    if args.site:
        site = Path(args.site) / "data" / "convergence.json"
        site.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site}")
    return 0


if __name__ == "__main__":
    main()
