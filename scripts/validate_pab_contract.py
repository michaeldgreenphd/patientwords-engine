"""Structural validator for PatientAgentBench run directories (integration Layer 2).

The benchmark's runner writes ``<run>/<experiment>/conversations.json`` and
``evaluations.json``. This script reads them **as data files** and checks that a
run is fit to analyse before any analysis touches it. It never imports
PatientAgentBench: that project is CC-BY-NC-4.0, this repo is MIT, and reading
JSON output is not a derivative work. The fork-side adapter that writes the arm
labels lives in ``PatientAgentBench-patientwords/src/patientwords_pab/``.

Two kinds of check, and the second is the reason this exists:

* **Shape** -- required keys and types on every record, join integrity between
  conversations and evaluations, rubric scores inside the declared range. Same
  job ``validate_frontend_contract.py`` does for the site payload.
* **Design integrity** -- a trait sweep is only interpretable if the arms differ
  in exactly one trait and every clinical case appears in every arm. Both are
  properties of the transcript, so both are checkable here, mechanically, before
  a single number is reported. An unbalanced or multi-factor run reads as a
  finding just as easily as a clean one; nothing downstream would notice.

Everything the checker requires is declared in ``data/pab_transcript_contract.json``
-- rubric names, score bounds, the arm-label grammar. No medical vocabulary
lives in this file.

  python scripts/validate_pab_contract.py --run <run-dir> [--strict] [--json]

Exit codes: 0 contract holds, 1 violations, 2 run directory missing/unreadable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_CONTRACT = Path(__file__).resolve().parents[1] / "data" / "pab_transcript_contract.json"

NUM = (int, float)
TYPES = {"str": str, "list": list, "int": int, "dict": dict, "num": NUM}

# Stand-in for "this arm did not name the trait, so it takes the base value".
# The base value itself is never resolved for preset bases -- that would mean
# copying the upstream preset table into this repo. Arms are only compared when
# they share a base, so an unresolved constant compares equal to itself.
_FROM_BASE = "\x00from-base"


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
        rep.err(artifact, f"{path}.{key}", f"wrong type {type(value).__name__}")
        return None
    return value


def load_json(path: Path, artifact: str, rep: Report, required: bool = True):
    if not path.is_file():
        if required:
            rep.err(artifact, "-", "artifact missing")
        else:
            rep.warn(artifact, "-", "artifact missing (check skipped)")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        rep.err(artifact, "-", f"unreadable: {err}")
        return None


# ------------------------------------------------------------------- arm labels

def parse_arm(label: str, spec: dict):
    """Split an arm label into ``(base, overrides)``, or ``(None, None)``.

    Mirrors the fork-side grammar declared in the contract file. A label without
    the prefix is a preset name, which carries no trait decomposition: it comes
    back as ``(label, None)`` so callers can tell "preset arm" from "malformed".
    """
    if not isinstance(label, str) or not label.strip():
        return None, None
    text = label.strip()
    if not text.startswith(spec["prefix"]):
        return text, None
    base = spec["neutral_base"]
    overrides: dict[str, str] = {}
    for chunk in text[len(spec["prefix"]):].split(spec["assignment_separator"]):
        item = chunk.strip()
        if not item:
            continue
        if spec["key_value_separator"] not in item:
            return None, None
        key, _, value = item.partition(spec["key_value_separator"])
        key, value = key.strip(), value.strip()
        if not key or not value:
            return None, None
        if key == spec["base_key"]:
            base = value
        else:
            overrides[key] = value
    return base, overrides


def varying_traits(arms: list[tuple[str, dict]], spec: dict) -> list[str]:
    """Traits whose level differs across arms that share a base.

    An arm that does not name a trait takes the base's level for it. For the
    neutral base that level is declared in the contract; for a preset base it
    stays an unresolved constant, which is enough because every arm compared
    here shares the base.
    """
    base_default = {spec["neutral_base"]: spec["neutral_level"]}
    named: set[str] = set()
    for _, overrides in arms:
        named.update(overrides)
    varying = []
    for trait in sorted(named):
        levels = {
            overrides.get(trait, base_default.get(base, _FROM_BASE))
            for base, overrides in arms
        }
        if len(levels) > 1:
            varying.append(trait)
    return varying


def pair_key(record: dict, fields: list[str]) -> str:
    """Identity of the clinical case behind a conversation.

    Arms are separate benchmark entries with separate ids, so the join back to
    "same case, different wording" runs on the case content the sweep holds
    fixed. Hashed rather than stored so no case text lands in a report.
    """
    joined = "\x00".join(str(record.get(f, "")) for f in fields)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------------- experiments

def check_conversations(rep: Report, artifact: str, data, contract: dict):
    """Validate conversations.json.

    Returns ``(slots, usable)``. ``slots`` is the file's own list, unfiltered, so
    the slot-for-slot join against evaluations.json stays aligned on a partially
    complete run; ``usable`` drops the null and errored records and is what the
    design checks analyse.
    """
    if not isinstance(data, list):
        rep.err(artifact, "$", f"expected a list, got {type(data).__name__}")
        return [], []
    if not data:
        rep.err(artifact, "$", "empty (nothing to analyse)")
        return [], []

    required = contract["required_conversation_keys"]
    message_types = set(contract["message_types"])
    usable: list[dict] = []
    seen_ids: set[str] = set()
    pending = 0

    for i, record in enumerate(data):
        p = f"$[{i}]"
        if record is None:
            pending += 1
            continue
        if not isinstance(record, dict):
            rep.err(artifact, p, f"expected an object, got {type(record).__name__}")
            continue
        for key, kind in required.items():
            need(rep, artifact, record, key, TYPES[kind], p)
        case_id = record.get("case_id")
        if isinstance(case_id, str) and case_id:
            # Downstream joins are keyed on case_id; a duplicate silently
            # shadows one measurement with another.
            if case_id in seen_ids:
                rep.err(artifact, p, f"duplicate case_id {case_id!r}")
            seen_ids.add(case_id)
        if record.get("error") is not None:
            rep.warn(artifact, p, f"conversation failed ({record['error']}); excluded")
            continue

        messages = record.get("conversation")
        if isinstance(messages, list):
            if not messages:
                rep.err(artifact, f"{p}.conversation", "no messages")
            for j, msg in enumerate(messages):
                mp = f"{p}.conversation[{j}]"
                if not isinstance(msg, dict):
                    rep.err(artifact, mp, "message is not an object")
                    continue
                mtype = msg.get("type")
                if mtype not in message_types:
                    rep.err(artifact, f"{mp}.type",
                            f"unknown message type {mtype!r} "
                            f"(known: {', '.join(sorted(message_types))})")
                if "content" not in msg:
                    rep.err(artifact, f"{mp}.content", "missing")
            if not any(isinstance(m, dict) and m.get("type") == "human" for m in messages):
                rep.warn(artifact, f"{p}.conversation",
                         "no patient turn (degenerate transcript)")
        turns = record.get("num_turns")
        if _is(turns, int) and turns < 1:
            rep.warn(artifact, f"{p}.num_turns", "zero turns (degenerate transcript)")
        usable.append(record)

    if pending:
        rep.warn(artifact, "$", f"{pending}/{len(data)} slots still null (run incomplete)")
    return data, usable


def check_evaluations(rep: Report, artifact: str, data, slots, contract: dict) -> int:
    """Validate evaluations.json against the conversation slots it scores.

    ``slots`` is conversations.json unfiltered: the runner pre-allocates both
    files to the same length and fills them in place, so the join is positional
    and a resumable run legitimately carries empty slots in both.

    Returns the count of scored records.
    """
    if not isinstance(data, list):
        rep.err(artifact, "$", f"expected a list, got {type(data).__name__}")
        return 0
    if len(data) != len(slots):
        # The runner writes both files slot-for-slot; a length mismatch means
        # the positional join every consumer makes is already wrong.
        rep.err(artifact, "$",
                f"{len(data)} entries against {len(slots)} conversation slots "
                "(slot-for-slot join broken)")
    lo, hi = contract["score_min"], contract["score_max"]
    required_rubrics = set(contract["required_rubrics"])
    expected_rubrics = set(contract["expected_rubrics"])
    scored = 0
    evaluator_counts: set[int] = set()

    for i, entry in enumerate(data):
        p = f"$[{i}]"
        if not isinstance(entry, dict):
            rep.err(artifact, p, f"expected an object, got {type(entry).__name__}")
            continue
        if not entry:
            rep.warn(artifact, p, "empty slot (not yet evaluated)")
            continue
        if i < len(slots) and isinstance(slots[i], dict):
            expected_id = slots[i].get("case_id")
            if entry.get("case_id") != expected_id:
                rep.err(artifact, f"{p}.case_id",
                        f"{entry.get('case_id')!r} does not match conversations[{i}] "
                        f"({expected_id!r})")
        if "error" in entry:
            rep.warn(artifact, p, f"evaluation failed ({entry['error']}); excluded")
            continue

        evaluation = need(rep, artifact, entry, "evaluation", dict, p)
        if evaluation is None:
            continue
        if "error" in evaluation:
            rep.warn(artifact, f"{p}.evaluation", f"{evaluation['error']}; excluded")
            continue
        scores = need(rep, artifact, evaluation, "rubric_scores", dict, f"{p}.evaluation")
        need(rep, artifact, evaluation, "aggregate_score", NUM, f"{p}.evaluation")
        if scores is None:
            continue
        for rubric, value in scores.items():
            rp = f"{p}.evaluation.rubric_scores.{rubric}"
            if not _is(value, NUM):
                rep.err(artifact, rp, f"non-numeric score {value!r}")
            elif not lo <= value <= hi:
                rep.err(artifact, rp, f"score {value} outside the {lo}-{hi} scale")
        missing_required = sorted(required_rubrics - set(scores))
        if missing_required:
            rep.err(artifact, f"{p}.evaluation.rubric_scores",
                    f"missing required rubric(s): {', '.join(missing_required)}")
        missing_expected = sorted(expected_rubrics - set(scores) - required_rubrics)
        if missing_expected:
            rep.warn(artifact, f"{p}.evaluation.rubric_scores",
                     f"missing rubric(s): {', '.join(missing_expected)}")
        evaluator_counts.add(sum(1 for k in entry if k.startswith("evaluation_")))
        scored += 1

    if evaluator_counts and max(evaluator_counts) < 2:
        rep.warn(artifact, "$",
                 "scored by a single evaluator; the benchmark's reported "
                 "jury/clinician agreement assumes a panel")
    if len(evaluator_counts) > 1:
        rep.warn(artifact, "$",
                 f"evaluator count varies across records ({sorted(evaluator_counts)})")
    return scored


def check_design(rep: Report, artifact: str, conversations: list[dict],
                 contract: dict, cases: dict | None) -> dict:
    """The identification checks: one factor varying, and a balanced pairing."""
    spec = contract["arm_spec"]
    fields = contract["pair_key_fields"]
    summary: dict = {"arms": {}, "n_pairs": 0, "varying_traits": [], "identified": None}

    arms: dict[str, list[dict]] = {}
    parsed: dict[str, tuple[str, dict | None]] = {}
    for i, record in enumerate(conversations):
        label = record.get("personality")
        base, overrides = parse_arm(label, spec)
        if base is None:
            rep.err(artifact, f"$[{i}].personality",
                    f"unparseable arm label {label!r} (expected a preset name or a "
                    f"{spec['prefix']!r} spec)")
            continue
        arms.setdefault(label, []).append(record)
        parsed[label] = (base, overrides)

    summary["arms"] = {label: len(records) for label, records in sorted(arms.items())}
    if len(arms) < 2:
        rep.warn(artifact, "$", "fewer than two arms; no contrast to identify")
        return summary

    free = {label: parsed[label] for label in arms if parsed[label][1] is not None}
    if len(free) < 2:
        rep.warn(artifact, "$",
                 "fewer than two free-trait arms; single-factor identification "
                 "not checkable from preset labels alone")
    else:
        bases = {base for base, _ in free.values()}
        if len(bases) > 1:
            rep.err(artifact, "$",
                    f"free-trait arms use different bases ({', '.join(sorted(bases))}); "
                    "traits they do not name are not held fixed across arms")
        else:
            varying = varying_traits(list(free.values()), spec)
            summary["varying_traits"] = varying
            summary["identified"] = len(varying) == 1
            if not varying:
                rep.err(artifact, "$",
                        "free-trait arms have identical traits; the manipulation is empty")
            elif len(varying) > 1:
                rep.err(artifact, "$",
                        f"{len(varying)} traits vary across arms ({', '.join(varying)}); "
                        "a single-factor contrast is not identified")

    # Balance: every case must be present in every arm, or the paired analysis
    # silently compares different case mixes.
    groups: dict[str, dict[str, int]] = {}
    for record in conversations:
        label = record.get("personality")
        if label not in arms:
            continue
        group = groups.setdefault(pair_key(record, fields), {})
        group[label] = group.get(label, 0) + 1
    summary["n_pairs"] = len(groups)

    incomplete = 0
    duplicated = 0
    for key, counts in sorted(groups.items()):
        missing = sorted(set(arms) - set(counts))
        if missing:
            incomplete += 1
            rep.err(artifact, f"$.pairs[{key}]",
                    f"case absent from arm(s): {', '.join(missing)}")
        extra = sorted(label for label, n in counts.items() if n > 1)
        if extra:
            duplicated += 1
            rep.err(artifact, f"$.pairs[{key}]",
                    f"case appears more than once in arm(s): {', '.join(extra)}")
    summary["complete_pairs"] = len(groups) - incomplete - duplicated

    # Stimulus-level confound check: paired entries must differ only in wording.
    if cases is None:
        rep.warn(artifact, "$",
                 "benchmark_cases.json absent; stimulus attributes not checked "
                 "for confounds across arms")
        return summary
    by_pair: dict[str, list[dict]] = {}
    for record in conversations:
        by_pair.setdefault(pair_key(record, fields), []).append(record)
    for key, records in sorted(by_pair.items()):
        attrs = [cases.get(r.get("case_id"), {}) for r in records]
        attrs = [a for a in attrs if a]
        if len(attrs) < 2:
            continue
        for field in contract["invariant_case_fields"]:
            values = {json.dumps(a.get(field), sort_keys=True) for a in attrs}
            if len(values) > 1:
                rep.err(artifact, f"$.pairs[{key}].{field}",
                        "differs across arms; the arms are not the same clinical case")
    return summary


def check_run(rep: Report, run_dir: Path, contract: dict) -> dict:
    """Walk every experiment subdirectory of a run."""
    summary: dict = {"run_dir": str(run_dir), "experiments": {}}

    cases = None
    cases_path = run_dir / "benchmark_cases.json"
    if cases_path.is_file():
        raw = load_json(cases_path, "benchmark_cases.json", rep, required=False)
        if isinstance(raw, list):
            cases = {}
            for entry in raw:
                if isinstance(entry, dict):
                    key = entry.get("scenario_id") or entry.get("query_id")
                    if key:
                        cases[key] = entry
        elif raw is not None:
            rep.warn("benchmark_cases.json", "$", "expected a list; ignored")

    experiment_dirs = [
        d for d in sorted(run_dir.iterdir())
        if d.is_dir() and (d / "conversations.json").is_file()
    ]
    if not experiment_dirs:
        rep.err("run", "-", "no experiment subdirectory with conversations.json")
        return summary

    case_sets: dict[str, set] = {}
    for exp in experiment_dirs:
        name = exp.name
        conv_artifact = f"{name}/conversations.json"
        eval_artifact = f"{name}/evaluations.json"
        slots, conversations = check_conversations(
            rep, conv_artifact,
            load_json(exp / "conversations.json", conv_artifact, rep), contract,
        )
        scored = check_evaluations(
            rep, eval_artifact,
            load_json(exp / "evaluations.json", eval_artifact, rep),
            slots, contract,
        )
        design = check_design(rep, conv_artifact, conversations, contract, cases)
        summary["experiments"][name] = {
            "n_conversations": len(conversations), "n_scored": scored, **design,
        }
        case_sets[name] = {r.get("case_id") for r in conversations}

    if len(case_sets) > 1:
        reference_name, reference = next(iter(case_sets.items()))
        for name, ids in case_sets.items():
            if ids != reference:
                rep.warn(f"{name}/conversations.json", "$",
                         f"case set differs from experiment {reference_name!r}; "
                         "cross-model comparisons are not on the same cases")
                break
    return summary


def validate(run_dir: Path, contract_path: Path, strict: bool = False):
    rep = Report()
    contract = load_json(contract_path, contract_path.name, rep)
    if contract is None:
        return rep, {}
    summary = check_run(rep, run_dir, contract)
    if strict:
        rep.errors.extend(rep.warnings)
        rep.warnings = []
    return rep, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="PatientAgentBench run directory")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT),
                        help="contract declaration (default: data/pab_transcript_contract.json)")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors (pre-analysis gate)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit the summary and findings as JSON")
    parser.add_argument("--quiet", action="store_true", help="print only the summary line")
    args = parser.parse_args(argv)

    run_dir = Path(args.run)
    if not run_dir.is_dir():
        print(f"error: {run_dir} is not a directory", file=sys.stderr)
        return 2

    rep, summary = validate(run_dir, Path(args.contract), strict=args.strict)

    if args.as_json:
        print(json.dumps({"summary": summary, "errors": rep.errors,
                          "warnings": rep.warnings}, indent=2))
        return 1 if rep.errors else 0

    if not args.quiet:
        for w in rep.warnings:
            print("warn:", w)
        for e in rep.errors:
            print("FAIL:", e)
        for name, exp in summary.get("experiments", {}).items():
            arms = ", ".join(f"{label} x{n}" for label, n in exp["arms"].items())
            identified = {True: "identified", False: "NOT identified", None: "n/a"}[
                exp.get("identified")
            ]
            print(f"{name}: {exp['n_conversations']} conversations, {exp['n_scored']} scored, "
                  f"{exp['n_pairs']} case pairs, single-factor {identified}"
                  f"{' on ' + ', '.join(exp['varying_traits']) if exp['varying_traits'] else ''}"
                  f"\n  arms: {arms or 'none'}")
    print(f"pab contract check: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
