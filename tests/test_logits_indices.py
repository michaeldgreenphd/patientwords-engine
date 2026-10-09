"""The logits-eval lane's `indices` (2026-10-09): measure a list of global pair indices instead of a range.

Held three ways, offline: logits_eval.py's --indices (results keep their global index, the part is named for the
first index, mixing with --offset/--limit is refused, before any model loads); the fire path's validation in
scripts/fire_trigger.py; and the workflow's params heredoc, run as CI runs it, refusing exactly what the fire path
refuses. The pairs are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "logits_evaluation.yml"
TRIGGER_SUBDIR = Path(".github") / "trigger"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_logits_indices", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


le = _load("logits_eval")
ft = _load("fire_trigger")


def test_parse_indices_accepts_ascending_and_refuses_everything_else():
    assert le.parse_indices("2,5,9", 10) == [2, 5, 9]
    assert le.parse_indices(" 3 ", 3) == [3]
    for bad in ("", "0,2", "2,2", "5,3", "a,1", "1,,2", "-1", "11"):
        with pytest.raises(ValueError):
            le.parse_indices(bad, 10)


def test_select_pairs_keeps_global_indices_for_both_forms():
    pairs = [f"p{i}" for i in range(1, 8)]
    assert le.select_pairs(pairs, indices=[2, 6]) == [(2, "p2"), (6, "p6")]
    assert le.select_pairs(pairs, offset=3, limit=2) == [(4, "p4"), (5, "p5")]
    assert le.select_pairs(pairs) == list(enumerate(pairs, start=1))
    assert le.select_pairs(pairs, offset=9) == []


@pytest.fixture
def stubbed(monkeypatch):
    """main() with the model load and the measurement stubbed: everything else runs as in CI."""
    monkeypatch.setattr(le, "load_pinned", lambda hf_id, pinned: (None, None, pinned))
    monkeypatch.setattr(le, "build_result", lambda i, pair, tok, fn, topk: {
        "index": i, "probabilities": {"clinical": 0.5, "patient": 0.25}, "language_penalty": -0.25})


def _pairs(tmp_path: Path, n: int) -> Path:
    path = tmp_path / "pairs_20990101T000000Z.json"
    path.write_text(json.dumps([{"top_prompt": f"xq {i}", "bottom_prompt": f"zq {i}"} for i in range(1, n + 1)]))
    return path


def test_an_indices_run_writes_one_part_named_for_its_first_index(tmp_path, stubbed):
    out = tmp_path / "out"
    le.main(["--pairs", str(_pairs(tmp_path, 12)), "--model", "qwen3-1.7b", "--out", str(out), "--indices", "4,9,12"])
    (part,) = out.glob("batch_summary*.json")
    assert part.name == "batch_summary.part_04.json"
    summary = json.loads(part.read_text())
    assert [r["index"] for r in summary["results"]] == [4, 9, 12]
    assert summary["start_index"] == 4 and summary["indices_requested"] == [4, 9, 12] and summary["completed"]


def test_a_range_run_is_unchanged(tmp_path, stubbed):
    out = tmp_path / "out"
    le.main(["--pairs", str(_pairs(tmp_path, 12)), "--model", "qwen3-1.7b", "--out", str(out),
             "--offset", "5", "--limit", "3"])
    (part,) = out.glob("batch_summary*.json")
    summary = json.loads(part.read_text())
    assert part.name == "batch_summary.part_06.json" and [r["index"] for r in summary["results"]] == [6, 7, 8]
    assert "indices_requested" not in summary


@pytest.mark.parametrize("extra", [["--offset", "2"], ["--limit", "3"], ["--indices", "3,2"], ["--indices", "13"]])
def test_indices_mixed_with_a_range_or_malformed_is_refused_before_loading(tmp_path, monkeypatch, extra):
    def no_load(*a):
        raise AssertionError("the model must not load")
    monkeypatch.setattr(le, "load_pinned", no_load)
    argv = ["--pairs", str(_pairs(tmp_path, 12)), "--model", "qwen3-1.7b", "--out", str(tmp_path / "o")]
    if extra[0] != "--indices":
        argv += ["--indices", "1,2"]
    with pytest.raises(SystemExit) as exc:
        le.main(argv + extra)
    assert exc.value.code == 2
    assert not (tmp_path / "o").exists()


# ---------------------------------------------------------------- fire path and params job agree

def _params_heredoc() -> str:
    run = next(s for s in yaml.safe_load(WORKFLOW.read_text())["jobs"]["params"]["steps"]
               if s.get("id") == "params")["run"]
    return re.search(r"python - <<'EOF'\n(.*?)\nEOF", run, re.S).group(1)


def _run_params(tmp_path: Path, cfg: dict) -> tuple[int, str]:
    trigger_dir = tmp_path / TRIGGER_SUBDIR
    trigger_dir.mkdir(parents=True, exist_ok=True)
    (trigger_dir / "logits-eval.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "push", "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=_params_heredoc(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8")


BASE = {"models": "medgemma-1.5-4b-it", "pairs_file": "data/simulated/pairs_20990101T000000Z.json",
        "commit_outputs": "true"}
CASES = [
    ("csv", {"indices": "4,9,12"}, False, "4,9,12"),
    ("json-list", {"indices": [4, 9, 12]}, False, "4,9,12"),
    ("zero-range-stated", {"indices": "4,9", "offset": "0", "limit": "0"}, False, "4,9"),
    ("empty-is-a-range-fire", {"indices": "", "offset": "25", "limit": "25"}, False, ""),
    ("descending", {"indices": "9,4"}, True, None),
    ("repeat", {"indices": "4,4"}, True, None),
    ("zero-index", {"indices": "0,4"}, True, None),
    ("not-a-number", {"indices": "4,x"}, True, None),
    ("with-offset", {"indices": "4,9", "offset": "3"}, True, None),
    ("with-limit", {"indices": "4,9", "limit": "2"}, True, None),
    ("depth-mode", {"indices": "4,9", "mode": "depth"}, True, None),
    ("pilot-root", {"indices": "4", "output_root": "pilot/logits",
                    "pairs_file": "pilot/runs/run_a/trace/run_a_pairs.json"}, True, None),
]


@pytest.mark.parametrize("cfg,refused,resolved", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_the_params_job_and_the_fire_path_refuse_the_same_indices(tmp_path, cfg, refused, resolved):
    params = {**BASE, **cfg}
    try:
        ft.validate_params("logits-eval", params)
        fire_refused = False
    except ValueError:
        fire_refused = True
    rc, out = _run_params(tmp_path, params)
    assert fire_refused is refused and (rc != 0) is refused, (fire_refused, rc)
    if refused:
        assert out == ""                                   # nothing written for a refused config
    else:
        assert f"indices={resolved}\n" in out


def test_the_resolve_step_names_an_indices_part_for_its_first_index():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["eval"]["steps"]
    resolve = next(s for s in steps if s.get("name") == "Resolve output dir")
    measure = next(s for s in steps if s.get("name") == "Measure next-token behavior")
    assert resolve["env"]["INDICES"] == measure["env"]["INDICES"] == "${{ needs.params.outputs.indices }}"
    script = resolve["run"].split('if [ "$OUTPUT_ROOT" = "pilot/logits" ]')[0]
    for indices, part in (("4,9,12", "part_04"), ("117", "part_117"), ("", "part_26")):
        proc = subprocess.run(["bash", "-c", script + '\necho "$PART"'], capture_output=True, text=True,
                              env={**os.environ, "INDICES": indices, "OFFSET": "25", "PAIRS_FILE": "data/x.json",
                                   "GITHUB_ENV": os.devnull})
        assert proc.stdout.strip() == part, (indices, proc.stdout, proc.stderr)
    assert '--indices "$INDICES"' in measure["run"]
