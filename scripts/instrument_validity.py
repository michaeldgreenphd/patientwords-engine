"""Offline validator and scorer for an interpretability-instrument validity bundle.

The benchmark (docs/protocols/instrument_validity_benchmark.md) asks whether an interpretability instrument
(a raw component comparison, a lens readout, a generated label or verbalization, an explanation scorer) recovers
the same reference facts from matched case families written in medical and in everyday language. This module reads
one bundle (schemas/protocols/instrument_validity.v1.schema.json), refuses it by name when it breaks the contract,
and computes the prespecified endpoints one stage at a time.

It loads no model, contacts no service and reads no study data. Besides the bundle it reads two repository files:
the schema, and the draft rubric (data/protocols/instrument_validity_rubric.draft.json) for the fixed irrelevant
placeholder description. Version 1 admits synthetic bundles only, and every report it writes says so. A synthetic
report is a software check, never a measurement.

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
* Description controls (the label and score stages). The bundle may carry the evaluation items of each held artifact:
  the truth label of every item, the scorer's verdict on it under the matched description of each register, under a
  shuffled description (the description of another artifact, by a seeded derangement that this module recomputes)
  and under the rubric's irrelevant placeholder description, and the cues the item exposes. Every score in the
  controls is balanced accuracy over one artifact's items, so all conditions are scored on the same items.
* Explanation-free baseline: a closed family of rules that read an item's construction and never the description
  (EXPLANATION_FREE_RULES). Each cue-only rule is fitted on the pooled discovery items, the rule with the highest
  mean score over discovery families is selected (ties: the earliest rule in the closed list) and then frozen.
* Control rule: per description stage and analysis set, the matched description must outscore the shuffled
  description, the irrelevant description and the frozen baseline, in each register, by the prespecified control
  margin. "Outscores" means that the whole family-clustered bootstrap interval of the mean difference lies above the
  margin. Any other state (CONTROL_STATES) replaces the held-artifact verdict. A missing control is never a pass.
* Cue association: Pearson correlation between a cue and a score over families, with a permutation p-value from
  random.Random("<seed>:cue:<stage>:<cue>[:<register>]:<analysis set>"), (1 + count) / (1 + permutations).
* Input-only and control-artifact arms (the label and score stages, optional). Where the stage's instrument reads an
  activation artifact, the bundle may also carry what the same system reports when it is given the wording alone
  (input_only) and when it is given the same-register artifact of another family (control_artifact; the other family
  is fixed by seeded_derangement over the family ids with the label "<seed>:control_artifact:<stage>"). Per register
  and analysis set, the family-clustered bootstrap interval of the mean of (actual-artifact rate minus arm rate) is
  compared with the arm's prespecified margin, as for a description control. The stage then carries one arm state
  (ARM_STATES). Each state names what was measured. Only artifact_contributes supports reading the stage's fact
  recovery as coming from the artifact. The two no_advantage states say that the actual artifact did not outperform
  an arm by the margin; they do not say that the system ignored the artifact or that its output came from the wording
  (when no arm recovers anything, no arm outperforms another, and nothing is shown about either). The mean rate of
  every arm is reported beside the state. The medical-minus-everyday difference is reported for each arm, and the
  artifact arm's difference minus the input-only arm's difference with its interval.
* Calibration record (--calibrate --quantile Q). For a bundle that holds discovery families only, per stage: the
  absolute difference between each within-register paraphrase and its base variant, in fact-recovery rate and in
  representation_value, averaged within family; then the median, the nearest-rank quantile Q and the maximum over
  families. The quantile of the representation differences is what a study protocol may name as its
  representation-change threshold. The record computes no margin: a margin is a stated judgement of the protocol,
  and the record supplies the within-register variation it has to exceed. A bundle with any family outside
  discovery is refused (calibration_reads_held_out), so held-out families cannot inform a threshold.
* A medical or everyday text that occurs in two families is refused (repeated_phrase): a phrase is one unit, and a
  repeated phrase scored as two families would be counted as two independent observations.

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
CALIBRATION_SCHEMA = "patientwords.instrument-validity-calibration/1"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "protocols" / "instrument_validity.v1.schema.json"
RUBRIC_PATH = SCHEMA_PATH.parents[2] / "data" / "protocols" / "instrument_validity_rubric.draft.json"
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

SCORE_METRIC = "balanced_accuracy"
VERDICT_CONDITIONS = ("medical", "everyday", "shuffled_medical", "shuffled_everyday", "irrelevant")
CONTROLS = ("shuffled", "irrelevant", "explanation_free")
CONTROL_MARGINS = {control: f"matched_minus_{control}" for control in CONTROLS}
CONSTANT_RULES = ("always_positive", "always_negative", "majority_class")
CUE_RULES = {"span_position": ("span_position", "category"), "span_marking": ("span_marking", "category"),
             "window_length": ("window_token_count", "threshold"),
             "presentation_order": ("presentation_index", "threshold")}
EXPLANATION_FREE_RULES = CONSTANT_RULES + tuple(CUE_RULES)
DESCRIPTION_CUES = {"description_length": "description_token_count", "description_formatting": "formatting_class",
                    "description_order": "presentation_order"}

CONTROLS_PASSED = "controls_passed"
CONTROL_NOT_RUN = "control_not_run"
CONTROL_INCOMPLETE = "control_incomplete"
# Named scorer_does_not_read_description until 2026-11-11. The comparison shows that the matched description did
# not outscore a control description by the margin; it does not show why, and it is also the result when every
# condition scores the same for another reason.
NO_ADVANTAGE_OVER_DESCRIPTION = "no_advantage_over_control_description"
BASELINE_NOT_BEATEN = "baseline_not_beaten"
READING_NOT_SHOWN = "description_reading_not_shown"
BASELINE_NOT_SHOWN = "baseline_advantage_not_shown"
CONTROL_STATES = (CONTROLS_PASSED, CONTROL_NOT_RUN, CONTROL_INCOMPLETE, NO_ADVANTAGE_OVER_DESCRIPTION,
                  BASELINE_NOT_BEATEN, READING_NOT_SHOWN, BASELINE_NOT_SHOWN)
BEATEN, NOT_BEATEN, NOT_SHOWN = "control_beaten", "control_not_beaten", "advantage_not_shown"
CONTROL_OUTCOMES = (BEATEN, NOT_BEATEN, NOT_SHOWN)
EXPOSED, NOT_EXPOSED, PARTLY_RECORDED = "exposed", "not_exposed", "partly_recorded"
CUE_STATES = (EXPOSED, NOT_EXPOSED, PARTLY_RECORDED)
ASSOCIATED, NOT_ASSOCIATED, NOT_COMPUTABLE = "association_detected", "association_not_detected", "not_computable"
ASSOCIATION_STATES = (ASSOCIATED, NOT_ASSOCIATED, NOT_COMPUTABLE, NOT_EXPOSED, PARTLY_RECORDED)
ARMS = ("input_only", "control_artifact")
ARM_MARGINS = {arm: f"artifact_minus_{arm}" for arm in ARMS}
ARTIFACT_CONTRIBUTES = "artifact_contributes"
ARMS_NOT_RUN = "arms_not_run"
ARMS_INCOMPLETE = "arms_incomplete"
# The two states below were named system_does_not_read_artifact and recoverable_from_wording_alone until
# 2026-11-11. Those names stated a cause. The comparison measures an advantage, and its absence does not establish
# one: with no fact recovered in any arm, no arm outperforms another and the old name still said the system did not
# read the artifact.
NO_ADVANTAGE_OVER_CONTROL = "no_advantage_over_control_artifact"
NO_ADVANTAGE_OVER_WORDING = "no_advantage_over_wording_alone"
SPECIFICITY_NOT_SHOWN = "artifact_specificity_not_shown"
CONTRIBUTION_NOT_SHOWN = "artifact_contribution_not_shown"
ARM_STATES = (ARTIFACT_CONTRIBUTES, ARMS_NOT_RUN, ARMS_INCOMPLETE, NO_ADVANTAGE_OVER_CONTROL,
              NO_ADVANTAGE_OVER_WORDING, SPECIFICITY_NOT_SHOWN, CONTRIBUTION_NOT_SHOWN)
ARM_STATE_MEANING = {
    ARTIFACT_CONTRIBUTES: "in each register the actual artifact outperformed the control artifact and the wording "
                          "alone by the prespecified margin",
    ARMS_NOT_RUN: "an arm has no data in this set, so nothing is compared",
    ARMS_INCOMPLETE: "arm data, or the actual-artifact row it is compared with, is missing for some family",
    NO_ADVANTAGE_OVER_CONTROL: "in some register the actual artifact did not outperform the control artifact by the "
                               "margin; this is no demonstrated advantage, not a finding that the system ignores "
                               "the artifact",
    NO_ADVANTAGE_OVER_WORDING: "in some register the actual artifact did not outperform the wording alone by the "
                               "margin; this is no demonstrated advantage, not a finding that the output came from "
                               "the wording",
    SPECIFICITY_NOT_SHOWN: "the interval of the advantage over the control artifact contains the margin",
    CONTRIBUTION_NOT_SHOWN: "the interval of the advantage over the wording alone contains the margin",
}
NOTHING_RECOVERED_NOTE = ("no arm recovered any fact in this set, so no arm could outperform another; the comparison "
                          "is uninformative about the artifact and about the wording")
ARM_RULE = (
    "A label or score stage whose instrument reads an activation artifact is described as reading that artifact only "
    "in the state artifact_contributes: in each register, the whole family-clustered bootstrap interval of the mean of "
    "(fact-recovery rate with the actual artifact minus the rate of the arm) lies above the prespecified arm margin, "
    "for the matched control artifact and for the wording alone. The first state that applies is returned: "
    "arms_not_run, arms_incomplete, no_advantage_over_control_artifact (the control artifact is not beaten), "
    "no_advantage_over_wording_alone (the wording alone is not beaten), artifact_specificity_not_shown, "
    "artifact_contribution_not_shown. A state other than artifact_contributes means that the advantage was not "
    "demonstrated at the margin. It establishes nothing more: not that the system ignores the artifact, and not that "
    "its output comes from the wording. An arm that recovers nothing, or was not measured, is not evidence for "
    "either. The mean rate of every arm is reported with the state. Missing arm data is never read as zero or as a "
    "pass.")
CONTROL_RULE = (
    "The held-artifact endpoint of a description stage gets a verdict only in the state controls_passed: in each "
    "register, the whole family-clustered bootstrap interval of the mean of (matched score minus control score) lies "
    "above the prespecified control margin, for the shuffled description, the irrelevant description and the frozen "
    "explanation-free baseline, on the same items. In every other state the state name replaces the verdict. "
    "A state names the comparison that was not passed. It does not establish why: "
    "no_advantage_over_control_description says the matched description did not outscore the shuffled or the "
    "irrelevant description by the margin, not that the scorer ignores descriptions. "
    "control_not_run and control_incomplete record missing control data; missing is never read as zero or as a pass. "
    "The report holds no verdict that a stage passes.")
LIMITATIONS = [
    "synthetic_not_measurement",
    "a representation difference with unchanged behaviour may be register encoding",
    "a behaviour difference without a detected representation difference may be limited method coverage",
    "no cell of the behaviour-by-representation table establishes tool bias or what the model understands",
    "exact-token ranks are lexical endpoints; a rank not observed in a top-k window is not an absence",
    "methods that share a vocabulary, a corpus or a judge are not independent replications",
    "a cue reported as not_exposed was not checked; it is not a pass",
    "the explanation-free baseline is the best rule of a closed family; a rule outside the family is not excluded",
    "an association that was not detected is not evidence that the cue has no effect",
    "an arm state other than artifact_contributes says the stage's reading was not shown to come from the artifact",
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


def load_rubric() -> dict[str, Any]:
    """The draft rubric; it defines the irrelevant placeholder description the controls must use."""
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


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
    paired_text_family: dict[str, str] = {}
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
                first = paired_text_family.setdefault(variant["text"], fid)
                require(first == fid, "repeated_phrase",
                        f"Variant {vid}: the same {register} text is a variant of family {first}; a phrase is one "
                        "unit, so merge the two families or drop one")
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


def _check_held_artifact(bundle: dict[str, Any], families: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    fixed: dict[str, tuple[str, str, str]] = {}
    seen: set[tuple[str, str]] = set()
    artifacts: dict[str, dict[str, Any]] = {}
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
        count, order = record.get("description_token_count"), record.get("presentation_order")
        require(count is None or count >= 1, "invalid_cue_value",
                f"Held artifact {aid}: description_token_count is a positive integer or null")
        require(record.get("formatting_class") is None or _text(record["formatting_class"]), "invalid_cue_value",
                f"Held artifact {aid}: formatting_class is a non-empty string or null")
        entry = artifacts.setdefault(aid, {"family_id": record["family_id"], "stage": record["stage"], "records": {}})
        require(order is None or (order in (1, 2) and all(other.get("presentation_order") != order
                                                          for other in entry["records"].values())),
                "invalid_cue_value", f"Held artifact {aid}: presentation_order is 1 or 2, once each per artifact")
        entry["records"][record["description_register"]] = record
    return artifacts


def balanced_accuracy(labels: list[bool], predictions: list[bool]) -> float | None:
    """Mean of the true-positive rate and the true-negative rate; None when either class has no item."""
    positives = [prediction for label, prediction in zip(labels, predictions) if label]
    negatives = [prediction for label, prediction in zip(labels, predictions) if not label]
    if not positives or not negatives:
        return None
    return (sum(positives) / len(positives) + sum(not prediction for prediction in negatives) / len(negatives)) / 2


def seeded_derangement(family_of: dict[str, str], seed_label: str,
                       max_attempts: int = 1000) -> tuple[dict[str, str], int] | None:
    """Assign every artifact the description of another artifact that belongs to a different family.

    The artifact ids are sorted. A copy is shuffled by random.Random(seed_label) until no artifact is paired with an
    artifact of its own family (which also rules out itself). Returns (mapping, attempts used), or None when no such
    assignment is found in max_attempts shuffles."""
    ids = sorted(family_of)
    rng = random.Random(seed_label)
    for attempt in range(1, max_attempts + 1):
        sources = list(ids)
        rng.shuffle(sources)
        if all(family_of[aid] != family_of[source] for aid, source in zip(ids, sources)):
            return dict(zip(ids, sources)), attempt
    return None


def _condition_score(rows: list[dict[str, Any]], condition: str) -> tuple[float | None, str | None]:
    """(balanced accuracy of one description condition on one artifact's items, reason when it is missing)."""
    if not rows:
        return None, "no_evaluation_items"
    verdicts = [(row.get("verdicts") or {}).get(condition) for row in rows]
    if any(verdict is None for verdict in verdicts):
        return None, "missing_item_verdict"
    score = balanced_accuracy([row["label"] for row in rows], verdicts)
    return score, None if score is not None else "single_class_items"


def _check_controls(bundle: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    items: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for item in bundle.get("evaluation_items", []):
        aid, item_id = item["artifact_id"], item["item_id"]
        where = f"Evaluation item {aid}/{item_id}"
        require(aid in artifacts, "unknown_artifact", f"{where}: no held-artifact record has this artifact_id")
        require(_text(item_id) and (aid, item_id) not in seen, "duplicate_item",
                f"{where}: item ids must be unique within an artifact and non-empty")
        seen.add((aid, item_id))
        require(set(item.get("verdicts") or {}) <= set(VERDICT_CONDITIONS), "verdict_condition",
                f"{where}: verdicts are keyed by {VERDICT_CONDITIONS}")
        require(all(item.get(field) is None or _text(item[field]) for field in ("span_position", "span_marking"))
                and all(item.get(field) is None or item[field] >= 1
                        for field in ("window_token_count", "presentation_index")),
                "invalid_cue_value", f"{where}: a cue is a non-empty string, a positive integer, or null")
        items.setdefault(aid, []).append(item)
    for aid, rows in items.items():
        shown = [row["presentation_index"] for row in rows if row.get("presentation_index") is not None]
        require(len(set(shown)) == len(shown), "invalid_cue_value",
                f"Artifact {aid}: two evaluation items share one presentation_index")
        for register, record in artifacts[aid]["records"].items():
            recomputed, _ = _condition_score(rows, register)
            require(recomputed is None or record["score"] is None or abs(recomputed - record["score"]) <= 1e-9,
                    "score_not_reproduced_from_items",
                    f"Held artifact {aid}: the {register} score {record['score']} is not the balanced accuracy "
                    f"{recomputed} of its item verdicts")
    plan = bundle.get("description_controls")
    if plan is None:
        return items
    require(plan["prespecified"], "control_margins_not_prespecified", "Control margins must be fixed before data")
    require(_text(plan["fixed_before_data"]), "control_margins_not_prespecified",
            "Record where and when the control margins were fixed")
    require(plan["score_metric"] == SCORE_METRIC, "score_metric",
            f"Version 1 scores description controls with {SCORE_METRIC} over binary item verdicts only")
    for name in CONTROL_MARGINS.values():
        require(name in plan["margins"], "missing_control_margins", f"No control margin named {name}")
    require(set(plan["margins"]) == set(CONTROL_MARGINS.values()), "unknown_control_margin",
            f"Known control margins: {sorted(CONTROL_MARGINS.values())}")
    for name, margin in plan["margins"].items():
        require(margin > 0, "invalid_margin", f"The control margin {name} must be positive")
    require(tuple(plan["explanation_free_rules"]) == EXPLANATION_FREE_RULES, "explanation_free_rule_family",
            f"The explanation-free rule family is closed: {EXPLANATION_FREE_RULES}")
    require(integer(plan["cue_association"]["permutations"], 1) and 0 < plan["cue_association"]["alpha"] < 1,
            "analysis_plan", "cue_association needs a positive integer permutations and an alpha between 0 and 1")
    placeholder = load_rubric()["description_controls"]["irrelevant_description"]
    require(plan["irrelevant_description"] == {key: placeholder[key] for key in ("placeholder_id", "text")},
            "irrelevant_description", "The irrelevant description must be the rubric's fixed placeholder, id and text")
    shuffle = plan["shuffle"]
    require(integer(shuffle["seed"]), "missing_seed", "The shuffle needs an explicit non-negative integer seed")
    require(set(shuffle["mapping"]) <= set(DESCRIPTION_STAGES), "unknown_stage",
            f"A shuffle mapping is keyed by one of {DESCRIPTION_STAGES}")
    for stage, mapping in shuffle["mapping"].items():
        expected = seeded_derangement({aid: body["family_id"] for aid, body in artifacts.items()
                                       if body["stage"] == stage}, f"{shuffle['seed']}:shuffle:{stage}")
        require(expected is not None and mapping == expected[0], "shuffle_mapping_not_reproducible",
                f"The {stage} shuffle mapping is not the seeded derangement of that stage's artifacts")
        for aid, source in mapping.items():
            for register, record in artifacts[aid]["records"].items():
                other = artifacts[source]["records"].get(register)
                require(other is None or other["description_text"] != record["description_text"],
                        "shuffle_identical_description",
                        f"Held artifact {aid}: its shuffled {register} description has its own text")
    return items


def _check_verbalizer_arms(bundle: dict[str, Any],
                           families: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``{stage: {"rows": {(family_id, register, arm): row}, "mapping": {...}}}`` for the optional arms."""
    section = bundle.get("verbalizer_arms")
    if section is None:
        return {}
    require(section["prespecified"], "arm_margins_not_prespecified", "Arm margins must be fixed before data")
    require(_text(section["fixed_before_data"]), "arm_margins_not_prespecified",
            "Record where and when the arm margins were fixed")
    for name in ARM_MARGINS.values():
        require(name in section["margins"], "missing_arm_margins", f"No arm margin named {name}")
        require(section["margins"][name] >= 0, "invalid_margin", f"The arm margin {name} must not be negative")
    out: dict[str, dict[str, Any]] = {}
    for stage, body in section["stages"].items():
        require(stage in DESCRIPTION_STAGES, "unknown_stage",
                f"verbalizer_arms: {stage!r} is not one of {DESCRIPTION_STAGES}")
        require(stage in bundle["stages"], "arm_without_stage",
                f"verbalizer_arms: stage {stage} has arm rows and no observations of its own")
        require(_text(body["control_artifact_rule"]), "control_artifact_rule",
                f"verbalizer_arms/{stage}: state how a control artifact is matched to the actual one")
        derangement = seeded_derangement({fid: fid for fid in families}, f"{bundle['seed']}:control_artifact:{stage}")
        mapping = derangement[0] if derangement else None
        rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in body["observations"]:
            fid, vid, arm = row["family_id"], row["variant_id"], row["arm"]
            where = f"verbalizer_arms/{stage}/{fid}/{vid}/{arm}"
            require(fid in families, "unknown_family", f"{where}: unknown family")
            require(arm in ARMS, "unknown_arm", f"{where}: arm must be one of {ARMS}")
            register = families[fid]["variants"].get(vid, {}).get("register")
            require(register in PAIRED_REGISTERS, "arm_variant",
                    f"{where}: an arm row names the family's medical or everyday variant")
            require((fid, register, arm) not in rows, "duplicate_observation", f"{where}: observed twice")
            require(set(row["fact_recovery"]) <= set(families[fid]["fact_ids"]), "unknown_fact",
                    f"{where}: fact_recovery names a fact outside the family's reference set")
            require(all(status is None or status in FACT_STATUSES for status in row["fact_recovery"].values()),
                    "fact_status", f"{where}: fact status must be one of {FACT_STATUSES} or null")
            source = row.get("control_family_id")
            if arm == "control_artifact":
                require(mapping is not None, "control_artifact_mapping",
                        f"{where}: a control artifact needs a second family; no assignment exists")
                require(source == mapping[fid], "control_artifact_mapping_not_reproducible",
                        f"{where}: control_family_id must be {mapping[fid]!r}, the family that "
                        f"seeded_derangement('<seed>:control_artifact:{stage}') assigns")
            else:
                require(source is None, "arm_variant", f"{where}: an input_only row names no control artifact")
            rows[fid, register, arm] = row
        out[stage] = {"rows": rows, "mapping": mapping}
    return out


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
    artifacts = _check_held_artifact(bundle, families)
    items = _check_controls(bundle, artifacts)
    arms = _check_verbalizer_arms(bundle, families)
    return {"families": families, "family_ids": sorted(families), "artifacts": artifacts, "items": items,
            "arms": arms, **index}


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


# ------------------------------------------------------------------------------- description controls and cues

def fit_explanation_free_rule(rule: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit one rule of the closed family on items that hold both classes. No rule reads a description.

    majority_class predicts the more frequent label (ties: positive). A category rule says yes for each cue value
    whose share among positive items is strictly above its share among negative items. A threshold rule tries
    "at_least" then "at_most" over the sorted cue values and keeps the first candidate with the highest balanced
    accuracy, so a cue that carries nothing keeps the first candidate, which says yes to every item."""
    labels = [item["label"] for item in items]
    if rule == "majority_class":
        return {"predicts": 2 * sum(labels) >= len(labels)}
    if rule in CONSTANT_RULES:
        return {}
    field, kind = CUE_RULES[rule]
    values = [item[field] for item in items]
    n_positive, n_negative = sum(labels), len(labels) - sum(labels)
    if kind == "category":
        chosen = []
        for value in sorted(set(values)):
            among_positive = sum(label and seen == value for label, seen in zip(labels, values))
            among_negative = sum(not label and seen == value for label, seen in zip(labels, values))
            if among_positive * n_negative > among_negative * n_positive:
                chosen.append(value)
        return {"field": field, "positive_values": chosen}
    best: tuple[float, str, int] | None = None
    for direction in ("at_least", "at_most"):
        for threshold in sorted(set(values)):
            score = balanced_accuracy(labels, [value >= threshold if direction == "at_least" else value <= threshold
                                               for value in values])
            if best is None or score > best[0]:
                best = (score, direction, threshold)
    return {"field": field, "direction": best[1], "threshold": best[2]}


def apply_explanation_free_rule(rule: str, parameters: dict[str, Any], item: dict[str, Any]) -> bool:
    """The rule's verdict on one item, from the item's construction alone."""
    if rule in ("always_positive", "always_negative"):
        return rule == "always_positive"
    if rule == "majority_class":
        return parameters["predicts"]
    value = item[parameters["field"]]
    if "positive_values" in parameters:
        return value in parameters["positive_values"]
    return value >= parameters["threshold"] if parameters["direction"] == "at_least" else value <= parameters["threshold"]


def _pearson(xs: list[float], ys: list[float]) -> float:
    mean_x, mean_y = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    return (math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            / math.sqrt(math.fsum((x - mean_x) ** 2 for x in xs) * math.fsum((y - mean_y) ** 2 for y in ys)))


def permutation_association(xs: list[float], ys: list[float], permutations: int, alpha: float,
                            seed_label: str) -> dict[str, Any]:
    """Pearson correlation of a cue with a score over families, with a seeded permutation p-value.

    One list of the cue values is shuffled in place `permutations` times by random.Random(seed_label). The p-value is
    (1 + number of shuffles whose |r| is at least the observed |r|) / (1 + permutations). association_detected when
    p <= alpha. Not computable with fewer than three families or when the cue or the score takes one value."""
    out: dict[str, Any] = {"state": NOT_COMPUTABLE, "reason": None, "n_families": len(xs), "statistic": "pearson_r",
                           "pearson_r": None, "p_value": None, "permutations": None, "alpha": alpha, "seed_label": None}
    reason = ("fewer_than_three_families" if len(xs) < 3 else "cue_constant" if len(set(xs)) == 1 else
              "score_constant" if len(set(ys)) == 1 else None)
    if reason:
        return {**out, "reason": reason}
    observed = _pearson(xs, ys)
    rng = random.Random(seed_label)
    shuffled = list(xs)
    count = 0
    for _ in range(permutations):
        rng.shuffle(shuffled)
        count += abs(_pearson(shuffled, ys)) >= abs(observed) - 1e-12
    p_value = (1 + count) / (1 + permutations)
    return {**out, "state": ASSOCIATED if p_value <= alpha else NOT_ASSOCIATED, "pearson_r": observed,
            "p_value": p_value, "permutations": permutations, "seed_label": seed_label}


def _association(xs: dict[str, float | None], ys: dict[str, float | None], members: list[str],
                 bundle: dict[str, Any], seed_label: str) -> dict[str, Any]:
    """Association over the member families; a cue recorded for some families only is missing, not computed."""
    recorded = [fid for fid in members if xs.get(fid) is not None]
    if not recorded:
        return {"state": NOT_EXPOSED}
    if len(recorded) < len(members):
        return {"state": PARTLY_RECORDED, "n_families": len(members), "n_families_recorded": len(recorded)}
    plan = bundle.get("description_controls")
    if plan is None:
        return {"state": NOT_COMPUTABLE, "reason": "no_description_controls_plan"}
    paired = [fid for fid in members if ys.get(fid) is not None]
    return permutation_association([float(xs[fid]) for fid in paired], [float(ys[fid]) for fid in paired],
                                   plan["cue_association"]["permutations"], plan["cue_association"]["alpha"], seed_label)


def _mean(values: list[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _family_means(per_artifact: dict[str, float | None], included: dict[str, list[str]],
                  members: list[str]) -> dict[str, float | None]:
    """Per family: the mean over its included artifacts, or None when any of them has no value."""
    out: dict[str, float | None] = {}
    for fid in members:
        values = [per_artifact.get(aid) for aid in included[fid]]
        out[fid] = None if None in values else _mean(values)
    return out


def _stage_controls(stage: str, index: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Scores of every description condition and every explanation-free rule on each artifact's own items."""
    plan = bundle.get("description_controls")
    artifacts = {aid: body for aid, body in sorted(index["artifacts"].items()) if body["stage"] == stage}
    items = {aid: index["items"].get(aid, []) for aid in artifacts}
    if plan is None or not any(items.values()):
        return {"status": CONTROL_NOT_RUN,
                "reason": "no_description_controls_plan" if plan is None else "no_evaluation_items"}
    stage_items = [item for rows in items.values() for item in rows]
    cues: dict[str, Any] = {}
    for rule, (field, kind) in CUE_RULES.items():
        recorded = sum(item.get(field) is not None for item in stage_items)
        cues[rule] = {"bundle_field": f"evaluation_items[].{field}", "kind": kind, "n_items": len(stage_items),
                      "n_items_recorded": recorded,
                      "state": EXPOSED if recorded == len(stage_items) else PARTLY_RECORDED if recorded else NOT_EXPOSED}
    split = {aid: index["families"][body["family_id"]]["split"] for aid, body in artifacts.items()}
    discovery = [item for aid, rows in items.items() if split[aid] == "discovery" for item in rows]
    candidates = [rule for rule in EXPLANATION_FREE_RULES if rule in CONSTANT_RULES or cues[rule]["state"] == EXPOSED]
    both_classes = any(item["label"] for item in discovery) and not all(item["label"] for item in discovery)
    parameters = {rule: fit_explanation_free_rule(rule, discovery) for rule in candidates} if both_classes else {}
    mapping = plan["shuffle"]["mapping"].get(stage)
    per_artifact: dict[str, dict[str, Any]] = {}
    for aid, rows in items.items():
        scores: dict[str, float | None] = {}
        missing: dict[str, str] = {}
        for condition in VERDICT_CONDITIONS:
            scores[condition], reason = _condition_score(rows, condition)
            if condition.startswith("shuffled") and mapping is None:
                scores[condition], reason = None, "no_shuffle_mapping"
            if reason:
                missing[condition] = reason
        labels = [row["label"] for row in rows]
        per_artifact[aid] = {
            "artifact_id": aid, "family_id": artifacts[aid]["family_id"], "split": split[aid], "n_items": len(rows),
            "n_positive_items": sum(labels), "scores": scores, "missing": missing,
            "rule_scores": {rule: balanced_accuracy(labels, [apply_explanation_free_rule(rule, body, row)
                                                             for row in rows]) for rule, body in parameters.items()}}
    discovery_scores: dict[str, float | None] = {}
    for rule in parameters:
        by_family: dict[str, list[float]] = {}
        for aid, body in per_artifact.items():
            if split[aid] == "discovery" and body["rule_scores"][rule] is not None:
                by_family.setdefault(body["family_id"], []).append(body["rule_scores"][rule])
        discovery_scores[rule] = _mean([_mean(values) for values in by_family.values()])
    ranked = [rule for rule in parameters if discovery_scores[rule] is not None]
    selected = max(ranked, key=lambda rule: discovery_scores[rule]) if ranked else None
    seed = plan["shuffle"]["seed"]
    derangement = (seeded_derangement({aid: body["family_id"] for aid, body in artifacts.items()},
                                      f"{seed}:shuffle:{stage}") if mapping is not None else None)
    return {
        "status": "evaluated", "score_metric": SCORE_METRIC, "margins": plan["margins"],
        "fixed_before_data": plan["fixed_before_data"],
        "same_items": "every condition and every rule is scored on the artifact's own evaluation items",
        "shuffle": ({"status": "reproduced", "seed": seed, "seed_label": f"{seed}:shuffle:{stage}",
                     "attempts": derangement[1], "mapping": mapping,
                     "rule": "sorted artifact ids; shuffled copies drawn until no artifact is paired with an artifact "
                             "of its own family"} if mapping is not None else
                    {"status": CONTROL_NOT_RUN, "reason": "no_shuffle_mapping", "seed": seed}),
        "irrelevant_description": plan["irrelevant_description"],
        "explanation_free": {
            "rule_family": list(EXPLANATION_FREE_RULES), "candidate_rules": candidates,
            "fitted_on": "pooled discovery items of this stage", "selected_on_split": "discovery",
            "selection_status": ("selected" if selected else "no_discovery_items_with_both_classes"),
            "selection_rule": "highest mean balanced accuracy over discovery families; ties go to the earliest rule "
                              "in the closed list; frozen before any other split is scored",
            "parameters": parameters, "discovery_scores": discovery_scores, "selected_rule": selected},
        "item_cues": cues, "per_artifact": list(per_artifact.values()), "_per_artifact": per_artifact,
        "_items": items}


def _control_state(stage: str, name: str, members: list[str], included: dict[str, list[str]],
                  controls: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """The control state of one description stage on one analysis set; see CONTROL_RULE."""
    if controls["status"] == CONTROL_NOT_RUN:
        return {"state": CONTROL_NOT_RUN, "reason": controls["reason"]}
    plan, margins, art = bundle["analysis_plan"], controls["margins"], controls["_per_artifact"]
    selected = controls["explanation_free"]["selected_rule"]

    def control_score(aid: str, control: str, register: str) -> float | None:
        if control == "explanation_free":
            return art[aid]["rule_scores"].get(selected) if selected else None
        return art[aid]["scores"]["irrelevant" if control == "irrelevant" else f"shuffled_{register}"]

    comparisons: dict[str, dict[str, Any]] = {control: {} for control in CONTROLS}
    not_run, incomplete = [], []
    for control in CONTROLS:
        present, complete = False, True
        for register in PAIRED_REGISTERS:
            differences: dict[str, float | None] = {}
            reasons: dict[str, str] = {}
            for fid in members:
                values = []
                for aid in included[fid]:
                    matched, other = art[aid]["scores"][register], control_score(aid, control, register)
                    present = present or other is not None
                    if matched is None or other is None:
                        reasons.setdefault(fid, f"missing_matched_item_score:{register}" if matched is None else
                                           f"missing_control_score:{control}")
                    else:
                        values.append(matched - other)
                differences[fid] = None if fid in reasons else _mean(values)
            complete = complete and not reasons
            label = f"{bundle['seed']}:held_artifact_{stage}:{CONTROL_MARGINS[control]}:{register}:{name}"
            summary = summarize_paired(differences, reasons, members, margin=None, plan=plan, seed_label=label)
            margin, interval = margins[CONTROL_MARGINS[control]], summary["interval"]
            comparisons[control][register] = {
                **{key: summary[key] for key in ("n_families", "n_included", "excluded", "mean_difference", "interval",
                                                 "interval_status", "seed_label")},
                "control_margin": margin,
                "outcome": (NOT_SHOWN if interval is None else BEATEN if interval[0] > margin else
                            NOT_BEATEN if interval[1] <= margin else NOT_SHOWN)}
        if not present:
            not_run.append(control)
        elif not complete:
            incomplete.append(control)
    partly = [rule for rule, body in controls["item_cues"].items() if body["state"] == PARTLY_RECORDED]
    outcomes = {control: [body["outcome"] for body in comparisons[control].values()] for control in CONTROLS}
    reading = outcomes["shuffled"] + outcomes["irrelevant"]
    state = (CONTROL_NOT_RUN if not_run else CONTROL_INCOMPLETE if incomplete or partly else
             NO_ADVANTAGE_OVER_DESCRIPTION if NOT_BEATEN in reading else
             BASELINE_NOT_BEATEN if NOT_BEATEN in outcomes["explanation_free"] else
             READING_NOT_SHOWN if NOT_SHOWN in reading else
             BASELINE_NOT_SHOWN if NOT_SHOWN in outcomes["explanation_free"] else CONTROLS_PASSED)

    def set_mean(per_artifact: dict[str, float | None]) -> float | None:
        values = list(_family_means(per_artifact, included, members).values())
        return None if not values or None in values else _mean(values)

    matched = {register: set_mean({aid: art[aid]["scores"][register] for aid in art}) for register in PAIRED_REGISTERS}
    rules = {rule: set_mean({aid: art[aid]["rule_scores"][rule] for aid in art})
             for rule in controls["explanation_free"]["parameters"]}
    scored_rules = [rule for rule in rules if rules[rule] is not None]
    top = max(scored_rules, key=lambda rule: rules[rule]) if scored_rules else None
    baseline_margin = margins[CONTROL_MARGINS["explanation_free"]]
    window = {aid: (_mean([row["window_token_count"] for row in rows])
                    if rows and all(row.get("window_token_count") is not None for row in rows) else None)
              for aid, rows in controls["_items"].items()}
    return {
        "state": state, "controls_not_run": not_run, "controls_incomplete": incomplete,
        "item_cues_partly_recorded": partly,
        "item_cues_not_exposed": [rule for rule, body in controls["item_cues"].items() if body["state"] == NOT_EXPOSED],
        "failed_comparisons": [f"{CONTROL_MARGINS[control]}:{register}" for control in CONTROLS
                               for register, body in comparisons[control].items() if body["outcome"] != BEATEN],
        "comparisons": comparisons,
        "mean_scores": {
            "note": "mean over families of the per-artifact balanced accuracy; the matched score is reported beside "
                    "every control and every rule",
            "matched": matched,
            "shuffled": {register: set_mean({aid: art[aid]["scores"][f"shuffled_{register}"] for aid in art})
                         for register in PAIRED_REGISTERS},
            "irrelevant": set_mean({aid: art[aid]["scores"]["irrelevant"] for aid in art}),
            "explanation_free_baseline": {"rule": selected, "score": rules.get(selected)},
            "explanation_free_rules": rules},
        "rule_family_maximum": {
            "rule": top, "score": rules.get(top),
            "selection": "highest mean on these items, chosen after the fact; reported, not used by the verdict rule",
            "within_control_margin_of_matched": {
                register: (None if top is None or matched[register] is None else
                           matched[register] - rules[top] <= baseline_margin) for register in PAIRED_REGISTERS}},
        "window_length_association": {
            register: _association(_family_means(window, included, members),
                                   _family_means({aid: art[aid]["scores"][register] for aid in art}, included, members),
                                   members, bundle, f"{bundle['seed']}:cue:{stage}:window_length:{register}:{name}")
            for register in PAIRED_REGISTERS}}


def _description_cues(stage: str, name: str, members: list[str], included: dict[str, list[str]],
                      pairs: dict[str, dict[str, Any]], differences: dict[str, float | None],
                      bundle: dict[str, Any]) -> dict[str, Any]:
    """Length, formatting and presentation order of the two descriptions, beside one medical-minus-everyday result."""
    artifact_ids = [aid for fid in members for aid in included[fid]]

    def exposure(field: str) -> tuple[str, int]:
        recorded = sum(pairs[aid][field] is not None for aid in artifact_ids)
        return (EXPOSED if artifact_ids and recorded == len(artifact_ids) else
                PARTLY_RECORDED if recorded else NOT_EXPOSED), recorded

    def association(field: str, cue: str) -> dict[str, Any]:
        xs = _family_means({aid: (None if pairs[aid][field] is None else float(pairs[aid][field]))
                            for aid in artifact_ids}, included, members)
        return _association(xs, differences, members, bundle, f"{bundle['seed']}:cue:{stage}:{cue}:{name}")

    length_state, length_recorded = exposure("token_count_difference")
    format_state, format_recorded = exposure("formatting_differs")
    order_state, order_recorded = exposure("medical_presented_first")
    by_length: dict[str, Any] = {}
    for key, wanted in (("length_matched", False), ("length_differs", True)):
        chosen = [pairs[aid]["difference"] for aid in artifact_ids if pairs[aid]["length_confounded"] is wanted]
        by_length[key] = {"n_artifacts": len(chosen), "mean_score_difference": _mean(chosen)}
    return {
        "description_length": {
            "bundle_field": "held_artifact[].description_token_count", "state": length_state,
            "n_pairs": len(artifact_ids), "n_pairs_recorded": length_recorded,
            "length_confounded_artifact_ids": [aid for aid in artifact_ids if pairs[aid]["length_confounded"]],
            "mean_token_count_difference": _mean([pairs[aid]["token_count_difference"] for aid in artifact_ids
                                                  if pairs[aid]["token_count_difference"] is not None]),
            "score_difference_by_length_match": by_length,
            "association_with_score_difference": association("token_count_difference", "description_length")},
        "description_formatting": {
            "bundle_field": "held_artifact[].formatting_class", "state": format_state,
            "n_pairs": len(artifact_ids), "n_pairs_recorded": format_recorded,
            "formatting_differs_artifact_ids": [aid for aid in artifact_ids if pairs[aid]["formatting_differs"]]},
        "description_order": {
            "bundle_field": "held_artifact[].presentation_order", "state": order_state,
            "n_pairs": len(artifact_ids), "n_pairs_recorded": order_recorded,
            "n_pairs_medical_first": sum(bool(pairs[aid]["medical_presented_first"]) for aid in artifact_ids),
            "association_with_score_difference": association("medical_presented_first", "description_order")}}


def _verbalizer_arms(stage: str, index: dict[str, Any], sets: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """The arm state of one description stage per analysis set; see ARM_RULE."""
    if stage not in index["arms"]:
        return {"status": ARMS_NOT_RUN,
                "reason": "the bundle carries no input_only or control_artifact rows for this stage",
                "state_by_analysis_set": dict.fromkeys(sets, ARMS_NOT_RUN)}
    section, plan = bundle["verbalizer_arms"], bundle["analysis_plan"]
    stage_rows, arm_rows = index["rows"][stage], index["arms"][stage]["rows"]
    rate: dict[tuple[str, str, str], float | None] = {}
    for fid in index["family_ids"]:
        family = index["families"][fid]
        for register in PAIRED_REGISTERS:
            rate[fid, register, "artifact"] = fact_recovery_rate(stage_rows.get((fid, family[register])),
                                                                 family["fact_ids"], plan["partial_credit"])
            for arm in ARMS:
                rate[fid, register, arm] = fact_recovery_rate(arm_rows.get((fid, register, arm)),
                                                              family["fact_ids"], plan["partial_credit"])
    keep = ("n_families", "n_included", "excluded", "mean_difference", "interval", "interval_status", "seed_label")
    seed = f"{bundle['seed']}:verbalizer_arms_{stage}"

    def register_difference(arm: str, fid: str) -> float | None:
        medical, everyday = rate[fid, "medical", arm], rate[fid, "everyday", arm]
        return None if medical is None or everyday is None else medical - everyday

    by_set: dict[str, Any] = {}
    for name, body in sets.items():
        members = body["family_ids"]
        comparisons: dict[str, dict[str, Any]] = {arm: {} for arm in ARMS}
        not_run, incomplete = [], []
        for arm in ARMS:
            present = any(rate[fid, register, arm] is not None for fid in members for register in PAIRED_REGISTERS)
            complete = True
            for register in PAIRED_REGISTERS:
                differences: dict[str, float | None] = {}
                reasons: dict[str, str] = {}
                for fid in members:
                    actual, other = rate[fid, register, "artifact"], rate[fid, register, arm]
                    if actual is None or other is None:
                        reasons[fid] = (f"missing_artifact_arm:{register}" if actual is None else
                                        f"missing_arm:{arm}:{register}")
                    differences[fid] = None if fid in reasons else actual - other
                complete = complete and not reasons
                summary = summarize_paired(differences, reasons, members, margin=None, plan=plan,
                                           seed_label=f"{seed}:{ARM_MARGINS[arm]}:{register}:{name}")
                margin, interval = section["margins"][ARM_MARGINS[arm]], summary["interval"]
                comparisons[arm][register] = {
                    **{key: summary[key] for key in keep}, "arm_margin": margin,
                    "outcome": (NOT_SHOWN if interval is None else BEATEN if interval[0] > margin else
                                NOT_BEATEN if interval[1] <= margin else NOT_SHOWN)}
            if not present:
                not_run.append(arm)
            elif not complete:
                incomplete.append(arm)
        outcomes = {arm: [entry["outcome"] for entry in comparisons[arm].values()] for arm in ARMS}
        state = (ARMS_NOT_RUN if not_run else ARMS_INCOMPLETE if incomplete else
                 NO_ADVANTAGE_OVER_CONTROL if NOT_BEATEN in outcomes["control_artifact"] else
                 NO_ADVANTAGE_OVER_WORDING if NOT_BEATEN in outcomes["input_only"] else
                 SPECIFICITY_NOT_SHOWN if NOT_SHOWN in outcomes["control_artifact"] else
                 CONTRIBUTION_NOT_SHOWN if NOT_SHOWN in outcomes["input_only"] else ARTIFACT_CONTRIBUTES)
        # What each arm recovered, so that a state is never read without it: an advantage cannot be shown
        # where there is nothing to have an advantage in.
        mean_rates = {arm: {register: _mean([rate[fid, register, arm] for fid in members
                                             if rate[fid, register, arm] is not None])
                            for register in PAIRED_REGISTERS} for arm in ("artifact", *ARMS)}
        recovered = [value for per_register in mean_rates.values() for value in per_register.values()]
        nothing_recovered = bool(recovered) and None not in recovered and all(value == 0 for value in recovered)
        by_arm = {}
        for arm in ("artifact", *ARMS):
            summary = summarize_paired({fid: register_difference(arm, fid) for fid in members}, {}, members,
                                       margin=None, plan=plan, seed_label=f"{seed}:register_difference:{arm}:{name}")
            by_arm[arm] = {key: summary[key] for key in keep}
        beyond = {}
        for fid in members:
            with_artifact, wording = register_difference("artifact", fid), register_difference("input_only", fid)
            beyond[fid] = None if with_artifact is None or wording is None else with_artifact - wording
        summary = summarize_paired(beyond, {}, members, margin=None, plan=plan,
                                   seed_label=f"{seed}:register_difference_beyond_input_only:{name}")
        by_set[name] = {
            "state": state,
            "state_meaning": ARM_STATE_MEANING[state] + ("; " + NOTHING_RECOVERED_NOTE if nothing_recovered else ""),
            "arms_not_run": not_run, "arms_incomplete": incomplete,
            "mean_rates": {"note": "mean fact-recovery rate per arm and register, over the families of the set that "
                                   "have one; null where none has",
                           **mean_rates},
            "no_fact_recovered_in_any_arm": nothing_recovered,
            "failed_comparisons": [f"{ARM_MARGINS[arm]}:{register}" for arm in ARMS
                                   for register, entry in comparisons[arm].items() if entry["outcome"] != BEATEN],
            "comparisons": comparisons,
            "medical_minus_everyday_by_arm": {
                "note": "the paired register difference in fact-recovery rate under each arm; a difference that is "
                        "equally large with the wording alone is not evidence about the representation",
                **by_arm},
            "register_difference_beyond_input_only": {
                "note": "per family, the artifact arm's medical-minus-everyday difference minus the input_only "
                        "arm's; reported with its interval and given no verdict",
                **{key: summary[key] for key in keep}}}
    return {"status": "scored", "margins": section["margins"],
            "control_artifact_rule": section["stages"][stage]["control_artifact_rule"],
            "control_artifact_mapping": index["arms"][stage]["mapping"],
            "analysis_sets": by_set,
            "state_by_analysis_set": {name: body["state"] for name, body in by_set.items()}}


def _held_artifact(index: dict[str, Any], sets: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"manipulation": "the artifact is held fixed; only the register of a meaning-equivalent "
                                           "description varies, so a score difference is a presentation or scoring "
                                           "effect, not a representation change",
                           "control_rule": CONTROL_RULE}
    for stage in DESCRIPTION_STAGES:
        artifacts = {aid: body for aid, body in sorted(index["artifacts"].items()) if body["stage"] == stage}
        if not artifacts:
            out[stage] = {"status": "not_supplied"}
            continue
        per_artifact, by_family, reasons = [], {}, {}
        pairs: dict[str, dict[str, Any]] = {}
        included: dict[str, list[str]] = {}
        for aid, body in artifacts.items():
            records, fid = body["records"], body["family_id"]
            absent = [r for r in PAIRED_REGISTERS if r not in records]
            unscored = [r for r in PAIRED_REGISTERS if r in records and records[r]["score"] is None]
            reason = (f"unpaired_description:{absent[0]}" if absent else
                      f"missing_score:{unscored[0]}" if unscored else None)
            difference = None if reason else records["medical"]["score"] - records["everyday"]["score"]
            cue = {register: {field: records.get(register, {}).get(field) for field in DESCRIPTION_CUES.values()}
                   for register in PAIRED_REGISTERS}
            tokens = [cue[register]["description_token_count"] for register in PAIRED_REGISTERS]
            classes = [cue[register]["formatting_class"] for register in PAIRED_REGISTERS]
            order = cue["medical"]["presentation_order"] or (3 - cue["everyday"]["presentation_order"]
                                                             if cue["everyday"]["presentation_order"] else None)
            pairs[aid] = {
                "artifact_id": aid, "family_id": fid,
                "medical_description_score": records.get("medical", {}).get("score"),
                "everyday_description_score": records.get("everyday", {}).get("score"),
                "difference": difference, "excluded_reason": reason,
                "medical_description_token_count": tokens[0], "everyday_description_token_count": tokens[1],
                "token_count_difference": None if None in tokens else tokens[0] - tokens[1],
                "length_confounded": None if None in tokens else tokens[0] != tokens[1],
                "medical_formatting_class": classes[0], "everyday_formatting_class": classes[1],
                "formatting_differs": None if None in classes else classes[0] != classes[1],
                "medical_presented_first": None if order is None else order == 1}
            per_artifact.append(pairs[aid])
            if reason:
                reasons.setdefault(fid, reason)
            else:
                by_family.setdefault(fid, []).append(difference)
                included.setdefault(fid, []).append(aid)
        differences = {fid: math.fsum(values) / len(values) for fid, values in by_family.items()}
        with_records = {body["family_id"] for body in artifacts.values()}
        margin = bundle["equivalence_margins"]["endpoints"]["held_artifact_score_difference"]
        own_sets = {name: {"family_ids": [f for f in body["family_ids"] if f in with_records]}
                    for name, body in sets.items()}
        controls = _stage_controls(stage, index, bundle)
        summaries = _by_set(differences, reasons, own_sets, plan=bundle["analysis_plan"], margin=margin,
                            label=f"{bundle['seed']}:held_artifact_{stage}:held_artifact_score_difference")
        states_by_set = {}
        for name, summary in summaries.items():
            members = [fid for fid in own_sets[name]["family_ids"] if fid in included]
            states_by_set[name] = _control_state(stage, name, members, included, controls, bundle)
            summary["control_state"] = states_by_set[name]["state"]
            summary["verdict_issued"] = states_by_set[name]["state"] == CONTROLS_PASSED
            if not summary["verdict_issued"]:
                summary["verdict"] = states_by_set[name]["state"]
            summary["description_cues"] = _description_cues(stage, name, members, included, pairs, differences, bundle)
        out[stage] = {
            "status": "scored", "n_artifacts": len(artifacts),
            "n_artifacts_included": sum(a["difference"] is not None for a in per_artifact),
            "families_without_records": [f for f in index["family_ids"] if f not in with_records],
            "per_artifact": per_artifact,
            "per_family": [{"family_id": fid, "difference": differences.get(fid)} for fid in sorted(with_records)],
            "analysis_sets": summaries,
            "description_controls": {**{key: value for key, value in controls.items() if not key.startswith("_")},
                                     "analysis_sets": states_by_set}}
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
    control_states = {stage: ({name: body["control_state"] for name, body in held[stage]["analysis_sets"].items()}
                           if held[stage]["status"] == "scored" else dict.fromkeys(sets, CONTROL_NOT_RUN))
                   for stage in DESCRIPTION_STAGES}
    arm_states: dict[str, dict[str, str]] = {}
    for stage in DESCRIPTION_STAGES:
        if stages[stage]["status"] == "scored":
            arms = _verbalizer_arms(stage, index, sets, bundle)
            arm_states[stage] = arms["state_by_analysis_set"]
            stages[stage]["verbalizer_arms"] = {
                "applies_to": "a stage whose instrument reads an activation artifact (a verbalizer or a scorer)",
                **arms,
                "rule": "this stage's fact recovery is described as coming from the artifact only where the state "
                        "is artifact_contributes; any other state says the advantage was not demonstrated and "
                        "establishes no cause; the fact-recovery verdict above is computed as before"}
    for stage in DESCRIPTION_STAGES:
        if stages[stage]["status"] == "scored":
            stages[stage]["description_controls"] = {
                "applies_to": "the held-artifact manipulation of this stage",
                "state_by_analysis_set": control_states[stage],
                "rule": "this stage is described as showing register equivalence only where the state is "
                        "controls_passed; the fact-recovery verdict above is computed as before and is not that "
                        "statement"}
    primary_results = {
        "analysis_set": primary,
        "fact_recovery_rate_difference": {
            stage: ({**{key: body["fact_recovery"]["analysis_sets"][primary][key] for key in keep},
                     **({"description_control_state": control_states[stage][primary],
                         "artifact_arm_state": arm_states[stage][primary]}
                        if stage in DESCRIPTION_STAGES else {})}
                    if body["status"] == "scored" else {"status": "not_supplied"})
            for stage, body in stages.items()},
        "held_artifact_score_difference": {
            stage: ({key: held[stage]["analysis_sets"][primary][key] for key in (*keep, "control_state")}
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
        "identities": bundle["identities"], "verdict_rule": VERDICT_RULE, "control_rule": CONTROL_RULE,
        "arm_rule": ARM_RULE,
        "control_randomness": {
            "generator": "random.Random",
            "shuffle_seed_rule": "'<description_controls.shuffle.seed>:shuffle:<stage>'",
            "control_interval_seed_rule": "'<seed>:held_artifact_<stage>:<control margin name>:<register>:"
                                          "<analysis set>'",
            "cue_association_seed_rule": "'<seed>:cue:<stage>:<cue>[:<register>]:<analysis set>'",
            "description_controls": bundle.get("description_controls")},
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


def _distribution(values: list[float], quantile: float) -> dict[str, Any]:
    """Median, nearest-rank quantile and maximum of one value per family; nulls when no family has a value."""
    ordered = sorted(values)
    if not ordered:
        return {"n_families": 0, "median": None, "quantile": None, "maximum": None}
    return {"n_families": len(ordered), "median": statistics.median(ordered),
            "quantile": ordered[max(1, math.ceil(quantile * len(ordered))) - 1], "maximum": ordered[-1]}


def _calibrate(bundle: dict[str, Any], quantile: float, schema: dict[str, Any] | None) -> dict[str, Any]:
    require(isinstance(quantile, float) and 0 < quantile < 1, "calibration_quantile",
            "The quantile is a number strictly between 0 and 1, fixed in the protocol before calibration data")
    index = _validate(bundle, schema)
    families, plan = index["families"], bundle["analysis_plan"]
    outside = sorted(fid for fid in families if families[fid]["split"] != "discovery")
    require(not outside, "calibration_reads_held_out",
            f"A calibration bundle holds discovery families only; {len(outside)} of {len(families)} families are in "
            "another split, and a threshold may not be informed by them")
    stages: dict[str, Any] = {}
    for stage in STAGES:
        if stage not in bundle["stages"]:
            continue
        rows = index["rows"][stage]
        rate_values, representation_values, per_family = [], [], []
        for fid in index["family_ids"]:
            family = families[fid]
            rates, representations = [], []
            for vid in family["paraphrases"]:
                pair = [rows.get((fid, family[family["variants"][vid]["base_register"]])), rows.get((fid, vid))]
                pair_rates = [fact_recovery_rate(row, family["fact_ids"], plan["partial_credit"]) for row in pair]
                if None not in pair_rates:
                    rates.append(abs(pair_rates[1] - pair_rates[0]))
                measured = [row["representation_value"] if row else None for row in pair]
                if None not in measured:
                    representations.append(abs(measured[1] - measured[0]))
            entry = {"family_id": fid, "n_paraphrases": len(family["paraphrases"]),
                     "fact_recovery_rate_abs_difference": _mean(rates),
                     "representation_value_abs_difference": _mean(representations)}
            per_family.append(entry)
            if rates:
                rate_values.append(entry["fact_recovery_rate_abs_difference"])
            if representations:
                representation_values.append(entry["representation_value_abs_difference"])
        stages[stage] = {
            "within_register_paraphrase": {
                "unit": "one value per family: the mean absolute difference between a paraphrase and its base variant",
                "fact_recovery_rate_abs_difference": _distribution(rate_values, quantile),
                "representation_value_abs_difference": _distribution(representation_values, quantile),
                "per_family": per_family},
            "changed_fact_sensitivity": _changed_fact_sensitivity(stage, index, plan)["by_base_register"]}
    return {
        "schema_version": CALIBRATION_SCHEMA, "status": "calibrated", "benchmark_status": STATUS_LINE,
        "execution_status": "synthetic", "synthetic": True, "evidence_label": SYNTHETIC_LABEL,
        "bundle_sha256": digest(bundle), "quantile": quantile, "quantile_method": "nearest rank over families",
        "families": index["family_ids"], "split": "discovery",
        "use": "a study protocol may name representation_value_abs_difference.quantile of a stage as that stage's "
               "representation-change threshold, and states each margin with its reason beside the within-register "
               "variation recorded here; this record computes no margin and no verdict",
        "stages": stages}


def calibration_record(bundle: Any, quantile: float, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Within-register variation of a discovery-only bundle; refuses a bundle that holds any other split."""
    try:
        return _calibrate(bundle, quantile, schema)
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
    parser.add_argument("--calibrate", action="store_true",
                        help="write the calibration record of a discovery-only bundle in place of the scored report")
    parser.add_argument("--quantile", type=float,
                        help="with --calibrate: the quantile of the within-register differences, fixed in the "
                             "protocol before calibration data; there is no default")
    args = parser.parse_args(argv)
    try:
        if args.calibrate:
            require(args.quantile is not None, "calibration_quantile", "--calibrate needs --quantile; none is assumed")
            result = calibration_record(load_bundle(args.bundle), args.quantile)
        else:
            require(args.quantile is None, "calibration_quantile", "--quantile applies to --calibrate only")
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
