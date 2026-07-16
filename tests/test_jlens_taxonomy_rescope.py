"""2026-07-14 owner-adopted lens counting rules (referee worklist item 7) and
the steering-swap pilot plumbing (docs/lens_steering_design.md).

- Persistence: one-layer blips do not count as formation.
- Readability conditioning: capture/hijack are scored only on pairs whose
  clinical side is lens-readable; both-null pairs are the 'unreadable' class.
- Window sensitivity: the top-8 column must equal the headline taxonomy.
- Steering: request bodies carry the swap fields only when steered.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ji = _load("jlens_insights")
js = _load("jlens_steer")


def _layers(ranks):
    return [{"layer": i, "target_rank": r, "top1": "x"} for i, r in enumerate(ranks)]


def test_persistence_ignores_one_layer_blips():
    # blip at layer 2 only: not formation; run at 5-6: forms at 5
    assert ji.formation_layer(_layers([None, None, 3, None, None, 2, 1, None])) == 5
    # a lone blip anywhere never counts
    assert ji.formation_layer(_layers([None, 4, None, None, None])) is None
    # pre-rescope this returned 1; the rule change is the point
    assert ji.formation_layer(_layers([None, 4, 4, None, None])) == 1


def test_classify_conditions_on_clinical_readability():
    def row(clin, pat, pat_final):
        return {"clin_formed": clin, "pat_formed": pat, "pat_final_rank": pat_final}
    assert ji.classify(row(10, 12, 1)) == "held"
    assert ji.classify(row(None, None, None)) == "unreadable"   # both-null
    assert ji.classify(row(10, None, None)) == "capture"
    assert ji.classify(row(10, 12, None)) == "hijack"
    # clinical never formed: not evidence of capture even if patient blipped
    assert ji.classify(row(None, 12, None)) == "unreadable"


def test_window_sensitivity_top8_matches_headline_taxonomy():
    rows = [
        {"clin_ranks": [None, 2, 2, 1], "pat_ranks": [None, None, 5, 5]},   # held
        {"clin_ranks": [None, 2, 2, None], "pat_ranks": [None, None, None, None]},  # capture
        {"clin_ranks": [None, None, None, None], "pat_ranks": [None, None, None, None]},  # unreadable
        {"clin_ranks": [1, 1, 1, 1], "pat_ranks": [None, 7, 7, None]},      # hijack
    ]
    ws = ji.window_sensitivity(rows)
    assert ws["8"]["held"] == 1
    assert ws["8"]["capture"] == 1
    assert ws["8"]["unreadable"] == 1
    assert ws["8"]["hijack"] == 1
    # at top-1: the held pair's final rank 5 no longer holds AND its clinical
    # side's lone rank-1 layer is a blip under persistence -> unreadable; only
    # the hijack row's clinical side still reads, its patient side never
    # reaches rank 1 -> capture
    assert ws["1"]["held"] == 0
    assert ws["1"]["capture"] == 1
    assert ws["1"]["unreadable"] == 3
    assert ws["1"]["hijack"] == 0


def test_steer_body_fields_only_when_steered():
    # route schema pinned 2026-07-14: steer tokens are {token, type} objects;
    # the first probe 400'd on a bare-string swapToken
    base = js.steer_request_body("gemma-2-2b", "p", 8, " tgt", None, None)
    assert "swapToken" not in base and "steerLayers" not in base
    assert base["numCompletionTokens"] == 1
    add = js.steer_request_body("gemma-2-2b", "p", 8, " tgt", 21, 0.5)
    assert add["steerTokens"] == [{"token": " tgt", "type": "JACOBIAN_LENS"}]
    assert add["steerLayers"] == [21]
    assert add["steerStrength"] == 0.5
    assert "swapToken" not in add
    swap = js.steer_request_body("gemma-2-2b", "p", 8, " tgt", 21, None,
                                 swap_source=" win")
    assert swap["steerTokens"] == [{"token": " win", "type": "JACOBIAN_LENS"}]
    assert swap["swapToken"] == {"token": " tgt", "type": "JACOBIAN_LENS"}
    assert "steerStrength" not in swap


def test_rate_limit_rides_the_long_ladder(monkeypatch):
    # batch-9 lens died on a sustained 429 window with only 4 attempts
    # (2026-07-14): pure rate limiting must get ATTEMPTS_RATELIMIT tries with
    # capped backoff, while 500s keep the short ladder.
    jr = _load("jlens_readout")
    sleeps = []
    monkeypatch.setattr(jr.time, "sleep", sleeps.append)

    class Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = ""

    class Session:
        def __init__(self, code):
            self.code, self.calls = code, 0

        def post(self, *a, **k):
            self.calls += 1
            return Resp(self.code)

    import pytest
    s429 = Session(429)
    with pytest.raises(RuntimeError):
        jr.post_lens(s429, {})
    assert s429.calls == jr.ATTEMPTS_RATELIMIT
    assert max(sleeps) == jr.RETRY_SLEEP_CAP
    sleeps.clear()
    s500 = Session(500)
    with pytest.raises(RuntimeError):
        jr.post_lens(s500, {})
    assert s500.calls == jr.ATTEMPTS


def test_pilot_spec_is_well_formed():
    spec = json.loads((_ROOT / "data" / "steer_pilot_spec.json").read_text(encoding="utf-8"))
    assert spec["model"] == "gemma-2-2b"
    assert spec["layers"] and spec["strengths"]
    classes = {i["class"] for i in spec["items"]}
    assert {"hijack", "capture", "held"} <= classes
    for item in spec["items"]:
        assert item["prompt"] and item["target"]


def test_unresolvable_steer_token_is_item_level(tmp_path, monkeypatch):
    # 2026-07-14 grid run: a multi-wordpiece target 400'd as "Could not
    # resolve steer token" and the script declared the CAPABILITY dead,
    # discarding 10 measured items. Now: mark the item, keep its baseline,
    # continue, and still write the summary.
    import sys
    import types
    spec = {"model": "gemma-2-2b", "layers": [19], "strengths": [1],
            "num_completion_tokens": 1,
            "items": [{"dataset": "d", "index": 1, "class": "capture",
                       "prompt": "p1", "target": " antivirals", "winner": " rest"},
                      {"dataset": "d", "index": 2, "class": "capture",
                       "prompt": "p2", "target": " nap", "winner": " rest"}]}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))

    calls = {"n": 0}

    def fake_post(session, body, timeout=180.0):
        calls["n"] += 1
        if body.get("steerTokens") and body["steerTokens"][0]["token"] == " antivirals":
            return None, 'unsupported (400): {"error":"Could not resolve steer token to a vocab id"}'
        return {"meta": {"layers_by_type": {"JACOBIAN_LENS": [0]}},
                "tokens": [{"kind": "token", "position": 0, "token": "p",
                            "results": [{"type": "JACOBIAN_LENS", "top_tokens": [[" nap"]]}]}]}, None

    monkeypatch.setattr(js.jr, "post_lens", fake_post)
    monkeypatch.setattr(js.jr, "save_raw", lambda *a, **k: None)
    fake_requests = types.SimpleNamespace(Session=lambda: types.SimpleNamespace(headers={}))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test")
    out = tmp_path / "out"
    rc = js.main(["--spec", str(spec_path), "--out", str(out)])
    assert rc == 0
    summary = json.loads((out / "jsteer_summary.part_01.json").read_text())
    assert len(summary["results"]) == 2
    assert summary["results"][0].get("steer_unresolvable") is True
    assert "baseline" in summary["results"][0]["calls"]
    assert summary["results"][1].get("steer_unresolvable") is None
    probe = json.loads((out / "jsteer_probe.json").read_text())
    assert probe["steering_supported"] is True


def test_insights_census_skips_txcorpus_lens_dirs(tmp_path):
    # translated-side lens profiles must never enter the patient formation
    # census (2026-07-15): the census would count haiku rewrites as patient
    # wordings.
    troot = tmp_path / "trace_out"
    def mk(stem):
        d = troot / f"{stem}__jlens_gemma-2-2b"
        d.mkdir(parents=True)
        (d / "jlens_summary.part_01.json").write_text(json.dumps({"results": [
            {"index": 1, "parse_status": {"clinical": "ok", "patient": "ok"},
             "depth": {"clinical": [{"layer": 0, "target_rank": 1}],
                       "patient": [{"layer": 0, "target_rank": 1}]}}]}))
    mk("pairs_20260711T000000Z")
    mk("txcorpus_priority2_20260714T224455Z")
    # translated/placebo/context arms are rewrites, not patient wordings
    # (guard extended 2026-07-16 when the arm lens pulls landed)
    mk("pairs_20260711T051145Z_txopus")
    mk("pairs_20260711T051145Z_txplacebo")
    mk("urgency_downgrades_20260707T1__context")
    per = ji.collect(troot)
    stems = {r["dataset"] for rows in per.values() for r in rows}
    assert stems == {"pairs_20260711T000000Z"}
