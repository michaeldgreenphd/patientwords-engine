"""Batch evaluation harness: quantify mechanistic degradation across prompt pairs.

Input is a JSON file containing an array of paired prompts:

    [
      {
        "top_prompt": "Clinical framing statement...",
        "bottom_prompt": "Patient framing statement...",
        "target_clinical_token": " therapist",          // optional word anchor for the delta metric
        "force_target_tokens": [" therapist", " hospital"]  // optional AttributionTargets
      }
    ]

For each pair the harness traces both prompts, tags the graphs, applies
target-token forcing (see medlang_circuits.targets - bypasses grammatical
articles by attributing from named substantive tokens), computes the
"Language Penalty" delta metric (p_clinical - p_patient for the target
medical token), and writes numbered outputs: index_01.html / index_01.png,
index_02.html / ... plus per-pair tagged graph JSONs and a batch_summary.json.

With ``--show-mitigation`` the harness adds an LLM translation step (Anthropic
Messages API via medlang_circuits.llm_client, offline phrase-table fallback)
that rewrites the patient prompt into standard terminology and renders a
3-panel view: clinical / patient (degraded circuit + probability drop) /
translated patient (restored circuit + recovered probability), with a
"Mitigation Recovery" badge in the second gap.

Usage:
    medlang-batch-eval pairs.json --out batch_out --show-mitigation
    python -m medlang_circuits.batch_eval pairs.json --backend local
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from medlang_circuits.compare_viz import (
    NEGATIVE_EDGE_COLOR,
    build_panels,
    render_panels_html,
    render_panels_png,
)
from medlang_circuits.feature_tagger import annotate_graph
from medlang_circuits.graph_client import generate_graph, slugify
from medlang_circuits.targets import AttributionTargets, retarget_graph, target_probability
from medlang_circuits.translate import translate_to_clinical

logger = logging.getLogger(__name__)

RECOVERY_COLOR = "#2f7d52"  # muted green for positive deltas
DEFAULT_PNG_DPI = 220  # high-resolution static export

PANEL_ROLES = ("clinical", "patient", "translated")


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


def evaluate_pair(
    pair: dict[str, Any],
    index: int,
    out_dir: Path,
    backend: str = "hosted",
    show_mitigation: bool = False,
    use_llm_translation: bool = True,
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    generation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trace, tag, retarget, measure, and render one prompt pair (or triple)."""
    top_prompt = pair["top_prompt"]
    bottom_prompt = pair["bottom_prompt"]
    anchor = pair.get("target_clinical_token")
    force_tokens = pair.get("force_target_tokens") or []
    targets = AttributionTargets.of(force_tokens) if force_tokens else None

    params = dict(generation_params or {})
    if targets:
        # Widen the salient-logit set and pass tokens through for forks with native forcing.
        for key, value in targets.to_generation_params().items():
            params.setdefault(key, value)

    prompts = [top_prompt, bottom_prompt]
    translation_method = None
    if show_mitigation:
        translation = translate_to_clinical(bottom_prompt, use_llm=use_llm_translation)
        prompts.append(translation["text"])
        translation_method = translation["method"]
        logger.info("Pair %02d mitigation translation via %s: %r", index, translation_method, translation["text"])

    graphs: list[dict[str, Any]] = []
    for prompt, role in zip(prompts, PANEL_ROLES):
        graph = generate_graph(prompt, slug=slugify(prompt, f"medlang-{role}"), backend=backend, **params)
        if targets:
            retarget_graph(graph, targets)  # before tagging, so summary stats reflect the retargeted graph
        annotate_graph(graph, fetcher=fetcher)
        graphs.append(graph)
        graph_path = out_dir / f"pair_{index:02d}_{role}.tagged.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)

    # Delta metric: resolve the target medical token on the clinical graph (anchor ->
    # forced targets -> top logit), then read the SAME token's probability elsewhere.
    reference = target_probability(graphs[0], anchor=anchor) if anchor else None
    if reference is None and targets:
        reference = target_probability(graphs[0], targets=targets)
    if reference is None:
        reference = target_probability(graphs[0])
    if reference is None:
        logger.warning("Pair %02d: no traced logit with a probability on the clinical graph", index)
        target_token, probs = None, [None] * len(graphs)
    else:
        target_token = reference[0]
        probs = [reference[1]] + [
            (result[1] if (result := target_probability(g, anchor=target_token)) else None)
            for g in graphs[1:]
        ]
        for role, p in zip(PANEL_ROLES, probs):
            if p is None:
                logger.warning(
                    "Pair %02d: target token %r absent from the %s graph's traced logits "
                    "(consider force_target_tokens / higher max_n_logits)",
                    index, target_token, role,
                )

    badges: list[Any] = [_delta_badge("Language Penalty", probs[0], probs[1])]
    if len(graphs) == 3:
        badges.append(_delta_badge("Mitigation Recovery", probs[1], probs[2]))

    panels = build_panels(graphs)
    html_path = out_dir / f"index_{index:02d}.html"
    png_path = out_dir / f"index_{index:02d}.png"
    render_panels_html(panels, str(html_path), badges=badges)
    render_panels_png(panels, str(png_path), badges=badges, dpi=dpi)

    result = {
        "index": index,
        "prompts": dict(zip(PANEL_ROLES, prompts)),
        "target_token": target_token,
        "probabilities": dict(zip(PANEL_ROLES, probs)),
        "language_penalty": (probs[1] - probs[0]) if probs[0] is not None and probs[1] is not None else None,
        "mitigation_recovery": (
            (probs[2] - probs[1]) if len(probs) == 3 and probs[1] is not None and probs[2] is not None else None
        ),
        "translation_method": translation_method,
        "forced_targets": list(force_tokens),
        "outputs": {"html": str(html_path), "png": str(png_path)},
    }
    logger.info(
        "Pair %02d done: target=%r penalty=%s recovery=%s",
        index, target_token, result["language_penalty"], result["mitigation_recovery"],
    )
    return result


def run_batch(
    pairs_path: str,
    out_dir: str = "medlang_batch_out",
    backend: str = "hosted",
    show_mitigation: bool = False,
    use_llm_translation: bool = True,
    dpi: int = DEFAULT_PNG_DPI,
    fetcher: Any = None,
    generation_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Sequentially evaluate every pair in the JSON file; returns the summary list."""
    with open(pairs_path, encoding="utf-8") as f:
        pairs = json.load(f)
    if not isinstance(pairs, list):
        raise ValueError(f"{pairs_path} must contain a JSON array of pair objects")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for i, pair in enumerate(pairs, start=1):
        results.append(
            evaluate_pair(
                pair, i, out,
                backend=backend,
                show_mitigation=show_mitigation,
                use_llm_translation=use_llm_translation,
                dpi=dpi,
                fetcher=fetcher,
                generation_params=generation_params,
            )
        )
    summary_path = out / "batch_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Batch complete: %d pairs, summary at %s", len(results), summary_path)
    return results


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="medlang-batch-eval",
        description="Batch-evaluate clinical vs. patient prompt pairs (see module docstring for the JSON format).",
    )
    parser.add_argument("pairs_file", help="JSON file containing an array of pair objects")
    parser.add_argument("--out", default="medlang_batch_out", help="Output directory")
    parser.add_argument("--backend", choices=["hosted", "local"], default="hosted")
    parser.add_argument(
        "--show-mitigation", action="store_true",
        help="Add the LLM translation step and render 3-panel clinical/patient/translated views",
    )
    parser.add_argument("--no-llm-translation", action="store_true", help="Phrase-table translation only")
    parser.add_argument("--dpi", type=int, default=DEFAULT_PNG_DPI, help="PNG export resolution")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    results = run_batch(
        args.pairs_file,
        out_dir=args.out,
        backend=args.backend,
        show_mitigation=args.show_mitigation,
        use_llm_translation=not args.no_llm_translation,
        dpi=args.dpi,
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
