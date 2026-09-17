"""Holdout-seal checks over everything the Petri lane may publish (design memo
sections 4 and 9). Reuses the study's single implementation of the seal
(scripts/seal_check.py over scripts/tierb_split.py); never re-derives the hash.

Two facts shape the result: a sealed set that computes empty (a checkout whose
dashboard has no tierb.start_utc) is a configuration state, reported as
`not_run`, never as `pass`; and a hit is reported by label only, never by
phrase, so the report cannot become the leak.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .framework import ROOT


def _seal_check_module():
    """scripts/seal_check.py loaded by path (the scripts directory is not a
    package the engine installs)."""
    name = "petri_audit_seal_check"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "seal_check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class SealResult:
    status: str                              # pass | fail | not_run
    detail: str | None
    sealed_phrases: int
    hits: dict[str, list[str]] = field(default_factory=dict)

    def as_check(self) -> dict:
        return {"status": self.status, "detail": self.detail}


def sealed_registry(simulated_dir: Path | str = ROOT / "data" / "simulated",
                    dashboard_path: Path | str = ROOT / "ops" / "dashboard.json") -> dict[str, str]:
    return _seal_check_module().sealed_registry(str(simulated_dir), str(dashboard_path))


def scan_paths(paths: list[Path], registry: dict[str, str]) -> SealResult:
    """Scan the given files (any suffix; the caller decides what is publishable)."""
    if not registry:
        return SealResult("not_run", "sealed set computed empty (no tierb.start_utc in the dashboard, or no Tier B "
                          "batches); nothing was checked", 0)
    mod = _seal_check_module()
    hits: dict[str, list[str]] = {}
    for p in paths:
        if not p.is_file():
            continue
        found = mod.scan_file(p, registry)
        if found:
            hits[str(p)] = sorted(found)
    if hits:
        return SealResult("fail", f"{sum(len(v) for v in hits.values())} sealed-phrase hit(s) in {len(hits)} file(s)",
                          len(registry), hits)
    return SealResult("pass", f"{len(registry)} sealed phrases, no hits in {len(paths)} file(s)", len(registry))


def scan_strings(strings: list[str], registry: dict[str, str], what: str = "in-memory export") -> SealResult:
    """Scan texts before they are written, so a verdict can enter the manifest
    whose identity digest the written files then carry."""
    if not registry:
        return SealResult("not_run", "sealed set computed empty (no tierb.start_utc in the dashboard, or no Tier B "
                          "batches); nothing was checked", 0)
    mod = _seal_check_module()
    labels: set[str] = set()
    for text in strings:
        lowered = mod.norm(text)
        for phrase, label in registry.items():
            if phrase in text or mod.norm(phrase) in lowered:
                labels.add(label)
    if labels:
        return SealResult("fail", f"{len(labels)} sealed phrase(s) in the {what}", len(registry), {what: sorted(labels)})
    return SealResult("pass", f"{len(registry)} sealed phrases, no hits in the {what}", len(registry))


def seed_texts_against_registry(texts: list[str], registry: dict[str, str]) -> list[str]:
    """Labels of sealed phrases that occur in the given seed texts (the pilot
    rule is explore-split only, so any hit refuses the seed before a run)."""
    if not registry:
        return []
    mod = _seal_check_module()
    labels: list[str] = []
    for text in texts:
        lowered = mod.norm(text)
        for phrase, label in registry.items():
            if phrase in text or mod.norm(phrase) in lowered:
                labels.append(label)
    return sorted(set(labels))
