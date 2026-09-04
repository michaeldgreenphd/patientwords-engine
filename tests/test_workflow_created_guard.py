"""Every push-to-run workflow skips the run that creating a ref fires.

A push that creates a ref carries ``created: true`` in its payload, and on a new
ref every ``paths`` filter matches, so without a guard a branch push fires every
lane whose trigger file exists on the ref (2026-09-04: creating a merge branch
from main fired all eight lanes, two of them paid, with main's live configs).
The guard is a job-level ``if`` on *every* job, not only the entry job, so a
downstream job cannot bypass it with ``always()``. CI-side behaviour cannot be
exercised offline, so this parse-level check is the only test the guard has.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
GUARD = "!github.event.created"


def _push_triggered(doc: dict) -> bool:
    on = doc.get(True, doc.get("on"))  # YAML 1.1 reads a bare `on:` key as boolean True
    return isinstance(on, dict) and "push" in on


def test_workflows_are_discovered():
    assert WORKFLOWS, "no workflow files found; the glob or the layout changed"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_of_every_push_workflow_skips_ref_creation(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not _push_triggered(doc):
        pytest.skip(f"{path.name} has no push trigger")
    for name, job in doc["jobs"].items():
        cond = job.get("if")
        assert cond is not None and GUARD in str(cond), (
            f"{path.name}: job {name!r} has no job-level `if` containing {GUARD}; "
            "a push that creates a ref would run it"
        )
