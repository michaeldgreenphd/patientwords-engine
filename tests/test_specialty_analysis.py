"""Coverage gaps + exploratory specialty breakdown (abstract placeholder data)."""
from scripts.coverage_gaps import build, topic_lookup
from scripts.specialty_breakdown import penalties_by_specialty

MAP = {"specialties": {
    "Alpha": {"Sub1": ["zeta wobble", "zeta twinge"], "Sub2": ["zeta drift"]},
    "Beta": {"Sub3": ["kappa chill"]},
}}


def scen(topic, batch="b1", idx=1, pc=None, pp=None, models=None):
    s = {"topic": topic, "batch": batch, "batch_index": idx}
    if pc is not None:
        s["prob_clinical"], s["prob_patient"] = pc, pp
    if models:
        s["models"] = models
    s["prompts"] = {"clinical": f"{topic}-{batch}-{idx}"}
    return s


def test_topic_lookup_flattens_taxonomy():
    lk = topic_lookup(MAP)
    assert lk["zeta drift"] == ("Alpha", "Sub2")
    assert len(lk) == 4


def test_coverage_counts_and_steering():
    scenarios = [scen("zeta wobble", idx=i) for i in range(5)] + [scen("kappa chill", idx=9)]
    urg = [{"batch": "b1", "index": 9, "model": "gemma-2-2b", "tier_top_clinical": 3}]
    out = build(MAP, scenarios, urg, "gemma-2-2b", steer_n=2, thin_threshold=3)
    assert out["per_specialty"] == {"Alpha": 5, "Beta": 1}
    assert out["tier_matrix"] == {"Beta": {"3": 1}}
    assert out["thin_specialties"] == ["Beta"]
    # steering lists the thin specialty's full topic vocabulary
    assert out["steer_topics"] == {"Beta": ["kappa chill"]}


def test_unmapped_topics_bucket_to_other():
    out = build(MAP, [scen("unknown thing")], [], "gemma-2-2b", 2, 3)
    assert out["per_specialty"] == {"Other": 1}
    assert "Other" not in out["thin_specialties"]  # never steer toward Other


def test_breakdown_dedupes_and_groups():
    scenarios = [
        scen("zeta wobble", idx=1, pc=0.6, pp=0.4),
        scen("zeta wobble", idx=1, pc=0.6, pp=0.4),   # same phrase re-traced: one record
        scen("kappa chill", idx=2, pc=0.3, pp=0.5,
             models={"qwen3-4b": {"prob_clinical": 0.4, "prob_patient": 0.1}}),
    ]
    urg = [{"batch": "b1", "index": 2, "model": "qwen3-4b", "flip_class": "downgrade"}]
    table = penalties_by_specialty(MAP, scenarios, urg)
    assert table["Alpha"]["gemma-2-2b"] == {"n_phrases": 1, "mean_penalty": -0.2, "downgrades": 0}
    assert table["Beta"]["gemma-2-2b"]["mean_penalty"] == 0.2
    assert table["Beta"]["qwen3-4b"] == {"n_phrases": 1, "mean_penalty": -0.3, "downgrades": 1}
