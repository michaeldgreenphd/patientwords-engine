from conftest import TEST_KEYWORD_CONFIG

from medlang_circuits.feature_tagger import annotate_graph, classify_text
from medlang_circuits.schema_utils import cantor_decode, node_layer_and_index


def test_cantor_decode_roundtrip():
    def cantor(layer, index):
        return ((layer + index) * (layer + index + 1)) // 2 + index

    for layer, index in [(0, 0), (3, 42), (25, 16383)]:
        assert cantor_decode(cantor(layer, index)) == (layer, index)


def test_old_schema_layer_index(graph):
    node = graph["nodes"][1]  # feature 300042 -> layer 3, index 42
    assert node_layer_and_index(node, schema_version=None, scan="gemma-2-2b") == (3, 42)


def test_classify_text_matches_and_priority():
    category, matched = classify_text("all about alpha things", keyword_config=TEST_KEYWORD_CONFIG)
    assert category == "clinical"
    assert "alpha" in matched

    category, _ = classify_text("gamma stuff", keyword_config=TEST_KEYWORD_CONFIG)
    assert category == "off_target"

    category, matched = classify_text("nothing relevant here", keyword_config=TEST_KEYWORD_CONFIG)
    assert category is None and matched == []

    # multi-word phrase matching
    category, matched = classify_text("a beta term appears", keyword_config=TEST_KEYWORD_CONFIG)
    assert category == "clinical"


def test_annotate_graph(graph, fetcher):
    annotate_graph(graph, fetcher=fetcher, keyword_config=TEST_KEYWORD_CONFIG)

    by_id = {n["node_id"]: n["medlang"] for n in graph["nodes"]}
    assert by_id["E_100_0"]["category"] == "structural"
    assert by_id["err_5_2"]["category"] == "structural"
    assert by_id["L_999_3"]["category"] == "structural"
    assert by_id["3_00042_1"]["category"] == "clinical"
    assert by_id["3_00042_1"]["method"] == "keyword"
    assert by_id["7_00007_2"]["category"] == "off_target"
    assert by_id["9_00001_3"]["category"] == "off_target"  # default bucket
    assert by_id["9_00001_3"]["method"] == "default"

    # clerp filled from fetched description
    node = next(n for n in graph["nodes"] if n["node_id"] == "3_00042_1")
    assert node["clerp"].startswith("references to alpha")

    summary = graph["metadata"]["medlang_summary"]
    assert summary["node_counts"]["structural"] == 3
    assert summary["node_counts"]["clinical"] == 1
    assert 0 < summary["attribution_mass_share"]["clinical"] <= 1
    assert summary["total_abs_edge_weight"] == 13.5


def test_annotate_graph_llm_fallback(graph, fetcher):
    calls = []

    def fake_llm(description, top_tokens):
        calls.append(description)
        return "clinical"

    annotate_graph(graph, fetcher=fetcher, keyword_config=TEST_KEYWORD_CONFIG, llm_classifier=fake_llm)
    by_id = {n["node_id"]: n["medlang"] for n in graph["nodes"]}
    assert by_id["9_00001_3"]["category"] == "clinical"
    assert by_id["9_00001_3"]["method"] == "llm"
    assert calls == ["something entirely unmatched"]
