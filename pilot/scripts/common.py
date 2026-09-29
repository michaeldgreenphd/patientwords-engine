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
MAX_ATTEMPTS = 2  # the protocol's retry rule: one attempt, at most one retry (PROTOCOL.md 3 and 6)
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


SEED_TEXT_FIELDS = ("clinical_term", "patient_term", "template", "specialty", "swap_type")


def validate_seeds(data: object) -> list[dict]:
    """The seed contract, checked before any plan or call: a non-empty `seeds` list; every seed an object with a
    unique non-empty `id`, non-empty string `clinical_term`, `patient_term`, `template`, `specialty` and
    `swap_type` (the checker set files a seed under its cell), and exactly one blank marker in the template. A seed
    without `provenance` is allowed and reported as MISSING by the manifest and the summary. A malformed file is
    refused, naming the seed and the rule, rather than planned into prompts and known-good rows (Codex review of
    PR #52)."""
    seeds = data.get("seeds") if isinstance(data, dict) else None
    if not isinstance(seeds, list) or not seeds:
        raise SystemExit("seeds.json: 'seeds' must be a non-empty list")
    seen: set[str] = set()
    for i, s in enumerate(seeds):
        where = f"seeds.json seed {i}"
        if not isinstance(s, dict):
            raise SystemExit(f"{where}: not an object")
        sid = s.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise SystemExit(f"{where}: 'id' must be a non-empty string")
        if sid in seen:
            raise SystemExit(f"{where}: duplicate id {sid!r}")
        seen.add(sid)
        for k in SEED_TEXT_FIELDS:
            if not isinstance(s.get(k), str) or not s[k].strip():
                raise SystemExit(f"{where} ({sid}): '{k}' must be a non-empty string")
        if s["template"].count(BLANK) != 1:
            raise SystemExit(f"{where} ({sid}): 'template' must contain the blank marker {BLANK!r} exactly once")
    return seeds


def load_seeds() -> list[dict]:
    return validate_seeds(json.loads((PILOT / "seeds.json").read_text(encoding="utf-8")))


def read_jsonl(path: Path) -> list[dict]:
    """A required JSONL input. A missing file is refused by name: an absent artifact must never read as an empty
    dataset and yield a plausible partial number (Codex review of PR #52)."""
    if not path.exists():
        shown = path.relative_to(PILOT) if path.is_relative_to(PILOT) else path
        raise SystemExit(f"{shown}: required input is missing; run the step that writes it first")
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
    """Casing, punctuation and spacing removed: two strings with the same key differ only in surface form. Letters
    and digits of every script are kept (str.isalnum is Unicode-aware), so an accented or non-Latin term keeps its
    letters instead of collapsing to nothing (Codex review of PR #52)."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


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


def checked_problems(checked: list[dict], key: list[dict], blind: list[dict], plan_sha256: str) -> list[str]:
    """Why checked.jsonl does not belong to the checker plan on disk: an item set that differs from the truth key's
    (an item absent, unknown or repeated), an item whose fields differ from the key and the blind set, or a row
    stamped with another plan's hash (parse_checker.py writes `checker_plan_sha256`, the hash of the
    checker_batches.json it parsed against, on every row). A count-only check let a previous run's checked.jsonl
    pass beside a rebuilt checker set and mix its verdicts into a new run's summary (Codex review of PR #52).
    Empty when checked.jsonl is that plan's parse."""
    by_key = {t["id"]: t for t in key}
    by_blind = {b["id"]: b for b in blind}
    ids = [c.get("id") for c in checked]
    problems = []
    if sorted(ids, key=str) != sorted(by_key):
        problems.append(f"item ids differ from checker_key.jsonl: {len(set(ids) - set(by_key))} unknown, "
                        f"{len(set(by_key) - set(ids))} absent, {len(ids) - len(set(ids))} repeated")
    for c in checked:
        cid = c.get("id")
        if cid not in by_key or cid not in by_blind:
            continue
        expected = {**by_key[cid], **by_blind[cid]}
        if any(c.get(k) != v for k, v in expected.items()):
            problems.append(f"item {cid}: fields differ from checker_key.jsonl and checker_set.jsonl")
        if c.get("checker_plan_sha256") != plan_sha256:
            problems.append(f"item {cid}: checker_plan_sha256 {str(c.get('checker_plan_sha256'))[:12]!r} is not "
                            f"the plan on disk ({plan_sha256[:12]})")
    return problems


def read_csv(path: Path) -> list[dict]:
    """A required CSV input, as dictionaries; a missing file is refused by name, like read_jsonl."""
    if not path.exists():
        shown = path.relative_to(PILOT) if path.is_relative_to(PILOT) else path
        raise SystemExit(f"{shown}: required input is missing; run the step that writes it first")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def attempt_failed(raw: str | None) -> bool:
    """PROTOCOL.md 3: a generation call has failed, and may be retried once, when the response is empty or no
    returned line parses as a JSON object carrying the four required keys. Fewer than 20 rows, or some invalid rows,
    is not a failure. The parser refuses a second attempt whose first did not fail (Codex review of PR #52)."""
    for line in lines_of(raw):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and all(k in obj for k in REQUIRED_FIELDS):
            return False
    return True


def checker_attempt_failed(result: object) -> bool:
    """PROTOCOL.md 6: a checker batch is retried once when its subagent returns nothing: no result object, no
    `verdicts` list, or an empty one."""
    return not isinstance(result, dict) or not isinstance(result.get("verdicts"), list) or not result["verdicts"]


def generation_problems(calls: dict, call_log: list[dict], rows: list[dict]) -> list[str]:
    """Why call_log.jsonl and the parsed rows do not belong to the call plan on disk: final records whose call ids
    differ from the plan's, or a final record or row whose `prompt_sha256` (stamped by parse_generation.py from the
    plan it parsed against) is not the planned prompt's. Call ids are stable across plans, so without the hash a
    previous run's responses would pass under re-planned prompts (Codex review of PR #52). Empty when they belong."""
    planned = {c["id"]: c["prompt_sha256"] for c in calls["calls"]}
    finals = [e for e in call_log if e.get("is_final")]
    ids = [e.get("call_id") for e in finals]
    problems = []
    if sorted(ids, key=str) != sorted(planned):
        problems.append(f"call_log.jsonl holds final records for {len(ids)} calls ({len(set(ids) - set(planned))} "
                        f"unplanned), calls.json plans {len(planned)}")
    for e in finals:
        cid = e.get("call_id")
        if cid in planned and e.get("prompt_sha256") != planned[cid]:
            problems.append(f"{cid}: call_log prompt_sha256 {str(e.get('prompt_sha256'))[:12]!r} is not the planned "
                            f"prompt's ({planned[cid][:12]})")
    for r in rows:
        cid = r.get("call_id")
        if cid not in planned:
            problems.append(f"row {r.get('id')}: call {cid!r} is not planned")
        elif r.get("prompt_sha256") != planned[cid]:
            problems.append(f"row {r.get('id')}: prompt_sha256 is not the planned prompt's for {cid}")
    return problems


def review_problems(review_map: dict, sheet: list[dict], key: list[dict], checked: list[dict],
                    plan_sha256: str) -> list[str]:
    """Why the human-review bundle (review_map.json, review_sheet.csv, review_key.csv) does not sample the checked
    rows on disk: a map stamped with another checker plan, review ids that differ between the three files, a mapped
    row that is not a checked generated row, or sheet terms or key fields that differ from that row. Generated row
    ids are stable across runs, so ids alone would not show changed terms or verdicts (Codex review of PR #52)."""
    problems = []
    if review_map.get("checker_plan_sha256") != plan_sha256:
        problems.append(f"review_map.json checker_plan_sha256 {str(review_map.get('checker_plan_sha256'))[:12]!r} is "
                        f"not the plan on disk ({plan_sha256[:12]})")
    mapping = review_map.get("map", {})
    sheet_by = {r.get("id"): r for r in sheet}
    key_by = {r.get("id"): r for r in key}
    if not (sorted(mapping) == sorted(sheet_by, key=str) == sorted(key_by, key=str)):
        problems.append("review ids differ between review_map.json, review_sheet.csv and review_key.csv")
    by_row = {c["row_id"]: c for c in checked if c.get("source") == "generated"}
    for rid, row_id in mapping.items():
        c = by_row.get(row_id)
        if c is None:
            problems.append(f"{rid}: row {row_id} is not a checked generated row")
            continue
        s, k = sheet_by.get(rid), key_by.get(rid)
        if s and any(s.get(f) != c.get(f) for f in ("clinical_term", "patient_term", "template")):
            problems.append(f"{rid}: review_sheet.csv terms differ from checked row {row_id}")
        if k and (k.get("arm") != c.get("arm") or k.get("cell") != c.get("cell")
                  or k.get("checker_verdict") != c.get("verdict")):
            problems.append(f"{rid}: review_key.csv fields differ from checked row {row_id}")
    return problems
