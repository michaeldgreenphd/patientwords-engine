"""Run one synthetic exporter -> HTTP -> browser slice. No inference or publication.

Requires only scripts/boundary_client/requirements.lock in a separate environment
and an installed Chromium. Everything exported is confined to TemporaryDirectory.

The temporary engine layout is derived, not listed: it holds what site CI's sparse
checkout of the engine holds (scripts/boundary_client/layout.py reads the directories
from the site's workflow file), plus the test-support files in TEST_SUPPORT. Every
subprocess run in that layout is watched by scripts/boundary_client/layout_probe.py; a
file a stage asks for that the engine checkout holds and the layout lacks stops the run
with a LayoutError that names the file and the stage.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.server
import importlib.metadata
import json
import os
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

from boundary_client import client, layout, layout_probe
from boundary_client.assertions import (assert_browser, assert_semantics, assert_summary_penalty,
                                        assert_summary_sentence, SUMMARY_PENALTY_FIELDS)
from check_pages import check_page
from validate_frontend_contract import Report, check_simulated

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/frontend_boundary.json"
UNIT_TESTS = [
    "tests/test_validate_frontend_contract.py", "tests/test_simulated_schema.py",
    "tests/test_check_pages.py", "tests/test_export_frontend_defaults.py", "tests/test_urgency_unjoinable.py",
    "tests/test_contract_summary_semantics.py", "tests/test_payload_summary.py", "tests/test_frontend_boundary.py",
]
# The only hand-kept part of the layout: site CI runs no pytest, so its sparse checkout holds no tests/.
# The run checks this list. A file one of these modules asks for that is missing here stops the run by name.
TEST_SUPPORT = [*UNIT_TESTS, "tests/conftest.py", "tests/fixtures/frontend_boundary.json"]
# Runs the validator's own check of the scenarios payload (check_simulated, which includes the
# summary.penalty recomputation) in the layout and exits as the validator's CLI does: 1 with a FAIL line per
# error, else 0. The CLI itself (validate_frontend_contract.py --site --engine) checks every artifact of a
# site against the engine's records; on a synthetic site those cross-artifact checks fail for reasons that
# have nothing to do with this payload, so its exit code could not show what rejected the payload.
VALIDATOR_DRIVER = """
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
from validate_frontend_contract import Report, check_simulated
site = Path(sys.argv[1])
rep = Report()
check_simulated(rep, site, json.loads((site / "data/simulated_scenarios.json").read_text(encoding="utf-8")))
for note in rep.notes:
    print("note:", note)
for error in rep.errors:
    print("FAIL:", error)
sys.exit(1 if rep.errors else 0)
"""
# Asks for two paths so the probe's two routes are both exercised: an existence test (os.stat) and an open.
PROBE_CONTROL = """
import os, sys
os.path.exists(sys.argv[1])
try:
    open(sys.argv[2]).close()
except OSError:
    pass
"""


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
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = fixture["expected"]
    checks = receipt["checks"]
    # Derived before anything is copied: the directories site CI checks out, and the files a commit would hold.
    sparse, root_files = layout.sparse_checkout(site_source / layout.WORKFLOW)
    committable = layout.committable_files(ROOT)
    files = layout.select(committable, sparse, root_files)
    with tempfile.TemporaryDirectory(prefix="pw-boundary-") as directory:
        temp = Path(directory).resolve()
        # The same sibling layout as site CI's two checkouts.
        engine = temp / "patientwords-engine"
        site = temp / "patientwords"
        needed = (sum((ROOT / name).stat().st_size for name in files)
                  + layout.tree_bytes(site_source, skip=(".git",)))
        layout.require_free_space(temp, needed, "the engine layout and the site copy")
        built = layout.build(ROOT, engine, files, TEST_SUPPORT)
        shutil.copytree(site_source, site, ignore=shutil.ignore_patterns(".git", ".DS_Store"))
        receipt["layout"] = {"derived_from": f"site {layout.WORKFLOW}, sparse-checkout block",
                             "sparse_checkout": sparse, "root_files": root_files, **built,
                             "test_support": TEST_SUPPORT, "temporary_bytes_needed": needed}
        checks.append({"name": "layout_mirrors_site_ci_sparse_checkout", "result": "passed",
                       "sparse_checkout": sparse, "root_files": root_files, **built})
        probe = temp / "layout-probe"
        probe.mkdir()
        shutil.copyfile(ROOT / "scripts/boundary_client/layout_probe.py", probe / "sitecustomize.py")
        stages: list[dict[str, Any]] = []

        def in_layout(stage: str, command: list[str]) -> subprocess.CompletedProcess[str]:
            """Run one command in the layout under the probe. A file the layout lacks is reported by name
            before the command's own exit code is read."""
            log = probe / f"{stage}.log"
            environment = {**os.environ, layout_probe.ROOT_ENV: str(engine), layout_probe.LOG_ENV: str(log),
                           "PYTHONPATH": os.pathsep.join(
                               item for item in (str(probe), os.environ.get("PYTHONPATH")) if item)}
            done = subprocess.run(command, cwd=engine, env=environment, capture_output=True, text=True)
            absent = layout.absent_inputs(ROOT, log)
            asked = len(set(log.read_text(encoding="utf-8", errors="replace").splitlines())) if log.exists() else 0
            stages.append({"stage": stage, "asked_and_absent": asked, "absent_inputs": absent})
            if absent:
                raise layout.LayoutError(
                    f"the temporary engine layout lacks {len(absent)} path(s) that stage '{stage}' asked for and "
                    f"the engine checkout holds: {', '.join(absent)}. Site CI's sparse checkout "
                    f"({', '.join(sparse)}{' and root files' if root_files else ''}) does not hold them either. "
                    "A test-only input belongs in TEST_SUPPORT (scripts/check_frontend_boundary.py); a file the "
                    "validator or the exporter reads must move into a directory site CI checks out.")
            return done

        def passed(done: subprocess.CompletedProcess[str], what: str) -> None:
            if done.returncode:
                print(done.stdout.replace(str(temp), "TEMP"), file=sys.stderr)
                print(done.stderr.replace(str(temp), "TEMP"), file=sys.stderr)
                raise AssertionError(f"{what} failed in the layout (exit {done.returncode})")

        # Required defect 0: the layout check itself. Ask, in the layout, for files the checkout holds and
        # the layout does not; the run must name them. Without this a silent probe would read as a complete layout.
        inside = set(files) | set(TEST_SUPPORT)
        outside = sorted(name for name in committable if name not in inside)
        if outside:
            # Prefer test modules that are not selected: the commonest way for the layout to fall short.
            candidates = [name for name in outside if name.startswith("tests/")] or outside
            wanted = [candidates[0], candidates[-1]]
            try:
                in_layout("layout_probe_control", [sys.executable, "-c", PROBE_CONTROL, *wanted])
            except layout.LayoutError as exc:
                missing = [name for name in wanted if name not in str(exc)]
                assert not missing, f"layout check did not name {missing}: {exc}"
            else:
                raise AssertionError(f"layout check did not detect requests for {wanted}")
            control = stages.pop()
            checks.append({"name": "layout_absent_input_named", "result": "detected",
                           "asked_for": wanted, "named": control["absent_inputs"]})
        else:
            checks.append({"name": "layout_absent_input_named", "result": "unrun",
                           "reason": "the engine checkout holds no file outside the layout"})

        # Selected offline cases only: no repository-wide collection or model imports.
        tested = in_layout("offline_tests", [sys.executable, "-m", "pytest", *UNIT_TESTS, "-q", "-rs"])
        passed(tested, "affected offline checks")
        test_lines = tested.stdout.replace(str(temp), "TEMP").strip().splitlines()
        checks.append({"name": "affected_offline_checks_in_sparse_layout", "result": "passed",
                       "command": "python -m pytest " + " ".join(UNIT_TESTS) + " -q -rs",
                       "summary": test_lines[-1],
                       "skipped": [line for line in test_lines if line.startswith("SKIPPED")]})
        inputs = temp / "synthetic-input"
        for relative, value in fixture["engine_files"].items():
            write_json(inputs / relative, value)
        for relative, value in fixture["site_files"].items():
            write_json(site / relative, value)

        # The only HTML change is an explicit, local-only disclosure; page JS is untouched.
        disclosures = {expected["index_page"]: fixture["disclosure"],
                       **{item["page"]: fixture["summary_page_disclosure"] for item in expected["summary_sentences"]}}
        for path, disclosure in disclosures.items():
            document = site / path.strip("/") / "index.html"
            html = document.read_text(encoding="utf-8")
            assert html.count("<body>") == 1, f"{path}: expected one <body> tag to carry the disclosure"
            document.write_text(html.replace("<body>", '<body><p role="note">' + disclosure + "</p>", 1),
                                encoding="utf-8")
            assert disclosure in document.read_text(encoding="utf-8"), "fixture disclosure was not inserted"
        command = [sys.executable, "scripts/export_frontend_simulated.py", "--engine", str(inputs),
                   "--frontend", str(site), "--stamps", ",".join(fixture["stamps"]),
                   "--models", ",".join(fixture["models"])]
        passed(in_layout("exporter", command), "the exporter CLI")
        checks.append({"name": "real_exporter_cli_in_sparse_layout", "result": "passed"})
        artifact = site / "data/simulated_scenarios.json"
        original = artifact.read_bytes()
        receipt["export_sha256"] = sha(original)
        payload = json.loads(original)
        # Stage 1 of 3 for the repeated-phrase regression: the exported file, before any transport.
        assert_summary_penalty(payload, expected)
        checks.append({"name": "exported_summary_penalty_matches_hand_calculation", "result": "passed",
                       "penalty": {field: payload["summary"]["penalty"][field] for field in SUMMARY_PENALTY_FIELDS},
                       "repeated_phrase_rows": expected["repeated_phrase"]["rows"]})
        rep = Report()
        check_simulated(rep, site, payload)
        assert not rep.errors, rep.errors
        checks.append({"name": "existing_check_simulated", "result": "passed", "warnings": rep.warnings})
        # The same check from the layout's own copy of the validator, without unrelated
        # published files or owner-only vendor pack reconstruction.
        validator = [sys.executable, "-c", VALIDATOR_DRIVER, "../patientwords"]
        passed(in_layout("contract_validator_exported", validator), "the contract validator's scenarios check")
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
                short_tmp = layout.browser_tmpdir(tempfile.gettempdir())
                browser = pw.chromium.launch(**({"executable_path": browser_path} if browser_path else {}),
                                             **({"env": {**os.environ, "TMPDIR": short_tmp}} if short_tmp else {}),
                                             args=["--disable-background-networking"])
                receipt["versions"]["chromium"] = browser.version
                receipt["browser_tmpdir"] = (f"{short_tmp} (the run's TMPDIR is too long for Chromium's socket)"
                                             if short_tmp else "the run's TMPDIR")
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

                def page_at(path: str) -> Any:
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    report = check_page(page, base, path)
                    assert not report["findings"], report
                    assert page.get_by_role("note").inner_text() == disclosures[path]
                    return page

                def page_at_fixture() -> Any:
                    return page_at(expected["index_page"])

                def summary_sentences(shown: list[dict[str, str]],
                                      not_shown: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
                    """Load each page that prints summary.penalty once. `shown` sentences must be rendered;
                    each `not_shown` sentence must be refused by the same assertion (a negative control)."""
                    detectors = []
                    for path in dict.fromkeys(item["page"] for item in shown):
                        page = page_at(path)
                        for item in shown:
                            if item["page"] == path:
                                assert_summary_sentence(page, item)
                        for item in not_shown or []:
                            if item["page"] == path:
                                detectors.append(rejected(
                                    lambda item=item: assert_summary_sentence(page, item, timeout=1000),
                                    (AssertionError,)))
                        page.close()
                    return detectors

                page = page_at_fixture()
                assert_browser(page, expected)
                page.close()
                checks.append({"name": "browser_values_models_filters_zero_missing", "result": "passed"})

                # Stage 3 of 3 for the repeated-phrase regression (stage 2 is assert_semantics above): the
                # sentences the home page and the wording-differences page print from summary.penalty.
                summary_sentences(expected["summary_sentences"])
                checks.append({"name": "browser_summary_sentences_phrase_count_and_mean", "result": "passed",
                               "sentences": expected["summary_sentences"]})

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

                # Required defect 3: valid shape, summary.penalty with a phrase count and a phrase-level mean
                # that the rows do not give and that are not the pre-correction form. The validator's
                # recomputation must reject it (FAIL lines for both fields, exit 1) and accept the restored file.
                defects = fixture["summary_defects"]
                broken = copy.deepcopy(payload)
                broken["summary"]["penalty"].update(defects["wrong_values"])
                write_json(artifact, broken)
                refused = in_layout("contract_validator_wrong_summary", validator)
                failures = [line for line in refused.stdout.replace(str(temp), "TEMP").splitlines()
                            if line.startswith("FAIL:")]
                assert refused.returncode == 1, f"validator exit {refused.returncode} on a wrong summary"
                for field in defects["wrong_values"]:
                    assert any(f"$.summary.penalty.{field} ::" in line for line in failures), (field, failures)
                assert all("$.summary.penalty." in line for line in failures), failures
                valid_shape = client.fetch(base)
                detected = rejected(lambda: assert_semantics(valid_shape, expected), (AssertionError,))
                artifact.write_bytes(original)
                passed(in_layout("contract_validator_restored", validator), "the validator on the restored payload")
                assert_semantics(client.fetch(base), expected)
                checks.append({"name": "summary_penalty_wrong_phrase_count_and_mean", "schema": "passed",
                               "altered": defects["wrong_values"],
                               "validator": {"exit_code": refused.returncode, "failures": failures},
                               "semantic_detector": detected, "result": "detected_then_restored_pass"})

                # Required defect 4: the summary as the producer wrote it before the 2026-11-10 correction
                # (every row its own phrase). The validator's dated transition notes this form until its
                # deadline and rejects it afterwards; both are recorded, neither is required here. The
                # fixture's hand-calculated values and the rendered sentences must reject it on every date.
                broken = copy.deepcopy(payload)
                broken["summary"]["penalty"].update(defects["pre_correction_form"])
                write_json(artifact, broken)
                judged = in_layout("contract_validator_pre_correction_summary", validator)
                lines = [line for line in judged.stdout.replace(str(temp), "TEMP").splitlines()
                         if "$.summary.penalty :: legacy" in line]
                assert len(lines) == 1 and lines[0].startswith(("note:", "FAIL:")), judged.stdout
                noted = lines[0].startswith("note:")
                assert judged.returncode == (0 if noted else 1), judged.returncode
                valid_shape = client.fetch(base)
                detected = rejected(lambda: assert_semantics(valid_shape, expected), (AssertionError,))
                browser_detected = summary_sentences(defects["pre_correction_sentences"],
                                                     not_shown=expected["summary_sentences"])
                assert len(browser_detected) == len(expected["summary_sentences"])
                artifact.write_bytes(original)
                assert_semantics(client.fetch(base), expected)
                summary_sentences(expected["summary_sentences"])
                checks.append({"name": "summary_penalty_pre_correction_form", "schema": "passed",
                               "altered": defects["pre_correction_form"],
                               "validator": {"exit_code": judged.returncode,
                                             "outcome": "noted_under_dated_transition" if noted
                                             else "rejected_after_transition"},
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

                # An accepted input without a result: exercise real exporter pending counts.
                pending = fixture["pending_case"]
                pairs_path = f"data/simulated/pairs_{pending['stamp']}.json"
                report_path = f"data/simulated/pairs_{pending['stamp']}.report.json"
                pairs = copy.deepcopy(fixture["engine_files"][pairs_path])
                pairs.append(pending["pair"])
                write_json(inputs / pairs_path, pairs)
                generation_report = copy.deepcopy(fixture["engine_files"][report_path])
                generation_report["accepted"] = pending["accepted"]
                write_json(inputs / report_path, generation_report)
                passed(in_layout("exporter_pending", command), "the exporter CLI with a pending pair")
                pending_payload = client.fetch(base)
                wanted = pending["expected"]
                assert pending_payload["summary"]["totals"]["accepted_public"] == wanted["accepted_public"]
                assert pending_payload["summary"]["totals"]["measured"] == wanted["measured"]
                assert len(pending_payload["scenarios"]) == wanted["scenarios"]
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
        # Every stage above ran under the probe; in_layout would have raised on a missing file.
        receipt["layout"]["stages"] = stages
        checks.append({"name": "layout_complete_for_every_stage", "result": "passed",
                       "stages": [stage["stage"] for stage in stages]})
    receipt["cleanup"] = "temporary server stopped; synthetic exports, engine layout and copied site removed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--browser", help="optional installed Chromium executable")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt_path = args.receipt.resolve()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
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
                          f"--stamps {','.join(fixture['stamps'])} --models {','.join(fixture['models'])}",
        "checks": [], "hosted_checks": "unrun", "native_sample_state": "unsupported by selected index",
    }
    try:
        run(args.site.resolve(), args.browser, receipt)
        receipt["result"] = "passed"
    except Exception as exc:
        receipt["result"] = "failed"
        receipt["failure"] = type(exc).__name__
        if isinstance(exc, layout.LayoutError):
            # Names repository-relative files and site CI's directories; workstation paths become placeholders.
            message = str(exc)
            for private, placeholder in ((str(args.site.resolve()), "SITE"), (str(ROOT), "ENGINE"),
                                         (str(Path(tempfile.gettempdir()).resolve()), "TMPDIR")):
                message = message.replace(private, placeholder)
            receipt["failure_message"] = message
        raise
    finally:
        write_json(receipt_path, receipt)
    print(f"boundary suite: {len(receipt['checks'])} checks passed; receipt: {args.receipt}")


if __name__ == "__main__":
    main()
