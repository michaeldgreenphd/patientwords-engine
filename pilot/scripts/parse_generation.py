"""Parse the raw generation responses. Never repairs a line: a line either validates or is logged as a format failure.

Input: a JSON file {"calls": [{"id", "arm", "cell", "attempts": [{"attempt", "raw", "null_return"}]}]}.
Writes generated/raw/<call>__attempt<N>.txt (verbatim), generated/<call>.jsonl (format-valid rows of the final
attempt), generated/all_rows.jsonl (the same rows in protocol order), generated/format_failures.jsonl, call_log.jsonl.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from common import (
    CONTROLS_PER_CALL,
    PILOT,
    ROWS_PER_CALL,
    cell_id,
    cells,
    control_is_faithful,
    lines_of,
    validate_line,
    write_jsonl,
)


def previous_outputs(gen_dir: Path) -> list[Path]:
    """Files an earlier parse left under generated/: the manifest hashes every one of them, so a rerun must not
    leave a stale attempt file beside the new ones (Codex review of PR #52)."""
    return sorted(gen_dir.glob("*.jsonl")) + sorted((gen_dir / "raw").glob("*.txt"))


def main(result_path: str, replace: bool = False) -> None:
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    calls_meta = {c["id"]: c for c in json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))["calls"]}
    cell_order = {cell_id(s, t): i for i, (s, t) in enumerate(cells())}
    gen_dir = PILOT / "generated"
    raw_dir = gen_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stale = previous_outputs(gen_dir)
    if stale and not replace:
        raise SystemExit(f"parse_generation: {len(stale)} file(s) from a previous parse exist under generated/ "
                         f"(first: {stale[0].relative_to(PILOT)}); pass --replace to delete them before parsing")
    for p in stale:
        p.unlink()
    if stale:
        print(f"parse_generation: --replace removed {len(stale)} file(s) from the previous parse")
    all_rows, failures, log = [], [], []
    by_id = {c["id"]: c for c in result["calls"] if c}
    for cid, meta in calls_meta.items():  # protocol order: cell order, A before B
        call = by_id.get(cid)
        attempts = call["attempts"] if call else []
        if not attempts:
            # a planned call with no response record is a final, failed call with zero lines: it stays in every
            # denominator that counts calls, and the run's call-level success rate shows it (Codex review of PR #52)
            log.append({"call_id": cid, "arm": meta["arm"], "cell": meta["cell"], "attempt": 0, "is_final": True,
                        "null_return": True, "n_lines": 0, "n_valid": 0, "n_invalid": 0, "n_control": 0,
                        "n_noncontrol": 0, "expected_lines": ROWS_PER_CALL, "expected_controls": CONTROLS_PER_CALL,
                        "reasons": {}, "status": "no_response_recorded"})
            write_jsonl(gen_dir / f"{cid}.jsonl", [])
            continue
        for a in attempts:
            raw = a.get("raw")
            (raw_dir / f"{cid}__attempt{a['attempt']}.txt").write_text(raw if raw is not None else "",
                                                                        encoding="utf-8")
        for idx, a in enumerate(attempts):
            is_final = idx == len(attempts) - 1
            lines = lines_of(a.get("raw"))
            reasons = Counter()
            rows = []
            for li, line in enumerate(lines):
                row, reason = validate_line(line)
                reasons[reason] += 1
                if row is not None:
                    rows.append({"id": f"{cid}__L{li + 1:02d}", "call_id": cid, "arm": meta["arm"],
                                 "specialty": meta["specialty"], "swap_type": meta["swap_type"],
                                 "cell": meta["cell"], "cell_index": cell_order[meta["cell"]], "line_index": li + 1,
                                 "attempt": a["attempt"], "clinical_term": row["clinical_term"],
                                 "patient_term": row["patient_term"], "template": row["template"],
                                 "control": row["control"],
                                 "control_faithful": control_is_faithful(row) if row["control"] == "negative" else None})
                elif is_final:
                    failures.append({"call_id": cid, "arm": meta["arm"], "cell": meta["cell"], "attempt": a["attempt"],
                                     "line_index": li + 1, "reason": reason, "line": line})
            n_ctrl = sum(1 for r in rows if r["control"] == "negative")
            log.append({"call_id": cid, "arm": meta["arm"], "cell": meta["cell"], "attempt": a["attempt"],
                        "is_final": is_final, "null_return": bool(a.get("null_return")), "n_lines": len(lines),
                        "n_valid": len(rows), "n_invalid": len(lines) - len(rows), "n_control": n_ctrl,
                        "n_noncontrol": len(rows) - n_ctrl, "expected_lines": ROWS_PER_CALL,
                        "expected_controls": CONTROLS_PER_CALL, "reasons": dict(reasons),
                        "status": "ok" if rows else "failed"})
            if is_final:
                write_jsonl(PILOT / "generated" / f"{cid}.jsonl", rows)
                all_rows.extend(rows)
    write_jsonl(PILOT / "generated" / "all_rows.jsonl", all_rows)
    write_jsonl(PILOT / "generated" / "format_failures.jsonl", failures)
    write_jsonl(PILOT / "call_log.jsonl", log)
    finals = [e for e in log if e.get("is_final")]
    print(f"calls={len(calls_meta)} attempts={len(log)} retried={sum(1 for e in log if not e.get('is_final'))} "
          f"final_lines={sum(e['n_lines'] for e in finals)} valid_rows={len(all_rows)} "
          f"failures={len(failures)} calls_with_zero_valid={sum(1 for e in finals if e['n_valid'] == 0)} "
          f"no_response={sum(1 for e in finals if e['status'] == 'no_response_recorded')}")


if __name__ == "__main__":
    main(sys.argv[1], replace="--replace" in sys.argv[2:])
