"""Tests for scripts/extract_site_text.py — strict extraction of the site's text into an Rmd.

The extractor's contract is verbatim transfer: entity unescaping and whitespace
collapsing only, intentional misspellings preserved byte-for-byte, nav/footer/script
never leaking, ids deterministic. The fixture page below is deliberately non-medical
(vocabulary stays in data files, never in Python source) but exercises every capture
tag, nested capture elements, excluded subtrees, and text outside <main>.
"""
import importlib.util
import re
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_site_text.py"
_SPEC = importlib.util.spec_from_file_location("extract_site_text", _SCRIPT)
extract_site_text = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(extract_site_text)

FIXTURE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fixture Page &amp; Title</title>
<meta name="description" content="A fixture page &amp; its description.">
<meta property="og:description" content="OG-LEAK must not be picked up.">
<style>.leak::after{content:"STYLE-LEAK"}</style>
</head>
<body>
<header><nav><a href="./">TOPNAV-LEAK</a></nav></header>
<p>OUTSIDE-MAIN-LEAK before main</p>
<main id="main">
  <h1>The <em>enjine</em> doesn&rsquo;t start</h1>
  <p class="lede">First paragraph: wot the   fixture
     sez stays &amp; survives verbatim.</p>
  <nav aria-label="inner"><li>INNERNAV-LEAK</li></nav>
  <h2>Second<br>heading</h2>
  <ul>
    <li>teh first bullet &mdash; wiht a typo</li>
    <li>outer wraps <p>an inner para</p> and continues</li>
  </ul>
  <details>
    <summary>Open the fold</summary>
    <p>Inside the fold.</p>
  </details>
  <figure><figcaption>caption line</figcaption></figure>
  <script>var leak = "SCRIPT-LEAK";</script>
  <p>   </p>
  <footer>FOOTER-LEAK provenance text</footer>
</main>
<p>OUTSIDE-MAIN-LEAK after main</p>
</body>
</html>
"""

# tag order and text exactly as they must come out: entities unescaped, whitespace
# collapsed, misspellings ('enjine', 'wot', 'sez', 'teh', 'wiht') untouched.
EXPECTED_BLOCKS = [
    ("h1", "The enjine doesn’t start"),
    ("p", "First paragraph: wot the fixture sez stays & survives verbatim."),
    ("h2", "Second heading"),
    ("li", "teh first bullet — wiht a typo"),
    ("li", "outer wraps an inner para and continues"),
    ("summary", "Open the fold"),
    ("p", "Inside the fold."),
    ("figcaption", "caption line"),
]

LEAK_MARKERS = ["TOPNAV-LEAK", "INNERNAV-LEAK", "SCRIPT-LEAK", "STYLE-LEAK",
                "FOOTER-LEAK", "OUTSIDE-MAIN-LEAK", "OG-LEAK"]


def test_parse_page_blocks_verbatim_and_in_order():
    parsed = extract_site_text.parse_page(FIXTURE)
    assert parsed.title == "Fixture Page & Title"
    assert parsed.meta_description == "A fixture page & its description."
    assert parsed.blocks == EXPECTED_BLOCKS  # order, tags, and byte-for-byte text


def test_parse_page_excludes_nav_script_style_footer_and_outside_main():
    parsed = extract_site_text.parse_page(FIXTURE)
    joined = " ".join(text for _, text in parsed.blocks)
    for marker in LEAK_MARKERS:
        assert marker not in joined
    assert "OG-LEAK" not in parsed.meta_description


def _run_main(tmp_path, monkeypatch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "fixture.html").write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(extract_site_text, "PAGES", ["fixture.html"])
    out = tmp_path / "docs" / "site_text.Rmd"
    assert extract_site_text.main(["--site-root", str(tmp_path), "--out", str(out)]) == 0
    return out.read_text(encoding="utf-8")


def test_rmd_structure_ids_sequential_and_no_leaks(tmp_path, monkeypatch, capsys):
    rmd = _run_main(tmp_path, monkeypatch)
    printed = capsys.readouterr().out
    assert "fixture.html: 8 blocks" in printed
    assert "total: 8 blocks" in printed

    # YAML header and instructions block
    assert rmd.startswith('---\ntitle: "PatientWords — site text for manual editing"\n'
                          'date: "2026-07-09"\noutput: html_document\n---\n')
    assert "**Instructions.**" in rmd

    # page heading and flagged meta description
    assert "# Fixture Page & Title — `fixture.html`" in rmd
    assert "> ⚑ meta description: A fixture page & its description." in rmd

    # ids: zero-padded, per-page, strictly sequential, one per block
    ids = re.findall(r"<!-- id: fixture\.b(\d{3}) -->", rmd)
    assert ids == [f"{n:03d}" for n in range(1, len(EXPECTED_BLOCKS) + 1)]

    # each block formatted per its tag, in document order
    prefixes = {"h1": "## ", "h2": "## ", "h3": "### ", "p": "",
                "li": "- ", "summary": "*fold:* ", "figcaption": "*caption:* "}
    positions = []
    for tag, text in EXPECTED_BLOCKS:
        rendered = prefixes[tag] + text
        assert rendered in rmd
        positions.append(rmd.index(rendered))
    assert positions == sorted(positions)

    # entities are unescaped exactly once; raw references never survive
    assert "&rsquo;" not in rmd and "’" in rmd
    assert "stays & survives verbatim." in rmd and "&amp;" not in rmd

    # nothing from nav/script/style/footer/outside-main reaches the document
    for marker in LEAK_MARKERS:
        assert marker not in rmd

    # the one allowed per-page note about runtime-generated text
    assert rmd.count(extract_site_text.PAGE_NOTE) == 1


def test_output_is_deterministic_across_runs(tmp_path, monkeypatch):
    first = _run_main(tmp_path / "a", monkeypatch)
    second = _run_main(tmp_path / "b", monkeypatch)
    assert first == second
