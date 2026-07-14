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
   exact) is Benjamini-Hochberg adjusted within registration family: the
   confirmatory family is the four pre-registered models; models added after
   registration form a separate exploratory family. Raw and adjusted p-values
   are reported unrounded.

4. POPULATION SCOPE (2026-07-14, referee response). The confirmatory numbers
   use observational generation batches only (batch names matching
   ``pairs_<STAMP>``). Steered runs, outcome-selected sets, hand-built imports,
   QC re-traces and sentinel aliases are excluded from the confirmatory
   population and reported as a labeled all-rows sensitivity instead. Within
   this scope each row is one stimulus, so the phrase collapse is the
   pre-registered paraphrase-averaged path. Holdout exclusion is phrase-keyed:
   any phrase ever flagged holdout is excluded wherever it re-appears,
   including split-less re-run batches.

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
import re
from collections import Counter, defaultdict
from pathlib import Path

# Observational generation batches: the confirmatory population. Everything
# else (steered runs, outcome-selected sets, imports, re-traces, sentinels)
# is sensitivity-only. Mirrors scripts/convergence_tracker.py.
_OBS_RE = re.compile(r"pairs_\d{8}T\d{6}Z")
# The four models fixed by docs/preregistration_tierB.md; later additions are
# exploratory (docs/prereg_divergence_log.md) and get their own BH family.
_PREREG_MODELS = ("gemma-2-2b", "gemma-3-4b-it", "qwen3-1.7b", "qwen3-4b")

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
    # Phrase-keyed exclusion (2026-07-14): a phrase flagged holdout anywhere is
    # excluded everywhere, so re-runs of a holdout phrase in split-less batches
    # cannot leak into interim numbers (found by the independent replication).
    holdout_phrases = {r["clinical_prompt"] for r in rows
                       if r.get("tierb_split") == "holdout"}
    kept = [r for r in rows if r["clinical_prompt"] not in holdout_phrases]
    excluded = len(rows) - len(kept)
    if excluded:
        print(f"Amendment 1: excluded {excluded} rows across "
              f"{len(holdout_phrases)} holdout phrases from interim analysis")
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
            # grouping keys for the pre-specified sensitivity bootstraps
            "batch": group[0].get("batch"),
            "topic": group[0].get("topic"),
            "tier_b": any("tierb_split" in r for r in group),
        })
    return records


def cluster_bootstrap_ci(values, rng, n_boot, alpha_simultaneous=None):
    """Mean, percentile 95% CI and (optionally) a Bonferroni-widened
    simultaneous interval from one bootstrap pass. The passed values are
    already one-per-phrase means, so this is a phrase-level nonparametric
    bootstrap after dedupe (the "cluster" it removes is verbatim re-traces,
    which the dedupe collapses)."""
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
    out = {
        "mean": round(sum(values) / n, 4),
        "ci95": [round(means[int(0.025 * n_boot)], 4),
                 round(means[int(0.975 * n_boot)], 4)],
        "n_phrases": n,
    }
    if alpha_simultaneous:
        lo = max(0, min(n_boot - 1, int((alpha_simultaneous / 2.0) * n_boot)))
        hi = max(0, min(n_boot - 1, int((1.0 - alpha_simultaneous / 2.0) * n_boot)))
        out["ci95_simultaneous"] = [round(means[lo], 4), round(means[hi], 4)]
    return out


def grouped_bootstrap_ci(records, key_field, rng, n_boot):
    """Percentile 95% CI resampling GROUPS (batches or topics) with
    replacement, pooling every phrase mean inside each drawn group. Reported
    as a pre-specified sensitivity beside the phrase-level interval, since
    stimuli are generated in batches from standing topics and near-duplicate
    phrases are not independent."""
    groups = defaultdict(list)
    for rec in records:
        if rec["penalty"] is not None:
            groups[rec.get(key_field) or "_none"].append(rec["penalty"])
    keys = sorted(groups)
    if len(keys) < 2:
        return None
    means = []
    for _ in range(n_boot):
        pooled = []
        for _ in range(len(keys)):
            pooled.extend(groups[keys[rng.randrange(len(keys))]])
        means.append(sum(pooled) / len(pooled))
    means.sort()
    return {"n_groups": len(keys),
            "ci95": [round(means[int(0.025 * n_boot)], 4),
                     round(means[int(0.975 * n_boot)], 4)]}


def near_duplicate_rate(records, threshold=0.8):
    """Share of phrases whose token-set Jaccard similarity to another phrase
    is at or above the threshold. A duplication diagnostic, not a filter: the
    dedupe key is exact string equality, so near-duplicates count as separate
    phrases in every interval above."""
    toks = [frozenset(rec["phrase"].lower().split()) for rec in records]
    n = len(toks)
    flagged = [False] * n
    for i in range(n):
        if flagged[i]:
            continue
        for j in range(i + 1, n):
            a, b = toks[i], toks[j]
            if not a or not b:
                continue
            inter = len(a & b)
            if inter / (len(a) + len(b) - inter) >= threshold:
                flagged[i] = flagged[j] = True
    return {"threshold": threshold, "n_phrases": n,
            "n_near_duplicate": sum(flagged),
            "rate": round(sum(flagged) / n, 4) if n else None}


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
    # Unrounded (2026-07-14): an exact test cannot yield p = 0, and rounding to
    # 5 decimals published exactly that. Display flooring is the renderer's job.
    return min(1.0, 2.0 * tail)


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
        out[ordered[i][0]] = min(running, 1.0)  # unrounded; display flooring is the renderer's job
    return out


def analyze(rows, models=None, boot=5000, seed=7):
    """Build the full rigor bundle from collector rows.

    Confirmatory population: observational ``pairs_<STAMP>`` batches only.
    Everything else enters a labeled all-rows sensitivity, never the headline
    numbers. BH runs within registration family (pre-registered four versus
    post-registration additions)."""
    obs_rows = [r for r in rows if _OBS_RE.fullmatch(r.get("batch", ""))]
    present = sorted({r["model"] for r in obs_rows})
    models = [m for m in (models or present) if m in present]
    rng = random.Random(seed)

    bundle = {
        "seed": seed,
        "boot": boot,
        "models": models,
        "population": "observational pairs_* generation batches only; other row "
                      "sources reported under sensitivity_all_rows",
        "ci_method_penalty": "phrase-level nonparametric bootstrap after dedupe "
                             "(percentile 95%); dedupe collapses re-traces, so no "
                             "cross-phrase dependence is modeled here - see the "
                             "batch/topic sensitivity intervals",
        "ci_method_downgrade": "clopper-pearson exact 95%",
        "sign_test_sidedness": "two-sided",
        "dedupe": "one record per (model, clinical_prompt); mean penalty over its "
                  "stimulus rows (the paraphrase-averaged path), majority flip label",
        "registration": {
            "pre_registered": [m for m in models if m in _PREREG_MODELS],
            "post_registration_exploratory": [m for m in models if m not in _PREREG_MODELS],
        },
        "per_model": {},
    }

    # simultaneous-band width: Bonferroni over the models the site displays
    site_eligible = 0
    records_by_model = {}
    for model in models:
        records_by_model[model] = dedupe_by_phrase(
            [r for r in obs_rows if r["model"] == model])
        n_pen = sum(1 for rec in records_by_model[model] if rec["penalty"] is not None)
        if n_pen >= 30:
            site_eligible += 1
    alpha_sim = 0.05 / max(1, site_eligible)
    bundle["simultaneous_ci"] = {
        "method": "bonferroni percentile", "m": site_eligible, "alpha": alpha_sim}

    raw_p = {}
    for model in models:
        model_rows = [r for r in obs_rows if r["model"] == model]
        records = records_by_model[model]

        pens = [rec["penalty"] for rec in records if rec["penalty"] is not None]
        pen_rows = sum(1 for r in model_rows
                       if isinstance(r.get("language_penalty"), (int, float)))

        n_flips = sum(1 for rec in records if rec["label"] != _NONFLIP)
        downgrades = sum(1 for rec in records if rec["label"] == "downgrade")
        upgrades = sum(1 for rec in records if rec["label"] == "upgrade")

        p = sign_test(downgrades, upgrades)
        raw_p[model] = p

        pen_block = cluster_bootstrap_ci(pens, rng, boot, alpha_simultaneous=alpha_sim) \
            or {"mean": None, "ci95": None, "n_phrases": 0}
        batch_ci = grouped_bootstrap_ci(records, "batch", rng, boot)
        topic_ci = grouped_bootstrap_ci(records, "topic", rng, boot)

        tier_a = [rec["penalty"] for rec in records
                  if rec["penalty"] is not None and not rec["tier_b"]]
        tier_b = [rec["penalty"] for rec in records
                  if rec["penalty"] is not None and rec["tier_b"]]

        bundle["per_model"][model] = {
            "registration": ("pre-registered" if model in _PREREG_MODELS
                             else "post-registration exploratory"),
            "n_rows": len(model_rows),
            "n_unique_phrases": len(records),
            "pseudoreplication_gap": len(model_rows) - len(records),
            "penalty": {
                "n_rows_with_penalty": pen_rows,
                "n_phrases_with_penalty": len(pens),
                **pen_block,
                "ci95_batch_cluster": batch_ci,
                "ci95_topic_cluster": topic_ci,
            },
            "by_generation_tier": {
                "tier_a": {"n_phrases": len(tier_a),
                           "mean": round(sum(tier_a) / len(tier_a), 4) if tier_a else None},
                "tier_b": {"n_phrases": len(tier_b),
                           "mean": round(sum(tier_b) / len(tier_b), 4) if tier_b else None},
            },
            "near_duplicates": near_duplicate_rate(records),
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

    # BH within registration family; a model's published q is its family's q
    fam_pre = {m: raw_p[m] for m in models if m in _PREREG_MODELS}
    fam_post = {m: raw_p[m] for m in models if m not in _PREREG_MODELS}
    bh_pre = benjamini_hochberg(fam_pre)
    bh_post = benjamini_hochberg(fam_post)
    bh = {**bh_pre, **bh_post}
    for model in models:
        bundle["per_model"][model]["sign_test"]["p_bh"] = bh[model]
    bundle["benjamini_hochberg"] = {
        "families": {
            "confirmatory": {"across": sorted(fam_pre),
                             "n_tests": sum(1 for p in fam_pre.values() if p is not None),
                             "adjusted": bh_pre},
            "exploratory": {"across": sorted(fam_post),
                            "n_tests": sum(1 for p in fam_post.values() if p is not None),
                            "adjusted": bh_post},
        },
        # legacy view kept for older consumers: family-wise values, merged
        "across": models,
        "n_tests": sum(1 for m in models if raw_p[m] is not None),
        "adjusted": {m: bh[m] for m in models},
    }

    # all-rows sensitivity: same collapse rules, unrestricted population
    sens = {}
    for model in sorted({r["model"] for r in rows}):
        recs = dedupe_by_phrase([r for r in rows if r["model"] == model])
        pens = [rec["penalty"] for rec in recs if rec["penalty"] is not None]
        sens[model] = {
            "n_unique_phrases": len(recs),
            "mean_penalty": round(sum(pens) / len(pens), 4) if pens else None,
            "downgrades": sum(1 for rec in recs if rec["label"] == "downgrade"),
            "upgrades": sum(1 for rec in recs if rec["label"] == "upgrade"),
        }
    bundle["sensitivity_all_rows"] = {
        "_": "every collector row regardless of batch provenance (steered runs, "
             "outcome-selected sets, imports, re-traces); NOT confirmatory",
        "per_model": sens,
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
        p_raw = "--" if st["p_raw"] is None else f"{st['p_raw']:.3g}"
        p_bh = "--" if st["p_bh"] is None else f"{st['p_bh']:.3g}"
        lines.append(f"  sign test  down {st['downgrades']} vs up {st['upgrades']}"
                     f"  p={p_raw}  BH q={p_bh}  [{pm['registration']}]")
        lines.append("")
    fams = bundle["benjamini_hochberg"]["families"]
    lines.append(f"Benjamini-Hochberg within family: confirmatory "
                 f"{fams['confirmatory']['n_tests']} tests, exploratory "
                 f"{fams['exploratory']['n_tests']} tests.")
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
        # public floor: a model enters the comparison page once it has a real
        # measurement set, not a 3-pair probe (probe rows stay in the full
        # engine bundle above)
        MIN_SITE_PHRASES = 30
        site_bundle["per_model"] = {
            m: v for m, v in bundle["per_model"].items()
            if v["penalty"]["n_phrases"] >= MIN_SITE_PHRASES}
        site_bundle["models"] = sorted(site_bundle["per_model"])
        site_bundle["site_floor_n_phrases"] = MIN_SITE_PHRASES
        # measured-but-below-floor models are listed so the page can show an
        # honest pending row instead of silently omitting them
        site_bundle["below_floor"] = sorted(
            [{"id": m, "n_phrases": v["penalty"]["n_phrases"]}
             for m, v in bundle["per_model"].items()
             if v["penalty"]["n_phrases"] < MIN_SITE_PHRASES],
            key=lambda r: r["id"])
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
