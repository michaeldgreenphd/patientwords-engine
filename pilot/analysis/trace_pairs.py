"""Turn a finished version-2 pilot run into a pairs file the circuit-trace lane can read.

A pilot row holds a clinical term, a patient term, a template with one blank and (from harness version 2) the word
expected next after the clinical sentence. The circuit-trace lane's 2panel mode reads a JSON array of pairs with
top_prompt (clinical), bottom_prompt (patient) and target_clinical_token (" " + the expected word; the study's
targets all carry the leading space). This script builds that array for the generated rows the checker judged
equivalent, in the run's own row order, with a provenance block per pair so every trace result joins back to its
row by the 1-based index the lane assigns.

It is a consumer of a finished run, like the review page: it reads the run directory and never writes inside the
run's sealed files. The output goes to <run>/trace/<run_id>_trace_pairs.json by default (default_out), with a
sidecar recording the selection rule, the counts (selected, not selected and why, refused and why) and the sha256 of
every input. The file is named for its run, in the run's trace/ directory, because both pilot lanes (circuit-trace's
pilot/traces/, logits-eval's pilot/logits/) refuse a pilot pairs file that is not at
pilot/runs/<run_id>/trace/<run_id>_<name>.json or whose name holds "__" (docs/triggers.md); an --out elsewhere writes a
file they refuse. They name the output folder <root>/<run_id>/<the file's stem>[__<model>] (2026-10-05), so the name
says which run a folder holds, and two files or two models of one run never share one.
Before 2026-10-04 every run's default was trace/trace_pairs.json, and the lanes named the folder by the stem alone,
so two runs' traces would have shared one folder. Run 2's committed trace/trace_pairs.json keeps its name; to trace
it again, re-run this script on run 2 with --review-sample, whose default writes a byte-identical
trace/pilot_v2_20261002_trace_pairs.json beside it (checked 2026-10-05), or copy the file to that path.

A run that is not version 2, not finalized or without probe endings, a generated row that lacks a key a pair is built
from (ROW_KEYS), or a selected row that cannot be traced (a term that is not a non-empty string, not exactly one
blank, a next word the parser's next-word check refuses) is refused rather than skipped: a pairs file that silently
lost rows would trace a different sample than the one described.

Pilot traces are pipeline checks, never measurements (AGENTS.md, pilot exception): the lane writes them under
pilot/traces/<run_id>/, which no collector reads. Run the holdout seal check over the output before it is pushed
anywhere.

The default selection is every generated row the checker judged equivalent. --review-sample instead selects exactly
the rows of the run's blind review sample (review_map.json), whatever the checker said, in review-id order, so trace
index 1 is r001: those are the pairs the owner labels, which joins the owner's quality labels to the trace measures.

Usage: trace_pairs.py --run-dir <pilot run directory> [--out <file>] [--include-controls | --review-sample]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

BLANK = "___"
# the keys every generated row must carry for a pair to be built from it: the version-2 row contract
# (common.REQUIRED_FIELDS_V2) and the row id parse_generation.py assigns. Every row of all_rows.jsonl is checked
# before any is selected, and a row without one is refused by its line, id and key (Copilot review of PR #74).
ROW_KEYS = ("id", "clinical_term", "patient_term", "template", "next_word", "control")
# the version-2 next_word check the parser applies to every row: pilot/scripts/common.NEXT_WORD_RE and next_word_ok,
# copied rather than imported, as surface_key is, and held equal by a test (Copilot review of PR #74), so a trace
# refuses exactly the next words the parser refused. It is the check behind run 2's PROTOCOL.md section 4, "a
# non-empty lowercase word of letters (one internal hyphen or apostrophe allowed)", and is broader than that wording
# in the two ways next_word_ok's docstring names.
NEXT_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)?")


class TraceInputError(ValueError):
    """The run cannot produce a faithful pairs file; the message says why."""


def surface_key(s: str) -> str:
    """Casing, punctuation and spacing removed. Mirrors pilot/scripts/common.surface_key (a test holds them equal);
    copied rather than imported because importing common reads PILOT_DIR's design at import time."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def next_word_ok(value: object) -> bool:
    """common.next_word_ok: a string that NEXT_WORD_RE matches in full and that lower() leaves unchanged. Broader
    than the protocol's wording in two ways: the pattern, \\w without the decimal digits and the underscore, also
    admits numerals that are not decimal digits (Unicode No and Nl, such as superscript digits and fractions), and the
    lowercase test admits an uppercase letter that has no lowercase form."""
    return isinstance(value, str) and NEXT_WORD_RE.fullmatch(value) is not None and value == value.lower()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path, required: tuple[str, ...] = ()) -> list[dict]:
    """The JSON objects of a JSONL file, blank lines skipped. A line that is not a JSON object, or (with `required`)
    an object that lacks one of those keys, is refused naming the line, the row id when it has one, and the keys."""
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise TraceInputError(f"{path.name} line {n} is not JSON: {e}") from e
        if not isinstance(obj, dict):
            raise TraceInputError(f"{path.name} line {n} is not a JSON object")
        missing = [k for k in required if k not in obj]
        if missing:
            row = f"row {obj['id']}" if "id" in obj else "a row without an id"
            raise TraceInputError(f"{path.name} line {n} ({row}) lacks the required key(s) {', '.join(missing)}")
        rows.append(obj)
    return rows


def build(run_dir: Path, include_controls: bool = False, review_sample: bool = False) -> tuple[list[dict], dict]:
    """The pairs and their sidecar for one finished version-2 run."""
    if include_controls and review_sample:
        raise TraceInputError("--include-controls and --review-sample select different rows; pass one")
    design = json.loads((run_dir / "design.json").read_text(encoding="utf-8"))
    if design.get("harness_version") != 2:
        raise TraceInputError(f"design.json harness_version is {design.get('harness_version')!r}; only version-2 "
                              "runs carry the expected next word a trace needs")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("finalized_utc"):
        raise TraceInputError("manifest.json is not finalized; trace a run only after write_manifest.py finalize")
    endings = design.get("probe_endings")
    if not isinstance(endings, list) or not endings or not all(isinstance(w, str) and w for w in endings):
        raise TraceInputError(f"design.json probe_endings is {endings!r}; a version-2 design lists its probe endings, "
                              "which the probe-point flag reads")
    # lowercased once, as common.probe_endings_set builds them, not per row (Copilot review of PR #74)
    probe_endings = frozenset(w.lower() for w in endings)
    rows_path, checked_path = run_dir / "generated" / "all_rows.jsonl", run_dir / "checked.jsonl"
    rows = _jsonl(rows_path, required=ROW_KEYS)
    verdicts: dict[str, dict] = {}
    for c in _jsonl(checked_path):
        if c.get("source") != "generated":
            continue
        rid = c.get("row_id")
        if rid in verdicts:
            raise TraceInputError(f"checked.jsonl has two verdicts for row {rid}")
        verdicts[rid] = c
    run_id = run_dir.name
    review_ids: dict[str, str] = {}
    if review_sample:
        mapping = json.loads((run_dir / "review_map.json").read_text(encoding="utf-8")).get("map")
        if not isinstance(mapping, dict) or not mapping:
            raise TraceInputError("review_map.json has no map of review ids to row ids")
        review_ids = {row_id: rid for rid, row_id in mapping.items()}
        by_id = {r["id"]: r for r in rows}
        missing = sorted(set(review_ids) - set(by_id))
        if missing:
            raise TraceInputError(f"review_map.json names rows absent from all_rows.jsonl: {missing[:5]}")
        rows = [by_id[row_id] for row_id in sorted(review_ids, key=lambda k: review_ids[k])]
    pairs: list[dict] = []
    not_selected: Counter = Counter()
    for r in rows:
        control = r.get("control")
        if review_sample:
            if control != "none":
                raise TraceInputError(f"review sample row {r['id']} is a control row")
            c = verdicts.get(r["id"])
            if c is None:
                raise TraceInputError(f"generated row {r['id']} has no checker verdict in checked.jsonl")
        elif control == "negative" and not include_controls:
            not_selected["negative control (not requested)"] += 1
            continue
        elif control == "none":
            c = verdicts.get(r["id"])
            if c is None:
                raise TraceInputError(f"generated row {r['id']} has no checker verdict in checked.jsonl")
            if c.get("verdict") != "yes":
                not_selected[f"checker equivalent {c.get('verdict')!r}"] += 1
                continue
        elif control != "negative":
            raise TraceInputError(f"row {r.get('id')} has control {control!r}")
        else:
            c = {}
        template, word = r["template"], r["next_word"]
        for k in ("clinical_term", "patient_term"):
            if not isinstance(r[k], str) or not r[k].strip():
                raise TraceInputError(f"row {r['id']}: {k} is not a non-empty string")
        if not isinstance(template, str) or template.count(BLANK) != 1:
            raise TraceInputError(f"row {r['id']}: template does not hold exactly one {BLANK}")
        if not next_word_ok(word):
            raise TraceInputError(f"row {r['id']}: next_word {word!r} breaks the version-2 next_word rule: one "
                                  "lowercase word of letters, at most one internal hyphen or apostrophe")
        last = template.rstrip().split()[-1].lower() if template.strip() else ""
        pairs.append({
            "top_prompt": template.replace(BLANK, r["clinical_term"]),
            "bottom_prompt": template.replace(BLANK, r["patient_term"]),
            "target_clinical_token": " " + word,
            "pilot": {
                "run": run_id, "row_id": r["id"], "review_id": review_ids.get(r["id"]), "call_id": r.get("call_id"),
                "arm": r.get("arm"),
                "cell": r.get("cell"), "control": control,
                "concept_key": f"{r.get('call_id')}|{surface_key(r['clinical_term'])}|{template}",
                "probe_point": last in probe_endings,
                "checker": {k: c.get(k) for k in ("verdict", "relation", "sentence_natural", "patient_realism")},
                "prompt_sha256": r.get("prompt_sha256"),
            },
        })
    if not pairs:
        raise TraceInputError("no row was selected; nothing to trace")
    meta = {
        "run": run_id,
        "harness_version": 2,
        "selection": (("exactly the blind review sample (review_map.json), whatever the checker said, in review-id "
                       "order" if review_sample else "generated rows the checker judged equivalent (verdict yes)"
                       + (", plus every negative control" if include_controls else "") + ", in the run's row order")
                      + "; target_clinical_token is a space plus the row's next_word"),
        "counts": {"selected": len(pairs), "not_selected": dict(sorted(not_selected.items())),
                   "at_probe_point": sum(p["pilot"]["probe_point"] for p in pairs)},
        "inputs_sha256": {"generated/all_rows.jsonl": _sha256(rows_path), "checked.jsonl": _sha256(checked_path),
                          "manifest.json": _sha256(run_dir / "manifest.json"),
                          "design.json": _sha256(run_dir / "design.json")},
        "use": "pipeline check only, never a measurement; trace under output_root pilot/traces; seal-check before push",
    }
    return pairs, meta


def default_out(run_dir: Path) -> Path:
    """<run-dir>/trace/<run_id>_trace_pairs.json, run_id being the run directory's name (as build() records it): the
    path both pilot lanes accept for a pilot-root fire, pilot/runs/<run_id>/trace/<run_id>_<name>.json (a run id
    holding "__" gives a name they refuse)."""
    return run_dir / "trace" / f"{run_dir.name}_trace_pairs.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", help="default: <run-dir>/trace/<run_id>_trace_pairs.json; a pilot-root fire refuses a "
                                  "pairs file whose name does not start with <run_id>_")
    ap.add_argument("--include-controls", action="store_true")
    ap.add_argument("--review-sample", action="store_true", help="trace exactly the blind review sample")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir)
    out = Path(a.out) if a.out else default_out(run_dir)
    try:
        pairs, meta = build(run_dir, a.include_controls, a.review_sample)
    except (TraceInputError, FileNotFoundError, KeyError) as e:
        print(f"trace_pairs: refused: {e}", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(pairs, ensure_ascii=False, indent=1) + "\n"
    out.write_text(text, encoding="utf-8")
    meta["output"] = {"file": out.name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"trace_pairs: {len(pairs)} pairs -> {out}; {meta['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
