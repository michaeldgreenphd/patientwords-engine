"""Browser-driven regression tests for check_pages.check_page.

The offline tests in test_check_pages.py test a local copy of the verdict rule
and never call the script -- which is how a dead branch shipped: the
"empty while visible" verdict asked the tbody for visibility, and an empty
tbody has a zero-height box, so it could never fire. These drive the real
function against three minimal pages. Skipped where no Chromium is available.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

pytest.importorskip("playwright")
pytestmark = pytest.mark.skipif(
    not (Path(CHROME).exists() or shutil.which("chromium")),
    reason="no Chromium available for a browser-driven test")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load("check_pages")

PAGES = {
    "empty_visible.html": '<h1>x</h1><table><thead><tr><th>c</th></tr></thead>'
                          '<tbody id="sim-sum-body"></tbody></table>',
    "empty_hidden.html": '<div hidden><table><tbody id="sim-sum-body"></tbody></table></div>',
    "populated_collapsed.html": '<details><summary>s</summary><table>'
                                '<tbody id="sim-sum-body"><tr><td>1</td></tr><tr><td>2</td></tr></tbody>'
                                '</table></details>',
}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("site")
    for name, body in PAGES.items():
        (d / name).write_text(f"<html><head><link rel='icon' href='data:,'></head><body>{body}</body></html>")
    return d


@pytest.fixture(scope="module")
def results(site):
    from playwright.sync_api import sync_playwright
    port = 8933
    server = cp.serve(site, port)
    out = {}
    try:
        with sync_playwright() as pw:
            launch = {"executable_path": CHROME} if Path(CHROME).exists() else {}
            browser = pw.chromium.launch(**launch)
            for name in PAGES:
                page = browser.new_page()
                out[name] = cp.check_page(page, f"http://127.0.0.1:{port}", "/" + name)
                page.close()
            browser.close()
    finally:
        server.terminate()
    return out


def test_empty_table_on_screen_is_a_finding(results):
    """The silent-blank failure. This is the case that was dead code."""
    r = results["empty_visible.html"]
    assert r["tables"]["sim-sum-body"] == 0
    assert any("0 rows while visible" in f for f in r["findings"]), r


def test_empty_table_in_hidden_container_is_graceful_degradation(results):
    r = results["empty_hidden.html"]
    assert r["tables"]["sim-sum-body"] == "0/hidden"
    assert r["findings"] == []


def test_populated_table_inside_collapsed_details_is_counted_not_skipped(results):
    """The earlier over-correction skipped these; rows must be counted."""
    r = results["populated_collapsed.html"]
    assert r["tables"]["sim-sum-body"] == 2
    assert r["findings"] == []
