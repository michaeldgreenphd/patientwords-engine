"""Tracked files a git checkout keeps off disk (sparse checkout, skip-worktree).

The cloud containers clone the site with
``git sparse-checkout set --no-cone '/*' '!/modes/'``
(docs/fresh_session_bootstrap.md), so a tool that walks the working tree sees
none of the site's renders. The render prune in export_frontend_simulated.py
then prunes nothing, and seal_check.py reads nothing under modes/, and both
used to report success (2026-09-23 review of the seal PR). Each calls
``hidden_tracked`` first and refuses when it returns anything, naming the fix:
``git -C <site> sparse-checkout disable``.

A file git tracks but keeps off disk carries the skip-worktree bit (tag ``S``
in ``git ls-files -t``); a sparse checkout sets that bit on every file outside
its patterns. A file deleted from disk without the bit (a render the prune has
just removed, not yet committed) is not hidden: git shows it as a deletion, and
the tools must not refuse a re-run over it.
"""

import os
import subprocess
from pathlib import Path


def hidden_tracked(root: str | Path, pathspec: str = ".") -> list[str]:
    """Paths, relative to the directory ``root``, of tracked files matching
    ``pathspec`` that carry the skip-worktree bit. The pathspec need not exist
    on disk: a sparse checkout leaves an excluded directory absent.

    Returns [] when ``root`` is not an existing directory inside a git work
    tree, or git is not installed: only git makes a sparse checkout. Raises
    RuntimeError when git runs but cannot answer (a timeout, a refused
    directory), so a caller refuses rather than reading an unknown checkout as
    complete."""
    cwd = Path(root)
    if not cwd.is_dir():
        return []
    env = {**os.environ, "LC_ALL": "C"}          # git's "not a git repository" untranslated
    try:
        proc = subprocess.run(["git", "-C", str(cwd), "ls-files", "-t", "-z", "--", pathspec],
                              capture_output=True, check=False, timeout=120, env=env)
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git ls-files timed out under {cwd}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        if "not a git repository" in err:
            return []
        raise RuntimeError(f"git ls-files failed under {cwd}: "
                           f"{err.splitlines()[-1] if err else f'exit {proc.returncode}'}")
    entries = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return sorted(e[2:] for e in entries if e.startswith("S "))
