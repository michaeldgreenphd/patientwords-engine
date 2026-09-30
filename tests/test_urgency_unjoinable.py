"""The unjoinable_rows record: urgency rows that join no published scenario, counted by cause.

scripts/urgency_unjoinable.py holds the join rule and the causes; scripts/urgency_shift.py --publish writes the
record into the site's data/urgency_shift.json and keeps every row. The unit tests pin the causes and the refusals;
the end-to-end tests run the collector (a script: module-level code) as a subprocess over a synthetic engine root and
site payload, and check that the contract validator counts the same rows the collector recorded. Abstract vocabulary
only - no medical terms.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uj = _load("urgency_unjoinable")
vfc = _load("validate_frontend_contract")

BATCH = "pairs_20200101T000000Z"          # published, pre-Tier-B stamp
UNPUBLISHED = "pairs_20200102T000000Z"    # generation batch the payload leaves out


def _payload(keys=((BATCH, 1), (BATCH, 2)), batches=(BATCH,)):
    return {"batches": [{"batch": b} for b in batches],
            "scenarios": [{"batch": b, "batch_index": i} for b, i in keys]}


def _row(batch, index, model="m1"):
    return {"batch": batch, "index": index, "model": model, "flip_class": "downgrade"}


def _empty_causes():
    return {cause: {"n": 0, "stems": {}} for cause in uj.CAUSES}


# ------------------------------------------------------------------ causes


def test_rows_are_counted_by_cause_with_stems():
    rows = [_row(BATCH, 1), _row(BATCH, 2, model="m2"),        # join
            _row(BATCH, 3), _row(BATCH, 4),                     # published batch, pair not published
            _row(UNPUBLISHED, 1),                               # generation batch not published
            _row("repeat_r1", 1), _row("repeat_r1", 2),         # run directories, not generation batches
            _row(f"{BATCH}_txsuffix", 1)]
    rec = uj.count_unjoinable(rows, _payload())
    assert rec == {"n": 6, "by_cause": {
        "not_a_generation_batch": {"n": 3, "stems": {f"{BATCH}_txsuffix": 1, "repeat_r1": 2}},
        "batch_not_in_payload": {"n": 1, "stems": {UNPUBLISHED: 1}},
        "pair_not_in_payload": {"n": 2, "stems": {BATCH: 2}},
    }}


def test_the_model_is_not_part_of_the_join():
    rows = [_row(BATCH, 1, model=m) for m in ("m1", "m2", "m3")]
    assert uj.count_unjoinable(rows, _payload())["n"] == 0


def test_nothing_unjoinable_still_records_every_cause():
    assert uj.count_unjoinable([_row(BATCH, 1)], _payload()) == {"n": 0, "by_cause": _empty_causes()}


@pytest.mark.parametrize("stem", ["pairs_S1", f"{BATCH}_txsuffix", f"{BATCH}__m2", "drift_sentinel_20200101",
                                  "pairs_20200101T000000", "xpairs_20200101T000000Z"])
def test_a_stem_that_is_not_exactly_pairs_stamp_is_not_a_generation_batch(stem):
    rec = uj.count_unjoinable([_row(stem, 1)], _payload())
    assert rec["by_cause"]["not_a_generation_batch"] == {"n": 1, "stems": {stem: 1}}


def test_a_batch_listed_in_the_payload_without_scenarios_counts_as_published():
    payload = _payload(batches=(BATCH, UNPUBLISHED))
    rec = uj.count_unjoinable([_row(UNPUBLISHED, 1)], payload)
    assert rec["by_cause"]["pair_not_in_payload"] == {"n": 1, "stems": {UNPUBLISHED: 1}}
    assert rec["by_cause"]["batch_not_in_payload"]["n"] == 0


def test_a_batch_carried_only_by_scenarios_counts_as_published():
    payload = _payload(batches=())
    rec = uj.count_unjoinable([_row(BATCH, 9)], payload)
    assert rec["by_cause"]["pair_not_in_payload"]["n"] == 1


def test_counting_keeps_every_row_unchanged():
    rows = [_row(BATCH, 1), _row("repeat_r1", 1)]
    before = json.loads(json.dumps(rows))
    uj.count_unjoinable(rows, _payload())
    assert rows == before


@pytest.mark.parametrize("row", [{"batch": BATCH, "model": "m1"}, {"batch": None, "index": 1},
                                 {"batch": BATCH, "index": "1"}, {"batch": BATCH, "index": True}])
def test_a_row_without_a_join_key_is_refused(row):
    with pytest.raises(uj.PayloadRefusal, match="no join key"):
        uj.count_unjoinable([row], _payload())


# ---------------------------------------------------------------- payload refusals


@pytest.mark.parametrize("content, says", [
    (None, "missing"),
    ("{not json", "unreadable"),
    ("[]", "not a JSON object"),
    ('{"batches": []}', "non-empty 'scenarios'"),
    ('{"scenarios": []}', "non-empty 'scenarios'"),
    ('{"scenarios": {}}', "non-empty 'scenarios'"),
    (json.dumps({"scenarios": [{"batch": BATCH, "batch_index": "1"}]}), "1 scenario(s) without"),
    (json.dumps({"scenarios": [{"batch": BATCH, "batch_index": True}]}), "1 scenario(s) without"),
    (json.dumps({"scenarios": [{"batch_index": 1}, "x"]}), "2 scenario(s) without"),
])
def test_read_payload_refuses_what_it_cannot_join_against(tmp_path, content, says):
    path = tmp_path / "simulated_scenarios.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(uj.PayloadRefusal) as err:
        uj.read_payload(path)
    assert says in str(err.value)


def test_read_payload_returns_a_usable_payload(tmp_path):
    path = tmp_path / "simulated_scenarios.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    assert uj.payload_join_keys(uj.read_payload(path)) == {(BATCH, 1), (BATCH, 2)}


# ---------------------------------------------------------------- parity with the contract check


def _joins(tmp_path, payload):
    site = tmp_path / "parity_site"
    site.mkdir(exist_ok=True)
    return vfc.check_simulated(vfc.Report(), site, payload)


def test_the_validator_counts_the_rows_the_record_counts(tmp_path):
    payload = _payload()
    rows = [_row(BATCH, 1), _row(BATCH, 3), _row(UNPUBLISHED, 1), _row("repeat_r1", 1)]
    data = {"vocabulary_status": "synthetic", "summary": {"flip_classes": {}}, "rows": rows,
            "unjoinable_rows": uj.count_unjoinable(rows, payload)}
    rep = vfc.Report()
    vfc.check_urgency(rep, data, _joins(tmp_path, payload))
    assert rep.errors == [] and rep.warnings == []
    assert any("3/4 rows join no published scenario" in n for n in rep.notes)


def test_the_validator_and_the_collector_name_the_same_causes():
    assert tuple(vfc.UNJOINABLE_CAUSES) == uj.CAUSES


# ---------------------------------------------------------------- the collector, end to end

_TIERS = {"status": "synthetic tiers - test only", "tiers": {"1": "tier one", "2": "tier two"},
          "tokens": {"alpha": {"tier": 2}, "beta": {"tier": 1}}}
_SPREAD = {"clinical": [["alpha", 0.6], ["beta", 0.2]], "patient": [["beta", 0.5], ["alpha", 0.3]]}


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _summary(indexes, graph_model=None):
    out = {"results": [{"index": i, "prompts": {"clinical": f"alpha prompt {i}", "patient": f"beta prompt {i}"},
                        "predictive_spread": _SPREAD, "language_penalty": 0.1} for i in indexes]}
    if graph_model:
        out["graph_model"] = graph_model
    return out


@pytest.fixture
def engine_root(tmp_path):
    """A synthetic engine root: tiers file, pre-Tier-B batch files, a dashboard, and trace_out summaries."""
    root = tmp_path / "engine"
    _write(root / "tiers.json", _TIERS)
    _write(root / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}})
    for stem, n in ((BATCH, 3), (UNPUBLISHED, 1)):
        _write(root / "data" / "simulated" / f"{stem}.json",
               [{"top_prompt": f"alpha prompt {i}", "generation": {"topic": "topic-a"}} for i in range(1, n + 1)])
    trace = root / "trace_out"
    _write(trace / BATCH / "batch_summary.part_01.json", _summary([1, 3]))                 # joins; pair unpublished
    _write(trace / f"{BATCH}__m2" / "batch_summary.part_01.json", _summary([2], "m2"))    # joins
    _write(trace / UNPUBLISHED / "batch_summary.part_01.json", _summary([1]))             # batch unpublished
    _write(trace / "repeat_r1" / "batch_summary.part_01.json", _summary([1, 2]))          # not a generation batch
    _write(trace / f"{BATCH}_txsuffix" / "batch_summary.part_01.json", _summary([1]))     # not a generation batch
    return root


def _site(tmp_path, payload):
    site = tmp_path / "site"
    if payload is not None:
        _write(site / "data" / "simulated_scenarios.json", payload)
    else:
        (site / "data").mkdir(parents=True, exist_ok=True)
    return site


def _site_payload():
    model = {"spread_clinical": _SPREAD["clinical"], "spread_patient": _SPREAD["patient"], "language_penalty": 0.1}
    return {"batches": [{"batch": BATCH}],
            "scenarios": [{"batch": BATCH, "batch_index": i, "clinical_prompt": f"alpha prompt {i}",
                           "models": {"gemma-2-2b": model}} for i in (1, 2)]}


def _collect(root, site, publish=True):
    pub = root.parent / "pub"
    (pub / "data").mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(_SCRIPTS / "urgency_shift.py"), "--tiers", "tiers.json",
           "--frontend", str(site), "--out", str(root.parent / "rows.json")]
    if publish:
        cmd += ["--publish", str(pub)]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
    return proc, pub / "data" / "urgency_shift.json", root.parent / "rows.json"


def test_publish_records_unjoinable_rows_and_keeps_every_row(engine_root, tmp_path):
    site = _site(tmp_path, _site_payload())
    proc, published, _ = _collect(engine_root, site)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(published.read_text(encoding="utf-8"))
    # 7 trace rows + the payload's own gemma-2-2b row for pair 2: nothing is filtered
    assert len(data["rows"]) == 8
    assert data["unjoinable_rows"] == {"n": 5, "by_cause": {
        "not_a_generation_batch": {"n": 3, "stems": {f"{BATCH}_txsuffix": 1, "repeat_r1": 2}},
        "batch_not_in_payload": {"n": 1, "stems": {UNPUBLISHED: 1}},
        "pair_not_in_payload": {"n": 1, "stems": {BATCH: 1}},
    }}
    assert "unjoinable rows (join no scenario in" in proc.stdout

    # the contract check finds the same five, so a recorded total that matches is a note, never a warning
    rep = vfc.Report()
    vfc.check_urgency(rep, data, _joins(tmp_path, _site_payload()))
    assert rep.errors == [] and rep.warnings == []
    assert any("5/8 rows join no published scenario" in n for n in rep.notes)


def test_publish_without_frontend_counts_against_the_published_sites_payload(engine_root, tmp_path):
    # --publish alone reads the payload of the site it writes into; before, it read ../patientwords, which
    # here does not exist, so the count could describe a different payload than the one published beside it
    site = _site(tmp_path, _site_payload())
    assert not (engine_root.parent / "patientwords").exists()
    cmd = [sys.executable, str(_SCRIPTS / "urgency_shift.py"), "--tiers", "tiers.json",
           "--out", str(engine_root.parent / "rows.json"), "--publish", str(site)]
    proc = subprocess.run(cmd, cwd=engine_root, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    data = json.loads((site / "data" / "urgency_shift.json").read_text(encoding="utf-8"))
    assert data["unjoinable_rows"]["n"] == 5
    assert str(site) in proc.stdout


@pytest.mark.parametrize("payload", [None, {"scenarios": []}])
def test_publish_refuses_without_a_readable_payload_and_writes_nothing(engine_root, tmp_path, payload):
    site = _site(tmp_path, payload)
    proc, published, rows_out = _collect(engine_root, site)
    assert proc.returncode != 0
    assert "refusing --publish, nothing written" in proc.stderr
    assert not published.exists() and not rows_out.exists()


def test_without_publish_a_missing_payload_is_still_skipped(engine_root, tmp_path):
    # the engine-side row file never needed the site payload; only --publish counts against it
    site = _site(tmp_path, None)
    proc, published, rows_out = _collect(engine_root, site, publish=False)
    assert proc.returncode == 0, proc.stderr
    assert rows_out.exists() and not published.exists()
    assert "unjoinable_rows" not in json.loads(rows_out.read_text(encoding="utf-8"))
