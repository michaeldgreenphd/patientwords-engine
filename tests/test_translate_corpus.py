"""Full-corpus translation path (owner request 2026-07-14): collection scope,
holdout sealing, dedupe, workflow wiring, and the collector's txcorpus guard.
"""

import importlib.util
import json
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tc = _load("translate_corpus")
ts = _load("translation_scale")


def _write_batch(d, stem, pairs):
    (d / f"{stem}.json").write_text(json.dumps(pairs), encoding="utf-8")


def test_collect_corpus_scope_holdout_dedupe(tmp_path):
    sim = tmp_path / "simulated"
    sim.mkdir()
    dash = tmp_path / "dashboard.json"
    dash.write_text(json.dumps({"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}))
    # Tier A observational batch: kept even though its phrases repeat later
    _write_batch(sim, "pairs_20260707T000000Z", [
        {"top_prompt": "CL1", "bottom_prompt": "PT1", "target_clinical_token": "t1"},
    ])
    # Tier B batch: holdout phrase withheld, duplicate patient sentence deduped
    _write_batch(sim, "pairs_20260711T000000Z", [
        {"top_prompt": "The patient reports symptom 4.", "bottom_prompt": "PT-HOLD",
         "target_clinical_token": "t2"},           # holdout by pinned hash
        {"top_prompt": "CL3", "bottom_prompt": "PT1", "target_clinical_token": "t3"},  # dup
        {"top_prompt": "CL4", "bottom_prompt": "PT4", "target_clinical_token": "t4"},
    ])
    # non-observational stems never enter the corpus
    _write_batch(sim, "dialects_20260708T000000Z", [
        {"top_prompt": "CLD", "bottom_prompt": "PTD", "target_clinical_token": "td"},
    ])
    _write_batch(sim, "txcorpus_20260714T000000Z", [
        {"top_prompt": "CLX", "bottom_prompt": "PTX", "target_clinical_token": "tx"},
    ])
    corpus = tc.collect_corpus(sim, dash)
    patients = [c["patient_prompt"] for c in corpus]
    assert patients == ["PT1", "PT4"]
    assert corpus[0]["source_batch"] == "pairs_20260707T000000Z"  # first occurrence wins


def test_workflow_translate_corpus_branch():
    wf = _ROOT / ".github" / "workflows" / "scenario_generation.yml"
    parsed = yaml.safe_load(wf.read_text(encoding="utf-8"))
    assert parsed["concurrency"]["cancel-in-progress"] is False
    text = wf.read_text(encoding="utf-8")
    assert '"$TASK" = "translate_corpus"' in text
    assert "data/simulated/txcorpus_${STAMP}.json" in text
    assert "scripts/translate_corpus.py" in text
    # the medlang-generate call must not run for the corpus branch
    assert "else\n            if [ -n \"$GEN_MODEL\" ]" in text


def test_collector_skips_txcorpus_dirs():
    src = (_ROOT / "scripts" / "urgency_shift.py").read_text(encoding="utf-8")
    assert 'stem.startswith("txcorpus_")' in src


def test_txcorpus_stem_never_matches_confirmatory_regex():
    assert not tc._OBS_RE.fullmatch("txcorpus_20260714T000000Z")
    rigor_src = (_ROOT / "scripts" / "paired_stats_rigor.py").read_text(encoding="utf-8")
    assert r"pairs_\d{8}T\d{6}Z" in rigor_src


def test_translation_scale_join_and_metrics(tmp_path):
    sim = tmp_path / "simulated"
    sim.mkdir()
    _write_batch(sim, "txcorpus_20260715T000000Z", [
        {"top_prompt": "CL1", "bottom_prompt": "TR1", "target_clinical_token": "t1",
         "generation": {"source_batch": "pairs_20260711T000000Z", "source_index": 2,
                        "original_patient": "PT1"}},
    ])
    troot = tmp_path / "trace_out"
    (troot / "txcorpus_20260715T000000Z__m1").mkdir(parents=True)
    (troot / "txcorpus_20260715T000000Z__m1" / "batch_summary.part_01.json").write_text(json.dumps(
        {"graph_model": "m1", "results": [{
            "index": 1, "probabilities": {"clinical": 0.5, "patient": 0.4},
            "predictive_spread": {"clinical": [["a", 0.5]], "patient": [["a", 0.4]]}}]}))
    (troot / "pairs_20260711T000000Z__m1").mkdir(parents=True)
    (troot / "pairs_20260711T000000Z__m1" / "batch_summary.part_01.json").write_text(json.dumps(
        {"graph_model": "m1", "results": [{
            "index": 2, "probabilities": {"clinical": 0.5, "patient": 0.1},
            "predictive_spread": {"clinical": [["a", 0.5]], "patient": [["b", 0.2]]}}]}))
    out = ts.analyze(troot, sim)
    s = out["per_model"]["m1"]
    assert s["n"] == 1
    assert abs(s["mean_recovery"] - 0.3) < 1e-9          # 0.4 translated vs 0.1 patient
    assert abs(s["mean_gap_closed"] - 0.75) < 1e-9       # 0.3 recovered of the 0.4 gap
    assert s["top_restored"] == 1 and s["top_lost"] == 0
