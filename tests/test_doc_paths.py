"""Every repository path the operating docs name must exist.

The weekly doc-accuracy sweep that used to re-check these references ended with
the 2026-08-29 maintenance rewrite (the last report is
docs/audits/doc_accuracy_20260824.md). This test replaces the part of it that a
machine can do: it reads the documents every session and every reviewer works
from (and the docs/ index), pulls out each path they name relative to the
repository root, and fails when one does not exist.

What counts as a named path (the method, so a reader can reproduce a failure):

* Candidates come from inline code spans (single backticks) and from fenced
  code blocks. Prose outside backticks is not read: it names paths only by
  accident, and the docs' own convention is to backtick every path.
* Each candidate is split on whitespace, quotes, commas and brackets, so a
  command such as ``python scripts/archive_run.py --out-dir dist`` yields its
  path arguments.
* A token is a repository path when its first segment is a top-level entry of
  this repository (``docs``, ``scripts``, ``.github``, ...), or when it is a
  root-level file name such as ``AGENTS.md``. Everything else is skipped:
  model ids (``anthropic/<model>``), branch names (``claude/...``), the sibling
  site (``../patientwords``) and its own paths (``modes/...``), URLs, absolute
  paths. A site path that happens to start with a shared top-level name
  (``data/...``) is resolved here like any other and, when it is the site's,
  sits in the allowlist below with that reason.
* A trailing ``:line`` or ``:start-end``, a pytest ``::node`` id, a ``#anchor``
  and trailing punctuation are removed.
* A path resolves when git lists it (tracked, or untracked and not ignored, so
  a new file counts before its first commit) or when it is a directory holding
  such a file. A glob (``*``), an ellipsis or a placeholder (``<batch>``,
  ``NN``) resolves when at least one listed path matches it.

Known gap: a path whose first segment is misspelt (``script/x.py``) or names a
top-level directory that no longer exists is skipped, not reported, because it
cannot be told apart from a model id or a branch name.

Paths that are named but do not exist on purpose (runtime outputs, other
repositories, files removed by design) are listed in ``ALLOWED_MISSING`` with
the reason, per document. An entry that starts to resolve, or that its document
stops naming, fails too, so the allowlist cannot quietly outlive its reason.

The root README.md is out of scope until it is rewritten: it names about
thirty runtime and upstream paths (eval_out/, medlang_out/, apps/...).
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The documents every session and every Codex review works from, plus the docs/
# index, whose do-not-move list is only useful while every path in it is real.
DOCS: tuple[str, ...] = (
    "AGENTS.md",
    "docs/operators_handbook.md",
    "docs/triggers.md",
    "docs/routine_standing_prompt.md",
    "docs/fresh_session_bootstrap.md",
    "docs/archiving.md",
    "docs/README.md",
)

_REJUDGE = ("runtime output of the petri-audit lane's `mode: rejudge`; no rejudge output has landed on main "
            "(2026-09-30), so the directory does not exist yet")
_SITE = "a file in the sibling site repository (../patientwords), not in this one"

# (document, path as the document writes it, after placeholders become `*`) -> why it does not exist.
ALLOWED_MISSING: dict[tuple[str, str], str] = {
    ("AGENTS.md", "data/petri/rejudge/"): _REJUDGE,
    ("AGENTS.md", "data/urgency_shift.json"): _SITE + " (`scripts/urgency_shift.py --publish` writes it)",
    ("docs/triggers.md", "data/petri/rejudge/*/*/"): _REJUDGE,
    ("docs/routine_standing_prompt.md", "data/petri/rejudge/*/*/"): _REJUDGE,
    ("docs/archiving.md", "data/simulated_scenarios.json"): _SITE,
    ("docs/archiving.md", "render_archives/renders-20260707.manifest.json"):
        "the worked example's tag, which the doc says is an example; the real manifest is "
        "render_archives/renders-20260707-fullrun.manifest.json",
    ("docs/archiving.md", "trace_out/pairs_20260707T215921Z/index_07.png"):
        "PNG renders left git on 2026-09-08; the line is the command that fetches this one back from its "
        "Release (renders-20260908-p1)",
    ("docs/README.md", "data/provenance.json"): _SITE,
    ("docs/README.md", "data/jlens_insights.json"): _SITE,
    ("docs/README.md", ".github/workflows/build.yml"):
        "the traces site build, in michaeldgreenphd/patientwords-traces, which the index points to",
}

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE = re.compile(r"`([^`]+)`")
_SPLIT = re.compile(r"[\s\"',;()\[\]{}=|]+")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")
_PLACEHOLDER = re.compile(r"<[^<>/\n]*>")
_ROOT_FILE = re.compile(r"^[A-Z][A-Z0-9_]*\.(?:md|cff)$|^pyproject\.toml$")
_GLOB_CHARS = set("*?")


def _listed_paths() -> list[str]:
    """Tracked files plus untracked, non-ignored ones, relative to ROOT."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:  # not a git checkout
        pytest.skip(f"git ls-files unavailable, cannot resolve doc paths: {exc}")
    return sorted({p for p in out.decode("utf-8").split("\0") if p})


def _directories(files: list[str]) -> set[str]:
    dirs: set[str] = set()
    for f in files:
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return dirs


def _code_spans(text: str) -> list[str]:
    """Inline code spans and the lines of fenced code blocks, in order.

    An inline span may wrap onto the next line of its paragraph, as Markdown
    allows, so spans are matched per paragraph (lines up to a blank line)."""
    spans: list[str] = []
    fenced = False
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            spans.extend(s.replace("\n", " ") for s in _INLINE.findall("\n".join(paragraph)))
            paragraph.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            flush()
            fenced = not fenced
            continue
        if fenced:
            spans.append(line)
        elif line.strip():
            paragraph.append(line)
        else:
            flush()
    flush()
    return spans


def _clean(token: str) -> str:
    token = token.strip().rstrip(".:;,)")
    token = token.lstrip("(")
    token = token.split("::", 1)[0]  # a pytest node id names its file
    token = _LINE_SUFFIX.sub("", token)
    if "#" in token:  # an anchor, never part of a repository path here
        token = token.split("#", 1)[0]
    return token


def named_paths(text: str, top_level: set[str]) -> list[str]:
    """Every repository-relative path the text names, in first-seen order."""
    seen: dict[str, None] = {}
    for span in _code_spans(text):
        # A placeholder may hold spaces (`<judge slug>`); make it one wildcard before splitting.
        span = _PLACEHOLDER.sub("*", span).replace("\u2026", "*").replace("...", "*")
        for raw in _SPLIT.split(span):
            token = _clean(raw)
            if not token or token.startswith(("/", "../", "~", "$", "-", "http:", "https:")):
                continue
            if token.startswith("./"):
                token = token[2:]
            if "/" in token:
                first = token.split("/", 1)[0]
                if first not in top_level:
                    continue
            elif not _ROOT_FILE.match(token):
                continue
            seen.setdefault(token, None)
    return list(seen)


def _pattern(path: str) -> str | None:
    """A glob for a path that carries a wildcard or placeholder, else None."""
    pat = _PLACEHOLDER.sub("*", path)
    pat = re.sub(r"(?<![A-Za-z])NN(?![A-Za-z])", "*", pat)
    if pat != path or _GLOB_CHARS & set(path):
        return pat
    return None


class Repo(NamedTuple):
    """The paths git lists for this checkout, with every directory that holds one."""
    files: list[str]
    fileset: set[str]
    dirs: set[str]
    top_level: set[str]


def make_repo(files: list[str]) -> Repo:
    return Repo(files, set(files), _directories(files), {f.split("/", 1)[0] for f in files})


def resolves(path: str, repo: Repo) -> bool:
    bare = path.rstrip("/")
    pat = _pattern(bare)
    if pat is None:
        return bare in repo.fileset or bare in repo.dirs
    return any(fnmatch.fnmatchcase(f, pat) for f in repo.files) or any(fnmatch.fnmatchcase(d, pat) for d in repo.dirs)


def missing_paths(text: str, repo: Repo) -> list[str]:
    """The paths `text` names that `repo` does not hold, in first-seen order."""
    return [p for p in named_paths(text, repo.top_level) if not resolves(p, repo)]


@pytest.fixture(scope="module")
def repo() -> Repo:
    return make_repo(_listed_paths())


@pytest.mark.parametrize("doc", DOCS)
def test_every_named_path_exists(doc: str, repo: Repo) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    missing = [p for p in missing_paths(text, repo) if (doc, p) not in ALLOWED_MISSING]
    assert not missing, (
        f"{doc} names repository paths that do not exist: {missing}. Fix the reference, or, if the path is a "
        "runtime output or lives in another repository, add it to ALLOWED_MISSING with the reason.")


@pytest.mark.parametrize("doc", DOCS)
def test_allowlist_entries_are_still_needed(doc: str, repo: Repo) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    named = set(named_paths(text, repo.top_level))
    stale = [p for (d, p) in ALLOWED_MISSING if d == doc and (p not in named or resolves(p, repo))]
    assert not stale, (
        f"ALLOWED_MISSING entries for {doc} that the document no longer names, or that now exist: {stale}. "
        "Remove them from the allowlist.")


def test_allowlist_names_only_scanned_documents() -> None:
    assert {d for d, _ in ALLOWED_MISSING} <= set(DOCS)


# ---- the extractor itself, on synthetic text, so a failure above can be trusted

_FAKE = make_repo([
    "AGENTS.md", "docs/archiving.md", "docs/archive/HANDOFF_20260709.md", "scripts/archive_run.py",
    "trace_out/pairs_1/batch_summary.part_01.json", "data/simulated/pairs_1.report.json", "tests/test_x.py",
])


def test_named_paths_reads_inline_spans_fenced_blocks_and_wrapped_spans() -> None:
    text = ("See `docs/archiving.md:28-56` and `AGENTS.md`, then run\n\n```bash\n"
            "python scripts/archive_run.py --runs trace_out/pairs_1 --out-dir dist\n```\n\n"
            "A span that wraps: `trace_out/*/batch_summary.part_NN.json\nplus more`, a node id "
            "`tests/test_x.py::test_y` and an anchor `docs/archiving.md#bundle`.\n")
    assert named_paths(text, _FAKE.top_level) == [
        "docs/archiving.md", "AGENTS.md", "scripts/archive_run.py", "trace_out/pairs_1",
        "trace_out/*/batch_summary.part_NN.json", "tests/test_x.py"]
    assert missing_paths(text, _FAKE) == []


def test_named_paths_skips_what_is_not_a_path_in_this_repository() -> None:
    text = ("`anthropic/claude-haiku-4-5` `claude/some-branch` `../patientwords/data/x.json` "
            "`modes/simulated/` `https://github.com/a/b` `/home/user/x` `batch_summary.part_NN.json` "
            "`--trigger <t>` `python -m pytest -q`")
    assert named_paths(text, _FAKE.top_level) == []


def test_placeholders_and_globs_resolve_when_something_matches() -> None:
    text = ("`data/simulated/<batch>.report.json` `trace_out/<pairs-stem>/` `trace_out/…` "
            "`data/petri/rejudge/<judge slug>/<run>/`")
    assert missing_paths(text, _FAKE) == ["data/petri/rejudge/*/*/"]


def test_a_moved_file_is_reported_at_its_old_path() -> None:
    """The case this test exists for: a doc still names a file after it moved."""
    text = "Read `HANDOFF.md` and `docs/HANDOFF_20260804.md`, not `docs/archive/HANDOFF_20260709.md`."
    assert missing_paths(text, _FAKE) == ["HANDOFF.md", "docs/HANDOFF_20260804.md"]
