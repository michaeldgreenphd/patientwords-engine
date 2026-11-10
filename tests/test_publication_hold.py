"""The default analysis membership (study-interim/1) through the import path collectors use
(scripts/publication_hold.py, since 2026-11-10 a compatibility module over scripts/results_policy.py).

Until 2026-11-10 these tests described a publication hold. The open-results policy (docs/open_results_policy.md)
replaced the hold: parts outside a membership are public in the results catalogue. What these tests still
guarantee is the benefit the hold was introduced for: nothing the backfill campaign lands moves a published
statistic without a versioned change. Under the default membership the 2026-10-09 post-registration models are
not read, and a CPU-logits part is read only when the pinned manifest
(data/publication_release/logits_parts.json) lists it with the sha256 of its bytes. Each consumer that pools
trace_out/ parts into a statistic the site shows is run, or its reading function called, over a synthetic engine
root before and after new parts land, and must give the same output. tests/test_results_policy.py covers the
other half: the same parts are visible. The phrases are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
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
    assert "parts not read" not in out_before
    _land_held_parts(engine_root)
    _land_unreleased_original_part(engine_root)
    rc, rows_after, site_after, out_after = _urgency(engine_root, "after")
    assert rc == 0, out_after
    assert rows_after == rows_before and site_after == site_before
    # skipped by name and count, never silently
    assert ("membership study-interim/1 (scripts/results_policy.py), parts not read: "
            "logits part outside the pinned manifest 1, "
            "model gemma-4-e2b (cohort post_registration_20261009, outside this membership) 1, "
            "model medgemma-1.5-4b-it (cohort post_registration_20261009, outside this membership) 1, "
            "model qwen3.5-2b-base (cohort post_registration_20261009, outside this membership) 1") in out_after


def test_a_release_publishes_the_new_part_and_nothing_else_changes_its_status(engine_root):
    _land_unreleased_original_part(engine_root)
    new = Path("trace_out") / f"{BATCH}__qwen3-4b" / "batch_summary.part_04.json"
    _manifest(engine_root, [QWEN_PART, new])                           # what --release would write
    rc, rows, _, out = _urgency(engine_root, "released")
    assert rc == 0 and ("qwen3-4b", 4) in {(r["model"], r["index"]) for r in json.loads(rows)["rows"]}
    assert "parts not read" not in out


def test_a_released_part_whose_bytes_changed_is_held_and_named(engine_root):
    _write(engine_root / QWEN_PART, _summary([1, 2, 3, 3], "qwen3-4b"))   # overwritten after its release
    rc, rows, _, out = _urgency(engine_root, "changed")
    assert rc == 0 and "logits part changed since it was recorded 1" in out
    assert "qwen3-4b" not in {r["model"] for r in json.loads(rows)["rows"]}


def test_without_a_manifest_the_collector_refuses_and_writes_nothing(engine_root):
    (engine_root / hold.RELEASE_MANIFEST).unlink()
    rc, rows, site, out = _urgency(engine_root, "nomanifest")
    assert rc != 0 and "refusing, nothing written" in out and "logits_parts.json is missing" in out
    assert rows == b"" and site == b""


def test_malformed_non_dict_manifest_raises_release_error(tmp_path):
    manifest_path = tmp_path / hold.RELEASE_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(hold.ReleaseError, match="not a logits_release/1 manifest"):
        hold.load_manifest(tmp_path)


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
    assert "model gemma-4-e2b (cohort post_registration_20261009, outside this membership) 1" in out


def test_paired_stats_rigor_drops_held_rows_by_name(tmp_path, capsys):
    rigor = _load("paired_stats_rigor")
    rows = [{"model": m, "batch": BATCH, "index": 1, "clinical_prompt": "alpha prompt 1"}
            for m in ("qwen3-4b", "gemma-4-e2b", "medgemma-1.5-4b-it")]
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({"rows": rows}))
    kept = rigor.load_rows(path)
    assert [r["model"] for r in kept] == ["qwen3-4b"]
    assert "analysis membership: excluded 2 rows" in capsys.readouterr().out


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
    assert before["totals"]["held_trace_summary_parts"] == 0
    assert after["totals"]["held_trace_summary_parts"] == 4


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
    assert after == before and "logits part outside the pinned manifest 1" in out


def test_interp_analyses_reads_only_released_parts(engine_root):
    interp = _load("interp_analyses")
    _land_held_parts(engine_root)
    _land_unreleased_original_part(engine_root)
    parts = list(interp.load_parts(engine_root / "trace_out"))
    # only the 2 released parts: gemma-2-2b and qwen3-4b part 1
    assert len(parts) == 2
    assert {name for name, _ in parts} == {BATCH, f"{BATCH}__qwen3-4b"}


def test_the_exporter_refuses_to_merge_a_held_model(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPTS / "export_frontend_simulated.py"), "--frontend",
                           str(tmp_path / "site"), "--stamps", "20200101T000000Z", "--models",
                           "gemma-2-2b,qwen3.5-2b-base"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "outside the analysis membership" in proc.stderr and "qwen3.5-2b-base" in proc.stderr
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
    with pytest.raises(SystemExit, match="never the Routine's action while analysis_pin.auto_advance is false"):
        release.main(["--repo", str(git_root), "--release"])
    monkeypatch.delenv("PW_ROUTINE")
    _write(git_root / QWEN_PART, _summary([1], "qwen3-4b"))
    with pytest.raises(SystemExit, match="differ from HEAD"):
        release.main(["--repo", str(git_root), "--release"])


def test_a_scoped_advance_pins_one_models_new_parts_and_keeps_every_existing_entry(git_root, monkeypatch, capsys):
    """Before 2026-11-10 an advance was all-or-nothing: pinning one model's new part pinned every other
    model's backfill in the same write. Hand-authored sets are never pinned: no pin could admit them."""
    monkeypatch.delenv("PW_ROUTINE", raising=False)
    _land_unreleased_original_part(git_root)                                               # qwen3-4b part_04
    _write(git_root / "trace_out" / f"{BATCH}__olmo-2-1b" / "batch_summary.part_01.json", _summary([1], "olmo-2-1b"))
    _write(git_root / "trace_out" / f"{EXPLORATORY}__qwen3-4b" / "batch_summary.part_01.json",
           _summary([1], "qwen3-4b"))
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "landed")
    assert release.main(["--repo", str(git_root), "--release", "--models", "olmo-2-1b"]) == 0
    parts = json.loads((git_root / hold.RELEASE_MANIFEST).read_text())["parts"]
    assert sorted(parts) == [f"trace_out/{BATCH}__olmo-2-1b/batch_summary.part_01.json", QWEN_PART.as_posix()]
    assert "1 new part(s) pinned, 1 kept" in capsys.readouterr().out
    assert release.main(["--repo", str(git_root), "--release"]) == 0                       # the unscoped advance
    parts = json.loads((git_root / hold.RELEASE_MANIFEST).read_text())["parts"]
    assert f"trace_out/{BATCH}__qwen3-4b/batch_summary.part_04.json" in parts
    assert not any(EXPLORATORY in p for p in parts)


def test_every_released_part_is_still_committed_with_its_released_bytes():
    """A released part must never change or vanish: that would move a published number without a release.
    (Parts landed after the last release are simply not listed yet; that is the hold working.)"""
    manifest = hold.load_manifest(ROOT)
    committed = release.committed_logits_parts(ROOT)
    assert len(manifest) >= 409
    assert {p: committed.get(p) for p in manifest} == manifest


def test_the_exporter_candidate_models_and_labels_cover_held_models():
    src = (SCRIPTS / "export_frontend_simulated.py").read_text(encoding="utf-8")
    for m in hold.HELD_MODELS:
        assert f'"{m}"' in src


def test_a_membership_that_includes_the_model_puts_it_in_models_meta(engine_root, tmp_path):
    """The gallery payload follows the analysis membership. A candidate policy whose default membership is
    exploratory-open/1 (named through PW_RESULTS_POLICY, the documented preview route) includes a 2026-10-09
    model with no manifest entry and no code change, and the run says which policy file it used."""
    _land_held_parts(engine_root)
    _write(engine_root / "data" / "simulated" / f"{BATCH}.report.json", {"accepted": 3, "cost_usd": 0.0})
    (engine_root / "trace_out" / BATCH / "index_01.html").write_text("render 1", encoding="utf-8")
    (engine_root / "trace_out" / f"{BATCH}__gemma-4-e2b" / "index_01.html").write_text("render 1", encoding="utf-8")
    candidate = json.loads((ROOT / "data" / "results_policy" / "policy.v1.json").read_text(encoding="utf-8"))
    candidate["default_membership"] = "exploratory-open/1"
    _write(tmp_path / "candidate_policy.json", candidate)

    site = tmp_path / "site"
    (site / "modes" / "simulated").mkdir(parents=True)
    (site / "data").mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "export_frontend_simulated.py"), "--engine", str(engine_root),
         "--frontend", str(site), "--stamps", "20200101T000000Z", "--models", "gemma-2-2b,qwen3-4b,gemma-4-e2b"],
        cwd=engine_root, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PW_RESULTS_POLICY": str(tmp_path / "candidate_policy.json")},
    )
    assert proc.returncode == 0, proc.stderr
    assert "analysis membership exploratory-open/1" in proc.stdout and "policy file overridden" in proc.stdout
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text(encoding="utf-8"))
    gemma4_meta = next(m for m in payload["models_meta"] if m["id"] == "gemma-4-e2b")
    assert gemma4_meta["label"] == "Gemma 4 E2B"
    assert gemma4_meta["available"] is True


def test_gate_fails_closed_on_missing_or_unknown_backend(tmp_path):
    gate = hold.Gate(tmp_path)
    part = tmp_path / "trace_out" / "pairs_A__qwen3-4b" / "batch_summary.part_01.json"
    part.parent.mkdir(parents=True)
    part.write_text("{}", encoding="utf-8")

    # Missing backend
    with pytest.raises(hold.ReleaseError, match="missing required 'backend' key"):
        gate.admit(part, {})

    # Unknown backend
    with pytest.raises(hold.ReleaseError, match="unrecognized backend"):
        gate.admit(part, {"backend": "future_backend"})


def test_committed_logits_parts_refuses_missing_or_unknown_backend(git_root):
    bad_part = git_root / "trace_out" / f"{BATCH}__olmo-2-1b" / "batch_summary.part_01.json"
    _write(bad_part, {"graph_model": "olmo-2-1b"})
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "bad1")
    with pytest.raises(SystemExit, match="missing required 'backend' key"):
        release.committed_logits_parts(git_root)

    _write(bad_part, {"graph_model": "olmo-2-1b", "backend": "unknown_backend"})
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    _git(git_root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "bad2")
    with pytest.raises(SystemExit, match="unrecognized backend"):
        release.committed_logits_parts(git_root)


def test_translation_scale_reads_only_released_logits_parts(engine_root):
    ts = _load("translation_scale")
    corpus = [{"top_prompt": "translated", "bottom_prompt": "patient",
               "target_clinical_token": " alpha", "generation": {"source_batch": BATCH, "source_index": 1}}]
    _write(engine_root / "data" / "simulated" / "txcorpus_A.json", corpus)
    # released part
    _write(engine_root / "trace_out" / "txcorpus_A__qwen3-4b" / "batch_summary.part_01.json",
           {"backend": "logits", "graph_model": "qwen3-4b", "results": [
               {"index": 1, "target_token": 'Output "alpha"',
                "probabilities": {"clinical": 0.5, "patient": 0.2},
                "predictive_spread": {"clinical": [['Output "alpha"', 0.5]], "patient": [['Output "beta"', 0.2]]}}]})
    _manifest(engine_root, [QWEN_PART, "trace_out/txcorpus_A__qwen3-4b/batch_summary.part_01.json"])
    # unreleased part
    _write(engine_root / "trace_out" / "txcorpus_A__olmo-2-1b" / "batch_summary.part_01.json",
           {"backend": "logits", "graph_model": "olmo-2-1b", "results": [
               {"index": 1, "target_token": 'Output "alpha"',
                "probabilities": {"clinical": 0.5, "patient": 0.2},
                "predictive_spread": {"clinical": [['Output "alpha"', 0.5]], "patient": [['Output "beta"', 0.2]]}}]})
    # held model part
    _write(engine_root / "trace_out" / "txcorpus_A__gemma-4-e2b" / "batch_summary.part_01.json",
           {"backend": "logits", "graph_model": "gemma-4-e2b", "results": [
               {"index": 1, "target_token": 'Output "alpha"',
                "probabilities": {"clinical": 0.5, "patient": 0.2},
                "predictive_spread": {"clinical": [['Output "alpha"', 0.5]], "patient": [['Output "beta"', 0.2]]}}]})

    gate = hold.Gate(engine_root)
    out = ts.analyze(engine_root / "trace_out", engine_root / "data" / "simulated", gate=gate)
    assert "qwen3-4b" in out["per_model"]
    assert "olmo-2-1b" not in out["per_model"]
    assert "gemma-4-e2b" not in out["per_model"]
    assert "logits part outside the pinned manifest" in gate.report()
    assert "model gemma-4-e2b" in gate.report()


# ---------------------------------------------------------------- exploratory stimulus sets (rule 3)

EXPLORATORY = "agscen_20990101"


def _land_exploratory_parts(root: Path) -> None:
    """A hosted part and a logits part of an exploratory set over the study batch's own prompts, the logits part
    listed in the release manifest: only the stem keeps them out, and a pooled read would change every output."""
    logits = Path("trace_out") / f"{EXPLORATORY}__model-x" / "batch_summary.part_01.json"
    _write(root / "trace_out" / EXPLORATORY / "batch_summary.part_01.json", _summary([1, 2, 3], "model-x", "hosted"))
    _write(root / logits, _summary([1, 2, 3], "model-x"))
    _manifest(root, [QWEN_PART, logits])


def test_the_gate_refuses_an_exploratory_set_by_stem_whatever_its_release(engine_root):
    assert hold.is_exploratory_run_dir(EXPLORATORY) and hold.is_exploratory_run_dir(f"{EXPLORATORY}__model-x")
    assert hold.is_exploratory_run_dir(f"{EXPLORATORY}__jlens_model-x")
    assert not hold.is_exploratory_run_dir(BATCH) and not hold.is_exploratory_run_dir(f"{BATCH}__model-x")
    _land_exploratory_parts(engine_root)
    gate = hold.Gate(engine_root)
    for run_dir in (EXPLORATORY, f"{EXPLORATORY}__model-x"):
        part = engine_root / "trace_out" / run_dir / "batch_summary.part_01.json"
        assert gate.admit(part, json.loads(part.read_text())) is False
    assert gate.report() == ("membership study-interim/1 (scripts/results_policy.py), parts not read: "
                             "stimulus class hand_authored_exploratory (not a study batch) 2")


def test_urgency_shift_publishes_the_same_bytes_after_an_exploratory_set_lands(engine_root):
    rc, rows_before, site_before, out_before = _urgency(engine_root, "before_x")
    assert rc == 0, out_before
    _land_exploratory_parts(engine_root)
    rc, rows_after, site_after, out_after = _urgency(engine_root, "after_x")
    assert rc == 0, out_after
    assert rows_after == rows_before and site_after == site_before
    assert "stimulus class hand_authored_exploratory (not a study batch) 2" in out_after


def test_the_timeline_and_the_audit_mirror_and_interp_skip_an_exploratory_set(engine_root, monkeypatch):
    _land_exploratory_parts(engine_root)
    tl = _load("study_timeline")
    monkeypatch.chdir(engine_root)
    assert tl.main(["--out", "timeline.json", "--site", ""]) == 0
    totals = json.loads((engine_root / "timeline.json").read_text())["totals"]
    assert totals["trace_summary_parts"] == 2 and totals["held_trace_summary_parts"] == 2
    audit = _load("audit_target_reads")
    loaded = {d: [(p, json.loads(p.read_text())) for p in sorted(d.glob("batch_summary*.json"))]
              for d in sorted((engine_root / "trace_out").iterdir())}
    reads = {part for part, _ in audit.urgency_reads(engine_root, loaded)}
    assert reads and not any(EXPLORATORY in p for p in reads)
    interp = _load("interp_analyses")
    assert {name for name, _ in interp.load_parts(engine_root / "trace_out")} == {BATCH, QWEN_PART.parent.name}


# ---------------------------------------------------------------- pin advance: findings of the 2026-11-10 review

def _commit(root: Path, message: str) -> None:
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "commit.gpgsign=false", "add", "-A")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit",
         "-qm", message)


def test_a_scoped_advance_refuses_without_a_readable_pin_or_for_a_model_with_nothing_to_add(git_root, monkeypatch):
    monkeypatch.delenv("PW_ROUTINE", raising=False)
    _land_unreleased_original_part(git_root)
    _commit(git_root, "landed")
    before = (git_root / hold.RELEASE_MANIFEST).read_bytes()
    with pytest.raises(SystemExit, match="have no unpinned committed logits part"):
        release.main(["--repo", str(git_root), "--release", "--models", "olmo-2-1b"])
    assert (git_root / hold.RELEASE_MANIFEST).read_bytes() == before
    (git_root / hold.RELEASE_MANIFEST).write_text("<<<<<<< merge conflict", encoding="utf-8")
    with pytest.raises(SystemExit, match="a scoped advance extends the existing pin and cannot read it"):
        release.main(["--repo", str(git_root), "--release", "--models", "qwen3-4b"])
    assert (git_root / hold.RELEASE_MANIFEST).read_text(encoding="utf-8") == "<<<<<<< merge conflict"


def test_a_scoped_advance_never_drops_an_existing_pin(git_root, monkeypatch, capsys):
    monkeypatch.delenv("PW_ROUTINE", raising=False)
    manifest = json.loads((git_root / hold.RELEASE_MANIFEST).read_text())
    manifest["parts"]["trace_out/pairs_gone__qwen3-4b/batch_summary.part_01.json"] = "0" * 64   # no longer committed
    _write(git_root / hold.RELEASE_MANIFEST, manifest)
    _land_unreleased_original_part(git_root)
    _commit(git_root, "landed")
    assert release.main(["--repo", str(git_root), "--release", "--models", "qwen3-4b"]) == 0
    parts = json.loads((git_root / hold.RELEASE_MANIFEST).read_text())["parts"]
    assert "trace_out/pairs_gone__qwen3-4b/batch_summary.part_01.json" in parts and len(parts) == 3
    out = capsys.readouterr().out
    assert "1 new part(s) pinned, 2 kept (1 of them name a part that is no longer committed or admissible" in out


def test_no_advance_rewrites_the_hash_of_a_part_whose_committed_bytes_changed(git_root, monkeypatch):
    """A recorded hash is never rewritten: before 2026-11-10 an unscoped release replaced it with the new
    bytes' hash, which let a modified part stand in for the one that was pinned."""
    monkeypatch.delenv("PW_ROUTINE", raising=False)
    _write(git_root / QWEN_PART, _summary([1, 2, 3, 3], "qwen3-4b"))
    _commit(git_root, "a pinned part rewritten and committed")
    before = (git_root / hold.RELEASE_MANIFEST).read_bytes()
    for argv in (["--release"], ["--release", "--models", "qwen3-4b"]):
        with pytest.raises(SystemExit, match="differ from their recorded sha256"):
            release.main(["--repo", str(git_root), *argv])
    assert (git_root / hold.RELEASE_MANIFEST).read_bytes() == before


def test_a_preview_override_cannot_let_the_routine_advance_the_pin(git_root, monkeypatch, tmp_path):
    candidate = json.loads((ROOT / "data" / "results_policy" / "policy.v1.json").read_text(encoding="utf-8"))
    candidate["analysis_pin"]["auto_advance"] = True
    _write(tmp_path / "candidate.json", candidate)
    monkeypatch.setenv("PW_ROUTINE", "1")
    monkeypatch.setenv("PW_RESULTS_POLICY", str(tmp_path / "candidate.json"))
    with pytest.raises(SystemExit, match="never the Routine's action while analysis_pin.auto_advance is false"):
        release.main(["--repo", str(git_root), "--release"])
