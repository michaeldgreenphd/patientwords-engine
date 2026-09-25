"""SYNTHETIC wave-2 run directories and a SYNTHETIC design-note section 10 artifact, for the tests of
scripts/export_petri_multiturn.py and for its --write-samples mode.

Nothing here reads a landed run or computes anything on landed data (design note 10.6): the seeds are the seed
file's (their scripted user turns are what a real transcript carries, and the judge's planner checks them), every
assistant reply is a placeholder, every grade is drawn from `random.Random(rng_seed)` over the values the judge's own
planner (`judge_runner.plan_run`) allows for that row, and the artifact is computed from those synthetic rows in the
shape `scripts/petri_w2_register_contrast.py --final` writes (script version 1.1, the fields the exporter reads). The
wording row, the section 10.3 statement and the flags that decide the exporter's refusals are parameters, so a test
states the case it exercises rather than searching for random data that produces it.

The run directories sit under `<root>/data/petri/runs/`, the layout the exporter's verify-chain command names, each
manifest sealed into that directory's `manifests.chain` (so the command verifies them, as it does landed runs), and the
plan the campaign's fires realise is written to `<root>/plan.json`, whose sha256 the artifact records.
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
    from scripts.petri_audit.manifest import CHAIN_FILE, seal_manifest
    from scripts.petri_audit.rules import rule_outcomes
    from scripts.petri_audit.seeds import ROOT_BRANCH, seed_digest, text_of, texts_by_key, tool_result_for
except ModuleNotFoundError:  # run as a file path: the repository root is not on sys.path
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.petri_audit import judge_runner
    from scripts.petri_audit.framework import sha256_file
    from scripts.petri_audit.manifest import CHAIN_FILE, seal_manifest
    from scripts.petri_audit.rules import rule_outcomes
    from scripts.petri_audit.seeds import ROOT_BRANCH, seed_digest, text_of, texts_by_key, tool_result_for

RUNS_SUBPATH = ("data", "petri", "runs")
REGISTERS = ("colloquial", "lay_careful", "clinical")
JUDGE_MODEL = "synthetic/judge"
TOOL_QUERY = "synthetic query"
FLOOR = 8                      # design note 10.1: a triple enters with at least 8 comparable exchanges
BOOTSTRAP_SEED = 20260923      # the seed 10.2 fixes; recorded as the real artifact records it
ALPHA = 0.05

RowsEdit = Callable[[str, list[dict]], list[dict]]          # (run stem, rows) -> rows
ManifestEdit = Callable[[str, dict], dict]                  # (run stem, manifest) -> manifest


@dataclass(frozen=True)
class Fire:
    """One synthetic fire: its journal nonce, its partition and the campaign epoch it gives each scenario set."""
    nonce: str
    partition: str
    campaign_epochs: dict[str, int]


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


def _conversation(seed: Mapping[str, Any], arm: Mapping[str, Any], cid: str,
                  tool_exchange: int) -> tuple[dict, dict]:
    """One transcript record and its rule outcome. User turns carry the seed's scripted texts; replies are
    placeholders. A seed with tools makes one call at `tool_exchange`, answered by the seed's scripted result. The
    rule outcome is the lane's own (`rules.rule_outcomes` over the record), so it has the shapes a landed run's has
    (`query_text` a list of every call's arguments; Codex review of PR #40, 2026-09-24: a hand-built one gave a
    string, and the samples built from it never carried the list the real files do)."""
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
    record = {"conversation_id": cid, "turns": turns}
    return record, rule_outcomes(record, dict(seed))


def _judgment(plan: judge_runner.JudgePlan, rng: random.Random) -> dict:
    """A judgment row for one plan: the planner's not-applicable rows as the runner writes them, otherwise a value
    drawn from the plan's allowed values (and, for a tier, every rubric flag)."""
    base = {"conversation_id": plan.conversation_id, "turn_id": plan.turn_id,
            "assistant_turn_index": plan.assistant_turn_index, "exchange_index": plan.exchange_index,
            "final_in_exchange": plan.final_in_exchange, "kind": plan.kind, "key": plan.key,
            "prompt_ref": plan.prompt_ref, "prompt_file_digest": plan.prompt_file_digest, "judge_model": JUDGE_MODEL}
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


def build_campaign(root: Path, *, seeds: Mapping[str, dict], sets: Mapping[str, Sequence[str]],
                   fires: Sequence[Fire], rubric: dict, registry: dict, rng_seed: int, tool_exchange: int = 5,
                   judgment_edit: RowsEdit | None = None, rule_edit: RowsEdit | None = None,
                   transcript_edit: RowsEdit | None = None, manifest_edit: ManifestEdit | None = None) -> Campaign:
    """One synthetic run directory per fire, each running one epoch of every seed of the sets the fire names. The
    edit hooks change a run's judgments, rule outcomes, transcripts or manifest before its digests are taken, so the
    manifest binds the edited files (a test's case is then the only thing wrong with the run)."""
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
        for sid in seed_ids:
            seed = seeds[sid]
            for arm in seed["protocol"]["arms"]:
                cid = _sha(f"{stem}|{sid}|{arm['id']}")
                record, outcomes = _conversation(seed, arm, cid, tool_exchange)
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
            "seeds": [{"seed_id": sid, "seed_sha256": seed_digest(seeds[sid])} for sid in seed_ids],
            "trees": trees,
            "holdout": {"phrases_in_seeds": 0, "sealed_phrases_in_seeds": 0, "consumed": False,
                        "consumption_registry_ref": None, "consumed_phrase_sha1": []},
            "artifacts": {"raw_eval_log_sha256": _sha("synthetic raw log"), "raw_eval_log_published": False,
                          "raw_eval_log_custody": "synthetic: no raw log exists",
                          "sanitised_log_sha256": _sha("synthetic sanitised log"),
                          "sanitiser": {"version": "synthetic", "allowlist_sha256": _sha("synthetic allowlist")}},
        }
        plans = judge_runner.plan_run(records, manifest, dict(seeds), outcomes=registry, rubric=rubric)
        judgments = [_judgment(p, rng) for p in plans]
        if judgment_edit:
            judgments = judgment_edit(stem, judgments)
        if rule_edit:
            rules = rule_edit(stem, rules)
        if transcript_edit:
            records = transcript_edit(stem, records)
        for name, rows in (("judgments", judgments), ("transcripts", records), ("rule_outcomes", rules)):
            _write_jsonl(path / f"{name}.jsonl", rows)
            manifest["artifacts"][f"{name}_sha256"] = sha256_file(path / f"{name}.jsonl")
        if manifest_edit:
            manifest = manifest_edit(stem, manifest)
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
    plan_path.write_text(json.dumps(plan_doc(seeds, sets, fires), indent=1) + "\n", encoding="utf-8")
    return Campaign(Path(root), runs, {k: list(v) for k, v in sets.items()}, dict(seeds), rubric, registry, plan_path)


def plan_doc(seeds: Mapping[str, dict], sets: Mapping[str, Sequence[str]], fires: Sequence[Fire]) -> dict[str, Any]:
    """The section 10 plan these fires realise, in the plan file's shape: the scenario sets, each fire's partition and
    campaign epochs, and the final triple count by partition (one triple per seed, epoch and speaker)."""
    by_partition: dict[str, int] = {}
    for fire in fires:
        n = sum(len(layout(seeds[sid])[0]) for set_name in fire.campaign_epochs for sid in sets[set_name])
        by_partition[fire.partition] = by_partition.get(fire.partition, 0) + n
    return {"scenario_sets": {k: list(v) for k, v in sets.items()},
            "fires": [{"journal_nonce": f.nonce, "campaign_epochs": dict(f.campaign_epochs), "partition": f.partition}
                      for f in fires],
            "final_triples": sum(by_partition.values()), "partition_triples": by_partition}


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


def build_artifact(campaign: Campaign, *, wording_row: str = "row5", selectable: bool = True,
                   statement: str = "not_computable", also_lowered: bool = False, section_10_3_refused: bool = False,
                   final: bool = True, truncated: bool = False, commit: str = "c" * 40) -> dict[str, Any]:
    """The artifact the exporter reads, computed from the campaign's synthetic rows: every triple with its primary
    standing (comparable exchanges, and for an entering triple D, sum and n), the primary sign test, the scenario gate
    and its means, and the run coverage with each file's sha256. The wording row and the 10.3 statement are given."""
    digest = judge_runner.rubric_digest(campaign.rubric)
    tiers = [t["id"] for t in campaign.rubric["tiers"]]
    final_rows: dict[tuple[str, int], list[dict]] = {}
    for run in campaign.runs:
        for r in run.rows:
            if (r["kind"], r["key"]) == ("tier", "response_only") and r["final_in_exchange"] is True:
                final_rows.setdefault((r["conversation_id"], r["exchange_index"]), []).append(r)

    def valued(cid: str | None, ex: int) -> dict | None:
        rows = [r for r in final_rows.get((cid, ex), []) if r.get("prompt_file_digest") == digest]
        ok = len(rows) == 1 and rows[0]["value"] in tiers and not rows[0].get("not_applicable_reason")
        return rows[0] if ok else None

    triples, entering = [], []
    for run in campaign.runs:
        by_arm = {(t["seed_id"], t["arm"]): t["branches"][0]["conversation_id"] for t in run.manifest["trees"]}
        for set_name, epoch in run.fire.campaign_epochs.items():
            for sid in campaign.sets[set_name]:
                speakers, cells = layout(campaign.seeds[sid])
                for speaker in speakers:
                    convs = {r: by_arm.get((sid, cells[(speaker, r)]["id"])) for r in REGISTERS}
                    n_ex = len(cells[(speaker, "clinical")]["turns"])
                    comparable = [ex for ex in range(1, n_ex + 1)
                                  if valued(convs["colloquial"], ex) and valued(convs["clinical"], ex)]
                    enters = len(comparable) >= FLOOR
                    rec: dict[str, Any] = {
                        "enters": enters, "comparable_exchanges": comparable, "excluded_exchanges": {},
                        "reason": None if enters else (f"{len(comparable)} of {n_ex} exchanges comparable "
                                                       f"(exchanges 1-{n_ex}); the floor is {FLOOR}")}
                    if enters:
                        diffs = [tiers.index(valued(convs["colloquial"], ex)["value"])
                                 - tiers.index(valued(convs["clinical"], ex)["value"]) for ex in comparable]
                        d = Fraction(sum(diffs), len(diffs))
                        rec.update({"D": float(d), "D_exact": str(d), "sum": sum(diffs), "n": len(diffs),
                                    "lower": sum(x < 0 for x in diffs), "higher": sum(x > 0 for x in diffs),
                                    "lower_minus_higher": sum(x < 0 for x in diffs) - sum(x > 0 for x in diffs)})
                        entering.append((sid, d))
                    triples.append({
                        "triple": f"{sid}#e{epoch}" + (f"/{speaker}" if speaker else ""), "seed_id": sid,
                        "scenario_set": set_name, "campaign_epoch": epoch, "speaker": speaker,
                        "partition": run.fire.partition, "journal_nonce": run.fire.nonce, "run_stem": run.stem,
                        "landed": True, "conversations": convs, "missing_conversations": {},
                        "contrasts": {"primary": rec}})
    primary = _sign_test([d for _, d in entering])
    groups: dict[str, list[Fraction]] = {}
    for sid, d in entering:
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
    wording = {"row_id": wording_row, "selectable_as_registered": selectable,
               "not_selectable_reasons": [] if selectable else ["synthetic: not selectable as registered"],
               "gate_same_direction": bool(gate["significant"]) and gate["direction"] == primary["direction"]}
    s103: dict[str, Any] = ({"status": "refused", "reason": "synthetic"} if section_10_3_refused else
                            {"statement": {"statement_id": statement, "vocabulary_also_lowered": also_lowered}})
    runs = [{"run_stem": r.stem, "run_id": r.manifest["run_id"], "path": str(r.path),
             "judgments_sha256": sha256_file(r.path / "judgments.jsonl"),
             "manifest_sha256": sha256_file(r.path / "manifest.json")} for r in campaign.runs]
    names = ("script", "judge_runner", "plan", "seed_file", "rubric", "outcome_registry")
    return {
        "analysis": ("SYNTHETIC artifact in the shape of scripts/petri_w2_register_contrast.py --final (script "
                     "version 1.1); not a result"),
        "final": final, "run_list": [r["path"] for r in runs], "bootstrap_seed": BOOTSTRAP_SEED,
        "identity": {"commit": commit, "uncommitted_changes": {n: [] for n in names}},
        "administratively_truncated": truncated, "truncation_reason": "synthetic" if truncated else None,
        "fires_not_landed": ["synthetic"] if truncated else [],
        "coverage": {"runs": runs, "rubric": {"digest": digest},
                     "plan": {"path": str(campaign.plan_path), "sha256": sha256_file(campaign.plan_path)}},
        "triples": triples,
        "section_10_2": {"primary_sign_test": primary, "scenario_gate": gate, "wording": wording},
        "section_10_3": s103, "section_10_4": {}, "section_10_5": {},
    }
