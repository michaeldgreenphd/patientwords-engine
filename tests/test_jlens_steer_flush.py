"""Regression: jlens_steer must flush its summary part after every item so a
job timeout lands the measured prefix (steering-100 chunk 1, 2026-07-28, lost
19 measured items to the 60-minute ceiling with the old end-only write)."""

import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "jlens_steer", Path(__file__).resolve().parents[1] / "scripts" / "jlens_steer.py")
steer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(steer)


def test_summary_part_flushes_after_every_item(tmp_path, monkeypatch):
    spec = {
        "model": "gemma-2-2b",
        "layers": [19],
        "strengths": [1],
        "num_completion_tokens": 1,
        "items": [
            {"dataset": "d", "index": 1, "class": "retained",
             "prompt": "alpha beta", "target": " gamma", "winner": " delta"},
            {"dataset": "d", "index": 2, "class": "absent",
             "prompt": "alpha epsilon", "target": " gamma", "winner": " zeta"},
        ],
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"

    seen = {}
    calls = {"n": 0}

    def fake_post_lens(session, body):
        calls["n"] += 1
        # item 1 = 4 calls (baseline + 1 additive + 2 swaps? -> baseline,
        # L19_s1, L19_swap = 3). Peek at disk on the first call of item 2.
        part = out / "jsteer_summary.part_01.json"
        if part.exists() and "mid" not in seen:
            seen["mid"] = json.loads(part.read_text(encoding="utf-8"))
        return {"meta": {}, "tokens": [{"results": []}], "done": {}}, None

    monkeypatch.setattr(steer.jr, "post_lens", fake_post_lens)
    monkeypatch.setattr(steer.jr, "save_raw", lambda *a, **k: None)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")

    rc = steer.main(["--spec", str(spec_path), "--out", str(out), "--limit", "2", "--offset", "0"])
    assert rc == 0
    assert "mid" in seen, "no flush happened before the run finished"
    assert len(seen["mid"]["results"]) >= 1
    assert seen["mid"]["partial"] is True
    final = json.loads((out / "jsteer_summary.part_01.json").read_text(encoding="utf-8"))
    assert len(final["results"]) == 2
    assert "partial" not in final
