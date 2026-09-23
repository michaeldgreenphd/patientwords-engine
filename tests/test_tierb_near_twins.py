"""Near-twin list for Tier B Amendment 5 (scripts/tierb_near_twins.py) - offline.

Pins the registered definition on synthetic data: the difflib ratio on
seal_check.norm text, sealed phrase first, twin iff the best ratio is >= 0.90
(the boundary counts); a case or spacing variant of a sealed phrase is a
different string and scores 1.0; the comparison set is the explore split plus
the site's per-row payloads; the count is re-derived from inputs, the output
carries labels and counts only, and --check fails when the frozen list and a
recomputation disagree. Synthetic abstract phrases only.
"""

import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("tierb_near_twins", _ROOT / "scripts" / "tierb_near_twins.py")
nt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(nt)

BATCH = "pairs_20260711T000000Z"
LATER = "pairs_20260801T000000Z"


def _hold(p):
    return int(hashlib.sha1(p.encode()).hexdigest(), 16) % 10 == 0


def _pick(template, holdout):
    return next(template.format(i) for i in range(2000) if _hold(template.format(i)) == holdout)


def test_threshold_boundary_counts_and_below_does_not():
    assert difflib.SequenceMatcher(None, "abcdefghij", "abcdefghiX").ratio() == 0.9
    sealed = {"abcdefghij": "b#1", "klmnopqrst": "b#2"}
    assert nt.near_twins(sealed, ["abcdefghiX"]) == ["b#1"]           # exactly 0.90: a twin
    assert nt.near_twins(sealed, ["abcdefghXY", "klmnopXYZW"]) == []   # 0.80 and 0.60: not


def test_case_and_spacing_variants_are_perfect_twins():
    sealed = {"alpha beta gamma delta": "b#1"}
    assert nt.near_twins(sealed, ["ALPHA  beta\tgamma delta"]) == ["b#1"]


def test_labels_of_one_normalized_phrase_are_all_twins_together():
    sealed = {"alpha beta gamma": "b#1", "Alpha Beta Gamma": "b#2"}
    assert nt.near_twins(sealed, ["alpha beta gamma!"]) == ["b#1", "b#2"]


def _tree(tmp_path):
    """Synthetic engine + site: 3 sealed phrases, 1 with an explore twin, 1 with
    a twin only on the site, 1 with no twin."""
    sealed_a = _pick("zq one two three four five six seven {} x", True)
    sealed_b = _pick("zq red green blue cyan teal lime {} y", True)
    sealed_c = _pick("zq {} unrelated words stand far apart", True)
    explore_twin = _pick(sealed_a + "{}", False)         # sealed_a plus a digit: ratio > 0.97
    explore_far = _pick("mm {} nothing like the others here", False)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    rows = [{"top_prompt": t, "bottom_prompt": "p"} for t in (sealed_a, sealed_b, sealed_c)]
    (sim / f"{BATCH}.json").write_text(json.dumps(rows), encoding="utf-8")
    (sim / f"{LATER}.json").write_text(json.dumps(
        [{"top_prompt": t, "bottom_prompt": "p"} for t in (explore_twin, explore_far)]), encoding="utf-8")
    (sim / "pairs_20260701T000000Z.json").write_text(json.dumps(   # Tier A: not in the explore split
        [{"top_prompt": sealed_c + ".", "bottom_prompt": "p"}]), encoding="utf-8")
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "dashboard.json").write_text(json.dumps({"tierb": {
        "start_utc": "2026-07-10T01:14:38Z", "batches": [{"file": f"{BATCH}.json"}]}}), encoding="utf-8")
    site = tmp_path / "site" / "data"
    site.mkdir(parents=True)
    (site / "simulated_scenarios.json").write_text(json.dumps({"scenarios": [
        {"clinical_prompt": sealed_b.replace("teal", "tea1")},     # one character off: a site-only twin
        {"clinical_prompt": sealed_a}]}), encoding="utf-8")          # a leak is not a comparison phrase
    (site / "simulated_archive.json").write_text(json.dumps([{"clinical_prompt": explore_far}]),
                                                 encoding="utf-8")
    return sim, ops, tmp_path / "site", (sealed_a, sealed_b, sealed_c)


def test_compute_rederives_the_count_from_inputs(tmp_path):
    sim, ops, site, sealed = _tree(tmp_path)
    result = nt.compute(str(sim), str(ops / "dashboard.json"), site)
    assert result["twin_labels"] == [f"{BATCH}#1", f"{BATCH}#2"]
    c = result["counts"]
    assert (c["sealed_phrases"], c["twins"], c["remaining_after_pruning"]) == (3, 2, 1)
    assert (c["campaign_sealed_phrases"], c["campaign_twins"]) == (3, 2)
    assert result["method"]["threshold"] == 0.90 and result["method"]["seed"] is None
    text = json.dumps(result)
    assert not any(p in text for p in sealed), "labels and counts only"


def test_check_passes_on_the_frozen_list_and_fails_on_a_changed_one(tmp_path, capsys):
    sim, ops, site, _ = _tree(tmp_path)
    out = tmp_path / "twins.json"
    argv = ["--site", str(site), "--simulated", str(sim), "--dashboard", str(ops / "dashboard.json"),
            "--out", str(out)]
    assert nt.main(argv) == 0
    first = out.read_text(encoding="utf-8")
    assert nt.main([*argv, "--check"]) == 0
    assert out.read_text(encoding="utf-8") == first                  # --check writes nothing
    frozen = json.loads(first)
    frozen["twin_labels"] = [f"{BATCH}#1"]
    out.write_text(json.dumps(frozen), encoding="utf-8")
    assert nt.main([*argv, "--check"]) == 1
    assert "MISMATCH" in capsys.readouterr().out


def test_missing_site_payload_is_an_error_not_an_empty_set(tmp_path):
    sim, ops, site, _ = _tree(tmp_path)
    (site / "data" / "simulated_archive.json").unlink()
    try:
        nt.compute(str(sim), str(ops / "dashboard.json"), site)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("a missing site payload silently shrank the comparison set")


def test_committed_frozen_list_is_labels_only_and_consistent():
    frozen = json.loads((_ROOT / "data" / "tierb_near_twins.json").read_text(encoding="utf-8"))
    labels = frozen["twin_labels"]
    c = frozen["counts"]
    assert len(labels) == len(set(labels)) == c["twins"]
    assert c["remaining_after_pruning"] == c["sealed_phrases"] - c["twins"]
    assert all(lab.count("#") == 1 and lab.startswith("pairs_") for lab in labels)
    assert frozen["method"]["threshold"] == 0.90 and frozen["registered"] == "2026-09-23"
