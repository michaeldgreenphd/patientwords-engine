"""Design-only power and error-rate simulation for the wave-2 register contrast (docs/petri_wave2_design.md §10).

No outcome data is read: every quantity is a stated parameter. Per exchange, the colloquial reply's tier is one lower
than the clinical reply's with probability `pd_s`, one higher with probability `pu`, and otherwise the same. `pd_s` is
drawn per scenario as pd + clip(N(0, tau), -m, m) with m = min(pd, 1 - pu - pd): the clip keeps pd_s in [0, 1 - pu],
and because it is symmetric E[pd_s] = pd exactly, so a row with pd = pu is a zero-mean null however large tau is
(`scenario_pd`). `tau` is the deviation's sd before the clip; where the clip binds the realised sd is smaller. With probability `rho` an exchange repeats the previous exchange's
difference, which models persistence within one conversation. A triple's D is the mean of its ten differences. The
design has 8 scenarios contributing 4, 4, 4, 8, 3, 3, 3 and 6 triples: 35 in all, the planned final data, where the
two identity seeds count twice for their two speakers.

For each parameter set the script reports how often two tests reject at two-sided α = 0.05:
- the triple-level exact sign test (10.2's primary test);
- the scenario-level exact sign-flip permutation test on the 8 scenario means (256 flips; 10.2's general-headline
  gate).

The seed is an argument and is written into the output, so the numbers the design note quotes are reproducible:
`python scripts/petri_w2_power_sim.py --seed 20260923 --sims 3000`.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random

TRIPLES_PER_SCENARIO = (4, 4, 4, 8, 3, 3, 3, 6)
_FLIPS = list(itertools.product((1, -1), repeat=len(TRIPLES_PER_SCENARIO)))


def sign_test_p(k: int, n: int) -> float:
    """Exact two-sided sign-test p-value for k of n non-tied observations on one side."""
    if n == 0:
        return 1.0
    k = min(k, n - k)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def sign_flip_p(means: list[float]) -> float:
    """Exact two-sided sign-flip permutation p-value for the mean of `means` (all 2^len sign assignments)."""
    flips = _FLIPS if len(means) == len(TRIPLES_PER_SCENARIO) else list(itertools.product((1, -1), repeat=len(means)))
    observed = abs(sum(means))
    return sum(1 for f in flips if abs(sum(a * b for a, b in zip(f, means))) >= observed - 1e-12) / len(flips)


def scenario_pd(rng: random.Random, pd: float, pu: float, tau: float) -> float:
    """One scenario's downgrade probability: pd plus a N(0, tau) deviation clipped to [-m, m], m = min(pd, 1 - pu - pd).

    The clip is symmetric about pd, so E[pd_s] = pd and the scenario effects stay centred on the stated mean. The first
    version clipped at zero only, min(max(0, pd + N(0, tau)), 1 - pu), which at pd = tau = 0.10 raised E[pd_s] to
    about 0.108 against pu = 0.10: the row labelled a null simulated a real downgrade shift (Codex, PR #29). One gauss
    draw is taken whatever tau is, as before, so the other rows see the same random stream."""
    if pd < 0 or pu < 0 or pd + pu > 1:
        raise ValueError(f"need pd >= 0, pu >= 0 and pd + pu <= 1, got pd={pd}, pu={pu}")
    bound = min(pd, 1 - pu - pd)
    return pd + max(-bound, min(bound, rng.gauss(0, tau)))


def conversation_d(rng: random.Random, pd: float, pu: float, rho: float, exchanges: int = 10) -> float:
    """Mean per-exchange tier difference (colloquial minus clinical) of one simulated triple."""
    previous: int | None = None
    total = 0
    for _ in range(exchanges):
        if previous is not None and rng.random() < rho:
            d = previous
        else:
            u = rng.random()
            d = -1 if u < pd else (1 if u < pd + pu else 0)
        total += d
        previous = d
    return total / exchanges


def rejection_rates(rng: random.Random, *, pd: float, pu: float, rho: float, tau: float, sims: int,
                    counts: tuple[int, ...] = TRIPLES_PER_SCENARIO) -> dict[str, float]:
    """Share of simulated campaigns in which each test rejects at two-sided 0.05."""
    sign_hits = perm_hits = 0
    for _ in range(sims):
        triples: list[float] = []
        means: list[float] = []
        for c in counts:
            pd_s = scenario_pd(rng, pd, pu, tau)
            ds = [conversation_d(rng, pd_s, pu, rho) for _ in range(c)]
            triples += ds
            means.append(sum(ds) / c)
        neg = sum(d < 0 for d in triples)
        pos = sum(d > 0 for d in triples)
        sign_hits += sign_test_p(neg, neg + pos) < 0.05
        perm_hits += sign_flip_p(means) < 0.05
    return {"triple_sign_test": sign_hits / sims, "scenario_sign_flip": perm_hits / sims}


HETEROGENEITY = ("pd_s = pd + clip(N(0, tau), -m, m), m = min(pd, 1 - pu - pd); symmetric, so E[pd_s] = pd; "
                 "tau is the sd before the clip")

GRID = (
    # (label, pd, pu, rho, tau)
    ("null, scenarios alike", 0.10, 0.10, 0.5, 0.00),
    ("null mean, scenarios differ (tau 0.10)", 0.10, 0.10, 0.5, 0.10),
    ("net shift 5 points", 0.15, 0.10, 0.5, 0.05),
    ("net shift 10 points", 0.20, 0.10, 0.5, 0.05),
    ("net shift 15 points", 0.25, 0.10, 0.5, 0.05),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--sims", type=int, default=3000)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    rows = [{"case": label, "pd": pd, "pu": pu, "rho": rho, "tau": tau,
             **rejection_rates(rng, pd=pd, pu=pu, rho=rho, tau=tau, sims=args.sims)}
            for label, pd, pu, rho, tau in GRID]
    print(json.dumps({"seed": args.seed, "sims": args.sims, "triples_per_scenario": list(TRIPLES_PER_SCENARIO),
                      "alpha": 0.05, "scenario_heterogeneity": HETEROGENEITY, "results": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
