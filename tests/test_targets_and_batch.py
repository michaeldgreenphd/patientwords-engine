import json

import pytest
from conftest import TEST_KEYWORD_CONFIG, build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval
from medlang_circuits.targets import (
    AttributionTargets,
    logit_spread,
    parse_logit_clerp,
    retarget_graph,
    select_logits,
    target_probability,
)


def _two_logit_graph():
    """Fixture graph plus a second, higher-probability article logit ('a')."""
    g = make_graph()
    g["nodes"].append({"node_id": "L_a", "feature": 1000, "layer": "26", "ctx_idx": 3,
                       "feature_type": "logit", "jsNodeId": "L_a-3", "clerp": "a (p=0.9)"})
    g["links"].append({"source": "7_00007_2", "target": "L_a", "weight": 3.0})
    return g


def test_parse_logit_clerp():
    assert parse_logit_clerp("therapist (p=0.62)") == ("therapist", 0.62)
    assert parse_logit_clerp("plain label") == ("plain label", None)
    assert parse_logit_clerp(None) == ("", None)


def test_retarget_graph_prunes_other_logits():
    g = _two_logit_graph()
    info = retarget_graph(g, AttributionTargets.of([" jumps"]))
    assert info["retargeted"] is True
    ids = {n["node_id"] for n in g["nodes"]}
    assert "L_999_3" in ids and "L_a" not in ids  # substantive target kept, article dropped
    assert all(link["target"] != "L_a" for link in g["links"])  # dangling edges pruned
    assert g["metadata"]["attribution_targets"]["dropped"] == ["a (p=0.9)"]


def test_retarget_no_match_leaves_graph_untouched():
    g = _two_logit_graph()
    n_nodes, n_links = len(g["nodes"]), len(g["links"])
    info = retarget_graph(g, AttributionTargets.of([" zebra"]))
    assert info["retargeted"] is False
    assert len(g["nodes"]) == n_nodes and len(g["links"]) == n_links


def test_target_probability_selection():
    g = _two_logit_graph()
    assert target_probability(g) == ("a", 0.9)  # top logit is the article
    assert target_probability(g, anchor=" jumps") == ("jumps", 0.81)
    assert target_probability(g, targets=AttributionTargets.of([" jumps"])) == ("jumps", 0.81)
    assert target_probability(g, anchor=" zebra") is None


def test_logit_spread_and_select_logits():
    g = _two_logit_graph()
    assert logit_spread(g) == [("a", 0.9), ("jumps", 0.81)]
    assert logit_spread(g, k=1) == [("a", 0.9)]

    # top-k pruning alone drops the weaker logit
    g1 = _two_logit_graph()
    info = select_logits(g1, keep_top_k=1)
    assert info["dropped"] == ["jumps (p=0.81)"]
    assert "L_999_3" not in {n["node_id"] for n in g1["nodes"]}

    # forced targets are kept in addition to the top-k spread
    g2 = _two_logit_graph()
    info = select_logits(g2, targets=AttributionTargets.of([" jumps"]), keep_top_k=1)
    assert info["dropped"] == []
    assert {n["node_id"] for n in g2["nodes"] if n["feature_type"] == "logit"} == {"L_999_3", "L_a"}
    assert g2["metadata"]["logit_selection"]["requested_targets"] == [" jumps"]


def test_run_batch_offline_with_mitigation(tmp_path, monkeypatch):
    # offline phrase table so the mitigation step restores the clinical phrasing
    config = tmp_path / "keyword_config.json"
    config.write_text(
        json.dumps({**TEST_KEYWORD_CONFIG, "translations": {"patient phrasing": "clinical phrasing"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(config))

    calls = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        calls.append({"prompt": prompt, "params": params})
        g = _two_logit_graph()
        p = 0.81 if "clinical" in prompt else 0.4  # patient phrasing degrades the target token
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)

    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{
            "top_prompt": "clinical phrasing about the fox",
            "bottom_prompt": "patient phrasing about the fox",
            "target_clinical_token": " jumps",
            "force_target_tokens": [" jumps"],
        }]),
        encoding="utf-8",
    )

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"),
        show_mitigation=True, use_llm_translation=False, dpi=60, fetcher=build_fetcher(),
    )

    assert len(results) == 1
    r = results[0]
    assert r["target_token"] == "jumps"
    assert r["probabilities"] == {"clinical": 0.81, "patient": 0.4, "translated": 0.81}
    assert r["language_penalty"] == pytest.approx(-0.41)
    assert r["mitigation_recovery"] == pytest.approx(0.41)
    assert r["translation_method"] == "phrase_table"
    # forced targets widen the salient-logit set and pass through to generation
    assert calls[0]["params"]["max_n_logits"] == 15
    assert calls[0]["params"]["force_target_tokens"] == [" jumps"]
    assert len(calls) == 3  # clinical, patient, translated

    out = tmp_path / "out"
    assert (out / "index_01.png").stat().st_size > 1000
    assert (out / "batch_summary.json").is_file()
    assert (out / "pair_01_translated.tagged.json").is_file()

    html = (out / "index_01.html").read_text(encoding="utf-8")
    # three stacked panels with both delta badges centered in the gaps
    assert html.count('<g transform="translate(0,') == 3
    assert "Language Penalty: -41% probability (0.81 → 0.40)" in html
    assert "Mitigation Recovery: +41% probability (0.40 → 0.81)" in html
    # the predictive spread keeps the article logit visible (prob notation, no p= syntax)
    assert "a · prob 0.90" in html
    assert "jumps · prob 0.81" in html
    assert r["predictive_spread"]["clinical"] == [("a", 0.9), ("jumps", 0.81)]
    assert r["predictive_spread"]["patient"] == [("a", 0.9), ("jumps", 0.4)]


def test_run_batch_quadrant_offline(tmp_path, monkeypatch):
    def fake_generate(prompt, slug=None, backend="hosted", **params):
        g = _two_logit_graph()
        p = 0.86
        if "blues" in prompt:
            p -= 0.40  # vocabulary effect
        if "'ve got" in prompt:
            p -= 0.08  # syntax effect
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p:.2f})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{
            "frames": {"clinical": "I have{term}, so the fox", "patient": "I've got{term}, so the fox"},
            "terms": {"clinical": " depression", "patient": " the blues"},
            "target_clinical_token": " jumps",
        }]),
        encoding="utf-8",
    )

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), mode="4quadrant", dpi=50, fetcher=build_fetcher()
    )
    r = results[0]
    assert r["mode"] == "4quadrant"
    assert r["prompts"]["C"] == "I've got depression, so the fox"  # patient frame + clinical term
    assert r["probabilities"] == {"A": 0.86, "B": 0.46, "C": 0.78, "D": 0.38}
    assert r["vocabulary_deltas"]["clinical_frame"] == pytest.approx(-0.40)
    assert r["vocabulary_deltas"]["patient_frame"] == pytest.approx(-0.40)
    assert r["syntax_deltas"]["clinical_term"] == pytest.approx(-0.08)
    assert r["syntax_deltas"]["patient_term"] == pytest.approx(-0.08)

    out = tmp_path / "out"
    assert (out / "index_01.png").stat().st_size > 1000
    assert (out / "pair_01_quad_c.tagged.json").is_file()
    html = (out / "index_01.html").read_text(encoding="utf-8")
    # four quadrant panels on one canvas, labeled A-D
    assert html.count('<g transform="translate(') == 4
    assert "A · Clinical frame + clinical term" in html
    assert "D · Patient frame + patient term" in html
    # prominent per-box target probabilities in explicit prob() notation
    for value in ("0.86", "0.46", "0.78", "0.38"):
        assert f"prob(jumps) = {value}" in html
    assert "p(jumps)" not in html
    # cross-panel deltas: all badges horizontal (no rotated gutter text)
    assert html.count("Vocabulary Δ: -40% probability (0.86 → 0.46)") == 1
    assert "Vocabulary Δ: -40% probability (0.78 → 0.38)" in html
    assert html.count("Syntax Δ: -8% probability") == 2
    assert 'transform="rotate(-90' not in html


def test_run_batch_translation_offline(tmp_path, monkeypatch):
    config = tmp_path / "keyword_config.json"
    config.write_text(
        json.dumps({**TEST_KEYWORD_CONFIG, "translations": {"patient phrasing": "clinical phrasing"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(config))

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        g = _two_logit_graph()
        p = 0.81 if "clinical" in prompt else 0.4
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{"patient_prompt": "patient phrasing about the fox", "target_clinical_token": " jumps"}]),
        encoding="utf-8",
    )

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), mode="translation",
        use_llm_translation=False, dpi=50, fetcher=build_fetcher(),
    )
    r = results[0]
    assert r["mode"] == "translation"
    # the raw translation output is traced natively - no template applied
    assert r["prompts"]["translated"] == "clinical phrasing about the fox"
    assert r["translation_method"] == "phrase_table"
    assert r["probabilities"] == {"patient": 0.4, "translated": 0.81}
    assert r["recovered_probability"] == pytest.approx(0.41)

    out = tmp_path / "out"
    assert (out / "pair_01_patient.tagged.json").is_file()
    assert (out / "pair_01_translated.tagged.json").is_file()
    html = (out / "index_01.html").read_text(encoding="utf-8")
    # two-panel vertical chain with the translation interstitial in the gap
    assert html.count('<g transform="translate(') == 2
    assert "Patient wording (original)" in html
    assert "natively traced" in html
    assert "LLM Translation (phrase_table): “clinical phrasing about the fox”" in html
    assert "Recovered target probability: +41% probability (0.40 → 0.81)" in html
    # recovered target probabilities as per-panel headlines, prob() notation
    assert "prob(jumps) = 0.40" in html and "prob(jumps) = 0.81" in html
    assert r["predictive_spread"]["translated"] == [("a", 0.9), ("jumps", 0.81)]
