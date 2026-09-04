"""Provenance stamp for published data payloads (audit 2026-07-21, E1).

A generator that calls into this module attaches a top-level ``_provenance``
block — generator script name, engine commit (with a ``+dirty`` marker when the
working tree has uncommitted changes), and a UTC timestamp — so the number it
publishes can be traced to the exact code that produced it. Frontend pages
ignore unknown fields; the block is additive. No medical vocabulary here.

**Coverage is partial, not universal.** As of 2026-08-03 five of the thirty
published payloads carry the block — `convergence.json`, `drift_series.json`,
`jlens_swaps.json`, `model_stats.json`, `tag_mass.json`. The rest predate the
audit that introduced it. Absence of ``_provenance`` therefore means "this
exporter was never wired up", NOT "this file is unstamped by design", and no
consumer may treat the block as a required field.
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
