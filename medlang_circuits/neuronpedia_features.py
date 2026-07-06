"""Fetch feature autointerp descriptions and top activating tokens from Neuronpedia.

Generated attribution graphs carry empty ``clerp`` labels - the webapp fetches
feature details at display time. The tagger needs those details at
post-processing time, so this module pulls them from the public Neuronpedia
feature API and caches each feature JSON on disk.

For gemma-2-2b with Gemma Scope transcoders the source is
``{layer}-gemmascope-transcoder-16k`` (e.g. layer 12, index 4321 ->
GET /api/feature/gemma-2-2b/12-gemmascope-transcoder-16k/4321).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.neuronpedia.org"
DEFAULT_SOURCE_SET = "gemmascope-transcoder-16k"
DEFAULT_CACHE_DIR = ".medlang_cache/features"
MAX_TOP_TOKENS = 12

# Per-model default autointerp source sets for feature-description fetching.
# None is a PLACEHOLDER: the model is traceable but its autointerp source name
# hasn't been confirmed yet - replace None with the right source name from
# neuronpedia.org; until then callers must pass --source-set explicitly.
MODEL_SOURCE_SETS: dict[str, str | None] = {
    "gemma-2-2b": DEFAULT_SOURCE_SET,
    "gemma-3-4b-it": None,  # PLACEHOLDER
    "qwen3-4b": None,  # PLACEHOLDER
    "qwen3-1.7b": None,  # PLACEHOLDER
}


def default_source_set(model_id: str) -> str:
    """Default autointerp source set for ``model_id``; raises until one is registered."""
    source_set = MODEL_SOURCE_SETS.get(model_id)
    if source_set is None:
        raise ValueError(
            f"No default feature source set is registered for model {model_id!r}; "
            "set --source-set explicitly (FeatureFetcher(source_set=...)) with the model's "
            "autointerp source name from neuronpedia.org"
        )
    return source_set


class FeatureDetails(dict):
    """Plain dict with keys: description (str), top_tokens (list[str])."""


class NullFetcher:
    """Detail fetcher for models with no registered autointerp source set.

    Tracing and probability measurement work; features keyword-match against
    their clerp only (usually nothing), so nodes fall to the default category
    and render without clinical accents until a source set is registered."""

    source_set = None

    def get(self, layer: int, index: int) -> FeatureDetails:
        return FeatureDetails(description="", top_tokens=[])


class FeatureFetcher:
    def __init__(
        self,
        model_id: str = "gemma-2-2b",
        source_set: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: str | os.PathLike | None = None,
        api_key: str | None = None,
        timeout: float = 20.0,
        generate_missing: int = 0,
    ):
        self.model_id = model_id
        self.source_set = source_set or default_source_set(model_id)
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.api_key = api_key or os.environ.get("NEURONPEDIA_API_KEY")
        self.timeout = timeout
        # EXPERIMENTAL auto-interp backfill: when a feature has no explanation
        # yet, ask Neuronpedia to generate one (their servers use the provider
        # keys saved in the ACCOUNT settings - no local keys involved), then
        # refetch. Capped per run; failures degrade to the empty description.
        self.generate_missing = max(0, int(generate_missing))
        self._generated = 0
        self.explain_endpoint = os.environ.get(
            "NEURONPEDIA_EXPLAIN_ENDPOINT", "/api/explanation/generate")
        self.explain_model = os.environ.get(
            "NEURONPEDIA_EXPLAIN_MODEL", "claude-haiku-4-5")
        self.explain_type = os.environ.get(
            "NEURONPEDIA_EXPLAIN_TYPE", "oai_token-act-pair")
        self._session = requests.Session()
        if self.api_key:
            self._session.headers["x-api-key"] = self.api_key

    def _maybe_generate_explanation(self, layer: int, index: int) -> bool:
        """Request server-side auto-interp for one unexplained feature; True on 2xx."""
        if self._generated >= self.generate_missing:
            return False
        self._generated += 1
        body = {
            "modelId": self.model_id,
            "layer": f"{layer}-{self.source_set}",
            "index": str(index),
            "explanationType": self.explain_type,
            "explanationModelName": self.explain_model,
        }
        try:
            resp = self._session.post(self.base_url + self.explain_endpoint,
                                      json=body, timeout=max(self.timeout, 60.0))
            if resp.ok:
                logger.info("Auto-interp generated for %s %s-%s/%s",
                            self.model_id, layer, self.source_set, index)
                return True
            logger.warning(
                "Auto-interp generation failed (%s) for %s-%s/%s: %s - if the schema "
                "differs, override NEURONPEDIA_EXPLAIN_ENDPOINT/_MODEL/_TYPE",
                resp.status_code, layer, self.source_set, index, resp.text[:200])
        except requests.RequestException as e:
            logger.warning("Auto-interp generation request failed: %s", e)
        return False

    def _cache_path(self, layer: int, index: int) -> Path:
        return self.cache_dir / self.model_id / f"{layer}-{self.source_set}" / f"{index}.json"

    def _fetch_raw(self, layer: int, index: int) -> dict:
        url = f"{self.base_url}/api/feature/{self.model_id}/{layer}-{self.source_set}/{index}"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get(self, layer: int, index: int) -> FeatureDetails:
        """Return {description, top_tokens} for a feature; empty values on any failure."""
        cache_path = self._cache_path(layer, index)
        if cache_path.is_file():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    return FeatureDetails(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass  # corrupt cache entry - refetch

        try:
            raw = self._fetch_raw(layer, index)
        except (requests.RequestException, ValueError) as e:
            logger.warning("Feature fetch failed for L%s/%s: %s", layer, index, e)
            return FeatureDetails(description="", top_tokens=[])

        details = FeatureDetails(
            description=_extract_description(raw),
            top_tokens=_extract_top_tokens(raw),
        )
        if not details["description"] and self.generate_missing:
            if self._maybe_generate_explanation(layer, index):
                try:
                    refetched = self._fetch_raw(layer, index)
                    details = FeatureDetails(
                        description=_extract_description(refetched),
                        top_tokens=_extract_top_tokens(refetched),
                    )
                except (requests.RequestException, ValueError) as e:
                    logger.warning("Refetch after auto-interp failed for L%s/%s: %s", layer, index, e)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(dict(details), f)
        except OSError as e:
            logger.debug("Could not write feature cache %s: %s", cache_path, e)
        return details


def _extract_description(raw: dict[str, Any]) -> str:
    explanations = raw.get("explanations") or []
    parts = [e.get("description", "").strip() for e in explanations if isinstance(e, dict)]
    return " | ".join(p for p in parts if p)


def _extract_top_tokens(raw: dict[str, Any]) -> list[str]:
    """Peak activating token from each of the top activation records, deduped."""
    tokens: list[str] = []
    seen: set[str] = set()
    for act in raw.get("activations") or []:
        if not isinstance(act, dict):
            continue
        toks = act.get("tokens") or []
        values = act.get("values") or []
        if not toks or len(toks) != len(values):
            continue
        peak = toks[max(range(len(values)), key=lambda i: values[i])]
        cleaned = re.sub(r"\s+", " ", str(peak)).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            tokens.append(cleaned)
        if len(tokens) >= MAX_TOP_TOKENS:
            break
    return tokens
