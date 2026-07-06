"""Task 3: end-to-end pipeline.

patient sentence -> translate to clinical wording -> trace both prompts ->
tag both graphs (Task 1) -> stacked visualization (Task 2) -> divergence summary.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from medlang_circuits.compare_viz import render_stacked_html, render_stacked_png
from medlang_circuits.feature_tagger import METADATA_KEY, SUMMARY_KEY, annotate_graph
from medlang_circuits.graph_client import generate_graph, resolve_graph_model, slugify
from medlang_circuits.neuronpedia_features import FeatureFetcher
from medlang_circuits.translate import translate_to_clinical

logger = logging.getLogger(__name__)


def run_comparison(
    patient_prompt: str,
    clinical_prompt: str | None = None,
    backend: str = "hosted",
    out_dir: str = "medlang_out",
    use_llm_translation: bool = True,
    use_llm_classifier: bool = False,
    llm_model: str | None = None,
    render_png: bool = True,
    graph_model: str | None = None,
    source_set: str | None = None,
    generation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full comparison and return a result dict with output paths + summary.

    Args:
        patient_prompt: the colloquial phrasing (e.g. next-token completion prompt).
        clinical_prompt: explicit clinical phrasing; auto-translated when None.
        backend: "hosted" (neuronpedia.org API) or "local" (apps/graph server).
        use_llm_classifier: enable the Anthropic fallback for unmatched features.
        graph_model: traced model (Neuronpedia ID; default MEDLANG_GRAPH_MODEL or gemma-2-2b).
        source_set: transcoder/autointerp source set; None -> the model's default.
        generation_params: bounded tracer parameters passed to generate_graph.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    graph_model = resolve_graph_model(graph_model)
    # Built up front so a missing source-set default fails before minutes of tracing.
    fetcher = FeatureFetcher(model_id=graph_model, source_set=source_set)

    translation_method = "provided"
    if clinical_prompt is None:
        translation = translate_to_clinical(patient_prompt, use_llm=use_llm_translation, model=llm_model)
        clinical_prompt, translation_method = translation["text"], translation["method"]
        logger.info("Translated patient prompt via %s: %r", translation_method, clinical_prompt)

    params = generation_params or {}
    clinical_graph = generate_graph(clinical_prompt, slug=slugify(clinical_prompt, "medlang-clin"),
                                    backend=backend, model_id=graph_model, source_set=source_set, **params)
    patient_graph = generate_graph(patient_prompt, slug=slugify(patient_prompt, "medlang-pat"),
                                   backend=backend, model_id=graph_model, source_set=source_set, **params)

    llm_classifier = None
    if use_llm_classifier:
        from medlang_circuits.llm_client import classify_feature_with_llm

        def llm_classifier(description, top_tokens):
            return classify_feature_with_llm(description, top_tokens, model=llm_model)

    for graph in (clinical_graph, patient_graph):
        annotate_graph(graph, fetcher=fetcher, llm_classifier=llm_classifier)

    paths = {
        "clinical_graph": out / "clinical_graph.tagged.json",
        "patient_graph": out / "patient_graph.tagged.json",
        "html": out / "index.html",  # standalone page, ready for GitHub Pages
        "summary": out / "summary.json",
    }
    for key, graph in (("clinical_graph", clinical_graph), ("patient_graph", patient_graph)):
        with open(paths[key], "w", encoding="utf-8") as f:
            json.dump(graph, f)

    render_stacked_html(clinical_graph, patient_graph, str(paths["html"]))
    if render_png:
        paths["png"] = out / "comparison.png"
        render_stacked_png(clinical_graph, patient_graph, str(paths["png"]))

    summary = build_divergence_summary(clinical_graph, patient_graph)
    summary["translation_method"] = translation_method
    summary["prompts"] = {"clinical": clinical_prompt, "patient": patient_prompt}
    summary["graph_generation"] = {
        "model": graph_model,
        "source_set": source_set or getattr(fetcher, "source_set", None),
        "backend": backend,
        "params": params,
    }
    with open(paths["summary"], "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Pipeline complete; outputs in %s", out)
    return {"paths": {k: str(v) for k, v in paths.items()}, "summary": summary}


def build_divergence_summary(clinical_graph: dict[str, Any], patient_graph: dict[str, Any]) -> dict[str, Any]:
    """Quantify how the two traces diverge - the hook for downstream metrics.

    Reports each graph's per-category node counts and attribution-mass shares,
    plus the overlap of clinical features (layer/index sets) between traces.
    """
    clinical_summary = clinical_graph["metadata"].get(SUMMARY_KEY, {})
    patient_summary = patient_graph["metadata"].get(SUMMARY_KEY, {})

    def clinical_feature_ids(graph: dict[str, Any]) -> set[int]:
        return {
            node["feature"]
            for node in graph.get("nodes", [])
            if (node.get(METADATA_KEY) or {}).get("category") == "clinical" and node.get("feature") is not None
        }

    clin_features = clinical_feature_ids(clinical_graph)
    pat_features = clinical_feature_ids(patient_graph)
    shared = clin_features & pat_features
    return {
        "clinical_prompt_graph": clinical_summary,
        "patient_prompt_graph": patient_summary,
        "clinical_feature_overlap": {
            "clinical_prompt_count": len(clin_features),
            "patient_prompt_count": len(pat_features),
            "shared_count": len(shared),
            "jaccard": len(shared) / len(clin_features | pat_features) if (clin_features | pat_features) else 0.0,
            "missing_in_patient_prompt": sorted(clin_features - pat_features)[:50],
        },
    }
