"""Census-table swap exporter (scripts/export_pair_swaps.py) - offline.

Pins the patient-swap span extraction, the batch build keyed by stem#index, the
block-id scoping from a depth payload, the empty-input refusal, and (owner
ruling 3, 2026-09-23) the Tier B holdout withholding with its published count
and its refusal when the holdout set cannot be computed. No network.
"""

import hashlib
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


# --- Tier B holdout withholding (owner ruling 3, 2026-09-23) ------------------ #
# Synthetic abstract phrases only; the split is sha1(accepted clinical prompt)
# mod 10 == 0, computed here to pick phrases on either side of it.

TIERB = "pairs_20260711T000000Z"        # after the synthetic tierb.start_utc
TIER_A = "pairs_20260701T000000Z"       # before it: never split
ALIAS = "pairs_20260711T000000Z_txopus"  # alias stem: sealed by phrase only


def _hold(p):
    return int(hashlib.sha1(p.encode()).hexdigest(), 16) % 10 == 0


def _phrase(base, holdout):
    return next(f"{base} {i} so a" for i in range(500) if _hold(f"{base} {i} so a") == holdout)


def _engine(tmp_path, with_start=True):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    ops = tmp_path / "ops"
    ops.mkdir()
    tierb = {"start_utc": "2026-07-10T01:14:38Z"} if with_start else {}
    (ops / "dashboard.json").write_text(json.dumps({"tierb": tierb}), encoding="utf-8")
    sealed = _phrase("zq sealed words", True)
    explore = _phrase("zq open words", False)
    probed = _phrase("zq probed words", False)      # accepted explore; traced prompt hashes holdout
    probed_trace = _phrase(probed, True)
    tier_a = _phrase("zq early words", True)        # hashes holdout but predates Tier B

    def row(top):
        return {"top_prompt": top, "bottom_prompt": f"{top} but plainer", "target_clinical_token": " tok"}

    (sim / f"{TIERB}.json").write_text(json.dumps([row(sealed), row(explore), row(probed)]),
                                       encoding="utf-8")
    (sim / f"{TIER_A}.json").write_text(json.dumps([row(tier_a)]), encoding="utf-8")
    (sim / f"{ALIAS}.json").write_text(json.dumps([row(sealed), row(explore)]), encoding="utf-8")
    trace = tmp_path / "trace_out" / f"{TIERB}__some-model"
    trace.mkdir(parents=True)
    (trace / "batch_summary.part_01.json").write_text(json.dumps({"results": [
        {"index": 3, "prompts": {"clinical": probed_trace, "patient": "x"}}]}), encoding="utf-8")
    return sim, ops


def test_holdout_rows_are_withheld_by_every_reading_of_the_rule(tmp_path):
    sim, ops = _engine(tmp_path)
    rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), str(tmp_path / "trace_out"))
    withheld = []
    swaps = ext.build_swaps([TIERB, TIER_A, ALIAS], str(sim), rule, withheld)
    assert sorted(withheld) == [f"{TIERB}#1", f"{TIERB}#3", f"{ALIAS}#1"]
    assert set(swaps) == {f"{TIERB}#2", f"{TIER_A}#1", f"{ALIAS}#2"}


def test_without_a_trace_store_only_the_accepted_prompt_counts(tmp_path):
    sim, ops = _engine(tmp_path)
    rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), None)
    withheld = []
    ext.build_swaps([TIERB], str(sim), rule, withheld)
    assert withheld == [f"{TIERB}#1"]


def test_main_publishes_the_withheld_count_and_no_holdout_key(tmp_path, capsys):
    sim, ops = _engine(tmp_path)
    depth = tmp_path / "jlens_depth.json"
    depth.write_text(json.dumps({"blocks": [{"id": TIERB}, {"id": ALIAS}]}), encoding="utf-8")
    out = tmp_path / "out" / "jlens_swaps.json"
    rc = ext.main(["--simulated-dir", str(sim), "--depth", str(depth), "--insights", "",
                   "--out", str(out), "--site", "", "--dashboard", str(ops / "dashboard.json"),
                   "--trace-out", str(tmp_path / "trace_out")])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["holdout_withheld"] == 3
    assert set(payload["swaps"]) == {f"{TIERB}#2", f"{ALIAS}#2"}
    assert "3 confirmatory-holdout pairs withheld" in capsys.readouterr().out


def test_main_refuses_when_the_holdout_set_cannot_be_computed(tmp_path, capsys):
    sim, ops = _engine(tmp_path, with_start=False)
    depth = tmp_path / "jlens_depth.json"
    depth.write_text(json.dumps({"blocks": [{"id": TIERB}]}), encoding="utf-8")
    out = tmp_path / "jlens_swaps.json"
    out.write_text('{"kept": 1}', encoding="utf-8")
    rc = ext.main(["--simulated-dir", str(sim), "--depth", str(depth), "--insights", "",
                   "--out", str(out), "--site", "", "--dashboard", str(ops / "dashboard.json")])
    assert rc == 2 and "CONFIG ERROR" in capsys.readouterr().out
    assert out.read_text() == '{"kept": 1}'              # nothing published unfiltered
