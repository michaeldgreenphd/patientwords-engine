"""Per-position lens scan (scripts/jlens_position_scan.py): the exploratory-set skip.

Hand-authored exploratory sets (agscen_; publication_hold.is_exploratory_run_dir)
have batch files in data/simulated/, so _batch_targets resolves their pairs and a
save_raw lens fire on one would enter ops/jlens_position_scan.json and, through
scan(), data/jlens_transport.json. These tests pin that scan() never reads them.
Synthetic raw responses in the hosted schema; offline.
"""
import gzip
import json
import sys

import scripts.jlens_position_scan as jps

MODEL = "gemma-2-2b"
STUDY = "setA"
EXPLORATORY = "agscen_20990101"


def _resp(per_position_top_tokens):
    """A raw lens response: one per-layer top-token list per prompt position."""
    n_layers = len(per_position_top_tokens[0])
    tokens = [{"kind": "token", "position": i, "token": f" t{i}",
               "results": [{"type": "JACOBIAN_LENS", "top_tokens": tops}]}
              for i, tops in enumerate(per_position_top_tokens)]
    return {"meta": {"layers_by_type": {"JACOBIAN_LENS": list(range(n_layers))}},
            "tokens": tokens, "done": {}}


READS_AT_ANSWER = _resp([[[" a"], [" a"]], [[" a"], [" tgt"]]])   # final position, layer 1
GAP = _resp([[[" a"], [" tgt"]], [[" a"], [" a"]]])               # mid-sentence only


def write_raw(root, stem, index, side, response):
    raw_dir = root / f"{stem}__jlens_{MODEL}" / "jlens_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(raw_dir / f"pair_{index:03d}_{side}.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(response, fh)


def study_and_exploratory(root):
    """One study pair, plus an exploratory set whose two transport-gap pairs would
    change every count if read."""
    write_raw(root, STUDY, 1, "clinical", READS_AT_ANSWER)
    write_raw(root, STUDY, 1, "patient", READS_AT_ANSWER)
    for index in (1, 2):
        write_raw(root, EXPLORATORY, index, "clinical", READS_AT_ANSWER)
        write_raw(root, EXPLORATORY, index, "patient", GAP)


def resolve_every_stem(monkeypatch):
    """Every stem, the exploratory one included, resolves targets, as the real agscen_
    batch files do: only the skip keeps the exploratory pairs out."""
    targets = {i: {"target_clinical_token": "tgt"} for i in (1, 2)}
    monkeypatch.setattr(jps, "_batch_targets", lambda stem: targets)


def test_scan_skips_an_exploratory_raw_dir(tmp_path, monkeypatch):
    resolve_every_stem(monkeypatch)
    root = tmp_path / "trace_out"
    study_and_exploratory(root)
    skipped = []
    result = jps.scan(root, skipped)
    assert {s["batch"] for s in result["scans"]} == {STUDY}
    assert result["n_responses"] == 2
    assert not any(s["transport_gap"] for s in result["scans"])
    assert [p.split("/")[-2] for p in skipped] == [f"{EXPLORATORY}__jlens_{MODEL}"]
    assert set(result) == {"_", "windows", "n_responses", "scans"}   # payload shape unchanged
    assert jps.scan(root) == result               # the skip does not depend on passing a list


def test_the_fixture_would_enter_the_scan_without_the_skip(tmp_path, monkeypatch):
    # control: the exploratory pairs are readable, so the test above is not passing vacuously
    resolve_every_stem(monkeypatch)
    monkeypatch.setattr(jps, "is_exploratory_run_dir", lambda run_dir: False)
    root = tmp_path / "trace_out"
    study_and_exploratory(root)
    result = jps.scan(root)
    assert {s["batch"] for s in result["scans"]} == {STUDY, EXPLORATORY}
    assert result["n_responses"] == 6


def test_main_output_carries_no_exploratory_row_and_prints_the_skip(tmp_path, monkeypatch, capsys):
    resolve_every_stem(monkeypatch)
    root = tmp_path / "trace_out"
    study_and_exploratory(root)
    out = tmp_path / "jlens_position_scan.json"
    monkeypatch.setattr(sys, "argv", ["jlens_position_scan.py", "--trace-root", str(root), "--out", str(out)])
    assert jps.main() is None
    printed = capsys.readouterr().out
    assert "1 exploratory-set part(s) not read (scripts/results_policy.py)" in printed
    assert not any(line.startswith(EXPLORATORY) for line in printed.splitlines())  # no per-pair line
    text = out.read_text(encoding="utf-8")
    assert "agscen" not in text
    assert json.loads(text)["n_responses"] == 2


def test_main_prints_nothing_about_a_skip_when_none_happened(tmp_path, monkeypatch, capsys):
    resolve_every_stem(monkeypatch)
    root = tmp_path / "trace_out"
    write_raw(root, STUDY, 1, "clinical", READS_AT_ANSWER)
    monkeypatch.setattr(sys, "argv", ["jlens_position_scan.py", "--trace-root", str(root),
                                      "--out", str(tmp_path / "scan.json")])
    jps.main()
    assert "exploratory-set" not in capsys.readouterr().out
