"""Compatibility import path for the results policy (scripts/results_policy.py).

Until 2026-11-10 this module was the publication hold: three rules (HELD_MODELS, the logits release manifest,
EXPLORATORY_STEM_PREFIXES) that kept parts out of everything the publish chain wrote. The owner replaced the
blanket hold with the open-results policy (docs/open_results_policy.md): sharing, analysis membership, artifact
integrity and data restrictions are now decided separately in scripts/results_policy.py from the declared
metadata in data/results_policy/policy.v1.json.

What stays here is the import path. Collectors that do ``from publication_hold import Gate, ReleaseError``
get the policy's gate under its default membership (``study-interim/1``), which reproduces the rule they applied
from 2026-10-09, so the published statistics keep their inputs. Nothing a default gate skips is hidden: the
results catalogue (scripts/export_results_catalogue.py) lists it and says which membership it is outside of.

The names below describe membership now, not publication:

* ``HELD_MODELS``   - models whose cohort the default membership excludes (the 2026-10-09 additions).
* ``is_exploratory_run_dir`` - run directories whose stimulus class the default membership excludes.
* ``RELEASE_MANIFEST`` - the logits manifest the default membership pins as its input record.

New code imports scripts/results_policy.py directly.
"""
from __future__ import annotations

try:
    from scripts.results_policy import (MANIFEST_SCHEMA, RELEASE_MANIFEST, Gate, ReleaseError,
                                        is_exploratory_run_dir, load_manifest, load_policy, run_dir_model,
                                        sha256_file)
except ImportError:  # run as a script from scripts/
    from results_policy import (MANIFEST_SCHEMA, RELEASE_MANIFEST, Gate, ReleaseError,  # noqa: F401
                                is_exploratory_run_dir, load_manifest, load_policy, run_dir_model, sha256_file)

__all__ = ["EXPLORATORY_STEM_PREFIXES", "Gate", "HELD_MODELS", "MANIFEST_SCHEMA", "RELEASE_MANIFEST",
           "ReleaseError", "is_exploratory_run_dir", "is_held", "is_held_run_dir", "load_manifest",
           "run_dir_model", "sha256_file"]

_POLICY = load_policy()
_DEFAULT = _POLICY.membership(_POLICY.default_membership)

# Models outside the default membership. Derived from the policy file; edit that, not this.
HELD_MODELS: frozenset[str] = _POLICY.excluded_models(_POLICY.default_membership)
# Stem prefixes of the stimulus classes the default membership excludes (today ``agscen_``).
EXPLORATORY_STEM_PREFIXES: tuple[str, ...] = tuple(
    _POLICY.doc["stimulus_classes"][name]["match"]["stem_prefix"]
    for name in _DEFAULT["exclude_stimulus_classes"]
    if "stem_prefix" in _POLICY.doc["stimulus_classes"][name].get("match", {}))


def is_held(model: str | None) -> bool:
    """True when the default membership excludes the model's cohort."""
    return model in HELD_MODELS


def is_held_run_dir(run_dir: str) -> bool:
    """True for a ``trace_out/<stem>__<model>`` directory of a model outside the default membership."""
    return is_held(run_dir_model(run_dir))
