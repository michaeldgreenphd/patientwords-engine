"""Tests for scripts/validate_frontend_contract.py - the structural export gate.

scripts/ is not a package, so the module loads via importlib from its file
path (same pattern as test_fire_trigger.py). Fixtures build a minimal valid
site tree under tmp_path, then each test seeds one contract break and asserts
the validator names it. Abstract vocabulary only - no medical terms.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_frontend_contract.py"
_SPEC = importlib.util.spec_from_file_location("validate_frontend_contract", _MODULE_PATH)
vfc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vfc)

BASE = "gemma-2-2b"
OTHER = "other-model"


def model_obj(**overrides):
    obj = {
        "prob_clinical": 0.5, "prob_patient": 0.25, "language_penalty": 0.25,
        "anchor_fallback": False, "top_clinical": ["alpha", 0.5],
        "top_patient": ["beta", 0.25], "spread_clinical": [["alpha", 0.5]],
        "spread_patient": [["beta", 0.25]], "target_token": "alpha",
        "flipped": True, "screening": None, "circuit_diff": None,
        "clinical_mass": {"clinical": 0.4, "patient": 0.1},
    }
    obj.update(overrides)
    return obj


def scenario(i, batch="pairs_S1", batch_index=None, **model_overrides):
    base = model_obj(**model_overrides)
    other = model_obj(clinical_mass=None)
    entry = {
        "index": i, "batch": batch,
        "batch_index": batch_index if batch_index is not None else i,
        "clinical_prompt": "alpha prompt", "patient_prompt": "beta prompt",
        "intended_target": "alpha", "topics": [],
        "models": {BASE: base, OTHER: other},
    }
    entry.update({k: base[k] for k in vfc.COMPAT})
    return entry


def payload(n=2):
    scenarios = [scenario(i) for i in range(1, n + 1)]
    return {
        "batches": [{"batch": "pairs_S1",
                     "generated": {"model": "m", "run_timestamp": "2026-01-01T00:00:00Z",
                                   "cost_usd": 0.1, "accepted": n, "rejected": 0},
                     "screen_targets": None}],
        "traced": {"graph_model": BASE},
        "traced_by_model": {},
        "holdout_withheld": 3,
        "models_meta": [
            {"id": BASE, "label": "Base", "graph_model": BASE, "source_set": "set-a",
             "features": True, "graphs": True, "available": True, "default": True,
             "attention_replacement": False, "n_traced": n},
            {"id": OTHER, "label": "Other", "graph_model": OTHER, "source_set": None,
             "features": False, "graphs": False, "available": True, "default": False,
             "attention_replacement": False, "n_traced": n},
        ],
        "scenarios": scenarios,
    }


def urgency(rows=None):
    return {
        "vocabulary_status": "owner-reviewed v1 - domain review pending",
        "summary": {"per_model_deduped": {BASE: {"downgrades": 1, "upgrades": 0}}},
        "tiers": {}, "tier_examples": {},
        "rows": rows if rows is not None else [
            {"batch": "pairs_S1", "index": 1, "model": BASE,
             "flip_class": "downgrade", "tier_shift": -1.0,
             "tier_top_clinical": 2, "tier_top_patient": 1, "urgency_recovery": None},
        ],
    }


@pytest.fixture
def site(tmp_path):
    data = tmp_path / "site" / "data"
    data.mkdir(parents=True)

    def write(name, obj):
        (data / name).write_text(json.dumps(obj), encoding="utf-8")

    write("simulated_scenarios.json", payload())
    write("urgency_shift.json", urgency())
    write("stress_pairs.json", [{"top_prompt": "a", "bottom_prompt": "b",
                                 "target_clinical_token": "alpha",
                                 "provenance": {"source": "hand"}}])
    write("provenance.json", {"steering": {"key_example": {"batch": "pairs_S1",
                                                           "batch_index": 1}},
                              "batches": [{"batch": "pairs_S1",
                                           "run_timestamp": "2026-01-01"}]})
    return tmp_path / "site"


def run(site, mutate=None, strict=False):
    if mutate:
        path = site / "data" / "simulated_scenarios.json"
        obj = json.loads(path.read_text(encoding="utf-8"))
        mutate(obj)
        path.write_text(json.dumps(obj), encoding="utf-8")
    return vfc.validate(site, engine=None, strict=strict)


def test_valid_fixture_passes(site):
    rep = run(site)
    assert rep.errors == []


def test_missing_optional_artifacts_warn_only(site):
    (site / "data" / "urgency_shift.json").unlink()
    rep = run(site)
    assert rep.errors == []
    assert any("urgency_shift" in w for w in rep.warnings)


def test_missing_payload_is_an_error(site):
    (site / "data" / "simulated_scenarios.json").unlink()
    rep = run(site)
    assert any("simulated_scenarios" in e for e in rep.errors)


def test_unknown_top_level_key_warns_then_fails_strict(site):
    def mutate(p):
        p["mystery_key"] = 1
    rep = run(site, mutate)
    assert any("mystery_key" in w for w in rep.warnings)
    rep = run(site, strict=True)
    assert any("mystery_key" in e for e in rep.errors)


def test_scenario_model_id_missing_from_models_meta(site):
    def mutate(p):
        p["models_meta"] = [m for m in p["models_meta"] if m["id"] != OTHER]
    rep = run(site, mutate)
    assert any("absent from models_meta" in e for e in rep.errors)


def test_n_traced_mismatch(site):
    def mutate(p):
        p["models_meta"][0]["n_traced"] = 99
    rep = run(site, mutate)
    assert any("n_traced" in e for e in rep.errors)


def test_compat_mirror_divergence(site):
    def mutate(p):
        p["scenarios"][0]["language_penalty"] = 0.99  # mirror no longer matches base
    rep = run(site, mutate)
    assert any("mirror disagrees" in e for e in rep.errors)


def test_noncontiguous_index(site):
    def mutate(p):
        p["scenarios"][1]["index"] = 7  # scenario.html prev/next assumes 1..N
    rep = run(site, mutate)
    assert any("contiguous" in e for e in rep.errors)


def test_duplicate_batch_index(site):
    def mutate(p):
        p["scenarios"][1]["batch_index"] = p["scenarios"][0]["batch_index"]
    rep = run(site, mutate)
    assert any("duplicate (batch, batch_index)" in e for e in rep.errors)


def test_clinical_mass_on_featureless_model(site):
    def mutate(p):
        p["scenarios"][0]["models"][OTHER]["clinical_mass"] = {"clinical": 0.001}
    rep = run(site, mutate)
    assert any("NullFetcher artifact" in e for e in rep.errors)


def test_dangling_render_path(site):
    def mutate(p):
        p["scenarios"][0]["html"] = "modes/simulated/pairs_S1/index_01.html"
        p["scenarios"][0]["models"][BASE]["html"] = p["scenarios"][0]["html"]
    rep = run(site, mutate)
    assert any("render path missing" in e for e in rep.errors)

    # and passes once the file exists
    render = site / "modes" / "simulated" / "pairs_S1"
    render.mkdir(parents=True)
    (render / "index_01.html").write_text("<p>render</p>", encoding="utf-8")
    rep = vfc.validate(site, engine=None)
    assert not any("render path missing" in e for e in rep.errors)


def test_duplicate_urgency_join_key(site):
    rows = urgency()["rows"] * 2
    (site / "data" / "urgency_shift.json").write_text(
        json.dumps(urgency(rows)), encoding="utf-8")
    rep = run(site)
    assert any("duplicate join key" in e for e in rep.errors)


def test_orphan_urgency_rows_warn(site):
    rows = urgency()["rows"] + [{"batch": "pairs_GONE", "index": 9, "model": BASE,
                                 "flip_class": None, "tier_shift": None,
                                 "tier_top_clinical": None, "tier_top_patient": None,
                                 "urgency_recovery": None}]
    (site / "data" / "urgency_shift.json").write_text(
        json.dumps(urgency(rows)), encoding="utf-8")
    rep = run(site)
    assert rep.errors == []
    assert any("join no published scenario" in w for w in rep.warnings)


def test_empty_vocabulary_status(site):
    u = urgency()
    u["vocabulary_status"] = "  "
    (site / "data" / "urgency_shift.json").write_text(json.dumps(u), encoding="utf-8")
    rep = run(site)
    assert any("draft label is load-bearing" in e for e in rep.errors)


def test_key_example_join_miss(site):
    prov = {"steering": {"key_example": {"batch": "pairs_GONE", "batch_index": 42}},
            "batches": []}
    (site / "data" / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    rep = run(site)
    assert any("key_example" in e for e in rep.errors)


def test_stale_engine_copy_warns(site, tmp_path):
    engine = tmp_path / "engine"
    (engine / "data" / "measured").mkdir(parents=True)
    (engine / "data" / "measured" / "imported_pairs.json").write_text(
        json.dumps([{"top_prompt": "different"}]), encoding="utf-8")
    rep = vfc.validate(site, engine=engine)
    assert any("manual copy went stale" in w for w in rep.warnings)


def test_features_true_without_source_set(site):
    def mutate(p):
        p["models_meta"][1]["features"] = True  # source_set stays null
    rep = run(site, mutate)
    assert any("untagged model" in e for e in rep.errors)


def test_two_default_models(site):
    def mutate(p):
        p["models_meta"][1]["default"] = True
    rep = run(site, mutate)
    assert any("exactly one default" in e for e in rep.errors)
