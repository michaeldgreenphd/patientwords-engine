"""Run one synthetic exporter -> HTTP -> browser slice. No inference or publication.

Requires only scripts/boundary_client/requirements.lock in a separate environment
and an installed Chromium. Everything exported is confined to TemporaryDirectory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.server
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from jsonschema.exceptions import ValidationError
from playwright.sync_api import sync_playwright

from boundary_client import client
from boundary_client.assertions import assert_browser, assert_semantics
from check_pages import check_page
from validate_frontend_contract import Report, check_simulated

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/frontend_boundary.json"
UNIT_TESTS = [
    "tests/test_validate_frontend_contract.py", "tests/test_simulated_schema.py",
    "tests/test_check_pages.py", "tests/test_export_frontend_defaults.py", "tests/test_urgency_unjoinable.py",
]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identity(root: Path, excluded: Path | None = None) -> dict[str, Any]:
    """Bind actual HEAD plus tracked diff and untracked bytes, excluding the receipt.

    Paths are repo-relative; private checkout paths never enter the receipt.
    """
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *args])
    exclusions = ["."]
    if excluded and excluded.is_relative_to(root):
        exclusions.append(f":(exclude){excluded.relative_to(root)}")
    diff = git("diff", "--binary", "HEAD", "--", *exclusions)
    untracked = {}
    for name in git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0"):
        path = root / name
        if name and path != excluded and path.is_file():
            untracked[name] = sha(path.read_bytes())
    return {"head": git("rev-parse", "HEAD").decode().strip(),
            "tracked_diff_sha256": sha(diff), "untracked_sha256": untracked,
            "dirty": bool(diff or untracked)}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def rejected(action: Callable[[], Any], kinds: tuple[type[Exception], ...]) -> dict[str, str]:
    """A negative control passes only when the intended layer actually rejects."""
    try:
        action()
    except kinds as exc:
        return {"exception": type(exc).__name__, "message": str(exc).split("\n", 1)[0][:240]}
    raise AssertionError("deliberate defect was not detected")


class Handler(http.server.SimpleHTTPRequestHandler):
    """Real static HTTP, with one deliberately bad HTTP fixture response."""
    html_fallback = False

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        if self.html_fallback and self.path.endswith("/data/simulated_scenarios.json"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>synthetic fallback</title>")
        else:
            super().do_GET()


def run(site_source: Path, browser_path: str | None, receipt: dict[str, Any]) -> None:
    fixture = json.loads(FIXTURE.read_text())
    expected = fixture["expected"]
    checks = receipt["checks"]
    with tempfile.TemporaryDirectory(prefix="pw-boundary-") as directory:
        temp = Path(directory)
        # The same sibling layout and scripts subtree as site CI's sparse engine.
        engine = temp / "patientwords-engine"
        site = temp / "patientwords"
        shutil.copytree(ROOT / "scripts", engine / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(site_source, site, ignore=shutil.ignore_patterns(".git", ".DS_Store"))
        for folder in ("data", "ops", "docs"):
            (engine / folder).mkdir(exist_ok=True)
        # Selected offline cases only: no repository-wide collection or model imports.
        for relative in [*UNIT_TESTS, "tests/conftest.py", "data/petri/publication_deviations.json"]:
            target = engine / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        test_command = [sys.executable, "-m", "pytest", *UNIT_TESTS, "-q"]
        tested = subprocess.run(test_command, cwd=engine, capture_output=True, text=True)
        if tested.returncode:
            print(tested.stdout, file=sys.stderr)
            print(tested.stderr, file=sys.stderr)
            raise AssertionError("affected offline checks failed in sparse layout")
        checks.append({"name": "affected_offline_checks_in_sparse_layout", "result": "passed",
                       "command": "python -m pytest " + " ".join(UNIT_TESTS) + " -q",
                       "summary": tested.stdout.strip().splitlines()[-1]})
        inputs = temp / "synthetic-input"
        for relative, value in fixture["engine_files"].items():
            write_json(inputs / relative, value)
        for relative, value in fixture["site_files"].items():
            write_json(site / relative, value)

        # The only HTML change is an explicit, local-only disclosure; page JS is untouched.
        index = site / "simulated-scenarios/index.html"
        html = index.read_text()
        index.write_text(html.replace("<body>", '<body><p role="note">' + fixture["disclosure"] + "</p>", 1))
        assert fixture["disclosure"] in index.read_text(), "fixture disclosure was not inserted"
        command = [sys.executable, "scripts/export_frontend_simulated.py", "--engine", str(inputs),
                   "--frontend", str(site), "--stamps", fixture["stamp"], "--models", ",".join(fixture["models"])]
        subprocess.run(command, cwd=engine, check=True, capture_output=True, text=True)
        checks.append({"name": "real_exporter_cli_in_sparse_layout", "result": "passed"})
        artifact = site / "data/simulated_scenarios.json"
        original = artifact.read_bytes()
        receipt["export_sha256"] = sha(original)
        payload = json.loads(original)
        rep = Report()
        check_simulated(rep, site, payload)
        assert not rep.errors, rep.errors
        checks.append({"name": "existing_check_simulated", "result": "passed", "warnings": rep.warnings})
        # Exercise the actual CLI checker dependency layout without unrelated
        # published files or owner-only vendor pack reconstruction.
        sparse_code = (
            "import json,sys; from pathlib import Path; sys.path.insert(0,'scripts'); "
            "from validate_frontend_contract import Report,check_simulated; "
            "r=Report(); check_simulated(r,Path('../patientwords'),"
            "json.loads(Path('../patientwords/data/simulated_scenarios.json').read_text())); "
            "assert not r.errors,r.errors"
        )
        subprocess.run([sys.executable, "-c", sparse_code], cwd=engine, check=True)
        subprocess.run([sys.executable, str(ROOT / "scripts/boundary_client/generate.py"), "--check"], check=True)
        checks.append({"name": "generator_regeneration", "result": "byte-identical"})

        # Serve project-path URLs, matching GitHub Pages /patientwords/, not only /.
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(temp)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        base = origin + "/patientwords"
        try:
            fetched = client.fetch(base)
            assert_semantics(fetched, expected)
            checks.append({"name": "http_schema_generated_model_semantics", "result": "passed"})
            with sync_playwright() as pw:
                browser = pw.chromium.launch(**({"executable_path": browser_path} if browser_path else {}),
                                             args=["--disable-background-networking"])
                receipt["versions"]["chromium"] = browser.version
                context = browser.new_context(service_workers="block")
                blocked: list[str] = []
                errors: list[str] = []

                def route_request(route: Any) -> None:
                    url = urlsplit(route.request.url)
                    if f"{url.scheme}://{url.netloc}" == origin:
                        route.continue_()
                    else:
                        blocked.append(f"{url.scheme}://{url.netloc}")
                        route.abort()

                context.route("**/*", route_request)

                def page_at_fixture() -> Any:
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    report = check_page(page, base, expected["index_page"])
                    assert not report["findings"], report
                    assert page.get_by_role("note").inner_text() == fixture["disclosure"]
                    return page

                page = page_at_fixture()
                assert_browser(page, expected)
                page.close()
                checks.append({"name": "browser_values_models_filters_zero_missing", "result": "passed"})

                # Required defect 1: shape break, served as real HTTP JSON.
                broken = copy.deepcopy(payload)
                del broken["scenarios"][0]["models"]["qwen3-4b"]["prob_patient"]
                write_json(artifact, broken)
                detected = rejected(lambda: client.fetch(base), (ValidationError,))
                artifact.write_bytes(original)
                assert_semantics(client.fetch(base), expected)
                checks.append({"name": "missing_required_field", "result": "detected_then_restored_pass",
                               "detector": detected})

                # Required defect 2: valid shapes and counts, wrong record/model association.
                broken = copy.deepcopy(payload)
                first, second = broken["scenarios"][:2]
                first["models"]["qwen3-4b"], second["models"]["qwen3-4b"] = (
                    second["models"]["qwen3-4b"], first["models"]["qwen3-4b"])
                write_json(artifact, broken)
                valid_shape = client.fetch(base)
                detected = rejected(lambda: assert_semantics(valid_shape, expected), (AssertionError,))
                page = page_at_fixture()
                browser_detected = rejected(lambda: assert_browser(page, expected), (AssertionError,))
                page.close()
                artifact.write_bytes(original)
                assert_semantics(client.fetch(base), expected)
                page = page_at_fixture()
                assert_browser(page, expected)
                page.close()
                checks.append({"name": "shape_valid_wrong_model_association", "schema": "passed",
                               "semantic_detector": detected, "browser_detector": browser_detected,
                               "result": "detected_then_restored_pass"})

                legacy = copy.deepcopy(payload)
                legacy.pop("models_meta")
                legacy.pop("archive", None)
                for scenario in legacy["scenarios"]:
                    scenario.pop("models")
                write_json(artifact, legacy)
                assert_semantics(client.fetch(base), expected, legacy=True)
                page = page_at_fixture()
                assert_browser(page, expected, legacy=True)
                page.close()
                artifact.write_bytes(original)
                checks.append({"name": "legacy_base_mirror_without_models_meta_models_archive", "result": "passed"})

                # An accepted fourth input has no result: exercise real exporter pending counts.
                pending = fixture["pending_case"]
                pairs_path = f"data/simulated/pairs_{fixture['stamp']}.json"
                report_path = f"data/simulated/pairs_{fixture['stamp']}.report.json"
                pairs = copy.deepcopy(fixture["engine_files"][pairs_path])
                pairs.append(pending["pair"])
                write_json(inputs / pairs_path, pairs)
                generation_report = copy.deepcopy(fixture["engine_files"][report_path])
                generation_report["accepted"] = pending["accepted"]
                write_json(inputs / report_path, generation_report)
                subprocess.run(command, cwd=engine, check=True, capture_output=True)
                pending_payload = client.fetch(base)
                assert pending_payload["summary"]["totals"]["accepted_public"] == 4
                assert pending_payload["summary"]["totals"]["measured"] == 2
                assert len(pending_payload["scenarios"]) == 3
                page = page_at_fixture()
                assert page.get_by_text(pending["display"], exact=True).is_visible()
                assert_browser(page, expected)
                page.close()
                artifact.write_bytes(original)
                checks.append({"name": "accepted_but_not_run_pending_denominator", "result": "passed"})

                # Real HTTP failures: no redirect/proxy/HTML-as-JSON acceptance.
                for name, raw, kinds in (
                    ("malformed_json", b"{", (json.JSONDecodeError,)),
                    ("html_bytes_as_json", b"<!doctype html>", (json.JSONDecodeError,)),
                ):
                    artifact.write_bytes(raw)
                    detector = rejected(lambda: client.fetch(base), kinds)
                    artifact.write_bytes(original)
                    client.fetch(base)
                    checks.append({"name": name, "result": "detected_then_restored_pass", "detector": detector})
                artifact.unlink()
                detector = rejected(lambda: client.fetch(base), (ValueError,))
                artifact.write_bytes(original)
                client.fetch(base)
                checks.append({"name": "http_404", "result": "detected_then_restored_pass", "detector": detector})
                Handler.html_fallback = True
                detector = rejected(lambda: client.fetch(base), (ValueError,))
                Handler.html_fallback = False
                client.fetch(base)
                checks.append({"name": "http_200_html_content_type", "result": "detected_then_restored_pass",
                               "detector": detector})
                assert not blocked, blocked
                assert not errors, errors
                receipt["browser_external_requests"] = blocked
                receipt["browser_errors"] = errors
                context.close()
                browser.close()
        finally:
            Handler.html_fallback = False
            server.shutdown()
            server.server_close()
            worker.join(timeout=10)
    receipt["cleanup"] = "temporary server stopped; synthetic exports and copied site removed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--browser", help="optional installed Chromium executable")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt_path = args.receipt.resolve()
    versions = {name: importlib.metadata.version(name) for name in
                ("playwright", "jsonschema", "datamodel-code-generator", "pydantic", "pytest")}
    receipt: dict[str, Any] = {
        "schema": "patientwords.frontend-boundary-receipt/1", "evidence": "local synthetic software test only",
        "utc": datetime.now(timezone.utc).isoformat(), "engine": identity(ROOT, receipt_path),
        "frontend": identity(args.site.resolve()), "versions": {"python": sys.version.split()[0], **versions},
        "fixture_sha256": sha(FIXTURE.read_bytes()),
        "contracts_sha256": {p.name: sha(p.read_bytes()) for p in sorted((ROOT / "scripts/contracts").glob("*.json"))},
        "toolchain_sha256": sha((ROOT / "scripts/boundary_client/requirements.lock").read_bytes()),
        "command": "python scripts/check_frontend_boundary.py --site SITE --browser CHROMIUM --receipt RECEIPT",
        "export_command": "python scripts/export_frontend_simulated.py --engine SYNTHETIC_INPUT --frontend TEMP_SITE "
                          "--stamps 20000101T000000Z --models gemma-2-2b,qwen3-4b",
        "checks": [], "hosted_checks": "unrun", "native_sample_state": "unsupported by selected index",
    }
    try:
        run(args.site.resolve(), args.browser, receipt)
        receipt["result"] = "passed"
    except Exception as exc:
        receipt["result"] = "failed"
        receipt["failure"] = type(exc).__name__
        raise
    finally:
        write_json(receipt_path, receipt)
    print(f"boundary suite: {len(receipt['checks'])} checks passed; receipt: {args.receipt}")


if __name__ == "__main__":
    main()
