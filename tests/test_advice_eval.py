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


# ----------------------------------------------------- multi-provider elicit


REGISTRY = {
    "fakeai": {"api": "openai-compat", "base_url": "https://fake.example/v1",
               "consumer_product": "fake consumer app", "consumer_default": "model-z",
               "key_env": "FAKEAI_API_KEY", "default_pricing": [0.5, 2.0]},
    "no_api": {"api": "manual_ui", "consumer_product": "ui-only product"},
}


def test_resolve_spec_variants(tmp_path):
    reg_path = tmp_path / "providers.json"
    reg_path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    reg = ae._load_providers(reg_path)
    assert ae._resolve_spec("fakeai", reg)["spec"] == "fakeai:model-z"  # consumer default
    assert ae._resolve_spec("fakeai:model-q", reg)["model"] == "model-q"  # explicit override
    bare = ae._resolve_spec("claude-haiku-4-5", reg)  # bare id -> anthropic builtin
    assert bare["provider"] == "anthropic" and bare["spec"] == "anthropic:claude-haiku-4-5"
    with pytest.raises(SystemExit, match="unknown provider"):
        ae._resolve_spec("nosuch:model", reg)
    with pytest.raises(SystemExit, match="import-manual-responses"):
        ae._resolve_spec("no_api", reg)  # manual_ui providers cannot be elicited via API


def test_finish_reason_captured_across_api_shapes():
    # Critic item 2026-07-22: compat-path records archived stop_reason=None, so a
    # Gemini max-token truncation was unattributable in the convenience field.
    assert ae._finish_reason({"stop_reason": "end_turn"}) == "end_turn"  # anthropic shape
    assert ae._finish_reason({"choices": [{"finish_reason": "length"}]}) == "length"  # compat shape
    assert ae._finish_reason({"choices": []}) is None
    assert ae._finish_reason({}) is None
    assert ae._finish_reason(None) is None


def test_registry_prices_rerouted_gemini_slug():
    # 2026-07-22: runs 1c and hedge-resume choked their max_spend ceilings because the
    # rerouted openrouter:google/gemini-3.5-flash spec fell through to the aggregator's
    # GPT-tier default_pricing (5, 30) - ~12x the flash-tier rate. The committed registry
    # must carry a per-model entry, resolved ahead of default_pricing exactly as elicit does.
    reg = ae._load_providers(Path(__file__).resolve().parents[1] / "data" / "advice_providers.json")
    r = ae._resolve_spec("openrouter:google/gemini-3.5-flash", reg)
    pricing = (r["cfg"].get("pricing") or {}).get(r["model"]) or r["cfg"].get("default_pricing")
    assert tuple(pricing) == (0.35, 2.75)
    other = ae._resolve_spec("openrouter:meta-llama/llama-4-maverick", reg)
    fallback = (other["cfg"].get("pricing") or {}).get(other["model"]) or other["cfg"].get("default_pricing")
    assert tuple(fallback) == (5.0, 30.0)  # arbitrary slugs keep the conservative catch-all


def test_elicit_openai_compat_provider(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    reg_path = tmp_path / "providers.json"
    reg_path.write_text(json.dumps(REGISTRY), encoding="utf-8")

    def stub_compat(cfg, model, system, user_text, max_tokens, temperature):
        assert cfg["base_url"] == "https://fake.example/v1" and model == "model-z"
        return "compat advice text", 100, 200, {"model": "model-z-live", "usage": {}}

    monkeypatch.setattr(ae, "_send_compat", stub_compat)
    monkeypatch.setattr(ae, "_send", _stub_send)
    monkeypatch.setattr(ae, "_client", lambda: object())
    ae.main(["elicit", "--stimuli", str(stim_path), "--models", "fakeai", "--providers", str(reg_path),
             "--arms", "clinical,patient", "--samples", "1", "--max-spend", "1.0",
             "--out-dir", str(stim_path.parent)])
    rows = [json.loads(x) for x in
            (stim_path.parent / f"responses_{stim_path.stem}.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert all(r["model_requested"] == "fakeai:model-z" and r["provider"] == "fakeai" for r in rows)
    assert all(r["model_returned"] == "model-z-live" and r["endpoint"] == "https://fake.example/v1"
               for r in rows)
    side = json.loads((stim_path.parent / f"responses_{stim_path.stem}.report.json")
                      .read_text(encoding="utf-8"))
    # registry pricing, not the conservative fallback: (100*0.5 + 200*2.0)/1e6 per call, 2 calls
    assert side["cost_usd"] == pytest.approx(2 * (100 * 0.5 + 200 * 2.0) / 1e6)
    assert side["providers"] == {"fakeai:model-z": "fakeai"}


def test_import_manual_responses(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, _ = _elicit(tmp_path, monkeypatch, stim_path)  # existing API records first
    manual = tmp_path / "captured.json"
    manual.write_text(json.dumps([
        {"stimulus_id": "s1", "arm": "patient", "product": "uiprod", "model_claimed": "ui-model-1",
         "captured_utc": "2026-07-21T12:00:00Z", "response_text": "ui advice one"},
        {"stimulus_id": "s1", "arm": "patient", "product": "uiprod",
         "captured_utc": "2026-07-21T12:05:00Z", "response_text": "ui advice two"},
    ]), encoding="utf-8")
    ae.main(["import-manual-responses", "--stimuli", str(stim_path), "--in", str(manual),
             "--out-dir", str(stim_path.parent)])
    rows = [json.loads(x) for x in resp.read_text(encoding="utf-8").splitlines()]
    ok, msg = ae.verify_chain(rows)
    assert ok, msg
    ui = [r for r in rows if r.get("endpoint") == "manual_ui"]
    assert [r["sample_k"] for r in ui] == [1, 2]  # auto-incremented per (stimulus, arm, product)
    assert all(r["model_requested"] == "uiprod:consumer_ui" and r["cost_usd"] == 0.0 for r in ui)
    assert ui[0]["capture"]["method"] == "manual_ui" and ui[0]["response_raw"] is None
    side = json.loads((stim_path.parent / f"responses_{stim_path.stem}.report.json")
                      .read_text(encoding="utf-8"))
    assert side["chain_head"] == rows[-1]["record_sha256"]
    assert side["manual_imports"][0]["records"] == 2

    # judge treats manual records uniformly (they are record_type advice)
    rubric_path = tmp_path / "rubric.json"
    rubric_path.write_text(json.dumps(RUBRIC), encoding="utf-8")
    monkeypatch.setattr(ae, "_send", _stub_send)
    monkeypatch.setattr(ae, "_client", lambda: object())
    ae.main(["judge", "--responses", str(resp), "--rubric", str(rubric_path),
             "--judge-model", "judge-x", "--max-spend", "1.0"])
    jpath = resp.with_name(resp.stem.replace("responses_", "judgments_") + ".jsonl")
    assert len(jpath.read_text(encoding="utf-8").splitlines()) == 8  # 6 API + 2 manual


@pytest.mark.parametrize("bad", [
    {"stimulus_id": "nope", "arm": "patient", "product": "p", "captured_utc": "x", "response_text": "t"},
    {"stimulus_id": "s1", "arm": "translated", "product": "p", "captured_utc": "x", "response_text": "t"},
    {"stimulus_id": "s1", "arm": "patient", "product": "", "captured_utc": "x", "response_text": "t"},
])
def test_import_manual_rejects_bad_entries(tmp_path, monkeypatch, bad):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    manual = tmp_path / "captured.json"
    manual.write_text(json.dumps([bad]), encoding="utf-8")
    with pytest.raises(SystemExit):
        ae.main(["import-manual-responses", "--stimuli", str(stim_path), "--in", str(manual),
                 "--out-dir", str(stim_path.parent)])


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


def test_send_compat_retries_transient_statuses_then_succeeds(monkeypatch):
    # run 1 (2026-07-22) died on a single Gemini 503: transient statuses must
    # retry with backoff, honoring Retry-After, before giving up
    calls = []

    class FakeResp:
        def __init__(self, status, body=None, retry_after=None):
            self.status_code = status
            self.headers = {"Retry-After": retry_after} if retry_after else {}
            self._body = body or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._body

    ok = {"choices": [{"message": {"content": "fine"}}],
          "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
    seq = [FakeResp(503), FakeResp(429, retry_after="2"), FakeResp(200, ok)]

    class FakeRequests:
        @staticmethod
        def post(url, **kw):
            calls.append(url)
            return seq[len(calls) - 1]

    naps = []
    monkeypatch.setattr(ae.time, "sleep", lambda s: naps.append(s))
    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    monkeypatch.setenv("FAKE_KEY", "k")
    cfg = {"api": "openai-compat", "base_url": "https://x.example/v1", "key_env": "FAKE_KEY"}
    text, in_tok, out_tok, raw, headers = ae._send_compat(cfg, "m", None, "hello", 64, 1.0)
    assert (text, in_tok, out_tok) == ("fine", 5, 7)
    assert len(calls) == 3 and len(naps) == 2
    assert naps[1] == 2.0          # Retry-After honored on the 429


def test_send_compat_exhausts_retries_and_raises(monkeypatch):
    class FakeResp:
        status_code = 503
        headers = {}

        def raise_for_status(self):
            raise RuntimeError("HTTP 503")

        def json(self):  # pragma: no cover
            return {}

    class FakeRequests:
        @staticmethod
        def post(url, **kw):
            return FakeResp()

    monkeypatch.setattr(ae.time, "sleep", lambda s: None)
    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    monkeypatch.setenv("FAKE_KEY", "k")
    cfg = {"api": "openai-compat", "base_url": "https://x.example/v1", "key_env": "FAKE_KEY"}
    with pytest.raises(RuntimeError, match="503"):
        ae._send_compat(cfg, "m", None, "hello", 64, 1.0)


def test_build_stimuli_only_hedges_filter(tmp_path, monkeypatch):
    # hedges: not flipped, penalty negative and past the magnitude floor
    payload = {"scenarios": [
        {"batch": "b", "batch_index": 1, "clinical_prompt": "c1", "patient_prompt": "p1",
         "flipped": True, "language_penalty": -0.5},                  # flip: excluded
        {"batch": "b", "batch_index": 2, "clinical_prompt": "c2", "patient_prompt": "p2",
         "flipped": False, "language_penalty": -0.4},                 # hedge: kept
        {"batch": "b", "batch_index": 3, "clinical_prompt": "c3", "patient_prompt": "p3",
         "flipped": False, "language_penalty": 0.2},                  # gained: excluded
        {"batch": "b", "batch_index": 4, "clinical_prompt": "c4", "patient_prompt": "p4",
         "flipped": False, "language_penalty": -0.05},                # below floor: excluded
    ]}
    pp = tmp_path / "payload.json"
    pp.write_text(json.dumps(payload))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "advice").mkdir(parents=True)
    ae.main(["build-stimuli", "--source", "payload", "--payload", str(pp),
             "--only-hedges", "--min-abs-penalty", "0.25"])
    out = sorted((tmp_path / "data" / "advice").glob("stimuli_*.json"))[-1]
    d = json.loads(out.read_text())
    assert [it["id"] for it in d["items"]] == ["b#2"]
    assert d["source"]["only_hedges"] is True


# ---------------- evaluation extensions (A-items + B-schema, 2026-07-22) ----


def test_manual_passthrough_reference_situation_variant(tmp_path, monkeypatch):
    manual = write_manual(tmp_path, [
        {"id": "v1", "clinical": "flurb alpha with a", "patient": "flurb allo wobbly with a",
         "reference": {"tier": "routine", "source": "clinician_panel",
                       "adjudicated_by": "dr-x", "date": "2026-07-22"},
         "situation_id": "sit_1", "variant": "neutral"},
        {"id": "v2", "clinical": "flurb beta with a", "patient": "flurb bee all weird with a",
         "situation_id": "sit_1", "variant": "misattributed"},
    ])
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual),
             "--out-dir", str(out_dir)])
    doc = json.loads(next(out_dir.glob("stimuli_*.json")).read_text(encoding="utf-8"))
    v1, v2 = doc["items"]
    assert v1["reference"]["tier"] == "routine" and v1["reference"]["adjudicated_by"] == "dr-x"
    assert "reference" not in v2
    assert (v1["situation_id"], v1["variant"]) == ("sit_1", "neutral")
    assert (v2["situation_id"], v2["variant"]) == ("sit_1", "misattributed")


def test_manual_reference_must_be_object_with_tier(tmp_path, monkeypatch):
    manual = write_manual(tmp_path, [
        {"id": "v1", "clinical": "a1 with a", "patient": "a2 with a", "reference": {"source": "x"}}])
    with pytest.raises(SystemExit, match="reference"):
        ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual),
                 "--out-dir", str(tmp_path / "advice")])


def _write_rubric(tmp_path):
    rubric = {"version": "t", "tiers": [{"id": "low", "label": "L", "definition": "d"},
                                        {"id": "mid", "label": "M", "definition": "d"},
                                        {"id": "high", "label": "H", "definition": "d"}],
              "flags": [], "judge_instructions": "{tiers}{flags}{response}"}
    p = tmp_path / "rubric.json"
    p.write_text(json.dumps(rubric), encoding="utf-8")
    return p


def _jrow(stim, model, arm, tier, k=1):
    return {"stimulus_id": stim, "model": model, "arm": arm, "tier": tier, "sample_k": k,
            "response_sha256": f"{stim}{model}{arm}{k}", "rubric_sha256": "r",
            "judge_model": "j", "flags": {}}


def test_analyze_reference_scoring_and_thesis_endpoint(tmp_path):
    rubric = _write_rubric(tmp_path)
    stimuli = {"items": [
        {"id": "s1", "reference": {"tier": "high"}},
        {"id": "s2", "reference": {"tier": "mid"}}]}
    sp = tmp_path / "stimuli.json"
    sp.write_text(json.dumps(stimuli), encoding="utf-8")
    rows = [
        # model A: correct on clinical, under-triages patient on both stimuli
        _jrow("s1", "A", "clinical", "high"), _jrow("s1", "A", "patient", "low"),
        _jrow("s2", "A", "clinical", "mid"), _jrow("s2", "A", "patient", "low"),
        # model B: over-triages s2 clinical, matches elsewhere
        _jrow("s1", "B", "clinical", "high"), _jrow("s1", "B", "patient", "high"),
        _jrow("s2", "B", "clinical", "high"), _jrow("s2", "B", "patient", "mid"),
    ]
    jp = tmp_path / "judgments_x.jsonl"
    jp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ae.main(["analyze", "--judgments", str(jp), "--rubric", str(rubric),
             "--stimuli", str(sp), "--bootstrap", "50", "--seed", "1"])
    out = json.loads((tmp_path / "analysis_x.json").read_text(encoding="utf-8"))
    ref = out["reference_scoring"]
    assert ref["n_referenced_stimuli"] == 2
    a_clin = ref["by_model_arm"]["A|clinical"]
    a_pat = ref["by_model_arm"]["A|patient"]
    assert a_clin == {"n": 2, "accuracy": 1.0, "under_triage_rate": 0.0, "over_triage_rate": 0.0}
    assert a_pat["under_triage_rate"] == 1.0
    b_clin = ref["by_model_arm"]["B|clinical"]
    assert b_clin["over_triage_rate"] == 0.5 and b_clin["accuracy"] == 0.5
    # thesis endpoint: A under-triages patient but not clinical -> +1.0 mean
    thesis_a = ref["under_triage_patient_minus_clinical"]["A"]
    assert thesis_a["mean"] == 1.0
    assert out["dispersion"]["consumer_lottery_by_arm"]["patient"] is not None


def test_analyze_dispersion_and_covariates(tmp_path):
    rubric = _write_rubric(tmp_path)
    rows = [
        # s1 clinical: A and B disagree (high vs low) -> lottery 1.0
        _jrow("s1", "A", "clinical", "high"), _jrow("s1", "B", "clinical", "low"),
        # s2 clinical: A and B agree -> lottery 0.0
        _jrow("s2", "A", "clinical", "mid"), _jrow("s2", "B", "clinical", "mid"),
        # self-lottery: model A s3 clinical, K=2 disagreeing samples
        _jrow("s3", "A", "clinical", "low", k=1), _jrow("s3", "A", "clinical", "high", k=2),
    ]
    jp = tmp_path / "judgments_y.jsonl"
    jp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    resp = [
        {"record_type": "advice", "model_requested": "A", "arm": "clinical",
         "response_text": "Take a rest. Then call someone."},
        {"record_type": "advice", "model_requested": "A", "arm": "clinical",
         "response_text": "Rest now."},
        {"record_type": "translation", "model_requested": "T", "response_text": "ignored"},
    ]
    rp = tmp_path / "responses_y.jsonl"
    rp.write_text("\n".join(json.dumps(r) for r in resp) + "\n", encoding="utf-8")
    ae.main(["analyze", "--judgments", str(jp), "--rubric", str(rubric),
             "--responses", str(rp), "--bootstrap", "50", "--seed", "1"])
    out = json.loads((tmp_path / "analysis_y.json").read_text(encoding="utf-8"))
    disp = out["dispersion"]
    # consumer lottery over s1 (1.0), s2 (0.0); s3 has a single model -> excluded
    assert disp["consumer_lottery_by_arm"]["clinical"] == 0.5
    assert disp["inter_model_agreement_by_arm"]["clinical"] == 0.5
    # self lottery: only s3 has K>=2 for A -> 1.0; B has no multi-sample cell
    assert disp["self_lottery_by_model"]["A"] == 1.0
    assert disp["self_lottery_by_model"]["B"] is None
    assert disp["tier_range_across_models_by_arm"]["clinical"]["max"] == 2
    cov = out["response_covariates"]["A|clinical"]
    assert cov["n"] == 2 and cov["mean_words"] == 4.0
    assert isinstance(cov["mean_fk_grade"], float)


def test_human_sample_stratified_by_arm(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path)
    rubric = _write_rubric(tmp_path)
    out = tmp_path / "judgments_z.jsonl"
    ae.main(["judge", "--responses", str(resp), "--rubric", str(rubric),
             "--out", str(out), "--human-sample", "4", "--max-spend", "0.1", "--dry-run"])
    csv_path = out.with_name(out.stem + "_human_sample.csv")
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    shas = [ln.split(",")[0] for ln in lines[1:]]
    rows = {r["response_sha256"]: r for r in ae._read_jsonl(resp) if r.get("record_type") == "advice"}
    arms = [rows[s]["arm"] for s in shas if s in rows]
    # 1 stimulus x 3 arms x K=2 archive: a 4-row sample must span >1 arm
    assert len(set(arms)) >= 2


def test_pace_spaces_same_provider_calls(monkeypatch):
    naps = []
    clock = {"t": 100.0}
    monkeypatch.setattr(ae.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(ae.time, "sleep", lambda s: naps.append(round(s, 3)))
    ae._LAST_CALL_AT.clear()
    cfg = {"min_interval_seconds": 10}
    ae._pace("g", cfg)             # first call: no wait
    clock["t"] = 103.0
    ae._pace("g", cfg)             # 3s later: wait the remaining 7
    ae._pace("other", {})          # unpaced provider: never waits
    assert naps == [7.0]
    ae._LAST_CALL_AT.clear()


# ---------------------------------------------------------------- recover-archive


def test_sidecar_cost_is_cumulative_across_resumes(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path)
    first = json.loads(sidecar.read_text(encoding="utf-8"))
    assert first["cost_basis"] == "cumulative_from_records"
    assert first["cost_usd"] == pytest.approx(first["run_cost_usd"], abs=1e-5)
    _elicit(tmp_path, monkeypatch, stim_path)  # resume appends nothing
    second = json.loads(sidecar.read_text(encoding="utf-8"))
    # the overwritten sidecar keeps the archive's full spend for the ledger
    assert second["run_cost_usd"] == 0.0
    assert second["cost_usd"] == pytest.approx(first["cost_usd"])


def _recover(stim_path, restored_dir, out_dir):
    ae.main(["recover-archive", "--restored-dir", str(restored_dir), "--stimuli", str(stim_path),
             "--source-run-id", "424242", "--out-dir", str(out_dir)])


def test_recover_archive_lands_extension(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path)
    full = resp.read_bytes()
    rows = [json.loads(x) for x in full.decode("utf-8").splitlines()]
    restored_dir = tmp_path / "restore"
    restored_dir.mkdir()
    (restored_dir / resp.name).write_bytes(full)
    # committed archive truncated to its first 3 records: the killed-run state
    resp.write_bytes(b"".join(line + b"\n" for line in full.splitlines()[:3]))
    _recover(stim_path, restored_dir, resp.parent)
    assert resp.read_bytes() == full
    side = json.loads(sidecar.read_text(encoding="utf-8"))
    assert side["records_total"] == len(rows)
    assert side["records_appended"] == len(rows) - 3
    assert side["chain_head"] == rows[-1]["record_sha256"]
    assert side["recovered_from_run_id"] == "424242"
    assert side["cost_basis"] == "cumulative_from_records"
    assert side["cost_usd"] == pytest.approx(
        sum(float(r.get("cost_usd") or 0.0) for r in rows if "cost_usd" in r))
    # idempotent: recovering the same snapshot again changes nothing
    _recover(stim_path, restored_dir, resp.parent)
    assert resp.read_bytes() == full


def test_recover_archive_drops_only_partial_final_line(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, sidecar = _elicit(tmp_path, monkeypatch, stim_path)
    full = resp.read_bytes()
    n = len(full.decode("utf-8").splitlines())
    restored_dir = tmp_path / "restore"
    restored_dir.mkdir()
    # the kill can interrupt the final append mid-line (no trailing newline)
    (restored_dir / resp.name).write_bytes(full + b'{"record_type": "advice", "half-writ')
    resp.unlink()  # no committed archive at all (nothing landed before the kill)
    _recover(stim_path, restored_dir, resp.parent)
    assert resp.read_bytes() == full
    side = json.loads(sidecar.read_text(encoding="utf-8"))
    assert side["dropped_partial_final_line"] is True and side["records_total"] == n


def test_recover_archive_refuses_divergent_prefix(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, _ = _elicit(tmp_path, monkeypatch, stim_path)
    rows = ae._read_jsonl(resp)
    # restored file with an intact chain that does NOT extend the committed
    # bytes: drop the first record and re-seal from a fresh chain root
    prev = None
    resealed = []
    for r in rows[1:]:
        body = {k: v for k, v in r.items() if k not in ("record_sha256", "prev_sha256")}
        sealed = ae._seal_record(body, prev)
        prev = sealed["record_sha256"]
        resealed.append(sealed)
    restored_dir = tmp_path / "restore"
    restored_dir.mkdir()
    (restored_dir / resp.name).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in resealed), encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing"):
        _recover(stim_path, restored_dir, resp.parent)


def test_recover_archive_refuses_corrupt_interior_line(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)
    resp, _ = _elicit(tmp_path, monkeypatch, stim_path)
    lines = resp.read_bytes().splitlines()
    lines[1] = b"not json at all"
    restored_dir = tmp_path / "restore"
    restored_dir.mkdir()
    (restored_dir / resp.name).write_bytes(b"".join(ln + b"\n" for ln in lines))
    with pytest.raises(SystemExit, match="corrupt interior"):
        _recover(stim_path, restored_dir, resp.parent)


def test_payload_complete_with_target(tmp_path):
    payload = {"scenarios": [
        {"batch": "pairs_x", "batch_index": 1, "clinical_prompt": "alpha frame so I reached for a",
         "patient_prompt": "alpha variant frame so I reached for a", "flipped": True,
         "language_penalty": -0.2, "screening": {"status": "passed"},
         "target_token": "wid", "intended_target": "widget"},
        {"batch": "pairs_x", "batch_index": 2, "clinical_prompt": "beta frame with a",
         "patient_prompt": "beta variant frame with a", "flipped": True,
         "language_penalty": -0.3, "screening": {"status": "passed"}},
    ]}
    src = tmp_path / "payload.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "payload", "--payload", str(src),
             "--only-flips", "--complete-with-target", "--out-dir", str(out_dir)])
    doc = json.loads(next(out_dir.glob("stimuli_*.json")).read_text(encoding="utf-8"))
    # item 2 has no intended_target/target_token: skipped with a notice
    assert [i["id"] for i in doc["items"]] == ["pairs_x#1"]
    it = doc["items"][0]
    # full intended word (not the wordpiece), same on both sides, sentence closed
    assert it["clinical_body"].endswith("reached for a widget.")
    assert it["patient_body"].endswith("reached for a widget.")
    assert it["meta"]["completed_with"] == "widget"
    # completed default suffix drops the ellipsis but keeps the same words
    assert doc["ask_suffix"] == "Anyway what should I do?"
    assert it["clinical_message"].endswith("widget. Anyway what should I do?")
    assert doc["source"]["complete_with_target"] is True
    # flag is payload-only
    with pytest.raises(SystemExit, match="only applies"):
        ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(src),
                 "--complete-with-target", "--out-dir", str(out_dir)])


def test_payload_complete_override(tmp_path):
    payload = {"scenarios": [
        {"batch": "pairs_x", "batch_index": 1, "clinical_prompt": "alpha frame so I reached for a",
         "patient_prompt": "alpha variant frame so I reached for a", "flipped": True,
         "language_penalty": -0.2, "screening": {"status": "passed"},
         "intended_target": "wid"},
    ]}
    src = tmp_path / "payload.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "payload", "--payload", str(src), "--only-flips",
             "--complete-with-target", "--complete-override", '{"pairs_x#1": "widget kit"}',
             "--out-dir", str(out_dir)])
    doc = json.loads(next(out_dir.glob("stimuli_*.json")).read_text(encoding="utf-8"))
    it = doc["items"][0]
    # the owner-approved word wins over the payload's partial intended_target
    assert it["clinical_body"].endswith("reached for a widget kit.")
    assert it["meta"]["completed_with"] == "widget kit"
    assert it["meta"]["completion_override"] is True
    assert doc["source"]["complete_overrides"] == {"pairs_x#1": "widget kit"}
    # override without the completion flag is a usage error
    with pytest.raises(SystemExit, match="requires"):
        ae.main(["build-stimuli", "--source", "payload", "--payload", str(src),
                 "--complete-override", '{"pairs_x#1": "widget kit"}', "--out-dir", str(out_dir)])


def test_anthropic_send_retries_transient_statuses(monkeypatch):
    class Boom(Exception):
        def __init__(self, status, body=None):
            self.status_code = status
            self.body = body

    calls = {"n": 0}

    def flaky(client, model, system, user_text, max_tokens, temperature):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Boom(522, {"retry_after": 3})
        if calls["n"] == 2:
            raise Boom(529)
        return "ok", 1, 2, {"model": model}

    naps = []
    monkeypatch.setattr(ae, "_send", flaky)
    monkeypatch.setattr(ae.time, "sleep", lambda s: naps.append(s))
    out = ae._send_anthropic_retrying(object(), "model-a", None, "hi", 10, 0.0)
    assert out[0] == "ok" and calls["n"] == 3
    assert naps == [3.0, 4]  # retry_after honored, then default backoff step 2

    # a non-retryable status raises immediately
    def hard_fail(client, model, system, user_text, max_tokens, temperature):
        raise Boom(400)
    monkeypatch.setattr(ae, "_send", hard_fail)
    with pytest.raises(Boom):
        ae._send_anthropic_retrying(object(), "model-a", None, "hi", 10, 0.0)


# ------------------------------------------------------- build-info capture


def test_send_captures_headers_via_raw_response():
    # A1 (2026-07-23): the anthropic seam must surface response headers so records
    # can carry request ids and api versions for vendor-side log correlation
    class Usage:
        input_tokens, output_tokens = 3, 4

    class Block:
        type, text = "text", "hi"

    class Parsed:
        content, usage = [Block()], Usage()

        def model_dump(self):
            return {"model": "m-1", "system_fingerprint": "fp_abc"}

    class Wrapped:
        headers = {"Request-Id": "req_123", "anthropic-version": "2023-06-01"}

        def parse(self):
            return Parsed()

    class RawAPI:
        def create(self, **kw):
            return Wrapped()

    class Messages:
        with_raw_response = RawAPI()

    class Client:
        messages = Messages()

    text, i, o, raw, headers = ae._send(Client(), "m", None, "u", 64, 1.0)
    assert text == "hi" and headers["request-id"] == "req_123"
    assert ae._build_info(raw, headers) == {
        "request_id": "req_123", "api_version": "2023-06-01", "build_fingerprint": "fp_abc"}


def test_send_compat_returns_headers(monkeypatch):
    class Resp:
        status_code = 200
        headers = {"X-Request-Id": "rq9", "openai-version": "v2"}

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                    "system_fingerprint": "fp_z"}

    class FakeRequests:
        @staticmethod
        def post(*a, **k):
            return Resp()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    monkeypatch.setenv("FAKE_KEY", "k")
    cfg = {"api": "openai-compat", "base_url": "https://x.example/v1", "key_env": "FAKE_KEY"}
    text, i, o, raw, headers = ae._send_compat(cfg, "m", None, "u", 64, 1.0)
    assert ae._build_info(raw, headers) == {
        "request_id": "rq9", "api_version": "v2", "build_fingerprint": "fp_z"}


def test_elicit_records_carry_build_info(tmp_path, monkeypatch):
    stim_path = build_manual_stimuli(tmp_path, monkeypatch)

    def stub5(client, model, system, user_text, max_tokens, temperature):
        raw = {"model": model + "-served", "system_fingerprint": "fp_e2e"}
        return "advice placeholder", 5, 6, raw, {"request-id": "req_e2e"}

    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_send", stub5)
    ae.main(["elicit", "--stimuli", str(stim_path), "--models", "model-x",
             "--arms", "clinical", "--samples", "1",
             "--max-spend", "1.0", "--out-dir", str(tmp_path / "advice")])
    rows = [json.loads(line) for line in
            (tmp_path / "advice" / f"responses_{stim_path.stem}.jsonl").read_text().splitlines()]
    adv = [r for r in rows if r["record_type"] == "advice"][0]
    assert adv["request_id"] == "req_e2e"
    assert adv["build_fingerprint"] == "fp_e2e"
    assert adv["api_version"] is None
