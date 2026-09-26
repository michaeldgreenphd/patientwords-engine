"""Zero-cost end-to-end proof of the adaptive-auditor lane
(docs/petri_adaptive_design.md): the adaptive controller drives a mock target
through Petri with turns 2..N written by a mock auditor bound to the `auditor`
role, and the adapter proves that the target received exactly the seed's first
turn and then the auditor's answers under the one text rule, books the
auditor's calls, and refuses a conversation whose auditor answer was empty or
unfinished. Runs only where the locked harness is installed, as
tests/petri/test_zero_cost_e2e.py does; nothing is paid for."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("inspect_petri")

from inspect_ai.model import ChatMessageUser, GenerateConfig, ModelOutput, get_model  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import adaptive, cli, judge_runner, seeds  # noqa: E402
from scripts.petri_audit.adapter import adapt_run, read_records  # noqa: E402
from scripts.petri_audit.task import run_study, study_task  # noqa: E402

TOOLS = "pw-petri-w2a-tool-clarify"
PLAIN = "pw-petri-w2a-referral-specificity"


class Target:
    """Replies with a counter; on the second user turn of a sample offered tools it calls the named tool once."""

    def __init__(self, tool: str | None = None) -> None:
        self.tool, self.n = tool, 0

    def __call__(self, input, tools, tool_choice, config) -> ModelOutput:
        self.n += 1
        users = [m for m in input if isinstance(m, ChatMessageUser)]
        if self.tool and tools and len(users) == 2 and input[-1].role == "user":
            return ModelOutput.for_tool_call("mockllm/model", self.tool, {"query": "q"})
        return ModelOutput.from_content("mockllm/model", f"reply {self.n}")


class Auditor:
    """Answers with padding around the message number it is asked for, so the strip rule is exercised; `fail_at`
    returns an empty answer or an unfinished one at that message number."""

    def __init__(self, fail_at: int | None = None, stop_reason: str = "stop") -> None:
        self.fail_at, self.stop_reason, self.requests = fail_at, stop_reason, []

    def __call__(self, input, tools, tool_choice, config) -> ModelOutput:
        request = input[-1].text
        self.requests.append((input[0].text, request))
        n = int(re.search(r"message (\d+) of", request).group(1))
        if n == self.fail_at:
            return ModelOutput.from_content("mockllm/model", "" if self.stop_reason == "stop" else "cut off mid",
                                            stop_reason=self.stop_reason)
        return ModelOutput.from_content("mockllm/model", f"  person message {n} \n")


def _run(tmp: Path, seed_ids: list[str], auditor: Auditor, *, tool: str | None = None, epochs: int = 1):
    seed_set = seeds.load_seed_file(adaptive.ADAPTIVE_SEED_FILE)
    chosen = seeds.select_seeds(seed_set, seed_ids)
    target = get_model("mockllm/model", custom_outputs=Target(tool), config=GenerateConfig(temperature=1.0, max_tokens=1024))
    auditor_model = get_model("mockllm/model", custom_outputs=auditor)
    log = run_study(study_task(seed_set, chosen), target=target, seeds=chosen, epochs=epochs, log_dir=tmp / "logs",
                    token_limit=200000, cost_limit=0.01, auditor=auditor_model)
    assert log.status == "success", log.error
    result = adapt_run(Path(log.location), seed_set, tmp / "runs" / "run_a", custody="github_actions_artifact:90d",
                       spend={"max_spend_usd": 0.01, "judge_max_spend_usd": None, "journal_nonce": None,
                              "cost_limit_per_sample_usd": 0.01, "token_limit_per_sample": 200000},
                       engine_sha="0" * 40, harness_commit="e199ec1abcd10267c60cd7eb03035a76567d9e52")
    return seed_set, chosen, result


def test_the_target_receives_the_seed_turn_then_the_auditors_answers(tmp_path):
    auditor = Auditor()
    seed_set, chosen, result = _run(tmp_path, [PLAIN, TOOLS], auditor,
                                    tool=seeds.load_seed_file(adaptive.ADAPTIVE_SEED_FILE).seeds[TOOLS]["tools"]["definitions"][0]["name"])
    m = result.manifest
    assert m["execution"]["mode"] == "autonomous" and m["execution"]["claim_grade_eligible"] is False
    assert m["execution"]["contract_checks"]["stimulus_digest_identity"]["status"] == "pass"
    assert m["execution"]["contract_checks"]["tool_results_from_data"]["status"] == "pass"
    assert m["execution"]["auditor_instruction_sha256"] == adaptive.adaptive_prompt_digest(adaptive.load_adaptive_prompt())
    assert m["models"]["auditor"]["inspect_name"] == "mockllm/model"
    assert result.refused == [] and len(m["trees"]) == 4
    records = read_records(tmp_path / "runs" / "run_a" / "transcripts.jsonl")
    for r in records:
        users = [t["text"] for t in r["turns"] if t["role"] == "user"]
        assert len(users) == 10
        assert users[1:] == [f"person message {n}" for n in range(2, 11)], "the auditor's answer, stripped, verbatim"
    # nine auditor calls per conversation, each counted under its own role; the locked mockllm returns no usage block
    # for a scripted output, so every one is recorded as a call without usage, which a priced model would book at
    # its ceiling rather than at zero (spend.reprice_usage)
    by_role = {r["role"]: r for r in m["usage"]["by_role"]}
    assert by_role["auditor"]["calls"] == 4 * 9 and by_role["auditor"]["calls_without_usage"] == 4 * 9
    # the auditor never sees tool traffic, and sees its own arm's agenda only
    systems = {s for s, _ in auditor.requests}
    assert len(systems) == 4
    assert all("Assistant: reply" in req for _, req in auditor.requests if "message 3 of" in req)


@pytest.mark.parametrize("stop_reason", ["stop", "max_tokens"])
def test_an_empty_or_unfinished_auditor_answer_stops_and_refuses_the_conversation(tmp_path, stop_reason):
    _, _, result = _run(tmp_path, [PLAIN], Auditor(fail_at=4, stop_reason=stop_reason))
    assert len(result.refused) == 2, result.refused
    assert all("auditor_turn limit" in r["reason"] for r in result.refused)
    # the calls were made and are still booked
    by_role = {r["role"]: r for r in result.manifest["usage"]["by_role"]}
    assert by_role["auditor"]["calls"] == 2 * 3


def test_the_register_check_and_the_tiers_are_planned_from_the_records(tmp_path):
    seed_set, _, result = _run(tmp_path, [PLAIN], Auditor())
    records = read_records(tmp_path / "runs" / "run_a" / "transcripts.jsonl")
    from scripts.petri_audit import framework
    plans = judge_runner.plan_run(records, result.manifest, seed_set.seeds,
                                  outcomes=framework.load_json(framework.OUTCOME_REGISTRY),
                                  rubric=framework.load_json(framework.ADVICE_RUBRIC))
    kinds = {}
    for p in plans:
        kinds[(p.kind, p.key)] = kinds.get((p.kind, p.key), 0) + 1
    assert kinds == {("tier", "response_only"): 20, ("tier", "contextual"): 18, ("register", "register"): 20}


def test_the_cli_preflight_prices_the_bound_at_the_dearer_model(capsys):
    code = cli.main(["preflight", "--seeds", str(adaptive.ADAPTIVE_SEED_FILE), "--seed-id", TOOLS,
                     "--target", "anthropic/claude-haiku-4-5", "--auditor-model", "anthropic/claude-sonnet-5",
                     "--max-spend", "50", "--token-limit", "60000", "--no-harness-commit"])
    out = capsys.readouterr().out
    assert code == 0 and "2 sample(s) x 1 epoch(s) x 60000 tokens -> $1.8000" in out, out
