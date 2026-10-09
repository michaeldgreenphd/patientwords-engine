"""scripts/feature_label_calibration.py: label coverage and clinical_mass side by side, offline."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("feature_label_calibration",
                                               ROOT / "scripts" / "feature_label_calibration.py")
flc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(flc)


def cantor(layer: int, index: int) -> int:
    return (layer + index) * (layer + index + 1) // 2 + index


def _node(layer: int, index: int, ctx: int, category: str | None, description: str | None) -> dict[str, Any]:
    note: dict[str, Any] = {"category": category, "method": "keyword" if category == "clinical" else "default",
                            "matched_terms": []}
    if description is not None:
        note["description"] = description
    return {"node_id": f"{layer}_{index}_{ctx}", "feature": cantor(layer, index), "layer": str(layer),
            "ctx_idx": ctx, "feature_type": "cross layer transcoder", "medlang": note}


def _graph(model: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    structural = [{"node_id": "err_1_1", "feature_type": "mlp reconstruction error", "layer": "1",
                   "medlang": {"category": "structural"}}]
    return {"metadata": {"scan": model, "schema_version": 1}, "nodes": nodes + structural, "links": []}


def _row(index: int, prompt: str, clinical: float | None, patient: float | None) -> dict[str, Any]:
    return {"index": index, "prompts": {"clinical": prompt, "patient": prompt + " plain"},
            "clinical_mass": {"clinical": clinical, "patient": patient}}


def _trace_dir(root: Path, model: str, source_set: str | None, rows: list[dict[str, Any]],
               graphs: dict[str, dict[str, Any]] | None, complete: bool = True) -> Path:
    """A trace dir. With ``complete``, every (index, role) the rows report as traced and
    ``graphs`` does not name gets a graph with no feature nodes, so the set matches."""
    d = root / model
    d.mkdir(parents=True)
    (d / "batch_summary.part_01.json").write_text(json.dumps(
        {"graph_model": model, "source_set": source_set, "results": rows}), encoding="utf-8")
    if graphs is None:
        return d
    graphs = dict(graphs)
    if complete:
        for row in rows:
            for role in row.get("clinical_mass") or {}:
                graphs.setdefault(f"pair_{row['index']:02d}_{role}.tagged.json", _graph(model, []))
    for name, graph in graphs.items():
        # the tagger records the set its labels came from; a test that sets its own keeps it
        graph["metadata"].setdefault("medlang_summary", {"feature_source_set": source_set})
        (d / name).write_text(json.dumps(graph), encoding="utf-8")
    return d


@pytest.fixture
def two_models(tmp_path):
    a = _trace_dir(tmp_path, "gemma-2-2b", "gemmascope-transcoder-16k",
                   [_row(1, "p one", 0.30, 0.20), _row(2, "p two", 0.40, 0.10), _row(3, "p three", 0.5, 0.5)],
                   {"pair_01_clinical.tagged.json": _graph("gemma-2-2b", [
                       _node(3, 42, 1, "clinical", "long label | short"),
                       _node(3, 42, 2, "clinical", "long label | short"),   # same feature, second position
                       _node(7, 7, 2, "off_target", "other words here"),
                       _node(9, 1, 3, "off_target", "")]),
                    "pair_01_patient.tagged.json": _graph("gemma-2-2b", [
                       _node(5, 5, 1, "off_target", "plain label")])})
    b = _trace_dir(tmp_path, "qwen3-4b", "transcoder-hp",
                   [_row(1, "p one", 0.10, None), _row(2, "p two", 0.20, 0.05), _row(4, "p four", 0.9, 0.9),
                    _row(3, "a different prompt", 0.1, 0.1)],
                   {"pair_01_clinical.tagged.json": _graph("qwen3-4b", [
                       _node(10, 5, 1, "off_target", "bear"),
                       _node(11, 6, 1, "clinical", "word"),
                       _node(12, 7, 2, "off_target", ""),
                       _node(13, 8, 2, "off_target", "")])})
    return a, b


def test_label_coverage_and_clinical_share_per_model(two_models):
    a, b = two_models
    report = flc.build_report(a, b, examples=0)
    ma, mb = report["models"]["a"], report["models"]["b"]
    assert (ma["graph_model"], ma["source_set"]) == ("gemma-2-2b", "gemmascope-transcoder-16k")
    assert ma["tagged_graphs"] == 6                               # pairs 1-3, both sides
    assert ma["feature_nodes"]["n"] == 5                          # structural node excluded
    assert ma["feature_nodes"]["share_described"] == 0.8          # 4 of 5 nodes
    assert ma["feature_nodes"]["share_clinical"] == 0.4           # 2 of 5 nodes
    assert ma["feature_nodes"]["share_described_multi_explanation"] == 0.5   # 2 of 4 described
    assert ma["unique_features"] == {"n": 4, "share_described": 0.75, "share_clinical": 0.25}
    assert mb["feature_nodes"]["share_described"] == 0.5
    assert mb["feature_nodes"]["share_clinical"] == 0.25
    assert mb["feature_nodes"]["mean_description_words"] == 1.0
    assert mb["feature_nodes"]["methods"] == {"default": 3, "keyword": 1}


def test_clinical_mass_side_by_side_joins_identical_prompts_only(two_models):
    a, b = two_models
    pairs = flc.build_report(a, b, examples=0)["pairs"]
    assert pairs["n_joined"] == 2
    assert pairs["only_in_a"] == [] and pairs["only_in_b"] == [4]
    assert pairs["prompt_mismatch"] == [3]                         # listed, never merged
    clin = pairs["clinical_mass_side_by_side"]["clinical"]
    assert clin["a"]["mean"] == 0.35 and clin["b"]["mean"] == 0.15
    assert clin["n_both"] == 2 and clin["mean_difference_b_minus_a"] == -0.2
    pat = pairs["clinical_mass_side_by_side"]["patient"]
    assert pat["b"] == {"n": 1, "n_null": 1, "mean": 0.05, "median": 0.05, "min": 0.05, "max": 0.05}
    assert pat["n_both"] == 1                                      # the null is excluded, not read as 0
    assert pairs["rows"][0] == {"index": 1, "a_clinical": 0.3, "b_clinical": 0.1,
                                "a_patient": 0.2, "b_patient": None}


def test_per_model_distribution_counts_nulls(two_models):
    a, b = two_models
    mb = flc.build_report(a, b, examples=0)["models"]["b"]
    assert mb["clinical_mass"]["patient"]["n_null"] == 1
    assert mb["clinical_mass"]["clinical"]["n"] == 4
    assert mb["clinical_mass"]["clinical"]["q25"] == 0.1


def test_example_draw_is_seeded_and_recorded(two_models):
    a, b = two_models
    one = flc.build_report(a, b, examples=1, seed=3)
    two = flc.build_report(a, b, examples=1, seed=3)
    assert one == two and one["seed"] == 3 and one["examples_per_model"] == 1
    assert one["models"]["b"]["clinical_examples"] == [{"layer": 11, "index": 6, "description": "word"}]


def test_refuses_a_dir_without_tagged_graphs(tmp_path, capsys):
    a = _trace_dir(tmp_path, "gemma-2-2b", "gemmascope-transcoder-16k", [_row(1, "p", 0.3, 0.2)],
                   {"pair_01_clinical.tagged.json": _graph("gemma-2-2b", [_node(1, 1, 1, "clinical", "x")])})
    b = _trace_dir(tmp_path, "qwen3-4b", "transcoder-hp", [_row(1, "p", 0.1, 0.1)], None)
    with pytest.raises(flc.MissingTaggedGraphsError, match="workflow artifact"):
        flc.build_report(a, b)
    assert flc.main([str(a), str(b)]) == 2
    assert "refused: MissingTaggedGraphsError" in capsys.readouterr().err


def test_refuses_an_untagged_feature_node(tmp_path):
    bare = _node(1, 1, 1, "clinical", "x")
    del bare["medlang"]
    a = _trace_dir(tmp_path, "gemma-2-2b", "s", [_row(1, "p", 0.3, 0.2)],
                   {"pair_01_clinical.tagged.json": _graph("gemma-2-2b", [bare])})
    with pytest.raises(flc.UntaggedGraphError):
        flc.build_report(a, a)


def test_refuses_mixed_models_and_duplicate_indices(tmp_path):
    d = _trace_dir(tmp_path, "qwen3-4b", "transcoder-hp", [_row(1, "p", 0.1, 0.1)],
                   {"pair_01_clinical.tagged.json": _graph("qwen3-4b", [_node(1, 1, 1, "clinical", "x")])})
    (d / "batch_summary.part_02.json").write_text(json.dumps(
        {"graph_model": "qwen3-4b", "source_set": "transcoder-hp", "results": [_row(1, "p", 0.2, 0.2)]}),
        encoding="utf-8")
    with pytest.raises(flc.DuplicateIndexError):
        flc.build_report(d, d)
    (d / "batch_summary.part_02.json").write_text(json.dumps(
        {"graph_model": "qwen3-4b", "source_set": None, "results": [_row(2, "q", 0.2, 0.2)]}),
        encoding="utf-8")
    with pytest.raises(flc.MixedModelError):
        flc.build_report(d, d)


def test_null_source_set_is_reported_with_a_warning(tmp_path):
    d = _trace_dir(tmp_path, "qwen3-4b", None, [_row(1, "p", 0.0, 0.0)],
                   {"pair_01_clinical.tagged.json": _graph("qwen3-4b", [_node(1, 1, 1, "off_target", "")])})
    report = flc.build_report(d, d, examples=0)
    assert "NullFetcher" in report["models"]["a"]["warning"]


def test_main_writes_the_report(two_models, tmp_path, capsys):
    a, b = two_models
    out = tmp_path / "report.json"
    assert flc.main([str(a), str(b), "--out", str(out), "--examples", "2", "--seed", "11"]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["seed"] == 11 and report["rule"] == flc.REPORT_RULE
    assert "pairs joined 2" in capsys.readouterr().out


def test_refuses_a_tagged_graph_from_another_model(tmp_path):
    # Regression (Codex review of PR #93): a wrong artifact downloaded into a directory was
    # counted as that directory's model; metadata.scan must match the summaries' graph_model.
    gemma = _trace_dir(tmp_path, "gemma-2-2b", "gemmascope-transcoder-16k", [_row(1, "p", 0.3, 0.2)],
                       {"pair_01_clinical.tagged.json": _graph("gemma-2-2b", [_node(1, 1, 1, "clinical", "x")])})
    qwen = _trace_dir(tmp_path, "qwen3-4b", "transcoder-hp", [_row(1, "p", 0.1, 0.1)],
                      {"pair_01_clinical.tagged.json": _graph("gemma-2-2b", [_node(1, 1, 1, "clinical", "x")])})
    with pytest.raises(flc.GraphModelMismatchError, match="'gemma-2-2b'.*'qwen3-4b'"):
        flc.build_report(gemma, qwen)
    no_scan = _graph("qwen3-4b", [_node(1, 1, 1, "clinical", "x")])
    del no_scan["metadata"]["scan"]
    (qwen / "pair_01_clinical.tagged.json").write_text(json.dumps(no_scan), encoding="utf-8")
    with pytest.raises(flc.GraphModelMismatchError):
        flc.build_report(gemma, qwen)


def test_refuses_an_incomplete_or_foreign_set_of_tagged_graphs(tmp_path, capsys):
    # Regression (Codex review of PR #93): with one of a chunked run's offset artifacts
    # downloaded, label coverage came from one chunk while clinical_mass covered every
    # summary part. The graphs must be exactly the (index, role) pairs the summaries traced.
    rows = [_row(1, "p one", 0.3, 0.2), _row(2, "p two", 0.4, 0.1),
            {**_row(3, "p three", 0.5, None), "clinical_mass": {"clinical": 0.5}}]   # screened out
    chunk_one = {"pair_01_clinical.tagged.json": _graph("qwen3-4b", [_node(1, 1, 1, "clinical", "x")]),
                 "pair_01_patient.tagged.json": _graph("qwen3-4b", [])}
    partial = _trace_dir(tmp_path / "partial", "qwen3-4b", "transcoder-hp", rows, chunk_one, complete=False)
    with pytest.raises(flc.TaggedGraphSetMismatchError, match=r"Missing 3: 2/clinical, 2/patient, 3/clinical"):
        flc.build_report(partial, partial)
    assert flc.main([str(partial), str(partial)]) == 2
    assert "refused: TaggedGraphSetMismatchError" in capsys.readouterr().err
    # a screened-out pair needs no patient graph; with every expected graph present it passes
    full = _trace_dir(tmp_path / "full", "qwen3-4b", "transcoder-hp", rows, chunk_one)
    assert flc.build_report(full, full, examples=0)["models"]["a"]["tagged_graphs"] == 5
    # a graph no summary part accounts for (another chunk's artifact) is refused too
    (full / "pair_07_clinical.tagged.json").write_text(json.dumps(_graph("qwen3-4b", [])), encoding="utf-8")
    with pytest.raises(flc.TaggedGraphSetMismatchError, match=r"Not in any summary 1: 7/clinical"):
        flc.build_report(full, full)


def test_refuses_graphs_tagged_from_another_source_set(tmp_path):
    # Regression (Codex review of PR #93): a complete artifact of the same model and pairs
    # from another trace (an untagged NullFetcher run beside transcoder-hp summaries) passed
    # the scan and index/role checks. Each graph must record the summaries' source set.
    rows = [_row(1, "p", 0.1, 0.1)]
    stale = _graph("qwen3-4b", [_node(1, 1, 1, "off_target", "")])
    stale["metadata"]["medlang_summary"] = {"feature_source_set": None}       # NullFetcher-tagged
    d = _trace_dir(tmp_path / "stale", "qwen3-4b", "transcoder-hp", rows,
                   {"pair_01_clinical.tagged.json": stale})
    with pytest.raises(flc.TaggingSourceSetMismatchError, match="None.*'transcoder-hp'"):
        flc.build_report(d, d)
    legacy = _graph("qwen3-4b", [_node(1, 1, 1, "off_target", "")])
    legacy["metadata"]["medlang_summary"] = {"node_counts": {}}               # tagged before the field existed
    d2 = _trace_dir(tmp_path / "legacy", "qwen3-4b", "transcoder-hp", rows,
                    {"pair_01_clinical.tagged.json": legacy})
    with pytest.raises(flc.TaggingSourceSetMismatchError, match="records no"):
        flc.build_report(d2, d2)


def test_out_creates_a_missing_parent_directory(two_models, tmp_path):
    a, b = two_models
    out = tmp_path / "reports" / "nested" / "report.json"
    assert flc.main([str(a), str(b), "--out", str(out), "--examples", "0"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["pairs"]["n_joined"] == 2
