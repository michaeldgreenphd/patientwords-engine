"""Extract the public site's static page text into one hierarchical Rmd for manual editing.

Walks the frontend checkout page by page (fixed order; 404.html excluded) and pulls
out each page's <title>, its meta description, and - inside <main> only - every
h1/h2/h3/p/li/summary/figcaption element's text in document order. Extraction is
strict: HTML entity unescaping and whitespace collapsing are the only transformations.
Nothing is reworded, corrected, or summarized - the intentional misspellings in the
stimuli must survive byte-for-byte. <script>/<style> content is skipped entirely, and
so are <nav> and <footer> subtrees (the footer provenance content is protected on the
site and is not up for editing). Text that page JS builds at runtime from the data
files cannot be extracted statically; each page section carries one note saying so.

Every emitted block is preceded by a deterministic HTML comment id
(<!-- id: <pageslug>.bNNN -->, a zero-padded per-page counter) so an edited Rmd can
be mapped back to its page and position. Reruns on the same input are byte-identical.

Usage:
  python scripts/extract_site_text.py [--site-root ../patientwords]
      [--out ops/site_text_outline.Rmd]

The artifact lives in THIS repo (ops/), never the site repo (owner directive
2026-07-09) — the outline is a working document, not site content.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Fixed extraction order (reading order); 404.html and redirect stubs excluded.
# word-differences/, syntax-differences/, answer-depth/, and model-evaluations/
# are one-line redirect stubs since the 2026-07-14 consolidation; their real
# content now lives on wording-differences/ and technical/ and is extracted there.
PAGES = [
    "index.html",
    "start-here/index.html",
    "methods.html",
    "technical/index.html",
    "simulated-scenarios/index.html",
    "wording-differences/index.html",
    "dialect-differences/index.html",
    "translation/index.html",
    "phrase-dataset/index.html",
]

CAPTURE_TAGS = {"h1", "h2", "h3", "p", "li", "summary", "figcaption"}
# Subtrees skipped wholesale: script/style are code, nav is chrome, footer is
# the protected provenance & acknowledgments content.
EXCLUDE_TAGS = {"script", "style", "nav", "footer"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}
# Tag boundaries that imply visual separation. A space is injected at each so text
# on either side never glues together ("doctors.<br>Medical" -> "doctors. Medical");
# whitespace collapse then removes any doubles. Inline tags (em/b/span/a...) are
# deliberately absent - a space there would split words.
BREAK_TAGS = {"br", "hr", "p", "li", "ul", "ol", "dl", "dt", "dd", "div", "section",
              "article", "aside", "header", "figure", "figcaption", "summary",
              "details", "blockquote", "pre", "table", "thead", "tbody", "tfoot",
              "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "button"}

DOC_TITLE = "PatientWords — site text for manual editing"
DOC_DATE = "2026-07-17"

# The only prose this script is allowed to author: the editing instructions and the
# one per-page note about runtime-generated text. Everything else is extracted verbatim.
INSTRUCTIONS = "\n".join([
    "**Instructions.**",
    "Edit the site text in place, block by block.",
    "Each block is preceded by an HTML comment id (`<!-- id: <page>.bNNN -->`) that maps it"
    " back to its page and position — keep the comments and do not reorder blocks.",
    "To delete text, delete the block body but keep its id comment.",
    "Dynamic table/chart text is generated at runtime by page JS from the data files and is not included here.",
    "Site navigation and footers are excluded; the provenance & acknowledgments footer content is protected.",
])
PAGE_NOTE = "*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*"

PREFIXES = {"h1": "## ", "h2": "## ", "h3": "### ", "p": "",
            "li": "- ", "summary": "*fold:* ", "figcaption": "*caption:* "}


def collapse(text):
    """Whitespace-collapse to single spaces (entities are already unescaped by the parser)."""
    return " ".join(text.split())


class PageTextParser(HTMLParser):
    """Collect <title>, the meta description, and capture-tag blocks inside <main>.

    convert_charrefs=True (the default) performs the entity unescaping; nothing else
    touches the text. The outermost capture element wins: a <p> inside an <li> feeds
    the open li block instead of starting its own, so nested markup never duplicates
    text. blocks is a list of (tag, normalized_text) in document order.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.meta_description = None
        self.blocks = []
        self._in_title = False
        self._title_parts = []
        self._main_depth = 0
        self._exclude_depth = 0
        self._block_tag = None
        self._block_depth = 0
        self._buf = []

    def _open(self, tag):
        self._block_tag, self._block_depth, self._buf = tag, 0, []

    def _flush(self):
        if self._block_tag is not None:
            text = collapse("".join(self._buf))
            if text:  # elements empty after normalization are skipped
                self.blocks.append((self._block_tag, text))
        self._block_tag, self._block_depth, self._buf = None, 0, []

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            if self.meta_description is None:
                attr = dict(attrs)
                if (attr.get("name") or "").lower() == "description" and attr.get("content"):
                    self.meta_description = collapse(attr["content"])
            return
        if tag == "title":
            self._in_title = self.title is None
            return
        if tag in EXCLUDE_TAGS:
            self._flush()  # an excluded subtree ends any block it interrupts
            self._exclude_depth += 1
            return
        if self._exclude_depth:
            return
        if tag == "main":
            self._main_depth += 1
            return
        if not self._main_depth:
            return
        if self._block_tag is not None:
            if tag == self._block_tag and tag not in VOID_TAGS:
                if tag == "p":  # HTML forbids nested <p>: a new one implicitly closes the old
                    self._flush()
                    self._open(tag)
                    return
                self._block_depth += 1  # e.g. an <li> nested via an inner list
            if tag in BREAK_TAGS:
                self._buf.append(" ")
            return
        if tag in CAPTURE_TAGS:
            self._open(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            if self._in_title:
                self.title = collapse("".join(self._title_parts))
                self._in_title = False
            return
        if tag in EXCLUDE_TAGS:
            if self._exclude_depth:
                self._exclude_depth -= 1
            return
        if self._exclude_depth:
            return
        if tag == "main":
            self._flush()
            self._main_depth = max(0, self._main_depth - 1)
            return
        if not self._main_depth or self._block_tag is None:
            return
        if tag == self._block_tag:
            if self._block_depth:
                self._block_depth -= 1
                self._buf.append(" ")
            else:
                self._flush()
            return
        if tag in BREAK_TAGS:
            self._buf.append(" ")

    def handle_data(self, data):
        if self._exclude_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        elif self._block_tag is not None:
            self._buf.append(data)


def parse_page(html_text):
    parser = PageTextParser()
    parser.feed(html_text)
    parser.close()
    return parser


def page_slug(rel_path):
    """'index.html' -> 'index', 'start-here/index.html' -> 'start-here', 'methods.html' -> 'methods'."""
    parts = rel_path.split("/")
    if len(parts) > 1 and parts[-1] == "index.html":
        return parts[-2]
    return parts[-1].rsplit(".", 1)[0]


def render_page(rel_path, parsed):
    """One Rmd section for a page: heading, flagged meta description, id-tagged blocks, note."""
    slug = page_slug(rel_path)
    lines = [f"# {parsed.title or slug} — `{rel_path}`", ""]
    if parsed.meta_description:
        lines += [f"> ⚑ meta description: {parsed.meta_description}", ""]
    for number, (tag, text) in enumerate(parsed.blocks, start=1):
        lines += [f"<!-- id: {slug}.b{number:03d} -->", PREFIXES[tag] + text, ""]
    lines += [PAGE_NOTE, ""]
    return "\n".join(lines)


def render_document(page_sections):
    header = "\n".join(["---", f'title: "{DOC_TITLE}"', f'date: "{DOC_DATE}"',
                        "output: html_document", "---", "", INSTRUCTIONS, ""])
    return header + "\n" + "\n".join(page_sections)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-root", default=str(REPO_ROOT.parent / "patientwords"),
                        help="frontend checkout to extract from (default: the sibling ../patientwords)")
    parser.add_argument("--out", default=None,
                        help="output Rmd path (default: <this repo>/ops/site_text_outline.Rmd)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    site_root = Path(args.site_root)
    out_path = Path(args.out) if args.out else REPO_ROOT / "ops" / "site_text_outline.Rmd"
    sections, total = [], 0
    for rel_path in PAGES:
        parsed = parse_page((site_root / rel_path).read_text(encoding="utf-8"))
        sections.append(render_page(rel_path, parsed))
        total += len(parsed.blocks)
        print(f"{rel_path}: {len(parsed.blocks)} blocks")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_document(sections), encoding="utf-8")
    print(f"total: {total} blocks across {len(PAGES)} pages -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
