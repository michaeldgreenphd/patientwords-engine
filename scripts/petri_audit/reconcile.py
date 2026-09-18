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
from datetime import datetime
from pathlib import Path
from typing import Any

from .framework import ROOT, load_json

LANE = "petri-audit"
JUDGE_SUFFIX = ".judge.report.json"
NUMBER = (int, float)
# `ledger_update.billing_channel` honours an explicit field ONLY for these two and silently books anything else to
# the Anthropic account the $2/day guard bounds, so an unrecognised channel is not a channel (Codex round 6 on PR #28)
CHANNELS = ("anthropic", "openrouter")
# What each writer actually emits. `spend.write_report_sidecar` gives a target one of two bases; the judge loop
# writes the cumulative basis and the fallback `judge-spend-report` an imputed or repriced one. The cumulative
# basis matters to the ledger: on first sight it books `run_cost_usd` to the run's day while advancing the folded
# watermark by the whole `cost_usd`, so a target claiming it, or a judge claiming it with inconsistent component
# costs, understates the daily total while reconciliation reads the watermark as fully booked (Codex round 6).
TARGET_BASES = ("engine_repriced_from_inspect_model_usage", "ceiling_imputed:usage_missing")
JUDGE_BASES = ("cumulative_from_records", "ceiling_imputed:judge_aborted_without_sidecar",
               "engine_repriced_from_inspect_model_usage")
CUMULATIVE = "cumulative_from_records"
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
            # `ledger_update` writes the filename to entries_seen and its cost to entries_folded in the same
            # fold, and this lane postdates that watermark, so there is no legitimate pre-watermark Petri
            # record: seen with no watermark means a truncated or edited dashboard (Codex round 5 on PR #28)
            return False, ("the ledger lists it as folded but records no amount for it in spend.entries_folded, "
                           "so how much of its cost reached the daily totals cannot be established")
        if float(booked) + self.RESOLUTION < cost:
            return False, (f"the ledger has booked {float(booked):.4f} of its {cost:.4f}, so "
                           f"{cost - float(booked):.4f} of landed spend is not in the daily totals")
        if cost + self.RESOLUTION < float(booked):
            # the archive now claims LESS than the ledger booked: a sidecar rewritten or truncated after its
            # fold, which is exactly the alteration this command exists to surface, and growth-only comparison
            # read it as fully booked (Codex round 3 on PR #28)
            return False, (f"the ledger has booked {float(booked):.4f} but the sidecar now records {cost:.4f}: a "
                           "landed cost record cannot shrink, so either it was rewritten or the ledger over-booked")
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


def _timestamp(value: Any) -> datetime | None:
    """A sidecar's `run_utc` as a datetime, or None when it is missing or does
    not parse. `ledger_update.parse_ts` reads the same field and falls back to
    the scan date when it cannot, which books the cost to the wrong day - so
    this mirrors that function exactly rather than parsing as it pleases. In
    particular it does NOT strip: `datetime.fromisoformat` rejects surrounding
    whitespace, so a padded stamp the ledger falls back on must be reported
    here too (found in self-review, 2026-09-18)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _channel(value: Any, default: str = "anthropic") -> str:
    """A billing channel, defaulting the way `fire_trigger.inflight_max_spend`
    defaults a journal entry with no `lane`: to the account the daily ceiling
    bounds. An unrecognised value is returned as given so the caller can name
    it - `_channel_unsupported` is the test, because two records agreeing on
    `"stripe"` are not agreeing about anything the ledger will honour."""
    return value if isinstance(value, str) and value else default


def _channel_unsupported(value: Any) -> str | None:
    """The offending value when a billing channel is present and is neither
    account the ledger knows, else None. `ledger_update.billing_channel` takes
    an explicit field only for `anthropic` and `openrouter`; anything else
    falls through to model-name derivation and lands on Anthropic, so a
    sidecar and a journal entry can agree on a channel the ledger ignores
    (Codex round 6 on PR #28)."""
    if isinstance(value, str) and value and value not in CHANNELS:
        return value
    return None


def _basis_problems(label: str, report: dict[str, Any], cost: float | None, judge: bool) -> list[str]:
    """Why a sidecar's `cost_basis` (and, for the cumulative basis, its
    component costs) cannot be trusted to have folded correctly.

    The basis is not decoration: `ledger_update` reads it. On a first fold a
    `cumulative_from_records` sidecar books `run_cost_usd` to the run's day and
    the whole `cost_usd` to the folded watermark, so `run_cost_usd: 0` beside a
    positive `cost_usd` leaves the daily total untouched while this module's
    watermark check reads the file as fully booked (Codex round 6 on PR #28).
    """
    found: list[str] = []
    basis = report.get("cost_basis")
    allowed = JUDGE_BASES if judge else TARGET_BASES
    if not isinstance(basis, str) or basis not in allowed:
        found.append(f"{label}: cost_basis {basis!r} is not one this lane's "
                     f"{'judge' if judge else 'target'} writer emits ({', '.join(allowed)}), so how the ledger "
                     "books it cannot be established")
        return found
    if basis != CUMULATIVE:
        return found
    run_cost, prior = _money(report.get("run_cost_usd")), _money(report.get("prior_cost_usd"))
    if run_cost is None or prior is None:
        found.append(f"{label}: cost_basis is {CUMULATIVE} but run_cost_usd {report.get('run_cost_usd')!r} and "
                     f"prior_cost_usd {report.get('prior_cost_usd')!r} are not both finite non-negative numbers, "
                     "and the ledger books run_cost_usd to the run's day")
    elif cost is not None and (run_cost > cost + 1e-9 or abs(run_cost + prior - cost) > 1e-6):
        found.append(f"{label}: cost_basis is {CUMULATIVE} with run_cost_usd {run_cost:.8f} and prior_cost_usd "
                     f"{prior:.8f}, which do not account for cost_usd {cost:.8f}; the ledger books run_cost_usd to "
                     "the run's day only while it is within cost_usd and the whole cost_usd otherwise, and the "
                     "folded watermark advances by the whole cost_usd either way, so the day's figure does not "
                     "follow from this record")
    return found


def _judge_identity_problem(run_dir: str, target: dict[str, Any], judge: dict[str, Any]) -> str | None:
    """Why a judge sidecar does not belong to the target run it sits beside.

    Sharing a directory is not identity: a sidecar copied or renamed from
    another run joins on the directory alone and its cost and judgments are
    attributed to this fire (Codex round 6 on PR #28). The two writers record
    identity differently, and the check follows them rather than assuming:
    the judge loop copies `run_id` and `eval_id` from the manifest, exactly as
    `adapt --report` does for the target, while the fallback
    `judge-spend-report` records the run DIRECTORY as its `run_id` and no
    `eval_id` at all. Comparing `run_id` blindly would therefore fail on the
    realistic path where an adapted run's judge died - the target carries
    Inspect's run id and the fallback carries the directory name.
    """
    def text(record: dict[str, Any], key: str) -> str | None:
        value = record.get(key)
        return value if isinstance(value, str) and value else None

    j_eval, t_eval = text(judge, "eval_id"), text(target, "eval_id")
    j_run, t_run = text(judge, "run_id"), text(target, "run_id")
    if j_eval is None:
        # the fallback writer: it names the directory it was written into. An ABSENT run_id is not the fallback
        # shape either - both judge writers record an identity, so a report carrying neither field is truncated
        # or copied, and letting it through attributes another run's cost here (Codex round 7 on PR #28).
        if j_run is None:
            return (f"{run_dir}: the judge sidecar records neither eval_id nor run_id; both judge writers record "
                    "an identity, so nothing ties this report to the run it sits in")
        if j_run != run_dir:
            return (f"{run_dir}: the judge sidecar records run_id {j_run!r}, but the fallback judge writer records "
                    f"the run directory, which is {run_dir!r}; this judge report was written for another run")
        return None
    if t_eval is not None and j_eval != t_eval:
        return (f"{run_dir}: the judge sidecar records eval_id {j_eval!r} and the target sidecar {t_eval!r}; both "
                "copy it from the same manifest, so this judge report belongs to another run")
    if j_run is not None and t_run is not None and j_run != t_run:
        return (f"{run_dir}: the judge sidecar records run_id {j_run!r} and the target sidecar {t_run!r}; both copy "
                "it from the same manifest, so this judge report belongs to another run")
    return None


def reconcile(journal_path: Path | str, runs_dir: Path | str, dashboard_path: Path | str | None = None) -> dict[str, Any]:
    """Join the lane's paid journal entries to the landed cost sidecars on the fire nonce.

    Returns `{"lane", "paid_fires": [row...], "sidecars": {"target", "judge"}, "runs_dir", "runs_dir_note",
    "unfolded_sidecars": [...], "problems": [...]}`. Each row carries the entry's `fired_utc`, `nonce`,
    `max_spend`, `resolved`, `evicted`, and, when exactly one sidecar matched, the run directory, the target and
    judge `cost_usd`, their sum and whether the ledger has booked them - `None` where no dashboard was given or
    it could not be read, never `False`, since unknown is not unbooked. `runs_dir_note` states an absent runs
    archive whether or not it is a problem. `problems` is the list a strict caller fails on; every sidecar the
    ledger has not booked is in it, so `unfolded_sidecars` is never a list of unnamed gaps.
    """
    entries = read_journal(journal_path)
    # A paid entry is CLASSIFIED before its commitment is read: filtering on `max_spend is not None` dropped an
    # entry that carries the paid-only `lane` with a missing or null commitment, so a paid fire whose sidecar is
    # also absent went unmentioned entirely (Codex round 3 on PR #28). `cmd_fire` writes both keys together on a
    # paid fire and neither on a free one, so either key present means the entry claims to be paid.
    paid = [e for e in entries if e.get("trigger") == LANE and ("max_spend" in e or "lane" in e)]
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

    # `ledger_update.sidecar_key` keys a Petri sidecar on its BARE FILENAME, so two run directories holding the
    # same basename are one entry to the ledger: it folds the first and the second never reaches the daily totals,
    # while a watermark that covers the first covers the second too and this module would read both as booked
    # (Codex round 6 on PR #28). The writers name every sidecar after its run directory, so a repeat is a copied
    # or renamed file - exactly the archive alteration this command exists to surface.
    by_basename: dict[str, set[str]] = {}
    for sp, _ in targets + judges:
        by_basename.setdefault(sp.name, set()).add(sp.parent.name)
    duplicate_names = {name for name, dirs in by_basename.items() if len(dirs) > 1}
    for name in sorted(duplicate_names):
        where = ", ".join(sorted(by_basename[name]))
        problems.append(f"{name}: the same sidecar basename is in {len(by_basename[name])} run directories "
                        f"({where}); the ledger keys Petri sidecars by bare filename, so only one of them can ever "
                        "be folded and neither can be checked against the ledger")

    # One run directory holds one target sidecar. Two carrying different nonces each matched a fire cleanly, so
    # both read "landed" while the directory's single judge sidecar was attached to both rows and its cost
    # counted twice (Codex round 3 on PR #28); such a directory joins nothing.
    targets_by_dir: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for p, r in targets:
        targets_by_dir.setdefault(p.parent.name, []).append((p, r))
    ambiguous_dirs = {d for d, found in targets_by_dir.items() if len(found) > 1}
    for run_dir in sorted(ambiguous_dirs):
        names = ", ".join(p.name for p, _ in targets_by_dir[run_dir])
        problems.append(f"{run_dir}: {len(targets_by_dir[run_dir])} target sidecars ({names}); one run directory "
                        "is one run, so none of them is joined to a fire")

    by_nonce: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    unbound: list[Path] = []
    for p, r in targets:
        if "unreadable" in r:
            problems.append(f"{p.parent.name}/{p.name}: sidecar unreadable ({r['unreadable']})")
            continue
        if p.parent.name in ambiguous_dirs:
            continue                               # named above; joining any of them would attribute one run twice
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
            problems.extend(_basis_problems(f"{p.parent.name}/{p.name}", r, row["cost_usd"], judge=False))
            if row["evicted"]:
                # eviction released this fire's in-flight commitment, so a replacement was admitted without
                # counting it; a sidecar proves the run went ahead anyway (Codex round 4 on PR #28)
                problems.append(f"paid fire {e.get('fired_utc')} (nonce {nonce!r}) is journaled evicted but landed "
                                f"{p.parent.name}: the queue released its commitment while the run spent, so the "
                                "daily total for that day is short by whatever it cost")
            # `ledger_update` books a sidecar to the day its `run_utc` names and falls back to the scan date when
            # that cannot be parsed, which puts the spend in the wrong daily bucket (Codex round 4 on PR #28)
            for sp, sr in ([(p, r)] + ([judge_by_dir[p.parent.name]] if p.parent.name in judge_by_dir else [])):
                if "unreadable" in sr:
                    continue
                # `ledger_update` reads the stamp in TWO different orders: its first-fold loop takes
                # `run_timestamp or run_utc` and its growth loop `run_utc or run_timestamp`. With both fields
                # present and one of them malformed the two paths disagree, and whichever hits the bad value
                # falls back to the scan date - so BOTH expressions must parse, not just the one a growth fold
                # would use (Codex round 7 on PR #28).
                for field_order, chosen in (("run_timestamp or run_utc", sr.get("run_timestamp") or sr.get("run_utc")),
                                            ("run_utc or run_timestamp", sr.get("run_utc") or sr.get("run_timestamp"))):
                    if _timestamp(chosen) is None:
                        problems.append(f"{sp.parent.name}/{sp.name}: the stamp `{field_order}` resolves to "
                                        f"{chosen!r}, which does not parse, so the ledger books its cost to the day "
                                        "it happens to scan rather than the run's (run_utc "
                                        f"{sr.get('run_utc')!r}, run_timestamp {sr.get('run_timestamp')!r})")
                        break
            judge = judge_by_dir.get(p.parent.name)
            # a target sidecar that records a judge ceiling says a judge pass was requested; no judge sidecar
            # beside it then hides up to that ceiling rather than a zero (Codex round 4 on PR #28). A ceiling
            # that is present but unusable is named rather than read as absent, which would suppress this check
            # as well as the authorisation one below (Codex round 5).
            judge_ceiling = _money(r.get("judge_max_spend_usd"))
            if r.get("judge_max_spend_usd") is not None and judge_ceiling is None:
                problems.append(f"{p.parent.name}/{p.name}: judge_max_spend_usd {r.get('judge_max_spend_usd')!r} is "
                                "not a finite non-negative number, so neither the judge's ceiling nor whether one "
                                "was requested can be established")
            # ...but only beside an ADAPTED sidecar. `spend_report_reason` is written by the workflow's fallback
            # `spend-report` step, which runs only when no adapted report exists - and the judge step is gated on
            # adapt succeeding, so it never started, its marker was never touched and `judge-spend-report` wrote
            # nothing. There the artifacts prove the zero rather than hiding a cost, and demanding a judge sidecar
            # would make every failed paid run report a gap that is not one (self-review, 2026-09-18).
            attempted_only = isinstance(r.get("spend_report_reason"), str) and r.get("spend_report_reason")
            if judge is not None and "unreadable" not in judge[1] and judge_ceiling is None \
                    and r.get("judge_max_spend_usd") is None:
                # the mirror of the check below: the run declares no judge reservation, yet a judge report landed.
                # With `judge: false` the workflow never runs the judge step, never touches its marker and never
                # writes a judge sidecar, so this is a stray or drifted paid report whose ceiling would otherwise
                # be read out of the judge's own file and folded into the authorisation sum (Codex round 6).
                problems.append(f"{p.parent.name}: a judge sidecar landed but the run reserved nothing for a judge "
                                "pass (judge_max_spend_usd is absent), so its cost was never counted against the "
                                "daily ceiling")
            if judge is None and judge_ceiling and not attempted_only:
                problems.append(f"{p.parent.name}: the run reserved {judge_ceiling:.4f} for a judge pass and no judge "
                                "sidecar landed beside it, so its cost is unaccounted rather than zero")
            if judge is not None:
                jp, jr = judge
                if "unreadable" in jr:
                    problems.append(f"{jp.parent.name}/{jp.name}: judge sidecar unreadable ({jr['unreadable']})")
                else:
                    row["judge_cost_usd"] = _money(jr.get("cost_usd"))
                    if row["judge_cost_usd"] is None:
                        problems.append(f"{jp.parent.name}/{jp.name}: judge cost_usd {jr.get('cost_usd')!r} is missing "
                                        "or not a finite non-negative number")
                    problems.extend(_basis_problems(f"{jp.parent.name}/{jp.name}", jr, row["judge_cost_usd"],
                                                    judge=True))
                    mismatch = _judge_identity_problem(p.parent.name, r, jr)
                    if mismatch:
                        problems.append(mismatch)
            if row["cost_usd"] is not None and (judge is None or row["judge_cost_usd"] is not None):
                row["total_usd"] = row["cost_usd"] + (row["judge_cost_usd"] or 0.0)
                if row["max_spend"] is not None and row["total_usd"] > row["max_spend"] + 1e-9:
                    problems.append(f"{p.parent.name}: landed cost {row['total_usd']:.4f} exceeds the fire's commitment "
                                    f"{row['max_spend']:.4f}")
            # Each component against its OWN ceiling, not only the pair against the commitment: a target that
            # overspends its max_spend_usd while the judge underspends stays under the journal's total and the
            # aggregate check passes, though CI let one side spend past what it was authorised (Codex round 6 on
            # PR #28). The imputed sidecars book exactly their ceiling, so only a strict excess is a problem.
            target_ceiling_now = _money(r.get("max_spend_usd"))
            if row["cost_usd"] is not None and target_ceiling_now is not None \
                    and row["cost_usd"] > target_ceiling_now + 1e-9:
                problems.append(f"{p.parent.name}/{p.name}: target cost {row['cost_usd']:.4f} exceeds the ceiling "
                                f"{target_ceiling_now:.4f} the run itself records, whatever the commitment allows")
            # What the run was AUTHORISED to spend, not only what it did: the daily guard counted the journal's
            # commitment, so ceilings on the sidecar that sum higher mean CI ran with more headroom than the guard
            # reserved, and a low actual cost hides it (Codex round 4 on PR #28).
            target_ceiling = _money(r.get("max_spend_usd"))
            if "max_spend_usd" not in r:
                # `spend.write_report_sidecar` always emits it, so an absent key is a truncated or edited record,
                # not an optional field - and the `is not None` guard below read it as nothing to check, which let
                # a low-cost sidecar pass --strict with its authorisation unverifiable (Codex round 7 on PR #28)
                problems.append(f"{p.parent.name}/{p.name}: max_spend_usd is absent; the target writer always "
                                "records it, so what the run was authorised to spend cannot be established")
            elif target_ceiling is None:
                problems.append(f"{p.parent.name}/{p.name}: max_spend_usd {r.get('max_spend_usd')!r} is not a finite "
                                "non-negative number, so what the run was authorised to spend cannot be established")
            # the judge report records the ceiling the judge loop ACTUALLY ran under; the target report only
            # declares what was requested, and the two can differ (Codex round 5 on PR #28)
            judge_actual = None
            if judge is not None and "unreadable" not in judge[1]:
                judge_actual = _money(judge[1].get("max_spend_usd"))
                if "max_spend_usd" not in judge[1]:
                    # both judge writers record it, so the same reasoning as the target's applies
                    problems.append(f"{judge[0].parent.name}/{judge[0].name}: max_spend_usd is absent; both judge "
                                    "writers record it, so the ceiling the judge ran under cannot be established")
                elif judge[1].get("max_spend_usd") is not None and judge_actual is None:
                    problems.append(f"{judge[0].parent.name}/{judge[0].name}: max_spend_usd "
                                    f"{judge[1].get('max_spend_usd')!r} is not a finite non-negative number")
                elif judge_actual is not None and judge_ceiling is not None \
                        and abs(judge_actual - judge_ceiling) > 1e-9:
                    problems.append(f"{p.parent.name}: the judge ran under a ceiling of {judge_actual:.4f} but the "
                                    f"run declared {judge_ceiling:.4f}, so the two records of the same reservation "
                                    "disagree")
            judge_limit = judge_actual if judge_actual is not None else judge_ceiling
            if row["judge_cost_usd"] is not None and judge_limit is not None \
                    and row["judge_cost_usd"] > judge_limit + 1e-9:
                problems.append(f"{p.parent.name}: judge cost {row['judge_cost_usd']:.4f} exceeds the judge ceiling "
                                f"{judge_limit:.4f} it ran under, whatever the commitment allows")
            ceilings = [target_ceiling, judge_actual if judge_actual is not None else judge_ceiling]
            authorised = sum(c for c in ceilings if c is not None)
            if row["max_spend"] is not None and any(c is not None for c in ceilings) \
                    and authorised > row["max_spend"] + 1e-9:
                problems.append(f"{p.parent.name}: the run carried ceilings summing to {authorised:.4f} but the fire "
                                f"reserved {row['max_spend']:.4f}, so it was authorised to spend past what the daily "
                                "guard counted")
            # The fire reserved its commitment against ONE prepaid account (the journal's `lane`), and the ledger
            # books the landed cost against whatever the sidecar's `billing_channel` says. A mismatch moves spend
            # between the Anthropic and OpenRouter ceilings unseen (Codex round 2 on PR #28).
            lane = _channel(e.get("lane"))
            unsupported = _channel_unsupported(e.get("lane"))
            if unsupported:
                problems.append(f"paid fire {e.get('fired_utc')} (nonce {nonce!r}): lane {unsupported!r} is not an "
                                f"account this study bills ({' or '.join(CHANNELS)}), so the ceiling it reserved "
                                "against cannot be identified")
            for sp, sr, what in ([(p, r, "sidecar")] + ([(judge[0], judge[1], "judge sidecar")]
                                                        if judge is not None and "unreadable" not in judge[1] else [])):
                channel = _channel(sr.get("billing_channel"), "")
                unsupported = _channel_unsupported(channel)
                if unsupported:
                    problems.append(f"{sp.parent.name}/{sp.name}: the {what} books billing_channel {unsupported!r}, "
                                    f"which is neither {' nor '.join(CHANNELS)}; `ledger_update` honours an explicit "
                                    "channel only for those two and books everything else to the Anthropic account, "
                                    "so this cost lands somewhere the record does not say")
                elif channel and channel != lane:
                    problems.append(f"{sp.parent.name}/{sp.name}: the {what} books the {channel} account but the fire "
                                    f"reserved its commitment on {lane}, so the two ceilings disagree about this spend")
                elif not channel:
                    problems.append(f"{sp.parent.name}/{sp.name}: the {what} states no billing_channel, so which "
                                    "account its cost lands on cannot be checked against the fire's lane")
            if ledger is not None:
                # the row records the state; the problem for an unbooked sidecar is raised once, below, over
                # every sidecar - joined to a fire or not - so nothing can be listed as unfolded and unnamed.
                # A basename that repeats across run directories is left None: the ledger cannot tell the two
                # apart, so neither "booked" nor "unbooked" is a true statement about this file (Codex round 6).
                if p.name not in duplicate_names:
                    row["folded"] = ledger.state(p.name, row["cost_usd"])[0]
                if judge is not None and judge[0].name not in duplicate_names:
                    row["judge_folded"] = ledger.state(judge[0].name, row["judge_cost_usd"])[0]
                # Folded but unresolved is not a transient: the ledger folds in the daily cycle, long after
                # `resolve` should have run. Until it does, `entry_is_active` keeps counting the fire's whole
                # commitment as in-flight ON TOP of the landed cost, and it holds a queue slot until it expires
                # (Codex round 5 on PR #28). Before the fold this is the ordinary gap between landing and
                # resolving, so it is not reported.
                if row["folded"] and row["judge_folded"] in (True, None) and not row["resolved"] \
                        and not row["evicted"]:
                    problems.append(f"paid fire {e.get('fired_utc')} (nonce {nonce!r}) landed and is fully booked but "
                                    "the journal entry is still unresolved: its commitment keeps counting as "
                                    "in-flight beside the landed cost and it holds a queue slot until it expires. "
                                    "Run `fire_trigger.py resolve --trigger petri-audit`")
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
    # Every sidecar the ledger has not fully booked, joined to a fire or not, named here and nowhere else, so
    # `--strict` cannot exit 0 while this list is non-empty (Codex round 2 on PR #28).
    unfolded: list[str] = []
    if ledger is not None:
        for p, r in targets + judges:
            if "unreadable" in r:
                continue                       # already named; its cost cannot be read, so nothing is owed on it
            if p.name in duplicate_names:
                continue                       # named above; the ledger's key cannot distinguish the copies
            booked, why = ledger.state(p.name, _money(r.get("cost_usd")))
            if not booked:
                unfolded.append(p.name)
                problems.append(f"{p.parent.name}/{p.name}: {why}")
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
    elif not result["paid_fires"] and not s["target"] and not s["judge"]:
        # a universal claim over an empty set reads as an assurance it is not: say what was actually the case
        lines.append("Nothing to reconcile: no paid petri-audit fire is journaled and no cost sidecar has landed.")
    else:
        lines.append("No problems: every paid fire has exactly one landed sidecar within its commitment and its own "
                     "ceilings, on an account the ledger honours, fully booked into it, and every sidecar has its "
                     "fire.")
    return "\n".join(lines) + "\n"
