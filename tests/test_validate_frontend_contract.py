"""Tests for scripts/validate_frontend_contract.py - the structural export gate.

scripts/ is not a package, so the module loads via importlib from its file
path (same pattern as test_fire_trigger.py). Fixtures build a minimal valid
site tree under tmp_path, then each test seeds one contract break and asserts
the validator names it. Abstract vocabulary only - no medical terms.
"""

import importlib.util
import json
import shutil
import subprocess
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


# ---- repro-pack gate (2026-09-23): any non-zero exit of the check is an error

_ADVICE_EVAL = _MODULE_PATH.parent / "advice_eval.py"


def _engine_with_log(tmp_path, entries):
    """A scratch engine root: the real advice_eval.py and a disclosure log holding
    `entries` (never the repository's own log)."""
    engine = tmp_path / "engine"
    (engine / "scripts").mkdir(parents=True)
    (engine / "ops").mkdir()
    shutil.copy(_ADVICE_EVAL, engine / "scripts" / "advice_eval.py")
    (engine / "ops" / "disclosure_log.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return engine


def _fake_run(code, stdout="", stderr=""):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)
    return run, calls


@pytest.mark.parametrize("code", [1, 3, 120])
def test_repro_pack_gate_fails_on_any_nonzero_exit(tmp_path, code):
    """Regression: only exit 2 was an error, so a crash of the check (exit 1)
    passed the gate silently while hiding any escalation behind it."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    run_fn, calls = _fake_run(code, stderr="Traceback (most recent call last):\nKeyError: 'stimuli_file'")
    out, errors = vfc.repro_pack_gate(engine, run=run_fn)
    assert len(calls) == 1 and len(errors) == 1
    assert f"exited {code}" in errors[0] and "unverified" in errors[0]
    assert "KeyError: 'stimuli_file'" in errors[0]


def test_repro_pack_gate_exit_codes_zero_and_two(tmp_path):
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    assert vfc.repro_pack_gate(engine, run=_fake_run(0, "FRESH  v1  acme  s")[0]) == ("FRESH  v1  acme  s", [])
    out, errors = vfc.repro_pack_gate(engine, run=_fake_run(2, "ESCALATION: ...")[0])
    assert errors == [vfc.REPRO_PACK_STALE_MSG] and out == "ESCALATION: ..."


def test_repro_pack_gate_skips_without_a_log(tmp_path):
    engine = tmp_path / "engine"
    engine.mkdir()
    run_fn, calls = _fake_run(1)
    assert vfc.repro_pack_gate(engine, run=run_fn) == ("", []) and calls == []


def test_repro_pack_gate_end_to_end_on_an_undeclared_foreign_entry(tmp_path):
    """The reproduced case, through the real check: a pack entry with no
    stimuli_file and no declared lane. Before 2026-09-23 the check exited 1 and the
    gate reported nothing; now the check names the entry (exit 3) and the gate fails."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    out, errors = vfc.repro_pack_gate(engine)
    assert "UNREADABLE: entry 1 (vpetri000001): missing manifest.stimuli_file" in out
    assert len(errors) == 1 and "exited 3" in errors[0]


def test_repro_pack_gate_end_to_end_on_a_declared_foreign_lane(tmp_path):
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "lane": "petri", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    out, errors = vfc.repro_pack_gate(engine)
    assert errors == [] and "skipped: 1 log entry of lane 'petri'" in out


def _main(monkeypatch, site, engine):
    monkeypatch.setattr("sys.argv", ["validate_frontend_contract.py", "--site", str(site), "--engine", str(engine)])
    with pytest.raises(SystemExit) as e:
        vfc.main()
    return e.value.code


def test_main_fails_when_the_pack_check_cannot_read_the_log(site, tmp_path, monkeypatch, capsys):
    """Regression (review of 2026-09-23): every gate test called repro_pack_gate
    directly, so dropping its errors from main() left the suite green. main() is
    what the Routine and publish-site-data run ('must be 0 errors'). On origin/main
    this exits 0: the check crashes (exit 1) and the gate passes it."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    assert _main(monkeypatch, site, engine) == 1
    out = capsys.readouterr().out
    assert "FAIL: repro-pack --check exited 3" in out
    assert "contract check: 1 error(s)" in out


def test_main_passes_the_same_site_when_the_pack_check_is_clean(site, tmp_path, monkeypatch, capsys):
    """The control for the test above: the same valid site and scratch engine with
    a log the check reads cleanly give no error, so the failure above is the gate's."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "lane": "petri", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    assert _main(monkeypatch, site, engine) == 0
    assert "contract check: 0 error(s)" in capsys.readouterr().out


# ---- owner-run files (2026-09-24): the Multi-turn pair is noted while absent, shape-checked once published

def _multiturn_pair(sample=False):
    """A minimal valid pair in the Multi-turn page's shapes; abstract vocabulary only."""
    summary = {"seed": 1, "status": {"final": True, "clinician_review": "pending",
                                     "vendor_pack": {"version": None, "sent": None}},
               "headline": {"row_id": "row5", "text": "alpha"}, "style_sentence": {"row_id": "x", "text": None},
               "primary": {"triples": 1, "negative": 1, "positive": 0, "tied": 0, "p_two_sided": 1.0,
                           "gate_p": 1.0, "gate_passed": False},
               "triples": [{"seed_id": "s1", "scenario_id": "sc1", "epoch": 1, "D": -0.5,
                            "partition": "prospective", "eligible": True}],
               "scenario_means": {"sc1": -0.5}, "repeats": [{"seed_id": "s1", "epochs": 1, "same_direction": 1}],
               "provenance": {"runs": ["run_1"], "analysis_commit": "c" * 40, "verify": "verify"}}
    conversations = {"seed": None,
                     "measures": [{"id": "m1", "row": ["tier", "k"], "label": "M", "kind": "ordinal",
                                   "values": ["lo", "hi"], "definition": None}],
                     "mechanisms": {"mech": {"title": "T", "question": "Q"}},
                     "seeds": [{"seed_id": "s1", "mechanism": "mech", "measures": ["m1"], "arms": ["a"],
                                "roles": [None], "hypotheses": ["H1"]}],
                     "conversations": [{"seed_id": "s1", "arm": "a", "epoch": 1, "identity": None, "rule": {},
                                        "exchanges": [{"user": "u", "reply": None, "reply_is_graded": True,
                                                       "interim": [], "vals": {"m1": {"v": "lo"}}}]}],
                     "example": {"seed_id": "s1", "turn": 1, "colloquial": "a", "lay_careful": "b", "clinical": "c"}}
    if sample:
        summary = {"sample": True, "_note": "SYNTHETIC", **summary}
        conversations = {"sample": True, "_note": "SYNTHETIC", **conversations, "seed": 1}   # the generator seed
    return summary, conversations


def _write_pair(site, pair, suffix=".json"):
    for stem, doc in zip(vfc.MT_PAIR, pair):
        (site / "data" / (stem + suffix)).write_text(json.dumps(doc), encoding="utf-8")


def test_owner_run_multiturn_pair_absent_is_a_note_never_a_warning(site):
    rep = run(site, strict=True)      # strict turns every warning into an error: none may name the pair
    assert not any("petri_multiturn" in e for e in rep.errors + rep.warnings)
    assert any("petri_multiturn_summary.json" in n and "owner-run" in n for n in rep.notes)


def test_owner_run_multiturn_pair_published_valid(site):
    _write_pair(site, _multiturn_pair())
    _write_pair(site, _multiturn_pair(sample=True), ".sample.json")
    rep = run(site, strict=True)
    assert not any("petri_multiturn" in e for e in rep.errors + rep.warnings) and rep.notes == []


def test_owner_run_multiturn_file_without_its_pair_is_an_error(site):
    (site / "data" / "petri_multiturn_summary.json").write_text(json.dumps(_multiturn_pair()[0]), encoding="utf-8")
    rep = run(site)
    assert any("published without its pair" in e for e in rep.errors)


def test_owner_run_multiturn_sample_flags_are_checked(site):
    summary, conversations = _multiturn_pair()
    _write_pair(site, ({"sample": True, **summary}, conversations))
    _write_pair(site, _multiturn_pair(), ".sample.json")
    rep = run(site)
    assert any("petri_multiturn_summary.json :: $.sample" in e for e in rep.errors)
    assert sum("must carry sample: true" in e for e in rep.errors) == 2


def test_owner_run_multiturn_shapes_are_checked(site):
    summary, conversations = _multiturn_pair()
    summary["triples"][0]["partition"] = "elsewhere"
    del summary["headline"]["text"]
    conversations["conversations"][0]["exchanges"][0]["vals"]["m9"] = {"v": "lo"}
    _write_pair(site, (summary, conversations))
    rep = run(site)
    assert any("$.triples[0].partition" in e for e in rep.errors)
    assert any("$.headline.text" in e for e in rep.errors)
    assert any("vals.m9" in e for e in rep.errors)


@pytest.mark.parametrize("sample", [False, True])
def test_owner_run_multiturn_summary_seed_is_required(site, sample):
    """Regression (Codex review of 2026-09-24): the summary's seed was nullable, so a published summary with its
    bootstrap seed removed passed --strict. The exporter always records one (a sample: its generator seed)."""
    summary, conversations = _multiturn_pair(sample)
    summary["seed"] = None
    suffix = ".sample.json" if sample else ".json"
    _write_pair(site, (summary, conversations), suffix)
    if not sample:
        _write_pair(site, _multiturn_pair(sample=True), ".sample.json")
    rep = run(site, strict=True)
    assert any(f"petri_multiturn_summary{suffix} :: $.seed" in e and "null" in e for e in rep.errors)


def test_owner_run_multiturn_conversations_seed_is_null_or_an_int(site):
    """The conversations file's seed is null when published (nothing in it is random); a sample records its generator
    seed, and a seed of another type is an error in either."""
    summary, conversations = _multiturn_pair()
    conversations["seed"] = "7"
    s_summary, s_conversations = _multiturn_pair(sample=True)
    s_conversations["seed"] = None
    _write_pair(site, (summary, conversations))
    _write_pair(site, (s_summary, s_conversations), ".sample.json")
    rep = run(site)
    assert any("petri_multiturn_conversations.json :: $.seed" in e and "wrong type" in e for e in rep.errors)
    assert any("petri_multiturn_conversations.sample.json :: $.seed" in e and "null" in e for e in rep.errors)
