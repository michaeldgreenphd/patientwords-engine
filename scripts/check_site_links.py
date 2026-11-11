"""Check the site's masthead navigation and internal links against its route definition ($0, no browser).

The site has no build system: the masthead navigation is the same static markup repeated on each page
that has one, and nothing generates it. The site's hand-maintained ``docs/site_routes.json`` states what
that markup must be and lists every public route. This script reads that definition and the composed
pages (every ``*.html`` outside ``modes/``, the set ``check_pages.py`` loads) and reports, by class:

* ``navigation_mismatch``: a page's ``<nav aria-label="Site">`` differs from the definition in labels,
  order, hrefs, the ``aria-current="page"`` link or the disclosure summary; or a page without a masthead
  in the definition has one;
* ``navigation_exclusion``: a route the definition marks ``unlinked`` (the experiments page) is linked from
  a masthead, has lost ``noindex`` or has lost a text the definition requires it to keep;
* ``missing_file``: an internal link (``href``, ``src``, a meta refresh, a share-image URL on the site's
  own origin, a link written whole in a script) resolves to no file or directory index. Links INTO
  ``modes/`` are checked; the renders under ``modes/`` are not read as sources;
* ``missing_static_anchor``: a link's fragment is not the ``id`` of an element in the target page's
  source and is not declared as created at run time; or an anchor the definition lists as established
  has no element;
* ``undeclared_generated``: a link carries an address parameter, or a script builds a fragment, that the
  target page's entry in the definition does not declare;
* ``route_mismatch``: a route in the definition has no file, or a redirect stub does not redirect where
  the definition says;
* ``unlisted_page``: a composed page the definition does not list.

``generated_anchor`` is informational and never fails: a link that uses a declared address parameter or a
declared run-time fragment (``scenario.html?sim=``, ``#s<N>`` on the LLM page). The check confirms the
declaration, not the behaviour: no page is loaded.

What it reads in a script, and what it does not. Two forms are read: a string literal assigned to
``.href`` or ``.src``, given as an ``href:`` or ``src:`` property, or passed to
``setAttribute('href', ...)``. A literal that ends the expression is checked like a link in the markup.
A literal followed by ``+`` is the fixed start of a link the page completes at run time: its file (or,
when the literal ends inside the path, its directory) must exist and its parameter or fragment prefix
must be declared. Template literals, links assembled from variables and ``fetch`` targets are not read;
``check_pages.py`` loads the pages and fails on a failed data request.

Exit 0: no finding. Exit 1: at least one finding. Exit 2: blocked, the site or its definition is missing
or the definition is not usable; nothing was checked.

Usage:
  python scripts/check_site_links.py --site ../patientwords [--definition FILE] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

DEFINITION_REL = "docs/site_routes.json"
DEFINITION_SCHEMA = "patientwords.site_routes.v1"
REPORT_SCHEMA = "patientwords.site_link_report.v1"

# The same source set as check_pages.discover_pages: renders under modes/ are engine output.
EXCLUDED_TOP = frozenset({"modes", ".git"})

MASTHEAD_KINDS = frozenset({"home", "primary", "more", "detail", "unlinked", "error"})
PLAIN_KINDS = frozenset({"standalone", "redirect"})

FINDING_CLASSES: tuple[str, ...] = (
    "navigation_mismatch", "navigation_exclusion", "missing_file", "missing_static_anchor",
    "undeclared_generated", "route_mismatch", "unlisted_page")
INFORMATIONAL_CLASSES: tuple[str, ...] = ("generated_anchor",)
CLASS_LABELS: dict[str, str] = {
    "navigation_mismatch": "navigation mismatch",
    "navigation_exclusion": "page kept out of the navigation",
    "missing_file": "missing file",
    "missing_static_anchor": "missing static anchor",
    "undeclared_generated": "undeclared address parameter or run-time anchor",
    "route_mismatch": "route mismatch",
    "unlisted_page": "unlisted page",
    "generated_anchor": "declared generated anchor (informational)",
}

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_REFRESH = re.compile(r"^\s*[0-9.]+\s*[;,]\s*(?:url\s*=\s*)?(['\"]?)(.*?)\1\s*$", re.IGNORECASE | re.DOTALL)
# A string literal assigned to .href/.src, given as an href:/src: property, or passed to setAttribute.
# Group 3 is the literal; group 4 is a "+" when the page appends a run-time value to it.
_SCRIPT_LINK = re.compile(
    r"""(?:\.(?:href|src)\s*=(?!=)|\b(?:href|src)\s*:|setAttribute\(\s*(['"])(?:href|src)\1\s*,)"""
    r"""\s*(['"])((?:\\.|(?!\2)[^\\\n])*)\2\s*(\+)?""")


class Blocked(Exception):
    """The check could not run. Reported with exit 2; never counted as a pass or as a finding."""


# ---------------------------------------------------------------- the definition

@dataclass(frozen=True)
class Generated:
    """An address parameter or a fragment that a page reads or creates at run time."""

    type: str
    names: tuple[str, ...]
    prefix: str
    pattern: re.Pattern[str] | None
    reason: str


@dataclass(frozen=True)
class Route:
    path: str
    file: str
    title: str
    kind: str
    current: str | None
    hrefs: str
    anchors: tuple[str, ...]
    generated: tuple[Generated, ...]
    redirect_to: str | None
    noindex: bool
    required_text: tuple[str, ...]

    def parameter(self, name: str) -> Generated | None:
        return next((g for g in self.generated if g.type == "query" and name in g.names), None)

    def fragment(self, value: str) -> Generated | None:
        return next((g for g in self.generated
                     if g.type == "fragment" and g.pattern is not None and g.pattern.fullmatch(value)), None)

    def fragment_prefix(self, value: str) -> Generated | None:
        return next((g for g in self.generated
                     if g.type == "fragment" and g.prefix and value.startswith(g.prefix)), None)


@dataclass(frozen=True)
class NavEntry:
    group: str
    label: str
    route: str | None
    href: str | None


@dataclass(frozen=True)
class Definition:
    public_base: str
    base_path: str
    nav_label: str
    more_summary: str
    separator: str
    entries: tuple[NavEntry, ...]
    routes: dict[str, Route]

    def by_path(self, path: str) -> Route | None:
        return next((r for r in self.routes.values() if r.path == path), None)

    def group(self, group: str) -> list[NavEntry]:
        return [e for e in self.entries if e.group == group]


def route_file(path: str) -> str:
    """The file a route is served from: a directory route is its index.html."""
    return path + "index.html" if path == "" or path.endswith("/") else path


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise Blocked(f"{where} must be a list of non-empty strings")
    return tuple(value)


def _generated(raw: Any, where: str) -> Generated:
    if not isinstance(raw, dict) or not isinstance(raw.get("reason"), str) or not raw["reason"].strip():
        raise Blocked(f"{where} must be an object with a one-line reason")
    if raw.get("type") == "query":
        return Generated("query", _strings(raw.get("names"), f"{where}.names"), "", None, raw["reason"])
    if raw.get("type") == "fragment":
        prefix, pattern = raw.get("prefix"), raw.get("pattern")
        if not isinstance(prefix, str) or not prefix or not isinstance(pattern, str):
            raise Blocked(f"{where} must give a non-empty prefix and a pattern")
        try:
            return Generated("fragment", (), prefix, re.compile(pattern), raw["reason"])
        except re.error as exc:
            raise Blocked(f"{where}.pattern is not a regular expression: {exc}") from exc
    raise Blocked(f'{where}.type must be "query" or "fragment"')


def _route(raw: Any, index: int) -> Route:
    where = f"routes[{index}]"
    if not isinstance(raw, dict) or not isinstance(raw.get("path"), str) or not isinstance(raw.get("title"), str):
        raise Blocked(f"{where} must be an object with a path and a title")
    path, kind = raw["path"], raw.get("kind")
    where = f'the route "{path}"'
    if path.startswith(("/", ".")) or "\\" in path or ".." in path.split("/"):
        raise Blocked(f"{where}: a path is relative to the site root, with no leading slash or dot segment")
    if kind not in MASTHEAD_KINDS | PLAIN_KINDS:
        raise Blocked(f"{where}: kind must be one of {sorted(MASTHEAD_KINDS | PLAIN_KINDS)}")
    hrefs = raw.get("hrefs", "relative")
    if hrefs not in ("relative", "absolute"):
        raise Blocked(f'{where}: hrefs must be "relative" or "absolute"')
    current = raw.get("current")
    if (kind == "detail") != isinstance(current, str):
        raise Blocked(f'{where}: "current" names the marked navigation link of a detail page, and of no other kind')
    redirect_to = raw.get("redirect_to")
    if (kind == "redirect") != isinstance(redirect_to, str):
        raise Blocked(f'{where}: "redirect_to" is required for a redirect, and for no other kind')
    generated = raw.get("generated", [])
    if not isinstance(generated, list):
        raise Blocked(f"{where}: generated must be a list")
    return Route(
        path=path, file=route_file(path), title=raw["title"], kind=kind, current=current, hrefs=hrefs,
        anchors=_strings(raw.get("anchors", []), f"{where}: anchors"),
        generated=tuple(_generated(g, f"{where}: generated[{i}]") for i, g in enumerate(generated)),
        redirect_to=redirect_to, noindex=raw.get("noindex") is True,
        required_text=_strings(raw.get("required_text", []), f"{where}: required_text"))


def parse_definition(raw: Any) -> Definition:
    """Build the definition from its JSON value. Raises Blocked when it cannot be used as stated."""
    if not isinstance(raw, dict) or raw.get("schema") != DEFINITION_SCHEMA:
        raise Blocked(f'the definition must be an object with "schema": "{DEFINITION_SCHEMA}"')
    public_base, base_path = raw.get("public_base"), raw.get("base_path")
    if not isinstance(public_base, str) or not public_base.endswith("/") or not _SCHEME.match(public_base):
        raise Blocked("public_base must be an absolute URL that ends with a slash")
    if not isinstance(base_path, str) or not (base_path.startswith("/") and base_path.endswith("/")):
        raise Blocked("base_path must begin and end with a slash")
    if not isinstance(raw.get("routes"), list) or not raw["routes"]:
        raise Blocked("routes must be a non-empty list")
    routes: dict[str, Route] = {}
    for index, item in enumerate(raw["routes"]):
        route = _route(item, index)
        if route.file in routes:
            raise Blocked(f'the route "{route.path}" is listed more than once')
        routes[route.file] = route
    by_path = {r.path: r for r in routes.values()}

    nav = raw.get("navigation")
    more = nav.get("more") if isinstance(nav, dict) else None
    if (not isinstance(nav, dict) or not isinstance(nav.get("aria_label"), str)
            or not isinstance(nav.get("primary"), list)
            or not isinstance(more, dict) or not isinstance(more.get("links"), list)
            or not isinstance(more.get("summary"), str) or not isinstance(more.get("current_separator"), str)):
        raise Blocked("navigation must give aria_label, primary and more (summary, current_separator, links)")
    entries: list[NavEntry] = []
    for group, items in (("primary", nav["primary"]), ("more", more["links"])):
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("label"), str):
                raise Blocked(f"each {group} navigation entry must be an object with a label")
            route, href = item.get("route"), item.get("href")
            if isinstance(route, str) == isinstance(href, str):
                raise Blocked(f'the navigation entry "{item["label"]}" must give a route or an href, not both')
            if isinstance(route, str):
                target = by_path.get(route)
                if target is None:
                    raise Blocked(f'the navigation entry "{item["label"]}" names "{route}", which is not a route')
                if target.kind != group:
                    raise Blocked(f'the {group} navigation lists "{route}", whose kind is "{target.kind}"; '
                                  "a route's kind and its place in the navigation must agree")
            elif not _SCHEME.match(href):
                raise Blocked(f'the navigation entry "{item["label"]}" has an href that is not an absolute URL')
            entries.append(NavEntry(group, item["label"], route if isinstance(route, str) else None,
                                    href if isinstance(href, str) else None))
    if len({e.label for e in entries}) != len(entries):
        raise Blocked("two navigation entries share a label")
    listed = {e.route for e in entries if e.route is not None}
    for route in routes.values():
        if route.kind in ("primary", "more") and route.path not in listed:
            raise Blocked(f'the route "{route.path}" has kind "{route.kind}" and the navigation does not list it')
        if route.current is not None and route.current not in listed:
            raise Blocked(f'the route "{route.path}": current names "{route.current}", '
                          "which the navigation does not list")
    return Definition(public_base=public_base, base_path=base_path, nav_label=nav["aria_label"],
                      more_summary=more["summary"], separator=more["current_separator"],
                      entries=tuple(entries), routes=routes)


def load_definition(path: Path) -> Definition:
    if not path.is_file():
        raise Blocked(f"no route definition at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Blocked(f"the route definition at {path} could not be read: {exc}") from exc
    return parse_definition(raw)


# ---------------------------------------------------------------- reading a page

@dataclass
class Link:
    attr: str
    value: str
    line: int


@dataclass
class NavLink:
    group: str
    href: str
    current: str | None
    line: int
    label: str = ""


@dataclass
class Nav:
    line: int
    links: list[NavLink] = field(default_factory=list)
    disclosures: int = 0
    summary: str = ""


@dataclass
class ScriptLink:
    value: str
    line: int
    prefix: bool


def _squash(text: str) -> str:
    return " ".join(text.split())


class PageParser(HTMLParser):
    """Collects what the checks read from one page's source: ids, links, the site navigation, scripts."""

    def __init__(self, nav_label: str) -> None:
        super().__init__(convert_charrefs=True)
        self.nav_label = nav_label
        self.ids: set[str] = set()
        self.links: list[Link] = []
        self.navs: list[Nav] = []
        self.refresh: list[Link] = []
        self.meta_urls: list[Link] = []
        self.noindex = False
        self.scripts: list[tuple[int, str]] = []
        self._nav: Nav | None = None
        self._nav_depth = 0
        self._more_depth = 0
        self._in_summary = False
        self._anchor: NavLink | None = None
        self._script: list[str] | None = None
        self._script_line = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: (value or "") for name, value in attrs}
        line = self.getpos()[0]
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("name"):
            self.ids.add(values["name"])
        for attr in ("href", "xlink:href", "src"):
            if attr in values:
                self.links.append(Link(attr, values[attr], line))
        if tag == "meta":
            self._meta(values, line)
        elif tag == "script" and "src" not in values:
            self._script, self._script_line = [], line
        self._nav_start(tag, values, line)

    def _meta(self, values: dict[str, str], line: int) -> None:
        content = values.get("content", "")
        if values.get("name", "").lower() == "robots" and "noindex" in content.lower():
            self.noindex = True
        if values.get("http-equiv", "").lower() == "refresh":
            match = _REFRESH.match(content)
            self.refresh.append(Link("refresh", match.group(2) if match else content, line))
        elif _SCHEME.match(content.strip()) and " " not in content.strip():
            self.meta_urls.append(Link("content", content.strip(), line))

    def _nav_start(self, tag: str, values: dict[str, str], line: int) -> None:
        if tag == "nav":
            if self._nav is not None:
                self._nav_depth += 1
            elif values.get("aria-label") == self.nav_label:
                self._nav, self._nav_depth = Nav(line), 1
                self.navs.append(self._nav)
            return
        if self._nav is None:
            return
        if tag == "details":
            if self._more_depth:
                self._more_depth += 1
            elif "nav-more" in values.get("class", "").split():
                self._more_depth = 1
                self._nav.disclosures += 1
        elif tag == "summary" and self._more_depth == 1:
            self._in_summary = True
        elif tag == "a":
            self._anchor = NavLink("more" if self._more_depth else "primary", values.get("href", ""),
                                   values.get("aria-current"), line)
            self._nav.links.append(self._anchor)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            self.scripts.append((self._script_line, "".join(self._script)))
            self._script = None
        if self._nav is None:
            return
        if tag == "a":
            self._anchor = None
        elif tag == "summary":
            self._in_summary = False
        elif tag == "details" and self._more_depth:
            self._more_depth -= 1
        elif tag == "nav":
            self._nav_depth -= 1
            if self._nav_depth == 0:
                self._nav, self._anchor, self._more_depth, self._in_summary = None, None, 0, False

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)
        elif self._anchor is not None:
            self._anchor.label += data
        elif self._nav is not None and self._in_summary:
            self._nav.summary += data

    def script_links(self) -> list[ScriptLink]:
        """Link literals in the inline scripts, with the line of the page they are on."""
        found: list[ScriptLink] = []
        for start, body in self.scripts:
            for match in _SCRIPT_LINK.finditer(body):
                value = re.sub(r"\\(.)", r"\1", match.group(3))
                found.append(ScriptLink(value, start + body.count("\n", 0, match.start(3)), match.group(4) is not None))
        return found


def read_page(path: Path, nav_label: str) -> PageParser:
    parser = PageParser(nav_label)
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()
    return parser


def discover_pages(site: Path) -> list[str]:
    """Every composed page, as a site-root-relative file path. Renders under modes/ are not sources."""
    pages = []
    for path in sorted(site.rglob("*.html")):
        rel = path.relative_to(site)
        if rel.parts and rel.parts[0] in EXCLUDED_TOP:
            continue
        pages.append(rel.as_posix())
    return pages


# ---------------------------------------------------------------- resolving a link

@dataclass(frozen=True)
class Reference:
    """An internal link, reduced to a site-root-relative path, a query and a fragment."""

    path: str
    wants_directory: bool
    query: str
    has_query: bool
    fragment: str
    has_fragment: bool
    problem: str | None = None


def reference(url: str, page: str, definition: Definition) -> Reference | None:
    """The internal reference a link makes from `page`, or None when the link leaves the site.

    A URL on the site's public origin and a root-absolute path under the published path are internal. A
    root-absolute path outside the published path is internal and unresolvable: on the project site it
    names another site.
    """
    text = url.strip()
    origin = definition.public_base.rstrip("/")
    relative = False
    if text == origin or text.startswith(definition.public_base):
        rest = text[len(definition.public_base):]
    elif text.startswith("//") or _SCHEME.match(text):
        return None
    elif text.startswith("/"):
        if text == definition.base_path.rstrip("/") or text.startswith(definition.base_path):
            rest = text[len(definition.base_path):]
        else:
            return Reference("", False, "", False, "", False,
                             f"is a root-absolute path outside the published path {definition.base_path}")
    else:
        rest, relative = text, True
    parts = urlsplit(rest)
    raw_path = unquote(parts.path)
    if raw_path:
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(page) if relative else "", raw_path))
    else:
        joined = page if relative else ""
    joined = "" if joined == "." else joined
    problem = "leaves the site root" if joined == ".." or joined.startswith("../") else None
    return Reference(joined, raw_path.endswith("/"), parts.query, "?" in rest, unquote(parts.fragment),
                     "#" in rest, problem)


def resolve(site: Path, ref: Reference) -> str | None:
    """The site-root-relative file a reference is served from, or None when nothing is there."""
    target = site / ref.path if ref.path else site
    if target.is_dir():
        return posixpath.join(ref.path, "index.html") if (target / "index.html").is_file() else None
    return ref.path if target.is_file() and not ref.wants_directory else None


def expected_href(page: str, route: str, style: str, base_path: str) -> str:
    """The href the convention gives a navigation link to `route` on `page`."""
    if style == "absolute":
        return base_path + route
    here = posixpath.dirname(page) or "."
    if route == "" or route.endswith("/"):
        rel = posixpath.relpath(route.rstrip("/") or ".", here)
        return "./" if rel == "." else rel + "/"
    return posixpath.relpath(route, here)


# ---------------------------------------------------------------- the checks

@dataclass
class Report:
    pages: int = 0
    mastheads: int = 0
    internal_links: int = 0
    external_links: int = 0
    findings: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: {c: [] for c in FINDING_CLASSES})
    informational: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {c: [] for c in INFORMATIONAL_CLASSES})

    def add(self, kind: str, page: str, line: int, message: str) -> None:
        bucket = self.findings if kind in self.findings else self.informational
        bucket[kind].append({"page": page, "line": line, "message": message})

    @property
    def total(self) -> int:
        return sum(len(items) for items in self.findings.values())

    def as_dict(self, site: str, definition: str) -> dict[str, Any]:
        return {"schema": REPORT_SCHEMA, "site": site, "definition": definition, "ok": self.total == 0,
                "pages": self.pages, "mastheads": self.mastheads, "internal_links": self.internal_links,
                "external_links": self.external_links,
                "counts": {c: len(v) for c, v in {**self.findings, **self.informational}.items()},
                "findings": self.findings, "informational": self.informational}


class SiteCheck:
    """One run of every check over one site tree."""

    def __init__(self, site: Path, definition: Definition) -> None:
        self.site = site
        self.definition = definition
        self.report = Report()
        self.parsed: dict[str, PageParser] = {}
        for page in discover_pages(site):
            self.parsed[page] = read_page(site / page, definition.nav_label)
        self._ids: dict[str, set[str]] = {page: parser.ids for page, parser in self.parsed.items()}

    def ids(self, file: str) -> set[str]:
        """The static ids of an HTML file. A render under modes/ is read only when a link names an anchor in it."""
        if file not in self._ids:
            self._ids[file] = read_page(self.site / file, self.definition.nav_label).ids
        return self._ids[file]

    def run(self) -> Report:
        self.report.pages = len(self.parsed)
        self.check_routes()
        self.check_navigation()
        self.check_exclusions()
        self.check_links()
        self.check_established_anchors()
        return self.report

    # ---- (e) routes and pages agree

    def check_routes(self) -> None:
        add, definition = self.report.add, self.definition
        for route in definition.routes.values():
            if route.file not in self.parsed:
                add("route_mismatch", route.file, 0,
                    f'the definition lists the route "{route.path}" and the site has no such file')
        for page, parser in self.parsed.items():
            route = definition.routes.get(page)
            if route is None:
                add("unlisted_page", page, 0, "a composed page that the definition does not list")
                continue
            if route.kind != "redirect":
                for link in parser.refresh:
                    add("route_mismatch", page, link.line,
                        f'carries a meta refresh to "{link.value}" and the definition does not mark it a redirect')
                continue
            if len(parser.refresh) != 1:
                add("route_mismatch", page, 0,
                    f"the definition marks it a redirect; found {len(parser.refresh)} meta refresh elements, "
                    "expected one")
                continue
            link = parser.refresh[0]
            actual = reference(link.value, page, definition)
            wanted = reference(definition.base_path + (route.redirect_to or ""), page, definition)
            there = (resolve(self.site, actual), actual.fragment) if actual and not actual.problem else None
            want = (resolve(self.site, wanted), wanted.fragment) if wanted and not wanted.problem else None
            if there != want or there is None or there[0] is None:
                add("route_mismatch", page, link.line,
                    f'redirects to "{link.value}"; the definition states "{route.redirect_to}"')

    # ---- (a) the masthead navigation

    def check_navigation(self) -> None:
        for page, parser in self.parsed.items():
            route = self.definition.routes.get(page)
            if route is not None:
                self._navigation(page, route, parser)

    def _navigation(self, page: str, route: Route, parser: PageParser) -> None:
        definition = self.definition
        label = f'<nav aria-label="{definition.nav_label}">'

        def add(line: int, message: str) -> None:
            self.report.add("navigation_mismatch", page, line, message)

        if route.kind not in MASTHEAD_KINDS:
            for nav in parser.navs:
                add(nav.line, f'has a {label} and the definition gives it kind "{route.kind}", which has no masthead')
            return
        if len(parser.navs) != 1:
            add(0, f"expected one {label}, found {len(parser.navs)}")
            return
        self.report.mastheads += 1
        nav = parser.navs[0]
        for link in nav.links:
            link.label = _squash(link.label)
        for group in ("primary", "more"):
            wanted = definition.group(group)
            found = [link for link in nav.links if link.group == group]
            where = "the primary links" if group == "primary" else "the links inside the disclosure"
            if [link.label for link in found] != [entry.label for entry in wanted]:
                add(nav.line, f"{where} are {[link.label for link in found]}; "
                              f"the definition states {[entry.label for entry in wanted]}")
                continue
            for entry, link in zip(wanted, found):
                href = entry.href or expected_href(page, entry.route or "", route.hrefs, definition.base_path)
                if link.href != href:
                    add(link.line, f'"{entry.label}" has href "{link.href}", expected "{href}"')
        if nav.disclosures != 1:
            add(nav.line, f'expected one <details class="nav-more">, found {nav.disclosures}')

        current = route.path if route.kind in ("primary", "more") else route.current
        entry = next((e for e in definition.entries if e.route == current), None) if current is not None else None
        marked = [link for link in nav.links if link.current is not None]
        if entry is None:
            for link in marked:
                add(link.line, f'"{link.label}" carries aria-current="{link.current}"; '
                               "no navigation link is the current page here")
        elif [(link.label, link.current, link.group) for link in marked] != [(entry.label, "page", entry.group)]:
            shown = [f'{link.label}="{link.current}"' for link in marked]
            add(nav.line, f'aria-current="page" belongs on "{entry.label}" and on no other link; found {shown}')
        summary = definition.more_summary
        if entry is not None and entry.group == "more":
            summary += definition.separator + entry.label
        if _squash(nav.summary) != _squash(summary):
            add(nav.line, f'the disclosure summary reads "{_squash(nav.summary)}", expected "{_squash(summary)}"')

    # ---- (b) a page the definition keeps out of the navigation

    def check_exclusions(self) -> None:
        definition, add = self.definition, self.report.add
        unlinked = {r.file: r for r in definition.routes.values() if r.kind == "unlinked"}
        for page, parser in self.parsed.items():
            for nav in parser.navs:
                for link in nav.links:
                    ref = reference(link.href, page, definition)
                    target = resolve(self.site, ref) if ref is not None and ref.problem is None else None
                    if target in unlinked:
                        add("navigation_exclusion", page, link.line,
                            f'the masthead links to "{unlinked[target].path}" (href "{link.href}"); '
                            "the definition keeps that page out of the navigation")
        for file, route in unlinked.items():
            parser = self.parsed.get(file)
            if parser is None:
                continue
            if route.noindex and not parser.noindex:
                add("navigation_exclusion", file, 0, 'no longer carries <meta name="robots" content="noindex">')
            source = (self.site / file).read_text(encoding="utf-8", errors="replace")
            for text in route.required_text:
                if text not in source:
                    add("navigation_exclusion", file, 0, f'no longer contains the text "{text}"')

    # ---- (c) and (d) links and fragments

    def check_links(self) -> None:
        for page, parser in self.parsed.items():
            for link in parser.links + parser.refresh:
                self._link(page, link.line, f'{link.attr}="{link.value}"', link.value)
            for link in parser.meta_urls:
                if link.value.startswith(self.definition.public_base.rstrip("/")):
                    self._link(page, link.line, f'{link.attr}="{link.value}"', link.value)
            for script in parser.script_links():
                if script.prefix:
                    self._prefix(page, script.line, script.value)
                else:
                    self._link(page, script.line, f'the script link "{script.value}"', script.value)

    def _internal(self, page: str, line: int, shown: str, url: str) -> Reference | None:
        """The link as an internal reference; None when it leaves the site or cannot be placed in it."""
        ref = reference(url, page, self.definition)
        if ref is None:
            self.report.external_links += 1
            return None
        self.report.internal_links += 1
        if ref.problem is not None:
            self.report.add("missing_file", page, line, f"{shown} {ref.problem}")
            return None
        return ref

    def _link(self, page: str, line: int, shown: str, url: str) -> None:
        ref = self._internal(page, line, shown, url)
        if ref is None:
            return
        target = resolve(self.site, ref)
        if target is None:
            lacks = "no index.html" if (self.site / ref.path).is_dir() else "no file"
            self.report.add("missing_file", page, line,
                            f'{shown} resolves to "{ref.path or "."}", where the site has {lacks}')
            return
        route = self.definition.routes.get(target)
        if route is not None:
            for name, _ in parse_qsl(ref.query, keep_blank_values=True):
                self._parameter(page, line, shown, target, route, name)
        if not ref.fragment or not target.endswith((".html", ".htm")):
            return
        if ref.fragment in self.ids(target) or ref.fragment.lower() == "top":
            return
        declared = route.fragment(ref.fragment) if route is not None else None
        if declared is not None:
            self.report.add("generated_anchor", page, line,
                            f'{shown}: {target} creates "#{ref.fragment}" at run time. {declared.reason}')
        else:
            self.report.add("missing_static_anchor", page, line,
                            f'{shown}: no element in {target} has id "{ref.fragment}", '
                            "and the definition declares no run-time anchor of that form")

    def _parameter(self, page: str, line: int, shown: str, target: str, route: Route, name: str) -> None:
        declared = route.parameter(name)
        if declared is not None:
            self.report.add("generated_anchor", page, line,
                            f'{shown}: {target} reads the address parameter "{name}". {declared.reason}')
        else:
            self.report.add("undeclared_generated", page, line,
                            f'{shown}: the definition declares no address parameter "{name}" for {target}')

    def _prefix(self, page: str, line: int, value: str) -> None:
        """A script literal followed by "+": the fixed start of a link the page completes at run time."""
        shown = f'the script link "{value}" + a run-time value'
        ref = self._internal(page, line, shown, value)
        if ref is None:
            return
        if not ref.has_query and not ref.has_fragment:
            directory = ref.path if ref.wants_directory else posixpath.dirname(ref.path)
            if not (self.site / directory).is_dir():
                self.report.add("missing_file", page, line, f'{shown}: the site has no directory "{directory}/"')
            return
        target = resolve(self.site, ref)
        if target is None:
            self.report.add("missing_file", page, line,
                            f'{shown} resolves to "{ref.path or "."}", where the site has no file')
            return
        route = self.definition.routes.get(target)
        if route is None:
            return
        if ref.has_query:
            pieces = ref.query.split("&")
            if not ref.has_fragment and "=" not in pieces[-1]:
                pieces = pieces[:-1]   # the literal ends inside a parameter name
            for piece in pieces:
                if piece:
                    self._parameter(page, line, shown, target, route, unquote(piece.split("=", 1)[0]))
        if ref.has_fragment and ref.fragment:
            declared = route.fragment_prefix(ref.fragment)
            if declared is not None:
                self.report.add("generated_anchor", page, line,
                                f'{shown}: {target} creates "#{declared.prefix}…" at run time. {declared.reason}')
            else:
                self.report.add("undeclared_generated", page, line,
                                f'{shown}: the definition declares no run-time anchor beginning "{ref.fragment}" '
                                f"for {target}")

    # ---- anchors the definition lists as established

    def check_established_anchors(self) -> None:
        for route in self.definition.routes.values():
            if route.file not in self.parsed:
                continue
            for anchor in route.anchors:
                if anchor not in self.ids(route.file):
                    self.report.add("missing_static_anchor", route.file, 0,
                                    f'the definition lists "#{anchor}" as an established anchor '
                                    "and no element has that id")


def check_site(site: Path, definition: Definition) -> Report:
    """Run every check. The caller has established that `site` is a directory."""
    return SiteCheck(site, definition).run()


# ---------------------------------------------------------------- command line

def render(report: Report) -> str:
    lines = [f"{report.pages} composed pages, {report.mastheads} mastheads, {report.internal_links} internal links "
             f"checked, {report.external_links} external links not followed"]
    for kind in (*FINDING_CLASSES, *INFORMATIONAL_CLASSES):
        items = report.findings.get(kind, report.informational.get(kind, []))
        lines.append(f"{CLASS_LABELS[kind]}: {len(items)}")
        for item in items:
            where = item["page"] + (f":{item['line']}" if item["line"] else "")
            lines.append(f"  {where}: {item['message']}")
    lines.append("no finding" if report.total == 0 else f"{report.total} finding(s)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--site", type=Path, required=True, help="the patientwords site checkout")
    parser.add_argument("--definition", type=Path, help=f"the route definition (default: <site>/{DEFINITION_REL})")
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args(argv)
    try:
        if not args.site.is_dir():
            raise Blocked(f"no such site directory: {args.site}")
        definition_path = args.definition or args.site / DEFINITION_REL
        definition = load_definition(definition_path)
        if not discover_pages(args.site):
            raise Blocked(f"no composed page found under {args.site}")
    except Blocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    report = check_site(args.site, definition)
    print(render(report))
    if args.json is not None:
        args.json.write_text(json.dumps(report.as_dict(str(args.site), str(definition_path)), indent=1) + "\n",
                             encoding="utf-8")
    return 0 if report.total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
