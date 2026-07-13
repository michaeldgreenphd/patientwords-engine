"""Claim-drift check: prose snippets vs values recomputed from data sources."""
import json
from pathlib import Path

from scripts.claim_check import check, evaluate


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


def test_live_manifest_verifies_against_live_site():
    """The committed manifest must stay green against the sibling site checkout."""
    root = Path(__file__).resolve().parents[1]
    site = root / ".." / "patientwords"
    if not site.exists():  # sibling checkout absent in some environments
        return
    failures, warnings = check(root / "data" / "claims_manifest.json", site)
    assert failures == [] and warnings == []


def test_evaluate_comprehension_body_sees_data():
    # regression: d must live in eval's globals - comprehension bodies run in
    # their own frame and never see eval's locals
    assert evaluate("[d['xs'][k] for k in ('a', 'b')]", {"xs": {"a": 1, "b": 2}}) == [1, 2]
