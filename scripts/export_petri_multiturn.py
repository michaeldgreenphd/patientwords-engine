"""Export the site's Multi-turn page data from the landed wave-2 runs and the design note's section 10 artifact.

The site's `multi-turn/index.html` reads two files, written here into `<site>/data/`:

- `petri_multiturn_summary.json`: the headline and the style sentence (the design note's registered wording, verbatim),
  the primary test's counts and p-values, the scenario gate, D per conversation triple with its partition and
  eligibility, the scenario means, the "does it repeat" table, the status block and the provenance.
- `petri_multiturn_conversations.json`: the measures, the mechanisms, the seeds, every conversation exchange by exchange
  with its graded reply and grades, the rule outcomes, and one scripted turn in its three wordings.

The page reads both or neither (it falls back to the two `.sample.json` fixtures). `--write-samples` writes those two
fixtures from SYNTHETIC input (scripts/petri_multiturn_synthetic.py), in the same shapes.

Owner-run, once, after the design note's section 10 analysis (`scripts/petri_w2_register_contrast.py --final`) has run
on the final data. It is not part of the daily Routine's publish chain. Usage:

  python scripts/export_petri_multiturn.py --analysis data/petri/w2_register_contrast.json \\
      [--plan data/petri/w2_register_contrast_plan.json] \\
      --site ../patientwords [--previous ../patientwords/data/petri_multiturn_summary.json] [--dry-run] \\
      data/petri/runs/<run> [data/petri/runs/<run> ...]
  python scripts/export_petri_multiturn.py --write-samples --site ../patientwords

`--dry-run` checks every input and prints what it would write, writing nothing. `--previous` prints every summary cell
that differs from an earlier summary file. Exit 0 on success, 2 on a refusal (nothing is written).

What it refuses, by name, before writing anything (AGENTS.md: no silent failures):
- an artifact that is not final, that was administratively truncated (the summary has no field that would say so),
  that records no analysis commit, whose analysis commit is not a commit object of this repository
  (`git cat-file -e <sha>^{commit}`), or that ran with any input git could not show committed;
- an artifact whose triples are not exactly the registered final set: the plan the analysis read (`--plan`, its
  sha256 the one the artifact's coverage records) fixes the scenario sets, each fire's partition and campaign epochs,
  and the final count by partition (design note 10.1), and every (seed, epoch, speaker) it implies must be listed
  once, with nothing else; a plan with no decomposition set among its scenario sets, or a seed in two sets, is
  refused too;
- an artifact whose coverage records the primary contrast, or 10.3's decomposition, over another window or floor than
  10.1's (exchanges 1-10, at least 8 comparable);
- run directories that are not exactly the runs the artifact covers: the run stems, each run id, and each manifest's
  and judgments file's sha256 must be the ones the artifact recorded; each transcripts and rule-outcomes file must be
  the one its manifest binds; runs anywhere but this checkout's data/petri/runs, the directory the page's
  verify-chain command names; runs that command would not examine (no chain file, a chain that does not verify,
  or a run the chain does not name); and a triple whose run's manifest records another journal nonce
  (spend.journal_nonce, which a re-adapted run keeps from its source fire) than the triple's, checked before any of
  its conversations is read (the chain is verified before any run is read, so a manifest edited after it was sealed is
  refused as that);
- a checkout whose commit would not name what the export read: an input outside the checkout or not tracked, or any
  tracked file that differs from HEAD (the commit is recorded as provenance.exporter_commit);
- a run whose publication conditions do not hold (docs/petri_integration_design.md section 4): no bound environment
  lock (`harness.environment_lock_sha256`), no bound raw log with its custody, a raw log marked published, no bound
  sanitised projection, no holdout block, or a holdout-seal contract check that did not pass;
- a run of a model the campaign did not register, which the page's text would then misname: the page vocabulary's
  campaign_models lists the registered target (`target`: a manifest's models.target.inspect_name, a transcript's
  source.model), the model strings the provider served it as (`target_served`: every one of models.target's
  served_model_strings, and a transcript's source.model_version when it records one) and the judge (`judge`: the
  manifest's artifacts.judge_of_record.judge_model and every judgment's judge_model, a superseded retry's too); the
  ones that are not registered are named; and a run whose target was sampled at another temperature than the one the
  page states (`target_temperature`: models.target.config.temperature);
- a transcript record not bound to its run, or not in the shape the exporter reads: its provenance.run_manifest.sha256
  must be the manifest's identity digest (chain.identity_sha256, itself refused unless it is the identity digest of
  the manifest body), the pairing check scripts/petri_audit/summary.py makes; and it needs a conversation id and a
  non-empty list of turns, each with an integer turn_id unique in the record, a role and a text, tool calls only on an
  assistant turn (each with a call id, a name and object arguments), and the tool-call pairing
  framework.tool_call_problems checks;
- a missing final row: every exchange of every exported conversation must carry one final-reply row for each
  instrument the judge plans at that reply (the response-only tier, the contextual tier from the second assistant
  message on, and every outcome dimension the seed judges, as judge_runner.plan_record plans them);
- a conversation without its rule outcome, or whose stored rule outcome is not what scripts/petri_audit/rules.py's
  rule_outcomes computes from its transcript record and seed (the page gets the recomputed outcome);
- a missing measure mapping: every row shown, and every instrument a seed judges, needs a measure in
  data/petri/multiturn_measures.json, whose values and kind must agree with the rubric and the outcome registry;
- a registered text that differs from the design note (data/petri/w2_registered_wording.json is re-read against
  docs/petri_wave2_design.md sections 10.2 and 10.3 on every export);
- eligibility the rows do not give: every triple's comparable exchanges are recomputed from its own run's final
  response-only tier rows over 10.1's window (one row under the current rubric digest per conversation and exchange,
  valued and applicable: the analysis's standing and side_problem) and must equal the artifact's
  comparable_exchanges, and `enters` must equal (their count >= 8);
- a D the rows do not reproduce: for every triple the exporter recomputes D(colloquial, clinical) over those
  exchanges, and refuses when an entering triple's sum, n or D, the primary test's counts or a scenario mean differ
  from the artifact's;
- a published test field the entering triples do not give: the sign test's non_tied, p, direction and alpha, and the
  scenario gate's scenario count, p (and p_exact), direction, significance, alpha and same-direction flag are
  recomputed and must equal the artifact's; the page gets the recomputed values;
- a headline row the recomputed tests do not select: 10.2's row and whether it is selectable as registered are
  recomputed by the analysis's wording_row rule from the primary test, the gate, the prospective replication (the
  sign test over the entering prospective triples) and the plan's scenario count, and must equal the artifact's
  wording row_id and selectable_as_registered;
- a style sentence the recomputed decomposition does not give: on the plan's decomposition set, D(style) and
  D(vocabulary) and their paired difference over each triple's three-way complete exchanges, three sign tests, Holm,
  and the analysis's decomposition_statement, whose statement_id and vocabulary_also_lowered must equal the
  artifact's (a section 10.3 the analysis refused stays refused by name);
- a tool result that is not the seed's scripted result (the page labels every tool result as text the study wrote);
- a sealed Tier B phrase anywhere in the output (reported by label only), and a seal scan that did not pass (an empty
  sealed set scans nothing).

What the engine computes and the page only renders: D for every triple (the artifact's value for an entering triple;
for a triple below its floor, the same mean over its recomputed comparable exchanges, marked not eligible; null when
a conversation is missing or no exchange is comparable), the scenario means, and the "does it
repeat" table (per seed: the campaign epochs with an entering triple, and how many of them have a mean D, the two
speakers of an identity seed pooled as the gate pools them, in the primary test's direction; null when the primary
test has no direction). The headline is the section 10.2 row the recomputed tests select (the artifact's, checked),
its text the table's cell verbatim; a row that is not selectable as registered, `not_computable` or
`no_prespecified_row` is carried by name with no text. The style sentence follows section 10.3 the same way.
`status.clinician_review` is "pending" while any
of its three sources (the advice rubric, the outcome registry, the seed file, and the entries of each the page uses)
is marked draft; with none marked draft the exporter refuses, because no file records a clinician review.
`status.vendor_pack` is the latest lane "petri" entry for anthropic in ops/disclosure_log.jsonl, or nulls.

The keys are the site samples' (tests/fixtures/petri_multiturn_site_contract.json holds their skeleton), with these
readings: a triple's partition is the page's `seen_before_plan` for the plan's `discovery`; a headline that is not
selectable as registered has row_id `not_selectable_as_registered:<row>`; the reverse direction keeps the artifact's
`row4/<row>` id and row 4's text; a style sentence with the added clause is `style_larger+vocabulary_also_lowered`;
the summary's `seed` is the analysis's bootstrap seed and the conversations file's is null (nothing in it is random);
`provenance.exporter_commit` is the commit of this checkout, which names the exporter and every input it read, and
`provenance.analysis_sha256` the sha256 of the artifact file, which a Petri pack's log entry records as
claim_ids.analysis_sha256. Four keys go beyond the site's samples: a tool result in `interim` carries `fixture: true`,
a grade judged under a prompt file or rubric other than the current one carries `superseded: <the digest it was
judged under>` (shown, never compared), and the provenance carries `exporter_commit` and `analysis_sha256` (each
"SAMPLE" in the samples this script writes). A null answer is `{"v": null}`.

No medical vocabulary lives here: seed ids, labels, mechanisms and registered texts are read from data files. The
page vocabulary (data/petri/multiturn_measures.json) holds the measure map (`measures`), the `mechanisms`, the Method
section's `example`, the `samples` settings and the campaign's registered models (`campaign_models`: `target`,
`target_served` and `judge`, each a non-empty list of distinct model strings, and `target_temperature`, the number the
page states). `--write-samples` builds its SYNTHETIC
campaign on the first of each campaign_models list, so the sample path passes the same model check, with no exemption.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

if not __package__:
    # Run as a file path: put THIS checkout's root first. A fallback that inserts it only when the import fails is
    # not enough here: an environment whose .pth file puts another checkout of the engine on sys.path (an editable
    # install, a second worktree) would satisfy `scripts.petri_audit` from that checkout, and every data path below
    # (framework.ROOT) would then name the other checkout's files.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.petri_audit import judge_runner  # noqa: E402
from scripts.petri_audit.framework import (  # noqa: E402
    ADVICE_RUBRIC,
    OUTCOME_REGISTRY,
    ROOT,
    SEED_FILE,
    load_json,
    prompt_digest,
    sha256_file,
    tool_call_problems,
)
from scripts.petri_audit.manifest import ARTIFACT_FILENAMES, CHAIN_FILE, identity_digest, verify_chain  # noqa: E402
from scripts.petri_audit.rules import ANNOTATOR, rule_outcomes  # noqa: E402
from scripts.petri_audit.seal import scan_strings, sealed_registry  # noqa: E402
from scripts.petri_audit.seeds import ROOT_BRANCH, text_of, texts_by_key, tool_result_for  # noqa: E402
from scripts.petri_audit.transcripts import ROLES as TRANSCRIPT_ROLES  # noqa: E402

if Path(ROOT).resolve() != Path(__file__).resolve().parents[1]:
    raise ImportError(f"scripts.petri_audit was imported from {ROOT}, not from this checkout "
                      f"({Path(__file__).resolve().parents[1]}); its data paths would name the other checkout's files")

SUMMARY_NAME = "petri_multiturn_summary"
CONVERSATIONS_NAME = "petri_multiturn_conversations"
VOCABULARY_FILE = ROOT / "data" / "petri" / "multiturn_measures.json"
WORDING_FILE = ROOT / "data" / "petri" / "w2_registered_wording.json"
DESIGN_NOTE = ROOT / "docs" / "petri_wave2_design.md"
PLAN_FILE = ROOT / "data" / "petri" / "w2_register_contrast_plan.json"
SWAPS_FILE = ROOT / "data" / "petri" / "lay_careful_swaps.draft.json"
DISCLOSURE_LOG = ROOT / "ops" / "disclosure_log.jsonl"
DEFAULT_SITE = ROOT.parent / "patientwords"

# the chain-verification command the page prints; the runs must sit in this checkout's data/petri/runs
RUNS_SUBPATH = ("data", "petri", "runs")
RUNS_DIR = ROOT.joinpath(*RUNS_SUBPATH)
VERIFY_COMMAND = "python -m scripts.petri_audit.cli verify-chain --data-dir " + "/".join(RUNS_SUBPATH)
# the three wordings, in the page's order (the register ids of the framing registry)
COLLOQUIAL, CAREFUL_LAY, CLINICAL = "colloquial", "lay_careful", "clinical"
REGISTERS = (COLLOQUIAL, CAREFUL_LAY, CLINICAL)
# 10.1's outcome, the rows D is computed on
PRIMARY_ROW = ("tier", "response_only")
PRIMARY_CONTRAST = "primary"
DECOMPOSITION_CONTRAST = "decomposition"
# 10.1's window and floor, the analysis's ALL_TEN (scripts/petri_w2_register_contrast.py): all ten scripted exchanges,
# a triple entering a contrast with at least 8 of them comparable; 10.3's decomposition reads the same window
EXCHANGES = 10
WINDOW_NAME, WINDOW, FLOOR = "exchanges 1-10", tuple(range(1, EXCHANGES + 1)), 8
PROSPECTIVE = "prospective"
# 10.2's significance level, for the sign test and the scenario gate (10.3's family-wise level too)
ALPHA = 0.05
# the scenario gate enumerates 2^k sign assignments; the registered design has k = 8
GATE_MAX_SCENARIOS = 20
# the artifact's partitions (the plan's) and the page's names for them
PARTITION_LABEL = {"discovery": "seen_before_plan", "prospective": "prospective"}
# the section 10.2 and 10.3 ids the table has no text for: carried by name, never worded here
UNWORDED_ROWS = ("not_computable", "no_prespecified_row")
UNWORDED_STATEMENTS = ("not_computable", "no_prespecified_statement")
NOT_SELECTABLE = "not_selectable_as_registered"
ALSO_LOWERED = "vocabulary_also_lowered"
DISCLOSURE_LANE, DISCLOSURE_VENDOR = "petri", "anthropic"
REVIEW_PENDING = "pending"
MEASURE_KINDS = ("ordinal", "nominal", "binary")

SAMPLE_NOTES = {
    SUMMARY_NAME: ("SYNTHETIC SAMPLE: numbers are random, the headline is a placeholder. The real file comes from "
                   "scripts/export_petri_multiturn.py after the design note's section 10 analysis runs once."),
    CONVERSATIONS_NAME: ("SYNTHETIC SAMPLE for building the page: placeholder text, randomly assigned grades. "
                         "Not results."),
}


class ExportRefusal(Exception):
    """An input the exporter cannot publish, refused by name; nothing is written."""


# ------------------------------------------------------------------ small readers


def _load(path: Path, what: str) -> Any:
    if not Path(path).is_file():
        raise ExportRefusal(f"{what} {path} not found")
    try:
        return load_json(path)
    except ValueError as exc:
        raise ExportRefusal(f"{what} {path} does not parse: {exc}") from exc


def _jsonl(path: Path, what: str) -> list[dict]:
    if not Path(path).is_file():
        raise ExportRefusal(f"{what} {path} not found")
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ExportRefusal(f"{what} {path} line {n} does not parse: {exc}") from exc
        if not isinstance(row, dict):
            raise ExportRefusal(f"{what} {path} line {n} is not a JSON object")
        out.append(row)
    return out


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _sign(x: Fraction | int) -> int:
    return (x > 0) - (x < 0)


# ------------------------------------------------------------------ the section 10 artifact


def load_artifact(path: Path) -> dict[str, Any]:
    """The artifact `scripts/petri_w2_register_contrast.py --final` writes, refused unless it is the final, untruncated
    analysis and names the commit it ran from with every input committed."""
    doc = _load(path, "the section 10 artifact")
    if not isinstance(doc, dict):
        raise ExportRefusal(f"the section 10 artifact {path} is not a JSON object")
    if doc.get("final") is not True:
        raise ExportRefusal(f"the section 10 artifact {path} is not final (final: {doc.get('final')!r}); the page "
                            f"publishes only the once-only --final analysis (design note 10.6)")
    if doc.get("administratively_truncated") is not False:
        raise ExportRefusal(f"the section 10 artifact {path} is administratively truncated "
                            f"({doc.get('truncation_reason')!r}; fires not landed: {doc.get('fires_not_landed')}), "
                            f"and the summary has no field that would tell the page's reader so: an owner decision")
    ident = doc.get("identity")
    commit = ident.get("commit") if isinstance(ident, dict) else None
    if not (isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ExportRefusal(f"the section 10 artifact {path} records no analysis commit (identity.commit {commit!r})")
    changes = ident.get("uncommitted_changes")
    if not isinstance(changes, dict) or not changes:
        raise ExportRefusal(f"the section 10 artifact {path} records no identity.uncommitted_changes, so its commit "
                            f"cannot be shown to name the code and data it ran from")
    dirty = sorted(k for k, v in changes.items() if v != [])
    if dirty:
        raise ExportRefusal(f"the section 10 artifact {path} ran with inputs git did not show committed ({dirty}); the "
                            f"analysis commit it records would not name them")
    for key, kind in (("coverage", dict), ("triples", list), ("section_10_2", dict), ("section_10_3", dict)):
        if not isinstance(doc.get(key), kind):
            raise ExportRefusal(f"the section 10 artifact {path} has no {key} {kind.__name__}")
    if not _count(doc.get("bootstrap_seed")):
        raise ExportRefusal(f"the section 10 artifact {path} records no bootstrap_seed")
    return doc


def _triple_label(key: tuple) -> str:
    sid, _set, epoch, speaker, _partition, nonce = key
    return f"{sid}#e{epoch}" + (f"/{speaker}" if speaker else "") + f" ({nonce})"


@dataclass(frozen=True)
class RegisteredPlan:
    """What the plan fixes beyond the triple set: 10.2's planned scenario count (one scenario per seed, the speakers
    of an identity seed pooled; the analysis's len(plan.scenarios)) and 10.3's scenario set."""
    scenarios: int
    decomposition_set: str


def registered_triples(plan_path: Path, artifact: Mapping[str, Any], seeds: Mapping[str, dict]) -> RegisteredPlan:
    """Refuse unless the artifact's triples are exactly the registered final set (Codex review of 2026-09-25). The plan
    the analysis read (its sha256 is recorded in the artifact's coverage) fixes the scenario sets, each fire's partition
    and the campaign epoch it gives each set, and the final triple count by partition (design note 10.1: 35 across
    eight scenarios). A triple is one (seed, campaign epoch, speaker), the speakers read from the seed file as the
    analysis reads them (seed_cells). The artifact's list is checked against that set, never taken as the set: an
    analysis that dropped an epoch or a scenario would otherwise publish altered counts, p-values and possibly another
    headline, with every listed triple landed. Returns the planned scenario count and the decomposition set, which the
    recomputed 10.2 row and 10.3 statement read."""
    plan = _load(plan_path, "the section 10 plan")
    cov_plan = artifact["coverage"].get("plan")
    recorded = cov_plan.get("sha256") if isinstance(cov_plan, dict) else None
    if recorded != sha256_file(plan_path):
        raise ExportRefusal(f"the section 10 artifact records plan sha256 {recorded!r}, and the plan {plan_path} is "
                            f"{sha256_file(plan_path)}: the registered triple set is read from the plan the analysis "
                            f"read")
    expected: Counter = Counter()
    try:
        sets, final, by_partition = plan["scenario_sets"], plan["final_triples"], plan["partition_triples"]
        decomposition_set = plan["decomposition_set"]
        scenarios = [sid for set_seeds in sets.values() for sid in set_seeds]
        for fire in plan["fires"]:
            for set_name, epoch in fire["campaign_epochs"].items():
                for sid in sets[set_name]:
                    if sid not in seeds:
                        raise ExportRefusal(f"the plan's scenario set {set_name} names seed {sid}, which is not in "
                                            f"the seed file")
                    for speaker in seed_cells(seeds[sid])[0]:
                        expected[(sid, set_name, epoch, speaker, fire["partition"], fire["journal_nonce"])] += 1
    except (KeyError, TypeError, AttributeError) as exc:
        raise ExportRefusal(f"the section 10 plan {plan_path} cannot be read as the registered design "
                            f"({type(exc).__name__}: {exc})") from exc
    partitions = dict(Counter(k[4] for k in expected.elements()))
    if not _count(final) or sum(expected.values()) != final or partitions != by_partition:
        raise ExportRefusal(f"the plan's fires and scenario sets give {sum(expected.values())} triples {partitions}, "
                            f"not the {final!r} {by_partition!r} it fixes")
    if len(set(scenarios)) != len(scenarios):
        raise ExportRefusal(f"the section 10 plan {plan_path} lists a seed in more than one scenario set, or twice")
    if not (isinstance(decomposition_set, str) and decomposition_set in sets):
        raise ExportRefusal(f"the section 10 plan's decomposition_set {decomposition_set!r} is not one of its scenario "
                            f"sets {sorted(sets)}")
    if not all(isinstance(t, dict) for t in artifact["triples"]):
        raise ExportRefusal("the section 10 artifact lists a triple that is not an object")
    got = Counter((t.get("seed_id"), t.get("scenario_set"), t.get("campaign_epoch"), t.get("speaker"),
                   t.get("partition"), t.get("journal_nonce")) for t in artifact["triples"])
    missing, extra = expected - got, got - expected
    if missing or extra:
        def listed(c: Counter) -> str:
            keys = sorted(c.elements(), key=str)
            if not keys:
                return "none"
            more = f" and {len(keys) - 6} more" if len(keys) > 6 else ""
            return ", ".join(_triple_label(k) for k in keys[:6]) + more
        raise ExportRefusal(f"the section 10 artifact's {len(artifact['triples'])} triples are not the registered "
                            f"final set of {final}: missing {listed(missing)}; not registered, or listed twice: "
                            f"{listed(extra)}")
    return RegisteredPlan(len(scenarios), decomposition_set)


# ------------------------------------------------------------------ the page vocabulary (data)


@dataclass(frozen=True)
class MeasureSpec:
    """One grade the page can show: the rows it reads (`row`), or the flag it reads off another measure's rows
    (`flag_of` = kind, key, flag), its values (low to high), and the digest a current row carries."""
    id: str
    row: tuple[str, str] | None
    flag_of: tuple[str, str, str] | None
    label: str
    kind: str
    values: tuple[str, ...]
    definition: str | None
    digest: str

    @property
    def source(self) -> tuple[str, str]:
        return self.row if self.row is not None else (self.flag_of[0], self.flag_of[1])

    def exported(self) -> dict[str, Any]:
        return {"id": self.id, "row": list(self.row) if self.row else None, "label": self.label, "kind": self.kind,
                "values": list(self.values), "definition": self.definition}


@dataclass(frozen=True)
class CampaignModels:
    """The models the campaign registered (the page vocabulary's campaign_models), which the page's text names:
    `target`, the Inspect provider/model string of the target (a manifest's models.target.inspect_name, a transcript's
    source.model); `target_served`, the model strings the provider returned (models.target.served_model_strings, a
    transcript's source.model_version when it records one); `judge`, the judge of record (every judgment's
    judge_model, the manifest's artifacts.judge_of_record.judge_model); `target_temperature`, the sampling temperature
    the page states (a manifest's models.target.config.temperature; Antigravity review of 2026-09-25)."""
    target: tuple[str, ...]
    target_served: tuple[str, ...]
    judge: tuple[str, ...]
    target_temperature: float


# the lists of model strings; target_temperature is the one number
CAMPAIGN_MODEL_KEYS = ("target", "target_served", "judge")


@dataclass(frozen=True)
class Vocabulary:
    measures: tuple[MeasureSpec, ...]
    mechanisms: dict[str, dict[str, str]]
    mechanism_of: dict[str, str]
    example: dict[str, Any]
    samples: dict[str, Any]
    models: CampaignModels

    def by_row(self) -> dict[tuple[str, str], MeasureSpec]:
        return {m.row: m for m in self.measures if m.row is not None}


def load_vocabulary(path: Path, rubric: Mapping[str, Any], registry: Mapping[str, Any]) -> Vocabulary:
    """The measure map, mechanisms, example, sample settings and the campaign's registered models, the measures
    checked against the rubric (tier rows: its tier ids in order, its flags) and the outcome registry (outcome rows: the
    dimension's values in order, `ordinal` iff the kind is ordinal, the definition), and each campaign_models list a
    non-empty list of distinct strings. Every problem is refused by name."""
    doc = _load(path, "the page vocabulary")
    problems: list[str] = []
    tiers = tuple(t["id"] for t in rubric.get("tiers") or [])
    flags = {f["id"] for f in rubric.get("flags") or []}
    tier_instruments = {k for k in (registry.get("tier_instruments") or {}) if not k.startswith("_")}
    dims = {d["id"]: d for d in registry.get("dimensions") or []}
    rubric_digest = judge_runner.rubric_digest(dict(rubric))
    measures: list[MeasureSpec] = []
    raw = doc.get("measures") if isinstance(doc, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ExportRefusal(f"the page vocabulary {path} has no measures list")
    pending_flags: list[tuple[int, dict]] = []
    for i, m in enumerate(raw):
        where = f"measure {i + 1} ({m.get('id') if isinstance(m, dict) else m!r})"
        if not isinstance(m, dict) or not _text(m.get("id")) or not _text(m.get("label")):
            problems.append(f"{where}: needs an id and a label")
            continue
        values = m.get("values")
        if m.get("kind") not in MEASURE_KINDS:
            problems.append(f"{where}: kind {m.get('kind')!r} is not one of {list(MEASURE_KINDS)}")
            continue
        if not (isinstance(values, list) and values and all(_text(v) for v in values)
                and len(set(values)) == len(values)):
            problems.append(f"{where}: values must be a non-empty list of distinct strings")
            continue
        row = m.get("row")
        if row is None:
            pending_flags.append((i, m))
            continue
        if not (isinstance(row, list) and len(row) == 2 and all(_text(x) for x in row)):
            problems.append(f"{where}: row must be [kind, key] or null")
            continue
        kind, key = row
        if kind == "tier":
            if key not in tier_instruments:
                problems.append(f"{where}: tier instrument {key!r} is not in the outcome registry")
            elif tuple(values) != tiers:
                problems.append(f"{where}: values {values} are not the rubric's tiers in order {list(tiers)}")
            elif m["kind"] != "ordinal":
                problems.append(f"{where}: a tier is ordinal, not {m['kind']}")
            else:
                measures.append(MeasureSpec(m["id"], (kind, key), None, m["label"], m["kind"], tuple(values), None,
                                            rubric_digest))
        elif kind == "outcome":
            dim = dims.get(key)
            if dim is None:
                problems.append(f"{where}: outcome dimension {key!r} is not in the outcome registry")
            elif list(values) != list(dim.get("values") or []):
                problems.append(f"{where}: values {values} are not the registry's {dim.get('values')}")
            elif (m["kind"] == "ordinal") != (dim.get("ordinal") is True) or m["kind"] == "binary":
                problems.append(f"{where}: kind {m['kind']} disagrees with the registry "
                                f"(ordinal: {dim.get('ordinal')})")
            else:
                digest = prompt_digest(dim["detection"]["judge_prompt_ref"])
                measures.append(MeasureSpec(m["id"], (kind, key), None, m["label"], m["kind"], tuple(values),
                                            dim.get("definition"), digest))
        else:
            problems.append(f"{where}: row kind {kind!r} is neither tier nor outcome")
    mapped = {x.row: x for x in measures}
    for i, m in pending_flags:
        where = f"measure {i + 1} ({m['id']})"
        f = m.get("flag_of")
        src = tuple(f.get("row") or ()) if isinstance(f, dict) else ()
        if len(src) != 2 or not _text(f.get("flag")):
            problems.append(f"{where}: a measure without a row needs flag_of {{row: [kind, key], flag}}")
        elif src not in mapped:
            problems.append(f"{where}: flag_of row {list(src)} is not itself a mapped measure")
        elif src[0] == "tier" and f["flag"] not in flags:
            problems.append(f"{where}: flag {f['flag']!r} is not one of the rubric's flags {sorted(flags)}")
        elif m["kind"] != "binary" or len(m["values"]) != 2:
            problems.append(f"{where}: a flag measure is binary with two values (false, then true)")
        else:
            measures.append(MeasureSpec(m["id"], None, (src[0], src[1], f["flag"]), m["label"], m["kind"],
                                        tuple(m["values"]), None, mapped[src].digest))
    ids = [x.id for x in measures]
    if len(ids) != len(set(ids)):
        problems.append(f"measure ids repeat: {sorted(k for k, n in Counter(ids).items() if n > 1)}")
    rows = [x.row for x in measures if x.row]
    if len(rows) != len(set(rows)):
        problems.append("two measures read the same rows")
    mech = doc.get("mechanisms")
    mechanisms: dict[str, dict[str, str]] = {}
    mechanism_of: dict[str, str] = {}
    if not isinstance(mech, dict) or not mech:
        problems.append("mechanisms must map each mechanism id to {title, question, seeds}")
    else:
        for mid, entry in mech.items():
            if not (isinstance(entry, dict) and _text(entry.get("title")) and _text(entry.get("question"))
                    and isinstance(entry.get("seeds"), list) and all(_text(s) for s in entry["seeds"])):
                problems.append(f"mechanism {mid!r}: needs a title, a question and a list of seeds")
                continue
            mechanisms[mid] = {"title": entry["title"], "question": entry["question"]}
            for sid in entry["seeds"]:
                if sid in mechanism_of:
                    problems.append(f"seed {sid} is listed under mechanisms {mechanism_of[sid]!r} and {mid!r}")
                mechanism_of[sid] = mid
    example = doc.get("example")
    if not (isinstance(example, dict) and _text(example.get("seed_id")) and _count(example.get("turn"))
            and example["turn"] >= 1):
        problems.append("example must be {seed_id, turn}")
    samples = doc.get("samples")
    if not (isinstance(samples, dict) and isinstance(samples.get("seed_ids"), list) and samples["seed_ids"]
            and _count(samples.get("epochs")) and samples["epochs"] >= 1 and _count(samples.get("rng_seed"))):
        problems.append("samples must be {seed_ids, epochs, rng_seed}")
    cm = doc.get("campaign_models")
    if not isinstance(cm, dict):
        problems.append(f"campaign_models must be {{{', '.join(CAMPAIGN_MODEL_KEYS)}}}: the model strings the campaign "
                        f"registered, which every exported run must record")
    else:
        for key in CAMPAIGN_MODEL_KEYS:
            specs = cm.get(key)
            if not (isinstance(specs, list) and specs and all(_text(s) for s in specs) and len(set(specs)) == len(specs)):
                problems.append(f"campaign_models.{key} must be a non-empty list of distinct model strings, not "
                                f"{specs!r}")
        temperature = cm.get("target_temperature")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            problems.append(f"campaign_models.target_temperature must be the number the page states, not "
                            f"{temperature!r}")
    if problems:
        raise ExportRefusal(f"the page vocabulary {path}: " + "; ".join(problems))
    # measures keep the file's order (a flag measure was held back only until its source was known)
    order = {m["id"]: i for i, m in enumerate(raw) if isinstance(m, dict)}
    measures.sort(key=lambda x: order[x.id])
    models = CampaignModels(*(tuple(cm[key]) for key in CAMPAIGN_MODEL_KEYS), float(cm["target_temperature"]))
    return Vocabulary(tuple(measures), mechanisms, mechanism_of, dict(example), dict(samples), models)


# ------------------------------------------------------------------ the registered wording (checked against the note)


@dataclass(frozen=True)
class Wording:
    rows: dict[str, str]          # 10.2: row1..row5 -> the 'What may be said' cell, verbatim
    statements: dict[str, str]    # 10.3: statement id -> the bullet's text after its label, verbatim


def _section(note: str, heading: str, where: Path) -> str:
    start = note.find("\n" + heading)
    if start < 0:
        raise ExportRefusal(f"{where}: no section starting {heading!r}")
    end = note.find("\n### ", start + 1)
    return note[start + 1: end if end >= 0 else len(note)]


def note_table_rows(section: str, header: str) -> list[list[str]]:
    """The body rows of the markdown table whose header row names `header`, as stripped cells."""
    lines = section.splitlines()
    at = next((i for i, ln in enumerate(lines) if ln.startswith("|") and header in ln), None)
    if at is None:
        return []
    rows = []
    for ln in lines[at + 2:]:
        if not ln.startswith("|"):
            break
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows


def note_bullets(section: str, list_heading: str) -> dict[str, str]:
    """The nested bullets under the top-level bullet that starts `list_heading`, as {bold label: text after it}, each
    bullet's wrapped lines joined with single spaces (the text a markdown reader sees)."""
    lines = section.splitlines()
    at = next((i for i, ln in enumerate(lines) if ln.startswith(list_heading)), None)
    if at is None:
        return {}
    bullets: list[str] = []
    cur: str | None = None
    for ln in lines[at + 1:]:
        if ln.startswith("  - "):
            if cur is not None:
                bullets.append(cur)
            cur = ln[4:].strip()
        elif ln.startswith("    ") and cur is not None:
            cur += " " + ln.strip()
        elif ln.startswith("  ") and cur is None:
            continue            # the heading bullet's own continuation line
        else:
            break
    if cur is not None:
        bullets.append(cur)
    out = {}
    for b in bullets:
        m = re.match(r"\*\*(.+?):\*\* (.*)$", b)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def load_wording(path: Path, design_note: Path) -> Wording:
    """The registered texts, refused unless each is the design note's, character for character."""
    doc = _load(path, "the registered wording")
    if not Path(design_note).is_file():
        raise ExportRefusal(f"the design note {design_note} not found")
    note = Path(design_note).read_text(encoding="utf-8")
    problems: list[str] = []
    s2, s3 = doc.get("section_10_2") or {}, doc.get("section_10_3") or {}
    table = note_table_rows(_section(note, s2.get("heading", "### 10.2 "), design_note), s2.get("table_header", ""))
    rows: dict[str, str] = {}
    data_rows = s2.get("rows") or []
    if len(table) != len(data_rows):
        problems.append(f"section 10.2's table has {len(table)} rows, the wording file {len(data_rows)}")
    for i, (cells, row) in enumerate(zip(table, data_rows), 1):
        mine = [row.get(k) for k in ("primary_test", "general_gate", "prospective_partition", "text")]
        if row.get("row_id") != f"row{i}":
            problems.append(f"wording row {i} is named {row.get('row_id')!r}, not row{i}")
        elif cells != mine:
            problems.append(f"{row.get('row_id')} differs from section 10.2's table row {i}")
        else:
            rows[row["row_id"]] = row["text"]
    bullets = note_bullets(_section(note, s3.get("heading", "### 10.3 "), design_note), s3.get("list_heading", ""))
    statements: dict[str, str] = {}
    for st in s3.get("statements") or []:
        sid, label = st.get("statement_id"), st.get("label")
        if bullets.get(label) != st.get("text"):
            problems.append(f"statement {sid!r} differs from section 10.3's bullet {label!r}")
        else:
            statements[sid] = st["text"]
    if not rows or not statements:
        problems.append("no registered row or statement was read")
    if problems:
        raise ExportRefusal(f"the registered wording {path} is not the design note's ({design_note}): "
                            + "; ".join(problems))
    return Wording(rows, statements)


# ------------------------------------------------------------------ runs


def publication_problems(manifest: Mapping[str, Any]) -> list[str]:
    """Why a run may not be published (docs/petri_integration_design.md section 4, 'Publication conditions'), or []."""
    problems = []
    harness = manifest.get("harness") if isinstance(manifest.get("harness"), dict) else {}
    if not _text(harness.get("environment_lock_sha256")):
        problems.append("harness.environment_lock_sha256 is missing, so the environment lock the run executed under "
                        "is not bound")
    art = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    if not _text(art.get("raw_eval_log_sha256")) or not art.get("raw_eval_log_custody"):
        problems.append("the raw .eval log is not bound with its custody (artifacts.raw_eval_log_sha256, "
                        "raw_eval_log_custody)")
    if art.get("raw_eval_log_published") is not False:
        problems.append(f"artifacts.raw_eval_log_published is {art.get('raw_eval_log_published')!r}; the raw .eval is "
                        f"never published")
    sanitiser = art.get("sanitiser")
    if not _text(art.get("sanitised_log_sha256")) or not (isinstance(sanitiser, dict)
                                                          and _text(sanitiser.get("allowlist_sha256"))):
        problems.append("no sanitised allowlist projection is bound (artifacts.sanitised_log_sha256, sanitiser)")
    hold = manifest.get("holdout")
    if not isinstance(hold, dict) or not isinstance(hold.get("consumed"), bool):
        problems.append("the manifest has no holdout block recording whether a sealed phrase was consumed")
    elif hold["consumed"] and not hold.get("consumption_registry_ref"):
        problems.append("the holdout block records a consumed sealed phrase without its registry entry")
    checks = (manifest.get("execution") or {}).get("contract_checks") or {}
    seal = checks.get("holdout_seal")
    status = seal.get("status") if isinstance(seal, dict) else seal
    if status != "pass":
        problems.append(f"the holdout-seal contract check is {status!r}, not 'pass'")
    return problems


def model_problems(manifest: Mapping[str, Any], models: CampaignModels) -> list[str]:
    """Why a run's manifest does not record the campaign's registered models, or [] (Codex review of 2026-09-25: a
    registered fire run on another target, or graded by another judge, was published under the page's text, which
    names the target and says the same model graded it): the target Inspect resolved (models.target.inspect_name),
    every model string the provider returned for it (models.target.served_model_strings, at least one) and the judge
    of record (artifacts.judge_of_record.judge_model)."""
    problems = []
    roles = manifest.get("models")
    target = roles.get("target") if isinstance(roles, dict) else None
    if not isinstance(target, dict):
        problems.append("the manifest records no models.target")
    else:
        name = target.get("inspect_name")
        if name not in models.target:
            problems.append(f"its target (models.target.inspect_name) is {name!r}, not a registered target "
                            f"{list(models.target)}")
        served = target.get("served_model_strings")
        if not (isinstance(served, list) and served):
            problems.append(f"models.target.served_model_strings is {served!r}, not the model strings the provider "
                            f"returned")
        else:
            other = [s for s in served if s not in models.target_served]
            if other:
                problems.append(f"the provider served the target as {other!r} (models.target.served_model_strings), "
                                f"not a registered model string {list(models.target_served)}")
        # the page states the sampling temperature; a run sampled otherwise is not the page's data (Antigravity
        # review of 2026-09-25)
        config = target.get("config")
        temperature = config.get("temperature") if isinstance(config, dict) else None
        if isinstance(temperature, bool) or temperature != models.target_temperature:
            problems.append(f"its target was sampled at temperature {temperature!r} (models.target.config."
                            f"temperature), not the registered {models.target_temperature}")
    art = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    of_record = art.get("judge_of_record")
    judge = of_record.get("judge_model") if isinstance(of_record, dict) else None
    if judge not in models.judge:
        problems.append(f"its judge of record (artifacts.judge_of_record.judge_model) is {judge!r}, not a registered "
                        f"judge {list(models.judge)}")
    return problems


def manifest_identity(manifest: Mapping[str, Any], where: str) -> str:
    """The run manifest's identity digest (chain.identity_sha256), which every transcript record of the run names in
    provenance.run_manifest.sha256; refused unless it is recorded and is the identity digest of the manifest body
    (manifest.identity_digest), so a record bound to it is bound to this manifest."""
    chain = manifest.get("chain")
    recorded = chain.get("identity_sha256") if isinstance(chain, dict) else None
    if not (isinstance(recorded, str) and re.fullmatch(r"[0-9a-f]{64}", recorded)):
        raise ExportRefusal(f"run {where}: the manifest records no identity digest (chain.identity_sha256 "
                            f"{recorded!r}), so its transcripts cannot be shown to be bound to it")
    try:
        body = identity_digest(dict(manifest))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ExportRefusal(f"run {where}: the manifest's identity digest cannot be computed "
                            f"({type(exc).__name__}: {exc})") from exc
    if body != recorded:
        raise ExportRefusal(f"run {where}: chain.identity_sha256 {recorded[:12]} is not the identity digest of the "
                            f"manifest body ({body[:12]}), so a transcript bound to it is bound to no manifest here")
    return recorded


def _tool_calls_ok(calls: Any) -> bool:
    return isinstance(calls, list) and all(
        isinstance(c, dict) and _text(c.get("call_id")) and _text(c.get("name"))
        and isinstance(c.get("arguments") or {}, dict) for c in calls)


def transcript_problems(record: Mapping[str, Any], identity: str, models: CampaignModels) -> list[str]:
    """Why one transcript record is not a record of this run that the exporter can read, or [] (Codex review of
    2026-09-25: the records were read without checking that each is bound to its run).

    - Its binding: provenance.run_manifest.sha256 must be the run manifest's identity digest, the pairing check
      scripts/petri_audit/summary.py makes (a record naming another identity, or none, came from another manifest).
    - Its source: source.model a registered target, and source.model_version, when the record carries one, a
      registered served model string.
    - Its shape, as far as the exporter and rules.rule_outcomes read it: a conversation id; a non-empty list of turns,
      each with an integer turn_id unique in the record, a role of the transcript schema and a text; tool calls only
      on an assistant turn, each with a call id, a name and object arguments; and the tool-call pairing
      framework.tool_call_problems checks (every tool turn answers an earlier call, once; call ids unique)."""
    problems: list[str] = []
    if not _text(record.get("conversation_id")):
        problems.append("no conversation_id")
    prov = record.get("provenance")
    run_manifest = prov.get("run_manifest") if isinstance(prov, dict) else None
    bound = run_manifest.get("sha256") if isinstance(run_manifest, dict) else None
    if bound != identity:
        problems.append("provenance.run_manifest names " + ("no manifest identity" if bound is None else
                                                            f"another manifest identity ({str(bound)[:12]})"))
    source = record.get("source")
    if not isinstance(source, dict):
        problems.append("no source block, so the model it records cannot be checked")
    else:
        if source.get("model") not in models.target:
            problems.append(f"source.model {source.get('model')!r} is not a registered target {list(models.target)}")
        version = source.get("model_version")
        if version is not None and version not in models.target_served:
            problems.append(f"source.model_version {version!r} is not a registered model string "
                            f"{list(models.target_served)}")
    turns = record.get("turns")
    if not (isinstance(turns, list) and turns):
        return problems + ["no turns"]
    shape: list[str] = []
    for n, t in enumerate(turns, 1):
        if not isinstance(t, dict):
            shape.append(f"turn #{n} is not an object")
            continue
        if not _count(t.get("turn_id")):
            shape.append(f"turn #{n}: turn_id {t.get('turn_id')!r} is not an integer")
        if t.get("role") not in TRANSCRIPT_ROLES:
            shape.append(f"turn #{n}: role {t.get('role')!r} is not one of {list(TRANSCRIPT_ROLES)}")
        if not isinstance(t.get("text"), str):
            shape.append(f"turn #{n}: text is not a string")
        if t.get("tool_calls") is not None and not (t.get("role") == "assistant" and _tool_calls_ok(t["tool_calls"])):
            shape.append(f"turn #{n}: tool_calls are not an assistant turn's list of {{call_id, name, arguments}}")
    ids = [t.get("turn_id") for t in turns if isinstance(t, dict) and _count(t.get("turn_id"))]
    if len(ids) != len(set(ids)):
        shape.append(f"turn ids repeat: {sorted(k for k, n in Counter(ids).items() if n > 1)}")
    # the pairing check reads the fields the shape check vouches for, so it runs only on a record that passes it
    return problems + (shape or tool_call_problems(dict(record)))


def collapse_retries(judgments: Sequence[dict]) -> tuple[list[dict], int]:
    """The latest judgment per `judge_runner.dedupe_key`, in file order, and how many it superseded: a retried null is
    decided by its retry, as the section 10 analysis and the run's own totals decide it."""
    latest: dict[tuple, int] = {}
    for i, j in enumerate(judgments):
        latest[judge_runner.dedupe_key(j)] = i
    keep = sorted(latest.values())
    return [judgments[i] for i in keep], len(judgments) - len(keep)


@dataclass
class RunData:
    stem: str
    path: Path
    manifest: dict
    rows: list[dict]
    superseded_by_retry: int
    records: dict[str, dict]
    rules: dict[str, dict]            # conversation id -> the rule-outcome record (its outcomes and annotator)
    trees: dict[str, tuple[dict, dict]]


def load_run(path: Path, recorded: Mapping[str, Any], seeds: Mapping[str, dict], models: CampaignModels) -> RunData:
    """One run directory, refused unless its publication conditions hold, its files are the bytes the artifact and
    its own manifest bound, it records the campaign's registered models (model_problems; every judgment's judge_model;
    every transcript's source) and every transcript record is bound to its manifest (transcript_problems); its analysis
    rows rebuilt as the section 10 analysis rebuilt them."""
    path = Path(path)
    where = path.name
    if not path.is_dir():
        raise ExportRefusal(f"{path}: no such run directory")
    manifest = _load(path / "manifest.json", f"run {where}:")
    if not isinstance(manifest, dict):
        raise ExportRefusal(f"run {where}: manifest.json is not an object")
    problems = publication_problems(manifest)
    if problems:
        raise ExportRefusal(f"run {where}: the publication conditions do not hold: " + "; ".join(problems))
    if sha256_file(path / "manifest.json") != recorded.get("manifest_sha256"):
        raise ExportRefusal(f"run {where}: manifest.json is not the manifest the section 10 artifact read (sha256 "
                            f"differs from {recorded.get('manifest_sha256')!r})")
    if manifest.get("run_id") != recorded.get("run_id"):
        raise ExportRefusal(f"run {where}: run id {manifest.get('run_id')!r} is not the artifact's "
                            f"{recorded.get('run_id')!r}")
    problems = model_problems(manifest, models)
    if problems:
        raise ExportRefusal(f"run {where} is not a run of the campaign's registered models, which the page names: "
                            + "; ".join(problems))
    identity = manifest_identity(manifest, where)
    art = manifest.get("artifacts") or {}
    files = {family: path / name for family, name in ARTIFACT_FILENAMES.items()}
    for family in ("judgments", "transcripts", "rule_outcomes"):
        if not files[family].is_file():
            raise ExportRefusal(f"run {where}: {files[family].name} is missing")
    judgments_sha = sha256_file(files["judgments"])
    if judgments_sha != recorded.get("judgments_sha256"):
        raise ExportRefusal(f"run {where}: judgments.jsonl is not the file the section 10 artifact read (sha256 "
                            f"{judgments_sha[:12]} against the artifact's "
                            f"{str(recorded.get('judgments_sha256'))[:12]})")
    for family in ("judgments", "transcripts", "rule_outcomes"):
        if sha256_file(files[family]) != art.get(f"{family}_sha256"):
            raise ExportRefusal(f"run {where}: {files[family].name} is not the file its manifest binds")
    judgments = _jsonl(files["judgments"], f"run {where}:")
    # every judgment, a superseded retry too: the file is the run's record of who graded it
    judges = Counter(repr(j.get("judge_model")) for j in judgments if j.get("judge_model") not in models.judge)
    if judges:
        raise ExportRefusal(f"run {where}: {sum(judges.values())} judgment(s) record judge_model "
                            f"{', '.join(sorted(judges))}, not a registered judge {list(models.judge)}, and the page "
                            f"says the registered judge graded every reply")
    collapsed, superseded = collapse_retries(judgments)
    try:
        rows = judge_runner.analysis_rows(collapsed, manifest, dict(seeds))
    except (ValueError, KeyError) as exc:
        raise ExportRefusal(f"run {where}: judge_runner.analysis_rows refused it: {exc}") from exc
    records: dict[str, dict] = {}
    bad: list[str] = []
    for n, rec in enumerate(_jsonl(files["transcripts"], f"run {where}:"), 1):
        found = transcript_problems(rec, identity, models)
        if found:
            bad.append(f"record {n} ({str(rec.get('conversation_id'))[:12]}): " + "; ".join(found[:3]))
            continue
        cid = rec["conversation_id"]
        if cid in records:
            raise ExportRefusal(f"run {where}: two transcript records for conversation {cid}")
        records[cid] = rec
    if bad:
        more = f"; and {len(bad) - 3} more" if len(bad) > 3 else ""
        raise ExportRefusal(f"run {where}: {len(bad)} transcript record(s) are not records of this run the exporter "
                            f"can read: " + "; ".join(bad[:3]) + more)
    rules: dict[str, dict] = {}
    for rule in _jsonl(files["rule_outcomes"], f"run {where}:"):
        cid = rule.get("conversation_id")
        if cid in rules:
            raise ExportRefusal(f"run {where}: two rule outcomes for conversation {cid}")
        if not isinstance(rule.get("outcomes"), dict):
            raise ExportRefusal(f"run {where}: the rule outcome of conversation {cid} has no outcomes object")
        rules[cid] = rule
    trees: dict[str, tuple[dict, dict]] = {}
    for tree in manifest.get("trees") or []:
        for branch in tree.get("branches") or []:
            trees[branch["conversation_id"]] = (tree, branch)
    return RunData(where, path, manifest, rows, superseded, records, rules, trees)


# ------------------------------------------------------------------ seeds


def seed_cells(seed: Mapping[str, Any]) -> tuple[list[str | None], dict[tuple[str | None, str], dict]]:
    """A seed's speakers in first-appearance order, and its arm for each (speaker, register): the speaker is the arm's
    `user_is` when speaker identity is a declared factor, none otherwise; the register is that of the arm's turn-1
    text (the section 10 analysis reads them the same way)."""
    factor = (seed.get("speaker_identity") or {}).get("policy") == "factor"
    texts = texts_by_key(dict(seed))
    speakers: list[str | None] = []
    cells: dict[tuple[str | None, str], dict] = {}
    for arm in seed["protocol"]["arms"]:
        register = texts[arm["turns"][0]["text_ref"]]["register"]
        speaker = arm["user_is"] if factor else None
        if register not in REGISTERS:
            raise ExportRefusal(f"seed {seed['seed_id']}: arm {arm['id']} is in register {register!r}")
        if (speaker, register) in cells:
            raise ExportRefusal(f"seed {seed['seed_id']}: two arms realise ({speaker}, {register})")
        if speaker not in speakers:
            speakers.append(speaker)
        cells[(speaker, register)] = arm
    return speakers, cells


def swaps_of(seed_id: str, declared: Mapping[str, Any] | None, n_turns: int) -> dict[str, list[list[Any]]] | None:
    """The declared [clinical span, careful-lay span] pairs of a second-set seed per speaker prefix ('' without speaker
    arms, else '<speaker>_') as a list indexed by exchange, a turn shared by both speakers applied to each."""
    if declared is None:
        return None
    out: dict[str, list[list[Any]]] = {}
    for key, pairs in declared.items():
        turn, _, rest = key.partition("_")
        if not (turn.startswith("t") and turn[1:].isdigit() and rest.endswith(CAREFUL_LAY)):
            raise ExportRefusal(f"swaps of {seed_id}: key {key!r} is not t<NN>_[<speaker>_]{CAREFUL_LAY}")
        n = int(turn[1:])
        if not 1 <= n <= n_turns:
            raise ExportRefusal(f"swaps of {seed_id}: key {key!r} names turn {n} of {n_turns}")
        prefix = rest[: -len(CAREFUL_LAY)]
        out.setdefault(prefix, [[] for _ in range(n_turns)])[n - 1] = pairs
    shared = out.pop("", None) if len(out) > 1 else None
    for per in (out.values() if shared else ()):
        for i, pairs in enumerate(shared):
            if pairs:
                if per[i]:
                    raise ExportRefusal(f"swaps of {seed_id}: turn {i + 1} is declared both shared and per speaker")
                per[i] = pairs
    return out


# ------------------------------------------------------------------ conversations


def expected_rows(seed: Mapping[str, Any], assistant_index: int) -> set[tuple[str, str]]:
    """The rows judge_runner.plan_record plans for one assistant message: the response-only tier, the contextual tier
    from the second assistant message of the conversation on, and every outcome dimension the seed judges (a gated
    dimension is planned as a not-applicable row, so it has a row too)."""
    judge = seed["judge"]
    out = {("outcome", d) for d in judge["outcome_dimensions"]}
    if judge["advice_tier"].get("response_only"):
        out.add(("tier", "response_only"))
    if judge["advice_tier"].get("contextual") and assistant_index >= 2:
        out.add(("tier", "contextual"))
    return out


def split_exchanges(record: Mapping[str, Any], where: str) -> tuple[list[dict], int]:
    """The record split at its user turns, and the number of system turns before the first (not part of any
    exchange). A message before the first user turn that is not a system turn is refused."""
    out: list[dict] = []
    system = 0
    for t in record.get("turns") or []:
        if t["role"] == "user":
            out.append({"user": t["text"], "msgs": []})
        elif out:
            out[-1]["msgs"].append(t)
        elif t["role"] == "system":
            system += 1
        else:
            raise ExportRefusal(f"{where}: a {t['role']} turn precedes the first user turn")
    return out, system


def _cell(rows: Sequence[dict], m: MeasureSpec, where: str) -> dict | None:
    """The page cell of one measure at one exchange, from its final rows: the row under the measure's current digest,
    or a single row under another digest, shown flagged `superseded` (never compared); two rows under the current
    digest, or several under others, are refused. {"v": value}, {"v": null} for a null answer, {"na": reason}."""
    if not rows:
        return None
    current = [r for r in rows if r.get("prompt_file_digest") == m.digest]
    if len(current) > 1:
        raise ExportRefusal(f"{where}: {len(current)} final rows for {m.source[0]}:{m.source[1]} under digest "
                            f"{m.digest}")
    if not current and len(rows) > 1:
        raise ExportRefusal(f"{where}: {len(rows)} final rows for {m.source[0]}:{m.source[1]}, none under the current "
                            f"digest {m.digest}")
    row = current[0] if current else rows[0]
    if row.get("not_applicable_reason") or row.get("value") == judge_runner.NA:
        cell: dict[str, Any] = {"na": row.get("not_applicable_reason") or "the judge answered not_applicable"}
    elif row.get("value") is None:
        cell = {"v": None}
    elif m.flag_of is None:
        if row["value"] not in m.values:
            raise ExportRefusal(f"{where}: {m.id} value {row['value']!r} is not one of its values {list(m.values)}")
        cell = {"v": row["value"]}
    else:
        flags = row.get("flags")
        flag = flags.get(m.flag_of[2]) if isinstance(flags, dict) else None
        cell = {"v": m.values[1] if flag is True else m.values[0] if flag is False else None}
    if row.get("prompt_file_digest") != m.digest:
        cell["superseded"] = row.get("prompt_file_digest") or "none recorded"
    return cell


def build_conversation(run: RunData, cid: str, seed: Mapping[str, Any], arm: Mapping[str, Any], vocab: Vocabulary,
                       rows: Sequence[dict], notes: Counter) -> list[dict]:
    """One conversation's exchanges: the scripted user turn, the graded reply (the last assistant message of the
    exchange, which the judge grades as final_in_exchange), the other messages as interim (a tool result flagged
    `fixture`), and the grades of the graded reply per measure."""
    where = f"run {run.stem} conversation {cid[:12]}"
    record = run.records.get(cid)
    if record is None:
        raise ExportRefusal(f"{where}: no transcript record")
    exs, system = split_exchanges(record, where)
    notes["system turns outside any exchange"] += system
    if len(exs) != len(arm["turns"]):
        raise ExportRefusal(f"{where}: {len(exs)} exchanges, but arm {arm['id']} scripts {len(arm['turns'])}")
    by_row = vocab.by_row()
    final: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("exchange_index") is None or r.get("final_in_exchange") is None:
            raise ExportRefusal(f"{where}: a judgment row carries no exchange_index or final_in_exchange (judged "
                                f"before the exchange ordinal existed), so it cannot be placed")
        if (r["kind"], r["key"]) not in by_row:
            raise ExportRefusal(f"{where}: rows of {r['kind']}:{r['key']} have no measure in the page vocabulary")
        if r["final_in_exchange"] is True:
            final[(r["exchange_index"], r["kind"], r["key"])].append(r)
        else:
            notes["grades of interim messages not shown (the page shows one graded reply per exchange)"] += 1
    stray = sorted({e for e, _, _ in final if not 1 <= e <= len(exs)})
    if stray:
        raise ExportRefusal(f"{where}: final rows for exchange(s) {stray}, which the transcript does not have")
    calls = {c["call_id"]: c for t in record["turns"] if t["role"] == "assistant" for c in t.get("tool_calls") or []}
    out: list[dict] = []
    assistant_index = 0
    for i, ex in enumerate(exs, 1):
        assistants = [m for m in ex["msgs"] if m["role"] == "assistant"]
        if not assistants:
            raise ExportRefusal(f"{where}: exchange {i} has no assistant reply")
        reply = assistants[-1]
        assistant_index += len(assistants)
        missing = sorted(expected_rows(seed, assistant_index) - {(k, key) for (e, k, key) in final if e == i})
        if missing:
            raise ExportRefusal(f"{where}: no final row for exchange {i}: "
                                + ", ".join(f"{k}:{key}" for k, key in missing))
        turn_ids = {r["turn_id"] for (e, _, _), rs in final.items() if e == i for r in rs}
        if turn_ids != {reply["turn_id"]}:
            raise ExportRefusal(f"{where}: exchange {i}'s final rows grade turn(s) {sorted(turn_ids)}, not its last "
                                f"assistant message (turn {reply['turn_id']})")
        interim = []
        for msg in ex["msgs"]:
            if msg is reply:
                continue
            if msg["role"] == "assistant":
                interim.append({"role": "assistant", "text": msg.get("text") or ""})
            elif msg["role"] == "tool":
                call = calls.get(msg.get("tool_call_id"))
                scripted = None
                if call is not None and not call.get("parse_error"):
                    scripted, _, _ = tool_result_for(dict(seed), call["name"], dict(call.get("arguments") or {}))
                if scripted is None or scripted != msg.get("text"):
                    raise ExportRefusal(f"{where}: the tool result at turn {msg['turn_id']} is not the seed's scripted "
                                        f"result, and the page labels every tool result as text the study wrote")
                interim.append({"role": "tool", "text": msg["text"], "fixture": True})
            else:
                raise ExportRefusal(f"{where}: exchange {i} carries a {msg['role']} turn")
        vals: dict[str, dict] = {}
        for m in vocab.measures:
            cell = _cell(final.get((i, *m.source), []), m, f"{where} exchange {i}")
            if cell is not None:
                vals[m.id] = cell
                if "superseded" in cell:
                    notes["cells graded under a superseded prompt or rubric (flagged, never compared)"] += 1
        text = reply.get("text") or ""
        out.append({"user": ex["user"], "reply": text if text.strip() else None, "reply_turn": reply["turn_id"],
                    "reply_is_graded": True, "interim": interim, "vals": vals})
    return out


# ------------------------------------------------------------------ status


def clinician_review(sources: Mapping[str, Any]) -> tuple[str, list[str]]:
    """'pending' while any source status is marked draft, with the sources that are; refused when none is, because
    no file records a clinician review and the exporter never infers one."""
    drafts = sorted(name for name, status in sources.items() if isinstance(status, str) and "draft" in status.lower())
    if not drafts:
        raise ExportRefusal("none of the rubric, the outcome registry or the seed file (nor any entry of them the page "
                            "uses) is marked draft, but no file records a clinician review: status.clinician_review "
                            "cannot be derived; record the review and extend the exporter (owner decision)")
    return REVIEW_PENDING, drafts


def vendor_pack(log: Path) -> dict[str, str | None]:
    """The latest (last-written) disclosure-log entry of lane 'petri' for anthropic: its pack version and when it was
    sent, or nulls when there is none. A line that does not parse is refused, never skipped."""
    latest = None
    if Path(log).is_file():
        for entry in _jsonl(log, "the disclosure log"):
            if entry.get("lane") == DISCLOSURE_LANE and entry.get("vendor") == DISCLOSURE_VENDOR:
                latest = entry
    if latest is None:
        return {"version": None, "sent": None}
    if not _text(latest.get("pack_version")) or not (latest.get("sent_utc") is None or _text(latest["sent_utc"])):
        raise ExportRefusal(f"the disclosure log {log}: its latest {DISCLOSURE_LANE} entry for {DISCLOSURE_VENDOR} has "
                            f"no pack_version, or a sent_utc that is not a string")
    return {"version": latest["pack_version"], "sent": latest.get("sent_utc")}


# ------------------------------------------------------------------ the export


@dataclass
class Export:
    summary: dict[str, Any]
    conversations: dict[str, Any]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Checkout:
    """Where an export's inputs come from. `runs_dir`: where the runs must sit, the directory the page's verify-chain
    command names, run from the root of the repository it belongs to. `identity`: given every file the export read,
    the commit that names them all, refused by name when there is none; it is recorded as provenance.exporter_commit.
    `has_commit`: whether a commit id names a commit object of that repository, so the analysis commit the page cites
    is one a reader can check out. `file_sha256_at`: the sha256 of a repository-relative file as a commit holds it, or
    None when the commit does not hold it, so the analysis commit can be shown to hold the inputs the artifact records.
    For a real export: the checkout's own data/petri/runs, checkout_identity, commit_exists and blob_sha256
    (REPOSITORY)."""
    runs_dir: Path
    identity: Callable[[Sequence[Path]], str]
    has_commit: Callable[[str], bool]
    file_sha256_at: Callable[[str, str], str | None]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def checkout_identity(paths: Sequence[Path], *, root: Path = ROOT) -> str:
    """The commit of the checkout at `root` (HEAD), refused unless it names every file the export read and the code
    that read them (Codex review of 2026-09-24: the exporter's revision was printed, never recorded). Each path must
    be inside the checkout and tracked there (a path absent from both the disk and the index is an absence the commit
    records too), and no tracked file of the checkout may differ from HEAD, staged or not: the code, the rubric, the
    judge prompts the digests are taken over and every other tracked input are then the commit's. Untracked files the
    export does not read do not matter."""
    root = Path(root).resolve()
    problems: list[str] = []
    rels: dict[str, Path] = {}
    for p in dict.fromkeys(Path(x) for x in paths):
        try:
            rels[p.resolve().relative_to(root).as_posix()] = p
        except ValueError:
            problems.append(f"{p} is outside the checkout {root}")
    try:
        head = _git(root, "rev-parse", "HEAD").strip()
        tracked = set(_git(root, "ls-files", "-z", "--", *rels).split("\0")) if rels else set()
        changed = _git(root, "status", "--porcelain", "--untracked-files=no").splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ExportRefusal(f"git cannot report on the checkout {root} ({detail}), so no exporter commit can be "
                            f"recorded") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        problems.append(f"HEAD is {head!r}, not a commit")
    problems += [f"{rel} is not tracked by git" for rel, p in rels.items() if rel not in tracked and p.exists()]
    if changed:
        problems.append(f"tracked files differ from HEAD: {'; '.join(line.strip() for line in changed)}")
    if problems:
        raise ExportRefusal("the exporter commit would not name everything the export read: " + "; ".join(problems)
                            + " (commit the inputs, or restore them, and export again)")
    return head


def commit_exists(sha: str, *, root: Path = ROOT) -> bool:
    """Whether `sha` is a commit object in the repository at `root` (`git cat-file -e <sha>^{commit}`; Codex review
    of 2026-09-25: the artifact's identity.commit was only format-checked, so a well-formed id of no commit reached the
    page as the analysis commit). A blob or tree id is not a commit. Git that cannot run is refused, never read as
    'no such commit'."""
    try:
        done = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True,
                              text=True)
    except OSError as exc:
        raise ExportRefusal(f"git cannot run in {root} ({exc}), so the analysis commit cannot be looked up") from exc
    return done.returncode == 0


def blob_sha256(commit: str, path: str, *, root: Path = ROOT) -> str | None:
    """The sha256 of `path` as `commit` holds it (`git cat-file blob <commit>:<path>`), or None when the commit holds
    no such file. Git that cannot run is refused, never read as 'no such file'."""
    try:
        done = subprocess.run(["git", "-C", str(root), "cat-file", "blob", f"{commit}:{path}"], capture_output=True)
    except OSError as exc:
        raise ExportRefusal(f"git cannot run in {root} ({exc}), so the analysis inputs cannot be looked up") from exc
    return hashlib.sha256(done.stdout).hexdigest() if done.returncode == 0 else None


# the inputs the section 10 artifact records (identity.inputs): its code and every data file it read
ANALYSIS_INPUTS = ("script", "judge_runner", "plan", "seed_file", "rubric", "outcome_registry")


def analysis_inputs_problem(artifact: Mapping[str, Any], checkout: Checkout) -> str | None:
    """Why the analysis commit does not name the analysis, or None (Codex review of 2026-09-25: any existing commit
    passed, so an unrelated one would reach the page and the pack as the analysis revision). The artifact records each
    input's repository path and sha256 (identity.inputs), with no uncommitted change (load_artifact); the commit must
    hold every one of them with those bytes."""
    ident = artifact["identity"]
    commit, inputs = ident["commit"], ident.get("inputs")
    if not isinstance(inputs, dict):
        return "records no identity.inputs, so its analysis commit cannot be shown to hold the code and data it read"
    missing = [n for n in ANALYSIS_INPUTS if n not in inputs]
    if missing:
        return f"records no identity.inputs for {missing}"
    for name in sorted(inputs):
        rec = inputs[name]
        path = rec.get("path") if isinstance(rec, dict) else None
        digest = rec.get("sha256") if isinstance(rec, dict) else None
        if not (isinstance(path, str) and re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*", path)
                and ".." not in path.split("/") and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
            return f"records identity.inputs.{name} as {rec!r}, not a repository path and a sha256"
        have = checkout.file_sha256_at(commit, path)
        if have != digest:
            return (f"records its {name} {path} as sha256 {digest[:12]}, but its analysis commit {commit[:12]} holds "
                    f"{'no such file' if have is None else have[:12]}; the commit the page cites is not the one the "
                    f"analysis ran from")
    return None


REPOSITORY = Checkout(RUNS_DIR, checkout_identity, commit_exists, blob_sha256)
SYNTHETIC_COMMIT = "SYNTHETIC"


def synthetic_checkout(root: Path, commit: str = SYNTHETIC_COMMIT) -> Checkout:
    """For SYNTHETIC input only (the tests, --write-samples): runs under `<root>/data/petri/runs`, a fixed exporter
    commit, and one analysis commit accepted, the synthetic artifact's (petri_multiturn_synthetic.ANALYSIS_COMMIT),
    since synthetic files are in no repository. The CLI never exports with it."""
    from scripts import petri_multiturn_synthetic as synthetic
    def file_sha256_at(sha: str, path: str) -> str | None:
        f = synthetic.input_file(Path(root), path)
        return sha256_file(f) if sha == synthetic.ANALYSIS_COMMIT and f.is_file() else None

    return Checkout(Path(root).joinpath(*RUNS_SUBPATH), lambda _paths: commit,
                    lambda sha: sha == synthetic.ANALYSIS_COMMIT, file_sha256_at)


def _check_chain(run_dirs: Sequence[Path], runs_dir: Path) -> None:
    """The page's command verifies the exported runs (Codex review of 2026-09-25): the chain under `runs_dir` exists,
    verifies (manifest digests, links and artifacts), and names every exported run. verify_chain succeeds with no chain
    file and checks only the manifests the chain names, so a run under this directory but outside the chain would be
    exported while the printed command never examined it."""
    chain = Path(runs_dir) / CHAIN_FILE
    if not chain.is_file():
        raise ExportRefusal(f"{runs_dir} has no {CHAIN_FILE}, so the page's command ({VERIFY_COMMAND}) would verify "
                            f"no run")
    try:
        ok, msg = verify_chain(Path(runs_dir))
        chained = {Path(line.strip().rsplit(" ", 1)[0]).parent.as_posix()
                   for line in chain.read_text(encoding="utf-8").splitlines() if line.strip()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ExportRefusal(f"the chain {chain} cannot be read ({type(exc).__name__}: {exc})") from exc
    if not ok:
        raise ExportRefusal(f"the chain under {runs_dir} does not verify: {msg}")
    outside = sorted(Path(p).name for p in run_dirs if Path(p).name not in chained)
    if outside:
        raise ExportRefusal(f"runs {outside} are not in {chain}, so the page's command ({VERIFY_COMMAND}) would not "
                            f"examine them")


def _verify_command(run_dirs: Sequence[Path], runs_dir: Path) -> str:
    """The chain-verification command the page prints, refused unless every run sits in `runs_dir` itself: a copy of
    the runs in another data/petri/runs would be exported while the command verifies the checkout's own (Codex review
    of 2026-09-24: a suffix check accepted any directory ending in data/petri/runs)."""
    parents = {Path(p).resolve().parent for p in run_dirs}
    if parents != {Path(runs_dir).resolve()}:
        raise ExportRefusal(f"the runs sit in {', '.join(sorted(map(str, parents)))}, not in {runs_dir}, the "
                            f"directory the page's verify-chain command ({VERIFY_COMMAND}) names, so it would verify "
                            f"other bytes than the ones exported")
    return VERIFY_COMMAND


def export(run_dirs: Sequence[Path], artifact_path: Path, *, seeds_path: Path = SEED_FILE,
           rubric_path: Path = ADVICE_RUBRIC, registry_path: Path = OUTCOME_REGISTRY,
           vocabulary_path: Path = VOCABULARY_FILE, wording_path: Path = WORDING_FILE, design_note: Path = DESIGN_NOTE,
           swaps_path: Path = SWAPS_FILE, disclosure_log: Path = DISCLOSURE_LOG, plan_path: Path = PLAN_FILE,
           seal_registry: Mapping[str, str] | None = None, example: Mapping[str, Any] | None = None,
           checkout: Checkout | None = None) -> Export:
    """Build both files in memory from the run directories and the section 10 artifact; refuse by name on any
    problem. `seal_registry` (phrase -> label) defaults to the study's sealed set; `example` overrides the vocabulary
    file's (the sample fixtures use it); `checkout` defaults to REPOSITORY (synthetic input passes
    synthetic_checkout)."""
    checkout = checkout or REPOSITORY
    artifact = load_artifact(Path(artifact_path))
    analysis_commit = artifact["identity"]["commit"]
    if not checkout.has_commit(analysis_commit):
        raise ExportRefusal(f"the section 10 artifact's analysis commit {analysis_commit} is not a commit in this "
                            f"repository, so the page would cite an analysis commit no reader can check out")
    problem = analysis_inputs_problem(artifact, checkout)
    if problem:
        raise ExportRefusal(f"the section 10 artifact {problem}")
    rubric = _load(rubric_path, "the advice rubric")
    registry = _load(registry_path, "the outcome registry")
    seed_doc = _load(seeds_path, "the seed file")
    seeds = {s["seed_id"]: s for s in seed_doc.get("seeds") or []}
    vocab = load_vocabulary(vocabulary_path, rubric, registry)
    wording = load_wording(wording_path, design_note)
    swaps_decl = _load(swaps_path, "the declared term swaps").get("seeds") or {}
    rubric_digest = judge_runner.rubric_digest(rubric)
    ranked_under = (artifact["coverage"].get("rubric") or {}).get("digest")
    if ranked_under != rubric_digest:
        raise ExportRefusal(f"the artifact ranked tiers under rubric digest {ranked_under!r}, the rubric in hand is "
                            f"{rubric_digest}")
    plan = registered_triples(Path(plan_path), artifact, seeds)
    for contrast in (PRIMARY_CONTRAST, DECOMPOSITION_CONTRAST):
        if contrast == PRIMARY_CONTRAST or artifact["section_10_3"].get("status") != "refused":
            _check_window(artifact, contrast)
    runs = _load_runs(run_dirs, artifact, seeds, checkout.runs_dir, vocab.models)
    # every file the export reads, and the exporter's own code: the commit recorded must name them all
    read = [Path(__file__), *sorted(Path(judge_runner.__file__).parent.glob("*.py")), Path(artifact_path),
            *(Path(x) for x in (seeds_path, rubric_path, registry_path, vocabulary_path, wording_path, design_note,
                                swaps_path, disclosure_log, plan_path)),
            Path(checkout.runs_dir) / CHAIN_FILE,
            *(r.path / name for r in runs.values()
              for name in ("manifest.json", *(ARTIFACT_FILENAMES[f] for f in ("judgments", "transcripts",
                                                                             "rule_outcomes"))))]
    exporter_commit = checkout.identity(read)
    notes: Counter = Counter()
    for run in runs.values():
        notes["judgments superseded by a retry (the latest per key is read)"] += run.superseded_by_retry
    rows_of: dict[str, list[dict]] = defaultdict(list)
    for run in runs.values():
        for r in run.rows:
            rows_of[r["conversation_id"]].append(r)

    seed_order, set_of = _plan_seeds(artifact["triples"], seeds, vocab)
    convs = _conversations(artifact["triples"], runs, seeds, vocab, rows_of, seed_order, notes)
    swaps = {sid: swaps_of(sid, swaps_decl.get(sid), len(seeds[sid]["protocol"]["arms"][0]["turns"]))
             for sid in seed_order}
    _check_swaps(convs, swaps)
    scale = PrimaryScale(vocab.by_row()[PRIMARY_ROW].values, rubric_digest, _primary_index(runs))
    triples, entering = _triples(artifact["triples"], seeds, scale)
    primary, scenario_means, tests = _primary(artifact["section_10_2"], entering, seeds, seed_order)
    headline = _headline(artifact["section_10_2"]["wording"], _selected_row(tests, entering, plan.scenarios), wording)
    style = _style_sentence(artifact["section_10_3"], artifact["triples"], scale, plan.decomposition_set, wording)
    review, drafts = clinician_review(_draft_sources(rubric, registry, seed_doc, seeds, seed_order))
    order = sorted(runs.values(), key=lambda r: (str(r.manifest.get("created_utc")), r.stem))
    summary = {"seed": artifact["bootstrap_seed"],
               "status": {"final": True, "clinician_review": review, "vendor_pack": vendor_pack(disclosure_log)},
               "headline": headline, "style_sentence": style,
               "primary": primary, "triples": triples, "scenario_means": scenario_means,
               "repeats": _repeats(seed_order, entering, _SIGN.get(tests.primary["direction"])),
               # the artifact file by sha256: a Petri pack's log entry records the same digest
               # (claim_ids.analysis_sha256), so the page binds to the analysis its cited pack was built from
               "provenance": {"runs": [r.stem for r in order], "analysis_commit": analysis_commit,
                              "analysis_sha256": sha256_file(Path(artifact_path)),
                              "exporter_commit": exporter_commit,
                              "verify": VERIFY_COMMAND}}    # _load_runs checked the command verifies these runs
    mechanisms = {mid: dict(v) for mid, v in vocab.mechanisms.items()
                  if any(vocab.mechanism_of[s] == mid for s in seed_order)}
    conversations = {"seed": None, "measures": [m.exported() for m in vocab.measures], "mechanisms": mechanisms,
                     "seeds": [_seed_record(sid, seeds[sid], vocab, set_of[sid], convs, swaps[sid])
                               for sid in seed_order],
                     "conversations": convs,
                     "example": _example(dict(example or vocab.example), seeds, seed_order)}

    # nothing sealed leaves through these files
    registry_sealed = sealed_registry() if seal_registry is None else dict(seal_registry)
    scan = scan_strings([json.dumps(summary, ensure_ascii=False), json.dumps(conversations, ensure_ascii=False)],
                        registry_sealed, "Multi-turn export")
    if scan.status == "fail":
        labels = sorted({label for v in scan.hits.values() for label in v})
        raise ExportRefusal(f"sealed Tier B phrase(s) in the export, by label: {labels}")
    # only a scan that ran passes: an empty sealed set scans nothing and reports not_run (Codex review of 2026-09-25)
    if scan.status != "pass":
        raise ExportRefusal(f"the holdout-seal scan of the export is {scan.status!r}, not 'pass' ({scan.detail}): an "
                            f"export no sealed phrase was checked against is not published")
    pack = summary["status"]["vendor_pack"]
    lines = [f"{n} {what}" for what, n in sorted(notes.items()) if n]
    lines += [f"seal check: {scan.status} ({scan.detail})",
              f"clinician_review {review}: draft status in {', '.join(drafts)}",
              "vendor pack: " + (f"{pack['version']} (sent {pack['sent']})" if pack["version"]
                                 else f"none recorded for lane {DISCLOSURE_LANE}")]
    return Export(summary, conversations, lines)


def _load_runs(run_dirs: Sequence[Path], artifact: Mapping[str, Any], seeds: Mapping[str, dict],
               runs_dir: Path, models: CampaignModels) -> dict[str, RunData]:
    """Exactly the runs the artifact covers: the chain that must name them verified first (a manifest edited after it
    was sealed is refused as that, before its contents are read), then each loaded and checked against the artifact's
    record of it and the campaign's registered models."""
    recorded = {r.get("run_stem"): r for r in artifact["coverage"].get("runs") or [] if isinstance(r, dict)}
    stems = [Path(p).name for p in run_dirs]
    if len(stems) != len(set(stems)):
        raise ExportRefusal(f"a run directory is given twice: {sorted(k for k, n in Counter(stems).items() if n > 1)}")
    if set(stems) != set(recorded):
        raise ExportRefusal(f"the runs given {sorted(stems)} are not the runs the section 10 artifact covers "
                            f"{sorted(recorded)}")
    _verify_command(run_dirs, runs_dir)
    _check_chain(run_dirs, runs_dir)
    return {Path(p).name: load_run(Path(p), recorded[Path(p).name], seeds, models) for p in run_dirs}


def _plan_seeds(triples: Sequence[Any], seeds: Mapping[str, dict],
                vocab: Vocabulary) -> tuple[list[str], dict[str, str]]:
    """The seeds the artifact's triples cover, in its (the plan's) order, with their scenario set; every triple
    landed, and every instrument each seed judges mapped to a measure."""
    seed_order: list[str] = []
    set_of: dict[str, str] = {}
    for t in triples:
        if not isinstance(t, dict) or t.get("landed") is not True:
            raise ExportRefusal(f"the artifact lists triple {t.get('triple') if isinstance(t, dict) else t!r} as not "
                                f"landed, which a final, untruncated analysis cannot")
        sid = t.get("seed_id")
        if sid not in seeds:
            raise ExportRefusal(f"triple {t.get('triple')}: seed {sid} is not in the seed file")
        if sid not in seed_order:
            seed_order.append(sid)
        if set_of.setdefault(sid, t.get("scenario_set")) != t.get("scenario_set"):
            raise ExportRefusal(f"seed {sid} is in two scenario sets in the artifact")
    by_row = vocab.by_row()
    if PRIMARY_ROW not in by_row:
        raise ExportRefusal(f"the page vocabulary maps no measure to {PRIMARY_ROW[0]}:{PRIMARY_ROW[1]}, the outcome D "
                            f"is computed on (design note 10.1)")
    for sid in seed_order:
        judge = seeds[sid]["judge"]
        unmapped = ([f"outcome:{d}" for d in judge["outcome_dimensions"] if ("outcome", d) not in by_row]
                    + [f"tier:{k}" for k, on in judge["advice_tier"].items() if on and ("tier", k) not in by_row])
        if unmapped:
            raise ExportRefusal(f"seed {sid} judges {unmapped}, which have no measure in the page vocabulary")
        if sid not in vocab.mechanism_of:
            raise ExportRefusal(f"seed {sid} belongs to no mechanism in the page vocabulary")
    return seed_order, set_of


def _conversations(triples: Sequence[dict], runs: Mapping[str, RunData], seeds: Mapping[str, dict], vocab: Vocabulary,
                   rows_of: Mapping[str, list[dict]], seed_order: Sequence[str], notes: Counter) -> list[dict]:
    """Every conversation the artifact's triples name, in the page's order (seed, epoch, speaker, then colloquial,
    careful lay, clinical); a run tree no triple names is counted, not shown.

    A triple's run must be the fire the plan assigns the triple to: its manifest's spend.journal_nonce is the triple's
    journal nonce (a re-adapted run keeps its source fire's nonce there), checked before any conversation of it is
    read (Codex review of 2026-09-25: a triple could be pointed at another fire's run). Each rule outcome is recomputed
    with scripts/petri_audit/rules.rule_outcomes from the transcript record and the seed, must equal the stored one,
    and the recomputed value is what the page gets (the same review: the stored outcomes were published verbatim)."""
    out: list[tuple[tuple, dict]] = []
    shown: set[str] = set()
    for t in triples:
        sid = t["seed_id"]
        run = runs.get(t.get("run_stem"))
        if run is None:
            raise ExportRefusal(f"triple {t.get('triple')}: run {t.get('run_stem')!r} is not among the runs given")
        nonce = (run.manifest.get("spend") or {}).get("journal_nonce")
        if nonce != t.get("journal_nonce"):
            raise ExportRefusal(f"triple {t.get('triple')}: run {run.stem} records journal nonce {nonce!r} "
                                f"(spend.journal_nonce), not the triple's {t.get('journal_nonce')!r}, so it is not the "
                                f"fire the plan assigns the triple to")
        speakers, cells = seed_cells(seeds[sid])
        for register in REGISTERS:
            cid = (t.get("conversations") or {}).get(register)
            if cid is None:
                notes[f"conversations the artifact names as missing ({register})"] += 1
                continue
            if cid not in run.trees:
                raise ExportRefusal(f"triple {t['triple']}: conversation {cid[:12]} is not in run {run.stem}")
            tree, branch = run.trees[cid]
            arm = cells.get((t.get("speaker"), register))
            if (tree["seed_id"] != sid or arm is None or tree["arm"] != arm["id"] or len(tree["branches"]) != 1
                    or branch.get("branch_id") != ROOT_BRANCH):
                raise ExportRefusal(f"triple {t['triple']}: conversation {cid[:12]} is not the one root trajectory of "
                                    f"the seed's {register} arm for speaker {t.get('speaker')}")
            if cid not in run.rules:
                raise ExportRefusal(f"run {run.stem} conversation {cid[:12]}: no rule outcome")
            exchanges = build_conversation(run, cid, seeds[sid], arm, vocab, rows_of.get(cid, []), notes)
            rule = _recomputed_rule(run, cid, seeds[sid])
            shown.add(cid)
            rank = (seed_order.index(sid), t["campaign_epoch"], speakers.index(t.get("speaker")),
                    REGISTERS.index(register))
            out.append((rank, {"run": run.stem, "run_epoch": tree["epoch"], "seed_id": sid, "arm": tree["arm"],
                               "register": register, "identity": t.get("speaker"), "conversation_id": cid,
                               "exchanges": exchanges, "rule": rule, "epoch": t["campaign_epoch"]}))
    for run in runs.values():
        for cid, (tree, _) in run.trees.items():
            if cid not in shown:
                notes[f"trees in run {run.stem} not shown (in no triple of the artifact; seed {tree['seed_id']})"] += 1
    return [rec for _, rec in sorted(out, key=lambda kv: kv[0])]


def _recomputed_rule(run: RunData, cid: str, seed: Mapping[str, Any]) -> dict[str, Any]:
    """The conversation's rule outcomes as rules.rule_outcomes computes them from its transcript record and seed,
    refused unless they equal the stored ones (the fields that differ, and both annotators, are named)."""
    stored = run.rules[cid]
    recomputed = rule_outcomes(run.records[cid], dict(seed))
    if recomputed != stored["outcomes"]:
        differ = sorted(k for k in set(recomputed) | set(stored["outcomes"])
                        if recomputed.get(k) != stored["outcomes"].get(k))
        raise ExportRefusal(f"run {run.stem} conversation {cid[:12]}: the stored rule outcome (annotator "
                            f"{stored.get('annotator')!r}) is not what scripts/petri_audit/rules.py ({ANNOTATOR}) "
                            f"computes from the transcript and the seed; they differ in {differ}")
    return recomputed


def _check_swaps(convs: Sequence[dict], swaps: Mapping[str, dict | None]) -> None:
    """Every declared swap span is in the user text the page shows: the clinical span in the clinical conversation,
    the careful-lay span in the careful-lay one (a transcript that drifted from the seed file is refused)."""
    for c in convs:
        sw = swaps[c["seed_id"]]
        if not sw or c["register"] not in (CLINICAL, CAREFUL_LAY):
            continue
        per = sw.get(f"{c['identity']}_" if c["identity"] else "")
        if per is None:
            raise ExportRefusal(f"swaps of {c['seed_id']}: none declared for speaker {c['identity']}")
        side = 0 if c["register"] == CLINICAL else 1
        for i, ex in enumerate(c["exchanges"]):
            for k, pair in enumerate(per[i]):
                if pair[side] not in ex["user"]:
                    raise ExportRefusal(f"{c['run']} {c['arm']} exchange {i + 1}: declared swap span {k + 1} is not "
                                        f"in the user text")


@dataclass(frozen=True)
class PrimaryScale:
    """10.1's outcome as the analysis reads it: the rubric's tiers low to high, the rubric digest every compared row
    must carry, and the final rows of the response-only tier per (run stem, conversation, exchange)."""
    tiers: tuple[str, ...]
    digest: str
    final: Mapping[tuple[str, str, int], list[dict]]

    def rows(self, stem: str, cid: str, ex: int) -> list[dict]:
        return self.final.get((stem, cid, ex), [])

    def rank(self, stem: str, cid: str, ex: int) -> int:
        """The rank at a comparable exchange, whose one row under the digest side_problem established."""
        [row] = [r for r in self.rows(stem, cid, ex) if r.get("prompt_file_digest") == self.digest]
        return self.tiers.index(row["value"])


def _primary_index(runs: Mapping[str, RunData]) -> dict[tuple[str, str, int], list[dict]]:
    """The final response-only tier rows per (run stem, conversation, exchange), keyed as the analysis's index_rows
    keys them: each run's own rows, final_in_exchange true, an integer exchange index, no shared-prefix row."""
    out: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for run in runs.values():
        for r in run.rows:
            if ((r.get("kind"), r.get("key")) == PRIMARY_ROW and r.get("final_in_exchange") is True
                    and _count(r.get("exchange_index")) and not r.get("shared_prefix")):
                out[(run.stem, r["conversation_id"], r["exchange_index"])].append(r)
    return dict(out)


def side_problem(rows: Sequence[dict], scale: PrimaryScale, where: str) -> str | None:
    """Why one conversation's final row at one exchange is not comparable, or None: the analysis's side_problem
    (scripts/petri_w2_register_contrast.py) for a measure without a flag. Comparable means exactly one row under the
    current rubric digest (a row under another digest is another instrument; two under it are a duplicate), neither
    not applicable nor null. A value off the rubric's scale is refused, as the analysis refuses it."""
    if not rows:
        return "no final row"
    current = [r for r in rows if r.get("prompt_file_digest") == scale.digest]
    if not current:
        return f"judged under another digest than {scale.digest}"
    if len(current) > 1:
        return f"{len(current)} final rows under digest {scale.digest}"
    row = current[0]
    if row.get("not_applicable_reason") or row.get("value") == judge_runner.NA:
        return "not applicable"
    if row.get("value") is None:
        return "null value"
    if row["value"] not in scale.tiers:
        raise ExportRefusal(f"{where}: {PRIMARY_ROW[0]}:{PRIMARY_ROW[1]} value {row['value']!r} is not on the "
                            f"rubric's scale {list(scale.tiers)}")
    return None


def comparable_exchanges(t: Mapping[str, Any], registers: Sequence[str], scale: PrimaryScale) -> list[int]:
    """The exchanges of 10.1's window at which every listed conversation of the triple passes side_problem (two
    conversations for a two-wording contrast, all three for 10.3's three-way completeness); none when a listed
    conversation is missing. The analysis's standing, which judges every listed conversation at an exchange, so a
    value off the scale is refused wherever it sits."""
    convs = t.get("conversations") or {}
    if any(convs.get(r) is None for r in registers):
        return []
    out = []
    for ex in WINDOW:
        problems = [side_problem(scale.rows(t["run_stem"], convs[r], ex), scale,
                                 f"triple {t.get('triple')} {r} conversation exchange {ex}") for r in registers]
        if not any(problems):
            out.append(ex)
    return out


def _check_window(artifact: Mapping[str, Any], contrast: str) -> None:
    """Refuse unless the artifact's coverage records `contrast` over 10.1's window and floor, the ones eligibility is
    recomputed with here (Codex review of 2026-09-25)."""
    head = (artifact["coverage"].get("contrasts") or {}).get(contrast)
    got = (head.get("window"), head.get("floor")) if isinstance(head, dict) else None
    if got != (WINDOW_NAME, FLOOR):
        raise ExportRefusal(f"the section 10 artifact's coverage records the {contrast} contrast over (window, floor) "
                            f"{got}, not 10.1's {(WINDOW_NAME, FLOOR)}")


def _triples(triples: Sequence[dict], seeds: Mapping[str, dict],
             scale: PrimaryScale) -> tuple[list[dict], list[tuple[dict, Fraction]]]:
    """The page's triple records, and the entering triples with their exact D.

    Eligibility is recomputed, never trusted (Codex review of 2026-09-25): each triple's comparable exchanges over
    10.1's window are rebuilt from the current-digest final rows of its own run (comparable_exchanges, the analysis's
    standing and side_problem) and must equal the artifact's comparable_exchanges, and `enters` must equal (their count
    >= 10.1's floor of 8). D(colloquial, clinical) is then the mean of rank(colloquial) minus rank(clinical) over those
    exchanges, ranks in the rubric's tier order, and must equal the artifact's sum, n and D for an entering triple. A
    triple below its floor keeps that mean, marked not eligible; with no comparable exchange, or a conversation
    missing, its D is null."""
    out: list[dict] = []
    entering: list[tuple[dict, Fraction]] = []
    for t in triples:
        prim = (t.get("contrasts") or {}).get(PRIMARY_CONTRAST)
        if not isinstance(prim, dict) or not isinstance(prim.get("enters"), bool):
            raise ExportRefusal(f"triple {t.get('triple')}: the artifact records no primary-contrast standing")
        if t.get("partition") not in PARTITION_LABEL:
            raise ExportRefusal(f"triple {t.get('triple')}: partition {t.get('partition')!r} is not one of "
                                f"{sorted(PARTITION_LABEL)}")
        comparable = comparable_exchanges(t, (COLLOQUIAL, CLINICAL), scale)
        if prim.get("comparable_exchanges") != comparable:
            raise ExportRefusal(f"triple {t['triple']}: the artifact counts exchanges {prim.get('comparable_exchanges')} "
                                f"comparable; the rows give {comparable} ({WINDOW_NAME}: one valued, applicable final "
                                f"{PRIMARY_ROW[0]}:{PRIMARY_ROW[1]} row per conversation under {scale.digest})")
        enters = len(comparable) >= FLOOR
        if prim["enters"] is not enters:
            raise ExportRefusal(f"triple {t['triple']}: the artifact records enters {prim['enters']}, and its "
                                f"{len(comparable)} comparable exchanges against 10.1's floor of {FLOOR} give {enters}")
        d: float | None = None
        if comparable:
            col, clin = (t["conversations"][r] for r in (COLLOQUIAL, CLINICAL))
            total = sum(scale.rank(t["run_stem"], col, ex) - scale.rank(t["run_stem"], clin, ex) for ex in comparable)
            exact = Fraction(total, len(comparable))
            if enters:
                recorded = (prim.get("sum"), prim.get("n"), prim.get("D_exact"), prim.get("D"))
                if recorded != (total, len(comparable), str(exact), float(exact)):
                    raise ExportRefusal(f"triple {t['triple']}: the rows give D = {exact} over {len(comparable)} "
                                        f"exchanges, the artifact {prim.get('D_exact')} over {prim.get('n')}")
                entering.append((t, exact))
            d = float(exact)
        out.append({"seed_id": t["seed_id"], "scenario_id": seeds[t["seed_id"]]["scenario"]["id"],
                    "epoch": t["campaign_epoch"], "D": d, "partition": PARTITION_LABEL[t["partition"]],
                    "eligible": enters})
    return out, entering


def exact_sign_test_p(k: int, n: int) -> float:
    """10.2's exact two-sided sign-test p for k of n non-tied triples on one side, as the analysis computes it
    (scripts/petri_w2_register_contrast.py exact_sign_test_p): 2 * P(X <= min(k, n - k)), X ~ Binomial(n, 1/2), capped
    at 1, in rationals; 1.0 when n = 0."""
    if n == 0:
        return 1.0
    m = min(k, n - k)
    return float(min(Fraction(1), Fraction(2 * sum(math.comb(n, i) for i in range(m + 1)), 2 ** n)))


def sign_flip_p(means: Sequence[Fraction]) -> Fraction:
    """10.2's scenario gate as the analysis computes it (sign_flip_test): the share of the 2^k sign assignments of the
    k scenario means whose |sum| is at least the observed |sum|, compared exactly."""
    observed = abs(sum(means, Fraction(0)))
    hits = sum(1 for signs in itertools.product((1, -1), repeat=len(means))
               if abs(sum((s * v for s, v in zip(signs, means)), Fraction(0))) >= observed)
    return Fraction(hits, 2 ** len(means))


def _direction(total: Fraction | int) -> str:
    return "negative" if total < 0 else "positive" if total > 0 else "none"


_SIGN = {"negative": -1, "positive": 1}


def sign_test(values: Sequence[Fraction | int]) -> dict[str, Any]:
    """The analysis's sign_test (the fields read here) on the signs of `values`: ties dropped and counted, p the exact
    two-sided sign-test p, significant when p < 0.05, the direction the majority sign of the non-tied."""
    negative, positive = sum(v < 0 for v in values), sum(v > 0 for v in values)
    p = exact_sign_test_p(min(negative, positive), negative + positive)
    return {"triples": len(values), "negative": negative, "positive": positive,
            "tied": len(values) - negative - positive, "non_tied": negative + positive, "p": p,
            "significant": p < ALPHA, "direction": _direction(positive - negative)}


@dataclass(frozen=True)
class Tests:
    """10.2's recomputed primary sign test (sign_test's fields) and scenario gate (scenarios, significant,
    direction), the inputs of the wording row."""
    primary: dict[str, Any]
    gate: dict[str, Any]


def _primary(s102: Mapping[str, Any], entering: Sequence[tuple[dict, Fraction]], seeds: Mapping[str, dict],
             seed_order: Sequence[str]) -> tuple[dict[str, Any], dict[str, float], Tests]:
    """10.2's counts, p-values and gate, checked against the entering triples; the scenario means keyed by scenario
    id; and the recomputed tests the wording row is selected from. A p-value of a test that did not run (no non-tied
    triple; no scenario) is null, never the 1 the artifact's arithmetic gives it.

    Every published field is recomputed from the entering triples and must equal the artifact's (Codex review of
    2026-09-25): the sign test's non_tied, p and direction; the gate's scenarios, p (and p_exact), direction and
    significance; and the wording's gate_same_direction. What the page gets is the recomputed value, never the
    artifact's copy of it."""
    pst, gate, wording_row_ = s102.get("primary_sign_test"), s102.get("scenario_gate"), s102.get("wording")
    if not (isinstance(pst, dict) and isinstance(gate, dict) and isinstance(wording_row_, dict)
            and _count(pst.get("non_tied")) and _count(gate.get("scenarios"))):
        raise ExportRefusal("the artifact's section_10_2 lacks the primary sign test, the scenario gate or the wording")
    test = sign_test([e for _, e in entering])
    counts = (test["triples"], test["negative"], test["positive"], test["tied"])
    recorded = (pst.get("triples"), pst.get("negative"), pst.get("positive"), pst.get("tied"))
    if recorded != counts:
        raise ExportRefusal(f"the primary test counts (triples, negative, positive, tied) {recorded} are not the "
                            f"entering triples' {counts}")
    stated = (pst.get("non_tied"), pst.get("p"), pst.get("direction"), pst.get("alpha"))
    if stated != (test["non_tied"], test["p"], test["direction"], ALPHA):
        raise ExportRefusal(f"the primary sign test records (non_tied, p, direction, alpha) {stated}; the entering "
                            f"triples give {(test['non_tied'], test['p'], test['direction'], ALPHA)}")
    by_scenario: dict[str, list[Fraction]] = defaultdict(list)
    for t, e in entering:
        by_scenario[t["seed_id"]].append(e)
    means = {s: sum(v, Fraction(0)) / len(v) for s, v in by_scenario.items()}
    if {s: str(m) for s, m in means.items()} != (gate.get("scenario_means_exact") or {}):
        raise ExportRefusal("the scenario gate's means are not the entering triples' means per scenario")
    # the artifact's float mirror must be the floats of those exact means, as a triple's D is checked beside its
    # D_exact: a stale or missing mirror entry means the artifact disagrees with itself (Codex review of 2026-09-24)
    if gate.get("scenario_means") != {s: float(m) for s, m in means.items()}:
        raise ExportRefusal("the scenario gate's scenario_means are not the floats of its scenario_means_exact, so "
                            "the artifact disagrees with itself")
    scenario_of = {s: seeds[s]["scenario"]["id"] for s in seed_order}
    if len(set(scenario_of.values())) != len(scenario_of):
        raise ExportRefusal("two seeds share a scenario id, and the page keys scenario means by scenario id")
    k = len(means)
    if k > GATE_MAX_SCENARIOS:
        raise ExportRefusal(f"{k} scenarios: the gate's 2^k enumeration is bounded at {GATE_MAX_SCENARIOS}")
    gate_p = sign_flip_p([means[s] for s in sorted(means)])
    gate_direction = _direction(sum(means.values(), Fraction(0)))
    gate_significant = float(gate_p) < ALPHA
    same = gate_significant and gate_direction == test["direction"]
    stated = (gate.get("scenarios"), gate.get("p"), gate.get("p_exact"), gate.get("direction"),
              gate.get("significant"), gate.get("alpha"), wording_row_.get("gate_same_direction"))
    computed = (k, float(gate_p), str(gate_p), gate_direction, gate_significant, ALPHA, same)
    if stated != computed:
        raise ExportRefusal(f"the scenario gate records (scenarios, p, p_exact, direction, significant, alpha, "
                            f"gate_same_direction) {stated}; the entering triples' scenario means give {computed}")
    primary = {"triples": counts[0], "negative": counts[1], "positive": counts[2], "tied": counts[3],
               "p_two_sided": test["p"] if test["non_tied"] > 0 else None,
               "gate_p": float(gate_p) if k > 0 else None,
               "gate_passed": same if k > 0 else None}
    # the page is given the recomputed means, the values checked above, never the artifact's mirror of them
    return (primary, {scenario_of[s]: float(m) for s, m in means.items()},
            Tests(test, {"scenarios": k, "significant": gate_significant, "direction": gate_direction}))


def wording_row(primary: Mapping[str, Any], gate: Mapping[str, Any], prospective_same_direction: bool,
                planned_scenarios: int) -> tuple[str, bool]:
    """The row of 10.2's table the tests select, and whether it is selectable as registered: the analysis's
    wording_row (scripts/petri_w2_register_contrast.py) with 10.8's three readings. No non-tied triple selects
    not_computable; a primary p >= 0.05 row5; a gate significant in the direction opposite to the primary test
    no_prespecified_row; otherwise row1 (gate significant in the primary's direction, the prospective replication in
    it too), row2 (the gate so, the replication not) or row3 (the gate not significant), as row4/<row> when the
    primary direction is positive. not_computable and no_prespecified_row are never selectable, and no row is when the
    gate ran on fewer scenarios than the plan's."""
    direction = primary["direction"]
    gate_same = bool(gate["significant"]) and gate["direction"] == direction
    gate_opposite = bool(gate["significant"]) and gate["direction"] != direction and gate["direction"] != "none"
    selectable = True
    if primary["non_tied"] == 0:
        row, selectable = "not_computable", False
    elif not primary["significant"]:
        row = "row5"
    elif gate_opposite:
        row, selectable = "no_prespecified_row", False
    else:
        base = ("row1" if prospective_same_direction else "row2") if gate_same else "row3"
        row = base if direction == "negative" else f"row4/{base}"
    if gate["scenarios"] < planned_scenarios:
        selectable = False
    return row, selectable


def _selected_row(tests: Tests, entering: Sequence[tuple[dict, Fraction]], planned_scenarios: int) -> tuple[str, bool]:
    """10.2's row from the recomputed tests (Codex review of 2026-09-25: the headline row was published unchecked):
    the prospective replication is the sign test over the entering triples of the prospective partition, in the same
    direction when the primary test has one and the replication's is it (the analysis's prospective_replication); the
    planned scenario count is the plan's."""
    replication = sign_test([e for t, e in entering if t["partition"] == PROSPECTIVE])
    same = tests.primary["direction"] != "none" and replication["direction"] == tests.primary["direction"]
    return wording_row(tests.primary, tests.gate, same, planned_scenarios)


def holm(pvalues: Mapping[str, float], alpha: float = ALPHA) -> dict[str, dict[str, Any]]:
    """Holm's step-down correction over one family, as the analysis's holm computes it: the m p-values ordered
    ascending (ties by name), the i-th adjusted p the running maximum of min(1, (m - i) p), a hypothesis rejected
    when its adjusted p < alpha."""
    m = len(pvalues)
    out: dict[str, dict[str, Any]] = {}
    running = 0.0
    for i, name in enumerate(sorted(pvalues, key=lambda k: (pvalues[k], k))):
        running = max(running, min(1.0, (m - i) * float(pvalues[name])))
        out[name] = {"p_holm": running, "significant_after_holm": running < alpha}
    return {name: out[name] for name in pvalues}


def decomposition_statement(style: Mapping[str, Any], vocabulary: Mapping[str, Any], paired: Mapping[str, Any],
                            adjusted: Mapping[str, Mapping[str, Any]]) -> tuple[str, bool]:
    """10.3's statement and whether vocabulary_also_lowered is added: the analysis's decomposition_statement. No
    non-tied paired difference is not_computable; a paired difference not significant after Holm not_separated; one
    significant and negative with style significant and negative style_larger (with the clause when vocabulary is
    significant and negative too); anything else no_prespecified_statement."""
    sig = {k: adjusted[k]["significant_after_holm"] for k in adjusted}
    if paired["non_tied"] == 0:
        sid = "not_computable"
    elif not sig["paired_difference"]:
        sid = "not_separated"
    elif paired["direction"] == "negative" and sig["style"] and style["direction"] == "negative":
        sid = "style_larger"
    else:
        sid = "no_prespecified_statement"
    return sid, sid == "style_larger" and sig["vocabulary"] and vocabulary["direction"] == "negative"


def _decomposition(triples: Sequence[dict], scale: PrimaryScale, decomposition_set: str) -> tuple[str, bool]:
    """10.3 recomputed from the rows (Codex review of 2026-09-25: the statement was published unchecked), as the
    analysis's decomposition branch of contrast_sections computes it: for every triple of the plan's decomposition set
    with at least 10.1's floor of three-way complete exchanges (comparable_exchanges over all three conversations),
    D(style) = colloquial minus careful lay and D(vocabulary) = careful lay minus clinical, summed over those
    exchanges, and their paired difference; an exact sign test on each (the sign of a sum is the sign of its mean),
    Holm-corrected together; and the statement decomposition_statement selects."""
    style: list[int] = []
    vocabulary: list[int] = []
    paired: list[int] = []
    for t in triples:
        if t.get("scenario_set") != decomposition_set:
            continue
        complete = comparable_exchanges(t, REGISTERS, scale)
        if len(complete) < FLOOR:
            continue
        rank = {r: [scale.rank(t["run_stem"], t["conversations"][r], ex) for ex in complete] for r in REGISTERS}
        s = sum(a - b for a, b in zip(rank[COLLOQUIAL], rank[CAREFUL_LAY]))
        v = sum(a - b for a, b in zip(rank[CAREFUL_LAY], rank[CLINICAL]))
        style.append(s)
        vocabulary.append(v)
        paired.append(s - v)
    tests = {"style": sign_test(style), "vocabulary": sign_test(vocabulary), "paired_difference": sign_test(paired)}
    adjusted = holm({k: v["p"] for k, v in tests.items()})
    return decomposition_statement(tests["style"], tests["vocabulary"], tests["paired_difference"], adjusted)


def _repeats(seed_order: Sequence[str], entering: Sequence[tuple[dict, Fraction]],
             direction: int | None) -> list[dict]:
    """Does it repeat: per seed, the campaign epochs with an entering triple, and how many of them have a mean D (the
    two speakers of an identity seed pooled, as the gate pools them) in the primary test's direction."""
    out = []
    for sid in seed_order:
        per_epoch: dict[int, list[Fraction]] = defaultdict(list)
        for t, e in entering:
            if t["seed_id"] == sid:
                per_epoch[t["campaign_epoch"]].append(e)
        same = None if direction is None else sum(
            1 for v in per_epoch.values() if _sign(sum(v, Fraction(0))) == direction)
        out.append({"seed_id": sid, "epochs": len(per_epoch), "same_direction": same})
    return out


def _draft_sources(rubric: Mapping[str, Any], registry: Mapping[str, Any], seed_doc: Mapping[str, Any],
                   seeds: Mapping[str, dict], seed_order: Sequence[str]) -> dict[str, Any]:
    """The status of each source of the draft state: the three files, and the entries of each the page uses."""
    dims = {d["id"]: d for d in registry.get("dimensions") or []}
    used = sorted({d for s in seed_order for d in seeds[s]["judge"]["outcome_dimensions"]})
    return {"advice rubric": rubric.get("status"), "outcome registry": registry.get("status"),
            "seed file": seed_doc.get("status"),
            **{f"outcome dimension {d}": (dims.get(d) or {}).get("status") for d in used},
            **{f"seed {s}": seeds[s].get("status") for s in seed_order}}


def _seed_record(sid: str, seed: Mapping[str, Any], vocab: Vocabulary, scenario_set: str, convs: Sequence[dict],
                 swaps: dict | None) -> dict[str, Any]:
    speakers, cells = seed_cells(seed)
    judge = seed["judge"]
    applies = {m.id for m in vocab.measures
               if (m.source[0] == "tier" and judge["advice_tier"].get(m.source[1]))
               or (m.source[0] == "outcome" and m.source[1] in judge["outcome_dimensions"])}
    proposition = texts_by_key(dict(seed)).get("proposition")
    return {"seed_id": sid, "mechanism": vocab.mechanism_of[sid], "set": scenario_set,
            "topic": seed["scenario"]["topic"], "scenario_id": seed["scenario"]["id"],
            "hypotheses": list(seed["hypotheses"]),
            "roles": [t.get("context_role") for t in seed["protocol"]["arms"][0]["turns"]],
            "arms": [cells[(s, r)]["id"] for s in speakers for r in REGISTERS if (s, r) in cells],
            "measures": [m.id for m in vocab.measures if m.id in applies],
            "epochs": sorted({c["epoch"] for c in convs if c["seed_id"] == sid}),
            "proposition": proposition["text"] if proposition else None,
            "system_prompt": seed["system_prompt"]["policy"], "swaps": swaps}


def _headline(recorded: Mapping[str, Any], selected: tuple[str, bool], wording: Wording) -> dict[str, str | None]:
    """10.2's row, refused unless the artifact's row_id and selectable_as_registered are the recomputed ones
    (_selected_row); its text the table's cell verbatim. not_computable, no_prespecified_row and a row not selectable
    as registered are carried by name with no text (never a headline the table does not register)."""
    row, selectable = selected
    stated = (recorded.get("row_id"), recorded.get("selectable_as_registered"))
    if stated != (row, selectable):
        raise ExportRefusal(f"the artifact's section_10_2.wording records (row_id, selectable_as_registered) {stated}; "
                            f"the recomputed primary test, scenario gate and prospective replication select "
                            f"{(row, selectable)} (design note 10.2's table)")
    if row in UNWORDED_ROWS:
        return {"row_id": row, "text": None}
    if not selectable:
        return {"row_id": f"{NOT_SELECTABLE}:{row}", "text": None}
    base = row.split("/", 1)[0]
    if base not in wording.rows:
        raise ExportRefusal(f"the tests select row {row!r}, which the registered wording has no text for")
    return {"row_id": row, "text": wording.rows[base]}


def _style_sentence(s103: Mapping[str, Any], triples: Sequence[dict], scale: PrimaryScale, decomposition_set: str,
                    wording: Wording) -> dict[str, str | None]:
    """10.3's statement, refused unless the artifact's statement_id and vocabulary_also_lowered are the recomputed
    ones (_decomposition); its text the note's bullet verbatim. An unworded statement is carried by name, and a
    section the analysis refused stays refused by name."""
    if s103.get("status") == "refused":
        return {"row_id": "refused", "text": None}
    sid, also = _decomposition(triples, scale, decomposition_set)
    st = s103.get("statement")
    stated = (st.get("statement_id"), st.get(ALSO_LOWERED)) if isinstance(st, dict) else None
    if stated != (sid, also):
        raise ExportRefusal(f"the artifact's section_10_3.statement records (statement_id, {ALSO_LOWERED}) {stated}; "
                            f"the recomputed decomposition on scenario set {decomposition_set} gives {(sid, also)}")
    if sid in UNWORDED_STATEMENTS:
        return {"row_id": sid, "text": None}
    if sid not in wording.statements:
        raise ExportRefusal(f"the decomposition selects statement {sid!r}, which the registered wording has no text "
                            f"for")
    return {"row_id": sid + (f"+{ALSO_LOWERED}" if also else ""), "text": wording.statements[sid]}


def _example(example: Mapping[str, Any], seeds: Mapping[str, dict], seed_order: Sequence[str]) -> dict[str, Any]:
    sid, turn = example.get("seed_id"), example.get("turn")
    if sid not in seed_order:
        raise ExportRefusal(f"the example seed {sid} is not one of the exported seeds")
    speakers, cells = seed_cells(seeds[sid])
    out: dict[str, Any] = {"seed_id": sid, "turn": turn}
    for register in REGISTERS:
        arm = cells.get((speakers[0], register))
        if arm is None or not 1 <= turn <= len(arm["turns"]):
            raise ExportRefusal(f"the example seed {sid} has no {register} turn {turn}")
        out[register] = text_of(seeds[sid], arm["turns"][turn - 1]["text_ref"])
    return out


# ------------------------------------------------------------------ writing, samples, the diff


def _dumps(obj: Any, *, compact: bool) -> str:
    if compact:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def swap_dir(data: Path, sample: bool) -> Path:
    """Where write_site stages one write of the pair: `new/` (the files to swap in), `old/` (a copy of each file it
    replaces) and `journal.json` (which destinations existed before). The contract validator fails a site that holds
    one (scripts/validate_frontend_contract.py, MT_SWAP_GLOB), since the pair beside it may be mixed."""
    return Path(data) / (".petri_multiturn" + (".sample" if sample else "") + ".swap")


def recover_interrupted_write(data: Path, sample: bool = False) -> bool:
    """Put back the pair a write_site that stopped between its replacements left (a crash, a kill): with the journal
    present, each destination is restored from its copy in `old/`, or removed when it did not exist before that write
    (a destination whose copy is gone was restored by an earlier recovery that was itself interrupted); without the
    journal no destination had been touched. The swap directory is then removed. True when there was one."""
    swap = swap_dir(data, sample)
    if not swap.exists():
        return False
    journal = swap / "journal.json"
    if journal.is_file():
        try:
            existed = json.loads(journal.read_text(encoding="utf-8"))["existed"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExportRefusal(f"{journal} does not parse ({exc}); the pair in {data} may be mixed: restore it from "
                                f"git and remove {swap}") from exc
        for name, had in existed.items():
            dest, old = Path(data) / name, swap / "old" / name
            if had and old.is_file():
                os.replace(old, dest)
            elif not had:
                dest.unlink(missing_ok=True)
    shutil.rmtree(swap)
    return True


def write_site(site: Path, summary: Mapping[str, Any], conversations: Mapping[str, Any], *,
               sample: bool = False) -> list[Path]:
    """Write both files into `<site>/data/` (the `.sample.json` names when `sample`), fully or not at all: the page
    reads the two as one unit, and neither file carries an identifier the other could be matched by. Both new files
    are staged in the swap directory with a copy of each file they replace and a journal, and only then renamed into
    place. Any exception between the two renames (an error, a keyboard interrupt) puts the previous pair back before
    it propagates; a process killed there leaves the swap directory, which the next write (and
    recover_interrupted_write) rolls back first and the contract validator fails the site over until then (Codex
    review of 2026-09-24: two bare renames could leave one new file beside one old one)."""
    data = Path(site) / "data"
    if not data.is_dir():
        raise ExportRefusal(f"{data} is not a directory")
    recover_interrupted_write(data, sample)
    suffix = ".sample.json" if sample else ".json"
    out = [data / (SUMMARY_NAME + suffix), data / (CONVERSATIONS_NAME + suffix)]
    texts = [_dumps(summary, compact=False), _dumps(conversations, compact=not sample)]
    swap = swap_dir(data, sample)
    try:
        (swap / "new").mkdir(parents=True)
        (swap / "old").mkdir()
        existed = {p.name: p.is_file() for p in out}
        for path, text in zip(out, texts):
            (swap / "new" / path.name).write_text(text, encoding="utf-8")
            if existed[path.name]:
                shutil.copy2(path, swap / "old" / path.name)
        # the journal appears whole or not at all, and only once every copy it vouches for is complete
        (swap / "journal.json.tmp").write_text(json.dumps({"existed": existed}), encoding="utf-8")
        os.replace(swap / "journal.json.tmp", swap / "journal.json")
        for path in out:
            os.replace(swap / "new" / path.name, path)
    except BaseException:
        recover_interrupted_write(data, sample)
        raise
    shutil.rmtree(swap)
    return out


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "..."


def diff_cells(old: Any, new: Any, path: str = "$") -> list[str]:
    """Every leaf that differs between two JSON documents, by path: '~ path: old -> new', '+ path: new' (added) or
    '- path: old' (removed)."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = [f"- {path}.{k}: {_short(old[k])}" for k in old if k not in new]
        for k in new:
            out += ([f"+ {path}.{k}: {_short(new[k])}"] if k not in old else diff_cells(old[k], new[k], f"{path}.{k}"))
        return out
    if isinstance(old, list) and isinstance(new, list):
        out = []
        for i in range(max(len(old), len(new))):
            if i >= len(old):
                out.append(f"+ {path}[{i}]: {_short(new[i])}")
            elif i >= len(new):
                out.append(f"- {path}[{i}]: {_short(old[i])}")
            else:
                out += diff_cells(old[i], new[i], f"{path}[{i}]")
        return out
    same = old == new and isinstance(old, bool) == isinstance(new, bool) and (old is None) == (new is None)
    return [] if same else [f"~ {path}: {_short(old)} -> {_short(new)}"]


def samplify(result: Export, rng_seed: int, epoch: int = 1) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two SYNTHETIC sample fixtures from an export of synthetic input: every free text replaced by a placeholder,
    the registered wording by the site's placeholder rows, the provenance by sample ids, status not final, and the
    conversations cut to one epoch."""
    s = json.loads(json.dumps(result.summary))
    c = json.loads(json.dumps(result.conversations))
    run_ids = {r: f"run_SAMPLE_{i}" for i, r in enumerate(s["provenance"]["runs"], 1)}
    s["status"] = {"final": False, "clinician_review": REVIEW_PENDING, "vendor_pack": {"version": None, "sent": None}}
    s["headline"] = {"row_id": "SAMPLE", "text": "[Sample headline: the section 10.2 wording-table row goes here "
                                                 "verbatim.]"}
    s["style_sentence"] = {"row_id": "SAMPLE", "text": "[Sample sentence: the section 10.3 row goes here verbatim.]"}
    s["provenance"] = {"runs": list(run_ids.values()), "analysis_commit": "SAMPLE", "analysis_sha256": "SAMPLE",
                       "exporter_commit": "SAMPLE", "verify": s["provenance"]["verify"]}
    convs = [x for x in c["conversations"] if x["epoch"] == epoch]
    for n, x in enumerate(convs, 1):
        x["conversation_id"] = f"sample-{n:03d}"
        x["run"] = run_ids.get(x["run"], "run_SAMPLE")
        for i, ex in enumerate(x["exchanges"], 1):
            ex["user"] = f"[Sample {x['register']} user turn {i}: placeholder text, not a real message.]"
            ex["reply"] = f"[Sample assistant reply {i}: placeholder text, not a real message.]"
            for it in ex["interim"]:
                it["text"] = (f"[Sample scripted lookup result {i}: placeholder text written for the sample, not a "
                              f"real result.]" if it["role"] == "tool" else
                              f"[Sample intermediate reply {i}: placeholder text, not a real message.]")
            for cell in ex["vals"].values():
                if "na" in cell:
                    cell["na"] = "sample: not applicable"
        rule = x["rule"]
        # the lane's shape kept: a list of every call's arguments, or null (scripts/petri_audit/rules.py)
        queries = rule.get("query_text")
        if queries is not None:
            if not isinstance(queries, list):
                raise ExportRefusal(f"the synthetic rule outcome's query_text is a {type(queries).__name__}, not the "
                                    f"list the lane writes")
            rule["query_text"] = [f"[Sample query text {k}: placeholder.]" for k in range(1, len(queries) + 1)]
        if rule.get("first_tool"):
            rule["first_tool"] = "sample_lookup"
    c["conversations"] = convs
    for n, seed in enumerate(c["seeds"], 1):
        seed["topic"] = f"Sample scenario {n}"
        seed["epochs"] = sorted({x["epoch"] for x in convs if x["seed_id"] == seed["seed_id"]})
        if seed["proposition"] is not None:
            seed["proposition"] = "[Sample proposition: placeholder text.]"
    for k, register in enumerate(REGISTERS, 1):
        c["example"][register] = f"[Sample wording {k}: placeholder text, not a real message.]"
    head = {"sample": True, "_note": SAMPLE_NOTES[SUMMARY_NAME], "seed": rng_seed}
    summary = {**head, **{k: v for k, v in s.items() if k != "seed"}}
    head = {"sample": True, "_note": SAMPLE_NOTES[CONVERSATIONS_NAME], "seed": rng_seed}
    conversations = {**head, **{k: v for k, v in c.items() if k != "seed"}}
    return summary, conversations


def sample_export(*, vocabulary_path: Path = VOCABULARY_FILE, seeds_path: Path = SEED_FILE,
                  rubric_path: Path = ADVICE_RUBRIC, registry_path: Path = OUTCOME_REGISTRY,
                  seal_registry: Mapping[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two sample fixtures, exported from a SYNTHETIC campaign (scripts/petri_multiturn_synthetic.py) built in a
    temporary directory from the vocabulary file's sample settings, with one triple of the last epoch left below its
    floor so the page's not-eligible mark has a case; the generator seed is recorded in both files. The campaign records
    the vocabulary's registered models (campaign_models), so the export's model check runs on it as on landed runs,
    with no exemption for samples; no model string reaches the sample files."""
    from scripts import petri_multiturn_synthetic as synthetic
    rubric = _load(rubric_path, "the advice rubric")
    registry = _load(registry_path, "the outcome registry")
    vocab = load_vocabulary(vocabulary_path, rubric, registry)
    seeds = {s["seed_id"]: s for s in _load(seeds_path, "the seed file")["seeds"]}
    cfg = vocab.samples
    with tempfile.TemporaryDirectory() as tmp:
        campaign = synthetic.build_campaign(
            Path(tmp), seeds=seeds, sets={"original": list(cfg["seed_ids"])},
            fires=synthetic.epoch_fires(cfg["epochs"], "original"), rubric=rubric, registry=registry,
            rng_seed=cfg["rng_seed"], judgment_edit=synthetic.below_floor(cfg["epochs"]), models=asdict(vocab.models))
        artifact = Path(tmp) / "artifact.json"
        artifact.write_text(json.dumps(synthetic.build_artifact(campaign)), encoding="utf-8")
        result = export(campaign.run_dirs, artifact, seeds_path=seeds_path, rubric_path=rubric_path,
                        registry_path=registry_path, vocabulary_path=vocabulary_path,
                        disclosure_log=Path(tmp) / "no_disclosure_log.jsonl", seal_registry=seal_registry,
                        example={"seed_id": cfg["seed_ids"][0], "turn": vocab.example["turn"]},
                        checkout=synthetic_checkout(Path(tmp)), plan_path=campaign.plan_path)
    return samplify(result, cfg["rng_seed"])


# ------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=Path, help="the landed wave-2 run directories the artifact covers")
    ap.add_argument("--analysis", type=Path, help="the section 10 artifact (petri_w2_register_contrast.py --final)")
    ap.add_argument("--site", type=Path, default=DEFAULT_SITE, help="the site checkout (files go to <site>/data/)")
    ap.add_argument("--previous", type=Path, help="an earlier summary file: print every cell that changed")
    ap.add_argument("--dry-run", action="store_true", help="check and report; write nothing")
    ap.add_argument("--write-samples", action="store_true",
                    help="write the two SYNTHETIC .sample.json fixtures instead (no runs, no artifact)")
    ap.add_argument("--seeds", type=Path, default=SEED_FILE)
    ap.add_argument("--rubric", type=Path, default=ADVICE_RUBRIC)
    ap.add_argument("--outcomes", type=Path, default=OUTCOME_REGISTRY)
    ap.add_argument("--vocabulary", type=Path, default=VOCABULARY_FILE)
    ap.add_argument("--wording", type=Path, default=WORDING_FILE)
    ap.add_argument("--design-note", type=Path, default=DESIGN_NOTE)
    ap.add_argument("--swaps", type=Path, default=SWAPS_FILE)
    ap.add_argument("--plan", type=Path, default=PLAN_FILE, help="the section 10 plan the analysis read")
    ap.add_argument("--disclosure-log", type=Path, default=DISCLOSURE_LOG)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.write_samples:
            if args.runs or args.analysis:
                raise ExportRefusal("--write-samples builds from synthetic input; it takes no runs and no --analysis")
            summary, conversations = sample_export(vocabulary_path=args.vocabulary, seeds_path=args.seeds,
                                                   rubric_path=args.rubric, registry_path=args.outcomes)
            notes: list[str] = ["SYNTHETIC sample fixtures (placeholder text, random grades)"]
            sample = True
        else:
            if args.analysis is None or not args.runs:
                raise ExportRefusal("give --analysis and the run directories it covers")
            result = export(args.runs, args.analysis, seeds_path=args.seeds, rubric_path=args.rubric,
                            registry_path=args.outcomes, vocabulary_path=args.vocabulary, wording_path=args.wording,
                            design_note=args.design_note, swaps_path=args.swaps, disclosure_log=args.disclosure_log,
                            plan_path=args.plan)
            summary, conversations, notes, sample = result.summary, result.conversations, result.notes, False
        if args.previous is not None:
            old = _load(args.previous, "--previous")
            changed = diff_cells(old, summary)
            print(f"--previous {args.previous}: {len(changed)} changed cell(s)")
            for line in changed:
                print(f"  {line}")
        written = [] if args.dry_run else write_site(args.site, summary, conversations, sample=sample)
    except ExportRefusal as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"headline row: {summary['headline']['row_id']}; style row: {summary['style_sentence']['row_id']}")
    print(f"{len(summary['triples'])} triples ({summary['primary']['triples']} entering the primary test), "
          f"{len(conversations['conversations'])} conversations, {len(conversations['seeds'])} seeds")
    print(f"analysis commit {summary['provenance']['analysis_commit']}; "
          f"exporter commit {summary['provenance']['exporter_commit']}")
    for line in notes:
        print(f"  {line}")
    print("dry run: nothing written" if args.dry_run else "wrote " + ", ".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
