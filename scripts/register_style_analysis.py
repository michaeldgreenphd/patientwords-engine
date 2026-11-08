#!/usr/bin/env python3
"""Style-vs-vocabulary sub-study: the registered analysis of docs/preregistration_advice_register_style.md.

Exploratory relative to the advice arm's registered endpoints. Reads the committed archives of files A
(`stimuli_20261108T014809Z`, clinical vs careful lay) and B (`stimuli_20261108T014810Z`, clinical vs colloquial)
under `data/advice/` and computes, per situation x model (tier ranks self_care 0 < routine 1 < urgent 2 < emergency 3):

  vocab = rank(A.patient) - rank(A.clinical)          contrast 2, D(careful lay, clinical)
  style = (rank(B.patient) - rank(B.clinical)) - vocab contrast 1, D(colloquial, careful lay)
  smv   = style - vocab                                contrast 3, style minus vocabulary

Tests: an exact two-sided sign test within each model (ties dropped and counted); pooled, each situation's
majority sign across the models that measured it (ties toward zero; zero labels dropped and counted) and an exact
two-sided sign test over situations; Holm over the three pooled tests. Sensitivity: the second judge, each model
alone, clinical test-retest (exact agreement, linear and quadratic weighted kappa). Added, not registered: the
three contrasts with every unit dropped that involves a reply stopped for length or empty.

Analysis choices the prereg leaves open are recorded in docs/prereg_divergence_log.md (2026-11-08) and were
fixed before any contrast was computed. Report: docs/exploratory/register_style_results_20261108.md.

    python scripts/register_style_analysis.py [--data-dir data/advice] [--out results.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path
from typing import Any

RANK = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
FILE_A = "stimuli_20261108T014809Z"
FILE_B = "stimuli_20261108T014810Z"
PRIMARY = "claude-haiku-4-5"
SECOND = "anthropic:claude-haiku-5-5"
CONTRASTS = ("style", "vocab", "smv")
DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "advice"

Key = tuple[str, str, str]  # (model, stimulus_id, arm)


def binom_two_sided(k: int, n: int) -> float | None:
    """Exact two-sided sign-test p for k successes of n at p = 0.5 (None when n is 0)."""
    if n == 0:
        return None
    k = min(k, n - k)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def sign_test(values: list[int]) -> dict[str, Any]:
    pos = sum(v > 0 for v in values)
    neg = sum(v < 0 for v in values)
    return {"n": len(values), "pos": pos, "neg": neg, "ties": len(values) - pos - neg,
            "p": binom_two_sided(pos, pos + neg)}


def holm(ps: list[float | None]) -> list[float | None]:
    """Holm step-down adjusted p-values; None entries stay None and do not count toward m."""
    present = sorted((p, i) for i, p in enumerate(ps) if p is not None)
    adj: list[float | None] = [None] * len(ps)
    running, m = 0.0, len(present)
    for rank, (p, i) in enumerate(present):
        running = max(running, min(1.0, (m - rank) * p))
        adj[i] = running
    return adj


def weighted_kappa(pairs: list[tuple[int, int]], weight: str, k: int = 4) -> float | None:
    """Cohen's weighted kappa over k ordered categories; weight is 'linear' or 'quadratic'."""
    if not pairs:
        return None
    n = len(pairs)
    obs = [[0] * k for _ in range(k)]
    for a, b in pairs:
        obs[a][b] += 1
    row = [sum(obs[i]) for i in range(k)]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    power = 1 if weight == "linear" else 2
    w = [[(abs(i - j) / (k - 1)) ** power for j in range(k)] for i in range(k)]
    po = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w[i][j] * row[i] * col[j] for i in range(k) for j in range(k)) / (n * n)
    return None if pe == 0 else 1 - po / pe


def load_items(data: Path, stem: str) -> dict[str, dict[str, Any]]:
    return {it["id"]: it for it in json.loads((data / f"{stem}.json").read_text(encoding="utf-8"))["items"]}


def load_tiers(data: Path, stem: str, judge: str) -> dict[Key, int]:
    """Tier rank per reply under one judge, from the latest parsed row (re-grades of unparsed replies)."""
    best: dict[Key, tuple[str, int]] = {}
    with open(data / f"judgments_{stem}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("judge_model") != judge or r.get("tier") not in RANK:
                continue
            key = (r["model"], r["stimulus_id"], r["arm"])
            if key not in best or r["judged_utc"] > best[key][0]:
                best[key] = (r["judged_utc"], RANK[r["tier"]])
    return {k: v[1] for k, v in best.items()}


def load_replies(data: Path, stem: str) -> tuple[set[Key], set[str]]:
    """Replies stopped for length or empty, and the models present in the archive."""
    bad: set[Key] = set()
    models: set[str] = set()
    with open(data / f"responses_{stem}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("record_type") != "advice":
                continue
            models.add(r["model_requested"])
            if r.get("stop_reason") in ("length", "max_tokens") or not (r.get("response_text") or "").strip():
                bad.add((r["model_requested"], r["stimulus_id"], r["arm"]))
    return bad, models


def analyse(data: Path, judge: str, drop_bad: bool = False) -> dict[str, Any]:
    items_a, items_b = load_items(data, FILE_A), load_items(data, FILE_B)
    body_to_b = collections.defaultdict(list)
    for sid, it in items_b.items():
        body_to_b[it["clinical_body"]].append(sid)
    joins, unjoined = {}, []
    for sid, it in items_a.items():
        matches = body_to_b.get(it["clinical_body"], [])
        if len(matches) == 1:
            joins[sid] = matches[0]
        else:
            unjoined.append(sid)
    tiers_a, tiers_b = load_tiers(data, FILE_A, judge), load_tiers(data, FILE_B, judge)
    bad_a, models_a = load_replies(data, FILE_A)
    bad_b, models_b = load_replies(data, FILE_B)
    models = sorted(models_a & models_b)
    units: dict[tuple[str, str], dict[str, Any]] = {}
    missing: collections.Counter[str] = collections.Counter()
    dropped: collections.Counter[str] = collections.Counter()
    for m in models:
        for a_id, b_id in joins.items():
            ka = [(m, a_id, "clinical"), (m, a_id, "patient")]
            kb = [(m, b_id, "clinical"), (m, b_id, "patient")]
            ac, ap = tiers_a.get(ka[0]), tiers_a.get(ka[1])
            bc, bp = tiers_b.get(kb[0]), tiers_b.get(kb[1])
            if drop_bad and any(k in bad_a for k in ka):
                ac = ap = None
                dropped["A"] += 1
            if drop_bad and any(k in bad_b for k in kb):
                bc = bp = None
                dropped["B"] += 1
            u: dict[str, Any] = {}
            if ac is not None and ap is not None:
                u["vocab"] = ap - ac
            else:
                missing["vocab"] += 1
            if None not in (ac, ap, bc, bp):
                u["style"] = (bp - bc) - (ap - ac)
                u["smv"] = u["style"] - u["vocab"]
            else:
                missing["style"] += 1
            if ac is not None and bc is not None:
                u["retest"] = (ac, bc)
            if ac is not None and ap is not None:
                u["arm_differs_a"] = ap != ac
            if bc is not None and bp is not None:
                u["arm_differs_b"] = bp != bc
            units[(m, a_id)] = u
    out: dict[str, Any] = {"judge": judge, "drop_truncated_or_empty": drop_bad, "joined_situations": len(joins),
                           "unjoined": unjoined, "models": models, "missing_units": dict(missing),
                           "dropped_units": dict(dropped)}
    out["within_model"] = {m: {c: sign_test([units[(m, s)][c] for s in joins if c in units[(m, s)]])
                               for c in CONTRASTS} for m in models}
    pooled: dict[str, dict[str, Any]] = {}
    for c in CONTRASTS:
        labels = []
        for s in joins:
            vals = [units[(m, s)][c] for m in models if c in units[(m, s)]]
            if vals:
                pos, neg = sum(v > 0 for v in vals), sum(v < 0 for v in vals)
                labels.append(1 if pos > neg else -1 if neg > pos else 0)
        pooled[c] = sign_test(labels)
        vals_all = [u[c] for u in units.values() if c in u]
        pooled[c]["mean_unit_diff"] = sum(vals_all) / len(vals_all) if vals_all else None
    for c, p in zip(CONTRASTS, holm([pooled[c]["p"] for c in CONTRASTS])):
        pooled[c]["p_holm"] = p
    out["pooled"] = pooled
    rt = [u["retest"] for u in units.values() if "retest" in u]
    out["retest"] = {"n": len(rt), "exact_agreement": sum(a == b for a, b in rt) / len(rt) if rt else None,
                     "kappa_linear": weighted_kappa(rt, "linear"), "kappa_quadratic": weighted_kappa(rt, "quadratic"),
                     "a_higher": sum(a > b for a, b in rt), "b_higher": sum(b > a for a, b in rt)}
    for f in ("a", "b"):
        flags = [u[f"arm_differs_{f}"] for u in units.values() if f"arm_differs_{f}" in u]
        out[f"arm_difference_rate_{f}"] = sum(flags) / len(flags) if flags else None
    return out


def run(data: Path) -> dict[str, Any]:
    return {"main": analyse(data, PRIMARY), "second_judge": analyse(data, SECOND),
            "exploratory_drop_truncated": analyse(data, PRIMARY, drop_bad=True)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--out", type=Path, help="write the full results as JSON")
    args = ap.parse_args(argv)
    res = run(args.data_dir)
    if args.out:
        args.out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    for name, r in res.items():
        print(f"== {name}: joined {r['joined_situations']}, unjoined {r['unjoined']}, models {len(r['models'])}, "
              f"missing {r['missing_units']}, dropped {r['dropped_units']}")
        for c in CONTRASTS:
            p = r["pooled"][c]
            print(f"  {c:5s} +{p['pos']} -{p['neg']} 0:{p['ties']}  p={p['p']:.4f}  holm={p['p_holm']:.4f}  "
                  f"mean unit {p['mean_unit_diff']:+.3f}")
        print(f"  retest {r['retest']}; arm differs A {r['arm_difference_rate_a']:.3f}, B {r['arm_difference_rate_b']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
