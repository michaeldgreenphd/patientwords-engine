#!/usr/bin/env python3
"""Fetch archived render PNGs on demand, and account for which PNGs are archived.

The engine's PNG renders (index_NN.png, index_NN_diff.png, the register and
variety edge panels, multi_NN.png) are the heaviest thing in the tree, roughly
15 GB at HEAD in September 2026, and nothing serves them: the public site has
been HTML-only since 2026-07-21 and the traces site copies HTML. Their durable
home is the GitHub Releases the archive lane writes (docs/archiving.md), each a
zip built by scripts/archive_run.py with a manifest committed under
render_archives/. Once a run's PNGs are in a Release they are pruned from git.

This module is the way back: it reads one member out of a Release zip without
downloading the zip, using HTTP Range requests against the asset (the central
directory is read from the tail of the file, then the one member's bytes), and
it reports, for every PNG still in the tree, which archive holds it or that
none does.

    python scripts/render_archive.py fetch --run pairs_20260707T215921Z --index 7
    python scripts/render_archive.py fetch --run pairs_20260707T215921Z --index 7 --variant diff
    python scripts/render_archive.py fetch --path trace_out/pairs_20260707T215921Z/index_07.png --in-place
    python scripts/render_archive.py fetch --run pairs_20260707T215921Z --all
    python scripts/render_archive.py coverage            # every tree PNG -> archive tag or UNARCHIVED
    python scripts/render_archive.py index --tag renders-20260721-pt3

Fetched files go to dist/renders/<run>/ unless --in-place puts them beside
their HTML under trace_out/, where git sees them as untracked. Manifests
written after 2026-09-08 carry a per-run member list, so a lookup needs no
network; for the older ones the member list is read once from the zip's
central directory and cached under ~/.cache/patientwords-engine/render_index/.
Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

PNG_GLOBS = ("index_*.png", "multi_*.png")
MANIFEST_DIR = Path("render_archives")
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "patientwords-engine" / "render_index"
TAIL_BYTES = 64 * 1024

# ---------------------------------------------------------------------------
# Range sources
# ---------------------------------------------------------------------------


class RangeSource:
    """Random access to a byte string of known size. Two implementations: a
    local file (tests, and the fallback after a full download) and an HTTP
    asset that honours Range requests."""

    size: int

    def read(self, offset: int, length: int) -> bytes:
        raise NotImplementedError

    def tail(self, length: int) -> bytes:
        length = min(length, self.size)
        return self.read(self.size - length, length)


class FileSource(RangeSource):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.size = self.path.stat().st_size

    def read(self, offset: int, length: int) -> bytes:
        with self.path.open("rb") as fh:
            fh.seek(offset)
            return fh.read(length)


class HttpSource(RangeSource):
    """A Release asset. GitHub answers the download URL with a redirect to a
    signed object URL that supports explicit byte ranges (probed 2026-09-08:
    206 on `bytes=0-15`) but answers a suffix range (`bytes=-N`) with 501, so
    the size is learned from a one-byte request's Content-Range and the tail
    is then read by explicit offsets."""

    def __init__(self, url: str, timeout: float = 60.0) -> None:
        self.url = url
        self.timeout = timeout
        self.size = self._probe_size()

    def _request(self, range_header: str) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(self.url, headers={"Range": range_header, "User-Agent": "patientwords-engine"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - fixed https host
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (416, 501):
                raise RangeUnsupported(exc.code, b"") from exc
            raise

    def _probe_size(self) -> int:
        status, headers, body = self._request("bytes=0-0")
        if status == 206:
            m = re.search(r"/(\d+)\s*$", headers.get("Content-Range", ""))
            if not m:
                raise RuntimeError(f"no Content-Range in a 206 response from {self.url}")
            return int(m.group(1))
        raise RangeUnsupported(status, body)

    def read(self, offset: int, length: int) -> bytes:
        if length <= 0:
            return b""
        status, _headers, body = self._request(f"bytes={offset}-{offset + length - 1}")
        if status != 206:
            raise RangeUnsupported(status, body)
        return body


class RangeUnsupported(Exception):
    """The server answered a Range request with a full body (200) or an
    error; the caller downloads the whole asset instead."""

    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(f"HTTP {status} to a Range request")
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# Zip central directory over a RangeSource
# ---------------------------------------------------------------------------

EOCD_SIG = b"PK\x05\x06"
EOCD64_LOC_SIG = b"PK\x06\x07"
EOCD64_SIG = b"PK\x06\x06"
CDIR_SIG = b"PK\x01\x02"
LOCAL_SIG = b"PK\x03\x04"


@dataclass(frozen=True)
class Member:
    name: str
    method: int
    crc32: int
    compressed_size: int
    size: int
    local_offset: int


def _parse_zip64_extra(extra: bytes, usize: int, csize: int, offset: int) -> tuple[int, int, int]:
    pos = 0
    while pos + 4 <= len(extra):
        tag, length = struct.unpack_from("<HH", extra, pos)
        data = extra[pos + 4:pos + 4 + length]
        if tag == 0x0001:
            fields = []
            for value in (usize, csize, offset):
                if value == 0xFFFFFFFF and len(data) >= 8 * (len(fields) + 1):
                    fields.append(struct.unpack_from("<Q", data, 8 * len(fields))[0])
                else:
                    fields.append(value)
            return fields[0], fields[1], fields[2]
        pos += 4 + length
    return usize, csize, offset


def read_central_directory(src: RangeSource) -> List[Member]:
    """Members of the zip behind `src`, read from its tail: the end-of-central-
    directory record (zip64 variant honoured), then the central directory."""
    tail = src.tail(TAIL_BYTES)
    eocd_at = tail.rfind(EOCD_SIG)
    if eocd_at < 0:
        raise ValueError("no end-of-central-directory record in the last 64 KiB: not a zip")
    _sig, _disk, _cd_disk, _n_disk, n_total, cd_size, cd_offset, _clen = struct.unpack_from("<IHHHHIIH", tail, eocd_at)
    if 0xFFFFFFFF in (cd_size, cd_offset) or n_total == 0xFFFF:
        loc_at = eocd_at - 20
        if loc_at >= 0 and tail[loc_at:loc_at + 4] == EOCD64_LOC_SIG:
            _s, _d, eocd64_offset, _nd = struct.unpack_from("<IIQI", tail, loc_at)
            rec = src.read(eocd64_offset, 56)
            if rec[:4] != EOCD64_SIG:
                raise ValueError("zip64 end-of-central-directory record not where the locator points")
            (_s, _rsize, _vm, _vn, _disk, _cd_disk, _n_disk, n_total,
             cd_size, cd_offset) = struct.unpack_from("<IQHHIIQQQQ", rec, 0)
    tail_start = src.size - len(tail)
    if cd_offset >= tail_start:
        cd = tail[cd_offset - tail_start:cd_offset - tail_start + cd_size]
    else:
        cd = src.read(cd_offset, cd_size)
    members: List[Member] = []
    pos = 0
    while pos + 46 <= len(cd):
        if cd[pos:pos + 4] != CDIR_SIG:
            raise ValueError(f"central directory entry {len(members)} has a bad signature")
        (_sig, _vm, _vn, _flags, method, _t, _d, crc, csize, usize,
         nlen, xlen, clen, _dstart, _iattr, _eattr, loff) = struct.unpack_from("<IHHHHHHIIIHHHHHII", cd, pos)
        name = cd[pos + 46:pos + 46 + nlen].decode("utf-8")
        extra = cd[pos + 46 + nlen:pos + 46 + nlen + xlen]
        usize, csize, loff = _parse_zip64_extra(extra, usize, csize, loff)
        members.append(Member(name, method, crc, csize, usize, loff))
        pos += 46 + nlen + xlen + clen
    if n_total not in (0xFFFF, len(members)):
        raise ValueError(f"central directory lists {n_total} entries, parsed {len(members)}")
    return members


def extract_member(src: RangeSource, member: Member) -> bytes:
    """The member's bytes, inflated and CRC-checked. Two reads: the local
    header (for its own name/extra lengths) and the compressed data."""
    head = src.read(member.local_offset, 30)
    if head[:4] != LOCAL_SIG:
        raise ValueError(f"local header of {member.name} has a bad signature")
    nlen, xlen = struct.unpack_from("<HH", head, 26)
    data_at = member.local_offset + 30 + nlen + xlen
    raw = src.read(data_at, member.compressed_size)
    if len(raw) != member.compressed_size:
        raise ValueError(f"short read for {member.name}: {len(raw)} of {member.compressed_size} bytes")
    if member.method == 0:
        data = raw
    elif member.method == 8:
        data = zlib.decompress(raw, -15)
    else:
        raise ValueError(f"{member.name}: compression method {member.method} not supported")
    if zlib.crc32(data) & 0xFFFFFFFF != member.crc32:
        raise ValueError(f"{member.name}: CRC mismatch after extraction")
    return data


# ---------------------------------------------------------------------------
# Manifests and the archive index
# ---------------------------------------------------------------------------


def _git(repo: Path, *argv: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *argv], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else ""


def load_manifests(repo: Path) -> List[dict]:
    """Every render_archives/*.manifest.json, from the working tree or, when the
    checkout is sparse and excludes the directory, from HEAD."""
    out: List[dict] = []
    mdir = repo / MANIFEST_DIR
    names = sorted(p.name for p in mdir.glob("*.manifest.json")) if mdir.is_dir() else []
    if names:
        for n in names:
            out.append(json.loads((mdir / n).read_text(encoding="utf-8")))
        return out
    listing = _git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", MANIFEST_DIR.as_posix())
    for rel in sorted(listing.split()):
        if rel.endswith(".manifest.json"):
            text = _git(repo, "show", f"HEAD:{rel}")
            if text:
                out.append(json.loads(text))
    return out


def asset_url(manifest: dict) -> str:
    """The direct download URL of the manifest's zip, derived from its
    release_url (…/releases/tag/<tag>) and zip_name."""
    release_url = manifest.get("release_url") or ""
    m = re.match(r"^(https://github\.com/[^/]+/[^/]+)/releases/tag/([^/]+)$", release_url)
    if not m:
        raise ValueError(f"manifest {manifest.get('tag')!r} has no usable release_url: {release_url!r}")
    return f"{m.group(1)}/releases/download/{m.group(2)}/{manifest['zip_name']}"


def open_source(url: str, cache_dir: Path = CACHE_DIR) -> RangeSource:
    """An HTTP Range source for the asset, or a full download into the cache
    when the server does not honour Range (it does, but the fallback keeps the
    tool working if that changes)."""
    try:
        return HttpSource(url)
    except RangeUnsupported as exc:
        if exc.status != 200:
            raise
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / url.rsplit("/", 1)[-1]
        target.write_bytes(exc.body)
        print(f"server ignored Range; downloaded whole asset to {target}", file=sys.stderr)
        return FileSource(target)


def _factory(kw: dict):
    """The source factory to use: an explicit one (tests), else open_source
    bound to the same cache_dir the caller passed."""
    return kw.get("source_factory") or (lambda url: open_source(url, cache_dir=kw.get("cache_dir", CACHE_DIR)))


def member_names(manifest: dict, cache_dir: Path = CACHE_DIR, source_factory=None) -> Dict[str, List[str]]:
    """{run: [member basenames]} for one archive. From the manifest's own
    `members` when present (written since 2026-09-08), else from the zip's
    central directory, cached on disk by tag."""
    by_run: Dict[str, List[str]] = {}
    if all("members" in r for r in manifest.get("runs", [])) and manifest.get("runs"):
        return {r["run"]: list(r["members"]) for r in manifest["runs"]}
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{manifest['tag']}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    src = _factory({"source_factory": source_factory, "cache_dir": cache_dir})(asset_url(manifest))
    for m in read_central_directory(src):
        run, _, name = m.name.partition("/")
        if name:
            by_run.setdefault(run, []).append(name)
    cache.write_text(json.dumps(by_run, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return by_run


def is_png(name: str) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in PNG_GLOBS)


def build_index(manifests: Iterable[dict], **kw) -> Dict[str, Dict[str, str]]:
    """{run: {png basename: tag}} across every PNG-bearing archive; when two
    archives hold the same file the later tag (sorted) wins."""
    index: Dict[str, Dict[str, str]] = {}
    for manifest in sorted(manifests, key=lambda m: m.get("tag", "")):
        if not manifest.get("includes_pngs") or not manifest.get("release_url"):
            continue
        for run, names in member_names(manifest, **kw).items():
            for name in names:
                if is_png(name):
                    index.setdefault(run, {})[name] = manifest["tag"]
    return index


def tree_pngs(repo: Path, runs: Optional[Sequence[str]] = None) -> Dict[str, List[str]]:
    """{run: [png basenames]} tracked under trace_out/ at HEAD, from git so a
    sparse checkout that excludes the PNGs still sees them."""
    listing = _git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", "trace_out")
    out: Dict[str, List[str]] = {}
    wanted = {Path(r).name for r in runs} if runs else None
    for rel in listing.split():
        parts = rel.split("/")
        if len(parts) != 3 or not is_png(parts[2]):
            continue
        if wanted is not None and parts[1] not in wanted:
            continue
        out.setdefault(parts[1], []).append(parts[2])
    return out


def coverage(repo: Path, runs: Optional[Sequence[str]] = None, **kw) -> dict:
    """For every PNG in the tree: the archive tag that holds it, or None."""
    index = build_index(load_manifests(repo), **kw)
    report: Dict[str, Dict[str, Optional[str]]] = {}
    for run, names in tree_pngs(repo, runs).items():
        report[run] = {n: index.get(run, {}).get(n) for n in names}
    archived = sum(1 for r in report.values() for t in r.values() if t)
    unarchived = sum(1 for r in report.values() for t in r.values() if not t)
    return {"runs": report, "archived": archived, "unarchived": unarchived,
            "unarchived_runs": sorted(r for r, files in report.items() if any(t is None for t in files.values()))}


# ---------------------------------------------------------------------------
# Shrink check: an upload must never replace PNGs a Release already holds
# ---------------------------------------------------------------------------


def shrink_check(new_manifest: dict, old_manifest: Optional[dict]) -> List[str]:
    """Runs whose PNG member count in `new_manifest` is below what
    `old_manifest` (the one committed on the branch for the same tag) records.
    An archive fire re-uploads with --clobber, so a bundle built after the
    PNGs were pruned would silently replace the asset that holds them
    (2026-09-08: a duplicate p3 fire did exactly that, and the PNGs were in
    neither the tree nor the Release until a recovery run). Old manifests
    without member lists fall back to `includes_pngs`."""
    if not old_manifest:
        return []
    problems: List[str] = []
    old_runs = {r["run"]: r for r in old_manifest.get("runs", [])}
    for run in new_manifest.get("runs", []):
        old = old_runs.get(run["run"])
        if old is None:
            continue
        new_png = sum(1 for n in run.get("members", []) if is_png(n))
        if "members" in old:
            old_png = sum(1 for n in old["members"] if is_png(n))
        else:
            old_png = 1 if old_manifest.get("includes_pngs") else 0
        if new_png < old_png:
            problems.append(f"{run['run']}: {new_png} png in the new bundle, {old_png} in the Release")
    return problems


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def png_name(index: int, variant: Optional[str]) -> str:
    return f"index_{index:02d}.png" if not variant else f"index_{index:02d}_{variant}.png"


def fetch(repo: Path, run: str, names: Sequence[str], out_dir: Path, **kw) -> List[Path]:
    """Extract the named members of `run` from whichever archive holds each,
    into out_dir/<run>/. Refuses a name no archive holds."""
    index = build_index(load_manifests(repo), **kw)
    by_tag: Dict[str, List[str]] = {}
    missing = []
    for name in names:
        tag = index.get(run, {}).get(name)
        if tag:
            by_tag.setdefault(tag, []).append(name)
        else:
            missing.append(name)
    if missing:
        raise SystemExit(f"no archive holds {run}/{{{', '.join(missing)}}}; "
                         f"run `render_archive.py coverage --runs trace_out/{run}` to see what is archived")
    manifests = {m["tag"]: m for m in load_manifests(repo)}
    written: List[Path] = []
    factory = _factory(kw)
    for tag, wanted in by_tag.items():
        src = factory(asset_url(manifests[tag]))
        members = {m.name: m for m in read_central_directory(src)}
        for name in wanted:
            data = extract_member(src, members[f"{run}/{name}"])
            target = out_dir / run / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(target)
            print(f"{target}  ({len(data) / 1e6:.1f} MB, from {tag})")
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _repo_default() -> Path:
    return Path(__file__).resolve().parents[1]


def cmd_fetch(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if args.path:
        p = Path(args.path)
        run, name = p.parent.name, p.name
        names = [name]
    else:
        if not args.run:
            print("fetch needs --path or --run", file=sys.stderr)
            return 2
        run = Path(args.run).name
        if args.all:
            names = tree_pngs(repo, [run]).get(run) or []
            if not names:
                index = build_index(load_manifests(repo))
                names = sorted(index.get(run, {}))
        elif args.index is None:
            print("fetch --run needs --index NN or --all", file=sys.stderr)
            return 2
        else:
            names = [png_name(args.index, args.variant)]
    out_dir = repo / "trace_out" if args.in_place else Path(args.out_dir)
    fetch(repo, run, names, out_dir)
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    rep = coverage(repo, args.runs or None)
    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        for run, files in sorted(rep["runs"].items()):
            tags = sorted({t for t in files.values() if t})
            n_un = sum(1 for t in files.values() if not t)
            state = f"UNARCHIVED {n_un}/{len(files)}" if n_un else f"archived in {', '.join(tags)}"
            print(f"{run}: {len(files)} png, {state}")
        print(f"\n{rep['archived']} archived, {rep['unarchived']} unarchived, "
              f"{len(rep['unarchived_runs'])} run(s) need an archive fire")
    if args.require_archived and rep["unarchived"]:
        print(f"refused: {rep['unarchived']} PNG(s) in {len(rep['unarchived_runs'])} run(s) are in no Release: "
              + ", ".join(rep["unarchived_runs"]), file=sys.stderr)
        return 1
    return 0


def cmd_shrink_check(args: argparse.Namespace) -> int:
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    old = json.loads(Path(args.old).read_text(encoding="utf-8")) if Path(args.old).exists() else None
    problems = shrink_check(new, old)
    if problems:
        print("refused: uploading this bundle would replace PNGs the Release already holds:\n  "
              + "\n  ".join(problems) + "\n(pass allow_shrink to override on purpose)", file=sys.stderr)
        return 1
    print("shrink check ok" if old else "shrink check ok (no manifest on the branch for this tag)")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    for manifest in load_manifests(repo):
        if args.tag and manifest.get("tag") != args.tag:
            continue
        if not manifest.get("includes_pngs"):
            continue
        for run, names in sorted(member_names(manifest).items()):
            print(f"{manifest['tag']}  {run}: {len(names)} members, {sum(1 for n in names if is_png(n))} png")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(_repo_default()))
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="extract PNG(s) from the Release that holds them")
    f.add_argument("--run", help="trace_out run directory or its stem")
    f.add_argument("--index", type=int, help="pair index NN")
    f.add_argument("--variant", help="diff, register_standard, register_nonstandard, variety_medical, variety_patient")
    f.add_argument("--all", action="store_true", help="every PNG of the run")
    f.add_argument("--path", help="trace_out/<run>/<name>.png, instead of --run/--index")
    f.add_argument("--out-dir", default="dist/renders", help="destination root (default dist/renders/<run>/)")
    f.add_argument("--in-place", action="store_true", help="write beside the HTML under trace_out/ (untracked)")
    f.set_defaults(func=cmd_fetch)
    c = sub.add_parser("coverage", help="which archive holds each tree PNG")
    c.add_argument("--runs", nargs="*", help="limit to these trace_out/<run> directories")
    c.add_argument("--json", action="store_true")
    c.add_argument("--require-archived", action="store_true", help="exit 1 if any PNG is in no Release")
    c.set_defaults(func=cmd_coverage)
    sc = sub.add_parser("shrink-check", help="refuse a bundle with fewer PNGs than the branch's manifest records")
    sc.add_argument("--new", required=True, help="the freshly built dist/<tag>.manifest.json")
    sc.add_argument("--old", required=True, help="render_archives/<tag>.manifest.json (may not exist)")
    sc.set_defaults(func=cmd_shrink_check)
    i = sub.add_parser("index", help="list an archive's members (reads the zip's central directory once)")
    i.add_argument("--tag")
    i.set_defaults(func=cmd_index)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
