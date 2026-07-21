"""payload.summary — the ONE definition of the site's headline numbers (audit M1).

The pages currently compute the headline mean language penalty three times in
JS with an un-deduped row mean over the public payload, while the claim-grade
data/model_stats.json uses a phrase-deduped mean over the full collector
population — two different numbers ("-4 pp" vs "-3.1 pp") with no population
label on either. This module computes the payload-population summary ONCE,
phrase-deduped exactly like the rigor script (grouped by clinical prompt,
collector-style batch#index fallback for missing prompts, penalties averaged
within a phrase), with a phrase-level bootstrap CI, and labels its population
explicitly so the two figures can never be conflated again.

Emitted by export_frontend_simulated.py as payload["summary"]; the pages'
JS switch to reading it is a separate owner-side change. No medical
vocabulary lives in this file.
"""
from __future__ import annotations

import random


def phrase_key(scenario: dict) -> str:
    prompt = (scenario.get("prompts") or {}).get("clinical")
    return prompt or f"{scenario.get('batch')}#{scenario.get('batch_index')}"


def _phrase_means(scenarios: list[dict]) -> list[float]:
    groups: dict[str, list[float]] = {}
    for s in scenarios:
        pen = s.get("language_penalty")
        if isinstance(pen, (int, float)) and not isinstance(pen, bool):
            groups.setdefault(phrase_key(s), []).append(float(pen))
    return [sum(v) / len(v) for v in groups.values()]


def bootstrap_ci(vals: list[float], seed: int = 7, n_boot: int = 2000):
    """Percentile bootstrap CI95 over phrase means (mirrors the rigor script)."""
    if len(vals) < 3:
        return None
    rng = random.Random(seed)
    k = len(vals)
    means = sorted(sum(vals[rng.randrange(k)] for _ in range(k)) / k
                   for _ in range(n_boot))
    return [round(means[int(0.025 * n_boot)], 4),
            round(means[int(0.975 * n_boot) - 1], 4)]


def build_summary(scenarios: list[dict], accepted: int, holdout_withheld: int,
                  base_model: str = "gemma-2-2b", seed: int = 7,
                  n_boot: int = 2000) -> dict:
    """The payload-population summary block.

    ``scenarios`` are the exporter's assembled scenario dicts (base-model
    fields mirrored at the top level). Screened-out rows carry a null penalty
    and drop out of the penalty stats implicitly, matching the pages' filter.
    """
    scored = [s for s in scenarios
              if isinstance(s.get("language_penalty"), (int, float))
              and not isinstance(s.get("language_penalty"), bool)]
    phrase_means = _phrase_means(scored)
    screened = sum(1 for s in scenarios
                   if (s.get("screening") or {}).get("status") == "screened_out")
    measured = [s for s in scenarios
                if (s.get("screening") or {}).get("status") != "screened_out"]
    raw = [float(s["language_penalty"]) for s in scored]
    return {
        "_": ("payload-population summary: the scenarios published in THIS file, "
              "phrase-deduped like scripts/paired_stats_rigor.py. The claim-grade "
              "estimate in data/model_stats.json covers the full collector "
              "population (holdout + supplementary excluded) and is the citable "
              "number; this block exists so pages stop recomputing divergent "
              "row-level means in JS."),
        "model": base_model,
        "penalty": {
            "population": "public_payload",
            "mean_phrase_deduped": round(sum(phrase_means) / len(phrase_means), 4)
                                    if phrase_means else None,
            "n_phrases": len(phrase_means),
            "n_scored_rows": len(scored),
            "mean_rows_raw": round(sum(raw) / len(raw), 4) if raw else None,
            "ci95": bootstrap_ci(phrase_means, seed=seed, n_boot=n_boot),
        },
        "totals": {
            "accepted": accepted,
            "accepted_public": accepted - holdout_withheld,
            "holdout_withheld": holdout_withheld,
            "measured": len(measured),
            "screened_out": screened,
            "flipped_base": sum(1 for s in measured if s.get("flipped")),
        },
    }
