"""scripts/restamp_payload_summary.py: the summary correction applied to a published payload, alone.

The tool recomputes ``summary`` from the payload's own rows with the corrected producer function and refuses
anything that is not exactly that correction. Rows are abstract placeholders; expected values are worked out by
hand below and not taken from the producer.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import restamp_payload_summary as restamp  # noqa: E402

SITE = ROOT.parent / "patientwords"


def _row(batch: str, index: int, phrase: str, penalty: float | None, **extra) -> dict:
    return {"index": index, "batch": batch, "batch_index": index, "clinical_prompt": phrase,
            "patient_prompt": f"placeholder wording {batch}#{index}", "language_penalty": penalty,
            "flipped": False, "screening": None, "models": {"gemma-2-2b": {"language_penalty": penalty}}, **extra}


def _legacy_payload() -> dict:
    """Four scored rows; 'placeholder phrase A' occurs in two different batches.

    Row mean: (-0.4 - 0.2 - 0.1 + 0.1) / 4 = -0.15.
    Phrase means: A (-0.4 - 0.2) / 2 = -0.3; B -0.1; C 0.1. Three phrases, mean (-0.3 - 0.1 + 0.1) / 3 = -0.1.
    The summary below is what the producer wrote before the correction: one phrase per scored row.
    """
    scenarios = [_row("b1", 1, "placeholder phrase A", -0.4), _row("b2", 1, "placeholder phrase A", -0.2),
                 _row("b2", 2, "placeholder phrase B", -0.1), _row("b2", 3, "placeholder phrase C", 0.1),
                 _row("b2", 4, "placeholder phrase D", None, screening={"status": "screened_out"})]
    summary = restamp.build_summary(scenarios, 6, 1, base_model="gemma-2-2b")
    summary["penalty"].update(n_phrases=4, mean_phrase_deduped=-0.15, ci95=[-0.325, 0.025])
    return {"batches": [], "summary": summary, "holdout_withheld": 1, "scenarios": scenarios,
            "urgency_meta": {"note": "untouched"}}


def _write(site: Path, payload: dict, indent: int | None = 2) -> Path:
    path = site / "data" / "simulated_scenarios.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=indent) + "\n", encoding="utf-8")
    return path


def test_the_legacy_summary_is_corrected_and_nothing_else_in_the_file_changes(tmp_path, capsys):
    payload = _legacy_payload()
    path = _write(tmp_path, payload)
    before = path.read_bytes()
    assert restamp.main(["--site", str(tmp_path), "--dry-run"]) == 0
    assert path.read_bytes() == before and "DRY RUN" in capsys.readouterr().out
    assert restamp.main(["--site", str(tmp_path)]) == 0
    after = json.loads(path.read_text(encoding="utf-8"))
    pen = after["summary"]["penalty"]
    assert (pen["n_phrases"], pen["mean_phrase_deduped"]) == (3, -0.1)          # by hand, see _legacy_payload
    assert (pen["n_scored_rows"], pen["mean_rows_raw"]) == (4, -0.15)           # unchanged
    assert pen["ci95"] is not None and pen["ci95"][0] <= -0.1 <= pen["ci95"][1]
    # every part of the payload outside summary.penalty is the same object, and the file keeps the exporter's form
    assert {k: v for k, v in after.items() if k != "summary"} == {k: v for k, v in payload.items() if k != "summary"}
    assert {k: v for k, v in after["summary"].items() if k != "penalty"} == \
        {k: v for k, v in payload["summary"].items() if k != "penalty"}
    assert path.read_bytes() == (json.dumps(after, indent=2) + "\n").encode("utf-8")
    out = capsys.readouterr().out
    assert "summary.penalty.n_phrases: 4 -> 3" in out and "mean_phrase_deduped: -0.15 -> -0.1" in out
    assert hashlib.sha256(before).hexdigest() in out
    # a second run finds the corrected summary and writes nothing
    stamp = path.stat().st_mtime_ns
    assert restamp.main(["--site", str(tmp_path)]) == 0
    assert path.stat().st_mtime_ns == stamp and "already holds the corrected summary" in capsys.readouterr().out


@pytest.mark.parametrize("mutate, reason", [
    (lambda p: p["summary"]["totals"].update(measured=99), "outside the corrected fields (totals)"),
    (lambda p: p["summary"]["penalty"].update(n_scored_rows=5), "outside the corrected fields (penalty.n_scored_rows)"),
    (lambda p: p["summary"]["penalty"].update(n_phrases=999999, mean_phrase_deduped=0.75), "neither the pre-correction"),
    (lambda p: p["scenarios"][0].update(language_penalty=-0.9), "outside the corrected fields"),
    (lambda p: p["summary"].pop("totals"), "no 'totals'"),
    (lambda p: p.pop("scenarios"), "no 'scenarios' list"),
])
def test_anything_that_is_not_exactly_the_correction_is_refused_and_nothing_is_written(tmp_path, capsys, mutate, reason):
    payload = _legacy_payload()
    mutate(payload)
    path = _write(tmp_path, payload)
    before = path.read_bytes()
    assert restamp.main(["--site", str(tmp_path)]) == 2
    assert path.read_bytes() == before
    assert reason in capsys.readouterr().err


def test_a_file_that_is_not_in_the_exporters_form_is_refused(tmp_path, capsys):
    path = _write(tmp_path, _legacy_payload(), indent=1)
    before = path.read_bytes()
    assert restamp.main(["--site", str(tmp_path)]) == 2
    assert path.read_bytes() == before and "exporter's own serialization" in capsys.readouterr().err
    assert restamp.main(["--site", str(tmp_path / "absent")]) == 2


def test_the_published_payload_is_either_restampable_or_already_correct():
    """Real data, read-only. The phrase count is recounted here without the producer: distinct clinical prompts
    among scored, non-steered rows, a row with no prompt counting as its own phrase."""
    path = SITE / "data" / "simulated_scenarios.json"
    if not path.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    payload = json.loads(path.read_text(encoding="utf-8"))
    scored = [s for s in payload["scenarios"] if not s.get("steered")
              and isinstance(s.get("language_penalty"), (int, float)) and not isinstance(s.get("language_penalty"), bool)]
    phrases = {s.get("clinical_prompt") or f"{s.get('batch')}#{s.get('batch_index')}" for s in scored}
    summary, change = restamp.restamp(payload)
    assert summary["penalty"]["n_scored_rows"] == len(scored)
    assert summary["penalty"]["n_phrases"] == len(phrases)
    assert set(change) <= set(restamp.CORRECTED_FIELDS)
    if change:                                   # still the published pre-correction block
        assert payload["summary"]["penalty"]["n_phrases"] == len(scored)
