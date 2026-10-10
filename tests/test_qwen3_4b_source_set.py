"""qwen3-4b's feature source set (transcoder-hp, registered 2026-10-09) and its consumers.

Registering the set changes which fetcher tags qwen3-4b's features. It must not
change the hosted graph request (graphs stay on the server's default source
set, as before), and it must not make qwen3-4b's clinical_mass publishable:
that waits on the owner's calibration decision (scripts/feature_models.py).
No network: the hosted API and the feature API are both faked.
"""
from __future__ import annotations

import copy
import functools
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import medlang_circuits.batch_eval as batch_eval
import medlang_circuits.graph_client as gc
from medlang_circuits.neuronpedia_features import (
    MODEL_SOURCE_SETS,
    FeatureFetcher,
    NullFetcher,
    default_source_set,
)

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feature_models = _load("feature_models")


def cantor(layer: int, index: int) -> int:
    """circuit-tracer's schema-1 node id: the Cantor pairing of (layer, index)."""
    return (layer + index) * (layer + index + 1) // 2 + index


# ---------------------------------------------------------------------------
# Registry and fetcher selection
# ---------------------------------------------------------------------------


def test_qwen3_4b_registers_transcoder_hp_and_the_others_stay_unregistered():
    assert MODEL_SOURCE_SETS["qwen3-4b"] == "transcoder-hp"
    assert MODEL_SOURCE_SETS["gemma-2-2b"] == "gemmascope-transcoder-16k"
    assert MODEL_SOURCE_SETS["gemma-3-4b-it"] is None
    assert MODEL_SOURCE_SETS["qwen3-1.7b"] is None
    assert default_source_set("qwen3-4b") == "transcoder-hp"


def test_cantor_helper_matches_a_production_qwen3_4b_node():
    # node 0_116505_1 of Neuronpedia's apps/graph/tests/fixtures/graphs/123-qwen3-4b-transcoder-hp.json
    assert cantor(0, 116505) == 6786882270
    assert cantor(1, 19591) == 191952619


def test_fetcher_requests_layer_dash_transcoder_hp(tmp_path, monkeypatch):
    fetcher = FeatureFetcher(model_id="qwen3-4b", cache_dir=tmp_path)
    assert fetcher.source_set == "transcoder-hp"
    seen = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"explanations": [{"description": "a label"}], "activations": []}

    monkeypatch.setattr(fetcher._session, "get", lambda url, timeout=None: seen.append(url) or _Resp())
    details = fetcher.get(1, 19591)
    assert details["description"] == "a label"
    assert seen == ["https://www.neuronpedia.org/api/feature/qwen3-4b/1-transcoder-hp/19591"]
    assert (tmp_path / "qwen3-4b" / "1-transcoder-hp" / "19591.json").is_file()


# ---------------------------------------------------------------------------
# run_batch on qwen3-4b: real fetcher, graph request unchanged, steering set
# ---------------------------------------------------------------------------


def _qwen_graph() -> dict[str, Any]:
    """A schema-1 qwen3-4b graph: three transcoder features, one error node, one logit."""
    feats = [(3, 42, 1), (7, 7, 2), (9, 1, 3)]
    nodes = [{"node_id": "E_100_0", "feature": 100, "layer": "E", "ctx_idx": 0,
              "feature_type": "embedding", "clerp": "the"}]
    nodes += [{"node_id": f"{lay}_{i}_{c}", "feature": cantor(lay, i), "layer": str(lay), "ctx_idx": c,
               "feature_type": "cross layer transcoder", "clerp": ""} for lay, i, c in feats]
    nodes += [{"node_id": "err_5_2", "feature": None, "layer": "5", "ctx_idx": 2,
               "feature_type": "mlp reconstruction error", "clerp": ""},
              {"node_id": "L_999_3", "feature": 999, "layer": "36", "ctx_idx": 3,
               "feature_type": "logit", "clerp": "jumps (p=0.81)"}]
    links = [{"source": "E_100_0", "target": "3_42_1", "weight": 2.0},
             {"source": "3_42_1", "target": "7_7_2", "weight": 4.0},
             {"source": "7_7_2", "target": "L_999_3", "weight": 6.0},
             {"source": "9_1_3", "target": "L_999_3", "weight": -1.5}]
    return {"metadata": {"slug": "q", "scan": "qwen3-4b", "schema_version": 1, "prompt": "p",
                         "prompt_tokens": ["the", " a", " b", " c"]},
            "qParams": {}, "nodes": nodes, "links": links}


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _Session:
    def __init__(self, parent):
        self.parent = parent
        self.headers = {}

    def post(self, url, json=None, timeout=None):
        self.parent.bodies.append(copy.deepcopy(json))
        return _Resp({})

    def get(self, url, timeout=None):
        return _Resp({"url": "https://files.example/graph.json"})


class _HostedAPI:
    """Stands in for graph_client.requests: records every /api/graph/generate body."""

    def __init__(self):
        self.bodies: list[dict[str, Any]] = []

    def Session(self):
        return _Session(self)

    def get(self, url, timeout=None):
        return _Resp(_qwen_graph())


class _OfflineFetcher(FeatureFetcher):
    """The real FeatureFetcher (same source-set resolution), with the feature API faked."""

    built: list[_OfflineFetcher] = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.urls: list[str] = []
        _OfflineFetcher.built.append(self)

    def _fetch_raw(self, layer, index):
        self.urls.append(f"/api/feature/{self.model_id}/{layer}-{self.source_set}/{index}")
        return {"explanations": [{"description": f"label {layer}/{index}"}], "activations": []}


@pytest.fixture
def qwen_batch(tmp_path, monkeypatch):
    api = _HostedAPI()
    monkeypatch.setattr(gc, "requests", api)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    monkeypatch.delenv(gc.GRAPH_MODEL_ENV_VAR, raising=False)
    _OfflineFetcher.built = []
    monkeypatch.setattr(batch_eval, "FeatureFetcher",
                        functools.partial(_OfflineFetcher, cache_dir=tmp_path / "cache"))
    pairs = tmp_path / "pairs.json"
    pairs.write_text(json.dumps([{"top_prompt": "one phrasing of it", "bottom_prompt": "another phrasing of it"}]),
                     encoding="utf-8")
    return api, pairs, tmp_path / "out"


def test_run_batch_tags_qwen3_4b_with_transcoder_hp(qwen_batch):
    api, pairs, out = qwen_batch
    batch_eval.run_batch(str(pairs), out_dir=str(out), graph_model="qwen3-4b",
                         use_llm_translation=False, dpi=50)
    assert len(_OfflineFetcher.built) == 1
    fetcher = _OfflineFetcher.built[0]
    assert not isinstance(fetcher, NullFetcher) and fetcher.source_set == "transcoder-hp"
    # node (layer, index) decoded from the Cantor id reaches the transcoder-hp feature URL
    assert set(fetcher.urls) == {"/api/feature/qwen3-4b/3-transcoder-hp/42",
                                 "/api/feature/qwen3-4b/7-transcoder-hp/7",
                                 "/api/feature/qwen3-4b/9-transcoder-hp/1"}
    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["graph_model"] == "qwen3-4b" and summary["source_set"] == "transcoder-hp"
    tagged = json.loads((out / "pair_01_clinical.tagged.json").read_text(encoding="utf-8"))
    descs = {n["medlang"]["description"] for n in tagged["nodes"] if n["feature_type"] == "cross layer transcoder"}
    assert descs == {"label 3/42", "label 7/7", "label 9/1"}
    # the tagger records which source set the labels came from (read by the calibration script)
    assert tagged["metadata"]["medlang_summary"]["feature_source_set"] == "transcoder-hp"


def test_registration_leaves_the_hosted_graph_request_unchanged(qwen_batch):
    # Graphs stay on Neuronpedia's default source set: no sourceSetName unless --source-set is passed.
    api, pairs, out = qwen_batch
    batch_eval.run_batch(str(pairs), out_dir=str(out), graph_model="qwen3-4b",
                         use_llm_translation=False, dpi=50)
    assert len(api.bodies) == 2  # clinical + patient
    for body in api.bodies:
        assert body["modelId"] == "qwen3-4b"
        assert "sourceSetName" not in body
        assert set(body) == {"modelId", "prompt", "slug", "maxNLogits", "desiredLogitProb",
                             "nodeThreshold", "edgeThreshold", "maxFeatureNodes"}


def test_explicit_source_set_still_reaches_the_graph_request(qwen_batch):
    api, pairs, out = qwen_batch
    batch_eval.run_batch(str(pairs), out_dir=str(out), graph_model="qwen3-4b", source_set="other-set",
                         use_llm_translation=False, dpi=50)
    assert [b["sourceSetName"] for b in api.bodies] == ["other-set", "other-set"]
    assert _OfflineFetcher.built[0].source_set == "other-set"


def test_steering_uses_the_fetchers_source_set(qwen_batch, monkeypatch):
    # Steering names features <layer>-<source set>; on qwen3-4b that must be transcoder-hp,
    # not steer_ablate's gemma default.
    _api, pairs, out = qwen_batch
    seen = {}
    for name in ("_steer_validation", "_steer_boost", "_steer_placebo"):
        monkeypatch.setattr(batch_eval, name,
                            lambda prompt, graph, k, source_set=None, _n=name: seen.setdefault(_n, source_set) and {})
    batch_eval.run_batch(str(pairs), out_dir=str(out), graph_model="qwen3-4b", use_llm_translation=False,
                         dpi=50, steer_validate=1, steer_boost=1, steer_placebo=1)
    assert seen == {"_steer_validation": "transcoder-hp", "_steer_boost": "transcoder-hp",
                    "_steer_placebo": "transcoder-hp"}


def test_unregistered_models_still_trace_with_null_fetcher(qwen_batch, monkeypatch):
    _api, pairs, out = qwen_batch
    monkeypatch.setattr(batch_eval, "FeatureFetcher", FeatureFetcher)  # the real one raises for None
    batch_eval.run_batch(str(pairs), out_dir=str(out), graph_model="gemma-3-4b-it",
                         use_llm_translation=False, dpi=50)
    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["source_set"] is None


# ---------------------------------------------------------------------------
# The publication gate: calibrated (model, source set) pairs only
# ---------------------------------------------------------------------------


def test_calibrated_pairs_are_gemma_with_its_registered_set():
    assert feature_models.CALIBRATED_FEATURE_SOURCES == frozenset({("gemma-2-2b", "gemmascope-transcoder-16k")})
    assert feature_models.CALIBRATED_FEATURE_MODELS == frozenset({"gemma-2-2b"})
    # every calibrated pair is a model's registered default set
    assert all(MODEL_SOURCE_SETS.get(m) == s for m, s in feature_models.CALIBRATED_FEATURE_SOURCES)


@pytest.mark.parametrize("model, source_set, expected", [
    ("gemma-2-2b", "gemmascope-transcoder-16k", True),
    ("gemma-2-2b", None, False),            # logits / activation-patch lanes: NullFetcher artifact
    (None, "gemmascope-transcoder-16k", True),   # pre-cross-model summaries name no model
    ("qwen3-4b", "transcoder-hp", False),   # labelled, not calibrated
    ("qwen3-4b", None, False),
    # Regression (Codex review of PR #93): gemma tagged from another set via --source-set
    ("gemma-2-2b", "some-other-set", False),
    (None, "some-other-set", False),
])
def test_clinical_mass_publishable(model, source_set, expected):
    assert feature_models.clinical_mass_publishable(model, source_set) is expected


def test_exporters_gate_each_row_on_the_shared_pair_rule():
    for name in ("export_frontend_simulated.py", "export_archive.py"):
        src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "clinical_mass_publishable" in src and "FEATURED" not in src, name


STAMP = "20260801T000000Z"
STEM = f"pairs_{STAMP}"


def _result(index: int, clinical: str, mass: float) -> dict[str, Any]:
    return {"index": index, "prompts": {"clinical": clinical, "patient": f"{clinical} plain"},
            "probabilities": {"clinical": 0.4, "patient": 0.2}, "language_penalty": -0.2,
            "target_token": 'Output " tok"', "clinical_mass": {"clinical": mass, "patient": mass - 0.1},
            "predictive_spread": {"clinical": [['Output " tok"', 0.4]], "patient": [['Output " other"', 0.3]]}}


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


ROWS = ["zq open words 0 so a", "zq open words 1 so a"]   # explore-split phrases


def _engine(engine: Path, qwen_parts: dict[str, list[dict[str, Any]]]) -> None:
    """A minimal engine checkout: per stamp, a gemma-2-2b hosted trace and the given qwen3-4b parts."""
    # no Tier B start covers these stamps, so nothing is withheld
    _write(engine / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-09-30T00:00:00Z"}})
    for stamp, parts in qwen_parts.items():
        stem = f"pairs_{stamp}"
        _write(engine / "data" / "simulated" / f"{stem}.json",
               [{"top_prompt": r, "bottom_prompt": f"{r} plain", "target_clinical_token": " tok"} for r in ROWS])
        _write(engine / "data" / "simulated" / f"{stem}.report.json", {"accepted": 2})
        _write(engine / "trace_out" / stem / "batch_summary.part_01.json",
               {"graph_model": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k", "backend": "hosted",
                "results": [_result(i, r, 0.3) for i, r in enumerate(ROWS, start=1)]})
        for n, part in enumerate(parts, start=1):
            _write(engine / "trace_out" / f"{stem}__qwen3-4b" / f"batch_summary.part_{n:02d}.json",
                   {**part, "results": [_result(i, r, 0.5) for i, r in enumerate(ROWS, start=1)]})
        for d in (stem, f"{stem}__qwen3-4b"):
            for i in (1, 2):
                _write(engine / "trace_out" / d / f"index_{i:02d}.html", f"<html>{d} {i}</html>")


def _export(engine: Path, site: Path, stamps: str) -> subprocess.CompletedProcess:
    (site / "data").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "export_frontend_simulated.py"),
                           "--engine", str(engine), "--frontend", str(site), "--stamps", stamps,
                           "--models", "gemma-2-2b,qwen3-4b"],
                          capture_output=True, text=True, cwd=str(engine))


HOSTED_TAGGED = {"graph_model": "qwen3-4b", "source_set": "transcoder-hp", "backend": "hosted"}
HOSTED_UNTAGGED = {"graph_model": "qwen3-4b", "source_set": None, "backend": "hosted"}
LOGITS = {"graph_model": "qwen3-4b", "source_set": None, "backend": "logits"}


def test_exporter_keeps_nulling_qwen3_4b_clinical_mass(tmp_path):
    engine, site = tmp_path / "engine", tmp_path / "site"
    _engine(engine, {STAMP: [HOSTED_TAGGED]})
    proc = _export(engine, site, STAMP)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    assert len(payload["scenarios"]) == 2
    for s in payload["scenarios"]:
        assert s["models"]["gemma-2-2b"]["clinical_mass"] == {"clinical": 0.3, "patient": pytest.approx(0.2)}
        assert s["models"]["qwen3-4b"]["clinical_mass"] is None
        assert s["models"]["qwen3-4b"]["prob_clinical"] == 0.4  # behavior still published
    meta = {m["id"]: m for m in payload["models_meta"]}
    assert meta["gemma-2-2b"]["features"] is True
    assert meta["qwen3-4b"]["features"] is False
    assert meta["qwen3-4b"]["source_set"] == "transcoder-hp"  # recorded, not published as mass


def test_exporter_refuses_a_model_whose_traces_mix_source_sets(tmp_path):
    # Regression (Codex review of PR #93): models_meta names one source set per model, and
    # took the first stamp's, so an untagged and a transcoder-hp qwen3-4b trace in one export
    # had all their scenarios described by whichever came first.
    engine, site = tmp_path / "engine", tmp_path / "site"
    later = "20260802T000000Z"
    _engine(engine, {STAMP: [HOSTED_UNTAGGED], later: [HOSTED_TAGGED]})
    proc = _export(engine, site, f"{STAMP},{later}")
    assert proc.returncode != 0
    assert "refusing" in proc.stderr and "qwen3-4b" in proc.stderr
    assert "untagged" in proc.stderr and "transcoder-hp" in proc.stderr
    assert not (site / "data" / "simulated_scenarios.json").exists()   # nothing written
    # within one trace dir too
    engine2 = tmp_path / "engine2"
    _engine(engine2, {STAMP: [HOSTED_UNTAGGED, HOSTED_TAGGED]})
    assert _export(engine2, tmp_path / "site2", STAMP).returncode != 0


def test_exporter_refuses_trace_part_with_mismatched_model(tmp_path):
    # Regression (Codex review of PR #93, thread 4234427502): a stale or misplaced part
    # naming another model (e.g. gemma part under __qwen3-4b) would publish mass while
    # models_meta emits features:false, breaking frontend contracts.
    engine, site = tmp_path / "engine", tmp_path / "site"
    _engine(engine, {STAMP: [HOSTED_TAGGED]})
    foreign_part = engine / "trace_out" / f"{STEM}__qwen3-4b" / "batch_summary.part_02.json"
    _write(foreign_part, {
        "graph_model": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k", "backend": "hosted",
        "results": [_result(1, ROWS[0], 0.3)]
    })
    proc = _export(engine, site, STAMP)
    assert proc.returncode != 0
    assert "refusing: trace part" in proc.stderr
    assert "gemma-2-2b" in proc.stderr and "qwen3-4b" in proc.stderr
    assert not (site / "data" / "simulated_scenarios.json").exists()


def test_logits_parts_are_not_a_source_set_and_meta_names_the_graphs_set(tmp_path):
    # a logits-lane part has no graph: its null source set is no tagging claim. models_meta
    # names the hosted parts' set even when the first stamp's metadata came from a logits dir.
    engine, site = tmp_path / "engine", tmp_path / "site"
    later = "20260802T000000Z"
    _engine(engine, {STAMP: [LOGITS], later: [HOSTED_TAGGED]})
    proc = _export(engine, site, f"{STAMP},{later}")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    meta = {m["id"]: m for m in payload["models_meta"]}
    assert meta["qwen3-4b"]["source_set"] == "transcoder-hp"
    assert all(s["models"]["qwen3-4b"]["clinical_mass"] is None for s in payload["scenarios"])


def test_export_archive_leaves_qwen3_4b_clinical_mass_empty(tmp_path):
    engine = tmp_path / "engine"
    _engine(engine, {STAMP: [HOSTED_TAGGED]})
    out = tmp_path / "archive"
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_archive.py"),
                           "--engine", str(engine), "--out", str(out)],
                          capture_output=True, text=True, cwd=str(engine))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    rows = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(row["graph_model"], []).append(row)
    assert len(by_model["qwen3-4b"]) == 2 and len(by_model["gemma-2-2b"]) == 2
    for row in by_model["qwen3-4b"]:
        assert row["has_features"] is False
        assert row["clinical_mass_clinical"] is None and row["clinical_mass_patient"] is None
        assert row["prob_clinical"] == 0.4                     # behavior still exported
    for row in by_model["gemma-2-2b"]:
        assert row["has_features"] is True and row["clinical_mass_clinical"] == 0.3
    csv_text = out.with_suffix(".csv").read_text(encoding="utf-8")
    qwen_lines = [line for line in csv_text.splitlines() if ",qwen3-4b," in line]
    assert len(qwen_lines) == 2 and all(line.endswith(",,") for line in qwen_lines)  # empty mass columns


def _gemma_other_set(engine: Path) -> None:
    """Re-tag the gemma-2-2b part as if traced with an explicit, uncalibrated --source-set."""
    part = engine / "trace_out" / STEM / "batch_summary.part_01.json"
    summary = json.loads(part.read_text(encoding="utf-8"))
    summary["source_set"] = "some-other-set"
    part.write_text(json.dumps(summary), encoding="utf-8")


def test_exporter_nulls_gemma_mass_tagged_from_an_uncalibrated_set(tmp_path):
    # Regression (Codex review of PR #93): the gate was model-only, so gemma traced with
    # another --source-set published its clinical_mass.
    engine, site = tmp_path / "engine", tmp_path / "site"
    _engine(engine, {STAMP: [HOSTED_TAGGED]})
    _gemma_other_set(engine)
    proc = _export(engine, site, STAMP)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    assert all(s["models"]["gemma-2-2b"]["clinical_mass"] is None for s in payload["scenarios"])
    assert all(s["clinical_mass"] is None for s in payload["scenarios"])     # the top-level mirror too
    meta = {m["id"]: m for m in payload["models_meta"]}
    assert meta["gemma-2-2b"]["features"] is False
    assert meta["gemma-2-2b"]["source_set"] == "some-other-set"


def test_export_archive_nulls_gemma_mass_tagged_from_an_uncalibrated_set(tmp_path):
    engine = tmp_path / "engine"
    _engine(engine, {STAMP: [HOSTED_TAGGED]})
    _gemma_other_set(engine)
    out = tmp_path / "archive"
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_archive.py"),
                           "--engine", str(engine), "--out", str(out)],
                          capture_output=True, text=True, cwd=str(engine))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    rows = [r for r in json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
            if r["graph_model"] == "gemma-2-2b"]
    assert len(rows) == 2
    assert all(r["has_features"] is False and r["clinical_mass_clinical"] is None for r in rows)


def test_export_tag_mass_excludes_labelled_but_uncalibrated_models(tmp_path, monkeypatch):
    ext = _load("export_tag_mass")
    monkeypatch.setattr(ext, "sealed_pair", lambda *a, **k: False)
    root = tmp_path / "trace_out"
    row = {"index": 1, "prompts": {"clinical": "c"}, "clinical_mass": {"clinical": 0.3, "patient": 0.2},
           "error_share": {"clinical": 0.1, "patient": 0.1}}
    _write(root / "pairs_F" / "batch_summary.part_01.json",
           {"graph_model": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k", "results": [row]})
    _write(root / "pairs_F__qwen3-4b" / "batch_summary.part_01.json",
           {"graph_model": "qwen3-4b", "source_set": "transcoder-hp",
            "results": [{**row, "clinical_mass": {"clinical": 0.9, "patient": 0.9}}]})
    acc = ext.collect(str(root))
    assert len(acc["clinical"]) == 1 and len(acc["patient"]) == 1
    assert acc["clinical"][0][0] == pytest.approx(0.9 * 0.3)   # gemma's row, not qwen's


def _retrace_run(root: Path, run: str, model: str, source_set: str | None, mass: float, p_clin: float = 0.5):
    _write(root / run / "batch_summary.part_01.json", {
        "backend": "hosted", "graph_model": model, "source_set": source_set,
        "results": [{"prompts": {"clinical": "clin A", "patient": "pat A"},
                     "probabilities": {"clinical": p_clin, "patient": 0.2},
                     "clinical_mass": {"clinical": mass, "patient": mass}}]})


def test_retrace_consistency_never_compares_mass_across_source_sets(tmp_path):
    from scripts.retrace_consistency import collect, compare

    # a calibrated model traced once untagged and once tagged: a tagging change, not noise
    _retrace_run(tmp_path, "run_null", "gemma-2-2b", None, 0.0)
    _retrace_run(tmp_path, "run_tagged", "gemma-2-2b", "gemmascope-transcoder-16k", 0.4)
    rows = compare(collect(tmp_path))
    assert rows[0]["cmass_param_variants"] == 1          # the untagged run's mass is not read at all
    assert rows[0]["cmass_same_params_spread"] is None


def test_retrace_consistency_keeps_uncalibrated_mass_out_of_every_aggregate(tmp_path):
    # Regression (Codex review of PR #93): two tagged qwen3-4b retraces share one
    # source-set signature, so their mass spread entered the global maximum.
    from scripts.retrace_consistency import collect, compare

    _retrace_run(tmp_path, "run_a", "qwen3-4b", "transcoder-hp", 0.1, p_clin=0.5)
    _retrace_run(tmp_path, "run_b", "qwen3-4b", "transcoder-hp", 0.6, p_clin=0.4)
    _retrace_run(tmp_path, "run_c", "gemma-2-2b", "gemmascope-transcoder-16k", 0.30)
    _retrace_run(tmp_path, "run_d", "gemma-2-2b", "gemmascope-transcoder-16k", 0.31)
    rows = {r["model"]: r for r in compare(collect(tmp_path))}
    assert rows["qwen3-4b"]["spread_p_clinical"] == 0.1          # probability consistency kept
    assert rows["qwen3-4b"]["cmass_same_params_spread"] is None  # mass kept out
    assert rows["qwen3-4b"]["cmass_param_variants"] == 0
    assert rows["gemma-2-2b"]["cmass_same_params_spread"] == pytest.approx(0.01)


def test_interp_named_features_reads_calibrated_models_only():
    ia = _load("interp_analyses")
    gemma = {"graph_model": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k",
             "results": [{"top_path": {"clinical": "tok → [L5·C] gemma label → out"}}]}
    qwen = {"graph_model": "qwen3-4b", "source_set": "transcoder-hp",
            "results": [{"top_path": {"clinical": "tok → [L9·C] qwen label → out"}}]}
    out = ia.named_features([("pairs_F", gemma), ("pairs_F__qwen3-4b", qwen)])
    assert [e["label"] for e in out["C"]] == ["gemma label"]
