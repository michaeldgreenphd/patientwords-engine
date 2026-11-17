"""Lens-robustness exporter (scripts/export_jlens_loglens.py) - offline.

Pins the formation/class row build (reusing jlens_insights), the per-pair
Jacobian-vs-logit join and agreement counts, and the refusal when no logit-lens
run is committed (never publish an empty arm). Fake summaries only; no network.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_jlens_loglens", _ROOT / "scripts" / "export_jlens_loglens.py")
ext = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ext)

N = 6


def _prof(readable_layers):
    return [{"layer": layer, "target_rank": (1 if layer in readable_layers else None),
             "top1": "x"} for layer in range(N)]


def _result(idx, clin_layers, pat_layers, pat_final=None, target=" tgt"):
    pat = _prof(pat_layers)
    if pat_final is not None:
        pat[-1]["target_rank"] = pat_final
    return {"index": idx, "target_token": target,
            "depth": {"clinical": _prof(clin_layers), "patient": pat},
            "parse_status": {"clinical": "ok", "patient": "ok"}}


def test_row_from_result_hijack_and_capture():
    # clinical forms (2,3); patient forms (2,3) but not at the final layer -> hijack
    hij = ext.row_from_result(_result(1, {2, 3}, {2, 3}))
    assert hij["clin_formed"] == 2 and hij["pat_formed"] == 2
    assert hij["pat_final_rank"] is None and hij["class"] == "hijack"
    # clinical forms, patient never -> capture
    cap = ext.row_from_result(_result(2, {2, 3}, set()))
    assert cap["pat_formed"] is None and cap["class"] == "capture"


def test_row_from_result_held_and_unreadable():
    held = ext.row_from_result(_result(1, {2, 3}, {2, 3}, pat_final=1))
    assert held["class"] == "held"
    unreadable = ext.row_from_result(_result(2, set(), set()))
    assert unreadable["class"] == "unreadable"


def test_row_from_result_skips_bad_parse_and_empty_depth():
    bad = _result(1, {2, 3}, {2, 3})
    bad["parse_status"] = {"clinical": "ok", "patient": "unrecognized layer shape"}
    assert ext.row_from_result(bad) is None
    empty = {"index": 3, "depth": {"clinical": [], "patient": []},
             "parse_status": {"clinical": "ok", "patient": "ok"}}
    assert ext.row_from_result(empty) is None


def test_rows_from_summary_indexes():
    summary = {"results": [_result(1, {2, 3}, {2, 3}), _result(2, {2, 3}, set())]}
    rows = ext.rows_from_summary(summary)
    assert set(rows) == {1, 2}
    assert rows[2]["class"] == "capture"


def test_class_counts():
    rows = [{"class": "hijack"}, {"class": "hijack"}, {"class": "held"}]
    counts = ext.class_counts(rows)
    assert counts["hijack"] == 2 and counts["held"] == 1 and counts["capture"] == 0


def test_join_lenses_agreement_flags():
    jac = {1: {"pat_formed": 5, "class": "hijack", "target": "t"},
           2: {"pat_formed": None, "class": "capture", "target": "t"}}
    log = {1: {"pat_formed": 6, "class": "hijack", "target": "t"},   # agrees (both formed, same class)
           2: {"pat_formed": 4, "class": "hijack", "target": "t"}}   # disagrees on both
    per_pair = ext.join_lenses(jac, log)
    assert [p["index"] for p in per_pair] == [1, 2]
    assert per_pair[0]["class_agree"] and per_pair[0]["formed_agree"]
    assert not per_pair[1]["class_agree"] and not per_pair[1]["formed_agree"]
    ag = ext.summarize_agreement(per_pair)
    assert ag == {"n_paired": 2, "class_agree": 1, "formed_agree": 1}


def test_join_lenses_only_common_indices():
    jac = {1: {"pat_formed": 5, "class": "hijack", "target": "t"}}
    log = {2: {"pat_formed": 5, "class": "hijack", "target": "t"}}
    assert ext.join_lenses(jac, log) == []


def _write_summary(root, kind, model, batch, results, credit="credit-from-data"):
    d = root / f"{batch}__{kind}_{model}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "jlens_summary.part_01.json").write_text(
        json.dumps({"method_credit": credit, "results": results}),
        encoding="utf-8")


def test_build_payload_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "sealed_pair", lambda batch, index, prompt: False)
    root = tmp_path / "trace_out"
    results = [_result(1, {2, 3}, {2, 3}), _result(2, {2, 3}, set())]
    _write_summary(root, "jlens", "gemma-2-2b", "b", results)
    _write_summary(root, "loglens", "gemma-2-2b", "b", results)
    payload = ext.build_payload(str(root), "gemma-2-2b")
    assert payload is not None
    assert payload["agreement"]["n_paired"] == 2
    assert payload["agreement"]["class_agree"] == 2          # identical readouts -> full agreement
    assert payload["method_credit"] == "credit-from-data"
    assert payload["logit"]["class_counts"]["hijack"] == 1
    assert payload["logit"]["class_counts"]["capture"] == 1


def test_build_payload_distributions_over_common_pairs(tmp_path, monkeypatch):
    # jlens measured pairs 1,2; loglens only measured pair 1 -> both per-lens
    # distributions must cover just the common pair (1), never the unshared one.
    monkeypatch.setattr(ext, "sealed_pair", lambda batch, index, prompt: False)
    root = tmp_path / "trace_out"
    _write_summary(root, "jlens", "gemma-2-2b", "b",
                   [_result(1, {2, 3}, {2, 3}), _result(2, {2, 3}, set())])
    _write_summary(root, "loglens", "gemma-2-2b", "b", [_result(1, {2, 3}, {2, 3})])
    payload = ext.build_payload(str(root), "gemma-2-2b")
    assert payload["agreement"]["n_paired"] == 1
    assert payload["jacobian"]["formation"]["n"] == 1     # not 2: pair 2 excluded
    assert payload["logit"]["formation"]["n"] == 1


def test_build_payload_refuses_without_loglens(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "sealed_pair", lambda batch, index, prompt: False)
    root = tmp_path / "trace_out"
    _write_summary(root, "jlens", "gemma-2-2b", "b", [_result(1, {2, 3}, {2, 3})])
    assert ext.build_payload(str(root), "gemma-2-2b") is None      # no __loglens_ committed


def test_collect_rows_puts_each_rows_own_prompt_to_the_seal(tmp_path, monkeypatch):
    calls = []

    def seal(batch, index, prompt):
        calls.append((batch, index, prompt))
        return prompt == "CL-SEALED"
    monkeypatch.setattr(ext, "sealed_pair", seal)
    root = tmp_path / "trace_out"
    results = [dict(_result(1, {2, 3}, {2, 3}), prompts={"clinical": "CL-SEALED", "patient": "p"}),
               dict(_result(2, {2, 3}, set()), prompts={"clinical": "CL-KEPT", "patient": "p"})]
    _write_summary(root, "jlens", "gemma-2-2b", "b_txopus", results)
    rows = ext.collect_rows("jlens", "gemma-2-2b", str(root))
    assert sorted(calls) == [("b_txopus", 1, "CL-SEALED"), ("b_txopus", 2, "CL-KEPT")]
    assert set(rows["b_txopus"]) == {2}


def test_main_exit_2_when_seal_cannot_be_evaluated(tmp_path, monkeypatch, capsys):
    def seal(batch, index, prompt):
        raise ext.SealError("no tierb.start_utc")
    monkeypatch.setattr(ext, "sealed_pair", seal)
    root = tmp_path / "trace_out"
    _write_summary(root, "loglens", "gemma-2-2b", "b", [_result(1, {2, 3}, {2, 3})])
    out = tmp_path / "jlens_loglens.json"
    rc = ext.main(["--trace-root", str(root), "--out", str(out), "--site", ""])
    assert rc == 2
    printed = capsys.readouterr().out                 # the shared stop line (tierb_split.seal_config_error)
    assert "CONFIG ERROR" in printed and "not a refusal: stop the publish chain" in printed
    assert not out.exists()


def test_main_refuses_without_overwriting(tmp_path, capsys):
    out = tmp_path / "jlens_loglens.json"
    out.write_text('{"kept": 1}', encoding="utf-8")
    rc = ext.main(["--trace-root", str(tmp_path / "empty"), "--model", "gemma-2-2b",
                   "--out", str(out), "--site", ""])
    assert rc == 3
    assert "refused" in capsys.readouterr().out
    assert out.read_text() == '{"kept": 1}'


# --- hand-authored exploratory sets (agscen_; publication_hold.is_exploratory_run_dir) -------
EXPLORATORY = "agscen_20990101"


def _study_and_exploratory(root):
    """Study batch b: two pairs under both lenses. The exploratory set sorts before b,
    carries its own method_credit and three disagreeing pairs under both lenses, so
    reading it would change the batches, the counts, the agreement and the credit."""
    study = [_result(1, {2, 3}, {2, 3}), _result(2, {2, 3}, set())]
    _write_summary(root, "jlens", "gemma-2-2b", "b", study)
    _write_summary(root, "loglens", "gemma-2-2b", "b", study)
    _write_summary(root, "jlens", "gemma-2-2b", EXPLORATORY,
                   [_result(i, {2, 3}, set()) for i in (1, 2, 3)], credit="credit-from-agscen")
    _write_summary(root, "loglens", "gemma-2-2b", EXPLORATORY,
                   [_result(i, set(), set()) for i in (1, 2, 3)], credit="credit-from-agscen")


def test_build_payload_skips_an_exploratory_set_under_both_lenses(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "sealed_pair", lambda batch, index, prompt: False)
    root = tmp_path / "trace_out"
    _study_and_exploratory(root)
    skipped = []
    payload = ext.build_payload(str(root), "gemma-2-2b", skipped)
    assert payload["batches"] == ["b"]
    assert {p["batch"] for p in payload["per_pair"]} == {"b"}
    assert payload["agreement"] == {"n_paired": 2, "class_agree": 2, "formed_agree": 2}
    for lens in ("jacobian", "logit"):                         # pair 1 forms, pair 2 never does
        assert payload[lens]["formation"]["n"] == 1 and payload[lens]["never_formed"] == 1
    assert payload["method_credit"] == "credit-from-data"      # load_credit skips the set too
    assert "agscen" not in json.dumps(payload)
    assert sorted(Path(p).parent.name for p in skipped) == [
        f"{EXPLORATORY}__jlens_gemma-2-2b", f"{EXPLORATORY}__loglens_gemma-2-2b"]
    assert ext.collect_rows("loglens", "gemma-2-2b", str(root)).keys() == {"b"}   # no list needed


def test_main_prints_the_skip_and_writes_no_exploratory_row(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ext, "sealed_pair", lambda batch, index, prompt: False)
    root = tmp_path / "trace_out"
    _study_and_exploratory(root)
    out = tmp_path / "jlens_loglens.json"
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    assert ext.main(["--trace-root", str(root), "--out", str(out), "--site", str(site)]) == 0
    assert "2 exploratory-set part(s) not read" in capsys.readouterr().out
    for written in (out, site / "data" / "jlens_loglens.json"):
        text = written.read_text(encoding="utf-8")
        assert "agscen" not in text
        assert json.loads(text)["agreement"]["n_paired"] == 2


def test_main_refuses_when_the_only_logit_lens_run_is_exploratory(tmp_path, monkeypatch, capsys):
    # an exploratory logit-lens fire alone never becomes the robustness arm (exit 3, nothing written)
    monkeypatch.setattr(ext, "sealed_pair", lambda batch, index, prompt: False)
    root = tmp_path / "trace_out"
    _write_summary(root, "jlens", "gemma-2-2b", EXPLORATORY, [_result(1, {2, 3}, {2, 3})])
    _write_summary(root, "loglens", "gemma-2-2b", EXPLORATORY, [_result(1, {2, 3}, {2, 3})])
    out = tmp_path / "jlens_loglens.json"
    out.write_text('{"kept": 1}', encoding="utf-8")
    assert ext.main(["--trace-root", str(root), "--out", str(out), "--site", ""]) == 3
    printed = capsys.readouterr().out
    assert "1 exploratory-set part(s) not read" in printed and "refused" in printed
    assert out.read_text(encoding="utf-8") == '{"kept": 1}'
