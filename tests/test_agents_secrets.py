"""AGENTS.md's Execution model paragraph against the files that decide what it
states. Which Actions secrets the repository holds cannot be read from the
repository (the paragraph records the owner's `gh secret list` of 2026-09-23),
so what is checked is that the paragraph and the repository agree: every
provider `key_env` in data/advice_providers.json names a held secret, every
`secrets.X` a workflow reads is either held or named as absent, and the Petri
target rule admits the lane's own park default where the code does.

The first version of that paragraph (2026-09-23) said a Petri target "must be"
`anthropic/<model>` or `openrouter/<vendor>/<model>`, which the lane's park
default (`mockllm/model`) broke, and said every non-Anthropic model is reached
through OpenRouter, which the Neuronpedia and Hugging Face lanes contradict."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

from scripts.petri_audit import spend

ROOT = Path(__file__).resolve().parents[1]
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"
REGISTRY = ROOT / "data" / "advice_providers.json"
BUILTIN_SECRETS = {"GITHUB_TOKEN"}          # provided by Actions itself, never listed by `gh secret list`
NUMBER_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
SECRET_NAME = re.compile(r"`([A-Z][A-Z0-9_]*)`")


def _fire_trigger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fire_trigger", ROOT / "scripts" / "fire_trigger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _execution_model() -> str:
    """The Execution model section's prose, up to its lane table, on one line."""
    start = AGENTS.index("## Execution model")
    end = AGENTS.index("\n| Trigger file", start)
    return " ".join(AGENTS[start:end].split())


def _clause(text: str, opening: str, stop: str) -> str:
    i = text.index(opening)
    return text[i:text.index(stop, i)]


def _held() -> list[str]:
    clause = _clause(_execution_model(), "holds exactly", ". ")
    count = NUMBER_WORDS[re.match(r"holds exactly (\w+)", clause).group(1)]
    names = SECRET_NAME.findall(clause)
    assert len(names) == count, f"AGENTS.md says it holds exactly {count} secrets but names {names}"
    return names


def _absent() -> list[str]:
    return SECRET_NAME.findall(_clause(_execution_model(), "There is no", ": "))


def _workflow_secrets() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for name in re.findall(r"secrets\.([A-Z][A-Z0-9_]*)", wf.read_text(encoding="utf-8")):
            refs.setdefault(name, []).append(wf.name)
    return refs


def test_held_and_absent_secret_lists_are_disjoint_and_non_empty() -> None:
    held, absent = set(_held()), set(_absent())
    assert held and absent
    assert not held & absent, sorted(held & absent)


def test_every_registry_key_env_names_a_held_secret() -> None:
    """A provider whose key_env the repository does not hold reaches the job as an
    empty string; the paragraph's list and the registry must not disagree."""
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    key_envs = {name: cfg["key_env"] for name, cfg in registry.items() if isinstance(cfg, dict) and cfg.get("key_env")}
    assert key_envs, "the registry names no key_env"
    unheld = {name: env for name, env in key_envs.items() if env not in _held()}
    assert not unheld, f"registry providers bill keys AGENTS.md does not list as held: {unheld}"


def test_every_workflow_secret_is_held_or_named_absent() -> None:
    known = set(_held()) | set(_absent()) | BUILTIN_SECRETS
    unknown = {name: files for name, files in _workflow_secrets().items() if name not in known}
    assert not unknown, f"workflows read secrets AGENTS.md neither lists as held nor names as absent: {unknown}"


def test_the_petri_target_rule_admits_the_park_default_where_the_code_does() -> None:
    """The rule is stated for `mode: run`, and it names the park default's mock
    target, which `cli preflight` admits and a `mode: run` fire refuses."""
    ft = _fire_trigger()
    park = ft.PARK_DEFAULTS["petri-audit"]
    target = park["target"]
    rule = _clause(_execution_model(), "A Petri target", ". ")
    assert "`mode: run`" in rule, rule
    assert f"`{target}`" in rule, f"the park default target {target!r} is not named in: {rule}"
    assert spend.target_provider_problems(target) == [], "cli preflight admits the park default's target"
    run_problems = ft.petri_params_problems({**park, "mode": "run", "_nonce": "agents-md-check"})
    assert any(target in p and "mode run" in p for p in run_problems), run_problems


def test_the_paragraph_does_not_route_every_non_anthropic_model_through_openrouter() -> None:
    """The traced and CPU-measured models are reached through Neuronpedia and
    Hugging Face, not OpenRouter; the OpenRouter statement is scoped to chat
    APIs."""
    para = _execution_model()
    assert "Every non-Anthropic model is reached through" not in para
    routing = _clause(para, "The models the study traces and measures", ". ")
    assert "`NEURONPEDIA_API_KEY`" in routing and "`HF_TOKEN`" in routing, routing
