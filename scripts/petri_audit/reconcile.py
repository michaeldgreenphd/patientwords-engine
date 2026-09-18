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

from .framework import ROOT, load_json

LANE = "petri-audit"
JUDGE_SUFFIX = ".judge.report.json"
NUMBER = (int, float)
DEFAULT_RUNS_DIR = ROOT / "data" / "petri" / "runs"      # the CLI's default; the first landed run creates it


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
    """A monetary field as a float, or None when it is anything money cannot be.

    `json.loads` accepts `NaN` and `Infinity`, and every comparison with NaN is
    False, so a NaN total sailed past the over-commitment check; a negative cost
    lowered a run's total instead of being named (Codex round 1 on PR #28). Both
    are None here, which every caller reports by name rather than treating as
    zero.
    """
    if not isinstance(value, NUMBER) or isinstance(value, bool):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")) or number < 0:
        return None
    return number


class Ledger:
    """What `ops/dashboard.json` has actually booked, per sidecar filename.

    `ledger_update.py` keeps two records: `spend.entries_seen`, every sidecar
    key it has ever folded, and `spend.entries_folded`, HOW MUCH of each one's
    `cost_usd` is booked. The second matters for this lane because a judge
    sidecar is cumulative (`cost_basis` `cumulative_from_records`): a resumed
    judge pass grows a file whose name is already in `entries_seen`, so the
    name alone says booked while the new delta has not reached the dashboard
    (Codex round 2 on PR #28). `ledger_update` also books Petri deltas in
    four-decimal steps and advances the watermark by what it booked, so a
    residual below that resolution waits legitimately and is not a gap.
    """

    RESOLUTION = 1e-4          # ledger_update's Petri branch books to four decimals

    def __init__(self, seen: set[str], folded: dict[str, float]) -> None:
        self.seen = seen
        self.folded = folded

    def state(self, name: str, cost: float | None) -> tuple[bool, str | None]:
        """(booked, why not) for one sidecar filename."""
        if name not in self.seen:
            return False, "the ledger has not folded it yet"
        if cost is None:
            return True, None                      # the cost itself is already a named problem
        booked = self.folded.get(name)
        if booked is None:
            return True, None                      # seen with no watermark: a pre-watermark fold, nothing owed
        if float(booked) + self.RESOLUTION < cost:
            return False, (f"the ledger has booked {float(booked):.4f} of its {cost:.4f}, so "
                           f"{cost - float(booked):.4f} of landed spend is not in the daily totals")
        return True, None


def _read_ledger(dashboard_path: Path | str | None, problems: list[str]) -> Ledger | None:
    """The ledger's booked state, or None when no dashboard was given or it
    cannot be read - an unreadable dashboard is a named problem, never an empty
    fold set that would report every landed sidecar as unbooked."""
    if dashboard_path is None:
        return None
    name = Path(dashboard_path).name
    if not Path(dashboard_path).is_file():
        # the CLI always supplies a path, so this is a mistyped --dashboard or a checkout without the ledger:
        # left silent, --strict printed "No problems" without having checked the ledger half at all
        problems.append(f"{dashboard_path}: no such file, so no sidecar can be checked against the ledger")
        return None
    try:
        dashboard: Any = load_json(dashboard_path)
    except (OSError, ValueError) as exc:
        problems.append(f"{name}: unreadable, so no sidecar can be checked against the ledger ({exc})")
        return None
    spend = dashboard.get("spend") if isinstance(dashboard, dict) else None
    if not isinstance(spend, dict):
        problems.append(f"{name}: no spend block, so no sidecar can be checked against the ledger")
        return None
    seen = spend.get("entries_seen")
    if not isinstance(seen, list):
        problems.append(f"{name}: spend.entries_seen is missing or not a list, so no sidecar can be checked "
                        "against the ledger")
        return None
    raw = spend.get("entries_folded")
    folded: dict[str, float] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            amount = _money(value)
            if amount is None:
                problems.append(f"{name}: spend.entries_folded[{key!r}] is {value!r}, not a finite non-negative "
                                "number, so how much of that sidecar is booked cannot be checked")
            else:
                folded[str(key)] = amount
    elif raw is not None:
        problems.append(f"{name}: spend.entries_folded is not an object, so how much of each sidecar is booked "
                        "cannot be checked")
    return Ledger({str(s) for s in seen}, folded)


def _flag(entry: dict[str, Any], key: str, problems: list[str]) -> bool:
    """A journal boolean, refused rather than coerced: `bool("false")` is True,
    which classified a paid fire with no sidecar as evicted and excused it from
    every check (Codex round 2 on PR #28). Anything but a real boolean reads as
    False, the state that keeps the fire under scrutiny."""
    value = entry.get(key, False)
    if isinstance(value, bool):
        return value
    problems.append(f"paid fire {entry.get('fired_utc')}: {key} is {value!r}, not true or false; read as false, "
                    "because a non-boolean flag must not be able to excuse a fire from reconciliation")
    return False


def _channel(value: Any, default: str = "anthropic") -> str:
    """A billing channel, defaulting the way `fire_trigger.inflight_max_spend`
    defaults a journal entry with no `lane`: to the account the daily ceiling
    bounds."""
    return value if isinstance(value, str) and value else default


def reconcile(journal_path: Path | str, runs_dir: Path | str, dashboard_path: Path | str | None = None) -> dict[str, Any]:
    """Join the lane's paid journal entries to the landed cost sidecars on the fire nonce.

    Returns `{"lane", "paid_fires": [row...], "sidecars": {"target", "judge"}, "unfolded_sidecars": [...],
    "problems": [...]}`. Each row carries the entry's `fired_utc`, `nonce`, `max_spend`, `resolved`, `evicted`,
    and, when one sidecar matched, the run directory, the target and judge `cost_usd`, their sum and whether the
    ledger has folded them (`None` when no dashboard was given). `problems` is the list a strict caller fails on.
    """
    entries = read_journal(journal_path)
    paid = [e for e in entries if e.get("trigger") == LANE and e.get("max_spend") is not None]
    problems: list[str] = []
    runs_absent = not Path(runs_dir).is_dir()
    if runs_absent and (paid or Path(runs_dir).resolve() != DEFAULT_RUNS_DIR.resolve()):
        # a mistyped --runs, or a checkout without the runs tree: read as an empty archive it reported "no
        # problems" with nothing scanned, or blamed every fire for a sidecar that was never looked for.
        # The default path before the lane's first landed run is not that: nothing has created it yet and no
        # paid fire is waiting on it, so the report states the absence without calling it a problem.
        problems.append(f"{runs_dir}: no such directory, so no landed sidecar was scanned at all")
    targets, judges = _sidecars(Path(runs_dir))
    ledger = _read_ledger(dashboard_path, problems)

    by_nonce: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    unbound: list[Path] = []
    for p, r in targets:
        if "unreadable" in r:
            problems.append(f"{p.parent.name}/{p.name}: sidecar unreadable ({r['unreadable']})")
            continue
        nonce = r.get("journal_nonce")
        if isinstance(nonce, str) and nonce:
            by_nonce.setdefault(nonce, []).append((p, r))
        else:
            unbound.append(p)
    # one judge sidecar per run directory is what the writers produce; keeping the last of several silently
    # dropped the others' cost from the reconciliation (Codex round 1 on PR #28), so an ambiguous directory
    # carries no judge cost at all and is named
    judges_by_dir: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for p, r in judges:
        judges_by_dir.setdefault(p.parent.name, []).append((p, r))
    judge_by_dir: dict[str, tuple[Path, dict[str, Any]]] = {}
    for run_dir, found in judges_by_dir.items():
        if len(found) == 1:
            judge_by_dir[run_dir] = found[0]
        else:
            names = ", ".join(p.name for p, _ in found)
            problems.append(f"{run_dir}: {len(found)} judge sidecars ({names}); one run directory carries one "
                            "judge pass, so none of their costs is joined to a fire")

    # A nonce binds ONE journal entry to ONE sidecar. Two paid entries carrying the same one - merged journal
    # histories, a hand edit, or a fire made before the fire path refused a repeat - each matched the single
    # sidecar independently and both reported "landed", booking one cost against two commitments (Codex round 2
    # on PR #28). fire_trigger refuses a repeat at the fire; this refuses it in the record.
    nonce_counts: dict[str, int] = {}
    for e in paid:
        n = e.get("nonce")
        if isinstance(n, str) and n:
            nonce_counts[n] = nonce_counts.get(n, 0) + 1
    duplicated = {n for n, c in nonce_counts.items() if c > 1}
    for n in sorted(duplicated):
        when = ", ".join(str(e.get("fired_utc")) for e in paid if e.get("nonce") == n)
        problems.append(f"nonce {n!r} is on {nonce_counts[n]} paid {LANE} journal entries ({when}); a nonce binds "
                        "one fire to one landed cost, so none of them is joined to a sidecar")

    rows: list[dict[str, Any]] = []
    known: set[str] = set()
    for e in paid:
        nonce = e.get("nonce")
        row: dict[str, Any] = {"fired_utc": e.get("fired_utc"), "nonce": nonce, "max_spend": _money(e.get("max_spend")),
                               "resolved": _flag(e, "resolved", problems), "evicted": _flag(e, "evicted", problems),
                               "run": None, "cost_usd": None, "judge_cost_usd": None, "total_usd": None,
                               "cost_basis": None, "folded": None, "judge_folded": None, "status": None}
        if row["max_spend"] is None:
            problems.append(f"paid fire {e.get('fired_utc')}: max_spend {e.get('max_spend')!r} is not a finite "
                            "non-negative number, so the landed cost cannot be checked against the commitment")
        if not isinstance(nonce, str) or not nonce:
            row["status"] = "no nonce recorded"
            problems.append(f"paid fire {e.get('fired_utc')}: the journal entry records no nonce, so no sidecar can be joined to it")
            rows.append(row)
            continue
        known.add(nonce)
        if nonce in duplicated:
            row["status"] = "duplicate nonce"      # named once above; no cost is attributed to either fire
            rows.append(row)
            continue
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
                problems.append(f"{p.parent.name}/{p.name}: cost_usd {r.get('cost_usd')!r} is missing or not a "
                                "finite non-negative number")
            judge = judge_by_dir.get(p.parent.name)
            if judge is not None:
                jp, jr = judge
                if "unreadable" in jr:
                    problems.append(f"{jp.parent.name}/{jp.name}: judge sidecar unreadable ({jr['unreadable']})")
                else:
                    row["judge_cost_usd"] = _money(jr.get("cost_usd"))
                    if row["judge_cost_usd"] is None:
                        problems.append(f"{jp.parent.name}/{jp.name}: judge cost_usd {jr.get('cost_usd')!r} is missing "
                                        "or not a finite non-negative number")
            if row["cost_usd"] is not None and (judge is None or row["judge_cost_usd"] is not None):
                row["total_usd"] = row["cost_usd"] + (row["judge_cost_usd"] or 0.0)
                if row["max_spend"] is not None and row["total_usd"] > row["max_spend"] + 1e-9:
                    problems.append(f"{p.parent.name}: landed cost {row['total_usd']:.4f} exceeds the fire's commitment "
                                    f"{row['max_spend']:.4f}")
            # The fire reserved its commitment against ONE prepaid account (the journal's `lane`), and the ledger
            # books the landed cost against whatever the sidecar's `billing_channel` says. A mismatch moves spend
            # between the Anthropic and OpenRouter ceilings unseen (Codex round 2 on PR #28).
            lane = _channel(e.get("lane"))
            for sp, sr, what in ([(p, r, "sidecar")] + ([(judge[0], judge[1], "judge sidecar")]
                                                        if judge is not None and "unreadable" not in judge[1] else [])):
                channel = _channel(sr.get("billing_channel"), "")
                if channel and channel != lane:
                    problems.append(f"{sp.parent.name}/{sp.name}: the {what} books the {channel} account but the fire "
                                    f"reserved its commitment on {lane}, so the two ceilings disagree about this spend")
                elif not channel:
                    problems.append(f"{sp.parent.name}/{sp.name}: the {what} states no billing_channel, so which "
                                    "account its cost lands on cannot be checked against the fire's lane")
            if ledger is not None:
                booked, why = ledger.state(p.name, row["cost_usd"])
                row["folded"] = booked
                if not booked:
                    problems.append(f"{p.parent.name}/{p.name}: {why}")
                if judge is not None:
                    jbooked, jwhy = ledger.state(judge[0].name, row["judge_cost_usd"])
                    row["judge_folded"] = jbooked
                    if not jbooked:
                        problems.append(f"{judge[0].parent.name}/{judge[0].name}: {jwhy}")
            row["status"] = "landed"
        rows.append(row)

    for p in unbound:
        problems.append(f"{p.parent.name}/{p.name}: sidecar carries no journal_nonce; no fire accounts for it")
    # a judge sidecar is joined through its run directory's target sidecar, so one standing alone is booked by
    # the ledger and reported by nothing here unless it is named (the fallback spend-report step writes a target
    # sidecar for every attempted run, so this means that step did not run either)
    target_dirs = {p.parent.name for p, _ in targets}
    for p, _ in judges:
        if p.parent.name not in target_dirs:
            problems.append(f"{p.parent.name}/{p.name}: judge sidecar with no target sidecar in its run directory, "
                            "so no journal entry accounts for its cost")
    for nonce, matches in by_nonce.items():
        if nonce not in known:
            for p, _ in matches:
                problems.append(f"{p.parent.name}/{p.name}: journal_nonce {nonce!r} matches no paid {LANE} journal entry")
    # Every sidecar the ledger has not fully booked, joined to a fire or not. Each one is already a problem in
    # its own right - a joined sidecar through the fold check above, an unjoined one through the checks just
    # above that - so `--strict` no longer exits 0 while this list is non-empty (Codex round 2 on PR #28).
    unfolded: list[str] = []
    if ledger is not None:
        for p, r in targets + judges:
            if "unreadable" in r:
                continue
            if not ledger.state(p.name, _money(r.get("cost_usd")))[0]:
                unfolded.append(p.name)
    unfolded = sorted(unfolded)
    if runs_absent:
        # stated whether or not it is a problem, so "Sidecars found: 0" is never read as "the archive is empty"
        problems_note = f"{runs_dir}: no such directory (no run has landed here)"
    else:
        problems_note = None
    return {"lane": LANE, "paid_fires": rows, "sidecars": {"target": len(targets), "judge": len(judges)},
            "runs_dir": str(runs_dir), "runs_dir_note": problems_note,
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
    if result.get("runs_dir_note"):
        lines.append(result["runs_dir_note"])
    if result["unfolded_sidecars"]:
        lines.append("Not yet folded into the ledger (the daily Routine folds): " + ", ".join(result["unfolded_sidecars"]))
    lines.append("")
    if result["problems"]:
        lines.append(f"**Problems ({len(result['problems'])})**")
        lines += [f"- {p}" for p in result["problems"]]
    else:
        lines.append("No problems: every paid fire has exactly one landed sidecar within its commitment, on the "
                     "account it reserved, fully booked into the ledger, and every sidecar has its fire.")
    return "\n".join(lines) + "\n"
