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


@pytest.mark.parametrize("sentinel", ["mockllm/model", "mockllm/judge", "none/none"])
def test_mode_run_refuses_every_test_sentinel_as_a_target(tmp_path, sentinel):
    # these price at zero in the engine table, so a run target naming one passed the paid pre-flight bound for
    # free and could commit mock output through the production path (Codex round 5 on PR #28)
    rc, out, err = _run(tmp_path, {**PAID, "target": sentinel})
    assert rc != 0 and "mode run needs a real target, not the test sentinel" in err
    assert out == ""
    # the same sentinel is exactly what dry_run is for
    rc, out, err = _run(tmp_path, {**PAID, "mode": "dry_run", "target": "mockllm/model"})
    assert rc == 0, err


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


@pytest.mark.parametrize("target", ["openai/gpt-5.4-mini", "google/gemini-3.5-flash", "grok/grok-4.3", "x-ai/grok-4.3",
                                    "bedrock/anthropic.claude-haiku-4-5"])
def test_mode_run_refuses_a_direct_vendor_target_that_the_guard_would_book_to_the_anthropic_lane(tmp_path, target):
    # fire_trigger.petri_channels books every target that is not openrouter/ to the Anthropic lane, but the run step
    # exports OPENAI_API_KEY and GEMINI_API_KEY too, so openai/... billed a direct vendor key against the Anthropic
    # ceiling (2026-09-23); cli preflight refuses the same spellings in every mode
    rc, out, err = _run(tmp_path, {**PAID, "target": target, "_nonce": "n1"})
    assert rc != 0 and "books every target that is not openrouter/ to the Anthropic lane" in err
    assert "openrouter/<vendor>/<model>" in err and out == ""


@pytest.mark.parametrize("target", ["claude-haiku-4-5", "", "anthropic/", "openrouter/", "openrouter/gpt-5.4-mini",
                                    "openrouter/openai/"])
def test_mode_run_refuses_a_target_that_names_no_provider_or_no_model(tmp_path, target):
    # Codex review of PR #37 (2026-09-23): the provider test above ran only when the target held a slash, so a bare
    # model name (which cli preflight reads as Anthropic) or an empty target passed the params job in mode run, and
    # so did an Inspect spelling with no model, or an OpenRouter one with no vendor
    rc, out, err = _run(tmp_path, {**PAID, "target": target, "_nonce": "n1"})
    assert rc != 0 and "mode run needs a target spelled anthropic/<model> or openrouter/<vendor>/<model>" in err, err
    assert out == ""


@pytest.mark.parametrize("target", ["anthropic/claude-haiku-4-5", "openrouter/openai/gpt-5.4-mini",
                                    "openrouter/google/gemini-3.5-flash"])
def test_mode_run_admits_the_two_providers_the_lane_books_correctly(tmp_path, target):
    rc, out, err = _run(tmp_path, {**PAID, "target": target, "_nonce": "n1"})
    assert rc == 0, err
    assert f"target={target}\n" in out


def _fire_trigger_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fire_trigger_parity", ROOT / "scripts" / "fire_trigger.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ABSENT = object()


@pytest.mark.parametrize("mode, target", [
    (mode, target)
    for mode in ("run", "dry_run", "preflight")
    for target in ("anthropic/claude-haiku-4-5", "openrouter/openai/gpt-5.4-mini", "openai/gpt-5.4-mini",
                   "google/gemini-3.5-flash", " anthropic/claude-haiku-4-5", "anthropic/claude-haiku-4-5 ",
                   "claude-haiku-4-5", "", "anthropic/", "openrouter/", "openrouter/gpt-5.4-mini",
                   "openrouter/openai/", "anthropic/claude-haiku-4-5/x", "anthropic/claude haiku",
                   "mockllm/model", "mockllm/judge", "none/none", " mockllm/model", _ABSENT)
])
def test_the_fire_guard_refuses_exactly_the_targets_the_params_job_refuses(tmp_path, mode, target):
    # Codex review of PR #37 (2026-09-24): the fire path journals a reservation before the params job runs, so a
    # target the params job refuses must be refused at the fire too, or the entry holds the queue slot and, in mode
    # run, the day's ceiling for a run that never starts. Same trigger file, both checks, same verdict.
    cfg = {**PAID, "mode": mode, "_nonce": "n1"}
    if target is _ABSENT:
        del cfg["target"]
    else:
        cfg["target"] = target
    rc, _, err = _run(tmp_path, cfg)
    try:
        _fire_trigger_module().validate_params("petri-audit", cfg)
        guard_admits = True
    except ValueError as exc:
        guard_admits, guard_err = False, str(exc)
    assert guard_admits == (rc == 0), (f"params job rc={rc} {err.strip()!r}; guard "
                                       f"{'admits' if guard_admits else 'refuses: ' + guard_err}")
