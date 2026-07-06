"""Batch evaluation harness with three isolated visualization modes.

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
from medlang_circuits.neuronpedia_features import FeatureFetcher
from medlang_circuits.targets import (
    TOP_K_SPREAD_DEFAULT,
    AttributionTargets,
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
    return f"prob({token}) = {prob:.2f}" if token is not None and prob is not None else None


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
) -> dict[str, Any]:
    """Direct lexical swap: clinical top panel vs. patient bottom panel."""
    anchor = pair.get("target_clinical_token")
    force_tokens = pair.get("force_target_tokens") or []
    targets = AttributionTargets.of(force_tokens) if force_tokens else None
    params = _generation_params(targets, generation_params, graph_model, source_set)

    prompts = [pair["top_prompt"], pair["bottom_prompt"]]
    roles = ["clinical", "patient"]
    translation_method = None
    if show_mitigation:
        translation = translate_to_clinical(pair["bottom_prompt"], use_llm=use_llm_translation, model=llm_model)
        prompts.append(translation["text"])
        roles.append("translated")
        translation_method = translation["method"]

    graphs = [
        _trace(prompt, role, index, out_dir, backend, params, targets, fetcher)
        for prompt, role in zip(prompts, roles)
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

    return {
        "index": index,
        "mode": "2panel",
        "prompts": dict(zip(roles, prompts)),
        "target_token": target_token,
        "probabilities": dict(zip(roles, probs)),
        "language_penalty": (probs[1] - probs[0]) if probs[0] is not None and probs[1] is not None else None,
        "mitigation_recovery": (
            (probs[2] - probs[1]) if len(probs) == 3 and probs[1] is not None and probs[2] is not None else None
        ),
        "translation_method": translation_method,
        "forced_targets": list(force_tokens),
        "predictive_spread": {role: logit_spread(g) for role, g in zip(roles, graphs)},
        "outputs": {"html": str(html_path), "png": str(png_path)},
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
        # lexicon axis drives accents: medical-lexicon boxes blue, patient-language boxes orange
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
        "outputs": {"html": str(html_path), "png": str(png_path)},
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
) -> list[dict[str, Any]]:
    """Sequentially evaluate every pair in the JSON file under the chosen mode.

    ``batch_summary.json`` is checkpointed after every pair - hosted graph
    generation takes minutes per graph, so a crash, cancellation, or CI
    timeout must not lose the pairs already traced. ``start_index`` offsets
    the output numbering (index_NN.*, pair_NN_*.tagged.json) so chunked runs
    over slices of one batch keep a single global numbering.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}")
    if start_index < 1:
        raise ValueError(f"start_index must be >= 1; got {start_index}")
    with open(pairs_path, encoding="utf-8") as f:
        pairs = json.load(f)
    if not isinstance(pairs, list):
        raise ValueError(f"{pairs_path} must contain a JSON array of pair objects")

    graph_model = resolve_graph_model(graph_model)
    if fetcher is None:
        # Fails fast for models whose default feature source set is unregistered.
        fetcher = FeatureFetcher(model_id=graph_model, source_set=source_set)

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
                dpi=dpi, fetcher=fetcher,
                graph_model=graph_model, source_set=source_set, generation_params=generation_params,
            )
        results.append(result)
        with open(summary_path, "w", encoding="utf-8") as f:  # checkpoint per pair
            json.dump(summary, f, indent=2)
        logger.info("Checkpointed pair %d (%d done) to %s", i, len(results), summary_path)
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
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
