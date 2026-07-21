"""Structural validator for the frontend data contract: engine exports vs page read-sets.

The frontend renders whatever lands in ../patientwords/data/*.json; its inline JS
reads a fixed set of paths from each artifact (the read map). claim_check.py already
polices VALUES (hardcoded prose numbers vs data expressions); this script polices
STRUCTURE: required keys and types for every path a page dereferences, join-key
integrity across artifacts, render paths that must exist on disk, and cross-repo
copies that drift. Run it after any export and before committing site data:

  python scripts/validate_frontend_contract.py --site ../patientwords [--engine .] [--strict]

Checks are derived from the page JS as of the 2026-07-16 audit (Audit 1); when a
page starts reading a new field, add it here in the same change. ERRORS are
contract breaks a page cannot survive (wrong numbers, broken joins, dead iframe
paths); WARNINGS are drift that degrades silently (orphan rows, stale manual
copies, unknown top-level keys). --strict promotes warnings to errors.

Exit codes: 0 contract holds, 1 violations, 2 site payload missing/unreadable.
No medical vocabulary lives in this file; all terms stay in the data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The four circuit-traced models the exporter can emit, and the mirror fields it
# copies from the base model to each scenario's top level for older readers.
BASE_MODEL = "gemma-2-2b"
COMPAT = ["prob_clinical", "prob_patient", "language_penalty", "flipped",
          "top_clinical", "top_patient", "spread_clinical", "spread_patient",
          "target_token", "anchor_fallback", "screening", "circuit_diff",
          "clinical_mass"]

NUM = (int, float)


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, artifact: str, path: str, msg: str):
        self.errors.append(f"{artifact} :: {path} :: {msg}")

    def warn(self, artifact: str, path: str, msg: str):
        self.warnings.append(f"{artifact} :: {path} :: {msg}")


def _is(value, kinds) -> bool:
    """Type check that keeps bool out of the numeric kinds (True is an int)."""
    if kinds is bool:
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    return isinstance(value, kinds)


def need(rep: Report, artifact: str, obj: dict, key: str, kinds, path: str,
         nullable: bool = False):
    """Require obj[key] to exist with one of the given types; record an error."""
    if not isinstance(obj, dict) or key not in obj:
        rep.err(artifact, f"{path}.{key}", "missing required key")
        return None
    value = obj[key]
    if value is None:
        if not nullable:
            rep.err(artifact, f"{path}.{key}", "null where a value is required")
        return None
    if not _is(value, kinds):
        rep.err(artifact, f"{path}.{key}",
                f"wrong type {type(value).__name__}")
        return None
    return value


def load(site: Path, name: str, rep: Report, required: bool = False):
    path = site / "data" / name
    if not path.is_file():
        if required:
            rep.err(name, "-", "artifact missing (page throws; no pending state)")
        else:
            rep.warn(name, "-", "artifact missing (pages fall back to pending states)")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        rep.err(name, "-", f"unreadable: {err}")
        return None


def known_keys(rep: Report, artifact: str, obj: dict, allowed: set, path: str = "$"):
    """Unknown top-level keys are silent drift: an untracked publish step or a
    writer/consumer version skew. Warn (error under --strict)."""
    for key in obj:
        if key not in allowed:
            rep.warn(artifact, f"{path}.{key}",
                     "key not in the audited contract (untracked writer or stale copy)")


# ---------------------------------------------------------------- simulated_scenarios

def check_simulated(rep: Report, site: Path, payload: dict) -> dict:
    """Returns join indexes used by cross-artifact checks."""
    a = "simulated_scenarios.json"
    known_keys(rep, a, payload,
               {"batches", "scenarios", "models_meta", "traced", "traced_by_model",
                "holdout_withheld", "archive", "traces_site", "summary",
                "depth_model", "urgency_meta", "featured"})
    batches = need(rep, a, payload, "batches", list, "$") or []
    scenarios = need(rep, a, payload, "scenarios", list, "$") or []
    models_meta = need(rep, a, payload, "models_meta", list, "$") or []
    need(rep, a, payload, "traced", dict, "$")
    if "holdout_withheld" in payload and not _is(payload["holdout_withheld"], int):
        rep.err(a, "$.holdout_withheld", "must be an integer count")

    if not scenarios:
        rep.err(a, "$.scenarios", "empty (simulated-scenarios/index.html throws 'empty')")

    batch_stems = set()
    for i, b in enumerate(batches):
        p = f"$.batches[{i}]"
        stem = need(rep, a, b, "batch", str, p)
        if stem:
            batch_stems.add(stem)
        gen = need(rep, a, b, "generated", dict, p) or {}
        for key, kinds in (("model", str), ("run_timestamp", str), ("cost_usd", NUM),
                           ("accepted", int), ("rejected", int)):
            if key in gen and gen[key] is not None and not _is(gen[key], kinds):
                rep.err(a, f"{p}.generated.{key}", f"wrong type {type(gen[key]).__name__}")
        if "screen_targets" in b and b["screen_targets"] is not None \
                and not _is(b["screen_targets"], NUM):
            rep.err(a, f"{p}.screen_targets", "must be a number or null")

    meta_ids = []
    defaults = 0
    featured = set()
    for i, m in enumerate(models_meta):
        p = f"$.models_meta[{i}]"
        mid = need(rep, a, m, "id", str, p)
        if mid:
            meta_ids.append(mid)
        need(rep, a, m, "label", str, p)
        need(rep, a, m, "source_set", str, p, nullable=True)
        for key in ("features", "graphs", "available", "default"):
            if need(rep, a, m, key, bool, p) is None:
                continue
        if _is(m.get("n_traced"), int) is False:
            rep.err(a, f"{p}.n_traced", "must be an integer")
        if m.get("default"):
            defaults += 1
        if m.get("features"):
            featured.add(mid)
        # A model without a transcoder source set has no clinical-feature tagging;
        # features must be false or its clinical_mass numbers are an artifact.
        if m.get("features") and m.get("source_set") is None:
            rep.err(a, f"{p}", "features:true with source_set:null (untagged model)")
    if len(set(meta_ids)) != len(meta_ids):
        rep.err(a, "$.models_meta", "duplicate model ids")
    if models_meta and defaults != 1:
        rep.err(a, "$.models_meta", f"expected exactly one default model, found {defaults}")

    seen_pairs = set()
    traced_counts = dict.fromkeys(meta_ids, 0)
    scenario_keys = set()
    for i, s in enumerate(scenarios):
        p = f"$.scenarios[{i}]"
        idx = need(rep, a, s, "index", int, p)
        # scenario.html's ?sim= lookup and prev/next links assume 1..N contiguous.
        if idx is not None and idx != i + 1:
            rep.err(a, f"{p}.index", f"expected {i + 1} (contiguous 1..N), got {idx}")
        stem = need(rep, a, s, "batch", str, p)
        bidx = need(rep, a, s, "batch_index", int, p)
        if stem and stem not in batch_stems:
            rep.err(a, f"{p}.batch", f"stem {stem!r} not in $.batches")
        if stem and bidx is not None:
            if (stem, bidx) in seen_pairs:
                rep.err(a, f"{p}", f"duplicate (batch, batch_index) = ({stem}, {bidx})")
            seen_pairs.add((stem, bidx))
            scenario_keys.add((stem, bidx))
        for key in ("clinical_prompt", "patient_prompt", "intended_target"):
            need(rep, a, s, key, str, p)
        models = need(rep, a, s, "models", dict, p) or {}
        if not models:
            rep.err(a, f"{p}.models", "no per-model measurements")
        for mid, mobj in models.items():
            mp = f"{p}.models[{mid}]"
            if mid not in meta_ids:
                rep.err(a, mp, "model id absent from models_meta (selector cannot offer it)")
            else:
                traced_counts[mid] += 1
            if not isinstance(mobj, dict):
                rep.err(a, mp, "not an object")
                continue
            for key in COMPAT:
                if key not in mobj:
                    rep.err(a, f"{mp}.{key}", "missing model-object key")
            for key in ("prob_clinical", "prob_patient", "language_penalty"):
                if key in mobj and mobj[key] is not None and not _is(mobj[key], NUM):
                    rep.err(a, f"{mp}.{key}", "must be number or null")
            for key in ("flipped", "anchor_fallback"):
                if key in mobj and not _is(mobj[key], bool):
                    rep.err(a, f"{mp}.{key}", "must be boolean")
            for key in ("spread_clinical", "spread_patient"):
                if key in mobj and not _is(mobj[key], list):
                    rep.err(a, f"{mp}.{key}", "must be a list")
            # The FEATURED rule: no source set means clinical_mass is untagged noise;
            # the exporter must null it, or the meter renders an artifact as a finding.
            if mid in meta_ids and mid not in featured and mobj.get("clinical_mass") is not None:
                rep.err(a, f"{mp}.clinical_mass",
                        "non-null for a features:false model (NullFetcher artifact)")
        # COMPAT mirror: older readers and the index page's base fallback read the
        # top level; it must equal the base model's object exactly.
        if BASE_MODEL in models and isinstance(models[BASE_MODEL], dict):
            for key in COMPAT:
                if s.get(key) != models[BASE_MODEL].get(key):
                    rep.err(a, f"{p}.{key}",
                            f"top-level mirror disagrees with models[{BASE_MODEL}]")
        for key in ("html", "png"):
            if key in s:
                if not _is(s[key], str):
                    rep.err(a, f"{p}.{key}", "must be a path string")
                elif not (site / s[key]).is_file():
                    rep.err(a, f"{p}.{key}", f"render path missing on disk: {s[key]}")

    for mid, count in traced_counts.items():
        meta = next((m for m in models_meta if m.get("id") == mid), None)
        if meta and _is(meta.get("n_traced"), int) and meta["n_traced"] != count:
            rep.err(a, f"$.models_meta[{mid}].n_traced",
                    f"says {meta['n_traced']}, payload has {count} scenarios with this model")

    return {"scenario_keys": scenario_keys, "batch_stems": batch_stems,
            "meta_ids": set(meta_ids)}


# ---------------------------------------------------------------------- urgency_shift

def check_urgency(rep: Report, data: dict, joins: dict):
    a = "urgency_shift.json"
    known_keys(rep, a, data, {"rows", "summary", "tiers", "tier_examples",
                              "vocabulary_status"})
    vocab = need(rep, a, data, "vocabulary_status", str, "$")
    if vocab is not None and not vocab.strip():
        rep.err(a, "$.vocabulary_status", "empty (the draft label is load-bearing)")
    rows = need(rep, a, data, "rows", list, "$") or []
    summary = need(rep, a, data, "summary", dict, "$") or {}
    if "per_model_deduped" not in summary and "flip_classes" not in summary:
        rep.err(a, "$.summary", "needs per_model_deduped or the flip_classes fallback")

    seen = set()
    orphans = 0
    for i, r in enumerate(rows):
        p = f"$.rows[{i}]"
        stem = need(rep, a, r, "batch", str, p)
        idx = need(rep, a, r, "index", int, p)
        model = need(rep, a, r, "model", str, p)
        if "tier_shift" in r and r["tier_shift"] is not None and not _is(r["tier_shift"], NUM):
            rep.err(a, f"{p}.tier_shift", "must be number or null")
        if stem and idx is not None and model:
            key = (stem, idx, model)
            # Page JS builds urgMap[batch#index#model]; a duplicate key silently
            # last-write-wins, so one measurement shadows another.
            if key in seen:
                rep.err(a, p, f"duplicate join key {stem}#{idx}#{model}")
            seen.add(key)
            if joins and (stem, idx) not in joins["scenario_keys"]:
                orphans += 1
    if orphans:
        rep.warn(a, "$.rows",
                 f"{orphans}/{len(rows)} rows join no published scenario "
                 "(dead weight in the public payload)")


# ------------------------------------------------------------------- small artifacts

def check_shapes(rep: Report, site: Path, joins: dict):
    """Required keys and types for every remaining fetched artifact."""
    specs = {
        # artifact: (top-level required {key: kinds}, nullable keys)
        "model_stats.json": ({"models": list, "models_meta": list, "per_model": dict,
                              "population": str, "seed": int, "boot": int,
                              "benjamini_hochberg": dict, "dedupe": (str, dict)}, set()),
        "convergence.json": ({"generated_utc": str, "scope": str, "models": dict}, set()),
        "timeline.json": ({"generated_utc": str, "batches": list, "milestones": list,
                           "totals": dict, "provenance": (str, dict)}, set()),
        "dialects.json": ({"updated": str, "batch": str, "graph_model": str,
                           "source_set": str, "items": list}, set()),
        "model_evaluations.json": ({"updated": str, "task": str, "models": list}, set()),
        "jlens_depth.json": ({"model": str, "generated_utc": str, "class_labels": dict,
                              "blocks": list, "translation": dict}, set()),
        "retrace_consistency.json": ({"pairs_retraced": int, "prob_spread_max": NUM,
                                      "prob_spread_mean": NUM, "top_word_stable_pairs": int,
                                      "rows": list}, set()),
        "specialties.json": ({"status": str, "specialties": dict}, set()),
        "specialty_breakdown.json": ({"min_n": int, "specialties": dict}, set()),
        "model_provenance.json": ({"note": str, "models": dict}, set()),
        "translation_scale.json": ({"corpora": list, "per_model": dict,
                                    "lens_recovery": dict}, set()),
        "jlens_insights.json": ({"model": str, "n_pairs": int, "points": (list, dict),
                                 "taxonomy": (list, dict)}, set()),
    }
    for name, (required, nullable) in specs.items():
        data = load(site, name, rep)
        if data is None:
            continue
        if not isinstance(data, dict):
            rep.err(name, "$", f"expected object, got {type(data).__name__}")
            continue
        for key, kinds in required.items():
            need(rep, name, data, key, kinds, "$", nullable=key in nullable)

    pairs = load(site, "stress_pairs.json", rep)
    if pairs is not None:
        # two accepted shapes: the original bare list, or the wrapped object
        # {pairs, featured} written by export_stress_featured.py (M3 tail)
        if isinstance(pairs, dict):
            feat = pairs.get("featured")
            if feat is not None and not (isinstance(feat, dict)
                                         and isinstance(feat.get("rows"), list)):
                rep.err("stress_pairs.json", "$.featured",
                        "must be an object with a rows list when present")
            pairs = pairs.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            rep.err("stress_pairs.json", "$", "expected a non-empty list "
                    "(bare or under $.pairs)")
        else:
            for i, item in enumerate(pairs):
                for key in ("top_prompt", "bottom_prompt"):
                    need(rep, "stress_pairs.json", item, key, str, f"$[{i}]")
                need(rep, "stress_pairs.json", item, "provenance", (str, dict), f"$[{i}]")
                # absent on syntax-type pairs; pages render the pending state
                if "target_clinical_token" in item and item["target_clinical_token"] is not None \
                        and not _is(item["target_clinical_token"], str):
                    rep.err("stress_pairs.json", f"$[{i}].target_clinical_token",
                            "must be a string when present")

    prov = load(site, "provenance.json", rep)
    if isinstance(prov, dict):
        steer = prov.get("steering") or {}
        ke = steer.get("key_example") or {}
        if ke:
            stem, bidx = ke.get("batch"), ke.get("batch_index")
            # The key-example card silently vanishes when this join misses.
            if joins and (stem, bidx) not in joins["scenario_keys"]:
                rep.err("provenance.json", "$.steering.key_example",
                        f"({stem}, {bidx}) joins no published scenario (card disappears)")
        for i, b in enumerate(prov.get("batches") or []):
            if not isinstance(b, dict) or "batch" not in b:
                rep.err("provenance.json", f"$.batches[{i}]", "missing batch stem")
            elif not any(k in b for k in ("run_timestamp", "updated", "generated")):
                rep.warn("provenance.json", f"$.batches[{i}]",
                         "no timestamp under any known key (schema drift across entries)")


# ------------------------------------------------------------------ cross-repo checks

def check_engine_copies(rep: Report, site: Path, engine: Path):
    """Site files that are manual copies of engine files drift silently."""
    copies = [
        ("stress_pairs.json", engine / "data/measured/imported_pairs.json"),
        ("specialties.json", engine / "data/specialty_map.draft.json"),
    ]
    for name, src in copies:
        dst = site / "data" / name
        if not (src.is_file() and dst.is_file()):
            continue
        try:
            src_data = json.loads(src.read_text(encoding="utf-8"))
            dst_data = json.loads(dst.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            src_data, dst_data = src.read_bytes().strip(), dst.read_bytes().strip()
        # the site copy may be wrapped ({pairs, featured}); the engine source
        # stays a bare list — compare the pair content, not the envelope
        if isinstance(dst_data, dict) and "pairs" in dst_data:
            dst_data = dst_data["pairs"]
        if src_data != dst_data:
            rep.warn(name, "-", f"diverges from engine copy {src.name} "
                                "(manual copy went stale)")

    manifest = engine / "data/claims_manifest.json"
    if manifest.is_file():
        try:
            claims = json.loads(manifest.read_text(encoding="utf-8")).get("claims", [])
        except (OSError, json.JSONDecodeError) as err:
            rep.err("claims_manifest.json", "-", f"unreadable: {err}")
            return
        for i, c in enumerate(claims):
            if not (site / c.get("page", "")).is_file():
                rep.err("claims_manifest.json", f"$.claims[{i}].page",
                        f"page missing: {c.get('page')}")
            if not (site / c.get("source", "")).is_file():
                rep.err("claims_manifest.json", f"$.claims[{i}].source",
                        f"source missing: {c.get('source')}")


# --------------------------------------------------------------------------- driver

def validate(site: Path, engine: Path | None, strict: bool = False) -> Report:
    rep = Report()
    payload = load(site, "simulated_scenarios.json", rep, required=True)
    joins = {"scenario_keys": set(), "batch_stems": set(), "meta_ids": set()}
    if isinstance(payload, dict):
        joins = check_simulated(rep, site, payload)
    urg = load(site, "urgency_shift.json", rep)
    if isinstance(urg, dict):
        check_urgency(rep, urg, joins)
    check_shapes(rep, site, joins)
    if engine is not None and engine.is_dir():
        check_engine_copies(rep, site, engine)
    if strict:
        rep.errors.extend(rep.warnings)
        rep.warnings = []
    return rep


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords", help="frontend repo root")
    parser.add_argument("--engine", default=".", help="engine repo root ('' skips cross-repo checks)")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors (pre-deploy gate)")
    parser.add_argument("--quiet", action="store_true", help="print only the summary line")
    args = parser.parse_args()

    site = Path(args.site)
    if not (site / "data").is_dir():
        print(f"error: {site}/data is not a directory", file=sys.stderr)
        sys.exit(2)
    rep = validate(site, Path(args.engine) if args.engine else None, strict=args.strict)

    if not args.quiet:
        for w in rep.warnings:
            print("warn:", w)
        for e in rep.errors:
            print("FAIL:", e)
    print(f"contract check: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
