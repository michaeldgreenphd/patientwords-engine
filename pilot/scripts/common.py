"""Shared helpers for the stimulus-generation pilot. Standard library only (Python 3.11+; a run sealed under 3.12 or
later, such as the recorded run in pilot/, is recomputed only under 3.12 or later: see sealed_interpreter_guard).

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
from collections.abc import Iterable
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
REQUIRED_FIELDS = ["clinical_term", "patient_term", "template", "control"]  # the version-1 row contract
# version 2 adds next_word, the word the template stops before (the probe word a later trace reads), in the key order
# the version-2 generation prompt lists
REQUIRED_FIELDS_V2 = ["clinical_term", "patient_term", "template", "next_word", "control"]
CONTROL_VALUES = ("none", "negative")
CHECKER_VERDICTS = ("yes", "no", "unclear")  # what the checker may answer (parse_checker.py)
VERDICT_VALUES = CHECKER_VERDICTS + ("missing",)  # what a checked row may carry; anything else is refused

# ---------------------------------------------------------------- harness version
# design.json's optional integer `harness_version` selects the row and checker contract; absent means 1, the contract
# the recorded run at pilot/ ran under, which every version-1 output keeps byte for byte. Version 2 adds next_word to
# every row; the checker's relation, sentence_natural and patient_realism; the probe-point, variant-design and
# next_word descriptives in the summary; and one review row per concept. Its design data (V2_DESIGN_KEYS) lives in
# the same file. Not to be confused with manifest_model.json's `harness_version`, the Claude Code version string.
HARNESS_VERSIONS = (1, 2)
V2_DESIGN_KEYS = ("probe_endings", "concepts_per_call", "variant_pairs_per_call", "review_sampling")
# version-2 prompt data: the example words the generation template's rules show (prompt_example_texts). Required and
# refused like V2_DESIGN_KEYS, but not recorded in the manifest's design block, which records the summary's design
# data; the prompts that show the examples are hashed one by one.
V2_PROMPT_DESIGN_KEYS = ("prompt_examples",)
REVIEW_SAMPLINGS = ("one_row_per_concept",)
# the version-2 checker's three further answers, each a closed set; the checker prompt must name every value
# (checker_enum_problems), so prompt and schema cannot drift apart
CHECKER_RELATIONS = ("same", "same_brand", "broader", "narrower", "different")
CHECKER_SENTENCE_NATURAL = ("both", "clinical_only", "patient_only", "neither")
CHECKER_PATIENT_REALISM = ("real", "textbook", "unlikely")
CHECKER_V2_FIELDS: dict[str, tuple[str, ...]] = {"relation": CHECKER_RELATIONS,
                                                 "sentence_natural": CHECKER_SENTENCE_NATURAL,
                                                 "patient_realism": CHECKER_PATIENT_REALISM}
# the equivalence each relation implies (codebook v0.2, L1-L5): an answer whose `equivalent` contradicts its relation
# is kept and flagged inconsistent, never dropped or corrected; `unclear` contradicts no relation
RELATION_EQUIVALENT = {"same": "yes", "same_brand": "yes", "broader": "yes", "narrower": "no", "different": "no"}
# the precision view the summary derives from the relation (codebook R6)
RELATION_PRECISION = {"same": "as_precise", "same_brand": "as_precise", "broader": "vaguer",
                      "narrower": "more_specific", "different": "not_applicable"}
PRECISION_VALUES = ("as_precise", "vaguer", "more_specific", "not_applicable")


def harness_version(design: dict) -> int:
    """The harness version a design file selects: its integer `harness_version`, 1 when absent. Anything else (a
    string, a boolean, an unknown number) is refused, never read as 1."""
    v = design.get("harness_version", 1)
    if isinstance(v, bool) or not isinstance(v, int) or v not in HARNESS_VERSIONS:
        raise SystemExit(f"design.json: harness_version must be an integer in {list(HARNESS_VERSIONS)} (absent means 1), "
                         f"got {v!r}; refusing to read the design")
    return v


def version_design_problems(design: dict) -> list[str]:
    """Why a design file's version data cannot be used. Version 1 must carry none of the version-2 keys: a design
    that names probe endings but no harness_version 2 would run version 1 and drop next_word without a word. Version 2
    must carry all of them: `probe_endings`, a non-empty list of distinct lowercase words; `concepts_per_call` and
    `variant_pairs_per_call`, integers that add up to the non-control rows a call asks for (each variant pair adds one
    row to a concept); `review_sampling`, one of REVIEW_SAMPLINGS; `prompt_examples`, whose shape
    prompt_example_texts checks before planning. Empty when the design can be used."""
    version = harness_version(design)
    keys = V2_DESIGN_KEYS + V2_PROMPT_DESIGN_KEYS
    if version < 2:
        present = [k for k in keys if k in design]
        return [f"design.json carries the version-2 key(s) {present} but no harness_version 2; add it, or remove them"] \
            if present else []
    problems = [f"design.json (harness_version 2) is missing {k!r}" for k in keys if k not in design]
    if problems:
        return problems
    ends = design["probe_endings"]
    if (not isinstance(ends, list) or not ends or len(set(map(str, ends))) != len(ends)
            or not all(isinstance(w, str) and w and w == w.lower() and not any(ch.isspace() for ch in w) for w in ends)):
        problems.append("design.json: probe_endings must be a non-empty list of distinct lowercase words")
    counts = [design[k] for k in ("concepts_per_call", "variant_pairs_per_call")]
    if any(isinstance(n, bool) or not isinstance(n, int) for n in counts) or counts[0] < 1 or counts[1] < 0:
        problems.append("design.json: concepts_per_call must be a positive integer and variant_pairs_per_call a "
                        "non-negative integer")
    elif counts[1] > counts[0] or sum(counts) != ROWS_PER_CALL - CONTROLS_PER_CALL:
        problems.append(f"design.json: concepts_per_call ({counts[0]}) plus variant_pairs_per_call ({counts[1]}) must equal "
                        f"the {ROWS_PER_CALL - CONTROLS_PER_CALL} non-control rows of a call, with no more pairs than "
                        f"concepts")
    if design["review_sampling"] not in REVIEW_SAMPLINGS:
        problems.append(f"design.json: review_sampling must be one of {list(REVIEW_SAMPLINGS)}, got "
                        f"{design['review_sampling']!r}")
    return problems


HARNESS_VERSION: int = harness_version(DESIGN)
_version_problems = version_design_problems(DESIGN)
if _version_problems:  # every script imports this module, so no script reads a design it cannot use
    raise SystemExit("design.json cannot be used:\n  " + "\n  ".join(_version_problems))
PROBE_ENDINGS: tuple[str, ...] = tuple(DESIGN.get("probe_endings", ()))  # version 2 only
CONCEPTS_PER_CALL: int | None = DESIGN.get("concepts_per_call")  # version 2 only
VARIANT_PAIRS_PER_CALL: int | None = DESIGN.get("variant_pairs_per_call")  # version 2 only


def plan_version(plan: dict) -> int:
    """The harness version a plan (calls.json, checker_batches.json) was derived under: the `harness_version` it
    records, which derive_plan and build_checker_set.derive write only for version 2 or later, so a version-1 plan
    stays byte-identical to the recorded run's. Anything other than an integer in HARNESS_VERSIONS (a string, a
    boolean, a null, an unknown number) is refused, as harness_version refuses it in design.json, never returned: a
    corrupted plan would otherwise raise a TypeError at the first `version >= 2` or select a contract no plan was
    derived under. make_review_sheet.py reads the checker plan's version from the file as it stands (Copilot review
    of PR #69)."""
    v = plan.get("harness_version", 1)
    if isinstance(v, bool) or not isinstance(v, int) or v not in HARNESS_VERSIONS:
        raise SystemExit(f"a plan file (calls.json or checker_batches.json) records harness_version {v!r}: it must be "
                         f"an integer in {list(HARNESS_VERSIONS)} (absent means 1); refusing to read the plan, re-run "
                         f"the step that wrote it")
    return v


def required_fields(version: int = HARNESS_VERSION) -> list[str]:
    """The keys a generated row must carry under a harness version, in the order the prompt lists them."""
    return REQUIRED_FIELDS_V2 if version >= 2 else REQUIRED_FIELDS


def checker_fields(version: int = HARNESS_VERSION) -> list[str]:
    """The keys every checker answer must carry under a harness version, in schema order."""
    return ["id", "equivalent", *CHECKER_V2_FIELDS, "reason"] if version >= 2 else ["id", "equivalent", "reason"]


def checker_output_schema(version: int, closed: bool) -> dict:
    """The checker's structured-output schema for a harness version 2 or later, built from the enums above (the
    version-1 schemas stay as literal text in make_workflow_scripts.py and build_api_requests.py, which must render
    the recorded run's bytes). `closed` adds additionalProperties false, as the Messages API request bodies carry."""
    if version < 2:
        raise ValueError("the version-1 checker schemas are literal text in their scripts")
    props = {"id": {"type": "string"}, "equivalent": {"type": "string", "enum": list(CHECKER_VERDICTS)},
             **{f: {"type": "string", "enum": list(v)} for f, v in CHECKER_V2_FIELDS.items()},
             "reason": {"type": "string"}}
    item: dict = {"type": "object", "properties": props, "required": checker_fields(version)}
    schema: dict = {"type": "object", "properties": {"verdicts": {"type": "array", "items": item}},
                    "required": ["verdicts"]}
    if closed:
        item["additionalProperties"] = False
        schema["additionalProperties"] = False
    return schema


def verdict_inconsistent(equivalent: str, relation: str) -> bool:
    """A version-2 answer whose `equivalent` contradicts its `relation` (yes with narrower or different, no with same,
    same_brand or broader). Such an answer is kept and flagged, never corrected; `unclear` contradicts nothing."""
    return equivalent in ("yes", "no") and RELATION_EQUIVALENT[relation] != equivalent


NEXT_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)?")  # letters, at most one internal hyphen or apostrophe


def next_word_ok(value: object) -> bool:
    """A version-2 row's next_word: a non-empty lowercase word of letters (any script), optionally with one internal
    hyphen or apostrophe (straight or typographic), and nothing else: no space, digit or other punctuation."""
    return isinstance(value, str) and NEXT_WORD_RE.fullmatch(value) is not None and value == value.lower()


def probe_endings_set(endings: Iterable[str]) -> frozenset[str]:
    """The probe endings lowercased, once: what probe_point_ok compares a template's last word with. A caller that
    tests many templates builds it once rather than per row (Copilot review of PR #69)."""
    return frozenset(e.lower() for e in endings)


def probe_point_ok(template: str, endings: frozenset[str]) -> bool:
    """Whether a template, stripped, ends on one of the probe endings: its last whitespace-separated word, lowercased,
    is in `endings`, the set probe_endings_set builds, so the comparison is case-insensitive. A word with punctuation
    attached ("my,") does not match. Version 2 reports this as a descriptive; it is not a format failure."""
    words = template.strip().split()
    return bool(words) and words[-1].lower() in endings
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
# the plans those two journals answered: the recorded run's per-call and per-batch prompt hashes, fingerprinted by
# plan_fingerprint (one hash over the sorted (id, prompt_sha256) pairs). A legacy result is parsed, and sealed, only
# against a plan with this fingerprint: a re-plan under changed inputs, --reset and a re-recording of the old
# transcripts could otherwise seal the responses under prompts they did not answer (Codex review of PR #52).
LEGACY_PLAN_FINGERPRINTS = {
    "faadf0993b9f9df16833db11e08c0656def1baa3719eaede59162905ec69c621":
        "86d00bb143d9448286540077e6e2e42988e798fc420965d7c2354fbb979e96ab",  # 18 generation calls
    "f5a81e6edf37cb8a9fc3825808275fd50ac9d41311333858c53a90cfc183d3f4":
        "6c20906c249a597a12cde35a5893008407d4e4abbacee386d98f412065dda6a0",  # 11 checker batches
}
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
    return call_id_of(arm, cell_id(specialty, swap_type))


def call_id_of(arm: str, cell: str) -> str:
    """The call id of an arm and a cell id: one call per arm per cell, so a checked row's arm and cell name its call."""
    return f"{arm}__{cell}"


def concept_key(call: str, clinical_term: str, template: str) -> tuple[str, str, str]:
    """A version-2 concept: the call, the clinical term's surface key and the exact template. A concept's second,
    vaguer patient phrasing shares all three; the review draws at most one row per concept and the variant-design
    descriptive counts concepts by this key."""
    return (call, surface_key(clinical_term), template)


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

def validate_line(line: str, version: int = HARNESS_VERSION) -> tuple[dict | None, str]:
    """Return (row, "ok") when the line is a format-valid row, else (None, reason). Never repairs. The reason is the
    first failing condition, in this order: JSON, object, required keys (all missing ones named), the three text
    fields, one blank in the template, (version 2) next_word, the control value."""
    try:
        obj = json.loads(line)
    except ValueError:
        return None, "not_json"
    if not isinstance(obj, dict):
        return None, "not_object"
    missing = [k for k in required_fields(version) if k not in obj]
    if missing:
        return None, "missing_field:" + ",".join(missing)
    for k in ("clinical_term", "patient_term", "template"):
        if not isinstance(obj[k], str) or not obj[k].strip():
            return None, f"empty_or_nonstring:{k}"
    if obj["template"].count(BLANK) != 1:
        return None, "template_blank_count_not_1"
    if version >= 2 and not next_word_ok(obj["next_word"]):
        return None, "next_word_invalid"
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


def checked_v2_problems(c: dict) -> list[str]:
    """Why a version-2 checked row's further answers are not what parse_checker.py writes: for a missing verdict,
    relation, sentence_natural, patient_realism and inconsistent all null; otherwise each answer in its set and
    `inconsistent` the boolean verdict_inconsistent gives. Empty when they are."""
    cid, extra = c.get("id"), (*CHECKER_V2_FIELDS, "inconsistent")
    if c.get("verdict") == "missing":
        return [] if all(c.get(k, 0) is None for k in extra) else [
            f"item {cid}: a missing verdict must carry null {list(extra)}"]
    bad = [f for f, values in CHECKER_V2_FIELDS.items() if c.get(f) not in values]
    if bad:
        return [f"item {cid}: {bad} not in their version-2 sets"]
    if c.get("inconsistent") is not verdict_inconsistent(c.get("verdict"), c["relation"]):
        return [(f"item {cid}: inconsistent {c.get('inconsistent')!r} does not describe verdict {c.get('verdict')!r} "
                 f"with relation {c['relation']!r}")]
    return []


def checked_problems(checked: list[dict], key: list[dict], blind: list[dict], plan_sha256: str,
                     version: int = HARNESS_VERSION) -> list[str]:
    """Why checked.jsonl does not belong to the checker plan on disk: an item set that differs from the truth key's
    (an item absent, unknown or repeated), an item whose fields differ from the key and the blind set, or a row
    stamped with another plan's hash (parse_checker.py writes `checker_plan_sha256`, the hash of the
    checker_batches.json it parsed against, on every row), or a verdict outside VERDICT_VALUES (a value such as
    "maybe" would leave both the answered and the missing counts and shrink every denominator unseen). A count-only
    check let a previous run's checked.jsonl pass beside a rebuilt checker set and mix its verdicts into a new run's
    summary (Codex review of PR #52). Under harness version 2 every row's further answers are checked too
    (checked_v2_problems). Empty when checked.jsonl is that plan's parse."""
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
        elif version >= 2:
            problems += checked_v2_problems(c)
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


def plan_fingerprint(prompt_hashes: dict[str, str]) -> str:
    """One hash over a plan's (id, prompt_sha256) pairs sorted by id: the generation calls or the checker batches."""
    return sha256_text(json.dumps(sorted(prompt_hashes.items())))


def legacy_plan_problems(result: dict, planned_hashes: dict[str, str]) -> list[str]:
    """Why one of the recorded run's legacy results (no protocol stamp, `source_sha256` in LEGACY_UNBOUND_SOURCES)
    may not be parsed against, or sealed under, the plan whose prompt hashes are `planned_hashes`: it answered the
    plan LEGACY_PLAN_FINGERPRINTS names and no other. Empty for a result that is not legacy, and for that plan. The
    parsers ask about the plan on disk; write_manifest.py finalize asks about the plan it is sealing (Codex review
    of PR #52)."""
    source = result.get("source_sha256")
    if result.get("protocol_sha256") is not None or source not in LEGACY_UNBOUND_SOURCES:
        return []
    want, got = LEGACY_PLAN_FINGERPRINTS[source], plan_fingerprint(planned_hashes)
    if got != want:
        return [f"a legacy result of the recorded run ({LEGACY_UNBOUND_SOURCES[source]}) answered the plan whose prompt "
                f"hashes fingerprint {want[:12]}; the plan on disk fingerprints {got[:12]} ({len(planned_hashes)} "
                f"prompts), so these responses did not answer these prompts"]
    return []


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


def result_binding_problems(result: dict, unbound: bool, planned_hashes: dict[str, str]) -> list[str]:
    """Why a recorded result file may not be parsed against this run: bound, its `protocol_sha256` (copied by the
    extractor from the agent labels the workflow script wrote) must be the frozen protocol on disk, so responses
    produced under another protocol, or by a script written before the protocol label, are refused; --unbound is
    accepted only for the recorded run's two result files (LEGACY_UNBOUND_SOURCES by `source_sha256`), which carry
    no hashes at all, and only under the protocol they ran under (LEGACY_PROTOCOL_SHA256) and against the plan they
    answered (LEGACY_PLAN_FINGERPRINTS, compared with `planned_hashes`, the plan on disk's id-to-prompt-hash map)
    (Codex review of PR #52). Empty when the result may be parsed."""
    stamp, source = result.get("protocol_sha256"), result.get("source_sha256")
    if unbound:
        if source not in LEGACY_UNBOUND_SOURCES:
            return [f"--unbound is accepted only for the recorded run's result files (source_sha256 one of "
                    f"{[k[:12] for k in LEGACY_UNBOUND_SOURCES]}), not this one ({str(source)[:12]!r}); a new run "
                    f"parses bound"]
        if stamp is not None:
            return ["a legacy result carries no protocol hash; this one does, so parse it bound"]
        return (legacy_protocol_problems(result, sha256_file(PILOT / "PROTOCOL.md"))
                + legacy_plan_problems(result, planned_hashes))
    current = sha256_file(PILOT / "PROTOCOL.md")
    if stamp != current:
        return [f"protocol_sha256 {str(stamp)[:12]!r} is not the frozen protocol on disk ({current[:12]}): the workflow "
                f"ran under another protocol, or from a script written before the protocol label, and its responses "
                f"are not this protocol's"]
    return []


def attempt_failed(raw: str | None, version: int = HARNESS_VERSION) -> bool:
    """PROTOCOL.md 3: a generation call has failed, and may be retried once, when the response is empty or no
    returned line parses as a JSON object carrying the required keys (four in version 1, five with next_word in
    version 2, as the workflow script's retry test counts them). Fewer than 20 rows, or some invalid rows, is not a
    failure. The parser refuses a second attempt whose first did not fail (Codex review of PR #52)."""
    for line in lines_of(raw):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and all(k in obj for k in required_fields(version)):
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


REVIEW_KEY_COLUMNS = ["id", "arm", "cell", "checker_verdict"]
# version 2 also shows the checker's three further answers in the key (the owner opens it only after reviewing)
REVIEW_KEY_COLUMNS_V2 = REVIEW_KEY_COLUMNS + ["checker_relation", "checker_sentence_natural", "checker_patient_realism"]


def review_key_columns(version: int = HARNESS_VERSION) -> list[str]:
    return REVIEW_KEY_COLUMNS_V2 if version >= 2 else REVIEW_KEY_COLUMNS


def review_problems(review_map: dict, sheet: list[dict], key: list[dict], checked: list[dict],
                    plan_sha256: str, version: int = HARNESS_VERSION) -> list[str]:
    """Why the human-review bundle (review_map.json, review_sheet.csv, review_key.csv) does not sample the checked
    rows on disk: a map stamped with another checker plan, review ids that differ between the three files, a mapped
    row that is not a checked generated row, or sheet terms or key fields that differ from that row (under version 2
    the key's relation, sentence_natural and patient_realism too, an empty cell for a missing verdict). Generated row
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
                  or k.get("checker_verdict") != c.get("verdict")
                  or (version >= 2 and any(k.get(f"checker_{f}") != (c.get(f) or "") for f in CHECKER_V2_FIELDS))):
            problems.append(f"{rid}: review_key.csv fields differ from checked row {row_id}")
    return problems


def plan_hash_problems(items: list[dict], id_key: str) -> list[str]:
    """Items of a plan whose stored `prompt_sha256` is not the SHA-256 of their `prompt`: an edited or inconsistently
    produced plan would otherwise send one text under another text's hash, and every binding downstream would carry
    the stale hash (Codex review of PR #52)."""
    return [f"{it.get(id_key)}: prompt_sha256 {str(it.get('prompt_sha256'))[:12]!r} is not the hash of its prompt"
            for it in items if not isinstance(it.get("prompt"), str) or sha256_text(it["prompt"]) != it.get("prompt_sha256")]


MARKER_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)  # any double-brace span, whatever it holds (Codex review of PR #52)
GENERATION_MARKERS = ("{{SPECIALTY}}", "{{SWAP_TYPE}}", "{{SWAP_DEFINITION}}", "{{CONTROL_EXAMPLE}}", "{{EXEMPLARS}}")
CHECKER_MARKERS = ("{{ITEMS}}",)
# Version 2: the example words and phrases the generation template's rules show live in design.json's
# `prompt_examples` and render into markers of their own, so no example vocabulary sits in the template or the code
# (engine AGENTS.md; moved out of the version-2 template on Codex's review of PR #69 with every rendered prompt
# byte-identical, as the example negative control moved on PR #52). Each field renders into one marker as "text"
# (verbatim), "list" (joined by ", ") or "alternatives" (each in double quotes, joined by " or "). {{PROBE_ENDINGS}}
# renders design.json's probe_endings as a list, so the prompt names exactly the endings the probe-point descriptive
# counts.
V2_PROMPT_EXAMPLES: dict[str, tuple[str, str]] = {
    "clinical_note_phrases": ("{{CLINICAL_NOTE_EXAMPLES}}", "alternatives"),  # rule 3: clinical-note prose
    "technical_term": ("{{TECHNICAL_TERM_EXAMPLE}}", "text"),  # rule 4: a technical term never used for ...
    "plain_word": ("{{PLAIN_WORD_EXAMPLE}}", "text"),  # ... a plain word clinicians also say
    "patient_phrases": ("{{PATIENT_PHRASE_EXAMPLES}}", "alternatives"),  # rule 5: what patients say, not ...
    "leaflet_wording": ("{{LEAFLET_WORDING_EXAMPLE}}", "text"),  # ... a health leaflet's wording
    "vaguer_patient_term": ("{{VAGUER_PATIENT_TERM_EXAMPLE}}", "text"),  # rule 6: a vaguer patient term for ...
    "vaguer_clinical_phrase": ("{{VAGUER_CLINICAL_PHRASE_EXAMPLE}}", "text"),  # ... a clinical term, with its article
    "probe_point_examples": ("{{PROBE_POINT_EXAMPLES}}", "alternatives"),  # rule 7: template endings
    "next_words": ("{{NEXT_WORD_EXAMPLES}}", "list"),  # rule 7: words that come next
}
V2_GENERATION_MARKERS = ("{{PROBE_ENDINGS}}", *(marker for marker, _ in V2_PROMPT_EXAMPLES.values()))


def generation_markers(version: int = HARNESS_VERSION) -> tuple[str, ...]:
    """The markers a generation template must carry, each exactly once and no other: version 1's five, and under
    version 2 also the probe endings and the rules' example words (V2_GENERATION_MARKERS), so a version-2 template is
    checked like a version-1 one and a version-1 template naming a version-2 marker is refused as unknown."""
    return GENERATION_MARKERS + V2_GENERATION_MARKERS if version >= 2 else GENERATION_MARKERS


SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]*")  # one file-name component, no separator, not hidden


def design_problems(specialties: list, swap_types: list) -> list[str]:
    """Why the design factors cannot be planned from: a specialty or swap type that is not a non-empty string, a
    repeated one, or two whose derived cell or call ids collide (cell_id replaces spaces with underscores, so two
    swap types that differ only there would name one cell), or a derived call id that is not a safe single file name.
    Duplicate ids would launch duplicate agents that the journal extractor refuses only after the run, and an unsafe
    id would break the parse after the previous one was removed (Codex review of PR #52). Empty when every id is
    distinct and safe."""
    problems = []
    for label, values in (("specialties", specialties), ("swap_types", swap_types)):
        if not isinstance(values, list) or not values or not all(isinstance(v, str) and v.strip() for v in values):
            problems.append(f"design.json: {label} must be a non-empty list of non-empty strings")
        elif len(set(values)) != len(values):
            problems.append(f"design.json: {label} repeat {sorted({v for v in values if values.count(v) > 1})}")
    if problems:
        return problems
    ids = [cell_id(s, t) for s in specialties for t in swap_types]
    if len(set(ids)) != len(ids):
        problems.append(f"design.json: two cells derive one id {sorted({i for i in ids if ids.count(i) > 1})}")
    cids = [call_id(a, s, t) for s in specialties for t in swap_types for a in ARMS]
    if len(set(cids)) != len(cids):
        problems.append(f"design.json: two calls derive one id {sorted({i for i in cids if cids.count(i) > 1})}")
    # call ids name files (generated/<id>.jsonl, generated/raw/<id>__attemptN.txt): a factor carrying a path
    # separator or another unsafe character would plan, run, and then break the parse after the previous one was
    # removed (Codex review of PR #52)
    unsafe = sorted({i for i in cids if not SAFE_ID_RE.fullmatch(i) or ".." in i})
    if unsafe:
        problems.append(f"design.json: call id(s) {unsafe[:3]} are not safe single file names (letters, digits, spaces, "
                        f"underscores, dots and hyphens only, not starting with a dot or a hyphen)")
    return problems


def template_problems(template: str, markers: tuple[str, ...], name: str) -> list[str]:
    """Why a prompt template cannot be rendered: a required marker absent or repeated, or a marker the renderer does
    not know (a misspelt one would survive rendering as literal text and the experiment would run without that
    condition) (Codex review of PR #52). Empty when every marker occurs exactly once and no other marker appears."""
    problems = [f"{name}: marker {m} occurs {template.count(m)} times, not once" for m in markers
                if template.count(m) != 1]
    unknown = sorted(set(MARKER_RE.findall(template)) - set(markers))
    if unknown:
        problems.append(f"{name}: unknown marker(s) {unknown}")
    rest = MARKER_RE.sub("", template)
    if "{{" in rest or "}}" in rest:
        problems.append(f"{name}: stray '{{{{' or '}}}}' outside the markers (a malformed marker would render as literal text)")
    return problems


def checker_enum_problems(template: str) -> list[str]:
    """Why a version-2 checker template does not match the version-2 schema: each answer field (equivalent and
    CHECKER_V2_FIELDS) must be named as a word, and each of its allowed values written in double quotes ("same_brand",
    "patient_only", ...). The schema accepts only those values, so a prompt that never offers one, or names a field
    the schema lacks, would bias or break the answers unseen. Empty when the template names every field and value."""
    problems = [f"field {f!r} is not named" for f in ("equivalent", *CHECKER_V2_FIELDS)
                if not re.search(rf"\b{re.escape(f)}\b", template)]
    missing = [v for values in (CHECKER_VERDICTS, *CHECKER_V2_FIELDS.values()) for v in values if f'"{v}"' not in template]
    if missing:
        problems.append(f"value(s) {missing} are not written in double quotes")
    return problems


def version_template_problems(template: str, kind: str, version: int = HARNESS_VERSION) -> list[str]:
    """Why a prompt template does not fit the harness version that will parse its answers. Version 1 refuses a
    template naming a version-2 field (next_word for generation; sentence_natural, patient_realism or same_brand for
    the checker): version 1 would ignore those answers and drop them without a word, which is what running the
    version-2 prompts under the recorded run's design.json would do. Version 2 requires the generation template to
    name every required key in double quotes and the checker template to name every answer field and value
    (checker_enum_problems). `kind` is "generation" or "checker". Empty when the template fits."""
    name = f"prompts/{kind}_prompt.txt"
    if version < 2:
        v2_only = ["next_word"] if kind == "generation" else ["sentence_natural", "patient_realism", "same_brand"]
        named = [f for f in v2_only if f in template]
        return [(f"{name} names the version-2 field(s) {named} but design.json is harness version 1, which would "
                 f"drop those answers; use the version-2 design.json (harness_version 2) with these prompts")] if named else []
    if kind == "generation":
        absent = [k for k in required_fields(version) if f'"{k}"' not in template]
        return [(f"{name} does not name the required key(s) {absent} in double quotes (harness version {version} "
                 f"requires {required_fields(version)})")] if absent else []
    return [f"{name} (harness version {version}): {p}" for p in checker_enum_problems(template)]


def stray_marker(text: str) -> str | None:
    """The first marker or stray double brace a rendered prompt still carries, or None: nothing that could be read as
    a placeholder may reach a subagent (Codex review of PR #52)."""
    found = MARKER_RE.search(text)
    if found:
        return found.group(0)
    return next((s for s in ("{{", "}}") if s in text), None)


def render_exemplars(rows: list[dict]) -> str:
    """The exemplar block a generation prompt shows: one JSON object per seed row, in the order drawn."""
    return "\n".join(json.dumps({"clinical_term": r["clinical_term"], "patient_term": r["patient_term"],
                                 "template": r["template"], "control": "none"}, ensure_ascii=False) for r in rows)


def control_example_text(design: dict) -> str:
    """The example negative control the generation prompt shows, rendered from design.json's `control_example` as
    one JSON object (the vocabulary lives in the data file, not in the template or the code: engine AGENTS.md; moved
    out of the template on Codex's review of PR #52, every rendered prompt byte-identical). Refused unless it is a
    row of the required shape, in key order, marked "negative", whose two terms are the same concept in the same
    register (surface form only), as the prompt says a negative control is. Under harness version 2 (read from the
    `design` passed) the example carries next_word too, in the version-2 key order, and its template ends on a probe
    ending, since the prompt says negative controls follow the probe-point rule like every other row."""
    version = harness_version(design)
    ex = design.get("control_example")
    row = validate_line(json.dumps(ex, ensure_ascii=False), version)[0] if isinstance(ex, dict) else None
    if (row is None or list(ex) != required_fields(version) or ex.get("control") != "negative"
            or not control_is_faithful(ex)):
        if version < 2:
            raise SystemExit("design.json: control_example must be an object with exactly the keys clinical_term, "
                             "patient_term, template (one ___) and control, in that order, control \"negative\", and the "
                             "two terms the same concept in the same register; refusing to plan")
        raise SystemExit("design.json (harness_version 2): control_example must be an object with exactly the keys "
                         "clinical_term, patient_term, template (one ___), next_word (one lowercase word) and control, in "
                         "that order, control \"negative\", and the two terms the same concept in the same register; "
                         "refusing to plan")
    if version >= 2 and not probe_point_ok(ex["template"], probe_endings_set(design.get("probe_endings") or ())):
        raise SystemExit("design.json (harness_version 2): control_example's template must end on one of probe_endings, "
                         "as the prompt asks of every row; refusing to plan")
    return json.dumps(ex, ensure_ascii=False)


def prompt_example_texts(design: dict) -> dict[str, str]:
    """What each version-2 example marker renders to, from the design passed: {{PROBE_ENDINGS}} the probe endings
    joined by ", ", and each marker of V2_PROMPT_EXAMPLES its field of `prompt_examples`. Refused unless the design is
    a usable version-2 design (version_design_problems) whose `prompt_examples` is an object with exactly those
    fields; each text, and each item of a list, a non-empty single line with no surrounding space, no double quote
    (the template quotes several of them) and no brace (an example cannot carry a marker); each list non-empty with
    no repeat; every next-word example a word next_word_ok accepts, and every probe-point example ending on a probe
    ending, since the prompt shows them as instances of rule 7. derive_plan calls it before rendering any prompt."""
    problems = version_design_problems(design)
    if not problems and harness_version(design) < 2:
        problems.append("prompt_examples are version-2 data; this design is harness version 1")
    ex = design.get("prompt_examples")
    if not problems and (not isinstance(ex, dict) or set(ex) != set(V2_PROMPT_EXAMPLES)):
        got = sorted(ex) if isinstance(ex, dict) else type(ex).__name__
        problems.append(f"prompt_examples must be an object with exactly the fields {sorted(V2_PROMPT_EXAMPLES)}, "
                        f"got {got}")
    texts: dict[str, str] = {}
    if not problems:
        def one_line(s: object) -> bool:
            return isinstance(s, str) and bool(s) and s == s.strip() and not any(c in s for c in '"{}\n\r')
        texts["{{PROBE_ENDINGS}}"] = ", ".join(design["probe_endings"])
        for field, (marker, form) in V2_PROMPT_EXAMPLES.items():
            v = ex[field]
            if form == "text" and not one_line(v):
                problems.append(f"prompt_examples.{field} must be one non-empty line of text with no surrounding "
                                f"space, double quote or brace")
            elif form != "text" and not (isinstance(v, list) and v and all(one_line(s) for s in v)
                                         and len(set(v)) == len(v)):
                problems.append(f"prompt_examples.{field} must be a non-empty list of distinct lines of text, each "
                                f"with no surrounding space, double quote or brace")
            else:
                texts[marker] = (v if form == "text" else ", ".join(v) if form == "list"
                                 else " or ".join(f'"{s}"' for s in v))
    if not problems:
        ends = probe_endings_set(design["probe_endings"])
        problems += [f"prompt_examples.next_words: {w!r} is not a next word rule 7 allows (one lowercase word)"
                     for w in ex["next_words"] if not next_word_ok(w)]
        problems += [f"prompt_examples.probe_point_examples: {s!r} does not end on one of probe_endings"
                     for s in ex["probe_point_examples"] if not probe_point_ok(s, ends)]
    if problems:
        raise SystemExit("design.json (harness_version 2) cannot render the generation prompt's examples; refusing to "
                         "plan:\n  " + "\n  ".join(problems))
    return texts


def render_generation_prompt(template: str, design: dict, specialty: str, swap_type: str,
                             exemplars: list[dict]) -> str:
    """One generation prompt from the template and the design passed, its markers replaced in a fixed order: the
    cell's specialty, swap type and definition; under harness version 2 the probe endings and the rules' example
    words (prompt_example_texts); the example negative control (control_example_text); the exemplar rows last, so no
    exemplar text is read as a marker. Under version 1 this is the recorded run's order exactly. derive_plan renders
    every call here."""
    definitions = {t["name"]: t["definition"] for t in design["swap_types"]}
    prompt = (template.replace("{{SPECIALTY}}", specialty)
              .replace("{{SWAP_TYPE}}", swap_type)
              .replace("{{SWAP_DEFINITION}}", definitions[swap_type]))
    if harness_version(design) >= 2:
        for marker, text in prompt_example_texts(design).items():
            prompt = prompt.replace(marker, text)
    return (prompt.replace("{{CONTROL_EXAMPLE}}", control_example_text(design))
            .replace("{{EXEMPLARS}}", render_exemplars(exemplars)))


def derive_plan(seeds: list[dict], template: str, seeds_sha256: str, design_sha256: str) -> dict:
    """The generation plan, pure and deterministic: Arm A exemplars drawn once per cell from the named stream in
    cell order, Arm B the first K seeds in file order, every prompt rendered from the template and hashed. plan_calls.py
    writes exactly this; load_calls derives it again and refuses a calls.json that differs (Codex review of PR #52).
    Under harness version 2 the plan records `harness_version`, the template must name every version-2 key and carry
    the version-2 markers, and the examples they show render from design.json; a version-1 plan carries no version
    key, byte-identical to the recorded run's."""
    problems = (design_problems(SPECIALTIES, SWAP_TYPES)
                + template_problems(template, generation_markers(HARNESS_VERSION), "prompts/generation_prompt.txt")
                + version_template_problems(template, "generation", HARNESS_VERSION))
    if problems:
        raise SystemExit("the design or the generation prompt template cannot be planned from; fix it before planning:"
                         "\n  " + "\n  ".join(problems))
    control_example_text(DESIGN)  # the design data a prompt shows, refused before any prompt is rendered
    if HARNESS_VERSION >= 2:
        prompt_example_texts(DESIGN)
    n = len(seeds)
    k = min(K_EXEMPLARS, n)
    r = rng("exemplars")
    fixed = seeds[:k]  # Arm B: the first k seeds in file order, identical in every call
    calls = []
    for specialty, swap_type in cells():
        sampled = r.sample(seeds, k)  # Arm A: one draw per cell, consumed in fixed cell order
        for arm, exemplars in (("A", sampled), ("B", fixed)):
            prompt = render_generation_prompt(template, DESIGN, specialty, swap_type, exemplars)
            stray = stray_marker(prompt)  # a marker or a brace carried in by an exemplar's or the example's own text
            if stray is not None:
                raise SystemExit(f"a rendered prompt ({call_id(arm, specialty, swap_type)}) still carries a marker or "
                                 f"stray braces {stray!r}; refusing to plan")
            calls.append({"id": call_id(arm, specialty, swap_type), "arm": arm, "specialty": specialty,
                          "swap_type": swap_type, "cell": cell_id(specialty, swap_type), "k_exemplars": k,
                          "exemplar_ids": [e["id"] for e in exemplars], "prompt_sha256": sha256_text(prompt),
                          "prompt": prompt})
    plan = {"harness_version": HARNESS_VERSION} if HARNESS_VERSION >= 2 else {}  # version 1: no key, as recorded
    return {**plan, "master_seed": MASTER_SEED, "n_seeds": n, "k_exemplars_used": k,
            "k_exemplars_requested": K_EXEMPLARS,
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
    (finalize) refuses a handoff whose block differs from this rendering (Codex review of PR #52).

    A summary that lacks a field the block renders was written by an earlier compute_summary.py: a version-2
    summary.json written before row_level_intervals existed (review round 3 of PR #69) is one. It is refused with
    the field's name and the step to take, as plan_version refuses a plan it cannot read, never rendered into a
    KeyError."""
    try:
        return _results_block_text(summary)
    except KeyError as e:
        raise SystemExit(f"summary.json has no field {e.args[0]!r}, which the handoff's results block renders: an "
                         f"earlier compute_summary.py wrote it; re-run compute_summary.py") from None


def _results_block_text(summary: dict) -> str:
    """results_block's rendering; a field missing from the summary raises the KeyError results_block names."""
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
    v2_lines = []
    if summary.get("harness_version", 1) >= 2:  # version 1 renders exactly the recorded block
        cv, pp, vd, nw, iv = (summary[k] for k in ("checker_v2", "probe_point", "variant_design", "next_word",
                                                   "row_level_intervals"))
        prec = cv["precision"]["generated"]
        top = ", ".join("{} ({})".format(x["word"], x["n"]) for x in nw["most_common"]) or "none"
        v2_lines = [
            (f"- **Intervals (version 2):** the intervals of estimands 1 to 5 are computed over rows, as the protocol "
             f"fixes them, and the rows are not independent draws: the rows of one call come from a single "
             f"generation, and by design {iv['rows_in_two_row_concepts_per_call']} of every "
             f"{iv['non_control_rows_per_call']} non-control rows of a call belong to "
             f"{iv['two_row_concepts_per_call']} two-row concepts ({iv['concepts']['total']} concepts in "
             f"{iv['non_control_rows']['total']} non-control rows here); read these intervals as descriptive."),
            (f"- **Checker relation (version 2), generated rows with a yes or no verdict:** "
             f"{json.dumps(cv['relation']['generated'])}; precision as precise {prec['as_precise']}, vaguer "
             f"{prec['vaguer']}, more specific {prec['more_specific']}, not applicable {prec['not_applicable']}; "
             f"unclear verdicts, whose relation is not counted, {cv['unclear_relation']['n']['generated']}; answers "
             f"whose equivalent contradicts their relation (kept, flagged inconsistent) "
             f"{cv['inconsistent']['total']}."),
            (f"- **Checker sentence and realism (version 2), generated rows:** sentence_natural "
             f"{json.dumps(cv['sentence_natural']['generated'])}; patient_realism "
             f"{json.dumps(cv['patient_realism']['generated'])}."),
            (f"- **Probe point (descriptive, not a format failure):** templates ending on a probe word "
             f"{w(pp['overall'])}; Arm A {w(pp['by_arm']['A'])}; Arm B {w(pp['by_arm']['B'])}."),
            (f"- **Variant design (descriptive):** calls with exactly {vd['expected_rows_per_call']} rows and "
             f"{vd['expected_concepts_per_call']} concepts, {vd['expected_pairs_per_call']} adjacent variant pairs, "
             f"and no concept split or run over three or more rows {w(vd['calls_compliant'])}; Arm A "
             f"{w(vd['by_arm']['A'])}; Arm B {w(vd['by_arm']['B'])}; adjacent variant pairs {vd['pairs_exact']} "
             f"(clinical term exact), {vd['pairs_clinical_surface']} (clinical term equal in surface form); "
             f"{len(vd['flagged_calls'])} call(s) flagged."),
            f"- **next_word:** {nw['n_distinct']} distinct words over {nw['n_rows']} rows; most common: {top}.",
        ]
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
        *v2_lines,
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
    """Why HANDOFF.md's Results section is not the summary's: no block, a summary the block cannot be rendered from
    (results_block's refusal, which names the missing field, is listed with summary_problems' others, as
    write_manifest.summary_recompute_problems lists a summary that no longer computes), or a block that differs from
    the rendering."""
    path = PILOT / "HANDOFF.md"
    parts = split_results_block(path.read_text(encoding="utf-8") if path.exists() else "")
    if parts is None:
        return ["HANDOFF.md carries no results block (the RESULTS_BEGIN and RESULTS_END markers, once, in order)"]
    try:
        rendered = results_block(summary)
    except SystemExit as e:
        return [str(e)]
    if parts[1].strip("\n") != rendered:
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


def finalized_run_guard(script: str, replace: bool) -> None:
    """Refuse a writer script's write into a run directory whose manifest.json is finalized, unless --replace was
    passed. Every script writes under PILOT_DIR and falls back to pilot/, the first recorded run, when it is unset, so
    a planning or rendering step run without it would write over a sealed record (plan_calls.py and
    make_workflow_scripts.py write unconditionally; rendering again would replace the recorded run's legacy workflow
    scripts). A later run lives in its own directory (pilot/runs/<run_id>/ once committed). With --replace the write
    goes ahead and the next write_manifest.py clears the finalization if any hashed output changed. A manifest that is
    not JSON is refused too, never read as unfinalized."""
    path = PILOT / "manifest.json"
    if replace or not path.exists():
        return
    try:
        finalized = json.loads(path.read_text(encoding="utf-8")).get("finalized_utc")
    except (ValueError, AttributeError):
        raise SystemExit(f"{script}: {path} cannot be read as a manifest; refusing to write into {PILOT}") from None
    if finalized:
        raise SystemExit(f"{script}: {PILOT} holds a finalized run (manifest.json finalized {finalized}); this script "
                         f"would write over its sealed files. Set PILOT_DIR to the run directory you mean (a new run "
                         f"lives in its own directory), or pass --replace to write here on purpose; nothing was written")


# Python 3.12 made sum() over floats compensated (Neumaier summation), so the summary's float sums (estimands 3 and 5)
# can differ in the last bit between an interpreter before 3.12 and one from 3.12 on. Within either side the values
# agree (the recorded run gives the same summary under 3.12.14 and 3.13.4).
FLOAT_SUM_CHANGED = (3, 12)


def float_sum_side(version: str) -> str:
    """Which side of the 3.12 change to sum() over floats a "major.minor[.patch]" interpreter version is on:
    "compensated" from 3.12 on, "plain" before. A version that is not of that form is refused."""
    m = re.fullmatch(r"(\d+)\.(\d+)(?:\.\S*)?", version) if isinstance(version, str) else None
    if not m:
        raise ValueError(f"not an interpreter version: {version!r}")
    return "compensated" if (int(m[1]), int(m[2])) >= FLOAT_SUM_CHANGED else "plain"


def sealed_interpreter_guard(script: str, running: str) -> None:
    """Refuse to recompute or rewrite a run directory whose manifest.json is finalized when the running interpreter
    is on the other side of the 3.12 sum() change from the interpreter that sealed it. Under such an interpreter
    compute_summary.py writes floats that differ in the last bit from the sealed ones, so a re-seal would flip the
    recorded summary between interpreters on every pull request that touches a pilot script. A finalized manifest
    that records no readable interpreter version, or that is not JSON, is refused too, never read as compatible."""
    path = PILOT / "manifest.json"
    if not path.exists():
        return
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
        finalized = m.get("finalized_utc")
    except (ValueError, AttributeError):
        raise SystemExit(f"{script}: {path} cannot be read as a manifest; refusing to work on {PILOT}") from None
    if not finalized:
        return
    sealed = m.get("python")
    try:
        sealed_side = float_sum_side(sealed)
    except ValueError:
        raise SystemExit(f"{script}: {path} is finalized but records no interpreter version ({sealed!r}); refusing to "
                         f"recompute a sealed run whose interpreter is unknown") from None
    if sealed_side != float_sum_side(running):
        need = (f"Python {FLOAT_SUM_CHANGED[0]}.{FLOAT_SUM_CHANGED[1]} or later" if sealed_side == "compensated"
                else f"a Python before {FLOAT_SUM_CHANGED[0]}.{FLOAT_SUM_CHANGED[1]}")
        raise SystemExit(f"{script}: {PILOT} was sealed under Python {sealed}, and this is Python {running}; sum() over "
                         f"floats changed in 3.12, so the summary's float sums would differ in the last bit from the "
                         f"sealed ones. Run this under {need}; nothing was written")


def log_binding(entries: list[dict]) -> bool | None:
    """Whether a parse was made with --unbound, read from the `plan_binding` every log entry records: False for a
    bound parse, True for an unbound one, None when the entries disagree or carry none (a parse to redo)."""
    values = {e.get("plan_binding") for e in entries}
    if values == {"prompt_sha256"}:
        return False
    if len(values) == 1 and isinstance(next(iter(values)), str) and next(iter(values)).startswith("none"):
        return True
    return None
