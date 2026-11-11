"""Record every path a process asks for inside the boundary layout and does not find.

scripts/check_frontend_boundary.py copies this file into a temporary directory as
`sitecustomize.py` and puts that directory on PYTHONPATH for each subprocess it runs in
the temporary engine layout, so the interpreter imports it at start-up, in that process
and in any Python process it starts in turn. It does nothing unless both environment
variables below are set. It changes no result: every call is passed through unchanged.

What is recorded: a path under the layout root that does not exist when the process
opens it (audit event `open`), lists it (`os.listdir`, `os.scandir`) or asks whether it
exists (`os.stat`, `os.lstat`, which `os.path.exists`, `os.path.isfile`, `Path.exists`,
`Path.is_file` and `Path.is_dir` call). One line per path, relative to the root, is
appended to the log. The runner decides which of those are layout defects.

What is not recorded: the import system's own lookups (it calls the C `stat` directly,
so a missing `.pyc` is not noise here), calls made with a directory file descriptor, a
child started with `-I`, `-E` or `-S` (it ignores PYTHONPATH or `sitecustomize`), and
any non-Python child process.
"""
from __future__ import annotations

import os
import sys

ROOT_ENV = "PW_BOUNDARY_LAYOUT_ROOT"
LOG_ENV = "PW_BOUNDARY_LAYOUT_LOG"


def install(root: str, log: str) -> None:
    """Start recording absent paths under `root` into `log` for the rest of this process."""
    roots = {os.path.abspath(root), os.path.realpath(root)}
    real_stat, real_lstat = os.stat, os.lstat
    descriptor = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    seen: set[str] = set()

    def note(path: object) -> None:
        try:
            text = os.fspath(path)  # type: ignore[arg-type]
        except TypeError:
            return  # an open file descriptor, not a path
        if isinstance(text, bytes):
            text = os.fsdecode(text)
        full = os.path.abspath(text)
        if full in seen:
            return
        seen.add(full)
        for base in roots:
            if full.startswith(base + os.sep):
                try:
                    real_lstat(full)
                except OSError:
                    os.write(descriptor, (os.path.relpath(full, base) + "\n").encode("utf-8", "surrogateescape"))
                return

    def stat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("dir_fd") is None:
            note(path)
        return real_stat(path, *args, **kwargs)

    def lstat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("dir_fd") is None:
            note(path)
        return real_lstat(path, *args, **kwargs)

    def hook(event: str, args: tuple) -> None:
        if event in ("open", "os.listdir", "os.scandir") and args and args[0] is not None:
            note(args[0])

    os.stat, os.lstat = stat, lstat
    sys.addaudithook(hook)


if os.environ.get(ROOT_ENV) and os.environ.get(LOG_ENV):
    install(os.environ[ROOT_ENV], os.environ[LOG_ENV])
