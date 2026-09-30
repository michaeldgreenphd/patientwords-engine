"""Specialty taxonomy: shape, uniqueness, and coverage of the live payload.

The coverage test reads the site checkout: `$PW_SITE_ROOT` when that variable is
set (it must then be a directory, or the test fails), and `../patientwords` next
to this repository otherwise. When that default sibling is absent the test skips
with a visible reason; before 2026-09-30 it returned early and counted as a pass,
which hid the known coverage failure in every layout without the sibling. A site
checkout that lacks `data/simulated_scenarios.json` fails rather than skips.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data" / "specialty_map.draft.json"


def load():
    return json.loads(MAP.read_text(encoding="utf-8"))


def resolve_site_root(engine_root: Path = ROOT) -> Path:
    """The site checkout to read, or a skip when the default sibling is absent."""
    override = os.environ.get("PW_SITE_ROOT")
    if override:
        root = Path(override).expanduser()
        if not root.is_dir():
            pytest.fail(f"PW_SITE_ROOT={override!r} is not a directory")
        return root
    root = engine_root.parent / "patientwords"
    if not root.is_dir():
        pytest.skip(f"sibling checkout ../patientwords absent ({root}); set PW_SITE_ROOT to point at one")
    return root


@pytest.fixture
def site_root() -> Path:
    return resolve_site_root()


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


def test_covers_live_payload_topics(site_root):
    """Every topic in the published payload maps; new batches may add topics
    (they render as 'Other' on the site) but the map must not silently rot -
    regenerate it when this fails."""
    payload = site_root / "data" / "simulated_scenarios.json"
    mapped = {t for subs in load()["specialties"].values() for ts in subs.values() for t in ts}
    live = set()
    for s in json.loads(payload.read_text(encoding="utf-8")).get("scenarios", []):
        t = s.get("topic") or (s.get("generation") or {}).get("topic")
        if t:
            live.add(t.strip().lower())
    unmapped = sorted(live - mapped)
    assert len(unmapped) <= max(3, len(live) // 20), f"unmapped topics growing: {unmapped}"


# --- where the coverage test reads the site from ---------------------------------------------


def test_absent_sibling_skips_instead_of_passing(monkeypatch, tmp_path):
    monkeypatch.delenv("PW_SITE_ROOT", raising=False)
    (tmp_path / "engine").mkdir()
    with pytest.raises(pytest.skip.Exception, match=r"sibling checkout \.\./patientwords absent"):
        resolve_site_root(tmp_path / "engine")
    (tmp_path / "patientwords").mkdir()
    assert resolve_site_root(tmp_path / "engine") == tmp_path / "patientwords"


def test_site_root_override_wins_and_must_exist(monkeypatch, tmp_path):
    (tmp_path / "engine").mkdir()
    (tmp_path / "patientwords").mkdir()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setenv("PW_SITE_ROOT", str(tmp_path / "elsewhere"))
    assert resolve_site_root(tmp_path / "engine") == tmp_path / "elsewhere"
    monkeypatch.setenv("PW_SITE_ROOT", str(tmp_path / "missing"))
    with pytest.raises(pytest.fail.Exception, match="PW_SITE_ROOT"):
        resolve_site_root(tmp_path / "engine")


def _write_payload(site: Path, topics: list[str]) -> Path:
    (site / "data").mkdir(parents=True)
    scenarios = [{"topic": t} for t in topics]
    (site / "data" / "simulated_scenarios.json").write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")
    return site


def test_coverage_check_reads_the_site_it_is_given(tmp_path):
    """The coverage test reads the payload under the site root it is given, not a
    fixed path: a payload of mapped topics passes, one of placeholders fails."""
    mapped = sorted({t for subs in load()["specialties"].values() for ts in subs.values() for t in ts})
    test_covers_live_payload_topics(_write_payload(tmp_path / "covered", mapped[:25]))
    unmapped = [f"placeholder-topic-{i:02d}" for i in range(25)]
    with pytest.raises(AssertionError, match="unmapped topics growing"):
        test_covers_live_payload_topics(_write_payload(tmp_path / "uncovered", unmapped))


def test_site_without_the_payload_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        test_covers_live_payload_topics(tmp_path)
