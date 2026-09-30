"""Claim-drift check: prose snippets vs values recomputed from data sources.

The live-manifest test reads the site checkout: `$PW_SITE_ROOT` when that
variable is set (it must then be a directory, or the test fails), and
`../patientwords` next to this repository otherwise. When that default sibling is
absent the test skips with a visible reason; before 2026-09-30 it returned early
and counted as a pass.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.claim_check import check, evaluate

ROOT = Path(__file__).resolve().parents[1]


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


def write_site(tmp_path: Path, page_text: str, source: dict):
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    (site / "page.html").write_text(page_text, encoding="utf-8")
    (site / "data" / "source.json").write_text(json.dumps(source), encoding="utf-8")
    return site


def write_manifest(tmp_path: Path, claims: list):
    path = tmp_path / "claims_manifest.json"
    path.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    return path


CLAIM = {"page": "page.html", "snippet": "the value is 42",
         "source": "data/source.json", "expr": "d['value']", "expected": 42}


def test_clean_pass(tmp_path):
    site = write_site(tmp_path, "<p>the value is 42</p>", {"value": 42})
    manifest = write_manifest(tmp_path, [CLAIM])
    failures, warnings = check(manifest, site)
    assert failures == [] and warnings == []


def test_value_drift_is_failure(tmp_path):
    site = write_site(tmp_path, "<p>the value is 42</p>", {"value": 43})
    manifest = write_manifest(tmp_path, [CLAIM])
    failures, warnings = check(manifest, site)
    assert len(failures) == 1 and "DRIFT" in failures[0]
    assert warnings == []


def test_missing_snippet_is_warning_not_failure(tmp_path):
    site = write_site(tmp_path, "<p>rewritten prose</p>", {"value": 42})
    manifest = write_manifest(tmp_path, [CLAIM])
    failures, warnings = check(manifest, site)
    assert failures == []
    assert len(warnings) == 1 and "update the manifest" in warnings[0]


def test_snippet_alt_fallback(tmp_path):
    site = write_site(tmp_path, "<p>value stays 42</p>", {"value": 42})
    claim = dict(CLAIM, snippet_alt="value stays")
    manifest = write_manifest(tmp_path, [claim])
    failures, warnings = check(manifest, site)
    assert failures == [] and warnings == []


def test_missing_page_is_failure(tmp_path):
    site = write_site(tmp_path, "x", {"value": 42})
    manifest = write_manifest(tmp_path, [dict(CLAIM, page="gone.html")])
    failures, _ = check(manifest, site)
    assert len(failures) == 1 and "page missing" in failures[0]


def test_broken_expr_is_failure(tmp_path):
    site = write_site(tmp_path, "<p>the value is 42</p>", {"value": 42})
    manifest = write_manifest(tmp_path, [dict(CLAIM, expr="d['absent']")])
    failures, _ = check(manifest, site)
    assert len(failures) == 1 and "source check failed" in failures[0]


def test_evaluate_restricted_builtins(tmp_path):
    assert evaluate("round(sum(d['xs']) / len(d['xs']), 1)", {"xs": [1, 2, 4]}) == 2.3


def test_live_manifest_verifies_against_live_site(site_root):
    """The committed manifest must stay green against the sibling site checkout."""
    failures, warnings = check(ROOT / "data" / "claims_manifest.json", site_root)
    assert failures == [] and warnings == []


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


def test_live_manifest_check_reads_the_site_it_is_given(tmp_path):
    """An empty site has none of the manifest's pages, so the live test fails there:
    it checks the site root it resolves, not a fixed path."""
    with pytest.raises(AssertionError):
        test_live_manifest_verifies_against_live_site(tmp_path)


def test_evaluate_comprehension_body_sees_data():
    # regression: d must live in eval's globals - comprehension bodies run in
    # their own frame and never see eval's locals
    assert evaluate("[d['xs'][k] for k in ('a', 'b')]", {"xs": {"a": 1, "b": 2}}) == [1, 2]
