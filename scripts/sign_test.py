"""The exact two-sided sign test shared by the urgency analyses.

One implementation behind three scripts, so the p-values they publish cannot
drift apart again:

  scripts/urgency_shift.py       summary.per_model.<model>.sign_test_p (row level)
  scripts/tier_sensitivity.py    sign_p under each vocabulary scenario
  scripts/paired_stats_rigor.py  per_model.<model>.sign_test.p (phrase level,
                                 before Benjamini-Hochberg)

Method. Each directional flip is a downgrade or an upgrade; lateral and
uninformative flips are ties and the callers leave them out of both counts.
Under the null hypothesis a directional flip is equally likely to go either way,
so the smaller count k of n = k_down + k_up is Binomial(n, 1/2). The two-sided p
doubles the exact lower tail, P(X <= k) = sum_{i=0..k} C(n, i) / 2**n, and caps
the result at 1.0 (the doubled tail exceeds 1 when the split is close to even).
The tail is summed in exact integer arithmetic and divided once, so the only
rounding is the final conversion to a float.

The value is returned unrounded. An exact test cannot give p = 0, and the
collector's former copy, which rounded to 5 decimals, published 0.0 for most
models; paired_stats_rigor.py dropped its rounding for that reason on
2026-07-14. Rounding for display is the renderer's job. One limit remains: the
result is an IEEE double, so a true p below about 4.9e-324 underflows to 0.0
(k = 0 with n of 1,075 or more, or a larger n with a lopsided split).

When there are no directional flips (n = 0) the test is undefined and the
function returns None rather than a p-value.

The Petri scripts (petri_w2_power_sim, petri_multiturn_synthetic,
export_petri_multiturn, petri_w2_register_contrast) keep their own copy on
purpose: it takes (k, n), returns 1.0 at n = 0, and the preregistered W2 design
and its tests pin it.

Deterministic and exact: there is no seed to record.
"""

from __future__ import annotations

import math


def sign_test(k_down: int, k_up: int) -> float | None:
    """Two-sided exact sign test: is the down/up split consistent with 50/50?

    Returns the unrounded p in (0, 1], or None when k_down + k_up == 0."""
    n = k_down + k_up
    if n == 0:
        return None
    k = min(k_down, k_up)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2.0 * tail)
