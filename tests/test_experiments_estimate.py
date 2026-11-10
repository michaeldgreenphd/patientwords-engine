"""Grid estimates: time from a supplied rate, logits storage, weight bytes.

Offline arithmetic only. Every expected number is worked out by hand in the comment beside it; none is produced
by the code under test. These tests show the formulas are applied as stated. They say nothing about how long a
real model run takes or how much memory it uses.
"""
from __future__ import annotations

import json

import pytest

from scripts import backfill_planner
from scripts.experiments import estimate
from scripts.experiments.common import Refusal
from scripts.experiments.planner import estimate_activation_bytes, estimate_fit_bytes


def refusal_code(call, *args, **kwargs) -> str:
    with pytest.raises(Refusal) as caught:
        call(*args, **kwargs)
    return caught.value.code


def test_recorded_rates_are_the_backfill_planners_and_carry_no_invented_sample_size():
    recorded = estimate.recorded_slowest_rates()
    assert recorded["seconds_per_pair"] == backfill_planner.SECONDS_PER_PAIR
    assert recorded["seconds_per_pair"] is not backfill_planner.SECONDS_PER_PAIR  # a copy, not the planner's dict
    assert backfill_planner.RATES_SOURCE in recorded["source"]
    assert recorded["leg_budget_seconds"] == backfill_planner.HALF_TIMEOUT_S == 7200
    assert recorded["n_samples"] is None  # not recorded in the source; missing stays missing


def test_attempted_units_rounds_the_allowance_up():
    assert estimate.attempted_units(20, 0.0) == 20
    assert estimate.attempted_units(20, 0.15) == 23     # 20 * 1.15 = 23.0
    assert estimate.attempted_units(1.5, 0.15) == 2     # 1.725 -> 2
    assert estimate.attempted_units(0, 0.5) == 0
    assert refusal_code(estimate.attempted_units, -1, 0.1) == "invalid_estimate_input"
    assert refusal_code(estimate.attempted_units, 1, float("nan")) == "invalid_estimate_input"


def test_cpu_logits_seconds_shows_its_arithmetic():
    # 20 families x 1 replicate x 2 prompts = 20 pairs; +15% -> 23 attempted pairs.
    # model-a: 23 * 100 s = 2,300 s; 7200 // 100 = 72 pairs per leg -> 1 leg.
    # model-b: 23 * 400 s = 9,200 s; 7200 // 400 = 18 pairs per leg -> ceil(23 / 18) = 2 legs.
    out = estimate.estimate_cpu_logits_seconds(20, {"model-b": 400.0, "model-a": 100.0}, failed_attempt_fraction=0.15,
                                               leg_budget_seconds=7200)
    assert out["pair_equivalents"] == 20
    assert out["attempted_pair_equivalents"] == 23
    assert list(out["per_model"]) == ["model-a", "model-b"]
    assert out["per_model"]["model-a"] == {"seconds_per_pair": 100.0, "runner_seconds": 2300.0, "pairs_per_leg": 72,
                                           "legs": 1}
    assert out["per_model"]["model-b"] == {"seconds_per_pair": 400.0, "runner_seconds": 9200.0, "pairs_per_leg": 18,
                                           "legs": 2}
    assert out["runner_seconds"] == 11500.0
    assert out["measured"] is False
    assert any("allowance" in line for line in out["assumptions"])


def test_three_variants_and_two_replicates_are_three_pair_equivalents_per_family():
    # 10 families x 2 replicates x 3 prompts / 2 = 30 pair-equivalents; no allowance; 30 * 50 s = 1,500 s.
    out = estimate.estimate_cpu_logits_seconds(10, {"m": 50}, replicates=2, prompts_per_family=3)
    assert out["pair_equivalents"] == 30
    assert out["runner_seconds"] == 1500
    assert "legs" not in out["per_model"]["m"]  # no leg budget given, so no leg count is invented


def test_a_rate_slower_than_the_leg_budget_still_gets_one_pair_per_leg():
    out = estimate.estimate_cpu_logits_seconds(3, {"m": 9000.0}, leg_budget_seconds=7200)
    assert out["per_model"]["m"]["pairs_per_leg"] == 1 and out["per_model"]["m"]["legs"] == 3


def test_legs_respect_the_backfill_planners_cap_on_pairs_per_fire(capsys):
    # Regression: 7200 // 44.0 = 163 pairs per leg for olmo-2-1b, so 150 pairs were printed as 1 leg, while
    # backfill_planner._rate_chunk caps a fire at 120 pairs and fires 2.
    recorded = estimate.recorded_slowest_rates()
    assert recorded["max_pairs_per_leg"] == backfill_planner.LOGITS_CHUNK_FAST == 120
    assert backfill_planner._rate_chunk("olmo-2-1b") == 120
    rates = {"olmo-2-1b": backfill_planner.SECONDS_PER_PAIR["olmo-2-1b"]}
    uncapped = estimate.estimate_cpu_logits_seconds(150, rates, leg_budget_seconds=7200)
    assert uncapped["per_model"]["olmo-2-1b"]["pairs_per_leg"] == 163 and uncapped["per_model"]["olmo-2-1b"]["legs"] == 1
    capped = estimate.estimate_cpu_logits_seconds(150, rates, leg_budget_seconds=7200, max_pairs_per_leg=120)
    # min(120, 163) = 120 pairs per leg; ceil(150 / 120) = 2 legs.
    assert capped["per_model"]["olmo-2-1b"] == {"seconds_per_pair": 44.0, "runner_seconds": 6600.0,
                                                "pairs_per_leg": 120, "legs": 2}
    assert "min(max_pairs_per_leg" in capped["formula"] and "min(max_pairs_per_leg" not in uncapped["formula"]
    # The command line applies the recorded cap, and every model's pairs per leg is the planner's own chunk.
    assert estimate.main(["--families", "150"]) == 0
    out = json.loads(capsys.readouterr().out)
    for model, entry in out["time"]["per_model"].items():
        assert entry["pairs_per_leg"] == backfill_planner._rate_chunk(model), model
    assert out["time"]["per_model"]["olmo-2-1b"]["legs"] == 2
    assert refusal_code(estimate.estimate_cpu_logits_seconds, 1, {"m": 1.0}, max_pairs_per_leg=120) == \
        "invalid_estimate_input"                                               # a cap needs a leg budget
    assert refusal_code(estimate.estimate_cpu_logits_seconds, 1, {"m": 1.0}, leg_budget_seconds=7200,
                        max_pairs_per_leg=0) == "invalid_estimate_input"


def test_cpu_logits_seconds_refuses_bad_inputs():
    call = estimate.estimate_cpu_logits_seconds
    assert refusal_code(call, 1, {}) == "invalid_estimate_input"
    assert refusal_code(call, 1, {"m": 0}) == "invalid_estimate_input"
    assert refusal_code(call, 1, {"m": True}) == "invalid_estimate_input"
    assert refusal_code(call, 1.5, {"m": 1.0}) == "invalid_estimate_input"
    assert refusal_code(call, 1, {"m": 1.0}, replicates=0) == "invalid_estimate_input"
    assert refusal_code(call, 1, {"m": 1.0}, leg_budget_seconds=0) == "invalid_estimate_input"


def test_logits_bytes_full_vocabulary_and_top_k():
    # 2 positions x 1,000 entries x 4 bytes = 8,000; bfloat16 halves it.
    assert estimate.estimate_logits_bytes(2, 1000, "float32") == 8000
    assert estimate.estimate_logits_bytes(2, 1000, "bfloat16") == 4000
    # top-10: 2 positions x 10 x (4-byte id + 4-byte value) = 160.
    assert estimate.estimate_logits_bytes(2, 1000, "float32", top_k=10) == 160
    assert estimate.estimate_logits_bytes(0, 1000, "float32") == 0
    assert refusal_code(estimate.estimate_logits_bytes, 1, 10, "float32", top_k=11) == "invalid_estimate_input"
    assert refusal_code(estimate.estimate_logits_bytes, 1, 10, "int8") == "unknown_dtype"


def test_weight_bytes():
    assert estimate.estimate_weight_bytes(1000, "bfloat16") == 2000
    assert estimate.estimate_weight_bytes(1000, "float32") == 4000
    assert refusal_code(estimate.estimate_weight_bytes, 0, "float32") == "invalid_estimate_input"
    assert refusal_code(estimate.estimate_weight_bytes, 10, "float8") == "unknown_dtype"


def test_grid_storage_uses_the_planners_activation_formula_and_keeps_missing_vocabulary_missing():
    # 5 families x 1 replicate x 3 prompts = 15 prompts; x 8 tokens = 120 tokens.
    # all positions: 120 x 2 layers x 16 wide x 4 bytes = 15,360. last position: 15 x 2 x 16 x 4 = 1,920.
    out = estimate.estimate_grid_storage(5, replicates=1, prompts_per_family=3, tokens_per_prompt=8, layers=2,
                                         hidden_size=16, dtype="float32")
    assert out["prompts"] == 15 and out["tokens"] == 120
    assert out["activation_bytes_all_positions"] == 15360 == estimate_activation_bytes(120, 2, 16, "float32")
    assert out["activation_bytes_last_position"] == 1920
    assert out["logits_bytes_last_position_full_vocab"] is None  # no vocabulary given: missing, not zero
    assert out["logits_bytes_last_position_top_k"] is None
    with_vocab = estimate.estimate_grid_storage(5, replicates=1, prompts_per_family=3, tokens_per_prompt=8, layers=2,
                                                hidden_size=16, dtype="float32", vocab_size=100, top_k=5)
    assert with_vocab["logits_bytes_last_position_full_vocab"] == 6000  # 15 x 100 x 4
    assert with_vocab["logits_bytes_last_position_top_k"] == 600        # 15 x 5 x 8
    assert with_vocab["measured"] is False


def test_cli_prints_json_and_refuses_with_exit_2(capsys):
    assert estimate.main(["--families", "20", "--rate", "model-a=100", "--failed-attempt-fraction", "0.15",
                          "--tokens-per-prompt", "8", "--layers", "2", "--hidden-size", "16", "--fit-samples",
                          "50"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["rates_source"] == "command line (--rate)"
    assert out["time"]["runner_seconds"] == 2300.0
    assert out["time"]["per_model"]["model-a"]["legs"] == 1
    assert out["storage"]["activation_bytes_last_position"] == 40 * 2 * 16 * 4
    # fit workspace from the planner: 4 x (2 x 50 x 16 + 3 x 16^2) = 4 x (1,600 + 768) = 9,472.
    assert out["fit_bytes"] == 9472 == estimate_fit_bytes(50, 16, "float32")

    assert estimate.main(["--families", "1", "--rate", "model-a"]) == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == "refused" and refused["code"] == "invalid_estimate_input"


def test_cli_default_rates_are_the_recorded_ones(capsys):
    assert estimate.main(["--families", "1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["time"]["per_model"]) == set(backfill_planner.SECONDS_PER_PAIR)
    assert "SECONDS_PER_PAIR" in out["rates_source"]
    # one pair per model, no allowance: the total is the sum of the recorded rates.
    assert out["time"]["runner_seconds"] == pytest.approx(sum(backfill_planner.SECONDS_PER_PAIR.values()))
