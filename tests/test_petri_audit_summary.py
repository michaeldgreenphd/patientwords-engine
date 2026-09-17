"""The lane's job summary (scripts/petri_audit/summary.py): every quantity it
reports is read from the files a run wrote, labelled by provenance, and a
section it cannot compute says so instead of failing the step. 3.11-safe."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, framework, spend, summary, transcripts  # noqa: E402
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402


def _record(conversation_id: str, manifest_sha: str) -> dict:
    messages = [{"role": "user", "text": "u", "id": "m1"},
                {"role": "assistant", "text": "", "id": "m2",
                 "tool_calls": [{"call_id": "c1", "name": "lookup", "arguments": {"query": "q"}, "parse_error": None}]},
                {"role": "tool", "text": "RESULT", "id": "m3", "tool_call_id": "c1"},
                {"role": "assistant", "text": "final", "id": "m4"}]
    return transcripts.build_record(messages, conversation_id=conversation_id, source_system="inspect_petri",
                                    source_model="mockllm/model", model_version="mockllm", captured_utc="2026-09-16T00:00:00Z",
                                    user_is="unknown", import_utc="2026-09-16T00:00:00Z", importer_sha=None,
                                    run_manifest_sha256=manifest_sha, run_manifest_ref=None)


@pytest.fixture
def run_dir(tmp_path) -> Path:
    """The schema's example manifest as a chained run directory whose
    transcripts are real records (one per exported branch), plus a cost
    sidecar and a raw .eval outside it."""
    runs = tmp_path / "runs"
    base = json.loads(json.dumps(framework.load_json(framework.MANIFEST_SCHEMA)["examples"][0]))
    d = runs / "example"
    d.mkdir(parents=True)
    conv_ids = [b["conversation_id"] for t in base["trees"] for b in t["branches"]]
    (d / "rule_outcomes.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "sanitised_log.json").write_text(json.dumps({"status": "success", "samples": []}), encoding="utf-8")
    base["artifacts"]["sanitised_log_sha256"] = framework.sha256_file(d / "sanitised_log.json")
    raw = tmp_path / "logs"
    raw.mkdir()
    (raw / "run.eval").write_bytes(b"raw log bytes")
    base["artifacts"]["raw_eval_log_sha256"] = framework.sha256_file(raw / "run.eval")
    # the run is priced with this checkout's registry, and the manifest pins its digest as the adapter does
    base["usage"]["pricing_source_sha256"] = spend.pricing_source_digest()
    # the records are bound to the manifest's identity digest exactly as the adapter binds them: the identity excludes
    # the record-dependent digests, so it is known before the records are written
    identity = manifest_mod.identity_digest(base)
    (d / "transcripts.jsonl").write_text("".join(json.dumps(_record(c, identity)) + "\n" for c in conv_ids), encoding="utf-8")
    for fam in ("transcripts", "rule_outcomes"):
        base["artifacts"][f"{fam}_sha256"] = framework.sha256_file(runs / base["artifacts"][f"{fam}_path"])
    sealed = manifest_mod.seal_manifest(base, None)
    assert sealed["chain"]["identity_sha256"] == identity
    assert manifest_mod.manifest_problems(sealed) == []
    manifest_mod.write_manifest(d / "manifest.json", sealed)
    manifest_mod.append_chain(runs, sealed, d / "manifest.json")
    framework.write_json(d / "example.report.json", {"cost_usd": 0.0, "cost_basis": "engine_repriced_from_inspect_model_usage",
                                                       "billing_channel": "anthropic", "usage_missing_models": ["mockllm/model"],
                                                       "max_spend_usd": 0.01})
    return d


def test_summary_reads_the_run_it_is_given_and_labels_usage_by_provenance(run_dir):
    s = summary.run_summary(run_dir, mode="dry_run", raw_eval_dir=run_dir.parent.parent / "logs")
    m = framework.load_json(run_dir / "manifest.json")
    st = s["structure"]
    assert st["trees"] == len(m["trees"]) and st["branches"] == sum(len(t["branches"]) for t in m["trees"])
    assert st["records"]["count"] == st["branches"] and st["records"]["with_problems"] == 0
    assert st["target_calls"] == next(r for r in m["usage"]["by_role"] if r["role"] == "target")["calls"]
    child = [b for t in m["trees"] for b in t["branches"] if b["parent_branch_id"] is not None]
    assert child and st["shared_prefix_branches"] == {"anchored": len(child), "without_resolved_anchor": 0}
    assert st["refused"]["count"] == len(m["integrity"]["records_refused"]) and st["eval_status"] == "success"
    assert st["conditions"] == len({(t["seed_id"], b["condition_id"]) for t in m["trees"] for b in t["branches"] if b["condition_id"] is not None})
    assert st["branches_without_condition_id"] == sum(1 for t in m["trees"] for b in t["branches"] if b["condition_id"] is None)
    assert st["unavailable_fields"] == {}
    # the mock target is labelled as such: its token counts are never called provider-measured
    assert [r["status"] for r in s["usage"]] == [summary.USAGE_MOCK]
    assert s["usage"][0]["price_source"] == "zero:mock_or_placeholder"
    # raw log: size measured, digest checked against the manifest
    assert s["raw_eval"]["files"][0]["bytes"] == len(b"raw log bytes") and s["raw_eval"]["files"][0]["matches_manifest"] is True
    # published bytes and the attachment scan
    pub = s["published"]
    assert set(pub["files"]) == {"manifest.json", "transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json"}
    assert pub["cost_sidecars"] == {"example.report.json": (run_dir / "example.report.json").stat().st_size} and pub["unexpected"] == {}
    assert pub["total_bytes"] == sum(pub["files"].values()) + sum(pub["cost_sidecars"].values()) and pub["attachment_references"] == 0
    assert s["integrity"]["manifest_problems"] == [] and s["integrity"]["artifact_problems"] == [] and s["integrity"]["chain"]["ok"] is True
    assert s["integrity"]["run_self_verification"] == []
    assert s["sidecar"]["cost_usd"] == 0.0 and s["sidecar"]["billing_channel"] == "anthropic"
    assert s["judge_sidecar"] is None
    assert s["judge_prompts"] == {"unavailable": "no seed file given"}
    assert s["redaction"] == m["artifacts"]["sanitiser"]["redaction_report"]
    assert st["records"]["id_match"] == {"records_not_in_manifest": 0, "branches_without_record": 0, "duplicate_branch_ids": 0}
    assert st["records"]["provenance_mismatches"] == 0
    assert s["manifest"]["contract_checks"] == m["execution"]["contract_checks"]
    text = summary.render_markdown(s)
    for needle in ("Measured structure", "mock/non-metered", "Run directory contents (byte sizes)", "unresolved attachment:// references | 0",
                   "verifies on its own (cli verify-run) | `[]`",
                   "Target cost sidecar", "hash chain | True", "Judge cost sidecar: none written."):
        assert needle in text, needle


def test_usage_status_distinguishes_measured_missing_and_mock():
    priced = {"input_tokens": 10, "output_tokens": 5, "calls": 1, "calls_without_usage": 0}
    assert summary.usage_status(priced, "registry", zero_priced=False) == summary.USAGE_PROVIDER_MEASURED
    assert summary.usage_status(dict(priced, calls_without_usage=1), "registry", zero_priced=False) == summary.USAGE_UNAVAILABLE
    assert summary.usage_status({"input_tokens": None, "output_tokens": None, "calls": 1, "calls_without_usage": 0}, "registry",
                                zero_priced=False) == summary.USAGE_UNAVAILABLE
    assert summary.usage_status(priced, "zero:mock_or_placeholder", zero_priced=True) == summary.USAGE_MOCK


def test_preflight_summary_reports_no_run_and_the_resolved_parameters(tmp_path):
    params = {"mode": "preflight", "target": "mockllm/model", "max_spend": "0.01"}
    s = summary.run_summary(tmp_path / "absent", mode="preflight", raw_eval_dir=tmp_path / "no-logs", params=params)
    assert s["manifest"] is None and s["run_dir_exists"] is False and s["raw_eval_present"] is False
    assert "gated off by mode" in s["note"] and s["raw_eval"]["note"].startswith("no raw .eval found")
    text = summary.render_markdown(s)
    assert "Parameters resolved by CI" in text and "| target | mockllm/model |" in text and "No manifest" in text


def test_a_section_that_cannot_be_computed_is_reported_not_defaulted(run_dir):
    (run_dir / "transcripts.jsonl").write_text("{not json\n", encoding="utf-8")
    s = summary.run_summary(run_dir, mode="dry_run")
    assert "unavailable" in s["structure"] and "JSONDecodeError" in s["structure"]["unavailable"]
    # the other sections still report, and integrity now names the changed artifact
    assert any("transcripts" in p for p in s["integrity"]["artifact_problems"])
    assert s["integrity"]["chain"]["ok"] is False
    text = summary.render_markdown(s)
    assert "Structure: unavailable (JSONDecodeError" in text


def test_attachment_references_in_a_published_file_are_counted(run_dir):
    (run_dir / "rule_outcomes.jsonl").write_text('{"text": "attachment://deadbeef"}\n', encoding="utf-8")
    s = summary.run_summary(run_dir, mode="dry_run")
    assert s["published"]["attachment_references"] == 1


def test_judged_outputs_and_unexpected_entries_are_inventoried(run_dir):
    """Codex (PR #27): a fixed tuple omitted the judged run's judgments.jsonl
    and analysis_rows.jsonl from the sizes, the total and the attachment
    scan; anything else in the run directory is now listed as unexpected."""
    (run_dir / "judgments.jsonl").write_text('{"key": "x"}\n', encoding="utf-8")
    (run_dir / "analysis_rows.jsonl").write_text('{"row": "attachment://beef"}\n', encoding="utf-8")
    (run_dir / "stray.txt").write_text("attachment://not-scanned-not-json\n", encoding="utf-8")
    (run_dir / "stray.json").write_text('{"x": "attachment://scanned"}\n', encoding="utf-8")
    (run_dir / "logs").mkdir()
    s = summary.run_summary(run_dir, mode="run")
    pub = s["published"]
    assert set(pub["files"]) == set(summary.PUBLISHED_FILES)
    assert pub["unexpected"] == {"logs/": None, "stray.json": (run_dir / "stray.json").stat().st_size,
                                 "stray.txt": (run_dir / "stray.txt").stat().st_size}
    assert pub["attachment_references"] == 2, "every JSON/JSONL file is scanned, the unexpected one included"
    assert pub["total_bytes"] == sum(pub["files"].values()) + sum(pub["cost_sidecars"].values()) + sum(
        v for v in pub["unexpected"].values() if v is not None)
    text = summary.render_markdown(s)
    assert "| judgments.jsonl |" in text and "| logs/ | directory (UNEXPECTED" in text and "| stray.txt |" in text
    # files inside a nested directory are inventoried, counted and scanned too (Codex, PR #27, seventh round)
    nested = run_dir / "nested" / "deeper"
    nested.mkdir(parents=True)
    (nested / "leak.json").write_text('{"t": "attachment://nested"}\n', encoding="utf-8")
    (run_dir / "nested" / "blob.bin").write_bytes(b"\x00" * 7)
    s = summary.run_summary(run_dir, mode="run")
    pub = s["published"]
    assert pub["unexpected"]["nested/deeper/leak.json"] == (nested / "leak.json").stat().st_size
    assert pub["unexpected"]["nested/blob.bin"] == 7 and "nested/" not in pub["unexpected"], "a non-empty directory lists its files"
    assert pub["attachment_references"] == 3
    assert pub["total_bytes"] == sum(pub["files"].values()) + sum(pub["cost_sidecars"].values()) + sum(
        v for v in pub["unexpected"].values() if v is not None)
    assert "| nested/deeper/leak.json |" in summary.render_markdown(s)


def test_a_missing_transcript_export_is_a_gap_not_a_zero_count(run_dir):
    """Codex (PR #27): an absent transcripts.jsonl read as zero records
    exported, a plausible false measurement."""
    (run_dir / "transcripts.jsonl").unlink()
    s = summary.run_summary(run_dir, mode="dry_run")
    st = s["structure"]
    assert st["records"] == {"unavailable": "transcripts.jsonl is missing from the run directory"}
    assert "count" not in st["records"] and st["trees"] == 1, "the manifest-derived counts stand"
    assert any("transcripts" in p for p in s["integrity"]["artifact_problems"])
    text = summary.render_markdown(s)
    assert "| records exported | unavailable: transcripts.jsonl is missing" in text


def test_partial_exports_are_inventoried_when_no_manifest_exists(run_dir):
    """Codex (PR #27): an adaptation that failed after writing the record
    families but before the manifest left files the early return never
    inventoried, attachment references included."""
    (run_dir / "manifest.json").unlink()
    (run_dir / "rule_outcomes.jsonl").write_text('{"text": "attachment://deadbeef"}\n', encoding="utf-8")
    s = summary.run_summary(run_dir, mode="dry_run")
    assert s["manifest"] is None and s["run_dir_exists"] is True
    pub = s["published"]
    assert set(pub["files"]) == {"transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json"}
    assert pub["attachment_references"] == 1 and "example.report.json" in pub["cost_sidecars"]
    text = summary.render_markdown(s)
    assert "No manifest (no adapted run)" in text and "no manifest: partial or failed adaptation" in text and "| rule_outcomes.jsonl |" in text
    assert summary.run_summary(run_dir.parent / "absent", mode="dry_run")["published"] is None
    # the raw log's measurements are rendered without a manifest too (Codex, PR #27, fourth round)
    s = summary.run_summary(run_dir, mode="dry_run", raw_eval_dir=run_dir.parent.parent / "logs")
    assert s["raw_eval"]["files"][0]["bytes"] == len(b"raw log bytes") and s["raw_eval"]["files"][0]["matches_manifest"] is None
    text = summary.render_markdown(s)
    assert "Raw .eval (private artifact, never committed)" in text and "| run.eval | 13 bytes, sha256 " in text


def test_a_malformed_manifest_is_reported_and_the_rest_still_inventoried(run_dir, tmp_path, capsys):
    """Codex (PR #27, fourth round): a truncated manifest.json raised out of
    run_summary, so the step printed only its generic failure line."""
    (run_dir / "manifest.json").write_text('{"run_id": "trunc', encoding="utf-8")
    s = summary.run_summary(run_dir, mode="dry_run", raw_eval_dir=run_dir.parent.parent / "logs")
    assert s["manifest"] is None and s["manifest_error"].startswith("manifest.json does not parse: JSONDecodeError")
    assert "manifest.json" in s["published"]["files"] and "example.report.json" in s["published"]["cost_sidecars"]
    assert s["raw_eval"]["files"][0]["bytes"] == len(b"raw log bytes")
    text = summary.render_markdown(s)
    assert "No manifest (manifest.json does not parse: JSONDecodeError" in text
    assert cli.main(["run-summary", "--run-dir", str(run_dir), "--mode", "dry_run"]) == 0
    assert "does not parse" in capsys.readouterr().out
    (run_dir / "manifest.json").write_text("[1, 2]", encoding="utf-8")
    assert "holds a list, not an object" in summary.run_summary(run_dir, mode="dry_run")["manifest_error"]


def test_missing_manifest_collections_are_unavailable_not_zero(run_dir):
    """Codex (PR #27): `or []` fallbacks turned a manifest without `trees`,
    `integrity.records_refused` or `usage.by_role` into plausible zero
    counts."""
    m = framework.load_json(run_dir / "manifest.json")
    del m["trees"]
    del m["integrity"]["records_refused"]
    m["usage"]["by_role"] = [{"role": "auditor", "calls": 3}]
    del m["usage"]["by_model"]
    framework.write_json(run_dir / "manifest.json", m)
    s = summary.run_summary(run_dir, mode="dry_run")
    st = s["structure"]
    assert st["trees"] is None and st["branches"] is None and st["conditions"] is None and st["survivors_exported"] is None
    assert st["refused"] is None and st["target_calls"] is None
    assert st["unavailable_fields"] == {"trees": "manifest lacks 'trees'",
                                        "refused": "manifest lacks 'integrity.records_refused'",
                                        "target_calls": "manifest usage.by_role carries no target row"}
    assert st["records"]["count"] == len((run_dir / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()), "the transcript file is intact, so its count stands"
    assert s["usage"] == {"unavailable": "KeyError: \"manifest lacks 'usage.by_model'\""}
    text = summary.render_markdown(s)
    assert "Structure fields unavailable (not zero):" in text and "- trees: manifest lacks 'trees'" in text
    assert "| trees (samples) | — |" in text and "Usage: unavailable" in text
    assert s["integrity"]["manifest_problems"], "the damaged manifest is also reported by the schema check"


def test_a_tree_without_its_branches_collection_is_a_gap_not_zero_branches(run_dir):
    """Codex (PR #27, third round): the outer `trees` list was validated but a
    tree's own `branches` fell back to zero branches."""
    m = framework.load_json(run_dir / "manifest.json")
    del m["trees"][0]["branches"]
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["trees"] is None and st["branches"] is None and st["conditions"] is None and st["shared_prefix_branches"] is None
    assert st["unavailable_fields"] == {"trees": f"tree {m['trees'][0]['tree_id']!r}: manifest lacks 'branches'"}
    m["trees"][0]["branches"] = "not a list"
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["branches"] is None and "is not a list" in st["unavailable_fields"]["trees"]


def test_a_missing_seeds_collection_is_a_gap_not_an_empty_list(run_dir):
    """Codex (PR #27, fourth round)."""
    m = framework.load_json(run_dir / "manifest.json")
    del m["seeds"]
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["seeds"] is None and st["unavailable_fields"] == {"seeds": "manifest lacks 'seeds'"}
    assert st["trees"] == 1, "the other collections still count"
    assert "| seeds | — |" in summary.render_markdown(summary.run_summary(run_dir, mode="dry_run"))


def test_conditions_are_counted_per_seed(run_dir):
    """Codex (PR #27, fifth round): condition ids repeat across seeds (every
    wave-1 seed has `clinical` and `colloquial`), so a manifest-wide set
    undercounted the cells that ran."""
    m = framework.load_json(run_dir / "manifest.json")
    second = json.loads(json.dumps(m["trees"][0]))
    second["tree_id"], second["seed_id"] = "t2", "another-seed"
    m["trees"].append(second)
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    labels = {b["condition_id"] for t in m["trees"] for b in t["branches"] if b["condition_id"] is not None}
    assert st["trees"] == 2 and st["conditions"] == 2 * len(labels) > len(labels)


def test_missing_member_keys_are_gaps_not_values(run_dir):
    """Codex (PR #27, fifth round): `.get()` on collection members read a
    missing survivor flag as False, a missing parent as a root and a missing
    anchor as unresolved."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(mutate):
        m = json.loads(json.dumps(base))
        mutate(m)
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="dry_run")["structure"]

    st = damaged(lambda m: m["trees"][0].pop("survivor_exported"))
    assert st["survivors_exported"] is None and st["trees"] is None
    assert st["unavailable_fields"]["trees"] == "tree 't1' lacks 'survivor_exported'"
    st = damaged(lambda m: m["trees"][0]["branches"][1].pop("parent_branch_id"))
    assert st["shared_prefix_branches"] is None and "branch 'b2' lacks 'parent_branch_id'" in st["unavailable_fields"]["trees"]
    st = damaged(lambda m: m["trees"][0]["branches"][0].pop("branched_from_turn_id"))
    assert st["branches"] is None and "lacks 'branched_from_turn_id'" in st["unavailable_fields"]["trees"]
    st = damaged(lambda m: m["trees"][0]["branches"][0].pop("condition_id"))
    assert st["conditions"] is None and "lacks 'condition_id'" in st["unavailable_fields"]["trees"]
    st = damaged(lambda m: m["integrity"]["records_refused"].append({"branch_id": "x"}))
    assert st["refused"] is None and st["unavailable_fields"]["refused"] == "refusal #0 lacks 'reason'"
    st = damaged(lambda m: m["seeds"][0].pop("claim_grade_eligible"))
    assert st["seeds"] is None and "lacks 'claim_grade_eligible'" in st["unavailable_fields"]["seeds"]
    st = damaged(lambda m: m["usage"]["by_role"][0].pop("calls"))
    assert st["target_calls"] is None and st["unavailable_fields"]["target_calls"] == "usage.by_role target row lacks 'calls'"
    # a legitimately null value is not a gap: the root branch's parent is None
    assert base["trees"][0]["branches"][0]["parent_branch_id"] is None
    framework.write_json(run_dir / "manifest.json", base)
    assert summary.run_summary(run_dir, mode="dry_run")["structure"]["unavailable_fields"] == {}


def test_wrong_member_types_are_gaps_not_values(run_dir):
    """Codex (PR #27, seventh round): presence alone read `survivor_exported:
    "false"` as a survivor; the expected type is checked too, and a bool
    never passes for an int."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(mutate):
        m = json.loads(json.dumps(base))
        mutate(m)
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="dry_run")

    st = damaged(lambda m: m["trees"][0].__setitem__("survivor_exported", "false"))["structure"]
    assert st["survivors_exported"] is None and st["unavailable_fields"]["trees"] == "tree 't1' 'survivor_exported' is not bool (got str)"
    st = damaged(lambda m: m["trees"][0]["branches"][1].__setitem__("branched_from_turn_id", True))["structure"]
    assert st["branches"] is None and "'branched_from_turn_id' is not int or null (got bool)" in st["unavailable_fields"]["trees"]
    st = damaged(lambda m: m["trees"][0]["branches"][1].__setitem__("condition_id", 3))["structure"]
    assert st["conditions"] is None and "'condition_id' is not str or null (got int)" in st["unavailable_fields"]["trees"]
    st = damaged(lambda m: m["usage"]["by_role"][0].__setitem__("calls", "3"))["structure"]
    assert st["target_calls"] is None and st["unavailable_fields"]["target_calls"] == "usage.by_role target row 'calls' is not int (got str)"
    st = damaged(lambda m: m["seeds"][0].__setitem__("claim_grade_eligible", 1))["structure"]
    assert st["seeds"] is None and "'claim_grade_eligible' is not bool (got int)" in st["unavailable_fields"]["seeds"]
    st = damaged(lambda m: m["integrity"]["records_refused"].append({"branch_id": "x", "reason": None}))["structure"]
    assert st["refused"] is None and st["unavailable_fields"]["refused"] == "refusal #0 'reason' is not str (got NoneType)"
    s = damaged(lambda m: m["usage"]["by_model"][0].__setitem__("input_tokens", "120"))
    assert s["usage"] == {"unavailable": "usage.by_model row #0 ('mockllm/model') 'input_tokens' is not int or null (got str)"}
    (run_dir / "sanitised_log.json").write_text(json.dumps({"status": 5}), encoding="utf-8")
    framework.write_json(run_dir / "manifest.json", base)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["eval_status"] is None and st["unavailable_fields"]["eval_status"] == "sanitised_log.json: sanitised_log.json 'status' is not str (got int)"


def test_a_damaged_sanitised_log_is_a_named_gap_not_a_failed_summary(run_dir, capsys):
    """Codex (PR #27, fifth round): the sanitised-log parse sat outside every
    guard, so a truncated file aborted the whole summary."""
    (run_dir / "sanitised_log.json").write_text('{"status": "succ', encoding="utf-8")
    s = summary.run_summary(run_dir, mode="dry_run")
    st = s["structure"]
    assert st["eval_status"] is None and st["unavailable_fields"]["eval_status"].startswith("sanitised_log.json: ")
    assert st["trees"] == 1 and s["published"]["files"]["sanitised_log.json"] > 0, "the rest of the summary still reports"
    assert any("sanitised_log" in p for p in s["integrity"]["artifact_problems"])
    assert cli.main(["run-summary", "--run-dir", str(run_dir), "--mode", "dry_run"]) == 0
    assert "- eval_status: sanitised_log.json: " in capsys.readouterr().out
    (run_dir / "sanitised_log.json").write_text('{"samples": []}', encoding="utf-8")
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["unavailable_fields"]["eval_status"] == "sanitised_log.json: sanitised_log.json lacks 'status'"
    (run_dir / "sanitised_log.json").unlink()
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["unavailable_fields"]["eval_status"] == "sanitised_log.json is missing from the run directory"


def test_nested_metadata_that_is_not_an_object_is_a_dash_not_a_failed_summary(run_dir, capsys):
    """Codex (PR #27, sixth round): `models.target: null` raised out of the
    header chain before any guarded section ran."""
    m = framework.load_json(run_dir / "manifest.json")
    m["models"]["target"] = None
    m["execution"] = "damaged"
    m["artifacts"]["sanitiser"] = None
    m["spend"] = []
    framework.write_json(run_dir / "manifest.json", m)
    s = summary.run_summary(run_dir, mode="dry_run", raw_eval_dir=run_dir.parent.parent / "logs")
    assert s["manifest"]["target"] is None and s["manifest"]["contract_checks"] is None and s["manifest"]["journal_nonce"] is None
    assert s["redaction"] is None and s["structure"]["trees"] == 1 and s["structure"]["max_turns"] is None
    assert s["published"]["files"]["manifest.json"] > 0 and s["raw_eval"]["files"]
    text = summary.render_markdown(s)
    assert "Contract checks: unavailable (execution.contract_checks is absent)" in text
    assert "Sanitiser redaction report: unavailable (absent)" in text and "| target | — |" in text
    assert cli.main(["run-summary", "--run-dir", str(run_dir), "--mode", "dry_run"]) == 0
    assert "Contract checks: unavailable" in capsys.readouterr().out
    # a contract-check block that is not the schema's closed set is unavailable by name, never a partial table
    # (Codex, PR #27, eleventh round)
    m["execution"] = {"contract_checks": {"holdout_seal": "pass"}}
    framework.write_json(run_dir / "manifest.json", m)
    text = summary.render_markdown(summary.run_summary(run_dir, mode="dry_run"))
    assert "Contract checks: unavailable (execution.contract_checks lacks 'stimulus_digest_identity'" in text


def test_cli_run_summary_survives_a_rendering_failure(run_dir, monkeypatch, capsys):
    """The step never fails the job over its own output: a renderer defect
    prints the summary data and the error instead of a traceback."""
    def broken(_s):
        raise RuntimeError("renderer defect")
    monkeypatch.setattr(summary, "render_markdown", broken)
    assert cli.main(["run-summary", "--run-dir", str(run_dir), "--mode", "dry_run"]) == 0
    out = capsys.readouterr().out
    assert "render failed: RuntimeError: renderer defect" in out and '"trees": 1' in out


def test_the_zero_missing_condition_count_is_rendered(run_dir):
    """Codex (PR #27, sixth round): a truthiness check dropped the valid zero."""
    s = summary.run_summary(run_dir, mode="dry_run")
    assert s["structure"]["branches_without_condition_id"] == 1, "the schema example's root branch has a null condition id"
    assert "| branches without a condition id | 1 |" in summary.render_markdown(s)
    m = framework.load_json(run_dir / "manifest.json")
    m["trees"][0]["branches"][0]["condition_id"] = "root-cond"
    framework.write_json(run_dir / "manifest.json", m)
    s = summary.run_summary(run_dir, mode="dry_run")
    assert s["structure"]["branches_without_condition_id"] == 0
    assert "| branches without a condition id | 0 |" in summary.render_markdown(s)


def test_a_damaged_usage_row_is_never_labelled_provider_measured(run_dir):
    """Codex (PR #27, sixth round): an absent calls_without_usage read as 0,
    so a row with token counts and no counters was provider-measured."""
    m = framework.load_json(run_dir / "manifest.json")
    m["usage"]["by_model"] = [{"model": "anthropic/claude-haiku-4-5", "input_tokens": 10, "output_tokens": 5, "calls": 1}]
    framework.write_json(run_dir / "manifest.json", m)
    s = summary.run_summary(run_dir, mode="run")
    assert s["usage"] == {"unavailable": "usage.by_model row #0 ('anthropic/claude-haiku-4-5') lacks 'calls_without_usage'"}
    assert "provider-measured" not in summary.render_markdown(s).split("Usage: unavailable")[1].split("\n")[0]
    m["usage"]["by_model"] = [{"input_tokens": 10, "output_tokens": 5, "calls": 1, "calls_without_usage": 0}]
    framework.write_json(run_dir / "manifest.json", m)
    assert summary.run_summary(run_dir, mode="run")["usage"] == {"unavailable": "usage.by_model row #0 lacks 'model'"}
    m["usage"]["by_model"] = [{"model": 7, "input_tokens": 10, "output_tokens": 5, "calls": 1, "calls_without_usage": 0}]
    framework.write_json(run_dir / "manifest.json", m)
    assert summary.run_summary(run_dir, mode="run")["usage"] == {"unavailable": "usage.by_model row #0 model is not a string"}


def test_incomplete_cost_sidecars_are_unavailable_not_tables_with_dashes(run_dir):
    """Codex (PR #27, eighth round)."""
    side = run_dir / "example.report.json"
    good = framework.load_json(side)
    del good["cost_usd"]
    framework.write_json(side, good)
    s = summary.run_summary(run_dir, mode="run")
    assert s["sidecar"] == {"path": "example.report.json", "unavailable": "example.report.json lacks 'cost_usd'"}
    assert "Target cost sidecar: unavailable (example.report.json lacks 'cost_usd')" in summary.render_markdown(s)
    good["cost_usd"] = "0.0"
    framework.write_json(side, good)
    assert summary.run_summary(run_dir, mode="run")["sidecar"]["unavailable"] == "example.report.json 'cost_usd' is not int or float (got str)"
    good["cost_usd"] = True
    framework.write_json(side, good)
    assert "is not int or float (got bool)" in summary.run_summary(run_dir, mode="run")["sidecar"]["unavailable"]
    side.write_text("[]", encoding="utf-8")
    assert summary.run_summary(run_dir, mode="run")["sidecar"]["unavailable"] == "example.report.json is not an object"
    judge_side = run_dir / "example.judge.report.json"
    framework.write_json(judge_side, {"judge_model": "claude-haiku-4-5", "cost_basis": "x", "billing_channel": "anthropic"})
    s = summary.run_summary(run_dir, mode="run")
    assert s["judge_sidecar"] == {"path": "example.judge.report.json", "unavailable": "example.judge.report.json lacks 'cost_usd'"}
    framework.write_json(judge_side, {"judge_model": "claude-haiku-4-5", "cost_usd": 0.01, "cost_basis": "x", "billing_channel": "anthropic",
                                      "max_spend_usd": 0.05, "price_source": "registry:anthropic", "input_per_mtok": 1.0, "output_per_mtok": 5.0})
    assert summary.run_summary(run_dir, mode="run")["judge_sidecar"]["cost_usd"] == 0.01


def test_judge_prompt_statistics_come_only_from_the_run_s_pinned_inputs(run_dir, monkeypatch):
    """Codex (PR #27, eighth round): a paid run's commit steps pull the branch
    before the summary, so the checkout can differ from the run's inputs."""
    m = framework.load_json(run_dir / "manifest.json")
    m["framework"]["outcome_registry_sha256"] = "f" * 64
    framework.write_json(run_dir / "manifest.json", m)
    jp = summary.run_summary(run_dir, mode="run", seeds_path=framework.SEED_FILE)["judge_prompts"]
    assert jp == {"unavailable": "the outcome registry in the checkout does not digest to the manifest's outcome_registry_sha256"}
    m["framework"]["outcome_registry_sha256"] = framework.sha256_file(framework.OUTCOME_REGISTRY)
    m["adapter"]["engine_sha"] = "a" * 40
    framework.write_json(run_dir / "manifest.json", m)
    # the comparison is blob-by-blob at the recorded commit, never HEAD against the sha (Codex, PR #27, ninth
    # round: a paid run's own commit steps move HEAD before the summary)
    monkeypatch.setattr(summary, "_blob_matches", lambda sha, path: path != framework.ADVICE_RUBRIC)
    jp = summary.run_summary(run_dir, mode="run", seeds_path=framework.SEED_FILE)["judge_prompts"]
    assert jp["unavailable"].startswith("rubric in the checkout differ from the run's engine commit aaaaaaaaaaaa")
    monkeypatch.setattr(summary, "_blob_matches", lambda sha, path: None)
    jp = summary.run_summary(run_dir, mode="run", seeds_path=framework.SEED_FILE)["judge_prompts"]
    assert "unavailable" in jp or jp["inputs"]["verified_against_engine_commit"] == {"seeds": None, "outcome_registry": None, "rubric": None}


def test_blob_matches_reads_the_file_at_the_recorded_commit(tmp_path):
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert summary._blob_matches(head, framework.OUTCOME_REGISTRY) is True, "the checkout matches its own HEAD"
    assert summary._blob_matches("0" * 40, framework.OUTCOME_REGISTRY) is None, "an unknown commit cannot be compared"
    assert summary._blob_matches(head, tmp_path / "outside.json") is None, "a path outside the repository cannot be compared"
    copy = ROOT / "docs" / "framework" / "_blob_probe.tmp.json"
    try:
        copy.write_text("{}", encoding="utf-8")
        assert summary._blob_matches(head, copy) is None, "a file the commit does not carry cannot be compared"
    finally:
        copy.unlink()


def test_judge_calls_appear_in_the_usage_table(run_dir):
    """Codex (PR #27, eighth round): the manifest's usage table is closed
    before the judge step, so every paid judge call was omitted."""
    rows = [{"method": "rule", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 0, "output_tokens": 0},
            {"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 100, "output_tokens": 20,
             "retry_attempts_charged": 0, "provider_attempts": 1},
            {"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 50, "output_tokens": 10,
             "retry_attempts_charged": 0, "provider_attempts": 1}]
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    usage = summary.run_summary(run_dir, mode="run")["usage"]
    judge = [r for r in usage if r.get("note", "").startswith("judge of record")]
    assert len(judge) == 1 and judge[0]["model"] == "claude-haiku-4-5" and judge[0]["calls"] == 2, "rule rows are not calls"
    assert judge[0]["input_tokens"] == 150 and judge[0]["output_tokens"] == 30 and judge[0]["status"] == summary.USAGE_PROVIDER_MEASURED
    assert [r["model"] for r in usage][0] == "mockllm/model", "the target rows stay first"
    rows.append({"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": True, "input_tokens": None, "output_tokens": None,
                 "retry_attempts_charged": 0, "provider_attempts": 1})
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r.get("note", "").startswith("judge of record")][0]
    assert judge["calls"] == 3 and judge["calls_without_usage"] == 1 and judge["status"] == summary.USAGE_UNAVAILABLE
    text = summary.render_markdown(summary.run_summary(run_dir, mode="run"))
    assert ("| claude-haiku-4-5 | 3 | 1 | 150 | 30 | **unavailable** (judge of record, aggregated from judgments.jsonl "
            "(3 judge row(s), 3 provider attempt(s))) |") in text
    (run_dir / "judgments.jsonl").write_text("{not json\n", encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "(judge of record)"][0]
    assert judge["status"] == summary.USAGE_UNAVAILABLE and "judgments.jsonl unreadable" in judge["note"]


def test_charged_judge_retries_count_as_calls_without_usage(run_dir):
    """Codex (PR #27, ninth round): a successful row after a charged failed
    attempt read as one fully metered call."""
    rows = [{"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 100, "output_tokens": 20,
             "retry_attempts_charged": 2, "provider_attempts": 3}]
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "claude-haiku-4-5"][0]
    assert judge["calls"] == 3 and judge["calls_without_usage"] == 2 and judge["status"] == summary.USAGE_UNAVAILABLE
    assert judge["input_tokens"] == 100 and judge["note"].endswith("(1 judge row(s), 3 provider attempt(s))")
    rows[0]["retry_attempts_charged"] = "2"
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "(judge of record)"][0]
    assert "'retry_attempts_charged' is not int" in judge["note"]


def test_a_gate_refused_judge_row_counts_its_charged_attempts_only(run_dir):
    """Independent review of PR #27: a row whose retry the ceiling refused
    records one charged attempt and no further request, but the summary
    derived `1 + retries` and reported two provider attempts, the same
    numbers as a row that really made two; the note also printed that
    attempt count as a row count. The row now carries `provider_attempts`
    and the summary reads it, checking it against the charged retries."""
    def judge_rows(*rows):
        (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] in ("claude-haiku-4-5", "(judge of record)")][0]

    refused = {"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": True, "input_tokens": None, "output_tokens": None,
               "retry_attempts_charged": 1, "provider_attempts": 1, "cost_basis": "imputed_worst_case:call_failed",
               "judge_error": "call failed: retry refused by the ceiling after 1 charged attempt(s): RuntimeError: transient 529"}
    judge = judge_rows(refused)
    assert judge["calls"] == 1 and judge["calls_without_usage"] == 1 and judge["status"] == summary.USAGE_UNAVAILABLE
    assert judge["note"].endswith("(1 judge row(s), 1 provider attempt(s))")
    exhausted = {**refused, "provider_attempts": 2, "judge_error": "call failed: RuntimeError: transient 529"}
    judge = judge_rows(exhausted)
    assert judge["calls"] == 2 and judge["calls_without_usage"] == 2, "a retry the provider received is a second attempt"
    judge = judge_rows(refused, exhausted)
    assert judge["calls"] == 3 and judge["calls_without_usage"] == 3 and judge["note"].endswith("(2 judge row(s), 3 provider attempt(s))")
    # a count that disagrees with the charged retries, or that is absent, is a named gap, never a derived number
    judge = judge_rows({**refused, "provider_attempts": 3})
    assert judge["model"] == "(judge of record)" and "'provider_attempts' 3 does not agree with 'retry_attempts_charged' 1" in judge["note"]
    judge = judge_rows({**refused, "provider_attempts": 0, "retry_attempts_charged": 0})
    assert judge["model"] == "(judge of record)" and "'provider_attempts' 0 does not agree" in judge["note"]
    judge = judge_rows({k: v for k, v in refused.items() if k != "provider_attempts"})
    assert judge["model"] == "(judge of record)" and "judgments.jsonl row #0 lacks 'provider_attempts'" in judge["note"]


def test_the_rendered_summary_passes_the_holdout_seal_before_it_is_printed(run_dir, monkeypatch, capsys, tmp_path):
    """Independent review of PR #27: the summary step is always(), so it runs
    after a rejected seal check too, and it prints manifest strings the seal
    never scanned (a refusal reason quotes Inspect's sample error); the job
    summary of a public repository is a publication like every file the
    lane commits. With --seal-scan the rendered text passes the same holdout
    seal, and a hit, an unchecked scan or a scan that fails withholds it."""
    from scripts.petri_audit import seal

    m = framework.load_json(run_dir / "manifest.json")
    m["integrity"]["records_refused"].append({"branch_id": "t1:root", "reason": "sample error: quoted holdout stimulus zq"})
    framework.write_json(run_dir / "manifest.json", m)
    argv = ["run-summary", "--run-dir", str(run_dir), "--mode", "dry_run", "--json-out", str(tmp_path / "s.json"), "--seal-scan"]
    monkeypatch.setattr(seal, "sealed_registry", lambda: {"quoted holdout stimulus zq": "batch#3"})
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert out.startswith("## Petri audit (dry_run, example): summary withheld") and "**fail**" in out
    assert "holdout stimulus" not in out and "batch#3" not in out and "Refusals" not in out, "the verdict alone: no phrase, no label, no data"
    assert (tmp_path / "s.json").is_file(), "the JSON stays available to the runner; it is not published"
    monkeypatch.setattr(seal, "sealed_registry", lambda: {})
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "summary withheld" in out and "**not_run**" in out, "an unchecked summary is not published either"
    monkeypatch.setattr(seal, "sealed_registry", lambda: (_ for _ in ()).throw(OSError("no dashboard")))
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "summary withheld" in out and "did not run (OSError: no dashboard)" in out, "a scan that fails to run fails closed"
    monkeypatch.setattr(seal, "sealed_registry", lambda: {"another phrase": "batch#4"})
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "summary withheld" not in out and "- t1:root: sample error: quoted holdout stimulus zq" in out, "a clean summary prints in full"
    # the render-failure fallback dumps the summary data, so it passes the gate too
    monkeypatch.setattr(seal, "sealed_registry", lambda: {"quoted holdout stimulus zq": "batch#3"})
    monkeypatch.setattr(summary, "render_markdown", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "summary withheld" in out and "holdout stimulus" not in out and "boom" not in out
    assert cli.main(argv[:-1]) == 0, "without the flag the fallback prints as before"
    assert "render failed: RuntimeError: boom" in capsys.readouterr().out


def test_a_judge_that_left_only_its_fallback_sidecar_is_reported_from_it(run_dir):
    """Codex (PR #27, ninth round): a judge that died before its first row
    leaves the workflow's fallback sidecar and no judgments.jsonl; that
    judge was omitted from the usage table."""
    framework.write_json(run_dir / "example.judge.report.json",
                         {"judge_model": "claude-haiku-4-5", "cost_usd": 0.01, "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar",
                          "billing_channel": "anthropic", "aborted": True, "max_spend_usd": 0.05, "price_source": "registry:anthropic", "input_per_mtok": 1.0, "output_per_mtok": 5.0})
    usage = summary.run_summary(run_dir, mode="run")["usage"]
    judge = [r for r in usage if r["model"] == "claude-haiku-4-5"]
    assert len(judge) == 1 and judge[0]["status"] == summary.USAGE_UNAVAILABLE and judge[0]["calls"] is None
    assert judge[0]["note"] == "judge of record: no judgments.jsonl; the judge sidecar books ceiling_imputed:judge_aborted_without_sidecar"
    (run_dir / "example.judge.report.json").write_text("[]", encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "(judge of record)"][0]
    assert "the judge sidecar is unavailable" in judge["note"]


def test_a_judgments_file_without_judge_rows_falls_back_to_the_sidecar(run_dir):
    """Codex (PR #27, tenth round): the judge loop opens judgments.jsonl before
    its first provider call, so a judge killed during that call leaves an
    empty file (or rule rows flushed earlier); the file's existence bypassed
    the sidecar fallback and the paid judge was omitted from the usage table."""
    def judge_rows():
        return [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] != "mockllm/model"]

    framework.write_json(run_dir / "example.judge.report.json",
                         {"judge_model": "claude-haiku-4-5", "cost_usd": 0.01, "cost_basis": "ceiling_imputed:judge_aborted_without_sidecar",
                          "billing_channel": "anthropic", "aborted": True, "max_spend_usd": 0.05, "price_source": "registry:anthropic", "input_per_mtok": 1.0, "output_per_mtok": 5.0})
    (run_dir / "judgments.jsonl").write_text("", encoding="utf-8")
    judge = judge_rows()
    assert len(judge) == 1 and judge[0]["model"] == "claude-haiku-4-5" and judge[0]["status"] == summary.USAGE_UNAVAILABLE
    assert judge[0]["calls"] is None, "no judge row: nothing is counted, the sidecar's ceiling is what is booked"
    assert judge[0]["note"] == ("judge of record: judgments.jsonl has no judge row (0 non-judge row(s)); the judge sidecar books "
                                "ceiling_imputed:judge_aborted_without_sidecar")
    rule = {"method": "rule", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 0, "output_tokens": 0}
    (run_dir / "judgments.jsonl").write_text(json.dumps(rule) + "\n" + json.dumps(rule) + "\n", encoding="utf-8")
    judge = judge_rows()
    assert len(judge) == 1 and "has no judge row (2 non-judge row(s))" in judge[0]["note"]
    assert "**unavailable**" in summary.render_markdown(summary.run_summary(run_dir, mode="run"))
    # a file with no judge row and no sidecar is a named gap: something ran the judge and nothing accounts for it
    (run_dir / "example.judge.report.json").unlink()
    judge = judge_rows()
    assert len(judge) == 1 and judge[0]["model"] == "(judge of record)" and judge[0]["note"].endswith("and no judge sidecar exists")
    # no file and no sidecar: nothing shows a judge ran, so there is no judge row to report
    (run_dir / "judgments.jsonl").unlink()
    assert judge_rows() == []


def test_negative_usage_counters_are_rejected_before_provenance(run_dir):
    """Codex (PR #27, tenth round): a schema-damaged manifest with
    `calls_without_usage: -1` or a negative token count passed the integer
    checks, `usage_is_missing` tests only `> 0`, and a priced row with
    negative measurements was labelled provider-measured."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(**counts):
        m = json.loads(json.dumps(base))
        m["usage"]["by_model"] = [{"model": "anthropic/claude-haiku-4-5", "calls": 3, "calls_without_usage": 0, "input_tokens": 120,
                                   "output_tokens": 30, **counts}]
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="run")["usage"]

    sound = damaged()
    assert sound[0]["status"] == summary.USAGE_PROVIDER_MEASURED, "the undamaged priced row is provider-measured"
    where = "usage.by_model row #0 ('anthropic/claude-haiku-4-5')"
    assert damaged(calls_without_usage=-1) == {"unavailable": f"{where} 'calls_without_usage' is negative (-1)"}
    assert damaged(calls=-1) == {"unavailable": f"{where} 'calls' is negative (-1)"}
    assert damaged(input_tokens=-5) == {"unavailable": f"{where} 'input_tokens' is negative (-5)"}
    assert damaged(output_tokens=-1) == {"unavailable": f"{where} 'output_tokens' is negative (-1)"}
    assert damaged(calls_without_usage=4) == {"unavailable": f"{where} 'calls_without_usage' 4 exceeds 'calls' 3"}
    assert damaged(calls=0, calls_without_usage=0, input_tokens=0, output_tokens=0)[0]["status"] == summary.USAGE_PROVIDER_MEASURED
    framework.write_json(run_dir / "manifest.json", base)
    # the same bound holds for judge rows read from judgments.jsonl
    row = {"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": -1, "output_tokens": 20,
           "retry_attempts_charged": 0, "provider_attempts": 1}
    (run_dir / "judgments.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "(judge of record)"][0]
    assert "judgments.jsonl row #0 'input_tokens' is negative (-1)" in judge["note"]


def test_a_judge_that_started_and_left_nothing_is_reported_from_its_marker(run_dir, tmp_path, capsys):
    """Codex (PR #27, eleventh round): a judge that died before opening
    judgments.jsonl, whose fallback sidecar was never written either, left no
    file, and the summary read the absence of both as proof that no judge
    ran; the workflow's judge-start marker is the evidence it ignored."""
    marker = tmp_path / "petri-run" / "judge_started"
    assert [r for r in summary.run_summary(run_dir, mode="run", judge_started=marker)["usage"] if r["model"] != "mockllm/model"] == [], \
        "no marker, no files: nothing shows a judge ran"
    marker.parent.mkdir()
    marker.write_text("", encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run", judge_started=marker)["usage"] if r["model"] != "mockllm/model"]
    assert len(judge) == 1 and judge[0]["model"] == "(judge of record)" and judge[0]["status"] == summary.USAGE_UNAVAILABLE
    assert judge[0]["note"] == "judge of record: no judgments.jsonl, the judge-start marker is set, and no judge sidecar exists"
    assert cli.main(["run-summary", "--run-dir", str(run_dir), "--mode", "run", "--judge-started-marker", str(marker)]) == 0
    assert "the judge-start marker is set" in capsys.readouterr().out


def test_by_role_counters_are_bounded_and_roles_unique(run_dir):
    """Codex (PR #27, eleventh round): `_bounded_counts` covered by_model and
    the judge rows but not the by_role target row the structure table reads,
    and a repeated `role` was silently the last row by list order."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(mutate):
        m = json.loads(json.dumps(base))
        mutate(m)
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="dry_run")["structure"]

    st = damaged(lambda m: m["usage"]["by_role"][0].__setitem__("calls", -1))
    assert st["target_calls"] is None and st["unavailable_fields"]["target_calls"] == "usage.by_role target row 'calls' is negative (-1)"
    st = damaged(lambda m: m["usage"]["by_role"][0].__setitem__("calls_without_usage", 9))
    assert st["target_calls"] is None and "'calls_without_usage' 9 exceeds 'calls'" in st["unavailable_fields"]["target_calls"]
    st = damaged(lambda m: m["usage"]["by_role"].append({**m["usage"]["by_role"][0], "calls": 99}))
    assert st["target_calls"] is None
    assert st["unavailable_fields"]["target_calls"] == "usage.by_role carries more than one 'target' row (#1 repeats an earlier one)"


def test_transcript_ids_are_matched_to_the_manifest_branches(run_dir):
    """Codex (PR #27, eleventh round): schema-valid records with ids the
    manifest's branches do not carry passed every per-record check and
    reported the expected count with no problem, while an analysis would
    join the wrong trajectories; the adapter lists a branch only after
    exporting its record, so the two id sets must be equal."""
    records = [json.loads(ln) for ln in (run_dir / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()]
    records[0]["conversation_id"] = "x" * 64
    (run_dir / "transcripts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["records"]["id_match"] == {"records_not_in_manifest": 1, "branches_without_record": 1, "duplicate_branch_ids": 0}
    assert any(p.startswith("record ids the manifest names no branch for: xxxxxxxxxxxx") for p in st["records"]["problems"])
    assert any(p.startswith("manifest branches with no exported record: ") for p in st["records"]["problems"])
    assert "| records vs manifest branches (not in manifest / without record) | " in summary.render_markdown(summary.run_summary(run_dir, mode="dry_run"))
    m = framework.load_json(run_dir / "manifest.json")
    del m["trees"]
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["records"]["id_match"] == {"unavailable": "manifest branches unavailable"}, "no branch set to compare with is a gap, not zero"


def test_the_redaction_report_is_validated_before_it_is_rendered(run_dir):
    """Codex (PR #27, eleventh round): a nonempty report missing a required
    counter, carrying a negative count or a mistyped boolean rendered as an
    ordinary measured table; the schema's closed set is enforced first."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(mutate):
        m = json.loads(json.dumps(base))
        mutate(m["artifacts"]["sanitiser"]["redaction_report"])
        framework.write_json(run_dir / "manifest.json", m)
        s = summary.run_summary(run_dir, mode="dry_run")
        return s["redaction"], summary.render_markdown(s)

    where = "artifacts.sanitiser.redaction_report"
    red, text = damaged(lambda r: r.pop("fields_removed"))
    assert red == {"unavailable": f"{where} lacks 'fields_removed'"} and f"Sanitiser redaction report: unavailable ({where} lacks" in text
    red, _ = damaged(lambda r: r.__setitem__("events_kept", -1))
    assert red == {"unavailable": f"{where} 'events_kept' is negative (-1)"}
    red, _ = damaged(lambda r: r.__setitem__("request_bodies_kept", "yes"))
    assert red == {"unavailable": f"{where} 'request_bodies_kept' is not bool (got str)"}
    red, _ = damaged(lambda r: r.__setitem__("headers_kept", True))
    assert red == {"unavailable": f"{where} 'headers_kept' must be False (got True)"}
    red, _ = damaged(lambda r: r.__setitem__("events_dropped_by_type", {"model": -2}))
    assert red == {"unavailable": f"{where} 'events_dropped_by_type'['model'] is negative (-2)"}
    red, _ = damaged(lambda r: r.__setitem__("extra", 1))
    assert red == {"unavailable": f"{where} carries unknown key(s) 'extra'"}
    red, _ = damaged(lambda r: r.__setitem__("samples", True))
    assert red == {"unavailable": f"{where} 'samples' is not int (got bool)"}
    red, text = damaged(lambda r: None)
    assert red == base["artifacts"]["sanitiser"]["redaction_report"] and "| fields_removed | 0 |" in text


def test_an_unknown_judgment_method_is_a_named_gap(run_dir):
    """Codex (PR #27, eleventh round): a row with `method: "judeg"` was
    skipped like a rule row, and its attempts and tokens vanished from a
    table that still carried a normal provenance status."""
    rows = [{"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 100, "output_tokens": 20,
             "retry_attempts_charged": 0, "provider_attempts": 1},
            {"method": "judeg", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 100, "output_tokens": 20,
             "retry_attempts_charged": 0, "provider_attempts": 1}]
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] != "mockllm/model"]
    assert len(judge) == 1 and judge[0]["model"] == "(judge of record)" and judge[0]["status"] == summary.USAGE_UNAVAILABLE
    assert "judgments.jsonl row #1 'method' 'judeg' is neither 'judge' nor 'rule'" in judge[0]["note"]


def test_every_contract_check_is_required_before_the_table_renders(run_dir):
    """Codex (PR #27, eleventh round): a nonempty block missing a required
    check rendered the remaining checks as a complete table."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(mutate):
        m = json.loads(json.dumps(base))
        mutate(m["execution"]["contract_checks"])
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="dry_run")["manifest"]["contract_checks"]

    where = "execution.contract_checks"
    assert damaged(lambda c: c.pop("holdout_seal")) == {"unavailable": f"{where} lacks 'holdout_seal'"}
    assert damaged(lambda c: c.__setitem__("extra_check", {"status": "pass", "detail": None})) == {"unavailable": f"{where} carries unknown key(s) 'extra_check'"}
    assert damaged(lambda c: c["holdout_seal"].__setitem__("status", "ok")) == \
        {"unavailable": f"{where}.holdout_seal 'status' 'ok' is not one of ['pass', 'fail', 'not_applicable', 'not_run']"}
    assert damaged(lambda c: c["no_cache"].pop("detail")) == {"unavailable": f"{where}.no_cache lacks 'detail'"}
    assert damaged(lambda c: c.__setitem__("no_prefill", "pass")) == {"unavailable": f"{where}.no_prefill is not an object"}
    assert damaged(lambda c: None) == base["execution"]["contract_checks"]
    text = summary.render_markdown(summary.run_summary(run_dir, mode="dry_run"))
    assert "| holdout_seal | " in text


def test_a_truncated_judge_sidecar_never_hides_the_target_usage(run_dir):
    """Codex (PR #27, eleventh round): a judge sidecar the non-atomic write
    left as invalid JSON raised out of the fallback, and the guard replaced
    the whole usage section, target rows included."""
    (run_dir / "example.judge.report.json").write_text('{"judge_model": "claude-haiku-4-5", "cost_usd": 0.0', encoding="utf-8")
    usage = summary.run_summary(run_dir, mode="run")["usage"]
    assert isinstance(usage, list) and usage[0]["model"] == "mockllm/model", "the target usage survives"
    judge = [r for r in usage if r["model"] == "(judge of record)"]
    assert len(judge) == 1 and "the judge sidecar is unavailable (Expecting" in judge[0]["note"]
    (run_dir / "example.report.json").write_text("{", encoding="utf-8")
    s = summary.run_summary(run_dir, mode="run")
    assert s["sidecar"]["path"] == "example.report.json" and s["sidecar"]["unavailable"].startswith("Expecting")


def test_the_no_manifest_summary_reports_usage_from_the_fallback_sidecar(tmp_path):
    """Codex (PR #27, twelfth round): a run that failed before its manifest
    leaves the workflow's fallback sidecar, whose `models` rows are the only
    per-model usage evidence, but the no-manifest summary showed a cost and
    no usage table at all."""
    from scripts.petri_audit.spend import write_report_sidecar

    run_dir = tmp_path / "run_x"
    run_dir.mkdir()
    s = summary.run_summary(run_dir, mode="run")
    assert s["manifest"] is None and s["usage"] == {"unavailable": "no manifest and no target cost sidecar: no usage evidence exists"}
    assert "Usage: unavailable (no manifest and no target cost sidecar" in summary.render_markdown(s)
    write_report_sidecar(run_dir / "run_x.report.json", run_id="run_x", eval_id="e", target="anthropic/claude-haiku-4-5",
                         model_usage={"anthropic/claude-haiku-4-5": {"input_tokens": None, "output_tokens": None, "calls": 2,
                                                                     "calls_without_usage": 2}},
                         max_spend_usd=0.05, judge_max_spend_usd=None, run_utc="2026-09-17T00:00:00Z")
    s = summary.run_summary(run_dir, mode="run")
    assert s["manifest"] is None and s["sidecar"]["cost_basis"] == "ceiling_imputed:usage_missing"
    assert [(r["model"], r["status"], r["calls"], r["calls_without_usage"]) for r in s["usage"]] == \
        [("anthropic/claude-haiku-4-5", summary.USAGE_UNAVAILABLE, 2, 2)]
    assert s["usage"][0]["note"] == "from the fallback sidecar run_x.report.json (no manifest)"
    text = summary.render_markdown(s)
    assert "No manifest (no adapted run)." in text and "| anthropic/claude-haiku-4-5 | 2 | 2 | — | — | **unavailable** (from the fallback" in text
    # the rows pass the same checks as the manifest's rows: a damaged row is a named gap, never a table
    side = framework.load_json(run_dir / "run_x.report.json")
    side["models"][0]["calls"] = -1
    framework.write_json(run_dir / "run_x.report.json", side)
    assert summary.run_summary(run_dir, mode="run")["usage"] == \
        {"unavailable": "run_x.report.json models #0 ('anthropic/claude-haiku-4-5') 'calls' is negative (-1)"}
    del side["models"]
    framework.write_json(run_dir / "run_x.report.json", side)
    assert summary.run_summary(run_dir, mode="run")["usage"] == {"unavailable": "run_x.report.json lacks a 'models' list"}
    assert summary.run_summary(None, mode="run")["usage"] == {"unavailable": "no run directory: no usage evidence exists"}


def test_artifact_families_are_bound_to_their_consumed_filenames(run_dir):
    """Codex (PR #27, twelfth round): `transcripts_path` sealed as
    `example/sanitised_log.json` with that file's digest verified while the
    `transcripts.jsonl` every consumer opens stayed unbound; the schema
    accepts any string path, so both verifiers now require the family's
    filename and unique paths."""
    m = framework.load_json(run_dir / "manifest.json")
    assert manifest_mod.verify_run(run_dir) == [] and manifest_mod.artifact_problems(m, run_dir.parent) == []
    m["artifacts"]["transcripts_path"] = m["artifacts"]["sanitised_log_path"]
    m["artifacts"]["transcripts_sha256"] = m["artifacts"]["sanitised_log_sha256"]
    framework.write_json(run_dir / "manifest.json", m)
    for problems in (manifest_mod.verify_run(run_dir), manifest_mod.artifact_problems(m, run_dir.parent)):
        assert "transcripts: recorded as sanitised_log.json, expected transcripts.jsonl" in problems
        assert "artifact path example/sanitised_log.json is recorded for more than one family: sanitised_log, transcripts" in problems
    assert manifest_mod.artifact_name_problems([("example/x.report.json", "d", "judge_of_record.report")]) == \
        ["judge_of_record.report: recorded as x.report.json, expected *.judge.report.json"]
    assert manifest_mod.artifact_name_problems([("example/example.judge.report.json", "d", "judge_of_record.report"), (None, None, "judgments")]) == []


def test_artifacts_are_bound_to_the_manifest_s_directory(run_dir, tmp_path):
    """Codex (PR #27, thirteenth round): a resealed manifest recording every
    artifact under another run directory, same basenames and matching
    digests, verified in the chain while the files beside it were unbound."""
    import shutil
    runs = tmp_path / "runs2"
    shutil.copytree(run_dir, runs / "example")
    shutil.copytree(run_dir, runs / "other")          # the same files under another run's directory
    m = framework.load_json(runs / "example" / "manifest.json")
    for fam in ("sanitised_log", "transcripts", "rule_outcomes"):
        m["artifacts"][f"{fam}_path"] = "other/" + Path(m["artifacts"][f"{fam}_path"]).name
    sealed = manifest_mod.seal_manifest(m, None)
    manifest_mod.write_manifest(runs / "example" / "manifest.json", sealed)
    manifest_mod.append_chain(runs, sealed, runs / "example" / "manifest.json")
    assert manifest_mod.artifact_problems(sealed, runs) == [], "basenames and digests alone accept the other run's files"
    problems = manifest_mod.artifact_problems(sealed, runs, manifest_dir="example")
    assert "sanitised_log: other/sanitised_log.json is recorded outside the manifest's directory example" in problems
    ok, msg = manifest_mod.verify_chain(runs)
    assert not ok and "recorded outside the manifest's directory example" in msg
    s = summary.run_summary(runs / "example", mode="dry_run")
    assert any("recorded outside" in p for p in s["integrity"]["artifact_problems"]) and s["integrity"]["chain"]["ok"] is False
    assert manifest_mod.verify_run(run_dir) == [] and manifest_mod.verify_chain(run_dir.parent)[0] is True, "the sound layout is unchanged"


def test_usage_provenance_is_bound_to_the_run_s_pricing_pin(run_dir, tmp_path):
    """Codex (PR #27, fourteenth round): the labels and price sources were
    resolved from whatever registry the summary ran against, although the
    manifest pins the digest of the registry the run was priced with and
    the sidecars retain the rates every call was charged at."""
    from scripts.petri_audit.spend import write_report_sidecar

    base = framework.load_json(run_dir / "manifest.json")
    assert base["usage"]["pricing_source_sha256"] == spend.pricing_source_digest()
    assert summary.run_summary(run_dir, mode="dry_run")["usage"][0]["status"] == summary.USAGE_MOCK

    def pinned(value):
        m = json.loads(json.dumps(base))
        m["usage"]["pricing_source_sha256"] = value
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="run")["usage"]

    u = pinned("f" * 64)
    assert u[0]["model"] == "mockllm/model" and u[0]["calls"] == base["usage"]["by_model"][0]["calls"], "the counts are measured"
    assert u[0]["status"] == summary.USAGE_UNAVAILABLE and u[0]["price_source"] is None
    assert u[0]["note"].startswith("price source not attributable: the pricing registry differs from the run's pin (pinned ffffffffffff, current ")
    u = pinned(None)
    assert u[0]["status"] == summary.USAGE_UNAVAILABLE and u[0]["price_source"] is None
    assert u[0]["note"] == "price source not attributable: manifest carries no pricing digest (usage.pricing_source_sha256)"
    assert "| mockllm/model | 3 | 0 | 120 | 90 | **unavailable** (price source not attributable" in summary.render_markdown(summary.run_summary(run_dir, mode="run"))
    framework.write_json(run_dir / "manifest.json", base)
    # the judge of record is priced from its sidecar's recorded rates, never re-resolved: zero rates under a pinned
    # source label the judge non-metered even though the registry prices that model
    rows = [{"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 100, "output_tokens": 20,
             "retry_attempts_charged": 0, "provider_attempts": 1}]
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    framework.write_json(run_dir / "example.judge.report.json",
                         {"judge_model": "claude-haiku-4-5", "cost_usd": 0.0, "cost_basis": "cumulative_from_records", "billing_channel": "anthropic",
                          "max_spend_usd": 0.05, "price_source": "pinned:test", "input_per_mtok": 0.0, "output_per_mtok": 0.0})
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "claude-haiku-4-5"][0]
    assert judge["status"] == summary.USAGE_MOCK and judge["price_source"] == "pinned:test"
    (run_dir / "judgments.jsonl").unlink()
    judge = [r for r in summary.run_summary(run_dir, mode="run")["usage"] if r["model"] == "claude-haiku-4-5"][0]
    assert judge["status"] == summary.USAGE_MOCK and judge["price_source"] == "pinned:test", "the sidecar-only row uses the same rates"
    # the no-manifest table takes each row's recorded source and rates from the fallback sidecar
    bare = tmp_path / "run_x"
    bare.mkdir()
    write_report_sidecar(bare / "run_x.report.json", run_id="run_x", eval_id="e", target="anthropic/claude-haiku-4-5",
                         model_usage={"anthropic/claude-haiku-4-5": {"input_tokens": 10, "output_tokens": 5, "calls": 1, "calls_without_usage": 0}},
                         max_spend_usd=0.05, judge_max_spend_usd=None, run_utc="2026-09-17T00:00:00Z")
    side = framework.load_json(bare / "run_x.report.json")
    side["models"][0].update({"price_source": "pinned:test", "input_per_mtok": 0.0, "output_per_mtok": 0.0})
    framework.write_json(bare / "run_x.report.json", side)
    row = summary.run_summary(bare, mode="run")["usage"][0]
    assert row["status"] == summary.USAGE_MOCK and row["price_source"] == "pinned:test"
    del side["models"][0]["price_source"]
    framework.write_json(bare / "run_x.report.json", side)
    assert summary.run_summary(bare, mode="run")["usage"] == {"unavailable": "run_x.report.json models #0 lacks 'price_source'"}


def test_judge_rows_survive_a_target_pricing_pin_mismatch(run_dir):
    """Codex (PR #27, fifteenth round): a target pricing-pin mismatch replaced
    the whole usage section, judge rows included, although the judge sidecar
    pins the judge's price on its own; and a judge without a sidecar cannot
    be priced from a registry that failed the pin."""
    rows = [{"method": "judge", "judge_model": "claude-haiku-4-5", "usage_missing": False, "input_tokens": 100, "output_tokens": 20,
             "retry_attempts_charged": 0, "provider_attempts": 1}]
    (run_dir / "judgments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    framework.write_json(run_dir / "example.judge.report.json",
                         {"judge_model": "claude-haiku-4-5", "cost_usd": 0.0, "cost_basis": "cumulative_from_records", "billing_channel": "anthropic",
                          "max_spend_usd": 0.05, "price_source": "pinned:test", "input_per_mtok": 0.0, "output_per_mtok": 0.0})
    m = framework.load_json(run_dir / "manifest.json")
    m["usage"]["pricing_source_sha256"] = "f" * 64
    framework.write_json(run_dir / "manifest.json", m)
    usage = summary.run_summary(run_dir, mode="run")["usage"]
    assert [r["model"] for r in usage] == ["mockllm/model", "claude-haiku-4-5"]
    assert usage[0]["status"] == summary.USAGE_UNAVAILABLE and usage[0]["price_source"] is None, "the target label is withheld"
    assert usage[1]["status"] == summary.USAGE_MOCK and usage[1]["price_source"] == "pinned:test" and usage[1]["calls"] == 1, \
        "the judge row stands on its sidecar's pinned rates"
    (run_dir / "example.judge.report.json").unlink()
    usage = summary.run_summary(run_dir, mode="run")["usage"]
    assert usage[1]["model"] == "claude-haiku-4-5" and usage[1]["calls"] == 1 and usage[1]["status"] == summary.USAGE_UNAVAILABLE
    assert usage[1]["price_source"] is None and "price source not attributable: the pricing registry differs" in usage[1]["note"], \
        "no recorded price and an unattributable registry: the counts stand, the label does not"


def test_fallback_rows_are_reconciled_with_their_missing_usage_declarations(tmp_path):
    """Codex (PR #27, fifteenth round): the no-manifest table read only the
    counters, so a sidecar row with complete counters beside
    `usage_missing: true` and a model named in `usage_missing_models` was
    labelled provider-measured while the same sidecar imputed the ceiling."""
    from scripts.petri_audit.spend import write_report_sidecar

    run_dir = tmp_path / "run_x"
    run_dir.mkdir()
    write_report_sidecar(run_dir / "run_x.report.json", run_id="run_x", eval_id="e", target="anthropic/claude-haiku-4-5",
                         model_usage={"anthropic/claude-haiku-4-5": {"input_tokens": None, "output_tokens": None, "calls": 2,
                                                                     "calls_without_usage": 2}},
                         max_spend_usd=0.05, judge_max_spend_usd=None, run_utc="2026-09-17T00:00:00Z")
    sound = framework.load_json(run_dir / "run_x.report.json")
    assert sound["usage_missing_models"] == ["anthropic/claude-haiku-4-5"] and sound["models"][0]["usage_missing"] is True
    assert summary.run_summary(run_dir, mode="run")["usage"][0]["status"] == summary.USAGE_UNAVAILABLE

    def damaged(mutate):
        side = json.loads(json.dumps(sound))
        mutate(side)
        framework.write_json(run_dir / "run_x.report.json", side)
        return summary.run_summary(run_dir, mode="run")["usage"]

    where = "run_x.report.json models #0"
    complete = {"input_tokens": 10, "output_tokens": 5, "calls": 2, "calls_without_usage": 0}
    assert damaged(lambda s: s["models"][0].update(complete)) == {"unavailable": f"{where} 'usage_missing' True disagrees with its counters"}
    assert damaged(lambda s: s["models"][0].update(usage_missing=False)) == \
        {"unavailable": f"{where} 'usage_missing' False disagrees with its counters"}
    assert damaged(lambda s: s.__setitem__("usage_missing_models", [])) == \
        {"unavailable": "run_x.report.json usage_missing_models names [] but the rows with missing usage are ['anthropic/claude-haiku-4-5']"}
    assert damaged(lambda s: s.__setitem__("usage_missing_models", "x")) == \
        {"unavailable": "run_x.report.json 'usage_missing_models' is not a list of strings"}
    assert damaged(lambda s: (s["models"][0].update(complete, usage_missing=False), s.__setitem__("usage_missing_models", [])))[0]["status"] \
        == summary.USAGE_PROVIDER_MEASURED, "consistent: labelled"
    assert damaged(lambda s: s["models"][0].__setitem__("input_per_mtok", -1)) == {"unavailable": f"{where} 'input_per_mtok' is negative (-1)"}


def test_usage_rows_are_reconciled_with_the_missing_model_list(run_dir):
    """Codex (PR #27, fourteenth round): a by_model row with usage beside a
    `usage_missing_models` entry naming the same model was labelled
    provider-measured while the sidecar imputed the ceiling from the
    declaration; the adapter derives the list from the rows, so they agree."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(rows=None, declared=None):
        m = json.loads(json.dumps(base))
        if rows is not None:
            m["usage"]["by_model"] = rows
        if declared is not None:
            m["usage"]["usage_missing_models"] = declared
        framework.write_json(run_dir / "manifest.json", m)
        return summary.run_summary(run_dir, mode="run")["usage"]

    assert damaged()[0]["status"] == summary.USAGE_MOCK
    assert damaged(declared=["mockllm/model"]) == \
        {"unavailable": "usage_missing_models names ['mockllm/model'] but the by_model rows with missing usage are []"}
    missing_row = dict(base["usage"]["by_model"][0], calls_without_usage=1)
    assert damaged(rows=[missing_row], declared=[]) == \
        {"unavailable": "usage_missing_models names [] but the by_model rows with missing usage are ['mockllm/model']"}
    assert damaged(rows=[missing_row], declared=["mockllm/model"])[0]["status"] == summary.USAGE_MOCK, "consistent: labelled"
    assert damaged(declared=[7]) == {"unavailable": "usage.usage_missing_models carries a non-string entry"}


def test_duplicate_branch_conversation_ids_are_reported(run_dir):
    """Codex (PR #27, twelfth round): two manifest branches sharing a
    conversation_id collapsed in the set comparison, so a single record
    could read as a clean match while the branches cannot be paired."""
    m = framework.load_json(run_dir / "manifest.json")
    branches = [b for t in m["trees"] for b in t["branches"]]
    first, second = branches[0]["conversation_id"], branches[1]["conversation_id"]
    branches[1]["conversation_id"] = first
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["records"]["id_match"] == {"records_not_in_manifest": 1, "branches_without_record": 0, "duplicate_branch_ids": 1}
    assert any(p.startswith(f"manifest branches sharing a conversation_id: {first[:12]}") for p in st["records"]["problems"])
    records = [json.loads(ln) for ln in (run_dir / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()]
    kept = [r for r in records if r["conversation_id"] != second]
    (run_dir / "transcripts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8")
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["records"]["id_match"] == {"records_not_in_manifest": 0, "branches_without_record": 0, "duplicate_branch_ids": 1}, \
        "both sides agree as sets; only the duplicate count says the pairing is broken"


def test_records_must_name_the_manifest_identity(run_dir):
    """Codex (PR #27, twelfth round): records carrying a valid but wrong
    `provenance.run_manifest.sha256` passed every check, so the summary
    reported zero problems for records bound to another run."""
    m = framework.load_json(run_dir / "manifest.json")
    records = [json.loads(ln) for ln in (run_dir / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["provenance"]["run_manifest"]["sha256"] == m["chain"]["identity_sha256"] for r in records)
    records[0]["provenance"]["run_manifest"]["sha256"] = "b" * 64
    records[1]["provenance"]["run_manifest"] = None
    (run_dir / "transcripts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["records"]["provenance_mismatches"] == 2 and st["records"]["with_problems"] == 2
    assert any("provenance names a different manifest identity (bbbbbbbbbbbb)" in p for p in st["records"]["problems"])
    assert any("provenance names no manifest identity" in p for p in st["records"]["problems"])
    assert "| records naming a different manifest identity | 2 |" in summary.render_markdown(summary.run_summary(run_dir, mode="dry_run"))
    del m["chain"]
    framework.write_json(run_dir / "manifest.json", m)
    st = summary.run_summary(run_dir, mode="dry_run")["structure"]
    assert st["records"]["provenance_mismatches"] == {"unavailable": "manifest carries no identity digest"}, "unknown identity: not passed"


def test_execution_limits_are_validated_before_rendering(run_dir):
    """Codex (PR #27, twelfth round): `epochs: -1` or `max_turns: "ten"` were
    published in the structure table as ordinary design measurements."""
    base = framework.load_json(run_dir / "manifest.json")

    def damaged(mutate):
        m = json.loads(json.dumps(base))
        mutate(m["execution"])
        framework.write_json(run_dir / "manifest.json", m)
        s = summary.run_summary(run_dir, mode="dry_run")
        return s["structure"], summary.render_markdown(s)

    st, text = damaged(lambda e: e.__setitem__("epochs", -1))
    assert st["epochs"] is None and st["unavailable_fields"]["epochs"] == "execution 'epochs' is below 1 (-1)" and "| epochs | — |" in text
    st, text = damaged(lambda e: e.__setitem__("max_turns", "ten"))
    assert st["max_turns"] is None and st["unavailable_fields"]["max_turns"] == "execution 'max_turns' is not int (got str)"
    assert "| max turns / tool rounds per turn | — / " in text
    st, _ = damaged(lambda e: e.pop("max_tool_rounds_per_turn"))
    assert st["max_tool_rounds_per_turn"] is None
    assert st["unavailable_fields"]["max_tool_rounds_per_turn"] == "execution lacks 'max_tool_rounds_per_turn'"
    st, _ = damaged(lambda e: e.__setitem__("epochs", True))
    assert st["epochs"] is None and st["unavailable_fields"]["epochs"] == "execution 'epochs' is not int (got bool)"
    st, _ = damaged(lambda e: None)
    assert st["epochs"] == base["execution"]["epochs"] and st["unavailable_fields"] == {}


def test_sidecar_spend_values_are_bounded(run_dir):
    """Codex (PR #27, twelfth round): a sidecar with `cost_usd: -1` or a
    non-positive ceiling passed the numeric type checks and rendered as an
    ordinary spend record; a sidecar may be the only spend evidence a failed
    run leaves."""
    side = framework.load_json(run_dir / "example.report.json")

    def target(**over):
        framework.write_json(run_dir / "example.report.json", {**side, **over})
        return summary.run_summary(run_dir, mode="dry_run")["sidecar"]

    assert target(cost_usd=-1)["unavailable"] == "example.report.json 'cost_usd' is negative (-1)"
    # Codex (PR #27, fourteenth round): a zero-priced dry run is admitted under `max_spend: "0"` and its sidecar records
    # that ceiling, so a zero target ceiling is a valid record; only a negative one is refused
    assert target(max_spend_usd=0)["max_spend_usd"] == 0 and "unavailable" not in target(max_spend_usd=0)
    assert target(max_spend_usd=-0.01)["unavailable"] == "example.report.json 'max_spend_usd' is negative (-0.01)"
    (run_dir / "example.report.json").write_text(json.dumps(side).replace('"cost_usd": 0.0', '"cost_usd": Infinity'), encoding="utf-8")
    assert summary.run_summary(run_dir, mode="dry_run")["sidecar"]["unavailable"] == "example.report.json 'cost_usd' is not finite (inf)"
    assert target()["cost_usd"] == 0.0, "the sound sidecar still reads"
    judge = {"judge_model": "claude-haiku-4-5", "cost_usd": -0.5, "cost_basis": "b", "billing_channel": "anthropic", "max_spend_usd": 0.05,
             "price_source": "registry:anthropic", "input_per_mtok": 1.0, "output_per_mtok": 5.0}
    framework.write_json(run_dir / "example.judge.report.json", judge)
    assert summary.run_summary(run_dir, mode="dry_run")["judge_sidecar"]["unavailable"] == "example.judge.report.json 'cost_usd' is negative (-0.5)"
    framework.write_json(run_dir / "example.judge.report.json", {**judge, "cost_usd": 0.0, "max_spend_usd": 0})
    assert summary.run_summary(run_dir, mode="dry_run")["judge_sidecar"]["unavailable"] == \
        "example.judge.report.json 'max_spend_usd' is not a positive ceiling (0)"
    # Codex (PR #27, thirteenth round): both judge-sidecar writers emit the ceiling, so a sidecar without it is damaged
    framework.write_json(run_dir / "example.judge.report.json", {k: v for k, v in judge.items() if k != "max_spend_usd"} | {"cost_usd": 0.0})
    assert summary.run_summary(run_dir, mode="dry_run")["judge_sidecar"]["unavailable"] == "example.judge.report.json lacks 'max_spend_usd'"
    framework.write_json(run_dir / "example.judge.report.json", {k: v for k, v in judge.items() if k != "input_per_mtok"} | {"cost_usd": 0.0})
    assert summary.run_summary(run_dir, mode="dry_run")["judge_sidecar"]["unavailable"] == "example.judge.report.json lacks 'input_per_mtok'"
    # Codex (PR #27, fifteenth round): the recorded rates label paid usage, so they are bounded like the spend values
    framework.write_json(run_dir / "example.judge.report.json", {**judge, "cost_usd": 0.0, "output_per_mtok": -5.0})
    assert summary.run_summary(run_dir, mode="dry_run")["judge_sidecar"]["unavailable"] == "example.judge.report.json 'output_per_mtok' is negative (-5.0)"
    (run_dir / "example.judge.report.json").write_text(json.dumps({**judge, "cost_usd": 0.0}).replace('"input_per_mtok": 1.0', '"input_per_mtok": Infinity'),
                                                        encoding="utf-8")
    assert summary.run_summary(run_dir, mode="dry_run")["judge_sidecar"]["unavailable"] == "example.judge.report.json 'input_per_mtok' is not finite (inf)"


def test_sidecars_are_found_by_pattern_after_a_flat_extraction(run_dir, tmp_path):
    """Codex (PR #27, ninth round): the sidecar name was rebuilt from the
    directory name, which a flat extraction does not preserve."""
    import shutil
    flat = tmp_path / "artifact-777"
    shutil.copytree(run_dir, flat)
    s = summary.run_summary(flat, mode="dry_run")
    assert s["sidecar"]["path"] == "example.report.json" and s["sidecar"]["cost_usd"] == 0.0
    framework.write_json(flat / "other.report.json", {"cost_usd": 0.0})
    s = summary.run_summary(flat, mode="dry_run")
    assert s["sidecar"]["unavailable"] == "2 target cost sidecars in the run directory"
    framework.write_json(flat / "example.judge.report.json", {"judge_model": "x", "cost_usd": 0.0, "cost_basis": "b", "billing_channel": "anthropic",
                                                              "max_spend_usd": 0.05, "price_source": "registry:anthropic", "input_per_mtok": 1.0, "output_per_mtok": 5.0})
    assert summary.run_summary(flat, mode="dry_run")["judge_sidecar"]["path"] == "example.judge.report.json"


def test_duplicate_conversation_ids_are_reported(run_dir):
    """Codex (PR #27, ninth round): a duplicate id overwrote the first
    record's diagnostics and counted as a clean record."""
    lines = (run_dir / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()
    (run_dir / "transcripts.jsonl").write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")
    rec = summary.run_summary(run_dir, mode="dry_run")["structure"]["records"]
    assert rec["count"] == len(lines) + 1 and rec["unique_conversation_ids"] == len(lines) and rec["with_problems"] == 1
    assert rec["problems"] == [f"record #{len(lines)} ({json.loads(lines[0])['conversation_id'][:12]}): duplicate conversation_id (identical record)"]
    conflicting = json.loads(lines[0])
    conflicting["turns"][0]["text"] = "edited"
    (run_dir / "transcripts.jsonl").write_text("\n".join(lines + [json.dumps(conflicting)]) + "\n", encoding="utf-8")
    rec = summary.run_summary(run_dir, mode="dry_run")["structure"]["records"]
    assert rec["with_problems"] == 1 and "duplicate conversation_id (conflicting record)" in rec["problems"][0]
    assert "text_sha256" in rec["problems"][0], "the record's own diagnostics are kept beside the duplicate"
    (run_dir / "transcripts.jsonl").write_text('{"turns": []}\n', encoding="utf-8")
    rec = summary.run_summary(run_dir, mode="dry_run")["structure"]["records"]
    assert rec["with_problems"] == 1 and "no conversation_id" in rec["problems"][0]


def test_an_empty_by_model_reports_the_missing_usage_instead_of_no_section(run_dir):
    """Codex (PR #27, fourth round): a run with samples but no target model
    event has an empty by_model while usage_missing_models names the target
    and the sidecar imputes the ceiling; the usage section was omitted."""
    m = framework.load_json(run_dir / "manifest.json")
    m["usage"]["by_model"] = []
    m["usage"]["usage_missing_models"] = ["anthropic/claude-haiku-4-5"]
    framework.write_json(run_dir / "manifest.json", m)
    s = summary.run_summary(run_dir, mode="run")
    assert len(s["usage"]) == 1 and s["usage"][0]["model"] == "anthropic/claude-haiku-4-5"
    assert s["usage"][0]["status"] == summary.USAGE_UNAVAILABLE and s["usage"][0]["calls"] is None
    assert "no usage row recorded" in s["usage"][0]["note"]
    text = summary.render_markdown(s)
    assert "| anthropic/claude-haiku-4-5 | — | — | — | — | **unavailable** (no usage row recorded" in text
    m["usage"]["usage_missing_models"] = []
    framework.write_json(run_dir / "manifest.json", m)
    s = summary.run_summary(run_dir, mode="run")
    assert s["usage"] == {"unavailable": "usage.by_model is empty and usage_missing_models names no model"}
    assert "Usage: unavailable (usage.by_model is empty" in summary.render_markdown(s)


def test_verify_run_checks_a_run_directory_on_its_own(run_dir, tmp_path, capsys):
    """Codex (PR #27): the exports artifact carried the cumulative chain
    file, which names every earlier committed run; a downloaded artifact
    could never pass verify-chain. verify-run needs no chain file."""
    assert manifest_mod.verify_run(run_dir) == []
    # the same directory copied elsewhere, without the chain file, verifies identically
    import shutil
    copy = tmp_path / "download" / run_dir.name
    shutil.copytree(run_dir, copy)
    assert not (copy.parent / manifest_mod.CHAIN_FILE).exists()
    assert manifest_mod.verify_run(copy) == []
    assert cli.main(["verify-run", "--run-dir", str(copy)]) == 0
    assert "verifies on its own" in capsys.readouterr().out
    # a flat extraction under any folder name (what upload-artifact produces: the archive is rooted at the run
    # directory, so the enclosing name is the downloader's choice) verifies too
    flat = tmp_path / "artifact-12345"
    shutil.copytree(run_dir, flat)
    assert flat.name != run_dir.name and manifest_mod.verify_run(flat) == []
    assert cli.main(["verify-run", "--run-dir", str(flat)]) == 0
    # a tampered artifact, a tampered manifest and a missing manifest all fail by name
    (copy / "transcripts.jsonl").write_text("edited\n", encoding="utf-8")
    assert any("transcripts" in p and "does not digest" in p for p in manifest_mod.verify_run(copy))
    m = framework.load_json(copy / "manifest.json")
    m["run_id"] = "rewritten"
    framework.write_json(copy / "manifest.json", m)
    assert any("manifest_sha256 does not match" in p for p in manifest_mod.verify_run(copy))
    (copy / "manifest.json").write_text("[1, 2]", encoding="utf-8")
    assert manifest_mod.verify_run(copy) == [f"{copy.name}: manifest.json holds a list, not an object"]
    assert cli.main(["verify-run", "--run-dir", str(copy)]) == 6
    # malformed nested objects are problems, never a traceback (Codex, PR #27, eighth round)
    good = framework.load_json(run_dir / "manifest.json")
    for field, bad in (("chain", [1]), ("artifacts", [1]), ("artifacts", {"transcripts_path": 7, "transcripts_sha256": "x"})):
        m = json.loads(json.dumps(good))
        m[field] = bad
        framework.write_json(copy / "manifest.json", m)
        problems = manifest_mod.verify_run(copy)
        assert problems and all(isinstance(p, str) for p in problems), (field, bad)
        assert cli.main(["verify-run", "--run-dir", str(copy)]) == 6
    assert any("chain is not an object" in p for p in manifest_mod.manifest_problems(dict(good, chain=[1])))
    assert any("artifacts is not an object" in p for p in manifest_mod.manifest_problems(dict(good, artifacts=[1])))
    (copy / "manifest.json").unlink()
    assert manifest_mod.verify_run(copy) == [f"{copy.name}: manifest.json is missing"]
    assert cli.main(["verify-run", "--run-dir", str(copy)]) == 6
    # artifacts recorded under two different run directories, or deeper than <run directory>/<file>, are refused
    m = framework.load_json(run_dir / "manifest.json")
    m["artifacts"]["transcripts_path"] = "elsewhere/transcripts.jsonl"
    other = tmp_path / "runs2" / run_dir.name
    shutil.copytree(run_dir, other)
    framework.write_json(other / "manifest.json", m)
    problems = manifest_mod.verify_run(other)
    assert any("more than one run directory" in p for p in problems), problems
    m["artifacts"]["transcripts_path"] = "example/nested/transcripts.jsonl"
    framework.write_json(other / "manifest.json", m)
    assert any("is not recorded as <run directory>/<file>" in p for p in manifest_mod.verify_run(other))
    # special components are refused even when they have two parts (Codex, PR #27, sixth round): `../x`, `/x`,
    # `./x`, and a backslash inside a component
    for bad in ("../transcripts.jsonl", "/transcripts.jsonl", "./transcripts.jsonl", "example\\transcripts.jsonl",
                "..\\transcripts.jsonl", "example/", "/example/transcripts.jsonl"):
        for fam in ("sanitised_log", "transcripts", "rule_outcomes"):
            m["artifacts"][f"{fam}_path"] = bad if fam == "transcripts" else f"example/{fam}.jsonl" if fam == "rule_outcomes" else "example/sanitised_log.json"
        framework.write_json(other / "manifest.json", m)
        problems = manifest_mod.verify_run(other)
        assert any(f"transcripts: {bad} is not recorded as <run directory>/<file>" in p for p in problems), (bad, problems)


def test_prompt_byte_stats_keep_the_numeric_median():
    """Codex (PR #27): `int(statistics.median(...))` truncated the half-byte
    median of an even count with middle values of different parity."""
    assert summary.byte_stats([1, 2]) == {"min": 1, "median": 1.5, "max": 2, "total": 3}
    assert summary.byte_stats([3, 1, 2]) == {"min": 1, "median": 2, "max": 3, "total": 6}
    assert summary.byte_stats([]) is None


def test_cli_run_summary_prints_markdown_writes_json_and_never_fails(run_dir, tmp_path, capsys):
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps({"mode": "dry_run", "target": "mockllm/model"}), encoding="utf-8")
    out = tmp_path / "summary.json"
    code = cli.main(["run-summary", "--run-dir", str(run_dir), "--mode", "dry_run", "--raw-eval-dir", str(tmp_path / "logs"),
                     "--params-file", str(params_file), "--json-out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert printed.startswith("## Petri audit (dry_run)") and "| target | mockllm/model |" in printed
    assert framework.load_json(out)["structure"]["trees"] == 1
    # an absent run directory under mode run is still a summary, not a failure
    assert cli.main(["run-summary", "--run-dir", str(tmp_path / "missing"), "--mode", "run"]) == 0
    assert "No manifest" in capsys.readouterr().out
