"""Home-teaser featured block (scripts/export_stress_featured.py, audit M3 tail).

Pins the page's exact consequence ranking (flip*10 + |observed prob gap|,
dataset-order tiebreak via stable sort), the wrap to {pairs, featured} with
pair content preserved verbatim, idempotence, and the refusal path.
Synthetic tokens only — no medical vocabulary in this file.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_stress_featured", _ROOT / "scripts" / "export_stress_featured.py")
sf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sf)


def pair(tok_c, tok_p, pc=None, pp=None, row=None):
    prov = {"patient": {"observed_next_token": tok_p, "observed_prob": pp},
            "clinical": {"observed_next_token": tok_c, "observed_prob": pc}}
    if row is not None:
        prov["source_row"] = row
    return {"top_prompt": "c", "bottom_prompt": "p", "provenance": prov}


def write(tmp_path, data):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    p = d / "stress_pairs.json"
    p.write_text(json.dumps(data))
    return p


def test_ranking_flips_first_then_gap_dataset_order_tiebreak(tmp_path):
    pairs = [pair("a", "a", 0.9, 0.1),           # no flip, gap .8 -> 0.8
             pair("a", "b", 0.5, 0.4, row=7),    # flip, gap .1 -> 10.1
             pair("a", "b", 0.6, 0.5),           # flip, gap .1 -> 10.1 (tie)
             pair(None, "b", 0.9, 0.0),          # missing token: no flip, 0.9
             pair("a", "a")]                     # no numbers -> 0
    p = write(tmp_path, pairs)
    assert sf.main(["--site", str(tmp_path)]) == 0
    out = json.loads(p.read_text())
    assert out["pairs"] == pairs                  # content preserved verbatim
    rows = out["featured"]["rows"]
    # ties broken by dataset order (row 1 before row 2)
    assert [r["row"] for r in rows] == [1, 2, 3, 0, 4]
    assert rows[0]["source_row"] == 7 and rows[1]["source_row"] is None
    assert rows[0]["flip"] is True and abs(rows[0]["gap"] - 0.1) < 1e-9
    assert abs(rows[0]["consequence"] - 10.1) < 1e-9
    assert out["featured"]["metric"] == "flip*10+abs_prob_gap"
    assert out["featured"]["tiebreak"] == "dataset order"


def test_idempotent_on_wrapped_shape_and_caps_at_five(tmp_path):
    pairs = [pair("a", "b", 0.5, 0.4 - i / 100) for i in range(7)]
    p = write(tmp_path, pairs)
    assert sf.main(["--site", str(tmp_path)]) == 0
    first = json.loads(p.read_text())
    assert first["featured"]["n"] == 5 and len(first["featured"]["rows"]) == 5
    assert sf.main(["--site", str(tmp_path)]) == 0   # run again on object shape
    assert json.loads(p.read_text()) == first


def test_refuses_when_missing_or_empty(tmp_path):
    (tmp_path / "data").mkdir()
    assert sf.main(["--site", str(tmp_path)]) == 3
    write(tmp_path, [])
    assert sf.main(["--site", str(tmp_path)]) == 3
