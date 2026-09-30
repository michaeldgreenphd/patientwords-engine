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
CHECKER_VERDICTS = ("yes", "no", "unclear")  # what the checker may answer (parse_checker.py)
VERDICT_VALUES = CHECKER_VERDICTS + ("missing",)  # what a checked row may carry; anything else is refused
# the recorded run's two journals (2026-09-29; their labels predate the prompt-hash and protocol-hash bindings): the
# only results the parsers accept with --unbound, so the escape hatch cannot parse a new run's responses against
# another plan or protocol (Codex review of PR #52)
LEGACY_UNBOUND_SOURCES = {
    "faadf0993b9f9df16833db11e08c0656def1baa3719eaede59162905ec69c621": "generation journal, run wf_028d99f0-c28",
    "f5a81e6edf37cb8a9fc3825808275fd50ac9d41311333858c53a90cfc183d3f4": "checker journal, run wf_453aa937-aff",
}
# the protocol those two journals ran under (PROTOCOL.md at the run, 2026-09-29). A legacy result is parsed, and
# sealed, only while the frozen protocol is this one: a protocol rewritten after the run and re-baselined with
# --reset could otherwise be finalized over the recorded outputs as "protocol_unchanged" (Codex review of PR #52).
LEGACY_PROTOCOL_SHA256 = "8dd838105e94a03190e81c841474479c8a27517553bdeabf9678f3550da5d969"
CHECKER_BATCH = 30
N_BROKEN = 20
N_KNOWN_GOOD = 10
N_REVIEW = 40
N_BOOT = 2000  # PROTOCOL.md fixes 2000; no override: one that leaked into a real run could finalize fewer (Codex review of PR #52)
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


def control_measurable(row: dict) -> bool:
    """A negative control can be judged only when both terms keep a letter or digit after normalization: two terms
    of punctuation alone both normalize to "" and would count as faithful with no lexical content compared (Codex
    review of PR #52). The summary excludes and counts such rows."""
    return bool(surface_key(row["clinical_term"])) and bool(surface_key(row["patient_term"]))


def control_is_faithful(row: dict) -> bool:
    """A negative control changed surface form only: same key on both sides, and a key to compare (a row that
    control_measurable rejects is never faithful)."""
    return control_measurable(row) and surface_key(row["clinical_term"]) == surface_key(row["patient_term"])


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

    def vector(self, doc: str) -> dict[str, float] | None:
        """The L2-normalised TF-IDF vector of doc, or None when doc has no token of two or more word characters:
        such a template has no measurable similarity, and an empty vector would score 0 against everything and
        pass as maximally diverse (Codex review of PR #52). Callers exclude and count None."""
        counts: dict[str, int] = {}
        for t in tokenize(doc):
            counts[t] = counts.get(t, 0) + 1
        vec = {t: c * self.idf.get(t, math.log((1 + self.n) / 1) + 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm > 0 else None


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
    checker_batches.json it parsed against, on every row), or a verdict outside VERDICT_VALUES (a value such as
    "maybe" would leave both the answered and the missing counts and shrink every denominator unseen). A count-only
    check let a previous run's checked.jsonl pass beside a rebuilt checker set and mix its verdicts into a new run's
    summary (Codex review of PR #52). Empty when checked.jsonl is that plan's parse."""
    by_key = {t["id"]: t for t in key}
    by_blind = {b["id"]: b for b in blind}
    ids = [c.get("id") for c in checked]
    problems = []
    if sorted(ids, key=str) != sorted(by_key):
        problems.append(f"item ids differ from checker_key.jsonl: {len(set(ids) - set(by_key))} unknown, "
                        f"{len(set(by_key) - set(ids))} absent, {len(ids) - len(set(ids))} repeated")
    for c in checked:
        cid = c.get("id")
        if c.get("verdict") not in VERDICT_VALUES or not isinstance(c.get("reason"), str):
            problems.append(f"item {cid}: verdict {c.get('verdict')!r} is not one of {list(VERDICT_VALUES)} with a "
                            f"text reason")
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


def resolve_input(path_str: str, script: str) -> Path:
    """A result-file argument: the path as given when it exists; otherwise a relative name looked up under the run
    directory (PILOT_DIR), since the documented commands name the file bare while the scripts run from the checkout
    (a laptop rerun on 2026-09-30 failed on this); refused by name when neither exists, never read as empty."""
    p = Path(path_str)
    if p.exists():
        return p
    if not p.is_absolute() and (PILOT / p).exists():
        print(f"{script}: {path_str} read from the run directory ({PILOT / p})")
        return PILOT / p
    raise SystemExit(f"{script}: {path_str} not found in the current directory or under {PILOT}")


def legacy_protocol_problems(result: dict, protocol_sha256: str) -> list[str]:
    """Why one of the recorded run's legacy results (no protocol stamp, `source_sha256` in LEGACY_UNBOUND_SOURCES)
    may not be attributed to the protocol `protocol_sha256`: it ran under LEGACY_PROTOCOL_SHA256 and no other. Empty
    for a result that is not legacy, and for the protocol it ran under. The parsers ask about the protocol on disk;
    write_manifest.py finalize asks about the protocol it is sealing (Codex review of PR #52)."""
    source = result.get("source_sha256")
    if result.get("protocol_sha256") is not None or source not in LEGACY_UNBOUND_SOURCES:
        return []
    if protocol_sha256 != LEGACY_PROTOCOL_SHA256:
        return [f"a legacy result of the recorded run ({LEGACY_UNBOUND_SOURCES[source]}) was produced under protocol "
                f"{LEGACY_PROTOCOL_SHA256[:12]}, not {str(protocol_sha256)[:12]}; it cannot be parsed or sealed as that "
                f"protocol's"]
    return []


def result_binding_problems(result: dict, unbound: bool) -> list[str]:
    """Why a recorded result file may not be parsed against this run: bound, its `protocol_sha256` (copied by the
    extractor from the agent labels the workflow script wrote) must be the frozen protocol on disk, so responses
    produced under another protocol, or by a script written before the protocol label, are refused; --unbound is
    accepted only for the recorded run's two result files (LEGACY_UNBOUND_SOURCES by `source_sha256`), which carry
    no hashes at all, and only under the protocol they ran under (LEGACY_PROTOCOL_SHA256) (Codex review of PR #52).
    Empty when the result may be parsed."""
    stamp, source = result.get("protocol_sha256"), result.get("source_sha256")
    if unbound:
        if source not in LEGACY_UNBOUND_SOURCES:
            return [f"--unbound is accepted only for the recorded run's result files (source_sha256 one of "
                    f"{[k[:12] for k in LEGACY_UNBOUND_SOURCES]}), not this one ({str(source)[:12]!r}); a new run "
                    f"parses bound"]
        if stamp is not None:
            return ["a legacy result carries no protocol hash; this one does, so parse it bound"]
        return legacy_protocol_problems(result, sha256_file(PILOT / "PROTOCOL.md"))
    current = sha256_file(PILOT / "PROTOCOL.md")
    if stamp != current:
        return [f"protocol_sha256 {str(stamp)[:12]!r} is not the frozen protocol on disk ({current[:12]}): the workflow "
                f"ran under another protocol, or from a script written before the protocol label, and its responses "
                f"are not this protocol's"]
    return []


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


def generation_problems(calls: dict, call_log: list[dict], rows: list[dict], failures: list[dict]) -> list[str]:
    """Why call_log.jsonl and the parsed rows do not belong to the call plan on disk: final records whose call ids
    differ from the plan's, a final record or row whose `prompt_sha256` (stamped by parse_generation.py from the
    plan it parsed against) is not the planned prompt's, or a final record whose valid and invalid line counts and
    attempt number do not match the rows and format failures on disk for its call. Call ids are stable across
    plans, so without the hash a previous run's responses would pass under re-planned prompts; and a parse
    interrupted between writing the rows and the log would leave a log that names the right plan beside rows it did
    not count (Codex review of PR #52). Empty when they belong."""
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
    final_attempt = {e.get("call_id"): e.get("attempt") for e in finals}
    for f in failures:  # every failure belongs to one planned final attempt and carries its prompt's hash
        cid = f.get("call_id")
        if cid not in planned or f.get("attempt") != final_attempt.get(cid):
            problems.append(f"failure at {cid} attempt {f.get('attempt')} line {f.get('line_index')}: belongs to no "
                            f"planned final attempt")
        elif f.get("prompt_sha256") != planned[cid]:
            problems.append(f"failure at {cid} line {f.get('line_index')}: prompt_sha256 is not the planned prompt's")
    for e in finals:
        cid, att = e.get("call_id"), e.get("attempt")
        mine = [r for r in rows if r.get("call_id") == cid]
        other_attempt = sum(1 for r in mine if r.get("attempt") != att)
        n_fail = sum(1 for f in failures if f.get("call_id") == cid and f.get("attempt") == att)
        if len(mine) != e.get("n_valid") or n_fail != e.get("n_invalid") or other_attempt:
            problems.append(f"{cid}: the final log record counts {e.get('n_valid')} valid and {e.get('n_invalid')} "
                            f"invalid lines (attempt {att}); the parsed files hold {len(mine)} rows "
                            f"({other_attempt} from another attempt) and {n_fail} failures")
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


def plan_hash_problems(items: list[dict], id_key: str) -> list[str]:
    """Items of a plan whose stored `prompt_sha256` is not the SHA-256 of their `prompt`: an edited or inconsistently
    produced plan would otherwise send one text under another text's hash, and every binding downstream would carry
    the stale hash (Codex review of PR #52)."""
    return [f"{it.get(id_key)}: prompt_sha256 {str(it.get('prompt_sha256'))[:12]!r} is not the hash of its prompt"
            for it in items if not isinstance(it.get("prompt"), str) or sha256_text(it["prompt"]) != it.get("prompt_sha256")]


MARKER_RE = re.compile(r"\{\{[A-Z_]+\}\}")
GENERATION_MARKERS = ("{{SPECIALTY}}", "{{SWAP_TYPE}}", "{{SWAP_DEFINITION}}", "{{EXEMPLARS}}")
CHECKER_MARKERS = ("{{ITEMS}}",)


def template_problems(template: str, markers: tuple[str, ...], name: str) -> list[str]:
    """Why a prompt template cannot be rendered: a required marker absent or repeated, or a marker the renderer does
    not know (a misspelt one would survive rendering as literal text and the experiment would run without that
    condition) (Codex review of PR #52). Empty when every marker occurs exactly once and no other marker appears."""
    problems = [f"{name}: marker {m} occurs {template.count(m)} times, not once" for m in markers
                if template.count(m) != 1]
    unknown = sorted(set(MARKER_RE.findall(template)) - set(markers))
    if unknown:
        problems.append(f"{name}: unknown marker(s) {unknown}")
    return problems


def render_exemplars(rows: list[dict]) -> str:
    """The exemplar block a generation prompt shows: one JSON object per seed row, in the order drawn."""
    return "\n".join(json.dumps({"clinical_term": r["clinical_term"], "patient_term": r["patient_term"],
                                 "template": r["template"], "control": "none"}, ensure_ascii=False) for r in rows)


def derive_plan(seeds: list[dict], template: str, seeds_sha256: str, design_sha256: str) -> dict:
    """The generation plan, pure and deterministic: Arm A exemplars drawn once per cell from the named stream in
    cell order, Arm B the first K seeds in file order, every prompt rendered from the template and hashed. plan_calls.py
    writes exactly this; load_calls derives it again and refuses a calls.json that differs (Codex review of PR #52)."""
    problems = template_problems(template, GENERATION_MARKERS, "prompts/generation_prompt.txt")
    if problems:
        raise SystemExit("the generation prompt template cannot be rendered; fix it before planning:\n  "
                         + "\n  ".join(problems))
    n = len(seeds)
    k = min(K_EXEMPLARS, n)
    r = rng("exemplars")
    fixed = seeds[:k]  # Arm B: the first k seeds in file order, identical in every call
    calls = []
    for specialty, swap_type in cells():
        sampled = r.sample(seeds, k)  # Arm A: one draw per cell, consumed in fixed cell order
        for arm, exemplars in (("A", sampled), ("B", fixed)):
            prompt = (template.replace("{{SPECIALTY}}", specialty)
                      .replace("{{SWAP_TYPE}}", swap_type)
                      .replace("{{SWAP_DEFINITION}}", SWAP_DEFINITIONS[swap_type])
                      .replace("{{EXEMPLARS}}", render_exemplars(exemplars)))
            if MARKER_RE.search(prompt):  # a marker carried in by an exemplar's own text
                raise SystemExit(f"a rendered prompt ({call_id(arm, specialty, swap_type)}) still carries a marker "
                                 f"{MARKER_RE.search(prompt).group(0)}; refusing to plan")
            calls.append({"id": call_id(arm, specialty, swap_type), "arm": arm, "specialty": specialty,
                          "swap_type": swap_type, "cell": cell_id(specialty, swap_type), "k_exemplars": k,
                          "exemplar_ids": [e["id"] for e in exemplars], "prompt_sha256": sha256_text(prompt),
                          "prompt": prompt})
    return {"master_seed": MASTER_SEED, "n_seeds": n, "k_exemplars_used": k, "k_exemplars_requested": K_EXEMPLARS,
            "generation_prompt_template_sha256": sha256_text(template),
            # the inputs this plan was rendered from: write_manifest.py refuses a plan whose inputs have since changed
            "input_hashes": {"seeds_json_sha256": seeds_sha256, "design_json_sha256": design_sha256,
                             "generation_prompt_template_sha256": sha256_text(template)},
            "calls": calls}


def load_calls() -> dict:
    """calls.json, refused unless it is exactly the plan derive_plan renders from the seed file, the design file and
    the generation template on disk. Self-consistency alone (every prompt hashing to its stored prompt_sha256) let a
    prompt edited together with its hash, or a planner that rendered the wrong prompt, run and finalize under the
    live input hashes (Codex review of PR #52). Every reader of the plan goes through here."""
    calls = json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))
    problems = plan_hash_problems(calls.get("calls", []), "id")
    ih = calls.get("input_hashes")
    if isinstance(ih, dict) and ih.get("generation_prompt_template_sha256") != calls.get("generation_prompt_template_sha256"):
        problems.append("generation_prompt_template_sha256 differs from input_hashes.generation_prompt_template_sha256")
    template = (PILOT / "prompts" / "generation_prompt.txt").read_text(encoding="utf-8")
    expected = derive_plan(load_seeds(), template, sha256_file(PILOT / "seeds.json"), sha256_file(PILOT / "design.json"))
    if calls != expected:
        top = sorted(k for k in set(calls) | set(expected) if k != "calls" and calls.get(k) != expected.get(k))
        where = f"top-level {top}" if top else "calls"
        if not top:
            got, want = calls.get("calls", []), expected["calls"]
            for i, (g, w) in enumerate(zip(got, want)):
                if g != w:
                    fields = sorted(k for k in set(g) | set(w) if g.get(k) != w.get(k))
                    where = f"call {i} ({w['id']}): {fields}"
                    break
            else:
                where = f"{len(got)} calls on disk, {len(want)} derived"
        problems.append(f"calls.json is not the plan the seed file, design file and template on disk derive "
                        f"(first difference: {where})")
    if problems:
        raise SystemExit("calls.json: refusing an inconsistent plan; re-run plan_calls.py:\n  " + "\n  ".join(problems[:5]))
    return calls


def load_checker_batches() -> dict:
    """checker_batches.json, refused unless it, checker_set.jsonl and checker_key.jsonl are exactly what
    build_checker_set.derive renders from generated/all_rows.jsonl, seeds.json and the checker template on disk.
    Self-consistency alone (every batch prompt hashing to its stored prompt_sha256 under unchanged input hashes) let
    a prompt edited together with its hash reach the checker subagents before finalize caught it (Codex review of
    PR #52). Every reader of the checker plan goes through here."""
    plan = json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))
    problems = plan_hash_problems(plan.get("batches", []), "batch_id")
    ih = plan.get("input_hashes")
    if isinstance(ih, dict) and ih.get("checker_prompt_template_sha256") != plan.get("checker_prompt_template_sha256"):
        problems.append("checker_prompt_template_sha256 differs from input_hashes.checker_prompt_template_sha256")
    import build_checker_set  # the scripts import each other by bare name; build_checker_set imports this module
    import rederive  # likewise: rederive imports this module and build_checker_set

    # the rows the bundle derives from must be the recorded generation journal's: a row whose text was edited under
    # intact ids, attempts and prompt hashes passed generation_problems, and checker work was emitted for data absent
    # from the journal, caught only at the summary (Codex review of PR #52)
    problems += rederive.generation_rederive_problems(load_calls())
    all_rows_path = PILOT / "generated" / "all_rows.jsonl"
    template = (PILOT / "prompts" / "checker_prompt.txt").read_text(encoding="utf-8")
    blind, truth, expected = build_checker_set.derive(read_jsonl(all_rows_path), load_seeds(), template,
                                                      sha256_file(PILOT / "seeds.json"), sha256_file(all_rows_path))
    if plan != expected:
        top = sorted(k for k in set(plan) | set(expected) if k != "batches" and plan.get(k) != expected.get(k))
        where = (f"top-level {top}" if top
                 else f"{len(plan.get('batches', []))} batches on disk, {len(expected['batches'])} derived")
        if not top:
            for i, (g, w) in enumerate(zip(plan.get("batches", []), expected["batches"])):
                if g != w:
                    where = f"batch {i} ({w['batch_id']}): {sorted(k for k in set(g) | set(w) if g.get(k) != w.get(k))}"
                    break
        problems.append(f"checker_batches.json is not the plan the rows, seed file and checker template on disk "
                        f"derive (first difference: {where})")
    if read_jsonl(PILOT / "checker_set.jsonl") != blind:
        problems.append("checker_set.jsonl is not the blind set the rows, seed file and checker template on disk derive")
    if read_jsonl(PILOT / "checker_key.jsonl") != truth:
        problems.append("checker_key.jsonl is not the truth key the rows, seed file and checker template on disk derive")
    if problems:
        raise SystemExit("checker_batches.json: refusing a plan that is not what the recorded generation and the inputs "
                         "on disk derive; re-run parse_generation.py --replace and build_checker_set.py:\n  "
                         + "\n  ".join(problems[:5]))
    return plan


SUMMARY_INPUTS = ("seeds.json", "design.json", "calls.json", "call_log.jsonl", "generated/all_rows.jsonl",
                  "generated/format_failures.jsonl", "checker_batches.json", "checker_set.jsonl", "checker_key.jsonl",
                  "checked.jsonl", "review_map.json", "review_sheet.csv", "review_key.csv")


RESULTS_BEGIN = "<!-- results:begin -->"
RESULTS_END = "<!-- results:end -->"


def results_block(summary: dict) -> str:
    """The handoff's Results section, rendered from summary.json's dictionaries so it cannot drift from the computed
    artifact: compute_summary.py writes it between RESULTS_BEGIN and RESULTS_END in HANDOFF.md, and summary_problems
    (finalize) refuses a handoff whose block differs from this rendering (Codex review of PR #52)."""
    def w(d: dict) -> str:
        return "0 / 0 (undefined)" if d["n"] == 0 else f"{d['x']} / {d['n']} = {d['p']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]"

    def m(d: dict) -> str:
        return f"{d['mean']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]" if d.get("mean") is not None else "undefined"

    def sd(d: dict) -> str:
        return f"{d['diff']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]" if d.get("diff") is not None else "undefined"

    run, e1, c, e2, e3, e4, e5 = (summary[k] for k in ("run", "E1", "controls", "E2", "E3", "E4", "E5"))
    g = e4["generated"]
    sens = e4["checker_sensitivity_known_good"]["unclear_counts_as_miss"]
    spec = e4["checker_specificity_broken"]["unclear_counts_as_miss"]
    return "\n".join([
        "(written by `scripts/compute_summary.py` from `summary.json`; finalize refuses a handoff whose block differs)",
        "",
        f"- **Run:** {run['n_calls']} calls, {run['n_attempts']} attempts, {run['n_retried_calls']} retried, "
        f"{run['calls_without_response']} without a response record; calls with a valid row "
        f"{w(run['calls_with_valid_rows'])}.",
        f"- **Estimand 1, format validity (final attempts):** {w(e1['overall'])}; Arm A {w(e1['by_arm']['A'])}; "
        f"Arm B {w(e1['by_arm']['B'])}.",
        f"- **Negative controls:** {c['n_control_rows']} returned ({c['expected']} expected), {c['unmeasurable']} "
        f"unmeasurable; faithful {w(c['faithful'])}.",
        f"- **Estimand 2, novelty (pair key):** Arm A {w(e2['by_arm']['A']['pair'])}; Arm B {w(e2['by_arm']['B']['pair'])}; "
        f"pooled {w(e2['pooled']['pair'])}; {e2['duplicates_of_seeds']} rows duplicate a seed pair.",
        f"- **Estimand 3, diversity (mean pairwise TF-IDF cosine of templates; lower is more diverse):** within cells "
        f"Arm A {m(e3['arm_mean_of_cells']['A'])}, Arm B {m(e3['arm_mean_of_cells']['B'])}; generated versus seed "
        f"templates Arm A {m(e3['vs_seeds']['A'])}, Arm B {m(e3['vs_seeds']['B'])}; {e3['n_boot']} bootstrap resamples.",
        f"- **Estimand 4, semantic equivalence:** judged yes {w(g['yes_over_answered'])}; verdict counts "
        f"{json.dumps(g['counts'], sort_keys=True)}; missing {g['missing']}; Arm A {w(e4['by_arm']['A']['yes_over_answered'])}; "
        f"Arm B {w(e4['by_arm']['B']['yes_over_answered'])}. Checker sensitivity on known-good rows {w(sens)}; "
        f"specificity on broken pairs {w(spec)} (unclear counts as a miss).",
        f"- **Estimand 5, Arm A minus Arm B:** novelty {sd(e5['novelty_pair'])} (Newcombe); within-cell similarity "
        f"{sd(e5['diversity_within_cell'])} (bootstrap); similarity to seeds {sd(e5['diversity_vs_seeds'])} (bootstrap); "
        f"equivalence {sd(e5['equivalence_yes'])} (Newcombe).",
    ])


def split_results_block(text: str) -> tuple[str, str, str] | None:
    """(before, inside, after) around the one results block in a handoff, or None when the markers are not there
    exactly once and in order."""
    if text.count(RESULTS_BEGIN) != 1 or text.count(RESULTS_END) != 1 or text.index(RESULTS_BEGIN) > text.index(RESULTS_END):
        return None
    before, rest = text.split(RESULTS_BEGIN, 1)
    inside, after = rest.split(RESULTS_END, 1)
    return before, inside, after


def write_results_block(summary: dict) -> None:
    """Write the results block into HANDOFF.md between its markers; refused when the handoff has no such block."""
    path = PILOT / "HANDOFF.md"
    parts = split_results_block(path.read_text(encoding="utf-8") if path.exists() else "")
    if parts is None:
        raise SystemExit(f"HANDOFF.md must carry one results block for compute_summary.py to write the Results section "
                         f"into: the lines {RESULTS_BEGIN} and {RESULTS_END}, in that order")
    before, _, after = parts
    path.write_text(before + RESULTS_BEGIN + "\n" + results_block(summary) + "\n" + RESULTS_END + after, encoding="utf-8")


def results_block_problems(summary: dict) -> list[str]:
    """Why HANDOFF.md's Results section is not the summary's: no block, or a block that differs from the rendering."""
    path = PILOT / "HANDOFF.md"
    parts = split_results_block(path.read_text(encoding="utf-8") if path.exists() else "")
    if parts is None:
        return ["HANDOFF.md carries no results block (the RESULTS_BEGIN and RESULTS_END markers, once, in order)"]
    if parts[1].strip("\n") != results_block(summary):
        return ["HANDOFF.md's results block is not what summary.json renders; re-run compute_summary.py, and put "
                "hand-written text outside the markers"]
    return []


def summary_problems(summary: dict) -> list[str]:
    """Why summary.json does not stand for the files on disk: an input whose hash differs from the one the summary
    recorded when it was computed (or none recorded), or a summary.md that is not the rendering the summary recorded.
    A finalize that only hashed the summary files would seal a summary computed from earlier inputs (Codex review of
    PR #52)."""
    recorded = summary.get("input_hashes")
    if not isinstance(recorded, dict):
        return ["summary.json records no input_hashes; re-run compute_summary.py"]
    missing = sorted(set(SUMMARY_INPUTS) - set(recorded))
    unexpected = sorted(set(recorded) - set(SUMMARY_INPUTS))
    if missing or unexpected:  # every input, not only the ones that happen to be recorded
        return [f"summary.json input_hashes do not cover exactly the summary's inputs (missing {missing}, unexpected "
                f"{unexpected}); re-run compute_summary.py"]
    problems = [f"{name}: changed since compute_summary.py ran (or missing)" for name, h in recorded.items()
                if not (PILOT / name).exists() or sha256_file(PILOT / name) != h]
    now = script_hashes()
    changed = sorted(n for n in set(now) | set(summary.get("script_hashes") or {})
                     if (summary.get("script_hashes") or {}).get(n) != now.get(n))
    if changed:  # the summary stands under the code that computed it; a script edit since means a recompute
        problems.append(f"{len(changed)} script(s) changed since compute_summary.py ran (first: {changed[0]}); "
                        f"re-run compute_summary.py")
    md = PILOT / "summary.md"
    if summary.get("summary_md_sha256") != (sha256_file(md) if md.exists() else None):
        problems.append("summary.md is not the rendering recorded in summary.json")
    problems += results_block_problems(summary)  # the handoff's numbers are the summary's (Codex review of PR #52)
    return problems


SCRIPTS_DIR = Path(__file__).resolve().parent


def script_hashes() -> dict[str, str]:
    """SHA-256 of every pilot script, by file name: what compute_summary.py records in summary.json and what
    summary_problems compares, so a summary never stands under code that did not compute it (Codex review of
    PR #52)."""
    return {p.name: sha256_file(p) for p in sorted(SCRIPTS_DIR.glob("*.py"))}


def log_binding(entries: list[dict]) -> bool | None:
    """Whether a parse was made with --unbound, read from the `plan_binding` every log entry records: False for a
    bound parse, True for an unbound one, None when the entries disagree or carry none (a parse to redo)."""
    values = {e.get("plan_binding") for e in entries}
    if values == {"prompt_sha256"}:
        return False
    if len(values) == 1 and isinstance(next(iter(values)), str) and next(iter(values)).startswith("none"):
        return True
    return None
