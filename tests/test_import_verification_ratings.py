"""Physician verification ratings import (scripts/import_verification_ratings.py) - offline.

Pins Krippendorff's alpha against the worked examples of Krippendorff (2011), "Computing Krippendorff's
Alpha-Reliability" (binary 0.095, two-coder nominal 0.692, four-coder nominal with missing data 0.743, the same data
ordinal 0.815, the coincidence matrix and the ordinal difference table); every named refusal (bundle and questions
sha256, unknown ids, bad values, identity fields and addresses, malformed events, broken reveal rules, outputs that
exist); first against latest answers; blind answers of reveal items taken from the reveal event, with later changes
counted; complete ratings only; exclusion of named raters and the warning for a removed one; the combined tier rule
(odd, even, even split to the more urgent, fewer than two answers, abstentions) and the proposed adjudication file;
determinism under a seed; and an integration test over a synthetic export the verification app's own server code
wrote over the real task bundle (tests/fixtures/verification_export_synthetic.json), checked against an oracle the
generating script computed from what it saved, with alpha values from the third-party `krippendorff` package
(tests/fixtures/verification_export_synthetic.expected.json).

Every export here is synthetic: rater codes, ids, answer values and invented neutral notes. Question ids, scale values
and tier ids are read from the questions in the bundle, never written here (AGENTS.md's medical vocabulary rule).
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("import_verification_ratings",
                                               ROOT / "scripts" / "import_verification_ratings.py")
ivr = importlib.util.module_from_spec(_SPEC)
sys.modules["import_verification_ratings"] = ivr  # dataclasses resolve their module through sys.modules
_SPEC.loader.exec_module(ivr)

BUNDLE_PATH = ROOT / "data" / "verification" / "tasks_20261004T042945Z.json"
BUNDLE_BYTES = BUNDLE_PATH.read_bytes()
BUNDLE = json.loads(BUNDLE_BYTES)
BUNDLE_SHA = hashlib.sha256(BUNDLE_BYTES).hexdigest()
Q = BUNDLE["questions"]
FIXTURE = ROOT / "tests" / "fixtures" / "verification_export_synthetic.json"
EXPECTED = ROOT / "tests" / "fixtures" / "verification_export_synthetic.expected.json"
ITEMS = {i["item_id"]: i for i in BUNDLE["items"]}
BY_SET: dict[str, list[str]] = {}
for _i in sorted(ITEMS):
    BY_SET.setdefault(ITEMS[_i]["question_set"], []).append(_i)
REVEAL_SET = next(i["question_set"] for i in BUNDLE["items"] if i["reveal"] is not None)
TIER_Q = next(q for q in Q["question_sets"][REVEAL_SET]["questions"] if q.get("locks_on_reveal"))
TIERS = [o["value"] for o in Q["scales"][TIER_Q["scale"]]["options"]]
TIER_ABSTAIN = Q["scales"][TIER_Q["scale"]]["abstain"]["value"]
PAIR_SET = next(s for s, ids in BY_SET.items() if ITEMS[ids[0]]["family"] == "tracing_pair")


def questions_of(set_name: str) -> list[dict]:
    return Q["question_sets"][set_name]["questions"]


def first_question(set_name: str, pred: Callable[[dict], bool]) -> dict:
    return next(q for q in questions_of(set_name) if pred(q))


def opt(q: dict, i: int) -> Any:
    return Q["scales"][q["scale"]]["options"][i]["value"]


def five_point(q: dict) -> bool:
    return [o["value"] for o in Q["scales"][q["scale"]]["options"]] == [1, 2, 3, 4, 5]


# A five-point question, a required nominal question and an optional question of the tracing set; a blind
# five-point question and the after-reveal questions of the reveal set. Ids are read from the questions.
PAIR_REALISM = first_question(PAIR_SET, lambda q: five_point(q))
PAIR_OPTIONAL = first_question(PAIR_SET, lambda q: not q["required"] and Q["scales"][q["scale"]]["type"] != "text")
REVEAL_REALISM = first_question(REVEAL_SET, lambda q: five_point(q) and q["phase"] == "blind")
REVEAL_OPTIONAL_BLIND = first_question(REVEAL_SET, lambda q: q["phase"] == "blind" and not q["required"])
PER_ARM_SET, PER_ARM_Q = next((s, q) for s in BY_SET for q in questions_of(s) if q.get("per_arm"))


def full(item_id: str, **overrides: Any) -> dict:
    """Every required blind answer (first option), then the overrides."""
    item = ITEMS[item_id]
    out: dict[str, Any] = {}
    for q in questions_of(item["question_set"]):
        if q["phase"] != "blind" or not q["required"]:
            continue
        keys = ([f"{q['id']}.{a['arm']}" for a in item["display"]["arms"]] if q.get("per_arm") else [q["id"]])
        for k in keys:
            out[k] = opt(q, 0)
    out.update(overrides)
    return out


def after_reveal(item_id: str) -> dict:
    return {q["id"]: opt(q, 0) for q in questions_of(ITEMS[item_id]["question_set"])
            if q["phase"] == "after_reveal" and q["required"]}


class Export:
    """A synthetic export of the app's schema over the real bundle, built event by event."""

    def __init__(self) -> None:
        self.raters: dict[str, str] = {}
        self.assigned: list[tuple[str, str]] = []
        self.events: list[dict] = []
        self.latest: dict[tuple[str, str], dict] = {}
        self.completed: set[tuple[str, str]] = set()  # ratings rate() finished: the app's n_complete
        self.clock = datetime(2026, 10, 12, 9, 0, 0, tzinfo=timezone.utc)

    def rater(self, rid: str, status: str = "active") -> "Export":
        self.raters[rid] = status
        return self

    def _event(self, rid: str, item_id: str, kind: str, answers: dict, notes: str) -> None:
        if (rid, item_id) not in self.assigned:
            self.assigned.append((rid, item_id))
        self.clock += timedelta(seconds=30)
        self.events.append({
            "event_id": f"ev_{len(self.events):016x}", "saved_utc": self.clock.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "rater_id": rid, "item_id": item_id, "question_set": ITEMS[item_id]["question_set"], "event": kind,
            "answers": answers, "notes": notes, "position": 1, "app_version": "verify-app/0.1.0",
            "bundle_sha256": BUNDLE_SHA})

    def save(self, rid: str, item_id: str, answers: dict, notes: str = "") -> "Export":
        self.latest[(rid, item_id)] = dict(answers)
        self._event(rid, item_id, "save", dict(answers), notes)
        return self

    def reveal(self, rid: str, item_id: str) -> "Export":
        self._event(rid, item_id, "reveal", dict(self.latest[(rid, item_id)]), "")
        return self

    def rate(self, rid: str, item_id: str, **overrides: Any) -> "Export":
        """A complete rating: the blind answers, and the reveal step where the item has one."""
        blind = full(item_id, **overrides)
        self.save(rid, item_id, blind)
        if ITEMS[item_id]["reveal"] is not None:
            self.reveal(rid, item_id)
            self.save(rid, item_id, {**blind, **after_reveal(item_id)})
        self.completed.add((rid, item_id))
        return self

    def doc(self) -> dict:
        n_complete = {r: sum(1 for c in self.completed if c[0] == r) for r in self.raters}
        return {
            "schema": "patientwords-verification-ratings/1", "exported_utc": "2026-10-20T02:00:00.000Z",
            "app_version": "verify-app/0.1.0", "bundle_id": BUNDLE["bundle_id"], "bundle_sha256": BUNDLE_SHA,
            "questions_sha256": BUNDLE["questions_sha256"],
            "settings": {"raters_per_item": 2, "max_items_per_rater": 0, "assignment_seed": "20261003",
                         "order_mode": "blocked"},
            "raters": [{"rater_id": r, "status": s, "consent_version": "2", "consent_utc": "2026-10-12T08:00:00.000Z",
                        "n_assigned": sum(1 for a in self.assigned if a[0] == r), "n_complete": n_complete.get(r, 0)}
                       for r, s in sorted(self.raters.items())],
            "assignments": [{"rater_id": r, "item_id": i, "position": n + 1, "order_key": f"{n:013x}", "round": 1,
                             "status": "assigned", "assigned_utc": "2026-10-12T08:30:00.000Z"}
                            for n, (r, i) in enumerate(self.assigned)],
            "events": self.events,
        }


def run(tmp_path: Path, doc: dict | Path, *args: str, out: str = "out") -> tuple[dict, Path]:
    if isinstance(doc, Path):
        path = doc
    else:
        path = tmp_path / "export.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
    out_dir = tmp_path / out
    ivr.main(["--export", str(path), "--out-dir", str(out_dir), "--resamples", "200", *args])
    summary = json.loads(next(out_dir.glob("*.summary.json")).read_text(encoding="utf-8"))
    return summary, out_dir


def refused(tmp_path: Path, doc: dict, code: str, *args: str) -> str:
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, doc, *args)
    message = str(exc.value)
    assert f"REFUSED [{code}]" in message, message
    out_dir = tmp_path / "out"
    assert not out_dir.exists() or not any(out_dir.iterdir()), "a refusal wrote a file"
    return message


def fixture_doc() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ---- Krippendorff's alpha against the published worked examples ---------------------------------------------------

def _columns(rows: list[list[Any]]) -> list[list[Any]]:
    """Units (columns) of a coders-by-units table; None is a missing value."""
    return [[r[u] for r in rows if r[u] is not None] for u in range(len(rows[0]))]


def _coded(units: list[list[Any]], categories: list[Any]) -> list[list[int]]:
    return [[categories.index(v) for v in u] for u in units]


# Krippendorff (2011), section A: two observers, binary data, no missing values.
EXAMPLE_A = [[0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
             [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]]
# Section B: two observers, nominal data, no missing values.
EXAMPLE_B = [list("aabbdcccedda"),
             list("babbbccceddd")]
# Sections C and D: four observers, twelve units, values 1-5, seven values missing.
_ = None
EXAMPLE_C = [[1, 2, 3, 3, 2, 1, 4, 1, 2, _, _, _],
             [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, _, 3],
             [_, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, _],
             [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, _]]


def test_alpha_matches_the_published_binary_and_two_coder_nominal_examples():
    a = ivr.krippendorff_alpha(_coded(_columns(EXAMPLE_A), [0, 1]), 2, "nominal")
    assert round(a, 3) == 0.095
    cats = list("abcde")
    b = ivr.krippendorff_alpha(_coded(_columns(EXAMPLE_B), cats), 5, "nominal")
    assert round(b, 3) == 0.692


def test_alpha_matches_the_published_example_with_missing_values_nominal_and_ordinal():
    units = _coded(_columns(EXAMPLE_C), [1, 2, 3, 4, 5])
    assert round(ivr.krippendorff_alpha(units, 5, "nominal"), 3) == 0.743
    assert round(ivr.krippendorff_alpha(units, 5, "ordinal"), 3) == 0.815


def test_coincidence_matrix_matches_the_published_example():
    o = ivr.coincidence_matrix(_coded(_columns(EXAMPLE_C), [1, 2, 3, 4, 5]), 5)
    third = 1 / 3
    published = [[7, 4 * third, third, third, 0],
                 [4 * third, 10, 4 * third, third, 0],
                 [third, 4 * third, 8, third, 0],
                 [third, third, third, 4, 0],
                 [0, 0, 0, 0, 3]]
    for c in range(5):
        for k in range(5):
            assert o[c][k] == pytest.approx(published[c][k], abs=1e-12), (c, k)
    assert [sum(r) for r in o] == pytest.approx([9, 13, 10, 5, 3])  # n_c; n = 40 pairable values
    # unit 12 holds one value and adds nothing
    assert ivr.unit_coincidences([2]) == []


def test_ordinal_difference_table_matches_the_published_example():
    # Section D: the ranks of example C with one unused rank added (n = 9, 13, 10, 5, 0, 3); the paper prints the
    # upper triangle as the squared bases below.
    d = ivr.delta2([9, 13, 10, 5, 0, 3], "ordinal")
    bases = {(0, 1): 11, (0, 2): 22.5, (0, 3): 30, (0, 4): 32.5, (0, 5): 34, (1, 2): 11.5, (1, 3): 19, (1, 4): 21.5,
             (1, 5): 23, (2, 3): 7.5, (2, 4): 10, (2, 5): 11.5, (3, 4): 2.5, (3, 5): 4, (4, 5): 1.5}
    for (c, k), base in bases.items():
        assert d[c][k] == pytest.approx(base ** 2) and d[k][c] == pytest.approx(base ** 2)
    assert all(d[c][c] == 0 for c in range(6))


def test_alpha_is_undefined_without_pairs_or_with_one_category():
    assert ivr.alpha_from_matrix(ivr.coincidence_matrix([[0], [1]], 2), "nominal")[0] is None
    value, reason = ivr.alpha_from_matrix(ivr.coincidence_matrix([[1, 1], [1, 1, 1]], 3), "ordinal")
    assert value is None and "same category" in reason
    assert ivr.krippendorff_alpha([[0, 0], [1, 1], [2, 2]], 3, "ordinal") == pytest.approx(1.0)


def test_percentile_interpolates_linearly_between_order_statistics():
    vals = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert ivr.percentile(vals, 0.0) == 0.0 and ivr.percentile(vals, 1.0) == 4.0
    assert ivr.percentile(vals, 0.5) == 2.0
    assert ivr.percentile(vals, 0.025) == pytest.approx(0.1)


def test_bootstrap_interval_is_seeded_and_withheld_when_most_resamples_are_undefined():
    import random

    units = [[0, 0, 1], [1, 1], [2, 2, 2], [0, 1], [2, 1, 2], [0, 0]]
    a = ivr.alpha_with_interval(units, 3, "ordinal", 300, random.Random("s|x"))
    b = ivr.alpha_with_interval(units, 3, "ordinal", 300, random.Random("s|x"))
    c = ivr.alpha_with_interval(units, 3, "ordinal", 300, random.Random("s|y"))
    assert a == b and a["ci95"] is not None and a["ci95"] != c["ci95"]
    assert a["resamples_defined"] + a["resamples_undefined"] == 300
    one = ivr.alpha_with_interval([[1, 1]], 3, "nominal", 50, random.Random(1))
    assert one["value"] is None and one["ci95"] is None and "fewer than half" in one["ci_note"]


# ---- the combined tier ----------------------------------------------------------------------------------------------

def test_combined_tier_rule():
    t0, t1, t2, t3 = TIERS
    assert ivr.combine_tiers([t2, t0, t1], TIERS) == (t1, None, False)        # odd: the middle answer
    assert ivr.combine_tiers([t1, t1], TIERS) == (t1, None, False)            # even, middle tiers equal
    assert ivr.combine_tiers([t0, t1], TIERS) == (t1, None, True)             # even split: the more urgent
    assert ivr.combine_tiers([t3, t0, t2, t1], TIERS) == (t2, None, True)
    assert ivr.combine_tiers([t3], TIERS)[0] is None                          # fewer than 2 answers
    assert "fewer than 2" in ivr.combine_tiers([], TIERS)[1]


def test_combined_tier_from_an_export_and_the_proposed_adjudication_file(tmp_path):
    a, b, c = BY_SET[REVEAL_SET][:3]
    t0, t1, _t2, t3 = TIERS
    tid = TIER_Q["id"]
    ex = Export().rater("md02").rater("md03").rater("md04")
    ex.rate("md02", a, **{tid: t0}).rate("md03", a, **{tid: t1})                   # even split -> t1
    ex.rate("md02", b, **{tid: t3}).rate("md03", b, **{tid: TIER_ABSTAIN})         # one answer -> no tier
    ex.rate("md02", c, **{tid: t3}).rate("md03", c, **{tid: t0}).rate("md04", c, **{tid: t1})  # median -> t1
    summary, out = run(tmp_path, ex.doc())
    assert not list(out.glob("*.proposed_adjudication.json")), "written only with the flag"
    rows = {r["item_id"]: r for r in summary["combined_tier"]["items"]}
    assert (rows[a]["tier"], rows[a]["even_split_to_more_urgent"]) == (t1, True)
    assert rows[b]["tier"] is None and rows[b]["answers"] == 1 and rows[b]["abstentions"] == 1
    assert "fewer than 2" in rows[b]["no_tier_reason"]
    assert rows[c]["tier"] == t1 and rows[c]["raters"] == ["md02", "md03", "md04"]
    for iid in (a, c):
        assert rows[iid]["agrees_with_proposed"] == (rows[iid]["tier"] == ITEMS[iid]["reveal"]["proposed_tier"])
    assert summary["combined_tier"]["status"] == ivr.ADJUDICATION_STATUS

    summary, out = run(tmp_path, ex.doc(), "--write-proposed-adjudication", out="out2")
    adj = json.loads(next(out.glob("*.proposed_adjudication.json")).read_text())
    assert adj["status"].startswith("proposed adjudication, not in force")
    assert len(adj["items"]) == len(BY_SET[REVEAL_SET]), "every item with a proposed tier is listed"
    by_id = {x["item_id"]: x for x in adj["items"]}
    assert by_id[a]["id"] == ITEMS[a]["provenance"]["source_id"]
    assert by_id[a]["reference"]["tier"] == t1
    assert by_id[a]["reference"]["adjudicated_by"] == "md02; md03 (median, even split to the more urgent)"
    assert by_id[c]["reference"]["adjudicated_by"] == "md02; md03; md04 (median)"
    assert by_id[b]["reference"] is None and adj["coverage"]["with_tier"] == 2
    # the shape advice_eval.py analyze --stimuli reads: items[].id and an optional reference {tier, adjudicated_by}
    for x in adj["items"]:
        assert isinstance(x["id"], str)
        ref = x["reference"] or {}
        if ref:
            assert ref["tier"] in TIERS and isinstance(ref["adjudicated_by"], str) and ref["adjudicated_by"].strip()


# ---- derivations ----------------------------------------------------------------------------------------------------

def test_current_answers_are_the_latest_save_and_changes_after_the_first_are_counted(tmp_path):
    item = BY_SET[PAIR_SET][0]
    rq, oq = PAIR_REALISM["id"], PAIR_OPTIONAL["id"]
    ex = Export().rater("md02").rater("md03")
    ex.save("md02", item, full(item, **{rq: 2, oq: opt(PAIR_OPTIONAL, 0)}))
    ex.save("md02", item, full(item, **{rq: 4}))                     # realism changed, optional answer cleared
    ex.save("md03", item, full(item, **{rq: 4, oq: opt(PAIR_OPTIONAL, 1)}))
    summary, _ = run(tmp_path, ex.doc())
    changes = summary["answer_changes"][PAIR_SET]
    assert changes[rq] == {"first_given": 2, "changed_after_first": 1, "cleared_after_first": 0}
    assert changes[oq] == {"first_given": 2, "changed_after_first": 0, "cleared_after_first": 1}
    dist = {d["value"]: d["n"] for d in summary["agreement"][PAIR_SET][rq]["distribution"]}
    assert dist[4] == 2 and dist[2] == 0, "the analysis uses the current answers, not the first"


def test_blind_answers_of_a_reveal_item_come_from_the_reveal_event(tmp_path):
    item = BY_SET[REVEAL_SET][0]
    rq, oq = REVEAL_REALISM["id"], REVEAL_OPTIONAL_BLIND["id"]
    ex = Export().rater("md02").rater("md03")
    blind = full(item, **{rq: 1})
    ex.save("md02", item, blind).reveal("md02", item)
    ex.save("md02", item, {**blind, **after_reveal(item), rq: 5, oq: opt(REVEAL_OPTIONAL_BLIND, 0)})
    ex.rate("md03", item, **{rq: 1})
    summary, _ = run(tmp_path, ex.doc())
    dist = {d["value"]: d["n"] for d in summary["agreement"][REVEAL_SET][rq]["distribution"]}
    assert dist[1] == 2 and dist[5] == 0, "the blind answer as of the reveal, not the later change"
    blk = summary["reveal"][REVEAL_SET]
    assert blk["ratings_revealed"] == 2
    assert blk["blind_changed_after_reveal"] == {rq: 1}
    assert blk["blind_first_given_after_reveal"] == {oq: 1}
    unanswered = next(d for d in summary["agreement"][REVEAL_SET][oq]["distribution"] if d.get("unanswered"))
    assert unanswered["n"] == 2, "an answer first given after the reveal is not blind and stays out"
    assert summary["answer_changes"][REVEAL_SET][rq]["changed_after_first"] == 1


def test_only_complete_ratings_enter_the_analysis(tmp_path):
    item = BY_SET[PAIR_SET][0]
    rq = PAIR_REALISM["id"]
    ex = Export().rater("md02").rater("md03").rater("md04")
    ex.rate("md02", item, **{rq: 3}).rate("md03", item, **{rq: 3})
    ex.save("md04", item, {rq: 1})                                   # unfinished
    summary, _ = run(tmp_path, ex.doc())
    rec = summary["agreement"][PAIR_SET][rq]
    assert rec["ratings"] == 2 and {d["value"]: d["n"] for d in rec["distribution"]}[1] == 0
    row = next(r for r in summary["items"] if r["item_id"] == item)
    assert (row["ratings_complete"], row["ratings_unfinished"]) == (2, 1)
    assert summary["coverage"]["by_question_set"][PAIR_SET]["ratings_unfinished"] == 1


def test_item_flag_when_most_physicians_rate_it_unrealistic(tmp_path):
    a, b = BY_SET[PAIR_SET][:2]
    rq = PAIR_REALISM["id"]
    ex = Export().rater("md02").rater("md03").rater("md04")
    ex.rate("md02", a, **{rq: 1}).rate("md03", a, **{rq: 2}).rate("md04", a, **{rq: 5})
    ex.rate("md02", b, **{rq: 2}).rate("md03", b, **{rq: 4})
    summary, _ = run(tmp_path, ex.doc())
    rows = {r["item_id"]: r for r in summary["items"]}
    assert rows[a]["flagged"] and rows[a]["flagged_keys"] == [rq]
    assert rows[a]["five_point"][rq] == {"n": 3, "median": 2, "n_low": 2, "share_low": pytest.approx(2 / 3, abs=1e-6),
                                        "majority_low": True}
    assert not rows[b]["flagged"], "one of two is not a majority"
    assert rows[b]["five_point"][rq]["median"] == 3


def test_named_raters_are_excluded_and_a_removed_rater_is_kept_with_a_warning(tmp_path):
    item = BY_SET[PAIR_SET][0]
    rq = PAIR_REALISM["id"]
    ex = Export().rater("md01", "removed").rater("md02").rater("md03")
    ex.rate("md01", item, **{rq: 1}).rate("md02", item, **{rq: 5}).rate("md03", item, **{rq: 5})
    summary, _ = run(tmp_path, ex.doc())
    assert summary["agreement"][PAIR_SET][rq]["ratings"] == 3
    assert any("md01" in w and "--exclude-rater md01" in w for w in summary["warnings"])
    summary, _ = run(tmp_path, ex.doc(), "--exclude-rater", "md01", out="out2")
    assert summary["agreement"][PAIR_SET][rq]["ratings"] == 2
    assert summary["exclusions"]["excluded_raters"] == ["md01"]
    assert (summary["exclusions"]["events"], summary["exclusions"]["ratings"]) == (1, 1)
    assert not any("md01" in w for w in summary["warnings"])
    assert next(r for r in summary["raters"] if r["rater_id"] == "md01")["included"] is False


# ---- refusals -------------------------------------------------------------------------------------------------------

def _first(doc: dict, pred: Callable[[dict], bool]) -> dict:
    return next(e for e in doc["events"] if pred(e))


def _reveal_pair(doc: dict) -> tuple[int, int]:
    """(index of a reveal, index of a later save of the same rater and item)."""
    for i, e in enumerate(doc["events"]):
        if e["event"] != "reveal":
            continue
        for j in range(i + 1, len(doc["events"])):
            f = doc["events"][j]
            if f["event"] == "save" and (f["rater_id"], f["item_id"]) == (e["rater_id"], e["item_id"]):
                return i, j
    raise AssertionError("the fixture has a reveal followed by a save")


def _save_before_reveal(doc: dict) -> dict:
    i, _ = _reveal_pair(doc)
    r = doc["events"][i]
    return next(e for e in doc["events"][:i] if e["event"] == "save" and
                (e["rater_id"], e["item_id"]) == (r["rater_id"], r["item_id"]))


def _pair_event(doc: dict) -> dict:
    return _first(doc, lambda e: e["question_set"] == PAIR_SET and e["event"] == "save" and
                  PAIR_REALISM["id"] in e["answers"])


def _m_lock(doc):
    i, j = _reveal_pair(doc)
    tid = TIER_Q["id"]
    now = doc["events"][j]["answers"][tid]
    doc["events"][j]["answers"][tid] = next(t for t in TIERS if t != now)


def _m_early(doc):
    e = _save_before_reveal(doc)
    e["answers"].update(after_reveal(e["item_id"]))


def _m_snapshot(doc):
    i, _ = _reveal_pair(doc)
    rq = REVEAL_REALISM["id"]
    doc["events"][i]["answers"][rq] = 1 if doc["events"][i]["answers"].get(rq) != 1 else 2


def _m_duplicate_reveal(doc):
    i, _ = _reveal_pair(doc)
    dup = copy.deepcopy(doc["events"][i])
    dup["event_id"] = "ev_ffffffffffffffff"
    doc["events"].insert(i + 1, dup)


def _m_reveal_without_step(doc):
    e = copy.deepcopy(_pair_event(doc))
    e["event"], e["event_id"] = "reveal", "ev_eeeeeeeeeeeeeeee"
    doc["events"].append(e)


def _m_reveal_first(doc):
    i, _ = _reveal_pair(doc)
    r = doc["events"].pop(i)
    first = next(k for k, e in enumerate(doc["events"]) if (e["rater_id"], e["item_id"]) == (r["rater_id"],
                                                                                              r["item_id"]))
    doc["events"].insert(first, r)


def _m_reveal_incomplete(doc):
    for k, e in enumerate(doc["events"]):
        if e["event"] == "reveal":
            e["answers"].pop(TIER_Q["id"])
            prev = max(j for j in range(k) if doc["events"][j]["event"] == "save" and
                       (doc["events"][j]["rater_id"], doc["events"][j]["item_id"]) == (e["rater_id"], e["item_id"]))
            doc["events"][prev]["answers"].pop(TIER_Q["id"])
            return


REFUSALS = [
    ("schema", lambda d: d.update(schema="patientwords-verification-ratings/2"), "bad_schema"),
    ("bundle not found", lambda d: d.update(bundle_sha256="0" * 64), "bundle_not_found"),
    ("bundle id", lambda d: d.update(bundle_id="vtasks_20990101T000000Z"), "bundle_id_mismatch"),
    ("questions sha", lambda d: d.update(questions_sha256="1" * 64), "questions_sha_mismatch"),
    ("username in a rater row", lambda d: d["raters"][0].update(username="someone"), "pii_field"),
    ("display name at the top", lambda d: d.update(display_name="someone"), "pii_field"),
    ("password hash in an event", lambda d: d["events"][0].update(hash_hex="00"), "pii_field"),
    ("unknown field", lambda d: d["events"][0].update(extra=1), "unexpected_field"),
    ("address-bearing settings field", lambda d: d["settings"].update(digest_email="x"), "pii_field"),
    ("unknown settings field", lambda d: d["settings"].update(digest_hour=2), "unexpected_field"),
    ("username as rater id", lambda d: d["raters"][1].update(rater_id="jsmith"), "rater_id_not_pseudonymous"),
    ("address as rater id", lambda d: d["raters"][1].update(rater_id="someone@example.org"),
     "rater_id_not_pseudonymous"),
    ("address in an event", lambda d: d["events"][0].update(rater_id="someone@example.org"), "pii_value"),
    ("address in a field", lambda d: d["raters"][0].update(consent_version="someone@example.org"), "pii_value"),
    ("unknown rater", lambda d: d["events"][0].update(rater_id="md99"), "unknown_rater"),
    ("duplicate rater", lambda d: d["raters"].append(copy.deepcopy(d["raters"][0])), "duplicate_rater"),
    ("unknown item", lambda d: d["events"][0].update(item_id="vt_000000000000"), "unknown_item"),
    ("unknown item in an assignment", lambda d: d["assignments"][0].update(item_id="vt_000000000000"),
     "unknown_item"),
    ("question set", lambda d: _pair_event(d).update(question_set=REVEAL_SET), "question_set_mismatch"),
    ("unknown question", lambda d: _pair_event(d)["answers"].update(not_a_question=1), "unknown_question"),
    ("unknown version", lambda d: _first(d, lambda e: e["question_set"] == PER_ARM_SET)["answers"].update(
        {f"{PER_ARM_Q['id']}.version_z": opt(PER_ARM_Q, 0)}), "unknown_question"),
    ("string for a number", lambda d: _pair_event(d)["answers"].update({PAIR_REALISM["id"]: "3"}), "bad_value"),
    ("out of scale", lambda d: _pair_event(d)["answers"].update({PAIR_REALISM["id"]: 6}), "bad_value"),
    ("boolean for a number", lambda d: _pair_event(d)["answers"].update({PAIR_REALISM["id"]: True}), "bad_value"),
    ("missing event field", lambda d: d["events"][0].pop("notes"), "bad_export"),
    ("event type", lambda d: d["events"][0].update(event="edit"), "bad_event"),
    ("event id", lambda d: d["events"][0].update(event_id="17"), "bad_event"),
    ("duplicate event id", lambda d: d["events"][1].update(event_id=d["events"][0]["event_id"]),
     "duplicate_event_id"),
    ("answers not an object", lambda d: d["events"][0].update(answers=[]), "bad_answers"),
    ("notes not a string", lambda d: d["events"][0].update(notes=5), "bad_notes"),
    ("notes too long", lambda d: d["events"][0].update(notes="x" * (Q["notes"]["max_length"] + 1)), "notes_too_long"),
    ("time", lambda d: d["events"][0].update(saved_utc="yesterday"), "bad_export"),
    ("position", lambda d: d["events"][0].update(position=0), "bad_event"),
    ("event on another bundle", lambda d: d["events"][3].update(bundle_sha256="2" * 64), "event_bundle_mismatch"),
    ("rater status", lambda d: d["raters"][0].update(status="deleted"), "bad_export"),
    ("raters per item", lambda d: d["settings"].update(raters_per_item=1), "bad_export"),
    ("lock broken", _m_lock, "lock_broken"),
    ("after-reveal answer before the reveal", _m_early, "answer_before_reveal"),
    ("reveal snapshot", _m_snapshot, "reveal_snapshot_mismatch"),
    ("second reveal", _m_duplicate_reveal, "duplicate_reveal"),
    ("reveal on an item without one", _m_reveal_without_step, "reveal_without_step"),
    ("reveal before any save", _m_reveal_first, "reveal_before_save"),
    ("reveal without the blind answers", _m_reveal_incomplete, "reveal_blind_incomplete"),
]


@pytest.mark.parametrize("name,mutate,code", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_refusals_are_named_and_write_nothing(tmp_path, name, mutate, code):
    doc = fixture_doc()
    mutate(doc)
    refused(tmp_path, doc, code)


def test_refuses_a_bundle_file_with_other_bytes(tmp_path):
    other = tmp_path / "tasks_copy.json"
    other.write_bytes(BUNDLE_BYTES + b" ")
    refused(tmp_path, fixture_doc(), "bundle_sha_mismatch", "--bundle", str(other))


def test_refuses_a_questions_file_with_other_bytes_or_content(tmp_path):
    q = tmp_path / "questions.json"
    q.write_text(json.dumps(Q), encoding="utf-8")  # same content, other bytes
    refused(tmp_path, fixture_doc(), "questions_sha_mismatch", "--questions", str(q))
    # a bundle whose copy of the questions differs from the questions file its sha256 names
    bundle = json.loads(BUNDLE_BYTES)
    bundle["questions"]["version"] = "edited"
    fake = tmp_path / "tasks_fake.json"
    fake.write_text(json.dumps(bundle), encoding="utf-8")
    sha = hashlib.sha256(fake.read_bytes()).hexdigest()
    doc = fixture_doc()
    doc["bundle_sha256"] = sha
    for e in doc["events"]:
        e["bundle_sha256"] = sha
    refused(tmp_path, doc, "questions_content_mismatch", "--bundle", str(fake))


def test_refuses_an_unknown_excluded_rater(tmp_path):
    refused(tmp_path, fixture_doc(), "unknown_excluded_rater", "--exclude-rater", "md77")


def test_outputs_are_never_replaced_silently(tmp_path):
    run(tmp_path, FIXTURE, "--exclude-rater", "md01")
    out = tmp_path / "out"
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    run(tmp_path, FIXTURE, "--exclude-rater", "md01")                  # identical rerun: a no-op
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, FIXTURE, "--exclude-rater", "md01", "--seed", "5")
    assert "REFUSED [output_exists]" in str(exc.value)
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    run(tmp_path, FIXTURE, "--exclude-rater", "md01", "--seed", "5", "--overwrite")
    assert json.loads(next(out.glob("*.summary.json")).read_text())["seed"] == 5


# ---- determinism ----------------------------------------------------------------------------------------------------

def test_same_seed_same_bytes_and_the_seed_is_recorded(tmp_path):
    s1, out1 = run(tmp_path, FIXTURE, "--exclude-rater", "md01", "--write-proposed-adjudication", out="a")
    s2, out2 = run(tmp_path, FIXTURE, "--exclude-rater", "md01", "--write-proposed-adjudication", out="b")
    files = sorted(p.name for p in out1.iterdir())
    assert len(files) == 3 and files == sorted(p.name for p in out2.iterdir())
    for name in files:
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name
    assert s1["seed"] == ivr.DEFAULT_SEED and s1["seed_is_default"] is True and s1["resamples"] == 200
    assert s1["inputs"]["export"]["sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert s1["inputs"]["bundle"]["sha256"] == BUNDLE_SHA
    assert s1["inputs"]["questions"]["sha256"] == BUNDLE["questions_sha256"]
    assert s1["script"]["version"] == ivr.SCRIPT_VERSION and len(s1["script"]["sha256"]) == 64
    s3, _ = run(tmp_path, FIXTURE, "--exclude-rater", "md01", "--seed", "11", out="c")
    assert s3["seed"] == 11 and s3["seed_is_default"] is False
    point = lambda s: {(st, k): r["alpha"]["value"] for st, b in s["agreement"].items()  # noqa: E731
                       for k, r in b.items() if "alpha" in r}
    ci = lambda s: {(st, k): r["alpha"]["ci95"] for st, b in s["agreement"].items()  # noqa: E731
                    for k, r in b.items() if "alpha" in r}
    assert point(s1) == point(s3), "the seed moves only the intervals"
    assert ci(s1) != ci(s3)


# ---- integration: an export the app wrote over the real bundle ---------------------------------------------------

def test_synthetic_app_export_matches_the_generators_oracle(tmp_path):
    exp = json.loads(EXPECTED.read_text(encoding="utf-8"))
    summary, out = run(tmp_path, FIXTURE, "--exclude-rater", "md01", "--write-proposed-adjudication")
    assert summary["warnings"] == []
    assert summary["exclusions"]["excluded_raters"] == exp["excluded"] == ["md01"]
    raters = {r["rater_id"]: r for r in summary["raters"]}
    for rid, rec in exp["raters"].items():
        assert raters[rid]["ratings_started"] == rec["started"], rid
        assert raters[rid]["ratings_complete"] == rec["complete"] == exp["app_n_complete"][rid], rid
        assert raters[rid]["recomputed_n_complete_on_assigned_items"] == raters[rid]["app_n_complete"], rid
    assert {r["status"] for r in summary["raters"]} == {"active", "paused", "removed"}
    assert summary["events"]["total"] == exp["n_events"]
    for set_name, cov in summary["coverage"]["by_question_set"].items():
        assert cov["ratings_complete"] == exp["complete_by_set"].get(set_name, 0), set_name
        assert cov["ratings_unfinished"] == exp["incomplete_by_set"].get(set_name, 0), set_name
    for set_name, block in summary["answer_changes"].items():
        for k, c in block.items():
            assert c["changed_after_first"] == exp["changed_after_first"].get(f"{set_name}|{k}", 0), k
            assert c["cleared_after_first"] == exp["cleared_after_first"].get(f"{set_name}|{k}", 0), k
    for set_name, blk in summary["reveal"].items():
        assert blk["blind_changed_after_reveal"] == {k.split("|")[1]: v for k, v in exp["changed_after_reveal"].items()
                                                     if k.startswith(set_name + "|")}
        assert blk["blind_first_given_after_reveal"] == {
            k.split("|")[1]: v for k, v in exp["first_given_after_reveal"].items() if k.startswith(set_name + "|")}
    n_dist = 0
    for set_name, block in summary["agreement"].items():
        for label, rec in block.items():
            if "distribution" not in rec or rec["unit"] != "item":
                continue
            mine = {("__unanswered__" if d.get("unanswered") else json.dumps(d["value"])): d["n"]
                    for d in rec["distribution"] if d["n"]}
            assert mine == exp["distributions"].get(f"{set_name}|{label}", {}), (set_name, label)
            n_dist += 1
    assert n_dist >= 30
    reference = exp["alpha_krippendorff_package"]["values"]
    assert len(reference) >= 30
    for key, ref in reference.items():
        set_name, label = key.split("|")
        rec = summary["agreement"][set_name][label]
        for got, want in ((rec["alpha"]["value"], ref["primary"]),
                          ((rec.get("alpha_abstain_as_category") or {}).get("value"), ref.get("abstain_as_category"))):
            if want is None:
                assert got is None, key
            else:
                assert got == pytest.approx(want, abs=1e-6), key
    for row in summary["combined_tier"]["items"]:
        want = exp["combined_tier"][row["item_id"]]
        assert (row["tier"], row["answers"], row["raters"]) == (want["tier"], want["n"], want["raters"]), row["item_id"]
    assert summary["notes"]["ratings_with_notes"] == exp["notes_nonempty"]

    # nothing a physician typed, no scenario text and no address reaches any output
    doc = fixture_doc()
    typed = {e["notes"] for e in doc["events"] if e["notes"]}
    typed |= {v for e in doc["events"] for v in e["answers"].values() if isinstance(v, str) and len(v) > 20}
    assert typed, "the fixture carries notes and text answers"
    shown = set()
    for item in BUNDLE["items"]:
        for v in ivr_strings(item["display"]):
            if len(v) > 20:
                shown.add(v)
    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not any(t in text for t in typed), f"{path.name} copies a note or a text answer"
        assert not any(s in text for s in shown), f"{path.name} copies scenario text"
        assert "@" not in text, path.name


def ivr_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in ivr_strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in ivr_strings(v)]
    return []
