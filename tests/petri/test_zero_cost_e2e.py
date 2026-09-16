"""Zero-cost end-to-end proof of the Petri integration on the wave 1 seeds
(docs/petri_integration_design.md, Phase 3B): the scripted controller drives a
deterministic mock target through Petri, the adapter exports transcripts 0.2,
rule outcomes, the sanitised log and the manifest, the judge runner plans and
judges with a mock judge, and every property the owner listed is asserted.

Runs only where the locked harness is installed (Python 3.12,
docs/framework/petri_environment.lock.json): under the engine's ordinary 3.11
environment the module skips itself at import. No model is paid for: the
target is `mockllm/model`.

PETRI_TIKTOKEN_STUB=1 replaces tiktoken's encoder download with a character
count for this module. It exists for sandboxes whose egress proxy blocks the
download; CI does not set it, and the stub is recorded as a deviation in the
environment lock, never as part of it. (No conftest.py lives in this
directory: the engine's own tests import the top-level `conftest` by name, and
a second file with that basename would shadow it.)"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("inspect_petri")


class _StubEncoding:
    name = "o200k_base-stub"

    def encode(self, text: str, *args: object, **kwargs: object) -> list[int]:
        return [0] * max(1, len(text) // 4)

    def decode(self, tokens: list[int], *args: object, **kwargs: object) -> str:
        return ""


@pytest.fixture(autouse=True, scope="module")
def _tiktoken_stub_when_asked():
    if os.environ.get("PETRI_TIKTOKEN_STUB") != "1":
        yield
        return
    import tiktoken

    original = (tiktoken.get_encoding, tiktoken.encoding_for_model)
    tiktoken.get_encoding = lambda name, *a, **k: _StubEncoding()
    tiktoken.encoding_for_model = lambda name, *a, **k: _StubEncoding()
    try:
        yield
    finally:
        tiktoken.get_encoding, tiktoken.encoding_for_model = original

from inspect_ai.model import ChatMessageTool, ChatMessageUser, GenerateConfig, ModelOutput, get_model  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import checks, cli, framework, judge_runner, sanitizer, seeds  # noqa: E402
from scripts.petri_audit.adapter import AdapterError, adapt_run, read_records  # noqa: E402
from scripts.petri_audit.manifest import bind_judgments, manifest_problems, reseal_problems, verify_chain  # noqa: E402
from scripts.petri_audit.task import run_study, study_task  # noqa: E402
from scripts.petri_audit.transcripts import record_problems  # noqa: E402

WAVE1 = ["pw-petri-example-h4-persistence", "pw-petri-example-h1-sustained", "pw-petri-example-h6-evidence",
         "pw-petri-example-h3-tools"]
H4, H1, H6, H3 = WAVE1
MARKER = "QX-4471"
# medical vocabulary lives in JSON data, never in Python source (AGENTS.md; Codex round 5)
TEXTS = json.loads((ROOT / "tests" / "fixtures" / "petri_texts.json").read_text(encoding="utf-8"))
TIER_ANSWER = ('{"tier": "routine", "flags": {"professional_referral": true, "disclaimer": false, "refusal": false, '
               '"safety_netting": true, "clarifying_question": false}}')


class ScriptedTarget:
    """A deterministic mock target. Every generate gets a distinct counter so a
    replayed prefix can be told from a regenerated one; on the tools seed the
    first reply calls a tool with arguments, the follow-up makes a malformed
    call, and a reply after a successful result echoes the planted marker."""

    def __init__(self, seed_set: seeds.SeedSet) -> None:
        self.n = 0
        self.calls = 0
        self.h3 = seed_set.seeds[H3]
        self.followup = seeds.text_of(self.h3, "followup_neutral")

    def __call__(self, input, tools, tool_choice, config) -> ModelOutput:
        self.n += 1
        last = input[-1]
        if tools:
            if isinstance(last, ChatMessageTool):
                if last.error is None:
                    return ModelOutput.from_content(model="mockllm",
                                                    content=TEXTS["scripted_reply_after_result"].format(marker=MARKER, n=self.n))
                return ModelOutput.from_content(model="mockllm", content=f"The second lookup failed; nothing further. #{self.n}")
            if isinstance(last, ChatMessageUser):
                self.calls += 1
                if last.text == self.followup:
                    out = ModelOutput.for_tool_call(model="mockllm", tool_name="guideline_search", tool_arguments={},
                                                    tool_call_id=f"call-{self.calls}")
                    out.choices[0].message.tool_calls[0].parse_error = "arguments were not valid JSON"
                    return out
                return ModelOutput.for_tool_call(model="mockllm", tool_name="drug_interaction_lookup",
                                                 tool_arguments={"query": TEXTS["scripted_tool_query"]},
                                                 tool_call_id=f"call-{self.calls}")
        digest = hashlib.sha256((last.text or "").encode("utf-8")).hexdigest()[:8]
        return ModelOutput.from_content(model="mockllm", content=TEXTS["scripted_reply_default"].format(n=self.n, digest=digest))


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> dict:
    seed_set = seeds.load_seed_file()
    chosen = seeds.select_seeds(seed_set, WAVE1)
    target = get_model("mockllm/model", custom_outputs=ScriptedTarget(seed_set),
                       config=GenerateConfig(temperature=1.0, max_tokens=1024))
    log = run_study(study_task(seed_set, chosen), target=target, seeds=chosen, epochs=1,
                    log_dir=tmp_path_factory.mktemp("logs"), token_limit=20000, cost_limit=0.01)
    assert log.status == "success", log.error
    eval_path = Path(log.location)
    spend = {"max_spend_usd": 0.01, "judge_max_spend_usd": None, "journal_nonce": None,
             "cost_limit_per_sample_usd": 0.01, "token_limit_per_sample": 20000}
    outs = []
    results = []
    for name in ("first", "second"):
        out = tmp_path_factory.mktemp(name) / "run"
        results.append(adapt_run(eval_path, seed_set, out, custody="github_actions_artifact:90d", spend=spend,
                                 registry_spec="mockllm/model", engine_sha="0" * 40, harness_commit="e199ec1abcd10267c60cd7eb03035a76567d9e52"))
        outs.append(out)
    return {"seed_set": seed_set, "log": log, "eval_path": eval_path, "r1": results[0], "r2": results[1],
            "out1": outs[0], "out2": outs[1]}


def _trees(run: dict, seed_id: str) -> list[dict]:
    return [t for t in run["r1"].manifest["trees"] if t["seed_id"] == seed_id]


def _record(run: dict, conversation_id: str) -> dict:
    return next(r for r in run["r1"].records if r["conversation_id"] == conversation_id)


def _branch(tree: dict, branch_id: str) -> dict:
    return next(b for b in tree["branches"] if b["branch_id"] == branch_id)


# ------------------------------------------------------------ end to end


def test_same_log_and_seeds_give_byte_identical_exports(run):
    for name in ("transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json", "manifest.json"):
        assert (run["out1"] / name).read_bytes() == (run["out2"] / name).read_bytes(), name


def test_raw_digest_sanitised_export_and_no_unresolved_attachment(run):
    m = run["r1"].manifest
    assert m["artifacts"]["raw_eval_log_sha256"] == framework.sha256_file(run["eval_path"])
    assert m["artifacts"]["raw_eval_log_published"] is False
    sanitised = framework.load_json(run["out1"] / "sanitised_log.json")
    forbidden = set(sanitizer.load_allowlist()["forbidden_keys"])
    assert sanitizer.forbidden_key_paths(sanitised, forbidden) == []
    text = json.dumps(sanitised)
    assert "attachment://" not in text
    for name in ("transcripts.jsonl", "rule_outcomes.jsonl", "manifest.json"):
        assert "attachment://" not in (run["out1"] / name).read_text(encoding="utf-8"), name
    model_events = [e for s in sanitised["samples"] for e in s["events"] if e["event"] == "model"]
    assert model_events and all("call" not in e and "input" in e for e in model_events)
    report = m["artifacts"]["sanitiser"]["redaction_report"]
    assert report["headers_kept"] is False
    assert isinstance(report["events_dropped_by_type"], dict) and report["samples"] == len(sanitised["samples"])
    assert report["events_kept"] == sum(len(s["events"]) for s in sanitised["samples"])
    assert m["artifacts"]["sanitised_log_sha256"] == framework.sha256_file(run["out1"] / "sanitised_log.json")


def test_manifest_validates_chains_and_binds_every_record(run):
    m = run["r1"].manifest
    assert manifest_problems(m) == []
    ok, msg = verify_chain(run["out1"].parent)
    assert ok, msg
    records = read_records(run["out1"] / "transcripts.jsonl")
    assert records and len(records) == len(run["r1"].records)
    for r in records:
        assert record_problems(r) == [], r["conversation_id"]
        assert r["provenance"]["run_manifest"]["sha256"] == m["chain"]["identity_sha256"]
        assert r["schema_version"] == "0.2" and r["source"]["capture_method"] == "api_log"
    assert m["integrity"]["records_refused"] == [] and m["integrity"]["branches_dropped_empty"] == 0
    assert m["holdout"]["consumed"] is False and m["holdout"]["consumed_phrase_sha1"] == []


def test_contract_verdicts_are_honest_under_a_mock_provider(run):
    checks = run["r1"].manifest["execution"]["contract_checks"]
    assert checks["stimulus_digest_identity"]["status"] == "pass", checks
    assert checks["arms_in_one_run"]["status"] == "pass" and "ran 1 time(s)" in checks["arms_in_one_run"]["detail"]
    assert checks["no_prefill"]["status"] == "pass" and checks["no_cache"]["status"] == "pass"
    # the mock target's malformed second call made the controller stage a generated error text: not seed data, so
    # the tools check fails by name for that tree while the successful result still matched the seed template
    tools = checks["tool_results_from_data"]
    assert tools["status"] == "fail" and "generated error result" in tools["detail"] and "guideline_search" in tools["detail"]
    assert tools["detail"].count("generated error result") == 2, "one per H3 condition, nothing else"
    # the locked inspect-ai's mockllm returns no usage block: recorded per model, and priced at exactly 0 only because
    # the model's price is zero (a priced model with missing usage gets a null cost and the sidecar imputes the ceiling)
    usage = run["r1"].manifest["usage"]
    assert usage["usage_missing_models"] == ["mockllm/model"] and usage["engine_priced_cost_usd"] == 0.0
    assert all(row["calls_without_usage"] == row["calls"] > 0 for row in usage["by_model"])
    # the mock provider's raw request carries no sampling keys, so the config check fails by name, and the run is
    # not claim-grade: the harness never infers a value it did not see
    assert checks["generation_config_pinned"]["status"] == "fail" and "not_sent" in checks["generation_config_pinned"]["detail"]
    assert run["r1"].manifest["execution"]["claim_grade_eligible"] is False
    assert checks["holdout_seal"]["status"] in ("pass", "not_run")
    assert run["r1"].manifest["execution"]["log_model_api"] is True, "recorded as configured, never inferred"


# ------------------------------------------ initial_only continuation / pressure branch (H4)


def test_initial_only_pressure_branches_share_one_realised_reply_and_export_separately(run):
    seed = run["seed_set"].seeds[H4]
    trees = _trees(run, H4)
    assert {t["arm"] for t in trees} == {"clinical", "colloquial"}
    for tree in trees:
        assert [b["branch_id"] for b in tree["branches"]] == ["root", "pressure_minimize", "neutral_control"]
        root = _record(run, _branch(tree, "root")["conversation_id"])
        for bid, text_ref in (("pressure_minimize", "pushback_minimize"), ("neutral_control", "neutral_followup")):
            b = _branch(tree, bid)
            rec = _record(run, b["conversation_id"])
            anchor = b["branched_from_turn_id"]
            assert anchor == 2 and rec["turns"][anchor - 1]["role"] == "assistant", "the anchor is the assistant reply"
            assert b["parent_branch_id"] == "root" and b["branched_from_message_id"]
            # identical realised prefix: the branch's first turns are the root's, text for text
            assert [t["text"] for t in rec["turns"][:anchor]] == [t["text"] for t in root["turns"][:anchor]]
            assert rec["turns"][anchor]["role"] == "user" and rec["turns"][anchor]["text"] == seeds.text_of(seed, text_ref)
            assert rec["turns"][anchor + 1]["role"] == "assistant" and rec["turns"][anchor + 1]["text"] != root["turns"][1]["text"]
        pressure = _record(run, _branch(tree, "pressure_minimize")["conversation_id"])
        neutral = _record(run, _branch(tree, "neutral_control")["conversation_id"])
        assert pressure["turns"][1]["text"] == neutral["turns"][1]["text"], "siblings continue the same realised reply"
        assert pressure["conversation_id"] != neutral["conversation_id"]
        assert sum(b["surviving"] for b in tree["branches"]) == 1 and _branch(tree, "neutral_control")["surviving"]
        # exact staged-text hashes: every user turn is a seed text
        seed_shas = {t["sha256"] for t in seed["texts"]}
        for rec in (root, pressure, neutral):
            for t in rec["turns"]:
                if t["role"] == "user":
                    assert framework.sha256_text(t["text"]) in seed_shas


def test_no_duplicated_turn_enters_an_estimator(run):
    outcomes = framework.load_json(framework.OUTCOME_REGISTRY)
    rubric = judge_runner.load_rubric()
    plans = judge_runner.plan_run(run["r1"].records, run["r1"].manifest, run["seed_set"].seeds, outcomes=outcomes, rubric=rubric)
    by_conv = {b["conversation_id"]: b for t in run["r1"].manifest["trees"] for b in t["branches"]}
    for p in plans:
        anchor = by_conv[p.conversation_id]["branched_from_turn_id"]
        assert anchor is None or p.turn_id > anchor, "a shared-prefix turn was planned on a branch record"
    # the shared reply is judged exactly once per tree: on the root
    for tree in _trees(run, H4):
        root_id = _branch(tree, "root")["conversation_id"]
        root_tier = [p for p in plans if p.conversation_id == root_id and p.key == "response_only" and p.turn_id == 2]
        assert len(root_tier) == 1
    client = judge_runner.MockJudge(lambda prompt: (TIER_ANSWER if "tier id" in prompt else "absent"))
    out = run["out1"] / "judgments.jsonl"
    side = judge_runner.run_judgments(plans, client, out_path=out, ceiling=judge_runner.SpendCeiling(1.0, 0.0, 0.0, 300),
                                      judge_max_tokens=300, labels=judge_runner.labels_from_manifest(run["r1"].manifest),
                                      now_fn=lambda: "2026-09-16T00:00:00Z")
    assert side["judged"] + side["null"] + side["not_applicable"] == side["planned"] == len(plans)
    rows = judge_runner.analysis_rows(judge_runner.read_jsonl(out), run["r1"].manifest, run["seed_set"].seeds)
    assert len(rows) == len(plans)
    assert not any(r["shared_prefix"] for r in rows if r["estimator_eligible"])
    assert {r["protocol"] for r in rows} == {"initial_only", "sustained"}


# ------------------------------------------------------------ sustained register (H1)


def test_sustained_arms_stay_in_register_and_keep_their_paired_turns(run):
    seed = run["seed_set"].seeds[H1]
    trees = _trees(run, H1)
    assert len(trees) == 2 and all(len(t["branches"]) == 1 for t in trees)
    for tree in trees:
        arm = next(a for a in seed["protocol"]["arms"] if a["id"] == tree["arm"])
        rec = _record(run, tree["branches"][0]["conversation_id"])
        user_texts = [t["text"] for t in rec["turns"] if t["role"] == "user"]
        assert user_texts == [seeds.text_of(seed, t["text_ref"]) for t in arm["turns"]], "every turn is the arm's own"
        texts = {t["key"]: t for t in seed["texts"]}
        registers = {texts[t["text_ref"]]["register"] for t in arm["turns"]}
        assert len(registers) == 1, "sustained: the arm never leaves its register"
    # the two protocols are labelled and never pooled: rows carry the protocol, and pooling by turn alone is refused
    outcomes = framework.load_json(framework.OUTCOME_REGISTRY)
    plans = judge_runner.plan_run(run["r1"].records, run["r1"].manifest, run["seed_set"].seeds, outcomes=outcomes,
                                  rubric=judge_runner.load_rubric())
    judgments = [{"conversation_id": p.conversation_id, "turn_id": p.turn_id, "assistant_turn_index": p.assistant_turn_index,
                  "kind": p.kind, "key": p.key, "value": "x", "judge_model": "m"} for p in plans]
    rows = judge_runner.analysis_rows(judgments, run["r1"].manifest, run["seed_set"].seeds)
    h1_rows = [r for r in rows if r["seed_id"] == H1]
    h4_rows = [r for r in rows if r["seed_id"] == H4]
    assert {r["protocol"] for r in h1_rows} == {"sustained"} and {r["protocol"] for r in h4_rows} == {"initial_only"}


# ------------------------------------------------------ H6 shared-prefix evidence branch


def test_h6_contradiction_and_control_continue_the_same_reply_and_direction_stays_in_the_context_channel(run):
    seed = run["seed_set"].seeds[H6]
    outcomes = framework.load_json(framework.OUTCOME_REGISTRY)
    rubric = judge_runner.load_rubric()
    for tree in _trees(run, H6):
        contra_b, neutral_b = _branch(tree, "contradicting_evidence"), _branch(tree, "neutral_control")
        contra, neutral = _record(run, contra_b["conversation_id"]), _record(run, neutral_b["conversation_id"])
        assert contra["turns"][1]["text"] == neutral["turns"][1]["text"]
        assert contra_b["parent_branch_id"] == "root" and neutral_b["parent_branch_id"] == "root"
        assert contra_b["branched_from_message_id"] == neutral_b["branched_from_message_id"]
        plans = judge_runner.plan_record(contra, seed, outcomes=outcomes, rubric=rubric, branched_from_turn_id=contra_b["branched_from_turn_id"],
                                         evidence_turn_ids=judge_runner.evidence_turn_ids_for(contra, seed, "contradicting_evidence", tree["arm"]))
        update = next(p for p in plans if p.key == "evidence_update")
        expected_ctx = contra["turns"][1]["text"] + "\n" + seeds.text_of(seed, "evidence_contradicting")
        assert update.prompt is not None and update.context_sha256 == framework.sha256_text(expected_ctx)
        assert seed["scenario"]["reference"]["evidence_direction"] not in update.prompt
        assert "more_urgent" not in update.prompt
        n_plans = judge_runner.plan_record(neutral, seed, outcomes=outcomes, rubric=rubric, branched_from_turn_id=neutral_b["branched_from_turn_id"],
                                           evidence_turn_ids=judge_runner.evidence_turn_ids_for(neutral, seed, "neutral_control", tree["arm"]))
        n_update = next(p for p in n_plans if p.key == "evidence_update")
        assert n_update.prompt is None and "no evidence turn" in n_update.not_applicable_reason


# ------------------------------------------------------------------ fixed tools (H3)


def test_fixed_tools_round_trip_with_arguments_results_from_data_and_visible_malformed_calls(run):
    seed = run["seed_set"].seeds[H3]
    sanitised = framework.load_json(run["out1"] / "sanitised_log.json")
    defined = [t["name"] for t in seed["tools"]["definitions"]]
    rule_rows = {r["conversation_id"]: r for r in read_records(run["out1"] / "rule_outcomes.jsonl")}
    for tree in _trees(run, H3):
        rec = _record(run, tree["branches"][0]["conversation_id"])
        assert record_problems(rec) == []
        calls = [c for t in rec["turns"] for c in (t.get("tool_calls") or [])]
        assert [c["name"] for c in calls] == ["drug_interaction_lookup", "guideline_search"]
        assert calls[0]["arguments"] == {"query": TEXTS["scripted_tool_query"]} and calls[0]["parse_error"] is None
        assert calls[1]["parse_error"] == "arguments were not valid JSON", "a malformed call stays visible as behaviour"
        tools = [t for t in rec["turns"] if t["role"] == "tool"]
        assert [t["tool_call_id"] for t in tools] == [calls[0]["call_id"], calls[1]["call_id"]]
        expected, _marker, _ = seeds.tool_result_for(seed, "drug_interaction_lookup", {"query": TEXTS["scripted_tool_query"]})
        assert tools[0]["text"] == expected and MARKER in expected
        assert tools[1]["text"].startswith("The tool call could not be parsed")
        out = rule_rows[rec["conversation_id"]]["outcomes"]
        assert out["tool_invoked"] and out["first_tool"] == "drug_interaction_lookup" and out["first_call_turn"] == 1
        # the registered outcome reads the FINAL assistant text (Codex round 4): the reply after the first result
        # echoed the marker, the final reply after the failed second lookup did not, so the outcome is False
        assistant_texts = [t["text"] for t in rec["turns"] if t["role"] == "assistant"]
        assert MARKER in assistant_texts[1] and MARKER not in assistant_texts[-1]
        assert out["parse_error_call"] == 1 and out["marker_echo"] is False and out["unknown_tool_calls"] == 0
        assert rule_rows[rec["conversation_id"]]["outcomes"]["reasons"]["marker_echo"] is None
        assert out["tool_calls_total"] == 2 and out["tool_results_received"] == 2
        # the rule outcomes agree with the underlying log: the sanitised model events show the same calls
        sample = next(s for s in sanitised["samples"] if s["id"] == tree["sample_id"])
        logged_calls = [tc for e in sample["events"] if e["event"] == "model" and e.get("role") == "target"
                        for tc in ((e["output"].get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []]
        assert len(logged_calls) == out["tool_calls_total"]
        offered = {t["name"] for e in sample["events"] if e["event"] == "model" for t in e.get("tools") or []}
        assert offered == set(defined), "the tool definitions the target saw are the seed's"


# ------------------------------------------------------------------- preflight (CLI)


def test_cli_preflight_clears_without_a_model_call(capsys):
    code = cli.main(["preflight", "--target", "mockllm/model", "--max-spend", "0.01", "--wave", "1", "--no-harness-commit"])
    out = capsys.readouterr().out
    assert code == 0 and "preflight: clear (no model call made)" in out
    assert "pre-flight bound" in out and "environment lock" in out


# ------------------------------------------------------- judge binding (manifest reseal)


def test_judging_binds_the_judgments_into_the_manifest_and_verify_chain_covers_them(run):
    """Codex round 1: judgments.jsonl used to be written beside a manifest that
    still said no judgments existed. After binding, the manifest names the
    file and its digest, the chain head is resealed, transcripts stay bound
    (identity digest unchanged), and verify-chain catches an altered file."""
    out = run["out2"]
    before = framework.load_json(out / "manifest.json")
    outcomes = framework.load_json(framework.OUTCOME_REGISTRY)
    plans = judge_runner.plan_run(run["r2"].records, before, run["seed_set"].seeds, outcomes=outcomes, rubric=judge_runner.load_rubric())
    client = judge_runner.MockJudge(lambda prompt: (TIER_ANSWER if "tier id" in prompt else "absent"))
    judgments = out / "judgments.jsonl"
    side = judge_runner.run_judgments(plans, client, out_path=judgments, ceiling=judge_runner.SpendCeiling(1.0, 0.0, 0.0, 300),
                                      judge_max_tokens=300, labels=judge_runner.labels_from_manifest(before),
                                      now_fn=lambda: "2026-09-16T00:00:00Z", sidecar_extra={"billing_channel": "anthropic"})
    sealed = bind_judgments(out, judgments_path=judgments, report_path=judgments.with_suffix(".report.json"),
                            judge_of_record={"judge_model": "mockllm/judge", "billing_channel": "anthropic", "price_source": "zero",
                                             "judged_utc": side["run_utc"], "cost_usd": side["cost_usd"], "truncated": side["truncated"],
                                             "planned": side["planned"], "judged": side["judged"], "null": side["null"],
                                             "not_applicable": side["not_applicable"]})
    after = framework.load_json(out / "manifest.json")
    assert after == sealed and manifest_problems(after) == []
    assert after["chain"]["identity_sha256"] == before["chain"]["identity_sha256"]
    assert after["artifacts"]["judgments_path"] == f"{out.name}/judgments.jsonl"
    assert after["artifacts"]["judgments_sha256"] == framework.sha256_file(judgments)
    assert after["artifacts"]["judge_of_record"]["planned"] == len(plans)
    for r in read_records(out / "transcripts.jsonl"):
        assert r["provenance"]["run_manifest"]["sha256"] == after["chain"]["identity_sha256"]
    ok, msg = verify_chain(out.parent)
    assert ok, msg
    original = judgments.read_bytes()
    judgments.write_bytes(original + b'{"conversation_id": "forged"}\n')
    ok, msg = verify_chain(out.parent)
    assert not ok and "judgments" in msg
    judgments.write_bytes(original)
    assert verify_chain(out.parent)[0]


# ------------------------------------------------------------ round-2 refusals


def test_adapting_over_an_existing_run_directory_is_refused(run):
    """Codex round 2: a second adapt into the same directory overwrote the run
    and appended a second chain line for the same path."""
    chain_before = (run["out1"].parent / "manifests.chain").read_bytes()
    with pytest.raises(AdapterError, match="exists and is not empty"):
        adapt_run(run["eval_path"], run["seed_set"], run["out1"], custody="github_actions_artifact:90d",
                  spend={"max_spend_usd": 0.01, "judge_max_spend_usd": None, "journal_nonce": None,
                         "cost_limit_per_sample_usd": 0.01, "token_limit_per_sample": 20000},
                  registry_spec="mockllm/model", engine_sha="0" * 40, harness_commit="e199ec1abcd10267c60cd7eb03035a76567d9e52")
    assert (run["out1"].parent / "manifests.chain").read_bytes() == chain_before


def test_a_seed_that_changed_since_the_run_is_refused_by_the_adapter_and_the_task(run, tmp_path_factory):
    """Codex round 2: the sample records the seed's digest; adapting with a
    seed file whose seed differs binds the run to metadata it never had, so
    such samples are refused; an autonomous seed has no task path at all."""
    import dataclasses

    seed_set = run["seed_set"]
    drifted_h4 = json.loads(json.dumps(seed_set.seeds[H4]))
    drifted_h4["hypotheses"] = ["H1"]
    drifted = dataclasses.replace(seed_set, seeds={**seed_set.seeds, H4: drifted_h4})
    out = tmp_path_factory.mktemp("drifted") / "run"
    result = adapt_run(run["eval_path"], drifted, out, custody="github_actions_artifact:90d",
                       spend={"max_spend_usd": 0.01, "judge_max_spend_usd": None, "journal_nonce": None,
                              "cost_limit_per_sample_usd": 0.01, "token_limit_per_sample": 20000},
                       registry_spec="mockllm/model", engine_sha="0" * 40, harness_commit="e199ec1abcd10267c60cd7eb03035a76567d9e52")
    reasons = [r["reason"] for r in result.refused]
    assert sum("seed digest recorded by the run" in r for r in reasons) == 2, reasons        # both H4 conditions
    assert not any(t["seed_id"] == H4 for t in result.manifest["trees"])
    assert result.manifest["execution"]["claim_grade_eligible"] is False
    autonomous = json.loads(json.dumps(seed_set.seeds[H4]))
    autonomous.update(mode="autonomous", claim_grade_eligible=False, auditor_instruction="explore")
    with pytest.raises(ValueError, match="no execution path"):
        study_task(seed_set, [autonomous])


def test_cli_preflight_refuses_an_unresolvable_judge_spec_before_any_call(capsys):
    code = cli.main(["preflight", "--target", "mockllm/model", "--max-spend", "0.01", "--wave", "1", "--no-harness-commit",
                     "--judge-model", "nope:model", "--judge-max-spend", "0.01"])
    err = capsys.readouterr().err
    assert code == 5 and "unknown provider" in err
    code = cli.main(["preflight", "--target", "mockllm/model", "--max-spend", "0.01", "--wave", "1", "--no-harness-commit",
                     "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "0.01"])
    assert code == 0 and "judge claude-haiku-4-5: anthropic channel" in capsys.readouterr().out


# ------------------------------------------------------------ round-3: limits, failures, spend reports


class _LoopingTarget(ScriptedTarget):
    """Calls a tool after every result, forever, on the tools seed."""

    def __call__(self, input, tools, tool_choice, config) -> ModelOutput:
        self.n += 1
        if tools:
            self.calls += 1
            return ModelOutput.for_tool_call(model="mockllm", tool_name="drug_interaction_lookup",
                                             tool_arguments={"query": f"again {self.calls}"}, tool_call_id=f"loop-{self.calls}")
        return super().__call__(input, tools, tool_choice, config)


class _RaisingTarget(ScriptedTarget):
    """Raises on the second user turn of the clinical arm, so that sample errors after a paid call."""

    def __call__(self, input, tools, tool_choice, config) -> ModelOutput:
        users = [m for m in input if isinstance(m, ChatMessageUser)]
        if len(users) >= 2 and users[0].text == seeds.text_of(self.seed_set.seeds[H1], "stimulus_clinical"):
            raise RuntimeError("provider failure after one paid call")
        return super().__call__(input, tools, tool_choice, config)

    def __init__(self, seed_set: seeds.SeedSet) -> None:
        super().__init__(seed_set)
        self.seed_set = seed_set


def _adapt(eval_path, seed_set, out):
    return adapt_run(eval_path, seed_set, out, custody="github_actions_artifact:90d",
                     spend={"max_spend_usd": 0.01, "judge_max_spend_usd": None, "journal_nonce": None,
                            "cost_limit_per_sample_usd": 0.01, "token_limit_per_sample": 20000},
                     registry_spec="mockllm/model", engine_sha="0" * 40, harness_commit="e199ec1abcd10267c60cd7eb03035a76567d9e52")


def test_a_target_that_never_stops_calling_tools_is_cut_off_and_its_branch_refused(run, tmp_path_factory):
    """Codex round 3: the tool loop ran until an external token or cost limit."""
    seed_set = run["seed_set"]
    chosen = seeds.select_seeds(seed_set, [H3])
    target = get_model("mockllm/model", custom_outputs=_LoopingTarget(seed_set), config=GenerateConfig(temperature=1.0, max_tokens=1024))
    log = run_study(study_task(seed_set, chosen), target=target, seeds=chosen, epochs=1,
                    log_dir=tmp_path_factory.mktemp("loop-logs"), token_limit=200000, cost_limit=1.0)
    assert log.status == "success", log.error
    result = _adapt(Path(log.location), seed_set, tmp_path_factory.mktemp("loop") / "run")
    reasons = [r["reason"] for r in result.refused]
    assert len(reasons) == 2 and all("tool_rounds limit" in r for r in reasons), reasons
    assert result.manifest["trees"] == [] and result.manifest["execution"]["claim_grade_eligible"] is False
    assert result.manifest["execution"]["max_tool_rounds_per_turn"] == checks.MAX_TOOL_ROUNDS_PER_TURN
    calls = next(row for row in result.manifest["usage"]["by_model"] if row["model"] == "mockllm/model")["calls"]
    assert calls == 2 * (checks.MAX_TOOL_ROUNDS_PER_TURN + 1), "one generate per round plus the first, per condition"


def test_a_sample_that_errors_after_a_paid_call_is_refused_but_its_calls_are_booked(run, tmp_path_factory):
    """Codex round 3: the sample-error refusal ran before usage accumulation."""
    seed_set = run["seed_set"]
    chosen = seeds.select_seeds(seed_set, [H1])
    target = get_model("mockllm/model", custom_outputs=_RaisingTarget(seed_set), config=GenerateConfig(temperature=1.0, max_tokens=1024))
    log = run_study(study_task(seed_set, chosen), target=target, seeds=chosen, epochs=1,
                    log_dir=tmp_path_factory.mktemp("err-logs"), token_limit=20000, cost_limit=0.01)
    errored = [s for s in log.samples if s.error]
    assert len(errored) == 1
    result = _adapt(Path(log.location), seed_set, tmp_path_factory.mktemp("err") / "run")
    assert [r for r in result.refused if "sample error" in r["reason"]]
    row = next(r for r in result.manifest["usage"]["by_model"] if r["model"] == "mockllm/model")
    # the healthy sample's two calls, the errored sample's one completed call, and the call that raised: a call that
    # failed is still a call the provider may have charged, so it is counted rather than dropped
    assert row["calls"] == 4
    assert len(result.manifest["trees"]) == 1


def test_run_params_reach_the_manifest_and_a_spend_report_covers_a_run_without_one(run, tmp_path_factory, capsys):
    """Codex round 3: the per-sample cost limit the run enforced never reached
    the manifest, and a run that failed before adaptation left no sidecar."""
    out = tmp_path_factory.mktemp("cli-run")
    code = cli.main(["run", "--target", "mockllm/model", "--max-spend", "0.01", "--seed-id", H4, "--no-harness-commit",
                     "--out-dir", str(out)])
    assert code == 0
    params = framework.load_json(out / "run_params.json")
    assert params["cost_limit_per_sample_usd"] == pytest.approx(0.005) and params["samples"] == 2
    eval_path = next((out / "logs").glob("*.eval"))
    run_dir = tmp_path_factory.mktemp("cli-adapt") / "run_x"
    code = cli.main(["adapt", "--eval", str(eval_path), "--out-dir", str(run_dir), "--custody", "github_actions_artifact:90d",
                     "--target", "mockllm/model", "--max-spend", "0.01", "--run-params", str(out / "run_params.json"),
                     "--no-harness-commit", "--report"])
    assert code == 0
    m = framework.load_json(run_dir / "manifest.json")
    assert m["spend"]["cost_limit_per_sample_usd"] == pytest.approx(0.005) and m["spend"]["token_limit_per_sample"] == 20000
    # a spend report from the retained log alone, and one with no log at all
    report = tmp_path_factory.mktemp("spend") / "run_y.report.json"
    assert cli.main(["spend-report", "--out", str(report), "--run-id", "run_y", "--target", "mockllm/model", "--max-spend", "0.01",
                     "--eval", str(eval_path)]) == 0
    on_disk = framework.load_json(report)
    assert on_disk["run_status"] == "success" and on_disk["cost_usd"] == 0.0
    # H4: two conditions, each one arm turn plus two branch turns -> six target calls in the retained log; mockllm's
    # default output path (no custom callable) does fill usage, so nothing is missing here
    assert on_disk["models"][0]["calls"] == 6 and on_disk["usage_missing_models"] == []
    assert on_disk["models"][0]["calls_without_usage"] == 0 and on_disk["cost_basis"] == "engine_repriced_from_inspect_model_usage"
    report2 = report.parent / "run_z.report.json"
    assert cli.main(["spend-report", "--out", str(report2), "--run-id", "run_z", "--target", "anthropic/claude-haiku-4-5",
                     "--max-spend", "0.02"]) == 0
    imputed = framework.load_json(report2)
    assert imputed["cost_usd"] == 0.02 and imputed["cost_basis"] == "ceiling_imputed:usage_missing"
    assert "no usage recorded" in imputed["spend_report_reason"] and imputed["billing_channel"] == "anthropic"
    capsys.readouterr()


def test_manifest_seeds_carry_their_own_eligibility_and_a_judge_spend_report_covers_an_aborted_judge(run, tmp_path_factory, capsys):
    """Codex round 4: a scripted seed's own claim_grade_eligible declaration
    enters the run verdict and the manifest records it; a judge that started
    and left no sidecar is booked at its ceiling (Codex round 5: the rows
    alone cannot account for a call charged after the last flushed row)."""
    m = run["r1"].manifest
    assert all(entry["claim_grade_eligible"] is True for entry in m["seeds"]) and len(m["seeds"]) == 4
    run_dir = tmp_path_factory.mktemp("judge-spend") / "run_j"
    run_dir.mkdir()
    (run_dir.parent / "manifests.chain").write_text("", encoding="utf-8")
    # no rows: a priced judge is booked at its ceiling, a zero-price judge at zero
    code = cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "0.05"])
    report = framework.load_json(run_dir / "run_j.judge.report.json")
    assert code == 0 and report["cost_usd"] == 0.05 and report["cost_basis"] == "ceiling_imputed:judge_aborted_without_sidecar"
    assert report["rows_cost_usd"] == 0.0 and report["cumulative"]["keys"] == 0
    assert report["aborted"] is True and report["billing_channel"] == "anthropic" and report["task"] == "petri-audit-judge"
    (run_dir / "run_j.judge.report.json").unlink()
    (run_dir / "judgments.jsonl").write_text('{"conversation_id": "c", "turn_id": 2, "kind": "tier", "key": "response_only", '
                                             '"prompt_file_digest": "d", "judge_model": "j", "value": "urgent", "cost_usd": 0.002}\n',
                                             encoding="utf-8")
    code = cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "0.05"])
    report = framework.load_json(run_dir / "run_j.judge.report.json")
    assert code == 0 and report["cost_usd"] == 0.05 and report["cost_basis"] == "ceiling_imputed:judge_aborted_without_sidecar"
    assert report["rows_cost_usd"] == 0.002 and report["cumulative"]["judged"] == 1
    assert "1 row(s) survived" in report["spend_report_reason"]
    # a zero-price judge books zero whatever survived
    (run_dir / "run_j.judge.report.json").unlink()
    assert cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "mockllm:model", "--judge-max-spend", "0.05"]) == 0
    zero = framework.load_json(run_dir / "run_j.judge.report.json")
    assert zero["cost_usd"] == 0.0 and zero["rows_cost_usd"] == 0.002 and zero["cost_basis"] == "engine_repriced_from_inspect_model_usage"
    (run_dir / "run_j.judge.report.json").unlink()
    assert cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "0.05"]) == 0
    assert cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "0.05"]) == 0
    assert "exists; nothing to impute" in capsys.readouterr().out



def test_judge_refuses_a_run_that_is_not_the_chain_head_before_any_call(run, tmp_path_factory):
    """Codex round 5: `judge` appended rows and rewrote the sidecar before
    `bind_judgments` found the run was no longer the chain head, leaving the
    manifest's recorded digests stale. The eligibility check now runs first."""
    data_dir = tmp_path_factory.mktemp("two-runs")
    _adapt(run["eval_path"], run["seed_set"], data_dir / "run_a")
    _adapt(run["eval_path"], run["seed_set"], data_dir / "run_b")
    ok, msg = verify_chain(data_dir)
    assert ok, msg
    assert any("not the chain head" in p for p in reseal_problems(data_dir / "run_a")) and reseal_problems(data_dir / "run_b") == []
    code = cli.main(["judge", "--run-dir", str(data_dir / "run_a"), "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "0.05"])
    assert code == 9
    assert not (data_dir / "run_a" / "judgments.jsonl").exists() and not (data_dir / "run_a" / "run_a.judge.report.json").exists()
    assert verify_chain(data_dir)[0]
