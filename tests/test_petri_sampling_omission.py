"""Sampling parameters the Petri lane withholds (registry revision of 2026-10-01).

Claude Fable 5.1, Opus 5.5 and Sonnet 5.5 reject temperature (the registry's anthropic `omit_temperature` map, from
the claude-api skill). The lane must leave it out of the target's and the auditor's GenerateConfig, the adapter must
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

from scripts.petri_audit import checks, cli, envlock, framework, judge_runner, spend  # noqa: E402
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402

SEED_GENERATION = {"max_tokens": 1024, "temperature": 1.0, "seed_requested": 7}
OMITTED = {"temperature": "rejects temperature (test)"}


@pytest.mark.parametrize("name", ["anthropic/claude-opus-5-5", "openrouter/anthropic/claude-opus-5.5",
                                  "anthropic/claude-fable-5-1", "anthropic/claude-sonnet-5-5",
                                  "openrouter/anthropic/claude-sonnet-5.5", "claude-opus-5-5",
                                  "openrouter:anthropic/claude-opus-5.5"])
def test_the_new_anthropic_models_have_temperature_withheld_in_every_spelling(name):
    assert set(spend.sampling_omissions(name)) == {"temperature"}


@pytest.mark.parametrize("name", ["anthropic/claude-haiku-4-5", "openrouter/anthropic/claude-haiku-4.5",
                                  "anthropic/claude-sonnet-5", "openrouter/openai/gpt-5.4-mini", "mockllm/model",
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
    code = cli.main([a if a != "anthropic/claude-opus-5-5" else "anthropic/claude-haiku-4-5" for a in args])
    out = capsys.readouterr().out
    assert code == 0 and "target anthropic/claude-haiku-4-5: temperature omitted" not in out
