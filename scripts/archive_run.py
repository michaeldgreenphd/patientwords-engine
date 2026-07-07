"""Bundle a run's full circuit renders into one zip for back-end archival.

The public site (patientwords) only carries a small demonstration set - the
most consequential renders, capped by export_frontend_simulated.py. The full
render set for a large run is heavy (hundreds of MB of HTML + PNG) and does
not belong in the site repo or, long-term, in the engine's git working tree.
This script packages one or more trace_out/<run>/ directories into a single
zip plus a manifest, so the companion archive_renders.yml workflow can attach
it to a GitHub Release and keep the durable copy off git.

Pure standard library, no network: the zip and manifest are built here and
the Release upload happens in CI (which has a token). That split keeps the
packaging logic testable locally.

Usage:
  python scripts/archive_run.py --runs trace_out/dialects_20260707T000923Z \
      --tag renders-20260707 --out-dir dist
  # -> dist/renders-20260707.zip  +  dist/renders-20260707.manifest.json

  # Several runs in one bundle, HTML only (drop the multi-MB PNGs):
  python scripts/archive_run.py --runs trace_out/pairs_A trace_out/pairs_B \
      --tag renders-20260707 --out-dir dist --no-pngs
"""

import argparse
import fnmatch
import hashlib
import json
import zipfile
from pathlib import Path

# Render artifacts worth archiving. PNGs are the heavy ones and can be dropped
# with --no-pngs (the interactive HTML is the essential artifact); the summary
# JSONs are tiny and always kept so the bundle is self-describing.
INCLUDE_GLOBS = ("index_*.html", "index_*.png", "batch_summary*.json")
PNG_GLOBS = ("index_*.png",)


def _matches(name, globs):
    return any(fnmatch.fnmatch(name, g) for g in globs)


def collect_files(run_dir, include_pngs):
    """Return the archivable files in run_dir, sorted for a stable zip."""
    files = []
    for path in sorted(run_dir.iterdir()):
        if not path.is_file():
            continue
        if not _matches(path.name, INCLUDE_GLOBS):
            continue
        if not include_pngs and _matches(path.name, PNG_GLOBS):
            continue
        files.append(path)
    return files


def build_bundle(runs, tag, out_dir, include_pngs):
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{tag}.zip"
    manifest_path = out_dir / f"{tag}.manifest.json"

    run_entries = []
    total_bytes = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for run_dir in runs:
            if not run_dir.is_dir():
                raise SystemExit(f"run directory not found: {run_dir}")
            files = collect_files(run_dir, include_pngs)
            if not files:
                print(f"  (skip) {run_dir} has no archivable renders")
                continue
            stem = run_dir.name
            run_bytes = 0
            for f in files:
                # Store under the run stem so several runs coexist in one zip
                # and unzip back into a trace_out-shaped tree.
                zf.write(f, arcname=f"{stem}/{f.name}")
                run_bytes += f.stat().st_size
            total_bytes += run_bytes
            run_entries.append({
                "run": stem,
                "files": len(files),
                "bytes": run_bytes,
            })
            print(f"  + {stem}: {len(files)} files, {run_bytes / 1e6:.1f} MB")

    if not run_entries:
        zip_path.unlink(missing_ok=True)
        raise SystemExit("nothing to archive - no runs contained renders")

    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    manifest = {
        "tag": tag,
        "runs": run_entries,
        "includes_pngs": include_pngs,
        "source_bytes": total_bytes,
        "zip_name": zip_path.name,
        "zip_bytes": zip_path.stat().st_size,
        "zip_sha256": sha256,
        # release_url is filled in by CI once the asset is uploaded.
        "release_url": None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return zip_path, manifest_path, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", nargs="+", required=True,
                        help="trace_out/<run> directories to bundle")
    parser.add_argument("--tag", required=True,
                        help="release tag / bundle name, e.g. renders-20260707")
    parser.add_argument("--out-dir", default="dist",
                        help="where to write <tag>.zip + <tag>.manifest.json (default: dist)")
    parser.add_argument("--no-pngs", action="store_true",
                        help="drop the multi-MB PNGs; keep interactive HTML + summaries")
    args = parser.parse_args()

    runs = [Path(r) for r in args.runs]
    print(f"Bundling {len(runs)} run(s) into {args.tag} "
          f"({'html only' if args.no_pngs else 'html + png'}):")
    zip_path, manifest_path, manifest = build_bundle(
        runs, args.tag, Path(args.out_dir), include_pngs=not args.no_pngs)

    print(f"\nBundle : {zip_path} ({manifest['zip_bytes'] / 1e6:.1f} MB)")
    print(f"Manifest: {manifest_path}")
    print(f"sha256 : {manifest['zip_sha256']}")


if __name__ == "__main__":
    main()
