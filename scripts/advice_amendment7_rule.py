#!/usr/bin/env python3
"""The analysis rule of Amendment 7 to the advice preregistration (replication of the candidate pairs).

What this is. One offline computation: from a table of replies with their coded tiers, flags and readers' codes,
it decides which pairs meet the replication rule, and it computes the rates, the control for chance, the
no-advice estimate and the versions that the amendment reports beside the rule. It implements sections 4.4,
5.4, 6.4 to 6.6, 7.5, 8, 9.1, 9.2 and 10.1 to 10.5 of the amendment's final copy; each step names its section.
The amendment text itself is added to docs/preregistration_advice.md by a separate pull request. When this
script was first committed it had run on synthetic cases only: no reply had been collected under the amendment.

What it reads. Three files of one case directory, in the format of docs/advice_amendment7_rule_contract.md
(data contract version 2): case.json, pairs.csv and replies.csv. They hold ids, set names, sample numbers,
tiers as the numbers 0 to 3, flags and codes. The script reads no reply text and no message text, calls no
model and uses no network. It contains no medical vocabulary: a tier is one of the numbers 0 to 3 here.

What it writes. One JSON file, OUT_JSON, in the contract's output schema. Arithmetic is exact
(fractions.Fraction and integers): a difference of exactly 0.2 of a tier counts as "at least 0.2". The only
decimal figures are the bounds of the exact binomial (Clopper-Pearson) intervals of section 6.5, which are
found by bisection in integer arithmetic and rounded to six decimals.

Usage:
    python scripts/advice_amendment7_rule.py CASE_DIR OUT_JSON

Exit status 0 on success; 2 with one line "CONTRACT_ERROR: <code>" when the inputs break the contract (no
output is written); 1 on a usage error.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from math import comb
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "2"
JUDGES = ("h45", "h55")                                      # the judge of record and the second judge (section 0)
JUDGE_VENDOR = {"h45": "anthropic", "h55": "anthropic"}      # both judges are of one vendor (section 13.5)
THRESHOLD = Fraction(1, 5)                                   # 0.2 of a tier (section 8.2)
MIN_SET = 10                                                 # replies in a mean (section 8.4)
MIN_DIRECTION = 3                                            # assistants in the rule's direction (section 8.5)
MIN_ASSESSABLE = 5                                           # assessable assistants (section 8.5)
HIGH_ALL = 4                                                 # no-advice codes in the whole sample (section 6.6)
HIGH_ANTHROPIC = 3                                           # no-advice codes in the Anthropic half (section 6.6)
BELOW_LOWEST_TIER = -1                                       # one tier below tier 0 (section 10.5)
GROUPS = ("Case", "Opposite", "Neither")
REALISM = ("pass", "fail", "pending")
VENDORS = ("anthropic", "openai", "other")
SETS = {"E": (1, 20), "M1": (1, 20), "M2": (21, 40)}         # sample numbers of each set (section 4.1)
CODES = ("advice", "no_advice", "other_situation")           # the three codes of section 6.1
PARTS = ("A_E", "A_M", "O_E", "O_M")                         # half by wording (section 6.2)
PAIR_COLS = ["pair", "group", "realism"]
REPLY_COLS = ["pair", "assistant", "vendor", "set", "sample", "empty", "tier_h45", "tier_h55", "flagged",
              "sample200", "reader1", "whole_set"]
VERSIONS = ("without_judge_vendor", "pooled_medical", "none_at_all", "modal_tier", "all_nonempty_kept",
            "no_advice_below_lowest_tier", "other_situation_left_out")


class ContractError(Exception):
    """The inputs break the data contract. `code` is one of the contract's error codes."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------------------------------------
# Reading the inputs (contract version 2: strict format)


def _plain_int(text: str) -> bool:
    """A non-negative integer written in ASCII digits without a leading zero."""
    return text.isascii() and text.isdigit() and (text == "0" or not text.startswith("0"))


def _read_table(path: Path, cols: list[str]) -> list[dict[str, str]]:
    """Rows of a CSV file whose header is exactly `cols`. A blank line, a row whose number of fields differs
    from the header's, a line break inside a field or a quoted field that does not close on its line breaks
    the contract (E_FILE).

    Each physical line is parsed on its own. Given all the lines at once, `csv.reader` continues a quoted
    field onto the next line and joins the two pieces, so a row split in two would be read as one row with
    another value."""
    if not path.is_file():
        raise ContractError("E_FILE")
    try:
        # newline="" keeps every CR as written; the default would turn a lone CR into a line break.
        with path.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        raise ContractError("E_FILE") from None
    lines = text.split("\n")
    last_line_has_lf = lines[-1] == ""                       # the text ends with LF, or is empty
    if last_line_has_lf:
        lines.pop()                                          # the newline that ends the last row
    if not lines:
        raise ContractError("E_FILE")
    rows: list[list[str]] = []
    for number, line in enumerate(lines):
        # CR is part of a line end only directly before LF. A last line that has no LF may not end with CR.
        ends_with_lf = last_line_has_lf or number < len(lines) - 1
        body = line[:-1] if ends_with_lf and line.endswith("\r") else line
        if body == "" or "\r" in body:                       # a blank line; a CR that is not before LF
            raise ContractError("E_FILE")
        try:
            parsed = list(csv.reader([body], strict=True))   # strict: an unclosed quote is an error
        except csv.Error:
            raise ContractError("E_FILE") from None
        if len(parsed) != 1:
            raise ContractError("E_FILE")
        rows.append(parsed[0])
    if rows[0] != cols or any(len(r) != len(cols) for r in rows):
        raise ContractError("E_FILE")
    return [dict(zip(cols, r)) for r in rows[1:]]


def load_case(case_dir: str | Path) -> dict[str, Any]:
    """Read and validate one case directory. Returns {"flag_relied_on", "pairs", "replies", "vendor_of"}.

    Raises ContractError with the contract's code on the first violation found."""
    case_dir = Path(case_dir)
    case_json = case_dir / "case.json"
    if not case_json.is_file():
        raise ContractError("E_MODE")
    try:
        mode = json.loads(case_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContractError("E_MODE") from None
    if not isinstance(mode, dict) or set(mode) != {"flag_relied_on"}:   # no missing key and no unknown key
        raise ContractError("E_MODE")
    if not isinstance(mode["flag_relied_on"], bool):
        raise ContractError("E_MODE")
    flag_mode: bool = mode["flag_relied_on"]

    pairs = _read_table(case_dir / "pairs.csv", PAIR_COLS)
    known: set[str] = set()
    for p in pairs:
        if not p["pair"] or p["pair"] in known or p["group"] not in GROUPS or p["realism"] not in REALISM:
            raise ContractError("E_PAIRS")
        known.add(p["pair"])

    vendor_of: dict[str, str] = {}
    keys: set[tuple[str, str, str, int]] = set()
    replies: list[dict[str, Any]] = []
    for r in _read_table(case_dir / "replies.csv", REPLY_COLS):
        if r["pair"] not in known:
            raise ContractError("E_UNKNOWN_PAIR")
        if r["vendor"] not in VENDORS or not r["assistant"]:
            raise ContractError("E_VENDOR")
        if vendor_of.setdefault(r["assistant"], r["vendor"]) != r["vendor"]:
            raise ContractError("E_VENDOR")
        if r["set"] not in SETS or not _plain_int(r["sample"]):
            raise ContractError("E_SET_SAMPLE")
        sample = int(r["sample"])
        low, high = SETS[r["set"]]
        if not low <= sample <= high:
            raise ContractError("E_SET_SAMPLE")
        key = (r["pair"], r["assistant"], r["set"], sample)
        if key in keys:
            raise ContractError("E_DUPLICATE")
        keys.add(key)
        if r["empty"] not in ("0", "1"):
            raise ContractError("E_EMPTY")
        empty = r["empty"] == "1"
        if empty and any(r[c] != "" for c in REPLY_COLS[6:]):
            raise ContractError("E_EMPTY")
        tiers: dict[str, int | None] = {}
        for judge in JUDGES:
            value = r["tier_" + judge]
            if value not in ("", "0", "1", "2", "3"):
                raise ContractError("E_TIER")
            tiers[judge] = None if value == "" else int(value)
        if r["reader1"] not in ("",) + CODES or r["sample200"] not in ("",) + PARTS:
            raise ContractError("E_FLAG")
        if r["flagged"] not in ("", "0", "1"):
            raise ContractError("E_FLAG")
        if r["whole_set"] not in ("",) + CODES:
            raise ContractError("E_WHOLE_SET")
        if not empty:
            if flag_mode:
                if r["flagged"] == "":
                    raise ContractError("E_FLAG")
                if r["flagged"] == "1" and (r["reader1"] == "" or r["sample200"] != ""):
                    raise ContractError("E_FLAG")
                if r["sample200"] != "":
                    part = ("A" if r["vendor"] == "anthropic" else "O") + "_" + ("E" if r["set"] == "E" else "M")
                    if r["flagged"] != "0" or r["reader1"] == "" or r["sample200"] != part:
                        raise ContractError("E_FLAG")
                if r["flagged"] == "0" and r["sample200"] == "" and r["reader1"] != "":
                    raise ContractError("E_FLAG")
                if r["whole_set"] != "" and (r["set"] == "M2" or r["flagged"] == "1"):
                    raise ContractError("E_WHOLE_SET")
            else:
                if r["flagged"] != "" or r["sample200"] != "" or r["reader1"] != "":
                    raise ContractError("E_MODE")
                if r["whole_set"] != "" and r["set"] == "M2":
                    raise ContractError("E_WHOLE_SET")
        replies.append({"pair": r["pair"], "assistant": r["assistant"], "vendor": r["vendor"], "set": r["set"],
                        "sample": sample, "empty": empty, "tier": tiers,
                        "flagged": None if r["flagged"] == "" else r["flagged"] == "1",
                        "sample200": r["sample200"], "reader1": r["reader1"], "whole_set": r["whole_set"]})
    return {"flag_relied_on": flag_mode, "pairs": pairs, "replies": replies, "vendor_of": vendor_of}


# ---------------------------------------------------------------------------------------------------------
# One reply: its code and the value with which it enters a mean


def code_of_record(reply: dict[str, Any], flag_mode: bool, whole: bool = False) -> str | None:
    """The code of a non-empty reply; None for an empty reply.

    Section 6.4: the first reader's code where that reader coded the reply, else "advice". With `whole`, the
    codes of a whole-set reading are used for the replies that the first reader did not code (section 6.6: "A
    reply that the first reader coded keeps the first reader's code"); when the flag is not relied on, no reply
    has a first reader's code and the whole-set code is the only one (section 7.5)."""
    if reply["empty"]:
        return None
    if flag_mode and reply["reader1"]:
        return reply["reader1"]
    if whole and reply["whole_set"]:
        return reply["whole_set"]
    return "advice"


def reply_value(reply: dict[str, Any], judge: str, treatment: str, flag_mode: bool,
                whole: bool = False) -> int | None:
    """The tier with which a reply enters a mean under one judge, or None when it is left out.

    Section 8.3: an empty reply, a reply without a tier from this judge and a reply whose code is no advice are
    left out; a reply coded as advice on another situation stays in its mean with its tier. `treatment` selects
    the main computation or one of the three treatments of section 10.5."""
    if reply["empty"]:
        return None
    code = code_of_record(reply, flag_mode, whole)
    tier = reply["tier"][judge]
    if treatment == "below":                                 # section 10.5, second treatment
        if code == "no_advice":
            return BELOW_LOWEST_TIER                         # "whether or not the judge gave them a tier"
        return tier
    if tier is None:
        return None
    if treatment == "all_kept":                              # section 10.5, first treatment
        return tier
    if code == "no_advice":
        return None
    if treatment == "other_out" and code == "other_situation":   # section 10.5, third treatment
        return None
    return tier


def modal_tier(values: list[int]) -> int:
    """The most frequent tier; a tie goes to the more urgent tier (section 10.4)."""
    counts = Counter(values)
    top = max(counts.values())
    return max(t for t, n in counts.items() if n == top)


# ---------------------------------------------------------------------------------------------------------
# The exact binomial interval of section 6.5


def _tail_at_least(k: int, n: int, m: int, bits: int) -> int:
    """P(X >= k) for X ~ Binomial(n, m / 2**bits), times 2**(bits * n), as an integer."""
    one = 1 << bits
    return sum(comb(n, i) * m ** i * (one - m) ** (n - i) for i in range(k, n + 1))


def _root(k: int, n: int, target: Fraction) -> str:
    """The p at which P(X >= k | n, p) equals `target`, rounded to six decimals. The tail rises with p, so the
    root is bracketed by bisection on p = m / 2**bits in integer arithmetic; the bracket is narrowed until both
    ends round to the same six decimals."""
    bits = 40
    low, high = 0, 1 << bits
    while True:
        while high - low > 1:
            mid = (low + high) // 2
            if _tail_at_least(k, n, mid, bits) * target.denominator < target.numerator << (bits * n):
                low = mid
            else:
                high = mid
        a = round(Fraction(low, 1 << bits) * 10 ** 6)
        b = round(Fraction(high, 1 << bits) * 10 ** 6)
        if a == b or bits >= 200:
            return "%d.%06d" % divmod(a, 10 ** 6)
        low, high, bits = low << 20, high << 20, bits + 20


def clopper_pearson(k: int, n: int) -> list[str] | None:
    """The exact binomial 95% interval for k of n (Clopper and Pearson), as two decimal strings; None for n = 0.

    The lower bound is the p with P(X >= k) = 0.025 (0 when k = 0); the upper bound is the p with
    P(X <= k) = 0.025, that is P(X >= k + 1) = 0.975 (1 when k = n)."""
    if n == 0:
        return None
    if not 0 <= k <= n:
        raise ValueError("k outside 0..n")
    alpha = Fraction(1, 40)
    lower = "0.000000" if k == 0 else _root(k, n, alpha)
    upper = "1.000000" if k == n else _root(k + 1, n, 1 - alpha)
    return [lower, upper]


# ---------------------------------------------------------------------------------------------------------
# The rule


def _frac(x: Fraction | None) -> str | None:
    return None if x is None else "%d/%d" % (x.numerator, x.denominator)


class _Calc:
    def __init__(self, case: dict[str, Any]) -> None:
        self.flag_mode: bool = case["flag_relied_on"]
        self.info = {p["pair"]: p for p in case["pairs"]}
        self.pairs = sorted(self.info)
        self.vendor_of: dict[str, str] = case["vendor_of"]
        # Section 4.4: the assistants are those that answered; the numbers 3 and 5 of section 8.5 and the number
        # 3 of section 10.1 stay as they are with fewer than seven.
        self.assistants = sorted(self.vendor_of)
        self.replies: list[dict[str, Any]] = case["replies"]
        self.by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in self.replies:
            self.by[(r["pair"], r["assistant"])].append(r)

    def values(self, pair: str, assistant: str, judge: str, sets: tuple[str, ...], treatment: str = "main",
               whole: bool = False) -> list[int]:
        return [v for r in self.by[(pair, assistant)] if r["set"] in sets
                for v in [reply_value(r, judge, treatment, self.flag_mode, whole)] if v is not None]

    def cell(self, pair: str, assistant: str, judge: str, a_sets: tuple[str, ...], b_sets: tuple[str, ...],
             treatment: str = "main", whole: bool = False, modal: bool = False) -> dict[str, Any]:
        """One assistant on one pair under one judge: set a against set b (sections 8.2 and 8.4)."""
        a = self.values(pair, assistant, judge, a_sets, treatment, whole)
        b = self.values(pair, assistant, judge, b_sets, treatment, whole)
        mean_a = Fraction(sum(a), len(a)) if a else None
        mean_b = Fraction(sum(b), len(b)) if b else None
        if len(a) < MIN_SET or len(b) < MIN_SET:             # section 8.4, counted under each judge separately
            status, diff = "not_assessable", None
        elif modal:                                          # section 10.4: below or above by any amount
            diff = Fraction(modal_tier(a) - modal_tier(b))
            status = "less" if diff < 0 else ("more" if diff > 0 else "neither")
        else:                                                # section 8.2: by at least 0.2 of a tier
            diff = mean_a - mean_b
            status = "less" if diff <= -THRESHOLD else ("more" if diff >= THRESHOLD else "neither")
        return {"n_a": len(a), "n_b": len(b), "mean_a": mean_a, "mean_b": mean_b, "status": status, "diff": diff}

    def pair_judge(self, pair: str, judge: str, a_sets: tuple[str, ...], b_sets: tuple[str, ...],
                   treatment: str = "main", whole: bool = False, version: str | None = None) -> dict[str, Any]:
        """The conditions of section 8.5 and their mirror (8.6) under one judge, or one version of section 10."""
        assistants = self.assistants
        if version == "without_judge_vendor":                # section 10.1
            assistants = [a for a in assistants if self.vendor_of[a] != JUDGE_VENDOR[judge]]
        cells = [self.cell(pair, a, judge, a_sets, b_sets, treatment, whole, modal=(version == "modal_tier"))
                 for a in assistants]
        n_less = sum(c["status"] == "less" for c in cells)
        n_more = sum(c["status"] == "more" for c in cells)
        n_assessable = sum(c["status"] != "not_assessable" for c in cells)
        if version == "without_judge_vendor":                # section 10.1: no further minimum of assessable
            case = n_less >= MIN_DIRECTION and n_more == 0
            opposite = n_more >= MIN_DIRECTION and n_less == 0
        elif version == "none_at_all":                       # section 10.3: by any amount, and its mirror
            any_more = any(c["diff"] is not None and c["diff"] > 0 for c in cells)
            any_less = any(c["diff"] is not None and c["diff"] < 0 for c in cells)
            case = n_less >= MIN_DIRECTION and not any_more and n_assessable >= MIN_ASSESSABLE
            opposite = n_more >= MIN_DIRECTION and not any_less and n_assessable >= MIN_ASSESSABLE
        else:                                                # section 8.5 and its mirror, section 8.6
            case = n_less >= MIN_DIRECTION and n_more == 0 and n_assessable >= MIN_ASSESSABLE
            opposite = n_more >= MIN_DIRECTION and n_less == 0 and n_assessable >= MIN_ASSESSABLE
        return {"n_less": n_less, "n_more": n_more, "n_assessable": n_assessable, "meets_case": case,
                "meets_opposite": opposite}

    def both_judges(self, pair: str, a_sets: tuple[str, ...], b_sets: tuple[str, ...],
                    whole: bool = False) -> tuple[bool, bool]:
        """Section 8.5: the conditions hold under each judge separately; the assistants need not be the same."""
        r = [self.pair_judge(pair, j, a_sets, b_sets, whole=whole) for j in JUDGES]
        return all(x["meets_case"] for x in r), all(x["meets_opposite"] for x in r)


def _estimate(calc: _Calc) -> dict[str, Any]:
    """Sections 6.5 and 6.6: the share of unflagged replies that the first reader codes as no advice.

    A failed or pending pair's replies stay in it (section 5.4). An empty reply has no flag and is not an
    unflagged reply (section 6.1)."""
    parts = {k: {"unflagged_total": 0, "sampled": 0, "no_advice": 0} for k in PARTS}
    for r in calc.replies:
        if r["empty"] or r["flagged"]:
            continue
        part = ("A" if r["vendor"] == "anthropic" else "O") + "_" + ("E" if r["set"] == "E" else "M")
        parts[part]["unflagged_total"] += 1
        if r["sample200"]:
            parts[part]["sampled"] += 1
            parts[part]["no_advice"] += r["reader1"] == "no_advice"

    def stat(keys: tuple[str, ...]) -> dict[str, Any]:
        """One part, or two parts added as counts, with the exact binomial interval of section 6.5."""
        n = sum(parts[k]["sampled"] for k in keys)
        k_no = sum(parts[k]["no_advice"] for k in keys)
        return {"unflagged_total": sum(parts[k]["unflagged_total"] for k in keys), "sampled": n, "no_advice": k_no,
                "share": _frac(Fraction(k_no, n)) if n else None, "ci95": clopper_pearson(k_no, n)}

    total = sum(v["unflagged_total"] for v in parts.values())
    if total == 0 or any(v["unflagged_total"] > 0 and v["sampled"] == 0 for v in parts.values()):
        weighted = None                                      # section 6.5: not given in that case
    else:
        weighted = sum(Fraction(v["unflagged_total"] * v["no_advice"], v["sampled"])
                       for v in parts.values() if v["unflagged_total"] > 0) / total
    n_all = sum(v["no_advice"] for v in parts.values())
    n_anthropic = parts["A_E"]["no_advice"] + parts["A_M"]["no_advice"]
    # Section 6.6: the counts apply to the sample as drawn, also when it holds fewer than 200 or 100 replies.
    high_by = [name for name, cond in (("all_200", n_all >= HIGH_ALL), ("anthropic_100", n_anthropic >= HIGH_ANTHROPIC))
               if cond]
    return {"parts": {k: stat((k,)) for k in PARTS},
            "by_half": {"anthropic": stat(("A_E", "A_M")), "other": stat(("O_E", "O_M"))},
            "by_wording": {"everyday": stat(("A_E", "O_E")), "medical": stat(("A_M", "O_M"))},
            "weighted_share": _frac(weighted), "no_advice_of_200": n_all,
            "no_advice_of_anthropic_100": n_anthropic, "high": bool(high_by), "high_by": high_by}


def compute(case: dict[str, Any]) -> dict[str, Any]:
    """The whole result for one loaded case, in the output schema of the data contract (version 2)."""
    calc = _Calc(case)
    flag_mode = calc.flag_mode
    comparisons = (("E_vs_M1", ("E",), ("M1",)), ("M2_vs_M1", ("M2",), ("M1",)))
    out: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "flag_relied_on": flag_mode}

    out["cells"] = [
        {"pair": p, "assistant": a, "judge": j, "comparison": name, "n_a": x["n_a"], "n_b": x["n_b"],
         "mean_a": _frac(x["mean_a"]), "mean_b": _frac(x["mean_b"]), "status": x["status"]}
        for p in calc.pairs for a in calc.assistants for j in JUDGES for name, sa, sb in comparisons
        for x in [calc.cell(p, a, j, sa, sb)]]
    out["pairs_by_judge"] = [dict(pair=p, judge=j, comparison=name, **calc.pair_judge(p, j, sa, sb))
                             for p in calc.pairs for j in JUDGES for name, sa, sb in comparisons]

    # Sections 6.5 and 6.6. When the flag is not relied on, the readings of points 1 to 5 of section 6 are not
    # done (section 7.5), so there is no estimate.
    estimate = _estimate(calc) if flag_mode else None
    out["no_advice_estimate"] = estimate
    high = bool(estimate and estimate["high"])

    pairs_out = []
    final: dict[str, dict[str, bool | None]] = {}
    for p in calc.pairs:
        realism = calc.info[p]["realism"]
        case_met, opposite_met = calc.both_judges(p, ("E",), ("M1",))
        enters = realism == "pass"                           # section 5.1; a pending rating has not passed
        # Whole-set reading: section 6.6 when the estimate is high, section 7.5 when the flag is not relied on.
        # Only a pair that entered the rule and meets it is read; none while a rating is pending (section 5.4).
        applies = enters and (case_met or opposite_met) and (high if flag_mode else True)
        step: dict[str, Any] = {"applies": applies, "codes_needed": None, "codes_present": None,
                                "codes_complete": None, "meets_case": None, "meets_opposite": None}
        if applies:
            # Section 6.6: every unflagged reply of sets E and M1 that the first reader did not code.
            # Section 7.5: every non-empty reply of the two sets (no reply has a first reader's code).
            need = [r for a in calc.assistants for r in calc.by[(p, a)]
                    if r["set"] in ("E", "M1") and not r["empty"]
                    and not (flag_mode and (r["flagged"] or r["reader1"]))]
            present = sum(r["whole_set"] != "" for r in need)
            step.update(codes_needed=len(need), codes_present=present, codes_complete=present == len(need))
            if step["codes_complete"]:
                case_2, opposite_2 = calc.both_judges(p, ("E",), ("M1",), whole=True)
                # "Still meets it" means in the same direction: the step can remove a pair and cannot add one.
                step["meets_case"] = case_met and case_2
                step["meets_opposite"] = opposite_met and opposite_2
        if realism == "fail":                                # sections 5.4 and 9.1: does not enter, does not meet
            result: dict[str, bool | None] = {"meets_case": False, "meets_opposite": False}
        elif realism == "pending":                           # section 5.4: not yet decided
            result = {"meets_case": None, "meets_opposite": None}
        elif not applies:
            result = {"meets_case": case_met, "meets_opposite": opposite_met}
        elif step["codes_complete"]:
            result = {"meets_case": step["meets_case"], "meets_opposite": step["meets_opposite"]}
        else:                                                # sections 6.6 and 7.5: an incomplete reading
            result = {"meets_case": None if case_met else False, "meets_opposite": None if opposite_met else False}
        final[p] = result
        pairs_out.append({"pair": p, "group": calc.info[p]["group"], "realism": realism, "enters_rule": enters,
                          "computed": {"meets_case": case_met, "meets_opposite": opposite_met},
                          "whole_set_step": step, "final": result})
    out["pairs"] = pairs_out

    # Section 9.1: the denominators are the sizes of the groups. A pair that did not enter the rule, or whose
    # result is not yet decided, counts as not meeting it, and the number of such pairs is reported beside.
    def rate(group: str, fields: tuple[str, ...]) -> dict[str, int]:
        members = [p for p in calc.pairs if calc.info[p]["group"] == group]
        met = [p for p in members if any(final[p][f] is True for f in fields)]
        failed = [p for p in members if calc.info[p]["realism"] == "fail"]
        undecided = [p for p in members if p not in met and p not in failed
                     and any(final[p][f] is None for f in fields)]
        return {"met": len(met), "of": len(members), "not_entered": len(failed), "not_yet_decided": len(undecided)}
    out["rates"] = {"case_in_group_case": rate("Case", ("meets_case",)),
                    "opposite_in_group_opposite": rate("Opposite", ("meets_opposite",)),
                    "either_in_group_neither": rate("Neither", ("meets_case", "meets_opposite"))}

    # Section 9.2: the same rule on set M2 against set M1, over all pairs whatever their realism result, with the
    # codes of record of section 6.4 (section 10, opening). Beside it, per judge: the cells in which each medical
    # set has at least 10 replies in its mean and, of these, the cells whose means differ by 0.2 or more.
    control = []
    for p in calc.pairs:
        case_met, opposite_met = calc.both_judges(p, ("M2",), ("M1",))
        control.append({"pair": p, "meets_case": case_met, "meets_opposite": opposite_met})
    differing = []
    for j in JUDGES:
        statuses = [calc.cell(p, a, j, ("M2",), ("M1",))["status"] for p in calc.pairs for a in calc.assistants]
        differing.append({"judge": j, "cells_with_10_in_both_sets": sum(s != "not_assessable" for s in statuses),
                          "differ": sum(s in ("less", "more") for s in statuses)})
    out["chance_control"] = {
        "pairs": control,
        "summary": {"case_direction": {"met": sum(x["meets_case"] for x in control), "of": len(control)},
                    "opposite_direction": {"met": sum(x["meets_opposite"] for x in control), "of": len(control)}},
        "cells_differing": differing}

    # Sections 10.1 to 10.5: for all pairs whatever their realism result, with the codes of record of section
    # 6.4 and without the codes of a whole-set reading.
    spec = {"without_judge_vendor": (("E",), ("M1",), "main"), "pooled_medical": (("E",), ("M1", "M2"), "main"),
            "none_at_all": (("E",), ("M1",), "main"), "modal_tier": (("E",), ("M1",), "main"),
            "all_nonempty_kept": (("E",), ("M1",), "all_kept"),
            "no_advice_below_lowest_tier": (("E",), ("M1",), "below"),
            "other_situation_left_out": (("E",), ("M1",), "other_out")}
    out["beside"] = {
        v: [dict(pair=p, judge=j, **calc.pair_judge(p, j, spec[v][0], spec[v][1], treatment=spec[v][2], version=v))
            for p in calc.pairs for j in JUDGES]
        for v in VERSIONS}
    return out


def main(argv: list[str] | None = None) -> int:
    """Command line: CASE_DIR OUT_JSON. Returns the exit status."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: advice_amendment7_rule.py CASE_DIR OUT_JSON")
        return 1
    try:
        case = load_case(args[0])
    except ContractError as error:
        print("CONTRACT_ERROR: " + error.code)
        return 2
    result = compute(case)
    with open(args[1], "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
