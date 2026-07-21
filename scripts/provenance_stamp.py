"""Provenance stamp for published data payloads (audit 2026-07-21, E1).

Every generator that writes a published data file attaches a top-level
``_provenance`` block — generator script name, engine commit (with a
``+dirty`` marker when the working tree has uncommitted changes), and a UTC
timestamp — so any published number can be traced to the exact code that
produced it. Frontend pages ignore unknown fields; the block is additive.
No medical vocabulary lives in this file.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone


def engine_sha() -> str | None:
    """Commit of the running checkout: git first, CI env second, else None."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (subprocess.CalledProcessError, OSError):
        env = os.environ.get("GITHUB_SHA", "")
        return env[:12] if env else None


def provenance(generator: str) -> dict:
    """The ``_provenance`` block for one generator run."""
    return {
        "generator": f"scripts/{generator}",
        "engine_sha": engine_sha(),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
