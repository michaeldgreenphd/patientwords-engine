"""Batch evaluation harness with four isolated visualization modes.

Input is a JSON file containing an array of pair objects. Common optional
fields on every object: ``target_clinical_token`` (word anchor for the delta
metrics) and ``force_target_tokens`` (AttributionTargets - bypasses
grammatical articles by attributing from named substantive tokens; see
medlang_circuits.targets). Mode-specific fields:

--mode 2panel (default) - direct lexical swap:
    {"top_prompt": "...", "bottom_prompt": "..."}
    The polished two-panel stacked view with the Language Penalty badge.
    (--show-mitigation appends the legacy third translated panel.)

--mode 4quadrant - the morphosyntax-vs-lexicon matrix:
    {"frames": {"standard": "I have{term}, so ...", "nonstandard": "I been had{term}, so ..."},
     "terms":  {"medical": " diabetes", "patient": " the sugar"}}
    (legacy key aliases: frames clinical=standard / patient=nonstandard,
    terms clinical=medical; explicit {"quadrants": {"A": ..., "B": ...,
    "C": ..., "D": ...}} is also accepted with the lettering below).
    Renders the study's generic 2x2 - rows are morphosyntax (standard on
    top), columns are lexicon (patient-derived language left, medical
    lexicon right):
        A - medical lexicon + standard morphosyntax (prestige form)
        B - medical lexicon + nonstandard morphosyntax (variety shift only)
        C - patient language + standard morphosyntax (register shift only)
        D - patient language + nonstandard morphosyntax (both axes shifted)
    with the target probability printed prominently in each box, register
    (lexicon) deltas A->C and B->D in the column gutters and variety
    (morphosyntax) deltas A->B and C->D in the row gutter.

--mode translation - organic downstream mitigation:
    {"patient_prompt": "..."}  (or "bottom_prompt")
    The patient prompt is sent to the Anthropic API for translation into
    standard clinical language; the RAW LLM output is fed natively into a
    completely fresh trace (no template). Renders the vertical chain
    patient prompt -> [LLM translation interstitial] -> natively traced
    translated prompt, with recovered target probabilities as headlines and
    a recovery badge.

--mode dialect - dialect/register syntax variants around a fixed term:
    {"baseline_prompt": "...", "variants": [{"dialect": "...", "prompt": "..."}, ...]}
    (the shape medlang-generate dialects emits). Panel 1 is the baseline
    (standard phrasing); one panel per variant carries its dialect label and
    a delta badge of target-token probability vs. the baseline panel. With
    no target_clinical_token the comparison falls back to the baseline's top
    logit via the usual predictive-spread path.

Every pair writes numbered outputs (index_01.html / index_01.png, ...), the
per-panel tagged graph JSONs, and a batch_summary.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from medlang_circuits.compare_viz import (
    CATEGORY_COLORS,
    NEGATIVE_EDGE_COLOR,
    build_panels,
    render_panels_html,
    render_panels_png,
    render_quadrant_html,
    render_quadrant_png,
)
from medlang_circuits.feature_tagger import annotate_graph
from medlang_circuits.graph_client import (
    add_graph_cli_arguments,
    generate_graph,
    generation_params_from_args,
    resolve_graph_model,
    slugify,
)
from medlang_circuits.neuronpedia_features import FeatureFetcher, NullFetcher
from medlang_circuits.schema_utils import is_feature_node, node_layer_and_index
from medlang_circuits.steering import (
    boost_strength,
    rank_offset,
    steer_ablate,
    top_clinical_features,
    top_offtarget_features,
    top_random_features,
)
from medlang_circuits.targets import (
    display_token,
    TOP_K_SPREAD_DEFAULT,
    AttributionTargets,
    bare_token,
    logit_spread,
    select_logits,
    target_probability,
)
from medlang_circuits.translate import translate_to_clinical

logger = logging.getLogger(__name__)

MODES = ("2panel", "4quadrant", "translation", "dialect")
RECOVERY_COLOR = "#15803d"  # positive deltas share the clinical green
DEFAULT_PNG_DPI = 220  # high-resolution static export

QUAD_KEYS = ("A", "B", "C", "D")
QUAD_LABELS = {
    "A": "A · Medical lexicon + standard morphosyntax (prestige form)",
    "B": "B · Medical lexicon + nonstandard morphosyntax (variety shift only)",
    "C": "C · Patient-derived language + standard morphosyntax (register shift only)",
    "D": "D · Patient-derived language + nonstandard morphosyntax (both axes shifted)",
}
# Grid placement (top-left, top-right, bottom-left, bottom-right): rows are
# morphosyntax (standard on top), columns are lexicon (patient-derived left).
QUAD_GRID_ORDER = ("C", "A", "D", "B")

# Pairwise edge views: each matrix edge as its own two-panel comparison with
# the shared circuit dimmed, so what the single swap changes is the only ink.
QUAD_EDGE_VIEWS = (
    # (tag, from, to, badge kind)
    ("register_standard", "A", "C", "Register shift Δ"),
    ("register_nonstandard", "B", "D", "Register shift Δ"),
    ("variety_medical", "A", "B", "Variety shift Δ"),
    ("variety_patient", "C", "D", "Variety shift Δ"),
)


# Function words that stage the real diagnostic token one position later.
# When a screen fails because BOTH phrasings converge on one of these, the
# probe extends by that token and re-measures at the next position.
PROBE_EXTENSION_TOKENS = frozenset(
    "the a an my his her their our your some this that these those to of for".split()
)


def clinical_mass_fraction(graph: dict[str, Any]) -> float | None:
    """Share of transcoder-feature attribution mass on clinical-tagged features.

    The quantitative form of "medical wording lights up medical reasoning":
    mass is |incident edge weight| summed per feature node; the fraction is
    clinical mass over all feature mass (logits and structural nodes excluded).
    """
    weight: dict[str, float] = defaultdict(float)
    for link in graph.get("links", []):
        w = abs(link.get("weight", 0.0))
        weight[link.get("source")] += w
        weight[link.get("target")] += w
    total = clinical = 0.0
    for node in graph.get("nodes", []):
        if not is_feature_node(node):
            continue
        w = weight[node["node_id"]]
        total += w
        if (node.get("medlang") or {}).get("category") == "clinical":
            clinical += w
    return round(clinical / total, 4) if total else None


def error_node_share(graph: dict[str, Any]) -> float | None:
    """Share of attribution mass carried by MLP reconstruction-error nodes.

    Transcoders only approximate each MLP; the residual appears as error
    nodes. This is the trace's honesty metric: the fraction of attribution
    the feature basis does NOT explain (0.0 = fully explained).
    """
    weight: dict[str, float] = defaultdict(float)
    for link in graph.get("links", []):
        w = abs(link.get("weight", 0.0))
        weight[link.get("source")] += w
        weight[link.get("target")] += w
    total = err = 0.0
    for node in graph.get("nodes", []):
        ftype = node.get("feature_type")
        if ftype == "mlp reconstruction error":
            err += weight[node["node_id"]]
            total += weight[node["node_id"]]
        elif is_feature_node(node):
            total += weight[node["node_id"]]
    return round(err / total, 4) if total else None


def _path_layer_rank(node: dict[str, Any]) -> int:
    if node.get("feature_type") == "embedding":
        return -1
    if node.get("feature_type") == "logit":
        return 10**6
    try:
        return int(node.get("layer"))
    except (TypeError, ValueError):
        return 0


def top_attribution_path(
    graph: dict[str, Any], target_node_id: str | None = None
) -> list[dict[str, Any]]:
    """Strongest embedding-to-logit attribution chain, one node per hop.

    Built by a greedy backtrace from the target logit: at each hop follow the
    strongest incoming |edge weight| from a strictly lower layer until an
    embedding is reached. (A max-product DP would collapse to a single strong
    direct edge; the greedy walk keeps the multi-hop story through features.)
    The result reads as the graph's one-line causal story.
    """
    nodes = {n["node_id"]: n for n in graph.get("nodes", [])}
    links = graph.get("links", [])
    if not nodes or not links:
        return []
    max_w = max((abs(link.get("weight", 0.0)) for link in links), default=1.0) or 1.0

    # Greedy backtrace from the target: at each node follow the strongest
    # incoming |weight| edge (from a strictly lower layer) until reaching an
    # embedding. A max-product DP would collapse to a single strong direct
    # edge; the greedy chain preserves the multi-hop story through features.
    preds: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for link in links:
        s, t = link.get("source"), link.get("target")
        if s not in nodes or t not in nodes:
            continue
        if _path_layer_rank(nodes[t]) <= _path_layer_rank(nodes[s]):
            continue
        preds[t].append((abs(link.get("weight", 0.0)) / max_w, s))

    if target_node_id is None:
        logits = [n for n in nodes.values()
                  if n.get("feature_type") == "logit" and preds.get(n["node_id"])]
        if not logits:
            return []
        target_node_id = max(
            logits,
            key=lambda n: max(w for w, _ in preds[n["node_id"]]),
        )["node_id"]
    if target_node_id not in nodes:
        return []

    chain = [target_node_id]
    seen = {target_node_id}
    while len(chain) < 24:
        options = [(w, s) for w, s in preds.get(chain[-1], []) if s not in seen]
        if not options:
            break
        _, nxt = max(options)
        chain.append(nxt)
        seen.add(nxt)
        if nodes[nxt].get("feature_type") == "embedding":
            break
    chain.reverse()

    out = []
    for nid in chain:
        n = nodes[nid]
        med = n.get("medlang") or {}
        out.append({
            "node_id": nid,
            "layer": n.get("layer"),
            "feature_type": n.get("feature_type"),
            "category": med.get("category"),
            "label": (med.get("description") or n.get("clerp") or "")[:80],
        })
    return out


def path_text(path: list[dict[str, Any]]) -> str | None:
    """Render a top_attribution_path as a compact readable chain."""
    if not path:
        return None
    steps = []
    for p in path:
        label = (p.get("label") or "").strip()
        if p.get("feature_type") == "embedding":
            steps.append(label or "embedding")
        elif p.get("feature_type") == "logit":
            steps.append(label or "logit")
        else:
            cat = (p.get("category") or "?")[:1].upper()
            steps.append(f"[L{p.get('layer')}·{cat}] {label[:52]}")
    return " → ".join(steps)


def _feature_identities(graph: dict[str, Any]) -> dict[tuple[int, int], list[str]]:
    """Map (layer, feature index) -> node_ids for the graph's transcoder features."""
    meta = graph.get("metadata", {})
    schema_version, scan = meta.get("schema_version"), meta.get("scan", "gemma-2-2b")
    identities: dict[tuple[int, int], list[str]] = {}
    for node in graph.get("nodes", []):
        if not is_feature_node(node):
            continue
        key = node_layer_and_index(node, schema_version, scan)
        if key is not None:
            identities.setdefault(key, []).append(node["node_id"])
    return identities


def shared_feature_dimming(
    graph_a: dict[str, Any], graph_b: dict[str, Any]
) -> tuple[set[str], set[str], dict[str, int]]:
    """Node_ids of features PRESENT IN BOTH graphs (to dim), plus diff counts.

    Feature identity is (layer, feature index) - position-independent, so a
    feature that fires in both prompts is background context however the
    tokens moved. Everything else (features unique to one side, logits,
    structural nodes) keeps full ink.
    """
    ids_a, ids_b = _feature_identities(graph_a), _feature_identities(graph_b)
    shared = set(ids_a) & set(ids_b)
    dim_a = {node_id for key in shared for node_id in ids_a[key]}
    dim_b = {node_id for key in shared for node_id in ids_b[key]}
    counts = {
        "shared_features": len(shared),
        "unique_to_a": len(set(ids_a) - shared),
        "unique_to_b": len(set(ids_b) - shared),
    }
    return dim_a, dim_b, counts


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _delta_badge(kind: str, p_from: float | None, p_to: float | None) -> dict[str, str] | None:
    """Badge spec for a probability delta, e.g. 'Language Penalty: -45% probability (0.86 -> 0.41)'."""
    if p_from is None or p_to is None:
        return None
    delta = p_to - p_from
    color = NEGATIVE_EDGE_COLOR if delta < 0 else RECOVERY_COLOR
    return {
        "text": f"{kind}: {delta * 100:+.0f}% probability ({p_from:.2f} → {p_to:.2f})",
        "color": color,
    }


def _headline(token: str | None, prob: float | None) -> str | None:
    if token is None or prob is None:
        return None
    return f"prob(\u201c{display_token(token)}\u201d) = {prob:.2f}"


def _generation_params(
    targets: AttributionTargets | None,
    generation_params: dict | None,
    graph_model: str | None = None,
    source_set: str | None = None,
) -> dict:
    params = dict(generation_params or {})
    if graph_model:
        params.setdefault("model_id", graph_model)
    if source_set:
        params.setdefault("source_set", source_set)
    if targets:
        # Widen the salient-logit set and pass tokens through for forks with native forcing.
        for key, value in targets.to_generation_params().items():
            params.setdefault(key, value)
    return params


def _trace(
    prompt: str,
    role: str,
    index: int,
    out_dir: Path,
    backend: str,
    params: dict[str, Any],
    targets: AttributionTargets | None,
    fetcher: Any,
) -> dict[str, Any]:
    """Generate + select the predictive spread + tag one graph, persisting the tagged JSON.

    Logits are pruned to the top-K spread (union any forced targets) instead of
    hard-retargeting, so the cluster of competing predictions stays visible."""
    graph = generate_graph(prompt, slug=slugify(prompt, f"medlang-{role}"), backend=backend, **params)
    select_logits(graph, targets=targets, keep_top_k=TOP_K_SPREAD_DEFAULT)  # before tagging
    annotate_graph(graph, fetcher=fetcher)
    with open(out_dir / f"pair_{index:02d}_{role}.tagged.json", "w", encoding="utf-8") as f:
        json.dump(graph, f)
    return graph


def _resolve_reference(
    graph: dict[str, Any], anchor: str | None, targets: AttributionTargets | None
) -> tuple[str, float] | None:
    """Target medical token on the reference graph: anchor -> forced targets -> top logit."""
    reference = target_probability(graph, anchor=anchor) if anchor else None
    if reference is None and targets:
        reference = target_probability(graph, targets=targets)
    if reference is None:
        reference = target_probability(graph)
    return reference


def _probability_for(graph: dict[str, Any], token: str | None) -> float | None:
    if token is None:
        return None
    result = target_probability(graph, anchor=token)
    return result[1] if result else None


# ---------------------------------------------------------------------------
# Mode 1: 2panel (direct lexical swap; legacy --show-mitigation keeps 3 panels)
# ---------------------------------------------------------------------------


def _steer_validation(patient_prompt: str, patient_graph: dict[str, Any], k: int,
                      source_set: str | None = None) -> dict[str, Any]:
    """EXPERIMENTAL: ablate the patient graph's top off-target features and
    record both continuations. Failures are recorded, never raised - the
    measurement stands on its own with or without the causal check."""
    features = top_offtarget_features(patient_graph, k)
    if not features:
        return {"ablated_features": [], "note": "no off-target features to ablate"}
    scan = (patient_graph.get("metadata") or {}).get("scan", "gemma-2-2b")
    kwargs = {"source_set": source_set} if source_set else {}
    result = steer_ablate(patient_prompt, features, model_id=scan, **kwargs)
    return {"ablated_features": features, **result}


def _steer_boost(patient_prompt: str, clinical_graph: dict[str, Any], k: int,
                 source_set: str | None = None) -> dict[str, Any]:
    """EXPERIMENTAL: amplify the CLINICAL graph's top clinical features while
    completing the PATIENT prompt - the listener-side mitigation probe. Where
    ablation asks "did the off-target features cause the miss?", boosting asks
    "does forcing the clinical circuit on recover the target without changing
    the patient's words?". NEURONPEDIA_STEER_RANK_OFFSET skips the top ranks
    (the low-rank faithfulness arm). Failures are recorded, never raised."""
    offset = rank_offset()
    features = top_clinical_features(clinical_graph, k, offset=offset)
    tag: dict[str, Any] = {"rank_offset": offset} if offset else {}
    if not features:
        return {"boosted_features": [], "note": "no clinical features to boost", **tag}
    scan = (clinical_graph.get("metadata") or {}).get("scan", "gemma-2-2b")
    kwargs: dict[str, Any] = {"strength": boost_strength()}
    if source_set:
        kwargs["source_set"] = source_set
    result = steer_ablate(patient_prompt, features, model_id=scan, **kwargs)
    return {"boosted_features": features, **tag, **result}


def _steer_placebo(patient_prompt: str, patient_graph: dict[str, Any], k: int,
                   source_set: str | None = None) -> dict[str, Any]:
    """EXPERIMENTAL: boost k RANDOM features on the patient prompt - the
    placebo arm for _steer_boost. Same strength, same prompt, arbitrary
    features; recoveries here would mean steering itself, not the clinical
    circuit, drives the effect. Failures are recorded, never raised."""
    features = top_random_features(patient_graph, k)
    if not features:
        return {"placebo_features": [], "note": "no feature nodes to draw from"}
    scan = (patient_graph.get("metadata") or {}).get("scan", "gemma-2-2b")
    kwargs: dict[str, Any] = {"strength": boost_strength()}
    if source_set:
        kwargs["source_set"] = source_set
    result = steer_ablate(patient_prompt, features, model_id=scan, **kwargs)
    return {"placebo_features": features, **result}


def evaluate_pair(
    pair: dict[str, Any],
    index: int,
    out_dir: Path,
    backend: str = "hosted",
    show_mitigation: bool = False,
    use_llm_translation: bool = True,
    llm_model: str | None = None,
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    graph_model: str | None = None,
    source_set: str | None = None,
    generation_params: dict[str, Any] | None = None,
    screen_targets: float | None = None,
    steer_validate: int = 0,
    steer_boost: int = 0,
    steer_placebo: int = 0,
) -> dict[str, Any]:
    """Direct lexical swap: clinical top panel vs. patient bottom panel.

    With ``screen_targets`` set, the clinical side is traced FIRST and the
    pair only proceeds if the intended target_clinical_token actually appears
    in the clinical spread at >= that probability (strict anchor match - no
    top-logit fallback for the screening decision). Screened-out pairs are
    still recorded in full - clinical trace, observed spread, machine-readable
    reason - so the batch stays auditable and the failures can be fed back to
    the generator; they just skip the patient trace and the renders.
    """
    anchor = pair.get("target_clinical_token")
    force_tokens = pair.get("force_target_tokens") or []
    targets = AttributionTargets.of(force_tokens) if force_tokens else None
    params = _generation_params(targets, generation_params, graph_model, source_set)

    clinical_prompt, patient_prompt = pair["top_prompt"], pair["bottom_prompt"]
    clinical_graph = _trace(clinical_prompt, "clinical", index, out_dir, backend, params, targets, fetcher)

    screening: dict[str, Any] | None = None
    if screen_targets is not None:
        observed = target_probability(clinical_graph, anchor=anchor) if anchor else None
        extension: str | None = None
        if observed is None or observed[1] < screen_targets:
            # Probe extension: when the phrasing funnels into a function word
            # ('...I should go to' -> ' the'), the article is a staging token,
            # not a failed measurement. Extend BOTH prompts by it and
            # re-measure one position deeper (once).
            top = target_probability(clinical_graph)
            staged = bare_token(top[0]) if top else ""
            if staged in PROBE_EXTENSION_TOKENS:
                extension = staged
                clinical_prompt = clinical_prompt.rstrip() + " " + staged
                patient_prompt = patient_prompt.rstrip() + " " + staged
                logger.info("Pair %d: probe extended by %r, re-tracing clinical side", index, staged)
                clinical_graph = _trace(clinical_prompt, "clinical", index, out_dir,
                                        backend, params, targets, fetcher)
                observed = target_probability(clinical_graph, anchor=anchor) if anchor else None
        if observed is None or observed[1] < screen_targets:
            reason = (
                "intended target not in the traced clinical spread" if observed is None
                else f"intended target below min_prob ({observed[1]:.3f} < {screen_targets})"
            )
            if extension:
                reason += f" (even after probe extension by '{extension}')"
            logger.info("Pair %d screened out: %s", index, reason)
            return {
                "index": index,
                "mode": "2panel",
                "prompts": {"clinical": clinical_prompt, "patient": patient_prompt},
                "target_token": observed[0] if observed else None,
                "probabilities": {"clinical": observed[1] if observed else None, "patient": None},
                "language_penalty": None,
                "clinical_mass": {"clinical": clinical_mass_fraction(clinical_graph)},
                "error_share": {"clinical": error_node_share(clinical_graph)},
                "screening": {
                    "status": "screened_out",
                    "min_prob": screen_targets,
                    "intended_target": anchor,
                    "observed_clinical": list(observed) if observed else None,
                    "probe_extension": extension,
                    "reason": reason,
                },
                "forced_targets": list(force_tokens),
                "predictive_spread": {"clinical": logit_spread(clinical_graph)},
                "outputs": {},
            }
        screening = {
            "status": "passed",
            "min_prob": screen_targets,
            "intended_target": anchor,
            "observed_clinical": list(observed),
            "probe_extension": extension,
        }

    prompts = [clinical_prompt, patient_prompt]
    roles = ["clinical", "patient"]
    translation_method = None
    translation_model = None
    if show_mitigation:
        translation = translate_to_clinical(patient_prompt, use_llm=use_llm_translation, model=llm_model)
        prompts.append(translation["text"])
        roles.append("translated")
        translation_method = translation["method"]
        translation_model = translation.get("model")

    graphs = [clinical_graph] + [
        _trace(prompt, role, index, out_dir, backend, params, targets, fetcher)
        for prompt, role in zip(prompts[1:], roles[1:])
    ]

    reference = _resolve_reference(graphs[0], anchor, targets)
    target_token = reference[0] if reference else None
    probs = [reference[1] if reference else None] + [
        _probability_for(g, target_token) for g in graphs[1:]
    ]

    badges: list[Any] = [_delta_badge("Language Penalty", probs[0], probs[1])]
    if len(graphs) == 3:
        badges.append(_delta_badge("Mitigation Recovery", probs[1], probs[2]))

    panels = build_panels(graphs)
    html_path = out_dir / f"index_{index:02d}.html"
    png_path = out_dir / f"index_{index:02d}.png"
    render_panels_html(panels, str(html_path), badges=badges)
    render_panels_png(panels, str(png_path), badges=badges, dpi=dpi)

    # Circuit diff: the same shared-feature dimming the quadrant edge views
    # use. Features present in both prompts render as faint context, so the
    # full-ink circuitry is exactly what the term swap added or removed.
    dim_c, dim_p, diff_counts = shared_feature_dimming(graphs[0], graphs[1])
    diff_panels = build_panels(
        [graphs[0], graphs[1]],
        labels=[f"Clinical wording: “{prompts[0]}”", f"Patient wording: “{prompts[1]}”"],
        accents=[CATEGORY_COLORS["clinical"], CATEGORY_COLORS["off_target"]],
        value_label_flags=[True, False],
        headlines=[_headline(target_token, probs[0]), _headline(target_token, probs[1])],
        refs=[1, 0],
        dimmed=[dim_c, dim_p],
    )
    diff_badge = {"lines": [
        badges[0] or "Language Penalty: —",
        f"circuit diff: shared features dimmed — {diff_counts['shared_features']} in both · "
        f"{diff_counts['unique_to_a']} only clinical · {diff_counts['unique_to_b']} only patient",
    ]}
    diff_html = out_dir / f"index_{index:02d}_diff.html"
    diff_png = out_dir / f"index_{index:02d}_diff.png"
    render_panels_html(diff_panels, str(diff_html), badges=[diff_badge])
    render_panels_png(diff_panels, str(diff_png), badges=[diff_badge], dpi=dpi)

    result_screening = {"screening": screening} if screening else {}
    return {
        "index": index,
        "mode": "2panel",
        "prompts": dict(zip(roles, prompts)),
        "target_token": target_token,
        "probabilities": dict(zip(roles, probs)),
        "language_penalty": (probs[1] - probs[0]) if probs[0] is not None and probs[1] is not None else None,
        "clinical_mass": {role: clinical_mass_fraction(g) for role, g in zip(roles, graphs)},
        "error_share": {role: error_node_share(g) for role, g in zip(roles, graphs)},
        "top_path": {role: path_text(top_attribution_path(g)) for role, g in zip(roles, graphs)},
        **({"steering": _steer_validation(prompts[1], graphs[1], steer_validate, source_set)}
           if steer_validate else {}),
        **({"steering_boost": _steer_boost(prompts[1], graphs[0], steer_boost, source_set)}
           if steer_boost else {}),
        **({"steering_placebo": _steer_placebo(prompts[1], graphs[1], steer_placebo, source_set)}
           if steer_placebo else {}),
        **result_screening,
        "mitigation_recovery": (
            (probs[2] - probs[1]) if len(probs) == 3 and probs[1] is not None and probs[2] is not None else None
        ),
        "translation_method": translation_method,
        "translation_model": translation_model,
        "forced_targets": list(force_tokens),
        "predictive_spread": {role: logit_spread(g) for role, g in zip(roles, graphs)},
        "circuit_diff": diff_counts,
        "outputs": {"html": str(html_path), "png": str(png_path),
                    "diff_html": str(diff_html), "diff_png": str(diff_png)},
    }


# ---------------------------------------------------------------------------
# Mode 2: 4quadrant (syntax vs. terminology matrix)
# ---------------------------------------------------------------------------


FRAME_ALIASES = {"standard": ("standard", "clinical"), "nonstandard": ("nonstandard", "patient")}
TERM_ALIASES = {"medical": ("medical", "clinical"), "patient": ("patient",)}


def _axis_value(source: dict[str, str], aliases: tuple[str, ...], what: str) -> str:
    for alias in aliases:
        if alias in source:
            return source[alias]
    raise ValueError(f"{what} must define one of {aliases}")


def _quadrant_prompts(pair: dict[str, Any]) -> dict[str, str]:
    """Resolve the four matrix prompts from explicit quadrants or frames x terms.

    Frames are the morphosyntax axis ('standard'/'nonstandard'; legacy aliases
    'clinical'/'patient'), terms the lexicon axis ('medical'/'patient'; legacy
    alias 'clinical' for 'medical'). Lettering follows the generic matrix in
    the module docstring.
    """
    if "quadrants" in pair:
        quadrants = pair["quadrants"]
        missing = [k for k in QUAD_KEYS if k not in quadrants]
        if missing:
            raise ValueError(f"quadrants must define keys {QUAD_KEYS}; missing {missing}")
        return {k: quadrants[k] for k in QUAD_KEYS}
    if "frames" in pair and "terms" in pair:
        frames, terms = pair["frames"], pair["terms"]
        frame = {key: _axis_value(frames, aliases, f"frames[{key}]") for key, aliases in FRAME_ALIASES.items()}
        term = {key: _axis_value(terms, aliases, f"terms[{key}]") for key, aliases in TERM_ALIASES.items()}
        compose = lambda f, t: frame[f].replace("{term}", term[t])  # noqa: E731
        return {
            "A": compose("standard", "medical"),
            "B": compose("nonstandard", "medical"),
            "C": compose("standard", "patient"),
            "D": compose("nonstandard", "patient"),
        }
    raise ValueError("4quadrant mode needs either 'quadrants': {A,B,C,D} or 'frames' + 'terms'")


def evaluate_quadrant(
    pair: dict[str, Any],
    index: int,
    out_dir: Path,
    backend: str = "hosted",
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    graph_model: str | None = None,
    source_set: str | None = None,
    generation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The generic 2x2: morphosyntax rows x lexicon columns (see module docstring)."""
    prompts = _quadrant_prompts(pair)
    anchor = pair.get("target_clinical_token")
    force_tokens = pair.get("force_target_tokens") or []
    targets = AttributionTargets.of(force_tokens) if force_tokens else None
    params = _generation_params(targets, generation_params, graph_model, source_set)

    graphs = {
        key: _trace(prompts[key], f"quad_{key.lower()}", index, out_dir, backend, params, targets, fetcher)
        for key in QUAD_KEYS
    }

    reference = _resolve_reference(graphs["A"], anchor, targets)  # A = prestige form
    target_token = reference[0] if reference else None
    probs = {
        key: (reference[1] if key == "A" and reference else _probability_for(graphs[key], target_token))
        for key in QUAD_KEYS
    }

    panels = build_panels(
        [graphs[k] for k in QUAD_GRID_ORDER],
        labels=[f"{QUAD_LABELS[k]}: “{prompts[k]}”" for k in QUAD_GRID_ORDER],
        # lexicon axis drives accents: medical-lexicon boxes green, patient-language boxes ink
        accents=[CATEGORY_COLORS["off_target"], CATEGORY_COLORS["clinical"],
                 CATEGORY_COLORS["off_target"], CATEGORY_COLORS["clinical"]],
        value_label_flags=[False, True, False, False],  # A is the prestige reference box
        headlines=[_headline(target_token, probs[k]) for k in QUAD_GRID_ORDER],
        refs=[1, 0, 3, 2],  # emphasis diffs across the lexicon axis within each morphosyntax row
    )
    badges = {
        # column gutters: register (lexicon) shift within each morphosyntax row
        "vocab_top": _delta_badge("Register shift Δ", probs["A"], probs["C"]),
        "vocab_bottom": _delta_badge("Register shift Δ", probs["B"], probs["D"]),
        # row gutter: variety (morphosyntax) shift within each lexicon column
        "syntax_left": _delta_badge("Variety shift Δ", probs["C"], probs["D"]),
        "syntax_right": _delta_badge("Variety shift Δ", probs["A"], probs["B"]),
    }

    html_path = out_dir / f"index_{index:02d}.html"
    png_path = out_dir / f"index_{index:02d}.png"
    render_quadrant_html(panels, str(html_path), badges=badges)
    render_quadrant_png(panels, str(png_path), badges=badges, dpi=dpi)

    # One two-panel comparison per matrix edge, shared circuit dimmed: the
    # top panel is the "from" cell, the bottom the "to" cell, and the only
    # full-ink features are the ones the single swap added or removed.
    edge_views: dict[str, dict[str, Any]] = {}
    for tag, key_from, key_to, kind in QUAD_EDGE_VIEWS:
        dim_from, dim_to, counts = shared_feature_dimming(graphs[key_from], graphs[key_to])
        edge_panels = build_panels(
            [graphs[key_from], graphs[key_to]],
            labels=[f"{QUAD_LABELS[k]}: “{prompts[k]}”" for k in (key_from, key_to)],
            accents=[CATEGORY_COLORS["clinical" if key_from in ("A", "B") else "off_target"],
                     CATEGORY_COLORS["clinical" if key_to in ("A", "B") else "off_target"]],
            value_label_flags=[key_from == "A", key_to == "A"],
            headlines=[_headline(target_token, probs[k]) for k in (key_from, key_to)],
            refs=[1, 0],
            dimmed=[dim_from, dim_to],
        )
        edge_badge = {"lines": [
            _delta_badge(f"{kind} ({key_from} → {key_to})", probs[key_from], probs[key_to])
            or f"{kind} ({key_from} → {key_to}): —",
            f"shared circuit dimmed: {counts['shared_features']} features in both · "
            f"{counts['unique_to_a']} only in {key_from} · {counts['unique_to_b']} only in {key_to}",
        ]}
        edge_html = out_dir / f"index_{index:02d}_{tag}.html"
        edge_png = out_dir / f"index_{index:02d}_{tag}.png"
        render_panels_html(edge_panels, str(edge_html), badges=[edge_badge])
        render_panels_png(edge_panels, str(edge_png), badges=[edge_badge], dpi=dpi)
        edge_views[tag] = {
            "from": key_from,
            "to": key_to,
            "delta": (probs[key_to] - probs[key_from])
            if probs[key_from] is not None and probs[key_to] is not None else None,
            **counts,
            "html": str(edge_html),
            "png": str(edge_png),
        }

    def _delta(a: str, b: str) -> float | None:
        return (probs[b] - probs[a]) if probs[a] is not None and probs[b] is not None else None

    return {
        "index": index,
        "mode": "4quadrant",
        "prompts": prompts,
        "target_token": target_token,
        "probabilities": probs,
        "register_shift_deltas": {"standard_morphosyntax": _delta("A", "C"),
                                  "nonstandard_morphosyntax": _delta("B", "D")},
        "variety_shift_deltas": {"medical_lexicon": _delta("A", "B"),
                                 "patient_language": _delta("C", "D")},
        "forced_targets": list(force_tokens),
        "predictive_spread": {key: logit_spread(graphs[key]) for key in QUAD_KEYS},
        "outputs": {"html": str(html_path), "png": str(png_path), "edge_views": edge_views},
    }


# ---------------------------------------------------------------------------
# Mode 3: translation (organic downstream mitigation)
# ---------------------------------------------------------------------------


def evaluate_translation(
    pair: dict[str, Any],
    index: int,
    out_dir: Path,
    backend: str = "hosted",
    use_llm_translation: bool = True,
    llm_model: str | None = None,
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    graph_model: str | None = None,
    source_set: str | None = None,
    generation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Organic mitigation chain: patient prompt -> LLM translation -> fresh native trace.

    No template is forced: the raw text the LLM returns is traced as-is."""
    patient_prompt = pair.get("patient_prompt") or pair["bottom_prompt"]
    anchor = pair.get("target_clinical_token")
    force_tokens = pair.get("force_target_tokens") or []
    targets = AttributionTargets.of(force_tokens) if force_tokens else None
    params = _generation_params(targets, generation_params, graph_model, source_set)

    translation = translate_to_clinical(patient_prompt, use_llm=use_llm_translation, model=llm_model)
    translated_prompt = translation["text"]  # raw LLM output, traced natively below

    patient_graph = _trace(patient_prompt, "patient", index, out_dir, backend, params, targets, fetcher)
    translated_graph = _trace(translated_prompt, "translated", index, out_dir, backend, params, targets, fetcher)

    # The clinical target lives on the translated graph; read the same token on both.
    reference = _resolve_reference(translated_graph, anchor, targets)
    target_token = reference[0] if reference else None
    p_translated = reference[1] if reference else None
    p_patient = _probability_for(patient_graph, target_token)

    panels = build_panels(
        [patient_graph, translated_graph],
        labels=[
            f"Patient wording (original): “{patient_prompt}”",
            f"Translated wording (natively traced): “{translated_prompt}”",
        ],
        accents=[CATEGORY_COLORS["off_target"], CATEGORY_COLORS["clinical"]],
        value_label_flags=[False, True],
        headlines=[_headline(target_token, p_patient), _headline(target_token, p_translated)],
    )
    interstitial_lines: list[Any] = [
        f"LLM Translation ({translation['method']}): “{translated_prompt}”",
    ]
    recovery = _delta_badge("Recovered target probability", p_patient, p_translated)
    if recovery:
        interstitial_lines.append(recovery)
    badges = [{"lines": interstitial_lines}]

    html_path = out_dir / f"index_{index:02d}.html"
    png_path = out_dir / f"index_{index:02d}.png"
    render_panels_html(panels, str(html_path), badges=badges)
    render_panels_png(panels, str(png_path), badges=badges, dpi=dpi)

    return {
        "index": index,
        "mode": "translation",
        "prompts": {"patient": patient_prompt, "translated": translated_prompt},
        "translation_method": translation["method"],
        "translation_model": translation.get("model"),
        "target_token": target_token,
        "probabilities": {"patient": p_patient, "translated": p_translated},
        "recovered_probability": (
            (p_translated - p_patient) if p_patient is not None and p_translated is not None else None
        ),
        "forced_targets": list(force_tokens),
        "predictive_spread": {
            "patient": logit_spread(patient_graph),
            "translated": logit_spread(translated_graph),
        },
        "outputs": {"html": str(html_path), "png": str(png_path)},
    }


# ---------------------------------------------------------------------------
# Mode 4: dialect (syntax/register variants around a fixed term)
# ---------------------------------------------------------------------------


def evaluate_dialect(
    pair: dict[str, Any],
    index: int,
    out_dir: Path,
    backend: str = "hosted",
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    graph_model: str | None = None,
    source_set: str | None = None,
    generation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Baseline phrasing vs. dialect/register rewrites of the same clinical situation.

    Panel 1 is the baseline (standard phrasing, clinical accent); each variant
    panel carries its dialect label and, in the gap above it, a delta badge of
    the target-token probability vs. the baseline panel. Without an explicit
    target the baseline's top logit anchors the comparison."""
    baseline_prompt = pair.get("baseline_prompt") or pair.get("top_prompt")
    variants = pair.get("variants") or []
    if not baseline_prompt or not variants:
        raise ValueError("dialect mode needs 'baseline_prompt' and a non-empty 'variants' list")
    if any(not v.get("prompt") or not v.get("dialect") for v in variants):
        raise ValueError("every dialect variant needs 'dialect' and 'prompt' keys")
    anchor = pair.get("target_clinical_token")
    force_tokens = pair.get("force_target_tokens") or []
    targets = AttributionTargets.of(force_tokens) if force_tokens else None
    params = _generation_params(targets, generation_params, graph_model, source_set)

    baseline_graph = _trace(baseline_prompt, "baseline", index, out_dir, backend, params, targets, fetcher)
    variant_graphs = [
        _trace(v["prompt"], f"variant_{j:02d}", index, out_dir, backend, params, targets, fetcher)
        for j, v in enumerate(variants, start=1)
    ]

    reference = _resolve_reference(baseline_graph, anchor, targets)  # falls back to the top logit
    target_token = reference[0] if reference else None
    p_baseline = reference[1] if reference else None
    probs = [_probability_for(g, target_token) for g in variant_graphs]

    panels = build_panels(
        [baseline_graph] + variant_graphs,
        labels=[f"Baseline (standard phrasing): “{baseline_prompt}”"]
        + [f"{v['dialect']}: “{v['prompt']}”" for v in variants],
        accents=[CATEGORY_COLORS["clinical"]] + [CATEGORY_COLORS["off_target"]] * len(variants),
        value_label_flags=[True] + [False] * len(variants),
        headlines=[_headline(target_token, p) for p in [p_baseline] + probs],
        refs=[1] + [0] * len(variants),  # every variant panel diffs against the baseline
    )
    badges = [
        _delta_badge(f"Dialect Δ vs. baseline ({v['dialect']})", p_baseline, p)
        for v, p in zip(variants, probs)
    ]

    html_path = out_dir / f"index_{index:02d}.html"
    png_path = out_dir / f"index_{index:02d}.png"
    render_panels_html(panels, str(html_path), badges=badges)
    render_panels_png(panels, str(png_path), badges=badges, dpi=dpi)

    return {
        "index": index,
        "mode": "dialect",
        "baseline_prompt": baseline_prompt,
        "held_fixed": pair.get("held_fixed"),
        "term": pair.get("term"),
        "target_token": target_token,
        "baseline_probability": p_baseline,
        "variants": [
            {
                "dialect": v["dialect"],
                "prompt": v["prompt"],
                "probability": p,
                "delta_vs_baseline": (p - p_baseline) if p is not None and p_baseline is not None else None,
            }
            for v, p in zip(variants, probs)
        ],
        "forced_targets": list(force_tokens),
        "predictive_spread": {
            "baseline": logit_spread(baseline_graph),
            "variants": [logit_spread(g) for g in variant_graphs],
        },
        "error_share": {"baseline": error_node_share(baseline_graph)},
        "top_path": {"baseline": path_text(top_attribution_path(baseline_graph))},
        "outputs": {"html": str(html_path), "png": str(png_path)},
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def run_batch(
    pairs_path: str,
    out_dir: str = "medlang_batch_out",
    mode: str = "2panel",
    backend: str = "hosted",
    show_mitigation: bool = False,
    use_llm_translation: bool = True,
    llm_model: str | None = None,
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    graph_model: str | None = None,
    source_set: str | None = None,
    generation_params: dict[str, Any] | None = None,
    start_index: int = 1,
    steer_validate: int = 0,
    steer_boost: int = 0,
    steer_placebo: int = 0,
    screen_targets: float | None = None,
    generate_missing_explanations: int = 0,
) -> list[dict[str, Any]]:
    """Sequentially evaluate every pair in the JSON file under the chosen mode.

    ``batch_summary.json`` is checkpointed after every pair - hosted graph
    generation takes minutes per graph, so a crash, cancellation, or CI
    timeout must not lose the pairs already traced. ``start_index`` offsets
    the output numbering (index_NN.*, pair_NN_*.tagged.json) so chunked runs
    over slices of one batch keep a single global numbering. ``screen_targets``
    (2panel only) traces the clinical side first and skips the patient trace
    when the intended target misses the clinical spread at that probability -
    the screened-out pair stays in the summary with its observed spread.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}")
    if start_index < 1:
        raise ValueError(f"start_index must be >= 1; got {start_index}")
    if screen_targets is not None and mode != "2panel":
        raise ValueError("--screen-targets is a 2panel-mode feature")
    if (steer_validate or steer_boost or steer_placebo) and mode != "2panel":
        raise ValueError("--steer-validate/--steer-boost are 2panel-mode features")
    with open(pairs_path, encoding="utf-8") as f:
        pairs = json.load(f)
    if not isinstance(pairs, list):
        raise ValueError(f"{pairs_path} must contain a JSON array of pair objects")

    graph_model = resolve_graph_model(graph_model)
    if fetcher is None:
        try:
            fetcher = FeatureFetcher(model_id=graph_model, source_set=source_set,
                                     generate_missing=generate_missing_explanations)
        except ValueError as e:
            # No registered autointerp source set (non-gemma models): trace and
            # measure probabilities anyway; features render without clinical
            # accents until the model's source set is registered.
            logger.warning("Feature details unavailable for %s (%s) - tracing with "
                           "untagged features", graph_model, e)
            fetcher = NullFetcher()

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    summary_path = out / "batch_summary.json"
    summary = {
        "mode": mode,
        "backend": backend,
        "graph_model": graph_model,
        "source_set": source_set or getattr(fetcher, "source_set", None),
        "generation_params": generation_params or {},
        "start_index": start_index,
        "pairs_requested": len(pairs),
        "completed": False,
        "screen_targets": screen_targets,
        "results": results,
    }
    for i, pair in enumerate(pairs, start=start_index):
        if mode == "4quadrant":
            result = evaluate_quadrant(
                pair, i, out, backend=backend, dpi=dpi, fetcher=fetcher,
                graph_model=graph_model, source_set=source_set, generation_params=generation_params,
            )
        elif mode == "dialect":
            result = evaluate_dialect(
                pair, i, out, backend=backend, dpi=dpi, fetcher=fetcher,
                graph_model=graph_model, source_set=source_set, generation_params=generation_params,
            )
        elif mode == "translation":
            result = evaluate_translation(
                pair, i, out, backend=backend, use_llm_translation=use_llm_translation,
                llm_model=llm_model, dpi=dpi, fetcher=fetcher,
                graph_model=graph_model, source_set=source_set, generation_params=generation_params,
            )
        else:
            result = evaluate_pair(
                pair, i, out, backend=backend, show_mitigation=show_mitigation,
                use_llm_translation=use_llm_translation, llm_model=llm_model,
                dpi=dpi, fetcher=fetcher, steer_validate=steer_validate, steer_boost=steer_boost,
                steer_placebo=steer_placebo,
                graph_model=graph_model, source_set=source_set, generation_params=generation_params,
                screen_targets=screen_targets,
            )
        results.append(result)
        with open(summary_path, "w", encoding="utf-8") as f:  # checkpoint per pair
            json.dump(summary, f, indent=2)
        logger.info("Checkpointed pair %d (%d done) to %s", i, len(results), summary_path)
    # F-H06 (audit 1, 2026-07-17): a truncated checkpoint must be tellable from
    # a complete smaller chunk; the final rewrite is what flips the flag.
    summary["completed"] = True
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info("Batch complete: %d pairs (mode=%s), summary at %s", len(results), mode, summary_path)
    return results


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="medlang-batch-eval",
        description="Batch-evaluate prompt pairs (see module docstring for per-mode JSON formats).",
    )
    parser.add_argument("pairs_file", help="JSON file containing an array of pair objects")
    parser.add_argument("--mode", choices=MODES, default="2panel",
                        help="2panel: direct lexical swap; 4quadrant: syntax-vs-terminology matrix; "
                             "translation: organic LLM mitigation chain; "
                             "dialect: baseline vs. dialect/register variants around a fixed term")
    parser.add_argument("--out", default="medlang_batch_out", help="Output directory")
    parser.add_argument("--backend", choices=["hosted", "local"], default="hosted")
    parser.add_argument("--show-mitigation", action="store_true",
                        help="(2panel mode) append the legacy third translated panel")
    parser.add_argument("--no-llm-translation", action="store_true", help="Phrase-table translation only")
    parser.add_argument("--llm-model", default=None,
                        help="Anthropic model for translation (default: MEDLANG_ANTHROPIC_MODEL or claude-opus-4-8)")
    parser.add_argument("--dpi", type=int, default=DEFAULT_PNG_DPI, help="PNG export resolution")
    parser.add_argument("--start-index", type=int, default=1,
                        help="First output number (chunked runs over slices of one batch keep global numbering)")
    parser.add_argument("--screen-targets", type=float, default=None, metavar="MIN_PROB",
                        help="(2panel) Trace the clinical side first and screen out pairs whose "
                             "intended target misses the clinical spread at >= MIN_PROB; "
                             "screened-out pairs stay in the summary with their observed spread")
    parser.add_argument("--steer-validate", type=int, default=0, metavar="K",
                        help="EXPERIMENTAL (2panel): after measuring a pair, ablate the top K "
                             "off-target features of the patient graph via Neuronpedia steering "
                             "and record the default vs. steered continuations (causal check)")
    parser.add_argument("--steer-placebo", type=int, default=0, metavar="K",
                        help="EXPERIMENTAL (2panel): boost K seeded-random features on the patient "
                             "prompt at the same positive strength - the placebo arm for --steer-boost")
    parser.add_argument("--steer-boost", type=int, default=0, metavar="K",
                        help="EXPERIMENTAL (2panel): amplify the top K clinical features of the "
                             "CLINICAL graph while completing the PATIENT prompt (positive "
                             "strength) - does forcing the clinical circuit on recover the "
                             "target without changing the patient's words?")
    parser.add_argument("--generate-missing-explanations", type=int, default=0, metavar="CAP",
                        help="EXPERIMENTAL: ask Neuronpedia to auto-interp up to CAP unexplained "
                             "features per run (server-side, uses the provider keys saved in "
                             "your Neuronpedia ACCOUNT settings)")
    add_graph_cli_arguments(parser)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    results = run_batch(
        args.pairs_file,
        out_dir=args.out,
        mode=args.mode,
        backend=args.backend,
        show_mitigation=args.show_mitigation,
        use_llm_translation=not args.no_llm_translation,
        llm_model=args.llm_model,
        dpi=args.dpi,
        graph_model=args.graph_model,
        source_set=args.source_set,
        generation_params=generation_params_from_args(args),
        start_index=args.start_index,
        screen_targets=args.screen_targets,
        steer_validate=args.steer_validate,
        steer_boost=args.steer_boost,
        steer_placebo=args.steer_placebo,
        generate_missing_explanations=args.generate_missing_explanations,
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
