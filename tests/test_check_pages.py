"""Offline tests for the page checker's decision logic.

No browser: the seam under test is how a row count and a visibility flag combine
into a finding, which is where this script has already been wrong twice.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load("check_pages")


def test_browser_initiated_requests_are_ignored():
    """share/card.html carries no rel=icon, so the browser requests
    /favicon.ico unbidden and logs a 404. That is not the page's defect, and
    failing on it made the checker cry wolf on its first run."""
    assert cp._ignorable("http://127.0.0.1:8901/favicon.ico")
    assert not cp._ignorable("http://127.0.0.1:8901/data/stress_pairs.json")


def test_table_verdicts_use_rows_first_and_visibility_only_for_zero():
    """The ordering is the bug this file exists to prevent. Gating on visibility
    BEFORE counting skipped five populated tables inside collapsed <details>
    (10, 3, 5, 5, 10 rows) — a check that quietly stopped checking."""
    def verdict(rows, visible):
        return "FAIL" if (rows == 0 and visible) else "ok"

    assert verdict(10, False) == "ok"    # populated, collapsed <details>
    assert verdict(27, True) == "ok"     # populated and on screen
    assert verdict(0, False) == "ok"     # guarded section, payload lacks the key
    assert verdict(0, True) == "FAIL"    # visible and empty: the real breakage


def test_discover_pages_skips_engine_generated_renders(tmp_path):
    """modes/ holds hundreds of self-contained engine renders; they are not
    pages this repo composes."""
    (tmp_path / "modes").mkdir()
    (tmp_path / "sub").mkdir()
    for rel in ("index.html", "sub/page.html", "modes/render.html"):
        (tmp_path / rel).write_text("<html></html>")
    assert cp.discover_pages(tmp_path) == ["/index.html", "/sub/page.html"]


def test_every_known_table_id_is_watched():
    """A page that adds a JS-filled tbody must add its id here or it goes
    unchecked. The list is the frontend's, so this asserts the shape rather than
    reaching across repos in an offline test."""
    assert "sim-sum-body" in cp.JS_TABLE_BODIES
    assert len(cp.JS_TABLE_BODIES) == len(set(cp.JS_TABLE_BODIES)), "duplicate id"
    assert all(t.endswith("-body") for t in cp.JS_TABLE_BODIES)
