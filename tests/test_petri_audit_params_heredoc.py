"""The petri-audit workflow's push-path parameter resolution, run as CI runs it:
the python heredoc of the "Resolve parameters" step, with a trigger file on
disk (the pattern of tests/test_archive_workflow_params.py).

Every resolved value is written to `$GITHUB_OUTPUT` as one `key=value` line and
a later duplicate key wins, so a value carrying a newline writes further
key=value lines of its own. `_nonce` is written last, where an injected line
overrides every key before it, including `mode`, `target` and the two spend
ceilings - after this step's own checks have passed. The guard refuses any
control character (PR B, 2026-09-18).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "petri_audit.yml"
PAID = {"seeds_file": "docs/framework/petri_seeds.draft.json", "seed_ids": "", "wave": "1",
        "target": "anthropic/claude-haiku-4-5", "mode": "run", "epochs": "1", "token_limit": "20000",
        "max_spend": "1.00", "judge": "false", "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01",
        "judge_max_tokens": "300", "log_model_api": "true", "commit_outputs": "true"}


def _resolve_step_python() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["params"]["steps"] if s.get("name") == "Resolve parameters")
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", step["run"], re.S)
    assert m, "the Resolve parameters step no longer carries its python heredoc"
    return m.group(1)


def _run(tmp_path: Path, cfg: dict, attempt: str = "1") -> tuple[int, str, str]:
    trigger_dir = tmp_path / ".github" / "trigger"
    trigger_dir.mkdir(parents=True, exist_ok=True)
    (trigger_dir / "petri-audit.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "push", "RUN_ATTEMPT": attempt, "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=_resolve_step_python(), cwd=tmp_path,
                          capture_output=True, text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


def test_a_paid_fire_resolves_and_carries_its_nonce_to_the_outputs(tmp_path):
    rc, out, err = _run(tmp_path, {**PAID, "_nonce": "pilot-20260918a"})
    assert rc == 0, err
    assert "mode=run\n" in out and "target=anthropic/claude-haiku-4-5\n" in out
    assert "_nonce=pilot-20260918a\n" in out
    assert "commit_outputs=true\n" in out and "max_spend=1.00\n" in out


def test_a_fire_without_a_nonce_resolves_with_an_empty_one(tmp_path):
    rc, out, err = _run(tmp_path, {**PAID, "mode": "preflight", "target": "mockllm/model"})
    assert rc == 0, err
    assert "_nonce=\n" in out, "the output must exist and be empty, never absent"


@pytest.mark.parametrize("nonce, injected", [
    ("x\nmode=run", "mode=run"),                       # preflight becomes a paid run
    ("x\nmax_spend=99", "max_spend=99"),               # the ceiling the journal reserved is rewritten
    ("x\ncommit_outputs=true", "commit_outputs=true"),
    ("x\rtarget=anthropic/claude-opus-4-8", "target=anthropic/claude-opus-4-8"),
])
def test_a_nonce_carrying_a_control_character_is_refused_before_any_output(tmp_path, nonce, injected):
    cfg = {**PAID, "mode": "preflight", "target": "mockllm/model", "_nonce": nonce}
    rc, out, err = _run(tmp_path, cfg)
    assert rc != 0, f"the injected line {injected!r} would have overridden the resolved value"
    assert "_nonce must not carry a control character" in err
    assert out == "", "nothing may be written once a value is refused"


@pytest.mark.parametrize("key", ["target", "seeds_file", "seed_ids", "judge_model"])
def test_a_trigger_value_carrying_a_newline_is_refused(tmp_path, key):
    # these four reach $GITHUB_OUTPUT unparsed (mode is set-checked, the numbers are float()/int()-parsed,
    # the booleans are canonicalised), so each is its own injection point into every key written after it
    rc, out, err = _run(tmp_path, {**PAID, "mode": "preflight", "target": "mockllm/model",
                                   key: f"{PAID[key]}\ncommit_outputs=true"})
    assert rc != 0 and f"{key} must not carry a control character" in err
    assert out == ""


def test_the_guard_does_not_reject_the_park_default(tmp_path):
    ft_path = ROOT / "scripts" / "fire_trigger.py"
    src = ft_path.read_text(encoding="utf-8")
    assert "petri-audit" in src
    import importlib.util

    spec = importlib.util.spec_from_file_location("fire_trigger", ft_path)
    ft = importlib.util.module_from_spec(spec)
    sys.modules["fire_trigger"] = ft
    spec.loader.exec_module(ft)
    rc, out, err = _run(tmp_path, dict(ft.PARK_DEFAULTS["petri-audit"]))
    assert rc == 0, err
    assert "mode=preflight\n" in out
