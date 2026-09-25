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
_PETRI_AUDIT = _MODULE_PATH.parent / "petri_audit"


def _engine_with_log(tmp_path, entries):
    """A scratch engine root: the real advice_eval.py, the real Petri package (the
    gate runs its pack check too, since 2026-09-24) and a disclosure log holding
    `entries` (never the repository's own log)."""
    engine = tmp_path / "engine"
    (engine / "scripts").mkdir(parents=True)
    (engine / "ops").mkdir()
    shutil.copy(_ADVICE_EVAL, engine / "scripts" / "advice_eval.py")
    shutil.copytree(_PETRI_AUDIT, engine / "scripts" / "petri_audit", ignore=shutil.ignore_patterns("__pycache__"))
    (engine / "ops" / "disclosure_log.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return engine


def _is_petri(cmd):
    return "scripts.petri_audit.cli" in cmd


def _fake_run(code, stdout="", stderr="", petri_code=0, petri_stdout="", petri_stderr=""):
    """A stand-in for subprocess.run: the advice check returns (code, stdout, stderr),
    the Petri check (petri_code, petri_stdout, petri_stderr)."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if _is_petri(cmd):
            return subprocess.CompletedProcess(cmd, petri_code, petri_stdout, petri_stderr)
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)
    return run, calls


@pytest.mark.parametrize("code", [1, 3, 120])
def test_repro_pack_gate_fails_on_any_nonzero_exit(tmp_path, code):
    """Regression: only exit 2 was an error, so a crash of the check (exit 1)
    passed the gate silently while hiding any escalation behind it."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    run_fn, calls = _fake_run(code, stderr="Traceback (most recent call last):\nKeyError: 'stimuli_file'")
    out, errors = vfc.repro_pack_gate(engine, run=run_fn)
    assert len(calls) == 2 and sum(map(_is_petri, calls)) == 1 and len(errors) == 1
    assert errors[0].startswith(f"repro-pack --check exited {code}") and "unverified" in errors[0]
    assert "KeyError: 'stimuli_file'" in errors[0]


def test_repro_pack_gate_exit_codes_zero_and_two(tmp_path):
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    assert vfc.repro_pack_gate(engine, run=_fake_run(0, "FRESH  v1  acme  s")[0]) == ("FRESH  v1  acme  s", [])
    out, errors = vfc.repro_pack_gate(engine, run=_fake_run(2, "ESCALATION: ...")[0])
    assert errors == [vfc.REPRO_PACK_STALE_MSG] and out == "ESCALATION: ..."


@pytest.mark.parametrize("code", [1, 3, 120])
def test_repro_pack_gate_fails_on_any_nonzero_exit_of_the_petri_check(tmp_path, code):
    """Since 2026-09-24 the gate also runs the Petri lane's pack check, whose packs gate
    the Multi-turn page (design note decision 16); any non-zero exit of it fails the
    gate with a message naming that lane, never the advice lane's."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    run_fn, calls = _fake_run(0, "skipped: 1 log entry of lane 'petri'", petri_code=code,
                              petri_stdout="UNREADABLE: entry 1", petri_stderr="Traceback\nKeyError: 'scope'")
    out, errors = vfc.repro_pack_gate(engine, run=run_fn)
    assert [c for c in calls if _is_petri(c)] == [[vfc.sys.executable, "-m", "scripts.petri_audit.cli", "repro-pack",
                                                   "--check", "--log", str(engine / "ops" / "disclosure_log.jsonl")]]
    assert len(errors) == 1 and errors[0].startswith(f"petri repro-pack --check exited {code}")
    assert "Petri vendor-pack currency is unverified" in errors[0] and "KeyError: 'scope'" in errors[0]
    assert out == "skipped: 1 log entry of lane 'petri'\nUNREADABLE: entry 1"


def test_repro_pack_gate_names_a_stale_sent_petri_pack_apart_from_the_advice_lanes(tmp_path):
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    out, errors = vfc.repro_pack_gate(engine, run=_fake_run(0, petri_code=2, petri_stdout="ESCALATION: petri")[0])
    assert errors == [vfc.PETRI_REPRO_PACK_STALE_MSG] and out == "ESCALATION: petri"
    out, errors = vfc.repro_pack_gate(engine, run=_fake_run(2, "ESCALATION: advice", petri_code=2,
                                                            petri_stdout="ESCALATION: petri")[0])
    assert errors == [vfc.REPRO_PACK_STALE_MSG, vfc.PETRI_REPRO_PACK_STALE_MSG]
    assert vfc.REPRO_PACK_STALE_MSG != vfc.PETRI_REPRO_PACK_STALE_MSG and "Petri" in vfc.PETRI_REPRO_PACK_STALE_MSG


def test_repro_pack_gate_skips_without_a_log(tmp_path):
    engine = tmp_path / "engine"
    engine.mkdir()
    run_fn, calls = _fake_run(1)
    assert vfc.repro_pack_gate(engine, run=run_fn) == ("", []) and calls == []


def test_repro_pack_gate_end_to_end_on_an_undeclared_foreign_entry(tmp_path):
    """The reproduced case, through the real check: a pack entry with no
    stimuli_file and no declared lane. Before 2026-09-23 the check exited 1 and the
    gate reported nothing; now the check names the entry (exit 3) and the gate fails.
    The Petri check counts the lane-less entry as the advice lane's and skips it."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    out, errors = vfc.repro_pack_gate(engine)
    assert "UNREADABLE: entry 1 (vpetri000001): missing manifest.stimuli_file" in out
    assert "skipped: 1 log entry of lane 'advice' (this check covers lane 'petri' only)" in out
    assert len(errors) == 1 and errors[0].startswith("repro-pack --check exited 3")


def test_repro_pack_gate_end_to_end_on_a_lane_neither_check_owns(tmp_path):
    engine = _engine_with_log(tmp_path, [{"pack_version": "vz000001", "lane": "zeta", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    out, errors = vfc.repro_pack_gate(engine)
    assert errors == [] and "skipped: 1 log entry of lane 'zeta' (this check covers lane 'advice' only)" in out
    assert "skipped: 1 log entry of lane 'zeta' (this check covers lane 'petri' only)" in out


def test_repro_pack_gate_end_to_end_on_a_petri_entry_the_petri_check_cannot_read(tmp_path):
    """A petri-lane entry: the advice check skips it (as before 2026-09-24), and the
    Petri check, which owns it, names it unreadable (exit 3), so the gate fails with
    the Petri lane's message."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "lane": "petri", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    out, errors = vfc.repro_pack_gate(engine)
    assert "skipped: 1 log entry of lane 'petri' (this check covers lane 'advice' only)" in out
    assert "UNREADABLE: entry 1 (vpetri000001): missing manifest.scope, manifest.inputs" in out
    assert len(errors) == 1 and errors[0].startswith("petri repro-pack --check exited 3")


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


def test_main_fails_when_the_petri_pack_check_cannot_read_the_log(site, tmp_path, monkeypatch, capsys):
    engine = _engine_with_log(tmp_path, [{"pack_version": "vpetri000001", "lane": "petri", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    assert _main(monkeypatch, site, engine) == 1
    out = capsys.readouterr().out
    assert "FAIL: petri repro-pack --check exited 3" in out
    assert "contract check: 1 error(s)" in out


def test_main_passes_the_same_site_when_the_pack_check_is_clean(site, tmp_path, monkeypatch, capsys):
    """The control for the tests above: the same valid site and scratch engine with
    a log both checks read cleanly give no error, so the failures above are the gate's."""
    engine = _engine_with_log(tmp_path, [{"pack_version": "vz000001", "lane": "zeta", "vendor": "acme",
                                          "manifest": {"run_ids": ["run_1"]}, "sent_utc": None}])
    assert _main(monkeypatch, site, engine) == 0
    assert "contract check: 0 error(s)" in capsys.readouterr().out


# ---- the Multi-turn page's publication gate (Codex, PR #39): a public page needs a sent, FRESH Petri pack

PUBLISHED_RUNS = ["run_200_1", "run_300_1"]


def _publish_multiturn(site, version="petri-v000000000001", conversations=True, summary=True, runs=PUBLISHED_RUNS):
    """The Multi-turn page's real data files in the site's data/ (what export_petri_multiturn.py writes once the page
    is public), the summary citing `version` as its vendor pack and `runs` as the runs it publishes. Placeholder
    content only."""
    data = site / "data"
    if summary:
        (data / "petri_multiturn_summary.json").write_text(json.dumps(
            {"status": {"final": True, "vendor_pack": {"version": version, "sent": None}},
             "provenance": {"runs": runs}}), encoding="utf-8")
    if conversations:
        (data / "petri_multiturn_conversations.json").write_text(json.dumps({"conversations": []}), encoding="utf-8")


def _samples_only(site):
    """The page's state today: only the synthetic .sample.json fixtures, which never make the data public."""
    data = site / "data"
    for name in ("petri_multiturn_summary.sample.json", "petri_multiturn_conversations.sample.json"):
        (data / name).write_text(json.dumps({"sample": True, "status": {"vendor_pack": {"version": None}}}),
                                 encoding="utf-8")


def _no_log_engine(tmp_path):
    engine = _engine_with_log(tmp_path, [])
    (engine / "ops" / "disclosure_log.jsonl").unlink()
    return engine


def test_multiturn_publication_reads_only_the_real_files(site):
    assert vfc.petri_publication(site) == (False, None, [], [])
    _samples_only(site)
    assert vfc.petri_publication(site) == (False, None, [], [])
    _publish_multiturn(site, version="petri-vabc")
    assert vfc.petri_publication(site) == (True, "petri-vabc", PUBLISHED_RUNS, [])
    _publish_multiturn(site, version=None)
    public, cited, runs, errors = vfc.petri_publication(site)
    assert public and cited is None and runs == PUBLISHED_RUNS and len(errors) == 1
    assert errors[0].startswith("petri_multiturn_summary.json :: $.status.vendor_pack.version :: the published summary "
                                "cites no Petri pack version")
    (site / "data" / "petri_multiturn_summary.json").write_text("{not json", encoding="utf-8")
    public, cited, runs, errors = vfc.petri_publication(site)
    assert public and cited is None and runs == [] and len(errors) == 1 and "cannot be read" in errors[0]
    assert vfc.petri_publication(None) == (False, None, [], [])


def test_public_conversations_without_the_summary_fail_publication(site):
    """Regression (Codex, PR #39): with only the conversations file on the site the page was public but cited no
    pack, and the gate fell back to accepting any sent, FRESH Petri pack. Per-model data with no citation fails."""
    _publish_multiturn(site, summary=False)
    public, cited, runs, errors = vfc.petri_publication(site)
    assert public and cited is None and runs == [] and len(errors) == 1
    assert errors[0].startswith("petri_multiturn_conversations.json :: the conversations file is public without "
                                "petri_multiturn_summary.json, so no page cites the Petri pack")


@pytest.mark.parametrize("runs", [None, [], "run_200_1", ["run_200_1", ""], ["run_200_1", 7], [" run_200_1"]])
def test_a_published_summary_must_name_its_runs(site, runs):
    """Regression (Codex, PR #39): the cited pack is bound to the runs the page publishes, so a summary that names
    none (or not as a list of run directory names) cannot be checked and fails."""
    _publish_multiturn(site, version="petri-vabc", runs=runs)
    public, cited, got, errors = vfc.petri_publication(site)
    assert public and cited == "petri-vabc" and got == [] and len(errors) == 1
    assert errors[0].startswith("petri_multiturn_summary.json :: $.provenance.runs :: the published summary names no "
                                "runs")


def test_repro_pack_gate_requires_a_sent_petri_pack_once_the_multiturn_data_is_public(tmp_path, site):
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    _publish_multiturn(site, version="petri-vabc")
    run_fn, calls = _fake_run(0, petri_code=4, petri_stdout="PUBLICATION: petri-vabc: no send is recorded")
    out, errors = vfc.repro_pack_gate(engine, run=run_fn, site=site)
    assert [c for c in calls if _is_petri(c)] == [[vfc.sys.executable, "-m", "scripts.petri_audit.cli", "repro-pack",
                                                   "--check", "--log", str(engine / "ops" / "disclosure_log.jsonl"),
                                                   "--require-sent", "--cited-version", "petri-vabc",
                                                   "--cited-run", "run_200_1", "--cited-run", "run_300_1"]]
    assert errors == [vfc.PETRI_PUBLICATION_UNMET_MSG] and "PUBLICATION: petri-vabc" in out
    run_fn, calls = _fake_run(0, petri_code=0)
    assert vfc.repro_pack_gate(engine, run=run_fn, site=site)[1] == []


def test_repro_pack_gate_is_unchanged_while_the_multiturn_page_is_unpublished(tmp_path, site):
    """Today's state: no real Multi-turn file (the samples at most). The Petri check runs as before, without the
    publication requirement, and a missing log still skips both checks."""
    _samples_only(site)
    engine = _engine_with_log(tmp_path, [{"pack_version": "v1"}])
    run_fn, calls = _fake_run(0, petri_code=0)
    assert vfc.repro_pack_gate(engine, run=run_fn, site=site) == ("", [])
    assert [c for c in calls if _is_petri(c)][0][-2:] == ["--log", str(engine / "ops" / "disclosure_log.jsonl")]
    run_fn, calls = _fake_run(1)
    assert vfc.repro_pack_gate(_no_log_engine(tmp_path / "x"), run=run_fn, site=site) == ("", []) and calls == []


def test_repro_pack_gate_end_to_end_on_public_multiturn_data_with_no_pack(tmp_path, site):
    """The reproduced case, through the real check: the page's data is public and no Petri pack was ever built (no
    log at all). Before the fix the gate skipped both checks and passed; now the Petri check runs with the requirement
    and fails (exit 4), and the gate names it."""
    _publish_multiturn(site)
    out, errors = vfc.repro_pack_gate(_no_log_engine(tmp_path), site=site)
    assert "never-built" in out and "PUBLICATION:" in out
    assert errors == [vfc.PETRI_PUBLICATION_UNMET_MSG]


def test_repro_pack_gate_end_to_end_on_public_multiturn_data_citing_an_unsent_pack(tmp_path, site):
    """A Petri pack built and logged, never sent, which the public summary cites. Unsent and unescalated, the plain
    check exits 0; the publication requirement fails it."""
    entry = {"pack_version": "petri-v000000000001", "lane": "petri", "vendor": "acme", "sent_utc": None,
             "manifest": {"scope": "w2_register_contrast",
                          "inputs": {k: "absent" for k in ("vendor", "runs_dir", "analysis", "plan", "claims",
                                                            "seeds", "lock", "repo_root")} | {"run_dirs": []},
                          "depends_on": {"prompt_refs": {}, "seed_ids": []}, "state": {}}}
    engine = _engine_with_log(tmp_path, [entry])
    _publish_multiturn(site, version="petri-v000000000001")
    out, errors = vfc.repro_pack_gate(engine, site=site)
    assert "PUBLICATION: the published page cites petri-v000000000001, whose send is not recorded" in out
    assert errors == [vfc.PETRI_PUBLICATION_UNMET_MSG]
    unpublished = tmp_path / "unpublished"
    unpublished.mkdir()
    assert vfc.repro_pack_gate(engine, site=unpublished)[1] == []      # the same log, the page not public: green


def test_main_fails_when_the_multiturn_data_is_public_without_a_sent_pack(site, tmp_path, monkeypatch, capsys):
    engine = _no_log_engine(tmp_path)
    _samples_only(site)
    assert _main(monkeypatch, site, engine) == 0                          # today: samples only, no log
    capsys.readouterr()
    _publish_multiturn(site)
    assert _main(monkeypatch, site, engine) == 1
    out = capsys.readouterr().out
    assert f"FAIL: {vfc.PETRI_PUBLICATION_UNMET_MSG}" in out and "contract check: 1 error(s)" in out
