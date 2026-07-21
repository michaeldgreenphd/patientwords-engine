"""Holdout-seal integrity check (scripts/seal_check.py) — offline.

Pins: empty-set refusal (exit 2, the wrong-branch guard), leak detection by
exact AND normalized match, label-only reporting (phrase text never printed),
and the clean path. Uses abstract non-medical test phrases only.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("seal_check", _ROOT / "scripts" / "seal_check.py")
sc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sc)


def sealed_phrase(base="zz test phrase"):
    """Find a phrase variant that lands in the sha1-mod-10 holdout bucket."""
    for i in range(200):
        p = f"{base} {i}"
        if int(hashlib.sha1(p.encode()).hexdigest(), 16) % 10 == 0:
            return p
    raise AssertionError("no holdout phrase found in 200 tries")


def setup(tmp_path, phrase):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_20260711T000000Z.json").write_text(json.dumps(
        [{"top_prompt": phrase, "bottom_prompt": "kept out of it"}]), encoding="utf-8")
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "dashboard.json").write_text(json.dumps(
        {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}), encoding="utf-8")
    site = tmp_path / "site" / "data"
    site.mkdir(parents=True)
    return sim, ops, site


def run(tmp_path, capsys):
    rc = sc.main(["--site", str(tmp_path / "site"),
                  "--dashboard", str(tmp_path / "ops" / "dashboard.json"),
                  "--simulated", str(tmp_path / "data" / "simulated"),
                  "--extra", ""])
    return rc, capsys.readouterr().out


def test_empty_sealed_set_is_a_config_error(tmp_path, capsys):
    phrase = sealed_phrase()
    setup(tmp_path, phrase)
    (tmp_path / "ops" / "dashboard.json").write_text(json.dumps({"tierb": {}}))
    rc, out = run(tmp_path, capsys)
    assert rc == 2 and "CONFIG ERROR" in out


def test_clean_when_site_has_no_sealed_phrase(tmp_path, capsys):
    phrase = sealed_phrase()
    _, _, site = setup(tmp_path, phrase)
    (site / "payload.json").write_text(json.dumps({"scenarios": [{"p": "harmless"}]}))
    rc, out = run(tmp_path, capsys)
    assert rc == 0 and "CLEAN" in out


def test_leak_found_by_normalized_match_and_never_quoted(tmp_path, capsys):
    phrase = sealed_phrase()
    _, _, site = setup(tmp_path, phrase)
    mangled = phrase.upper().replace(" ", "   ")          # case + whitespace mangling
    (site / "leaky.json").write_text(json.dumps({"text": mangled}))
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and "LEAK" in out
    assert "pairs_20260711T000000Z#1" in out               # label-only reporting
    assert phrase not in out and mangled not in out        # the report is not the leak
