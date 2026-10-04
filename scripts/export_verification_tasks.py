"""Physician verification task bundle: the scenarios physicians rate in the private verification app.

Writes ``data/verification/tasks_<UTC stamp>.json`` (schema ``patientwords-verification-tasks/1``), the one file the
owner uploads to Google Drive for the app in the private repository michaeldgreenphd/patientwords-verify. The app
shows each physician only an item's ``display`` and its questions; ``reveal`` only after that physician's own blind
answers are saved; never ``provenance`` or any bundle metadata. docs/verification_protocol.md is the plain-language
protocol.

Three families, every item from a committed engine file or the published site payload:

* ``tracing_pair`` (question set ``tracing_pair``; display kind ``pair_sentence``):
  - pilot Run 2's 40 traced pairs (``pilot/runs/pilot_v2_20261002/trace/trace_pairs.json``), joined to the run's
    generated rows (template, terms, next word) and to their trace results in ``pilot/traces/trace_pairs/``;
  - the ``--main-pairs`` (default 40) main-study pairs already published in the site payload
    (``<site>/data/simulated_scenarios.json``) whose ``--rank-model`` (default gemma-2-2b) language penalty is
    largest in absolute value, compared at ``RANK_DECIMALS`` decimals so that penalties equal at their recorded
    precision tie and the stated tie rule (batch, then index) decides between them. A row without a measured
    penalty, a row the seal allowlist names as containing a
    sealed phrase, a row traced with a screening probe extension (the traced sentence is not the generated one) and
    a repeat of a higher-ranked prompt pair are excluded and counted. The ranking is a way to pick pairs worth a
    physician's look, not a measurement: AGENTS.md's known limitations say no claim may rest on one pair's penalty.
  The highlight on each sentence is the shortest span where the two sentences differ, widened to whole words, so
  "they differ only in the highlighted words" is true by construction. Offsets are JavaScript string indices
  (UTF-16 code units), end exclusive.
* ``advice`` (display kind ``message_pair``): the 24 new questions (``data/advice/stimuli_20261002T080026Z.json``,
  question set ``advice_new``, ``reveal`` = the proposed reference tier) and the 15 rerun items
  (``data/advice/stimuli_20261002T081803Z.json``): ``advice_rerun_truncated`` for an item whose source stimuli file
  was built from the payload's cut-off sentences and that was not completed with its target word, ``advice_rerun``
  otherwise. Both messages are shown exactly as sent (each must still hash to its recorded sha256). The probe file
  ``data/advice/stimuli_20261002T074159Z.json`` is not an input: its one item repeats item #01.
* ``multiturn`` (question set ``multiturn_script``; display kind ``script``): one item per Petri wave-3 seed
  (``docs/framework/petri_seeds_w3.draft.json``) with its arms' scripted user turns, each turn text checked against
  its recorded sha256. ``same_as`` names the first earlier arm whose turn is word for word the same. Model replies
  are never included; the seed file holds none.

Display fields carry only the texts a physician rates, the highlight spans and the expected next word: no measured
number, model name, batch id, rationale, topic, checker verdict or proposed tier. The script display's ``arm`` ids
are the one exception the contract makes: the app replaces them with "Version A/B/C" per physician before sending
an item. ``provenance`` keeps source path, source id and sha256s; the app never sends it to a physician.

Holdout seal, failing closed. Every tracing and advice row is checked with ``tierb_split.sealed_pair`` (for an advice
or payload row naming a non-Tier-B batch whose file exists, the batch's accepted prompt as well, the pattern of
``advice_eval._selection_seal_check``); every rater-visible string, and then the whole serialized bundle, is swept
with ``seal_check``'s matcher against the sealed registry, with no allowlist. A sealed row anywhere in the published
payload, a sealed row or text in the bundle, or a seal that cannot be evaluated refuses the export. Messages name
item ids, batch#index labels and paths only, never text. The bundle's ``seal`` block also lists the items whose
clinical text hashes into the holdout bucket (``tierb_split.is_holdout``) without being sealed: Amendment 3 would
seal such a text everywhere once a later Tier B batch accepted it. A bundle is therefore re-checked after export:
``scripts/seal_check.py``'s default roots include ``data/verification``, so the daily sweep covers every committed
bundle, and the same command runs before each upload to the app.

Determinism: the item set and every item are a pure function of the inputs; the item order is the items sorted by
item_id and then shuffled with ``random.Random(seed)``. The same inputs, ``--seed`` and ``--stamp`` give a
byte-identical file; a different seed gives the same items in another order. The seed is recorded in the bundle.
``item_id`` is ``"vt_"`` plus the first 12 hex digits of sha256(family U+001F source path U+001F source id), so an
item keeps its id across bundles while its source keeps its path and id.

Refusals (a named SystemExit, and nothing is written): a missing or unreadable input, a field the exporter does not
know in a record it reads (a new field may carry meaning the selection must respect, so a person decides), a shape
it cannot use, a text whose sha256 no longer matches, a questions file that does not fit the items, fewer
main-study candidates than requested, an item id collision, an existing output file (a bundle is an archive, never
rewritten), and every seal failure above.

Usage (from the engine root):
  python scripts/export_verification_tasks.py [--site ../patientwords] [--seed 20261003] [--main-pairs 40]
      [--stamp 20261003T120000Z] [--out-dir data/verification]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

if not __package__:
    # Run as a file path (or loaded by path in tests): put THIS checkout's root first, so `scripts.*` resolves to
    # this checkout even when an editable install's .pth file puts another engine checkout on sys.path
    # (export_petri_multiturn.py has the same guard and the reason in full).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import seal_check  # noqa: E402
from scripts import tierb_split  # noqa: E402
from scripts.petri_audit.seeds import seed_digest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEMA = "patientwords-verification-tasks/1"
QUESTIONS_SCHEMA = "patientwords-verification-questions/1"
DEFAULT_SEED = 20261003
DEFAULT_MAIN_PAIRS = 40
DEFAULT_RANK_MODEL = "gemma-2-2b"
# Main-study pairs are ranked on |language penalty| rounded to this many decimals. The payload's penalties are
# differences of probabilities recorded to three decimals, so they carry binary floating-point noise (0.531 - 0.104
# is 0.42700000000000005, 0.859 - 0.432 is 0.427); six decimals is finer than the recorded precision and far coarser
# than that noise, so two penalties equal as recorded tie and the tie rule (batch, then index) decides.
RANK_DECIMALS = 6
MULTITURN_WAVE = 3
SITE_PAYLOAD = "data/simulated_scenarios.json"
SITE_LABEL = "patientwords:" + SITE_PAYLOAD
BLANK = "___"

DEFAULTS = {
    "questions": REPO_ROOT / "data" / "verification" / "questions.json",
    "pilot_run": REPO_ROOT / "pilot" / "runs" / "pilot_v2_20261002",
    "pilot_traces": REPO_ROOT / "pilot" / "traces" / "trace_pairs",
    "advice_new": REPO_ROOT / "data" / "advice" / "stimuli_20261002T080026Z.json",
    "advice_rerun": REPO_ROOT / "data" / "advice" / "stimuli_20261002T081803Z.json",
    "petri_seeds": REPO_ROOT / "docs" / "framework" / "petri_seeds_w3.draft.json",
    "dashboard": REPO_ROOT / "ops" / "dashboard.json",
    "simulated": REPO_ROOT / "data" / "simulated",
    "allowlist": REPO_ROOT / "data" / "seal_allowlist.json",
    "out_dir": REPO_ROOT / "data" / "verification",
    "site": REPO_ROOT.parent / "patientwords",
}
EXCLUDED_ADVICE_FILES = [{"path": "data/advice/stimuli_20261002T074159Z.json",
                          "reason": "probe archive; its one item repeats advman_20261002#01 and is never judged"}]

FAMILIES = ("tracing_pair", "advice", "multiturn")
QUESTION_SETS = {"tracing_pair": "tracing_pair", "advice_new": "advice", "advice_rerun": "advice",
                 "advice_rerun_truncated": "advice", "multiturn_script": "multiturn"}

# ---- the fields of every record the exporter reads (anything else is refused as unknown) ----------------------
TRACE_PAIR_KEYS = frozenset({"top_prompt", "bottom_prompt", "target_clinical_token", "pilot"})
TRACE_PILOT_KEYS = frozenset({"run", "row_id", "review_id", "call_id", "arm", "cell", "control", "concept_key",
                              "probe_point", "checker", "prompt_sha256"})
TRACE_META_KEYS = frozenset({"run", "harness_version", "selection", "counts", "inputs_sha256", "use", "output"})
PILOT_ROW_KEYS = frozenset({"id", "call_id", "arm", "specialty", "swap_type", "cell", "cell_index", "line_index",
                            "attempt", "clinical_term", "patient_term", "template", "next_word", "control",
                            "control_faithful", "prompt_sha256"})
PAYLOAD_SCENARIO_KEYS = frozenset({
    "index", "batch", "batch_index", "clinical_prompt", "patient_prompt", "intended_target", "rationale",
    "patient_term", "clinical_term", "topic", "topics", "models", "prob_clinical", "prob_patient",
    "language_penalty", "flipped", "top_clinical", "top_patient", "spread_clinical", "spread_patient",
    "target_token", "anchor_fallback", "screening", "circuit_diff", "clinical_mass", "trace_url", "urgency",
    "html", "png", "depth_class", "steered"})
ADVICE_FILE_KEYS = frozenset({"created_utc", "engine_sha", "source", "ask_suffix", "n_items", "items"})
ADVICE_ITEM_KEYS = frozenset({"id", "source_ref", "clinical_body", "patient_body", "clinical_message",
                              "patient_message", "clinical_sha256", "patient_sha256", "meta", "reference"})
ADVICE_NEW_SOURCE_KEYS = frozenset({"kind", "path"})
ADVICE_NEW_META_KEYS = frozenset({"notes"})
ADVICE_NOTES_KEYS = frozenset({"family", "syntax_style", "clinical_span", "patient_span", "relation",
                               "clinical_span_status", "lexicon_basis", "lexicon_basis_status", "lexicon_conflict",
                               "lexicon_sources", "body_system", "speaker", "tier_rationale", "author",
                               "revision_note"})
ADVICE_REFERENCE_KEYS = frozenset({"tier", "basis"})
ADVICE_RERUN_SOURCE_KEYS = frozenset({"kind", "path", "sha256", "rule", "notes", "files", "ask_suffixes",
                                      "file_sources", "renamed_ids", "shared_source_pairs", "seal_items_checked",
                                      "tierb_items_checked", "accepted_prompt_items_checked", "tierb_start_stamp"})
ADVICE_RERUN_META_KEYS = frozenset({"rerun_of", "language_penalty", "flipped", "topic", "completed_with",
                                    "completion_override"})
RERUN_OF_KEYS = frozenset({"file", "id", "file_sha256", "prior"})
SEED_FILE_KEYS = frozenset({"schema_version", "status", "_readme", "seed_schema", "seeds"})
SEED_KEYS = frozenset({"schema_version", "seed_id", "mode", "claim_grade_eligible", "hypotheses", "pilot_wave",
                       "framing", "speaker_identity", "scenario", "texts", "system_prompt", "tools", "protocol",
                       "auditor_instruction", "generation", "judge", "status", "notes"})
PROTOCOL_KEYS = frozenset({"arms", "register_exposure", "branch_anchor", "branches", "max_target_turns"})
ARM_KEYS = frozenset({"id", "user_is", "turns"})
TURN_KEYS = frozenset({"role", "text_ref", "context_role"})
TEXT_KEYS = frozenset({"key", "text", "sha256", "register", "authored_by"})
QUESTIONS_KEYS = frozenset({"schema", "version", "status", "_readme", "scales", "question_sets", "notes",
                            "instructions"})
QUESTION_SET_KEYS = frozenset({"family", "applies_to", "questions"})
QUESTION_KEYS = frozenset({"id", "scale", "required", "phase", "per_arm", "locks_on_reveal", "text", "hint",
                           "measures"})
SCALE_KEYS = frozenset({"type", "options", "abstain", "max_length"})
OPTION_KEYS = frozenset({"value", "label", "definition"})
SCALE_TYPES = frozenset({"ordinal", "nominal", "multi", "text"})
PHASES = frozenset({"blind", "after_reveal"})

_STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$")


# ---- refusals and small helpers ------------------------------------------------------------------------------

def refuse(code: str, message: str) -> NoReturn:
    """Stop the export with a named refusal. Messages carry ids, labels and paths, never row text."""
    raise SystemExit(f"export_verification_tasks: REFUSED [{code}] {message}; nothing was written")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def item_id_for(family: str, source_path: str, source_id: str) -> str:
    """The stable item id: "vt_" + 12 hex digits of sha256(family U+001F source path U+001F source id)."""
    return "vt_" + sha256_text("\x1f".join((family, source_path, source_id)))[:12]


def logical_path(path: Path) -> str:
    """A path as the bundle records it: repository-relative inside this checkout, else as resolved."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


class Inputs:
    """Reads each input once, keeps its bytes' sha256 for the bundle's ``sources`` list."""

    def __init__(self) -> None:
        self.sources: list[dict[str, str]] = []

    def read_bytes(self, path: Path, role: str, label: str | None = None) -> bytes:
        if not path.is_file():
            refuse("missing_input", f"{role}: {path} does not exist or is not a file")
        try:
            data = path.read_bytes()
        except OSError as exc:
            refuse("unreadable_input", f"{role}: cannot read {path} ({type(exc).__name__})")
        self.sources.append({"path": label or logical_path(path), "role": role, "sha256": sha256_bytes(data)})
        return data

    def read_json(self, path: Path, role: str, label: str | None = None) -> tuple[Any, str]:
        data = self.read_bytes(path, role, label)
        try:
            return json.loads(data.decode("utf-8")), sha256_bytes(data)
        except (UnicodeDecodeError, ValueError) as exc:
            refuse("unreadable_input", f"{role}: {path} is not UTF-8 JSON ({type(exc).__name__})")

    def read_jsonl(self, path: Path, role: str) -> tuple[list[dict], str]:
        data = self.read_bytes(path, role)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            refuse("unreadable_input", f"{role}: {path} is not UTF-8")
        rows: list[dict] = []
        for n, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                refuse("unreadable_input", f"{role}: {path} line {n} is not JSON")
            if not isinstance(obj, dict):
                refuse("bad_input", f"{role}: {path} line {n} is not a JSON object")
            rows.append(obj)
        return rows, sha256_bytes(data)


def check_keys(obj: Any, allowed: frozenset[str], where: str, required: tuple[str, ...] = ()) -> dict:
    """The object, after refusing a non-object, an unknown key or a missing required key (names only)."""
    if not isinstance(obj, dict):
        refuse("bad_input", f"{where} is not a JSON object")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        refuse("unknown_field", f"{where} carries field(s) the exporter does not know: {unknown}. Decide whether a "
                                "rater may see each one and whether it changes the selection, then add it to the "
                                "exporter's known fields")
    missing = [k for k in required if k not in obj]
    if missing:
        refuse("bad_input", f"{where} lacks required field(s) {missing}")
    return obj


def need_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        refuse("bad_input", f"{where} is not a non-empty string")
    return value


def utf16_index(text: str, index: int) -> int:
    """A Python string index as a JavaScript one (UTF-16 code units), which is what the app slices with."""
    return len(text[:index].encode("utf-16-le")) // 2


def _word_char(ch: str) -> bool:
    return ch.isalnum() or ch in "'’-"


def diff_spans(a: str, b: str) -> tuple[list[int] | None, list[int] | None]:
    """The shortest span where a and b differ (common prefix and suffix removed), widened to whole words on each
    side, as [start, end) in UTF-16 code units; (None, None) for identical texts, and None for a side whose span
    is empty after widening (a pure insertion that touches no word)."""
    if a == b:
        return None, None
    p = 0
    limit = min(len(a), len(b))
    while p < limit and a[p] == b[p]:
        p += 1
    q = 0
    while q < limit - p and a[len(a) - 1 - q] == b[len(b) - 1 - q]:
        q += 1

    def widen(text: str, start: int, end: int) -> list[int] | None:
        while start > 0 and _word_char(text[start - 1]):
            start -= 1
        while end < len(text) and _word_char(text[end]):
            end += 1
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return [utf16_index(text, start), utf16_index(text, end)] if end > start else None

    return widen(a, p, len(a) - q), widen(b, p, len(b) - q)


def strings_in(obj: Any) -> list[str]:
    """Every string value in a JSON value (keys excluded), depth first."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in strings_in(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in strings_in(v)]
    return []


# ---- seal ----------------------------------------------------------------------------------------------------

class Seal:
    """The study's holdout seal, failing closed: tierb_split.sealed_pair per row and seal_check's matcher over text."""

    def __init__(self, dashboard: Path, simulated: Path) -> None:
        self.dashboard = dashboard
        self.simulated = simulated
        self.start = tierb_split.tierb_start_stamp(str(dashboard))
        self.registry = seal_check.sealed_registry(str(simulated), str(dashboard))
        if not self.start or not self.registry:
            refuse("seal_config", f"the sealed set computed empty from {dashboard} and {simulated} (no "
                                  "tierb.start_utc, or no Tier B batch files); the holdout rule cannot be applied")
        self.rows_checked: Counter = Counter()
        self.accepted_checked = 0
        self.texts_scanned = 0
        self.bucket_items: list[str] = []

    def row_sealed(self, family: str, batch: str | None, index: int | None, clinical: str | None,
                   label: str) -> bool:
        """sealed_pair for one row; for a non-Tier-B batch whose file exists, its accepted prompt as well."""
        try:
            sealed = tierb_split.sealed_pair(batch, index, clinical, dashboard_path=self.dashboard,
                                             simulated_dir=self.simulated)
            if (not sealed and batch and not tierb_split.is_tierb_batch(batch, self.start)
                    and (self.simulated / f"{batch}.json").is_file()):
                sealed = tierb_split.sealed_pair(batch, index, None, dashboard_path=self.dashboard,
                                                 simulated_dir=self.simulated)
                self.accepted_checked += 1
        except tierb_split.SealError as exc:
            refuse("seal_config", f"{label}: the holdout seal cannot be applied ({exc})")
        self.rows_checked[family] += 1
        return sealed

    def note_bucket(self, item_id: str, clinical: str) -> None:
        """Record an unsealed item whose clinical text hashes into the holdout bucket (``tierb_split.is_holdout``).
        It is not sealed today, but Amendment 3 would seal it everywhere once a later Tier B batch accepted the same
        prompt, so the bundle lists it and the recurring seal sweep covers data/verification."""
        if tierb_split.is_holdout(clinical):
            self.bucket_items.append(item_id)

    def scan(self, text: str, suffix: str = "") -> list[str]:
        """Sealed labels found in a text (seal_check's normalized, decoded match; no allowlist)."""
        self.texts_scanned += 1
        hits, _ = seal_check.scan_text(text, self.registry, None, suffix)
        return hits


# ---- questions -----------------------------------------------------------------------------------------------

def validate_questions(doc: Any, where: str) -> dict:
    """Refuse a questions document the app could not render or the items could not use (names only)."""
    check_keys(doc, QUESTIONS_KEYS, where, ("schema", "scales", "question_sets", "notes", "instructions"))
    if doc["schema"] != QUESTIONS_SCHEMA:
        refuse("questions_mismatch", f"{where}: schema is {doc['schema']!r}, expected {QUESTIONS_SCHEMA!r}")
    scales = doc["scales"]
    if not isinstance(scales, dict) or not scales:
        refuse("questions_mismatch", f"{where}: scales is not a non-empty object")
    for name, scale in scales.items():
        check_keys(scale, SCALE_KEYS, f"{where} scale {name!r}", ("type", "abstain"))
        if scale["type"] not in SCALE_TYPES:
            refuse("questions_mismatch", f"{where} scale {name!r}: type {scale['type']!r}")
        options = scale.get("options", [])
        if not isinstance(options, list) or (scale["type"] != "text" and not options):
            refuse("questions_mismatch", f"{where} scale {name!r}: options is not a non-empty list")
        values = []
        for n, opt in enumerate(options, 1):
            check_keys(opt, OPTION_KEYS, f"{where} scale {name!r} option {n}", ("value", "label"))
            values.append(opt["value"])
        abstain = scale["abstain"]
        if abstain is not None:
            check_keys(abstain, frozenset({"value", "label"}), f"{where} scale {name!r} abstain", ("value", "label"))
            values.append(abstain["value"])
        if len(set(map(canonical, values))) != len(values):
            refuse("questions_mismatch", f"{where} scale {name!r}: an answer value is listed twice")
        if scale["type"] == "text" and not (isinstance(scale.get("max_length"), int) and scale["max_length"] > 0):
            refuse("questions_mismatch", f"{where} scale {name!r}: a text scale needs a positive max_length")
    sets = doc["question_sets"]
    if not isinstance(sets, dict):
        refuse("questions_mismatch", f"{where}: question_sets is not an object")
    for set_name, family in QUESTION_SETS.items():
        if set_name not in sets:
            refuse("questions_mismatch", f"{where}: question set {set_name!r} is missing")
        qset = check_keys(sets[set_name], QUESTION_SET_KEYS, f"{where} question set {set_name!r}",
                          ("family", "questions"))
        if qset["family"] != family:
            refuse("questions_mismatch", f"{where} question set {set_name!r}: family {qset['family']!r}, the "
                                         f"exporter uses it for {family!r}")
        questions = qset["questions"]
        if not isinstance(questions, list) or not questions:
            refuse("questions_mismatch", f"{where} question set {set_name!r} has no questions")
        ids = []
        for q in questions:
            check_keys(q, QUESTION_KEYS, f"{where} question set {set_name!r} question",
                       ("id", "scale", "required", "phase", "text"))
            ids.append(q["id"])
            if q["scale"] not in scales:
                refuse("questions_mismatch", f"{where} {set_name}.{q['id']}: unknown scale {q['scale']!r}")
            if q["phase"] not in PHASES:
                refuse("questions_mismatch", f"{where} {set_name}.{q['id']}: phase {q['phase']!r}")
            if q.get("per_arm") and family != "multiturn":
                refuse("questions_mismatch", f"{where} {set_name}.{q['id']}: per_arm outside a script set")
        if len(set(ids)) != len(ids):
            refuse("questions_mismatch", f"{where} question set {set_name!r} repeats a question id")
    notes = doc["notes"]
    if not isinstance(notes, dict) or not (isinstance(notes.get("max_length"), int) and notes["max_length"] > 0):
        refuse("questions_mismatch", f"{where}: notes.max_length is not a positive integer")
    instructions = doc["instructions"]
    families = instructions.get("families") if isinstance(instructions, dict) else None
    if not isinstance(families, dict) or sorted(families) != sorted(FAMILIES):
        refuse("questions_mismatch", f"{where}: instructions.families must name exactly {list(FAMILIES)}")
    return doc


def reveal_scale_values(questions: dict, set_name: str) -> list[Any]:
    """The answer values a reveal's proposed tier may take: the options of the set's one locks_on_reveal question."""
    locking = [q for q in questions["question_sets"][set_name]["questions"] if q.get("locks_on_reveal")]
    if len(locking) != 1:
        refuse("questions_mismatch", f"question set {set_name!r} has {len(locking)} locks_on_reveal questions; a "
                                     "set with a reveal needs exactly one")
    return [o["value"] for o in questions["scales"][locking[0]["scale"]].get("options", [])]


def has_after_reveal(questions: dict, set_name: str) -> bool:
    return any(q["phase"] == "after_reveal" for q in questions["question_sets"][set_name]["questions"])


# ---- tracing pairs -------------------------------------------------------------------------------------------

def pair_display(clinical: str, patient: str, next_word: str) -> dict:
    hc, hp = diff_spans(clinical, patient)
    return {"kind": "pair_sentence", "clinical": {"text": clinical, "highlight": hc},
            "patient": {"text": patient, "highlight": hp}, "next_word": next_word, "cut_off": True}


def pilot_items(inp: Inputs, seal: Seal, run_dir: Path, traces_dir: Path) -> tuple[list[dict], dict]:
    pairs_path = run_dir / "trace" / "trace_pairs.json"
    meta_path = run_dir / "trace" / "trace_pairs.meta.json"
    rows_path = run_dir / "generated" / "all_rows.jsonl"
    pairs, pairs_sha = inp.read_json(pairs_path, "pilot Run 2 trace pairs")
    meta, _ = inp.read_json(meta_path, "pilot Run 2 trace pairs sidecar")
    rows, _ = inp.read_jsonl(rows_path, "pilot Run 2 generated rows")
    check_keys(meta, TRACE_META_KEYS, f"{meta_path.name}", ("output", "counts"))
    if (meta.get("output") or {}).get("sha256") != pairs_sha:
        refuse("hash_mismatch", f"{pairs_path} no longer hashes to the sha256 its sidecar records")
    if not isinstance(pairs, list) or not pairs:
        refuse("bad_input", f"{pairs_path} is not a non-empty list of pairs")
    if (meta.get("counts") or {}).get("selected") != len(pairs):
        refuse("bad_input", f"{pairs_path} holds {len(pairs)} pairs; its sidecar says {meta['counts'].get('selected')}")
    by_id: dict[str, dict] = {}
    for row in rows:
        check_keys(row, PILOT_ROW_KEYS, f"{rows_path.name} row {row.get('id')!r}", ("id",))
        if row["id"] in by_id:
            refuse("bad_input", f"{rows_path.name} repeats row id {row['id']!r}")
        by_id[row["id"]] = row
    traced = traced_prompts(inp, traces_dir)
    source_path = logical_path(pairs_path)
    items = []
    for i, pair in enumerate(pairs, 1):
        where = f"{pairs_path.name} pair {i}"
        check_keys(pair, TRACE_PAIR_KEYS, where, tuple(sorted(TRACE_PAIR_KEYS)))
        pilot = check_keys(pair["pilot"], TRACE_PILOT_KEYS, f"{where} pilot block", ("row_id", "run"))
        row_id = need_str(pilot["row_id"], f"{where} pilot.row_id")
        row = by_id.get(row_id)
        if row is None:
            refuse("bad_input", f"{where}: row {row_id!r} is not in {rows_path.name}")
        top = need_str(pair["top_prompt"], f"{where} top_prompt")
        bottom = need_str(pair["bottom_prompt"], f"{where} bottom_prompt")
        template = need_str(row.get("template"), f"row {row_id} template")
        if template.count(BLANK) != 1:
            refuse("bad_input", f"row {row_id}: template does not hold exactly one blank")
        clinical_term = need_str(row.get("clinical_term"), f"row {row_id} clinical_term")
        patient_term = need_str(row.get("patient_term"), f"row {row_id} patient_term")
        next_word = need_str(row.get("next_word"), f"row {row_id} next_word")
        if top != template.replace(BLANK, clinical_term) or bottom != template.replace(BLANK, patient_term):
            refuse("bad_input", f"{where}: the pair's sentences are not row {row_id}'s template with its terms")
        if pair["target_clinical_token"] != " " + next_word:
            refuse("bad_input", f"{where}: target_clinical_token is not a space plus row {row_id}'s next_word")
        if traced.get(i) != (top, bottom):
            refuse("bad_input", f"{where}: no trace result in {traces_dir} carries index {i} with this pair's "
                                "prompts; only traced pairs are rated")
        if seal.row_sealed("tracing_pilot", None, None, top, f"pilot Run 2 row {row_id}"):
            refuse("sealed_row", f"pilot Run 2 row {row_id} (trace index {i}) is a sealed holdout phrase")
        display = pair_display(top, bottom, next_word)
        seal.note_bucket(item_id_for("tracing_pair", source_path, row_id), top)
        items.append({
            "item_id": item_id_for("tracing_pair", source_path, row_id),
            "family": "tracing_pair", "question_set": "tracing_pair", "display": display, "reveal": None,
            "provenance": {"subset": "pilot_run2", "source_path": source_path, "source_id": row_id,
                           "source_sha256": pairs_sha, "run": pilot["run"], "review_id": pilot.get("review_id"),
                           "trace_index": i, "rows_path": logical_path(rows_path),
                           "display_sha256": sha256_text(canonical(display))},
        })
    selection = {
        "rule": "every pair of pilot Run 2's trace pairs file (the run's blind review sample, 40 pairs), joined to "
                "the run's generated rows for template, terms and next word, each required to have a trace result "
                "with the same prompts",
        "source": source_path,
        "counts": {"pairs": len(pairs), "traced": sum(1 for i in range(1, len(pairs) + 1) if i in traced),
                   "selected": len(items)},
    }
    return items, selection


def traced_prompts(inp: Inputs, traces_dir: Path) -> dict[int, tuple[str, str]]:
    """{trace index: (clinical prompt, patient prompt)} from the trace results under traces_dir."""
    parts = sorted(traces_dir.glob("batch_summary*.json")) if traces_dir.is_dir() else []
    if not parts:
        refuse("missing_input", f"pilot traces: no batch_summary*.json under {traces_dir}")
    out: dict[int, tuple[str, str]] = {}
    for part in parts:
        summary, _ = inp.read_json(part, "pilot Run 2 trace results")
        results = summary.get("results") if isinstance(summary, dict) else None
        if not isinstance(results, list):
            refuse("bad_input", f"{part} has no results list")
        for r in results:
            idx = r.get("index") if isinstance(r, dict) else None
            prompts = r.get("prompts") if isinstance(r, dict) else None
            if not isinstance(idx, int) or not isinstance(prompts, dict):
                refuse("bad_input", f"{part}: a result without an integer index and a prompts object")
            if idx in out:
                refuse("bad_input", f"{part}: trace index {idx} appears twice across the trace results")
            out[idx] = (prompts.get("clinical"), prompts.get("patient"))
    return out


def main_items(inp: Inputs, seal: Seal, site: Path, allowlist: Path, n_pairs: int,
               rank_model: str) -> tuple[list[dict], dict]:
    payload, payload_sha = inp.read_json(site / SITE_PAYLOAD, "published site payload", SITE_LABEL)
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
    if not isinstance(scenarios, list) or not scenarios:
        refuse("bad_input", f"{site / SITE_PAYLOAD} has no scenarios list")
    inp.read_json(allowlist, "holdout seal allowlist")
    try:
        allow_entries = seal_check.load_allowlist(allowlist)
    except ValueError as exc:
        refuse("seal_config", f"seal allowlist malformed ({exc})")
    allow_containing = {e["containing"] for e in allow_entries}
    # each excluded row counts once, under the first reason in this order
    counts: Counter = Counter({"excluded_no_measured_penalty": 0, "excluded_allowlisted_containing_row": 0,
                               "excluded_probe_extended_trace": 0, "excluded_repeat_of_higher_ranked_pair": 0})
    candidates = []
    for n, s in enumerate(scenarios, 1):
        check_keys(s, PAYLOAD_SCENARIO_KEYS, f"payload scenario {n}", ("batch", "batch_index", "clinical_prompt",
                                                                     "patient_prompt", "models"))
        batch, index = s["batch"], s["batch_index"]
        label = f"{batch}#{index}"
        counts["payload_rows"] += 1
        if seal.row_sealed("tracing_main", batch, index, s["clinical_prompt"], f"payload row {label}"):
            refuse("sealed_row", f"the published payload carries the sealed row {label}: a holdout breach on the "
                                 "site. Stop and follow the breach protocol (seal_check.py) before any export")
        model = (s["models"] or {}).get(rank_model) if isinstance(s["models"], dict) else None
        penalty = model.get("language_penalty") if isinstance(model, dict) else None
        if isinstance(penalty, bool) or not isinstance(penalty, (int, float)) or not math.isfinite(penalty):
            counts["excluded_no_measured_penalty"] += 1
            continue
        if label in allow_containing:
            counts["excluded_allowlisted_containing_row"] += 1
            continue
        if ((model.get("screening") or {}).get("probe_extension")):
            counts["excluded_probe_extended_trace"] += 1
            continue
        candidates.append((-round(abs(penalty), RANK_DECIMALS), batch, index, s, model, penalty))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    seen: set[tuple[str, str]] = set()
    chosen = []
    for c in candidates:
        s = c[3]
        key = (s["clinical_prompt"], s["patient_prompt"])
        if key in seen:
            counts["excluded_repeat_of_higher_ranked_pair"] += 1
            continue
        seen.add(key)
        if len(chosen) < n_pairs:
            chosen.append(c)
    counts["ranked_candidates"] = len(seen)
    if len(chosen) < n_pairs:
        refuse("too_few_candidates", f"only {len(chosen)} main-study pairs remain after the exclusions; "
                                     f"--main-pairs asked for {n_pairs}")
    items = []
    highlight_missing: Counter = Counter()
    for rank, (_, batch, index, s, model, penalty) in enumerate(chosen, 1):
        label = f"{batch}#{index}"
        clinical = need_str(s["clinical_prompt"], f"payload row {label} clinical_prompt")
        patient = need_str(s["patient_prompt"], f"payload row {label} patient_prompt")
        next_word = need_str(s.get("intended_target"), f"payload row {label} intended_target").strip()
        display = pair_display(clinical, patient, next_word)
        for side in ("clinical", "patient"):
            if display[side]["highlight"] is None:
                highlight_missing[side] += 1
        seal.note_bucket(item_id_for("tracing_pair", SITE_LABEL, label), clinical)
        items.append({
            "item_id": item_id_for("tracing_pair", SITE_LABEL, label),
            "family": "tracing_pair", "question_set": "tracing_pair", "display": display, "reveal": None,
            "provenance": {"subset": "main_study", "source_path": SITE_LABEL, "source_id": label,
                           "source_sha256": payload_sha, "rank": rank, "rank_model": rank_model,
                           "language_penalty": penalty, "anchor_fallback": bool(model.get("anchor_fallback")),
                           "tierb": tierb_split.is_tierb_batch(batch, seal.start),
                           "display_sha256": sha256_text(canonical(display))},
        })
    penalties = [-c[0] for c in chosen]
    selection = {
        "rule": f"pairs already published in the site payload, ranked by the absolute language penalty of "
                f"{rank_model} rounded to {RANK_DECIMALS} decimals (largest first; ties by batch, then index; the "
                "rounding removes floating-point noise, so penalties equal as recorded tie), excluding rows without "
                "a measured penalty, rows the seal allowlist names as containing a sealed phrase, rows traced with a "
                "screening "
                "probe extension, and repeats of a higher-ranked prompt pair (each excluded row counted once, under "
                "the first of these reasons). A selection heuristic for review, not a measurement: no claim rests "
                "on one pair's penalty (AGENTS.md, known measurement limitations)",
        "source": SITE_LABEL,
        "source_sha256": payload_sha,
        "rank_model": rank_model,
        "rank_decimals": RANK_DECIMALS,
        "main_pairs_requested": n_pairs,
        "allowlist_entries": len(allow_entries),
        "counts": dict(sorted(counts.items())) | {"selected": len(items)},
        "abs_language_penalty_range": [min(penalties), max(penalties)] if penalties else None,
        "highlight_not_found": {"clinical": highlight_missing["clinical"], "patient": highlight_missing["patient"]},
    }
    return items, selection


# ---- advice --------------------------------------------------------------------------------------------------

def _advice_display(item: dict, where: str, cut_off: bool) -> dict:
    clinical = need_str(item["clinical_message"], f"{where} clinical_message")
    patient = need_str(item["patient_message"], f"{where} patient_message")
    if sha256_text(clinical) != item["clinical_sha256"] or sha256_text(patient) != item["patient_sha256"]:
        refuse("hash_mismatch", f"{where}: a message no longer hashes to its recorded sha256")
    return {"kind": "message_pair", "clinical_message": clinical, "patient_message": patient, "cut_off": cut_off}


def _advice_seal(seal: Seal, item: dict, where: str) -> None:
    ref = item.get("source_ref") if isinstance(item.get("source_ref"), dict) else {}
    batch = ref.get("batch") if isinstance(ref.get("batch"), str) and ref.get("batch") else None
    index = ref.get("batch_index") if batch else None
    if seal.row_sealed("advice", batch, index, item.get("clinical_body"), where):
        refuse("sealed_row", f"{where} is a sealed Tier B holdout pair")


def advice_items(inp: Inputs, seal: Seal, questions: dict, new_path: Path,
                 rerun_path: Path) -> tuple[list[dict], dict]:
    items: list[dict] = []
    tiers_allowed = reveal_scale_values(questions, "advice_new")
    new_doc, new_sha = inp.read_json(new_path, "advice stimuli, new questions")
    check_keys(new_doc, ADVICE_FILE_KEYS, new_path.name, tuple(sorted(ADVICE_FILE_KEYS)))
    check_keys(new_doc["source"], ADVICE_NEW_SOURCE_KEYS, f"{new_path.name} source")
    new_list = new_doc["items"]
    if not isinstance(new_list, list) or new_doc["n_items"] != len(new_list):
        refuse("bad_input", f"{new_path.name}: items is not a list of n_items entries")
    new_source = logical_path(new_path)
    tier_counts: Counter = Counter()
    for item in new_list:
        where = f"{new_path.name} item {item.get('id')!r}"
        check_keys(item, ADVICE_ITEM_KEYS, where, tuple(sorted(ADVICE_ITEM_KEYS)))
        meta = check_keys(item["meta"], ADVICE_NEW_META_KEYS, f"{where} meta")
        check_keys(meta.get("notes", {}), ADVICE_NOTES_KEYS, f"{where} meta.notes")
        reference = check_keys(item["reference"], ADVICE_REFERENCE_KEYS, f"{where} reference", ("tier",))
        if reference["tier"] not in tiers_allowed:
            refuse("bad_input", f"{where}: reference tier is not one of the reveal scale's values")
        _advice_seal(seal, item, where)
        display = _advice_display(item, where, cut_off=False)
        tier_counts[reference["tier"]] += 1
        item_id = item_id_for("advice", new_source, need_str(item["id"], f"{where} id"))
        seal.note_bucket(item_id, need_str(item["clinical_body"], f"{where} clinical_body"))
        items.append({
            "item_id": item_id,
            "family": "advice", "question_set": "advice_new", "display": display,
            "reveal": {"proposed_tier": reference["tier"]},
            "provenance": {"source_path": new_source, "source_id": item["id"], "source_sha256": new_sha,
                           "clinical_sha256": item["clinical_sha256"], "patient_sha256": item["patient_sha256"],
                           "display_sha256": sha256_text(canonical(display))},
        })
    rerun_doc, rerun_sha = inp.read_json(rerun_path, "advice stimuli, rerun")
    check_keys(rerun_doc, ADVICE_FILE_KEYS, rerun_path.name, tuple(sorted(ADVICE_FILE_KEYS)))
    source = check_keys(rerun_doc["source"], ADVICE_RERUN_SOURCE_KEYS, f"{rerun_path.name} source",
                        ("file_sources",))
    file_sources = source["file_sources"]
    rerun_list = rerun_doc["items"]
    if not isinstance(rerun_list, list) or rerun_doc["n_items"] != len(rerun_list):
        refuse("bad_input", f"{rerun_path.name}: items is not a list of n_items entries")
    rerun_source = logical_path(rerun_path)
    forms: Counter = Counter()
    for item in rerun_list:
        where = f"{rerun_path.name} item {item.get('id')!r}"
        check_keys(item, ADVICE_ITEM_KEYS - {"reference"}, where, tuple(sorted(ADVICE_ITEM_KEYS - {"reference"})))
        meta = check_keys(item["meta"], ADVICE_RERUN_META_KEYS, f"{where} meta", ("rerun_of",))
        rerun_of = check_keys(meta["rerun_of"], RERUN_OF_KEYS, f"{where} meta.rerun_of", ("file", "id"))
        kind = (file_sources.get(rerun_of["file"]) or {}).get("kind") if isinstance(file_sources, dict) else None
        if kind not in ("payload", "pairs"):
            refuse("bad_input", f"{where}: its source file {rerun_of['file']} has no payload/pairs kind in the "
                                "file's source.file_sources")
        if kind == "pairs":
            form = "natural"
        elif "completed_with" in meta:
            form = "completed"
        else:
            form = "truncated"
        forms[form] += 1
        _advice_seal(seal, item, where)
        display = _advice_display(item, where, cut_off=(form == "truncated"))
        item_id = item_id_for("advice", rerun_source, need_str(item["id"], f"{where} id"))
        seal.note_bucket(item_id, need_str(item["clinical_body"], f"{where} clinical_body"))
        items.append({
            "item_id": item_id,
            "family": "advice",
            "question_set": "advice_rerun_truncated" if form == "truncated" else "advice_rerun",
            "display": display, "reveal": None,
            "provenance": {"source_path": rerun_source, "source_id": item["id"], "source_sha256": rerun_sha,
                           "form": form, "rerun_of": {"file": rerun_of["file"], "id": rerun_of["id"]},
                           "clinical_sha256": item["clinical_sha256"], "patient_sha256": item["patient_sha256"],
                           "display_sha256": sha256_text(canonical(display))},
        })
    selection = {
        "advice_new": {"rule": "every item of the new-question stimuli file; reveal = its proposed reference tier",
                       "source": new_source, "counts": {"items": len(new_list)},
                       "proposed_tiers": dict(sorted(tier_counts.items()))},
        "advice_rerun": {"rule": "every item of the rerun stimuli file; an item from a stimuli file built from the "
                                 "payload's cut-off sentences and not completed with its target word is "
                                 "'truncated' (question set advice_rerun_truncated), one completed with it is "
                                 "'completed', one from a natural-question pairs file is 'natural'",
                         "source": rerun_source, "counts": {"items": len(rerun_list)},
                         "forms": dict(sorted(forms.items()))},
        "excluded_files": EXCLUDED_ADVICE_FILES,
    }
    return items, selection


# ---- multi-turn ----------------------------------------------------------------------------------------------

def multiturn_items(inp: Inputs, seeds_path: Path) -> tuple[list[dict], dict]:
    doc, doc_sha = inp.read_json(seeds_path, "Petri wave-3 seeds")
    check_keys(doc, SEED_FILE_KEYS, seeds_path.name, ("seeds",))
    seeds = doc["seeds"]
    if not isinstance(seeds, list) or not seeds:
        refuse("bad_input", f"{seeds_path.name}: seeds is not a non-empty list")
    source = logical_path(seeds_path)
    items = []
    counts: Counter = Counter()
    for seed in seeds:
        where = f"{seeds_path.name} seed {seed.get('seed_id')!r}" if isinstance(seed, dict) else seeds_path.name
        check_keys(seed, SEED_KEYS, where, ("seed_id", "mode", "pilot_wave", "texts", "protocol"))
        seed_id = need_str(seed["seed_id"], f"{where} seed_id")
        if seed["mode"] != "scripted" or seed["pilot_wave"] != MULTITURN_WAVE:
            refuse("bad_input", f"{where}: only scripted wave-{MULTITURN_WAVE} seeds have a fixed patient script "
                                f"(mode {seed['mode']!r}, wave {seed['pilot_wave']!r})")
        protocol = check_keys(seed["protocol"], PROTOCOL_KEYS, f"{where} protocol", ("arms", "max_target_turns"))
        if protocol.get("branches"):
            refuse("bad_input", f"{where}: a branching protocol has no single script to show")
        texts: dict[str, str] = {}
        for entry in seed["texts"]:
            check_keys(entry, TEXT_KEYS, f"{where} text", ("key", "text", "sha256"))
            if entry["key"] in texts:
                refuse("bad_input", f"{where}: text key {entry['key']!r} appears twice")
            if sha256_text(entry["text"]) != entry["sha256"]:
                refuse("hash_mismatch", f"{where}: text {entry['key']!r} no longer hashes to its recorded sha256")
            texts[entry["key"]] = entry["text"]
        n_turns = protocol["max_target_turns"]
        arms_out: list[dict] = []
        turn_sha: dict[str, list[str]] = {}
        for arm in protocol["arms"]:
            check_keys(arm, ARM_KEYS, f"{where} arm", ("id", "turns"))
            arm_id = need_str(arm["id"], f"{where} arm id")
            if any(a["arm"] == arm_id for a in arms_out):
                refuse("bad_input", f"{where}: arm {arm_id!r} appears twice")
            if not isinstance(arm["turns"], list) or len(arm["turns"]) != n_turns:
                refuse("bad_input", f"{where} arm {arm_id!r}: its turns are not a list of max_target_turns "
                                    f"({n_turns!r}) entries")
            turns = []
            for t, turn in enumerate(arm["turns"]):
                check_keys(turn, TURN_KEYS, f"{where} arm {arm_id!r} turn {t + 1}", ("role", "text_ref"))
                if turn["role"] != "user":
                    refuse("bad_input", f"{where} arm {arm_id!r} turn {t + 1}: role {turn['role']!r} is not the "
                                        "patient's message")
                if turn["text_ref"] not in texts:
                    refuse("bad_input", f"{where} arm {arm_id!r} turn {t + 1}: text_ref does not resolve")
                text = texts[turn["text_ref"]]
                same_as = next((a["arm"] for a in arms_out if a["turns"][t]["text"] == text), None)
                counts["same_as"] += same_as is not None
                turns.append({"text": text, "same_as": same_as})
            arms_out.append({"arm": arm_id, "turns": turns})
            turn_sha[arm_id] = [sha256_text(t["text"]) for t in turns]
        if len(arms_out) < 2:
            refuse("bad_input", f"{where}: fewer than two arms")
        counts["seeds"] += 1
        counts["arms"] += len(arms_out)
        counts["turns"] += len(arms_out) * n_turns
        display = {"kind": "script", "n_turns": n_turns, "arms": arms_out}
        items.append({
            "item_id": item_id_for("multiturn", source, seed_id),
            "family": "multiturn", "question_set": "multiturn_script", "display": display, "reveal": None,
            "provenance": {"source_path": source, "source_id": seed_id, "source_sha256": doc_sha,
                           "seed_sha256": seed_digest(seed),
                           "scenario_id": (seed.get("scenario") or {}).get("id"),
                           "turn_sha256": turn_sha, "display_sha256": sha256_text(canonical(display))},
        })
    selection = {"rule": f"one item per scripted wave-{MULTITURN_WAVE} seed: every arm's user turns in order, no "
                         "model replies; same_as names the first earlier arm whose turn is word for word the same",
                 "source": source, "counts": dict(sorted(counts.items()))}
    return items, selection


# ---- bundle --------------------------------------------------------------------------------------------------

def parse_stamp(stamp: str | None) -> tuple[str, str]:
    """(compact stamp, ISO created_utc) for --stamp, or the current UTC second."""
    if stamp is None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")
    m = _STAMP_RE.match(stamp)
    if not m:
        refuse("bad_input", f"--stamp {stamp!r} is not YYYYMMDDTHHMMSSZ")
    try:
        datetime(*(int(g) for g in m.groups()), tzinfo=timezone.utc)
    except ValueError:
        refuse("bad_input", f"--stamp {stamp!r} is not a real UTC time")
    y, mo, d, h, mi, s = m.groups()
    return stamp, f"{y}-{mo}-{d}T{h}:{mi}:{s}Z"


def build_bundle(args: argparse.Namespace) -> tuple[dict, str]:
    """(bundle, file name) for the parsed arguments, or a named refusal. Writes nothing."""
    if args.main_pairs < 0:
        refuse("bad_input", "--main-pairs must be 0 or more")
    stamp, created = parse_stamp(args.stamp)
    inp = Inputs()
    q_bytes = inp.read_bytes(Path(args.questions), "question wording and scales")
    try:
        questions = json.loads(q_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        refuse("unreadable_input", f"{args.questions} is not UTF-8 JSON")
    validate_questions(questions, Path(args.questions).name)
    inp.read_bytes(Path(args.dashboard), "holdout seal: Tier B start (dashboard)")
    seal = Seal(Path(args.dashboard), Path(args.simulated))

    pilot, pilot_sel = pilot_items(inp, seal, Path(args.pilot_run), Path(args.pilot_traces))
    if args.main_pairs:
        main, main_sel = main_items(inp, seal, Path(args.site), Path(args.allowlist), args.main_pairs,
                                    args.rank_model)
    else:
        main, main_sel = [], {"rule": "not requested (--main-pairs 0)", "counts": {"selected": 0}}
    advice, advice_sel = advice_items(inp, seal, questions, Path(args.advice_new), Path(args.advice_rerun))
    multi, multi_sel = multiturn_items(inp, Path(args.petri_seeds))
    items = pilot + main + advice + multi

    advice_rerun_pairs = {i["provenance"]["rerun_of"]["id"] for i in advice if i["question_set"] != "advice_new"}
    main_sel["overlap_with_advice_rerun_sources"] = sum(1 for i in main if i["provenance"]["source_id"]
                                                        in advice_rerun_pairs)

    ids = Counter(i["item_id"] for i in items)
    dupes = sorted(k for k, v in ids.items() if v > 1)
    if dupes:
        refuse("id_collision", f"item ids repeat: {dupes}")
    for i in items:
        set_name = i["question_set"]
        if QUESTION_SETS[set_name] != i["family"]:
            refuse("questions_mismatch", f"{i['item_id']}: question set {set_name!r} is not a {i['family']} set")
        if (i["reveal"] is not None) != has_after_reveal(questions, set_name):
            refuse("questions_mismatch", f"{i['item_id']}: a reveal and after_reveal questions must come together "
                                         f"(question set {set_name!r})")
        if i["reveal"] is not None and i["reveal"]["proposed_tier"] not in reveal_scale_values(questions, set_name):
            refuse("questions_mismatch", f"{i['item_id']}: the proposed tier is not an option of its reveal scale")

    hits: dict[str, list[str]] = {}
    for i in items:
        found = sorted({label for text in strings_in(i["display"]) for label in seal.scan(text)})
        if found:
            hits[i["item_id"]] = found
    if hits:
        refuse("seal_hit", f"rater-visible text of {len(hits)} item(s) contains a sealed holdout phrase: "
                           + "; ".join(f"{k} :: {', '.join(v)}" for k, v in sorted(hits.items())))

    items.sort(key=lambda i: i["item_id"])
    random.Random(args.seed).shuffle(items)
    by_family = Counter(i["family"] for i in items)
    by_set = Counter(i["question_set"] for i in items)
    bundle = {
        "schema": SCHEMA,
        "bundle_id": f"vtasks_{stamp}",
        "created_utc": created,
        "seed": args.seed,
        "questions": questions,
        "questions_sha256": sha256_bytes(q_bytes),
        "sources": inp.sources,
        "selection": {
            "tracing_pair": {"pilot_run2": pilot_sel, "main_study": main_sel},
            "advice": advice_sel,
            "multiturn": multi_sel,
            "order": "items sorted by item_id, then shuffled with Python's random.Random(seed); the app orders "
                     "each physician's items by its own seeded hash",
            "item_id": "vt_ + the first 12 hex digits of sha256(family U+001F source path U+001F source id)",
            "highlight": "the shortest span where the two sentences differ, widened to whole words; [start, end) in "
                         "UTF-16 code units (JavaScript string indices)",
        },
        "seal": {
            "result": "clean",
            "phrase_count": len(seal.registry),
            "registry_labels_sha256": sha256_text("\n".join(sorted(seal.registry.values()))),
            "tierb_start_stamp": seal.start,
            "rows_checked_with_sealed_pair": dict(sorted(seal.rows_checked.items())),
            "accepted_prompts_checked": seal.accepted_checked,
            "rater_visible_texts_scanned": seal.texts_scanned,
            "whole_bundle_scanned": True,
            "allowlist_applied": False,
            "holdout_bucket_unsealed": {
                "item_ids": sorted(seal.bucket_items),
                "rule": "items whose clinical text (the sentence of a tracing pair, the clinical body of an advice "
                        "item) hashes into the holdout bucket (tierb_split.is_holdout) but is not sealed; Amendment 3 "
                        "would seal such a text everywhere once a later Tier B batch accepted the same prompt. "
                        "scripts/seal_check.py sweeps data/verification by default, so the daily sweep would flag it",
            },
            "method": "tierb_split.sealed_pair on every tracing and advice row (and every published payload row); "
                      "seal_check.scan_text over every rater-visible string and over the serialized bundle, with no "
                      "allowlist",
        },
        "counts": {
            "items": len(items),
            "by_family": {f: by_family[f] for f in FAMILIES},
            "by_question_set": {s: by_set[s] for s in QUESTION_SETS},
            "with_reveal": sum(1 for i in items if i["reveal"] is not None),
            "tracing_pair_by_subset": {"pilot_run2": len(pilot), "main_study": len(main)},
        },
        "items": items,
    }
    text = serialize(bundle)
    whole = seal.scan(text, ".json")
    if whole:
        refuse("seal_hit", f"the serialized bundle contains sealed holdout phrase(s): {', '.join(sorted(whole))}")
    return bundle, f"tasks_{stamp}.json"


def serialize(bundle: dict) -> str:
    """The bundle file's exact text: ASCII-escaped JSON (safe through Drive and Apps Script), one-space indent."""
    return json.dumps(bundle, ensure_ascii=True, indent=1) + "\n"


def write_bundle(bundle: dict, out_dir: Path, name: str) -> Path:
    out = out_dir / name
    if out.exists():
        refuse("output_exists", f"{out} already exists; a bundle is an archive and is never rewritten (pass a new "
                                "--stamp)")
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".tasks_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(serialize(bundle))
        os.chmod(tmp, 0o644)
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return out


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default=str(DEFAULTS["site"]),
                    help="the public site checkout whose data/simulated_scenarios.json lists published pairs")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="item-order seed, recorded in the bundle")
    ap.add_argument("--main-pairs", type=int, default=DEFAULT_MAIN_PAIRS,
                    help="how many main-study pairs to take by absolute language penalty (0 skips the payload)")
    ap.add_argument("--rank-model", default=DEFAULT_RANK_MODEL, help="the model whose language penalty ranks pairs")
    ap.add_argument("--stamp", default=None, help="UTC stamp YYYYMMDDTHHMMSSZ (default: now)")
    ap.add_argument("--out-dir", default=str(DEFAULTS["out_dir"]))
    for key in ("questions", "pilot_run", "pilot_traces", "advice_new", "advice_rerun", "petri_seeds",
                "dashboard", "simulated", "allowlist"):
        ap.add_argument("--" + key.replace("_", "-"), default=str(DEFAULTS[key]))
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle, name = build_bundle(args)
    out = write_bundle(bundle, Path(args.out_dir), name)
    digest = sha256_bytes(out.read_bytes())
    print(json.dumps({"written": logical_path(out), "sha256": digest, "bundle_id": bundle["bundle_id"],
                      "seed": bundle["seed"], "counts": bundle["counts"],
                      "seal": {"result": bundle["seal"]["result"], "phrase_count": bundle["seal"]["phrase_count"]}},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
