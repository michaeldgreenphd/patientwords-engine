"""The fallback-price judge guard (owner decision Q6, 2026-10-14) and the price of the second judge, Claude Haiku 5.5
(owner decision Q8).

A judge spec that no price table names is booked at the 10/50 fallback rate: eq01's `anthropic/claude-haiku-4-5` (a
slash where the judge's registry spelling takes a colon or the bare id) expanded to `anthropic/anthropic/claude-haiku-
4-5` and was booked at ten times list, and before this change `claude-haiku-5-5` would have been booked at a hundred
times its list price. The Petri lane refuses such a spec in `cli preflight`, `cli judge` and the rejudge plan
(scripts/petri_audit/spend.py judge_fallback_price_problems), and the fire path refuses it before it journals
(scripts/fire_trigger.py, which reads the engine's PRICING with `ast` and mirrors resolve_price's lookup order); the
advice lane's fire path refuses its own fallback-priced judge. The two views are held to agree here. Offline: nothing
fires and no provider is called.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, envlock, framework, judge_runner, rejudge, spend  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")
LIVE_REGISTRY = json.loads((ROOT / "data" / "advice_providers.json").read_text(encoding="utf-8"))

# Every form a judge spec takes: a bare Anthropic id, provider:model, a bare provider (its consumer default), an
# OpenRouter slug with and without a reviewed entry, the zero-price sentinels, and the slash spellings the guard exists
# to refuse.
SPECS = ["claude-haiku-4-5", "claude-haiku-5-5", "anthropic:claude-haiku-5-5", "anthropic:claude-haiku-4-5",
         "claude-opus-5-5", "claude-sonnet-5", "claude-fable-5-1", "anthropic", "openai", "xai",
         "openai:gpt-5.4-mini", "openrouter:openai/gpt-5.4-mini", "openrouter:anthropic/claude-haiku-4.5",
         "openrouter:anthropic/claude-haiku-5-5", "openrouter:openai/no-such-slug", "deepseek:deepseek-chat",
         "mockllm/judge", "mockllm/model", "none/none",
         "anthropic/claude-haiku-4-5", "anthropic/claude-haiku-5-5", "claude-haiku-9-9", "judge-x"]
FALLBACK = ["anthropic/claude-haiku-4-5", "anthropic/claude-haiku-5-5", "claude-haiku-9-9", "judge-x"]


def test_the_fire_path_reads_the_engine_price_table_as_the_package_defines_it():
    from medlang_circuits.evaluate_models import PRICING

    assert ft.engine_pricing() == {k: (float(v[0]), float(v[1])) for k, v in PRICING.items()}
    assert ft.engine_pricing(ROOT / "no-such-checkout") == {}, "a missing table reads as empty (fail closed)"


@pytest.mark.parametrize("spec", SPECS)
def test_the_fire_path_prices_every_petri_judge_spec_as_resolve_registry_price_does(spec):
    price = spend.resolve_registry_price(spec, LIVE_REGISTRY)
    assert ft.petri_judge_price(spec, LIVE_REGISTRY) == (price.input_per_mtok, price.output_per_mtok, price.source)
    refused_here = bool(ft.petri_judge_price_problems(spec, LIVE_REGISTRY))
    refused_there = bool(spend.judge_fallback_price_problems(spec, LIVE_REGISTRY))
    assert refused_here == refused_there == (spec in FALLBACK), spec


def test_the_two_views_agree_on_a_registry_built_to_reach_every_branch():
    registry = {"anthropic": {"api": "anthropic", "pricing": {"model-a": [3, 4]}},
                "vendor": {"api": "openai_compat", "key_env": "OPENROUTER_API_KEY", "consumer_default": "v-1",
                           "default_pricing": [7, 8]},
                "bare": {"api": "openai_compat", "key_env": "OPENROUTER_API_KEY"},
                "openrouter": {"api": "openai_compat", "key_env": "OPENROUTER_API_KEY", "default_pricing": [5, 30],
                               "pricing": {"vendor/listed": [1, 2]}}}
    engine = {"model-e": (0.5, 1.5), "claude-z": (11.0, 60.0)}
    for spec in ("model-a", "model-e", "model-u", "anthropic:model-a", "vendor", "vendor:x", "openrouter:vendor/listed",
                 "openrouter:vendor/other", "openrouter:anthropic/claude-z", "openrouter:anthropic/claude-q",
                 "openrouter:nobody/x", "mockllm/judge"):
        price = spend.resolve_registry_price(spec, registry, engine)
        assert ft.petri_judge_price(spec, registry, engine) == (price.input_per_mtok, price.output_per_mtok,
                                                                price.source), spec
    # a bare provider without a consumer_default cannot be expanded: the fire path names nothing, spend names it
    assert ft.petri_judge_price("bare", registry, engine) is None and ft.petri_judge_price_problems("bare", registry) == []
    assert "consumer_default" in spend.judge_fallback_price_problems("bare", registry, engine)[0]


def test_haiku_5_5_is_priced_at_list_where_it_was_booked_at_the_fallback():
    price = spend.resolve_registry_price("claude-haiku-5-5")
    assert (price.input_per_mtok, price.output_per_mtok, price.source) == (0.10, 0.50, "engine:evaluate_models.PRICING")
    assert spend.resolve_registry_price("anthropic:claude-haiku-5-5") == price
    # before this change the engine table did not name it, and the same lookup booked it at 10/50, a hundred times list
    before = spend.resolve_registry_price("claude-haiku-5-5", engine_pricing={})
    assert (before.input_per_mtok, before.output_per_mtok) == spend.FALLBACK_PRICING
    assert spend.judge_fallback_price_problems("claude-haiku-5-5", engine_pricing={})
    assert spend.judge_fallback_price_problems("claude-haiku-5-5") == []


def test_the_slash_spelling_of_eq01_is_refused_and_says_how_to_spell_it():
    [problem] = spend.judge_fallback_price_problems("anthropic/claude-haiku-4-5")
    assert problem.startswith(spend.FALLBACK_PRICED_JUDGE) and "'anthropic/anthropic/claude-haiku-4-5'" in problem
    assert "10.0/50.0" in problem and "claude-haiku-4-5" in problem
    assert spend.judge_fallback_price_problems(" mockllm/judge ") == [], "the sentinels keep their own handling"


@pytest.mark.parametrize("spec", FALLBACK)
def test_the_rejudge_plan_and_the_fire_path_refuse_a_fallback_priced_judge(spec):
    assert any(p.startswith(spend.FALLBACK_PRICED_JUDGE) for p in rejudge.judge_spec_refusals(spec)), spec
    assert any("fallback_priced_judge" in p for p in ft.petri_judge_spec_problems(spec)), spec


@pytest.mark.parametrize("spec", ["claude-haiku-5-5", "anthropic:claude-haiku-5-5", "claude-haiku-4-5"])
def test_the_rejudge_plan_and_the_fire_path_admit_the_two_judges(spec):
    assert rejudge.judge_spec_refusals(spec) == []
    assert ft.petri_judge_spec_problems(spec) == []


def _run_params(judge_model: str, mode: str = "run") -> dict:
    return dict(ft.PARK_DEFAULTS["petri-audit"], mode=mode, judge="true", judge_max_spend="0.01", _nonce="n1",
                target="anthropic/claude-haiku-4-5", judge_model=judge_model)


def test_a_paid_run_with_a_fallback_priced_judge_is_refused_before_it_journals():
    assert any("fallback_priced_judge" in p for p in ft.petri_params_problems(_run_params("anthropic/claude-haiku-4-5")))
    assert not any("fallback_priced_judge" in p for p in ft.petri_params_problems(_run_params("claude-haiku-5-5")))
    with pytest.raises(ValueError, match="fallback_priced_judge"):
        ft.validate_params("petri-audit", _run_params("anthropic/claude-haiku-4-5"))
    # a free mode and a run without the judge are not refused for a judge they do not call
    assert not any("fallback_priced_judge" in p
                   for p in ft.petri_params_problems(_run_params("anthropic/claude-haiku-4-5", mode="preflight")))
    assert not any("fallback_priced_judge" in p
                   for p in ft.petri_params_problems(dict(_run_params("anthropic/claude-haiku-4-5"), judge="false")))


def _preflight(monkeypatch, capsys, judge_model: str) -> tuple[int, str, str]:
    monkeypatch.setattr(cli, "verify_lock", lambda *a, **k: envlock.LockReport(
        lock_path="locked-for-test", lock_sha256="0" * 64, digest_matches=True))
    argv = ["preflight", "--no-harness-commit", "--token-limit", "40000", "--target", "anthropic/claude-haiku-4-5",
            "--max-spend", "6", "--judge-model", judge_model, "--judge-max-spend", "1"]
    for s in ("pw-petri-example-h1-sustained", "pw-petri-example-h4-persistence", "pw-petri-example-h6-evidence"):
        argv += ["--seed-id", s]
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_preflight_refuses_a_fallback_priced_judge_and_prices_haiku_5_5_at_list(monkeypatch, capsys):
    code, _, err = _preflight(monkeypatch, capsys, "anthropic/claude-haiku-4-5")
    assert code == 5 and "fallback_priced_judge" in err
    code, out, _ = _preflight(monkeypatch, capsys, "claude-haiku-5-5")
    assert code == 0, out
    assert "judge claude-haiku-5-5: anthropic channel, in 0.1/Mtok out 0.5/Mtok (engine:evaluate_models.PRICING)" in out
    assert "judge claude-haiku-5-5: temperature omitted from every call (Claude Haiku 5.5" in out
    assert "judge claude-haiku-5-5: thinking disabled on every call (Claude Haiku 5.5" in out
    assert "min_output_tokens" not in out, "Haiku 5.5 judges at the 300-token allowance its judge of record used"


def test_cli_judge_refuses_a_fallback_priced_judge_before_reading_the_run(tmp_path, capsys):
    code = cli.main(["judge", "--run-dir", str(tmp_path / "no-such-run"), "--judge-model", "anthropic/claude-haiku-4-5",
                     "--judge-max-spend", "0.5"])
    assert code == 5 and "fallback_priced_judge" in capsys.readouterr().err


# ------------------------------------------------------------------ the advice lane's fire path


def _advice_judge_fire(judge_model: str) -> dict:
    return {"models": "claude-haiku-4-5", "arms": "clinical", "judge": "true", "judge_model": judge_model,
            "offset": "999", "max_spend": "0.01", "judge_max_spend": "0.50"}


def test_the_advice_fire_path_refuses_a_bare_second_claude_judge_and_admits_its_secondary_spelling():
    problems = ft.advice_params_problems(_advice_judge_fire("claude-haiku-5-5"), LIVE_REGISTRY)
    assert len(problems) == 1 and "anthropic:claude-haiku-5-5" in problems[0] and "pool" in problems[0]
    assert ft.advice_params_problems(_advice_judge_fire("anthropic:claude-haiku-5-5"), LIVE_REGISTRY) == []
    assert ft.advice_params_problems(_advice_judge_fire("claude-haiku-4-5"), LIVE_REGISTRY) == []


@pytest.mark.parametrize("spec", ["anthropic/claude-haiku-4-5", "judge-x", "anthropic:claude-haiku-9-9"])
def test_the_advice_fire_path_refuses_a_fallback_priced_judge(spec):
    problems = ft.advice_params_problems(_advice_judge_fire(spec), LIVE_REGISTRY)
    assert any("fallback_priced_judge" in p for p in problems), problems


def _advice_eval():
    return judge_runner._advice_eval_module()


@pytest.mark.parametrize("spec", ["claude-haiku-4-5", "claude-haiku-5-5", "anthropic:claude-haiku-5-5", "openai",
                                  "openai:gpt-5.4-mini", "openrouter:openai/gpt-5.4-mini", "openrouter:openai/nope",
                                  "anthropic/claude-haiku-4-5", "judge-x", "deepseek:deepseek-chat"])
def test_the_advice_fire_path_prices_a_judge_as_the_advice_judge_books_it(spec):
    """advice_eval.judge books its judge through CostTracker: the registry block's pricing entry for the resolved
    model (keyed by the spec), else the engine's PRICING under the spec or its model part, else the fallback."""
    ae = _advice_eval()
    registry = ae._load_providers(ae.DEFAULT_PROVIDERS)
    resolved = ae._resolve_spec(spec, registry)
    entry = (resolved["cfg"].get("pricing") or {}).get(resolved["model"])
    custom = {spec: (float(entry[0]), float(entry[1]))} if entry else {}
    booked = ae.CostTracker(1.0, 300, custom)._price(spec)
    rates = ft.advice_judge_price(spec, LIVE_REGISTRY)
    assert rates[:2] == tuple(booked), spec
    named = bool(custom) or any(c in ae._PRICING for c in (spec, spec.split(":", 1)[-1]))
    assert (rates[2] == ft.FALLBACK_PRICE_SOURCE) is (not named), spec


# ------------------------------------------------------------------ the second judge's records on the Petri lane


def _registry_judge(monkeypatch, spec: str):
    ae = _advice_eval()
    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_ANTHROPIC_NO_TEMPERATURE", False)
    return ae, judge_runner.RegistryJudge(spec)


def test_the_petri_judge_sends_haiku_5_5_thinking_disabled_and_no_temperature(monkeypatch):
    ae, client = _registry_judge(monkeypatch, "claude-haiku-5-5")
    sent = []

    def send(c, model, system, prompt, max_tokens, temperature, before_retry=None, thinking=None):
        sent.append((model, max_tokens, temperature, thinking))
        return "absent", 5, 6, {"model": model, "usage": {"input_tokens": 5, "output_tokens": 6}}, {}

    monkeypatch.setattr(ae, "_send_anthropic_retrying", send)
    reply = client.complete("prompt", max_tokens=300, temperature=judge_runner.TIER_TEMPERATURE)
    assert sent == [("claude-haiku-5-5", 300, None, {"type": "disabled"})]
    assert "Haiku 5.5" in reply.temperature_omitted and "Haiku 5.5" in reply.thinking_disabled
    assert client.thinking_disabled == reply.thinking_disabled
    assert judge_runner.judge_thinking_disabled("claude-haiku-5-5") == reply.thinking_disabled
    assert judge_runner.judge_min_output_tokens("claude-haiku-5-5") is None
    assert judge_runner.judge_budget_problems("claude-haiku-5-5", 300) == []


def test_the_judge_of_record_is_sent_exactly_what_it_was(monkeypatch):
    """No thinking keyword reaches the send for an unlisted judge, so the six-argument stubs and the call keep
    their shape."""
    ae, client = _registry_judge(monkeypatch, "claude-haiku-4-5")
    sent = []
    monkeypatch.setattr(ae, "_send_anthropic_retrying", lambda c, model, system, prompt, max_tokens, temperature,
                        before_retry=None: sent.append(temperature)
                        or ("absent", 5, 6, {"model": model, "usage": {"input_tokens": 5, "output_tokens": 6}}, {}))
    reply = client.complete("prompt", max_tokens=300, temperature=0.0)
    assert sent == [0.0] and reply.thinking_disabled is None and client.thinking_disabled is None
    assert judge_runner.judge_thinking_disabled("claude-haiku-4-5") is None


def test_a_thinking_disabled_judge_on_a_route_that_cannot_send_it_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "providers.json"
    path.write_text(json.dumps({"anthropic": {"api": "anthropic", "disable_thinking": {"vendor/m": "why"}},
                                "fakeai": {"api": "openai_compat", "base_url": "https://fake.example/v1",
                                           "key_env": "OPENROUTER_API_KEY"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="only the direct Anthropic API path"):
        judge_runner.RegistryJudge("fakeai:vendor/m", providers_path=path)


class _ThinkingOffJudge(judge_runner.MockJudge):
    """A MockJudge reporting what RegistryJudge reports for Claude Haiku 5.5."""

    temperature_omitted = "rejects temperature (test)"
    thinking_disabled = "thinking off (test)"

    def complete(self, prompt, *, max_tokens, temperature, attempt_gate=None):
        reply = super().complete(prompt, max_tokens=max_tokens, temperature=temperature, attempt_gate=attempt_gate)
        return judge_runner.JudgeReply(text=reply.text, input_tokens=reply.input_tokens,
                                       output_tokens=reply.output_tokens, served_model=reply.served_model,
                                       temperature_omitted=self.temperature_omitted,
                                       thinking_disabled=self.thinking_disabled)


def _plan(i: int) -> judge_runner.JudgePlan:
    return judge_runner.JudgePlan(conversation_id="c1", turn_id=i, assistant_turn_index=i, exchange_index=i,
                                  final_in_exchange=True, kind="outcome", key="k", prompt_ref="p.json",
                                  prompt=f"prompt {i}", prompt_file_digest="d" * 12, context_sha256=None,
                                  not_applicable_reason=None, allowed_values=["absent", "present"])


def test_judgment_rows_and_the_sidecar_record_thinking_disabled(tmp_path):
    out = tmp_path / "judgments.jsonl"
    side = judge_runner.run_judgments([_plan(2), _plan(4)], _ThinkingOffJudge(lambda p: "absent"), out_path=out,
                                      ceiling=judge_runner.SpendCeiling(1.0, 0.1, 0.5, 300), judge_max_tokens=300,
                                      labels={}, now_fn=lambda: "2026-10-14T00:00:00Z")
    rows = judge_runner.read_jsonl(out)
    assert len(rows) == 2
    for r in rows:
        assert r["thinking_sent"] == "disabled" and r["thinking_disabled"] == "thinking off (test)"
        assert r["temperature_sent"] is None and r["max_tokens"] == 300
    assert side["thinking_sent"] == "disabled" and side["thinking_disabled"] == "thinking off (test)"
    plain = tmp_path / "plain.jsonl"
    side = judge_runner.run_judgments([_plan(2)], judge_runner.MockJudge(lambda p: "absent"), out_path=plain,
                                      ceiling=judge_runner.SpendCeiling(1.0, 1.0, 5.0, 300), judge_max_tokens=300,
                                      labels={}, now_fn=lambda: "2026-10-14T00:00:00Z")
    [row] = judge_runner.read_jsonl(plain)
    assert "thinking_sent" not in row and "thinking_disabled" not in row
    assert "thinking_sent" not in side and "thinking_disabled" not in side


def test_the_manifests_judge_of_record_records_thinking_disabled_and_validates():
    sidecar = {"run_utc": "2026-10-14T00:00:00Z", "cost_usd": 0.01, "truncated": False, "planned": 3,
               "temperature_sent": None, "temperature_omitted": "rejects temperature (test)",
               "thinking_sent": "disabled", "thinking_disabled": "thinking off (test)"}
    totals = {"judged": 3, "null": 0, "not_applicable": 0}
    block = cli.judge_of_record_block("claude-haiku-5-5", "anthropic", "engine", sidecar, totals, 300)
    assert block["thinking_sent"] == "disabled" and block["thinking_disabled"] == "thinking off (test)"
    plain = cli.judge_of_record_block("claude-haiku-4-5", "anthropic", "engine",
                                      {k: v for k, v in sidecar.items() if not k.startswith(("temperature_", "thinking_"))},
                                      totals, 300)
    assert "thinking_sent" not in plain and "thinking_disabled" not in plain
    schema = framework.load_json(framework.MANIFEST_SCHEMA)
    for jor in (block, plain):
        base = json.loads(json.dumps(schema["examples"][0]))
        base["artifacts"]["judge_of_record"] = {**jor, "report_path": "run_1_1/run_1_1.judge.report.json",
                                                "report_sha256": "0" * 64}
        assert framework.validate_with_refs(base, schema) == []
    base["artifacts"]["judge_of_record"]["thinking_sent"] = "enabled"
    assert framework.validate_with_refs(base, schema) != []
    # a rejudge copies them from its source's judge of record
    assert {"thinking_sent", "thinking_disabled"} <= set(rejudge.JUDGE_OF_RECORD_OPTIONAL_KEYS)


def test_both_fallback_judge_sidecars_record_thinking_disabled(tmp_path):
    run_dir = tmp_path / "runs" / "run_9_1"
    run_dir.mkdir(parents=True)
    assert cli.main(["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-haiku-5-5",
                     "--judge-max-spend", "1.5", "--judge-max-tokens", "300"]) == 0
    side = framework.load_json(run_dir / "run_9_1.judge.report.json")
    assert side["thinking_sent"] == "disabled" and "Haiku 5.5" in side["thinking_disabled"]
    assert side["price_source"] == "engine:evaluate_models.PRICING" and side["input_per_mtok"] == 0.10
    plan = {"judge_model": "claude-haiku-5-5", "judge_slug": "claude-haiku-5-5", "judge_max_tokens": 300,
            "judge_max_spend_usd": 1.0, "rejudge_root": str(tmp_path / "rejudge"), "source_runs": ["run_4242_1"],
            "rehearsal": False,
            "fire": {"workflow_run_id": "777", "workflow_run_attempt": "1", "commit": "c" * 40, "journal_nonce": "rj-1"},
            "sources": [{"run_stem": "run_4242_1", "source": {"run_id": "Run4242", "eval_id": "Eval4242"}}]}
    started = tmp_path / "started"
    started.mkdir()
    framework.write_json(rejudge.started_marker(started, "run_4242_1"),
                         {"run_stem": "run_4242_1", "max_spend_usd": 1.0, "fire_spent_before_usd": 0.0})
    (written,) = rejudge.impute_missing_reports(plan, started)
    side = framework.load_json(written)
    assert side["thinking_sent"] == "disabled" and "Haiku 5.5" in side["thinking_disabled"]
    assert side["temperature_sent"] is None
