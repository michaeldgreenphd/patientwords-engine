"""Task 1: annotate attribution-graph nodes with category classifications.

Post-processes a Neuronpedia/circuit-tracer graph JSON (see
apps/webapp/app/api/graph/graph-schema.json):

- embedding / logit / error / bias nodes are tagged ``structural`` by construction
- transcoder feature nodes are classified by keyword-matching their Neuronpedia
  autointerp description + top activating tokens against the external keyword
  config (see keywords.py), with an optional Anthropic LLM fallback for
  unmatched features
- classifications are appended in-place: per-node ``node["medlang"]`` metadata
  plus a graph-level ``metadata["medlang_summary"]``

The extra keys are additive - the schema allows unknown properties, so tagged
graphs still load in the existing Neuronpedia viewer.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Any, Callable

from medlang_circuits.keywords import (
    CATEGORIES,
    CATEGORY_CLINICAL,
    CATEGORY_OFF_TARGET,
    CATEGORY_STRUCTURAL,
    load_keyword_config,
)
from medlang_circuits.schema_utils import is_feature_node, is_structural_node, node_layer_and_index

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY = CATEGORY_OFF_TARGET  # unmatched, non-structural features default here
METADATA_KEY = "medlang"
SUMMARY_KEY = "medlang_summary"

# Tie-break priority when keyword scores are equal (domain evidence wins).
_PRIORITY = (CATEGORY_CLINICAL, CATEGORY_STRUCTURAL, CATEGORY_OFF_TARGET)


def _compile_patterns(config: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    return {
        cat: [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in terms if term.strip()]
        for cat, terms in config.items()
    }


def classify_text(
    text: str,
    keyword_config: dict[str, list[str]] | None = None,
    _compiled: dict[str, list[re.Pattern]] | None = None,
) -> tuple[str | None, list[str]]:
    """Keyword-classify text. Returns (category | None, matched_terms)."""
    patterns = _compiled or _compile_patterns(keyword_config or load_keyword_config())
    matches: dict[str, list[str]] = {}
    for cat in CATEGORIES:
        hits = [p.pattern for p in patterns.get(cat, []) if p.search(text)]
        if hits:
            matches[cat] = hits
    if not matches:
        return None, []
    best = max(matches, key=lambda cat: (len(matches[cat]), -_PRIORITY.index(cat)))
    # de-escape the regex patterns back to readable terms
    matched_terms = [re.sub(r"\\b", "", m).replace("\\ ", " ").replace("\\", "") for m in matches[best]]
    return best, matched_terms


def annotate_graph(
    graph: dict[str, Any],
    fetcher: Any = None,
    keyword_config: dict[str, list[str]] | None = None,
    llm_classifier: Callable[[str, list[str]], str | None] | None = None,
    default_category: str = DEFAULT_CATEGORY,
    fill_clerp: bool = True,
) -> dict[str, Any]:
    """Annotate graph nodes in place and return the graph.

    Args:
        graph: parsed graph JSON (mutated in place).
        fetcher: object with ``get(layer, index) -> {description, top_tokens}``;
            defaults to a Neuronpedia FeatureFetcher for the graph's scan.
        keyword_config: {category: [terms]}; defaults to load_keyword_config().
        llm_classifier: optional ``fn(description, top_tokens) -> category | None``
            used for features with no keyword match (e.g.
            ``medlang_circuits.llm_client.classify_feature_with_llm``).
        default_category: bucket for features that nothing else classified.
        fill_clerp: copy the fetched description into empty ``clerp`` labels so
            standalone renders have readable node labels.
    """
    metadata = graph.get("metadata", {})
    scan = metadata.get("scan", "gemma-2-2b")
    schema_version = metadata.get("schema_version")

    if fetcher is None:
        from medlang_circuits.neuronpedia_features import FeatureFetcher

        source_set = (metadata.get("feature_details") or {}).get("neuronpedia_source_set")
        kwargs = {"model_id": scan}
        if source_set:
            kwargs["source_set"] = source_set
        fetcher = FeatureFetcher(**kwargs)

    compiled = _compile_patterns(keyword_config or load_keyword_config())
    counts: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    feature_cache: dict[tuple[int, int], dict[str, Any]] = {}

    for node in graph.get("nodes", []):
        annotation: dict[str, Any] = {"category": None, "method": None, "matched_terms": []}

        if is_structural_node(node):
            annotation["category"] = CATEGORY_STRUCTURAL
            annotation["method"] = "feature_type"
        elif is_feature_node(node):
            layer_index = node_layer_and_index(node, schema_version, scan)
            if layer_index is None:
                annotation["category"] = default_category
                annotation["method"] = "undecodable"
            else:
                if layer_index not in feature_cache:
                    feature_cache[layer_index] = fetcher.get(*layer_index)
                details = feature_cache[layer_index]
                description = details.get("description", "")
                top_tokens = details.get("top_tokens", [])
                annotation["description"] = description

                text = " ".join(filter(None, [node.get("clerp", ""), description, " ".join(top_tokens)]))
                category, matched = classify_text(text, _compiled=compiled)
                if category is not None:
                    annotation.update(category=category, method="keyword", matched_terms=matched)
                elif llm_classifier is not None:
                    llm_category = llm_classifier(description, top_tokens)
                    if llm_category in CATEGORIES:
                        annotation.update(category=llm_category, method="llm")
                if annotation["category"] is None:
                    annotation.update(category=default_category, method="default")

                if fill_clerp and description and not node.get("clerp"):
                    node["clerp"] = description[:120]
        else:
            annotation["category"] = CATEGORY_STRUCTURAL
            annotation["method"] = "unrecognized_feature_type"

        node[METADATA_KEY] = annotation
        counts[annotation["category"]] += 1
        methods[annotation["method"]] += 1

    metadata[SUMMARY_KEY] = _build_summary(graph, counts, methods)
    graph["metadata"] = metadata
    logger.info("Tagged %s: %s", metadata.get("slug", "graph"), dict(counts))
    return graph


def _build_summary(graph: dict[str, Any], counts: Counter, methods: Counter) -> dict[str, Any]:
    """Node counts per category plus each category's share of total attribution mass.

    Attribution mass for a category = sum of |link weight| over links whose
    source or target node carries that category.
    """
    category_by_id = {n["node_id"]: n.get(METADATA_KEY, {}).get("category") for n in graph.get("nodes", [])}
    mass: dict[str, float] = defaultdict(float)
    total = 0.0
    for link in graph.get("links", []):
        weight = abs(link.get("weight", 0.0))
        total += weight
        touched = {category_by_id.get(link.get("source")), category_by_id.get(link.get("target"))}
        for category in touched:
            if category:
                mass[category] += weight
    return {
        "node_counts": dict(counts),
        "classification_methods": dict(methods),
        "attribution_mass_share": {cat: (mass[cat] / total if total else 0.0) for cat in CATEGORIES},
        "total_abs_edge_weight": total,
    }
