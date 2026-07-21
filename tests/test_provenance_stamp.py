"""Provenance stamp helper (scripts/provenance_stamp.py) — offline."""

import importlib.util
import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "provenance_stamp", _ROOT / "scripts" / "provenance_stamp.py")
ps = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ps)


def test_provenance_block_shape():
    block = ps.provenance("paired_stats_rigor.py")
    assert block["generator"] == "scripts/paired_stats_rigor.py"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", block["generated_utc"])
    assert set(block) == {"generator", "engine_sha", "generated_utc"}


def test_engine_sha_matches_git_in_a_repo():
    sha = ps.engine_sha()
    head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert sha is not None and sha.startswith(head)


def test_engine_sha_env_fallback_outside_a_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "abcdef0123456789")
    assert ps.engine_sha() == "abcdef012345"
    monkeypatch.delenv("GITHUB_SHA")
    assert ps.engine_sha() is None
