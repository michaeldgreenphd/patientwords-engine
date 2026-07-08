import re

import pytest
from conftest import TEST_KEYWORD_CONFIG, build_fetcher, make_graph

from medlang_circuits.compare_viz import (
    CATEGORY_COLORS,
    ELIDED_GAP_ROWS,
    _prepare,
    render_stacked_html,
    render_stacked_png,
)
from medlang_circuits.feature_tagger import annotate_graph


def _tagged_pair():
    top, bottom = make_graph(), make_graph()
    bottom["metadata"]["prompt"] = "patient wording variant"
    # multi-token diff: tokens 1-2 altered, but only the compared word (" swift",
    # the longest content token) should be emphasized; " very" must stay muted
    bottom["metadata"]["prompt_tokens"] = ["the", " very", " swift", " brown", " fox"]
    for g in (top, bottom):
        annotate_graph(g, fetcher=build_fetcher(), keyword_config=TEST_KEYWORD_CONFIG)
    return top, bottom


def test_render_stacked_html_standalone_interactive(tmp_path):
    top, bottom = _tagged_pair()
    out = tmp_path / "index.html"
    render_stacked_html(top, bottom, str(out))
    html = out.read_text(encoding="utf-8")

    # feature category colors present; interactive tooltip machinery inlined
    assert CATEGORY_COLORS["clinical"] in html
    assert CATEGORY_COLORS["off_target"] in html
    assert 'id="tt"' in html and "var DATA=" in html
    assert 'data-p="1"' in html and 'data-i="0"' in html
    # full autointerp description flows into the tooltip payload
    assert "references to alpha and beta term contexts" in html
    # tooltip readout uses explicit prob()/mass notation (no "p(...)" / "Probability")
    assert '"wl":"prob(jumps)","w":"0.81"' in html  # fixture logit clerp "jumps (p=0.81)"
    assert '"wl":"mass"' in html
    assert '"wl":"Probability"' not in html and '"wl":"Mass"' not in html
    # threshold value layer: only the top panel's clinical node (norm mass 0.60 >= 0.50)
    # carries an on-chart number; the identical bottom-panel node does not
    assert html.count('class="nv"') == 1
    assert '>0.60</text>' in html
    # ...and the tooltip carries the exact same normalized number alongside absolute mass
    assert '"w":"6.000 (norm 0.60)"' in html
    # proportional node sizing: radii vary across nodes instead of a uniform value
    # node circles only - the top-1 logit's emphasis ring draws wider on purpose
    radii = {m for m in re.findall(r'class="n"[^/]*? r="([\d.]+)"', html)}
    assert len(radii) > 2
    assert all(3.0 <= float(r) <= 14.0 for r in radii)
    # bezier endpoints are trimmed to node rims (curves exist and start offset from centers)
    assert html.count("<path d=\"M") == len(top["links"]) + len(bottom["links"])
    # only the single compared word is emphasized per panel, in the panel accent color;
    # surrounding differenced tokens (" very") stay muted like static tokens
    # wordpiece assembly strips the tokenizer's leading space from labels
    assert f'class="tk tke" style="fill:{CATEGORY_COLORS["clinical"]}">quick<' in html
    # ...and gets an accent underline bar
    assert f'height="3.5" fill="{CATEGORY_COLORS["clinical"]}"' in html
    assert f'class="tk tke" style="fill:{CATEGORY_COLORS["off_target"]}"> swift<' in html
    assert 'font-weight:600"> very<' not in html
    assert html.count('class="tk tke"') == 2  # exactly one emphasized token per panel
    # inline category labels instead of a detached legend
    assert ">Clinical</text>" in html and ">Off-target</text>" in html
    assert "<legend" not in html
    # standalone + responsive: no external refs, viewport meta, fluid svg
    body = html.split("</style>")[1]
    assert "http://" not in body.replace("http://www.w3.org/2000/svg", "") and "https://" not in body
    assert 'name="viewport"' in html
    assert "viewBox=" in html
    assert "patient wording variant" in html


def test_dynamic_layer_compression(graph):
    # fixture occupies layers {-1, 3, 5, 7, 9, 27}; empty runs must be elided
    prep = _prepare(graph, max_edges=100)
    ys = dict(prep["layer_ticks"])
    assert set(ys) == {"emb", "L3", "L5", "L7", "L9", "logit"}
    row_step = abs(ys["L5"] - ys["L7"])  # adjacent occupied layers (gap of 1 empty layer -> elided)
    # emb (-1) to L3 skips 3 empty layers, but only costs the fixed elision gap
    assert abs(ys["emb"] - ys["L3"]) == pytest.approx(row_step)
    # elision markers rendered for each compressed run
    assert len(prep["elision_ys"]) == 5
    # total height is compact: 6 occupied layers, not 29 rows
    assert prep["panel_height"] < 500
    assert row_step / 34 == pytest.approx(ELIDED_GAP_ROWS)


def test_render_stacked_png(tmp_path):
    top, bottom = _tagged_pair()
    out = tmp_path / "cmp.png"
    render_stacked_png(top, bottom, str(out), dpi=60)
    assert out.stat().st_size > 1000


def test_logit_spread_stacks_without_collisions(graph):
    # three logits share the final token column -> they must stack vertically,
    # best probability on top, spaced rim-to-rim so labels can't overlap
    graph["nodes"].append({"node_id": "L_mid", "feature": None, "layer": "26", "ctx_idx": 3,
                           "feature_type": "logit", "jsNodeId": "L_mid", "clerp": "leaps (p=0.9)"})
    graph["nodes"].append({"node_id": "L_low", "feature": None, "layer": "26", "ctx_idx": 3,
                           "feature_type": "logit", "jsNodeId": "L_low", "clerp": "runs (p=0.2)"})
    graph["links"].append({"source": "9_00001_3", "target": "L_mid", "weight": 2.0})
    graph["links"].append({"source": "9_00001_3", "target": "L_low", "weight": 1.0})

    prep = _prepare(graph, max_edges=100)
    pos, radius = prep["positions"], prep["radius"]
    ys = {nid: pos[nid][1] for nid in ("L_mid", "L_999_3", "L_low")}
    # ordered by probability: 0.9 on top, then 0.81, then 0.2
    assert ys["L_mid"] < ys["L_999_3"] < ys["L_low"]
    # same x (a clean vertical stack); labels sit beside each node, so the
    # invariant is rim-to-rim clearance plus center spacing above the 9.5px
    # label line height
    assert pos["L_mid"][0] == pos["L_999_3"][0] == pos["L_low"][0]
    for upper, lower in (("L_mid", "L_999_3"), ("L_999_3", "L_low")):
        gap = (ys[lower] - ys[upper]) - radius[upper] - radius[lower]
        assert gap >= 9.9
        assert ys[lower] - ys[upper] >= 12.0
    # the panel grew to make room for the stack (vs. the unstacked fixture)
    single = _prepare(make_graph(), max_edges=100)
    assert prep["panel_height"] > single["panel_height"]
