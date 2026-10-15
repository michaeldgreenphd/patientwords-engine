"""Tests for the wave-3 register-contrast analysis (scripts/petri_w3_register_contrast.py; design note
docs/petri_wave3_design.md section 9; plan data/petri/w3_register_contrast_plan.json).

No wave-3 run exists, so every run here is synthetic: built in a temporary directory from wave 1's landed manifest as
the schema template (the approach tests/test_petri_w2_register_contrast.py takes, so each synthetic run passes
manifest.verify_run as a landed run must), with re-grade directories written in the shape mode rejudge writes and
checked with rejudge.verify_output. The synthetic plan is the committed wave-3 plan with its seeds, targets, fires and
judge replaced by abstract ones, so every other field (windows, digests, statements, family) is the plan's own. Seed
ids, target names and mechanism names are abstract: medical vocabulary lives in JSON data, never in Python. The
--final guards are pointed at the synthetic plan, committed in a throwaway git repository through plumbing, which runs
no hook, and at a synthetic trigger journal; the real ops/trigger_journal.jsonl is never read or written here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from scripts import petri_w2_register_contrast as w2
from scripts import petri_w3_register_contrast as w3
from scripts.petri_audit import judge_runner, rejudge
from scripts.petri_audit.framework import ADVICE_RUBRIC_REF, OUTCOME_REGISTRY, load_json, sha256_file
from scripts.petri_audit.manifest import ARTIFACT_FILENAMES, CHAIN_FILE, JUDGE_REPORT_SUFFIX, seal_manifest
from scripts.petri_audit.seeds import seed_digest

ROOT = Path(__file__).resolve().parents[1]
REAL_PLAN = load_json(ROOT / "data" / "petri" / "w3_register_contrast_plan.json")
TEMPLATE_MANIFEST = load_json(ROOT / "data" / "petri" / "runs" / "run_35351739969_1" / "manifest.json")
RUBRIC = judge_runner.load_rubric()
TIERS = [t["id"] for t in RUBRIC["tiers"]]                 # low to high, from data
FLAG_IDS = [f["id"] for f in RUBRIC["flags"]]
REGISTRY = load_json(OUTCOME_REGISTRY)
DIMS = {d["id"]: d for d in REGISTRY["dimensions"]}
PINS = REAL_PLAN["prompt_digests"]
RUBRIC_PIN = REAL_PLAN["rubric_digest"]
JUDGE = "claude-haiku-4-5"                                 # one of the plan's judge.routes
OTHER_ROUTE = next(r for r in REAL_PLAN["judge"]["routes"] if r != JUDGE)
SECOND = "claude-haiku-5-5"
MEASURES = {m.name: m for m in w2.SECONDARY_MEASURES}
FAMILY = REAL_PLAN["exploratory_outcomes"]["family"]
REFERRAL = next(iter(REAL_PLAN["exploratory_outcomes"]["restricted_to_seeds"]))
RECOMMENDATION, PRESENCE = [n for n in FAMILY if MEASURES[n].kind == "outcome"]
FLAG = next(MEASURES[n].flag for n in FAMILY if MEASURES[n].flag)
COVERAGE_ONLY = REAL_PLAN["exploratory_outcomes"]["coverage_only"]
COL, LAY, CLIN = w3.COLLOQUIAL, w3.CAREFUL_LAY, w3.CLINICAL

# ------------------------------------------------------------------ a synthetic campaign

SEEDS_IDS = ["syn-a", "syn-b", "syn-c", "syn-d"]
MECHANISMS = {"mech-one": ["syn-a", "syn-b"], "mech-two": ["syn-c", "syn-d"]}
REFERRAL_SEEDS = ["syn-c", "syn-d"]
TARGETS = [{"id": "tgt-a", "role": "anchor", "name": "Target A", "target_specs": ["prov/tgt-a", "alt/tgt-a"]},
           {"id": "tgt-b", "role": "comparison", "name": "Target B", "target_specs": ["prov/tgt-b"]},
           {"id": "tgt-c", "role": "comparison", "name": "Target C", "target_specs": ["prov/tgt-c"]}]
EPOCHS = 2
FIRES = {f"{t['id'][-1]}{e}": (t["id"], e) for t in TARGETS for e in range(1, EPOCHS + 1)}   # nonce -> (target, epoch)
STEMS = {nonce: f"run_{100 + i}_1" for i, nonce in enumerate(FIRES)}


class Cell(NamedTuple):
    target: str
    seed_id: str
    epoch: int
    register: str


def synthetic_seed(seed_id: str) -> dict:
    """The fields the analysis and judge_runner.analysis_rows read: a constant speaker, three sustained arms of ten
    turns, and the dimensions it judges."""
    texts, arms = [], []
    for register in w3.REGISTERS:
        texts.append({"key": f"{register}_t", "register": register, "text": f"synthetic {register}"})
        arms.append({"id": register, "user_is": "patient", "turns": [{"text_ref": f"{register}_t"}] * w2.EXCHANGES})
    dims = [RECOMMENDATION, PRESENCE, COVERAGE_ONLY[0]] + ([REFERRAL] if seed_id in REFERRAL_SEEDS else [])
    return {"seed_id": seed_id, "pilot_wave": 3, "mode": "scripted", "hypotheses": ["H1"],
            "scenario": {"id": f"{seed_id}-scenario"}, "speaker_identity": {"policy": "constant"},
            "framing": {"dimension_id": "register", "contrast_id": "clinical_to_colloquial"},
            "protocol": {"register_exposure": "sustained", "arms": arms}, "texts": texts,
            "judge": {"outcome_dimensions": dims}}


SEEDS = {s: synthetic_seed(s) for s in SEEDS_IDS}


def synthetic_plan(seeds_path: Path, **over: Any) -> dict:
    """The committed wave-3 plan with abstract seeds, targets, fires and judge; every other field is the plan's."""
    plan = deepcopy(REAL_PLAN)
    plan["scenario_sets"] = {"wave3": list(SEEDS_IDS)}
    plan["decomposition_set"] = "wave3"
    plan["mechanisms"] = deepcopy(MECHANISMS)
    plan["targets"] = deepcopy(TARGETS)
    plan["epochs_per_target"] = EPOCHS
    plan["triples_per_epoch_per_target"] = len(SEEDS_IDS)
    plan["final_triples_per_target"] = len(SEEDS_IDS) * EPOCHS
    plan["fires"] = [{"journal_nonce": n, "target": t, "campaign_epoch": e} for n, (t, e) in FIRES.items()]
    plan["exploratory_outcomes"]["restricted_to_seeds"] = {REFERRAL: list(REFERRAL_SEEDS)}
    for s in plan["sensitivity"]:     # the plan's mechanism window, renamed for the synthetic mechanism
        if s.get("rule") and s["name"] not in w3.SENSITIVITY_RULES:
            s["name"] = "mech_two" + w3.MECHANISM_WINDOW_SUFFIX
    plan["judge"]["judge_model"] = JUDGE
    plan["approval"]["approved"] = True
    plan["analysis_script"].update(path="scripts/petri_w3_register_contrast.py", status="written")
    plan["judge"]["second_family_regrade"] = SECOND + " through the synthetic regrade path"
    plan["seed_file"] = str(seeds_path)
    plan.update(over)
    return plan


def default_value(cell: Cell, exchange: int, measure: str) -> Any:
    if measure in ("response_only", "contextual"):
        return TIERS[1]
    if measure == FLAG:
        return False
    return DIMS[measure]["values"][0]


def _hex(label: str, n: int = 64) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:n]


def judgment_rows(cell: Cell, conversation_id: str, value_fn: Callable, judge: str) -> list[dict]:
    """One final response-only tier row per exchange, a contextual one from exchange 2, and one row per judged outcome
    dimension, each under the plan's pinned digest, shaped like judge_runner's rows."""
    rows = []
    base = {"conversation_id": conversation_id, "judge_model": judge, "seed_id": cell.seed_id, "branch_id": "root",
            "condition_id": cell.register, "epoch": 1, "tree_id": f"{cell.seed_id}::{cell.register}#1",
            "not_applicable_reason": None, "judge_error": None, "judge_raw": "synthetic"}
    for ex in range(1, w2.EXCHANGES + 1):
        at = {"turn_id": 2 * ex, "assistant_turn_index": ex, "exchange_index": ex, "final_in_exchange": True}
        for key in ("response_only", "contextual"):
            if key == "contextual" and ex == 1:
                continue
            flags = {f: False for f in FLAG_IDS}
            if key == "response_only":
                flags[FLAG] = value_fn(cell, ex, FLAG)
            rows.append({**base, **at, "kind": "tier", "key": key, "prompt_ref": ADVICE_RUBRIC_REF,
                         "prompt_file_digest": RUBRIC_PIN, "value": value_fn(cell, ex, key), "flags": flags,
                         "answer_form": "json_object"})
        for dim in SEEDS[cell.seed_id]["judge"]["outcome_dimensions"]:
            rows.append({**base, **at, "kind": "outcome", "key": dim,
                         "prompt_ref": DIMS[dim]["detection"]["judge_prompt_ref"], "prompt_file_digest": PINS[dim],
                         "value": value_fn(cell, ex, dim), "flags": None, "answer_form": "value_only"})
    return rows


def write_campaign(tmp_path: Path, *, fires: tuple[str, ...] = tuple(FIRES), value_fn: Callable = default_value,
                   judge_of: Callable[[str], str] = lambda nonce: JUDGE,
                   spec_of: Callable[[str], str] | None = None,
                   seed_ids_of: Callable[[str], list[str]] | None = None,
                   mutate: Callable[[Cell, dict], dict | None] | None = None,
                   manifest_update: Callable[[str, dict], None] | None = None, **plan_over: Any) -> dict[str, Any]:
    """A plan, a seed file and one run directory per fire. `judge_of(nonce)` is the run's own judge, `spec_of(nonce)`
    its target spec (default: its target's first), and `mutate(cell, row)` may change or drop a judgment row."""
    (tmp_path / "seeds.json").write_text(json.dumps({"seed_schema": {}, "seeds": list(SEEDS.values())}),
                                         encoding="utf-8")
    plan = synthetic_plan(tmp_path / "seeds.json", **plan_over)
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(exist_ok=True)
    out = {"plan": tmp_path / "plan.json", "seeds": tmp_path / "seeds.json", "runs_dir": runs_dir,
           "rejudge": tmp_path / "rejudge", "runs": {}, "value_fn": value_fn}
    for nonce in fires:
        target, epoch = FIRES[nonce]
        stem = STEMS[nonce]
        run_dir = runs_dir / stem
        run_dir.mkdir()
        judge = judge_of(nonce)
        seed_ids = seed_ids_of(nonce) if seed_ids_of else SEEDS_IDS
        judgments, trees = [], []
        for sid in seed_ids:
            for register in w3.REGISTERS:
                cell = Cell(target, sid, epoch, register)
                cid = _hex(f"{stem}:{sid}:{register}")
                trees.append({"tree_id": f"{sid}::{register}#1", "sample_uuid": _hex(f"{stem}:{sid}:{register}", 22),
                              "sample_id": f"{sid}::{register}", "epoch": 1, "seed_id": sid, "arm": register,
                              "system_prompt_variant": None,
                              "branches": [{"branch_id": "root", "parent_branch_id": None,
                                            "branched_from_message_id": None, "branched_from_turn_id": None,
                                            "condition_id": register, "conversation_id": cid, "surviving": True,
                                            "creation_index": 1}],
                              "surviving_branch_id": "root", "survivor_exported": True})
                for row in judgment_rows(cell, cid, value_fn, judge):
                    row = mutate(cell, row) if mutate else row
                    if row is not None:
                        judgments.append(row)
        (run_dir / "judgments.jsonl").write_text("".join(json.dumps(j) + "\n" for j in judgments), encoding="utf-8")
        for family in ("sanitised_log", "transcripts", "rule_outcomes"):
            (run_dir / ARTIFACT_FILENAMES[family]).write_text(f"synthetic {family}\n", encoding="utf-8")
        report = f"{stem}{JUDGE_REPORT_SUFFIX}"
        (run_dir / report).write_text("synthetic judge report\n", encoding="utf-8")
        m = deepcopy(TEMPLATE_MANIFEST)
        m["run_id"] = f"synthetic-{nonce}"
        m["spend"]["journal_nonce"] = nonce
        m["framework"]["outcome_registry_sha256"] = sha256_file(OUTCOME_REGISTRY)
        m["seeds"] = [{"seed_id": s, "seed_sha256": seed_digest(SEEDS[s]), "file": "seeds.json",
                       "claim_grade_eligible": True} for s in seed_ids]
        m["trees"] = trees
        for family, filename in ARTIFACT_FILENAMES.items():
            m["artifacts"][f"{family}_path"] = f"{stem}/{filename}"
            m["artifacts"][f"{family}_sha256"] = sha256_file(run_dir / filename)
        m["artifacts"]["judge_of_record"] = {**TEMPLATE_MANIFEST["artifacts"]["judge_of_record"], "judge_model": judge,
                                             "report_path": f"{stem}/{report}",
                                             "report_sha256": sha256_file(run_dir / report)}
        spec = spec_of(nonce) if spec_of else next(t for t in TARGETS if t["id"] == target)["target_specs"][0]
        m["models"]["target"]["model"] = spec
        m["models"]["target"]["inspect_name"] = spec
        if manifest_update:
            manifest_update(nonce, m)
        (run_dir / "manifest.json").write_text(json.dumps(seal_manifest(m, None)), encoding="utf-8")
        out["runs"][nonce] = run_dir
    return out


def write_regrade(c: dict[str, Any], nonce: str, spec: str, regrade_nonce: str, *,
                  value_fn: Callable | None = None, run_id: str = "900", truncated: bool = False) -> Path:
    """A re-grade of one run in the layout mode rejudge writes (data/petri/rejudge/<slug>/<stem>/): the run's
    judgments again under `spec` (with `value_fn`'s values when given), the analysis rows, the judge sidecar and a
    sealed, schema-valid manifest binding the source run, which the chain file names. Checked with verify_output."""
    run_dir = c["runs"][nonce]
    stem = run_dir.name
    target, epoch = FIRES[nonce]
    out_dir = rejudge.output_dir(c["rejudge"], spec, stem)
    out_dir.mkdir(parents=True)
    manifest = load_json(run_dir / "manifest.json")
    source_rows = judge_runner.read_jsonl(run_dir / "judgments.jsonl")
    by_conv = {b["conversation_id"]: t for t in manifest["trees"] for b in t["branches"]}
    rows = []
    for j in source_rows:
        row = {**j, "judge_model": spec}
        if value_fn is not None:
            tree = by_conv[j["conversation_id"]]
            cell = Cell(target, tree["seed_id"], epoch, tree["arm"])
            if j["kind"] == "tier" and j["key"] == "response_only":
                row["flags"] = {**j["flags"], FLAG: value_fn(cell, j["exchange_index"], FLAG)}
            row["value"] = value_fn(cell, j["exchange_index"], j["key"])
        rows.append(row)
    (out_dir / rejudge.JUDGMENTS_NAME).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    arows = judge_runner.analysis_rows(rows, manifest, SEEDS)
    (out_dir / rejudge.ANALYSIS_NAME).write_text("".join(json.dumps(r) + "\n" for r in arows), encoding="utf-8")
    report_name = rejudge.judge_report_name(stem, run_id)
    totals = judge_runner.cumulative_counts(rows)
    jor = {k: manifest["artifacts"]["judge_of_record"].get(k) for k in rejudge.JUDGE_OF_RECORD_KEYS}
    (out_dir / report_name).write_text(json.dumps(
        {"judgments_sha256": sha256_file(out_dir / rejudge.JUDGMENTS_NAME), "journal_nonce": regrade_nonce,
         "rejudge_workflow_run_id": run_id, "source_run_stem": stem, "judge_model": spec, "cost_usd": 0.5,
         "max_spend_usd": 2.0, "task": rejudge.TASK}), encoding="utf-8")
    sha = "0" * 64
    rm = {"rejudge_manifest_version": rejudge.MANIFEST_VERSION, "mode": rejudge.MODE, "exploratory": True,
          "rehearsal": False, "created_utc": "2026-10-14T00:00:00Z",
          "source": {"run_stem": stem, "run_id": manifest["run_id"], "eval_id": manifest["eval_id"],
                     "manifest_sha256": sha256_file(run_dir / "manifest.json"),
                     "chain_manifest_sha256": manifest["chain"]["manifest_sha256"],
                     "transcripts_sha256": manifest["artifacts"]["transcripts_sha256"],
                     "judgments_sha256": manifest["artifacts"]["judgments_sha256"], "judge_of_record": jor},
          "judge": {"judge_model": spec, "judge_slug": rejudge.judge_slug(spec), "inspect_name": spec,
                    "billing_channel": "anthropic", "price_source": "synthetic", "input_per_mtok": 1.0,
                    "output_per_mtok": 5.0, "judge_max_tokens": 300, "temperature": 0.0, "max_spend_usd": 2.0,
                    "fire_judge_max_spend_usd": 2.0, "fire_spent_before_usd": 0.0},
          "instrument": {"outcome_registry": {"ref": "registry", "sha256": sha}, "rubric": {"ref": ADVICE_RUBRIC_REF,
                                                                                            "sha256": sha,
                                                                                            "digest": RUBRIC_PIN},
                         "prompt_files": {}, "plan_sha256": sha, "planned": len(rows),
                         "parity_with_judge_of_record": "exact"},
          "fire": {"workflow_run_id": run_id, "workflow_run_attempt": "1", "commit": "c" * 40,
                   "journal_nonce": regrade_nonce, "source_runs": [stem], "position": 1},
          "counts": {"planned": len(rows), **totals, "null_share": rejudge.null_share(totals["judged"], totals["null"]),
                     "judge_of_record_null_share": rejudge.null_share(jor["judged"], jor["null"]),
                     "truncated": truncated, "stopped_early": False, "call_failures": 0},
          "estimate": {"calls": len(rows), "recorded_input_tokens": 0, "recorded_output_tokens": 0,
                       "calls_without_recorded_usage": 0, "price_source": "synthetic", "input_per_mtok": 1.0,
                       "output_per_mtok": 5.0, "expected_usd": 0.5, "worst_case_usd": 1.0,
                       "last_call_headroom_usd": 0.01, "assumption": "synthetic"},
          "cost_usd": 0.5,
          "artifacts": {"judgments": {"path": rejudge.JUDGMENTS_NAME,
                                      "sha256": sha256_file(out_dir / rejudge.JUDGMENTS_NAME), "rows": len(rows)},
                        "analysis_rows": {"path": rejudge.ANALYSIS_NAME,
                                          "sha256": sha256_file(out_dir / rejudge.ANALYSIS_NAME), "rows": len(arows)},
                        "judge_report": {"path": report_name, "sha256": sha256_file(out_dir / report_name)}},
          "manifest_sha256": ""}
    rm["manifest_sha256"] = rejudge.manifest_digest(rm)
    (out_dir / rejudge.MANIFEST_NAME).write_text(json.dumps(rm), encoding="utf-8")
    with open(c["runs_dir"] / CHAIN_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{stem}/manifest.json {manifest['chain']['manifest_sha256']}\n")
    assert rejudge.verify_output(out_dir, c["runs_dir"]) == []
    return out_dir


def add_regrade_fire(c: dict[str, Any], regrade_nonce: str, stems: list[str], **extra: Any) -> None:
    plan = load_json(c["plan"])
    plan["fires"].append({"journal_nonce": regrade_nonce, "source_runs": stems, **extra})
    c["plan"].write_text(json.dumps(plan), encoding="utf-8")


def prepared(c: dict[str, Any], runs: list[Path] | None = None, **kw: Any) -> w3.Prepared:
    return w3.prepare(runs, runs_dir=c["runs_dir"], plan_path=c["plan"], seeds_path=c["seeds"],
                      rejudge_root=c["rejudge"], **kw)


def cli_args(c: dict[str, Any], *extra: str) -> list[str]:
    return ["--plan", str(c["plan"]), "--seeds", str(c["seeds"]), "--runs-dir", str(c["runs_dir"]),
            "--rejudge-root", str(c["rejudge"]), *extra]


GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def plumbing(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
                          env=GIT_ENV).stdout.strip()


def final_ready(monkeypatch: pytest.MonkeyPatch, c: dict[str, Any], journal: tuple[dict, ...] = ()) -> None:
    """Point --final's guards at the synthetic campaign: its plan is the default plan, committed in a throwaway git
    repository through plumbing (no hook runs), and the trigger journal is a synthetic file holding `journal`."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    root = c["plan"].parent
    if not (root / ".git").exists():
        plumbing(root, "init", "-q")
    journal_path = root / "journal.jsonl"
    journal_path.write_text("".join(json.dumps(e) + "\n" for e in journal), encoding="utf-8")
    # Project the repository's code and fixed validation inputs into this synthetic git repository. The tested
    # files and all campaign artifacts use real git status, while an in-progress edit to the test subject itself
    # must not make every synthetic final invocation dirty.
    if "code_files" not in c:
        static = root / "static"
        static.mkdir()
        originals = {**w3.code_files(), "rubric": w3.ADVICE_RUBRIC, "outcomes": OUTCOME_REGISTRY,
                     "framing": w3.framework.FRAMING_REGISTRY, "run_schema": w3.framework.MANIFEST_SCHEMA,
                     "regrade_schema": rejudge.MANIFEST_SCHEMA, "judge_providers": w3.spend.PROVIDERS_PATH,
                     **{f"prompt_{name}": ROOT / dimension["detection"]["judge_prompt_ref"]
                        for name, dimension in DIMS.items()}}
        projection = {}
        for name, source in originals.items():
            destination = static / f"{name}{source.suffix}"
            shutil.copyfile(source, destination)
            projection[source.resolve()] = destination
        c["code_files"] = {name: projection[path.resolve()] for name, path in w3.code_files().items()}
        c["static_files"] = projection
        original_inputs = w3.analysis_input_files

        def projected_inputs(args: Any, prep: w3.Prepared) -> dict[str, Path]:
            return {name: projection.get(path.resolve(), path) for name, path in original_inputs(args, prep).items()}

        monkeypatch.setattr(w3, "code_files", lambda: c["code_files"])
        monkeypatch.setattr(w3, "analysis_input_files", projected_inputs)
    plumbing(root, "add", "--all")
    tree = plumbing(root, "write-tree")
    commit = plumbing(root, "commit-tree", "--no-gpg-sign", "-m", "synthetic", tree)
    plumbing(root, "update-ref", "HEAD", commit)
    monkeypatch.setattr(w3, "PLAN_FILE", c["plan"])
    monkeypatch.setattr(w3, "REPO_ROOT", root)
    monkeypatch.setattr(w3, "JOURNAL_FILE", journal_path)


def run_final(monkeypatch: pytest.MonkeyPatch, c: dict[str, Any], tmp_path: Path, *extra: str) -> dict:
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out), *extra)) == 0
    return load_json(out)


# ------------------------------------------------------------------ the committed plan


def test_the_committed_draft_plan_loads_and_coverage_lists_every_target_epoch_unlanded(tmp_path):
    plan = w3.load_plan()
    assert plan.approved is False and plan.judge_model is None and plan.fires == {}
    assert plan.bootstrap_seed == w3.DEFAULT_SEED == 20261001
    assert plan.family == tuple(FAMILY) and len(plan.family) == 3 and REFERRAL not in plan.family
    (tmp_path / "runs").mkdir()
    prep = w3.prepare(runs_dir=tmp_path / "runs", rejudge_root=tmp_path / "rejudge")
    cov = w3.coverage(prep)
    per_target = REAL_PLAN["final_triples_per_target"]
    assert {t: (v["expected"], v["landed"]) for t, v in cov["triples"].items()} == \
        {t["id"]: (per_target, 0) for t in REAL_PLAN["targets"]}
    for target in REAL_PLAN["targets"]:
        assert set(cov["epochs_not_landed"][target["id"]]) == {str(e) for e in range(1, plan.epochs + 1)}
        assert cov["epochs_not_landed"][target["id"]]["1"]["reason"] == "no fire recorded"
    assert any("no fire is recorded" in t.missing[COL] for t in prep.triples)
    assert {f"exploratory:{n}" for n in FAMILY} | {f"restricted:{REFERRAL}", "primary", "decomposition"} <= \
        set(cov["contrasts"])


def test_final_refuses_the_draft_plan_and_writes_nothing(tmp_path, capsys):
    (tmp_path / "runs").mkdir()
    out = tmp_path / "final.json"
    code = w3.main(["--runs-dir", str(tmp_path / "runs"), "--rejudge-root", str(tmp_path / "rj"), "--final",
                    "--out", str(out)])
    err = capsys.readouterr().err
    assert code == 2 and not out.exists()
    assert "not approved" in err and "judge.judge_model is null" in err and "have not landed" in err


def test_the_wave2_plan_is_refused_by_name():
    with pytest.raises(w3.AnalysisRefusal, match="missing 'mechanisms'"):
        w3.load_plan(w2.PLAN_FILE)


def test_the_wave2_script_is_the_one_its_committed_artifact_records():
    """The wave-3 script reuses the wave-2 script by import and never edits it: the file is still the bytes whose
    sha256 the wave-2 final artifact records, so its behaviour and outputs are unchanged (its own tests stay green)."""
    artifact = load_json(ROOT / "data" / "petri" / "w2_register_contrast.json")
    assert sha256_file(Path(w2.__file__)) == artifact["identity"]["script_sha256"]
    assert w2.PLAN_FILE.name == "w2_register_contrast_plan.json" and w2.DEFAULT_SEED == 20260923


# ------------------------------------------------------------------ the plan's shape


@pytest.mark.parametrize("over, named", [
    ({"fires": [{"journal_nonce": "x", "target": "tgt-a", "campaign_epoch": 1, "partition": "discovery"}]},
     "unknown key(s) ['partition']"),
    ({"fires": [{"journal_nonce": "x", "target": "nobody", "campaign_epoch": 1}]}, "is not a registered target"),
    ({"fires": [{"journal_nonce": "x", "target": "tgt-a", "campaign_epoch": 9}]}, "is not one of 1..2"),
    ({"fires": [{"journal_nonce": "x", "target": "tgt-a", "campaign_epoch": 1},
                {"journal_nonce": "y", "target": "tgt-a", "campaign_epoch": 1}]}, "has 2 fires not voided"),
    ({"fires": [{"journal_nonce": "r", "source_runs": ["not-a-stem"]}]}, "distinct run stems"),
    ({"decomposition_set": "other", "scenario_sets": {"wave3": SEEDS_IDS[:2], "other": SEEDS_IDS[2:]}},
     "does not hold every plan seed"),
    ({"mechanisms": {"mech-one": SEEDS_IDS[:3]}}, "every plan seed exactly once"),
    ({"targets": [dict(TARGETS[1], role="comparison")]}, "exactly one anchor"),
])
def test_a_malformed_plan_is_refused_by_name(tmp_path, over, named):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(synthetic_plan(tmp_path / "seeds.json", **over)), encoding="utf-8")
    with pytest.raises(w3.AnalysisRefusal, match=re.escape(named)):
        w3.load_plan(path)


def test_a_statement_table_without_the_target_placeholder_is_refused(tmp_path):
    plan = synthetic_plan(tmp_path / "seeds.json")
    plan["statements"]["primary"][0]["text"] = "no placeholder"
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(w3.AnalysisRefusal, match=r"row1 does not name \{target\}"):
        w3.load_plan(tmp_path / "plan.json")


# ------------------------------------------------------------------ triples, judges and targets


def test_triples_are_keyed_by_target_seed_and_epoch_and_every_target_has_its_own(tmp_path):
    c = write_campaign(tmp_path)
    prep = prepared(c)
    ids = [t.triple_id for t in prep.triples]
    assert len(ids) == len(set(ids)) == len(TARGETS) * EPOCHS * len(SEEDS_IDS)
    for t in prep.triples:
        assert t.landed and not t.missing and t.speaker is None
        assert t.run_stem == STEMS[next(n for n, (tg, e) in FIRES.items() if tg == t.target and e == t.campaign_epoch)]
    assert ids[0] == "tgt-a:syn-a#e1"
    # the decomposition runs on every seed, per target
    decomposed = {(s.triple.target, s.triple.seed_id) for s in prep.record.standings["decomposition"]}
    assert decomposed == {(t["id"], s) for t in TARGETS for s in SEEDS_IDS}
    referral = {s.triple.seed_id for s in prep.record.standings[f"restricted:{REFERRAL}"]}
    assert referral == set(REFERRAL_SEEDS)


def test_a_run_whose_rows_carry_two_judges_is_refused(tmp_path):
    def two_judges(cell: Cell, row: dict) -> dict:
        return {**row, "judge_model": OTHER_ROUTE} if cell.seed_id == "syn-b" and row["exchange_index"] == 3 else row
    c = write_campaign(tmp_path, mutate=two_judges)
    with pytest.raises(w3.AnalysisRefusal, match="carry judge spec"):
        prepared(c)


def test_a_fire_judged_under_another_route_is_named_and_refuses_final(tmp_path, monkeypatch, capsys):
    c = write_campaign(tmp_path, judge_of=lambda nonce: OTHER_ROUTE if nonce == "b1" else JUDGE)
    prep = prepared(c)
    run = next(r for r in prep.runs if r.stem == STEMS["b1"])
    assert not run.registered and "no re-grade fire" in run.unregistered_reason and run.rows == []
    cov = w3.coverage(prep)
    assert STEMS["b1"] in cov["runs_without_registered_rows"]
    assert all("has no registered rows" in t.missing[COL] for t in prep.triples if t.run_stem == STEMS["b1"])
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out))) == 2 and not out.exists()
    assert f"run {STEMS['b1']} has no registered rows" in capsys.readouterr().err


def test_a_recorded_regrade_under_the_judge_of_record_replaces_the_runs_rows(tmp_path):
    other = {"value": TIERS[3]}

    def regraded(cell: Cell, ex: int, measure: str) -> Any:
        if measure == "response_only" and cell.register == CLIN:
            return other["value"]
        return default_value(cell, ex, measure)
    c = write_campaign(tmp_path, judge_of=lambda nonce: OTHER_ROUTE if nonce.startswith("b") else JUDGE)
    for nonce in ("b1", "b2"):
        write_regrade(c, nonce, JUDGE, "rg-b", value_fn=regraded)
    add_regrade_fire(c, "rg-b", [STEMS["b1"], STEMS["b2"]], target="tgt-b")
    prep = prepared(c)
    for nonce in ("b1", "b2"):
        run = next(r for r in prep.runs if r.stem == STEMS[nonce])
        assert run.registered and run.provenance["registered_rows_from"]["source"] == "re-grade"
        assert run.provenance["registered_rows_from"]["journal_nonce"] == "rg-b"
        assert {r["judge_model"] for r in run.rows} == {JUDGE}
    result = w3.final_analysis(prep, resamples=200)
    # the re-grade's clinical tier is the highest everywhere, so every tgt-b triple is negative
    assert result["targets"]["tgt-b"]["primary_sign_test"]["negative"] == EPOCHS * len(SEEDS_IDS)
    assert result["targets"]["tgt-a"]["primary_sign_test"]["non_tied"] == 0


def test_a_regrade_is_refused_unless_it_verifies_and_its_fire_is_the_recorded_one(tmp_path):
    c = write_campaign(tmp_path, judge_of=lambda nonce: OTHER_ROUTE if nonce == "c1" else JUDGE)
    # recorded, but not landed: named, not registered
    add_regrade_fire(c, "rg-c", [STEMS["c1"]])
    run = next(r for r in prepared(c).runs if r.stem == STEMS["c1"])
    assert not run.registered and "holds no re-grade" in run.unregistered_reason
    out_dir = write_regrade(c, "c1", JUDGE, "rg-other")
    with pytest.raises(w3.AnalysisRefusal, match="not the re-grade fire rg-c"):
        prepared(c)
    # a re-grade whose judgments changed after its manifest bound them does not verify
    path = out_dir / rejudge.JUDGMENTS_NAME
    path.write_text(path.read_text(encoding="utf-8").replace(TIERS[1], TIERS[2], 1), encoding="utf-8")
    with pytest.raises(w3.AnalysisRefusal, match="does not verify"):
        prepared(c)


def test_a_regrade_recorded_for_a_run_already_judged_by_the_judge_of_record_is_refused(tmp_path):
    c = write_campaign(tmp_path)
    add_regrade_fire(c, "rg-a", [STEMS["a1"]])
    with pytest.raises(w3.AnalysisRefusal, match="ambiguous"):
        prepared(c)


def test_the_target_refusal_applies_within_a_target_only(tmp_path):
    # the anchor's two epochs under its two specs: refused within the target
    c = write_campaign(tmp_path, spec_of=lambda nonce: "alt/tgt-a" if nonce == "a2" else
                       next(t for t in TARGETS if t["id"] == FIRES[nonce][0])["target_specs"][0])
    with pytest.raises(w3.AnalysisRefusal, match="target tgt-a: its runs record different target models"):
        prepared(c)


def test_a_run_whose_target_is_not_its_fires_target_is_refused(tmp_path):
    c = write_campaign(tmp_path, spec_of=lambda nonce: "prov/tgt-c" if nonce == "b1" else
                       next(t for t in TARGETS if t["id"] == FIRES[nonce][0])["target_specs"][0])
    with pytest.raises(w3.AnalysisRefusal, match="recorded for target tgt-b"):
        prepared(c)


def test_a_voided_fire_is_listed_and_not_analysed(tmp_path):
    c = write_campaign(tmp_path)
    plan = load_json(c["plan"])
    plan["fires"][0]["voided"] = "truncated by an operational defect"
    c["plan"].write_text(json.dumps(plan), encoding="utf-8")
    prep = prepared(c)
    assert STEMS["a1"] not in {r.stem for r in prep.runs}
    assert any("is voided in the plan" in s["reason"] for s in prep.skipped)
    with pytest.raises(w3.VoidedFire):
        prepared(c, [c["runs"]["a1"]])


def test_a_row_under_another_digest_is_not_comparable_by_name(tmp_path):
    def stale(cell: Cell, row: dict) -> dict:
        if row["key"] == RECOMMENDATION and cell.seed_id == "syn-a" and row["exchange_index"] == 2:
            return {**row, "prompt_file_digest": "0" * 12}
        return row
    c = write_campaign(tmp_path, mutate=stale)
    prep = prepared(c)
    dim = w3.coverage(prep)["dimensions"][f"outcome:{RECOMMENDATION}"]
    assert dim["status"] == "pooled" and dim["pinned_digest"] == PINS[RECOMMENDATION]
    assert sum(dim["rows_outside_pinned_digest_by_run"].values()) == len(TARGETS) * EPOCHS * 3
    st = next(s for s in prep.record.standings[f"exploratory:{RECOMMENDATION}"]
              if s.triple.triple_id == "tgt-a:syn-a#e1")
    assert 2 not in st.comparable
    assert any(f"not {PINS[RECOMMENDATION]}" in p for _, p in st.exclusions[2])


# ------------------------------------------------------------------ 9.8's statements


def _t(sig: bool, direction: str, non_tied: int = 20) -> dict:
    return {"significant": sig, "direction": direction, "non_tied": non_tied}


def _g(sig: bool, direction: str, scenarios: int = 8) -> dict:
    return {"significant": sig, "direction": direction, "scenarios": scenarios}


@pytest.mark.parametrize("primary, gate, row, rule_of", [
    (_t(True, "negative"), _g(True, "negative"), "row1", None),
    (_t(True, "negative"), _g(False, "negative"), "row2", None),
    (_t(True, "positive"), _g(True, "positive"), "row3", "row1"),
    (_t(True, "positive"), _g(False, "none"), "row3", "row2"),
    (_t(False, "negative"), _g(True, "negative"), "row4", None),
    (_t(True, "negative"), _g(True, "positive"), "no_prespecified_row", None),
    (_t(False, "none", non_tied=0), _g(False, "none"), "not_computable", None),
])
def test_the_statement_row_follows_the_plans_table(primary, gate, row, rule_of):
    target = w3.Target("tgt-x", "comparison", "Target X", ("prov/x",))
    table = {r["id"]: r for r in REAL_PLAN["statements"]["primary"]}
    out = w3.statement_row(primary, gate, {"s1": -0.1, "s2": 0.2}, planned_scenarios=8, target=target,
                           statements=table)
    assert out["row_id"] == row and out["rule_of"] == rule_of and out["text"] == table[row]["text"]
    if row in w3.RENDERED_ROWS:
        assert "Target X" in out["rendered"] and "{target}" not in out["rendered"]
        assert out["rendered"] == table[row]["text"].replace("{target}", "Target X")
    else:
        assert out["rendered"] is None
    assert out["selectable_as_registered"] is (row not in ("not_computable", "no_prespecified_row"))


def test_a_gate_on_fewer_scenarios_than_the_plans_is_not_selectable():
    target = w3.Target("tgt-x", "anchor", "Target X", ("prov/x",))
    table = {r["id"]: r for r in REAL_PLAN["statements"]["primary"]}
    out = w3.statement_row(_t(True, "negative"), _g(True, "negative", scenarios=7), {}, planned_scenarios=8,
                           target=target, statements=table)
    assert out["row_id"] == "row1" and out["selectable_as_registered"] is False
    assert "ran on 7 of the plan's 8" in out["not_selectable_reasons"][0]


# ------------------------------------------------------------------ the final analysis


def patterned(cell: Cell, ex: int, measure: str) -> Any:
    """tgt-a: the clinical reply one tier higher at exchanges 6 to 10 (D(colloquial, clinical) = -1/2 on every
    triple; the careful-lay reply equals the colloquial one, so style is 0 and vocabulary -1/2), and on the referral
    seeds the clinical referral one step higher everywhere. tgt-b: no difference anywhere (every triple tied).
    tgt-c: the clinical reply one tier lower at exchange 1 of epoch 1 only (four triples at D = +1/10, four tied)."""
    if measure == "response_only":
        if cell.target == "tgt-a" and cell.register == CLIN and ex >= 6:
            return TIERS[2]
        if cell.target == "tgt-c" and cell.register == CLIN and ex == 1 and cell.epoch == 1:
            return TIERS[0]
    if measure == REFERRAL and cell.target == "tgt-a" and cell.register == CLIN:
        return DIMS[REFERRAL]["values"][1]
    return default_value(cell, ex, measure)


def test_the_final_analysis_on_a_synthetic_campaign(tmp_path, monkeypatch, capsys):
    c = write_campaign(tmp_path, value_fn=patterned)
    doc = run_final(monkeypatch, c, tmp_path)
    capsys.readouterr()
    n = EPOCHS * len(SEEDS_IDS)
    assert doc["bootstrap_seed"] == 20261001 and doc["judge_of_record"] == JUDGE and doc["final"] is True
    assert doc["administratively_truncated_targets"] == {}
    a = doc["targets"]["tgt-a"]
    assert (a["primary_sign_test"]["negative"], a["primary_sign_test"]["non_tied"]) == (n, n)
    assert a["primary_sign_test"]["p"] == 2 / 2 ** n and a["primary_sign_test"]["significant"]
    assert a["effect_size"]["mean_D"] == -0.5 and a["effect_size"]["proportion_D_negative"] == 1.0
    assert a["effect_size"]["bootstrap"]["seed"] == 20261001
    assert a["effect_size"]["bootstrap"]["resamples"] == REAL_PLAN["effect_size"]["bootstrap_resamples"]
    # four scenarios: the gate's floor is 2/16, so it cannot reject; the statement is row 2, naming the target
    gate = a["scenario_gate"]
    assert gate["scenarios"] == 4 and gate["p"] == 2 / 16 and gate["can_reject_at_alpha"] is False
    st = a["statement"]
    assert st["row_id"] == "row2" and st["selectable_as_registered"] is True
    assert "Target A" in st["rendered"] and "{target}" not in st["rendered"]
    assert st["scenarios_with_mean_in_primary_direction"] == SEEDS_IDS
    assert doc["section_9_2"]["target"] == "tgt-a" and doc["section_9_8"]["primary"]["tgt-a"] == st
    assert set(a["leave_one_scenario_out"]) == set(SEEDS_IDS)
    assert a["exchanges_6_10"]["negative"] == n and doc["section_9_5"]["anchor"]["negative"] == n
    assert a["sensitivity"]["exchange_1"]["tied"] == n
    mech = a["sensitivity"]["each_mechanism_alone"]
    assert mech["mech-one"]["negative"] == EPOCHS * 2 and "p" not in mech["mech-one"]
    late = a["sensitivity"]["mech_two" + w3.MECHANISM_WINDOW_SUFFIX]
    assert late["mechanism"] == "mech-two" and late["triples"] == EPOCHS * 2 and "p" not in late
    # ties are dropped from the test and counted: tgt-b is all ties, so its row is not computable
    b = doc["targets"]["tgt-b"]
    assert b["primary_sign_test"]["tied"] == n and b["primary_sign_test"]["non_tied"] == 0
    assert len(b["primary_sign_test"]["tied_triples"]) == n
    assert b["statement"]["row_id"] == "not_computable" and b["statement"]["rendered"] is None
    cc = doc["targets"]["tgt-c"]
    assert (cc["primary_sign_test"]["positive"], cc["primary_sign_test"]["tied"]) == (4, 4)
    assert cc["primary_sign_test"]["p"] == 2 / 16 and cc["statement"]["row_id"] == "row4"
    assert cc["statement"]["rendered"].count("Target C") == 1
    # Holm across the comparison targets only: tgt-b ran no test (kept at p = 1), tgt-c is doubled
    holm = doc["section_9_3"]["holm_primary"]
    assert set(holm) == {"tgt-b", "tgt-c"} and holm["tgt-b"]["ran"] is False
    assert holm["tgt-c"]["p_holm"] == pytest.approx(2 * 2 / 16)
    assert set(doc["section_9_3"]["between_targets"]["by_target"]) == {"tgt-a", "tgt-b", "tgt-c"}
    # 9.4: style tied everywhere, vocabulary negative, the paired difference positive: no pre-specified statement
    reg = doc["section_9_4"]["registered"]
    assert reg["tests"]["style"]["non_tied"] == 0 and reg["tests"]["vocabulary"]["negative"] == n
    assert reg["tests"]["paired_difference"]["positive"] == n
    assert reg["holm"]["paired_difference"]["significant_after_holm"] is True
    assert reg["statement"]["statement_id"] == "no_prespecified_statement"
    pooled = doc["section_9_4"]["prespecified_secondary"]
    assert pooled["tests"]["vocabulary"]["triples"] == n * len(TARGETS) and "across targets" in pooled["label"]
    # 9.6: the family of three per target, Holm-corrected; the referral outcome descriptive per target, one pooled test
    exp = a["exploratory"]
    assert list(exp["tests"]) == FAMILY and set(exp["holm"]) == set(FAMILY)
    assert exp["tests"][FAMILY[-1]]["instrument"] == {"kind": "tier", "key": "response_only", "flag": FLAG}
    ref = a["restricted_outcomes_descriptive"][REFERRAL]
    assert (ref["negative"], ref["triples"], ref["test"]) == (EPOCHS * 2, EPOCHS * 2, "none (descriptive)")
    across = doc["section_9_6"]["restricted_outcomes_across_targets"][REFERRAL]
    assert across["triples"] == EPOCHS * 2 * len(TARGETS) and across["negative"] == EPOCHS * 2
    assert across["p"] == 2 / 16 and "uncorrected" in across["label"]
    counts = a["coverage_only"][COVERAGE_ONLY[0]]["by_wording"]
    assert counts[COL] == {str(DIMS[COVERAGE_ONLY[0]]["values"][0]): n * 10}
    assert doc["section_9_8"]["every_statement_carries"]["judge_of_record"] == JUDGE
    assert doc["secondary_judge"] is None


def test_the_final_analysis_is_reproducible_from_its_seed(tmp_path):
    c = write_campaign(tmp_path, value_fn=patterned)
    prep = prepared(c)
    first = w3.final_analysis(prep, resamples=300)
    again = w3.final_analysis(prep, resamples=300)
    assert first["targets"]["tgt-a"]["effect_size"]["bootstrap"] == again["targets"]["tgt-a"]["effect_size"]["bootstrap"]
    assert first["targets"]["tgt-a"]["effect_size"]["bootstrap"]["seed"] == 20261001


def test_without_final_nothing_is_ranked(tmp_path, capsys):
    c = write_campaign(tmp_path, value_fn=patterned)
    assert w3.main(cli_args(c)) == 0
    doc = json.loads(capsys.readouterr().out)
    text = json.dumps(doc)
    for forbidden in ('"D"', '"negative"', '"positive"', '"p"', '"by_wording"', '"statement"'):
        assert forbidden not in text
    assert doc["final"] is False and doc["bootstrap_seed"] == 20261001
    exploratory = doc["coverage"]["contrasts"][f"exploratory:{RECOMMENDATION}"]
    assert exploratory["register_labels_withheld"] is True


def test_final_refuses_another_seed_another_plan_and_an_existing_artifact(tmp_path, monkeypatch, capsys):
    c = write_campaign(tmp_path)
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--seed", "7")) == 2
    assert "fixes the bootstrap seed at 20261001" in capsys.readouterr().err
    other = tmp_path / "other_plan.json"
    other.write_text(c["plan"].read_text(encoding="utf-8"), encoding="utf-8")
    args = cli_args(c, "--final", "--out", str(out))
    args[args.index("--plan") + 1] = str(other)
    assert w3.main(args) == 2 and "reads only the committed plan" in capsys.readouterr().err
    out.write_text("{}", encoding="utf-8")
    assert w3.main(cli_args(c, "--final", "--out", str(out))) == 2
    assert "never overwrites" in capsys.readouterr().err


def test_a_target_epoch_not_landed_needs_a_declared_truncation_the_journal_supports(tmp_path, monkeypatch, capsys):
    c = write_campaign(tmp_path, fires=tuple(n for n in FIRES if n != "c2"))
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out))) == 2
    assert "have not landed" in capsys.readouterr().err
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--declare-truncated", "provider outage")) == 2
    assert "fire c2" in capsys.readouterr().err
    final_ready(monkeypatch, c, ({"trigger": "petri-audit", "nonce": "c2", "fired_utc": "2026-10-20T00:00:00Z",
                                  "resolved": True, "evicted": False},))
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--declare-truncated", "provider outage")) == 0
    doc = load_json(out)
    assert doc["administratively_truncated_targets"] == {"tgt-c": [2]}
    assert doc["truncation_reason"] == "provider outage"
    assert doc["targets"]["tgt-c"]["primary_sign_test"]["triples"] == len(SEEDS_IDS)


def test_not_computable_outcomes_are_named(tmp_path):
    c = write_campaign(tmp_path, mechanisms={"mech-one": SEEDS_IDS, "mech-two": []})
    plan = load_json(c["plan"])
    plan["exploratory_outcomes"]["restricted_to_seeds"] = {REFERRAL: []}
    c["plan"].write_text(json.dumps(plan), encoding="utf-8")
    prep = prepared(c)
    result = w3.final_analysis(prep, resamples=100)
    a = result["targets"]["tgt-a"]
    late = "mech_two" + w3.MECHANISM_WINDOW_SUFFIX
    assert a["sensitivity"][late]["status"] == "not computable" and "has no seed" in a["sensitivity"][late]["reason"]
    assert a["sensitivity"]["each_mechanism_alone"]["mech-two"]["status"] == "absent"
    assert a["restricted_outcomes_descriptive"][REFERRAL]["status"] == "not computable"
    assert result["section_9_6"]["restricted_outcomes_across_targets"][REFERRAL]["status"] == "not computable"
    assert w3.coverage(prep)["contrasts"][f"restricted:{REFERRAL}"]["status"] == "not computable"


# ------------------------------------------------------------------ the secondary judge (owner decision Q8)


def second_values(cell: Cell, ex: int, measure: str) -> Any:
    """The secondary judge sees no difference anywhere, and its referral reading is one step higher throughout."""
    if measure == REFERRAL:
        return DIMS[REFERRAL]["values"][1]
    return default_value(cell, ex, measure)


def test_the_secondary_judge_gets_its_own_labelled_tables_never_mixed_with_the_record(tmp_path, monkeypatch, capsys):
    c = write_campaign(tmp_path, value_fn=patterned)
    for nonce in FIRES:
        write_regrade(c, nonce, SECOND, f"q8-{nonce}", value_fn=second_values)
    doc = run_final(monkeypatch, c, tmp_path, "--secondary-judge", SECOND)
    capsys.readouterr()
    n = EPOCHS * len(SEEDS_IDS)
    # the registered tables are the judge of record's alone
    assert doc["targets"]["tgt-a"]["primary_sign_test"]["negative"] == n
    sec = doc["secondary_judge"]
    assert sec["judge_model"] == SECOND and sec["label"].startswith("secondary")
    assert sec["targets"]["tgt-a"]["primary_sign_test"]["tied"] == n
    assert sec["targets"]["tgt-a"]["statement"]["selectable_as_registered"] is False
    assert all(v["status"] == "covered" for v in sec["coverage"].values())
    agree = sec["agreement"]["tier_response_only"]
    # the record and the secondary differ at exchanges 6-10 of tgt-a's clinical conversations and at exchange 1 of
    # tgt-c's epoch-1 clinical conversations; everywhere else they agree, all within one tier
    total = len(TARGETS) * n * 3 * w2.EXCHANGES
    differ = n * 5 + len(SEEDS_IDS)
    assert agree["exchanges_both_admissible"] == total and agree["exact_agreement"] == total - differ
    assert agree["within_one"] == total
    assert (agree["secondary_ranked_lower"], agree["secondary_ranked_higher"]) == (n * 5, len(SEEDS_IDS))
    holds = {r["test"]: r["holds"] for r in sec["registered_test_directions"]}
    assert holds["targets.tgt-a.primary_sign_test"] is False
    assert {r["judge_model"] for run in sec["runs"] for r in [run["rows_from"]]} == {SECOND}


def test_a_secondary_that_does_not_cover_the_records_exchanges_is_refused_with_counts(tmp_path, monkeypatch, capsys):
    c = write_campaign(tmp_path, value_fn=patterned)
    for nonce in FIRES:
        if nonce != "c2":
            write_regrade(c, nonce, SECOND, f"q8-{nonce}")
    prep = prepared(c, secondary_judge=SECOND)
    assert prep.secondary_complete is False
    primary = prep.secondary_coverage["primary"]
    assert primary["status"] == "not covered" and primary["triples_affected"] == len(SEEDS_IDS)
    assert primary["record_exchange_sides_not_comparable_under_secondary"] == len(SEEDS_IDS) * 2 * w2.EXCHANGES
    assert primary["reasons"] == {"no final row": len(SEEDS_IDS) * 2 * w2.EXCHANGES}
    assert any("no re-grade by" in (r["reason"] or "") for r in w3.coverage(prep)["secondary_judge"]["runs"])
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--secondary-judge", SECOND)) == 2
    assert "do not cover the exchanges" in capsys.readouterr().err and not out.exists()


def test_the_secondary_judge_cannot_be_the_judge_of_record_under_another_spelling(tmp_path):
    c = write_campaign(tmp_path)
    with pytest.raises(w3.AnalysisRefusal, match="is the judge of record"):
        prepared(c, secondary_judge="anthropic:" + JUDGE)


def test_a_contrast_refused_for_the_record_is_refused_by_name_for_the_secondary(tmp_path):
    """Stand-in review of PR #113: align_secondary skips a contrast the judge of record's reading refused, so the
    secondary had no standings for it and the secondary's tables failed with a bare KeyError. It is now reported as
    refused for the judge of record."""
    c = write_campaign(tmp_path, value_fn=patterned)
    for nonce in FIRES:
        write_regrade(c, nonce, SECOND, f"q8-{nonce}", value_fn=second_values)
    prep = prepared(c, secondary_judge=SECOND)
    name = next(s.name for s in prep.specs if s.name not in ("primary", "decomposition"))
    prep.record.refused_specs[name] = "no row under the pinned prompt digest"
    prep.secondary_standings.pop(name, None)
    doc = w3.final_analysis(prep, resamples=50)
    assert json.dumps(doc["secondary_judge"]).count("refused for the judge of record: no row under the pinned") >= 1


# ------------------------------------------------------------------ review of PR #113 (Codex)


def test_final_refuses_a_run_list_that_leaves_out_a_landed_plan_fire(tmp_path, monkeypatch, capsys):
    """Codex, PR #113: with run paths given, the fires left out were classed as not landed, and a declared truncation
    accepted them because a landed fire's journal entry is resolved too. Every landed plan fire must be analysed."""
    c = write_campaign(tmp_path)
    final_ready(monkeypatch, c, ({"trigger": "petri-audit", "nonce": "c2", "fired_utc": "2026-10-20T00:00:00Z",
                                  "resolved": True, "evicted": False},))
    out = tmp_path / "final.json"
    subset = [str(c["runs"][n]) for n in FIRES if n != "c2"]
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--declare-truncated", "outage", *subset)) == 2
    err = capsys.readouterr().err
    assert "carries plan fire c2 (target tgt-c, epoch 2) but is not among the runs given" in err
    assert not out.exists()
    # every landed fire given: no refusal of that kind
    every = [str(c["runs"][n]) for n in FIRES]
    assert w3.main(cli_args(c, "--final", "--out", str(out), *every)) == 0


def test_registered_test_directions_cover_every_test_the_tables_emit(tmp_path, monkeypatch, capsys):
    """Codex, PR #113: the secondary's direction check covered only each target's primary test, gate and exchanges
    6-10 test. It now covers every test analysis_sections emits."""
    c = write_campaign(tmp_path, value_fn=patterned)
    for nonce in FIRES:
        write_regrade(c, nonce, SECOND, f"q8-{nonce}", value_fn=second_values)
    doc = run_final(monkeypatch, c, tmp_path, "--secondary-judge", SECOND)
    capsys.readouterr()
    tests = {r["test"] for r in doc["secondary_judge"]["registered_test_directions"]}
    assert tests == set(w3.emitted_tests(doc))
    for path in ("targets.tgt-a.primary_sign_test", "targets.tgt-a.scenario_gate", "targets.tgt-a.exchanges_6_10",
                 "targets.tgt-a.leave_one_scenario_out.syn-a", "targets.tgt-b.sensitivity.exchange_1",
                 f"targets.tgt-c.exploratory.tests.{FAMILY[0]}", "section_9_4.registered.tests.paired_difference",
                 "section_9_4.prespecified_secondary.tests.style",
                 f"section_9_6.restricted_outcomes_across_targets.{REFERRAL}"):
        assert path in tests, path
    # descriptive blocks carry no test
    assert not any("each_mechanism_alone" in t or "restricted_outcomes_descriptive" in t for t in tests)


def _truncated(nonce: str, m: dict) -> None:
    if nonce == "a1":
        m["artifacts"]["judge_of_record"]["truncated"] = True


def _short(nonce: str, m: dict) -> None:
    if nonce == "a1":
        m["artifacts"]["judge_of_record"]["planned"] = m["artifacts"]["judge_of_record"]["planned"] + 5


@pytest.mark.parametrize("update, named", [(_truncated, "truncated is True"), (_short, "judgments (judged")])
def test_an_incomplete_judge_pass_registers_no_rows_and_refuses_final(tmp_path, monkeypatch, capsys, update, named):
    """Codex, PR #113: verify_run checks integrity, not completeness, so a truncated or short judging pass registered
    its partial rows. Such a run now has no registered rows, named, and --final refuses."""
    c = write_campaign(tmp_path, manifest_update=update)
    run = next(r for r in prepared(c).runs if r.stem == STEMS["a1"])
    assert not run.registered and run.rows == [] and "incomplete" in run.unregistered_reason
    assert named in run.unregistered_reason
    final_ready(monkeypatch, c)
    assert w3.main(cli_args(c, "--final", "--out", str(tmp_path / "final.json"))) == 2
    assert f"run {STEMS['a1']} has no registered rows" in capsys.readouterr().err


def test_a_truncated_regrade_registers_no_rows_and_leaves_the_secondary_short(tmp_path):
    c = write_campaign(tmp_path, judge_of=lambda nonce: OTHER_ROUTE if nonce == "b1" else JUDGE)
    write_regrade(c, "b1", JUDGE, "rg-b", truncated=True)
    add_regrade_fire(c, "rg-b", [STEMS["b1"]])
    run = next(r for r in prepared(c).runs if r.stem == STEMS["b1"])
    assert not run.registered and "re-grade under judge.judge_model is incomplete" in run.unregistered_reason
    (tmp_path / "second").mkdir()
    c2 = write_campaign(tmp_path / "second")
    for nonce in FIRES:
        write_regrade(c2, nonce, SECOND, f"q8-{nonce}", truncated=nonce == "a2")
    prep = prepared(c2, secondary_judge=SECOND)
    assert prep.secondary_complete is False
    reasons = [r["reason"] for r in w3.coverage(prep)["secondary_judge"]["runs"] if r["reason"]]
    assert len(reasons) == 1 and "is incomplete" in reasons[0]


def test_a_run_failing_the_claim_grade_contract_registers_no_rows(tmp_path, monkeypatch, capsys):
    """Codex, PR #113: execution.claim_grade_eligible was only copied into provenance. Every wave-3 seed is declared
    claim-grade (design note section 2), so a run that fails the contract is an operational defect fires_rule voids;
    it registers no rows, named, and --final refuses."""
    def failed(nonce: str, m: dict) -> None:
        if nonce == "b2":
            m["execution"]["claim_grade_eligible"] = False
            m["execution"]["contract_checks"]["no_prefill"] = {"status": "fail", "detail": "synthetic"}
    c = write_campaign(tmp_path, manifest_update=failed)
    prep = prepared(c)
    run = next(r for r in prep.runs if r.stem == STEMS["b2"])
    assert not run.registered and run.rows == []
    assert "fails the claim-grade contract" in run.unregistered_reason and "no_prefill" in run.unregistered_reason
    assert all(not t.conversations[COL] for t in prep.triples if t.run_stem == STEMS["b2"])
    final_ready(monkeypatch, c)
    assert w3.main(cli_args(c, "--final", "--out", str(tmp_path / "final.json"))) == 2
    assert "fails the claim-grade contract" in capsys.readouterr().err


def test_a_coverage_only_table_is_refused_when_its_dimension_is(tmp_path):
    """Codex, PR #113: the coverage-only value counts were built even when the dimension check refused the outcome
    (registry definitions that differ across runs), merging rows that are not one measurement."""
    key = COVERAGE_ONLY[0]
    changed = deepcopy(REGISTRY)
    entry = next(d for d in changed["dimensions"] if d["id"] == key)
    entry["values"] = list(reversed(entry["values"]))
    registry = tmp_path / "registry_changed.json"
    registry.write_text(json.dumps(changed), encoding="utf-8")

    def recorded(nonce: str, m: dict) -> None:
        if nonce == "a1":
            m["framework"]["outcome_registry_sha256"] = sha256_file(registry)
    c = write_campaign(tmp_path, manifest_update=recorded)
    prep = prepared(c, registry_versions=[registry])
    assert prep.record.dimensions[("outcome", key)].pooled is False
    result = w3.final_analysis(prep, resamples=50)
    table = result["targets"]["tgt-a"]["coverage_only"][key]
    assert table["status"] == "refused" and "differs across the pooled runs" in table["reason"]
    assert "by_wording" not in table


# ------------------------------------------------------------------ second review of PR #113


def test_comparison_statements_use_holm_before_selecting_a_row(tmp_path: Path) -> None:
    def six_negative(cell: Cell, exchange: int, measure: str) -> Any:
        if measure == "response_only" and cell.register == CLIN:
            if cell.target == "tgt-a" or (cell.target == "tgt-b" and cell.seed_id != SEEDS_IDS[-1]):
                return TIERS[2]
        return default_value(cell, exchange, measure)

    result = w3.final_analysis(prepared(write_campaign(tmp_path, value_fn=six_negative)), resamples=20)
    block = result["targets"]["tgt-b"]
    adjusted = result["section_9_3"]["holm_primary"]["tgt-b"]
    assert block["primary_sign_test"]["p"] == 2 / 64
    assert block["primary_sign_test"]["significant"] is True
    assert adjusted["p_holm"] == 4 / 64 and adjusted["significant_after_holm"] is False
    statement = block["statement"]
    assert statement["row_id"] == "row4" and statement["primary_significant"] is False
    assert statement["primary_p_holm"] == adjusted["p_holm"]
    assert result["section_9_8"]["primary"]["tgt-b"] == statement
    assert result["targets"]["tgt-a"]["statement"]["row_id"] == "row2"


@pytest.mark.parametrize(("dirty", "state"), [("script", "modified"), ("wave2_module", "staged"),
                                            ("judge_runner", "modified"), ("rejudge", "modified"),
                                            ("seed_file", "modified"), ("outcome_registry", "modified"),
                                            ("registry_version", "modified"), ("prompt", "modified"), ("run_manifest", "untracked"),
                                            ("regrade_judgments", "untracked"), ("judge_providers", "modified")])
def test_final_refuses_uncommitted_code_and_data_inputs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        dirty: str, state: str) -> None:
    c = write_campaign(tmp_path)
    extra: list[str] = []
    version = tmp_path / "registry-version.json"
    if dirty == "registry_version":
        shutil.copyfile(OUTCOME_REGISTRY, version)
        extra = ["--registry-version", str(version)]
    if dirty in ("regrade_judgments", "judge_providers"):
        for nonce in FIRES:
            write_regrade(c, nonce, SECOND, f"second-{nonce}")
        extra = ["--secondary-judge", SECOND]
    final_ready(monkeypatch, c)
    path = {"seed_file": c["seeds"], "outcome_registry": tmp_path / "static/outcomes.json",
            "registry_version": version, "run_manifest": c["runs"]["a1"] / "manifest.json",
            "prompt": c["static_files"][(ROOT / DIMS[RECOMMENDATION]["detection"]["judge_prompt_ref"]).resolve()],
            "judge_providers": c["static_files"][w3.spend.PROVIDERS_PATH.resolve()],
            "regrade_judgments": rejudge.output_dir(c["rejudge"], SECOND, STEMS["a1"]) / rejudge.JUDGMENTS_NAME,
            **c["code_files"]}[dirty]
    if state == "untracked":
        # Preserve valid manifest bindings, proving that integrity is not proof of commit.
        plumbing(tmp_path, "rm", "--cached", "--", str(path.relative_to(tmp_path)))
    else:
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        if state == "staged":
            plumbing(tmp_path, "add", "--", str(path.relative_to(tmp_path)))
    out = tmp_path / "final.json"

    def unexpected_analysis(*args: Any, **kwargs: Any) -> dict:
        pytest.fail("final statistics ran before the uncommitted-input refusal")

    monkeypatch.setattr(w3, "final_analysis", unexpected_analysis)
    assert w3.main(cli_args(c, "--final", "--out", str(out), *extra)) == 2
    expected = "cannot be shown to be committed" if state == "untracked" else "has uncommitted changes"
    assert expected in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("nonce", [None, "", " ", " c2 ", 5, [], {}])
def test_final_refuses_an_omitted_manifest_without_a_usable_nonce(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, nonce: Any) -> None:
    c = write_campaign(tmp_path)
    path = c["runs"]["c2"] / "manifest.json"
    record = load_json(path)
    record["spend"]["journal_nonce"] = nonce
    path.write_text(json.dumps(record), encoding="utf-8")
    final_ready(monkeypatch, c, ({"trigger": "petri-audit", "nonce": "c2", "fired_utc": "2026-10-20T00:00:00Z",
                                 "resolved": True, "evicted": False},))
    out = tmp_path / "final.json"
    subset = [str(c["runs"][n]) for n in FIRES if n != "c2"]
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--declare-truncated", "outage", *subset)) == 2
    err = capsys.readouterr().err
    assert "spend.journal_nonce" in err and "left out of the run list is unknown" in err
    assert not out.exists()


def test_leave_one_scenario_out_is_not_computable_for_an_absent_scenario(tmp_path: Path) -> None:
    def unusable(cell: Cell, row: dict) -> dict:
        if cell.target == "tgt-a" and cell.seed_id == SEEDS_IDS[-1] and row["key"] == "response_only":
            row["value"] = None
        return row

    result = w3.final_analysis(prepared(write_campaign(tmp_path, value_fn=patterned, mutate=unusable)), resamples=20)
    target = result["targets"]["tgt-a"]
    assert target["scenario_gate"]["scenarios"] == len(SEEDS_IDS) - 1
    omitted = target["leave_one_scenario_out"][SEEDS_IDS[-1]]
    assert omitted["status"] == "not computable" and "no triple" in omitted["reason"]
    assert "p" not in omitted and "significant" not in omitted and "direction" not in omitted
    assert target["leave_one_scenario_out"][SEEDS_IDS[0]]["triples"] == 4
    assert f"targets.tgt-a.leave_one_scenario_out.{SEEDS_IDS[-1]}" not in w3.emitted_tests(result)


def test_every_secondary_statement_is_marked_non_registered(tmp_path: Path) -> None:
    c = write_campaign(tmp_path, value_fn=patterned)
    for nonce in FIRES:
        write_regrade(c, nonce, SECOND, f"second-{nonce}", value_fn=second_values)
    result = w3.final_analysis(prepared(c, secondary_judge=SECOND), resamples=20)
    secondary = result["secondary_judge"]
    statements = [block["statement"] for block in secondary["targets"].values()]
    statements.extend([secondary["section_9_2"]["statement"],
                       *secondary["section_9_8"]["primary"].values(),
                       secondary["section_9_4"]["registered"]["statement"],
                       secondary["section_9_4"]["prespecified_secondary"]["statement"],
                       secondary["section_9_8"]["decomposition_registered"],
                       secondary["section_9_8"]["decomposition_across_targets"]])
    for statement in statements:
        assert statement["selectable_as_registered"] is False
        assert statement["not_selectable_reasons"].count(w3.SECONDARY_REASON) == 1
    assert result["targets"]["tgt-a"]["statement"]["selectable_as_registered"] is True
    assert w3.SECONDARY_REASON not in json.dumps(result["section_9_4"])


@pytest.mark.parametrize("change_window", [False, True])
def test_duplicate_sensitivity_names_are_refused(tmp_path: Path, change_window: bool) -> None:
    plan = synthetic_plan(tmp_path / "seeds.json")
    original = next(s for s in plan["sensitivity"] if s["name"] not in w3.SENSITIVITY_RULES)
    duplicate = deepcopy(original)
    if change_window:
        duplicate["window"] = next(name for name in plan["windows"] if name != original["window"])
    plan["sensitivity"].append(duplicate)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(w3.AnalysisRefusal, match=re.escape(f"({original['name']!r}): repeated name")):
        w3.load_plan(path)


@pytest.mark.parametrize("live_state", ["resolved", "pending", "evicted", "missing", "no_live_fire"])
def test_truncation_validates_the_live_replacement_before_voided_history(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, live_state: str) -> None:
    c = write_campaign(tmp_path, fires=tuple(n for n in FIRES if n != "c2"))
    plan = load_json(c["plan"])
    plan["fires"].append({"journal_nonce": "superseded", "target": "tgt-c", "campaign_epoch": 2,
                          "voided": "evicted before completion"})
    if live_state == "no_live_fire":
        plan["fires"] = [f for f in plan["fires"] if f["journal_nonce"] != "c2"]
    c["plan"].write_text(json.dumps(plan), encoding="utf-8")
    prior = {"trigger": "petri-audit", "nonce": "superseded", "fired_utc": "2026-10-20T00:00:00Z",
             "resolved": True, "evicted": True}
    journal = [prior]
    if live_state not in ("missing", "no_live_fire"):
        journal.append({**prior, "nonce": "c2", "resolved": live_state != "pending",
                        "evicted": live_state == "evicted"})
    final_ready(monkeypatch, c, tuple(journal))
    out = tmp_path / "final.json"
    code = w3.main(cli_args(c, "--final", "--out", str(out), "--declare-truncated", "replacement failed to land"))
    if live_state == "resolved":
        assert code == 0
        doc = load_json(out)
        assert doc["administratively_truncated_targets"] == {"tgt-c": [2]}
        history = doc["coverage"]["epochs_not_landed"]["tgt-c"]["2"]
        assert history["live_fire"] == "c2" and history["voided_fires"] == ["superseded"]
    else:
        assert code == 2 and not out.exists()
        nonce = "superseded" if live_state == "no_live_fire" else "c2"
        assert f"fire {nonce}:" in capsys.readouterr().err


def test_final_refuses_a_claim_grade_fire_that_omits_a_planned_seed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    c = write_campaign(tmp_path, seed_ids_of=lambda nonce: SEEDS_IDS[:-1] if nonce == "a1" else SEEDS_IDS)
    partial = c["runs"]["a1"]
    manifest = load_json(partial / "manifest.json")
    assert w3.verify_run(partial) == []
    assert w3.claim_grade_problem(manifest) is None
    assert w3.incomplete_pass(manifest["artifacts"]["judge_of_record"], "judge") is None
    # The next epoch covers the missing seed, so a pooled scenario gate alone cannot detect this partial fire.
    assert {s["seed_id"] for s in load_json(c["runs"]["a2"] / "manifest.json")["seeds"]} == set(SEEDS_IDS)
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"

    def unexpected_analysis(*args: Any, **kwargs: Any) -> dict:
        pytest.fail("final statistics ran before the partial-fire refusal")

    monkeypatch.setattr(w3, "final_analysis", unexpected_analysis)
    assert w3.main(cli_args(c, "--final", "--out", str(out))) == 2
    error = capsys.readouterr().err
    assert "fire a1 seed set differs from the plan's scenarios" in error
    assert f"missing {[SEEDS_IDS[-1]]}" in error and "unplanned []" in error
    assert not out.exists()


@pytest.mark.parametrize("field", ["primary.contrast", "decomposition.contrasts.style",
                                  "decomposition.contrasts.vocabulary"])
@pytest.mark.parametrize("form", ["null", "number", "boolean", "text", "mapping"])
def test_non_list_contrasts_are_named_cli_refusals(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        field: str, form: str) -> None:
    c = write_campaign(tmp_path, fires=())
    plan = load_json(c["plan"])
    parts = field.split(".")
    node = plan
    for key in parts[:-1]:
        node = node[key]
    key = parts[-1]
    malformed = {"null": None, "number": 3, "boolean": True, "text": "unexpected",
                 "mapping": dict.fromkeys(node[key])}
    node[key] = malformed[form]
    c["plan"].write_text(json.dumps(plan), encoding="utf-8")
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out))) == 2
    error = capsys.readouterr().err
    assert error.startswith("refused: plan file ") and f"{field} must be the list" in error
    assert "Traceback" not in error and not out.exists()


@pytest.mark.parametrize("field", ["decomposition_set", "primary.window", "secondary_exchanges_6_10.window",
                                  "judge.judge_model"])
@pytest.mark.parametrize("value", [[], {}, True, 4])
def test_scalar_plan_references_refuse_before_membership(
        tmp_path: Path, field: str, value: Any) -> None:
    c = write_campaign(tmp_path, fires=())
    doc = load_json(c["plan"])
    node = doc
    parts = field.split(".")
    for key in parts[:-1]:
        node = node[key]
    node[parts[-1]] = value
    c["plan"].write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(w3.AnalysisRefusal, match=field):
        w3.load_plan(c["plan"])


def test_coverage_only_refuses_a_tier_measure(tmp_path: Path) -> None:
    c = write_campaign(tmp_path, fires=())
    doc = load_json(c["plan"])
    doc["exploratory_outcomes"]["coverage_only"] = [next(m.name for m in w2.SECONDARY_MEASURES if m.kind == "tier")]
    c["plan"].write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(w3.AnalysisRefusal, match="coverage_only.*not an outcome dimension"):
        w3.load_plan(c["plan"])


@pytest.mark.parametrize("path,status", [(None, "not written"), ("scripts/another.py", "written"),
                                        ("scripts/petri_w3_register_contrast.py", "not written")])
def test_final_requires_the_approved_script_binding(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        path: Any, status: str) -> None:
    c = write_campaign(tmp_path)
    doc = load_json(c["plan"])
    doc["analysis_script"].update(path=path, status=status)
    c["plan"].write_text(json.dumps(doc), encoding="utf-8")
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out))) == 2
    assert "analysis_script must name" in capsys.readouterr().err
    assert not out.exists()


def test_final_binds_the_secondary_to_the_plan_designation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    c = write_campaign(tmp_path, secondary=True)
    doc = load_json(c["plan"])
    doc["judge"]["second_family_regrade"] = REAL_PLAN["judge"]["second_family_regrade"]
    c["plan"].write_text(json.dumps(doc), encoding="utf-8")
    final_ready(monkeypatch, c)
    out = tmp_path / "final.json"
    assert w3.main(cli_args(c, "--final", "--out", str(out), "--secondary-judge", SECOND)) == 2
    assert "not the plan's designated" in capsys.readouterr().err
    assert not out.exists()


def test_coverage_cannot_overwrite_an_existing_final_artifact(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "final.json"
    original = b'{"final":true,"preserve":"exact bytes"}\n'
    out.write_bytes(original)
    assert w3.main(["--out", str(out)]) == 2
    assert "overwrites an artifact" in capsys.readouterr().err
    assert out.read_bytes() == original


def test_coverage_uses_exclusive_creation_even_if_destination_appears_during_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    c = write_campaign(tmp_path, fires=())
    out = tmp_path / "coverage.json"
    original_prepare = w3.prepare

    def prepare_and_create(*args: Any, **kwargs: Any) -> w3.Prepared:
        result = original_prepare(*args, **kwargs)
        out.write_text("preserve", encoding="utf-8")
        return result

    monkeypatch.setattr(w3, "prepare", prepare_and_create)
    assert w3.main(cli_args(c, "--out", str(out))) == 2
    assert "appeared while coverage ran" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "preserve"
