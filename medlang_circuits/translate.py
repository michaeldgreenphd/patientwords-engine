"""Task 3 hook: translate colloquial patient language into clinical terminology.

Primary path is the Anthropic Messages API (see llm_client.translate_with_llm).
When no API key / package is available, an offline phrase table keeps the
pipeline runnable end-to-end for demos. Like the keyword classifier, the phrase
table is data: it is loaded from the same keyword_config.json under an optional
"translations" key ({"colloquial phrase": "clinical phrase"}), so no vocabulary
lives in source.
"""

from __future__ import annotations

import json
import os
import logging
import re
from typing import Any

from medlang_circuits.keywords import _candidate_paths
from medlang_circuits.llm_client import DEFAULT_MODEL, translate_with_llm

logger = logging.getLogger(__name__)

TRANSLATIONS_KEY = "translations"


def _load_phrase_table() -> dict[str, str]:
    for candidate in _candidate_paths(None):
        if candidate.is_file():
            try:
                with open(candidate, encoding="utf-8") as f:
                    raw = json.load(f)
                table = raw.get(TRANSLATIONS_KEY, {})
                return {str(k): str(v) for k, v in table.items()}
            except (json.JSONDecodeError, OSError):
                return {}
    return {}


def translate_to_clinical(patient_text: str, use_llm: bool = True, model: str | None = None) -> dict[str, Any]:
    """Translate a patient sentence to clinical terminology.

    Returns {"text": <translated>, "method": "llm" | "phrase_table" | "unchanged",
    "model": <anthropic model id> | None (non-llm methods)}.
    """
    if use_llm:
        translated = translate_with_llm(patient_text, model=model)
        if translated:
            # the placebo arm reroutes the prompt inside translate_with_llm;
            # record it as a distinct method so the two arms can never be
            # pooled by accident downstream
            placebo = os.environ.get("MEDLANG_TRANSLATION_PLACEBO", "") in ("1", "true")
            method = "llm_placebo" if placebo else "llm"
            return {"text": translated, "method": method, "model": model or DEFAULT_MODEL}

    table = _load_phrase_table()
    text = patient_text
    applied = False
    for colloquial, clinical in sorted(table.items(), key=lambda kv: -len(kv[0])):
        pattern = re.compile(re.escape(colloquial), re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(clinical, text)
            applied = True
    if applied:
        return {"text": text, "method": "phrase_table", "model": None}

    logger.warning(
        "No translation available (no ANTHROPIC_API_KEY and no phrase-table match); using input unchanged"
    )
    return {"text": patient_text, "method": "unchanged", "model": None}
