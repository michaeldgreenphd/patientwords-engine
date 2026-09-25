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
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple

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
        self.notes: list[str] = []      # expected states worth saying, never counted (owner-run files not yet out)

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
                "depth_model", "urgency_meta", "featured", "steering_disclosure"})
    batches = need(rep, a, payload, "batches", list, "$") or []
    scenarios = need(rep, a, payload, "scenarios", list, "$") or []
    models_meta = need(rep, a, payload, "models_meta", list, "$") or []
    need(rep, a, payload, "traced", dict, "$")
    if "holdout_withheld" in payload and not _is(payload["holdout_withheld"], int):
        rep.err(a, "$.holdout_withheld", "must be an integer count")
    # Steered batches publish under a disclosure block (owner decision
    # 2026-08-15). If any scenario is flagged steered, the block must name its
    # batch: an unlabelled steered scenario reads as an ordinary cadence draw.
    disclosure = payload.get("steering_disclosure")
    if disclosure is not None:
        if not isinstance(disclosure, dict) or not disclosure.get("note"):
            rep.err(a, "$.steering_disclosure", "must be an object carrying a 'note'")
        declared = set((disclosure or {}).get("stamps") or [])
        flagged = {s.get("batch") for s in scenarios if s.get("steered")}
        missing = sorted(flagged - declared)
        if missing:
            rep.err(a, "$.steering_disclosure.stamps",
                    f"steered scenarios from undeclared batches: {missing}")
    elif any(s.get("steered") for s in scenarios):
        rep.err(a, "$.steering_disclosure",
                "scenarios are flagged steered but the payload declares no disclosure")

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
                              "vocabulary_status", "render_min_n"})
    # render gate (2026-07-28): pages pend any per-model cell below this n
    rmn = data.get("render_min_n")
    if rmn is not None and (not isinstance(rmn, int) or rmn < 1):
        rep.err(a, "$.render_min_n", "must be a positive integer when present")
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
        # critic 2026-07-31: newer exporter outputs gain shape coverage
        "tag_mass.json": ({"empirical": bool, "n_pairs": dict, "clinical": dict,
                           "patient": dict}, set()),
        "jspace.json": ({"empirical": bool, "source": dict, "panels": dict}, set()),
        "advice_scenarios.json": ({"selection": dict, "source": dict,
                                   "families": list}, set()),
        "judge_agreement.json": ({"tier_order": list, "n_paired": int,
                                  "exact": dict, "within_one": dict,
                                  "lean": dict, "matrix": list,
                                  "coverage": list, "policy": str}, set()),
        "drift_series.json": ({"pairs_file": str, "threshold": NUM,
                               "days_measured": list, "series": dict}, set()),
        # critic 2026-08-10: the three j-lens payloads the Technical page's chain
        # dereferences had no shape coverage, so a malformed export degraded
        # silently to the figure's "pending" state with every gate still green.
        # display_vocab.json is the dialect page's token blocklist and gates the
        # redirect gallery's featured picks - same silent-degrade shape.
        "jlens_transport.json": ({"generated_utc": str, "model": str,
                                  "census_batch": str, "n_pairs": int, "census": dict,
                                  "exemplars": list, "per_pair": list}, set()),
        "jlens_loglens.json": ({"generated_utc": str, "model": str, "jacobian": dict,
                                "logit": dict, "agreement": dict, "per_pair": list}, set()),
        "jlens_swaps.json": ({"swaps": dict}, set()),
        "display_vocab.json": ({"version": int, "match": str,
                                "fragment_blocklist": list,
                                "function_word_targets": dict}, set()),
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


# ------------------------------------------------------------------ owner-run files

# Files an owner-run exporter writes outside the daily Routine's publish chain (the site's contract table marks them
# "owner-run, not the daily Routine"). They are published once, after gates the Routine never sees (for the Multi-turn
# page: the design note's section 10 analysis, the vendor pack, the owner's sign-off), so until then their absence is
# the expected state: it is noted, never warned, because under --strict a warning would fail the Routine's gate over a
# file it has no business publishing. Present, they are shape-checked like any payload.
OWNER_RUN = {
    "petri_multiturn_summary.json": "scripts/export_petri_multiturn.py",
    "petri_multiturn_conversations.json": "scripts/export_petri_multiturn.py",
}
# the Multi-turn page reads these two as one unit (both real files, or both samples), in the shapes of
# multi-turn/index.html's reads; the .sample.json fixtures carry the same keys plus sample/_note
MT_PAIR = ("petri_multiturn_summary", "petri_multiturn_conversations")
MT_SUMMARY_KEYS = {"seed", "status", "headline", "style_sentence", "primary", "triples", "scenario_means", "repeats",
                   "provenance"}
MT_CONVERSATIONS_KEYS = {"seed", "measures", "mechanisms", "seeds", "conversations", "example"}
MT_SAMPLE_KEYS = {"sample", "_note"}
MT_PARTITIONS = ("seen_before_plan", "prospective")
# the page's three wording columns (multi-turn/index.html ARMS): a conversation is placed in one by its register, since
# an identity seed's arm ids carry the speaker as well
MT_REGISTERS = ("colloquial", "lay_careful", "clinical")
# a conversation's rule outcomes as scripts/petri_audit/rules.py writes them and the page reads them (the site contract
# fixture's `rule` keys): each field, its type, and whether null is allowed (Codex review of 2026-09-25)
MT_RULE_FIELDS = (("tool_invoked", bool, False), ("first_tool", str, True), ("first_call_turn", int, True),
                  ("advice_before_lookup", bool, True), ("marker_echo", bool, True), ("parse_error_call", int, False),
                  ("tool_calls_total", int, False), ("unknown_tool_calls", int, False),
                  ("tool_results_received", int, False), ("reasons", dict, False))
# who wrote an intermediate message of an exchange: the target (a reply before the graded one) or the scripted tool
MT_INTERIM_ROLES = ("assistant", "tool")
# the page that reads the pair; while it is on the site and the real pair is not published, it fetches the samples
MT_PAGE = "multi-turn/index.html"
# the staging directory of one write of the pair (export_petri_multiturn.swap_dir): present only when a write was
# interrupted between its two renames, so the pair beside it may be one new file and one old one
MT_SWAP_GLOB = ".petri_multiturn*.swap"


def _sample_flag(rep: Report, a: str, obj: dict, sample: bool):
    if sample and obj.get("sample") is not True:
        rep.err(a, "$.sample", "a .sample.json fixture must carry sample: true (the page's sample notice keys on it)")
    if not sample and (MT_SAMPLE_KEYS & set(obj)):
        rep.err(a, "$.sample", "a published file must not carry the sample flag or note")


def check_multiturn_summary(rep: Report, a: str, s: dict, sample: bool):
    _sample_flag(rep, a, s, sample)
    known_keys(rep, a, s, MT_SUMMARY_KEYS | (MT_SAMPLE_KEYS if sample else set()))
    # the analysis's bootstrap seed (a sample: its generator seed); the exporter always records one, and a summary
    # without it is not reproducible from its own output (AGENTS.md), so null is an error (Codex review, 2026-09-24)
    need(rep, a, s, "seed", int, "$")
    status = need(rep, a, s, "status", dict, "$") or {}
    need(rep, a, status, "final", bool, "$.status")
    need(rep, a, status, "clinician_review", str, "$.status")
    pack = need(rep, a, status, "vendor_pack", dict, "$.status") or {}
    # a sample has no pack; the real pair is public, so it cites the sent pack (pre-registration rules (1)-(2), design
    # note decision 16): a null version or send date fails --strict and plain runs alike (Codex review of 2026-09-25)
    for key in ("version", "sent"):
        value = need(rep, a, pack, key, str, "$.status.vendor_pack", nullable=sample)
        if not sample and isinstance(value, str) and not value.strip():
            rep.err(a, f"$.status.vendor_pack.{key}", "empty where the sent pack's value is required")
    for block in ("headline", "style_sentence"):
        b = need(rep, a, s, block, dict, "$") or {}
        need(rep, a, b, "row_id", str, f"$.{block}")
        need(rep, a, b, "text", str, f"$.{block}", nullable=True)
    p = need(rep, a, s, "primary", dict, "$") or {}
    for key in ("triples", "negative", "positive", "tied"):
        need(rep, a, p, key, int, "$.primary")
    for key in ("p_two_sided", "gate_p"):
        need(rep, a, p, key, NUM, "$.primary", nullable=True)
    need(rep, a, p, "gate_passed", bool, "$.primary", nullable=True)
    for i, t in enumerate(need(rep, a, s, "triples", list, "$") or []):
        path = f"$.triples[{i}]"
        for key, kinds in (("seed_id", str), ("scenario_id", str), ("epoch", int), ("eligible", bool)):
            need(rep, a, t, key, kinds, path)
        need(rep, a, t, "D", NUM, path, nullable=True)
        if isinstance(t, dict) and t.get("partition") not in MT_PARTITIONS:
            rep.err(a, f"{path}.partition", f"must be one of {list(MT_PARTITIONS)} (the figure's two panels)")
    for key, value in (need(rep, a, s, "scenario_means", dict, "$") or {}).items():
        if not _is(value, NUM):
            rep.err(a, f"$.scenario_means.{key}", "must be a number")
    for i, r in enumerate(need(rep, a, s, "repeats", list, "$") or []):
        need(rep, a, r, "seed_id", str, f"$.repeats[{i}]")
        need(rep, a, r, "epochs", int, f"$.repeats[{i}]")
        need(rep, a, r, "same_direction", int, f"$.repeats[{i}]", nullable=True)
    prov = need(rep, a, s, "provenance", dict, "$") or {}
    runs = need(rep, a, prov, "runs", list, "$.provenance") or []
    if not all(isinstance(r, str) for r in runs):
        rep.err(a, "$.provenance.runs", "must be a list of run ids")
    need(rep, a, prov, "analysis_commit", str, "$.provenance")
    # the section 10 artifact the summary was exported from, by sha256; a Petri pack's log entry records the same
    # digest (claim_ids.analysis_sha256), which binds the page to the analysis its cited pack was built from (Codex
    # review of PR #39, 2026-09-25). The site's own samples predate the key, so a sample may omit it; the exporter's
    # samples carry "SAMPLE"
    if sample:
        if "analysis_sha256" in prov and prov["analysis_sha256"] != "SAMPLE":
            rep.err(a, "$.provenance.analysis_sha256", 'a sample carries "SAMPLE" here, or nothing')
    else:
        digest = need(rep, a, prov, "analysis_sha256", str, "$.provenance")
        if isinstance(digest, str) and not (len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)):
            rep.err(a, "$.provenance.analysis_sha256", "must be the artifact file's sha256 (64 lowercase hex)")
    # the checkout the exporter ran from, naming its code and every input it read (Codex review of 2026-09-24)
    need(rep, a, prov, "exporter_commit", str, "$.provenance")
    need(rep, a, prov, "verify", str, "$.provenance")


def check_multiturn_conversations(rep: Report, a: str, c: dict, sample: bool):
    _sample_flag(rep, a, c, sample)
    known_keys(rep, a, c, MT_CONVERSATIONS_KEYS | (MT_SAMPLE_KEYS if sample else set()))
    # null in a published file (nothing in it is random); a sample records its generator seed
    need(rep, a, c, "seed", int, "$", nullable=not sample)
    measure_ids = set()
    for i, m in enumerate(need(rep, a, c, "measures", list, "$") or []):
        path = f"$.measures[{i}]"
        mid = need(rep, a, m, "id", str, path)
        for key, kinds in (("label", str), ("kind", str), ("values", list)):
            need(rep, a, m, key, kinds, path)
        need(rep, a, m, "definition", str, path, nullable=True)
        need(rep, a, m, "row", list, path, nullable=True)
        if mid:
            measure_ids.add(mid)
    mechanisms = need(rep, a, c, "mechanisms", dict, "$") or {}
    for key, value in mechanisms.items():
        need(rep, a, value, "title", str, f"$.mechanisms.{key}")
        need(rep, a, value, "question", str, f"$.mechanisms.{key}")
    seed_ids = set()
    for i, sd in enumerate(need(rep, a, c, "seeds", list, "$") or []):
        path = f"$.seeds[{i}]"
        sid = need(rep, a, sd, "seed_id", str, path)
        mech = need(rep, a, sd, "mechanism", str, path)
        if mech and mech not in mechanisms:
            rep.err(a, f"{path}.mechanism", f"{mech!r} is not in $.mechanisms (the seed header loses its question)")
        for key in ("measures", "arms", "roles", "hypotheses"):
            need(rep, a, sd, key, list, path)
        if sid:
            seed_ids.add(sid)
    for i, cv in enumerate(need(rep, a, c, "conversations", list, "$") or []):
        path = f"$.conversations[{i}]"
        sid = need(rep, a, cv, "seed_id", str, path)
        if sid and sid not in seed_ids:
            rep.err(a, f"{path}.seed_id", f"{sid} is not in $.seeds")
        need(rep, a, cv, "arm", str, path)
        need(rep, a, cv, "epoch", int, path)
        need(rep, a, cv, "identity", str, path, nullable=True)
        # the keys the page groups and selects by (Codex review of 2026-09-25: a file without register passed --strict)
        if need(rep, a, cv, "register", str, path) not in (None, *MT_REGISTERS):
            rep.err(a, f"{path}.register", f"must be one of {list(MT_REGISTERS)} (the page's three wording columns)")
        need(rep, a, cv, "conversation_id", str, path)
        need(rep, a, cv, "run", str, path)
        need(rep, a, cv, "run_epoch", int, path)
        rule = need(rep, a, cv, "rule", dict, path)
        # every rule field the page reads, typed (Codex review of 2026-09-25: a file missing tool_invoked or reasons
        # passed --strict)
        for key, kind, nullable in MT_RULE_FIELDS if rule is not None else ():
            need(rep, a, rule, key, kind, f"{path}.rule", nullable=nullable)
        # scripts/petri_audit/rules.py: every call's arguments in order, or null when no tool was invoked; a sample
        # carries the same shape (Codex review of 2026-09-24: the samples carried one string)
        if rule is not None and "query_text" not in rule:
            rep.err(a, f"{path}.rule.query_text", "missing required key")
        queries = (rule or {}).get("query_text")
        if queries is not None and not (isinstance(queries, list) and all(isinstance(q, str) for q in queries)):
            rep.err(a, f"{path}.rule.query_text", "must be a list of strings (each tool call's arguments) or null")
        for j, ex in enumerate(need(rep, a, cv, "exchanges", list, path) or []):
            xp = f"{path}.exchanges[{j}]"
            need(rep, a, ex, "user", str, xp)
            need(rep, a, ex, "reply", str, xp, nullable=True)
            need(rep, a, ex, "reply_is_graded", bool, xp)
            # the graded reply's turn, which labels it, and each intermediate message's role and text (Codex review of
            # 2026-09-25: an exchange without reply_turn, or an interim item without role or text, passed --strict)
            need(rep, a, ex, "reply_turn", int, xp)
            for k, item in enumerate(need(rep, a, ex, "interim", list, xp) or []):
                ip = f"{xp}.interim[{k}]"
                if need(rep, a, item, "role", str, ip) not in (None, *MT_INTERIM_ROLES):
                    rep.err(a, f"{ip}.role", f"must be one of {list(MT_INTERIM_ROLES)}")
                need(rep, a, item, "text", str, ip)
            for mid, cell in (need(rep, a, ex, "vals", dict, xp) or {}).items():
                if mid not in measure_ids:
                    rep.err(a, f"{xp}.vals.{mid}", "a grade for a measure $.measures does not define")
                elif not isinstance(cell, dict) or not ({"v", "na"} & set(cell)):
                    rep.err(a, f"{xp}.vals.{mid}", "a grade cell carries v (a value or null) or na (the reason)")
    example = need(rep, a, c, "example", dict, "$", nullable=True)
    for key in ("seed_id", "colloquial", "lay_careful", "clinical") if example else ():
        need(rep, a, example, key, str, "$.example")


def check_owner_run(rep: Report, site: Path):
    """The owner-run Multi-turn pair: absent (the expected state until it is published) is a note; one file without
    the other is an error; present files are shape-checked. The .sample.json fixtures are checked the same way,
    because the page fetches them whenever the real pair is not published: with the page on the site and the real
    pair not published, the sample pair is required (Codex review of 2026-09-24; before, a site with neither passed).
    A site without the page (the site's main before the page lands) needs neither."""
    for swap in sorted((site / "data").glob(MT_SWAP_GLOB)):
        rep.err(f"data/{swap.name}", "-", "an interrupted write of the Multi-turn pair left this, so the pair on disk "
                                          "may be one new file beside one old one: rerun the exporter (it puts the "
                                          "previous pair back first), or restore the pair from git and remove it")
    real_published = False
    for suffix, sample in ((".json", False), (".sample.json", True)):
        names = [stem + suffix for stem in MT_PAIR]
        present = [n for n in names if (site / "data" / n).is_file()]
        if not sample:
            real_published = len(present) == len(names)
        if not present:
            if not sample:
                rep.notes.append(f"{' and '.join(names)} not published (owner-run: {OWNER_RUN[names[0]]}); the "
                                 f"Multi-turn page renders its samples until they are")
            elif not real_published and (site / MT_PAGE).is_file():
                rep.err(" and ".join(names), "-", f"missing while {MT_PAGE} is on the site and the real pair is not "
                                                  f"published: the page falls back to these samples and has nothing "
                                                  f"to fetch")
            continue
        if len(present) == 1:
            rep.err(present[0], "-", "published without its pair: the Multi-turn page reads the summary and the "
                                     "conversations as one unit and falls back to both samples when either is missing")
        for name, check in ((names[0], check_multiturn_summary), (names[1], check_multiturn_conversations)):
            data = load(site, name, rep) if name in present else None
            if data is None:
                continue
            if not isinstance(data, dict):
                rep.err(name, "$", f"expected object, got {type(data).__name__}")
                continue
            check(rep, name, data, sample)


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
    check_owner_run(rep, site)
    if engine is not None and engine.is_dir():
        check_engine_copies(rep, site, engine)
    if strict:
        rep.errors.extend(rep.warnings)
        rep.warnings = []
    return rep


REPRO_PACK_STALE_MSG = ("repro-pack --check: a SENT vendor pack is stale or superseded-unsent "
                        "(see lines above) - an updated pack is owed before any per-model publication")
PETRI_REPRO_PACK_STALE_MSG = ("petri repro-pack --check: a SENT Petri vendor pack is stale or superseded-unsent "
                              "(see lines above) - an updated pack is owed before any public per-model Multi-turn "
                              "claim")
PETRI_PUBLICATION_UNMET_MSG = ("petri repro-pack --check --require-sent: the Multi-turn page's data files are public on "
                               "the site, but the Petri vendor pack it cites is not sent and FRESH (see lines above) - "
                               "the pack reaches the vendor before the page is public, and the page cites its version "
                               "(pre-registration rules (1)-(2); Petri design note decision 16)")
# The Multi-turn page's published data files (the site's data-contract table; written by the owner-run
# scripts/export_petri_multiturn.py). The synthetic fixtures the page is built on are named *.sample.json and never
# count: only a real file makes the page's per-model claim public.
PETRI_PUBLIC_FILES = ("petri_multiturn_summary.json", "petri_multiturn_conversations.json")


class Citation(NamedTuple):
    """What the Multi-turn page's published data cites (petri_publication)."""
    public: bool
    version: str | None
    runs: list[str]
    analysis_sha256: str | None
    errors: list[str]


def petri_publication(site: Path | None) -> Citation:
    """Whether the Multi-turn page's data is public, the Petri pack version its summary cites, the runs it publishes,
    the sha256 of the analysis artifact it publishes from, and errors.

    Public means either real data file is in the site's data/: the site deploys data/ from main, so a real file is
    public whether or not the page reads it yet, and it names the target model. The summary's
    `status.vendor_pack.version` is the page's citation of its pack (pre-registration rule (2)), and its
    `provenance.runs` names the runs the page publishes, which the cited pack must be built over (the pack builder
    refuses runs naming another vendor's model, so the run set binds both the vendor and the campaign), and its
    `provenance.analysis_sha256` the analysis artifact, which the cited pack must be built from (two analyses of the
    same runs are two packs; Codex, PR #39). A published summary that cites no version, no runs or no analysis digest,
    or cannot be read, is an error; so is the conversations file without the summary (Codex, PR #39): per-model data
    would be public with no page able to cite a pack. No real file means nothing is public, and nothing is required:
    today's state, with the samples at most."""
    if site is None:
        return Citation(False, None, [], None, [])
    data = Path(site) / "data"
    if not any((data / name).is_file() for name in PETRI_PUBLIC_FILES):
        return Citation(False, None, [], None, [])
    summary = data / PETRI_PUBLIC_FILES[0]
    if not summary.is_file():
        return Citation(True, None, [], None, [f"{PETRI_PUBLIC_FILES[1]} :: the conversations file is public without "
                                f"{PETRI_PUBLIC_FILES[0]}, so no page cites the Petri pack its per-model data is "
                                f"reproducible from; the two files are published together (pre-registration rule (2), "
                                f"Petri design note decision 16)"])
    where = f"{PETRI_PUBLIC_FILES[0]} :: $.status.vendor_pack.version"
    try:
        doc = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Citation(True, None, [], None, [f"{where} :: the published summary cannot be read "
                                               f"({type(exc).__name__}), so the Petri pack it cites cannot be checked"])
    status = doc.get("status") if isinstance(doc, dict) else None
    pack = status.get("vendor_pack") if isinstance(status, dict) else None
    version = pack.get("version") if isinstance(pack, dict) else None
    provenance = doc.get("provenance") if isinstance(doc, dict) else None
    runs = provenance.get("runs") if isinstance(provenance, dict) else None
    analysis = provenance.get("analysis_sha256") if isinstance(provenance, dict) else None
    errors = []
    if not isinstance(version, str) or not version.strip():
        errors.append(f"{where} :: the published summary cites no Petri pack version; a public per-model claim cites "
                      f"the sent pack it is reproducible from (pre-registration rule (2), Petri design note "
                      f"decision 16)")
    if (not isinstance(runs, list) or not runs
            or not all(isinstance(r, str) and r.strip() and r == r.strip() for r in runs)):
        errors.append(f"{PETRI_PUBLIC_FILES[0]} :: $.provenance.runs :: the published summary names no runs as a "
                      f"list of run directory names, so the Petri pack it cites cannot be bound to the data it "
                      f"publishes")
        runs = []
    if not (isinstance(analysis, str) and re.fullmatch(r"[0-9a-f]{64}", analysis)):
        errors.append(f"{PETRI_PUBLIC_FILES[0]} :: $.provenance.analysis_sha256 :: the published summary names no "
                      f"analysis artifact digest, so the Petri pack it cites cannot be bound to the analysis it "
                      f"publishes")
        analysis = None
    return Citation(True, version.strip() if isinstance(version, str) and version.strip() else None, list(runs),
                    analysis, errors)


def _pack_check(run: Callable[..., subprocess.CompletedProcess], cmd: list[str], engine_root: Path,
                messages: dict[int, str], name: str, what_currency: str) -> tuple[str, list[str]]:
    """One lane's pack check: (its stdout, errors). EVERY non-zero exit is an error (repro_pack_gate); `messages`
    names the exits the check defines (2, the stale or superseded-unsent sent pack; 4, the Petri publication
    requirement)."""
    r = run(cmd, capture_output=True, text=True, cwd=str(engine_root))
    out = (r.stdout or "").strip()
    if r.returncode == 0:
        return out, []
    if r.returncode in messages:
        return out, [messages[r.returncode]]
    what = ("found disclosure-log entries it could not read (see lines above)" if r.returncode == 3
            else "did not complete")
    tail = " | ".join((r.stderr or "").strip().splitlines()[-3:]) or "no stderr"
    return out, [f"{name} exited {r.returncode}: it {what}, so {what_currency} currency is "
                 f"unverified; stderr: {tail}"]


def repro_pack_gate(engine_root: Path,
                    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                    site: Path | None = None) -> tuple[str, list[str]]:
    """repro-pack currency (owner directive 2026-07-23): a sent vendor pack that has
    gone stale against the archive must surface within a daily cycle, not wait for
    someone to remember. The disclosure log lives in the engine checkout.

    Two checks read the one log, each owning its lane's entries and counting and
    skipping the other's: the advice lane's (`advice_eval.py repro-pack --check`)
    and, since 2026-09-24, the Petri lane's (`python -m scripts.petri_audit.cli
    repro-pack --check`), whose packs gate the Multi-turn page (design note
    decision 16). Each check's errors carry its own message, so a failure names
    its lane.

    Returns (both checks' stdout, errors). EVERY non-zero exit is an error. Until
    2026-09-23 only exit 2 was: a crash (exit 1, e.g. a KeyError on a log entry
    without stimuli_file) passed the gate with nothing printed, while it also hid
    any real escalation behind it. Exit 3 is the check naming log entries it
    could not read; anything else is the check failing to run. Either way pack
    currency is unverified, and the gate says so with the check's stderr tail.

    Publication (since 2026-09-24, Codex on PR #39). Pack currency alone let the
    Multi-turn page go public with no Petri pack built, or with one built and
    never sent: the check passes both, since it escalates only sent packs. When
    `site` holds the page's real data files (petri_publication), the Petri check
    also runs with --require-sent, the version the page's summary cites and the
    runs it publishes (--cited-run, one per run; the cited pack must be built
    over exactly those) and the analysis digest (--cited-analysis-sha256; the
    pack must be built from that artifact), even with no log, and exit 4 fails
    the gate. Without
    those files nothing is public, the check runs as it did, and a missing log
    still skips both checks, so the requirement cannot fail the gate before the
    page is published."""
    log = engine_root / "ops" / "disclosure_log.jsonl"
    has_log = log.is_file() and log.stat().st_size > 0
    public, cited, cited_runs, cited_analysis, publication_errors = petri_publication(site)
    if not has_log and not public:
        return "", []
    outs: list[str] = []
    errors: list[str] = []
    if has_log:
        advice_out, advice_errors = _pack_check(
            run, [sys.executable, str(engine_root / "scripts" / "advice_eval.py"), "repro-pack", "--check",
                  "--log", str(log)],
            engine_root, {2: REPRO_PACK_STALE_MSG}, "repro-pack --check", "vendor-pack")
        outs.append(advice_out)
        errors += advice_errors
    petri_cmd = [sys.executable, "-m", "scripts.petri_audit.cli", "repro-pack", "--check", "--log", str(log)]
    if public:
        petri_cmd += ["--require-sent"] + (["--cited-version", cited] if cited else [])
        for stem in cited_runs:
            petri_cmd += ["--cited-run", stem]
        if cited_analysis:
            petri_cmd += ["--cited-analysis-sha256", cited_analysis]
    petri_out, petri_errors = _pack_check(
        run, petri_cmd, engine_root, {2: PETRI_REPRO_PACK_STALE_MSG, 4: PETRI_PUBLICATION_UNMET_MSG},
        "petri repro-pack --check", "Petri vendor-pack")
    outs.append(petri_out)
    return "\n".join(o for o in outs if o), errors + publication_errors + petri_errors


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

    # repro-pack currency: see repro_pack_gate
    engine_root = Path(args.engine) if args.engine else Path(__file__).resolve().parents[1]
    pack_out, pack_errors = repro_pack_gate(engine_root, site=site)
    if not args.quiet and pack_out:
        print(pack_out)
    rep.errors.extend(pack_errors)

    if not args.quiet:
        for n in rep.notes:
            print("note:", n)
        for w in rep.warnings:
            print("warn:", w)
        for e in rep.errors:
            print("FAIL:", e)
    print(f"contract check: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
