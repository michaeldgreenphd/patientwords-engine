"""Does patient health literacy change what the assistant does? (Layer 2, $0.)

Reads PatientAgentBench run directories **as data files** and reports, per
assistant model, how the assistant's behaviour differs between the low- and
high-health-literacy arms of the *same* clinical case. It never imports
PatientAgentBench: that project is CC-BY-NC-4.0, this repo is MIT, and reading
JSON output is not a derivative work.

Run ``scripts/validate_pab_contract.py`` first. This script assumes the design
already holds (paired arms, balanced cases) and will say so loudly if it does
not, but it is not the checker.

**Why this exists rather than jury scores.** The benchmark's rubric scores are
produced by an LLM jury, which costs money per conversation and is a separate
billing account. Everything reported here is computed from the transcript
itself, so it is $0, deterministic, and re-runnable: whether the assistant
called tools, whether it completed the workflow, how much it wrote, and whether
it used escalation or reassurance language. Jury scores answer "was the advice
good"; these measures answer "did the advice *change*", which is the question
the manipulation was designed to ask, and the one that does not need a jury to
be interpretable.

**The paired contrast is the unit.** Arms of a case differ in nothing but the
patient's rendered health literacy, so within a case the difference between arms
is attributable to the manipulation. Comparing arm means across cases would
instead be dominated by which cases happened to land in which arm. Every
headline number here is a mean of within-case differences, and ``n_pairs`` is
how many cases contributed -- small, in a pilot, and reported rather than
smoothed over.

**Draft vocabulary.** The escalation/reassurance term lists in
``data/pab_behavior_markers.json`` are marked "draft pending domain review".
Anything derived from them carries that label into the output, and must carry it
into any figure, exactly as the urgency tiers do.

  python scripts/pab_literacy_shift.py --run <run-dir> [--json] [--csv out.csv]

Exit codes: 0 report produced, 1 the run is not analysable, 2 unreadable.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKERS = REPO_ROOT / "data" / "pab_behavior_markers.json"
DEFAULT_CONTRACT = REPO_ROOT / "data" / "pab_transcript_contract.json"

#: Trait whose level the sweep varies. The arm grammar itself is declared in the
#: transcript contract; this is the key within it that this analysis reads.
TRAIT = "health_literacy"

#: The two ends of the sweep, low first so a positive difference always means
#: "more of this when the patient reads as high-literacy".
LOW, HIGH = "low", "high"


class AnalysisError(RuntimeError):
    """The run cannot be analysed as a paired literacy sweep."""


# ----------------------------------------------------------------- loading

def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise AnalysisError(f"unreadable: {path}: {err}") from err


def arm_level(label: str, spec: dict) -> str | None:
    """The health-literacy level an arm label encodes, or None.

    Mirrors the fork-side grammar declared in the contract rather than importing
    it, keeping this repo free of the fork's licence.
    """
    if not isinstance(label, str) or not label.startswith(spec["prefix"]):
        return None
    for chunk in label[len(spec["prefix"]):].split(spec["assignment_separator"]):
        key, sep, value = chunk.strip().partition(spec["key_value_separator"])
        if sep and key.strip() == TRAIT:
            return value.strip()
    return None


def pair_key(conversation: dict, contract: dict) -> str:
    """What identifies "the same clinical case" across arms.

    NOT ``case_id``. The sweep builder gives each arm its own ``scenario_id``
    (``<case>--arm0``, ``<case>--arm1``) so the transcripts stay distinguishable,
    and the runner copies that into ``case_id`` -- so arms of one case never
    share it and pairing on it yields zero pairs from a perfectly good run.

    The key is declared in the transcript contract (``pair_key_fields``), which
    already settled this: the scenario text is identical across arms of a case
    and differs between cases, while ``user_profile`` is deliberately excluded
    because ``initialize_sandbox()`` attaches a generated PCP to it before the
    transcript records it.
    """
    fields = contract.get("pair_key_fields") or ["scenario"]
    return "\x00".join(str(conversation.get(f, "")) for f in fields)


def assistant_model(exp_dir: Path) -> str:
    """The assistant model an experiment ran, from its own config.

    Falls back to the directory name when the config is absent or unreadable.
    A run cancelled mid-experiment leaves ``conversations.json`` (the runner
    checkpoints into it per conversation) without the ``experiment_config.json``
    that is written when the experiment finishes -- so insisting on the config
    would throw away the conversations that *did* complete.
    """
    path = exp_dir / "experiment_config.json"
    if path.is_file():
        try:
            config = load_json(path)
        except AnalysisError:
            config = None
        if config:
            agent = config.get("assistant_agent") or config.get("assistant") or {}
            model = agent.get("model")
            if isinstance(model, dict):
                model = model.get("model") or model.get("model_id")
            if model:
                return model
    return _model_from_run_config(exp_dir)


def _model_from_run_config(exp_dir: Path) -> str:
    """Recover the model from the run-level config when the experiment's own is
    missing.

    Experiment directories are named ``<assistant index>_<user index>``, and
    ``run_config.json`` is written when the run starts rather than when an
    experiment finishes -- so it survives exactly the cases that lose
    ``experiment_config.json``: a ceiling-stopped or cancelled experiment.

    The last resort is ``<run dir>/<experiment>``, not the bare experiment name.
    Two pooled runs both contain ``0_0``, ``1_0``, ... so a bare name would merge
    two different models into one row and silently average them together.
    """
    fallback = f"{exp_dir.parent.name}/{exp_dir.name}"
    try:
        run_config = load_json(exp_dir.parent / "run_config.json")
    except AnalysisError:
        return fallback
    assistants = (run_config.get("config") or run_config).get("assistant_agent")
    if not isinstance(assistants, list):
        return fallback
    try:
        index = int(exp_dir.name.split("_")[0])
        spec = assistants[index]
    except (ValueError, IndexError):
        return fallback
    model = spec.get("model") if isinstance(spec, dict) else None
    if isinstance(model, dict):
        model = model.get("model") or model.get("model_id")
    return model or fallback


# ----------------------------------------------------------------- measures

def _words(text: str) -> int:
    return len(text.split())


def compile_terms(terms: list[str]) -> re.Pattern:
    """One case-insensitive pattern for a term list.

    Word-boundary anchored so 'today' does not fire inside 'todays' and, more
    importantly, so short tokens like 'otc' and 'the er' do not match inside
    unrelated words -- 'er' appearing in 'better' would make every transcript
    look like an escalation.
    """
    if not terms:
        return re.compile(r"(?!)")
    parts = [r"\b" + re.escape(t).replace(r"\ ", r"\s+") + r"\b" for t in terms]
    return re.compile("|".join(parts), re.IGNORECASE)


def measure(conversation: dict, markers: dict, patterns: dict) -> dict:
    """Behavioural measures for one conversation, all from the transcript."""
    messages = conversation.get("conversation") or []
    assistant_text, tools_called = [], []
    for message in messages:
        kind = message.get("type") or message.get("role")
        if kind == "ai":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                assistant_text.append(content)
            for call in message.get("tool_calls") or []:
                name = call.get("name") if isinstance(call, dict) else None
                if name:
                    tools_called.append(name)
        elif kind == "tool":
            name = message.get("name")
            # A tool message with no matching call still evidences a call the
            # transcript did not serialise; counted so tool use is never
            # under-reported.
            if name and name not in tools_called:
                tools_called.append(name)

    text = "\n".join(assistant_text)
    workflow = markers["workflow_tools"]
    completion = set(workflow["completion_tools"])
    lookup = set(workflow["lookup_tools"])
    return {
        "n_tool_calls": len(tools_called),
        "n_distinct_tools": len(set(tools_called)),
        "used_any_tool": int(bool(tools_called)),
        "completed_workflow": int(any(t in completion for t in tools_called)),
        "used_lookup": int(any(t in lookup for t in tools_called)),
        "assistant_words": _words(text),
        "n_assistant_messages": len(assistant_text),
        "emergency_terms": len(patterns["emergency"].findall(text)),
        "urgent_terms": len(patterns["urgent"].findall(text)),
        "escalation_terms": (len(patterns["emergency"].findall(text))
                             + len(patterns["urgent"].findall(text))),
        "reassurance_terms": len(patterns["reassurance"].findall(text)),
        "self_care_terms": len(patterns["self_care"].findall(text)),
        "any_escalation": int(bool(patterns["emergency"].search(text)
                                   or patterns["urgent"].search(text))),
    }


MEASURES = [
    "completed_workflow", "used_any_tool", "n_tool_calls", "n_distinct_tools",
    "used_lookup", "assistant_words", "n_assistant_messages",
    "any_escalation", "escalation_terms", "emergency_terms", "urgent_terms",
    "reassurance_terms", "self_care_terms",
]

#: Measures whose meaning depends on the draft term lists. Flagged in the output
#: so a consumer cannot use them without inheriting the review status.
DRAFT_MEASURES = {"any_escalation", "escalation_terms", "emergency_terms",
                  "urgent_terms", "reassurance_terms", "self_care_terms"}


# ----------------------------------------------------------------- analysis

def collect(run_dir: Path, markers: dict, contract: dict) -> list[dict]:
    """One row per conversation, across every experiment in the run."""
    spec = contract["arm_spec"]
    patterns = {
        "emergency": compile_terms(markers["escalation_terms"]["emergency"]),
        "urgent": compile_terms(markers["escalation_terms"]["urgent"]),
        "reassurance": compile_terms(markers["reassurance_terms"]["terms"]),
        "self_care": compile_terms(markers["self_care_terms"]["terms"]),
    }
    experiment_dirs = [d for d in sorted(run_dir.iterdir())
                       if d.is_dir() and (d / "conversations.json").is_file()]
    if not experiment_dirs:
        raise AnalysisError(f"no experiment subdirectory in {run_dir}")

    rows = []
    for exp in experiment_dirs:
        model = assistant_model(exp)
        try:
            conversations = load_json(exp / "conversations.json") or []
        except AnalysisError as err:
            # One unreadable experiment must not cost the readable ones. A
            # cancelled run's last experiment is exactly this case.
            print(f"warning: skipping {exp.name}: {err}", file=sys.stderr)
            continue
        for conversation in conversations:
            if not isinstance(conversation, dict) or not conversation.get("conversation"):
                continue  # an unfilled slot, not a conversation
            level = arm_level(conversation.get("personality", ""), spec)
            rows.append({
                "experiment": exp.name,
                "model": model,
                "pair_key": pair_key(conversation, contract),
                "case_id": conversation.get("case_id"),
                "arm": conversation.get("personality"),
                "literacy": level,
                "n_turns": conversation.get("num_turns"),
                **measure(conversation, markers, patterns),
            })
    return rows


def paired_shift(rows: list[dict]) -> dict:
    """Per model, the mean within-case difference between the arms.

    Pairs on ``case_id`` within a model. A case present in only one arm is
    dropped and counted, rather than contributing a one-sided difference.
    """
    by_model: dict[str, dict] = {}
    for row in rows:
        if row["literacy"] not in (LOW, HIGH):
            continue
        slot = by_model.setdefault(row["model"], {})
        slot.setdefault(row["pair_key"], {})[row["literacy"]] = row

    report = {}
    for model, cases in sorted(by_model.items()):
        paired = {c: a for c, a in cases.items() if LOW in a and HIGH in a}
        # Report the human-readable case id, not the scenario text used as the key.
        unpaired = sorted(next(iter(a.values()))["case_id"]
                          for c, a in cases.items() if c not in paired)
        deltas: dict[str, list[float]] = {m: [] for m in MEASURES}
        arm_means: dict[str, dict[str, float]] = {LOW: {}, HIGH: {}}
        for arms in paired.values():
            for name in MEASURES:
                deltas[name].append(arms[HIGH][name] - arms[LOW][name])
        for level in (LOW, HIGH):
            for name in MEASURES:
                values = [a[level][name] for a in paired.values()]
                arm_means[level][name] = round(statistics.fmean(values), 4) if values else None

        summary = {}
        for name, values in deltas.items():
            if not values:
                summary[name] = None
                continue
            summary[name] = {
                "mean_high_minus_low": round(statistics.fmean(values), 4),
                "sd": round(statistics.stdev(values), 4) if len(values) > 1 else None,
                "n_nonzero": sum(1 for v in values if v),
                "draft_vocabulary": name in DRAFT_MEASURES,
            }
        report[model] = {
            "n_pairs": len(paired),
            "n_unpaired_cases": len(unpaired),
            "unpaired_case_ids": unpaired,
            "arm_means": arm_means,
            "shift": summary,
        }
    return report


# ----------------------------------------------------------------- output

def render(report: dict, rows: list[dict], markers: dict) -> str:
    lines = []
    total = len(rows)
    models = len(report)
    lines.append(f"{total} conversations across {models} assistant models")
    lines.append(f"vocabulary status: {markers['status']}")
    lines.append("")
    lines.append("Mean within-case difference, high-literacy arm minus low-literacy arm.")
    lines.append("Positive = more of it when the patient reads as health-literate.")
    lines.append("")
    head = (f"{'model':<44} {'n':>3} {'workflow':>9} {'tools':>7} "
            f"{'words':>8} {'escal*':>7} {'reassur*':>9}")
    lines.append(head)
    lines.append("-" * len(head))
    for model, block in report.items():
        shift = block["shift"]

        def cell(name, width, places=2):
            entry = shift.get(name)
            if not entry:
                return f"{'--':>{width}}"
            return f"{entry['mean_high_minus_low']:>{width}.{places}f}"

        lines.append(
            f"{model:<44} {block['n_pairs']:>3} "
            f"{cell('completed_workflow', 9)} {cell('n_tool_calls', 7)} "
            f"{cell('assistant_words', 8, 1)} {cell('escalation_terms', 7)} "
            f"{cell('reassurance_terms', 9)}"
        )
        if block["n_unpaired_cases"]:
            lines.append(f"{'':<44}     ({block['n_unpaired_cases']} unpaired case(s) dropped)")
    lines.append("")
    lines.append("* escal/reassur come from the DRAFT term lists in "
                 "data/pab_behavior_markers.json.")
    lines.append("  They are not clinician-reviewed; do not publish a number "
                 "built on them without that label.")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, action="append",
                        help="run directory (repeatable)")
    parser.add_argument("--markers", default=str(DEFAULT_MARKERS))
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--csv", help="write the per-conversation rows here")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        markers = load_json(Path(args.markers))
        contract = load_json(Path(args.contract))
        rows = []
        for run in args.run:
            path = Path(run)
            if not path.is_dir():
                raise AnalysisError(f"not a directory: {run}")
            rows.extend(collect(path, markers, contract))
    except AnalysisError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    if not rows:
        print("error: no conversations found", file=sys.stderr)
        return 1

    report = paired_shift(rows)
    if not report:
        print("error: no case appears in both literacy arms; nothing to pair",
              file=sys.stderr)
        return 1

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {out} ({len(rows)} rows)", file=sys.stderr)

    if args.as_json:
        print(json.dumps({
            "n_conversations": len(rows),
            "vocabulary_status": markers["status"],
            "vocabulary_status_note": markers["status_note"],
            "draft_measures": sorted(DRAFT_MEASURES),
            "by_model": report,
        }, indent=2))
    else:
        print(render(report, rows, markers))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
