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

from scripts.petri_audit import cli, framework, summary, transcripts  # noqa: E402
from scripts.petri_audit import manifest as manifest_mod  # noqa: E402


def _record(conversation_id: str) -> dict:
    messages = [{"role": "user", "text": "u", "id": "m1"},
                {"role": "assistant", "text": "", "id": "m2",
                 "tool_calls": [{"call_id": "c1", "name": "lookup", "arguments": {"query": "q"}, "parse_error": None}]},
                {"role": "tool", "text": "RESULT", "id": "m3", "tool_call_id": "c1"},
                {"role": "assistant", "text": "final", "id": "m4"}]
    return transcripts.build_record(messages, conversation_id=conversation_id, source_system="inspect_petri",
                                    source_model="mockllm/model", model_version="mockllm", captured_utc="2026-09-16T00:00:00Z",
                                    user_is="unknown", import_utc="2026-09-16T00:00:00Z", importer_sha=None,
                                    run_manifest_sha256="a" * 64, run_manifest_ref=None)


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
    (d / "transcripts.jsonl").write_text("".join(json.dumps(_record(c)) + "\n" for c in conv_ids), encoding="utf-8")
    (d / "rule_outcomes.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "sanitised_log.json").write_text(json.dumps({"status": "success", "samples": []}), encoding="utf-8")
    for fam in ("sanitised_log", "transcripts", "rule_outcomes"):
        base["artifacts"][f"{fam}_sha256"] = framework.sha256_file(runs / base["artifacts"][f"{fam}_path"])
    raw = tmp_path / "logs"
    raw.mkdir()
    (raw / "run.eval").write_bytes(b"raw log bytes")
    base["artifacts"]["raw_eval_log_sha256"] = framework.sha256_file(raw / "run.eval")
    sealed = manifest_mod.seal_manifest(base, None)
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
    assert st["conditions"] == len({b["condition_id"] for t in m["trees"] for b in t["branches"]})
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
    assert s["sidecar"]["cost_usd"] == 0.0 and s["sidecar"]["billing_channel"] == "anthropic"
    assert s["judge_sidecar"] is None
    assert s["judge_prompts"] == {"unavailable": "no seed file given"}
    assert s["redaction"] == m["artifacts"]["sanitiser"]["redaction_report"]
    text = summary.render_markdown(s)
    for needle in ("Measured structure", "mock/non-metered", "Sanitised exports", "unresolved attachment:// references | 0",
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
