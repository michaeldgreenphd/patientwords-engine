"""Environment stamping in measurement summaries (audit 2026-07-21 E3) — offline.

Both measurement paths record the environment that produced them: the CPU
logits path (scripts/logits_eval.py, full ML-stack versions) and the hosted
graph path (medlang_circuits/batch_eval.py, python + engine sha + runner).
Offline, the heavy ML imports resolve to None — keys must still be present.
"""

import importlib.util
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "logits_eval", _ROOT / "scripts" / "logits_eval.py")
le = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(le)

from medlang_circuits.batch_eval import _environment  # noqa: E402


def test_logits_summary_carries_environment():
    s = le.build_summary("qwen3-4b", "Qwen/Qwen3-4B", results=[])
    env = s["inference"]["environment"]
    assert re.fullmatch(r"3\.\d+\.\d+", env["python"])
    assert {"torch", "transformers", "accelerate", "engine_sha",
            "platform", "runner_image"} <= set(env)
    # offline: ML versions may be None but the keys never disappear
    assert all(k in env for k in ("torch", "transformers", "accelerate"))


def test_batch_eval_environment_block():
    env = _environment()
    assert re.fullmatch(r"3\.\d+\.\d+", env["python"])
    assert set(env) == {"python", "engine_sha", "runner_image"}
    assert env["engine_sha"]  # in a git checkout this is always present


def test_constraints_pin_the_ml_stack():
    text = (_ROOT / "constraints.txt").read_text(encoding="utf-8")
    for pkg in ("torch==", "transformers==", "accelerate==", "requests==", "numpy=="):
        assert pkg in text, f"constraints.txt missing pin: {pkg}"
