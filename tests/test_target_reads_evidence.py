"""AGENTS.md's target-read figures equal the committed evidence they cite (data/audits/target_reads_20261007.json).

The evidence file is written by scripts/audit_target_reads.py --compact-out. These tests check that its quoted
figures follow from its own published rows, and that every number the AGENTS.md bullet quotes is the evidence
file's, so neither can drift from the other unnoticed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/audits/target_reads_20261007.json"
sys.path.insert(0, str(ROOT / "scripts"))

import audit_target_reads as audit  # noqa: E402


def evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def bullet() -> str:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    start = text.index("* **The hosted path read some targets off another token.**")
    return " ".join(text[start:text.index("\n* **", start + 1)].split())


def test_the_quoted_figures_follow_from_the_evidence_rows():
    e = evidence()
    assert e["schema"] == audit.COMPACT_SCHEMA
    assert audit.quoted_figures(e["published_rows"], e["counts_last_part"]) == e["quoted"]
    assert e["site_payload"]["sha256"] and e["site_payload"]["site_ref"] and e["engine_sha"]
    assert not e["engine_sha"].endswith("+dirty")


def test_agents_md_quotes_the_evidence():
    q, text = evidence()["quoted"], bullet()
    assert "data/audits/target_reads_20261007.json" in text
    expected = {
        r"(\d+)\s+hosted results carry another token's value": q["borrowed_hosted_results"],
        r"(\d+) in a published field": q["published_scenarios_borrowed_in_a_published_field"],
        r"(\d+) measured a leading piece": q["wordpiece_reads_of_whole_tokens"],
        r"holds whole \((\d+) published\)": q["published_wordpiece_reads_of_whole_tokens"],
        r"Of (\d+) published substituted rows": q["published_substituted_rows"],
        r"(\d+) are the unscreened top-logit fallback": q["published_substituted_rows_by_mechanism"]["top_logit_fallback"],
        r"(\d+) the prefix match itself": q["published_substituted_rows_by_mechanism"]["prefix_match"],
        r"\((\d+) extensions": q["prefix_match_extensions"],
        r"(\d+) case variants": q["prefix_match_case_variants"],
        r"(\d+) screened\)": q["prefix_match_screened"],
        r"(\d+) the logits lane's bare-space first token": q["published_substituted_rows_by_mechanism"]["logits_first_token"],
        r"`anchor_fallback` misses (\d+)": q["published_substituted_rows_not_flagged"],
    }
    for pattern, value in expected.items():
        match = re.search(pattern, text)
        assert match, pattern
        assert int(match.group(1)) == value, pattern
