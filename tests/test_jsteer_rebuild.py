import gzip
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "jsteer_rebuild", Path(__file__).resolve().parents[1] / "scripts" / "jsteer_rebuild.py")
jr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jr)

RESPONSE = {"meta": {}, "tokens": [{"results": []}], "done": {}}


def _write_raw(d, index, label):
    (d / "jlens_raw").mkdir(parents=True, exist_ok=True)
    with gzip.open(d / "jlens_raw" / f"pair_{index:03d}_{label}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(RESPONSE, f)


def test_rebuild_salvages_missing_rows_and_flags_incomplete(tmp_path):
    spec = {"model": "gemma-2-2b", "layers": [19], "strengths": [1],
            "items": [
                {"dataset": "d", "index": 1, "class": "retained",
                 "prompt": "p1", "target": " a", "winner": " b"},
                {"dataset": "d", "index": 2, "class": "absent",
                 "prompt": "p2", "target": " a", "winner": " c"},
            ]}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    # item 1: full call set (baseline + L19_s1 + L19_swap); item 2: baseline only
    for label in ("baseline", "L19_s1", "L19_swap"):
        _write_raw(out, 1, label)
    _write_raw(out, 2, "baseline")

    written = jr.rebuild(spec_path, out, topn=8, chunk=25)
    assert written == {1: 2}
    doc = json.loads((out / "jsteer_summary.part_01.json").read_text(encoding="utf-8"))
    rows = {r["index"]: r for r in doc["results"]}
    assert rows[1]["salvaged_from_raw"] and "salvage_incomplete" not in rows[1]
    assert rows[2]["salvage_incomplete"] is True
    assert set(rows[1]["calls"]) == {"baseline", "L19_s1", "L19_swap"}

    # idempotent: indices already present in a part are never rebuilt
    again = jr.rebuild(spec_path, out, topn=8, chunk=25)
    assert again == {}
