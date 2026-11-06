"""scripts/judge_register_sensitivity.py: the cross-judge harness must reproduce the registered wave-2 result.

The harness rebuilds each wave-2 run in a scratch directory and calls the registered analysis's own functions. Run with
the judge of record's files, it must give exactly the committed data/petri/w2_register_contrast.json, or the
cross-judge rows it reports beside it would not be comparable.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("judge_register_sensitivity", _SCRIPTS / "judge_register_sensitivity.py")
jrs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jrs)


def test_the_judge_of_record_through_the_harness_reproduces_the_committed_result(tmp_path):
    got = jrs.summarize(jrs.w2_under_judge(jrs.OF_RECORD, tmp_path))
    committed = jrs.summarize(json.loads(jrs.W2_RESULT.read_text(encoding="utf-8")))
    assert got == committed
    assert got["primary"]["negative"] == 27 and got["decomposition_statement"] == "not_separated"


def test_the_registered_verifier_is_restored_after_a_regrade(tmp_path):
    registered = jrs.w2.verify_run
    jrs.w2_under_judge(jrs.DEFAULT_JUDGES[0], tmp_path)
    assert jrs.w2.verify_run is registered


def test_human_vs_judge_reads_all_25_coded_responses():
    out = jrs.human_vs_judge()
    assert sum(v["n"] for v in out.values()) == 25
    assert set(out) == {"clinical", "patient", "translated"}
