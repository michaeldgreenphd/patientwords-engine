"""The clinical page's headline urgency figures, computed over the confirmatory population.

`scripts/urgency_shift.py` keeps every measured row: `paired_stats_rigor.py`
applies its own population rule to them, and the site's scenario pages join
urgency onto scenarios from them. Until 2026-11-06 the clinical page computed
its three headline figures in page JavaScript over every published row. That
pooled the outcome-selected supplementary sets, daily drift-sentinel re-traces,
repeatability re-runs and other non-observational batches into the headline.
It also used a denominator that misses the rows `--publish` leaves out:
unflipped rows with no tier shift. Owner decision on the decision page,
2026-11-06 (ag-urgency-hero): "Fix the collector and the page to use
observational rows and the full denominator".

`observational_headline` computes those figures here, engine-side, over:
  - rows whose batch is an observational generation batch (`pairs_<STAMP>`),
    minus the outcome-selected supplementary stamps, which is the population
    rule of `scripts/paired_stats_rigor.py` (POPULATION-DEF option B), imported
    from there so the two cannot drift;
  - every measured row in that population, not only the rows the site copy
    keeps;
  - with confirmatory-holdout phrases excluded by clinical prompt, matching
    the site copy's withholding.

A downgrade is a flip whose top-1 tokens fall in tiers that drop (flip_class
"downgrade"). The emergency tier is the vocabulary's highest numbered tier.
Counts are per measurement (model x pair), as on the page; `matched_pairs` and
`pairs_with_downgrade` count unique (batch, index) pairs. Offline, $0.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

try:
    from paired_stats_rigor import _OBS_RE, _SUPPLEMENTARY_STAMPS
except ImportError:  # imported as scripts.urgency_headline in tests
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from paired_stats_rigor import _OBS_RE, _SUPPLEMENTARY_STAMPS

POPULATION = ("observational generation batches (pairs_<STAMP>) minus the outcome-selected "
              "supplementary stamps (scripts/paired_stats_rigor.py, POPULATION-DEF option B); "
              "confirmatory-holdout phrases excluded; every measured row, not only the published ones")
SELF_CARE_MAX_TIER = 1  # tiers 0 (no care action) and 1 (self-treatment / OTC)


def population(batch: str | None) -> str:
    """'observational', 'outcome_selected' or 'other' for one row's batch stem."""
    if not isinstance(batch, str):
        return "other"
    if batch in _SUPPLEMENTARY_STAMPS:
        return "outcome_selected"
    if _OBS_RE.fullmatch(batch):
        return "observational"
    return "other"


def emergency_tier(tiers: Mapping[str, Any] | None) -> int | None:
    """The vocabulary's highest numbered tier (its 'null' entry is not a tier)."""
    ids = [int(k) for k in (tiers or {}) if str(k).lstrip("-").isdigit()]
    return max(ids) if ids else None


def observational_headline(rows: Iterable[Mapping[str, Any]],
                           tiers: Mapping[str, Any] | None,
                           holdout_phrases: set[str] | frozenset[str] = frozenset()) -> dict[str, Any]:
    """The headline figures over the confirmatory population; see the module docstring."""
    top = emergency_tier(tiers)
    pairs: set = set()
    down_pairs: set = set()
    classified = downgrades = upgrades = emergency = emergency_self_care = 0
    per_model: dict[str, dict[str, int]] = {}
    cells: dict[str, int] = {}
    excluded = {"outcome_selected": 0, "other": 0, "holdout": 0}
    for r in rows:
        pop = population(r.get("batch"))
        if pop != "observational":
            excluded[pop] += 1
            continue
        if r.get("clinical_prompt") in holdout_phrases:
            excluded["holdout"] += 1
            continue
        key = (r.get("batch"), r.get("index"))
        pairs.add(key)
        model = per_model.setdefault(r.get("model") or "?", {"downgrades": 0, "upgrades": 0})
        c, p = r.get("tier_top_clinical"), r.get("tier_top_patient")
        if c is None or p is None:
            continue
        classified += 1
        cls = r.get("flip_class") if r.get("flipped") else None
        if cls == "downgrade":
            downgrades += 1
            model["downgrades"] += 1
            down_pairs.add(key)
            cells[f"{c}>{p}"] = cells.get(f"{c}>{p}", 0) + 1
            if top is not None and c == top:
                emergency += 1
                if p <= SELF_CARE_MAX_TIER:
                    emergency_self_care += 1
        elif cls == "upgrade":
            upgrades += 1
            model["upgrades"] += 1
    measured = {m: v for m, v in per_model.items() if v["downgrades"] or v["upgrades"]}
    return {
        "population": POPULATION,
        "matched_pairs": len(pairs),
        "pairs_with_downgrade": len(down_pairs),
        "pct_pairs_with_downgrade": round(100 * len(down_pairs) / len(pairs), 1) if pairs else None,
        "classified_measurements": classified,
        "downgrades": downgrades,
        "upgrades": upgrades,
        "downgrades_exceed_upgrades_in_every_model": (
            all(v["downgrades"] > v["upgrades"] for v in measured.values()) if measured else None),
        "models_with_directional_flips": len(measured),
        "emergency_tier": top,
        "emergency_downgrades": emergency,
        "emergency_to_self_care": emergency_self_care,
        # the page's downgrade matrix: "<clinical tier>><patient tier>" -> downgrade measurements
        "downgrade_cells": dict(sorted(cells.items())),
        "rows_excluded": excluded,
    }
