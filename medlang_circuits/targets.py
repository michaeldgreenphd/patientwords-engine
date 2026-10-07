"""Target-token forcing: attribute from named substantive tokens, not articles.

The tracer attributes from the top salient logits, and the single most probable
next token is often a grammatical article (" a", " the") rather than the
substantive recommendation. ``AttributionTargets`` names the tokens you care
about (e.g. [" xtok", " ytok"]) and this module applies them at the
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

    Tokenizers split intended targets: the trace shows ' xabi' for
    ' xabihomes', ' xab' for ' xabmel'. A traced token that is a
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
    """Split a logit node label like 'xtok (p=0.62)' into (token, probability)."""
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
    """Named next-token targets to attribute from, e.g. (" xtok", " ytok")."""

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
    keep_labels: Sequence[str] = (),
) -> dict[str, Any]:
    """Prune the graph's logit set to the predictive spread, in place.

    Keeps the union of: the top ``keep_top_k`` logits by probability (the
    predictive spread), any logits matching ``targets``, any logit whose label
    is in ``keep_labels`` (the measured target, so a target read at rank 6-10
    keeps its node in the rendered graph; ``metric_view`` removes those nodes
    again for every metric), and logits whose probability can't
    be parsed (unrankable). Everything else - and any links touching it - is
    removed. Unlike ``retarget_graph`` this preserves the surrounding
    distribution so the spread of competing predictions stays visible. Records
    ``metadata["logit_selection"]`` and returns the info dict.
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
    # Nodes kept only for the read: recorded so every metric can be computed without them (metric_view).
    measurement_ids = ({nid for nid, (token, _) in parsed.items() if token in set(keep_labels)} - keep_ids
                       if keep_labels else set())
    keep_ids |= measurement_ids

    dropped = [n for n in logits if n["node_id"] not in keep_ids]
    info: dict[str, Any] = {
        "keep_top_k": keep_top_k,
        "requested_targets": list(targets.tokens) if targets else [],
        **({"kept_for_measurement": list(keep_labels),
            "kept_for_measurement_ids": sorted(measurement_ids)} if keep_labels else {}),
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


def metric_view(graph: dict[str, Any]) -> dict[str, Any]:
    """The graph as top-K pruning alone leaves it: the logit nodes ``select_logits``
    kept only for the read (``kept_for_measurement_ids``) and their links removed.
    Every metric and the predictive spread are computed on this view, so keeping
    a node for the read and the render changes no published number. Returns the
    graph itself when nothing was kept for the read."""
    selection = (graph.get("metadata") or {}).get("logit_selection") or {}
    extra = set(selection.get("kept_for_measurement_ids") or [])
    if not extra:
        return graph
    view = dict(graph)
    view["nodes"] = [n for n in graph.get("nodes", []) if n.get("node_id") not in extra]
    view["links"] = [link for link in graph.get("links", [])
                     if link.get("source") not in extra and link.get("target") not in extra]
    return view


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
    probability is returned under the target's name: ' xab' read as ' xabi'
    (the neighbour begins with the target) and ' xabicor' read as ' xabi'
    (the neighbour is the target's first part). It also folds case.

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
# A read records the probability of exactly the target token. Identity is
# ``same_token``: a hosted label ('Output "..."') is compared byte for byte on
# ``token_form``, its text with the wrapper removed and a leading SentencePiece
# or byte-level space marker spelt as a space - so the leading space counts
# (' xab' is not 'xab') and so does case. A bare label (local/test format) has
# had its surrounding whitespace stripped by parse_logit_clerp, so it can only
# be compared without its leading space. The one tolerance kept is the
# existing, intended wordpiece rule on the REFERENCE side (``resolve_target``):
# an intended target the tokenizer splits (' xabmel' traced as ' xab', a
# multi-word target's first word) is measured on its leading piece, and the
# record says so. Every other side is read with ``read_exact`` on the measured
# token, so a likelier neighbour's probability is never recorded under the
# target's name.

# Read record ``status`` values that carry a probability.
FOUND_STATUSES = ("exact", "leading_wordpiece")

# SentencePiece U+2581 and byte-level BPE U+0120: how tokenizers spell a leading space.
SPACE_MARKERS = "▁Ġ"

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


def is_hosted_label(label: str | None) -> bool:
    """A hosted logit label, 'Output "..."': its text keeps its leading space."""
    return isinstance(label, str) and _HOSTED_OUTPUT_RE.match(label.strip()) is not None


def token_form(label: str | None) -> str:
    """The text an exact read compares: ``token_text`` with each leading space
    marker spelt as an ordinary space. The leading space itself, case and every
    other character are kept."""
    text = token_text(label) or ""
    body = text.lstrip(SPACE_MARKERS + " ")
    lead = text[: len(text) - len(body)]
    return lead.translate({ord(m): " " for m in SPACE_MARKERS}) + body


def token_key(label: str | None) -> str:
    """Loose key: the token text without its leading whitespace or space
    markers, case kept. For diagnostics, for telling whether a label has any
    text, and for bare labels whose spacing is already gone - never to equate
    two hosted tokens ('Output " xab"' and 'Output "xab"' share this key)."""
    return (token_text(label) or "").lstrip(SPACE_MARKERS + " \t\r\n")


def same_token(label: str | None, target: str | None) -> bool:
    """Whether a returned logit ``label`` is the ``target`` token.

    A hosted label is compared on ``token_form`` (leading space significant,
    markers read as a space); a bare label, whose spacing parse_logit_clerp
    has already stripped, on ``token_key``. A label with no text is never a
    target."""
    if not token_key(label) or not token_key(target):
        return False
    if is_hosted_label(label):
        return token_form(label) == token_form(target)
    return token_key(label) == token_key(target)


def _is_leading_piece(label: str, intended: str) -> bool:
    """``label`` is a proper leading piece of ``intended``, case-sensitive, at
    least MIN_PIECE_CHARS long, compared the way ``same_token`` compares."""
    if len(token_key(label)) < MIN_PIECE_CHARS:
        return False
    piece, whole = ((token_form(label), token_form(intended)) if is_hosted_label(label)
                    else (token_key(label), token_key(intended)))
    return len(piece) < len(whole) and whole.startswith(piece)


def _clerps(graph: dict[str, Any]) -> list[Any]:
    """Every logit label the service returned: the graph's logit nodes plus
    those ``select_logits`` pruned for display."""
    clerps = [n.get("clerp") for n in _logit_nodes(graph)]
    selection = (graph.get("metadata") or {}).get("logit_selection") or {}
    return clerps + list(selection.get("dropped") or [])


def returned_logits(graph: dict[str, Any]) -> list[tuple[str, float]]:
    """Every logit the service returned for this graph, (label, probability),
    most probable first: the graph's logit nodes plus those ``select_logits``
    pruned for display (recorded in ``metadata.logit_selection.dropped``).
    Logits whose probability cannot be parsed are left out (``read_exact``
    names that case when it is the target)."""
    scored = []
    for clerp in _clerps(graph):
        token, prob = parse_logit_clerp(clerp)
        if prob is not None:
            scored.append((token, prob))
    return sorted(scored, key=lambda pair: -pair[1])


def _rank(logits: list[tuple[str, float]], prob: float) -> int:
    """1-based rank of a probability among the returned logits (ties share the best rank)."""
    return 1 + sum(1 for _, p in logits if p > prob)


def prefix_relation(token: str | None, target: str | None) -> str | None:
    """How a returned token that is not the target relates to it, compared
    without the leading space and case-insensitively, with the MIN_PIECE_CHARS
    guard (the relations the legacy prefix-tolerant read accepted):
    'space_variant' (the same text with a different leading space),
    'case_variant' (' Xab' for ' xab'), 'token_is_leading_piece_of_target'
    (' xabi' for ' xabicor'), 'target_is_leading_piece_of_token' (' xabi' for
    ' xab'), or None. Diagnostic only."""
    if same_token(token, target):
        return None
    tok, tgt = token_key(token), token_key(target)
    if not tok or not tgt:
        return None
    if tok == tgt:
        return "space_variant"
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


def _found(logits: list[tuple[str, float]], status: str, label: str, prob: float) -> dict[str, Any]:
    return {"status": status, "token": label, "probability": prob,
            "rank": _rank(logits, prob), "returned": len(logits)}


def read_exact(graph: dict[str, Any], token: str | None) -> dict[str, Any]:
    """Read exactly ``token``'s probability from the logits the service returned.

    Returns a read record: ``{"status": "exact", "token", "probability",
    "rank", "returned"}`` when one returned logit is the token (``same_token``),
    else ``{"status": "missing", "reason", "returned", "prefix_candidates"}``
    with reason ``no_target_token`` (nothing to read), ``no_returned_logits``,
    ``unparseable_probability`` (the token was returned without a probability
    that parses), ``target_not_in_returned_logits`` or
    ``ambiguous_exact_match``. A missing read carries no probability: the
    prefix candidates are diagnostics, never a value. ``rank`` above the stored
    predictive spread's length means the value is not visible in
    ``predictive_spread``.
    """
    logits = returned_logits(graph)
    if not token_key(token):
        return {"status": "missing", "reason": "no_target_token", "returned": len(logits)}
    hits = [(label, prob) for label, prob in logits if same_token(label, token)]
    if len(hits) == 1:
        return _found(logits, "exact", *hits[0])
    if hits:
        record = _missing("ambiguous_exact_match", logits, token)
        record["exact_candidates"] = [[label, prob] for label, prob in hits]
        return record
    unparsed = [parse_logit_clerp(c)[0] for c in _clerps(graph) if parse_logit_clerp(c)[1] is None]
    if any(same_token(label, token) for label in unparsed):
        return _missing("unparseable_probability", logits, token)
    if not logits:
        return _missing("no_returned_logits", logits, token)
    return _missing("target_not_in_returned_logits", logits, token)


def _unspaced(intended: str) -> bool:
    """An intended target written without a leading space or marker."""
    return bool(intended) and intended[:1] not in SPACE_MARKERS + " \t\r\n"


def resolve_target(graph: dict[str, Any], intended: str | None) -> dict[str, Any]:
    """Which returned token stands for the ``intended`` target on the reference
    side, and its probability.

    ``exact``: a returned token is the intended target (``read_exact``).
    ``leading_wordpiece``: none is, but returned tokens are proper leading
    pieces of it, case-sensitive, leading space included, at least
    MIN_PIECE_CHARS long - a target the tokenizer splits (' xab' for
    ' xabmel', the first word of a multi-word target). The likeliest piece is
    measured, as the earlier read did, and every other piece is listed in
    ``alternatives``. ``missing``: neither; the record names the reason and
    lists the prefix candidates. A returned token that only begins with the
    target (' xabicors' for ' xabicor') is never taken: it is another token.
    When the intended token itself was returned but cannot be read
    (``unparseable_probability``, ``ambiguous_exact_match``), that failure is
    the record: no shorter piece stands in for it. When the likeliest piece
    was returned more than once, the read is missing with reason
    ``ambiguous_wordpiece`` and the duplicates in ``wordpiece_candidates``, as
    for an ambiguous exact token: no value is guessed.

    An intended target written without its leading space ('xab', as some
    pairs files spell it) is read with the space first (' xab': after a prompt
    that ends in a word, the next word's token carries it), then as written.
    The record always says which: ``"intended_spacing"`` is
    ``"leading_space_added"`` (the spaced form was read), ``"as_written"``
    (only the unspaced form was returned) or ``"both_tried"`` (neither was
    read; ``forms_tried`` lists them). A preferred spaced form that is
    returned but unparseable or ambiguous is that failure, recorded with
    ``leading_space_added``: the as-written spelling never stands in for it.
    """
    if not token_key(intended):
        return read_exact(graph, intended)
    forms = [" " + intended, intended] if _unspaced(intended) else [intended]
    reads = [read_exact(graph, form) for form in forms]
    for i, (form, exact) in enumerate(zip(forms, reads)):
        if exact["status"] == "exact":
            return _spaced(exact, form, intended)
        if exact.get("reason") in ("unparseable_probability", "ambiguous_exact_match"):
            # This form was returned but cannot be read: report that failure. Neither a later, less preferred
            # spelling nor a shorter leading piece may stand in for it.
            return _spaced(dict(exact), form, intended) if i == 0 else _both_tried(dict(exact), forms)
    logits = returned_logits(graph)
    for form in forms:
        pieces = [(label, prob) for label, prob in logits if _is_leading_piece(label, form)]
        if pieces:
            label, prob = max(pieces, key=lambda c: c[1])
            if sum(1 for lab, _ in pieces if lab == label) > 1:
                # the chosen piece was returned more than once: which value is its own cannot be told
                record = _missing("ambiguous_wordpiece", logits, form)
                record["wordpiece_candidates"] = [[lab, p] for lab, p in pieces if lab == label]
                return _spaced(record, form, intended)
            record = _found(logits, "leading_wordpiece", label, prob)
            others = [[lab, p] for lab, p in pieces if lab != label]
            if others:
                record["alternatives"] = others
            return _spaced(record, form, intended)
    return _both_tried(dict(reads[0]), forms)


def _both_tried(missed: dict[str, Any], forms: list[str]) -> dict[str, Any]:
    if len(forms) > 1:
        missed["intended_spacing"] = "both_tried"
        missed["forms_tried"] = forms
    return missed


def _spaced(record: dict[str, Any], form: str, intended: str) -> dict[str, Any]:
    if _unspaced(intended):
        record["intended_spacing"] = "leading_space_added" if form != intended else "as_written"
    return record
