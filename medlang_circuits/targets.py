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

``resolve_target()`` and ``read_exact()`` read a named token's next-token
probability from the logits a graph's service returned - the input to the
Wording gap delta metric. Since 2026-10-07 a read is exact: it records the
probability of the target token itself, or records the target as missing with
a named reason, and never another token's value. ``target_probability()`` is
the earlier prefix-tolerant read that produced the hosted values published
before that date; it is kept so those values can be reproduced and audited
(``scripts/audit_target_reads.py``), not for new measurements.
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

# How many top logits the predictive spread keeps for display by default.
TOP_K_SPREAD_DEFAULT = 5

_CLERP_PROB_RE = re.compile(r"^(.*?)\s*\(p=([0-9.]+)\)\s*$")


def _norm(token: str) -> str:
    return token.strip().lower()


_HOSTED_OUTPUT_RE = re.compile(r'^Output\s+"(.*)"$', re.S)


def bare_token(label: str) -> str:
    """Bare lowercase next-token text: hosted logit labels arrive wrapped as
    'Output " word"'; local/test labels are the plain token."""
    match = _HOSTED_OUTPUT_RE.match(label.strip())
    return _norm(match.group(1) if match else label)


def anchor_matches(label: str, anchor: str) -> bool:
    """Wordpiece-tolerant anchor match.

    Tokenizers split intended targets: the trace shows ' anti' for
    ' antihistamines', ' ant' for ' antacid'. A traced token that is a
    leading piece of the anchor (or vice versa) counts as the anchor,
    with a >=3-character guard so stub tokens can't match everything;
    exact matches work at any length.
    """
    token_text, anchor_text = bare_token(label), bare_token(anchor)
    if not token_text or not anchor_text:
        return False
    if token_text == anchor_text:
        return True
    return (min(len(token_text), len(anchor_text)) >= 3
            and (anchor_text.startswith(token_text) or token_text.startswith(anchor_text)))


def display_token(label: str | None) -> str:
    """Case-preserving display form of a logit token: strips the hosted
    'Output "..."' wrapper and whitespace, nothing else. (bare_token also
    lowercases - right for matching, wrong for display: 'Xanax' != 'xanax'.)"""
    if not label:
        return ""
    match = _HOSTED_OUTPUT_RE.match(label.strip())
    return (match.group(1) if match else label).strip()


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


def logit_spread(graph: dict[str, Any], k: int = TOP_K_SPREAD_DEFAULT) -> list[tuple[str, float]]:
    """Top-k (token, probability) pairs at the final logit layer, best first."""
    scored = []
    for node in _logit_nodes(graph):
        token, prob = parse_logit_clerp(node.get("clerp"))
        if prob is not None:
            scored.append((token, prob))
    return sorted(scored, key=lambda pair: -pair[1])[:k]


def select_logits(
    graph: dict[str, Any],
    targets: AttributionTargets | None = None,
    keep_top_k: int | None = TOP_K_SPREAD_DEFAULT,
) -> dict[str, Any]:
    """Prune the graph's logit set to the predictive spread, in place.

    Keeps the union of: the top ``keep_top_k`` logits by probability (the
    predictive spread), any logits matching ``targets``, and logits whose
    probability can't be parsed (unrankable). Everything else - and any links
    touching it - is removed. Unlike ``retarget_graph`` this preserves the
    surrounding distribution so the spread of competing predictions stays
    visible. Records ``metadata["logit_selection"]`` and returns the info dict.
    """
    logits = _logit_nodes(graph)
    parsed = {n["node_id"]: parse_logit_clerp(n.get("clerp")) for n in logits}
    keep_ids = {nid for nid, (_, prob) in parsed.items() if prob is None}
    if targets:
        keep_ids |= {nid for nid, (token, _) in parsed.items() if targets.matches(token)}
    if keep_top_k:
        ranked = sorted(
            (nid for nid, (_, prob) in parsed.items() if prob is not None),
            key=lambda nid: -parsed[nid][1],
        )
        keep_ids |= set(ranked[:keep_top_k])

    dropped = [n for n in logits if n["node_id"] not in keep_ids]
    info: dict[str, Any] = {
        "keep_top_k": keep_top_k,
        "requested_targets": list(targets.tokens) if targets else [],
        "kept": [n.get("clerp") for n in logits if n["node_id"] in keep_ids],
        "dropped": [n.get("clerp") for n in dropped],
    }
    if dropped:
        dropped_ids = {n["node_id"] for n in dropped}
        graph["nodes"] = [n for n in graph.get("nodes", []) if n["node_id"] not in dropped_ids]
        graph["links"] = [
            link
            for link in graph.get("links", [])
            if link.get("source") not in dropped_ids and link.get("target") not in dropped_ids
        ]
    graph.setdefault("metadata", {})["logit_selection"] = info
    return info


def target_probability(
    graph: dict[str, Any],
    anchor: str | None = None,
    targets: AttributionTargets | None = None,
) -> tuple[str, float] | None:
    """Return (token, probability) for the target medical token in this graph.

    LEGACY READ, kept to reproduce and audit values published before
    2026-10-07; new measurements use ``resolve_target`` and ``read_exact``.
    With an ``anchor`` it keeps the most probable logit that ``anchor_matches``
    accepts, a prefix match in either direction, so a likelier neighbour's
    probability is returned under the target's name: ' ant' read as ' anti'
    (the neighbour begins with the target) and ' antibiotic' read as ' anti'
    (the neighbour is the target's first part).

    Selection order: the explicit ``anchor`` token if present among the traced
    logits, else the best-probability match from ``targets``, else the graph's
    top logit. Returns None when an anchor/targets filter was given but nothing
    matches (the caller decides how to report a missing target). Anchor
    matching is wordpiece-tolerant and understands hosted 'Output "..."'
    labels - see ``anchor_matches``.
    """
    candidates: list[tuple[str, float]] = []
    for node in _logit_nodes(graph):
        token, prob = parse_logit_clerp(node.get("clerp"))
        if prob is not None:
            candidates.append((token, prob))
    if not candidates:
        return None
    if anchor is not None:
        matches = [c for c in candidates if anchor_matches(c[0], anchor)]
        return max(matches, key=lambda c: c[1]) if matches else None
    if targets is not None:
        matches = [c for c in candidates if targets.matches(c[0])]
        return max(matches, key=lambda c: c[1]) if matches else None
    return max(candidates, key=lambda c: c[1])


# ---------------------------------------------------------------------------
# Exact target reads (2026-10-07)
# ---------------------------------------------------------------------------
#
# A read records the probability of exactly the target token. Token identity is
# compared on ``token_key``: the text unwrapped from the hosted 'Output "..."'
# label, with the leading space normalised the way tokenizers mark it (leading
# whitespace and the SentencePiece / byte-level space markers removed), and
# nothing else changed - no case folding, no prefix tolerance. The one
# tolerance kept is the existing, intended wordpiece rule on the REFERENCE side
# (``resolve_target``): an intended target the tokenizer splits (' antacid'
# traced as ' ant', a multi-word target's first word) is measured on its
# leading piece, and the record says so. Every other side is read with
# ``read_exact`` on the measured token, so a likelier neighbour's probability
# is never recorded under the target's name.

# Read record ``status`` values that carry a probability.
FOUND_STATUSES = ("exact", "leading_wordpiece")

# SentencePiece '▁' and byte-level BPE 'Ġ': how tokenizers spell a leading space.
SPACE_MARKERS = "\u2581\u0120"

# The shortest leading piece accepted for a split target, as anchor_matches has
# it: stub tokens (' a', ' an') must not stand for every word they begin.
MIN_PIECE_CHARS = 3

# How many prefix candidates a missing read lists as diagnostics.
PREFIX_CANDIDATES_MAX = 5


def token_text(label: str | None) -> str | None:
    """The token text exactly as returned: the hosted 'Output "..."' wrapper
    removed and nothing else (case and whitespace kept)."""
    if not isinstance(label, str):
        return None
    match = _HOSTED_OUTPUT_RE.match(label.strip())
    return match.group(1) if match else label


def _canonical(label: str | None) -> str:
    """token_text with leading space markers spelt as ordinary spaces."""
    text = token_text(label) or ""
    stripped = text.lstrip(SPACE_MARKERS + " ")
    lead = text[: len(text) - len(stripped)]
    return " " * len(lead) + stripped


def token_key(label: str | None) -> str:
    """Identity key for an exact read: the token text with its leading space
    normalised away (whitespace and SentencePiece/byte-level markers), case and
    every other character kept. '' for a label with no text."""
    return (token_text(label) or "").lstrip(SPACE_MARKERS + " \t\r\n")


def returned_logits(graph: dict[str, Any]) -> list[tuple[str, float]]:
    """Every logit the service returned for this graph, (label, probability),
    most probable first: the graph's logit nodes plus those ``select_logits``
    pruned for display (recorded in ``metadata.logit_selection.dropped``).
    Logits whose probability cannot be parsed are left out."""
    clerps = [n.get("clerp") for n in _logit_nodes(graph)]
    selection = (graph.get("metadata") or {}).get("logit_selection") or {}
    clerps += list(selection.get("dropped") or [])
    scored = []
    for clerp in clerps:
        token, prob = parse_logit_clerp(clerp)
        if prob is not None:
            scored.append((token, prob))
    return sorted(scored, key=lambda pair: -pair[1])


def _rank(logits: list[tuple[str, float]], prob: float) -> int:
    """1-based rank of a probability among the returned logits (ties share the best rank)."""
    return 1 + sum(1 for _, p in logits if p > prob)


def prefix_relation(token: str | None, target: str | None) -> str | None:
    """How a returned token relates to a target, compared case-insensitively
    with the MIN_PIECE_CHARS guard (the relations the legacy prefix-tolerant
    read accepted): 'token_is_leading_piece_of_target' (' anti' for
    ' antibiotic'), 'target_is_leading_piece_of_token' (' anti' for ' ant'),
    'case_variant' (' Ant' for ' ant'), or None. Diagnostic only; an exact
    token is not a candidate."""
    tok, tgt = token_key(token), token_key(target)
    if not tok or not tgt or tok == tgt:
        return None
    a, b = tok.casefold(), tgt.casefold()
    if a == b:
        return "case_variant"
    if min(len(a), len(b)) < MIN_PIECE_CHARS:
        return None
    if b.startswith(a):
        return "token_is_leading_piece_of_target"
    if a.startswith(b):
        return "target_is_leading_piece_of_token"
    return None


def prefix_candidates(logits: list[tuple[str, float]], target: str | None,
                      limit: int = PREFIX_CANDIDATES_MAX) -> list[list[Any]]:
    """Diagnostics for a target that was not read: the returned tokens that
    ``prefix_relation`` relates to it, nearest first (closest length, then most
    probable), as [label, probability, relation]."""
    target_len = len(token_key(target))
    found = [(label, prob, rel) for label, prob in logits
             if (rel := prefix_relation(label, target)) is not None]
    found.sort(key=lambda c: (abs(len(token_key(c[0])) - target_len), -c[1]))
    return [[label, prob, rel] for label, prob, rel in found[:limit]]


def _missing(reason: str, logits: list[tuple[str, float]], target: str | None) -> dict[str, Any]:
    record: dict[str, Any] = {"status": "missing", "reason": reason, "returned": len(logits)}
    if logits and target:
        record["prefix_candidates"] = prefix_candidates(logits, target)
    return record


def _exact_hits(logits: list[tuple[str, float]], target: str) -> list[tuple[str, float]]:
    """Returned logits whose key is the target's. When the leading-space
    normalisation leaves several (' ant' and 'ant'), the one spelt like the
    target is kept; if that does not leave exactly one, all are returned."""
    key = token_key(target)
    hits = [(label, prob) for label, prob in logits if token_key(label) == key]
    if len(hits) > 1:
        same = [h for h in hits if _canonical(h[0]) == _canonical(target)]
        if len(same) == 1:
            return same
    return hits


def _found(logits: list[tuple[str, float]], status: str, label: str, prob: float) -> dict[str, Any]:
    return {"status": status, "token": label, "probability": prob,
            "rank": _rank(logits, prob), "returned": len(logits)}


def read_exact(graph: dict[str, Any], token: str | None) -> dict[str, Any]:
    """Read exactly ``token``'s probability from the logits the service returned.

    Returns a read record: ``{"status": "exact", "token", "probability",
    "rank", "returned"}`` when one returned logit is the token, else
    ``{"status": "missing", "reason", "returned", "prefix_candidates"}`` with
    reason ``no_target_token`` (nothing to read), ``no_returned_logits``,
    ``target_not_in_returned_logits`` or ``ambiguous_exact_match``. A missing
    read carries no probability: the prefix candidates are diagnostics, never
    a value. ``rank`` above the stored predictive spread's length means the
    value is not visible in ``predictive_spread``.
    """
    logits = returned_logits(graph)
    if not token_key(token):
        return {"status": "missing", "reason": "no_target_token", "returned": len(logits)}
    if not logits:
        return _missing("no_returned_logits", logits, token)
    hits = _exact_hits(logits, token)
    if len(hits) == 1:
        return _found(logits, "exact", *hits[0])
    if hits:
        record = _missing("ambiguous_exact_match", logits, token)
        record["exact_candidates"] = [[label, prob] for label, prob in hits]
        return record
    return _missing("target_not_in_returned_logits", logits, token)


def resolve_target(graph: dict[str, Any], intended: str | None) -> dict[str, Any]:
    """Which returned token stands for the ``intended`` target on the reference
    side, and its probability.

    ``exact``: a returned token is the intended target (``read_exact``).
    ``leading_wordpiece``: none is, but returned tokens are proper leading
    pieces of it, case-sensitive and at least MIN_PIECE_CHARS long - a target
    the tokenizer splits (' ant' for ' antacid', the first word of a
    multi-word target). The likeliest piece is measured, as the earlier read
    did, and every other piece is listed in ``alternatives``.
    ``missing``: neither; the record names the reason and lists the prefix
    candidates. A returned token that only begins with the target
    (' antibiotics' for ' antibiotic') is never taken: it is another token.
    """
    exact = read_exact(graph, intended)
    if exact["status"] == "exact" or exact.get("reason") != "target_not_in_returned_logits":
        return exact
    logits = returned_logits(graph)
    key = token_key(intended)
    pieces = [(label, prob) for label, prob in logits
              if len(token_key(label)) >= MIN_PIECE_CHARS
              and len(token_key(label)) < len(key) and key.startswith(token_key(label))]
    if not pieces:
        return exact
    label, prob = max(pieces, key=lambda c: c[1])
    record = _found(logits, "leading_wordpiece", label, prob)
    others = [[lab, p] for lab, p in pieces if lab != label]
    if others:
        record["alternatives"] = others
    return record
