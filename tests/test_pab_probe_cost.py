"""Tests for scripts/pab_probe_cost.py - the PatientAgentBench probe estimator.

scripts/ is not a package, so the module loads via importlib from its file path
(same pattern as test_validate_frontend_contract.py). The plan in
docs/pab_first_probe_costing.md quotes this module's numbers, so the headline
totals are pinned here: a silent edit to a size or a price would otherwise leave
the document quoting a figure nothing produces any more.

The pricing tests matter as much as the arithmetic ones. Every price has to come
from a named in-repo source, and a model with no verified price has to make the
total render N/A rather than quietly fall back to a default rate.
"""

import importlib.util
import json
from math import ceil
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "scripts" / "pab_probe_cost.py"
_SPEC = importlib.util.spec_from_file_location("pab_probe_cost", _MODULE_PATH)
ppc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ppc)

PATIENT = "openrouter:x-ai/grok-4.3"
ASSISTANT = ["openrouter:openai/gpt-5.4-mini"]
JURY = ["claude-opus-4-8"]
SANDBOX = "openrouter:openai/gpt-5.4-mini"
UNPRICED = "openrouter:nobody/not-in-the-registry"


def plan(**overrides):
    args = {**ppc.DEFAULT_PLAN, **overrides}
    return ppc.estimate(
        args["arms"], args["cases"], args["turns"], args["patient_model"],
        args["assistant_models"], args["jury_models"], args["sandbox_model"],
    )


class TestDocumentedPlan:
    def test_stage_two_total_matches_the_plan(self):
        """Pins the figure docs/pab_first_probe_costing.md quotes for the
        OpenRouter outcome pilot."""
        assert plan()["usd"]["total"] == pytest.approx(10.405, abs=0.001)

    def test_stage_one_total_matches_the_plan(self):
        """Generation only: the manipulation check that gates the jury spend."""
        result = plan(cases=8, jury_models=[])
        assert result["usd"]["total"] == pytest.approx(1.187, abs=0.001)
        assert result["fits_daily_ceiling"] is True

    def test_stage_one_fits_a_single_day(self):
        assert plan(cases=8, jury_models=[])["days_at_ceiling"] == 1

    def test_stage_two_is_scheduled_not_refused(self):
        result = plan()
        assert result["fits_daily_ceiling"] is False
        assert result["days_at_ceiling"] == 6

    def test_bedrock_preset_is_kept_for_the_diff(self):
        """The superseded plan stays costable so the re-costing can be
        checked rather than asserted."""
        bedrock = ppc.PRESETS["bedrock"]
        result = ppc.estimate(
            bedrock["arms"], bedrock["cases"], bedrock["turns"],
            bedrock["patient_model"], bedrock["assistant_models"],
            bedrock["jury_models"], bedrock["sandbox_model"],
        )
        assert result["usd"]["total"] == pytest.approx(10.211, abs=0.001)

    def test_openrouter_costs_slightly_more_than_bedrock(self):
        """The headline of the re-costing: the channel switch is close to
        cost-neutral because the jury dominates and does not move."""
        bedrock = ppc.PRESETS["bedrock"]
        old = ppc.estimate(
            bedrock["arms"], bedrock["cases"], bedrock["turns"],
            bedrock["patient_model"], bedrock["assistant_models"],
            bedrock["jury_models"], bedrock["sandbox_model"],
        )["usd"]["total"]
        new = plan()["usd"]["total"]
        assert 1.0 < new / old < 1.1


class TestPricing:
    def test_openrouter_prices_come_from_the_provider_registry(self):
        table = ppc.openrouter_prices()
        assert table, "no OpenRouter prices resolved from data/advice_providers.json"
        for key, price in table.items():
            assert key.startswith("openrouter:")
            assert len(price) == 2 and all(p >= 0 for p in price)

    def test_every_plan_model_resolves_to_a_named_source(self):
        for model in (SANDBOX, PATIENT, *ASSISTANT, *JURY):
            price, source = ppc.resolve_price(model)
            assert price is not None, model
            assert source and "no verified price" not in source

    def test_openrouter_models_cite_the_provider_registry(self):
        _price, source = ppc.resolve_price(PATIENT)
        assert "advice_providers.json" in source

    def test_jury_price_comes_from_this_repo_s_table(self):
        """The jury stays on the direct Anthropic API, priced from the engine's
        own table -- and this resolves even though scripts/ is on sys.path
        instead of the repo root."""
        price, source = ppc.resolve_price("claude-opus-4-8")
        assert price == (5.0, 25.0)
        assert "evaluate_models" in source

    def test_unknown_model_is_unpriced_not_defaulted(self):
        price, reason = ppc.resolve_price(UNPRICED)
        assert price is None
        assert "no verified" in reason

    def test_unpriced_role_makes_the_total_na(self):
        """Upstream's rule, carried through: None -> unpriced, never guessed."""
        result = plan(assistant_models=[UNPRICED])
        assert result["usd"]["total"] is None
        assert result["unpriced_roles"] == ["assistant"]
        assert result["usd_per_conversation"] is None
        assert result["days_at_ceiling"] is None

    def test_priced_subtotal_survives_an_unpriced_role(self):
        result = plan(assistant_models=[UNPRICED])
        assert result["usd"]["priced_subtotal"] > 0
        assert result["usd"]["sandbox"] is not None

    def test_missing_provider_registry_yields_no_prices(self, tmp_path):
        assert ppc.openrouter_prices(tmp_path / "absent.json") == {}


class TestCostStructure:
    def test_the_jury_dominates(self):
        """The reason the plan is staged: scoring costs several times what
        generating the conversations costs."""
        usd = plan()["usd"]
        assert usd["jury"] > usd["sandbox"] + usd["patient"] + usd["assistant"]

    def test_sandbox_leg_is_counted(self):
        """One generation call per conversation, not per run. The runner makes
        it and discards the response, so it is easy to leave out of a model."""
        assert plan()["usd"]["sandbox"] > 0

    def test_sandbox_scales_with_conversations(self):
        assert plan(cases=20)["usd"]["sandbox"] == pytest.approx(
            2 * plan(cases=10)["usd"]["sandbox"], rel=1e-3
        )

    def test_no_jury_removes_the_jury_cost(self):
        assert plan(jury_models=[])["usd"]["jury"] == 0.0

    # Totals are rounded to the cent-fraction on the way out, so the linearity
    # comparisons carry a tolerance wider than that rounding.
    def test_cost_is_linear_in_cases(self):
        one = plan(cases=10)["usd"]["total"]
        two = plan(cases=20)["usd"]["total"]
        assert two == pytest.approx(2 * one, rel=1e-4)

    def test_cost_is_linear_in_arms(self):
        assert plan(arms=8)["usd"]["total"] == pytest.approx(
            2 * plan(arms=4)["usd"]["total"], rel=1e-4
        )

    def test_cost_grows_faster_than_linearly_in_turns(self):
        """Every call re-sends the context accumulated so far."""
        short = plan(turns=3)["usd"]["total"]
        long = plan(turns=6)["usd"]["total"]
        assert long / short > 1.3

    def test_adding_an_assistant_adds_its_own_conversations(self):
        one = plan()["conversations_total"]
        two = plan(assistant_models=ASSISTANT + ["openrouter:openai/gpt-5.5"])
        assert two["conversations_total"] == 2 * one

    def test_a_dearer_assistant_costs_more(self):
        cheap = plan()["usd"]["assistant"]
        dear = plan(assistant_models=["openrouter:openai/gpt-5.5"])["usd"]["assistant"]
        assert dear > cheap


class TestCeilingArithmetic:
    def test_days_at_ceiling_is_the_rounded_up_quotient(self):
        result = plan()
        assert result["days_at_ceiling"] == ceil(
            result["usd"]["total"] / ppc.DAILY_CEILING_USD
        )

    def test_max_cases_stays_under_the_ceiling(self):
        n = ppc.max_cases_within_ceiling(4, 3, PATIENT, ASSISTANT, JURY, SANDBOX)
        assert n >= 1
        under = ppc.estimate(4, n, 3, PATIENT, ASSISTANT, JURY, SANDBOX)
        over = ppc.estimate(4, n + 1, 3, PATIENT, ASSISTANT, JURY, SANDBOX)
        assert under["usd"]["total"] <= ppc.DAILY_CEILING_USD
        assert over["usd"]["total"] > ppc.DAILY_CEILING_USD

    def test_max_cases_is_zero_when_unpriced(self):
        assert ppc.max_cases_within_ceiling(4, 3, PATIENT, [UNPRICED], JURY) == 0

    def test_a_cheaper_jury_buys_more_cases_per_day(self):
        opus = ppc.max_cases_within_ceiling(4, 3, PATIENT, ASSISTANT, JURY, SANDBOX)
        haiku = ppc.max_cases_within_ceiling(
            4, 3, PATIENT, ASSISTANT, ["claude-haiku-4-5"], SANDBOX
        )
        assert haiku > opus


class TestCli:
    def test_default_plan_exits_one_over_the_ceiling(self, capsys):
        assert ppc.main([]) == 1
        assert "days at the ceiling" in capsys.readouterr().out

    def test_stage_one_exits_zero(self, capsys):
        assert ppc.main(["--cases", "8", "--no-jury"]) == 0
        assert "within" in capsys.readouterr().out

    def test_bedrock_preset_selectable(self, capsys):
        ppc.main(["--preset", "bedrock"])
        assert "[bedrock]" in capsys.readouterr().out

    def test_unpriced_plan_prints_na_and_exits_one(self, capsys):
        assert ppc.main(["--assistant-model", UNPRICED]) == 1
        out = capsys.readouterr().out
        assert "N/A" in out
        assert "never guessed" in out

    def test_prepaid_balance_is_checked_when_given(self, capsys):
        ppc.main(["--cases", "8", "--no-jury", "--balance", "25"])
        assert "prepaid balance $25.00: within" in capsys.readouterr().out

    def test_prepaid_balance_flags_an_overrun(self, capsys):
        ppc.main(["--balance", "5"])
        assert "prepaid balance $5.00: OVER" in capsys.readouterr().out

    def test_json_mode(self, capsys):
        ppc.main(["--cases", "8", "--no-jury", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["usd"]["jury"] == 0.0
        assert payload["jury_models"] == []
        assert payload["price_sources"][PATIENT]
