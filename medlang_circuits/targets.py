"""Target-token forcing: attribute from named substantive tokens, not articles.

The tracer attributes from the top salient logits, and the single most probable
next token is often a grammatical article (" a", " the") rather than the
substantive recommendation. ``AttributionTargets`` names the tokens you care
about (e.g. [" therapist", " hospital"]) and this module applies them at the
two points our pipeline controls:

1. generation - ``to_generation_params()`` widens ``max_n_logits`` so the named
   tokens fall inside the traced salient-logit set, and includes a
   ``force_target_tokens`` passthrough for graph servers whose circuit-tracer
   fork supports native target forcing (unknown fields are ignored by the
   stock server, so this is safe either way);
2. post-processing - ``retarget_graph()`` prunes the graph's logit nodes down
   to the named targets (dropping other logit nodes and their now-dangling
   edges), so visualization and metrics attribute back from the substantive
   token instead of the article.

``target_probability()`` reads a named token's next-token probability from a
graph's logit nodes - the input to the Language Penalty delta metric.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# Widen the traced logit set when forcing targets, so substantive tokens that
# rank below the article still get attribution nodes.
FORCED_TARGET_MAX_N_LOGITS = 15

_CLERP_PROB_RE = re.compile(r"^(.*?)\s*\(p=([0-9.]+)\)\s*$")


def _norm(token: str) -> str:
    return token.strip().lower()


def parse_logit_clerp(clerp: str | None) -> tuple[str, float | None]:
    """Split a logit node label like 'therapist (p=0.62)' into (token, probability)."""
    if not clerp:
        return "", None
    match = _CLERP_PROB_RE.match(clerp)
    if not match:
        return clerp.strip(), None
    try:
        return match.group(1).strip(), min(float(match.group(2)), 1.0)
    except ValueError:
        return match.group(1).strip(), None


@dataclass(frozen=True)
class AttributionTargets:
    """Named next-token targets to attribute from, e.g. (" therapist", " hospital")."""

    tokens: tuple[str, ...]

    @classmethod
    def of(cls, tokens: Sequence[str]) -> "AttributionTargets":
        return cls(tuple(tokens))

    def matches(self, token: str) -> bool:
        return _norm(token) in {_norm(t) for t in self.tokens}

    def to_generation_params(self) -> dict[str, Any]:
        return {
            "max_n_logits": FORCED_TARGET_MAX_N_LOGITS,
            "force_target_tokens": list(self.tokens),
        }


def _logit_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in graph.get("nodes", []) if n.get("feature_type") == "logit"]


def retarget_graph(graph: dict[str, Any], targets: AttributionTargets) -> dict[str, Any]:
    """Prune the graph's logit set down to the named targets, in place.

    Non-matching logit nodes and any links touching them are removed, so all
    remaining attribution flows into the substantive tokens. If no logit node
    matches, the graph is left untouched (with a warning) rather than emptied.
    Returns an info dict; the same info is recorded under
    ``metadata["attribution_targets"]``.
    """
    logits = _logit_nodes(graph)
    matched, dropped = [], []
    for node in logits:
        token, _ = parse_logit_clerp(node.get("clerp"))
        (matched if targets.matches(token) else dropped).append(node)

    info: dict[str, Any] = {
        "requested": list(targets.tokens),
        "kept": [n.get("clerp") for n in matched],
        "dropped": [n.get("clerp") for n in dropped],
        "retargeted": bool(matched),
    }
    if not matched:
        logger.warning(
            "No traced logit matches targets %s (traced: %s); leaving graph untouched. "
            "Consider raising max_n_logits / desired_logit_prob at generation.",
            targets.tokens,
            [n.get("clerp") for n in logits],
        )
    else:
        dropped_ids = {n["node_id"] for n in dropped}
        graph["nodes"] = [n for n in graph.get("nodes", []) if n["node_id"] not in dropped_ids]
        graph["links"] = [
            link
            for link in graph.get("links", [])
            if link.get("source") not in dropped_ids and link.get("target") not in dropped_ids
        ]
    graph.setdefault("metadata", {})["attribution_targets"] = info
    return info


def target_probability(
    graph: dict[str, Any],
    anchor: str | None = None,
    targets: AttributionTargets | None = None,
) -> tuple[str, float] | None:
    """Return (token, probability) for the target medical token in this graph.

    Selection order: the explicit ``anchor`` token if present among the traced
    logits, else the best-probability match from ``targets``, else the graph's
    top logit. Returns None when an anchor/targets filter was given but nothing
    matches (the caller decides how to report a missing target).
    """
    candidates: list[tuple[str, float]] = []
    for node in _logit_nodes(graph):
        token, prob = parse_logit_clerp(node.get("clerp"))
        if prob is not None:
            candidates.append((token, prob))
    if not candidates:
        return None
    if anchor is not None:
        matches = [c for c in candidates if _norm(c[0]) == _norm(anchor)]
        return max(matches, key=lambda c: c[1]) if matches else None
    if targets is not None:
        matches = [c for c in candidates if targets.matches(c[0])]
        return max(matches, key=lambda c: c[1]) if matches else None
    return max(candidates, key=lambda c: c[1])
