"""Offline validator and scorer for an interpretability-instrument validity bundle.

The benchmark (docs/protocols/instrument_validity_benchmark.md) asks whether an interpretability instrument
(a raw component comparison, a lens readout, a generated label or verbalization, an explanation scorer) recovers
the same reference facts from matched case families written in medical and in everyday language. This module reads
one bundle (schemas/protocols/instrument_validity.v1.schema.json), refuses it by name when it breaks the contract,
and computes the prespecified endpoints one stage at a time.

It loads no model, contacts no service and reads no study data. Version 1 admits synthetic bundles only, and every
report it writes says so. A synthetic report is a software check, never a measurement.

Methods, all recorded in the report:

* Fact-recovery rate of one variant in one stage: mean credit over the family's reference facts (recovered 1, the
  plan's partial credit for partially, 0 for not_recovered and contradicted). A variant with any unassessed fact has
  no rate; its family is excluded from that stage with the reason, never scored as zero.
* Paired difference per family: medical rate minus everyday rate. The family is the independent unit.
* Interval: family-clustered percentile bootstrap. Families are resampled with replacement, `bootstrap_resamples`
  times, by `random.Random("<seed>:<stage>:<endpoint>:<analysis set>")`. With the resampled means sorted and
  k = round((1 - confidence_level) / 2 * resamples), the interval is the k-th smallest and the k-th largest mean.
* Verdict from the prespecified margin m and that interval: equivalent_within_margin only when the whole interval is
  inside (-m, +m); different_beyond_margin only when the whole interval is above +m or below -m; otherwise
  inconclusive. A difference that is not significant is never reported as equivalence.
* Binomial shares (changed-fact sensitivity, the behaviour-by-representation cells): Wilson score intervals at the
  plan's confidence level.
* Held-artifact effect: with one artifact fixed, the score of its medical-register description minus the score of
  its everyday-register description, averaged within family, then treated like any other paired difference.

Values are returned unrounded; rounding for display is the renderer's job.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.exploratory_methods import Refusal, digest, integer, require
    from scripts.frontend_contract_schema import check_schema_subset
except ImportError:  # run as a script from scripts/
    from exploratory_methods import Refusal, digest, integer, require
    from frontend_contract_schema import check_schema_subset

SCHEMA = "patientwords.instrument-validity/1"
REPORT_SCHEMA = "patientwords.instrument-validity-report/1"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "protocols" / "instrument_validity.v1.schema.json"
STATUS_LINE = "proposed PatientWords contribution; no register bias has been measured with it"
SYNTHETIC_LABEL = "synthetic software fixture - not a research result"

STAGES = ("activation", "readout", "label", "score")
DESCRIPTION_STAGES = ("label", "score")
SPLITS = ("discovery", "validation", "fresh_test")
PAIRED_REGISTERS = ("medical", "everyday")
REGISTERS = PAIRED_REGISTERS + ("within_register_paraphrase", "changed_fact")
FACT_STATUSES = ("recovered", "partially", "not_recovered", "contradicted")
RANK_STATUSES = ("observed", "not_observed_in_window", "not_recorded")
PRIMARY_SETS = ("validation", "fresh_test", "held_out")
SUBSETS = ("comparable_behaviour",)

EQUIVALENT = "equivalent_within_margin"
DIFFERENT = "different_beyond_margin"
INCONCLUSIVE = "inconclusive"
NO_MARGIN = "no_margin_declared"
VERDICT_RULE = ("equivalent_within_margin only when the whole interval lies inside (-margin, +margin); "
                "different_beyond_margin only when the whole interval lies above +margin or below -margin; "
                "otherwise inconclusive. A non-significant difference is never reported as equivalence.")
CELLS = ("behaviour_changed__representation_changed", "behaviour_changed__representation_unchanged",
         "behaviour_unchanged__representation_changed", "behaviour_unchanged__representation_unchanged")
LIMITATIONS = [
    "synthetic_not_measurement",
    "a representation difference with unchanged behaviour may be register encoding",
    "a behaviour difference without a detected representation difference may be limited method coverage",
    "no cell of the behaviour-by-representation table establishes tool bias or what the model understands",
    "exact-token ranks are lexical endpoints; a rank not observed in a top-k window is not an absence",
    "methods that share a vocabulary, a corpus or a judge are not independent replications",
]


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _refuse_non_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        require(math.isfinite(value), "non_finite_value", f"{path} is not a finite number")
    elif isinstance(value, dict):
        for key, child in value.items():
            _refuse_non_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for position, child in enumerate(value):
            _refuse_non_finite(child, f"{path}[{position}]")


def _reject_constant(name: str) -> None:
    raise Refusal("non_finite_value", f"{name} is not a finite number")


def load_bundle(path: Path) -> dict[str, Any]:
    """Read a bundle file, refusing NaN and Infinity tokens by name."""
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def load_schema() -> dict[str, Any]:
    """The structural schema this module executes."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------- validation

def _check_plan(bundle: dict[str, Any]) -> None:
    require(bundle["synthetic"], "real_bundle_not_admitted",
            "Version 1 scores synthetic bundles only; a real bundle needs a reviewed CI lane, and none is wired")
    require(bundle["execution_status"] == "synthetic", "synthetic_claims_measurement",
            "A synthetic bundle must declare execution_status 'synthetic'; it is never a measurement")
    plan = bundle["analysis_plan"]
    require(integer(plan["bootstrap_resamples"], 1), "analysis_plan", "bootstrap_resamples must be a positive integer")
    require(0 < plan["confidence_level"] < 1, "analysis_plan", "confidence_level must lie strictly between 0 and 1")
    require(0 <= plan["partial_credit"] <= 1, "analysis_plan", "partial_credit must lie between 0 and 1")
    require(integer(plan["minimum_families_for_verdict"], 2), "analysis_plan",
            "minimum_families_for_verdict must be an integer of at least 2")
    require(plan["primary_analysis_set"] in PRIMARY_SETS, "primary_analysis_set",
            f"The primary analysis set must be one of {PRIMARY_SETS}; it may not contain discovery families")
    subsets = plan["prespecified_subsets"]
    require(len(set(subsets)) == len(subsets) and set(subsets) <= set(SUBSETS), "analysis_plan",
            f"Known prespecified subsets: {SUBSETS}")

    margins = bundle["equivalence_margins"]
    require(margins["prespecified"], "margins_not_prespecified", "Equivalence margins must be fixed before data")
    require(_text(margins["fixed_before_data"]), "margins_not_prespecified",
            "Record where and when the margins were fixed")
    needed = ["fact_recovery_rate_difference"] + (["held_artifact_score_difference"] if bundle["held_artifact"] else [])
    for endpoint in needed:
        require(endpoint in margins["endpoints"], "missing_margins", f"No margin for endpoint {endpoint}")
    for endpoint, margin in margins["endpoints"].items():
        require(margin > 0, "invalid_margin", f"The margin for {endpoint} must be positive")

    for name, split in bundle["development"].items():
        require(split == "discovery", "development_split", f"{name} must be 'discovery', not {split!r}")
    thresholds = bundle["thresholds"]
    require(set(thresholds["representation_change"]) <= set(STAGES), "unknown_stage",
            "A representation threshold names an unknown stage")
    named = {"behaviour_change": thresholds["behaviour_change"],
             **{f"representation_change.{stage}": t for stage, t in thresholds["representation_change"].items()}}
    for name, threshold in named.items():
        require(threshold["selected_on_split"] == "discovery", "threshold_split",
                f"Threshold {name} was selected on {threshold['selected_on_split']!r}; only discovery is allowed")
        require(threshold["value"] >= 0, "invalid_threshold", f"Threshold {name} must be non-negative")
    identities = {**bundle["identities"],
                  **{f"{stage}.{key}": value for stage, body in bundle["stages"].items()
                     for key, value in body.items() if key != "observations"}}
    for name, value in identities.items():
        require(_text(value), "missing_identity", f"Identity {name} must be a non-empty string")


def _check_families(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require(bool(bundle["families"]), "missing_families", "At least one case family is required")
    families: dict[str, dict[str, Any]] = {}
    text_split: dict[str, str] = {}
    for family in bundle["families"]:
        fid, split = family["family_id"], family["split"]
        require(_text(fid), "missing_family", "family_id must be a non-empty string")
        require(split in SPLITS, "split", f"Family {fid}: split must be one of {SPLITS}")
        if fid in families:
            require(families[fid]["split"] == split, "split_leakage", f"Family {fid} appears in two splits")
            raise Refusal("duplicate_family", f"Family {fid} is listed twice")
        require(_text(family["review_status"]), "review_status", f"Family {fid}: review_status is required")
        fact_ids = [fact["fact_id"] for fact in family["reference_facts"]]
        require(bool(fact_ids) and len(set(fact_ids)) == len(fact_ids) and all(_text(x) for x in fact_ids)
                and all(_text(fact["text"]) for fact in family["reference_facts"]),
                "reference_facts", f"Family {fid}: reference facts need unique ids and text")
        entry: dict[str, Any] = {"split": split, "fact_ids": fact_ids, "variants": {}, "paraphrases": [],
                                 "controls": []}
        for variant in family["variants"]:
            vid, register = variant["variant_id"], variant["register"]
            require(_text(vid) and vid not in entry["variants"], "duplicate_variant",
                    f"Family {fid}: variant ids must be unique and non-empty")
            require(register in REGISTERS, "register", f"Variant {vid}: register must be one of {REGISTERS}")
            require(_text(variant["text"]), "missing_text", f"Variant {vid}: text is required")
            require(text_split.setdefault(variant["text"], split) == split, "split_leakage",
                    f"Variant {vid}: the same text occurs in two splits")
            entry["variants"][vid] = variant
            if register in PAIRED_REGISTERS:
                require(register not in entry, "duplicate_register", f"Family {fid} has two {register} variants")
                require("base_register" not in variant and "changed_fact_id" not in variant, "register",
                        f"Variant {vid}: a {register} variant is not derived from another variant")
                entry[register] = vid
                continue
            require(variant.get("base_register") in PAIRED_REGISTERS, "base_register",
                    f"Variant {vid}: base_register must be one of {PAIRED_REGISTERS}")
            if register == "changed_fact":
                require(variant.get("changed_fact_id") in fact_ids, "changed_fact",
                        f"Variant {vid}: changed_fact_id must name one reference fact of family {fid}")
                entry["controls"].append(vid)
            else:
                require("changed_fact_id" not in variant, "changed_fact",
                        f"Variant {vid}: a within-register paraphrase changes no fact")
                entry["paraphrases"].append(vid)
        for register in PAIRED_REGISTERS:
            require(register in entry, "missing_register", f"Family {fid} has no {register} variant")
        require(bool(entry["controls"]), "missing_changed_fact_control",
                f"Family {fid} needs at least one changed-fact control")
        families[fid] = entry
    return families


def _check_stages(bundle: dict[str, Any], families: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    behaviour: dict[tuple[str, str], float] = {}
    for stage, body in bundle["stages"].items():
        rows[stage] = {}
        for row in body["observations"]:
            fid, vid = row["family_id"], row["variant_id"]
            where = f"{stage}/{fid}/{vid}"
            require(fid in families, "unknown_family", f"{where}: unknown family")
            require(vid in families[fid]["variants"], "unknown_variant", f"{where}: unknown variant")
            require((fid, vid) not in rows[stage], "duplicate_observation", f"{where}: observed twice")
            require(set(row["fact_recovery"]) <= set(families[fid]["fact_ids"]), "unknown_fact",
                    f"{where}: fact_recovery names a fact outside the family's reference set")
            require(all(status is None or status in FACT_STATUSES for status in row["fact_recovery"].values()),
                    "fact_status", f"{where}: fact status must be one of {FACT_STATUSES} or null")
            require(row["unsupported_facts"] is None or row["unsupported_facts"] >= 0, "invalid_count",
                    f"{where}: unsupported_facts must be non-negative or null")
            require(all(row[key] is None or row[key] >= 1 for key in ("raw_rank", "filtered_rank")),
                    "invalid_rank", f"{where}: ranks are 1-based or null")
            require(row["rank_status"] in RANK_STATUSES, "rank_status",
                    f"{where}: rank_status must be one of {RANK_STATUSES}")
            observed = row["rank_status"] == "observed"
            require(observed == (row["raw_rank"] is not None) and (observed or row["filtered_rank"] is None),
                    "rank_status", f"{where}: a rank is recorded exactly when rank_status is 'observed'")
            if row["behaviour_value"] is not None:
                require(behaviour.setdefault((fid, vid), row["behaviour_value"]) == row["behaviour_value"],
                        "behaviour_inconsistent",
                        f"{where}: behaviour_value is the model's output and must agree across stages")
            rows[stage][fid, vid] = row
    return {"rows": rows, "behaviour": behaviour}


def _check_held_artifact(bundle: dict[str, Any], families: dict[str, dict[str, Any]]) -> None:
    fixed: dict[str, tuple[str, str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for record in bundle["held_artifact"]:
        aid = record["artifact_id"]
        require(_text(aid) and _text(record["artifact_sha256"]), "missing_identity",
                "A held artifact needs an id and a digest")
        require(record["family_id"] in families, "unknown_family", f"Held artifact {aid}: unknown family")
        require(record["stage"] in DESCRIPTION_STAGES, "held_artifact_stage",
                f"Held artifact {aid}: stage must be one of {DESCRIPTION_STAGES}")
        require(record["description_register"] in PAIRED_REGISTERS, "register",
                f"Held artifact {aid}: description_register must be one of {PAIRED_REGISTERS}")
        require(_text(record["description_text"]), "missing_text", f"Held artifact {aid}: description text is required")
        identity = (record["artifact_sha256"], record["family_id"], record["stage"])
        previous = fixed.setdefault(aid, identity)
        require(previous[0] == identity[0], "artifact_not_held_fixed",
                f"Held artifact {aid}: the digest differs between description registers")
        require(previous == identity, "held_artifact_identity",
                f"Held artifact {aid}: one artifact belongs to one family and one stage")
        key = (aid, record["description_register"])
        require(key not in seen, "duplicate_description", f"Held artifact {aid}: one description per register")
        seen.add(key)


def _validate(bundle: Any, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    require(isinstance(bundle, dict), "invalid_input", "A bundle is a JSON object")
    _refuse_non_finite(bundle)
    require(bundle.get("schema_version") == SCHEMA, "schema_version", f"Expected {SCHEMA}")
    require(integer(bundle.get("seed")), "missing_seed", "An explicit non-negative integer seed is required")
    require(isinstance(bundle.get("equivalence_margins"), dict), "missing_margins",
            "Equivalence margins must be present before scoring")
    stages = bundle.get("stages")
    require(isinstance(stages, dict) and bool(stages), "no_stages", "At least one stage is required")
    unknown = sorted(set(stages) - set(STAGES))
    require(not unknown, "unknown_stage", f"Unknown stages {unknown}; known stages are {STAGES}")
    errors: list[str] = []
    check_schema_subset(lambda artifact, path, message: errors.append(f"{path}: {message}"), "bundle", bundle,
                        schema or load_schema())
    require(not errors, "schema", "; ".join(errors[:10]) + (f"; and {len(errors) - 10} more" if errors[10:] else ""))
    _check_plan(bundle)
    families = _check_families(bundle)
    index = _check_stages(bundle, families)
    _check_held_artifact(bundle, families)
    return {"families": families, "family_ids": sorted(families), **index}


def validate_bundle(bundle: Any, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refuse a bundle that breaks the contract; otherwise return a short validation record."""
    try:
        index = _validate(bundle, schema)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", str(exc)) from exc
    families = index["families"]
    return {"schema_version": REPORT_SCHEMA, "status": "validated", "execution_status": "synthetic",
            "bundle_sha256": digest(bundle), "seed": bundle["seed"],
            "families_by_split": {split: sorted(f for f in families if families[f]["split"] == split)
                                  for split in SPLITS},
            "stages_supplied": [stage for stage in STAGES if stage in bundle["stages"]]}


# ------------------------------------------------------------------------------------------------------ scoring

def wilson_interval(successes: int, n: int, confidence: float) -> list[float] | None:
    """Wilson score interval for a binomial share; None when n is 0."""
    if n <= 0:
        return None
    z = statistics.NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    share = successes / n
    denominator = 1 + z * z / n
    centre = (share + z * z / (2 * n)) / denominator
    half = z * math.sqrt(share * (1 - share) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def bootstrap_mean_interval(values: list[float], resamples: int, confidence: float, seed_label: str) -> list[float]:
    """Percentile interval of the mean, resampling the given units with replacement.

    The generator is random.Random(seed_label). With the resampled means sorted and
    k = round((1 - confidence) / 2 * resamples), capped at (resamples - 1) // 2, the interval is
    [means[k], means[resamples - 1 - k]]."""
    rng = random.Random(seed_label)
    n = len(values)
    means = sorted(math.fsum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    k = min(round((1 - confidence) / 2 * resamples), (resamples - 1) // 2)
    return [means[k], means[resamples - 1 - k]]


def equivalence_verdict(interval: list[float], margin: float) -> str:
    """One of three outcomes from a prespecified margin; see VERDICT_RULE."""
    low, high = interval
    if -margin < low and high < margin:
        return EQUIVALENT
    if low > margin or high < -margin:
        return DIFFERENT
    return INCONCLUSIVE


def fact_recovery_rate(row: dict[str, Any] | None, fact_ids: list[str], partial_credit: float) -> float | None:
    """Mean credit over the reference facts; None when the row or any fact status is missing."""
    if row is None:
        return None
    statuses = [row["fact_recovery"].get(fact_id) for fact_id in fact_ids]
    if any(status is None for status in statuses):
        return None
    return math.fsum(_credit(status, partial_credit) for status in statuses) / len(statuses)


def _credit(status: str, partial_credit: float) -> float:
    return {"recovered": 1.0, "partially": float(partial_credit)}.get(status, 0.0)


def summarize_paired(differences: dict[str, float | None], reasons: dict[str, str], members: list[str], *,
                     margin: float | None, plan: dict[str, Any], seed_label: str) -> dict[str, Any]:
    """Mean paired difference over the member families that have one, with interval, verdict and denominators."""
    included = [fid for fid in members if differences.get(fid) is not None]
    values = [differences[fid] for fid in included]
    out: dict[str, Any] = {
        "n_families": len(members), "n_included": len(included),
        "excluded": [{"family_id": fid, "reason": reasons.get(fid, "no_paired_value")}
                     for fid in members if fid not in included],
        "mean_difference": math.fsum(values) / len(values) if values else None,
        "interval": None, "interval_status": "not_computed_fewer_than_minimum_families", "seed_label": None,
        "margin": margin, "verdict": INCONCLUSIVE if margin is not None else NO_MARGIN,
        "interval_excludes_zero": None,
        "null_family_ids": [fid for fid in included if differences[fid] == 0],
        "direction_discordant_family_ids": [],
    }
    if not values:
        out["interval_status"] = "not_computed_no_included_families"
        return out
    mean = out["mean_difference"]
    out["direction_discordant_family_ids"] = [fid for fid in included if differences[fid] * mean < 0]
    if len(values) >= plan["minimum_families_for_verdict"]:
        interval = bootstrap_mean_interval(values, plan["bootstrap_resamples"], plan["confidence_level"], seed_label)
        out.update(interval=interval, interval_status="computed", seed_label=seed_label,
                   interval_excludes_zero=interval[0] > 0 or interval[1] < 0)
        if margin is not None:
            out["verdict"] = equivalence_verdict(interval, margin)
    return out


def _by_set(differences: dict[str, float | None], reasons: dict[str, str], sets: dict[str, dict[str, Any]], *,
            margin: float | None, plan: dict[str, Any], label: str) -> dict[str, Any]:
    return {name: summarize_paired(differences, reasons, body["family_ids"], margin=margin, plan=plan,
                                   seed_label=f"{label}:{name}") for name, body in sets.items()}


def _model_behaviour(index: dict[str, Any], threshold: float) -> dict[str, Any]:
    per_family = {}
    for fid in index["family_ids"]:
        family = index["families"][fid]
        values = {register: index["behaviour"].get((fid, family[register])) for register in PAIRED_REGISTERS}
        missing = [f"behaviour_value:{register}" for register in PAIRED_REGISTERS if values[register] is None]
        difference = None if missing else values["medical"] - values["everyday"]
        per_family[fid] = {"family_id": fid, **values, "difference": difference, "missing": missing,
                           "changed": None if missing else abs(difference) > threshold}
    return {"evidence_about": "the model's output, not the instrument", "threshold": threshold,
            "per_family": [per_family[fid] for fid in index["family_ids"]], "_by_id": per_family}


def _analysis_sets(index: dict[str, Any], plan: dict[str, Any], behaviour: dict[str, Any]) -> dict[str, Any]:
    families, ids = index["families"], index["family_ids"]
    members = {"all": ids, **{split: [f for f in ids if families[f]["split"] == split] for split in SPLITS}}
    members["held_out"] = [f for f in ids if families[f]["split"] != "discovery"]
    sets = {name: {"family_ids": fids, "contains_discovery_families": any(families[f]["split"] == "discovery"
                                                                           for f in fids)}
            for name, fids in members.items()}
    if "comparable_behaviour" in plan["prespecified_subsets"]:
        changed = {fid: behaviour["_by_id"][fid]["changed"] for fid in ids}
        chosen = [fid for fid in ids if changed[fid] is False]
        sets["comparable_behaviour"] = {
            "family_ids": chosen, "definition": "prespecified: families whose behaviour difference is determined "
                                                "and not above the behaviour threshold",
            "contains_discovery_families": any(families[f]["split"] == "discovery" for f in chosen),
            "undetermined_family_ids": [fid for fid in ids if changed[fid] is None]}
    return sets


def _fact_recovery(stage: str, index: dict[str, Any], sets: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    plan, rows = bundle["analysis_plan"], index["rows"][stage]
    differences: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    per_family = []
    for fid in index["family_ids"]:
        family = index["families"][fid]
        rates = {}
        for register in PAIRED_REGISTERS:
            row = rows.get((fid, family[register]))
            rates[register] = fact_recovery_rate(row, family["fact_ids"], plan["partial_credit"])
            if rates[register] is None:
                reasons.setdefault(fid, f"{'missing_observation' if row is None else 'missing_fact_recovery'}"
                                        f":{register}")
        differences[fid] = None if fid in reasons else rates["medical"] - rates["everyday"]
        per_family.append({"family_id": fid, "split": family["split"], "medical_rate": rates["medical"],
                           "everyday_rate": rates["everyday"], "difference": differences[fid]})
    return {"endpoint": "paired medical-minus-everyday difference in fact-recovery rate, one value per family",
            "per_family": per_family, "_differences": differences,
            "analysis_sets": _by_set(differences, reasons, sets,
                                     margin=bundle["equivalence_margins"]["endpoints"]["fact_recovery_rate_difference"],
                                     plan=plan, label=f"{bundle['seed']}:{stage}:fact_recovery_rate_difference")}


def _share(successes: int, n: int, confidence: float) -> dict[str, Any]:
    return {"count": successes, "share": successes / n if n else None,
            "wilson_interval": wilson_interval(successes, n, confidence)}


def _changed_fact_sensitivity(stage: str, index: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    rows = index["rows"][stage]
    per_control = []
    for fid in index["family_ids"]:
        family = index["families"][fid]
        for vid in family["controls"]:
            variant = family["variants"][vid]
            fact_id, base = variant["changed_fact_id"], variant["base_register"]
            statuses = {name: (rows[fid, key]["fact_recovery"].get(fact_id) if (fid, key) in rows else None)
                        for name, key in (("base", family[base]), ("control", vid))}
            if None in statuses.values():
                outcome = "undetermined"
            elif _credit(statuses["base"], plan["partial_credit"]) == 0:
                outcome = "base_not_recovered"
            else:
                lower = _credit(statuses["control"], plan["partial_credit"]) < _credit(statuses["base"],
                                                                                        plan["partial_credit"])
                outcome = "detected" if lower else "not_detected"
            per_control.append({"family_id": fid, "variant_id": vid, "base_register": base,
                                "changed_fact_id": fact_id, "base_status": statuses["base"],
                                "control_status": statuses["control"], "outcome": outcome})
    by_base = {}
    for register in PAIRED_REGISTERS:
        outcomes = [c["outcome"] for c in per_control if c["base_register"] == register]
        detected, missed = outcomes.count("detected"), outcomes.count("not_detected")
        by_base[register] = {"n_controls": len(outcomes), "n_assessed": detected + missed,
                             "n_base_not_recovered": outcomes.count("base_not_recovered"),
                             "n_undetermined": outcomes.count("undetermined"),
                             "detected": _share(detected, detected + missed, plan["confidence_level"])}
    return {"endpoint": "share of changed-fact controls in which credit for the changed fact fell below its base "
                        "variant's credit; controls whose base variant earned no credit are counted apart",
            "by_base_register": by_base, "per_control": per_control}


def _stage_rows(stage: str, index: dict[str, Any], register: str) -> tuple[list[dict[str, Any]], int]:
    """(rows present, variants expected) for every variant of one register in one stage."""
    keys = [(fid, vid) for fid in index["family_ids"] for vid, variant in index["families"][fid]["variants"].items()
            if variant["register"] == register]
    return [index["rows"][stage][key] for key in keys if key in index["rows"][stage]], len(keys)


def _unsupported_facts(stage: str, index: dict[str, Any], sets: dict[str, Any], bundle: dict[str, Any]) -> dict:
    by_register = {}
    for register in REGISTERS:
        rows, expected = _stage_rows(stage, index, register)
        counts = [row["unsupported_facts"] for row in rows if row["unsupported_facts"] is not None]
        by_register[register] = {"n_variants": expected, "n_absent_rows": expected - len(rows),
                                 "n_missing_count": len(rows) - len(counts), "n_counted": len(counts),
                                 "total": sum(counts) if counts else None,
                                 "mean_per_description": sum(counts) / len(counts) if counts else None}
    differences: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    for fid in index["family_ids"]:
        family = index["families"][fid]
        counts = {r: (index["rows"][stage].get((fid, family[r])) or {}).get("unsupported_facts")
                  for r in PAIRED_REGISTERS}
        missing = [r for r in PAIRED_REGISTERS if counts[r] is None]
        if missing:
            reasons[fid] = f"missing_unsupported_count:{missing[0]}"
        differences[fid] = None if missing else float(counts["medical"] - counts["everyday"])
    return {"endpoint": "count of asserted facts that the reference set does not support, per description",
            "by_register": by_register,
            "paired_medical_minus_everyday": _by_set(
                differences, reasons, sets, plan=bundle["analysis_plan"],
                margin=bundle["equivalence_margins"]["endpoints"].get("unsupported_facts_count_difference"),
                label=f"{bundle['seed']}:{stage}:unsupported_facts_count_difference")}


def _paraphrase_consistency(stage: str, index: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    rows = index["rows"][stage]
    per_paraphrase = []
    for fid in index["family_ids"]:
        family = index["families"][fid]
        for vid in family["paraphrases"]:
            base = family["variants"][vid]["base_register"]
            pair = [rows.get((fid, family[base])), rows.get((fid, vid))]
            rates = [fact_recovery_rate(row, family["fact_ids"], plan["partial_credit"]) for row in pair]
            entry = {"family_id": fid, "variant_id": vid, "base_register": base, "agreement_share": None,
                     "rate_difference": None}
            if None not in rates:
                same = sum(pair[0]["fact_recovery"][f] == pair[1]["fact_recovery"][f] for f in family["fact_ids"])
                entry.update(agreement_share=same / len(family["fact_ids"]), rate_difference=rates[1] - rates[0])
            per_paraphrase.append(entry)
    by_base = {}
    for register in PAIRED_REGISTERS:
        entries = [e for e in per_paraphrase if e["base_register"] == register]
        scored = [e for e in entries if e["agreement_share"] is not None]
        by_base[register] = {
            "n_paraphrases": len(entries), "n_scored": len(scored), "n_undetermined": len(entries) - len(scored),
            "mean_agreement_share": math.fsum(e["agreement_share"] for e in scored) / len(scored) if scored else None,
            "mean_absolute_rate_difference": (math.fsum(abs(e["rate_difference"]) for e in scored) / len(scored)
                                              if scored else None)}
    return {"endpoint": "per-fact status agreement between a within-register paraphrase and its base variant; "
                        "the within-register variation against which a cross-register difference is read",
            "by_base_register": by_base, "per_paraphrase": per_paraphrase}


def _exact_token_ranks(stage: str, index: dict[str, Any]) -> dict[str, Any]:
    by_register = {}
    for register in REGISTERS:
        rows, expected = _stage_rows(stage, index, register)
        observed = [row for row in rows if row["rank_status"] == "observed"]
        filtered = [row["filtered_rank"] for row in observed if row["filtered_rank"] is not None]
        by_register[register] = {
            "n_variants": expected, "n_absent_rows": expected - len(rows), "n_observed": len(observed),
            "n_not_observed_in_window": sum(row["rank_status"] == "not_observed_in_window" for row in rows),
            "n_not_recorded": sum(row["rank_status"] == "not_recorded" for row in rows),
            "median_raw_rank": statistics.median(row["raw_rank"] for row in observed) if observed else None,
            "n_filtered_rank": len(filtered), "n_excluded_by_filter": len(observed) - len(filtered),
            "median_filtered_rank": statistics.median(filtered) if filtered else None}
    paired, unpaired = [], []
    for fid in index["family_ids"]:
        family = index["families"][fid]
        ranks = [(index["rows"][stage].get((fid, family[r])) or {}).get("raw_rank") for r in PAIRED_REGISTERS]
        if None in ranks:
            unpaired.append(fid)
        else:
            paired.append(ranks[0] - ranks[1])
    return {"endpoint_kind": "lexical", "note": "exact-token ranks; reported next to the semantic endpoints and "
            "never in place of them. Full-vocabulary and filtered ranks are separate. not_observed_in_window is "
            "not an absence and enters no median.",
            "by_register": by_register,
            "paired_raw_rank_medical_minus_everyday": {
                "n_families_both_observed": len(paired), "family_ids_without_both_ranks": unpaired,
                "median": statistics.median(paired) if paired else None}}


def _behaviour_by_representation(stage: str, index: dict[str, Any], behaviour: dict[str, Any],
                                 bundle: dict[str, Any]) -> dict[str, Any]:
    threshold = bundle["thresholds"]["representation_change"].get(stage)
    if threshold is None:
        return {"status": "undetermined", "reason": "no_representation_threshold_declared_for_stage"}
    confidence = bundle["analysis_plan"]["confidence_level"]
    members: dict[str, list[str]] = {cell: [] for cell in CELLS}
    undetermined = []
    for fid in index["family_ids"]:
        family = index["families"][fid]
        values = {r: (index["rows"][stage].get((fid, family[r])) or {}).get("representation_value")
                  for r in PAIRED_REGISTERS}
        missing = behaviour["_by_id"][fid]["missing"] + [f"representation_value:{r}" for r in PAIRED_REGISTERS
                                                         if values[r] is None]
        if missing:
            undetermined.append({"family_id": fid, "missing": missing})
            continue
        moved = abs(values["medical"] - values["everyday"]) > threshold["value"]
        members[f"behaviour_{'changed' if behaviour['_by_id'][fid]['changed'] else 'unchanged'}__"
                f"representation_{'changed' if moved else 'unchanged'}"].append(fid)
    n = sum(len(fids) for fids in members.values())
    status = "undetermined" if n == 0 else "partly_undetermined" if undetermined else "determined"
    return {"status": status, "representation_threshold": threshold["value"],
            "behaviour_threshold": behaviour["threshold"], "n_determined": n,
            "cells": {cell: {**_share(len(fids), n, confidence), "family_ids": fids} for cell, fids in members.items()},
            "undetermined": {"count": len(undetermined), "families": undetermined}}


def _held_artifact(index: dict[str, Any], sets: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"manipulation": "the artifact is held fixed; only the register of a meaning-equivalent "
                                           "description varies, so a score difference is a presentation or scoring "
                                           "effect, not a representation change"}
    for stage in DESCRIPTION_STAGES:
        records = [r for r in bundle["held_artifact"] if r["stage"] == stage]
        if not records:
            out[stage] = {"status": "not_supplied"}
            continue
        artifacts: dict[str, dict[str, Any]] = {}
        for record in records:
            entry = artifacts.setdefault(record["artifact_id"], {"artifact_id": record["artifact_id"],
                                                                 "family_id": record["family_id"]})
            entry[record["description_register"]] = record["score"]
            entry[f"has_{record['description_register']}"] = True
        per_artifact, by_family, reasons = [], {}, {}
        for aid in sorted(artifacts):
            entry = artifacts[aid]
            absent = [r for r in PAIRED_REGISTERS if not entry.get(f"has_{r}")]
            unscored = [r for r in PAIRED_REGISTERS if entry.get(f"has_{r}") and entry[r] is None]
            reason = (f"unpaired_description:{absent[0]}" if absent else
                      f"missing_score:{unscored[0]}" if unscored else None)
            difference = None if reason else entry["medical"] - entry["everyday"]
            per_artifact.append({"artifact_id": aid, "family_id": entry["family_id"],
                                 "medical_description_score": entry.get("medical"),
                                 "everyday_description_score": entry.get("everyday"),
                                 "difference": difference, "excluded_reason": reason})
            if reason:
                reasons.setdefault(entry["family_id"], reason)
            else:
                by_family.setdefault(entry["family_id"], []).append(difference)
        differences = {fid: math.fsum(values) / len(values) for fid, values in by_family.items()}
        with_records = {entry["family_id"] for entry in artifacts.values()}
        margin = bundle["equivalence_margins"]["endpoints"]["held_artifact_score_difference"]
        own_sets = {name: {"family_ids": [f for f in body["family_ids"] if f in with_records]}
                    for name, body in sets.items()}
        out[stage] = {
            "status": "scored", "n_artifacts": len(artifacts),
            "n_artifacts_included": sum(a["difference"] is not None for a in per_artifact),
            "families_without_records": [f for f in index["family_ids"] if f not in with_records],
            "per_artifact": per_artifact,
            "per_family": [{"family_id": fid, "difference": differences.get(fid)} for fid in sorted(with_records)],
            "analysis_sets": _by_set(differences, reasons, own_sets, plan=bundle["analysis_plan"], margin=margin,
                                     label=f"{bundle['seed']}:held_artifact_{stage}:held_artifact_score_difference")}
    return out


def _score(bundle: dict[str, Any], schema: dict[str, Any] | None) -> dict[str, Any]:
    index = _validate(bundle, schema)
    plan, ids = bundle["analysis_plan"], index["family_ids"]
    behaviour = _model_behaviour(index, bundle["thresholds"]["behaviour_change"]["value"])
    sets = _analysis_sets(index, plan, behaviour)
    stages: dict[str, Any] = {}
    signs: dict[str, set[int]] = {fid: set() for fid in ids}
    representation_moved: dict[str, bool] = {fid: False for fid in ids}
    for stage in STAGES:
        if stage not in bundle["stages"]:
            stages[stage] = {"status": "not_supplied"}
            continue
        recovery = _fact_recovery(stage, index, sets, bundle)
        table = _behaviour_by_representation(stage, index, behaviour, bundle)
        for fid, difference in recovery.pop("_differences").items():
            if difference is not None:
                signs[fid].add((difference > 0) - (difference < 0))
        for cell, body in table.get("cells", {}).items():
            if cell.endswith("representation_changed"):
                for fid in body["family_ids"]:
                    representation_moved[fid] = True
        stages[stage] = {
            "status": "scored", "evidence_about": "the instrument's output at this stage",
            "identity": {key: value for key, value in bundle["stages"][stage].items() if key != "observations"},
            "fact_recovery": recovery,
            "changed_fact_sensitivity": _changed_fact_sensitivity(stage, index, plan),
            "unsupported_facts": _unsupported_facts(stage, index, sets, bundle),
            "paraphrase_consistency": _paraphrase_consistency(stage, index, plan),
            "exact_token_ranks": _exact_token_ranks(stage, index),
            "behaviour_by_representation": table}
    by_id = behaviour.pop("_by_id")
    families = index["families"]
    held = _held_artifact(index, sets, bundle)
    keep = ("n_families", "n_included", "mean_difference", "interval", "margin", "verdict")
    primary = plan["primary_analysis_set"]
    primary_results = {
        "analysis_set": primary,
        "fact_recovery_rate_difference": {
            stage: ({key: body["fact_recovery"]["analysis_sets"][primary][key] for key in keep}
                    if body["status"] == "scored" else {"status": "not_supplied"})
            for stage, body in stages.items()},
        "held_artifact_score_difference": {
            stage: ({key: held[stage]["analysis_sets"][primary][key] for key in keep}
                    if held[stage]["status"] == "scored" else {"status": "not_supplied"})
            for stage in DESCRIPTION_STAGES}}
    return {
        "schema_version": REPORT_SCHEMA, "status": "scored", "benchmark_status": STATUS_LINE,
        "execution_status": "synthetic", "synthetic": True, "evidence_label": SYNTHETIC_LABEL,
        "bundle_sha256": digest(bundle), "seed": bundle["seed"],
        "randomness": {"generator": "random.Random", "seed_rule": "'<seed>:<stage>:<endpoint>:<analysis set>'",
                       "interval": "family-clustered percentile bootstrap of the mean",
                       "bootstrap_resamples": plan["bootstrap_resamples"],
                       "confidence_level": plan["confidence_level"]},
        "analysis_plan": plan, "equivalence_margins": bundle["equivalence_margins"],
        "thresholds": bundle["thresholds"], "development": bundle["development"],
        "identities": bundle["identities"], "verdict_rule": VERDICT_RULE,
        "families": {"n": len(ids), "by_split": {split: [f for f in ids if families[f]["split"] == split]
                                                 for split in SPLITS},
                     "review_status": {f["family_id"]: f["review_status"] for f in bundle["families"]}},
        "analysis_sets": sets, "primary_results": primary_results,
        "model_behaviour": behaviour, "stages": stages, "held_artifact": held,
        "null_family_ids": [fid for fid in ids if signs[fid] == {0} and by_id[fid]["changed"] is False
                            and not representation_moved[fid]],
        "null_family_rule": "zero fact-recovery difference in every stage that scored the family, a determined and "
                            "unchanged behaviour, and no detected representation change in any determined table",
        "cross_stage_sign_discordant_family_ids": [fid for fid in ids if {1, -1} <= signs[fid]],
        "limitations": LIMITATIONS}


def score_bundle(bundle: Any, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a bundle and compute every prespecified endpoint; malformed shapes refuse by name."""
    try:
        return _score(bundle, schema)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", str(exc)) from exc


def _write_exclusive(out: Path, result: dict[str, Any]) -> None:
    require(out.name.startswith("instrument_validity_report.") and out.suffix == ".json", "output_namespace",
            "Use instrument_validity_report.<id>.json")
    resolved = out.resolve()
    require(resolved.parent.name == "instrument_validity", "output_namespace", "Use an instrument_validity/ directory")
    forbidden = {"trace_out", "data", "pilot", ".github", "ops", ".claude", ".githooks", ".git", "modes"}
    require(not forbidden.intersection(resolved.parts), "output_namespace", "Protected output root")
    require(not any((parent / ".git").exists() for parent in resolved.parents), "output_namespace",
            "Write outside every Git checkout; a synthetic report is not committed")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bundle", required=True, type=Path, help="benchmark bundle JSON")
    parser.add_argument("--out", type=Path,
                        help="write instrument_validity/instrument_validity_report.<id>.json (exclusive create, "
                             "outside every Git checkout); default prints to stdout")
    args = parser.parse_args(argv)
    try:
        result = score_bundle(load_bundle(args.bundle))
        if args.out:
            _write_exclusive(args.out, result)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (Refusal, OSError, ValueError) as exc:
        print(json.dumps({"schema_version": REPORT_SCHEMA, "status": "refused",
                          "code": exc.code if isinstance(exc, Refusal) else "invalid_input", "detail": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
