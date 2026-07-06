import json

import pytest
from conftest import build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval
import medlang_circuits.scenario_gen as scenario_gen
from medlang_circuits.scenario_gen import (
    dialect_batch_item,
    ends_at_probe_boundary,
    generate_dialect_variants,
    generate_stress_pairs,
    import_sheet,
    single_span_swap,
    validate_dialect_variant,
    validate_stress_pair,
)

# Abstract placeholder pair (real vocabulary lives in data files, never here).
VALID_CANDIDATE = {
    "patient_prompt": "I caught the alpha at work, so I need to talk to a",
    "clinical_prompt": "I caught beta gamma at work, so I need to talk to a",
    "patient_term": "the alpha",
    "clinical_term": "beta gamma",
    "expected_clinical_continuations": ["delta", "epsilon"],
    "rationale": "mundane vs. care-seeking continuation",
}


def _fake_call_returning(responses):
    """A scenario_gen._call stand-in that pops canned response texts in order."""
    queue = list(responses)
    calls = []

    def fake_call(client, model, system, prompt, max_tokens=200):
        calls.append({"model": model, "system": system, "prompt": prompt})
        return queue.pop(0), 100, 100

    return fake_call, calls


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def test_probe_boundary():
    assert ends_at_probe_boundary("so I need to talk to a")
    assert ends_at_probe_boundary("so I should take some ")  # trailing space tolerated
    assert not ends_at_probe_boundary("so I need to talk to a doctor.")
    assert not ends_at_probe_boundary("really?")
    assert not ends_at_probe_boundary("")
    assert not ends_at_probe_boundary(None)


def test_single_span_swap_accepts_one_contiguous_replacement():
    spans = single_span_swap(
        "I caught the alpha at work, so I need to talk to a",
        "I caught beta gamma at work, so I need to talk to a",
    )
    assert spans == {"patient_span": "the alpha", "clinical_span": "beta gamma"}


def test_single_span_swap_rejects_multi_span_and_identical():
    # two separated edits -> reject (same single-swap property as the hand-built set)
    assert single_span_swap(
        "I caught the alpha at work, so I must talk to a",
        "I caught beta gamma at work, so I need to talk to a",
    ) is None
    # identical prompts -> nothing swapped -> reject
    assert single_span_swap("the same frame", "the same frame") is None


@pytest.mark.parametrize("mutate,reason_part", [
    (lambda c: c.pop("patient_term"), "missing keys"),
    (lambda c: c.update(expected_clinical_continuations=["  "]), "non-empty list"),
    (lambda c: c.update(clinical_prompt=c["clinical_prompt"] + "."), "probe boundary"),
    (lambda c: c.update(patient_prompt="I caught the alpha at home, so I must talk to a"),
     "single contiguous term span"),
    (lambda c: c.update(patient_term="zeta"), "does not appear"),
])
def test_validate_stress_pair_rejections(mutate, reason_part):
    candidate = json.loads(json.dumps(VALID_CANDIDATE))
    mutate(candidate)
    pair, reason = validate_stress_pair(candidate, set())
    assert pair is None
    assert reason_part in reason


def test_validate_stress_pair_accepts_and_dedupes():
    seen = set()
    pair, reason = validate_stress_pair(dict(VALID_CANDIDATE), seen)
    assert reason is None
    assert pair["top_prompt"] == VALID_CANDIDATE["clinical_prompt"]
    assert pair["bottom_prompt"] == VALID_CANDIDATE["patient_prompt"]
    assert pair["target_clinical_token"] == " delta"  # first expected continuation
    assert pair["generation"]["swap_spans"] == {"patient_span": "the alpha", "clinical_span": "beta gamma"}
    # the same candidate again is now a duplicate
    dup, reason = validate_stress_pair(dict(VALID_CANDIDATE), seen)
    assert dup is None and "duplicate" in reason


def test_validate_dialect_variant():
    seen = set()
    ok, reason = validate_dialect_variant(
        {"dialect": "Variant One", "prompt": "me beta been acting up, so I gone see my"}, "beta", seen)
    assert reason is None and ok["dialect"] == "Variant One"
    for candidate, part in [
        ({"dialect": "X", "prompt": "the gamma is acting up, so I will see my"}, "verbatim"),
        ({"dialect": "X", "prompt": "the beta is acting up, so I will see my GP."}, "probe boundary"),
        ({"dialect": "", "prompt": "the beta is acting up, so I will see my"}, "dialect label"),
        ({"dialect": "Y", "prompt": "me beta been acting up, so I gone see my"}, "duplicate"),
    ]:
        rejected, reason = validate_dialect_variant(candidate, "beta", seen)
        assert rejected is None and part in reason


# ---------------------------------------------------------------------------
# Generators (offline: monkeypatched _call, no network)
# ---------------------------------------------------------------------------


VALID_QUADRANT = {
    "standard_frame": "I have{term}, and I feel really unwell. I should go to",
    "nonstandard_frame": "I been had{term}, and I been feeling really unwell. I should go to",
    "medical_term": "alpha",
    "patient_term": "the beta",
    "expected_clinical_continuations": ["gamma"],
    "rationale": "prestige vs shifted axes",
}


@pytest.mark.parametrize("mutate,reason_part", [
    (lambda c: c.pop("medical_term"), "missing keys"),
    (lambda c: c.update(standard_frame="I have {term} twice {term} so I go to"), "exactly once"),
    (lambda c: c.update(nonstandard_frame=c["nonstandard_frame"] + "."), "probe boundary"),
    (lambda c: c.update(nonstandard_frame=c["standard_frame"]), "no morphosyntax shift"),
    (lambda c: c.update(patient_term=" Alpha "), "no lexicon shift"),
    (lambda c: c.update(expected_clinical_continuations=[" "]), "non-empty list"),
])
def test_validate_quadrant_item_rejections(mutate, reason_part):
    candidate = dict(VALID_QUADRANT)
    mutate(candidate)
    item, reason = scenario_gen.validate_quadrant_item(candidate, set())
    assert item is None
    assert reason_part in reason


def test_validate_quadrant_item_accepts_composes_and_dedupes():
    seen = set()
    item, reason = scenario_gen.validate_quadrant_item(dict(VALID_QUADRANT), seen)
    assert reason is None
    # batch-ready --mode 4quadrant shape, terms carrying their leading space
    assert item["frames"]["standard"].endswith("go to")
    assert item["terms"] == {"medical": " alpha", "patient": " the beta"}
    assert item["target_clinical_token"] == " gamma"
    quads = item["generation"]["quadrants"]
    assert quads["A"] == "I have alpha, and I feel really unwell. I should go to"
    assert quads["D"] == "I been had the beta, and I been feeling really unwell. I should go to"
    # identical resubmission is a duplicate
    dup, reason = scenario_gen.validate_quadrant_item(dict(VALID_QUADRANT), seen)
    assert dup is None and reason == "duplicate of a seed or an already-accepted item"


def test_generate_quadrant_scenarios_offline(monkeypatch):
    fake_call, calls = _fake_call_returning([json.dumps([VALID_QUADRANT])])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)
    seeds = [{
        "frames": {"clinical": "I have{term}, so the fox goes to", "patient": "I got{term}, so the fox goes to"},
        "terms": {"clinical": " delta", "patient": " the epsilon"},
        "target_clinical_token": " zeta",
    }]
    result = scenario_gen.generate_quadrant_scenarios(1, seed_pairs=seeds, topics=["everyday life"],
                                                      max_spend=1.0, client=object())
    assert len(result["pairs"]) == 1
    assert result["pairs"][0]["generation"]["topics"] == ["everyday life"]
    assert result["rejected"] == []
    # seeds ride along as few-shot examples and dedupe context
    assert "delta" in calls[0]["prompt"]
    assert "everyday life" in calls[0]["prompt"]
    assert "morphosyntax" in calls[0]["system"]


def test_parse_json_array_salvages_truncated_output():
    items = [dict(VALID_CANDIDATE), dict(VALID_CANDIDATE)]
    full = json.dumps(items, indent=2)
    assert scenario_gen._parse_json_array(full) == items
    # a max_tokens cutoff mid-second-object keeps the complete first object
    truncated = full[: full.rfind('"rationale"')]
    assert scenario_gen._parse_json_array(truncated) == [VALID_CANDIDATE]
    assert scenario_gen._parse_json_array("no json here") == []


def test_generate_stress_pairs_offline(monkeypatch):
    second_valid = dict(VALID_CANDIDATE)
    second_valid.update(
        patient_prompt="Since her zeta was flaring up, she went to grab her",
        clinical_prompt="Since her eta theta was flaring up, she went to grab her",
        patient_term="zeta", clinical_term="eta theta",
        expected_clinical_continuations=["iota"],
    )
    multi_span = dict(VALID_CANDIDATE)
    multi_span["patient_prompt"] = "I caught the alpha at home, so I must talk to a"
    punct = dict(second_valid)
    punct["clinical_prompt"] = punct["clinical_prompt"] + "."

    fake_call, calls = _fake_call_returning([
        json.dumps([VALID_CANDIDATE, multi_span, dict(VALID_CANDIDATE)]),  # valid, reject, duplicate
        json.dumps([punct, second_valid]),  # reject, valid
    ])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)

    result = generate_stress_pairs(2, model="claude-haiku-4-5", client=object())
    assert [p["target_clinical_token"] for p in result["pairs"]] == [" delta", " iota"]
    assert result["rounds"] == 2
    assert not result["truncated"]
    reasons = [r["reason"] for r in result["rejected"]]
    assert any("single contiguous" in r for r in reasons)
    assert any("duplicate" in r for r in reasons)
    assert any("probe boundary" in r for r in reasons)
    assert result["usage"]["total_cost_usd"] > 0
    assert calls[0]["model"] == "claude-haiku-4-5"
    # the system prompt states the generation rules explicitly
    for phrase in ("IDENTICAL syntactic frame", "contiguous term span", "probe point",
                   "terminal punctuation", "diagnostic", "STRICT JSON"):
        assert phrase in calls[0]["system"]


def test_generate_stress_pairs_seeds_few_shot_and_dedupe(monkeypatch):
    seed = {  # batch schema, as written by a previous run / the importer
        "top_prompt": VALID_CANDIDATE["clinical_prompt"],
        "bottom_prompt": VALID_CANDIDATE["patient_prompt"],
        "target_clinical_token": " delta",
    }
    fake_call, calls = _fake_call_returning([json.dumps([VALID_CANDIDATE])] * 6)
    monkeypatch.setattr(scenario_gen, "_call", fake_call)

    result = generate_stress_pairs(1, seed_pairs=[seed], client=object())
    # the only candidate duplicates the seed, so nothing is ever accepted
    assert result["pairs"] == []
    assert all("duplicate" in r["reason"] for r in result["rejected"])
    # seeds are few-shot examples in the user message
    assert VALID_CANDIDATE["patient_prompt"] in calls[0]["prompt"]


def test_generate_stress_pairs_remaps_legacy_model_names(monkeypatch):
    fake_call, calls = _fake_call_returning([json.dumps([VALID_CANDIDATE])])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)
    result = generate_stress_pairs(1, model="claude-3-5-sonnet", client=object())
    assert calls[0]["model"] == "claude-sonnet-5"  # retired name remapped, not 404ing at the API
    assert result["model"] == "claude-sonnet-5"


def test_generate_stress_pairs_feedback_counterexamples(monkeypatch):
    fake_call, calls = _fake_call_returning([json.dumps([VALID_CANDIDATE])])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)
    feedback = [{"clinical_prompt": "a frame that failed", "intended_target": " delta",
                 "observed_top": [["mundane", 0.4]]}]
    result = scenario_gen.generate_stress_pairs(1, feedback=feedback, max_spend=1.0, client=object())
    assert len(result["pairs"]) == 1
    assert "MEASUREMENT-SCREENING FAILURES" in calls[0]["prompt"]
    assert "a frame that failed" in calls[0]["prompt"]


def test_generate_stress_pairs_topics_recorded(monkeypatch):
    fake_call, calls = _fake_call_returning([json.dumps([VALID_CANDIDATE])])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)
    result = generate_stress_pairs(1, topics=["topic one", "topic two"], client=object())
    assert "topic one, topic two" in calls[0]["prompt"]  # steering reaches the model
    assert result["pairs"][0]["generation"]["topics"] == ["topic one", "topic two"]
    assert result["topics"] == ["topic one", "topic two"]


def test_pairs_cli_writes_cost_report_sidecar(tmp_path, monkeypatch, capsys):
    fake_call, calls = _fake_call_returning([json.dumps([VALID_CANDIDATE])])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)
    monkeypatch.setattr(scenario_gen, "_get_client", lambda: object())

    out = tmp_path / "pairs_test.json"
    rc = scenario_gen.main(["pairs", "-n", "1", "--max-spend", "1.5",
                            "--topics", "topic one", "--out", str(out)])
    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["report"] == str(tmp_path / "pairs_test.report.json")

    report = json.loads((tmp_path / "pairs_test.report.json").read_text(encoding="utf-8"))
    assert report["task"] == "pairs"
    assert report["accepted"] == 1 and report["rejected"] == 0
    assert report["max_spend_usd"] == 1.5
    assert report["cost_usd"] > 0
    assert report["cost_usd"] == report["usage"]["total_cost_usd"]
    assert report["language_register"] == "general_patient_language"
    assert report["topics"] == ["topic one"]
    assert report["batch_file"] == str(out)
    assert "run_timestamp" in report


def test_generate_stress_pairs_budget_ceiling(monkeypatch):
    fake_call, calls = _fake_call_returning([json.dumps([VALID_CANDIDATE])])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)
    result = generate_stress_pairs(5, max_spend=0.0, client=object())
    assert result["pairs"] == [] and result["truncated"] is True
    assert calls == []  # no call was affordable


def test_generate_dialect_variants_offline(monkeypatch):
    fake_call, calls = _fake_call_returning([
        json.dumps([
            {"dialect": "Variant One", "prompt": "me beta been acting up, so I gone see my"},
            {"dialect": "Variant Two", "prompt": "the beta is acting up, so I will see my GP."},
            {"dialect": "Variant Three", "prompt": "the gamma is acting up, so I will see my"},
        ]),
        json.dumps([
            {"dialect": "Variant Four", "prompt": "beta acting up again so imma go see my"},
        ]),
    ])
    monkeypatch.setattr(scenario_gen, "_call", fake_call)

    result = generate_dialect_variants(
        "Since the beta was acting up, I went to see my", "beta", 2, client=object())
    assert [v["dialect"] for v in result["variants"]] == ["Variant One", "Variant Four"]
    assert result["held_fixed"] == "clinical"
    reasons = [r["reason"] for r in result["rejected"]]
    assert any("probe boundary" in r for r in reasons)
    assert any("verbatim" in r for r in reasons)
    # the system prompt states the dialect requirements explicitly
    for phrase in ("authentic and respectful", "no caricature", "UNCHANGED, verbatim",
                   "probe boundary", "STRICT JSON"):
        assert phrase in calls[0]["system"]
    # the fixed term and its direction are in the user message
    assert "'beta'" in calls[0]["prompt"] and "clinical wording" in calls[0]["prompt"]

    item = dialect_batch_item(result, target_token=" iota")
    assert item["baseline_prompt"].startswith("Since the beta")
    assert item["target_clinical_token"] == " iota"
    assert len(item["variants"]) == 2


def test_generate_dialect_variants_input_validation():
    with pytest.raises(ValueError, match="verbatim"):
        generate_dialect_variants("no such term here", "beta", 2, client=object())
    with pytest.raises(ValueError, match="held_fixed"):
        generate_dialect_variants("the beta frame", "beta", 2, held_fixed="other", client=object())


# ---------------------------------------------------------------------------
# Spreadsheet importer (CSV fixture with abstract placeholder phrases)
# ---------------------------------------------------------------------------


def _write_fixture_csv(path):
    rows = [
        ["Phrase 1", "Next token", "Prob", "Link to Circuit Tracer", "Phrase 2", "", "",
         "Link to Circuit Tracer", "Notes", "sourcing"],
        ["I grabbed the alpha, so I need to talk to a", "delta ", "0.26",
         "https://www.neuronpedia.org/m/graph?slug=aaa",
         "I grabbed beta gamma, so I need to talk to a", "epsilon", "0.31",
         "https://www.neuronpedia.org/m/graph?slug=bbb", "all suggestions shift", "src1"],
        # link parked in the Next-token column; tokens/probs/second link missing
        ["He mispleled the alpha, so he should call a",
         "https://www.neuronpedia.org/m/graph?slug=ccc", "", "",
         "He mispleled beta gamma, so he should call a", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", ""],  # fully empty
        ["only one phrase present", "", "", "", "", "", "", "", "", ""],  # no Phrase 2
        ["model-z transcoder 16k set", "", "", "", "", "", "", "", "", ""],  # trailing metadata
    ]
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_import_sheet_csv(tmp_path):
    sheet = tmp_path / "dataset.csv"
    _write_fixture_csv(sheet)
    pairs = import_sheet(sheet)
    assert len(pairs) == 2

    anchored, unanchored = pairs
    assert anchored["top_prompt"] == "I grabbed beta gamma, so I need to talk to a"
    assert anchored["bottom_prompt"] == "I grabbed the alpha, so I need to talk to a"
    assert anchored["target_clinical_token"] == " epsilon"  # token whitespace stripped
    prov = anchored["provenance"]
    assert prov["patient"] == {"observed_next_token": "delta", "observed_prob": 0.26,
                               "circuit_link": "https://www.neuronpedia.org/m/graph?slug=aaa"}
    assert prov["clinical"]["observed_prob"] == 0.31
    assert prov["notes"] == "all suggestions shift" and prov["sourcing"] == "src1"

    # missing next token -> unanchored (top-logit fallback); link found despite the column
    assert "target_clinical_token" not in unanchored
    assert unanchored["provenance"]["patient"]["circuit_link"] == "https://www.neuronpedia.org/m/graph?slug=ccc"
    assert unanchored["provenance"]["patient"]["observed_next_token"] is None
    # verbatim preservation, intentional misspelling included
    assert "mispleled" in unanchored["bottom_prompt"] and "mispleled" in unanchored["top_prompt"]


def test_import_sheet_cli(tmp_path, capsys):
    sheet = tmp_path / "dataset.csv"
    _write_fixture_csv(sheet)
    out = tmp_path / "imported.json"
    assert scenario_gen.main(["import-sheet", str(sheet), "--out", str(out)]) == 0
    capsys.readouterr()
    pairs = json.loads(out.read_text(encoding="utf-8"))
    assert len(pairs) == 2 and pairs[0]["provenance"]["source_row"] == 2


# ---------------------------------------------------------------------------
# --mode dialect end-to-end (synthetic graphs, monkeypatched generation)
# ---------------------------------------------------------------------------


def _two_logit_graph():
    g = make_graph()
    g["nodes"].append({"node_id": "L_a", "feature": 1000, "layer": "26", "ctx_idx": 3,
                       "feature_type": "logit", "jsNodeId": "L_a-3", "clerp": "a (p=0.9)"})
    g["links"].append({"source": "7_00007_2", "target": "L_a", "weight": 3.0})
    return g


def test_run_batch_dialect_offline(tmp_path, monkeypatch):
    def fake_generate(prompt, slug=None, backend="hosted", **params):
        g = _two_logit_graph()
        p = 0.81 if "clinical" in prompt else (0.4 if "patient" in prompt else 0.6)
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(json.dumps([{
        "baseline_prompt": "clinical phrasing about the fox",
        "target_clinical_token": " jumps",
        "held_fixed": "clinical",
        "term": "fox",
        "variants": [
            {"dialect": "Variant One", "prompt": "patient phrasing about the fox"},
            {"dialect": "Variant Two", "prompt": "other phrasing about the fox"},
        ],
    }]), encoding="utf-8")

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), mode="dialect", dpi=50, fetcher=build_fetcher())
    r = results[0]
    assert r["mode"] == "dialect"
    assert r["target_token"] == "jumps"
    assert r["baseline_probability"] == 0.81
    assert [v["probability"] for v in r["variants"]] == [0.4, 0.6]
    assert r["variants"][0]["delta_vs_baseline"] == pytest.approx(-0.41)
    assert r["variants"][1]["delta_vs_baseline"] == pytest.approx(-0.21)
    assert r["predictive_spread"]["baseline"] == [("a", 0.9), ("jumps", 0.81)]

    out = tmp_path / "out"
    for name in ("pair_01_baseline", "pair_01_variant_01", "pair_01_variant_02"):
        assert (out / f"{name}.tagged.json").is_file()
    assert (out / "index_01.png").stat().st_size > 1000

    html = (out / "index_01.html").read_text(encoding="utf-8")
    assert html.count('<g transform="translate(0,') == 3  # baseline + one panel per variant
    assert "Baseline (standard phrasing)" in html
    assert "Variant One" in html and "Variant Two" in html
    assert "Dialect Δ vs. baseline (Variant One): -41% probability (0.81 → 0.40)" in html
    assert "Dialect Δ vs. baseline (Variant Two): -21% probability (0.81 → 0.60)" in html

    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "dialect"


def test_run_batch_dialect_top_logit_fallback_and_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "generate_graph",
                        lambda prompt, slug=None, backend="hosted", **params: _two_logit_graph())
    pairs = tmp_path / "pairs.json"
    pairs.write_text(json.dumps([{
        "baseline_prompt": "one phrasing of the fox",
        "variants": [{"dialect": "Variant One", "prompt": "another phrasing of the fox"}],
    }]), encoding="utf-8")
    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), mode="dialect", dpi=50, fetcher=build_fetcher())
    # no target token given -> the baseline's top logit anchors the comparison
    assert results[0]["target_token"] == "a"
    assert results[0]["baseline_probability"] == 0.9

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"baseline_prompt": "no variants here"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="variants"):
        batch_eval.run_batch(str(bad), out_dir=str(tmp_path / "out2"), mode="dialect",
                             dpi=50, fetcher=build_fetcher())
