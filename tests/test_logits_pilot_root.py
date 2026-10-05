"""The logits-eval lane's opt-in pilot output root (`output_root`, 2026-10-04).

Circuit-trace's pilot root (tests/test_circuit_trace_pilot_root.py) carried over to the CPU next-token lane: pilot
stimulus pairs under pilot/runs/ are measured by the open-weight models at $0 into
pilot/logits/<run_id>/<stem>__<model>/ (the run's own folder), so their outputs never enter trace_out/, where every
collector reads measurements. Each thing is held by running or parsing what CI runs:

- the params job's push-path refusals (its python heredoc, run as CI runs it) agree case for case with the fire-time
  refusals in scripts/fire_trigger.py, and a refused config writes no job outputs; among them, a pilot pairs file is
  named for its run (pilot/runs/<run_id>/.../<run_id>_<name>.json, 2026-10-04), and a run id that names one of
  circuit-trace's flat pilot folders from before 2026-10-05 is refused, as there;
- the "Resolve output dir" step writes OUT_DIR under the pilot root only when asked, in the run's own folder with the
  run id read as the fire path reads it, so two runs never share a folder, and leaves the default root's three paths
  (logits, depth, verify) as they were;
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
# the pairs file of the circuit-trace pilot fire of 2026-10-02 (pilot run 2's review sample), named before pilot pairs
# files were named for their run: its parts stay at pilot/traces/trace_pairs/, and a new fire of it is refused
RUN2_PAIRS = "pilot/runs/pilot_v2_20261002/trace/trace_pairs.json"
# the pairs file of the circuit-trace pilot fire of 2026-10-04 (pilot run 3's review sample, PR #84), renamed by hand
# for its run so its parts would not land in run 2's folder: the shape every later pilot pairs file takes, accepted
RUN3_PAIRS = "pilot/runs/pilot_v3_20261004/trace/pilot_v3_20261004_trace_pairs.json"


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
# a placeholder run, run_a, and its pairs file, named for it
PILOT_PAIRS = "pilot/runs/run_a/run_a_pairs.json"
PILOT = {"output_root": PILOT_ROOT, "pairs_file": PILOT_PAIRS}
# Codex on PR #85 (2026-10-05): run a's a_b_pairs.json and run a_b's a_b_pairs.json both pass the naming rule and share
# a stem, so a folder cut from the stem alone held both runs' parts; each now measures into its own run's folder
PREFIX_RUN_PAIRS = "pilot/runs/a/a_b_pairs.json"
PREFIXED_RUN_PAIRS = "pilot/runs/a_b/a_b_pairs.json"
# run 2's pairs under the run-named name, beside the legacy file: where trace_pairs.py's default writes them when re-run
# on run 2 (a byte-identical file), and what docs/triggers.md and the refusal tell a session to fire instead
RUN2_RUN_NAMED = "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json"

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
    ("pilot-root-dotted-runs-pairs", {**PILOT, "pairs_file": "./" + PILOT_PAIRS}, False),
    ("pilot-root-list-of-models", {**PILOT, "models": ["qwen3-4b", "qwen3-1.7b"]}, False),
    ("pilot-root-chunked", {**PILOT, "limit": 10, "offset": 20}, False),
    ("pilot-root-the-run-3-review-sample", {"models": "qwen3-4b qwen3-1.7b", "pairs_file": RUN3_PAIRS,
                                            "output_root": PILOT_ROOT, "limit": "0", "offset": "0",
                                            "commit_outputs": "true"}, False),
    ("pilot-root-the-run-2-review-sample", {"models": "qwen3-4b qwen3-1.7b", "pairs_file": RUN2_PAIRS,
                                            "output_root": PILOT_ROOT, "limit": "0", "offset": "0",
                                            "commit_outputs": "true"}, True),
    # named for its run: pilot/runs/<run_id>/.../<run_id>_<name>.json, the name read as given (OUT_DIR's stem is cut
    # from it) and the run id from the normalised path
    ("pilot-root-pairs-in-a-deeper-directory", {**PILOT, "pairs_file": "pilot/runs/run_a/x/y/run_a_pairs.json"}, False),
    ("pilot-root-climbing-back-into-the-run", {**PILOT, "pairs_file": "pilot/runs/run_b/../run_a/run_a_pairs.json"},
     False),
    ("pilot-root-pairs-directly-in-runs", {**PILOT, "pairs_file": "pilot/runs/run_a_pairs.json"}, True),
    ("pilot-root-pairs-not-named-for-the-run", {**PILOT, "pairs_file": "pilot/runs/run_a/trace/pairs.json"}, True),
    ("pilot-root-pairs-named-for-another-run", {**PILOT, "pairs_file": "pilot/runs/run_a/run_b_pairs.json"}, True),
    ("pilot-root-climbing-into-another-run", {**PILOT, "pairs_file": "pilot/runs/run_b/../run_a/run_b_pairs.json"},
     True),
    ("pilot-root-run-id-without-the-underscore", {**PILOT, "pairs_file": "pilot/runs/run_a/run_apairs.json"}, True),
    ("pilot-root-run-id-alone", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_.json"}, True),
    ("pilot-root-name-starts-with-part-of-the-run-id", {**PILOT, "pairs_file": "pilot/runs/run_a/run_pairs.json"},
     True),
    ("pilot-root-not-a-json-name", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_pairs.txt"}, True),
    ("pilot-root-upper-case-suffix", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_pairs.JSON"}, True),
    ("pilot-root-trailing-dot", {**PILOT, "pairs_file": PILOT_PAIRS + "/."}, True),
    ("pilot-root-trailing-slash", {**PILOT, "pairs_file": PILOT_PAIRS + "/"}, True),
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
    # with / separators a drive spelling is a relative name on the Linux runner, read alike on both sides
    ("forward-slash-drive-spelling-default-root", {"pairs_file": "C:/engine/data/x.json"}, False),
    ("forward-slash-drive-spelling-pilot-root", {**PILOT, "pairs_file": "C:/engine/pilot/runs/p.json"}, True),
    # every resolved value is written as one `key=value` line and a later duplicate key wins, so a value carrying a
    # newline (or any control character, as fire_trigger.control_char_values reads one) is refused on both sides
    # before anything is written: otherwise it would add key=value lines after the checks had passed
    ("newline-injects-pilot-pairs-default-root", {"pairs_file": "data/x.json\npairs_file=pilot/runs/p.json"}, True),
    ("newline-injects-the-pilot-root-via-dtype", {"dtype": "float32\noutput_root=pilot/logits"}, True),
    ("newline-injects-commit-outputs", {"commit_outputs": "false\ncommit_outputs=true"}, True),
    ("newline-in-a-model-list-element", {"models": ["qwen3-1.7b\noutput_root=pilot/logits"]}, True),
    ("newline-in-mode-under-pilot-root", {**PILOT, "mode": "logits\npairs_file=data/x.json"}, True),
    ("carriage-return-in-limit", {"limit": "1\r"}, True),
    ("tab-in-models", {"models": "qwen3-1.7b\tqwen3-4b"}, True),
    ("delete-character-in-layers", {"layers": "all\x7f"}, True),
    ("control-character-in-pilot-pairs", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_p\x0b.json"}, True),
    # each run measures into its own folder, pilot/logits/<run_id>/<stem>__<model>: run a's and run a_b's
    # a_b_pairs.json (Codex on PR #85) are both accepted, and land in two folders
    ("pilot-root-run-a-owns-a_b_pairs", {**PILOT, "pairs_file": PREFIX_RUN_PAIRS}, False),
    ("pilot-root-run-a_b-owns-a_b_pairs", {**PILOT, "pairs_file": PREFIXED_RUN_PAIRS}, False),
    ("pilot-root-run-2s-run-named-file", {**PILOT, "pairs_file": RUN2_RUN_NAMED}, False),
    # a run id that names one of circuit-trace's flat folders from before 2026-10-05 is refused here too, so a run id
    # is usable on both pilot lanes or on neither
    ("pilot-root-run-id-is-run-2s-legacy-folder", {**PILOT, "pairs_file": "pilot/runs/trace_pairs/trace_pairs_x.json"},
     True),
    ("pilot-root-run-id-is-run-3s-legacy-folder",
     {**PILOT, "pairs_file": "pilot/runs/pilot_v3_20261004_trace_pairs/trace/pilot_v3_20261004_trace_pairs_x.json"},
     True),
    ("pilot-root-climbing-into-a-legacy-run-id",
     {**PILOT, "pairs_file": "pilot/runs/run_a/../trace_pairs/trace_pairs_x.json"}, True),
    ("pilot-root-run-id-extends-a-legacy-name",
     {**PILOT, "pairs_file": "pilot/runs/trace_pairs_v2/trace_pairs_v2_x.json"}, False),
    ("pilot-root-legacy-name-below-the-run-id",
     {**PILOT, "pairs_file": "pilot/runs/run_a/trace_pairs/run_a_pairs.json"}, False),
    ("pilot-root-legacy-name-as-the-file-name", {**PILOT, "pairs_file": "pilot/runs/run_a/run_a_trace_pairs.json"},
     False),
    # path spellings the runner normalises: the run id is read from the normalised path, the name as given
    ("pilot-root-doubled-slashes", {**PILOT, "pairs_file": "pilot//runs//run_a//run_a_pairs.json"}, False),
    ("pilot-root-dot-segments-inside-the-run", {**PILOT, "pairs_file": "pilot/runs/run_a/./x/../run_a_pairs.json"},
     False),
    ("pilot-root-run-id-with-a-dot", {**PILOT, "pairs_file": "pilot/runs/run.a/run.a_pairs.json"}, False),
    ("pilot-root-dot-run-directory", {**PILOT, "pairs_file": "pilot/runs/./run_a_pairs.json"}, True),
    ("pilot-root-climbing-out-of-runs", {**PILOT, "pairs_file": "pilot/runs/../runs_x/runs_x_pairs.json"}, True),
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
    ({**PILOT, "pairs_file": "pilot/runs/run_a/run_a_a,b.json"}, "contains a comma"),
    ({**PILOT, "pairs_file": RUN2_PAIRS}, "is not named for its run"),
    ({**PILOT, "pairs_file": "pilot/runs/run_a_pairs.json"}, "is not named for its run"),
    ({**PILOT, "output_root": "pilot/traces"}, "or 'pilot/logits' is accepted"),
    ({"pairs_file": "pilot\\runs\\p.json"}, "contains a backslash"),
    ({"pairs_file": "/abs/pilot/runs/p.json"}, "is absolute or leaves the checkout"),
    ({"pairs_file": "data/x.json\npairs_file=pilot/runs/p.json"}, "control character"),
    # run 2's refusal names the run-named file to fire instead, and how to make it, on both sides
    ({**PILOT, "pairs_file": RUN2_PAIRS}, RUN2_RUN_NAMED),
    ({**PILOT, "pairs_file": RUN2_PAIRS}, "trace_pairs.py --run-dir pilot/runs/pilot_v2_20261002 --review-sample"),
    ({**PILOT, "pairs_file": "pilot/runs/trace_pairs/trace_pairs_x.json"},
     "pilot output folder pilot/traces/trace_pairs/ written before 2026-10-05"),
    ({**PILOT, "pairs_file": "pilot/runs/pilot_v3_20261004_trace_pairs/pilot_v3_20261004_trace_pairs_x.json"},
     "pilot output folder pilot/traces/pilot_v3_20261004_trace_pairs/ written before 2026-10-05"),
], ids=["pilot-pairs-default-root", "pilot-file-outside-runs", "pilot-logits-file", "depth-mode", "comma",
        "run-2-legacy-name", "no-run-directory", "circuit-trace-root", "backslash", "absolute", "newline",
        "run-2-run-named-file-named", "run-2-rebuild-command-named", "run-2-legacy-run-id", "run-3-legacy-run-id"])
def test_both_sides_name_the_refusal(tmp_path, cfg, needle):
    full = {**BASE, **cfg}
    rc, _, err = _run_params(tmp_path, full)
    assert rc != 0 and needle in err, err
    fire_problems = _fire_refuses(full)
    assert fire_problems and needle in " ".join(fire_problems), fire_problems


def test_run_3s_pairs_file_is_accepted_and_run_2s_legacy_name_is_refused_for_a_new_fire(tmp_path):
    """Codex on PR #85: the pilot folder was cut from the pairs file's stem alone, and run 2's file kept the name
    trace_pairs.py gave every run, so a later run's file of that name would have measured into the same
    pilot/logits/trace_pairs__<model>/. Run 3's file, renamed for its run by hand, is the shape now required; run 2's
    legacy name is refused on both sides, and the run-named file beside it that the refusal names passes. Each
    measures into its run's own folder."""
    cfg = {"models": ["qwen3-4b", "qwen3-1.7b"], "output_root": PILOT_ROOT, "limit": "0", "offset": "0",
           "commit_outputs": "true"}
    for pairs in (RUN3_PAIRS, RUN2_RUN_NAMED):
        rc, out, err = _run_params(tmp_path / pairs.split("/")[2], {**cfg, "pairs_file": pairs})
        assert rc == 0, err
        assert _outputs(out)["pairs_file"] == pairs and _outputs(out)["output_root"] == PILOT_ROOT
        assert _fire_refuses({**cfg, "pairs_file": pairs}) == []
    rc, out, err = _run_params(tmp_path / "legacy", {**cfg, "pairs_file": RUN2_PAIRS})
    assert rc != 0 and out == "" and "is not named for its run" in err, err
    assert RUN2_RUN_NAMED in err, "the params job names the run-named file to fire instead"
    problems = _fire_refuses({**cfg, "pairs_file": RUN2_PAIRS})
    assert problems and "is not named for its run" in problems[0]
    assert RUN2_RUN_NAMED in problems[0], "the refusal names the file that would pass, beside the legacy one"
    for pairs, run in ((RUN3_PAIRS, "pilot_v3_20261004"), (RUN2_RUN_NAMED, "pilot_v2_20261002")):
        rc, env, log = _run_resolve(tmp_path / f"resolve_{run}", "logits", PILOT_ROOT, pairs_file=pairs,
                                    model="qwen3-4b", offset="0")
        assert rc == 0, log
        stem = pairs.rsplit("/", 1)[1][:-len(".json")]
        assert f"OUT_DIR=pilot/logits/{run}/{stem}__qwen3-4b\n" in env


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


def _dispatch_keys() -> list[str]:
    """The keys a workflow_dispatch can set: the params step reads each from an IN_<KEY> env var."""
    return [k[len("IN_"):].lower() for k in _params_step()["env"] if k.startswith("IN_")]


# a clean value for every dispatch input, so each test varies one input only
DISPATCH_CLEAN = {"models": "qwen3-1.7b", "pairs_file": "data/x.json", "limit": "0", "offset": "0",
                  "commit_outputs": "false", "mode": "logits", "layers": "all", "topk": "10", "dtype": "float32"}


def _run_dispatch(tmp_path: Path, inputs: dict[str, str]) -> tuple[int, str, str]:
    """Run the params heredoc on the workflow_dispatch path, as CI runs it, with these form (or API) inputs. A
    dispatch never passes through scripts/fire_trigger.py, so the params job is its only guard."""
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("IN_")}
    env.update({"EVENT_NAME": "workflow_dispatch", "GITHUB_OUTPUT": str(out)})
    env.update({"IN_" + k.upper(): v for k, v in inputs.items()})
    proc = subprocess.run([sys.executable, "-"], input=_params_heredoc(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


def test_the_dispatch_inputs_are_the_keys_these_tests_cover():
    assert sorted(_dispatch_keys()) == sorted(DISPATCH_CLEAN)


def test_a_dispatch_of_pilot_pairs_is_refused_too(tmp_path):
    """The dispatch path reads the form inputs, of which output_root is none, so a pilot pairs file given there is
    refused rather than measured into trace_out/."""
    rc, out, err = _run_dispatch(tmp_path, {"models": "qwen3-1.7b", "pairs_file": "pilot/runs/p.json"})
    assert rc != 0 and "is under pilot/" in err, err
    assert out == ""


def test_a_clean_dispatch_writes_each_output_once(tmp_path):
    rc, out, err = _run_dispatch(tmp_path, DISPATCH_CLEAN)
    assert rc == 0, err
    keys = [line.split("=", 1)[0] for line in out.splitlines()]
    assert sorted(keys) == sorted([*DISPATCH_CLEAN, "output_root"]), out
    assert _outputs(out)["pairs_file"] == "data/x.json" and _outputs(out)["output_root"] == ""


def test_a_dispatch_pairs_file_cannot_inject_pilot_pairs_with_a_newline(tmp_path):
    """The reproduction of 2026-10-04: through the API (the form takes one line) a dispatch pairs_file of a study path,
    a newline and a second pairs_file= line passed the pilot/ refusal, which read the whole string, and wrote two
    pairs_file lines. Read later-wins, the eval job would have measured run 2's pilot pairs into trace_out/."""
    rc, out, err = _run_dispatch(tmp_path, {**DISPATCH_CLEAN, "commit_outputs": "true",
                                            "pairs_file": "data/x.json\npairs_file=" + RUN2_PAIRS})
    assert rc != 0, (out, err)
    assert "pairs_file must not carry a control character" in err, err
    assert out == "", "a refused dispatch writes no outputs, so no eval job starts"


@pytest.mark.parametrize("key", sorted(DISPATCH_CLEAN))
def test_no_dispatch_input_can_add_an_output_line(tmp_path, key):
    """Every input, not only pairs_file: each is written as its own key=value line, so any of them could carry an
    injected pairs_file (or commit_outputs, or output_root) line."""
    rc, out, err = _run_dispatch(tmp_path, {**DISPATCH_CLEAN, key: DISPATCH_CLEAN[key] + "\npairs_file=pilot/runs/p.json"})
    assert rc != 0, (out, err)
    assert f"{key} must not carry a control character" in err, err
    assert out == ""


@pytest.mark.parametrize("char", ["\n", "\r", "\t", "\x0b", "\x1b", "\x7f"],
                         ids=["newline", "carriage-return", "tab", "vertical-tab", "escape", "delete"])
def test_every_control_character_is_refused_on_dispatch(tmp_path, char):
    """The same set fire_trigger.control_char_values refuses: below code point 32, and 127. (NUL is left out: no
    environment variable can carry one, on the runner or here.)"""
    rc, out, err = _run_dispatch(tmp_path, {**DISPATCH_CLEAN, "pairs_file": f"data/x{char}.json"})
    assert rc != 0 and "must not carry a control character" in err, err
    assert out == ""
    assert ft.control_char_values({"pairs_file": f"data/x{char}.json"}) == ["pairs_file"]


@pytest.mark.parametrize("path", ["push", "dispatch"])
def test_an_unknown_mode_is_refused_before_any_output_is_written(tmp_path, path):
    """The mode check ran after the writes until 2026-10-04; it now runs before them, as every other check does."""
    if path == "push":
        rc, out, err = _run_params(tmp_path, {**BASE, "pairs_file": "data/x.json", "mode": "spread"})
    else:
        rc, out, err = _run_dispatch(tmp_path, {**DISPATCH_CLEAN, "mode": "spread"})
    assert rc != 0 and "mode must be 'logits', 'depth' or 'verify'" in err, err
    assert out == ""


# --- Resolve output dir -----------------------------------------------------------------------------------------

def _run_resolve(tmp_path: Path, mode: str, root: str | None, pairs_file: str = "data/simulated/pairs_X.json",
                 model: str = "qwen3-4b", offset: str = "10", topk: str = "10") -> tuple[int, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    gh_env = tmp_path / "gh_env"
    gh_env.write_text("")
    # `python` on PATH is this interpreter, as setup-python makes it on the runner (the pilot branch reads the run id
    # with it)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    if not (bindir / "python").exists():
        (bindir / "python").symlink_to(sys.executable)
    env = {**os.environ, "MODEL": model, "PAIRS_FILE": pairs_file, "OFFSET": offset, "MODE": mode, "TOPK": topk,
           "GITHUB_ENV": str(gh_env), "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
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


def test_the_pilot_root_writes_under_pilot_logits_in_the_runs_folder_with_the_model_suffix(tmp_path):
    """pilot/logits/<run_id>/<stem>__<model> (the run's own folder; every logits-eval folder carries the model)."""
    rc, env, log = _run_resolve(tmp_path, "logits", PILOT_ROOT, pairs_file=RUN3_PAIRS, model="qwen3-1.7b", offset="0")
    assert rc == 0, log
    assert env == ("PART=part_01\nOUT_DIR=pilot/logits/pilot_v3_20261004/pilot_v3_20261004_trace_pairs__qwen3-1.7b\n"
                   "SUMMARY_FILE=batch_summary.part_01.json\n")


def test_two_runs_whose_pairs_files_share_a_stem_measure_into_two_folders(tmp_path):
    """Codex on PR #85 (2026-10-05): with the folder cut from the stem alone, run a's a_b_pairs.json and run a_b's
    a_b_pairs.json both passed the naming rule and measured into one pilot/logits/a_b_pairs__<model>/, so a later fire
    at the same offset replaced the earlier run's part. Both are still accepted, on both sides, and now measure into
    two folders."""
    dirs = []
    for pairs in (PREFIX_RUN_PAIRS, PREFIXED_RUN_PAIRS):
        rc, _, err = _run_params(tmp_path / "params", {**BASE, **PILOT, "pairs_file": pairs})
        assert rc == 0 and _fire_refuses({**BASE, **PILOT, "pairs_file": pairs}) == [], err
        rc, env, log = _run_resolve(tmp_path / "resolve", "logits", PILOT_ROOT, pairs_file=pairs, offset="0")
        assert rc == 0, log
        dirs.append(next(line for line in env.splitlines() if line.startswith("OUT_DIR=")))
    assert dirs == ["OUT_DIR=pilot/logits/a/a_b_pairs__qwen3-4b", "OUT_DIR=pilot/logits/a_b/a_b_pairs__qwen3-4b"]


ACCEPTED_PILOT_PATHS = sorted({c["pairs_file"] for _, c, refused in CASES
                               if not refused and c.get("output_root") == PILOT_ROOT})


def test_every_accepted_pilot_path_measures_into_its_runs_folder_as_the_fire_path_reads_the_run_id(tmp_path):
    """For each pilot pairs path the parity table accepts, the resolve step's OUT_DIR is
    pilot/logits/<fire_trigger.pilot_run_id(path)>/<the given name's stem>__<model>, so the folder's run id is the one
    the fire path and the params job checked; and paths of different runs never share a folder."""
    assert {PREFIX_RUN_PAIRS, PREFIXED_RUN_PAIRS, RUN3_PAIRS, RUN2_RUN_NAMED} <= set(ACCEPTED_PILOT_PATHS)
    seen: dict[str, str] = {}
    for i, path in enumerate(ACCEPTED_PILOT_PATHS):
        run_id = ft.pilot_run_id(path)
        stem = path.rsplit("/", 1)[1][:-len(".json")]
        assert run_id and run_id not in ft.PILOT_LEGACY_OUTPUT_FOLDERS, path
        rc, env, log = _run_resolve(tmp_path / str(i), "logits", PILOT_ROOT, pairs_file=path, model="qwen3-1.7b",
                                    offset="0")
        assert rc == 0, log
        out_dir = next(line for line in env.splitlines() if line.startswith("OUT_DIR="))
        assert out_dir == f"OUT_DIR=pilot/logits/{run_id}/{stem}__qwen3-1.7b", path
        assert seen.setdefault(out_dir, run_id) == run_id, f"{path} shares {out_dir} with run {seen[out_dir]}"


@pytest.mark.parametrize("pairs", ["pilot/runs/run_a_pairs.json", "pilot/runs/./run_a_pairs.json", "pilot/p.json",
                                   "pilot/other/run_a/run_a_pairs.json", "data/simulated/pairs_X.json"])
def test_the_resolve_step_refuses_a_pilot_path_without_a_run_directory(tmp_path, pairs):
    """The params job never admits such a path under the pilot root; the resolve step refuses it too rather than
    write a folder directly under pilot/logits/."""
    rc, env, log = _run_resolve(tmp_path, "logits", PILOT_ROOT, pairs_file=pairs)
    assert rc != 0 and "is not under pilot/runs/<run_id>/" in log, log
    assert "OUT_DIR=" not in env and "SUMMARY_FILE=" not in env


@pytest.mark.parametrize("legacy", sorted(ft.PILOT_LEGACY_OUTPUT_FOLDERS))
def test_both_sides_refuse_every_legacy_folder_name_as_a_run_id(tmp_path, legacy):
    """The fire path's list and this params job's agree name for name (circuit-trace's params job is held to the same
    list in tests/test_circuit_trace_pilot_root.py)."""
    pairs = f"pilot/runs/{legacy}/trace/{legacy}_x.json"
    rc, out, err = _run_params(tmp_path, {**BASE, **PILOT, "pairs_file": pairs})
    assert rc != 0 and out == "" and f"pilot/traces/{legacy}/ written before 2026-10-05" in err, err
    problems = _fire_refuses({**BASE, **PILOT, "pairs_file": pairs})
    assert problems and f"pilot/traces/{legacy}/ written before 2026-10-05" in problems[0], problems


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
OUT_DIR = "pilot/logits/run_a/run_a_p__qwen3-1.7b"


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
