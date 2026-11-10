"""Preview one synthetic experiment bundle in the site's viewer page. No model, no measurement, no publication.

    python scripts/check_experiment_preview.py --site ../patientwords [--browser CHROMIUM] [--receipt FILE]
        [--shots DIR]

What runs, in order:

1. The site checkout is copied to a temporary directory (``.git``, caches and ``modes/`` are left out; the viewer
   references nothing under ``modes/``).
2. The experiment command line (``python -m scripts.experiments.cli``) takes the synthetic fixture protocol
   through validate, plan, an interrupted run, a resumed run, collect, compare and bundle. Its outputs go to a
   work directory in the temporary tree. The command line refuses any path that has a ``data`` component, so the
   finished bundle is copied, as a plain file, into the COPY's ``data/experiment_preview/``. Nothing is written
   into the real site or into either checkout.
3. The copy is served over HTTP on an ephemeral loopback port under ``/patientwords/``, and Chromium opens the
   real page, ``experiments/index.html``, with its real JavaScript.
4. The rendered text is compared with values this script works out itself: the softmax of the fixture logits,
   and the hand-computed ICA scores of the toy basis. They are not read back from the bundle.
5. Deliberate defects are served, each followed by a restored pass.

This is a software check of a viewer on hand-written numbers. It loads no model and says nothing about one.

Exit codes: 0 every check passed; 1 a check failed; 2 a setup problem (no Chromium, no site page, a failed
command-line step). Exit 2 is a blocked check, not a pass.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.server
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "experiments"
PROTOCOL = FIXTURES / "protocol_synthetic_ica.json"
LOGITS = FIXTURES / "behavior_logits.json"
ICA_INDEX = FIXTURES / "ica" / "fixture_index.json"
REGISTRY_FIXTURE = FIXTURES / "neuronpedia" / "representation_registry.fixture.json"

PAGE = "experiments/index.html"
BUNDLE_PARAM = "experiment_preview/bundle.json"
BUNDLE_SCHEMA = "patientwords.experiment-bundle/1"
RECEIPT_SCHEMA = "patientwords.experiment-preview-receipt/1"
EVIDENCE = "local synthetic software test only"
COPY_IGNORED = (".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules", ".DS_Store",
                "modes")
EXIT_PASS, EXIT_FAILED, EXIT_SETUP = 0, 1, 2

# Text the page prints. The checks compare rendered text, so these are the reader-visible strings.
SYNTHETIC_TEXT = "synthetic fixture - not a measurement"
IDLE_SENTENCES = (
    "This page displays method-comparison bundles exported by the engine's experiment interface.",
    "No study bundle is published yet.",
    "Synthetic fixtures are never published.",
)
NOT_RECORDED = "state not recorded"
WINDOW_MISS = "not observed in the top-k window"
NO_INTERVENTION = "no intervention in this bundle"
SHARE_LABEL = "squared-coordinate share, not a probability"
SHARE_UNDEFINED = "\u2014 not computed: zero or non-finite energy"
MINUS = "\u2212"
DISPLAY_STEP = 0.00005  # half a unit of the fourth printed decimal
BELOW_DISPLAY = ", below the 4 decimals shown"
EXECUTION_STATES = ("completed", "unsupported", "unavailable", "not_run", "invalid", "failed")

# Hand-computed ICA scores at the last token position of each variant, layer 1 of the toy basis, components 0-3.
# The toy basis reads back exactly the integer score vector each fixture row was built from (see the worked
# table in tests/fixtures/experiments/ica/build_ica_fixtures.py). These are literals, not an import, so that a
# change to the builder or the adapter cannot move the expectation with it; tests/test_check_experiment_preview.py
# fails if the two tables stop agreeing.
ICA_LAYER = 1
ICA_LAST_SCORES: dict[tuple[str, str], tuple[int, int, int, int]] = {
    ("fam-1", "clinical"): (3, -4, 0, 0),
    ("fam-1", "colloquial"): (-3, 4, 0, 0),
    ("fam-1", "normalized"): (1, 6, 2, 1),
    ("fam-2", "clinical"): (2, 0, 0, -1),
    ("fam-2", "colloquial"): (0, 0, 0, 0),
    ("fam-2", "normalized"): (0, 1, 0, 0),
    ("fam-3", "clinical"): (1, 1, 1, 1),
    ("fam-3", "colloquial"): (1, 1, 1, 1),
    ("fam-3", "normalized"): (-1, 2, 0, 2),
}
# Execution state this fixture protocol gives each method. Completed methods are the ones with an offline
# adapter; the other two are the capability matrix's unsupported and unavailable fixture rows.
EXPECTED_METHOD_STATE = {"behavior_next_token": "completed", "logit_lens": "completed", "ica_lens": "completed",
                         "j_lens": "unsupported", "jpp": "unavailable"}
TIE_TOLERANCE = 1e-12


class SetupProblem(Exception):
    """The check could not run. Reported with exit 2; never counted as a pass or as a page failure."""


# ------------------------------------------------------------------------------------------ address parameter

def bundle_param_refusal(value: str) -> str | None:
    """The reason the page refuses a ``?bundle=`` value, or None when it accepts it.

    A mirror of ``bundleRefusal`` in the site's ``experiments/index.html``, with the same order of tests and the
    same wording. The browser run compares the two on ``PARAM_CASES``; the mirror is not trusted on its own.
    """
    if value == "":
        return "the bundle parameter is empty"
    if len(value) > 200:
        return "the bundle parameter is longer than 200 characters"
    head = value.split(":", 1)[0]
    if ":" in value and head[:1].isascii() and head[:1].isalpha() and all(
            c.isascii() and (c.isalnum() or c in "+.-") for c in head):
        return "the bundle parameter has a scheme"
    if value[0] in "/\\":
        return "the bundle parameter is an absolute path"
    if ".." in value:
        return 'the bundle parameter contains ".."'
    if not all(c.isascii() and (c.isalnum() or c in "._/-") for c in value):
        return "the bundle parameter has a character outside A-Z a-z 0-9 . _ - /"
    for part in value.split("/"):
        if not part or part[0] == ".":
            return "the bundle parameter has an empty or dot-leading path segment"
    if not value.endswith(".json"):
        return "the bundle parameter does not name a .json file"
    return None


PARAM_CASES: tuple[str, ...] = (
    BUNDLE_PARAM,
    "",
    "../data/experiment_preview/bundle.json",
    "experiment_preview/../experiment_preview/bundle.json",
    "experiment_preview/..bundle.json",
    "/experiment_preview/bundle.json",
    "\\experiment_preview\\bundle.json",
    "//registry-fixture.invalid/bundle.json",
    "https://registry-fixture.invalid/bundle.json",
    "javascript:alert(1)",
    "data:application/json,{}",
    "experiment_preview/bundle.json?x=1",
    "experiment_preview/bundle.json#part",
    "experiment preview/bundle.json",
    "%2e%2e/experiment_preview/bundle.json",
    "experiment_preview//bundle.json",
    "experiment_preview/.bundle.json",
    "experiment_preview/bundle.txt",
    "x" * 196 + ".json",
)


# ------------------------------------------------------------------------------------------ expected values

def softmax(logits: Sequence[float]) -> list[float]:
    """Full-vocabulary softmax, shifted by the largest logit and summed with ``math.fsum``."""
    if not logits or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in logits):
        raise ValueError("softmax needs a non-empty list of finite numbers")
    peak = max(logits)
    weights = [math.exp(v - peak) for v in logits]
    total = math.fsum(weights)
    return [w / total for w in weights]


def expected_behavior(protocol: Mapping[str, Any], logits_doc: Mapping[str, Any]) -> dict[str, Any]:
    """Target probabilities and signed differences worked out from the fixture logits, without the bundle.

    Returns ``{"variants": {(family, variant, target): p}, "differences": {(family, comparison, target):
    {"a", "b", "difference", "tie", "a_name", "b_name"}}}``. ``tie`` is true when the recomputed difference is
    smaller than ``TIE_TOLERANCE`` in magnitude. For the fixture's integer weights that is an exact tie in exact
    arithmetic (the unit test checks this with fractions). Its floating-point value is 0 or one rounding step
    either way, depending on how the softmax is summed, so no single printed value can be expected for it.
    A family, variant or token the fixture does not hold raises ``ValueError``: a missing expectation is never
    replaced by a number.
    """
    rows = {(row["family_id"], row["variant"]): softmax(row["logits"]) for row in logits_doc["rows"]}
    variants: dict[tuple[str, str, str], float] = {}
    differences: dict[tuple[str, str, str], dict[str, Any]] = {}
    for family in protocol["case_families"]:
        fid = family["family_id"]
        for variant in family["variants"]:
            if (fid, variant) not in rows:
                raise ValueError(f"the logits fixture has no row for {fid} {variant}")
            for target in family["targets"]:
                token = target["token_ids"][0]
                variants[(fid, variant, target["id"])] = rows[(fid, variant)][token]
        for comparison in protocol["comparisons"]:
            for target in family["targets"]:
                a = variants[(fid, comparison["a"], target["id"])]
                b = variants[(fid, comparison["b"], target["id"])]
                difference = a - b
                differences[(fid, comparison["id"], target["id"])] = {
                    "a": a, "b": b, "difference": difference, "tie": abs(difference) < TIE_TOLERANCE,
                    "a_name": comparison["a"], "b_name": comparison["b"]}
    return {"variants": variants, "differences": differences}


def energy_shares(scores: Sequence[int]) -> list[float | None]:
    """Squared-coordinate shares of an integer score vector; all None when the vector is zero."""
    total = sum(Fraction(v) ** 2 for v in scores)
    if total == 0:
        return [None for _ in scores]
    return [float(Fraction(v) ** 2 / total) for v in scores]


def expected_ica(protocol: Mapping[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    """Per family, comparison and component: both signed scores, their difference and both energy shares, from
    ``ICA_LAST_SCORES``. A share of a zero vector is None (undefined), never 0."""
    out: dict[tuple[str, str, int], dict[str, Any]] = {}
    for family in protocol["case_families"]:
        fid = family["family_id"]
        for comparison in protocol["comparisons"]:
            a = ICA_LAST_SCORES[(fid, comparison["a"])]
            b = ICA_LAST_SCORES[(fid, comparison["b"])]
            shares_a, shares_b = energy_shares(a), energy_shares(b)
            for component in range(len(a)):
                out[(fid, comparison["id"], component)] = {
                    "score_a": float(a[component]), "score_b": float(b[component]),
                    "difference": float(a[component] - b[component]),
                    "share_a": shares_a[component], "share_b": shares_b[component],
                    "a_name": comparison["a"], "b_name": comparison["b"]}
    return out


def _fixed(value: float) -> str:
    """Magnitude to four decimals, ties away from zero on the exact binary value, as JavaScript ``toFixed(4)``
    gives. A non-zero magnitude that would print as 0.0000 is printed with an exponent instead."""
    magnitude = abs(value)
    if magnitude != 0 and magnitude < DISPLAY_STEP:
        mantissa, exponent = f"{magnitude:.2e}".split("e")
        return f"{mantissa}e{int(exponent)}"
    return str(Decimal(magnitude).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def fmt_plain(value: float) -> str:
    """How the page prints a probability or share."""
    return (MINUS if value < 0 else "") + _fixed(value)


def fmt_signed(value: float) -> str:
    """How the page prints a signed quantity. Zero is the digit 0 with no sign."""
    if value == 0:
        return "0"
    return ("+" if value > 0 else MINUS) + _fixed(value)


def sign_text(value: float, a_name: str, b_name: str) -> str:
    """The sign in words, as the page prints it beside a signed difference. A non-zero value too small for the
    four printed decimals keeps its sign and says that it is below them."""
    if value == 0:
        return "no difference"
    return f"{a_name if value > 0 else b_name} higher" + (BELOW_DISPLAY if abs(value) < DISPLAY_STEP else "")


# ------------------------------------------------------------------------------------------ receipt

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def identity(root: Path, excluded: Path | None = None) -> dict[str, Any]:
    """HEAD, tracked diff identity and untracked-file identity of a checkout. Paths never enter the result.

    A directory that is not a Git checkout, or a failing ``git``, gives ``head: None`` with the reason in
    ``not_recorded``; nothing is guessed.
    """
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)
    try:
        head = git("rev-parse", "HEAD").decode().strip()
        exclusions = ["."]
        if excluded is not None and excluded.is_relative_to(root):
            exclusions.append(f":(exclude){excluded.relative_to(root)}")
        diff = git("diff", "--binary", "HEAD", "--", *exclusions)
        untracked = sorted(name for name in git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
                           if name and (root / name) != excluded and (root / name).is_file())
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"head": None, "not_recorded": f"git could not describe this directory: {type(exc).__name__}"}
    listing = hashlib.sha256()
    for name in untracked:
        listing.update(f"{name}\0{sha256_file(root / name)}\n".encode())
    return {"head": head, "tracked_diff_sha256": sha256_bytes(diff), "untracked_files": len(untracked),
            "untracked_listing_sha256": listing.hexdigest(), "dirty": bool(diff or untracked)}


def file_hashes(root: Path, paths: Sequence[Path]) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(paths)}


def new_receipt(site: Path, receipt_path: Path | None) -> dict[str, Any]:
    """The receipt before any check has run. It binds both checkouts, the fixtures and the tools by hash."""
    fixtures = [p for p in FIXTURES.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    tools = [Path(__file__).resolve(), ROOT / "schemas" / "experiments" / "bundle.v1.schema.json",
             ROOT / "data" / "experiments" / "capability_matrix.v1.json",
             *[p for p in (ROOT / "scripts" / "experiments").rglob("*.py")]]
    page = site / PAGE
    return {
        "schema": RECEIPT_SCHEMA,
        "evidence": EVIDENCE,
        "statement": "A viewer page rendered one bundle built from hand-written fixture numbers. No model was "
                     "loaded, nothing was measured, nothing was published or deployed.",
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "python scripts/check_experiment_preview.py --site SITE [--browser CHROMIUM] [--receipt RECEIPT] "
                   "[--shots SHOTS]",
        "engine": identity(ROOT, receipt_path),
        "frontend": identity(site, receipt_path),
        "page_sha256": {PAGE: sha256_file(page) if page.is_file() else None},
        "fixture_sha256": file_hashes(ROOT, fixtures),
        "tool_sha256": file_hashes(ROOT, [p for p in tools if p.is_file()]),
        "versions": {"python": sys.version.split()[0], "playwright": None, "chromium": None},
        "bundle": None,
        "cli_steps": [],
        "checks": [],
        "screenshots": [],
        "browser_external_requests": [],
        "result": "not_run",
    }


@dataclass
class Recorder:
    """Runs named checks and files each result in the receipt. A failed check does not stop the later ones."""
    receipt: dict[str, Any]
    failed: int = 0

    def run(self, name: str, action: Callable[[], Mapping[str, Any] | None], *, result: str = "passed") -> bool:
        try:
            detail = dict(action() or {})
        except SetupProblem:
            raise
        except Exception as exc:  # an assertion, or a browser timeout while waiting for a state
            self.failed += 1
            message = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else ""
            self.receipt["checks"].append({"name": name, "result": "failed", "exception": type(exc).__name__,
                                           "message": message})
            print(f"FAIL {name}: {type(exc).__name__}: {message}")
            return False
        self.receipt["checks"].append({"name": name, "result": result, **detail})
        print(f"ok   {name}")
        return True


def rejected(action: Callable[[], Any]) -> str:
    """A deliberate defect counts only when the named assertion actually fails on it."""
    try:
        action()
    except AssertionError as exc:
        return str(exc).strip().splitlines()[0][:240]
    raise AssertionError("a deliberate defect was not detected")


# ------------------------------------------------------------------------------------------ bundle from the CLI

def run_cli(*argv: str, expect: int = 0) -> dict[str, Any]:
    """One experiment command-line call from the engine root. Returns its JSON; raises ``SetupProblem`` when the
    exit code is not the expected one, with the command's own output."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-m", "scripts.experiments.cli", *argv], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != expect:
        raise SetupProblem(f"experiment command line step {argv[0]!r} exited {proc.returncode}, expected {expect}:\n"
                           f"{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise SetupProblem(f"experiment command line step {argv[0]!r} printed no JSON: {proc.stdout[-400:]}") from exc


def build_bundle(work: Path, receipt: dict[str, Any]) -> Path:
    """Run the synthetic slice through the real command line, with one interruption and a resume.

    Returns the bundle path inside ``work``. Each step's summary goes into ``receipt['cli_steps']``.
    """
    steps = receipt["cli_steps"]
    plan, runs, bundle = work / "plan.json", work / "runs", work / "bundle.json"
    validated = run_cli("validate", "--protocol", str(PROTOCOL))
    steps.append({"step": "validate", "status": validated.get("status"), "synthetic": validated.get("synthetic"),
                  "protocol_sha256": validated.get("protocol_sha256")})
    planned = run_cli("plan", "--protocol", str(PROTOCOL), "--out", str(plan))
    steps.append({"step": "plan", "tasks": planned["totals"]["tasks"],
                  "by_planned_state": planned["totals"]["by_planned_state"]})
    run = ("run-fixture", "--plan", str(plan), "--fixtures", str(FIXTURES), "--run-dir", str(runs))
    first = run_cli(*run, "--stop-after", "5")
    steps.append({"step": "run-fixture --stop-after 5", "executed": first["executed"], "reused": first["reused"],
                  "stopped_early": first["stopped_early"], "remaining_ready": first["remaining_ready"]})
    second = run_cli(*run)
    steps.append({"step": "run-fixture (resume)", "executed": second["executed"], "reused": second["reused"],
                  "remaining_ready": second["remaining_ready"]})
    collected = run_cli("collect", "--run-dir", str(runs), "--require-complete")
    steps.append({"step": "collect --require-complete", "complete": collected["complete"],
                  "by_state": collected["by_state"], "executed_attempts": collected["executed_attempts"]})
    compared = run_cli("compare", "--run-dir", str(runs), "--out", str(work / "compare.json"))
    steps.append({"step": "compare", "behavior_blocks_computed": compared["behavior_blocks_computed"],
                  "ica_blocks_computed": compared["ica_blocks_computed"]})
    bundled = run_cli("bundle", "--run-dir", str(runs), "--out", str(bundle))
    steps.append({"step": "bundle", "schema_version": bundled["schema_version"], "by_state": bundled["by_state"]})
    ready = planned["totals"]["by_planned_state"].get("ready")
    if not (first["stopped_early"] and first["executed"] == 5 and second["reused"] == 5
            and second["executed"] == ready - 5 and second["remaining_ready"] == 0 and collected["complete"]):
        raise SetupProblem(f"the interrupted run did not resume as the store documents: {steps}")
    return bundle


def copy_site(site: Path, destination: Path) -> None:
    shutil.copytree(site, destination, ignore=shutil.ignore_patterns(*COPY_IGNORED))


# ------------------------------------------------------------------------------------------ HTTP

class Handler(http.server.SimpleHTTPRequestHandler):
    """Plain static HTTP. Conditional requests are answered in full and nothing is cacheable, so a bundle that
    is rewritten within one second is never served from a browser cache."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        for name in ("If-Modified-Since", "If-None-Match"):
            if name in self.headers:
                del self.headers[name]
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


# ------------------------------------------------------------------------------------------ browser helpers

@dataclass
class PageLog:
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    http_errors: list[str] = field(default_factory=list)

    def data_requests(self) -> list[str]:
        return [url for url in self.requests if "/data/" in urlsplit(url).path]


def page_url(base: str, bundle: str | None = None, *, raw_query: str | None = None) -> str:
    """The viewer's URL. ``bundle`` is percent-encoded in full; ``raw_query`` is used as written."""
    if raw_query is not None:
        return f"{base}/{PAGE}?{raw_query}"
    return f"{base}/{PAGE}" + ("" if bundle is None else "?bundle=" + quote(bundle, safe=""))


def open_all_families(page: Any) -> int:
    """Open every family fold with the page's own button, from the keyboard. Returns how many were closed."""
    closed = "() => document.querySelectorAll('#exp-families details.fam-fold:not([open])').length"
    before = page.evaluate(closed)
    if before:
        page.focus("#exp-fam-toggle")
        page.keyboard.press("Enter")
        assert page.evaluate(closed) == 0, "the family button did not open every family"
    return before


def open_page(context: Any, url: str, *, settle: bool = True, expand: bool = True) -> tuple[Any, PageLog]:
    """Open the viewer and wait until it has left the loading state. Returns the page and what it logged.

    With ``expand`` a rendered bundle has every family opened, so that the text of every row can be read.
    """
    page, log = context.new_page(), PageLog()
    page.on("pageerror", lambda error: log.page_errors.append(str(error)))
    page.on("console", lambda message: log.console_errors.append(message.text) if message.type == "error" else None)
    page.on("request", lambda request: None if request.url.startswith("data:") else log.requests.append(request.url))
    page.on("requestfailed", lambda request: log.failed.append(request.url))
    page.on("response", lambda response: log.http_errors.append(f"{response.url} -> HTTP {response.status}")
            if response.status >= 400 else None)
    page.goto(url, wait_until="load", timeout=30_000)
    if settle:
        page.wait_for_function("() => { const s = document.body.dataset.expState; return !!s && s !== 'loading'; }",
                               timeout=20_000)
        page.wait_for_load_state("networkidle", timeout=20_000)
        if expand and page.evaluate("() => document.body.dataset.expState") == "ready":
            open_all_families(page)
    return page, log


def page_state(page: Any) -> dict[str, Any]:
    return page.evaluate("""() => {
        const box = document.getElementById('exp-state');
        const visible = (node) => !!node && node.getClientRects().length > 0;
        return {
            state: document.body.dataset.expState || null,
            box_visible: visible(box),
            box_class: box.className,
            box_role: box.getAttribute('role'),
            label: box.querySelector('b') ? box.querySelector('b').textContent : null,
            messages: Array.from(box.querySelectorAll('span')).map((s) => s.textContent),
            border_style: getComputedStyle(box).borderTopStyle + '/' + getComputedStyle(box).borderLeftStyle,
            idle_visible: visible(document.getElementById('exp-idle')),
            results_visible: visible(document.getElementById('exp-results')),
            family_sections: document.querySelectorAll('#exp-families section').length,
            method_rows: document.querySelectorAll('#exp-methods-body tr').length,
        };
    }""")


def table_rows(page: Any) -> dict[str, list[dict[str, Any]]]:
    """Every data row of the rendered bundle as ``{kind: [{attrs, cells}]}``, with the text a reader sees."""
    rows = page.evaluate("""() => Array.from(document.querySelectorAll('#exp-results tr[data-kind]')).map((tr) => ({
        kind: tr.dataset.kind,
        attrs: Object.assign({}, tr.dataset),
        cells: Object.fromEntries(Array.from(tr.querySelectorAll('td[data-col]')).map(
            (td) => [td.dataset.col, td.innerText.trim()])),
    }))""")
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["kind"], []).append(row)
    return out


def method_rows(page: Any) -> dict[str, dict[str, str]]:
    rows = page.evaluate("""() => Array.from(document.querySelectorAll('#exp-methods-body tr[data-method]')).map(
        (tr) => [tr.dataset.method, Object.fromEntries(Array.from(tr.querySelectorAll('td[data-col]')).map(
            (td) => [td.dataset.col, td.innerText.trim().replace(/\\s+/g, ' ')]))])""")
    return {name: cells for name, cells in rows}


def keyed(rows: Sequence[Mapping[str, Any]], *names: str) -> dict[tuple[str, ...], dict[str, str]]:
    out: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(str(row["attrs"][name]) for name in names)
        assert key not in out, f"two rendered rows share the key {key}"
        out[key] = row["cells"]
    return out


# ------------------------------------------------------------------------------------------ assertions

def assert_ready(page: Any, log: PageLog, base: str) -> None:
    state = page_state(page)
    assert state["state"] == "ready", f"page state is {state['state']!r}: {state['messages']}"
    assert state["results_visible"] and not state["idle_visible"], "the results are hidden or the idle text shows"
    assert not log.console_errors and not log.page_errors, f"browser errors: {log.console_errors + log.page_errors}"
    assert not log.failed and not log.http_errors, f"failed requests: {log.failed + log.http_errors}"
    wanted = f"{base}/data/{BUNDLE_PARAM}"
    assert log.data_requests() == [wanted], f"data requests were {log.data_requests()}, expected only {wanted}"


def assert_banner(page: Any, families: int) -> dict[str, Any]:
    found = page.evaluate("""() => Array.from(document.querySelectorAll('[data-kind="synthetic-banner"]')).map((p) => ({
        text: p.firstChild ? p.firstChild.textContent : '',
        visible: p.getClientRects().length > 0,
        in_family: p.closest('section.fam') ? p.closest('section.fam').dataset.family : null,
        in_methods: !!p.closest('#methods'),
        in_evidence: !!p.closest('#evidence'),
    }))""")
    assert found and all(b["text"] == SYNTHETIC_TEXT and b["visible"] for b in found), f"banner text: {found}"
    assert sum(1 for b in found if b["in_evidence"]) == 1, "the evidence section does not carry the banner once"
    assert sum(1 for b in found if b["in_methods"]) == 1, "the methods table does not carry the banner"
    assert len({b["in_family"] for b in found if b["in_family"]}) == families, "a family section lacks the banner"
    evidence = page.locator('#exp-evidence dd[data-col="evidence_class"]').inner_text().strip()
    assert evidence == "synthetic_fixture", f"evidence class shown is {evidence!r}"
    return {"banners": len(found)}


def assert_behavior(page: Any, expected: Mapping[str, Any]) -> dict[str, Any]:
    rows = table_rows(page)
    shown = keyed(rows.get("behavior-variant", []), "family", "variant", "target")
    assert set(shown) == set(expected["variants"]), "the per-variant behaviour rows do not match the fixture's set"
    for key, value in expected["variants"].items():
        assert shown[key]["probability"] == fmt_plain(value), (
            f"{key}: page shows {shown[key]['probability']!r}, the fixture logits give {fmt_plain(value)!r}")
    shown = keyed(rows.get("behavior-diff", []), "family", "comparison", "target")
    assert set(shown) == set(expected["differences"]), "the difference rows do not match the fixture's set"
    zeros, rounding = 0, []
    for key, want in expected["differences"].items():
        cells = shown[key]
        assert (cells["a"], cells["b"]) == (fmt_plain(want["a"]), fmt_plain(want["b"])), (
            f"{key}: page shows a, b = {cells['a']!r}, {cells['b']!r}; the fixture logits give "
            f"{fmt_plain(want['a'])!r}, {fmt_plain(want['b'])!r}")
        got = (cells["difference"], cells["sign"])
        if not want["tie"]:
            wanted = (fmt_signed(want["difference"]), sign_text(want["difference"], want["a_name"], want["b_name"]))
            assert got == wanted, f"{key}: page shows {got}, the fixture logits give {wanted}"
        elif got == ("0", "no difference"):
            zeros += 1
        else:
            # An exact tie that the bundle records one rounding step from zero. The page must print the recorded
            # value with its exponent and its sign in words, never as 0.0000 and never as a missing value.
            higher = {"+": want["a_name"], MINUS: want["b_name"]}.get(got[0][:1])
            assert higher and "e-" in got[0] and float(got[0][1:]) < TIE_TOLERANCE, (
                f"{key}: an exact tie in the fixture is shown as {got[0]!r}")
            assert got[1] == f"{higher} higher{BELOW_DISPLAY}", f"{key}: the sign text reads {got[1]!r}"
            rounding.append({"row": " / ".join(key), "difference_shown": got[0], "sign_shown": got[1]})
    assert zeros > 0, "no exact zero difference is shown as 0 with 'no difference'; the valid-zero state is unchecked"
    return {"variant_values": len(expected["variants"]), "differences": len(expected["differences"]),
            "zero_differences_shown_as_0_no_difference": zeros,
            "exact_ties_the_bundle_records_as_float_rounding": rounding}


def assert_ica(page: Any, expected: Mapping[tuple[str, str, int], Mapping[str, Any]],
               basis_sha256: str) -> dict[str, Any]:
    rows = table_rows(page)
    shown = {(f, c, int(k)): cells for (f, c, k), cells in
             keyed(rows.get("ica", []), "family", "comparison", "component").items()}
    assert set(shown) == set(expected), "the ICA rows do not match the hand-computed set"
    undefined = 0
    for key, want in expected.items():
        cells = shown[key]
        share = [SHARE_UNDEFINED if want[name] is None else fmt_plain(want[name]) for name in ("share_a", "share_b")]
        undefined += sum(1 for name in ("share_a", "share_b") if want[name] is None)
        got = (cells["layer"], cells["score_a"], cells["score_b"], cells["difference"], cells["sign"],
               cells["share_a"], cells["share_b"])
        wanted = (str(ICA_LAYER), fmt_signed(want["score_a"]), fmt_signed(want["score_b"]),
                  fmt_signed(want["difference"]), sign_text(want["difference"], want["a_name"], want["b_name"]),
                  share[0], share[1])
        assert got == wanted, f"{key}: page shows {got}, the hand-computed values are {wanted}"
    blocks = page.evaluate("""() => Array.from(document.querySelectorAll('[data-kind="ica-block"]')).map((d) => ({
        basis: d.querySelector('dd[data-col="ica_basis"]').innerText.trim(),
        label: d.querySelector('dd[data-col="ica_share_label"]').innerText.trim(),
        preprocessing: d.querySelector('dd[data-col="ica_preprocessing"]').innerText.trim(),
        heads: Array.from(d.querySelectorAll('th')).map((th) => th.textContent),
    }))""")
    assert blocks and all(b["basis"] == basis_sha256 for b in blocks), "the basis hash shown is not the fixture's"
    assert all(b["label"] == SHARE_LABEL and sum(SHARE_LABEL in h for h in b["heads"]) == 2 for b in blocks), (
        "an energy-share column is not labelled as a share that is not a probability")
    assert undefined > 0, "the fixture no longer holds a zero score vector; the undefined-share state is unchecked"
    return {"component_rows": len(expected), "undefined_shares_shown_as_not_computed": undefined,
            "preprocessing_shown": sorted({b["preprocessing"] for b in blocks})}


def assert_readout(page: Any, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Rendering fidelity only: the ranks on the page are the bundle's ranks. No independent oracle is used."""
    shown = keyed(table_rows(page).get("readout", []), "family", "method", "comparison", "layer", "target")
    expected: dict[tuple[str, ...], dict[str, str]] = {}
    misses = 0
    for family in bundle["comparisons"]:
        for entry in family["comparisons"]:
            for method, block in entry["readout"].items():
                if block.get("status") != "computed":
                    continue
                for layer in block["layers"]:
                    for target in layer["targets"]:
                        cells = {}
                        for side in ("a", "b"):
                            cells[f"raw_{side}"] = str(target[side]["raw_rank"])
                            cells[f"filtered_{side}"] = str(target[side]["filtered_rank"])
                            seen = [f"top-{k}" for k in sorted(target[side]["top_k"], key=int)
                                    if target[side]["top_k"][k] == "observed"]
                            missed = [f"top-{k}" for k in sorted(target[side]["top_k"], key=int)
                                      if target[side]["top_k"][k] == "not_observed_in_window"]
                            assert len(seen) + len(missed) == len(target[side]["top_k"]), "an unknown window value"
                            misses += bool(missed)
                            window = (["observed in " + ", ".join(seen)] if seen else []) + (
                                [f"{WINDOW_MISS}: " + ", ".join(missed)] if missed else [])
                            cells[f"window_{side}"] = "\n".join(window)
                        expected[(family["family_id"], method, entry["comparison_id"], str(layer["layer"]),
                                  target["target_id"])] = cells
    assert expected and set(shown) == set(expected), "the readout rows do not match the bundle's computed blocks"
    for key, want in expected.items():
        got = {name: shown[key][name] for name in want}
        assert got == want, f"{key}: page shows {got}, the bundle holds {want}"
    order = page.evaluate("""() => Array.from(document.querySelector('tr[data-kind="readout"]').querySelectorAll(
        'td[data-col]')).map((td) => td.dataset.col)""")
    for side in ("a", "b"):
        assert order.index(f"filtered_{side}") == order.index(f"raw_{side}") + 1, "raw and filtered rank are apart"
    assert misses > 0, "the fixture no longer holds a top-k miss; the miss wording is unchecked"
    return {"readout_rows": len(expected), "cells_wording_a_top_k_miss": misses,
            "oracle": "the bundle itself (rendering fidelity), not an independent computation"}


def assert_methods(page: Any, protocol: Mapping[str, Any], bundle: Mapping[str, Any]) -> dict[str, Any]:
    shown = method_rows(page)
    planned = [method["id"] for method in protocol["methods"]]
    assert sorted(shown) == sorted(planned), f"methods listed {sorted(shown)}, protocol plans {sorted(planned)}"
    assert set(planned) == set(EXPECTED_METHOD_STATE), "the fixture protocol's methods changed; update the expectation"
    per_method = sum(len(family["variants"]) for family in protocol["case_families"])
    reasons = {row["method"]: row["reasons"] for row in bundle["methods_not_run"]}
    for method, state in EXPECTED_METHOD_STATE.items():
        cells = shown[method]
        assert cells["state"] == f"{state} {per_method} of {per_method} tasks", (
            f"{method}: state cell reads {cells['state']!r}")
        if state == "completed":
            assert cells["reason"] == "none recorded: every planned task completed", f"{method}: {cells['reason']!r}"
        else:
            assert reasons[method] and all(reason in cells["reason"] for reason in reasons[method]), (
                f"{method}: the reason cell does not carry the bundle's reason")
            assert "completed" not in cells["state"], f"{method}: a method that did not run reads as completed"
    return {"methods": len(planned), "tasks_per_method": per_method,
            "not_completed": {m: s for m, s in EXPECTED_METHOD_STATE.items() if s != "completed"}}


def assert_not_computed_blocks(page: Any, families: int) -> dict[str, Any]:
    found = page.evaluate("""() => Array.from(document.querySelectorAll('[data-kind="not-computed"]')).map((p) => ({
        method: p.dataset.method, family: p.dataset.family, text: p.innerText,
        states: Array.from(p.querySelectorAll('[data-col="state"]')).map((s) => s.textContent),
    }))""")
    for method, state in EXPECTED_METHOD_STATE.items():
        if state == "completed":
            continue
        mine = [b for b in found if b["method"] == method]
        assert len({b["family"] for b in mine}) == families, f"{method}: not shown as not computed in every family"
        assert all(b["states"] == [state] and "Reason: " in b["text"] for b in mine), (
            f"{method}: a family block does not state {state} with its reason")
    return {"not_computed_blocks": len(found)}


def assert_other_sections(page: Any, protocol: Mapping[str, Any], validated: Mapping[str, Any]) -> dict[str, Any]:
    families = len(protocol["case_families"])
    interventions = page.locator('[data-kind="intervention"]').all_inner_texts()
    assert interventions == [NO_INTERVENTION] * families, f"intervention blocks read {interventions}"
    text = {name: page.locator(f'#exp-protocol dd[data-col="{name}"]').inner_text().strip()
            for name in ("protocol_id", "protocol_version", "protocol_sha256", "model_id", "model_revision",
                         "tokenizer_id", "tokenizer_revision")}
    model = protocol["model"]
    wanted = {"protocol_id": protocol["protocol_id"], "protocol_version": protocol["version"],
              "protocol_sha256": validated["protocol_sha256"], "model_id": model["hf_id"],
              "model_revision": model["revision"], "tokenizer_id": model["tokenizer_id"],
              "tokenizer_revision": model["tokenizer_revision"]}
    assert text == wanted, f"protocol and model identity shown {text}, the fixture protocol gives {wanted}"
    variant_count = sum(len(family["variants"]) for family in protocol["case_families"])
    tasks = variant_count * len(protocol["methods"])
    planned = page.locator('#exp-totals dd[data-col="planned_tasks"]').inner_text().strip()
    assert planned == str(tasks), f"planned tasks shown {planned!r}; families x variants x methods is {tasks}"
    reused = page.locator('#exp-totals dd[data-col="reused"]').inner_text().strip()
    assert reused.isdigit() or reused.startswith("\u2014"), f"the reuse count reads {reused!r}"
    packages = page.locator('#exp-provenance dd[data-col="packages"]').inner_text().strip()
    assert packages.startswith("python "), f"package versions read {packages!r}"
    links = page.evaluate("""() => ({
        statement: document.querySelectorAll('#exp-links [data-kind="no-link-records"]').length,
        anchors: document.querySelectorAll('#exp-links a').length,
    })""")
    assert links == {"statement": 1, "anchors": 0}, f"a bundle with no link record shows {links}"
    limitations = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#exp-limitations li[data-limitation]')).map((li) => li.dataset.limitation)""")
    assert limitations[:1] == ["synthetic_not_measurement"], f"limitations start with {limitations[:1]}"
    own = page.locator("#exp-limitations").inner_text()
    assert "No value on this page is a clinical risk score." in own, "the page's own limitation is absent"
    variants = table_rows(page).get("variant", [])
    assert len(variants) == variant_count, "a family does not list every variant"
    return {"planned_tasks": tasks, "reuse_count_shown": reused, "limitations": len(limitations),
            "prompt_hash_cells": sorted({row["cells"]["prompt_sha256"] for row in variants})[:2],
            "token_count_cells": sorted({row["cells"]["n_tokens"] for row in variants})[:2]}


def assert_no_overflow(page: Any) -> dict[str, Any]:
    size = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, inner: window.innerWidth})")
    assert size["scroll"] <= size["inner"], f"the page is {size['scroll']} px wide in a {size['inner']} px window"
    return {"scroll_width": size["scroll"], "window_width": size["inner"]}


def assert_keyboard(page: Any) -> dict[str, Any]:
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.className") == "skip", "the first Tab stop is not the skip link"
    presses = 1
    while presses < 40 and not page.evaluate("() => !!document.activeElement.closest('.toc')"):
        page.keyboard.press("Tab")
        presses += 1
    assert page.evaluate("() => !!document.activeElement.closest('.toc')"), "Tab never reached the section links"
    page.keyboard.press("Enter")
    assert page.evaluate("() => location.hash") == "#evidence", "Enter on a section link did not move to the section"
    page.evaluate("() => document.querySelector('#exp-results details.fold > summary').focus()")
    page.keyboard.press("Enter")
    opened = page.evaluate("() => document.querySelector('#exp-results details.fold').open")
    page.keyboard.press("Enter")
    closed = not page.evaluate("() => document.querySelector('#exp-results details.fold').open")
    assert opened and closed, "a fold did not open and close from the keyboard"
    stray = page.evaluate("""() => Array.from(document.querySelectorAll(
        'main [onclick], main [role="button"], main [tabindex]'))
        .filter((n) => !['A', 'BUTTON', 'SUMMARY'].includes(n.tagName)).length""")
    assert stray == 0, "an element takes pointer input without being a link, a button or a summary"
    return {"tab_presses_to_section_links": presses}


# ------------------------------------------------------------------------------------------ the browser checks

@dataclass
class Session:
    """What the browser checks share: the served copy, the two browser contexts and the expectations."""
    base: str
    served: Path
    original: bytes
    bundle: dict[str, Any]
    protocol: dict[str, Any]
    validated: dict[str, Any]
    behavior: dict[str, Any]
    ica: dict[tuple[str, str, int], dict[str, Any]]
    basis_sha256: str
    desktop: Any
    phone: Any
    receipt: dict[str, Any]
    shots: Path | None
    states: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def families(self) -> int:
        return len(self.protocol["case_families"])

    @property
    def url(self) -> str:
        return page_url(self.base, BUNDLE_PARAM)

    def write(self, doc: Any) -> None:
        self.served.write_text(json.dumps(doc), encoding="utf-8")

    def restore(self) -> None:
        self.served.write_bytes(self.original)

    def open(self, url: str | None = None, *, phone: bool = False, expand: bool = True) -> tuple[Any, PageLog]:
        return open_page(self.phone if phone else self.desktop, url or self.url, expand=expand)

    def shot(self, page: Any, name: str) -> None:
        if self.shots is None:
            return
        self.shots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(self.shots / name), full_page=True)
        self.receipt["screenshots"].append({"file": name, "sha256": sha256_file(self.shots / name),
                                            "device_scale_factor": 2})

    def note_state(self, state: Mapping[str, Any]) -> None:
        self.states[state["state"]] = {"label": state["label"], "class": state["box_class"],
                                       "border": state["border_style"]}

    def core(self, page: Any, log: PageLog) -> None:
        """The assertions a correct render must pass; a defect must make at least one of them fail."""
        assert_ready(page, log, self.base)
        assert_behavior(page, self.behavior)
        assert_ica(page, self.ica, self.basis_sha256)
        assert_methods(page, self.protocol, self.bundle)

    def restored_pass(self) -> None:
        self.restore()
        page, log = self.open()
        try:
            self.core(page, log)
        finally:
            page.close()


def check_no_parameter(s: Session) -> dict[str, Any]:
    url = page_url(s.base)
    page, log = s.open(url)
    try:
        state = page_state(page)
        assert state["state"] == "idle" and state["idle_visible"], f"state {state['state']!r}"
        assert not state["box_visible"] and not state["results_visible"], "a state box or results show"
        assert state["method_rows"] == 0, "the methods table has rows with no bundle"
        shown = page.locator("#exp-idle").inner_text()
        assert all(sentence in shown for sentence in IDLE_SENTENCES), f"statement reads {shown!r}"
        assert log.requests == [url], f"requests made with no parameter: {log.requests}"
        assert not log.console_errors and not log.page_errors and not log.http_errors, "browser errors"
        s.states["idle"] = {"label": "idle statement", "class": "idle", "border": "statement"}
        s.shot(page, "experiment_no_parameter_1280.png")
        return {"requests": len(log.requests), "data_requests": len(log.data_requests())}
    finally:
        page.close()


def check_rendered_bundle(s: Session, recorder: Recorder) -> None:
    """The checks that read one rendered page at 1280 px. Each is filed under its own name."""
    page, log = s.open()
    try:
        recorder.run("bundle_renders_with_no_console_error_and_no_failed_request",
                     lambda: assert_ready(page, log, s.base))
        s.note_state(page_state(page))
        recorder.run("synthetic_banner_beside_the_results", lambda: assert_banner(page, s.families))
        recorder.run("behaviour_values_equal_softmax_of_fixture_logits", lambda: assert_behavior(page, s.behavior))
        recorder.run("ica_scores_equal_hand_computed_fixture_values",
                     lambda: assert_ica(page, s.ica, s.basis_sha256))
        recorder.run("readout_raw_and_filtered_ranks_side_by_side", lambda: assert_readout(page, s.bundle))
        recorder.run("every_planned_method_listed_with_state_and_reason",
                     lambda: assert_methods(page, s.protocol, s.bundle))
        recorder.run("unsupported_and_unavailable_methods_stated_in_each_family",
                     lambda: assert_not_computed_blocks(page, s.families))
        recorder.run("protocol_model_totals_links_limitations",
                     lambda: assert_other_sections(page, s.protocol, s.validated))
        recorder.run("no_horizontal_overflow_at_1280", lambda: assert_no_overflow(page))
        s.shot(page, "experiment_bundle_1280.png")
    finally:
        page.close()


def check_keyboard(s: Session) -> dict[str, Any]:
    # A fresh page: Tab must start from the top of the document, not from a control another check used.
    page, _ = s.open(expand=False)
    try:
        return assert_keyboard(page)
    finally:
        page.close()


FOLD_STATE = """() => ({
    open: Array.from(document.querySelectorAll('#exp-families details.fam-fold')).map((d) => d.open),
    headings: Array.from(document.querySelectorAll('#exp-families details.fam-fold > summary h3'))
        .filter((h) => h.getClientRects().length > 0).length,
    banners: Array.from(document.querySelectorAll('#exp-families [data-kind="synthetic-banner"]'))
        .filter((p) => p.getClientRects().length > 0).length,
    button: document.getElementById('exp-fam-toggle').textContent,
})"""


def check_family_folds(s: Session) -> dict[str, Any]:
    """The first family is open, the rest are closed, and a closed family keeps its heading and its label."""
    page, _ = s.open(expand=False)
    try:
        first = page.evaluate(FOLD_STATE)
        assert first["open"] == [True] + [False] * (s.families - 1), f"default folds: {first['open']}"
        assert first["headings"] == s.families and first["banners"] == s.families, (
            "a closed family hides its heading or its synthetic label")
        assert first["button"] == "Open every family", f"button reads {first['button']!r}"
        page.focus("#exp-fam-toggle")
        page.keyboard.press("Enter")
        opened = page.evaluate(FOLD_STATE)
        page.keyboard.press("Enter")
        closed = page.evaluate(FOLD_STATE)
        assert all(opened["open"]) and opened["button"] == "Close every family", f"after one press: {opened}"
        assert not any(closed["open"]) and closed["button"] == "Open every family", f"after two: {closed}"
        page.focus("#exp-families details.fam-fold > summary")
        page.keyboard.press("Enter")
        assert page.evaluate(FOLD_STATE)["open"][0], "Enter on a family heading did not open it"
        return {"families": s.families, "open_by_default": 1}
    finally:
        page.close()


def check_narrow(s: Session) -> dict[str, Any]:
    page, log = s.open(phone=True)
    try:
        assert_ready(page, log, s.base)
        assert_behavior(page, s.behavior)
        assert_banner(page, s.families)
        detail = assert_no_overflow(page)
        s.shot(page, "experiment_bundle_390.png")
        return detail
    finally:
        page.close()


def check_loading(s: Session) -> dict[str, Any]:
    """Hold the bundle request open and read the page while it waits."""
    held: list[Any] = []
    page = s.desktop.new_page()
    try:
        page.route(f"**/data/{BUNDLE_PARAM}", lambda route: held.append(route))
        page.goto(s.url, wait_until="domcontentloaded")
        page.wait_for_function("() => document.body.dataset.expState === 'loading'", timeout=10_000)
        for _ in range(200):
            if held:
                break
            page.wait_for_timeout(25)
        state = page_state(page)
        assert held and state["box_visible"] and state["label"] == "Loading", f"loading state: {state}"
        assert not state["results_visible"] and state["family_sections"] == 0, "results show while loading"
        s.note_state(state)
        held[0].continue_()
        page.wait_for_function("() => document.body.dataset.expState === 'ready'", timeout=20_000)
        return {"role": state["box_role"]}
    finally:
        page.close()


def run_defect(recorder: Recorder, s: Session, name: str, break_it: Callable[[], None],
               detect: Callable[[], Mapping[str, Any]]) -> None:
    """Serve a deliberate defect, require its detection, restore the bundle and require a full pass again."""
    def action() -> dict[str, Any]:
        break_it()
        try:
            detail = dict(detect())
        finally:
            s.restore()
        s.restored_pass()
        return detail
    recorder.run(name, action, result="detected_then_restored_pass")


def detect_error_state(s: Session, expect_state: str, expect_label: str, needles: Sequence[str]) -> dict[str, Any]:
    """The page must show the named state, say why, and render no part of a bundle beside it."""
    page, log = s.open()
    try:
        state = page_state(page)
        assert state["state"] == expect_state and state["label"] == expect_label, f"state: {state}"
        joined = " | ".join(state["messages"])
        assert all(needle in joined for needle in needles), f"message reads {joined!r}"
        assert not state["results_visible"] and state["family_sections"] == 0 and state["method_rows"] == 0, (
            "part of a bundle is rendered beside the state box")
        assert not log.page_errors, f"the page threw: {log.page_errors}"
        s.note_state(state)
        return {"state": state["state"], "role": state["box_role"], "messages": state["messages"],
                "core_assertions_reject": rejected(lambda: s.core(page, log))}
    finally:
        page.close()


def stateless_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """A copy in which one method lost its state counts, one lost its payload records, and their family blocks
    lost their state fields. Nothing in it says ``completed`` for those methods any more."""
    doc = copy.deepcopy(dict(bundle))
    for item in doc["methods_not_run"]:
        if item["method"] == "j_lens":
            del item["states"]
    doc["provenance"]["payloads"] = [p for p in doc["provenance"]["payloads"] if p["method"] != "behavior_next_token"]
    for family in doc["comparisons"]:
        for entry in family["comparisons"]:
            del entry["readout"]["j_lens"]["states"]
            del entry["behavior"]["status"]
    return doc


STATELESS_BLOCKS = """() => ({
    lens: Array.from(document.querySelectorAll(
        '[data-kind="not-computed"][data-method="j_lens"] [data-col="state"]')).map((s) => s.textContent),
    behaviour: Array.from(document.querySelectorAll(
        '[data-kind="block-unrecorded"][data-method="behavior_next_token"]')).map((p) => p.innerText),
    behaviour_rows: document.querySelectorAll('tr[data-kind^="behavior"]').length,
})"""


def detect_state_not_recorded(s: Session) -> dict[str, Any]:
    page, _ = s.open()
    try:
        assert page_state(page)["state"] == "ready", "the page did not render the bundle"
        shown = method_rows(page)
        for method in ("j_lens", "behavior_next_token"):
            cell = shown[method]["state"]
            assert cell.startswith(NOT_RECORDED) and not any(state in cell for state in EXECUTION_STATES), (
                f"{method}: with no recorded state the cell reads {cell!r}")
        assert shown["jpp"]["state"].startswith("unavailable "), "an untouched method changed"
        blocks = page.evaluate(STATELESS_BLOCKS)
        assert blocks["lens"] and set(blocks["lens"]) == {NOT_RECORDED}, f"family blocks: {blocks['lens']}"
        assert blocks["behaviour"] and all(NOT_RECORDED in text for text in blocks["behaviour"]), (
            "a behaviour block with no status is not marked")
        assert blocks["behaviour_rows"] == 0, "values of a block with no recorded state are shown"
        return {"state_cells": {m: shown[m]["state"] for m in ("j_lens", "behavior_next_token")},
                "methods_assertion_rejects": rejected(lambda: assert_methods(page, s.protocol, s.bundle))}
    finally:
        page.close()


def detect_traversal_refused(s: Session) -> dict[str, Any]:
    """Each address would reach the served bundle if it were followed. The page must refuse it and request nothing."""
    cases = (("literal", page_url(s.base, raw_query="bundle=../data/experiment_preview/bundle.json")),
             ("encoded", page_url(s.base, "../data/experiment_preview/bundle.json")),
             ("two_parameters", page_url(s.base, raw_query=f"bundle={BUNDLE_PARAM}&bundle={BUNDLE_PARAM}")))
    seen = {}
    for label, url in cases:
        page, log = s.open(url)
        try:
            state = page_state(page)
            assert state["state"] == "refused" and state["label"] == "Refused", f"{label}: {state}"
            assert "No request was made." in " ".join(state["messages"]), f"{label}: {state['messages']}"
            assert log.requests == [url], f"{label}: requests were {log.requests}"
            assert not state["results_visible"] and state["method_rows"] == 0, f"{label}: results show"
            s.note_state(state)
            seen[label] = state["messages"][0]
        finally:
            page.close()
    return {"refusals": seen, "requests_beyond_the_page": 0}


def wrong_number_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """A copy with one wrong probability and one ICA score of the wrong sign."""
    doc = copy.deepcopy(dict(bundle))
    entry = doc["comparisons"][0]["comparisons"][0]
    target = entry["behavior"]["targets"][0]
    target["a"], target["difference_a_minus_b"] = 0.5, 0.5 - target["b"]
    component = entry["ica"]["layers"][0]["components"][0]
    component["score_a"] = -component["score_a"]
    return doc


def detect_wrong_numbers(s: Session) -> dict[str, Any]:
    page, _ = s.open()
    try:
        return {"behaviour_assertion_rejects": rejected(lambda: assert_behavior(page, s.behavior)),
                "ica_assertion_rejects": rejected(lambda: assert_ica(page, s.ica, s.basis_sha256))}
    finally:
        page.close()


LINK_STATE = """() => ({
    anchors: Array.from(document.querySelectorAll('#exp-links a')).map((a) => [a.getAttribute('href'), a.textContent]),
    verified: document.querySelectorAll('#exp-links [data-kind="link-record"][data-verified="true"]').length,
    unverified: Array.from(document.querySelectorAll(
        '#exp-links [data-kind="link-record"][data-verified="false"] [data-col="no-link"]')).map((p) => p.innerText),
    local: document.querySelectorAll('#exp-links [data-kind="link-record"] dl').length,
})"""


def check_link_records(s: Session) -> dict[str, Any]:
    """Records built by the engine's own link builder from its fixture registry, plus two forged ones.

    One link is expected: the verified, built record. The unverified alias, an alias record with a link string
    pasted in, and a verified record whose link is not an https URL must each show their reason and no link.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.experiments import neuronpedia
    registry = neuronpedia.validate_registry(json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8")))
    entries = {entry["verification"]["status"]: entry for entry in registry["entries"]
               if entry["representation_type"] == "ica_component"}
    verified = neuronpedia.link_or_fallback(entries["verified_exact"], 1, layer=1, record={"component": 1})
    alias = neuronpedia.link_or_fallback(entries["alias_unverified_checkpoint"], 1, layer=2)
    assert verified["link"] and alias["link"] is None, "the registry fixture no longer gives one of each"
    forged_status = dict(alias, link=verified["link"])
    forged_scheme = dict(verified, link="javascript:alert(1)")
    linked = copy.deepcopy(s.bundle)
    entry = linked["comparisons"][0]["comparisons"][0]
    entry["ica"]["layers"][0]["components"][1]["neuronpedia"] = verified
    entry["references"]["registry"] = {"status": "reference_only",
                                       "neuronpedia": [alias, forged_status, forged_scheme]}
    s.write(linked)
    try:
        page, log = s.open()
        try:
            assert_ready(page, log, s.base)
            found = page.evaluate(LINK_STATE)
            assert found["anchors"] == [[verified["link"], verified["link"]]], f"anchors: {found['anchors']}"
            assert found["verified"] == 1 and len(found["unverified"]) == 3 and found["local"] == 4, found
            assert alias["reason"] in found["unverified"][0], "the unverified record lacks its reason"
            assert all(text.startswith("No link. Reason: ") for text in found["unverified"]), found
            return {"links_shown": 1, "records_shown_with_reason_and_local_record": 3,
                    "source": "scripts.experiments.neuronpedia.link_or_fallback on the fixture registry"}
        finally:
            page.close()
    finally:
        s.restore()


def check_parameter_cases(s: Session) -> dict[str, Any]:
    """The page's rule and ``bundle_param_refusal`` give the same answer, with the same words, on every case."""
    refused = 0
    for value in PARAM_CASES:
        reason = bundle_param_refusal(value)
        url = page_url(s.base, value)
        page, log = s.open(url)
        try:
            state = page_state(page)
            direct = page.evaluate("(v) => window.pwExperimentViewer.bundleRefusal(v)", value)
            assert direct == reason, f"{value!r}: page rule says {direct!r}, mirror says {reason!r}"
            if reason is None:
                assert state["state"] != "refused", f"{value!r}: refused by the page"
                continue
            refused += 1
            assert state["state"] == "refused" and state["messages"][0] == reason, (
                f"{value!r}: page state {state['state']!r} {state['messages'][:1]}")
            assert log.requests == [url], f"{value!r}: a request was made"
        finally:
            page.close()
    return {"cases": len(PARAM_CASES), "refused": refused}


def check_distinct_states(s: Session) -> dict[str, Any]:
    wanted = {"idle", "loading", "ready", "missing", "error", "refused"}
    assert set(s.states) == wanted, f"states observed: {sorted(s.states)}"
    for name in ("label", "class"):
        values = [s.states[key][name] for key in sorted(s.states)]
        assert len(set(values)) == len(values), f"two states share a {name}: {values}"
    return {"states": {key: s.states[key] for key in sorted(s.states)}}


def run_browser_checks(s: Session, recorder: Recorder) -> None:
    recorder.run("no_parameter_shows_the_statement_and_requests_no_data", lambda: check_no_parameter(s))
    check_rendered_bundle(s, recorder)
    recorder.run("keyboard_reaches_section_links_and_folds", lambda: check_keyboard(s))
    recorder.run("family_folds_open_from_the_keyboard_and_keep_their_labels", lambda: check_family_folds(s))
    recorder.run("renders_at_390_px_without_horizontal_overflow", lambda: check_narrow(s))
    recorder.run("loading_state_is_shown_while_the_bundle_is_in_flight", lambda: check_loading(s))

    wrong_schema = dict(copy.deepcopy(s.bundle), schema_version="patientwords.experiment-bundle/2")
    run_defect(recorder, s, "defect_wrong_schema_string_gives_an_error_state_not_a_partial_render",
               lambda: s.write(wrong_schema),
               lambda: detect_error_state(s, "error", "Error", ["patientwords.experiment-bundle/2", BUNDLE_SCHEMA,
                                                                "Nothing is displayed."]))
    run_defect(recorder, s, "defect_missing_bundle_file_gives_a_missing_state_with_status",
               s.served.unlink,
               lambda: detect_error_state(s, "missing", "Missing", ["HTTP 404", f"data/{BUNDLE_PARAM}"]))
    run_defect(recorder, s, "defect_method_records_without_a_state_read_state_not_recorded_not_completed",
               lambda: s.write(stateless_bundle(s.bundle)), lambda: detect_state_not_recorded(s))
    run_defect(recorder, s, "defect_traversal_parameter_is_refused_without_a_request",
               lambda: None, lambda: detect_traversal_refused(s))
    run_defect(recorder, s, "control_a_wrong_probability_and_a_flipped_score_fail_the_value_checks",
               lambda: s.write(wrong_number_bundle(s.bundle)), lambda: detect_wrong_numbers(s))

    recorder.run("a_link_is_shown_only_for_a_verified_built_record", lambda: check_link_records(s))
    recorder.run("parameter_rule_matches_its_python_mirror", lambda: check_parameter_cases(s))
    recorder.run("loading_missing_error_refused_ready_and_idle_differ", lambda: check_distinct_states(s))


# ------------------------------------------------------------------------------------------ the run

def launch(playwright: Any, browser_path: str | None) -> Any:
    try:
        return playwright.chromium.launch(**({"executable_path": browser_path} if browser_path else {}),
                                          args=["--disable-background-networking"])
    except Exception as exc:
        raise SetupProblem("no Chromium could be started; this check is blocked, not passed: "
                           f"{str(exc).strip().splitlines()[0][:300]}") from exc


def new_context(browser: Any, origin: str, blocked: list[str], width: int, height: int) -> Any:
    """A browser context that can reach the test server and nothing else."""
    context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2,
                                  service_workers="block")

    def route_request(route: Any) -> None:
        url = urlsplit(route.request.url)
        if f"{url.scheme}://{url.netloc}" == origin:
            route.continue_()
        else:
            blocked.append(f"{url.scheme}://{url.netloc}")
            route.abort()
    context.route("**/*", route_request)
    return context


def run(site_source: Path, browser_path: str | None, shots: Path | None, receipt: dict[str, Any]) -> int:
    """Run every check; return the number that failed. Raises ``SetupProblem`` when the check cannot run."""
    try:
        import importlib.metadata

        from playwright.sync_api import sync_playwright
        receipt["versions"]["playwright"] = importlib.metadata.version("playwright")
    except ImportError as exc:
        raise SetupProblem("the playwright package is not importable; this check is blocked, not passed: "
                           f"{exc}") from exc

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    behavior = expected_behavior(protocol, json.loads(LOGITS.read_text(encoding="utf-8")))
    basis_sha256 = json.loads(ICA_INDEX.read_text(encoding="utf-8"))["basis_manifest_sha256"]
    recorder = Recorder(receipt)
    real_preview = site_source / "data" / "experiment_preview"
    blocked: list[str] = receipt["browser_external_requests"]

    with tempfile.TemporaryDirectory(prefix="pw-exp-preview-") as directory:
        temp = Path(directory).resolve()
        site, work = temp / "patientwords", temp / "experiment_work"
        work.mkdir()
        copy_site(site_source, site)
        bundle_file = build_bundle(work, receipt)
        validated = next(step for step in receipt["cli_steps"] if step["step"] == "validate")
        recorder.run("cli_synthetic_slice_with_interruption_and_resume", lambda: {"steps": len(receipt["cli_steps"])})

        served = site / "data" / BUNDLE_PARAM

        def cli_refuses_site_data() -> dict[str, Any]:
            refused = run_cli("bundle", "--run-dir", str(work / "runs"), "--out", str(served), expect=2)
            assert refused.get("code") == "protected_root" and not served.exists(), f"not refused: {refused}"
            return {"refusal_code": refused["code"]}
        recorder.run("cli_refuses_to_write_under_a_site_data_directory", cli_refuses_site_data)

        served.parent.mkdir(parents=True)
        shutil.copyfile(bundle_file, served)
        original = served.read_bytes()
        bundle = json.loads(original)
        receipt["bundle"] = {
            "sha256": sha256_bytes(original), "bytes": len(original), "schema_version": bundle.get("schema_version"),
            "served_as": f"TEMP_SITE/data/{BUNDLE_PARAM}",
            "written_by": "plain file copy of the command line's bundle; the command line refuses a path under a "
                          "data directory"}

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(temp)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = launch(playwright, browser_path)
                receipt["versions"]["chromium"] = browser.version
                session = Session(
                    base=origin + "/patientwords", served=served, original=original, bundle=bundle,
                    protocol=protocol, validated=validated, behavior=behavior, ica=expected_ica(protocol),
                    basis_sha256=basis_sha256, desktop=new_context(browser, origin, blocked, 1280, 900),
                    phone=new_context(browser, origin, blocked, 390, 844), receipt=receipt, shots=shots)
                run_browser_checks(session, recorder)

                def no_outside_request() -> dict[str, Any]:
                    assert not blocked, f"the page tried to reach {sorted(set(blocked))}"
                    return {"external_requests": 0}
                recorder.run("no_request_left_the_test_server", no_outside_request)
                session.desktop.close()
                session.phone.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=10)

    def real_site_untouched() -> dict[str, Any]:
        assert not real_preview.exists(), "the real site holds data/experiment_preview; a fixture must never be there"
        assert not temp.exists(), "the temporary tree was not removed"
        return {"cleanup": "temporary server stopped; copied site, run store and bundle removed"}
    recorder.run("real_site_untouched_and_temporary_tree_removed", real_site_untouched)
    return recorder.failed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", type=Path, required=True, help="the patientwords site checkout")
    parser.add_argument("--browser", help="an installed Chromium executable (default: CHROMIUM, then Playwright's own)")
    parser.add_argument("--receipt", type=Path, help="write the JSON receipt here")
    parser.add_argument("--shots", type=Path, help="write screenshots into this directory")
    args = parser.parse_args(argv)
    site = args.site.resolve()
    receipt_path = args.receipt.resolve() if args.receipt else None
    browser = args.browser or os.environ.get("CHROMIUM") or None

    def finish(receipt: dict[str, Any] | None, code: int, message: str) -> int:
        if receipt is not None and receipt_path is not None:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(message, file=sys.stderr if code else sys.stdout)
        return code

    if not (site / PAGE).is_file():
        return finish(None, EXIT_SETUP, f"setup problem: {site} has no {PAGE}; nothing was checked")
    receipt = new_receipt(site, receipt_path)
    if browser and not Path(browser).is_file():
        receipt["result"], receipt["blocked_by"] = "blocked", "the --browser path is not a file"
        return finish(receipt, EXIT_SETUP,
                      f"setup problem: no Chromium at {browser}; this check is blocked, not passed")
    try:
        failed = run(site, browser, args.shots.resolve() if args.shots else None, receipt)
    except SetupProblem as exc:
        receipt["result"], receipt["blocked_by"] = "blocked", str(exc).splitlines()[0][:400]
        return finish(receipt, EXIT_SETUP, f"setup problem: {exc}")
    except Exception as exc:  # the run stopped before every check could be filed
        receipt["result"] = "failed"
        first_line = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else ""
        receipt["failure"] = f"{type(exc).__name__}: {first_line}"
        return finish(receipt, EXIT_FAILED, f"experiment preview stopped: {receipt['failure']}")
    receipt["result"] = "failed" if failed else "passed"
    total = len(receipt["checks"])
    if failed:
        return finish(receipt, EXIT_FAILED, f"experiment preview: {failed} of {total} checks failed")
    return finish(receipt, EXIT_PASS, f"experiment preview: {total} checks passed ({EVIDENCE})")


if __name__ == "__main__":
    sys.exit(main())
