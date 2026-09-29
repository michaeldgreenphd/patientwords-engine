"""Shared helpers for the stimulus-generation pilot. Standard library only (Python 3.11+).

Every constant that the protocol fixes lives here so that the scripts cannot drift from PROTOCOL.md.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import re
from pathlib import Path

# The pilot directory: the parent of scripts/, or PILOT_DIR when set (used by the self-test's temporary copy).
PILOT = Path(os.environ.get("PILOT_DIR") or Path(__file__).resolve().parent.parent)

# Design constants (fixed by PROTOCOL.md).
MASTER_SEED = 20260929
# The design factors are data, not code (engine AGENTS.md: medical vocabulary lives in data files, never in Python
# source): design.json holds the specialties and the swap types with the definition each prompt shows.
DESIGN: dict = json.loads((PILOT / "design.json").read_text(encoding="utf-8"))
SPECIALTIES: list[str] = list(DESIGN["specialties"])
SWAP_TYPES: list[str] = [t["name"] for t in DESIGN["swap_types"]]
SWAP_DEFINITIONS: dict[str, str] = {t["name"]: t["definition"] for t in DESIGN["swap_types"]}
ARMS = ["A", "B"]  # A: exemplars sampled per call; B: the same fixed exemplars in every call (plan_calls.py)
K_EXEMPLARS = 8
ROWS_PER_CALL = 20
CONTROLS_PER_CALL = 4
BLANK = "___"
REQUIRED_FIELDS = ["clinical_term", "patient_term", "template", "control"]
CONTROL_VALUES = ("none", "negative")
CHECKER_BATCH = 30
N_BROKEN = 20
N_KNOWN_GOOD = 10
N_REVIEW = 40
N_BOOT = int(os.environ.get("PILOT_N_BOOT", "2000"))  # the protocol fixes 2000; the test wrapper lowers it
Z = 1.959964


def cells() -> list[tuple[str, str]]:
    return [(s, t) for s in SPECIALTIES for t in SWAP_TYPES]


def cell_id(specialty: str, swap_type: str) -> str:
    return f"{specialty}__{swap_type.replace(' ', '_')}"


def call_id(arm: str, specialty: str, swap_type: str) -> str:
    return f"{arm}__{cell_id(specialty, swap_type)}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rng(purpose: str) -> random.Random:
    """A named deterministic stream. Exemplar sampling uses the integer seed exactly; every other draw uses a
    string seed derived from it (Python hashes str seeds with SHA-512, independent of PYTHONHASHSEED)."""
    if purpose == "exemplars":
        return random.Random(MASTER_SEED)
    return random.Random(f"{MASTER_SEED}:{purpose}")


def load_seeds() -> list[dict]:
    data = json.loads((PILOT / "seeds.json").read_text(encoding="utf-8"))
    return data["seeds"]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------- row validity (estimand 1)

def validate_line(line: str) -> tuple[dict | None, str]:
    """Return (row, "ok") when the line is a format-valid row, else (None, reason). Never repairs."""
    try:
        obj = json.loads(line)
    except ValueError:
        return None, "not_json"
    if not isinstance(obj, dict):
        return None, "not_object"
    missing = [k for k in REQUIRED_FIELDS if k not in obj]
    if missing:
        return None, "missing_field:" + ",".join(missing)
    for k in ("clinical_term", "patient_term", "template"):
        if not isinstance(obj[k], str) or not obj[k].strip():
            return None, f"empty_or_nonstring:{k}"
    if obj["template"].count(BLANK) != 1:
        return None, "template_blank_count_not_1"
    if obj["control"] not in CONTROL_VALUES:
        return None, "control_value_invalid"
    return obj, "ok"


def lines_of(text: str | None) -> list[str]:
    """The rows of a response: its non-empty lines, verbatim apart from surrounding whitespace."""
    if not text:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def surface_key(s: str) -> str:
    """Casing, punctuation and spacing removed: two strings with the same key differ only in surface form."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def control_is_faithful(row: dict) -> bool:
    return surface_key(row["clinical_term"]) == surface_key(row["patient_term"])


def dup_key(row: dict) -> tuple[str, str]:
    """Estimand 2 duplicate key: the (clinical_term, patient_term) pair, exact after case folding."""
    return (row["clinical_term"].lower(), row["patient_term"].lower())


# ---------------------------------------------------------------- intervals

def wilson(x: int, n: int) -> dict:
    if n == 0:
        return {"x": x, "n": n, "p": None, "lo": None, "hi": None}
    p = x / n
    z2 = Z * Z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return {"x": x, "n": n, "p": p, "lo": max(0.0, centre - half), "hi": min(1.0, centre + half)}


def newcombe_diff(x1: int, n1: int, x2: int, n2: int) -> dict:
    """Newcombe (1998) method 10: score interval for p1 - p2 built from the two Wilson intervals."""
    if n1 == 0 or n2 == 0:
        return {"diff": None, "lo": None, "hi": None}
    w1, w2 = wilson(x1, n1), wilson(x2, n2)
    d = w1["p"] - w2["p"]
    lo = d - math.sqrt((w1["p"] - w1["lo"]) ** 2 + (w2["hi"] - w2["p"]) ** 2)
    hi = d + math.sqrt((w1["hi"] - w1["p"]) ** 2 + (w2["p"] - w2["lo"]) ** 2)
    return {"diff": d, "lo": lo, "hi": hi}


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


# ---------------------------------------------------------------- TF-IDF (estimand 3)

TOKEN_RE = re.compile(r"\b\w\w+\b")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.replace(BLANK, " ").lower())


class Tfidf:
    """Word-unigram TF-IDF with sklearn's defaults re-implemented: raw term counts, smooth idf
    ln((1 + N) / (1 + df)) + 1, L2-normalised vectors, tokens of two or more word characters, lowercase."""

    def __init__(self, docs: list[str]):
        self.n = len(docs)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(tokenize(d)):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((1 + self.n) / (1 + c)) + 1.0 for t, c in df.items()}

    def vector(self, doc: str) -> dict[str, float]:
        counts: dict[str, int] = {}
        for t in tokenize(doc):
            counts[t] = counts.get(t, 0) + 1
        vec = {t: c * self.idf.get(t, math.log((1 + self.n) / 1) + 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm > 0 else {}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def mean_pairwise(vectors: list[dict[str, float]]) -> tuple[float | None, int]:
    n = len(vectors)
    if n < 2:
        return None, 0
    total, pairs = 0.0, 0
    for i in range(n):
        for j in range(i + 1, n):
            total += cosine(vectors[i], vectors[j])
            pairs += 1
    return total / pairs, pairs


def mean_cross(vectors: list[dict[str, float]], others: list[dict[str, float]]) -> tuple[float | None, int]:
    if not vectors or not others:
        return None, 0
    total = sum(cosine(v, o) for v in vectors for o in others)
    return total / (len(vectors) * len(others)), len(vectors) * len(others)


def bootstrap_mean(stat, items: list, r: random.Random, n_boot: int = N_BOOT) -> dict:
    """Percentile bootstrap of stat(list) over resampled items (with replacement)."""
    n = len(items)
    if n == 0:
        return {"lo": None, "hi": None, "n_boot": 0}
    vals = []
    for _ in range(n_boot):
        sample = [items[r.randrange(n)] for _ in range(n)]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return {"lo": None, "hi": None, "n_boot": 0}
    return {"lo": percentile(vals, 0.025), "hi": percentile(vals, 0.975), "n_boot": len(vals)}
