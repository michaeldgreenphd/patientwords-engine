"""EXPERIMENTAL causal validation via Neuronpedia steering.

Attribution graphs are correlational: they say which features carried mass
toward a prediction, not that removing them would change it. Steering closes
that gap. ``steer_ablate`` asks Neuronpedia's steering API to suppress a set
of features (negative strength) while completing the same prompt, so the
default and steered continuations can be compared. If knocking out the top
off-target features restores the clinical continuation, the language-penalty
story is causal, not just correlational.

The exact response schema of ``/api/steer`` is not pinned by this module: the
raw JSON is stored verbatim in the batch summary, and the endpoint, method
and strength are all env-overridable (NEURONPEDIA_STEER_ENDPOINT / _METHOD /
_STRENGTH), so a schema mismatch is a recorded failure plus an env tweak, not
a code change. Steering runs on Neuronpedia's GPUs; like graph generation it
does not bill - the API key only authenticates and rate-limits.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any

import requests

from medlang_circuits.schema_utils import is_feature_node, node_layer_and_index

logger = logging.getLogger(__name__)

NEURONPEDIA_BASE_URL = "https://www.neuronpedia.org"
DEFAULT_STRENGTH = -10.0
DEFAULT_N_TOKENS = 8


def top_offtarget_features(graph: dict[str, Any], k: int) -> list[dict[str, Any]]:
    """The k highest-mass off-target features of a tagged graph.

    Mass is |incident edge weight| summed per node, aggregated over every
    position where the same (layer, feature index) fires. These are the
    ablation candidates: the features the colloquial wording dragged in.
    """
    meta = graph.get("metadata", {})
    schema_version, scan = meta.get("schema_version"), meta.get("scan", "gemma-2-2b")
    weight: dict[str, float] = defaultdict(float)
    for link in graph.get("links", []):
        w = abs(link.get("weight", 0.0))
        weight[link.get("source")] += w
        weight[link.get("target")] += w
    mass: dict[tuple[int, int], float] = defaultdict(float)
    label: dict[tuple[int, int], str] = {}
    for node in graph.get("nodes", []):
        if not is_feature_node(node):
            continue
        if (node.get("medlang") or {}).get("category") != "off_target":
            continue
        key = node_layer_and_index(node, schema_version, scan)
        if key is None:
            continue
        mass[key] += weight[node["node_id"]]
        med = node.get("medlang") or {}
        label.setdefault(key, (med.get("description") or node.get("clerp") or "")[:80])
    ranked = sorted(mass.items(), key=lambda kv: -kv[1])[:k]
    return [
        {"layer": layer, "index": index, "mass": round(m, 4), "label": label[(layer, index)]}
        for (layer, index), m in ranked
    ]


def steer_ablate(
    prompt: str,
    features: list[dict[str, Any]],
    model_id: str = "gemma-2-2b",
    source_set: str = "gemmascope-transcoder-16k",
    strength: float | None = None,
    n_tokens: int = DEFAULT_N_TOKENS,
    api_key: str | None = None,
    base_url: str = NEURONPEDIA_BASE_URL,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Suppress ``features`` while completing ``prompt``; return both runs.

    ``features`` are {layer, index, ...} dicts (top_offtarget_features
    output). Returns {"ok", "status", "request", "response"} with the raw
    response JSON preserved so downstream analysis never depends on schema
    guesses made here.
    """
    api_key = api_key or os.environ.get("NEURONPEDIA_API_KEY")
    if not api_key:
        return {"ok": False, "status": None, "error": "NEURONPEDIA_API_KEY is not set"}
    if strength is None:
        strength = float(os.environ.get("NEURONPEDIA_STEER_STRENGTH", DEFAULT_STRENGTH))
    endpoint = os.environ.get("NEURONPEDIA_STEER_ENDPOINT", "/api/steer")
    method = os.environ.get("NEURONPEDIA_STEER_METHOD", "SIMPLE_ADDITIVE")

    body = {
        "prompt": prompt,
        "modelId": model_id,
        "features": [
            {
                "modelId": model_id,
                "layer": f"{f['layer']}-{source_set}",
                "index": int(f["index"]),
                "strength": strength,
            }
            for f in features
        ],
        "temperature": 0.0,
        "n_tokens": int(n_tokens),
        "freq_penalty": 0,
        "seed": 16,
        "strength_multiplier": 1,
        "steer_special_tokens": True,
        "steer_method": method,
    }
    request_record = {
        "endpoint": endpoint,
        "strength": strength,
        "features": [{"layer": f["layer"], "index": f["index"]} for f in features],
    }
    try:
        resp = requests.post(
            base_url.rstrip("/") + endpoint,
            json=body,
            headers={"x-api-key": api_key},
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.warning("Steering request failed: %s", e)
        return {"ok": False, "status": None, "request": request_record, "error": str(e)[:300]}
    if not resp.ok:
        logger.warning("Steering returned %s: %s", resp.status_code, resp.text[:200])
        return {
            "ok": False,
            "status": resp.status_code,
            "request": request_record,
            "error": resp.text[:500],
        }
    try:
        payload = resp.json()
    except ValueError:
        payload = {"text": resp.text[:1000]}
    logger.info("Steering succeeded for %d features at strength %s", len(features), strength)
    return {"ok": True, "status": resp.status_code, "request": request_record, "response": payload}
