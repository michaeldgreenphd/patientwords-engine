"""Derive, build and check the temporary engine layout of the synthetic boundary check.

Standard library only, so the engine's ordinary test environment can import it.

The layout is not a hand-kept list of files. It is what site CI's sparse checkout of the
engine holds, read from the site's own workflow file on every run:

- the directories named in the `sparse-checkout` block of the step that checks out
  `patientwords-engine` (today `scripts`, `data`, `ops`, `docs`), whole;
- the files at the engine's root, because actions/checkout uses git's cone mode unless
  `sparse-checkout-cone-mode: false` is set, and cone mode always checks out root files.
  This is read from the documentation of actions/checkout and git; it was not observed
  on a hosted runner from here.

Of those paths it copies the files a commit of the working tree would hold: tracked, or
untracked and not ignored, and present on disk. An ignored file (a cache, a local
result) is not in site CI and is not copied.

Site CI runs no pytest, so the selected test modules are added as an explicit
test-support list. That list, and nothing else, is maintained by hand, and the run
checks it: `absent_inputs` reads the log written by layout_probe.py and reports every
path a layout process asked for, did not find, and that the engine checkout does hold.
The runner fails on such a path by name before it reads the stage's own exit code.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

WORKFLOW = ".github/workflows/site_checks.yml"
ENGINE_REPOSITORY = "patientwords-engine"


class LayoutError(Exception):
    """The temporary engine layout cannot be derived, or lacks a file a stage asked for."""


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def sparse_checkout(workflow: Path) -> tuple[list[str], bool]:
    """The engine directories site CI checks out, and whether root files come with them.

    Reads the one `sparse-checkout: |` block of the workflow. Refuses, naming the file,
    when the file is unreadable, holds no such block or more than one, when the block's
    step does not check out the engine, or when an entry is not a plain directory name.
    """
    try:
        lines = workflow.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LayoutError(f"cannot read the site workflow {workflow}: {exc}. The layout is derived from its "
                          "sparse-checkout block.") from None
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r"\s*sparse-checkout:\s*\|[-+]?\s*", line)]
    if len(starts) != 1:
        raise LayoutError(f"{workflow} holds {len(starts)} `sparse-checkout: |` blocks; exactly one is expected "
                          "(the engine checkout). The layout cannot be derived.")
    start = starts[0]
    key_indent = _indent(lines[start])
    entries: list[str] = []
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or _indent(lines[end]) > key_indent):
        if lines[end].strip():
            entries.append(lines[end].strip())
        end += 1
    first = start
    while first > 0 and not (lines[first].lstrip().startswith("- ") and _indent(lines[first]) < key_indent):
        first -= 1
    step = "\n".join(lines[first:end])
    if not re.search(rf"^\s*repository:\s*\S*{re.escape(ENGINE_REPOSITORY)}\s*$", step, re.MULTILINE):
        raise LayoutError(f"{workflow}: the step with the sparse-checkout block does not check out "
                          f"{ENGINE_REPOSITORY}. The layout cannot be derived.")
    bad = [entry for entry in entries if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*",
                                                          entry)]
    if bad or not entries:
        raise LayoutError(f"{workflow}: sparse-checkout entries must be plain directory names, got {bad or entries}. "
                          "Patterns are not supported; the layout cannot be derived.")
    cone = not re.search(r"^\s*sparse-checkout-cone-mode:\s*['\"]?false['\"]?\s*$", step, re.MULTILINE)
    return entries, cone


def _git_files(root: Path, *pathspecs: str) -> list[str]:
    command = ["git", "-C", str(root), "--literal-pathspecs", "ls-files", "-z", "--cached", "--others",
               "--exclude-standard"]
    if pathspecs:
        command += ["--", *pathspecs]
    try:
        raw = subprocess.check_output(command)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LayoutError(f"cannot list the engine checkout's files with git at {root}: {exc}") from None
    return [name for name in raw.decode("utf-8", "surrogateescape").split("\0") if name]


def committable_files(root: Path) -> list[str]:
    """Files a commit of this working tree would hold: tracked, or untracked and not ignored, and on disk."""
    return [name for name in _git_files(root) if (root / name).is_file()]


def select(files: list[str], directories: list[str], root_files: bool) -> list[str]:
    """The subset of `files` a sparse checkout of `directories` holds."""
    prefixes = tuple(directory.rstrip("/") + "/" for directory in directories)
    return [name for name in files if name.startswith(prefixes) or (root_files and "/" not in name)]


def build(root: Path, target: Path, files: list[str], test_support: list[str]) -> dict[str, int]:
    """Copy `files` and `test_support` from the checkout into `target`. Returns counts for the receipt.

    A test-support path the checkout does not hold is refused by name: a stale entry in
    the hand-kept list must not surface later as a collection error.
    """
    missing = [name for name in test_support if not (root / name).is_file()]
    if missing:
        raise LayoutError("test-support files listed in scripts/check_frontend_boundary.py are not in the engine "
                          f"checkout: {missing}")
    copied = size = 0
    for name in dict.fromkeys([*files, *test_support]):
        source = root / name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied += 1
        size += source.stat().st_size
    return {"files": copied, "bytes": size}


def tree_bytes(root: Path, skip: tuple[str, ...] = ()) -> int:
    """Bytes of the regular files under `root`, without the top-level names in `skip`."""
    total = 0
    for directory, names, files in os.walk(root):
        if Path(directory) == root:
            names[:] = [name for name in names if name not in skip]
        for name in files:
            try:
                total += os.lstat(os.path.join(directory, name)).st_size
            except OSError:
                pass
    return total


def require_free_space(where: Path, needed: int, what: str) -> int:
    """Refuse before copying when the temporary directory's file system cannot hold the copy twice over."""
    free = shutil.disk_usage(where).free
    if free < 2 * needed:
        raise LayoutError(f"{where} has {free // 2**20} MiB free; {what} needs {needed // 2**20} MiB and the run "
                          "keeps as much again in reserve. Free space or set TMPDIR to a larger file system.")
    return free


# Chromium puts a Unix socket at TMPDIR/org.chromium.Chromium.XXXXXX/SingletonSocket.
CHROMIUM_SOCKET_SUFFIX = "/org.chromium.Chromium.XXXXXX/SingletonSocket"
# A Unix socket address holds 108 bytes on Linux including the terminator (104 on macOS).
SOCKET_PATH_LIMIT = 103


def browser_tmpdir(tempdir: str) -> str | None:
    """A short TMPDIR for the browser process when the run's own is too long for it, else None.

    Chromium aborts at launch ("Socket path too long") when its singleton socket path exceeds the
    socket address limit. The run's large copies still go to the caller's TMPDIR; only the browser
    process is given /tmp, where it keeps that socket directory and removes it on exit.
    """
    if len(os.fsencode(tempdir.rstrip("/") + CHROMIUM_SOCKET_SUFFIX)) <= SOCKET_PATH_LIMIT:
        return None
    return "/tmp"


def absent_inputs(root: Path, log: Path) -> list[str]:
    """Paths a layout process asked for and did not find that the engine checkout holds.

    `log` is layout_probe.py's output: paths relative to the layout root that did not
    exist when asked for. Most are harmless: a path no checkout has (an optional file,
    a config file pytest looks for) or an ignored cache. A path is reported only when
    the real checkout holds it as a committable file, or as a directory with one inside.
    """
    try:
        asked = sorted(set(log.read_text(encoding="utf-8", errors="surrogateescape").splitlines()))
    except FileNotFoundError:
        return []
    on_disk = [name for name in asked if name and not name.startswith("..") and os.path.lexists(root / name)]
    if not on_disk:
        return []
    held = _git_files(root, *on_disk)
    return [name for name in on_disk if any(item == name or item.startswith(name.rstrip("/") + "/")
                                            for item in held)]
