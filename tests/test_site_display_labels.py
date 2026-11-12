"""The labels a reader sees on the public pages, and where the identifiers behind them stay readable.

The owner's request of 2026-11-11, as checks on the pages in a browser. The rule in force (site
``docs/agent_reference.md``, *Established UI conventions*): a display label comes from an explicit map keyed on the
exact stored value; a value with no entry is printed as stored and is never transformed; an identifier, version
string, file name or digest that leaves the main interface stays readable, word for word, in a Details, Provenance
or Source section the page already had, or in a title attribute or a link target.

* ``multi-turn/``: no Speaker control is drawn for a scenario and run with one speaker value, and no option reads
  "none". A grading-prompt digest and the register classifier's model string are in Provenance. A grade value or a
  turn type with no entry is printed as recorded, and "not addressed" has a cell text that is not "NA".
* ``llm/``: a scenario is headed by its number, a model row by the model's name, a cell by its attempt and date. The
  archive id, the provider:route spec, the served build and the classifier's served id are in Provenance. A model
  with no name entry is printed by its stored spec, in a row and in a figure.
* ``methods.html`` and ``technical/``: the measured J-space caption carries no source pair and keeps the selection
  rule; the exporter's note is in the fold under the figure. A census square's hover text names its set by a
  label; the set's stored name is on the set cell of the per-pair fold, and a set name that only extends a batch's
  name is printed as stored.
* The classifier (Multi-turn, LLM, Methods): a served id the page's map lists is named in the sentence, any other
  id is printed there as recorded, and either way the id is in Provenance or in the Source line.
* ``results/``: no row title is built from a stimulus-set name, and a stored value with no entry is printed as
  stored. Run ids, set names, analysis-rule ids and file paths are under each run's "Methods & source". The study
  rule has one wording, and two open runs with one heading have rows tables with different names.
* ``simulated-scenarios/``: the traced-model line names the feature source set and the methodology fold keeps its
  id; code-shaped topic values get names; a scenario with no target token gets one dash and a named quantity.
* ``dialect-differences/`` and ``translation/``: an empty or absent top token is not printed as "?", the last matrix
  column is not headed by a JSON key, a framing with no short name is printed as recorded, and a caption links its
  data file instead of printing the file's path.

The Clinical page's figure label is checked in ``tests/test_site_loading_states.py``, beside the tier line it heads.

These tests drive the site's real pages in Chromium with the server, the page wrapper and the skip rule of
``tests/test_site_loading_states.py``. Most data requests are answered from the test (``page.route``) with a
placeholder payload, or with a committed or sample file changed in memory; nothing is written into the site
checkout. A passing test is evidence about what a page does with a stored value. It is not evidence about a model
or about any measurement, and no measured value is asserted.

Every test here fails on site revision 9132d57 (the revision before the label cleanup) for the behaviour it guards.
One guards a defect of the cleanup itself (two open runs with one heading had rows tables named alike); it fails
there on the form of the name, which that revision built from a file name and a run id.

Skipped where the sibling site checkout, Playwright or a Chromium is missing.
"""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

import pytest

import test_site_loading_states as loading

# The server-and-browser fixture of the loading-state tests, with its skip rule for a missing site checkout,
# Playwright or Chromium. pytest registers it for this module under the same name.
site = loading.site
SITE = loading.SITE
_Page = loading._Page
_json = loading._json
_fixture = loading._fixture

# The text of the main interface: every text node outside a fold (``details``), outside the elements named in
# ``skip`` (a Provenance or Source block that is not a fold) and outside anything not displayed. Title attributes
# and link targets are not text, so an identifier kept there is not in the result.
_MAIN_TEXT = """(skip) => { const out = [];
    const walk = (node) => { for (const child of node.childNodes) {
        if (child.nodeType === 3) { out.push(child.nodeValue); continue; }
        if (child.nodeType !== 1) continue;
        if (['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT', 'DETAILS', 'IFRAME'].includes(child.tagName)) continue;
        if (skip.some((selector) => child.matches(selector))) continue;
        if (getComputedStyle(child).display === 'none') continue;
        walk(child); } };
    walk(document.body); return out.join(' ').replace(/\\s+/g, ' '); }"""

# How long a test waits for a label a page writes after its data file has answered.
WAIT_MS = 5_000

# A batch or stimulus-set name as the engine writes one: a stem, an eight-digit date and, usually, a time stamp.
STEM = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*_\d{8}(?:T\w*)?")


def _main_text(view: Any, *skip: str) -> str:
    return view.page.evaluate(_MAIN_TEXT, list(skip))


def _comes_to_hold(view: Any, selector: str, text: str) -> bool:
    """Whether the element holds ``text``, waiting a short time for it: a page writes some labels after a data
    file has answered. False when the element is missing or never holds the text."""
    from playwright.sync_api import Error

    try:
        view.page.wait_for_function("""([selector, text]) => { const node = document.querySelector(selector);
            return node !== null && node.textContent.includes(text); }""", arg=[selector, text], timeout=WAIT_MS)
    except Error:
        return False
    return True


def _need(name: str) -> None:
    if not (SITE / "data" / name).is_file():
        pytest.skip(f"the site checkout holds no data/{name}")


# ------------------------------------------------------------------ Multi-turn: the Speaker control

MULTI_TURN = loading.MULTI_TURN
REGISTER = "**/data/petri_register_drift.json"

_SPEAKER = """() => { const wrap = document.getElementById('pick-id-wrap'), box = wrap.getBoundingClientRect();
    return {display: getComputedStyle(wrap).display, width: box.width, height: box.height,
            options: [...document.getElementById('pick-id').options].map((option) => option.textContent)}; }"""
_OPTION_VALUES = "(id) => [...document.getElementById(id).options].map((option) => option.value)"


def _speaker(view: Any) -> dict:
    seen = view.page.evaluate(_SPEAKER)
    seen["drawn"] = view.page.is_visible("#pick-id-wrap")
    assert view.page.is_visible("#pick-id") is seen["drawn"]
    return seen


def _assert_not_drawn(seen: dict, where: object) -> None:
    """Computed visibility, not the ``hidden`` attribute: on 9132d57 the attribute was set and the control was
    still drawn, because the stylesheet's ``display: flex`` overrode it."""
    assert not seen["drawn"], where
    assert (seen["display"], seen["width"], seen["height"]) == ("none", 0, 0), (where, seen)


def _recorded_speakers(conversations: dict) -> dict[tuple[str, str], list]:
    """(scenario, run) -> the speaker values the file records for it, in the file's order."""
    out: dict[tuple[str, str], list] = {}
    for conversation in conversations["conversations"]:
        run = conversation["epoch"] if conversation.get("epoch") is not None else conversation.get("run_epoch")
        speakers = out.setdefault((conversation["seed_id"], str(run)), [])
        if conversation.get("identity") not in speakers:
            speakers.append(conversation.get("identity"))
    return out


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("mode", ["published", "sample"])
def test_multi_turn_draws_a_speaker_control_only_for_a_run_with_two_speakers(site, mode, width) -> None:
    """Regression (2026-11-11): every scenario and run with one speaker value drew a Speaker control whose single
    option read "none". With the committed files, and with the sample files under ``?sample=1``: every scenario and
    run is selected in turn. Only the speaker values of the file are read; no grade or count is asserted."""
    browser, base = site
    name = "petri_multiturn_conversations.json" if mode == "published" else "petri_multiturn_conversations.sample.json"
    _need(name)
    recorded = _recorded_speakers(_fixture(name))
    path = MULTI_TURN + ("" if mode == "published" else "?sample=1")
    walked: list[tuple[str, str]] = []
    with _Page(browser, base, path, width=width) as view:
        for scenario in view.page.evaluate(_OPTION_VALUES, "pick-seed"):
            view.page.select_option("#pick-seed", scenario)
            for run in view.page.evaluate(_OPTION_VALUES, "pick-epoch"):
                view.page.select_option("#pick-epoch", run)
                seen, speakers = _speaker(view), recorded[(scenario, run)]
                assert "none" not in [option.strip().lower() for option in seen["options"]], (scenario, run)
                if len(speakers) < 2:
                    _assert_not_drawn(seen, (scenario, run))
                else:
                    assert seen["drawn"] and seen["width"] > 0, (scenario, run, seen)
                    if None not in speakers:
                        assert seen["options"] == speakers, (scenario, run)
                walked.append((scenario, run))
        assert sorted(walked) == sorted(recorded) and walked
        assert view.errors == []


def _sample_conversations() -> tuple[dict, dict, dict]:
    """The sample conversations as a published file, and its first two scenarios (the entries of ``seeds``)."""
    conversations = loading._as_published(_fixture("petri_multiturn_conversations.sample.json"))
    first, second = conversations["seeds"][:2]
    return conversations, first, second


def _speaker_file() -> tuple[dict, str, str]:
    """The sample conversations changed in memory to hold the three states, and the ids of the two scenarios:
    scenario 1, run 1 records no speaker; scenario 1, run 2 records no speaker for one conversation and "patient"
    for another; scenario 2 records "patient" and "clinician"."""
    conversations, first, second = _sample_conversations()
    one, two = first["seed_id"], second["seed_id"]
    added = []
    for conversation in conversations["conversations"]:
        if conversation["seed_id"] == two:
            conversation["identity"] = "patient"
            added.append({**copy.deepcopy(conversation), "identity": "clinician",
                          "conversation_id": conversation["conversation_id"] + "-clinician"})
        elif conversation["seed_id"] == one:
            conversation["identity"] = None
            again = {**copy.deepcopy(conversation), "epoch": 2, "run_epoch": 2,
                     "conversation_id": conversation["conversation_id"] + "-run2"}
            added += [again, {**copy.deepcopy(again), "identity": "patient",
                              "conversation_id": again["conversation_id"] + "-patient"}]
    conversations["conversations"] += added
    return conversations, one, two


def _mt_published(conversations: dict) -> dict[str, Callable]:
    summary = loading._as_published(_fixture("petri_multiturn_summary.sample.json"))
    return loading._mt_routes(_json(summary), _json(conversations))


def test_multi_turn_speaker_control_with_one_two_and_an_unrecorded_speaker(site) -> None:
    """A placeholder file with the three states. One speaker value: no control, and the Tab key does not reach
    its select. Two recorded speakers: the control with their names. A conversation with no recorded speaker beside
    a named one: the control, and its option does not read "none"."""
    browser, base = site
    tab_lands_on = "() => document.activeElement.id"
    conversations, one, two = _speaker_file()
    with _Page(browser, base, MULTI_TURN, _mt_published(conversations)) as view:
        page = view.page
        assert page.evaluate(_OPTION_VALUES, "pick-seed")[:2] == [one, two]
        _assert_not_drawn(_speaker(view), "scenario 1, run 1")
        page.focus("#pick-epoch")
        page.keyboard.press("Tab")
        assert page.evaluate(tab_lands_on) != "pick-id"

        page.select_option("#pick-epoch", "2")
        seen = _speaker(view)
        assert seen["drawn"] and seen["options"] == ["not stated", "patient"]

        page.select_option("#pick-seed", two)
        seen = _speaker(view)
        assert seen["drawn"] and seen["options"] == ["patient", "clinician"]
        page.focus("#pick-epoch")
        page.keyboard.press("Tab")
        assert page.evaluate(tab_lands_on) == "pick-id"
        page.select_option("#pick-id", "clinician")
        assert page.input_value("#pick-id") == "clinician"

        page.select_option("#pick-seed", one)                     # back to one speaker: the control goes again
        _assert_not_drawn(_speaker(view), "scenario 1, run 1, after a scenario with two speakers")
        assert view.errors == []


# ------------------------------------------------------------------ Multi-turn: digests, grade values, turn types

DIGEST = "0a1b2c3d4e5f"
LEFT_OUT = "graded under an earlier grading prompt"
UNLISTED_VALUE, UNLISTED_ROLE = "brand_new_value", "clarifier_answer"

_PROVENANCE_ROWS = """(list) => [...document.querySelectorAll(list + ' > dt')].map(
    (dt) => [dt.textContent, dt.nextElementSibling.textContent])"""
_STRIP_CELLS = "() => [...document.querySelectorAll('#strip tbody td button')].map((button) => button.textContent)"


def test_multi_turn_keeps_an_earlier_grading_prompt_digest_in_provenance(site) -> None:
    """Regression (2026-11-11): the grade line under a reply, and the grade strip's hover text and accessible
    name, printed the digest of the grading prompt a superseded grade was judged under. The statement that such a
    grade is left out of the comparison stays where it was; the digest is listed once, in Provenance."""
    browser, base = site
    conversations, scenario, _ = _sample_conversations()
    measure = scenario["measures"][0]
    marked = 0
    for conversation in conversations["conversations"]:
        for exchange in conversation["exchanges"][:3]:
            grade = exchange["vals"].get(measure)
            if conversation["seed_id"] == scenario["seed_id"] and grade and "v" in grade:
                grade["superseded"] = DIGEST
                marked += 1
    assert marked
    with _Page(browser, base, MULTI_TURN, _mt_published(conversations)) as view:
        page = view.page
        lines = page.evaluate("() => [...document.querySelectorAll('#chat .grades .sup')].map((n) => n.textContent)")
        assert lines and all(LEFT_OUT in line and "left out of the comparison" in line for line in lines)
        page.click(f'#measure-chips .chip[data-measure="{measure}"]')
        cells = page.evaluate("""() => [...document.querySelectorAll('#strip tbody td.sup button')].map(
            (button) => [button.title, button.getAttribute('aria-label')])""")
        assert len(cells) == marked
        assert all(LEFT_OUT in text and DIGEST not in text for cell in cells for text in cell)
        assert DIGEST not in " ".join(lines) and DIGEST not in _main_text(view)
        # Provenance is a fold the page already had; the digest is one of its rows, word for word
        assert page.evaluate("() => document.getElementById('prov-list').closest('details').id") == "sec-prov"
        assert [value for _, value in page.evaluate(_PROVENANCE_ROWS, "#prov-list") if DIGEST in value] == [DIGEST]
        assert view.errors == []


def test_multi_turn_prints_a_grade_value_or_turn_type_without_an_entry_as_recorded(site) -> None:
    """Regression (2026-11-11): a grade-strip cell was built from the value id (the initials of a multi-word id,
    so "not addressed" read "NA" beside "n/a"), and a turn-type header was the id's first five characters. The
    cell texts and the headers now come from the page's tables: a value or a turn type the tables do not list is
    printed as the file records it, and "not addressed" has a cell text that cannot be read as "n/a". The tables'
    texts are short (3 and 5 characters at most), which keeps the key under the strip no longer than it was."""
    browser, base = site
    conversations, scenario, _ = _sample_conversations()
    changed = scenario["measures"][0]
    for measure in conversations["measures"]:
        if measure["id"] == changed:
            measure["values"] += [UNLISTED_VALUE, "not_addressed"]
    for conversation in conversations["conversations"]:
        if conversation["seed_id"] == scenario["seed_id"]:
            assert len(conversation["exchanges"]) >= 2
            conversation["exchanges"][-1]["vals"][changed] = {"v": UNLISTED_VALUE}
            conversation["exchanges"][-2]["vals"][changed] = {"v": "not_addressed"}
    scenario["roles"][next(i for i, role in enumerate(scenario["roles"]) if role)] = UNLISTED_ROLE
    initials = "".join(word[0] for word in UNLISTED_VALUE.split("_")).upper()
    with _Page(browser, base, MULTI_TURN, _mt_published(conversations)) as view:
        page = view.page
        cells: list[str] = []
        key = ""
        for measure in page.evaluate("""() => [...document.querySelectorAll('#measure-chips .chip')].map(
                (chip) => chip.dataset.measure)"""):
            page.click(f'#measure-chips .chip[data-measure="{measure}"]')
            cells += page.evaluate(_STRIP_CELLS)
            if measure == changed:
                key = page.inner_text("#strip-key")
        assert UNLISTED_VALUE in cells and initials not in cells
        assert UNLISTED_VALUE in key and UNLISTED_VALUE.replace("_", " ") not in key
        # the key pairs "not addressed" with its cell text, and that text is not "NA", which stood beside "n/a"
        not_addressed = re.search(r"(\S+) not addressed", key)
        assert not_addressed and not_addressed.group(1) in cells
        assert not_addressed.group(1).replace("/", "").lower() != "na" and "NA" not in cells
        heads = page.evaluate("""() => [...document.querySelectorAll('#strip thead tr.roles th:not(.row)')].map(
            (th) => [th.textContent, th.title])""")
        assert [UNLISTED_ROLE, UNLISTED_ROLE] in heads
        assert UNLISTED_ROLE[:5] not in [text for text, _ in heads]
        assert UNLISTED_ROLE in key and UNLISTED_ROLE.replace("_", " ") not in key
        # a value or a turn type with an entry gets the entry's short text
        listed_cells = [cell for cell in cells if cell not in (UNLISTED_VALUE, "n/a", "\u2014", "")]
        assert listed_cells and all(len(cell) <= 3 for cell in listed_cells), sorted(set(listed_cells))
        assert all(len(text) <= 5 for text, _ in heads if text != UNLISTED_ROLE), heads
        assert view.errors == []


# ------------------------------------------------------------------ a recorded id, named from a map

SCENARIOS_FILE = "**/data/simulated_scenarios.json"
GALLERY = "/simulated-scenarios/index.html"
SCENARIO = "/simulated-scenarios/scenario.html"
UNLISTED_ID = "placeholder/unlisted-id-9"


def _register_file(model: str) -> dict:
    return {**_fixture("petri_register_drift.json"), "models_served": [model]}


def _scenarios_file(count: int = 12) -> dict:
    """The committed scenarios payload cut to its first scenarios, so a test can change one field in memory."""
    payload = _fixture("simulated_scenarios.json")
    return {**payload, "scenarios": copy.deepcopy(payload["scenarios"][:count])}


def _source_set_file(source_set: str) -> dict:
    payload = _scenarios_file()
    base_model = payload["traced"]["graph_model"]
    payload["traced"] = {**payload["traced"], "source_set": source_set}
    payload["models_meta"] = [{**meta, "source_set": source_set} if meta["id"] == base_model else meta
                              for meta in payload["models_meta"]]
    return payload


# page -> (its path, the file that records the id, the route that serves it, a value the page's map lists, the
# element that names it, the existing section that keeps the id, and the fold that section is in). The listed
# values are the ones the engine writes: medlang_circuits/jev_client.py (the Jev classifier, typesafe/jev-1.13,
# served under a dated id) and medlang_circuits/neuronpedia_features.py (DEFAULT_SOURCE_SET).
NAMED_IDS = {
    "multi-turn register classifier": (
        MULTI_TURN, "petri_register_drift.json", REGISTER, _register_file, "typesafe/jev-1.13-20260917",
        "#reg-intro", "#prov-list", "sec-prov"),
    "scenario gallery source set": (
        GALLERY, "simulated_scenarios.json", SCENARIOS_FILE, _source_set_file, "gemmascope-transcoder-16k",
        "#sim-traced-model", "#sim-source-set", None),
}


@pytest.mark.parametrize("listed", [True, False], ids=["listed", "unlisted"])
@pytest.mark.parametrize("name", sorted(NAMED_IDS))
def test_a_recorded_id_is_named_from_the_page_map_and_stays_readable_in_its_section(site, name, listed) -> None:
    """Regression (2026-11-11): the Multi-turn register sentence printed the classifier's served model string, and
    the scenario gallery's traced-model line printed the feature source set's id. An id the page's map lists is
    now named in the sentence; an id with no entry is printed there as recorded. Either way the id is readable,
    word for word, in a section the page already had."""
    browser, base = site
    path, file_name, pattern, build, listed_id, named_in, kept_in, fold = NAMED_IDS[name]
    _need(file_name)
    recorded = listed_id if listed else UNLISTED_ID
    with _Page(browser, base, path, {pattern: _json(build(recorded))}) as view:
        page = view.page
        assert _comes_to_hold(view, kept_in, recorded), f"{kept_in} does not hold {recorded!r}"
        sentence = page.evaluate("(selector) => document.querySelector(selector).textContent", named_in)
        assert (recorded in sentence) is (not listed), sentence
        assert (recorded in _main_text(view)) is (not listed)
        kept_fold = page.evaluate("""(selector) => { const fold = document.querySelector(selector).closest('details');
            return fold ? (fold.id || fold.className) : null; }""", kept_in)
        assert kept_fold is not None and (fold is None or kept_fold == fold)
        assert view.errors == []


# ------------------------------------------------------------------ LLM responses

LLM = "/llm/index.html"
LLM_FILE = "**/data/advice_scenarios.json"
CLASSIFIER_FILE = "**/data/jev_calibration.json"
LLM_BATCH, LLM_OTHER_BATCH = "pairs_20990101T000000Z", "advmc_selected_20990102"
LLM_LISTED_SPEC, LLM_UNLISTED_SPEC = "anthropic:claude-haiku-4-5", "example-b:demo-model"
LLM_BUILD = "placeholder-build-0000"
LLM_UNLISTED_TIER, LLM_UNLISTED_FAMILY = "watchful_waiting", "multiple_choice_items"
# The classifier's served id as the engine writes it (medlang_circuits/jev_client.py: typesafe/jev-1.13, served under
# a dated id), which the three pages' maps list, and an id none of them lists.
LISTED_CLASSIFIER, CLASSIFIER_ID = "typesafe/jev-1.13-20260917", "placeholder/classifier-9"

_LLM_READ = """() => { const text = (node) => (node ? node.textContent : null);
    const heading = document.querySelector('#sc-meta > b');
    return {
        pager: text(document.querySelector('#sc-pager .state')), meta: text(document.getElementById('sc-meta')),
        heading: text(heading), heading_title: heading ? heading.title : null,
        rows: Object.fromEntries([...document.querySelectorAll('#sc-body > p.model-row')].map(
            (row) => [row.dataset.model, [row.textContent, row.title]])),
        tiers: [...document.querySelectorAll('#sc-body .resp-tier > b')].map(text),
        footers: [...document.querySelectorAll('#sc-body .cell')].filter(
            (cell) => cell.querySelector('.resp-text:not(.missing)')).map(
            (cell) => { const foot = cell.querySelector('p.resp-foot');
                        return [text(foot), foot ? foot.title : null]; }),
        note: text(document.getElementById('fam-note')), classifier: text(document.getElementById('jv-note-model')),
        provenance: Object.fromEntries([...document.querySelectorAll('#prov-list > dt')].map(
            (dt) => [dt.textContent, dt.nextElementSibling.innerText]))}; }"""


def _llm_file() -> dict:
    """The LLM page's sample fixture as a published file, changed in memory: the two scenarios carry archive ids
    of two batches, one of the two models has a spec the page's map lists, every response records one served
    build, and a tier key and a family key the page has no entry for are present beside ones it has."""
    text = json.dumps(loading._as_published(_fixture("advice_scenarios.sample.json")))
    for placeholder in ("example-a:demo-model", LLM_UNLISTED_SPEC, "demo-model-0000"):
        assert placeholder in text, f"the sample fixture no longer holds {placeholder!r}"
    payload = json.loads(text.replace("example-a:demo-model", LLM_LISTED_SPEC).replace("demo-model-0000", LLM_BUILD))
    first, second = payload["scenarios"]
    first.update(id=f"{LLM_BATCH}#3", family="natural_questions")
    second.update(id=f"{LLM_OTHER_BATCH}#1", family=LLM_UNLISTED_FAMILY)
    first["clinical"]["responses"][0]["samples"][0]["tier"] = "self_care"
    first["patient"]["responses"][0]["samples"][0]["tier"] = LLM_UNLISTED_TIER
    payload["families"] = [
        {"family": "natural_questions", "stimuli_file": "data/advice/stimuli_PLACEHOLDER_A.json",
         "n_items_registered": 1, "selection": {"kind": "pairs", "paths": [f"data/simulated/{LLM_BATCH}.json"]}},
        {"family": LLM_UNLISTED_FAMILY, "stimuli_file": "data/advice/stimuli_PLACEHOLDER_B.json",
         "n_items_registered": 1, "selection": {"kind": "pairs", "paths": [f"data/advice/{LLM_OTHER_BATCH}.json"]}}]
    return payload


def _llm_summary(spec: str) -> dict:
    """Placeholder per-model statistics, enough for the page to draw its two model figures. No value is asserted."""
    arm = {"n": 3, "mean_words": 100, "tier_mean_rank": 2.0,
           "flag_rates": {"disclaimer": 0.5, "professional_referral": 0.5, "clarifying_question": 0.5,
                          "question_then_referral": 0.25}}
    return {"model": spec, "clinical": arm, "patient": dict(arm),
            "similarity": {"reasked": 0.5, "reworded": 0.5, "n_stimuli": 1}}


def _llm_routes(classifier_id: str = LISTED_CLASSIFIER, figures: bool = False) -> dict[str, Callable]:
    classifier = {"is_mock": False, "cases_summary": {}, "models_served": [classifier_id],
                  "tier_order": ["self_care", "routine", "urgent", "emergency"]}
    payload = _llm_file()
    if figures:
        payload["model_summary"] = [_llm_summary(LLM_LISTED_SPEC), _llm_summary(LLM_UNLISTED_SPEC)]
    return {LLM_FILE: _json(payload), CLASSIFIER_FILE: _json(classifier)}


def _next_scenario(view: Any) -> None:
    view.page.click("#sc-pager button:not([disabled])")
    view.page.wait_for_function("() => /^scenario 2 /.test(document.querySelector('#sc-pager .state').textContent)")


def test_llm_main_interface_carries_no_archive_identifier_and_provenance_keeps_each(site) -> None:
    """Regression (2026-11-11): a scenario was headed by a date read out of its batch name (or by the raw archive
    id), each model row by its provider:route spec, each cell footer by the served build, the generation note by
    the batch name, and the Limitations sentence by the classifier's served id. Each of those is now in the
    Provenance list; the archive id, the spec and the build are also the title of the label that replaced them.
    The classifier's id here is one the page's map lists (an id with no entry is the next test but one)."""
    browser, base = site
    with _Page(browser, base, LLM, _llm_routes()) as view:
        seen = view.page.evaluate(_LLM_READ)
        # the heading is the number the pager counts; the archive id is its title
        assert seen["pager"].startswith("scenario 1 of ") and seen["heading"] == "Scenario 1"
        assert seen["heading_title"] == f"{LLM_BATCH}#3"
        # a model the page's map lists is named beside its answers; its spec is the row's title
        label, title = seen["rows"][LLM_LISTED_SPEC]
        assert label and label != LLM_LISTED_SPEC and ":" not in label and label in LLM_LISTED_SPEC
        assert title == LLM_LISTED_SPEC
        # one served build per model: under each archived answer the footer keeps the attempt and the date, and the
        # build is the footer's title
        assert seen["footers"]
        for text, title in seen["footers"]:
            assert "served as" not in text and LLM_BUILD not in text and title == f"served as {LLM_BUILD}"
        assert seen["classifier"] and LISTED_CLASSIFIER not in seen["classifier"]
        shown = _main_text(view, "#llm-prov")
        for identifier in (LLM_BATCH, LLM_LISTED_SPEC, LLM_BUILD, LISTED_CLASSIFIER):
            assert identifier not in shown, identifier
        assert STEM.findall(shown) == []
        # Provenance is the section the page already had; each identifier is in it, word for word
        assert view.page.evaluate("() => document.getElementById('prov-list').closest('section').id") == "llm-prov"
        assert f"{LLM_BATCH}#3" in seen["provenance"]["scenario id"]
        assert f"{LLM_LISTED_SPEC} · served as {LLM_BUILD}" in seen["provenance"]["models"]
        assert [row for row in seen["provenance"].values() if LISTED_CLASSIFIER in row] == [LISTED_CLASSIFIER]
        # the row for the scenario on screen follows the pager
        _next_scenario(view)
        seen = view.page.evaluate(_LLM_READ)
        assert seen["heading"] == "Scenario 2" and seen["heading_title"] == f"{LLM_OTHER_BATCH}#1"
        assert f"{LLM_OTHER_BATCH}#1" in seen["provenance"]["scenario id"]
        assert LLM_OTHER_BATCH not in _main_text(view, "#llm-prov")
        assert view.errors == []


def test_llm_prints_a_tier_a_model_or_a_family_without_an_entry_as_stored(site) -> None:
    """Regression (2026-11-11): the tier key ``self_care`` was printed as stored in an answer cell, and a family
    key the page had no word for was printed with its underscores replaced (and its scenarios were headed
    "sentence completion"). A key with an entry now gets the entry's words; a key without one is printed as
    stored, or is left out where the page has no word for it, and Provenance prints it as stored. A model spec
    with no name entry was printed by the last part of its route in the figures ("demo-model"): a row and a
    figure now print the whole stored spec."""
    browser, base = site
    with _Page(browser, base, LLM, _llm_routes(figures=True)) as view:
        seen = view.page.evaluate(_LLM_READ)
        assert LLM_UNLISTED_TIER in seen["tiers"] and "self_care" not in seen["tiers"]
        assert seen["rows"][LLM_UNLISTED_SPEC] == [LLM_UNLISTED_SPEC, LLM_UNLISTED_SPEC]
        # the label of each figure row is the first text of its <text> element
        figures = view.page.evaluate("""() => Object.fromEntries(['fig-profiles-body', 'fig-flags-body'].map((id) =>
            [id, [...document.querySelectorAll('#' + id + ' svg text')].map(
                (text) => (text.firstChild && text.firstChild.nodeType === 3 ? text.firstChild.nodeValue : ''))]))""")
        for figure, labels in figures.items():
            assert LLM_UNLISTED_SPEC in labels, (figure, labels)
            assert LLM_UNLISTED_SPEC.rsplit(":", 1)[1] not in labels, (figure, labels)
            assert LLM_LISTED_SPEC not in labels, (figure, labels)      # a listed model keeps its name
        spaced = LLM_UNLISTED_FAMILY.replace("_", " ")
        assert spaced not in seen["note"] and LLM_UNLISTED_FAMILY not in seen["note"]
        assert LLM_UNLISTED_FAMILY in seen["provenance"]["stimulus sets"]
        assert spaced not in seen["provenance"]["stimulus sets"]
        _next_scenario(view)                                      # the scenario of the family with no entry
        meta = view.page.evaluate(_LLM_READ)["meta"]
        assert meta.startswith("Scenario 2") and "completion" not in meta and "question" not in meta
        assert spaced not in meta and LLM_UNLISTED_FAMILY not in meta
        assert view.errors == []


# ------------------------------------------------------------------ Methods and Technical

METHODS = "/methods.html"
TECHNICAL = loading.TECHNICAL
DEPTH_FILE = "**/data/jlens_depth.json"
NOTE = "Placeholder note that names the pair pairs_20990101T000000Z#3 and how it was chosen."
UNLISTED_SET = "custom_set_X"


_JSPACE_CAPTION = """() => { const cap = document.querySelector('figure.jspace .jspace-cap');
    return {text: cap.textContent, links: cap.querySelectorAll('a').length}; }"""


def test_methods_jspace_caption_names_no_source_pair_and_the_fold_keeps_the_note(site) -> None:
    """Regression (2026-11-11): the measured caption on the Methods page appended the exporter's note and a source
    line, so the batch name was printed twice in the caption. Both are now in the fold under the figure, word for
    word, and only while the figure is measured (the illustrative states are checked in the loading-state tests).
    The caption keeps the selection rule: the exporter's clause, printed when the file's note holds it word for
    word, and no selection wording of the page's own when the note words the rule another way."""
    browser, base = site
    source = (SITE / METHODS.lstrip("/")).read_text(encoding="utf-8")
    selected = re.search(r"var SELECTED='([^']+)';", source).group(1)
    payload = {"empirical": True, "note": NOTE, "source": {"stem": "pairs_20990101T000000Z", "index": 3},
               "panels": loading.MEASURED_PANELS}
    with_rule = {**payload, "note": f"PLACEHOLDER readout, pairs_20990101T000000Z#3, {selected}. More of the note."}
    with _Page(browser, base, METHODS, {loading.JSPACE_FILE: _json(with_rule)}) as view:
        caption = view.page.evaluate(_JSPACE_CAPTION)
        assert f"one measured pair, {selected}. " in caption["text"] and caption["links"] == 0
        assert STEM.findall(caption["text"]) == [] and "PLACEHOLDER" not in caption["text"]
        assert view.errors == []
    with _Page(browser, base, METHODS, {loading.JSPACE_FILE: _json(payload)}) as view:
        page = view.page
        caption = page.evaluate(_JSPACE_CAPTION)
        assert caption["text"].startswith("Empirical J-lens residual stream readout") and caption["links"] == 0
        assert STEM.findall(caption["text"]) == [] and "Source data" not in caption["text"]
        assert "one measured pair. " in caption["text"] and "chosen" not in caption["text"]
        assert "pairs_20990101T000000Z" not in _main_text(view)
        note = page.evaluate("""() => { const note = document.getElementById('jspace-note');
            return {hidden: note.hidden, text: note.textContent, in_fold: note.closest('details') !== null,
                    targets: [...note.querySelectorAll('a')].map((a) => a.getAttribute('href'))}; }""")
        assert note["hidden"] is False and note["in_fold"]
        assert NOTE in note["text"] and "pair pairs_20990101T000000Z#3" in note["text"]
        files = [target.rsplit("/", 1)[1] for target in note["targets"]]
        assert files == ["jspace.json", "pairs_20990101T000000Z.json"]
        page.click("figure.jspace + details.fold > summary")
        assert page.is_visible("#jspace-note") and view.errors == []


@pytest.mark.parametrize("listed", [True, False], ids=["listed", "unlisted"])
@pytest.mark.parametrize("name", ["methods", "llm"])
def test_the_classifier_is_named_from_the_page_map_and_its_id_is_in_the_source_section(site, name, listed) -> None:
    """Regression (2026-11-11): on the Methods page (Step 5b) and the LLM page (Limitations) the served model id
    replaced the classifier's name in the sentence, and on Methods in the matrix's column header too. A served id
    the page's map lists is now named there, by the name the markup carries; an id with no entry is printed as
    recorded, as on the Multi-turn page. Either way the id the file records is in the section's Source line or
    the Provenance list, under the heading the three pages share."""
    browser, base = site
    recorded = LISTED_CLASSIFIER if listed else CLASSIFIER_ID
    if name == "methods":
        _need("jev_calibration.json")
        routes = {CLASSIFIER_FILE: _json({**_fixture("jev_calibration.json"), "cases_summary": {},
                                           "models_served": [recorded]})}
        path, named, kept_in, skip = METHODS, ("#jv-model", "#jv-table thead th.axis"), "#jv-prov", ("#jv-prov",)
    else:
        routes = _llm_routes(recorded)
        path, named, kept_in, skip = LLM, ("#jv-note-model",), "#prov-list", ("#llm-prov",)
    source = (SITE / path.lstrip("/")).read_text(encoding="utf-8")
    static = re.search(rf'id="{named[0][1:]}"[^>]*>([^<]+)<', source).group(1)
    with _Page(browser, base, path, routes) as view:
        page = view.page
        assert _comes_to_hold(view, kept_in, recorded), f"{kept_in} does not hold {recorded!r}"
        # the heading of the id: the term of the Provenance row that holds it, or the words before it in the Source line
        heading = page.evaluate("""([selector, id]) => { const kept = document.querySelector(selector);
            const row = [...kept.querySelectorAll('dd')].find((dd) => dd.textContent === id);
            return row ? row.previousElementSibling.textContent : kept.textContent; }""", [kept_in, recorded])
        assert heading == "classifier model" or f"classifier model {recorded}" in heading, heading
        texts = [page.evaluate("(selector) => document.querySelector(selector).textContent", s) for s in named]
        if listed:
            assert texts[0] == static and all(static in text and recorded not in text for text in texts)
            assert recorded not in _main_text(view, *skip)
        else:
            assert texts[0] == recorded and all(recorded in text and static not in text for text in texts)
        assert page.is_visible(kept_in) and view.errors == []


def test_methods_draws_no_translated_line_without_a_translated_sentence(site) -> None:
    """Regression (2026-11-11): the "Reading the layers" figure printed the clinical sentence under the label
    "translated:" when the file's exemplar carried no ``translated_sentence``. A line is drawn only for that
    field's own value."""
    browser, base = site
    _need("jlens_depth.json")
    depth = _fixture("jlens_depth.json")
    lines = "() => [...document.querySelectorAll('#rl-fig svg text')].map((t) => t.textContent)"
    without = {**depth, "exemplar": {k: v for k, v in depth["exemplar"].items() if k != "translated_sentence"}}
    with _Page(browser, base, METHODS, {DEPTH_FILE: _json(without)}) as view:
        drawn = view.page.evaluate(lines)
        assert drawn and [line for line in drawn if line.startswith("translated:")] == []
        assert view.errors == []
    placeholder = "Placeholder rewritten sentence"
    with_field = {**depth, "exemplar": {**depth["exemplar"], "translated_sentence": placeholder}}
    with _Page(browser, base, METHODS, {DEPTH_FILE: _json(with_field)}) as view:
        drawn = [line for line in view.page.evaluate(lines) if line.startswith("translated:")]
        assert drawn == [f"translated: “{placeholder}”"] and view.errors == []


def test_technical_census_hover_text_names_a_set_by_its_label_and_the_fold_keeps_its_name(site) -> None:
    """Regression (2026-11-11): each census square's hover text carried its set's stored name. The hover text now
    names the set by the page's label for it; the stored name is on the set's cell in the per-pair fold, in the
    link target and in the title. A set name the page's map does not read is printed as stored, and so is a name
    that extends a batch's name with a suffix: it is another set, not that batch. The committed file is served
    with two sets renamed; no value of it is asserted."""
    browser, base = site
    _need("jlens_depth.json")
    depth = _fixture("jlens_depth.json")
    renamed, suffixed = (block["id"] for block in depth["blocks"][:2])
    extended = f"{suffixed}_txplaceholder"
    payload = json.loads(json.dumps(depth).replace(renamed, UNLISTED_SET).replace(suffixed, extended))
    with _Page(browser, base, TECHNICAL, {DEPTH_FILE: _json(payload)}) as view:
        page = view.page
        page.wait_for_selector("#ad-blocks .ucensus-sq", state="attached")
        titles = page.evaluate("() => [...document.querySelectorAll('#ad-blocks .ucensus-sq')].map((s) => s.title)")
        of_extended = [title for title in titles if title.endswith(f" of the {extended}")]
        assert of_extended and len(of_extended) == sum(extended in title for title in titles)
        assert titles and [title for title in titles if STEM.search(title) and extended not in title] == []
        assert len(of_extended) < len(titles)                     # the other sets are named by their labels
        unlisted = [title for title in titles if UNLISTED_SET in title]
        assert unlisted and all(title.endswith(f" of the {UNLISTED_SET}") for title in unlisted)
        cells = page.evaluate("""() => [...document.querySelectorAll('#ad-pairs tbody tr td:first-child a')].map(
            (a) => ({text: a.textContent, target: a.getAttribute('href'), title: a.title,
                     in_fold: a.closest('details') !== null}))""")
        assert cells
        for cell in cells:
            stored = PurePosixPath(cell["target"]).stem
            assert cell["in_fold"] and stored in cell["title"], cell
        assert view.errors == []


# ------------------------------------------------------------------ a link to a file

def _open_run(view: Any) -> None:
    view.page.click("#cat-body tr.cat-run td.c-exp button")
    view.page.wait_for_selector("#cat-body tr.cat-detail .det-links a[download]")


def _archive_note(payload: dict) -> str:
    """The address of a scenario whose record says its render is not in the public demonstration set."""
    scenario = payload["scenarios"][0]
    for record in (scenario, *(scenario.get("models") or {}).values()):
        record.pop("html", None)
        record.pop("diff_html", None)
        record["screening"] = {**(record.get("screening") or {}), "status": "passed"}
    return f"{SCENARIO}?sim={scenario['index']}"


def _archive_link() -> tuple:
    scenarios = _scenarios_file(2)
    return (_archive_note(scenarios), {SCENARIOS_FILE: _json(scenarios)},
            '#sim-card .pending-note a[href$="simulated_archive.csv"]', "data/simulated_archive.csv", None)


# name -> (the data file the case reads from the site checkout, a builder of: path, routes, the link, what its
# target ends with, a step to take first). The builders run inside the test, after the site fixture's skip rule.
LINK_CASES: dict[str, tuple[str, Callable[[], tuple]]] = {
    "technical census caption": ("jlens_depth.json", lambda: (
        TECHNICAL, {}, "#ad-blocks + p.cap a:nth-of-type(2)", "data/jlens_depth.json", None)),
    "translation at-scale caption": ("translation_scale.json", lambda: (
        "/translation/index.html", {}, "#tx-scale-cap a", "data/translation_scale.json", None)),
    "scenario archive note": ("simulated_scenarios.json", _archive_link),
    "llm generation note": ("advice_scenarios.sample.json", lambda: (
        LLM, _llm_routes(), "#sc-gen > a:first-of-type", f"{LLM_BATCH}.json", None)),
    "results run download": ("results_catalogue/index.json", lambda: (
        RESULTS, {RESULTS_INDEX: _json(_one_run_index())}, "#cat-body tr.cat-detail .det-links a[download]",
        ".json", _open_run)),
}


@pytest.mark.parametrize("name", sorted(LINK_CASES))
def test_a_link_to_a_file_names_it_in_its_target_and_not_in_its_text(site, name) -> None:
    """Regression (2026-11-11): five places printed a file's name or path as the visible text (a caption's link
    text, a caption's plain "source:" path, a note's link text, the generation note's batch name, a run's two
    download links). Each is now a link whose words say what the file is; the file's name is the link's target."""
    browser, base = site
    file_name, build = LINK_CASES[name]
    _need(file_name)
    path, routes, selector, target, first = build()
    with _Page(browser, base, path, routes) as view:
        if first is not None:
            first(view)
        view.page.wait_for_load_state("networkidle")
        links = view.page.evaluate("""(selector) => [...document.querySelectorAll(selector)].map(
            (a) => ({text: a.textContent, target: a.getAttribute('href'), around: a.parentElement.textContent}))""",
                                   selector)
        assert links, f"no link {selector}"
        for link in links:
            assert link["target"].endswith(target), link
            assert link["text"].strip() and "/" not in link["text"], link
            # neither the link nor the sentence around it prints the file's name, with or without its extension
            assert PurePosixPath(link["target"]).stem not in link["around"], link
        assert view.errors == []


# ------------------------------------------------------------------ Results

RESULTS = "/results/index.html"
RESULTS_INDEX = "**/data/results_catalogue/index.json"
UNLISTED_STEM = "zzqx_probe_s9p9_20990101T000000Z"
UNLISTED_CLASS, UNLISTED_INSTRUMENT = "made_up_class", "zzinstrument"
_DATE_TOKEN = re.compile(r"\d{8}(T\w*)?", re.IGNORECASE)

_ROWS_TABLE_NAMES = """() => [...document.querySelectorAll('#cat-body tr.cat-detail table.row-table')]
    .map((table) => table.getAttribute('aria-label'))"""
_RESULT_ROWS = """() => [...document.querySelectorAll('#cat-body tr.cat-run')].map((row) => {
    const text = (selector) => { const node = row.querySelector(selector); return node ? node.innerText : null; };
    return {run: row.dataset.run, title: text('td.c-exp .cat-x'), stem_line: text('td.c-exp .x-set'),
            model: [...row.querySelectorAll('td.c-model .ln')].map((n) => n.textContent),
            badges: [...row.querySelectorAll('td.c-ctx .bdg')].map((n) => n.textContent)}; })"""


def _code_tokens(stem: str) -> list[str]:
    """The tokens of a stimulus-set name that are codes, not words: a letter and a digit together (``r2``,
    ``s2p5``, ``k200``, ``2panel``). The date stamp is not one."""
    return [token for token in stem.lower().split("_")
            if not _DATE_TOKEN.fullmatch(token) and re.search(r"[a-z]", token) and re.search(r"\d", token)]


def _words(text: str) -> list[str]:
    return [word for word in re.split(r"[^a-z0-9]+", text.lower()) if word]


def _one_run_index() -> dict:
    """The committed index cut to one run that has rows, so its title is no other run's."""
    index = _fixture("results_catalogue/index.json")
    with_rows = [r for r in index["runs"] if r.get("rows_file") and r.get("stimuli_file") and not r.get("instrument")
                 and r.get("visibility") == "public"]
    # the run that the most analysis rules include, so the rule ids are among the identifiers checked
    run = max(with_rows, key=lambda r: sum(1 for parts in r["analysis_parts"].values() if parts))
    return {**index, "runs": [run]}


def _labelled_index() -> tuple[dict, dict]:
    """The committed index cut to one run per stimulus set whose name holds a code token, plus three placeholder
    runs: a set of a family the page cannot have an entry for, a run of an evidence class it has none for, and an
    instrument run of an instrument it has none for."""
    index = _fixture("results_catalogue/index.json")
    coded: dict[str, dict] = {}
    for run in index["runs"]:
        if _code_tokens(run["stem"]) and not run.get("instrument"):
            coded.setdefault(run["stem"], run)
    plain = next(run for run in index["runs"] if not run.get("instrument"))
    family = {**copy.deepcopy(plain), "stem": UNLISTED_STEM, "run_dir": UNLISTED_STEM, "stimulus_class": "unclassified"}
    evidence = {**copy.deepcopy(plain), "run_dir": plain["run_dir"] + "__placeholder-model",
                "model": "placeholder-model", "evidence_class": UNLISTED_CLASS}
    other = {**copy.deepcopy(plain), "instrument": UNLISTED_INSTRUMENT, "model": None,
             "run_dir": f"{plain['stem']}__{UNLISTED_INSTRUMENT}_placeholder"}
    placeholders = {"family": family, "evidence": evidence, "instrument": other}
    return {**index, "runs": [*coded.values(), *placeholders.values()]}, placeholders


def test_results_row_titles_are_not_built_from_set_names_and_unlisted_values_are_printed_as_stored(site) -> None:
    """Regression (2026-11-11): a row's title was the stimulus set's file stem with its date removed, its
    underscores split and its first letter capitalised ("Boostgrid lowrank r2"), and an evidence class was printed
    with its underscores replaced. No title now holds an underscore or a code token of its set's name. A set of a
    family with no entry gets a label that holds no token of the name, and keeps the name, as stored, on the line
    under it. An evidence class or an instrument with no entry is printed as stored."""
    browser, base = site
    _need("results_catalogue/index.json")
    index, placeholders = _labelled_index()
    stems = {run["run_dir"]: run["stem"] for run in index["runs"]}
    with _Page(browser, base, RESULTS, {RESULTS_INDEX: _json(index)}) as view:
        view.page.wait_for_selector("#cat-body tr.cat-run")
        while view.page.is_visible("#cat-more"):
            view.page.click("#cat-more")
        rows = {row["run"]: row for row in view.page.evaluate(_RESULT_ROWS)}
        assert sorted(rows) == sorted(stems)
        for run, row in rows.items():
            assert row["title"] and "_" not in row["title"], row
            assert set(_code_tokens(stems[run])) & set(_words(row["title"])) == set(), row
        family = rows[placeholders["family"]["run_dir"]]
        name_tokens = [token for token in UNLISTED_STEM.split("_") if not _DATE_TOKEN.fullmatch(token)]
        assert set(name_tokens) & set(_words(family["title"])) == set(), family
        assert family["stem_line"] == UNLISTED_STEM
        assert UNLISTED_CLASS in rows[placeholders["evidence"]["run_dir"]]["badges"]
        assert f"instrument: {UNLISTED_INSTRUMENT}" in rows[placeholders["instrument"]["run_dir"]]["model"]
        assert view.errors == []


def test_results_run_keeps_its_identifiers_under_methods_and_source(site) -> None:
    """Regression (2026-11-11): every row printed its stimulus set's name under its title, and an opened run
    printed analysis-rule ids and file paths in its main lines. With one run of the committed index: the row and
    the opened run print none of them outside a fold, and the run's "Methods & source" fold prints each one, word
    for word. No count or measured value is asserted."""
    browser, base = site
    _need("results_catalogue/index.json")
    index = _one_run_index()
    (run,) = index["runs"]
    rules = [rule for rule, parts in run["analysis_parts"].items() if parts]
    identifiers = [run["run_dir"], run["stem"], run["rows_file"], run["stimuli_file"], *rules]
    with _Page(browser, base, RESULTS, {RESULTS_INDEX: _json(index)}) as view:
        view.page.wait_for_selector("#cat-body tr.cat-run")
        (row,) = view.page.evaluate(_RESULT_ROWS)
        assert row["stem_line"] is None and "_" not in row["title"]
        _open_run(view)
        view.page.wait_for_load_state("networkidle")
        shown = _main_text(view)
        for identifier in identifiers:
            assert identifier not in shown, identifier
        kept = view.page.evaluate("""() => {
            const fold = document.querySelector('#cat-body tr.cat-detail details.det-src');
            return {summary: fold.querySelector('summary').textContent, text: fold.textContent}; }""")
        assert "Methods" in kept["summary"]
        for identifier in identifiers:
            assert identifier in kept["text"], identifier
        labels = view.page.evaluate(_ROWS_TABLE_NAMES)
        assert labels and all(run["stem"] not in label and ".json" not in label for label in labels)
        # The study rule is worded as eligibility, never as inclusion: a rule admits parts, and a published
        # statistic may use fewer. The badge of the row and of each part reads "study-eligible"; the rule's full
        # name is in the filter option and in the open run's line.
        short = "study-eligible"
        included = [badge for badge in row["badges"] if "eligible" in badge]
        assert len(included) == 1 and re.fullmatch(rf"{short}(?: \(\d+ of \d+ parts\))?", included[0]), row["badges"]
        assert not any(badge.startswith(("in ", "review:")) or "analysis" in badge for badge in row["badges"])
        said = view.page.evaluate("""() => {
            const lines = document.querySelectorAll('#cat-body tr.cat-detail .det > dl.kv dd');
            return {filter: [...document.querySelectorAll('#f-membership option')].map((option) => option.textContent),
                    open_run: lines[lines.length - 1].textContent,
                    parts: [...document.querySelectorAll('#cat-body tr.cat-detail section.part .part-state .bdg')].map(
                        (badge) => badge.textContent)}; }""")
        named = [option for option in said["filter"] if option.startswith("eligible for the ")]
        assert len(named) == 1, said["filter"]
        phrase = named[0][len("eligible for the "):named[0].index(" (")]
        assert [option for option in said["filter"] if option.startswith(f"not eligible for the {phrase} (")] != []
        assert not any(option.startswith(("in the ", "not in the ")) for option in said["filter"]), said["filter"]
        assert said["open_run"].startswith(f"{phrase}: ") and short in said["parts"], said
        assert view.errors == []


def test_results_study_context_states_each_fact_once(site) -> None:
    """(2026-11-12, owner request) The Study context cell of a run's row holds only the words the row needs: no
    filler word before the eligibility wording, no ``review:`` before a review status, and no evidence-class words
    that the experiment title of the same row already gives. The stored evidence class and its definition stay in
    the badge's title.

    (2026-11-12, review of patientwords#33) The second line states eligibility under an analysis rule, never use
    in a result: a rule admits parts, and a collector may keep fewer (``scripts/urgency_headline.py`` leaves out
    every population but the observational one). The rule's id and recorded label are in the badge's title."""
    browser, base = site
    _need("results_catalogue/index.json")
    with _Page(browser, base, RESULTS) as view:
        view.page.wait_for_selector("#cat-body tr.cat-run")
        while view.page.is_visible("#cat-more"):
            view.page.click("#cat-more")
        rows = view.page.evaluate("""() => [...document.querySelectorAll('#cat-body tr.cat-run')].map((row) => {
            const cell = row.querySelector('td.c-ctx'), badges = cell.querySelectorAll('.bdg'), evidence = badges[0];
            return {title: row.querySelector('td.c-exp .cat-x').innerText,
                    lines: [...cell.querySelectorAll('.ln')].map((n) => n.innerText.trim()),
                    evidence: evidence.textContent, stored: evidence.getAttribute('title'),
                    rule: badges[1].getAttribute('title')}; })""")
        assert rows
        for row in rows:
            assert not any(line.startswith(("in ", "review:")) for line in row["lines"]), row
            eligibility = row["lines"][1].split(" (")[0]
            assert eligibility in ("study-eligible", "not eligible") or eligibility.endswith("-eligible only"), row
            assert "analysis" not in row["lines"][1], row
            if eligibility != "not eligible":
                assert row["rule"].startswith("Eligible under analysis rule ") and "fewer" in row["rule"], row
            assert row["stored"].startswith("evidence_class: "), row
        named = [row for row in rows if row["title"].startswith(("Hand-authored set", "Third-party text set"))]
        assert len({row["title"].split(" ")[0] for row in named}) == 2          # both classes are in the index
        for row in named:
            assert row["evidence"] == "exploratory", row
            assert "exploratory_hand_authored" in row["stored"] or "exploratory_third_party_source" in row["stored"]
        # a row whose title does not name the class keeps the whole evidence label
        assert "exploratory, post-registration" in {row["evidence"] for row in rows}
        assert view.errors == []


def test_results_search_matches_the_second_line_a_row_shows(site) -> None:
    """Regression (2026-11-12, review of patientwords#33): the second line of a Model cell printed a label, such
    as ``lens reader pairs``, that the search text did not hold, so searching for the words a row shows listed no
    run. The search text now holds that line. The stored code in the run id still lists the same runs."""
    browser, base = site
    _need("results_catalogue/index.json")
    with _Page(browser, base, RESULTS) as view:
        view.page.wait_for_selector("#cat-body tr.cat-run")

        def listed(query: str) -> dict[str, str]:
            view.page.fill("#f-q", query)
            while view.page.is_visible("#cat-more"):
                view.page.click("#cat-more")
            return dict(view.page.evaluate("""() => [...document.querySelectorAll('#cat-body tr.cat-run')].map((row) => {
                const lines = row.querySelectorAll('td.c-model .ln');
                return [row.dataset.run, lines.length > 1 ? lines[1].textContent : '']; })"""))

        everything = listed("")
        label = "lens reader pairs"
        shown = {run for run, second in everything.items() if label in second}
        assert shown and all("lenspairs" in run for run in shown), "no row of the committed index shows the label"
        by_label, by_code = listed(label), listed("lenspairs")
        assert shown <= set(by_label) and len(by_label) < len(everything), sorted(by_label)[:5]
        assert shown <= set(by_code), sorted(by_code)[:5]
        assert view.errors == []


def test_results_rows_tables_of_two_runs_with_one_heading_are_named_apart(site) -> None:
    """Regression (2026-11-12, fix round of the label cleanup): a rows table was named with the open run's heading
    alone, so two open runs with the same title and model had rows tables with the same accessible name. Where
    another run of the index has the same heading, the name now ends with the run id, as each row button's name
    does. A run whose heading is its own keeps a name without the id (the test above). The committed index is cut
    to one run and a copy of it under another run id, of the form the index uses for one set measured on one model
    by two backends (the set's name alone, and the set's name with the model); no count or measured value is
    asserted."""
    browser, base = site
    _need("results_catalogue/index.json")
    index = _one_run_index()
    (run,) = index["runs"]
    other_id = run["stem"] if run["run_dir"] != run["stem"] else f"{run['stem']}__{run['model']}"
    twin = {**copy.deepcopy(run), "run_dir": other_id}
    index["runs"].append(twin)
    with _Page(browser, base, RESULTS, {RESULTS_INDEX: _json(index)}) as view:
        page = view.page
        page.wait_for_selector("#cat-body tr.cat-run")
        rows = page.evaluate(_RESULT_ROWS)
        assert [row["run"] for row in rows] == [run["run_dir"], twin["run_dir"]]
        assert rows[0]["title"] == rows[1]["title"] and rows[0]["model"][0] == rows[1]["model"][0]
        names: dict[str, list[str]] = {}
        for row in rows:
            page.click(f'#cat-body tr.cat-run[data-run="{row["run"]}"] td.c-exp button')
            page.wait_for_selector(f'#cat-body tr.cat-run[data-run="{row["run"]}"] + tr.cat-detail table.row-table')
            names[row["run"]] = page.evaluate("""(run) => [...document.querySelectorAll(
                `#cat-body tr.cat-run[data-run="${run}"] + tr.cat-detail table.row-table`)].map(
                (table) => table.getAttribute('aria-label'))""", row["run"])
        for run_dir, labels in names.items():
            assert labels and all(label.endswith(f", run {run_dir}") for label in labels), (run_dir, labels)
        both = [label for labels in names.values() for label in labels]
        assert len(both) == len(set(both))
        assert view.errors == []


# ------------------------------------------------------------------ Scenarios

LISTED_TOPIC, UNLISTED_TOPIC = "infectious_skin", "made_up_code-value"

_GALLERY_READ = """() => ({
    conditions: [...document.querySelectorAll('#sim-fsel-condition option')].map((option) => option.textContent),
    targets: [...document.querySelectorAll('#sim-sum-body tr:not(.sim-detail) > td:nth-child(3)')].map(
        (cell) => cell.textContent),
    shifts: [...document.querySelectorAll('#sim-sum-body td.sum-slope svg title')].map(
        (title) => title.textContent)})"""


def test_scenario_gallery_condition_filter_names_code_shaped_topics(site) -> None:
    """Regression (2026-11-11): the condition filter listed code-shaped topic values as stored ("infectious_skin",
    and "mental_health" beside "mental health"). A value the page's map lists gets its name, two spellings of one
    name are one option, and any other topic is printed as stored."""
    browser, base = site
    _need("simulated_scenarios.json")
    payload = _scenarios_file()
    for scenario, topic in zip(payload["scenarios"], (LISTED_TOPIC, UNLISTED_TOPIC, "mental_health", "mental health")):
        scenario["topic"] = topic
    with _Page(browser, base, GALLERY, {SCENARIOS_FILE: _json(payload)}) as view:
        view.page.wait_for_function(loading._FILTERS_LOADED, arg=["sim-fsel-condition"])
        conditions = view.page.evaluate(_GALLERY_READ)["conditions"]
        assert UNLISTED_TOPIC in conditions
        assert LISTED_TOPIC not in conditions and "mental_health" not in conditions
        assert conditions.count("mental health") == 1 and len(conditions) == len(set(conditions))
        assert view.errors == []


def test_a_scenario_without_a_target_token_gets_one_dash_and_a_named_quantity(site) -> None:
    """Regression (2026-11-11): with no target token the gallery's Target cell read as a quoted dash, the hover
    text of its shift glyph read "prob():", and the scenario page's probability line read "prob() =". The committed
    payload is cut to two scenarios and the target token of the first is removed in memory; its probabilities are
    left as they are and none is asserted."""
    browser, base = site
    _need("simulated_scenarios.json")
    payload = _scenarios_file(2)
    without = payload["scenarios"][0]
    for record in (without, *(without.get("models") or {}).values()):
        record["target_token"] = None
    with _Page(browser, base, GALLERY, {SCENARIOS_FILE: _json(payload)}) as view:
        view.page.wait_for_selector("#sim-sum-body tr")
        seen = view.page.evaluate(_GALLERY_READ)
        targets, shifts = seen["targets"], seen["shifts"]
        view.page.select_option("#sim-fsel-outcome", "screened")  # the screened-out rows as well
        seen = view.page.evaluate(_GALLERY_READ)
        targets, shifts = targets + seen["targets"], shifts + seen["shifts"]
        assert "—" in targets and [target for target in targets if "“—”" in target] == []
        # a shift glyph names its quantity: by the target token where there is one, in words where there is none
        assert [shift for shift in shifts if shift.startswith("prob():")] == []
        if any(isinstance(record.get("prob_clinical"), (int, float))
               for record in (without, *(without.get("models") or {}).values())):
            assert [shift for shift in shifts if shift.startswith("target probability: ")] != [], shifts
        assert view.errors == []
    with _Page(browser, base, f"{SCENARIO}?sim={without['index']}", {SCENARIOS_FILE: _json(payload)}) as view:
        view.page.wait_for_selector("#sim-card .sim-prompts")
        lines = view.page.evaluate("""() => [...document.querySelectorAll(
            '#sim-card details.spread > summary, #sim-card p.sim-probs')].map((node) => node.textContent)""")
        assert len(lines) == 2
        assert all(line.startswith("target probability = ") and "prob(" not in line for line in lines)
        assert view.errors == []


# ------------------------------------------------------------------ Dialect differences

DIALECTS = "/dialect-differences/index.html"
DIALECTS_FILE = "**/data/dialects.json"

UNLISTED_FRAMING = "Placeholder Valley English"

_DIALECT_READ = """() => ({
    last_head: (th => [th.dataset.key, th.textContent.trim(), th.title])(
        document.querySelector('#dlm-head th[data-key=core]')),
    heads: [...document.querySelectorAll('#dlm-head th button')].map((button) => button.textContent.trim()),
    featured: Object.fromEntries([...document.querySelectorAll('#dlf-body > tr:not(.acc)')].map(
        (row) => [row.children[0].textContent, row.children[4].textContent])),
    hover: [...document.querySelectorAll('#dlm-body td.spark')].map(
        (cell) => [cell.getAttribute('title'), cell.getAttribute('aria-label')])})"""


def test_dialect_page_labels_an_empty_or_absent_top_token_and_heads_its_last_column_in_words(site) -> None:
    """Regression (2026-11-11): a top prediction whose stored token is empty was printed as "?", in the
    featured-term table and in the matrix cell's hover text and accessible name, and the last matrix column was
    headed by its JSON key, ``core``; the header's title now gives the definition and names the field. A framing
    was named by pattern tests on its instruction string, then by the string with " English" cut off: a framing
    the page's map does not list is now printed as recorded. The committed file is served with three top tokens of
    the featured term changed in memory (an empty string beside a probability, no token and no probability, and a
    placeholder word) and one of its framings renamed."""
    browser, base = site
    _need("dialects.json")
    payload = _fixture("dialects.json")
    featured = next(item for item in payload["items"] if item["term"] == payload["featured_term"]["term"])
    empty, absent, stored = featured["variants"][:3]
    empty.update(top_token="", top_p=0.5)
    absent.update(top_token=None, top_p=None)
    stored.update(top_token="placeholder", dialect=UNLISTED_FRAMING)
    with _Page(browser, base, DIALECTS, {DIALECTS_FILE: _json(payload)}) as view:
        view.page.wait_for_selector("#dlf-body > tr")
        seen = view.page.evaluate(_DIALECT_READ)
        key, head, definition = seen["last_head"]
        assert key == "core" and head and head != "core" and "clinical features" in definition
        assert re.search(r"\bcore\b", definition), definition          # the field's name stays readable there
        assert UNLISTED_FRAMING in seen["heads"] and UNLISTED_FRAMING in seen["featured"], seen["heads"]
        assert UNLISTED_FRAMING.removesuffix(" English") not in seen["heads"]
        tops = list(seen["featured"].values())
        assert len(tops) == len(featured["variants"]) + 1 and [top for top in tops if "?" in top] == []
        assert [top for top in tops if top.startswith("placeholder · ")] != []      # a stored token, as stored
        assert [top for top in tops if top.startswith("— ") or top == "—"] != []    # no token and no probability
        assert sum("top: ?" in text for cell in seen["hover"] for text in cell if text) == 0
        assert view.errors == []
