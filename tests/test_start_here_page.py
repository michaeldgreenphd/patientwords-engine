"""Start here keeps its diagram-led design, its interactions and its checked values.

The page was restored on 2026-11-11 from the design published before a redesign the owner rejected
(site commit ``ac82473``), with a small number of corrections made in place. The owner's standing
preference is recorded in the site's ``docs/agent_reference.md``: preserve the narrative, the diagrams
and the interactions; later work makes small, justified edits. These tests are the executable part of
that preference:

* the nine steps, the seven diagrams with a second drawing for narrow screens, the wording toggle and
  the three-stage cycle are present;
* the specific claims corrected in the restoration do not return (a next token described as an answer
  or as advice, a trace described as showing the reasoning, an invented completed word where the
  record holds a word piece);
* every recorded value printed in a diagram has a claim entry and is replaced from the data files
  when they load.

The browser tests serve the site's real page from a temporary directory with placeholder data, so no
study value is involved. Skipped where the sibling site checkout, Playwright or a Chromium is missing.
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
import shutil
import socket
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"
PAGE = SITE / "start-here" / "index.html"
REL = "start-here/index.html"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

STEPS = ("A doctor converges", "The model diverges", "Try it", "What we measure", "Look inside", "The patch",
         "The smart patch", "The lasting fix", "The mended system")
# Corrected in the restoration; each is a claim the measurement does not support.
WITHDRAWN = (
    "Watch one word change the answer",            # one next token is not an assistant's answer
    "photographs the reasoning",                   # a trace is a readout of active features, not the reasoning
    "Who is harmed, and how",                      # no harm was measured
    "right answer",                                # the measured quantity is the target token
    "ice cream 29%",                               # the record holds the word piece "ice"
    "antacid 31%",                                 # the record holds the word piece "ant"
)
KEPT = (
    "Watch wording change the prediction",
    "Looking inside the prediction",
    "Why wording matters",
    "It is not an assistant’s advice",
    "a readout, not proof of a cause",
    "say it the other way",
)
PLACEHOLDER_PAYLOAD = {
    "featured": {"tap_demo": {
        "clinical": {"swap": "placeholder one", "bars": [{"label": "alpha", "p": 0.5, "role": "target"},
                                                         {"label": "beta", "p": 0.25, "role": "other"}]},
        "patient": {"swap": "placeholder two", "bars": [{"label": "gamma", "p": 0.125, "role": "top"},
                                                        {"label": "alpha (4th)", "p": 0.0625, "role": "target"}]}}},
    "scenarios": [{"batch": "pairs_20260707T171223Z", "batch_index": 12,
                   "top_clinical": [" one", 0.5], "top_patient": [" two", 0.25],
                   "circuit_diff": {"shared_features": 10, "unique_to_a": 3, "unique_to_b": 4}}],
}
# 0.285 and 0.125 both sit on a rounding boundary in binary; the page rounds the recorded decimal half up.
PLACEHOLDER_PROVENANCE = {
    "ladder_digestive": {"baseline_top": ["three", 0.2]},
    "translation_cases": {"icecream_antacid": {"patient": ["two", 0.285], "translated": ["one", 0.125]},
                          "summary": {"recovered": 1, "n_downgrades": 4}},
}
FROM_PLACEHOLDERS = {
    "s2-clin": "“one”", "s2-pat": "“two”", "s2-formal": "“three”",
    "s5-counts": "hold 13 and 14 features and share 10",
    "s6-pat": "“two” 29%", "s6-trans": "“one” 13%",
    "s6-summary": "restored the top prediction in 1 of 4",
}


def _source() -> str:
    if not PAGE.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    return PAGE.read_text(encoding="utf-8")


def _static_copies(source: str) -> dict[str, set[str]]:
    copies: dict[str, set[str]] = {}
    for key, text in re.findall(r'data-rec="([^"]+)">([^<]*)<', source):
        copies.setdefault(key, set()).add(html.unescape(text))
    return copies


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_page_keeps_its_nine_steps_its_diagrams_and_its_interactions() -> None:
    source = _source()
    steps = [html.unescape(s).strip() for s in re.findall(r'<p class="step-no">(.*?)</p>', source)]
    numbered = [s for s in steps if s[:1].isdigit()]
    assert numbered == [f"{n} · {title}" for n, title in enumerate(STEPS, start=1)]
    # Seven wide diagrams, each with a second drawing of the same content for narrow screens, in one figure.
    figures = re.findall(r'<div class="fig"[^>]*>(.*?)</div>', source, flags=re.S)
    paired = [f for f in figures if 'class="fig-wide"' in f]
    assert len(paired) == 7
    assert all(f.count('class="fig-wide"') == 1 and f.count('class="fig-narrow"') == 1 for f in paired)
    # The wording toggle, the care-urgency ladder and the three-stage cycle with its panels.
    assert 'id="tg-btn"' in source and 'id="tg-swap"' in source and 'id="tg-bars" aria-live="polite"' in source
    assert 'id="care-ladder"' in source
    tabs = re.findall(r'class="cyc-tab" id="tab-(\w+)" role="tab" aria-selected="(true|false)" aria-controls="panel-\1"',
                      source)
    assert tabs == [("measure", "true"), ("mend", "false"), ("maintain", "false")]
    assert [bool(hidden) for _, hidden in re.findall(
        r'class="cyc-panel" id="panel-(\w+)" role="tabpanel" aria-labelledby="tab-\1"( hidden)?>', source)] == [
        False, True, True]
    assert "People say the same thing many ways." in source          # the opening question


def test_the_corrected_claims_stay_corrected() -> None:
    text = html.unescape(_source())
    for phrase in WITHDRAWN:
        assert phrase.lower() not in text.lower(), phrase
    for phrase in KEPT:
        assert phrase in text, phrase
    # Conceptual diagrams are labelled where they stand, not in a separate warning panel.
    assert text.count("Illustration") >= 2 and "Research direction" in text


def test_every_recorded_value_in_a_diagram_has_one_static_copy_and_a_claim_entry() -> None:
    source = _source()
    copies = _static_copies(source)
    assert set(copies) == set(FROM_PLACEHOLDERS)
    for key, texts in copies.items():                       # the two drawings of a diagram say the same thing
        assert len(texts) == 1, (key, texts)
    claims = [c for c in json.loads((ROOT / "data" / "claims_manifest.json").read_text(encoding="utf-8"))["claims"]
              if c["page"] == REL]
    for claim in claims:
        assert claim["snippet"] in source, claim["snippet"]
    for key, texts in copies.items():
        (text,) = texts
        assert any(text in c["snippet"] for c in claims), f"no claim entry guards the static copy of {key}"
    # The step-3 bars and the two text alternatives no script rewrites.
    for snippet in ("bars:[['inhaler',0.692,", "bars:[['shirt',0.183,", "come out as ice at 29% and apple",
                    "comes out as the start of antacid at 31%"):
        assert any(snippet in c["snippet"] for c in claims), snippet


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[object, str]]:
    if not PAGE.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    site = tmp_path_factory.mktemp("start_here_site")
    (site / "start-here").mkdir()
    (site / "data").mkdir()
    shutil.copy2(PAGE, site / "start-here" / "index.html")
    serve = _load("check_pages").serve
    port = _free_port()
    with sync_playwright() as pw:
        candidates = (CHROME, pw.chromium.executable_path, shutil.which("chromium"))
        chrome = next((c for c in candidates if c and Path(c).exists()), None)
        if chrome is None:
            pytest.skip("no Chromium available for a browser-driven test")
        server = serve(site, port)
        try:
            browser = pw.chromium.launch(executable_path=chrome)
            yield browser, f"http://127.0.0.1:{port}/start-here/index.html"
            browser.close()
        finally:
            server.terminate()


def _open(browser, url: str, *, payload: dict | None, provenance: dict | None, width: int = 1280, height: int = 900):
    """A page with the three data files answered from the test. ``None`` answers 404."""
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def answer(body: dict | None):
        if body is None:
            return lambda route: route.fulfill(status=404, body="")
        return lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/data/simulated_scenarios.json", answer(payload))
    page.route("**/data/provenance.json", answer(provenance))
    page.route("**/data/urgency_shift.json", answer(None))
    page.goto(url, wait_until="networkidle")
    return page, errors


def _recorded(page) -> dict[str, list[str]]:
    return page.evaluate("""() => { const out = {};
        document.querySelectorAll('[data-rec]').forEach(n => (out[n.dataset.rec] ||= []).push(n.textContent));
        return out; }""")


def _bars(page) -> list[list[str]]:
    return page.evaluate("""() => [...document.querySelectorAll('#tg-bars .bar-row')].map(r =>
        [r.querySelector('.bar-lbl').textContent, r.querySelector('.bar-val').textContent])""")


def test_recorded_values_follow_the_data_files_and_keep_their_checked_copies_without_them(served) -> None:
    browser, url = served
    page, errors = _open(browser, url, payload=PLACEHOLDER_PAYLOAD, provenance=PLACEHOLDER_PROVENANCE)
    shown = _recorded(page)
    assert {key: set(values) for key, values in shown.items()} == {k: {v} for k, v in FROM_PLACEHOLDERS.items()}
    assert page.inner_text("#tg-swap") == "placeholder one"
    assert _bars(page) == [["alpha", "50%"], ["beta", "25%"]]
    assert errors == []
    page.close()

    static = {key: texts for key, texts in _static_copies(PAGE.read_text(encoding="utf-8")).items()}
    # No file, an empty record, and a record whose values are not numbers: the checked copy stays.
    not_numbers = {"translation_cases": {"icecream_antacid": {"patient": ["two", None], "translated": ["one"]},
                                         "summary": {"recovered": "1"}}}
    for payload, provenance in ((None, None), ({}, {}), ({"scenarios": []}, not_numbers)):
        page, errors = _open(browser, url, payload=payload, provenance=provenance)
        assert {key: set(values) for key, values in _recorded(page).items()} == static
        assert page.inner_text("#tg-swap") == "asthma flares"
        assert _bars(page) == [["inhaler", "69%"], ["mask", "6%"], ["set", "3%"]]
        assert errors == []
        page.close()


def test_the_wording_toggle_and_the_cycle_tabs_work_by_pointer_and_by_keyboard(served) -> None:
    browser, url = served
    page, errors = _open(browser, url, payload=PLACEHOLDER_PAYLOAD, provenance=PLACEHOLDER_PROVENANCE)
    page.click("#tg-btn")
    assert page.inner_text("#tg-swap") == "placeholder two"
    assert _bars(page) == [["gamma", "13%"], ["alpha (4th)", "6%"]]
    page.focus("#tg-btn")
    page.keyboard.press("Enter")
    assert page.inner_text("#tg-swap") == "placeholder one"
    page.keyboard.press("Space")
    assert page.inner_text("#tg-swap") == "placeholder two"

    def cycle() -> tuple[list[str], list[bool], list[str]]:
        return tuple(page.evaluate("""() => { const tabs = [...document.querySelectorAll('.cyc-tab')];
            return [tabs.map(t => t.getAttribute('aria-selected')),
                    tabs.map(t => document.getElementById(t.getAttribute('aria-controls')).hidden),
                    tabs.map(t => t.getAttribute('tabindex'))]; }"""))

    assert cycle() == (["true", "false", "false"], [False, True, True], ["0", "-1", "-1"])
    page.click("#tab-mend")
    assert cycle() == (["false", "true", "false"], [True, False, True], ["-1", "0", "-1"])
    page.focus("#tab-mend")
    page.keyboard.press("ArrowRight")
    assert cycle() == (["false", "false", "true"], [True, True, False], ["-1", "-1", "0"])
    assert page.evaluate("document.activeElement.id") == "tab-maintain"
    page.keyboard.press("ArrowRight")                               # wraps to the first stage
    assert page.evaluate("document.activeElement.id") == "tab-measure"
    page.keyboard.press("End")
    assert cycle()[0] == ["false", "false", "true"]
    page.keyboard.press("Home")
    assert cycle() == (["true", "false", "false"], [False, True, True], ["0", "-1", "-1"])
    assert errors == []
    page.close()


def test_each_diagram_is_drawn_once_at_either_width_and_stays_readable_on_a_phone(served) -> None:
    browser, url = served
    measure = """() => { const shown = sel => [...document.querySelectorAll(sel)].filter(n => n.getClientRects().length);
        const narrow = shown('.fig .fig-narrow');
        const sizes = narrow.flatMap(svg => { const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
            return [...svg.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize) * scale); });
        return {wide: shown('.fig .fig-wide').length, narrow: narrow.length,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                smallest: sizes.length ? Math.min(...sizes) : null}; }"""
    page, errors = _open(browser, url, payload=None, provenance=None, width=1280, height=900)
    desktop = page.evaluate(measure.replace("shown('.fig .fig-narrow');", "shown('.fig .fig-wide');"))
    assert (desktop["wide"], desktop["narrow"]) == (7, 7) and desktop["overflow"] <= 0 and errors == []
    assert page.evaluate("[...document.querySelectorAll('.fig .fig-narrow')].filter(n => n.getClientRects().length).length") == 0
    page.close()
    page, errors = _open(browser, url, payload=None, provenance=None, width=390, height=844)
    phone = page.evaluate(measure)
    assert (phone["wide"], phone["narrow"]) == (0, 7) and phone["overflow"] <= 0 and errors == []
    # The narrow drawings reflow the nodes and labels; they do not shrink the wide drawing. Their smallest
    # label is as large on a 390 px phone as the wide drawings' smallest label is on a desktop (about 10 px;
    # ``smallest`` on the desktop page is measured over the wide drawings). A wide drawing scaled to the
    # phone's width would put the same label below 5 px.
    assert phone["smallest"] >= 10 and phone["smallest"] >= desktop["smallest"] - 0.01, (phone, desktop)
    page.close()
