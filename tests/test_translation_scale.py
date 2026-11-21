"""translation_scale.py: recovery is the rewrite against the patient sentence, joined to the source pair's run.

Until 2026-11-20 the script read a txcorpus run's clinical side as the rewrite and its patient side as the
patient sentence. scripts/translate_corpus.py writes the opposite: top_prompt is the source pair's clinical
sentence and bottom_prompt is the rewrite. Every corpus row here is built by the writer's own function, so
the two scripts cannot disagree on the layout again without a failure in this file.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = _load("translation_scale")
tc = _load("translate_corpus")

SRC = "pairs_20260707T000000Z"       # before the Tier B start: sealed only through a registered phrase
TIERB = "pairs_20260711T000000Z"
HOLD = "The patient reports symptom 4."   # hashes holdout; tests/test_tierb_split.py pins it
EXPLORE = "The patient reports symptom 0."
MODEL = "gemma-3-4b-it"
CORPUS = "txcorpus_20260715T000000Z"


def _tok(t):
    return f'Output "{t}"'


def _pair(n, source_index=None, batch=SRC, clinical=None):
    """A corpus row as translate_corpus.py writes it, for source pair ``n`` and its rewrite."""
    item = {"top_prompt": clinical or f"clinical {n}", "patient_prompt": f"patient {n}",
            "target_clinical_token": " X", "source_batch": batch, "source_index": source_index or n}
    return tc.corpus_pair(item, f"rewrite {n}", "translator")


def _tx_row(index, pair, p_clinical, p_rewrite, top_rewrite="X", target="X"):
    """A txcorpus run row: its patient side is the corpus row's bottom_prompt, which is the rewrite."""
    return {"index": index, "target_token": _tok(target),
            "prompts": {"clinical": pair["top_prompt"], "patient": pair["bottom_prompt"]},
            "probabilities": {"clinical": p_clinical, "patient": p_rewrite},
            "predictive_spread": {"clinical": [[_tok("X"), p_clinical]], "patient": [[_tok(top_rewrite), p_rewrite]]}}


def _src_row(index, pair, p_clinical, p_patient, top_patient="X", target="X", patient=None):
    """The source pair's own run row: its patient side is the original patient sentence."""
    return {"index": index, "target_token": _tok(target),
            "prompts": {"clinical": pair["top_prompt"],
                        "patient": patient or pair["generation"]["original_patient"]},
            "probabilities": {"clinical": p_clinical, "patient": p_patient},
            "predictive_spread": {"clinical": [[_tok("X"), p_clinical]], "patient": [[_tok(top_patient), p_patient]]}}


def _part(trace, run_dir, rows, backend="logits", name="batch_summary.part_01.json"):
    d = trace / run_dir
    d.mkdir(parents=True, exist_ok=True)
    model = run_dir.partition("__")[2] or "gemma-2-2b"
    (d / name).write_text(json.dumps({"backend": backend, "graph_model": model, "results": rows}), encoding="utf-8")


def _tree(tmp_path, corpora, start="2026-07-10T01:14:38Z"):
    """(trace_out, simulated dir, dashboard) with the corpora written and a synthetic seal: one Tier B
    batch that registers HOLD, so the phrase set is not empty and the real sealed_pair can answer."""
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    for stem, pairs in corpora.items():
        (sim / f"{stem}.json").write_text(json.dumps(pairs), encoding="utf-8")
    (sim / f"{TIERB}.json").write_text(json.dumps([{"top_prompt": HOLD}, {"top_prompt": EXPLORE}]), encoding="utf-8")
    dash = tmp_path / "dashboard.json"
    dash.write_text(json.dumps({"tierb": {"start_utc": start}}), encoding="utf-8")
    trace = tmp_path / "trace_out"
    trace.mkdir()
    return trace, sim, dash


def test_recovery_is_the_rewrite_minus_the_patient_sentence_from_the_source_run(tmp_path):
    pairs = [_pair(1), _pair(2)]
    trace, sim, dash = _tree(tmp_path, {CORPUS: pairs})
    _part(trace, f"{CORPUS}__{MODEL}", [
        _tx_row(1, pairs[0], 0.60, 0.50),                      # the rewrite reaches 0.50
        _tx_row(2, pairs[1], 0.45, 0.20, top_rewrite="Z"),     # the rewrite reaches 0.20, top word leaves X
    ])
    _part(trace, f"{SRC}__{MODEL}", [
        _src_row(1, pairs[0], 0.60, 0.10, top_patient="Y"),    # patient wording: 0.10, top word Y
        _src_row(2, pairs[1], 0.45, 0.30),                     # patient wording: 0.30, top word X
    ])
    out = ts.analyze(trace, sim, dashboard_path=dash)
    m = out["per_model"][MODEL]
    assert m["n"] == 2
    assert m["family"] == "instruction-tuned" and m["backends"] == ["logits"]
    # +0.40 and -0.10. The retired reading (clinical side minus patient side of the txcorpus run) gives
    # +0.10 and +0.25: mean 0.175, both positive, and no top word restored.
    assert m["mean_recovery"] == 0.15 and m["median_recovery"] == 0.15
    assert m["share_recovery_positive"] == 0.5
    assert m["n_with_headroom"] == 1
    assert m["top_restored"] == 1 and m["top_lost"] == 1
    assert m["mean_gap"] == 0.325 and m["n_gap"] == 2           # (0.60 - 0.10 + 0.45 - 0.30) / 2
    assert m["mean_gap_closed"] is None
    assert out["corpora"] == [CORPUS]
    cov = out["coverage"][MODEL]
    assert (cov["rows"], cov["pairs"], cov["pairs_counted"], cov["not_counted"]) == (2, 2, 2, {})
    assert cov["rows_without_corpus_row"] == 0
    assert cov["clinical_side_between_runs"] == {"n": 2, "mean_diff": 0.0, "max_abs_diff": 0.0,
                                                 "n_abs_diff_over_1pp": 0}


def test_the_baseline_is_the_source_run_of_the_same_backend(tmp_path):
    # gemma-2-2b has a hosted run and a CPU logits run of the same source batch. A hosted txcorpus row is
    # set against the hosted one; before the backend was part of the key the logits part overwrote it.
    pairs = [_pair(1)]
    trace, sim, dash = _tree(tmp_path, {CORPUS: pairs})
    _part(trace, CORPUS, [_tx_row(1, pairs[0], 0.60, 0.50)], backend="hosted")
    _part(trace, SRC, [_src_row(1, pairs[0], 0.62, 0.10)], backend="hosted")
    _part(trace, f"{SRC}__gemma-2-2b", [_src_row(1, pairs[0], 0.60, 0.30)])
    out = ts.analyze(trace, sim, dashboard_path=dash)
    m = out["per_model"]["gemma-2-2b"]
    assert m["backends"] == ["hosted"]
    assert m["mean_recovery"] == 0.4                            # 0.50 - 0.10, not 0.50 - 0.30
    # the two hosted runs read the identical clinical sentence at 0.60 and 0.62, and that is recorded
    assert out["coverage"]["gemma-2-2b"]["clinical_side_between_runs"] == {
        "n": 1, "mean_diff": -0.02, "max_abs_diff": 0.02, "n_abs_diff_over_1pp": 1}


def test_a_pair_that_is_not_counted_is_recorded_with_its_reason(tmp_path):
    pairs = [_pair(n) for n in range(1, 7)]
    trace, sim, dash = _tree(tmp_path, {CORPUS: pairs})
    _part(trace, f"{CORPUS}__{MODEL}", [
        _tx_row(1, pairs[0], 0.60, 0.50),
        _tx_row(2, pairs[1], 0.60, None),                       # the rewrite's probability was not recorded
        _tx_row(3, pairs[2], 0.60, 0.50),                       # no source row landed
        _tx_row(4, pairs[3], 0.60, 0.50),                       # the source run read another patient sentence
        _tx_row(5, pairs[4], 0.60, 0.50),                       # the source run scored another target
        _tx_row(6, pairs[5], 0.60, 0.50),                       # the source run has no patient probability
        {**_tx_row(7, pairs[0], 0.60, 0.50)},                   # a row past the end of the corpus
    ])
    _part(trace, f"{SRC}__{MODEL}", [
        _src_row(1, pairs[0], 0.60, 0.10),
        _src_row(2, pairs[1], 0.60, 0.10),
        _src_row(4, pairs[3], 0.60, 0.10, patient="another patient sentence"),
        _src_row(5, pairs[4], 0.60, 0.10, target="W"),
        _src_row(6, pairs[5], 0.60, None),
    ])
    # a model whose txcorpus rows have no source run at all: listed in coverage, absent from per_model
    _part(trace, f"{CORPUS}__qwen3-1.7b", [_tx_row(1, pairs[0], 0.60, 0.50)])
    out = ts.analyze(trace, sim, dashboard_path=dash)
    assert out["per_model"][MODEL]["n"] == 1 and out["per_model"][MODEL]["mean_recovery"] == 0.4
    cov = out["coverage"][MODEL]
    assert (cov["rows"], cov["rows_without_corpus_row"], cov["pairs"], cov["pairs_counted"]) == (7, 1, 6, 1)
    assert cov["not_counted"] == {"patient_probability_missing": 1, "rewrite_probability_missing": 1,
                                  "sentence_mismatch": 1, "source_row_not_landed": 1, "target_mismatch": 1}
    assert "qwen3-1.7b" not in out["per_model"]
    assert out["coverage"]["qwen3-1.7b"] == {
        "rows": 1, "rows_without_corpus_row": 0, "pairs": 1, "pairs_counted": 0,
        "not_counted": {"source_row_not_landed": 1}, "clinical_side_between_runs": None}


def test_a_pair_in_two_corpora_is_counted_once(tmp_path):
    # The two priority corpora hold the same source pairs in another order. One model measured on both
    # contributes each pair once; a first row that cannot be counted does not hide a later one that can.
    first, second = "txcorpus_a_20260715T000000Z", "txcorpus_b_20260715T000000Z"
    trace, sim, dash = _tree(tmp_path, {first: [_pair(1), _pair(2)], second: [_pair(2), _pair(1)]})
    one, two = _pair(1), _pair(2)
    _part(trace, f"{first}__{MODEL}", [_tx_row(1, one, 0.60, 0.50), _tx_row(2, two, 0.60, None)])
    _part(trace, f"{second}__{MODEL}", [_tx_row(1, two, 0.60, 0.20), _tx_row(2, one, 0.60, 0.50)])
    _part(trace, f"{SRC}__{MODEL}", [_src_row(1, one, 0.60, 0.10), _src_row(2, two, 0.60, 0.30)])
    out = ts.analyze(trace, sim, dashboard_path=dash)
    m = out["per_model"][MODEL]
    assert m["n"] == 2 and m["mean_recovery"] == 0.15           # +0.40 once, -0.10 from the second corpus
    cov = out["coverage"][MODEL]
    assert (cov["rows"], cov["pairs"], cov["pairs_counted"], cov["not_counted"]) == (4, 2, 2, {})
    assert out["corpora"] == [first, second]


def _lens(trace, stem, rows):
    d = trace / f"{stem}__jlens_gemma-2-2b"
    d.mkdir(parents=True, exist_ok=True)
    results = [{"index": i, "parse_status": {"clinical": "ok", "patient": "ok"},
                "depth": {"patient": [{"layer": n, "target_rank": r} for n, r in enumerate(ranks)]}}
               for i, ranks in rows.items()]
    (d / "jlens_summary.part_01.json").write_text(json.dumps({"results": results}), encoding="utf-8")


FORMS, NEVER = [None, 2, 2, 1], [None, None, 5, None]


def test_lens_recovery_counts_each_source_pair_once(tmp_path):
    # Both priority corpora have a lens pull. Before 2026-11-20 a pair read in both was counted twice
    # (704 pairings from 352 source pairs on the landed data).
    first, second = "txcorpus_a_20260715T000000Z", "txcorpus_b_20260715T000000Z"
    trace, sim, dash = _tree(tmp_path, {first: [_pair(1), _pair(2)], second: [_pair(2), _pair(1)]})
    _lens(trace, SRC, {1: NEVER, 2: FORMS})
    _lens(trace, first, {1: FORMS, 2: NEVER})                   # pair 1 recovered, pair 2 lost
    _lens(trace, second, {1: NEVER, 2: NEVER})                  # pair 2 again (agrees), pair 1 again (disagrees)
    out = ts.lens_recovery(trace, sim, dashboard_path=dash)
    assert out["n_paired"] == 2
    assert (out["patient_never_formed"], out["recovered_to_formed"]) == (1, 1)
    assert (out["formed_both"], out["lost_by_translation"]) == (0, 1)
    assert (out["repeat_readouts"], out["repeat_readouts_disagreeing"]) == (2, 1)
    assert out["sealed_holdout"] == 0


def test_a_sealed_source_pair_is_never_read_into_the_aggregate(tmp_path):
    # A corpus row whose clinical sentence is a registered holdout phrase is sealed wherever it sits
    # (Amendment 3). The committed corpora hold none; the join reads source runs, so it asks every time.
    pairs = [_pair(1), _pair(2, clinical=HOLD)]
    trace, sim, dash = _tree(tmp_path, {CORPUS: pairs})
    _part(trace, f"{CORPUS}__{MODEL}", [_tx_row(1, pairs[0], 0.60, 0.50), _tx_row(2, pairs[1], 0.60, 0.50)])
    _part(trace, f"{SRC}__{MODEL}", [_src_row(1, pairs[0], 0.60, 0.10), _src_row(2, pairs[1], 0.60, 0.10)])
    _lens(trace, SRC, {1: NEVER, 2: NEVER})
    _lens(trace, CORPUS, {1: FORMS, 2: FORMS})
    out = ts.analyze(trace, sim, dashboard_path=dash)
    assert out["per_model"][MODEL]["n"] == 1
    assert out["coverage"][MODEL]["not_counted"] == {"sealed_holdout": 1}
    lens = ts.lens_recovery(trace, sim, dashboard_path=dash)
    assert (lens["n_paired"], lens["sealed_holdout"]) == (1, 1)


def test_a_seal_that_cannot_be_evaluated_stops_the_run_before_anything_is_written(tmp_path, monkeypatch, capsys):
    pairs = [_pair(1)]
    trace, sim, dash = _tree(tmp_path, {CORPUS: pairs}, start=None)
    _part(trace, CORPUS, [_tx_row(1, pairs[0], 0.60, 0.50)], backend="hosted")
    _part(trace, SRC, [_src_row(1, pairs[0], 0.60, 0.10)], backend="hosted")
    with pytest.raises(ts.SealError):
        ts.analyze(trace, sim, dashboard_path=dash)
    out = tmp_path / "translation_scale.json"
    monkeypatch.setattr(sys, "argv", ["translation_scale.py", "--trace-root", str(trace), "--simulated-dir", str(sim),
                                      "--dashboard", str(dash), "--out", str(out)])
    assert ts.main() == 2
    assert "CONFIG ERROR" in capsys.readouterr().out
    assert not out.exists()


def test_empty_when_no_corpus(tmp_path):
    (tmp_path / "data" / "simulated").mkdir(parents=True)
    (tmp_path / "trace_out").mkdir()
    out = ts.analyze(tmp_path / "trace_out", tmp_path / "data" / "simulated")
    assert out["per_model"] == {}
    assert out["corpora"] == []


def test_every_active_logits_model_has_a_family():
    # Gemini review of PR #94: a model missing from MODEL_FAMILY renders as "other" with no error, and the three
    # 2026-10-09 additions had no test, so a reverted or mistyped entry would have passed.
    le = _load("logits_eval")
    active = set(le.HF_IDS) - set(le.TOMBSTONES)
    assert sorted(active - set(ts.MODEL_FAMILY)) == []
    assert {m: ts.MODEL_FAMILY[m] for m in ("gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it")} == {
        "gemma-4-e2b": "base", "qwen3.5-2b-base": "base", "medgemma-1.5-4b-it": "medical"}
