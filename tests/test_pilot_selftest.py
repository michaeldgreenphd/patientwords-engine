"""The stimulus-generation pilot's self-test (pilot/scripts/selftest.py): known-value checks of its interval and
TF-IDF helpers, the 8-of-N exemplar sampling, and an end-to-end dry run of every pilot script on fabricated responses
in a temporary directory. PILOT_N_BOOT lowers the bootstrap from the protocol's 2000 resamples to keep the suite fast.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pilot_selftest_passes():
    env = {**os.environ, "PILOT_N_BOOT": "200"}
    out = subprocess.run([sys.executable, str(ROOT / "pilot" / "scripts" / "selftest.py")], env=env,
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "selftest: all checks passed" in out.stdout
