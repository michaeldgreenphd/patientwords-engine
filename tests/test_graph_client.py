import json
import re

import pytest
from conftest import build_fetcher, make_graph

import medlang_circuits.graph_client as gc
from medlang_circuits.neuronpedia_features import FeatureFetcher


@pytest.fixture(autouse=True)
def _clean_graph_model_env(monkeypatch):
    monkeypatch.delenv(gc.GRAPH_MODEL_ENV_VAR, raising=False)


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, parent):
        self.parent = parent
        self.headers = {}

    def post(self, url, json=None, timeout=None):  # hosted generate
        self.parent.posts.append(json)
        return _Resp({})

    def get(self, url, timeout=None):  # hosted graph metadata
        self.parent.meta_urls.append(url)
        return _Resp({"url": "https://files.example/graph.json"})


class FakeRequests:
    """Drop-in for graph_client.requests: records request bodies, no network."""

    def __init__(self, graph):
        self.graph = graph
        self.posts = []
        self.meta_urls = []

    def Session(self):
        return _FakeSession(self)

    def get(self, url, timeout=None):  # hosted graph JSON download
        return _Resp(self.graph)

    def post(self, url, headers=None, json=None, timeout=None):  # local generate
        self.posts.append(json)
        return _Resp(self.graph)


@pytest.fixture
def fake_requests(monkeypatch):
    fake = FakeRequests(graph={"nodes": [], "links": []})
    monkeypatch.setattr(gc, "requests", fake)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    monkeypatch.setenv("GRAPH_SERVER_SECRET", "test-secret")
    return fake


# ---------------------------------------------------------------------------
# Model registry resolution
# ---------------------------------------------------------------------------


def test_resolve_graph_model_default_env_and_explicit(monkeypatch):
    assert gc.resolve_graph_model() == "gemma-2-2b"
    monkeypatch.setenv(gc.GRAPH_MODEL_ENV_VAR, "qwen3-4b")
    assert gc.resolve_graph_model() == "qwen3-4b"
    # an explicit argument beats the environment override
    assert gc.resolve_graph_model("gemma-3-4b-it") == "gemma-3-4b-it"


def test_resolve_graph_model_unknown_raises():
    with pytest.raises(ValueError, match="Unknown graph model"):
        gc.resolve_graph_model("gpt2")


def test_env_override_reaches_hosted_request(fake_requests, monkeypatch):
    monkeypatch.setenv(gc.GRAPH_MODEL_ENV_VAR, "qwen3-4b")
    gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    assert fake_requests.posts[0]["modelId"] == "qwen3-4b"
    assert fake_requests.meta_urls[0].endswith("/api/graph/qwen3-4b/s")


# ---------------------------------------------------------------------------
# Hosted request body
# ---------------------------------------------------------------------------


def test_hosted_request_defaults(fake_requests):
    graph = gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    body = fake_requests.posts[0]
    assert body["modelId"] == "gemma-2-2b"
    assert body["maxNLogits"] == 10
    assert body["desiredLogitProb"] == 0.95
    assert body["nodeThreshold"] == 0.8
    assert body["edgeThreshold"] == 0.98
    assert body["maxFeatureNodes"] == 5000
    # None source set is omitted so the server applies the model's default
    assert "sourceSetName" not in body
    assert "qkTopFraction" not in body and "qkTopk" not in body
    assert graph == fake_requests.graph


def test_hosted_source_set_sent_when_given(fake_requests):
    gc.generate_graph("the quick brown fox", slug="s", backend="hosted", source_set="my-set")
    assert fake_requests.posts[0]["sourceSetName"] == "my-set"


def test_qk_params_forwarded_for_lorsa_model(fake_requests):
    gc.generate_graph("the quick brown fox", slug="s", backend="hosted",
                      model_id="qwen3-1.7b", qk_top_fraction=0.1, qk_topk=2)
    body = fake_requests.posts[0]
    assert body["qkTopFraction"] == 0.1
    assert body["qkTopk"] == 2


# ---------------------------------------------------------------------------
# Client-side validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("param,value", [
    ("max_n_logits", 4), ("max_n_logits", 16),
    ("desired_logit_prob", 0.59), ("desired_logit_prob", 1.0),
    ("node_threshold", 0.45), ("node_threshold", 0.96),
    ("edge_threshold", 0.6), ("edge_threshold", 0.99),
    ("max_feature_nodes", 1499), ("max_feature_nodes", 10001),
])
def test_out_of_range_params_raise_before_any_request(param, value):
    with pytest.raises(ValueError, match=re.escape(f"{param}={value} is out of range")):
        gc.generate_graph("the quick brown fox", **{param: value})


@pytest.mark.parametrize("param,value", [
    ("qk_top_fraction", 0.04), ("qk_top_fraction", 0.51),
    ("qk_topk", 0), ("qk_topk", 6),
])
def test_qk_bounds(param, value):
    with pytest.raises(ValueError, match="out of range"):
        gc.generate_graph("the quick brown fox", model_id="qwen3-1.7b", **{param: value})


def test_integer_params_reject_floats():
    with pytest.raises(ValueError, match="max_n_logits must be an integer"):
        gc.generate_graph("the quick brown fox", max_n_logits=7.5)


@pytest.mark.parametrize("model", ["gemma-2-2b", "gemma-3-4b-it", "qwen3-4b"])
def test_qk_params_rejected_for_non_lorsa_models(model):
    with pytest.raises(ValueError, match="LORSA"):
        gc.generate_graph("the quick brown fox", model_id=model, qk_topk=2)


# ---------------------------------------------------------------------------
# Local request body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("np_id,tlens_id", sorted(gc.MODEL_REGISTRY.items()))
def test_local_model_mapping_and_defaults(fake_requests, np_id, tlens_id):
    gc.generate_graph("the quick brown fox", slug="s", backend="local", model_id=np_id)
    body = fake_requests.posts[0]
    assert body["model_id"] == tlens_id
    assert body["batch_size"] == 48
    assert body["compress"] is False
    assert body["max_feature_nodes"] == 5000


def test_local_overrides_and_qk(fake_requests):
    gc.generate_graph("the quick brown fox", slug="s", backend="local", model_id="qwen3-1.7b",
                      batch_size=8, compress=True, qk_top_fraction=0.2, qk_topk=3)
    body = fake_requests.posts[0]
    assert body["batch_size"] == 8
    assert body["compress"] is True
    assert body["qk_top_fraction"] == 0.2
    assert body["qk_topk"] == 3


# ---------------------------------------------------------------------------
# FeatureFetcher per-model source sets
# ---------------------------------------------------------------------------


def test_fetcher_default_source_set_for_gemma():
    fetcher = FeatureFetcher(model_id="gemma-2-2b")
    assert fetcher.source_set == "gemmascope-transcoder-16k"


@pytest.mark.parametrize("model", ["gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b"])
def test_fetcher_placeholder_models_require_explicit_source_set(model):
    with pytest.raises(ValueError, match="--source-set"):
        FeatureFetcher(model_id=model)


def test_fetcher_explicit_source_set_accepted():
    fetcher = FeatureFetcher(model_id="qwen3-4b", source_set="my-autointerp-set")
    assert fetcher.source_set == "my-autointerp-set"


# ---------------------------------------------------------------------------
# CLI threading: flags -> generate_graph / FeatureFetcher / summary files
# ---------------------------------------------------------------------------


def test_batch_cli_flags_reach_generate_graph(tmp_path, monkeypatch, capsys):
    import medlang_circuits.batch_eval as batch_eval

    calls = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        calls.append({"prompt": prompt, "backend": backend, "params": params})
        return make_graph()

    fetcher_kwargs = {}

    def fake_fetcher(**kwargs):
        fetcher_kwargs.update(kwargs)
        return build_fetcher()

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    monkeypatch.setattr(batch_eval, "FeatureFetcher", fake_fetcher)

    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{"top_prompt": "one phrasing of the fox", "bottom_prompt": "another phrasing of the fox"}]),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    rc = batch_eval.main([
        str(pairs), "--out", str(out), "--no-llm-translation", "--dpi", "50",
        "--graph-model", "qwen3-1.7b", "--source-set", "my-autointerp-set",
        "--max-n-logits", "7", "--desired-logit-prob", "0.9",
        "--node-threshold", "0.6", "--edge-threshold", "0.7",
        "--max-feature-nodes", "2000", "--qk-top-fraction", "0.1", "--qk-topk", "2",
    ])
    assert rc == 0
    capsys.readouterr()

    assert fetcher_kwargs == {"model_id": "qwen3-1.7b", "source_set": "my-autointerp-set",
                              "generate_missing": 0}
    assert len(calls) == 2  # clinical + patient panels
    for call in calls:
        params = call["params"]
        assert params["model_id"] == "qwen3-1.7b"
        assert params["source_set"] == "my-autointerp-set"
        assert params["max_n_logits"] == 7
        assert params["desired_logit_prob"] == 0.9
        assert params["node_threshold"] == 0.6
        assert params["edge_threshold"] == 0.7
        assert params["max_feature_nodes"] == 2000
        assert params["qk_top_fraction"] == 0.1
        assert params["qk_topk"] == 2

    # the batch summary is self-describing: model + source set recorded
    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["graph_model"] == "qwen3-1.7b"
    assert summary["source_set"] == "my-autointerp-set"
    assert summary["generation_params"]["qk_topk"] == 2
    assert summary["results"][0]["mode"] == "2panel"


def test_compare_cli_flags_reach_generate_graph(tmp_path, monkeypatch, capsys):
    import medlang_circuits.pipeline as pipeline
    from medlang_circuits import cli

    calls = []

    def fake_generate(prompt, slug=None, backend="hosted", model_id=None, source_set=None, **params):
        calls.append({"prompt": prompt, "model_id": model_id, "source_set": source_set, "params": params})
        return make_graph()

    fetcher_kwargs = {}

    def fake_fetcher(**kwargs):
        fetcher_kwargs.update(kwargs)
        return build_fetcher()

    monkeypatch.setattr(pipeline, "generate_graph", fake_generate)
    monkeypatch.setattr(pipeline, "FeatureFetcher", fake_fetcher)

    out = tmp_path / "out"
    rc = cli.main([
        "--patient", "one phrasing of the fox",
        "--clinical", "another phrasing of the fox",
        "--out", str(out), "--no-png",
        "--graph-model", "gemma-2-2b", "--source-set", "gemmascope-transcoder-16k",
        "--max-n-logits", "12",
    ])
    assert rc == 0
    capsys.readouterr()

    assert fetcher_kwargs == {"model_id": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k"}
    assert [c["model_id"] for c in calls] == ["gemma-2-2b", "gemma-2-2b"]
    assert all(c["params"]["max_n_logits"] == 12 for c in calls)

    # summary.json records the chosen model/source set
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["graph_generation"] == {
        "model": "gemma-2-2b",
        "source_set": "gemmascope-transcoder-16k",
        "backend": "hosted",
        "params": {"max_n_logits": 12},
    }


def test_hosted_retries_transient_500(monkeypatch):
    import requests as real_requests

    calls = {"post": 0}

    class Resp:
        def __init__(self, payload=None, status=200):
            self._payload = payload or {}
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise real_requests.exceptions.HTTPError(
                    f"{self.status_code} Server Error", response=self)

        def json(self):
            return self._payload

    class Sess:
        def __init__(self):
            self.headers = {}

        def post(self, url, json=None, timeout=None):
            calls["post"] += 1
            if calls["post"] < 3:
                return Resp(status=500)
            return Resp({})

        def get(self, url, timeout=None):
            return Resp({"url": "https://files.example/graph.json"})

    class Req:
        def Session(self):
            return Sess()

        def get(self, url, timeout=None):
            return Resp({"nodes": [], "links": []})

    monkeypatch.setattr(gc, "requests", Req())
    monkeypatch.setattr(gc, "HOSTED_RETRY_SLEEP", 0.0)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    graph = gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    assert calls["post"] == 3  # two 500s waited out, third attempt succeeded
    assert graph == {"nodes": [], "links": []}


def test_hosted_gives_up_after_max_attempts(monkeypatch):
    import pytest
    import requests as real_requests

    calls = {"post": 0}

    class Resp:
        status_code = 500

        def raise_for_status(self):
            raise real_requests.exceptions.HTTPError("500 Server Error", response=self)

    class Sess:
        def __init__(self):
            self.headers = {}

        def post(self, url, json=None, timeout=None):
            calls["post"] += 1
            return Resp()

        def get(self, url, timeout=None):
            raise AssertionError("metadata fetch should never run when generate 500s")

    class Req:
        def Session(self):
            return Sess()

    monkeypatch.setattr(gc, "requests", Req())
    monkeypatch.setattr(gc, "HOSTED_RETRY_SLEEP", 0.0)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="after 4 attempts"):
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    assert calls["post"] == gc.HOSTED_ATTEMPTS
