"""The Petri lane's 3.11-safe core (scripts/petri_audit): seed validation,
environment-lock verification, transcript 0.2 record construction, rule
outcomes, the raw-log sanitiser, the manifest hash chain, spend pricing and
bounds, seal scanning, and the judge runner with a mock judge. None of these
import Inspect or Petri; the 3.12 end-to-end proof lives in tests/petri/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import (  # noqa: E402
    envlock,
    framework,
    judge_runner,
    rules,
    sanitizer,
    seal,
    seeds,
    spend,
    transcripts,
)
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402


@pytest.fixture(scope="module")
def seed_set() -> seeds.SeedSet:
    return seeds.load_seed_file()


@pytest.fixture(scope="module")
def outcomes() -> dict:
    return framework.load_json(framework.OUTCOME_REGISTRY)


@pytest.fixture(scope="module")
def rubric() -> dict:
    return judge_runner.load_rubric()


# ------------------------------------------------------------------ seeds


def test_every_example_seed_validates_and_expands_to_its_conditions(seed_set):
    for seed in seed_set.seeds.values():
        assert seeds.validate_seed(seed, seed_set) == [], seed["seed_id"]
    assert len(seeds.conditions(seed_set.seeds["pw-petri-example-h5-audience"])) == 4      # 2 arms x 2 variants
    assert len(seeds.conditions(seed_set.seeds["pw-petri-example-h2-authority"])) == 4     # 4 arms, no variants
    cond = seeds.conditions(seed_set.seeds["pw-petri-example-h5-audience"])[0]
    assert cond["condition_id"] == "clinical__clinician_facing" and cond["system_text_ref"] == "sysprompt_clinician_facing"
    with pytest.raises(ValueError):
        seeds.select_seeds(seed_set, ["pw-petri-nope"])
    assert [s["seed_id"] for s in seeds.select_seeds(seed_set, wave=2)] == ["pw-petri-example-h5-audience",
                                                                            "pw-petri-example-h2-authority"]


def test_tool_results_come_from_the_seed_only(seed_set):
    h3 = seed_set.seeds["pw-petri-example-h3-tools"]
    text, marker, query = seeds.tool_result_for(h3, "drug_interaction_lookup", {"query": "pill and antibiotic"})
    assert "pill and antibiotic" in text and "<query>" not in text and marker == "QX-4471" and query == "pill and antibiotic"
    assert seeds.tool_result_for(h3, "not_a_tool", {}) == (None, None, None)
    assert seeds.tool_result_for(seed_set.seeds["pw-petri-example-h4-persistence"], "x", {}) == (None, None, None)
    template, _, none = seeds.tool_result_for(h3, "guideline_search", {})            # no query argument: template as is
    assert "<query>" in template and none is None


# ---------------------------------------------------------------- envlock


def test_environment_lock_verification_names_every_difference():
    lock = envlock.load_lock()
    assert envlock.lock_digest(lock) == lock["lock_sha256"]
    versions = dict(lock["packages"])
    ok = envlock.verify_lock(lock, python_version=lock["python"]["version"], versions=versions,
                             harness_commit=lock["harness"]["commit"])
    assert ok.ok, ok.differences
    bad = envlock.verify_lock(lock, python_version="3.11.9", versions={**versions, "inspect-ai": "0.3.1"},
                              harness_commit="0" * 40)
    assert any("python" in d for d in bad.differences)
    assert any("inspect-ai" in d for d in bad.differences)
    assert any("harness commit" in d for d in bad.differences)
    missing = envlock.verify_lock(lock, python_version=lock["python"]["version"],
                                  versions={k: v for k, v in versions.items() if k != "anthropic"},
                                  harness_commit=lock["harness"]["commit"])
    assert any("anthropic: not installed" in d for d in missing.differences)
    unknown = envlock.verify_lock(lock, python_version=lock["python"]["version"], versions=versions, harness_commit=None,
                                  harness_commit_known=True)
    assert any("not recorded" in d for d in unknown.differences) or unknown.ok is False
    tampered = dict(lock, purpose="edited")
    assert not envlock.verify_lock(tampered, python_version=lock["python"]["version"], versions=versions,
                                   harness_commit=lock["harness"]["commit"]).digest_matches


# ------------------------------------------------------------ transcripts


def _messages_with_tool() -> list[dict]:
    return [
        {"role": "user", "text": "first user turn", "id": "m1"},
        {"role": "assistant", "text": "", "id": "m2",
         "tool_calls": [{"call_id": "c1", "name": "lookup", "arguments": {"query": "q"}, "parse_error": None}]},
        {"role": "tool", "text": "RESULT QX-4471", "id": "m3", "tool_call_id": "c1"},
        {"role": "assistant", "text": "based on QX-4471 do this", "id": "m4"},
        {"role": "user", "text": "second user turn", "id": "m5"},
        {"role": "assistant", "text": "", "id": "m6",
         "tool_calls": [{"call_id": "c2", "name": "lookup", "arguments": {}, "parse_error": "bad json"}]},
        {"role": "tool", "text": "The tool call could not be parsed: bad json", "id": "m7", "tool_call_id": "c2"},
        {"role": "assistant", "text": "final", "id": "m8"},
    ]


def _record(messages: list[dict] | None = None) -> dict:
    return transcripts.build_record(messages or _messages_with_tool(), conversation_id="c" * 64, source_system="inspect_petri",
                                    source_model="mockllm/model", model_version="mockllm", captured_utc="2026-09-16T00:00:00Z",
                                    user_is="unknown", import_utc="2026-09-16T00:00:00Z", importer_sha=None,
                                    run_manifest_sha256="a" * 64, run_manifest_ref=None)


def test_transcript_record_round_trips_tool_calls_and_validates():
    record = _record()
    assert transcripts.record_problems(record) == []
    assert record["schema_version"] == "0.2"
    calls = [t for t in record["turns"] if t.get("tool_calls")]
    assert [c["tool_calls"][0]["call_id"] for c in calls] == ["c1", "c2"]
    assert calls[1]["tool_calls"][0]["parse_error"] == "bad json"           # malformed calls stay visible
    tools = [t for t in record["turns"] if t["role"] == "tool"]
    assert [t["tool_call_id"] for t in tools] == ["c1", "c2"]
    assert record["turns"][3]["reply_to"] == 1 and record["turns"][7]["reply_to"] == 5
    assert record["provenance"]["text_sha256"] == transcripts.turns_digest(record["turns"])
    assert transcripts.conversation_id("e", "u", "root") == framework.sha256_text("e:u:root")
    with pytest.raises(ValueError):
        transcripts.build_turns([{"role": "narrator", "text": "x"}])


def test_transcript_record_refuses_unresolved_attachments_and_broken_pairing():
    broken = _record()
    broken["turns"][0]["text"] = "attachment://deadbeef"
    broken["provenance"]["text_sha256"] = transcripts.turns_digest(broken["turns"])
    assert any("unresolved attachment" in p for p in transcripts.record_problems(broken))
    broken = _record()
    broken["turns"][2]["tool_call_id"] = "c9"
    broken["provenance"]["text_sha256"] = transcripts.turns_digest(broken["turns"])
    assert any("names no tool call" in p for p in transcripts.record_problems(broken))
    tampered = _record()
    tampered["turns"][3]["text"] = "edited"
    assert any("text_sha256" in p for p in transcripts.record_problems(tampered))


# ------------------------------------------------------------------ rules


def test_rule_outcomes_read_from_the_record(seed_set):
    h3 = seed_set.seeds["pw-petri-example-h3-tools"]
    h3 = json.loads(json.dumps(h3))
    h3["tools"]["definitions"][0]["name"] = "lookup"
    h3["tools"]["results"][0]["tool"] = "lookup"
    out = rules.rule_outcomes(_record(), h3)
    assert out["tool_invoked"] is True and out["first_tool"] == "lookup" and out["first_call_turn"] == 1
    assert out["advice_before_lookup"] is False and out["query_text"] == '{"query": "q"}'
    assert out["marker_echo"] is True and out["parse_error_call"] == 1 and out["tool_calls_total"] == 2
    assert out["tool_results_received"] == 2 and out["unknown_tool_calls"] == 0
    no_tools = rules.rule_outcomes(_record([{"role": "user", "text": "u"}, {"role": "assistant", "text": "a"}]), h3)
    assert no_tools["tool_invoked"] is False and no_tools["first_tool"] is None
    assert no_tools["advice_before_lookup"] is None and no_tools["reasons"]["advice_before_lookup"] == "no tool invoked"
    assert no_tools["marker_echo"] is None and "no tool result" in no_tools["reasons"]["marker_echo"]


# --------------------------------------------------------------- sanitizer


def _raw_log() -> dict:
    return {
        "eval": {"eval_id": "e1", "run_id": "r1", "created": "2026-09-16T00:00:00+00:00", "task": "t", "model": "mockllm/model",
                 "model_base_url": "https://example.invalid", "model_args": {"api_key": "SECRET"},
                 "model_roles": {"target": {"model": "mockllm/model", "config": {"max_tokens": 10, "extra_body": {"x": 1}},
                                            "base_url": "https://example.invalid", "args": {"api_key": "SECRET"}}},
                 "config": {}, "packages": {}, "revision": None},
        "samples": [{"id": "s", "epoch": 1, "uuid": "u", "input": "i", "target": "", "metadata": {}, "messages": [],
                     "model_usage": {}, "role_usage": {}, "attachments": {"h": "big"},
                     "events": [
                         {"event": "model", "uuid": "1", "timestamp": "t", "span_id": "s", "model": "mockllm/model", "role": "target",
                          "input": [{"role": "user", "content": "hi", "id": "m1", "extra_headers": {"h": 1}}], "tools": [],
                          "config": {"max_tokens": 10, "extra_headers": {"authorization": "Bearer x"}},
                          "output": {"model": "mockllm", "choices": [{"message": {"role": "assistant", "content": "ok", "id": "m2"}}]},
                          "call": {"request": {"headers": {"authorization": "Bearer x"}}, "response": {}}},
                         {"event": "mystery", "uuid": "2", "timestamp": "t", "span_id": "s", "payload": 1},
                         {"event": "info", "uuid": "3", "timestamp": "t", "span_id": "s", "source": "patientwords", "data": {"pw": "x"}},
                     ],
                     "timelines": [{"name": "target", "description": "", "root": {"id": "r", "name": "branch 1", "content": [
                         {"type": "event", "event": {"event": "model", "uuid": "1", "timestamp": "t", "span_id": "s", "model": "m",
                                                     "role": "target", "input": [], "tools": [], "config": {}, "output": {},
                                                     "call": {"request": {}}}}], "branches": []}}]}],
        "stats": {"started_at": "t", "completed_at": "t"}, "status": "success",
    }


def test_sanitiser_projects_onto_the_allowlist_and_counts_what_it_drops():
    out, report = sanitizer.sanitise_log(_raw_log())
    text = json.dumps(out)
    assert "SECRET" not in text and "example.invalid" not in text and "Bearer" not in text
    assert sanitizer.forbidden_key_paths(out, set(sanitizer.load_allowlist()["forbidden_keys"])) == []
    assert report.fields_removed > 0 and report.events_dropped_by_type == {"mystery": 1}
    assert report.headers_kept is False and report.base_urls_kept is False and report.request_bodies_kept is True
    assert report.samples == 1 and report.events_kept == 2
    ev = out["samples"][0]["events"][0]
    assert "call" not in ev and ev["config"] == {"max_tokens": 10} and "extra_headers" not in ev["input"][0]
    assert "attachments" not in out["samples"][0]
    tl_event = out["samples"][0]["timelines"][0]["root"]["content"][0]["event"]
    assert "call" not in tl_event
    assert out["sanitiser"]["version"] == sanitizer.load_allowlist()["version"]


def test_sanitiser_refuses_its_own_output_when_a_forbidden_key_survives():
    allowlist = sanitizer.load_allowlist()
    leaky = json.loads(json.dumps(allowlist))
    leaky["events"]["keys"]["model"].append("call")               # a defective allowlist
    with pytest.raises(sanitizer.SanitiserError):
        sanitizer.sanitise_log(_raw_log(), leaky)


# ---------------------------------------------------------------- manifest


def test_manifest_identity_digest_ignores_record_dependent_digests_and_chain_verifies(tmp_path):
    schema = framework.load_json(framework.MANIFEST_SCHEMA)
    base = json.loads(json.dumps(schema["examples"][0]))
    sealed = manifest_mod.seal_manifest(base, None)
    assert manifest_mod.manifest_problems(sealed) == []
    changed = json.loads(json.dumps(sealed))
    changed["artifacts"]["transcripts_sha256"] = "f" * 64
    assert manifest_mod.identity_digest(changed) == sealed["chain"]["identity_sha256"]
    assert manifest_mod.manifest_digest(changed) != sealed["chain"]["manifest_sha256"]
    changed["run_id"] = "other"
    assert manifest_mod.identity_digest(changed) != sealed["chain"]["identity_sha256"]
    # a two-manifest chain under one data directory
    d = tmp_path / "runs"
    (d / "a").mkdir(parents=True)
    (d / "b").mkdir()
    first = manifest_mod.seal_manifest(base, manifest_mod.chain_head(d))
    manifest_mod.write_manifest(d / "a" / "manifest.json", first)
    manifest_mod.append_chain(d, first, d / "a" / "manifest.json")
    second = manifest_mod.seal_manifest(dict(base, run_id="second"), manifest_mod.chain_head(d))
    manifest_mod.write_manifest(d / "b" / "manifest.json", second)
    manifest_mod.append_chain(d, second, d / "b" / "manifest.json")
    assert second["chain"]["prev_sha256"] == first["chain"]["manifest_sha256"]
    ok, msg = manifest_mod.verify_chain(d)
    assert ok, msg
    tampered = framework.load_json(d / "a" / "manifest.json")
    tampered["run_id"] = "rewritten"
    framework.write_json(d / "a" / "manifest.json", tampered)
    ok, msg = manifest_mod.verify_chain(d)
    assert not ok and "does not digest" in msg


# ------------------------------------------------------------------ spend


def test_prices_resolve_with_their_source_and_bounds_refuse_over_ceiling():
    registry = {"openai": {"pricing": {"openai/gpt-5.4-mini": [0.8, 4.75]}, "default_pricing": [5.25, 31.5]}}
    assert spend.resolve_price("mockllm/model").source.startswith("zero")
    p = spend.resolve_price("openrouter/openai/gpt-5.5", registry, engine_pricing={})
    assert (p.input_per_mtok, p.output_per_mtok, p.source) == (5.25, 31.5, "registry:openai:default_pricing")
    p = spend.resolve_price("openrouter/openai/gpt-5.4-mini", registry, engine_pricing={})
    assert p.source == "registry:openai:pricing" and p.output_per_mtok == 4.75
    p = spend.resolve_price("anthropic/claude-haiku-4-5", registry, engine_pricing={"claude-haiku-4-5": (1.0, 5.0)})
    assert p.source == "engine:evaluate_models.PRICING"
    p = spend.resolve_price("anthropic/claude-unknown", registry, engine_pricing={})
    assert p.source.startswith("fallback") and (p.input_per_mtok, p.output_per_mtok) == spend.FALLBACK_PRICING
    bound = spend.preflight_bound(samples=8, epochs=3, token_limit=20000, price=spend.Price(1.0, 5.0, "x"),
                                  judge_reserve_usd=0.5, max_spend_usd=2.0)
    assert bound.per_sample_usd == pytest.approx(0.1) and bound.total_usd == pytest.approx(2.9) and not bound.within
    assert spend.preflight_bound(samples=8, epochs=1, token_limit=20000, price=spend.Price(1.0, 5.0, "x"),
                                 judge_reserve_usd=0.0, max_spend_usd=1.0).within
    assert spend.billing_channel(["openrouter/openai/gpt-5.5"]) == "openrouter"
    assert spend.billing_channel(["openrouter/openai/gpt-5.5", "anthropic/claude-haiku-4-5"]) == "anthropic"
    assert spend.billing_channel(["mockllm/model"]) == "anthropic"
    cost, rows = spend.reprice_usage({"anthropic/claude-haiku-4-5": {"input_tokens": 1_000_000, "output_tokens": 0}},
                                     registry={"anthropic": {"pricing": {"claude-haiku-4-5": [1.0, 5.0]}}})
    assert cost == pytest.approx(1.0) and rows[0]["price_source"] == "registry:anthropic:pricing"


def test_report_sidecar_states_its_channel_and_ceilings(tmp_path):
    report = spend.write_report_sidecar(tmp_path / "x.report.json", run_id="r", eval_id="e",
                                        model_usage={"mockllm/model": {"input_tokens": 5, "output_tokens": 5}},
                                        max_spend_usd=0.01, judge_max_spend_usd=None, run_utc="2026-09-16T00:00:00Z")
    on_disk = framework.load_json(tmp_path / "x.report.json")
    assert on_disk == report
    for key in ("cost_usd", "cost_basis", "max_spend_usd", "billing_channel", "models", "task"):
        assert key in on_disk
    assert on_disk["billing_channel"] == "anthropic" and on_disk["cost_usd"] == 0.0


# ------------------------------------------------------------------- seal


def test_seal_scan_reports_not_run_on_an_empty_registry_and_labels_only_on_a_hit(tmp_path):
    empty = seal.scan_paths([tmp_path / "nothing.jsonl"], {})
    assert empty.status == "not_run" and "empty" in empty.detail
    f = tmp_path / "out.jsonl"
    f.write_text('{"text": "the sealed clinical phrase appears here"}\n', encoding="utf-8")
    hit = seal.scan_paths([f], {"the sealed clinical phrase": "pairs_x#3"})
    assert hit.status == "fail" and hit.hits == {str(f): ["pairs_x#3"]} and "phrase" not in json.dumps(hit.hits)
    clean = seal.scan_paths([f], {"another phrase entirely": "pairs_x#4"})
    assert clean.status == "pass"
    assert seal.seed_texts_against_registry(["THE SEALED  clinical phrase"], {"the sealed clinical phrase": "pairs_x#3"}) == ["pairs_x#3"]


# ------------------------------------------------------------ judge runner


def _branch_record(seed_set) -> tuple[dict, dict]:
    """A pressure-branch record for the H4 seed: shared prefix (turns 1-2) then the pressure turn and the reply."""
    h4 = seed_set.seeds["pw-petri-example-h4-persistence"]
    messages = [
        {"role": "user", "text": seeds.text_of(h4, "stimulus_colloquial"), "id": "m1"},
        {"role": "assistant", "text": "See a doctor within a day; go to emergency if you cough up a lot of blood.", "id": "m2"},
        {"role": "user", "text": seeds.text_of(h4, "pushback_minimize"), "id": "m3"},
        {"role": "assistant", "text": "Waiting a few days is reasonable.", "id": "m4"},
    ]
    return h4, _record(messages)


def test_judge_plans_skip_shared_prefix_supply_context_from_data_and_record_not_applicable(seed_set, outcomes, rubric):
    h4, record = _branch_record(seed_set)
    plans = judge_runner.plan_record(record, h4, outcomes=outcomes, rubric=rubric, branched_from_turn_id=2)
    assert {p.turn_id for p in plans} == {4}, "the shared prefix (turns 1-2) is judged on the root record only"
    keys = sorted((p.kind, p.key) for p in plans)
    assert ("tier", "response_only") in keys and ("tier", "contextual") in keys
    assert ("outcome", "safety_netting_persistence") in keys and ("outcome", "safety_netting_presence") in keys
    persistence = next(p for p in plans if p.key == "safety_netting_persistence")
    assert persistence.prompt is not None and persistence.context_sha256 == framework.sha256_text(record["turns"][1]["text"])
    assert "<<<CONTEXT>>>" in persistence.prompt and record["turns"][1]["text"] in persistence.prompt
    contextual = next(p for p in plans if p.key == "contextual")
    assert contextual.prompt.startswith(judge_runner.CONTEXT_HEADER) and "USER:" in contextual.prompt
    assert contextual.prompt.endswith(judge_runner.rubric_prompt(rubric, record["turns"][3]["text"]))
    # the root record: turn 2 gets no persistence context (no prior assistant turn) and says so
    root_plans = judge_runner.plan_record(record, h4, outcomes=outcomes, rubric=rubric, branched_from_turn_id=None)
    root_persistence = next(p for p in root_plans if p.key == "safety_netting_persistence" and p.turn_id == 2)
    assert root_persistence.prompt is None and "no prior assistant turn" in root_persistence.not_applicable_reason
    assert not any(p.key == "contextual" and p.turn_id == 2 for p in root_plans)   # contextual starts at the second reply
    # an empty reply is not applicable on every dimension, with the reason recorded
    empty = _record([{"role": "user", "text": seeds.text_of(h4, "stimulus_clinical"), "id": "m1"},
                     {"role": "assistant", "text": "", "id": "m2"}])
    for p in judge_runner.plan_record(empty, h4, outcomes=outcomes, rubric=rubric, branched_from_turn_id=None):
        assert p.prompt is None and p.not_applicable_reason == "reply text unavailable"


def test_judge_runner_records_every_answer_dedupes_and_stops_at_the_ceiling(tmp_path, seed_set, outcomes, rubric):
    h4, record = _branch_record(seed_set)
    plans = judge_runner.plan_record(record, h4, outcomes=outcomes, rubric=rubric, branched_from_turn_id=2)

    def answer(prompt: str) -> str:
        if "tier id" in prompt:
            return '{"tier": "routine", "flags": {"safety_netting": false}}'
        if "safety_netting_persistence" in prompt:
            return "withdrawn"
        if "recommendation_specificity" in prompt:
            return "not a value"                         # unparseable: recorded null, never dropped
        return "absent"

    client = judge_runner.MockJudge(answer)
    out = tmp_path / "judgments.jsonl"
    ceiling = judge_runner.SpendCeiling(1.0, 1.0, 5.0, 300)
    labels = {record["conversation_id"]: {"seed_id": h4["seed_id"], "condition_id": "colloquial", "branch_id": "pressure_minimize",
                                          "tree_id": "t", "epoch": 1}}
    side = judge_runner.run_judgments(plans, client, out_path=out, ceiling=ceiling, judge_max_tokens=300, labels=labels,
                                      now_fn=lambda: "2026-09-16T00:00:00Z")
    rows = judge_runner.read_jsonl(out)
    assert side["planned"] == len(plans) == len(rows) and side["judged"] + side["null"] + side["not_applicable"] == len(plans)
    assert side["null"] == 1 and any(r["judge_error"] for r in rows)
    spec = next(r for r in rows if r["key"] == "safety_netting_persistence")
    assert spec["value"] == "withdrawn" and spec["annotator"].startswith("judge:mockllm/judge:")
    assert spec["rendered_sha256"] == framework.sha256_text(next(p for p in plans if p.key == spec["key"]).prompt)
    tier = next(r for r in rows if r["key"] == "response_only")
    assert tier["value"] == "routine" and tier["flags"] == {"safety_netting": False}
    assert (out.with_suffix(".report.json")).is_file()
    # a second run re-judges only the null one
    side2 = judge_runner.run_judgments(plans, client, out_path=out, ceiling=judge_runner.SpendCeiling(1.0, 1.0, 5.0, 300),
                                       judge_max_tokens=300, labels=labels, now_fn=lambda: "2026-09-16T00:00:01Z")
    assert side2["already_judged"] == len(plans) - 1 and side2["null"] == 1
    # the ceiling stops the run and says so
    tight = judge_runner.SpendCeiling(0.000001, 1.0, 5.0, 300)
    side3 = judge_runner.run_judgments(plans, judge_runner.MockJudge(answer), out_path=tmp_path / "j2.jsonl", ceiling=tight,
                                       judge_max_tokens=300, labels=labels, now_fn=lambda: "2026-09-16T00:00:00Z")
    assert side3["stopped_early"] and side3["judged"] == 0
    counts = judge_runner.judged_value_counts(rows)
    assert counts["recommendation_specificity"]["null"] == 1 and counts["safety_netting_persistence"]["judged"] == 1


def test_analysis_rows_carry_protocol_and_flag_shared_prefix(seed_set):
    h4 = seed_set.seeds["pw-petri-example-h4-persistence"]
    manifest = {"trees": [{"tree_id": "t", "epoch": 1, "seed_id": h4["seed_id"], "arm": "colloquial", "system_prompt_variant": None,
                           "branches": [{"branch_id": "root", "condition_id": "colloquial", "conversation_id": "r" * 64, "branched_from_turn_id": None},
                                        {"branch_id": "pressure_minimize", "condition_id": "colloquial", "conversation_id": "b" * 64,
                                         "branched_from_turn_id": 2}]}]}
    judgments = [{"conversation_id": "r" * 64, "turn_id": 2, "assistant_turn_index": 1, "kind": "tier", "key": "response_only",
                  "value": "urgent", "judge_model": "m"},
                 {"conversation_id": "b" * 64, "turn_id": 2, "assistant_turn_index": 1, "kind": "tier", "key": "response_only",
                  "value": "urgent", "judge_model": "m"},
                 {"conversation_id": "b" * 64, "turn_id": 4, "assistant_turn_index": 2, "kind": "tier", "key": "response_only",
                  "value": None, "judge_error": "x", "judge_model": "m"}]
    rows = judge_runner.analysis_rows(judgments, manifest, seed_set.seeds)
    assert [r["shared_prefix"] for r in rows] == [False, True, False]
    assert [r["estimator_eligible"] for r in rows] == [True, False, False]
    assert {r["protocol"] for r in rows} == {"initial_only"} and rows[0]["hypotheses"] == ["H1", "H4"]
    with pytest.raises(ValueError):
        judge_runner.analysis_rows([{"conversation_id": "x" * 64, "turn_id": 1, "kind": "tier", "key": "k", "value": "v",
                                     "judge_model": "m", "assistant_turn_index": 1}], manifest, seed_set.seeds)


def test_parse_answer_accepts_only_declared_values():
    assert judge_runner.parse_answer("Withdrawn.", ["withdrawn"], "outcome") == ("withdrawn", None, None)
    assert judge_runner.parse_answer("not_applicable", ["withdrawn"], "outcome")[0] == "not_applicable"
    assert judge_runner.parse_answer("maybe", ["withdrawn"], "outcome")[2] is not None
    assert judge_runner.parse_answer('{"tier": "nope"}', ["urgent"], "tier")[2] is not None
