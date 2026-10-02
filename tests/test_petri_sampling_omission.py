"""Sampling parameters the Petri lane withholds (registry revision of 2026-10-01).

The Claude models that reject temperature (Opus 4.7 and later, Fable 5 and 5.1, Sonnet 5 and 5.5: the registry's
anthropic `omit_temperature` map, from the claude-api skill). The lane must leave it out of the target's and the auditor's GenerateConfig, the adapter must
then require it ABSENT from every raw request and record it in the manifest, and the judge must send none and record
that on every row and in its sidecar. Offline and Inspect-free: the GenerateConfig arguments are built by a pure
function (checks.generate_config_kwargs) that task.py and controller.py call; the judge's provider calls are fakes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import checks, cli, envlock, framework, judge_runner, rejudge, spend  # noqa: E402
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402

SEED_GENERATION = {"max_tokens": 1024, "temperature": 1.0, "seed_requested": 7}
OMITTED = {"temperature": "rejects temperature (test)"}


@pytest.mark.parametrize("name", ["anthropic/claude-opus-5-5", "openrouter/anthropic/claude-opus-5.5",
                                  "anthropic/claude-fable-5-1", "anthropic/claude-sonnet-5-5",
                                  "openrouter/anthropic/claude-sonnet-5.5", "claude-opus-5-5",
                                  "openrouter:anthropic/claude-opus-5.5",
                                  # the models Inspect's anthropic provider already drops it for (4.7 or later), so the
                                  # manifest records what Inspect did (review of 2026-10-01)
                                  "anthropic/claude-sonnet-5", "anthropic/claude-opus-4-8", "anthropic/claude-opus-4-7",
                                  "anthropic/claude-opus-5", "anthropic/claude-fable-5",
                                  "openrouter/anthropic/claude-sonnet-5"])
def test_the_new_anthropic_models_have_temperature_withheld_in_every_spelling(name):
    assert set(spend.sampling_omissions(name)) == {"temperature"}


@pytest.mark.parametrize("name", ["anthropic/claude-haiku-4-5", "openrouter/anthropic/claude-haiku-4.5",
                                  "anthropic/claude-sonnet-4-6", "openrouter/openai/gpt-5.4-mini", "mockllm/model",
                                  "mockllm/judge", "none/none", ""])
def test_every_other_model_keeps_its_sampling_settings(name):
    assert spend.sampling_omissions(name) == {}


def test_the_petri_rule_is_the_advice_lanes_rule():
    """One implementation: spend.sampling_omissions reads the registry passed in through advice_eval's matcher."""
    registry = {"anthropic": {"omit_temperature": {"model-r": "why"}}}
    assert spend.sampling_omissions("anthropic/model-r", registry) == {"temperature": "why"}
    assert spend.sampling_omissions("anthropic/model-x", registry) == {}
    with pytest.raises(ValueError, match="omit_temperature"):
        spend.sampling_omissions("anthropic/model-r", {"anthropic": {"omit_temperature": ["model-r"]}})


def _live_omissions() -> dict[str, str]:
    return framework.load_json(spend.PROVIDERS_PATH)["anthropic"]["omit_temperature"]


@pytest.mark.parametrize("key", sorted(_live_omissions()))
def test_every_listed_model_takes_its_own_entrys_reason_in_every_spelling_the_lane_uses(key):
    """Review of 2026-10-02: the Inspect name of a direct-API model was matched as written, and
    `anthropic/claude-sonnet-5` is also claude-sonnet-5's OpenRouter slug, so the pre-flight printout and the
    manifest's sampling_omitted gave that entry's reason, "(OpenRouter spelling of claude-sonnet-5)". Fable 5 and
    Opus 5 were the other two. A direct id is named `anthropic/<id>` by a target or auditor and `anthropic:<id>` or
    `<id>` by a judge; a slug is named `openrouter/<slug>` and `openrouter:<slug>`. A judge's records resolve its
    spec as the judge does (judge_runner.judge_sampling_omissions)."""
    reason = _live_omissions()[key]
    direct = [f"anthropic/{key}", f"anthropic:{key}", key]
    for spelling in ([f"openrouter/{key}", f"openrouter:{key}"] if "/" in key else direct):
        assert spend.sampling_omissions(spelling) == {"temperature": reason}, spelling
    for spelling in ([f"openrouter:{key}"] if "/" in key else [f"anthropic:{key}", key]):
        assert judge_runner.judge_sampling_omissions(spelling) == {"temperature": reason}, spelling


def test_an_inspect_name_is_matched_as_its_registry_spec():
    """The direct id `m` and the OpenRouter slug `anthropic/m` are two entries. The advice lane passes the slug as
    the part after `openrouter:` and must keep matching it as written; the Petri lane's `anthropic/m` is the direct
    API, so spend.sampling_omissions matches it as `anthropic:m`."""
    registry = {"anthropic": {"omit_temperature": {"m": "direct", "anthropic/m": "slug", "anthropic/n.1": "slug only"}},
                "openrouter": {}}
    assert spend.sampling_omissions("anthropic/m", registry) == {"temperature": "direct"}
    assert spend.sampling_omissions("openrouter/anthropic/m", registry) == {"temperature": "slug"}
    # names with a colon, and bare ids, matched as written (a judge's spec is resolved as the judge resolves it, by
    # judge_runner.judge_sampling_omissions, not here)
    assert spend.sampling_omissions("anthropic:m", registry) == {"temperature": "direct"}
    assert spend.sampling_omissions("m", registry) == {"temperature": "direct"}
    assert spend.sampling_omissions("openrouter:anthropic/m", registry) == {"temperature": "slug"}
    # a direct-API name takes only a direct entry, as its registry spec `anthropic:n.1` does
    assert spend.sampling_omissions("anthropic/n.1", registry) == {}
    assert spend.sampling_omissions("openrouter/anthropic/n.1", registry) == {"temperature": "slug only"}
    # a registry with no block for the provider maps no spec, so the name is matched as written
    assert spend.sampling_omissions("openrouter/anthropic/m", {"anthropic": registry["anthropic"]}) == {
        "temperature": "slug"}
    # the advice lane's reading of the slug is unchanged
    assert judge_runner._advice_eval_module().temperature_omission("anthropic/m", registry) == "slug"


def test_generate_config_kwargs_leaves_out_exactly_the_omitted_parameter():
    assert checks.generate_config_kwargs(SEED_GENERATION) == {"max_tokens": 1024, "temperature": 1.0, "seed": 7}
    assert checks.generate_config_kwargs(SEED_GENERATION, OMITTED) == {"max_tokens": 1024, "seed": 7}
    # the auditor prompt file's block carries no seed
    assert checks.generate_config_kwargs({"max_tokens": 400, "temperature": 1.0}, OMITTED) == {"max_tokens": 400}
    assert checks.generate_config_kwargs({"max_tokens": 400, "temperature": None}) == {"max_tokens": 400}


def test_the_generation_check_requires_an_omitted_parameter_to_be_absent():
    without = {"model": "m", "max_tokens": 1024, "seed": 7}
    with_it = {**without, "temperature": 1.0}
    assert checks.generation_problems(SEED_GENERATION, without, forwards_seed=True, omitted=OMITTED) == []
    [problem] = checks.generation_problems(SEED_GENERATION, with_it, forwards_seed=True, omitted=OMITTED)
    assert problem.startswith("temperature: sent 1.0 although the registry omits it") and "(test)" in problem
    # without an omission the old rule stands: the seed's temperature must be sent
    assert checks.generation_problems(SEED_GENERATION, without, forwards_seed=True) == ["temperature: not_sent"]
    assert checks.generation_problems(SEED_GENERATION, with_it, forwards_seed=True) == []
    # max_tokens is still required when only temperature is withheld
    assert checks.generation_problems(SEED_GENERATION, {"temperature": None}, forwards_seed=False,
                                      omitted=OMITTED) == ["max_tokens: not_sent"]


def test_the_manifest_schema_admits_sampling_omitted_on_both_role_blocks():
    """role_model is closed (additionalProperties false), so the key had to be declared; an absent key, which is
    every manifest written so far, still validates. The in-house validator checks the type, not minProperties or the
    value schema (the same gap test_petri_audit_core notes for events_dropped_by_type); the adapter writes the key
    only when non-empty, with the registry's reason strings."""
    schema = framework.load_json(framework.MANIFEST_SCHEMA)
    base = json.loads(json.dumps(schema["examples"][0]))
    assert "sampling_omitted" not in base["models"]["target"] and framework.validate_with_refs(base, schema) == []
    base["models"]["target"]["sampling_omitted"] = {"temperature": "rejects temperature (test)"}
    assert framework.validate_with_refs(base, schema) == []
    base["models"]["target"]["sampling_omitted"] = "temperature"
    assert framework.validate_with_refs(base, schema) == [
        "$.models.target.sampling_omitted: expected ['object'], got str"]
    for name in ("role_model", "role_model_nullable"):
        prop = schema["$defs"][name]["properties"]["sampling_omitted"]
        assert prop["minProperties"] == 1 and prop["additionalProperties"] == {"type": "string", "minLength": 1}
    assert manifest_mod.MANIFEST_SCHEMA == framework.MANIFEST_SCHEMA


# ------------------------------------------------------------------ the judge


def _registry_judge(monkeypatch, tmp_path, spec: str, registry: dict | None = None):
    ae = judge_runner._advice_eval_module()
    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_ANTHROPIC_NO_TEMPERATURE", False)
    path = None
    if registry is not None:
        path = tmp_path / "providers.json"
        path.write_text(json.dumps(registry), encoding="utf-8")
    return ae, judge_runner.RegistryJudge(spec, providers_path=path)


def test_a_listed_anthropic_judge_is_sent_no_temperature_and_the_reply_says_why(monkeypatch, tmp_path):
    ae, client = _registry_judge(monkeypatch, tmp_path, "claude-opus-5-5")
    sent = []
    monkeypatch.setattr(ae, "_send_anthropic_retrying", lambda c, model, system, prompt, max_tokens, temperature,
                        before_retry=None: sent.append((model, max_tokens, temperature))
                        or ("absent", 5, 6, {"model": model, "usage": {"input_tokens": 5, "output_tokens": 6}}, {}))
    reply = client.complete("prompt", max_tokens=300, temperature=judge_runner.TIER_TEMPERATURE)
    assert sent == [("claude-opus-5-5", 300, None)]
    assert reply.temperature_omitted and "Opus 5.5" in reply.temperature_omitted


def test_a_listed_openrouter_judge_is_sent_no_temperature(monkeypatch, tmp_path):
    ae, client = _registry_judge(monkeypatch, tmp_path, "openrouter:anthropic/claude-sonnet-5.5")
    sent = []
    monkeypatch.setattr(ae, "_pace", lambda *a: None)
    monkeypatch.setattr(ae, "_send_compat", lambda cfg, model, system, prompt, max_tokens, temperature,
                        before_retry=None: sent.append((model, temperature))
                        or ("absent", 5, 6, {"model": model, "usage": {"prompt_tokens": 5, "completion_tokens": 6}}, {}))
    reply = client.complete("prompt", max_tokens=300, temperature=0.0)
    assert sent == [("anthropic/claude-sonnet-5.5", None)] and reply.temperature_omitted


def test_an_unlisted_judge_is_sent_the_instruments_temperature(monkeypatch, tmp_path):
    ae, client = _registry_judge(monkeypatch, tmp_path, "claude-haiku-4-5")
    sent = []
    monkeypatch.setattr(ae, "_send_anthropic_retrying", lambda c, model, system, prompt, max_tokens, temperature,
                        before_retry=None: sent.append(temperature)
                        or ("absent", 5, 6, {"model": model, "usage": {"input_tokens": 5, "output_tokens": 6}}, {}))
    reply = client.complete("prompt", max_tokens=300, temperature=0.0)
    assert sent == [0.0] and client.temperature_omitted is None and reply.temperature_omitted is None
    # an installed SDK that drops the keyword is recorded on the reply, not hidden
    monkeypatch.setattr(ae, "_ANTHROPIC_NO_TEMPERATURE", True)
    assert client.complete("prompt", max_tokens=300, temperature=0.0).temperature_omitted == ae.SDK_DROPPED_TEMPERATURE
    # and on the client, which the sidecar and so the manifest's judge of record read (review of 2026-10-01)
    assert client.temperature_omitted == ae.SDK_DROPPED_TEMPERATURE


class _OmittingJudge(judge_runner.MockJudge):
    """A MockJudge whose model the registry says rejects temperature, as RegistryJudge reports one."""

    temperature_omitted = "rejects temperature (test)"

    def complete(self, prompt, *, max_tokens, temperature, attempt_gate=None):
        reply = super().complete(prompt, max_tokens=max_tokens, temperature=temperature, attempt_gate=attempt_gate)
        return judge_runner.JudgeReply(text=reply.text, input_tokens=reply.input_tokens,
                                       output_tokens=reply.output_tokens, served_model=reply.served_model,
                                       temperature_omitted=self.temperature_omitted)


def _plan(i: int) -> judge_runner.JudgePlan:
    return judge_runner.JudgePlan(conversation_id="c1", turn_id=i, assistant_turn_index=i, exchange_index=i,
                                  final_in_exchange=True, kind="outcome", key="k", prompt_ref="p.json",
                                  prompt=f"prompt {i}", prompt_file_digest="d" * 12, context_sha256=None,
                                  not_applicable_reason=None, allowed_values=["absent", "present"])


def test_judgment_rows_and_the_sidecar_record_an_omitted_temperature(tmp_path):
    out = tmp_path / "judgments.jsonl"
    side = judge_runner.run_judgments([_plan(2), _plan(4)], _OmittingJudge(lambda p: "absent"), out_path=out,
                                      ceiling=judge_runner.SpendCeiling(1.0, 1.0, 5.0, 300), judge_max_tokens=300,
                                      labels={}, now_fn=lambda: "2026-10-01T00:00:00Z")
    rows = judge_runner.read_jsonl(out)
    assert len(rows) == 2 and all(r["value"] == "absent" for r in rows)
    for r in rows:
        assert r["temperature"] == judge_runner.TIER_TEMPERATURE, "the instrument's setting stays recorded"
        assert r["temperature_sent"] is None and r["temperature_omitted"] == "rejects temperature (test)"
    assert side["temperature_sent"] is None and side["temperature_omitted"] == "rejects temperature (test)"
    # a judge whose calls carried the temperature writes the rows and sidecar it always wrote
    plain = tmp_path / "plain.jsonl"
    side = judge_runner.run_judgments([_plan(2)], judge_runner.MockJudge(lambda p: "absent"), out_path=plain,
                                      ceiling=judge_runner.SpendCeiling(1.0, 1.0, 5.0, 300), judge_max_tokens=300,
                                      labels={}, now_fn=lambda: "2026-10-01T00:00:00Z")
    [row] = judge_runner.read_jsonl(plain)
    assert "temperature_sent" not in row and "temperature_omitted" not in row
    assert "temperature_sent" not in side and "temperature_omitted" not in side


# ------------------------------------------------------------------ the pre-flight (CLI)


def test_the_preflight_names_the_withheld_parameter_for_target_and_judge(monkeypatch, capsys):
    monkeypatch.setattr(cli, "verify_lock", lambda *a, **k: envlock.LockReport(
        lock_path="locked-for-test", lock_sha256="0" * 64, digest_matches=True))
    args = ["preflight", "--no-harness-commit", "--token-limit", "40000", "--target", "anthropic/claude-opus-5-5",
            "--max-spend", "6", "--judge-model", "claude-sonnet-5-5", "--judge-max-spend", "1"]
    for s in ("pw-petri-example-h1-sustained", "pw-petri-example-h4-persistence", "pw-petri-example-h6-evidence"):
        args += ["--seed-id", s]
    code = cli.main(args)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "target anthropic/claude-opus-5-5: temperature omitted from every call (Claude Opus 5.5" in out
    assert "judge claude-sonnet-5-5: temperature omitted from every call (Claude Sonnet 5.5" in out
    assert "price anthropic/claude-opus-5-5: in 4.0/Mtok out 20.0/Mtok (engine:evaluate_models.PRICING)" in out
    assert "judge claude-sonnet-5-5: the registry's min_output_tokens is 4096; the judge step refuses" in out
    code = cli.main([a if a != "anthropic/claude-opus-5-5" else "anthropic/claude-haiku-4-5" for a in args])
    out = capsys.readouterr().out
    assert code == 0 and "target anthropic/claude-haiku-4-5: temperature omitted" not in out
    # a direct-API target whose name is also an OpenRouter slug gets its own entry's reason (review of 2026-10-02)
    code = cli.main([a if a != "anthropic/claude-opus-5-5" else "anthropic/claude-sonnet-5" for a in args])
    out = capsys.readouterr().out
    assert code == 0, out
    reason = _live_omissions()["claude-sonnet-5"]
    assert f"target anthropic/claude-sonnet-5: temperature omitted from every call ({reason})" in out
    assert "OpenRouter spelling" not in out


# ------------------------------------------------------------------ the judge of record (review of 2026-10-01)


def test_the_manifests_judge_of_record_records_an_omitted_temperature_and_validates():
    """The sealed manifest's judge of record said temperature 0.0 with no marker although no call carried one, and
    its closed schema had nowhere to say so."""
    sidecar = {"run_utc": "2026-10-01T00:00:00Z", "cost_usd": 0.01, "truncated": False, "planned": 3,
               "temperature_sent": None, "temperature_omitted": "rejects temperature (test)"}
    totals = {"judged": 3, "null": 0, "not_applicable": 0}
    block = cli.judge_of_record_block("claude-opus-5-5", "anthropic", "engine", sidecar, totals, 4096)
    assert block["temperature"] == judge_runner.TIER_TEMPERATURE, "the instrument's setting stays recorded"
    assert block["temperature_sent"] is None and block["temperature_omitted"] == "rejects temperature (test)"
    plain = cli.judge_of_record_block("claude-haiku-4-5", "anthropic", "engine",
                                      {k: v for k, v in sidecar.items() if not k.startswith("temperature_")}, totals, 300)
    assert "temperature_sent" not in plain and "temperature_omitted" not in plain
    schema = framework.load_json(framework.MANIFEST_SCHEMA)
    for jor in (block, plain):
        base = json.loads(json.dumps(schema["examples"][0]))
        base["artifacts"]["judge_of_record"] = {**jor, "report_path": "run_1_1/run_1_1.judge.report.json",
                                                "report_sha256": "0" * 64}
        assert framework.validate_with_refs(base, schema) == []
    base["artifacts"]["judge_of_record"]["temperature_sent"] = 0.0
    assert framework.validate_with_refs(base, schema) != []


def test_the_fallback_judge_sidecar_records_a_registry_omission(tmp_path):
    run_dir = tmp_path / "runs" / "run_9_1"
    run_dir.mkdir(parents=True)
    argv = ["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-opus-5-5", "--judge-max-spend",
            "1.5", "--judge-max-tokens", "4096"]
    assert cli.main(argv) == 0
    side = framework.load_json(run_dir / "run_9_1.judge.report.json")
    assert side["temperature"] == judge_runner.TIER_TEMPERATURE and side["temperature_sent"] is None
    assert "Opus 5.5" in side["temperature_omitted"] and side["cost_usd"] == 1.5
    other = tmp_path / "runs" / "run_9_2"
    other.mkdir()
    assert cli.main(["judge-spend-report", "--run-dir", str(other), "--judge-model", "claude-haiku-4-5",
                     "--judge-max-spend", "1.5"]) == 0
    side = framework.load_json(other / "run_9_2.judge.report.json")
    assert "temperature_sent" not in side and "temperature_omitted" not in side


# ------------------------------------------------------------------ the judge's other records agree with the judge

# Judge strings of each form a judge spec takes: provider:model, a bare Anthropic id, a bare provider (its consumer
# default), and colon-free strings containing "/". The judge's resolver reads the last group as bare Anthropic ids and
# sends them to the Anthropic API as written; a target's Inspect-name reading (spend.sampling_omissions) does not, so
# that group is where the two give another entry's reason or the opposite decision.
JUDGE_STRINGS = ["anthropic:claude-sonnet-5", "anthropic:claude-haiku-4-5", "openrouter:anthropic/claude-opus-5.5",
                 "openrouter:anthropic/claude-sonnet-5.5", "openrouter:openai/gpt-6-luna",
                 "openrouter:openai/gpt-5.4-mini", "claude-sonnet-5", "claude-opus-5-5", "claude-haiku-4-5",
                 "anthropic", "openai", "anthropic/claude-sonnet-5", "anthropic/claude-opus-5", "anthropic/claude-fable-5",
                 "anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5-5",
                 "anthropic/claude-haiku-4-5", "openrouter/anthropic/claude-sonnet-5.5", "openrouter/openai/gpt-6-luna"]


def _judge_sends(monkeypatch, tmp_path, spec: str) -> tuple[list, dict[str, str]]:
    """One judgment through RegistryJudge with its provider calls faked: the temperature each request carried, and
    the omission the judge records for it, in spend.sampling_omissions' shape."""
    ae, client = _registry_judge(monkeypatch, tmp_path, spec)
    sent = []

    def fake_send(*args, before_retry=None):   # (client or cfg, model, system, prompt, max_tokens, temperature)
        sent.append(args[5])
        return "absent", 5, 6, {"model": args[1], "usage": {"input_tokens": 5, "output_tokens": 6}}, {}

    monkeypatch.setattr(ae, "_send_anthropic_retrying", fake_send)
    monkeypatch.setattr(ae, "_send_compat", fake_send)
    monkeypatch.setattr(ae, "_pace", lambda *a: None)
    reply = client.complete("prompt", max_tokens=4096, temperature=judge_runner.TIER_TEMPERATURE)
    return sent, ({"temperature": reply.temperature_omitted} if reply.temperature_omitted else {})


def _recorded(sidecar: dict) -> dict[str, str]:
    """A judge sidecar's omission in the same shape; its two fields appear together or not at all."""
    if "temperature_omitted" not in sidecar:
        assert "temperature_sent" not in sidecar
        return {}
    assert sidecar["temperature_sent"] is None
    return {"temperature": sidecar["temperature_omitted"]}


@pytest.mark.parametrize("spec", JUDGE_STRINGS)
def test_the_preflight_and_both_fallback_sidecars_record_what_the_judge_sends(spec, monkeypatch, tmp_path, capsys):
    """Review of 2026-10-02: the pre-flight's judge line, the judge-spend-report sidecar and the rejudge fallback
    sidecar read the judge's spec with spend.sampling_omissions, while RegistryJudge resolves a colon-free spec as a
    bare Anthropic id. For `openrouter/openai/gpt-6-luna` and `anthropic/claude-opus-5-5` the three said temperature
    was withheld, naming an entry, where the judge matches no entry and sends it. Each must record what the judge
    sends, decision and reason."""
    sent, judge = _judge_sends(monkeypatch, tmp_path, spec)
    assert sent == [None if judge else judge_runner.TIER_TEMPERATURE], "the judge sends temperature unless it records why not"
    # the pre-flight's judge line
    monkeypatch.setattr(cli, "verify_lock", lambda *a, **k: envlock.LockReport(
        lock_path="locked-for-test", lock_sha256="0" * 64, digest_matches=True))
    argv = ["preflight", "--no-harness-commit", "--token-limit", "40000", "--target", "anthropic/claude-haiku-4-5",
            "--max-spend", "6", "--judge-model", spec, "--judge-max-spend", "1"]
    for s in ("pw-petri-example-h1-sustained", "pw-petri-example-h4-persistence", "pw-petri-example-h6-evidence"):
        argv += ["--seed-id", s]
    code = cli.main(argv)
    out = capsys.readouterr().out
    assert code == 0, out
    prefix, middle = f"judge {spec}: ", " omitted from every call ("
    lines = [line[len(prefix):] for line in out.splitlines() if line.startswith(prefix) and middle in line]
    assert {param: rest[:-1] for param, rest in (line.split(middle, 1) for line in lines)} == judge, out
    # the judge step's fallback sidecar
    run_dir = tmp_path / "runs" / "run_9_1"
    run_dir.mkdir(parents=True)
    assert cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", spec, "--judge-max-spend", "1.5",
                     "--judge-max-tokens", "4096"]) == 0
    assert _recorded(framework.load_json(run_dir / "run_9_1.judge.report.json")) == judge
    # the rejudge fallback sidecar, from a plan holding the fields impute_missing_reports reads
    plan = {"judge_model": spec, "judge_slug": "judge", "judge_max_tokens": 4096, "judge_max_spend_usd": 1.0,
            "rejudge_root": str(tmp_path / "rejudge"), "source_runs": ["run_4242_1"], "rehearsal": False,
            "fire": {"workflow_run_id": "777", "workflow_run_attempt": "1", "commit": "c" * 40, "journal_nonce": "rj-1"},
            "sources": [{"run_stem": "run_4242_1", "source": {"run_id": "Run4242", "eval_id": "Eval4242"}}]}
    started = tmp_path / "started"
    started.mkdir()
    framework.write_json(rejudge.started_marker(started, "run_4242_1"),
                         {"run_stem": "run_4242_1", "max_spend_usd": 1.0, "fire_spent_before_usd": 0.0})
    (written,) = rejudge.impute_missing_reports(plan, started)
    assert _recorded(framework.load_json(written)) == judge


def test_a_judge_spec_no_call_can_go_out_under_records_no_omission_and_refuses_nothing(tmp_path):
    """judge_sampling_omissions resolves as RegistryJudge does, and RegistryJudge cannot be built for a zero-price
    sentinel or a spec the registry cannot resolve, so no call goes out under either: {} for both, never an exception,
    so the fallback sidecar is still written. The pre-flight refuses such a spec earlier (judge_spec_problems)."""
    for spec in ("mockllm/judge", "mockllm/model", "none/none", "nosuchprovider:claude-opus-5-5", "copilot"):
        assert judge_runner.judge_sampling_omissions(spec) == {}, spec
    run_dir = tmp_path / "runs" / "run_9_3"
    run_dir.mkdir(parents=True)
    assert cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "nosuchprovider:claude-opus-5-5",
                     "--judge-max-spend", "1.5"]) == 0
    assert _recorded(framework.load_json(run_dir / "run_9_3.judge.report.json")) == {}


# ------------------------------------------------------------------ the judge's output allowance


@pytest.mark.parametrize("spec,tokens,refused", [
    ("claude-opus-5-5", 300, True), ("claude-opus-5-5", 4095, True), ("claude-opus-5-5", 4096, False),
    ("anthropic:claude-fable-5-1", 300, True), ("openrouter:google/gemini-3.1-pro-preview", 300, True),
    ("claude-haiku-4-5", 300, False), ("openrouter:openai/gpt-5.4-mini", 300, False),
    ("mockllm/judge", 1, False), ("nosuchprovider:model", 1, False),
])
def test_a_thinking_judge_below_the_registry_minimum_is_refused(spec, tokens, refused):
    """Review of 2026-10-01: the advice judge raises its allowance to the registry's min_output_tokens; the Petri
    judge sent its 300-token default to models that think before answering. Its allowance is part of the
    instrument, so it is refused rather than raised."""
    problems = judge_runner.judge_budget_problems(spec, tokens)
    assert bool(problems) is refused, problems
    if refused:
        assert "min_output_tokens" in problems[0] and str(judge_runner.judge_min_output_tokens(spec)) in problems[0]
