"""Load every published page in a browser and fail on the breakages CI cannot see ($0).

This is the **second** of two gates, and the narrower one. Which catches what was
established by breaking the site on purpose (2026-09-04) rather than assumed:

* **A renamed or missing payload field is caught by
  ``scripts/validate_frontend_contract.py``, not by this script.** Renaming
  ``stress_pairs.json``'s ``pairs`` key made the validator fail
  (``expected a non-empty list``, exit 1) while this script passed. The page had
  degraded gracefully — section hidden, table empty — which from a browser is
  indistinguishable from an optional section that legitimately has no data. Run
  the validator first; it is the primary defence.
* **This script catches what the validator cannot see**: JavaScript that throws,
  a payload that 404s or errors at the network level, an HTTP error on the page
  itself, and a table that is **empty while visible** — the case where the page
  did *not* degrade gracefully and a reader sees a blank panel.

Together they cover the documented failure mode; neither does alone.

It drives the real pages in Chromium and fails on:

* an uncaught page error or a console ``error`` (the JS broke outright);
* a failed request for anything under ``data/`` (a payload went missing or was
  renamed — the exporter's half of the contract);
* a **visible** JS-populated ``<tbody>`` that renders **zero rows** (the silent
  one: the fetch succeeded, the field did not, and the table came out empty).

Two things deliberately do NOT fail, both learned by running this against the
live site before shipping it, where each produced a false positive:

* **An empty table that is hidden.** ``dialect-differences`` guards its
  ``#dlc-body`` section on ``feat.core.top`` and leaves the container ``hidden``
  when the payload has no ``core`` key — which it currently does not. That is the
  graceful degradation the site's rules require.

  Note the order carefully: **rows are counted first, and visibility only
  interprets a zero.** Gating on visibility *before* counting skipped five
  populated tables sitting inside collapsed ``<details>`` (10, 3, 5, 5 and 10
  rows), turning the check into one that quietly stopped checking — a worse
  failure than the false positive it was fixing. A populated table passes
  whether or not it is on screen; only an empty *and visible* one fails.
* **The automatic favicon request.** ``share/card.html`` is an internal source
  for a PNG and carries no ``rel="icon"``, so the browser requests
  ``/favicon.ico`` unbidden and logs a 404. Browser-initiated, not the page's.

Pending and em-dash cells are legitimate and stay passing — a scenario lacking
data is a supported state. Zero rows in a *visible* table is not.

A check that cries wolf gets switched off, so both exclusions are narrow and
named rather than a blanket softening.

Lives in the engine repo because the frontend repo deliberately contains no
Python, and because the contract validator it runs beside is already here. The
frontend's workflow checks this repo out to use both.

Usage:
  python scripts/check_pages.py --site ../patientwords [--port 8901] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

# tbody ids that page JS fills at runtime. A zero-row render here is the silent
# breakage this script exists for; the id list is the frontend's, so a page that
# adds a table adds its id here.
JS_TABLE_BODIES = (
    "dlc-body", "dlf-body", "dlm-body", "ev-body", "ja-body", "me-body",
    "mx-body", "router-body", "sim-sum-body", "sp-body", "tier-body",
    "tx-scale-body",
)

# Requests the browser makes on its own, which say nothing about the page.
IGNORED_REQUESTS = ("/favicon.ico",)

# Pages whose VISIBLE tables are legitimately empty until data lands go here with
# a reason, never silently skipped. Hidden tables need no entry — invisible ones
# are not checked at all.
ALLOW_EMPTY: dict[str, str] = {}


def _ignorable(text: str) -> bool:
    return any(pat in text for pat in IGNORED_REQUESTS)


def discover_pages(site: Path) -> list[str]:
    """Every page a visitor can reach, as site-root-relative URLs.

    `modes/` is excluded: those are engine-generated self-contained renders, not
    pages this repo composes, and there are hundreds of them.
    """
    out = []
    for p in sorted(site.rglob("*.html")):
        rel = p.relative_to(site)
        if rel.parts and rel.parts[0] in {"modes", ".git"}:
            continue
        out.append("/" + rel.as_posix())
    return out


def serve(site: Path, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=site, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urlopen(f"http://127.0.0.1:{port}/", timeout=0.5).read(1)
            return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit(f"could not serve {site} on port {port}")


def check_page(page, base: str, url: str) -> dict:
    """Load one page and collect every failure it shows. Never raises on a
    page problem — a crashed page is a finding, not an abort."""
    errors: list[str] = []
    console: list[str] = []
    failed: list[str] = []

    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console",
            lambda m: console.append(m.text)
            if m.type == "error" and not _ignorable(m.location.get("url", "")) else None)
    page.on("requestfailed",
            lambda r: failed.append(r.url)
            if "/data/" in r.url and not _ignorable(r.url) else None)
    page.on("response",
            lambda r: failed.append(f"{r.url} -> HTTP {r.status}")
            if r.status >= 400 and not _ignorable(r.url) else None)

    findings: list[str] = []
    try:
        resp = page.goto(base + url, wait_until="networkidle", timeout=45_000)
        if resp is not None and resp.status >= 400:
            findings.append(f"HTTP {resp.status}")
    except Exception as exc:  # navigation timeout or crash
        findings.append(f"navigation failed: {type(exc).__name__}: {exc}")
        return {"url": url, "findings": findings, "tables": {}}

    findings += [f"page error: {e}" for e in errors]
    findings += [f"console error: {c}" for c in console]
    findings += [f"data request failed: {u}" for u in failed]

    tables = {}
    for tid in JS_TABLE_BODIES:
        loc = page.locator(f"#{tid} tr")
        try:
            body = page.locator(f"#{tid}")
            if body.count() == 0:
                continue  # this page does not carry that table
            rows = loc.count()
            # Visibility is consulted ONLY to interpret a zero. Gating on it
            # first skipped five populated tables sitting inside collapsed
            # <details> (2026-09-04) -- a check that quietly stops checking.
            visible = body.is_visible()
        except Exception as exc:
            findings.append(f"#{tid}: could not count rows ({exc})")
            continue
        tables[tid] = rows if rows else ("0/hidden" if not visible else 0)
        if rows == 0 and visible and url not in ALLOW_EMPTY:
            findings.append(
                f"#{tid} rendered 0 rows while visible — the payload loaded but "
                f"the table is empty, which is the silent-blank failure")
    return {"url": url, "findings": findings, "tables": tables}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default="../patientwords")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--json", default=None, help="write the full report here")
    ap.add_argument("--browser", default=None,
                    help="chromium executable path (default: Playwright's own)")
    args = ap.parse_args()

    site = Path(args.site).resolve()
    if not site.is_dir():
        raise SystemExit(f"no such site directory: {site}")
    pages = discover_pages(site)
    if not pages:
        raise SystemExit(f"no pages found under {site}")

    from playwright.sync_api import sync_playwright

    base = f"http://127.0.0.1:{args.port}"
    server = serve(site, args.port)
    results = []
    try:
        with sync_playwright() as pw:
            launch = {"executable_path": args.browser} if args.browser else {}
            browser = pw.chromium.launch(**launch)
            for url in pages:
                page = browser.new_page()
                results.append(check_page(page, base, url))
                page.close()
            browser.close()
    finally:
        server.terminate()

    failing = [r for r in results if r["findings"]]
    for r in results:
        mark = "FAIL" if r["findings"] else "ok  "
        rows = " ".join(f"{k}={v}" for k, v in sorted(r["tables"].items()))
        print(f"{mark} {r['url']}" + (f"   [{rows}]" if rows else ""))
        for f in r["findings"]:
            print(f"       - {f}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"pages": len(results), "failing": len(failing), "results": results},
            indent=1) + "\n", encoding="utf-8")

    print(f"\n{len(results)} pages checked, {len(failing)} failing")
    raise SystemExit(1 if failing else 0)


if __name__ == "__main__":
    main()
