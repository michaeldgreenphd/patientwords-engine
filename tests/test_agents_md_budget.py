"""AGENTS.md stays under a byte budget below the size Codex reads.

Codex loads project instruction files up to `project_doc_max_bytes`, 32,768
bytes by default, and cuts the file that crosses that limit at the limit, with
only a log line as notice (openai/codex, codex-rs/core/src/agents_md.rs,
read 2026-09-29). That is certain for local Codex CLI sessions; whether the
GitHub reviewer applies the same cut is not documented. A cut loses the end of
the file first, and the second half of this file holds the Code Review Rules,
the Coding constraints and the Known measurement limitations that reviewers and
sessions work from. The file was 29,367 bytes on 2026-09-29 after growing 25%
in 20 days, with nothing checking its size.

The budget is 30 KiB, 2 KiB under the Codex default, so a change that pushes
the file toward the limit fails here first. Raising the budget is the owner's
decision; move reference material to docs/ instead.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_MD = ROOT / "AGENTS.md"
CODEX_DEFAULT_MAX_BYTES = 32 * 1024
BUDGET_BYTES = 30 * 1024


def test_the_budget_sits_below_the_codex_default() -> None:
    assert BUDGET_BYTES == 30_720 and BUDGET_BYTES < CODEX_DEFAULT_MAX_BYTES


def test_agents_md_is_within_its_byte_budget() -> None:
    size = len(AGENTS_MD.read_bytes())
    assert size <= BUDGET_BYTES, (
        f"AGENTS.md is {size:,} bytes, over its {BUDGET_BYTES:,}-byte budget "
        f"({CODEX_DEFAULT_MAX_BYTES:,} is where Codex stops reading by default); "
        "move reference material to docs/ rather than raising the budget")
