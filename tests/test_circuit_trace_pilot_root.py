"""The circuit-trace lane's opt-in pilot output root (`output_root`, 2026-10-01).

Pilot stimulus pairs are traced at $0 into pilot/traces/<stem>/ so their outputs
never enter trace_out/, where every collector reads measurements. Three things
are held here, each by running or parsing what CI runs:

- the params job's push-path refusals (its python heredoc, run as CI runs it, the
  pattern of tests/test_petri_audit_params_heredoc.py) agree case for case with
  the fire-time refusals in scripts/fire_trigger.py;
- the "Select sample pairs" heredoc writes OUT_DIR under the pilot root only when
  asked, and leaves the default trace_out/<stem>[__<model>] path as it was;
- the trace job checks out pilot/, seal-checks a pilot cell before committing it,
  commits only its summary parts, and commits nothing from a pilot cell whose seal
  check did not succeed.

The pairs written here are abstract placeholders, never study stimuli.
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
WORKFLOW = ROOT / ".github" / "workflows" / "circuit_trace_evaluation.yml"
# the trigger directory, spelled once so no test body carries the literal path
TRIGGER_SUBDIR = Path(".github") / "trigger"
PILOT_ROOT = "pilot/traces"


def _load_fire_trigger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fire_trigger_pilot_root", ROOT / "scripts" / "fire_trigger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ft = _load_fire_trigger()


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _heredoc(step: dict) -> str:
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", step["run"], re.S)
    assert m, f"step {step.get('name') or step.get('id')!r} no longer carries its python heredoc"
    return m.group(1)


def _params_step() -> dict:
    return next(s for s in _workflow()["jobs"]["params"]["steps"] if s.get("id") == "params")


def _trace_steps() -> list[dict]:
    return _workflow()["jobs"]["trace"]["steps"]


def _step(name_prefix: str) -> dict:
    return next(s for s in _trace_steps() if str(s.get("name", "")).startswith(name_prefix))


def _pair(target: bool = True) -> dict:
    pair = {"top_prompt": "placeholder alpha", "bottom_prompt": "placeholder beta"}
    if target:
        pair["target_clinical_token"] = " gamma"
    return pair


def _write_pairs(base: Path) -> None:
    """pilot/p.json: four pairs, the fourth (1-based index 4) without a target; pilot/q.json: the third without
    one; data/x.json: a study-side file with no targets at all."""
    (base / "pilot").mkdir(parents=True, exist_ok=True)
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "pilot" / "p.json").write_text(json.dumps([_pair(), _pair(), _pair(), _pair(False)]), encoding="utf-8")
    (base / "pilot" / "q.json").write_text(json.dumps([_pair(), _pair(), _pair(False)]), encoding="utf-8")
    (base / "data" / "x.json").write_text(json.dumps([_pair(False), _pair(False)]), encoding="utf-8")


def _run_params(tmp_path: Path, cfg: dict) -> tuple[int, str, str]:
    trigger_dir = tmp_path / TRIGGER_SUBDIR
    trigger_dir.mkdir(parents=True, exist_ok=True)
    (trigger_dir / "circuit-trace.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "push", "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=_heredoc(_params_step()), cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


def _fire_refuses(tmp_path: Path, cfg: dict) -> list[str]:
    """Every refusal the fire path gives these params before journaling (validate_params, then the source check)."""
    try:
        ft.validate_params("circuit-trace", {"commit_outputs": "false", **cfg})
    except ValueError as exc:
        return [str(exc)]
    return ft.circuit_trace_pilot_source_problems(tmp_path, "circuit-trace", cfg)


PILOT = {"output_root": PILOT_ROOT, "pairs_file": "pilot/p.json"}

# (case id, trigger params, refused?)
CASES = [
    ("default-root-default-pairs", {}, False),
    ("default-root-study-pairs", {"pairs_file": "data/x.json"}, False),
    ("default-root-screening-is-unchanged", {"pairs_file": "data/x.json", "screen_targets": "0.02"}, False),
    ("pilot-pairs-need-the-pilot-root", {"pairs_file": "pilot/p.json"}, True),
    ("dotted-pilot-pairs-need-the-pilot-root", {"pairs_file": "./pilot/p.json"}, True),
    ("pilot-root-plain", dict(PILOT), False),
    ("pilot-root-other-mode", {**PILOT, "mode": "4quadrant"}, False),
    ("pilot-root-list-offsets", {**PILOT, "offsets": [0, 2], "sample_size": "1"}, False),
    ("pilot-root-study-pairs", {**PILOT, "pairs_file": "data/x.json"}, True),
    ("pilot-root-escaping-pairs", {**PILOT, "pairs_file": "pilot/../data/x.json"}, True),
    ("pilot-root-default-pairs", {"output_root": PILOT_ROOT}, True),
    ("unknown-root", {**PILOT, "output_root": "trace_out"}, True),
    ("trailing-slash-root", {**PILOT, "output_root": "pilot/traces/"}, True),
    ("case-variant-root", {**PILOT, "output_root": "Pilot/traces"}, True),
    ("null-root", {**PILOT, "output_root": None}, True),
    ("pilot-mitigation-bool", {**PILOT, "show_mitigation": True}, True),
    ("pilot-mitigation-upper", {**PILOT, "show_mitigation": "TRUE"}, True),
    ("pilot-mitigation-off", {**PILOT, "show_mitigation": False}, False),
    ("pilot-translation", {**PILOT, "mode": "translation"}, True),
    ("pilot-translation-variant", {**PILOT, "mode": " Translation"}, True),
    ("pilot-steer-validate", {**PILOT, "steer_validate": "5"}, True),
    ("pilot-steer-boost", {**PILOT, "steer_boost": "3"}, True),
    ("pilot-steer-placebo", {**PILOT, "steer_placebo": "2"}, True),
    ("pilot-steer-false-is-passed-on", {**PILOT, "steer_validate": False}, True),
    ("pilot-steer-zero", {**PILOT, "steer_validate": "0", "steer_boost": 0, "steer_placebo": ""}, False),
    ("pilot-explanations", {**PILOT, "generate_explanations": "1"}, True),
    ("pilot-screen-all-targeted", {**PILOT, "screen_targets": "0.02", "offsets": "0", "sample_size": "3"}, False),
    ("pilot-screen-untargeted-in-slice", {**PILOT, "screen_targets": "0.02", "offsets": "0", "sample_size": "4"},
     True),
    ("pilot-screen-untargeted-in-later-offset", {**PILOT, "screen_targets": "0.02", "offsets": [0, 3],
                                                 "sample_size": "1"}, True),
    ("pilot-screen-other-file", {**PILOT, "pairs_file": "pilot/q.json", "screen_targets": "0.02",
                                 "offsets": [0, 1], "sample_size": "1"}, False),
    ("pilot-screen-other-file-missing", {**PILOT, "pairs_file": "pilot/q.json", "screen_targets": "0.02",
                                         "offsets": "1", "sample_size": "5"}, True),
]


@pytest.mark.parametrize("cfg, refused", [(c, r) for _, c, r in CASES], ids=[i for i, _, _ in CASES])
def test_the_params_job_and_the_fire_path_refuse_the_same_pilot_configs(tmp_path, cfg, refused):
    _write_pairs(tmp_path)
    rc, out, err = _run_params(tmp_path, {"commit_outputs": "false", **cfg})
    fire_problems = _fire_refuses(tmp_path, cfg)
    assert (rc != 0) == refused, (rc, err)
    assert bool(fire_problems) == refused, fire_problems
    if refused:
        assert out == "", "a refused config writes no outputs, so no trace job starts"
    else:
        config = json.loads(next(line for line in out.splitlines() if line.startswith("config="))[len("config="):])
        expected_root = cfg.get("output_root", "")
        assert config["output_root"] == expected_root


def test_the_fire_path_names_the_pairs_it_would_screen_out(tmp_path):
    _write_pairs(tmp_path)
    problems = ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {**PILOT, "screen_targets": "0.02", "offsets": "0", "sample_size": "4"})
    assert len(problems) == 1 and "1 selected pair(s)" in problems[0] and "indices 4" in problems[0], problems
    # a missing pairs file is a named refusal, not a pass
    problems = ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {**PILOT, "pairs_file": "pilot/absent.json", "screen_targets": "0.02"})
    assert problems and "cannot read the pairs file" in problems[0], problems
    # other lanes and the default root are untouched
    assert ft.circuit_trace_pilot_source_problems(tmp_path, "logits-eval", {**PILOT, "screen_targets": "1"}) == []
    assert ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {"pairs_file": "data/x.json", "screen_targets": "0.02"}) == []


def test_the_park_default_and_the_params_jobs_defaults_pass_the_pilot_rules():
    assert ft.circuit_trace_params_problems(dict(ft.PARK_DEFAULTS["circuit-trace"])) == []
    assert ft.validate_params("circuit-trace", dict(ft.PARK_DEFAULTS["circuit-trace"])) is None
    block = _params_step()["run"]
    block = block[block.index("defaults = {"):]
    assert '"output_root": ""' in block[:block.index("}") + 1], "output_root defaults to '' (trace_out)"


# --- Select sample pairs: OUT_DIR -------------------------------------------------------------------------------

def _run_select(tmp_path: Path, pairs_file: str, model: str, root: str | None) -> str:
    _write_pairs(tmp_path)
    (tmp_path / "data" / "pairs_20990101T000000Z.json").write_text(json.dumps([_pair()]), encoding="utf-8")
    gh_env = tmp_path / "gh_env"
    gh_env.write_text("")
    env = {**os.environ, "MODE": "2panel", "SAMPLE_SIZE": "1", "PAIRS_FILE": pairs_file, "GRAPH_MODEL": model,
           "OFFSET": "0", "GITHUB_ENV": str(gh_env)}
    env.pop("OUTPUT_ROOT", None)
    if root is not None:
        env["OUTPUT_ROOT"] = root
    proc = subprocess.run([sys.executable, "-"], input=_heredoc(_step("Select sample pairs")), cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return gh_env.read_text(encoding="utf-8")


@pytest.mark.parametrize("root", ["", None])
def test_the_default_root_keeps_the_trace_out_path(tmp_path, root):
    batch = "data/pairs_20990101T000000Z.json"
    assert _run_select(tmp_path, batch, "gemma-2-2b", root) == "OUT_DIR=trace_out/pairs_20990101T000000Z\n"
    assert _run_select(tmp_path, batch, "qwen3-4b", root) == "OUT_DIR=trace_out/pairs_20990101T000000Z__qwen3-4b\n"


def test_the_pilot_root_writes_under_pilot_traces_with_the_model_suffix_rule(tmp_path):
    assert _run_select(tmp_path, "pilot/p.json", "gemma-2-2b", PILOT_ROOT) == "OUT_DIR=pilot/traces/p\n"
    assert _run_select(tmp_path, "pilot/p.json", "qwen3-4b", PILOT_ROOT) == "OUT_DIR=pilot/traces/p__qwen3-4b\n"


def test_the_select_step_reads_the_root_from_the_resolved_config():
    step = _step("Select sample pairs")
    assert step["env"]["OUTPUT_ROOT"] == "${{ fromJson(needs.params.outputs.config).output_root }}"
    assert 'out_dir = f"trace_out/{stem}"' in step["run"], "the default path's text is unchanged"


# --- checkout, seal check, commit -------------------------------------------------------------------------------

def test_both_sparse_checkouts_include_pilot_and_keep_their_other_roots():
    wf = _workflow()
    for job in ("params", "trace"):
        checkout = next(s for s in wf["jobs"][job]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
        cone = checkout["with"]["sparse-checkout"].split()
        assert "pilot" in cone, job
        assert {".github", "scripts", "data", "medlang_circuits", "docs", "ops", "tests"} <= set(cone), job


def test_a_fail_closed_seal_check_runs_before_a_pilot_commit():
    steps = _trace_steps()
    names = [str(s.get("name", "")) for s in steps]
    seal_at = next(i for i, s in enumerate(steps) if s.get("id") == "seal")
    run_at = names.index("Run batch evaluation against the hosted backend")
    commit_at = names.index("Commit trace outputs to the dispatched branch")
    assert run_at < seal_at < commit_at
    seal, commit = steps[seal_at], steps[commit_at]
    # gated on the pilot root, and run after a failed trace as the checkpoint commit is
    assert "always()" in seal["if"] and "fromJson(needs.params.outputs.config).output_root == 'pilot/traces'" in seal["if"]
    assert 'python scripts/seal_check.py --site "$RUNNER_TEMP/no-site" --extra "$OUT_DIR,$PAIRS_FILE"' in seal["run"]
    assert seal["env"]["PAIRS_FILE"] == "${{ fromJson(needs.params.outputs.config).pairs_file }}"
    assert "continue-on-error" not in seal, "the seal check fails the job"
    # a pilot cell commits only when the seal check succeeded; the default root's condition is otherwise unchanged
    cond = commit["if"]
    assert "always()" in cond and "fromJson(needs.params.outputs.config).commit_outputs == 'true'" in cond
    assert ("(fromJson(needs.params.outputs.config).output_root != 'pilot/traces' "
            "|| steps.seal.outcome == 'success')") in cond


def test_a_pilot_commit_stages_only_summary_parts_and_the_default_list_is_unchanged():
    run = _step("Commit trace outputs to the dispatched branch")["run"]
    assert _step("Commit trace outputs to the dispatched branch")["env"]["OUTPUT_ROOT"] == (
        "${{ fromJson(needs.params.outputs.config).output_root }}")
    m = re.search(r'if \[ "\$OUTPUT_ROOT" = "pilot/traces" \]; then\n(.*?)\n\s*else\n(.*?)\n\s*fi', run, re.S)
    assert m, "the commit step no longer branches on the pilot root"
    pilot_files = [ln.strip() for ln in m.group(1).splitlines() if ln.strip().startswith("FILES=")]
    default_files = [ln.strip() for ln in m.group(2).splitlines() if ln.strip().startswith("FILES=")]
    assert pilot_files == ['FILES=("$OUT_DIR"/batch_summary.part_*.json)']
    assert default_files == ['FILES=("$OUT_DIR"/index_*.html "$OUT_DIR"/index_*.png "$OUT_DIR"/multi_*.html '
                             '"$OUT_DIR"/multi_*.png "$OUT_DIR"/batch_summary.part_*.json '
                             '"$OUT_DIR"/mitigation.part_*.report.json)']
