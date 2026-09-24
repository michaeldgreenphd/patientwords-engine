"""Mode readapt of the petri-audit lane (scripts/petri_audit/readapt.py and the
CLI pieces around it): the source artifact is chosen by exact name and refused
when missing, expired or listed under another run; the source run directory
must hold its landed target sidecar and nothing else; the downloaded log must
be the one that sidecar priced; the adapt step refuses before writing anything
and leaves the landed sidecar byte-identical; the manifest schema takes the
optional provenance block and still takes every manifest written before it;
and verify-run / verify-chain bind the landed sidecar by digest. 3.11-safe:
the harness-backed end-to-end readapt is in tests/petri/test_zero_cost_e2e.py.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, framework, readapt, seeds  # noqa: E402
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402

SRC = "4242"
STEM = f"run_{SRC}_1"
EVAL_NAME = "2026-09-24T00-09-42-00-00_patientwords-petri-audit_Src.eval"
EVAL_ID = "EvSrc0001"
SOURCE_NONCE = "src-nonce"
PARAMS_SHA = "a" * 64
COMMIT = "c" * 40
NOW = datetime(2026, 9, 24, 2, 0, tzinfo=timezone.utc)
LANDED_RUNS = ROOT / "data" / "petri" / "runs"


def _landed_sidecar(runs: Path, stem: str = STEM, **overrides) -> Path:
    """What the workflow's fallback `spend-report` step leaves for an attempted run whose adaptation failed
    (cli.cmd_spend_report through spend.write_report_sidecar), field for field."""
    d = runs / stem
    d.mkdir(parents=True, exist_ok=True)
    report = {"run_utc": "2026-09-24T00:10:41Z", "run_id": stem, "eval_id": EVAL_ID, "task": "petri-audit",
              "cost_usd": 0.929803, "cost_basis": "engine_repriced_from_inspect_model_usage",
              "usage_missing_models": [], "max_spend_usd": 6.1, "judge_max_spend_usd": 2.5,
              "billing_channel": "anthropic", "models": [],
              "spend_report_reason": "run attempted; no adapted report exists (run or adaptation failed)",
              "eval_log": EVAL_NAME, "run_status": "success", "journal_nonce": SOURCE_NONCE}
    report.update(overrides)
    path = d / f"{stem}.report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def _artifact(run_id: str = SRC, **overrides) -> dict:
    art = {"id": 9001, "node_id": "x", "name": f"petri-audit-raw-eval-{run_id}-1", "size_in_bytes": 433000,
           "expired": False, "digest": "sha256:" + "d" * 64, "created_at": "2026-09-24T00:10:40Z",
           "expires_at": "2026-12-23T00:10:40Z", "workflow_run": {"id": int(run_id), "head_branch": "b"}}
    art.update(overrides)
    return art


def _listing(*arts: dict, total: int | None = None) -> dict:
    arts = arts or (_artifact(), _artifact(id=9002, name=f"petri-audit-exports-{SRC}-1"))
    return {"total_count": len(arts) if total is None else total, "artifacts": list(arts)}


def _journal_entries(nonce: str = SOURCE_NONCE, **extra) -> list[dict]:
    entry = {"trigger": "petri-audit", "fired_utc": "2026-09-24T00:08:16Z", "commit": "", "note": "t",
             "resolved": True, "evicted": False, "nonce": nonce, "params_sha256": PARAMS_SHA, "max_spend": 8.6,
             "lane": "anthropic"}
    entry.update(extra)
    return [entry]


def _params(**overrides) -> dict:
    """The params job's resolved outputs (every value a string), as the workflow passes them."""
    p = {"seeds_file": "docs/framework/petri_seeds.draft.json", "seed_ids": "", "wave": "2",
         "target": "anthropic/claude-haiku-4-5", "mode": "readapt", "epochs": "1", "token_limit": "40000",
         "max_spend": "6.10", "judge": "true", "judge_model": "claude-haiku-4-5", "judge_max_spend": "2.50",
         "judge_max_tokens": "300", "log_model_api": "true", "commit_outputs": "true", "source_run_id": SRC,
         "_nonce": "re-nonce"}
    p.update(overrides)
    return p


def _wave2_ids() -> list[str]:
    return [s["seed_id"] for s in seeds.select_seeds(seeds.load_seed_file(), None, 2)]


def _wave2_digests() -> dict[str, str]:
    return {s["seed_id"]: seeds.seed_digest(s) for s in seeds.select_seeds(seeds.load_seed_file(), None, 2)}


def _plan(runs: Path, **param_overrides) -> dict:
    return readapt.plan(params=_params(**param_overrides), listing=_listing(), runs_dir=runs, seed_ids=_wave2_ids(),
                        journal_entries=_journal_entries(), readapt_run_id="5555", readapt_run_attempt="1",
                        readapt_commit=COMMIT, now=NOW, seed_digests=_wave2_digests())


# ------------------------------------------------------------ source artifact


def test_the_source_artifact_is_chosen_by_its_exact_name_and_refused_by_name_otherwise():
    art = readapt.select_source_artifact(_listing(), SRC, now=NOW)
    assert art == {"id": 9001, "name": f"petri-audit-raw-eval-{SRC}-1", "digest": "sha256:" + "d" * 64,
                   "size_in_bytes": 433000, "created_at": "2026-09-24T00:10:40Z", "expires_at": "2026-12-23T00:10:40Z"}
    # a digest the API does not report is recorded as null, never invented
    assert readapt.select_source_artifact(_listing(_artifact(digest=None)), SRC, now=NOW)["digest"] is None
    cases = [
        (_listing(_artifact(name=f"petri-audit-exports-{SRC}-1")), "has no artifact named"),
        (_listing(_artifact(name=f"petri-audit-raw-eval-{SRC}-2")), "has no artifact named"),   # an attempt-2 log
        (_listing(_artifact(), _artifact(id=9003)), "the source log is ambiguous"),
        (_listing(_artifact(expired=True)), "is expired"),
        (_listing(_artifact(expired=None)), "is expired"),                                        # unknown is not live
        (_listing(_artifact(expires_at="2026-09-24T01:00:00Z")), "expired at"),
        (_listing(_artifact(workflow_run={"id": 1})), "not the source run"),
        (_listing(_artifact(id=None)), "no usable id"),
        (_listing(_artifact(), total=150), "incomplete listing"),
        ({"message": "Not Found"}, "not an object with an `artifacts` list"),
    ]
    for listing, needle in cases:
        with pytest.raises(readapt.ReadaptError, match=needle):
            readapt.select_source_artifact(listing, SRC, now=NOW)
    for bad in ("", "12a", "１２", "-5", None, True):
        with pytest.raises(readapt.ReadaptError, match="numeric workflow run id"):
            readapt.artifact_name(bad)


# ------------------------------------------------------------ source run directory


def test_the_source_run_directory_must_hold_its_landed_sidecar_and_nothing_else(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    assert "no such run directory" in readapt.run_dir_problems(runs, STEM)[0]
    (runs / STEM).mkdir()
    assert "landed target cost sidecar" in readapt.run_dir_problems(runs, STEM)[0]
    _landed_sidecar(runs)
    assert readapt.run_dir_problems(runs, STEM) == []
    # adapted outputs: a landed run is never rewritten
    (runs / STEM / "manifest.json").write_text("{}", encoding="utf-8")
    assert any("already holds adapted outputs (manifest.json)" in p for p in readapt.run_dir_problems(runs, STEM))
    (runs / STEM / "manifest.json").unlink()
    (runs / STEM / "transcripts.jsonl").write_text("", encoding="utf-8")
    assert any("already holds adapted outputs (transcripts.jsonl)" in p for p in readapt.run_dir_problems(runs, STEM))
    (runs / STEM / "transcripts.jsonl").unlink()
    (runs / STEM / "notes.txt").write_text("x", encoding="utf-8")
    assert any("files other than the landed target sidecar and earlier readapts' judge sidecars (notes.txt)" in p
               for p in readapt.run_dir_problems(runs, STEM))
    (runs / STEM / "notes.txt").unlink()
    # a manifest removed after it was chained is a rewrite too
    (runs / manifest_mod.CHAIN_FILE).write_text(f"{STEM}/manifest.json {'e' * 64}\n", encoding="utf-8")
    assert any("already names" in p for p in readapt.run_dir_problems(runs, STEM))


def test_the_landed_sidecar_must_be_the_fallback_writers_with_nonce_eval_and_log(tmp_path):
    runs = tmp_path / "runs"
    path = _landed_sidecar(runs)
    report = readapt.source_report(runs, STEM)
    assert report == {"path": f"{STEM}/{STEM}.report.json", "sha256": framework.sha256_file(path),
                      "journal_nonce": SOURCE_NONCE, "eval_id": EVAL_ID, "eval_log": EVAL_NAME}
    for missing in ("journal_nonce", "eval_log", "eval_id", "spend_report_reason"):
        _landed_sidecar(runs, **{missing: None})
        with pytest.raises(readapt.ReadaptError, match=missing):
            readapt.source_report(runs, STEM)
    path.write_text("[1]", encoding="utf-8")
    with pytest.raises(readapt.ReadaptError, match="not an object"):
        readapt.source_report(runs, STEM)


def test_a_source_run_whose_eval_did_not_complete_is_refused_before_the_download(tmp_path):
    """The fallback sidecar is written for any attempted run with no adapted report, an error or cancelled one
    included (it spent), and records the eval's status. Mode run adapts only a `success` log (`cli run` exits 0 on
    nothing else), so a readapt of any other status would publish a partial log mode run never would: refused by
    the sidecar before the plan is written, and by the log's own status before anything is adapted."""
    runs = tmp_path / "runs"
    for status in ("error", "cancelled", "started", None, "Success"):
        _landed_sidecar(runs, run_status=status)
        with pytest.raises(readapt.ReadaptError, match=f"records run_status {status!r}, not 'success'"):
            readapt.source_report(runs, STEM)
        with pytest.raises(readapt.ReadaptError, match="recovers only a run whose eval completed"):
            _plan(runs)
    _landed_sidecar(runs)
    assert _plan(runs)["target_report"]["journal_nonce"] == SOURCE_NONCE, "a success run still plans"


def test_cli_readapt_plan_refuses_an_error_run_and_writes_no_plan(tmp_path, capsys):
    runs = tmp_path / "runs"
    _landed_sidecar(runs, run_status="error")
    params, listing, journal, out = (tmp_path / n for n in ("params.json", "listing.json", "journal.jsonl", "plan.json"))
    framework.write_json(params, _params())
    framework.write_json(listing, _listing())
    journal.write_text("".join(json.dumps(e) + "\n" for e in _journal_entries()), encoding="utf-8")
    assert cli.main(["readapt-plan", "--params-file", str(params), "--listing", str(listing), "--runs-dir", str(runs),
                     "--journal", str(journal), "--readapt-run-id", "5555", "--readapt-run-attempt", "1",
                     "--readapt-commit", COMMIT, "--out", str(out)]) == 12
    assert "records run_status 'error'" in capsys.readouterr().err and not out.exists()


def test_the_downloaded_log_must_be_the_one_the_sidecar_priced(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    assert "is missing" in readapt.eval_file_problems(logs / EVAL_NAME, EVAL_NAME)[0]
    (logs / EVAL_NAME).write_bytes(b"raw")
    assert readapt.eval_file_problems(logs / EVAL_NAME, EVAL_NAME) == []
    assert "this is not the source run's log" in readapt.eval_file_problems(logs / EVAL_NAME, "other.eval")[0]
    (logs / "second.eval").write_bytes(b"raw")
    assert any("more than one .eval" in p for p in readapt.eval_file_problems(logs / EVAL_NAME, EVAL_NAME))


def test_the_log_must_record_what_the_readapt_fire_states():
    expected = {"eval_id": EVAL_ID, "target": "anthropic/claude-haiku-4-5", "seed_ids": ["a", "b"], "epochs": 1,
                "token_limit": 40000, "log_model_api": True}
    observed = dict(expected, seed_ids=["b", "a"], status="success")   # the run records the selection in file order
    assert readapt.log_problems(expected, observed) == []
    for key, value in (("target", "anthropic/claude-sonnet-4-5"), ("epochs", 2), ("token_limit", 20000),
                       ("log_model_api", False), ("eval_id", "other"), ("seed_ids", ["a"])):
        problems = readapt.log_problems(expected, dict(observed, **{key: value}))
        assert len(problems) == 1 and problems[0].startswith(f"{key}:"), (key, problems)
    # a value the log does not record is a problem, never a match
    assert any("records no token_limit" in p for p in readapt.log_problems(expected, dict(observed, token_limit=None)))
    assert any("no seed selection" in p for p in readapt.log_problems(expected, dict(observed, seed_ids=None)))


def test_the_log_must_record_a_completed_eval_whatever_the_plan_states():
    """The log's own status is compared as well as the sidecar's record of it: `success` only, checked even when
    the expected values name no status, and a log that records none is refused rather than matched."""
    expected = {"eval_id": EVAL_ID, "target": "anthropic/claude-haiku-4-5", "seed_ids": ["a"], "epochs": 1,
                "token_limit": 40000, "log_model_api": True}
    observed = dict(expected, status="success")
    assert readapt.log_problems(expected, observed) == []
    for status in ("error", "cancelled", "started"):
        problems = readapt.log_problems(expected, dict(observed, status=status))
        assert problems == [f"status: the log records {status!r}, and a readapt recovers only a 'success' run "
                            "(mode run adapts nothing from an error or cancelled one)"], problems
        assert readapt.log_problems({}, dict(observed, status=status)), "checked with no expected values at all"
    assert readapt.log_problems(expected, {k: v for k, v in observed.items() if k != "status"}) == [
        "the log records no status; it cannot be shown to be a run whose eval completed"]


# ------------------------------------------------------------ the plan


def test_a_readapt_plan_binds_the_source_run_artifact_sidecar_and_journal_entry(tmp_path):
    runs = tmp_path / "runs"
    sidecar = _landed_sidecar(runs)
    plan = _plan(runs)
    assert plan["run_stem"] == STEM and plan["source_run_id"] == SRC
    assert plan["artifact"]["id"] == 9001 and plan["source_params_sha256"] == PARAMS_SHA
    assert plan["target_report"]["sha256"] == framework.sha256_file(sidecar)
    assert plan["expected"] == {"target": "anthropic/claude-haiku-4-5", "seed_ids": _wave2_ids(), "epochs": 1,
                                "token_limit": 40000, "log_model_api": True, "eval_id": EVAL_ID,
                                "seed_sha256": _wave2_digests()}
    assert plan["readapt"] == {"workflow_run_id": "5555", "workflow_run_attempt": 1, "commit": COMMIT,
                               "journal_nonce": "re-nonce"}
    block = readapt.provenance_block(plan)
    assert block["source_journal_nonce"] == SOURCE_NONCE and block["readapt_journal_nonce"] == "re-nonce"
    assert block["target_report"] == {"path": f"{STEM}/{STEM}.report.json", "sha256": plan["target_report"]["sha256"]}
    # refusals, each by name
    with pytest.raises(readapt.ReadaptError, match="is the source fire's"):
        _plan(runs, _nonce=SOURCE_NONCE)
    with pytest.raises(readapt.ReadaptError, match="no _nonce"):
        _plan(runs, _nonce="")
    with pytest.raises(readapt.ReadaptError, match="needs mode readapt"):
        _plan(runs, mode="run")
    with pytest.raises(readapt.ReadaptError, match="numeric workflow run id"):
        _plan(runs, source_run_id="")
    with pytest.raises(readapt.ReadaptError, match="0 petri-audit journal entries carry the source nonce"):
        readapt.plan(params=_params(), listing=_listing(), runs_dir=runs, seed_ids=["x"], journal_entries=[],
                     readapt_run_id="5555", readapt_run_attempt="1", readapt_commit=COMMIT, now=NOW)
    with pytest.raises(readapt.ReadaptError, match="records no params_sha256"):
        readapt.plan(params=_params(), listing=_listing(), runs_dir=runs, seed_ids=["x"],
                     journal_entries=_journal_entries(params_sha256=None), readapt_run_id="5555",
                     readapt_run_attempt="1", readapt_commit=COMMIT, now=NOW)
    for attempt in ("2", "0", "x"):
        with pytest.raises(readapt.ReadaptError, match="first attempt only"):
            readapt.plan(params=_params(), listing=_listing(), runs_dir=runs, seed_ids=["x"],
                         journal_entries=_journal_entries(), readapt_run_id="5555", readapt_run_attempt=attempt,
                         readapt_commit=COMMIT, now=NOW)
    with pytest.raises(readapt.ReadaptError, match="40-hex commit"):
        readapt.plan(params=_params(), listing=_listing(), runs_dir=runs, seed_ids=["x"],
                     journal_entries=_journal_entries(), readapt_run_id="5555", readapt_run_attempt="1",
                     readapt_commit="HEAD", now=NOW)
    (runs / STEM / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(readapt.ReadaptError, match="already holds adapted outputs"):
        _plan(runs)


def test_cli_readapt_plan_writes_the_plan_or_refuses_by_name_and_writes_nothing(tmp_path, capsys):
    runs = tmp_path / "runs"
    _landed_sidecar(runs)
    params, listing, journal, out = (tmp_path / n for n in ("params.json", "listing.json", "journal.jsonl", "plan.json"))
    framework.write_json(params, _params())
    framework.write_json(listing, _listing())
    journal.write_text("".join(json.dumps(e) + "\n" for e in _journal_entries()), encoding="utf-8")
    argv = ["readapt-plan", "--params-file", str(params), "--listing", str(listing), "--runs-dir", str(runs),
            "--journal", str(journal), "--readapt-run-id", "5555", "--readapt-run-attempt", "1",
            "--readapt-commit", COMMIT, "--out", str(out)]
    assert cli.main(argv) == 0
    plan = framework.load_json(out)
    assert plan["run_stem"] == STEM and plan["expected"]["seed_ids"] == _wave2_ids()
    assert plan["expected"]["seed_sha256"] == _wave2_digests(), "each selected seed's digest in hand, for the adapter"
    assert f"artifact petri-audit-raw-eval-{SRC}-1 id 9001" in capsys.readouterr().out
    out.unlink()
    framework.write_json(listing, _listing(_artifact(expired=True)))
    assert cli.main(argv) == 12
    assert "readapt refused before the download" in capsys.readouterr().err and not out.exists()
    framework.write_json(listing, _listing())
    framework.write_json(params, _params(seed_ids="no-such-seed"))
    assert cli.main(argv) == 12 and "unknown seed id" in capsys.readouterr().err and not out.exists()


# ------------------------------------------------------------ the adapt step


def _staged(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    runs = tmp_path / "runs"
    sidecar = _landed_sidecar(runs)
    logs = tmp_path / "petri-run" / "logs"
    logs.mkdir(parents=True)
    (logs / EVAL_NAME).write_bytes(b"the raw log")
    plan = _plan(runs)
    plan_path = tmp_path / "plan.json"
    framework.write_json(plan_path, plan)
    return runs, sidecar, plan_path, plan


def _adapt_argv(runs: Path, eval_path: Path, plan_path: Path, out_dir: Path | None = None) -> list[str]:
    return ["adapt", "--eval", str(eval_path), "--out-dir", str(out_dir or runs / STEM), "--custody",
            "github_actions_artifact:90d", "--target", "anthropic/claude-haiku-4-5", "--max-spend", "6.10",
            "--judge-max-spend", "2.50", "--token-limit", "40000", "--report", "--readapt", str(plan_path)]


def test_adapt_under_readapt_refuses_before_writing_anything(tmp_path, capsys):
    runs, sidecar, plan_path, plan = _staged(tmp_path)
    logs = tmp_path / "petri-run" / "logs"
    before = sidecar.read_bytes()
    args = cli.build_parser().parse_args(_adapt_argv(runs, logs / EVAL_NAME, plan_path))
    assert cli.readapt_pre_problems(args, plan) == [], "the staged state is exactly what a readapt accepts"
    # every refusal below returns before the harness is imported, so it runs here without it
    (logs / "renamed.eval").write_bytes((logs / EVAL_NAME).read_bytes())
    (logs / EVAL_NAME).unlink()
    assert cli.main(_adapt_argv(runs, logs / "renamed.eval", plan_path)) == 11
    assert "this is not the source run's log" in capsys.readouterr().err
    (logs / "renamed.eval").rename(logs / EVAL_NAME)
    other = runs / "run_7_1"
    other.mkdir()
    assert cli.main(_adapt_argv(runs, logs / EVAL_NAME, plan_path, out_dir=other)) == 11
    assert "is not the source run's directory" in capsys.readouterr().err
    (runs / STEM / "transcripts.jsonl").write_text("", encoding="utf-8")
    assert cli.main(_adapt_argv(runs, logs / EVAL_NAME, plan_path)) == 11
    assert "already holds adapted outputs" in capsys.readouterr().err
    (runs / STEM / "transcripts.jsonl").unlink()
    sidecar.write_text(before.decode("utf-8").replace("0.929803", "0.5"), encoding="utf-8")
    assert cli.main(_adapt_argv(runs, logs / EVAL_NAME, plan_path)) == 11
    assert "changed after the readapt bound it" in capsys.readouterr().err
    sidecar.write_bytes(before)
    assert cli.main(_adapt_argv(runs, logs / EVAL_NAME, plan_path) + ["--run-params", str(tmp_path / "rp.json")]) == 11
    assert "--run-params is the run step's record" in capsys.readouterr().err
    assert sorted(p.name for p in (runs / STEM).iterdir()) == [sidecar.name] and sidecar.read_bytes() == before


def _manifest_stub(eval_id: str = EVAL_ID) -> dict:
    """The manifest fields `write_target_report` reads, as the adapter writes them."""
    return {"run_id": "InspectRun1", "eval_id": eval_id, "created_utc": "2026-09-24T00:09:42Z",
            "usage": {"by_model": [{"model": "anthropic/claude-haiku-4-5", "input_tokens": 10, "output_tokens": 5,
                                    "total_tokens": 15, "calls": 1, "calls_without_usage": 0}]},
            "artifacts": {"raw_eval_log_sha256": "b" * 64}, "spend": {"journal_nonce": SOURCE_NONCE},
            "models": {"target": {"inspect_name": "anthropic/claude-haiku-4-5"}}}


def test_the_landed_target_sidecar_is_left_byte_identical_and_never_rewritten(tmp_path, capsys):
    runs, sidecar, _plan_path, plan = _staged(tmp_path)
    before = sidecar.read_bytes()
    assert cli.write_target_report(runs / STEM, _manifest_stub(), max_spend=6.1, judge_max_spend=2.5, plan=plan) == 0
    assert sidecar.read_bytes() == before, "a readapt books no target spend and leaves the landed sidecar as it is"
    assert "left unchanged" in capsys.readouterr().out
    # the landed sidecar must price the log just adapted
    assert cli.write_target_report(runs / STEM, _manifest_stub("other"), max_spend=6.1, judge_max_spend=2.5,
                                   plan=plan) == 11
    assert "not the adapted log's" in capsys.readouterr().err and sidecar.read_bytes() == before
    # outside a readapt an existing sidecar is refused too, never overwritten (the ordinary path adapts into an
    # empty directory, so this only guards a state that should not arise)
    assert cli.write_target_report(runs / STEM, _manifest_stub(), max_spend=6.1, judge_max_spend=2.5) == 11
    assert "never rewritten" in capsys.readouterr().err and sidecar.read_bytes() == before
    # and the ordinary path still writes a sidecar where none exists
    fresh = tmp_path / "runs" / "run_9_1"
    fresh.mkdir()
    assert cli.write_target_report(fresh, _manifest_stub(), max_spend=1.0, judge_max_spend=None) == 0
    written = framework.load_json(fresh / "run_9_1.report.json")
    assert written["journal_nonce"] == SOURCE_NONCE and written["eval_id"] == EVAL_ID and written["cost_usd"] > 0


# ------------------------------------------------------------ schema and verification


def _landed_manifests() -> list[Path]:
    return sorted(LANDED_RUNS.glob("*/manifest.json"))


def test_the_schema_takes_the_readapt_block_and_every_manifest_written_before_it(tmp_path):
    landed = _landed_manifests()
    assert landed, "the landed runs are the compatibility evidence"
    for path in landed:
        m = framework.load_json(path)
        assert "readapt" not in m
        assert manifest_mod.manifest_problems(m) == [], path
    runs, _sidecar, _plan_path, plan = _staged(tmp_path)
    m = framework.load_json(landed[-1])
    m["readapt"] = readapt.provenance_block(plan)
    sealed = manifest_mod.seal_manifest(m, m["chain"]["prev_sha256"])
    assert manifest_mod.manifest_problems(sealed) == []
    for mutate, needle in ((lambda b: b.update(extra="x"), "unexpected key 'extra'"),
                           (lambda b: b.update(readapt_commit="HEAD"), "readapt_commit"),
                           (lambda b: b.pop("source_artifact"), "missing 'source_artifact'"),
                           (lambda b: b["target_report"].update(path="elsewhere.json"), "target_report.path"),
                           (lambda b: b["source_artifact"].update(name="petri-audit-exports-1-1"), "source_artifact.name")):
        broken = json.loads(json.dumps(m))
        mutate(broken["readapt"])
        problems = manifest_mod.manifest_problems(manifest_mod.seal_manifest(broken, None))
        assert any(needle in p for p in problems), (needle, problems)


def test_verify_run_and_verify_chain_bind_the_landed_sidecar_of_a_readapted_run(tmp_path):
    for path in _landed_manifests():
        assert manifest_mod.verify_run(path.parent) == [], path
    ok, msg = manifest_mod.verify_chain(LANDED_RUNS)
    assert ok, msg
    # a readapted run: a landed run directory with the provenance block added and the manifest resealed
    source = _landed_manifests()[-1].parent
    runs = tmp_path / "runs"
    shutil.copytree(source, runs / source.name)
    sidecar = runs / source.name / f"{source.name}.report.json"
    m = framework.load_json(runs / source.name / "manifest.json")
    m["readapt"] = {"source_workflow_run_id": source.name.split("_")[1], "source_run_stem": source.name,
                    "source_journal_nonce": "n", "source_params_sha256": PARAMS_SHA, "source_eval_log": EVAL_NAME,
                    "source_artifact": {"id": 1, "name": f"petri-audit-raw-eval-{source.name.split('_')[1]}-1",
                                        "digest": None, "size_in_bytes": None, "created_at": None, "expires_at": None},
                    "target_report": {"path": f"{source.name}/{sidecar.name}", "sha256": framework.sha256_file(sidecar)},
                    "readapt_workflow_run_id": "5555", "readapt_workflow_run_attempt": 1, "readapt_commit": COMMIT,
                    "readapt_journal_nonce": "r"}
    sealed = manifest_mod.seal_manifest(m, None)
    manifest_mod.write_manifest(runs / source.name / "manifest.json", sealed)
    (runs / manifest_mod.CHAIN_FILE).write_text(f"{source.name}/manifest.json {sealed['chain']['manifest_sha256']}\n",
                                                encoding="utf-8")
    assert manifest_mod.verify_run(runs / source.name) == []
    ok, msg = manifest_mod.verify_chain(runs)
    assert ok, msg
    # a downloaded copy extracted under another folder name still verifies (verify-run looks files up by basename)
    shutil.copytree(runs / source.name, tmp_path / "download")
    assert manifest_mod.verify_run(tmp_path / "download") == []
    # the landed sidecar rewritten after the readapt is detected by both
    report = framework.load_json(sidecar)
    report["cost_usd"] = 0.0
    framework.write_json(sidecar, report)
    assert any("readapt.target_report" in p and "never rewritten" in p for p in manifest_mod.verify_run(runs / source.name))
    ok, msg = manifest_mod.verify_chain(runs)
    assert not ok and "readapt.target_report" in msg
    sidecar.unlink()
    assert any("is missing" in p for p in manifest_mod.verify_run(runs / source.name))


# ------------------------------------------------------------ a retry after a readapt whose judge failed

PRIOR_RUN = "5000"
PRIOR_NONCE = "re-nonce-1"


def _prior_judge_sidecar(runs: Path, **overrides) -> Path:
    """What a readapt whose paid judge failed after Adapt leaves committed (Codex, PR #29): the source directory's
    landed target sidecar plus that readapt's judge sidecar, written by `cli judge` (JudgeAborted) or the workflow's
    fallback `judge-spend-report`, named for its workflow run and carrying its fire's nonce and the log's eval id.
    The outputs themselves never commit (default success gating)."""
    report = {"run_utc": "2026-09-24T09:20:00Z", "judgments_file": "judgments.jsonl", "judge_model": "claude-haiku-4-5",
              "cost_usd": 2.5, "run_cost_usd": 2.5, "prior_cost_usd": 0.0, "rows_cost_usd": 0.81,
              "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar", "max_spend_usd": 2.5, "aborted": True,
              "run_id": STEM, "billing_channel": "anthropic", "journal_nonce": PRIOR_NONCE, "eval_id": EVAL_ID}
    report.update(overrides)
    path = runs / STEM / readapt.judge_report_name(STEM, PRIOR_RUN)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def _retry_journal() -> list[dict]:
    return _journal_entries() + _journal_entries(PRIOR_NONCE, fired_utc="2026-09-24T09:07:00Z", max_spend=2.5,
                                                 params_sha256="b" * 64)


def _retry_plan(runs: Path, **param_overrides) -> dict:
    return readapt.plan(params=_params(**param_overrides), listing=_listing(), runs_dir=runs, seed_ids=_wave2_ids(),
                        journal_entries=_retry_journal(), readapt_run_id="5555", readapt_run_attempt="1",
                        readapt_commit=COMMIT, now=NOW, seed_digests=_wave2_digests())


def test_a_readapt_whose_judge_failed_can_be_retried_beside_the_judge_sidecar_it_committed(tmp_path):
    """The failed readapt's judge sidecar is its spend record, already committed: a retry is admitted beside it
    and binds it by digest, and every way that sidecar could be anything else is refused by name."""
    runs = tmp_path / "runs"
    _landed_sidecar(runs)
    prior = _prior_judge_sidecar(runs)
    assert readapt.run_dir_problems(runs, STEM) == [], "the state a readapt whose judge failed leaves is re-adaptable"
    plan = _retry_plan(runs)
    assert plan["prior_judge_reports"] == [{"path": f"{STEM}/{prior.name}", "sha256": framework.sha256_file(prior),
                                            "journal_nonce": PRIOR_NONCE}]
    assert readapt.judge_report_name(STEM, "5555") == f"{STEM}.readapt_5555.judge.report.json" != prior.name
    for overrides, needle in (({"journal_nonce": SOURCE_NONCE}, "which is the source fire's or this readapt's"),
                              ({"journal_nonce": "re-nonce"}, "which is the source fire's or this readapt's"),
                              ({"journal_nonce": None}, "records no journal_nonce"),
                              ({"journal_nonce": "unknown"}, "0 petri-audit journal entries carry the nonce 'unknown'"),
                              ({"eval_id": "EvOther"}, "not the source log's")):
        _prior_judge_sidecar(runs, **overrides)
        with pytest.raises(readapt.ReadaptError, match=needle):
            _retry_plan(runs)
    prior.write_text("{not json", encoding="utf-8")
    with pytest.raises(readapt.ReadaptError, match="does not parse"):
        _retry_plan(runs)
    prior.unlink()
    # a sidecar under this workflow run's own name cannot predate its judge
    (runs / STEM / readapt.judge_report_name(STEM, "5555")).write_text("{}", encoding="utf-8")
    with pytest.raises(readapt.ReadaptError, match="is this readapt's own judge sidecar"):
        _retry_plan(runs)
    (runs / STEM / readapt.judge_report_name(STEM, "5555")).unlink()
    # the ordinary judge name is no readapt's and stays refused, as does anything else
    (runs / STEM / f"{STEM}.judge.report.json").write_text("{}", encoding="utf-8")
    assert any("files other than the landed target sidecar and earlier readapts' judge sidecars" in p
               for p in readapt.run_dir_problems(runs, STEM))


def test_the_retry_leaves_the_earlier_readapts_judge_sidecar_byte_identical(tmp_path, capsys):
    runs = tmp_path / "runs"
    _landed_sidecar(runs)
    prior = _prior_judge_sidecar(runs)
    before = prior.read_bytes()
    logs = tmp_path / "petri-run" / "logs"
    logs.mkdir(parents=True)
    (logs / EVAL_NAME).write_bytes(b"the raw log")
    plan = _retry_plan(runs)
    plan_path = tmp_path / "plan.json"
    framework.write_json(plan_path, plan)
    args = cli.build_parser().parse_args(_adapt_argv(runs, logs / EVAL_NAME, plan_path))
    assert cli.readapt_pre_problems(args, plan) == []
    assert readapt.kept_prior_problems(runs / STEM, plan["prior_judge_reports"]) == []
    prior.write_text(before.decode("utf-8").replace('"cost_usd": 2.5', '"cost_usd": 0.1'), encoding="utf-8")
    assert cli.main(_adapt_argv(runs, logs / EVAL_NAME, plan_path)) == 11
    assert "changed after the readapt bound it" in capsys.readouterr().err
    prior.unlink()
    assert any("is gone" in p for p in readapt.kept_prior_problems(runs / STEM, plan["prior_judge_reports"]))
    prior.write_bytes(before)
    stray = runs / STEM / readapt.judge_report_name(STEM, "6000")
    stray.write_bytes(before)
    assert any("appeared after the readapt was planned" in p
               for p in readapt.kept_prior_problems(runs / STEM, plan["prior_judge_reports"]))


def test_a_readapt_judge_names_its_sidecar_for_its_own_workflow_run(tmp_path, capsys):
    """Before this, a readapt's judge wrote `<stem>.judge.report.json`: a retry's judge would have rewritten the
    sidecar the failed readapt committed (a spend record another fire's reservation is booked against), and the
    fallback writer would have found it and imputed nothing for a retry judge that spent. Both writers now name
    the sidecar for the re-adapting workflow run, from the manifest's `readapt` block."""
    run_dir = tmp_path / "runs" / STEM
    run_dir.mkdir(parents=True)
    prior = run_dir / readapt.judge_report_name(STEM, PRIOR_RUN)
    prior.write_text('{"cost_usd": 2.5, "journal_nonce": "re-nonce-1"}\n', encoding="utf-8")
    before = prior.read_bytes()
    framework.write_json(run_dir / "manifest.json", {"eval_id": EVAL_ID, "readapt": {
        "readapt_journal_nonce": "re-nonce", "readapt_workflow_run_id": "5555", "source_run_stem": STEM}})
    assert cli._judge_report_path(run_dir) == run_dir / f"{STEM}.readapt_5555.judge.report.json"
    argv = ["judge-spend-report", "--run-dir", str(run_dir), "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "2.5"]
    assert cli.main(argv) == 0
    side = framework.load_json(run_dir / f"{STEM}.readapt_5555.judge.report.json")
    assert side["journal_nonce"] == "re-nonce" and side["eval_id"] == EVAL_ID and side["cost_usd"] == 2.5
    assert prior.read_bytes() == before and not (run_dir / f"{STEM}.judge.report.json").exists()
    assert cli.main(argv) == 0 and "exists; nothing to impute" in capsys.readouterr().out
    # an ordinary run keeps the ordinary name
    framework.write_json(run_dir / "manifest.json", {"eval_id": EVAL_ID})
    assert cli._judge_report_path(run_dir) == run_dir / f"{STEM}.judge.report.json"
    # a readapt block naming no usable workflow run: the judge refuses before any call; the fallback books the
    # ceiling under the ordinary name (no readapt writes it) and records why
    framework.write_json(run_dir / "manifest.json", {"eval_id": EVAL_ID, "readapt": {
        "readapt_journal_nonce": "re-nonce", "readapt_workflow_run_id": "x"}})
    with pytest.raises(ValueError, match="no usable readapt_workflow_run_id"):
        cli._judge_report_path(run_dir)
    assert cli.main(argv) == 0
    side = framework.load_json(run_dir / f"{STEM}.judge.report.json")
    assert side["journal_nonce"] == "re-nonce" and "readapt_run_id" in side["judge_report_name_unavailable"]
    capsys.readouterr()



# ------------------------------------------------------------ the seed content the source run executed


def test_the_seed_content_in_hand_must_be_what_the_source_runs_samples_recorded():
    """Codex, PR #29: the plan resolves the selection against the seed file in the checkout, and the adapter refused
    a sample whose recorded seed digest differed from it one sample at a time, writing whatever remained into the
    source run's directory as its measurement. The log's per-sample digests are now compared, per seed, with the
    seed in hand before anything is written, and any drift refuses by name."""
    digests = {"a": "1" * 64, "b": "2" * 64}
    expected = {"eval_id": EVAL_ID, "target": "anthropic/claude-haiku-4-5", "seed_ids": ["a", "b"], "epochs": 1,
                "token_limit": 40000, "log_model_api": True, "seed_sha256": digests}
    observed = dict(expected, status="success", seed_sha256={"a": ["1" * 64] * 3, "b": ["2" * 64] * 3})
    assert readapt.log_problems(expected, observed) == []
    cases = [({"a": ["1" * 64] * 3, "b": ["3" * 64] * 3}, "seed b: the source run executed seed content 333333333333, "
                                                        "and the seed file in hand holds 222222222222"),
             ({"a": ["1" * 64, "4" * 64], "b": ["2" * 64]}, "seed a: the log's samples record 2 different seed digests"),
             ({"a": ["1" * 64]}, "seed b: the log's samples record no usable seed digest (None)"),
             ({"a": [None], "b": ["2" * 64]}, "seed a: the log's samples record no usable seed digest ([None])"),
             (None, "the log records no per-sample seed digests")]
    for recorded, needle in cases:
        problems = readapt.log_problems(expected, dict(observed, seed_sha256=recorded))
        assert len(problems) == 1 and needle in problems[0], (recorded, problems)
    # the plan cannot be made without the digest of every selected seed
    for bad in (None, {"a": "1" * 64}, {"a": "1" * 64, "b": "short"}):
        with pytest.raises(readapt.ReadaptError, match="needs the digest of every selected seed"):
            readapt.expected_from_params(_params(), ["a", "b"], bad)


def test_a_readapt_plan_refuses_without_the_seed_digests(tmp_path):
    runs = tmp_path / "runs"
    _landed_sidecar(runs)
    with pytest.raises(readapt.ReadaptError, match="needs the digest of every selected seed"):
        readapt.plan(params=_params(), listing=_listing(), runs_dir=runs, seed_ids=_wave2_ids(),
                     journal_entries=_journal_entries(), readapt_run_id="5555", readapt_run_attempt="1",
                     readapt_commit=COMMIT, now=NOW)


def test_a_judge_sidecar_named_for_the_readapt_binds_and_verifies(tmp_path):
    """The readapt's judge sidecar name (`judge_report_name`) is what `cli judge` hands `bind_judgments`: the
    manifest must bind it, reseal, and pass verify-run and verify-chain, or the judge would spend and then fail to
    bind. A landed judged run, copied and re-adapted in place, is bound to a readapt-named copy of its sidecar."""
    source = _landed_manifests()[-1].parent
    runs = tmp_path / "runs"
    shutil.copytree(source, runs / source.name)
    run_dir = runs / source.name
    m = framework.load_json(run_dir / "manifest.json")
    bound = (m["artifacts"].get("judge_of_record") or {}).get("report_path")
    assert bound and (runs / bound).is_file(), "the last landed run is judged"
    sidecar = run_dir / f"{source.name}.report.json"
    m["readapt"] = {"source_workflow_run_id": source.name.split("_")[1], "source_run_stem": source.name,
                    "source_journal_nonce": "n", "source_params_sha256": PARAMS_SHA, "source_eval_log": EVAL_NAME,
                    "source_artifact": {"id": 1, "name": f"petri-audit-raw-eval-{source.name.split('_')[1]}-1",
                                        "digest": None, "size_in_bytes": None, "created_at": None, "expires_at": None},
                    "target_report": {"path": f"{source.name}/{sidecar.name}", "sha256": framework.sha256_file(sidecar)},
                    "readapt_workflow_run_id": "5555", "readapt_workflow_run_attempt": 1, "readapt_commit": COMMIT,
                    "readapt_journal_nonce": "r"}
    sealed = manifest_mod.seal_manifest(m, None)
    manifest_mod.write_manifest(run_dir / "manifest.json", sealed)
    (runs / manifest_mod.CHAIN_FILE).write_text(f"{source.name}/manifest.json {sealed['chain']['manifest_sha256']}\n",
                                                encoding="utf-8")
    renamed = run_dir / readapt.judge_report_name(source.name, "5555")
    assert cli._judge_report_path(run_dir) == renamed
    (runs / bound).rename(renamed)
    judge = dict(sealed["artifacts"]["judge_of_record"])
    for key in ("report_path", "report_sha256"):
        judge.pop(key)
    rebound = manifest_mod.bind_judgments(run_dir, judgments_path=run_dir / "judgments.jsonl", report_path=renamed,
                                          judge_of_record=judge)
    assert rebound["artifacts"]["judge_of_record"]["report_path"] == f"{source.name}/{renamed.name}"
    assert manifest_mod.verify_run(run_dir) == []
    ok, msg = manifest_mod.verify_chain(runs)
    assert ok, msg
