"""Preview one synthetic experiment bundle in the site's experiments page. No model, no measurement, no publication.

    python scripts/check_experiment_preview.py --site ../patientwords [--browser CHROMIUM] [--receipt FILE]
        [--shots DIR]
    python scripts/check_experiment_preview.py --site ../patientwords --serve [--port PORT]

The second form is the development route to the fixture: it builds the same temporary copy and the same
synthetic bundle, serves them on a loopback port, prints the address of the preview and waits. It runs no
check and needs no browser of its own. Ctrl-C stops the server and removes the copy. The fixture is never
written into the site, so this is the only way to see it in the page.

What the first form runs, in order:

1. The site checkout is copied to a temporary directory (``.git``, caches and ``modes/`` are left out; the page
   references nothing under ``modes/``).
2. The experiment command line (``python -m scripts.experiments.cli``) takes the synthetic fixture protocol
   through validate, plan, an interrupted run, a resumed run, collect, compare and bundle. The protocol it
   runs is a copy written in the temporary tree, with the prompt-text marker added to two of the three
   families (``TEXT_FAMILIES``) and the target-text marker to one of those two (``TARGET_FAMILIES``), so that
   one bundle shows three states: wording and target text exported, wording exported and target text not
   exported, and neither exported. Its outputs go to a work directory in the temporary tree. The
   command line refuses any path that has a ``data`` component, so the finished bundle is copied, as a plain
   file, into the COPY's ``data/experiment_preview/``. Nothing is written into the real site or into either
   checkout.
3. The copy is served over HTTP on an ephemeral loopback port under ``/patientwords/``, and Chromium opens the
   real page, ``experiments/index.html``, with its real JavaScript.
4. The rendered text is compared with values this script works out itself: the softmax of the fixture logits,
   and the hand-computed ICA scores of the toy basis. They are not read back from the bundle. The fields added
   to bundle version 1 on 2026-11-10 are compared the same way: prompt and token hashes, token counts and the
   exported prompt text with the protocol file, the ICA preprocessing mode with the protocol's method block,
   and the executed and reused counts with the summaries the command line printed in step 2. The position of
   every dot of the target-token probability plot is measured in the browser and compared with its value.
   The order of the page is checked too: in a loaded comparison the paired wording and its primary output
   come before the run status and before Methods & source, and hashes and schema strings are in neither.
5. The page with no address parameter is checked against the site's own ``data/experiments/index.json`` (it
   lists nothing today), then against an index the real writer (``scripts/export_experiment_index.py``) builds
   in the copy: the synthetic bundle is never listed; a copy of it relabelled as publishable, which exists
   only in the temporary tree, is listed and its link opens it.
6. Deliberate defects are served, each followed by a restored pass. One of them is a copy of the bundle
   without the 2026-11-10 additions, as a bundle written before them: the page must render it and say
   "not in this bundle" in each place.
7. Link records are written into copies of the bundle and served: exact links and reference links built by
   ``scripts/experiments/neuronpedia.py`` from its fixture registry, one reference link built from the
   committed registry, and forged reference records. No link is followed; a request to any origin but the
   test server is blocked and counted.
8. Display-state alterations are served and then restored. Each is a copy of the built bundle with one thing
   changed so that a state the fixture run cannot produce is on the page: a target that spans two tokens, each
   of the six run statuses, a zero probability beside a missing difference. The receipt names each as an
   alteration of a display state. None is a run and none is a defect of the page.

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
import signal
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
INDEX_FILE = "experiments/index.json"
INDEX_SCHEMA = "patientwords.experiment-index/1"
INDEX_WRITER = ROOT / "scripts" / "export_experiment_index.py"
INDEX_CONTRACT = ROOT / "scripts" / "experiment_index_contract.py"
INDEX_SCHEMA_FILE = ROOT / "scripts" / "contracts" / "experiment_index.v1.schema.json"
# Where the relabelled copy of the fixture bundle is served for the listing check. It exists only in the
# temporary copy of the site.
RELABELLED_PARAM = "experiments/relabelled_fixture.json"
# The marker scripts/experiments/bundle.py reads in a family's ``facts`` (a literal, not an import, so that a
# renamed marker fails here), and the fixture families this check marks. The third family stays unmarked.
PROMPT_TEXT_MARKER = "publication:prompt_text_approved"
TEXT_FAMILIES = ("fam-1", "fam-2")
# The second marker (bundle version 1 since 2026-11-11): the family's target text. The bundle writer honours it
# only together with the prompt-text marker, so the families that carry it are among TEXT_FAMILIES.
TARGET_TEXT_MARKER = "publication:target_text_approved"
TARGET_FAMILIES = ("fam-1",)
BUNDLE_SCHEMA = "patientwords.experiment-bundle/1"
RECEIPT_SCHEMA = "patientwords.experiment-preview-receipt/1"
EVIDENCE = "local synthetic software test only"
COPY_IGNORED = (".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules", ".DS_Store",
                "modes")
EXIT_PASS, EXIT_FAILED, EXIT_SETUP = 0, 1, 2

# Text the page prints. The checks compare rendered text, so these are the reader-visible strings.
SYNTHETIC_TEXT = "Synthetic fixture: not a measurement"
EMPTY_HEAD = "No experiment comparisons published yet"
EMPTY_ROUTES = ("../results/", "../methods.html")
# Reader-facing label -> the schema term it stands for. The page shows the label and keeps the term in its
# Methods & source section (and beside the value where the label names one field).
READER_LABELS = {
    "Compare methods": "method-comparison bundle",
    "Cases": "Case families",
    "Run status": "Execution state",
    "Analysis eligibility": "Analysis membership",
    "Study version": "analysis pin",
    "Methods & source": "Provenance",
}
SCHEMA_TERMS = ("evidence.analysis_memberships", "protocol.sha256", "execution.by_state", "protocol.families",
                "patientwords.experiment-bundle/1")
# Headings the page had before 2026-11-10. None may be a heading or a column head any more.
RETIRED_HEADINGS = ("Method-comparison bundles", "Case families", "Execution state", "Analysis membership",
                    "Analysis pin", "Provenance")
ENDPOINT_LABEL = "Target-token probability"
ENDPOINT_FIRST_TOKEN = "first encoded token"
# The names the page gives the wordings. The file's own variant names are in data attributes and, as code, in
# Methods & source. The third required variant is called ``normalized`` in the file; the engine documents no
# transformation for it, so the page names it neutrally and never prints that word as a label.
WORDING_LABELS = {"clinical": "Medical wording", "colloquial": "Everyday wording", "normalized": "Rewritten wording",
                  "within_register_paraphrase": "Same-register paraphrase",
                  "changed_fact_control": "Changed-fact control"}
NEVER_A_LABEL = "normalized"
# What the page prints about a target. Its text is shown only when the bundle exports it.
TARGET_TEXT_ABSENT = "its text is not exported in this bundle"
FIRST_TOKEN = "first token of the target"
NOT_THE_WHOLE_WORD = "It is not the probability of the whole word."
NO_INTERVAL = "No interval: the bundle records one value per wording and computed no uncertainty."
SUBTRACTION_HEAD = "first wording minus second"
OUTPUT_QUESTION = "How does the probability of the target differ between the wordings?"
# The order of one case, as its headings read.
CASE_HEADINGS = ["Paired wording", OUTPUT_QUESTION, "Internal measurements", "Intervention evidence"]
# The section links of a loaded comparison, in order.
SECTION_LINKS = ["#families", "#methods", "#provenance", "#limitations"]
MIN_TEXT_PX = 12
# Colour. The two wordings keep their identity colours (the engine's figures use them) and are always named
# beside the mark. A value, a difference and a run status are in ink. The page keeps one alert colour for a
# file that failed to load and a refused address; a rendered comparison shows it nowhere.
WORDING_COLOURS = {"clinical": "rgb(21, 128, 61)", "colloquial": "rgb(17, 24, 39)"}
ALERT_COLOUR = "rgb(180, 72, 61)"
MUTED_COLOUR = "rgb(109, 108, 102)"
# What the endpoint must never be called in a heading, a column head or a label.
FORBIDDEN_IN_LABELS = ("accuracy", "risk", "understanding", "combined", "composite", "overall")
SCORE_LABEL = "signed component score"
OPEN_ALL, CLOSE_ALL = "Open every case", "Close every case"
CONFLICT = "two comparison blocks record different values"
# Section and control ids that links and scripts/check_pages.py rely on. All must stay on the page.
STABLE_IDS = ("main", "exp-idle", "exp-state", "exp-results", "evidence", "protocol", "families", "methods",
              "totals", "links", "provenance", "limitations", "exp-evidence", "exp-protocol", "exp-families",
              "exp-methods-body", "exp-totals", "exp-links", "exp-provenance", "exp-limitations", "exp-fam-toggle",
              "exp-index-list", "exp-fixture", "exp-capability-body", "exp-state-key")
NOT_RECORDED = "state not recorded"
WINDOW_MISS = "not observed in the top-k window"
NO_INTERVENTION = "no intervention in this bundle"
# What the page prints where a bundle does not carry a value it has a place for.
MISS = "\u2014 "
NOT_IN_BUNDLE = "not in this bundle"
PROMPT_TEXT_ABSENT = MISS + "prompt text is " + NOT_IN_BUNDLE
EXECUTED_ABSENT = MISS + "executed count is " + NOT_IN_BUNDLE
REUSED_ABSENT = MISS + "reuse count is " + NOT_IN_BUNDLE
SHARE_LABEL = "squared-coordinate share, not a probability"
SHARE_UNDEFINED = "\u2014 not computed: zero or non-finite energy"
# Reference links: what the page prints beside one, and the reasons it gives for not showing one. The fixed
# label sentence is not copied here; the checks read it from scripts/experiments/neuronpedia.py.
REFERENCE_TAG = "Reference only \u00b7 external service \u00b7 not a link to the study's model, feature or representation"
REFERENCE_LINK_TEXT = "Reference page on Neuronpedia (external service)"
REFERENCE_HOST = "www.neuronpedia.org"
REFERENCE_PAGE_WORDS = {"model_page": "model page", "source_page": "source page of one layer", "lens_page": "lens page"}
NO_LINK_PREFIX = "No link. Reason: "
REFUSED_KIND = 'the record kind is not "reference"'
REFUSED_RESULT_KIND = 'the record does not say its kind is "reference"'
REFUSED_NO_LABEL = "the record has no label"
REFUSED_LABEL = "the label is not the fixed reference sentence"
REFUSED_ADDRESS = "the address is not an https address without a query string or a fragment"
REFUSED_HOST = "the host is not " + REFERENCE_HOST
REFUSED_PAGE = "the page form is not a model, source or lens page"
REFUSED_PATH = "the address does not have the path of a "
REFUSED_REASON = "the record does not say the link was built from a recorded page form"
REFUSED_DATE = "the record has no date read"
REFUSED_STATUS = "the record has no identity status"
REFUSED_BOTH = "a record holds a verified link or a reference, never both"
REFUSED_BARE = "the reference record is not shown as a link: "
REFERENCE_REFUSALS = (REFUSED_KIND, REFUSED_RESULT_KIND, REFUSED_NO_LABEL, REFUSED_LABEL, REFUSED_ADDRESS,
                      REFUSED_HOST, REFUSED_PAGE, REFUSED_PATH, REFUSED_REASON, REFUSED_DATE, REFUSED_STATUS,
                      REFUSED_BOTH, REFUSED_BARE)
# Words the visible text of a reference link must not use: it is never presented as a verified link or as a
# link to something of the study.
NOT_IN_REFERENCE_LINK_TEXT = ("verified", "study", "feature", "representation", "exact")
# How the page has rendered a verified link and a record with no link since before reference links existed:
# the element children of the record's box, and the link's attributes. Literals, so that a change is seen.
RECORD_BOX_CHILDREN = ["P.plain", "P.plain", "DL.kv"]
EXACT_LINK_PREFIX = "Verified link: "
EXACT_LINK_REL = "noopener noreferrer external"
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


# ------------------------------------------------------------------------------------------ added bundle fields

def marked_protocol(protocol: Mapping[str, Any], families: Sequence[str] = TEXT_FAMILIES,
                    target_families: Sequence[str] = TARGET_FAMILIES) -> dict[str, Any]:
    """A copy of ``protocol`` with the prompt-text marker in the ``facts`` of ``families`` and the target-text
    marker in the ``facts`` of ``target_families``. The markers are part of the protocol, so the copy has
    another protocol hash and is a different run. Raises ``ValueError`` when a named family is absent, or when
    a family is to carry the target marker without the prompt marker: the bundle writer refuses that."""
    doc = copy.deepcopy(dict(protocol))
    known = {family["family_id"] for family in doc["case_families"]}
    if not set(families) | set(target_families) <= known:
        raise ValueError(f"the fixture protocol has no family {sorted((set(families) | set(target_families)) - known)}")
    if not set(target_families) <= set(families):
        raise ValueError("a family carries the target-text marker without the prompt-text marker: "
                         f"{sorted(set(target_families) - set(families))}")
    for family in doc["case_families"]:
        for marker, named in ((PROMPT_TEXT_MARKER, families), (TARGET_TEXT_MARKER, target_families)):
            if family["family_id"] in named and marker not in family["facts"]:
                family["facts"].append(marker)
    return doc


def wording_label(name: str) -> str:
    """The name the page prints for a wording of the fixture. ``KeyError`` for a name the page does not know."""
    return WORDING_LABELS[name]


def expected_target_text(protocol: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any] | None]:
    """``{(family, target id): {"text", "n_tokens", "partial"} or None}``: the target text the page must show
    for a family that carries both markers, and None where the bundle may hold no target text. Read from the
    protocol, not from the bundle. ``partial`` is true when the target spans more than one token."""
    out: dict[tuple[str, str], dict[str, Any] | None] = {}
    for family in protocol["case_families"]:
        marked = PROMPT_TEXT_MARKER in family["facts"] and TARGET_TEXT_MARKER in family["facts"]
        for target in family["targets"]:
            tokens = len(target["token_ids"])
            out[(family["family_id"], target["id"])] = (
                {"text": target["text"], "n_tokens": tokens, "partial": tokens > 1} if marked else None)
    return out


def with_partial_target(bundle: Mapping[str, Any], family_id: str, target_id: str) -> dict[str, Any]:
    """A copy of ``bundle`` in which one exported target says it spans two tokens (``n_tokens`` 2,
    ``partial_token_endpoint`` true). The fixture backend's targets are single tokens, so this display state
    cannot come from a fixture run; the copy is an alteration of a display state, not a run. Raises
    ``ValueError`` when the bundle exports no text for that target."""
    doc = copy.deepcopy(dict(bundle))
    family = next((f for f in doc["protocol"]["families"] if f["family_id"] == family_id), None)
    if family is None or target_id not in family.get("target_text", {}):
        raise ValueError(f"the bundle exports no target text for {family_id} {target_id}")
    family["target_text"][target_id].update({"n_tokens": 2, "partial_token_endpoint": True})
    return doc


def expected_prompt_text(protocol: Mapping[str, Any]) -> dict[tuple[str, str], str | None]:
    """``{(family, variant): text or None}``: the prompt text the page must show for a variant of a marked
    family, and None where the bundle may hold no text. Read from the protocol, not from the bundle."""
    return {(family["family_id"], name): (entry["prompt"] if PROMPT_TEXT_MARKER in family["facts"] else None)
            for family in protocol["case_families"] for name, entry in family["variants"].items()}


def relabelled_as_publishable(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of a fixture bundle whose labels say it may be published: not synthetic, visibility ``public``,
    no restriction reason. It is still hand-written fixture numbers. It exists so that the listing path of the
    index writer and of the page can be exercised, and it is written only into a temporary tree.

    Exported prompt text is removed: text exported under the synthetic rule was never asked of the holdout
    seal, so a copy that claims to be publishable must not carry it."""
    doc = copy.deepcopy(dict(bundle))
    doc["protocol"]["synthetic"] = False
    doc["evidence"].update({"synthetic": False, "evidence_class": "unclassified",
                            "clinical_review": "domain_review_pending", "visibility": "public",
                            "restriction_reasons": [], "analysis_memberships": []})
    doc["limitations"] = [code for code in doc["limitations"] if not code.startswith(("synthetic_", "no_real_model",
                                                                                      "fixture_timings"))]
    for family in doc["protocol"]["families"]:
        for key in ("variant_text", "prompt_text_export", "target_text", "target_text_export"):
            family.pop(key, None)
    return doc


def expected_variant_inputs(protocol: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    """``{(family, variant): {prompt_sha256, token_sha256, n_tokens}}`` as the page must print them, read from
    the fixture protocol file. Hashes and a count; the prompt text itself is never expected on the page."""
    out: dict[tuple[str, str], dict[str, str]] = {}
    for family in protocol["case_families"]:
        for name, entry in family["variants"].items():
            out[(family["family_id"], name)] = {"prompt_sha256": entry["prompt_sha256"],
                                                "token_sha256": entry["token_sha256"],
                                                "n_tokens": str(len(entry["token_ids"]))}
    return out


def expected_preprocessing(protocol: Mapping[str, Any]) -> str:
    """The preprocessing mode the fixture protocol's ICA method block declares. The ICA adapter completes a
    task only when the mode its payload records equals this one, so it is what a completed block must show."""
    blocks = [method for method in protocol["methods"] if method["id"] == "ica_lens"]
    if len(blocks) != 1 or not isinstance(blocks[0].get("basis", {}).get("preprocessing"), str):
        raise ValueError("the fixture protocol does not declare one ica_lens basis with a preprocessing mode")
    return blocks[0]["basis"]["preprocessing"]


def expected_journal_counts(cli_steps: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Executed attempts and reuse events, summed over the ``run-fixture`` summaries the command line printed.
    Not read from the bundle."""
    runs = [step for step in cli_steps if str(step.get("step", "")).startswith("run-fixture")]
    if not runs:
        raise ValueError("no run-fixture step was recorded")
    return {"executed": sum(step["executed"] for step in runs), "reused": sum(step["reused"] for step in runs)}


def without_added_fields(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of ``bundle`` as it was written before 2026-11-10: no ``variant_inputs``, no exported prompt text
    (``variant_text``, ``prompt_text_export``), no exported target text (``target_text``,
    ``target_text_export``, added 2026-11-11), no ICA preprocessing fields, no ``vocabulary_size`` in a
    behaviour block, no executed or reused count. It must still be a valid version 1 bundle and the page must
    render it. Raises ``ValueError`` when the bundle carries none of them, so that the check cannot pass on a
    bundle that never had the fields."""
    doc = copy.deepcopy(dict(bundle))
    removed = 0
    for family in doc["protocol"]["families"]:
        removed += family.pop("variant_inputs", None) is not None
        removed += family.pop("variant_text", None) is not None
        family.pop("prompt_text_export", None)
        family.pop("target_text", None)          # added on 2026-11-11; an older bundle has neither
        family.pop("target_text_export", None)
    for family in doc["comparisons"]:
        for entry in family["comparisons"]:
            block = entry.get("ica")
            if isinstance(block, dict):
                removed += block.pop("preprocessing_mode", None) is not None
                block.pop("preprocessing_read_from", None)
            if isinstance(entry.get("behavior"), dict):
                removed += entry["behavior"].pop("vocabulary_size", None) is not None
    for key in ("executed_attempts", "reused_events"):
        removed += doc["execution"]["counts"].pop(key, None) is not None
    if not removed:
        raise ValueError("the bundle carries none of the fields added on 2026-11-10")
    return doc


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
    """The sign in words, as the page prints it beside a signed difference: the page's name of the wording
    whose value is higher. ``a_name`` and ``b_name`` are the file's variant names. A non-zero value too small
    for the four printed decimals keeps its sign and says that it is below them."""
    if value == 0:
        return "no difference"
    higher = wording_label(a_name if value > 0 else b_name)
    return f"{higher} higher" + (BELOW_DISPLAY if abs(value) < DISPLAY_STEP else "")


def pair_label(a_name: str, b_name: str) -> str:
    """How the page names a difference: the first wording, a minus sign, the second. The value beside it is
    the bundle's ``a`` minus ``b``; the page does not change its sign."""
    return f"{wording_label(a_name)} {MINUS} {wording_label(b_name)}"


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
             INDEX_WRITER, INDEX_CONTRACT, INDEX_SCHEMA_FILE,
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
        "protocol_run": f"tests/fixtures/experiments/{PROTOCOL.name} with {PROMPT_TEXT_MARKER!r} added to the facts "
                        f"of {list(TEXT_FAMILIES)} and {TARGET_TEXT_MARKER!r} to the facts of "
                        f"{list(TARGET_FAMILIES)}, written in the temporary tree",
        "display_state_alterations": [],
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


def build_bundle(work: Path, receipt: dict[str, Any], protocol: Mapping[str, Any] | None = None) -> Path:
    """Run the synthetic slice through the real command line, with one interruption and a resume.

    ``protocol`` is the protocol document to run; the default is the fixture protocol with the prompt-text
    marker on ``TEXT_FAMILIES``. It is written into ``work`` and every step names that file, so the bundle
    step can export the marked families' placeholder text. Returns the bundle path inside ``work``. Each
    step's summary goes into ``receipt['cli_steps']``.
    """
    steps = receipt["cli_steps"]
    plan, runs, bundle = work / "plan.json", work / "runs", work / "bundle.json"
    source = work / "protocol_marked.json"
    document = protocol if protocol is not None else marked_protocol(json.loads(PROTOCOL.read_text(encoding="utf-8")))
    source.write_text(json.dumps(document), encoding="utf-8")
    validated = run_cli("validate", "--protocol", str(source))
    steps.append({"step": "validate", "status": validated.get("status"), "synthetic": validated.get("synthetic"),
                  "protocol_sha256": validated.get("protocol_sha256")})
    planned = run_cli("plan", "--protocol", str(source), "--out", str(plan))
    steps.append({"step": "plan", "tasks": planned["totals"]["tasks"],
                  "by_planned_state": planned["totals"]["by_planned_state"]})
    run = ("run-fixture", "--plan", str(plan), "--fixtures", str(FIXTURES), "--protocol", str(source),
           "--run-dir", str(runs))
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
    bundled = run_cli("bundle", "--run-dir", str(runs), "--out", str(bundle), "--protocol", str(source))
    steps.append({"step": "bundle --protocol", "schema_version": bundled["schema_version"],
                  "by_state": bundled["by_state"], "prompt_text_families": bundled["prompt_text_families"]})
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
    """Open every case fold with the page's own button, from the keyboard, then every smaller fold (hashes,
    protocol details, estimates), so that the text of every row can be read. Returns how many cases were
    closed. The smaller folds are opened by script here; ``assert_keyboard`` opens one from the keyboard."""
    closed = "() => document.querySelectorAll('#exp-families details.fam-fold:not([open])').length"
    before = page.evaluate(closed)
    if before:
        page.focus("#exp-fam-toggle")
        page.keyboard.press("Enter")
        assert page.evaluate(closed) == 0, "the case button did not open every case"
    page.evaluate("() => document.querySelectorAll('#exp-results details').forEach((d) => { d.open = true; })")
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
            links: Array.from(box.querySelectorAll('a')).map((a) => [a.getAttribute('href'), a.textContent,
                                                                     a.hasAttribute('download')]),
            idle_visible: visible(document.getElementById('exp-idle')),
            index: document.body.dataset.expIndex || null,
            empty_visible: visible(document.getElementById('exp-empty')),
            index_visible: visible(document.getElementById('exp-index')),
            results_visible: visible(document.getElementById('exp-results')),
            family_sections: document.querySelectorAll('#exp-families section').length,
            method_rows: document.querySelectorAll('#exp-methods-body tr').length,
        };
    }""")


def table_rows(page: Any) -> dict[str, list[dict[str, Any]]]:
    """Every data row of the rendered bundle as ``{kind: [{attrs, cells}]}``, with the text a reader sees.

    A row is a table row, a row of the dot plot or a row of the paired wording. A cell that belongs to one
    wording inside a row (the ICA table has one score cell and one share cell per wording) is keyed
    ``<column>@<wording>``."""
    rows = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#exp-results tr[data-kind], #exp-results [role="row"][data-kind]')).map((tr) => ({
        kind: tr.dataset.kind,
        attrs: Object.assign({}, tr.dataset),
        cells: Object.fromEntries(Array.from(tr.querySelectorAll('[data-col]')).map(
            (td) => [td.dataset.col + (td.dataset.variant ? '@' + td.dataset.variant : ''), td.innerText.trim()])),
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


BANNERS = """() => {
    const fixture = document.getElementById('exp-fixture');
    const inView = (node) => {
        const r = node.getBoundingClientRect();
        return r.height > 0 && r.top >= 0 && r.bottom <= window.innerHeight;
    };
    const start = window.scrollY;
    const stops = Array.from(document.querySelectorAll('#exp-families section.fam, #methods, #provenance, #limitations'));
    const kept = stops.map((node) => { node.scrollIntoView(); return [node.id || node.dataset.family, inView(fixture)]; });
    window.scrollTo(0, start);
    return {
        position: getComputedStyle(fixture).position,
        hidden: fixture.hidden,
        text: fixture.innerText.trim(),
        kept,
        banners: Array.from(document.querySelectorAll('[data-kind="synthetic-banner"]')).map((p) => ({
            text: p.firstChild ? p.firstChild.textContent : '',
            visible: p.getClientRects().length > 0,
            in_family: p.closest('section.fam') ? p.closest('section.fam').dataset.family : null,
            in_case_line: !!p.closest('summary [data-col="case-labels"]'),
            in_fixture: !!p.closest('#exp-fixture'),
            weight: parseInt(getComputedStyle(p).fontWeight, 10),
        })),
    };
}"""


def assert_banner(page: Any, families: int) -> dict[str, Any]:
    """The synthetic label of a synthetic bundle. One line carries it above everything the bundle shows and
    stays in view while the page scrolls: the check scrolls to every case, to the run status, to Methods &
    source and to the limitations, and the line must be inside the window each time. The heading line of every
    case carries the same words, so a case that is read or captured alone is still labelled."""
    found = page.evaluate(BANNERS)
    banners = found["banners"]
    assert banners and all(b["text"] == SYNTHETIC_TEXT and b["visible"] for b in banners), f"label text: {banners}"
    assert all(b["weight"] >= 600 for b in banners), "the synthetic label is not set in a bold weight"
    assert sum(1 for b in banners if b["in_fixture"]) == 1 and not found["hidden"], (
        "the line above the results does not carry the synthetic label once")
    assert found["position"] == "sticky", f"the label line is positioned {found['position']!r}; it does not stay in view"
    lost = [name for name, kept in found["kept"] if not kept]
    assert len(found["kept"]) == families + 3 and not lost, f"the synthetic label leaves the view at {lost}"
    in_cases = [b for b in banners if b["in_family"]]
    assert len(in_cases) == families == len({b["in_family"] for b in in_cases}) and all(
        b["in_case_line"] for b in in_cases), "a case does not carry the synthetic label in its heading line"
    assert len(banners) == families + 1, f"{len(banners)} synthetic labels on the page, {families + 1} expected"
    evidence = page.locator('#exp-evidence [data-col="evidence_class"]').inner_text().strip()
    assert evidence == "synthetic_fixture", f"evidence class shown is {evidence!r}"
    return {"labels": len(banners), "stays_in_view_at": [name for name, _kept in found["kept"]]}


DIFF_HEADS = """() => Array.from(document.querySelectorAll('#exp-results [data-kind="dotplot"]')).map((panel) => {
    const table = panel.querySelector('tr[data-kind="behavior-diff"]');
    return table ? Array.from(table.closest('table').querySelectorAll('th')).map((th) => th.innerText.trim()) : null;
})"""


def assert_behavior(page: Any, expected: Mapping[str, Any]) -> dict[str, Any]:
    rows = table_rows(page)
    shown = keyed(rows.get("behavior-variant", []), "family", "variant", "target")
    assert set(shown) == set(expected["variants"]), "the per-variant behaviour rows do not match the fixture's set"
    for key, value in expected["variants"].items():
        assert shown[key]["probability"] == fmt_plain(value), (
            f"{key}: page shows {shown[key]['probability']!r}, the fixture logits give {fmt_plain(value)!r}")
        assert 0.0 <= value <= 1.0 and shown[key]["variant"] == wording_label(key[1]), (
            f"{key}: the row is named {shown[key]['variant']!r}")
    by_wording = shown
    order = {(row["attrs"]["family"], row["attrs"]["comparison"], row["attrs"]["target"]):
             (row["attrs"].get("a"), row["attrs"].get("b")) for row in rows.get("behavior-diff", [])}
    shown = keyed(rows.get("behavior-diff", []), "family", "comparison", "target")
    assert set(shown) == set(expected["differences"]), "the difference rows do not match the fixture's set"
    zeros, rounding = 0, []
    for key, want in expected["differences"].items():
        cells = shown[key]
        # The subtraction order. The row is named by its two wordings, first minus second, and the value beside
        # it is the fixture's a minus b with its sign: the page neither swaps the wordings nor changes the sign.
        assert order[key] == (want["a_name"], want["b_name"]), f"{key}: the row records the order {order[key]}"
        assert cells["comparison"] == pair_label(want["a_name"], want["b_name"]), (
            f"{key}: the difference is named {cells['comparison']!r}, not "
            f"{pair_label(want['a_name'], want['b_name'])!r}")
        # Each value is printed once, in the row of its wording. The two rows the difference names must show
        # the values the fixture logits give for a and b.
        sides = tuple(by_wording[(key[0], want[name], key[2])]["probability"] for name in ("a_name", "b_name"))
        assert sides == (fmt_plain(want["a"]), fmt_plain(want["b"])), (
            f"{key}: the rows of its two wordings show {sides}; the fixture logits give "
            f"{fmt_plain(want['a'])!r}, {fmt_plain(want['b'])!r}")
        assert "a" not in cells and "b" not in cells, f"{key}: a value is repeated in the difference row"
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
            assert got[1] == f"{wording_label(higher)} higher{BELOW_DISPLAY}", f"{key}: the sign text reads {got[1]!r}"
            rounding.append({"row": " / ".join(key), "difference_shown": got[0], "sign_shown": got[1]})
    assert zeros > 0, "no exact zero difference is shown as 0 with 'no difference'; the valid-zero state is unchecked"
    heads = page.evaluate(DIFF_HEADS)
    assert heads and all(head and SUBTRACTION_HEAD in head[0] and head[1].startswith("In probability")
                         for head in heads), f"a difference table does not state its order and unit: {heads[:1]}"
    return {"variant_values": len(expected["variants"]), "differences": len(expected["differences"]),
            "subtraction_order": "first wording minus second, the bundle's a minus b, sign unchanged",
            "unit": "probability, 0 to 1",
            "zero_differences_shown_as_0_no_difference": zeros,
            "exact_ties_the_bundle_records_as_float_rounding": rounding}


def assert_ica(page: Any, expected: Mapping[tuple[str, str, int], Mapping[str, Any]],
               basis_sha256: str) -> dict[str, Any]:
    rows = table_rows(page)
    shown = {(f, c, int(k)): cells for (f, c, k), cells in
             keyed(rows.get("ica", []), "family", "comparison", "component").items()}
    assert set(shown) == set(expected), "the ICA difference rows do not match the hand-computed set"
    # A signed score and a share are printed once per wording, in the row of their layer and component.
    by_wording = {(f, int(k)): cells for (f, layer, k), cells in
                  keyed(rows.get("ica-wording", []), "family", "layer", "component").items()
                  if layer == str(ICA_LAYER)}
    assert set(by_wording) == {(f, k) for f, _c, k in expected}, "the per-wording ICA rows are not the fixture's"
    undefined, wordings = 0, set()
    for key, want in expected.items():
        cells, mine = shown[key], by_wording[(key[0], key[2])]
        share = [SHARE_UNDEFINED if want[name] is None else fmt_plain(want[name]) for name in ("share_a", "share_b")]
        undefined += sum(1 for name in ("share_a", "share_b") if want[name] is None)
        wordings |= {want["a_name"], want["b_name"]}
        got = (cells["layer"], mine[f"score@{want['a_name']}"], mine[f"score@{want['b_name']}"],
               cells["difference"], cells["sign"], mine[f"share@{want['a_name']}"], mine[f"share@{want['b_name']}"])
        wanted = (str(ICA_LAYER), fmt_signed(want["score_a"]), fmt_signed(want["score_b"]),
                  fmt_signed(want["difference"]), sign_text(want["difference"], want["a_name"], want["b_name"]),
                  share[0], share[1])
        assert got == wanted, f"{key}: page shows {got}, the hand-computed values are {wanted}"
        assert not any(name.startswith(("score", "share")) for name in cells), (
            f"{key}: a per-wording value is repeated in the difference row")
    blocks = page.evaluate("""() => Array.from(document.querySelectorAll('[data-kind="ica-block"]')).map((d) => ({
        basis: d.querySelector('dd[data-col="ica_basis"]').innerText.trim(),
        label: d.querySelector('dd[data-col="ica_share_label"]').innerText.trim(),
        preprocessing: d.querySelector('dd[data-col="ica_preprocessing"]').innerText.trim(),
        heads: Array.from(d.querySelector('tr[data-kind="ica-wording"]').closest('table').querySelectorAll('th'))
            .map((th) => th.textContent),
        narrow: Array.from(d.querySelectorAll('tr[data-kind="ica-wording"] td[data-variant]')).map(
            (td) => [td.dataset.col, td.dataset.l]),
    }))""")
    assert blocks and all(b["basis"] == basis_sha256 for b in blocks), "the basis hash shown is not the fixture's"
    for block in blocks:
        share_heads = [h for h in block["heads"] if SHARE_LABEL in h]
        score_heads = [h for h in block["heads"] if SCORE_LABEL in h]
        assert block["label"] == SHARE_LABEL and len(share_heads) == len(wordings), (
            "a share column is not labelled as a squared-coordinate share that is not a probability")
        assert len(score_heads) == len(wordings) and not set(share_heads) & set(score_heads), (
            "a signed-score column is not labelled as a signed component score, or one head carries both labels")
        # The label the narrow layout prints beside each value keeps the same distinction.
        assert all(("signed score" in label) == (col == "score") and ("squared-coordinate share" in label) == (
            col == "share") for col, label in block["narrow"]), f"narrow-layout labels: {block['narrow'][:2]}"
    assert undefined > 0, "the fixture no longer holds a zero score vector; the undefined-share state is unchecked"
    return {"component_rows": len(expected), "per_wording_rows": len(by_wording), "wordings": sorted(wordings),
            "undefined_shares_shown_as_not_computed": undefined,
            "preprocessing_shown": sorted({b["preprocessing"] for b in blocks})}


def assert_readout(page: Any, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Rendering fidelity only: the ranks on the page are the bundle's ranks. No independent oracle is used.

    The page prints one row per wording, layer and target. Every side of every comparison block of the bundle
    must equal the row of its wording, so a wording that sits in two comparisons is compared twice."""
    shown = keyed(table_rows(page).get("readout", []), "family", "method", "variant", "layer", "target")
    expected: dict[tuple[str, ...], dict[str, str]] = {}
    misses = sides = 0
    for family in bundle["comparisons"]:
        for entry in family["comparisons"]:
            for method, block in entry["readout"].items():
                if block.get("status") != "computed":
                    continue
                for layer in block["layers"]:
                    for target in layer["targets"]:
                        for side in ("a", "b"):
                            cells = {"raw": str(target[side]["raw_rank"]),
                                     "filtered": str(target[side]["filtered_rank"])}
                            seen = [f"top-{k}" for k in sorted(target[side]["top_k"], key=int)
                                    if target[side]["top_k"][k] == "observed"]
                            missed = [f"top-{k}" for k in sorted(target[side]["top_k"], key=int)
                                      if target[side]["top_k"][k] == "not_observed_in_window"]
                            assert len(seen) + len(missed) == len(target[side]["top_k"]), "an unknown window value"
                            window = (["observed in " + ", ".join(seen)] if seen else []) + (
                                [f"{WINDOW_MISS}: " + ", ".join(missed)] if missed else [])
                            cells["window"] = "\n".join(window)
                            key = (family["family_id"], method, entry[side], str(layer["layer"]),
                                   target["target_id"])
                            assert expected.setdefault(key, cells) == cells, (
                                f"{key}: two comparison blocks of the fixture bundle disagree")
                            sides += 1
                            misses += bool(missed) and expected[key] is cells
    assert expected and set(shown) == set(expected), "the readout rows do not match the bundle's computed blocks"
    for key, want in expected.items():
        got = {name: shown[key][name] for name in want}
        assert got == want, f"{key}: page shows {got}, the bundle holds {want}"
    order = page.evaluate("""() => Array.from(document.querySelector('tr[data-kind="readout"]').querySelectorAll(
        'td[data-col]')).map((td) => td.dataset.col)""")
    assert order.index("filtered") == order.index("raw") + 1, "raw and filtered rank are apart"
    assert misses > 0, "the fixture no longer holds a top-k miss; the miss wording is unchecked"
    return {"readout_rows": len(expected), "bundle_sides_compared": sides, "cells_wording_a_top_k_miss": misses,
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


def assert_not_computed_blocks(page: Any, families: int, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Each case states the run status of a method that was not computed, and where its reason is.

    The reason paragraph is printed once, in the Run status table. A case block points there with a link when
    its reason is the single reason that table holds for the method, and prints the reason itself otherwise.
    Either way the reason the bundle records must be readable: this check follows the link to the table row."""
    found = page.evaluate("""() => Array.from(document.querySelectorAll('[data-kind="not-computed"]')).map((p) => ({
        method: p.dataset.method, family: p.dataset.family, text: p.innerText,
        states: Array.from(p.querySelectorAll('[data-col="state"]')).map((s) => s.textContent),
        reason: p.querySelector('[data-col="reason"]') ? p.querySelector('[data-col="reason"]').dataset.reason : null,
        links: Array.from(p.querySelectorAll('a')).map((a) => a.getAttribute('href')),
    }))""")
    table = method_rows(page)
    reasons = {row["method"]: row["reasons"] for row in bundle["methods_not_run"]}
    linked = 0
    for method, state in EXPECTED_METHOD_STATE.items():
        if state == "completed":
            continue
        mine = [b for b in found if b["method"] == method]
        assert len({b["family"] for b in mine}) == families, f"{method}: not shown as not computed in every case"
        assert all(b["states"] == [state] and "Reason: " in b["text"] for b in mine), (
            f"{method}: a case block does not state {state} with its reason")
        for block in mine:
            if block["reason"] == "in-run-status":
                assert block["links"] == ["#methods"], f"{method}: the reason link goes to {block['links']}"
                assert len(reasons[method]) == 1 and reasons[method][0] in table[method]["reason"], (
                    f"{method}: the Run status row the case points to does not carry the bundle's reason")
                linked += 1
            else:
                assert block["reason"] == "inline" and any(r in block["text"] for r in reasons[method]), (
                    f"{method}: a case block neither prints its reason nor points to it")
    assert page.evaluate("() => !!document.querySelector('#methods #exp-methods-body')"), "the link target is absent"
    return {"not_computed_blocks": len(found), "reasons_read_from_the_run_status_table": linked}


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
    assert reused.isdigit(), f"the reuse count reads {reused!r}"
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


ADDED_FIELDS = """() => ({
    executed: document.querySelector('#exp-totals dd[data-col="executed"]').innerText.trim(),
    reused: document.querySelector('#exp-totals dd[data-col="reused"]').innerText.trim(),
    preprocessing: Array.from(document.querySelectorAll(
        '[data-kind="ica-block"] dd[data-col="ica_preprocessing"]')).map((d) => d.innerText.trim()),
    preprocessing_source: Array.from(document.querySelectorAll(
        '[data-kind="ica-block"] dd[data-col="ica_preprocessing_source"]')).map((d) => d.innerText.trim()),
    text: document.querySelector('main').innerText,
})"""


def shown_added_fields(page: Any) -> dict[str, Any]:
    """What the page prints for the fields added to bundle version 1 on 2026-11-10."""
    shown = page.evaluate(ADDED_FIELDS)
    rows = table_rows(page)
    # Hashes and the token count are in the input-identity table; the prompt text, or the statement that the
    # bundle holds none, is in the paired-wording row of the same family and variant.
    wording = keyed(rows.get("wording", []), "family", "variant")
    shown["variants"] = {key: {**{name: cells.get(name) for name in ("prompt_sha256", "token_sha256", "n_tokens")},
                               "prompt": wording.get(key, {}).get("prompt")}
                         for key, cells in keyed(rows.get("variant", []), "family", "variant").items()}
    return shown


def assert_added_fields(page: Any, protocol: Mapping[str, Any], variant_inputs: Mapping[tuple[str, str], Any],
                        preprocessing: str, counts: Mapping[str, int]) -> dict[str, Any]:
    """Prompt and token hashes, token counts, the ICA preprocessing mode and the executed and reused counts,
    each against a value that was not read from the bundle.

    Prompt text: a family the protocol marks (``PROMPT_TEXT_MARKER``) shows exactly the protocol's text for each
    variant. Every other family shows "prompt text is not in this bundle", and none of its prompt strings may
    be anywhere on the page. Until 2026-11-10 no family could carry text and this check required that of all
    of them; the rule is unchanged for a family without the marker, and ``detect_older_bundle`` still requires
    it of every family for a bundle without the export."""
    shown = shown_added_fields(page)
    assert set(shown["variants"]) == set(variant_inputs), "the variant rows are not the protocol's variants"
    wanted_text = expected_prompt_text(protocol)
    for key, want in variant_inputs.items():
        got = {name: shown["variants"][key][name] for name in ("prompt_sha256", "token_sha256", "n_tokens")}
        assert got == dict(want), f"{key}: page shows {got}, the fixture protocol gives {dict(want)}"
        wanted = PROMPT_TEXT_ABSENT if wanted_text[key] is None else wanted_text[key]
        assert shown["variants"][key]["prompt"] == wanted, (
            f"{key}: the prompt cell does not read what the protocol's marker allows "
            f"({'no text' if wanted_text[key] is None else 'the protocol text'})")
    withheld = [entry["prompt"] for family in protocol["case_families"]
                for name, entry in family["variants"].items() if wanted_text[(family["family_id"], name)] is None]
    exported = [text for text in wanted_text.values() if text is not None]
    leaked = [number for number, prompt in enumerate(withheld) if prompt and prompt in shown["text"]]
    assert withheld and exported, "the fixture run no longer has both a marked and an unmarked family"
    assert not leaked, f"the page shows the text of {len(leaked)} prompts the protocol does not mark for publication"
    families = len(protocol["case_families"])
    assert shown["preprocessing"] == [preprocessing] * families, (
        f"preprocessing mode shown {shown['preprocessing']}, the protocol's ICA block declares {preprocessing!r}")
    assert len(shown["preprocessing_source"]) == families and all(shown["preprocessing_source"]), (
        "a completed ICA block does not say where its preprocessing mode was read from")
    assert (shown["executed"], shown["reused"]) == (str(counts["executed"]), str(counts["reused"])), (
        f"executed and reused shown ({shown['executed']!r}, {shown['reused']!r}); the command line reported "
        f"{counts['executed']} executed attempts and {counts['reused']} reuse events")
    return {"variant_rows": len(variant_inputs), "preprocessing_mode": preprocessing,
            "executed_attempts": counts["executed"], "reused_events": counts["reused"],
            "prompt_text_on_page": 0, "prompt_text_exported_by_the_protocol_marker": len(exported),
            "prompt_text_on_page_scope": "prompts of families the protocol does not mark"}


DOTS = """() => Array.from(document.querySelectorAll('#exp-results [data-kind="dotplot"]')).map((panel) => {
    const box = (node) => { const r = node.getBoundingClientRect(); return {left: r.left, width: r.width}; };
    const rows = Array.from(panel.querySelectorAll('[data-kind="behavior-variant"]'));
    const axis = panel.querySelector('.dp-axis .dp-t');
    return {
        family: panel.dataset.family, target: panel.dataset.target, title: panel.querySelector('h5').textContent,
        label: panel.getAttribute('aria-label'),
        primary: panel.dataset.primary, in_other_targets: !!panel.closest('details[data-kind="other-targets"]'),
        axis: box(axis),
        ticks: Array.from(axis.querySelectorAll('span')).map((t) => [t.textContent, t.style.left]),
        rows: rows.map((row) => {
            const track = row.querySelector('.dp-t'), dot = row.querySelector('[data-kind="dot"]');
            const d = dot ? dot.getBoundingClientRect() : null;
            return {
                variant: row.dataset.variant, value: row.dataset.value === undefined ? null : row.dataset.value,
                track: box(track), centre: d ? d.left + d.width / 2 : null, diameter: d ? d.width : null,
                text: row.querySelector('[data-col="probability"]').innerText.trim(),
                name: row.querySelector('[data-col="variant"]').innerText.trim(),
            };
        }),
    };
})"""


STRAY_MARKS = """() => ({
    dots_outside_a_probability_panel: Array.from(document.querySelectorAll('[data-kind="dot"]'))
        .filter((d) => !d.closest('[data-kind="dotplot"]')).length,
    axes_in_internal_measurements: document.querySelectorAll(
        '[data-kind="method-fold"] .dp-t, [data-kind="method-fold"] [data-kind="dot"]').length,
})"""


def assert_dots(page: Any, expected: Mapping[str, Any], bundle: Mapping[str, Any]) -> dict[str, Any]:
    """The directly labelled dot plot of the target-token probability: one row per wording on one 0 to 1 axis.

    For every dot: the value it carries is the value the bundle records for that wording (every side of every
    comparison block), and equals the softmax of the fixture logits; its centre sits at that fraction of its
    track, to within one CSS pixel; its printed label is the value to four decimals; its row names the
    wording by the page's name for it. All tracks of one panel share the axis the tick labels 0, 0.5 and 1 are
    drawn on. One panel per case is the primary one, for the protocol's primary target, and it sits outside
    the fold of the other targets. Nothing but a probability is drawn on such an axis: a readout rank and a
    component score have no dot and no axis."""
    recorded: dict[tuple[str, str, str], float] = {}
    for family in bundle["comparisons"]:
        for entry in family["comparisons"]:
            for target in entry["behavior"]["targets"]:
                for side in ("a", "b"):
                    key = (family["family_id"], entry[side], target["target_id"])
                    assert recorded.setdefault(key, target[side]) == target[side], f"{key}: the bundle disagrees"
    panels = page.evaluate(DOTS)
    seen: set[tuple[str, str, str]] = set()
    worst = 0.0
    for panel in panels:
        assert ENDPOINT_LABEL in panel["title"] and ENDPOINT_LABEL in panel["label"], f"panel title {panel['title']!r}"
        assert [tick[0] for tick in panel["ticks"]] == ["0", "0.5", "1"], f"axis labels {panel['ticks']}"
        assert [tick[1] for tick in panel["ticks"]] == ["0px", "50%", "100%"], f"axis positions {panel['ticks']}"
        for row in panel["rows"]:
            key = (panel["family"], row["variant"], panel["target"])
            assert key not in seen, f"{key}: the value is plotted twice"
            seen.add(key)
            assert row["value"] is not None and row["centre"] is not None, f"{key}: no dot is drawn"
            value = float(row["value"])
            assert value == recorded[key], f"{key}: the dot carries {value!r}, the bundle records {recorded[key]!r}"
            assert abs(value - expected["variants"][key]) < TIE_TOLERANCE, (
                f"{key}: the dot carries {value!r}, the fixture logits give {expected['variants'][key]!r}")
            assert abs(row["track"]["left"] - panel["axis"]["left"]) < 0.01 and abs(
                row["track"]["width"] - panel["axis"]["width"]) < 0.01, f"{key}: the row is not on the panel's axis"
            offset = row["centre"] - (row["track"]["left"] + value * row["track"]["width"])
            worst = max(worst, abs(offset))
            assert abs(offset) <= 1.0, f"{key}: the dot is {offset:+.2f} px from its value on the axis"
            assert row["diameter"] >= 8, f"{key}: the dot is {row['diameter']} px wide"
            assert row["text"] == fmt_plain(value) and row["name"] == wording_label(row["variant"]), (
                f"{key}: the dot is labelled {row['name']!r} {row['text']!r}")
    assert seen == set(expected["variants"]), "the dots are not the fixture's family, wording and target set"
    wanted_primary = bundle["protocol"]["primary_endpoint"]["target"]
    for family in {panel["family"] for panel in panels}:
        mine = [panel for panel in panels if panel["family"] == family]
        first = [panel for panel in mine if panel["primary"] == "true"]
        assert len(first) == 1 and first[0]["target"] == wanted_primary and not first[0]["in_other_targets"], (
            f"{family}: the primary panel is not the one panel of target {wanted_primary} outside the other targets")
        assert all(panel["in_other_targets"] for panel in mine if panel["primary"] != "true"), (
            f"{family}: a target that is not the primary one is drawn outside the fold of the other targets")
    stray = page.evaluate(STRAY_MARKS)
    assert stray == {"dots_outside_a_probability_panel": 0, "axes_in_internal_measurements": 0}, (
        f"a quantity that is not a probability is drawn on an axis: {stray}")
    return {"panels": len(panels), "dots": len(seen), "largest_offset_px": round(worst, 3),
            "axis": "0 to 1, tick labels 0, 0.5 and 1", "primary_target": wanted_primary,
            "quantities_plotted": "target-token probability only"}


LABELS = """() => {
    const visible = (node) => node.getClientRects().length > 0;
    const text = (sel) => Array.from(document.querySelectorAll(sel)).filter(visible).map((n) => n.innerText.trim());
    return {
        h1: document.querySelector('h1').innerText.trim(),
        title: document.title,
        headings: text('main h2, main h3, main h4, main h5'),
        heads: text('main th').concat(text('main .ctx-l'), text('main dt'), text('.toc a')),
        context: Object.fromEntries(Array.from(document.querySelectorAll('#exp-evidence .ctx-i')).map((item) => [
            item.querySelector('.ctx-l').innerText.trim(),
            [item.querySelector('.ctx-v').innerText.trim(), item.querySelector('.ctx-l').getAttribute('title')]])),
        recorded: Object.fromEntries(Array.from(document.querySelectorAll('#exp-protocol dt')).map((dt) => [
            dt.innerText.trim(), dt.nextElementSibling.innerText.trim()])),
        folds_in_context: document.querySelectorAll('#evidence details').length,
        terms: Object.fromEntries(Array.from(document.querySelectorAll('#exp-terms dt')).map((dt) => [
            dt.innerText.trim(), dt.nextElementSibling.innerText.trim()])),
        run_status_head: document.querySelector('#methods th:nth-child(2)').innerText.trim(),
        guide: document.getElementById('exp-guide').innerText,
        page: document.querySelector('main').innerText,
        wordings: Array.from(document.querySelectorAll('#exp-families [data-variant]')).map((node) => {
            const name = node.matches('[data-kind="wording"]') ? node.querySelector('[data-col="wording-name"]')
                : node.matches('[data-kind="behavior-variant"], [data-kind="readout"]')
                    ? node.querySelector('[data-col="variant"]') : null;
            return name ? [node.dataset.kind, node.dataset.variant, name.innerText.trim()] : null;
        }).filter(Boolean),
        outside_code: (() => {
            const copy = document.querySelector('main').cloneNode(true);
            copy.querySelectorAll('code, .hash').forEach((node) => node.remove());
            return copy.textContent;
        })(),
        titles: Array.from(document.querySelectorAll('main [title], main [aria-label]')).map(
            (node) => (node.getAttribute('title') || '') + ' ' + (node.getAttribute('aria-label') || '')).join(' | '),
        uncertainty: Array.from(document.querySelectorAll('#exp-families [data-kind="uncertainty"]')).map(
            (node) => node.innerText.trim()),
        cases_text: document.getElementById('exp-families').innerText,
    };
}"""


def assert_reader_labels(page: Any, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """The reader-facing labels are what the page shows, and the schema term of each is still on the page."""
    found = page.evaluate(LABELS)
    assert found["h1"] == "Compare methods" and found["title"].startswith("Compare methods"), found["h1"]
    upper = [heading.upper() for heading in found["headings"] + found["heads"]]
    for label in ("Cases", "Run status", "Methods & source"):
        assert label.upper() in upper, f"no heading reads {label!r}"
    for retired in RETIRED_HEADINGS:
        assert retired.upper() not in upper, f"the retired heading {retired!r} is still a heading or a column head"
    assert found["run_status_head"].upper() == "RUN STATUS", f"the status column is headed {found['run_status_head']!r}"
    context = {label.upper(): value for label, value in found["context"].items()}
    declared, schema = context["ANALYSIS ELIGIBILITY"]
    assert declared == "none declared" and "evidence.analysis_memberships" in schema, (declared, schema)
    version, schema = context["STUDY VERSION"]
    assert version == f"{protocol['protocol_id']} · version {protocol['version']}" and "protocol.sha256" in schema, (
        version, schema)
    assert context["CLINICAL REVIEW"][0] == protocol["evidence"]["clinical_review"], context["CLINICAL REVIEW"]
    # One disclosure holds the shared context, with each schema field named and its recorded value.
    assert found["folds_in_context"] == 1, f"{found['folds_in_context']} folds hold the shared context"
    recorded = found["recorded"]
    assert recorded["evidence.analysis_memberships (analysis membership)"] == "none", recorded
    assert recorded["evidence.clinical_review"] == protocol["evidence"]["clinical_review"], recorded
    assert recorded["evidence.visibility"] == "not_published" and recorded["evidence.restriction_reasons"] == "none"
    for label, term in READER_LABELS.items():
        assert label in found["terms"] and term.lower() in found["terms"][label].lower(), (
            f"Methods & source does not give the schema term of {label!r} ({term!r})")
    for term in SCHEMA_TERMS:
        assert term in found["page"], f"the schema term {term!r} is no longer on the page"
    # The endpoint: named "Target-token probability", explained once, never called accuracy, risk or understanding.
    assert found["page"].count(ENDPOINT_FIRST_TOKEN) == 1 and ENDPOINT_FIRST_TOKEN in found["guide"], (
        "the first-token explanation is absent or repeated")
    assert ENDPOINT_LABEL in found["guide"] and "0 to 1" in found["guide"] and "Uncertainty: none computed" in found[
        "guide"], "the endpoint's unit, denominator or uncertainty statement is absent"
    labelled = [text for text in found["headings"] + found["heads"]
                if any(word in text.lower() for word in FORBIDDEN_IN_LABELS)]
    assert not labelled, f"a heading or column head uses a forbidden word: {labelled}"
    # Units, stated once: a difference is a difference in probability, and 0.01 of it is one percentage point.
    assert "0.01 is one percentage point" in found["guide"] and SUBTRACTION_HEAD.split()[0] in found["guide"], (
        "the unit of a difference is not stated beside the endpoint")
    # Uncertainty is stated as the bundle records it. This bundle computed none, so each case says so once and
    # no interval is printed anywhere among the cases.
    cases = len(protocol["case_families"])
    assert found["uncertainty"] == [NO_INTERVAL] * cases, f"uncertainty lines: {found['uncertainty'][:2]}"
    assert "\u00b1" not in found["cases_text"] and "95%" not in found["cases_text"], (
        "an interval is shown for a bundle that computed none")
    return {"labels": sorted(READER_LABELS), "schema_terms_on_page": len(SCHEMA_TERMS),
            "endpoint_explained": 1, "headings_checked": len(found["headings"]) + len(found["heads"]),
            "uncertainty": "none computed, stated once per case"}


def assert_wording_labels(page: Any, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Every wording is named by the page's label for it, in the pair, in the plot and in the readout tables.
    The file's name of the third required variant is printed nowhere as a label: with every fold open, the
    page's text outside ``code`` elements (where identifiers are printed as the file records them) does not
    hold it, and neither does a title or an accessible name."""
    found = page.evaluate(LABELS)
    variants = {name for family in protocol["case_families"] for name in family["variants"]}
    assert variants <= set(WORDING_LABELS) and NEVER_A_LABEL in variants, "the fixture's variant names changed"
    kinds: dict[str, int] = {}
    for kind, variant, shown in found["wordings"]:
        assert shown == wording_label(variant), f"a {kind} row of {variant!r} is named {shown!r}"
        kinds[kind] = kinds.get(kind, 0) + 1
    assert set(kinds) == {"wording", "behavior-variant", "readout"}, f"rows read: {sorted(kinds)}"
    assert len(set(WORDING_LABELS.values())) == len(WORDING_LABELS) and all(
        NEVER_A_LABEL not in label.lower() for label in WORDING_LABELS.values()), "a label repeats or uses the word"
    labels = page.evaluate("() => window.pwExperimentViewer.wordingLabels")
    assert labels == WORDING_LABELS, f"the page's wording names are {labels}"
    assert NEVER_A_LABEL not in found["outside_code"].lower(), (
        f"the word {NEVER_A_LABEL!r} is printed outside a code element")
    assert NEVER_A_LABEL not in found["titles"].lower(), f"the word {NEVER_A_LABEL!r} is in a title or a name"
    as_recorded = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#exp-families tr[data-kind="variant"] [data-col="variant"] code')).map((node) => node.textContent)""")
    assert sorted(set(as_recorded)) == sorted(variants), "Methods & source of a case does not give the file's names"
    return {"rows_named": kinds, "labels": {name: WORDING_LABELS[name] for name in sorted(variants)},
            "file_names_printed_as_code_in_methods_and_source": sorted(set(as_recorded))}


def assert_prompt_text(page: Any, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """The explicit prompt-text path and the missing-text state, in one bundle.

    A marked family shows the protocol's text in each paired-wording row; in a synthetic bundle the line under
    the pair says the text is a placeholder, and the case's Methods & source says on what basis the text is
    shown. An unmarked family shows the missing-text sentence and neither line. The prompt hash of every row
    is in the case's Methods & source."""
    wanted = expected_prompt_text(protocol)
    rows = keyed(table_rows(page).get("wording", []), "family", "variant")
    assert set(rows) == set(wanted), "the paired-wording rows are not the protocol's variants"
    state = page.evaluate("""() => Array.from(document.querySelectorAll('section.fam')).map((fam) => ({
        family: fam.dataset.family,
        rows: Array.from(fam.querySelectorAll('[data-kind="wording"]')).map((r) => [r.dataset.variant, r.dataset.text]),
        basis: Array.from(fam.querySelectorAll('[data-kind="input-identity"] [data-kind="text-basis"]')).map(
            (p) => p.innerText),
        placeholder: Array.from(fam.querySelectorAll('[data-kind="text-placeholder"]')).map((p) => p.innerText),
        hashes: fam.querySelectorAll('[data-kind="input-identity"] tr[data-kind="variant"]').length,
        order: Array.from(fam.querySelectorAll('h4')).map((h) => h.innerText.trim()),
        banner: fam.querySelectorAll('[data-kind="synthetic-banner"]').length,
    }))""")
    exported = absent = 0
    for family in state:
        marked = family["family"] in TEXT_FAMILIES
        for variant, flag in family["rows"]:
            text = wanted[(family["family"], variant)]
            shown = rows[(family["family"], variant)]["prompt"]
            assert (flag, shown) == (("exported", text) if marked else ("absent", PROMPT_TEXT_ABSENT)), (
                f"{family['family']} {variant}: the wording row is in state {flag!r}")
            exported += marked
            absent += not marked
        if marked:
            assert len(family["basis"]) == 1 and PROMPT_TEXT_MARKER in family["basis"][0], (
                f"{family['family']}: the basis of the shown text is not stated: {family['basis']}")
            assert len(family["placeholder"]) == 1 and "placeholder text of a synthetic fixture" in family[
                "placeholder"][0], f"{family['family']}: the pair does not say its text is a placeholder"
        else:
            assert family["basis"] == [] and family["placeholder"] == [], (
                f"{family['family']}: a basis or placeholder line is shown for text that is absent")
        assert family["hashes"] == len(family["rows"]) and family["banner"] == 1, (
            f"{family['family']}: the hash rows or the synthetic label are missing")
        # Reading order of one case: the pair, the primary output, internal measurements, interventions.
        assert family["order"] == CASE_HEADINGS, family["order"]
    assert exported and absent, "the bundle no longer shows both states"
    return {"wording_rows_with_exported_text": exported, "wording_rows_that_say_text_is_absent": absent,
            "marker": PROMPT_TEXT_MARKER}


TARGETS = """() => Array.from(document.querySelectorAll('#exp-families section.fam')).map((fam) => ({
    family: fam.dataset.family,
    text: fam.innerText,
    panels: Array.from(fam.querySelectorAll('[data-kind="dotplot"]')).map((panel) => ({
        target: panel.dataset.target, title: panel.querySelector('h5').innerText.trim(),
        label: panel.getAttribute('aria-label'),
        note: panel.querySelector('[data-kind="target-note"]').innerText.trim(),
        state: panel.querySelector('[data-kind="target-note"]').dataset.targetText,
    })),
    records: Array.from(fam.querySelectorAll('tr[data-kind="target-record"]')).map((tr) => [tr.dataset.target,
        tr.querySelector('[data-col="text"]').innerText.trim(), tr.querySelector('[data-col="n_tokens"]').innerText.trim()]),
    basis: Array.from(fam.querySelectorAll('[data-kind="target-basis"]')).map((p) => p.innerText),
}))"""


def assert_target_text(page: Any, protocol: Mapping[str, Any],
                       partial: tuple[str, str] | None = None) -> dict[str, Any]:
    """Target text is on the page only where the bundle exports it, and a first-token value is never shown as
    the probability of a whole word.

    A family with both markers names each target by the protocol's text and says the target is one token. A
    family without the target marker names the target by its id and says its text is not exported; the
    protocol's target text is then nowhere in that case, although every family of the fixture has the same
    target ids and token ids, so text worked out from a token id or taken from another case would show here.
    ``partial`` names one target that the served copy says spans two tokens: its title and its note must say
    "first token of the target", and the note must say the value is not the probability of the whole word."""
    wanted = expected_target_text(protocol)
    found = page.evaluate(TARGETS)
    texts = {family["family_id"]: sorted({target["text"] for target in family["targets"]})
             for family in protocol["case_families"]}
    states: dict[str, int] = {"exported": 0, "absent": 0, "partial": 0}
    assert {family["family"] for family in found} == set(texts), "the cases shown are not the protocol's"
    for family in found:
        fid = family["family"]
        assert {panel["target"] for panel in family["panels"]} == {tid for f, tid in wanted if f == fid}, (
            f"{fid}: the targets plotted are not the protocol's")
        records = {target: (text, tokens) for target, text, tokens in family["records"]}
        for panel in family["panels"]:
            key, want = (fid, panel["target"]), wanted[(fid, panel["target"])]
            if want is None:
                assert panel["state"] == "absent" and panel["title"].startswith(
                    f"{ENDPOINT_LABEL} of target {panel['target']}"), f"{key}: titled {panel['title']!r}"
                assert TARGET_TEXT_ABSENT in panel["note"], f"{key}: the note reads {panel['note']!r}"
                assert records[panel["target"]][0] == MISS + "target text is " + NOT_IN_BUNDLE, (
                    f"{key}: the target record reads {records[panel['target']][0]!r}")
            elif key == partial:
                assert panel["state"] == "partial", f"{key}: a target of two tokens is in state {panel['state']!r}"
                assert panel["title"].startswith(f"{ENDPOINT_LABEL} of the {FIRST_TOKEN} “{want['text']}”"), (
                    f"{key}: titled {panel['title']!r}")
                assert FIRST_TOKEN in panel["label"] and FIRST_TOKEN in panel["note"] and NOT_THE_WHOLE_WORD in panel[
                    "note"] and "2 tokens" in panel["note"], f"{key}: the note reads {panel['note']!r}"
                assert records[panel["target"]] == (want["text"], "2"), f"{key}: record {records[panel['target']]}"
            else:
                assert panel["state"] == "exported" and panel["title"].startswith(
                    f"{ENDPOINT_LABEL} of “{want['text']}”"), f"{key}: titled {panel['title']!r}"
                assert FIRST_TOKEN not in panel["title"] and "one token" in panel["note"], (
                    f"{key}: a one-token target is described as a first token: {panel['note']!r}")
                assert records[panel["target"]] == (want["text"], str(want["n_tokens"])), (
                    f"{key}: record {records[panel['target']]}")
            states["partial" if key == partial and want is not None else "absent" if want is None else "exported"] += 1
        exports = any(wanted[(fid, tid)] is not None for f, tid in wanted if f == fid)
        if exports:
            assert len(family["basis"]) == 1 and TARGET_TEXT_MARKER in family["basis"][0], (
                f"{fid}: the basis of the shown target text is not stated: {family['basis']}")
        else:
            assert family["basis"] == [], f"{fid}: a basis line is shown for target text that is absent"
            leaked = [number for number, text in enumerate(texts[fid]) if text in family["text"]]
            assert texts[fid] and not leaked, (
                f"{fid}: the case shows the text of {len(leaked)} targets the bundle does not export")
    assert states["exported"] and states["absent"], f"the bundle no longer shows both states: {states}"
    assert (states["partial"] == 1) is (partial is not None), f"partial targets shown: {states['partial']}"
    return {"target_panels": states, "marker": TARGET_TEXT_MARKER,
            "text_never_shown_for": sorted(fid for fid in texts if all(wanted[(fid, t)] is None for f, t in wanted
                                                                       if f == fid))}


def assert_stable_links(page: Any, base: str) -> dict[str, Any]:
    """Ids that links and other tools use are on the page, and the loaded state offers a plain download link."""
    missing = page.evaluate("(ids) => ids.filter((id) => !document.getElementById(id))", list(STABLE_IDS))
    assert not missing, f"ids no longer on the page: {missing}"
    state = page_state(page)
    assert state["links"] == [[f"../data/{BUNDLE_PARAM}", "Download this comparison file (JSON)", True]], state["links"]
    resolved = page.evaluate("() => document.querySelector('#exp-state a').href")
    assert resolved == f"{base}/data/{BUNDLE_PARAM}", f"the download link resolves to {resolved}"
    toc = page.evaluate("() => Array.from(document.querySelectorAll('.toc a')).map((a) => a.getAttribute('href'))")
    assert toc == SECTION_LINKS, f"section links: {toc}"
    # Until 2026-11-11 "#evidence" was the first section and a section link. It is now inside Methods & source;
    # the id is kept, so an address that ends in it still reaches the labels.
    inside = page.evaluate("() => ['evidence', 'protocol', 'totals', 'links', 'limitations'].filter("
                           "(id) => !document.querySelector('#provenance #' + id))")
    assert not inside, f"not inside Methods & source any more: {inside}"
    return {"ids": len(STABLE_IDS), "section_links": toc}


ORDER = """() => {
    const before = (a, b) => !!a && !!b && !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const shown = (node) => !!node && node.checkVisibility();
    const top = (node) => node ? Math.round(node.getBoundingClientRect().top + window.scrollY) : null;
    const first = document.querySelector('#exp-families section.fam');
    const pair = first ? first.querySelector('[data-kind="wording"] [data-col="prompt"]') : null;
    const output = first ? first.querySelector('[data-kind="primary-output"] [data-kind="dotplot"]') : null;
    const value = output ? output.querySelector('[data-kind="behavior-variant"] [data-col="probability"]') : null;
    const parts = ['[data-kind="wording"]', '[data-kind="primary-output"]', '[data-kind="other-targets"]',
                   '[data-kind="internal"]', '[data-kind="intervention"]', '[data-kind="input-identity"]'];
    return {
        pair_before_output: before(pair, output),
        output_before_run_status: before(output, document.getElementById('methods')),
        output_before_methods_and_source: before(output, document.getElementById('provenance')),
        run_status_before_methods_and_source: before(document.getElementById('methods'),
                                                    document.getElementById('provenance')),
        shown_as_loaded: [shown(pair), shown(output), shown(value)],
        tops: {pair: top(pair), output: top(output), run_status: top(document.getElementById('methods')),
               methods_and_source: top(document.getElementById('provenance'))},
        cases: Array.from(document.querySelectorAll('#exp-families section.fam')).map((fam) => {
            const found = parts.map((selector) => fam.querySelector(selector));
            return {family: fam.dataset.family, present: found.map((node) => !!node),
                    in_order: found.filter(Boolean).every((node, i, all) => i === 0 || before(all[i - 1], node))};
        }),
    };
}"""


def check_reading_order(s: Session) -> dict[str, Any]:
    """In document order, and as the page loads with no fold opened by the reader: the paired wording of the
    first case, then its primary output with a value, then the run status, then Methods & source. Each case
    keeps one order of its parts. Positions in CSS pixels go into the receipt; none is required."""
    page, _ = s.open(expand=False)
    try:
        found = page.evaluate(ORDER)
        for name in ("pair_before_output", "output_before_run_status", "output_before_methods_and_source",
                     "run_status_before_methods_and_source"):
            assert found[name], f"document order: {name.replace('_', ' ')} does not hold"
        assert found["shown_as_loaded"] == [True, True, True], (
            f"the pair, the primary plot or its value is not visible as the page loads: {found['shown_as_loaded']}")
        assert len(found["cases"]) == s.families, f"{len(found['cases'])} cases rendered"
        for case in found["cases"]:
            assert case["present"][:2] == [True, True] and case["present"][3:] == [True, True, True], (
                f"{case['family']}: a part of the case is missing: {case['present']}")
            assert case["in_order"], f"{case['family']}: the parts of the case are out of order"
        return {"order": "pair, primary output, run status, methods and source",
                "top_in_css_px_at_1280": found["tops"]}
    finally:
        page.close()


LEAD = """() => {
    const text = (node) => node ? node.innerText : '';
    return {
        lead: ['exp-state', 'exp-fixture', 'families'].map((id) => text(document.getElementById(id))).join('\\n')
            + '\\n' + text(document.querySelector('.toc')),
        source: text(document.getElementById('provenance')),
        file: text(document.querySelector('#exp-provenance dd[data-col="file"]')).trim(),
        schema: text(document.querySelector('#exp-provenance dd[data-col="schema"]')).trim(),
    };
}"""
# What belongs under Methods & source and nowhere above it: hashes, the schema string, the publication markers
# and the schema words of the evidence block.
MACHINERY = (BUNDLE_SCHEMA, "sha256", "SHA-256", PROMPT_TEXT_MARKER, TARGET_TEXT_MARKER, "not_published",
             "evidence.", "protocol.sha256", "execution.by_state", "restriction")


def check_machinery_placement(s: Session) -> dict[str, Any]:
    """Hashes, schema versions and publication markers are under Methods & source. What a reader sees above it,
    with every case opened and no smaller fold opened, holds none of them: no 64-character hash, no schema
    string, no marker. Methods & source holds the file path, the schema string and the hashes."""
    import re

    page, _ = s.open(expand=False)
    try:
        page.focus("#exp-fam-toggle")
        page.keyboard.press("Enter")
        found = page.evaluate(LEAD)
        hashes = re.findall(r"[0-9a-f]{64}", found["lead"])
        assert not hashes, f"{len(hashes)} hash(es) are shown above Methods & source"
        above = [needle for needle in MACHINERY if needle in found["lead"]]
        assert not above, f"shown above Methods & source: {above}"
        assert found["file"] == f"data/{BUNDLE_PARAM}" and found["schema"] == BUNDLE_SCHEMA, (
            f"Methods & source gives the file as {found['file']!r} and the schema as {found['schema']!r}")
        assert re.search(r"[0-9a-f]{64}", found["source"]) and "not_published" in found["source"], (
            "Methods & source does not hold the hashes or the visibility label")
        page.evaluate("() => document.querySelectorAll('#exp-families details').forEach((d) => { d.open = true; })")
        cases = page.evaluate("() => document.getElementById('exp-families').innerText")
        in_case = page.evaluate("""() => Array.from(document.querySelectorAll('#exp-families section.fam')).map((fam) => {
            const copy = fam.cloneNode(true);
            copy.querySelectorAll('[data-kind="input-identity"], [data-kind="method-source"]').forEach(
                (node) => node.remove());
            return copy.textContent;
        }).join('\\n')""")
        assert re.search(r"[0-9a-f]{64}", cases) and not re.search(r"[0-9a-f]{64}", in_case), (
            "a case shows a hash outside its Methods & source folds, or those folds hold none")
        return {"hashes_above_methods_and_source": 0, "checked_for": list(MACHINERY)}
    finally:
        page.close()


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
    assert page.evaluate("() => location.hash") == SECTION_LINKS[0], "Enter on a section link did not move to the section"
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


FOCUS = """() => {
    const node = document.activeElement, style = getComputedStyle(node), box = node.getBoundingClientRect();
    const parent = node.parentElement;
    return {
        tag: node.tagName, id: node.id || null, cls: typeof node.className === 'string' ? node.className : '',
        text: (node.innerText || '').trim().split('\\n')[0].slice(0, 60),
        kind: node.tagName === 'SUMMARY' ? (parent.className || parent.dataset.kind || '') : (node.dataset.kind || ''),
        in_nav: !!node.closest('.masthead nav'), in_toc: !!node.closest('.toc'),
        outline: style.outlineStyle, width: parseFloat(style.outlineWidth),
        in_view: box.bottom > 0 && box.top < window.innerHeight && box.right > 0 && box.left < window.innerWidth,
    };
}"""
# The controls a reader of a loaded comparison uses, in Tab order: name, and how the focused element is known.
MAIN_CONTROLS: tuple[tuple[str, Callable[[Mapping[str, Any]], bool]], ...] = (
    ("skip link", lambda stop: stop["cls"] == "skip"),
    ("first navigation link", lambda stop: stop["in_nav"] and stop["tag"] == "A"),
    ("navigation disclosure", lambda stop: stop["tag"] == "SUMMARY" and stop["kind"] == "nav-more"),
    ("download link", lambda stop: stop["kind"] == "download"),
    ("section link", lambda stop: stop["in_toc"]),
    ("button that opens every case", lambda stop: stop["id"] == "exp-fam-toggle"),
    ("case heading", lambda stop: stop["tag"] == "SUMMARY" and stop["kind"] == "fam-fold"),
    ("fold of the other targets", lambda stop: stop["tag"] == "SUMMARY" and stop["kind"] == "fold"),
)


def tab_stops(page: Any, limit: int = 45) -> list[dict[str, Any]]:
    """Press Tab up to ``limit`` times from the top of a fresh page and describe each element that takes focus."""
    stops = []
    for _ in range(limit):
        page.keyboard.press("Tab")
        stop = page.evaluate(FOCUS)
        if stop["tag"] in ("BODY", "HTML"):
            break
        stops.append(stop)
    return stops


def assert_focus(stops: Sequence[Mapping[str, Any]],
                 controls: Sequence[tuple[str, Callable[[Mapping[str, Any]], bool]]]) -> dict[str, Any]:
    """Every named control is reached by Tab, in the order given, and shows a focus outline when it is.

    The outline is read from the focused element after a real key press: a solid outline at least 2 CSS px
    wide, on an element that is inside the window."""
    position, reached = 0, {}
    for name, known in controls:
        index = next((i for i in range(position, len(stops)) if known(stops[i])), None)
        assert index is not None, f"Tab does not reach the {name} (after {position} of {len(stops)} stops)"
        stop = stops[index]
        assert stop["outline"] == "solid" and stop["width"] >= 2, (
            f"the {name} shows no focus outline: {stop['outline']} {stop['width']} px")
        assert stop["in_view"], f"the {name} takes focus outside the window"
        reached[name], position = index + 1, index + 1
    unmarked = [stop["text"] or stop["tag"] for stop in stops if stop["outline"] != "solid" or stop["width"] < 2]
    assert not unmarked, f"{len(unmarked)} Tab stop(s) show no focus outline; first: {unmarked[:2]}"
    return {"tab_stops_read": len(stops), "reached_at_tab_press": reached}


# ------------------------------------------------------------------------------------------ the browser checks

@dataclass
class Session:
    """What the browser checks share: the served copy, the two browser contexts and the expectations."""
    base: str
    site: Path
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
    plain: Any = None          # a browser context with JavaScript turned off, for the navigation disclosure
    variant_inputs: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    preprocessing: str = ""
    journal_counts: dict[str, int] = field(default_factory=dict)
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

    def alteration(self, name: str, what: str) -> None:
        """File a served copy of the bundle that shows a display state the fixture run cannot produce."""
        self.receipt.setdefault("display_state_alterations", []).append(
            {"check": name, "what": what, "kind": "alteration of a display state; not a run and not a measurement"})

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


IDLE = """() => ({
    head: document.getElementById('exp-empty-head').innerText.trim(),
    routes: Array.from(document.querySelectorAll('#exp-empty a.route')).map((a) => a.getAttribute('href')),
    entries: Array.from(document.querySelectorAll('#exp-index-list [data-kind="index-entry"]')).map((li) => ({
        bundle: li.dataset.bundle, href: li.querySelector('a').getAttribute('href'), text: li.innerText,
    })),
    count: document.getElementById('exp-index-count').innerText.trim(),
    text: document.querySelector('main').innerText,
    source: document.documentElement.outerHTML,
})"""
# Developer syntax that moved to docs/experiment_interface/preview.md. None may be in what a reader sees.
DEVELOPER_SYNTAX = ("?bundle=", "bundle=<", "path under data/", "<path", "address parameter")


def check_no_parameter(s: Session) -> dict[str, Any]:
    """With no address parameter the page reads the site's index, and today that index lists nothing: the
    page shows the empty statement with routes to the results and the methods, and requests no bundle.

    Until 2026-11-10 the page requested no data at all here. It now requests exactly one file, the index, so
    that a reader is given a list and never has to write an address parameter."""
    url, index_url = page_url(s.base), f"{s.base}/data/{INDEX_FILE}"
    index = json.loads((s.site / "data" / INDEX_FILE).read_text(encoding="utf-8"))
    assert index["schema_version"] == INDEX_SCHEMA and index["comparisons"] == [], (
        "the site's index lists a comparison; this check expects today's empty list")
    page, log = s.open(url)
    try:
        state = page_state(page)
        assert state["state"] == "idle" and state["idle_visible"], f"state {state['state']!r}"
        assert state["index"] == "empty" and state["empty_visible"] and not state["index_visible"], (
            f"index state {state['index']!r}")
        assert not state["box_visible"] and not state["results_visible"], "a state box or results show"
        assert state["method_rows"] == 0, "the methods table has rows with no bundle"
        idle = page.evaluate(IDLE)
        assert idle["head"] == EMPTY_HEAD, f"the empty statement reads {idle['head']!r}"
        assert idle["routes"] == list(EMPTY_ROUTES), f"routes offered: {idle['routes']}"
        assert idle["entries"] == [], f"an empty index is shown with entries: {idle['entries']}"
        syntax = [needle for needle in DEVELOPER_SYNTAX if needle in idle["text"]]
        assert not syntax, f"the page still shows developer syntax: {syntax}"
        assert log.requests == [url, index_url], f"requests made with no parameter: {log.requests}"
        assert log.data_requests() == [index_url], f"data requests: {log.data_requests()}"
        assert not log.console_errors and not log.page_errors and not log.http_errors, "browser errors"
        s.states["idle"] = {"label": "idle statement", "class": "idle", "border": "statement"}
        s.shot(page, "experiment_no_parameter_1280.png")
        return {"requests": len(log.requests), "data_requests": len(log.data_requests()),
                "bundle_requests": 0, "empty_statement": idle["head"], "routes": idle["routes"]}
    finally:
        page.close()


class _Report:
    """The two members of ``validate_frontend_contract.Report`` that ``check_experiment_index`` uses."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def err(self, artifact: str, path: str, message: str) -> None:
        self.errors.append(f"{artifact} :: {path} :: {message}")


def contract_errors(site: Path) -> list[str]:
    """What ``scripts/experiment_index_contract.check_experiment_index`` reports for the site at ``site``."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_experiment_index_contract_for_preview", INDEX_CONTRACT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = _Report()
    module.check_experiment_index(report, site)
    return report.errors


def write_index(site: Path) -> dict[str, Any]:
    """Run the real index writer on the site copy at ``site`` and return the document it wrote."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, str(INDEX_WRITER), "--site", str(site)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise SetupProblem(f"the index writer exited {proc.returncode}:\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}")
    return json.loads((site / "data" / INDEX_FILE).read_text(encoding="utf-8"))


def check_index_never_lists_the_synthetic_bundle(s: Session) -> dict[str, Any]:
    """The real writer, run on the copy that holds the synthetic bundle, lists nothing and names the bundle
    under ``not_listed``. The page then shows the empty statement and no link. The contract check reports the
    synthetic bundle under ``data/`` as an error, which is what stops such a file reaching the real site."""
    index_path = s.site / "data" / INDEX_FILE
    original = index_path.read_bytes()
    try:
        index = write_index(s.site)
        assert index["comparisons"] == [] and index["totals"]["listed"] == 0, f"listed: {index['comparisons']}"
        named = {row["file"]: row["reasons"] for row in index["not_listed"]}
        assert named.get(BUNDLE_PARAM) and "synthetic" in named[BUNDLE_PARAM], f"not_listed: {named}"
        page, log = s.open(page_url(s.base))
        try:
            state, idle = page_state(page), page.evaluate(IDLE)
            assert state["index"] == "empty" and idle["head"] == EMPTY_HEAD and idle["entries"] == [], (
                f"with a synthetic bundle under data/ the page shows {idle['entries']}")
            assert BUNDLE_PARAM not in idle["source"], "the page names the synthetic bundle"
            assert log.data_requests() == [f"{s.base}/data/{INDEX_FILE}"], f"data requests: {log.data_requests()}"
        finally:
            page.close()
        errors = contract_errors(s.site)
        assert any(BUNDLE_PARAM in error and "may not be published" in error for error in errors), (
            f"the contract check does not report the synthetic bundle: {errors}")
        return {"listed": 0, "not_listed_reasons": named[BUNDLE_PARAM], "contract_errors_in_the_copy": len(errors)}
    finally:
        index_path.write_bytes(original)


def check_forged_index_entries_are_not_linked(s: Session) -> dict[str, Any]:
    """The page's own rule, apart from the writer's. A hand-made index in the temporary copy names the
    synthetic bundle with its true labels, names it again under forged public labels at a path the address
    rule refuses, and names a non-public entry. The page must link none of them and say that entries are
    not shown. The page cannot open a forged public entry at a valid path without reading the bundle; that
    case is what the writer and the contract check exist for."""
    index_path = s.site / "data" / INDEX_FILE
    original = index_path.read_bytes()
    labels = {"protocol": {"id": "forged", "version": "1", "sha256": "0" * 64}, "model": {"study_id": None, "hf_id": None},
              "clinical_review": "domain_review_pending", "analysis_memberships": [], "cases": 3, "methods": [],
              "primary_endpoint": {"method": None, "metric": None, "target": None}, "prompt_text_cases": 0,
              "bundle_sha256": "0" * 64}
    forged = {"schema_version": INDEX_SCHEMA, "bundle_schema": BUNDLE_SCHEMA, "eligibility": "forged for a check",
              "comparisons": [
                  dict(labels, bundle=BUNDLE_PARAM, evidence_class="synthetic_fixture", visibility="not_published"),
                  dict(labels, bundle=BUNDLE_PARAM, evidence_class="synthetic_fixture", visibility="public"),
                  dict(labels, bundle="../data/" + BUNDLE_PARAM, evidence_class="unclassified", visibility="public"),
                  dict(labels, bundle=BUNDLE_PARAM, evidence_class="unclassified", visibility="restricted")],
              "not_listed": [], "totals": {"bundle_files": 4, "listed": 4, "not_listed": 0}}
    index_path.write_text(json.dumps(forged), encoding="utf-8")
    try:
        page, log = s.open(page_url(s.base))
        try:
            state, idle = page_state(page), page.evaluate(IDLE)
            assert state["index"] == "empty" and idle["entries"] == [], f"forged entries are linked: {idle['entries']}"
            links = page.evaluate("() => Array.from(document.querySelectorAll('#exp-idle a')).map((a) => a.getAttribute('href'))")
            assert links == list(EMPTY_ROUTES), f"links offered: {links}"
            note = page.locator("#exp-index-note").inner_text()
            assert note.startswith("4 index entries are not shown"), f"the note reads {note!r}"
            assert log.data_requests() == [f"{s.base}/data/{INDEX_FILE}"], f"data requests: {log.data_requests()}"
        finally:
            page.close()
        unreadable = dict(forged, schema_version="patientwords.experiment-index/2")
        index_path.write_text(json.dumps(unreadable), encoding="utf-8")
        page, _ = s.open(page_url(s.base))
        try:
            state, idle = page_state(page), page.evaluate(IDLE)
            assert state["index"] == "unreadable" and idle["entries"] == [], state
            assert idle["head"] == "The list of comparisons could not be read" and EMPTY_HEAD not in idle["text"], (
                f"with an index it cannot read the page says {idle['head']!r}")
        finally:
            page.close()
        return {"forged_entries": 4, "linked": 0, "unreadable_index_state": "stated, not shown as empty"}
    finally:
        index_path.write_bytes(original)


def check_index_lists_a_publishable_bundle(s: Session) -> dict[str, Any]:
    """The listing path. A copy of the fixture bundle relabelled as publishable is written into the temporary
    site only. The real writer lists it and still does not list the synthetic bundle; the page shows one link;
    the link, followed from the keyboard, opens that file and renders it without the synthetic marker.

    The relabelled copy is hand-written fixture numbers under a public label. It is a test input for the
    listing path and is never a study bundle; no screenshot is taken of it."""
    index_path, extra = s.site / "data" / INDEX_FILE, s.site / "data" / RELABELLED_PARAM
    original = index_path.read_bytes()
    extra.write_text(json.dumps(relabelled_as_publishable(s.bundle)), encoding="utf-8")
    try:
        index = write_index(s.site)
        assert [entry["bundle"] for entry in index["comparisons"]] == [RELABELLED_PARAM], index["comparisons"]
        entry = index["comparisons"][0]
        assert entry["bundle_sha256"] == sha256_file(extra) and entry["visibility"] == "public", entry
        assert BUNDLE_PARAM in {row["file"] for row in index["not_listed"]}, "the synthetic bundle is not set aside"
        page, log = s.open(page_url(s.base))
        try:
            state, idle = page_state(page), page.evaluate(IDLE)
            assert state["index"] == "listed" and state["index_visible"] and not state["empty_visible"], state
            assert [e["bundle"] for e in idle["entries"]] == [RELABELLED_PARAM], idle["entries"]
            assert idle["entries"][0]["href"] == "?bundle=" + quote(RELABELLED_PARAM, safe=""), idle["entries"]
            assert s.protocol["protocol_id"] in idle["entries"][0]["text"] and idle["count"].startswith("1 comparison")
            assert EMPTY_HEAD not in idle["text"], "the empty statement shows beside a listed comparison"
            page.focus("#exp-index-list a")
            page.keyboard.press("Enter")
            page.wait_for_function("() => document.body.dataset.expState === 'ready'", timeout=20_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            opened = page.evaluate("""() => ({
                query: new URLSearchParams(location.search).get('bundle'),
                synthetic: document.querySelector('#exp-evidence [data-synthetic]').dataset.synthetic,
                banners: document.querySelectorAll('[data-kind="synthetic-banner"]').length,
                evidence: document.querySelector('#exp-evidence [data-col="evidence_class"]').innerText.trim(),
                wording: Array.from(document.querySelectorAll('[data-kind="wording"]')).map((r) => r.dataset.text),
            })""")
            assert opened["query"] == RELABELLED_PARAM and (opened["synthetic"], opened["banners"]) == ("false", 0), opened
            assert opened["evidence"] == "unclassified" and set(opened["wording"]) == {"absent"}, opened
            assert f"{s.base}/data/{RELABELLED_PARAM}" in log.data_requests(), log.data_requests()
            assert not log.console_errors and not log.page_errors and not log.http_errors, "browser errors"
        finally:
            page.close()
        errors = [error for error in contract_errors(s.site) if RELABELLED_PARAM in error or error.startswith(
            INDEX_FILE)]
        assert not errors, f"the contract check faults the index the writer wrote: {errors}"
        return {"listed": 1, "link_followed_from_the_keyboard": True,
                "input": "a relabelled copy of the fixture bundle, in the temporary tree only; not a study bundle"}
    finally:
        extra.unlink()
        index_path.write_bytes(original)


def check_rendered_bundle(s: Session, recorder: Recorder) -> None:
    """The checks that read one rendered page at 1280 px. Each is filed under its own name."""
    page, log = s.open()
    try:
        recorder.run("bundle_renders_with_no_console_error_and_no_failed_request",
                     lambda: assert_ready(page, log, s.base))
        s.note_state(page_state(page))
        recorder.run("synthetic_label_stays_in_view_and_is_in_every_case_line",
                     lambda: assert_banner(page, s.families))
        recorder.run("behaviour_values_equal_softmax_of_fixture_logits", lambda: assert_behavior(page, s.behavior))
        recorder.run("ica_scores_equal_hand_computed_fixture_values",
                     lambda: assert_ica(page, s.ica, s.basis_sha256))
        recorder.run("readout_raw_and_filtered_ranks_side_by_side", lambda: assert_readout(page, s.bundle))
        recorder.run("every_planned_method_listed_with_state_and_reason",
                     lambda: assert_methods(page, s.protocol, s.bundle))
        recorder.run("unsupported_and_unavailable_methods_stated_in_each_family",
                     lambda: assert_not_computed_blocks(page, s.families, s.bundle))
        recorder.run("protocol_model_totals_links_limitations",
                     lambda: assert_other_sections(page, s.protocol, s.validated))
        recorder.run("prompt_hashes_token_counts_preprocessing_and_run_counts_equal_the_fixture",
                     lambda: assert_added_fields(page, s.protocol, s.variant_inputs, s.preprocessing,
                                                 s.journal_counts))
        recorder.run("dot_plot_values_and_positions_equal_the_bundle_and_the_fixture_logits",
                     lambda: assert_dots(page, s.behavior, s.bundle))
        recorder.run("reader_labels_shown_schema_terms_kept_and_endpoint_explained_once",
                     lambda: assert_reader_labels(page, s.protocol))
        recorder.run("wordings_are_named_for_the_reader_and_the_third_variant_is_never_called_normalized",
                     lambda: assert_wording_labels(page, s.protocol))
        recorder.run("prompt_text_shown_only_for_marked_cases_and_absent_state_for_the_rest",
                     lambda: assert_prompt_text(page, s.protocol))
        recorder.run("target_text_shown_only_where_the_bundle_exports_it_and_never_inferred",
                     lambda: assert_target_text(page, s.protocol))
        recorder.run("section_ids_section_links_and_download_link_are_stable",
                     lambda: assert_stable_links(page, s.base))
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


FOLD_STATE = """() => {
    const shown = (node) => !!node && node.checkVisibility();
    const all = (selector) => Array.from(document.querySelectorAll(selector));
    return {
        open: all('#exp-families details.fam-fold').map((d) => d.open),
        headings: all('#exp-families details.fam-fold > summary h3').filter(shown).length,
        banners: all('#exp-families [data-kind="synthetic-banner"]').filter(shown).length,
        button: document.getElementById('exp-fam-toggle').textContent,
        reviews: all('#exp-families details.fam-fold > summary [data-col="case-labels"]').filter(shown)
            .map((n) => n.textContent),
        context: all('#exp-evidence .ctx-i').filter((n) => shown(n.querySelector('.ctx-l')))
            .map((n) => [n.querySelector('.ctx-l').innerText.trim(), n.querySelector('.ctx-v').innerText.trim()]),
        context_fold_open: document.getElementById('protocol').open,
        first_case_top: document.querySelector('#exp-families section.fam').getBoundingClientRect().top + window.scrollY,
        guide_folded: !document.getElementById('exp-guide-more').open,
        plots_shown: all('#exp-families [data-kind="dotplot"]').filter(shown).map((p) => [p.dataset.family, p.dataset.target]),
        tables_shown: all('#exp-families table').filter(shown).map((t) => t.getAttribute('aria-label')),
        inner_folds: all('#exp-families details.fam-fold[open] details').map((d) => [d.dataset.kind, d.dataset.method || '', d.open]),
        capability_fold_open: document.getElementById('exp-capability').open,
    };
}"""


def check_family_folds(s: Session) -> dict[str, Any]:
    """The first family is open, the rest are closed, and a closed family keeps its heading and its labels.
    In the open case one plot is shown, of the primary target; the other targets, each internal method and the
    case's source are closed folds that open from the keyboard."""
    page, _ = s.open(expand=False)
    try:
        first = page.evaluate(FOLD_STATE)
        assert first["open"] == [True] + [False] * (s.families - 1), f"default folds: {first['open']}"
        assert first["headings"] == s.families and first["banners"] == s.families, (
            "a closed family hides its heading or its synthetic label")
        statuses = [family["review_status"].replace("_", " ") for family in s.protocol["case_families"]]
        model = s.protocol["model"]["hf_id"]
        assert len(first["reviews"]) == s.families and all(
            f"clinical review of this case: {status}" in text and f"model {model}" in text
            and f"endpoint: {ENDPOINT_LABEL.lower()} ({FIRST_TOKEN})" in text
            for status, text in zip(statuses, first["reviews"])), (
            f"a case heading does not give the model, the endpoint and the review state: {first['reviews'][:1]}")
        # The labels that say what the comparison may be used for are under Methods & source, visible there
        # without opening a fold.
        assert not first["context_fold_open"] and first["guide_folded"] and not first["capability_fold_open"], (
            "a fold of Methods & source or of the run status is open on load")
        context = {label: value for label, value in first["context"]}
        wanted = {"Clinical review": s.protocol["evidence"]["clinical_review"],
                  "Analysis eligibility": "none declared",
                  "Evidence class": s.protocol["evidence"]["evidence_class"]}
        assert {label: context.get(label) for label in wanted} == wanted, first["context"]
        # One primary target first: the only plot on load is the first case's primary target, and no table of
        # an internal measurement or of hashes is shown until its fold is opened.
        primary = s.bundle["protocol"]["primary_endpoint"]["target"]
        first_family = s.protocol["case_families"][0]["family_id"]
        assert first["plots_shown"] == [[first_family, primary]], f"plots shown on load: {first['plots_shown']}"
        assert len(first["tables_shown"]) == 1 and first["tables_shown"][0].startswith(ENDPOINT_LABEL), (
            f"tables shown on load: {first['tables_shown']}")
        kinds = [kind for kind, _method, _open in first["inner_folds"]]
        assert kinds.count("other-targets") == 1 and kinds.count("method-fold") >= 2 and kinds.count(
            "input-identity") == 1, f"folds of the open case: {kinds}"
        assert not any(is_open for _kind, _method, is_open in first["inner_folds"]), "a fold of the case is open on load"
        opened_from_keyboard = []
        for selector in ('[data-kind="other-targets"]', '[data-kind="method-fold"]', '[data-kind="input-identity"]'):
            fold = f"#exp-families details.fam-fold[open] details{selector}"
            page.focus(f"{fold} > summary")
            page.keyboard.press("Enter")
            assert page.evaluate("(sel) => document.querySelector(sel).open", fold), f"Enter did not open {selector}"
            opened_from_keyboard.append(selector)
        after = page.evaluate(FOLD_STATE)
        assert len(after["plots_shown"]) > 1 and len(after["tables_shown"]) > 2, "an opened fold shows nothing"
        page.evaluate("() => document.querySelectorAll('#exp-families details.fam-fold details').forEach((d) => { d.open = false; })")
        assert first["button"] == OPEN_ALL, f"button reads {first['button']!r}"
        page.focus("#exp-fam-toggle")
        page.keyboard.press("Enter")
        opened = page.evaluate(FOLD_STATE)
        page.keyboard.press("Enter")
        closed = page.evaluate(FOLD_STATE)
        assert all(opened["open"]) and opened["button"] == CLOSE_ALL, f"after one press: {opened['open']}"
        assert not any(closed["open"]) and closed["button"] == OPEN_ALL, f"after two: {closed['open']}"
        page.focus("#exp-families details.fam-fold > summary")
        page.keyboard.press("Enter")
        assert page.evaluate(FOLD_STATE)["open"][0], "Enter on a family heading did not open it"
        return {"families": s.families, "open_by_default": 1, "plots_shown_on_load": 1,
                "folds_opened_from_the_keyboard": opened_from_keyboard,
                "first_case_starts_at_css_px": round(first["first_case_top"])}
    finally:
        page.close()


CASE_STATE = """() => {
    const fixture = document.getElementById('exp-fixture'), box = fixture.getBoundingClientRect();
    const open = document.querySelector('#exp-families details.fam-fold[open]');
    const inView = (node) => {
        if (!node || !node.checkVisibility()) return false;
        const r = node.getBoundingClientRect();
        return r.bottom > 0 && r.top < window.innerHeight;
    };
    const note = document.getElementById('exp-case-note');
    return {
        open: Array.from(document.querySelectorAll('#exp-families details.fam-fold')).map((d) => d.open),
        open_family: open ? open.parentElement.dataset.family : null,
        fixture_in_view: !fixture.hidden && box.height > 0 && box.top >= 0 && box.bottom <= window.innerHeight,
        fixture_text: fixture.innerText.trim(),
        case_heading_in_view: inView(open ? open.querySelector('summary h3') : null),
        case_label_in_view: inView(open ? open.querySelector('summary [data-kind="synthetic-banner"]') : null),
        pair_shown: !!open && Array.from(open.querySelectorAll('[data-kind="wording"]')).every(
            (row) => row.checkVisibility()),
        plot_shown: !!open && !!open.querySelector('[data-kind="primary-output"] [data-kind="dot"]'),
        note: note.hidden ? null : note.innerText.trim(),
        markup: document.querySelector('main').innerHTML,
    };
}"""


def check_case_address(s: Session) -> dict[str, Any]:
    """A case opened directly by its address is the open one, and it is labelled: the address's ``case`` value
    opens that case and scrolls to it, the synthetic line is inside the window, and the case's own heading line
    carries the label. An address that names no case of the comparison says so and shows the first case. The
    value is compared with the file's family ids and is never written into the page."""
    families = [family["family_id"] for family in s.protocol["case_families"]]
    wanted = families[1]
    page, log = s.open(f"{s.url}&case={quote(wanted, safe='')}", expand=False)
    try:
        assert_ready(page, log, s.base)
        found = page.evaluate(CASE_STATE)
        assert found["open"] == [family == wanted for family in families] and found["open_family"] == wanted, (
            f"with case={wanted} the open cases are {found['open']}")
        assert found["fixture_in_view"] and found["fixture_text"].startswith(SYNTHETIC_TEXT), (
            "a case opened by address is shown without the synthetic line in view")
        assert found["case_heading_in_view"] and found["case_label_in_view"], (
            "the page did not scroll to the case, or its heading line lacks the synthetic label")
        assert found["pair_shown"] and found["plot_shown"] and found["note"] is None, found["note"]
    finally:
        page.close()
    probe = "no-such-case<b>x</b>"
    page, log = s.open(f"{s.url}&case={quote(probe, safe='')}", expand=False)
    try:
        assert_ready(page, log, s.base)
        other = page.evaluate(CASE_STATE)
        assert other["open"] == [True] + [False] * (len(families) - 1), f"with an unknown case: {other['open']}"
        assert other["note"] and "not in this comparison" in other["note"], f"the note reads {other['note']!r}"
        assert probe not in other["markup"] and "no-such-case" not in other["markup"], (
            "the case value of the address was written into the page")
        assert other["fixture_in_view"], "the synthetic line is not in view"
        return {"case_opened_by_address": wanted, "synthetic_line_in_view": True,
                "unknown_case": "stated, first case shown, value not written into the page"}
    finally:
        page.close()


SMALLEST_TEXT = """() => {
    let smallest = 999, where = '';
    const seen = (px, label) => { if (px < smallest) { smallest = px; where = label; } };
    for (const node of document.querySelectorAll('body *')) {
        if (node.closest('svg') || !node.checkVisibility()) continue;      // a closed fold's content is not shown
        const style = getComputedStyle(node), box = node.getBoundingClientRect();
        if (style.visibility === 'hidden' || box.right <= 0) continue;        // parked off screen for a screen reader
        const name = node.tagName.toLowerCase() + (typeof node.className === 'string' && node.className
            ? '.' + node.className.split(' ')[0] : '');
        if (Array.from(node.childNodes).some((child) => child.nodeType === 3 && child.textContent.trim())) {
            seen(parseFloat(style.fontSize), name);
        }
        for (const pseudo of ['::before', '::after']) {
            const part = getComputedStyle(node, pseudo);
            if (part.content && part.content !== 'none' && part.content !== 'normal' && part.display !== 'none'
                && /[A-Za-z0-9]/.test(part.content)) seen(parseFloat(part.fontSize), name + pseudo);
        }
    }
    return {smallest, where};
}"""
# Text only, twice the size: every element's computed font size is doubled in place. The window keeps its
# width, so this is what a reader's 200 % text setting asks of the layout.
DOUBLE_TEXT = """() => {
    const nodes = Array.from(document.body.querySelectorAll('*')).filter((node) => !(node instanceof SVGElement));
    const sizes = nodes.map((node) => parseFloat(getComputedStyle(node).fontSize));
    nodes.forEach((node, i) => node.style.setProperty('font-size', (sizes[i] * 2) + 'px', 'important'));
    return nodes.length;
}"""


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


def check_text_size(s: Session) -> dict[str, Any]:
    """With every fold open, no visible text is smaller than ``MIN_TEXT_PX``, at 1280 px and at 390 px. Labels a
    stylesheet prints (the label above a value in the narrow layout) are read too."""
    found = {}
    for name, phone in (("1280", False), ("390", True)):
        page, _ = s.open(phone=phone)
        try:
            text = page.evaluate(SMALLEST_TEXT)
            assert text["smallest"] >= MIN_TEXT_PX, (
                f"at {name} px the smallest visible text is {text['smallest']} px ({text['where']}), below "
                f"{MIN_TEXT_PX}")
            found[f"smallest_px_at_{name}"] = text["smallest"]
        finally:
            page.close()
    return {**found, "floor_px": MIN_TEXT_PX}


def check_text_zoom(s: Session) -> dict[str, Any]:
    """At 390 px with every text size doubled the page does not scroll sideways: as it loads, and with every
    fold open."""
    found = {}
    for name, expand in (("as_loaded", False), ("every_fold_open", True)):
        page, _ = s.open(phone=True, expand=expand)
        try:
            changed = page.evaluate(DOUBLE_TEXT)
            assert changed > 50, f"only {changed} elements were resized"
            found[name] = assert_no_overflow(page)["scroll_width"]
        finally:
            page.close()
    return {"text_scale": 2, "window_width": 390, "scroll_width": found}


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
    behaviour_rows: document.querySelectorAll('[data-kind^="behavior"], [data-kind="dotplot"]').length,
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


def detect_older_bundle(s: Session) -> dict[str, Any]:
    """A bundle without the fields added on 2026-11-10 must render in full, keep the synthetic label beside
    every family, and print "not in this bundle" in each place those fields have. Nothing may be filled in."""
    page, log = s.open()
    try:
        s.core(page, log)                                   # still a correct render of everything else
        banner = assert_banner(page, s.families)
        shown = shown_added_fields(page)
        missing = MISS + NOT_IN_BUNDLE
        assert len(shown["variants"]) == len(s.variant_inputs), "a family does not list every variant"
        for key, cells in shown["variants"].items():
            assert (cells["prompt_sha256"], cells["token_sha256"], cells["n_tokens"]) == (missing,) * 3, (
                f"{key}: without variant_inputs the cells read {cells}")
            assert cells["prompt"] == PROMPT_TEXT_ABSENT, f"{key}: the prompt cell reads {cells['prompt']!r}"
        # A bundle without the export shows no prompt text of any family, as every bundle did before it.
        prompts = [entry["prompt"] for family in s.protocol["case_families"] for entry in family["variants"].values()]
        leaked = [number for number, prompt in enumerate(prompts) if prompt and prompt in shown["text"]]
        assert prompts and not leaked, f"the page shows the text of {len(leaked)} fixture prompts"
        assert page.evaluate("() => document.querySelectorAll('[data-kind=\"text-basis\"], "
                             "[data-kind=\"text-placeholder\"], [data-kind=\"target-basis\"]').length") == 0, (
            "a basis line is shown for text the bundle does not hold")
        targets = page.evaluate("""() => Array.from(document.querySelectorAll('[data-kind="target-note"]')).map(
            (node) => [node.dataset.targetText, node.innerText])""")
        assert targets and all(state == "absent" and TARGET_TEXT_ABSENT in note for state, note in targets), (
            "a bundle without target text does not say that the target text is not exported")
        named = sorted({target["text"] for family in s.protocol["case_families"] for target in family["targets"]})
        assert not [text for text in named if text in page.locator("#exp-families").inner_text()], (
            "the page shows target text the bundle does not hold")
        unit = page.evaluate("() => document.getElementById('exp-endpoint-unit').innerText")
        assert f"its size is {NOT_IN_BUNDLE}" in unit, f"without vocabulary_size the unit line reads {unit!r}"
        assert shown["preprocessing"] == [missing] * s.families, f"preprocessing reads {shown['preprocessing']}"
        assert shown["preprocessing_source"] == [], "a source is shown for a mode the bundle does not carry"
        assert (shown["executed"], shown["reused"]) == (EXECUTED_ABSENT, REUSED_ABSENT), (
            f"executed and reused read ({shown['executed']!r}, {shown['reused']!r})")
        return {"synthetic_banners": banner, "variant_cells": missing, "executed": shown["executed"],
                "reused": shown["reused"], "prompt_text_on_page": 0,
                "added_fields_assertion_rejects": rejected(lambda: assert_added_fields(
                    page, s.protocol, s.variant_inputs, s.preprocessing, s.journal_counts))}
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
            # The refusal is short. The address syntax is in docs/experiment_interface/preview.md, not here.
            shown = page.locator("main").inner_text()
            syntax = [needle for needle in DEVELOPER_SYNTAX if needle in shown]
            assert len(state["messages"]) == 2 and not syntax, f"{label}: refusal reads {state['messages']} {syntax}"
            assert state["links"] == [["./", "See the published comparisons", False]], f"{label}: {state['links']}"
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
                "dot_assertion_rejects": rejected(lambda: assert_dots(page, s.behavior, s.bundle)),
                "ica_assertion_rejects": rejected(lambda: assert_ica(page, s.ica, s.basis_sha256))}
    finally:
        page.close()


def disagreeing_bundle(bundle: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """A copy in which two comparison blocks of the first family record different values for one wording: the
    target-token probability, a readout rank and an ICA score of the wording that is ``b`` in the first
    comparison and ``a`` in the second. Returns the copy and what was changed."""
    doc = copy.deepcopy(dict(bundle))
    first, second = doc["comparisons"][0]["comparisons"][:2]
    if first["b"] != second["a"]:
        raise ValueError("the fixture's first two comparisons no longer share a wording")
    target = second["behavior"]["targets"][0]
    target["a"] = target["a"] / 2 + 0.25
    method = sorted(name for name, block in second["readout"].items() if block.get("status") == "computed")[0]
    layer = second["readout"][method]["layers"][0]
    layer["targets"][0]["a"]["raw_rank"] += 1
    component = second["ica"]["layers"][0]["components"][0]
    component["score_a"] += 1.0
    return doc, {"family": doc["comparisons"][0]["family_id"], "wording": second["a"],
                 "target": target["target_id"], "method": method, "layer": str(layer["layer"]),
                 "readout_target": layer["targets"][0]["target_id"], "component": str(component["component"])}


def detect_disagreeing_blocks(s: Session, changed: Mapping[str, str]) -> dict[str, Any]:
    """A wording's value is printed once although two comparison blocks record it. When the two records differ
    the page must print neither and say so; it must not pick one."""
    page, _ = s.open()
    try:
        assert page_state(page)["state"] == "ready", "the page did not render the bundle"
        rows = table_rows(page)
        dot = keyed(rows["behavior-variant"], "family", "variant", "target")[
            (changed["family"], changed["wording"], changed["target"])]
        assert dot["probability"] == MISS + CONFLICT, f"the probability cell reads {dot['probability']!r}"
        drawn = page.evaluate("""(key) => document.querySelectorAll('[data-kind="behavior-variant"][data-family="' +
            key.family + '"][data-variant="' + key.wording + '"][data-target="' + key.target +
            '"] [data-kind="dot"]').length""", dict(changed))
        assert drawn == 0, "a dot is drawn for a value two blocks disagree on"
        rank = keyed(rows["readout"], "family", "method", "variant", "layer", "target")[
            (changed["family"], changed["method"], changed["wording"], changed["layer"], changed["readout_target"])]
        assert rank["raw"] == MISS + CONFLICT, f"the raw rank cell reads {rank['raw']!r}"
        score = keyed(rows["ica-wording"], "family", "layer", "component")[
            (changed["family"], str(ICA_LAYER), changed["component"])]
        assert score[f"score@{changed['wording']}"] == MISS + CONFLICT, f"the score cell reads {score}"
        return {"cells_that_say_two_blocks_disagree": 3,
                "behaviour_assertion_rejects": rejected(lambda: assert_behavior(page, s.behavior))}
    finally:
        page.close()


def check_partial_target(s: Session) -> dict[str, Any]:
    """A target that spans two tokens. The fixture backend's targets are single tokens, so the state is put on
    the page by an alteration: a copy of the built bundle in which the primary target of the first marked
    family says ``n_tokens`` 2 and ``partial_token_endpoint`` true. The value is unchanged and still equals the
    fixture's; what must change is what the page says the value is a probability of."""
    family, target = TARGET_FAMILIES[0], s.bundle["protocol"]["primary_endpoint"]["target"]
    s.write(with_partial_target(s.bundle, family, target))
    s.alteration("a_target_of_two_tokens_is_shown_as_the_first_token_of_the_target",
                 f"{family} {target}: n_tokens set to 2 and partial_token_endpoint to true in a copy of the bundle")
    try:
        page, log = s.open()
        try:
            assert_ready(page, log, s.base)
            detail = assert_target_text(page, s.protocol, partial=(family, target))
            assert_behavior(page, s.behavior)          # the value itself is the fixture's, unchanged
            return {**detail, "altered": f"{family} {target}", "values_unchanged": True,
                    "input": "an alteration of a display state in the temporary tree; not a run"}
        finally:
            page.close()
    finally:
        s.restore()


def all_states_bundle(bundle: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """A copy of ``bundle`` whose planned methods are in six different run statuses, and what each method must
    then show: ``{method: {state: tasks}}``.

    The fixture run gives completed, unsupported and unavailable. Here ``logit_lens`` is made ``failed`` and
    ``ica_lens`` is split between ``invalid`` and ``not_run``: their payload records are removed, a record of
    their states is added, and their blocks in every case say the same. The reasons are placeholder
    sentences. Raises ``ValueError`` when the bundle does not have those two methods completed."""
    doc = copy.deepcopy(dict(bundle))
    planned = {method: row["total"] for method, row in doc["plan_totals"]["by_method"].items()}
    done = {payload["method"] for payload in doc["provenance"]["payloads"]}
    if not {"logit_lens", "ica_lens", "behavior_next_token"} <= done:
        raise ValueError("the fixture bundle no longer completes behavior_next_token, logit_lens and ica_lens")
    doc["provenance"]["payloads"] = [p for p in doc["provenance"]["payloads"]
                                     if p["method"] not in ("logit_lens", "ica_lens")]
    invalid = planned["ica_lens"] // 2
    reasons = {"failed": "placeholder reason: the attempt raised an error",
               "invalid": "placeholder reason: the result did not pass validation",
               "not_run": "placeholder reason: no attempt is recorded"}
    doc["methods_not_run"] += [
        {"method": "logit_lens", "reasons": [reasons["failed"]], "states": {"failed": planned["logit_lens"]}},
        {"method": "ica_lens", "reasons": [reasons["invalid"], reasons["not_run"]],
         "states": {"invalid": invalid, "not_run": planned["ica_lens"] - invalid}}]
    for family in doc["comparisons"]:
        for entry in family["comparisons"]:
            entry["readout"]["logit_lens"] = {"status": "not_computed", "states": {"a": "failed", "b": "failed"},
                                              "reasons": {"a": reasons["failed"], "b": reasons["failed"]}}
            entry["ica"] = {"status": "not_computed", "states": {"a": "invalid", "b": "not_run"},
                            "reasons": {"a": reasons["invalid"], "b": reasons["not_run"]}}
    wanted = {"behavior_next_token": {"completed": planned["behavior_next_token"]},
              "logit_lens": {"failed": planned["logit_lens"]},
              "ica_lens": {"invalid": invalid, "not_run": planned["ica_lens"] - invalid}}
    for row in bundle["methods_not_run"]:
        wanted[row["method"]] = dict(row["states"])
    return doc, wanted


STATE_MARKS = """() => ({
    key: Array.from(document.querySelectorAll('#exp-state-key dt .bdg')).map((b) => [b.textContent,
        getComputedStyle(b, '::before').content, b.getClientRects().length > 0]),
    meanings: Array.from(document.querySelectorAll('#exp-state-key dd')).map((d) => d.innerText.trim()),
    rows: Array.from(document.querySelectorAll('#exp-methods-body tr[data-method]')).map((tr) => [tr.dataset.method,
        Array.from(tr.querySelectorAll('td[data-col="state"] .ln')).map((line) => [line.dataset.state,
            line.querySelector('.bdg').textContent, getComputedStyle(line.querySelector('.bdg'), '::before').content,
            line.innerText.trim().replace(/\\s+/g, ' ')])]),
    cases: Array.from(document.querySelectorAll('#exp-families [data-kind="not-computed"]')).map((li) => [
        li.dataset.family, li.dataset.method, Array.from(li.querySelectorAll('[data-col="state"]')).map((b) => b.textContent)]),
})"""


def check_each_state(s: Session) -> dict[str, Any]:
    """Failed, invalid, not run, unsupported, unavailable and completed are six different things on the page.

    A copy of the bundle with a method in each state is served (an alteration of display states). The run
    status table must give every method its own states with the task counts, each state must carry its own
    word and its own mark, the key above the table must define all six, and every case must name the state of
    each method that has no result there. A missing state is covered by its own defect check."""
    altered, wanted = all_states_bundle(s.bundle)
    s.write(altered)
    s.alteration("each_run_status_is_shown_as_its_own_state",
                 "logit_lens made failed and ica_lens split between invalid and not_run in a copy of the bundle")
    try:
        page, log = s.open()
        try:
            assert page_state(page)["state"] == "ready" and not log.page_errors, "the page did not render the copy"
            found = page.evaluate(STATE_MARKS)
            key = {word: mark for word, mark, _shown in found["key"]}
            assert sorted(key) == sorted(EXECUTION_STATES) and all(shown for _w, _m, shown in found["key"]), (
                f"the key above the table defines {sorted(key)}")
            assert len(set(key.values())) == len(EXECUTION_STATES) and "none" not in key.values(), (
                f"two run statuses share a mark, or one has none: {key}")
            assert len(found["meanings"]) == len(EXECUTION_STATES) and len(set(found["meanings"])) == len(
                EXECUTION_STATES) and all(found["meanings"]), "a run status has no meaning of its own in the key"
            shown = {method: lines for method, lines in found["rows"]}
            assert set(shown) == set(wanted), f"methods listed {sorted(shown)}"
            seen: dict[str, str] = {}
            for method, states in wanted.items():
                planned = sum(states.values())
                got = {state: (word, mark, text) for state, word, mark, text in shown[method]}
                assert set(got) == set(states), f"{method}: states shown {sorted(got)}, the copy records {sorted(states)}"
                for state, tasks in states.items():
                    word, mark, text = got[state]
                    assert word == state and mark == key[state], f"{method}: {state} is marked {word!r} {mark!r}"
                    assert text == f"{state} {tasks} of {planned} tasks", f"{method}: the line reads {text!r}"
                    seen[state] = mark
            assert sorted(seen) == sorted(EXECUTION_STATES), f"states on the page: {sorted(seen)}"
            in_cases = {(family, method): states for family, method, states in found["cases"]}
            for family in s.protocol["case_families"]:
                fid = family["family_id"]
                assert in_cases.get((fid, "logit_lens")) == ["failed"], f"{fid}: logit_lens reads {in_cases.get((fid, 'logit_lens'))}"
                assert in_cases.get((fid, "ica_lens")) == ["invalid", "not_run"], (
                    f"{fid}: ica_lens reads {in_cases.get((fid, 'ica_lens'))}")
                assert in_cases.get((fid, "j_lens")) == ["unsupported"] and in_cases.get((fid, "jpp")) == [
                    "unavailable"], f"{fid}: an untouched method changed"
            values = page.evaluate("() => document.querySelectorAll('#exp-families [data-kind=\"readout\"], "
                                   "#exp-families [data-kind=\"ica\"], #exp-families [data-kind=\"ica-wording\"]').length")
            assert values == 0, "values are shown for a method that did not complete"
            return {"states_shown": sorted(seen), "marks": key, "methods": {m: wanted[m] for m in sorted(wanted)},
                    "input": "an alteration of display states in the temporary tree; not a run"}
        finally:
            page.close()
    finally:
        s.restore()


def zero_and_missing_bundle(bundle: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """A copy of ``bundle`` in which, for the primary target of the first comparison of the first case, the
    first wording's probability is exactly 0 and the difference is absent (null). Returns the copy and the
    family, comparison, target and wording that were changed. The first wording of the first comparison is in
    no other comparison of the fixture, so no second block disagrees with the zero."""
    doc = copy.deepcopy(dict(bundle))
    family = doc["comparisons"][0]
    entry = family["comparisons"][0]
    primary = doc["protocol"]["primary_endpoint"]["target"]
    target = next(t for t in entry["behavior"]["targets"] if t["target_id"] == primary)
    if any(entry["a"] in (other["a"], other["b"]) for other in family["comparisons"][1:]):
        raise ValueError("the first wording of the fixture's first comparison is now in a second comparison")
    target["a"], target["difference_a_minus_b"] = 0.0, None
    return doc, {"family": family["family_id"], "comparison": entry["comparison_id"], "target": primary,
                 "wording": entry["a"]}


def check_zero_and_missing(s: Session) -> dict[str, Any]:
    """A zero and a missing value never share a form. In a served copy one probability is exactly 0 and one
    difference is null: the zero is printed as 0.0000 with a dot at the left end of the axis, and the missing
    difference is a dash with words and no digit. In the unaltered bundle a difference of exactly zero reads
    0 with "no difference"."""
    altered, changed = zero_and_missing_bundle(s.bundle)
    s.write(altered)
    s.alteration("a_zero_and_a_missing_value_are_shown_differently",
                 f"{changed['family']} {changed['comparison']} {changed['target']}: probability of {changed['wording']} "
                 "set to 0 and the difference set to null in a copy of the bundle")
    try:
        page, log = s.open()
        try:
            assert page_state(page)["state"] == "ready" and not log.page_errors, "the page did not render the copy"
            rows = table_rows(page)
            zero = keyed(rows["behavior-variant"], "family", "variant", "target")[
                (changed["family"], changed["wording"], changed["target"])]
            missing = keyed(rows["behavior-diff"], "family", "comparison", "target")[
                (changed["family"], changed["comparison"], changed["target"])]
            assert zero["probability"] == fmt_plain(0.0) == "0.0000", f"a zero probability reads {zero['probability']!r}"
            dot = page.evaluate("""(key) => { const row = document.querySelector('[data-kind="behavior-variant"]'
                + '[data-family="' + key.family + '"][data-variant="' + key.wording + '"][data-target="' + key.target + '"]');
                const dot = row.querySelector('[data-kind="dot"]'), track = row.querySelector('.dp-t');
                return dot ? dot.getBoundingClientRect().left + dot.getBoundingClientRect().width / 2
                    - track.getBoundingClientRect().left : null; }""", dict(changed))
            assert dot is not None and abs(dot) <= 1.0, f"the dot of a zero probability is {dot} px from the left end"
            assert missing["difference"].startswith(MISS) and not any(ch.isdigit() for ch in missing["difference"]), (
                f"a missing difference reads {missing['difference']!r}")
            assert missing["sign"].startswith(MISS) and "no difference" not in missing["sign"], (
                f"a missing difference is described as {missing['sign']!r}")
            assert missing["difference"] != "0" and zero["probability"] != missing["difference"]
            return {"zero_probability_shown_as": zero["probability"], "missing_difference_shown_as": missing["difference"],
                    "missing_sign_shown_as": missing["sign"], "dot_offset_from_zero_px": round(dot, 2),
                    "input": "an alteration of display states in the temporary tree; not a run"}
        finally:
            page.close()
    finally:
        s.restore()


def flipped_sign_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """A copy in which one recorded difference has the opposite sign and nothing else is changed. The two
    probabilities are the fixture's, so only a check of the sign and of the order can notice it."""
    doc = copy.deepcopy(dict(bundle))
    for family in doc["comparisons"]:
        for entry in family["comparisons"]:
            for target in entry["behavior"]["targets"]:
                if abs(target["difference_a_minus_b"]) > 0.01:
                    target["difference_a_minus_b"] = -target["difference_a_minus_b"]
                    return doc
    raise ValueError("the fixture bundle holds no difference large enough to flip")


def detect_flipped_sign(s: Session) -> dict[str, Any]:
    page, _ = s.open()
    try:
        assert page_state(page)["state"] == "ready", "the page did not render the bundle"
        return {"behaviour_assertion_rejects": rejected(lambda: assert_behavior(page, s.behavior))}
    finally:
        page.close()


def check_focus(s: Session) -> dict[str, Any]:
    """Tab, from the top of a loaded comparison, reaches the main controls in reading order, and each shows a
    focus outline when it has the focus."""
    page, _ = s.open(expand=False)
    try:
        return assert_focus(tab_stops(page), MAIN_CONTROLS)
    finally:
        page.close()


NAV_STATE = """() => {
    const nav = document.querySelector('.masthead nav'), more = nav.querySelector('details.nav-more');
    const list = more.querySelector('.nav-more-list'), box = list.getBoundingClientRect();
    return {
        primary: Array.from(nav.children).filter((n) => n.tagName === 'A').map((a) => [a.textContent.trim(), a.getAttribute('href')]),
        open: more.open,
        summary: more.querySelector('summary').textContent.trim(),
        more: Array.from(list.querySelectorAll('a')).map((a) => [a.textContent.trim(), a.getAttribute('href'),
            a.checkVisibility()]),
        list_inside_window: !list.checkVisibility() || (box.left >= 0 && box.right <= window.innerWidth + 0.5),
        focus_in_list: !!document.activeElement.closest('.nav-more-list'),
        focus_on_summary: document.activeElement === more.querySelector('summary'),
        outline: getComputedStyle(document.activeElement).outlineStyle,
        skip_first: document.body.firstElementChild.className,
        scroll: [document.documentElement.scrollWidth, window.innerWidth],
    };
}"""
# The primary navigation follows the research journey; everything else is in one disclosure.
NAV_PRIMARY = [["Start here", "../start-here/"], ["Scenarios", "../simulated-scenarios/"], ["Results", "../results/"],
               ["Methods", "../methods.html"]]
NAV_MORE = ("Wording differences", "Dialect differences", "Translation", "LLM responses", "Multi-turn",
            "Phrase dataset", "Technical", "Clinical brief", "GitHub")


def check_navigation(s: Session) -> dict[str, Any]:
    """The masthead navigation: four links for the journey, the supporting pages in one disclosure.

    The disclosure is a ``details`` element. It is closed on load, opens with Enter on its summary, and Tab
    then moves into its links, with JavaScript on and with JavaScript off. At 390 px its list stays inside the
    window. This page is not linked from the navigation while its index is empty."""
    found: dict[str, Any] = {}
    for name, context in (("with_javascript", s.desktop), ("without_javascript", s.plain), ("at_390_px", s.phone)):
        page = context.new_page()
        try:
            page.goto(page_url(s.base), wait_until="load", timeout=30_000)
            first = page.evaluate(NAV_STATE)
            assert first["primary"] == NAV_PRIMARY, f"{name}: the primary navigation is {first['primary']}"
            assert not first["open"] and first["summary"] == "More" and first["skip_first"] == "skip", (
                f"{name}: the disclosure is open on load, or is named {first['summary']!r}")
            assert [label for label, _href, _shown in first["more"]] == list(NAV_MORE), (
                f"{name}: the disclosure lists {[label for label, _h, _s in first['more']]}")
            assert not any(shown for _label, _href, shown in first["more"]), f"{name}: a closed disclosure shows links"
            hrefs = [href for _label, href in first["primary"]] + [href for _label, href, _shown in first["more"]]
            assert not [href for href in hrefs if "experiments" in href], f"{name}: the navigation links this page"
            page.focus(".masthead nav details.nav-more > summary")
            page.keyboard.press("Shift+Tab")
            page.keyboard.press("Tab")
            focused = page.evaluate(NAV_STATE)
            assert focused["focus_on_summary"] and focused["outline"] == "solid", (
                f"{name}: Tab does not put a visible focus on the disclosure: {focused['outline']}")
            page.keyboard.press("Enter")
            opened = page.evaluate(NAV_STATE)
            assert opened["open"] and all(shown for _label, _href, shown in opened["more"]), (
                f"{name}: Enter on the summary did not show the links")
            assert opened["list_inside_window"] and opened["scroll"][0] <= opened["scroll"][1], (
                f"{name}: the open list leaves the window: {opened['scroll']}")
            page.keyboard.press("Tab")
            inside = page.evaluate(NAV_STATE)
            assert inside["focus_in_list"] and inside["outline"] == "solid", f"{name}: Tab does not enter the open list"
            page.focus(".masthead nav details.nav-more > summary")
            page.keyboard.press("Enter")
            assert not page.evaluate(NAV_STATE)["open"], f"{name}: Enter did not close the disclosure"
            found[name] = "closed on load; opens and closes with Enter; Tab enters the list"
        finally:
            page.close()
    return {**found, "primary": [label for label, _href in NAV_PRIMARY], "supporting": len(NAV_MORE)}


COLOURS = """(alert) => {
    const main = document.querySelector('main');
    const shown = (node) => node.checkVisibility();
    const alerts = [];
    for (const node of main.querySelectorAll('*')) {
        if (!shown(node)) continue;
        const style = getComputedStyle(node);
        const border = parseFloat(style.borderTopWidth) > 0 || parseFloat(style.borderLeftWidth) > 0;
        if (style.color === alert || style.backgroundColor === alert
            || (border && (style.borderTopColor === alert || style.borderLeftColor === alert))) {
            alerts.push(node.tagName.toLowerCase() + (typeof node.className === 'string' && node.className
                ? '.' + node.className.split(' ')[0] : ''));
        }
    }
    const colours = (selector) => Array.from(new Set(Array.from(main.querySelectorAll(selector)).filter(shown).map(
        (node) => getComputedStyle(node).color)));
    return {
        alerts,
        ink: getComputedStyle(document.body).color,
        values: colours('[data-kind="behavior-variant"] [data-col="probability"]'),
        differences: colours('tr[data-kind="behavior-diff"] td, tr[data-kind="behavior-diff"] td *, '
            + 'tr[data-kind="ica"] td, tr[data-kind="ica"] td *'),
        states: colours('#exp-methods-body .bdg, #exp-state-key .bdg, [data-kind="not-computed"] [data-col="state"]'),
        dots: Array.from(main.querySelectorAll('[data-kind="behavior-variant"]')).map((row) => [row.dataset.variant,
            getComputedStyle(row.querySelector('[data-kind="dot"]')).borderTopColor,
            getComputedStyle(row.querySelector('[data-kind="dot"]')).backgroundColor,
            row.querySelector('[data-col="variant"]').innerText.trim()]),
    };
}"""


def check_colours(s: Session) -> dict[str, Any]:
    """No result is coloured as right or wrong. With every fold of a rendered comparison open: values,
    differences and run statuses are in the page's ink (or its muted grey for a missing value); the medical
    wording's mark is the green and the everyday wording's the ink that the engine's figures use, each beside
    its printed name; and nothing shows the alert colour, which is kept for a file that failed to load."""
    page, _ = s.open()
    try:
        found = page.evaluate(COLOURS, ALERT_COLOUR)
        assert not found["alerts"], f"the alert colour is shown in a rendered comparison: {found['alerts'][:4]}"
        neutral = {found["ink"], MUTED_COLOUR}
        for name in ("values", "differences", "states"):
            assert found[name] and set(found[name]) <= neutral, f"{name} are coloured {found[name]}"
        marks: dict[str, set[str]] = {}
        for variant, border, _fill, name in found["dots"]:
            assert name == wording_label(variant), f"a mark of {variant!r} stands beside the name {name!r}"
            marks.setdefault(variant, set()).add(border)
        for variant, colour in WORDING_COLOURS.items():
            assert marks.get(variant) == {colour}, f"the mark of {variant!r} is coloured {marks.get(variant)}"
        assert ALERT_COLOUR not in {colour for colours in marks.values() for colour in colours}
        return {"alert_colour_elements": 0, "value_and_difference_colours": sorted(neutral & set(
            found["values"] + found["differences"])), "wording_marks": {v: sorted(c) for v, c in sorted(marks.items())}}
    finally:
        page.close()


def check_old_section_link_opens_its_fold(s: Session) -> dict[str, Any]:
    """``#protocol`` was a section and is now inside a fold. A link to it must still show the protocol."""
    page, _ = s.open(s.url + "#protocol", expand=False)
    try:
        opened = page.evaluate("""() => ({open: document.getElementById('protocol').open,
            visible: document.querySelector('#exp-protocol dd[data-col="protocol_id"]').getClientRects().length > 0})""")
        assert opened == {"open": True, "visible": True}, f"#protocol: {opened}"
        return {"anchor": "#protocol", "fold_opened": True}
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


# -- reference links

RECORD_STATE = """() => Array.from(document.querySelectorAll('#exp-links [data-kind="link-record"]')).map((box) => {
    const shown = (node) => !!node && node.getClientRects().length > 0;
    const read = (selector) => { const node = box.querySelector(selector); return node ? node.textContent : null; };
    return {
        verified: box.dataset.verified,
        kind: box.dataset.linkKind || null,
        cls: box.className,
        border: getComputedStyle(box).borderTopStyle,
        children: Array.from(box.children).map((n) => n.tagName + (n.className ? '.' + n.className.split(' ').join('.') : '')),
        paragraphs: Array.from(box.querySelectorAll('p')).map((n) => n.textContent),
        anchors: Array.from(box.querySelectorAll('a')).map((a) => ({
            href: a.getAttribute('href'), text: a.textContent, rel: a.getAttribute('rel'), cls: a.className,
            kind: a.dataset.kind || null, title: a.getAttribute('title'), target: a.getAttribute('target'),
            decoration: getComputedStyle(a).textDecorationStyle, shown: shown(a)})),
        tag: read('[data-col="reference-tag"]'),
        tag_shown: shown(box.querySelector('[data-col="reference-tag"]')),
        label: read('[data-col="reference-label"]'),
        label_shown: shown(box.querySelector('[data-col="reference-label"]')),
        read: read('[data-col="reference-read"]'),
        identity: read('[data-col="reference-identity"]'),
        no_exact: read('[data-col="reference-no-exact"]'),
        no_link: read('[data-col="no-link"]'),
        text: box.textContent,
        lists: box.querySelectorAll('dl').length,
    };
})"""


def _neuronpedia() -> Any:
    """The engine's link module, imported from the engine root."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.experiments import neuronpedia
    return neuronpedia


def fixture_link_results() -> dict[str, Any]:
    """Link results built by ``scripts.experiments.neuronpedia.link_or_fallback`` from the fixture registry:
    one exact link, one result with no link, and a reference link of each page form. Nothing is hand-written.
    Raises ``ValueError`` when the fixture registry no longer gives one of them."""
    neuronpedia = _neuronpedia()
    registry = neuronpedia.validate_registry(json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8")))
    ica = {entry["verification"]["status"]: entry for entry in registry["entries"]
           if entry["representation_type"] == "ica_component"}
    readout = next(entry for entry in registry["entries"] if entry["representation_type"] == "workspace_readout")
    alias = ica["alias_unverified_checkpoint"]
    results = {
        "exact": neuronpedia.link_or_fallback(ica["verified_exact"], 1, layer=1, record={"component": 1}),
        "none": neuronpedia.link_or_fallback(alias, 1, layer=2),
        "model_page": neuronpedia.link_or_fallback(alias, 1, layer=2, reference_page="model_page"),
        "source_page": neuronpedia.link_or_fallback(alias, 1, layer=2, reference_page="source_page"),
        "lens_page": neuronpedia.link_or_fallback(readout, 1, layer=1, reference_page="lens_page"),
    }
    wanted = {"exact": "exact", "none": "none", "model_page": "reference", "source_page": "reference",
              "lens_page": "reference"}
    kinds = {name: result["kind"] for name, result in results.items()}
    if kinds != wanted:
        raise ValueError(f"the registry fixture gives the link kinds {kinds}, expected {wanted}")
    for name in REFERENCE_PAGE_WORDS:
        if results[name]["link"] is not None or results[name]["reference"]["page"] != name:
            raise ValueError(f"the {name} result is not a reference link of that page form")
        neuronpedia.validate_reference_link(results[name]["reference"], registry)
    return {"registry": registry, "results": results, "label": neuronpedia.REFERENCE_LABEL}


def committed_reference_result() -> dict[str, Any]:
    """A reference link to a model page, built by ``link_or_fallback`` from the committed registry and its
    saved evidence files. It is the one kind of external link a real bundle can carry today. Local files are
    read; no request is made. Raises ``ValueError`` when the committed registry builds none."""
    neuronpedia = _neuronpedia()
    registry = neuronpedia.load_registry()
    for entry in registry["entries"]:
        if not neuronpedia.permissions(entry)["reference_link"]:
            continue
        if not any(page["kind"] == "model_page" for page in entry["reference"]["pages"]):
            continue
        result = neuronpedia.link_or_fallback(entry, 0, reference_page="model_page")
        if result["kind"] == "reference":
            neuronpedia.validate_reference_link(result["reference"], registry)
            return result
    raise ValueError("the committed registry builds no reference link to a model page")


def forged_reference_cases(reference: Mapping[str, Any], exact: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Records that must not become a link, each made from a valid reference result by one change.

    ``reference`` is a ``link_or_fallback`` result of kind ``reference``; ``exact`` is one of kind ``exact``.
    Each case is ``{"name", "record", "reason", "level"}``: the record to serve, the reason the page must
    print, and what was changed: ``record`` (the reference record inside the result), ``result`` (the result
    around a valid reference record) or ``bare`` (a reference record served on its own, without a result).
    """
    def changed(**fields: Any) -> dict[str, Any]:
        result = copy.deepcopy(dict(reference))
        result["reference"].update(fields)
        return result

    def without(key: str) -> dict[str, Any]:
        result = copy.deepcopy(dict(reference))
        del result["reference"][key]
        return result

    url = reference["reference"]["url"]
    path = url[len("https://"):].split("/", 1)[1]
    host = url[len("https://"):].split("/", 1)[0]
    cases = [
        ("another_host", changed(url=f"https://{REFERENCE_HOST}.registry-fixture.example/{path}"), REFUSED_HOST),
        ("service_host_without_www", changed(url=f"https://neuronpedia.org/{path}"), REFUSED_HOST),
        ("query_string", changed(url=url + "?prompt=placeholder"), REFUSED_ADDRESS),
        ("fragment", changed(url=url + "#activations"), REFUSED_ADDRESS),
        ("not_https", changed(url="http" + url[len("https"):]), REFUSED_ADDRESS),
        ("script_scheme", changed(url="javascript:alert(1)"), REFUSED_ADDRESS),
        ("exact_looking_label", changed(label="Verified link"), REFUSED_LABEL),
        ("label_is_the_address", changed(label=url), REFUSED_LABEL),
        ("label_with_a_changed_word", changed(label=reference["reference"]["label"].replace("not evidence", "evidence")),
         REFUSED_LABEL),
        ("missing_label", without("label"), REFUSED_NO_LABEL),
        ("empty_label", changed(label=""), REFUSED_NO_LABEL),
        ("record_kind_exact", changed(kind="exact"), REFUSED_KIND),
        ("feature_page_form", changed(page="feature_page"), REFUSED_PAGE),
        ("path_of_a_feature_page", changed(url=f"https://{host}/{path}/2-placeholder-set/7"), REFUSED_PATH),
        ("reason_of_an_exact_link", changed(reason=exact["reason"]), REFUSED_REASON),
        ("no_date_read", changed(read_utc_date=None), REFUSED_DATE),
        ("unknown_identity_status", changed(identity_status="verified"), REFUSED_STATUS),
    ]
    out = [{"name": name, "record": record, "reason": reason, "level": "record"} for name, record, reason in cases]
    out.append({"name": "result_kind_exact", "record": dict(copy.deepcopy(dict(reference)), kind="exact"),
                "reason": REFUSED_RESULT_KIND, "level": "result"})
    out.append({"name": "result_with_a_link_string_as_well",
                "record": dict(copy.deepcopy(dict(reference)), link=exact["link"]), "reason": REFUSED_BOTH,
                "level": "result"})
    bare = copy.deepcopy(dict(reference["reference"]))
    bare["url"] = f"https://{REFERENCE_HOST}.registry-fixture.example/{path}"
    out.append({"name": "bare_record_with_another_host", "record": bare, "reason": REFUSED_BARE + REFUSED_HOST,
                "level": "bare"})
    return out


def with_link_records(bundle: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
                      component_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of ``bundle`` with ``records`` under the first comparison's ``references.registry.neuronpedia``
    and, when given, ``component_record`` beside the second ICA component of its first layer. These are the
    two places the page reads a link record from; the bundle contract names neither."""
    doc = copy.deepcopy(dict(bundle))
    entry = doc["comparisons"][0]["comparisons"][0]
    entry["references"]["registry"] = {"status": "reference_only", "neuronpedia": [dict(r) for r in records]}
    if component_record is not None:
        entry["ica"]["layers"][0]["components"][1]["neuronpedia"] = dict(component_record)
    return doc


def assert_reference_box(box: Mapping[str, Any], result: Mapping[str, Any], label: str) -> None:
    """One rendered record is a reference link: marked as one, with the fixed label in full beside it, the date
    read and the identity status, and never marked or worded as a verified link."""
    record = result["reference"]
    name = record["page"]
    assert (box["kind"], box["verified"]) == ("reference", "false"), f"{name}: marked {box['kind']!r}, {box['verified']!r}"
    assert "lnk-ref" in box["cls"].split() and box["border"] == "dashed", f"{name}: box {box['cls']!r} {box['border']!r}"
    assert len(box["anchors"]) == 1, f"{name}: {len(box['anchors'])} links in the record"
    link = box["anchors"][0]
    assert link["href"] == record["url"] and link["shown"], f"{name}: the link goes to {link['href']!r}"
    assert link["text"] == f"{REFERENCE_LINK_TEXT}: {REFERENCE_PAGE_WORDS[name]}, {record['url']}", (
        f"{name}: the link text is {link['text']!r}")
    assert (link["kind"], link["rel"], link["target"], link["title"]) == ("reference-link", EXACT_LINK_REL, None, None), (
        f"{name}: link attributes {link}")
    assert link["decoration"] == "dashed", f"{name}: the link is underlined {link['decoration']!r}, as a verified link is"
    words = link["text"][:link["text"].index(record["url"])].lower()
    used = [word for word in NOT_IN_REFERENCE_LINK_TEXT if word in words]
    assert not used, f"{name}: the link text uses {used}"
    assert box["tag"] == REFERENCE_TAG and box["tag_shown"], f"{name}: the tag reads {box['tag']!r}"
    assert box["label"] == label == record["label"] and box["label_shown"], f"{name}: the fixed label is not shown in full"
    assert box["read"] == record["read_utc_date"], f"{name}: date read {box['read']!r}"
    assert box["identity"] == record["identity_status"], f"{name}: identity status {box['identity']!r}"
    assert box["no_exact"] is not None and result["reason"] in box["no_exact"], (
        f"{name}: the reason there is no verified link is not shown")
    assert box["no_link"] is None and EXACT_LINK_PREFIX not in box["text"], f"{name}: shown as another kind of record"


def assert_refused_box(box: Mapping[str, Any], reason: str, name: str) -> None:
    """One rendered record shows no link, with the reason."""
    assert (box["kind"], box["verified"]) == ("none", "false"), f"{name}: marked {box['kind']!r}, {box['verified']!r}"
    assert box["anchors"] == [], f"{name}: a link is shown: {box['anchors']}"
    assert box["no_link"] is not None and box["no_link"].startswith(NO_LINK_PREFIX), f"{name}: no no-link line"
    assert reason in box["no_link"], f"{name}: the no-link line lacks its reason: {box['no_link'][-160:]!r}"
    assert "lnk-ref" not in box["cls"].split() and box["label"] is None and box["tag"] is None, (
        f"{name}: a refused record carries reference marks")


def check_reference_records(s: Session, recorder: Recorder) -> None:
    """Reference links beside an exact link and a record with no link, all built by the engine's link builder
    from its fixture registry. Three checks read one render at 1280 px and one at 390 px."""
    names = ("a_reference_record_renders_as_a_reference_with_the_fixed_label",
             "a_reference_record_is_never_rendered_as_a_verified_link",
             "an_exact_record_and_a_record_with_no_link_render_as_before")
    collected: dict[str, Any] = {}

    def collect() -> None:
        built = fixture_link_results()
        results = built["results"]
        s.write(with_link_records(s.bundle, [results[name] for name in ("model_page", "source_page", "lens_page",
                                                                         "none")], results["exact"]))
        try:
            page, log = s.open()
            try:
                assert_ready(page, log, s.base)
                collected.update(built, boxes=page.evaluate(RECORD_STATE), note=page.evaluate(
                    "() => document.querySelector('#exp-links p.note').textContent"),
                    page_label=page.evaluate("() => window.pwExperimentViewer.referenceLabel"),
                    anchors=page.evaluate(LINK_STATE)["anchors"])
                collected["focus"] = None
                if page.evaluate("() => { const a = document.querySelector('#exp-links a.ref-a'); if (a) a.focus(); "
                                 "return !!a; }"):
                    page.keyboard.press("Shift+Tab")
                    page.keyboard.press("Tab")
                    collected["focus"] = page.evaluate("""() => ({
                        on_reference_link: document.activeElement === document.querySelector('#exp-links a.ref-a'),
                        outline: getComputedStyle(document.activeElement).outlineStyle})""")
            finally:
                page.close()
            page, log = s.open(phone=True)
            try:
                assert_ready(page, log, s.base)
                collected["phone"] = dict(assert_no_overflow(page), boxes=page.evaluate(RECORD_STATE))
            finally:
                page.close()
        finally:
            s.restore()

    try:
        collect()
    except SetupProblem:
        raise
    except Exception as exc:
        failure = exc

        def not_collected() -> None:
            raise failure
        for name in names:
            recorder.run(name, not_collected)
        return
    results, boxes, label = collected["results"], collected["boxes"], collected["label"]
    order = ("model_page", "source_page", "lens_page", "none", "exact")

    def renders() -> dict[str, Any]:
        assert len(boxes) == len(order), f"{len(boxes)} records rendered, {len(order)} served"
        assert collected["page_label"] == label, "the page's label sentence is not the engine's REFERENCE_LABEL"
        for name, box in zip(order[:3], boxes[:3]):
            assert_reference_box(box, results[name], label)
        assert "reference page" in collected["note"].lower() and "not a link to the study" in collected["note"], (
            "the note above the records does not say what a reference page is")
        assert collected["focus"] == {"on_reference_link": True, "outline": "solid"}, (
            f"Tab did not put a visible focus outline on a reference link: {collected['focus']}")
        phone = collected["phone"]
        for name, box in zip(order[:3], phone["boxes"][:3]):
            assert_reference_box(box, results[name], label)
        return {"reference_links_shown": 3, "page_forms": list(order[:3]), "fixed_label_shown_in_full": 3,
                "identity_statuses": sorted({results[name]["reference"]["identity_status"] for name in order[:3]}),
                "width_at_390": phone["scroll_width"],
                "source": "scripts.experiments.neuronpedia.link_or_fallback(reference_page=...) on the fixture "
                          "registry; each record passed validate_reference_link"}

    def never_exact() -> dict[str, Any]:
        exact_href = results["exact"]["link"]
        for name, box in zip(order[:3], boxes[:3]):
            link = box["anchors"][0]
            assert box["verified"] == "false" and box["kind"] != "exact", f"{name}: marked as a verified link"
            assert EXACT_LINK_PREFIX not in box["text"], f"{name}: the record says {EXACT_LINK_PREFIX!r}"
            assert link["text"] != link["href"] and link["href"] != exact_href, f"{name}: rendered as an exact link is"
            assert link["cls"] == "ref-a" and box["children"] != RECORD_BOX_CHILDREN, f"{name}: the exact markup"
        verified = [box for box in boxes if box["verified"] == "true"]
        assert len(verified) == 1 and verified[0] is boxes[4], f"{len(verified)} records are marked verified"
        assert sum(1 for box in boxes if EXACT_LINK_PREFIX in box["text"]) == 1, "more than one verified link line"
        return {"records_marked_verified": 1, "reference_records_marked_verified": 0}

    def as_before() -> dict[str, Any]:
        exact, none = boxes[4], boxes[3]
        link = results["exact"]["link"]
        assert (exact["kind"], exact["verified"], exact["cls"], exact["border"]) == ("exact", "true", "lnk", "solid"), exact
        assert exact["children"] == RECORD_BOX_CHILDREN and exact["lists"] == 1, f"exact record: {exact['children']}"
        assert exact["paragraphs"][1] == EXACT_LINK_PREFIX + link, f"exact record: {exact['paragraphs'][1]!r}"
        assert [(a["href"], a["text"], a["rel"], a["cls"], a["kind"], a["title"], a["target"]) for a in exact["anchors"]] == [
            (link, link, EXACT_LINK_REL, "", None, None, None)], f"exact link: {exact['anchors']}"
        assert exact["anchors"][0]["decoration"] == "solid" and exact["tag"] is None and exact["label"] is None
        assert_refused_box(none, results["none"]["reason"], "record with no link")
        assert none["children"] == RECORD_BOX_CHILDREN and none["cls"] == "lnk" and none["border"] == "solid", none
        assert none["no_link"] == f"{NO_LINK_PREFIX}{results['none']['reason']} \u00b7 {results['none']['detail']}", (
            f"record with no link: {none['no_link']!r}")
        assert collected["anchors"][-1] == [link, link], "the verified link is not the last link under External links"
        return {"exact_record": "unchanged markup and text", "record_with_no_link": "unchanged markup and text"}

    for name, action in zip(names, (renders, never_exact, as_before)):
        recorder.run(name, action)


def check_forged_reference_records(s: Session) -> dict[str, Any]:
    """Each forged record is served in the synthetic bundle and must show no link with its reason. The page's
    own rule is also asked directly, and the engine's validator must refuse every record-level forgery."""
    neuronpedia = _neuronpedia()
    built = fixture_link_results()
    valid, exact = built["results"]["model_page"], built["results"]["exact"]
    cases = forged_reference_cases(valid, exact)
    s.write(with_link_records(s.bundle, [case["record"] for case in cases]))
    try:
        page, log = s.open()
        try:
            assert_ready(page, log, s.base)
            boxes = page.evaluate(RECORD_STATE)
            assert len(boxes) == len(cases), f"{len(boxes)} records rendered, {len(cases)} served"
            assert page.evaluate(LINK_STATE)["anchors"] == [], "a forged record is shown as a link"
            rule = "([record, synthetic]) => window.pwExperimentViewer.referenceRefusal(record, synthetic)"
            assert page.evaluate(rule, [valid["reference"], True]) is None, "the page's rule refuses the valid record"
            assert page.evaluate(rule, [valid["reference"], False]) == REFUSED_HOST, (
                "the page's rule accepts a fixture host outside a synthetic bundle")
            engine_refused = 0
            for case, box in zip(cases, boxes):
                assert_refused_box(box, case["reason"], case["name"])
                if case["level"] == "result":
                    continue
                record = case["record"] if case["level"] == "bare" else case["record"]["reference"]
                direct = page.evaluate(rule, [record, True])
                assert direct is not None and direct.startswith(case["reason"].removeprefix(REFUSED_BARE)), (
                    f"{case['name']}: the page's rule says {direct!r}")
                try:
                    neuronpedia.validate_reference_link(record, built["registry"])
                except neuronpedia.Refusal:
                    engine_refused += 1
                else:
                    raise AssertionError(f"{case['name']}: the engine's validate_reference_link accepts this record")
            return {"forged_records": len(cases), "links_shown": 0,
                    "cases": [case["name"] for case in cases],
                    "also_refused_by_validate_reference_link": engine_refused}
        finally:
            page.close()
    finally:
        s.restore()


def check_reference_host_by_bundle_label(s: Session) -> dict[str, Any]:
    """In a bundle that is not labelled synthetic the only accepted host is ``www.neuronpedia.org``.

    A relabelled copy of the fixture bundle, which exists only in the temporary site, carries two reference
    results: the fixture registry's (a ``.invalid`` host) and one built from the committed registry. The first
    must show no link; the second must render as a reference. The link is not followed."""
    built = fixture_link_results()
    fixture, committed = built["results"]["model_page"], committed_reference_result()
    url = committed["reference"]["url"]
    assert url.startswith(f"https://{REFERENCE_HOST}/"), "the committed registry's reference link is on another host"
    extra = s.site / "data" / RELABELLED_PARAM
    extra.write_text(json.dumps(relabelled_as_publishable(with_link_records(s.bundle, [fixture, committed]))),
                     encoding="utf-8")
    try:
        page, log = s.open(page_url(s.base, RELABELLED_PARAM))
        try:
            state = page_state(page)
            assert state["state"] == "ready", f"page state is {state['state']!r}: {state['messages']}"
            assert not log.console_errors and not log.page_errors and not log.http_errors, "browser errors"
            assert page.evaluate("() => document.querySelectorAll('[data-kind=\"synthetic-banner\"]').length") == 0, (
                "the relabelled copy is shown as synthetic")
            boxes = page.evaluate(RECORD_STATE)
            assert len(boxes) == 2, f"{len(boxes)} records rendered, 2 served"
            assert_refused_box(boxes[0], REFUSED_HOST, "fixture host outside a synthetic bundle")
            assert_reference_box(boxes[1], committed, built["label"])
            assert page.evaluate(LINK_STATE)["anchors"] == [[url, boxes[1]["anchors"][0]["text"]]], "links shown"
            return {"fixture_host_outside_a_synthetic_bundle": "no link, with the reason",
                    "committed_registry_reference": "rendered as a reference", "host": REFERENCE_HOST,
                    "registry_id": committed["reference"]["registry_id"], "link_followed": False,
                    "input": "a relabelled copy of the fixture bundle, in the temporary tree only; not a study bundle"}
        finally:
            page.close()
    finally:
        extra.unlink()


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
    recorder.run("no_parameter_shows_the_empty_statement_and_requests_only_the_index", lambda: check_no_parameter(s))
    recorder.run("index_writer_never_lists_the_synthetic_bundle", lambda: check_index_never_lists_the_synthetic_bundle(s))
    recorder.run("index_lists_a_publishable_bundle_and_its_link_opens_it",
                 lambda: check_index_lists_a_publishable_bundle(s))
    recorder.run("forged_or_unreadable_index_links_nothing", lambda: check_forged_index_entries_are_not_linked(s))
    check_rendered_bundle(s, recorder)
    recorder.run("pair_and_primary_output_come_before_run_status_and_methods_and_source",
                 lambda: check_reading_order(s))
    recorder.run("hashes_schema_strings_and_publication_markers_are_under_methods_and_source",
                 lambda: check_machinery_placement(s))
    recorder.run("old_section_link_opens_the_fold_it_now_sits_in", lambda: check_old_section_link_opens_its_fold(s))
    recorder.run("keyboard_reaches_section_links_and_folds", lambda: check_keyboard(s))
    recorder.run("main_controls_are_reached_by_tab_and_show_a_focus_outline", lambda: check_focus(s))
    recorder.run("navigation_disclosure_opens_from_the_keyboard_with_and_without_javascript",
                 lambda: check_navigation(s))
    recorder.run("family_folds_open_from_the_keyboard_and_keep_their_labels", lambda: check_family_folds(s))
    recorder.run("a_case_opened_by_address_is_the_open_one_and_keeps_the_synthetic_label",
                 lambda: check_case_address(s))
    recorder.run("renders_at_390_px_without_horizontal_overflow", lambda: check_narrow(s))
    recorder.run("no_visible_text_is_smaller_than_12_px_at_1280_or_at_390", lambda: check_text_size(s))
    recorder.run("no_horizontal_overflow_at_390_px_with_text_at_200_percent", lambda: check_text_zoom(s))
    recorder.run("loading_state_is_shown_while_the_bundle_is_in_flight", lambda: check_loading(s))
    recorder.run("a_target_of_two_tokens_is_shown_as_the_first_token_of_the_target", lambda: check_partial_target(s))
    recorder.run("each_run_status_is_shown_as_its_own_state", lambda: check_each_state(s))
    recorder.run("a_zero_and_a_missing_value_are_shown_differently", lambda: check_zero_and_missing(s))
    recorder.run("values_and_states_are_in_ink_and_wording_marks_keep_their_identity_colours",
                 lambda: check_colours(s))

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
    run_defect(recorder, s, "older_bundle_without_the_added_fields_reads_not_in_this_bundle",
               lambda: s.write(without_added_fields(s.bundle)), lambda: detect_older_bundle(s))
    run_defect(recorder, s, "defect_traversal_parameter_is_refused_without_a_request",
               lambda: None, lambda: detect_traversal_refused(s))
    run_defect(recorder, s, "control_a_wrong_probability_and_a_flipped_score_fail_the_value_checks",
               lambda: s.write(wrong_number_bundle(s.bundle)), lambda: detect_wrong_numbers(s))
    run_defect(recorder, s, "control_a_difference_of_the_opposite_sign_fails_the_value_check",
               lambda: s.write(flipped_sign_bundle(s.bundle)), lambda: detect_flipped_sign(s))

    disagreeing, changed = disagreeing_bundle(s.bundle)
    run_defect(recorder, s, "defect_two_blocks_that_disagree_on_one_wording_show_neither_value",
               lambda: s.write(disagreeing), lambda: detect_disagreeing_blocks(s, changed))

    recorder.run("a_link_is_shown_only_for_a_verified_built_record", lambda: check_link_records(s))
    check_reference_records(s, recorder)
    recorder.run("forged_reference_records_show_no_link_with_a_reason", lambda: check_forged_reference_records(s))
    recorder.run("reference_host_is_the_service_host_outside_a_synthetic_bundle",
                 lambda: check_reference_host_by_bundle_label(s))
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


def new_context(browser: Any, origin: str, blocked: list[str], width: int, height: int, *,
                javascript: bool = True) -> Any:
    """A browser context that can reach the test server and nothing else. ``javascript`` false turns the page's
    scripts off, as a reader's browser setting would."""
    context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2,
                                  service_workers="block", java_script_enabled=javascript)

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

    protocol = marked_protocol(json.loads(PROTOCOL.read_text(encoding="utf-8")))
    behavior = expected_behavior(protocol, json.loads(LOGITS.read_text(encoding="utf-8")))
    basis_sha256 = json.loads(ICA_INDEX.read_text(encoding="utf-8"))["basis_manifest_sha256"]
    recorder = Recorder(receipt)
    real_preview = site_source / "data" / "experiment_preview"
    real_index = site_source / "data" / INDEX_FILE
    if not real_index.is_file():
        raise SetupProblem(f"the site has no data/{INDEX_FILE}; write it with scripts/export_experiment_index.py "
                           "--site SITE (the page requests it, so its absence is a failed request)")
    index_before = sha256_file(real_index)
    blocked: list[str] = receipt["browser_external_requests"]

    with tempfile.TemporaryDirectory(prefix="pw-exp-preview-") as directory:
        temp = Path(directory).resolve()
        site, work = temp / "patientwords", temp / "experiment_work"
        work.mkdir()
        copy_site(site_source, site)
        bundle_file = build_bundle(work, receipt, protocol)
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
        with_target_text = sorted(family["family_id"] for family in bundle["protocol"]["families"]
                                  if "target_text" in family)
        if with_target_text != sorted(TARGET_FAMILIES):
            raise SetupProblem(f"the bundle exports target text for {with_target_text}, expected "
                               f"{sorted(TARGET_FAMILIES)}: the bundle writer does not honour {TARGET_TEXT_MARKER!r} "
                               "as this check expects, so the target-text checks cannot run")
        receipt["bundle"] = {
            "sha256": sha256_bytes(original), "bytes": len(original), "schema_version": bundle.get("schema_version"),
            "target_text_families": with_target_text,
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
                    base=origin + "/patientwords", site=site, served=served, original=original, bundle=bundle,
                    protocol=protocol, validated=validated, behavior=behavior, ica=expected_ica(protocol),
                    basis_sha256=basis_sha256, desktop=new_context(browser, origin, blocked, 1280, 900),
                    phone=new_context(browser, origin, blocked, 390, 844), receipt=receipt, shots=shots,
                    plain=new_context(browser, origin, blocked, 1280, 900, javascript=False),
                    variant_inputs=expected_variant_inputs(protocol),
                    preprocessing=expected_preprocessing(protocol),
                    journal_counts=expected_journal_counts(receipt["cli_steps"]))
                run_browser_checks(session, recorder)

                def no_outside_request() -> dict[str, Any]:
                    assert not blocked, f"the page tried to reach {sorted(set(blocked))}"
                    return {"external_requests": 0}
                recorder.run("no_request_left_the_test_server", no_outside_request)
                session.desktop.close()
                session.phone.close()
                session.plain.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=10)

    def real_site_untouched() -> dict[str, Any]:
        assert not real_preview.exists(), "the real site holds data/experiment_preview; a fixture must never be there"
        assert not (site_source / "data" / RELABELLED_PARAM).exists(), "the relabelled fixture reached the real site"
        assert sha256_file(real_index) == index_before, "the real site's experiment index was changed"
        assert not temp.exists(), "the temporary tree was not removed"
        return {"cleanup": "temporary server stopped; copied site, run store and bundles removed",
                "real_index_sha256": index_before}
    recorder.run("real_site_untouched_and_temporary_tree_removed", real_site_untouched)
    return recorder.failed


def serve_preview(site_source: Path, port: int, wait: Callable[[], None] | None = None) -> int:
    """The development route: build the temporary copy and the synthetic bundle, serve them, print the address
    of the preview and wait until interrupted. No check runs. The copy, the run store and the bundle are
    removed when the function returns, however it returns. ``wait`` replaces the wait in tests."""
    receipt: dict[str, Any] = {"cli_steps": []}
    with tempfile.TemporaryDirectory(prefix="pw-exp-preview-") as directory:
        temp = Path(directory).resolve()
        site, work = temp / "patientwords", temp / "experiment_work"
        work.mkdir()
        copy_site(site_source, site)
        bundle_file = build_bundle(work, receipt)
        served = site / "data" / BUNDLE_PARAM
        served.parent.mkdir(parents=True)
        shutil.copyfile(bundle_file, served)
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(temp)))
        except OSError as exc:
            raise SetupProblem(f"could not listen on 127.0.0.1 port {port}: {exc}") from exc
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}/patientwords"
        families = [family["family_id"] for family in json.loads(served.read_text(encoding="utf-8"))["protocol"]["families"]]
        print("Synthetic fixture preview: not a measurement. Hand-written numbers; no model was loaded.")
        print(f"  the comparison   {page_url(base, BUNDLE_PARAM)}")
        for family in families[1:2]:
            print(f"  one case         {page_url(base, BUNDLE_PARAM)}&case={quote(family, safe='')}")
        print(f"  the empty index  {page_url(base)}")
        print("The copy of the site is temporary. Press Ctrl-C to stop the server and remove it.", flush=True)
        try:
            (wait or threading.Event().wait)()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=10)
    print("Stopped. The temporary copy was removed.")
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", type=Path, required=True, help="the patientwords site checkout")
    parser.add_argument("--browser", help="an installed Chromium executable (default: CHROMIUM, then Playwright's own)")
    parser.add_argument("--receipt", type=Path, help="write the JSON receipt here")
    parser.add_argument("--shots", type=Path, help="write screenshots into this directory")
    parser.add_argument("--serve", action="store_true",
                        help="run no check: serve the temporary copy with the synthetic bundle until interrupted")
    parser.add_argument("--port", type=int, default=0,
                        help="with --serve: the loopback port to serve on (default: an ephemeral port)")
    args = parser.parse_args(argv)
    site = args.site.resolve()
    receipt_path = args.receipt.resolve() if args.receipt else None
    browser = args.browser or os.environ.get("CHROMIUM") or None

    if args.serve:
        if not (site / PAGE).is_file():
            print(f"setup problem: {site} has no {PAGE}; nothing was served", file=sys.stderr)
            return EXIT_SETUP
        # a terminal's Ctrl-C and a plain termination both end the wait and remove the copy
        signal.signal(signal.SIGTERM, lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            return serve_preview(site, args.port)
        except SetupProblem as exc:
            print(f"setup problem: {exc}", file=sys.stderr)
            return EXIT_SETUP

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
