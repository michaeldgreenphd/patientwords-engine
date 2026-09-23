"""Design-only power and error-rate simulation for the wave-2 register contrast (docs/petri_wave2_design.md §10).

No outcome data is read: every quantity is a stated parameter. Per exchange, the colloquial reply's tier is one lower
than the clinical reply's with probability `pd` (drawn per scenario as max(0, pd + N(0, tau))), one higher with
probability `pu`, and otherwise the same. With probability `rho` an exchange repeats the previous exchange's
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
            pd_s = min(max(0.0, pd + rng.gauss(0, tau)), 1 - pu)
            ds = [conversation_d(rng, pd_s, pu, rho) for _ in range(c)]
            triples += ds
            means.append(sum(ds) / c)
        neg = sum(d < 0 for d in triples)
        pos = sum(d > 0 for d in triples)
        sign_hits += sign_test_p(neg, neg + pos) < 0.05
        perm_hits += sign_flip_p(means) < 0.05
    return {"triple_sign_test": sign_hits / sims, "scenario_sign_flip": perm_hits / sims}


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
                      "alpha": 0.05, "results": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
