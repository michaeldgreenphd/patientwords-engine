"""Synthetic contracts only; no provider or archived source is loaded."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable

import pytest

from scripts import action_annotations as aa

FIXTURES = Path(__file__).parent / "fixtures/action_annotations"


@pytest.fixture
def packets() -> tuple[dict, dict]:
    return aa.read_json(FIXTURES / "sources.json"), aa.read_json(FIXTURES / "responses.json")


def test_manual_keys_and_unicode_offsets(packets: tuple[dict, dict]) -> None:
    source, responses = packets
    result = aa.validate(source, responses)
    assert len(result["items"]) == 10
    assert result["model_calls"] == 0
    assert result["status"] == "structurally_valid_semantics_unverified"
    cases = aa.read_json(FIXTURES / "cases.json")["cases"]
    for expected, item, row in zip(cases, source["items"], result["items"]):
        assert expected["text"] == item["text"]
        assert expected["id"] == row["source_id"]
        assert row["annotation"]["status"] == expected["status"]
        assert row["annotation"]["reason"] == expected["reason"]
        assert len(row["annotation"]["actions"]) == len(expected["actions"])
        for actual, gold in zip(row["annotation"]["actions"], expected["actions"]):
            for key in ("category", "stance", "actor"):
                assert actual[key] == gold[key]
            for key in ("evidence", "timing", "condition"):
                assert (None if actual[key] is None else actual[key]["quote"]) == gold[key]
    # A non-BMP character counts once, not as a UTF-16 pair or four UTF-8 bytes.
    assert result["items"][6]["annotation"]["actions"][0]["evidence"]["start"] == 2


def test_prepare_deterministic_and_blinded(packets: tuple[dict, dict]) -> None:
    source, _ = packets
    one, two = aa.prepare(source), aa.prepare(copy.deepcopy(source))
    assert one == two
    assert one["sources_sha256"] == aa.digest(aa.encoded(source))
    for item, req in zip(source["items"], one["requests"]):
        assert json.loads(req["payload"]["user"]) == {"response": item["text"]}
        assert set(req["payload"]) == {"system", "user", "response_schema"}
        assert "annotation" not in req["payload"]


@pytest.mark.parametrize("field", ["timing", "condition"])
def test_missing_required_nullable_refuses_but_null_passes(packets: tuple[dict, dict], field: str) -> None:
    source, rows = packets
    action = rows["items"][0]["annotation"]["actions"][0]
    assert action[field] is None
    aa.validate(source, rows)
    del action[field]
    with pytest.raises(aa.AnnotationRefusal, match="annotation_schema"):
        aa.validate(source, rows)


@pytest.mark.parametrize("change,reason", [
    (lambda r: r["items"].pop(), "coverage"),
    (lambda r: r["items"].append(copy.deepcopy(r["items"][0])), "duplicate_response"),
    (lambda r: r["items"][0].update(source_id="not-selected"), "coverage"),
    (lambda r: r["items"][0].update(source_sha256="0" * 64), "source_sha256_mismatch"),
    (lambda r: r["items"][0].update(request_sha256="0" * 64), "request_sha256_mismatch"),
    (lambda r: r.update(artifact_kind="recorded"), "research_response_not_enabled"),
])
def test_packets_refuse_missing_duplicate_and_stale(
    packets: tuple[dict, dict], change: Callable[[dict], None], reason: str,
) -> None:
    source, rows = packets
    change(rows)
    with pytest.raises(aa.AnnotationRefusal, match=reason):
        aa.validate(source, rows)


@pytest.mark.parametrize("field,value,reason", [
    ("category", "invented", "unknown_category"),
    ("stance", "invented", "unknown_stance"),
    ("actor", "invented", "unknown_actor"),
    ("evidence", {"start": True, "end": 2, "quote": "x"}, "annotation_schema"),
    ("evidence", {"start": "0", "end": 2, "quote": "x"}, "annotation_schema"),
    ("evidence", {"start": 0.0, "end": 2, "quote": "x"}, "annotation_schema"),
    ("evidence", {"start": -1, "end": 2, "quote": "x"}, "evidence_span_mismatch"),
    ("evidence", {"start": 0, "end": 99999, "quote": "x"}, "evidence_span_mismatch"),
    ("evidence", {"start": 0, "end": 1, "quote": "x"}, "evidence_span_mismatch"),
    ("evidence", None, "annotation_schema"),
    ("condition", "inferred", "annotation_schema"),
    ("stance", "conditional", "conditional_without_condition"),
])
def test_action_refusals(packets: tuple[dict, dict], field: str, value: object, reason: str) -> None:
    source, rows = packets
    rows["items"][0]["annotation"]["actions"][0][field] = value
    with pytest.raises(aa.AnnotationRefusal, match=reason):
        aa.validate(source, rows)


def test_timing_must_belong_to_action_evidence(packets: tuple[dict, dict]) -> None:
    source, rows = packets
    action = rows["items"][3]["annotation"]["actions"][0]
    action["timing"] = rows["items"][3]["annotation"]["actions"][1]["evidence"]
    with pytest.raises(aa.AnnotationRefusal, match="timing_outside_evidence"):
        aa.validate(source, rows)


@pytest.mark.parametrize("status,actions,reason", [
    ("annotated", [], None), ("uncertain", [], None), ("no_actions", [], "x"), ("other", [], None),
])
def test_distinct_empty_states(packets: tuple[dict, dict], status: str, actions: list, reason: str | None) -> None:
    source, rows = packets
    rows["items"][0]["annotation"] = {"status": status, "actions": actions, "reason": reason}
    with pytest.raises(aa.AnnotationRefusal):
        aa.validate(source, rows)


def test_duplicate_actions_and_nonannotated_actions_refuse(packets: tuple[dict, dict]) -> None:
    source, rows = packets
    row = rows["items"][0]["annotation"]
    row["actions"] *= 2
    with pytest.raises(aa.AnnotationRefusal, match="duplicate_action"):
        aa.validate(source, rows)
    row["status"] = "uncertain"
    with pytest.raises(aa.AnnotationRefusal, match="nonannotated_actions"):
        aa.validate(source, rows)


def test_literal_match_does_not_certify_meaning(packets: tuple[dict, dict]) -> None:
    source, rows = packets
    key = copy.deepcopy(rows)
    rows["items"][0]["annotation"]["actions"][0]["stance"] = "recommended"
    result = aa.validate(source, rows)
    assert result["status"] == "structurally_valid_semantics_unverified"
    expected = aa.read_json(FIXTURES / "cases.json")["cases"][0]["actions"][0]["stance"]
    assert result["items"][0]["annotation"]["actions"][0]["stance"] != expected
    scored = aa.score(source, rows, key)["key_comparison"]
    assert scored["exact_case_matches"] == 9
    assert scored["cases"][0]["extra_actions"] == 1
    assert scored["cases"][0]["missing_actions"] == 1


def test_scoring_does_not_drop_uncertain_or_empty_cases(packets: tuple[dict, dict]) -> None:
    source, rows = packets
    key = copy.deepcopy(rows)
    rows["items"][0]["annotation"] = {"status": "uncertain", "actions": [], "reason": "Unclear source."}
    result = aa.score(source, rows, key)["key_comparison"]
    assert result["total_cases"] == 10
    assert result["exact_case_matches"] == 9
    assert result["cases"][0]["observed_status"] == "uncertain"
    assert result["cases"][0]["missing_actions"] == 1
    assert not result["cases"][0]["status_matches"]
    assert result["cases"][5]["exact_case_match"]


def test_scoring_ignores_action_order(packets: tuple[dict, dict]) -> None:
    source, rows = packets
    key = copy.deepcopy(rows)
    rows["items"][3]["annotation"]["actions"].reverse()
    assert aa.score(source, rows, key)["key_comparison"]["exact_case_matches"] == 10


@pytest.mark.parametrize("change,reason", [
    (lambda d: d["items"][0].update(text="changed"), "source_hash_mismatch"),
    (lambda d: d.update(artifact_kind="archive"), "research_input_not_enabled"),
    (lambda d: d.update(items=[]), "empty_sources"),
    (lambda d: d["items"].append(d["items"][0]), "duplicate_source_id"),
    (lambda d: d["items"][0].update(source_id=""), "source_id"),
])
def test_source_refusals(packets: tuple[dict, dict], change: Callable[[dict], None], reason: str) -> None:
    source, _ = packets
    change(source)
    with pytest.raises(aa.AnnotationRefusal, match=reason):
        aa.prepare(source)


def test_escaped_unpaired_unicode_has_named_refusal(packets: tuple[dict, dict]) -> None:
    source, _ = packets
    source["items"][0]["text"] = "\ud800"
    with pytest.raises(aa.AnnotationRefusal, match="invalid_utf8"):
        aa.prepare(source)


@pytest.mark.parametrize("body,reason", [('{"a":1,"a":2}', "duplicate_json_key"),
                                        ('{"a":NaN}', "nonfinite_json"), ('{', "unreadable_json")])
def test_strict_json(tmp_path: Path, body: str, reason: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(body)
    with pytest.raises(aa.AnnotationRefusal, match=reason):
        aa.read_json(path)


def test_reordered_responses_rejoin_by_id(packets: tuple[dict, dict]) -> None:
    source, rows = packets
    rows["items"].reverse()
    result = aa.validate(source, rows)
    assert [r["source_id"] for r in result["items"]] == [s["source_id"] for s in source["items"]]


def test_cli_replay_preserves_existing_outputs_and_refuses_partial(tmp_path: Path, packets: tuple[dict, dict]) -> None:
    out = tmp_path / "action_annotations.json"
    command = [sys.executable, "-m", "scripts.action_annotations", "validate", "--sources",
               str(FIXTURES / "sources.json"), "--responses", str(FIXTURES / "responses.json"), "--out", str(out)]
    good = subprocess.run(command, cwd=aa.ROOT, capture_output=True, text=True)
    assert good.returncode == 0, good.stdout + good.stderr
    before = out.read_bytes()
    assert subprocess.run(command, cwd=aa.ROOT, capture_output=True).returncode == 2
    assert out.read_bytes() == before
    _, bad = packets
    bad["items"].pop()
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad))
    out.unlink()
    command[command.index("--responses") + 1] = str(bad_path)
    assert subprocess.run(command, cwd=aa.ROOT, capture_output=True).returncode == 2
    assert not out.exists()


def test_output_namespace_and_git_boundary(tmp_path: Path) -> None:
    with pytest.raises(aa.AnnotationRefusal, match="output_filename"):
        aa.write_new(tmp_path / "batch_summary.json", {})
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: elsewhere")
    with pytest.raises(aa.AnnotationRefusal, match="output_inside_repository"):
        aa.write_new(repo / "action_annotations.json", {})
    assert sorted(p.name for p in repo.iterdir()) == [".git"]
