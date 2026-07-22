"""Tests for scripts/export_advice_scenarios.py - the LLM-responses page exporter.

Offline: a tiny archive is built with the monkeypatched advice_eval seams, then
exported. Covers the payload contract, judgment tier joining, chain-refusal, the
no-records refusal, and the site-copy path.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ae = _load("advice_eval")
ex = _load("export_advice_scenarios")


def _stub_send(client, model, system, user_text, max_tokens, temperature):
    raw = {"model": model + "-served", "stop_reason": "end_turn"}
    if system and "clinical terminology" in system:
        return "translated placeholder body, so I track it with a", 10, 20, raw
    if "RESPONSE TO CODE" in user_text:
        return json.dumps({"tier": "routine", "flags": {"refusal": False}}), 10, 20, raw
    return f"advice for [{user_text[:18]}]", 10, 20, raw


RUBRIC = {"version": "t1",
          "tiers": [{"id": "self_care", "label": "a", "definition": "d"},
                    {"id": "routine", "label": "b", "definition": "d"}],
          "flags": [{"id": "refusal", "definition": "d"}],
          "judge_instructions": "Tiers:\n{tiers}\nFlags:\n{flags}\nRESPONSE TO CODE:\n{response}"}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps([
        {"id": "s1", "clinical": "clinical body one, so I track it with a",
         "patient": "everyday body one, so I track it with a"},
        {"id": "s2", "clinical": "clinical body two, so I track it with a",
         "patient": "everyday body two, so I track it with a"},
    ]), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual), "--out-dir", str(out_dir)])
    stim = next(out_dir.glob("stimuli_*.json"))
    registry = tmp_path / "providers.json"
    registry.write_text(json.dumps({
        "prov-x": {"api": "openai-compat", "base_url": "https://x.example/v1",
                   "key_env": "X_KEY", "default_pricing": [1.0, 4.0]},
        "prov-y": {"api": "openai-compat", "base_url": "https://y.example/v1",
                   "key_env": "Y_KEY", "default_pricing": [1.0, 4.0]},
    }), encoding="utf-8")

    def stub_compat(cfg, model, system, user_text, max_tokens, temperature):
        return f"advice for [{user_text[:18]}]", 10, 20, {"model": model + "-served", "usage": {}}

    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_send", _stub_send)
    monkeypatch.setattr(ae, "_send_compat", stub_compat)
    ae.main(["elicit", "--stimuli", str(stim), "--models", "prov-x:model-1,prov-y:model-2",
             "--providers", str(registry),
             "--arms", "clinical,patient,translated", "--samples", "2",
             "--translator-model", "model-t", "--max-spend", "5.0", "--out-dir", str(out_dir)])
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps(RUBRIC), encoding="utf-8")
    ae.main(["judge", "--responses", str(out_dir / f"responses_{stim.stem}.jsonl"),
             "--rubric", str(rubric), "--judge-model", "judge-x", "--max-spend", "5.0"])
    return {"stim": stim, "out_dir": out_dir, "rubric": rubric, "tmp": tmp_path}


def test_export_contract(archive, monkeypatch):
    out = archive["tmp"] / "advice_scenarios.json"
    site = archive["tmp"] / "site"
    ex.main(["--stimuli", str(archive["stim"]), "--out", str(out),
             "--rubric", str(archive["rubric"]), "--site", str(site)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [s["id"] for s in payload["scenarios"]] == ["s1", "s2"]
    s1 = payload["scenarios"][0]
    assert s1["clinical"]["message"].startswith("clinical body one")
    assert s1["patient"]["message"].startswith("everyday body one")
    assert s1["translated"]["message"]  # assembled translated wording captured
    # one displayed response per model per arm, in stable model order
    assert [r["model"] for r in s1["clinical"]["responses"]] == ["prov-x:model-1", "prov-y:model-2"]
    r0 = s1["clinical"]["responses"][0]
    assert r0["sample_k"] == 1 and r0["n_samples"] == 2
    assert r0["tier"] == "routine" and r0["refusal"] is False
    assert r0["model_returned"] == "model-1-served"
    run = payload["run"]
    assert run["n_calls"] == len(ae._read_jsonl(archive["out_dir"] / f"responses_{archive['stim'].stem}.jsonl"))
    assert run["cost_usd"] > 0 and run["cost_per_scenario"] > 0
    assert {m["spec"] for m in run["models"]} == {"prov-x:model-1", "prov-y:model-2"}
    assert payload["chain_head"] and payload["rubric_version"] == "t1"
    assert payload["tier_order"] == ["self_care", "routine"]
    assert (site / "data" / "advice_scenarios.json").is_file()


def test_export_refuses_tampered_chain(archive):
    resp = archive["out_dir"] / f"responses_{archive['stim'].stem}.jsonl"
    lines = resp.read_text(encoding="utf-8").splitlines()
    doctored = json.loads(lines[1])
    doctored["response_text"] = "edited"
    lines[1] = json.dumps(doctored, ensure_ascii=False)
    resp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = archive["tmp"] / "advice_scenarios.json"
    out.write_text("KEEP", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        ex.main(["--stimuli", str(archive["stim"]), "--out", str(out)])
    assert exc.value.code == 3
    assert out.read_text(encoding="utf-8") == "KEEP"  # refusal leaves the good file untouched


def test_export_refuses_empty_archive(tmp_path):
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps([{"id": "s1", "clinical": "aa bb", "patient": "cc dd"}]), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual), "--out-dir", str(out_dir)])
    stim = next(out_dir.glob("stimuli_*.json"))
    with pytest.raises(SystemExit) as exc:
        ex.main(["--stimuli", str(stim), "--out", str(tmp_path / "x.json")])
    assert exc.value.code == 3


def test_export_without_judgments(archive):
    (archive["out_dir"] / f"judgments_{archive['stim'].stem}.jsonl").unlink()
    out = archive["tmp"] / "advice_scenarios.json"
    ex.main(["--stimuli", str(archive["stim"]), "--out", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    r0 = payload["scenarios"][0]["clinical"]["responses"][0]
    assert r0["tier"] is None and r0["refusal"] is None
    assert payload["rubric_version"] is None and payload["tier_order"] is None
