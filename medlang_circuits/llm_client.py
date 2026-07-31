"""Optional Anthropic Messages API helpers (classifier fallback + translation).

Both functions degrade gracefully: if the ``anthropic`` package is missing or
no API key is configured, they return None and callers fall back to offline
behavior. Install with ``pip install medlang-circuits[llm]`` (or ``pip install
anthropic``) and set ANTHROPIC_API_KEY to enable.
"""

from __future__ import annotations

import logging
import os

from medlang_circuits.keywords import CATEGORIES

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("MEDLANG_ANTHROPIC_MODEL", "claude-opus-4-8")

_CLASSIFY_SYSTEM = (
    "You label neural-network feature descriptions for a mechanistic interpretability study. "
    "Given a feature's autointerp description and top activating tokens, respond with exactly one "
    "word - one of: clinical (healthcare/medical domain concepts), off_target (non-medical domain "
    "concepts such as other senses of the same words), structural (grammar, syntax, punctuation, "
    "formatting, positional features). Respond with only the label."
)

_TRANSLATE_SYSTEM = (
    "Translate this colloquial patient statement into standard clinical terminology. "
    "Preserve the sentence structure and length as closely as possible - change only the "
    "colloquial terms, keep everything else (including any trailing incomplete phrasing) intact. "
    "Respond with only the translated sentence."
)

# Placebo control for the mitigation arm: rewrite without introducing clinical
# vocabulary. If recovery tracks clinical terminology specifically, the placebo
# should show none; if it tracks any rewording, the placebo matches the real
# translation. Selected by MEDLANG_TRANSLATION_PLACEBO=1 (threaded from the
# circuit-trace workflow's translation_placebo param).
_PLACEBO_SYSTEM = (
    "Rewrite this statement in different everyday words with the same meaning. "
    "Do not introduce medical or clinical terminology - keep the same casual register. "
    "Preserve the sentence structure and length as closely as possible, keep everything "
    "else (including any trailing incomplete phrasing) intact. "
    "Respond with only the rewritten sentence."
)


def _translate_system():
    if os.environ.get("MEDLANG_TRANSLATION_PLACEBO", "") in ("1", "true"):
        return _PLACEBO_SYSTEM
    return _TRANSLATE_SYSTEM


def _get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        logger.info("anthropic package not installed; LLM features disabled")
        return None
    return anthropic.Anthropic()


def classify_feature_with_llm(description: str, top_tokens: list[str] | None = None, model: str | None = None) -> str | None:
    """Classify a feature description into one of the three categories, or None if unavailable."""
    client = _get_client()
    if client is None or not description.strip():
        return None
    prompt = f"Description: {description}"
    if top_tokens:
        prompt += f"\nTop activating tokens: {', '.join(top_tokens)}"
    try:
        response = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=16,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:  # network/auth errors should not abort tagging
        logger.warning("LLM classification failed: %s", e)
        return None
    text = next((b.text for b in response.content if b.type == "text"), "").strip().lower()
    return text if text in CATEGORIES else None


# Translation-call usage accumulator. The mitigation translation is the only
# paid call inside a trace run, and until 2026-07-31 its cost was invisible:
# no sidecar was ever written, so ledger_update booked $0 for every
# --show-mitigation run. Callers snapshot this after a batch to emit a real
# cost sidecar. Module-level (not a return-value change) so the existing
# callers of translate_with_llm keep their signature.
_TRANSLATE_USAGE: dict[str, object] = {
    "calls": 0, "input_tokens": 0, "output_tokens": 0, "models": {}}


def translate_usage_snapshot() -> dict:
    """Copy of the accumulated translation usage since the last reset."""
    snap = dict(_TRANSLATE_USAGE)
    snap["models"] = dict(_TRANSLATE_USAGE["models"])
    return snap


def reset_translate_usage() -> None:
    """Zero the accumulator (call before a batch)."""
    _TRANSLATE_USAGE.update(calls=0, input_tokens=0, output_tokens=0, models={})


def _record_translate_usage(model: str, usage) -> None:
    """Fold one response's usage in; tolerates SDKs that omit the field."""
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    _TRANSLATE_USAGE["calls"] = int(_TRANSLATE_USAGE["calls"]) + 1
    _TRANSLATE_USAGE["input_tokens"] = int(_TRANSLATE_USAGE["input_tokens"]) + inp
    _TRANSLATE_USAGE["output_tokens"] = int(_TRANSLATE_USAGE["output_tokens"]) + out
    per = _TRANSLATE_USAGE["models"].setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    per["calls"] += 1
    per["input_tokens"] += inp
    per["output_tokens"] += out


def translate_with_llm(patient_text: str, model: str | None = None) -> str | None:
    """Translate colloquial patient language to clinical terminology, or None if unavailable."""
    client = _get_client()
    if client is None:
        return None
    resolved = model or DEFAULT_MODEL
    try:
        response = client.messages.create(
            model=resolved,
            max_tokens=256,
            system=_translate_system(),
            messages=[{"role": "user", "content": patient_text}],
        )
    except Exception as e:
        logger.warning("LLM translation failed: %s", e)
        return None
    _record_translate_usage(resolved, getattr(response, "usage", None))
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    return text or None
