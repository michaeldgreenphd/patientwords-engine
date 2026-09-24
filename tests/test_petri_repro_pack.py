"""Tests for the Petri lane's vendor reproduction packs (scripts/petri_audit/repro_pack.py).

Offline and synthetic: every run directory, the chain, the seed file, the prompt files, the plan and the section 10
analysis artifact are written under tmp_path. A landed wave-2 manifest is read (never written) as the template, so the
synthetic manifests pass the schema, digest and artifact checks of verify-run and verify-chain; every field the pack
reads is replaced. The disclosure log is always a temporary file, never ops/disclosure_log.jsonl. No medical
vocabulary: the texts are placeholders.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.petri_audit import cli
from scripts.petri_audit import repro_pack as rp
from scripts.petri_audit.framework import ROOT, load_json, prompt_canonical, sha256_file, sha256_text
from scripts.petri_audit.judge_runner import _advice_eval_module, rubric_digest
from scripts.petri_audit.manifest import CHAIN_FILE, seal_manifest, verify_chain, verify_run, write_manifest
from scripts.petri_audit.seeds import seed_digest

ae = _advice_eval_module()

LANDED = ROOT / "data" / "petri" / "runs"
TEMPLATE = load_json(LANDED / "run_35812312136_1" / "manifest.json")
READAPT_TEMPLATE = load_json(LANDED / "run_35937014168_1" / "manifest.json")["readapt"]
TARGET = "anthropic/claude-haiku-4-5"
JUDGE = "claude-haiku-4-5"
RUBRIC_REF = "data/advice_rubric.draft.json"
PROMPT_REF = "docs/framework/judge_prompts/outcomes/d1.draft.json"
RUBRIC = {"version": "t1", "tiers": [{"id": "t0", "label": "a", "definition": "d"}],
          "flags": [{"id": "f1", "definition": "d"}], "judge_instructions": "{tiers}{flags}{response}"}
PROMPT = {"dimension_id": "d1", "values": {"v1": "one", "v2": "two"}, "instructions": "{values}{turn_text}"}
SEEDS = {"seed_schema": {"version": "t"},
         "seeds": [{"seed_id": "s1", "text": "alpha"}, {"seed_id": "s2", "text": "beta"},
                   {"seed_id": "s9", "text": "unused"}]}
PLAN = {"fires": [{"journal_nonce": "f1", "campaign_epochs": {"original": 1}, "partition": "discovery"},
                  {"journal_nonce": "f2", "campaign_epochs": {"original": 2}, "partition": "prospective"}]}
# a sealed phrase no synthetic file contains: the seal scan runs and passes
REGISTRY = {"zq sealed placeholder phrase zq": "pairs_T#1"}


def _hex(label: str, n: int = 40) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:n]


def _jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _judgments(stem: str, judge: str = JUDGE, request_ids: bool = True) -> list[dict]:
    rdig = rubric_digest(RUBRIC)
    pdig = sha256_text(prompt_canonical(PROMPT))[:12]
    return [
        {"conversation_id": f"{stem}-c1", "kind": "tier", "key": "response_only", "prompt_ref": RUBRIC_REF,
         "prompt_file_digest": rdig, "judge_model": judge, "method": "judge", "value": "t0",
         "judge_request_id": "req_a" if request_ids else None, "served_model": "served-judge-1"},
        {"conversation_id": f"{stem}-c1", "kind": "outcome", "key": "d1", "prompt_ref": PROMPT_REF,
         "prompt_file_digest": pdig, "judge_model": judge, "method": "judge", "value": "v1",
         "judge_request_id": None, "served_model": "served-judge-1"},
        {"conversation_id": f"{stem}-c2", "kind": "outcome", "key": "d1", "prompt_ref": PROMPT_REF,
         "prompt_file_digest": pdig, "judge_model": judge, "method": "rule", "value": "not_applicable",
         "judge_request_id": None, "served_model": None},
    ]


def _write_run(runs: Path, stem: str, nonce: str, *, readapt: bool = False, target: str = TARGET,
               judge: str = JUDGE, seed_ids: tuple[str, ...] = ("s1", "s2"), transcript_text: str = "text") -> Path:
    """One landed synthetic run, sealed onto the chain head and appended to the chain."""
    run = runs / stem
    run.mkdir(parents=True)
    (run / "sanitised_log.json").write_text(json.dumps({
        "sanitiser": {"version": "t"}, "eval": {"model_roles": {"target": {"model": target}}},
        "samples": [{"events": [{"event": "model", "model": target, "timestamp": "2026-09-24T00:00:01+00:00",
                                 "call": None}, {"event": "info"}]}]}), encoding="utf-8")
    _jsonl(run / "transcripts.jsonl", [
        {"conversation_id": f"{stem}-c{i}", "source": {"model": target, "model_version": "served-target-1"},
         "turns": [{"turn_id": 1, "role": "user", "text": transcript_text}]} for i in (1, 2)])
    _jsonl(run / "rule_outcomes.jsonl", [{"conversation_id": f"{stem}-c1", "outcomes": []}])
    _jsonl(run / "judgments.jsonl", _judgments(stem, judge))
    _jsonl(run / "analysis_rows.jsonl", [{"judge_model": judge, "kind": "tier"}])
    (run / f"{stem}.report.json").write_text(json.dumps({"models": [{"model": target}], "journal_nonce": nonce}),
                                             encoding="utf-8")
    judge_report = f"{stem}.readapt_555.judge.report.json" if readapt else f"{stem}.judge.report.json"
    (run / judge_report).write_text(json.dumps({"judge_model": judge}), encoding="utf-8")
    m = copy.deepcopy(TEMPLATE)
    m.pop("readapt", None)
    m["run_id"] = stem
    m["models"]["target"].update(inspect_name=target, registry_spec=target)
    m["usage"]["by_role"] = [dict(m["usage"]["by_role"][0], calls=10)]
    m["usage"]["by_model"] = [dict(m["usage"]["by_model"][0], model=target, calls=10)]
    m["spend"]["journal_nonce"] = nonce
    seeds = {s["seed_id"]: s for s in SEEDS["seeds"]}
    m["seeds"] = [dict(TEMPLATE["seeds"][0], seed_id=s, seed_sha256=seed_digest(seeds[s])) for s in seed_ids]
    for fam, name in (("sanitised_log", "sanitised_log.json"), ("transcripts", "transcripts.jsonl"),
                      ("rule_outcomes", "rule_outcomes.jsonl"), ("judgments", "judgments.jsonl")):
        m["artifacts"][f"{fam}_path"] = f"{stem}/{name}"
        m["artifacts"][f"{fam}_sha256"] = sha256_file(run / name)
    m["artifacts"]["judge_of_record"].update(judge_model=judge, report_path=f"{stem}/{judge_report}",
                                             report_sha256=sha256_file(run / judge_report))
    m["eval_spec_dump"]["model_roles"]["target"]["model"] = target
    if readapt:
        block = copy.deepcopy(READAPT_TEMPLATE)
        run_id = stem.split("_")[1]
        block.update(source_workflow_run_id=run_id, source_run_stem=stem, source_journal_nonce=nonce,
                     readapt_workflow_run_id="555", readapt_journal_nonce=f"{nonce}r", readapt_commit=_hex("c"),
                     target_report={"path": f"{stem}/{stem}.report.json",
                                    "sha256": sha256_file(run / f"{stem}.report.json")})
        block["source_artifact"] = dict(block["source_artifact"], name=f"petri-audit-raw-eval-{run_id}-1")
        m["readapt"] = block
    chain = runs / CHAIN_FILE
    lines = [ln for ln in chain.read_text().splitlines() if ln.strip()] if chain.is_file() else []
    sealed = seal_manifest(m, lines[-1].rsplit(" ", 1)[1] if lines else None)
    write_manifest(run / "manifest.json", sealed)
    with open(chain, "a", encoding="utf-8") as fh:
        fh.write(f"{stem}/manifest.json {sealed['chain']['manifest_sha256']}\n")
    return run


def _reseal(run: Path, **artifact_updates) -> None:
    """Rebind a run's changed files and reseal it in place (the chain head only, as bind_judgments does)."""
    m = load_json(run / "manifest.json")
    for fam, name in (("transcripts", "transcripts.jsonl"), ("judgments", "judgments.jsonl"),
                      ("sanitised_log", "sanitised_log.json"), ("rule_outcomes", "rule_outcomes.jsonl")):
        m["artifacts"][f"{fam}_sha256"] = sha256_file(run / name)
    m["artifacts"].update(artifact_updates)
    old = m["chain"]["manifest_sha256"]
    sealed = seal_manifest(m, m["chain"]["prev_sha256"])
    write_manifest(run / "manifest.json", sealed)
    chain = run.parent / CHAIN_FILE
    chain.write_text(chain.read_text().replace(old, sealed["chain"]["manifest_sha256"]), encoding="utf-8")


def _artifact(runs: list[Path], **over) -> dict:
    doc = {
        "analysis": "synthetic", "final": True, "run_list": [str(r) for r in runs], "bootstrap_seed": 20260923,
        "identity": {"commit": _hex("analysis"), "generated_utc": "2026-09-25T03:00:00Z",
                     "uncommitted_changes": {"script": [], "plan": []}},
        "administratively_truncated": False, "truncation_reason": None, "fires_not_landed": [],
        "coverage": {"runs": [{"run_stem": r.name, "manifest_sha256": sha256_file(r / "manifest.json"),
                               "judgments_sha256": sha256_file(r / "judgments.jsonl"),
                               "committed_analysis_rows": {"status": "read",
                                                           "sha256": sha256_file(r / "analysis_rows.jsonl")}}
                              for r in runs]},
        "section_10_2": {"wording": {"row_id": "row5", "selectable_as_registered": True, "not_selectable_reasons": [],
                                     "scenarios_with_mean_in_primary_direction": []}},
        "section_10_3": {"statement": {"statement_id": "not_separated", "vocabulary_also_lowered": False}},
        "as_first_written": {"status": "computed", "label": "secondary", "section_10_2": {"wording": {"row_id": "row5"}}},
    }
    doc.update(over)
    return doc


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / RUBRIC_REF).write_text(json.dumps(RUBRIC), encoding="utf-8")
    (repo / PROMPT_REF).parent.mkdir(parents=True)
    (repo / PROMPT_REF).write_text(json.dumps(PROMPT), encoding="utf-8")
    (repo / "seeds.json").write_text(json.dumps(SEEDS), encoding="utf-8")
    (repo / "plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    shutil.copyfile(rp.DEFAULT_CLAIMS, repo / "claims.json")
    shutil.copyfile(rp.ENV_LOCK, repo / "lock.json")
    runs = repo / "data" / "petri" / "runs"
    _write_run(runs, "run_100_1", "pilot")                   # not a plan fire: never part of the pack
    r1 = _write_run(runs, "run_200_1", "f1")
    r2 = _write_run(runs, "run_300_1", "f2", readapt=True)
    analysis = repo / "w2_register_contrast.json"
    analysis.write_text(json.dumps(_artifact([r1, r2])), encoding="utf-8")
    inputs = rp.PackInputs(vendor="anthropic", run_dirs=(r1, r2), runs_dir=runs, analysis=analysis,
                           plan=repo / "plan.json", claims=repo / "claims.json", seeds=repo / "seeds.json",
                           lock=repo / "lock.json", repo_root=repo)
    return {"tmp": tmp_path, "repo": repo, "runs": runs, "r1": r1, "r2": r2, "analysis": analysis, "inputs": inputs,
            "log": tmp_path / "disclosure_log.jsonl", "out": tmp_path / "dist"}


def _build(w, out="dist", state="not_yet_public", inputs=None, registry=REGISTRY) -> Path:
    return rp.build_pack(inputs or w["inputs"], publication_state=state, out=w["tmp"] / out, log=w["log"],
                         registry=registry)


def _log(w) -> list[dict]:
    return [json.loads(x) for x in w["log"].read_text().splitlines()]


def _check(w, capsys) -> tuple[int, str]:
    capsys.readouterr()
    code = rp.check_packs(w["log"])
    return code, capsys.readouterr().out


def _refusal(w, **kw) -> list[str]:
    with pytest.raises(rp.PackRefusal) as e:
        _build(w, **kw)
    return e.value.problems


def _refresh_artifact(w, **over) -> None:
    w["analysis"].write_text(json.dumps(_artifact([w["r1"], w["r2"]], **over)), encoding="utf-8")


# ------------------------------------------------------------------ contents


def test_pack_holds_every_run_file_the_analysis_the_claims_and_their_digests(world):
    bundle = _build(world)
    man = json.loads((bundle / "MANIFEST.json").read_text())
    version = man["pack_version"]
    assert bundle.name == f"petri_repro_anthropic_{version}" and version.startswith("petri-v")
    # every file of each listed run, byte for byte, including a readapt's judge sidecar; the pilot run is not packed
    for run in (world["r1"], world["r2"]):
        for f in run.iterdir():
            assert (bundle / "runs" / run.name / f.name).read_bytes() == f.read_bytes()
        assert verify_run(bundle / "runs" / run.name) == []          # the pack's copy verifies on its own
    assert (bundle / "runs" / "run_300_1" / "run_300_1.readapt_555.judge.report.json").is_file()
    assert not (bundle / "runs" / "run_100_1").exists()
    for rel in ("analysis/w2_register_contrast.json", "analysis/plan.json", f"prompts/{RUBRIC_REF}",
                f"prompts/{PROMPT_REF}", "seeds.json", "environment/lock.json", "CLAIMS.json", "README.md",
                "DISCLOSURE_NOTE.md", "SHA256SUMS"):
        assert (bundle / rel).is_file(), rel
    sums = dict(reversed(ln.split("  ", 1)) for ln in (bundle / "SHA256SUMS").read_text().splitlines())
    assert set(sums) == {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()} - {"SHA256SUMS"}
    assert all(sha256_file(bundle / p) == d for p, d in sums.items())
    # the version is the canonical manifest's own digest
    body = {k: v for k, v in man.items() if k != "pack_version"}
    assert version == "petri-v" + sha256_text(ae.canonical_json(body))[:12]
    assert man["lane"] == "petri" and man["vendor"] == "anthropic" and man["scope"] == "w2_register_contrast"
    assert man["prompts"][RUBRIC_REF]["digest"] == rubric_digest(RUBRIC)
    assert man["prompts"][PROMPT_REF]["digest"] == sha256_text(prompt_canonical(PROMPT))[:12]
    assert man["seeds"] == {s["seed_id"]: seed_digest(s) for s in SEEDS["seeds"][:2]}     # the used seeds only
    assert man["environment_lock"]["packed"] is True
    seeds = json.loads((bundle / "seeds.json").read_text())
    assert [s["seed_id"] for s in seeds["seeds"]] == ["s1", "s2"]
    # the claims: the artifact's ids with the design note's words
    claims = json.loads((bundle / "CLAIMS.json").read_text())
    wording = load_json(rp.DEFAULT_CLAIMS)
    assert claims["headline"]["row_id"] == "row5"
    assert claims["headline"]["what_may_be_said"] == wording["wording_table"]["rows"]["row5"]["what_may_be_said"]
    assert claims["decomposition"]["statement_id"] == "not_separated"
    assert claims["as_first_written"]["row_id"] == "row5"
    assert claims["limitations"] == wording["limitations"]
    readme = (bundle / "README.md").read_text()
    for needle in (version, "python -m scripts.petri_audit.cli verify-chain --data-dir",
                   f"verify-run --run-dir {world['runs']}/run_200_1",
                   "--final --plan", "--seed 20260923", f"git checkout {_hex('analysis')}",
                   wording["wording_table"]["rows"]["row5"]["what_may_be_said"],
                   wording["decomposition_statements"]["always"], "Every fire of the plan landed"):
        assert needle in readme, needle
    head = (world["runs"] / CHAIN_FILE).read_text().splitlines()[-1].split()[-1]
    assert f"the head was\n`{head}`" in readme and "- line 2: `run_200_1/manifest.json`" in readme


def test_readme_counts_request_ids_and_never_promises_the_targets(world):
    bundle = _build(world)
    readme = (bundle / "README.md").read_text()
    # target: 10 calls per run by the manifests' usage, no raw call or header kept
    assert "None of the 20 target calls carries a request id from your API in these records" in readme
    # judge: 2 calls per run (method judge), one of them with a request id
    assert "2 of the 4 judge calls made directly carry the request id your API returned" in readme
    assert "4 judge calls to `claude-haiku-4-5` and 2 codings by `rule` recorded without a call" in readme
    note = (bundle / "DISCLOSURE_NOTE.md").read_text()
    assert ("Request ids: the 20 target calls carry none in these records; 2 of the 4 judge calls made directly "
            "carry the one your API returned.") in note


def test_request_id_text_names_an_aggregators_ids_as_not_the_vendors():
    target = {"calls": 3, "model_events_with_raw_call": 0, "headers_kept_runs": []}
    judge = {"calls": 5, "calls_with_vendor_request_id": 2, "calls_via_aggregator": 3, "aggregator_request_ids": 3}
    text = rp.request_id_text(target, judge, 1)
    assert "All 2 judge calls made directly carry the request id" in text
    assert "3 judge calls were routed through an aggregator; the request ids on 3 of them are the aggregator's" in text
    kept = rp.request_id_text(dict(target, model_events_with_raw_call=2), dict(judge, calls_via_aggregator=0), 1)
    assert kept.startswith("Of the 3 target calls, 2 model events in the sanitised logs keep the raw provider call")


@pytest.mark.parametrize("state,needle,absent", [
    ("not_yet_public", "Nothing from this arm naming your model is public yet", "[date]"),
    ("already_public", "has shown this arm's results for your model since\n[date]", "Nothing from this arm"),
    ("formerly_public", "from\n[first date] to [last date]", "Nothing from this arm"),
])
def test_disclosure_note_takes_the_publication_states_version(world, state, needle, absent):
    note = (_build(world, state=state) / "DISCLOSURE_NOTE.md").read_text()
    assert needle in note and absent not in note
    assert "before publication" in note if state == "not_yet_public" else "we want to know:" in note
    assert "{" not in note and "BEGIN" not in note
    if state == "not_yet_public":
        assert not re.search(r"\[[^\]]+\]", note)                  # nothing left to fill


def test_build_is_deterministic_and_logs_each_version_once(world):
    b1 = _build(world, out="d1")
    b2 = _build(world, out="d2")
    assert rp._dir_digests(b1) == rp._dir_digests(b2)
    entries = _log(world)
    assert len(entries) == 1
    e = entries[0]
    assert e["lane"] == "petri" and e["pack_version"] == b1.name.rsplit("_", 1)[1]
    assert e["sent_utc"] is None and e["supersedes"] is None
    # the log keeps what --check reads and the claim ids, not the bundle's whole manifest
    assert set(e["manifest"]) == set(rp.LOG_MANIFEST_KEYS) | {"claim_ids"}
    assert e["manifest"]["claim_ids"]["headline_row_id"] == "row5"


def test_a_pack_directory_holding_other_bytes_is_never_rebuilt_in_place(world):
    bundle = _build(world)
    (bundle / "README.md").write_text("edited", encoding="utf-8")
    problems = _refusal(world)
    assert any("exists and holds other bytes" in p for p in problems)
    assert (bundle / "README.md").read_text() == "edited"
    assert not list(world["out"].glob(".staging_*"))


# ------------------------------------------------------------------ refusals


def test_refuses_without_the_analysis_artifact_or_a_final_one(world):
    world["analysis"].unlink()
    assert any("is absent: build the pack after `python scripts/petri_w2_register_contrast.py --final" in p
               for p in _refusal(world))
    world["analysis"].write_text(json.dumps({"final": False, "coverage": {}}), encoding="utf-8")
    assert any("is not a final analysis (final: False)" in p for p in _refusal(world))
    assert not world["log"].exists() and not world["out"].exists()


def test_refuses_an_artifact_computed_on_other_bytes_or_other_runs(world):
    doc = _artifact([world["r1"], world["r2"]])
    doc["coverage"]["runs"][0]["judgments_sha256"] = "0" * 64
    world["analysis"].write_text(json.dumps(doc), encoding="utf-8")
    assert any("run_200_1/judgments.jsonl: the analysis read sha256 000000000000" in p for p in _refusal(world))
    world["analysis"].write_text(json.dumps(_artifact([world["r1"]])), encoding="utf-8")
    assert any("the pack lists run_300_1, which the analysis did not read" in p for p in _refusal(world))


def test_refuses_a_run_list_that_omits_a_landed_run_of_the_plans_fires(world):
    inputs = rp.PackInputs(**{**world["inputs"].__dict__, "run_dirs": (world["r1"],)})
    world["analysis"].write_text(json.dumps(_artifact([world["r1"]])), encoding="utf-8")
    problems = _refusal(world, inputs=inputs)
    assert any("run_300_1 is a landed run of the plan's fires that the pack does not list" in p for p in problems)


def test_refuses_a_run_that_fails_verify_run(world):
    with open(world["r1"] / "judgments.jsonl", "a") as fh:
        fh.write(json.dumps({"judge_model": JUDGE}) + "\n")
    problems = _refusal(world)
    assert any(p.startswith("run_200_1 does not pass verify-run: judgments: judgments.jsonl does not digest")
               for p in problems)


@pytest.mark.parametrize("where", ["judgment", "transcript", "sidecar"])
def test_refuses_a_record_naming_another_vendors_model(world, where):
    """Runs are packed whole (their files are bound by digest), so one foreign record refuses the pack by name. The
    records are changed in the chain head (run_300_1), resealed, so the foreign model is the only problem."""
    run = world["r2"]
    if where == "judgment":
        rows = _judgments(run.name)
        rows[1]["judge_model"] = "openai:gpt-9"
        _jsonl(run / "judgments.jsonl", rows)
        _reseal(run)
        expected = "run_300_1/judgments.jsonl judge_model names 'openai:gpt-9', not a anthropic model (1 record(s))"
    elif where == "transcript":
        _jsonl(run / "transcripts.jsonl", [{"conversation_id": "c", "source": {"model": "openrouter/google/g-1"}}])
        _reseal(run)
        expected = "run_300_1/transcripts.jsonl source.model names 'openrouter/google/g-1'"
    else:
        # an ordinary run's target sidecar is not bound by its manifest (a readapt's is), so it changes without a reseal
        (world["r1"] / "run_200_1.report.json").write_text(json.dumps({"models": [{"model": "openai/gpt-9"}]}))
        expected = "run_200_1/run_200_1.report.json models.model names 'openai/gpt-9'"
    _refresh_artifact(world)
    problems = _refusal(world)
    assert len(problems) == 1 and problems[0].startswith(expected), problems


@pytest.mark.parametrize("spec,vendor,expected", [
    ("anthropic/claude-haiku-4-5", "anthropic", True),
    ("claude-haiku-4-5", "anthropic", True),               # a bare id is an Anthropic id by the registry's rule
    ("anthropic:claude-haiku-4-5", "anthropic", True),
    ("openrouter:google/gemini-x", "google", True),
    ("openrouter/google/gemini-x", "anthropic", False),
    ("openai:gpt-9", "anthropic", False),
    ("mockllm/judge", "anthropic", False),
    ("none/none", "anthropic", False),
])
def test_spec_matches_vendor(spec, vendor, expected):
    assert rp.spec_matches_vendor(spec, vendor) is expected


def test_refuses_a_seed_that_drifted_from_what_a_run_recorded(world):
    seeds = copy.deepcopy(SEEDS)
    seeds["seeds"][0]["text"] = "changed"
    (world["repo"] / "seeds.json").write_text(json.dumps(seeds), encoding="utf-8")
    assert any(p.startswith("seed s1: run_200_1 recorded digest") for p in _refusal(world))


def test_refuses_unknown_files_and_a_missing_cost_sidecar(world):
    (world["r1"] / "notes.txt").write_text("x")
    (world["r2"] / "run_300_1.report.json").unlink()
    problems = _refusal(world)
    assert any("run_200_1: holds notes.txt, which is not a file of a landed run" in p for p in problems)
    assert any("run_300_1" in p and "report.json" in p for p in problems)


def test_refuses_a_pack_that_carries_a_sealed_phrase_and_names_labels_only(world, capsys):
    phrase = "zq sealed placeholder phrase zq"
    _jsonl(world["r2"] / "transcripts.jsonl", [{"conversation_id": "c", "source": {"model": TARGET},
                                                "turns": [{"text": f"before {phrase} after"}]}])
    _reseal(world["r2"])
    _refresh_artifact(world)
    problems = _refusal(world)
    assert any(p.startswith("holdout seal:") and "pairs_T#1" in p for p in problems)
    assert all(phrase not in p for p in problems) and phrase not in capsys.readouterr().out
    assert not world["out"].exists() or not any(world["out"].iterdir())
    # an empty sealed set cannot show the pack clean
    assert _refusal(world, registry={})[0].startswith("holdout seal not checked: sealed set computed empty")


# ------------------------------------------------------------------ claims


def test_claims_resolve_every_id_the_analysis_writes():
    wording = load_json(rp.DEFAULT_CLAIMS)
    rows = wording["wording_table"]["rows"]

    def claims(**over):
        doc = _artifact([])
        doc.update(over)
        return rp.claims_block(doc, wording, Path("a.json"), Path("c.json"))

    block, problems = claims(section_10_2={"wording": {"row_id": "row4/row2"}})
    assert problems == [] and block["headline"]["what_may_be_said"] == (
        f"{rows['row4']['what_may_be_said']} Under row2's rule: {rows['row2']['what_may_be_said']}")
    block, _ = claims(section_10_2={"wording": {"row_id": "no_prespecified_row", "selectable_as_registered": False,
                                                "not_selectable_reasons": ["gate opposite"]}})
    assert block["headline"]["what_may_be_said"] is None and "no wording is permitted" in block["headline"]["note"]
    block, _ = claims(section_10_3={"statement": {"statement_id": "style_larger", "vocabulary_also_lowered": True}})
    assert block["decomposition"]["what_may_be_said"].endswith(
        "Add: " + wording["decomposition_statements"]["vocabulary_also_lowered"]["what_may_be_said"])
    block, _ = claims(section_10_3={"status": "refused", "reason": "a dimension was refused"})
    assert block["decomposition"]["status"] == "refused"
    block, _ = claims(as_first_written={"status": "refused", "reason": "no committed rows"})
    assert block["as_first_written"] == {"source": "as_first_written.section_10_2.wording", "label": None,
                                         "status": "refused", "reason": "no committed rows"}
    _, problems = claims(section_10_2={"wording": {"row_id": "row9"}})
    assert problems == ["the wording table (10.2, 'What each outcome permits') has no row 'row9'"]
    _, problems = claims(section_10_3={"statement": {"statement_id": "invented"}})
    assert problems == ["the statement table (10.3, 'What may be said') has no statement 'invented'"]


def test_readme_names_truncation_and_an_unselectable_row(world):
    _refresh_artifact(world, administratively_truncated=True, truncation_reason="fire failed",
                      fires_not_landed=["f3"],
                      section_10_2={"wording": {"row_id": "row3", "selectable_as_registered": False,
                                                "not_selectable_reasons": ["the gate ran on 5 of 8 scenarios"],
                                                "scenarios_with_mean_in_primary_direction": ["sc-a"]}})
    readme = (_build(world) / "README.md").read_text()
    assert "- **Administratively truncated**: fire failed; fires not landed: f3." in readme
    assert "Not selectable as registered: the gate ran on 5 of 8 scenarios." in readme
    assert "`sc-a`" in readme and '--declare-truncated "fire failed"' in readme


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_the_wording_file_is_the_design_notes_text_verbatim():
    """The pack quotes the design note; an amended table or statement fails here until the wording file is amended
    with it."""
    doc = (ROOT / "docs" / "petri_wave2_design.md").read_text(encoding="utf-8")
    wording = load_json(rp.DEFAULT_CLAIMS)
    table = doc.split("**What each outcome permits.**", 1)[1].split("### 10.3", 1)[0]
    cells = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table.splitlines()
             if ln.startswith("| p")]
    rows = wording["wording_table"]["rows"]
    assert [[r["primary_test"], r["general_gate"], r["prospective_partition"], r["what_may_be_said"]]
            for r in (rows[f"row{i}"] for i in range(1, 6))] == cells
    flat = _normalized(doc)
    statements = wording["decomposition_statements"]
    quoted = [s["what_may_be_said"] for s in statements["statements"].values() if s["what_may_be_said"]]
    quoted += [statements["vocabulary_also_lowered"]["what_may_be_said"], statements["always"]]
    quoted += [lim["text"] for lim in wording["limitations"]]
    for text in quoted:
        assert _normalized(text) in flat, text
    # every id the analysis can write has an entry (scripts/petri_w2_register_contrast.py wording_row and
    # decomposition_statement)
    assert set(wording["wording_table"]["without_a_row"]) == {"not_computable", "no_prespecified_row"}
    assert set(statements["statements"]) == {"style_larger", "not_separated", "not_computable",
                                             "no_prespecified_statement"}


# ------------------------------------------------------------------ check, send, supersede


def test_check_reports_never_built_and_skips_the_advice_lanes_entries(world, capsys):
    code, out = _check(world, capsys)
    assert code == 0 and "never-built" in out
    world["log"].write_text(json.dumps({"pack_version": "v1", "vendor": "acme", "manifest": {}}) + "\n")
    code, out = _check(world, capsys)
    assert code == 0 and "skipped: 1 log entry of lane 'advice' (this check covers lane 'petri' only)" in out
    assert "never-built" in out
    # a line that is not an object has no lane, so it is the advice lane's: counted, never dropped
    with open(world["log"], "a") as fh:
        fh.write("[1, 2]\n")
    code, out = _check(world, capsys)
    assert code == 0 and "skipped: 2 log entries of lane 'advice'" in out


def test_logged_inputs_are_repository_relative_and_round_trip():
    """The public log names no local directory for inputs inside the repository, and --check resolves them back."""
    inputs = rp.PackInputs(vendor="anthropic", run_dirs=(rp.DEFAULT_RUNS_DIR / "run_1_1",))
    rec = inputs.record()
    assert rec["run_dirs"] == ["data/petri/runs/run_1_1"] and rec["analysis"] == "data/petri/w2_register_contrast.json"
    assert rec["repo_root"] == "." and rec["seeds"] == "docs/framework/petri_seeds.draft.json"
    assert rp.PackInputs.from_record(rec) == inputs


def test_check_is_fresh_after_a_build_and_stale_but_unescalated_when_unsent(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    code, out = _check(world, capsys)
    assert code == 0 and f"FRESH  {version}  anthropic  w2_register_contrast" in out
    _refresh_artifact(world, section_10_3={"statement": {"statement_id": "style_larger"}})
    code, out = _check(world, capsys)
    assert code == 0 and f"STALE  {version}  anthropic  w2_register_contrast  | analysis_sha256:" in out
    assert "ESCALATION" not in out


def test_record_sent_stamps_today_and_a_stale_sent_pack_escalates(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], version, "vendor safety team (role ref)")
    sent = _log(world)[-1]
    assert sent["sent_utc"][:10] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert sent["sent_to"] == "vendor safety team (role ref)" and sent["lane"] == "petri"
    assert len(_log(world)) == 2 and _log(world)[0]["sent_utc"] is None        # the build entry is never rewritten
    code, out = _check(world, capsys)
    assert code == 0 and f"FRESH  {version}" in out
    rows = _judgments(world["r2"].name)
    rows[0]["value"] = "t1"
    _jsonl(world["r2"] / "judgments.jsonl", rows)
    code, out = _check(world, capsys)
    assert code == 2 and "runs[run_300_1][files][judgments.jsonl]" in out
    assert f"ESCALATION: sent pack {version} (anthropic, w2_register_contrast) is stale" in out


def test_a_rebuild_supersedes_and_is_owed_until_sent(world, capsys):
    v1 = _build(world, out="d1").name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], v1, "vendor safety team")
    (world["repo"] / PROMPT_REF).write_text(json.dumps({**PROMPT, "instructions": "changed {values}"}))
    code, out = _check(world, capsys)
    assert code == 2 and f"prompts[{PROMPT_REF}][digest]" in out
    # the judgments now name a digest the file no longer has; a rebuild still packs, and says so in its README
    v2_bundle = _build(world, out="d2")
    v2 = v2_bundle.name.rsplit("_", 1)[1]
    assert v2 != v1 and [e["supersedes"] for e in _log(world) if e["pack_version"] == v2] == [v1]
    assert "were judged under an earlier version of the file" in (v2_bundle / "README.md").read_text()
    code, out = _check(world, capsys)
    assert code == 2 and f"newest built is {v2} (unsent) - send the superseding pack" in out
    rp.record_sent(world["log"], v2, "vendor safety team")
    assert _check(world, capsys)[0] == 0


def test_a_new_landed_run_of_the_campaign_stales_the_pack_and_another_run_does_not(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], version, "vendor safety team")
    _write_run(world["runs"], "run_400_1", "later-wave")          # not a plan fire: the chain head moves, nothing else
    code, out = _check(world, capsys)
    assert code == 0 and f"FRESH  {version}" in out
    _write_run(world["runs"], "run_500_1", "f2")                  # a second landed run of a plan fire
    code, out = _check(world, capsys)
    assert code == 2 and "campaign_runs: ['run_200_1', 'run_300_1'] -> ['run_200_1', 'run_300_1', 'run_500_1']" in out


def test_a_reseal_of_a_listed_runs_chain_line_stales_the_pack(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], version, "vendor safety team")
    _reseal(world["r2"], judgments_sha256=sha256_file(world["r2"] / "judgments.jsonl"))
    m = load_json(world["r2"] / "manifest.json")
    m["created_utc"] = "2026-09-30T00:00:00Z"                     # a changed manifest, resealed at the head
    old = m["chain"]["manifest_sha256"]
    sealed = seal_manifest(m, m["chain"]["prev_sha256"])
    write_manifest(world["r2"] / "manifest.json", sealed)
    chain = world["runs"] / CHAIN_FILE
    chain.write_text(chain.read_text().replace(old, sealed["chain"]["manifest_sha256"]))
    code, out = _check(world, capsys)
    assert code == 2 and "chain[lines][run_300_1]" in out and "chain[prefix_sha256]" in out


def test_inputs_the_pack_does_not_depend_on_leave_it_fresh(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], version, "vendor safety team")
    seeds = copy.deepcopy(SEEDS)
    seeds["seeds"][2]["text"] = "an unused seed changed"
    seeds["seeds"].append({"seed_id": "s10", "text": "a new seed"})
    (world["repo"] / "seeds.json").write_text(json.dumps(seeds), encoding="utf-8")
    lock = load_json(world["repo"] / "lock.json")
    lock["python"] = "9.9"
    (world["repo"] / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    (world["repo"] / "docs" / "framework" / "judge_prompts" / "outcomes" / "d2.draft.json").write_text("{}")
    code, out = _check(world, capsys)
    assert code == 0 and f"FRESH  {version}" in out
    seeds["seeds"][1]["text"] = "a used seed changed"
    (world["repo"] / "seeds.json").write_text(json.dumps(seeds), encoding="utf-8")
    code, out = _check(world, capsys)
    assert code == 2 and "seeds[s2]:" in out


def test_packs_for_two_analyses_are_two_keys(world, capsys):
    v1 = _build(world, out="d1").name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], v1, "vendor safety team")
    other = world["repo"] / "w3_other_contrast.json"
    shutil.copyfile(world["analysis"], other)
    inputs = rp.PackInputs(**{**world["inputs"].__dict__, "analysis": other})
    v2 = _build(world, out="d2", inputs=inputs).name.rsplit("_", 1)[1]
    assert [e["supersedes"] for e in _log(world) if e["pack_version"] == v2] == [None]
    code, out = _check(world, capsys)
    assert code == 0 and f"FRESH  {v1}  anthropic  w2_register_contrast" in out
    assert f"FRESH  {v2}  anthropic  w3_other_contrast" in out


def test_an_unreadable_petri_entry_exits_3_and_never_hides_an_escalation(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    with open(world["log"], "a") as fh:
        fh.write(json.dumps({"pack_version": "petri-vbroken", "lane": "petri", "vendor": "anthropic",
                             "manifest": {"scope": "x"}}) + "\n")
    code, out = _check(world, capsys)
    assert code == 3 and "UNREADABLE: entry 2 (petri-vbroken): missing manifest.inputs, manifest.depends_on" in out
    assert f"FRESH  {version}" in out
    rp.record_sent(world["log"], version, "vendor safety team")
    _refresh_artifact(world, bootstrap_seed=1)
    code, out = _check(world, capsys)
    assert code == 2 and "ESCALATION" in out and "UNREADABLE" in out


def test_record_sent_refusals(world):
    version = _build(world).name.rsplit("_", 1)[1]
    with pytest.raises(rp.PackRefusal, match="not in"):
        rp.record_sent(world["log"], "petri-v000000000000", "vendor safety team")
    with pytest.raises(rp.PackRefusal, match="contact address"):
        rp.record_sent(world["log"], version, "someone@example.com")
    with pytest.raises(rp.PackRefusal, match="--sent-to is required"):
        rp.record_sent(world["log"], version, " ")
    with open(world["log"], "a") as fh:
        fh.write(json.dumps({"pack_version": "v0000advice", "vendor": "acme", "manifest": {}}) + "\n")
    with pytest.raises(rp.PackRefusal, match="is not a petri-lane pack"):
        rp.record_sent(world["log"], "v0000advice", "vendor safety team")
    assert len(_log(world)) == 2                                   # nothing appended by a refusal


def test_the_advice_check_still_skips_petri_entries(world, capsys):
    version = _build(world).name.rsplit("_", 1)[1]
    rp.record_sent(world["log"], version, "vendor safety team")
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        ae.main(["repro-pack", "--check", "--log", str(world["log"])])
    assert e.value.code == 0
    assert "skipped: 2 log entries of lane 'petri' (this check covers lane 'advice' only)" in capsys.readouterr().out


# ------------------------------------------------------------------ the CLI


def _cli_build(w, *extra) -> list[str]:
    inputs = w["inputs"]
    argv = ["repro-pack", "--vendor", "anthropic", "--run-dir", str(w["r1"]), "--run-dir", str(w["r2"]),
            "--analysis", str(inputs.analysis), "--plan", str(inputs.plan), "--claims", str(inputs.claims),
            "--seeds", str(inputs.seeds), "--lock", str(inputs.lock), "--runs-dir", str(inputs.runs_dir),
            "--repo-root", str(inputs.repo_root), "--out", str(w["out"]), "--log", str(w["log"]), *extra]
    return argv


def test_cli_builds_checks_and_records_a_send(world, monkeypatch, capsys):
    monkeypatch.setattr(rp.seal, "sealed_registry", lambda: dict(REGISTRY))
    assert cli.main(_cli_build(world)) == rp.REFUSED_EXIT        # the publication state is never defaulted
    assert "refused: build mode requires --publication-state" in capsys.readouterr().err
    assert cli.main(_cli_build(world, "--publication-state", "not_yet_public")) == 0
    version = _log(world)[0]["pack_version"]
    assert cli.main(["repro-pack", "--check", "--log", str(world["log"])]) == 0
    assert f"FRESH  {version}" in capsys.readouterr().out
    assert cli.main(["repro-pack", "--record-sent", version, "--sent-to", "vendor safety team",
                     "--log", str(world["log"])]) == 0
    assert f"recorded send of {version} to vendor safety team" in capsys.readouterr().out
    assert cli.main(["repro-pack", "--record-sent", version, "--sent-to", "a@b.c", "--log", str(world["log"])]) == 13
    world["analysis"].unlink()
    assert cli.main(_cli_build(world, "--publication-state", "not_yet_public")) == rp.REFUSED_EXIT
    assert "is absent" in capsys.readouterr().err


# ------------------------------------------------------------------ the chain prefix


def test_verify_chain_over_its_first_lines_ignores_later_ones(world):
    runs = world["runs"]
    (world["r2"] / "rule_outcomes.jsonl").write_text("altered\n")      # breaks line 3 only
    assert verify_chain(runs, lines=2)[0] is True
    ok, msg = verify_chain(runs, lines=3)
    assert not ok and msg.startswith("line 3:")
    assert verify_chain(runs)[0] is False
    ok, msg = verify_chain(runs, lines=9)
    assert not ok and "fewer than the 9" in msg
