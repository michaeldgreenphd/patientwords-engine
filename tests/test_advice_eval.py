"""Tests for scripts/advice_eval.py - the frontier-advice arm.

Offline like the rest of the suite: the Anthropic seam (_send/_client) is
monkeypatched, all vocabulary is abstract placeholder text, and everything runs
against tmp_path. Covers stimulus assembly + validation, the Tier B holdout
guard (including the null-start_utc trap), the append-only hash-chained
elicitation archive (resume, tamper detection, spend ceiling), judge parsing
and idempotence, the paired analysis classifications, and the workflow YAML's
defaults-dict wiring.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "advice_eval.py"
_SPEC = importlib.util.spec_from_file_location("advice_eval", _MODULE_PATH)
ae = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ae)

RUBRIC = {
    "version": "test",
    "tiers": [
        {"id": "self_care", "label": "a", "definition": "least urgent placeholder"},
        {"id": "routine", "label": "b", "definition": "mid placeholder"},
        {"id": "urgent", "label": "c", "definition": "higher placeholder"},
        {"id": "emergency", "label": "d", "definition": "most urgent placeholder"},
    ],
    "flags": [
        {"id": "professional_referral", "definition": "placeholder"},
        {"id": "disclaimer", "definition": "placeholder"},
        {"id": "refusal", "definition": "placeholder"},
    ],
    "judge_instructions": "Tiers:\n{tiers}\nFlags:\n{flags}\nRESPONSE TO CODE:\n{response}",
}


def write_manual(tmp_path, items):
    p = tmp_path / "manual.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    return p


def build_manual_stimuli(tmp_path, monkeypatch):
    manual = write_manual(
        tmp_path,
        [{"id": "s1", "clinical": "My flurb registers a level-two wobble, so I track it with a",
          "patient": "My flurb keeps going all wobbly on me, so I track it with a"}],
    )
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual), "--out-dir", str(out_dir)])
    return next(out_dir.glob("stimuli_*.json"))


# ------------------------------------------------------------- build-stimuli


def test_manual_build_assembles_identical_suffix(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    doc = json.loads(stim_path.read_text(encoding="utf-8"))
    item = doc["items"][0]
    suffix = doc["ask_suffix"]
    assert item["clinical_message"].endswith(suffix) and item["patient_message"].endswith(suffix)
    # minimal-pair property: stripping the shared suffix recovers the two bodies
    assert item["clinical_message"] == f"{item['clinical_body']} {suffix}"
    assert item["patient_message"] == f"{item['patient_body']} {suffix}"
    assert item["clinical_sha256"] != item["patient_sha256"]


@pytest.mark.parametrize(
    "items",
    [
        [{"id": "x", "clinical": "", "patient": "b"}],
        [{"id": "x", "clinical": "same text here", "patient": "same text here"}],
        [{"id": "x", "clinical": "a1", "patient": "b1"}, {"id": "x", "clinical": "a2", "patient": "b2"}],
    ],
)
def test_manual_build_rejects_bad_items(tmp_path, items):
    manual = write_manual(tmp_path, items)
    with pytest.raises(SystemExit):
        ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual),
                 "--out-dir", str(tmp_path / "advice")])


def test_payload_source_filters(tmp_path):
    payload = {
        "holdout_withheld": 1,
        "scenarios": [
            {"batch": "pairs_x", "batch_index": 1, "clinical_prompt": "alpha frame with a",
             "patient_prompt": "alpha frame variant with a", "flipped": True, "language_penalty": -0.2,
             "screening": {"status": "passed"}},
            {"batch": "pairs_x", "batch_index": 2, "clinical_prompt": "beta frame with a",
             "patient_prompt": "beta frame variant with a", "flipped": False, "language_penalty": -0.01,
             "screening": {"status": "passed"}},
            {"batch": "pairs_x", "batch_index": 3, "clinical_prompt": "gamma frame with a",
             "patient_prompt": "gamma frame variant with a", "flipped": True,
             "screening": {"status": "screened_out"}},
        ],
    }
    src = tmp_path / "payload.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "payload", "--payload", str(src),
             "--only-flips", "--out-dir", str(out_dir)])
    doc = json.loads(next(out_dir.glob("stimuli_*.json")).read_text(encoding="utf-8"))
    # screened_out excluded always; non-flip excluded by --only-flips
    assert [i["id"] for i in doc["items"]] == ["pairs_x#1"]
    assert doc["items"][0]["meta"]["flipped"] is True


def _holdout_phrase():
    n = 0
    while True:
        cand = f"placeholder probe phrase number {n}"
        if int(hashlib.sha1(cand.encode()).hexdigest(), 16) % 10 == 0:
            return cand
        n += 1


def _pairs_repo(tmp_path, start_utc):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "dashboard.json").write_text(
        json.dumps({"tierb": {"start_utc": start_utc}}), encoding="utf-8")
    batch = tmp_path / "pairs_20260715T000000Z.json"
    holdout = _holdout_phrase()
    keep = "placeholder probe phrase kept"
    assert int(hashlib.sha1(keep.encode()).hexdigest(), 16) % 10 != 0
    batch.write_text(json.dumps([
        {"top_prompt": holdout, "bottom_prompt": "variant one"},
        {"top_prompt": keep, "bottom_prompt": "variant two"},
    ]), encoding="utf-8")
    return batch


def test_pairs_holdout_guard_refuses_null_start(tmp_path):
    batch = _pairs_repo(tmp_path, start_utc=None)
    with pytest.raises(SystemExit, match="holdout set cannot be computed"):
        ae.main(["build-stimuli", "--source", "pairs", "--pairs", str(batch),
                 "--dashboard", str(tmp_path / "ops" / "dashboard.json"),
                 "--out-dir", str(tmp_path / "advice")])


def test_pairs_holdout_rows_excluded(tmp_path):
    batch = _pairs_repo(tmp_path, start_utc="2026-07-10T01:14:38Z")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "pairs", "--pairs", str(batch),
             "--dashboard", str(tmp_path / "ops" / "dashboard.json"), "--out-dir", str(out_dir)])
    doc = json.loads(next(out_dir.glob("stimuli_*.json")).read_text(encoding="utf-8"))
    assert doc["source"]["holdout_excluded"] == 1
    assert [i["clinical_body"] for i in doc["items"]] == ["placeholder probe phrase kept"]


# ------------------------------------------------------------------- elicit


def _stub_send(client, model, system, user_text, max_tokens, temperature):
    raw = {"model": model + "-20260101", "stop_reason": "end_turn"}
    if system and "clinical terminology" in system:
        return "translated placeholder body, so I track it with a", 10, 20, raw
    if "RESPONSE TO CODE" in user_text:
        return json.dumps({"tier": "routine", "flags": {"professional_referral": True,
                                                        "disclaimer": False, "refusal": False}}), 10, 20, raw
    return f"advice text for [{user_text[:24]}]", 10, 20, raw


def _elicit(tmp_path, monkeypatch, stim_path, max_spend="1.0", samples="2"):
    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_send", _stub_send)
    ae.main(["elicit", "--stimuli", str(stim_path), "--models", "model-x",
             "--arms", "clinical,patient,translated", "--samples", samples,
             "--translator-model", "model-y",  # fallback-priced like model-x: deterministic ceiling math
             "--max-spend", max_spend, "--out-dir", str(stim_path.parent)])
    stem = stim_path.stem
    return (stim_path.parent / f"responses_{stem}.jsonl",
            stim_path.parent / f"responses_{stem}.report.json")


def test_elicit_chain_and_resume(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path)
    rows = [json.loads(line) for line in resp.read_text(encoding="utf-8").splitlines()]
    # 1 translation + 3 arms x 1 model x K=2 advice records
    assert [r["record_type"] for r in rows].count("translation") == 1
    assert [r["record_type"] for r in rows].count("advice") == 6
    ok, msg = ae.verify_chain(rows)
    assert ok, msg
    side = json.loads(sidecar.read_text(encoding="utf-8"))
    assert side["chain_head"] == rows[-1]["record_sha256"]
    assert side["cost_usd"] > 0 and side["truncated"] is False
    translated = [r for r in rows if r.get("arm") == "translated"]
    assert all(r["translation_sha256"] == rows[0]["output_sha256"] for r in translated)
    assert all(r["model_returned"] == "model-x-20260101" for r in translated)

    # resume: identical invocation appends nothing
    _elicit(tmp_path, monkeypatch, stim_path)
    assert len(resp.read_text(encoding="utf-8").splitlines()) == 7
    assert json.loads(sidecar.read_text(encoding="utf-8"))["records_appended"] == 0


def test_verify_chain_detects_tamper(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path)
    lines = resp.read_text(encoding="utf-8").splitlines()
    doctored = json.loads(lines[2])
    doctored["response_text"] = "edited after landing"
    lines[2] = json.dumps(doctored, ensure_ascii=False)
    resp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ae.main(["verify-chain", "--responses", str(resp), "--sidecar", str(sidecar)])
    # a tampered archive also refuses further appends
    with pytest.raises(SystemExit, match="chain"):
        _elicit(tmp_path, monkeypatch, stim_path)


def test_elicit_spend_ceiling_stops_early(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    # fallback-priced worst case per call: 400*10/1e6 + 1024*50/1e6 = 0.0552 USD
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path, max_spend="0.056")
    assert len(resp.read_text(encoding="utf-8").splitlines()) == 1
    side = json.loads(sidecar.read_text(encoding="utf-8"))
    assert side["truncated"] is True and "ceiling" in side["stopped_reason"]


# -------------------------------------------------------------------- judge


def test_judge_parses_and_is_idempotent(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, _ = _elicit(tmp_path, monkeypatch, stim_path)
    rubric_path = tmp_path / "rubric.json"
    rubric_path.write_text(json.dumps(RUBRIC), encoding="utf-8")
    ae.main(["judge", "--responses", str(resp), "--rubric", str(rubric_path),
             "--judge-model", "judge-x", "--max-spend", "1.0"])
    jpath = resp.with_name(resp.stem.replace("responses_", "judgments_") + ".jsonl")
    rows = [json.loads(line) for line in jpath.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 6  # every advice record, none of the translation records
    assert all(r["tier"] == "routine" and r["flags"]["professional_referral"] for r in rows)
    assert all(r["rubric_version"] == "test" for r in rows)
    ae.main(["judge", "--responses", str(resp), "--rubric", str(rubric_path),
             "--judge-model", "judge-x", "--max-spend", "1.0"])
    assert len(jpath.read_text(encoding="utf-8").splitlines()) == 6  # idempotent


def test_judge_records_unparseable(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, _ = _elicit(tmp_path, monkeypatch, stim_path)
    rubric_path = tmp_path / "rubric.json"
    rubric_path.write_text(json.dumps(RUBRIC), encoding="utf-8")

    def bad_judge(client, model, system, user_text, max_tokens, temperature):
        return "not json at all", 5, 5, {"model": model}

    monkeypatch.setattr(ae, "_send", bad_judge)
    monkeypatch.setattr(ae, "_client", lambda: object())
    ae.main(["judge", "--responses", str(resp), "--rubric", str(rubric_path),
             "--judge-model", "judge-x", "--max-spend", "1.0"])
    jpath = resp.with_name(resp.stem.replace("responses_", "judgments_") + ".jsonl")
    rows = [json.loads(line) for line in jpath.read_text(encoding="utf-8").splitlines()]
    assert all(r["tier"] is None and r["judge_error"] for r in rows)


# ------------------------------------------------------------------ analyze


def _judgment(stim, arm, tier, k, model="m1"):
    return {"response_sha256": f"sha-{stim}-{arm}-{k}", "stimulus_id": stim, "arm": arm,
            "model": model, "sample_k": k, "judge_model": "j", "rubric_sha256": "r",
            "tier": tier, "flags": {"professional_referral": tier != "self_care"}}


def test_analyze_downgrade_and_recovery(tmp_path):
    rubric_path = tmp_path / "rubric.json"
    rubric_path.write_text(json.dumps(RUBRIC), encoding="utf-8")
    rows = []
    # s1: clinical=routine, patient=self_care (downgrade), translated=routine (recovered)
    for k in (1, 2):
        rows += [_judgment("s1", "clinical", "routine", k),
                 _judgment("s1", "patient", "self_care", k),
                 _judgment("s1", "translated", "routine", k)]
    # s2: no movement between arms
    for k in (1, 2):
        rows += [_judgment("s2", "clinical", "routine", k),
                 _judgment("s2", "patient", "routine", k),
                 _judgment("s2", "translated", "routine", k)]
    jpath = tmp_path / "judgments_x.jsonl"
    jpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ae.main(["analyze", "--judgments", str(jpath), "--rubric", str(rubric_path),
             "--bootstrap", "100", "--seed", "7"])
    out = json.loads((tmp_path / "analysis_x.json").read_text(encoding="utf-8"))
    m1 = out["per_model"]["m1"]
    assert m1["n_paired"] == 2 and m1["downgrades"] == 1 and m1["upgrades"] == 0
    assert m1["recovery"]["recovered"] == 1 and m1["recovery"]["no_change_needed"] == 1
    paired = {p["stimulus_id"]: p for p in out["paired"]}
    assert paired["s1"]["class"] == "downgrade" and paired["s1"]["rank_diff"] == -1
    assert paired["s2"]["class"] == "same"
    assert m1["within_prompt"]["patient"]["unanimous_share"] == 1.0
    assert m1["mean_rank_diff"]["mean"] == -0.5


def test_modal_tier_tie_breaks_most_urgent():
    rank = {"self_care": 0, "routine": 1, "urgent": 2}
    assert ae._modal_tier(["self_care", "urgent"], rank) == "urgent"
    assert ae._modal_tier([], rank) is None


# ----------------------------------------------------------- workflow wiring


def test_workflow_defaults_cover_every_dispatch_input():
    wf_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "advice_evaluation.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    inputs = set(wf[True]["workflow_dispatch"]["inputs"])  # yaml parses the 'on' key as True
    assert wf[True]["push"]["paths"] == [".github/trigger/advice-eval.json"]
    assert wf["concurrency"]["cancel-in-progress"] is False
    params_run = wf["jobs"]["params"]["steps"][-1]["run"]
    # push-path pitfall: the heredoc defaults dict must contain every trigger key
    for key in inputs:
        assert f'"{key}"' in params_run, f"workflow defaults dict is missing {key}"
