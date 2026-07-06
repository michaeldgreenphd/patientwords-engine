import json

import pytest

from medlang_circuits import evaluate_models as em


@pytest.fixture
def pairs_file(tmp_path):
    # abstract stand-ins: the scoring logic is domain-agnostic
    data = {
        "translation": [
            {"patient": "phrase one", "expected": ["alpha"]},
            {"patient": "phrase two", "expected": ["beta", "gamma"]},
            {"patient": "phrase three", "expected": ["delta"]},
        ],
        "classification": [
            {"text": "desc one", "label": "clinical"},
            {"text": "desc two", "label": "structural"},
        ],
    }
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _patch_call(monkeypatch, responses, in_tok=100, out_tok=20):
    """responses: dict keyed by prompt substring -> reply text; default 'miss'."""
    calls = []

    def fake_call(client, model, system, prompt, max_tokens=em.MAX_OUTPUT_TOKENS):
        calls.append((model, prompt))
        reply = next((v for k, v in responses.items() if k in prompt), "miss")
        return reply, in_tok, out_tok

    monkeypatch.setattr(em, "_call", fake_call)
    return calls


def test_accuracy_and_outputs(monkeypatch, pairs_file, tmp_path):
    # model nails pair one (Alpha, case-insensitive) and pair two, misses three;
    # gets one of two classifications right
    _patch_call(monkeypatch, {
        "phrase one": "the Alpha term",
        "phrase two": "some gamma phrasing",
        "desc one": "clinical",
        "desc two": "off_target",
    })
    results = em.run_evaluation(
        ["claude-haiku-4-5"], scenario="both", sample_size=5,
        max_spend=5.0, pairs_path=pairs_file, out_dir=tmp_path / "out", client=object(),
    )
    block = results["by_model"]["claude-haiku-4-5"]
    assert block["translation"]["hits"] == 2 and block["translation"]["attempted"] == 3
    assert block["translation"]["accuracy"] == pytest.approx(2 / 3)
    assert block["classification"]["accuracy"] == pytest.approx(0.5)
    # both artifacts written; summary carries the accuracy table
    saved = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert saved["usage"]["total_cost_usd"] == results["usage"]["total_cost_usd"]
    summary = (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")
    assert "claude-haiku-4-5" in summary and "67% (2/3)" in summary


def test_cost_math(monkeypatch, pairs_file, tmp_path):
    # haiku: $1/MTok in, $5/MTok out; 5 calls x (100 in + 20 out)
    _patch_call(monkeypatch, {}, in_tok=100, out_tok=20)
    results = em.run_evaluation(
        ["claude-haiku-4-5"], scenario="both", sample_size=5,
        max_spend=5.0, pairs_path=pairs_file, out_dir=tmp_path / "out", client=object(),
    )
    per_call = 100 * 1.0 / 1e6 + 20 * 5.0 / 1e6
    assert results["usage"]["total_cost_usd"] == pytest.approx(5 * per_call)
    stats = results["usage"]["per_model"]["claude-haiku-4-5"]
    assert stats["calls"] == 5 and stats["input_tokens"] == 500 and stats["output_tokens"] == 100
    assert not results["usage"]["truncated_by_budget"]


def test_budget_exhaustion_truncates(monkeypatch, pairs_file, tmp_path):
    # worst case per haiku call = 500*1/1e6 + 200*5/1e6 = $0.0015; budget allows ~1 call
    _patch_call(monkeypatch, {}, in_tok=400, out_tok=150)
    results = em.run_evaluation(
        ["claude-haiku-4-5"], scenario="translation", sample_size=3,
        max_spend=0.002, pairs_path=pairs_file, out_dir=tmp_path / "out", client=object(),
    )
    block = results["by_model"]["claude-haiku-4-5"]["translation"]
    assert results["usage"]["truncated_by_budget"]
    assert block["attempted"] == 1 and block["skipped_for_budget"] == 2
    assert results["usage"]["total_cost_usd"] <= 0.002
    summary = (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")
    assert "truncated" in summary and "2 skipped" in summary


def test_legacy_alias_resolution():
    models, warnings = em.resolve_models(["claude-3-5-sonnet", "claude-3-haiku", "claude-opus-4-8"])
    assert models == ["claude-sonnet-5", "claude-haiku-4-5", "claude-opus-4-8"]
    assert any("claude-3-5-sonnet" in w and "claude-sonnet-5" in w for w in warnings)
    assert any("claude-3-haiku" in w and "claude-haiku-4-5" in w for w in warnings)
    # unknown model passes through but is flagged for fallback pricing
    models2, warnings2 = em.resolve_models(["some-future-model"])
    assert models2 == ["some-future-model"]
    assert any("no pricing" in w for w in warnings2)


def test_packaged_pairs_load_and_shape():
    pairs = em.load_pairs()
    assert 5 <= len(pairs["translation"]) <= 12
    assert all(p["patient"] and p["expected"] for p in pairs["translation"])
    labels = {c["label"] for c in pairs["classification"]}
    assert labels == {"clinical", "off_target", "structural"}
