"""SYNTHETIC wave-2 run directories and a SYNTHETIC design-note section 10 artifact, for the tests of
scripts/export_petri_multiturn.py and for its --write-samples mode.

Nothing here reads a landed run or computes anything on landed data (design note 10.6): the seeds are the seed
file's (their scripted user turns are what a real transcript carries, and the judge's planner checks them), every
assistant reply is a placeholder, every grade is drawn from `random.Random(rng_seed)` over the values the judge's own
planner (`judge_runner.plan_run`) allows for that row, and the artifact is computed from those synthetic rows in the
shape `scripts/petri_w2_register_contrast.py --final` writes (script version 1.1, the fields the exporter reads),
including the section 10.2 wording row and the section 10.3 statement, each selected from the rows by the analysis's
own rule (wording_row, decomposition_statement). A test that needs a given row or statement states it through
`build_campaign`'s `design`, which fixes the rank of every final response-only tier grade, rather than searching for
random data that produces it; the flags that decide the exporter's other refusals are parameters.

The run directories sit under `<root>/data/petri/runs/`, the layout the exporter's verify-chain command names, each
manifest sealed into that directory's `manifests.chain` (so the command verifies them, as it does landed runs), and the
plan the campaign's fires realise is written to `<root>/plan.json`, whose sha256 the artifact records. Every transcript
record is bound to its run's manifest as the adapter binds it (provenance.run_manifest.sha256, the manifest's identity
digest), and the model fields record the campaign's registered models (data/petri/multiturn_measures.json
campaign_models, the first of each list: the manifest's models.target and judge of record, each record's source, each
judgment's judge_model), so the exporter checks synthetic runs exactly as it checks landed ones; the replies are
placeholders all the same.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

try:
    from scripts.petri_audit import judge_runner
    from scripts.petri_audit.framework import sha256_file
    from scripts.petri_audit.manifest import CHAIN_FILE, identity_digest, seal_manifest
    from scripts.petri_audit.rules import rule_outcomes
    from scripts.petri_audit.seeds import ROOT_BRANCH, seed_digest, text_of, texts_by_key, tool_result_for
except ModuleNotFoundError:  # run as a file path: the repository root is not on sys.path
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.petri_audit import judge_runner
    from scripts.petri_audit.framework import sha256_file
    from scripts.petri_audit.manifest import CHAIN_FILE, identity_digest, seal_manifest
    from scripts.petri_audit.rules import rule_outcomes
    from scripts.petri_audit.seeds import ROOT_BRANCH, seed_digest, text_of, texts_by_key, tool_result_for

RUNS_SUBPATH = ("data", "petri", "runs")
REGISTERS = ("colloquial", "lay_careful", "clinical")
TOOL_QUERY = "synthetic query"
EXCHANGES = 10                 # design note 10.1: all ten scripted exchanges
WINDOW = tuple(range(1, EXCHANGES + 1))
FLOOR = 8                      # design note 10.1: a triple enters with at least 8 comparable exchanges
BOOTSTRAP_SEED = 20260923      # the seed 10.2 fixes; recorded as the real artifact records it
ALPHA = 0.05
PRIMARY = ("tier", "response_only")          # 10.1's outcome
# the analysis commit a synthetic artifact records: the one commit export_petri_multiturn.synthetic_checkout accepts
ANALYSIS_COMMIT = "c" * 40
# the analysis inputs a synthetic artifact records (identity.inputs, as the real artifact does), by name and path: the
# synthetic "analysis" is this module, the plan is the campaign's own, the rest are the repository's files
ANALYSIS_INPUT_PATHS = {"script": "scripts/petri_multiturn_synthetic.py",
                        "judge_runner": "scripts/petri_audit/judge_runner.py", "plan": "plan.json",
                        "seed_file": "docs/framework/petri_seeds.draft.json", "rubric": "data/advice_rubric.draft.json",
                        "outcome_registry": "docs/framework/outcome_dimensions.draft.json"}
REPO_ROOT = Path(__file__).resolve().parents[1]
# the page vocabulary, whose campaign_models the exporter holds every run to
VOCABULARY_FILE = REPO_ROOT / "data" / "petri" / "multiturn_measures.json"


def registered_models(vocabulary: Path = VOCABULARY_FILE) -> dict[str, Any]:
    """The campaign_models block of the page vocabulary: {target, target_served, judge}, each a list of model strings,
    and target_temperature, the number the page states."""
    return json.loads(Path(vocabulary).read_text(encoding="utf-8"))["campaign_models"]


def input_file(root: Path, rel: str) -> Path:
    """Where a synthetic artifact's recorded input lives: under the campaign root (the plan), else the repository."""
    return Path(root) / rel if (Path(root) / rel).is_file() else REPO_ROOT / rel

RowsEdit = Callable[[str, list[dict]], list[dict]]          # (run stem, rows) -> rows
ManifestEdit = Callable[[str, dict], dict]                  # (run stem, manifest) -> manifest


@dataclass(frozen=True)
class Fire:
    """One synthetic fire: its journal nonce, its partition and the campaign epoch it gives each scenario set."""
    nonce: str
    partition: str
    campaign_epochs: dict[str, int]


@dataclass(frozen=True)
class Cell:
    """One final response-only tier grade of a synthetic campaign: the fire, the seed, the speaker (None without
    speaker arms), the register of the conversation, and the exchange."""
    fire: Fire
    seed_id: str
    speaker: str | None
    register: str
    exchange: int


# the rank (index in the rubric's tier order) a cell's grade is given, or None for a judge-error null (not comparable)
Design = Callable[[Cell], int | None]


def epoch_fires(epochs: int, set_name: str) -> list[Fire]:
    """One fire per campaign epoch of one scenario set: the first half discovery, the rest prospective."""
    half = (epochs + 1) // 2
    return [Fire(f"syn{e}", "discovery" if e <= half else "prospective", {set_name: e}) for e in range(1, epochs + 1)]


@dataclass
class SyntheticRun:
    stem: str
    path: Path
    fire: Fire
    manifest: dict
    rows: list[dict]


@dataclass
class Campaign:
    root: Path
    runs: list[SyntheticRun]
    sets: dict[str, list[str]]
    seeds: dict[str, dict]
    rubric: dict
    registry: dict
    plan_path: Path
    decomposition_set: str

    @property
    def run_dirs(self) -> list[Path]:
        return [r.path for r in self.runs]


def layout(seed: Mapping[str, Any]) -> tuple[list[str | None], dict[tuple[str | None, str], dict]]:
    """A seed's speakers (first-appearance order) and its arm per (speaker, register), read as the section 10 analysis
    reads them: the speaker is `user_is` when speaker identity is a factor, the register that of the turn-1 text."""
    factor = (seed.get("speaker_identity") or {}).get("policy") == "factor"
    texts = texts_by_key(dict(seed))
    speakers: list[str | None] = []
    cells: dict[tuple[str | None, str], dict] = {}
    for arm in seed["protocol"]["arms"]:
        speaker = arm["user_is"] if factor else None
        if speaker not in speakers:
            speakers.append(speaker)
        cells[(speaker, texts[arm["turns"][0]["text_ref"]]["register"])] = arm
    return speakers, cells


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _conversation(seed: Mapping[str, Any], arm: Mapping[str, Any], cid: str, tool_exchange: int,
                  source: Mapping[str, Any]) -> tuple[dict, dict]:
    """One transcript record and its rule outcome. User turns carry the seed's scripted texts; replies are
    placeholders. A seed with tools makes one call at `tool_exchange`, answered by the seed's scripted result. The
    rule outcome is the lane's own (`rules.rule_outcomes` over the record), so it has the shapes a landed run's has
    (`query_text` a list of every call's arguments; Codex review of PR #40, 2026-09-24: a hand-built one gave a
    string, and the samples built from it never carried the list the real files do). The record carries `source` and
    a provenance block whose run-manifest binding build_campaign fills once the manifest's identity is known."""
    results = (seed.get("tools") or {}).get("results") or []
    tool = results[0]["tool"] if results else None
    turns: list[dict] = []
    tid = 0
    for i, entry in enumerate(arm["turns"], 1):
        tid += 1
        user = tid
        turns.append({"turn_id": tid, "role": "user", "text": text_of(dict(seed), entry["text_ref"]),
                      "attachments_omitted": 0})
        if tool and i == tool_exchange:
            args = {"query": TOOL_QUERY}
            call_id = f"call_{cid[:8]}_{i}"
            tid += 1
            turns.append({"turn_id": tid, "role": "assistant", "text": "", "attachments_omitted": 0, "reply_to": user,
                          "tool_calls": [{"call_id": call_id, "name": tool, "arguments": args, "parse_error": None}]})
            result, _, _ = tool_result_for(dict(seed), tool, args)
            tid += 1
            turns.append({"turn_id": tid, "role": "tool", "text": result, "attachments_omitted": 0,
                          "tool_call_id": call_id})
        tid += 1
        turns.append({"turn_id": tid, "role": "assistant", "text": f"[Synthetic reply to exchange {i}: placeholder.]",
                      "attachments_omitted": 0, "reply_to": user})
    record = {"conversation_id": cid, "source": dict(source), "turns": turns, "provenance": {"run_manifest": None}}
    return record, rule_outcomes(record, dict(seed))


def _judgment(plan: judge_runner.JudgePlan, rng: random.Random, judge_model: str) -> dict:
    """A judgment row for one plan: the planner's not-applicable rows as the runner writes them, otherwise a value
    drawn from the plan's allowed values (and, for a tier, every rubric flag)."""
    base = {"conversation_id": plan.conversation_id, "turn_id": plan.turn_id,
            "assistant_turn_index": plan.assistant_turn_index, "exchange_index": plan.exchange_index,
            "final_in_exchange": plan.final_in_exchange, "kind": plan.kind, "key": plan.key,
            "prompt_ref": plan.prompt_ref, "prompt_file_digest": plan.prompt_file_digest, "judge_model": judge_model}
    if plan.prompt is None:
        return {**base, "value": judge_runner.NA, "flags": None, "method": "rule",
                "not_applicable_reason": plan.not_applicable_reason, "answer_form": None, "judge_error": None}
    value = rng.choice([v for v in plan.allowed_values if v != judge_runner.NA])
    flags = {f: rng.random() < 0.3 for f in plan.allowed_flags} if plan.kind == "tier" else None
    return {**base, "value": value, "flags": flags, "method": "judge", "not_applicable_reason": None,
            "answer_form": "json_object" if plan.kind == "tier" else "value_only", "judge_error": None}


def run_stem(k: int) -> str:
    """The stem of the campaign's k-th run (1-based), in the lane's run_<workflow run id>_<attempt> form."""
    return f"run_{9_000_000_000 + k}_1"


def below_floor(k: int, exchanges: Sequence[int] = (1, 2, 3)) -> RowsEdit:
    """A judgments edit for build_campaign that leaves one triple of the k-th run below 10.1's floor: the final
    response-only tier rows of the run's first conversation, at the given exchanges, become judge-error nulls, so
    that conversation's triple keeps fewer than 8 comparable exchanges."""
    def edit(stem: str, rows: list[dict]) -> list[dict]:
        if stem != run_stem(k) or not rows:
            return rows
        cid = rows[0]["conversation_id"]
        for r in rows:
            if (r["conversation_id"] == cid and (r["kind"], r["key"]) == ("tier", "response_only")
                    and r["final_in_exchange"] and r["exchange_index"] in exchanges):
                r.update(value=None, flags=None, answer_form=None,
                         judge_error="synthetic: answer is not one of the declared values")
        return rows
    return edit


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _apply_design(design: Design, fire: Fire, judgments: list[dict], cell_of: Mapping[str, tuple],
                  tiers: Sequence[str]) -> None:
    """Give every final response-only tier grade the rank the design names (its flags are kept), or make it a
    judge-error null. Applied after every grade is drawn, so the generator's sequence, and every other grade, is the
    one an undesigned campaign draws."""
    for j in judgments:
        if ((j["kind"], j["key"]) != PRIMARY or j["final_in_exchange"] is not True
                or j.get("not_applicable_reason")):
            continue
        sid, speaker, register = cell_of[j["conversation_id"]]
        rank = design(Cell(fire, sid, speaker, register, j["exchange_index"]))
        if rank is None:
            j.update(value=None, flags=None, answer_form=None, judge_error="synthetic: a designed null")
        else:
            j["value"] = tiers[rank]


def build_campaign(root: Path, *, seeds: Mapping[str, dict], sets: Mapping[str, Sequence[str]],
                   fires: Sequence[Fire], rubric: dict, registry: dict, rng_seed: int, tool_exchange: int = 5,
                   design: Design | None = None, decomposition_set: str | None = None,
                   judgment_edit: RowsEdit | None = None, rule_edit: RowsEdit | None = None,
                   transcript_edit: RowsEdit | None = None, manifest_edit: ManifestEdit | None = None,
                   models: Mapping[str, Sequence[str]] | None = None) -> Campaign:
    """One synthetic run directory per fire, each running one epoch of every seed of the sets the fire names.
    `design` fixes the final response-only tier grades (grades are otherwise drawn at random); `decomposition_set` is
    the plan's section 10.3 set (by default the last scenario set, as the real plan's second set is); `models` is a
    campaign_models block (by default the page vocabulary's), whose first target, served string and judge every run
    records. The edit hooks change a run's judgments, rule outcomes, transcripts or manifest before its digests are
    taken, so the manifest binds the edited files (a test's case is then the only thing wrong with the run): the
    manifest is edited before the transcript records are bound to its identity digest, and the transcripts after they
    are bound, so each edit is the last word on what it changes."""
    decomposition_set = decomposition_set if decomposition_set is not None else list(sets)[-1]
    models = registered_models() if models is None else models
    target, served, judge = models["target"][0], models["target_served"][0], models["judge"][0]
    source = {"system": "synthetic", "product": None, "model": target, "model_version": served,
              "capture_method": "synthetic", "captured_utc": None}
    tiers = [t["id"] for t in rubric["tiers"]]
    rng = random.Random(rng_seed)
    runs_dir = Path(root).joinpath(*RUNS_SUBPATH)
    runs_dir.mkdir(parents=True, exist_ok=True)
    runs: list[SyntheticRun] = []
    for k, fire in enumerate(fires, 1):
        stem = run_stem(k)
        path = runs_dir / stem
        path.mkdir()
        seed_ids = [sid for set_name in fire.campaign_epochs for sid in sets[set_name]]
        records, rules, trees = [], [], []
        cell_of: dict[str, tuple] = {}
        for sid in seed_ids:
            seed = seeds[sid]
            arm_cell = {arm["id"]: cell for cell, arm in layout(seed)[1].items()}
            for arm in seed["protocol"]["arms"]:
                cid = _sha(f"{stem}|{sid}|{arm['id']}")
                cell_of[cid] = (sid, *arm_cell[arm["id"]])
                record, outcomes = _conversation(seed, arm, cid, tool_exchange, source)
                records.append(record)
                rules.append({"conversation_id": cid, "seed_id": sid, "branch_id": ROOT_BRANCH,
                              "condition_id": arm["id"], "annotator": "rule:synthetic", "outcomes": outcomes})
                trees.append({"tree_id": f"{sid}::{arm['id']}#1", "seed_id": sid, "arm": arm["id"], "epoch": 1,
                              "system_prompt_variant": None, "survivor_exported": True,
                              "branches": [{"branch_id": ROOT_BRANCH, "conversation_id": cid,
                                            "condition_id": arm["id"], "branched_from_turn_id": None}]})
        manifest: dict[str, Any] = {
            "run_id": f"synthetic-{stem}", "created_utc": f"2026-09-{10 + k:02d}T00:00:00Z",
            "harness": {"environment_lock_sha256": _sha("synthetic environment lock")},
            "execution": {"claim_grade_eligible": True, "epochs": 1,
                          "contract_checks": {"holdout_seal": {"status": "pass", "detail": "synthetic"}}},
            "spend": {"journal_nonce": fire.nonce},
            "models": {"target": {"provider": target.split("/", 1)[0], "model": target.split("/", 1)[-1],
                                  "inspect_name": target, "registry_spec": target, "served_model_strings": [served],
                                  "config": {"temperature": float(models.get("target_temperature", 1.0))},
                                  "seed_requested": None, "seed_forwarded_by_provider": None,
                                  "seed_honored": None},
                       "auditor": None, "judge_harness": None},
            "seeds": [{"seed_id": sid, "seed_sha256": seed_digest(seeds[sid])} for sid in seed_ids],
            "trees": trees,
            "holdout": {"phrases_in_seeds": 0, "sealed_phrases_in_seeds": 0, "consumed": False,
                        "consumption_registry_ref": None, "consumed_phrase_sha1": []},
            "artifacts": {"raw_eval_log_sha256": _sha("synthetic raw log"), "raw_eval_log_published": False,
                          "raw_eval_log_custody": "synthetic: no raw log exists",
                          "sanitised_log_sha256": _sha("synthetic sanitised log"),
                          "sanitiser": {"version": "synthetic", "allowlist_sha256": _sha("synthetic allowlist")},
                          # the record-dependent fields, filled once the files are written (the identity digest
                          # blanks them, and a key it blanks must be present when the records are bound too)
                          "transcripts_sha256": None, "rule_outcomes_sha256": None, "judgments_sha256": None,
                          "judge_of_record": {"judge_model": judge}},
        }
        plans = judge_runner.plan_run(records, manifest, dict(seeds), outcomes=registry, rubric=rubric)
        judgments = [_judgment(p, rng, judge) for p in plans]
        if design:
            _apply_design(design, fire, judgments, cell_of, tiers)
        if judgment_edit:
            judgments = judgment_edit(stem, judgments)
        if rule_edit:
            rules = rule_edit(stem, rules)
        if manifest_edit:
            manifest = manifest_edit(stem, manifest)
        # the identity digest leaves out the chain and the record-dependent fields set below, so it is the one the
        # chain seals; every record names it, as the adapter's second pass binds it (transcripts.bind_manifest)
        identity = identity_digest(manifest)
        for record in records:
            record["provenance"]["run_manifest"] = {"sha256": identity, "ref": f"{stem}/manifest.json"}
        if transcript_edit:
            records = transcript_edit(stem, records)
        for name, rows in (("judgments", judgments), ("transcripts", records), ("rule_outcomes", rules)):
            _write_jsonl(path / f"{name}.jsonl", rows)
            manifest["artifacts"][f"{name}_sha256"] = sha256_file(path / f"{name}.jsonl")
        (path / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        rows = judge_runner.analysis_rows(judgments, manifest, dict(seeds))
        runs.append(SyntheticRun(stem, path, fire, manifest, rows))
    prev: str | None = None
    lines = []
    for run in runs:                      # the chain, in fire order, as the lane's landing appends it
        run.manifest = seal_manifest(run.manifest, prev)
        (run.path / "manifest.json").write_text(json.dumps(run.manifest, indent=1) + "\n", encoding="utf-8")
        prev = run.manifest["chain"]["manifest_sha256"]
        lines.append(f"{run.stem}/manifest.json {prev}")
    (runs_dir / CHAIN_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan_path = Path(root) / "plan.json"
    plan_path.write_text(json.dumps(plan_doc(seeds, sets, fires, decomposition_set), indent=1) + "\n",
                         encoding="utf-8")
    return Campaign(Path(root), runs, {k: list(v) for k, v in sets.items()}, dict(seeds), rubric, registry, plan_path,
                    decomposition_set)


def plan_doc(seeds: Mapping[str, dict], sets: Mapping[str, Sequence[str]], fires: Sequence[Fire],
             decomposition_set: str) -> dict[str, Any]:
    """The section 10 plan these fires realise, in the plan file's shape: the scenario sets, each fire's partition and
    campaign epochs, the final triple count by partition (one triple per seed, epoch and speaker), and the 10.3 set."""
    by_partition: dict[str, int] = {}
    for fire in fires:
        n = sum(len(layout(seeds[sid])[0]) for set_name in fire.campaign_epochs for sid in sets[set_name])
        by_partition[fire.partition] = by_partition.get(fire.partition, 0) + n
    return {"scenario_sets": {k: list(v) for k, v in sets.items()},
            "fires": [{"journal_nonce": f.nonce, "campaign_epochs": dict(f.campaign_epochs), "partition": f.partition}
                      for f in fires],
            "final_triples": sum(by_partition.values()), "partition_triples": by_partition,
            "decomposition_set": decomposition_set}


def _binomial_p(k: int, n: int) -> float:
    """Exact two-sided sign-test p for k of n on the smaller side (1.0 when n = 0)."""
    if n == 0:
        return 1.0
    m = min(k, n - k)
    return float(min(Fraction(1), Fraction(2 * sum(math.comb(n, i) for i in range(m + 1)), 2 ** n)))


def _sign_test(ds: Sequence[Fraction]) -> dict[str, Any]:
    neg, pos = sum(d < 0 for d in ds), sum(d > 0 for d in ds)
    p = _binomial_p(min(neg, pos), neg + pos)
    return {"triples": len(ds), "negative": neg, "positive": pos, "tied": len(ds) - neg - pos, "non_tied": neg + pos,
            "p": p, "alpha": ALPHA, "significant": p < ALPHA,
            "direction": "negative" if neg > pos else "positive" if pos > neg else "none"}


def _holm(pvalues: Mapping[str, float]) -> dict[str, dict[str, Any]]:
    """Holm's step-down correction, as the analysis's holm computes it."""
    m = len(pvalues)
    out: dict[str, dict[str, Any]] = {}
    running = 0.0
    for i, name in enumerate(sorted(pvalues, key=lambda k: (pvalues[k], k))):
        running = max(running, min(1.0, (m - i) * pvalues[name]))
        out[name] = {"p": pvalues[name], "p_holm": running, "significant_after_holm": running < ALPHA}
    return {name: out[name] for name in pvalues}


def _wording_row(primary: Mapping[str, Any], gate: Mapping[str, Any], replication: Mapping[str, Any],
                 planned_scenarios: int) -> dict[str, Any]:
    """The 10.2 row the tests select, by the analysis's wording_row rule (the fields the exporter reads)."""
    direction = primary["direction"]
    gate_same = bool(gate["significant"]) and gate["direction"] == direction
    gate_opposite = bool(gate["significant"]) and gate["direction"] not in (direction, "none")
    reasons: list[str] = []
    if primary["non_tied"] == 0:
        row = "not_computable"
        reasons.append("synthetic: no non-tied triple")
    elif not primary["significant"]:
        row = "row5"
    elif gate_opposite:
        row = "no_prespecified_row"
        reasons.append("synthetic: the gate is significant in the opposite direction")
    else:
        base = ("row1" if replication["same_direction"] else "row2") if gate_same else "row3"
        row = base if direction == "negative" else f"row4/{base}"
    if gate["scenarios"] < planned_scenarios:
        reasons.append(f"synthetic: the gate ran on {gate['scenarios']} of {planned_scenarios} scenarios")
    return {"row_id": row, "selectable_as_registered": not reasons, "not_selectable_reasons": reasons,
            "gate_same_direction": gate_same, "gate_scenarios": gate["scenarios"],
            "planned_scenarios": planned_scenarios, "prospective_same_direction": replication["same_direction"]}


def _statement(tests: Mapping[str, Mapping[str, Any]], adjusted: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The 10.3 statement the Holm-corrected tests permit, by the analysis's decomposition_statement rule."""
    sig = {k: adjusted[k]["significant_after_holm"] for k in adjusted}
    style, vocabulary, paired = tests["style"], tests["vocabulary"], tests["paired_difference"]
    if paired["non_tied"] == 0:
        sid = "not_computable"
    elif not sig["paired_difference"]:
        sid = "not_separated"
    elif paired["direction"] == "negative" and sig["style"] and style["direction"] == "negative":
        sid = "style_larger"
    else:
        sid = "no_prespecified_statement"
    also = sid == "style_larger" and sig["vocabulary"] and vocabulary["direction"] == "negative"
    return {"statement_id": sid, "vocabulary_also_lowered": also}


def _window_name(window: Sequence[int]) -> str:
    return f"exchange {window[0]}" if len(window) == 1 else f"exchanges {window[0]}-{window[-1]}"


def build_artifact(campaign: Campaign, *, section_10_3_refused: bool = False, final: bool = True,
                   truncated: bool = False, commit: str = ANALYSIS_COMMIT, window: Sequence[int] = WINDOW,
                   floor: int = FLOOR) -> dict[str, Any]:
    """The artifact the exporter reads, computed from the campaign's synthetic rows: every triple with its primary
    standing (comparable exchanges over `window`, entering with at least `floor`, and for an entering triple D, sum and
    n), the primary sign test, the scenario gate and its means, the prospective replication and the 10.2 row they
    select; the 10.3 decomposition on the plan's set (style, vocabulary and their paired difference on three-way
    complete exchanges, Holm-corrected) and the statement it permits; the coverage of both contrasts; and the run
    coverage with each file's sha256. `window` and `floor` stand for an analysis run with another window or floor than
    10.1's (the exporter refuses one)."""
    digest = judge_runner.rubric_digest(campaign.rubric)
    tiers = [t["id"] for t in campaign.rubric["tiers"]]
    window = tuple(window)
    final_rows: dict[tuple[str, int], list[dict]] = {}
    for run in campaign.runs:
        for r in run.rows:
            if (r["kind"], r["key"]) == PRIMARY and r["final_in_exchange"] is True:
                final_rows.setdefault((r["conversation_id"], r["exchange_index"]), []).append(r)

    def valued(cid: str | None, ex: int) -> dict | None:
        rows = [r for r in final_rows.get((cid, ex), []) if r.get("prompt_file_digest") == digest]
        ok = len(rows) == 1 and rows[0]["value"] in tiers and not rows[0].get("not_applicable_reason")
        return rows[0] if ok else None

    def rank(cid: str | None, ex: int) -> int:
        return tiers.index(valued(cid, ex)["value"])

    triples, entering, decomposition = [], [], []
    for run in campaign.runs:
        by_arm = {(t["seed_id"], t["arm"]): t["branches"][0]["conversation_id"] for t in run.manifest["trees"]}
        for set_name, epoch in run.fire.campaign_epochs.items():
            for sid in campaign.sets[set_name]:
                speakers, cells = layout(campaign.seeds[sid])
                for speaker in speakers:
                    convs = {r: by_arm.get((sid, cells[(speaker, r)]["id"])) for r in REGISTERS}
                    comparable = [ex for ex in window
                                  if valued(convs["colloquial"], ex) and valued(convs["clinical"], ex)]
                    enters = len(comparable) >= floor
                    rec: dict[str, Any] = {
                        "enters": enters, "comparable_exchanges": comparable, "excluded_exchanges": {},
                        "reason": None if enters else (f"{len(comparable)} of {len(window)} exchanges comparable "
                                                       f"({_window_name(window)}); the floor is {floor}")}
                    if enters:
                        diffs = [rank(convs["colloquial"], ex) - rank(convs["clinical"], ex) for ex in comparable]
                        d = Fraction(sum(diffs), len(diffs))
                        rec.update({"D": float(d), "D_exact": str(d), "sum": sum(diffs), "n": len(diffs),
                                    "lower": sum(x < 0 for x in diffs), "higher": sum(x > 0 for x in diffs),
                                    "lower_minus_higher": sum(x < 0 for x in diffs) - sum(x > 0 for x in diffs)})
                        entering.append((sid, run.fire.partition, d))
                    if set_name == campaign.decomposition_set:
                        complete = [ex for ex in window if all(valued(convs[r], ex) for r in REGISTERS)]
                        if len(complete) >= floor:
                            style = sum(rank(convs["colloquial"], ex) - rank(convs["lay_careful"], ex)
                                        for ex in complete)
                            vocabulary = sum(rank(convs["lay_careful"], ex) - rank(convs["clinical"], ex)
                                             for ex in complete)
                            decomposition.append((Fraction(style, len(complete)), Fraction(vocabulary, len(complete)),
                                                  Fraction(style - vocabulary, len(complete))))
                    triples.append({
                        "triple": f"{sid}#e{epoch}" + (f"/{speaker}" if speaker else ""), "seed_id": sid,
                        "scenario_set": set_name, "campaign_epoch": epoch, "speaker": speaker,
                        "partition": run.fire.partition, "journal_nonce": run.fire.nonce, "run_stem": run.stem,
                        "landed": True, "conversations": convs, "missing_conversations": {},
                        "contrasts": {"primary": rec}})
    primary = _sign_test([d for _, _, d in entering])
    groups: dict[str, list[Fraction]] = {}
    for sid, _, d in entering:
        groups.setdefault(sid, []).append(d)
    means = {s: sum(v, Fraction(0)) / len(v) for s, v in sorted(groups.items())}
    vals = list(means.values())
    observed = abs(sum(vals, Fraction(0)))
    hits = sum(1 for signs in itertools.product((1, -1), repeat=len(vals))
               if abs(sum((s * v for s, v in zip(signs, vals)), Fraction(0))) >= observed)
    gate_p = Fraction(hits, 2 ** len(vals))
    total = sum(vals, Fraction(0))
    gate = {"scenarios": len(vals), "scenario_means": {s: float(m) for s, m in means.items()},
            "scenario_means_exact": {s: str(m) for s, m in means.items()}, "p": float(gate_p),
            "p_exact": str(gate_p), "alpha": ALPHA, "significant": float(gate_p) < ALPHA,
            "direction": "negative" if total < 0 else "positive" if total > 0 else "none"}
    replication = _sign_test([d for _, partition, d in entering if partition == "prospective"])
    replication["same_direction"] = primary["direction"] != "none" and replication["direction"] == primary["direction"]
    planned = sum(len(v) for v in campaign.sets.values())
    s103: dict[str, Any]
    if section_10_3_refused:
        s103 = {"status": "refused", "reason": "synthetic"}
    else:
        tests = {name: _sign_test([row[i] for row in decomposition])
                 for i, name in enumerate(("style", "vocabulary", "paired_difference"))}
        adjusted = _holm({k: v["p"] for k, v in tests.items()})
        s103 = {"scenario_set": campaign.decomposition_set, "exchanges": "three-way complete", "tests": tests,
                "holm": adjusted, "statement": _statement(tests, adjusted)}
    heads = {name: {"section": section, "measure": "tier_response_only", "registers": registers,
                    "window": _window_name(window), "floor": floor, "scope": scope, "status": "computable"}
             for name, section, registers, scope in (
                 ("primary", "10.2", ["colloquial", "clinical"], "all"),
                 ("decomposition", "10.3", list(REGISTERS), f"set:{campaign.decomposition_set}"))}
    runs = [{"run_stem": r.stem, "run_id": r.manifest["run_id"], "path": str(r.path),
             "judgments_sha256": sha256_file(r.path / "judgments.jsonl"),
             "manifest_sha256": sha256_file(r.path / "manifest.json")} for r in campaign.runs]
    names = ("script", "judge_runner", "plan", "seed_file", "rubric", "outcome_registry")
    return {
        "analysis": ("SYNTHETIC artifact in the shape of scripts/petri_w2_register_contrast.py --final (script "
                     "version 1.1); not a result"),
        "final": final, "run_list": [r["path"] for r in runs], "bootstrap_seed": BOOTSTRAP_SEED,
        "identity": {"commit": commit, "uncommitted_changes": {n: [] for n in names},
                     "inputs": {n: {"path": rel, "sha256": sha256_file(input_file(campaign.root, rel))}
                                for n, rel in ANALYSIS_INPUT_PATHS.items()}},
        "administratively_truncated": truncated, "truncation_reason": "synthetic" if truncated else None,
        "fires_not_landed": ["synthetic"] if truncated else [],
        "coverage": {"runs": runs, "rubric": {"digest": digest},
                     "plan": {"path": str(campaign.plan_path), "sha256": sha256_file(campaign.plan_path)},
                     "contrasts": heads},
        "triples": triples,
        "section_10_2": {"primary_sign_test": primary, "scenario_gate": gate, "prospective_replication": replication,
                         "wording": _wording_row(primary, gate, replication, planned)},
        "section_10_3": s103, "section_10_4": {}, "section_10_5": {},
    }
