"""Rebuild lost jsteer summary rows offline from committed raw responses.

When a steering run dies before (or between) summary flushes, the per-call raw
API responses are still on the branch (save_raw is standard for steering).
Those raws contain everything the summary row derives - this tool re-runs the
same parsers (jlens_steer.final_rank_profile / completion_token) over them and
writes the missing jsteer_summary parts, so lane hours are never re-spent on
measurements that already landed. First use: steering-100 chunk 1 (2026-07-28),
19 items lost to the 60-minute job ceiling under the pre-flush script.

Rows carry "salvaged_from_raw": true; items whose call set is incomplete
(killed mid-item) carry "salvage_incomplete": true. Existing summary parts are
never overwritten; only indices absent from every landed part are rebuilt.
$0, offline.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import importlib.util
import json
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "jlens_steer", Path(__file__).resolve().parent / "jlens_steer.py")
steer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(steer)

RAW_RE = re.compile(r"pair_(\d+)_(.+)\.json\.gz$")


def covered_indices(out_dir: Path) -> set[int]:
    got: set[int] = set()
    for f in glob.glob(str(out_dir / "jsteer_summary.part_*.json")):
        for row in json.loads(Path(f).read_text(encoding="utf-8")).get("results", []):
            got.add(row["index"])
    return got


def expected_labels(spec_doc, item) -> list[str]:
    labels = ["baseline"] + [f"L{la}_s{st:g}" for la in spec_doc["layers"]
                             for st in spec_doc["strengths"]]
    if item.get("winner") and item["winner"] != item["target"]:
        labels += [f"L{la}_swap" for la in spec_doc["layers"]]
    return labels


def rebuild(spec_path: Path, out_dir: Path, topn: int, chunk: int) -> dict[int, int]:
    spec_doc = json.loads(spec_path.read_text(encoding="utf-8"))
    items = spec_doc["items"]
    have = covered_indices(out_dir)

    raws: dict[int, dict[str, Path]] = {}
    for f in glob.glob(str(out_dir / "jlens_raw" / "pair_*.json.gz")):
        m = RAW_RE.search(f)
        if m:
            raws.setdefault(int(m.group(1)), {})[m.group(2)] = Path(f)

    by_part: dict[int, list] = {}
    for index in sorted(raws):
        if index in have or index > len(items):
            continue
        item = items[index - 1]
        row = {"index": index, "dataset": item["dataset"], "spec_index": item["index"],
               "class": item["class"], "target_token": item["target"],
               "winner_token": item.get("winner"), "salvaged_from_raw": True, "calls": {}}
        for label, path in sorted(raws[index].items()):
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                response = json.load(fh)
            first, final_rank, status = steer.final_rank_profile(response, item["target"], topn)
            row["calls"][label] = {"first_layer": first, "final_rank": final_rank,
                                   "completion": steer.completion_token(response),
                                   "parse_status": status}
        if set(row["calls"]) != set(expected_labels(spec_doc, item)):
            row["salvage_incomplete"] = True
        part_no = ((index - 1) // chunk) * chunk + 1
        by_part.setdefault(part_no, []).append(row)

    written = {}
    for part_no, rows in sorted(by_part.items()):
        out = out_dir / f"jsteer_summary.part_{part_no:02d}.json"
        if out.exists():
            # merge into the existing part rather than clobbering a landed one
            doc = json.loads(out.read_text(encoding="utf-8"))
            doc["results"] = sorted(doc["results"] + rows, key=lambda r: r["index"])
        else:
            doc = {"mode": "jsteer", "backend": "jlens-hosted",
                   "graph_model": spec_doc["model"], "spec": str(spec_path),
                   "layers": spec_doc["layers"], "strengths": spec_doc["strengths"],
                   "top_n": topn, "start_index": part_no,
                   "_": ("Rebuilt offline from committed raw responses "
                         "(scripts/jsteer_rebuild.py); same parsers as the live run."),
                   "results": rows}
        out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        written[part_no] = len(rows)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--dir", required=True, type=Path, help="the __jsteer_ output dir")
    ap.add_argument("--topn", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=25, help="items per fire (part numbering)")
    args = ap.parse_args(argv)
    written = rebuild(args.spec, args.dir, args.topn, args.chunk)
    total = sum(written.values())
    for part_no, n in sorted(written.items()):
        print(f"part_{part_no:02d}: +{n} salvaged rows")
    print(f"salvaged {total} item(s) from raw responses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
