"""The logits-eval lane's opt-in pilot output root (`output_root`, 2026-10-04).

Circuit-trace's pilot root (tests/test_circuit_trace_pilot_root.py) carried over to the CPU next-token lane: pilot
stimulus pairs under pilot/runs/ are measured by the open-weight models at $0 into pilot/logits/<stem>__<model>/, so
their outputs never enter trace_out/, where every collector reads measurements. Each thing is held by running or
parsing what CI runs:

- the params job's push-path refusals (its python heredoc, run as CI runs it) agree case for case with the fire-time
  refusals in scripts/fire_trigger.py, and a refused config writes no job outputs;
- the "Resolve output dir" step writes OUT_DIR under the pilot root only when asked, and leaves the default root's
  three paths (logits, depth, verify) as they were;
- the eval job checks out pilot/runs and never pilot/logits; a fail-closed holdout seal check runs after the
  measurement and before the commit, over a copy of what the cell wrote and the pairs file; a pilot cell commits
  only its batch_summary part, and only when that check succeeded; and the run-page summary is gated the same way.

The pairs and phrases written here are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "logits_evaluation.yml"
# the trigger directory, spelled once so no test body carries the literal path
TRIGGER_SUBDIR = Path(".github") / "trigger"
PILOT_ROOT = "pilot/logits"
# the pairs file of the circuit-trace pilot fire of 2026-10-02 (pilot run 2's review sample): the file a first pilot
# logits fire would most likely measure, so a config of its shape stays accepted whatever the rules become
RUN2_PAIRS = "pilot/runs/pilot_v2_20261002/trace/trace_pairs.json"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"{name}_logits_pilot_root", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")
tierb = _load("tierb_split")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _params_step() -> dict:
    return next(s for s in _workflow()["jobs"]["params"]["steps"] if s.get("id") == "params")


def _params_heredoc() -> str:
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", _params_step()["run"], re.S)
    assert m, "the params step no longer carries its python heredoc"
    return m.group(1)


def _eval_steps() -> list[dict]:
    return _workflow()["jobs"]["eval"]["steps"]


def _step(name_prefix: str) -> dict:
    return next(s for s in _eval_steps() if str(s.get("name", "")).startswith(name_prefix))


def _run_params(tmp_path: Path, cfg: dict) -> tuple[int, str, str]:
    """Run the params heredoc on the push path, as CI runs it, over a trigger file holding `cfg`."""
    trigger_dir = tmp_path / TRIGGER_SUBDIR
    trigger_dir.mkdir(parents=True, exist_ok=True)
    (trigger_dir / "logits-eval.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "push", "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=_params_heredoc(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


def _fire_refuses(cfg: dict) -> list[str]:
    """Every refusal the fire path gives these params before journaling (validate_params)."""
    try:
        ft.validate_params("logits-eval", {"commit_outputs": "false", **cfg})
    except ValueError as exc:
        return [str(exc)]
    return []


BASE = {"models": "qwen3-1.7b", "commit_outputs": "false"}
PILOT = {"output_root": PILOT_ROOT, "pairs_file": "pilot/runs/p.json"}

# (case id, trigger params on top of BASE, refused?)
CASES = [
    ("default-root-default-pairs", {}, False),
    ("default-root-study-pairs", {"pairs_file": "data/x.json"}, False),
    ("default-root-explicit-empty-root", {"pairs_file": "data/x.json", "output_root": ""}, False),
    ("default-root-depth-is-unchanged", {"pairs_file": "data/x.json", "mode": "depth"}, False),
    ("default-root-verify-is-unchanged", {"pairs_file": "data/x.json", "mode": "verify", "dtype": "bfloat16"}, False),
    ("pilot-pairs-need-the-pilot-root", {"pairs_file": "pilot/runs/p.json"}, True),
    ("pilot-pairs-outside-runs-need-the-pilot-root-too", {"pairs_file": "pilot/p.json"}, True),
    ("dotted-pilot-pairs-need-the-pilot-root", {"pairs_file": "./pilot/runs/p.json"}, True),
    ("circuit-trace-pilot-root-is-not-this-lanes", {**PILOT, "output_root": "pilot/traces"}, True),
    ("pilot-root-plain", dict(PILOT), False),
    ("pilot-root-mode-logits-stated", {**PILOT, "mode": "logits"}, False),
    ("pilot-root-dotted-runs-pairs", {**PILOT, "pairs_file": "./pilot/runs/p.json"}, False),
    ("pilot-root-list-of-models", {**PILOT, "models": ["qwen3-4b", "qwen3-1.7b"]}, False),
    ("pilot-root-chunked", {**PILOT, "limit": 10, "offset": 20}, False),
    ("pilot-root-the-run-2-review-sample", {"models": "qwen3-4b qwen3-1.7b", "pairs_file": RUN2_PAIRS,
                                            "output_root": PILOT_ROOT, "limit": "0", "offset": "0",
                                            "commit_outputs": "true"}, False),
    ("pilot-root-study-pairs", {**PILOT, "pairs_file": "data/x.json"}, True),
    ("pilot-root-escaping-pairs", {**PILOT, "pairs_file": "pilot/../data/x.json"}, True),
    ("pilot-root-default-pairs", {"output_root": PILOT_ROOT}, True),
    ("pilot-root-empty-pairs", {**PILOT, "pairs_file": ""}, True),
    # under the pilot root a pairs file sits under pilot/runs/, the one pilot directory the eval job checks out;
    # pilot/logits, where earlier pilot parts are committed, never is
    ("pilot-root-pilot-pairs-outside-runs", {**PILOT, "pairs_file": "pilot/p.json"}, True),
    ("pilot-root-pairs-under-pilot-logits", {**PILOT, "pairs_file": "pilot/logits/p__qwen3-1.7b/x.json"}, True),
    ("pilot-root-runs-climbing-to-logits", {**PILOT, "pairs_file": "pilot/runs/../logits/p/x.json"}, True),
    ("pilot-root-the-runs-directory-itself", {**PILOT, "pairs_file": "pilot/runs"}, True),
    ("unknown-root", {**PILOT, "output_root": "trace_out"}, True),
    ("trailing-slash-root", {**PILOT, "output_root": "pilot/logits/"}, True),
    ("case-variant-root", {**PILOT, "output_root": "Pilot/logits"}, True),
    ("null-root", {**PILOT, "output_root": None}, True),
    ("boolean-root", {**PILOT, "output_root": True}, True),
    # a pilot run measures next-token behavior only: depth and verify write other files under trace_out/ names
    ("pilot-depth", {**PILOT, "mode": "depth"}, True),
    ("pilot-verify", {**PILOT, "mode": "verify"}, True),
    ("pilot-mode-case-variant", {**PILOT, "mode": "Logits"}, True),
    ("pilot-mode-padded", {**PILOT, "mode": " logits"}, True),
    # the seal step's --extra list splits on commas, so a comma in a pilot pairs name would scan nothing of it
    ("pilot-root-comma-pairs", {**PILOT, "pairs_file": "pilot/runs/a,b.json"}, True),
    ("default-root-comma-pairs-is-unchanged", {"pairs_file": "data/a,b.json"}, False),
    # an absolute or ..-escaping path can name the checkout's pilot/ without the pilot/ prefix, so both are refused
    ("absolute-pilot-pairs-default-root", {"pairs_file": "/home/runner/work/engine/engine/pilot/runs/p.json"}, True),
    ("absolute-pilot-pairs-pilot-root", {**PILOT, "pairs_file": "/home/runner/work/engine/engine/pilot/runs/p.json"},
     True),
    ("absolute-study-pairs", {"pairs_file": "/home/runner/work/engine/engine/data/x.json"}, True),
    ("escaping-pilot-pairs-default-root", {"pairs_file": "../engine/pilot/runs/p.json"}, True),
    ("escaping-via-inner-dots", {"pairs_file": "data/../../engine/pilot/runs/p.json"}, True),
    # a backslash is part of a file name on the Linux runner, so a Windows spelling would hide pilot/ (or a drive or
    # UNC root) from the tests above; it is refused under every root, before any of them is read
    ("backslash-pilot-pairs-default-root", {"pairs_file": "pilot\\runs\\p.json"}, True),
    ("backslash-study-pairs-default-root", {"pairs_file": "data\\x.json"}, True),
    ("backslash-pilot-pairs-pilot-root", {**PILOT, "pairs_file": "pilot\\runs\\p.json"}, True),
    ("mixed-separators-pilot-root", {**PILOT, "pairs_file": "pilot/runs\\p.json"}, True),
    ("drive-letter-pairs", {"pairs_file": "C:\\engine\\pilot\\runs\\p.json"}, True),
    ("unc-pairs", {"pairs_file": "\\\\runner\\engine\\pilot\\runs\\p.json"}, True),
    # with / separators a drive spelling is a relative name on the Linux runner, read alike on both sides
    ("forward-slash-drive-spelling-default-root", {"pairs_file": "C:/engine/data/x.json"}, False),
    ("forward-slash-drive-spelling-pilot-root", {**PILOT, "pairs_file": "C:/engine/pilot/runs/p.json"}, True),
]


def _outputs(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if line)


@pytest.mark.parametrize("cfg, refused", [(c, r) for _, c, r in CASES], ids=[i for i, _, _ in CASES])
def test_the_params_job_and_the_fire_path_refuse_the_same_pilot_configs(tmp_path, cfg, refused):
    full = {**BASE, **cfg}
    rc, out, err = _run_params(tmp_path, full)
    fire_problems = _fire_refuses(full)
    assert (rc != 0) == refused, (rc, err)
    assert bool(fire_problems) == refused, fire_problems
    if refused:
        assert out == "", "a refused config writes no outputs, so no eval job starts"
    else:
        assert _outputs(out)["output_root"] == cfg.get("output_root", "")


@pytest.mark.parametrize("cfg, needle", [
    ({"pairs_file": "pilot/runs/p.json"}, "is under pilot/"),
    ({**PILOT, "pairs_file": "pilot/p.json"}, "under pilot/runs/"),
    ({**PILOT, "pairs_file": "pilot/logits/p/x.json"}, "under pilot/runs/"),
    ({**PILOT, "mode": "depth"}, "mode 'depth'"),
    ({**PILOT, "pairs_file": "pilot/runs/a,b.json"}, "contains a comma"),
    ({**PILOT, "output_root": "pilot/traces"}, "or 'pilot/logits' is accepted"),
    ({"pairs_file": "pilot\\runs\\p.json"}, "contains a backslash"),
    ({"pairs_file": "/abs/pilot/runs/p.json"}, "is absolute or leaves the checkout"),
], ids=["pilot-pairs-default-root", "pilot-file-outside-runs", "pilot-logits-file", "depth-mode", "comma",
        "circuit-trace-root", "backslash", "absolute"])
def test_both_sides_name_the_refusal(tmp_path, cfg, needle):
    full = {**BASE, **cfg}
    rc, _, err = _run_params(tmp_path, full)
    assert rc != 0 and needle in err, err
    fire_problems = _fire_refuses(full)
    assert fire_problems and needle in " ".join(fire_problems), fire_problems


def test_the_park_default_resolves_exactly_as_before_with_an_empty_root(tmp_path):
    """The default root is unchanged for existing fires: the park default resolves to the same nine outputs as before
    this change, plus output_root, empty."""
    park = dict(ft.PARK_DEFAULTS["logits-eval"])
    assert ft.logits_eval_params_problems(park) == [] and ft.validate_params("logits-eval", park) is None
    rc, out, err = _run_params(tmp_path, park)
    assert rc == 0, err
    assert out == ('models=["qwen3-1.7b"]\n'
                   "pairs_file=data/simulated/pairs_20260706T172135Z.json\n"
                   "limit=1\noffset=0\ncommit_outputs=false\nmode=logits\nlayers=all\ntopk=10\ndtype=float32\n"
                   "output_root=\n")


def test_the_params_job_publishes_the_root_and_its_defaults_match_the_fire_path():
    params_job = _workflow()["jobs"]["params"]
    assert params_job["outputs"]["output_root"] == "${{ steps.params.outputs.output_root }}"
    block = _params_step()["run"]
    block = block[block.index("defaults = {"):]
    literal = block[:block.index("}") + 1]
    assert '"output_root": ""' in literal, "output_root defaults to '' (trace_out)"
    for key, value in ft.LOGITS_EVAL_JOB_DEFAULTS.items():
        assert f'"{key}": {json.dumps(value)}' in literal, key
    # a workflow_dispatch has no output_root input, so it always measures into trace_out/
    assert "output_root" not in _workflow()[True]["workflow_dispatch"]["inputs"]


def test_a_dispatch_of_pilot_pairs_is_refused_too(tmp_path):
    """The dispatch path reads the form inputs, of which output_root is none, so a pilot pairs file given there is
    refused rather than measured into trace_out/."""
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "workflow_dispatch", "GITHUB_OUTPUT": str(out),
           "IN_MODELS": "qwen3-1.7b", "IN_PAIRS_FILE": "pilot/runs/p.json"}
    proc = subprocess.run([sys.executable, "-"], input=_params_heredoc(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    assert proc.returncode != 0 and "is under pilot/" in proc.stderr, proc.stderr
    assert out.read_text(encoding="utf-8") == ""


# --- Resolve output dir -----------------------------------------------------------------------------------------

def _run_resolve(tmp_path: Path, mode: str, root: str | None, pairs_file: str = "data/simulated/pairs_X.json",
                 model: str = "qwen3-4b", offset: str = "10", topk: str = "10") -> tuple[int, str, str]:
    gh_env = tmp_path / "gh_env"
    gh_env.write_text("")
    env = {**os.environ, "MODEL": model, "PAIRS_FILE": pairs_file, "OFFSET": offset, "MODE": mode, "TOPK": topk,
           "GITHUB_ENV": str(gh_env)}
    env.pop("OUTPUT_ROOT", None)
    if root is not None:
        env["OUTPUT_ROOT"] = root
    # GitHub runs a `run:` block as `bash --noprofile --norc -eo pipefail`
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step("Resolve output dir")["run"]],
                          cwd=tmp_path, capture_output=True, text=True, env=env)
    return proc.returncode, gh_env.read_text(encoding="utf-8"), proc.stdout + proc.stderr


@pytest.mark.parametrize("root", ["", None])
@pytest.mark.parametrize("mode, expected", [
    ("logits", "OUT_DIR=trace_out/pairs_X__qwen3-4b\nSUMMARY_FILE=batch_summary.part_11.json\n"),
    ("depth", "OUT_DIR=trace_out/depth_k10_pairs_X__qwen3-4b\nSUMMARY_FILE=depth_probe.part_11.json\n"),
    ("verify", "OUT_DIR=trace_out/verify_pairs_X__qwen3-4b\nSUMMARY_FILE=verify_summary.part_11.json\n"),
])
def test_the_default_root_keeps_all_three_trace_out_paths(tmp_path, root, mode, expected):
    rc, env, log = _run_resolve(tmp_path, mode, root)
    assert rc == 0, log
    assert env == "PART=part_11\n" + expected


def test_the_pilot_root_writes_under_pilot_logits_with_the_model_suffix(tmp_path):
    rc, env, log = _run_resolve(tmp_path, "logits", PILOT_ROOT, pairs_file=RUN2_PAIRS, model="qwen3-1.7b", offset="0")
    assert rc == 0, log
    assert env == ("PART=part_01\nOUT_DIR=pilot/logits/trace_pairs__qwen3-1.7b\n"
                   "SUMMARY_FILE=batch_summary.part_01.json\n")


@pytest.mark.parametrize("mode, root", [("depth", PILOT_ROOT), ("verify", PILOT_ROOT), ("logits", "pilot/traces"),
                                        ("logits", "trace_out")])
def test_the_resolve_step_refuses_what_the_params_job_never_admits(tmp_path, mode, root):
    rc, env, _ = _run_resolve(tmp_path, mode, root)
    assert rc != 0
    assert "OUT_DIR=" not in env and "SUMMARY_FILE=" not in env


def test_the_resolve_step_reads_the_root_from_the_params_job():
    assert _step("Resolve output dir")["env"]["OUTPUT_ROOT"] == "${{ needs.params.outputs.output_root }}"
    measure = _step("Measure next-token behavior")
    assert measure["if"] == "${{ needs.params.outputs.mode == 'logits' }}"
    assert '--out "$OUT_DIR"' in measure["run"]


# --- checkout, seal check, commit, run page ---------------------------------------------------------------------

def _checkout_cone(job: str) -> list[str]:
    steps = _workflow()["jobs"][job]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    return checkout["with"]["sparse-checkout"].split()


def test_the_eval_job_checks_out_pilot_runs_and_leaves_pilot_logits_out():
    """Earlier pilot parts are committed under pilot/logits; checking that tree out would put them in a later cell's
    OUT_DIR. Only pilot/runs, where pilot-root pairs files sit, is checked out, and pilot/logits stays out as trace_out/
    does. The params job reads no pairs file, so it checks out no pilot path."""
    cone = _checkout_cone("eval")
    assert [c for c in cone if c.strip("/").split("/")[0] == "pilot"] == ["pilot/runs"], cone
    assert not any(c.strip("/").split("/")[0] == "trace_out" for c in cone), cone
    assert {".github", "scripts", "data", "medlang_circuits", "docs", "ops", "tests"} <= set(cone)
    assert not any(c.strip("/").split("/")[0] == "pilot" for c in _checkout_cone("params"))
    assert ft.CIRCUIT_TRACE_PILOT_RUNS_PREFIX == "pilot/runs/", "the fire path requires the directory checked out"


SEAL_IF = "${{ always() && needs.params.outputs.output_root == 'pilot/logits' }}"
PILOT_SEAL_GATE = "(needs.params.outputs.output_root != 'pilot/logits' || steps.seal.outcome == 'success')"


def test_a_fail_closed_seal_check_runs_after_every_measurement_and_before_the_commit():
    steps = _eval_steps()
    names = [str(s.get("name", "")) for s in steps]
    seal_at = next(i for i, s in enumerate(steps) if s.get("id") == "seal")
    measure_at = [i for i, n in enumerate(names) if n.startswith(("Measure ", "Re-measure "))]
    commit_at = names.index("Commit the per-model summary to the branch")
    assert len(measure_at) == 3 and max(measure_at) < seal_at < commit_at
    seal = steps[seal_at]
    # gated on the pilot root, and run after a failed measurement as the checkpoint commit is
    assert seal["if"] == SEAL_IF
    assert seal["env"] == {"PAIRS_FILE": "${{ needs.params.outputs.pairs_file }}"}
    assert 'python scripts/seal_check.py --site "$RUNNER_TEMP/no-site" --extra "$SEAL_COPY,$PAIRS_FILE"' in seal["run"]
    assert "continue-on-error" not in seal, "the seal check fails the job"
    run = seal["run"]
    assert run.index('test -f "$PAIRS_FILE"') < run.index('cp -R "$OUT_DIR/." "$SEAL_COPY/"') < run.index("python scripts/seal_check.py")


def test_a_pilot_cell_commits_only_after_its_seal_check_and_only_its_summary_part():
    commit = _step("Commit the per-model summary to the branch")
    assert commit["if"] == ("${{ always() && needs.params.outputs.commit_outputs == 'true' && "
                            + PILOT_SEAL_GATE + " }}")
    # the one file staged is the cell's own summary, which the resolve step names batch_summary.part_NN.json under the
    # pilot root (test_the_pilot_root_writes_under_pilot_logits_with_the_model_suffix)
    adds = [ln.strip() for ln in commit["run"].splitlines() if "git add" in ln]
    assert adds == ['git add --sparse -f "$OUT_DIR/$SUMMARY_FILE"'], adds


def test_a_pilot_cell_whose_seal_check_failed_prints_no_summary_to_the_run_page():
    steps = _eval_steps()
    names = [str(s.get("name", "")) for s in steps]
    seal_at = next(i for i, s in enumerate(steps) if s.get("id") == "seal")
    at = names.index("Job summary")
    assert at > seal_at
    assert steps[at]["if"] == "${{ always() && " + PILOT_SEAL_GATE + " }}"
    # the logits lane uploads no artifact; if one is added, it is a publication and needs the same gate
    assert not any(str(s.get("uses", "")).startswith("actions/upload-artifact") for s in steps)


# --- the seal step, run as CI runs it ---------------------------------------------------------------------------

SEALED_BATCH = "pairs_20260711T000000Z"
TIERB_START = "2026-07-10T01:14:38Z"
OUT_DIR = "pilot/logits/p__qwen3-1.7b"


def _sealed_phrase() -> str:
    for i in range(500):
        phrase = f"zz placeholder phrase {i}"
        if tierb.is_holdout(phrase):
            return phrase
    raise AssertionError("no placeholder phrase hashes into the holdout bucket")


def _part(text: str) -> str:
    return json.dumps({"backend": "logits", "results": [{"index": 11, "prompts": {"clinical": text,
                                                                                    "patient": "placeholder"}}]})


def _seal_repo(tmp_path: Path, pairs_text: str = "placeholder pairs", part_text: str | None = "placeholder part"
               ) -> tuple[Path, dict]:
    """A checkout as the seal step sees it: a sealed set of one placeholder phrase (data/simulated + ops), the
    pairs file, and OUT_DIR holding this cell's part (none when part_text is None). scripts/ is the real one."""
    repo = tmp_path / "repo"
    (repo / "data" / "simulated").mkdir(parents=True)
    (repo / "data" / "simulated" / f"{SEALED_BATCH}.json").write_text(
        json.dumps([{"top_prompt": _sealed_phrase(), "bottom_prompt": "placeholder"}]), encoding="utf-8")
    (repo / "ops").mkdir()
    (repo / "ops" / "dashboard.json").write_text(json.dumps({"tierb": {"start_utc": TIERB_START}}), encoding="utf-8")
    (repo / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
    (repo / "pilot" / "runs").mkdir(parents=True)
    (repo / "pilot" / "runs" / "p.json").write_text(
        json.dumps([{"top_prompt": pairs_text, "bottom_prompt": "placeholder"}]), encoding="utf-8")
    if part_text is not None:
        (repo / OUT_DIR).mkdir(parents=True)
        (repo / OUT_DIR / "batch_summary.part_11.json").write_text(_part(part_text), encoding="utf-8")
    # `python` on PATH is this interpreter, as setup-python makes it on the runner
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python").symlink_to(sys.executable)
    runner_temp = tmp_path / "runner_temp"            # outside the checkout, as on the runner
    runner_temp.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"PATH": f"{bindir}{os.pathsep}{env.get('PATH', '')}", "RUNNER_TEMP": str(runner_temp),
                "OUT_DIR": OUT_DIR, "PAIRS_FILE": "pilot/runs/p.json"})
    return repo, env


def _run_seal(repo: Path, env: dict) -> subprocess.CompletedProcess:
    seal = next(s for s in _eval_steps() if s.get("id") == "seal")
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", seal["run"]], cwd=repo,
                          capture_output=True, text=True, env=env)


def test_the_seal_step_passes_a_clean_cell(tmp_path):
    repo, env = _seal_repo(tmp_path)
    proc = _run_seal(repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "seal check: CLEAN" in proc.stdout and "(2 file(s) scanned)" in proc.stdout, proc.stdout


def test_the_seal_step_fails_on_a_sealed_phrase_in_the_cells_output(tmp_path):
    repo, env = _seal_repo(tmp_path, part_text=_sealed_phrase())
    proc = _run_seal(repo, env)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "LEAK" in proc.stdout and f"{SEALED_BATCH}#1" in proc.stdout
    assert _sealed_phrase() not in proc.stdout, "the report names labels, never phrase text"


def test_the_seal_step_fails_on_a_sealed_phrase_in_the_pairs_file(tmp_path):
    repo, env = _seal_repo(tmp_path, pairs_text=_sealed_phrase(), part_text=None)
    proc = _run_seal(repo, env)
    assert proc.returncode == 1 and "LEAK" in proc.stdout, proc.stdout + proc.stderr


def test_the_seal_step_fails_when_the_pairs_file_is_absent(tmp_path):
    """seal_check.py reads a missing root as zero files and passes, so the step itself refuses a missing pairs file
    before the check runs."""
    repo, env = _seal_repo(tmp_path)
    env["PAIRS_FILE"] = "pilot/runs/absent.json"
    proc = _run_seal(repo, env)
    assert proc.returncode == 1 and "pairs file pilot/runs/absent.json not found" in proc.stdout
    assert "CLEAN" not in proc.stdout and "LEAK" not in proc.stdout, "seal_check.py never ran"


def test_the_seal_step_fails_when_the_output_dir_was_never_resolved(tmp_path):
    repo, env = _seal_repo(tmp_path)
    del env["OUT_DIR"]
    assert _run_seal(repo, env).returncode != 0


def _git(repo: Path, *args: str, env: dict) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                    "-c", "core.hooksPath=/dev/null", *args], cwd=repo, env=env, check=True, capture_output=True)


def _hide_an_earlier_part(repo: Path, env: dict) -> None:
    """Commit an earlier chunk's part in OUT_DIR and keep it off disk with the skip-worktree bit, which is how the
    runner's sparse checkout leaves every committed file outside its cone (pilot/logits is outside it)."""
    earlier = f"{OUT_DIR}/batch_summary.part_01.json"
    (repo / earlier).write_text(_part("placeholder earlier part"), encoding="utf-8")
    _git(repo, "init", "-q", env=env)
    _git(repo, "add", earlier, env=env)
    _git(repo, "commit", "-q", "-m", "earlier chunk", env=env)
    _git(repo, "update-index", "--skip-worktree", earlier, env=env)
    (repo / earlier).unlink()


def test_a_later_chunk_passes_the_seal_check_beside_an_earlier_committed_part(tmp_path):
    """Why the step sweeps a copy: this lane chunks across fires (one offset per fire), so a later chunk's OUT_DIR
    holds an earlier chunk's committed part, off disk. seal_check.py refuses a root holding such a file (exit 2), which
    would fail closed on every chunk after the first; the copy holds only what this cell wrote."""
    repo, env = _seal_repo(tmp_path)
    _hide_an_earlier_part(repo, env)
    in_place = subprocess.run([sys.executable, "scripts/seal_check.py", "--site", str(tmp_path / "no-site"),
                               "--extra", f"{OUT_DIR},pilot/runs/p.json"], cwd=repo, capture_output=True, text=True,
                              env=env)
    assert in_place.returncode == 2 and "not on disk" in in_place.stdout, in_place.stdout
    proc = _run_seal(repo, env)
    assert proc.returncode == 0 and "seal check: CLEAN" in proc.stdout, proc.stdout + proc.stderr


def test_a_later_chunk_with_a_sealed_phrase_still_fails(tmp_path):
    repo, env = _seal_repo(tmp_path, part_text=_sealed_phrase())
    _hide_an_earlier_part(repo, env)
    proc = _run_seal(repo, env)
    assert proc.returncode == 1 and "LEAK" in proc.stdout, proc.stdout + proc.stderr
