"""The exporter reads a batch's base-model trace from the batch's own directory only.

Until 2026-11-20 ``export_frontend_simulated.model_dir`` returned the top level of
``trace_out/`` for the base model whenever ``trace_out/<stem>/`` did not exist. That
was the layout of the first published trace (``pairs_20260706T175614Z``, 2026-07-06),
whose summaries and renders stayed at the top level until 2026-09-12. Every batch
whose other models landed before its base-model trace was therefore exported with
that trace's rows as its base-model rows: its prompts, its probabilities and its
renders under the newer batch's name. The site payloads of 2026-08-06, 2026-08-07
and 2026-08-08 carried 28 such rows across three batches, and five renders copied
then were still on the site on 2026-11-20.

Pins, on synthetic engine and site trees with abstract phrases only:

- a summary and renders at the top level of ``trace_out/`` are never read for a
  batch that has no base-model directory: the batch exports its own prompts, the
  base model is absent from its rows and from ``models_meta``, and no top-level
  render is copied to the site;
- a stamp whose only "trace" is at the top level has no trace: the exporter
  stops and writes nothing;
- with the batch directory present, its rows are the base-model rows, whatever
  the top level holds.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

STAMP = "20260801T000000Z"
STEM = f"pairs_{STAMP}"
BASE = "gemma-2-2b"
OTHER = "qwen3-4b"
STRAY_MARK = "stray top-level render"


def _hold(p):
    return int(hashlib.sha1(p.encode()).hexdigest(), 16) % 10 == 0


def _phrase(base):
    """An abstract phrase outside the Tier B holdout, so no row is withheld."""
    return next(f"{base} {i} so a" for i in range(500) if not _hold(f"{base} {i} so a"))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _result(index, clinical, p_clinical, p_patient):
    return {"index": index, "prompts": {"clinical": clinical, "patient": f"{clinical} plain"},
            "probabilities": {"clinical": p_clinical, "patient": p_patient},
            "language_penalty": round(p_patient - p_clinical, 3), "target_token": 'Output " tok"',
            "predictive_spread": {"clinical": [['Output " tok"', p_clinical]],
                                  "patient": [['Output " other"', p_patient]]}}


OWN = [_phrase("zq own words"), _phrase("zq more own words"), _phrase("zq last own words")]
STRAY = [_phrase("zq stray words"), _phrase("zq more stray words")]


def build(tmp_path, *, base_dir=False, other_model=True):
    """A batch of three pairs. The top level of trace_out/ always holds a base-model
    summary of two rows of some other batch, with their renders."""
    engine, site = tmp_path / "engine", tmp_path / "site"
    _write(engine / "ops" / "dashboard.json", json.dumps({"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}))
    _write(engine / "data" / "simulated" / f"{STEM}.json", json.dumps(
        [{"top_prompt": p, "bottom_prompt": f"{p} plain", "target_clinical_token": " tok"} for p in OWN]))
    _write(engine / "data" / "simulated" / f"{STEM}.report.json", json.dumps({"accepted": len(OWN)}))
    trace = engine / "trace_out"
    _write(trace / "batch_summary.part_01.json", json.dumps(
        {"graph_model": BASE, "backend": "hosted", "source_set": "gemmascope-transcoder-16k",
         "results": [_result(i, p, 0.9, 0.1) for i, p in enumerate(STRAY, start=1)]}))
    for i in (1, 2):
        _write(trace / f"index_{i:02d}.html", f"<html>{STRAY_MARK} {i}</html>")
    if other_model:
        _write(trace / f"{STEM}__{OTHER}" / "batch_summary.part_01.json", json.dumps(
            {"graph_model": OTHER, "backend": "hosted",
             "results": [_result(i, p, 0.4, 0.2) for i, p in enumerate(OWN, start=1)]}))
    if base_dir:
        _write(trace / STEM / "batch_summary.part_01.json", json.dumps(
            {"graph_model": BASE, "backend": "hosted", "source_set": "gemmascope-transcoder-16k",
             "results": [_result(i, p, 0.5, 0.3) for i, p in enumerate(OWN, start=1)]}))
        for i in (1, 2, 3):
            _write(trace / STEM / f"index_{i:02d}.html", f"<html>own render {i}</html>")
    (site / "data").mkdir(parents=True)
    return engine, site


def export(engine, site, *extra):
    return subprocess.run([sys.executable, str(_ROOT / "scripts" / "export_frontend_simulated.py"),
                           "--engine", str(engine), "--frontend", str(site), "--stamps", STAMP,
                           "--models", f"{BASE},{OTHER}", *extra],
                          capture_output=True, text=True, cwd=str(engine))


def _site_files(site):
    return {p.relative_to(site).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(site.rglob("*")) if p.is_file()}


def test_a_top_level_summary_is_not_read_for_a_batch_without_a_base_directory(tmp_path):
    engine, site = build(tmp_path)
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    rows = payload["scenarios"]
    # the batch's own three pairs, not the two rows of the top-level summary
    assert [(s["batch"], s["batch_index"], s["clinical_prompt"]) for s in rows] == [
        (STEM, i, p) for i, p in enumerate(OWN, start=1)]
    for s in rows:
        assert sorted(s["models"]) == [OTHER]            # the base model has no measurement here
        assert s["models"][OTHER]["prob_clinical"] == 0.4
        assert not s.get("html")                          # and no render
    assert [m["id"] for m in payload["models_meta"]] == [OTHER]
    assert BASE not in payload["traced_by_model"]
    files = _site_files(site)
    assert not any(rel.startswith("modes/") for rel in files), sorted(files)
    assert not any(STRAY_MARK in text or any(p in text for p in STRAY) for text in files.values())


def test_a_stamp_whose_only_summary_is_at_the_top_level_has_no_trace(tmp_path):
    engine, site = build(tmp_path, other_model=False)
    for extra in ((), ("--dry-run",)):
        proc = export(engine, site, *extra)
        assert proc.returncode != 0, extra
        assert f"no trace dirs for stamp {STAMP}" in proc.stderr
        assert _site_files(site) == {}                    # nothing written or copied


def test_the_batch_directory_supplies_the_base_rows_whatever_the_top_level_holds(tmp_path):
    engine, site = build(tmp_path, base_dir=True)
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    rows = payload["scenarios"]
    assert [s["clinical_prompt"] for s in rows] == OWN
    for i, s in enumerate(rows, start=1):
        assert sorted(s["models"]) == sorted([BASE, OTHER])
        assert s["models"][BASE]["prob_clinical"] == 0.5 and s["prob_clinical"] == 0.5
        assert s["html"] == f"modes/simulated/{STEM}/index_{i:02d}.html"
        assert (site / s["html"]).read_text(encoding="utf-8") == f"<html>own render {i}</html>"
    assert not any(STRAY_MARK in text for text in _site_files(site).values())
