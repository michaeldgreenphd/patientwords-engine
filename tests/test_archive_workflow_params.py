"""The archive workflow's push-path parameter parsing, run as CI runs it: the
python heredoc of the "Resolve parameters" step, with a trigger file on disk.
Booleans must be JSON booleans or the strings "true"/"false"; anything else
is a refusal. bool("false") is True, which on allow_shrink would skip the
guard that stops an upload from destroying archived PNGs (Codex, PR #15)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _resolve_step_python() -> str:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "archive_renders.yml").read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["archive"]["steps"] if s.get("name") == "Resolve parameters")
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", step["run"], re.S)
    assert m, "the Resolve parameters step no longer carries its python heredoc"
    return m.group(1)


def _run(tmp_path: Path, cfg: dict) -> tuple[int, str, str]:
    (tmp_path / ".github" / "trigger").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "trigger" / "archive-renders.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "push", "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=_resolve_step_python(), cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


@pytest.mark.parametrize("value, expect", [(True, "1"), (False, "0"), ("true", "1"), ("false", "0"), ("False", "0")])
def test_allow_shrink_parses_booleans_and_their_strings(tmp_path, value, expect):
    rc, out, err = _run(tmp_path, {"tag": "t", "runs": ["trace_out/x"], "allow_shrink": value})
    assert rc == 0, err
    assert f"allow_shrink={expect}\n" in out


@pytest.mark.parametrize("value", ["yes", 1, "", "off", [True]])
def test_other_boolean_spellings_are_refused(tmp_path, value):
    rc, out, err = _run(tmp_path, {"tag": "t", "runs": ["trace_out/x"], "prune": value})
    assert rc != 0 and "prune must be true or false" in err


def test_park_default_strings_still_parse(tmp_path):
    rc, out, err = _run(tmp_path, {"tag": "park-noop", "runs": ["trace_out/pairs_20260706T172135Z"],
                                   "no_pngs": "true"})
    assert rc == 0, err
    assert "no_pngs=1\n" in out and "prune=0\n" in out and "prune_only=0\n" in out and "allow_shrink=0\n" in out


def test_prune_only_is_exclusive(tmp_path):
    rc, out, err = _run(tmp_path, {"tag": "t", "runs": ["trace_out/x"], "prune_only": True, "prune": True})
    assert rc != 0 and "prune_only stands alone" in err
