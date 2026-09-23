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
