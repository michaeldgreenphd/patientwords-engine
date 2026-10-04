"""Physician verification ratings: import the app's export, check it, and compute agreement and summaries.

Reads one export written by the physician verification app (private repository michaeldgreenphd/patientwords-verify,
"Export for the engine" or the daily backup's ``export_<stamp>.json``; schema ``patientwords-verification-ratings/1``),
the task bundle it names (``data/verification/tasks_<stamp>.json``, found by its sha256) and the questions file
(``data/verification/questions.json``). Writes ``ratings_<bundle_id>_<export stamp>.summary.json`` and ``.summary.md``
to ``--out-dir`` (default ``data/verification/``), and, only with ``--write-proposed-adjudication``, a proposed
reference-tier file for the advice items that carry a proposed tier. docs/verification_protocol.md ("How ratings are
imported and analysed") is the plain-language description; the app's docs/DESIGN.md section 10 is the design this
follows.

Nothing here is a model call or a paid call, and no medical vocabulary is written in this file: question ids, scales,
answer values, tier ids and the tier order are read from the questions file, the bundle and
``data/advice_rubric.draft.json``.

Privacy. The export carries rater codes (``md01``, ``md02``, ...), assignments, answers and the physicians' notes,
never usernames, names or password data. The import refuses an export that carries any field outside its schema, a
field named after identity or credential data, a rater id that is not a code, or an email-shaped string outside the
two free-text places (notes and text answers). Note text and text answers are counted, never copied (owner decision
11 of the app's DESIGN.md: none is committed unless the owner has read the notes and listed them). The export itself
holds the notes, so it stays outside the repository.

Checks, each a named refusal (``REFUSED [code]``) that writes nothing:

* the export's schema and every field's type; ``bundle_sha256`` must equal the sha256 of the bundle file given with
  ``--bundle`` or found under ``data/verification/``, and ``bundle_id`` must match it; ``questions_sha256`` must equal
  the bundle's and the sha256 of the questions file, whose content must equal the bundle's copy;
* every event's item id is in the bundle and its question set is the item's; every answer key is a question of that
  set (per-version keys name one of the item's versions) and every value is allowed by the question's scale, with
  JSON types kept (``"3"`` is not ``3``); notes and text answers are strings within their length limits (counted in
  UTF-16 code units, as the app counts them); an event's ``bundle_sha256`` is the export's (one bundle per import);
* event ids are unique; rater ids are known codes; ``--exclude-rater`` names a rater in the export;
* the reveal step held: a reveal only on an item with a reveal step, after a save, once, with exactly the answers of
  the save before it, holding every required blind answer; no after-reveal answer before the reveal; every
  ``locks_on_reveal`` answer unchanged in every later save.

Derivations, per physician (rater) and item, events taken in the export's order, which is the Ratings tab's append
order (the app's own rule for "latest"):

* **current answers**: the latest ``save``; **first answers**: for each answer key, the value in the earliest save
  that answers it. Changes after the first answer are counted per question (changed, or cleared), over every rating
  by an included physician, finished or not.
* **blind answers of reveal items** (owner decision 18, as built: only the urgency question locks): every blind-phase
  answer is taken from the ``reveal`` event, which holds the saved answers at the moment the proposed urgency was
  shown; after-reveal answers come from the latest save. A blind answer changed, or first given, after the reveal
  is counted per question and never enters the analysis.
* **complete**: the current answers answer every required question (after-reveal ones too on an item with a reveal
  step), the app's rule, recomputed here from the questions; the app's own count is compared and any difference
  reported. **Only complete ratings enter the distributions, the agreement and the combined tier**; unfinished
  ratings are counted per item, set and physician.
* **exclusions**: physicians named with ``--exclude-rater`` (the owner's dummy test account, a wording-pilot
  physician) are left out after their events are checked, and the count of their events and ratings is recorded.
  No other physician is dropped: a physician whose status is ``removed`` stays in (their ratings are kept, as the app
  keeps them) and the output warns, naming them, so a forgotten test account shows.

Statistics (all per question set and question, because the same id is worded differently in different sets):

* **Krippendorff's alpha** (Krippendorff 2011, "Computing Krippendorff's Alpha-Reliability"), from the coincidence
  matrix o_ck = sum over units u of (number of c-k pairs of values from different physicians in u) / (m_u - 1), with
  m_u the number of values in u and units with m_u < 2 left out (they are not pairable); n_c = sum_k o_ck,
  n = sum_c n_c; alpha = 1 - (n - 1) * sum_ck o_ck d2_ck / sum_ck n_c n_k d2_ck. Nominal: d2_ck = 0 when c = k, else 1.
  Ordinal: for c < k, d2_ck = (sum over g from c to k of n_g - (n_c + n_k) / 2)^2, categories in the scale's order.
  Undefined (null, with the reason) when no unit is pairable or every pairable value is the same category. The
  metric follows the scale's ``type`` in the questions file: ``ordinal`` (the five-point realism and plausibility
  scales, the urgency scale, the clinical-term scale) or ``nominal``; multi-select and text questions get counts only.
  For a per-version question the unit is (item, version), pooled, and each version is also reported on its own.
* **Abstentions** (the scale's ``abstain`` answer, "Can't judge" / "Can't tell"; owner decision 10's default) are
  missing in the primary analysis and their count is reported; for nominal questions a sensitivity analysis counts
  them as one more category.
* **Interval**: percentile bootstrap over units, ``--resamples`` resamples (default 2000) of the pairable units with
  replacement, each analysis with its own ``random.Random`` seeded by the string "<seed>|<question set>|<key>|<variant>"
  (Python seeds a string through SHA-512, so it does not depend on PYTHONHASHSEED). Physicians are not resampled.
  Resamples where alpha is undefined are counted and left out; with fewer than half defined, no interval is given.
  The 2.5th and 97.5th percentiles are interpolated linearly between order statistics (position q * (B - 1)).
* **Pairwise agreement**: among all pairs of non-abstaining answers on the same unit, the share that are equal, and
  for ordinal scales the share at most one category apart. Every pair counts once.
* **Per item**: the distribution of every answer, the median and the share at the two lowest points (<= 2) of every
  question on a numeric five-point ordinal scale (realism and plausibility), and a flag when more than half of the
  item's non-abstaining physicians answered <= 2 (unrealistic or implausible). Notes and text answers counted.
* **Combined tier** (owner decision 9's default) for the question set whose items carry a proposed tier: the blind
  answers to the set's ``locks_on_reveal`` question, whose options are the advice rubric's tier ids; the median on the
  rubric's order (``data/advice_rubric.draft.json`` lists tiers least to most urgent; a tier's rank is its list
  position); with an even number of answers whose two middle tiers differ, the more urgent of the two; abstentions
  left out; no tier from fewer than 2 answers. Reported with its agreement with the proposed tier. It is a proposed
  adjudication, not in force until the owner records the combining rule in a pre-registration amendment.

Outputs (new files; an existing file is never replaced unless ``--overwrite``, and an identical rerun is a no-op):
the summary JSON and Markdown record the seed (and whether it was the default), the resample count, the sha256 of
every input and of this script, the script version, every exclusion and every warning. They carry item ids, source
ids, rater codes, answer values and counts only: no scenario text, no note, no name. The proposed adjudication has
the shape ``scripts/advice_eval.py analyze --stimuli`` reads, ``{"items": [{"id", "reference": {"tier",
"adjudicated_by"}}]}``, with ``id`` the advice stimuli id and ``adjudicated_by`` the rater codes and the rule; items
without a tier carry ``"reference": null``, which ``analyze`` skips. It is written next to the summary, not under
``data/advice/``.

Usage (from the engine root):
  python scripts/import_verification_ratings.py --export ~/Downloads/export_20261020T020000Z.json
      [--exclude-rater md01] [--bundle data/verification/tasks_<stamp>.json] [--questions ...] [--rubric ...]
      [--seed 20261004] [--resamples 2000] [--out-dir data/verification] [--write-proposed-adjudication]
      [--overwrite]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NoReturn, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT_VERSION = "1.0.0"
EXPORT_SCHEMA = "patientwords-verification-ratings/1"
BUNDLE_SCHEMA = "patientwords-verification-tasks/1"
SUMMARY_SCHEMA = "patientwords-verification-ratings-summary/1"
ADJUDICATION_STATUS = ("proposed adjudication, not in force until the owner records the combining rule in a "
                       "pre-registration amendment")
DEFAULT_SEED = 20261004
DEFAULT_RESAMPLES = 2000
CI_LEVEL = 0.95
# "Unrealistic" / "implausible": an answer at the two lowest points of a numeric five-point ordinal scale (1 or 2 on
# the realism and plausibility scales). A scale counts as five-point numeric when it is ordinal and its five option
# values are the integers 1 to 5, read from the questions file.
LOW_MAX = 2
FIVE_POINT_VALUES = [1, 2, 3, 4, 5]

DEFAULTS = {
    "verification_dir": REPO_ROOT / "data" / "verification",
    "questions": REPO_ROOT / "data" / "verification" / "questions.json",
    "rubric": REPO_ROOT / "data" / "advice_rubric.draft.json",
    "out_dir": REPO_ROOT / "data" / "verification",
}

# ---- the export's fields (app src/Logic.gs buildExport_); anything else is refused ---------------------------
EXPORT_KEYS = frozenset({"schema", "exported_utc", "app_version", "bundle_id", "bundle_sha256", "questions_sha256",
                         "settings", "raters", "assignments", "events"})
SETTINGS_KEYS = frozenset({"raters_per_item", "max_items_per_rater", "assignment_seed", "order_mode"})
RATER_KEYS = frozenset({"rater_id", "status", "consent_version", "consent_utc", "n_assigned", "n_complete"})
ASSIGNMENT_KEYS = frozenset({"rater_id", "item_id", "position", "order_key", "round", "status", "assigned_utc"})
EVENT_KEYS = frozenset({"event_id", "saved_utc", "rater_id", "item_id", "question_set", "event", "answers", "notes",
                        "position", "app_version", "bundle_sha256"})
# Field names of identity or credential data (the app's Users tab, and the obvious general ones): named in a
# refusal of their own, since an export carrying one is a privacy failure, not only a schema surprise.
IDENTITY_KEYS = frozenset({"username", "user", "display_name", "name", "email", "e_mail", "salt_hex", "hash_hex",
                           "iterations", "algo", "token_version", "failed_count", "locked_until_utc", "password",
                           "password_hash", "password_set_utc", "last_login_utc", "token"})
IDENTITY_WORDS = ("email", "password", "username", "display_name")
RATER_STATUSES = frozenset({"active", "paused", "removed"})
ASSIGNMENT_STATUSES = frozenset({"assigned", "released"})
ORDER_MODES = frozenset({"blocked", "mixed"})
EVENT_TYPES = frozenset({"save", "reveal"})

RATER_ID_RE = re.compile(r"^md\d{2,}$")
EVENT_ID_RE = re.compile(r"^ev_[0-9a-f]{8,64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d{1,6})?Z$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


# ---- refusals and small helpers ------------------------------------------------------------------------------

def refuse(code: str, message: str) -> NoReturn:
    """Stop with a named refusal. Messages carry ids, codes, keys and paths, never note or scenario text."""
    raise SystemExit(f"import_verification_ratings: REFUSED [{code}] {message}; nothing was written")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def logical_path(path: Path) -> str:
    """A path as the outputs record it: repository-relative inside this checkout, else the file name only (an
    export kept outside the repository is named by its file name and sha256, not by where it sits on a disk)."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units, as JavaScript's String.length counts it (the app's limits use that)."""
    return len(text.encode("utf-16-le")) // 2


def parse_utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not ISO_UTC_RE.match(value):
        refuse("bad_export", f"{where} is not an ISO-8601 UTC time")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        refuse("bad_export", f"{where} is not a real UTC time")


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def answered(value: Any) -> bool:
    """The app's rule (src/Logic.gs answered_): null, "" and [] are unanswered; everything else is an answer."""
    return value is not None and value != "" and value != []


def same_value(a: Any, b: Any) -> bool:
    """Equality that keeps JSON types apart (3 is not "3", true is not 1), as the app's === does."""
    return type(a) is type(b) and a == b


def read_file(path: Path, role: str) -> tuple[Any, bytes]:
    if not path.is_file():
        refuse("missing_input", f"{role}: {path} does not exist or is not a file")
    try:
        data = path.read_bytes()
    except OSError as exc:
        refuse("unreadable_input", f"{role}: cannot read {path} ({type(exc).__name__})")
    try:
        return json.loads(data.decode("utf-8-sig")), data
    except (UnicodeDecodeError, ValueError) as exc:
        refuse("unreadable_input", f"{role}: {path} is not UTF-8 JSON ({type(exc).__name__})")


def check_keys(obj: Any, allowed: frozenset[str], where: str) -> dict:
    """The object, after refusing a non-object, an identity field, an unknown field or a missing field."""
    if not isinstance(obj, dict):
        refuse("bad_export", f"{where} is not a JSON object")
    identity = sorted(k for k in obj if k.lower() in IDENTITY_KEYS or any(w in k.lower() for w in IDENTITY_WORDS))
    if identity:
        refuse("pii_field", f"{where} carries {identity}, identity or credential data the export must never carry")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        refuse("unexpected_field", f"{where} carries field(s) {unknown} outside the export schema")
    missing = sorted(allowed - set(obj))
    if missing:
        refuse("bad_export", f"{where} is missing field(s) {missing}")
    return obj


def need_str(value: Any, where: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        refuse("bad_export", f"{where} is not a string")
    return value


def need_rater_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not RATER_ID_RE.match(value):
        refuse("rater_id_not_pseudonymous", f"{where} is not a rater code like md01 (a username, name or address "
                                            "must never leave the app's Sheet)")
    return value


# ---- inputs ---------------------------------------------------------------------------------------------------

@dataclass
class Inputs:
    export: dict
    export_path: Path
    export_sha256: str
    bundle: dict
    bundle_path: Path
    bundle_sha256: str
    questions: dict
    questions_path: Path
    questions_sha256: str
    tier_order: list[str]
    rubric_path: Path
    rubric_sha256: str


def locate_bundle(bundle_sha: str, bundle_arg: str | None, verification_dir: Path) -> tuple[dict, Path, bytes]:
    """The bundle file whose bytes hash to the export's bundle_sha256: the one given, or the one found."""
    if bundle_arg:
        path = Path(bundle_arg)
        doc, data = read_file(path, "task bundle")
        if sha256_bytes(data) != bundle_sha:
            refuse("bundle_sha_mismatch", f"{path} has sha256 {sha256_bytes(data)[:16]}..., the export names "
                                          f"{bundle_sha[:16]}...; the ratings were given on another bundle")
        return doc, path, data
    for path in sorted(verification_dir.glob("tasks_*.json")):
        data = path.read_bytes()
        if sha256_bytes(data) == bundle_sha:
            doc, _ = read_file(path, "task bundle")
            return doc, path, data
    refuse("bundle_not_found", f"no tasks_*.json under {verification_dir} has the export's bundle_sha256 "
                               f"{bundle_sha[:16]}...; pass --bundle with the file the app served")


def load_inputs(args: argparse.Namespace) -> Inputs:
    export_path = Path(args.export)
    export, export_bytes = read_file(export_path, "ratings export")
    if not isinstance(export, dict):
        refuse("bad_export", "the export is not a JSON object")
    if export.get("schema") != EXPORT_SCHEMA:
        refuse("bad_schema", f"the export's schema is {export.get('schema')!r}, expected {EXPORT_SCHEMA!r}")
    check_keys(export, EXPORT_KEYS, "the export")
    bundle_sha = export["bundle_sha256"]
    if not isinstance(bundle_sha, str) or not SHA256_RE.match(bundle_sha):
        refuse("bad_export", "the export's bundle_sha256 is not a sha256")
    bundle, bundle_path, bundle_bytes = locate_bundle(bundle_sha, args.bundle, Path(args.verification_dir))
    if not isinstance(bundle, dict) or bundle.get("schema") != BUNDLE_SCHEMA:
        refuse("bad_bundle", f"{bundle_path} is not a {BUNDLE_SCHEMA} bundle")
    if export["bundle_id"] != bundle.get("bundle_id"):
        refuse("bundle_id_mismatch", f"the export names bundle {export['bundle_id']!r}, the file with its sha256 is "
                                     f"{bundle.get('bundle_id')!r}")

    questions_path = Path(args.questions)
    questions, q_bytes = read_file(questions_path, "questions")
    q_sha = sha256_bytes(q_bytes)
    if export["questions_sha256"] != bundle.get("questions_sha256") or q_sha != export["questions_sha256"]:
        refuse("questions_sha_mismatch",
               f"questions sha256: export {str(export['questions_sha256'])[:16]}..., bundle "
               f"{str(bundle.get('questions_sha256'))[:16]}..., {questions_path} {q_sha[:16]}...; all three must be "
               "the same file (for an older bundle, pass --questions with the questions.json of that bundle's "
               "commit, e.g. from git show)")
    if canonical(questions) != canonical(bundle.get("questions")):
        refuse("questions_content_mismatch", f"{questions_path} does not equal the bundle's copy of the questions")
    check_questions(questions)

    rubric_path = Path(args.rubric)
    rubric, r_bytes = read_file(rubric_path, "advice rubric (tier order)")
    tiers = rubric.get("tiers") if isinstance(rubric, dict) else None
    if not isinstance(tiers, list) or not tiers or not all(isinstance(t, dict) and isinstance(t.get("id"), str)
                                                          for t in tiers):
        refuse("bad_rubric", f"{rubric_path} has no list of tiers with ids")
    tier_order = [t["id"] for t in tiers]
    if len(set(tier_order)) != len(tier_order):
        refuse("bad_rubric", f"{rubric_path} lists a tier id twice")
    return Inputs(export, export_path, sha256_bytes(export_bytes), bundle, bundle_path, sha256_bytes(bundle_bytes),
                  questions, questions_path, q_sha, tier_order, rubric_path, sha256_bytes(r_bytes))


def check_questions(questions: Any) -> None:
    """Refuse a questions document this script cannot read (the exporter validated it in full; this checks only
    the parts the analysis relies on)."""
    if not isinstance(questions, dict):
        refuse("bad_questions", "the questions file is not an object")
    scales = questions.get("scales")
    sets = questions.get("question_sets")
    if not isinstance(scales, dict) or not isinstance(sets, dict):
        refuse("bad_questions", "the questions file lacks scales or question_sets")
    for name, scale in scales.items():
        if not isinstance(scale, dict) or scale.get("type") not in ("ordinal", "nominal", "multi", "text"):
            refuse("bad_questions", f"scale {name!r} has no known type")
        if not isinstance(scale.get("options", []), list):
            refuse("bad_questions", f"scale {name!r}: options is not a list")
    for set_name, qset in sets.items():
        qs = qset.get("questions") if isinstance(qset, dict) else None
        if not isinstance(qs, list):
            refuse("bad_questions", f"question set {set_name!r} has no question list")
        for q in qs:
            if not isinstance(q, dict) or q.get("scale") not in scales or q.get("phase") not in ("blind",
                                                                                                    "after_reveal"):
                refuse("bad_questions", f"question set {set_name!r}: a question lacks a known scale or phase")
    notes = questions.get("notes")
    if not isinstance(notes, dict) or not is_int(notes.get("max_length")):
        refuse("bad_questions", "notes.max_length is not an integer")


# ---- the bundle's items and their answer keys -------------------------------------------------------------------

@dataclass(frozen=True)
class KeySpec:
    """One answer key of one item: a question id, or "<question id>.<version id>" for a per-version question."""
    key: str
    question: dict
    scale_name: str
    scale: dict
    arm: str | None


def item_arms(item: dict) -> list[str]:
    display = item.get("display") or {}
    if display.get("kind") != "script":
        return []
    return [a["arm"] for a in display.get("arms", [])]


def item_keys(item: dict, questions: dict) -> dict[str, KeySpec]:
    qset = questions["question_sets"].get(item["question_set"])
    if qset is None:
        refuse("bad_bundle", f"item {item['item_id']}: question set {item['question_set']!r} is not in the questions")
    out: dict[str, KeySpec] = {}
    for q in qset["questions"]:
        scale = questions["scales"][q["scale"]]
        if q.get("per_arm"):
            for arm in item_arms(item):
                out[f"{q['id']}.{arm}"] = KeySpec(f"{q['id']}.{arm}", q, q["scale"], scale, arm)
        else:
            out[q["id"]] = KeySpec(q["id"], q, q["scale"], scale, None)
    return out


def option_values(scale: dict) -> list[Any]:
    return [o["value"] for o in scale.get("options", [])]


def abstain_value(scale: dict) -> Any:
    return scale["abstain"]["value"] if scale.get("abstain") else None


def is_abstain(scale: dict, value: Any) -> bool:
    return scale.get("abstain") is not None and same_value(value, abstain_value(scale))


def valid_value(scale: dict, value: Any) -> bool:
    """The app's validValue_ (src/Logic.gs), with JSON types kept apart."""
    values = option_values(scale)
    if scale["type"] == "text":
        return isinstance(value, str) and utf16_len(value) <= int(scale.get("max_length") or 1000)
    if scale["type"] == "multi":
        if is_abstain(scale, value):
            return True
        if not isinstance(value, list):
            return False
        seen: list[Any] = []
        for v in value:
            if not any(same_value(v, o) for o in values) or any(same_value(v, s) for s in seen):
                return False
            seen.append(v)
        return True
    return any(same_value(value, o) for o in values) or is_abstain(scale, value)


def is_five_point(scale: dict) -> bool:
    values = option_values(scale)
    return scale["type"] == "ordinal" and all(is_int(v) for v in values) and values == FIVE_POINT_VALUES


# ---- validation of the export and the event log -----------------------------------------------------------------

@dataclass
class Rating:
    """One physician's rating of one item: every save's answer map in log order, the reveal snapshot, the notes."""
    rater: str
    item_id: str
    saves: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    reveal: dict[str, Any] | None = None
    complete: bool = False

    @property
    def current(self) -> dict[str, Any]:
        return self.saves[-1] if self.saves else {}


@dataclass
class Checked:
    raters: list[dict]
    assignments: list[dict]
    ratings: dict[tuple[str, str], Rating]
    events_by_rater: Counter
    event_counts: Counter
    saved_utc_regressions: int


def scan_for_addresses(export: dict) -> None:
    """Refuse an email-shaped string anywhere outside the two free-text places (notes and text answers), which are
    never copied out. Rater codes, ids and times are format-checked elsewhere; this catches an address in any
    other string, such as a consent version or an app version typed by hand."""
    def walk(value: Any, where: str) -> None:
        if isinstance(value, str):
            if EMAIL_RE.search(value):
                refuse("pii_value", f"{where} holds an email-shaped string; the export must carry rater codes only")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{where}[{i}]")
        elif isinstance(value, dict):
            for k, v in value.items():
                if EMAIL_RE.search(str(k)):
                    refuse("pii_value", f"{where} has an email-shaped key")
                walk(v, f"{where}.{k}")

    for key in ("exported_utc", "app_version", "bundle_id", "settings", "raters", "assignments"):
        walk(export[key], key)
    for i, ev in enumerate(export["events"]):
        if isinstance(ev, dict):
            walk({k: v for k, v in ev.items() if k not in ("notes", "answers")}, f"events[{i}]")


def check_export(inp: Inputs) -> Checked:
    export, bundle, questions = inp.export, inp.bundle, inp.questions
    parse_utc(export["exported_utc"], "exported_utc")
    need_str(export["app_version"], "app_version")
    q_sha = export["questions_sha256"]
    if not isinstance(q_sha, str) or not SHA256_RE.match(q_sha):
        refuse("bad_export", "questions_sha256 is not a sha256")

    settings = check_keys(export["settings"], SETTINGS_KEYS, "settings")
    if not is_int(settings["raters_per_item"]) or settings["raters_per_item"] < 2:
        refuse("bad_export", "settings.raters_per_item is not an integer of at least 2")
    if not is_int(settings["max_items_per_rater"]) or settings["max_items_per_rater"] < 0:
        refuse("bad_export", "settings.max_items_per_rater is not a non-negative integer")
    need_str(settings["assignment_seed"], "settings.assignment_seed")
    if settings["order_mode"] not in ORDER_MODES:
        refuse("bad_export", f"settings.order_mode is not one of {sorted(ORDER_MODES)}")

    items = {i["item_id"]: i for i in bundle.get("items", [])}
    if not isinstance(export["raters"], list) or not isinstance(export["assignments"], list) or \
            not isinstance(export["events"], list):
        refuse("bad_export", "raters, assignments and events must be lists")

    raters: list[dict] = []
    seen_raters: set[str] = set()
    for n, r in enumerate(export["raters"]):
        where = f"raters[{n}]"
        check_keys(r, RATER_KEYS, where)
        rid = need_rater_id(r["rater_id"], f"{where}.rater_id")
        if rid in seen_raters:
            refuse("duplicate_rater", f"rater {rid} is listed twice")
        seen_raters.add(rid)
        if r["status"] not in RATER_STATUSES:
            refuse("bad_export", f"{where}.status is not one of {sorted(RATER_STATUSES)}")
        need_str(r["consent_version"], f"{where}.consent_version", nullable=True)
        if r["consent_utc"] is not None:
            parse_utc(r["consent_utc"], f"{where}.consent_utc")
        for k in ("n_assigned", "n_complete"):
            if not is_int(r[k]) or r[k] < 0:
                refuse("bad_export", f"{where}.{k} is not a non-negative integer")
        raters.append(r)

    assignments: list[dict] = []
    for n, a in enumerate(export["assignments"]):
        where = f"assignments[{n}]"
        check_keys(a, ASSIGNMENT_KEYS, where)
        rid = need_rater_id(a["rater_id"], f"{where}.rater_id")
        if rid not in seen_raters:
            refuse("unknown_rater", f"{where} names rater {rid}, who is not in the export's raters")
        if a["item_id"] not in items:
            refuse("unknown_item", f"{where} names item {a['item_id']!r}, which is not in bundle {bundle['bundle_id']}")
        if a["status"] not in ASSIGNMENT_STATUSES:
            refuse("bad_export", f"{where}.status is not one of {sorted(ASSIGNMENT_STATUSES)}")
        if a["position"] is not None and not (is_int(a["position"]) and a["position"] >= 1):
            refuse("bad_export", f"{where}.position is not a positive integer or null")
        round_ = a["round"]
        if round_ is not None and (isinstance(round_, bool) or not isinstance(round_, (int, float))):
            refuse("bad_export", f"{where}.round is not a number or null")
        need_str(a["order_key"], f"{where}.order_key")
        need_str(a["assigned_utc"], f"{where}.assigned_utc")
        assignments.append(a)

    scan_for_addresses(export)
    notes_max = int(questions["notes"]["max_length"])
    keys_of = {iid: item_keys(item, questions) for iid, item in items.items()}
    ratings: dict[tuple[str, str], Rating] = {}
    event_ids: set[str] = set()
    events_by_rater: Counter = Counter()
    event_counts: Counter = Counter()
    regressions = 0
    previous_time: datetime | None = None
    for n, ev in enumerate(export["events"]):
        where = f"events[{n}]"
        check_keys(ev, EVENT_KEYS, where)
        eid = ev["event_id"]
        if not isinstance(eid, str) or not EVENT_ID_RE.match(eid):
            refuse("bad_event", f"{where}.event_id is not an event id like ev_0123abcd")
        if eid in event_ids:
            refuse("duplicate_event_id", f"event id {eid} appears twice")
        event_ids.add(eid)
        where = f"event {eid}"
        when = parse_utc(ev["saved_utc"], f"{where}.saved_utc")
        if previous_time is not None and when < previous_time:
            regressions += 1
        previous_time = when
        rid = need_rater_id(ev["rater_id"], f"{where}.rater_id")
        if rid not in seen_raters:
            refuse("unknown_rater", f"{where} names rater {rid}, who is not in the export's raters")
        item = items.get(ev["item_id"])
        if item is None:
            refuse("unknown_item", f"{where} names item {ev['item_id']!r}, which is not in bundle "
                                   f"{bundle['bundle_id']}")
        if ev["question_set"] != item["question_set"]:
            refuse("question_set_mismatch", f"{where}: question set {ev['question_set']!r}, the bundle's item "
                                            f"{item['item_id']} is {item['question_set']!r}")
        if ev["event"] not in EVENT_TYPES:
            refuse("bad_event", f"{where}.event is not one of {sorted(EVENT_TYPES)}")
        if ev["bundle_sha256"] != export["bundle_sha256"]:
            refuse("event_bundle_mismatch", f"{where} was saved on bundle {str(ev['bundle_sha256'])[:16]}..., the "
                                            "export's bundle is another; this import reads one bundle at a time, so "
                                            "import that bundle's ratings on their own or exclude the rater")
        if ev["position"] is not None and not (is_int(ev["position"]) and ev["position"] >= 1):
            refuse("bad_event", f"{where}.position is not a positive integer or null")
        need_str(ev["app_version"], f"{where}.app_version")
        notes = ev["notes"]
        if not isinstance(notes, str):
            refuse("bad_notes", f"{where}.notes is not a string")
        if utf16_len(notes) > notes_max:
            refuse("notes_too_long", f"{where}: notes exceed {notes_max} characters")
        answers = ev["answers"]
        if not isinstance(answers, dict):
            refuse("bad_answers", f"{where}.answers is not an object")
        keys = keys_of[item["item_id"]]
        clean: dict[str, Any] = {}
        for k, v in answers.items():
            spec = keys.get(k)
            if spec is None:
                refuse("unknown_question", f"{where}: answer key {k!r} is not a question of set "
                                           f"{item['question_set']!r} on item {item['item_id']}")
            if not answered(v):
                continue
            if not valid_value(spec.scale, v):
                refuse("bad_value", f"{where}: the answer to {k!r} is not an allowed value of scale "
                                    f"{spec.scale_name!r}")
            clean[k] = v
        events_by_rater[rid] += 1
        event_counts[ev["event"]] += 1
        rating = ratings.setdefault((rid, item["item_id"]), Rating(rid, item["item_id"]))
        apply_event(rating, ev["event"], clean, notes, item, keys, where)

    for rating in ratings.values():
        item = items[rating.item_id]
        rating.complete = is_complete(rating, keys_of[rating.item_id], item.get("reveal") is not None)
    return Checked(raters, assignments, ratings, events_by_rater, event_counts, regressions)


def apply_event(rating: Rating, kind: str, answers: dict[str, Any], notes: str, item: dict,
                keys: dict[str, KeySpec], where: str) -> None:
    """Add one event to a rating, refusing anything the app's reveal rules would have refused."""
    has_reveal_step = item.get("reveal") is not None
    if kind == "reveal":
        if not has_reveal_step:
            refuse("reveal_without_step", f"{where}: a reveal on item {item['item_id']}, which has no proposed "
                                          "answer to reveal")
        if not rating.saves:
            refuse("reveal_before_save", f"{where}: a reveal before any save of rater {rating.rater} on item "
                                         f"{item['item_id']}")
        if rating.reveal is not None:
            refuse("duplicate_reveal", f"{where}: a second reveal of rater {rating.rater} on item {item['item_id']}")
        if canonical(answers) != canonical(rating.current):
            refuse("reveal_snapshot_mismatch", f"{where}: the reveal's answers are not the answers of the save "
                                               "before it, which the app copies into the reveal")
        missing = sorted(s.key for s in keys.values()
                         if s.question.get("required") and s.question["phase"] == "blind" and s.key not in answers)
        if missing:
            refuse("reveal_blind_incomplete", f"{where}: the reveal lacks required blind answer(s) {missing}")
        rating.reveal = dict(answers)
        return
    early = sorted(k for k in answers if keys[k].question["phase"] == "after_reveal" and rating.reveal is None)
    if early:
        refuse("answer_before_reveal", f"{where}: after-reveal answer(s) {early} saved before the reveal")
    if rating.reveal is not None:
        for spec in keys.values():
            if spec.question.get("locks_on_reveal"):
                if canonical(answers.get(spec.key)) != canonical(rating.reveal.get(spec.key)):
                    refuse("lock_broken", f"{where}: {spec.key!r} changed after the reveal, which locks it")
    rating.saves.append(dict(answers))
    rating.notes = notes


def is_complete(rating: Rating, keys: dict[str, KeySpec], has_reveal_step: bool) -> bool:
    """The app's itemComplete_ on the latest save: every required question answered; an after-reveal one only
    where the item has a reveal step."""
    if not rating.saves:
        return False
    current = rating.current
    for spec in keys.values():
        if not spec.question.get("required"):
            continue
        if spec.question["phase"] == "after_reveal" and not has_reveal_step:
            continue
        if spec.key not in current:
            return False
    return True


def first_answers(rating: Rating) -> dict[str, Any]:
    """Each key's value in the earliest save that answers it."""
    out: dict[str, Any] = {}
    for answers in rating.saves:
        for k, v in answers.items():
            out.setdefault(k, v)
    return out


def analysis_value(rating: Rating, spec: KeySpec, has_reveal_step: bool) -> Any:
    """The answer the analysis uses: a blind answer of a revealed item as of the reveal, else the current one."""
    if has_reveal_step and spec.question["phase"] == "blind" and rating.reveal is not None:
        return rating.reveal.get(spec.key)
    return rating.current.get(spec.key)


# ---- Krippendorff's alpha ----------------------------------------------------------------------------------------

def unit_coincidences(values: Sequence[int]) -> list[tuple[int, int, float]]:
    """One unit's contribution to the coincidence matrix: (c, k, weight) with weight = number of ordered c-k pairs of
    values from different coders, divided by m_u - 1 (Krippendorff 2011, section C). Empty when m_u < 2."""
    m = len(values)
    if m < 2:
        return []
    counts = Counter(values)
    out = []
    for c, nc in counts.items():
        for k, nk in counts.items():
            pairs = nc * (nk - 1) if c == k else nc * nk
            if pairs:
                out.append((c, k, pairs / (m - 1)))
    return out


def coincidence_matrix(units: Iterable[Sequence[int]], n_categories: int) -> list[list[float]]:
    o = [[0.0] * n_categories for _ in range(n_categories)]
    for values in units:
        for c, k, w in unit_coincidences(values):
            o[c][k] += w
    return o


def delta2(marginals: Sequence[float], metric: str) -> list[list[float]]:
    """Squared difference function. Nominal: 0 on the diagonal, 1 elsewhere. Ordinal (Krippendorff 2011, section D):
    for c < k, (sum of n_g for g from c to k, minus (n_c + n_k) / 2) squared, symmetric; categories in scale order."""
    size = len(marginals)
    d = [[0.0] * size for _ in range(size)]
    for c in range(size):
        for k in range(c + 1, size):
            if metric == "nominal":
                v = 1.0
            elif metric == "ordinal":
                v = (sum(marginals[c:k + 1]) - (marginals[c] + marginals[k]) / 2.0) ** 2
            else:
                raise ValueError(f"unknown metric {metric!r}")
            d[c][k] = d[k][c] = v
    return d


def alpha_from_matrix(o: Sequence[Sequence[float]], metric: str) -> tuple[float | None, str | None]:
    """(alpha, None), or (None, reason) when alpha is undefined: alpha = 1 - (n - 1) * sum o_ck d2_ck /
    sum n_c n_k d2_ck, the paper's computational form."""
    marginals = [sum(row) for row in o]
    n = sum(marginals)
    if n <= 1:
        return None, "no pairable values (no unit has answers from two physicians)"
    d = delta2(marginals, metric)
    size = len(marginals)
    observed = sum(o[c][k] * d[c][k] for c in range(size) for k in range(size))
    expected = sum(marginals[c] * marginals[k] * d[c][k] for c in range(size) for k in range(size))
    if expected <= 0:
        return None, "every pairable answer is the same category, so chance disagreement is zero"
    return 1.0 - (n - 1) * observed / expected, None


def krippendorff_alpha(units: Iterable[Sequence[int]], n_categories: int, metric: str) -> float | None:
    """Krippendorff's alpha over units of category indices (0-based, in scale order); None when undefined."""
    return alpha_from_matrix(coincidence_matrix(units, n_categories), metric)[0]


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics at position q * (B - 1) (numpy's default "linear")."""
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def alpha_with_interval(units: list[list[int]], n_categories: int, metric: str, resamples: int,
                        rng: random.Random) -> dict[str, Any]:
    """Point alpha over the pairable units and a percentile bootstrap interval over those units."""
    pairable = [u for u in units if len(u) >= 2]
    contributions = [unit_coincidences(u) for u in pairable]
    o = [[0.0] * n_categories for _ in range(n_categories)]
    for contrib in contributions:
        for c, k, w in contrib:
            o[c][k] += w
    value, reason = alpha_from_matrix(o, metric)
    out: dict[str, Any] = {
        "value": None if value is None else round(value, 6),
        "undefined_reason": reason,
        "pairable_units": len(pairable),
        "pairable_values": sum(len(u) for u in pairable),
        "ci95": None,
        "ci_note": None,
        "resamples_defined": 0,
        "resamples_undefined": 0,
    }
    if not pairable:
        out["ci_note"] = "no pairable units"
        return out
    replicates: list[float] = []
    undefined = 0
    size = len(pairable)
    for _ in range(resamples):
        rep = [[0.0] * n_categories for _ in range(n_categories)]
        for _j in range(size):
            for c, k, w in contributions[rng.randrange(size)]:
                rep[c][k] += w
        a, _r = alpha_from_matrix(rep, metric)
        if a is None:
            undefined += 1
        else:
            replicates.append(a)
    out["resamples_defined"] = len(replicates)
    out["resamples_undefined"] = undefined
    if len(replicates) * 2 < resamples:
        out["ci_note"] = "fewer than half of the resamples have a defined alpha; no interval"
        return out
    replicates.sort()
    tail = (1.0 - CI_LEVEL) / 2.0
    out["ci95"] = [round(percentile(replicates, tail), 6), round(percentile(replicates, 1.0 - tail), 6)]
    return out


def pairwise_agreement(units: list[list[int]], ordinal: bool) -> dict[str, Any]:
    """Share of equal answer pairs (and, ordinal, pairs at most one category apart) within units; each pair once."""
    n_pairs = exact = within = 0
    for values in units:
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                n_pairs += 1
                exact += values[i] == values[j]
                within += abs(values[i] - values[j]) <= 1
    out: dict[str, Any] = {"pairs": n_pairs, "exact": round(exact / n_pairs, 6) if n_pairs else None}
    if ordinal:
        out["within_one"] = round(within / n_pairs, 6) if n_pairs else None
    return out


# ---- the analysis -------------------------------------------------------------------------------------------------

@dataclass
class Unit:
    """One rated unit: an item, or an (item, version) pair for a per-version question."""
    item_id: str
    arm: str | None
    values: list[tuple[str, Any]]  # (rater, value or None for unanswered), complete ratings only


def distribution(scale: dict, values: Iterable[Any]) -> list[dict[str, Any]]:
    """Counts per answer value in the scale's order, the abstain answer last, then unanswered."""
    values = list(values)
    out = []
    for v in option_values(scale):
        out.append({"value": v, "n": sum(1 for x in values if same_value(x, v))})
    if scale.get("abstain"):
        out.append({"value": abstain_value(scale), "n": sum(1 for x in values if is_abstain(scale, x)),
                    "abstain": True})
    out.append({"value": None, "n": sum(1 for x in values if x is None), "unanswered": True})
    return out


def multi_counts(scale: dict, values: Iterable[Any]) -> dict[str, Any]:
    values = list(values)
    lists = [v for v in values if isinstance(v, list)]
    return {"ratings": len(values), "ratings_with_any_flag": len(lists),
            "flag_counts": [{"value": o, "n": sum(1 for v in lists if any(same_value(o, x) for x in v))}
                            for o in option_values(scale)]}


def five_point_stats(values: Iterable[Any]) -> dict[str, Any]:
    nums = [v for v in values if is_int(v)]
    low = sum(1 for v in nums if v <= LOW_MAX)
    return {"n": len(nums), "median": statistics.median(nums) if nums else None, "n_low": low,
            "share_low": round(low / len(nums), 6) if nums else None,
            "majority_low": bool(nums) and low * 2 > len(nums)}


def analyse_key(set_name: str, label: str, spec_of: dict[str, KeySpec], units: list[Unit], seed: int,
                resamples: int) -> dict[str, Any]:
    """Distribution and agreement for one question (or one version of a per-version question)."""
    spec = next(iter(spec_of.values()))
    scale = spec.scale
    all_values = [v for u in units for _r, v in u.values]
    rec: dict[str, Any] = {
        "question": spec.question["id"],
        "version": spec.arm if label != spec.question["id"] else None,
        "scale": spec.scale_name,
        "scale_type": scale["type"],
        "phase": spec.question["phase"],
        "required": bool(spec.question.get("required")),
        "unit": "item and version" if spec.question.get("per_arm") and label == spec.question["id"] else "item",
        "units": len(units),
        "units_rated": sum(1 for u in units if u.values),
        "ratings": len(all_values),
        "answers": sum(1 for v in all_values if v is not None and not is_abstain(scale, v)),
        "abstentions": sum(1 for v in all_values if v is not None and is_abstain(scale, v)),
        "unanswered": sum(1 for v in all_values if v is None),
    }
    if scale["type"] == "text":
        rec["note"] = "free text: counted only, never copied"
        return rec
    if scale["type"] == "multi":
        rec.update(multi_counts(scale, all_values))
        rec["note"] = "multi-select: an empty answer cannot be told from 'looked and found nothing'; no coefficient"
        return rec
    rec["distribution"] = distribution(scale, all_values)
    if is_five_point(scale):
        rec["five_point"] = five_point_stats(all_values)
    options = option_values(scale)
    index = {canonical(v): i for i, v in enumerate(options)}

    def coded(abstain_as_category: bool) -> list[list[int]]:
        out = []
        for u in units:
            vals = []
            for _r, v in u.values:
                if v is None:
                    continue
                if is_abstain(scale, v):
                    if abstain_as_category:
                        vals.append(len(options))
                    continue
                vals.append(index[canonical(v)])
            out.append(vals)
        return out

    primary = coded(False)
    rec["units_with_fewer_than_2_answers"] = sum(1 for u in primary if len(u) < 2)
    metric = scale["type"]
    rng = random.Random(f"{seed}|{set_name}|{label}|primary")
    rec["alpha"] = {"metric": metric, **alpha_with_interval(primary, len(options), metric, resamples, rng)}
    rec["pairwise_agreement"] = pairwise_agreement(primary, metric == "ordinal")
    if metric == "nominal" and scale.get("abstain"):
        rng = random.Random(f"{seed}|{set_name}|{label}|abstain_as_category")
        rec["alpha_abstain_as_category"] = {
            "metric": "nominal",
            **alpha_with_interval(coded(True), len(options) + 1, "nominal", resamples, rng)}
    return rec


@dataclass
class Analysis:
    agreement: dict[str, dict[str, Any]]
    items: list[dict[str, Any]]
    coverage: dict[str, Any]
    answer_changes: dict[str, dict[str, dict[str, int]]]
    reveal: dict[str, dict[str, Any]]
    combined_tier: dict[str, Any] | None
    notes: dict[str, Any]


def analyse(inp: Inputs, checked: Checked, included: set[str], seed: int, resamples: int) -> Analysis:
    questions, bundle = inp.questions, inp.bundle
    items = bundle["items"]
    keys_of = {i["item_id"]: item_keys(i, questions) for i in items}
    by_item: dict[str, list[Rating]] = {i["item_id"]: [] for i in items}
    for (rater, item_id), rating in sorted(checked.ratings.items()):
        if rater in included:
            by_item[item_id].append(rating)

    # ---- answer changes after the first answer, and after the reveal (every included rating, finished or not)
    answer_changes: dict[str, dict[str, dict[str, int]]] = {}
    reveal_block: dict[str, dict[str, Any]] = {}
    for item in items:
        set_name = item["question_set"]
        has_step = item.get("reveal") is not None
        for rating in by_item[item["item_id"]]:
            first = first_answers(rating)
            for k, spec in keys_of[item["item_id"]].items():
                if k not in first:
                    continue
                rec = answer_changes.setdefault(set_name, {}).setdefault(
                    k, {"first_given": 0, "changed_after_first": 0, "cleared_after_first": 0})
                rec["first_given"] += 1
                if k not in rating.current:
                    rec["cleared_after_first"] += 1
                elif canonical(rating.current[k]) != canonical(first[k]):
                    rec["changed_after_first"] += 1
            if has_step:
                blk = reveal_block.setdefault(set_name, {"ratings_with_reveal_step": 0, "ratings_revealed": 0,
                                                         "blind_changed_after_reveal": {},
                                                         "blind_first_given_after_reveal": {}})
                blk["ratings_with_reveal_step"] += 1
                if rating.reveal is None:
                    continue
                blk["ratings_revealed"] += 1
                for k, spec in keys_of[item["item_id"]].items():
                    if spec.question["phase"] != "blind":
                        continue
                    at_reveal, now = rating.reveal.get(k), rating.current.get(k)
                    if at_reveal is None and now is not None:
                        blk["blind_first_given_after_reveal"][k] = blk["blind_first_given_after_reveal"].get(k, 0) + 1
                    elif at_reveal is not None and canonical(at_reveal) != canonical(now):
                        blk["blind_changed_after_reveal"][k] = blk["blind_changed_after_reveal"].get(k, 0) + 1

    # ---- agreement per question set and question
    agreement: dict[str, dict[str, Any]] = {}
    for set_name, qset in questions["question_sets"].items():
        set_items = [i for i in items if i["question_set"] == set_name]
        if not set_items:
            continue
        block: dict[str, Any] = {}
        for q in qset["questions"]:
            if q.get("per_arm"):
                arms: list[str] = []
                for i in set_items:
                    arms.extend(a for a in item_arms(i) if a not in arms)
                labels = [(q["id"], None)] + [(f"{q['id']}.{a}", a) for a in arms]
            else:
                labels = [(q["id"], None)]
            for label, arm in labels:
                units: list[Unit] = []
                specs: dict[str, KeySpec] = {}
                for i in set_items:
                    for spec in keys_of[i["item_id"]].values():
                        if spec.question["id"] != q["id"] or (arm is not None and spec.arm != arm):
                            continue
                        specs[spec.key] = spec
                        values = [(r.rater, analysis_value(r, spec, i.get("reveal") is not None))
                                  for r in by_item[i["item_id"]] if r.complete]
                        units.append(Unit(i["item_id"], spec.arm, values))
                if specs:
                    block[label] = analyse_key(set_name, label, specs, units, seed, resamples)
        agreement[set_name] = block

    # ---- per item
    item_rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda i: i["item_id"]):
        iid = item["item_id"]
        has_step = item.get("reveal") is not None
        complete = [r for r in by_item[iid] if r.complete]
        row: dict[str, Any] = {
            "item_id": iid,
            "question_set": item["question_set"],
            "family": item["family"],
            "source_id": (item.get("provenance") or {}).get("source_id"),
            "ratings_complete": len(complete),
            "ratings_unfinished": len(by_item[iid]) - len(complete),
            "raters_complete": [r.rater for r in complete],
            "notes": sum(1 for r in by_item[iid] if r.notes),
            "text_answers": sum(1 for r in by_item[iid] for k, sp in keys_of[iid].items()
                                if sp.scale["type"] == "text" and k in r.current),
            "answers": {},
            "five_point": {},
            "flagged": False,
            "flagged_keys": [],
        }
        subset = (item.get("provenance") or {}).get("subset")
        if subset is not None:
            row["subset"] = subset
        for k, spec in keys_of[iid].items():
            vals = [analysis_value(r, spec, has_step) for r in complete]
            if spec.scale["type"] == "text":
                row["answers"][k] = {"text_answers": sum(1 for v in vals if v is not None)}
            elif spec.scale["type"] == "multi":
                row["answers"][k] = multi_counts(spec.scale, vals)
            else:
                row["answers"][k] = [d for d in distribution(spec.scale, vals) if d["n"]]
            if is_five_point(spec.scale):
                stats = five_point_stats(vals)
                row["five_point"][k] = stats
                if stats["majority_low"]:
                    row["flagged_keys"].append(k)
        row["flagged"] = bool(row["flagged_keys"])
        if has_step:
            row["ratings_revealed"] = sum(1 for r in by_item[iid] if r.reveal is not None)
        item_rows.append(row)

    # ---- coverage per question set and per family
    def cover(group: list[dict]) -> dict[str, Any]:
        rows = [r for r in item_rows if r["item_id"] in {i["item_id"] for i in group}]
        return {
            "items": len(rows),
            "items_with_a_complete_rating": sum(1 for r in rows if r["ratings_complete"] >= 1),
            "items_with_2_or_more_complete_ratings": sum(1 for r in rows if r["ratings_complete"] >= 2),
            "items_below_2_complete_ratings": [r["item_id"] for r in rows if r["ratings_complete"] < 2],
            "ratings_complete": sum(r["ratings_complete"] for r in rows),
            "ratings_unfinished": sum(r["ratings_unfinished"] for r in rows),
            "items_flagged": sum(1 for r in rows if r["flagged"]),
            "ratings_with_notes": sum(r["notes"] for r in rows),
        }

    sets = list(dict.fromkeys(i["question_set"] for i in items))
    families = list(dict.fromkeys(i["family"] for i in items))
    coverage = {
        "by_question_set": {s: cover([i for i in items if i["question_set"] == s]) for s in sets},
        "by_family": {f: cover([i for i in items if i["family"] == f]) for f in families},
    }
    notes = {
        "ratings_with_notes": sum(r["notes"] for r in item_rows),
        "text_answers": sum(r["text_answers"] for r in item_rows),
        "copied": 0,
        "counted_over": "every rating by an included physician, finished or not (the latest save's notes)",
        "rule": "Owner decision 11: note text and text answers are counted per item, never copied into anything "
                "committed, unless the owner has read them and listed which may be published",
    }
    combined = combined_tier(inp, keys_of, by_item)
    return Analysis(agreement, item_rows, coverage, answer_changes, reveal_block, combined, notes)


# ---- the combined (proposed) reference tier -----------------------------------------------------------------------

def tier_question(inp: Inputs, set_name: str) -> dict:
    """The set's locks_on_reveal question whose options are the rubric's tier ids, refusing ambiguity."""
    qs = inp.questions["question_sets"][set_name]["questions"]
    found = []
    for q in qs:
        if not q.get("locks_on_reveal"):
            continue
        values = option_values(inp.questions["scales"][q["scale"]])
        if sorted(map(canonical, values)) == sorted(map(canonical, inp.tier_order)):
            found.append(q)
            if [canonical(v) for v in values] != [canonical(t) for t in inp.tier_order]:
                refuse("tier_order_mismatch", f"question {set_name}.{q['id']}: its options are the rubric's tier ids "
                                              f"in another order than {inp.rubric_path.name} lists them")
    if len(found) != 1:
        refuse("tier_question_ambiguous", f"question set {set_name!r} has {len(found)} locks_on_reveal questions "
                                          "whose options are the rubric's tier ids; the combined tier needs one")
    return found[0]


def combine_tiers(answers: Sequence[str], tier_order: Sequence[str]) -> tuple[str | None, str | None, bool]:
    """Owner decision 9's default: (tier, reason when none, even split). Median on the tier order; an even number of
    answers whose two middle tiers differ gives the more urgent (later in the rubric's list); fewer than 2 answers
    gives no tier. Abstentions are removed by the caller."""
    ranks = sorted(tier_order.index(a) for a in answers)
    n = len(ranks)
    if n < 2:
        return None, f"fewer than 2 tier answers ({n})", False
    if n % 2:
        return tier_order[ranks[n // 2]], None, False
    lo, hi = ranks[n // 2 - 1], ranks[n // 2]
    return tier_order[max(lo, hi)], None, lo != hi


def combined_tier(inp: Inputs, keys_of: dict[str, dict[str, KeySpec]],
                  by_item: dict[str, list[Rating]]) -> dict[str, Any] | None:
    items = [i for i in inp.bundle["items"] if i.get("reveal") is not None]
    if not items:
        return None
    sets = sorted({i["question_set"] for i in items})
    if len(sets) != 1:
        refuse("tier_question_ambiguous", f"items with a proposed tier come from {len(sets)} question sets {sets}; "
                                          "the combined tier is defined for one")
    set_name = sets[0]
    q = tier_question(inp, set_name)
    scale = inp.questions["scales"][q["scale"]]
    rows = []
    per_rater: dict[str, dict[str, int]] = {}
    for item in sorted(items, key=lambda i: (str((i.get("provenance") or {}).get("source_id")), i["item_id"])):
        proposed = item["reveal"].get("proposed_tier")
        if proposed not in inp.tier_order:
            refuse("bad_bundle", f"item {item['item_id']}: proposed tier {proposed!r} is not a rubric tier id")
        spec = keys_of[item["item_id"]][q["id"]]
        votes: list[tuple[str, str]] = []
        abstained = 0
        for r in by_item[item["item_id"]]:
            if not r.complete:
                continue
            v = analysis_value(r, spec, True)
            if v is None:
                continue
            if is_abstain(scale, v):
                abstained += 1
                continue
            votes.append((r.rater, v))
            pr = per_rater.setdefault(r.rater, {"answers": 0, "agree_with_proposed": 0})
            pr["answers"] += 1
            pr["agree_with_proposed"] += int(v == proposed)
        tier, reason, split = combine_tiers([v for _r, v in votes], inp.tier_order)
        rows.append({
            "item_id": item["item_id"],
            "id": (item.get("provenance") or {}).get("source_id"),
            "proposed": proposed,
            "answers": len(votes),
            "abstentions": abstained,
            "raters": sorted(r for r, _v in votes),
            "distribution": [{"value": t, "n": sum(1 for _r, v in votes if v == t)} for t in inp.tier_order
                             if any(v == t for _r, v in votes)],
            "tier": tier,
            "no_tier_reason": reason,
            "even_split_to_more_urgent": split,
            "agrees_with_proposed": None if tier is None else tier == proposed,
            "direction_vs_proposed": None if tier is None else (
                "same" if tier == proposed else
                "more urgent" if inp.tier_order.index(tier) > inp.tier_order.index(proposed) else "less urgent"),
        })
    with_tier = [r for r in rows if r["tier"] is not None]
    return {
        "status": ADJUDICATION_STATUS,
        "question_set": set_name,
        "question": q["id"],
        "rule": "median of the complete ratings' blind answers on the rubric's tier order (rank = list position, "
                "least to most urgent); an even number of answers whose two middle tiers differ gives the more urgent "
                "of the two; abstentions left out; no tier from fewer than 2 answers (owner decision 9's default)",
        "tier_order": list(inp.tier_order),
        "summary": {
            "items": len(rows),
            "with_tier": len(with_tier),
            "without_tier": len(rows) - len(with_tier),
            "agree_with_proposed": sum(1 for r in with_tier if r["agrees_with_proposed"]),
            "more_urgent_than_proposed": sum(1 for r in with_tier if r["direction_vs_proposed"] == "more urgent"),
            "less_urgent_than_proposed": sum(1 for r in with_tier if r["direction_vs_proposed"] == "less urgent"),
            "even_splits": sum(1 for r in with_tier if r["even_split_to_more_urgent"]),
        },
        "per_rater_agreement_with_proposed": dict(sorted(per_rater.items())),
        "items": rows,
    }


def adjudication_doc(combined: dict[str, Any], inp: Inputs, summary_name: str, stamp: str) -> dict[str, Any]:
    """The proposed reference-tier file, in the shape advice_eval.py analyze --stimuli reads."""
    date = inp.export["exported_utc"][:10]
    items = []
    for r in combined["items"]:
        if r["tier"] is None:
            items.append({"id": r["id"], "item_id": r["item_id"], "reference": None,
                          "no_tier_reason": r["no_tier_reason"]})
            continue
        rule = "median, even split to the more urgent" if r["even_split_to_more_urgent"] else "median"
        items.append({"id": r["id"], "item_id": r["item_id"], "reference": {
            "tier": r["tier"],
            "adjudicated_by": "; ".join(r["raters"]) + f" ({rule})",
            "source": f"physician verification ratings, export {stamp}; {ADJUDICATION_STATUS}",
            "date": date,
        }})
    sources = sorted({(i.get("provenance") or {}).get("source_path") for i in inp.bundle["items"]
                      if i.get("reveal") is not None} - {None})
    return {
        "status": ADJUDICATION_STATUS,
        "rule": combined["rule"],
        "stimuli_files": sources,
        "derived_from": {"summary": summary_name, "export_sha256": inp.export_sha256,
                         "bundle_id": inp.bundle["bundle_id"], "bundle_sha256": inp.bundle_sha256},
        "coverage": {"items": combined["summary"]["items"], "with_tier": combined["summary"]["with_tier"],
                     "without_tier": [r["id"] for r in combined["items"] if r["tier"] is None]},
        "items": items,
    }


# ---- the summary --------------------------------------------------------------------------------------------------

def export_stamp(exported_utc: str) -> str:
    when = parse_utc(exported_utc, "exported_utc")
    return when.strftime("%Y%m%dT%H%M%SZ")


def build_summary(inp: Inputs, checked: Checked, args: argparse.Namespace) -> tuple[dict[str, Any], Analysis]:
    excluded = sorted(set(args.exclude_rater or []))
    known = {r["rater_id"] for r in checked.raters}
    for rid in excluded:
        if not RATER_ID_RE.match(rid) or rid not in known:
            refuse("unknown_excluded_rater", f"--exclude-rater {rid}: no such rater in the export ({sorted(known)})")
    included = known - set(excluded)
    analysis = analyse(inp, checked, included, args.seed, args.resamples)

    assigned = {(a["rater_id"], a["item_id"]) for a in checked.assignments if a["status"] == "assigned"}
    any_assignment = {(a["rater_id"], a["item_id"]) for a in checked.assignments}
    items_by_id = {i["item_id"]: i for i in inp.bundle["items"]}
    warnings: list[str] = []
    rater_rows = []
    for r in sorted(checked.raters, key=lambda x: x["rater_id"]):
        rid = r["rater_id"]
        mine = [x for (rr, _i), x in checked.ratings.items() if rr == rid]
        recomputed = sum(1 for x in mine if x.complete and (rid, x.item_id) in assigned)
        abstentions = answers = 0
        for x in mine:
            if not x.complete:
                continue
            item = items_by_id[x.item_id]
            for spec in item_keys(item, inp.questions).values():
                v = analysis_value(x, spec, item.get("reveal") is not None)
                if v is None or spec.scale["type"] in ("text", "multi"):
                    continue
                answers += 1
                abstentions += int(is_abstain(spec.scale, v))
        rater_rows.append({
            "rater_id": rid,
            "status": r["status"],
            "included": rid in included,
            "events": checked.events_by_rater[rid],
            "ratings_started": len(mine),
            "ratings_complete": sum(1 for x in mine if x.complete),
            "app_n_complete": r["n_complete"],
            "recomputed_n_complete_on_assigned_items": recomputed,
            "answers_in_complete_ratings": answers,
            "abstentions_in_complete_ratings": abstentions,
        })
        if recomputed != r["n_complete"]:
            warnings.append(f"{rid}: the app counts {r['n_complete']} complete ratings, the import recomputes "
                            f"{recomputed} from the questions")
        if r["status"] == "removed" and rid in included and mine:
            warnings.append(f"{rid} has status removed and {len(mine)} rating(s), which are included; if {rid} is "
                            f"the owner's dummy test account, rerun with --exclude-rater {rid}")
    orphans = sorted(f"{rid}/{iid}" for (rid, iid) in checked.ratings if (rid, iid) not in any_assignment)
    if orphans:
        warnings.append(f"{len(orphans)} rating(s) on items with no assignment row: {orphans}")
    if checked.saved_utc_regressions:
        warnings.append(f"{checked.saved_utc_regressions} event(s) carry an earlier saved_utc than the event before "
                        "them; the import follows the log's order, as the app does")
    ex_ratings = [x for (rid, _i), x in checked.ratings.items() if rid in excluded]
    stamp = export_stamp(inp.export["exported_utc"])
    export = inp.export
    summary: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "status": "Draft analysis of physician verification ratings; question wording "
                  f"{inp.questions.get('version')!r} ({inp.questions.get('status')})",
        "script": {"path": "scripts/import_verification_ratings.py", "version": SCRIPT_VERSION,
                   "sha256": sha256_bytes(Path(__file__).read_bytes())},
        "inputs": {
            "export": {"file": logical_path(inp.export_path), "sha256": inp.export_sha256,
                       "schema": export["schema"], "exported_utc": export["exported_utc"],
                       "stamp": stamp, "app_version": export["app_version"], "settings": export["settings"]},
            "bundle": {"path": logical_path(inp.bundle_path), "sha256": inp.bundle_sha256,
                       "bundle_id": inp.bundle["bundle_id"]},
            "questions": {"path": logical_path(inp.questions_path), "sha256": inp.questions_sha256,
                          "version": inp.questions.get("version")},
            "rubric": {"path": logical_path(inp.rubric_path), "sha256": inp.rubric_sha256,
                       "tier_order": inp.tier_order},
        },
        "seed": args.seed,
        "seed_is_default": args.seed == DEFAULT_SEED,
        "resamples": args.resamples,
        "ci_level": CI_LEVEL,
        "method": {
            "events": "taken in the export's order (the Ratings tab's append order); current answers = the latest "
                      "save; first answers = each key's earliest saved value; blind answers of an item with a reveal "
                      "step = the reveal event's answers (owner decision 18, as built)",
            "population": "complete ratings by included physicians only: distributions, agreement and the combined "
                          "tier; unfinished ratings are counted",
            "alpha": "Krippendorff's alpha from the coincidence matrix (Krippendorff 2011): alpha = 1 - (n - 1) "
                     "sum o_ck d2_ck / sum n_c n_k d2_ck; nominal d2 = [c != k]; ordinal d2_ck = (sum_{g=c..k} n_g - "
                     "(n_c + n_k) / 2)^2; metric = the scale's type; units with fewer than 2 answers are not pairable",
            "abstentions": "missing in the primary analysis; one more category in the nominal sensitivity analysis "
                           "(owner decision 10's default)",
            "interval": "percentile bootstrap over pairable units with replacement; random.Random seeded by the "
                        "string '<seed>|<question set>|<key>|<variant>'; undefined resamples counted and left out; "
                        "no interval when fewer than half are defined; percentiles interpolated linearly at "
                        "q * (B - 1)",
            "pairwise_agreement": "share of equal pairs of non-abstaining answers on the same unit (ordinal: and "
                                  "within one category); every pair counts once",
            "five_point": f"numeric five-point ordinal scales: median, and the share at <= {LOW_MAX}; an item is "
                          "flagged when more than half of its non-abstaining answers are <= "
                          f"{LOW_MAX} (unrealistic or implausible)",
        },
        "raters": rater_rows,
        "exclusions": {
            "excluded_raters": excluded,
            "rule": "Physicians named with --exclude-rater (the owner's dummy test account, a wording-pilot "
                    "physician) are left out; every other physician is included, a removed one with a warning",
            "events": sum(checked.events_by_rater[r] for r in excluded),
            "ratings": len(ex_ratings),
            "ratings_complete": sum(1 for x in ex_ratings if x.complete),
        },
        "warnings": warnings,
        "events": {"total": len(export["events"]), "save": checked.event_counts["save"],
                   "reveal": checked.event_counts["reveal"],
                   "saved_utc_regressions": checked.saved_utc_regressions,
                   "ratings_without_assignment": len(orphans)},
        "coverage": analysis.coverage,
        "answer_changes": analysis.answer_changes,
        "reveal": analysis.reveal,
        "agreement": analysis.agreement,
        "combined_tier": analysis.combined_tier,
        "notes": analysis.notes,
        "items": analysis.items,
    }
    return summary, analysis


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(summary: dict[str, Any]) -> str:
    """A reader's view of the summary: ids, codes and numbers only."""
    inp = summary["inputs"]
    lines = [
        f"# Physician verification ratings: {inp['bundle']['bundle_id']}, export {inp['export']['stamp']}",
        "",
        f"Written by `scripts/import_verification_ratings.py` {summary['script']['version']} "
        f"(sha256 `{summary['script']['sha256'][:16]}`). {summary['status']}.",
        "",
        "## Inputs",
        "",
        "| Input | File | sha256 |",
        "|---|---|---|",
        f"| App export ({inp['export']['app_version']}, exported {inp['export']['exported_utc']}) | "
        f"`{inp['export']['file']}` | `{inp['export']['sha256']}` |",
        f"| Task bundle | `{inp['bundle']['path']}` | `{inp['bundle']['sha256']}` |",
        f"| Questions (version {inp['questions']['version']}) | `{inp['questions']['path']}` | "
        f"`{inp['questions']['sha256']}` |",
        f"| Tier order | `{inp['rubric']['path']}` | `{inp['rubric']['sha256']}` |",
        "",
        f"Seed {summary['seed']} ({'the default' if summary['seed_is_default'] else 'set with --seed'}), "
        f"{summary['resamples']} bootstrap resamples, {int(summary['ci_level'] * 100)}% percentile intervals.",
        "",
        "## Physicians",
        "",
        "| Rater | Status | Included | Events | Ratings started | Complete | App's count | Abstentions |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["raters"]:
        lines.append(f"| {r['rater_id']} | {r['status']} | {'yes' if r['included'] else 'no'} | {r['events']} | "
                     f"{r['ratings_started']} | {r['ratings_complete']} | {r['app_n_complete']} | "
                     f"{r['abstentions_in_complete_ratings']} of {r['answers_in_complete_ratings']} |")
    ex = summary["exclusions"]
    lines += ["", f"Excluded: {', '.join(ex['excluded_raters']) or 'none'} ({ex['events']} events, "
                  f"{ex['ratings']} ratings). {ex['rule']}.", ""]
    lines += ["## Warnings", ""]
    lines += [f"- {w}" for w in summary["warnings"]] or ["None."]
    lines += ["", "## Coverage", "",
              "| Question set | Items | With a complete rating | With 2 or more | Complete ratings | Unfinished | "
              "Flagged items | Ratings with notes |",
              "|---|---|---|---|---|---|---|---|"]
    for s, c in summary["coverage"]["by_question_set"].items():
        lines.append(f"| {s} | {c['items']} | {c['items_with_a_complete_rating']} | "
                     f"{c['items_with_2_or_more_complete_ratings']} | {c['ratings_complete']} | "
                     f"{c['ratings_unfinished']} | {c['items_flagged']} | {c['ratings_with_notes']} |")
    lines += ["", "## Agreement between physicians", "",
              "Krippendorff's alpha over complete ratings, abstentions missing; the last column counts them as one "
              "more category (nominal questions). Conventional thresholds: at least 0.800 reliable, at least 0.667 "
              "tentative. Few units give wide intervals; a coefficient on fewer than about ten units should not "
              "carry a claim.", "",
              "| Question set | Question | Metric | Pairable units | Answers | Abstentions | Alpha | 95% interval | "
              "Exact agreement | Alpha, abstain as category |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for s, block in summary["agreement"].items():
        for label, rec in block.items():
            a = rec.get("alpha")
            if a is None:
                lines.append(f"| {s} | {label} | {rec['scale_type']} | - | {rec['answers']} | {rec['abstentions']} "
                             f"| - | - | - | - |")
                continue
            ci = f"{a['ci95'][0]:.3f} to {a['ci95'][1]:.3f}" if a["ci95"] else "none"
            value = fmt(a["value"]) if a["value"] is not None else "undefined"
            sens = rec.get("alpha_abstain_as_category")
            lines.append(f"| {s} | {label} | {a['metric']} | {a['pairable_units']} | {rec['answers']} | "
                         f"{rec['abstentions']} | {value} | {ci} | {fmt(rec['pairwise_agreement']['exact'])} | "
                         f"{fmt(sens['value']) if sens else '-'} |")
    flagged = [r for r in summary["items"] if r["flagged"]]
    lines += ["", "## Items flagged unrealistic or implausible", "",
              f"More than half of an item's non-abstaining physicians answered {LOW_MAX} or lower on a five-point "
              "realism or plausibility question.", ""]
    if flagged:
        lines += ["| Item | Source | Question set | Questions | Complete ratings |", "|---|---|---|---|---|"]
        for r in flagged:
            lines.append(f"| {r['item_id']} | {r['source_id']} | {r['question_set']} | "
                         f"{', '.join(r['flagged_keys'])} | {r['ratings_complete']} |")
    else:
        lines.append("None.")
    ct = summary["combined_tier"]
    if ct:
        sm = ct["summary"]
        lines += ["", "## Combined urgency tier (proposed)", "", f"**{ct['status']}.** Rule: {ct['rule']}.", "",
                  f"{sm['with_tier']} of {sm['items']} items have a combined tier; it equals the proposed tier on "
                  f"{sm['agree_with_proposed']}, is more urgent on {sm['more_urgent_than_proposed']} and less urgent "
                  f"on {sm['less_urgent_than_proposed']}; {sm['even_splits']} came from an even split.", "",
                  "| Item | Stimulus id | Answers | Combined tier | Proposed tier | Reason for no tier |",
                  "|---|---|---|---|---|---|"]
        for r in ct["items"]:
            lines.append(f"| {r['item_id']} | {r['id']} | {r['answers']} | {r['tier'] or '-'} | {r['proposed']} | "
                         f"{r['no_tier_reason'] or ''} |")
    lines += ["", "## Answers changed", "", "Over every rating by an included physician, finished or not.", "",
              "| Question set | Question | First given | Changed later | Cleared later |", "|---|---|---|---|---|"]
    for s, block in summary["answer_changes"].items():
        for k, c in block.items():
            lines.append(f"| {s} | {k} | {c['first_given']} | {c['changed_after_first']} | "
                         f"{c['cleared_after_first']} |")
    for s, blk in summary["reveal"].items():
        lines += ["", f"After the reveal ({s}): {blk['ratings_revealed']} of {blk['ratings_with_reveal_step']} ratings "
                      "revealed. Blind answers changed after the reveal: "
                      f"{json.dumps(blk['blind_changed_after_reveal'], sort_keys=True)}; first given after it: "
                      f"{json.dumps(blk['blind_first_given_after_reveal'], sort_keys=True)}. The analysis uses the "
                      "answers as of the reveal."]
    nt = summary["notes"]
    lines += ["", "## Notes", "", f"{nt['ratings_with_notes']} ratings carry notes and {nt['text_answers']} carry a "
                                  f"text answer; none is copied here. {nt['rule']}.", ""]
    return "\n".join(lines)


# ---- writing ------------------------------------------------------------------------------------------------------

def serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def plan_write(path: Path, text: str, overwrite: bool) -> bool:
    """True when the file must be written; refuses an existing file with other content unless --overwrite."""
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return False
        if not overwrite:
            refuse("output_exists", f"{path} exists with other content; outputs are not replaced silently (pass "
                                    "--overwrite to replace it)")
    return True


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ratings_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--export", required=True, help="the app's export_<stamp>.json (keep it outside the repository)")
    ap.add_argument("--bundle", default=None, help="the task bundle (default: found under data/verification by the "
                                                   "export's bundle_sha256)")
    ap.add_argument("--verification-dir", default=str(DEFAULTS["verification_dir"]))
    ap.add_argument("--questions", default=str(DEFAULTS["questions"]))
    ap.add_argument("--rubric", default=str(DEFAULTS["rubric"]), help="the advice rubric whose tier list gives the "
                                                                     "tier order")
    ap.add_argument("--exclude-rater", action="append", default=[], metavar="RATER_ID",
                    help="a rater code to leave out (the dummy test account, a pilot physician); repeatable")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="bootstrap seed, recorded in the output")
    ap.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES, help="bootstrap resamples, recorded")
    ap.add_argument("--out-dir", default=str(DEFAULTS["out_dir"]))
    ap.add_argument("--write-proposed-adjudication", action="store_true",
                    help="also write the proposed combined-tier file (not in force until a pre-registration "
                         "amendment records the rule)")
    ap.add_argument("--overwrite", action="store_true", help="replace existing outputs with other content")
    args = ap.parse_args(argv)
    if args.resamples < 1:
        refuse("bad_argument", "--resamples must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    inp = load_inputs(args)
    checked = check_export(inp)
    summary, analysis = build_summary(inp, checked, args)
    stamp = summary["inputs"]["export"]["stamp"]
    base = f"ratings_{inp.bundle['bundle_id']}_{stamp}"
    out_dir = Path(args.out_dir)
    outputs = [(out_dir / f"{base}.summary.json", serialize(summary)),
               (out_dir / f"{base}.summary.md", render_markdown(summary))]
    if args.write_proposed_adjudication:
        if analysis.combined_tier is None:
            refuse("nothing_to_adjudicate", "no item in the bundle carries a proposed tier")
        outputs.append((out_dir / f"{base}.proposed_adjudication.json",
                        serialize(adjudication_doc(analysis.combined_tier, inp, f"{base}.summary.json", stamp))))
    to_write = [(p, t) for p, t in outputs if plan_write(p, t, args.overwrite)]
    for path, text in to_write:
        write_text(path, text)
    print(json.dumps({"written": [logical_path(p) for p, _t in to_write],
                      "unchanged": [logical_path(p) for p, _t in outputs if (p, _t) not in to_write],
                      "seed": args.seed, "resamples": args.resamples,
                      "excluded_raters": summary["exclusions"]["excluded_raters"],
                      "warnings": summary["warnings"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
