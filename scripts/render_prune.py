"""Prune site renders that no export lists (owner ruling 2, 2026-09-23).

export_frontend_simulated.py copies interactive renders into the site's
modes/simulated/ tree and, until 2026-09-23, never removed one. A render stayed
served after its scenario left the payload: modes/simulated/
pairs_20260710T163230Z/index_44.html, a render of a Tier B holdout row, was
live from 2026-07-12 until site PR michaeldgreenphd/patientwords#8, although
the payload had withheld the row since 2026-07-14.

The prune set is narrow by construction:

- only files the exporter itself writes: ``modes/simulated/pairs_<STAMP>/
  index_NN.{html,png}`` and ``modes/simulated/pairs_<STAMP>__<MODEL>/
  index_NN.html`` (RENDER_RE). preview.html/.png, the hand-placed
  featured_sim85/, dialects_*/, urgency_downgrades_*/ directories, and every
  other modes/ subtree are never candidates;
- minus every render the current export lists in its payload;
- minus every render any other site file names (a page, or a payload another
  exporter writes, such as data/jlens_insights.json or
  data/advice_scenarios.json). The payload being replaced is not consulted:
  the export's own listing supersedes it.

The candidates come from the working tree, so a site checkout that keeps
tracked renders off disk (the cloud containers' sparse clone excludes modes/)
would prune nothing and say so as if it were done. ``hidden_renders`` finds
those files (sparse_guard.py) and the exporter refuses before writing anything.

No medical vocabulary lives here.
"""

import os
import re
from pathlib import Path

try:
    from scripts.sparse_guard import hidden_tracked
except ImportError:  # loaded by path (tests) or run from scripts/
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sparse_guard import hidden_tracked

SIM_DIR = "modes/simulated"
_RENDER = r"modes/simulated/pairs_\d{8}T\d{6}Z(?:__[A-Za-z0-9.\-]+)?/index_\d{2,}\.(?:html|png)"
RENDER_RE = re.compile(rf"^{_RENDER}$")
REFERENCE_RE = re.compile(_RENDER)
REFERENCE_SUFFIXES = {".html", ".htm", ".js", ".mjs", ".json", ".jsonl", ".css", ".md",
                      ".csv", ".txt", ".xml", ".svg", ".yml", ".yaml"}


def exporter_renders(frontend: Path) -> list[str]:
    """Site-relative paths under modes/simulated/ that match the exporter's own naming."""
    root = Path(frontend) / SIM_DIR
    if not root.is_dir():
        return []
    site_root = Path(frontend).resolve()
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        if not p.resolve().is_relative_to(site_root / SIM_DIR):
            continue
        rel = p.relative_to(frontend).as_posix()
        if RENDER_RE.match(rel):
            out.append(rel)
    return out


def hidden_renders(frontend: Path) -> list[str]:
    """Site-relative exporter-named renders that the site's git checkout tracks
    but keeps off disk (sparse checkout or skip-worktree). Non-empty means the
    prune cannot see them; the exporter refuses. Raises RuntimeError when git
    cannot answer."""
    return [rel for rel in hidden_tracked(frontend, SIM_DIR) if RENDER_RE.match(rel)]


def referenced_renders(frontend: Path, ignore: set[str] | frozenset[str] = frozenset()) -> set[str]:
    """Render paths named by any text file of the site other than the renders
    themselves, .git, and the site-relative paths in ``ignore``."""
    frontend = Path(frontend)
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(frontend):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(frontend).as_posix()
            if rel in ignore or RENDER_RE.match(rel) or p.suffix.lower() not in REFERENCE_SUFFIXES:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "modes/simulated/" in text:
                found.update(REFERENCE_RE.findall(text))
    return found


def prune_candidates(frontend: Path, listed: set[str],
                     ignore: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Exporter-named renders on the site that neither the export nor any other site file lists."""
    keep = set(listed) | referenced_renders(frontend, ignore)
    return [rel for rel in exporter_renders(frontend) if rel not in keep]


def prune(frontend: Path, candidates: list[str], dry_run: bool) -> int:
    """Delete the candidates (nothing when dry_run) and any render directory
    the deletions leave empty. Returns the number of files removed or, in a dry
    run, that would be."""
    frontend = Path(frontend)
    if dry_run:
        return len(candidates)
    emptied: set[Path] = set()
    for rel in candidates:
        if not RENDER_RE.match(rel):          # defence in depth: never outside the pattern
            raise ValueError(f"refusing to prune a non-render path: {rel}")
        p = frontend / rel
        p.unlink(missing_ok=True)
        emptied.add(p.parent)
    for d in sorted(emptied):
        try:
            d.rmdir()                         # only succeeds when empty
        except OSError:
            pass
    return len(candidates)
