"""Helpers for decoding node layer/index from Neuronpedia attribution graph JSON.

Mirrors the decoding logic in apps/webapp/app/[modelId]/graph/utils.ts:
- schema_version 1 graphs encode (layer, index) in node["feature"] as a Cantor pair
- older gemma-2-2b graphs encode them as layer * 100000 + index (index is the last 5 digits)
"""

from __future__ import annotations

import math
from typing import Any

# feature_type values whose nodes are transcoder/SAE features (classifiable)
FEATURE_NODE_TYPES = {"cross layer transcoder", "lorsa"}

# feature_type values that are structural by construction (embeddings, logits, error terms)
STRUCTURAL_NODE_TYPES = {
    "embedding",
    "logit",
    "mlp reconstruction error",
    "lorsa error",
    "bias",
    "unknown",
    "unexplored node",
}

GEMMA2_OLD_SCHEMA_INDEX_DIGITS = 5


def cantor_decode(value: int) -> tuple[int, int]:
    """Invert the Cantor pairing used by circuit-tracer: value = cantor(layer, index)."""
    w = math.floor((math.sqrt(8 * value + 1) - 1) / 2)
    t = (w * w + w) // 2
    index = value - t
    layer = w - index
    return layer, index


def is_feature_node(node: dict[str, Any]) -> bool:
    return node.get("feature_type") in FEATURE_NODE_TYPES


def is_structural_node(node: dict[str, Any]) -> bool:
    return node.get("feature_type") in STRUCTURAL_NODE_TYPES


def node_layer_and_index(node: dict[str, Any], schema_version: int | None, scan: str) -> tuple[int, int] | None:
    """Return (layer, feature_index) for a feature node, or None if it can't be decoded."""
    if not is_feature_node(node):
        return None
    feature = node.get("feature")
    if feature is None:
        return None
    feature = int(feature)

    if schema_version == 1:
        return cantor_decode(feature)

    if scan == "gemma-2-2b":
        # Old schema 0: feature = layer * 100000 + index (5-digit index)
        digits = str(feature)
        index = int(digits[-GEMMA2_OLD_SCHEMA_INDEX_DIGITS:])
        layer_str = digits[:-GEMMA2_OLD_SCHEMA_INDEX_DIGITS]
        layer = int(layer_str) if layer_str else 0
        return layer, index

    # Fallback: trust the node's own layer field and treat feature as the raw index
    try:
        return int(node["layer"]), feature
    except (KeyError, TypeError, ValueError):
        return None


def node_display_layer(node: dict[str, Any], max_numeric_layer: int) -> int:
    """Y-axis layer for layout: embeddings below layer 0, logits above the top layer."""
    layer = node.get("layer")
    if node.get("feature_type") == "logit":
        return max_numeric_layer + 1
    if layer == "E" or node.get("feature_type") == "embedding":
        return -1
    try:
        return int(layer)
    except (TypeError, ValueError):
        return 0


def max_numeric_layer(nodes: list[dict[str, Any]]) -> int:
    best = 0
    for node in nodes:
        try:
            best = max(best, int(node.get("layer")))
        except (TypeError, ValueError):
            continue
    return best
