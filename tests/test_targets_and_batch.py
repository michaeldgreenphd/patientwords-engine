import json

import pytest
from conftest import TEST_KEYWORD_CONFIG, build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval
from medlang_circuits.targets import (
    AttributionTargets,
    parse_logit_clerp,
    retarget_graph,
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
    # retargeting removed the article logit from every panel
    assert "a (p=0.9)" not in html
