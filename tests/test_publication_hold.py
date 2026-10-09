"""The publication hold (scripts/publication_hold.py, 2026-10-09): nothing the backfill campaign lands moves a
published number until the owner releases it.

Two rules: the exploratory models (HELD_MODELS) are never read; and a CPU-logits part is read only when the release
manifest (data/publication_release/logits_parts.json) lists it with the sha256 of its bytes. Each consumer that
would pool trace_out/ parts into something the site shows is run, or its reading function called, over a synthetic
engine root before and after new parts land, and must give the same output until a release. The phrases are
abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import hashlib
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
release = _load("publication_release")

_TIERS = {"status": "synthetic tiers - test only", "tiers": {"1": "tier one", "2": "tier two"},
          "tokens": {"alpha": {"tier": 2}, "beta": {"tier": 1}}}
_SPREAD = {"clinical": [["alpha", 0.6], ["beta", 0.2]], "patient": [["beta", 0.5], ["alpha", 0.3]]}
QWEN_PART = Path("trace_out") / f"{BATCH}__qwen3-4b" / "batch_summary.part_01.json"


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _summary(indexes, graph_model, backend="logits"):
    return {"graph_model": graph_model, "backend": backend, "source_set": None,
            "results": [{"index": i, "prompts": {"clinical": f"alpha prompt {i}", "patient": f"beta prompt {i}"},
                         "probabilities": {"clinical": 0.6, "patient": 0.3},
                         "predictive_spread": _SPREAD, "language_penalty": -0.3} for i in indexes]}


def _manifest(root: Path, rels) -> None:
    parts = {Path(r).as_posix(): hashlib.sha256((root / r).read_bytes()).hexdigest() for r in rels}
    _write(root / hold.RELEASE_MANIFEST, {"schema": hold.MANIFEST_SCHEMA, "parts": parts})


def _land_held_parts(root: Path) -> None:
    for model in sorted(hold.HELD_MODELS):
        _write(root / "trace_out" / f"{BATCH}__{model}" / "batch_summary.part_01.json", _summary([1, 2, 3], model))


def _land_unreleased_original_part(root: Path) -> None:
    """A gap-fill part for an original model, as the backfill chain lands it: not in the manifest."""
    _write(root / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_04.json", _summary([4], "qwen3-4b"))


@pytest.fixture
def engine_root(tmp_path):
    """A hosted gemma-2-2b part and a released qwen3-4b logits part over pairs 1-3 of a 4-pair batch."""
    root = tmp_path / "engine"
    _write(root / "tiers.json", _TIERS)
    _write(root / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}})
    _write(root / "data" / "simulated" / f"{BATCH}.json",
           [{"top_prompt": f"alpha prompt {i}", "generation": {"topic": "topic-a"}} for i in (1, 2, 3, 4)])
    _write(root / "trace_out" / BATCH / "batch_summary.part_01.json", _summary([1, 2, 3], "gemma-2-2b", "hosted"))
    _write(root / QWEN_PART, _summary([1, 2, 3], "qwen3-4b"))
    _manifest(root, [QWEN_PART])
    return root


def test_the_held_models_are_the_planners_exploratory_models():
    assert hold.HELD_MODELS == set(bp.EXPLORATORY)
    assert hold.is_held_run_dir(f"{BATCH}__gemma-4-e2b") and not hold.is_held_run_dir(f"{BATCH}__qwen3-4b")
    assert not hold.is_held_run_dir(BATCH) and not hold.is_held_run_dir(f"{BATCH}__jlens_gemma-2-2b")


def _urgency(root: Path, tag: str) -> tuple[int, bytes, bytes, str]:
    site = root.parent / f"site_{tag}"
    _write(site / "data" / "simulated_scenarios.json",
           {"batches": [{"batch": BATCH}], "scenarios": [
               {"batch": BATCH, "batch_index": i, "clinical_prompt": f"alpha prompt {i}", "models": {}}
               for i in (1, 2, 3, 4)]})
    rows = root.parent / f"rows_{tag}.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "urgency_shift.py"), "--tiers", "tiers.json",
                           "--out", str(rows), "--publish", str(site)], cwd=root, capture_output=True, text=True,
                          timeout=120)
    published = site / "data" / "urgency_shift.json"
    return (proc.returncode, rows.read_bytes() if rows.exists() else b"",
            published.read_bytes() if published.exists() else b"", proc.stdout + proc.stderr)


def test_urgency_shift_publishes_the_same_bytes_after_held_and_unreleased_parts_land(engine_root):
    rc, rows_before, site_before, out_before = _urgency(engine_root, "before")
    assert rc == 0, out_before
    assert {(r["model"], r["index"]) for r in json.loads(rows_before)["rows"]} >= {("qwen3-4b", 1), ("qwen3-4b", 3)}
    assert "publication hold" not in out_before
    _land_held_parts(engine_root)
    _land_unreleased_original_part(engine_root)
    rc, rows_after, site_after, out_after = _urgency(engine_root, "after")
    assert rc == 0, out_after
    assert rows_after == rows_before and site_after == site_before
    # skipped by name and count, never silently
    assert ("publication hold (scripts/publication_hold.py), parts not read: held model gemma-4-e2b 1, "
            "held model medgemma-1.5-4b-it 1, held model qwen3.5-2b-base 1, unreleased logits part 1") in out_after


def test_a_release_publishes_the_new_part_and_nothing_else_changes_its_status(engine_root):
    _land_unreleased_original_part(engine_root)
    new = Path("trace_out") / f"{BATCH}__qwen3-4b" / "batch_summary.part_04.json"
    _manifest(engine_root, [QWEN_PART, new])                           # what --release would write
    rc, rows, _, out = _urgency(engine_root, "released")
    assert rc == 0 and ("qwen3-4b", 4) in {(r["model"], r["index"]) for r in json.loads(rows)["rows"]}
    assert "publication hold" not in out


def test_a_released_part_whose_bytes_changed_is_held_and_named(engine_root):
    _write(engine_root / QWEN_PART, _summary([1, 2, 3, 3], "qwen3-4b"))   # overwritten after its release
    rc, rows, _, out = _urgency(engine_root, "changed")
    assert rc == 0 and "logits part changed since its release 1" in out
    assert "qwen3-4b" not in {r["model"] for r in json.loads(rows)["rows"]}


def test_without_a_manifest_the_collector_refuses_and_writes_nothing(engine_root):
    (engine_root / hold.RELEASE_MANIFEST).unlink()
    rc, rows, site, out = _urgency(engine_root, "nomanifest")
    assert rc != 0 and "refusing, nothing written" in out and "logits_parts.json is missing" in out
    assert rows == b"" and site == b""


def test_hosted_parts_need_no_manifest(engine_root):
    (engine_root / QWEN_PART).unlink()
    (engine_root / hold.RELEASE_MANIFEST).unlink()
    rc, rows, _, out = _urgency(engine_root, "hosted")
    assert rc == 0, out
    assert {r["model"] for r in json.loads(rows)["rows"]} == {"gemma-2-2b"}


def test_a_held_part_is_skipped_by_its_directory_even_without_graph_model(engine_root):
    part = _summary([1], "gemma-4-e2b")
    del part["graph_model"]
    _write(engine_root / "trace_out" / f"{BATCH}__gemma-4-e2b" / "batch_summary.part_01.json", part)
    rc, rows, _, out = _urgency(engine_root, "suffix")
    assert rc == 0 and "gemma-4-e2b" not in {r["model"] for r in json.loads(rows)["rows"]}
    assert "held model gemma-4-e2b 1" in out


def test_paired_stats_rigor_drops_held_rows_by_name(tmp_path, capsys):
    rigor = _load("paired_stats_rigor")
    rows = [{"model": m, "batch": BATCH, "index": 1, "clinical_prompt": "alpha prompt 1"}
            for m in ("qwen3-4b", "gemma-4-e2b", "medgemma-1.5-4b-it")]
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({"rows": rows}))
    kept = rigor.load_rows(path)
    assert [r["model"] for r in kept] == ["qwen3-4b"]
    assert "publication hold: excluded 2 rows" in capsys.readouterr().out


def test_the_timeline_counts_only_publishable_parts(engine_root, monkeypatch):
    tl = _load("study_timeline")
    monkeypatch.chdir(engine_root)
    assert tl.main(["--out", "before.json", "--site", ""]) == 0
    _land_held_parts(engine_root)
    _land_unreleased_original_part(engine_root)
    assert tl.main(["--out", "after.json", "--site", ""]) == 0
    before = json.loads((engine_root / "before.json").read_text())
    after = json.loads((engine_root / "after.json").read_text())
    assert before["totals"]["trace_summary_parts"] == after["totals"]["trace_summary_parts"] == 2


def test_screen_sensitivity_reads_only_released_logits_parts(engine_root):
    ss = _load("screen_sensitivity")
    before = ss.collect_rows(engine_root / "trace_out")
    _land_held_parts(engine_root)
    _land_unreleased_original_part(engine_root)
    after = ss.collect_rows(engine_root / "trace_out")
    assert before and after == before and {r.get("model") for r in after} == {"qwen3-4b"}


def test_the_audit_mirror_of_urgency_shift_skips_what_the_collector_skips(engine_root):
    audit = _load("audit_target_reads")
    _land_held_parts(engine_root)
    _land_unreleased_original_part(engine_root)
    loaded = {d: [(p, json.loads(p.read_text())) for p in sorted(d.glob("batch_summary*.json"))]
              for d in sorted((engine_root / "trace_out").iterdir())}
    reads = {part for part, _ in audit.urgency_reads(engine_root, loaded)}
    assert QWEN_PART.as_posix() in reads
    assert not any(p.endswith("part_04.json") or p.split("/")[1].split("__")[-1] in hold.HELD_MODELS for p in reads)


def test_export_archive_reads_only_released_logits_parts(engine_root, tmp_path):
    def export(tag):
        proc = subprocess.run([sys.executable, str(SCRIPTS / "export_archive.py"), "--engine", str(engine_root),
                               "--out", str(tmp_path / tag)], cwd=engine_root, capture_output=True, text=True,
                              timeout=120)
        assert proc.returncode == 0, proc.stderr
        return (tmp_path / f"{tag}.json").read_bytes(), proc.stdout
    before, _ = export("before")
    _land_unreleased_original_part(engine_root)
    after, out = export("after")
    assert after == before and "unreleased logits part 1" in out


def test_the_exporter_refuses_to_merge_a_held_model(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPTS / "export_frontend_simulated.py"), "--frontend",
                           str(tmp_path / "site"), "--stamps", "20200101T000000Z", "--models",
                           "gemma-2-2b,qwen3.5-2b-base"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "held from publication" in proc.stderr and "qwen3.5-2b-base" in proc.stderr
    assert not (tmp_path / "site").exists()


# ---------------------------------------------------------------- the owner's release command

def _git(root: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(root), *argv], check=True, capture_output=True, text=True)


@pytest.fixture
def git_root(engine_root):
    _git(engine_root, "init", "-q")
    _git(engine_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    _git(engine_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base")
    return engine_root


def test_release_lists_every_committed_logits_part_and_nothing_else(git_root, monkeypatch, capsys):
    monkeypatch.delenv("PW_ROUTINE", raising=False)
    _land_held_parts(git_root)
    _land_unreleased_original_part(git_root)
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "landed")
    _write(git_root / "trace_out" / f"{BATCH}__olmo-2-1b" / "batch_summary.part_01.json", _summary([1], "olmo-2-1b"))
    assert release.main(["--repo", str(git_root)]) == 0                 # --check: lists, writes nothing
    assert "unreleased: 1" in capsys.readouterr().out
    assert release.main(["--repo", str(git_root), "--release"]) == 0
    parts = json.loads((git_root / hold.RELEASE_MANIFEST).read_text())["parts"]
    # the committed qwen parts; not the hosted part, not the held models, not the untracked olmo part
    assert sorted(parts) == [QWEN_PART.as_posix(), f"trace_out/{BATCH}__qwen3-4b/batch_summary.part_04.json"]


def test_release_refuses_in_the_routine_and_over_a_modified_part(git_root, monkeypatch):
    monkeypatch.setenv("PW_ROUTINE", "1")
    with pytest.raises(SystemExit, match="never the Routine's"):
        release.main(["--repo", str(git_root), "--release"])
    monkeypatch.delenv("PW_ROUTINE")
    _write(git_root / QWEN_PART, _summary([1], "qwen3-4b"))
    with pytest.raises(SystemExit, match="differ from HEAD"):
        release.main(["--repo", str(git_root), "--release"])


def test_every_released_part_is_still_committed_with_its_released_bytes():
    """A released part must never change or vanish: that would move a published number without a release.
    (Parts landed after the last release are simply not listed yet; that is the hold working.)"""
    manifest = hold.load_manifest(ROOT)
    committed = release.committed_logits_parts(ROOT)
    assert len(manifest) >= 409
    assert {p: committed.get(p) for p in manifest} == manifest
