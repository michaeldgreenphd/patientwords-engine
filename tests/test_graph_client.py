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


# ---------------------------------------------------------------------------
# Hosted error bodies (2026-10-09): a non-2xx response keeps what the server said
# ---------------------------------------------------------------------------

_API_KEY = "np-secret-key-value-do-not-log"
_SIGNED_GRAPH_URL = "https://files.example/graph.json?X-Amz-Signature=abc123"


class _ErrResp:
    """A response that fails raise_for_status the way requests does."""

    def __init__(self, status=200, text="", payload=None):
        self.status_code = status
        self.text = text
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        import requests as real_requests

        if self.status_code >= 400:
            raise real_requests.exceptions.HTTPError(f"{self.status_code} Client Error", response=self)

    def json(self):
        return self._payload


def _scripted_requests(post_responses, meta_response=None, download_response=None):
    """A fake requests module whose generate POSTs return ``post_responses`` in order."""
    calls = {"post": 0, "meta": 0, "download": 0}

    class Sess:
        def __init__(self):
            self.headers = {}

        def post(self, url, json=None, timeout=None):
            resp = post_responses[min(calls["post"], len(post_responses) - 1)]
            calls["post"] += 1
            return resp

        def get(self, url, timeout=None):
            calls["meta"] += 1
            return meta_response or _ErrResp(payload={"url": _SIGNED_GRAPH_URL})

    class Req:
        def Session(self):
            return Sess()

        def get(self, url, timeout=None):
            calls["download"] += 1
            return download_response or _ErrResp(payload={"nodes": [], "links": []})

    return Req(), calls


@pytest.fixture
def hosted_env(monkeypatch):
    monkeypatch.setattr(gc, "HOSTED_RETRY_SLEEP", 0.0)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", _API_KEY)


def _all_log_text(caplog):
    return "\n".join(rec.getMessage() for rec in caplog.records)


def test_hosted_400_body_reaches_exception_and_log_without_retry(monkeypatch, hosted_env, caplog):
    import requests as real_requests

    body = '{"error":"Prompt Too Long","message":"LORSA models accept at most 10 tokens"}'
    fake, calls = _scripted_requests([_ErrResp(status=400, text=body)])
    monkeypatch.setattr(gc, "requests", fake)
    caplog.set_level("INFO", logger=gc.logger.name)

    with pytest.raises(gc.HostedHTTPError) as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted", model_id="qwen3-1.7b")

    err = excinfo.value
    assert calls["post"] == 1  # a 400 is not retryable: exactly one attempt
    assert calls["meta"] == 0
    # still an HTTPError carrying the response, so existing handlers and the
    # retry classification see the same object shape as before
    assert isinstance(err, real_requests.exceptions.HTTPError)
    assert err.response.status_code == 400
    assert err.status == 400 and err.step == "generate" and err.model_id == "qwen3-1.7b"
    assert err.body == body
    assert "Prompt Too Long" in str(err)
    assert "HTTP 400" in str(err) and "model=qwen3-1.7b" in str(err)
    errors = [rec for rec in caplog.records if rec.levelname == "ERROR"]
    assert len(errors) == 1
    assert "Prompt Too Long" in errors[0].getMessage()
    assert "qwen3-1.7b" in errors[0].getMessage()


@pytest.mark.parametrize("status", sorted(gc.RETRYABLE_HOSTED_STATUS))
def test_hosted_retryable_status_still_retries_with_body(monkeypatch, hosted_env, caplog, status):
    fake, calls = _scripted_requests([_ErrResp(status=status, text="GPUs Busy"), _ErrResp(payload={})])
    monkeypatch.setattr(gc, "requests", fake)
    caplog.set_level("INFO", logger=gc.logger.name)

    graph = gc.generate_graph("the quick brown fox", slug="s", backend="hosted")

    assert graph == {"nodes": [], "links": []}
    assert calls["post"] == 2  # the retryable status was waited out, as before
    warnings = [rec.getMessage() for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("GPUs Busy" in msg and f"HTTP {status}" in msg for msg in warnings)
    assert not [rec for rec in caplog.records if rec.levelname == "ERROR"]


def test_retryable_status_set_is_unchanged():
    assert gc.RETRYABLE_HOSTED_STATUS == {429, 500, 502, 503, 504}


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_hosted_non_retryable_statuses_raise_after_one_attempt(monkeypatch, hosted_env, status):
    fake, calls = _scripted_requests([_ErrResp(status=status, text="nope")])
    monkeypatch.setattr(gc, "requests", fake)
    with pytest.raises(gc.HostedHTTPError):
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    assert calls["post"] == 1


def test_hosted_exhausted_retries_name_the_last_body(monkeypatch, hosted_env):
    fake, calls = _scripted_requests([_ErrResp(status=503, text="GPUs Busy")])
    monkeypatch.setattr(gc, "requests", fake)
    with pytest.raises(RuntimeError, match="after 4 attempts") as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    assert calls["post"] == gc.HOSTED_ATTEMPTS
    assert "GPUs Busy" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, gc.HostedHTTPError)


def test_hosted_error_body_is_truncated(monkeypatch, hosted_env, caplog):
    huge = "x" * (gc.HOSTED_ERROR_BODY_LIMIT * 5)
    fake, _ = _scripted_requests([_ErrResp(status=400, text=huge)])
    monkeypatch.setattr(gc, "requests", fake)
    caplog.set_level("INFO", logger=gc.logger.name)

    with pytest.raises(gc.HostedHTTPError) as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")

    body = excinfo.value.body
    assert body.startswith("x" * gc.HOSTED_ERROR_BODY_LIMIT)
    assert body.count("x") == gc.HOSTED_ERROR_BODY_LIMIT
    assert f"{len(huge)} chars total" in body
    assert len(str(excinfo.value)) < gc.HOSTED_ERROR_BODY_LIMIT + 300
    assert all(len(rec.getMessage()) < gc.HOSTED_ERROR_BODY_LIMIT + 300 for rec in caplog.records)


def test_hosted_error_unreadable_body_is_recorded_as_missing(monkeypatch, hosted_env):
    class NoBody:
        status_code = 400

        @property
        def text(self):
            raise ValueError("cannot decode")

        def raise_for_status(self):
            import requests as real_requests

            raise real_requests.exceptions.HTTPError("400 Client Error", response=self)

    fake, _ = _scripted_requests([NoBody()])
    monkeypatch.setattr(gc, "requests", fake)
    with pytest.raises(gc.HostedHTTPError) as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")
    assert excinfo.value.body is None
    assert "<body unreadable>" in str(excinfo.value)


def test_hosted_error_never_logs_headers_or_key(monkeypatch, hosted_env, caplog):
    # even a server that echoes the key back must not get it into the log or exception
    fake, _ = _scripted_requests([_ErrResp(status=400, text=f'{{"error":"bad key {_API_KEY}"}}')])
    monkeypatch.setattr(gc, "requests", fake)
    caplog.set_level("DEBUG")

    with pytest.raises(gc.HostedHTTPError) as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")

    logged = _all_log_text(caplog)
    assert _API_KEY not in logged
    assert _API_KEY not in str(excinfo.value)
    assert "[redacted]" in excinfo.value.body
    assert "x-api-key" not in logged.lower()
    assert "x-api-key" not in str(excinfo.value).lower()


@pytest.mark.parametrize("step,failing", [("metadata", "meta"), ("graph download", "download")])
def test_hosted_metadata_and_download_errors_carry_scrubbed_body(monkeypatch, hosted_env, caplog, step, failing):
    s3_body = ("<Error><Code>SignatureDoesNotMatch</Code><AWSAccessKeyId>AKIAEXAMPLE</AWSAccessKeyId>"
               "<StringToSign>GET\nsigned-material</StringToSign><SignatureProvided>sig</SignatureProvided>"
               "<Url>https://files.example/graph.json?X-Amz-Signature=deadbeef&amp;x=1</Url></Error>")
    bad = _ErrResp(status=403, text=s3_body)
    if failing == "meta":
        fake, calls = _scripted_requests([_ErrResp(payload={})], meta_response=bad)
    else:
        fake, calls = _scripted_requests([_ErrResp(payload={})], download_response=bad)
    monkeypatch.setattr(gc, "requests", fake)
    caplog.set_level("INFO", logger=gc.logger.name)

    with pytest.raises(gc.HostedHTTPError) as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")

    err = excinfo.value
    assert calls["post"] == 1  # 403 is not retryable
    assert err.step == step and err.status == 403
    assert "SignatureDoesNotMatch" in err.body
    for leaked in ("AKIAEXAMPLE", "signed-material", "<SignatureProvided>sig<", "deadbeef", "abc123"):
        assert leaked not in str(err)
        assert leaked not in _all_log_text(caplog)
    # the logged URL never carries the pre-signed query string
    assert "?" not in err.url


# Gemini review of PR #90: requests' own messages quote the full URL ("for url: ..."), so neither the raised error nor
# its chain may carry the original exception, and a connection error's text is scrubbed before it is logged or raised.

class _RealisticErrResp(_ErrResp):
    """Fails raise_for_status with requests' real message shape, which ends "for url: <url>"."""

    def __init__(self, status, text, url):
        super().__init__(status=status, text=text)
        self.url = url

    def raise_for_status(self):
        import requests as real_requests

        raise real_requests.exceptions.HTTPError(f"{self.status_code} Client Error: Forbidden for url: {self.url}",
                                                 response=self)


def test_download_failure_traceback_never_prints_the_signed_url(monkeypatch, hosted_env, caplog):
    import traceback

    bad = _RealisticErrResp(403, "<Error><Code>AccessDenied</Code></Error>", _SIGNED_GRAPH_URL)
    fake, _ = _scripted_requests([_ErrResp(payload={})], download_response=bad)
    monkeypatch.setattr(gc, "requests", fake)
    caplog.set_level("INFO", logger=gc.logger.name)

    with pytest.raises(gc.HostedHTTPError) as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")

    printed = "".join(traceback.format_exception(excinfo.value))
    assert "AccessDenied" in printed  # the server's message still reaches the CI log
    assert "abc123" not in printed and "X-Amz-Signature" not in printed
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__
    assert "abc123" not in _all_log_text(caplog)


def test_exhausted_retries_scrub_a_connection_error_that_quotes_the_signed_url(monkeypatch, hosted_env, caplog):
    import traceback

    import requests as real_requests

    class Req:
        def Session(self):
            sess, _ = _scripted_requests([_ErrResp(payload={})])
            return sess.Session()

        def get(self, url, timeout=None):
            raise real_requests.exceptions.ConnectionError(
                "HTTPSConnectionPool(host='files.example', port=443): Max retries exceeded with url: "
                "/graph.json?X-Amz-Signature=abc123&X-Amz-Credential=cred456 (Caused by NewConnectionError)")

    monkeypatch.setattr(gc, "requests", Req())
    caplog.set_level("INFO", logger=gc.logger.name)

    with pytest.raises(RuntimeError, match="after 4 attempts") as excinfo:
        gc.generate_graph("the quick brown fox", slug="s", backend="hosted")

    printed = "".join(traceback.format_exception(excinfo.value))
    assert "ConnectionError" in printed and "/graph.json?[query redacted]" in printed
    for leaked in ("abc123", "cred456", "X-Amz-"):
        assert leaked not in printed
        assert leaked not in _all_log_text(caplog)


def test_hosted_http_error_survives_copy_and_pickle():
    import copy
    import pickle

    err = gc.HostedHTTPError("hosted generate returned HTTP 400", response=None, status=400, step="generate",
                             model_id="gemma-3-4b-it", url="https://www.neuronpedia.org/api/graph/generate",
                             body="Source Set Missing")
    for clone in (copy.copy(err), pickle.loads(pickle.dumps(err))):
        assert isinstance(clone, gc.HostedHTTPError)
        assert (clone.status, clone.step, clone.model_id, clone.body) == (400, "generate", "gemma-3-4b-it",
                                                                           "Source Set Missing")
        assert str(clone) == str(err)
