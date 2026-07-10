"""Pre-registered statistical rigor over the collector output (urgency_shift.json).

Implements the confirmatory analysis rules fixed in advance by
docs/preregistration_tierB.md, which the descriptive collector summary does not
enforce. The collector counts every row; this script counts *phrases*. Three
things separate a defensible estimate from the raw tallies:

1. DEDUPE BY PHRASE. A re-traced phrase lands as several rows that share the
   same clinical_prompt. Pooling those as independent observations is
   pseudoreplication: it shrinks intervals on data that carry no new
   information. Every phrase collapses to one record (mean penalty across its
   rows; a single flip label by majority vote) BEFORE any pooled statistic, and
   the row/phrase gap is reported so the shrinkage that dedupe removes is
   visible rather than silent.

2. CLUSTER intervals. The mean-penalty CI resamples phrases, not rows (the
   cluster bootstrap; cluster = clinical_prompt), so re-traced phrases can never
   inflate precision. The downgrade-rate CI is Clopper-Pearson exact (the beta
   inverse, math only — no scipy), which keeps nominal coverage at the small
   flip counts these models produce, where a normal approximation would not.

3. MULTIPLICITY. The per-model sign test (downgrades vs upgrades, two-sided
   exact) is Benjamini-Hochberg adjusted across models, so a per-model claim
   carries the false-discovery cost of having asked the question four times.
   Raw and adjusted p-values are both reported.

No medical vocabulary appears here: phrases and tier labels arrive as data from
the collector rows.

Usage:
  python scripts/urgency_shift.py --out urgency_shift.json     # collector first
  python scripts/paired_stats_rigor.py --rows urgency_shift.json
      [--models gemma-2-2b qwen3-4b ...] [--boot 5000] [--seed 7]
      [--out paired_stats_rigor.json]
"""

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

# Non-flip rows carry flip_class None; represent that as an explicit label so a
# phrase's flip status survives the categorical majority vote intact.
_NONFLIP = "none"
# Deterministic, hypothesis-CONSERVATIVE tie-break for the phrase label vote:
# a tie never manufactures a directional flip (prefer no-flip, then the
# non-directional classes, and prefer upgrade over downgrade so ties cannot
# inflate the asymmetry the study is testing for).
_TIE_ORDER = [_NONFLIP, "uninformative", "lateral", "upgrade", "downgrade"]


def load_rows(path):
    """Read the collector bundle and return its flat row list.

    Amendment 1 (pre-registered): rows the collector flagged as Tier B
    confirmatory holdout are excluded from every interim analysis this
    script produces. The holdout is analyzed exactly once, after the
    collection week, against the pre-registered endpoints.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["rows"]
    kept = [r for r in rows if r.get("tierb_split") != "holdout"]
    excluded = len(rows) - len(kept)
    if excluded:
        print(f"Amendment 1: excluded {excluded} Tier B holdout rows from interim analysis")
    return kept


def _phrase_label(group):
    """Collapse a phrase's rows to one flip label by majority vote.

    Re-traces of the same stimulus almost always agree; the tie-break only
    fires on genuine ambiguity and is documented (see ``_TIE_ORDER``)."""
    labels = [(r.get("flip_class") if r.get("flipped") else _NONFLIP) for r in group]
    counts = Counter(labels)
    top = max(counts.values())
    tied = [lab for lab, c in counts.items() if c == top]
    for candidate in _TIE_ORDER:
        if candidate in tied:
            return candidate
    return sorted(tied)[0]


def dedupe_by_phrase(model_rows):
    """Collapse rows sharing a clinical_prompt into one record per phrase.

    Returns a list of dicts: ``phrase``, ``penalty`` (mean of the numeric
    language_penalty rows, or None if none are numeric) and ``label`` (the
    majority flip class, with ``_NONFLIP`` for phrases that do not flip)."""
    groups = defaultdict(list)
    for r in model_rows:
        groups[r["clinical_prompt"]].append(r)
    records = []
    for phrase in sorted(groups):
        group = groups[phrase]
        pens = [r["language_penalty"] for r in group
                if isinstance(r.get("language_penalty"), (int, float))]
        records.append({
            "phrase": phrase,
            "penalty": (sum(pens) / len(pens)) if pens else None,
            "label": _phrase_label(group),
        })
    return records


def cluster_bootstrap_ci(values, rng, n_boot):
    """Mean and percentile 95% CI, resampling clusters (the passed values are
    already one-per-cluster phrase means, so this is the cluster bootstrap)."""
    if not values:
        return None
    n = len(values)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return {
        "mean": round(sum(values) / n, 4),
        "ci95": [round(means[int(0.025 * n_boot)], 4),
                 round(means[int(0.975 * n_boot)], 4)],
        "n_phrases": n,
    }


# --- regularized incomplete beta + its inverse (Clopper-Pearson support) -----
# Numerical Recipes continued-fraction evaluation of I_x(a, b); math.lgamma is
# stdlib. The interval endpoints then invert I_x by bisection, which is monotone
# and needs no derivative — robust for the small counts these flip tallies give.

def _betacf(a, b, x):
    maxit, eps, fpmin = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def reg_incomplete_beta(a, b, x):
    """I_x(a, b), the regularized incomplete beta function, on x in [0, 1]."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_ppf(p, a, b):
    """Inverse of I_x(a, b) in x: solve reg_incomplete_beta(a, b, x) = p."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if reg_incomplete_beta(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def clopper_pearson(k, n, alpha=0.05):
    """Exact (Clopper-Pearson) 95% CI for k successes in n, endpoints in [0, 1].

    Returns None when n == 0. Degenerate tails (k == 0 or k == n) pin the
    corresponding endpoint at 0 or 1 rather than evaluating an undefined beta."""
    if n == 0:
        return None
    lo = 0.0 if k == 0 else beta_ppf(alpha / 2.0, k, n - k + 1)
    hi = 1.0 if k == n else beta_ppf(1.0 - alpha / 2.0, k + 1, n - k)
    return [round(lo, 4), round(hi, 4)]


def sign_test(k_down, k_up):
    """Two-sided exact sign test: is the down/up split consistent with 50/50?

    Matches scripts/urgency_shift.py so the deduped p is comparable to the
    collector's row-level one. None when there are no directional flips."""
    n = k_down + k_up
    if n == 0:
        return None
    k = min(k_down, k_up)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2.0 * tail), 5)


def benjamini_hochberg(pvals):
    """Benjamini-Hochberg adjusted p-values (q-values) for a {key: p} mapping.

    Keys whose p is None (no directional flips) are passed through as None and
    do not count toward the number of tests. The adjusted values are monotone
    in the raw ranking and never below the raw p."""
    defined = [(k, p) for k, p in pvals.items() if p is not None]
    out = {k: None for k in pvals}
    m = len(defined)
    if m == 0:
        return out
    ordered = sorted(defined, key=lambda kv: kv[1])
    running = 1.0
    for i in range(m - 1, -1, -1):
        rank = i + 1
        running = min(running, ordered[i][1] * m / rank)
        out[ordered[i][0]] = round(min(running, 1.0), 5)
    return out


def analyze(rows, models=None, boot=5000, seed=7):
    """Build the full rigor bundle from collector rows."""
    present = sorted({r["model"] for r in rows})
    models = [m for m in (models or present) if m in present]
    rng = random.Random(seed)

    bundle = {
        "seed": seed,
        "boot": boot,
        "models": models,
        "ci_method_penalty": "cluster bootstrap (percentile 95%), cluster = clinical_prompt phrase",
        "ci_method_downgrade": "clopper-pearson exact 95%",
        "dedupe": "one record per (model, clinical_prompt); mean penalty, majority flip label",
        "per_model": {},
    }

    raw_p = {}
    for model in models:
        model_rows = [r for r in rows if r["model"] == model]
        records = dedupe_by_phrase(model_rows)

        pens = [rec["penalty"] for rec in records if rec["penalty"] is not None]
        pen_rows = sum(1 for r in model_rows
                       if isinstance(r.get("language_penalty"), (int, float)))

        n_flips = sum(1 for rec in records if rec["label"] != _NONFLIP)
        downgrades = sum(1 for rec in records if rec["label"] == "downgrade")
        upgrades = sum(1 for rec in records if rec["label"] == "upgrade")

        p = sign_test(downgrades, upgrades)
        raw_p[model] = p

        bundle["per_model"][model] = {
            "n_rows": len(model_rows),
            "n_unique_phrases": len(records),
            "pseudoreplication_gap": len(model_rows) - len(records),
            "penalty": {
                "n_rows_with_penalty": pen_rows,
                "n_phrases_with_penalty": len(pens),
                **(cluster_bootstrap_ci(pens, rng, boot) or {"mean": None, "ci95": None, "n_phrases": 0}),
            },
            "flips": {
                "n_flips": n_flips,
                "downgrades": downgrades,
                "upgrades": upgrades,
                "downgrade_rate": round(downgrades / n_flips, 4) if n_flips else None,
                "downgrade_rate_ci95": clopper_pearson(downgrades, n_flips),
                "ci_method": "clopper-pearson",
            },
            "sign_test": {
                "downgrades": downgrades,
                "upgrades": upgrades,
                "p_raw": p,
                "p_bh": None,
            },
        }

    bh = benjamini_hochberg(raw_p)
    for model in models:
        bundle["per_model"][model]["sign_test"]["p_bh"] = bh[model]
    bundle["benjamini_hochberg"] = {
        "across": models,
        "n_tests": sum(1 for m in models if raw_p[m] is not None),
        "adjusted": {m: bh[m] for m in models},
    }
    return bundle


def format_summary(bundle):
    """Render the bundle as a plain, declarative text block."""
    lines = []
    lines.append("paired-stats rigor")
    lines.append(f"seed={bundle['seed']}  boot={bundle['boot']}")
    lines.append(f"penalty CI: {bundle['ci_method_penalty']}")
    lines.append(f"downgrade CI: {bundle['ci_method_downgrade']}")
    lines.append("")
    for model in bundle["models"]:
        pm = bundle["per_model"][model]
        pen = pm["penalty"]
        fl = pm["flips"]
        st = pm["sign_test"]
        lines.append(f"{model}")
        lines.append(f"  rows {pm['n_rows']} -> phrases {pm['n_unique_phrases']}"
                     f"  (pseudoreplication gap {pm['pseudoreplication_gap']})")
        if pen["mean"] is not None:
            lines.append(f"  mean penalty  {pen['mean']:+.4f}  {pen['ci95']}"
                         f"  (phrases={pen['n_phrases_with_penalty']}, penalty rows={pen['n_rows_with_penalty']})")
        else:
            lines.append("  mean penalty  --  (no numeric penalty rows)")
        if fl["downgrade_rate"] is not None:
            lines.append(f"  downgrade rate  {fl['downgrades']}/{fl['n_flips']} = "
                         f"{fl['downgrade_rate']:.4f}  {fl['downgrade_rate_ci95']} exact")
        else:
            lines.append("  downgrade rate  --  (no flips)")
        p_raw = "--" if st["p_raw"] is None else f"{st['p_raw']:.5f}"
        p_bh = "--" if st["p_bh"] is None else f"{st['p_bh']:.5f}"
        lines.append(f"  sign test  down {st['downgrades']} vs up {st['upgrades']}"
                     f"  p={p_raw}  BH q={p_bh}")
        lines.append("")
    bh = bundle["benjamini_hochberg"]
    lines.append(f"Benjamini-Hochberg across {bh['n_tests']} model sign tests.")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", default="urgency_shift.json",
                        help="collector output (urgency_shift.json)")
    parser.add_argument("--models", nargs="+", default=None,
                        help="restrict to these model ids (default: all present, sorted)")
    parser.add_argument("--boot", type=int, default=5000,
                        help="cluster bootstrap resamples")
    parser.add_argument("--seed", type=int, default=7,
                        help="fixed RNG seed (deterministic; not system entropy)")
    parser.add_argument("--out", default="paired_stats_rigor.json",
                        help="path for the JSON bundle")
    parser.add_argument("--site", default="../patientwords",
                        help="frontend repo root: also write data/model_stats.json for the "
                             "cross-model comparison page ('' skips)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    rows = load_rows(args.rows)
    bundle = analyze(rows, models=args.models, boot=args.boot, seed=args.seed)
    bundle["source"] = str(args.rows)
    Path(args.out).write_text(json.dumps(bundle, indent=1) + "\n", encoding="utf-8")
    if args.site:
        # site copy for model-evaluations/: same claim-grade numbers plus the
        # models_meta block (backend/features flags) from the exporter payload,
        # so the comparison page renders entirely from committed data
        site_bundle = dict(bundle)
        payload_path = Path(args.site) / "data" / "simulated_scenarios.json"
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            site_bundle["models_meta"] = payload.get("models_meta")
        except (OSError, ValueError):
            site_bundle["models_meta"] = None
        site_path = Path(args.site) / "data" / "model_stats.json"
        site_path.write_text(json.dumps(site_bundle, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site_path}")
    print(format_summary(bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
