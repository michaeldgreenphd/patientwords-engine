"""tierForest gate + headline pick as data (scripts/urgency_shift.py, audit M4).

The collector is script-style (module-level code runs on import), so these
pins read the source, matching the repo pattern for such files: the n>=100
reliability gate is a recorded analysis parameter, and the headline
downgrader is the most negative gate-passing mean tier shift (model-id
tiebreak), None when nothing passes.
"""

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1]
        / "scripts" / "urgency_shift.py").read_text(encoding="utf-8")


def test_reliability_gate_is_a_recorded_parameter():
    assert re.search(r"^RELIABILITY_GATE_N = 100$", _SRC, re.M)
    assert 'summary["reliability_gate_n"] = RELIABILITY_GATE_N' in _SRC


def test_headline_downgrader_pick_semantics():
    assert 'summary["headline_downgrader"]' in _SRC
    # gate-passing + numeric mean only, most negative first, model-id tiebreak
    assert re.search(r'v\["n"\] >= RELIABILITY_GATE_N', _SRC)
    assert 'min(_reliable, key=lambda m: (_reliable[m], m)) if _reliable else None' in _SRC
