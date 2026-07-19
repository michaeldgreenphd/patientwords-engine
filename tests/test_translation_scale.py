"""translation_scale.py: self-contained, reproducible txcorpus recovery (offline)."""

import importlib.util
import json
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "translation_scale.py"
    spec = importlib.util.spec_from_file_location("translation_scale", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = _load()


def _tok(t):
    return f'Output "{t}"'


def _row(index, p_translated, p_patient, target, top_translated, top_patient):
    # clinical side = translated (top_prompt), patient side = patient (bottom_prompt)
    return {
        "index": index,
        "target_token": _tok(target),
        "probabilities": {"clinical": p_translated, "patient": p_patient},
        "predictive_spread": {
            "clinical": [[_tok(top_translated), p_translated]],
            "patient": [[_tok(top_patient), p_patient]],
        },
    }


def _setup(tmp_path):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    corpus = [
        {"top_prompt": "translated one", "bottom_prompt": "patient one",
         "target_clinical_token": " X", "generation": {"source_batch": "pairs_A", "source_index": 1}},
        {"top_prompt": "translated two", "bottom_prompt": "patient two",
         "target_clinical_token": " X", "generation": {"source_batch": "pairs_A", "source_index": 2}},
    ]
    (sim / "txcorpus_TEST.json").write_text(json.dumps(corpus))
    trace = tmp_path / "trace_out"
    mdir = trace / "txcorpus_TEST__gemma-3-4b-it"
    mdir.mkdir(parents=True)
    summary = {"backend": "logits", "results": [
        # recovery +0.40, translated restores the target top (patient top was Y)
        _row(1, 0.50, 0.10, "X", "X", "Y"),
        # recovery -0.10, translation LOSES the target top (patient had X)
        _row(2, 0.20, 0.30, "X", "Z", "X"),
    ]}
    (mdir / "batch_summary.part_01.json").write_text(json.dumps(summary))
    return trace, sim


def test_self_contained_recovery_counts_all_committed_rows(tmp_path):
    trace, sim = _setup(tmp_path)
    out = ts.analyze(trace, sim)
    m = out["per_model"]["gemma-3-4b-it"]
    assert m["n"] == 2                                    # no join drops rows
    assert m["family"] == "instruction-tuned"
    assert round(m["mean_recovery"], 4) == 0.15           # (0.40 + -0.10) / 2
    assert round(m["median_recovery"], 4) == 0.15
    assert m["share_recovery_positive"] == 0.5            # one of two positive
    assert m["n_with_headroom"] == 1                      # only the +0.40 row exceeds 1pp
    assert m["top_restored"] == 1                         # row 1
    assert m["top_lost"] == 1                             # row 2
    assert m["mean_gap_closed"] is None                   # undefined self-contained
    assert out["corpora"] == ["txcorpus_TEST"]            # only the measured stem


def test_recovery_uses_translated_minus_patient_not_a_cross_join(tmp_path):
    # A source-batch pairs_ run must NOT be needed or consulted: recovery is
    # p(target|translated) - p(target|patient) from the one txcorpus run.
    trace, sim = _setup(tmp_path)
    out = ts.analyze(trace, sim)
    # exact recovery of row 1 is clinical(0.50) - patient(0.10) = 0.40
    assert out["per_model"]["gemma-3-4b-it"]["n"] == 2
    src = (Path(__file__).resolve().parents[1] / "scripts" / "translation_scale.py").read_text()
    assert "no cross-join" in src            # methodology note pinned
    assert "p_translated - p_patient" in src  # the self-contained formula


def test_empty_when_no_corpus(tmp_path):
    (tmp_path / "data" / "simulated").mkdir(parents=True)
    (tmp_path / "trace_out").mkdir()
    out = ts.analyze(tmp_path / "trace_out", tmp_path / "data" / "simulated")
    assert out["per_model"] == {}
    assert out["corpora"] == []
