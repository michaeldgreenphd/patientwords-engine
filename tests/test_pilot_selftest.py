"""The stimulus-generation pilot's self-test (pilot/scripts/selftest.py): known-value checks of its interval and
TF-IDF helpers, the 8-of-N exemplar sampling, and end-to-end dry runs of every pilot script on fabricated responses
in temporary directories (harness version 1, and version 2 with the run kit in pilot/prompts_v2/), at the protocol's
2000 bootstrap resamples (about two minutes, since finalize now recomputes the summary; the environment override that once
lowered it was removed on Codex's review of PR #52, since one that leaked into a real run could finalize fewer).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pilot_selftest_passes():
    out = subprocess.run([sys.executable, str(ROOT / "pilot" / "scripts" / "selftest.py")],
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "selftest: all checks passed" in out.stdout
