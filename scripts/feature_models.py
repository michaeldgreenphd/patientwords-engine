"""Which traced models' feature-tag numbers (clinical_mass) may be published.

Two facts used to coincide and no longer do:

- a model HAS feature labels when ``neuronpedia_features.MODEL_SOURCE_SETS``
  registers a source set for it, so its trace summaries carry a non-null
  ``source_set`` and a real (not NullFetcher ~0) ``clinical_mass``;
- a model's clinical_mass is PUBLISHABLE only when its labels have been checked
  to tag clinical features at a rate comparable with the study's reference
  model, gemma-2-2b. Labels from another explainer or explanation type can tag
  more or fewer features clinical for reasons that have nothing to do with the
  model, so a cross-model clinical_mass comparison needs that check first.

Until 2026-10-09 only gemma-2-2b had labels, and consumers gated on
``source_set`` being non-null. qwen3-4b's ``transcoder-hp`` set was registered
then, so its summaries now carry ``source_set: "transcoder-hp"``; every consumer
that publishes or aggregates clinical_mass gates on this set instead. Adding a
model here is an owner decision taken after ``scripts/feature_label_calibration.py``
has compared its labels with gemma-2-2b's on the same pairs, and is logged in
``docs/prereg_divergence_log.md``.

No medical vocabulary lives in this file.
"""

from __future__ import annotations

CALIBRATED_FEATURE_MODELS: frozenset[str] = frozenset({"gemma-2-2b"})

# The model a summary without a graph_model field was traced on: summaries
# written before cross-model tracing (2026-07) name no model and are gemma-2-2b's.
LEGACY_GRAPH_MODEL = "gemma-2-2b"


def clinical_mass_publishable(graph_model: str | None, source_set: str | None) -> bool:
    """True when a summary's clinical_mass may be published or aggregated.

    Both conditions hold: the model is in CALIBRATED_FEATURE_MODELS, and the
    summary was tagged from a source set (a null source_set means NullFetcher,
    whose ~0 clinical_mass is an artifact even for a calibrated model, as in the
    logits and activation-patching lanes)."""
    return bool(source_set) and (graph_model or LEGACY_GRAPH_MODEL) in CALIBRATED_FEATURE_MODELS
