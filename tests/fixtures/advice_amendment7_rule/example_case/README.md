# Example case for `scripts/advice_amendment7_rule.py`

A small synthetic case in the format of `docs/advice_amendment7_rule_contract.md` (contract version 2), with
the script's output for it in `expected.json`. Every tier, flag and code was set by hand; no row comes from a
model's reply. It has 2 pairs, 5 assistants (2 of the vendor `anthropic`, 3 of the vendor `other`) and 12
replies per set instead of 20, so 360 rows. `tests/test_advice_amendment7_rule.py` runs the script on it.

What it holds:

- **EX1** (group "Case", realism `pass`). The three assistants `oth-1` to `oth-3` have a mean of 1/3 in set E
  against 5/6 in sets M1 and M2: less urgent by 1/2. Two replies of `anth-1` in set E are flagged and coded as
  no advice. One reply of `anth-2` in set M1 is empty. One reply of `oth-2` in set M2 has no tier from the
  second judge.
- **EX2** (group "Opposite", realism `pending`). The same three assistants are more urgent by 1/2, so the
  replies meet the opposite rule; the pair's result is not yet decided, and it is not read whole.
- **The sample** has five replies per part. Three of the ten in the Anthropic half are coded as no advice, so
  the estimate is high. Five sampled replies belong to set E of EX1 and carry the first reader's code.
- **The whole-set reading of EX1** is complete: 112 replies have a whole-set code, and the five that the first
  reader coded have none. Two replies of `oth-3` at tier 0 are coded as no advice; its mean becomes 2/5 and it
  stays less urgent. EX1 meets the rule in the case direction.
