"""The text of advice Amendment 7 is kept byte for byte as the owner approved it.

`docs/preregistration_advice.md` records two SHA-256 values for
`docs/preregistration_advice_amendment7.md`: one for the whole file and one for its first
27,425 bytes (the title, sections 0 to 13 and the annex). These tests fail when the file
changes, or when the record and the file stop agreeing. A change to the amendment is a new
amendment with its own approval, not an edit of this file.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = ROOT / "docs" / "preregistration_advice_amendment7.md"
RECORD = ROOT / "docs" / "preregistration_advice.md"

WHOLE_SHA256 = "5aa8fa90848faebb37de962722fc5bace61618af574a723f34f2ca1fb0d7b53d"
PREFIX_BYTES = 27_425
PREFIX_SHA256 = "b7eb54cb150d9a5b51fefca9452c15e611d500a4eb2394650e3e1ceb9e335e5a"
SIZE_BYTES = 37_568


def _record_section() -> str:
    text = RECORD.read_text(encoding="utf-8")
    start = text.index("## Amendment 7 (")
    following = re.search(r"^## ", text[start + 3:], flags=re.MULTILINE)
    return text[start:] if following is None else text[start:start + 3 + following.start()]


def test_the_file_has_the_approved_bytes() -> None:
    raw = TEXT.read_bytes()
    assert len(raw) == SIZE_BYTES
    assert hashlib.sha256(raw).hexdigest() == WHOLE_SHA256


def test_the_amendment_without_its_closing_page_has_the_approved_bytes() -> None:
    raw = TEXT.read_bytes()
    assert hashlib.sha256(raw[:PREFIX_BYTES]).hexdigest() == PREFIX_SHA256
    # The prefix ends just before the rule that precedes the page "What this approval fixes".
    assert raw[PREFIX_BYTES:].startswith(b"---\n")
    assert b"# What this approval fixes" in raw[PREFIX_BYTES:]
    assert b"# What this approval fixes" not in raw[:PREFIX_BYTES]


def test_the_file_is_utf8_with_line_feeds_and_one_final_line_feed() -> None:
    raw = TEXT.read_bytes()
    raw.decode("utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")


def test_the_preregistration_records_both_hashes_and_names_the_file() -> None:
    section = _record_section()
    assert "docs/preregistration_advice_amendment7.md" in section
    assert WHOLE_SHA256 in section
    assert PREFIX_SHA256 in section
    assert f"{SIZE_BYTES:,} bytes" in section
    assert f"{PREFIX_BYTES:,}" in section


def test_the_record_says_that_approval_authorises_no_spending() -> None:
    section = " ".join(_record_section().split())
    assert "authorises no spending" in section
    assert "explicit dollar authorisation" in section
