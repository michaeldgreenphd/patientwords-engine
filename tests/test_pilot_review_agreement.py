"""pilot/analysis/review_agreement.py compares the owner's blind review of a version-2 run with the checker's
structured answers. These tests use a small fake run and export with hand-checkable numbers."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pilot_review_agreement_test",
                                              ROOT / "pilot" / "analysis" / "review_agreement.py")
assert _spec is not None and _spec.loader is not None
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

# (owner same, precision, sentence, real, keep) and (checker verdict, relation, sentence_natural, patient_realism)
CASES = [
    (("yes", "as_precise", "both", "real", "keep"), ("yes", "same", "both", "real")),
    (("yes", "vaguer", "both", "textbook", "keep"), ("yes", "broader", "both", "real")),
    (("no", "more_specific", "patient_only", "unlikely", "drop"), ("no", "narrower", "clinical_only", "unlikely")),
    (("unclear", "as_precise", "neither", "real", "edit"), ("no", "different", "both", "textbook")),
]


def _fixture(tmp_path: Path):
    run = tmp_path / "pilot_test_run"
    run.mkdir()
    mapping, checked, rows = {}, [], []
    for i, (owner, ck) in enumerate(CASES, 1):
        sid, rid = f"r{i:03d}", f"row{i}"
        mapping[sid] = rid
        checked.append({"source": "generated", "row_id": rid, "verdict": ck[0], "relation": ck[1],
                        "sentence_natural": ck[2], "patient_realism": ck[3]})
        fa = dict(zip(("same", "precision", "sentence", "patient_real", "keep"), owner))
        rows.append({"sample_id": sid, "owner": {"first_answers": fa, "checker_shown_before_first_answer": False}})
    checked.append({"source": "broken", "row_id": None, "verdict": "no"})
    (run / "review_map.json").write_text(json.dumps({"map": mapping}), encoding="utf-8")
    (run / "checked.jsonl").write_text("".join(json.dumps(c) + "\n" for c in checked), encoding="utf-8")
    return run, {"rows": rows}


def test_agreement_per_question_with_hand_checked_numbers(tmp_path):
    run, export = _fixture(tmp_path)
    out = ra.compare(run, export, seed=1, resamples=200)["comparisons"]
    assert (out["same"]["agreement"]["x"], out["same"]["n_compared"]) == (3, 4)
    # relation 'different' has no precision: counted as not comparable, never compared
    assert (out["precision"]["n_compared"], out["precision"]["not_comparable"]) == (3, 1)
    assert out["precision"]["agreement"]["x"] == 3
    assert out["sentence"]["agreement"]["x"] == 2 and out["sentence_both_vs_not"]["agreement"]["x"] == 3
    assert out["realism"]["agreement"]["x"] == 2 and out["realism_real_vs_not"]["agreement"]["x"] == 2


def test_keep_rule_r8_counts(tmp_path):
    run, export = _fixture(tmp_path)
    k = ra.compare(run, export, seed=1, resamples=200)["keep_rule_r8"]
    assert k["counts"] == {"tp": 2, "fn": 0, "fp": 1, "tn": 1}


def test_bootstrap_is_reproducible_under_its_seed(tmp_path):
    run, export = _fixture(tmp_path)
    a = ra.compare(run, export, seed=7, resamples=300)
    b = ra.compare(run, export, seed=7, resamples=300)
    assert a == b


def test_refuses_non_blind_rows_unmapped_rows_and_version_1_runs(tmp_path):
    run, export = _fixture(tmp_path)
    bad = copy.deepcopy(export)
    bad["rows"][0]["owner"]["checker_shown_before_first_answer"] = True
    with pytest.raises(ra.AgreementError, match="not a blind label"):
        ra.compare(run, bad, 1, 100)
    bad = copy.deepcopy(export)
    bad["rows"][0]["sample_id"] = "r999"
    with pytest.raises(ra.AgreementError, match="not in review_map"):
        ra.compare(run, bad, 1, 100)
    lines = (run / "checked.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    del first["relation"]
    (run / "checked.jsonl").write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n", encoding="utf-8")
    with pytest.raises(ra.AgreementError, match="not version 2"):
        ra.compare(run, export, 1, 100)


def test_main_writes_json_and_markdown_with_seed(tmp_path):
    run, export = _fixture(tmp_path)
    ex = tmp_path / "export.json"
    ex.write_text(json.dumps(export), encoding="utf-8")
    assert ra.main(["--run-dir", str(run), "--export", str(ex), "--seed", "5", "--resamples", "100"]) == 0
    result = json.loads((tmp_path / "agreement.json").read_text(encoding="utf-8"))
    assert result["seed"] == 5 and result["resamples"] == 100 and len(result["export_sha256"]) == 64
    assert "Keep rule R8" in (tmp_path / "agreement.md").read_text(encoding="utf-8")
