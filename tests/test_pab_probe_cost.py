"""Tests for scripts/pab_probe_cost.py - the PatientAgentBench probe estimator.

scripts/ is not a package, so the module loads via importlib from its file path
(same pattern as test_validate_frontend_contract.py). The plan in
docs/pab_first_probe_costing.md quotes this module's numbers, so the headline
totals are pinned here: a silent edit to a size or a price would otherwise leave
the document quoting a figure nothing produces any more.
"""

import importlib.util
import json
from math import ceil
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pab_probe_cost.py"
_SPEC = importlib.util.spec_from_file_location("pab_probe_cost", _MODULE_PATH)
ppc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ppc)

PATIENT = "qwen3-235b-bedrock"
ASSISTANT = ["claude-haiku-4.5-bedrock"]
JURY = ["claude-opus-4.8-bedrock"]


def plan(**overrides):
    args = {**ppc.DEFAULT_PLAN, **overrides}
    return ppc.estimate(
        args["arms"], args["cases"], args["turns"], args["patient_model"],
        args["assistant_models"], args["jury_models"],
    )


class TestDocumentedPlan:
    def test_stage_two_total_matches_the_plan(self):
        """Pins the figure docs/pab_first_probe_costing.md quotes for the
        outcome pilot."""
        assert plan()["usd"]["total"] == pytest.approx(10.004, abs=0.001)

    def test_stage_one_total_matches_the_plan(self):
        """Generation only: the manipulation check that gates the jury spend."""
        result = plan(cases=8, jury_models=[])
        assert result["usd"]["total"] == pytest.approx(0.940, abs=0.001)
        assert result["fits_daily_ceiling"] is True

    def test_stage_one_fits_a_single_day(self):
        assert plan(cases=8, jury_models=[])["days_at_ceiling"] == 1

    def test_stage_two_is_scheduled_not_refused(self):
        result = plan()
        assert result["fits_daily_ceiling"] is False
        assert result["days_at_ceiling"] == 6


class TestCostStructure:
    def test_the_jury_dominates(self):
        """The reason the plan is staged: scoring costs several times what
        generating the conversations costs."""
        usd = plan()["usd"]
        assert usd["jury"] > usd["patient"] + usd["assistant"]

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
        assert long > 2 * short * 0.5  # sanity: it grows
        assert long / short > 1.3      # and faster than the transcript alone

    def test_adding_an_assistant_adds_its_own_conversations(self):
        one = plan()["conversations_total"]
        two = plan(assistant_models=ASSISTANT + ["gpt-oss-120b-bedrock"])
        assert two["conversations_total"] == 2 * one

    def test_unpriced_model_is_rejected(self):
        with pytest.raises(KeyError, match="no price"):
            ppc.estimate(4, 5, 3, "no-such-model", ASSISTANT, JURY)


class TestCeilingArithmetic:
    def test_days_at_ceiling_is_the_rounded_up_quotient(self):
        result = plan()
        assert result["days_at_ceiling"] == ceil(
            result["usd"]["total"] / ppc.DAILY_CEILING_USD
        )

    def test_max_cases_stays_under_the_ceiling(self):
        n = ppc.max_cases_within_ceiling(4, 3, PATIENT, ASSISTANT, JURY)
        assert n >= 1
        under = ppc.estimate(4, n, 3, PATIENT, ASSISTANT, JURY)
        over = ppc.estimate(4, n + 1, 3, PATIENT, ASSISTANT, JURY)
        assert under["usd"]["total"] <= ppc.DAILY_CEILING_USD
        assert over["usd"]["total"] > ppc.DAILY_CEILING_USD

    def test_a_cheaper_jury_buys_more_cases_per_day(self):
        opus = ppc.max_cases_within_ceiling(4, 3, PATIENT, ASSISTANT, JURY)
        haiku = ppc.max_cases_within_ceiling(
            4, 3, PATIENT, ASSISTANT, ["claude-haiku-4.5-bedrock"]
        )
        assert haiku > opus


class TestCli:
    def test_default_plan_exits_one_over_the_ceiling(self, capsys):
        assert ppc.main([]) == 1
        assert "days at the ceiling" in capsys.readouterr().out

    def test_stage_one_exits_zero(self, capsys):
        assert ppc.main(["--cases", "8", "--no-jury"]) == 0
        assert "within" in capsys.readouterr().out

    def test_json_mode(self, capsys):
        ppc.main(["--cases", "8", "--no-jury", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["usd"]["jury"] == 0.0
        assert payload["jury_models"] == []
