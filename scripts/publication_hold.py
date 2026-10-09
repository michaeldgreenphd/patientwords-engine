"""What the publish chain may read from trace_out/: the publication hold and the logits release manifest.

Two rules, both enforced by every collector that would pool trace_out/ summaries into a published number
(urgency_shift.py, whose rows also feed paired_stats_rigor.py, tier_sensitivity.py and embed_scenario_joins.py;
study_timeline.py; screen_sensitivity.py; export_frontend_simulated.py; export_archive.py; and the
audit_target_reads.py mirror of urgency_shift's ingestion):

1. HELD_MODELS. The three post-registration exploratory logits models added on 2026-10-09
   (docs/model_matrix.md, docs/prereg_divergence_log.md) are skipped entirely, whatever has landed. Releasing
   one is removing it from HELD_MODELS in a reviewed pull request and then running the release command below.

2. The logits release manifest (data/publication_release/logits_parts.json; owner decision 2026-10-09,
   "republish only when you say so"). A CPU-logits part (``"backend": "logits"``) is read only when its path is
   listed in the manifest with the sha256 of its exact bytes. A part landed by the 2026-10 backfill campaign,
   or a listed part whose bytes changed since, is held until the owner releases it, so nothing the campaign
   lands moves a published number even when the Routine's publish chain runs for another reason. Hosted-trace
   parts (gemma-2-2b's graphs, the drift sentinel) are not logits parts and are never held by this rule.

   Releasing is an owner action, never the Routine's or the backfill chain's:
       python scripts/publication_release.py --release
   rewrites the manifest from the logits parts committed at HEAD (scripts/publication_release.py).

A missing or unreadable manifest is refused (ReleaseError) the first time a logits part needs it: publishing
without it would either drop every logits row or pool unreleased ones, and both are silent changes.
Every skip is counted and printed by the collector, never silent.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

HELD_MODELS: frozenset[str] = frozenset({"gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it"})
RELEASE_MANIFEST = Path("data") / "publication_release" / "logits_parts.json"
MANIFEST_SCHEMA = "logits_release/1"


class ReleaseError(RuntimeError):
    """The release manifest is missing or malformed, so no logits part can be admitted or held soundly."""


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(root: Path) -> dict[str, str]:
    """{repo-relative part path: sha256} from root/data/publication_release/logits_parts.json."""
    path = Path(root) / RELEASE_MANIFEST
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReleaseError(f"{path} is missing: logits parts cannot be published without the owner's release "
                           "manifest (python scripts/publication_release.py --release writes it)") from None
    except (OSError, ValueError) as exc:
        raise ReleaseError(f"{path} is unreadable: {exc}") from None
    parts = doc.get("parts") if isinstance(doc, dict) else None
    if doc.get("schema") != MANIFEST_SCHEMA or not isinstance(parts, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) == 64 for k, v in parts.items()):
        raise ReleaseError(f"{path} is not a {MANIFEST_SCHEMA} manifest with a {{path: sha256}} 'parts' map")
    return parts


class Gate:
    """Admits or holds trace_out summary parts for one collector run, and counts every hold by reason."""

    def __init__(self, root: Path | str = ".", manifest_optional: bool = False) -> None:
        """`manifest_optional` is for readers that publish nothing (audit_target_reads.py's mirror of the
        collector): with no manifest at `root` they admit logits parts as before the gate existed, instead of
        refusing. Every publishing collector leaves it False."""
        self.root = Path(root).resolve()
        self.manifest_optional = manifest_optional
        self._manifest: dict[str, str] | None = None
        self.held: Counter[str] = Counter()

    def _rel(self, part: Path) -> str:
        path = Path(part)
        path = path if path.is_absolute() else Path.cwd() / path
        return path.resolve().relative_to(self.root).as_posix()

    def admit(self, part: Path | str, summary: dict, model: str | None = None) -> bool:
        """True when the part may be read for publication. `model` is the collector's own reading of the part's
        model (graph_model or directory suffix); the directory suffix is checked too."""
        part = Path(part)
        if is_held(model) or is_held(summary.get("graph_model")) or is_held_run_dir(part.parent.name):
            self.held[f"held model {model or summary.get('graph_model') or run_dir_model(part.parent.name)}"] += 1
            return False
        if summary.get("backend") != "logits":
            return True
        if self._manifest is None:
            if self.manifest_optional and not (self.root / RELEASE_MANIFEST).exists():
                return True
            self._manifest = load_manifest(self.root)
        rel = self._rel(part)
        want = self._manifest.get(rel)
        if want is None:
            self.held["unreleased logits part"] += 1
            return False
        if want != sha256_file(part):
            self.held["logits part changed since its release"] += 1
            return False
        return True

    def report(self) -> str:
        """One line for stdout, or "" when nothing was held."""
        if not self.held:
            return ""
        return ("publication hold (scripts/publication_hold.py), parts not read: "
                + ", ".join(f"{reason} {n}" for reason, n in sorted(self.held.items())))
