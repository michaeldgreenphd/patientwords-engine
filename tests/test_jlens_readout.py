"""Hosted Jacobian-lens readout path (scripts/jlens_readout.py) - offline.

The Neuronpedia lens response schema is undocumented, so the parser is
defensive across the plausible shapes; these tests pin each recognized shape,
the depth classification, the unsupported-model probe contract, and the
trigger/workflow wiring (defaults dict completeness, part naming, distinct
output filenames so behavioral collectors never ingest lens readouts).
"""

import importlib.util
import json
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "scripts" / "jlens_readout.py"
_SPEC = importlib.util.spec_from_file_location("jlens_readout", _MODULE_PATH)
jlens = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(jlens)

_FT_PATH = _ROOT / "scripts" / "fire_trigger.py"
_FT_SPEC = importlib.util.spec_from_file_location("fire_trigger", _FT_PATH)
ft = importlib.util.module_from_spec(_FT_SPEC)
_FT_SPEC.loader.exec_module(ft)


def _response(layers):
    """Response with two positions; the FINAL one carries `layers`."""
    return {"meta": {}, "tokens": [{"layers": []}, {"layers": layers}], "done": {}}


def test_depth_profile_layers_shape_with_dict_tokens():
    resp = _response([
        {"layer": 3, "topTokens": [{"token": " alpha"}, {"token": "beta"}]},
        {"layer": 7, "topTokens": [{"token": " tgt"}, {"token": " alpha"}]},
    ])
    profile, status = jlens.depth_profile(resp, "tgt", topn=8)
    assert status == "ok"
    assert [(e["layer"], e["target_rank"]) for e in profile] == [(3, None), (7, 1)]
    assert profile[0]["top1"] == " alpha"


def test_depth_profile_pair_list_and_bare_string_tokens():
    resp = _response([
        {"layer": 1, "top": [[" tgt", 0.4], ["other", 0.1]]},
        {"layer": 2, "tokens": ["plain", " tgt"]},
    ])
    profile, status = jlens.depth_profile(resp, "tgt", topn=8)
    assert status == "ok"
    assert [(e["layer"], e["target_rank"]) for e in profile] == [(1, 1), (2, 2)]


def test_depth_profile_lens_wrapper_and_numeric_dict_shapes():
    wrapped = _response([])
    wrapped["tokens"][-1] = {"lens": {"JACOBIAN_LENS": {"layers": [
        {"layer": 5, "topTokens": [{"token": " tgt"}]}]}}}
    profile, status = jlens.depth_profile(wrapped, "tgt", topn=8)
    assert status == "ok" and profile[0]["layer"] == 5 and profile[0]["target_rank"] == 1

    numeric = _response([])
    numeric["tokens"][-1] = {"2": [" x"], "10": [" tgt"]}
    profile, status = jlens.depth_profile(numeric, "tgt", topn=8)
    assert status == "ok"
    assert [(e["layer"], e["target_rank"]) for e in profile] == [(2, None), (10, 1)]


def test_depth_profile_unrecognized_shape_reports_not_crashes():
    resp = _response([])
    resp["tokens"][-1] = {"mystery": True}
    profile, status = jlens.depth_profile(resp, "tgt", topn=8)
    assert profile == []
    assert "unrecognized layer shape" in status


def test_depth_profile_no_tokens():
    profile, status = jlens.depth_profile({"meta": {}}, "tgt", topn=8)
    assert profile == [] and status == "no tokens[] in response"


def test_confirmed_hosted_schema_results_top_tokens_with_meta_layers():
    """The REAL response shape, pinned 2026-07-11 against a committed
    gemma-2-2b raw response: tokens[i].results = [{type, top_tokens:
    [[strings] per layer]}], layer numbering from meta.layers_by_type."""
    resp = {
        "meta": {"kind": "meta", "model": "gemma-2-2b",
                 "layers_by_type": {"JACOBIAN_LENS": [0, 1, 2]},
                 "top_n": 8, "prompt_len": 2},
        "tokens": [
            {"kind": "token", "position": 0, "token": "x", "results": []},
            {"kind": "token", "position": 1, "token": " y", "is_generated": False,
             "results": [{"type": "JACOBIAN_LENS",
                          "top_tokens": [["</em>", " junk"],
                                         [" tgt", " other"],
                                         [" other", " tgt"]]}]},
        ],
        "done": {},
    }
    profile, status = jlens.depth_profile(resp, "tgt", topn=8)
    assert status == "ok"
    assert [(e["layer"], e["target_rank"], e["match"]) for e in profile] == [
        (0, None, None), (1, 1, "exact"), (2, 2, "exact")]


def test_confirmed_schema_layer_numbers_fall_back_positional_on_meta_mismatch():
    resp = {
        "meta": {"layers_by_type": {"JACOBIAN_LENS": [5]}},  # wrong length
        "tokens": [{"results": [{"type": "JACOBIAN_LENS",
                                 "top_tokens": [[" tgt"], [" x"]]}]}],
    }
    profile, status = jlens.depth_profile(resp, "tgt", topn=8)
    assert status == "ok"
    assert [e["layer"] for e in profile] == [0, 1]


def test_prefix_match_catches_wordpiece_and_singular_forms():
    # Observed on the batch-6 probe: target ' antivirals' surfaces in the lens
    # as ' antiviral' (singular / leading wordpiece). Prefix matches count;
    # short function words never do.
    variants = jlens.target_variants("antivirals")
    assert jlens.target_match(" antivirals", variants) == "exact"
    assert jlens.target_match(" antiviral", variants) == "prefix"
    assert jlens.target_match(" anti", variants) == "prefix"
    assert jlens.target_match(" ant", variants) is None      # under MIN_PREFIX_CHARS
    assert jlens.target_match(" the", jlens.target_variants("therapy")) is None  # strip floor
    assert jlens.target_match(" ther", jlens.target_variants("therapy")) == "prefix"
    assert jlens.target_match(" unrelated", variants) is None


def test_exhausted_500_retries_is_probe_negative_before_any_success(tmp_path, monkeypatch):
    """Observed 2026-07-11: the endpoint answers persistent 500s for unserved
    models. Before any successful measurement that records supported=false and
    exits 0; after a success it must abort loudly (a truncated batch is a
    failure, not evidence of non-support)."""
    pairs = [{"top_prompt": "clin", "bottom_prompt": "pat",
              "target_clinical_token": "tgt", "generation": {}}]
    pairs_path = tmp_path / "pairs_z.json"
    pairs_path.write_text(json.dumps(pairs), encoding="utf-8")

    class Fake500:
        status_code = 500
        text = "internal"

    class FakeSession:
        headers = {}

        def post(self, *a, **k):
            return Fake500()

    import sys
    import types
    fake_requests = types.SimpleNamespace(
        Session=lambda: FakeSession(),
        exceptions=types.SimpleNamespace(ConnectionError=OSError, Timeout=OSError),
    )
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    monkeypatch.setattr(jlens.time, "sleep", lambda s: None)
    out = tmp_path / "out"
    rc = jlens.main(["--pairs", str(pairs_path), "--model", "maybe-1b",
                     "--out", str(out), "--limit", "1"])
    assert rc == 0
    probe = json.loads((out / "jlens_probe.json").read_text(encoding="utf-8"))
    assert probe["supported"] is False
    assert "500" in probe["detail"] and "re-probe" in probe["detail"]

    # mid-batch: first prompt succeeds, second 500s forever -> must raise
    class FlakySession:
        headers = {}
        calls = 0

        def post(self, *a, **k):
            FlakySession.calls += 1
            if FlakySession.calls == 1:
                class OK:
                    status_code = 200
                    text = ""

                    def raise_for_status(self):
                        pass

                    def json(self):
                        return {"meta": {}, "tokens": [{"results": []}], "done": {}}
                return OK()
            return Fake500()

    fake_requests.Session = lambda: FlakySession()
    import pytest
    with pytest.raises(RuntimeError):
        jlens.main(["--pairs", str(pairs_path), "--model", "maybe-1b",
                    "--out", str(tmp_path / "out2"), "--limit", "1"])


def test_target_variants_cover_space_and_case_but_not_substrings():
    v = jlens.target_variants("sleep")
    assert {"sleep", " sleep", "Sleep", " Sleep"} == v
    assert "sleeping" not in v
    assert jlens.target_variants("") == set()
    assert jlens.target_variants(None) == set()


def test_classify_absent_suppressed_retained():
    readable = [{"layer": 10, "target_rank": 2, "top1": "x"},
                {"layer": 25, "target_rank": None, "top1": "y"}]
    absent = [{"layer": 10, "target_rank": None, "top1": "x"},
              {"layer": 25, "target_rank": None, "top1": "y"}]
    retained = [{"layer": 10, "target_rank": 3, "top1": "x"},
                {"layer": 25, "target_rank": 1, "top1": "t"}]
    assert jlens.classify(retained, readable)["patient_depth_class"] == "suppressed"
    assert jlens.classify(retained, absent)["patient_depth_class"] == "absent"
    assert jlens.classify(retained, retained)["patient_depth_class"] == "retained"
    assert jlens.classify(retained, [])["patient_depth_class"] is None
    out = jlens.classify(retained, readable)
    assert out["first_layer"] == {"clinical": 10, "patient": 10}
    assert out["last_layer_rank"] == {"clinical": 1, "patient": None}


def test_build_summary_carries_join_keys_and_credit():
    s = jlens.build_summary("qwen3-1.7b", [], start_index=6, topn=8)
    assert s["backend"] == "jlens-hosted"
    assert s["graph_model"] == "qwen3-1.7b"
    assert s["start_index"] == 6
    assert "anthropics/jacobian-lens" in s["method_credit"]


def test_logit_lens_type_threads_through_body_and_parser():
    # LOGIT_LENS comparison arm (2026-07-14): the request asks for it and the
    # parser reads the matching results entry, not the first one it sees.
    body = jlens.lens_request_body("gemma-2-2b", "p", 8, "LOGIT_LENS")
    assert body["type"] == ["LOGIT_LENS"]
    token_entry = {"results": [
        {"type": "JACOBIAN_LENS", "top_tokens": [["a"]]},
        {"type": "LOGIT_LENS", "top_tokens": [["b"]]},
    ]}
    resp = {"meta": {"layers_by_type": {"JACOBIAN_LENS": [0], "LOGIT_LENS": [0]}}}
    assert list(jlens._layer_entries_from_results(token_entry, resp, "LOGIT_LENS")) == [(0, ["b"])]
    assert list(jlens._layer_entries_from_results(token_entry, resp)) == [(0, ["a"])]


def test_output_filename_never_collides_with_behavioral_summaries():
    # Collectors glob batch_summary*.json; the lens path must not match it.
    src = _MODULE_PATH.read_text(encoding="utf-8")
    assert "jlens_summary." in src
    assert 'f"batch_summary' not in src


def test_fire_trigger_knows_jlens_readout():
    assert "jlens-readout" in ft.TRIGGERS
    assert ft.KNOWN_KEYS["jlens-readout"] == frozenset(
        {"models", "pairs_file", "limit", "offset", "topn", "lens_type", "save_raw",
         "commit_outputs"})
    # unknown-key typo is a hard error, like every other trigger
    try:
        ft.validate_params("jlens-readout", {"models": "m", "topN": "8"})
    except ValueError as exc:
        assert "topN" in str(exc)
    else:
        raise AssertionError("unknown key accepted")


def test_workflow_wiring_defaults_and_part_naming():
    wf = _ROOT / ".github" / "workflows" / "jlens_readout.yml"
    parsed = yaml.safe_load(wf.read_text(encoding="utf-8"))
    assert parsed["concurrency"]["cancel-in-progress"] is False
    text = wf.read_text(encoding="utf-8")
    # push-path defaults dict must contain every trigger key (CI silently
    # drops keys absent from `defaults`)
    for key in ('"models"', '"pairs_file"', '"limit"', '"offset"', '"topn"',
                '"lens_type"', '"save_raw"', '"commit_outputs"'):
        assert f"{key}:" in text.replace(f"{key} :", f"{key}:"), key
    assert '".github/trigger/jlens-readout.json"' in text
    assert "part_%02d' $((OFFSET + 1))" in text     # part naming from offset
    assert "__${KIND}_${MODEL}" in text             # dir distinct from logits dirs
    # LOGIT_LENS comparison runs must never write into __jlens_ dirs
    assert 'KIND="loglens"' in text
    assert "--lens-type" in text
    assert "NEURONPEDIA_API_KEY" in text
    # list->string normalization before str(): the push path must join lists
    assert 'isinstance(cfg.get("models"), list)' in text


def test_unsupported_model_probe_contract(tmp_path, monkeypatch):
    """A 404-ish response records supported=false and exits 0 (probe runs
    across the matrix must stay green on unsupported models)."""
    pairs = [{"top_prompt": "clin", "bottom_prompt": "pat",
              "target_clinical_token": "tgt", "generation": {}}]
    pairs_path = tmp_path / "pairs_x.json"
    pairs_path.write_text(json.dumps(pairs), encoding="utf-8")

    class FakeResp:
        status_code = 404
        text = "model not found"

    class FakeSession:
        headers = {}

        def post(self, *a, **k):
            return FakeResp()

    import sys
    import types
    fake_requests = types.SimpleNamespace(
        Session=lambda: FakeSession(),
        exceptions=types.SimpleNamespace(ConnectionError=OSError, Timeout=OSError),
    )
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    out = tmp_path / "out"
    rc = jlens.main(["--pairs", str(pairs_path), "--model", "nope-1b",
                     "--out", str(out), "--limit", "1"])
    assert rc == 0
    probe = json.loads((out / "jlens_probe.json").read_text(encoding="utf-8"))
    assert probe == {"model": "nope-1b", "supported": False,
                     "detail": probe["detail"], "checked_utc": probe["checked_utc"]}
    assert "404" in probe["detail"]
    assert not list(out.glob("jlens_summary*"))


def test_supported_model_end_to_end_summary(tmp_path, monkeypatch):
    pairs = [{"top_prompt": "clin", "bottom_prompt": "pat",
              "target_clinical_token": "tgt", "generation": {}}] * 2
    pairs_path = tmp_path / "pairs_y.json"
    pairs_path.write_text(json.dumps(pairs), encoding="utf-8")

    layers = [{"layer": 4, "topTokens": [{"token": " tgt"}]},
              {"layer": 20, "topTokens": [{"token": " other"}]}]

    class FakeResp:
        status_code = 200
        text = ""

        def raise_for_status(self):
            pass

        def json(self):
            return {"meta": {}, "tokens": [{"layers": layers}], "done": {}}

    class FakeSession:
        headers = {}

        def post(self, *a, **k):
            return FakeResp()

    import sys
    import types
    fake_requests = types.SimpleNamespace(
        Session=lambda: FakeSession(),
        exceptions=types.SimpleNamespace(ConnectionError=OSError, Timeout=OSError),
    )
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    out = tmp_path / "out"
    rc = jlens.main(["--pairs", str(pairs_path), "--model", "qwen3-1.7b",
                     "--out", str(out), "--offset", "1", "--save-raw"])
    assert rc == 0
    summary = json.loads((out / "jlens_summary.part_02.json").read_text(encoding="utf-8"))
    assert summary["start_index"] == 2
    assert len(summary["results"]) == 1
    r = summary["results"][0]
    assert r["index"] == 2                       # global 1-based join key
    assert r["patient_depth_class"] == "suppressed"
    assert r["first_layer"] == {"clinical": 4, "patient": 4}
    probe = json.loads((out / "jlens_probe.json").read_text(encoding="utf-8"))
    assert probe["supported"] is True and probe["pairs_measured"] == 1
    assert list((out / "jlens_raw").glob("pair_002_*.json.gz"))
