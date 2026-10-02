"""Every recorded pilot run must still finalize under the current pilot scripts. Each run directory (pilot/ for the
first recorded run, each pilot/runs/<run_id>/ for later ones) records the hashes of every pilot/scripts/*.py, and
finalize recomputes the summary, re-derives the plans, re-renders the workflow scripts and compares them with the
files on disk. A pull request that changes a pilot script must recompute and re-finalize each recorded run
(AGENTS.md, Code Review Rules); this test fails when it did not, or when a script change altered a recorded output.

The finalize runs on a copy in a temporary directory, so the committed run is never written. It takes about a minute
per run. It is skipped, with the reason, under an interpreter on the other side of Python 3.12 from the one that
sealed the run: 3.12 changed sum() over floats, so the summary's float sums differ in the last bit across that line
and write_manifest.py refuses there (common.sealed_interpreter_guard).
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "pilot"
SCRIPTS = PILOT / "scripts"

_spec = importlib.util.spec_from_file_location("pilot_common_recorded_runs_test", SCRIPTS / "common.py")
assert _spec is not None and _spec.loader is not None, "pilot/scripts/common.py is missing"
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

# what sits in pilot/ beside the first recorded run and is not part of it
NOT_RUN_FILES = ("scripts", "runs", "prompts_v2", "codebook", "analysis", "__pycache__")


def recorded_runs() -> list[Path]:
    runs = [PILOT] + sorted(p for p in (PILOT / "runs").glob("*") if p.is_dir())
    return [r for r in runs if (r / "manifest.json").exists()]


def test_recorded_runs_are_found():
    assert PILOT in recorded_runs(), "pilot/manifest.json, the first recorded run's manifest, is missing"


@pytest.mark.parametrize("run_dir", recorded_runs(), ids=lambda p: str(p.relative_to(ROOT)))
def test_recorded_run_finalizes_under_current_scripts(run_dir: Path, tmp_path: Path):
    committed = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert committed.get("finalized_utc"), f"{run_dir.relative_to(ROOT)}/manifest.json is not finalized"
    running = platform.python_version()
    if common.float_sum_side(committed["python"]) != common.float_sum_side(running):
        pytest.skip(f"sealed under Python {committed['python']}, running {running}: sum() over floats changed in 3.12, "
                    f"so this run can be re-finalized only on the sealing interpreter's side of 3.12")
    copy = tmp_path / "run"
    shutil.copytree(run_dir, copy, ignore=shutil.ignore_patterns(*NOT_RUN_FILES))
    out = subprocess.run([sys.executable, str(SCRIPTS / "write_manifest.py"), "finalize"],
                         env={**os.environ, "PILOT_DIR": str(copy)}, cwd=str(tmp_path),
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    now = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    for key in ("script_hashes", "workflow_script_hashes", "output_hashes", "prompt_hashes", "design"):
        assert now[key] == committed[key], f"{key} differs from the committed manifest: re-finalize the recorded run"
    # finalize writes only the manifest: the sealed outputs in the copy are the committed ones
    for name in committed["output_hashes"]:
        assert (copy / name).read_bytes() == (run_dir / name).read_bytes(), name
