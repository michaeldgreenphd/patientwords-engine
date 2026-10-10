"""The publication hold (scripts/publication_hold.py, 2026-10-09): a landed summary of a held exploratory model
changes no published aggregate.

Each consumer that would otherwise pool trace_out/<stem>__<model>/ parts into something the site shows is run, or
its reading function called, over a synthetic engine root twice - before and after held models' parts land - and
must give the same output. The phrases are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BATCH = "pairs_20200101T000000Z"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_publication_hold", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hold = _load("publication_hold")
bp = _load("backfill_planner")

_TIERS = {"status": "synthetic tiers - test only", "tiers": {"1": "tier one", "2": "tier two"},
          "tokens": {"alpha": {"tier": 2}, "beta": {"tier": 1}}}
_SPREAD = {"clinical": [["alpha", 0.6], ["beta", 0.2]], "patient": [["beta", 0.5], ["alpha", 0.3]]}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _summary(indexes, graph_model, backend="logits"):
    return {"graph_model": graph_model, "backend": backend, "source_set": None,
            "results": [{"index": i, "prompts": {"clinical": f"alpha prompt {i}", "patient": f"beta prompt {i}"},
                         "probabilities": {"clinical": 0.6, "patient": 0.3},
                         "predictive_spread": _SPREAD, "language_penalty": -0.3} for i in indexes]}


def _land_held_parts(root: Path) -> None:
    for model in sorted(hold.HELD_MODELS):
        _write(root / "trace_out" / f"{BATCH}__{model}" / "batch_summary.part_01.json", _summary([1, 2, 3], model))


@pytest.fixture
def engine_root(tmp_path):
    root = tmp_path / "engine"
    _write(root / "tiers.json", _TIERS)
    _write(root / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}})
    _write(root / "data" / "simulated" / f"{BATCH}.json",
           [{"top_prompt": f"alpha prompt {i}", "generation": {"topic": "topic-a"}} for i in (1, 2, 3)])
    _write(root / "trace_out" / BATCH / "batch_summary.part_01.json", _summary([1, 2, 3], "gemma-2-2b", "hosted"))
    _write(root / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_01.json", _summary([1, 2, 3], "qwen3-4b"))
    return root


def test_the_held_models_are_the_planners_exploratory_models():
    assert hold.HELD_MODELS == set(bp.EXPLORATORY)
    assert hold.is_held_run_dir(f"{BATCH}__gemma-4-e2b") and not hold.is_held_run_dir(f"{BATCH}__qwen3-4b")
    assert not hold.is_held_run_dir(BATCH) and not hold.is_held_run_dir(f"{BATCH}__jlens_gemma-2-2b")


def _urgency(root: Path, tag: str) -> tuple[bytes, bytes, str]:
    site = root.parent / f"site_{tag}"
    _write(site / "data" / "simulated_scenarios.json",
           {"batches": [{"batch": BATCH}], "scenarios": [
               {"batch": BATCH, "batch_index": i, "clinical_prompt": f"alpha prompt {i}", "models": {}}
               for i in (1, 2, 3)]})
    rows = root.parent / f"rows_{tag}.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "urgency_shift.py"), "--tiers", "tiers.json",
                           "--out", str(rows), "--publish", str(site)], cwd=root, capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    return rows.read_bytes(), (site / "data" / "urgency_shift.json").read_bytes(), proc.stdout


def test_urgency_shift_publishes_the_same_bytes_after_held_parts_land(engine_root):
    rows_before, site_before, out_before = _urgency(engine_root, "before")
    assert {r["model"] for r in json.loads(rows_before)["rows"]} == {"gemma-2-2b", "qwen3-4b"}
    _land_held_parts(engine_root)
    rows_after, site_after, out_after = _urgency(engine_root, "after")
    assert rows_after == rows_before and site_after == site_before
    # skipped by name and count, never silently
    assert "held from publication" not in out_before
    assert "held from publication (scripts/publication_hold.py), parts skipped: gemma-4-e2b 1, " \
           "medgemma-1.5-4b-it 1, qwen3.5-2b-base 1" in out_after


def test_a_held_part_is_skipped_by_its_directory_even_without_graph_model(engine_root):
    part = _summary([1], "gemma-4-e2b")
    del part["graph_model"]
    _write(engine_root / "trace_out" / f"{BATCH}__gemma-4-e2b" / "batch_summary.part_01.json", part)
    rows, _, out = _urgency(engine_root, "suffix")
    assert "gemma-4-e2b" not in {r["model"] for r in json.loads(rows)["rows"]} and "gemma-4-e2b 1" in out


def test_paired_stats_rigor_drops_held_rows_by_name(tmp_path, capsys):
    rigor = _load("paired_stats_rigor")
    rows = [{"model": m, "batch": BATCH, "index": 1, "clinical_prompt": "alpha prompt 1"}
            for m in ("qwen3-4b", "gemma-4-e2b", "medgemma-1.5-4b-it")]
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({"rows": rows}))
    kept = rigor.load_rows(path)
    assert [r["model"] for r in kept] == ["qwen3-4b"]
    assert "publication hold: excluded 2 rows" in capsys.readouterr().out


def test_the_timeline_does_not_count_held_parts(engine_root, monkeypatch):
    tl = _load("study_timeline")
    monkeypatch.chdir(engine_root)
    assert tl.main(["--out", "before.json", "--site", ""]) == 0
    _land_held_parts(engine_root)
    assert tl.main(["--out", "after.json", "--site", ""]) == 0
    before = json.loads((engine_root / "before.json").read_text())
    after = json.loads((engine_root / "after.json").read_text())
    assert before["totals"]["trace_summary_parts"] == after["totals"]["trace_summary_parts"] == 2
    assert before["totals"]["held_trace_summary_parts"] == 0
    assert after["totals"]["held_trace_summary_parts"] == 3


def test_screen_sensitivity_skips_held_models(engine_root):
    ss = _load("screen_sensitivity")
    before = ss.collect_rows(engine_root / "trace_out")
    _land_held_parts(engine_root)
    after = ss.collect_rows(engine_root / "trace_out")
    assert before and after == before and {r.get("model") for r in after} == {"qwen3-4b"}


def test_the_audit_mirror_of_urgency_shift_skips_held_parts(engine_root):
    audit = _load("audit_target_reads")
    _land_held_parts(engine_root)
    loaded = {d: [(p, json.loads(p.read_text())) for p in sorted(d.glob("batch_summary*.json"))]
              for d in sorted((engine_root / "trace_out").iterdir())}
    reads = audit.urgency_reads(engine_root, loaded)
    assert reads and not any("__" in part and part.split("/")[1].split("__")[1] in hold.HELD_MODELS
                             for part, _ in reads)


def test_the_exporter_refuses_to_merge_a_held_model(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPTS / "export_frontend_simulated.py"), "--frontend",
                           str(tmp_path / "site"), "--stamps", "20200101T000000Z", "--models",
                           "gemma-2-2b,qwen3.5-2b-base"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "held from publication" in proc.stderr and "qwen3.5-2b-base" in proc.stderr
    assert not (tmp_path / "site").exists()


def test_the_exporter_candidate_models_and_labels_cover_held_models():
    src = (SCRIPTS / "export_frontend_simulated.py").read_text(encoding="utf-8")
    for m in hold.HELD_MODELS:
        assert f'"{m}"' in src


def test_releasing_held_model_includes_it_in_models_meta(engine_root, tmp_path):
    _land_held_parts(engine_root)
    _write(engine_root / "data" / "simulated" / f"{BATCH}.report.json", {"accepted": 3, "cost_usd": 0.0})
    (engine_root / "trace_out" / BATCH / "index_01.html").write_text("render 1", encoding="utf-8")
    (engine_root / "trace_out" / f"{BATCH}__gemma-4-e2b" / "index_01.html").write_text("render 1", encoding="utf-8")

    site = tmp_path / "site"
    (site / "modes" / "simulated").mkdir(parents=True)
    (site / "data").mkdir(parents=True)
    override_code = (
        "import sys; "
        f"sys.path.insert(0, {str(SCRIPTS)!r}); "
        "import publication_hold as ph; "
        "import sys as _sys; _sys.modules['scripts.publication_hold'] = ph; "
        "ph.HELD_MODELS = frozenset(ph.HELD_MODELS - {'gemma-4-e2b'}); "
        "import export_frontend_simulated\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", override_code, "--engine", str(engine_root),
         "--frontend", str(site), "--stamps", "20200101T000000Z"],
        cwd=engine_root, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    meta_ids = [m["id"] for m in payload["models_meta"]]
    assert "gemma-4-e2b" in meta_ids
    gemma4_meta = next(m for m in payload["models_meta"] if m["id"] == "gemma-4-e2b")
    assert gemma4_meta["label"] == "Gemma 4 E2B"
    assert gemma4_meta["available"] is True
