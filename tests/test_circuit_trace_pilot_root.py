"""The circuit-trace lane's opt-in pilot output root (`output_root`, 2026-10-01).

Pilot stimulus pairs are traced at $0 into pilot/traces/<stem>/ so their outputs
never enter trace_out/, where every collector reads measurements. Three things
are held here, each by running or parsing what CI runs:

- the params job's push-path refusals (its python heredoc, run as CI runs it, the
  pattern of tests/test_petri_audit_params_heredoc.py) agree case for case with
  the fire-time refusals in scripts/fire_trigger.py; among them, a pilot pairs
  file is named for its run (pilot/runs/<run_id>/.../<run_id>_<name>.json,
  2026-10-04), so every pilot output folder carries its run id;
- the "Select sample pairs" heredoc writes OUT_DIR under the pilot root only when
  asked, and leaves the default trace_out/<stem>[__<model>] path as it was;
- both jobs check out pilot/runs and never pilot/traces (where earlier pilot parts
  are committed), the trace job seal-checks a pilot cell before committing it,
  commits only its summary parts, commits nothing from a pilot cell whose seal check
  did not succeed, and prints only the cell's own summary part to the run page.

The pairs written here are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import importlib.util
import json
import os
import posixpath
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


# the pairs path of the pilot fire of 2026-10-02 (pilot run 2's review sample), named before pilot pairs files were
# named for their run: its parts stay at pilot/traces/trace_pairs/, and a new fire of it is refused
RUN2_PAIRS = "pilot/runs/pilot_v2_20261002/trace/trace_pairs.json"
# the pairs path of the pilot fire of 2026-10-04 (pilot run 3's review sample, PR #84), renamed by hand for its run so
# its parts would not land in run 2's folder: the shape every later pilot pairs file takes, accepted
RUN3_PAIRS = "pilot/runs/pilot_v3_20261004/trace/pilot_v3_20261004_trace_pairs.json"
# a placeholder run, run_a, and its pairs files, named for it
P_PAIRS = "pilot/runs/run_a/run_a_p.json"
Q_PAIRS = "pilot/runs/run_a/run_a_q.json"


def _write_pairs(base: Path) -> None:
    """P_PAIRS: four pairs, the fourth (1-based index 4) without a target; Q_PAIRS: the third without one;
    pilot/p.json and pilot/traces/p/x.json: pilot files outside pilot/runs/; data/x.json: a study-side file with no
    targets at all; RUN2_PAIRS and RUN3_PAIRS: forty pairs each, every one targeted."""
    for sub in ("pilot/traces/p", "data", posixpath.dirname(P_PAIRS), posixpath.dirname(RUN2_PAIRS),
                posixpath.dirname(RUN3_PAIRS)):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (base / P_PAIRS).write_text(json.dumps([_pair(), _pair(), _pair(), _pair(False)]), encoding="utf-8")
    (base / Q_PAIRS).write_text(json.dumps([_pair(), _pair(), _pair(False)]), encoding="utf-8")
    (base / "pilot" / "p.json").write_text(json.dumps([_pair()]), encoding="utf-8")
    (base / "pilot" / "traces" / "p" / "x.json").write_text(json.dumps([_pair()]), encoding="utf-8")
    (base / "data" / "x.json").write_text(json.dumps([_pair(False), _pair(False)]), encoding="utf-8")
    for run_pairs in (RUN2_PAIRS, RUN3_PAIRS):
        (base / run_pairs).write_text(json.dumps([_pair() for _ in range(40)]), encoding="utf-8")


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


PILOT = {"output_root": PILOT_ROOT, "pairs_file": P_PAIRS}

# (case id, trigger params, refused?)
CASES = [
    ("default-root-default-pairs", {}, False),
    ("default-root-study-pairs", {"pairs_file": "data/x.json"}, False),
    ("default-root-screening-is-unchanged", {"pairs_file": "data/x.json", "screen_targets": "0.02"}, False),
    ("pilot-pairs-need-the-pilot-root", {"pairs_file": "pilot/runs/p.json"}, True),
    ("pilot-pairs-outside-runs-need-the-pilot-root-too", {"pairs_file": "pilot/p.json"}, True),
    ("dotted-pilot-pairs-need-the-pilot-root", {"pairs_file": "./pilot/runs/p.json"}, True),
    ("pilot-root-plain", dict(PILOT), False),
    ("pilot-root-dotted-runs-pairs", {**PILOT, "pairs_file": "./" + P_PAIRS}, False),
    ("pilot-root-other-mode", {**PILOT, "mode": "4quadrant"}, False),
    ("pilot-root-list-offsets", {**PILOT, "offsets": [0, 2], "sample_size": "1"}, False),
    ("pilot-root-study-pairs", {**PILOT, "pairs_file": "data/x.json"}, True),
    ("pilot-root-escaping-pairs", {**PILOT, "pairs_file": "pilot/../data/x.json"}, True),
    ("pilot-root-default-pairs", {"output_root": PILOT_ROOT}, True),
    # under the pilot root a pairs file sits under pilot/runs/, the one pilot directory either job checks out;
    # pilot/traces, where earlier pilot parts are committed, never is
    ("pilot-root-pilot-pairs-outside-runs", {**PILOT, "pairs_file": "pilot/p.json"}, True),
    ("pilot-root-pairs-under-pilot-traces", {**PILOT, "pairs_file": "pilot/traces/p/x.json"}, True),
    ("pilot-root-runs-climbing-to-traces", {**PILOT, "pairs_file": "pilot/runs/../traces/p/x.json"}, True),
    ("pilot-root-the-runs-directory-itself", {**PILOT, "pairs_file": "pilot/runs"}, True),
    # run 3's fire of 2026-10-04, as its trigger file held it, is accepted; the same config over run 2's legacy name
    # (its fire of 2026-10-02) is refused for a new fire
    ("pilot-root-run-3s-fire-config", {"mode": "2panel", "pairs_file": RUN3_PAIRS, "output_root": PILOT_ROOT,
                                       "graph_models": "gemma-2-2b", "offsets": "0,10,20,30", "sample_size": "10",
                                       "screen_targets": "0.02", "commit_outputs": "true"}, False),
    ("pilot-root-run-2s-fire-config", {"mode": "2panel", "pairs_file": RUN2_PAIRS, "output_root": PILOT_ROOT,
                                       "graph_models": "gemma-2-2b", "offsets": "0,10,20,30", "sample_size": "10",
                                       "screen_targets": "0.02", "commit_outputs": "true"}, True),
    # named for its run: pilot/runs/<run_id>/.../<run_id>_<name>.json, the name read as given (OUT_DIR's stem is cut
    # from it) and the run id from the normalised path
    ("pilot-root-pairs-in-a-deeper-directory", {**PILOT, "pairs_file": "pilot/runs/run_a/x/y/run_a_p.json"}, False),
    ("pilot-root-climbing-back-into-the-run", {**PILOT, "pairs_file": "pilot/runs/run_b/../run_a/run_a_p.json"},
     False),
    ("pilot-root-pairs-directly-in-runs", {**PILOT, "pairs_file": "pilot/runs/run_a_p.json"}, True),
    ("pilot-root-pairs-not-named-for-the-run", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/p.json"}, True),
    ("pilot-root-pairs-named-for-another-run", {**PILOT, "pairs_file": "pilot/runs/run_a/run_b_p.json"}, True),
    ("pilot-root-climbing-into-another-run", {**PILOT, "pairs_file": "pilot/runs/run_b/../run_a/run_b_p.json"}, True),
    ("pilot-root-run-id-without-the-underscore", {**PILOT, "pairs_file": "pilot/runs/run_a/run_ap.json"}, True),
    ("pilot-root-run-id-alone", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_.json"}, True),
    ("pilot-root-name-starts-with-part-of-the-run-id", {**PILOT, "pairs_file": "pilot/runs/run_a/run_p.json"}, True),
    ("pilot-root-not-a-json-name", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_p.txt"}, True),
    ("pilot-root-upper-case-suffix", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_p.JSON"}, True),
    ("pilot-root-trailing-dot", {**PILOT, "pairs_file": P_PAIRS + "/."}, True),
    ("pilot-root-trailing-slash", {**PILOT, "pairs_file": P_PAIRS + "/"}, True),
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
    ("pilot-screen-other-file", {**PILOT, "pairs_file": Q_PAIRS, "screen_targets": "0.02",
                                 "offsets": [0, 1], "sample_size": "1"}, False),
    ("pilot-screen-other-file-missing", {**PILOT, "pairs_file": Q_PAIRS, "screen_targets": "0.02",
                                         "offsets": "1", "sample_size": "5"}, True),
    # the seal step's --extra list splits on commas, so a comma in a pilot pairs name would scan nothing
    ("pilot-root-comma-pairs", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_a,b.json"}, True),
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
    # with / separators a drive spelling is a relative name on the Linux runner (a directory "C:" inside the
    # checkout), read alike on both sides: it cannot name pilot/ without the prefix, and is no pilot/runs/ path
    ("forward-slash-drive-spelling-default-root", {"pairs_file": "C:/engine/data/x.json"}, False),
    ("forward-slash-drive-spelling-pilot-root", {**PILOT, "pairs_file": "C:/engine/pilot/runs/p.json"}, True),
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


@pytest.mark.parametrize("cfg, needle", [
    ({**PILOT, "pairs_file": "pilot/p.json"}, "under pilot/runs/"),
    ({**PILOT, "pairs_file": "pilot/traces/p/x.json"}, "under pilot/runs/"),
    ({**PILOT, "pairs_file": RUN2_PAIRS}, "is not named for its run"),
    ({**PILOT, "pairs_file": "pilot/runs/run_a_p.json"}, "is not named for its run"),
    ({"pairs_file": "pilot\\runs\\p.json"}, "contains a backslash"),
    ({**PILOT, "pairs_file": "C:\\engine\\pilot\\runs\\p.json"}, "contains a backslash"),
], ids=["pilot-file-outside-runs", "pilot-traces-file", "run-2-legacy-name", "no-run-directory",
        "backslash-default-root", "drive-letter-pilot-root"])
def test_both_sides_name_the_pilot_runs_and_backslash_refusals(tmp_path, cfg, needle):
    _write_pairs(tmp_path)
    rc, _, err = _run_params(tmp_path, {"commit_outputs": "false", **cfg})
    assert rc != 0 and needle in err, err
    fire_problems = _fire_refuses(tmp_path, cfg)
    assert fire_problems and needle in " ".join(fire_problems), fire_problems


# the copy docs/triggers.md names for re-tracing run 2: its committed file under a name that carries the run id
RUN2_RENAMED = "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json"


def test_run_3s_pairs_file_is_accepted_and_run_2s_legacy_name_is_refused_for_a_new_fire(tmp_path):
    """Codex on PR #85: OUT_DIR is cut from the pairs file's stem alone, and run 2's file kept the name trace_pairs.py
    gave every run, so a later run's file of that name would have traced into run 2's pilot/traces/trace_pairs/ and
    replaced its parts; run 3's file had to be renamed by hand to avoid it. Run 3's fire config of 2026-10-04 is
    accepted on both sides, the same config over run 2's legacy name is refused on both, and a copy of run 2's file
    under its run-named name passes."""
    _write_pairs(tmp_path)
    (tmp_path / RUN2_RENAMED).write_text((tmp_path / RUN2_PAIRS).read_text(encoding="utf-8"), encoding="utf-8")
    cfg = {"mode": "2panel", "output_root": PILOT_ROOT, "graph_models": "gemma-2-2b", "offsets": "0,10,20,30",
           "sample_size": "10", "screen_targets": "0.02", "commit_outputs": "true"}
    for pairs in (RUN3_PAIRS, RUN2_RENAMED):
        rc, out, err = _run_params(tmp_path, {**cfg, "pairs_file": pairs})
        assert rc == 0, err
        config = json.loads(next(line for line in out.splitlines() if line.startswith("config="))[len("config="):])
        assert config["pairs_file"] == pairs and config["output_root"] == PILOT_ROOT
        assert _fire_refuses(tmp_path, {**cfg, "pairs_file": pairs}) == []
    rc, out, err = _run_params(tmp_path, {**cfg, "pairs_file": RUN2_PAIRS})
    assert rc != 0 and out == "" and "is not named for its run" in err, err
    problems = _fire_refuses(tmp_path, {**cfg, "pairs_file": RUN2_PAIRS})
    assert problems and "is not named for its run" in problems[0]
    assert "pilot_v2_20261002_trace_pairs.json" in problems[0], "the refusal names the copy that would pass"


def test_the_fire_path_names_the_pairs_it_would_screen_out(tmp_path):
    _write_pairs(tmp_path)
    problems = ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {**PILOT, "screen_targets": "0.02", "offsets": "0", "sample_size": "4"})
    assert len(problems) == 1 and "1 selected pair(s)" in problems[0] and "indices 4" in problems[0], problems
    # a missing pairs file is a named refusal, not a pass
    problems = ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_absent.json",
                                    "screen_targets": "0.02"})
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
    # the folder carries the run id because the pairs file's name does (the params job refuses any other name)
    assert _run_select(tmp_path, P_PAIRS, "gemma-2-2b", PILOT_ROOT) == "OUT_DIR=pilot/traces/run_a_p\n"
    assert _run_select(tmp_path, P_PAIRS, "qwen3-4b", PILOT_ROOT) == "OUT_DIR=pilot/traces/run_a_p__qwen3-4b\n"
    assert _run_select(tmp_path, RUN3_PAIRS, "gemma-2-2b", PILOT_ROOT) == (
        "OUT_DIR=pilot/traces/pilot_v3_20261004_trace_pairs\n")


def test_the_select_step_reads_the_root_from_the_resolved_config():
    step = _step("Select sample pairs")
    assert step["env"]["OUTPUT_ROOT"] == "${{ fromJson(needs.params.outputs.config).output_root }}"
    assert 'out_dir = f"trace_out/{stem}"' in step["run"], "the default path's text is unchanged"


# --- checkout, seal check, commit -------------------------------------------------------------------------------

def test_both_sparse_checkouts_take_pilot_runs_and_leave_pilot_traces_out():
    """Earlier pilot parts are committed under pilot/traces. Checking that tree out put them in a later cell's
    OUT_DIR (and the commit step's rebase wrote other cells' parts there), where the run-page summary and the
    artifact upload picked them up; so only pilot/runs, where pilot-root pairs files sit, is checked out, and
    pilot/traces stays out as trace_out/ does."""
    wf = _workflow()
    for job in ("params", "trace"):
        checkout = next(s for s in wf["jobs"][job]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
        cone = checkout["with"]["sparse-checkout"].split()
        assert [c for c in cone if c.strip("/").split("/")[0] == "pilot"] == ["pilot/runs"], (job, cone)
        assert not any(c.strip("/").split("/")[0] == "trace_out" for c in cone), (job, cone)
        assert {".github", "scripts", "data", "medlang_circuits", "docs", "ops", "tests"} <= set(cone), job
    assert ft.CIRCUIT_TRACE_PILOT_RUNS_PREFIX == "pilot/runs/", "the fire path requires the directory checked out"


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



PILOT_SEAL_GATE = ("${{ always() && (fromJson(needs.params.outputs.config).output_root != 'pilot/traces' "
                   "|| steps.seal.outcome == 'success') }}")


def test_a_pilot_cell_whose_seal_check_failed_publishes_neither_its_summary_nor_its_artifact():
    """The run page and the workflow artifact are publications too (petri_audit.yml gates its upload on its seal
    check the same way); the default root keeps running both after a failure, as `always()` did."""
    steps = _trace_steps()
    names = [str(s.get("name", "")) for s in steps]
    seal_at = next(i for i, s in enumerate(steps) if s.get("id") == "seal")
    for name in ("Publish summary to run page", "Upload trace outputs"):
        at = names.index(name)
        assert at > seal_at, name
        assert steps[at]["if"] == PILOT_SEAL_GATE, name


def test_the_seal_step_fails_when_the_pairs_file_is_absent(tmp_path):
    """seal_check.py reads a missing root as zero files and passes, so the step itself refuses a missing pairs
    file before the check runs (exit 1, no seal_check.py call)."""
    run = next(s for s in _trace_steps() if s.get("id") == "seal")["run"]
    assert run.index('test -f "$PAIRS_FILE"') < run.index("python scripts/seal_check.py")
    env = {**os.environ, "PAIRS_FILE": "pilot/runs/absent.json", "OUT_DIR": "pilot/traces/absent",
           "RUNNER_TEMP": str(tmp_path)}
    proc = subprocess.run(["bash", "-c", run], cwd=tmp_path, capture_output=True, text=True, env=env)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert "pairs file pilot/runs/absent.json not found" in proc.stdout


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
    # neither root's output directory is checked out, so the new part is staged outside the sparse checkout
    assert 'git add --sparse -f "${FILES[@]}"' in run


# --- run-page summary -------------------------------------------------------------------------------------------

def _run_summary(tmp_path: Path, offset: int, files: dict[str, str]) -> str:
    """Run the "Publish summary to run page" script as CI runs it (bash -e) over an OUT_DIR holding `files`, and
    return what it appended to the step summary."""
    out_dir = tmp_path / "pilot" / "traces" / "p"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    step_summary = tmp_path / "step_summary.md"
    step_summary.write_text("")
    env = {**os.environ, "OUT_DIR": "pilot/traces/p", "OFFSET": str(offset), "MODEL": "gemma-2-2b", "MODE": "2panel",
           "GITHUB_STEP_SUMMARY": str(step_summary)}
    proc = subprocess.run(["bash", "-e", "-c", _step("Publish summary to run page")["run"]], cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return step_summary.read_text(encoding="utf-8")


def test_the_run_page_summary_prints_this_cells_own_part_and_never_another(tmp_path):
    step = _step("Publish summary to run page")
    assert step["env"] == {"OFFSET": "${{ matrix.offset }}", "MODEL": "${{ matrix.model }}",
                           "MODE": "${{ fromJson(needs.params.outputs.config).mode }}"}
    others = {"batch_summary.part_01.json": '{"cell": "other-01"}',
              "batch_summary.part_21.json": '{"cell": "other-21"}'}
    # committed: the commit step renamed this cell's summary to part_NN, NN = offset + 1; other parts sort first
    shown = _run_summary(tmp_path, 10, {**others, "batch_summary.part_11.json": '{"cell": "this-11"}'})
    assert "## Circuit trace batch summary (gemma-2-2b, 2panel, offset 10)" in shown
    assert "this-11" in shown and "other" not in shown, shown
    # NN is zero-padded to two digits, as the commit step names it
    shown = _run_summary(tmp_path / "first", 0, {"batch_summary.part_01.json": '{"cell": "this-01"}',
                                                 "batch_summary.part_11.json": '{"cell": "other-11"}'})
    assert "this-01" in shown and "other" not in shown, shown


def test_the_run_page_summary_prints_an_uncommitted_summary_first(tmp_path):
    shown = _run_summary(tmp_path, 10, {"batch_summary.part_01.json": '{"cell": "other-01"}',
                                        "batch_summary.json": '{"cell": "this-uncommitted"}'})
    assert "this-uncommitted" in shown and "other" not in shown, shown


def test_the_run_page_summary_prints_nothing_rather_than_another_cells_part(tmp_path):
    assert _run_summary(tmp_path, 10, {"batch_summary.part_01.json": '{"cell": "other-01"}'}) == ""
    assert _run_summary(tmp_path / "empty", 0, {}) == ""
