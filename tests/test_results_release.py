"""The release check and the publication record (scripts/results_snapshot.py ``check-release``).

A publish changes two repositories. The site push is the publication, so the version record has to exist and
be checked before anything is pushed. These tests build both repositories, and a bare remote for each, in a
temporary directory and pin:

* each refusal of the check before the pushes (uncommitted engine inputs, an uncommitted snapshot, a snapshot
  that is not current or does not verify, a recorded engine commit that is not in the engine HEAD, uncommitted
  site data, recorded bytes that differ at the site's HEAD commit);
* the coverage rule: a changed published statistics file the snapshot does not record, and a changed data
  file that nobody classified, are refused; a catalogue-only publish passes without a new snapshot;
* the published-measurement rule: ``create`` refuses, and the check before the pushes refuses, a gallery
  payload that changes or removes a published measurement or flips a capability label without the owner's
  committed disposition (scripts/payload_dispositions.py); new rows, models and batches pass;
* what a superseding snapshot records about the change, read from the two site commits;
* the difference between a snapshot that was created and one that was published, without editing the
  snapshot file;
* the recovery cases: the engine push lands and the site push does not, the site commit is rebased, another
  publish changes a recorded file, and a superseded snapshot's site commit is gone.

All file contents are abstract placeholders, never study stimuli or study numbers.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import payload_dispositions as pd  # noqa: E402
import results_policy as rp  # noqa: E402
import results_snapshot as snap  # noqa: E402
import tierb_split  # noqa: E402

BATCH = "pairs_20200101T000000Z"
# The seal cannot be evaluated over a batch with no holdout phrase, so the middle placeholder is one that hashes
# into the holdout. No test reads it back.
_SEALED = next(f"alpha prompt {i}" for i in range(1, 500) if tierb_split.is_holdout(f"alpha prompt {i}"))
_OPEN = [f"alpha prompt {i}" for i in range(1, 500) if not tierb_split.is_holdout(f"alpha prompt {i}")][:2]
PROMPTS = [_OPEN[0], _SEALED, _OPEN[1]]
PAYLOAD = "data/simulated_scenarios.json"
SKILL = ROOT / ".claude" / "skills" / "publish-site-data" / "SKILL.md"


def _git(root: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *argv],
                          check=check, capture_output=True, text=True)


def _head(root: Path, ref: str = "HEAD") -> str:
    return _git(root, "rev-parse", ref).stdout.strip()


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _head(root)


def _result(index: int, penalty: float = -0.3) -> dict:
    return {"index": index, "prompts": {"clinical": PROMPTS[index - 1], "patient": f"beta wording {index}"},
            "probabilities": {"clinical": 0.6, "patient": 0.6 + penalty}, "language_penalty": penalty,
            "target_token": 'Output " alpha"'}


def _summary(results: list[dict], graph_model: str, backend: str) -> dict:
    return {"graph_model": graph_model, "backend": backend, "source_set": None, "completed": True,
            "pairs_requested": len(results), "results": results}


def _payload(n_phrases: int, mean: float) -> dict:
    return {"batches": [BATCH], "scenarios": [{"batch": BATCH, "batch_index": 1}],
            "summary": {"model": "gemma-2-2b",
                        "penalty": {"population": "public_payload", "n_phrases": n_phrases,
                                    "mean_phrase_deduped": mean}}}


def _with_remote(root: Path, bare: Path) -> None:
    _git(bare.parent, "init", "-q", "--bare", "-b", "main", bare.name)
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-q", "-u", "origin", "main")


@pytest.fixture
def repos(tmp_path):
    """An engine and a site, each a git repository on ``main`` with a bare remote that holds its first commit."""
    engine, site = tmp_path / "engine", tmp_path / "site"
    _write(engine / "ops" / "dashboard.json", {"tierb": {"start_utc": "2019-12-31T00:00:00Z"}})
    _write(engine / "data" / "simulated" / f"{BATCH}.json", [{"top_prompt": p} for p in PROMPTS])
    _write(engine / "data" / "urgency_tiers.draft.json", {"tiers": ["a"]})
    _write(engine / "trace_out" / BATCH / "batch_summary.part_01.json",
           _summary([_result(1), _result(2)], "gemma-2-2b", "hosted"))
    pinned = engine / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_01.json"
    _write(pinned, _summary([_result(1), _result(3)], "qwen3-4b", "logits"))
    _write(engine / rp.RELEASE_MANIFEST, {"schema": rp.MANIFEST_SCHEMA, "parts": {
        pinned.relative_to(engine).as_posix(): hashlib.sha256(pinned.read_bytes()).hexdigest()}})
    _write(site / PAYLOAD, _payload(10, -0.05))
    _write(site / "data" / "urgency_shift.json", {"rows": [], "summary": {"n": 2}})
    _write(site / "data" / "model_stats.json", {"seed": 7, "boot": 10, "per_model": {}})
    _write(site / "data" / "drift_series.json", {"series": [1]})
    _write(site / "data" / "results_catalogue" / "index.json", {"runs": []})
    for root in (engine, site):
        _git(root, "init", "-q", "-b", "main")
        _commit_all(root, "base")
        _with_remote(root, tmp_path / f"{root.name}-remote.git")
    return engine, site


def _seal(engine: Path) -> dict:
    return {"dashboard_path": engine / "ops" / "dashboard.json", "simulated_dir": engine / "data" / "simulated"}


def _snapshot(engine: Path, site: Path, snapshot_id: str, supersedes: str | None = None, commit: bool = True) -> dict:
    path = snap.create(engine, snapshot_id, rp.STUDY_INTERIM, f"{snapshot_id}: test release", site=site,
                       supersedes=supersedes, seal_paths=_seal(engine))
    if commit:
        _commit_all(engine, f"snapshot {snapshot_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _published(engine: Path, site: Path, snapshot_id: str = "study-interim-20200101") -> dict:
    """A first snapshot of the committed site, pushed with it and recorded as published."""
    doc = _snapshot(engine, site, snapshot_id)
    _git(engine, "push", "-q", "origin", "main")
    _git(site, "push", "-q", "origin", "main")
    report = snap.check_published(engine, site, snapshot_id)
    assert report["ok"], report["problems"]
    assert snap.record_publication(engine, report, recorded_utc="2020-01-01T00:00:00Z") is True
    _commit_all(engine, f"publication record for {snapshot_id}")
    _git(engine, "push", "-q", "origin", "main")
    return doc


def _republish_payload(site: Path, n_phrases: int = 9, mean: float = -0.04) -> str:
    _write(site / PAYLOAD, _payload(n_phrases, mean))
    return _commit_all(site, "re-export")


def _other_publish(tmp_path: Path, site: Path, rel: str, obj) -> None:
    """Another session pushes a change of ``rel`` to the site's remote."""
    other = tmp_path / "other-site"
    if not other.exists():
        _git(tmp_path, "clone", "-q", _git(site, "remote", "get-url", "origin").stdout.strip(), other.name)
    else:
        _git(other, "pull", "-q", "origin", "main")
    _write(other / rel, obj)
    _commit_all(other, f"another publish of {rel}")
    _git(other, "push", "-q", "origin", "main")


def _problems(report: dict) -> str:
    return "\n".join(report["problems"])


# ---------------------------------------------------------------- the check before the pushes

def test_a_committed_current_snapshot_of_the_committed_site_passes_and_the_manifest_names_what_is_released(
        repos, capsys):
    engine, site = repos
    _published(engine, site)
    site_commit = _republish_payload(site)
    doc = _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    report = snap.check_release(engine, site)                       # default: the current snapshot
    assert report["ok"] is True and report["problems"] == []
    assert report["snapshot"]["id"] == "study-interim-20200102" and report["snapshot"]["current"] is True
    assert report["engine"]["commit"] == _head(engine) and report["site"]["commit"] == site_commit
    assert report["site"]["base_commit"] == _head(site, "origin/main") != site_commit
    assert {o["path"]: o["sha256"] for o in report["outputs"]} == doc["outputs"]["files"]
    assert set(doc["outputs"]["files"]) == set(snap.STATISTICS_FILES)        # create records the whole set
    assert report["changed"]["statistics"] == [PAYLOAD] and report["snapshot_required"] is True
    assert report["publications"] == []                             # checked, not yet published
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site), "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True and printed["site"]["commit"] == site_commit
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site)]) == 0
    out = capsys.readouterr().out
    assert f"{doc['outputs']['files'][PAYLOAD]}  {PAYLOAD}" in out and "release check passed" in out
    assert _head(site, "origin/main") != site_commit                # the check pushed nothing


def test_a_changed_statistics_file_without_a_new_snapshot_is_refused(repos, capsys):
    """The case the check exists for: the payload's summary changes and no other statistics file does."""
    engine, site = repos
    _published(engine, site)
    _republish_payload(site)
    report = snap.check_release(engine, site)
    assert report["ok"] is False and report["changed"]["statistics"] == [PAYLOAD]
    assert f"{PAYLOAD} at the site HEAD has sha256" in _problems(report)
    assert "create a superseding one" in _problems(report)
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site)]) == 1
    assert "push nothing" in capsys.readouterr().out


def test_coverage_refuses_a_changed_payload_that_the_snapshot_does_not_record(repos, monkeypatch):
    """A snapshot created with a narrower set (as every snapshot before 2026-11-10 was, for other files)
    cannot cover a release that changes a statistics file outside what it recorded."""
    engine, site = repos
    monkeypatch.setattr(snap, "SITE_OUTPUTS", ("data/urgency_shift.json", "data/model_stats.json"))
    doc = _snapshot(engine, site, "study-interim-20200101")
    monkeypatch.undo()
    assert PAYLOAD not in doc["outputs"]["files"]
    _republish_payload(site)
    report = snap.check_release(engine, site)
    assert report["ok"] is False
    assert (f"{PAYLOAD} is a published statistics file this release changes, and snapshot "
            "study-interim-20200101 does not record it") in _problems(report)
    assert "has sha256" not in _problems(report)                    # nothing recorded changed: coverage alone refuses


def test_a_changed_data_file_that_is_not_classified_is_refused(repos):
    engine, site = repos
    _snapshot(engine, site, "study-interim-20200101")
    _write(site / "data" / "new_metric.json", {"mean": 1})
    _write(site / "data" / "new_family" / "rows.json", {"rows": []})
    _write(site / "data" / "notes.sample.json", {"sample": True})            # a fixture: classified, passes
    _commit_all(site, "new files")
    report = snap.check_release(engine, site)
    assert report["changed"]["unclassified"] == ["data/new_family/rows.json", "data/new_metric.json"]
    assert "data/new_metric.json is changed by this release and is not classified" in _problems(report)
    assert "data/new_family/rows.json is changed by this release and is not classified" in _problems(report)
    assert [c["path"] for c in report["changed"]["outside_snapshot"]] == ["data/notes.sample.json"]
    assert len(report["problems"]) == 2


def test_a_catalogue_only_publish_passes_without_a_new_snapshot(repos):
    engine, site = repos
    _published(engine, site)
    _write(site / "data" / "results_catalogue" / "index.json", {"runs": [{"run_dir": "x"}]})
    _write(site / "data" / "results_catalogue" / "rows" / "x.json", {"parts": []})
    _commit_all(site, "catalogue")
    part = engine / "trace_out" / BATCH / "batch_summary.part_01.json"        # step 6b's engine-side output
    rp.record_parts(engine, {part.relative_to(engine).as_posix(): hashlib.sha256(part.read_bytes()).hexdigest()},
                    recorded_utc="2020-01-01T00:00:00Z", recorded_at_commit=None)
    _commit_all(engine, "ledger")
    report = snap.check_release(engine, site)
    assert report["ok"] is True, report["problems"]
    assert report["snapshot"]["id"] == "study-interim-20200101" and report["snapshot_required"] is False
    assert report["changed"]["statistics"] == [] and report["changed"]["unclassified"] == []
    assert sorted(c["path"] for c in report["changed"]["outside_snapshot"]) == [
        "data/results_catalogue/index.json", "data/results_catalogue/rows/x.json"]
    assert "evolving public record" in report["changed"]["outside_snapshot"][0]["reason"]
    differences = report["payload_differences"]                     # the payload did not change: nothing to dispose
    assert differences["compared"] is True and differences["differences"] == 0 and differences["refused"] == []


# ---------------------------------------------------------------- published measurements and capability labels

def _measured(p_clinical: float = 0.4, p_patient: float = 0.2) -> dict:
    """One model object with the thirteen measured fields; tokens are placeholders."""
    return {"prob_clinical": p_clinical, "prob_patient": p_patient,
            "language_penalty": round(p_patient - p_clinical, 4), "anchor_fallback": False,
            "top_clinical": ["zqalpha", p_clinical], "top_patient": ["zqbeta", 0.3],
            "spread_clinical": [["zqalpha", p_clinical]], "spread_patient": [["zqbeta", 0.3]],
            "target_token": "zqalpha", "flipped": True, "screening": None, "circuit_diff": None,
            "clinical_mass": None}


def _gallery(rows: dict[int, dict], n_phrases: int = 10, graphs: bool = False, batch: str = BATCH) -> dict:
    return {"batches": [batch],
            "scenarios": [{"index": i, "batch": batch, "batch_index": i, "models": models}
                          for i, models in sorted(rows.items())],
            "models_meta": [{"id": "gemma-2-2b", "graphs": True, "n_traced": len(rows)},
                            {"id": "qwen3-4b", "graphs": graphs, "n_traced": len(rows)}],
            "traced_by_model": {"qwen3-4b": {"backend": "hosted" if graphs else "logits"}},
            "summary": {"model": "gemma-2-2b",
                        "penalty": {"population": "public_payload", "n_phrases": n_phrases,
                                    "mean_phrase_deduped": -0.05}}}


def _both(qwen_clinical: float = 0.5) -> dict[int, dict]:
    return {1: {"gemma-2-2b": _measured(), "qwen3-4b": _measured(qwen_clinical, 0.1)},
            2: {"gemma-2-2b": _measured(0.3, 0.3), "qwen3-4b": _measured(0.6, 0.2)}}


def _publish_gallery(engine: Path, site: Path) -> dict:
    """The site's HEAD and remote hold a gallery payload with measured rows, recorded by a published snapshot."""
    _write(site / PAYLOAD, _gallery(_both()))
    _commit_all(site, "gallery")
    return _published(engine, site)


def _record(engine: Path, entries: list[dict], commit: bool = True) -> None:
    _write(engine / pd.RECORD_REL, {"schema": pd.SCHEMA, "entries": entries})
    if commit:
        _commit_all(engine, "disposition record")


def _accept(difference: dict, **over) -> dict:
    return {**pd.pending_entry(difference), "disposition": "accept_candidate", "decided_by": "owner",
            "decision_ref": "docs/decision.md#row-1", **over}


def test_a_changed_published_measurement_is_refused_by_create_and_by_the_release_check(repos, capsys):
    """A snapshot would record the changed payload as a new sha256. Neither it nor the pushes go ahead until
    the owner's disposition for exactly this change is committed in the engine."""
    engine, site = repos
    _publish_gallery(engine, site)
    before, after = _gallery(_both()), _gallery(_both(qwen_clinical=0.55), n_phrases=9)
    _write(site / PAYLOAD, after)
    _commit_all(site, "re-export with a changed row")
    [difference] = pd.scientific_differences(before, after)
    identity = f"({BATCH}, 1, qwen3-4b) values_changed: prob_clinical 0.5 -> 0.55"

    def refused(status: str) -> None:
        with pytest.raises(snap.SnapshotError, match="without an accepting owner disposition") as err:
            _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
        assert identity in str(err.value) and f"[{status}:" in str(err.value)
        assert snap.unindexed_files(engine) == []                   # nothing was written
        assert snap.load_index(engine)["current"] == {rp.STUDY_INTERIM: "study-interim-20200101"}
        report = snap.check_release(engine, site)
        assert report["ok"] is False and report["payload_differences"]["differences"] == 1
        [line] = [p for p in report["problems"] if "published measurement or capability label" in p]
        assert identity in line and f"[{status}:" in line and "zq" not in line

    refused("no_disposition")
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site)]) == 1
    out = capsys.readouterr().out
    assert "REFUSED: the release changes a published measurement or capability label" in out and identity in out
    _record(engine, [pd.pending_entry(difference)])
    refused("pending")
    _record(engine, [_accept(difference)])
    refused("invalid_entry")                                         # docs/decision.md is not a committed file
    _write(engine / "docs" / "decision.md", "the owner accepts the re-measured row 1")
    wrong = _accept(difference)
    wrong["candidate"] = {**wrong["candidate"], "values": {**wrong["candidate"]["values"], "prob_clinical": 0.56}}
    _record(engine, [wrong])
    refused("values_do_not_match")
    _record(engine, [pd.pending_entry(difference)])
    _record(engine, [_accept(difference)], commit=False)             # edited, not committed: HEAD still says pending
    refused("pending")
    _commit_all(engine, "the owner's disposition")
    doc = _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    recorded = doc["outputs"]["changed_since_superseded"]["payload_measurement_differences"]
    assert recorded["differences"] == 1 and recorded["record"] == pd.RECORD_REL
    assert identity in recorded["accepted_by_owner_disposition"][0]
    report = snap.check_release(engine, site)
    assert report["ok"] is True, report["problems"]
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site)]) == 0
    out = capsys.readouterr().out
    assert "this release changes: 1 (1 accepted by an owner disposition" in out and f"accepted: {identity}" in out


def test_a_removed_model_a_removed_row_and_a_capability_label_flip_are_refused(repos):
    engine, site = repos
    _publish_gallery(engine, site)
    rows = _both()
    del rows[1]["qwen3-4b"]                                          # the model leaves row 1
    del rows[2]                                                      # row 2 leaves the payload
    _write(site / PAYLOAD, _gallery(rows, graphs=True))              # and qwen3-4b is now labelled as having graphs
    _commit_all(site, "re-export")
    with pytest.raises(snap.SnapshotError, match="changes 5 published measurement"):
        _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    problems = _problems(snap.check_release(engine, site))
    for expected in (f"({BATCH}, 1, qwen3-4b) model_removed", f"({BATCH}, 2, gemma-2-2b) row_removed",
                     f"({BATCH}, 2, qwen3-4b) row_removed", "models_meta.qwen3-4b.graphs: false -> true",
                     "traced_by_model.qwen3-4b.backend: logits -> hosted"):
        assert expected in problems, expected
    # a payload that is gone is every measurement gone
    _git(site, "rm", "-q", PAYLOAD)
    _commit_all(site, "payload removed")
    assert "every published measurement would be removed" in _problems(snap.check_release(engine, site))


def test_new_rows_a_new_model_a_new_batch_and_a_restamped_summary_need_no_disposition(repos):
    engine, site = repos
    _publish_gallery(engine, site)
    rows = _both()
    rows[1]["olmo-2-1b"] = _measured(0.7, 0.6)                       # a new model on a published row
    rows[3] = {"gemma-2-2b": _measured(0.2, 0.1)}                    # a new row
    after = _gallery(rows, n_phrases=7)                              # the summary block restamped
    after["scenarios"].append({"index": 9, "batch": "pairs_20200102T000000Z", "batch_index": 1,
                               "models": {"gemma-2-2b": _measured()}})          # a new batch
    after["scenarios"][0]["index"] = 5                               # display order
    after["scenarios"][0]["models"]["gemma-2-2b"]["urgency"] = {"flip_class": "downgrade"}   # a later step's join
    after["models_meta"].append({"id": "olmo-2-1b", "graphs": True, "n_traced": 1})
    _write(site / PAYLOAD, after)
    _commit_all(site, "re-export with additions")
    doc = _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    recorded = doc["outputs"]["changed_since_superseded"]["payload_measurement_differences"]
    assert recorded["differences"] == 0 and recorded["accepted_by_owner_disposition"] == []
    report = snap.check_release(engine, site)
    assert report["ok"] is True, report["problems"]
    assert report["payload_differences"]["differences"] == 0 and report["changed"]["statistics"] == [PAYLOAD]


def test_an_unreadable_payload_or_record_is_a_refusal_not_a_pass(repos):
    engine, site = repos
    _publish_gallery(engine, site)
    (site / PAYLOAD).write_text("{truncated", encoding="utf-8")
    _commit_all(site, "a truncated payload")
    assert "cannot be compared with what was published" in _problems(snap.check_release(engine, site))
    _write(site / PAYLOAD, _gallery(_both(qwen_clinical=0.55)))
    _commit_all(site, "re-export")
    (engine / pd.RECORD_REL).parent.mkdir(parents=True, exist_ok=True)
    (engine / pd.RECORD_REL).write_text("{not a record", encoding="utf-8")
    _commit_all(engine, "a damaged record")
    problems = _problems(snap.check_release(engine, site))
    assert "cannot be compared with what was published" in problems and "is not JSON" in problems


def test_uncommitted_engine_inputs_and_an_uncommitted_snapshot_are_refused(repos):
    engine, site = repos
    _snapshot(engine, site, "study-interim-20200101", commit=False)
    report = snap.check_release(engine, site)
    assert "commit the snapshot file and the index" in _problems(report) and report["ok"] is False
    assert "does not hold data/analysis_snapshots/study-interim-20200101.json" in _problems(report)
    _commit_all(engine, "snapshot")
    assert snap.check_release(engine, site)["ok"] is True
    _write(engine / "trace_out" / "repeatability_r9" / "batch_summary.part_01.json",
           _summary([_result(1)], "gemma-2-2b", "hosted"))                   # an untracked hosted part
    report = snap.check_release(engine, site)
    assert "the engine tree differs from HEAD under the snapshot's inputs" in _problems(report)
    assert "repeatability_r9" in _problems(report)


def test_a_superseded_snapshot_a_stale_one_and_a_preview_are_refused(repos):
    engine, site = repos
    _snapshot(engine, site, "study-interim-20200101")
    _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    report = snap.check_release(engine, site, "study-interim-20200101")
    assert "is not the current snapshot of study-interim/1 ('study-interim-20200102' is)" in _problems(report)
    assert snap.check_release(engine, site, "study-interim-20200102")["ok"] is True
    _write(engine / "data" / "urgency_tiers.draft.json", {"tiers": ["a", "b"]})   # a recorded input changes
    _commit_all(engine, "tiers")
    report = snap.check_release(engine, site)
    assert "does not verify" in _problems(report) and "data/urgency_tiers.draft.json" in _problems(report)
    _write(engine / "trace_out" / "repeatability_r9" / "batch_summary.part_01.json",
           _summary([_result(1)], "gemma-2-2b", "hosted"))
    snap.create(engine, "study-interim-preview", rp.STUDY_INTERIM, "preview", site=site, allow_dirty=True,
                seal_paths=_seal(engine))
    _commit_all(engine, "preview")
    report = snap.check_release(engine, site, "study-interim-preview")
    assert "is a preview of uncommitted bytes" in _problems(report)


def test_a_recorded_engine_commit_that_a_rebase_replaced_is_refused(repos):
    engine, site = repos
    doc = _snapshot(engine, site, "study-interim-20200101")
    assert snap.check_release(engine, site)["ok"] is True
    _git(engine, "checkout", "-q", "--orphan", "rewritten")          # the same tree on a history without it
    _commit_all(engine, "rewritten history")
    report = snap.check_release(engine, site)
    assert report["ok"] is False and len(report["problems"]) == 1
    assert (f"the engine commit the snapshot records ({doc['engine_commit'][:12]}) is not an ancestor of the "
            "engine HEAD") in _problems(report)
    assert "git pull --no-rebase" in _problems(report)


def test_uncommitted_site_data_is_refused_and_the_recorded_bytes_are_read_from_the_commit(repos):
    engine, site = repos
    doc = _snapshot(engine, site, "study-interim-20200101")
    recorded_bytes = (site / PAYLOAD).read_bytes()
    _republish_payload(site)                                         # HEAD now holds other bytes
    (site / PAYLOAD).write_bytes(recorded_bytes)                     # the working tree shows the recorded ones
    assert hashlib.sha256((site / PAYLOAD).read_bytes()).hexdigest() == doc["outputs"]["files"][PAYLOAD]
    report = snap.check_release(engine, site)
    assert "the site has uncommitted changes under data or modes/simulated" in _problems(report)
    assert f"{PAYLOAD} at the site HEAD has sha256" in _problems(report)        # judged by the commit
    _git(site, "checkout", "-q", "--", PAYLOAD)
    (site / "modes" / "simulated" / BATCH).mkdir(parents=True)
    (site / "modes" / "simulated" / BATCH / "index_01.html").write_text("<p>render</p>", encoding="utf-8")
    assert "?? modes/simulated/" in _problems(snap.check_release(engine, site))  # an unstaged render


def test_a_missing_base_ref_and_a_snapshot_without_site_files_are_refused(repos):
    engine, site = repos
    snap.create(engine, "study-interim-20200101", rp.STUDY_INTERIM, "no site", seal_paths=_seal(engine))
    _commit_all(engine, "snapshot")
    report = snap.check_release(engine, site, site_base="origin/gone")
    assert "the site has no commit at the base ref 'origin/gone'" in _problems(report)
    assert "records no published files (it was created without --site)" in _problems(report)
    with pytest.raises(snap.SnapshotError, match="no snapshot 'nope'"):
        snap.check_release(engine, site, "nope")
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site), "--id", "nope"]) == 2
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site), "--record"]) == 2


# ---------------------------------------------------------------- what a superseding snapshot records

def test_a_superseding_snapshot_records_the_payload_summary_at_both_site_commits(repos):
    engine, site = repos
    first = _published(engine, site)
    assert first["outputs"]["changed_since_superseded"] == {"compared_with": None,
                                                            "reason": "no superseded snapshot"}
    before_commit = _head(site)
    after_commit = _republish_payload(site, n_phrases=9, mean=-0.04)
    (site / "README.txt").write_text("the working tree is not what is read", encoding="utf-8")
    doc = _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    change = doc["outputs"]["changed_since_superseded"]
    assert change["compared_with"] == "study-interim-20200101" and change["snapshots_passed_over"] == []
    assert (change["site_commit_before"], change["site_commit_after"]) == (before_commit, after_commit)
    assert list(change["files"]) == [PAYLOAD]
    assert change["files"][PAYLOAD] == {"sha256_before": first["outputs"]["files"][PAYLOAD],
                                        "sha256_after": doc["outputs"]["files"][PAYLOAD],
                                        "changed_top_level_keys": ["summary"]}
    penalty = change["payload_summary_penalty"]
    assert penalty["pointer"] == "/summary/penalty" and penalty["changed"] is True
    assert penalty["before"] == {"population": "public_payload", "n_phrases": 10, "mean_phrase_deduped": -0.05}
    assert penalty["after"] == {"population": "public_payload", "n_phrases": 9, "mean_phrase_deduped": -0.04}
    assert doc["outputs"]["statistics_set"]["files"][PAYLOAD] == snap.MEMBERSHIP_INPUTS
    assert snap.verify(engine, "study-interim-20200101")["ok"] is True          # the earlier one is untouched


def test_a_change_record_names_the_files_the_compared_snapshot_did_not_record(repos, monkeypatch):
    engine, site = repos
    monkeypatch.setattr(snap, "SITE_OUTPUTS", ("data/urgency_shift.json",))
    _snapshot(engine, site, "study-interim-20200101")
    monkeypatch.undo()
    _republish_payload(site)
    doc = _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    change = doc["outputs"]["changed_since_superseded"]
    assert PAYLOAD in change["not_recorded_by_compared_snapshot"]
    assert "data/urgency_shift.json" not in change["not_recorded_by_compared_snapshot"]
    assert list(change["files"]) == [PAYLOAD]                        # compared from git all the same
    assert snap.check_release(engine, site)["ok"] is True


# ---------------------------------------------------------------- created is not published

def test_a_created_snapshot_is_distinguishable_from_a_published_one_without_editing_it(repos, capsys):
    engine, site = repos
    _published(engine, site)
    _republish_payload(site)
    _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    snapshot_file = engine / snap.SNAPSHOT_DIR / "study-interim-20200102.json"
    before = snapshot_file.read_bytes()
    assert snap.publication_records(engine, "study-interim-20200102") == []
    assert snap.main(["--engine", str(engine), "list"]) == 0
    listing = capsys.readouterr().out
    assert "study-interim-20200102 (current) (no publication recorded)" in listing
    assert "study-interim-20200101 (published: site " in listing
    # the engine push lands; the site push does not
    _git(engine, "push", "-q", "origin", "main")
    report = snap.check_published(engine, site)
    assert report["ok"] is False and report["mismatched"] == [PAYLOAD]
    assert all(PAYLOAD in p for p in report["problems"])             # the engine side is in place
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site), "--published",
                      "--record"]) == 1
    assert "NOT PUBLISHED AS RECORDED" in capsys.readouterr().out
    assert snap.publication_records(engine, "study-interim-20200102") == []     # a failed check records nothing
    with pytest.raises(snap.SnapshotError, match="only a passing"):
        snap.record_publication(engine, report)
    # the site push, then the check and the record
    _git(site, "push", "-q", "origin", "main")
    assert snap.main(["--engine", str(engine), "check-release", "--site", str(site), "--published",
                      "--record"]) == 0
    assert "published: the remote site branch holds the recorded bytes" in capsys.readouterr().out
    records = snap.publication_records(engine, "study-interim-20200102")
    assert [r["site_commit"] for r in records] == [_head(site, "origin/main")]
    assert records[0]["site_ref"] == "origin/main" and records[0]["engine_commit"] == _head(engine, "origin/main")
    assert snapshot_file.read_bytes() == before                      # the snapshot file was not edited
    assert snap.verify(engine, "study-interim-20200102")["ok"] is True
    assert snap.record_publication(engine, snap.check_published(engine, site)) is False   # recorded once
    assert len(snap.load_index(engine)["publications"]) == 2
    # the record is an index change like any other: it is committed before the next release check passes
    assert "commit the snapshot file and the index" in _problems(snap.check_release(engine, site))
    _commit_all(engine, "publication record")
    assert snap.check_release(engine, site)["ok"] is True


def test_a_site_published_before_the_engine_holds_the_snapshot_is_not_reported_published(repos):
    engine, site = repos
    _snapshot(engine, site, "study-interim-20200101")
    _git(site, "push", "-q", "origin", "main")                       # the wrong order
    report = snap.check_published(engine, site)
    assert report["ok"] is False and report["mismatched"] == []
    assert "the snapshot commit has not been pushed there" in _problems(report)
    assert "the commit the snapshot was created at has not been pushed there" not in _problems(report)
    _git(engine, "push", "-q", "origin", "main")
    assert snap.check_published(engine, site)["ok"] is True


def test_an_earlier_publication_can_be_checked_at_its_commit_of_the_published_branch(repos):
    engine, site = repos
    _snapshot(engine, site, "study-interim-20200101")
    _git(engine, "push", "-q", "origin", "main")
    first_commit = _head(site)
    _republish_payload(site)
    _git(site, "push", "-q", "origin", "main")                       # a later publish replaced the bytes
    assert snap.check_published(engine, site, "study-interim-20200101")["ok"] is False
    report = snap.check_published(engine, site, "study-interim-20200101", at=first_commit)
    assert report["ok"] is True and report["site"]["commit"] == first_commit
    _git(site, "checkout", "-q", "--orphan", "elsewhere")
    stray = _commit_all(site, "not on the published branch")
    report = snap.check_published(engine, site, "study-interim-20200101", at=stray)
    assert "a publication is a commit of the published branch" in _problems(report)


# ---------------------------------------------------------------- recovery

def test_a_rebased_site_commit_is_bound_by_the_recorded_hashes_not_by_its_id(repos, tmp_path):
    engine, site = repos
    _published(engine, site)
    recorded_commit = _republish_payload(site)
    doc = _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    assert doc["outputs"]["site_commit"] == recorded_commit
    _other_publish(tmp_path, site, "data/drift_series.json", {"series": [1, 2]})   # the remote moves
    assert _git(site, "push", "origin", "main", check=False).returncode != 0       # rejected
    _git(site, "fetch", "-q", "origin")
    report = snap.check_release(engine, site)
    assert report["ok"] is True                                      # the base changed no statistics file
    assert report["changed"]["on_base_since_merge_base"] == ["data/drift_series.json"]
    assert any("a direct push needs the base brought in first" in n for n in report["notes"])
    _git(site, "pull", "-q", "--rebase", "origin", "main")
    assert _head(site) != recorded_commit                            # the commit id changed
    report = snap.check_release(engine, site)
    assert report["ok"] is True
    assert any("is not the commit the snapshot recorded" in n and "bind the release" in n for n in report["notes"])
    _git(engine, "push", "-q", "origin", "main")
    _git(site, "push", "-q", "origin", "main")
    published = snap.check_published(engine, site)
    assert published["ok"] is True and published["site"]["commit"] == _head(site) != recorded_commit
    snap.record_publication(engine, published)
    assert snap.publication_records(engine, "study-interim-20200102")[0]["site_commit"] == _head(site)


def test_another_publish_that_changes_a_recorded_file_is_refused_until_a_superseding_snapshot(repos, tmp_path):
    engine, site = repos
    _published(engine, site)
    _republish_payload(site)
    _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    _other_publish(tmp_path, site, "data/urgency_shift.json", {"rows": [], "summary": {"n": 3}})
    _git(site, "fetch", "-q", "origin")
    report = snap.check_release(engine, site)
    assert "origin/main changed the published statistics file data/urgency_shift.json" in _problems(report)
    _git(site, "pull", "-q", "--rebase", "origin", "main")
    report = snap.check_release(engine, site)
    assert report["ok"] is False and "data/urgency_shift.json at the site HEAD has sha256" in _problems(report)
    unpublished = (engine / snap.SNAPSHOT_DIR / "study-interim-20200102.json").read_bytes()
    doc = _snapshot(engine, site, "study-interim-20200103", supersedes="study-interim-20200102")
    assert (engine / snap.SNAPSHOT_DIR / "study-interim-20200102.json").read_bytes() == unpublished   # never edited
    assert snap.check_release(engine, site)["ok"] is True
    change = doc["outputs"]["changed_since_superseded"]
    assert change["compared_with"] == "study-interim-20200102"       # its commit is still in the repository
    assert list(change["files"]) == ["data/urgency_shift.json"]
    _git(engine, "push", "-q", "origin", "main")
    _git(site, "push", "-q", "origin", "main")
    snap.record_publication(engine, snap.check_published(engine, site))
    assert snap.publication_records(engine, "study-interim-20200102") == []     # created, never published
    assert len(snap.publication_records(engine, "study-interim-20200103")) == 1


def test_a_superseded_snapshot_whose_site_commit_is_gone_is_passed_over_for_the_one_before(repos, tmp_path):
    engine, site = repos
    _published(engine, site)
    lost = _republish_payload(site, n_phrases=9, mean=-0.04)
    _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    _other_publish(tmp_path, site, "data/urgency_shift.json", {"rows": [], "summary": {"n": 3}})
    _git(site, "pull", "-q", "--rebase", "origin", "main")
    _git(site, "update-ref", "-d", "ORIG_HEAD")
    _git(site, "reflog", "expire", "--expire=now", "--all")          # a later clone: the old commit is not there
    _git(site, "gc", "-q", "--prune=now")
    assert _git(site, "cat-file", "-e", lost, check=False).returncode != 0
    doc = _snapshot(engine, site, "study-interim-20200103", supersedes="study-interim-20200102")
    change = doc["outputs"]["changed_since_superseded"]
    assert change["compared_with"] == "study-interim-20200101"
    assert [p["id"] for p in change["snapshots_passed_over"]] == ["study-interim-20200102"]
    assert lost in change["snapshots_passed_over"][0]["reason"]
    assert sorted(change["files"]) == [PAYLOAD, "data/urgency_shift.json"]
    assert change["payload_summary_penalty"]["before"]["n_phrases"] == 10
    assert change["payload_summary_penalty"]["after"]["n_phrases"] == 9


def test_a_change_record_is_refused_when_no_snapshot_in_the_chain_can_be_read(repos):
    engine, site = repos
    _snapshot(engine, site, "study-interim-20200101")
    _write(site / PAYLOAD, _payload(8, -0.03))
    _git(site, "add", "-A")
    _git(site, "commit", "-q", "--amend", "-m", "base, rewritten")   # the recorded commit leaves the history
    _git(site, "remote", "remove", "origin")
    _git(site, "reflog", "expire", "--expire=now", "--all")
    _git(site, "gc", "-q", "--prune=now")
    with pytest.raises(snap.SnapshotError, match="the change record cannot be written"):
        _snapshot(engine, site, "study-interim-20200102", supersedes="study-interim-20200101")
    assert snap.unindexed_files(engine) == []                        # nothing was written
    assert snap.load_index(engine)["current"] == {rp.STUDY_INTERIM: "study-interim-20200101"}


# ---------------------------------------------------------------- shallow checkouts

def test_ancestry_is_read_from_the_commit_objects_in_a_shallow_checkout(repos, tmp_path):
    """Found 2026-11-10 in a cloud checkout: a depth-limited fetch had marked the branch head as a shallow
    boundary although its parents were on disk, and ``merge-base --is-ancestor`` then answered no for the
    commit the committed snapshot records."""
    engine, site = repos
    doc = _snapshot(engine, site, "study-interim-20200101")
    _write(engine / "docs" / "note.md", "a later commit")
    _commit_all(engine, "later")
    (engine / ".git" / "shallow").write_text(_head(engine) + "\n", encoding="utf-8")
    assert _git(engine, "merge-base", "--is-ancestor", doc["engine_commit"], "HEAD", check=False).returncode != 0
    assert snap._is_ancestor(engine, doc["engine_commit"], "HEAD") is True
    assert snap.check_release(engine, site)["ok"] is True
    # the same on the site: the base ref and a local commit on top of it, with the local head marked shallow
    base = _head(site)
    _write(site / "data" / "results_catalogue" / "index.json", {"runs": [{"run_dir": "x"}]})
    _commit_all(site, "catalogue")
    (site / ".git" / "shallow").write_text(_head(site) + "\n", encoding="utf-8")
    assert _git(site, "merge-base", "origin/main", "HEAD", check=False).returncode != 0
    assert snap._merge_base(site, base, _head(site)) == base
    report = snap.check_release(engine, site)
    assert report["ok"] is True and report["site"]["merge_base"] == base
    assert [c["path"] for c in report["changed"]["outside_snapshot"]] == ["data/results_catalogue/index.json"]
    # history that was never fetched cannot be vouched for: the answer is "cannot say", and the check refuses
    (engine / ".git" / "shallow").unlink()
    first = _git(engine, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
    _git(engine, "tag", "first", first)
    clone = tmp_path / "shallow-clone"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{engine}", clone.name)
    _git(clone, "fetch", "-q", "--depth", "1", "origin", "tag", "first")
    assert snap._commit(clone, first) == first and snap._is_ancestor(clone, first, "HEAD") is None
    problem = snap._ancestry_problem(clone, "the engine commit the snapshot records", first, _head(clone),
                                     "the engine HEAD", "unused")
    assert problem is not None and "shallow checkout" in problem and "git fetch --deepen" in problem


# ---------------------------------------------------------------- the set, the skill and the real repository

def test_every_data_path_is_in_exactly_one_list_and_the_set_covers_what_earlier_snapshots_recorded():
    assert not set(snap.STATISTICS_FILES) & set(snap.OUTSIDE_SNAPSHOT_FILES)
    assert set(snap.STATISTICS_FILES.values()) <= set(snap.INPUT_RELATIONS)
    assert snap.classify_site_path(PAYLOAD) == ("statistics", snap.MEMBERSHIP_INPUTS)   # carries summary.penalty
    assert snap.classify_site_path("data/results_catalogue/rows/x.json")[0] == "outside"
    assert snap.classify_site_path("data/advice_scenarios.sample.json")[0] == "outside"
    assert snap.classify_site_path("data/unknown/advice.sample.json") == ("unclassified", "")
    assert snap.classify_site_path("data/results_catalogue.json") == ("unclassified", "")
    assert snap.classify_site_path("data/anything_new.json") == ("unclassified", "")
    for entry in snap.load_index(rp.ENGINE)["snapshots"]:
        recorded = (snap.load_snapshot(rp.ENGINE, entry["id"]).get("outputs") or {}).get("files") or {}
        assert set(recorded) <= set(snap.STATISTICS_FILES), entry["id"]


def test_the_committed_snapshots_still_verify_and_their_files_are_unchanged():
    index = snap.load_index(rp.ENGINE)
    assert snap.unindexed_files(rp.ENGINE) == []
    assert "study-interim-20261110" in {e["id"] for e in index["snapshots"]}
    for entry in index["snapshots"]:
        report = snap.verify(rp.ENGINE, entry["id"])
        assert report["ok"] and report["snapshot_file_unchanged"], (entry["id"], report["config_changed"])
    first = snap.load_snapshot(rp.ENGINE, "study-interim-20261110")
    assert "changed_since_superseded" not in first["outputs"]        # the 2026-11-10 file predates the key
    assert len(first["outputs"]["files"]) == 8


def test_every_data_file_the_sibling_site_tracks_is_classified():
    site = rp.ENGINE.parent / "patientwords"
    if snap._commit(site, "HEAD") is None:
        pytest.skip("the sibling site checkout is not present")
    tracked = [p for p in _git(site, "ls-files", "-z", "data").stdout.split("\0") if p]
    assert tracked
    assert [p for p in tracked if snap.classify_site_path(p)[0] == "unclassified"] == []
    assert sorted(set(snap.STATISTICS_FILES) - set(tracked)) == []     # no entry names a file the site lacks


def test_the_publish_skill_pushes_nothing_before_the_snapshot_exists_and_the_release_check_passes():
    lines = SKILL.read_text(encoding="utf-8").splitlines()

    def first(needle: str) -> int:
        return next(i for i, line in enumerate(lines) if needle in line)

    pushes = [i for i, line in enumerate(lines) if "push origin" in line]
    assert len(pushes) >= 2
    create, check = first("results_snapshot.py create"), first("results_snapshot.py check-release --site")
    assert create < check < min(pushes)
    engine_push = first("git push origin main")
    site_push = first("git -C ../patientwords push origin main")
    assert check < engine_push < site_push < first("check-release --site ../patientwords --published")
    text = SKILL.read_text(encoding="utf-8")
    assert "whenever ANY published statistics file changes" in text
    for rule in ("Never edit page HTML, page text, figures, or labels",
                 "Never publish a scale-framing sentence",
                 "Never remove or soften the urgency-tier review label",
                 "Never hand-edit an exported payload",
                 "Never change depth-exporter pins",
                 "Never let holdout phrase text reach any output",
                 "Never run `scripts/publication_release.py --release`"):
        assert rule in text, rule
