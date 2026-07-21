"""Companion traces-site exporter (scripts/export_traces_site.py) — offline.

Pins the payload-as-source-of-truth rule (only published scenarios get a
trace), the incremental copy, the trace_url stamping, and the refusal when
the traces repo checkout is absent. No network.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_traces_site", _ROOT / "scripts" / "export_traces_site.py")
ets = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ets)

BASE = "https://example.test/traces"


def setup(tmp_path, scenarios, renders):
    trace_root = tmp_path / "trace_out"
    for batch, idx in renders:
        d = trace_root / batch
        d.mkdir(parents=True, exist_ok=True)
        (d / f"index_{idx:02d}.html").write_text(f"<html>{batch}#{idx}</html>")
    repo = tmp_path / "traces-repo"
    (repo / ".git").mkdir(parents=True)
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")
    return trace_root, repo, payload_path


def test_publish_copies_stamps_and_counts(tmp_path):
    scenarios = [{"batch": "pairs_A", "batch_index": 5},
                 {"batch": "pairs_A", "batch_index": 105},
                 {"batch": "pairs_B", "batch_index": 1},   # no render committed
                 {"batch": None, "batch_index": 2}]
    trace_root, repo, _ = setup(tmp_path, scenarios,
                                renders=[("pairs_A", 5), ("pairs_A", 105)])
    payload = {"scenarios": scenarios}
    copied, unchanged, missing = ets.publish(payload, trace_root, repo, BASE + "/")
    assert (copied, unchanged, missing) == (2, 0, 2)
    assert (repo / "t/pairs_A/index_05.html").is_file()
    assert (repo / "t/pairs_A/index_105.html").is_file()          # 3-digit index intact
    assert scenarios[0]["trace_url"] == f"{BASE}/t/pairs_A/index_05.html"
    assert "trace_url" not in scenarios[2]                        # render-less: no dead link
    # second run is incremental
    copied2, unchanged2, _ = ets.publish(payload, trace_root, repo, BASE)
    assert (copied2, unchanged2) == (0, 2)


def test_main_refuses_without_repo_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, _, payload_path = setup(tmp_path, [{"batch": "pairs_A", "batch_index": 1}], [])
    before = payload_path.read_text()
    rc = ets.main(["--payload", str(payload_path), "--trace-root", str(tmp_path / "trace_out"),
                   "--traces-repo", str(tmp_path / "not-a-repo"), "--base-url", BASE])
    assert rc == 3
    assert payload_path.read_text() == before                     # untouched on refusal


def test_main_writes_traces_site_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenarios = [{"batch": "pairs_A", "batch_index": 5}]
    trace_root, repo, payload_path = setup(tmp_path, scenarios, renders=[("pairs_A", 5)])
    rc = ets.main(["--payload", str(payload_path), "--trace-root", str(trace_root),
                   "--traces-repo", str(repo), "--base-url", BASE])
    assert rc == 0
    out = json.loads(payload_path.read_text())
    assert out["traces_site"]["base_url"] == BASE
    assert out["traces_site"]["_provenance"]["generator"] == "scripts/export_traces_site.py"
    assert out["scenarios"][0]["trace_url"].endswith("/t/pairs_A/index_05.html")
