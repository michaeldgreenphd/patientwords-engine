"""Mitigation-cost sidecar: the trace run's only paid call must leave a record.

Regression cover for the accounting gap closed 2026-07-31 (owner decision D2).
No sidecar was ever written, so ledger_update booked $0 for every
--show-mitigation run the study fired. No medical vocabulary in this file:
the fixtures are abstract placeholder text.
"""

import json

from medlang_circuits.batch_eval import write_mitigation_sidecar
from medlang_circuits.llm_client import (
    _record_translate_usage,
    reset_translate_usage,
    translate_usage_snapshot,
)


class _Usage:
    def __init__(self, inp, out):
        self.input_tokens = inp
        self.output_tokens = out


def test_no_paid_calls_writes_no_sidecar(tmp_path):
    reset_translate_usage()
    assert write_mitigation_sidecar(tmp_path) is None
    assert not list(tmp_path.glob("*.report.json"))


def test_sidecar_records_measured_usage_and_cost(tmp_path):
    reset_translate_usage()
    # haiku is $1/$5 per Mtok: 1M in + 1M out would be $6; 1000/500 -> $0.0035
    _record_translate_usage("claude-haiku-4-5", _Usage(600, 300))
    _record_translate_usage("claude-haiku-4-5", _Usage(400, 200))
    path = write_mitigation_sidecar(tmp_path, start_index=11)
    assert path is not None and path.name == "mitigation.report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["kind"] == "mitigation"
    assert payload["imputed"] is False          # metered, not estimated
    assert payload["calls"] == 2
    assert payload["input_tokens"] == 1000 and payload["output_tokens"] == 500
    assert payload["start_index"] == 11
    assert payload["cost_usd"] == 0.0035
    assert payload["per_model"]["claude-haiku-4-5"]["calls"] == 2


def test_usage_accumulates_per_model_and_resets(tmp_path):
    reset_translate_usage()
    _record_translate_usage("claude-haiku-4-5", _Usage(100, 50))
    _record_translate_usage("claude-opus-4-8", _Usage(200, 100))
    snap = translate_usage_snapshot()
    assert snap["calls"] == 2
    assert set(snap["models"]) == {"claude-haiku-4-5", "claude-opus-4-8"}
    # opus is priced 5x/5x haiku, so a mixed run must not be billed at one rate
    payload = json.loads(write_mitigation_sidecar(tmp_path).read_text(encoding="utf-8"))
    haiku = payload["per_model"]["claude-haiku-4-5"]["cost_usd"]
    opus = payload["per_model"]["claude-opus-4-8"]["cost_usd"]
    assert opus > haiku * 5
    reset_translate_usage()
    assert translate_usage_snapshot()["calls"] == 0


def test_missing_usage_field_does_not_crash(tmp_path):
    """An SDK that omits usage must still leave a call-count record."""
    reset_translate_usage()
    _record_translate_usage("claude-haiku-4-5", None)
    payload = json.loads(write_mitigation_sidecar(tmp_path).read_text(encoding="utf-8"))
    assert payload["calls"] == 1
    assert payload["cost_usd"] == 0.0
