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
    # one block per model per arm in stable order, carrying EVERY attempt
    assert [r["model"] for r in s1["clinical"]["responses"]] == ["prov-x:model-1", "prov-y:model-2"]
    r0 = s1["clinical"]["responses"][0]
    assert [sm["k"] for sm in r0["samples"]] == [1, 2]
    assert all(sm["tier"] == "routine" and sm["refusal"] is False for sm in r0["samples"])
    assert r0["model_returned"] == "model-1-served"
    assert r0["samples"][0]["model_returned"] == "model-1-served"
    run = payload["run"]
    assert run["n_calls"] == len(ae._read_jsonl(archive["out_dir"] / f"responses_{archive['stim'].stem}.jsonl"))
    assert run["cost_usd"] > 0 and run["cost_per_scenario"] > 0
    assert {m["spec"] for m in run["models"]} == {"prov-x:model-1", "prov-y:model-2"}
    # A3: distinct served builds per spec with sent window
    b = run["models"][0]["builds"]
    assert len(b) == 1 and b[0]["model_returned"] == "model-1-served"
    assert b[0]["n"] > 0 and b[0]["first_sent_utc"] <= b[0]["last_sent_utc"]
    assert payload["chain_head"] and payload["rubric_version"] == "t1"
    assert payload["tier_order"] == ["self_care", "routine"]
    # per-model figure block: mechanical stats plus coded-tier aggregates
    ms = payload["model_summary"]
    assert [m["model"] for m in ms] == ["prov-x:model-1", "prov-y:model-2"]
    c = ms[0]["clinical"]
    assert c["n"] == 4 and c["mean_words"] > 0  # 2 stimuli x 2 attempts
    assert c["tier_counts"] == {"routine": 4}
    assert c["tier_mean_rank"] == 2.0  # every stub judgment is 'routine', rank 2 of tier_order
    # answer-stability block: identical stub text per cell -> re-asked overlap is 1.0;
    # the two wordings produce different stub texts -> re-worded overlap drops below it
    sim = ms[0]["similarity"]
    assert sim["n_stimuli"] == 2
    assert sim["reasked"] == 1.0 and 0 < sim["reworded"] < 1.0
    # judged flag rates present (stub judge sets refusal False only -> no true flags)
    assert c["n_judged"] == 4 and c["flag_rates"] == {}
    # per-scenario modal tiers reduce to a summary once tier_order is known
    ts = payload["scenarios"][0]["tier_summary"]
    assert {t["model"] for t in ts} == {"prov-x:model-1", "prov-y:model-2"}
    assert all(t["clinical"] == "routine" and t["patient"] == "routine"
               and t["drop"] == 0 and t["downgrade"] is False for t in ts)
    assert (site / "data" / "advice_scenarios.json").is_file()


def test_export_merges_rerouted_google_paths(tmp_path, monkeypatch):
    # 2026-07-22 access amendment: google's arm rerouted to OpenRouter mid-pilot.
    # Display rows merge the two access paths into one model family; duplicated
    # attempts keep the direct-path record; provenance lists both raw specs.
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps([
        {"id": "s1", "clinical": "clinical body one, so I track it with a",
         "patient": "everyday body one, so I track it with a"},
    ]), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual), "--out-dir", str(out_dir)])
    stim = next(out_dir.glob("stimuli_*.json"))
    registry = tmp_path / "providers.json"
    registry.write_text(json.dumps({
        "google": {"api": "openai-compat", "base_url": "https://g.example/v1",
                   "key_env": "G_KEY", "default_pricing": [1.0, 4.0]},
        "openrouter": {"api": "openai-compat", "base_url": "https://or.example/v1",
                       "key_env": "OR_KEY", "default_pricing": [5.0, 30.0]},
    }), encoding="utf-8")

    def stub_compat(cfg, model, system, user_text, max_tokens, temperature):
        return f"advice for [{user_text[:18]}]", 10, 20, {"model": model + "-served", "usage": {}}

    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_send_compat", stub_compat)
    ae.main(["elicit", "--stimuli", str(stim), "--models", "google:gemini-3.5-flash",
             "--providers", str(registry), "--arms", "clinical", "--samples", "2",
             "--max-spend", "5.0", "--out-dir", str(out_dir)])
    ae.main(["elicit", "--stimuli", str(stim), "--models", "openrouter:google/gemini-3.5-flash",
             "--providers", str(registry), "--arms", "clinical", "--samples", "3",
             "--max-spend", "5.0", "--out-dir", str(out_dir)])

    out = tmp_path / "advice_scenarios.json"
    ex.main(["--stimuli", str(out_dir / stim.name), "--out", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    rs = payload["scenarios"][0]["clinical"]["responses"]
    assert [r["model"] for r in rs] == ["google:gemini-3.5-flash"]  # one display row
    samples = rs[0]["samples"]
    assert [sm["k"] for sm in samples] == [1, 2, 3]
    assert samples[0]["model_returned"] == "gemini-3.5-flash-served"
    assert samples[1]["model_returned"] == "gemini-3.5-flash-served"
    assert samples[2]["model_returned"] == "google/gemini-3.5-flash-served"
    specs = {m["spec"]: m["n_responses"] for m in payload["run"]["models"]}
    assert specs == {"google:gemini-3.5-flash": 2, "openrouter:google/gemini-3.5-flash": 3}


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
    sm = payload["scenarios"][0]["clinical"]["responses"][0]["samples"][0]
    assert sm["tier"] is None and sm["refusal"] is None
    assert payload["rubric_version"] is None and payload["tier_order"] is None
    # figure block still present: words computable, tier fields stay null until judged
    c = payload["model_summary"][0]["clinical"]
    assert c["mean_words"] > 0 and c["tier_counts"] is None and c["tier_mean_rank"] is None
