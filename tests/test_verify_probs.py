"""Offline tests for the verification path's pure functions.

No torch, no interp-engine, no network: the measurement seam (``measure``) is
separate from the schema assembly, so everything here runs on stubs.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vp = _load("verify_probs")


class StubTokenizer:
    """Ids are 1-based word positions in a fixed abstract vocabulary."""

    VOCAB = ["<bos>", "alpha", "bravo", "charlie", "delta"]

    def __call__(self, text, add_special_tokens=True):
        ids = [self.VOCAB.index(w) for w in text.split() if w in self.VOCAB]
        if add_special_tokens:
            ids = [0] + ids

        class Out:
            input_ids = ids
        return Out()

    def decode(self, ids):
        return " ".join(self.VOCAB[int(i)] for i in ids)


class StubRow(list):
    """A 1-D torch row, as far as the code under test is concerned."""

    def tolist(self):
        return list(self)


class StubModel:
    """to_tokens mirrors the tokenizer unless told to diverge.

    Returns a batched [1, seq] shape with a `.tolist()`-able row, because that
    is what a real `to_tokens` returns and the parity check indexes it that way.
    """

    def __init__(self, tokenizer, drop_bos=False):
        self.tokenizer = tokenizer
        self.drop_bos = drop_bos

    def to_tokens(self, text):
        ids = self.tokenizer(text, add_special_tokens=True).input_ids
        if self.drop_bos:
            ids = ids[1:]
        return [StubRow(ids)]


PAIR = {"top_prompt": "alpha bravo", "bottom_prompt": "alpha charlie",
        "target_clinical_token": "delta"}


def fake_measure(probs):
    """measure_fn stub: clinical prompt gets probs[0], patient probs[1]."""
    def _m(prompt, target_id, topk):
        p = probs[0] if prompt == PAIR["top_prompt"] else probs[1]
        return p, [['Output " delta"', p]]
    return _m


def test_label_matches_the_graph_paths_format():
    assert vp.label(StubTokenizer(), 1) == 'Output "alpha"'


def test_token_parity_true_when_the_two_tokenizers_agree():
    tok = StubTokenizer()
    parity = vp.token_parity(StubModel(tok), tok, "alpha bravo")
    assert parity["match"] is True
    assert parity["n_engine"] == parity["n_hf"] == 3


def test_token_parity_false_and_lengths_recorded_when_they_diverge():
    """A BOS difference must surface as a parity failure, not as a small
    probability disagreement attributed to the engine."""
    tok = StubTokenizer()
    parity = vp.token_parity(StubModel(tok, drop_bos=True), tok, "alpha bravo")
    assert parity["match"] is False
    assert parity["n_engine"] == 2 and parity["n_hf"] == 3


def test_build_result_carries_the_penalty_and_the_parity_record():
    tok = StubTokenizer()
    model = StubModel(tok)
    r = vp.build_result(7, PAIR, model, tok, fake_measure((0.40, 0.25)), topk=1)
    assert r["index"] == 7
    assert r["probabilities"] == {"clinical": 0.40, "patient": 0.25}
    assert r["language_penalty"] == -0.15
    assert r["target_token"] == 'Output "delta"'
    assert r["token_parity"]["clinical"]["match"] is True
    assert r["token_parity"]["patient"]["match"] is True


def test_build_result_records_an_unmeasurable_target_without_crashing():
    tok = StubTokenizer()
    model = StubModel(tok)
    pair = dict(PAIR, target_clinical_token="   ")
    r = vp.build_result(1, pair, model, tok, fake_measure((0.4, 0.2)), topk=1)
    assert r["target_token"] is None
    assert r["probabilities"] == {"clinical": None, "patient": None}
    assert r["language_penalty"] is None
    # Parity is still recorded: the prompts were tokenized even if the target
    # was not measurable.
    assert r["token_parity"]["clinical"]["match"] is True


def test_summary_backend_is_distinct_from_hosted_and_logits():
    """Downstream behavioral collectors key off `backend`; a verification run
    must never look like a published measurement."""
    s = vp.build_summary("model-x", "org/model-x", [], dtype="float32")
    assert s["backend"] == "interp-engine"
    assert s["source_set"] is None
    assert s["inference"]["dtype"] == "float32"
    assert s["inference"]["device"] == "cpu"


def test_summary_filename_is_not_globbed_by_batch_summary_consumers(tmp_path):
    s = vp.build_summary("model-x", "org/model-x", [])
    path = vp.write_summary(tmp_path, s, start_index=1)
    assert path.name == "verify_summary.part_01.json"
    assert list(tmp_path.glob("batch_summary*.json")) == []
    assert json.loads(path.read_text())["backend"] == "interp-engine"


def test_chunk_offset_becomes_the_global_join_key(tmp_path):
    """A chunked run's filename and indices stay global, matching the trace
    path, so parts never clobber and the join key still works."""
    s = vp.build_summary("model-x", "org/model-x", [], start_index=51)
    path = vp.write_summary(tmp_path, s, start_index=51)
    assert path.name == "verify_summary.part_51.json"
    assert json.loads(path.read_text())["start_index"] == 51
