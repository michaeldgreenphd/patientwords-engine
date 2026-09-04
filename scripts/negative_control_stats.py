"""Reproducible statistics for the negative-control comparison ($0, offline).

The first write-up of the 2026-09-04 control computed its bootstrap by hand in a
shell one-liner and recorded no artifact -- violating the repo's own rule that a
seed exists in the output, not the invocation, and producing CI endpoints an
independent reviewer could not regenerate from any committed script. This is
the script that should have existed. It uses the study's registered bootstrap
(``paired_stats_rigor.cluster_bootstrap_ci``) and sign test, records the seed,
and writes everything the write-up cites.

It also computes what that review found was missing:

* **Outlier sensitivity.** The treatment interval's "excludes zero" is checked
  with the k most-negative pairs removed. If it stops excluding zero at small k,
  the defensible claim is about direction (the sign test), not magnitude.
* **Length in tokens, not words.** ``token_parity.n_engine`` in every run is the
  tokenized length of each side, so the delta the model actually saw is on disk.
* **Both spread ratios.** sd ratio and variance ratio, because "33% of the
  variance" reads as an sd ratio and understates the control's noise (it is 58%).
* **Top-1 redirects under the control.** The site calls a top-1 change a
  "redirect"; if a neutral clause insertion produces them, per-pair flip labels
  are as unstable as per-pair penalties.

No medical vocabulary lives in this file.

Usage:
  PYTHONPATH=scripts python scripts/negative_control_stats.py \
      --treatment trace_out/verify_pairs_<STAMP>__<model> \
      --control   trace_out/verify_control_qualified_<STAMP>__<model> \
      --identity  trace_out/verify_control_identity_<STAMP>__<model> \
      --out ops/negative_control_<DATE>.json [--seed 7] [--boot 10000]
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

from paired_stats_rigor import cluster_bootstrap_ci, sign_test


def load(run_dir: str) -> dict[int, dict]:
    paths = sorted(glob.glob(str(Path(run_dir) / "verify_summary*.json")))
    if not paths:
        raise SystemExit(f"no verify_summary*.json under {run_dir}")
    out: dict[int, dict] = {}
    for p in paths:
        for r in json.loads(Path(p).read_text(encoding="utf-8"))["results"]:
            out[r["index"]] = r
    return out


def penalty(r: dict) -> float | None:
    p = r.get("probabilities") or {}
    if p.get("clinical") is None or p.get("patient") is None:
        return None
    return round(p["patient"] - p["clinical"], 4)


def token_delta(r: dict) -> int | None:
    tp = r.get("token_parity") or {}
    try:
        return tp["patient"]["n_engine"] - tp["clinical"]["n_engine"]
    except (KeyError, TypeError):
        return None


def top1(r: dict, side: str) -> str | None:
    spread = (r.get("predictive_spread") or {}).get(side) or []
    return spread[0][0] if spread else None


def arm_stats(rows: dict[int, dict], rng: random.Random, n_boot: int) -> dict:
    pens = {i: penalty(r) for i, r in rows.items()}
    pens = {i: v for i, v in pens.items() if v is not None}
    vals = list(pens.values())
    boot = cluster_bootstrap_ci(vals, rng, n_boot)
    neg = sum(1 for v in vals if v < 0)
    pos = sum(1 for v in vals if v > 0)
    toks = [d for d in (token_delta(r) for r in rows.values()) if d is not None]
    redirects = sum(1 for r in rows.values() if top1(r, "clinical") != top1(r, "patient"))
    return {
        "n": len(vals),
        "mean": boot["mean"],
        "ci95": boot["ci95"],
        "ci95_excludes_zero": boot["ci95"][0] > 0 or boot["ci95"][1] < 0,
        "median": round(st.median(vals), 4),
        "sd_sample": round(st.stdev(vals), 4),
        "sd_population": round(st.pstdev(vals), 4),
        "min": min(vals), "max": max(vals),
        "n_negative": neg, "n_positive": pos, "n_zero": len(vals) - neg - pos,
        "sign_test_two_sided_p": sign_test(neg, pos),
        "n_abs_over_0.05": sum(1 for v in vals if abs(v) > 0.05),
        "token_delta_mean": round(st.mean(toks), 2) if toks else None,
        "token_delta_median": st.median(toks) if toks else None,
        "token_delta_range": [min(toks), max(toks)] if toks else None,
        "top1_redirects": redirects,
        "penalties_by_index": pens,
    }


def drop_k_sensitivity(pens: dict[int, float], rng: random.Random, n_boot: int, ks=(1, 2, 3, 5)) -> list[dict]:
    """Remove the k most-negative pairs and re-bootstrap. Answers: is 'excludes
    zero' a property of the batch or of a few pairs?"""
    ordered = sorted(pens.items(), key=lambda kv: kv[1])
    total = sum(pens.values())
    out = []
    for k in ks:
        dropped = ordered[:k]
        kept = [v for i, v in pens.items() if i not in {i for i, _ in dropped}]
        b = cluster_bootstrap_ci(kept, rng, n_boot)
        out.append({
            "k_dropped": k,
            "dropped_indices": [i for i, _ in dropped],
            "dropped_share_of_total": round(sum(v for _, v in dropped) / total, 3) if total else None,
            "mean": b["mean"], "ci95": b["ci95"],
            "ci95_excludes_zero": b["ci95"][0] > 0 or b["ci95"][1] < 0,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--treatment", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--identity", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--boot", type=int, default=10000)
    args = ap.parse_args()

    T, C = load(args.treatment), load(args.control)
    # One RNG, seeded once, consumed in a fixed order: treatment, control,
    # sensitivity. Re-running with the same seed regenerates every number.
    rng = random.Random(args.seed)
    treat = arm_stats(T, rng, args.boot)
    ctrl = arm_stats(C, rng, args.boot)
    sens = drop_k_sensitivity(treat["penalties_by_index"], rng, args.boot)

    report = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": args.seed, "n_boot": args.boot,
        "method": "paired_stats_rigor.cluster_bootstrap_ci (percentile, one-per-phrase); sign_test",
        "runs": {"treatment": args.treatment, "control": args.control, "identity": args.identity},
        "treatment": treat, "control": ctrl,
        "spread_ratio": {
            "sd_ratio_control_over_treatment": round(ctrl["sd_sample"] / treat["sd_sample"], 3),
            "variance_ratio_control_over_treatment": round((ctrl["sd_sample"] / treat["sd_sample"]) ** 2, 3),
            "note": "sd ratio is the honest 'how noisy' figure; the variance ratio reads smaller",
        },
        "control_over_treatment_mean": round(ctrl["mean"] / treat["mean"], 3) if treat["mean"] else None,
        "treatment_drop_k_sensitivity": sens,
    }
    if args.identity:
        rows = load(args.identity)
        diffs = [i for i, r in rows.items() if penalty(r) not in (0.0, None)]
        same = sum(1 for r in rows.values() if r["prompts"]["clinical"] == r["prompts"]["patient"])
        report["identity"] = {"n": len(rows), "prompts_identical": same,
                              "nonzero_penalty_indices": diffs, "passed": not diffs and same == len(rows)}

    for arm in ("treatment", "control"):
        report[arm].pop("penalties_by_index")  # keep the artifact readable; the runs hold the rows
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")

    t, c = report["treatment"], report["control"]
    print(f"seed={args.seed} boot={args.boot}")
    print(f"treatment  mean {t['mean']:+.4f}  CI {t['ci95']}  excl0={t['ci95_excludes_zero']}  "
          f"sign {t['n_negative']}/{t['n_positive']} p={t['sign_test_two_sided_p']:.4f}  tokens {t['token_delta_mean']:+.2f}")
    print(f"control    mean {c['mean']:+.4f}  CI {c['ci95']}  excl0={c['ci95_excludes_zero']}  "
          f"sign {c['n_negative']}/{c['n_positive']} p={c['sign_test_two_sided_p']:.4f}  tokens {c['token_delta_mean']:+.2f}")
    print(f"sd ratio {report['spread_ratio']['sd_ratio_control_over_treatment']}  "
          f"variance ratio {report['spread_ratio']['variance_ratio_control_over_treatment']}  "
          f"control redirects {c['top1_redirects']}/{c['n']}  treatment redirects {t['top1_redirects']}/{t['n']}")
    for s in sens:
        print(f"drop {s['k_dropped']} most-negative ({s['dropped_share_of_total']:.0%} of total): "
              f"mean {s['mean']:+.4f} CI {s['ci95']} excl0={s['ci95_excludes_zero']}")
    if "identity" in report:
        print(f"identity passed={report['identity']['passed']}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
