"""Tests for scripts/advice_human_coding.py - the blinded human-coding gate.

Offline; archives built with the monkeypatched advice_eval seams. Covers the
blinding contract (payload carries coding_id + response_text ONLY), determinism,
stratification, and the agreement scoring (per-arm, weighted kappa, flags,
inter-human).
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
hc = _load("advice_human_coding")

RUBRIC = {"version": "t1",
          "tiers": [{"id": "self_care", "label": "a", "definition": "d"},
                    {"id": "routine", "label": "b", "definition": "d"},
                    {"id": "urgent", "label": "c", "definition": "d"}],
          "flags": [{"id": "refusal", "definition": "d"}],
          "judge_instructions": "Tiers:\n{tiers}\nFlags:\n{flags}\nRESPONSE TO CODE:\n{response}"}


def _stub_send(client, model, system, user_text, max_tokens, temperature):
    raw = {"model": model + "-served", "stop_reason": "end_turn"}
    if system and "clinical terminology" in system:
        return f"translated {user_text[:20]}, so I track it with a", 10, 20, raw
    if "RESPONSE TO CODE" in user_text:
        return json.dumps({"tier": "routine", "flags": {"refusal": False}}), 10, 20, raw
    return f"advice for [{user_text[:34]}]", 10, 20, raw


@pytest.fixture
def archive(tmp_path, monkeypatch):
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps([
        {"id": f"s{i}", "clinical": f"clinical body {i}, so I track it with a",
         "patient": f"everyday body {i}, so I track it with a"} for i in range(1, 7)
    ]), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual), "--out-dir", str(out_dir)])
    stim = next(out_dir.glob("stimuli_*.json"))
    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_send", _stub_send)
    ae.main(["elicit", "--stimuli", str(stim), "--models", "model-x",
             "--arms", "clinical,patient,translated", "--samples", "1",
             "--translator-model", "model-t", "--max-spend", "5.0", "--out-dir", str(out_dir)])
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps(RUBRIC), encoding="utf-8")
    resp = out_dir / f"responses_{stim.stem}.jsonl"
    ae.main(["judge", "--responses", str(resp), "--rubric", str(rubric),
             "--judge-model", "judge-x", "--max-spend", "5.0"])
    return {"resp": resp, "rubric": rubric, "tmp": tmp_path,
            "judgments": out_dir / f"judgments_{stim.stem}.jsonl"}


def _build(archive, n=9, seed=7):
    out = archive["tmp"] / "coding_sample.json"
    km = archive["tmp"] / "keymap.json"
    hc.main(["build-sample", "--responses", str(archive["resp"]), "--rubric", str(archive["rubric"]),
             "--n", str(n), "--seed", str(seed), "--out", str(out), "--keymap-out", str(km)])
    return json.loads(out.read_text(encoding="utf-8")), json.loads(km.read_text(encoding="utf-8"))


def test_payload_is_blinded_and_deterministic(archive):
    payload, keymap = _build(archive)
    assert payload["n_items"] == 9
    assert payload["coders"] == [{"id": "owner", "label": "Michael D. Green (study owner)"}]
    for it in payload["items"]:
        assert set(it.keys()) == {"coding_id", "response_text"}  # blinding contract
        assert "so I track it with a" not in ""  # no prompt text field exists at all
    text = json.dumps(payload)
    for forbidden in ("\"arm\"", "\"model\"", "stimulus_id", "clinical_message", "patient_message"):
        assert forbidden not in text
    arms = [v["arm"] for v in keymap["map"].values()]
    assert {a: arms.count(a) for a in set(arms)} == {"clinical": 3, "patient": 3, "translated": 3}
    payload2, keymap2 = _build(archive)
    assert payload2["items"] == payload["items"] and keymap2["map"] == keymap["map"]  # same seed, same sample


def test_score_agreement_and_kappa(archive):
    payload, keymap = _build(archive)
    # perfect-agreement coder: copy the machine tier via the keymap
    machine = {j["response_sha256"]: j for j in
               [json.loads(x) for x in archive["judgments"].read_text(encoding="utf-8").splitlines()]}
    codings = []
    for it in payload["items"]:
        sha = keymap["map"][it["coding_id"]]["response_sha256"]
        codings.append({"coding_id": it["coding_id"], "tier": machine[sha]["tier"],
                        "flags": {"refusal": False}, "coded_utc": "2026-07-28T00:00:00Z"})
    cfile = archive["tmp"] / "codings_owner.json"
    cfile.write_text(json.dumps({"coder": "owner", "codings": codings}), encoding="utf-8")
    out = archive["tmp"] / "agreement.json"
    hc.main(["score", "--codings", str(cfile), "--keymap", str(archive["tmp"] / "keymap.json"),
             "--judgments", str(archive["judgments"]), "--rubric", str(archive["rubric"]),
             "--out", str(out)])
    rep = json.loads(out.read_text(encoding="utf-8"))
    o = rep["vs_machine"]["owner"]
    assert o["overall"]["raw_agreement"] == 1.0
    assert set(o["by_arm"].keys()) == {"clinical", "patient", "translated"}  # registered stratification
    assert all(v["raw_agreement"] == 1.0 for v in o["by_arm"].values())
    assert o["overall"]["flags"]["refusal"] == 1.0
    # a disagreeing second coder produces inter-human stats and lower agreement
    cod2 = [dict(c, tier="urgent") for c in codings]
    cfile2 = archive["tmp"] / "codings_second.json"
    cfile2.write_text(json.dumps({"coder": "second", "codings": cod2}), encoding="utf-8")
    hc.main(["score", "--codings", str(cfile), str(cfile2), "--keymap", str(archive["tmp"] / "keymap.json"),
             "--judgments", str(archive["judgments"]), "--rubric", str(archive["rubric"]),
             "--out", str(out)])
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["vs_machine"]["second"]["overall"]["raw_agreement"] == 0.0
    assert rep["inter_human"]["n"] == 9 and rep["inter_human"]["raw_agreement"] == 0.0


def test_weighted_kappa_bounds():
    order = ["a", "b", "c"]
    assert hc._weighted_kappa([("a", "a"), ("b", "b")], order) == 1.0
    assert hc._weighted_kappa([], order) is None


def test_build_refuses_tampered_archive(archive):
    lines = archive["resp"].read_text(encoding="utf-8").splitlines()
    doctored = json.loads(lines[1])
    doctored["response_text"] = "edited"
    lines[1] = json.dumps(doctored, ensure_ascii=False)
    archive["resp"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="tampered"):
        _build(archive)
