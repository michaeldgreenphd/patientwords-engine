"""The legacy payload rows record (data/results_policy/legacy_payload_rows.v1.json) against what the collector does.

scripts/urgency_shift.py reads engine parts through the analysis membership and then fills from the site gallery
payload. A payload row at a key whose engine part the membership did not read is still taken, so it is in the
published statistics without any part of the membership behind it. On 2026-11-10 there are 11 such rows, all
qwen3-4b (docs/open_results_migration_20261110.md, section 6; docs/corrections/payload_summary_dedupe_20261110.md).

The record declares each of those rows. These tests keep it equal to reality:

* the keys the collector takes today (its ``--fallback-keys-out`` list) are exactly the record's active entries,
  so a twelfth, undeclared row fails here, and so does a declared row the collector has stopped taking;
* each declared row has the recorded bytes in the payload, and the engine part at its key is the recorded file
  and is outside the membership for the recorded reason;
* the record holds no prompt or token text.

The synthetic cases use abstract placeholder strings, never study stimuli. The two cases that read the published
payload and ``trace_out/`` skip, visibly, when the sibling site checkout or the engine parts are not on disk.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from scripts import results_policy as rp  # noqa: E402

RECORD = ROOT / "data" / "results_policy" / "legacy_payload_rows.v1.json"
COLLECTOR = SCRIPTS / "urgency_shift.py"
SCHEMA = "patientwords.legacy-payload-rows/1"
ACTIVE, RETIRED = "taken_by_collector", "retired"
ENTRY_KEYS = {"model", "batch", "batch_index", "state", "payload_row", "payload_row_sha256",
              "payload_measurement_sha256", "payload_values_measured_by", "engine_part", "not_read_because",
              "membership_reason", "engine_part_values", "retired_by"}
PAYLOAD_ROW_KEYS = {"prob_clinical", "prob_patient", "language_penalty", "flipped", "anchor_fallback", "screening",
                    "clinical_mass", "circuit_diff_present", "top_clinical_p", "top_patient_p", "spread_clinical_n",
                    "spread_patient_n", "target_token_chars", "urgency"}
FLIP_CLASSES = {None, "downgrade", "upgrade", "lateral", "uninformative"}
_SHA = re.compile(r"[0-9a-f]{64}")
_PART = re.compile(r"trace_out/[A-Za-z0-9_.-]+/batch_summary[A-Za-z0-9_.]*\.json")


def load_record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def entry_key(entry: dict) -> tuple:
    return (entry["model"], entry["batch"], entry["batch_index"])


def row_sha256(obj: dict, without: tuple[str, ...] = ()) -> str:
    """The record's row hash: UTF-8 JSON, sorted keys, compact separators, non-ASCII kept."""
    kept = {k: v for k, v in obj.items() if k not in without}
    return hashlib.sha256(json.dumps(kept, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _order(key: tuple) -> tuple:
    return (str(key[0]), str(key[1]), key[2] if isinstance(key[2], int) else -1)


def key_differences(record: dict, collector_keys: list) -> list[str]:
    """Every disagreement between the record and the keys the collector takes. Empty means they agree."""
    taken = {tuple(k) for k in collector_keys}
    active = {entry_key(e) for e in record["entries"] if e["state"] == ACTIVE}
    retired = {entry_key(e) for e in record["entries"] if e["state"] == RETIRED}
    problems = [f"undeclared: the collector takes {k} from the site payload although the membership did not read "
                f"its engine part, and {RECORD.name} has no active entry for it. Declare it there with its part and "
                "reason, or change what the collector takes in a reviewed change with a superseding snapshot"
                for k in sorted(taken - active - retired, key=_order)]
    problems += [f"retired but still taken: {k}" for k in sorted(taken & retired, key=_order)]
    problems += [f"no longer taken: {k} is declared as {ACTIVE} and the collector does not take it (the payload "
                 "was re-exported, the pin advanced, or the part changed). Set its state to "
                 f"{RETIRED!r} with retired_by naming the snapshot that recorded the change"
                 for k in sorted(active - taken, key=_order)]
    return problems


def run_collector(engine_root: Path, site: Path, out_dir: Path, *extra: str, keys: bool = True
                  ) -> tuple[int, list | None, bytes, str]:
    """Run the collector in ``engine_root`` against ``site``. Returns (exit code, the fallback keys or None when
    the file was not written, the bytes of --out, stdout and stderr)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, keys_file = out_dir / "rows.json", out_dir / "fallback_keys.json"
    argv = [sys.executable, str(COLLECTOR), "--out", str(rows), "--frontend", str(site), *extra]
    if keys:
        argv += ["--fallback-keys-out", str(keys_file)]
    proc = subprocess.run(argv, cwd=engine_root, capture_output=True, text=True, timeout=600)
    listed = json.loads(keys_file.read_text(encoding="utf-8")) if keys_file.exists() else None
    return proc.returncode, listed, rows.read_bytes() if rows.exists() else b"", proc.stdout + proc.stderr


# ---------------------------------------------------------------- the record itself (always runs)

def test_the_record_is_well_formed_and_holds_no_prompt_or_token_text():
    record = load_record()
    assert record["schema"] == SCHEMA and record["membership"] == rp.STUDY_INTERIM
    entries = record["entries"]
    assert record["count"] == len(entries) == len({entry_key(e) for e in entries})
    policy = rp.load_policy()
    for e in entries:
        assert set(e) <= ENTRY_KEYS, sorted(set(e) - ENTRY_KEYS)
        assert e["state"] in (ACTIVE, RETIRED)
        assert (e["state"] == RETIRED) == bool(e.get("retired_by")), "a retired entry names its snapshot; an active one names none"
        assert policy.cohort_of(e["model"]) is not None and isinstance(e["batch_index"], int)
        assert re.fullmatch(r"[A-Za-z0-9_]+", e["batch"])
        assert _SHA.fullmatch(e["payload_row_sha256"]) and _SHA.fullmatch(e["payload_measurement_sha256"])
        assert _PART.fullmatch(e["engine_part"]) and e["not_read_because"] in ("pin", "cohort", "class")
        assert _PART.fullmatch(e["payload_values_measured_by"].partition("@")[0])
        assert re.fullmatch(r"[a-z0-9 ,()/_.-]{1,120}", e["membership_reason"])
        # no text field of the row is copied: only numbers, booleans, counts, null and the urgency join
        row = e["payload_row"]
        assert set(row) == PAYLOAD_ROW_KEYS
        urgency = row["urgency"] or {}
        assert urgency.get("flip_class") in FLIP_CLASSES
        scalars = [v for k, v in row.items() if k != "urgency"] + [v for k, v in urgency.items() if k != "flip_class"]
        assert all(v is None or isinstance(v, (bool, int, float)) for v in scalars), scalars
        assert all(v is None or isinstance(v, (int, float)) for v in e["engine_part_values"].values())
    today = record["parts"]["engine_part_at_these_keys_today"]
    assert {e["engine_part"] for e in entries if e["state"] == ACTIVE} <= {today["path"]}
    assert _SHA.fullmatch(today["sha256"]) and _SHA.fullmatch(record["site_payload"]["sha256"])


def test_the_comparison_reports_an_undeclared_row_a_row_no_longer_taken_and_a_retired_row_still_taken():
    record = load_record()
    declared = [list(entry_key(e)) for e in record["entries"] if e["state"] == ACTIVE]
    assert key_differences(record, declared) == []
    twelfth = ["qwen3-4b", "pairs_20200101T000000Z", 12]
    problems = key_differences(record, declared + [twelfth])
    assert len(problems) == 1 and problems[0].startswith("undeclared") and "pairs_20200101T000000Z" in problems[0]
    fewer = copy.deepcopy(record)
    fewer["entries"].append({"model": "qwen3-4b", "batch": "pairs_20200101T000000Z", "batch_index": 7,
                             "state": ACTIVE})
    problems = key_differences(fewer, declared)
    assert len(problems) == 1 and problems[0].startswith("no longer taken") and "retired_by" in problems[0]
    fewer["entries"][-1].update(state=RETIRED, retired_by="study-interim-20991231")
    assert key_differences(fewer, declared) == []                                   # retired and not taken: agreed
    problems = key_differences(fewer, declared + [["qwen3-4b", "pairs_20200101T000000Z", 7]])
    assert len(problems) == 1 and problems[0].startswith("retired but still taken")


# ---------------------------------------------------------------- the collector's key list, on a synthetic tree

BATCH = "pairs_20200101T000000Z"
_SPREAD = {"clinical": [["alpha", 0.6], ["beta", 0.2]], "patient": [["beta", 0.5], ["alpha", 0.3]]}
_TIERS = {"status": "synthetic tiers - test only", "tiers": {"1": "tier one", "2": "tier two"},
          "tokens": {"alpha": {"tier": 2}, "beta": {"tier": 1}}}
_PAYLOAD_MODEL = {"spread_clinical": [["alpha", 0.6], ["beta", 0.2]], "spread_patient": [["beta", 0.5], ["alpha", 0.3]],
                  "language_penalty": -0.3}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _summary(indexes, graph_model, backend="logits"):
    return {"graph_model": graph_model, "backend": backend, "source_set": None, "completed": True,
            "pairs_requested": len(indexes),
            "results": [{"index": i, "prompts": {"clinical": f"alpha prompt {i}", "patient": f"beta prompt {i}"},
                         "probabilities": {"clinical": 0.6, "patient": 0.3},
                         "predictive_spread": _SPREAD, "language_penalty": -0.3} for i in indexes]}


@pytest.fixture
def synthetic(tmp_path):
    """An engine tree with a hosted base part, a pinned qwen3-4b logits part (pairs 1-2) and an unpinned one
    (pairs 3-4); a site payload that shows qwen3-4b on pairs 1-3 and a payload-only model on every pair."""
    engine, site = tmp_path / "engine", tmp_path / "site"
    _write(engine / "trace_out" / BATCH / "batch_summary.part_01.json", _summary([1, 2, 3, 4], "gemma-2-2b", "hosted"))
    pinned = engine / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_01.json"
    _write(pinned, _summary([1, 2], "qwen3-4b"))
    _write(engine / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_03.json", _summary([3, 4], "qwen3-4b"))
    _write(engine / rp.RELEASE_MANIFEST, {"schema": rp.MANIFEST_SCHEMA, "parts": {
        pinned.relative_to(engine).as_posix(): hashlib.sha256(pinned.read_bytes()).hexdigest()}})
    _write(engine / "tiers.json", _TIERS)
    _write(engine / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}})
    _write(engine / "data" / "simulated" / f"{BATCH}.json",
           [{"top_prompt": f"alpha prompt {i}", "generation": {"topic": "topic-a"}} for i in (1, 2, 3, 4)])
    _write(site / "data" / "simulated_scenarios.json", {"batches": [{"batch": BATCH}], "scenarios": [
        {"batch": BATCH, "batch_index": i, "clinical_prompt": f"alpha prompt {i}",
         "models": {"olmo-2-1b": copy.deepcopy(_PAYLOAD_MODEL),
                    **({"qwen3-4b": copy.deepcopy(_PAYLOAD_MODEL)} if i <= 3 else {})}} for i in (1, 2, 3, 4)]})
    return engine, site


def test_the_collector_lists_exactly_the_rows_it_takes_at_unread_keys_and_changes_no_other_output(synthetic, tmp_path):
    """New on 2026-11-10: ``--fallback-keys-out``. Pair 3 is in an unpinned part and in the payload: listed. Pair
    4 is in the unpinned part and not in the payload: nothing is taken, so it is not listed. Pairs 1-2 are read
    from the pinned part. The payload-only model has no engine part at all, so none of its rows is listed."""
    engine, site = synthetic
    rc, keys, rows_with, out_with = run_collector(engine, site, tmp_path / "with", "--tiers", "tiers.json")
    assert rc == 0, out_with
    assert keys == [["qwen3-4b", BATCH, 3]]
    assert "at keys whose engine part this membership did not read" in out_with and "qwen3-4b 1" in out_with
    taken = {(r["model"], r["index"]) for r in json.loads(rows_with)["rows"]}
    assert ("qwen3-4b", 3) in taken and ("qwen3-4b", 4) not in taken and ("olmo-2-1b", 4) in taken
    rc, none, rows_without, out_without = run_collector(engine, site, tmp_path / "without", "--tiers", "tiers.json",
                                                        keys=False)
    assert rc == 0 and none is None                                    # not asked: no file is written
    assert rows_without == rows_with                                   # the flag changes no byte of --out
    assert out_without.replace(str(tmp_path / "without"), "X") == out_with.replace(str(tmp_path / "with"), "X")


def test_the_collector_writes_an_empty_list_when_it_takes_no_such_row(synthetic, tmp_path):
    engine, site = synthetic
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    for scenario in payload["scenarios"]:
        scenario["models"].pop("qwen3-4b", None)
    _write(site / "data" / "simulated_scenarios.json", payload)
    rc, keys, _, out = run_collector(engine, site, tmp_path / "none", "--tiers", "tiers.json")
    assert rc == 0, out
    assert keys == [] and "at keys whose engine part this membership did not read" not in out


# ---------------------------------------------------------------- the record against the published payload

def _site_root() -> Path:
    override = os.environ.get("PW_SITE_ROOT")
    site = Path(override) if override else ROOT.parent / "patientwords"
    if not (site / "data" / "simulated_scenarios.json").is_file():
        if override:
            pytest.fail(f"PW_SITE_ROOT={override} holds no data/simulated_scenarios.json")
        pytest.skip(f"sibling checkout ../patientwords absent ({site}); set PW_SITE_ROOT to compare the record "
                    "with the published payload")
    return site


def _require_parts_on_disk(paths: set[str]) -> None:
    """Skip in a checkout that tracks a recorded part and keeps it off disk (sparse or partial). A part that git
    does not track either is not skipped: the comparison then fails and says the row is no longer taken."""
    for rel in sorted(paths):
        if (ROOT / rel).is_file():
            continue
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", rel],
                                 capture_output=True, text=True)
        if tracked.returncode == 0:
            pytest.skip(f"{rel} is tracked and not on disk (partial checkout): restore trace_out/ summaries as "
                        "docs/fresh_session_bootstrap.md shows")


def test_the_record_equals_the_rows_the_collector_takes_from_the_published_payload(tmp_path):
    record, site = load_record(), _site_root()
    _require_parts_on_disk({e["engine_part"] for e in record["entries"] if e["state"] == ACTIVE})
    if not any((ROOT / "trace_out").glob("*/batch_summary.part_*.json")):
        pytest.skip("no trace_out/ summaries on disk: the collector would take every row from the payload")
    rc, keys, _, out = run_collector(ROOT, site, tmp_path / "published")
    assert rc == 0, out[-2000:]
    assert keys is not None
    problems = key_differences(record, keys)
    assert not problems, "\n".join(problems)
    by_model: dict[str, int] = {}
    for model, _, _ in keys:
        by_model[model] = by_model.get(model, 0) + 1
    for model, n in by_model.items():                                   # the list and the printed count agree
        assert f"{model} {n}" in out.rsplit("note: rows taken from the site payload", 1)[-1]


def test_each_declared_row_has_the_recorded_bytes_and_its_part_is_outside_the_membership_for_the_recorded_reason():
    record, site = load_record(), _site_root()
    active = [e for e in record["entries"] if e["state"] == ACTIVE]
    _require_parts_on_disk({e["engine_part"] for e in active})
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    rows = {(s.get("batch"), s.get("batch_index")): s for s in payload["scenarios"]}
    gate = rp.Gate(ROOT)
    summaries: dict[str, dict] = {}
    today = record["parts"]["engine_part_at_these_keys_today"]
    for e in active:
        scenario = rows.get((e["batch"], e["batch_index"]))
        model_obj = ((scenario or {}).get("models") or {}).get(e["model"])
        assert model_obj is not None, f"{entry_key(e)} is declared and the published payload does not hold it"
        assert row_sha256(model_obj) == e["payload_row_sha256"], entry_key(e)
        assert row_sha256(model_obj, without=("urgency",)) == e["payload_measurement_sha256"], entry_key(e)
        for field in ("prob_clinical", "prob_patient", "language_penalty", "flipped"):
            assert model_obj.get(field) == e["payload_row"][field], (entry_key(e), field)
        part = ROOT / e["engine_part"]
        assert part.is_file(), f"{e['engine_part']} is gone: {entry_key(e)} has no engine part at its key"
        summary = summaries.setdefault(e["engine_part"], json.loads(part.read_text(encoding="utf-8")))
        assert gate.reason(part, summary, e["model"]) == e["membership_reason"], entry_key(e)
        kind = {"pin": "pinned manifest", "cohort": "cohort", "class": "stimulus class"}[e["not_read_because"]]
        assert kind in e["membership_reason"]
        result = next((r for r in summary["results"] if r["index"] == e["batch_index"]), None)
        assert result is not None, f"{e['engine_part']} holds no result at index {e['batch_index']}"
        assert {"prob_clinical": result["probabilities"].get("clinical"),
                "prob_patient": result["probabilities"].get("patient"),
                "language_penalty": result.get("language_penalty")} == e["engine_part_values"], entry_key(e)
        if e["engine_part"] == today["path"]:
            assert rp.sha256_file(part) == today["sha256"]
