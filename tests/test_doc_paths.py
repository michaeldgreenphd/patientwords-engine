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
the reason, per document. An entry that its document stops naming fails, and so
does an entry that starts to resolve, so the allowlist cannot quietly outlive
its reason. The exception is ``MAY_APPEAR``: runtime outputs that a CI commit or
a documented command puts in the tree (a paid rejudge commits its re-grades to
main; ``render_archive.py fetch --in-place`` writes an untracked, unignored PNG).
Those may start to resolve without failing, because failing would turn the
suite red on a data commit or a local fetch, not on a change to the docs.

The root README.md is out of scope until it is rewritten: it names about
thirty runtime and upstream paths (eval_out/, medlang_out/, apps/...).

The new verify/reference guides in both repositories also check Markdown file
links and explicitly named companion paths. Engine-local guide references always
run; paired checks visibly skip only when the default companion checkout is absent.
An existing companion must contain its guides. Anchor/prose validation stays out of scope.
"""
from __future__ import annotations

import fnmatch
import os
import posixpath
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
    "docs/pilot_runs.md",
    "docs/README.md",
)

# These paired guides additionally use ordinary Markdown links and explicit
# ../patientwords[-engine]/ references. Keep the older operating-doc gate intact.
GUIDES = ("verify.md", "docs/agent_reference.md")

# Runtime outputs may appear after a documented run; unlike stored source paths,
# their absence is expected. Each exception must still be named by its guide.
GUIDE_OUTPUTS: dict[tuple[str, str, str], str] = {
    ("patientwords-engine", "verify.md", "docs/framework/_blob_probe.tmp.json"):
        "temporary file made and cleaned by the Git blob-path regression test",
    ("patientwords-engine", "docs/agent_reference.md", "data/jev/runs/"):
        "live jev-audit output, absent until a live run lands",
    ("patientwords-engine", "docs/agent_reference.md", "pilot/logits/"):
        "pilot logits workflow output, absent until a pilot logits run lands",
}
# This code literal is joined to the selected site Path inside the guide's
# Python example; it must remain relative there. Validate its actual owner.
GUIDE_COMPANION_PATHS = {
    ("patientwords-engine", "verify.md", "data/simulated_scenarios.json"):
        "../patientwords/data/simulated_scenarios.json",
}

_REJUDGE = ("runtime output of the petri-audit lane's `mode: rejudge`; no rejudge output has landed on main "
            "(2026-09-30), so the directory does not exist yet")
_SITE = "a file in the sibling site repository (../patientwords), not in this one"
_PILOT_LOGITS = ("runtime output of the logits-eval lane's `output_root: pilot/logits` (2026-10-04); no pilot "
                 "logits fire has landed, so the directory does not exist yet")
# every name the docs give the pilot logits root, as missing_paths reports them (each run's own folder,
# pilot/logits/<run_id>/<stem>__<model>/, since 2026-10-05)
PILOT_LOGITS_NAMES: tuple[tuple[str, str], ...] = (
    ("AGENTS.md", "pilot/logits/"),
    ("docs/triggers.md", "pilot/logits"),
    ("docs/triggers.md", "pilot/logits/"),
    ("docs/triggers.md", "pilot/logits/*/*__*/"),
    ("docs/triggers.md", "pilot/logits/*/*__*/batch_summary.part_NN.json"),
    ("docs/triggers.md", "pilot/logits/*/**"),
    ("docs/pilot_runs.md", "pilot/logits"),
    ("docs/pilot_runs.md", "pilot/logits/*/*__*/"),
)
_RUN3_TRACES = ("run 3's circuit-trace parts, committed by CI to its fire branch on 2026-10-04 and on main since "
                "PR #84 merged (894d3d7c, 2026-10-05 UTC); this branch's base predates that merge")
_RUN2_RUN_NAMED = ("where docs/triggers.md and docs/pilot_runs.md tell a session to rebuild (trace_pairs.py) or copy "
                   "run 2's pairs file under its run-named name before tracing or measuring it again (2026-10-05); "
                   "no such file has been made")
_RUN2_NEW_TRACE_OUT = ("runtime output: where the parts of a new trace of run 2's run-named pairs file would land; "
                       "run 2 has not been traced again")
# the pilot paths other than pilot/logits the docs name that are missing here, with why
PILOT_OTHER_NAMES: dict[tuple[str, str], str] = {
    ("docs/triggers.md", "pilot/traces/pilot_v3_20261004_trace_pairs/"): _RUN3_TRACES,
    ("docs/pilot_runs.md", "pilot/traces/pilot_v3_20261004_trace_pairs/"): _RUN3_TRACES,
    ("docs/triggers.md", "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json"): _RUN2_RUN_NAMED,
    ("docs/pilot_runs.md", "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json"): _RUN2_RUN_NAMED,
    ("docs/triggers.md", "pilot/traces/pilot_v2_20261002/"): _RUN2_NEW_TRACE_OUT,
}

_JEV = "a live jev-audit run's cost sidecar or report, which its CI commit writes (no live run has fired yet)"
JEV_RUN_NAMES: dict[tuple[str, str], str] = {
    ("AGENTS.md", "data/jev/runs/"): _JEV,
    ("docs/triggers.md", "data/jev/runs/jev_audit_*_1.report.json"): _JEV,
    ("docs/triggers.md", "data/jev/runs/jev_audit_*_1.json"): _JEV,
}

# (document, path as the document writes it, after placeholders become `*`) -> why it does not exist.
ALLOWED_MISSING: dict[tuple[str, str], str] = {
    ("AGENTS.md", "data/petri/rejudge/"): _REJUDGE,
    ("AGENTS.md", "data/urgency_shift.json"): _SITE + " (`scripts/urgency_shift.py --publish` writes it)",
    ("docs/triggers.md", "data/petri/rejudge/*/*/"): _REJUDGE,
    ("docs/triggers.md", "data/petri/secondary/fire_*.json"): "Automatic second-judge status records created only by CI.",
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
    **{name: _PILOT_LOGITS for name in PILOT_LOGITS_NAMES},
    **PILOT_OTHER_NAMES,
    **JEV_RUN_NAMES,
}

# ALLOWED_MISSING keys whose path is a runtime output that may legitimately appear in the tree: the stale check
# below does not fail when one of these starts to resolve. Every other entry must stay missing.
MAY_APPEAR: frozenset[tuple[str, str]] = frozenset({
    ("AGENTS.md", "data/petri/rejudge/"),
    ("docs/triggers.md", "data/petri/rejudge/*/*/"),
    ("docs/triggers.md", "data/petri/secondary/fire_*.json"),
    ("docs/routine_standing_prompt.md", "data/petri/rejudge/*/*/"),
    ("docs/archiving.md", "trace_out/pairs_20260707T215921Z/index_07.png"),
    *PILOT_LOGITS_NAMES,      # a pilot logits fire's CI commit creates them
    *PILOT_OTHER_NAMES,       # a merge of main, a documented copy, or a pilot trace's CI commit creates them
    *JEV_RUN_NAMES,           # a live jev-audit run's CI commit creates them
})

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE = re.compile(r"`([^`]+)`")
_SPLIT = re.compile(r"[\s\"',;()\[\]{}=|]+")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")
_PLACEHOLDER = re.compile(r"<[^<>/\n]*>")
_ROOT_FILE = re.compile(r"^[A-Z][A-Z0-9_]*\.(?:md|cff)$|^(?:pyproject\.toml|verify\.md)$")
_GLOB_CHARS = set("*?")
_MARKDOWN_LINK = re.compile(r"\[[^\]\n]*\]\(([^\s)]+)(?:\s+[^)]*)?\)")
_COMPANIONS = ("../patientwords/", "../patientwords-engine/")


def _listed_paths(root: Path = ROOT, *, required: bool = False) -> list[str]:
    """Tracked files plus untracked, non-ignored ones, relative to root."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:  # not a git checkout
        if required:
            pytest.fail(f"Cannot list required companion checkout {root}: {exc}")
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


def guide_paths(doc: str, text: str, repo: Repo) -> list[str]:
    """Code paths are repo-relative; Markdown links are document-relative.

    Only explicit sibling names cross repositories. Anchors are stripped as in
    the operating-doc check; this is a file-path gate, not a full Markdown parser.
    """
    paths = dict.fromkeys(named_paths(text, repo.top_level))
    for span in _code_spans(text):
        span = _PLACEHOLDER.sub("*", span).replace("\u2026", "*").replace("...", "*")
        for raw in _SPLIT.split(span):
            path = _clean(raw)
            if path.startswith(_COMPANIONS):
                paths.setdefault(path, None)
    for target in _MARKDOWN_LINK.findall(text):
        if target.startswith(("#", "/")) or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
            continue
        path = target.split("#", 1)[0]
        if path:
            paths.setdefault(posixpath.normpath(posixpath.join(posixpath.dirname(doc), path)), None)
    return list(paths)


def unresolved_guide_paths(doc: str, text: str, repo: Repo, companions: dict[str, Repo],
                           aliases: dict[str, str] | None = None) -> list[str]:
    """Resolve explicit sibling references against that checkout, never this one."""
    missing = []
    for path in guide_paths(doc, text, repo):
        target = (aliases or {}).get(path, path)
        sibling = next((prefix for prefix in _COMPANIONS if target.startswith(prefix)), None)
        if sibling is None:
            found = resolves(target, repo)
        else:
            found = sibling in companions and resolves(target[len(sibling):], companions[sibling])
        if not found:
            missing.append(path)
    return missing


def stale_allowlist_entries(doc: str, text: str, repo: Repo, allowed: dict[tuple[str, str], str],
                            may_appear: frozenset[tuple[str, str]]) -> list[str]:
    """The allowlisted paths for `doc` that its text no longer names, or that now resolve and are not in
    `may_appear`."""
    named = set(named_paths(text, repo.top_level))
    return [p for (d, p) in allowed
            if d == doc and (p not in named or ((d, p) not in may_appear and resolves(p, repo)))]


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
    stale = stale_allowlist_entries(doc, text, repo, ALLOWED_MISSING, MAY_APPEAR)
    assert not stale, (
        f"ALLOWED_MISSING entries for {doc} that the document no longer names, or that now exist: {stale}. "
        "Remove them from the allowlist.")


def test_allowlist_names_only_scanned_documents() -> None:
    assert {d for d, _ in ALLOWED_MISSING} <= set(DOCS)
    assert MAY_APPEAR <= set(ALLOWED_MISSING)


def guidance_site_root() -> Path:
    """Use the explicit companion, or visibly skip when the default is absent."""
    override = os.environ.get("PW_SITE_ROOT")
    if override is not None:
        site = Path(override).expanduser()
        if not override or not site.is_dir():
            pytest.fail(f"PW_SITE_ROOT={override!r} is not a directory")
        return site
    site = ROOT.parent / "patientwords"
    if not site.is_dir():
        pytest.skip(f"sibling checkout ../patientwords absent ({site}); set PW_SITE_ROOT to check paired guides")
    return site


@pytest.fixture(scope="module")
def guidance_repos(repo: Repo) -> dict[str, tuple[Path, Repo]]:
    site = guidance_site_root()
    return {"patientwords-engine": (ROOT, repo), "patientwords": (site, make_repo(_listed_paths(site, required=True)))}


@pytest.mark.parametrize("doc", GUIDES)
def test_engine_guidance_local_references_without_companion(doc: str, repo: Repo) -> None:
    """A missing sibling must not hide a broken local setup/reference link."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    local = [p for p in guide_paths(doc, text, repo)
             if not p.startswith(_COMPANIONS) and ("patientwords-engine", doc, p) not in GUIDE_COMPANION_PATHS]
    missing = [p for p in local if not resolves(p, repo) and ("patientwords-engine", doc, p) not in GUIDE_OUTPUTS]
    assert not missing, f"{doc} names missing engine paths: {missing}"


@pytest.mark.parametrize("repository", ("patientwords-engine", "patientwords"))
@pytest.mark.parametrize("doc", GUIDES)
def test_guidance_references_resolve(repository: str, doc: str,
                                    guidance_repos: dict[str, tuple[Path, Repo]]) -> None:
    root, current = guidance_repos[repository]
    text = (root / doc).read_text(encoding="utf-8")
    companions = {f"../{name}/": r for name, (_, r) in guidance_repos.items() if name != repository}
    aliases = {p: target for (name, d, p), target in GUIDE_COMPANION_PATHS.items()
               if (name, d) == (repository, doc)}
    missing = [p for p in unresolved_guide_paths(doc, text, current, companions, aliases)
               if (repository, doc, p) not in GUIDE_OUTPUTS]
    assert not missing, f"{repository}/{doc} names missing paths: {missing}; qualify companion paths explicitly"
    named = guide_paths(doc, text, current)
    stale = [p for (name, d, p) in (*GUIDE_OUTPUTS, *GUIDE_COMPANION_PATHS)
             if (name, d) == (repository, doc) and p not in named]
    assert not stale, f"Remove unused runtime-output exceptions for {repository}/{doc}: {stale}"


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


def test_a_runtime_output_that_lands_does_not_make_its_entry_stale() -> None:
    """A CI commit of a runtime output (a paid rejudge's re-grades) must not turn the suite red, while an entry
    outside MAY_APPEAR that starts to exist, or that its document stops naming, is still reported."""
    allowed = {("d.md", "data/petri/rejudge/*/*/"): "runtime output", ("d.md", "scripts/gone.py"): "removed",
               ("d.md", "docs/unnamed.md"): "no longer named"}
    may_appear = frozenset({("d.md", "data/petri/rejudge/*/*/")})
    text = "`data/petri/rejudge/<judge>/<run>/` and `scripts/gone.py`"
    before = make_repo(list(_FAKE.files))
    assert stale_allowlist_entries("d.md", text, before, allowed, may_appear) == ["docs/unnamed.md"]
    landed = make_repo(list(_FAKE.files) + ["data/petri/rejudge/judge-a/run-1/grades.json", "scripts/gone.py"])
    assert stale_allowlist_entries("d.md", text, landed, allowed, may_appear) == ["scripts/gone.py", "docs/unnamed.md"]
    assert stale_allowlist_entries("d.md", "nothing named", landed, allowed, may_appear) == [
        "data/petri/rejudge/*/*/", "scripts/gone.py", "docs/unnamed.md"]


def test_guidance_links_and_explicit_companion_paths_use_the_correct_repository(tmp_path: Path) -> None:
    """A real guide-shaped fixture accepts both sides, then names a broken target."""
    engine = make_repo(["verify.md", "docs/agent_reference.md", "scripts/check.py"])
    site = make_repo(["verify.md", "docs/agent_reference.md", "data/example.json"])
    guide = tmp_path / "guide.md"
    good = ("[Verification](../verify.md#setup) and [engine](../../patientwords-engine/verify.md). "
            "Read `data/example.json` and `../patientwords-engine/scripts/check.py`. "
            "[External](https://example.invalid/reference) and [this section](#here).")
    guide.write_text(good, encoding="utf-8")
    companions = {"../patientwords-engine/": engine}
    assert unresolved_guide_paths("docs/agent_reference.md", guide.read_text(), site, companions) == []
    # A same-named local target must not conceal a missing companion reference.
    guide.write_text(good.replace("scripts/check.py", "data/example.json"), encoding="utf-8")
    assert unresolved_guide_paths("docs/agent_reference.md", guide.read_text(), site, companions) == [
        "../patientwords-engine/data/example.json"]
    guide.write_text(good.replace("../verify.md#setup", "../missing-guide.md#setup"), encoding="utf-8")
    assert unresolved_guide_paths("docs/agent_reference.md", guide.read_text(), site, companions) == [
        "missing-guide.md"]


def test_guidance_companion_override_is_explicit_and_must_exist(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PW_SITE_ROOT", str(tmp_path))
    assert guidance_site_root() == tmp_path
    for bad in ("", str(tmp_path / "absent")):
        monkeypatch.setenv("PW_SITE_ROOT", bad)
        with pytest.raises(pytest.fail.Exception, match="PW_SITE_ROOT"):
            guidance_site_root()


def test_existing_non_git_companion_fails_instead_of_skipping(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PW_SITE_ROOT", str(tmp_path))
    with pytest.raises(pytest.fail.Exception, match="required companion checkout"):
        _listed_paths(guidance_site_root(), required=True)
