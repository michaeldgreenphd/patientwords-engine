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
# hosted graph generation. Tested against the live backend on 2026-07-07: only
# gemma-2-2b actually produces graphs. gemma-3-4b-it and qwen3-1.7b return a
# fast non-retryable error (not served), and qwen3-4b returns persistent 500s
# from /api/graph/generate even with no parallel load. The others are kept here
# so the cross-model trace matrix + front-end model selector light up
# automatically if/when Neuronpedia enables them - re-run the 2-pair probe (a
# graph_models circuit-trace trigger) to re-check before scaling.
MODEL_REGISTRY: dict[str, str] = {
    "gemma-2-2b": "google/gemma-2-2b",       # confirmed working
    "gemma-3-4b-it": "google/gemma-3-4b-it", # registered; not served yet (400/404)
    "qwen3-4b": "Qwen/Qwen3-4B",             # registered; hosted backend 500s
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",         # registered; not served yet (400/404)
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
                attempt, HOSTED_ATTEMPTS - 1, attempt_slug, wait, last_err,
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
        f"hosted graph generation failed after {HOSTED_ATTEMPTS} attempts for slug={slug!r}"
    ) from last_err


def _hosted_attempt(
    session: Any, body: dict[str, Any], model_id: str, slug: str, timeout: float
) -> dict[str, Any]:
    logger.info("Requesting hosted graph generation: model=%s slug=%s", model_id, slug)
    resp = session.post(f"{NEURONPEDIA_BASE_URL}/api/graph/generate", json=body, timeout=timeout)
    resp.raise_for_status()

    # Fetch metadata for the JSON file URL, then download the graph itself.
    meta_resp = session.get(f"{NEURONPEDIA_BASE_URL}/api/graph/{model_id}/{slug}", timeout=60)
    meta_resp.raise_for_status()
    json_url = meta_resp.json()["url"]
    graph_resp = requests.get(json_url, timeout=120)
    graph_resp.raise_for_status()
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
