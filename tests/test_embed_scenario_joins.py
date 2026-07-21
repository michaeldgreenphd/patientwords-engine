"""Payload embed pass (scripts/embed_scenario_joins.py) — offline (audit M2+M3).

Pins the verified page semantics: the index-vs-batch_index join-key naming,
per-model urgency embed with base mirror, depth-class join (no model in key),
urgency_meta sourcing, the gallery's exact scoring (untiered patient top
= -0.5), the data-driven token-clean test (synthetic blocklist — no medical
vocabulary in this file), diversity caps, and the refusal path.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "embed_scenario_joins", _ROOT / "scripts" / "embed_scenario_joins.py")
ej = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ej)

BASE = "gemma-2-2b"


def scen(batch, bidx, gidx, spread_c=None, spread_p=None, models=(BASE,)):
    return {"batch": batch, "batch_index": bidx, "index": gidx,
            "spread_clinical": spread_c, "spread_patient": spread_p,
            "models": {m: {} for m in models}}


def urow(batch, idx, model=BASE, flip="downgrade", tc=3, tp=1, shift=-2.0, rec=None):
    r = {"batch": batch, "index": idx, "model": model, "flip_class": flip,
         "tier_top_clinical": tc, "tier_top_patient": tp, "tier_shift": shift}
    if rec is not None:
        r["urgency_recovery"] = rec
    return r


def write_site(tmp_path, payload, urg=None, depth=None, vocab=None):
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "simulated_scenarios.json").write_text(json.dumps(payload))
    if urg is not None:
        (d / "urgency_shift.json").write_text(json.dumps(urg))
    if depth is not None:
        (d / "jlens_depth.json").write_text(json.dumps(depth))
    if vocab is not None:
        (d / "display_vocab.json").write_text(json.dumps(vocab))
    return d / "simulated_scenarios.json"


def test_urgency_join_keys_and_base_mirror(tmp_path):
    payload = {"scenarios": [scen("b1", 5, 1, models=(BASE, "qwen3-4b"))]}
    urg = {"rows": [urow("b1", 5, rec=0.4),
                    urow("b1", 5, model="qwen3-4b", flip="upgrade", tc=1, tp=3, shift=2.0),
                    urow("b1", 99)],   # no matching scenario
           "vocabulary_status": "draft", "tiers": {"4": "emergency"}}
    p = write_site(tmp_path, payload, urg=urg)
    assert ej.main(["--site", str(tmp_path)]) == 0
    out = json.loads(p.read_text())
    s = out["scenarios"][0]
    assert s["urgency"]["flip_class"] == "downgrade"          # base mirrored to top
    assert s["urgency"]["urgency_recovery"] == 0.4
    assert s["models"]["qwen3-4b"]["urgency"]["flip_class"] == "upgrade"
    assert out["urgency_meta"] == {"vocabulary_status": "draft", "tiers": {"4": "emergency"}}


def test_depth_join_has_no_model_in_key(tmp_path):
    payload = {"scenarios": [scen("b1", 2, 1), scen("b1", 3, 2)]}
    depth = {"model": BASE, "blocks": [
        {"id": "b1", "pairs": [{"index": 2, "class": "suppressed"},
                               {"index": 7, "class": "absent"}]}]}
    p = write_site(tmp_path, payload, depth=depth)
    assert ej.main(["--site", str(tmp_path)]) == 0
    out = json.loads(p.read_text())
    assert out["scenarios"][0]["depth_class"] == "suppressed"
    assert "depth_class" not in out["scenarios"][1]           # unmeasured: field omitted
    assert out["depth_model"] == BASE


def test_gallery_scoring_untiered_caps_and_blocklist(tmp_path):
    vocab = {"fragment_blocklist": ["zzz"]}                    # synthetic, non-medical
    payload = {"scenarios": [
        # tier drop 3->1 = 2, clean tokens, pp .5 -> 200+40+5 = 245
        scen("b", 1, 10, [["alpha", .9]], [["beta", .5]]),
        # untiered patient: 3-(-0.5)=3.5 -> 350+40+2 = 392 (ranks first)
        scen("b", 2, 11, [["gamma", .9]], [["delta", .2]]),
        # blocklisted patient top: no clean bonus -> 200+0+9 = 209
        scen("b", 3, 12, [["epsln", .9]], [["zzz", .9]]),
        # same clinical answer 'alpha' as #1 but higher pp -> outscores it (249 vs 245),
        # so the <=1-per-clinical-answer cap drops #1, not #4
        scen("b", 4, 13, [["alpha", .9]], [["omega", .9]]),
    ]}
    urg = {"rows": [urow("b", 1), urow("b", 2, tp=None), urow("b", 3), urow("b", 4)]}
    p = write_site(tmp_path, payload, urg=urg, vocab=vocab)
    assert ej.main(["--site", str(tmp_path)]) == 0
    g = json.loads(p.read_text())["featured"]["redirect_gallery"]
    assert [x["batch_index"] for x in g] == [2, 4, 3]          # 1 dropped by clinical cap
    assert g[0]["components"]["tier_drop"] == 3.5              # untiered = -0.5
    assert g[0]["score"] == 392.0
    assert g[2]["components"]["clean_bonus"] == 0              # blocklist hit
    assert [x["rank"] for x in g] == [1, 2, 3]


def test_refuses_without_payload_and_survives_missing_joins(tmp_path):
    (tmp_path / "data").mkdir()
    assert ej.main(["--site", str(tmp_path)]) == 3             # no payload: refusal
    p = write_site(tmp_path, {"scenarios": [scen("b", 1, 1)]})
    assert ej.main(["--site", str(tmp_path)]) == 0             # no urgency/depth: no-op embed
    out = json.loads(p.read_text())
    assert "urgency" not in out["scenarios"][0] and "featured" not in out
