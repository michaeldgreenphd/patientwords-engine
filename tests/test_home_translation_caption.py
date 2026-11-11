"""The home page's rewritten-sentence caption reads its two probabilities from the provenance file.

Regression for a review finding of 2026-11-11: the caption printed two typed numbers and the page never
replaced them, and the claims manifest compared only the first with its record. A regenerated provenance
file could therefore leave the second number stale without any check failing.

The browser test loads the site's real ``index.html`` from a temporary directory with placeholder data, so
no study value is involved. Skipped where the sibling site checkout, Playwright or a Chromium is missing.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT.parent / "patientwords"
HOME = SITE / "index.html"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
SNIPPET = "0.45 after translation (clinical baseline 0.26) · July 7 trace"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_static_caption_is_the_checked_copy_and_the_manifest_guards_both_numbers() -> None:
    if not HOME.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    assert f'<span id="tr-claim">{SNIPPET}</span>' in HOME.read_text(encoding="utf-8")
    claims = json.loads((ROOT / "data" / "claims_manifest.json").read_text(encoding="utf-8"))["claims"]
    claim = next(c for c in claims if c["page"] == "index.html" and c["snippet"] == SNIPPET)
    assert claim["source"] == "data/provenance.json" and claim["expected"] == [0.45, 0.26]
    assert "['translated'][1]" in claim["expr"] and "['clinical'][1]" in claim["expr"]


def _caption(page, base: str, provenance: dict) -> str:
    page.route("**/data/provenance.json", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(provenance)))
    page.goto(base + "/index.html", wait_until="networkidle")
    page.wait_for_selector("#ex-top:not([hidden])")          # the page's script has run to its end
    return page.inner_text("#tr-claim")


def test_the_caption_follows_the_provenance_record_and_keeps_its_checked_copy_without_one(tmp_path: Path) -> None:
    if not HOME.is_file():
        pytest.skip("the sibling site checkout is not on disk")
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    shutil.copy2(HOME, site / "index.html")
    (site / "data" / "simulated_scenarios.json").write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    serve = _load("check_pages").serve
    port = _free_port()
    with sync_playwright() as pw:
        candidates = (CHROME, pw.chromium.executable_path, shutil.which("chromium"))
        chrome = next((c for c in candidates if c and Path(c).exists()), None)
        if chrome is None:
            pytest.skip("no Chromium available for a browser-driven test")
        server = serve(site, port)
        try:
            browser = pw.chromium.launch(executable_path=chrome)
            base = f"http://127.0.0.1:{port}"
            # Placeholder record: 0.5 and 0.25 are not the study's values, so a page that printed its typed
            # numbers would fail here. toFixed(2) of each gives 0.50 and 0.25.
            record = {"translation_cases": {"grandma_laxative": {"translated": ["placeholder", 0.5],
                                                                 "clinical": ["placeholder", 0.25]}}}
            page = browser.new_page()
            assert _caption(page, base, record) == "0.50 after translation (clinical baseline 0.25) · July 7 trace"
            page.close()
            # No record, a record without numbers, and a record with one number: the checked copy stays.
            for missing in ({}, {"translation_cases": {"grandma_laxative": {"translated": ["x", None],
                                                                            "clinical": ["x", 0.25]}}},
                            {"translation_cases": {"grandma_laxative": {"translated": ["x", 0.5]}}}):
                page = browser.new_page()
                assert _caption(page, base, missing) == SNIPPET
                page.close()
            browser.close()
        finally:
            server.terminate()
