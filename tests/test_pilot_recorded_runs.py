"""Every recorded pilot run must still finalize under the current pilot scripts. Each run directory (pilot/ for the
first recorded run, each pilot/runs/<run_id>/ for later ones) records the hashes of every pilot/scripts/*.py, and
finalize recomputes the summary, re-derives the plans, re-renders the workflow scripts and compares them with the
files on disk. A pull request that changes a pilot script must recompute and re-finalize each recorded run
(AGENTS.md, Code Review Rules); this test fails when it did not, or when a script change altered a recorded output.

Each run is checked in two steps. First every hash the run records is compared with the file it names, without
running any pilot code: the script hashes in manifest.json and summary.json against pilot/scripts/*.py, the workflow
scripts and copied journals against the manifest and its run records, every output hash, the seed, design, model-facts
and protocol hashes, the prompt templates and each planned prompt, and summary.json's input hashes and summary.md
hash. None of these depends on the interpreter, so a stale script or output fails this test on every Python (Codex
review of PR #69). Then the finalize runs on a copy in a temporary directory, so the committed run is never written;
it takes about a minute per run. Only this second step is skipped, with the reason, under an interpreter on the other
side of Python 3.12 from the one that sealed the run: 3.12 changed sum() over floats, so the summary's float sums
differ in the last bit across that line and write_manifest.py refuses there (common.sealed_interpreter_guard).
"""
from __future__ import annotations

import hashlib
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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def recorded_hash_problems(run_dir: Path, scripts: Path = SCRIPTS) -> list[str]:
    """Every recorded hash of a finalized run that no longer describes the file it names, compared with hashlib and
    json alone (no pilot code runs, nothing depends on the interpreter). Empty when every record holds."""
    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    s = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    problems: list[str] = []

    def file_matches(name: str, recorded: object, label: str) -> None:
        path = run_dir / name
        if not path.exists():
            problems.append(f"{label}: {name} is missing")
        elif _sha(path) != recorded:
            problems.append(f"{label}: {name} is not the file recorded")

    now = {p.name: _sha(p) for p in sorted(scripts.glob("*.py"))}
    for label, rec in (("manifest.json script_hashes", m.get("script_hashes") or {}),
                       ("summary.json script_hashes", s.get("script_hashes") or {})):
        changed = sorted(n for n in set(rec) | set(now) if rec.get(n) != now.get(n))
        if changed:
            problems.append(f"{label} do not match pilot/scripts for {changed}: recompute and re-finalize the run")
    workflows = {p.name: _sha(p) for p in sorted((run_dir / "workflows").glob("*.js"))}
    if m.get("workflow_script_hashes") != workflows:
        problems.append("manifest.json workflow_script_hashes do not match workflows/*.js")
    for stage in ("generation", "checker"):
        rec = (m.get("runs") or {}).get(stage) or {}
        file_matches(f"workflows/{stage}.workflow.js", rec.get("workflow_script_sha256"), f"runs.{stage}")
        file_matches(f"workflows/{stage}.journal.jsonl", rec.get("journal_sha256"), f"runs.{stage}")
    if not m.get("output_hashes"):
        problems.append("manifest.json records no output_hashes")
    for name, h in sorted((m.get("output_hashes") or {}).items()):
        file_matches(name, h, "output_hashes")
    for key, name in (("seeds_json_sha256", "seeds.json"), ("design_json_sha256", "design.json"),
                      ("manifest_model_sha256", "manifest_model.json"), ("protocol_sha256_now", "PROTOCOL.md")):
        file_matches(name, m.get(key), key)
    ph = m.get("prompt_hashes") or {}
    file_matches("prompts/generation_prompt.txt", ph.get("generation_prompt_template"), "prompt_hashes")
    file_matches("prompts/checker_prompt.txt", ph.get("checker_prompt_template"), "prompt_hashes")
    calls = json.loads((run_dir / "calls.json").read_text(encoding="utf-8"))["calls"]
    planned = {c["id"]: {"prompt_sha256": _sha_text(c["prompt"]), "exemplar_ids": c["exemplar_ids"]} for c in calls}
    if ph.get("generation_calls") != planned:
        problems.append("prompt_hashes.generation_calls is not calls.json's prompts, hashed again, and exemplar ids")
    batches = json.loads((run_dir / "checker_batches.json").read_text(encoding="utf-8"))["batches"]
    if ph.get("checker_batches") != {b["batch_id"]: _sha_text(b["prompt"]) for b in batches}:
        problems.append("prompt_hashes.checker_batches is not checker_batches.json's prompts, hashed again")
    if not s.get("input_hashes"):
        problems.append("summary.json records no input_hashes")
    for name, h in sorted((s.get("input_hashes") or {}).items()):
        file_matches(name, h, "summary.json input_hashes")
    file_matches("summary.md", s.get("summary_md_sha256"), "summary.json summary_md_sha256")
    return problems


def check_recorded_run(run_dir: Path, tmp_path: Path, scripts: Path = SCRIPTS, running: str | None = None) -> None:
    """The recorded hashes first, on every interpreter; then, on the sealing interpreter's side of 3.12 only, a
    finalize of a copy under the current scripts, which must reproduce the committed manifest's records."""
    committed = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert committed.get("finalized_utc"), f"{run_dir.relative_to(ROOT)}/manifest.json is not finalized"
    problems = recorded_hash_problems(run_dir, scripts)
    assert not problems, (f"{run_dir.relative_to(ROOT)}: recorded hashes do not describe the files:\n  "
                          + "\n  ".join(problems))
    running = running or platform.python_version()
    if common.float_sum_side(committed["python"]) != common.float_sum_side(running):
        pytest.skip(f"sealed under Python {committed['python']}, running {running}: every recorded hash matches its "
                    f"file, but sum() over floats changed in 3.12, so this run can be re-finalized only on the sealing "
                    f"interpreter's side of 3.12")
    copy = tmp_path / "run"
    shutil.copytree(run_dir, copy, ignore=shutil.ignore_patterns(*NOT_RUN_FILES))
    out = subprocess.run([sys.executable, str(scripts / "write_manifest.py"), "finalize"],
                         env={**os.environ, "PILOT_DIR": str(copy)}, cwd=str(tmp_path),
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    now = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    for key in ("script_hashes", "workflow_script_hashes", "output_hashes", "prompt_hashes", "design"):
        assert now[key] == committed[key], f"{key} differs from the committed manifest: re-finalize the recorded run"
    # finalize writes only the manifest: the sealed outputs in the copy are the committed ones
    for name in committed["output_hashes"]:
        assert (copy / name).read_bytes() == (run_dir / name).read_bytes(), name


def test_recorded_runs_are_found():
    assert PILOT in recorded_runs(), "pilot/manifest.json, the first recorded run's manifest, is missing"


@pytest.mark.parametrize("run_dir", recorded_runs(), ids=lambda p: str(p.relative_to(ROOT)))
def test_recorded_run_finalizes_under_current_scripts(run_dir: Path, tmp_path: Path):
    check_recorded_run(run_dir, tmp_path)


def test_a_stale_script_fails_before_the_interpreter_skip(tmp_path: Path):
    """A pilot script edited without re-finalizing the recorded runs fails on every interpreter: with a drifted copy
    of the scripts and an interpreter on the other side of 3.12 from the sealing one, the check fails on the script
    hashes instead of skipping; with the scripts as committed, the same interpreter reaches the skip.

    pytest.skip raises Skipped, a BaseException that pytest.raises(AssertionError) lets through, so a check that
    reached the skip before comparing the hashes would report this test as skipped and leave the suite green; that
    is what this test did, before this guard, with the hash comparison removed or the skip moved back ahead of it.
    Reaching the skip with the drifted scripts is therefore turned into a failure here."""
    sealed = json.loads((PILOT / "manifest.json").read_text(encoding="utf-8"))["python"]
    other_side = "3.11.9" if common.float_sum_side(sealed) == "compensated" else "3.12.0"
    drifted = tmp_path / "scripts"
    shutil.copytree(SCRIPTS, drifted, ignore=shutil.ignore_patterns("__pycache__"))
    target = drifted / "compute_summary.py"
    target.write_text(target.read_text(encoding="utf-8") + "# an edit after the run was sealed\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError,
                           match=r"script_hashes do not match pilot/scripts for \['compute_summary.py'\]"):
            check_recorded_run(PILOT, tmp_path, scripts=drifted, running=other_side)
    except pytest.skip.Exception as skipped:
        pytest.fail(f"a drifted pilot script reached the interpreter skip before the recorded hashes were compared "
                    f"({skipped}); the hash comparison must come first and fail")
    with pytest.raises(pytest.skip.Exception, match="every recorded hash matches its file"):
        check_recorded_run(PILOT, tmp_path, scripts=SCRIPTS, running=other_side)
