"""The circuit-trace lane's opt-in pilot output root (`output_root`, 2026-10-01).

Pilot stimulus pairs are traced at $0 into pilot/traces/<run_id>/<stem>/ (the
run's own folder since 2026-10-05) so their outputs never enter trace_out/, where
every collector reads measurements. Three things are held here, each by running
or parsing what CI runs:

- the params job's push-path refusals (its python heredoc, run as CI runs it, the
  pattern of tests/test_petri_audit_params_heredoc.py) agree case for case with
  the fire-time refusals in scripts/fire_trigger.py; among them, a pilot pairs
  file sits in its run's trace/ directory and is named for its run, with no "__"
  in its name (pilot/runs/<run_id>/trace/<run_id>_<name>.json, 2026-10-04 and
  2026-10-05), a run id that names a flat pilot folder written before
  2026-10-05 is refused, and so is a value carrying a control character;
- the "Select sample pairs" heredoc writes OUT_DIR under the pilot root only when
  asked, in the run's own folder with the run id read as the fire path reads it,
  so two runs never share a folder and neither do two files or two models of one
  run, and leaves the default
  trace_out/<stem>[__<model>] path as it was;
- both jobs check out pilot/runs and never pilot/traces (where earlier pilot parts
  are committed), the trace job seal-checks a pilot cell before committing it,
  commits only its summary parts, commits nothing from a pilot cell whose seal check
  did not succeed, and prints only the cell's own summary part to the run page.

The pairs written here are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import ast
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
# a placeholder run, run_a, and its pairs files, in its trace/ directory and named for it
P_PAIRS = "pilot/runs/run_a/trace/run_a_p.json"
Q_PAIRS = "pilot/runs/run_a/trace/run_a_q.json"
# Codex on PR #85 (2026-10-05): run a's a_b_pairs.json and run a_b's a_b_pairs.json both pass the naming rule and share
# a stem, so a folder cut from the stem alone held both runs' parts; each now traces into its own run's folder
PREFIX_RUN_PAIRS = "pilot/runs/a/trace/a_b_pairs.json"
PREFIXED_RUN_PAIRS = "pilot/runs/a_b/trace/a_b_pairs.json"
# run 2's pairs under the run-named name, beside the legacy file: where trace_pairs.py's default writes them when re-run
# on run 2 (a byte-identical file), and what docs/triggers.md and the refusal tell a session to fire instead
RUN2_RUN_NAMED = "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json"


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
    # named for its run: pilot/runs/<run_id>/trace/<run_id>_<name>.json, the name read as given (OUT_DIR's stem is
    # cut from it) and the run id from the normalised path
    ("pilot-root-climbing-back-into-the-run", {**PILOT, "pairs_file": "pilot/runs/run_b/../run_a/trace/run_a_p.json"},
     False),
    ("pilot-root-pairs-directly-in-runs", {**PILOT, "pairs_file": "pilot/runs/run_a_p.json"}, True),
    ("pilot-root-pairs-not-named-for-the-run", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/p.json"}, True),
    ("pilot-root-pairs-named-for-another-run", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_b_p.json"}, True),
    ("pilot-root-climbing-into-another-run", {**PILOT, "pairs_file": "pilot/runs/run_b/../run_a/trace/run_b_p.json"},
     True),
    ("pilot-root-run-id-without-the-underscore", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_ap.json"}, True),
    ("pilot-root-run-id-alone", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_.json"}, True),
    ("pilot-root-name-starts-with-part-of-the-run-id", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_p.json"},
     True),
    ("pilot-root-not-a-json-name", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_p.txt"}, True),
    ("pilot-root-upper-case-suffix", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_p.JSON"}, True),
    ("pilot-root-trailing-dot", {**PILOT, "pairs_file": P_PAIRS + "/."}, True),
    ("pilot-root-trailing-slash", {**PILOT, "pairs_file": P_PAIRS + "/"}, True),
    # in its run's trace/ directory and nowhere else: the folder is pilot/traces/<run_id>/<stem>, so a file of one name
    # elsewhere in the run would trace into the trace/ file's folder (the independent check of 2026-10-05 found each)
    ("pilot-root-pairs-directly-in-the-run-directory", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_p.json"}, True),
    ("pilot-root-pairs-in-another-directory-of-the-run",
     {**PILOT, "pairs_file": "pilot/runs/run_a/other/run_a_p.json"}, True),
    ("pilot-root-pairs-below-trace", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/deeper/run_a_p.json"}, True),
    ("pilot-root-pairs-in-a-deeper-directory", {**PILOT, "pairs_file": "pilot/runs/run_a/x/y/run_a_p.json"}, True),
    ("pilot-root-trace-directory-in-another-case", {**PILOT, "pairs_file": "pilot/runs/run_a/Trace/run_a_p.json"},
     True),
    ("pilot-root-climbing-out-of-trace", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/../run_a_p.json"}, True),
    ("pilot-root-climbing-back-into-trace", {**PILOT, "pairs_file": "pilot/runs/run_a/other/../trace/run_a_p.json"},
     False),
    ("pilot-root-run-3s-file-directly-in-its-run-directory",
     {**PILOT, "pairs_file": "pilot/runs/pilot_v3_20261004/pilot_v3_20261004_trace_pairs.json"}, True),
    # no "__" in the name: the select step names a folder <stem>__<model>, so r_x__qwen3-4b.json traced with gemma-2-2b
    # would write the folder of r_x.json traced with qwen3-4b (the independent check of 2026-10-05)
    ("pilot-root-model-separator-in-the-name", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_p__qwen3-4b.json"},
     True),
    ("pilot-root-model-separator-after-the-run-id", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a__p.json"},
     True),
    ("pilot-root-model-separator-at-the-end", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_p__.json"}, True),
    ("pilot-root-model-separator-in-the-run-id", {**PILOT, "pairs_file": "pilot/runs/a__b/trace/a__b_p.json"}, True),
    ("pilot-root-single-underscores", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_p_q.json"}, False),
    # a run id is kept as given: Run_A is a run of its own, beside run_a
    ("pilot-root-upper-case-run-id", {**PILOT, "pairs_file": "pilot/runs/Run_A/trace/Run_A_p.json"}, False),
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
    ("pilot-root-comma-pairs", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_a,b.json"}, True),
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
    # each run traces into its own folder, pilot/traces/<run_id>/<stem>: run a's and run a_b's a_b_pairs.json (Codex on
    # PR #85) are both accepted, and land in two folders (test_two_runs_whose_pairs_files_share_a_stem_...)
    ("pilot-root-run-a-owns-a_b_pairs", {**PILOT, "pairs_file": PREFIX_RUN_PAIRS}, False),
    ("pilot-root-run-a_b-owns-a_b_pairs", {**PILOT, "pairs_file": PREFIXED_RUN_PAIRS}, False),
    ("pilot-root-run-2s-run-named-file", {**PILOT, "pairs_file": RUN2_RUN_NAMED}, False),
    # a run id that names a flat folder written before 2026-10-05 would trace into it, so it is refused
    ("pilot-root-run-id-is-run-2s-legacy-folder",
     {**PILOT, "pairs_file": "pilot/runs/trace_pairs/trace/trace_pairs_x.json"}, True),
    ("pilot-root-run-id-is-run-3s-legacy-folder",
     {**PILOT, "pairs_file": "pilot/runs/pilot_v3_20261004_trace_pairs/trace/pilot_v3_20261004_trace_pairs_x.json"},
     True),
    ("pilot-root-climbing-into-a-legacy-run-id",
     {**PILOT, "pairs_file": "pilot/runs/run_a/../trace_pairs/trace/trace_pairs_x.json"}, True),
    ("pilot-root-run-id-extends-a-legacy-name",
     {**PILOT, "pairs_file": "pilot/runs/trace_pairs_v2/trace/trace_pairs_v2_x.json"}, False),
    ("pilot-root-legacy-name-below-the-run-id", {**PILOT, "pairs_file": "pilot/runs/run_a/trace_pairs/run_a_p.json"},
     True),
    ("pilot-root-legacy-name-as-the-file-name",
     {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_trace_pairs.json"}, False),
    # path spellings the runner normalises: the run id is read from the normalised path, the name as given
    ("pilot-root-doubled-slashes", {**PILOT, "pairs_file": "pilot//runs//run_a//trace//run_a_p.json"}, False),
    ("pilot-root-dot-segments-inside-the-run", {**PILOT, "pairs_file": "pilot/runs/run_a/./x/../trace/run_a_p.json"},
     False),
    ("pilot-root-run-id-with-a-dot", {**PILOT, "pairs_file": "pilot/runs/run.a/trace/run.a_p.json"}, False),
    ("pilot-root-dot-run-directory", {**PILOT, "pairs_file": "pilot/runs/./run_a_p.json"}, True),
    ("pilot-root-climbing-out-of-runs", {**PILOT, "pairs_file": "pilot/runs/../runs_x/trace/runs_x_p.json"}, True),
    # a value carrying a control character is refused on both sides before anything is written (on main the params job
    # did not refuse one, 2026-10-05): the select step writes OUT_DIR=<folder> to $GITHUB_ENV from the pairs file's
    # name, so a newline there adds lines of its own and the last OUT_DIR wins
    ("newline-injects-out-dir-via-pilot-pairs",
     {**PILOT, "pairs_file": "pilot/runs/r\nOUT_DIR=trace_out\nQ=/trace/r\nOUT_DIR=trace_out\nQ=_x.json"}, True),
    ("newline-in-a-pilot-run-id", {**PILOT, "pairs_file": "pilot/runs/r\nQ=1/trace/r\nQ=1_x.json"}, True),
    ("newline-in-a-pilot-path-outside-trace", {**PILOT, "pairs_file": "pilot/runs/r\nQ=1/r\nQ=1_x.json"}, True),
    ("tab-in-a-pilot-run-id", {**PILOT, "pairs_file": "pilot/runs/r\tq/trace/r\tq_x.json"}, True),
    ("newline-injects-out-dir-default-root", {"pairs_file": "data/x\nOUT_DIR=pilot/traces/x.json"}, True),
    ("carriage-return-in-offsets", {"offsets": "0\r"}, True),
    ("delete-character-in-mode", {"mode": "2panel\x7f"}, True),
    ("newline-in-a-graph-models-element", {"graph_models": ["gemma-2-2b\nqwen3-4b"]}, True),
    ("vertical-tab-in-show-mitigation", {"show_mitigation": "false\x0b"}, True),
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
    ({**PILOT, "pairs_file": "pilot/runs/run_a_p.json"}, "is not in its run's trace/ directory"),
    ({**PILOT, "pairs_file": "pilot/runs/run_a/run_a_p.json"}, "is not in its run's trace/ directory"),
    ({**PILOT, "pairs_file": "pilot/runs/run_a/trace/deeper/run_a_p.json"}, "is not in its run's trace/ directory"),
    ({**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_b_p.json"}, "is not named for its run"),
    ({**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_p__qwen3-4b.json"}, "holds '__' in its name"),
    ({**PILOT, "pairs_file": "pilot/runs/r\nQ=1/trace/r\nQ=1_x.json"}, "control character"),
    ({"pairs_file": "pilot\\runs\\p.json"}, "contains a backslash"),
    ({**PILOT, "pairs_file": "C:\\engine\\pilot\\runs\\p.json"}, "contains a backslash"),
    # run 2's refusal names the run-named file to fire instead, and how to make it, on both sides
    ({**PILOT, "pairs_file": RUN2_PAIRS}, RUN2_RUN_NAMED),
    ({**PILOT, "pairs_file": RUN2_PAIRS}, "trace_pairs.py --run-dir pilot/runs/pilot_v2_20261002 --review-sample"),
    ({**PILOT, "pairs_file": "pilot/runs/trace_pairs/trace/trace_pairs_x.json"},
     "pilot output folder pilot/traces/trace_pairs/ written before 2026-10-05"),
    ({**PILOT, "pairs_file": "pilot/runs/pilot_v3_20261004_trace_pairs/trace/pilot_v3_20261004_trace_pairs_x.json"},
     "pilot output folder pilot/traces/pilot_v3_20261004_trace_pairs/ written before 2026-10-05"),
], ids=["pilot-file-outside-runs", "pilot-traces-file", "run-2-legacy-name", "no-run-directory",
        "file-directly-in-the-run", "file-below-trace", "named-for-another-run", "model-separator",
        "control-character", "backslash-default-root", "drive-letter-pilot-root", "run-2-run-named-file-named",
        "run-2-rebuild-command-named", "run-2-legacy-run-id",
        "run-3-legacy-run-id"])
def test_both_sides_name_the_pilot_runs_and_backslash_refusals(tmp_path, cfg, needle):
    _write_pairs(tmp_path)
    rc, _, err = _run_params(tmp_path, {"commit_outputs": "false", **cfg})
    assert rc != 0 and needle in err, err
    fire_problems = _fire_refuses(tmp_path, cfg)
    assert fire_problems and needle in " ".join(fire_problems), fire_problems


def test_run_3s_pairs_file_is_accepted_and_run_2s_legacy_name_is_refused_for_a_new_fire(tmp_path):
    """Codex on PR #85: OUT_DIR was cut from the pairs file's stem alone, and run 2's file kept the name trace_pairs.py
    gave every run, so a later run's file of that name would have traced into run 2's pilot/traces/trace_pairs/ and
    replaced its parts; run 3's file had to be renamed by hand to avoid it. Run 3's fire config of 2026-10-04 is
    accepted on both sides, the same config over run 2's legacy name is refused on both, and a copy of run 2's file
    beside it under the run-named name the refusal gives passes. Fired again, each traces into its run's own folder,
    never into the flat folder its parts landed in before 2026-10-05."""
    _write_pairs(tmp_path)
    (tmp_path / RUN2_RUN_NAMED).write_text((tmp_path / RUN2_PAIRS).read_text(encoding="utf-8"), encoding="utf-8")
    cfg = {"mode": "2panel", "output_root": PILOT_ROOT, "graph_models": "gemma-2-2b", "offsets": "0,10,20,30",
           "sample_size": "10", "screen_targets": "0.02", "commit_outputs": "true"}
    for pairs in (RUN3_PAIRS, RUN2_RUN_NAMED):
        rc, out, err = _run_params(tmp_path, {**cfg, "pairs_file": pairs})
        assert rc == 0, err
        config = json.loads(next(line for line in out.splitlines() if line.startswith("config="))[len("config="):])
        assert config["pairs_file"] == pairs and config["output_root"] == PILOT_ROOT
        assert _fire_refuses(tmp_path, {**cfg, "pairs_file": pairs}) == []
    rc, out, err = _run_params(tmp_path, {**cfg, "pairs_file": RUN2_PAIRS})
    assert rc != 0 and out == "" and "is not named for its run" in err, err
    assert RUN2_RUN_NAMED in err, "the params job names the run-named file to fire instead"
    problems = _fire_refuses(tmp_path, {**cfg, "pairs_file": RUN2_PAIRS})
    assert problems and "is not named for its run" in problems[0]
    assert RUN2_RUN_NAMED in problems[0], "the refusal names the file that would pass, beside the legacy one"
    assert ft.PILOT_RUN2_RUN_NAMED_PAIRS == RUN2_RUN_NAMED
    assert _run_select(tmp_path, RUN2_RUN_NAMED, "gemma-2-2b", PILOT_ROOT) == (
        "OUT_DIR=pilot/traces/pilot_v2_20261002/pilot_v2_20261002_trace_pairs\n")
    assert _run_select(tmp_path, RUN3_PAIRS, "gemma-2-2b", PILOT_ROOT) == (
        "OUT_DIR=pilot/traces/pilot_v3_20261004/pilot_v3_20261004_trace_pairs\n")


def test_the_fire_path_names_the_pairs_it_would_screen_out(tmp_path):
    _write_pairs(tmp_path)
    problems = ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {**PILOT, "screen_targets": "0.02", "offsets": "0", "sample_size": "4"})
    assert len(problems) == 1 and "1 selected pair(s)" in problems[0] and "indices 4" in problems[0], problems
    # a missing pairs file is a named refusal, not a pass
    problems = ft.circuit_trace_pilot_source_problems(
        tmp_path, "circuit-trace", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/run_a_absent.json",
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


def _run_dispatch(tmp_path: Path, inputs: dict[str, str]) -> tuple[int, str, str]:
    """Run the params heredoc on the dispatch path, as CI runs it, with these workflow_dispatch inputs."""
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("IN_")}
    env.update({"EVENT_NAME": "workflow_dispatch", "GITHUB_OUTPUT": str(out)})
    env.update({"IN_" + k.upper(): v for k, v in inputs.items()})
    proc = subprocess.run([sys.executable, "-"], input=_heredoc(_params_step()), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


DISPATCH_INPUTS = sorted(k[len("IN_"):].lower() for k in _params_step()["env"] if k.startswith("IN_"))


def test_a_clean_dispatch_resolves_and_writes_each_output_once(tmp_path):
    rc, out, err = _run_dispatch(tmp_path, {"pairs_file": "data/x.json", "offsets": "0,2"})
    assert rc == 0, err
    assert sorted(line.split("=", 1)[0] for line in out.splitlines()) == ["config", "models", "offsets"]


@pytest.mark.parametrize("key", DISPATCH_INPUTS)
def test_a_dispatch_input_carrying_a_newline_is_refused_with_nothing_written(tmp_path, key):
    """A dispatch never passes through scripts/fire_trigger.py, so the params job is the one place a control character
    is refused for it; the select step would otherwise write the value's lines to $GITHUB_ENV (through the pairs
    file's name). On main the params job refused none (2026-10-05)."""
    assert len(DISPATCH_INPUTS) == 13 and "pairs_file" in DISPATCH_INPUTS
    rc, out, err = _run_dispatch(tmp_path, {key: "1\nOUT_DIR=trace_out/x"})
    assert rc != 0 and out == "" and "must not carry a control character" in err, err


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


def test_the_pilot_root_writes_under_pilot_traces_in_the_runs_folder_with_the_model_suffix_rule(tmp_path):
    # pilot/traces/<run_id>/<stem>[__<model>] (2026-10-05): the run's own folder, the stem's rule as before
    assert _run_select(tmp_path, P_PAIRS, "gemma-2-2b", PILOT_ROOT) == "OUT_DIR=pilot/traces/run_a/run_a_p\n"
    assert _run_select(tmp_path, P_PAIRS, "qwen3-4b", PILOT_ROOT) == (
        "OUT_DIR=pilot/traces/run_a/run_a_p__qwen3-4b\n")
    assert _run_select(tmp_path, RUN3_PAIRS, "gemma-2-2b", PILOT_ROOT) == (
        "OUT_DIR=pilot/traces/pilot_v3_20261004/pilot_v3_20261004_trace_pairs\n")


def _write_pairs_at(base: Path, path: str) -> None:
    """One targeted pair at `path` as the runner would open it: every directory the given spelling passes through
    exists (a `..` climbs out of a real directory), and the file sits at the normalised path."""
    parts = path.split("/")
    for i in range(1, len(parts)):
        (base / posixpath.normpath("/".join(parts[:i]))).mkdir(parents=True, exist_ok=True)
    target = base / posixpath.normpath(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([_pair()]), encoding="utf-8")


ACCEPTED_PILOT_PATHS = sorted({c["pairs_file"] for _, c, refused in CASES
                               if not refused and c.get("output_root") == PILOT_ROOT})


def test_two_runs_whose_pairs_files_share_a_stem_trace_into_two_folders(tmp_path):
    """Codex on PR #85 (2026-10-05): with the folder cut from the stem alone, run a's a_b_pairs.json and run a_b's
    a_b_pairs.json both passed the naming rule and traced into one pilot/traces/a_b_pairs/, so a later fire at the
    same offset replaced the earlier run's part. Both are still accepted, on both sides, and now trace into two
    folders, for every model."""
    for pairs in (PREFIX_RUN_PAIRS, PREFIXED_RUN_PAIRS):
        _write_pairs_at(tmp_path, pairs)
        rc, _, err = _run_params(tmp_path, {**PILOT, "pairs_file": pairs, "commit_outputs": "false"})
        assert rc == 0 and _fire_refuses(tmp_path, {**PILOT, "pairs_file": pairs}) == [], err
    for model, suffix in (("gemma-2-2b", ""), ("qwen3-4b", "__qwen3-4b")):
        dirs = [_run_select(tmp_path, pairs, model, PILOT_ROOT) for pairs in (PREFIX_RUN_PAIRS, PREFIXED_RUN_PAIRS)]
        assert dirs == [f"OUT_DIR=pilot/traces/a/a_b_pairs{suffix}\n", f"OUT_DIR=pilot/traces/a_b/a_b_pairs{suffix}\n"]


GRAPH_MODELS = ("gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b")


def test_every_accepted_pilot_path_traces_into_its_runs_folder_as_the_fire_path_reads_the_run_id(tmp_path):
    """For each pilot pairs path the parity table accepts and each graph model, the select step's OUT_DIR is
    pilot/traces/<fire_trigger.pilot_run_id(path)>/<the given name's stem>[__<model>], so the folder's run id is the one
    the fire path and the params job checked. No folder is shared by two runs, nor within a run by two files (two
    normalised paths) or two models: the independent check of 2026-10-05 found pilot/runs/r/r_x.json,
    pilot/runs/r/other/r_x.json and pilot/runs/r/trace/deeper/r_x.json each tracing into pilot/runs/r/trace/r_x.json's
    folder, and r_x__qwen3-4b.json traced with gemma-2-2b into r_x.json's qwen3-4b folder; the table refuses each."""
    assert {PREFIX_RUN_PAIRS, PREFIXED_RUN_PAIRS, RUN3_PAIRS, RUN2_RUN_NAMED, P_PAIRS, Q_PAIRS} <= set(
        ACCEPTED_PILOT_PATHS)
    files_per_run: dict[str, set[str]] = {}
    for path in ACCEPTED_PILOT_PATHS:
        files_per_run.setdefault(ft.pilot_run_id(path), set()).add(posixpath.normpath(path))
    assert max(len(files) for files in files_per_run.values()) >= 2, "some run has two files, so within-run is tested"
    seen_run: dict[str, str] = {}
    seen_cell: dict[str, tuple[str, str]] = {}
    for path in ACCEPTED_PILOT_PATHS:
        _write_pairs_at(tmp_path, path)
        run_id = ft.pilot_run_id(path)
        stem = posixpath.splitext(posixpath.basename(path))[0]
        assert run_id and run_id not in ft.PILOT_LEGACY_OUTPUT_FOLDERS, path
        for model in GRAPH_MODELS:
            out_dir = _run_select(tmp_path, path, model, PILOT_ROOT)
            suffix = "" if model == "gemma-2-2b" else f"__{model}"
            assert out_dir == f"OUT_DIR=pilot/traces/{run_id}/{stem}{suffix}\n", (path, model)
            assert seen_run.setdefault(out_dir, run_id) == run_id, f"{path} shares {out_dir} with run {seen_run[out_dir]}"
            cell = (posixpath.normpath(path), model)
            assert seen_cell.setdefault(out_dir, cell) == cell, f"{cell} shares {out_dir} with {seen_cell[out_dir]}"


def test_the_run_ids_case_is_kept_in_the_output_folder(tmp_path):
    """A run id is read and written as given, so Run_A is a run of its own, beside run_a; the independent check's
    mutant that lower-cased the run id in the select step passed every other test. (On a case-insensitive disk, such
    as a default macOS checkout, the two runs' folders would be one; the runner's is case-sensitive.)"""
    upper = "pilot/runs/Run_A/trace/Run_A_p.json"
    for pairs in (upper, P_PAIRS):
        _write_pairs_at(tmp_path, pairs)
        rc, _, err = _run_params(tmp_path, {**PILOT, "pairs_file": pairs, "commit_outputs": "false"})
        assert rc == 0 and _fire_refuses(tmp_path, {**PILOT, "pairs_file": pairs}) == [], err
    assert ft.pilot_run_id(upper) == "Run_A"
    assert _run_select(tmp_path, upper, "gemma-2-2b", PILOT_ROOT) == "OUT_DIR=pilot/traces/Run_A/Run_A_p\n"
    assert _run_select(tmp_path, upper, "qwen3-4b", PILOT_ROOT) == "OUT_DIR=pilot/traces/Run_A/Run_A_p__qwen3-4b\n"
    assert _run_select(tmp_path, P_PAIRS, "gemma-2-2b", PILOT_ROOT) == "OUT_DIR=pilot/traces/run_a/run_a_p\n"


@pytest.mark.parametrize("path, run_id", [
    ("pilot/runs/r/r_x.json", "r"), ("pilot/runs/r/trace/deeper/r_x.json", "r"), ("./pilot/runs/r/r_x.json", "r"),
    ("pilot//runs/r//r_x.json", "r"), ("pilot/runs/s/../r/r_x.json", "r"), ("pilot/runs/r/x/../r_x.json", "r"),
    ("pilot/runs/r_x.json", ""), ("pilot/runs/./r_x.json", ""), ("pilot/runs", ""), ("pilot/runs/r", ""),
    ("pilot/other/r/r_x.json", ""), ("data/runs/r/r_x.json", ""), ("pilot/runs/../traces/r/r_x.json", ""),
])
def test_the_run_id_is_the_directory_directly_under_pilot_runs_of_the_normalised_path(path, run_id):
    assert ft.pilot_run_id(path) == run_id


@pytest.mark.parametrize("pairs", ["pilot/runs/run_a_p.json", "pilot/runs/./run_a_p.json", "pilot/p.json",
                                   "pilot/other/run_a/run_a_p.json"])
def test_the_select_step_refuses_a_pilot_path_without_a_run_directory(tmp_path, pairs):
    """The params job never admits such a path under the pilot root; the select step refuses it too rather than
    write a folder directly under pilot/traces/."""
    _write_pairs_at(tmp_path, pairs)
    gh_env = tmp_path / "gh_env"
    gh_env.write_text("")
    env = {**os.environ, "MODE": "2panel", "SAMPLE_SIZE": "1", "PAIRS_FILE": pairs, "GRAPH_MODEL": "gemma-2-2b",
           "OFFSET": "0", "GITHUB_ENV": str(gh_env), "OUTPUT_ROOT": PILOT_ROOT}
    proc = subprocess.run([sys.executable, "-"], input=_heredoc(_step("Select sample pairs")), cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    assert proc.returncode != 0 and "is not under pilot/runs/<run_id>/" in proc.stderr, proc.stderr
    assert gh_env.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize("legacy", sorted(ft.PILOT_LEGACY_OUTPUT_FOLDERS))
def test_both_sides_refuse_every_legacy_folder_name_as_a_run_id(tmp_path, legacy):
    """Each name on the fire path's list is refused on both sides, with the same reason. A name on the params job's
    list alone is not exercised here: test_the_params_jobs_legacy_list_is_the_fire_paths parses that list."""
    pairs = f"pilot/runs/{legacy}/trace/{legacy}_x.json"
    _write_pairs_at(tmp_path, pairs)
    rc, out, err = _run_params(tmp_path, {**PILOT, "pairs_file": pairs, "commit_outputs": "false"})
    assert rc != 0 and out == "" and f"pilot/traces/{legacy}/ written before 2026-10-05" in err, err
    problems = _fire_refuses(tmp_path, {**PILOT, "pairs_file": pairs})
    assert problems and f"pilot/traces/{legacy}/ written before 2026-10-05" in problems[0], problems


def _heredoc_legacy_names(heredoc: str) -> tuple[str, ...]:
    """The run ids a params heredoc refuses as legacy folder names, read from its one `elif run_id in (...)` line."""
    found = re.findall(r"elif run_id in (\([^)]*\)):", heredoc)
    assert len(found) == 1, found
    names = ast.literal_eval(found[0])
    assert isinstance(names, tuple) and all(isinstance(n, str) for n in names), names
    return names


def test_the_params_jobs_legacy_list_is_the_fire_paths():
    """The params job's list, parsed from its heredoc, equals the fire path's as a set, with no name twice. The
    behavioural test above tries only the fire path's names, so a name added to the workflow alone would have passed
    it (the independent check's mutant D, 2026-10-05)."""
    names = _heredoc_legacy_names(_heredoc(_params_step()))
    assert len(names) == len(set(names)), names
    assert set(names) == set(ft.PILOT_LEGACY_OUTPUT_FOLDERS)


def test_the_legacy_folder_list_names_every_flat_pilot_trace_folder_in_the_tree():
    """Every folder directly under pilot/traces/ that holds summary parts of its own is a flat folder from before
    the per-run layout and is listed, so no run id can name one; a new-layout folder, pilot/traces/<run_id>/, holds
    none directly. Read from git, so it holds for whichever of those folders this checkout carries (run 3's landed on
    main with PR #84), and it fails if a pilot trace fired from a branch without the per-run layout lands a new flat
    folder that the list does not name."""
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "pilot/traces"], capture_output=True, text=True,
                             check=True).stdout.split()
    flat = {f.split("/")[2] for f in tracked
            if len(f.split("/")) == 4 and f.split("/")[3].startswith("batch_summary")}
    assert flat, "run 2's parts at pilot/traces/trace_pairs/ are committed"
    assert flat <= set(ft.PILOT_LEGACY_OUTPUT_FOLDERS), flat - set(ft.PILOT_LEGACY_OUTPUT_FOLDERS)


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
