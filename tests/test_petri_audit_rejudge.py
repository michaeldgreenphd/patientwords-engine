"""Mode rejudge of the petri-audit lane (scripts/petri_audit/rejudge.py and the CLI, reconciliation and ledger
pieces around it): a landed run is re-graded by a judge other than its judge of record, from its committed
transcripts, under exactly the plan its judge of record applied; the outputs go to their own directory and never
touch data/petri/runs; a directory holding a re-grade is refused; the manifest binds the source run and verifies
on its own; one fire's ceiling is shared by its source runs; the judge sidecar is booked once, to the rejudge
fire. Synthetic and offline: every source run here is built in a temporary directory through the lane's own
writers (the schema example manifest, a seed from the seed file, a mock judge of record bound by
manifest.bind_judgments), and every judge is a MockJudge; nothing calls a provider or reads a landed run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# medical vocabulary lives in JSON data, never in Python source (AGENTS.md)
TEXTS = json.loads((ROOT / "tests" / "fixtures" / "petri_texts.json").read_text(encoding="utf-8"))

from scripts import ledger_update  # noqa: E402
from scripts.petri_audit import cli, framework, judge_runner, reconcile, rejudge, seeds, transcripts  # noqa: E402
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402

SEED_ID = "pw-petri-example-h4-persistence"
BRANCH_CONVERSATION = "2" * 64                   # the schema example's pressure_minimize branch
JUDGE_OF_RECORD = "claude-haiku-4-5"
PAID_JUDGE = "openrouter:openai/gpt-5.4-mini"
PAID_SLUG = "openrouter-openai-gpt-5.4-mini"
COMMIT = "c" * 40
# the environment a paid judge's key check reads (rejudge.judge_key_problem); every judge here is a MockJudge, so the
# value is never sent anywhere
KEYS = {"OPENROUTER_API_KEY": "test-key-never-sent"}


def _load_fire_trigger():
    spec = importlib.util.spec_from_file_location("fire_trigger_rejudge", ROOT / "scripts" / "fire_trigger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ft = _load_fire_trigger()


@pytest.fixture(scope="module")
def seed_set() -> seeds.SeedSet:
    return seeds.load_seed_file()


def _branch_record(seed: dict) -> dict:
    """The pressure-branch record of the example H4 seed: its shared prefix (turns 1-2), then the pressure turn and
    the reply (the fixture texts are data, tests/fixtures/petri_texts.json)."""
    messages = [
        {"role": "user", "text": seeds.text_of(seed, "stimulus_colloquial"), "id": "m1"},
        {"role": "assistant", "text": TEXTS["reply_safety_netted"], "id": "m2"},
        {"role": "user", "text": seeds.text_of(seed, "pushback_minimize"), "id": "m3"},
        {"role": "assistant", "text": TEXTS["reply_minimised"], "id": "m4"},
    ]
    return transcripts.build_record(messages, conversation_id=BRANCH_CONVERSATION, source_system="inspect_petri",
                                    source_model="mockllm/model", model_version="mockllm",
                                    captured_utc="2026-09-16T00:00:00Z", user_is="unknown",
                                    import_utc="2026-09-16T00:00:00Z", importer_sha=None,
                                    run_manifest_sha256="a" * 64, run_manifest_ref=None)


def _land(runs: Path, stem: str, seed_set: seeds.SeedSet, *, judge_model: str = JUDGE_OF_RECORD,
          judge_max_tokens: int = 300) -> Path:
    """A landed, chained, judged run, written through the lane's own writers: the schema example manifest with the
    seed in hand's digest, one branch record as its transcripts, sealed and chained, then a mock judge of record
    run under `judge_model` and bound into the manifest (manifest.bind_judgments)."""
    base = json.loads(json.dumps(framework.load_json(framework.MANIFEST_SCHEMA)["examples"][0]))
    run_dir = runs / stem
    run_dir.mkdir(parents=True)
    base["run_id"], base["eval_id"] = f"Run{stem}", f"Eval{stem}"
    base["seeds"][0]["seed_sha256"] = seeds.seed_digest(seed_set.seeds[SEED_ID])
    # the example names its branches b2/b3; the adapter names a branch by the seed's declared branch id
    for branch in base["trees"][0]["branches"]:
        if branch["condition_id"]:
            branch["branch_id"] = branch["condition_id"]
    base["trees"][0]["surviving_branch_id"] = "neutral_control"
    record = _branch_record(seed_set.seeds[SEED_ID])
    (run_dir / "transcripts.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (run_dir / "sanitised_log.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "rule_outcomes.jsonl").write_text("", encoding="utf-8")
    for fam, name in (("sanitised_log", "sanitised_log.json"), ("transcripts", "transcripts.jsonl"),
                      ("rule_outcomes", "rule_outcomes.jsonl")):
        base["artifacts"][f"{fam}_path"] = f"{stem}/{name}"
        base["artifacts"][f"{fam}_sha256"] = framework.sha256_file(run_dir / name)
    sealed = manifest_mod.seal_manifest(base, manifest_mod.chain_head(runs))
    manifest_mod.write_manifest(run_dir / "manifest.json", sealed)
    manifest_mod.append_chain(runs, sealed, run_dir / "manifest.json")
    plans = judge_runner.plan_run([record], sealed, seed_set.seeds, outcomes=framework.load_json(framework.OUTCOME_REGISTRY),
                                  rubric=judge_runner.load_rubric())
    answers = rejudge.mock_answers(plans)
    report = run_dir / f"{stem}.judge.report.json"
    side = judge_runner.run_judgments(plans, judge_runner.MockJudge(lambda p: answers[p], model_spec=judge_model),
                                      out_path=run_dir / "judgments.jsonl",
                                      ceiling=judge_runner.SpendCeiling(1.0, 1.0, 5.0, judge_max_tokens),
                                      judge_max_tokens=judge_max_tokens,
                                      labels=judge_runner.labels_from_manifest(sealed), report_path=report,
                                      sidecar_extra={"run_id": sealed["run_id"], "eval_id": sealed["eval_id"]},
                                      now_fn=lambda: "2026-09-20T00:00:00Z")
    totals = judge_runner.cumulative_counts(judge_runner.read_jsonl(run_dir / "judgments.jsonl"))
    manifest_mod.bind_judgments(run_dir, judgments_path=run_dir / "judgments.jsonl", report_path=report,
                                judge_of_record={"judge_model": judge_model, "billing_channel": "anthropic",
                                                 "price_source": "engine", "judged_utc": side["run_utc"],
                                                 "cost_usd": side["cost_usd"], "truncated": side["truncated"],
                                                 "planned": side["planned"], "judged": totals["judged"],
                                                 "null": totals["null"], "not_applicable": totals["not_applicable"],
                                                 "judge_max_tokens": judge_max_tokens, "temperature": 0.0})
    assert manifest_mod.verify_run(run_dir) == []
    return run_dir


def _params(**over) -> dict:
    """The params job's resolved outputs for a paid rejudge (strings), with the fire's nonce."""
    p = {"mode": "rejudge", "source_runs": "run_4242_1", "judge": "true", "judge_model": PAID_JUDGE,
         "judge_max_spend": "1.00", "judge_max_tokens": "300", "commit_outputs": "true",
         "seeds_file": str(framework.SEED_FILE), "_nonce": "rj-1"}
    p.update(over)
    return p


def _plan(runs: Path, root: Path, *, journal: list[dict] | None = None, run_id: str = "777", **over) -> dict:
    return rejudge.make_plan(params=_params(**over), runs_dir=runs, rejudge_root=root, journal_entries=journal or [],
                             workflow_run_id=run_id, workflow_run_attempt="1", commit=COMMIT)


def _mock_factory(spec: str, plans: list) -> judge_runner.MockJudge:
    """The judge client for tests: first declared value for every prompt, under the spec the plan names (so a paid
    spec is priced at its registry rate and the sidecar books a real-looking cost)."""
    answers = rejudge.mock_answers(plans)
    return judge_runner.MockJudge(lambda p: answers[p], model_spec=spec)


def _tree_digest(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file()}


@pytest.fixture
def layout(tmp_path, seed_set):
    runs = tmp_path / "data" / "petri" / "runs"
    _land(runs, "run_4242_1", seed_set)
    return runs, tmp_path / "data" / "petri" / "rejudge"


# ------------------------------------------------------------ names and mirrors


def test_the_fire_path_mirrors_the_lanes_names():
    """scripts/fire_trigger.py imports nothing from the lane; its copies of the lane's names are held equal here."""
    assert ft.PETRI_REJUDGE_MODE == rejudge.MODE and ft.PETRI_REJUDGE_MOCK_JUDGE == rejudge.MOCK_JUDGE
    assert ft.PETRI_REJUDGE_JUDGE_SUFFIX == rejudge.JUDGE_REPORT_SUFFIX_PATTERN
    assert ft.PETRI_REJUDGE_OUTPUT_FILES == rejudge.OUTPUT_FILES
    assert ft.PETRI_REJUDGE_STEM_RE.pattern == rejudge.STEM_PATTERN
    assert (ROOT / ft.PETRI_REJUDGE_RELPATH) == rejudge.DEFAULT_ROOT
    from scripts.petri_audit import spend

    for spec in (PAID_JUDGE, "x-ai/grok-4.3", "openrouter:google/gemini-3.5-flash", "claude-haiku-4-5",
                 "anthropic:claude-haiku-4-5", "openai", "xai", "mockllm/judge", "openrouter:x-ai/grok-4.3"):
        assert ft.petri_rejudge_slug(spec) == rejudge.judge_slug(spec), spec
        assert ft.petri_judge_inspect_name(spec) == spend.registry_spec_to_inspect(spec), spec
    assert rejudge.judge_slug(PAID_JUDGE) == PAID_SLUG
    for bad in ("", "::", "/..", "..", "-"):
        with pytest.raises(rejudge.RejudgeError):
            rejudge.judge_slug(bad)
        with pytest.raises(ValueError):
            ft.petri_rejudge_slug(bad)
    assert not rejudge.DEFAULT_ROOT.is_relative_to(ROOT / "data" / "petri" / "runs"), "never under the runs directory"


def test_source_runs_are_distinct_run_stems():
    assert rejudge.parse_source_runs("run_1_1 run_2_1") == ["run_1_1", "run_2_1"]
    assert rejudge.parse_source_runs(["run_1_1"]) == ["run_1_1"]
    for bad, needle in (("", "needs source_runs"), ("run_1_1 run_1_1", "names a run twice"),
                        ("run_1", "are not run stems"), ("../run_1_1", "are not run stems"),
                        ("run_１_1", "are not run stems"), (None, "space-separated")):
        with pytest.raises(rejudge.RejudgeError, match=needle):
            rejudge.parse_source_runs(bad)


def test_two_spellings_of_the_judge_of_record_are_one_judge():
    assert rejudge.same_judge("claude-haiku-4-5", "anthropic:claude-haiku-4-5")
    assert rejudge.same_judge(" claude-haiku-4-5", "claude-haiku-4-5")
    assert not rejudge.same_judge(PAID_JUDGE, "claude-haiku-4-5")
    with pytest.raises(rejudge.RejudgeError, match="cannot be resolved"):
        rejudge.same_judge("openrouter", "claude-haiku-4-5")          # a bare provider with no consumer default


# ------------------------------------------------------------ plan and execution


def test_a_rehearsal_plans_runs_and_verifies_without_writing_under_the_runs_directory(layout):
    runs, root = layout
    before = _tree_digest(runs)
    plan = _plan(runs, root, judge_model=rejudge.MOCK_JUDGE, commit_outputs="false", judge_max_spend="0.01", _nonce="")
    assert plan["rehearsal"] is True and plan["fire"]["journal_nonce"] is None
    (source,) = plan["sources"]
    assert source["run_stem"] == "run_4242_1" and source["source"]["judge_of_record"]["judge_model"] == JUDGE_OF_RECORD
    assert source["planned"] == source["source"]["judge_of_record"]["planned"]
    outcome = rejudge.execute(plan, started_dir=root.parent / "started")
    (result,) = outcome["results"]
    assert result["status"] == "complete" and outcome["spent_usd"] == 0.0 and not outcome["aborted"]
    out_dir = root / "mockllm-judge" / "run_4242_1"
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(rejudge.OUTPUT_FILES + ("run_4242_1.rejudge_777.judge.report.json",))
    assert rejudge.verify_output(out_dir, runs) == []
    assert _tree_digest(runs) == before, "nothing under the runs directory is written, the chain file included"
    m = framework.load_json(out_dir / rejudge.MANIFEST_NAME)
    assert m["rehearsal"] is True and m["exploratory"] is True and m["cost_usd"] == 0.0
    assert m["counts"]["planned"] == source["planned"] and m["instrument"]["parity_with_judge_of_record"] == "exact"
    rows = judge_runner.read_jsonl(out_dir / rejudge.JUDGMENTS_NAME)
    assert {r["judge_model"] for r in rows} == {rejudge.MOCK_JUDGE} and len(rows) == source["planned"]
    # the analysis rows are the per-judgment projection (judge_runner.analysis_rows), one per judgment
    assert len(judge_runner.read_jsonl(out_dir / rejudge.ANALYSIS_NAME)) == len(rows)


def test_a_paid_rejudge_books_its_judge_to_its_own_fire_on_the_judges_channel(layout):
    runs, root = layout
    plan = _plan(runs, root)
    assert plan["rehearsal"] is False and plan["judge_slug"] == PAID_SLUG and plan["fire"]["journal_nonce"] == "rj-1"
    outcome = rejudge.execute(plan, started_dir=root.parent / "started", client_factory=_mock_factory, environ=KEYS)
    out_dir = root / PAID_SLUG / "run_4242_1"
    report = framework.load_json(out_dir / "run_4242_1.rejudge_777.judge.report.json")
    assert report["journal_nonce"] == "rj-1" and report["billing_channel"] == "openrouter"
    assert report["task"] == rejudge.TASK and report["source_run_stem"] == "run_4242_1"
    assert report["rejudge_workflow_run_id"] == "777" and report["rejudge_commit"] == COMMIT
    assert report["judge_model"] == PAID_JUDGE and report["cost_basis"] == "cumulative_from_records"
    assert report["price_source"] == "registry:openrouter:pricing" and report["input_per_mtok"] == 0.8
    assert report["max_spend_usd"] == 1.0 == report["fire_judge_max_spend_usd"] and report["fire_spent_before_usd"] == 0.0
    assert 0 < report["cost_usd"] <= 1.0 and outcome["spent_usd"] == pytest.approx(report["cost_usd"])
    assert rejudge.verify_output(out_dir, runs) == []
    m = framework.load_json(out_dir / rejudge.MANIFEST_NAME)
    assert m["judge"]["billing_channel"] == "openrouter" and m["fire"]["journal_nonce"] == "rj-1"
    assert m["source"]["judgments_sha256"] == framework.sha256_file(runs / "run_4242_1" / "judgments.jsonl")
    assert m["source"]["manifest_sha256"] == framework.sha256_file(runs / "run_4242_1" / "manifest.json")


def test_the_judge_of_record_or_another_allowance_is_refused(layout):
    runs, root = layout
    for spec in (JUDGE_OF_RECORD, "anthropic:claude-haiku-4-5"):
        with pytest.raises(rejudge.RejudgeError, match="is its judge of record"):
            _plan(runs, root, judge_model=spec)
    with pytest.raises(rejudge.RejudgeError, match="ran with judge_max_tokens 300"):
        _plan(runs, root, judge_max_tokens="500")
    with pytest.raises(rejudge.RejudgeError, match="spelled exactly"):
        _plan(runs, root, judge_model=f" {PAID_JUDGE}")
    with pytest.raises(rejudge.RejudgeError, match="never committed"):
        _plan(runs, root, judge_model=rejudge.MOCK_JUDGE, commit_outputs="true")
    with pytest.raises(rejudge.RejudgeError, match="carries its fire's _nonce"):
        _plan(runs, root, _nonce="")
    with pytest.raises(rejudge.RejudgeError, match="judge true"):
        _plan(runs, root, judge="false")
    # a judge the registry cannot bill correctly is refused before any call (spend.judge_key_routing_problems)
    with pytest.raises(rejudge.RejudgeError, match="GEMINI_API_KEY"):
        _plan(runs, root, judge_model="google:gemini-3.5-flash")
    # an OpenRouter slug with no reviewed price is refused (spend.openrouter_price_problems)
    with pytest.raises(rejudge.RejudgeError, match="unreviewed_openrouter_price"):
        _plan(runs, root, judge_model="openrouter:openai/gpt-5.5")
    with pytest.raises(rejudge.RejudgeError, match="first attempt only"):
        rejudge.make_plan(params=_params(), runs_dir=runs, rejudge_root=root, journal_entries=[],
                          workflow_run_id="777", workflow_run_attempt="2", commit=COMMIT)


def test_a_directory_holding_a_regrade_is_never_written_again(layout):
    runs, root = layout
    rejudge.execute(_plan(runs, root), started_dir=root.parent / "s1", client_factory=_mock_factory, environ=KEYS)
    out_dir = root / PAID_SLUG / "run_4242_1"
    before = _tree_digest(out_dir)
    with pytest.raises(rejudge.RejudgeError, match="already holds a re-grade"):
        _plan(runs, root, run_id="778", _nonce="rj-2")
    assert _tree_digest(out_dir) == before
    # the fire path refuses the same directory before it would journal a reservation
    repo = runs.parents[2]
    problems = ft.petri_rejudge_source_problems(repo, "petri-audit", _params(_nonce="rj-2"))
    assert len(problems) == 1 and "already holds a re-grade" in problems[0], problems
    # and the plan bound when the directory was free is refused at execution once a re-grade appeared there
    other = tmp = root.parent / "second_root"
    plan = _plan(runs, tmp, run_id="779", _nonce="rj-3")
    (other / PAID_SLUG / "run_4242_1").mkdir(parents=True)
    (other / PAID_SLUG / "run_4242_1" / rejudge.JUDGMENTS_NAME).write_text("", encoding="utf-8")
    with pytest.raises(rejudge.RejudgeError, match="already holds a re-grade"):
        rejudge.execute(plan, started_dir=root.parent / "s3", client_factory=_mock_factory, environ=KEYS)


def test_a_retry_is_admitted_beside_an_earlier_failed_fires_sidecar_which_it_leaves_as_it_is(layout):
    runs, root = layout
    out_dir = root / PAID_SLUG / "run_4242_1"
    out_dir.mkdir(parents=True)
    prior = out_dir / rejudge.judge_report_name("run_4242_1", "700")
    framework.write_json(prior, {"judge_model": PAID_JUDGE, "source_run_stem": "run_4242_1", "journal_nonce": "rj-0",
                                 "cost_usd": 0.01})
    journal = [{"trigger": "petri-audit", "nonce": "rj-0"}]
    plan = _plan(runs, root, journal=journal)
    assert plan["sources"][0]["prior_judge_reports"] == [
        {"path": prior.name, "sha256": framework.sha256_file(prior), "journal_nonce": "rj-0"}]
    digest = framework.sha256_file(prior)
    rejudge.execute(plan, started_dir=root.parent / "s", client_factory=_mock_factory, environ=KEYS)
    assert framework.sha256_file(prior) == digest, "the earlier fire's sidecar is a spend record, never rewritten"
    assert rejudge.verify_output(out_dir, runs) == []
    # refusals: a nonce no fire accounts for, another judge's sidecar, this fire's own nonce, a stray file
    for body, journal_entries, needle in (
            ({"judge_model": PAID_JUDGE, "source_run_stem": "run_4242_1", "journal_nonce": "ghost"}, journal,
             "0 petri-audit journal entries carry its nonce"),
            ({"judge_model": "x-ai/grok-4.3", "source_run_stem": "run_4242_1", "journal_nonce": "rj-0"}, journal,
             "a directory holds one judge's re-grades of one run"),
            ({"judge_model": PAID_JUDGE, "source_run_stem": "run_4242_1", "journal_nonce": "rj-1"},
             [{"trigger": "petri-audit", "nonce": "rj-1"}], "carries this fire's nonce")):
        fresh = root.parent / f"root_{abs(hash(needle))}"
        d = fresh / PAID_SLUG / "run_4242_1"
        d.mkdir(parents=True)
        framework.write_json(d / rejudge.judge_report_name("run_4242_1", "700"), body)
        with pytest.raises(rejudge.RejudgeError, match=needle):
            _plan(runs, fresh, journal=journal_entries)
    stray = root.parent / "stray_root" / PAID_SLUG / "run_4242_1"
    stray.mkdir(parents=True)
    (stray / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(rejudge.RejudgeError, match="holds files other than earlier rejudge fires"):
        _plan(runs, root.parent / "stray_root")
    # a bound sidecar that changes between the plan and the execution is refused before any call
    changed_root = root.parent / "changed_root"
    d = changed_root / PAID_SLUG / "run_4242_1"
    d.mkdir(parents=True)
    bound = d / rejudge.judge_report_name("run_4242_1", "700")
    framework.write_json(bound, {"judge_model": PAID_JUDGE, "source_run_stem": "run_4242_1", "journal_nonce": "rj-0"})
    plan = _plan(runs, changed_root, journal=journal)
    bound.write_text(bound.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(rejudge.RejudgeError, match="changed after the rejudge bound it"):
        rejudge.execute(plan, started_dir=root.parent / "s4", client_factory=_mock_factory, environ=KEYS)
    assert not (d / rejudge.JUDGMENTS_NAME).exists()


def test_a_source_run_that_is_not_landed_chained_verified_and_judged_is_refused(tmp_path, seed_set):
    runs = tmp_path / "runs"
    root = tmp_path / "rejudge"
    run_dir = _land(runs, "run_4242_1", seed_set)
    with pytest.raises(rejudge.RejudgeError, match="no landed run"):
        _plan(runs, root, source_runs="run_9_1")
    chain = runs / manifest_mod.CHAIN_FILE
    original = chain.read_text(encoding="utf-8")
    chain.write_text("", encoding="utf-8")
    with pytest.raises(rejudge.RejudgeError, match="does not name run_4242_1/manifest.json"):
        _plan(runs, root)
    chain.write_text(original, encoding="utf-8")
    transcripts_file = run_dir / "transcripts.jsonl"
    body = transcripts_file.read_bytes()
    transcripts_file.write_bytes(body + b"\n")
    with pytest.raises(rejudge.RejudgeError, match="does not verify on its own"):
        _plan(runs, root)
    transcripts_file.write_bytes(body)
    assert _plan(runs, root)["sources"][0]["run_stem"] == "run_4242_1"


def test_parity_with_the_judge_of_record_is_exact_or_refused(layout, seed_set):
    """The rejudge applies the instrument the judge of record applied: the same judgments, each shown the same
    rendered prompt and context. A prompt file, the rubric or the planner changing since the source run was judged
    is refused by name before any call (landed w2e1 is refused this way: its baseline-persistence prompt predates
    2026-09-23)."""
    runs, _root = layout
    plans, _manifest, _seeds = rejudge.build_plans(runs, "run_4242_1")
    rows = judge_runner.read_jsonl(runs / "run_4242_1" / "judgments.jsonl")
    assert rejudge.parity_problems(plans, rows) == []
    judged = next(i for i, r in enumerate(rows) if r["rendered_sha256"])
    altered = [dict(r) for r in rows]
    altered[judged]["rendered_sha256"] = "f" * 64
    (problem,) = rejudge.parity_problems(plans, altered)
    assert "1 judgment(s) whose rendered prompt, context or not-applicable reason differs" in problem
    renamed = [dict(r) for r in rows]
    renamed[judged]["prompt_file_digest"] = "000000000000"
    problems = rejudge.parity_problems(plans, renamed)
    assert any("1 planned judgment(s) the judge of record never made" in p for p in problems)
    assert any("1 judgment(s) of the judge of record that are no longer planned" in p for p in problems)
    # a judgment the plan now records as not applicable, where the judge of record was shown a prompt, differs too
    import dataclasses

    index = next(i for i, p in enumerate(plans) if p.prompt is not None)
    withdrawn = list(plans)
    withdrawn[index] = dataclasses.replace(plans[index], prompt=None, not_applicable_reason="another reason")
    assert "differs" in rejudge.parity_problems(withdrawn, rows)[0]
    # a retried null row is read by its latest row, as cumulative_counts reads it
    assert rejudge.parity_problems(plans, rows + [dict(rows[judged])]) == []
    # names identifiers only: never the prompt or the reply
    assert TEXTS["reply_minimised"] not in problem and "turn" in problem


def test_verification_names_every_alteration(layout):
    runs, root = layout
    rejudge.execute(_plan(runs, root), started_dir=root.parent / "s", client_factory=_mock_factory, environ=KEYS)
    out_dir = root / PAID_SLUG / "run_4242_1"
    assert rejudge.verify_output(out_dir, runs) == []
    judgments = out_dir / rejudge.JUDGMENTS_NAME
    body = judgments.read_bytes()
    judgments.write_bytes(body + b"{}\n")
    assert any("judgments: judgments.jsonl does not digest to its recorded value" in p
               for p in rejudge.verify_output(out_dir, runs))
    judgments.write_bytes(body)
    (out_dir / "extra.json").write_text("{}", encoding="utf-8")
    assert any("holds files a rejudge does not write (extra.json)" in p for p in rejudge.verify_output(out_dir, runs))
    (out_dir / "extra.json").unlink()
    manifest_path = out_dir / rejudge.MANIFEST_NAME
    m = framework.load_json(manifest_path)
    framework.write_json(manifest_path, dict(m, cost_usd=0.0))
    assert any("manifest_sha256 does not match" in p for p in rejudge.verify_output(out_dir, runs))
    framework.write_json(manifest_path, m)
    # the source run must still be the bytes the rejudge read, and still verify
    source_manifest = runs / "run_4242_1" / "manifest.json"
    original = source_manifest.read_bytes()
    source_manifest.write_bytes(original + b"\n")
    assert any("is not the bytes the rejudge read" in p for p in rejudge.verify_output(out_dir, runs))
    source_manifest.write_bytes(original)
    assert rejudge.verify_output(out_dir, runs) == []
    # a re-grade moved under another judge's directory is refused
    moved = root / "x-ai-grok-4.3" / "run_4242_1"
    moved.parent.mkdir(parents=True)
    out_dir.rename(moved)
    assert any("re-grades under" in p for p in rejudge.verify_output(moved, runs))


def test_one_fire_shares_one_ceiling_across_its_source_runs(tmp_path, seed_set):
    runs, root = tmp_path / "runs", tmp_path / "rejudge"
    _land(runs, "run_4242_1", seed_set)
    _land(runs, "run_4343_1", seed_set)
    plan = _plan(runs, root, source_runs="run_4242_1 run_4343_1", judge_max_spend="1.00")
    outcome = rejudge.execute(plan, started_dir=tmp_path / "s", client_factory=_mock_factory, environ=KEYS)
    assert [r["status"] for r in outcome["results"]] == ["complete", "complete"]
    first = framework.load_json(root / PAID_SLUG / "run_4242_1" / "run_4242_1.rejudge_777.judge.report.json")
    second = framework.load_json(root / PAID_SLUG / "run_4343_1" / "run_4343_1.rejudge_777.judge.report.json")
    assert second["fire_spent_before_usd"] == pytest.approx(first["cost_usd"])
    assert second["max_spend_usd"] + second["fire_spent_before_usd"] == pytest.approx(1.0)
    assert outcome["spent_usd"] == pytest.approx(first["cost_usd"] + second["cost_usd"])
    for stem in ("run_4242_1", "run_4343_1"):
        assert rejudge.verify_output(root / PAID_SLUG / stem, runs) == []
    # a ceiling the first run exhausts truncates it, and the second is not started and writes nothing
    tight_root = tmp_path / "tight"
    plan = _plan(runs, tight_root, source_runs="run_4242_1 run_4343_1")
    plan["judge_max_spend_usd"] = 0.0001          # a judge that spends past the estimate, which the plan cannot see
    outcome = rejudge.execute(plan, started_dir=tmp_path / "s2", client_factory=_mock_factory, environ=KEYS)
    assert [r["status"] for r in outcome["results"]] == ["truncated", "not_started"]
    assert not (tight_root / PAID_SLUG / "run_4343_1").exists()
    m = framework.load_json(tight_root / PAID_SLUG / "run_4242_1" / rejudge.MANIFEST_NAME)
    assert m["counts"]["truncated"] is True and m["counts"]["judged"] < m["counts"]["planned"]
    assert rejudge.verify_output(tight_root / PAID_SLUG / "run_4242_1", runs) == []


class _Raising(judge_runner.MockJudge):
    def complete(self, prompt, **kw):
        raise RuntimeError("provider down")


def test_a_judge_that_raises_leaves_its_sidecar_no_outputs_and_ends_the_fire(tmp_path, seed_set):
    runs, root = tmp_path / "runs", tmp_path / "rejudge"
    _land(runs, "run_4242_1", seed_set)
    _land(runs, "run_4343_1", seed_set)
    plan = _plan(runs, root, source_runs="run_4242_1 run_4343_1")
    outcome = rejudge.execute(plan, started_dir=tmp_path / "s",
                              client_factory=lambda spec, plans: _Raising(lambda p: "", model_spec=spec), environ=KEYS)
    assert outcome["aborted"] and [r["status"] for r in outcome["results"]] == ["aborted", "not_started"]
    d = root / PAID_SLUG / "run_4242_1"
    report = framework.load_json(d / "run_4242_1.rejudge_777.judge.report.json")
    assert report["aborted"] is True and report["cost_usd"] > 0 and report["journal_nonce"] == "rj-1"
    assert not (d / rejudge.MANIFEST_NAME).exists() and not (d / rejudge.ANALYSIS_NAME).exists()
    assert not (root / PAID_SLUG / "run_4343_1").exists()
    # the workflow commits that sidecar alone (its outputs step needs every prior step green), so the next checkout
    # holds the sidecar and nothing else; a retry fire is admitted beside it
    (d / rejudge.JUDGMENTS_NAME).unlink()
    plan = _plan(runs, root, source_runs="run_4242_1", run_id="778", _nonce="rj-2",
                 journal=[{"trigger": "petri-audit", "nonce": "rj-1"}])
    assert [p["path"] for p in plan["sources"][0]["prior_judge_reports"]] == ["run_4242_1.rejudge_777.judge.report.json"]


def test_the_fallback_books_the_allotment_of_a_judge_that_started_and_left_no_sidecar(layout):
    runs, root = layout
    plan = _plan(runs, root, judge_max_spend="0.75")
    started = root.parent / "started"
    started.mkdir()
    framework.write_json(rejudge.started_marker(started, "run_4242_1"),
                         {"run_stem": "run_4242_1", "max_spend_usd": 0.75, "fire_spent_before_usd": 0.0})
    (written,) = rejudge.impute_missing_reports(plan, started)
    report = framework.load_json(written)
    assert written.name == "run_4242_1.rejudge_777.judge.report.json"
    assert report["cost_usd"] == 0.75 == report["max_spend_usd"]
    assert report["cost_basis"] == "ceiling_imputed:judge_aborted_without_sidecar" and report["journal_nonce"] == "rj-1"
    assert report["billing_channel"] == "openrouter" and report["fire_judge_max_spend_usd"] == 0.75
    assert rejudge.impute_missing_reports(plan, started) == [], "a sidecar that exists is never rewritten"
    # a run whose judge never started (no marker) books nothing
    empty = root.parent / "none_started"
    empty.mkdir()
    assert rejudge.impute_missing_reports(_plan(runs, root.parent / "other"), empty) == []
    # reconciliation reads the imputed sidecar as the fallback writer's: the ceiling it books is its own
    assert reconcile._basis_problems("x", report, 0.75, judge=True) == []


# ------------------------------------------------------------ the CLI


def test_the_cli_plans_runs_verifies_and_summarises_a_rehearsal(layout, capsys):
    runs, root = layout
    params = root.parent / "params.json"
    framework.write_json(params, _params(judge_model=rejudge.MOCK_JUDGE, commit_outputs="false", _nonce=""))
    plan = root.parent / "plan.json"
    base = ["--runs-dir", str(runs)]
    assert cli.main(["rejudge-plan", "--params-file", str(params), *base, "--rejudge-root", str(root),
                     "--journal", str(root.parent / "no_journal.jsonl"), "--rejudge-run-id", "5",
                     "--rejudge-run-attempt", "2", "--rejudge-commit", COMMIT, "--out", str(plan)]) == 0
    assert "rehearsal, $0" in capsys.readouterr().out
    assert cli.main(["rejudge", "--plan", str(plan), "--started-dir", str(root.parent / "started")]) == 0
    assert "run_4242_1: complete" in capsys.readouterr().out
    exports = root.parent / "exports"
    assert cli.main(["verify-rejudge", "--plan", str(plan), *base, "--copy-to", str(exports)]) == 0
    assert (exports / "mockllm-judge" / "run_4242_1" / rejudge.MANIFEST_NAME).is_file()
    assert cli.main(["verify-rejudge", "--root", str(root), *base]) == 0
    capsys.readouterr()
    assert cli.main(["rejudge-summary", "--plan", str(plan)]) == 0
    summary = capsys.readouterr().out
    assert "| run_4242_1 | complete |" in summary and TEXTS["reply_minimised"] not in summary
    # a refused plan: the summary says so and the spend report books nothing
    missing = root.parent / "missing_plan.json"
    assert cli.main(["rejudge-summary", "--plan", str(missing)]) == 0
    assert "refused before any call" in capsys.readouterr().out
    assert cli.main(["rejudge-spend-report", "--plan", str(missing), "--started-dir", str(root.parent)]) == 0
    framework.write_json(params, _params(judge_model=JUDGE_OF_RECORD))
    assert cli.main(["rejudge-plan", "--params-file", str(params), *base, "--rejudge-root", str(root),
                     "--rejudge-run-id", "6", "--rejudge-run-attempt", "1", "--rejudge-commit", COMMIT,
                     "--out", str(root.parent / "refused.json")]) == 12
    assert "is its judge of record" in capsys.readouterr().err


def test_the_offline_rehearsal_writes_outside_the_repository_only(layout, capsys):
    runs, root = layout
    assert cli.main(["rejudge-rehearse", "--source-run", "run_4242_1", "--runs-dir", str(runs),
                     "--out-root", str(ROOT / "data" / "petri" / "rejudge_rehearsal")]) == 2
    assert "is inside the repository" in capsys.readouterr().err
    assert not (ROOT / "data" / "petri" / "rejudge_rehearsal").exists()
    out = root.parent / "rehearsal"
    assert cli.main(["rejudge-rehearse", "--source-run", "run_4242_1", "--runs-dir", str(runs),
                     "--out-root", str(out)]) == 0
    text = capsys.readouterr().out
    assert "run_4242_1: complete" in text and "parity with judge of record 'claude-haiku-4-5': exact" in text
    assert "verify: clean" in text and (out / "mockllm-judge" / "run_4242_1" / rejudge.MANIFEST_NAME).is_file()


# ------------------------------------------------------------ spend: reconciliation and the ledger


def _journal(path: Path, *entries: dict) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def _rejudge_entry(nonce: str = "rj-1", max_spend: float = 1.0, **extra) -> dict:
    e = {"trigger": "petri-audit", "fired_utc": "2026-09-20T00:00:00Z", "commit": "", "note": "rejudge",
         "resolved": False, "evicted": False, "nonce": nonce, "max_spend": max_spend, "lane": "openrouter"}
    e.update(extra)
    return e


def test_reconciliation_joins_every_rejudge_sidecar_to_its_own_fire(tmp_path, seed_set):
    runs, root = tmp_path / "runs", tmp_path / "rejudge"
    _land(runs, "run_4242_1", seed_set)
    _land(runs, "run_4343_1", seed_set)
    rejudge.execute(_plan(runs, root, source_runs="run_4242_1 run_4343_1"), started_dir=tmp_path / "s",
                    client_factory=_mock_factory, environ=KEYS)
    journal = tmp_path / "journal.jsonl"
    _journal(journal, _rejudge_entry())
    # the fixture's source runs carry a judge sidecar but no target sidecar, which reconciliation rightly names; the
    # rejudge fire is reconciled here against a runs directory holding nothing, so every problem left is the rejudge's
    runs = tmp_path / "elsewhere" / "runs"
    runs.mkdir(parents=True)
    result = reconcile.reconcile(journal, runs, rejudge_dir=root)
    (row,) = result["paid_fires"]
    assert row["status"] == "landed (rejudge)" and result["rejudge_sidecars"] == 2
    costs = [framework.load_json(p)["cost_usd"] for p in sorted(root.glob("*/*/*.report.json"))]
    assert row["judge_cost_usd"] == pytest.approx(sum(costs)) == row["total_usd"]
    assert result["problems"] == [], result["problems"]
    assert result["sidecars"] == {"target": 0, "judge": 0}, "the shape of the runs block is unchanged"
    assert "2 rejudge." in reconcile.render_markdown(result)
    # the default rejudge root is the runs directory's sibling
    assert reconcile.reconcile(journal, runs)["rejudge_sidecars"] == 0
    assert reconcile.reconcile(journal, root.parent / "runs")["rejudge_sidecars"] == 2
    # a commitment other than the fire's recorded ceiling, a wrong lane, or no fire at all is named
    _journal(journal, _rejudge_entry(max_spend=2.0))
    assert any("a rejudge fire reserves exactly the judge's ceiling" in p
               for p in reconcile.reconcile(journal, runs, rejudge_dir=root)["problems"])
    _journal(journal, _rejudge_entry(lane="anthropic"))
    assert any("books the openrouter account but the fire reserved its commitment on anthropic" in p
               for p in reconcile.reconcile(journal, runs, rejudge_dir=root)["problems"])
    _journal(journal)
    problems = reconcile.reconcile(journal, runs, rejudge_dir=root)["problems"]
    assert sum("matches no paid petri-audit journal entry" in p for p in problems) == 2
    # a sidecar copied into another run's directory is named by its identity
    _journal(journal, _rejudge_entry())
    src = root / PAID_SLUG / "run_4343_1" / "run_4343_1.rejudge_777.judge.report.json"
    (root / PAID_SLUG / "run_4242_1" / "run_4343_1.rejudge_777.judge.report.json").write_bytes(src.read_bytes())
    problems = reconcile.reconcile(journal, runs, rejudge_dir=root)["problems"]
    assert any("records source run 'run_4343_1' but sits in 'run_4242_1'" in p for p in problems), problems


def test_the_ledger_folds_each_rejudge_sidecar_once_to_the_judges_channel(tmp_path, seed_set):
    runs, root = tmp_path / "data" / "petri" / "runs", tmp_path / "data" / "petri" / "rejudge"
    _land(runs, "run_4242_1", seed_set)
    rejudge.execute(_plan(runs, root), started_dir=tmp_path / "s", client_factory=_mock_factory, environ=KEYS)
    report = next(root.glob("*/*/*.report.json"))
    cost = framework.load_json(report)["cost_usd"]
    day = framework.load_json(report)["run_utc"][:10]
    empty = tmp_path / "empty"
    empty.mkdir()
    dash, ledger = tmp_path / "dashboard.json", tmp_path / "ledger.md"
    ledger.write_text("# ledger\n", encoding="utf-8")
    argv = ["--simulated-dir", str(empty), "--advice-dir", str(empty), "--pab-dir", str(empty),
            "--petri-dir", str(empty), "--petri-rejudge-dir", str(root), "--trace-dir", str(empty),
            "--dashboard", str(dash), "--ledger", str(ledger), "--date", day]
    assert ledger_update.main(argv) == 0
    spend = framework.load_json(dash)["spend"]
    assert spend["entries_seen"] == [report.name] and spend["entries_folded"][report.name] == pytest.approx(cost)
    assert spend["by_day_by_channel"]["openrouter"][day] == pytest.approx(round(cost, 4))
    assert "anthropic" not in spend["by_day_by_channel"]
    before = dash.read_bytes()
    assert ledger_update.main(argv) == 0
    assert dash.read_bytes() == before, "folded once: a second pass books nothing"
    assert ledger.read_text(encoding="utf-8").count(report.name) == 1
    # the source runs' own sidecars are a different scan: the rejudge root is never folded as runs
    journal = tmp_path / "journal.jsonl"
    _journal(journal, _rejudge_entry(max_spend=1.0))
    result = reconcile.reconcile(journal, runs, dashboard_path=dash, rejudge_dir=root)
    (row,) = result["paid_fires"]
    assert row["folded"] is True and report.name not in result["unfolded_sidecars"]


# ------------------------------------------------------------ PR #41 review


def test_an_earlier_runs_completed_regrade_survives_a_later_runs_abort(tmp_path, seed_set, capsys):
    """Finding 1: the judge aborting on the second source run failed the Rejudge step, and verification, upload and
    the re-grade commit were skipped, so the branch kept only sidecars and a retry paid again for run 1. The verify
    step now runs whenever the plan succeeded: it verifies the re-grades that wrote their manifest, and writes
    exactly what the commit stages (those directories and the fire's sidecars, never the aborted run's rows)."""
    runs, root = tmp_path / "runs", tmp_path / "rejudge"
    _land(runs, "run_4242_1", seed_set)
    _land(runs, "run_4343_1", seed_set)
    plan = _plan(runs, root, source_runs="run_4242_1 run_4343_1")
    calls = {"n": 0}

    def factory(spec, plans):
        calls["n"] += 1
        if calls["n"] == 2:
            return _Raising(lambda p: "", model_spec=spec)            # the provider fails on the second source run
        return _mock_factory(spec, plans)

    outcome = rejudge.execute(plan, started_dir=tmp_path / "s", client_factory=factory, environ=KEYS)
    assert [r["status"] for r in outcome["results"]] == ["complete", "aborted"] and outcome["aborted"]
    plan_path = tmp_path / "plan.json"
    framework.write_json(plan_path, plan)
    exports, verified, stage = tmp_path / "exports", tmp_path / "verified.txt", tmp_path / "stage.txt"
    assert cli.main(["verify-rejudge", "--plan", str(plan_path), "--runs-dir", str(runs), "--copy-to", str(exports),
                     "--verified-list", str(verified), "--stage-list", str(stage)]) == 0
    first, second = root / PAID_SLUG / "run_4242_1", root / PAID_SLUG / "run_4343_1"
    assert verified.read_text(encoding="utf-8").splitlines() == [str(first)]
    assert stage.read_text(encoding="utf-8").splitlines() == [
        str(first), str(second / "run_4343_1.rejudge_777.judge.report.json")], "never the aborted run's rows"
    assert (second / rejudge.JUDGMENTS_NAME).is_file(), "the aborted run's partial rows exist and are not staged"
    assert sorted(p.name for p in (exports / PAID_SLUG).iterdir()) == ["run_4242_1"], "only the verified re-grade"
    assert "run_4343_1" in capsys.readouterr().out
    # the branch after the commit steps: run 1's re-grade and both sidecars; the aborted run's rows never landed
    (second / rejudge.JUDGMENTS_NAME).unlink()
    with pytest.raises(rejudge.RejudgeError, match="run_4242_1: already holds a re-grade"):
        _plan(runs, root, source_runs="run_4242_1", run_id="778", _nonce="rj-2",
              journal=[{"trigger": "petri-audit", "nonce": "rj-1"}])
    retry = _plan(runs, root, source_runs="run_4343_1", run_id="778", _nonce="rj-2",
                  journal=[{"trigger": "petri-audit", "nonce": "rj-1"}])
    assert [p["path"] for p in retry["sources"][0]["prior_judge_reports"]] == ["run_4343_1.rejudge_777.judge.report.json"]
    # a directory that fails verification writes no list at all: the step fails closed and nothing is staged
    (first / rejudge.ANALYSIS_NAME).write_text("tampered\n", encoding="utf-8")
    verified.unlink()
    stage.unlink()
    assert cli.main(["verify-rejudge", "--plan", str(plan_path), "--runs-dir", str(runs),
                     "--verified-list", str(verified), "--stage-list", str(stage)]) == 6
    assert not verified.exists() and not stage.exists()


def test_a_judge_whose_key_is_absent_is_refused_before_any_marker_and_books_nothing(layout, monkeypatch, capsys):
    """Finding 2: the start marker was written before the first call, the provider client raised SystemExit on the
    empty key, nothing caught it, and the fallback booked the whole allotment for a call never made. The key is now
    checked before the marker: a named refusal, no marker, nothing imputed."""
    runs, root = layout
    plan = _plan(runs, root)
    started = root.parent / "started"
    for environ in ({}, {"OPENROUTER_API_KEY": ""}, {"OPENROUTER_API_KEY": "  "}, {"ANTHROPIC_API_KEY": "x"}):
        with pytest.raises(rejudge.RejudgeError, match="OPENROUTER_API_KEY, which is unset or empty"):
            rejudge.execute(plan, started_dir=started, client_factory=_mock_factory, environ=environ)
        assert not list(started.glob("*.json")), "no start marker for a judge that cannot call"
        assert rejudge.impute_missing_reports(plan, started) == [], "nothing booked"
        assert not (root / PAID_SLUG).exists()
    # through the CLI, with the process environment the workflow gives it
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    plan_path = root.parent / "plan.json"
    framework.write_json(plan_path, plan)
    assert cli.main(["rejudge", "--plan", str(plan_path), "--started-dir", str(started)]) == 13
    assert "OPENROUTER_API_KEY, which is unset or empty" in capsys.readouterr().err
    assert cli.main(["rejudge-spend-report", "--plan", str(plan_path), "--started-dir", str(started)]) == 0
    assert "nothing to impute" in capsys.readouterr().out and not list(root.glob("*/*/*.report.json"))
    # an Anthropic judge reads ANTHROPIC_API_KEY; the rehearsal reads no key at all
    assert "ANTHROPIC_API_KEY" in (rejudge.judge_key_problem("claude-sonnet-4-5", {}) or "")
    assert rejudge.judge_key_problem("claude-sonnet-4-5", {"ANTHROPIC_API_KEY": "x"}) is None
    assert rejudge.judge_key_problem(rejudge.MOCK_JUDGE, {}) is None


def test_the_plan_prices_the_regrade_from_the_judge_of_records_tokens_and_refuses_a_ceiling_below_it(layout, capsys):
    """Finding 3a: nothing sized the ceiling, and a truncated re-grade closes its directory for good. The plan prices
    every source run from the judge of record's recorded tokens at the new judge's registry price, prints that and
    the worst case, and refuses a ceiling below the expected cost plus one call's admission headroom."""
    from scripts.petri_audit import spend

    runs, root = layout
    plan = _plan(runs, root)
    rows = judge_runner.read_jsonl(runs / "run_4242_1" / "judgments.jsonl")
    judged = [r for r in rows if r["method"] == "judge"]
    tokens_in, tokens_out = sum(r["input_tokens"] for r in judged), sum(r["output_tokens"] for r in judged)
    price = spend.resolve_registry_price(PAID_JUDGE)
    est = plan["sources"][0]["estimate"]
    assert (est["calls"], est["recorded_input_tokens"], est["recorded_output_tokens"]) == (len(judged), tokens_in, tokens_out)
    assert est["expected_usd"] == pytest.approx(tokens_in * 0.8 / 1e6 + tokens_out * 4.75 / 1e6, abs=1e-6)
    assert est["worst_case_usd"] == pytest.approx(tokens_in * 0.8 / 1e6 + len(judged) * 300 * 4.75 / 1e6, abs=1e-6)
    assert (est["input_per_mtok"], est["output_per_mtok"]) == (price.input_per_mtok, price.output_per_mtok) == (0.8, 4.75)
    assert "close to the judge of record's" in est["assumption"]
    required = plan["estimate"]["required_usd"]
    assert required == pytest.approx(est["expected_usd"] + est["last_call_headroom_usd"]) and required > est["expected_usd"]
    with pytest.raises(rejudge.RejudgeError, match="is below the expected cost of the re-grade"):
        _plan(runs, root.parent / "tight", judge_max_spend=f"{required * 0.99:.8f}")
    _plan(runs, root.parent / "enough", judge_max_spend=f"{required:.8f}")
    # a judge of record row without usage is priced at the ceiling's own bound, and counted
    no_usage = [dict(r, input_tokens=None, output_tokens=None) if r is judged[0] else r for r in rows]
    plans, _m, _s = rejudge.build_plans(runs, "run_4242_1")
    bounded = rejudge.estimate_cost(plans, no_usage, PAID_JUDGE, 300)
    assert bounded["calls_without_recorded_usage"] == 1 and bounded["recorded_output_tokens"] > tokens_out
    # the CLI prints both figures and the assumption
    params = root.parent / "params.json"
    framework.write_json(params, _params())
    assert cli.main(["rejudge-plan", "--params-file", str(params), "--runs-dir", str(runs), "--rejudge-root", str(root),
                     "--journal", str(root.parent / "none.jsonl"), "--rejudge-run-id", "5", "--rejudge-run-attempt", "1",
                     "--rejudge-commit", COMMIT, "--out", str(root.parent / "plan.json")]) == 0
    out = capsys.readouterr().out
    assert f"expected ${est['expected_usd']:.4f}" in out and f"worst case ${est['worst_case_usd']:.4f}" in out
    assert "ASSUMES the new judge's token counts are close to the judge of record's" in out


def test_the_manifest_and_summary_make_a_mostly_null_regrade_visible(layout, capsys):
    """Finding 3b: a re-grade that is complete but mostly null closed its directory looking like a success. The
    manifest records the share of the judgments that were not not-applicable which came back null, beside the judge
    of record's, and verification and the summary carry it."""
    runs, root = layout
    plan = _plan(runs, root)

    def mostly_unparseable(spec, plans):
        return judge_runner.MockJudge(lambda p: "no value here", model_spec=spec)

    rejudge.execute(plan, started_dir=root.parent / "s", client_factory=mostly_unparseable, environ=KEYS)
    out_dir = root / PAID_SLUG / "run_4242_1"
    m = framework.load_json(out_dir / rejudge.MANIFEST_NAME)
    c = m["counts"]
    assert c["judged"] == 0 and c["null"] > 0 and c["null_share"] == 1.0
    assert c["judge_of_record_null_share"] == 0.0, "the mock judge of record answered every call"
    assert m["estimate"]["expected_usd"] == plan["sources"][0]["estimate"]["expected_usd"]
    assert rejudge.verify_output(out_dir, runs) == []
    understated = {**m, "counts": {**c, "null_share": 0.0}}
    understated["manifest_sha256"] = rejudge.manifest_digest(understated)       # resealed: only the count is wrong
    framework.write_json(out_dir / rejudge.MANIFEST_NAME, understated)
    assert any("null_share" in p for p in rejudge.verify_output(out_dir, runs))
    framework.write_json(out_dir / rejudge.MANIFEST_NAME, m)
    plan_path = root.parent / "plan.json"
    framework.write_json(plan_path, plan)
    assert cli.main(["rejudge-summary", "--plan", str(plan_path)]) == 0
    assert "| 100.0% (0.0%) |" in capsys.readouterr().out
    assert rejudge.null_share(0, 0) is None and rejudge.null_share(3, 1) == 0.25 and rejudge.null_share(None, 1) is None
