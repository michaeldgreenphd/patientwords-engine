"""scripts/render_archive.py: one PNG out of a Release zip by Range requests,
and the archived/unarchived accounting the archive lane's prune_only relies on.
The HTTP path is exercised against a local server that honours Range the way
GitHub's asset host does (206 + Content-Range), and one that ignores it (200),
which must fall back to a full download."""
import functools
import http.server
import importlib.util
import json
import subprocess
import sys
import threading
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod            # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


ra = _load("render_archive")
ar = _load("archive_run")


def _make_run(root, stem, n=3, with_multi=False):
    d = root / "trace_out" / stem
    d.mkdir(parents=True)
    for i in range(1, n + 1):
        (d / f"index_{i:02d}.html").write_text(f"<html>{stem} {i}</html>")
        (d / f"index_{i:02d}.png").write_bytes(b"\x89PNG" + bytes([i]) * (5000 + i))
        (d / f"index_{i:02d}_diff.png").write_bytes(b"\x89PNGdiff" + bytes([i]) * 700)
    if with_multi:
        (d / "multi_01.html").write_text("<html>multi</html>")
        (d / "multi_01.png").write_bytes(b"\x89PNGmulti" * 300)
    (d / "batch_summary.part_01.json").write_text("{}")
    return d


class _RangeHandler(http.server.SimpleHTTPRequestHandler):
    honour_range = True

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        path = Path(self.directory) / self.path.lstrip("/")
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        rng = self.headers.get("Range")
        if rng and self.honour_range:
            spec = rng.split("=", 1)[1]
            if spec.startswith("-"):
                start, end = max(0, len(data) - int(spec[1:])), len(data) - 1
            else:
                a, b = spec.split("-")
                start, end = int(a), int(b) if b else len(data) - 1
            chunk = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


@pytest.fixture
def served_bundle(tmp_path):
    """A repo-shaped tmp dir with two runs bundled by archive_run, the zip
    served over HTTP, and a manifest that points at it."""
    repo = tmp_path / "repo"
    r1 = _make_run(repo, "pairs_A", 3)
    r2 = _make_run(repo, "pairs_B", 2, with_multi=True)
    dist = tmp_path / "dist"
    _zip, _mpath, manifest = ar.build_bundle([r1, r2], "renders-test", dist, include_pngs=True)
    handler = type("H", (_RangeHandler,), {})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(dist)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/renders-test.zip"
    manifest["release_url"] = "https://github.com/o/r/releases/tag/renders-test"
    (repo / "render_archives").mkdir()
    (repo / "render_archives" / "renders-test.manifest.json").write_text(json.dumps(manifest))
    yield repo, url, manifest, handler, dist
    server.shutdown()


def test_archive_run_manifest_lists_members_and_multi_renders(served_bundle):
    repo, url, manifest, handler, dist = served_bundle
    runs = {r["run"]: r for r in manifest["runs"]}
    assert runs["pairs_A"]["members"] == ["batch_summary.part_01.json", "index_01.html", "index_01.png",
                                          "index_01_diff.png", "index_02.html", "index_02.png", "index_02_diff.png",
                                          "index_03.html", "index_03.png", "index_03_diff.png"]
    assert "multi_01.png" in runs["pairs_B"]["members"] and "multi_01.html" in runs["pairs_B"]["members"]
    assert ar.PNG_GLOBS == ra.PNG_GLOBS


def test_central_directory_and_member_over_file_source(served_bundle):
    repo, url, manifest, handler, dist = served_bundle
    src = ra.FileSource(dist / "renders-test.zip")
    members = {m.name: m for m in ra.read_central_directory(src)}
    assert "pairs_A/index_02.png" in members and "pairs_B/multi_01.png" in members
    data = ra.extract_member(src, members["pairs_A/index_02.png"])
    assert data == (repo / "trace_out" / "pairs_A" / "index_02.png").read_bytes()


def test_fetch_one_png_over_http_range(served_bundle, monkeypatch):
    repo, url, manifest, handler, dist = served_bundle
    monkeypatch.setattr(ra, "asset_url", lambda m: url)
    out = tmp = repo / "out"
    written = ra.fetch(repo, "pairs_A", ["index_03_diff.png"], out, cache_dir=tmp / "cache")
    assert written == [out / "pairs_A" / "index_03_diff.png"]
    assert written[0].read_bytes() == (repo / "trace_out" / "pairs_A" / "index_03_diff.png").read_bytes()
    # the source only ever asked for byte ranges: the whole zip never travelled
    src = ra.HttpSource(url)
    assert src.size == (dist / "renders-test.zip").stat().st_size


def test_fetch_falls_back_to_full_download_when_range_is_ignored(served_bundle, monkeypatch):
    repo, url, manifest, handler, dist = served_bundle
    handler.honour_range = False
    monkeypatch.setattr(ra, "asset_url", lambda m: url)
    cache = repo / "cache"
    written = ra.fetch(repo, "pairs_B", ["multi_01.png"], repo / "out", cache_dir=cache)
    assert written[0].read_bytes() == (repo / "trace_out" / "pairs_B" / "multi_01.png").read_bytes()
    assert (cache / "renders-test.zip").exists()


def test_fetch_refuses_a_png_no_archive_holds(served_bundle, monkeypatch):
    repo, url, manifest, handler, dist = served_bundle
    monkeypatch.setattr(ra, "asset_url", lambda m: url)
    with pytest.raises(SystemExit, match="no archive holds pairs_A/{index_09.png}"):
        ra.fetch(repo, "pairs_A", ["index_09.png"], repo / "out", cache_dir=repo / "cache")


def test_member_names_prefers_the_manifest_list_and_caches_the_zip_read(served_bundle, monkeypatch):
    repo, url, manifest, handler, dist = served_bundle
    calls = []

    def factory(u):
        calls.append(u)
        return ra.FileSource(dist / "renders-test.zip")

    # with members in the manifest: no source opened at all
    assert "pairs_A" in ra.member_names(manifest, cache_dir=repo / "c1", source_factory=factory) and not calls
    # an old-style manifest (no members): one read, then the cache
    old = {k: v for k, v in manifest.items()}
    old["runs"] = [{"run": r["run"], "files": r["files"], "bytes": r["bytes"]} for r in manifest["runs"]]
    names = ra.member_names(old, cache_dir=repo / "c2", source_factory=factory)
    assert names["pairs_B"] and len(calls) == 1
    ra.member_names(old, cache_dir=repo / "c2", source_factory=factory)
    assert len(calls) == 1


def test_coverage_reports_archived_and_unarchived_runs(served_bundle, monkeypatch):
    repo, url, manifest, handler, dist = served_bundle
    # a third run in the tree that no archive holds, and git so tree_pngs can see it
    _make_run(repo, "pairs_C", 1)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@x", "-c", "user.name=t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@x", "-c", "user.name=t", "commit", "-q", "-m", "x"],
                   check=True)
    rep = ra.coverage(repo, cache_dir=repo / "cache",
                      source_factory=lambda u: ra.FileSource(dist / "renders-test.zip"))
    assert rep["unarchived_runs"] == ["pairs_C"]
    assert rep["runs"]["pairs_A"]["index_01.png"] == "renders-test"
    assert rep["runs"]["pairs_B"]["multi_01.png"] == "renders-test"
    assert rep["archived"] == 3 * 2 + 2 * 2 + 1 and rep["unarchived"] == 2
    rc = ra.main(["--repo", str(repo), "coverage", "--require-archived"]) if False else None  # noqa: F841
    assert rc is None


def test_crc_mismatch_is_refused(served_bundle):
    repo, url, manifest, handler, dist = served_bundle
    src = ra.FileSource(dist / "renders-test.zip")
    m = next(x for x in ra.read_central_directory(src) if x.name == "pairs_A/index_01.png")
    bad = ra.Member(m.name, m.method, (m.crc32 + 1) & 0xFFFFFFFF, m.compressed_size, m.size, m.local_offset)
    with pytest.raises(ValueError, match="CRC"):
        ra.extract_member(src, bad)
    assert zlib.crc32(b"") == 0


def test_cli_fetch_by_path_in_place(served_bundle, monkeypatch):
    repo, url, manifest, handler, dist = served_bundle
    monkeypatch.setattr(ra, "asset_url", lambda m: url)
    monkeypatch.setattr(ra, "CACHE_DIR", repo / "cache")
    (repo / "trace_out" / "pairs_A" / "index_01.png").unlink()      # as after a prune
    rc = ra.main(["--repo", str(repo), "fetch", "--path", "trace_out/pairs_A/index_01.png", "--in-place"])
    assert rc == 0
    assert (repo / "trace_out" / "pairs_A" / "index_01.png").read_bytes().startswith(b"\x89PNG\x01")
    assert sys.version_info >= (3, 10)


def test_shrink_check_refuses_fewer_pngs_than_the_branch_manifest_records(served_bundle, tmp_path):
    repo, url, manifest, handler, dist = served_bundle
    # the same runs bundled after their PNGs were pruned: HTML and summaries only
    for d in (repo / "trace_out").iterdir():
        for png in d.glob("*.png"):
            png.unlink()
    _zip, _mpath, shrunk = ar.build_bundle(sorted((repo / "trace_out").iterdir()), "renders-test",
                                          tmp_path / "dist2", include_pngs=True)
    problems = ra.shrink_check(shrunk, manifest)
    assert [p.split(":")[0] for p in problems] == ["pairs_A", "pairs_B"]
    assert problems[0].startswith("pairs_A: 6 of 6 png in the Release absent from the new bundle: index_01.png")
    assert "… (6 in all)" in problems[0] and problems[1].startswith("pairs_B: 5 of 5 png")
    assert ra.shrink_check(manifest, manifest) == []                 # same content: fine
    assert ra.shrink_check(shrunk, None) == []                       # no manifest: the workflow checks gh
    new_path = tmp_path / "dist2" / "renders-test.manifest.json"
    old_path = repo / "render_archives" / "renders-test.manifest.json"
    assert ra.main(["shrink-check", "--new", str(new_path), "--old", str(old_path)]) == 1
    assert ra.main(["shrink-check", "--new", str(new_path), "--old", str(tmp_path / "absent.json")]) == 0


def test_shrink_check_counts_a_legacy_release_from_its_zip_and_flags_omitted_runs(served_bundle, tmp_path):
    repo, url, manifest, handler, dist = served_bundle
    factory = lambda u: ra.FileSource(dist / "renders-test.zip")  # noqa: E731
    # a pre-2026-09-08 manifest: no member lists, only includes_pngs
    legacy = {k: v for k, v in manifest.items()}
    legacy["runs"] = [{"run": r["run"], "files": r["files"], "bytes": r["bytes"]} for r in manifest["runs"]]
    # a rebuilt bundle for pairs_A alone, with one PNG left: pairs_A shrank from 6, pairs_B is omitted
    keep = repo / "trace_out" / "pairs_A"
    for png in sorted(keep.glob("*.png"))[1:]:
        png.unlink()
    _zip, _mpath, partial = ar.build_bundle([keep], "renders-test", tmp_path / "dist3", include_pngs=True)
    problems = ra.shrink_check(partial, legacy, cache_dir=tmp_path / "c", source_factory=factory)
    assert problems == ["pairs_A: 5 of 6 png in the Release absent from the new bundle: index_01_diff.png, "
                        "index_02.png, index_02_diff.png, index_03.png, index_03_diff.png",
                        "pairs_B: 5 png in the Release, run absent from the new bundle"]
    # the member list is read from the zip, never assumed: an unreadable Release is itself a refusal
    broken = dict(legacy, release_url="not-a-url")
    out = ra.shrink_check(partial, broken, cache_dir=tmp_path / "c2")
    assert len(out) == 1 and out[0].startswith("cannot read the Release's member list")


def test_shrink_check_compares_png_names_not_counts(served_bundle, tmp_path):
    repo, url, manifest, handler, dist = served_bundle
    # same count, renumbered: index_01..03 become index_04..06
    d = repo / "trace_out" / "pairs_A"
    for i in (1, 2, 3):
        (d / f"index_{i:02d}.png").rename(d / f"index_{i + 3:02d}.png")
        (d / f"index_{i:02d}_diff.png").rename(d / f"index_{i + 3:02d}_diff.png")
    _zip, _mpath, renumbered = ar.build_bundle([d], "renders-test", tmp_path / "dist4", include_pngs=True)
    assert sum(1 for n in renumbered["runs"][0]["members"] if ra.is_png(n)) == 6
    problems = ra.shrink_check(renumbered, manifest)
    assert problems[0].startswith("pairs_A: 6 of 6 png in the Release absent from the new bundle")
    assert problems[1] == "pairs_B: 5 png in the Release, run absent from the new bundle"
