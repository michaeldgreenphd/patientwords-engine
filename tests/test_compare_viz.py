from conftest import TEST_KEYWORD_CONFIG, build_fetcher, make_graph

from medlang_circuits.compare_viz import CATEGORY_COLORS, render_stacked_html, render_stacked_png
from medlang_circuits.feature_tagger import annotate_graph


def _tagged_pair():
    top, bottom = make_graph(), make_graph()
    bottom["metadata"]["prompt"] = "patient wording variant"
    for g in (top, bottom):
        annotate_graph(g, fetcher=build_fetcher(), keyword_config=TEST_KEYWORD_CONFIG)
    return top, bottom


def test_render_stacked_html(tmp_path):
    top, bottom = _tagged_pair()
    out = tmp_path / "cmp.html"
    render_stacked_html(top, bottom, str(out))
    html = out.read_text(encoding="utf-8")
    assert CATEGORY_COLORS["clinical"] in html
    assert CATEGORY_COLORS["off_target"] in html
    assert "patient wording variant" in html
    assert "<svg" in html and "http" not in html.split("</style>")[1]  # self-contained: no external refs in body


def test_render_stacked_png(tmp_path):
    top, bottom = _tagged_pair()
    out = tmp_path / "cmp.png"
    render_stacked_png(top, bottom, str(out), dpi=60)
    assert out.stat().st_size > 1000
