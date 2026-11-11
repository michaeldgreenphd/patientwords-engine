"""Start here keeps its diagram-led design, its interactions and its checked values.

The page was restored on 2026-11-11 from the design published before a redesign the owner rejected
(site commit ``ac82473``), with a small number of corrections made in place. The owner's standing
preference is recorded in the site's ``docs/agent_reference.md``: preserve the narrative, the diagrams
and the interactions; later work makes small, justified edits. These tests are the executable part of
that preference:

* the nine steps, the seven diagrams with a second drawing for narrow screens, the wording toggle, the
  care-urgency ladder and the three-stage cycle are present, and the two drawings of a diagram carry
  the same words;
* the specific claims corrected in the restoration do not return (a next token described as an answer
  or as advice, a trace described as showing the reasoning, an invented completed word where the
  record holds a word piece);
* captions follow the owner's rule of 2026-11-11 (a caption identifies the model, explains a visual
  encoding or prevents a specific misreading). The check is on what a reader can tell, not on the
  captions' wording: a measured example names its model beside it, the feature sketch is recognizable
  as a schematic, the prospective sections are prospective in their own prose, and the status the
  examples share is stated once, in the endnote;
* every recorded value printed in a diagram has its own claim entry, is replaced from the data files
  when they load, and is named in the figure's text alternative with the value the figure shows.

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
from collections import Counter
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
    "can answer each one differently",             # the page description: a prediction, not an answer
    "the same complaint in three phrasings",       # the three rows are shortened, and one is another sentence
    "recommended clinical advice",                 # a single-token readout is not advice
    "measured across this site are written by an LLM",   # not every pair on the site is; the endnote speaks for this page
)
KEPT = (
    "Watch wording change the prediction",
    "Looking inside the prediction",
    "Why wording matters",
    "It is not an assistant’s advice",
    "a readout, not proof of a cause",
    "say it the other way",
    "sentences shortened",
)
PLACEHOLDER_PAYLOAD = {
    "featured": {
        "tap_demo": {
            "clinical": {"swap": "placeholder one", "bars": [{"label": "alpha", "p": 0.5, "role": "target"},
                                                             {"label": "beta", "p": 0.25, "role": "other"}]},
            "patient": {"swap": "placeholder two", "bars": [{"label": "gamma", "p": 0.125, "role": "top"},
                                                            {"label": "alpha (4th)", "p": 0.0625, "role": "target"}]}},
        "care_ladder": [{"batch": "placeholder_batch", "batch_index": 7, "model": "gemma-2-2b", "x": 330}]},
    "scenarios": [
        {"batch": "pairs_20260707T171223Z", "batch_index": 12,
         "top_clinical": [" one", 0.5], "top_patient": [" two", 0.25]},
        # the ladder prints the exported token as it is; the exporter writes tokens without a leading space
        {"batch": "placeholder_batch", "batch_index": 7, "top_clinical": ["up", 0.6], "top_patient": ["down", 0.2],
         "clinical_prompt": "A placeholder term goes", "clinical_term": "placeholder term",
         "patient_prompt": "A plain phrase goes", "patient_term": "plain phrase"}],
}
# 0.285 and 0.125 both sit on a rounding boundary in binary; the page rounds the recorded decimal half up.
PLACEHOLDER_PROVENANCE = {
    "ladder_digestive": {"baseline_top": ["three", 0.2]},
    "translation_cases": {"icecream_antacid": {"patient": ["two", 0.285], "translated": ["one", 0.125]}},
}
PLACEHOLDER_URGENCY = {
    "tiers": {"0": "tier zero", "1": "tier one", "2": "tier two", "3": "tier three", "4": "tier four"},
    "rows": [{"batch": "placeholder_batch", "index": 7, "model": "gemma-2-2b",
              "tier_top_clinical": 3, "tier_top_patient": 1}],
}
FROM_PLACEHOLDERS = {
    "s2-clin": "“one”", "s2-pat": "“two”", "s2-formal": "“three”",
    "s6-pat": "“two” 29%", "s6-trans": "“one” 13%",
}
# The name the captions give the model the examples were measured on.
MODEL = "Gemma 2 2B"
# The figures whose text alternative names recorded values, by the step they are in.
LABELLED_FIGURES = 4
PENDING_LADDER = "figure pending: the urgency measurements have not loaded"


def _source() -> str:
    if not PAGE.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    return PAGE.read_text(encoding="utf-8")


def _static_copies(source: str) -> dict[str, set[str]]:
    copies: dict[str, set[str]] = {}
    for key, text in re.findall(r'data-rec="([^"]+)">([^<]*)<', source):
        copies.setdefault(key, set()).add(html.unescape(text))
    return copies


def _figures(source: str) -> list[str]:
    return re.findall(r'<div class="fig"[^>]*>.*?</div>', source, flags=re.S)


def _steps(source: str) -> dict[int, str]:
    """The markup of each numbered step, by its number."""
    found: dict[int, str] = {}
    for section in re.findall(r"<section>.*?</section>", source, flags=re.S):
        label = re.search(r'<p class="step-no">(\d+)', section)
        if label:
            found[int(label.group(1))] = section
    return found


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _captions(markup: str) -> list[str]:
    return [_text(c) for c in re.findall(r'<p class="cap[^"]*"[^>]*>(.*?)</p>', markup, flags=re.S)]


def _fill(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{([a-z0-9-]+)\}", lambda match: values[match.group(1)], template)


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
    paired = [f for f in _figures(source) if 'class="fig-wide"' in f]
    assert len(paired) == 7
    assert all(f.count('class="fig-wide"') == 1 and f.count('class="fig-narrow"') == 1 for f in paired)
    # The wording toggle, the care-urgency ladder and the three-stage cycle with its panels.
    assert 'id="tg-btn"' in source and 'id="tg-swap"' in source and 'id="tg-bars" aria-live="polite"' in source
    assert 'id="care-ladder"' in source and PENDING_LADDER in source
    tabs = re.findall(r'class="cyc-tab" id="tab-(\w+)" role="tab" aria-selected="(true|false)" aria-controls="panel-\1"',
                      source)
    assert tabs == [("measure", "true"), ("mend", "false"), ("maintain", "false")]
    assert [bool(hidden) for _, hidden in re.findall(
        r'class="cyc-panel" id="panel-(\w+)" role="tabpanel" aria-labelledby="tab-\1"( hidden)?>', source)] == [
        False, True, True]
    assert "People say the same thing many ways." in source          # the opening question


def test_the_two_drawings_of_a_diagram_carry_the_same_words() -> None:
    """A narrow drawing reflows the wide one: a label may wrap onto two lines or move, but no word is added,
    dropped or changed. (Review finding, 2026-11-11: two pairs differed; comparing only the recorded values
    did not see it.)"""
    paired = [f for f in _figures(_source()) if 'class="fig-wide"' in f]

    def words(figure: str, cls: str) -> Counter:
        svg = re.search(rf'<svg class="{cls}".*?</svg>', figure, flags=re.S).group(0)
        texts = [html.unescape(re.sub(r"<[^>]+>", "", t)) for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S)]
        return Counter(" ".join(texts).split())

    for figure in paired:
        wide, narrow = words(figure, "fig-wide"), words(figure, "fig-narrow")
        assert wide == narrow, (sorted((wide - narrow).elements()), sorted((narrow - wide).elements()))


def test_the_corrected_claims_stay_corrected() -> None:
    text = html.unescape(_source())
    for phrase in WITHDRAWN:
        assert phrase.lower() not in text.lower(), phrase
    for phrase in KEPT:
        assert phrase in text, phrase
    # No heading calls a single-token readout the right answer or recommended clinical advice.
    headings = [_text(a or b) for a, b in re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>|<p class="step-no">(.*?)</p>',
                                                     _source(), flags=re.S)]
    assert len(headings) > len(STEPS)
    for heading in headings:
        assert not re.search(r"(right|correct) answer|recommended|clinical advice", heading, flags=re.I), heading


def test_each_figure_states_its_basis_where_a_reader_needs_it() -> None:
    """The owner's caption rule (2026-11-11, recorded in the site's ``docs/agent_reference.md``): a caption
    identifies the model, explains a visual encoding or prevents a specific misreading; it does not repeat the
    paragraph or a status the whole page shares. An earlier version of this test counted captions that began
    "Illustration" and "Research direction", which froze copy the owner then removed. This one checks what a
    reader can tell and leaves the wording free."""
    source = _source()
    steps = _steps(source)
    assert sorted(steps) == list(range(1, len(STEPS) + 1))
    captions = {n: _captions(section) for n, section in steps.items()}

    # A measured example names its model once, beside the example. Steps 2, 3 and 6 name it in the caption.
    # Step 4's ladder prints the model from each pair's record inside the figure (the browser test below reads
    # it there), so its caption does not name it a second time.
    for n in (2, 3, 6):
        assert len(captions[n]) == 1 and captions[n][0].count(MODEL) == 1, (n, captions[n])
    assert len(captions[4]) == 1 and "gemma" not in captions[4][0].lower(), captions[4]
    # What each measured figure cannot show by itself: step 2's third row comes from another run (the three
    # rows are not one matched experiment), step 4's tiers are a draft, and step 6 is one case whose dashed path
    # was not measured.
    assert re.search(r"\b(separate|different|another)\b[^·]*\brun\b", captions[2][0]), captions[2]
    assert re.search(r"\bdraft\b", captions[4][0], flags=re.I), captions[4]
    assert re.search(r"\bone\b", captions[6][0]) and re.search(r"\bnot measured\b", captions[6][0]), captions[6]
    # Step 3's chart prints a whole word where the record holds its first piece; while it does, the caption
    # names the recorded piece. The caption keeps one link, to the pair's trace.
    if "bars:[['inhaler'," in source:
        assert "“inhal”" in captions[3][0], captions[3]
    assert re.findall(r'href="([^"]+)"', re.search(r'<p class="cap">(.*?)</p>', steps[3], flags=re.S).group(1)) == [
        "../modes/simulated/pairs_20260707T171223Z/index_49.html"]

    # The feature sketch of step 5 is recognizable as a schematic, and its drawn circles are not described with
    # a measured count.
    assert len(captions[5]) == 1 and re.search(r"schematic|illustrat", captions[5][0], flags=re.I), captions[5]
    assert not re.search(r"\d", captions[5][0]), captions[5]
    # Conceptual diagrams (1, 5, 7, 8, 9) do not name a model; only measured examples do.
    for n in (1, 5, 7, 8, 9):
        assert "gemma" not in _text(steps[n]).lower(), n
    # The prospective sections (7 and 9) say so in their own prose, before the diagram: what an intermediary
    # "could" do, "the goal", what a model "would" do. No caption carries that status for them.
    for n in (7, 9):
        prose = _text(" ".join(re.findall(r"<p>(.*?)</p>", steps[n].split('<div class="fig"', 1)[0], flags=re.S)))
        assert re.search(r"\b(could|would|might|goal|propos\w+|not yet)\b", prose), (n, prose)

    # The Sources note names the two data files behind the measured values and the panels that are illustrations.
    sources = re.search(r'<div class="src">(.*?)</div>', source, flags=re.S).group(1)
    assert "data/simulated_scenarios.json" in sources and "data/provenance.json" in sources
    illustrated = re.search(r"[^.]*\billustrati(?:ons?|ve)\b[^.]*\.", _text(sources))
    assert illustrated and set(re.findall(r"\d", illustrated.group(0))) == {"1", "7", "8", "9"}, _text(sources)
    # The status the examples share (model-generated prompts, clinical equivalence not reviewed) is stated once,
    # in the endnote, and no caption repeats it.
    endnote = _text(re.search(r'<div class="endnote"[^>]*>(.*?)</div>', source, flags=re.S).group(1))
    assert "model-generated" in endnote and re.search(r"not (yet )?been reviewed", endnote), endnote
    assert _text(source).count("model-generated") == 1
    for n, texts in captions.items():
        for caption in texts:
            assert not re.search(r"model-generated|review pending", caption), (n, caption)


def test_every_recorded_value_in_a_diagram_has_one_static_copy_and_its_own_claim_entry() -> None:
    source = _source()
    copies = _static_copies(source)
    assert set(copies) == set(FROM_PLACEHOLDERS)
    for key, texts in copies.items():                       # the two drawings of a diagram say the same thing
        assert len(texts) == 1, (key, texts)
    claims = [c for c in json.loads((ROOT / "data" / "claims_manifest.json").read_text(encoding="utf-8"))["claims"]
              if c["page"] == REL]
    for claim in claims:
        assert claim["snippet"] in source, claim["snippet"]
    # Each key has an entry of its own. Matching the bare text would let the entry for “ant” 31% stand in for
    # the entry for “ant”, which reads another file.
    for key, texts in copies.items():
        (text,) = texts
        wanted = f'data-rec="{key}">{text}<'
        assert any(html.unescape(c["snippet"]).startswith(wanted) for c in claims), f"no claim entry for {key}"
    # The step-3 bars, the static copies of the four text alternatives, and the fixed note in step 2's drawing
    # that the recorded token is the start of the target word.
    for snippet in ("bars:[['inhaler',0.692,", "bars:[['shirt',0.183,", "come out as “ice” 29% and “apple”.",
                    "comes out as “ant” 31%.", "predictions: “ant” (the start of “antacid”), “ice” and",
                    "leads to “ant”.", "start of “antacid”"):
        assert any(snippet in c["snippet"] for c in claims), snippet
    # Two captions state a fact of the record in fixed text; each has an entry that fails when the record moves:
    # step 3's word piece, and the draft status of the urgency tiers in step 4.
    assert any("inhal" in html.unescape(c["snippet"]) and "'top_clinical'" in c["expr"] for c in claims)
    assert any(c["source"] == "data/urgency_shift.json" and "vocabulary_status" in c["expr"] for c in claims)


def test_a_figure_that_prints_recorded_values_names_them_in_its_text_alternative() -> None:
    """The static text alternative is the template filled with the static copies, so a reader without scripts
    hears what the drawing shows. (Codex finding, 2026-11-11: the alternatives were fixed text beside values
    that the page replaces from the data files.)"""
    source = _source()
    static = {key: next(iter(texts)) for key, texts in _static_copies(source).items()}
    labelled = re.findall(r'<div class="fig" role="img" data-label="([^"]*)" aria-label="([^"]*)">', source)
    assert len(labelled) == LABELLED_FIGURES
    for template, label in labelled:
        keys = re.findall(r"\{([a-z0-9-]+)\}", template)
        assert keys and set(keys) <= set(static), keys
        assert html.unescape(label) == _fill(html.unescape(template), static)
    # No other figure names a recorded token or percentage in fixed text.
    for figure in _figures(source):
        opening = figure.split(">", 1)[0]
        if "data-label=" not in opening:
            assert not re.search(r"“|\d+%", html.unescape(opening)), opening[:120]


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


def _open(browser, url: str, *, payload: dict | None, provenance: dict | None, urgency: dict | None = None,
          width: int = 1280, height: int = 900):
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
    page.route("**/data/urgency_shift.json", answer(urgency))
    page.goto(url, wait_until="networkidle")
    return page, errors


def _recorded(page) -> dict[str, list[str]]:
    return page.evaluate("""() => { const out = {};
        document.querySelectorAll('[data-rec]').forEach(n => (out[n.dataset.rec] ||= []).push(n.textContent));
        return out; }""")


def _bars(page) -> list[list[str]]:
    return page.evaluate("""() => [...document.querySelectorAll('#tg-bars .bar-row')].map(r =>
        [r.querySelector('.bar-lbl').textContent, r.querySelector('.bar-val').textContent])""")


def _labels(page) -> list[list[str]]:
    return page.evaluate("""() => [...document.querySelectorAll('.fig[data-label]')].map(f =>
        [f.getAttribute('data-label'), f.getAttribute('aria-label')])""")


def test_recorded_values_follow_the_data_files_and_keep_their_checked_copies_without_them(served) -> None:
    browser, url = served
    page, errors = _open(browser, url, payload=PLACEHOLDER_PAYLOAD, provenance=PLACEHOLDER_PROVENANCE)
    shown = _recorded(page)
    assert {key: set(values) for key, values in shown.items()} == {k: {v} for k, v in FROM_PLACEHOLDERS.items()}
    assert page.inner_text("#tg-swap") == "placeholder one"
    assert _bars(page) == [["alpha", "50%"], ["beta", "25%"]]
    # Each text alternative names the values the figure now shows, and none of the page's own copies.
    labels = _labels(page)
    assert len(labels) == LABELLED_FIGURES
    for template, label in labels:
        assert label == _fill(template, FROM_PLACEHOLDERS)
        assert "“ice”" not in label and "“apple”" not in label and "29%" not in label.replace("“two” 29%", "")
    assert errors == []
    page.close()

    source = PAGE.read_text(encoding="utf-8")
    static = _static_copies(source)
    static_labels = [html.unescape(label) for _, label in
                     re.findall(r'<div class="fig" role="img" data-label="([^"]*)" aria-label="([^"]*)">', source)]
    # No file, an empty record, a record whose values are not numbers, empty tokens, and a toggle record with
    # one bad bar: the checked copy stays, whole.
    not_numbers = {"translation_cases": {"icecream_antacid": {"patient": ["two", None], "translated": ["one"]}}}
    empty_tokens = {"scenarios": [{"batch": "pairs_20260707T171223Z", "batch_index": 12,
                                   "top_clinical": ["", 0.5], "top_patient": [" ", 0.25]}],
                    "featured": {"tap_demo": {
                        "clinical": {"swap": "other", "bars": [{"label": "alpha", "p": "0.5", "role": "target"},
                                                               {"label": "beta", "p": 0.25, "role": "other"}]},
                        "patient": PLACEHOLDER_PAYLOAD["featured"]["tap_demo"]["patient"]}}}
    blank = {"ladder_digestive": {"baseline_top": ["", 0.2]},
             "translation_cases": {"icecream_antacid": {"patient": ["\n", 0.285], "translated": ["", 0.125]}}}
    for payload, provenance in ((None, None), ({}, {}), ({"scenarios": []}, not_numbers), (empty_tokens, blank)):
        page, errors = _open(browser, url, payload=payload, provenance=provenance)
        assert {key: set(values) for key, values in _recorded(page).items()} == static
        assert [label for _, label in _labels(page)] == static_labels
        assert page.inner_text("#tg-swap") == "asthma flares"
        assert _bars(page) == [["inhaler", "69%"], ["mask", "6%"], ["set", "3%"]]
        assert errors == []
        page.close()


def test_the_wording_toggle_and_the_cycle_tabs_work_by_pointer_and_by_keyboard(served) -> None:
    browser, url = served
    page, errors = _open(browser, url, payload=PLACEHOLDER_PAYLOAD, provenance=PLACEHOLDER_PROVENANCE)
    # The button's accessible name contains its visible label, and the sentence that changes is announced.
    assert page.get_attribute("#tg-btn", "aria-label").lower().startswith(page.inner_text("#tg-btn").strip().lower())
    assert page.get_attribute(".tg-sentence", "aria-live") == "polite"
    page.click("#tg-btn")
    assert page.inner_text("#tg-swap") == "placeholder two"
    assert _bars(page) == [["gamma", "13%"], ["alpha (4th)", "6%"]]
    page.focus("#tg-btn")
    page.keyboard.press("Enter")
    assert page.inner_text("#tg-swap") == "placeholder one"
    page.keyboard.press("Space")
    assert page.inner_text("#tg-swap") == "placeholder two"
    # A data file equal to what the bars already show does not redraw them (the bars would replay and the live
    # region would announce the same text again); a different one does.
    page.keyboard.press("Space")
    same = PLACEHOLDER_PAYLOAD["featured"]["tap_demo"]
    other = {"clinical": {"swap": "placeholder three", "bars": [{"label": "delta", "p": 0.75, "role": "target"}]},
             "patient": same["patient"]}
    redrawn = """(demo) => { const first = document.querySelector('#tg-bars .bar-row'); first.dataset.kept = 'yes';
        window.pwTapDemo(demo); return document.querySelector('#tg-bars .bar-row').dataset.kept !== 'yes'; }"""
    assert page.evaluate(redrawn, same) is False
    assert page.evaluate(redrawn, other) is True and _bars(page) == [["delta", "75%"]]

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


def test_the_care_urgency_ladder_draws_from_its_data_and_stays_pending_without_it(served) -> None:
    """No other check renders the ladder: the page load check does not notice one left pending, and the
    ladder's own errors are caught by the page."""
    browser, url = served
    page, errors = _open(browser, url, payload=PLACEHOLDER_PAYLOAD, provenance=None, urgency=PLACEHOLDER_URGENCY)
    drawn = page.evaluate("""() => { const svg = document.querySelector('#care-ladder svg');
        return {circles: svg ? svg.querySelectorAll('circle').length : 0,
                texts: svg ? [...svg.querySelectorAll('text')].map(t => t.textContent) : [],
                sentences: [...document.querySelectorAll('#care-ladder .ladder-sent p:not(.ladder-model)')].map(p => p.textContent),
                models: [...document.querySelectorAll('#care-ladder .ladder-model')].map(p => p.textContent),
                label: svg ? svg.getAttribute('aria-label') : null,
                caption: document.getElementById('ladder-cap').textContent,
                captionShown: document.getElementById('ladder-cap').getClientRects().length > 0}; }""")
    assert drawn["circles"] == 2                                     # the medical wording's rung and the everyday one
    assert {"tier zero", "tier one", "tier two", "tier three", "tier four"} <= set(drawn["texts"])
    assert "“up” 60%" in drawn["texts"] and "“down” 20%" in drawn["texts"]
    assert any("placeholder term" in s and "“up” 60%" in s for s in drawn["sentences"])
    assert any("plain phrase" in s and "“down” 20%" in s for s in drawn["sentences"])
    assert drawn["label"] and drawn["label"].startswith("Care-urgency ladder")
    # The model is named once for the figure, from the pair's record. The caption is shown with the figure,
    # states that the tiers are a draft and does not name the model again.
    assert drawn["models"] == ["measured on gemma-2-2b"]
    assert drawn["captionShown"] is True
    assert re.search(r"\bdraft\b", drawn["caption"], flags=re.I) and "gemma" not in drawn["caption"].lower()
    assert errors == []
    page.close()
    # Without the urgency file, and with a pair the urgency file does not hold: the pending notice stays.
    for urgency in (None, {**PLACEHOLDER_URGENCY, "rows": []}):
        page, errors = _open(browser, url, payload=PLACEHOLDER_PAYLOAD, provenance=None, urgency=urgency)
        assert page.inner_text("#care-ladder").strip() == PENDING_LADDER
        assert page.evaluate("document.getElementById('ladder-cap').hidden") is True and errors == []
        page.close()


def test_each_diagram_is_drawn_once_at_either_width_and_stays_readable_on_a_phone(served) -> None:
    browser, url = served
    measure = """() => { const shown = sel => [...document.querySelectorAll(sel)].filter(n => n.getClientRects().length);
        const wide = shown('.fig .fig-wide'), narrow = shown('.fig .fig-narrow');
        const sizes = [...wide, ...narrow].flatMap(svg => {
            const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
            return [...svg.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize) * scale); });
        return {wide: wide.length, narrow: narrow.length,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                smallest: sizes.length ? Math.min(...sizes) : null}; }"""

    def at(width: int) -> dict:
        page, errors = _open(browser, url, payload=None, provenance=None, width=width, height=900)
        found = page.evaluate(measure)
        page.close()
        assert errors == [] and found["overflow"] <= 0, (width, found, errors)
        return found

    desktop = at(1280)
    assert (desktop["wide"], desktop["narrow"]) == (7, 0)
    # One drawing of each diagram is shown at every width; the narrow ones up to 600 px.
    assert (at(601)["wide"], at(601)["narrow"]) == (7, 0) and (at(600)["wide"], at(600)["narrow"]) == (0, 7)
    # The narrow drawings reflow the nodes and labels; they do not shrink the wide drawing. On a 390 px phone
    # their smallest label is as large as the wide drawings' smallest label on a desktop (about 10 px); a wide
    # drawing scaled to that width would put the same label below 5 px. The floors at 360 and 320 px are what
    # the page measures today (9.2 and 8.0 px), stated so that a change that shrinks them is noticed.
    floors = {390: 10.0, 360: 9.0, 320: 8.0}
    for width, floor in floors.items():
        phone = at(width)
        assert (phone["wide"], phone["narrow"]) == (0, 7)
        assert phone["smallest"] >= floor, (width, phone["smallest"])
    assert at(390)["smallest"] >= desktop["smallest"] - 0.01


def test_no_label_runs_over_a_connector_or_a_box_edge_also_under_a_wider_serif_font(served) -> None:
    """The page's serif stack resolves to fonts of different widths (Iowan Old Style, Palatino, Georgia, the
    platform serif). A label that fits under the narrowest must not reach its connector under a wider one.
    (Review finding, 2026-11-11: the rewritten phrase of step 6 fitted only under Times metrics.) The check runs
    under the default serif and under each wider serif that is installed where the test runs."""
    browser, url = served
    installed = """(names) => { const c = document.createElement('canvas').getContext('2d'); const probe = 'mmmmllllWWWiii';
        c.font = '40px monospace'; const base = c.measureText(probe).width;
        return names.filter(n => { c.font = '40px "' + n + '", monospace'; return c.measureText(probe).width !== base; }); }"""
    overlaps = """() => { const out = [];
        const hit = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
        const inside = (a, b) => a.x >= b.x && a.y >= b.y && a.x + a.width <= b.x + b.width && a.y + a.height <= b.y + b.height;
        [...document.querySelectorAll('.fig svg')].filter(s => s.getClientRects().length).forEach((svg, i) => {
            const vb = svg.viewBox.baseVal;
            const texts = [...svg.querySelectorAll('text')].map(t => ({t: t.textContent.trim(), b: t.getBBox()}));
            const lines = [...svg.querySelectorAll('path, line')].map(e => e.getBBox()).filter(b => b.width < 3 || b.height < 3)
                .map(b => ({x: b.x - 0.5, y: b.y - 0.5, width: b.width + 1, height: b.height + 1}));
            const boxes = [...svg.querySelectorAll('rect')].map(e => e.getBBox()).filter(b => b.width > 20 && b.height > 14);
            texts.forEach((a, p) => {
                if (a.b.x < -0.5 || a.b.x + a.b.width > vb.width + 0.5) out.push([i, 'outside the drawing', a.t]);
                texts.slice(p + 1).forEach(o => { if (hit(a.b, o.b)) out.push([i, 'over another label', a.t, o.t]); });
                lines.forEach(l => { if (hit(a.b, l)) out.push([i, 'over a connector', a.t]); });
                boxes.forEach(b => { if (hit(a.b, b) && !inside(a.b, b)) out.push([i, 'over a box edge', a.t]); });
            });
        });
        return out; }"""
    checked = []
    for width in (1280, 390):
        page, errors = _open(browser, url, payload=None, provenance=None, width=width, height=900)
        fonts = [None, *page.evaluate(installed, ["DejaVu Serif", "Noto Serif", "Georgia", "Gelasio", "Palatino Linotype"])]
        for font in fonts:
            if font:
                page.add_style_tag(content=':root{--serif:"%s",serif}' % font)
                page.wait_for_timeout(200)
            found = page.evaluate(overlaps)
            assert found == [], (width, font or "default serif", found)
            checked.append((width, font or "default serif"))
        assert errors == []
        page.close()
    assert len(checked) >= 2
