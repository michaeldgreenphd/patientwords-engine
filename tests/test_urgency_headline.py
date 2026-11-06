"""scripts/urgency_headline.py: the clinical page's headline figures over the confirmatory population.

Owner decision 2026-11-06 (ag-urgency-hero). The page computed its headline over every published row, which pooled
outcome-selected, sentinel and re-run batches and missed the rows --publish leaves out. These tests pin the
population rule (shared with paired_stats_rigor.py), the full denominator, the holdout exclusion and the counts.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paired_stats_rigor = _load("paired_stats_rigor")
_uh = _load("urgency_headline")
emergency_tier, observational_headline, population = (
    _uh.emergency_tier, _uh.observational_headline, _uh.population)

TIERS = {"4": "emergency care", "3": "specialist care", "2": "generalist", "1": "self-treatment",
         "0": "no care action", "null": "excluded"}
OBS = "pairs_20260710T163230Z"
OBS2 = "pairs_20260712T163501Z"
STEERED = "pairs_20260809T172338Z"


def row(batch, index, model="gemma-2-2b", c=None, p=None, flip=None, prompt=None):
    return {"batch": batch, "index": index, "model": model, "tier_top_clinical": c, "tier_top_patient": p,
            "flipped": flip is not None, "flip_class": flip, "clinical_prompt": prompt or f"{batch}#{index}"}


def test_population_matches_paired_stats_rigor():
    assert population(OBS) == "observational"
    for stamp in paired_stats_rigor._SUPPLEMENTARY_STAMPS:
        assert population(stamp) == "outcome_selected"
    for other in ("drift_sentinel_20260829", "urgency_downgrades_20260707T1", "repeatability_r1",
                  "pairs_20260706T172135Z__context", "dialects_20260708T215356Z", None):
        assert population(other) == "other"


def test_emergency_tier_is_the_highest_numbered_tier():
    assert emergency_tier(TIERS) == 4
    assert emergency_tier({}) is None


def test_non_observational_rows_never_enter_the_headline():
    rows = [row(OBS, 1, c=3, p=2, flip="downgrade"),
            row(STEERED, 1, c=4, p=1, flip="downgrade"),
            row("drift_sentinel_20260829", 1, c=4, p=0, flip="downgrade"),
            row("repeatability_r1", 1, c=3, p=2, flip="downgrade")]
    h = observational_headline(rows, TIERS)
    assert h["matched_pairs"] == 1 and h["downgrades"] == 1 and h["emergency_downgrades"] == 0
    assert h["rows_excluded"] == {"outcome_selected": 1, "other": 2, "holdout": 0}


def test_denominator_counts_unflipped_and_unclassified_rows():
    # The site copy drops unflipped rows with no tier shift; the headline must not.
    rows = [row(OBS, 1, c=3, p=2, flip="downgrade"),
            row(OBS, 2, c=2, p=2),           # unflipped, classified
            row(OBS, 3),                     # unflipped, no tier at all
            row(OBS2, 1, c=2, p=3, flip="upgrade")]
    h = observational_headline(rows, TIERS)
    assert h["matched_pairs"] == 4
    assert h["classified_measurements"] == 3
    assert h["pairs_with_downgrade"] == 1 and h["pct_pairs_with_downgrade"] == 25.0
    assert (h["downgrades"], h["upgrades"]) == (1, 1)


def test_pairs_are_unique_across_models_but_measurements_are_not():
    rows = [row(OBS, 1, model="gemma-2-2b", c=3, p=2, flip="downgrade"),
            row(OBS, 1, model="qwen3-4b", c=3, p=2, flip="downgrade")]
    h = observational_headline(rows, TIERS)
    assert h["matched_pairs"] == 1 and h["pairs_with_downgrade"] == 1
    assert h["downgrades"] == 2 and h["classified_measurements"] == 2


def test_holdout_phrases_are_excluded_by_prompt():
    rows = [row(OBS, 1, c=3, p=2, flip="downgrade", prompt="sealed"),
            row(OBS, 2, c=3, p=2, flip="downgrade")]
    h = observational_headline(rows, TIERS, holdout_phrases={"sealed"})
    assert h["matched_pairs"] == 1 and h["downgrades"] == 1
    assert h["rows_excluded"]["holdout"] == 1


def test_emergency_downgrades_and_the_self_care_subset():
    rows = [row(OBS, 1, c=4, p=1, flip="downgrade"),
            row(OBS, 2, c=4, p=3, flip="downgrade"),
            row(OBS, 3, c=3, p=0, flip="downgrade")]
    h = observational_headline(rows, TIERS)
    assert h["emergency_tier"] == 4
    assert h["emergency_downgrades"] == 2 and h["emergency_to_self_care"] == 1


def test_every_model_claim_is_computed_not_asserted():
    ok = [row(OBS, 1, model="a", c=3, p=2, flip="downgrade"),
          row(OBS, 2, model="b", c=3, p=2, flip="downgrade")]
    assert observational_headline(ok, TIERS)["downgrades_exceed_upgrades_in_every_model"] is True
    tie = ok + [row(OBS, 3, model="b", c=2, p=3, flip="upgrade")]
    assert observational_headline(tie, TIERS)["downgrades_exceed_upgrades_in_every_model"] is False
    assert observational_headline([row(OBS, 1)], TIERS)["downgrades_exceed_upgrades_in_every_model"] is None


vfc = _load("validate_frontend_contract")


def _check(headline):
    rep = vfc.Report()
    vfc.check_urgency(rep, {"vocabulary_status": "synthetic", "rows": [],
                            "summary": {"flip_classes": {}, "headline_observational": headline}}, {})
    return rep


def test_the_validator_accepts_a_computed_headline():
    rows = [row(OBS, 1, c=4, p=1, flip="downgrade"), row(OBS, 2, c=2, p=3, flip="upgrade")]
    assert _check(observational_headline(rows, TIERS)).errors == []


def test_the_validator_refuses_an_inconsistent_headline():
    h = observational_headline([row(OBS, 1, c=4, p=1, flip="downgrade")], TIERS)
    assert any("more than matched_pairs" in e for e in _check(dict(h, pairs_with_downgrade=5)).errors)
    assert any("more than downgrades" in e for e in _check(dict(h, emergency_downgrades=9)).errors)
    assert any("must be nonnegative" in e for e in _check(dict(h, upgrades=-1)).errors)
    assert _check("not an object").errors


def test_downgrade_cells_feed_the_matrix_and_sum_to_the_downgrades():
    rows = [row(OBS, 1, c=4, p=1, flip="downgrade"), row(OBS, 2, c=4, p=1, flip="downgrade"),
            row(OBS, 3, c=3, p=2, flip="downgrade"), row(STEERED, 1, c=4, p=0, flip="downgrade")]
    h = observational_headline(rows, TIERS)
    assert h["downgrade_cells"] == {"3>2": 1, "4>1": 2}
    assert _check(h).errors == []
    assert any("downgrade_cells" in e for e in _check(dict(h, downgrade_cells={"4>1": 1})).errors)
