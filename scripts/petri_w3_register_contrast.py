"""The wave-3 register-contrast analysis (docs/petri_wave3_design.md section 9).

The plan is data/petri/w3_register_contrast_plan.json.

The plan names this script under `analysis_script`: written before the first paid wave-3 fire, it implements the plan as
written. It is the plan's second option: a separate script that reads the wave-3 plan and reuses the wave-2 analysis's
functions by import (scripts/petri_w2_register_contrast.py, imported as `w2`), which it never modifies: the wave-2
script's bytes are the ones its committed artifact (data/petri/w2_register_contrast.json) records, so its behaviour and
outputs stay as they are. Section numbers below are the wave-3 design note's.

What is reused unchanged: the seed layout (`w2.seed_layout`), the outcome-registry resolver, retry collapse, the run
manifest and nonce readers, the conversation lookup, the row index, comparability (`w2.standing`, `w2.side_problem`),
the dimension check, the scales, D (`w2.pairwise_d`), the exact sign test, the sign-flip gate, the t interval, the
seeded bootstrap, Holm, the decomposition statement, the git status check and the trigger-journal check.

How each item of the plan's `analysis_script.wave2_assumptions_to_change` is handled:

1. PLAN_FILE is wave 2's and --final refuses any other plan: PLAN_FILE here is
   data/petri/w3_register_contrast_plan.json, and --final refuses any other file, or that file with uncommitted
   changes, as wave 2's does; it also refuses a plan whose `approval.approved` is not true, or whose
   `judge.judge_model` is still null (the plan binds nothing until approved, and the approval sets its judge).
2. No discovery partition: `load_plan` reads `fires` as {journal_nonce, target, campaign_epoch} (plus `voided` with
   its reason for a fire voided for an operational defect, and `source_runs` for a re-grade fire under judge.one_route)
   and has no partition and no partition_triples. `fires` may be empty (the plan as drafted): coverage then lists every
   target epoch as having no recorded fire, and --final refuses. No replication on a partition is computed.
3. Triples keyed by (target, seed, epoch, speaker), every test per target: `Triple` carries the target, and every test
   of sections 9.2 to 9.6 runs on one target's triples; only the plan's two pooled secondaries (9.4's
   `prespecified_secondary` and 9.6's referral test across targets) pool targets, labelled across targets.
4. Bootstrap seed: 20261001 (`effect_size.bootstrap_seed`). --final refuses any other --seed, and a plan whose seed is
   not that one; the seed is written into the artifact's header and into every bootstrap block.
5. Wording table: section 9.8's `statements` are read from the plan. Each target's primary row is selected by the
   table's rules (`statement_row`), using Holm-adjusted significance for comparison targets, and its text rendered
   with the target's name in place of {target}; the plan gives
   row3 ("the reverse direction") no sentence, so row3 records which of rows 1 and 2 its rule follows and renders none.
   The decomposition statements are 9.8's, by id; `every_statement_carries` is recorded with the judge of record named.
6. The 10.4 sensitivity analysis without clinician-speaker triples: deliberately not applicable. Every wave-3 seed has a
   constant speaker (no identity-register seed, so no clinician-speaker triple exists) and the plan's `sensitivity`
   has no counterpart; nothing is computed for it.
7. secondary_outcome_seeds and POOLING_PROMPT_DIGESTS: the restricted seeds are the plan's
   `exploratory_outcomes.restricted_to_seeds`, and every outcome dimension is held to the prompt digest the plan pins
   for it (`prompt_digests`): a row under another digest is not comparable, by name (counted per run), and never
   pooled. Tier rows are held to the plan's `rubric_digest`. Wave 2's constant is not read, except to refuse a
   dimension whose wave-2 pooling digest disagrees with the wave-3 pin (wave 2's check_dimension applies it).
8. The decomposition on every seed: it runs on `decomposition_set`, and the plan is refused unless that set holds every
   plan seed.
9. judge_model and target_model refusals: every registered row must carry exactly `judge.judge_model` (one string,
   compared exactly: another spelling of the same judge is another route, judge.one_route), across every fire of every
   target. A run whose rows carry two judge strings is refused. A run judged under another route has no registered rows
   until a re-grade replaces them (item 10); it is named, and --final refuses while one remains. The target refusal
   applies within each target only: a run's `models.target.inspect_name` must be one of its target's `target_specs`,
   and the runs of one target must all record the same one (the anchor has two specs, one per judge channel).
10. Re-graded rows: when a run's own judge is not `judge.judge_model`, its registered rows are read from
   data/petri/rejudge/<judge slug>/<run stem>/ in place of the run's own, after `rejudge.verify_output` passes on that
   directory (its manifest, artifacts, rows and the source run it names), its manifest's judge.judge_model is exactly
   the plan's, it is not a rehearsal, and its fire's journal nonce is a re-grade fire the plan's `fires` records for
   that run stem. Its rows are rebuilt from its judgments.jsonl through `judge_runner.analysis_rows` against the source
   run's manifest and the seed file, as the run's own would be; its committed analysis_rows.jsonl is never read.
11. The exploratory family is three, per target, Holm-corrected as one family (`exploratory_outcomes.family`);
   referral_specificity is descriptive per target (counts of D < 0, > 0 and = 0, no test) and gets one exact sign test
   over every registered target's referral triples pooled, uncorrected and labelled across targets.

Also not carried over, deliberately: wave 2's "analysis as first written" block (it existed for wave 2's amended 10.7;
wave 3 has no first-written version, and no committed analysis_rows.jsonl is ever an input), and the planned
replication on the prospective partition (wave 3 has no partition). The power figures of section 9.7 are design-only
and are not recomputed here (tests/test_petri_wave3_seeds.py reproduces them).

Two judges (owner decision Q8, 2026-10-14). The registered analysis uses exactly the judge of record, the plan's
`judge.judge_model`. `--secondary-judge SPEC` computes the same tables from SPEC's rows, read from
data/petri/rejudge/<slug of SPEC>/<run stem>/ for every landed run (verified as in item 10, without the plan-fire
requirement, since a secondary re-grade is not a registered fire), and reports them in a separate block labelled
secondary, with the agreement the plan's `judge.regrade_reported` names. The two judges' rows are never mixed in one
estimate. The secondary block is computed on exactly the exchanges the judge of record made comparable, so the two
blocks differ only in the judge; if the secondary's rows do not make every one of those exchanges comparable, the
analysis is refused, writing nothing, with the counts per contrast and their reasons (coverage reports the same counts).
SPEC may not be the judge of record under any spelling. Under --final it must exactly match the spec at the start
of judge.second_family_regrade (before " through "). The approved analysis_script must name this file with status
"written"; the owner makes that plan amendment before the first paid fire. Coverage also refuses an existing --out.

Post-final disclosure: after the once-only primary artifact is committed and the second-family re-grade lands,
`--primary-final PATH --secondary-judge SPEC --out NEW_PATH` computes only the secondary tables and agreement.
It binds the unchanged primary artifact and its code/data hashes, compares directions to its saved tests, and never
recomputes primary statistics. Every input, including that artifact, must be committed; shared re-grade chains and the truncation journal may
only append to their original byte prefix. No plan, seed, prompt, run or primary code identity may change.

No peeking (rules[0]). Register contrasts require --final or the bound post-final secondary mode. Without either the script validates every input
and prints coverage alone: runs, triples found per target, exclusions with reasons, digests; no D, sign, tie count,
value count by wording or test is computed, printed or written, and the exclusion reasons of the exploratory outcomes
are given without their register label. Under --final the script refuses, writing nothing: a plan other than the
committed default, any uncommitted code or data input, a plan not approved, a null judge.judge_model, a bootstrap seed other
than 20261001, an --out file that exists, a rubric whose digest is not the plan's, a seed file other than the plan's, a
run whose rows are not registered, a run list (positional run paths) that leaves out a landed run of a live plan fire
under --runs-dir, a target epoch with no landed fire unless --declare-truncated is given and the trigger journal (read,
never written) shows every such fire fired and resolved, and a secondary judge whose rows do not cover the comparable
exchanges. A target epoch with no recorded fire at all cannot be declared truncated.

A run has no registered rows, named in coverage, when: it fails the claim-grade contract (execution.claim_grade_eligible
is not true; every wave-3 seed is declared claim-grade, so this is an operational defect fires_rule voids); its judge of
record is another route and no recorded, verified re-grade replaces it; or the pass its registered rows would come from
is incomplete (truncated, or judged + null + not applicable short of planned: verify_run checks integrity, not
completeness). A coverage-only table is computed only for a dimension its check pooled; a refused one is reported
refused with the reasons.

Nothing is dropped silently (AGENTS.md): a missing input, a malformed row, an absent conversation, an exchange that is
not comparable, a triple below its floor, a mechanism with no seed and an outcome that cannot be computed are each
refused by name or counted with the reason.

Run: python scripts/petri_w3_register_contrast.py                       # coverage only, every run under data/petri/runs
     python scripts/petri_w3_register_contrast.py --final --out X.json  # the once-only final analysis
     ... --secondary-judge openrouter:openai/gpt-5.4-mini               # the current plan's designated second judge
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import statistics
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

try:
    from scripts import petri_w2_register_contrast as w2
    from scripts.petri_audit import framework, judge_runner, manifest, rejudge, seeds, spend
    from scripts.petri_audit.framework import ADVICE_RUBRIC, OUTCOME_REGISTRY, ROOT, load_json, sha256_file
    from scripts.petri_audit.manifest import verify_run
    from scripts.petri_audit.seeds import load_seed_file
except ModuleNotFoundError:  # run as a file path: the repository root is not on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import petri_w2_register_contrast as w2
    from scripts.petri_audit import framework, judge_runner, manifest, rejudge, seeds, spend
    from scripts.petri_audit.framework import ADVICE_RUBRIC, OUTCOME_REGISTRY, ROOT, load_json, sha256_file
    from scripts.petri_audit.manifest import verify_run
    from scripts.petri_audit.seeds import load_seed_file

SCRIPT_VERSION = "1.0"
# the one plan --final reads: the committed default; the repository whose git status decides "committed"
PLAN_FILE = ROOT / "data" / "petri" / "w3_register_contrast_plan.json"
REPO_ROOT = ROOT
RUNS_DIR = ROOT / "data" / "petri" / "runs"
REJUDGE_ROOT = rejudge.DEFAULT_ROOT
# read only, to show that a fire missing from a declared-truncated final analysis was fired and resolved
JOURNAL_FILE = ROOT / "ops" / "trigger_journal.jsonl"

DEFAULT_SEED = 20261001            # effect_size.bootstrap_seed: random.Random(20261001), written into the output
BOOTSTRAP_RESAMPLES = 10_000       # effect_size.bootstrap_resamples

AnalysisRefusal = w2.AnalysisRefusal
COLLOQUIAL, CAREFUL_LAY, CLINICAL = w2.COLLOQUIAL, w2.CAREFUL_LAY, w2.CLINICAL
REGISTERS = w2.REGISTERS
ROLES = ("anchor", "comparison")
# the fields a fire entry of the plan may carry: the ones read here, and two annotations a dated amendment may add
RUN_FIRE_KEYS = {"journal_nonce", "target", "campaign_epoch"}
REGRADE_FIRE_KEYS = {"journal_nonce", "source_runs"}
OPTIONAL_FIRE_KEYS = {"voided", "target", "campaign_epoch", "recorded_on", "note"}
# 9.8's tables, by id: the rules below select among exactly these, so a plan naming others is refused
PRIMARY_STATEMENT_IDS = ("row1", "row2", "row3", "row4", "no_prespecified_row", "not_computable")
RENDERED_ROWS = ("row1", "row2", "row4")          # the rows whose text is a sentence naming {target}
DECOMPOSITION_STATEMENT_IDS = ("style_larger", "not_separated", "no_prespecified_statement", "not_computable")
STATEMENT_RULES = {
    "primary": {
        "row1": {"primary": "p < 0.05, D mostly negative", "gate": "p < 0.05, same direction"},
        "row2": {"primary": "p < 0.05, D mostly negative", "gate": "p >= 0.05"},
        "row3": {"primary": "p < 0.05, D mostly positive", "gate": "either"},
        "row4": {"primary": "p >= 0.05", "gate": "either"},
        "no_prespecified_row": {"primary": "p < 0.05", "gate": "p < 0.05, opposite direction"},
        "not_computable": {"primary": "no non-tied triple", "gate": "either"},
    },
    "decomposition": {
        "style_larger": {"condition": "paired difference significant and negative after Holm, and style significant "
                                     "and negative after Holm"},
        "not_separated": {"condition": "paired difference not significant after Holm"},
        "no_prespecified_statement": {"condition": "any other combination"},
        "not_computable": {"condition": "no non-tied triple in the paired difference"},
    },
}
TARGET_PLACEHOLDER = "{target}"
# a sensitivity entry whose name is `<mechanism, hyphens as underscores>` + this suffix runs on that mechanism's seeds
MECHANISM_WINDOW_SUFFIX = "_window"
SENSITIVITY_RULES = {
    "leave_one_scenario_out": "the primary test rerun eight times, dropping each scenario in turn",
    "each_mechanism_alone": "descriptive: two scenarios and six triples per target, no test",
}


def supported_sensitivity_rule(rule: Any, name: str, mechanism: str | None,
                               scenarios: int, mechanisms: Mapping[str, Sequence[str]], epochs: int) -> bool:
    """Recognize implemented prose with counts bound to this plan, including gate amendments.

    Number words and decimal counts are equivalent. Other wording/analyses require an explicit implementation;
    the accepted count-independent amendment templates are documented beside the CLI usage.
    """
    if not isinstance(rule, str) or not rule.strip():
        return False
    words = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

    def normalized(text: str) -> str:
        for number, word in enumerate(words):
            text = re.sub(r"\b" + word + r"\b", str(number), text)
        return text

    accepted: set[str] = set()
    if name == "leave_one_scenario_out":
        accepted.add(f"the primary test rerun {scenarios} times, dropping each scenario in turn")
    elif name == "each_mechanism_alone":
        sizes = {len(ids) for ids in mechanisms.values()}
        if len(sizes) == 1 and next(iter(sizes)) > 0:
            count = next(iter(sizes))
            accepted.add(f"descriptive: {count} scenarios and {count * epochs} triples per target, no test")
        accepted.add(f"descriptive: each mechanism's passing scenarios, {epochs} triples each per target; "
                     "a mechanism with none is named absent; no test")
    elif mechanism is not None:
        accepted.add(f"descriptive, on the {mechanism} seeds only: whether the replies from the warning sign on "
                     "differ by wording")
        accepted.add(f"descriptive, on the passing {mechanism} seeds only: whether the replies from the warning "
                     "sign on differ by wording; with none, not computable")
    return normalized(rule) in {normalized(value) for value in accepted}


class NotAPlanFire(AnalysisRefusal):
    """A run whose journal nonce is not one of the plan's run fires."""


class VoidedFire(AnalysisRefusal):
    """A run of a fire the plan records as voided for an operational defect."""


# ------------------------------------------------------------------ the plan


@dataclass(frozen=True)
class Target:
    id: str
    role: str
    name: str
    target_specs: tuple[str, ...]


@dataclass(frozen=True)
class RunFire:
    journal_nonce: str
    target: str
    campaign_epoch: int
    voided: str | None
    recorded_on: str


@dataclass(frozen=True)
class RegradeFire:
    journal_nonce: str
    source_runs: tuple[str, ...]
    target: str | None              # optional on a re-grade entry; when given, checked against the runs it re-grades
    campaign_epoch: int | None      # likewise
    voided: str | None
    recorded_on: str


@dataclass(frozen=True)
class Sensitivity:
    name: str
    window: str
    measure: w2.Measure
    rule: str | None
    mechanism: str | None           # a mechanism window's mechanism


@dataclass(frozen=True)
class Plan:
    path: Path
    sha256: str
    approved: bool
    approved_by: Any
    approved_on: Any
    realism_gate: dict[str, Any]
    analysis_script_path: Any
    analysis_script_status: Any
    secondary_spec: str
    sets: dict[str, tuple[str, ...]]
    decomposition_set: str
    mechanisms: dict[str, tuple[str, ...]]
    targets: tuple[Target, ...]
    epochs: int
    triples_per_epoch: int
    final_triples_per_target: int
    fires: dict[str, RunFire]
    regrade_fires: dict[str, RegradeFire]
    rubric_digest: str
    tier_rank: dict[str, int]
    prompt_digests: dict[str, str]
    windows: dict[str, w2.Window]
    alpha: float
    primary_measure: w2.Measure
    primary_window: str
    late_window: str
    sensitivity: tuple[Sensitivity, ...]
    family: tuple[str, ...]
    restricted: dict[str, tuple[str, ...]]
    coverage_only: tuple[str, ...]
    bootstrap_seed: int
    bootstrap_resamples: int
    judge_model: str | None
    judge_routes: tuple[str, ...]
    statements: dict[str, dict[str, dict]]
    every_statement_carries: str
    seed_file: Path
    realism_gate_selection: Any

    @property
    def scenarios(self) -> list[str]:
        """Every plan seed (one scenario each), in plan order: the k of the general-headline gate."""
        return [s for seeds in self.sets.values() for s in seeds]

    @property
    def anchor(self) -> Target:
        return next(t for t in self.targets if t.role == "anchor")

    @property
    def comparison(self) -> list[Target]:
        return [t for t in self.targets if t.role == "comparison"]

    def target(self, tid: str) -> Target:
        return next(t for t in self.targets if t.id == tid)

    def live_fire(self, target: str, epoch: int) -> RunFire | None:
        """The one fire of (target, epoch) the plan has not voided, or None."""
        return next((f for f in self.fires.values() if f.target == target and f.campaign_epoch == epoch
                     and f.voided is None), None)

    def regrade_fire_of(self, stem: str) -> RegradeFire | None:
        return next((f for f in self.regrade_fires.values() if stem in f.source_runs and f.voided is None), None)


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _seed_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(s, str) and s for s in value)


def _hex12(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 12 and all(c in "0123456789abcdef" for c in value)


def _get(doc: Mapping[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def _measure(spec: Any) -> w2.Measure | None:
    """A sensitivity's `measure` ("tier response_only") as a Measure, named as wave 2 names its tier measures."""
    if not isinstance(spec, str) or len(spec.split()) != 2:
        return None
    kind, key = spec.split()
    return w2.Measure(f"{kind}_{key}", kind, key)


def _fires(raw: Any, targets: Mapping[str, Target], epochs: int,
           problems: list[str]) -> tuple[dict[str, RunFire], dict[str, RegradeFire]]:
    run_fires: dict[str, RunFire] = {}
    regrades: dict[str, RegradeFire] = {}
    if not isinstance(raw, list):
        problems.append("fires must be a list (empty until the first fire is recorded)")
        return run_fires, regrades
    for i, f in enumerate(raw, 1):
        if not isinstance(f, dict):
            problems.append(f"fire entry {i} is a JSON {type(f).__name__}, not an object")
            continue
        nonce = f.get("journal_nonce")
        if not isinstance(nonce, str) or not nonce or nonce in run_fires or nonce in regrades:
            problems.append(f"fire entry {i}: journal_nonce {nonce!r} missing, not a string, or repeated")
            continue
        recorded_on = f.get("recorded_on")
        try:
            if not isinstance(recorded_on, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", recorded_on) is None:
                raise ValueError("expected YYYY-MM-DD")
            date.fromisoformat(recorded_on)
        except ValueError:
            problems.append(f"fire {nonce}: recorded_on must be the dated amendment's valid YYYY-MM-DD date")
            continue
        voided = f.get("voided")
        if voided is not None and not (isinstance(voided, str) and voided.strip()):
            problems.append(f"fire {nonce}: voided must be the reason the fire was voided, as text")
            continue
        regrade = "source_runs" in f
        unknown = sorted(set(f) - (REGRADE_FIRE_KEYS if regrade else RUN_FIRE_KEYS) - OPTIONAL_FIRE_KEYS)
        if unknown:
            problems.append(f"fire {nonce}: unknown key(s) {unknown}; a fire is {{journal_nonce, target, "
                            f"campaign_epoch}}, a re-grade fire adds source_runs")
            continue
        target = f.get("target")
        if (not regrade or target is not None) and target not in targets:
            problems.append(f"fire {nonce}: target {target!r} is not a registered target {sorted(targets)}")
            continue
        epoch = f.get("campaign_epoch")
        if (not regrade or epoch is not None) and (not _count(epoch) or not 1 <= epoch <= epochs):
            problems.append(f"fire {nonce}: campaign_epoch {epoch!r} is not one of 1..{epochs}")
            continue
        if regrade:
            stems = f["source_runs"]
            if not _seed_list(stems) or not stems or len(set(stems)) != len(stems) \
                    or not all(_stem_ok(s) for s in stems):
                problems.append(f"fire {nonce}: source_runs must be a non-empty list of distinct run stems "
                                f"(run_<id>_<attempt>)")
                continue
            regrades[nonce] = RegradeFire(nonce, tuple(stems), target, epoch, voided, recorded_on)
            continue
        run_fires[nonce] = RunFire(nonce, target, epoch, voided, recorded_on)
    live = Counter((f.target, f.campaign_epoch) for f in run_fires.values() if f.voided is None)
    for (target, epoch), n in sorted(live.items()):
        if n > 1:
            problems.append(f"target {target} epoch {epoch} has {n} fires not voided; a voided fire is recorded "
                            f"with its reason before its epoch is re-fired")
    stems = Counter(s for f in regrades.values() if f.voided is None for s in f.source_runs)
    doubled = sorted(s for s, n in stems.items() if n > 1)
    if doubled:
        problems.append(f"run(s) {doubled} are re-graded by more than one re-grade fire not voided")
    return run_fires, regrades


def _stem_ok(stem: str) -> bool:
    return re.fullmatch(rejudge.STEM_PATTERN, stem) is not None


def load_plan(path: Path | str = PLAN_FILE) -> Plan:
    """The wave-3 plan's structure, refused by name when a field is absent or malformed, or when it says something
    this script does not implement (a contrast, window, statement id or sensitivity it has no rule for): every problem
    is reported, never raised as a KeyError from deep inside."""
    path = Path(path)
    if not path.is_file():
        raise AnalysisRefusal(f"plan file {path} not found")
    try:
        doc = load_json(path)
    except ValueError as exc:
        raise AnalysisRefusal(f"plan file {path} does not parse: {exc}") from exc
    if not isinstance(doc, dict):
        raise AnalysisRefusal(f"plan file {path} is not a JSON object")
    required = ("approval.approved", "scenario_sets", "decomposition_set", "mechanisms", "targets", "epochs_per_target",
                "triples_per_epoch_per_target", "final_triples_per_target", "fires", "outcome.kind", "outcome.key",
                "outcome.final_in_exchange", "outcome.tier_rank", "rubric_digest", "prompt_digests", "windows",
                "alpha", "primary.contrast", "primary.window", "primary.target", "general_headline_gate.target", "decomposition.contrasts.style",
                "decomposition.contrasts.vocabulary", "secondary_exchanges_6_10.window", "sensitivity",
                "exploratory_outcomes.family", "exploratory_outcomes.restricted_to_seeds",
                "exploratory_outcomes.coverage_only", "effect_size.bootstrap_seed",
                "effect_size.bootstrap_resamples", "judge.judge_model", "judge.routes", "statements.primary",
                "statements.decomposition", "statements.every_statement_carries", "seed_file", "judge.second_family_regrade")
    problems = []
    for key in required:
        try:
            _get(doc, key)
        except KeyError:
            problems.append(f"missing {key!r}")
    if problems:
        raise AnalysisRefusal(f"plan file {path}: " + "; ".join(problems))

    raw_sets = doc["scenario_sets"]
    if not isinstance(raw_sets, dict) or not raw_sets or not all(_seed_list(v) and v for v in raw_sets.values()):
        raise AnalysisRefusal(f"plan file {path}: scenario_sets must map each set name to a non-empty list of seed ids")
    sets = {name: tuple(seeds) for name, seeds in raw_sets.items()}
    every = [s for seeds in sets.values() for s in seeds]
    if len(every) != len(set(every)):
        problems.append("a seed is listed in more than one scenario set, or twice")
    decomposition_set = doc["decomposition_set"]
    if not isinstance(decomposition_set, str) or decomposition_set not in sets:
        problems.append(f"decomposition_set {decomposition_set!r} is not a scenario set")
    elif set(sets[decomposition_set]) != set(every):
        problems.append(f"decomposition_set {decomposition_set!r} does not hold every plan seed; in wave 3 the "
                        f"decomposition runs on every seed")

    raw_mech = doc["mechanisms"]
    mechanisms: dict[str, tuple[str, ...]] = {}
    if not isinstance(raw_mech, dict) or not all(isinstance(v, list) and _seed_list(v) for v in raw_mech.values()):
        problems.append("mechanisms must map each mechanism to a list of seed ids (an empty list is an absent one)")
    else:
        mechanisms = {k: tuple(v) for k, v in raw_mech.items()}
        listed = [s for v in mechanisms.values() for s in v]
        if sorted(listed) != sorted(set(every)) or len(listed) != len(set(listed)):
            problems.append("mechanisms must list every plan seed exactly once")

    targets: dict[str, Target] = {}
    raw_targets = doc["targets"]
    if not isinstance(raw_targets, list) or not raw_targets:
        problems.append("targets must be a non-empty list")
        raw_targets = []
    for i, t in enumerate(raw_targets, 1):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t.get("id") or t.get("id") in targets:
            problems.append(f"target entry {i}: id missing, not a string, or repeated")
            continue
        specs = t.get("target_specs")
        if t.get("role") not in ROLES or not isinstance(t.get("name"), str) or not t.get("name") \
                or not _seed_list(specs) or not specs:
            problems.append(f"target {t['id']}: role must be one of {list(ROLES)}, name text, and target_specs a "
                            f"non-empty list of target specs")
            continue
        targets[t["id"]] = Target(t["id"], t["role"], t["name"], tuple(specs))
    if targets and sum(t.role == "anchor" for t in targets.values()) != 1:
        problems.append("targets must have exactly one anchor")
    all_specs = [s for t in targets.values() for s in t.target_specs]
    if len(all_specs) != len(set(all_specs)):
        problems.append("a target spec is listed under more than one target")

    epochs = doc["epochs_per_target"]
    if not _count(epochs) or epochs < 1:
        problems.append(f"epochs_per_target {epochs!r} is not a positive integer")
        epochs = 0
    for key in ("triples_per_epoch_per_target", "final_triples_per_target"):
        if not _count(doc[key]):
            problems.append(f"{key} {doc[key]!r} is not an integer")
    if _count(doc["triples_per_epoch_per_target"]) and _count(epochs) \
            and doc["final_triples_per_target"] != doc["triples_per_epoch_per_target"] * epochs:
        problems.append("final_triples_per_target is not triples_per_epoch_per_target x epochs_per_target")
    fires, regrades = _fires(doc["fires"], targets, epochs, problems)

    outcome = doc["outcome"]
    if outcome.get("kind") != w2.PRIMARY.kind or outcome.get("key") != w2.PRIMARY.key \
            or outcome.get("final_in_exchange") is not True:
        problems.append(f"outcome must be the final reply's {w2.PRIMARY.kind}:{w2.PRIMARY.key} rows (the outcome this "
                        f"script ranks)")
    tier_rank = outcome.get("tier_rank")
    if not isinstance(tier_rank, dict) or not all(_count(v) for v in tier_rank.values()) \
            or sorted(tier_rank.values()) != list(range(len(tier_rank))):
        problems.append("outcome.tier_rank must rank its tiers 0..n-1")
        tier_rank = {}
    if not _hex12(doc["rubric_digest"]):
        problems.append(f"rubric_digest {doc['rubric_digest']!r} is not a 12-character lowercase hex digest")
    prompt_digests = doc["prompt_digests"]
    if not isinstance(prompt_digests, dict) or not all(_hex12(v) for v in prompt_digests.values()):
        problems.append("prompt_digests must map each outcome dimension to a 12-character hex digest")
        prompt_digests = {}

    windows: dict[str, w2.Window] = {}
    raw_windows = doc["windows"]
    if not isinstance(raw_windows, dict):
        problems.append("windows must be an object")
        raw_windows = {}
    for name, w in raw_windows.items():
        ex = w.get("exchanges") if isinstance(w, dict) else None
        floor = w.get("floor") if isinstance(w, dict) else None
        if not (isinstance(ex, list) and ex and all(_count(e) and 1 <= e <= w2.EXCHANGES for e in ex)
                and len(set(ex)) == len(ex) and _count(floor) and 1 <= floor <= len(ex)):
            problems.append(f"window {name}: exchanges must be distinct exchange numbers 1..{w2.EXCHANGES} and its "
                            f"floor 1..their number")
            continue
        windows[name] = w2.Window(name, tuple(ex), floor)

    def window_ref(key: str) -> str:
        name = _get(doc, key)
        if not isinstance(name, str) or name not in windows:
            problems.append(f"{key} {name!r} is not one of the plan's windows")
        return name

    primary_window = window_ref("primary.window")
    for selector in ("primary.target", "general_headline_gate.target"):
        if _get(doc, selector) != "anchor":
            problems.append(f"{selector} must remain anchor, the target this script computes")
    late_window = window_ref("secondary_exchanges_6_10.window")
    for key, expected in (("primary.contrast", [COLLOQUIAL, CLINICAL]),
                          ("decomposition.contrasts.style", [COLLOQUIAL, CAREFUL_LAY]),
                          ("decomposition.contrasts.vocabulary", [CAREFUL_LAY, CLINICAL])):
        contrast = _get(doc, key)
        if not isinstance(contrast, list) or contrast != expected:
            problems.append(f"{key} must be the list {expected!r}, the contrast this script computes")
    alpha = doc["alpha"]
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0 < alpha < 1:
        problems.append(f"alpha {alpha!r} is not a number between 0 and 1")
    elif alpha != 0.05:
        problems.append("alpha must remain 0.05 to match the implemented statement rules")

    # Rule-bearing method text is an executable contract too. Counts may follow a gate amendment,
    # but an unsupported test or correction must never silently select the hard-coded statistic.
    method_rules = {
        "primary.test": "exact two-sided sign test on the sign of D over the anchor's triples",
        "general_headline_gate.test": (
            f"exact two-sided sign-flip permutation test over all {2 ** len(every)} sign assignments of the "
            f"{len(every)} scenario means; p is the share whose absolute sum is at least the observed one"),
        "comparison_targets.test": "for each comparison target, the primary test and the general-headline gate "
                                   "on its own triples",
        "comparison_targets.correction": "Holm across the comparison targets' primary tests, family-wise alpha "
                                         "0.05; each target's gate is reported beside its test",
        "secondary_exchanges_6_10.test": f"exact two-sided sign test on D({COLLOQUIAL}, {CLINICAL}) over the window",
        "secondary_exchanges_6_10.correction": "none for the anchor, which is one pre-specified secondary reported "
                                              "beside the primary; Holm across the comparison targets, as in "
                                              "comparison_targets",
        "exploratory_outcomes.test": f"exact two-sided sign test on D({COLLOQUIAL}, {CLINICAL}) over "
                                     "exchanges_1_10, per target",
        "exploratory_outcomes.correction": "Holm, one family of three per target",
    }
    method_rules["decomposition.contrasts.paired_difference"] = "the sign of D(style) - D(vocabulary) per triple"
    method_rules["effect_size.rule"] = "cite the direction, not the magnitude (AGENTS.md, Known measurement limitations)"
    if len(every) >= 2:
        interval = (f"a 95% interval for the mean across scenarios: the mean of the {len(every)} scenario means "
                    f"plus or minus t(0.975, {len(every) - 1}) times their standard error "
                    f"(t = {w2.student_t_quantile(0.975, len(every) - 1):.3f})")
        reported = ["the proportion of triples with D < 0", "the median and mean of D", interval,
                    "a percentile bootstrap over triples, labelled unclustered and within these scenarios only"]
        actual_reported = doc["effect_size"].get("reported")
        # Validate each list member with the same number-word equivalence as method prose.
        if not isinstance(actual_reported, list) or len(actual_reported) != len(reported):
            problems.append("effect_size.reported must list the four implemented methods")
        else:
            for i, expected in enumerate(reported):
                method_rules[f"effect_size.reported_{i}"] = expected
        doc = {**doc, "effect_size": {**doc["effect_size"],
               **{f"reported_{i}": value for i, value in enumerate(actual_reported if isinstance(actual_reported, list) else [])}}}
    else:
        problems.append("effect_size.reported needs at least two planned scenarios for its registered interval")
    for rule_path, expected in method_rules.items():
        try:
            actual = _get(doc, rule_path)
        except KeyError:
            actual = None
        if isinstance(actual, str):
            for number, word in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                                            "nine", "ten")):
                actual = re.sub(r"\b" + word + r"\b", str(number), actual)
                expected = re.sub(r"\b" + word + r"\b", str(number), expected)
        if actual != expected:
            problems.append(f"{rule_path} must match the implemented registered method (including amended counts)")

    sensitivity: list[Sensitivity] = []
    raw_sens = doc["sensitivity"]
    if not isinstance(raw_sens, list):
        problems.append("sensitivity must be a list")
        raw_sens = []
    by_window_name = {k.replace("-", "_") + MECHANISM_WINDOW_SUFFIX: k for k in mechanisms}
    sensitivity_names: set[str] = set()
    for i, s in enumerate(raw_sens, 1):
        name = s.get("name") if isinstance(s, dict) else None
        measure = _measure(s.get("measure")) if isinstance(s, dict) else None
        if not isinstance(name, str) or measure is None or measure.kind != "tier" or not isinstance(s.get("window"), str) or s["window"] not in windows:
            problems.append(f"sensitivity entry {i} ({name!r}): needs a name, a window of the plan and a measure "
                            f"'tier <key>'")
            continue
        if name in sensitivity_names:
            problems.append(f"sensitivity entry {i} ({name!r}): repeated name; sensitivity names must be distinct")
            continue
        sensitivity_names.add(name)
        if name in SENSITIVITY_RULES and (
                (measure.kind, measure.key) != (w2.PRIMARY.kind, w2.PRIMARY.key)
                or s["window"] != primary_window or not isinstance(s.get("rule"), str) or not s["rule"].strip()):
            problems.append(f"sensitivity {name!r} must retain the primary measure/window and a rule")
            continue
        rule = s.get("rule")
        mechanism = by_window_name.get(name)
        if (name in SENSITIVITY_RULES or mechanism is not None) and not supported_sensitivity_rule(
                rule, name, mechanism, len(every), mechanisms, epochs):
            problems.append(f"sensitivity {name!r} does not retain its implemented rule for these passing counts")
            continue
        if rule is not None and name not in SENSITIVITY_RULES and mechanism is None:
            problems.append(f"sensitivity {name!r} has a rule this script does not implement (it implements "
                            f"{list(SENSITIVITY_RULES)} and a mechanism's window, named <mechanism>"
                            f"{MECHANISM_WINDOW_SUFFIX})")
            continue
        sensitivity.append(Sensitivity(name, s["window"], measure, rule, mechanism))

    exploratory = doc["exploratory_outcomes"]
    secondary_names = {m.name for m in w2.SECONDARY_MEASURES}
    family = exploratory["family"]
    if not _seed_list(family) or family != [m.name for m in w2.SECONDARY_MEASURES[1:]]:
        problems.append("exploratory_outcomes.family must retain the registered three outcomes in order, "
                        "with the restricted outcome separate")
        family = []
    restricted_raw = exploratory["restricted_to_seeds"]
    restricted: dict[str, tuple[str, ...]] = {}
    if not isinstance(restricted_raw, dict) or not all(_seed_list(v) for v in restricted_raw.values()):
        problems.append("exploratory_outcomes.restricted_to_seeds must map each outcome to a list of seed ids")
    else:
        for name, seeds in restricted_raw.items():
            if name not in secondary_names:
                problems.append(f"restricted_to_seeds names {name!r}, which is not an outcome this script measures")
            stray = sorted(set(seeds) - set(every))
            if stray:
                problems.append(f"restricted_to_seeds[{name!r}] names seeds outside the scenario sets: {stray}")
            restricted[name] = tuple(seeds)
    coverage_only = exploratory["coverage_only"]
    if not _seed_list(coverage_only):
        problems.append("exploratory_outcomes.coverage_only must be a list of outcome dimension ids")
        coverage_only = []
    for name in coverage_only:
        if _measure_of(name).kind != "outcome":
            problems.append(f"exploratory_outcomes.coverage_only entry {name!r} is not an outcome dimension")
    for name in [*family, *restricted, *coverage_only]:
        m = next((m for m in w2.SECONDARY_MEASURES if m.name == name), None)
        key = m.key if m is not None else name
        if (m is None or m.kind == "outcome") and key not in prompt_digests:
            problems.append(f"prompt_digests pins no digest for {key}, so its rows cannot be held to one instrument")

    seed_value = _get(doc, "effect_size.bootstrap_seed")
    resamples = _get(doc, "effect_size.bootstrap_resamples")
    if not _count(seed_value) or not _count(resamples) or resamples < 1:
        problems.append("effect_size.bootstrap_seed and bootstrap_resamples must be integers")
    judge_model = _get(doc, "judge.judge_model")
    routes = _get(doc, "judge.routes")
    if not isinstance(routes, dict) or not routes:
        problems.append("judge.routes must name the judge routes")
        routes = {}
    if judge_model is not None and (not isinstance(judge_model, str) or judge_model not in routes):
        problems.append(f"judge.judge_model {judge_model!r} is not one of judge.routes {sorted(routes)}")

    secondary = _get(doc, "judge.second_family_regrade")
    secondary_spec = secondary.split(" through ", 1)[0] if isinstance(secondary, str) else ""
    try:
        rejudge.judge_slug(secondary_spec)
    except rejudge.RejudgeError:
        problems.append("judge.second_family_regrade must begin with the designated judge spec before ' through '")
    script = doc.get("analysis_script")
    script = script if isinstance(script, dict) else {}

    statements: dict[str, dict[str, dict]] = {}
    for table, ids in (("primary", PRIMARY_STATEMENT_IDS), ("decomposition", DECOMPOSITION_STATEMENT_IDS)):
        rows = _get(doc, f"statements.{table}")
        got = [r.get("id") for r in rows] if isinstance(rows, list) and all(isinstance(r, dict) for r in rows) else []
        if sorted(map(str, got)) != sorted(ids) or not all(
                isinstance(r.get("text"), str) and r["text"].strip() for r in rows):
            problems.append(f"statements.{table} must hold exactly the rows {list(ids)}, each with nonempty text")
            continue
        statements[table] = {r["id"]: r for r in rows}
        # Selection implements these rules, not an interpreter for arbitrary amended prose.
        for row_id, rules in STATEMENT_RULES[table].items():
            for key, expected in rules.items():
                if statements[table][row_id].get(key) != expected:
                    problems.append(f"statements.{table} {row_id}.{key} is not the implemented rule {expected!r}")
    for row in RENDERED_ROWS:
        text = statements.get("primary", {}).get(row, {}).get("text", TARGET_PLACEHOLDER)
        if TARGET_PLACEHOLDER not in text:
            problems.append(f"statements.primary {row} does not name {TARGET_PLACEHOLDER}; 9.8 renders it per target")
    disclosure = doc["statements"]["every_statement_carries"]
    if not isinstance(disclosure, str) or not disclosure.strip():
        problems.append("statements.every_statement_carries must be nonempty text")
    seed_file = Path(doc["seed_file"]) if isinstance(doc["seed_file"], str) else None
    if seed_file is None:
        problems.append("seed_file must be a path")
    if not isinstance(_get(doc, "approval.approved"), bool):
        problems.append("approval.approved must be true or false")
    if problems:
        raise AnalysisRefusal(f"plan file {path}: " + "; ".join(problems))
    return Plan(
        path=path, sha256=sha256_file(path), approved=doc["approval"]["approved"], sets=sets,
        approved_by=doc["approval"].get("approved_by"), approved_on=doc["approval"].get("approved_on"),
        realism_gate=doc.get("physician_realism_gate") if isinstance(doc.get("physician_realism_gate"), dict) else {},
        analysis_script_path=script.get("path"), analysis_script_status=script.get("status"),
        secondary_spec=secondary_spec,
        decomposition_set=decomposition_set, mechanisms=mechanisms, targets=tuple(targets.values()), epochs=epochs,
        triples_per_epoch=doc["triples_per_epoch_per_target"],
        final_triples_per_target=doc["final_triples_per_target"], fires=fires, regrade_fires=regrades,
        rubric_digest=doc["rubric_digest"], tier_rank=dict(tier_rank), prompt_digests=dict(prompt_digests),
        windows=windows, alpha=float(alpha), primary_measure=w2.PRIMARY, primary_window=primary_window,
        late_window=late_window, sensitivity=tuple(sensitivity), family=tuple(family), restricted=restricted,
        coverage_only=tuple(coverage_only), bootstrap_seed=seed_value, bootstrap_resamples=resamples,
        judge_model=judge_model, judge_routes=tuple(routes), statements=statements,
        every_statement_carries=doc["statements"]["every_statement_carries"],
        seed_file=seed_file if seed_file.is_absolute() else ROOT / seed_file,
        realism_gate_selection=(doc.get("physician_realism_gate") if isinstance(doc.get("physician_realism_gate"), dict) else {}).get("selection"))


def plan_layouts(plan: Plan, seeds: Mapping[str, dict]) -> dict[str, w2.SeedLayout]:
    """Every plan seed's layout (wave 2's `seed_layout`: sustained exposure, one arm per register and speaker, ten
    exchanges), and the check that the plan's per-target counts follow from the seeds."""
    layouts: dict[str, w2.SeedLayout] = {}
    for name, seed_ids in plan.sets.items():
        for sid in seed_ids:
            if sid not in seeds:
                raise AnalysisRefusal(f"plan seed {sid} is not in the seed file")
            layouts[sid] = w2.seed_layout(seeds[sid], name)
    per_epoch = sum(len(layout.speakers) for layout in layouts.values())
    if per_epoch != plan.triples_per_epoch:
        raise AnalysisRefusal(f"the plan's seeds give {per_epoch} triples per epoch and target, but it fixes "
                              f"{plan.triples_per_epoch}")
    for name, seed_ids in plan.restricted.items():
        key = _measure_of(name).key
        undeclared = [s for s in seed_ids if key not in layouts[s].outcome_dimensions]
        if undeclared:
            raise AnalysisRefusal(f"restricted outcome {name}: seeds {undeclared} do not judge {key}")
    return layouts


def _measure_of(name: str) -> w2.Measure:
    """A wave-2 secondary measure by name (the clarifying-question flag is read from the response-only tier rows), or a
    coverage-only outcome dimension."""
    return next((m for m in w2.SECONDARY_MEASURES if m.name == name), None) or w2.Measure(name, "outcome", name)


# ------------------------------------------------------------------ runs and their registered rows


@dataclass
class RunInput:
    """One landed run of a plan fire: its manifest, the target it ran, and the rows the analysis reads, which are the
    judge of record's (registered) rows, from the run itself or from a verified re-grade; empty, with the reason, when
    the run has none (judged under another route, no re-grade yet)."""
    run_dir: Path
    stem: str
    manifest: dict
    fire: RunFire
    target: Target
    rows: list[dict]
    registered: bool
    unregistered_reason: str | None
    registry: w2.RegistryVersion | None
    registry_problem: str | None
    provenance: dict[str, Any]


def rebuild_rows(judgments_path: Path, manifest: dict, seeds: Mapping[str, dict], judge_model: str,
                 where: str) -> tuple[list[dict], dict[str, int]]:
    """The analysis rows of one judgments file, rebuilt through `judge_runner.analysis_rows` (against the source run's
    manifest) after retries collapse to the latest per key; refused when any row carries a judge spec other than
    `judge_model` (judge.one_route: one judge string per registered row)."""
    try:
        judgments = judge_runner.read_jsonl(judgments_path)
    except ValueError as exc:
        raise AnalysisRefusal(f"{where}: {judgments_path.name} does not parse ({exc})") from exc
    others = sorted({str(j.get("judge_model")) for j in judgments if j.get("judge_model") != judge_model})
    if others:
        raise AnalysisRefusal(f"{where}: its judgments carry judge spec(s) {others} beside {judge_model!r}; one run's "
                              f"rows carry one judge (judge.one_route)")
    try:
        collapsed, superseded = w2.collapse_retries(judgments)
        rows = judge_runner.analysis_rows(collapsed, manifest, dict(seeds))
    except (ValueError, KeyError) as exc:
        raise AnalysisRefusal(f"{where}: judge_runner.analysis_rows refused the rows: {exc}") from exc
    return rows, {"judgment_rows": len(judgments), "superseded_by_retry": superseded, "rows_rebuilt": len(rows)}


JUDGE_COUNT_FIELDS = ("planned", "judged", "null", "not_applicable")


def incomplete_pass(record: Any, what: str) -> str | None:
    """Why a judging pass cannot vouch that every planned judgment has a row, or None when it can (the check
    scripts/petri_three_arm.py's `_incomplete_judging` makes). `record` is a run's artifacts.judge_of_record or a
    re-grade manifest's `counts`: `truncated` must be false, and judged + null + not_applicable must reach `planned`.
    manifest.verify_run and rejudge.verify_output check integrity, not completeness: a pass the spend ceiling stopped
    binds its partial file, and the judgments after the stop would vanish from the comparable exchanges unnamed."""
    if not isinstance(record, Mapping):
        return f"{what} is not an object, so it records neither truncation nor the plan count"
    if record.get("truncated") is not False:
        return (f"{what}.truncated is {record.get('truncated')!r} (the judge stopped before every plan was judged; "
                f"planned {record.get('planned')!r})")
    counts = {k: record.get(k) for k in JUDGE_COUNT_FIELDS}
    if any(isinstance(v, bool) or not isinstance(v, int) for v in counts.values()):
        return f"{what} lacks an integer count among {counts}"
    recorded = counts["judged"] + counts["null"] + counts["not_applicable"]
    if recorded < counts["planned"]:
        return (f"{what} records {recorded} judgments (judged {counts['judged']}, null {counts['null']}, "
                f"not_applicable {counts['not_applicable']}) for {counts['planned']} planned")
    return None


def judgment_plan_problem(path: Path, record: Mapping[str, Any], seeds: Mapping[str, dict],
                          registry: w2.RegistryVersion | None, *, judgments_path: Path | None = None,
                          planned_count: int | None = None) -> str | None:
    """Rebuild expected judgment slots independently of the pass's self-reported counts.

    Slot parity covers conversation/turn/kind/key. Prompt-version admissibility remains the existing per-row
    instrument gate: a mismatched digest is explicitly excluded there, never used as evidence of a missing slot.
    No judgment call is made; the planner only renders the committed instrument against committed transcripts.
    """
    if registry is None:
        return "judgment plan cannot be rebuilt: the run's recorded outcome registry is unresolved"
    try:
        plans = judge_runner.plan_run(judge_runner.read_jsonl(path / "transcripts.jsonl"), dict(record), dict(seeds),
                                      outcomes=registry.registry, rubric=judge_runner.load_rubric())
        expected = {(p.conversation_id, p.turn_id, p.kind, p.key) for p in plans}
        rows = judge_runner.read_jsonl(judgments_path or path / "judgments.jsonl")
        actual = {(r.get("conversation_id"), r.get("turn_id"), r.get("kind"), r.get("key")) for r in rows}
        declared = planned_count if planned_count is not None else record["artifacts"]["judge_of_record"]["planned"]
        if len(expected) != len(plans):
            return "rebuilt judgment plan contains duplicate slots"
        if declared != len(expected) or actual != expected:
            return (f"rebuilt judgment plan requires {len(expected)} slots, pass declares {declared}; "
                    f"missing slots {len(expected - actual)}, unexpected slots {len(actual - expected)}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return f"judgment plan cannot be rebuilt: {exc}"
    return None


def claim_grade_problem(manifest: Mapping[str, Any]) -> str | None:
    """Why a run fails the claim-grade contract, or None. Every wave-3 seed is declared claim_grade_eligible (design
    note section 2), so a run whose manifest's execution.claim_grade_eligible is not true failed a contract check, had
    records refused by the adapter, or ran a seed that is not claim-grade: an operational defect, for which fires_rule
    voids the fire and re-fires its epoch. Its rows are never registered (judge_runner.analysis_rows marks every one of
    them estimator_eligible false)."""
    execution = manifest.get("execution") or {}
    if execution.get("claim_grade_eligible") is True:
        return None
    failing = sorted(k for k, v in (execution.get("contract_checks") or {}).items()
                     if not (isinstance(v, Mapping) and v.get("status") in ("pass", "not_applicable")))
    refused = len((manifest.get("integrity") or {}).get("records_refused") or [])
    seeds = sorted(str(s.get("seed_id")) for s in manifest.get("seeds") or []
                   if s.get("claim_grade_eligible") is not True)
    return (f"the run fails the claim-grade contract (execution.claim_grade_eligible is "
            f"{execution.get('claim_grade_eligible')!r}; contract checks not passed: {failing}; records refused by the "
            f"adapter: {refused}; seeds not claim-grade: {seeds}); fires_rule voids such a fire and re-fires its epoch")


def read_regrade(out_dir: Path, runs_dir: Path, judge_model: str, manifest: dict, seeds: Mapping[str, dict],
                 registry: w2.RegistryVersion | None) -> tuple[list[dict], dict[str, Any]] | None:
    """A re-grade's rows for one source run, or None when the directory holds no re-grade. Refused, by name, unless
    `rejudge.verify_output` passes (the manifest, its artifacts, its rows' judge, and the source run it names still
    verifying as the bytes it read), the manifest's judge is exactly `judge_model`, and it is not a rehearsal."""
    if not (out_dir / rejudge.MANIFEST_NAME).is_file():
        return None
    where = w2._display(out_dir)
    try:
        problems = rejudge.verify_output(out_dir, runs_dir)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AnalysisRefusal(f"the re-grade {where} cannot be verified: {exc}") from exc
    if problems:
        raise AnalysisRefusal(f"the re-grade {where} does not verify: " + "; ".join(problems[:6]))
    rm = load_json(out_dir / rejudge.MANIFEST_NAME)
    if rm["judge"]["judge_model"] != judge_model:
        raise AnalysisRefusal(f"the re-grade {where} was judged by {rm['judge']['judge_model']!r}, not "
                              f"{judge_model!r}")
    if rm.get("rehearsal"):
        raise AnalysisRefusal(f"the re-grade {where} is a rehearsal (mock judge), never a measurement")
    rows, counts = rebuild_rows(out_dir / rejudge.JUDGMENTS_NAME, manifest, seeds, judge_model, where)
    info = {"path": where, "judge_model": judge_model, "journal_nonce": rm["fire"]["journal_nonce"],
            "manifest_sha256": sha256_file(out_dir / rejudge.MANIFEST_NAME),
            "judgments_sha256": rm["artifacts"]["judgments"]["sha256"], "truncated": rm["counts"]["truncated"],
            "null_share": rm["counts"]["null_share"],
            "incomplete": (incomplete_pass(rm["counts"], f"the re-grade {where}'s counts")
                           or judgment_plan_problem(runs_dir / out_dir.name, manifest, seeds, registry,
                                                    judgments_path=out_dir / rejudge.JUDGMENTS_NAME,
                                                    planned_count=rm["counts"]["planned"])), **counts}
    return rows, info


def load_run(path: Path, plan: Plan, seeds: Mapping[str, dict], resolver: w2.RegistryResolver,
             rejudge_root: Path) -> RunInput:
    """One run directory, verified, with its registered rows. Refuses, by name: a file in place of a directory; a
    directory without manifest.json or judgments.jsonl; a fire outside the plan (NotAPlanFire) or voided (VoidedFire);
    a run that fails `manifest.verify_run` or differs from the plan's complete seed set; one that binds no judgments
    or records more than one epoch; a target spec
    that is not one of its fire's target's `target_specs`; judgments carrying two judge specs; a re-grade recorded for
    a run already judged under judge.judge_model; and a re-grade that does not verify or names another judge. A run
    that fails the claim-grade contract (`claim_grade_problem`), and one whose registered rows would come from an
    incomplete judging pass (`incomplete_pass`: its own, or the re-grade's), is loaded with no registered rows and the
    reason: coverage names it, and --final refuses while it remains (void the fire and re-fire, or re-grade)."""
    path = Path(path)
    where = w2._display(path)
    if path.is_file():
        raise AnalysisRefusal(f"{where}: a run is given as its directory, not as a file (a committed "
                              f"analysis_rows.jsonl is never an input)")
    if not path.is_dir():
        raise AnalysisRefusal(f"{where}: no such run directory")
    manifest = w2.read_manifest(path)
    if not (path / "judgments.jsonl").is_file():
        raise AnalysisRefusal(f"{where}: judgments.jsonl is missing, so no row can be rebuilt")
    nonce = w2.run_nonce(path, manifest)
    fire = plan.fires.get(nonce)
    if fire is None:
        raise NotAPlanFire(f"{where}: journal nonce {nonce!r} is not one of the plan's fires {sorted(plan.fires)}")
    if fire.voided is not None:
        raise VoidedFire(f"{where}: fire {nonce} is voided in the plan ({fire.voided})")
    problems = verify_run(path)
    if problems:
        raise AnalysisRefusal(f"{where}: the run does not verify: " + "; ".join(problems))
    run_seed_ids = {seed["seed_id"] for seed in manifest["seeds"]}
    planned_seed_ids = set(plan.scenarios)
    if run_seed_ids != planned_seed_ids:
        raise AnalysisRefusal(f"{where}: fire {nonce} seed set differs from the plan's scenarios "
                              f"(missing {sorted(planned_seed_ids - run_seed_ids)}; "
                              f"unplanned {sorted(run_seed_ids - planned_seed_ids)}); "
                              f"every landed fire must run the complete planned seed set")
    artifacts = manifest.get("artifacts") or {}
    if not artifacts.get("judgments_sha256"):
        raise AnalysisRefusal(f"{where}: the manifest binds no judgments (no judge of record)")
    epochs = (manifest.get("execution") or {}).get("epochs")
    tree_epochs = sorted({t.get("epoch") for t in manifest.get("trees") or []})
    if epochs != 1 or tree_epochs != [1]:
        raise AnalysisRefusal(f"{where}: each fire runs one campaign epoch, but the run records execution.epochs "
                              f"{epochs} and tree epochs {tree_epochs}")
    target = plan.target(fire.target)
    target_model = ((manifest.get("models") or {}).get("target") or {}).get("inspect_name")
    if target_model not in target.target_specs:
        raise AnalysisRefusal(f"{where}: fire {nonce} is recorded for target {target.id}, whose specs are "
                              f"{list(target.target_specs)}, but the run's target is {target_model!r}")
    recorded = (manifest.get("framework") or {}).get("outcome_registry_sha256")
    registry: w2.RegistryVersion | None = None
    registry_problem: str | None = None
    try:
        registry = resolver.resolve(path.name, recorded)
        if not isinstance(registry.registry, dict):
            raise ValueError("registry must be a JSON object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnalysisRefusal(f"run {path.name}: outcome registry {recorded} could not be read: {exc}") from exc
    except AnalysisRefusal as exc:
        registry_problem = str(exc)
    own_judge = (artifacts.get("judge_of_record") or {}).get("judge_model")
    regrade_fire = plan.regrade_fire_of(path.name)
    rows: list[dict] = []
    reason: str | None = None
    rows_from: dict[str, Any]
    claim = claim_grade_problem(manifest)
    if claim is not None:
        reason = claim
        rows_from = {"source": None}
    elif plan.judge_model is None:
        reason = "judge.judge_model is null: no row is registered until the dated approval sets the judge route"
        rows_from = {"source": None}
    elif own_judge == plan.judge_model:
        if regrade_fire is not None:
            raise AnalysisRefusal(f"{where}: re-grade fire {regrade_fire.journal_nonce} is recorded for a run already "
                                  f"judged under judge.judge_model {plan.judge_model!r}; which rows are registered is "
                                  f"ambiguous")
        incomplete = (incomplete_pass(artifacts.get("judge_of_record"), "artifacts.judge_of_record")
                      or judgment_plan_problem(path, manifest, seeds, registry))
        if incomplete is not None:
            reason = f"its judge of record's pass is incomplete: {incomplete}"
            rows_from = {"source": None}
        else:
            rows, counts = rebuild_rows(path / "judgments.jsonl", manifest, seeds, plan.judge_model, where)
            rows_from = {"source": "the run's own judgments", **counts}
    else:
        rows_from = {"source": None, "own_judge": own_judge}
        out_dir = Path(rejudge_root) / rejudge.judge_slug(plan.judge_model) / path.name
        if regrade_fire is None:
            reason = (f"judged under {own_judge!r}, not judge.judge_model {plan.judge_model!r}, and no re-grade "
                      f"fire in the plan's fires re-grades it (judge.one_route: re-grade it or re-fire)")
        else:
            got = read_regrade(out_dir, path.parent, plan.judge_model, manifest, seeds, registry)
            if got is None:
                reason = (f"judged under {own_judge!r}; re-grade fire {regrade_fire.journal_nonce} is recorded, but "
                          f"{w2._display(out_dir)} holds no re-grade")
            else:
                rows, info = got
                if info["journal_nonce"] != regrade_fire.journal_nonce:
                    raise AnalysisRefusal(f"the re-grade {info['path']} was made by fire {info['journal_nonce']!r}, "
                                          f"not the re-grade fire {regrade_fire.journal_nonce} the plan records for "
                                          f"{path.name}")
                if regrade_fire.target is not None and regrade_fire.target != target.id:
                    raise AnalysisRefusal(f"re-grade fire {regrade_fire.journal_nonce} is recorded for target "
                                          f"{regrade_fire.target}, but {path.name} ran target {target.id}")
                if regrade_fire.campaign_epoch is not None and regrade_fire.campaign_epoch != fire.campaign_epoch:
                    raise AnalysisRefusal(f"re-grade fire {regrade_fire.journal_nonce} is recorded for epoch "
                                          f"{regrade_fire.campaign_epoch}, but {path.name} is epoch "
                                          f"{fire.campaign_epoch}")
                rows_from = {"source": "re-grade", "own_judge": own_judge, **info}
                if info["incomplete"] is not None:
                    reason = f"its re-grade under judge.judge_model is incomplete: {info['incomplete']}"
                    rows = []
    provenance = {
        "run_stem": path.name, "path": where, "run_id": manifest.get("run_id"), "journal_nonce": nonce,
        "target": target.id, "campaign_epoch": fire.campaign_epoch, "target_model": target_model,
        "manifest_sha256": sha256_file(path / "manifest.json"), "manifest_chain": manifest.get("chain"),
        "judgments_sha256": sha256_file(path / "judgments.jsonl"), "own_judge_model": own_judge,
        "registered": reason is None, "unregistered_reason": reason, "registered_rows_from": rows_from,
        "outcome_registry": ({"sha256": registry.sha256, "source": registry.source, "location": registry.location,
                              "commit": registry.commit, "unresolved": None} if registry is not None else
                             {"sha256": recorded, "unresolved": registry_problem}),
        "run_claim_grade_eligible": bool((manifest.get("execution") or {}).get("claim_grade_eligible", False)),
        "records_refused_by_adapter": len((manifest.get("integrity") or {}).get("records_refused") or []),
    }
    return RunInput(path, path.name, manifest, fire, target, rows, reason is None, reason, registry, registry_problem,
                    provenance)


def load_runs(paths: Sequence[Path] | None, runs_dir: Path, plan: Plan, seeds: Mapping[str, dict],
              resolver: w2.RegistryResolver, rejudge_root: Path) -> tuple[list[RunInput], list[dict[str, str]]]:
    """The runs to analyse. Explicit paths must all be live plan fires. Without them, every directory under `runs_dir`
    holding a manifest is read, and a run outside the plan or of a voided fire is listed with that reason. Refused:
    two runs of one fire; registered rows under more than one judge string across the fires (judge.one_route); and,
    within one target, runs recording different target models (the targets differ by design, so the target refusal
    is per target)."""
    skipped: list[dict[str, str]] = []
    if paths:
        runs = [load_run(Path(p), plan, seeds, resolver, rejudge_root) for p in paths]
    else:
        if not Path(runs_dir).is_dir():
            raise AnalysisRefusal(f"runs directory {runs_dir} not found")
        runs = []
        for d in sorted(p for p in Path(runs_dir).iterdir() if p.is_dir()):
            if not (d / "manifest.json").is_file():
                skipped.append({"path": w2._display(d), "reason": "no manifest.json"})
                continue
            try:
                runs.append(load_run(d, plan, seeds, resolver, rejudge_root))
            except (NotAPlanFire, VoidedFire) as exc:
                skipped.append({"path": w2._display(d), "reason": str(exc)})
    doubled = sorted(n for n, c in Counter(r.fire.journal_nonce for r in runs).items() if c > 1)
    if doubled:
        raise AnalysisRefusal(f"more than one run carries journal nonce(s) {doubled}; the plan has one run per fire")
    judges = sorted({str(row.get("judge_model")) for r in runs for row in r.rows})
    if judges and judges != [plan.judge_model]:
        raise AnalysisRefusal(f"the registered rows carry judge specs {judges}; every registered row carries "
                              f"judge.judge_model {plan.judge_model!r} (judge.one_route)")
    for target in plan.targets:
        seen = sorted({str(r.provenance["target_model"]) for r in runs if r.target.id == target.id})
        if len(seen) > 1:
            raise AnalysisRefusal(f"target {target.id}: its runs record different target models {seen}; one target's "
                                  f"fires run one target spec")
    return runs, skipped


# ------------------------------------------------------------------ triples


@dataclass
class Triple:
    """9.1's conversation triple: one target, one seed, one campaign epoch and one speaker (none on every wave-3 seed),
    with its three conversations; a conversation is None with the reason in `missing`."""
    triple_id: str
    target: str
    seed_id: str
    scenario_set: str
    campaign_epoch: int
    speaker: str | None
    journal_nonce: str | None
    run_stem: str | None
    conversations: dict[str, str | None]
    missing: dict[str, str] = field(default_factory=dict)

    @property
    def landed(self) -> bool:
        return self.run_stem is not None

    @property
    def partition(self) -> None:
        """Wave 3 has no partition; present so wave 2's `pairwise_d` can build its record."""
        return None

    def label(self) -> dict[str, Any]:
        return {"triple": self.triple_id, "target": self.target, "seed_id": self.seed_id,
                "campaign_epoch": self.campaign_epoch, "speaker": self.speaker, "journal_nonce": self.journal_nonce,
                "run_stem": self.run_stem, "landed": self.landed, "conversations": dict(self.conversations),
                "missing_conversations": dict(self.missing)}


def triple_id(target: str, seed_id: str, epoch: int, speaker: str | None) -> str:
    return f"{target}:{seed_id}#e{epoch}" + (f"/{speaker}" if speaker else "")


def build_triples(plan: Plan, layouts: Mapping[str, w2.SeedLayout], runs: Sequence[RunInput]) -> list[Triple]:
    """Every triple the plan fixes, per target, landed or not, in plan order (targets, then epochs, then seeds)."""
    by_nonce = {r.fire.journal_nonce: r for r in runs}
    triples: list[Triple] = []
    for target in plan.targets:
        for epoch in range(1, plan.epochs + 1):
            fire = plan.live_fire(target.id, epoch)
            run = by_nonce.get(fire.journal_nonce) if fire else None
            run_seeds = {s.get("seed_id") for s in (run.manifest.get("seeds") or [])} if run else set()
            for set_name, seed_ids in plan.sets.items():
                for sid in seed_ids:
                    layout = layouts[sid]
                    for speaker in layout.speakers:
                        t = Triple(triple_id(target.id, sid, epoch, speaker), target.id, sid, set_name, epoch,
                                   speaker, fire.journal_nonce if fire else None, run.stem if run else None,
                                   {r: None for r in REGISTERS})
                        for register in REGISTERS:
                            if fire is None:
                                t.missing[register] = (f"no fire is recorded for target {target.id} epoch {epoch} "
                                                       f"(the plan's fires)")
                            elif run is None:
                                t.missing[register] = (f"fire {fire.journal_nonce} has not landed: no input run "
                                                       f"carries that journal nonce")
                            elif not run.registered:
                                t.missing[register] = (f"run {run.stem} has no registered rows: "
                                                       f"{run.unregistered_reason}")
                            elif sid not in run_seeds:
                                t.missing[register] = f"run {run.stem} did not run seed {sid}"
                            else:
                                cid, why = w2._conversation(run, sid, layout.arms[(speaker, register)])
                                t.conversations[register] = cid
                                if why:
                                    t.missing[register] = why
                        triples.append(t)
    return triples


# ------------------------------------------------------------------ dimensions and contrasts


def check_dimension(kind: str, key: str, runs: Sequence[Any], index: w2.RowIndex, plan: Plan,
                    tiers: tuple[str, ...]) -> tuple[w2.DimensionCheck, dict[str, int]]:
    """Wave 2's dimension check, on the rows under the digest the plan pins for this dimension only (tier rows: the
    plan's rubric_digest; outcome rows: its prompt_digests entry). Rows under any other digest are counted per run and
    are not comparable where they fall, by name (rules: no pooling across judge prompts or rubric digests)."""
    pin = plan.rubric_digest if kind == "tier" else plan.prompt_digests.get(key)
    filtered: dict[tuple[str, str, str], dict[int, list[dict]]] = {}
    outside: Counter[str] = Counter()
    for (conv, k, kk), cell in index.final.items():
        if (k, kk) != (kind, key):
            continue
        for ex, rows in cell.items():
            kept = [r for r in rows if r.get("prompt_file_digest") == pin]
            outside[index.run_of[conv]] += len(rows) - len(kept)
            if kept:
                filtered.setdefault((conv, k, kk), {})[ex] = kept
    check = w2.check_dimension(kind, key, runs, w2.RowIndex(filtered, index.run_of, {}), pin or "", tiers)
    wave2_pin = w2.POOLING_PROMPT_DIGESTS.get(key) if kind == "outcome" else None
    if pin is None:
        check.pooled = False
        check.reasons.append(f"the plan pins no digest for {kind}:{key}")
    elif wave2_pin is not None and wave2_pin != pin:
        check.pooled = False
        check.reasons.append(f"wave 2's pooling digest for {key} is {wave2_pin}, not the plan's {pin}")
    return check, {stem: n for stem, n in sorted(outside.items()) if n}


@dataclass(frozen=True)
class Spec:
    """One contrast: its measure, the conversations that must be comparable at an exchange, the window and floor, and
    the seeds it covers (None: every plan seed)."""
    name: str
    section: str
    measure: w2.Measure
    registers: tuple[str, ...]
    window: w2.Window
    seeds: frozenset[str] | None
    withhold_register_in_coverage: bool = False


def contrast_specs(plan: Plan) -> tuple[list[Spec], dict[str, str]]:
    """Every contrast the plan computes per target, and those that cannot be computed, by name with the reason. The
    leave-one-scenario-out and each-mechanism sensitivities reuse the primary contrast's triples."""
    pw = plan.windows[plan.primary_window]
    two = (COLLOQUIAL, CLINICAL)
    specs = [Spec("primary", "9.2", plan.primary_measure, two, pw, None),
             Spec("decomposition", "9.4", plan.primary_measure, REGISTERS, pw,
                  frozenset(plan.sets[plan.decomposition_set])),
             Spec("exchanges_6_10", "9.5", plan.primary_measure, two, plan.windows[plan.late_window], None)]
    not_computable: dict[str, str] = {}
    for s in plan.sensitivity:
        if s.name in SENSITIVITY_RULES:
            continue
        seeds = None
        if s.mechanism is not None:
            seeds = frozenset(plan.mechanisms[s.mechanism])
            if not seeds:
                not_computable[f"sensitivity:{s.name}"] = (f"mechanism {s.mechanism} has no seed in the plan, so "
                                                           f"{s.name} is not computable")
                continue
        specs.append(Spec(f"sensitivity:{s.name}", "9.6", s.measure, two, plan.windows[s.window], seeds))
    for name in plan.family:
        seeds = frozenset(plan.restricted[name]) if name in plan.restricted else None
        specs.append(Spec(f"exploratory:{name}", "9.6", _measure_of(name), two, pw, seeds, True))
    for name, seed_ids in plan.restricted.items():
        if name in plan.family:
            continue
        if not seed_ids:
            not_computable[f"restricted:{name}"] = f"no seed is listed for {name}, so it is not computable"
            continue
        specs.append(Spec(f"restricted:{name}", "9.6", _measure_of(name), two, pw, frozenset(seed_ids), True))
    return specs, not_computable


def in_scope(spec: Spec, triple: Triple) -> bool:
    return spec.seeds is None or triple.seed_id in spec.seeds


@dataclass
class Reading:
    """One judge's rows over the plan's triples: the index, the dimension checks, the scales and every contrast's
    standings. The judge of record's reading is the registered one; a secondary judge's is never mixed with it."""
    judge_model: str | None
    index: w2.RowIndex
    dimensions: dict[tuple[str, str], w2.DimensionCheck]
    outside_pin: dict[tuple[str, str], dict[str, int]]
    scales: dict[str, w2.Scale]
    refused_measures: dict[str, str]
    standings: dict[str, list[w2.Standing]]
    refused_specs: dict[str, str]


def all_measures(plan: Plan, specs: Sequence[Spec]) -> list[w2.Measure]:
    seen: dict[str, w2.Measure] = {}
    for m in [s.measure for s in specs] + [_measure_of(n) for n in plan.coverage_only]:
        seen.setdefault(m.name, m)
    return list(seen.values())


def make_reading(judge_model: str | None, runs: Sequence[Any], triples: Sequence[Triple], plan: Plan,
                 specs: Sequence[Spec], tiers: tuple[str, ...]) -> Reading:
    index = w2.index_rows(runs, triples)
    dims: dict[tuple[str, str], w2.DimensionCheck] = {}
    outside: dict[tuple[str, str], dict[str, int]] = {}
    for m in all_measures(plan, specs):
        if (m.kind, m.key) not in dims:
            dims[(m.kind, m.key)], outside[(m.kind, m.key)] = check_dimension(m.kind, m.key, runs, index, plan, tiers)
    scales, refused = w2.measure_scales(dims, [s.measure for s in specs])
    standings: dict[str, list[w2.Standing]] = {}
    refused_specs: dict[str, str] = {}
    for spec in specs:
        if spec.measure.name in refused:
            refused_specs[spec.name] = refused[spec.measure.name]
            continue
        standings[spec.name] = [w2.standing(t, spec.registers, scales[spec.measure.name], spec.window, index)
                                for t in triples if t.landed and in_scope(spec, t)]
    return Reading(judge_model, index, dims, outside, scales, refused, standings, refused_specs)


# ------------------------------------------------------------------ the secondary judge


@dataclass
class SecondaryRun:
    """A landed run's rows under the secondary judge, from its re-grade directory; empty, with the reason, without one.
    Duck-types the run fields wave 2's row index and dimension check read (stem, rows, registry)."""
    stem: str
    rows: list[dict]
    registry: w2.RegistryVersion | None
    registry_problem: str | None
    provenance: dict[str, Any]


def secondary_runs(runs: Sequence[RunInput], spec: str, rejudge_root: Path,
                   seeds: Mapping[str, dict]) -> list[SecondaryRun]:
    out = []
    for run in runs:
        if not run.registered:
            continue
        out_dir = Path(rejudge_root) / rejudge.judge_slug(spec) / run.stem
        got = read_regrade(out_dir, run.run_dir.parent, spec, run.manifest, seeds, run.registry)
        if got is None:
            out.append(SecondaryRun(run.stem, [], run.registry, run.registry_problem,
                                    {"run_stem": run.stem, "rows_from": None,
                                     "reason": f"no re-grade by {spec} at {w2._display(out_dir)}"}))
        elif got[1]["incomplete"] is not None:
            out.append(SecondaryRun(run.stem, [], run.registry, run.registry_problem,
                                    {"run_stem": run.stem, "rows_from": got[1],
                                     "reason": f"the re-grade by {spec} is incomplete: {got[1]['incomplete']}"}))
        else:
            rows, info = got
            out.append(SecondaryRun(run.stem, rows, run.registry, run.registry_problem,
                                    {"run_stem": run.stem, "rows_from": info, "reason": None}))
    return out


def secondary_spec_problem(spec: str, plan: Plan) -> str | None:
    """Why `spec` cannot be the secondary judge: it is the judge of record under any spelling, or names no judge."""
    if plan.judge_model is None:
        return "judge.judge_model is null, so there is no judge of record to set a secondary judge beside"
    try:
        rejudge.judge_slug(spec)
        same = rejudge.same_judge(spec, plan.judge_model)
    except rejudge.RejudgeError as exc:
        return f"--secondary-judge {spec!r}: {exc}"
    if same:
        return f"--secondary-judge {spec!r} is the judge of record {plan.judge_model!r}; a secondary judge is another"
    return None


def align_secondary(record: Reading, secondary: Reading,
                    specs: Sequence[Spec]) -> tuple[dict[str, list[w2.Standing]], dict[str, Any], bool]:
    """The secondary's standings on exactly the record's comparable exchanges, and the coverage counts: per contrast,
    the record's comparable exchanges, how many of them the secondary's rows do not make comparable (with the reasons,
    by problem only, never by register), and how many exchanges only the secondary makes comparable (reported, not
    used). The third value is whether the secondary covers every record exchange (else the caller refuses)."""
    aligned: dict[str, list[w2.Standing]] = {}
    counts: dict[str, Any] = {}
    complete = True
    for spec in specs:
        if spec.name in record.refused_specs:
            continue
        if spec.name in secondary.refused_specs:
            counts[spec.name] = {"status": "refused", "reason": secondary.refused_specs[spec.name]}
            complete = False
            continue
        scale = secondary.scales[spec.measure.name]
        m = scale.measure
        reasons: Counter[str] = Counter()
        triples_short: set[str] = set()
        record_n = 0
        only_secondary = 0
        sts = []
        own = {s.triple.triple_id: s for s in secondary.standings[spec.name]}
        for st in record.standings[spec.name]:
            record_n += len(st.comparable)
            for ex in st.comparable:
                for register in spec.registers:
                    cell = secondary.index.final.get((st.triple.conversations[register], m.kind, m.key), {})
                    problem = w2.side_problem(cell.get(ex), scale)
                    if problem:
                        reasons[problem] += 1
                        triples_short.add(st.triple.triple_id)
            mine = own.get(st.triple.triple_id)
            if mine is not None:
                only_secondary += len(set(mine.comparable) - set(st.comparable))
            sts.append(w2.Standing(st.triple, st.enters, st.reason, st.comparable, st.exclusions,
                                   st.missing_register))
        short = sum(reasons.values())
        complete = complete and short == 0
        counts[spec.name] = {"status": "covered" if short == 0 else "not covered",
                             "record_comparable_exchanges": record_n,
                             "record_exchange_sides_not_comparable_under_secondary": short,
                             "triples_affected": len(triples_short),
                             "reasons": dict(sorted(reasons.items())),
                             "exchanges_comparable_under_secondary_only_not_used": only_secondary}
        aligned[spec.name] = sts
    return aligned, counts, complete


# ------------------------------------------------------------------ preparation (shared by both modes)


@dataclass
class Prepared:
    plan: Plan
    seeds_path: Path
    seeds_sha256: str
    rubric_path: Path
    rubric_digest: str
    loaded_registry: Path
    rejudge_root: Path
    runs: list[RunInput]
    skipped: list[dict[str, str]]
    layouts: dict[str, w2.SeedLayout]
    triples: list[Triple]
    specs: list[Spec]
    not_computable: dict[str, str]
    record: Reading
    secondary_judge: str | None = None
    secondary_runs: list[SecondaryRun] = field(default_factory=list)
    secondary: Reading | None = None
    secondary_standings: dict[str, list[w2.Standing]] = field(default_factory=dict)
    secondary_coverage: dict[str, Any] = field(default_factory=dict)
    secondary_complete: bool = True


def prepare(run_paths: Sequence[Path] | None = None, *, runs_dir: Path = RUNS_DIR, plan_path: Path = PLAN_FILE,
            seeds_path: Path | None = None, rubric_path: Path = ADVICE_RUBRIC, registry_path: Path = OUTCOME_REGISTRY,
            registry_versions: Sequence[Path] = (), repo_root: Path = ROOT, rejudge_root: Path = REJUDGE_ROOT,
            secondary_judge: str | None = None) -> Prepared:
    """Everything both modes need, and nothing that ranks a value."""
    plan = load_plan(plan_path)
    seeds_path = Path(seeds_path) if seeds_path is not None else plan.seed_file
    try:
        seed_set = load_seed_file(seeds_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnalysisRefusal(f"seed file {seeds_path} could not be loaded: {exc}") from exc
    layouts = plan_layouts(plan, seed_set.seeds)
    try:
        rubric = judge_runner.load_rubric(rubric_path)
        rdigest = judge_runner.rubric_digest(rubric)
        tiers = tuple(t["id"] for t in rubric["tiers"])
        flag_ids = {f["id"] for f in rubric.get("flags", [])}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnalysisRefusal(f"rubric file {rubric_path} could not be loaded: {exc}") from exc
    if list(tiers) != sorted(plan.tier_rank, key=plan.tier_rank.__getitem__):
        raise AnalysisRefusal(f"the rubric {rubric_path} orders its tiers {list(tiers)}, but the plan's "
                              f"outcome.tier_rank orders them {sorted(plan.tier_rank, key=plan.tier_rank.__getitem__)}")
    for name in plan.family:
        m = _measure_of(name)
        if m.flag is not None and m.flag not in flag_ids:
            raise AnalysisRefusal(f"the rubric {rubric_path} declares no flag {m.flag!r}")
    if secondary_judge is not None:
        problem = secondary_spec_problem(secondary_judge, plan)
        if problem:
            raise AnalysisRefusal(problem)
    try:
        resolver = w2.RegistryResolver(Path(registry_path), extra=registry_versions, repo_root=repo_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnalysisRefusal(f"outcome registry inputs could not be loaded: {exc}") from exc
    runs, skipped = load_runs(run_paths, runs_dir, plan, seed_set.seeds, resolver, rejudge_root)
    triples = build_triples(plan, layouts, runs)
    specs, not_computable = contrast_specs(plan)
    record = make_reading(plan.judge_model, runs, triples, plan, specs, tiers)
    prep = Prepared(plan, Path(seeds_path), seed_set.file_sha256, Path(rubric_path), rdigest, Path(registry_path),
                    Path(rejudge_root), runs, skipped, layouts, triples, specs, not_computable, record)
    if secondary_judge is not None:
        prep.secondary_judge = secondary_judge
        prep.secondary_runs = secondary_runs(runs, secondary_judge, rejudge_root, seed_set.seeds)
        prep.secondary = make_reading(secondary_judge, prep.secondary_runs, triples, plan, specs, tiers)
        prep.secondary_standings, prep.secondary_coverage, prep.secondary_complete = align_secondary(
            record, prep.secondary, specs)
    return prep


# ------------------------------------------------------------------ coverage (both modes; ranks nothing)


def missing_epochs(prep: Prepared) -> dict[str, dict[int, dict[str, Any]]]:
    """Per target, each campaign epoch without a landed run, with its fires (live and voided) and why."""
    landed = {r.fire.journal_nonce for r in prep.runs}
    out: dict[str, dict[int, dict[str, Any]]] = {}
    for target in prep.plan.targets:
        for epoch in range(1, prep.plan.epochs + 1):
            live = prep.plan.live_fire(target.id, epoch)
            if live is not None and live.journal_nonce in landed:
                continue
            voided = [f.journal_nonce for f in prep.plan.fires.values()
                      if f.target == target.id and f.campaign_epoch == epoch and f.voided is not None]
            out.setdefault(target.id, {})[epoch] = {
                "live_fire": live.journal_nonce if live else None, "voided_fires": voided,
                "reason": (f"fire {live.journal_nonce} has not landed" if live else
                           "no fire recorded" + (f"; voided: {voided}" if voided else ""))}
    return out


def contrast_coverage(prep: Prepared) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in prep.specs:
        head = {"section": spec.section, "measure": spec.measure.name, "instrument": w2.instrument(spec.measure),
                "registers": list(spec.registers), "window": spec.window.name, "floor": spec.window.floor,
                "seeds": None if spec.seeds is None else sorted(spec.seeds)}
        if spec.name in prep.record.refused_specs:
            out[spec.name] = {**head, "status": "refused", "reason": prep.record.refused_specs[spec.name]}
            continue
        by_target: dict[str, Any] = {}
        for target in prep.plan.targets:
            sts = [s for s in prep.record.standings[spec.name] if s.triple.target == target.id]
            if spec.withhold_register_in_coverage:
                reasons = Counter(p for s in sts for pairs in s.exclusions.values() for _reg, p in pairs)
                excluded = [{"triple": s.triple.triple_id,
                             "reason": "a conversation of the triple is missing (triples names it)"
                             if s.missing_register else s.reason} for s in sts if not s.enters]
            else:
                reasons = Counter(r for s in sts for rs in s.excluded_exchanges.values() for r in rs)
                excluded = [{"triple": s.triple.triple_id, "reason": s.reason} for s in sts if not s.enters]
            by_target[target.id] = {"triples_in_scope": len(sts), "triples_entering": sum(s.enters for s in sts),
                                    "triples_excluded": excluded,
                                    "exchange_exclusion_reasons": dict(sorted(reasons.items()))}
        out[spec.name] = {**head, "status": "computable", "register_labels_withheld":
                          spec.withhold_register_in_coverage, "by_target": by_target}
    for name, reason in prep.not_computable.items():
        out[name] = {"status": "not computable", "reason": reason}
    return out


def coverage(prep: Prepared) -> dict[str, Any]:
    """Coverage alone (rules[0]): runs, triples per target, exclusions with reasons, digests. Nothing here ranks a value
    or counts values by wording."""
    plan = prep.plan
    rubric_matches = prep.rubric_digest == plan.rubric_digest
    triples_by_target = {}
    for target in plan.targets:
        mine = [t for t in prep.triples if t.target == target.id]
        landed = [t for t in mine if t.landed]
        triples_by_target[target.id] = {
            "role": target.role, "fixed_by_plan": plan.final_triples_per_target, "expected": len(mine),
            "landed": len(landed), "not_landed": [t.triple_id for t in mine if not t.landed],
            "landed_with_missing_conversations": [{"triple": t.triple_id, "missing": t.missing}
                                                  for t in landed if t.missing]}
    dims = {}
    for (kind, key), d in prep.record.dimensions.items():
        dims[f"{kind}:{key}"] = {**d.record(), "pinned_digest": plan.rubric_digest if kind == "tier"
                                 else plan.prompt_digests.get(key),
                                 "rows_outside_pinned_digest_by_run": prep.record.outside_pin[(kind, key)]}
    doc: dict[str, Any] = {
        "plan": {"path": w2._display(plan.path), "sha256": plan.sha256, "approved": plan.approved,
                 "judge_model": plan.judge_model, "targets": {t.id: {"role": t.role, "name": t.name,
                                                                     "target_specs": list(t.target_specs)}
                                                              for t in plan.targets},
                 "fires": {n: {"target": f.target, "campaign_epoch": f.campaign_epoch, "voided": f.voided}
                           for n, f in plan.fires.items()},
                 "regrade_fires": {n: {"source_runs": list(f.source_runs), "target": f.target,
                                       "campaign_epoch": f.campaign_epoch, "voided": f.voided}
                                   for n, f in plan.regrade_fires.items()},
                 "realism_gate_selection": plan.realism_gate_selection},
        "seed_file": {"path": w2._display(prep.seeds_path), "sha256": prep.seeds_sha256},
        "rubric": {"path": w2._display(prep.rubric_path), "digest": prep.rubric_digest,
                   "digest_pinned_by_plan": plan.rubric_digest, "matches_plan": rubric_matches},
        "prompt_digests_pinned_by_plan": dict(plan.prompt_digests),
        "loaded_outcome_registry": {"path": w2._display(prep.loaded_registry),
                                    "sha256": sha256_file(prep.loaded_registry)},
        "runs": [r.provenance for r in prep.runs],
        "runs_not_analysed": prep.skipped,
        "runs_without_registered_rows": {r.stem: r.unregistered_reason for r in prep.runs if not r.registered},
        "epochs_not_landed": {t: {str(e): v for e, v in eps.items()} for t, eps in missing_epochs(prep).items()},
        "rows_not_read": prep.record.index.not_read,
        "dimensions": dims,
        "triples": triples_by_target,
        "contrasts": contrast_coverage(prep),
    }
    if prep.secondary_judge is not None:
        doc["secondary_judge"] = {"judge_model": prep.secondary_judge,
                                  "runs": [s.provenance for s in prep.secondary_runs],
                                  "covers_the_record_exchanges": prep.secondary_complete,
                                  "by_contrast": prep.secondary_coverage}
    return doc


# ------------------------------------------------------------------ statistics on one reading (only under --final)


def describe(ds: Sequence[w2.TripleD]) -> dict[str, Any]:
    """Descriptive counts with no test (the plan's descriptive analyses): triples with D < 0, > 0 and = 0, and the mean
    of D."""
    neg = sum(d.sign < 0 for d in ds)
    pos = sum(d.sign > 0 for d in ds)
    return {"test": "none (descriptive)", "triples": len(ds), "negative": neg, "positive": pos,
            "tied": len(ds) - neg - pos, "tied_triples": [d.triple_id for d in ds if d.sign == 0],
            "mean_D": float(sum((d.d for d in ds), Fraction(0)) / len(ds)) if ds else None}


def statement_row(primary: Mapping[str, Any], gate: Mapping[str, Any], means: Mapping[str, float], *,
                  planned_scenarios: int, target: Target, statements: Mapping[str, dict]) -> dict[str, Any]:
    """The row of 9.8's table the results select for one target, with its text rendered with the target's name.

    - no non-tied triple: "not_computable" (row 4 presumes a test that ran);
    - primary p >= alpha: row4;
    - primary significant and the gate significant in the opposite direction: "no_prespecified_row";
    - primary significant with D mostly negative: row1 when the gate is significant in the same direction, else row2;
    - primary significant with D mostly positive: row3, which follows the rule of row1 or row2 (`rule_of`) and has no
      sentence in the plan, so none is rendered.
    A gate that ran on fewer scenarios than the plan's leaves the row computed and marks it not selectable as
    registered, since the table was fixed for all of them."""
    direction = primary["direction"]
    gate_same = bool(gate["significant"]) and gate["direction"] == direction
    gate_opposite = bool(gate["significant"]) and gate["direction"] not in (direction, "none")
    not_selectable: list[str] = []
    rule_of = None
    if primary["non_tied"] == 0:
        row = "not_computable"
        not_selectable.append("no non-tied triple entered the primary contrast, so no sign test ran")
    elif not primary["significant"]:
        row = "row4"
    elif gate_opposite:
        row = "no_prespecified_row"
        not_selectable.append(f"the scenario gate is significant in the {gate['direction']} direction, opposite to "
                              f"the primary test's {direction}; 9.8's table has no statement for that")
    else:
        base = "row1" if gate_same else "row2"
        row, rule_of = (base, None) if direction == "negative" else ("row3", base)
    if gate["scenarios"] < planned_scenarios:
        not_selectable.append(f"the scenario gate ran on {gate['scenarios']} of the plan's {planned_scenarios} "
                              f"scenarios; the table was fixed for all {planned_scenarios}")
    sign = -1 if direction == "negative" else 1 if direction == "positive" else 0
    carrying = sorted(s for s, m in means.items() if sign and (m > 0) - (m < 0) == sign)
    entry = statements[row]
    return {"row_id": row, "rule_of": rule_of, "table": "docs/petri_wave3_design.md section 9.8 (plan statements)",
            "target": target.id, "target_name": target.name, "text": entry["text"],
            "rendered": entry["text"].replace(TARGET_PLACEHOLDER, target.name) if row in RENDERED_ROWS else None,
            "also": entry.get("also"), "selectable_as_registered": not not_selectable,
            "not_selectable_reasons": not_selectable, "primary_significant": primary["significant"],
            "primary_direction": direction, "primary_non_tied": primary["non_tied"],
            "gate_significant": gate["significant"], "gate_direction": gate["direction"],
            "gate_same_direction": gate_same, "gate_scenarios": gate["scenarios"],
            "planned_scenarios": planned_scenarios, "scenarios_with_mean_in_primary_direction": carrying}


def decomposition_block(ds: Mapping[str, Sequence[w2.TripleD]], plan: Plan, label: str) -> dict[str, Any]:
    """9.4's three exact sign tests, Holm-corrected together, and the statement they permit (wave 2's rule, which is
    9.8's), with 9.8's text."""
    tests = {k: w2.sign_test(ds.get(k, []), plan.alpha) for k in ("style", "vocabulary", "paired_difference")}
    adjusted = w2.holm({k: (v["p"] if v["non_tied"] else None) for k, v in tests.items()}, plan.alpha)
    statement = w2.decomposition_statement(tests["style"], tests["vocabulary"], tests["paired_difference"], adjusted)
    entry = plan.statements["decomposition"][statement["statement_id"]]
    statement.update({"section": "docs/petri_wave3_design.md section 9.8 (plan statements.decomposition)",
                      "text": entry["text"],
                      "added": entry.get("add_if_vocabulary_significant_and_negative")
                      if statement["vocabulary_also_lowered"] else None})
    return {"label": label, "exchanges": "three-way complete", "tests": tests, "holm": adjusted,
            "statement": statement}


def pairwise(st: w2.Standing, spec: Spec, scale: w2.Scale, index: w2.RowIndex) -> dict[str, w2.TripleD]:
    """D for one entering triple: D(colloquial, clinical), and for the decomposition D(style), D(vocabulary) (which sum
    to it exactly on its three-way complete exchanges) and their paired difference."""
    if spec.registers != REGISTERS:
        return {"whole": w2.pairwise_d(st, COLLOQUIAL, CLINICAL, scale, index)}
    style = w2.pairwise_d(st, COLLOQUIAL, CAREFUL_LAY, scale, index)
    vocab = w2.pairwise_d(st, CAREFUL_LAY, CLINICAL, scale, index)
    whole = w2.pairwise_d(st, COLLOQUIAL, CLINICAL, scale, index)
    if style.total + vocab.total != whole.total:
        raise ArithmeticError(f"{st.triple.triple_id}: D(style) + D(vocabulary) != D(colloquial, clinical)")
    diff = w2.TripleD(whole.triple_id, whole.scenario, whole.speaker, whole.scenario_set, None,
                      style.total - vocab.total, whole.n)
    return {"style": style, "vocabulary": vocab, "whole": whole, "paired_difference": diff}


def value_counts_by_wording(prep: Prepared, reading: Reading, target: str, key: str) -> dict[str, Any]:
    """A coverage-only outcome's values per wording over the primary window (9.6): each register's final rows under
    the plan's pinned digest, one per exchange, counted by value; an exchange without exactly one such row is counted
    with its reason. No rank and no D: these values carry no order."""
    pin = prep.plan.prompt_digests.get(key)
    window = prep.plan.windows[prep.plan.primary_window]
    out: dict[str, Counter[str]] = {r: Counter() for r in REGISTERS}
    for t in prep.triples:
        if t.target != target or not t.landed:
            continue
        for register in REGISTERS:
            conv = t.conversations[register]
            if conv is None:
                out[register]["(no conversation)"] += len(window.exchanges)
                continue
            cell = reading.index.final.get((conv, "outcome", key), {})
            for ex in window.exchanges:
                rows = [r for r in cell.get(ex, []) if r.get("prompt_file_digest") == pin]
                if len(rows) != 1:
                    out[register]["(no row under the pinned digest)" if not rows else "(duplicate rows)"] += 1
                elif rows[0].get("not_applicable_reason") or rows[0].get("value") == w2.NOT_APPLICABLE:
                    out[register]["(not applicable)"] += 1
                elif rows[0].get("value") is None:
                    out[register]["(null)"] += 1
                else:
                    out[register][str(rows[0]["value"])] += 1
    return {"pinned_digest": pin, "window": window.name,
            "by_wording": {r: dict(sorted(c.items())) for r, c in out.items()}}


def target_block(prep: Prepared, reading: Reading, standings: Mapping[str, Sequence[w2.Standing]],
                 target: Target, ds: Mapping[str, Mapping[str, list[w2.TripleD]]], *, seed: int,
                 resamples: int) -> dict[str, Any]:
    """Every per-target number of 9.2 (9.3 for a comparison target), 9.5 and 9.6."""
    plan = prep.plan
    mine = ds[target.id]
    planned = len(plan.scenarios)
    primary = mine["primary"]
    primary_test = w2.sign_test(primary, plan.alpha)
    means = w2.scenario_means(primary)
    gate = w2.sign_flip_test(means, plan.alpha)
    gate["planned_scenarios"] = planned
    gate["missing_scenarios"] = w2.missing_scenarios(
        plan, means, [t for t in prep.triples if t.target == target.id],
        [s for s in standings["primary"] if s.triple.target == target.id])
    loso: dict[str, Any] = {}
    for scenario in plan.scenarios:
        if scenario not in means:
            loso[scenario] = {"status": "not computable",
                              "reason": "no triple of this scenario entered the primary contrast; leaving it out "
                                        "would repeat the full test (see scenario_gate.missing_scenarios)"}
            continue
        rerun = w2.sign_test([d for d in primary if d.scenario != scenario], plan.alpha)
        loso[scenario] = {k: rerun[k] for k in ("triples", "negative", "positive", "tied", "p", "direction",
                                                "significant")}
    effect = {
        "over": "the triples entering the primary contrast, ties included (ties leave sign tests, not means)",
        "interval_to_quote": "scenario_t_interval; the bootstrap is the labelled secondary",
        "triples": len(primary),
        "proportion_D_negative": (sum(d.sign < 0 for d in primary) / len(primary)) if primary else None,
        "median_D": float(statistics.median([d.d for d in primary])) if primary else None,
        "mean_D": float(sum((d.d for d in primary), Fraction(0)) / len(primary)) if primary else None,
        "scenario_t_interval": w2.scenario_t_interval(list(means.values()), planned_scenarios=planned),
        "bootstrap": w2.bootstrap_mean_interval([float(d.d) for d in primary], seed=seed, resamples=resamples),
        "note": "AGENTS.md: cite the direction, not the magnitude",
    }
    block: dict[str, Any] = {
        "target": target.id, "name": target.name, "role": target.role,
        "primary_sign_test": primary_test, "scenario_gate": gate, "leave_one_scenario_out": loso,
        "effect_size": effect,
    }
    block["exchanges_6_10"] = _test_or_refusal(reading, "exchanges_6_10", mine, plan)
    sensitivity: dict[str, Any] = {}
    for s in plan.sensitivity:
        name = f"sensitivity:{s.name}"
        if s.name == "leave_one_scenario_out":
            sensitivity[s.name] = {"see": f"targets.{target.id}.leave_one_scenario_out"}
        elif s.name == "each_mechanism_alone":
            sensitivity[s.name] = {
                mech: ({"status": "absent", "reason": f"mechanism {mech} has no seed in the plan"} if not seeds else
                       {**describe([d for d in primary if d.scenario in seeds]),
                        "scenario_means": {sc: float(m) for sc, m in means.items() if sc in seeds}})
                for mech, seeds in plan.mechanisms.items()}
        elif name in prep.not_computable:
            sensitivity[s.name] = {"status": "not computable", "reason": prep.not_computable[name]}
        elif s.mechanism is not None:
            sensitivity[s.name] = ({"status": "refused", "reason": reading.refused_specs[name]}
                                   if name in reading.refused_specs else
                                   {"mechanism": s.mechanism, **describe(mine[name])})
        else:
            sensitivity[s.name] = _test_or_refusal(reading, name, mine, plan)
    block["sensitivity"] = sensitivity
    tests: dict[str, Any] = {}
    pvals: dict[str, float | None] = {}
    for name in plan.family:
        spec_name = f"exploratory:{name}"
        if spec_name in reading.refused_specs:
            tests[name] = {"status": "not run", "instrument": w2.instrument(_measure_of(name)),
                           "reason": reading.refused_specs[spec_name]}
            pvals[name] = None
        else:
            tests[name] = {"status": "exploratory", "instrument": w2.instrument(_measure_of(name)),
                           **w2.sign_test(mine[spec_name], plan.alpha)}
            pvals[name] = tests[name]["p"] if tests[name]["non_tied"] else None
    block["exploratory"] = {"label": "exploratory: no headline rests on any of them", "tests": tests,
                            "holm": w2.holm(pvals, plan.alpha)}
    restricted = {}
    for name in plan.restricted:
        if name in plan.family:
            continue
        spec_name = f"restricted:{name}"
        if spec_name in prep.not_computable:
            restricted[name] = {"status": "not computable", "reason": prep.not_computable[spec_name]}
        elif spec_name in reading.refused_specs:
            restricted[name] = {"status": "refused", "reason": reading.refused_specs[spec_name]}
        else:
            restricted[name] = {"seeds": list(plan.restricted[name]), **describe(mine[spec_name])}
    block["restricted_outcomes_descriptive"] = restricted
    # each table only over rows its dimension check pooled: a dimension refused (registry definitions that differ
    # across the runs, an unresolved registry version, no row under the pinned digest) is reported refused, by name,
    # never counted over rows that are not one measurement
    coverage_only: dict[str, Any] = {}
    for name in plan.coverage_only:
        check = reading.dimensions[("outcome", name)]
        coverage_only[name] = ({"status": "refused", "reason": f"dimension outcome:{name} refused: "
                                + "; ".join(check.reasons)} if not check.pooled else
                               {"status": "coverage only: no order, so no D",
                                **value_counts_by_wording(prep, reading, target.id, name)})
    block["coverage_only"] = coverage_only
    return block


def _test_or_refusal(reading: Reading, name: str, mine: Mapping[str, list[w2.TripleD]], plan: Plan) -> dict[str, Any]:
    if name in reading.refused_specs:
        return {"status": "refused", "reason": reading.refused_specs[name]}
    return w2.sign_test(mine[name], plan.alpha)


def analysis_sections(prep: Prepared, reading: Reading, standings: Mapping[str, Sequence[w2.Standing]], *,
                      seed: int, resamples: int) -> dict[str, Any]:
    """Every test, interval and statement on one judge's reading, after final or bound-secondary guards."""
    plan = prep.plan
    ds: dict[str, dict[str, list[w2.TripleD]]] = {t.id: {} for t in plan.targets}
    per_triple: dict[str, dict[str, Any]] = {t.triple_id: {**t.label(), "contrasts": {}} for t in prep.triples}
    for spec in prep.specs:
        if spec.name in reading.refused_specs:
            continue
        scale = reading.scales[spec.measure.name]
        for target in plan.targets:
            ds[target.id].setdefault(spec.name, [])
        for st in standings[spec.name]:
            rec = st.record()
            if st.enters:
                parts = pairwise(st, spec, scale, reading.index)
                if spec.name == "decomposition":
                    for part in ("style", "vocabulary", "paired_difference"):
                        ds[st.triple.target].setdefault(f"decomposition:{part}", []).append(parts[part])
                        rec[part] = {"D": float(parts[part].d), "D_exact": str(parts[part].d)}
                    rec["colloquial_clinical_on_three_way_complete"] = w2._d_record(parts["whole"])
                else:
                    ds[st.triple.target][spec.name].append(parts["whole"])
                    rec.update(w2._d_record(parts["whole"]))
            per_triple[st.triple.triple_id]["contrasts"][spec.name] = rec
    blocks = {t.id: target_block(prep, reading, standings, t, ds, seed=seed, resamples=resamples)
              for t in plan.targets}
    anchor = plan.anchor
    comparison = plan.comparison

    def p_of(test: Mapping[str, Any]) -> float | None:
        return test["p"] if "p" in test and test.get("non_tied") else None

    holm_primary = w2.holm({t.id: p_of(blocks[t.id]["primary_sign_test"]) for t in comparison}, plan.alpha)
    for target in plan.targets:
        block = blocks[target.id]
        primary = block["primary_sign_test"]
        adjusted = holm_primary.get(target.id)
        verdict = primary if adjusted is None else {**primary, "significant": adjusted["significant_after_holm"]}
        block["statement"] = statement_row(
            verdict, block["scenario_gate"], block["scenario_gate"]["scenario_means"],
            planned_scenarios=len(plan.scenarios), target=target, statements=plan.statements["primary"])
        block["statement"].update({
            "primary_significance": "unadjusted anchor test" if adjusted is None else "Holm across comparison targets",
            "primary_p": primary["p"], "primary_p_holm": None if adjusted is None else adjusted["p_holm"],
            "primary_significant_unadjusted": primary["significant"]})
    section_9_2 = {"target": anchor.id, "primary_sign_test": blocks[anchor.id]["primary_sign_test"],
                   "scenario_gate": blocks[anchor.id]["scenario_gate"], "statement": blocks[anchor.id]["statement"],
                   "see": f"targets.{anchor.id}"}
    section_9_3 = {
        "targets": [t.id for t in comparison],
        "holm_primary": holm_primary,
        "gates": {t.id: {k: blocks[t.id]["scenario_gate"][k] for k in ("p", "direction", "significant", "scenarios")}
                  for t in comparison},
        "between_targets": {"test": "none: descriptive only, side by side",
                            "by_target": {t.id: {"proportion_D_negative":
                                                 blocks[t.id]["effect_size"]["proportion_D_negative"],
                                                 "scenario_means": blocks[t.id]["scenario_gate"]["scenario_means"]}
                                          for t in plan.targets}},
    }
    if "decomposition" in reading.refused_specs:
        section_9_4: dict[str, Any] = {"status": "refused", "reason": reading.refused_specs["decomposition"]}
    else:
        pooled: dict[str, list[w2.TripleD]] = {}
        for t in plan.targets:
            for part in ("style", "vocabulary", "paired_difference"):
                pooled.setdefault(part, []).extend(ds[t.id].get(f"decomposition:{part}", []))
        section_9_4 = {
            "scenario_set": plan.decomposition_set,
            "registered": decomposition_block({p: ds[anchor.id].get(f"decomposition:{p}", [])
                                               for p in ("style", "vocabulary", "paired_difference")}, plan,
                                              f"registered: the anchor {anchor.id}'s triples"),
            "prespecified_secondary": decomposition_block(pooled, plan, "across targets: every registered target's "
                                                                        "triples pooled (pre-specified secondary)"),
        }
    late = {t.id: blocks[t.id]["exchanges_6_10"] for t in plan.targets}
    section_9_5 = {"anchor": {"target": anchor.id, "correction": "none (one pre-specified secondary)",
                              **late[anchor.id]},
                   "comparison_targets": {t.id: late[t.id] for t in comparison},
                   "holm_comparison": w2.holm({t.id: p_of(late[t.id]) for t in comparison}, plan.alpha)}
    across: dict[str, Any] = {}
    for name in plan.restricted:
        if name in plan.family:
            continue
        spec_name = f"restricted:{name}"
        if spec_name in prep.not_computable or spec_name in reading.refused_specs:
            across[name] = {"status": "not computable",
                            "reason": prep.not_computable.get(spec_name) or reading.refused_specs[spec_name]}
            continue
        triples = [d for t in plan.targets for d in ds[t.id].get(spec_name, [])]
        across[name] = {"label": "across targets: exploratory, uncorrected, reported beside the per-target counts",
                        **w2.sign_test(triples, plan.alpha)}
    section_9_6 = {"restricted_outcomes_across_targets": across,
                   "per_target": {t.id: {k: blocks[t.id][k] for k in ("sensitivity", "exploratory",
                                                                      "restricted_outcomes_descriptive",
                                                                      "coverage_only")} for t in plan.targets}}
    section_9_8 = {"primary": {t.id: blocks[t.id]["statement"] for t in plan.targets},
                   "decomposition_registered": section_9_4.get("registered", {}).get("statement"),
                   "decomposition_across_targets": section_9_4.get("prespecified_secondary", {}).get("statement"),
                   "every_statement_carries": {"text": plan.every_statement_carries,
                                               "judge_of_record": plan.judge_model,
                                               "targets": [t.name for t in plan.targets],
                                               "realism_gate_selection": plan.realism_gate_selection}}
    return {"triples": list(per_triple.values()), "targets": blocks, "section_9_2": section_9_2,
            "section_9_3": section_9_3, "section_9_4": section_9_4, "section_9_5": section_9_5,
            "section_9_6": section_9_6, "section_9_8": section_9_8}


def nominal_agreement_values(prep: Prepared, name: str) -> tuple[tuple[Any, ...] | None, str | None]:
    """Admissible categories from the contributing runs' checked definitions; these are never ordinal ranks."""
    assert prep.secondary is not None
    checks = [r.dimensions[("outcome", name)] for r in (prep.record, prep.secondary)]
    for label, check in zip(("judge of record", "secondary judge"), checks):
        if not check.pooled:
            return None, f"{label} dimension outcome:{name} refused: " + "; ".join(check.reasons)
    definitions = {d for check in checks for d in check.registry_definitions.values()}
    if len(definitions) != 1 or None in definitions or checks[0].pooled_digest != checks[1].pooled_digest:
        return None, f"dimension outcome:{name} has different instruments across judges"
    contributing = set(checks[0].registry_definitions) | set(checks[1].registry_definitions)
    for run in prep.runs:
        if run.stem in contributing and run.registry is not None:
            definition = w2.registry_definition(run.registry.registry, "outcome", name)
            if definition is not None:
                return tuple(definition["values"]), None
    return None, f"dimension outcome:{name} has no resolved contributing registry"


def agreement(prep: Prepared) -> dict[str, Any]:
    """judge.regrade_reported for the secondary judge, including coverage-only categories: over every exchange of every
    landed triple's conversations where both judges have exactly one admissible row under the pinned digest, the exact
    agreement, the within-one agreement (the ordinal tier only) and the directional lean (how often the secondary
    ranked above and below the judge of record). Nominal categories have exact agreement only, never invented ranks."""
    assert prep.secondary is not None
    out: dict[str, Any] = {}
    planned = [m.name for m in all_measures(prep.plan, prep.specs)]
    planned.extend(prep.plan.family)
    planned.extend(prep.plan.restricted)
    for name in dict.fromkeys(planned):
        if name in prep.record.refused_measures:
            out[name] = {"status": "refused", "reason": "judge of record: " + prep.record.refused_measures[name]}
            continue
        nominal = name in prep.plan.coverage_only
        if nominal:
            values, reason = nominal_agreement_values(prep, name)
            if values is None:
                out[name] = {"status": "refused", "reason": reason}
                continue
            # Reuse the digest/value admissibility checks only; Scale.rank is never called for categories.
            rec_scale = sec_scale = w2.Scale(_measure_of(name), values, prep.plan.prompt_digests[name])
        else:
            rec_scale = prep.record.scales.get(name)
            if rec_scale is None:
                out[name] = {"status": "refused", "reason": "no computable contrast for the planned measure"}
                continue
            sec_scale = prep.secondary.scales.get(name)
        if sec_scale is None:
            out[name] = {"status": "refused", "reason": prep.secondary.refused_measures.get(name)}
            continue
        m = rec_scale.measure
        n = exact = within = higher = lower = 0
        for t in prep.triples:
            for conv in t.conversations.values():
                if conv is None:
                    continue
                a = prep.record.index.final.get((conv, m.kind, m.key), {})
                b = prep.secondary.index.final.get((conv, m.kind, m.key), {})
                for ex in range(1, w2.EXCHANGES + 1):
                    if w2.side_problem(a.get(ex), rec_scale) or w2.side_problem(b.get(ex), sec_scale):
                        continue
                    [ra] = rec_scale.current(a[ex])
                    [rb] = sec_scale.current(b[ex])
                    n += 1
                    if nominal:
                        exact += ra["value"] == rb["value"]
                        continue
                    x, y = rec_scale.rank(ra), sec_scale.rank(rb)
                    exact += x == y
                    within += abs(x - y) <= 1
                    higher += y > x
                    lower += y < x
        out[name] = {"instrument": w2.instrument(m), "exchanges_both_admissible": n, "exact_agreement": exact,
                     "within_one": within if m.kind == "tier" and m.flag is None else None,
                     "secondary_ranked_higher": None if nominal else higher,
                     "secondary_ranked_lower": None if nominal else lower}
    return out


# where analysis_sections emits its tests; every other place a test appears is a copy of one of these (section_9_2,
# section_9_3.gates, section_9_5 and section_9_6.per_target copy entries of `targets`)
TEST_ROOTS = ("targets", "section_9_4", "section_9_6.restricted_outcomes_across_targets")


def emitted_tests(sections: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Every test analysis_sections emits, by its path: each object under TEST_ROOTS carrying both a `p` and a
    `direction` (a sign test, a scenario gate, a leave-one-scenario-out rerun, a sensitivity, exploratory or pooled
    test). Descriptive blocks carry no p and are not tests."""
    found: dict[str, Mapping[str, Any]] = {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            if "p" in node and "direction" in node:
                found[path] = node
            for k, v in node.items():
                walk(v, f"{path}.{k}")
    for root in TEST_ROOTS:
        node: Any = sections
        for part in root.split("."):
            node = node.get(part, {}) if isinstance(node, Mapping) else {}
        walk(node, root)
    return found


def directions_hold(record: Mapping[str, Any], secondary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Whether each registered test's direction holds under the secondary judge (judge.regrade_reported): every test
    the judge of record's tables emit (emitted_tests), beside the same test from the secondary's tables, or null when
    the secondary's tables have none there (a contrast refused for it)."""
    sec = emitted_tests(secondary)
    rows = []
    for path, a in emitted_tests(record).items():
        b = sec.get(path, {})
        rows.append({"test": path, "record_direction": a.get("direction"), "secondary_direction": b.get("direction"),
                     "holds": a.get("direction") is not None and a.get("direction") == b.get("direction")})
    return rows


SECONDARY_REASON = "a secondary judge's rows; only the judge of record's select a statement"


def mark_secondary_statements(sections: Mapping[str, Any]) -> None:
    """Mark each primary or decomposition statement, including shared section copies, as non-registered."""
    seen: set[int] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict) or id(node) in seen:
            return
        seen.add(id(node))
        if "row_id" in node or "statement_id" in node:
            node["selectable_as_registered"] = False
            node.setdefault("not_selectable_reasons", []).append(SECONDARY_REASON)
        for value in node.values():
            walk(value)

    walk(sections)


SECONDARY_LABEL = ("secondary: the same tables from a second judge's rows (owner decision Q8, 2026-10-14), on exactly "
                   "the exchanges the judge of record made comparable. Exploratory and disclosure only: it selects no "
                   "statement as registered, and no estimate mixes its rows with the judge of record's")


def final_analysis(prep: Prepared, *, seed: int = DEFAULT_SEED,
                   resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, Any]:
    """The registered analysis on the judge of record's rows and, with a secondary judge, the same tables from its rows
    in their own block. Called only under --final."""
    if "primary" in prep.record.refused_specs:
        raise AnalysisRefusal(f"the primary contrast cannot be computed: {prep.record.refused_specs['primary']}")
    out = analysis_sections(prep, prep.record, prep.record.standings, seed=seed, resamples=resamples)
    out["secondary_judge"] = None
    if prep.secondary is not None:
        out["secondary_judge"] = secondary_report(prep, out, seed=seed, resamples=resamples)
    return out


def secondary_report(prep: Prepared, primary: Mapping[str, Any], *, seed: int,
                     resamples: int) -> dict[str, Any]:
    """Compute only secondary statistics; use the supplied primary tests for direction comparisons."""
    if prep.secondary is None or not prep.secondary_complete:
        raise AnalysisRefusal(f"the secondary judge {prep.secondary_judge}'s rows do not cover the exchanges the "
                              f"judge of record made comparable: " + json.dumps(prep.secondary_coverage))
    secondary = replace(prep.secondary, refused_specs={
        **prep.secondary.refused_specs,
        **{name: f"refused for the judge of record: {why}" for name, why in prep.record.refused_specs.items()
           if name not in prep.secondary.refused_specs}})
    sec = analysis_sections(prep, secondary, prep.secondary_standings, seed=seed, resamples=resamples)
    mark_secondary_statements(sec)
    return {"label": SECONDARY_LABEL, "judge_model": prep.secondary_judge,
            "runs": [s.provenance for s in prep.secondary_runs],
            "coverage": prep.secondary_coverage, "agreement": agreement(prep),
            "registered_test_directions": directions_hold(primary, sec), **sec}


# ------------------------------------------------------------------ provenance and CLI


def plan_commit_problem(path: Path) -> str | None:
    """Why --final may not read this plan, or None: it must be the default plan file, committed unchanged."""
    if Path(path).resolve() != Path(PLAN_FILE).resolve():
        return (f"--final reads only the committed plan {w2._display(PLAN_FILE)}; --plan {path} is another file (a "
                f"changed plan is a dated amendment committed to that file, section 9.9)")
    status = w2.git_status(PLAN_FILE, REPO_ROOT)
    if isinstance(status, str):
        return f"the plan {w2._display(PLAN_FILE)} cannot be shown to be committed: {status}"
    if status:
        return f"the plan {w2._display(PLAN_FILE)} has uncommitted changes ({status}); commit it or restore it"
    return None


def code_files() -> dict[str, Path]:
    """The analysis module and the local modules whose functions rebuild and validate its inputs."""
    return {"script": Path(__file__), "wave2_module": Path(w2.__file__),
            **{module.__name__.rsplit(".", 1)[-1]: Path(module.__file__)
               for module in (framework, judge_runner, manifest, rejudge, seeds, spend)}}


def verified_run_chain_inputs(args: argparse.Namespace, prep: Prepared) -> dict[str, Path]:
    """Verify complete source chains and bind every manifest/artifact they actually inspect."""
    roots = {Path(args.runs_dir).resolve(), *(r.run_dir.parent.resolve() for r in prep.runs)}
    files: dict[str, Path] = {}
    for i, root in enumerate(sorted(roots)):
        chain = root / manifest.CHAIN_FILE
        try:
            lines = [line for line in chain.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not lines:
                raise ValueError("empty chain")
            entries: dict[str, str] = {}
            for line in lines:
                relative, digest = line.rsplit(" ", 1)
                parts = Path(relative).parts
                if (len(parts) != 2 or parts[0] in {".", ".."} or parts[1] != "manifest.json"
                        or Path(relative).is_absolute() or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                        or relative in entries):
                    raise ValueError("malformed or duplicate chain entry")
                entries[relative] = digest
            for run in prep.runs:
                if run.run_dir.parent.resolve() == root and f"{run.stem}/manifest.json" not in entries:
                    raise ValueError(f"chain does not name selected run {run.stem}")
            valid, reason = manifest.verify_chain(root)
            if not valid:
                raise ValueError(reason)
            files[f"run_chain[{i}].chain"] = chain
            for j, relative in enumerate(entries):
                path = root / relative
                record = load_json(path)
                prefix = f"run_chain[{i}].entry[{j}]"
                files[f"{prefix}.manifest"] = path
                for key, value in record["artifacts"].items():
                    if key.endswith("_path") and value:
                        files[f"{prefix}.{key}"] = path.parent / Path(value).name
                report = (record["artifacts"].get("judge_of_record") or {}).get("report_path")
                if report:
                    files[f"{prefix}.judge_report"] = path.parent / Path(report).name
                if record.get("readapt") is not None:
                    target_report = record["readapt"]["target_report"]["path"]
                    files[f"{prefix}.target_report"] = path.parent / Path(target_report).name
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise AnalysisRefusal(f"run chain {chain} does not verify: {exc}") from exc
    return files


def analysis_input_files(args: argparse.Namespace, prep: Prepared) -> dict[str, Path]:
    """The data read for analysis or its validation, including bound artifacts and any replacement judge pass."""
    files = {"plan": args.plan, "seed_file": prep.seeds_path, "rubric": args.rubric,
             "outcome_registry": args.outcomes, "seed_outcome_registry": framework.OUTCOME_REGISTRY,
             "framing_registry": framework.FRAMING_REGISTRY, "manifest_schema": framework.MANIFEST_SCHEMA,
             **{f"registry_version[{i}]": path for i, path in enumerate(args.registry_version)}}
    files.update(selection_files(prep.plan))
    roots = {Path(args.runs_dir).resolve(), *(r.run_dir.parent.resolve() for r in prep.runs)}
    for root in sorted(roots):
        for path in sorted(root.glob("*/manifest.json")):
            files[f"discovered_manifest[{path}]"] = path
    if prep.secondary_judge is not None:
        files["judge_providers"] = spend.PROVIDERS_PATH
    regrade_dirs: set[Path] = set()
    for run in prep.runs:
        prefix = f"run[{run.stem}]"
        files[f"{prefix}.manifest"] = run.run_dir / "manifest.json"
        for key, value in run.manifest["artifacts"].items():
            if key.endswith("_path") and value:
                files[f"{prefix}.{key}"] = run.run_dir / Path(value).name
        report = run.manifest["artifacts"]["judge_of_record"].get("report_path")
        if report:
            files[f"{prefix}.judge_report"] = run.run_dir / Path(report).name
        info = run.provenance["registered_rows_from"]
        has_regrade = info.get("source") == "re-grade"
        if has_regrade:
            regrade_dirs.add(prep.rejudge_root / rejudge.judge_slug(prep.plan.judge_model) / run.stem)
        if prep.secondary_judge is not None:
            path = prep.rejudge_root / rejudge.judge_slug(prep.secondary_judge) / run.stem
            if (path / rejudge.MANIFEST_NAME).is_file():
                regrade_dirs.add(path)
                has_regrade = True
        if has_regrade:
            files[f"{prefix}.chain"] = run.run_dir.parent / rejudge.CHAIN_FILE
    if regrade_dirs:
        files["regrade_schema"] = rejudge.MANIFEST_SCHEMA
    for i, path in enumerate(sorted(regrade_dirs)):
        files[f"regrade[{i}].manifest"] = path / rejudge.MANIFEST_NAME
        record = load_json(path / rejudge.MANIFEST_NAME)
        for family, artifact in record["artifacts"].items():
            files[f"regrade[{i}].{family}"] = path / artifact["path"]
    # Rebuilding can recover an older rejected answer using its prompt's declared values. Those prompt bytes are
    # analysis inputs too, even when they do not agree with the recorded digest and leave the answer unavailable.
    prompt_refs = {row["prompt_ref"] for run in [*prep.runs, *prep.secondary_runs] for row in run.rows
                   if isinstance(row.get("prompt_ref"), str) and row["prompt_ref"]}
    for i, ref in enumerate(sorted(prompt_refs)):
        files[f"prompt[{i}]"] = ROOT / ref
    if args.final or args.primary_final is not None:
        files.update(verified_run_chain_inputs(args, prep))
        files["trigger_journal"] = JOURNAL_FILE
    return files


def uncommitted_input_problems(identity: Mapping[str, Any]) -> list[str]:
    """Refuse final statistics unless every recorded input belongs to the committed repository state."""
    problems = []
    if identity["commit"] is None:
        problems.append(f"the analysis commit is unavailable: {identity['commit_unavailable']}")
    for name, status in identity["uncommitted_changes"].items():
        path = identity["inputs"][name]["path"]
        if isinstance(status, str):
            problems.append(f"input {name} ({path}) cannot be shown to be committed: {status}")
        elif status:
            problems.append(f"input {name} ({path}) has uncommitted changes ({status}); commit it or restore it")
    return problems


def analysis_identity(inputs: Mapping[str, Path], repo_root: Path | None = None) -> dict[str, Any]:
    """The commit and files the analysis ran from: this script, the wave-2 module it reuses, judge_runner.py,
    rejudge.py and the inputs, each with its sha256 and any uncommitted change git reports for it."""
    me = Path(__file__)
    ident: dict[str, Any] = {"script": w2._display(me), "script_version": SCRIPT_VERSION,
                             "script_sha256": sha256_file(me), "python": platform.python_version(),
                             "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    files = {**code_files(), **inputs}
    ident["inputs"] = {name: {"path": w2._display(p), "sha256": sha256_file(p) if Path(p).is_file() else None}
                       for name, p in files.items()}
    root = REPO_ROOT if repo_root is None else repo_root
    ident["uncommitted_changes"] = {name: w2.git_status(p, root) for name, p in files.items()}
    try:
        ident["commit"] = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                                         text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        ident.update({"commit": None, "commit_unavailable": f"{type(exc).__name__}: {exc}"})
    return ident



def validate_saved_tests(primary: Mapping[str, Any], prep: Prepared) -> None:
    """Require the complete planned test structure without recomputing primary statistics.

    Expected tests/refusals come from the bound plan, dimension checks and entering standings. A missing test
    cannot disappear merely because recursive discovery no longer sees its p/direction fields.
    """
    expected: set[str] = set()

    def node(path: tuple[str, ...]) -> Mapping[str, Any]:
        value: Any = primary
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if not isinstance(value, Mapping):
            raise AnalysisRefusal(f"primary artifact is missing test structure {'.'.join(path)}")
        return value

    def keys(path: tuple[str, ...], names: Sequence[str]) -> None:
        if set(node(path)) != set(names):
            raise AnalysisRefusal(f"primary artifact has incomplete test inventory {'.'.join(path)}")

    def refusal(path: tuple[str, ...], reason: str) -> None:
        value = node(path)
        if (value.get("status") not in ("refused", "not computable", "not run")
                or value.get("reason") != reason or "p" in value or "direction" in value):
            raise AnalysisRefusal(f"primary artifact has malformed refusal {'.'.join(path)}")

    def test(path: tuple[str, ...], spec: str | None = None) -> None:
        reason = prep.not_computable.get(spec) or prep.record.refused_specs.get(spec)
        if reason:
            refusal(path, reason)
            return
        value = node(path)
        p = value.get("p")
        if (isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 1
                or value.get("direction") not in ("negative", "positive", "none")
                or not isinstance(value.get("significant"), bool)):
            raise AnalysisRefusal(f"primary artifact has malformed test {'.'.join(path)}")
        expected.add(".".join(path))

    plan = prep.plan
    keys(("targets",), [t.id for t in plan.targets])
    for target in plan.targets:
        root = ("targets", target.id)
        test((*root, "primary_sign_test"), "primary")
        test((*root, "scenario_gate"))
        test((*root, "exchanges_6_10"), "exchanges_6_10")
        keys((*root, "leave_one_scenario_out"), plan.scenarios)
        present = {st.triple.seed_id for st in prep.record.standings["primary"]
                   if st.enters and st.triple.target == target.id}
        for scenario in plan.scenarios:
            path = (*root, "leave_one_scenario_out", scenario)
            if scenario in present:
                test(path)
            else:
                refusal(path, "no triple of this scenario entered the primary contrast; leaving it out "
                              "would repeat the full test (see scenario_gate.missing_scenarios)")
        keys((*root, "sensitivity"), [s.name for s in plan.sensitivity])
        for sensitivity in plan.sensitivity:
            path = (*root, "sensitivity", sensitivity.name)
            if sensitivity.name in SENSITIVITY_RULES or sensitivity.mechanism is not None:
                node(path)  # descriptive/reference entries are not inferential tests
            else:
                test(path, f"sensitivity:{sensitivity.name}")
        keys((*root, "exploratory", "tests"), plan.family)
        for name in plan.family:
            test((*root, "exploratory", "tests", name), f"exploratory:{name}")
        keys((*root, "restricted_outcomes_descriptive"), [n for n in plan.restricted if n not in plan.family])
    if "decomposition" in prep.record.refused_specs:
        refusal(("section_9_4",), prep.record.refused_specs["decomposition"])
    else:
        for group in ("registered", "prespecified_secondary"):
            path = ("section_9_4", group, "tests")
            keys(path, ("style", "vocabulary", "paired_difference"))
            for part in ("style", "vocabulary", "paired_difference"):
                test((*path, part))
    path = ("section_9_6", "restricted_outcomes_across_targets")
    restricted = [name for name in plan.restricted if name not in plan.family]
    keys(path, restricted)
    for name in restricted:
        test((*path, name), f"restricted:{name}")
    if set(emitted_tests(primary)) != expected:
        raise AnalysisRefusal("primary artifact test inventory differs from the planned tests")


def bound_primary(args: argparse.Namespace, prep: Prepared, header: Mapping[str, Any],
                  truncated: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a committed once-only artifact to the unchanged primary inputs; never rerun its statistics."""
    try:
        primary = load_json(args.primary_final)
    except (OSError, ValueError) as exc:
        raise AnalysisRefusal(f"primary artifact cannot be read: {exc}") from exc
    if not isinstance(primary, dict) or primary.get("final") is not True or primary.get("secondary_judge") is not None:
        raise AnalysisRefusal("primary artifact must be a primary-only final analysis")
    for key in ("analysis", "plan_approved", "run_list", "bootstrap_seed", "bootstrap_resamples", "judge_of_record"):
        if primary.get(key) != header[key]:
            raise AnalysisRefusal(f"primary artifact differs in {key}")
    if (primary.get("administratively_truncated_targets") != truncated
            or primary.get("truncation_reason") != (args.declare_truncated if truncated else None)):
        raise AnalysisRefusal("primary artifact differs in the declared truncation")
    targets = primary.get("targets")
    if not isinstance(targets, dict) or set(targets) != {t.id for t in prep.plan.targets}:
        raise AnalysisRefusal("primary artifact is missing its target tests")
    for target in targets.values():
        if not isinstance(target, dict) or not all(
                isinstance(target.get(key), dict) and "p" in target[key] and "direction" in target[key]
                for key in ("primary_sign_test", "scenario_gate")):
            raise AnalysisRefusal("primary artifact has malformed target tests")
    validate_saved_tests(primary, prep)
    identity = primary.get("identity")
    if (not isinstance(identity, dict) or not isinstance(identity.get("commit"), str)
            or not isinstance(identity.get("inputs"), dict)
            or not isinstance(identity.get("uncommitted_changes"), dict)
            or any(identity["uncommitted_changes"].values())):
        raise AnalysisRefusal("primary artifact does not record committed input identity")
    original = identity.get("inputs")
    current = analysis_identity(analysis_input_files(args, replace(prep, secondary_judge=None, secondary_runs=[])))
    if not isinstance(original, dict) or not set(original) <= set(current["inputs"]):
        raise AnalysisRefusal("primary artifact input inventory differs")
    paths = {**code_files(), **analysis_input_files(args, replace(prep, secondary_judge=None, secondary_runs=[]))}
    added = set(current["inputs"]) - set(original)
    verified = verified_run_chain_inputs(args, prep)
    appended = {name for name in added if name in verified and ".entry[" in name}
    new_manifests = {verified[name].resolve() for name in appended if name.endswith(".manifest")}
    allowed = appended | {name for name in added if name.startswith("discovered_manifest[")
                          and paths[name].resolve() in new_manifests}
    if added != allowed:
        raise AnalysisRefusal("primary artifact input inventory differs beyond verified chain append")
    for name, old in original.items():
        now = current["inputs"][name]
        if old == now:
            continue
        # Secondary regrades append the verified chain and journal. Preserve the original byte prefix.
        if ((name.endswith(".chain") or name == "trigger_journal")
                and isinstance(old, dict) and old.get("path") == now["path"]
                and isinstance(old.get("sha256"), str)):
            digest = hashlib.sha256()
            for line in paths[name].read_bytes().splitlines(keepends=True):
                digest.update(line)
                if digest.hexdigest() == old["sha256"]:
                    break
            else:
                raise AnalysisRefusal(f"primary artifact input {name} is not an unchanged evidence prefix")
            continue
        raise AnalysisRefusal(f"primary artifact input {name} differs")
    return primary


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=Path,
                    help="run directories (default: every run under --runs-dir whose fire is in the plan)")
    ap.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    ap.add_argument("--rejudge-root", type=Path, default=REJUDGE_ROOT,
                    help="where re-grades live (<judge slug>/<run stem>/)")
    ap.add_argument("--plan", type=Path, default=PLAN_FILE, help="the plan (--final reads only the committed default)")
    ap.add_argument("--seeds", type=Path, help="the seed file (default and, under --final, only: the plan's seed_file)")
    ap.add_argument("--rubric", type=Path, default=ADVICE_RUBRIC)
    ap.add_argument("--outcomes", type=Path, default=OUTCOME_REGISTRY, help="the loaded outcome registry")
    ap.add_argument("--registry-version", type=Path, action="append", default=[],
                    help="an outcome registry file a run recorded, when git history lacks it (repeatable)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"the bootstrap seed ({DEFAULT_SEED}, the only one --final accepts)")
    ap.add_argument("--secondary-judge", metavar="SPEC",
                    help="also compute the same tables from this judge's re-grade rows, labelled secondary")
    ap.add_argument("--primary-final", type=Path,
                    help="post-final secondary-only report bound to this committed primary artifact; needs "
                         "--secondary-judge and --out, and cannot accompany --final")
    ap.add_argument("--final", action="store_true",
                    help="compute the register contrasts (once, on the final data); without it, coverage only")
    ap.add_argument("--declare-truncated", metavar="REASON",
                    help="under --final, run although a target epoch has not landed, recording the analysis as "
                         "administratively truncated with this reason; refused unless the trigger journal shows each "
                         "such fire fired and resolved")
    ap.add_argument("--out", type=Path, help="the JSON artifact (required with --final, and never overwritten)")
    return ap


def invocation_problems(args: argparse.Namespace) -> list[str]:
    """What the command line alone rules out, before any input is read."""
    problems = []
    if args.declare_truncated is not None and not args.declare_truncated.strip():
        problems.append("--declare-truncated needs a nonblank operational reason")
    if args.out is not None and args.out.exists():
        problems.append(f"--out {args.out} exists; this script never overwrites an artifact")
    if args.primary_final is not None:
        if args.final or args.secondary_judge is None:
            problems.append("--primary-final requires --secondary-judge and cannot accompany --final")
        if args.out is None:
            problems.append("--primary-final requires a separate --out")
    if not args.final and args.primary_final is None:
        if args.declare_truncated:
            problems.append("--declare-truncated applies only under --final")
        return problems
    if args.out is None:
        problems.append("--final writes its result to the artifact named by --out")
    if args.seed != DEFAULT_SEED:
        problems.append(f"--seed {args.seed}: the plan fixes the bootstrap seed at {DEFAULT_SEED}")
    plan_problem = plan_commit_problem(args.plan)
    if plan_problem:
        problems.append(plan_problem)
    return problems


def omitted_landed_runs(runs_dir: Path, plan: Plan, analysed: Sequence[RunInput]) -> list[str]:
    """Under --final with run paths given: every run directory under `runs_dir` that carries a live plan fire's journal
    nonce and is not among the runs analysed, or that cannot be read to say which fire it carries. A selective subset
    would otherwise make the once-only artifact, with the fires left out classed as not landed (and declarable as
    truncated, since a landed fire's journal entry is resolved too)."""
    if not Path(runs_dir).is_dir():
        return [f"--runs-dir {runs_dir} is not a directory, so the runs given cannot be shown to be every landed plan "
                f"fire"]
    given = {Path(r.run_dir).resolve() for r in analysed}
    problems = []
    for d in sorted(p for p in Path(runs_dir).iterdir() if p.is_dir() and (p / "manifest.json").is_file()):
        if d.resolve() in given:
            continue
        try:
            nonce = w2.run_nonce(d, w2.read_manifest(d))
            if not nonce.strip() or nonce != nonce.strip():
                raise AnalysisRefusal(f"{d}: the manifest records no usable spend.journal_nonce ({nonce!r})")
        except (AnalysisRefusal, OSError, ValueError, AttributeError) as exc:
            problems.append(f"{w2._display(d)}: its manifest cannot be read ({exc}), so whether it is a landed plan "
                            f"fire left out of the run list is unknown")
            continue
        fire = plan.fires.get(nonce)
        if fire is not None and fire.voided is None:
            problems.append(f"{w2._display(d)} carries plan fire {nonce} (target {fire.target}, epoch "
                            f"{fire.campaign_epoch}) but is not among the runs given; --final analyses every landed "
                            f"plan fire")
    return problems


def selection_files(plan: Plan) -> dict[str, Path]:
    """Files explicitly bound by the gate selection; included in final input/commit provenance."""
    selection = plan.realism_gate_selection
    if not isinstance(selection, dict):
        return {}
    refs = {"gate_report": selection.get("gate_report")}
    summaries = selection.get("summaries")
    if isinstance(summaries, list):
        refs.update({f"gate_summary[{i}]": row.get("summary") for i, row in enumerate(summaries)
                     if isinstance(row, dict)})
    return {key: Path(ref) if Path(ref).is_absolute() else ROOT / ref for key, ref in refs.items()
            if isinstance(ref, str) and ref.strip()}


def gate_selection_problems(plan: Plan) -> list[str]:
    """Validate the recorded gate decision and its bound artifacts, without recalculating ratings."""
    label = "physician_realism_gate.selection"
    selection = plan.realism_gate_selection
    if not isinstance(selection, dict):
        return [f"{label} must record the applied gate before final analysis, even when every seed passes"]
    problems = []
    rounds = plan.realism_gate.get("rounds")
    nrounds = len(rounds) if isinstance(rounds, list) else 0
    summaries = selection.get("summaries")
    if (not nrounds or not isinstance(summaries, list) or len(summaries) != nrounds
            or any(not isinstance(row, dict) or type(row.get("round")) is not int or row["round"] != i
                   for i, row in enumerate(summaries, 1))):
        problems.append(f"{label}.summaries must name every gate round in order")
        summaries = []
    artifacts = [("gate_report", selection.get("gate_report"), selection.get("gate_report_sha256"))]
    artifacts.extend((f"summary[{i}]", row.get("summary"), row.get("summary_sha256"))
                     for i, row in enumerate(summaries, 1))
    for name, ref, digest in artifacts:
        if (not isinstance(ref, str) or not ref.strip() or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            problems.append(f"{label}.{name} needs a file path and 64-hex digest")
            continue
        path = Path(ref) if Path(ref).is_absolute() else ROOT / ref
        try:
            raw = path.read_bytes()
            if not isinstance(json.loads(raw), dict) or hashlib.sha256(raw).hexdigest() != digest:
                problems.append(f"{label}.{name} is not the pinned JSON object")
        except (OSError, ValueError) as exc:
            problems.append(f"{label}.{name} cannot be read: {exc}")
    seen: set[str] = set()
    passing: list[str] = []
    for group in ("passing", "failing"):
        rows = selection.get(group)
        if not isinstance(rows, list):
            problems.append(f"{label}.{group} must be a list")
            continue
        for row in rows:
            if not isinstance(row, dict):
                problems.append(f"{label}.{group} has a non-object entry")
                continue
            sid, decided, short = row.get("seed_id"), row.get("round"), row.get("short_rounds")
            if not isinstance(sid, str) or not sid.strip() or sid in seen:
                problems.append(f"{label}.{group} has a missing or repeated seed id")
                continue
            seen.add(sid)
            if group == "passing":
                passing.append(sid)
            valid_round = type(decided) is int and 1 <= decided <= nrounds
            valid_short = (isinstance(short, list) and all(type(r) is int and 1 <= r <= nrounds for r in short)
                           and short == sorted(set(short)))
            if group == "passing" and not valid_round:
                problems.append(f"{label}.passing entry {sid!r} needs its deciding round")
            if not valid_short or (valid_round and any(r >= decided for r in short)):
                problems.append(f"{label}.{group} entry {sid!r} has invalid short_rounds")
            if group == "failing" and not (
                    row.get("reason") == "rated unrealistic" and valid_round
                    or row.get("reason") == "not enough ratings" and decided is None and valid_short and short):
                problems.append(f"{label}.failing entry {sid!r} has an invalid reason/round")
    if passing != plan.scenarios:
        problems.append(f"{label}.passing must match the planned scenario set in order")
    try:
        candidates = list(load_seed_file(plan.seed_file).seeds)
        if seen != set(candidates):
            problems.append(f"{label} must classify every candidate seed exactly once "
                            f"(missing {sorted(set(candidates) - seen)}; extra {sorted(seen - set(candidates))})")
        for group in ("passing", "failing"):
            rows = selection.get(group)
            if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
                ids = [row.get("seed_id") for row in rows]
                if ids != [sid for sid in candidates if sid in ids]:
                    problems.append(f"{label}.{group} must follow candidate seed-file order")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f"{label} candidate seed file cannot be read: {exc}")
    minimum = plan.realism_gate.get("min_scenarios")
    if type(minimum) is not int or minimum < 1 or len(passing) < minimum:
        problems.append(f"{label} does not meet its min_scenarios floor")
    return problems


def approval_chronology_problems(prep: Prepared, approved: date) -> list[str]:
    """Require day-level approval to precede the recorded fire and run dates, with no guessed intra-day order."""
    problems: list[str] = []
    if approved > datetime.now(timezone.utc).date():
        problems.append("approval.approved_on is in the future")

    def check(value: Any, label: str) -> bool:
        try:
            if not isinstance(value, str):
                raise ValueError("missing timestamp")
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timestamp has no UTC offset")
            if approved >= timestamp.astimezone(timezone.utc).date():
                problems.append(f"approval.approved_on must precede {label}'s UTC date; date-only approval "
                                "cannot establish order within the same day")
            return True
        except ValueError as exc:
            problems.append(f"approval chronology cannot be established for {label}: {exc}")
            return False

    for run in prep.runs:
        check(run.manifest.get("created_utc"), f"run {run.stem}")
    try:
        entries = [json.loads(line) for line in JOURNAL_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not all(isinstance(entry, dict) for entry in entries):
            raise ValueError("journal entries must be objects")
    except (OSError, ValueError) as exc:
        return problems + [f"approval chronology cannot read trigger journal: {exc}"]
    recorded: set[str] = set()
    fires = {**prep.plan.fires, **prep.plan.regrade_fires}
    for entry in entries:
        nonce = entry.get("nonce")
        if entry.get("trigger") != "petri-audit" or not isinstance(nonce, str) or nonce not in fires:
            continue
        if entry.get("fired_utc") is not None and check(entry["fired_utc"], f"fire {nonce}"):
            recorded.add(nonce)
            fired = datetime.fromisoformat(entry["fired_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if date.fromisoformat(fires[nonce].recorded_on) >= fired.date():
                problems.append(f"fire {nonce}: recorded_on must precede fired_utc's UTC date; a date-only "
                                "amendment cannot establish order within the same day")
    for nonce in fires:
        if nonce not in recorded:
            problems.append(f"approval chronology: fire {nonce} has no usable fired_utc in the journal")
    return problems


def final_problems(args: argparse.Namespace, prep: Prepared) -> tuple[list[str], dict[str, list[int]]]:
    """What the inputs rule out under --final, and the target epochs a declared truncation covers."""
    plan = prep.plan
    problems = []
    if not plan.approved:
        problems.append("the plan is not approved (approval.approved is false): it binds nothing until the owner "
                        "approves it as a dated decision")
    if not isinstance(plan.approved_by, str) or not plan.approved_by.strip():
        problems.append("approval.approved_by must name the approving owner")
    try:
        if not isinstance(plan.approved_on, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", plan.approved_on) is None:
            raise ValueError("expected YYYY-MM-DD")
        approved = date.fromisoformat(plan.approved_on)
    except ValueError:
        problems.append("approval.approved_on must be a valid YYYY-MM-DD date")
    else:
        problems.extend(approval_chronology_problems(prep, approved))
    problems.extend(gate_selection_problems(plan))
    if plan.analysis_script_path != "scripts/petri_w3_register_contrast.py" or plan.analysis_script_status != "written":
        problems.append("analysis_script must name scripts/petri_w3_register_contrast.py with status 'written' "
                        "in the approved plan before the first paid fire")
    if prep.secondary_judge is not None and prep.secondary_judge != plan.secondary_spec:
        problems.append(f"--secondary-judge {prep.secondary_judge!r} is not the plan's designated "
                        f"judge.second_family_regrade {plan.secondary_spec!r}")
    if plan.judge_model is None:
        problems.append("judge.judge_model is null: the dated approval sets the judge of record before any fire")
    if plan.bootstrap_seed != DEFAULT_SEED or args.seed != plan.bootstrap_seed:
        problems.append(f"the plan's bootstrap seed is {plan.bootstrap_seed} and --seed is {args.seed}; both must be "
                        f"{DEFAULT_SEED}")
    if prep.rubric_digest != plan.rubric_digest:
        problems.append(f"the rubric {w2._display(prep.rubric_path)} has digest {prep.rubric_digest}, not the "
                        f"{plan.rubric_digest} the plan pins")
    if prep.seeds_path.resolve() != plan.seed_file.resolve():
        problems.append(f"--seeds {prep.seeds_path} is not the plan's seed_file {w2._display(plan.seed_file)}")
    if args.runs:
        roots = {Path(args.runs_dir).resolve(), *(r.run_dir.parent.resolve() for r in prep.runs)}
        for root in sorted(roots):
            problems.extend(omitted_landed_runs(root, plan, prep.runs))
    for r in prep.runs:
        if not r.registered:
            problems.append(f"run {r.stem} has no registered rows: {r.unregistered_reason}")
    if prep.secondary is not None and not prep.secondary_complete:
        short = {k: v for k, v in prep.secondary_coverage.items() if v.get("status") != "covered"}
        problems.append(f"the secondary judge {prep.secondary_judge}'s rows do not cover the exchanges the judge of "
                        f"record made comparable: {json.dumps(short)}")
    missing = missing_epochs(prep)
    truncated = {t: sorted(eps) for t, eps in missing.items()}
    if missing and not args.declare_truncated:
        problems.append(f"target epochs {truncated} have not landed. The analysis runs once, on each target's final "
                        f"data; to run on what landed after an operational failure, pass --declare-truncated with the "
                        f"reason")
    elif args.declare_truncated and not missing:
        problems.append("--declare-truncated was given, but every target epoch has landed: nothing is truncated")
    elif missing:
        nonces = []
        for target, eps in missing.items():
            for epoch, info in eps.items():
                # A live replacement supersedes its voided predecessors. Keep their history in coverage, but
                # require completion of the replacement only; without one, the voided fires remain the evidence.
                fired = [info["live_fire"]] if info["live_fire"] else info["voided_fires"]
                if not fired:
                    problems.append(f"target {target} epoch {epoch}: no fire is recorded, so no operational failure "
                                    f"can be shown; record its fire, or the plan's amendment, first")
                nonces.extend(fired)
        problems.extend(w2.journal_problems(nonces, JOURNAL_FILE))
    return problems, truncated


def _refuse(problems: Sequence[str]) -> int:
    for problem in problems:
        print(f"refused: {problem}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problems = invocation_problems(args)
    if problems:
        return _refuse(problems)
    try:
        prep = prepare(args.runs or None, runs_dir=args.runs_dir, plan_path=args.plan, seeds_path=args.seeds,
                       rubric_path=args.rubric, registry_path=args.outcomes, registry_versions=args.registry_version,
                       rejudge_root=args.rejudge_root, secondary_judge=args.secondary_judge)
    except AnalysisRefusal as exc:
        return _refuse([str(exc)])
    cov = coverage(prep)
    try:
        inputs = analysis_input_files(args, prep)
    except AnalysisRefusal as exc:
        problems, _ = final_problems(args, prep) if args.final or args.primary_final is not None else ([], {})
        return _refuse([*problems, str(exc)])
    if args.primary_final is not None:
        inputs["primary_final"] = args.primary_final
    header = {"analysis": "docs/petri_wave3_design.md section 9 (wave-3 register contrast)",
              "plan_approved": prep.plan.approved, "final": bool(args.final),
              "run_list": [r.provenance["path"] for r in prep.runs], "bootstrap_seed": args.seed,
              "bootstrap_resamples": prep.plan.bootstrap_resamples, "judge_of_record": prep.plan.judge_model,
              "secondary_judge": args.secondary_judge,
              "identity": analysis_identity(inputs)}
    if not args.final and args.primary_final is None:
        doc = {**header, "note": "coverage only (rules[0]): no register contrast is computed without --final",
               "coverage": cov}
        print(json.dumps(doc, indent=1, ensure_ascii=False))
        if args.out is not None:
            try:
                with args.out.open("x", encoding="utf-8") as fh:
                    fh.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
            except FileExistsError:
                return _refuse([f"--out {args.out} appeared while coverage ran; nothing was written"])
        return 0
    problems, truncated = final_problems(args, prep)
    problems.extend(uncommitted_input_problems(header["identity"]))
    if problems:
        return _refuse(problems)
    try:
        if args.primary_final is not None:
            primary = bound_primary(args, prep, header, truncated)
            result = {"mode": "post_final_secondary",
                      "primary_final": {"path": str(args.primary_final), "sha256": sha256_file(args.primary_final)},
                      "secondary_judge": secondary_report(prep, primary, seed=args.seed,
                                                          resamples=prep.plan.bootstrap_resamples)}
        else:
            result = final_analysis(prep, seed=args.seed, resamples=prep.plan.bootstrap_resamples)
    except AnalysisRefusal as exc:
        return _refuse([str(exc)])
    doc = {**header, "administratively_truncated_targets": truncated,
           "truncation_reason": args.declare_truncated if truncated else None, "coverage": cov, **result}
    try:
        with open(args.out, "x", encoding="utf-8") as fh:       # never overwrite: the analysis runs once
            fh.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    except FileExistsError:
        return _refuse([f"--out {args.out} appeared while the analysis ran; nothing was written"])
    print(json.dumps({"final": bool(args.final), "out": str(args.out),
                      "statements": {t: b["statement"]["row_id"] for t, b in result.get("targets", {}).items()},
                      "administratively_truncated_targets": truncated,
                      "secondary_judge": args.secondary_judge}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
