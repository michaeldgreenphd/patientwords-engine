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
        def __init__(self, role, text, stop="stop"):
            self.role, self.output = role, type("O", (), {"completion": text, "stop_reason": stop})()
    assert adaptive.auditor_texts_from_events([E("target", "x"), E("auditor", " a "), E("auditor", "")]) == ["a", None]
    # an unfinished answer is None exactly where the controller stopped, so the adapter never declares a turn the
    # target did not receive (review of PR #50: a max_tokens answer failed the whole run's stimulus check)
    assert adaptive.auditor_texts_from_events([E("auditor", "cut off", "max_tokens"),
                                               E("auditor", "withheld", "content_filter")]) == [None, None]
    assert adaptive.auditor_answer(None) is None


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
    # a readapt states its source run's auditor, as it states the target (Codex review of PR #50: the recovery mode
    # refused every autonomous run)
    ({"auditor_model": "anthropic/claude-haiku-4-5", "mode": "readapt", "source_run_id": "123"}, None),
    ({"auditor_model": "haiku", "mode": "readapt", "source_run_id": "123"}, "spelled anthropic/<model>"),
    ({}, None),
    ({"auditor_model": "claude-haiku-4-5"}, "spelled anthropic/<model>"),
    ({"auditor_model": "openrouter/anthropic/claude-haiku-4.5"}, "bill different channels"),
    ({"auditor_model": "anthropic/claude-haiku-4-5", "mode": "rejudge", "source_runs": "run_1"}, "read by preflight, dry_run, run and readapt only"),
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


def test_a_readapt_must_state_its_source_runs_auditor():
    """The auditor is a readapt match key, resolved empty when a trigger file names none, so a scripted source and a
    readapt that names no auditor still match, and an autonomous source's readapt must name the same auditor."""
    assert "auditor_model" in ft.PETRI_READAPT_MATCH_KEYS
    assert ft._petri_resolved({"mode": "readapt"})["auditor_model"] == ""
    mine = ft._petri_resolved({"auditor_model": "anthropic/claude-haiku-4-5"})
    theirs = ft._petri_resolved({"auditor_model": "anthropic/claude-sonnet-5"})
    assert ft._petri_values_differ("auditor_model", mine["auditor_model"], theirs["auditor_model"])


def test_a_rejudge_binds_the_register_prompt_an_autonomous_runs_plans_carry(adaptive_set):
    """Codex review of PR #50: the rejudge instrument block bound outcome prompt files only, so a re-grade of an
    adaptive run sealed no digest for the register prompt its new judge was sent."""
    from scripts.petri_audit import rejudge

    seed = adaptive_set.seeds["pw-petri-w2a-referral-specificity"]
    cond = seeds.conditions(seed)[0]
    plans = judge_runner.plan_register(_record(seed, cond, [seeds.text_of(seed, cond["turns"][0]["text_ref"]), "x"]))
    block = rejudge.instrument_block(plans)
    assert list(block["prompt_files"]) == [adaptive.REGISTER_PROMPT_REF]
    assert block["prompt_files"][adaptive.REGISTER_PROMPT_REF]["sha256"] == framework.sha256_file(
        framework.ROOT / adaptive.REGISTER_PROMPT_REF)


def test_the_fallback_spend_report_books_the_auditors_calls():
    """Review of PR #50: the no-adapted-report path counted target calls only, so an auditor call without usage was
    never imputed and one with usage but no aggregate was dropped."""
    from types import SimpleNamespace as NS

    usage = NS(input_tokens=1000, output_tokens=100, total_tokens=1100, input_tokens_cache_read=None,
               input_tokens_cache_write=None)
    sample = NS(model_usage={}, events=[
        NS(event="model", role="target", model="anthropic/claude-haiku-4-5", output=NS(usage=usage)),
        NS(event="model", role="auditor", model="anthropic/claude-sonnet-5", output=NS(usage=usage)),
        NS(event="model", role="auditor", model="anthropic/claude-sonnet-5", output=NS(usage=None))])
    rows = spend.usage_from_samples([sample])
    assert rows["anthropic/claude-sonnet-5"]["calls"] == 2 and rows["anthropic/claude-sonnet-5"]["calls_without_usage"] == 1
    assert rows["anthropic/claude-sonnet-5"]["input_tokens"] == 1000
    cost, priced = spend.reprice_usage(rows)
    assert cost is None, "a priced auditor call without usage makes the total unknown, so the ceiling is imputed"


@pytest.mark.parametrize("change, expect", [
    ({}, "need auditor_model"),                                                  # adaptive seeds, no auditor
    ({"auditor_model": "anthropic/claude-haiku-4-5"}, None),
    ({"seeds_file": "docs/framework/petri_seeds.draft.json", "auditor_model": "anthropic/claude-haiku-4-5"},
     "take no auditor_model"),
    ({"seeds_file": "docs/framework/petri_seeds.draft.json", "wave": "1"}, None),  # a scripted fire, as before
    ({"seed_ids": "pw-petri-w2a-tool-clarify", "auditor_model": "anthropic/claude-haiku-4-5"}, None),
    ({"mode": "rejudge", "source_runs": "run_1"}, None),                         # rejudge reads no seeds this way
    # a seed file preflight would refuse after the fire had journaled its reservation (Antigravity review of PR #50)
    ({"seeds_file": "docs/framework/no_such_file.json"}, "cannot be read as a seed file"),
    ({"seeds_file": None}, "names no file"),
    ({"seeds_file": "/etc/hosts"}, "not an absolute one"),
    ({"seeds_file": "../patientwords/README.md"}, "climbs out of the repository"),
    ({"wave": "1", "auditor_model": "anthropic/claude-haiku-4-5"}, "selects no seed"),
    ({"seed_ids": "pw-petri-w2a-nope", "auditor_model": "anthropic/claude-haiku-4-5"}, "are not in"),
    ({"seed_ids": ["pw-petri-w2a-tool-clarify"], "auditor_model": "anthropic/claude-haiku-4-5"}, None),
    ({"wave": 2, "auditor_model": "anthropic/claude-haiku-4-5"}, None),
])
def test_the_fire_guard_refuses_a_seed_file_and_auditor_that_do_not_match(change, expect):
    """Review of PR #50: cli preflight's one-mode rule ran only in CI, after the fire had journaled a reservation that
    holds the day's ceiling; the guard now refuses the mismatch before the push."""
    problems = ft.petri_seed_mode_problems({**BASE, **change}, repo=ROOT)
    assert (problems == []) if expect is None else any(expect in p for p in problems), problems
    assert ft.petri_params_problems({"mode": "preflight"}) == [], "the park is unaffected"


def _turns() -> list[dict]:
    """A record's turns: the person's first message, a reply that calls a tool with text, the tool result, a
    whitespace-only reply, then the person's second message and a plain reply."""
    return [{"turn_id": 1, "role": "user", "text": "first"},
            {"turn_id": 2, "role": "assistant", "text": "let me look that up"},
            {"turn_id": 3, "role": "tool", "text": "tool result the person never sees"},
            {"turn_id": 4, "role": "assistant", "text": "   "},
            {"turn_id": 5, "role": "user", "text": "second"},
            {"turn_id": 6, "role": "assistant", "text": "a reply"}]


def _call(prompt: dict, request: str, *, answer: str = "ok", stop: str = "stop", roles=("system", "user"), tools=None,
          error=None):
    from types import SimpleNamespace as NS
    texts = {"system": "sys", "user": request, "assistant": "prefill"}
    return NS(input=[NS(role=r, text=texts[r]) for r in roles], tools=tools or [], error=error,
              output=NS(completion=answer, stop_reason=stop))


def test_the_auditor_requests_are_recomputed_from_what_the_person_saw(prompt):
    """Review of PR #50: the person sees their own messages and the assistant's non-empty text, never tool traffic;
    the request for message 2 renders exactly that, with the controller's total."""
    assert adaptive.visible_turns(_turns()) == [("user", "first"), ("assistant", "let me look that up"),
                                                ("user", "second"), ("assistant", "a reply")]
    [req] = adaptive.expected_auditor_requests(prompt, _turns(), 10)
    assert req == adaptive.render_turn_request(
        prompt, adaptive.render_conversation(prompt, [("user", "first"), ("assistant", "let me look that up")]), 2, 10)


def test_the_auditor_request_check_refuses_every_departure(prompt):
    [req2] = adaptive.expected_auditor_requests(prompt, _turns(), 10)
    req3 = adaptive.render_turn_request(prompt, adaptive.render_conversation(prompt, adaptive.visible_turns(_turns())), 3, 10)
    ok = _call(prompt, req2)
    check = lambda calls: adaptive.auditor_request_problems(prompt, _turns(), calls, 10, where="t")  # noqa: E731
    assert check([ok]) == []
    assert "0 auditor call(s)" in check([])[0]
    assert "auditor calls for 1" in check([ok, ok, ok])[0]
    assert "was not sent the conversation" in check([_call(prompt, req3)])[0]
    # exactly one system and one user message, and no tools (a prefill or an injected message passed before)
    assert "not one system and one user message" in check([_call(prompt, req2, roles=("system", "user", "assistant"))])[0]
    assert "not one system and one user message" in check([_call(prompt, req2, tools=["t"])])[0]
    # the one further call is the refused one: the whole conversation as the next request, and an unfinished answer
    assert check([ok, _call(prompt, req3, answer="", stop="stop")]) == []
    assert check([ok, _call(prompt, req3, answer="cut", stop="max_tokens")]) == []
    assert "was not sent the conversation" in check([ok, _call(prompt, req2, answer="", stop="stop")])[0]
    assert "finished answer that was never staged" in check([ok, _call(prompt, req3, answer="done")])[0]


def test_a_retried_auditor_attempt_is_booked_but_not_read_as_a_call():
    """Review of PR #50: Inspect records an attempt that failed and was retried as its own event with an error; it is
    not an answer the controller staged, so the text and request checks read completed calls only."""
    from types import SimpleNamespace as NS

    failed, done = NS(error="overloaded", role="auditor"), NS(error=None, role="auditor")
    assert adaptive.completed_calls([failed, done]) == [done]


def _repo_with_run(tmp_path: Path, seeds_file: str) -> Path:
    """A throwaway checkout holding both seed files and one landed run whose manifest recorded its seeds from
    `seeds_file`, as the adapter records them."""
    fw = tmp_path / "docs" / "framework"
    fw.mkdir(parents=True)
    for f in (framework.SEED_FILE, adaptive.ADAPTIVE_SEED_FILE):
        (fw / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    doc = framework.load_json(tmp_path / seeds_file)
    run = tmp_path / "data" / "petri" / "runs" / "run_1_1"
    run.mkdir(parents=True)
    framework.write_json(run / "manifest.json", {"seeds": [{"seed_id": s["seed_id"], "file": seeds_file}
                                                          for s in doc["seeds"][:2]]})
    return tmp_path


def test_the_fire_guard_refuses_a_rejudge_whose_seed_file_lacks_the_runs_seeds(tmp_path):
    """Antigravity review of PR #50: a rejudge plans from the seed file its fire names, which defaults to the scripted
    one, so a rejudge of an autonomous run was refused by the plan after the fire had reserved the judge's ceiling."""
    adaptive_rel = "docs/framework/" + adaptive.ADAPTIVE_SEED_FILE.name
    repo = _repo_with_run(tmp_path, adaptive_rel)
    params = {"mode": "rejudge", "source_runs": "run_1_1", "judge": "true", "judge_model": "claude-haiku-4-5",
              "judge_max_spend": "1"}
    problems = ft.petri_seed_mode_problems(params, repo=repo)
    assert any("run_1_1" in p and adaptive_rel in p for p in problems), problems
    assert ft.petri_seed_mode_problems({**params, "seeds_file": adaptive_rel}, repo=repo) == []
    assert ft.petri_seed_mode_problems({**params, "source_runs": ["run_1_1"], "seeds_file": adaptive_rel}, repo=repo) == []
    # a source run this checkout does not hold is left to the plan
    assert ft.petri_seed_mode_problems({**params, "source_runs": "run_9_1"}, repo=repo) == []


def test_the_rehearsal_plans_from_the_seed_file_the_run_recorded(tmp_path):
    """Antigravity review of PR #50: rejudge-rehearse defaulted to the scripted seed file and refused every autonomous
    run; it now reads the file the run's manifest recorded."""
    from scripts.petri_audit import rejudge

    adaptive_rel = "docs/framework/" + adaptive.ADAPTIVE_SEED_FILE.name
    repo = _repo_with_run(tmp_path, adaptive_rel)
    runs = repo / "data" / "petri" / "runs"
    assert cli.recorded_seed_file(runs, "run_1_1") == str(framework.ROOT / adaptive_rel)
    framework.write_json(runs / "run_1_1" / "manifest.json", {"seeds": []})
    assert cli.recorded_seed_file(runs, "run_1_1") == str(framework.SEED_FILE)
    framework.write_json(runs / "run_1_1" / "manifest.json", {"seeds": [{"seed_id": "a", "file": "x.json"},
                                                                         {"seed_id": "b", "file": "y.json"}]})
    with pytest.raises(rejudge.RejudgeError, match="more than one file"):
        cli.recorded_seed_file(runs, "run_1_1")
