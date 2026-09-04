"""Inter-judge agreement exporter (scripts/export_judge_agreement.py) - offline."""

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "export_judge_agreement.py"
_SPEC = importlib.util.spec_from_file_location("export_judge_agreement", _MODULE_PATH)
exporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exporter)

TIERS = ["self_care", "routine", "urgent", "emergency"]


def _row(sha, judge, tier, utc="2026-08-22T00:00:00Z"):
    return {"response_sha256": sha, "judge_model": judge, "tier": tier,
            "rubric_version": "1.1-draft", "judged_utc": utc}


def _write(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_matrix_counts_and_rates(tmp_path):
    ae = exporter._load_advice_eval()
    rows = [
        _row("a", "claude-haiku-4-5", "routine"), _row("a", "openrouter:x/y", "routine"),
        _row("b", "claude-haiku-4-5", "urgent"), _row("b", "openrouter:x/y", "emergency"),
        _row("c", "claude-haiku-4-5", "emergency"), _row("c", "openrouter:x/y", "self_care"),
        _row("d", "claude-haiku-4-5", "self_care"),  # unpaired: no secondary
    ]
    payload = exporter.build_payload([_write(tmp_path, "judgments_t.jsonl", rows)], ae, TIERS)
    assert payload["n_paired"] == 3
    assert payload["exact"] == {"n": 1, "rate": round(1 / 3, 4)}
    assert payload["within_one"] == {"n": 2, "rate": round(2 / 3, 4)}
    assert payload["lean"] == {"secondary_more_urgent": 1, "primary_more_urgent": 1}
    # matrix[primary][secondary] in tier_order
    assert payload["matrix"][TIERS.index("routine")][TIERS.index("routine")] == 1
    assert payload["matrix"][TIERS.index("urgent")][TIERS.index("emergency")] == 1
    assert payload["matrix"][TIERS.index("emergency")][TIERS.index("self_care")] == 1
    assert sum(map(sum, payload["matrix"])) == 3
    assert payload["secondary_judges"] == {"openrouter:x/y": 3}
    assert payload["coverage"][0]["n_primary"] == 4


def test_later_pass_overwrites_earlier(tmp_path):
    ae = exporter._load_advice_eval()
    rows = [
        _row("a", "claude-haiku-4-5", "routine"),
        _row("a", "openrouter:x/y", "self_care"),
        _row("a", "openrouter:x/y", "routine"),  # re-judge: later pass wins
    ]
    payload = exporter.build_payload([_write(tmp_path, "judgments_t.jsonl", rows)], ae, TIERS)
    assert payload["exact"]["n"] == 1


def test_refuses_without_any_pair(tmp_path):
    ae = exporter._load_advice_eval()
    rows = [_row("a", "claude-haiku-4-5", "routine"), _row("b", "openrouter:x/y", "urgent")]
    with pytest.raises(SystemExit):
        exporter.build_payload([_write(tmp_path, "judgments_t.jsonl", rows)], ae, TIERS)


def test_unknown_tiers_are_ignored_not_counted(tmp_path):
    ae = exporter._load_advice_eval()
    rows = [
        _row("a", "claude-haiku-4-5", "routine"), _row("a", "openrouter:x/y", "routine"),
        _row("b", "claude-haiku-4-5", "not_a_tier"), _row("b", "openrouter:x/y", "routine"),
    ]
    payload = exporter.build_payload([_write(tmp_path, "judgments_t.jsonl", rows)], ae, TIERS)
    assert payload["n_paired"] == 1
