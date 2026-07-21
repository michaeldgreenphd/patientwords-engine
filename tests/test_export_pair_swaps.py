"""Census-table swap exporter (scripts/export_pair_swaps.py) - offline.

Pins the patient-swap span extraction, the batch build keyed by stem#index, the
block-id scoping from a depth payload, and the empty-input refusal. No network.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_pair_swaps", _ROOT / "scripts" / "export_pair_swaps.py")
ext = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ext)


def test_patient_swap_takes_differing_patient_span():
    swap = ext.patient_swap("I have tachycardia, so I need a",
                            "My heart keeps racing, so I need a")
    assert swap == "My heart keeps racing"


def test_patient_swap_none_when_identical():
    assert ext.patient_swap("same words here", "same words here") is None


def test_patient_swap_trims_long_span_at_word_boundary():
    long_patient = "my heart has been pounding and racing nonstop all day and night, so"
    swap = ext.patient_swap("I have tachycardia, so", long_patient)
    assert swap.endswith("…") and len(swap) <= 46 and " " in swap
    assert "pounding" in swap


def test_build_swaps_keys_and_fields(tmp_path):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_X.json").write_text(json.dumps([
        {"top_prompt": "I have tachycardia, so I should see a",
         "bottom_prompt": "My heart keeps racing, so I should see a",
         "target_clinical_token": " cardiologist"},
        {"top_prompt": "a b c", "bottom_prompt": "a b c", "target_clinical_token": " x"},
    ]), encoding="utf-8")
    swaps = ext.build_swaps(["pairs_X"], str(sim))
    assert set(swaps) == {"pairs_X#1", "pairs_X#2"}
    assert swaps["pairs_X#1"] == {
        "target": "cardiologist", "swap": "My heart keeps racing",
        "baseline": "My heart keeps racing, so I should see a"}
    assert swaps["pairs_X#2"]["swap"] is None            # identical prompts


def test_build_swaps_skips_missing_batch(tmp_path):
    sim = tmp_path / "sim"
    sim.mkdir()
    assert ext.build_swaps(["does_not_exist"], str(sim)) == {}


def test_block_stems_reads_depth_payload(tmp_path):
    depth = tmp_path / "jlens_depth.json"
    depth.write_text(json.dumps({"blocks": [{"id": "pairs_A"}, {"id": "urgency_B"}, {}]}),
                     encoding="utf-8")
    assert ext.block_stems(str(depth)) == ["pairs_A", "urgency_B"]
    assert ext.block_stems(str(tmp_path / "missing.json")) == []


def test_insights_datasets_widen_beyond_census(tmp_path):
    # points reference a drift_sentinel track NOT in the depth census -> its base
    # sentence must still be covered so hijack tooltips work on every track.
    insights = tmp_path / "jlens_insights.json"
    insights.write_text(json.dumps({"points": [
        {"dataset": "pairs_A", "index": 1}, {"dataset": "drift_sentinel_20260720", "index": 1},
        {"dataset": "drift_sentinel_20260720", "index": 2}, {"index": 3}]}), encoding="utf-8")
    assert ext.insights_datasets(str(insights)) == ["drift_sentinel_20260720", "pairs_A"]
    assert ext.insights_datasets(str(tmp_path / "missing.json")) == []


def test_main_refuses_without_blocks(tmp_path, capsys):
    out = tmp_path / "jlens_swaps.json"
    out.write_text('{"kept": 1}', encoding="utf-8")
    depth = tmp_path / "empty_depth.json"
    depth.write_text(json.dumps({"blocks": []}), encoding="utf-8")
    rc = ext.main(["--depth", str(depth), "--insights", "", "--out", str(out), "--site", ""])
    assert rc == 3
    assert "refused" in capsys.readouterr().out
    assert out.read_text() == '{"kept": 1}'              # untouched
