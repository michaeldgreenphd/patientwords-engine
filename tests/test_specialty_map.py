"""Specialty taxonomy: shape, uniqueness, and coverage of the live payload."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data" / "specialty_map.draft.json"


def load():
    return json.loads(MAP.read_text(encoding="utf-8"))


def test_shape_and_draft_label():
    d = load()
    assert d["status"].startswith("draft")
    assert isinstance(d["specialties"], dict) and d["specialties"]
    for spec, subs in d["specialties"].items():
        assert isinstance(subs, dict) and subs, spec
        for sub, topics in subs.items():
            assert isinstance(topics, list) and topics, f"{spec}/{sub}"


def test_each_topic_mapped_exactly_once():
    seen = {}
    for spec, subs in load()["specialties"].items():
        for sub, topics in subs.items():
            for t in topics:
                assert t == t.strip().lower(), f"non-normalized topic: {t!r}"
                assert t not in seen, f"{t!r} in both {seen[t]} and {spec}/{sub}"
                seen[t] = f"{spec}/{sub}"
    assert len(seen) > 100


def test_covers_live_payload_topics():
    """Every topic in the published payload maps; new batches may add topics
    (they render as 'Other' on the site) but the map must not silently rot -
    regenerate it when this fails."""
    payload = ROOT / ".." / "patientwords" / "data" / "simulated_scenarios.json"
    if not payload.exists():  # sibling checkout absent in some environments
        return
    mapped = {t for subs in load()["specialties"].values() for ts in subs.values() for t in ts}
    live = set()
    for s in json.loads(payload.read_text(encoding="utf-8")).get("scenarios", []):
        t = s.get("topic") or (s.get("generation") or {}).get("topic")
        if t:
            live.add(t.strip().lower())
    unmapped = sorted(live - mapped)
    assert len(unmapped) <= max(3, len(live) // 20), f"unmapped topics growing: {unmapped}"
