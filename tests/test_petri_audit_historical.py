"""The historical instrument of mode rejudge (scripts/petri_audit/historical.py; owner decision R2, 2026-10-14): a
landed run whose judge of record ran under a prompt file or a planner that has since changed is re-graded by
replaying that judge's own judgments, each prompt rebuilt from the prompt-file version its row records and held to
the judge of record's rows digest for digest. Synthetic source runs are landed through the lane's own writers
(tests/test_petri_audit_rejudge.py `_land`); one test reads the two landed runs R2 names, read-only, and skips when
they are absent. Nothing here calls a provider. Medical vocabulary stays in JSON (AGENTS.md): every prompt and reply
text comes from the repository's data files."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, framework, historical, judge_runner, rejudge, seeds  # noqa: E402


def _rejudge_tests():
    spec = importlib.util.spec_from_file_location("rejudge_test_helpers", ROOT / "tests" / "test_petri_audit_rejudge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _rejudge_tests()
STEM = "run_4242_1"
CHANGED_DIM = "safety_netting_presence"
GATED_DIM = "safety_netting_persistence"
R2_RUNS = ("run_35351739969_1", "run_35801345137_1")


@pytest.fixture(scope="module")
def seed_set() -> seeds.SeedSet:
    return seeds.load_seed_file()


def _prompt_ref(dim: str) -> str:
    outcomes = framework.load_json(framework.OUTCOME_REGISTRY)
    return next(d for d in outcomes["dimensions"] if d["id"] == dim)["detection"]["judge_prompt_ref"]


def _older_version(prompt: dict) -> dict:
    """A different version of a prompt file: the same declared values and placeholders, other instruction bytes."""
    old = json.loads(json.dumps(prompt))
    old["instructions"] = old["instructions"] + "\n"
    return old


def _archive(tmp_path: Path, ref: str, prompt: dict, commit: str = "d" * 40) -> Path:
    """A one-entry prompt archive holding `prompt`'s bytes, as historical.load_archive reads one."""
    folder = tmp_path / "archive"
    folder.mkdir(exist_ok=True)
    data = (json.dumps(prompt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    digest = historical.canonical_digest(prompt)
    name = f"{Path(ref).name}.{digest}.json"
    (folder / name).write_bytes(data)
    index = folder / "index.json"
    index.write_text(json.dumps({"entries": [{"prompt_ref": ref, "prompt_file_digest": digest, "file": name,
                                              "sha256": framework.sha256_bytes(data),
                                              "git_blob": historical.git_blob_id(data), "commit": commit}]}),
                     encoding="utf-8")
    return index


def _rehearsal_plan(runs: Path, root: Path, instrument: str) -> dict:
    """A $0 rehearsal plan (the mock judge) of the landed STEM under `instrument`."""
    return rejudge.make_plan(
        params=H._params(judge_model=rejudge.MOCK_JUDGE, commit_outputs="false", judge_max_spend="0.01", _nonce=""),
        runs_dir=runs, rejudge_root=root, journal_entries=[], workflow_run_id="777", workflow_run_attempt="1",
        commit=H.COMMIT, instrument=instrument)


@pytest.fixture
def changed_prompt_run(tmp_path, seed_set, monkeypatch):
    """A run whose judge of record judged CHANGED_DIM under an older version of its prompt file than the checkout's,
    and an archive holding that older version's bytes."""
    ref = _prompt_ref(CHANGED_DIM)
    current = framework.load_prompt(ref)
    old = _older_version(current)
    real = judge_runner.load_prompt
    with monkeypatch.context() as m:
        m.setattr(judge_runner, "load_prompt", lambda r: old if r == ref else real(r))
        runs = tmp_path / "data" / "petri" / "runs"
        H._land(runs, STEM, seed_set)
    return runs, tmp_path / "rejudge", ref, old, _archive(tmp_path, ref, old)


# ------------------------------------------------------------------ prompt versions


def test_the_git_blob_id_is_gits():
    assert historical.git_blob_id(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_the_committed_archive_verifies_and_is_the_git_blob_its_entry_names():
    archive = historical.load_archive()
    index = framework.load_json(historical.ARCHIVE_INDEX)
    assert len(archive) == len(index["entries"]) >= 1
    for e in index["entries"]:
        version = archive[(e["prompt_ref"], e["prompt_file_digest"])]
        assert version.source == "archive" and version.commit == e["commit"] and version.git_blob == e["git_blob"]
        # the checkout's file has moved on: an archived version is never the current one
        assert framework.prompt_digest(e["prompt_ref"]) != e["prompt_file_digest"]
        have = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{e['commit']}^{{commit}}"],
                              capture_output=True)
        if have.returncode != 0:
            pytest.skip(f"commit {e['commit'][:12]} is not in this clone's history (a shallow checkout)")
        blob = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{e['commit']}:{e['prompt_ref']}"],
                              capture_output=True, text=True, check=True).stdout.strip()
        assert blob == e["git_blob"]
        found = historical.recover_from_git(e["prompt_ref"], e["prompt_file_digest"])
        assert found is not None and found["git_blob"] == e["git_blob"] and found["sha256"] == e["sha256"]


def test_a_tampered_or_mislabelled_archive_is_refused(tmp_path):
    ref = _prompt_ref(CHANGED_DIM)
    old = _older_version(framework.load_prompt(ref))
    index = _archive(tmp_path, ref, old)
    assert historical.load_archive(index)[(ref, historical.canonical_digest(old))].prompt == old
    entry = json.loads(index.read_text(encoding="utf-8"))["entries"][0]
    path = index.parent / entry["file"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(rejudge.RejudgeError, match="does not digest to its recorded sha256.*git blob"):
        historical.load_archive(index)
    _archive(tmp_path, ref, old)
    doc = json.loads(index.read_text(encoding="utf-8"))
    doc["entries"][0]["prompt_file_digest"] = "0" * 12
    index.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(rejudge.RejudgeError, match="has canonical digest"):
        historical.load_archive(index)
    doc["entries"][0]["file"] = "../index.json"
    index.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(rejudge.RejudgeError, match="is not a file beside the index"):
        historical.load_archive(index)


# ------------------------------------------------------------------ the replay


def test_with_nothing_changed_the_replay_is_todays_plan(tmp_path, seed_set):
    runs = tmp_path / "runs"
    H._land(runs, STEM, seed_set)
    replayed, _, _ = historical.replay_plans(runs, STEM)
    planned, _, _ = rejudge.build_plans(runs, STEM)
    assert [vars(p) for p in replayed] == [vars(p) for p in planned]
    assert rejudge.plan_digest(replayed) == rejudge.plan_digest(planned)


def test_a_changed_prompt_file_is_refused_today_and_replayed_from_its_archived_version(changed_prompt_run,
                                                                                       monkeypatch):
    runs, root, ref, old, index = changed_prompt_run
    with pytest.raises(rejudge.RejudgeError, match="never made"):
        _rehearsal_plan(runs, root, "current")
    # the version the rows name is not the checkout's and not archived: refused by name, never guessed
    monkeypatch.setattr(historical, "ARCHIVE_INDEX", index.parent / "absent.json")
    with pytest.raises(rejudge.RejudgeError, match=f"{ref} at digest {historical.canonical_digest(old)}"):
        _rehearsal_plan(runs, root, "historical")
    monkeypatch.setattr(historical, "ARCHIVE_INDEX", index)
    plan = _rehearsal_plan(runs, root, "historical")
    assert plan["instrument"] == "historical"
    outcome = rejudge.execute(plan, started_dir=root.parent / "started")
    assert [r["status"] for r in outcome["results"]] == ["complete"]
    out_dir = root / "mockllm-judge" / STEM
    assert rejudge.verify_output(out_dir, runs) == []
    m = framework.load_json(out_dir / rejudge.MANIFEST_NAME)
    entry = m["instrument"]["prompt_files"][ref]
    assert entry["digest"] == historical.canonical_digest(old) and entry["source"] == "archive"
    assert entry["commit"] == "d" * 40 and entry["archive_file"].endswith(".json")
    others = [e for r, e in m["instrument"]["prompt_files"].items() if r != ref]
    assert others and all(e["source"] == "checkout" and e["commit"] == H.COMMIT for e in others)
    hist = m["instrument"]["historical"]
    assert hist["instrument"] == "historical" and hist["archived_prompt_files"] == [ref]
    assert hist["judgments_replayed"] == m["counts"]["planned"] == hist["calls"] + hist["not_applicable"]
    assert hist["archive_index"]["sha256"] == framework.sha256_file(index)
    # every prompt the new judge was shown is the one the judge of record was shown, digest for digest
    of_record = {rejudge._row_key(r): r for r in judge_runner.read_jsonl(runs / STEM / "judgments.jsonl")}
    regraded = judge_runner.read_jsonl(out_dir / rejudge.JUDGMENTS_NAME)
    assert len(regraded) == len(of_record)
    for r in regraded:
        jor = of_record[rejudge._row_key(r)]
        assert (r["rendered_sha256"], r["context_sha256"], r["not_applicable_reason"]) == \
            (jor["rendered_sha256"], jor["context_sha256"], jor["not_applicable_reason"])


def test_a_planner_change_is_refused_today_and_replayed_from_the_rows(tmp_path, seed_set, monkeypatch):
    """The wave-1 shape: the judge of record judged a gated dimension with a prior-reply context, and today's planner
    gates it out. The replay recovers the context by digest from the committed transcript."""
    runs, root = tmp_path / "runs", tmp_path / "rejudge"
    H._land(runs, STEM, seed_set)
    real = judge_runner._gate_problem
    monkeypatch.setattr(judge_runner, "_gate_problem", lambda dim, *a: "stricter gate" if dim == GATED_DIM
                        else real(dim, *a))
    with pytest.raises(rejudge.RejudgeError, match="differs from what the judge of record was given"):
        _rehearsal_plan(runs, root, "current")
    plan = _rehearsal_plan(runs, root, "historical")
    rows = judge_runner.read_jsonl(runs / STEM / "judgments.jsonl")
    plans, _, _ = historical.replay_plans(runs, STEM)
    gated = [p for p in plans if p.key == GATED_DIM]
    assert gated and all(p.prompt is not None and p.context_sha256 for p in gated)
    assert rejudge.parity_problems(plans, rows) == []
    assert plan["sources"][0]["plan_sha256"] == rejudge.plan_digest(plans)


def _replay(runs: Path, rows: list[dict]) -> list:
    manifest = framework.load_json(runs / STEM / "manifest.json")
    records = judge_runner.read_jsonl(runs / STEM / "transcripts.jsonl")
    return historical.replay_rows(rows, records, manifest, seeds.load_seed_file().seeds,
                                  rubric=judge_runner.load_rubric(), resolver=historical.PromptResolver())


def test_a_row_that_cannot_be_rebuilt_exactly_is_refused(tmp_path, seed_set):
    runs = tmp_path / "runs"
    H._land(runs, STEM, seed_set)
    rows = judge_runner.read_jsonl(runs / STEM / "judgments.jsonl")
    assert len(_replay(runs, rows)) == len(rows)
    ctx = next(i for i, r in enumerate(rows) if r["kind"] == "outcome" and r.get("context_sha256"))
    cases = [
        (ctx, {"context_sha256": "f" * 64}, "no context drawn from the committed transcript and seed digests"),
        (0, {"rendered_sha256": "f" * 64}, "the rebuilt prompt does not digest"),
        (0, {"rendered_sha256": None, "not_applicable_reason": None}, "neither a rendered prompt nor"),
        (0, {"assistant_turn_index": 99}, "records assistant_turn_index 99"),
        (0, {"prompt_file_digest": "0" * 12}, "no earlier rubric version is archived"),
    ]
    for i, change, needle in cases:
        edited = [dict(r) for r in rows]
        edited[i].update(change)
        with pytest.raises(rejudge.RejudgeError, match=needle):
            _replay(runs, edited)
    outcome = next(i for i, r in enumerate(rows) if r["kind"] == "outcome")
    edited = [dict(r) for r in rows]
    edited[outcome]["prompt_file_digest"] = "0" * 12
    with pytest.raises(rejudge.RejudgeError, match="is neither the checkout's version nor in"):
        _replay(runs, edited)
    with pytest.raises(rejudge.RejudgeError, match="its rows hold"):
        _replay(runs, rows[:-1])
    with pytest.raises(rejudge.RejudgeError, match="carry judge spec"):
        _replay(runs, rows + [{**rows[0], "judge_model": "another"}])


def test_an_unknown_instrument_is_refused_and_todays_plan_keeps_its_shape(tmp_path, seed_set):
    runs, root = tmp_path / "runs", tmp_path / "rejudge"
    H._land(runs, STEM, seed_set)
    with pytest.raises(rejudge.RejudgeError, match="must be one of"):
        _rehearsal_plan(runs, root, "older")
    plan = _rehearsal_plan(runs, root, "current")
    assert "instrument" not in plan
    rejudge.execute(plan, started_dir=root.parent / "started")
    m = framework.load_json(root / "mockllm-judge" / STEM / rejudge.MANIFEST_NAME)
    assert "historical" not in m["instrument"]
    assert all(set(e) == {"digest", "sha256"} for e in m["instrument"]["prompt_files"].values())
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["rejudge-rehearse", "--source-run", STEM, "--out-root", str(tmp_path),
                                       "--instrument", "older"])


def test_the_rehearsal_command_runs_the_historical_instrument(changed_prompt_run, monkeypatch, capsys):
    runs, root, ref, old, index = changed_prompt_run
    monkeypatch.setattr(historical, "ARCHIVE_INDEX", index)
    code = cli.main(["rejudge-rehearse", "--source-run", STEM, "--out-root", str(root), "--runs-dir", str(runs),
                     "--seeds", str(framework.SEED_FILE), "--instrument", "historical"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "historical instrument:" in out and f"{ref} @ {historical.canonical_digest(old)}: archive" in out
    assert "verify: clean" in out


# ------------------------------------------------------------------ the landed runs R2 names


@pytest.mark.parametrize("stem", R2_RUNS)
def test_the_runs_r2_names_replay_exactly(stem):
    runs = ROOT / "data" / "petri" / "runs"
    if not (runs / stem / "manifest.json").is_file():
        pytest.skip(f"{stem} is not in this checkout")
    plans, _, _ = historical.replay_plans(runs, stem, cli.recorded_seed_file(runs, stem))
    rows = judge_runner.read_jsonl(runs / stem / "judgments.jsonl")
    assert rejudge.parity_problems(plans, rows) == []
    assert len(plans) == framework.load_json(runs / stem / "manifest.json")["artifacts"]["judge_of_record"]["planned"]
    # today's planner does not reproduce them, which is why the historical instrument exists
    todays, _, _ = rejudge.build_plans(runs, stem, cli.recorded_seed_file(runs, stem))
    assert rejudge.parity_problems(todays, rows) != []
