"""Physician verification task bundle: the scenarios physicians rate in the private verification app.

Writes ``data/verification/tasks_<UTC stamp>.json`` (schema ``patientwords-verification-tasks/1``), the one file the
owner uploads to Google Drive for the app in the private repository michaeldgreenphd/patientwords-verify. The app
shows each physician only an item's ``display`` and its questions; ``reveal`` only after that physician's own blind
answers are saved; never ``provenance`` or any bundle metadata. docs/verification_protocol.md is the plain-language
protocol.

Three families, every item from a committed engine file or the published site payload:

* ``tracing_pair`` (question set ``tracing_pair``; display kind ``pair_sentence``):
  - the pairs of each pilot run named with ``--pilot-run <run id>`` (repeatable; a run is the directory
    ``<--pilot-runs-dir>/<run id>``, default ``pilot/runs/``; with none named, ``pilot_v2_20261002`` alone, the first
    bundle's run). A run must be finalized (``manifest.json`` has ``finalized_utc``) and version 2 (``design.json``
    ``harness_version`` 2), and every run file read (``design.json``, ``generated/all_rows.jsonl``,
    ``review_map.json``) must hash as the finalized manifest's ``output_hashes`` records. Each run contributes its
    blind review sample (the rows ``review_map.json`` names, in review-id order), or with ``--pilot-all-rows <run
    id>`` every generated row whose ``control`` is ``none`` (negative controls are excluded and counted), each shown
    as its template with the clinical and the patient term and the row's next word, which must follow the version-2
    next_word rule (one lowercase word, ``next_word_ok``; ``bad_next_word``). By default every pair needs a trace
    result: the run's one trace pairs file (the JSON file under ``<run>/trace/`` beside its ``.meta.json`` sidecar)
    must hold the row, and the trace results must carry its index with the same prompts. They are read where the
    circuit-trace lane's pilot root writes them under PR #85's per-run layout: ``<--pilot-trace-root>/<run id>/<that
    file's stem>/`` (default root ``pilot/traces/``), or ``<stem>__<model>/`` there for a graph model other than
    gemma-2-2b. The two folders written before that layout stay where they are and are read for their own runs
    (``LEGACY_TRACE_FOLDERS``): Run 2's ``pilot/traces/trace_pairs/`` and Run 3's
    ``pilot/traces/pilot_v3_20261004_trace_pairs/`` (with ``__<model>`` likewise). A run with one graph model's
    results in both layouts is refused (``trace_layout_conflict``), never chosen between (different models in
    different layouts are read by the model rules below), and a run id that is one of those folder names is refused,
    as the lanes refuse it. The model is the one ``--pilot-trace-model <run id> <model>`` names, read from its own
    directory only; with none named, the one model whose directory holds results, and results for none or in more than
    one directory are refused (``missing_trace``, ``ambiguous_trace``), never guessed between. Every trace summary
    read must declare that model in its ``graph_model`` field, as the hosted summaries do (``trace_model_mismatch``),
    so a summary placed in another model's directory is never recorded under that directory's model. A trace pairs
    file must be named after its run, ``<run id>_<name>.json`` with ``<name>`` not empty, the rule the lane's pilot
    root applies before it traces a file, and its stem may not hold ``__``; both are checked for a run with optional
    traces too (only names are read). Two runs' files may share a stem, since each run's results are in its own
    folder. Run 2's ``trace_pairs.json`` predates the naming rule and keeps its name; its ``trace/`` may also hold
    byte-identical copies named for the run (the lane needs one to trace Run 2 again). The exporter still reads
    ``trace_pairs.json``, which Run 2's item ids are keyed on, and reads a copy's trace results as the same pairs'
    results, in Run 2's own folder ``<root>/pilot_v2_20261002/<copy's stem>/``; with Run 2's legacy results present, a
    copy traced with gemma-2-2b is a ``trace_layout_conflict``, and one traced with another model makes two models
    (name one). A trace pairs file built with ``trace_pairs.py --review-sample`` records each pair's review id, which
    must be the one ``review_map.json`` gives its row; one built without it records none (a file recording some is
    refused). The review sample therefore needs a ``--review-sample`` trace pairs file (or one that holds every review
    row), and ``--pilot-all-rows`` one that holds every non-control row, which neither of ``trace_pairs.py``'s
    selections gives once the checker has judged any row not equivalent; in practice it goes with
    ``--pilot-trace-optional``. With ``--pilot-trace-optional <run id>`` that run's pairs need no trace and its trace
    results are not read, so its items do not change when its traces land; a pair joins its trace later by run and row
    id. Such a run reads no trace file at all, except Run 2, whose item ids are keyed on its trace pairs file: that
    file is still read (and must exist) for the items' ``source_sha256``. A pair whose two sentences repeat an earlier
    pilot item's is kept (each row is its run's output) and counted. Item ids are keyed on the run's generated rows
    file and the row id, so a row keeps one id under every selection and trace option; Run 2's are keyed on its trace
    pairs file and labelled ``pilot_run2``, as in the first bundle (``LEGACY_PILOT_RUNS``), and every other run's
    items are labelled ``pilot:<run id>``. Labels are provenance, never shown to a rater;
  - the ``--main-pairs`` (default 40) main-study pairs already published in the site payload
    (``<site>/data/simulated_scenarios.json``) whose ``--rank-model`` (default gemma-2-2b) language penalty is
    largest in absolute value, compared at ``RANK_DECIMALS`` decimals so that penalties equal at their recorded
    precision tie and the stated tie rule (batch, then index) decides between them. A row without a measured
    penalty, a row the seal allowlist names as containing a
    sealed phrase, a row traced with a screening probe extension (the traced sentence is not the generated one) and
    a repeat of a higher-ranked prompt pair are excluded and counted. The ranking is a way to pick pairs worth a
    physician's look, not a measurement: AGENTS.md's known limitations say no claim may rest on one pair's penalty.
  The highlight on each sentence is the shortest span where the two sentences differ, widened to whole words, so
  the family instruction that the two sentences differ only in the marked words is true by construction. Offsets
  are JavaScript string indices (UTF-16 code units), end exclusive.
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

Examples. The questions file may hold ``instructions.examples``, invented examples the app shows a physician before
the first item: a list of ``{family, label, caption, display}``, where ``family`` names a question set (a key of
``QUESTION_SETS``: tracing_pair, advice_new, advice_rerun, advice_rerun_truncated or multiturn_script; the set's own
``family`` gives its item family and so its entry in ``instructions.families``), ``label`` and ``caption`` are text,
and ``display`` has exactly the shape that set's items' display has (``validate_examples``): the same kind and
fields, a highlight that is the span ``diff_spans`` gives, the cut-off flag the set's items carry, a script's turns
``n_turns`` long with ``same_as`` set as ``multiturn_items`` sets it. An example carries nothing else: no answer,
reveal or provenance. An item's display is built only from the texts a physician rates, so it carries none of the
study's own model names, ids, measurements or answers; an example is written by hand, so its text is checked
instead, and more strictly than an item's could be: it may not hold a model or vendor name from any of the engine's
model registries (``EXAMPLE_MODEL_NAMES``; found inside another word too, as in BioMistral), a batch, run or item id,
a decimal number or a percentage (how a measured value is written, though a patient's message in an item may hold
one), or the label of an urgency level a reveal can propose (read from the questions data). Every example string is
seal-scanned as an item's display strings are.
The bundle copies the questions file, examples included, unchanged. A questions file without ``examples`` is valid.

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
know in a record it reads (a new field may carry meaning the selection must respect, so a person decides), a shape it
cannot use, a text whose sha256 no longer matches, a pilot run that is not finalized (``run_not_finalized``) or not
version 2 (``run_not_version_2``), a pilot row whose next word breaks the version-2 rule (``bad_next_word``), whether
or not its trace is required, a run id that is a legacy trace folder's name, a trace pairs file not named after its
run or whose stem holds ``__``, a second file under the ``trace/`` of a run whose trace is required (for Run 2, one
that is not a byte-identical copy of its pairs file; an optional run reads no pairs file but Run 2's id key, so only
the names of its files are checked), a pilot pair without its required trace (``missing_trace``) or whose trace
result carries other prompts (``trace_mismatch``), trace results in more than one directory for the model read, or
for more than one graph model with none named (``ambiguous_trace``), trace results in both the legacy and the per-run
layout for one model (``trace_layout_conflict``), a trace summary that does not declare the graph model its directory
is read as (``trace_model_mismatch``), a questions file that does not fit the items, an example that is malformed
(``bad_example``), shows what a physician may not see (``example_not_blind``) or repeats or nearly repeats a study
text (``example_copies_item``), fewer main-study candidates than
requested, an item id collision, an existing output file (a bundle is an archive, never rewritten), and every seal
failure above (a sealed phrase in an example is ``seal_hit``, naming the example).

Rounds. Each physician round uses one bundle (the ratings import reads one bundle per export). A later round's
bundle is built with ``--previous-bundle <the previous round's bundle>``, which refuses unless every item of that
bundle is in the new one under the same id with the same question set, display and reveal (``previous_item_missing``,
``previous_item_changed``), every question id it uses is kept (``previous_question_missing``) with the same scale
type, answer values, abstain value, text length limit, phase, required, per_arm and reveal lock
(``previous_question_changed``), no question set the previous items use has gained a required question
(``previous_required_question_added``; a new optional question is allowed), and the notes length limit is the same
(``previous_notes_changed``): the app needs every item a physician holds to stay in the bundle it switches to, stores
answers under item and question ids, validates a stored answer and note against the question's current scale, phase
and lock and the notes limit, and gates the reveal and an item's completeness on ``required``, so a required
question added to a set has no stored answer and would turn a completed rating incomplete. These are compared as
canonical JSON, so a value of another JSON type (true for 1) is a change, as it is to the app and the import.
docs/verification_protocol.md (Rounds) has how round 2 is built.

Usage (from the engine root):
  python scripts/export_verification_tasks.py [--site ../patientwords] [--seed 20261003] [--main-pairs 40]
      [--stamp 20261003T120000Z] [--out-dir data/verification]
      [--pilot-run RUN_ID ...] [--pilot-all-rows RUN_ID ...] [--pilot-trace-optional RUN_ID ...]
      [--pilot-trace-model RUN_ID MODEL ...]
      [--previous-bundle data/verification/tasks_<stamp>.json]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
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


def _load_pilot_module(rel: str, name: str) -> Any:
    """A module of this checkout's pilot/ loaded by its path (pilot/ is not a package, and an import by name could
    resolve to another engine checkout on sys.path)."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {rel}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The version-2 next_word rule: one lowercase word of letters, at most one internal hyphen or apostrophe. The parser
# applies pilot/scripts/common.next_word_ok to every version-2 row, and the trace-pairs builder applies its copy
# before it builds a pair (tests/test_pilot_trace_pairs.py holds the two equal). The exporter uses the builder's, not
# a third copy: the builder is standard library only and reads nothing when imported, whereas importing common reads
# the pilot design (or PILOT_DIR's) at import time.
next_word_ok = _load_pilot_module("pilot/analysis/trace_pairs.py", "_pilot_trace_pairs_builder").next_word_ok

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
# Pilot runs: a run is a directory under --pilot-runs-dir (default pilot/runs), named by its run id.
DEFAULT_PILOT_RUN = "pilot_v2_20261002"
HARNESS_VERSION = 2
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
PILOT_SUBSET_PREFIX = "pilot:"
# Run 2's items were first exported (tasks_20261004T042945Z.json) under the subset label "pilot_run2" and keyed on
# the run's trace pairs file, so they keep both: the item id is derived from that key, and the app stores every
# rating under the item id (a changed id orphans them). Every other run is labelled "pilot:<run id>" and keyed on its
# generated rows file, which every selection and trace option reads, so a row keeps one item id in every bundle.
LEGACY_PILOT_RUNS = {"pilot_v2_20261002": {"subset": "pilot_run2", "id_source": "trace/trace_pairs.json"}}
# The circuit-trace lane's pilot root writes a run's trace results in the run's own folder (PR #85's per-run layout,
# 2026-10-05): <root>/<run id>/<pairs-file stem>/ for gemma-2-2b and <root>/<run id>/<pairs-file stem>__<model>/ for
# any other graph model, where <run id> is the directory directly under pilot/runs/ that holds the pairs file
# (circuit_trace_evaluation.yml, "Select sample pairs"; fire_trigger.pilot_run_id). The exporter reads them by the
# same rule. A pairs-file stem may not hold MODEL_SEPARATOR, so that no results directory can be read both as one
# stem's and as another stem's with a model suffix.
UNSUFFIXED_TRACE_MODEL = "gemma-2-2b"
MODEL_SEPARATOR = "__"
# Before 2026-10-05 the lane wrote <root>/<pairs-file stem>[__<model>]/, with no run folder. Two runs' parts were
# written that way and stay where they are (fire_trigger.PILOT_LEGACY_OUTPUT_FOLDERS, PR #85): Run 2's in
# pilot/traces/trace_pairs/ and Run 3's in pilot/traces/pilot_v3_20261004_trace_pairs/. The exporter reads such a
# folder for its own run only, and only while the run still holds the pairs file the folder is named after. A run with
# one model's results both there and in its own folder is refused (trace_layout_conflict), never chosen between;
# another model's results in its own folder are not a conflict. The lanes refuse
# a run id that is one of these folder names, since that run's own folder would sit inside the old one, and so does
# the exporter. A test holds the names equal to fire_trigger's list when fire_trigger has one.
LEGACY_TRACE_FOLDERS = {"pilot_v2_20261002": "trace_pairs", "pilot_v3_20261004": "pilot_v3_20261004_trace_pairs"}
SITE_PAYLOAD = "data/simulated_scenarios.json"
SITE_LABEL = "patientwords:" + SITE_PAYLOAD
BLANK = "___"

DEFAULTS = {
    "questions": REPO_ROOT / "data" / "verification" / "questions.json",
    "pilot_runs_dir": REPO_ROOT / "pilot" / "runs",
    "pilot_trace_root": REPO_ROOT / "pilot" / "traces",
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
# The fields of the questions file's instructions. Checked before anything reads it, so a misspelled field (example
# for examples) is refused by name instead of reading as "no examples" (Codex review of PR #88).
INSTRUCTIONS_KEYS = frozenset({"version", "welcome", "consent", "families", "examples", "tier_scale_note"})
OPTION_KEYS = frozenset({"value", "label", "definition"})
SCALE_TYPES = frozenset({"ordinal", "nominal", "multi", "text"})
PHASES = frozenset({"blind", "after_reveal"})

# ---- instructions.examples (optional): invented examples shown before the first item ---------------------------
EXAMPLE_KEYS = frozenset({"family", "label", "caption", "display"})
# The display an item of each family has (pair_display, _advice_display, multiturn_items build them), by its fields.
DISPLAY_KIND = {"tracing_pair": "pair_sentence", "advice": "message_pair", "multiturn": "script"}
DISPLAY_FIELDS = {"pair_sentence": frozenset({"kind", "clinical", "patient", "next_word", "cut_off"}),
                  "message_pair": frozenset({"kind", "clinical_message", "patient_message", "cut_off"}),
                  "script": frozenset({"kind", "n_turns", "arms"})}
# The cut_off flag every item of a question set carries: a tracing sentence always stops before its next word, and
# advice_rerun_truncated holds exactly the cut-off messages (advice_items). A script has no cut_off field.
EXAMPLE_CUT_OFF = {"tracing_pair": True, "advice_new": False, "advice_rerun": False, "advice_rerun_truncated": True}
# What an example's text may not show a physician (the blinding section of docs/verification_protocol.md): a model
# or vendor name, the study's batch, run or item ids, and a decimal number or a percentage, the forms in which a
# measured value is written. An item's display, built from the texts a physician rates, carries none of the study's
# own; an example is written by hand, so its text is checked, more strictly than an item's could be (a patient's
# message may hold a decimal number). Urgency levels are read from the questions data (example_answer_levels).
#
# The model and vendor names are those of every model registry the engine has: scripts/logits_eval.py HF_IDS (and
# scripts/activation_patch.py's), medlang_circuits/graph_client.py MODEL_REGISTRY, medlang_circuits/evaluate_models.py
# PRICING, LEGACY_ALIASES and DEFAULT_MODELS, scripts/pab_probe_cost.py's price tables and presets,
# data/advice_providers.json (every vendor block, consumer product and model id it names), the Petri lane's targets
# and judges (it prices a target from the two tables above, and data/petri records the landed ones) and its park
# target, plus the two services the study calls (Neuronpedia, OpenRouter). tests/test_export_verification_tasks.py
# reads every one of those registries and fails when an id in any of them is not matched here, so a model added to a
# registry must be named here too. A distinctive name is matched case-insensitively anywhere in a string, so a name
# inside another (BioMistral, MedGemma, OpenMeditron, ChatGPT, Qwen3) is found; Codex review of PR #88 found the
# first version's word-boundary pattern let those through.
EXAMPLE_MODEL_SUBSTRINGS = ("gemma", "qwen", "llama", "olmo", "mistral", "meditron", "apertus", "claude", "openai",
                            "gpt", "gemini", "grok", "deepseek", "kimi", "moonshot", "xai", "copilot", "allenai", "epfl",
                            "mockllm", "neuronpedia", "openrouter")
# Names that are ordinary words, or sit inside ordinary words, get an explicit pattern instead, so that the word in
# the right column is not refused (measured against the system word list and every short string in the study's data).
EXAMPLE_MODEL_PATTERNS = (
    r"(?<![a-z])anthropic",                  # the vendor, not philanthropic, misanthropic
    r"\b(?:opus|sonnet|haiku|fable)\b",      # Claude tiers named alone; inside octopus, affable
    r"\bmuse[\s_-]*spark\b",                 # meta/muse-spark-1.3; both halves are ordinary words (amused, sparkle)
    r"\bmeta(?:[\s_-]?ai\b|/|[\s_-]llama)",  # Meta AI, meta/<model>, meta-llama; not metal, metaphor
    r"\bgoogle\b",                           # the vendor, not googled
    r"\bnova[\s_-](?:micro|lite|pro|premier)\b",  # Amazon Nova (nova-lite-bedrock); not supernova, Casanova
)
EXAMPLE_MODEL_NAMES = re.compile("|".join([*map(re.escape, EXAMPLE_MODEL_SUBSTRINGS), *EXAMPLE_MODEL_PATTERNS]),
                                 re.I)
# The study's ids, by the shapes they take in the data (Codex review of PR #88 found the first pattern, a list of batch
# prefixes, let the Petri seed and scenario ids through). tests/test_export_verification_tasks.py reads every id of
# every source below and fails when one is not matched.
EXAMPLE_IDS = re.compile("|".join((
    # an underscore joining two letters or digits: every stamped batch, run and bundle id and its index
    # (pairs_<stamp>#17, advman_<date>#01, vtasks_<stamp>, pilot_v2_<date>, run_<number>_1, the data/simulated and
    # data/advice file stems), a bundle item id (vt_<hex>), a pilot row, call or cell id (A__<cell>__L01) and a Petri
    # text key (t01_clinical); patient text has no underscores
    r"[^\W_]_+[^\W_]",
    r"\bpw-petri-",                                            # Petri seed ids (docs/framework/petri_seeds*.json)
    r"\b(?:synthetic-h|w)\d+[a-z]?(?:-[a-z0-9]+)*-\d{4}\b",   # Petri scenario ids (w3-<slug>-0001, synthetic-h1-0001)
    r"\br\d{3}\b",                                            # pilot review ids (review_map.json: r001)
)), re.I)
# The study's method vocabulary, which an example may not show (the blinding section of docs/verification_protocol.md
# says physicians never see method labels; Codex review of PR #88 found examples were not checked for it). The terms
# are the study's own: the method fields of the site payload (PAYLOAD_SCENARIO_KEYS) and of the trace summaries, the
# names of the push-to-run lanes (fire_trigger.TRIGGERS), and the method names AGENTS.md uses (attribution graphs,
# transcoders, next-token probabilities, the holdout and Tier A/B; Neuronpedia is refused as a service name, with the
# model names). tests/test_export_verification_tasks.py reads those
# fields and lane names and fails when one is neither matched here nor listed there as bookkeeping or an ordinary word.
# A term that is also an ordinary word is matched only in its method phrase: steering (feature steering, steering
# boost; not the steering wheel), selection (selection rule, selected by; not a selection of), patching (activation
# patching; not patching a tyre), circuit (circuit tracing or diff; not circuit training), petri (not a petri dish),
# spread, top, target, model and set only in the payload's and summaries' own phrases.
EXAMPLE_METHOD_TERMS = re.compile("|".join((
    r"\blogit", r"transcoder", r"\battribution", r"\bprobabilit", r"\bj-?lens\b", r"\bjacobian\b",
    r"\bnext[\s_-]+token", r"\bhold[\s_-]?out\b", r"\btier[\s_-]+[ab]\b",
    r"\bcircuit[\s_-]*(?:trac|diff)", r"\blanguage[\s_-]+penalt", r"\bprob[\s_-]+(?:clinical|patient)\b",
    r"\bclinical[\s_-]+mass\b", r"\bdepth[\s_-]+(?:class|readout|probe)", r"\banchor[\s_-]+fallback",
    r"\btarget[\s_-]+tokens?\b", r"\btop[\s_-]+(?:clinical|patient|path)\b", r"\bspread[\s_-]+(?:clinical|patient)\b",
    r"\bpredictive[\s_-]+spread", r"\berror[\s_-]+share", r"\bforced[\s_-]+targets?\b", r"\bmitigation[\s_-]+recovery",
    r"\btranslation[\s_-]+(?:method|model)", r"\bgraph[\s_-]+models?\b", r"\bsource[\s_-]+sets?\b",
    r"\bscreen(?:ing)?[\s_-]+targets?\b", r"\bgeneration[\s_-]+params?\b", r"\bbaseline[\s_-]+(?:prompt|probabilit)",
    r"\bregister[\s_-]+(?:shift|gap|contrast)", r"\bvariety[\s_-]+shift", r"\bactivation[\s_-]+patch",
    r"\bpatching[\s_-]+grid", r"\bsteer(?:ing|ed)[\s_-]+(?:boost|vector|feature|result|experiment)s?\b",
    r"\b(?:causal|feature|activation)[\s_-]+steer", r"\bselection[\s_-]+(?:rule|heuristic|criteri|method)",
    r"\bselected[\s_-]+by\b", r"\bscenario[\s_-]+generation", r"\bmodel[\s_-]+evaluation", r"\barchive[\s_-]+renders?\b",
    r"\badvice[\s_-]+eval", r"\bpetri\b(?![\s_-]+dish)", r"\bpab[\s_-]+probe",
)), re.I)

# A measured value as it is written: a decimal with or without its leading digit (0.43, .43, -.43; not an ellipsis
# before a number), a percent sign, or a percentage in words (percent, per cent, percentage, pct). Codex review of PR
# #88 found the first version, digit-dot-digit and the sign only, let the leading-dot and word forms through.
EXAMPLE_MEASURED = re.compile(r"\d[.,]\d|(?<![\w.])\.\d|%|\bper[\s-]?cent|\bpct\b", re.I)

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
        # each path is read and recorded once, under the role it was first read for; a later read reuses the bytes
        # (Gemini review of PR #88: a previous bundle that is also a committed bundle was listed twice)
        self._read: dict[Path, bytes] = {}
        # every study text the inputs hold, selected for the bundle or not, with where it is (ids only): an example may
        # not repeat or nearly repeat one (check_example_copies)
        self.study_texts: list[tuple[str, str]] = []

    def study(self, text: Any, where: str) -> None:
        if isinstance(text, str) and text.strip():
            self.study_texts.append((text, where))

    def read_bytes(self, path: Path, role: str, label: str | None = None) -> bytes:
        key = path.resolve()
        if key in self._read:
            return self._read[key]
        if not path.is_file():
            refuse("missing_input", f"{role}: {path} does not exist or is not a file")
        try:
            data = path.read_bytes()
        except OSError as exc:
            refuse("unreadable_input", f"{role}: cannot read {path} ({type(exc).__name__})")
        self.sources.append({"path": label or logical_path(path), "role": role, "sha256": sha256_bytes(data)})
        self._read[key] = data
        return data

    def read_json(self, path: Path, role: str, label: str | None = None) -> tuple[Any, str]:
        data = self.read_bytes(path, role, label)
        try:
            return json.loads(data.decode("utf-8")), sha256_bytes(data)
        except (UnicodeDecodeError, ValueError) as exc:
            refuse("unreadable_input", f"{role}: {path} is not UTF-8 JSON ({type(exc).__name__})")


def parse_jsonl(data: bytes, path: Path, role: str) -> list[dict]:
    """The JSON objects of a JSONL file's bytes, blank lines skipped; anything else is a named refusal."""
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
    return rows


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
    instructions = check_keys(doc["instructions"], INSTRUCTIONS_KEYS, f"{where} instructions")
    families = instructions.get("families")
    if not isinstance(families, dict) or sorted(families) != sorted(FAMILIES):
        refuse("questions_mismatch", f"{where}: instructions.families must name exactly {list(FAMILIES)}")
    validate_examples(doc, where)
    return doc


def example_answer_levels(doc: dict) -> list[tuple[str, list[str]]]:
    """The urgency levels a proposed tier is one of, one entry per option, as (its label, the terms an example could
    write it as): for every option of every scale a reveal-locked question of the exporter's question sets uses, its
    label, its value (the tier a reveal stores), and the value with an underscore written as a space or a hyphen. Read
    from the questions data, so no level is written in this file. An example whose text names one would show a
    physician an answer; Codex review of PR #88 found that checking labels alone let the bare values (the tier ids)
    through. One entry per option, so a refusal names an option once (Gemini review of PR #88)."""
    scales = {q["scale"] for set_name in QUESTION_SETS for q in doc["question_sets"][set_name]["questions"]
              if q.get("locks_on_reveal")}
    levels: dict[str, set[str]] = {}
    for s in sorted(scales):
        for option in doc["scales"][s].get("options", []):
            terms: set[str] = set()
            for field in ("label", "value"):
                term = option.get(field)
                if isinstance(term, str) and term.strip():
                    terms |= {term, term.replace("_", " "), term.replace("_", "-")}
            if terms:
                name = option.get("label") if isinstance(option.get("label"), str) else str(option.get("value"))
                levels.setdefault(name, set()).update(terms)
    return [(name, sorted(terms)) for name, terms in levels.items()]


# An answer stated outright: "rating/score/answer/verdict" with a linking verb, "of" ("a rating of 4"; Gemini review of
# PR #88, round 3) or a sign, or "rated/scored/scores", before an answer. "Answer yes or no" (no link) describes the
# task and is not one.
_ASSERTION_LEAD = (r"\b(?:(?:rating|score|answer|verdict)\s*(?:is|was|would\s+be|should\s+be|will\s+be|of|=|:)"
                   r"|(?:rated|scored|scores)(?:\s+(?:as|at))?"
                   # a rating verb with its object, a pronoun or a determiner and up to eight words (of, in and for
                   # phrases among them), before the answer ("I rated it 4", "I rate this example 4", "I rated the first
                   # version of the conversation 4"; Codex review of PR #88). The object holds no copula or other verb
                   # that ends a noun phrase, so a noun "rate" followed by its clause ("the exchange rate the whole week
                   # was 4") is not read as one.
                   r"|(?:rate|rates|rated|rating|score|scores|scored|scoring)\s+"
                   # (quantifiers count as determiners, and "both" and "all" stand alone too: "I rate both messages 4",
                   # "rated all three versions 2"; Codex review of PR #88)
                   r"(?:it|this|that|them|these|those|both|all|(?:the|this|that|these|those|each|every|my|our|your|"
                   r"both|all|either|neither|some|any|several|two|three|four|five|six|seven|eight|nine|ten)"
                   r"(?:\s+(?!(?:is|are|was|were|be|been|went|got)\b)[\w'-]+){1,8}?)\s+(?:(?:as|at|a|an)\s+)?)\s*")


def _label_pattern(label: str) -> str:
    """A label as a phrase: flexible whitespace, and a numbered label's separator ("4 - Likely") as any dash or a colon."""
    words = [re.escape(w) for w in label.split()]
    return r"\s*".join(w if w not in ("\\-", "-") else r"[-\u2013\u2014:]" for w in words)


def example_answer_rules(doc: dict, set_name: str) -> list[tuple[str, re.Pattern]]:
    """(what it shows, pattern) for the answers to the questions of question set ``set_name``, read from every scale
    those questions use, abstentions included (Codex review of PR #88: only the reveal's scale was read). Where the line
    is drawn: a label is refused as a phrase when it is a statement of its own, four or more words or a numbered
    label ("4 - Likely", "I could hear this from a real patient", "Entirely plausible; I have seen this"); a shorter
    label ("Likely", "Possible", "Yes", "None of them", "Can't tell") and every answer value are refused only inside a
    rating statement ("the rating is 4", "rated Likely", "the answer is yes"), and an ordinal number scale's values as
    "N out of M" with M its highest value. Refusing the short labels as bare words would refuse a caption that says
    what a physician judges ("how likely a real patient is ...")."""
    rules: list[tuple[str, re.Pattern]] = []
    stated: set[str] = set()
    for q in doc["question_sets"][set_name]["questions"]:
        scale = doc["scales"][q["scale"]]
        options = list(scale.get("options", [])) + ([scale["abstain"]] if scale.get("abstain") else [])
        for option in options:
            label, value = option.get("label"), option.get("value")
            if isinstance(value, (int, str)) and not isinstance(value, bool) and str(value).strip():
                stated |= {str(value), str(value).replace("_", " "), str(value).replace("_", "-")}
            if not isinstance(label, str) or not label.strip():
                continue
            stated.add(label)
            numbered = re.fullmatch(r"\s*(\d+)\s*-\s*(.+)", label)
            if numbered:
                stated.add(numbered.group(2))
            if numbered or len(re.findall(r"[^\W_]+", label)) >= 4:
                # one rule per option: a numbered label, and its text when that is a statement too
                forms = [label] + ([numbered.group(2)] if numbered
                                   and len(re.findall(r"[^\W_]+", numbered.group(2))) >= 4 else [])
                rules.append((f"the answer label {label!r}",
                              re.compile("|".join(rf"(?<!\w){_label_pattern(f)}(?!\w)" for f in forms), re.I)))
        values = [o.get("value") for o in scale.get("options", [])]
        if scale.get("type") == "ordinal" and values and all(isinstance(v, int) and not isinstance(v, bool)
                                                             for v in values):
            top = max(values)
            rules.append((f"a rating out of {top}",
                          re.compile(rf"\b(?:{'|'.join(map(str, values))})\s*(?:out\s+of|/)\s*{top}\b", re.I)))
    alternatives = "|".join(_label_pattern(s) for s in sorted(stated, key=len, reverse=True))
    rules.append(("a rating or answer stated outright", re.compile(rf"{_ASSERTION_LEAD}(?:{alternatives})(?!\w)", re.I)))
    return list(dict(rules).items())                    # one rule per description (questions can share a scale)


# Copies of study items. A text is normalised (lower case, every run of characters that are not letters or digits read
# as one space) and compared exactly. Beyond that, an example text and a study text are compared by their word 4-grams
# in both directions, and the larger share decides, against COPY_SHARE (half):
# - the share of the example text's 4-grams that occur in one study text (the example text has at least
#   COPY_MIN_GRAMS of them): a near copy, such as a copied sentence with a word changed;
# - the share of the study text's 4-grams that occur in the example text (Codex review of PR #88: a whole study prompt
#   with novel words around it passed): counted for a study text of at least COPY_CONTAIN_MIN_GRAMS 4-grams, a
#   stimulus rather than a stock phrase, and for any study text of at least COPY_MIN_GRAMS contained whole.
# Measured on the real inputs: the three draft examples of questions 1.2-draft share at most a quarter of their own
# 4-grams with any study text, and at most a ninth of any study text of COPY_CONTAIN_MIN_GRAMS (ten, a text of
# thirteen words) or more. Shorter study texts count only when contained whole, because a stock question ("is there
# anything else I should ...") gives the drafts three of the four 4-grams of a seven-word seed turn and three of the
# eight of an eleven-word one (38%, too close to half).
# A study text with fewer than COPY_MIN_GRAMS 4-grams (under seven words) has no gram share to speak of, so it is a
# copy when its words occur in the example text as one run, if it has at least COPY_CONTAIN_MIN_WORDS words (Codex review
# of PR #88: a five-word turn of vt_f51de47d1933 pasted inside longer text passed). Measured on the real inputs: 39
# study texts have four to six words and none fewer; the drafts contain none of them; the one four-word text is a stock
# reply ("ok thanks anything else"), so four-word texts are compared exactly only. Two five-word stock questions
# ("anything else I should know", "anything else that might help") would be refused if an example pasted them whole.
COPY_GRAM = 4
COPY_MIN_GRAMS = 4
COPY_CONTAIN_MIN_GRAMS = 10
COPY_CONTAIN_MIN_WORDS = 5
COPY_SHARE = 0.5
COMMITTED_BUNDLES_DIR = REPO_ROOT / "data" / "verification"


def normalised_words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold())


def word_grams(text: str) -> set[tuple[str, ...]]:
    words = normalised_words(text)
    return {tuple(words[i:i + COPY_GRAM]) for i in range(len(words) - COPY_GRAM + 1)}


class StudyTextIndex:
    """The study texts an example may not copy: their normalised forms, and an index from each word 4-gram to the
    texts holding it."""

    def __init__(self, texts: list[tuple[str, str]]) -> None:
        self.where: list[str] = []
        self.size: list[int] = []
        self.exact: dict[str, str] = {}
        self.short: dict[str, str] = {}
        self.grams: dict[tuple[str, ...], set[int]] = {}
        for text, where in texts:
            n = len(self.where)
            self.where.append(where)
            grams = word_grams(text)
            self.size.append(len(grams))
            words = normalised_words(text)
            self.exact.setdefault(" ".join(words), where)
            if COPY_CONTAIN_MIN_WORDS <= len(words) and len(grams) < COPY_MIN_GRAMS:
                self.short.setdefault(" ".join(words), where)
            for gram in grams:
                self.grams.setdefault(gram, set()).add(n)

    def copy_of(self, text: str) -> tuple[str, float, str, str] | None:
        """(how, the deciding share, where, whose 4-grams the share is of) for a copy, else None: "repeats" for the
        same normalised text, "nearly repeats" when the example text's share decides, "contains" when the study
        text's does."""
        key = " ".join(normalised_words(text))
        if key and key in self.exact:
            return "repeats", 1.0, self.exact[key], "its"
        padded = f" {key} "
        for run, where in self.short.items():
            if f" {run} " in padded:
                return "contains", 1.0, where, "the study text's"
        share, where, whose = self.overlap(text)
        if share < COPY_SHARE:
            return None
        return ("nearly repeats" if whose == "its" else "contains"), share, where or "", whose

    def overlap(self, text: str) -> tuple[float, str | None, str]:
        """The largest share, over the study texts, of the larger of the two shares a study text and this text have
        in common (see COPY_SHARE), that text's place, and whose 4-grams the share is of ("its", the example
        text's, or "the study text's"); (0, None, "its") when no study text shares a 4-gram."""
        grams = word_grams(text)
        hits: Counter = Counter(n for gram in grams for n in self.grams.get(gram, ()))
        best: tuple[float, str | None, str] = (0.0, None, "its")
        for n, count in sorted(hits.items()):
            if len(grams) >= COPY_MIN_GRAMS and count / len(grams) > best[0]:
                best = (count / len(grams), self.where[n], "its")
            size = self.size[n]
            if (size >= COPY_CONTAIN_MIN_GRAMS or (size >= COPY_MIN_GRAMS and count == size)) and count / size > best[0]:
                best = (count / size, self.where[n], "the study text's")
        return best


def study_payload(inp: "Inputs", site: Path) -> None:
    """Add every prompt of the published payload to the study texts, whether or not main-study pairs are selected
    (Codex review of PR #88: with --main-pairs 0 the payload was never read, so an example copied from a published
    row passed). The payload is read once (Inputs reuses the bytes main_items read)."""
    payload, _ = inp.read_json(site / SITE_PAYLOAD, "published site payload", SITE_LABEL)
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
    if not isinstance(scenarios, list):
        refuse("bad_input", f"{site / SITE_PAYLOAD} has no scenarios list")
    for n, s in enumerate(scenarios, 1):
        # the same checks main_items makes, so a malformed row is refused by name, never skipped (Codex review of
        # PR #88: with --main-pairs 0 this is the payload's only reader)
        check_keys(s, PAYLOAD_SCENARIO_KEYS, f"payload scenario {n}", ("batch", "batch_index", "clinical_prompt",
                                                                     "patient_prompt", "models"))
        for side in ("clinical_prompt", "patient_prompt"):
            inp.study(need_str(s[side], f"payload scenario {n} {side}"), f"payload row {s['batch']}#{s['batch_index']}")


def check_example_copies(inp: "Inputs", examples: list[dict]) -> None:
    """Refuse an example whose label, caption, or any sentence, message or turn (copy_texts) repeats, nearly repeats or
    contains a study text
    (Codex review of PR #88: a copied
    item display passed every other check, and a physician would rate the same stimulus after seeing it as an example).
    The study texts are every text the inputs hold, selected for this bundle or not (Inputs.study_texts; every item
    of this bundle is built from them; the payload's are added by study_payload whether or not main pairs are), and the item displays of every committed bundle in data/verification, which
    are read for this and recorded in sources. Messages name the example and the place, never text."""
    texts = list(inp.study_texts)
    for path in sorted(COMMITTED_BUNDLES_DIR.glob("tasks_*.json")):
        bundle, _ = inp.read_json(path, "committed bundle (an example may not copy its items)")
        for item in bundle.get("items", []) if isinstance(bundle, dict) else []:
            texts += [(t, f"item {item.get('item_id')} of {path.name}") for t in copy_texts(item.get("display"))]
    index = StudyTextIndex(texts)
    found = []
    for n, example in enumerate(examples):
        # the label and caption as well as the display's sentences, messages and turns (Codex review of PR #88)
        for text in [example["label"], example["caption"], *copy_texts(example["display"])]:
            copy = index.copy_of(text)
            if copy:
                found.append(f"instructions.examples[{n}] ({example['family']}) {copy[0]} {copy[2]} "
                             f"({copy[1]:.0%} of {copy[3]} word 4-grams)")
                break
    if found:
        refuse("example_copies_item", "an example is a study item, or nearly one, so a physician would see it before "
                                      "rating it: " + "; ".join(found) + ". Examples are invented")


def copy_texts(display: Any) -> list[str]:
    """The texts of a display the copy check compares: its sentences, messages and turns. A pair's next word is left
    out (Gemini review of PR #88: as a one-word study text it made any example whose next word was a committed pair's
    target "repeat" that item); next words have their own rules (next_word_ok and the blinding checks)."""
    if isinstance(display, dict):
        return [s for k, v in display.items() if k not in NOT_SHOWN_DISPLAY_FIELDS | {"next_word"}
                for s in item_shown_texts(v)]
    return item_shown_texts(display)


def item_shown_texts(display: Any) -> list[str]:
    """The texts of an item display a physician reads (not its kind, arm ids or same_as; NOT_SHOWN_DISPLAY_FIELDS)."""
    if isinstance(display, str):
        return [display]
    if isinstance(display, dict):
        return [s for k, v in display.items() if k not in NOT_SHOWN_DISPLAY_FIELDS for s in item_shown_texts(v)]
    if isinstance(display, list):
        return [s for v in display for s in item_shown_texts(v)]
    return []


# A caption says what a physician judges; it never evaluates the example. An evaluation is a declarative clause that
# applies an answer to the example: a subject that is the example ("the conversation", "this message", "it"), a
# copula, an optional "not" and intensifiers, then a predicate read from the questions data (example_predicates).
# Codex review of PR #88 asked whether "The conversation is entirely plausible" should pass; the owner adopted Gemini's
# answer that it should not, while a task description must: a clause under "whether", "if" or "how", or a sentence
# that opens with an imperative ("Judge whether the conversation is plausible", "Say how likely it is").
_EXAMPLE_SUBJECT = (r"(?:(?:the|this|that|these|those|each|every|its|their)\s+(?:[a-z-]+\s+){0,2}?"
                    r"(?:conversations?|scripts?|scenarios?|situations?|stor(?:y|ies)|examples?|items?|pairs?|"
                    r"sentences?|messages?|versions?|wordings?|course(?:\s+of\s+events)?|events|cases?|texts?|"
                    r"exchanges?|turns?|ones?)|it|this|that|they|these|those)")
_EXAMPLE_COPULA = r"(?:is|are|was|were|seems?|appears?|sounds?|looks?|reads?|feels?)(?:\s+to\s+be)?"
_INTENSIFIERS = ("entirely", "completely", "wholly", "very", "quite", "fairly", "highly", "mostly", "somewhat",
                 "clearly", "perfectly", "totally", "rather", "so", "as", "really", "medically", "definitely",
                 "probably")
# The verbs that open a task directive, and only those (Gemini review of PR #88, round 3): "note", "consider", "ask",
# "read", "look" and "think" also introduce an assertion ("Note that the conversation is plausible"), so they are not
# here, and a directive followed by "that" introduces one too ("Say that this message is realistic") and exempts
# nothing.
_TASK_SENTENCE_OPENERS = ("judge", "rate", "say", "decide", "assess", "determine", "check", "choose", "tell")


def example_predicates(doc: dict, set_name: str) -> list[str]:
    """What an evaluation of an example of question set set_name could call it, read from the questions data: the
    label of every option of every ordinal scale the set's questions use (an ordinal scale rates a degree, so its
    labels are evaluations; a nominal scale's, such as a message number, and an abstention are not), without its
    number ("4 - Likely" gives "Likely") or what follows a ";" or "(", when that is three words or fewer, and its last
    word when it opens with an intensifier ("Entirely plausible" gives "plausible"); the last word of each of the
    set's yes/no questions (a nominal scale of two options) that asks "is the ... X?" ("coherent"), and what each of
    those questions measures, after the last colon of its measures field ("medically coherent", "coherent"); and the qualities the welcome text says physicians
    judge ("whether each one is realistic and checkable")."""
    found: set[str] = set()
    for q in doc["question_sets"][set_name]["questions"]:
        scale = doc["scales"][q["scale"]]
        for option in scale.get("options", []) if scale.get("type") == "ordinal" else []:
            label = option.get("label")
            if not isinstance(label, str):
                continue
            core = re.split(r"[;(]", re.sub(r"^\s*\d+\s*-\s*", "", label))[0].strip()
            words = re.findall(r"[^\W_][\w'-]*", core)
            if 0 < len(words) <= 3:
                found.add(core)
                if len(words) > 1 and words[0].lower() in _INTENSIFIERS:
                    found.add(words[-1])
        if scale.get("type") == "nominal" and len(scale.get("options", [])) == 2:
            asks = re.search(r"\bis the\b[^?]*\b([a-z]+)\?\s*$", q.get("text", ""), re.I)
            if asks:
                found.add(asks.group(1))
            # what the question measures, after its last colon, without a parenthesis ("verifiability: medically
            # coherent"): the same words for every set however its question is worded (Gemini review of PR #88,
            # round 3: tracing_pair asks "Does the sentence make medical sense?")
            measures = q.get("measures")
            if isinstance(measures, str) and ":" in measures:
                phrase = re.sub(r"\(.*?\)", "", measures.rsplit(":", 1)[1]).strip()
                words = re.findall(r"[^\W_][\w'-]*", phrase)
                if 0 < len(words) <= 3:
                    found.add(phrase)
                    if len(words) > 1 and words[0].lower() in _INTENSIFIERS:
                        found.add(words[-1])
    for line in (doc.get("instructions") or {}).get("welcome", []):
        for qualities in re.findall(r"\bwhether each one is ([a-z]+(?: and [a-z]+)*)", line, re.I):
            found |= set(qualities.split(" and "))
    return sorted({p.lower() for p in found}, key=lambda p: (-len(p), p))


# Where one clause ends and the next begins: sentence punctuation, a comma, a coordinating or contrasting conjunction,
# or a subordinating one (because, since, as, so). Each clause is checked on its own, so a directive or a "whether" in
# one clause does not exempt an evaluation in the next (Gemini review of PR #88, round 3: "Judge whether the
# conversation is plausible, but this message is realistic" passed; Codex review: "... agree because this conversation
# is entirely plausible" passed). "as" and "so" are also degree words ("is as realistic as", "is so realistic"), so
# they end a clause only when the word before them is not a copula, "not" or an intensifier (_clauses).
_CLAUSE_BREAK = re.compile(r"[.;:!?,]+|\b(?:but|and|yet|while|although|however|because|since|as|so)\b", re.I)
_DEGREE_AFTER = {"is", "are", "was", "were", "be", "seem", "seems", "appear", "appears", "sound", "sounds", "look",
                 "looks", "read", "reads", "feel", "feels", "not"}


def _clauses(text: str) -> list[tuple[str, bool]]:
    """The clauses of a text (_CLAUSE_BREAK), keeping "as" and "so" inside a clause where they are degree words, each
    with whether it opens a sentence (the text's start, or after . ; : ! or ?)."""
    parts, start, opens = [], 0, True
    for m in _CLAUSE_BREAK.finditer(text):
        if m.group(0).lower() in ("as", "so"):
            before = re.findall(r"[a-z']+", text[start:m.start()].lower())
            if before and (before[-1] in _DEGREE_AFTER or before[-1] in _INTENSIFIERS):
                continue
        parts.append((text[start:m.start()], opens))
        opens = any(c in ".;:!?" for c in m.group(0))
        start = m.end()
    return parts + [(text[start:], opens)]


def example_evaluations(text: str, predicates: list[str]) -> list[str]:
    """The predicates a text applies to the example in an evaluation (see _EXAMPLE_SUBJECT), clause by clause
    (_CLAUSE_BREAK), skipping a clause under "whether", "if" or "how" and a clause that opens with an imperative."""
    if not predicates:
        return []
    pattern = re.compile(rf"\b{_EXAMPLE_SUBJECT}\s+{_EXAMPLE_COPULA}\s+(?:not\s+)?(?:(?:{'|'.join(_INTENSIFIERS)})\s+)*"
                         rf"(?P<pred>{'|'.join(_label_pattern(p) for p in predicates)})(?!\w)", re.I)
    # a clause that opens with a relative "which" ("the versions, which are entirely plausible") evaluates its noun
    relative = re.compile(rf"^\s*which\s+{_EXAMPLE_COPULA}\s+(?:not\s+)?(?:(?:{'|'.join(_INTENSIFIERS)})\s+)*"
                          rf"(?P<pred>{'|'.join(_label_pattern(p) for p in predicates)})(?!\w)", re.I)
    # A clause with no subject and copula of its own shares those of the nearest clause before it in the same sentence
    # ("This message is brief but medically coherent"; Codex review of PR #88), and that clause's exemption, so "Judge
    # whether the message is brief and medically coherent" stays a task directive.
    head_pattern = re.compile(rf"(?P<subject>\b{_EXAMPLE_SUBJECT}|^\s*which)\s+{_EXAMPLE_COPULA}\b", re.I)
    # a continuation that repeats the copula ("This message is brief but is medically coherent") takes the subject only
    own_copula = re.compile(rf"\s*(?:not\s+)?{_EXAMPLE_COPULA}\b", re.I)
    question = re.compile(r"\b(?:whether|if|how|which|what)\b", re.I)
    out: list[str] = []
    head: str | None = None
    head_subject = ""
    head_exempt = False
    for clause, opens in _clauses(text):
        if opens:
            head, head_exempt = None, False
        opener = re.match(r"\s*([a-z]+)(\s+that\b)?", clause, re.I)
        directive = bool(opener and opener.group(1).lower() in _TASK_SENTENCE_OPENERS and not opener.group(2))
        own = head_pattern.search(clause)
        if own:
            head, head_subject = own.group(0).strip(), own.group("subject").strip()
            head_exempt = directive or bool(question.search(clause[:own.start()]))
            checked, exempt = clause, directive
        elif head is not None:
            carried = head_subject if own_copula.match(clause) else head
            checked, exempt = f"{carried} {clause.strip()}", directive or head_exempt
        else:
            checked, exempt = clause, directive
        if exempt:
            continue
        found = relative.match(checked)
        if found:
            out.append(found.group("pred"))
            continue
        for m in pattern.finditer(checked):
            # a question word before the evaluation makes it what the physician is asked, not a claim; "which" and
            # "what" are question words here because a relative "which" opens its own clause, after a comma
            if not question.search(checked[:m.start()]):
                out.append(m.group("pred"))
    return out


def example_texts(example: dict) -> list[str]:
    """Every string an example shows a physician: its label, its caption and every string of its display."""
    return [example["label"], example["caption"], *strings_in(example["display"])]


# Display fields that hold the contract's own vocabulary, not text a physician reads: the display kind, and a
# script's arm ids, which the app replaces with Version A/B/C and same_as names. Both are snake_case
# (pair_sentence, lay_careful), so the id check skips them.
NOT_SHOWN_DISPLAY_FIELDS = frozenset({"kind", "arm", "same_as"})


def example_shown_texts(example: dict) -> list[str]:
    """The text of an example a physician reads: its label, its caption, and its display's strings except the
    display kind and the arm ids (NOT_SHOWN_DISPLAY_FIELDS)."""
    return [example["label"], example["caption"], *item_shown_texts(example["display"])]


def _example_display_problem(display: Any, set_name: str) -> str | None:
    """How an example's display departs from the display every item of question set ``set_name`` has, or None. The
    rules are the ones the item builders follow, so the app renders an example exactly as it renders an item."""
    kind = DISPLAY_KIND[QUESTION_SETS[set_name]]
    if not isinstance(display, dict):
        return "display is not an object"
    if display.get("kind") != kind:
        return f"display kind is {display.get('kind')!r}; an item of question set {set_name!r} has {kind!r}"
    if set(display) != DISPLAY_FIELDS[kind]:
        return (f"display fields are {sorted(display)}; a {kind} display has exactly {sorted(DISPLAY_FIELDS[kind])} "
                "(an example carries no answer, reveal, tier or provenance)")

    def text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    if kind == "pair_sentence":
        for side in ("clinical", "patient"):
            part = display[side]
            if not isinstance(part, dict) or set(part) != {"text", "highlight"} or not text(part["text"]):
                return f"display.{side} is not an object of exactly a non-empty text and its highlight"
        expected = diff_spans(display["clinical"]["text"], display["patient"]["text"])
        if None in expected:
            return "the two sentences do not each have words where they differ, so nothing would be marked"
        if canonical([display["clinical"]["highlight"], display["patient"]["highlight"]]) != canonical(list(expected)):
            return ("a highlight is not the span where the two sentences differ, widened to whole words, in UTF-16 "
                    f"code units (the exporter gives {list(expected)} for these sentences)")
        if not next_word_ok(display["next_word"]):
            return "next_word is not one lowercase word (the version-2 next_word rule an item's next word follows)"
    elif kind == "message_pair":
        if not (text(display["clinical_message"]) and text(display["patient_message"])):
            return "a message is not a non-empty string"
        if display["clinical_message"] == display["patient_message"]:
            return "the two messages are the same text"
    else:
        n_turns, arms = display["n_turns"], display["arms"]
        if isinstance(n_turns, bool) or not isinstance(n_turns, int) or n_turns < 1:
            return "n_turns is not a positive integer"
        if not isinstance(arms, list) or len(arms) < 2:
            return "arms is not a list of at least two versions"
        seen: list[dict] = []
        for arm in arms:
            if not isinstance(arm, dict) or set(arm) != {"arm", "turns"} or not text(arm["arm"]):
                return "an arm is not an object of exactly a non-empty arm id and its turns"
            if any(a["arm"] == arm["arm"] for a in seen):
                return f"arm {arm['arm']!r} appears twice"
            if not isinstance(arm["turns"], list) or len(arm["turns"]) != n_turns:
                return f"arm {arm['arm']!r}: its turns are not a list of n_turns ({n_turns}) entries"
            for t, turn in enumerate(arm["turns"]):
                if not isinstance(turn, dict) or set(turn) != {"text", "same_as"} or not text(turn["text"]):
                    return f"arm {arm['arm']!r} turn {t + 1} is not an object of exactly a non-empty text and same_as"
                same_as = next((a["arm"] for a in seen if a["turns"][t]["text"] == turn["text"]), None)
                if canonical(turn["same_as"]) != canonical(same_as):
                    return (f"arm {arm['arm']!r} turn {t + 1}: same_as is {turn['same_as']!r}; an item names the first "
                            f"earlier arm whose turn is word for word the same ({same_as!r})")
            seen.append(arm)
    if kind != "script" and display["cut_off"] is not EXAMPLE_CUT_OFF[set_name]:
        return f"cut_off is {display['cut_off']!r}; every item of question set {set_name!r} has {EXAMPLE_CUT_OFF[set_name]}"
    return None


def validate_examples(doc: dict, where: str) -> None:
    """Refuse an ``instructions.examples`` the app could not render as it renders an item, or whose text shows a
    model, an id, a measured value or an answer (names only, never text). Absent is valid: a questions file needs no
    examples. The seal scan of example text is build_bundle's (it needs the sealed registry)."""
    instructions = doc["instructions"]
    if "examples" not in instructions:
        return
    examples = instructions["examples"]
    if not isinstance(examples, list) or not examples:
        refuse("bad_example", f"{where}: instructions.examples is not a non-empty list (leave it out for none)")
    answer_levels = example_answer_levels(doc)
    for n, example in enumerate(examples):
        at = f"{where} instructions.examples[{n}]"
        if not isinstance(example, dict):
            refuse("bad_example", f"{at} is not an object")
        fields = set(example)
        if fields != EXAMPLE_KEYS:
            refuse("bad_example", f"{at}: fields {sorted(fields)}; an example has exactly {sorted(EXAMPLE_KEYS)} "
                                  f"(missing {sorted(EXAMPLE_KEYS - fields)}, not allowed {sorted(fields - EXAMPLE_KEYS)}: "
                                  "an example carries no answer, reveal, tier or provenance)")
        family = example["family"]
        if not isinstance(family, str) or family not in QUESTION_SETS:
            refuse("bad_example", f"{at}: family {family!r} is not one of the item question sets "
                                  f"{sorted(QUESTION_SETS)}")
        for field in ("label", "caption"):
            if not isinstance(example[field], str) or not example[field].strip():
                refuse("bad_example", f"{at} ({family}): {field} is not a non-empty string")
        problem = _example_display_problem(example["display"], family)
        if problem:
            refuse("bad_example", f"{at} ({family}): {problem}")
        texts = example_texts(example)
        shown = [what for what, pattern in (("a model or vendor name", EXAMPLE_MODEL_NAMES),
                                            ("a decimal number or a percentage", EXAMPLE_MEASURED))
                 if any(pattern.search(t) for t in texts)]
        if any(EXAMPLE_IDS.search(t) for t in example_shown_texts(example)):
            shown.append("a batch, run, item, seed or scenario id")
        if any(EXAMPLE_METHOD_TERMS.search(t) for t in example_shown_texts(example)):
            shown.append("a method term")
        shown += [f"the urgency level {name!r}" for name, terms in answer_levels
                  if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", t, re.I) for term in terms for t in texts)]
        shown += [what for what, pattern in example_answer_rules(doc, family) if any(pattern.search(t) for t in texts)]
        predicates = example_predicates(doc, family)
        evaluated = sorted({p.lower() for t in (example["label"], example["caption"]) for p in example_evaluations(t, predicates)})
        shown += [f"an evaluation of the example as {p!r}" for p in evaluated]
        if shown:
            refuse("example_not_blind", f"{at} ({family}) shows {', '.join(shown)}; an example shows a physician no "
                                        "model, method, measured value or answer")


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


class PilotRun:
    """One pilot run to export: its id, which rows it contributes, whether each needs a trace result, and the graph
    model whose trace results it reads (None: not named, so the exporter finds the one model that has results)."""

    def __init__(self, run_id: str, all_rows: bool = False, trace_required: bool = True,
                 trace_model: str | None = None) -> None:
        self.run_id = run_id
        self.all_rows = all_rows
        self.trace_required = trace_required
        self.trace_model = trace_model

    @property
    def subset(self) -> str:
        """The provenance label of the run's items (never shown to a rater)."""
        legacy = LEGACY_PILOT_RUNS.get(self.run_id)
        return legacy["subset"] if legacy else PILOT_SUBSET_PREFIX + self.run_id


def pilot_runs_from_args(args: argparse.Namespace) -> list[PilotRun]:
    """The pilot runs named on the command line (the default run when none is), or a named refusal."""
    run_ids = list(args.pilot_run) if args.pilot_run else [DEFAULT_PILOT_RUN]
    for run_id in run_ids:
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            refuse("bad_input", f"--pilot-run {run_id!r} is not a run id: it takes a directory name under "
                                "--pilot-runs-dir, not a path")
    repeated = sorted(k for k, v in Counter(run_ids).items() if v > 1)
    if repeated:
        refuse("bad_input", f"--pilot-run names {repeated} more than once")
    model_pairs = [tuple(pair) for pair in (args.pilot_trace_model or ())]
    model_runs = [run_id for run_id, _ in model_pairs]
    for flag, named in (("--pilot-all-rows", args.pilot_all_rows), ("--pilot-trace-optional",
                                                                    args.pilot_trace_optional),
                        ("--pilot-trace-model", model_runs)):
        stray = sorted(set(named or ()) - set(run_ids))
        if stray:
            refuse("bad_input", f"{flag} names {stray}, which no --pilot-run exports")
    repeated = sorted(k for k, v in Counter(model_runs).items() if v > 1)
    if repeated:
        refuse("bad_input", f"--pilot-trace-model names {repeated} more than once; a run's traces are read for one "
                            "graph model")
    optional = set(args.pilot_trace_optional or ())
    for run_id, model in model_pairs:
        if run_id in optional:
            refuse("bad_input", f"--pilot-trace-model names {run_id}, whose trace results --pilot-trace-optional "
                                "says not to read")
        if not RUN_ID_RE.fullmatch(model) or MODEL_SEPARATOR in model:
            refuse("bad_input", f"--pilot-trace-model {run_id} {model!r}: not a graph model id (a name such as "
                                f"{UNSUFFIXED_TRACE_MODEL}, with no path separator and no {MODEL_SEPARATOR!r})")
    models = dict(model_pairs)
    return [PilotRun(r, all_rows=r in set(args.pilot_all_rows or ()), trace_required=r not in optional,
                     trace_model=models.get(r)) for r in run_ids]


def _run_dir(runs_dir: Path, run_id: str) -> Path:
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        refuse("missing_input", f"pilot run {run_id}: {run_dir} is not a directory")
    return run_dir


def _pairs_file_named_for_run(stem: str, run_id: str) -> bool:
    """The naming rule for a run's trace pairs file: <run id>_<name>.json with <name> not empty, so that a trace
    results folder's name says which run it holds. It is the rule the circuit-trace and logits-eval lanes apply to a
    pilot pairs file under their pilot roots (fire_trigger's pilot_pairs_run_name_problem, PR #85), so a run this
    exporter accepts is one the lane will trace: a bare run id, or the run id followed by anything but "_", is refused
    by both. Run 2's trace/trace_pairs.json predates the rule and keeps its name, since its items' ids are keyed on it
    (LEGACY_PILOT_RUNS)."""
    prefix = run_id + "_"
    if stem.startswith(prefix) and len(stem) > len(prefix):
        return True
    legacy = LEGACY_PILOT_RUNS.get(run_id)
    return legacy is not None and stem == Path(legacy["id_source"]).stem


def check_trace_pairs_files(runs: list[PilotRun], runs_dir: Path) -> None:
    """Refuse, before any trace file is read, a run the circuit-trace lane's pilot root would not trace: a run id that
    is the name of a legacy trace folder (LEGACY_TRACE_FOLDERS), a trace pairs file not named after its run, or one
    whose stem holds the model separator. Every file under every run's trace/ is checked, a run whose traces are
    optional included: its traces may be fired later. Only file names are read here. Two runs' files may share a
    stem: under the per-run layout each run's results are in a folder of its own."""
    legacy_folders = set(LEGACY_TRACE_FOLDERS.values())
    for run in runs:
        if run.run_id in legacy_folders:
            refuse("bad_input", f"pilot run {run.run_id}: the run id is the name of the pilot trace folder "
                                f"pilot/traces/{run.run_id}/, written before 2026-10-05, so the run's own folder "
                                "would sit inside it; the circuit-trace and logits-eval lanes refuse the id "
                                "(fire_trigger's pilot_legacy_run_id_problem, PR #85), so give the run another one")
        run_dir = _run_dir(runs_dir, run.run_id)
        for stem in (p.stem for p in _trace_pairs_candidates(run_dir)):
            if not _pairs_file_named_for_run(stem, run.run_id):
                refuse("bad_input", f"pilot run {run.run_id}: trace pairs file {stem}.json is not named after the "
                                    f"run (its name must be {run.run_id}_<name>.json, as the circuit-trace and "
                                    "logits-eval lanes' pilot roots require before they trace a file, so that a "
                                    "results folder's name says which run it holds); rebuild it with "
                                    "pilot/analysis/trace_pairs.py --out "
                                    f".../trace/{run.run_id}_trace_pairs.json")
            if MODEL_SEPARATOR in stem:
                refuse("bad_input", f"pilot run {run.run_id}: trace pairs file {stem}.json holds "
                                    f"{MODEL_SEPARATOR!r}, which the circuit-trace lane puts between a stem and a "
                                    "graph model in a results directory's name, so its directory could be read as "
                                    "another file's results for another model")


def _results_dir(base: Path, model: str) -> Path:
    """Where the circuit-trace lane's pilot root writes one pairs file's results for one graph model, given the
    model-free directory ``base`` (<root>/<run id>/<stem>, or a legacy <root>/<stem>)."""
    return base if model == UNSUFFIXED_TRACE_MODEL else base.with_name(f"{base.name}{MODEL_SEPARATOR}{model}")


def _results_found(base: Path) -> list[tuple[str, Path]]:
    """(graph model, directory) for each of <base>/ (gemma-2-2b) and <base>__<model>/ (that model) that holds a
    batch_summary*.json; each directory counts, so no entry hides another."""
    found = []
    for d in [base] + sorted(base.parent.glob(f"{glob.escape(base.name)}{MODEL_SEPARATOR}*")):
        if d.is_dir() and any(d.glob("batch_summary*.json")):
            found.append((UNSUFFIXED_TRACE_MODEL if d == base else d.name[len(base.name) + len(MODEL_SEPARATOR):], d))
    return found


def trace_results_dir(trace_root: Path, run: PilotRun, stems: list[str]) -> tuple[Path, str]:
    """(results directory, graph model) for a run whose trace results are required. ``stems`` are the stems of the
    run's trace pairs file and of its byte-identical copies (Run 2's), any of which the lane may have traced. Two
    layouts are read (PR #85): the run's own folder, <root>/<run id>/<stem>[__<model>]/, where every pilot fire since
    2026-10-05 writes; and, for a run in LEGACY_TRACE_FOLDERS, the folder written before then,
    <root>/<legacy folder>[__<model>]/, while the run still holds the pairs file it is named after. A run with one
    graph model's results in both layouts is refused (``trace_layout_conflict``), whichever model is named: those would
    be two traces of one pairs file by one model, and the export never chooses between them. Different models in
    different layouts are not a conflict (a run traced again with another model keeps its first model's results where
    they were): across both layouts, a model named with --pilot-trace-model is read from its one directory and nowhere
    else; with none named, the one model whose directory holds results is read; none, or more than one directory, is
    refused (``missing_trace``, ``ambiguous_trace``), never guessed between."""
    run_id = run.run_id
    legacy_folder = LEGACY_TRACE_FOLDERS.get(run_id)
    legacy_bases = [trace_root / legacy_folder] if legacy_folder in stems else []
    own_bases = [trace_root / run_id / stem for stem in stems]
    legacy = [hit for base in legacy_bases for hit in _results_found(base)]
    own = [hit for base in own_bases for hit in _results_found(base)]
    both = sorted({m for m, _ in legacy} & {m for m, _ in own})
    if both:
        refuse("trace_layout_conflict", f"pilot run {run_id} has {', '.join(both)} trace results in both layouts: in "
                                        "the folder written before 2026-10-05 "
                                        f"({', '.join(f'{m}: {d}' for m, d in legacy if m in both)}) and in the run's "
                                        "own folder under PR #85's per-run layout "
                                        f"({', '.join(f'{m}: {d}' for m, d in own if m in both)}). The export does not "
                                        "choose between two traces of one pairs file by one model; a person decides "
                                        "which set stands (moving or removing committed results is a decision, made "
                                        f"in a pull request), or pass --pilot-trace-optional {run_id} to export the "
                                        "run without trace results")
    found = legacy + own
    if run.trace_model is not None:
        found = [(m, d) for m, d in found if m == run.trace_model]
    if len(found) > 1:
        tail = "" if run.trace_model is not None else (
            f"; if they are for different graph models, name the one whose traces this bundle requires with "
            f"--pilot-trace-model {run_id} <model>")
        refuse("ambiguous_trace", f"pilot run {run_id}: its trace results are in {len(found)} directories "
                                  f"({', '.join(f'{m}: {d}' for m, d in found)}), and the export reads one{tail}")
    if not found:
        bases = legacy_bases + own_bases
        where = (", ".join(str(_results_dir(b, run.trace_model)) for b in bases) if run.trace_model is not None else
                 ", ".join(f"{b} or {b}{MODEL_SEPARATOR}<model>" for b in bases))
        named = f"{run.trace_model} " if run.trace_model is not None else ""
        refuse("missing_trace", f"pilot run {run_id}: no {named}trace results (batch_summary*.json) in {where}; a "
                                f"trace result is required for its pairs (pass --pilot-trace-optional {run_id} to "
                                "export it without trace results)")
    model, d = found[0]
    return d, model


def _finalized_hash(manifest: dict, rel: str, data: bytes, run_id: str) -> None:
    """Refuse a run file whose bytes differ from the sha256 its finalized manifest records for it."""
    recorded = manifest["output_hashes"].get(rel)
    if not isinstance(recorded, str):
        refuse("run_not_finalized", f"pilot run {run_id}: the finalized manifest records no sha256 for {rel}")
    if sha256_bytes(data) != recorded:
        refuse("hash_mismatch", f"pilot run {run_id}: {rel} no longer hashes to the sha256 its finalized "
                                "manifest records")


def _json_of(data: bytes, path: Path, role: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        refuse("unreadable_input", f"{role}: {path} is not UTF-8 JSON ({type(exc).__name__})")


def _trace_pairs_candidates(run_dir: Path) -> list[Path]:
    """The JSON files under <run>/trace/ that are not .meta.json sidecars (names only; nothing is read)."""
    trace_dir = run_dir / "trace"
    return sorted(p for p in trace_dir.glob("*.json") if not p.name.endswith(".meta.json")) \
        if trace_dir.is_dir() else []


def _trace_pairs_file(run_dir: Path, run_id: str) -> tuple[Path, list[Path]]:
    """The run's one trace pairs file (the JSON file under <run>/trace/ that is not a .meta.json sidecar), and the
    other files there that must be byte-identical copies of it (pilot_items compares them). Only Run 2 may have
    copies: the lanes' pilot roots refuse its legacy trace_pairs.json for a new fire, so tracing it again needs a
    copy named for the run beside it (PR #85: pilot_v2_20261002_trace_pairs.json). The exporter still reads the
    legacy file, which its items' ids are keyed on; a copy's trace results are the same pairs' results, in the run's
    own folder (trace_results_dir)."""
    trace_dir = run_dir / "trace"
    found = _trace_pairs_candidates(run_dir)
    if not found:
        refuse("missing_trace", f"pilot run {run_id}: no trace pairs file under {trace_dir}; a trace result is "
                                f"required for its pairs (pass --pilot-trace-optional {run_id} to export it "
                                "without trace results)")
    if len(found) == 1:
        return found[0], []
    legacy = LEGACY_PILOT_RUNS.get(run_id)
    if legacy is not None and run_dir / legacy["id_source"] in found:
        id_file = run_dir / legacy["id_source"]
        return id_file, [p for p in found if p != id_file]
    refuse("bad_input", f"pilot run {run_id}: {len(found)} trace pairs files under {trace_dir} "
                        f"({[p.name for p in found]}); the exporter reads a run's one trace pairs file")


def _read_trace_pairs(inp: Inputs, pairs_path: Path, run_id: str) -> tuple[list[dict], str]:
    """The run's trace pairs, after the sidecar, run and key checks; and the pairs file's sha256."""
    meta_path = pairs_path.with_name(pairs_path.stem + ".meta.json")
    pairs, pairs_sha = inp.read_json(pairs_path, f"pilot run {run_id} trace pairs")
    meta, _ = inp.read_json(meta_path, f"pilot run {run_id} trace pairs sidecar")
    check_keys(meta, TRACE_META_KEYS, f"{meta_path.name}", ("output", "counts"))
    if (meta.get("output") or {}).get("sha256") != pairs_sha:
        refuse("hash_mismatch", f"{pairs_path} no longer hashes to the sha256 its sidecar records")
    if "run" in meta and meta["run"] != run_id:
        refuse("bad_input", f"{meta_path.name} names run {meta['run']!r}, not {run_id!r}")
    if not isinstance(pairs, list) or not pairs:
        refuse("bad_input", f"{pairs_path} is not a non-empty list of pairs")
    if (meta.get("counts") or {}).get("selected") != len(pairs):
        refuse("bad_input", f"{pairs_path} holds {len(pairs)} pairs; its sidecar says {meta['counts'].get('selected')}")
    for i, pair in enumerate(pairs, 1):
        where = f"{pairs_path.name} pair {i}"
        check_keys(pair, TRACE_PAIR_KEYS, where, tuple(sorted(TRACE_PAIR_KEYS)))
        pilot = check_keys(pair["pilot"], TRACE_PILOT_KEYS, f"{where} pilot block", ("row_id", "run"))
        if pilot["run"] != run_id:
            refuse("bad_input", f"{where}: its pilot block names run {pilot['run']!r}, not {run_id!r}")
        need_str(pilot["row_id"], f"{where} pilot.row_id")
    return pairs, pairs_sha


def pilot_items(inp: Inputs, seal: Seal, runs_dir: Path, trace_root: Path,
                run: PilotRun) -> tuple[list[dict], dict]:
    """The items of one finalized version-2 pilot run, in selection order, and the run's selection block."""
    run_id = run.run_id
    run_dir = _run_dir(runs_dir, run_id)
    manifest, _ = inp.read_json(run_dir / "manifest.json", f"pilot run {run_id} manifest")
    design_bytes = inp.read_bytes(run_dir / "design.json", f"pilot run {run_id} design")
    design = _json_of(design_bytes, run_dir / "design.json", f"pilot run {run_id} design")
    version = design.get("harness_version") if isinstance(design, dict) else None
    if version != HARNESS_VERSION:
        refuse("run_not_version_2", f"pilot run {run_id}: design.json harness_version is {version!r}; only "
                                    f"version-{HARNESS_VERSION} runs record the expected next word a pair shows")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("finalized_utc"), str) \
            or not manifest["finalized_utc"].strip():
        refuse("run_not_finalized", f"pilot run {run_id}: manifest.json is not finalized (no finalized_utc); "
                                    "export a run only after write_manifest.py finalize")
    if not isinstance(manifest.get("output_hashes"), dict):
        refuse("run_not_finalized", f"pilot run {run_id}: the finalized manifest records no output_hashes")
    _finalized_hash(manifest, "design.json", design_bytes, run_id)

    rows_path = run_dir / "generated" / "all_rows.jsonl"
    rows_bytes = inp.read_bytes(rows_path, f"pilot run {run_id} generated rows")
    _finalized_hash(manifest, "generated/all_rows.jsonl", rows_bytes, run_id)
    rows = parse_jsonl(rows_bytes, rows_path, f"pilot run {run_id} generated rows")
    by_id: dict[str, dict] = {}
    for row in rows:
        check_keys(row, PILOT_ROW_KEYS, f"{rows_path.name} row {row.get('id')!r}", ("id",))
        need_str(row["id"], f"{rows_path.name} row id")
        if row["id"] in by_id:
            refuse("bad_input", f"{rows_path.name} repeats row id {row['id']!r}")
        by_id[row["id"]] = row
        template = row.get("template")
        if isinstance(template, str) and BLANK in template:
            for side in ("clinical_term", "patient_term"):
                if isinstance(row.get(side), str):
                    inp.study(template.replace(BLANK, row[side]), f"pilot run {run_id} row {row['id']}")

    map_path = run_dir / "review_map.json"
    map_bytes = inp.read_bytes(map_path, f"pilot run {run_id} review map")
    _finalized_hash(manifest, "review_map.json", map_bytes, run_id)
    review_doc = _json_of(map_bytes, map_path, f"pilot run {run_id} review map")
    mapping = review_doc.get("map") if isinstance(review_doc, dict) else None
    if not isinstance(mapping, dict) or not mapping or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        refuse("bad_input", f"pilot run {run_id}: review_map.json has no map of review ids to row ids")
    review_of: dict[str, str] = {}
    for review_id, row_id in mapping.items():
        if row_id not in by_id:
            refuse("bad_input", f"pilot run {run_id}: review_map.json names row {row_id!r}, which is not in "
                                f"{rows_path.name}")
        if row_id in review_of:
            refuse("bad_input", f"pilot run {run_id}: review_map.json names row {row_id!r} twice")
        review_of[row_id] = review_id

    counts: Counter = Counter()
    if run.all_rows:
        selected = []
        for row in rows:
            control = row.get("control")
            if control == "none":
                selected.append(row)
            elif control == "negative":
                counts["excluded_control_rows"] += 1
            else:
                refuse("bad_input", f"pilot run {run_id} row {row['id']!r}: control {control!r} is neither 'none' "
                                    "nor 'negative'")
        counts["generated_rows"] = len(rows)
    else:
        selected = [by_id[mapping[review_id]] for review_id in sorted(mapping)]
        for row in selected:
            if row.get("control") != "none":
                refuse("bad_input", f"pilot run {run_id}: review sample row {row['id']!r} is a control row")
        counts["review_sample"] = len(mapping)
    if not selected:
        refuse("bad_input", f"pilot run {run_id}: no row was selected")

    pairs_by_row: dict[str, tuple[int, dict]] = {}
    traced: dict[int, tuple[str, str]] = {}
    pairs_path = traces_dir = trace_model = None
    pairs_sha = None
    if run.trace_required:
        pairs_path, copies = _trace_pairs_file(run_dir, run_id)
        pairs, pairs_sha = _read_trace_pairs(inp, pairs_path, run_id)
        for copy_path in copies:
            # a copy that differs would be a second selection of the run's pairs, whose traces this export does not
            # read; only a byte-identical copy (made to fire the run again under the lane's naming rule) is allowed
            if sha256_bytes(inp.read_bytes(copy_path, f"pilot run {run_id} trace pairs copy")) != pairs_sha:
                refuse("bad_input", f"pilot run {run_id}: {copy_path.name} under {copy_path.parent} is not a "
                                    f"byte-identical copy of {pairs_path.name}, which the export reads (its items' "
                                    f"ids are keyed on it). Besides {pairs_path.name}, the run's trace/ may hold "
                                    "only copies of it named for the run, as the lane's pilot root needs to trace "
                                    "it again")
        # trace_pairs.py records a review id on every pair when built with --review-sample and on none otherwise
        # (its default and --include-controls selections), so a file that records them must agree with
        # review_map.json on every pair, and a file that records none has nothing to check
        recorded = [pair["pilot"].get("review_id") for pair in pairs]
        carries_review_ids = any(r is not None for r in recorded)
        if carries_review_ids and None in recorded:
            refuse("bad_input", f"{pairs_path.name} records a review id for {sum(r is not None for r in recorded)} "
                                f"of its {len(pairs)} pairs; trace_pairs.py records one for every pair "
                                "(--review-sample) or for none")
        for i, pair in enumerate(pairs, 1):
            row_id = pair["pilot"]["row_id"]
            if row_id not in by_id:
                refuse("bad_input", f"{pairs_path.name} pair {i}: row {row_id!r} is not in {rows_path.name}")
            if row_id in pairs_by_row:
                refuse("bad_input", f"{pairs_path.name} pair {i} repeats row {row_id!r}")
            if carries_review_ids and pair["pilot"]["review_id"] != review_of.get(row_id):
                refuse("bad_input", f"{pairs_path.name} pair {i}: its review id is not the one review_map.json "
                                    f"gives row {row_id} (the file was built from another review map)")
            pairs_by_row[row_id] = (i, pair)
        traces_dir, trace_model = trace_results_dir(trace_root, run, [pairs_path.stem] + [c.stem for c in copies])
        traced = traced_prompts(inp, traces_dir, run_id, trace_model)
        counts["trace_pairs"] = len(pairs)
        counts["traced"] = sum(1 for i in range(1, len(pairs) + 1) if i in traced)
        counts["trace_pairs_not_selected"] = len(set(pairs_by_row) - {r["id"] for r in selected})

    legacy = LEGACY_PILOT_RUNS.get(run_id)
    if legacy:
        id_path = run_dir / legacy["id_source"]
        if pairs_path is not None and id_path.resolve() == pairs_path.resolve():
            id_sha = pairs_sha
        else:
            id_sha = sha256_bytes(inp.read_bytes(id_path, f"pilot run {run_id} item id key"))
    else:
        id_path, id_sha = rows_path, sha256_bytes(rows_bytes)
    source_path = logical_path(id_path)

    items = []
    for row in selected:
        row_id = row["id"]
        label = f"pilot run {run_id} row {row_id}"
        template = need_str(row.get("template"), f"{label} template")
        if template.count(BLANK) != 1:
            refuse("bad_input", f"{label}: template does not hold exactly one blank")
        clinical_term = need_str(row.get("clinical_term"), f"{label} clinical_term")
        patient_term = need_str(row.get("patient_term"), f"{label} patient_term")
        next_word = row.get("next_word")
        if not next_word_ok(next_word):
            # every row, whether or not its trace is required: a trace-optional run builds no trace pairs, so nothing
            # else would refuse a next word the parser and the trace-pairs builder refuse (the value is row text, so
            # the message does not quote it)
            refuse("bad_next_word", f"{label}: next_word breaks the version-2 rule, one lowercase word of letters "
                                    "with at most one internal hyphen or apostrophe (pilot/scripts/common.py "
                                    "next_word_ok, which the parser and pilot/analysis/trace_pairs.py apply). A "
                                    "physician would be asked to judge an expected next word the study's next-token "
                                    "target is never built from")
        top, bottom = template.replace(BLANK, clinical_term), template.replace(BLANK, patient_term)
        trace_index = None
        if run.trace_required:
            if row_id not in pairs_by_row:
                which = ("--pilot-all-rows takes every non-control row, and trace_pairs.py's selections leave out "
                         "the rows the checker did not judge equivalent (default) or every row outside the review "
                         "sample (--review-sample)" if run.all_rows else
                         "the review sample needs a trace pairs file that holds every review-sample row, as "
                         "trace_pairs.py --review-sample builds it")
                refuse("missing_trace", f"{label} is not in {pairs_path.name}; a trace result is required for its "
                                        f"pairs, and {which}. Pass --pilot-trace-optional {run_id} to export it "
                                        "without one")
            trace_index, pair = pairs_by_row[row_id]
            where = f"{pairs_path.name} pair {trace_index}"
            if pair["top_prompt"] != top or pair["bottom_prompt"] != bottom:
                refuse("bad_input", f"{where}: the pair's sentences are not row {row_id}'s template with its terms")
            if pair["target_clinical_token"] != " " + next_word:
                refuse("bad_input", f"{where}: target_clinical_token is not a space plus row {row_id}'s next_word")
            if trace_index not in traced:
                refuse("missing_trace", f"{where} (row {row_id}) has no trace result in {traces_dir}; a trace "
                                        f"result is required for its pairs (pass --pilot-trace-optional {run_id} "
                                        "to export it without one)")
            if traced[trace_index] != (top, bottom):
                refuse("trace_mismatch", f"{where} (row {row_id}): the trace result with index {trace_index} in "
                                         f"{traces_dir} carries other prompts")
        if seal.row_sealed("tracing_pilot", None, None, top, label):
            refuse("sealed_row", f"{label} is a sealed holdout phrase")
        display = pair_display(top, bottom, next_word)
        item_id = item_id_for("tracing_pair", source_path, row_id)
        seal.note_bucket(item_id, top)
        items.append({
            "item_id": item_id,
            "family": "tracing_pair", "question_set": "tracing_pair", "display": display, "reveal": None,
            "provenance": {"subset": run.subset, "source_path": source_path, "source_id": row_id,
                           "source_sha256": id_sha, "run": run_id, "review_id": review_of.get(row_id),
                           "trace_index": trace_index, "rows_path": logical_path(rows_path),
                           "display_sha256": sha256_text(canonical(display))},
        })
    counts["selected"] = len(items)
    rows_rule = ("every generated row of the run that is not a control row (control 'none'), in the run's row order"
                 if run.all_rows else
                 "the run's blind review sample (review_map.json), in review-id order")
    trace_rule = ("; each pair required to be in the run's trace pairs file and to have a trace result with the "
                  f"same prompts in the {trace_model} trace results, every trace summary read declaring "
                  f"graph_model {trace_model}" if run.trace_required else
                  "; trace results not required and not read (a pair joins its trace later by run and row id)")
    selection = {
        "run": run_id,
        "rule": f"{rows_rule}, joined to the run's generated rows for template, terms and next word{trace_rule}. "
                "The run must be finalized and version 2, and every run file read must hash as its finalized "
                "manifest records",
        "rows": "all_rows" if run.all_rows else "review_sample",
        "trace_required": run.trace_required,
        "source": source_path,
        "rows_source": logical_path(rows_path),
        "trace_pairs": logical_path(pairs_path) if pairs_path is not None else None,
        "trace_results": logical_path(traces_dir) if traces_dir is not None else None,
        "trace_model": trace_model,
        "counts": dict(sorted(counts.items())),
    }
    return items, selection


def traced_prompts(inp: Inputs, traces_dir: Path, run_id: str, model: str) -> dict[int, tuple[str, str]]:
    """{trace index: (clinical prompt, patient prompt)} from the trace results under traces_dir, which are read as
    ``model``'s. Every summary there must declare that graph model in its ``graph_model`` field, which the hosted
    circuit-trace summaries always record (medlang_circuits/batch_eval.py, run_batch): the directory name says which
    model the lane wrote it for, and the summary says which model traced it, so a summary that names another model,
    or none, is refused (``trace_model_mismatch``) rather than recorded under the directory's model."""
    parts = sorted(traces_dir.glob("batch_summary*.json")) if traces_dir.is_dir() else []
    if not parts:
        refuse("missing_trace", f"pilot run {run_id}: no batch_summary*.json under {traces_dir}; a trace result is "
                                f"required for its pairs (pass --pilot-trace-optional {run_id} to export it without "
                                "trace results)")
    out: dict[int, tuple[str, str]] = {}
    for part in parts:
        summary, _ = inp.read_json(part, f"pilot run {run_id} trace results")
        declared = summary.get("graph_model") if isinstance(summary, dict) else None
        if not isinstance(declared, str) or declared != model:
            what = f"declares graph model {declared!r}" if isinstance(declared, str) else \
                "declares no graph model (no string graph_model)"
            refuse("trace_model_mismatch", f"pilot run {run_id}: {part} {what}, but the export reads {traces_dir} "
                                           f"as {model}'s trace results. A summary of another model, or of none "
                                           "named, would be recorded under the wrong model; move it to its model's "
                                           "directory, or name the model with --pilot-trace-model")
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
        for field in ("clinical_message", "patient_message", "clinical_body", "patient_body"):
            inp.study(item[field], where)
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
        for field in ("clinical_message", "patient_message", "clinical_body", "patient_body"):
            inp.study(item[field], where)
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
            inp.study(entry["text"], where)
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

def answer_contracts(questions: Any, where: str) -> dict[str, dict]:
    """{"<question set>.<question id>": what a stored answer to that question means} for a questions document: the
    scale's type, its option values in order, its abstain value and (a text scale) its max_length, and the
    question's phase, required, per_arm and locks_on_reveal. Labels, definitions, text and hint are wording, which
    may change. The app validates a stored answer against all of these when a physician saves the item again
    (patientwords-verify src/Logic.gs: validValue_, answerKeys_, validateAnswers_), gates the reveal and an item's
    completeness on ``required`` (blindComplete_, itemComplete_), and the import reads a rating against all of them
    (its is_complete and reveal checks read ``required``). required, per_arm and locks_on_reveal are read as the app
    and the import read them, by truth value. A document of another shape is refused, naming where, never
    skipped."""
    def bad(what: str) -> NoReturn:
        refuse("bad_input", f"{where}: {what}")

    if not isinstance(questions, dict):
        bad("questions is not an object")
    scales, sets = questions.get("scales"), questions.get("question_sets")
    if not isinstance(scales, dict):
        bad("questions.scales is not an object")
    if not isinstance(sets, dict):
        bad("questions.question_sets is not an object")
    out: dict[str, dict] = {}
    for set_name, qset in sets.items():
        qs = qset.get("questions") if isinstance(qset, dict) else None
        if not isinstance(qs, list):
            bad(f"question set {set_name!r} has no questions list")
        for n, q in enumerate(qs, 1):
            if not isinstance(q, dict) or not isinstance(q.get("id"), str):
                bad(f"question {n} of set {set_name!r} is not an object with a string id")
            scale = scales.get(q["scale"]) if isinstance(q.get("scale"), str) else None
            options =scale.get("options", []) if isinstance(scale, dict) else None
            if not isinstance(options, list) or not all(isinstance(o, dict) and "value" in o for o in options):
                bad(f"{set_name}.{q['id']}: its scale is not an object with a list of options that have values")
            abstain = scale.get("abstain")
            if abstain is not None and not (isinstance(abstain, dict) and "value" in abstain):
                bad(f"{set_name}.{q['id']}: its scale's abstain is not an object with a value")
            out[f"{set_name}.{q['id']}"] = {
                "scale_type": scale.get("type"), "values": [o["value"] for o in options],
                "abstain": abstain["value"] if abstain is not None else None,
                "max_length": scale.get("max_length") if scale.get("type") == "text" else None,
                "phase": q.get("phase"), "required": bool(q.get("required")), "per_arm": bool(q.get("per_arm")),
                "locks_on_reveal": bool(q.get("locks_on_reveal"))}
    return out


def notes_limit(questions: Any, where: str) -> int:
    """The questions document's notes.max_length: the longest note (in UTF-16 code units) the app saves and the import
    accepts with a rating (src/Logic.gs validateAnswers_; the import's notes_too_long). Refused, never skipped, when
    it is not a positive integer."""
    notes = questions.get("notes") if isinstance(questions, dict) else None
    limit = notes.get("max_length") if isinstance(notes, dict) else None
    if not (isinstance(limit, int) and not isinstance(limit, bool) and limit > 0):
        refuse("bad_input", f"{where}: questions.notes.max_length is not a positive integer")
    return limit


def check_previous_bundle(inp: Inputs, path: Path, items: list[dict], questions: dict) -> dict:
    """The previous round's bundle, checked against this one: every item it holds is here under the same id, with
    the same question set, display and reveal, every question id of each of its question sets is still in that
    set with the same answer contract (``answer_contracts``), no question set its items use has gained a required
    question, and the notes limit (``notes_limit``) is the same. The app needs every item a physician holds to stay
    in the bundle it switches to, and stores answers under the item id and the question id (its DEPLOY.md section
    19), so a missing item or question, another text under the same id, another scale, set of answer values, phase,
    required, per_arm or reveal lock under the same question id, a new required question that stored ratings cannot
    have answered (a new optional one is kept), or another notes limit is refused (ids only). Contracts are compared
    as canonical JSON, never with Python's ==: the app (===) and the import (same_value) keep JSON types apart, so
    true is not 1 and 1.0 is not 1 here either, though the app would take 1.0 for 1 (refusing that is the safe
    side)."""
    role = "previous round's bundle"
    data = inp.read_bytes(path, role)
    prev = _json_of(data, path, role)
    if not isinstance(prev, dict) or prev.get("schema") != SCHEMA or not isinstance(prev.get("items"), list) \
            or not isinstance(prev.get("questions"), dict):
        refuse("bad_input", f"--previous-bundle {path} is not a {SCHEMA} bundle")
    now = {i["item_id"]: i for i in items}
    missing, changed = [], []
    for n, old in enumerate(prev["items"], 1):
        item_id = old.get("item_id") if isinstance(old, dict) else None
        if not isinstance(item_id, str):
            refuse("bad_input", f"--previous-bundle {path}: item {n} has no item_id")
        new = now.get(item_id)
        if new is None:
            missing.append(item_id)
        elif any(canonical(new[k]) != canonical(old.get(k)) for k in ("question_set", "display", "reveal")):
            changed.append(item_id)
    if missing:
        refuse("previous_item_missing", f"{len(missing)} item(s) of {prev.get('bundle_id')} are not in this bundle: "
                                        f"{sorted(missing)}. The app needs every item a physician holds to stay in "
                                        "the bundle it switches to")
    if changed:
        refuse("previous_item_changed", f"{len(changed)} item(s) of {prev.get('bundle_id')} show another text, "
                                        f"proposed tier or question set under the same item id: {sorted(changed)}. "
                                        "A rating stored under the id would be read as a rating of the new one")
    old_contracts = answer_contracts(prev["questions"], f"--previous-bundle {path}")
    new_contracts = answer_contracts(questions, "this bundle's questions")
    lost = sorted(k for k in old_contracts if k not in new_contracts)
    if lost:
        refuse("previous_question_missing", f"question id(s) of {prev.get('bundle_id')} are not in this bundle's "
                                            f"questions: {lost}. Wording may change between bundles; "
                                            "question ids may not")
    altered = []
    for k, old_contract in old_contracts.items():
        fields = [f for f in old_contract if canonical(old_contract[f]) != canonical(new_contracts[k][f])]
        if fields:
            altered.append(f"{k} ({', '.join(fields)})")
    altered.sort()
    if altered:
        refuse("previous_question_changed", f"question id(s) of {prev.get('bundle_id')} keep their id with another "
                                            f"answer contract: {altered}. An answer stored under the id would be "
                                            "read on another scale, phase, requirement or lock. Wording may change "
                                            "between bundles; what an answer means may not")
    # Every previous item is here with the same question set (checked above), so these are the sets whose items may
    # hold stored ratings. A question added to one of them as required makes each such rating lack a required
    # answer: the app (itemComplete_, blindComplete_) and the import (is_complete; reveal_blind_incomplete for a
    # blind one) would count a completed item as incomplete and refuse a stored reveal. An optional one changes
    # neither, and a set no previous item uses holds no stored rating.
    retained_sets = sorted({now[old["item_id"]]["question_set"] for old in prev["items"]})
    added_required = [f"{set_name}.{q['id']}" for set_name in retained_sets
                      for q in questions["question_sets"][set_name]["questions"]
                      if f"{set_name}.{q['id']}" not in old_contracts
                      and new_contracts[f"{set_name}.{q['id']}"]["required"]]
    if added_required:
        refuse("previous_required_question_added", f"question set(s) that items of {prev.get('bundle_id')} use "
                                                   f"gained required question(s): {sorted(added_required)}. A "
                                                   "rating saved on the previous bundle holds no answer to them, so "
                                                   "the app and the import would count a completed item as "
                                                   "incomplete (and refuse a stored reveal that lacks a required "
                                                   "blind answer). Add a question to such a set as optional "
                                                   "(required false)")
    old_notes = notes_limit(prev["questions"], f"--previous-bundle {path}")
    new_notes = notes_limit(questions, "this bundle's questions")
    if old_notes != new_notes:
        refuse("previous_notes_changed", f"the notes limit (questions.notes.max_length) of {prev.get('bundle_id')} is "
                                         f"{old_notes} and this bundle's is {new_notes}. The app and the import refuse "
                                         "a note longer than the bundle's limit, so the limit a saved note was written "
                                         "under may not change between bundles (a lower one would refuse it)")
    return {"path": logical_path(path), "bundle_id": prev.get("bundle_id"), "sha256": sha256_bytes(data),
            "items_kept": len(prev["items"]), "items_added": len(items) - len(prev["items"])}


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

    runs = pilot_runs_from_args(args)
    check_trace_pairs_files(runs, Path(args.pilot_runs_dir))
    pilot: list[dict] = []
    pilot_sel: dict[str, dict] = {}
    pilot_by_subset: dict[str, int] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for run in runs:
        run_items, run_sel = pilot_items(inp, seal, Path(args.pilot_runs_dir), Path(args.pilot_trace_root), run)
        # a pair whose two sentences repeat an earlier pilot item's (in this run or an earlier one) is kept, since
        # each row is its run's output, and counted
        repeats = 0
        for item in run_items:
            key = (item["display"]["clinical"]["text"], item["display"]["patient"]["text"])
            repeats += key in seen_pairs
            seen_pairs.add(key)
        run_sel["counts"]["repeats_an_earlier_pilot_pair"] = repeats
        run_sel["counts"] = dict(sorted(run_sel["counts"].items()))
        pilot += run_items
        pilot_sel[run.subset] = run_sel
        pilot_by_subset[run.subset] = len(run_items)
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
    previous = (check_previous_bundle(inp, Path(args.previous_bundle), items, questions)
                if args.previous_bundle else None)
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
    # an example's strings are shown to every physician, so each is swept as an item's display strings are, and a hit
    # names the example (the whole-bundle sweep below would catch it too, but could not say where)
    example_hits: dict[str, list[str]] = {}
    for n, example in enumerate(questions["instructions"].get("examples", [])):
        found = sorted({label for text in example_texts(example) for label in seal.scan(text)})
        if found:
            example_hits[f"instructions.examples[{n}] ({example['family']})"] = found
    if example_hits:
        refuse("seal_hit", f"rater-visible text of {len(example_hits)} example(s) contains a sealed holdout phrase: "
                           + "; ".join(f"{k} :: {', '.join(v)}" for k, v in sorted(example_hits.items())))
    if questions["instructions"].get("examples"):
        study_payload(inp, Path(args.site))
        check_example_copies(inp, questions["instructions"]["examples"])

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
            "tracing_pair": {**pilot_sel, "main_study": main_sel},
            "advice": advice_sel,
            "multiturn": multi_sel,
            "order": "items sorted by item_id, then shuffled with Python's random.Random(seed); the app orders "
                     "each physician's items by its own seeded hash",
            "item_id": "vt_ + the first 12 hex digits of sha256(family U+001F source path U+001F source id)",
            "previous_bundle": previous,
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
            "tracing_pair_by_subset": {**pilot_by_subset, "main_study": len(main)},
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
    ap.add_argument("--pilot-run", action="append", metavar="RUN_ID",
                    help="a finalized version-2 pilot run to take tracing pairs from, by its directory name under "
                         f"--pilot-runs-dir; repeatable (default: {DEFAULT_PILOT_RUN} alone, the first bundle's run)")
    ap.add_argument("--pilot-all-rows", action="append", metavar="RUN_ID",
                    help="take every non-control generated row of this run instead of its blind review sample")
    ap.add_argument("--previous-bundle", default=None, metavar="PATH",
                    help="the previous round's bundle: refuse unless every item it holds is in this one, unchanged, "
                         "every question id it uses is kept with the same scale, answer values, phase, requirement "
                         "and lock, no question set its items use gains a required question, and the notes limit is "
                         "the same")
    ap.add_argument("--pilot-trace-optional", action="append", metavar="RUN_ID",
                    help="do not require (or read) trace results for this run's pairs; by default every pilot "
                         "pair needs one (Run 2's trace pairs file is still read: its item ids are keyed on it)")
    ap.add_argument("--pilot-trace-model", action="append", nargs=2, metavar=("RUN_ID", "MODEL"),
                    help="read this run's required trace results for this graph model, from "
                         f"<--pilot-trace-root>/<run id>/<pairs stem>{MODEL_SEPARATOR}<model>/ "
                         f"({UNSUFFIXED_TRACE_MODEL}: <pairs stem>/), as the circuit-trace lane writes them (Run 2's "
                         "and Run 3's legacy folders: <--pilot-trace-root>/<pairs stem>[__<model>]/); with none "
                         "named, the one model whose results exist is read, and none or more than one is refused. "
                         "Every summary read must declare the model in its graph_model field")
    for key in ("questions", "pilot_runs_dir", "pilot_trace_root", "advice_new", "advice_rerun", "petri_seeds",
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
