"""The static link and navigation check reports each kind of defect under its own class.

``scripts/check_site_links.py`` compares the site's composed pages with the site's hand-maintained
``docs/site_routes.json``: the masthead navigation each page repeats, every internal link, every fragment
and the list of routes. These tests build a small site tree in a temporary directory, with its own
definition, and plant one defect at a time. Each test requires the finding to appear in the class the
defect belongs to and in no other, so a defect cannot pass because a neighbouring check happened to
notice it. The tree is synthetic: nine short pages with made-up names. A pass here says the checker's
rules behave as written. It says nothing about the published site.

The last tests run the checker on the sibling site checkout and require exit 0. They are skipped where
that checkout is not on disk, and where it is a revision from before the definition file was added.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


links = _load("check_site_links")

ORIGIN = "https://example.invalid/proj/"
BASE = "/proj/"
CODE = "https://example.invalid/code"


def definition() -> dict[str, Any]:
    return {
        "schema": "patientwords.site_routes.v1",
        "public_base": ORIGIN,
        "base_path": BASE,
        "navigation": {
            "aria_label": "Site",
            "primary": [{"label": "Start", "route": "start/"}, {"label": "List", "route": "list/"}],
            "more": {"summary": "More", "current_separator": " · ",
                     "links": [{"label": "Notes", "route": "notes/"}, {"label": "Code", "href": CODE}]},
        },
        "routes": [
            {"path": "", "title": "Home", "kind": "home", "anchors": ["kept"]},
            {"path": "start/", "title": "Start", "kind": "primary"},
            {"path": "list/", "title": "List", "kind": "primary", "generated": [
                {"type": "fragment", "prefix": "s", "pattern": "^s[0-9]+$", "reason": "Selects row N."}]},
            {"path": "list/item.html", "title": "Item", "kind": "detail", "current": "list/", "generated": [
                {"type": "query", "names": ["sim"], "reason": "The row to show."}]},
            {"path": "notes/", "title": "Notes", "kind": "more"},
            {"path": "lab/", "title": "Lab", "kind": "unlinked", "noindex": True,
             "required_text": ["Synthetic fixture: not a measurement"]},
            {"path": "404.html", "title": "Not found", "kind": "error", "hrefs": "absolute"},
            {"path": "card.html", "title": "Card", "kind": "standalone"},
            {"path": "old/", "title": "Old", "kind": "redirect", "redirect_to": "notes/#part"},
        ],
    }


def masthead(prefix: str, current: str | None = None) -> str:
    """The navigation of one page, written out as the convention states it: the current page's own link is
    "./" and carries aria-current, and the summary names the page when its link is inside the disclosure."""
    def link(route: str, label: str) -> str:
        if route == current:
            return f'<a href="./" aria-current="page">{label}</a>'
        return f'<a href="{prefix}{route}">{label}</a>'
    here = '<span class="nav-here"> · Notes</span>' if current == "notes/" else ""
    return (f'<nav aria-label="Site">\n{link("start/", "Start")}\n{link("list/", "List")}\n'
            f'<details class="nav-more">\n<summary>More{here}</summary>\n<div class="nav-more-list">\n'
            f'{link("notes/", "Notes")}\n<a href="{CODE}">Code</a>\n</div>\n</details>\n</nav>')


def page(prefix: str, current: str | None = None, body: str = "", head: str = "") -> str:
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<title>t</title>\n{head}\n</head>\n<body>\n'
            f'<a class="wordmark" href="{prefix or "./"}">Home</a>\n{masthead(prefix, current)}\n'
            f'<main id="main">\n{body}\n</main>\n</body>\n</html>\n')


def build(root: Path) -> Path:
    """A clean synthetic site: every link resolves and every masthead follows the definition."""
    site = root / "site"
    files = {
        "index.html": page("", body='<p id="kept">kept</p>\n<a href="list/item.html?sim=3">row three</a>',
                           head=f'<link rel="canonical" href="{ORIGIN}">\n'
                                f'<meta property="og:image" content="{ORIGIN}assets/card.png">'),
        "start/index.html": page("../", "start/", body=(
            '<a href="../notes/#part">a part</a>\n<a href="../list/#s12">row twelve</a>\n'
            '<iframe src="../modes/render/index_01.html" title="render"></iframe>\n<a href="#main">top</a>')),
        "list/index.html": page("../", "list/", body=(
            "<script>\nvar a = {}, n = 4;\na.href = 'item.html?sim=' + n;\na.href = '#s' + n;\n"
            "a.src = '../modes/render/' + name;\na.href = 'https://example.invalid/x/' + n;\n</script>")),
        "list/item.html": page("../", "list/", body='<a href="./">back to the list</a>'),
        "notes/index.html": page("../", "notes/", body='<h2 id="part">Part</h2>'),
        "lab/index.html": page("../", head='<meta name="robots" content="noindex">',
                               body="<script>var LABEL = 'Synthetic fixture: not a measurement';</script>"),
        "404.html": page(BASE),
        "card.html": "<!doctype html>\n<title>card</title>\n<p>A page without a masthead.</p>\n",
        "old/index.html": ('<!doctype html>\n<meta http-equiv="refresh" content="0; url=../notes/#part">\n'
                           '<p>Moved to <a href="../notes/#part">Notes</a>.</p>\n'),
        "modes/render/index_01.html": '<!doctype html>\n<a href="gone.html">a broken link inside a render</a>\n',
        "assets/card.png": "not an image; the check only needs the file to exist",
        "docs/site_routes.json": json.dumps(definition(), indent=1),
    }
    for name, text in files.items():
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return site


def edit(site: Path, name: str, old: str, new: str) -> None:
    path = site / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{name}: expected {old!r} once, found {text.count(old)}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def add_to_body(site: Path, name: str, markup: str) -> None:
    edit(site, name, "</main>", markup + "\n</main>")


def run(site: Path) -> Any:
    return links.check_site(site, links.load_definition(site / "docs" / "site_routes.json"))


def classes(report: Any) -> set[str]:
    return {kind for kind, items in report.findings.items() if items}


def messages(report: Any, kind: str) -> list[str]:
    bucket = report.findings.get(kind, report.informational.get(kind))
    return [f"{item['page']}: {item['message']}" for item in bucket]


@pytest.fixture
def site(tmp_path: Path) -> Path:
    return build(tmp_path)


# ---- the clean tree

def test_a_clean_tree_has_no_finding_and_exits_zero(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = run(site)
    assert classes(report) == set(), report.findings
    assert (report.pages, report.mastheads) == (9, 7)
    assert links.main(["--site", str(site)]) == 0
    assert "no finding" in capsys.readouterr().out


def test_declared_generated_anchors_are_informational_and_named(site: Path) -> None:
    """The four generated links of the clean tree: a static link with a declared parameter, a static link to a
    declared run-time fragment, and the two a script builds. None is a finding."""
    report = run(site)
    listed = messages(report, "generated_anchor")
    assert len(listed) == 4, listed
    assert any('href="list/item.html?sim=3"' in m and 'address parameter "sim"' in m for m in listed)
    assert any('href="../list/#s12"' in m and "Selects row N." in m for m in listed)
    assert any("""the script link "item.html?sim=" + a run-time value""" in m for m in listed)
    assert any("""the script link "#s" + a run-time value""" in m for m in listed)
    assert report.total == 0


# ---- one defect at a time, each in its own class

def test_a_link_to_a_missing_file_is_a_missing_file(site: Path) -> None:
    add_to_body(site, "notes/index.html", '<a href="../nowhere/">nowhere</a>')
    report = run(site)
    assert classes(report) == {"missing_file"}
    assert messages(report, "missing_file") == [
        'notes/index.html: href="../nowhere/" resolves to "nowhere", where the site has no file']


def test_a_directory_without_an_index_is_a_missing_file(site: Path) -> None:
    (site / "empty").mkdir()
    add_to_body(site, "notes/index.html", '<a href="../empty/">empty</a>')
    report = run(site)
    assert classes(report) == {"missing_file"}
    assert "no index.html" in messages(report, "missing_file")[0]


def test_a_fragment_with_no_element_is_a_missing_static_anchor(site: Path) -> None:
    add_to_body(site, "start/index.html", '<a href="../notes/#absent">absent</a>')
    report = run(site)
    assert classes(report) == {"missing_static_anchor"}
    assert 'no element in notes/index.html has id "absent"' in messages(report, "missing_static_anchor")[0]


def test_a_fragment_outside_the_declared_pattern_is_a_missing_static_anchor(site: Path) -> None:
    """`#s12` on the list page is declared as created at run time. `#sx` has the prefix and not the form."""
    add_to_body(site, "start/index.html", '<a href="../list/#sx">not a row</a>')
    report = run(site)
    assert classes(report) == {"missing_static_anchor"}
    assert len(messages(report, "generated_anchor")) == 4


def test_removing_an_established_anchor_is_a_missing_static_anchor(site: Path) -> None:
    """No page links to the homepage's #kept. The definition lists it, so removing the id is still reported."""
    edit(site, "index.html", '<p id="kept">kept</p>', "<p>kept</p>")
    report = run(site)
    assert classes(report) == {"missing_static_anchor"}
    assert messages(report, "missing_static_anchor") == [
        'index.html: the definition lists "#kept" as an established anchor and no element has that id']


NAVIGATION_DEFECTS = [
    ("start/index.html", '<a href="./" aria-current="page">Start</a>\n<a href="../list/">List</a>',
     '<a href="../list/">List</a>\n<a href="./" aria-current="page">Start</a>',
     "the primary links are ['List', 'Start']; the definition states ['Start', 'List']"),
    ("notes/index.html", '<a href="../start/">Start</a>', '<a href="../start/index.html">Start</a>',
     '"Start" has href "../start/index.html", expected "../start/"'),
    ("start/index.html", '<a href="./" aria-current="page">Start</a>', '<a href="./">Start</a>',
     'aria-current="page" belongs on "Start" and on no other link; found []'),
    ("start/index.html", '<a href="../list/">List</a>', '<a href="../list/" aria-current="page">List</a>',
     """aria-current="page" belongs on "Start" and on no other link; found ['Start="page"', 'List="page"']"""),
    ("list/item.html", '<a href="./" aria-current="page">List</a>', '<a href="./" aria-current="true">List</a>',
     """aria-current="page" belongs on "List" and on no other link; found ['List="true"']"""),
    ("index.html", '<a href="start/">Start</a>', '<a href="start/" aria-current="page">Start</a>',
     '"Start" carries aria-current="page"; no navigation link is the current page here'),
    ("notes/index.html", '<span class="nav-here"> · Notes</span>', "",
     'the disclosure summary reads "More", expected "More · Notes"'),
    ("start/index.html", f'<a href="{CODE}">Code</a>\n', "",
     "the links inside the disclosure are ['Notes']; the definition states ['Notes', 'Code']"),
    ("404.html", '<a href="/proj/list/">List</a>', '<a href="list/">List</a>',
     '"List" has href "list/", expected "/proj/list/"'),
    ("start/index.html", '<details class="nav-more">', "<details>",
     "the links inside the disclosure are []; the definition states ['Notes', 'Code']"),
]


@pytest.mark.parametrize(("name", "old", "new", "expected"), NAVIGATION_DEFECTS)
def test_a_masthead_that_differs_from_the_definition_is_a_navigation_mismatch(
        site: Path, name: str, old: str, new: str, expected: str) -> None:
    edit(site, name, old, new)
    report = run(site)
    assert classes(report) == {"navigation_mismatch"}, report.findings
    assert f"{name}: {expected}" in messages(report, "navigation_mismatch")


def test_a_masthead_on_a_page_the_definition_gives_none_is_a_navigation_mismatch(site: Path) -> None:
    (site / "card.html").write_text(page(""), encoding="utf-8")
    report = run(site)
    assert classes(report) == {"navigation_mismatch"}
    found = messages(report, "navigation_mismatch")
    assert 'the definition gives it kind "standalone", which has no masthead' in found[0]


def test_a_page_that_lost_its_masthead_is_a_navigation_mismatch(site: Path) -> None:
    edit(site, "notes/index.html", '<nav aria-label="Site">', '<nav aria-label="Pages">')
    report = run(site)
    assert classes(report) == {"navigation_mismatch"}
    assert messages(report, "navigation_mismatch") == [
        'notes/index.html: expected one <nav aria-label="Site">, found 0']


def test_a_page_the_definition_does_not_list_is_an_unlisted_page(site: Path) -> None:
    (site / "extra").mkdir()
    (site / "extra" / "index.html").write_text("<!doctype html>\n<title>extra</title>\n", encoding="utf-8")
    report = run(site)
    assert classes(report) == {"unlisted_page"}
    assert messages(report, "unlisted_page") == [
        "extra/index.html: a composed page that the definition does not list"]


def test_a_masthead_link_to_the_unlinked_page_is_reported_as_an_exclusion(site: Path) -> None:
    """The page the definition keeps out of the navigation, linked from one masthead. The exclusion class
    names the page and the link. The navigation class reports the same edit for its own reason: the page's
    primary links are no longer the stated ones."""
    edit(site, "start/index.html", '<a href="../list/">List</a>',
         '<a href="../list/">List</a>\n<a href="../lab/">Lab</a>')
    report = run(site)
    assert classes(report) == {"navigation_exclusion", "navigation_mismatch"}
    assert messages(report, "navigation_exclusion") == [
        'start/index.html: the masthead links to "lab/" (href "../lab/"); '
        "the definition keeps that page out of the navigation"]
    assert "the primary links are ['Start', 'List', 'Lab']" in messages(report, "navigation_mismatch")[0]


def test_a_link_to_the_unlinked_page_outside_a_masthead_is_not_an_exclusion(site: Path) -> None:
    add_to_body(site, "start/index.html", '<a href="../lab/">the lab page</a>')
    assert classes(run(site)) == set()


@pytest.mark.parametrize(("old", "new", "expected"), [
    ('<meta name="robots" content="noindex">', "", 'no longer carries <meta name="robots" content="noindex">'),
    ("Synthetic fixture: not a measurement", "Fixture",
     'no longer contains the text "Synthetic fixture: not a measurement"'),
])
def test_the_unlinked_page_keeps_its_noindex_and_its_label(site: Path, old: str, new: str, expected: str) -> None:
    edit(site, "lab/index.html", old, new)
    report = run(site)
    assert classes(report) == {"navigation_exclusion"}
    assert messages(report, "navigation_exclusion") == [f"lab/index.html: {expected}"]


def test_a_definition_that_puts_the_unlinked_page_in_the_navigation_is_refused(site: Path) -> None:
    """Adding the page to the navigation means changing its kind, which is one deliberate edit. A definition
    that lists it in the navigation and still marks it unlinked contradicts itself and blocks the check."""
    changed = definition()
    changed["navigation"]["primary"].append({"label": "Lab", "route": "lab/"})
    (site / "docs" / "site_routes.json").write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(links.Blocked, match='the primary navigation lists "lab/", whose kind is "unlinked"'):
        run(site)
    assert links.main(["--site", str(site)]) == 2


def test_a_route_without_a_file_is_a_route_mismatch(site: Path) -> None:
    (site / "card.html").unlink()
    report = run(site)
    assert classes(report) == {"route_mismatch"}
    assert messages(report, "route_mismatch") == [
        'card.html: the definition lists the route "card.html" and the site has no such file']


@pytest.mark.parametrize(("old", "new", "expected"), [
    ('<meta http-equiv="refresh" content="0; url=../notes/#part">\n',
     '<meta http-equiv="refresh" content="0; url=../notes/">\n',
     'redirects to "../notes/"; the definition states "notes/#part"'),
    ('<meta http-equiv="refresh" content="0; url=../notes/#part">\n', "",
     "the definition marks it a redirect; found 0 meta refresh elements, expected one"),
])
def test_a_redirect_stub_that_goes_elsewhere_is_a_route_mismatch(site: Path, old: str, new: str, expected: str) -> None:
    edit(site, "old/index.html", old, new)
    report = run(site)
    assert classes(report) == {"route_mismatch"}
    assert messages(report, "route_mismatch") == [f"old/index.html: {expected}"]


def test_an_address_parameter_the_target_does_not_declare_is_reported(site: Path) -> None:
    add_to_body(site, "notes/index.html", '<a href="../list/item.html?row=3">row three</a>')
    report = run(site)
    assert classes(report) == {"undeclared_generated"}
    assert messages(report, "undeclared_generated") == [
        'notes/index.html: href="../list/item.html?row=3": the definition declares no address parameter "row" '
        "for list/item.html"]


# ---- links written in a script

SCRIPT_DEFECTS = [
    ("a.href = '../absent/';", "missing_file", 'the script link "../absent/" resolves to "absent"'),
    ("a.setAttribute('href', '../notes/#absent');", "missing_static_anchor", 'has id "absent"'),
    ("var o = {href: 'item.html?row=' + n};", "undeclared_generated", 'no address parameter "row" for list/item.html'),
    ("a.href = '#row-' + n;", "undeclared_generated", 'no run-time anchor beginning "row-" for list/index.html'),
    ("a.src = '../modes/absent/' + name;", "missing_file", 'the site has no directory "modes/absent/"'),
]


@pytest.mark.parametrize(("statement", "kind", "expected"), SCRIPT_DEFECTS)
def test_a_link_written_in_a_script_is_checked_like_one_in_the_markup(
        site: Path, statement: str, kind: str, expected: str) -> None:
    edit(site, "list/index.html", "</script>", statement + "\n</script>")
    report = run(site)
    assert classes(report) == {kind}, report.findings
    assert expected in messages(report, kind)[0]
    assert report.findings[kind][0]["line"] > 0


def test_script_forms_the_check_does_not_read_produce_no_finding(site: Path) -> None:
    """A comparison, a link taken from a variable and a fetch target are not link literals."""
    edit(site, "list/index.html", "</script>",
         "if (a.href === '../absent/') { a.href = other; }\nfetch('../absent.json');\n</script>")
    assert classes(run(site)) == set()


# ---- what counts as internal, and what is read as a source

def test_a_link_into_modes_must_resolve_and_a_render_is_not_a_source(site: Path) -> None:
    """The clean tree's render holds a broken link and is in no definition: neither is reported, because renders
    are not read as sources. A page's link to a render that does not exist is reported."""
    assert classes(run(site)) == set()
    edit(site, "start/index.html", "../modes/render/index_01.html", "../modes/render/index_02.html")
    report = run(site)
    assert classes(report) == {"missing_file"}
    assert 'src="../modes/render/index_02.html"' in messages(report, "missing_file")[0]


@pytest.mark.parametrize(("markup", "expected"), [
    (f'<a href="{ORIGIN}absent/">absolute</a>', 'resolves to "absent", where the site has no file'),
    (f'<meta property="og:image" content="{ORIGIN}assets/absent.png">', 'resolves to "assets/absent.png"'),
    ('<a href="/proj/absent.html">root-absolute</a>', 'resolves to "absent.html"'),
    ('<a href="/elsewhere/">outside</a>', "is a root-absolute path outside the published path /proj/"),
    ('<a href="../../above.html">above</a>', "leaves the site root"),
])
def test_links_on_the_public_origin_and_root_absolute_links_are_internal(
        site: Path, markup: str, expected: str) -> None:
    add_to_body(site, "notes/index.html", markup)
    report = run(site)
    assert classes(report) == {"missing_file"}
    assert expected in messages(report, "missing_file")[0]


def test_links_that_leave_the_site_are_not_followed(site: Path) -> None:
    before = run(site).external_links
    add_to_body(site, "notes/index.html",
                '<a href="https://example.invalid/other/absent">other</a> <a href="mailto:a@example.invalid">mail</a> '
                '<a href="//example.invalid/x">scheme-relative</a>')
    report = run(site)
    assert classes(report) == set()
    assert report.external_links == before + 3


# ---- blocked, and the report file

def test_a_missing_site_or_definition_blocks_with_exit_two(site: Path, tmp_path: Path,
                                                            capsys: pytest.CaptureFixture[str]) -> None:
    assert links.main(["--site", str(tmp_path / "absent")]) == 2
    assert "no such site directory" in capsys.readouterr().err
    (site / "docs" / "site_routes.json").unlink()
    assert links.main(["--site", str(site)]) == 2
    assert "no route definition" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["{not json", json.dumps({"schema": "another"}), json.dumps([])])
def test_an_unusable_definition_blocks_with_exit_two(site: Path, text: str) -> None:
    (site / "docs" / "site_routes.json").write_text(text, encoding="utf-8")
    assert links.main(["--site", str(site)]) == 2


def test_the_report_file_lists_every_class_and_the_exit_code_follows_it(site: Path, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    add_to_body(site, "notes/index.html", '<a href="../nowhere/">nowhere</a>')
    assert links.main(["--site", str(site), "--json", str(out)]) == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert set(report["findings"]) == set(links.FINDING_CLASSES)
    assert set(report["informational"]) == {"generated_anchor"}
    assert report["counts"]["missing_file"] == 1 and report["counts"]["generated_anchor"] == 4
    assert report["findings"]["missing_file"][0]["page"] == "notes/index.html"


def test_the_convention_for_a_navigation_href() -> None:
    """Written out, so the rule the navigation is held to is readable here and not only in the checker."""
    cases = [
        ("index.html", "start/", "relative", "start/"),
        ("methods.html", "methods.html", "relative", "methods.html"),
        ("clinical/index.html", "clinical/", "relative", "./"),
        ("clinical/index.html", "methods.html", "relative", "../methods.html"),
        ("simulated-scenarios/scenario.html", "simulated-scenarios/", "relative", "./"),
        ("llm/code.html", "start-here/", "relative", "../start-here/"),
        ("404.html", "start-here/", "absolute", "/proj/start-here/"),
    ]
    for page_file, route, style, expected in cases:
        assert links.expected_href(page_file, route, style, BASE) == expected, (page_file, route)


# ---- the sibling site

def _sibling_site() -> Path:
    if not SITE.is_dir():
        pytest.skip("the sibling site checkout is not on disk")
    if not (SITE / links.DEFINITION_REL).is_file():
        pytest.skip(f"the sibling site checkout has no {links.DEFINITION_REL}: it is a revision from before the "
                    "definition was added, and the paired check is blocked there (exit 2), not passed")
    return SITE


def test_the_sibling_site_passes(capsys: pytest.CaptureFixture[str]) -> None:
    site = _sibling_site()
    code = links.main(["--site", str(site)])
    assert code == 0, capsys.readouterr().out


def test_the_sibling_site_is_read_over_the_same_pages_as_the_browser_check() -> None:
    """`check_pages.py` loads every composed page in Chromium. This check must read the same set, or a page could
    be loaded there and never have its links read here."""
    site = _sibling_site()
    pages = _load("check_pages").discover_pages(site)
    assert ["/" + name for name in links.discover_pages(site)] == pages
    assert set(links.load_definition(site / links.DEFINITION_REL).routes) == set(links.discover_pages(site))
