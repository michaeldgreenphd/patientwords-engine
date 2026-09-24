"""Census-table swap exporter (scripts/export_pair_swaps.py) - offline.

Pins the patient-swap span extraction, the batch build keyed by stem#index, the
block-id scoping from a depth payload, the empty-input refusal, and (owner
ruling 3, 2026-09-23) the Tier B holdout withholding with its published count
and its refusal when the holdout set cannot be computed. No network.
"""

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

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


def _git(repo, *argv):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@x", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *argv], check=True, capture_output=True)


def _commit(repo, *paths):
    """git init ``repo`` if needed and commit ``paths`` (default: everything)."""
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "add", "-A", "--", *(paths or (".",)))
    _git(repo, "commit", "-q", "--allow-empty", "-m", "x")


def _engine(tmp_path, with_start=True, probe_in="model", commit=True):
    """Tier B batch TIERB traced into a base dir and a model dir, as on the live
    store. Row 3's accepted prompt hashes explore; its trace-time prompt in the
    ``probe_in`` dir ("base" or "model") hashes holdout, and the other dir traced
    the accepted prompt. With ``commit`` the tree is a git repo at HEAD."""
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
    for where, name in (("base", TIERB), ("model", f"{TIERB}__some-model")):
        trace = tmp_path / "trace_out" / name
        trace.mkdir(parents=True)
        third = probed_trace if where == probe_in else probed
        (trace / "batch_summary.part_01.json").write_text(json.dumps({"results": [
            {"index": i, "prompts": {"clinical": c, "patient": "x"}}
            for i, c in ((1, sealed), (2, explore), (3, third))]}), encoding="utf-8")
    if commit:
        _commit(tmp_path)
    return sim, ops


def test_holdout_rows_are_withheld_by_every_reading_of_the_rule(tmp_path):
    sim, ops = _engine(tmp_path)
    rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), str(tmp_path / "trace_out"))
    withheld = []
    swaps = ext.build_swaps([TIERB, TIER_A, ALIAS], str(sim), rule, withheld)
    assert sorted(withheld) == [f"{TIERB}#1", f"{TIERB}#3", f"{ALIAS}#1"]
    assert set(swaps) == {f"{TIERB}#2", f"{TIER_A}#1", f"{ALIAS}#2"}


# --- the trace-time reading fails closed (Codex review of PR #32, 2026-09-23) -- #
# An absent or unreadable trace source used to read as "no trace-time prompts",
# so a row whose accepted prompt hashes explore but whose trace-time prompt
# hashes holdout (TIERB#3 above) published its patient sentence. The first fix
# refused only when no model's dir had any part, so a checkout missing the one
# dir that carries the probe-extended prompt still published it (second review).
# The parts HEAD tracks are now compared with the parts on disk.

UNTRACED = "pairs_20260712T000000Z"      # a Tier B batch with no part at HEAD and none on disk


def _refused(fn):
    try:
        fn()
    except ext.TraceStoreError as exc:
        return str(exc)
    raise AssertionError("the rule read an absent trace source as empty")


def _main_args(tmp_path, sim, ops, depth, out, trace):
    return ["--simulated-dir", str(sim), "--depth", str(depth), "--insights", "", "--out", str(out),
            "--site", "", "--dashboard", str(ops / "dashboard.json"), "--trace-out", str(trace)]


def test_without_a_trace_store_the_rule_refuses(tmp_path):
    sim, ops = _engine(tmp_path)
    for root in (None, str(tmp_path / "no_such_trace_out")):
        rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), root)
        assert "trace store" in _refused(lambda: ext.build_swaps([TIERB], str(sim), rule, []))


def test_main_refuses_a_missing_trace_store_and_writes_nothing(tmp_path, capsys):
    sim, ops = _engine(tmp_path)
    depth = tmp_path / "jlens_depth.json"
    depth.write_text(json.dumps({"blocks": [{"id": TIERB}]}), encoding="utf-8")
    out = tmp_path / "jlens_swaps.json"
    out.write_text('{"kept": 1}', encoding="utf-8")
    rc = ext.main(_main_args(tmp_path, sim, ops, depth, out, tmp_path / "trace_outs"))   # misspelled
    assert rc == 2 and "trace store" in capsys.readouterr().out
    assert out.read_text() == '{"kept": 1}'


@pytest.mark.parametrize("probe_in", ["base", "model"])
@pytest.mark.parametrize("gone", ["probe dir", "probe part", "other part", "every dir"])
def test_a_trace_part_head_tracks_but_the_checkout_lacks_refuses(tmp_path, probe_in, gone):
    sim, ops = _engine(tmp_path, probe_in=probe_in)
    trace = tmp_path / "trace_out"
    dirs = {"base": trace / TIERB, "model": trace / f"{TIERB}__some-model"}
    rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), str(trace))
    withheld = []
    ext.build_swaps([TIERB], str(sim), rule, withheld)
    assert withheld == [f"{TIERB}#1", f"{TIERB}#3"]       # full checkout: the trace-time prompt is read
    other = "model" if probe_in == "base" else "base"
    if gone == "probe dir":
        shutil.rmtree(dirs[probe_in])
    elif gone == "probe part":
        (dirs[probe_in] / "batch_summary.part_01.json").unlink()
    elif gone == "other part":
        (dirs[other] / "batch_summary.part_01.json").unlink()
    else:
        shutil.rmtree(dirs["base"])
        shutil.rmtree(dirs["model"])
    rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), str(trace))
    refusal = _refused(lambda: ext.build_swaps([TIERB], str(sim), rule, []))
    assert TIERB in refusal and "not on disk" in refusal


def test_main_refuses_when_the_base_dir_holding_the_probe_is_missing(tmp_path, capsys):
    # The live case: the three rows withheld only by a trace-time prompt carry it
    # in the base dir alone; a checkout without it still holds model dirs' parts.
    sim, ops = _engine(tmp_path, probe_in="base")
    shutil.rmtree(tmp_path / "trace_out" / TIERB)
    depth = tmp_path / "jlens_depth.json"
    depth.write_text(json.dumps({"blocks": [{"id": TIERB}]}), encoding="utf-8")
    out = tmp_path / "jlens_swaps.json"
    out.write_text('{"kept": 1}', encoding="utf-8")
    rc = ext.main(_main_args(tmp_path, sim, ops, depth, out, tmp_path / "trace_out"))
    printed = capsys.readouterr().out
    assert rc == 2 and printed.startswith("CONFIG ERROR") and f"{TIERB}/batch_summary.part_01.json" in printed
    assert out.read_text() == '{"kept": 1}'


def test_a_tierb_batch_not_traced_on_this_branch_uses_its_accepted_prompt(tmp_path, capsys):
    sim, ops = _engine(tmp_path)
    (sim / f"{UNTRACED}.json").write_text(json.dumps([
        {"top_prompt": _phrase("zq untraced words", False), "bottom_prompt": "b", "target_clinical_token": " t"},
        {"top_prompt": _phrase("zq untraced sealed", True), "bottom_prompt": "c", "target_clinical_token": " t"}]),
        encoding="utf-8")
    rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), str(tmp_path / "trace_out"))
    withheld = []
    assert set(ext.build_swaps([UNTRACED], str(sim), rule, withheld)) == {f"{UNTRACED}#1"}
    assert withheld == [f"{UNTRACED}#2"]
    # Tier A and alias stems never consult the trace store, so they need no trace dir
    assert set(ext.build_swaps([TIER_A, ALIAS], str(sim), rule, [])) == {f"{TIER_A}#1", f"{ALIAS}#2"}
    depth = tmp_path / "jlens_depth.json"
    depth.write_text(json.dumps({"blocks": [{"id": TIERB}, {"id": UNTRACED}]}), encoding="utf-8")
    out = tmp_path / "jlens_swaps.json"
    rc = ext.main(_main_args(tmp_path, sim, ops, depth, out, tmp_path / "trace_out"))
    assert rc == 0, capsys.readouterr().out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["holdout_withheld"] == 3
    assert set(payload["swaps"]) == {f"{TIERB}#2", f"{UNTRACED}#1"}


def test_the_rule_refuses_when_git_cannot_say_which_parts_head_tracks(tmp_path):
    no_git = tmp_path / "no_git"
    _engine(no_git, commit=False)
    no_commit = tmp_path / "no_commit"
    _engine(no_commit, commit=False)
    subprocess.run(["git", "init", "-q", "-b", "main", str(no_commit)], check=True, capture_output=True)
    untracked = tmp_path / "untracked"
    _engine(untracked, commit=False)
    _commit(untracked, "data", "ops")                    # HEAD tracks nothing under trace_out/
    for repo, expected in ((no_git, "cannot list"), (no_commit, "cannot list"), (untracked, "tracks no file")):
        rule = ext.HoldoutRule(str(repo / "data" / "simulated"), str(repo / "ops" / "dashboard.json"),
                               str(repo / "trace_out"))
        refusal = _refused(lambda: ext.build_swaps([TIERB], str(repo / "data" / "simulated"), rule, []))
        assert expected in refusal, (repo.name, refusal)


def test_an_unreadable_or_malformed_trace_part_refuses(tmp_path):
    for n, bad in enumerate(("{not json", json.dumps([1, 2]), json.dumps({"results": [{"index": 3}]}),
                             json.dumps({"results": [{"index": "3", "prompts": {"clinical": "zq x"}}]}))):
        case = tmp_path / f"case{n}"
        sim, ops = _engine(case)
        (case / "trace_out" / f"{TIERB}__some-model" / "batch_summary.part_01.json").write_text(bad, encoding="utf-8")
        rule = ext.HoldoutRule(str(sim), str(ops / "dashboard.json"), str(case / "trace_out"))
        assert TIERB in _refused(lambda: ext.build_swaps([TIERB], str(sim), rule, [])), bad


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
