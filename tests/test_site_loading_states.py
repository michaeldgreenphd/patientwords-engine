"""What seven site pages show while a data file loads, when it fails to load, when it holds nothing, and when it loads.

The owner's requirements of 2026-11-11, as checks on the pages in a browser:

* ``multi-turn/``: a published file that fails to load is never replaced by a sample fixture. The two files are one
  unit: one failure, or two, shows the failed state and draws nothing from either file. The sample fixtures are
  drawn only when the address carries ``?sample=1``, under the sample notice.
* ``llm/``, ``llm/code.html`` and ``technical/``: a request that errors or answers an HTTP error status reads as a
  failed load; a file that loads and holds no measurement reads as not yet published; no state sentence names a
  file or tells the reader to wait for one. The file and the reason stay available to a maintainer in the
  sentence's ``title`` attribute and in the browser console.
* ``technical/``: a table or a figure with nothing to show says so in its caption. No header row is left over an
  empty table body and no legend is left under a figure that was not drawn. The repair table reads its own file,
  so a lens file that fails to load does not empty it.
* ``technical/`` and ``methods.html``: the J-space figure's text alternative names what its panels display, in the
  measured state and in the illustrative one.
* ``clinical/``: the line under the verbatim pair is drawn whichever data file arrives first, and it is the row of
  the pair shown.
* ``simulated-scenarios/``: the filter selects do not make the page wider than a phone's viewport.

These tests drive the site's real pages in Chromium and answer the data requests from the test (``page.route``):
a placeholder payload, an HTTP error, an aborted request, or a request held until the test releases it. The
payloads are placeholders, so a passing test is evidence about what a page does with a file. It is not evidence
about a model or about any measurement. Six tests read the committed data files as they are (each page with no
request answered by the test, the Technical page with every file served, its tables and figures in the loaded
state, the J-space figure on both pages, the Clinical page with each file delayed in turn, and the Scenarios page
at three widths); they assert that the page agrees with itself and assert no value from those files.

Skipped where the sibling site checkout, Playwright or a Chromium is missing.
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
import shutil
import socket
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

MULTI_TURN = "/multi-turn/index.html"
SUMMARY = "**/data/petri_multiturn_summary.json"
CONVERSATIONS = "**/data/petri_multiturn_conversations.json"
MT_SECTIONS = ("sec-headline", "sec-differ", "sec-fig", "sec-explore", "example-wrap", "sec-register", "sec-prov")
# A summary and a conversations file that are valid by the frontend contract and record no result: the lists the
# exporter writes (summary.triples, conversations.conversations) are empty, and the headline carries the row id the
# exporter gives a test with no non-tied triple. No field is added to say "empty".
NO_RESULT_SUMMARY = {
    "seed": 7,
    "status": {"final": True, "clinician_review": "pending",
               "vendor_pack": {"version": "placeholder-pack", "sent": "2026-01-01"}},
    "headline": {"row_id": "not_computable", "text": None},
    "style_sentence": {"row_id": "not_computable", "text": None},
    "primary": {"triples": 0, "negative": 0, "positive": 0, "tied": 0, "p_two_sided": None, "gate_p": None,
                "gate_passed": None},
    "triples": [], "scenario_means": {}, "repeats": [],
    "provenance": {"runs": [], "analysis_commit": "0" * 40, "analysis_sha256": "0" * 64,
                   "exporter_commit": "0" * 40, "verify": "placeholder",
                   "models": {"target": ["placeholder-target"], "target_served": ["placeholder-target"],
                              "judge": ["placeholder-judge"], "target_temperature": 1.0,
                              "target_label": "Placeholder target", "judge_label": "Placeholder judge"}},
}
NO_RESULT_CONVERSATIONS = {"seed": None, "measures": [], "mechanisms": {}, "seeds": [], "conversations": [],
                           "example": None}

# Text that told a reader to wait for a file, or named one in a state sentence. None of it may be shown.
WAITING = re.compile(r"\.json\s+lands|data file lands|results? land\b|data pending|figure pending|"
                     r"examples pending|pending data load|once the (exporter|engine)|when \w+ lands", flags=re.I)


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


def _fixture(name: str) -> dict:
    return json.loads((SITE / "data" / name).read_text(encoding="utf-8"))


def _as_published(sample: dict) -> dict:
    """A sample fixture with its sample marks removed: placeholder content served under a published file's name."""
    return {key: value for key, value in sample.items() if key not in ("sample", "_sample", "_note")}


# ------------------------------------------------------------------ answers to a data request

def _json(body: object) -> Callable:
    return lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _status(code: int) -> Callable:
    return lambda route: route.fulfill(status=code, content_type="text/plain", body="")


def _abort(route) -> None:
    route.abort()


def _not_json(route) -> None:
    route.fulfill(status=200, content_type="application/json", body="<html>not json</html>")


FAILURES = {"HTTP 404": _status(404), "HTTP 500": _status(500), "aborted": _abort, "not JSON": _not_json}


class _Held:
    """A request the test holds open, so the page can be inspected while the file is still loading."""

    def __init__(self) -> None:
        self.routes: list = []

    def __call__(self, route) -> None:
        self.routes.append(route)

    def answer(self, handler: Callable | None = None) -> None:
        for route in self.routes:
            route.continue_() if handler is None else handler(route)
        self.routes.clear()


@pytest.fixture(scope="module")
def site() -> Iterator[tuple[object, str]]:
    if not (SITE / "multi-turn" / "index.html").is_file():
        pytest.skip("the sibling site checkout is not on disk")
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    serve = _load("check_pages").serve
    port = _free_port()
    with sync_playwright() as pw:
        candidates = (CHROME, pw.chromium.executable_path, shutil.which("chromium"))
        chrome = next((c for c in candidates if c and Path(c).exists()), None)
        if chrome is None:
            pytest.skip("no Chromium available for a browser-driven test")
        server = serve(SITE, port)
        try:
            browser = pw.chromium.launch(executable_path=chrome)
            yield browser, f"http://127.0.0.1:{port}"
            browser.close()
        finally:
            server.terminate()


class _Page:
    def __init__(self, browser, base: str, path: str, routes: dict | None = None, *,
                 width: int = 1280, wait: str = "networkidle") -> None:
        self.page = browser.new_page(viewport={"width": width, "height": 900})
        self.errors: list[str] = []
        self.requests: list[str] = []
        self.console: list[tuple[str, str]] = []
        self.unanswered: list[str] = []       # data requests that got an HTTP error status
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("response", lambda response: self.unanswered.append(f"{response.url} -> {response.status}")
                     if response.status >= 400 and "/data/" in response.url else None)
        self.page.on("request", lambda request: self.requests.append(request.url))
        # the browser asks for /favicon.ico by itself; its 404 says nothing about the page
        self.page.on("console", lambda message: self.console.append((message.type, message.text))
                     if "favicon.ico" not in (message.location or {}).get("url", "") else None)
        for pattern, handler in (routes or {}).items():
            self.page.route(pattern, handler)
        self.page.goto(base + path, wait_until=wait)

    def __enter__(self) -> "_Page":
        return self

    def __exit__(self, *exc) -> None:
        self.page.close()

    def status(self, prefix: str) -> dict:
        """The status block ``#<prefix>-pending``: its state, the one sentence shown and that sentence's title."""
        return self.page.evaluate("""(prefix) => { const box = document.getElementById(prefix + '-pending');
            const shown = [...box.querySelectorAll('span[id]')].filter(s => !s.hidden);
            return {state: box.getAttribute('data-state'), hidden: box.hidden, role: box.getAttribute('role'),
                    text: box.hidden ? '' : box.innerText.trim().replace(/\\s+/g, ' '),
                    titles: shown.map(s => s.title)}; }""", prefix)

    def hidden(self, ids: tuple[str, ...]) -> dict[str, bool]:
        return self.page.evaluate(
            "(ids) => Object.fromEntries(ids.map(id => [id, document.getElementById(id).hidden]))", list(ids))

    def settle(self, prefix: str) -> None:
        self.page.wait_for_function(
            "(prefix) => document.getElementById(prefix + '-pending').getAttribute('data-state') !== 'loading'",
            arg=prefix)

    def warnings(self) -> list[str]:
        return [text for kind, text in self.console if kind == "warning"]


# ------------------------------------------------------------------ Multi-turn

def _published_pair() -> tuple[dict, dict]:
    return (_as_published(_fixture("petri_multiturn_summary.sample.json")),
            _as_published(_fixture("petri_multiturn_conversations.sample.json")))


def _mt_routes(summary: Callable, conversations: Callable) -> dict[str, Callable]:
    # the register reading is a third, optional file; it is answered 404 so no committed value is read
    return {SUMMARY: summary, CONVERSATIONS: conversations, "**/data/petri_register_drift.json": _status(404)}


def test_multi_turn_draws_a_published_pair_without_a_sample_notice_and_requests_no_sample(site) -> None:
    browser, base = site
    summary, conversations = _published_pair()
    with _Page(browser, base, MULTI_TURN, _mt_routes(_json(summary), _json(conversations))) as view:
        status = view.status("mt")
        assert (status["state"], status["hidden"]) == ("loaded", True)
        assert view.page.is_hidden("#sample-banner")
        assert view.page.inner_text("#headline") == summary["headline"]["text"]
        drawn = view.hidden(MT_SECTIONS)
        assert not drawn["sec-headline"] and not drawn["sec-explore"] and not drawn["sec-fig"]
        assert not any(".sample.json" in url for url in view.requests)
        # the optional register reading is requested once, by its own name, after a published pair is drawn
        assert [url.rsplit("/", 1)[1] for url in view.requests if "register" in url] == ["petri_register_drift.json"]
        assert view.errors == []


@pytest.mark.parametrize("path", [MULTI_TURN, MULTI_TURN + "?sample=1", "/llm/index.html", "/llm/index.html?sample=1",
                                  "/llm/code.html", "/llm/code.html?sample=1", "/technical/index.html",
                                  "/clinical/index.html"])
def test_a_page_requests_only_data_files_the_site_holds(site, path) -> None:
    """With the committed files and no request answered by the test. (While these states were being written, one
    page asked for ``petri_register_drift.json.json``; the tests above answer that file themselves and did not see
    it.) No value of any file is asserted."""
    browser, base = site
    with _Page(browser, base, path) as view:
        assert view.unanswered == [] and view.errors == []
        assert [text for kind, text in view.console if kind == "error"] == []
        left = view.page.evaluate("""() => [...document.querySelectorAll('[data-state]')]
            .map(n => [n.id, n.getAttribute('data-state')]).filter(([, state]) => state !== 'loaded')""")
        assert left == []


@pytest.mark.parametrize("failure", sorted(FAILURES))
@pytest.mark.parametrize("failing", ["summary", "conversations", "both"])
def test_multi_turn_shows_a_failed_load_and_no_sample_when_a_published_file_fails(site, failing, failure) -> None:
    """One file failing and both failing, by an HTTP error, an aborted request and a body that is not JSON. Before
    2026-11-11 the page answered each of these by drawing the two sample fixtures under the sample notice."""
    browser, base = site
    summary, conversations = _published_pair()
    fail = FAILURES[failure]
    routes = _mt_routes(fail if failing in ("summary", "both") else _json(summary),
                        fail if failing in ("conversations", "both") else _json(conversations))
    with _Page(browser, base, MULTI_TURN, routes) as view:
        status = view.status("mt")
        assert status["state"] == "failed" and status["hidden"] is False
        assert status["text"] == "The results did not load. Reload the page to try again."
        # nothing is drawn, from the file that failed or from the one that loaded
        assert all(view.hidden(MT_SECTIONS).values())
        assert view.page.inner_text("#headline") == ""
        # no sample fixture was requested, and neither sample content nor the sample notice is shown
        assert not any(".sample.json" in url for url in view.requests)
        assert view.page.is_hidden("#sample-banner")
        shown = view.page.inner_text("main")
        assert "[Sample" not in shown and "Sample data" not in shown
        # the files that failed are named for a maintainer, in the sentence's title and in the console
        (title,) = status["titles"]
        named = {"summary": ["petri_multiturn_summary.json"], "conversations": ["petri_multiturn_conversations.json"],
                 "both": ["petri_multiturn_summary.json", "petri_multiturn_conversations.json"]}[failing]
        assert re.findall(r"petri_multiturn_\w+\.json", title) == named
        if failure.startswith("HTTP"):
            assert failure in title
        assert any(title in warning for warning in view.warnings())
        assert ".json" not in status["text"] and not WAITING.search(shown)
        assert view.errors == []


def test_multi_turn_says_no_results_are_published_when_the_published_pair_records_none(site) -> None:
    browser, base = site
    # The payload is valid by the engine's own frontend contract, so "no result" is read from the exporter's fields.
    contract = _load("validate_frontend_contract")
    report = contract.Report()
    contract.check_multiturn_summary(report, "petri_multiturn_summary.json", NO_RESULT_SUMMARY, False)
    contract.check_multiturn_conversations(report, "petri_multiturn_conversations.json", NO_RESULT_CONVERSATIONS, False)
    assert report.errors == []
    with _Page(browser, base, MULTI_TURN, _mt_routes(_json(NO_RESULT_SUMMARY), _json(NO_RESULT_CONVERSATIONS))) as view:
        status = view.status("mt")
        assert (status["state"], status["text"]) == ("none", "No results are published yet.")
        assert all(view.hidden(MT_SECTIONS).values())
        assert view.page.is_hidden("#sample-banner")
        assert not any(".sample.json" in url for url in view.requests)
        assert "petri_multiturn_summary.json" in status["titles"][0] and view.errors == []
    # A pair that lists triples or conversations is a result, and is drawn: the state is not keyed on anything else.
    summary, conversations = _published_pair()
    with _Page(browser, base, MULTI_TURN, _mt_routes(_json(summary), _json(NO_RESULT_CONVERSATIONS))) as view:
        assert view.status("mt")["state"] == "loaded" and not view.hidden(MT_SECTIONS)["sec-headline"]
        assert view.errors == []


def test_multi_turn_with_nothing_published_says_so_and_requests_no_file(site) -> None:
    """``REAL_DATA_PUBLISHED`` set to false is the page's own record that nothing is published. Before 2026-11-11 the
    page then drew the samples without being asked."""
    browser, base = site
    source = (SITE / "multi-turn" / "index.html").read_text(encoding="utf-8")
    assert source.count("var REAL_DATA_PUBLISHED=true;") == 1
    unpublished = source.replace("var REAL_DATA_PUBLISHED=true;", "var REAL_DATA_PUBLISHED=false;")
    page_route = {re.compile(r"/multi-turn/index\.html(\?.*)?$"): lambda route: route.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=unpublished)}
    with _Page(browser, base, MULTI_TURN, page_route) as view:
        status = view.status("mt")
        assert (status["state"], status["text"]) == ("none", "No results are published yet.")
        assert not any("petri_multiturn" in url for url in view.requests)
        assert view.page.is_hidden("#sample-banner") and all(view.hidden(MT_SECTIONS).values())
        assert view.errors == []
    # The sample mode stays available on request while nothing is published.
    with _Page(browser, base, MULTI_TURN + "?sample=1", page_route) as view:
        assert view.status("mt")["state"] == "loaded" and view.page.is_visible("#sample-banner")


def test_multi_turn_sample_mode_is_explicit_and_carries_its_notice(site) -> None:
    browser, base = site
    sample = _fixture("petri_multiturn_summary.sample.json")
    with _Page(browser, base, MULTI_TURN + "?sample=1") as view:
        status = view.status("mt")
        assert (status["state"], status["hidden"]) == ("loaded", True)
        assert view.page.is_visible("#sample-banner")
        assert view.page.inner_text("#sample-banner").startswith("Sample data:")
        assert view.page.inner_text("#headline") == sample["headline"]["text"]
        fetched = [url.rsplit("/", 1)[1] for url in view.requests if "petri_multiturn" in url]
        assert sorted(fetched) == ["petri_multiturn_conversations.sample.json", "petri_multiturn_summary.sample.json"]
        assert view.errors == []
    # In sample mode a fixture that fails is a failed load of the samples, and the notice is not shown over nothing.
    failing = {"**/data/petri_multiturn_*.sample.json": _status(404)}
    with _Page(browser, base, MULTI_TURN + "?sample=1", failing) as view:
        status = view.status("mt")
        assert (status["state"], status["text"]) == (
            "failed", "The sample files did not load. Reload the page to try again.")
        assert view.page.is_hidden("#sample-banner") and all(view.hidden(MT_SECTIONS).values())


def test_multi_turn_does_not_draw_a_summary_and_conversations_from_two_sources(site) -> None:
    """A file marked ``sample: true`` beside one that is not: the two do not come from one source."""
    browser, base = site
    summary, conversations = _published_pair()
    marked = _fixture("petri_multiturn_summary.sample.json")
    assert marked.get("sample") is True
    for routes in (_mt_routes(_json(marked), _json(conversations)),
                   _mt_routes(_json(summary), _json(_fixture("petri_multiturn_conversations.sample.json")))):
        with _Page(browser, base, MULTI_TURN, routes) as view:
            status = view.status("mt")
            assert status["state"] == "failed"
            assert status["text"] == "The two result files do not come from the same source, so neither is shown."
            assert all(view.hidden(MT_SECTIONS).values()) and view.page.is_hidden("#sample-banner")
            assert view.errors == []


def test_multi_turn_says_it_is_loading_until_both_files_have_answered(site) -> None:
    browser, base = site
    summary, conversations = _published_pair()
    held = _Held()
    with _Page(browser, base, MULTI_TURN, _mt_routes(held, _json(conversations)), wait="domcontentloaded") as view:
        view.page.wait_for_timeout(400)                       # the conversations file has answered; the summary has not
        status = view.status("mt")
        assert (status["state"], status["text"], status["role"]) == ("loading", "Loading the results…", "status")
        assert all(view.hidden(MT_SECTIONS).values())         # nothing is drawn from one file of the two
        held.answer(_json(summary))
        view.settle("mt")
        assert view.status("mt")["state"] == "loaded" and not view.hidden(MT_SECTIONS)["sec-headline"]


# ------------------------------------------------------------------ LLM responses and the coding instrument

LLM_PAGES = {
    "llm": {"path": "/llm/index.html", "file": "advice_scenarios.json", "list": "scenarios", "app": "llm-viewer",
            "loading": "Loading the responses…",
            "failed": "The responses did not load. Reload the page to try again.",
            "none": "No responses are published yet."},
    "cd": {"path": "/llm/code.html", "file": "advice_coding_sample.json", "list": "items", "app": "cd-app",
           "loading": "Loading the coding sample…",
           "failed": "The coding sample did not load. Reload the page to try again.",
           "none": "No coding sample is published yet."},
}


@pytest.mark.parametrize("prefix", sorted(LLM_PAGES))
def test_an_llm_page_tells_a_failed_load_from_a_file_with_nothing_published(site, prefix) -> None:
    browser, base = site
    spec = LLM_PAGES[prefix]
    pattern = f"**/data/{spec['file']}"

    # the static markup, and the page while the request is open: loading, not "nothing published"
    source = (SITE / spec["path"].lstrip("/")).read_text(encoding="utf-8")
    block = re.search(rf'<div class="pending" id="{prefix}-pending"[^>]*>(.*?)</div>', source, flags=re.S).group(1)
    assert re.findall(r"<span id=\"[\w-]+\"( hidden)?>", block) == ["", " hidden", " hidden"]
    assert ".json" not in block and not WAITING.search(html.unescape(block))
    held = _Held()
    with _Page(browser, base, spec["path"], {pattern: held}, wait="domcontentloaded") as view:
        view.page.wait_for_timeout(300)
        status = view.status(prefix)
        assert (status["state"], status["text"], status["role"]) == ("loading", spec["loading"], "status")
        held.answer(_status(404))
        view.settle(prefix)
        assert view.status(prefix)["state"] == "failed"

    for failure, handler in FAILURES.items():
        with _Page(browser, base, spec["path"], {pattern: handler}) as view:
            status = view.status(prefix)
            assert (status["state"], status["text"]) == ("failed", spec["failed"]), failure
            assert view.page.is_hidden(f"#{spec['app']}") and view.page.is_hidden("#sample-banner")
            (title,) = status["titles"]
            assert title.startswith(f"data/{spec['file']}") and (failure in title or not failure.startswith("HTTP"))
            assert any(title in warning for warning in view.warnings())
            assert not any(".sample.json" in url for url in view.requests)
            assert view.errors == []

    for empty in ({spec["list"]: []}, {}):
        with _Page(browser, base, spec["path"], {pattern: _json(empty)}) as view:
            status = view.status(prefix)
            assert (status["state"], status["text"]) == ("none", spec["none"]), empty
            assert view.page.is_hidden(f"#{spec['app']}") and view.page.is_hidden("#sample-banner")
            assert status["titles"][0].startswith(f"data/{spec['file']}") and view.warnings() == []
            assert view.errors == []

    # no state sentence names a file or tells the reader to wait for one
    for sentence in (spec["loading"], spec["failed"], spec["none"]):
        assert ".json" not in sentence and not WAITING.search(sentence)


@pytest.mark.parametrize("prefix", sorted(LLM_PAGES))
def test_an_llm_page_draws_a_published_file_and_keeps_its_explicit_sample_mode(site, prefix) -> None:
    browser, base = site
    spec = LLM_PAGES[prefix]
    sample_name = spec["file"].replace(".json", ".sample.json")
    published = _as_published(_fixture(sample_name))
    with _Page(browser, base, spec["path"], {f"**/data/{spec['file']}": _json(published)}) as view:
        status = view.status(prefix)
        assert (status["state"], status["hidden"]) == ("loaded", True)
        assert view.page.is_visible(f"#{spec['app']}") and view.page.is_hidden("#sample-banner")
        assert not any(".sample.json" in url for url in view.requests)
    with _Page(browser, base, spec["path"] + "?sample=1") as view:
        assert view.status(prefix)["state"] == "loaded"
        assert view.page.is_visible(f"#{spec['app']}") and view.page.is_visible("#sample-banner")
        assert any(url.endswith(sample_name) for url in view.requests)
        assert not any(url.endswith("/" + spec["file"]) for url in view.requests)


# ------------------------------------------------------------------ Technical

TECHNICAL = "/technical/index.html"
ALL_DATA = "**/data/*.json"
FIGURE_HOSTS = ("fig-traj", "fig-form", "fig-it", "fig-transport", "fig-loglens", "ad-blocks", "ad-examples")
# element id -> (the file it waits on, the sentence when that file fails to load, the sentence when it holds nothing)
TECH_STATES = {
    "dd-head": ("jlens_insights.json", "The lens readouts did not load.", "No lens readouts are published yet."),
    "fig-traj": ("jlens_insights.json", "This figure did not load.", "No lens readouts are published yet."),
    "fig-form": ("jlens_insights.json", "This figure did not load.", "No lens readouts are published yet."),
    "fig-it": ("jlens_insights.json", "This figure did not load.", "No lens readouts are published yet."),
    "credit-line": ("jlens_insights.json", "The method credit did not load.", "No method credit is published yet."),
    "fig-transport": ("jlens_transport.json", "This figure did not load.", "No transport readout is published yet."),
    "fig-loglens": ("jlens_loglens.json", "This figure did not load.", "No logit-lens readout is published yet."),
    "ad-blocks": ("jlens_depth.json", "This figure did not load.", "No depth census is published yet."),
    "ad-examples": ("jlens_depth.json", "The examples did not load.", "No examples are published yet."),
    "forest-cap": ("model_stats.json", "The model statistics did not load.", "No model statistics are published yet."),
}
CONVERGENCE = ("convergence.json", "The convergence figure did not load.", "No convergence data are published yet.")
# the integrity panel's value cells: the file each reads; "did not load" on a failed load, the dash otherwise
INTEGRITY = {"rg-prereg": "model_stats.json", "rg-bh": "model_stats.json", "rg-holdout": "simulated_scenarios.json",
             "rg-drift": "drift_series.json", "rg-retrace": "retrace_consistency.json"}
# each file loaded and holding no measurement, in the keys its page block reads
NOTHING_MEASURED = {
    "jlens_insights.json": {"model": "placeholder-model", "n_pairs": 0, "points": [], "exemplars": [], "taxonomy": {},
                            "formation": {"clinical": None, "patient": None, "clinical_never": 0, "patient_never": 0,
                                          "lag": None, "n_layers": 26}},
    "jlens_transport.json": {"model": "placeholder-model", "n_pairs": 0, "census": {}, "exemplars": [], "per_pair": []},
    "jlens_loglens.json": {"model": "placeholder-model", "per_pair": [], "agreement": {}},
    "jlens_depth.json": {"model": "placeholder-model", "blocks": [], "examples": []},
    "model_stats.json": {"models": [], "per_model": {}},
    "convergence.json": {"render_min_n": 30, "models": {}},
}

_TECH_READ = """() => { const text = n => n ? n.textContent.trim().replace(/\\s+/g, ' ') : null;
    const one = id => { const host = document.getElementById(id);
        const node = host.hasAttribute('data-state') ? host : host.querySelector('[data-state]');
        return {text: text(host), state: node ? node.getAttribute('data-state') : null,
                title: node ? node.title : (host.title || ''), role: host.getAttribute('role'),
                label: host.getAttribute('aria-label')}; };
    const out = {};
    for (const id of IDS) out[id] = one(id);
    const conv = document.querySelector('.conv-pending');
    out.convergence = conv ? {text: text(conv), state: conv.getAttribute('data-state'), title: conv.title} : null;
    document.querySelectorAll('main details').forEach(d => d.open = true);
    out.shown = document.querySelector('main').innerText;
    return out; }"""


def _technical(view: _Page) -> dict:
    ids = json.dumps(list(TECH_STATES) + list(INTEGRITY))
    return view.page.evaluate(_TECH_READ.replace("IDS", ids))


def _data_routes(answers: dict[str, Callable], default: Callable | None = None) -> dict[str, Callable]:
    """One handler for every data file: the named files get their answer, the rest ``default`` (or the real file)."""
    def handler(route) -> None:
        name = route.request.url.rsplit("/", 1)[1].split("?")[0]
        chosen = answers.get(name, default)
        route.continue_() if chosen is None else chosen(route)
    return {ALL_DATA: handler}


def test_technical_static_markup_is_a_loading_state_and_names_no_file_to_wait_for() -> None:
    page = SITE / "technical" / "index.html"
    if not page.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    source = page.read_text(encoding="utf-8")
    assert not WAITING.search(html.unescape(source))
    pending = re.findall(r'<span class="pend"([^>]*)>([^<]*)</span>', source)
    assert len(pending) == len(FIGURE_HOSTS)
    for attributes, text in pending:
        assert 'data-state="loading"' in attributes and text.startswith("Loading the ") and text.endswith("…")


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_technical_reads_a_failed_load_as_failed_in_every_block(site, failure) -> None:
    browser, base = site
    with _Page(browser, base, TECHNICAL, _data_routes({}, FAILURES[failure])) as view:
        seen = _technical(view)
        for element, (file, failed, _) in TECH_STATES.items():
            assert (seen[element]["text"], seen[element]["state"]) == (failed, "failed"), element
            assert seen[element]["title"].startswith(f"data/{file}: "), (element, seen[element]["title"])
            assert len(seen[element]["title"]) > len(f"data/{file}: ")
            if failure.startswith("HTTP"):
                assert failure in seen[element]["title"]
            # a figure with role="img" hides its content from assistive technology, so the sentence is its label too
            if seen[element]["role"] == "img":
                assert seen[element]["label"] == failed
        file, failed, _ = CONVERGENCE
        assert (seen["convergence"]["text"], seen["convergence"]["state"]) == (failed, "failed")
        assert seen["convergence"]["title"].startswith(f"data/{file}: ")
        for cell, file in INTEGRITY.items():
            assert (seen[cell]["text"], seen[cell]["state"]) == ("did not load", "failed"), cell
            assert seen[cell]["title"].startswith(f"data/{file}: ")
        # no shown text names a file to wait for, and each failed file is reported once in the console
        assert not WAITING.search(seen["shown"])
        warned = " ".join(view.warnings())
        for file in {spec[0] for spec in TECH_STATES.values()} | {CONVERGENCE[0], *INTEGRITY.values()}:
            assert f"data/{file}" in warned, file
        assert view.errors == []


def test_technical_reads_a_file_that_holds_nothing_as_not_yet_published(site) -> None:
    browser, base = site
    answers = {name: _json(body) for name, body in NOTHING_MEASURED.items()}
    with _Page(browser, base, TECHNICAL, _data_routes(answers, _json({}))) as view:
        seen = _technical(view)
        for element, (file, _, none) in TECH_STATES.items():
            assert (seen[element]["text"], seen[element]["state"]) == (none, "none"), element
            assert seen[element]["title"].startswith(f"data/{file}: loaded"), (element, seen[element]["title"])
            if seen[element]["role"] == "img":
                assert seen[element]["label"] == none
        assert (seen["convergence"]["text"], seen["convergence"]["state"]) == (CONVERGENCE[2], "none")
        # an integrity value its file does not hold keeps the dash; nothing failed to load
        for cell in INTEGRITY:
            assert seen[cell]["text"] == "—" and seen[cell]["state"] is None, cell
        assert "did not load" not in seen["shown"] and not WAITING.search(seen["shown"])
        assert view.warnings() == [] and view.errors == []


def test_technical_keeps_one_failed_file_from_changing_another_files_figures(site) -> None:
    """The committed files are served as they are, except one that answers 404. No value of theirs is asserted."""
    browser, base = site
    needed = {spec[0] for spec in TECH_STATES.values()} | {CONVERGENCE[0]}
    if not all((SITE / "data" / name).is_file() for name in needed):
        pytest.skip("the site checkout does not hold every data file the Technical page reads")
    with _Page(browser, base, TECHNICAL, _data_routes({"jlens_insights.json": _status(404)})) as view:
        seen = _technical(view)
        for element, (file, failed, _) in TECH_STATES.items():
            if file == "jlens_insights.json":
                assert (seen[element]["text"], seen[element]["state"]) == (failed, "failed"), element
            else:
                assert seen[element]["state"] in (None, "loaded"), (element, seen[element])
                assert "did not load" not in seen[element]["text"]
        assert seen["convergence"] is None                            # the convergence figure was drawn
    # With every file served: no loading, failed or not-published state is left, and the console has no warning.
    with _Page(browser, base, TECHNICAL) as view:
        seen = _technical(view)
        left = view.page.evaluate("""() => [...document.querySelectorAll('[data-state]')]
            .filter(n => n.getAttribute('data-state') !== 'loaded').map(n => [n.id, n.getAttribute('data-state')])""")
        assert left == [] and view.page.locator(".pend").count() == 0
        assert seen["convergence"] is None and "did not load" not in seen["shown"]
        assert not WAITING.search(seen["shown"])
        assert view.warnings() == [] and view.errors == []


def test_technical_leaves_no_figure_loading_when_drawing_stops_part_way(site) -> None:
    """A file that loads and then breaks the drawing code: what was drawn or filled stays, and a figure the code
    never reached says it did not load, with the cause in its title. No figure is left saying it is loading."""
    browser, base = site
    broken = {"model": "placeholder-model", "method_credit": "placeholder credit", "n_pairs": 3, "points": [],
              "exemplars": [], "taxonomy": {},
              "formation": {"clinical": None, "patient": None, "clinical_never": 0, "patient_never": 0, "lag": None,
                            "n_layers": 26}}
    answers = {**{name: _json(body) for name, body in NOTHING_MEASURED.items()}, "jlens_insights.json": _json(broken)}
    with _Page(browser, base, TECHNICAL, _data_routes(answers, _json({}))) as view:
        seen = _technical(view)
        assert seen["dd-head"]["state"] == "loaded" and seen["dd-head"]["text"].startswith("3 pairs")
        assert (seen["credit-line"]["text"], seen["credit-line"]["state"]) == ("placeholder credit", "loaded")
        assert (seen["fig-traj"]["text"], seen["fig-traj"]["state"]) == (
            "No example pair is published for this figure yet.", "none")
        assert seen["fig-form"]["state"] is None                      # drawn before the code stopped
        assert (seen["fig-it"]["text"], seen["fig-it"]["state"]) == ("This figure did not load.", "failed")
        assert seen["fig-it"]["title"].startswith("data/jlens_insights.json: loaded; drawing stopped: ")
        assert not any(state["state"] == "loading" for state in seen.values() if isinstance(state, dict))
        assert any("drawing stopped" in warning for warning in view.warnings())


def test_technical_says_it_is_loading_while_the_lens_file_is_open(site) -> None:
    browser, base = site
    held = _Held()
    routes = _data_routes({"jlens_insights.json": held}, _json({}))
    with _Page(browser, base, TECHNICAL, routes, wait="domcontentloaded") as view:
        view.page.wait_for_timeout(400)
        seen = _technical(view)
        assert (seen["dd-head"]["text"], seen["dd-head"]["state"]) == ("Loading the lens readouts…", "loading")
        assert (seen["fig-form"]["text"], seen["fig-form"]["state"]) == ("Loading the figure…", "loading")
        held.answer(_status(404))
        view.page.wait_for_function("() => document.getElementById('dd-head').getAttribute('data-state') === 'failed'")


# -- a table or a figure with nothing to show: its caption says so, and no header row or legend is left alone

REPAIR_FILE = "jlens_depth.json"
STATS_FILE = "model_stats.json"
# the depth file with the three classes the repair table lists, and nothing else the page draws from that file
REPAIR_TABLE = {"model": "placeholder-model", "blocks": [], "examples": [],
                "translation": {"by_class": {"suppressed": {"n": 4, "mean_recovery": 0.5},
                                             "absent": {"n": 2, "mean_recovery": 0.75},
                                             "retained": {"n": 5, "mean_recovery": -0.25}}},
                "steering": {"by_class": {"suppressed": {"n": 3, "restored": 2, "unresolvable": 1},
                                          "absent": {"n": 0}, "unknown": {"n": 2}}}}
REPAIR_ROWS = [["formed, then lost (hijack)", "+0.50 tiers · n = 4", "2 of 3 pairs"],
               ["never formed (capture)", "held back · n = 2", "queued"],
               ["held to the end", "-0.25 tiers · n = 5", "not swap-eligible"]]
# what the depth file answers -> (the handler, the caption's state, its sentence, how its title continues)
REPAIR_STATES = {
    "HTTP 404": (_status(404), "failed", "This table did not load.", "HTTP 404"),
    "not JSON": (_not_json, "failed", "This table did not load.", ""),
    "an empty file": (_json({}), "none", "No repair results by depth class are published yet.",
                      "loaded, with no depth class listed"),
    "no class listed": (_json({"model": "placeholder-model", "translation": {"by_class": {}}}), "none",
                        "No repair results by depth class are published yet.", "loaded, with no depth class listed"),
    # a class the drawing code cannot write a row for: drawing stops before any row is in the table
    "a class without its mean": (_json({"translation": {"by_class": {"suppressed": {"n": 4}}}}), "failed",
                                 "This table did not load.", "loaded; drawing stopped: "),
}
# model statistics that list one model, which is not one of the base-and-fine-tune pair the page compares
ONE_MODEL = {"models": ["placeholder-model"], "seed": 7, "boot": 100, "dedupe": "placeholder rule",
             "ci_method_downgrade": "placeholder method",
             "per_model": {"placeholder-model": {
                 "registration": "pre-registered",
                 "penalty": {"mean": -0.03, "ci95": [-0.04, -0.02], "n_phrases": 40},
                 "sign_test": {"downgrades": 6, "upgrades": 2, "p_bh": 0.25}}}}
NO_STATISTICS = "No model statistics are published yet."
NO_PAIR = "No statistics are published for this pair yet."
BACKEND_CELL = "no value is published yet"

_TABLES_READ = """() => { document.querySelectorAll('main details').forEach(d => d.open = true);
    const shown = n => !!n && n.getClientRects().length > 0;
    const text = n => n.textContent.trim().replace(/\\s+/g, ' ');
    const caption = id => { const n = document.getElementById(id);
        return n ? {text: text(n), state: n.getAttribute('data-state'), title: n.title, shown: shown(n)}
                 : {text: null, state: null, title: '', shown: false}; };
    const rows = id => [...document.querySelectorAll('#' + id + ' tr')].map(r => [...r.cells].map(text));
    return {
        repair: {caption: caption('cap-router'), table: shown(document.querySelector('table.router')),
                 rows: rows('router-body')},
        interim: {caption: caption('ev-cap'), table: shown(document.getElementById('ev-table')),
                  hint: shown(document.getElementById('ev-hint')), rows: rows('ev-body').length},
        forest: {caption: caption('forest-cap'), drawn: document.querySelectorAll('#forest svg').length},
        asymmetry: {caption: caption('asym-cap'), drawn: document.querySelectorAll('#dumbbells svg').length},
        pair: {caption: caption('twin-cap'), drawn: document.querySelectorAll('#twin svg').length},
        backend: text(document.getElementById('rg-backend')),
        // every table a reader can see whose body has no row
        header_only: [...document.querySelectorAll('main table')].filter(t => shown(t) && t.tBodies.length
            && ![...t.tBodies].some(b => b.rows.length)).map(t => t.id || t.className),
        // every element still marked as waiting on its file
        loading: [...document.querySelectorAll('[data-state="loading"]')].map(n => n.id || n.className),
        shown: document.querySelector('main').innerText}; }"""


def _tables(view: _Page) -> dict:
    """The repair table, the three figures and the table of the model statistics, and the backend cell, with every
    fold open: each caption's text, state and title, and whether a reader can see it."""
    return view.page.evaluate(_TABLES_READ)


def _nothing_else(answers: dict[str, Callable]) -> dict[str, Callable]:
    """The named files get their answer. Every other data file loads and holds no measurement."""
    return _data_routes({**{name: _json(body) for name, body in NOTHING_MEASURED.items()}, **answers}, _json({}))


def _static_caption(element: str) -> str:
    """A caption's text in the page source: what the page shows under a table or a figure it has drawn."""
    source = (SITE / "technical" / "index.html").read_text(encoding="utf-8")
    return html.unescape(re.search(rf'<p class="[\w-]+" id="{element}"[^>]*>([^<]*)</p>', source).group(1))


@pytest.mark.parametrize("answer", sorted(REPAIR_STATES))
def test_the_technical_repair_table_says_so_when_it_has_no_row_to_show(site, answer) -> None:
    """Regression (2026-11-11): the reader saw the column headers and the caption, with no row and no sentence."""
    browser, base = site
    handler, state, sentence, reason = REPAIR_STATES[answer]
    with _Page(browser, base, TECHNICAL, _nothing_else({REPAIR_FILE: handler})) as view:
        seen = _tables(view)
        caption = seen["repair"]["caption"]
        assert (caption["text"], caption["state"], caption["shown"]) == (sentence, state, True)
        prefix = f"data/{REPAIR_FILE}: "
        assert caption["title"].startswith(prefix + reason) and len(caption["title"]) > len(prefix)
        # the sentence is outside the table body, the table is not shown, and no placeholder row was written
        assert seen["repair"]["table"] is False and seen["repair"]["rows"] == []
        assert seen["header_only"] == [] and seen["loading"] == []
        assert ".json" not in sentence and not WAITING.search(seen["shown"])
        assert any(prefix in warning for warning in view.warnings()) is (state == "failed")
        assert view.errors == []


@pytest.mark.parametrize("lens", ["HTTP 404", "no pair listed"])
def test_the_technical_repair_table_is_drawn_from_its_own_file_whatever_the_lens_file_does(site, lens) -> None:
    """Regression (2026-11-11): the table's fetch sat inside the lens file's handler, so a lens file that failed to
    load, or listed no pair, left the table as a header row with no rows. The rows are placeholders."""
    browser, base = site
    answer = {"HTTP 404": _status(404), "no pair listed": _json(NOTHING_MEASURED["jlens_insights.json"])}[lens]
    routes = _nothing_else({"jlens_insights.json": answer, REPAIR_FILE: _json(REPAIR_TABLE)})
    with _Page(browser, base, TECHNICAL, routes) as view:
        seen = _tables(view)
        assert seen["repair"]["rows"] == REPAIR_ROWS and seen["repair"]["table"] is True
        # the caption is the table's own, with the model the file names; no state sentence is shown
        caption = seen["repair"]["caption"]
        assert (caption["state"], caption["title"], caption["shown"]) == ("loaded", "", True)
        assert caption["text"] == f"placeholder-model · {_static_caption('cap-router')}"
        assert "did not load" not in caption["text"] and "published yet" not in caption["text"]
        assert seen["header_only"] == [] and view.errors == []
        # the lens file's own elements still say what happened to the lens file
        assert _technical(view)["dd-head"]["state"] == ("failed" if lens == "HTTP 404" else "none")


def test_the_technical_repair_table_is_hidden_only_together_with_its_sentence(site) -> None:
    """While the file is open nothing has been decided: the table is shown, empty, under its own caption. It is
    hidden when the caption takes a sentence, and at no other time, so a table left visible with no row is still
    what ``scripts/check_pages.py`` reports."""
    browser, base = site
    held = _Held()
    with _Page(browser, base, TECHNICAL, _nothing_else({REPAIR_FILE: held}), wait="domcontentloaded") as view:
        view.page.wait_for_timeout(400)
        seen = _tables(view)
        caption = seen["repair"]["caption"]
        assert (caption["text"], caption["state"]) == (_static_caption("cap-router"), "loading")
        assert seen["repair"]["table"] is True and seen["repair"]["rows"] == []
        held.answer(_status(404))
        view.page.wait_for_function(
            "() => document.getElementById('cap-router').getAttribute('data-state') === 'failed'")
        assert _tables(view)["repair"]["table"] is False


def test_the_page_gate_finds_no_visible_empty_table_and_no_placeholder_row_on_the_technical_page(site) -> None:
    """``scripts/check_pages.py`` counts the rows of the repair table and of the interim table and fails on either
    when it is visible with no row. With no measurement in any file, each is hidden under its sentence and holds
    no row. Before 2026-11-11 the repair table was reported here: it was visible with no row."""
    browser, base = site
    check_page = _load("check_pages").check_page
    page = browser.new_page()
    try:
        for pattern, handler in _nothing_else({}).items():
            page.route(pattern, handler)
        report = check_page(page, base, TECHNICAL)
    finally:
        page.close()
    assert (report["tables"]["router-body"], report["tables"]["ev-body"]) == ("0/hidden", "0/hidden")
    assert report["findings"] == []


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_technical_says_so_at_each_figure_and_table_of_the_model_statistics_when_the_file_fails(site, failure) -> None:
    """Regression (2026-11-11): one sentence appeared under the forest. The asymmetry figure left its legend under
    nothing, the interim table its header row over no rows, and the base-and-fine-tune comparison said nothing."""
    browser, base = site
    expected = {"forest": "The model statistics did not load.", "asymmetry": "This figure did not load.",
                "pair": "This figure did not load.", "interim": "This table did not load."}
    prefix = f"data/{STATS_FILE}: "
    # 390 px wide: at that width the page shows a "table scrolls sideways" hint over a table that is shown
    with _Page(browser, base, TECHNICAL, _nothing_else({STATS_FILE: FAILURES[failure]}), width=390) as view:
        seen = _tables(view)
        for part, sentence in expected.items():
            caption = seen[part]["caption"]
            assert (caption["text"], caption["state"], caption["shown"]) == (sentence, "failed", True), part
            assert caption["title"].startswith(prefix) and len(caption["title"]) > len(prefix), part
            if failure.startswith("HTTP"):
                assert failure in caption["title"]
            assert ".json" not in sentence
        assert (seen["forest"]["drawn"], seen["asymmetry"]["drawn"], seen["pair"]["drawn"]) == (0, 0, 0)
        # the legend of the figure that was not drawn is gone; the interim table and its scroll hint are hidden
        assert "filled red" not in seen["shown"]
        assert (seen["interim"]["table"], seen["interim"]["hint"], seen["interim"]["rows"]) == (False, False, 0)
        assert seen["header_only"] == [] and seen["loading"] == [] and not WAITING.search(seen["shown"])
        assert any(prefix in warning for warning in view.warnings()) and view.errors == []


def test_technical_says_so_at_each_figure_and_table_of_the_model_statistics_when_no_model_is_listed(site) -> None:
    browser, base = site
    expected = {"forest": NO_STATISTICS, "asymmetry": NO_STATISTICS, "interim": NO_STATISTICS, "pair": NO_PAIR}
    with _Page(browser, base, TECHNICAL, _nothing_else({}), width=390) as view:
        seen = _tables(view)
        for part, sentence in expected.items():
            caption = seen[part]["caption"]
            assert (caption["text"], caption["state"], caption["shown"]) == (sentence, "none", True), part
            assert caption["title"].startswith(f"data/{STATS_FILE}: loaded"), part
        assert (seen["forest"]["drawn"], seen["asymmetry"]["drawn"], seen["pair"]["drawn"]) == (0, 0, 0)
        assert "filled red" not in seen["shown"]
        assert (seen["interim"]["table"], seen["interim"]["hint"], seen["interim"]["rows"]) == (False, False, 0)
        assert seen["header_only"] == [] and seen["loading"] == []
        assert view.warnings() == [] and view.errors == []


def test_technical_draws_the_model_statistics_it_has_and_names_the_comparison_it_has_not(site) -> None:
    """One placeholder model, which is not one of the base-and-fine-tune pair. What the file holds is drawn under
    its own legend and caption; the comparison the file does not hold is not drawn, and its caption says so."""
    browser, base = site
    with _Page(browser, base, TECHNICAL, _nothing_else({STATS_FILE: _json(ONE_MODEL)}), width=390) as view:
        seen = _tables(view)
        assert (seen["forest"]["drawn"], seen["asymmetry"]["drawn"]) == (1, 1)
        legend = seen["asymmetry"]["caption"]
        assert (legend["text"], legend["state"], legend["title"]) == (_static_caption("asym-cap"), "loaded", "")
        assert (seen["interim"]["table"], seen["interim"]["hint"], seen["interim"]["rows"]) == (True, True, 1)
        assert (seen["interim"]["caption"]["state"], seen["forest"]["caption"]["state"]) == ("loaded", "loaded")
        pair = seen["pair"]["caption"]
        assert (pair["text"], pair["state"], seen["pair"]["drawn"]) == (NO_PAIR, "none", 0)
        assert pair["title"].startswith(f"data/{STATS_FILE}: loaded, without both ")
        assert seen["header_only"] == [] and seen["loading"] == []
        assert view.warnings() == [] and view.errors == []


def test_technical_keeps_the_figure_it_drew_when_drawing_the_model_statistics_stops_part_way(site) -> None:
    """A file that loads and then breaks the drawing code (a model without its sign test). The forest was drawn and
    stays. The asymmetry figure and the interim table were not reached: each says it did not load, with the cause
    in its title, and neither a legend nor a header row is left alone."""
    browser, base = site
    model = {key: value for key, value in ONE_MODEL["per_model"]["placeholder-model"].items() if key != "sign_test"}
    broken = {**ONE_MODEL, "per_model": {"placeholder-model": model}}
    with _Page(browser, base, TECHNICAL, _nothing_else({STATS_FILE: _json(broken)}), width=390) as view:
        seen = _tables(view)
        assert (seen["forest"]["drawn"], seen["forest"]["caption"]["state"]) == (1, "loaded")
        for part, sentence in (("asymmetry", "This figure did not load."), ("interim", "This table did not load.")):
            caption = seen[part]["caption"]
            assert (caption["text"], caption["state"], caption["shown"]) == (sentence, "failed", True), part
            assert caption["title"].startswith(f"data/{STATS_FILE}: loaded; drawing stopped: "), part
        assert seen["asymmetry"]["drawn"] == 0 and "filled red" not in seen["shown"]
        assert (seen["interim"]["table"], seen["interim"]["hint"]) == (False, False)
        assert seen["header_only"] == [] and seen["loading"] == []
        assert any("drawing stopped" in warning for warning in view.warnings()) and view.errors == []


def test_technical_tables_and_figures_are_unchanged_when_their_files_load(site) -> None:
    """With the committed files, read as they are: the rows and the figures are present, each caption is the
    table's or the figure's own, and no state sentence is shown. No value of the files is asserted."""
    browser, base = site
    if not all((SITE / "data" / name).is_file() for name in (REPAIR_FILE, STATS_FILE)):
        pytest.skip("the site checkout does not hold the two data files these tables and figures read")
    with _Page(browser, base, TECHNICAL, width=390) as view:
        seen = _tables(view)
        for part in ("repair", "interim", "forest", "asymmetry"):
            caption = seen[part]["caption"]
            assert (caption["state"], caption["title"], caption["shown"]) == ("loaded", "", True), part
            assert "did not load" not in caption["text"] and "published yet" not in caption["text"], part
        assert seen["repair"]["table"] is True and len(seen["repair"]["rows"]) > 0
        assert seen["repair"]["caption"]["text"].endswith(_static_caption("cap-router"))
        assert seen["interim"]["table"] is True and seen["interim"]["hint"] is True and seen["interim"]["rows"] > 0
        assert (seen["forest"]["drawn"], seen["asymmetry"]["drawn"]) == (1, 1)
        assert seen["asymmetry"]["caption"]["text"] == _static_caption("asym-cap")
        # the base-and-fine-tune comparison is drawn when the file lists both models, and says so when it does not
        pair = seen["pair"]["caption"]
        assert (pair["state"], pair["text"] == NO_PAIR, seen["pair"]["drawn"]) in (("loaded", False, 1),
                                                                                   ("none", True, 0))
        assert seen["backend"] == BACKEND_CELL
        assert seen["header_only"] == [] and seen["loading"] == []
        assert view.warnings() == [] and view.errors == []


def test_the_backend_cross_check_cell_says_no_value_is_published_in_every_state(site) -> None:
    """Regression (2026-11-11): the cell read "accumulating; reported when parity lands". No script writes the
    cell, so its text in the markup is its text in every state, and it agrees with the sentence above the table."""
    browser, base = site
    source = (SITE / "technical" / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'<td id="rg-backend">([^<]*)</td>', source) == [BACKEND_CELL]
    assert source.count("rg-backend") == 1                    # the markup is the only place that names the cell
    assert "the backend cross-check has no published value yet" in source
    for routes in (_data_routes({}, _status(404)), _nothing_else({})):
        with _Page(browser, base, TECHNICAL, routes) as view:
            assert _tables(view)["backend"] == BACKEND_CELL


# -- the J-space figure's text alternative, on the Technical page (three panels) and the Methods page (two)

JSPACE_FILE = "**/data/jspace.json"
MEASURED_PANELS = {
    "clinical": {"input": "Placeholder clinical sentence about item one", "trigger": "item one",
                 "concepts": ["alpha", "beta"], "output": "gamma", "on_target": True},
    "patient": {"input": "Placeholder everyday sentence about thing two", "trigger": "thing two",
                "concepts": ["delta", "epsilon", "zeta"], "output": "eta", "on_target": False},
    "translation": {"input": "Placeholder rewritten sentence about item three", "trigger": "item three",
                    "concepts": ["theta"], "output": "iota", "on_target": True},
}
ILLUSTRATIVE_WORDS = ("dyspepsia", "antacid", "ice cream", "gastrointestinal", "spicy")
# the page -> (its path, the panels its figure has, the word its measured label opens with). Both pages bind the
# same file; the Methods page has no translation panel.
JSPACE_PAGES = {"technical": (TECHNICAL, ("clinical", "patient", "translation"), "Three"),
                "methods": ("/methods.html", ("clinical", "patient"), "Two")}

_JSPACE_READ = """() => { const grid = document.querySelector('.jspace-grid');
    const text = n => n.textContent.trim().replace(/\\s+/g, ' ');
    return {label: grid.getAttribute('aria-label'), role: grid.getAttribute('role'),
            caption: text(document.querySelector('.jspace-cap')),
            panels: [...grid.querySelectorAll('.jspanel')].map(p => ({
                part: p.getAttribute('data-jsrole'),
                head: text(p.querySelector('.jspanel-head')), input: text(p.querySelector('.jspanel-in')),
                pills: [...p.querySelectorAll('.jspill')].map(text), output: text(p.querySelector('.jsout')),
                on_target: p.querySelector('.jsout').classList.contains('jsout-ok')}))}; }"""


def _ax_names(page, role: str) -> list[str]:
    """The accessible names of the nodes of one role in Chromium's own accessibility tree."""
    client = page.context.new_cdp_session(page)
    client.send("Accessibility.enable")
    nodes = client.send("Accessibility.getFullAXTree")["nodes"]
    return [(node.get("name") or {}).get("value", "") for node in nodes
            if not node.get("ignored") and (node.get("role") or {}).get("value") == role]


def _static_jspace_label(path: str) -> str:
    """The label in the page's markup: the one written for the hand-authored panels."""
    source = (SITE / path.lstrip("/")).read_text(encoding="utf-8")
    return html.unescape(re.search(r'class="jspace-grid jspace-\d" role="img" aria-label="([^"]*)"', source).group(1))


@pytest.mark.parametrize("name", sorted(JSPACE_PAGES))
def test_the_jspace_figure_describes_the_measured_panels_it_displays(site, name) -> None:
    """Regression for the Methods page (2026-11-11): its two panels showed the measured pair under the caption
    "Empirical J-lens residual stream readout", and the accessibility tree still named the dyspepsia example."""
    browser, base = site
    path, parts, count = JSPACE_PAGES[name]
    payload = {"empirical": True, "note": "placeholder note", "panels": MEASURED_PANELS}
    with _Page(browser, base, path, {JSPACE_FILE: _json(payload)}) as view:
        seen = view.page.evaluate(_JSPACE_READ)
        label = seen["label"]
        assert seen["role"] == "img" and label.startswith(f"{count} panels, one measured pair. ")
        assert tuple(panel["part"] for panel in seen["panels"]) == parts
        # every sentence, pill and output the panels display is in the label, panel by panel and in order
        position = 0
        for panel in seen["panels"]:
            spec = MEASURED_PANELS[panel["part"]]
            assert panel["input"] == f"“{spec['input']}”" and panel["pills"] == spec["concepts"]
            assert panel["output"] == spec["output"] and panel["on_target"] is spec["on_target"]
            letter = panel["head"].split(" · ")[0] + ", "
            for text in (letter, panel["input"], *panel["pills"], f"“{panel['output']}”"):
                found = label.find(text, position)
                assert found >= 0, (text, label)
                position = found + len(text)
            verdict = f"which is {'' if spec['on_target'] else 'not '}the pair’s clinical target."
            assert label.startswith(verdict, position + 2), (label[position:position + 60], verdict)
        # nothing of the hand-authored example is left in the label, the caption or the panels
        for word in ILLUSTRATIVE_WORDS:
            assert word not in label and word not in json.dumps(seen["panels"], ensure_ascii=False)
        assert seen["caption"].startswith("Empirical J-lens residual stream readout")
        assert "Illustrative" not in seen["caption"]
        # the browser's accessibility tree gives the image that name
        assert label in _ax_names(view.page, "image")
        assert view.errors == []


@pytest.mark.parametrize("name", sorted(JSPACE_PAGES))
def test_the_jspace_figure_follows_the_committed_file(site, name) -> None:
    """With the committed ``data/jspace.json``: the label and the panels agree, whichever state the file is in. No
    word of the file is asserted. (On 2026-11-11 the file held a measured pair and the label of each page still
    described the hand-authored dyspepsia example.)"""
    browser, base = site
    if not (SITE / "data" / "jspace.json").is_file():
        pytest.skip("the site checkout holds no data/jspace.json")
    path, _, count = JSPACE_PAGES[name]
    measured = _fixture("jspace.json").get("empirical") is True
    with _Page(browser, base, path) as view:
        seen = view.page.evaluate(_JSPACE_READ)
        for panel in seen["panels"]:
            assert panel["input"] in seen["label"] or not measured
            assert all(pill in seen["label"] for pill in panel["pills"]), panel
            assert panel["output"] in seen["label"]
        assert seen["label"].startswith(f"{count} panels, one measured pair. ") is measured
        assert ("Illustrative schematic" in seen["caption"]) is (not measured)
        assert (seen["label"] == _static_jspace_label(path)) is (not measured)
        # the name the browser's accessibility tree gives the image is that label
        assert seen["label"] in _ax_names(view.page, "image")


@pytest.mark.parametrize("answer", ["HTTP 404", "aborted", "not JSON", "not empirical", "one panel incomplete"])
@pytest.mark.parametrize("name", sorted(JSPACE_PAGES))
def test_the_jspace_figure_stays_illustrative_and_matched_without_a_measured_file(site, name, answer) -> None:
    browser, base = site
    path = JSPACE_PAGES[name][0]
    incomplete = {"empirical": True,
                  "panels": {**MEASURED_PANELS, "patient": {**MEASURED_PANELS["patient"], "output": ""}}}
    handler = {**FAILURES, "not empirical": _json({"empirical": False, "panels": MEASURED_PANELS}),
               "one panel incomplete": _json(incomplete)}[answer]
    static = _static_jspace_label(path)
    with _Page(browser, base, path, {JSPACE_FILE: handler}) as view:
        seen = view.page.evaluate(_JSPACE_READ)
        # the label is the one in the markup, the caption says the figure is illustrative, and no panel was bound
        assert seen["label"] == static
        assert "Illustrative schematic" in seen["caption"] and "Empirical" not in seen["caption"]
        shown = json.dumps(seen["panels"], ensure_ascii=False)
        assert "Placeholder" not in shown and "alpha" not in shown
        # the markup's label and the hand-authored panels name the same words
        for panel in seen["panels"]:
            assert all(pill in static for pill in panel["pills"]) and panel["output"] in static, panel
        for word in ("dyspepsia", "stomach’s on fire", "antacid", "ice cream"):
            assert word in static and word in shown
        assert static in _ax_names(view.page, "image")
        # the fold for the exporter's note is the Technical page's alone, and is shown only under a measured figure
        assert view.page.is_hidden("#jspace-note") and view.errors == []


# ------------------------------------------------------------------ Clinical: the tier line under the verbatim pair

CLINICAL = "/clinical/index.html"
URGENCY = "**/data/urgency_shift.json"
SCENARIOS = "**/data/simulated_scenarios.json"
TIERS = {"4": "tier four", "3": "tier three", "2": "tier two", "1": "tier one", "0": "tier zero", "null": "excluded"}


def _clinical_constants() -> tuple[str, int, str]:
    source = (SITE / "clinical" / "index.html").read_text(encoding="utf-8")
    found = re.search(r"var PREF_BATCH='([^']+)', PREF_INDEX=(\d+), VIG_MODEL='([^']+)';", source)
    return found.group(1), int(found.group(2)), found.group(3)


def _pair(batch: str, batch_index: int, index: int, word: str) -> dict:
    return {"batch": batch, "batch_index": batch_index, "index": index, "flipped": True,
            "clinical_prompt": f"A placeholder term {word} goes", "clinical_term": "placeholder term",
            "patient_prompt": f"A plain phrase {word} goes", "patient_term": "plain phrase",
            "spread_clinical": [["up", 0.6], ["mid", 0.2]], "spread_patient": [["down", 0.5], ["mid", 0.1]]}


def _row(batch: str, index: int, model: str, clinical: int | None, patient: int | None, flip: str | None) -> dict:
    return {"batch": batch, "index": index, "model": model, "tier_top_clinical": clinical,
            "tier_top_patient": patient, "flip_class": flip}


def _tier_line(browser, base: str, scenarios: dict | None, urgency: dict | None, last: str | None) -> tuple[str, str]:
    """The tier line and the vignette's label after both files have answered, with ``last`` held until the other
    file has been drawn. A payload of ``None`` serves the committed file."""
    payloads = {"urgency": urgency, "scenarios": scenarios}
    patterns = {"urgency": URGENCY, "scenarios": SCENARIOS}
    answers = {patterns[name]: _json(body) for name, body in payloads.items() if body is not None}
    held = _Held()
    if last is not None:
        answers[patterns[last]] = held
    drawn = {"urgency": "() => document.getElementById('l-down').textContent !== '—'",
             "scenarios": "() => !document.getElementById('vig-lab').textContent.includes('loading')"}
    with _Page(browser, base, CLINICAL, answers, wait="domcontentloaded") as view:
        if last is not None:
            other = "scenarios" if last == "urgency" else "urgency"
            view.page.wait_for_function(drawn[other])
            assert held.routes, f"the {last} file was not requested"
            held.answer(None if payloads[last] is None else _json(payloads[last]))
        for check in drawn.values():
            view.page.wait_for_function(check)
        assert view.errors == []
        # textContent, not the rendered text: the label is set in capitals by the stylesheet
        return tuple(view.page.evaluate(
            "() => ['vig-tier', 'vig-lab'].map(id => document.getElementById(id).textContent.trim())"))


@pytest.mark.parametrize("last", [None, "urgency", "scenarios"])
def test_the_clinical_tier_line_does_not_depend_on_which_file_arrives_first(site, last) -> None:
    """Regression (2026-11-11): the line was drawn only when the urgency file finished before the scenarios file."""
    browser, base = site
    batch, index, model = _clinical_constants()
    scenarios = {"scenarios": [_pair("another_batch", 2, 1, "one"), _pair(batch, index, 280, "two")]}
    urgency = {"vocabulary_status": "placeholder status", "tiers": TIERS, "rows": [
        _row(batch, index, "another-model", 4, 0, "downgrade"),
        _row(batch, index, model, 3, 2, "downgrade"),
        _row("another_batch", 2, model, 4, 1, "downgrade")]}
    line, label = _tier_line(browser, base, scenarios, urgency, last)
    assert label.endswith(f"batch {batch} #{index}")
    assert line == "care-urgency tier of the top word: Tier three → Tier two (a downgrade)"


@pytest.mark.parametrize("last", [None, "urgency", "scenarios"])
def test_a_clinical_fallback_pair_gets_its_own_tier_row_or_no_line(site, last) -> None:
    """Regression (2026-11-11): when the preferred pair is not in the scenarios file, the page shows another pair,
    and the line under it was still the preferred pair's row."""
    browser, base = site
    batch, index, model = _clinical_constants()
    scenarios = {"scenarios": [_pair("fallback_batch", 7, 3, "three")]}       # the preferred pair is absent
    rows = [_row(batch, index, model, 3, 2, "downgrade"),                     # the preferred pair's row
            _row("fallback_batch", 3, model, 2, 0, "downgrade"),              # another pair of the fallback's batch
            _row("fallback_batch", 7, "another-model", 3, 0, "downgrade")]    # the fallback pair on another model
    shown = _row("fallback_batch", 7, model, 4, 1, "downgrade")
    urgency = {"vocabulary_status": "placeholder status", "tiers": TIERS, "rows": [*rows, shown]}
    line, label = _tier_line(browser, base, scenarios, urgency, last)
    assert label.endswith("batch fallback_batch #7")
    assert line == "care-urgency tier of the top word: Tier four → Tier one (a downgrade)"
    # the pair shown has no downgrade of its own, or no row at all: no line, whatever the preferred pair's row says
    for own in ([_row("fallback_batch", 7, model, 2, 2, None)], []):
        line, _ = _tier_line(browser, base, scenarios, {**urgency, "rows": [*rows, *own]}, last)
        assert line == ""


def test_the_clinical_tier_line_is_the_same_in_either_order_with_the_committed_files(site) -> None:
    """Each committed file delayed in turn. The two orders must agree; no value of the files is asserted."""
    browser, base = site
    if not all((SITE / "data" / name).is_file() for name in ("urgency_shift.json", "simulated_scenarios.json")):
        pytest.skip("the site checkout does not hold the two data files the Clinical page reads")
    seen = {last: _tier_line(browser, base, None, None, last) for last in ("urgency", "scenarios")}
    assert seen["urgency"] == seen["scenarios"]
    line, label = seen["urgency"]
    batch, index, model = _clinical_constants()
    rows = _fixture("urgency_shift.json")["rows"]
    row = next((r for r in rows if (r["batch"], r["index"], r["model"]) == (batch, index, model)), None)
    if label.endswith(f"batch {batch} #{index}") and row and row.get("flip_class") == "downgrade":
        assert line.startswith("care-urgency tier of the top word: ") and line.endswith("(a downgrade)")


# ------------------------------------------------------------------ Scenarios: the filters on a phone

SCENARIO_GALLERY = "/simulated-scenarios/index.html"
FILTER_SELECTS = ("sim-model-sel", "sim-fsel-condition")

_FILTERS_LOADED = """(ids) => ids.every(id => { const select = document.getElementById(id);
    return select && select.options.length > 1; })"""
_PAGE_WIDTH = """(ids) => ({page: document.documentElement.scrollWidth, viewport: window.innerWidth,
    edges: Object.fromEntries(ids.map(id => { const box = document.getElementById(id).getBoundingClientRect();
        return [id, [box.left, box.right]]; }))})"""
_ADD_LONG_OPTION = """(ids) => ids.forEach(id => { const option = document.createElement('option');
    option.textContent = 'a placeholder option that is much longer than the viewport is wide '.repeat(3);
    document.getElementById(id).appendChild(option); })"""


@pytest.mark.parametrize("width", [390, 360, 320])
def test_the_scenario_filters_do_not_make_the_page_wider_than_a_phone(site, width) -> None:
    """Regression (2026-11-11): a select as wide as its longest option made the page 426 px wide in a 390 px
    viewport, so the page scrolled sideways. The committed files are read as they are and no value is asserted;
    a longer placeholder option is then added to each select, so the check does not depend on the options the
    files happen to hold."""
    browser, base = site
    if not (SITE / "data" / "simulated_scenarios.json").is_file():
        pytest.skip("the site checkout does not hold the data file the Scenarios page reads")
    with _Page(browser, base, SCENARIO_GALLERY, width=width) as view:
        view.page.wait_for_function(_FILTERS_LOADED, arg=list(FILTER_SELECTS))
        for step in ("as loaded", "with a longer option"):
            seen = view.page.evaluate(_PAGE_WIDTH, list(FILTER_SELECTS))
            assert seen["viewport"] == width
            assert seen["page"] == seen["viewport"], (step, seen)
            for select, (left, right) in seen["edges"].items():
                assert 0 <= left < right <= seen["viewport"], (step, select, left, right)
            view.page.evaluate(_ADD_LONG_OPTION, list(FILTER_SELECTS))
        assert view.errors == []
