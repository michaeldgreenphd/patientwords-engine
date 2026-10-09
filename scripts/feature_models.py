"""Which traced (model, feature source set) pairs' clinical_mass may be published.

Two facts used to coincide and no longer do:

- a model HAS feature labels when ``neuronpedia_features.MODEL_SOURCE_SETS``
  registers a source set for it (or a run passes ``--source-set``), so its trace
  summaries carry a non-null ``source_set`` and a real (not NullFetcher ~0)
  ``clinical_mass``;
- a clinical_mass is PUBLISHABLE only when the labels it was tagged from have
  been checked to tag clinical features at a rate comparable with the study's
  reference, gemma-2-2b tagged from ``gemmascope-transcoder-16k``. Labels from
  another source set, explainer or explanation type can tag more or fewer
  features clinical for reasons that have nothing to do with the model, so a
  comparison needs that check first. Calibration is therefore a property of a
  (model, source set) PAIR: the same model tagged from another set (an explicit
  ``--source-set``) is not calibrated.

Until 2026-10-09 only gemma-2-2b had labels, and consumers gated on
``source_set`` being non-null. qwen3-4b's ``transcoder-hp`` set was registered
then, so its summaries now carry ``source_set: "transcoder-hp"``; every consumer
that publishes or aggregates clinical_mass gates on CALIBRATED_FEATURE_SOURCES
instead. Adding a pair is an owner decision taken after
``scripts/feature_label_calibration.py`` has compared its labels with the
reference's on the same pairs, and is logged in ``docs/prereg_divergence_log.md``.

No medical vocabulary lives in this file.
"""

from __future__ import annotations

CALIBRATED_FEATURE_SOURCES: frozenset[tuple[str, str]] = frozenset({("gemma-2-2b", "gemmascope-transcoder-16k")})

# Models with at least one calibrated source set (a model-level view, for listings).
CALIBRATED_FEATURE_MODELS: frozenset[str] = frozenset(model for model, _ in CALIBRATED_FEATURE_SOURCES)

# The model a summary without a graph_model field was traced on: summaries
# written before cross-model tracing (2026-07) name no model and are gemma-2-2b's.
LEGACY_GRAPH_MODEL = "gemma-2-2b"


def clinical_mass_publishable(graph_model: str | None, source_set: str | None) -> bool:
    """True when clinical_mass tagged from ``source_set`` on ``graph_model`` may be
    published or aggregated: the exact (model, source set) pair is calibrated.

    A null source_set (NullFetcher: the logits and activation-patching lanes, or
    an unlabelled model) is never publishable, nor is a calibrated model tagged
    from any other set."""
    return ((graph_model or LEGACY_GRAPH_MODEL), source_set) in CALIBRATED_FEATURE_SOURCES
