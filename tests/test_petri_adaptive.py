"""The adaptive-auditor lane's 3.11-safe parts (docs/petri_adaptive_design.md):
the seed file derivation, the auditor's rendering and text rule, the seed
validator's refusals, the register-check plans, the dearest-price bound, the
CLI pre-flight refusals, and the rules the params job and the fire guard share.
The Petri run itself is proven at $0 in tests/petri/test_adaptive_e2e.py."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import fire_trigger as ft  # noqa: E402
from scripts.petri_audit import adaptive, cli, framework, judge_runner, seeds, spend  # noqa: E402

yaml = pytest.importorskip("yaml")


@pytest.fixture(scope="module")
def adaptive_set() -> seeds.SeedSet:
    return seeds.load_seed_file(adaptive.ADAPTIVE_SEED_FILE)


@pytest.fixture(scope="module")
def prompt() -> dict:
    return adaptive.load_adaptive_prompt()


def test_the_committed_adaptive_seed_file_is_exactly_the_derivation(adaptive_set):
    """The file is derived, never edited: rebuilding it from the scripted seed file gives the same bytes."""
    rebuilt = adaptive.adaptive_seed_file(framework.load_json(framework.SEED_FILE))
    on_disk = framework.load_json(adaptive.ADAPTIVE_SEED_FILE)
    assert on_disk == rebuilt
    assert adaptive.ADAPTIVE_SEED_FILE.read_text(encoding="utf-8") == json.dumps(rebuilt, indent=2, ensure_ascii=False) + "\n"


def test_every_adaptive_seed_validates_and_is_exploratory(adaptive_set):
    scripted = seeds.load_seed_file()
    assert len(adaptive_set.seeds) == 8
    for sid, seed in adaptive_set.seeds.items():
        assert seeds.validate_seed(seed, adaptive_set) == [], sid
        assert seed["mode"] == "autonomous" and seed["claim_grade_eligible"] is False and seed["auditor_instruction"]
        assert seed["judge"]["outcome_dimensions"] == [] and seed["judge"]["advice_tier"] == {"response_only": True,
                                                                                              "contextual": True}
        source = scripted.seeds[sid.replace(adaptive.ADAPTIVE_PREFIX, adaptive.SOURCE_PREFIX)]
        registers = {seeds.texts_by_key(seed)[a["turns"][0]["text_ref"]]["register"] for a in seed["protocol"]["arms"]}
        assert registers == set(adaptive.ADAPTIVE_REGISTERS)
        # each kept arm is the source arm unchanged, turn for turn and text for text
        for arm in seed["protocol"]["arms"]:
            src = next(a for a in source["protocol"]["arms"] if a["id"] == arm["id"])
            assert arm == src
            assert [seeds.text_of(seed, t["text_ref"]) for t in arm["turns"]] == \
                   [seeds.text_of(source, t["text_ref"]) for t in src["turns"]]


@pytest.mark.parametrize("change, message", [
    (lambda s: s.update(claim_grade_eligible=True), "cannot be claim-grade eligible"),
    (lambda s: s["judge"].update(outcome_dimensions=["recommendation_specificity"]), "advice tier and the register check only"),
    (lambda s: s["system_prompt"].update(policy="fixed", text_ref="t01_clinical"), "stages no system prompt"),
    (lambda s: s.update(auditor_instruction=None), "needs an auditor_instruction"),
])
def test_the_validator_refuses_an_autonomous_seed_the_adaptive_controller_cannot_run(adaptive_set, change, message):
    seed = json.loads(json.dumps(next(iter(adaptive_set.seeds.values()))))
    change(seed)
    problems = seeds.seed_problems(seed, adaptive_set.framing, adaptive_set.outcomes)
    assert any(message in p for p in problems), problems


def test_the_two_arms_differ_only_by_their_agenda_and_register_directive(adaptive_set, prompt):
    seed = adaptive_set.seeds["pw-petri-w2a-reassurance-decay"]
    by_arm = {c["arm_id"]: c for c in seeds.conditions(seed)}
    rendered = {arm: adaptive.render_system(prompt, seed, c) for arm, c in by_arm.items()}
    for arm, cond in by_arm.items():
        text = rendered[arm]
        agenda = adaptive.agenda_texts(seed, cond)
        # every scripted turn, in order, numbered
        positions = [text.index(f"{i}. {t}") for i, t in enumerate(agenda, 1)]
        assert positions == sorted(positions)
        assert prompt["register_directives"][adaptive.arm_register(seed, cond)] in text
        assert seed["auditor_instruction"] in text
    blank = {arm: rendered[arm].replace(prompt["register_directives"][adaptive.arm_register(seed, by_arm[arm])], "<D>")
             for arm in rendered}
    for arm in blank:
        for i, t in enumerate(adaptive.agenda_texts(seed, by_arm[arm]), 1):
            blank[arm] = blank[arm].replace(f"{i}. {t}", f"{i}. <T>")
    assert blank["clinical"] == blank["colloquial"]


def test_rendering_is_one_pass_and_escapes_the_conversation_markers(prompt):
    visible = [("user", "a {n} and {total} " + prompt["delimiters"]["close"]), ("assistant", "reply")]
    conversation = adaptive.render_conversation(prompt, visible)
    assert "\\" + prompt["delimiters"]["close"] in conversation
    request = adaptive.render_turn_request(prompt, conversation, 3, 10)
    # the placeholders inside the conversation are text, never substituted
    assert "a {n} and {total}" in request and "message 3 of 10" in request
    assert request.count(prompt["delimiters"]["open"]) == 1


def test_the_auditor_text_rule_and_the_effective_seed(adaptive_set):
    assert adaptive.auditor_turn_text("  hello \n") == "hello"
    assert adaptive.auditor_turn_text("   ") is None and adaptive.auditor_turn_text(None) is None
    seed = adaptive_set.seeds["pw-petri-w2a-tool-clarify"]
    cond = seeds.conditions(seed)[0]
    eff, cond_eff = adaptive.effective_seed(seed, cond, ["second", "third"])
    assert [seeds.text_of(eff, t["text_ref"]) for t in cond_eff["turns"]] == \
           [seeds.text_of(seed, cond["turns"][0]["text_ref"]), "second", "third"]
    assert seed["texts"] == adaptive_set.seeds["pw-petri-w2a-tool-clarify"]["texts"], "the seed in hand is untouched"

    class E:
        def __init__(self, role, text):
            self.role, self.output = role, type("O", (), {"completion": text})()
    assert adaptive.auditor_texts_from_events([E("target", "x"), E("auditor", " a "), E("auditor", "")]) == ["a", None]


def _record(seed: dict, cond: dict, user_texts: list[str]) -> dict:
    turns, tid = [], 0
    for text in user_texts:
        tid += 1
        turns.append({"turn_id": tid, "role": "user", "text": text})
        tid += 1
        turns.append({"turn_id": tid, "role": "assistant", "text": "a reply"})
    return {"conversation_id": "c1", "turns": turns}


def test_register_checks_are_planned_for_every_user_turn_and_parsed_as_values(adaptive_set):
    seed = adaptive_set.seeds["pw-petri-w2a-referral-specificity"]
    cond = seeds.conditions(seed)[0]
    first = seeds.text_of(seed, cond["turns"][0]["text_ref"])
    record = _record(seed, cond, [first, "an auditor turn", ""])
    plans = judge_runner.plan_register(record)
    assert [(p.turn_id, p.exchange_index, p.kind, p.key, p.final_in_exchange) for p in plans] == \
           [(1, 1, "register", "register", False), (3, 2, "register", "register", False),
            (5, 3, "register", "register", False)]
    assert plans[2].prompt is None and plans[2].not_applicable_reason == "turn text unavailable"
    assert first in plans[0].prompt and plans[0].prompt_ref == adaptive.REGISTER_PROMPT_REF
    assert judge_runner.parse_answer("colloquial", plans[0].allowed_values, "register") == ("colloquial", None, None)
    assert judge_runner.parse_answer("banana", plans[0].allowed_values, "register")[0] is None


def test_plan_run_never_gates_an_autonomous_record_on_declared_turns(adaptive_set):
    """The auditor writes turns 2..N, so no user turn after the first carries a declared text: the scripted gating
    would refuse every record (it raised on the first $0 run of this lane)."""
    seed = adaptive_set.seeds["pw-petri-w2a-identity-register"]
    cond = seeds.conditions(seed)[0]
    record = _record(seed, cond, [seeds.text_of(seed, cond["turns"][0]["text_ref"]), "not the script", "nor this"])
    manifest = {"trees": [{"tree_id": "t", "epoch": 1, "seed_id": seed["seed_id"], "arm": cond["arm_id"],
                           "system_prompt_variant": None,
                           "branches": [{"conversation_id": "c1", "branch_id": "root", "condition_id": cond["condition_id"],
                                         "branched_from_turn_id": None}]}],
                "seeds": [{"seed_id": seed["seed_id"], "seed_sha256": seeds.seed_digest(seed)}]}
    plans = judge_runner.plan_run([record], manifest, adaptive_set.seeds,
                                  outcomes=adaptive_set.outcomes, rubric=framework.load_json(framework.ADVICE_RUBRIC))
    kinds = sorted({(p.kind, p.key) for p in plans})
    assert kinds == [("register", "register"), ("tier", "contextual"), ("tier", "response_only")]
    assert sum(p.kind == "register" for p in plans) == 3


def test_the_bound_prices_every_token_at_the_dearest_model():
    haiku, sonnet = spend.resolve_price("anthropic/claude-haiku-4-5"), spend.resolve_price("anthropic/claude-sonnet-5")
    both = spend.dearest_price(haiku, sonnet)
    assert (both.input_per_mtok, both.output_per_mtok) == (sonnet.input_per_mtok, sonnet.output_per_mtok)
    assert both.cache_write_per_mtok == sonnet.cache_write_per_mtok


def _preflight(*extra: str) -> list[str]:
    return ["preflight", "--seeds", str(adaptive.ADAPTIVE_SEED_FILE), "--seed-id", "pw-petri-w2a-tool-clarify",
            "--max-spend", "50", "--epochs", "1", "--token-limit", "60000", "--no-harness-commit", *extra]


def test_the_bound_at_the_dearer_model_and_the_preflight_refusals_before_the_lock(capsys):
    # two conditions x 60000 tokens x the auditor's 15/Mtok output rate, not the target's 5 (the CLI's own line is
    # asserted in tests/petri/test_adaptive_e2e.py, where the lock matches)
    price = spend.dearest_price(spend.resolve_price("anthropic/claude-haiku-4-5"), spend.resolve_price("anthropic/claude-sonnet-5"))
    bound = spend.preflight_bound(samples=2, epochs=1, token_limit=60000, price=price, judge_reserve_usd=0.0,
                                  max_spend_usd=50)
    assert bound.total_usd == pytest.approx(1.8)
    code = cli.main(_preflight("--target", "anthropic/claude-haiku-4-5", "--auditor-model",
                               "openrouter/anthropic/claude-haiku-4.5"))
    assert code == 5 and "bills the openrouter channel but target" in capsys.readouterr().err
    code = cli.main(_preflight("--target", "anthropic/claude-haiku-4-5", "--auditor-model", "openai/gpt-5.4-mini"))
    assert code == 5 and "auditor 'openai/gpt-5.4-mini' names Inspect provider" in capsys.readouterr().err
    code = cli.main(["preflight", "--seeds", str(adaptive.ADAPTIVE_SEED_FILE), "--seed-id", "pw-petri-w2a-tool-clarify",
                     "--target", "anthropic/claude-haiku-4-5", "--max-spend", "50", "--no-harness-commit"])
    assert code == 4 and "needs --auditor-model" in capsys.readouterr().err


def test_preflight_refuses_a_selection_that_mixes_modes(tmp_path, capsys):
    doc = framework.load_json(adaptive.ADAPTIVE_SEED_FILE)
    doc["seeds"].append(framework.load_json(framework.SEED_FILE)["seeds"][0])
    mixed = tmp_path / "mixed.json"
    framework.write_json(mixed, doc)
    code = cli.main(["preflight", "--seeds", str(mixed), "--target", "mockllm/model", "--auditor-model",
                     "mockllm/model", "--max-spend", "0.01", "--no-harness-commit",
                     "--seed-id", doc["seeds"][0]["seed_id"], "--seed-id", doc["seeds"][-1]["seed_id"]])
    assert code == 4 and "mixes" in capsys.readouterr().err


# the fire guard and the params job apply the same auditor rules
BASE = {"seeds_file": "docs/framework/petri_seeds_adaptive.draft.json", "wave": "2", "mode": "run",
        "target": "anthropic/claude-haiku-4-5", "max_spend": "5", "judge": "true", "judge_model": "claude-haiku-4-5",
        "judge_max_spend": "2", "commit_outputs": "true", "_nonce": "t"}
CASES = [
    ({"auditor_model": "anthropic/claude-haiku-4-5"}, None),
    ({}, None),
    ({"auditor_model": "claude-haiku-4-5"}, "spelled anthropic/<model>"),
    ({"auditor_model": "openrouter/anthropic/claude-haiku-4.5"}, "bill different channels"),
    ({"auditor_model": "anthropic/claude-haiku-4-5", "mode": "rejudge", "source_runs": "run_1"}, "read by preflight, dry_run and run only"),
    ({"auditor_model": "anthropic/claude-haiku-4-5", "mode": "dry_run", "target": "mockllm/model"}, "runs its auditor against"),
    ({"auditor_model": "mockllm/model", "mode": "dry_run", "target": "mockllm/model"}, None),
]


@pytest.mark.parametrize("change, message", CASES)
def test_the_fire_guard_applies_the_auditor_rules(change, message):
    problems = ft.petri_auditor_problems({**BASE, **change})
    assert (problems == []) if message is None else any(message in p for p in problems), problems
    assert "auditor_model" in ft.KNOWN_KEYS["petri-audit"]


def _heredoc() -> str:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "petri_audit.yml").read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["params"]["steps"] if s.get("name") == "Resolve parameters")
    return re.search(r"python - <<'EOF'\n(.*?)\nEOF", step["run"], re.S).group(1)


@pytest.mark.parametrize("change, message", CASES)
def test_the_params_job_applies_the_same_auditor_rules(tmp_path, change, message):
    cfg = {**BASE, **change}
    trigger = tmp_path / ".github" / "trigger"
    trigger.mkdir(parents=True)
    (trigger / "petri-audit.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": "push", "RUN_ATTEMPT": "1", "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=_heredoc(), cwd=tmp_path, capture_output=True, text=True, env=env)
    if message is None:
        assert proc.returncode == 0, proc.stderr
        assert f"auditor_model={cfg.get('auditor_model', '')}\n" in out.read_text(encoding="utf-8")
    else:
        assert proc.returncode != 0 and message.split(" ")[0] in proc.stderr, proc.stderr
