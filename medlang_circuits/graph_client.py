"""Generate attribution graphs via either backend behind one function.

Backends:
    hosted - neuronpedia.org's graph generation API (no GPU needed).
             Requires NEURONPEDIA_API_KEY. Mirrors GraphRequest.generate() in
             packages/python/neuronpedia-webapp-client.
    local  - a running apps/graph server (circuit-tracer backend, needs GPU).
             Requires GRAPH_SERVER_SECRET; server URL via GRAPH_SERVER_URL
             (default http://localhost:5004). With no signed_url the server
             returns the graph JSON directly.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

NEURONPEDIA_BASE_URL = os.environ.get("NEURONPEDIA_BASE_URL", "https://www.neuronpedia.org")
LOCAL_SERVER_URL = os.environ.get("GRAPH_SERVER_URL", "http://localhost:5004")
HOSTED_MODEL_ID = "gemma-2-2b"
LOCAL_TLENS_MODEL_ID = "google/gemma-2-2b"

DEFAULT_PARAMS = {
    "max_n_logits": 10,
    "desired_logit_prob": 0.95,
    "node_threshold": 0.8,
    "edge_threshold": 0.98,
}


def slugify(text: str, prefix: str = "medlang") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return f"{prefix}-{slug}-{int(time.time())}"


def generate_graph(
    prompt: str,
    slug: str | None = None,
    backend: str = "hosted",
    timeout: float = 600.0,
    **params: Any,
) -> dict[str, Any]:
    """Run the circuit tracer on ``prompt`` and return the parsed graph JSON."""
    merged = {**DEFAULT_PARAMS, **params}
    slug = slug or slugify(prompt)
    if backend == "hosted":
        return _generate_hosted(prompt, slug, timeout, **merged)
    if backend == "local":
        return _generate_local(prompt, slug, timeout, **merged)
    raise ValueError(f"Unknown backend {backend!r}; expected 'hosted' or 'local'")


def _generate_hosted(prompt: str, slug: str, timeout: float, **params: Any) -> dict[str, Any]:
    api_key = os.environ.get("NEURONPEDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NEURONPEDIA_API_KEY is required for the hosted backend")
    session = requests.Session()
    session.headers["x-api-key"] = api_key

    logger.info("Requesting hosted graph generation: slug=%s", slug)
    resp = session.post(
        f"{NEURONPEDIA_BASE_URL}/api/graph/generate",
        json={
            "modelId": HOSTED_MODEL_ID,
            "prompt": prompt,
            "slug": slug,
            "maxNLogits": params["max_n_logits"],
            "desiredLogitProb": params["desired_logit_prob"],
            "nodeThreshold": params["node_threshold"],
            "edgeThreshold": params["edge_threshold"],
        },
        timeout=timeout,
    )
    resp.raise_for_status()

    # Fetch metadata for the JSON file URL, then download the graph itself.
    meta_resp = session.get(f"{NEURONPEDIA_BASE_URL}/api/graph/{HOSTED_MODEL_ID}/{slug}", timeout=60)
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
        HOSTED_MODEL_ID,
        slug,
    )
    return graph


def _generate_local(prompt: str, slug: str, timeout: float, **params: Any) -> dict[str, Any]:
    secret = os.environ.get("GRAPH_SERVER_SECRET")
    if not secret:
        raise RuntimeError("GRAPH_SERVER_SECRET is required for the local backend")

    logger.info("Requesting local graph generation at %s: slug=%s", LOCAL_SERVER_URL, slug)
    resp = requests.post(
        f"{LOCAL_SERVER_URL}/generate-graph",
        headers={"x-secret-key": secret},
        json={
            "prompt": prompt,
            "model_id": LOCAL_TLENS_MODEL_ID,
            "slug_identifier": slug,
            "max_n_logits": params["max_n_logits"],
            "desired_logit_prob": params["desired_logit_prob"],
            "node_threshold": params["node_threshold"],
            "edge_threshold": params["edge_threshold"],
            # no signed_url -> the server returns the graph JSON in the response body
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    graph = resp.json()
    if "error" in graph:
        raise RuntimeError(f"Local graph server error: {graph['error']}")
    logger.info("Local graph ready: %s nodes, %s links", len(graph.get("nodes", [])), len(graph.get("links", [])))
    return graph
