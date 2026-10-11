"""Generate attribution graphs via either backend behind one function.

Backends:
    hosted - neuronpedia.org's graph generation API (no GPU needed).
             Requires NEURONPEDIA_API_KEY. Mirrors GraphRequest.generate() in
             packages/python/neuronpedia-webapp-client.
    local  - a running apps/graph server (circuit-tracer backend, needs GPU).
             Requires GRAPH_SERVER_SECRET; server URL via GRAPH_SERVER_URL
             (default http://localhost:5004). With no signed_url the server
             returns the graph JSON directly.

Model selection: MODEL_REGISTRY maps Neuronpedia model IDs (hosted API, graph
URLs) to TransformerLens model IDs (local circuit-tracer server). The traced
model resolves as: explicit ``model_id`` argument -> MEDLANG_GRAPH_MODEL
environment variable -> DEFAULT_GRAPH_MODEL. Request parameters are validated
client-side against the hosted schema bounds (PARAM_BOUNDS) so bad values fail
with a ValueError naming the bound instead of an API 400.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

NEURONPEDIA_BASE_URL = os.environ.get("NEURONPEDIA_BASE_URL", "https://www.neuronpedia.org")
LOCAL_SERVER_URL = os.environ.get("GRAPH_SERVER_URL", "http://localhost:5004")

# Neuronpedia model ID -> TransformerLens model ID. Registered candidates for
# hosted graph generation; docs/cross-model.md has the dated probe table, and
# the hosted backend changes, so re-run the 2-pair probe (a graph_models
# circuit-trace trigger) before relying on any of this. As of the 2026-09-02
# re-probe: gemma-2-2b and qwen3-4b serve graphs (qwen3-4b since 2026-09-02;
# it returned persistent 500s on 2026-07-07). Which models have feature labels
# is neuronpedia_features.MODEL_SOURCE_SETS, not this table. gemma-3-4b-it and
# qwen3-1.7b return a fast non-retryable error whose cause is unrecorded,
# because the client discarded the response body until HostedHTTPError began
# carrying it. Both causes below are inferred from Neuronpedia's source and its
# public model records (2026-10-09), not observed: gemma-3-4b-it has no default
# graph source set, so a request that omits sourceSetName (this study's
# default) gets "Source Set Missing"; qwen3-1.7b has a 10-token prompt cap for
# LORSA models ("Prompt Too Long"). The unserved models stay here so the
# cross-model trace matrix and the front-end model selector light up if
# Neuronpedia enables them.
MODEL_REGISTRY: dict[str, str] = {
    "gemma-2-2b": "google/gemma-2-2b",       # confirmed working
    "gemma-3-4b-it": "google/gemma-3-4b-it", # registered; fast non-retryable error (likely no default source set)
    "qwen3-4b": "Qwen/Qwen3-4B",             # SERVES GRAPHS since 2026-09-02
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",         # registered; fast non-retryable error (likely 10-token LORSA cap)
}

DEFAULT_GRAPH_MODEL = "gemma-2-2b"
GRAPH_MODEL_ENV_VAR = "MEDLANG_GRAPH_MODEL"

# Models traced with LORSA attention replacement, where the QK tracing
# parameters (qk_top_fraction / qk_topk) apply.
QK_TRACING_MODELS = ("qwen3-1.7b",)

# name -> (lo, hi, must_be_int), mirroring neuronpedia.org's request schema.
PARAM_BOUNDS: dict[str, tuple[float, float, bool]] = {
    "max_n_logits": (5, 15, True),
    "desired_logit_prob": (0.6, 0.99, False),
    "node_threshold": (0.5, 0.95, False),
    "edge_threshold": (0.65, 0.98, False),
    "max_feature_nodes": (1500, 10000, True),
    "qk_top_fraction": (0.05, 0.5, False),
    "qk_topk": (1, 5, True),
}

DEFAULT_PARAMS = {
    "max_n_logits": 10,
    "desired_logit_prob": 0.95,
    "node_threshold": 0.8,
    "edge_threshold": 0.98,
    "max_feature_nodes": 5000,
}

# Local (circuit-tracer server) knobs with no hosted equivalent.
LOCAL_DEFAULT_PARAMS = {"batch_size": 48, "compress": False}


def resolve_graph_model(model_id: str | None = None) -> str:
    """Resolve the Neuronpedia model ID: explicit arg -> env override -> default."""
    resolved = model_id or os.environ.get(GRAPH_MODEL_ENV_VAR) or DEFAULT_GRAPH_MODEL
    if resolved not in MODEL_REGISTRY:
        raise ValueError(
            f"Unknown graph model {resolved!r}; known models: {', '.join(MODEL_REGISTRY)}"
        )
    return resolved


def validate_generation_params(model_id: str, params: dict[str, Any]) -> None:
    """Check every bounded parameter client-side rather than letting the API 400."""
    for name, (lo, hi, must_be_int) in PARAM_BOUNDS.items():
        value = params.get(name)
        if value is None:
            continue
        if must_be_int and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{name} must be an integer in [{lo}, {hi}]; got {value!r}")
        if not lo <= value <= hi:
            raise ValueError(f"{name}={value} is out of range [{lo}, {hi}]")
    for name in ("qk_top_fraction", "qk_topk"):
        if params.get(name) is not None and model_id not in QK_TRACING_MODELS:
            raise ValueError(
                f"{name} only applies to LORSA/QK tracing models {QK_TRACING_MODELS}; "
                f"unset it or choose one of those models (got model {model_id!r})"
            )


def slugify(text: str, prefix: str = "medlang") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return f"{prefix}-{slug}-{int(time.time())}"


def generate_graph(
    prompt: str,
    slug: str | None = None,
    backend: str = "hosted",
    model_id: str | None = None,
    source_set: str | None = None,
    timeout: float = 600.0,
    **params: Any,
) -> dict[str, Any]:
    """Run the circuit tracer on ``prompt`` and return the parsed graph JSON.

    Args:
        model_id: Neuronpedia model ID from MODEL_REGISTRY (default: the
            MEDLANG_GRAPH_MODEL environment variable, then gemma-2-2b).
        source_set: transcoder source set for hosted generation; when None the
            field is omitted and the server applies the model's default.
        **params: bounded tracer parameters (see PARAM_BOUNDS); the local
            backend additionally honors batch_size, compress, and
            force_target_tokens.
    """
    model_id = resolve_graph_model(model_id)
    merged = {**DEFAULT_PARAMS, **{k: v for k, v in params.items() if v is not None}}
    validate_generation_params(model_id, merged)
    slug = slug or slugify(prompt)
    if backend == "hosted":
        return _generate_hosted(prompt, slug, model_id, source_set, timeout, **merged)
    if backend == "local":
        return _generate_local(prompt, slug, model_id, timeout, **merged)
    raise ValueError(f"Unknown backend {backend!r}; expected 'hosted' or 'local'")


# Retry policy for the hosted backend: Neuronpedia intermittently returns
# 5xx under parallel load (observed as 500s when three matrix jobs generate
# concurrently). Those are worth waiting out instead of failing the batch.
RETRYABLE_HOSTED_STATUS = {429, 500, 502, 503, 504}
HOSTED_ATTEMPTS = 4
HOSTED_RETRY_SLEEP = 15.0  # doubles per retry: 15s, 30s, 60s

# Bound at import so retry logic keeps working when tests monkeypatch
# graph_client.requests with a fake module.
_HTTPError = requests.exceptions.HTTPError
_ConnectionError = requests.exceptions.ConnectionError
_Timeout = requests.exceptions.Timeout

# Upper bound on the response body kept on a hosted error (log line and
# exception message). Neuronpedia's error bodies are short JSON messages such as
# "Prompt Too Long" or "Source Set Missing"; the bound only keeps an HTML error
# page from flooding the CI log.
HOSTED_ERROR_BODY_LIMIT = 2000

# Signed-URL material that a storage error body (an S3-style
# SignatureDoesNotMatch reply to the graph download) can echo back. The API key
# travels only in a request header and is never logged; these are scrubbed from
# the body before it is logged or raised because the repository is public.
_SIGNED_BODY_ELEMENTS = re.compile(
    r"<(AWSAccessKeyId|SignatureProvided|StringToSign|StringToSignBytes|CanonicalRequest|"
    r"CanonicalRequestBytes)>.*?</\1>",
    re.DOTALL,
)
_SIGNED_QUERY_PARAMS = re.compile(r"(X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s\"'<]+")


class HostedHTTPError(_HTTPError):
    """A non-2xx response from the hosted backend, carrying what the server said.

    Subclasses ``requests.exceptions.HTTPError`` and keeps the original
    exception's ``response``, so ``err.response.status_code`` (the retry
    classification in _generate_hosted) and any ``except HTTPError`` keep
    working unchanged. The extra attributes record which request failed and the
    bounded, scrubbed response body; ``body`` is None when it could not be read.
    """

    def __init__(
        self,
        message: str,
        *,
        response: Any = None,
        status: int | None = None,
        step: str = "",
        model_id: str = "",
        url: str = "",
        body: str | None = None,
    ) -> None:
        # Defaults only so copy/pickle (which call cls(*self.args) and then
        # restore __dict__) can rebuild the exception; every raise passes all.
        super().__init__(message, response=response)
        self.status = status
        self.step = step
        self.model_id = model_id
        self.url = url
        self.body = body


def _redact_url(url: str) -> str:
    """Drop the query string and fragment: the graph download is a pre-signed storage URL."""
    return url.split("?", 1)[0].split("#", 1)[0]


_QUERY_STRING_RE = re.compile(r"\?[^\s'\"<>()]*")


def _safe_error_text(err: BaseException | None) -> str:
    """``type: message`` with every query string removed.

    requests and urllib3 quote the request URL in their own messages ("for url:
    ...", "Max retries exceeded with url: ..."), which for the graph download is
    the pre-signed storage URL; a HostedHTTPError's message is already safe.
    """
    if err is None:
        return "None"
    return f"{type(err).__name__}: {_QUERY_STRING_RE.sub('?[query redacted]', str(err))}"


def _bounded_body(resp: Any, secrets: tuple[str, ...] = ()) -> str | None:
    """The response body, scrubbed and truncated to HOSTED_ERROR_BODY_LIMIT characters.

    Returns None when the body cannot be read, so a missing body is recorded as
    missing rather than as an empty message.
    """
    try:
        text = resp.text
    except Exception:  # noqa: BLE001 - an unreadable body must not mask the HTTP error itself
        return None
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    text = _SIGNED_BODY_ELEMENTS.sub(lambda m: f"<{m.group(1)}>[redacted]</{m.group(1)}>", text)
    text = _SIGNED_QUERY_PARAMS.sub(r"\1[redacted]", text)
    if len(text) > HOSTED_ERROR_BODY_LIMIT:
        text = f"{text[:HOSTED_ERROR_BODY_LIMIT]}... [truncated; {len(text)} chars total]"
    return text


def _raise_for_hosted_status(
    resp: Any, *, step: str, model_id: str, slug: str, url: str, secrets: tuple[str, ...] = ()
) -> None:
    """``resp.raise_for_status()``, except that a failure logs and carries the response body.

    Re-raises as HostedHTTPError holding the original exception's ``response``,
    so the status code the retry loop classifies on is exactly the one
    raise_for_status reported. Only the step, status, model, slug, query-free URL
    and scrubbed body are logged: never request headers, the session, or the
    request body.
    """
    try:
        resp.raise_for_status()
    except _HTTPError as err:
        response = err.response
        status = getattr(response, "status_code", None)
        body = _bounded_body(resp, secrets)
        safe_url = _redact_url(url)
        level = logging.WARNING if status in RETRYABLE_HOSTED_STATUS else logging.ERROR
        logger.log(
            level,
            "Hosted %s failed: HTTP %s model=%s slug=%s url=%s body=%s",
            step, status, model_id, slug, safe_url, body,
        )
        raise HostedHTTPError(
            f"hosted {step} returned HTTP {status} for model={model_id} slug={slug} "
            f"url={safe_url}: {body if body is not None else '<body unreadable>'}",
            response=response,
            status=status,
            step=step,
            model_id=model_id,
            url=safe_url,
            body=body,
        ) from None  # the original HTTPError's message quotes the full URL; never chain it


def _generate_hosted(
    prompt: str, slug: str, model_id: str, source_set: str | None, timeout: float, **params: Any
) -> dict[str, Any]:
    api_key = os.environ.get("NEURONPEDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NEURONPEDIA_API_KEY is required for the hosted backend")
    session = requests.Session()
    session.headers["x-api-key"] = api_key

    body = {
        "modelId": model_id,
        "prompt": prompt,
        "slug": slug,
        "maxNLogits": params["max_n_logits"],
        "desiredLogitProb": params["desired_logit_prob"],
        "nodeThreshold": params["node_threshold"],
        "edgeThreshold": params["edge_threshold"],
        "maxFeatureNodes": params["max_feature_nodes"],
    }
    if source_set is not None:
        body["sourceSetName"] = source_set  # omitted -> server picks the model's default
    if params.get("qk_top_fraction") is not None:
        body["qkTopFraction"] = params["qk_top_fraction"]
    if params.get("qk_topk") is not None:
        # NOTE: the hosted API silently ignores unknown keys rather than 400ing,
        # so a misspelled field here would drop the option without any error.
        body["qkTopk"] = params["qk_topk"]

    last_err: Exception | None = None
    for attempt in range(HOSTED_ATTEMPTS):
        # a fresh slug per attempt sidesteps server-side state from a half
        # finished earlier attempt (generate succeeded, metadata fetch 500d)
        attempt_slug = slug if attempt == 0 else f"{slug}-r{attempt}"
        if attempt:
            wait = HOSTED_RETRY_SLEEP * 2 ** (attempt - 1)
            logger.warning(
                "Hosted generation retry %d/%d for slug=%s in %.0fs (%s)",
                attempt, HOSTED_ATTEMPTS - 1, attempt_slug, wait, _safe_error_text(last_err),
            )
            time.sleep(wait)
        body["slug"] = attempt_slug
        try:
            return _hosted_attempt(session, body, model_id, attempt_slug, timeout)
        except _HTTPError as err:
            status = getattr(err.response, "status_code", None)
            if status not in RETRYABLE_HOSTED_STATUS:
                raise
            last_err = err
        except (_ConnectionError, _Timeout) as err:
            last_err = err
    raise RuntimeError(
        f"hosted graph generation failed after {HOSTED_ATTEMPTS} attempts for slug={slug!r}; "
        f"last error: {_safe_error_text(last_err)}"
    ) from (last_err if isinstance(last_err, HostedHTTPError) else None)
    # A HostedHTTPError is already scrubbed and carries no chain of its own; any
    # other last error (a connection error, a timeout) can quote the pre-signed
    # URL in its message or its chain, so only its scrubbed text is kept.


def _hosted_attempt(
    session: Any, body: dict[str, Any], model_id: str, slug: str, timeout: float
) -> dict[str, Any]:
    logger.info("Requesting hosted graph generation: model=%s slug=%s", model_id, slug)
    # The key is read only to scrub it from an error body should a server ever
    # echo it back; it is never logged.
    secrets = (session.headers.get("x-api-key") or "",)
    generate_url = f"{NEURONPEDIA_BASE_URL}/api/graph/generate"
    resp = session.post(generate_url, json=body, timeout=timeout)
    _raise_for_hosted_status(resp, step="generate", model_id=model_id, slug=slug, url=generate_url,
                             secrets=secrets)

    # Fetch metadata for the JSON file URL, then download the graph itself.
    meta_url = f"{NEURONPEDIA_BASE_URL}/api/graph/{model_id}/{slug}"
    meta_resp = session.get(meta_url, timeout=60)
    _raise_for_hosted_status(meta_resp, step="metadata", model_id=model_id, slug=slug, url=meta_url,
                             secrets=secrets)
    json_url = meta_resp.json()["url"]
    graph_resp = requests.get(json_url, timeout=120)
    _raise_for_hosted_status(graph_resp, step="graph download", model_id=model_id, slug=slug, url=json_url,
                             secrets=secrets)
    graph = graph_resp.json()
    logger.info(
        "Hosted graph ready: %s nodes, %s links (view at %s/%s/graph?slug=%s)",
        len(graph.get("nodes", [])),
        len(graph.get("links", [])),
        NEURONPEDIA_BASE_URL,
        model_id,
        slug,
    )
    return graph


def _generate_local(prompt: str, slug: str, model_id: str, timeout: float, **params: Any) -> dict[str, Any]:
    secret = os.environ.get("GRAPH_SERVER_SECRET")
    if not secret:
        raise RuntimeError("GRAPH_SERVER_SECRET is required for the local backend")

    logger.info("Requesting local graph generation at %s: slug=%s", LOCAL_SERVER_URL, slug)
    body = {
        "prompt": prompt,
        "model_id": MODEL_REGISTRY[model_id],
        "slug_identifier": slug,
        "batch_size": params.get("batch_size", LOCAL_DEFAULT_PARAMS["batch_size"]),
        "compress": params.get("compress", LOCAL_DEFAULT_PARAMS["compress"]),
        "max_n_logits": params["max_n_logits"],
        "desired_logit_prob": params["desired_logit_prob"],
        "node_threshold": params["node_threshold"],
        "edge_threshold": params["edge_threshold"],
        "max_feature_nodes": params["max_feature_nodes"],
        # no signed_url -> the server returns the graph JSON in the response body
    }
    for key in ("qk_top_fraction", "qk_topk"):
        if params.get(key) is not None:
            body[key] = params[key]
    if params.get("force_target_tokens"):
        # Native target forcing for circuit-tracer forks whose server accepts it;
        # the stock apps/graph server ignores unknown fields, so this is harmless.
        body["force_target_tokens"] = list(params["force_target_tokens"])
    resp = requests.post(
        f"{LOCAL_SERVER_URL}/generate-graph",
        headers={"x-secret-key": secret},
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    graph = resp.json()
    if "error" in graph:
        raise RuntimeError(f"Local graph server error: {graph['error']}")
    logger.info("Local graph ready: %s nodes, %s links", len(graph.get("nodes", [])), len(graph.get("links", [])))
    return graph


def add_graph_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """Register the shared circuit-tracer flags on a CLI parser.

    Unset flags stay None so DEFAULT_PARAMS (or the server) decides; bounds are
    enforced in generate_graph via validate_generation_params.
    """
    group = parser.add_argument_group("circuit tracer options")
    group.add_argument("--graph-model", default=None, choices=sorted(MODEL_REGISTRY),
                       help=f"Traced model (default: ${GRAPH_MODEL_ENV_VAR} or {DEFAULT_GRAPH_MODEL})")
    group.add_argument("--source-set", default=None,
                       help="Transcoder source set; omitted -> the server applies the model's default. "
                            "Also selects the feature-autointerp source for tagging.")
    group.add_argument("--max-n-logits", type=int, default=None, help="Salient logits to trace (int 5-15, default 10)")
    group.add_argument("--desired-logit-prob", type=float, default=None,
                       help="Cumulative probability mass to cover (0.6-0.99, default 0.95)")
    group.add_argument("--node-threshold", type=float, default=None, help="Node pruning threshold (0.5-0.95, default 0.8)")
    group.add_argument("--edge-threshold", type=float, default=None, help="Edge pruning threshold (0.65-0.98, default 0.98)")
    group.add_argument("--max-feature-nodes", type=int, default=None,
                       help="Feature node cap (int 1500-10000, default 5000)")
    group.add_argument("--qk-top-fraction", type=float, default=None,
                       help=f"QK tracing top fraction (0.05-0.5); {', '.join(QK_TRACING_MODELS)} only")
    group.add_argument("--qk-topk", type=int, default=None,
                       help=f"QK tracing top-k (int 1-5); {', '.join(QK_TRACING_MODELS)} only")


def generation_params_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Collect the tracer flags that were actually set into a generation_params dict."""
    return {name: getattr(args, name, None) for name in PARAM_BOUNDS if getattr(args, name, None) is not None}
