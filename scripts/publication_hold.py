"""Models whose measurements stay out of every published aggregate until the owner releases them.

The three post-registration exploratory logits models added on 2026-10-09 (docs/model_matrix.md,
docs/prereg_divergence_log.md) are being backfilled at $0 by the logits-eval lane, so their summaries land
under ``trace_out/<pairs-stem>__<model>/`` while the backfill is partial. Every collector that globs
``trace_out/*/batch_summary*`` would otherwise pool them into the site's urgency aggregates and headline
(``urgency_shift.py``), the model statistics built from those rows (``paired_stats_rigor.py``), the scenario
payload's ``urgency_meta`` (``embed_scenario_joins.py``) and the timeline's part count (``study_timeline.py``).
The owner decided on 2026-10-09 that whether these rows are published is their call, so each such consumer
skips the models named here and says how many parts it skipped.

Releasing a model is removing it from HELD_MODELS, in a reviewed pull request; the next publish then pools it.
"""
from __future__ import annotations

HELD_MODELS: frozenset[str] = frozenset({"gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it"})


def is_held(model: str | None) -> bool:
    """True when a model's measurements must stay out of published aggregates."""
    return model in HELD_MODELS


def run_dir_model(run_dir: str) -> str | None:
    """The suffix after ``__`` in a ``<stem>__<suffix>`` run directory (a model id, or an instrument suffix such as
    ``jlens_gemma-2-2b`` or ``patch``), or None for a bare ``<stem>`` (gemma-2-2b's hosted traces)."""
    _, sep, suffix = run_dir.partition("__")
    return suffix if sep else None


def is_held_run_dir(run_dir: str) -> bool:
    """True for a ``trace_out/<stem>__<model>`` directory of a held model."""
    return is_held(run_dir_model(run_dir))
