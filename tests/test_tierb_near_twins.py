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

import pytest

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


# --- malformed rows are refused, not dropped (Codex review of PR #32) --------- #
# site_phrases and explore_phrases dropped a non-object row or one without a
# phrase string, shrinking the registered comparison set without a word.

_BAD_ROWS = ["not an object", {"other": 1}, {"clinical_prompt": None}, {"clinical_prompt": 7},
             {"clinical_prompt": "   "}]


def _refuses(sim, ops, site, needle):
    with pytest.raises(nt.MalformedInputError, match=needle):
        nt.compute(str(sim), str(ops / "dashboard.json"), site)


def test_a_malformed_site_row_is_refused_with_a_count(tmp_path, capsys):
    for bad in _BAD_ROWS:
        for name in ("simulated_scenarios.json", "simulated_archive.json"):
            case = tmp_path / f"{_BAD_ROWS.index(bad)}_{name}"
            sim, ops, site, _ = _tree(case)
            path = site / "data" / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload["scenarios"] if isinstance(payload, dict) else payload
            rows.extend([bad, bad])
            path.write_text(json.dumps(payload), encoding="utf-8")
            _refuses(sim, ops, site, f"data/{name}: 2 row")
    out = case / "twins.json"
    sim, ops, site = case / "data" / "simulated", case / "ops", case / "site"
    out.write_text(json.dumps({"twin_labels": [f"{BATCH}#1", f"{BATCH}#2"]}), encoding="utf-8")
    argv = ["--site", str(site), "--simulated", str(sim), "--dashboard", str(ops / "dashboard.json"),
            "--out", str(out)]
    assert nt.main([*argv, "--check"]) == 2 and "refused" in capsys.readouterr().out
    assert nt.main(argv) == 2
    assert json.loads(out.read_text(encoding="utf-8")) == {"twin_labels": [f"{BATCH}#1", f"{BATCH}#2"]}


def test_a_site_payload_of_the_wrong_shape_is_refused(tmp_path):
    sim, ops, site, _ = _tree(tmp_path)
    (site / "data" / "simulated_archive.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    _refuses(sim, ops, site, "simulated_archive.json")
    sim, ops, site, _ = _tree(tmp_path / "b")
    (site / "data" / "simulated_scenarios.json").write_text(json.dumps({"batches": []}), encoding="utf-8")
    _refuses(sim, ops, site, "simulated_scenarios.json")


def test_a_malformed_explore_row_is_refused_with_a_count(tmp_path):
    for i, bad in enumerate(["not an object", {"bottom_prompt": "p"}, {"top_prompt": 3}, {"top_prompt": " "}]):
        sim, ops, site, _ = _tree(tmp_path / str(i))
        path = sim / f"{LATER}.json"
        path.write_text(json.dumps([*json.loads(path.read_text(encoding="utf-8")), bad]), encoding="utf-8")
        _refuses(sim, ops, site, f"{LATER}.json: 1 row")
    sim, ops, site, _ = _tree(tmp_path / "shape")
    (sim / f"{LATER}.json").write_text(json.dumps({"pairs": []}), encoding="utf-8")
    _refuses(sim, ops, site, f"{LATER}.json")


# --- the output fingerprints the engine inputs it read (Codex review of PR #32) #
# inputs recorded only engine_head, which is the same commit (or null) for a
# dirty checkout or custom --simulated/--dashboard paths, so different frozen
# results could carry identical provenance.

def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_inputs_record_the_hash_of_every_engine_file_read(tmp_path):
    sim, ops, site, _ = _tree(tmp_path)
    inputs = nt.compute(str(sim), str(ops / "dashboard.json"), site)["inputs"]
    assert inputs["batch_files_sha256"] == {f"{BATCH}.json": _sha(sim / f"{BATCH}.json"),
                                            f"{LATER}.json": _sha(sim / f"{LATER}.json")}   # no Tier A file
    assert inputs["dashboard_sha256"] == _sha(ops / "dashboard.json")
    tierb = json.loads((ops / "dashboard.json").read_text(encoding="utf-8"))["tierb"]
    canonical = json.dumps(tierb, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert inputs["dashboard_tierb_sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_different_engine_inputs_never_share_provenance(tmp_path):
    sim, ops, site, _ = _tree(tmp_path)
    dash = ops / "dashboard.json"
    first = nt.compute(str(sim), str(dash), site)["inputs"]
    later = sim / f"{LATER}.json"
    later.write_text(json.dumps([*json.loads(later.read_text(encoding="utf-8")),
                                 {"top_prompt": "mm another explore phrase", "bottom_prompt": "p"}]),
                     encoding="utf-8")
    second = nt.compute(str(sim), str(dash), site)["inputs"]
    assert first["engine_head"] == second["engine_head"]            # same commit (here: no repo)
    assert first != second
    assert first["batch_files_sha256"][f"{LATER}.json"] != second["batch_files_sha256"][f"{LATER}.json"]
    # a dashboard rewrite outside the tierb block changes the file hash but not the block's
    payload = json.loads(dash.read_text(encoding="utf-8"))
    payload["queue"] = {"pending": []}
    dash.write_text(json.dumps(payload), encoding="utf-8")
    third = nt.compute(str(sim), str(dash), site)["inputs"]
    assert third["dashboard_sha256"] != second["dashboard_sha256"]
    assert third["dashboard_tierb_sha256"] == second["dashboard_tierb_sha256"]
