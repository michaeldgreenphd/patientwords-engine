"""Text that this repository and the site repository must keep identical.

Two blocks are shared with the public site repository (`patientwords`, the
sibling checkout `../patientwords`), and nothing compared them before this file:
the owner's writing conventions were said to be "identical across my repos"
while they existed in this repository alone.

1. **Writing conventions, `CLAUDE.md`.** The section whose heading line starts
   with `## Shared conventions`: from that heading line to the next heading of
   the same or a higher level (`#` or `##`), or to the end of the file. Deeper
   headings (`###` and below) stay inside it. The heading line is part of the
   comparison, so both copies must name the same repositories.
2. **The generic Code Review Rules, `AGENTS.md`.** The section whose heading
   line starts with `## Code Review Rules`: from that heading line up to the
   first heading of *any* level after it. Both repositories follow the generic
   bullets with a `### What those rules mean in this repository` subsection,
   which is repository-specific on purpose and is not compared.

Extraction rules, the same for both files: headings are ATX headings (up to
three spaces, one to six `#`, then a space, a tab or the end of the line);
lines inside fenced code blocks are never headings; the heading must occur
exactly once at its level, and a missing or repeated heading is a failure, not
a skip; trailing blank lines are dropped from a section, so a section at the
end of a file compares equal to one followed by another heading. Everything
else, including trailing spaces and line endings, is compared byte for byte.

The site checkout is `$PW_SITE_ROOT` when that variable is set (it must then be
a directory, or the comparison fails), and `../patientwords` next to this
repository otherwise. When the default sibling is absent the two cross-repository
tests skip with a visible reason; the extraction tests and the engine-side checks
still run.
"""
from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

CONVENTIONS_HEADING = "## Shared conventions"
REVIEW_RULES_HEADING = "## Code Review Rules"

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]|$)")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


class SectionError(ValueError):
    """The requested heading is missing, repeated, or not a heading."""


def heading_levels(lines: list[str]) -> list[int | None]:
    """The ATX heading level of each line, or None; fenced code is never a heading."""
    levels: list[int | None] = []
    fence: str | None = None
    for line in lines:
        fence_match = _FENCE.match(line)
        if fence is not None:
            closing = line.strip()
            if (fence_match and fence_match.group(1)[0] == fence[0]
                    and len(fence_match.group(1)) >= len(fence) and set(closing) == {fence[0]}):
                fence = None
            levels.append(None)
            continue
        if fence_match:
            fence = fence_match.group(1)
            levels.append(None)
            continue
        heading = _HEADING.match(line)
        levels.append(len(heading.group(1)) if heading else None)
    return levels


def extract_section(text: str, heading_prefix: str, *, stop_at_any_heading: bool = False) -> str:
    """The section whose heading line starts with `heading_prefix`, per the module docstring.

    `heading_prefix` must itself be a heading (for example `## Shared conventions`);
    its level decides which later heading ends the section. With
    `stop_at_any_heading`, the first later heading of any level ends it instead.
    """
    prefix_match = _HEADING.match(heading_prefix)
    if prefix_match is None:
        raise SectionError(f"{heading_prefix!r} is not a Markdown heading")
    level = len(prefix_match.group(1))
    lines = text.split("\n")
    levels = heading_levels(lines)
    starts = [i for i, lvl in enumerate(levels) if lvl == level and lines[i].startswith(heading_prefix)]
    if len(starts) != 1:
        found = "no" if not starts else f"{len(starts)}"
        raise SectionError(f"expected exactly one heading starting {heading_prefix!r}, found {found}")
    start = starts[0]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        lvl = levels[j]
        if lvl is not None and (stop_at_any_heading or lvl <= level):
            end = j
            break
    section = lines[start:end]
    while section and not section[-1].strip():
        section.pop()
    return "\n".join(section) + "\n"


def _section_of(path: Path, heading_prefix: str, *, stop_at_any_heading: bool = False) -> str:
    assert path.is_file(), f"{path} is missing"
    try:
        return extract_section(path.read_bytes().decode("utf-8"), heading_prefix,
                               stop_at_any_heading=stop_at_any_heading)
    except SectionError as exc:
        raise SectionError(f"{path}: {exc}") from exc


def _conventions(repo: Path) -> str:
    return _section_of(repo / "CLAUDE.md", CONVENTIONS_HEADING)


def _review_rules(repo: Path) -> str:
    return _section_of(repo / "AGENTS.md", REVIEW_RULES_HEADING, stop_at_any_heading=True)


def _diff(engine: str, site: str, name: str) -> str:
    return "".join(difflib.unified_diff(
        engine.splitlines(keepends=True), site.splitlines(keepends=True),
        fromfile=f"patientwords-engine/{name}", tofile=f"patientwords/{name}"))


@pytest.fixture
def site_root() -> Path:
    override = os.environ.get("PW_SITE_ROOT")
    if override:
        root = Path(override).expanduser()
        if not root.is_dir():
            pytest.fail(f"PW_SITE_ROOT={override!r} is not a directory")
        return root
    root = ROOT.parent / "patientwords"
    if not root.is_dir():
        pytest.skip(f"site checkout not found at {root}; set PW_SITE_ROOT to compare the shared text")
    return root


# --- extraction ---------------------------------------------------------------------------

DOC = """# Title

## Shared conventions (both repos)

Body line.
### Deeper heading
Still inside.

## Next section
Outside.
"""


def test_section_runs_to_next_heading_of_same_level_and_keeps_deeper_ones() -> None:
    assert extract_section(DOC, "## Shared conventions") == (
        "## Shared conventions (both repos)\n\nBody line.\n### Deeper heading\nStill inside.\n")


def test_section_stops_at_a_higher_level_heading() -> None:
    text = "## A\nbody\n# Top\nafter\n"
    assert extract_section(text, "## A") == "## A\nbody\n"


def test_section_at_end_of_file_drops_trailing_blank_lines() -> None:
    assert extract_section("## A\nbody\n\n  \n\n", "## A") == "## A\nbody\n"
    assert extract_section("## A\nbody", "## A") == "## A\nbody\n"


def test_stop_at_any_heading_ends_at_the_first_subheading() -> None:
    assert extract_section(DOC, "## Shared conventions", stop_at_any_heading=True) == (
        "## Shared conventions (both repos)\n\nBody line.\n")


def test_headings_inside_fenced_code_are_ignored() -> None:
    text = "## A\n```bash\n# a shell comment\n## not a heading\n```\nafter\n~~~~\n### nor this\n~~~~\n## B\n"
    assert extract_section(text, "## A", stop_at_any_heading=True) == (
        "## A\n```bash\n# a shell comment\n## not a heading\n```\nafter\n~~~~\n### nor this\n~~~~\n")


def test_fence_closes_only_on_a_matching_fence() -> None:
    text = "## A\n````\n```\n## still fenced\n````\n## B\n"
    assert extract_section(text, "## A") == "## A\n````\n```\n## still fenced\n````\n"


def test_heading_must_be_at_the_requested_level() -> None:
    with pytest.raises(SectionError, match="found no"):
        extract_section("### Shared conventions\nbody\n", "## Shared conventions")


def test_missing_and_repeated_headings_are_refused() -> None:
    with pytest.raises(SectionError, match="found no"):
        extract_section("# Title\nno section here\n", "## Shared conventions")
    with pytest.raises(SectionError, match="found 2"):
        extract_section("## A\none\n## A again\ntwo\n", "## A")


def test_prefix_must_be_a_heading() -> None:
    with pytest.raises(SectionError, match="not a Markdown heading"):
        extract_section("## A\n", "A")


def test_byte_differences_inside_a_section_are_kept() -> None:
    assert extract_section("## A\nline \n", "## A") != extract_section("## A\nline\n", "## A")
    assert extract_section("## A\r\nline\r\n", "## A").endswith("line\r\n")


# --- this repository ----------------------------------------------------------------------

def test_engine_carries_both_shared_blocks() -> None:
    conventions = _conventions(ROOT)
    assert len(conventions.splitlines()) > 1, "the shared-conventions section has a heading and no body"
    rules = _review_rules(ROOT)
    assert any(line.startswith("* ") for line in rules.splitlines()), (
        "the generic Code Review Rules block has no bullets; the extraction no longer finds it")


# --- against the site ---------------------------------------------------------------------

def test_writing_conventions_match_the_site(site_root: Path) -> None:
    engine = _conventions(ROOT)
    site = _conventions(site_root)
    assert engine == site, (
        "CLAUDE.md shared conventions differ between the repositories; edit both:\n"
        + _diff(engine, site, "CLAUDE.md"))


def test_generic_code_review_rules_match_the_site(site_root: Path) -> None:
    engine = _review_rules(ROOT)
    site = _review_rules(site_root)
    assert engine == site, (
        "AGENTS.md generic Code Review Rules differ between the repositories; edit both:\n"
        + _diff(engine, site, "AGENTS.md"))
