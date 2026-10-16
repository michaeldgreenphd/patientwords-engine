"""Independent fixture oracles for fetched artifacts and the actual series page.

Expected values are authored in tests/fixtures/frontend_boundary.json, never
computed by the exporter. These checks deliberately supplement structural
validation: a valid object assigned to the wrong model/pair must still fail.
"""
from __future__ import annotations

import math
import re
from typing import Any, TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def _equal(actual: Any, wanted: Any, label: str) -> None:
    assert actual == wanted, f"{label}: expected {wanted!r}, got {actual!r}"


def assert_semantics(payload: dict[str, Any], expected: dict[str, Any], legacy: bool = False) -> None:
    """Check identities, exact fixture values, signs, calibration and denominators."""
    scenarios = payload["scenarios"]
    _equal([[s["batch"], s["batch_index"]] for s in scenarios], expected["scenario_keys"], "pair identities")
    _equal([s["index"] for s in scenarios], list(range(1, len(scenarios) + 1)), "display identities")
    by_index = {str(s["index"]): s for s in scenarios}
    for index, fields in expected["scenarios"].items():
        for field, wanted in fields.items():
            _equal(by_index[index][field], wanted, f"pair {index} {field}")

    base = payload["traced"]["graph_model"]
    _equal(base, "gemma-2-2b", "base model")
    model_expectations = {base: expected["models"][base]} if legacy else expected["models"]
    if not legacy:
        meta = {m["id"]: m for m in payload["models_meta"]}
        _equal(set(meta), set(model_expectations), "model inventory")
        for model, wanted in model_expectations.items():
            for field in ("label", "n_traced", "source_set", "features"):
                _equal(meta[model][field], wanted[field], f"{model} metadata {field}")
            _equal(payload["traced_by_model"][model]["graph_model"], model, f"{model} provenance identity")
            _equal(payload["traced_by_model"][model]["source_set"], wanted["source_set"],
                   f"{model} provenance source")

    for model, wanted_model in model_expectations.items():
        for index, wanted in wanted_model["rows"].items():
            scenario = by_index[index]
            actual = scenario if legacy else scenario["models"].get(model)
            label = f"pair {index} model {model}"
            if wanted.get("has_model") is False:
                _equal(actual, None, f"{label} must remain unmeasured")
                continue
            assert actual is not None, f"{label}: missing measurement"
            _equal(actual["target_token"], wanted["target"], f"{label} target association")
            for field in ("prob_clinical", "prob_patient", "language_penalty"):
                _equal(actual[field], wanted[field], f"{label} {field}")
                if model == base:
                    _equal(scenario[field], wanted[field], f"pair {index} base mirror {field}")
            if "clinical_mass" in wanted:
                _equal(actual["clinical_mass"], wanted["clinical_mass"], f"{label} calibrated mass")
            if wanted["language_penalty"] is not None:
                assert math.isclose(actual["prob_patient"] - actual["prob_clinical"],
                                    actual["language_penalty"], abs_tol=1e-12), f"{label}: wrong gap sign or value"
                assert math.isclose(actual["language_penalty"] * 100, wanted["gap_percentage_points"],
                                    abs_tol=1e-12), f"{label}: wrong probability-point units"
                _equal(actual["screening"], None, f"{label} measured status")
            else:
                _equal((actual["screening"] or {}).get("status"), "screened_out", f"{label} missing status")

    summary = expected["summary"]
    for field in ("accepted", "measured", "screened_out", "flipped_base"):
        _equal(payload["summary"]["totals"][field], summary[field], f"summary denominator {field}")
    for field in ("n_scored_rows", "n_phrases", "mean_rows_raw", "mean_phrase_deduped", "ci95"):
        _equal(payload["summary"]["penalty"][field], summary[field], f"summary penalty {field}")


def _assert_indices(page: Page, indices: list[int]) -> None:
    from playwright.sync_api import expect

    links = page.locator("#sim-sum-body").get_by_role("link", name=re.compile(r"^Sim \d+"))
    expect(links).to_have_count(len(indices))
    actual = [int(parse_qs(urlsplit(link.get_attribute("href") or "").query)["sim"][0])
              for link in links.all()]
    _equal(actual, indices, "visible pair identities")


def _row(page: Page, index: int) -> Locator:
    return page.locator("#sim-sum-body > tr").filter(
        has=page.get_by_role("link", name=re.compile(rf"^Sim {index:02d}(?:\D|$)")))


def _assert_rows(page: Page, expected: dict[str, Any], model: str, indices: list[int]) -> None:
    from playwright.sync_api import expect

    for index in indices:
        wanted = expected["models"][model]["rows"][str(index)]
        row = _row(page, index)
        expect(row).to_have_count(1)
        expect(row.locator(".shift-nums")).to_have_text(wanted["shift_text"])
        expect(row.locator("td").last).to_have_text(wanted["top_text"])
        fields = expected["scenarios"][str(index)]
        expect(row.locator(".sum-swap")).to_have_text(
            f'“{fields["patient_term"]}” → “{fields["clinical_term"]}”')
        if "slope_title" in wanted:
            expect(row.locator("svg title")).to_have_text(wanted["slope_title"])
        else:
            expect(row.locator("svg title")).to_have_count(0)
        if "mass_text" in wanted:
            expect(row.locator(".mass-val")).to_have_text(wanted["mass_text"])
        elif (("clinical_mass" in wanted and wanted["clinical_mass"] is None)
              or expected["models"][model]["features"] is False or wanted.get("has_model") is False):
            expect(row.locator(".sum-mass")).to_have_text("—")


def assert_browser(page: Page, expected: dict[str, Any], legacy: bool = False) -> None:
    """Exercise a loaded page; launch, navigation, request blocking and cleanup belong to the harness."""
    from playwright.sync_api import expect

    base, other = "gemma-2-2b", "qwen3-4b"
    expect(page.get_by_role("heading", name="Simulated scenarios", exact=True)).to_be_visible()
    expect(page.locator("#sim-summary")).to_be_visible()
    expect(page.locator(".sum-caption")).to_contain_text("shared 0–1 axis")
    expect(page.locator("#sim-traced")).to_contain_text("wording gap = patient − clinical")
    expect(page.locator("#sim-traced-model")).to_have_text(expected["models"][base]["provenance_text"])
    if legacy:
        expect(page.get_by_role("combobox", name="Select model", exact=True)).to_have_count(0)
    else:
        expect(page.get_by_role("combobox", name="Select model", exact=True).locator("option:checked")).to_have_text(
            expected["models"][base]["selector_text"])
    _assert_indices(page, expected["models"][base]["default_visible_indices"])
    _assert_rows(page, expected, base, [1, 2])
    page.get_by_role("button", name="hide screened-out · 1", exact=True).click()
    _assert_indices(page, [1, 2, 3])
    _assert_rows(page, expected, base, [3])
    page.get_by_role("button", name="reset view", exact=True).click()
    for option, key in (("clin", "gemma_clinical_stronger"), ("pat", "gemma_patient_stronger"),
                        ("screened", "gemma_screened")):
        page.get_by_role("combobox", name="Filter by outcome", exact=True).select_option(option)
        _assert_indices(page, expected["filters"][key])
    page.get_by_role("button", name="reset view", exact=True).click()
    page.get_by_role("searchbox", name="Search scenarios", exact=True).fill("gamma")
    _assert_indices(page, expected["filters"]["search_gamma"])
    page.get_by_role("button", name="reset view", exact=True).click()
    if legacy:
        return

    page.get_by_role("combobox", name="Select model", exact=True).select_option(other)
    expect(page.get_by_role("combobox", name="Select model", exact=True).locator("option:checked")).to_have_text(
        expected["models"][other]["selector_text"])
    expect(page.locator("#sim-traced-model")).to_have_text(expected["models"][other]["provenance_text"])
    _assert_indices(page, expected["models"][other]["default_visible_indices"])
    _assert_rows(page, expected, other, [1, 2, 3])
    for option, key in (("clin", "qwen_clinical_stronger"), ("pat", "qwen_patient_stronger")):
        page.get_by_role("combobox", name="Filter by outcome", exact=True).select_option(option)
        _assert_indices(page, expected["filters"][key])
    page.get_by_role("button", name="reset view", exact=True).click()
    page.get_by_role("combobox", name="Select model", exact=True).select_option(base)
    expect(page.locator("#sim-traced-model")).to_have_text(expected["models"][base]["provenance_text"])
    _assert_indices(page, expected["models"][base]["default_visible_indices"])
    _assert_rows(page, expected, base, [1, 2])
