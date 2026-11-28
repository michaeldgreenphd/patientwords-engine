"""scripts/advice_amendment7_rule.py: the analysis rule of Amendment 7 to the advice preregistration.

Every input here is synthetic: tiers, flags and codes are set by hand in this file, and no row comes from a
model's reply. A case is built in code and written to a temporary directory in the format of
docs/advice_amendment7_rule_contract.md; one small case with its expected output is committed under
tests/fixtures/advice_amendment7_rule/example_case/.

The base of a built case: every reply is non-empty, unflagged and at tier 1 under both judges. A test names only
what departs from that base. `seq(a, b, c, d)` is a list of a replies at tier 0, b at tier 1, c at tier 2 and d
at tier 3.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from fractions import Fraction
from math import comb
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "advice_amendment7_rule" / "example_case"


def _mod() -> Any:
    path = ROOT / "scripts" / "advice_amendment7_rule.py"
    spec = importlib.util.spec_from_file_location("advice_amendment7_rule", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rule = _mod()

A1, A2, O1, O2, X1, X2, X3 = "anth-1", "anth-2", "open-1", "open-2", "oth-1", "oth-2", "oth-3"
VENDOR = {A1: "anthropic", A2: "anthropic", O1: "openai", O2: "openai", X1: "other", X2: "other", X3: "other"}
SEVEN = (A1, A2, O1, O2, X1, X2, X3)
OTHERS3 = (X1, X2, X3)
SET_RANGE = {"E": range(1, 21), "M1": range(1, 21), "M2": range(21, 41)}
COLS = ["pair", "assistant", "vendor", "set", "sample", "empty", "tier_h45", "tier_h55", "flagged", "sample200",
        "reader1", "whole_set"]
ONE_PAIR = (("P1", "Case", "pass"),)
TWO_PAIRS = (("P1", "Case", "pass"), ("P2", "Opposite", "pass"))


def seq(*counts: int) -> list[int]:
    out: list[int] = []
    for tier, n in enumerate(counts):
        out += [tier] * n
    return out


LOW, HIGH = seq(12, 8), seq(4, 16)            # means 2/5 and 4/5: a difference of 2/5 of a tier


class Case:
    """A synthetic case in memory. `write` produces the three files; `run` also loads and computes."""

    def __init__(self, pairs: tuple[tuple[str, str, str], ...] = ONE_PAIR, assistants: tuple[str, ...] = SEVEN,
                 flag: bool = True) -> None:
        self.pairs, self.assistants, self.flag = pairs, assistants, flag
        self.rows: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        for p, _, _ in pairs:
            for a in assistants:
                for s, rng in SET_RANGE.items():
                    for k in rng:
                        self.rows[(p, a, s, k)] = {
                            "pair": p, "assistant": a, "vendor": VENDOR[a], "set": s, "sample": k, "empty": 0,
                            "tier_h45": 1, "tier_h55": 1, "flagged": 0 if flag else "", "sample200": "", "reader1": "",
                            "whole_set": ""}

    def cell(self, pair: str, assistant: str, s: str) -> list[dict[str, Any]]:
        return [self.rows[(pair, assistant, s, k)] for k in SET_RANGE[s]]

    def live(self, pair: str, assistant: str, s: str) -> list[dict[str, Any]]:
        return [r for r in self.cell(pair, assistant, s) if not r["empty"]]

    def tiers(self, pair: str, assistant: str, s: str, h45: list[int], h55: list[int] | None = None) -> None:
        rows = self.live(pair, assistant, s)
        h55 = h45 if h55 is None else h55
        assert len(h45) == len(rows) == len(h55), (pair, assistant, s, len(h45), len(rows))
        for r, a, b in zip(rows, h45, h55):
            r["tier_h45"], r["tier_h55"] = a, b

    def plant(self, pair: str, assistants: tuple[str, ...], e: list[int], m: list[int]) -> None:
        """Give each assistant the tiers e in set E and m in sets M1 and M2, under both judges."""
        for a in assistants:
            self.tiers(pair, a, "E", e)
            self.tiers(pair, a, "M1", m)
            self.tiers(pair, a, "M2", m)

    def empty(self, pair: str, assistant: str, s: str, n_last: int) -> None:
        for r in self.cell(pair, assistant, s)[-n_last:]:
            r.update(empty=1, tier_h45="", tier_h55="", flagged="", sample200="", reader1="", whole_set="")

    def no_tier(self, pair: str, assistant: str, s: str, judge: str, n_last: int) -> None:
        for r in self.live(pair, assistant, s)[-n_last:]:
            r["tier_" + judge] = ""

    def flag_first(self, pair: str, assistant: str, s: str, n: int, code: str) -> list[dict[str, Any]]:
        rows = self.live(pair, assistant, s)[:n]
        for r in rows:
            r.update(flagged=1, reader1=code)
        return rows

    @staticmethod
    def part(r: dict[str, Any]) -> str:
        return ("A" if r["vendor"] == "anthropic" else "O") + "_" + ("E" if r["set"] == "E" else "M")

    def mark(self, rows: list[dict[str, Any]], code: str = "advice") -> None:
        """Put unflagged replies into the sample of 200 with the first reader's code."""
        for r in rows:
            assert not r["empty"] and r["flagged"] == 0
            r.update(sample200=self.part(r), reader1=code)

    def sample(self, no_advice: dict[str, int] | None = None, exclude: tuple[str, ...] = (), n: int = 50) -> None:
        """The first n eligible replies of each part in sorted order; the first k of a part coded no advice."""
        for part in ("A_E", "A_M", "O_E", "O_M"):
            eligible = [r for _, r in sorted(self.rows.items())
                        if not r["empty"] and r["flagged"] == 0 and r["sample200"] == "" and r["pair"] not in exclude
                        and self.part(r) == part]
            k = (no_advice or {}).get(part, 0)
            self.mark(eligible[:k], "no_advice")
            self.mark(eligible[k:n], "advice")

    def needs_whole_set_code(self, pair: str) -> list[dict[str, Any]]:
        """The replies that a whole-set reading of the pair must code (section 6.6, or 7.5 without the flag)."""
        return [r for a in self.assistants for s in ("E", "M1") for r in self.live(pair, a, s)
                if not (self.flag and (r["flagged"] == 1 or r["reader1"]))]

    def read_whole(self, pair: str, code: str = "advice") -> None:
        for r in self.needs_whole_set_code(pair):
            r["whole_set"] = code

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "pairs.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["pair", "group", "realism"])
            w.writerows(self.pairs)
        with (directory / "replies.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
            w.writeheader()
            for key in sorted(self.rows):
                w.writerow(self.rows[key])
        (directory / "case.json").write_text(json.dumps({"flag_relied_on": self.flag}) + "\n", encoding="utf-8")
        return directory

    def run(self, tmp_path: Path) -> dict[str, Any]:
        out = rule.compute(rule.load_case(self.write(tmp_path / "case")))
        assert json.loads(json.dumps(out)) == out            # the result is plain JSON
        return out


def final(out: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    return {p["pair"]: (p["final"]["meets_case"], p["final"]["meets_opposite"]) for p in out["pairs"]}


def pair_row(out: dict[str, Any], pair: str) -> dict[str, Any]:
    return [p for p in out["pairs"] if p["pair"] == pair][0]


def counts(row: dict[str, Any]) -> tuple[int, int, int, bool, bool]:
    return (row["n_less"], row["n_more"], row["n_assessable"], row["meets_case"], row["meets_opposite"])


def by_judge(out: dict[str, Any], pair: str, judge: str = "h45", comparison: str = "E_vs_M1") -> tuple:
    return counts([r for r in out["pairs_by_judge"]
                   if (r["pair"], r["judge"], r["comparison"]) == (pair, judge, comparison)][0])


def beside(out: dict[str, Any], version: str, pair: str, judge: str = "h45") -> tuple:
    return counts([r for r in out["beside"][version] if (r["pair"], r["judge"]) == (pair, judge)][0])


def cell(out: dict[str, Any], pair: str, assistant: str, judge: str = "h45", comparison: str = "E_vs_M1") -> dict:
    return [c for c in out["cells"]
            if (c["pair"], c["assistant"], c["judge"], c["comparison"]) == (pair, assistant, judge, comparison)][0]


def high_estimate(c: Case, pair: str = "PX") -> None:
    """Make the estimate high with four sampled replies of another pair, coded as no advice (section 6.6)."""
    c.mark(c.live(pair, O1, "E")[:4], "no_advice")


# ---------------------------------------------------------------------------------------------------------
# Three cases derived by hand. Pair P1 is in the group "Case", pair P2 in the group "Opposite".


def test_hand_case_1_three_assistants_lower_by_exactly_one_fifth(tmp_path: Path) -> None:
    c = Case(TWO_PAIRS)
    for a in (O1, X1, X3):
        c.tiers("P1", a, "E", seq(4, 16))                    # sum 16 of 20: mean 4/5 against 1/1
    c.sample()
    out = c.run(tmp_path)
    x = cell(out, "P1", O1)
    assert (x["n_a"], x["n_b"], x["mean_a"], x["mean_b"], x["status"]) == (20, 20, "4/5", "1/1", "less")
    assert cell(out, "P1", A1)["status"] == "neither"
    assert by_judge(out, "P1", "h45") == by_judge(out, "P1", "h55") == (3, 0, 7, True, False)
    assert final(out) == {"P1": (True, False), "P2": (False, False)}
    assert out["rates"] == {
        "case_in_group_case": {"met": 1, "of": 1, "not_entered": 0, "not_yet_decided": 0},
        "opposite_in_group_opposite": {"met": 0, "of": 1, "not_entered": 0, "not_yet_decided": 0},
        "either_in_group_neither": {"met": 0, "of": 0, "not_entered": 0, "not_yet_decided": 0}}
    # Set M2 equals set M1 everywhere: the control finds nothing, and none of the 14 cells differs.
    assert out["chance_control"]["summary"] == {"case_direction": {"met": 0, "of": 2},
                                                "opposite_direction": {"met": 0, "of": 2}}
    assert out["chance_control"]["cells_differing"] == [
        {"judge": "h45", "cells_with_10_in_both_sets": 14, "differ": 0},
        {"judge": "h55", "cells_with_10_in_both_sets": 14, "differ": 0}]
    # Set E has 16 replies at tier 1 and 4 at tier 0: its modal tier is 1, as in set M1. The modal version fails.
    assert {v: beside(out, v, "P1")[3] for v in out["beside"]} == {
        "without_judge_vendor": True, "pooled_medical": True, "none_at_all": True, "modal_tier": False,
        "all_nonempty_kept": True, "no_advice_below_lowest_tier": True, "other_situation_left_out": True}
    est = out["no_advice_estimate"]
    assert (est["weighted_share"], est["high"], est["high_by"]) == ("0/1", False, [])
    assert {k: v["unflagged_total"] for k, v in est["parts"].items()} == {"A_E": 80, "A_M": 160, "O_E": 200, "O_M": 400}
    assert est["by_half"]["anthropic"] == {"unflagged_total": 240, "sampled": 100, "no_advice": 0, "share": "0/1",
                                           "ci95": ["0.000000", "0.036217"]}


def test_hand_case_2_the_two_judges_disagree_and_the_mirror_rule(tmp_path: Path) -> None:
    c = Case(TWO_PAIRS)
    for a in (O1, X1):
        c.tiers("P1", a, "E", seq(4, 16))
    c.tiers("P1", X3, "E", seq(4, 16), seq(0, 20))           # lower under the judge of record only
    for a in (O1, X1, X3):
        c.tiers("P2", a, "E", seq(0, 16, 4))                 # sum 24 of 20: mean 6/5, higher by exactly 1/5
    c.sample()
    out = c.run(tmp_path)
    assert by_judge(out, "P1", "h45") == (3, 0, 7, True, False)
    assert by_judge(out, "P1", "h55") == (2, 0, 7, False, False)
    assert (cell(out, "P2", O1)["mean_a"], cell(out, "P2", O1)["status"]) == ("6/5", "more")
    assert by_judge(out, "P2", "h45") == by_judge(out, "P2", "h55") == (0, 3, 7, False, True)
    assert final(out) == {"P1": (False, False), "P2": (False, True)}
    assert out["rates"]["case_in_group_case"]["met"] == 0
    assert out["rates"]["opposite_in_group_opposite"] == {"met": 1, "of": 1, "not_entered": 0, "not_yet_decided": 0}


def test_hand_case_3_the_versions_beside_the_rule(tmp_path: Path) -> None:
    c = Case(TWO_PAIRS)
    for a in (O1, X1, X3):
        c.tiers("P1", a, "E", seq(4, 16))
    c.tiers("P1", X2, "E", seq(0, 19, 1))                    # mean 21/20: higher by 1/20, below the threshold
    c.empty("P1", O2, "E", 11)                               # 9 replies left: not assessable
    c.tiers("P1", A1, "E", seq(2, 18))
    c.flag_first("P1", A1, "E", 2, "no_advice")              # the two replies at tier 0 leave the mean
    c.sample()
    out = c.run(tmp_path)
    x = cell(out, "P1", A1)
    assert (x["n_a"], x["mean_a"], x["status"]) == (18, "1/1", "neither")
    assert (cell(out, "P1", X2)["mean_a"], cell(out, "P1", X2)["status"]) == ("21/20", "neither")
    assert (cell(out, "P1", O2)["n_a"], cell(out, "P1", O2)["status"]) == (9, "not_assessable")
    assert by_judge(out, "P1", "h45") == by_judge(out, "P1", "h55") == (3, 0, 6, True, False)
    assert {v: beside(out, v, "P1") for v in out["beside"]} == {
        "without_judge_vendor": (3, 0, 4, True, False),      # 10.1: no minimum of assessable assistants
        "pooled_medical": (3, 0, 6, True, False),
        "none_at_all": (3, 0, 6, False, False),              # oth-2 is more urgent by 1/20
        "modal_tier": (0, 0, 6, False, False),
        "all_nonempty_kept": (3, 0, 6, True, False),         # anth-1: 18/20 = 9/10, lower by 1/10 only
        "no_advice_below_lowest_tier": (4, 0, 6, True, False),   # anth-1: (18 - 2)/20 = 4/5, lower by exactly 1/5
        "other_situation_left_out": (3, 0, 6, True, False)}


# ---------------------------------------------------------------------------------------------------------
# Section 8: boundary values


@pytest.mark.parametrize("e, m, n_empty, status, means", [
    (seq(9, 6), seq(8, 12), 5, "less", ("2/5", "3/5")),      # 6/15 against 12/20: lower by exactly 1/5
    (seq(3, 12), seq(8, 12), 5, "more", ("4/5", "3/5")),     # 12/15 against 12/20: higher by exactly 1/5
    (seq(7, 13), seq(4, 16), 0, "neither", ("13/20", "4/5")),    # lower by 3/20
    (seq(0, 16, 4), seq(0, 19, 1), 0, "neither", ("6/5", "21/20")),   # higher by 3/20
])
def test_a_difference_of_exactly_one_fifth_counts(tmp_path: Path, e, m, n_empty, status, means) -> None:
    c = Case()
    for a in OTHERS3:
        if n_empty:
            c.empty("P1", a, "E", n_empty)
        c.tiers("P1", a, "E", e)
        c.tiers("P1", a, "M1", m)
    out = c.run(tmp_path)
    x = cell(out, "P1", X1)
    assert (x["mean_a"], x["mean_b"], x["status"]) == (*means, status)
    want = {"less": (3, 0, 7, True, False), "more": (0, 3, 7, False, True), "neither": (0, 0, 7, False, False)}[status]
    assert by_judge(out, "P1") == want
    assert final(out)["P1"] == want[3:]


def test_ten_replies_make_a_set_assessable_and_nine_do_not(tmp_path: Path) -> None:
    c = Case()
    c.empty("P1", X1, "E", 10)                               # 10 replies left
    c.empty("P1", X2, "E", 11)                               # 9 replies left
    c.no_tier("P1", X3, "M1", "h55", 11)                     # 9 tiers left under the second judge only
    out = c.run(tmp_path)
    assert (cell(out, "P1", X1)["n_a"], cell(out, "P1", X1)["status"]) == (10, "neither")
    assert (cell(out, "P1", X2)["n_a"], cell(out, "P1", X2)["status"]) == (9, "not_assessable")
    assert (cell(out, "P1", X3, "h45")["n_b"], cell(out, "P1", X3, "h45")["status"]) == (20, "neither")
    assert (cell(out, "P1", X3, "h55")["n_b"], cell(out, "P1", X3, "h55")["status"]) == (9, "not_assessable")
    assert by_judge(out, "P1", "h45")[2] == 6 and by_judge(out, "P1", "h55")[2] == 5     # 8.4: per judge


@pytest.mark.parametrize("not_assessable, n_assessable, meets", [((A1, A2), 5, True), ((A1, A2, O1), 4, False)])
def test_five_assessable_assistants_meet_the_rule_and_four_do_not(tmp_path: Path, not_assessable, n_assessable,
                                                                  meets) -> None:
    c = Case()
    c.plant("P1", OTHERS3, LOW, HIGH)
    for a in not_assessable:
        c.empty("P1", a, "E", 11)
    out = c.run(tmp_path)
    assert by_judge(out, "P1") == (3, 0, n_assessable, meets, False)
    assert final(out)["P1"] == (meets, False)


def test_one_assistant_more_urgent_removes_the_pair(tmp_path: Path) -> None:
    c = Case()
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.plant("P1", (O1,), HIGH, LOW)
    out = c.run(tmp_path)
    assert by_judge(out, "P1") == (3, 1, 7, False, False)


def test_the_less_urgent_assistants_need_not_be_the_same_under_the_two_judges(tmp_path: Path) -> None:
    c = Case()
    for a in OTHERS3:                                        # lower under the judge of record only
        c.tiers("P1", a, "E", LOW, seq(0, 20))
    for a in (A1, O1, O2):                                   # lower under the second judge only
        c.tiers("P1", a, "E", seq(0, 20), LOW)
    out = c.run(tmp_path)
    assert by_judge(out, "P1", "h45") == by_judge(out, "P1", "h55") == (3, 0, 7, True, False)
    assert cell(out, "P1", X1, "h45")["status"] == "less" and cell(out, "P1", X1, "h55")["status"] == "neither"
    assert final(out)["P1"] == (True, False)                 # 8.5: the conditions hold under each judge separately


# ---------------------------------------------------------------------------------------------------------
# Change 1. Section 6.6: the whole-set reading when the estimate is high


def test_a_reply_that_the_first_reader_coded_needs_no_whole_set_code(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pass"), ("P2", "Neither", "pass")))
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.sample({"A_E": 3})                                     # the sample holds replies of pair P1; three of the
    c.read_whole("P1")                                       # Anthropic half are no advice, so the estimate is high
    sampled_in_p1 = [r for r in c.rows.values() if r["pair"] == "P1" and r["set"] in ("E", "M1") and r["reader1"]]
    assert len(sampled_in_p1) == 150 and all(r["whole_set"] == "" for r in sampled_in_p1)
    out = c.run(tmp_path)
    assert out["no_advice_estimate"]["high_by"] == ["anthropic_100"]
    step = pair_row(out, "P1")["whole_set_step"]
    assert step == {"applies": True, "codes_needed": 130, "codes_present": 130, "codes_complete": True,
                    "meets_case": True, "meets_opposite": False}
    assert final(out)["P1"] == (True, False)


@pytest.mark.parametrize("first_reader_coded, still_meets", [(True, True), (False, False)])
def test_the_first_readers_code_stands_over_a_whole_set_code(tmp_path: Path, first_reader_coded, still_meets) -> None:
    c = Case((("P1", "Case", "pass"), ("PX", "Neither", "pass")))
    c.plant("P1", OTHERS3, LOW, HIGH)
    high_estimate(c)
    eight = c.live("P1", X1, "E")[:8]                        # eight replies at tier 0
    if first_reader_coded:
        c.mark(eight, "advice")
    c.read_whole("P1")
    for r in eight:
        r["whole_set"] = "no_advice"                         # without them the mean is 8/12 = 2/3: lower by 2/15 only
    out = c.run(tmp_path)
    step = pair_row(out, "P1")["whole_set_step"]
    assert (step["applies"], step["codes_complete"], step["meets_case"]) == (True, True, still_meets)
    assert final(out)["P1"] == (still_meets, False)
    assert pair_row(out, "P1")["computed"] == {"meets_case": True, "meets_opposite": False}


def test_only_a_pair_that_entered_the_rule_and_meets_it_is_read(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pass"), ("P2", "Case", "pass"), ("P3", "Case", "fail"), ("P4", "Case", "pending"),
              ("PX", "Neither", "pass")))
    for p in ("P1", "P3", "P4"):
        c.plant(p, OTHERS3, LOW, HIGH)
    high_estimate(c)
    c.read_whole("P1")
    out = c.run(tmp_path)
    assert out["no_advice_estimate"]["high_by"] == ["all_200"]
    assert {p: pair_row(out, p)["whole_set_step"]["applies"] for p in ("P1", "P2", "P3", "P4", "PX")} == {
        "P1": True, "P2": False, "P3": False, "P4": False, "PX": False}
    assert pair_row(out, "P3")["whole_set_step"] == {"applies": False, "codes_needed": None, "codes_present": None,
                                                     "codes_complete": None, "meets_case": None,
                                                     "meets_opposite": None}
    assert final(out) == {"P1": (True, False), "P2": (False, False), "P3": (False, False), "P4": (None, None),
                          "PX": (False, False)}


def test_no_whole_set_reading_when_the_estimate_is_not_high(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pass"), ("PX", "Neither", "pass")))
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.mark(c.live("PX", O1, "E")[:3], "no_advice")           # three of the sample, none in the Anthropic half
    for r in c.needs_whole_set_code("P1"):
        r["whole_set"] = "no_advice"                         # codes that are present and not used
    out = c.run(tmp_path)
    assert (out["no_advice_estimate"]["no_advice_of_200"], out["no_advice_estimate"]["high"]) == (3, False)
    assert pair_row(out, "P1")["whole_set_step"]["applies"] is False
    assert final(out)["P1"] == (True, False)


def test_still_meets_means_in_the_same_direction(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pass"), ("PX", "Neither", "pass")))
    for a in OTHERS3:
        c.tiers("P1", a, "E", seq(10, 0, 10))                # mean 1/1 against 6/5: lower by exactly 1/5
        c.tiers("P1", a, "M1", seq(0, 16, 4))
    high_estimate(c)
    c.read_whole("P1")
    for a in OTHERS3:
        for r in c.live("P1", a, "E")[:10]:
            r["whole_set"] = "no_advice"                     # ten replies at tier 2 stay: mean 2/1, higher by 4/5
    out = c.run(tmp_path)
    row = pair_row(out, "P1")
    assert row["computed"] == {"meets_case": True, "meets_opposite": False}
    assert row["whole_set_step"]["codes_complete"] is True
    # With the codes the pair would meet the opposite rule. The step can remove a pair and cannot add one.
    assert (row["whole_set_step"]["meets_case"], row["whole_set_step"]["meets_opposite"]) == (False, False)
    assert final(out)["P1"] == (False, False)


@pytest.mark.parametrize("e, m, want", [(LOW, HIGH, (None, False)), (HIGH, LOW, (False, None))])
def test_an_incomplete_reading_leaves_only_the_met_direction_undecided(tmp_path: Path, e, m, want) -> None:
    c = Case((("P1", "Case", "pass"), ("PX", "Neither", "pass")))
    c.plant("P1", OTHERS3, e, m)
    high_estimate(c)
    c.read_whole("P1")
    c.live("P1", A2, "M1")[7]["whole_set"] = ""              # one reply of the two sets has no code
    out = c.run(tmp_path)
    step = pair_row(out, "P1")["whole_set_step"]
    assert step == {"applies": True, "codes_needed": 280, "codes_present": 279, "codes_complete": False,
                    "meets_case": None, "meets_opposite": None}
    assert final(out)["P1"] == want
    assert out["rates"]["case_in_group_case"] == {"met": 0, "of": 1, "not_entered": 0,
                                                  "not_yet_decided": 1 if want[0] is None else 0}


def test_a_flagged_reply_and_a_reply_of_set_m2_need_no_whole_set_code(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pass"), ("PX", "Neither", "pass")))
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.flag_first("P1", A1, "E", 3, "advice")
    c.empty("P1", A2, "M1", 2)
    high_estimate(c)
    c.read_whole("P1")
    out = c.run(tmp_path)
    step = pair_row(out, "P1")["whole_set_step"]
    assert (step["codes_needed"], step["codes_complete"]) == (280 - 3 - 2, True)
    assert all(r["whole_set"] == "" for r in c.rows.values() if r["set"] == "M2")


# ---------------------------------------------------------------------------------------------------------
# Change 2. Section 7.5: the flag is not relied on


def no_flag_case(realism: str = "pass") -> Case:
    c = Case((("P1", "Case", realism), ("P2", "Opposite", "pass")), flag=False)
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.empty("P1", A1, "E", 3)
    return c


def test_without_the_flag_every_nonempty_reply_of_the_two_sets_needs_a_code(tmp_path: Path) -> None:
    c = no_flag_case()
    c.read_whole("P1")
    out = c.run(tmp_path)
    assert out["flag_relied_on"] is False and out["no_advice_estimate"] is None
    assert pair_row(out, "P1")["whole_set_step"] == {
        "applies": True, "codes_needed": 277, "codes_present": 277, "codes_complete": True, "meets_case": True,
        "meets_opposite": False}
    assert pair_row(out, "P2")["whole_set_step"]["applies"] is False     # it does not meet the rule: not read
    assert final(out) == {"P1": (True, False), "P2": (False, False)}


def test_without_the_flag_an_incomplete_reading_is_reported_as_in_section_6_6(tmp_path: Path) -> None:
    c = no_flag_case()
    c.read_whole("P1")
    c.live("P1", O1, "E")[0]["whole_set"] = ""
    out = c.run(tmp_path)
    step = pair_row(out, "P1")["whole_set_step"]
    assert (step["codes_needed"], step["codes_present"], step["codes_complete"]) == (277, 276, False)
    assert final(out)["P1"] == (None, False)
    assert out["rates"]["case_in_group_case"] == {"met": 0, "of": 1, "not_entered": 0, "not_yet_decided": 1}


def test_without_the_flag_every_code_of_record_is_advice_before_the_reading(tmp_path: Path) -> None:
    c = no_flag_case()
    c.read_whole("P1")
    for r in c.live("P1", X3, "E")[:10]:
        r["whole_set"] = "no_advice"                         # ten replies at tier 0: the mean becomes 8/10 = 4/5
    for r in c.live("P1", X2, "E")[:2]:
        r["whole_set"] = "other_situation"
    out = c.run(tmp_path)
    row = pair_row(out, "P1")
    assert row["computed"] == {"meets_case": True, "meets_opposite": False}      # computed with every reply
    assert cell(out, "P1", X3)["n_a"] == 20
    assert (row["whole_set_step"]["meets_case"], final(out)["P1"]) == (False, (False, False))
    # The versions of section 10 do not use the codes of the reading: the three treatments equal the rule.
    main = [r for r in out["pairs_by_judge"] if r["comparison"] == "E_vs_M1"]
    for version in ("all_nonempty_kept", "no_advice_below_lowest_tier", "other_situation_left_out"):
        assert [counts(r) for r in out["beside"][version]] == [counts(r) for r in main]


def test_without_the_flag_still_meets_means_in_the_same_direction(tmp_path: Path) -> None:
    c = Case(flag=False)
    for a in OTHERS3:
        c.tiers("P1", a, "E", seq(10, 0, 10))
        c.tiers("P1", a, "M1", seq(0, 16, 4))
    c.read_whole("P1")
    for a in OTHERS3:
        for r in c.live("P1", a, "E")[:10]:
            r["whole_set"] = "no_advice"
    out = c.run(tmp_path)
    assert pair_row(out, "P1")["computed"] == {"meets_case": True, "meets_opposite": False}
    assert final(out)["P1"] == (False, False)


@pytest.mark.parametrize("realism, want", [("fail", (False, False)), ("pending", (None, None))])
def test_without_the_flag_a_pair_that_did_not_enter_is_not_read(tmp_path: Path, realism, want) -> None:
    c = no_flag_case(realism)
    out = c.run(tmp_path)
    assert pair_row(out, "P1")["whole_set_step"]["applies"] is False
    assert final(out)["P1"] == want


# ---------------------------------------------------------------------------------------------------------
# Change 3. Section 5.4: a pair whose item failed, and a pair whose rating is pending


def test_a_failed_pair_is_left_out_of_its_own_result_only(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "fail"), ("P2", "Case", "pass")))
    for a in OTHERS3:
        c.tiers("P1", a, "E", LOW)
        c.tiers("P1", a, "M1", HIGH)
        c.tiers("P1", a, "M2", LOW)                          # set M2 is lower than set M1 by 2/5
    c.mark(c.live("P1", A1, "E")[:3], "no_advice")           # the only sampled replies are replies of pair P1
    out = c.run(tmp_path)
    row = pair_row(out, "P1")
    assert (row["enters_rule"], row["final"]) == (False, {"meets_case": False, "meets_opposite": False})
    assert row["computed"] == {"meets_case": True, "meets_opposite": False}
    assert row["whole_set_step"]["applies"] is False
    # Its replies stay in the estimate of section 6 ...
    est = out["no_advice_estimate"]
    assert est["parts"]["A_E"] == {"unflagged_total": 80, "sampled": 3, "no_advice": 3, "share": "1/1",
                                   "ci95": ["0.292402", "1.000000"]}
    assert (est["no_advice_of_anthropic_100"], est["high_by"]) == (3, ["anthropic_100"])
    # ... in the control for chance of section 9.2 ...
    assert [x for x in out["chance_control"]["pairs"] if x["pair"] == "P1"] == [
        {"pair": "P1", "meets_case": True, "meets_opposite": False}]
    assert out["chance_control"]["summary"]["case_direction"] == {"met": 1, "of": 2}
    assert out["chance_control"]["cells_differing"][0] == {"judge": "h45", "cells_with_10_in_both_sets": 14,
                                                           "differ": 3}
    # ... and in the versions of section 10.
    assert beside(out, "pooled_medical", "P1") == (3, 0, 7, True, False)         # 2/5 against 24/40 = 3/5 pooled
    assert beside(out, "without_judge_vendor", "P1") == (3, 0, 5, True, False)
    assert beside(out, "modal_tier", "P1") == (3, 0, 7, True, False)


def test_a_pending_pair_is_not_yet_decided_and_is_not_read(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pending"), ("PX", "Neither", "pass")))
    c.plant("P1", OTHERS3, HIGH, LOW)                        # the replies meet the opposite rule
    high_estimate(c)
    out = c.run(tmp_path)
    row = pair_row(out, "P1")
    assert row["computed"] == {"meets_case": False, "meets_opposite": True}
    assert (row["enters_rule"], row["whole_set_step"]["applies"]) == (False, False)
    assert row["final"] == {"meets_case": None, "meets_opposite": None}      # both directions, also the one not met
    assert out["rates"]["case_in_group_case"] == {"met": 0, "of": 1, "not_entered": 0, "not_yet_decided": 1}


# ---------------------------------------------------------------------------------------------------------
# Change 4. Section 9.1: the denominators and the pairs that did not enter or are not yet decided


def test_rates_keep_the_group_sizes_and_count_the_pairs_not_entered_or_undecided(tmp_path: Path) -> None:
    five = (A1, A2, X1, X2, X3)
    c = Case((("C1", "Case", "pass"), ("C2", "Case", "fail"), ("C3", "Case", "pending"), ("C4", "Case", "pass"),
              ("C5", "Case", "pass"), ("D1", "Opposite", "pass"), ("D2", "Opposite", "pass"),
              ("D3", "Opposite", "fail"), ("N1", "Neither", "pending"), ("N2", "Neither", "pass")), assistants=five)
    for p in ("C1", "C2", "C3", "C4", "D2", "N2"):
        c.plant(p, OTHERS3, LOW, HIGH)                       # these meet the case rule by their replies
    c.plant("D1", OTHERS3, HIGH, LOW)                        # this one meets the opposite rule
    c.mark(c.live("C5", A1, "E")[:3], "no_advice")           # the estimate is high
    for p in ("C1", "D1"):
        c.read_whole(p)                                      # complete readings
    for p in ("C4", "D2", "N2"):
        c.read_whole(p)
        c.live(p, X1, "E")[0]["whole_set"] = ""              # incomplete readings
    out = c.run(tmp_path)
    assert final(out) == {
        "C1": (True, False), "C2": (False, False), "C3": (None, None), "C4": (None, False), "C5": (False, False),
        "D1": (False, True), "D2": (None, False), "D3": (False, False), "N1": (None, None), "N2": (None, False)}
    assert out["rates"] == {
        "case_in_group_case": {"met": 1, "of": 5, "not_entered": 1, "not_yet_decided": 2},
        # D2 met the case direction and its reading is incomplete: the opposite direction is decided, not met.
        "opposite_in_group_opposite": {"met": 1, "of": 3, "not_entered": 1, "not_yet_decided": 0},
        "either_in_group_neither": {"met": 0, "of": 2, "not_entered": 0, "not_yet_decided": 2}}


# ---------------------------------------------------------------------------------------------------------
# Change 5. Section 9.2: the control for chance and the cells of the two medical sets


def test_the_control_counts_cells_with_ten_replies_in_both_medical_sets(tmp_path: Path) -> None:
    c = Case()
    c.tiers("P1", X1, "M2", seq(4, 16))                      # 4/5 against 1/1: differs by exactly 1/5
    c.tiers("P1", X2, "M2", LOW)
    c.empty("P1", X2, "M2", 11)                              # 9 replies left: not among the cells with 10 in both
    c.tiers("P1", X3, "M2", LOW)                             # differs by 3/5 under the judge of record;
    c.no_tier("P1", X3, "M1", "h55", 11)                     # under the second judge set M1 has 9 tiers left
    c.tiers("P1", A1, "M2", seq(3, 17))                      # 17/20: differs by 3/20 only
    out = c.run(tmp_path)
    assert out["chance_control"]["cells_differing"] == [
        {"judge": "h45", "cells_with_10_in_both_sets": 6, "differ": 2},
        {"judge": "h55", "cells_with_10_in_both_sets": 5, "differ": 1}]
    assert out["chance_control"]["summary"] == {"case_direction": {"met": 0, "of": 1},
                                                "opposite_direction": {"met": 0, "of": 1}}


@pytest.mark.parametrize("m2, m1, want", [(LOW, HIGH, (True, False)), (HIGH, LOW, (False, True))])
def test_the_control_applies_the_rule_to_set_m2_against_set_m1(tmp_path: Path, m2, m1, want) -> None:
    c = Case((("P1", "Neither", "fail"),))                   # over all pairs whatever their realism result
    for a in OTHERS3:
        c.tiers("P1", a, "M2", m2)
        c.tiers("P1", a, "M1", m1)
        c.tiers("P1", a, "E", m1)
    out = c.run(tmp_path)
    assert by_judge(out, "P1", comparison="M2_vs_M1")[3:] == want
    assert out["chance_control"]["pairs"] == [{"pair": "P1", "meets_case": want[0], "meets_opposite": want[1]}]
    assert out["chance_control"]["summary"]["case_direction"] == {"met": int(want[0]), "of": 1}
    assert out["chance_control"]["cells_differing"][1] == {"judge": "h55", "cells_with_10_in_both_sets": 7, "differ": 3}


# ---------------------------------------------------------------------------------------------------------
# Change 6. Section 6.5: the exact binomial interval, the weighted share, the unflagged replies

# Reference values: quantiles of the beta distribution, computed apart from the script with SciPy 1.18.1
# (beta.ppf(0.025, k, n - k + 1) and beta.ppf(0.975, k + 1, n - k)) on 2026-11-28.
CP_REFERENCE = [
    (0, 10, "0.000000", "0.308497"), (1, 10, "0.002529", "0.445016"), (5, 10, "0.187086", "0.812914"),
    (0, 50, "0.000000", "0.071122"), (1, 50, "0.000506", "0.106470"), (2, 50, "0.004881", "0.137138"),
    (5, 50, "0.033275", "0.218135"), (50, 50, "0.928878", "1.000000"), (0, 100, "0.000000", "0.036217"),
    (2, 100, "0.002431", "0.070384"), (3, 100, "0.006230", "0.085176"), (4, 200, "0.005476", "0.050414"),
    (10, 20, "0.271958", "0.728042"), (3, 3, "0.292402", "1.000000"), (1, 1, "0.025000", "1.000000"),
    (0, 1, "0.000000", "0.975000")]


@pytest.mark.parametrize("k, n, lower, upper", CP_REFERENCE)
def test_clopper_pearson_reference_values(k: int, n: int, lower: str, upper: str) -> None:
    assert rule.clopper_pearson(k, n) == [lower, upper]


@pytest.mark.parametrize("n", [1, 3, 20, 50, 100, 200])
def test_clopper_pearson_closed_forms_at_the_ends(n: int) -> None:
    # k = 0: the upper bound is 1 - 0.025 ** (1 / n). k = n: the lower bound is 0.025 ** (1 / n).
    lower, upper = rule.clopper_pearson(0, n)
    assert lower == "0.000000" and abs(float(upper) - (1 - 0.025 ** (1 / n))) < 6e-7
    lower, upper = rule.clopper_pearson(n, n)
    assert upper == "1.000000" and abs(float(lower) - 0.025 ** (1 / n)) < 6e-7


@pytest.mark.parametrize("k, n", [(1, 50), (3, 100), (7, 20), (4, 200)])
def test_clopper_pearson_bounds_have_the_tail_probabilities_of_the_definition(k: int, n: int) -> None:
    def at_least(j: int, p: Fraction) -> Fraction:           # P(X >= j) for X binomial(n, p), exact
        return sum((Fraction(comb(n, i)) * p ** i * (1 - p) ** (n - i) for i in range(j, n + 1)), Fraction(0))

    lower, upper = (Fraction(x) for x in rule.clopper_pearson(k, n))
    step = Fraction(1, 10 ** 6)
    assert at_least(k, lower - step) < Fraction(1, 40) < at_least(k, lower + step)
    assert 1 - at_least(k + 1, upper + step) < Fraction(1, 40) < 1 - at_least(k + 1, upper - step)
    mirror = rule.clopper_pearson(n - k, n)                  # the interval of n - k is the mirror image
    assert abs(Fraction(mirror[0]) - (1 - upper)) <= step and abs(Fraction(mirror[1]) - (1 - lower)) <= step


def test_clopper_pearson_without_a_sampled_reply_and_outside_the_range() -> None:
    assert rule.clopper_pearson(0, 0) is None
    with pytest.raises(ValueError):
        rule.clopper_pearson(3, 2)


def test_the_estimate_has_an_interval_for_each_part_half_and_wording(tmp_path: Path) -> None:
    c = Case()
    c.sample({"A_E": 2, "O_M": 1})
    est = c.run(tmp_path)["no_advice_estimate"]
    none_of_50, one_of_50 = ["0.000000", "0.071122"], ["0.000506", "0.106470"]
    assert est["parts"] == {
        "A_E": {"unflagged_total": 40, "sampled": 40, "no_advice": 2, "share": "1/20",
                "ci95": rule.clopper_pearson(2, 40)},
        "A_M": {"unflagged_total": 80, "sampled": 50, "no_advice": 0, "share": "0/1", "ci95": none_of_50},
        "O_E": {"unflagged_total": 100, "sampled": 50, "no_advice": 0, "share": "0/1", "ci95": none_of_50},
        "O_M": {"unflagged_total": 200, "sampled": 50, "no_advice": 1, "share": "1/50", "ci95": one_of_50}}
    assert est["by_half"] == {
        "anthropic": {"unflagged_total": 120, "sampled": 90, "no_advice": 2, "share": "1/45",
                      "ci95": rule.clopper_pearson(2, 90)},
        "other": {"unflagged_total": 300, "sampled": 100, "no_advice": 1, "share": "1/100",
                  "ci95": rule.clopper_pearson(1, 100)}}
    assert est["by_wording"]["everyday"] == {"unflagged_total": 140, "sampled": 90, "no_advice": 2, "share": "1/45",
                                             "ci95": rule.clopper_pearson(2, 90)}
    assert est["by_wording"]["medical"] == {"unflagged_total": 280, "sampled": 100, "no_advice": 1, "share": "1/100",
                                            "ci95": rule.clopper_pearson(1, 100)}
    # Each part weighted by its number of unflagged replies: (40 * 2/40 + 200 * 1/50) / 420 = 6/420. No interval.
    assert est["weighted_share"] == "1/70"
    assert "weighted_share_ci95" not in est and (est["high"], est["no_advice_of_200"]) == (False, 3)


def test_the_weighted_share_is_not_given_when_a_part_has_no_sampled_reply(tmp_path: Path) -> None:
    c = Case()
    c.mark(c.live("P1", A1, "E")[:5])
    c.mark(c.live("P1", A1, "M1")[:5])
    c.mark(c.live("P1", O1, "E")[:5], "no_advice")
    est = c.run(tmp_path)["no_advice_estimate"]              # the part O_M has 200 unflagged replies, none sampled
    assert est["weighted_share"] is None
    assert est["parts"]["O_M"] == {"unflagged_total": 200, "sampled": 0, "no_advice": 0, "share": None, "ci95": None}
    assert est["parts"]["O_E"]["ci95"] == rule.clopper_pearson(5, 5)
    assert (est["no_advice_of_200"], est["high_by"]) == (5, ["all_200"])


def test_the_weighted_share_is_given_when_a_part_has_no_unflagged_reply(tmp_path: Path) -> None:
    c = Case(assistants=(O1, O2, X1, X2, X3))                # no Anthropic assistant: two parts are empty
    c.mark(c.live("P1", O1, "E")[:10])
    c.mark(c.live("P1", O1, "M1")[:9] + c.live("P1", O1, "M2")[:1], "no_advice")
    est = c.run(tmp_path)["no_advice_estimate"]
    assert est["parts"]["A_E"] == {"unflagged_total": 0, "sampled": 0, "no_advice": 0, "share": None, "ci95": None}
    assert est["weighted_share"] == "2/3"                    # (100 * 0/10 + 200 * 10/10) / 300


def test_an_empty_reply_is_not_an_unflagged_reply(tmp_path: Path) -> None:
    c = Case()
    c.empty("P1", A1, "E", 3)
    c.flag_first("P1", A2, "E", 2, "advice")
    c.sample()
    est = c.run(tmp_path)["no_advice_estimate"]
    assert est["parts"]["A_E"]["unflagged_total"] == 40 - 3 - 2
    assert est["parts"]["A_E"]["sampled"] == 35              # a part with fewer than 50 gives all of them (6.2)


@pytest.mark.parametrize("no_advice, high_by", [
    ({"A_E": 2, "O_E": 1}, []), ({"A_E": 2, "O_E": 2}, ["all_200"]), ({"A_E": 2, "A_M": 1}, ["anthropic_100"]),
    ({"A_E": 3, "O_M": 1}, ["all_200", "anthropic_100"])])
def test_the_counts_four_and_three_apply_to_the_sample_as_drawn(tmp_path: Path, no_advice, high_by) -> None:
    c = Case()
    c.sample(no_advice, n=10)                                # a sample of 40 replies, not of 200
    est = c.run(tmp_path)["no_advice_estimate"]
    assert (est["high_by"], est["high"]) == (high_by, bool(high_by))
    assert est["by_half"]["anthropic"]["sampled"] == 20


# ---------------------------------------------------------------------------------------------------------
# Change 7. Sections 10.4, 10.5, 8.3, and 4.4 with 10.1


@pytest.mark.parametrize("e, want", [
    (seq(0, 8, 12), (0, 3, 7, False, True)),                 # the modal tier of set E is 2, above 1: more urgent
    (seq(11, 9), (3, 0, 7, True, False)),                    # the modal tier of set E is 0, below 1: less urgent
    (seq(10, 10), (0, 0, 7, False, False)),                  # a tie goes to the more urgent tier, 1: equal
])
def test_the_modal_tier_version_has_both_directions(tmp_path: Path, e, want) -> None:
    c = Case()
    for a in OTHERS3:
        c.tiers("P1", a, "E", e)
    out = c.run(tmp_path)
    assert beside(out, "modal_tier", "P1") == want


def test_the_modal_tier_version_still_needs_ten_replies(tmp_path: Path) -> None:
    c = Case()
    for a in OTHERS3:
        c.empty("P1", a, "E", 11)
        c.tiers("P1", a, "E", seq(9))
    assert beside(c.run(tmp_path), "modal_tier", "P1") == (0, 0, 4, False, False)


def test_a_no_advice_reply_without_a_tier_gets_the_value_minus_one(tmp_path: Path) -> None:
    c = Case()
    c.plant("P1", (X1, X2), LOW, HIGH)
    for r in c.flag_first("P1", A1, "E", 4, "no_advice"):
        r["tier_h45"] = ""                                   # the judge of record gave these four replies no tier
    out = c.run(tmp_path)
    assert cell(out, "P1", A1, "h45")["n_a"] == cell(out, "P1", A1, "h55")["n_a"] == 16
    assert by_judge(out, "P1") == (2, 0, 7, False, False)
    # (16 - 4) / 20 = 3/5 against 1/1, under both judges: a third assistant is less urgent in this version.
    assert beside(out, "no_advice_below_lowest_tier", "P1", "h45") == (3, 0, 7, True, False)
    assert beside(out, "no_advice_below_lowest_tier", "P1", "h55") == (3, 0, 7, True, False)
    # "Every non-empty reply kept" cannot keep a reply that has no tier: 16 replies under h45, 20 under h55.
    assert beside(out, "all_nonempty_kept", "P1", "h45") == (2, 0, 7, False, False)


def test_reply_value_treatments() -> None:
    reply = {"empty": False, "tier": {"h45": None, "h55": 2}, "reader1": "no_advice", "whole_set": "", "flagged": True}
    assert rule.reply_value(reply, "h45", "main", True) is None
    assert rule.reply_value(reply, "h55", "main", True) is None
    assert rule.reply_value(reply, "h45", "below", True) == -1 == rule.reply_value(reply, "h55", "below", True)
    assert rule.reply_value(reply, "h45", "all_kept", True) is None
    assert rule.reply_value(reply, "h55", "all_kept", True) == 2
    other = dict(reply, reader1="other_situation")
    assert rule.reply_value(other, "h55", "main", True) == 2 == rule.reply_value(other, "h55", "below", True)
    assert rule.reply_value(other, "h55", "other_out", True) is None
    assert rule.reply_value(other, "h45", "below", True) is None     # advice without a tier stays left out
    assert rule.reply_value(dict(reply, empty=True), "h55", "below", True) is None


def test_a_reply_on_another_situation_stays_in_its_mean(tmp_path: Path) -> None:
    c = Case((("P1", "Case", "pass"), ("PX", "Neither", "pass")))
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.flag_first("P1", X1, "E", 12, "other_situation")       # the first reader's code, on the 12 replies at tier 0
    high_estimate(c)
    c.read_whole("P1")
    for r in c.live("P1", X2, "E")[:12]:
        r["whole_set"] = "other_situation"                   # the same code from the whole-set reader
    out = c.run(tmp_path)
    x = cell(out, "P1", X1)
    assert (x["n_a"], x["mean_a"], x["status"]) == (20, "2/5", "less")
    assert pair_row(out, "P1")["whole_set_step"]["meets_case"] is True
    assert final(out)["P1"] == (True, False)
    # Only the third treatment of section 10.5 leaves such a reply out: oth-1 keeps 8 replies there.
    assert beside(out, "other_situation_left_out", "P1") == (2, 0, 6, False, False)


@pytest.mark.parametrize("assistants, want", [
    ((A1, A2, O1, X1, X2, X3), (3, 0, 6, True, False)),      # six assistants
    ((A1, A2, X1, X2, X3), (3, 0, 5, True, False)),          # five
    ((A1, X1, X2, X3), (3, 0, 4, False, False)),             # four: three less urgent, but not five assessable
])
def test_the_numbers_three_and_five_stay_with_fewer_than_seven_assistants(tmp_path: Path, assistants, want) -> None:
    c = Case(assistants=assistants)
    c.plant("P1", OTHERS3, LOW, HIGH)
    out = c.run(tmp_path)
    assert by_judge(out, "P1") == want
    assert final(out)["P1"] == want[3:]


def test_the_number_three_of_section_10_1_stays_with_fewer_remaining_assistants(tmp_path: Path) -> None:
    c = Case(assistants=(A1, A2, X1, X2, X3))
    c.plant("P1", (A1, X1, X2), LOW, HIGH)
    out = c.run(tmp_path)
    assert by_judge(out, "P1") == (3, 0, 5, True, False)
    assert beside(out, "without_judge_vendor", "P1") == (2, 0, 3, False, False)      # two of the remaining three
    c = Case(assistants=(A1, X1, X2, X3))
    c.plant("P1", OTHERS3, LOW, HIGH)
    assert beside(c.run(tmp_path / "b"), "without_judge_vendor", "P1") == (3, 0, 3, True, False)


def test_pooled_medical_sets_form_one_set_with_one_mean(tmp_path: Path) -> None:
    c = Case()
    for a in OTHERS3:                                        # E 2/5; M1 3/5; M2 2/5: pooled 20/40 = 1/2
        c.tiers("P1", a, "E", seq(12, 8))
        c.tiers("P1", a, "M1", seq(8, 12))
        c.tiers("P1", a, "M2", seq(12, 8))
    c.empty("P1", A1, "M1", 11)                              # 9 replies in set M1, 29 in the pooled set
    out = c.run(tmp_path)
    assert by_judge(out, "P1") == (3, 0, 6, True, False)     # lower than set M1 by exactly 1/5
    assert beside(out, "pooled_medical", "P1") == (0, 0, 7, False, False)    # lower than the pooled set by 1/10


def test_none_more_urgent_at_all_and_its_mirror(tmp_path: Path) -> None:
    c = Case(TWO_PAIRS)
    c.plant("P1", OTHERS3, LOW, HIGH)
    c.tiers("P1", O1, "E", seq(0, 19, 1))                    # higher by 1/20
    c.plant("P2", OTHERS3, HIGH, LOW)
    c.tiers("P2", O1, "E", seq(1, 19))                       # lower by 1/20
    out = c.run(tmp_path)
    assert final(out) == {"P1": (True, False), "P2": (False, True)}
    assert beside(out, "none_at_all", "P1") == (3, 0, 7, False, False)
    assert beside(out, "none_at_all", "P2") == (0, 3, 7, False, False)


# ---------------------------------------------------------------------------------------------------------
# Change 8. The strict input format, and every error code of the contract


def edit_row(directory: Path, name: str, row: int, column: int | None = None, value: str = "",
             append: str = "") -> None:
    """Rewrite one line of a CSV file: line 0 is the header."""
    path = directory / name
    lines = path.read_text(encoding="utf-8").split("\n")
    if column is not None:
        fields = lines[row].split(",")
        fields[column] = value
        lines[row] = ",".join(fields)
    lines[row] += append
    path.write_text("\n".join(lines), encoding="utf-8")


def small_case(tmp_path: Path, flag: bool = True) -> Path:
    c = Case(flag=flag)
    if flag:
        c.flag_first("P1", A1, "E", 1, "no_advice")          # line 1 of replies.csv is a flagged reply
        c.sample()
    return c.write(tmp_path / "case")


COL = {name: i for i, name in enumerate(COLS)}
SAMPLED_LINE = 2                                             # anth-1, set E, sample 2: in the sample, part A_E
M2_LINE = 41                                                 # anth-1, set M2, sample 21
PLAIN_LINE = 5 * 60 + 60                                     # oth-2, set M2, sample 40: unflagged and not sampled

FORMAT_VIOLATIONS = [
    ("a sample index with a leading zero", lambda d: edit_row(d, "replies.csv", 7, COL["sample"], "07"),
     "E_SET_SAMPLE"),
    ("a blank line after the last row of replies.csv",
     lambda d: (d / "replies.csv").write_text((d / "replies.csv").read_text() + "\n"), "E_FILE"),
    ("a blank line after the last row of pairs.csv",
     lambda d: (d / "pairs.csv").write_text((d / "pairs.csv").read_text() + "\n"), "E_FILE"),
    ("a blank line between two rows", lambda d: edit_row(d, "replies.csv", 9, append="\n"), "E_FILE"),
    ("a row with a thirteenth, empty field", lambda d: edit_row(d, "replies.csv", 9, append=","), "E_FILE"),
    ("a row of pairs.csv with a fourth field", lambda d: edit_row(d, "pairs.csv", 1, append=",x"), "E_FILE"),
    ("a second key in case.json",
     lambda d: (d / "case.json").write_text('{"flag_relied_on": true, "note": "x"}\n'), "E_MODE"),
]


@pytest.mark.parametrize("what, change, code", FORMAT_VIOLATIONS, ids=[v[0] for v in FORMAT_VIOLATIONS])
def test_each_violation_of_the_strict_format_stops_with_a_named_error(tmp_path: Path, what, change, code) -> None:
    directory = small_case(tmp_path)
    rule.load_case(directory)                                # the case is valid before the change
    change(directory)
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == code, what


def test_a_row_with_too_few_fields_stops_with_e_file(tmp_path: Path) -> None:
    directory = small_case(tmp_path)
    path = directory / "replies.csv"
    lines = path.read_text().split("\n")
    lines[PLAIN_LINE] = lines[PLAIN_LINE].rsplit(",", 1)[0]  # eleven fields
    path.write_text("\n".join(lines))
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == "E_FILE"


# A row is one physical line. Before 2026-11-28 the reader gave all lines to `csv.reader` at once, which
# continued a quoted field onto the next line and joined the pieces: `"ant` and `h-1"` on two lines were
# read as the assistant `anth-1`, and the run ended with a result. Each case below was accepted then.
ROWS_OVER_TWO_LINES = [
    ("a quoted field of replies.csv split over two lines",
     lambda d: edit_row(d, "replies.csv", 9, COL["assistant"], '"ant\nh-1"')),
    ("a quoted field of pairs.csv split over two lines", lambda d: edit_row(d, "pairs.csv", 1, 0, '"P\n1"')),
    ("a carriage return inside a quoted field",
     lambda d: (d / "replies.csv").write_bytes(
         (d / "replies.csv").read_bytes().replace(b"\nP1,anth-1,", b'\nP1,"ant\rh-1",', 1))),
    ("a quote that opens in the last field of the last row and never closes",
     lambda d: (d / "replies.csv").write_bytes((d / "replies.csv").read_bytes().rstrip(b"\n") + b'"')),
    ("lines that end with a carriage return alone",
     lambda d: (d / "pairs.csv").write_bytes((d / "pairs.csv").read_bytes().replace(b"\n", b"\r"))),
]


@pytest.mark.parametrize("what, change", ROWS_OVER_TWO_LINES, ids=[v[0] for v in ROWS_OVER_TWO_LINES])
def test_a_row_that_does_not_stay_on_one_line_stops_with_e_file(tmp_path: Path, what, change) -> None:
    directory = small_case(tmp_path)
    rule.load_case(directory)                                # the case is valid before the change
    before = {name: (directory / name).read_bytes() for name in ("pairs.csv", "replies.csv")}
    change(directory)
    after = {name: (directory / name).read_bytes() for name in ("pairs.csv", "replies.csv")}
    assert after != before, what                             # the change reached the file
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == "E_FILE", what


def test_a_quoted_field_that_closes_on_its_line_is_read_and_text_after_it_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"
    path.write_bytes(b'a,b\n"x,y",z\n"p""q",r\n')
    assert rule._read_table(path, ["a", "b"]) == [{"a": "x,y", "b": "z"}, {"a": 'p"q', "b": "r"}]
    path.write_bytes(b'a,b\n"x"y,z\n')                       # read as `xy` before 2026-11-28
    with pytest.raises(rule.ContractError) as error:
        rule._read_table(path, ["a", "b"])
    assert error.value.code == "E_FILE"


CONSTRAINT_VIOLATIONS = [
    # (what, file, line, column, value, code, flag_relied_on)
    ("another header", "replies.csv", 0, COL["whole_set"], "whole", "E_FILE", True),
    ("another header in pairs.csv", "pairs.csv", 0, 1, "groups", "E_FILE", True),
    ("an unknown group", "pairs.csv", 1, 1, "Maybe", "E_PAIRS", True),
    ("an unknown realism result", "pairs.csv", 1, 2, "passed", "E_PAIRS", True),
    ("a blank pair id", "pairs.csv", 1, 0, "", "E_PAIRS", True),
    ("a reply of an unknown pair", "replies.csv", 7, COL["pair"], "P9", "E_UNKNOWN_PAIR", True),
    ("an unknown vendor", "replies.csv", 7, COL["vendor"], "google", "E_VENDOR", True),
    ("an assistant with two vendors", "replies.csv", 7, COL["vendor"], "other", "E_VENDOR", True),
    ("a blank assistant", "replies.csv", 7, COL["assistant"], "", "E_VENDOR", True),
    ("an unknown set", "replies.csv", 7, COL["set"], "M3", "E_SET_SAMPLE", True),
    ("sample 21 in set E", "replies.csv", 7, COL["sample"], "21", "E_SET_SAMPLE", True),
    ("sample 20 in set M2", "replies.csv", M2_LINE, COL["sample"], "20", "E_SET_SAMPLE", True),
    ("a sample index with a sign", "replies.csv", 7, COL["sample"], "+7", "E_SET_SAMPLE", True),
    ("a sample index with a space", "replies.csv", 7, COL["sample"], " 7", "E_SET_SAMPLE", True),
    ("a sample index with a decimal point", "replies.csv", 7, COL["sample"], "7.0", "E_SET_SAMPLE", True),
    ("a blank sample index", "replies.csv", 7, COL["sample"], "", "E_SET_SAMPLE", True),
    ("two rows with the same key", "replies.csv", 7, COL["sample"], "6", "E_DUPLICATE", True),
    ("empty written 2", "replies.csv", 7, COL["empty"], "2", "E_EMPTY", True),
    ("empty written 01", "replies.csv", 7, COL["empty"], "01", "E_EMPTY", True),
    ("an empty reply with a tier", "replies.csv", 7, COL["empty"], "1", "E_EMPTY", True),
    ("tier 4", "replies.csv", 7, COL["tier_h45"], "4", "E_TIER", True),
    ("a tier with a leading zero", "replies.csv", 7, COL["tier_h55"], "01", "E_TIER", True),
    ("a tier with a decimal point", "replies.csv", 7, COL["tier_h55"], "1.0", "E_TIER", True),
    ("a non-empty reply with a blank flag", "replies.csv", PLAIN_LINE, COL["flagged"], "", "E_FLAG", True),
    ("flagged written 2", "replies.csv", PLAIN_LINE, COL["flagged"], "2", "E_FLAG", True),
    ("a flagged reply without a first reader's code", "replies.csv", 1, COL["reader1"], "", "E_FLAG", True),
    ("a flagged reply with a sample mark", "replies.csv", 1, COL["sample200"], "A_E", "E_FLAG", True),
    ("a sampled reply without a first reader's code", "replies.csv", SAMPLED_LINE, COL["reader1"], "", "E_FLAG", True),
    ("a sample mark of another part", "replies.csv", SAMPLED_LINE, COL["sample200"], "O_E", "E_FLAG", True),
    ("an unknown sample mark", "replies.csv", SAMPLED_LINE, COL["sample200"], "A_X", "E_FLAG", True),
    ("an unknown first reader's code", "replies.csv", SAMPLED_LINE, COL["reader1"], "maybe", "E_FLAG", True),
    ("a first reader's code on an unread reply", "replies.csv", PLAIN_LINE, COL["reader1"], "advice", "E_FLAG", True),
    ("a whole-set code on a reply of set M2", "replies.csv", M2_LINE, COL["whole_set"], "advice", "E_WHOLE_SET", True),
    ("a whole-set code on a flagged reply", "replies.csv", 1, COL["whole_set"], "advice", "E_WHOLE_SET", True),
    ("an unknown whole-set code", "replies.csv", 7, COL["whole_set"], "yes", "E_WHOLE_SET", True),
    ("a flag when the flag is not relied on", "replies.csv", 7, COL["flagged"], "0", "E_MODE", False),
    ("a first reader's code when the flag is not relied on", "replies.csv", 7, COL["reader1"], "advice", "E_MODE",
     False),
    ("a whole-set code on set M2 without the flag", "replies.csv", M2_LINE, COL["whole_set"], "advice", "E_WHOLE_SET",
     False),
]


@pytest.mark.parametrize("what, name, line, column, value, code, flag", CONSTRAINT_VIOLATIONS,
                         ids=[v[0] for v in CONSTRAINT_VIOLATIONS])
def test_each_constraint_of_the_contract_stops_with_its_error(tmp_path: Path, what, name, line, column, value, code,
                                                              flag) -> None:
    directory = small_case(tmp_path, flag)
    rule.load_case(directory)
    edit_row(directory, name, line, column, value)
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == code, what


def test_a_repeated_pair_id_stops_with_e_pairs(tmp_path: Path) -> None:
    directory = small_case(tmp_path)
    (directory / "pairs.csv").write_text("pair,group,realism\nP1,Case,pass\nP1,Case,pass\n")
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == "E_PAIRS"


@pytest.mark.parametrize("text", ['{"flag_relied_on": "yes"}', '{"flag_relied_on": 1}', "{}", "[true]", "not json",
                                  None])
def test_a_malformed_or_missing_case_json_stops_with_e_mode(tmp_path: Path, text: str | None) -> None:
    directory = small_case(tmp_path)
    if text is None:
        (directory / "case.json").unlink()
    else:
        (directory / "case.json").write_text(text)
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == "E_MODE"


@pytest.mark.parametrize("name", ["pairs.csv", "replies.csv"])
def test_a_missing_csv_file_stops_with_e_file(tmp_path: Path, name: str) -> None:
    directory = small_case(tmp_path)
    (directory / name).unlink()
    with pytest.raises(rule.ContractError) as error:
        rule.load_case(directory)
    assert error.value.code == "E_FILE"


def test_crlf_line_ends_and_a_last_line_without_a_line_end_are_read(tmp_path: Path) -> None:
    directory = small_case(tmp_path)
    want = rule.compute(rule.load_case(directory))
    for name in ("pairs.csv", "replies.csv"):
        text = (directory / name).read_text()
        (directory / name).write_bytes(text.rstrip("\n").replace("\n", "\r\n").encode("utf-8"))
    assert rule.compute(rule.load_case(directory)) == want


def test_main_writes_the_result_or_stops_with_one_line_and_no_output(tmp_path: Path, capsys) -> None:
    directory = small_case(tmp_path)
    out_json = tmp_path / "out.json"
    assert rule.main([str(directory), str(out_json)]) == 0
    assert json.loads(out_json.read_text())["contract_version"] == "2"
    edit_row(directory, "replies.csv", 7, COL["sample"], "07")
    refused = tmp_path / "refused.json"
    assert rule.main([str(directory), str(refused)]) == 2
    assert capsys.readouterr().out == "CONTRACT_ERROR: E_SET_SAMPLE\n"
    assert not refused.exists()
    assert rule.main([str(directory)]) == 1


# ---------------------------------------------------------------------------------------------------------
# The shape of the output, and the committed example case


def test_lists_are_sorted_and_no_number_is_a_float(tmp_path: Path) -> None:
    c = Case((("P2", "Opposite", "pass"), ("P10", "Case", "pass"), ("P1", "Neither", "pass")))
    c.sample()
    out = c.run(tmp_path)
    assert [p["pair"] for p in out["pairs"]] == ["P1", "P10", "P2"]          # compared as strings
    keys = [(x["pair"], x["assistant"], x["judge"], x["comparison"]) for x in out["cells"]]
    assert keys == sorted(keys) and len(keys) == 3 * 7 * 2 * 2
    keys = [(x["pair"], x["judge"], x["comparison"]) for x in out["pairs_by_judge"]]
    assert keys == sorted(keys) and len(keys) == 3 * 2 * 2
    assert set(out["beside"]) == set(rule.VERSIONS) and len(rule.VERSIONS) == 7
    for rows in out["beside"].values():
        assert [(x["pair"], x["judge"]) for x in rows] == sorted((x["pair"], x["judge"]) for x in rows)

    def walk(o: Any) -> None:
        assert not isinstance(o, float)
        for x in (o.values() if isinstance(o, dict) else o if isinstance(o, list) else ()):
            walk(x)
    walk(out)
    assert set(out) == {"contract_version", "flag_relied_on", "cells", "pairs_by_judge", "pairs", "no_advice_estimate",
                        "rates", "chance_control", "beside"}


def test_the_committed_example_case_gives_its_expected_output(tmp_path: Path) -> None:
    out_json = tmp_path / "out.json"
    assert rule.main([str(FIXTURE), str(out_json)]) == 0
    out = json.loads(out_json.read_text(encoding="utf-8"))
    assert out == json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    # What the example holds, stated apart from the expected file (see the README beside it).
    assert final(out) == {"EX1": (True, False), "EX2": (None, None)}
    assert out["no_advice_estimate"]["high_by"] == ["anthropic_100"]
    step = pair_row(out, "EX1")["whole_set_step"]
    assert (step["applies"], step["codes_complete"], step["meets_case"]) == (True, True, True)
    assert (step["codes_needed"], step["codes_present"]) == (112, 112)
    assert pair_row(out, "EX2")["computed"] == {"meets_case": False, "meets_opposite": True}
    assert pair_row(out, "EX2")["whole_set_step"]["applies"] is False
    assert out["no_advice_estimate"]["weighted_share"] == "46/595"       # (46 * 3/5) / (46 + 95 + 72 + 144)
    assert out["rates"]["opposite_in_group_opposite"] == {"met": 0, "of": 1, "not_entered": 0, "not_yet_decided": 1}
