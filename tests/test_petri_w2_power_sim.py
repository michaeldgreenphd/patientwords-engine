"""The wave-2 design simulation's tests and its reproducibility (docs/petri_wave2_design.md §10)."""
import json
import random

from scripts import petri_w2_power_sim as sim


def test_sign_test_matches_the_thresholds_the_plan_quotes():
    # §10.2: at 35 non-tied triples 24 of one sign is significant and 23 is not; at 20, 15 and 14
    assert sim.sign_test_p(24, 35) < 0.05 < sim.sign_test_p(23, 35)
    assert sim.sign_test_p(15, 20) < 0.05 < sim.sign_test_p(14, 20)
    assert sim.sign_test_p(0, 0) == 1.0
    assert sim.sign_test_p(3, 6) == 1.0


def test_sign_flip_test_is_exact_and_symmetric():
    # eight scenario means all of one sign reach the test's floor, 2/256
    assert sim.sign_flip_p([-0.1] * 8) == 2 / 256
    assert sim.sign_flip_p([0.1] * 8) == 2 / 256
    means = [-0.3, -0.1, 0.05, -0.2, -0.15, 0.1, -0.05, -0.25]
    assert sim.sign_flip_p(means) == sim.sign_flip_p([-m for m in means])


def test_the_output_records_its_seed_and_is_reproducible(capsys):
    assert sim.main(["--seed", "7", "--sims", "40"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert sim.main(["--seed", "7", "--sims", "40"]) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert first["seed"] == 7 and first["triples_per_scenario"] == [4, 4, 4, 8, 3, 3, 3, 6]


def test_a_conversation_with_no_change_scores_zero():
    assert sim.conversation_d(random.Random(1), 0.0, 0.0, 0.5) == 0.0


class _FixedGauss:
    """A stand-in RNG whose gauss() returns preset deviations, so the clip can be checked exactly."""

    def __init__(self, deviations):
        self._deviations = list(deviations)

    def gauss(self, mu, sigma):
        return self._deviations.pop(0)


def test_scenario_effects_are_clipped_symmetrically_about_the_stated_mean():
    # Codex, PR #29: clipping at zero alone lifted E[pd_s] above pd, so the "null" row carried a real shift.
    # For every deviation z, pd_s(z) and pd_s(-z) must sit symmetrically about pd and inside [0, 1 - pu].
    for z in (0.0, 0.05, 0.1, 0.3, 2.0):
        rng = _FixedGauss([z, -z])
        up, down = sim.scenario_pd(rng, 0.10, 0.10, 0.10), sim.scenario_pd(rng, 0.10, 0.10, 0.10)
        assert abs((up + down) - 0.20) < 1e-12
        assert 0.0 <= down <= up <= 0.90


def test_the_heterogeneous_null_is_centred():
    rng = random.Random(20260923)
    draws = [sim.scenario_pd(rng, 0.10, 0.10, 0.10) for _ in range(200_000)]
    # the old max(0, .) clip gave about 0.1083 here; the standard error of this mean is about 0.00015
    assert abs(sum(draws) / len(draws) - 0.10) < 0.001


def test_an_impossible_probability_pair_is_refused():
    import pytest

    with pytest.raises(ValueError):
        sim.scenario_pd(random.Random(1), 0.6, 0.5, 0.1)


def test_the_output_states_how_scenario_effects_are_drawn(capsys):
    assert sim.main(["--seed", "7", "--sims", "5"]) == 0
    assert "symmetric" in json.loads(capsys.readouterr().out)["scenario_heterogeneity"]
