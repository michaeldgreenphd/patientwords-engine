"""Tests for the PAB frame builder. Abstract fixture content only (hard rule:
no medical vocabulary in test code - fixtures use appliance language)."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pab_build_frames",
    Path(__file__).resolve().parent.parent / "scripts" / "pab_build_frames.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ROOT = Path(__file__).resolve().parent.parent
REAL_FRAMES = ROOT / "data" / "pab_frames.json"

# Frame fixture: ids deliberately out of file order to exercise the sort.
FRAMES = {
    "frames": [
        {"id": "zz_frame", "template": "{span}, so the pointer moves to the", "elicits": "place"},
        {"id": "aa_frame", "template": "{span}, so the dial turns to a", "elicits": "treatment"},
    ]
}

SECRET_PREIMAGE = "hidden-scenario-basis-text-never-in-output"


def _key(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _group(seed, low_utts, high_utts):
    arms = {}
    if low_utts is not None:
        arms["low"] = [{"run": "r1", "experiment": "0_0", "utterances": low_utts}]
    if high_utts is not None:
        arms["high"] = [{"run": "r1", "experiment": "0_1", "utterances": high_utts}]
    return {"pair_key": _key(seed), "arms": arms}


def _harvest(groups):
    return {"generated_utc": "2026-08-07T00:00:00Z", "groups": groups}


def test_span_extraction_mechanics():
    # greeting stripped (case-insensitive), casing of the span preserved
    assert mod.extract_span("HELLO! the Widget Rattles Loudly") == "the Widget Rattles Loudly"
    assert mod.extract_span("Thank you, the fan spins slowly, can you explain that?") == "the fan spins slowly"
    # first sentence taken
    assert mod.extract_span("Hi, the panel hums all day. It also clicks at night.") == "the panel hums all day"
    # request tail stripped mid-sentence
    assert mod.extract_span("the gadget keeps blinking, could you check it") == "the gadget keeps blinking"
    # pure requests yield no span
    assert mod.extract_span("Can you check the manual?") == ""
    assert mod.extract_span("please look at this now") == ""
    assert mod.extract_span("Hey!") == ""  # bare greeting
    # in-number periods do not cut the clause
    assert mod.extract_span("the reading is 12.5 and rising steadily") == "the reading is 12.5 and rising steadily"


def test_pair_built_only_when_both_arms_yield_and_exclusions_counted():
    groups = [
        _group("both-ok", ["hi, the rotor wobbles a lot"], ["The rotor assembly exhibits wobble."]),
        _group("low-empty", ["Can you check it?"], ["The casing vibrates."]),
        _group("high-missing", ["the belt squeaks"], None),
        _group("both-empty", ["please help"], ["could you advise"]),
    ]
    entries, meta = mod.build(_harvest(groups), FRAMES)
    built_keys = {e["pair_key"] for e in entries}
    assert built_keys == {_key("both-ok")}
    assert meta["exclusions"] == {"missing_arm": 1, "no_span_low": 1, "no_span_high": 0, "no_span_both": 1}
    reasons = {p["pair_key"]: p["reason"] for p in meta["excluded_pairs"]}
    assert reasons[_key("low-empty")] == "no_span_low"
    assert reasons[_key("high-missing")] == "missing_arm"
    assert reasons[_key("both-empty")] == "no_span_both"
    assert meta["counts"] == {"groups_seen": 4, "pairs_built": 1, "frames_used": 2, "entries": 2}


def test_same_frame_for_both_arms_and_entry_shape():
    groups = [_group("g", ["hello, the small lamp flickers"], ["The lamp unit flickers intermittently."])]
    entries, _ = mod.build(_harvest(groups), FRAMES)
    assert len(entries) == 2
    by_frame = {e["frame_id"]: e for e in entries}
    for frame in FRAMES["frames"]:
        entry = by_frame[frame["id"]]
        tail = frame["template"].split("{span}")[1]
        assert entry["top_prompt"].endswith(tail) and entry["bottom_prompt"].endswith(tail)
        # top = high-literacy span, bottom = low-literacy span
        assert entry["top_prompt"].startswith("The lamp unit flickers intermittently")
        assert entry["bottom_prompt"].startswith("the small lamp flickers")
        assert entry["provenance"] == "pabharvest"
        assert entry["generation"]["provenance"] == "pabharvest"
        assert entry["generation"]["frame_class"] == frame["elicits"]
        assert "target_clinical_token" not in entry  # absent without --anchors


def test_anchors_attach_targets_per_frame_and_missing_anchor_errors():
    groups = [_group("g", ["the hinge creaks"], ["The hinge mechanism creaks."])]
    anchors = {"_": "comment ignored", "aa_frame": " alpha", "zz_frame": " beta"}
    entries, meta = mod.build(_harvest(groups), FRAMES, anchors=anchors)
    assert {e["frame_id"]: e["target_clinical_token"] for e in entries} == {"aa_frame": " alpha", "zz_frame": " beta"}
    assert meta["screening"]["screening_ready"] is True
    with pytest.raises(ValueError):
        mod.build(_harvest(groups), FRAMES, anchors={"aa_frame": " alpha"})


def test_deterministic_order_sorted_by_pair_key_then_frame_id():
    seeds = ["s3", "s1", "s2"]
    groups = [_group(s, ["the wheel sticks"], ["The wheel binds under load."]) for s in seeds]
    entries_a, _ = mod.build(_harvest(groups), FRAMES)
    entries_b, _ = mod.build(_harvest(list(reversed(groups))), FRAMES)
    assert entries_a == entries_b
    order = [(e["pair_key"], e["frame_id"]) for e in entries_a]
    assert order == sorted(order)
    assert [fid for _, fid in order[:2]] == ["aa_frame", "zz_frame"]


def test_main_end_to_end_hides_preimage_and_writes_metadata_sidecar(tmp_path):
    groups = [_group(SECRET_PREIMAGE, ["hi, the toaster lever sticks halfway"],
                     ["The lever mechanism sticks at the midpoint."]),
              _group("excluded-one", ["can you have a look"], ["The knob is loose."])]
    harvest_path = tmp_path / "h.json"
    harvest_path.write_text(json.dumps(_harvest(groups)))
    frames_path = tmp_path / "f.json"
    frames_path.write_text(json.dumps(FRAMES))
    out = tmp_path / "pabharvest_test.json"
    rc = mod.main(["--harvest", str(harvest_path), "--frames", str(frames_path), "--out", str(out)])
    assert rc == 0
    batch_text = out.read_text()
    batch = json.loads(batch_text)
    assert isinstance(batch, list) and len(batch) == 2  # 1 built pair x 2 frames
    sidecar = tmp_path / "pabharvest_test.build.json"
    meta = json.loads(sidecar.read_text())
    # metadata block present, exclusions counted, counts consistent
    assert meta["exclusions"]["no_span_low"] == 1
    assert meta["counts"]["entries"] == len(batch) == meta["counts"]["pairs_built"] * meta["counts"]["frames_used"]
    assert meta["screening"]["screening_ready"] is False
    # no preimage of any scenario hash reaches either output
    assert SECRET_PREIMAGE not in batch_text and SECRET_PREIMAGE not in sidecar.read_text()
    assert _key(SECRET_PREIMAGE) in batch_text  # the hash itself is the join key


def test_main_rejects_non_pabharvest_stem(tmp_path):
    harvest_path = tmp_path / "h.json"
    harvest_path.write_text(json.dumps(_harvest([])))
    frames_path = tmp_path / "f.json"
    frames_path.write_text(json.dumps(FRAMES))
    with pytest.raises(SystemExit):
        mod.main(["--harvest", str(harvest_path), "--frames", str(frames_path),
                  "--out", str(tmp_path / "pairs_wrong.json")])


def test_shipped_frames_inventory_is_pure_carrier_syntax():
    data = json.loads(REAL_FRAMES.read_text(encoding="utf-8"))
    frames = mod.load_frames(data)  # validates unique ids + {span} placeholder
    assert 3 <= len(frames) <= 4
    assert {f["elicits"] for f in frames} == {"treatment", "place", "person"}
    for frame in frames:
        assert frame["template"].startswith("{span}")
