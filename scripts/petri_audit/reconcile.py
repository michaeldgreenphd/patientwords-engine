"""Journal-to-ledger reconciliation for the petri-audit lane.

`scripts/fire_trigger.py` journals every fire (`ops/trigger_journal.jsonl`)
and, for a paid fire, the worst-case commitment the daily ceiling absorbed
(`max_spend`). The workflow passes the fire's `_nonce` into the run
(`cli run --journal-nonce`), the adapter records it in the manifest's
`spend.journal_nonce`, and both cost-sidecar writers (`adapt --report` and the
workflow's fallback `spend-report`) copy it into the sidecar the daily Routine
folds into the ledger. This module joins the two records on that nonce and
names every gap: a paid fire with no landed sidecar (spent, unbooked), a
sidecar no fire accounts for, a landed cost above the fire's commitment, and
a sidecar the ledger has not folded yet. It reads and reports; it changes
nothing (`fire_trigger.py` and `ledger_update.py` stay the only writers).

A missing or malformed value is reported by name, never defaulted (AGENTS.md,
*No silent failures in extraction or parsing*).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .framework import load_json

LANE = "petri-audit"
JUDGE_SUFFIX = ".judge.report.json"
NUMBER = (int, float)


def read_journal(path: Path | str) -> list[dict[str, Any]]:
    """Every journal entry, in file order; a line that does not parse is a named error."""
    entries: list[dict[str, Any]] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{Path(path).name} line {i} does not parse: {exc}") from None
        if not isinstance(entry, dict):
            raise ValueError(f"{Path(path).name} line {i} is not an object")
        entries.append(entry)
    return entries


def _sidecars(runs_dir: Path) -> tuple[list[tuple[Path, Any]], list[tuple[Path, Any]]]:
    """(target sidecars, judge sidecars) directly inside each run directory; an unreadable file is kept, marked."""
    targets: list[tuple[Path, Any]] = []
    judges: list[tuple[Path, Any]] = []
    if not runs_dir.is_dir():
        return targets, judges
    for p in sorted(runs_dir.glob("*/*.report.json")):
        try:
            report: Any = load_json(p)
        except (OSError, ValueError) as exc:
            report = {"unreadable": str(exc)}
        if not isinstance(report, dict):
            report = {"unreadable": f"not an object ({type(report).__name__})"}
        (judges if p.name.endswith(JUDGE_SUFFIX) else targets).append((p, report))
    return targets, judges


def _money(value: Any) -> float | None:
    return float(value) if isinstance(value, NUMBER) and not isinstance(value, bool) else None


def reconcile(journal_path: Path | str, runs_dir: Path | str, dashboard_path: Path | str | None = None) -> dict[str, Any]:
    """Join the lane's paid journal entries to the landed cost sidecars on the fire nonce.

    Returns `{"lane", "paid_fires": [row...], "sidecars": {"target", "judge"}, "unfolded_sidecars": [...],
    "problems": [...]}`. Each row carries the entry's `fired_utc`, `nonce`, `max_spend`, `resolved`, `evicted`,
    and, when one sidecar matched, the run directory, the target and judge `cost_usd`, their sum and whether the
    ledger has folded them (`None` when no dashboard was given). `problems` is the list a strict caller fails on.
    """
    entries = read_journal(journal_path)
    paid = [e for e in entries if e.get("trigger") == LANE and e.get("max_spend") is not None]
    targets, judges = _sidecars(Path(runs_dir))
    folded: set[str] | None = None
    if dashboard_path is not None and Path(dashboard_path).is_file():
        seen = (load_json(dashboard_path).get("spend") or {}).get("entries_seen")
        folded = set(seen) if isinstance(seen, list) else set()

    by_nonce: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    unbound: list[Path] = []
    problems: list[str] = []
    for p, r in targets:
        if "unreadable" in r:
            problems.append(f"{p.parent.name}/{p.name}: sidecar unreadable ({r['unreadable']})")
            continue
        nonce = r.get("journal_nonce")
        if isinstance(nonce, str) and nonce:
            by_nonce.setdefault(nonce, []).append((p, r))
        else:
            unbound.append(p)
    judge_by_dir = {p.parent.name: (p, r) for p, r in judges}

    rows: list[dict[str, Any]] = []
    known: set[str] = set()
    for e in paid:
        nonce = e.get("nonce")
        row: dict[str, Any] = {"fired_utc": e.get("fired_utc"), "nonce": nonce, "max_spend": _money(e.get("max_spend")),
                               "resolved": bool(e.get("resolved")), "evicted": bool(e.get("evicted")), "run": None,
                               "cost_usd": None, "judge_cost_usd": None, "total_usd": None, "cost_basis": None,
                               "folded": None, "judge_folded": None, "status": None}
        if not isinstance(nonce, str) or not nonce:
            row["status"] = "no nonce recorded"
            problems.append(f"paid fire {e.get('fired_utc')}: the journal entry records no nonce, so no sidecar can be joined to it")
            rows.append(row)
            continue
        known.add(nonce)
        matches = by_nonce.get(nonce, [])
        if row["evicted"] and not matches:
            row["status"] = "evicted before it ran"          # the queue superseded it; nothing was spent
        elif not matches:
            row["status"] = "no sidecar landed"
            problems.append(f"paid fire {e.get('fired_utc')} (nonce {nonce!r}): no cost sidecar carries its nonce; the run has not "
                            f"landed, or it failed before the workflow's fallback spend report")
        elif len(matches) > 1:
            row["status"] = "ambiguous"
            names = ", ".join(f"{p.parent.name}/{p.name}" for p, _ in matches)
            problems.append(f"paid fire {e.get('fired_utc')} (nonce {nonce!r}): {len(matches)} sidecars carry its nonce ({names})")
        else:
            p, r = matches[0]
            row["run"] = p.parent.name
            row["cost_usd"] = _money(r.get("cost_usd"))
            row["cost_basis"] = r.get("cost_basis") if isinstance(r.get("cost_basis"), str) else None
            if row["cost_usd"] is None:
                problems.append(f"{p.parent.name}/{p.name}: cost_usd is missing or not a number")
            judge = judge_by_dir.get(p.parent.name)
            if judge is not None:
                jp, jr = judge
                row["judge_cost_usd"] = _money(jr.get("cost_usd")) if "unreadable" not in jr else None
                if row["judge_cost_usd"] is None:
                    problems.append(f"{jp.parent.name}/{jp.name}: judge cost_usd is missing or not a number")
            if row["cost_usd"] is not None and (judge is None or row["judge_cost_usd"] is not None):
                row["total_usd"] = row["cost_usd"] + (row["judge_cost_usd"] or 0.0)
                if row["max_spend"] is not None and row["total_usd"] > row["max_spend"] + 1e-9:
                    problems.append(f"{p.parent.name}: landed cost {row['total_usd']:.4f} exceeds the fire's commitment "
                                    f"{row['max_spend']:.4f}")
            if folded is not None:
                row["folded"] = p.name in folded
                row["judge_folded"] = (judge[0].name in folded) if judge is not None else None
            row["status"] = "landed"
        rows.append(row)

    for p in unbound:
        problems.append(f"{p.parent.name}/{p.name}: sidecar carries no journal_nonce; no fire accounts for it")
    for nonce, matches in by_nonce.items():
        if nonce not in known:
            for p, _ in matches:
                problems.append(f"{p.parent.name}/{p.name}: journal_nonce {nonce!r} matches no paid {LANE} journal entry")
    unfolded = sorted(p.name for p, _ in targets + judges if folded is not None and p.name not in folded)
    return {"lane": LANE, "paid_fires": rows, "sidecars": {"target": len(targets), "judge": len(judges)},
            "unfolded_sidecars": unfolded, "problems": problems}


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    lines = [f"## {result['lane']}: paid fires against landed cost sidecars", "",
             "| fired (UTC) | nonce | commitment | run | target cost | judge cost | total | basis | folded | status |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in result["paid_fires"]:
        folded = "—" if r["folded"] is None else ("yes" if r["folded"] and r["judge_folded"] in (True, None) else "no")
        lines.append("| " + " | ".join(_cell(v) for v in (r["fired_utc"], r["nonce"], r["max_spend"], r["run"], r["cost_usd"],
                                                         r["judge_cost_usd"], r["total_usd"], r["cost_basis"], folded, r["status"])) + " |")
    if not result["paid_fires"]:
        lines.append("| — | — | — | — | — | — | — | — | — | no paid fire journaled |")
    s = result["sidecars"]
    lines += ["", f"Sidecars found: {s['target']} target, {s['judge']} judge."]
    if result["unfolded_sidecars"]:
        lines.append("Not yet folded into the ledger (the daily Routine folds): " + ", ".join(result["unfolded_sidecars"]))
    lines.append("")
    if result["problems"]:
        lines.append(f"**Problems ({len(result['problems'])})**")
        lines += [f"- {p}" for p in result["problems"]]
    else:
        lines.append("No problems: every paid fire has exactly one landed sidecar within its commitment, and every sidecar has its fire.")
    return "\n".join(lines) + "\n"
