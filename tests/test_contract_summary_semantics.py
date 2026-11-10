"""The contract validator's check of payload.summary.penalty (scripts/validate_frontend_contract.py).

Until 2026-11-10 the validator did not read the summary block: a payload whose
summary said n_phrases 999999 and mean_phrase_deduped 0.75 produced zero errors.
check_summary_penalty recomputes the block from the payload's own rows, in code
that does not import the producer (scripts/payload_summary.py).

These tests pin the rule, the one dated legacy form it accepts
(LEGACY_SUMMARY_ACCEPTED_THROUGH) and the level that form is reported at. Every
date is passed in, so no test depends on the wall clock. Rows are synthetic and
their phrases are abstract placeholders, never stimulus text. The two tests
marked REAL DATA read the published site payload without writing to it and
print none of its text; they are the only evidence here about a real file, and
none of this is evidence about a model.
"""

import ast
import hashlib
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vfc = _load("validate_frontend_contract")
ps = _load("payload_summary")          # the producer: used only to show the two agree, never by the validator

BASE = "gemma-2-2b"
DEADLINE = vfc.LEGACY_SUMMARY_ACCEPTED_THROUGH
BEFORE = date(2026, 11, 10)
AFTER = DEADLINE + timedelta(days=1)
A = "simulated_scenarios.json :: $.summary.penalty"

# The published site payload this change was reviewed against. Once the site carries a re-exported payload the
# digest no longer matches and the REAL DATA tests skip; delete them with the transition.
SITE_PAYLOAD = _ROOT.parent / "patientwords" / "data" / "simulated_scenarios.json"
SITE_PAYLOAD_SHA256 = "5bcd3eac2bc347f181d92c0f33cf4a74390ec0ad36740e4c624199f0b3e01ef7"


def row(batch, batch_index, phrase, penalty, steered=False, screened=False):
    """One scenario as the exporter assembles it, with the base-model mirror at the top level."""
    model = {"prob_clinical": 0.5, "prob_patient": 0.25, "language_penalty": penalty, "flipped": False,
             "top_clinical": ["alpha", 0.5], "top_patient": ["beta", 0.25], "spread_clinical": [["alpha", 0.5]],
             "spread_patient": [["beta", 0.25]], "target_token": "alpha", "anchor_fallback": False,
             "screening": {"status": "screened_out"} if screened else None, "circuit_diff": None,
             "clinical_mass": None}
    entry = {"index": 0, "batch": batch, "batch_index": batch_index, "clinical_prompt": phrase,
             "patient_prompt": "placeholder patient wording", "intended_target": "alpha", "topics": [],
             "models": {BASE: model}}
    entry.update({k: model[k] for k in vfc.COMPAT})
    if steered:
        entry["steered"] = True
    return entry


def payload(rows, penalty="absent"):
    """A schema-valid payload around `rows`; `penalty` becomes summary.penalty unless left absent."""
    for i, r in enumerate(rows, start=1):
        r["index"] = i
    stems = sorted({r["batch"] for r in rows})
    out = {
        "batches": [{"batch": s, "generated": {"model": "m", "run_timestamp": "2026-01-01T00:00:00Z",
                                                "cost_usd": 0.1, "accepted": 2, "rejected": 0},
                     "screen_targets": None} for s in stems],
        "traced": {"graph_model": BASE}, "traced_by_model": {}, "holdout_withheld": 0,
        "models_meta": [{"id": BASE, "label": "Base", "graph_model": BASE, "source_set": "set-a", "features": True,
                         "graphs": True, "available": True, "default": True, "attention_replacement": False,
                         "n_traced": len(rows)}],
        "scenarios": rows,
    }
    steered = sorted({r["batch"] for r in rows if r.get("steered")})
    if steered:
        out["steering_disclosure"] = {"stamps": steered, "note": "placeholder disclosure"}
    if penalty != "absent":
        out["summary"] = {"model": BASE, "penalty": penalty}
    return out


def check(pl, today=BEFORE, tmp_path=Path(".")):
    rep = vfc.Report()
    vfc.check_simulated(rep, tmp_path, pl, today)
    return rep


def four_rows():
    """Four scored rows in two batches. One phrase is traced in both batches.

    rows:    -0.4, -0.2, -0.1, 0.1                 n_scored_rows 4   mean_rows_raw       -0.6 / 4 = -0.15
    phrases: one   (-0.4 + -0.2) / 2 = -0.3
             two   -0.1
             three  0.1                             n_phrases 3       mean_phrase_deduped -0.3 / 3 = -0.1
    """
    return [row("pairs_A", 1, "placeholder phrase one", -0.4),
            row("pairs_B", 1, "placeholder phrase one", -0.2),
            row("pairs_A", 2, "placeholder phrase two", -0.1),
            row("pairs_B", 2, "placeholder phrase three", 0.1)]


def corrected(**changes):
    """summary.penalty for four_rows() under the corrected rule. The interval is what the producer writes for its
    default seed and resample count; the validator checks it for consistency only."""
    return {"population": "public_payload", "mean_phrase_deduped": -0.1, "n_phrases": 3, "n_scored_rows": 4,
            "mean_rows_raw": -0.15, "ci95": [-0.3, 0.1], **changes}


def legacy(**changes):
    """summary.penalty for four_rows() as the producer wrote it before the correction: every row its own phrase, so
    n_phrases is the row count, the deduped mean is the row mean, and the interval resampled rows."""
    return {"population": "public_payload", "mean_phrase_deduped": -0.15, "n_phrases": 4, "n_scored_rows": 4,
            "mean_rows_raw": -0.15, "ci95": [-0.325, 0.025], **changes}


def summary_errors(rep):
    return [e for e in rep.errors if "$.summary" in e]


def legacy_notes(rep):
    return [n for n in rep.notes if n.startswith(f"{A} :: legacy summary")]


# ---------------------------------------------------------------------------------------- the corrected form

@pytest.mark.parametrize("today", [BEFORE, DEADLINE, AFTER])
def test_a_corrected_summary_passes_with_no_note(today):
    rep = check(payload(four_rows(), corrected()), today)
    assert rep.errors == [] and rep.notes == []


def test_a_repeated_phrase_in_two_batches_counts_once():
    """The hand-computed values of four_rows(): the phrase traced in pairs_A and in pairs_B is one phrase."""
    rep = check(payload(four_rows(), corrected()))
    assert rep.errors == [] and rep.notes == []
    # counting the repeat twice (4 phrases) or weighting its two rows separately (-0.15) is the legacy form
    wrong = check(payload(four_rows(), corrected(n_phrases=4)))
    assert [e for e in wrong.errors if f"{A}.n_phrases :: says 4" in e and "3 distinct" in e]


def test_rows_with_no_prompt_use_the_batch_index_fallback_and_stay_distinct():
    """Two rows with an empty prompt are two phrases, identified by (batch, batch_index), not one empty phrase.

    rows:    -0.4, -0.2, -0.3, -0.1                 n_scored_rows 4   mean_rows_raw       -1.0 / 4 = -0.25
    phrases: one   (-0.4 + -0.2) / 2 = -0.3
             pairs_A#2  -0.3
             pairs_A#3  -0.1                        n_phrases 3       mean_phrase_deduped -0.7 / 3 = -0.2333
    """
    rows = [row("pairs_A", 1, "placeholder phrase one", -0.4), row("pairs_B", 1, "placeholder phrase one", -0.2),
            row("pairs_A", 2, "", -0.3), row("pairs_A", 3, "", -0.1)]
    good = {"mean_phrase_deduped": -0.2333, "n_phrases": 3, "n_scored_rows": 4, "mean_rows_raw": -0.25,
            "ci95": [-0.3, -0.1]}
    rep = check(payload(rows, good))
    assert rep.errors == [] and rep.notes == []
    # had the two empty prompts been merged: phrases -0.3 and (-0.3 + -0.1) / 2 = -0.2, mean -0.25, n_phrases 2
    merged = check(payload(rows, {**good, "n_phrases": 2, "mean_phrase_deduped": -0.25, "ci95": None}))
    assert len(summary_errors(merged)) == 3, merged.errors


def test_steered_null_and_screened_rows_are_outside_the_population():
    """Scored means: not steered, and a numeric top-level penalty. A steered row with a penalty, a pending row
    (null penalty) and a screened-out row (null penalty) change none of the four values."""
    rows = four_rows() + [row("pairs_S", 1, "placeholder phrase one", 0.9, steered=True),
                          row("pairs_A", 3, "placeholder phrase four", None),
                          row("pairs_A", 4, "placeholder phrase five", None, screened=True)]
    rep = check(payload(rows, corrected()))
    assert rep.errors == [] and rep.notes == []
    counted = check(payload(rows, corrected(n_scored_rows=5)))
    assert [e for e in counted.errors if f"{A}.n_scored_rows :: says 5, the payload has 4" in e]


def test_no_scored_row_means_null_means_and_zero_counts():
    rows = [row("pairs_A", 1, "placeholder phrase one", None)]
    empty = {"mean_phrase_deduped": None, "n_phrases": 0, "n_scored_rows": 0, "mean_rows_raw": None, "ci95": None}
    assert check(payload(rows, empty)).errors == []
    assert summary_errors(check(payload(rows, {**empty, "mean_rows_raw": 0.0})))


# ------------------------------------------------------------------------------------------ the legacy form

@pytest.mark.parametrize("today", [BEFORE, DEADLINE])
def test_the_legacy_form_is_a_note_through_the_deadline(today):
    rep = check(payload(four_rows(), legacy()), today)
    assert rep.errors == [] and rep.warnings == []
    assert len(rep.notes) == 1 and legacy_notes(rep)
    note = rep.notes[0]
    # the correction, the two values, the deadline and the remedy
    assert "2026-11-10 phrase-key correction in scripts/payload_summary.py" in note
    assert "n_phrases 4 and mean_phrase_deduped -0.15" in note
    assert "n_phrases 3 and mean_phrase_deduped -0.1." in note
    assert "Accepted through 2026-12-15 (LEGACY_SUMMARY_ACCEPTED_THROUGH); an error from 2026-12-16." in note
    assert "re-export with the corrected producer" in note


def test_the_legacy_form_is_an_error_after_the_deadline():
    rep = check(payload(four_rows(), legacy()), AFTER)
    assert rep.notes == []
    assert len(rep.errors) == 1 and rep.errors[0].startswith(f"{A} :: legacy summary")
    assert "ended on 2026-12-15" in rep.errors[0] and "re-export with the corrected producer" in rep.errors[0]


def test_the_deadline_is_the_named_date():
    assert DEADLINE == date(2026, 12, 15)


def test_the_default_date_is_the_current_utc_date_and_is_replaceable(monkeypatch):
    """With no date passed, the deadline is compared with _utc_today(); nothing else reads the clock."""
    monkeypatch.setattr(vfc, "_utc_today", lambda: DEADLINE)
    assert legacy_notes(check(payload(four_rows(), legacy()), today=None))
    monkeypatch.setattr(vfc, "_utc_today", lambda: AFTER)
    assert check(payload(four_rows(), legacy()), today=None).errors


def test_row_keyed_values_are_simply_correct_when_no_phrase_repeats():
    """With no repeated phrase the row-keyed and the phrase-keyed summaries are the same numbers: no note."""
    rows = [row("pairs_A", 1, "placeholder phrase one", -0.4), row("pairs_A", 2, "placeholder phrase two", -0.2),
            row("pairs_A", 3, "placeholder phrase three", 0.3)]
    pen = {"mean_phrase_deduped": -0.1, "n_phrases": 3, "n_scored_rows": 3, "mean_rows_raw": -0.1,
           "ci95": [-0.4, 0.3]}
    for today in (BEFORE, AFTER):
        rep = check(payload(rows, pen), today)
        assert rep.errors == [] and rep.notes == []


@pytest.mark.parametrize("strict", [False, True])
def test_the_legacy_note_is_not_promoted_by_strict(tmp_path, strict):
    """Level: a note. --strict promotes warnings only, so before the deadline the legacy form fails neither site
    CI's report-mode run nor a --strict run; after it, it fails both."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "simulated_scenarios.json").write_text(json.dumps(payload(four_rows(), legacy())), encoding="utf-8")
    rep = vfc.validate(tmp_path, engine=None, strict=strict, today=BEFORE)
    assert legacy_notes(rep) and not summary_errors(rep)
    assert not [w for w in rep.warnings if "$.summary" in w]
    late = vfc.validate(tmp_path, engine=None, strict=strict, today=AFTER)
    assert len(summary_errors(late)) == 1 and not legacy_notes(late)


# --------------------------------------------------------- every other disagreement, on both sides of the date

@pytest.mark.parametrize("today", [BEFORE, AFTER])
def test_impossible_values_are_an_error_before_and_after_the_date(today):
    """The reviewed head accepted exactly this payload."""
    rep = check(payload(four_rows(), corrected(n_phrases=999999, mean_phrase_deduped=0.75)), today)
    assert rep.notes == []
    assert [e for e in rep.errors if f"{A}.n_phrases :: says 999999" in e]
    assert [e for e in rep.errors if f"{A}.mean_phrase_deduped :: says 0.75" in e]


@pytest.mark.parametrize("today", [BEFORE, AFTER])
@pytest.mark.parametrize("change, field", [
    ({"mean_phrase_deduped": -0.12}, "mean_phrase_deduped"),     # right n_phrases, wrong mean
    ({"mean_phrase_deduped": -0.15}, "mean_phrase_deduped"),     # right n_phrases, the legacy (row) mean
    ({"n_phrases": 4}, "n_phrases"),                             # the legacy count, the corrected mean
    ({"n_scored_rows": 5}, "n_scored_rows"),                     # right means, wrong row count
    ({"mean_rows_raw": -0.1}, "mean_rows_raw"),
    ({"mean_phrase_deduped": -0.10004}, "mean_phrase_deduped"),  # within rounding distance but not 4 decimals
])
def test_one_wrong_value_is_an_error(today, change, field):
    rep = check(payload(four_rows(), corrected(**change)), today)
    assert rep.notes == []
    assert [e for e in rep.errors if f"{A}.{field} :: says" in e], rep.errors


@pytest.mark.parametrize("today", [BEFORE, AFTER])
@pytest.mark.parametrize("change", [
    {"n_scored_rows": 5},                      # the legacy phrase fields beside a wrong row count
    {"mean_rows_raw": -0.1},
    {"n_phrases": 5},
    {"ci95": [0.0, 0.025]},                    # an interval that excludes the row mean
    {"ci95": None},
])
def test_the_transition_accepts_the_one_legacy_form_and_nothing_near_it(today, change):
    rep = check(payload(four_rows(), legacy(**change)), today)
    assert not legacy_notes(rep)
    assert summary_errors(rep)


@pytest.mark.parametrize("ci, says", [
    ([0.1, -0.3], "low 0.1 is above high -0.3"),
    ([-0.05, 0.1], "does not contain the mean"),
    ([-0.5, 0.1], "leaves the range"),
    ([-0.3, 0.2], "leaves the range"),
    (None, "must be [low, high]"),
    ([-0.3], "must be [low, high]"),
    ([-0.3, "0.1"], "must be [low, high]"),
    ([-0.3, True], "must be [low, high]"),
])
def test_ci95_is_checked_for_consistency_with_the_phrase_means(ci, says):
    rep = check(payload(four_rows(), corrected(ci95=ci)))
    assert [e for e in rep.errors if f"{A}.ci95 :: " in e and says in e], rep.errors


def test_ci95_is_null_below_three_phrases():
    """rows -0.4, -0.2 (one phrase, mean -0.3) and -0.1: two phrases, mean (-0.3 + -0.1) / 2 = -0.2; row mean
    -0.7 / 3 = -0.2333."""
    rows = four_rows()[:3]
    pen = {"mean_phrase_deduped": -0.2, "n_phrases": 2, "n_scored_rows": 3, "mean_rows_raw": -0.2333, "ci95": None}
    assert check(payload(rows, pen)).errors == []
    rep = check(payload(rows, {**pen, "ci95": [-0.3, -0.1]}))
    assert [e for e in rep.errors if "must be null with fewer than 3 phrase means" in e]


# --------------------------------------------------------------------------- shape, and payloads without it

def test_a_payload_without_the_block_is_not_checked():
    """Older payloads: no summary, a summary that is not an object, or a summary without `penalty`."""
    for pl in (payload(four_rows()),
               {**payload(four_rows()), "summary": {"totals": {"accepted": 4}}},
               {**payload(four_rows()), "summary": None}):
        for today in (BEFORE, AFTER):
            rep = check(pl, today)
            assert rep.errors == [] and rep.notes == []


@pytest.mark.parametrize("penalty, where", [
    (None, "$.summary.penalty :: must be an object"),
    ([], "$.summary.penalty :: must be an object"),
    ({k: v for k, v in corrected().items() if k != "n_phrases"}, "$.summary.penalty.n_phrases :: missing"),
    ({k: v for k, v in corrected().items() if k != "ci95"}, "$.summary.penalty.ci95 :: missing"),
    (corrected(n_phrases=3.0), "$.summary.penalty.n_phrases :: wrong type"),
    (corrected(n_scored_rows=True), "$.summary.penalty.n_scored_rows :: wrong type"),
    (corrected(mean_rows_raw="-0.15"), "$.summary.penalty.mean_rows_raw :: wrong type"),
    (corrected(n_phrases=None), "$.summary.penalty.n_phrases :: null"),
])
def test_a_present_block_must_have_the_five_fields_typed(penalty, where):
    rep = check(payload(four_rows(), penalty))
    assert [e for e in rep.errors if where in e], rep.errors


# ------------------------------------------------------------------------------ the validator and the producer

def test_the_validator_does_not_import_the_producer():
    """The recomputation is written in the validator so that a producer defect is not repeated by its check."""
    tree = ast.parse((_ROOT / "scripts" / "validate_frontend_contract.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not [name for name in imported if "payload_summary" in name]


def test_the_corrected_producers_output_passes_and_its_row_keyed_output_is_the_legacy_form():
    """Agreement of the two implementations on the synthetic rows. The row-keyed output is produced by blanking
    every prompt, which makes the producer take the batch#batch_index fallback for every row: what it did for
    every published row before the correction."""
    rows = four_rows() + [row("pairs_A", 3, "", -0.05), row("pairs_B", 3, "placeholder phrase two", 0.2)]
    now = ps.build_summary(rows, accepted=6, holdout_withheld=0)["penalty"]
    rep = check(payload(rows, now), AFTER)
    assert rep.errors == [] and rep.notes == []
    then = ps.build_summary([{**r, "clinical_prompt": ""} for r in rows], accepted=6, holdout_withheld=0)["penalty"]
    assert then["n_phrases"] == then["n_scored_rows"] == 6 and now["n_phrases"] == 4
    assert legacy_notes(check(payload(rows, then), BEFORE))
    assert summary_errors(check(payload(rows, then), AFTER))


# ------------------------------------------------------------------------------------------------- REAL DATA

@pytest.fixture(scope="module")
def site_payload():
    if not SITE_PAYLOAD.is_file():
        pytest.skip(f"no site checkout at {SITE_PAYLOAD.parents[1]}")
    raw = SITE_PAYLOAD.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SITE_PAYLOAD_SHA256:
        pytest.skip("the site payload is not the one this transition was written for (re-exported since)")
    return json.loads(raw)


def test_real_site_payload_validates_with_exactly_the_legacy_note(site_payload):
    """REAL DATA, read-only. The published payload still carries the pre-correction summary."""
    pen = site_payload["summary"]["penalty"]
    assert (pen["n_scored_rows"], pen["n_phrases"], pen["mean_phrase_deduped"]) == (1163, 1163, -0.0387)
    rep = check(site_payload, BEFORE, SITE_PAYLOAD.parents[1])
    assert rep.errors == [] and rep.warnings == []
    assert len(rep.notes) == 1 and legacy_notes(rep)
    assert "n_phrases 1163 and mean_phrase_deduped -0.0387" in rep.notes[0]
    assert "n_phrases 1124 and mean_phrase_deduped -0.0367." in rep.notes[0]
    late = check(site_payload, AFTER, SITE_PAYLOAD.parents[1])
    assert len(late.errors) == 1 and late.errors[0].startswith(f"{A} :: legacy summary")


def test_real_site_payload_with_the_corrected_summary_validates_with_no_note(site_payload):
    """REAL DATA, read-only: the summary is replaced in memory by the values the corrected rule gives for the same
    rows. n_scored_rows and mean_rows_raw are the published ones, unchanged by the correction."""
    pen = site_payload["summary"]["penalty"]
    fixed = {**site_payload, "summary": {**site_payload["summary"], "penalty": {
        **pen, "n_phrases": 1124, "mean_phrase_deduped": -0.0367, "ci95": [-0.046, -0.0267]}}}
    assert fixed["summary"]["penalty"]["n_scored_rows"] == 1163
    for today in (BEFORE, AFTER):
        rep = check(fixed, today, SITE_PAYLOAD.parents[1])
        assert rep.errors == [] and rep.warnings == [] and rep.notes == []
    # and the reviewed head's counter-example, on the real rows
    broken = {**fixed, "summary": {**fixed["summary"], "penalty": {
        **fixed["summary"]["penalty"], "n_phrases": 999999, "mean_phrase_deduped": 0.75}}}
    assert len(summary_errors(check(broken, BEFORE, SITE_PAYLOAD.parents[1]))) >= 2
