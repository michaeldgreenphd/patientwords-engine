"""Render pruning (scripts/render_prune.py, wired into export_frontend_simulated.py).

Owner ruling 2 (2026-09-23): the exporter prunes renders no export lists. A
render of a withheld Tier B holdout row stayed served from 2026-07-12 because the
exporter copied renders and never removed one. Pins, on synthetic engine and
site trees with abstract phrases only:

- only files matching the exporter's own naming under modes/simulated/ are
  candidates; other modes/ subtrees, preview files and hand-placed directories
  are never touched;
- a render the new payload lists, or any other site file names, is kept; the
  payload being replaced does not keep a render alive;
- --dry-run writes, copies and deletes nothing and lists what would go;
- the summary reports the count;
- a site checkout that keeps tracked renders off disk (a sparse clone that
  excludes modes/) makes the exporter refuse before writing anything.
"""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rp = _load("render_prune")

STAMP = "20260801T000000Z"
STEM = f"pairs_{STAMP}"
OLD = "pairs_20260701T000000Z"


def _hold(p):
    return int(hashlib.sha1(p.encode()).hexdigest(), 16) % 10 == 0


def _phrase(base, holdout):
    return next(f"{base} {i} so a" for i in range(500) if _hold(f"{base} {i} so a") == holdout)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _result(index, clinical):
    return {"index": index, "prompts": {"clinical": clinical, "patient": f"{clinical} plain"},
            "probabilities": {"clinical": 0.4, "patient": 0.2}, "language_penalty": -0.2,
            "target_token": 'Output " tok"',
            "predictive_spread": {"clinical": [['Output " tok"', 0.4]], "patient": [['Output " other"', 0.3]]}}


def build(tmp_path):
    engine, site = tmp_path / "engine", tmp_path / "site"
    rows = [_phrase("zq open words", False), _phrase("zq more open words", False),
            _phrase("zq sealed words", True)]
    _write(engine / "ops" / "dashboard.json", json.dumps({"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}))
    _write(engine / "data" / "simulated" / f"{STEM}.json", json.dumps(
        [{"top_prompt": r, "bottom_prompt": f"{r} plain", "target_clinical_token": " tok"} for r in rows]))
    _write(engine / "data" / "simulated" / f"{STEM}.report.json", json.dumps({"accepted": 3}))
    trace = engine / "trace_out" / STEM
    _write(trace / "batch_summary.part_01.json", json.dumps(
        {"graph_model": "gemma-2-2b", "results": [_result(i, r) for i, r in enumerate(rows, start=1)]}))
    for i in (1, 2, 3):
        _write(trace / f"index_{i:02d}.html", f"<html>render {i}</html>")
    sim = site / "modes" / "simulated"
    files = {
        "listed_stale_copy": _write(sim / STEM / "index_01.html", "<html>old copy</html>"),
        "holdout_render": _write(sim / STEM / "index_03.html", "<html>withheld row</html>"),
        "old_png": _write(sim / OLD / "index_07.png", "png"),
        "page_linked": _write(sim / OLD / "index_08.html", "<html>linked</html>"),
        "model_render": _write(sim / f"{STEM}__qwen3-4b" / "index_02.html", "<html>m</html>"),
        "featured": _write(sim / "featured_sim85" / "index_01.html", "<html>f</html>"),
        "preview": _write(sim / "preview.html", "<html>p</html>"),
        "notes": _write(sim / STEM / "notes.txt", "hand note"),
        "other_mode": _write(site / "modes" / "2panel" / "index_09.html", "<html>2</html>"),
    }
    _write(site / "start-here" / "index.html", f'<a href="../modes/simulated/{OLD}/index_08.html">x</a>')
    # the payload about to be replaced still lists the holdout render: it must not keep it alive
    _write(site / "data" / "simulated_scenarios.json",
           json.dumps({"scenarios": [{"html": f"modes/simulated/{STEM}/index_03.html"}]}))
    return engine, site, files


def export(engine, site, *extra):
    return subprocess.run([sys.executable, str(_ROOT / "scripts" / "export_frontend_simulated.py"),
                           "--engine", str(engine), "--frontend", str(site), "--stamps", STAMP, *extra],
                          capture_output=True, text=True, cwd=str(engine))


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_render_pattern_is_the_exporters_naming_only():
    ok = [f"modes/simulated/{STEM}/index_01.html", f"modes/simulated/{STEM}/index_120.png",
          f"modes/simulated/{STEM}__gemma-3-4b-it/index_07.html"]
    no = ["modes/simulated/preview.html", "modes/simulated/featured_sim85/index_01.html",
          "modes/simulated/dialects_20260708T011831Z/index_01.html", f"modes/2panel/{STEM}/index_01.html",
          f"modes/simulated/{STEM}/notes.txt", f"modes/simulated/{STEM}/index_1.html"]
    assert all(rp.RENDER_RE.match(p) for p in ok)
    assert not any(rp.RENDER_RE.match(p) for p in no)


def test_candidates_exclude_listed_and_referenced(tmp_path):
    _, site, _ = build(tmp_path)
    cands = rp.prune_candidates(site, {f"modes/simulated/{STEM}/index_01.html"},
                                ignore={"data/simulated_scenarios.json"})
    assert cands == [f"modes/simulated/{OLD}/index_07.png",
                     f"modes/simulated/{STEM}/index_03.html",
                     f"modes/simulated/{STEM}__qwen3-4b/index_02.html"]
    # without the ignore, the stale payload would keep the holdout render alive
    assert f"modes/simulated/{STEM}/index_03.html" not in rp.prune_candidates(
        site, {f"modes/simulated/{STEM}/index_01.html"})


def test_prune_refuses_a_path_outside_the_pattern(tmp_path):
    (tmp_path / "modes" / "simulated").mkdir(parents=True)
    try:
        rp.prune(tmp_path, ["modes/simulated/preview.html"], dry_run=False)
    except ValueError as exc:
        assert "non-render" in str(exc)
    else:
        raise AssertionError("pruned a non-render path")


def test_dry_run_changes_nothing_and_lists_the_prune_set(tmp_path):
    engine, site, _ = build(tmp_path)
    before = snapshot(site)
    proc = export(engine, site, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert snapshot(site) == before
    out = proc.stdout
    assert "3 unlisted render(s) would be pruned" in out and "DRY RUN" in out
    for rel in (f"modes/simulated/{OLD}/index_07.png", f"modes/simulated/{STEM}/index_03.html",
                f"modes/simulated/{STEM}__qwen3-4b/index_02.html"):
        assert f"would prune {rel}" in out


def test_export_prunes_unlisted_renders_and_nothing_else(tmp_path):
    engine, site, files = build(tmp_path)
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    assert "3 unlisted render(s) pruned" in proc.stdout
    assert "1 confirmatory-holdout pairs withheld" in proc.stdout
    for gone in ("holdout_render", "old_png", "model_render"):
        assert not files[gone].exists(), gone
    for kept in ("listed_stale_copy", "page_linked", "featured", "preview", "notes", "other_mode"):
        assert files[kept].exists(), kept
    assert files["listed_stale_copy"].read_text() == "<html>render 1</html>"   # re-copied
    assert not (site / "modes" / "simulated" / f"{STEM}__qwen3-4b").exists()      # emptied dir removed
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text())
    assert payload["holdout_withheld"] == 1
    assert {s["html"] for s in payload["scenarios"]} == {
        f"modes/simulated/{STEM}/index_01.html", f"modes/simulated/{STEM}/index_02.html"}
    # a second run is a no-op for pruning
    again = export(engine, site)
    assert again.returncode == 0 and "0 unlisted render(s) pruned" in again.stdout


# --- a site checkout that keeps renders off disk (2026-09-23 review) ---------- #
# The cloud containers clone the site with a sparse checkout that excludes
# modes/ (docs/fresh_session_bootstrap.md). The prune reads the working tree, so
# it pruned nothing there and printed "0 unlisted render(s) pruned".

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(cwd, *argv):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *argv],
                   cwd=str(cwd), check=True, capture_output=True)


def _commit_site(site):
    _git(site, "init", "-q")
    _git(site, "add", "-A")
    _git(site, "commit", "-qm", "site")


@needs_git
def test_export_refuses_a_sparse_site_checkout_and_writes_nothing(tmp_path):
    engine, site, files = build(tmp_path)
    _commit_site(site)
    _git(site, "sparse-checkout", "set", "--no-cone", "/*", "!/modes/")
    assert not (site / "modes").exists()
    assert rp.hidden_renders(site) == [f"modes/simulated/{OLD}/index_07.png",
                                       f"modes/simulated/{OLD}/index_08.html",
                                       f"modes/simulated/{STEM}/index_01.html",
                                       f"modes/simulated/{STEM}/index_03.html",
                                       f"modes/simulated/{STEM}__qwen3-4b/index_02.html"]
    before = snapshot(site)
    for extra in ((), ("--dry-run",)):
        proc = export(engine, site, *extra)
        assert proc.returncode != 0, extra
        assert "5 render(s)" in proc.stderr and "sparse-checkout disable" in proc.stderr
        assert "pruned" not in proc.stdout
        assert snapshot(site) == before
    _git(site, "sparse-checkout", "disable")
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    assert "3 unlisted render(s) pruned" in proc.stdout
    assert not files["holdout_render"].exists()


@needs_git
def test_a_pruned_but_uncommitted_render_does_not_block_a_rerun(tmp_path):
    # Deleted from disk without the skip-worktree bit is a pending deletion,
    # not a hidden file: re-running the exporter before the commit must work.
    engine, site, _ = build(tmp_path)
    _commit_site(site)
    assert export(engine, site).returncode == 0
    again = export(engine, site)
    assert again.returncode == 0, again.stderr
    assert "0 unlisted render(s) pruned" in again.stdout


@needs_git
def test_hidden_tracked_reads_the_skip_worktree_bit(tmp_path):
    sg = _load("sparse_guard")
    site = tmp_path / "site"
    _write(site / "modes" / "simulated" / STEM / "index_01.html", "x")
    _write(site / "data" / "a.json", "{}")
    assert sg.hidden_tracked(site) == []                   # not a git work tree
    assert sg.hidden_tracked(tmp_path / "absent") == []
    _commit_site(site)
    assert sg.hidden_tracked(site) == []                   # full checkout
    _git(site, "update-index", "--skip-worktree", "data/a.json")
    assert sg.hidden_tracked(site) == ["data/a.json"]
    assert sg.hidden_tracked(site, "modes/simulated") == []
    assert rp.hidden_renders(site) == []


# --- an unreadable reference file (Codex review of PR #32, 2026-09-23) -------- #
# referenced_renders skipped a file it could not read, so a render named only
# there looked unlisted and was pruned: a committed link broken by the export.


def _unreadable(path):
    """chmod 000 and confirm it took (root, or a filesystem that ignores modes, reads anyway)."""
    path.chmod(0)
    try:
        if path.is_dir():
            list(path.iterdir())
        else:
            path.read_bytes()
    except PermissionError:
        return True
    path.chmod(0o755 if path.is_dir() else 0o644)
    return False


def test_an_unreadable_reference_file_or_dir_refuses_the_scan(tmp_path):
    _, site, _ = build(tmp_path)
    page = site / "start-here" / "index.html"
    if not _unreadable(page):
        pytest.skip("permissions are not enforced here")
    try:
        for fn in (lambda: rp.referenced_renders(site),
                   lambda: rp.prune_candidates(site, set(), ignore={"data/simulated_scenarios.json"})):
            with pytest.raises(rp.ReferenceScanError, match="start-here/index.html"):
                fn()
    finally:
        page.chmod(0o644)
    assert f"modes/simulated/{OLD}/index_08.html" in rp.referenced_renders(site)
    locked = site / "start-here"
    assert _unreadable(locked)
    try:
        with pytest.raises(rp.ReferenceScanError, match="start-here"):
            rp.referenced_renders(site)
    finally:
        locked.chmod(0o755)


def test_export_refuses_before_writing_when_a_reference_file_is_unreadable(tmp_path):
    engine, site, files = build(tmp_path)
    page = site / "start-here" / "index.html"
    before = snapshot(site)
    if not _unreadable(page):
        pytest.skip("permissions are not enforced here")
    try:
        for extra in ((), ("--dry-run",)):
            proc = export(engine, site, *extra)
            assert proc.returncode != 0, extra
            assert "start-here/index.html" in proc.stderr and "pruned" not in proc.stdout
    finally:
        page.chmod(0o644)
    assert snapshot(site) == before                  # nothing copied, written or pruned
    assert files["page_linked"].exists()
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    assert files["page_linked"].exists() and "3 unlisted render(s) pruned" in proc.stdout


# --- an engine render source missing from disk (Codex review of PR #32, 2026-09-24) #
# The fresh-session repair (docs/fresh_session_bootstrap.md) restores only the
# batch_summary*.json files under trace_out/. With the summaries present and a
# render off disk, the export listed no render for that scenario, and the prune
# then deleted the site's valid copy as unlisted: exit 0, a published render gone.


def test_export_refuses_when_an_engine_render_is_missing_but_the_site_has_a_copy(tmp_path):
    engine, site, files = build(tmp_path)
    source = engine / "trace_out" / STEM / "index_01.html"
    source.unlink()                                  # a partial engine checkout: summaries only
    before = snapshot(site)
    for extra in ((), ("--dry-run",)):
        proc = export(engine, site, *extra)
        assert proc.returncode != 0, extra
        assert f"modes/simulated/{STEM}/index_01.html" in proc.stderr and "1 render(s)" in proc.stderr
        assert "pruned" not in proc.stdout
        assert snapshot(site) == before              # nothing copied, written or pruned
    _write(source, "<html>render 1</html>")
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    assert files["listed_stale_copy"].read_text() == "<html>render 1</html>"


def test_a_missing_png_source_with_a_site_copy_refuses_only_when_pngs_are_published(tmp_path):
    engine, site, _ = build(tmp_path)
    png = _write(site / "modes" / "simulated" / STEM / "index_01.png", "png")
    proc = export(engine, site, "--with-pngs")       # the engine has no PNGs (they live in Releases)
    assert proc.returncode != 0 and f"modes/simulated/{STEM}/index_01.png" in proc.stderr
    assert png.exists()
    proc = export(engine, site)                      # HTML-only: the PNG is not a render this export lists
    assert proc.returncode == 0, proc.stderr
    assert not png.exists()


def test_a_missing_engine_render_with_no_site_copy_still_exports_data_only(tmp_path):
    engine, site, _ = build(tmp_path)
    (engine / "trace_out" / STEM / "index_02.html").unlink()     # never published: nothing to lose
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads((site / "data" / "simulated_scenarios.json").read_text())
    assert [s.get("html") for s in payload["scenarios"]] == [f"modes/simulated/{STEM}/index_01.html", None]


def test_a_missing_model_render_with_a_site_copy_refuses_under_preview_models_all(tmp_path):
    engine, site, files = build(tmp_path)
    mdir = engine / "trace_out" / f"{STEM}__qwen3-4b"
    _write(mdir / "batch_summary.part_01.json", json.dumps(
        {"graph_model": "qwen3-4b", "results": [_result(2, json.loads(
            (engine / "trace_out" / STEM / "batch_summary.part_01.json").read_text())["results"][1]["prompts"]
            ["clinical"])]}))
    proc = export(engine, site, "--models", "gemma-2-2b,qwen3-4b", "--preview-models", "all")
    assert proc.returncode != 0 and f"modes/simulated/{STEM}__qwen3-4b/index_02.html" in proc.stderr
    assert files["model_render"].exists()
    _write(mdir / "index_02.html", "<html>m2</html>")
    proc = export(engine, site, "--models", "gemma-2-2b,qwen3-4b", "--preview-models", "all")
    assert proc.returncode == 0, proc.stderr
    assert files["model_render"].read_text() == "<html>m2</html>"


# --- a sparse checkout that hides a reference file (Codex review of PR #32, 2026-09-24) #
# The sparse guard asked git only about modes/simulated/. A checkout that kept
# the renders but excluded a page naming one (start-here/) let the scan miss the
# page, and the render it names was pruned as unlisted.


@needs_git
def test_export_refuses_when_the_checkout_hides_a_reference_file(tmp_path):
    engine, site, files = build(tmp_path)
    _commit_site(site)
    _git(site, "sparse-checkout", "set", "--no-cone", "/*", "!/start-here/")
    assert not (site / "start-here").exists() and files["page_linked"].exists()
    assert rp.hidden_renders(site) == []
    before = snapshot(site)
    for extra in ((), ("--dry-run",)):
        proc = export(engine, site, *extra)
        assert proc.returncode != 0, extra
        assert "start-here/index.html" in proc.stderr and "sparse-checkout disable" in proc.stderr
        assert "pruned" not in proc.stdout
        assert snapshot(site) == before
    _git(site, "sparse-checkout", "disable")
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    assert files["page_linked"].exists() and "3 unlisted render(s) pruned" in proc.stdout


@needs_git
def test_hidden_references_are_the_files_the_scan_would_read(tmp_path):
    _, site, _ = build(tmp_path)
    _write(site / "assets" / "logo.png", "png")
    _commit_site(site)
    for rel in ("start-here/index.html", "assets/logo.png", "data/simulated_scenarios.json",
                f"modes/simulated/{OLD}/index_08.html", "modes/simulated/preview.html"):
        _git(site, "update-index", "--skip-worktree", rel)
    # a binary asset and a render are never scanned, and the ignored payload is not read
    assert rp.hidden_references(site, {"data/simulated_scenarios.json"}) == [
        "modes/simulated/preview.html", "start-here/index.html"]
    assert rp.hidden_references(site) == [
        "data/simulated_scenarios.json", "modes/simulated/preview.html", "start-here/index.html"]
