"""payload.summary builder (scripts/payload_summary.py) — offline (audit M1).

Pins the phrase-dedupe (rigor semantics with the collector's batch#index
fallback), the screened/measured/flip totals the home strip needs, the
holdout-adjusted public denominator, and CI determinism.

The fixture rows have the shape scripts/export_frontend_simulated.py builds:
the clinical text is the top-level ``clinical_prompt`` string and there is no
``prompts`` object. Until 2026-11-10 these rows carried a nested
``prompts.clinical`` instead, a shape the exporter never produced, so the
tests passed while every published row fell back to being its own phrase.
Phrases here are abstract placeholders, never stimulus text.
"""

import importlib.util
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "payload_summary", _ROOT / "scripts" / "payload_summary.py")
ps = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ps)

_EXPORTER_SRC = (_ROOT / "scripts" / "export_frontend_simulated.py").read_text(encoding="utf-8")


def scen(batch, idx, phrase, pen, flipped=False, screened=False):
    """One scenario row as the exporter assembles it: the fields the summary
    reads, plus the per-model object the base-model mirror is copied from."""
    screening = {"status": "screened_out"} if screened else None
    return {"index": idx, "batch": batch, "batch_index": idx,
            "clinical_prompt": phrase,
            "patient_prompt": f"placeholder patient wording {batch}#{idx}",
            "models": {"gemma-2-2b": {"language_penalty": pen, "flipped": flipped,
                                      "screening": screening}},
            "language_penalty": pen, "flipped": flipped, "screening": screening}


def test_summary_reads_the_key_the_exporter_writes():
    """The exporter is script-style, so this pins its source: the entry key that
    holds the traced clinical prompt is the one phrase_key reads, and the
    fixture rows above use that key and no ``prompts`` object."""
    written = re.findall(r'"(\w+)":\s*base_r\["prompts"\]\["clinical"\]', _EXPORTER_SRC)
    assert written == ["clinical_prompt"]
    row = scen("b", 1, "placeholder phrase A", -0.1)
    assert written[0] in row and "prompts" not in row
    assert ps.PHRASE_FIELD == written[0]
    assert ps.phrase_key(row) == "placeholder phrase A"


def test_phrase_dedupe_and_fallback_key():
    rows = [scen("b", 1, "placeholder phrase A", -0.4),
            scen("b", 2, "placeholder phrase A", -0.2),  # re-trace: averaged, not double-counted
            scen("b", 3, None, -0.1),               # missing prompt -> batch#index fallback
            scen("b", 4, "", -0.3)]                 # distinct fallback keys stay distinct
    out = ps.build_summary(rows, accepted=10, holdout_withheld=2, n_boot=50)
    pen = out["penalty"]
    assert pen["n_phrases"] == 3 and pen["n_scored_rows"] == 4
    assert pen["mean_phrase_deduped"] == round((-0.3 + -0.1 + -0.3) / 3, 4)
    assert pen["mean_rows_raw"] == round((-0.4 - 0.2 - 0.1 - 0.3) / 4, 4)
    assert pen["population"] == "public_payload"


def test_retrace_in_a_later_batch_is_the_same_phrase():
    """The phrase is the clinical prompt, not the row identity: a phrase traced
    again under another (batch, batch_index) still counts once, and the
    interval resamples phrases, so two phrases are too few for a CI."""
    rows = [scen("b1", 1, "placeholder phrase A", -0.6),
            scen("b2", 7, "placeholder phrase A", -0.2),
            scen("b2", 8, "placeholder phrase B", 0.0)]
    pen = ps.build_summary(rows, accepted=3, holdout_withheld=0, n_boot=50)["penalty"]
    assert pen["n_scored_rows"] == 3 and pen["n_phrases"] == 2
    assert pen["mean_phrase_deduped"] == round((-0.4 + 0.0) / 2, 4)
    assert pen["mean_rows_raw"] == round((-0.6 - 0.2 + 0.0) / 3, 4)
    assert pen["ci95"] is None


def test_totals_screening_flips_and_public_denominator():
    rows = [scen("b", 1, "p1", -0.2, flipped=True),
            scen("b", 2, "p2", None, screened=True),   # screened: null penalty, not measured
            scen("b", 3, "p3", 0.1)]
    out = ps.build_summary(rows, accepted=100, holdout_withheld=9, n_boot=50)
    t = out["totals"]
    assert t == {"accepted": 100, "accepted_public": 91, "holdout_withheld": 9,
                 "measured": 2, "screened_out": 1, "flipped_base": 1,
                 "steered_measured": 0, "steered_flipped_base": 0, "steered_batches": []}


def test_steered_scenarios_are_counted_but_never_pooled():
    """Steered batches publish, and stay out of every headline figure.

    Owner decision 2026-08-15: they were generated at topics already known to
    flip, so pooling them would let the selection inflate the site's share.
    """
    plain = [scen("b", 1, "p1", -0.2, flipped=True), scen("b", 2, "p2", -0.2)]
    steered = [dict(scen("s", 1, "s1", -0.9, flipped=True), steered=True),
               dict(scen("s", 2, "s2", -0.9, flipped=True), steered=True, batch="s")]
    for row in steered:
        row["batch"] = "s"
    out = ps.build_summary(plain + steered, accepted=10, holdout_withheld=0, n_boot=50)
    t = out["totals"]
    assert t["measured"] == 2 and t["flipped_base"] == 1          # steered excluded
    assert t["steered_measured"] == 2 and t["steered_flipped_base"] == 2
    assert t["steered_batches"] == ["s"]
    # the -0.9 steered penalties must not drag the published mean
    assert out["penalty"]["n_scored_rows"] == 2
    assert out["penalty"]["mean_rows_raw"] == round(-0.2, 4)


def test_ci_deterministic_and_none_under_three_phrases():
    rows = [scen("b", i, f"p{i}", -0.1 * i) for i in range(1, 6)]
    a = ps.build_summary(rows, 5, 0, n_boot=200)["penalty"]["ci95"]
    b = ps.build_summary(rows, 5, 0, n_boot=200)["penalty"]["ci95"]
    assert a == b and a[0] <= a[1]
    tiny = [scen("b", 1, "p1", -0.1), scen("b", 2, "p2", -0.2)]
    assert ps.build_summary(tiny, 2, 0, n_boot=50)["penalty"]["ci95"] is None


def test_bool_penalty_never_counts_as_number():
    rows = [scen("b", 1, "p1", True), scen("b", 2, "p2", -0.2)]
    out = ps.build_summary(rows, 2, 0, n_boot=50)
    assert out["penalty"]["n_scored_rows"] == 1
