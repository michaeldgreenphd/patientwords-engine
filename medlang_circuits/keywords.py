"""Keyword-config loading for feature classification.

The classifier is data-driven: term lists live in an external JSON file
(``keyword_config.json``), NOT in this source file. The code only knows the
three abstract category buckets; you populate the vocabulary locally.

Config file schema (all keys optional, values are lists of strings; multi-word
phrases are allowed and matched case-insensitively on word boundaries):

    {
      "clinical":   ["TERM_A", "TERM_B", "MULTI WORD PHRASE"],
      "off_target": ["TERM_C"],
      "structural": ["TERM_D"]
    }

Resolution order for the config path:
    1. explicit ``path`` argument
    2. ``MEDLANG_KEYWORD_CONFIG`` environment variable
    3. ``keyword_config.json`` in the current working directory
    4. ``keyword_config.json`` next to this package
    5. the packaged default (``medlang_circuits/data/keyword_config_default.json``)
       - a general medical/structural vocabulary so CI trace runs tag
       features without a local config; any local config fully overrides it

If nothing is found (packaged default removed), placeholder terms are
returned (which match nothing in practice) and classification falls through
to the LLM fallback / default category. See ``keyword_config.example.json``
for a template.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CATEGORY_CLINICAL = "clinical"
CATEGORY_OFF_TARGET = "off_target"
CATEGORY_STRUCTURAL = "structural"
CATEGORIES = (CATEGORY_CLINICAL, CATEGORY_OFF_TARGET, CATEGORY_STRUCTURAL)

ENV_VAR = "MEDLANG_KEYWORD_CONFIG"
CONFIG_FILENAME = "keyword_config.json"

# Abstract placeholders only - populate the real vocabulary in keyword_config.json.
PLACEHOLDER_CONFIG: dict[str, list[str]] = {
    CATEGORY_CLINICAL: ["TERM_A", "TERM_B"],
    CATEGORY_OFF_TARGET: ["TERM_C", "TERM_D"],
    CATEGORY_STRUCTURAL: ["TERM_E", "TERM_F"],
}


def _candidate_paths(path: str | os.PathLike | None) -> list[Path]:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    env_path = os.environ.get(ENV_VAR)
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / CONFIG_FILENAME)
    candidates.append(Path(__file__).resolve().parent.parent / CONFIG_FILENAME)
    # Packaged default vocabulary: keeps CI trace runs tagging features
    # (clinical = green ink) when no local config exists; any local config
    # above fully overrides it.
    candidates.append(Path(__file__).resolve().parent / "data" / "keyword_config_default.json")
    return candidates


def load_keyword_config(path: str | os.PathLike | None = None) -> dict[str, list[str]]:
    """Load {category: [terms]} from the first config file found.

    Unknown keys in the file are ignored; missing categories default to empty.
    Returns PLACEHOLDER_CONFIG when no file exists.
    """
    for candidate in _candidate_paths(path):
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                raw = json.load(f)
            config = {cat: [str(t) for t in raw.get(cat, [])] for cat in CATEGORIES}
            logger.info("Loaded keyword config from %s (%s)", candidate, {k: len(v) for k, v in config.items()})
            return config
    logger.warning(
        "No %s found (env %s unset). Using abstract placeholders - keyword matching will be a no-op "
        "and classification will rely on the LLM fallback / default category.",
        CONFIG_FILENAME,
        ENV_VAR,
    )
    return {cat: list(terms) for cat, terms in PLACEHOLDER_CONFIG.items()}
