"""Neuronpedia identity and link boundary: representation registry, links with an offline fallback, records.

THIS MODULE MAKES NO NETWORK REQUEST. It imports no HTTP client and no socket. It reads the registry file, hashes
files a person already downloaded, and validates records a caller built. ``tests/test_experiments_neuronpedia.py``
(``test_importing_and_using_the_module_opens_no_socket``) calls every public function of this module with
``socket.socket``, ``socket.create_connection`` and ``socket.getaddrinfo`` replaced by a function that raises,
and fails when a public function is added that it does not call.

What it holds:

* The representation registry (``patientwords.representation-registry/1``,
  ``data/experiments/representation_registry.v1.json``). One entry names one representation of one study model:
  its type, the method that reads it, the study model identity, the Neuronpedia ids when one is known, the fitted
  artifact, the label source and a verification status with its evidence. The seven representation types are
  different objects. Nothing here converts one into another.
* ``resolve``: a study model id plus a representation type gives an entry or a typed "no mapping" result.
* ``build_link`` and ``link_or_fallback``: a URL is returned only for an entry whose mapping is ``verified_exact``
  and whose URL pattern is recorded in the registry with its source. A URL is assembled from recorded ids and
  integers only. No prompt, no patient-style text and no other free text can enter one: the functions take no text
  argument, refuse a non-integer component id, bound both integers (so a hash written as a decimal integer is
  refused) and check the finished URL against a closed character set.
* Snapshot records for bulk exports and a request record for bounded API calls. Both are structures with
  validation. Somebody else performs the download or the request. A request record is checked by key name, by
  value type, by character class and by a credential screen, so that a credential or prompt text is refused
  under another key name or as a string value; ``validate_request_record`` states what that check cannot see.
* Explanation provenance: several competing labels per feature, each with its source and scorer, and four
  quantities that stay in four differently named fields.
* ``validate_graph_reference`` for the envelope payload kind ``attribution_graph_ref/1``: ids, hashes and
  source-set identity. This milestone has no graph exporter; ``docs/experiment_interface/neuronpedia.md`` holds
  the plan.

A verification status says what was checked about the mapping, with evidence. An alias (the same checkpoint
under another id) is not a verified checkpoint: ``verified_exact`` needs the hosted checkpoint revision recorded
and equal to the study pin. Missing provenance is explicit: a field may be null only when its JSON pointer is in
the record's ``not_recorded`` list, as in the run envelope.

Refusal messages. A message names positions, counts, this module's own vocabularies and key names that are
short identifiers. A value that failed its check is not repeated, and neither is a key that is not a short
identifier or that starts like a credential (it is counted or given by position): the string that must not be
stored must not reach a log either. A value is repeated only after it passed an id, hash, date or integer
check. No refusal of a request record repeats any value. Two things are outside this rule: a local file path
the caller passed to a snapshot function, and the registry's structural errors, which the shared schema checker
(``common.require_structure``) words and which name the path of the offending key.
"""
from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, TypeVar

from scripts.experiments.common import (
    DATE, ENGINE, HEX40, HEX64, METHOD_IDS, NOT_APPLICABLE, REPRESENTATION_TYPES, Refusal, integer, read_json,
    require, require_structure, sha256_bytes, text,
)
from scripts.experiments.envelope import null_pointers

REGISTRY_SCHEMA = "patientwords.representation-registry/1"
EXPLANATION_SCHEMA = "patientwords.feature-explanations/1"
SNAPSHOT_SCHEMA = "patientwords.export-snapshot/1"
REQUEST_SCHEMA = "patientwords.api-request-record/1"
GRAPH_REF_KIND = "attribution_graph_ref/1"

REGISTRY_PATH = ENGINE / "data" / "experiments" / "representation_registry.v1.json"

# What was checked about a mapping. Only the first permits a link.
VERIFIED = "verified_exact"
VERIFICATION_STATUSES = (VERIFIED, "alias_unverified_checkpoint", "hosted_identity_unknown", "unverified")
CALIBRATIONS = ("calibrated_reference", "not_calibrated", NOT_APPLICABLE)
USES = ("calibrated_feature_source", "exploration_only", "landed_hosted_readouts", "named_not_used",
        "synthetic_fixture")
# A page that shows one component of one representation. No kind takes a prompt or any other text.
URL_KINDS = ("feature_page", "component_page", "head_page")
PLACEHOLDERS = ("model_id", "source_set", "source_id", "layer", "component")

# The two reasons a link is withheld, and the reason no entry was found.
LINK_BUILT = "link built from the recorded pattern"
REASON_NOT_VERIFIED = "mapping not verified"
REASON_NO_PATTERN = "no recorded URL pattern"
REASON_NO_MAPPING = "no mapping"

FIXTURE_PREFIX = "fixture/"
FIXTURE_HOST_SUFFIX = ".invalid"  # a reserved top-level domain: a fixture link can never reach a real site

REGISTRY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
ID_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
UTC_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?\Z")
TEMPLATE_TEXT = re.compile(r"https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~{}-]+)+\Z")
BUILT_URL = re.compile(r"https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~-]+)+\Z")
PLAIN_URL = re.compile(r"https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/-]*)?\Z")
# Strings a reference may hold: ids, repository ids, hashes, dates and JSON pointers. No whitespace.
NO_FREE_TEXT = re.compile(r"[A-Za-z0-9._:/~-]{1,128}\Z")

GRAPH_REPRESENTATIONS = ("transcoder_feature", "sae_latent", "graph_node")

# Explanation provenance.
LABEL_BASES = ("activation_examples", "token_list_only", "human_written")
TOKEN_LIST_BASIS = "token_list_only"
TOKEN_LIST_FLAG = "not_a_clinical_concept_name"
FLAG_TEXT = {TOKEN_LIST_FLAG: "not a clinical concept name"}
LABEL_STATUS = "hypothesis"
LENS_METHODS = ("logit_lens", "j_lens", "jpp", "ica_lens")
# Four quantities, four fields. Each record repeats its field name in "kind"; no function here adds, averages
# or ranks records of different kinds.
QUANTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "feature_interpretability_score": ("kind", "value", "missing_reason", "scale", "source", "scorer"),
    "label_prediction_score": ("kind", "value", "missing_reason", "scale", "source", "scorer", "label_id"),
    "lens_token_rank": ("kind", "value", "missing_reason", "source", "lens", "layer", "token_id", "rank_base",
                        "filtered"),
    "clinical_outcome": ("kind", "value", "missing_reason", "scale", "source", "outcome_id", "owner"),
}
QUANTITY_KINDS = tuple(QUANTITY_FIELDS)
GENERIC_SCORE_KEYS = frozenset({
    "score", "scores", "combined_score", "overall_score", "composite_score", "understanding_score", "quality",
})
LABEL_SELECTION_KEYS = frozenset({"primary_label", "best_label", "selected_label", "label"})
OUTCOME_OWNER = "patientwords"
# Closed key sets. A label, its source and a scorer hold these keys and no other, so a number, a rank or a
# flag that selects a label has nowhere to sit inside one.
LABEL_KEYS = ("label_id", "text", "basis", "flags", "status", "source", "scorer")
LABEL_OPTIONAL_KEYS = ("tokens",)
SOURCE_KEYS = ("name", "version", "explanation_type", "explanation_model", "retrieved_utc")
SCORER_KEYS = ("name", "version")

# Request records. Both repositories are public and a validated record is a file that gets committed, so the
# record is checked three ways: by key name, by value type and by the character class of the few strings allowed.
#
# 1. Key names. A key is lowercased and stripped of everything but letters and digits, then refused when it
#    CONTAINS one of the fragments below. "NEURONPEDIA_API_KEY", "x-api-key", "apiKey" and "keys" all contain
#    "key"; "user_prompt", "promptText" and "prompts" all contain "prompt".
SECRET_FRAGMENTS = ("key", "token", "secret", "auth", "password", "passwd", "pwd", "cookie", "bearer", "credential",
                    "session", "signature", "header", "jwt")
TEXT_FRAGMENTS = ("prompt", "text", "message", "content", "input", "query", "body", "slug", "completion",
                  "utterance", "transcript")
# Two exceptions, each with its own value rule. A key that ends in "sha256" names its subject by hash
# (prompt_sha256, token_sha256) and must hold 64 hex digits or null; the text fragments and "token" do not
# refuse it, every other secret fragment still does. The counted settings below are fields of the engine's own
# lens request (scripts/jlens_readout.py, lens_request_body) and of common completion APIs; they are matched by
# exact normalized name and must hold a boolean or an integer.
HASH_KEY_SUFFIX = "sha256"
COUNT_SETTING_KEYS = frozenset({"numcompletiontokens", "filternonwordtokens", "maxtokens", "maxnewtokens"})
# 2. Value types. A value is null, a boolean, a finite number, an object or a list of those. A string is
#    allowed only under one of these normalized keys, where it must be one id (optionally "owner/name"); under
#    a hash key, where it must be 64 hex digits; nowhere else.
ID_VALUE_KEYS = frozenset({"modelid", "sourceset", "sourcesetname", "sourceid", "service", "instrumentrevision",
                           "modelrevision", "dictionaryrevision", "type", "lens", "lenstype", "dtype"})
ID_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}(/[A-Za-z0-9][A-Za-z0-9._-]{0,63})?\Z")
SETTING_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,47}\Z")
#    A list of strings is allowed under one key only: "type". It is the one field of the engine's own request
#    bodies that holds a list of strings (scripts/jlens_readout.py, lens_request_body: "type": [lens_type], with
#    lens_type one of JACOBIAN_LENS, LOGIT_LENS). The graph request (medlang_circuits/graph_client.py) holds no
#    list. Such a list has 1 to MAX_LIST_ITEMS distinct items, each an upper-case constant.
LIST_VALUE_KEYS = frozenset({"type"})
LIST_ITEM = re.compile(r"[A-Z][A-Z0-9_]{0,31}\Z")
MAX_LIST_ITEMS = 8
# 3. The credential screen. A string that starts like a credential of a known issuer is refused, and so is an
#    id value that holds a run of more than TOKEN_RUN_LENGTH letters and digits with no separator, drawn from at
#    least two of lower-case letters, upper-case letters and digits: that is how issued tokens look. The one
#    exception is 40 or 64 lower-case hex digits under a revision key (a commit id or a content hash).
CREDENTIAL_PREFIXES = ("sk-", "hf_", "aiza", "ghp_", "gho_", "github_pat_", "xox")
TOKEN_RUN_LENGTH = 24
TOKEN_RUN = re.compile(r"[A-Za-z0-9]{%d,}" % (TOKEN_RUN_LENGTH + 1))
REVISION_KEYS = frozenset({"instrumentrevision", "modelrevision", "dictionaryrevision"})
ENDPOINT_PATH = re.compile(r"(/[A-Za-z0-9._~{}-]{1,64})+\Z")
MAX_PATH_SEGMENTS = 8
ENDPOINT_HOST = re.compile(r"[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63}){0,7}\Z")
# A not_recorded entry of a request record: a JSON pointer made of key names and list indexes.
RECORD_POINTER = re.compile(r"(/[A-Za-z0-9_.-]{1,48})+\Z")
REQUEST_POINTER_ROOTS = ("effective_request_settings", "service_identity", "response_sha256", "retrieved_utc")
MAX_POINTERS = 256

# Integers that go into a URL. A component index is below the entry's recorded component count when the entry
# records one (component_id.count), and below MAX_COMPONENT_ID in every case; a layer is below MAX_LAYER. A
# SHA-256 written as a decimal integer has up to 78 digits and is refused by either bound.
MAX_COMPONENT_ID = 2 ** 20
MAX_LAYER = 4096


# ------------------------------------------------------------------------------------------------ registry

_F = TypeVar("_F", bound=Callable[..., Any])


def _guarded(function: _F) -> _F:
    """Turn a malformed-shape error into ``Refusal('invalid_input')``; pass a ``Refusal`` through.

    The message carries the error type. It carries the error text for a ``KeyError`` (the missing key is a field
    name written in this module), a ``TypeError`` and an ``AttributeError`` (Python names types there, not
    values). A ``ValueError`` text can quote the value that failed to parse, so it is left out. A document
    nested beyond the interpreter's recursion limit ends here too."""
    @functools.wraps(function)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except Refusal:
            raise
        except (ValueError, RecursionError) as exc:
            raise Refusal("invalid_input", f"{type(exc).__name__}: a value has the wrong form or is nested too "
                          "deeply") from exc
        except (KeyError, TypeError, AttributeError) as exc:
            raise Refusal("invalid_input", f"{type(exc).__name__}: {exc}") from exc
    return run  # type: ignore[return-value]


def _credential_prefixed(parts: Iterable[str], *, host: bool = False) -> bool:
    """True when one of ``parts`` starts like a credential of a known issuer, in any letter case.

    ``host`` is for host labels: a host cannot hold an underscore, so a prefix that has one is also tested with
    a hyphen in its place (``hf-`` for ``hf_``)."""
    prefixes = CREDENTIAL_PREFIXES + (tuple(p.replace("_", "-") for p in CREDENTIAL_PREFIXES) if host else ())
    return any(part.lower().startswith(prefixes) for part in parts)


def _token_shaped(value: str) -> bool:
    """True when ``value`` holds a run of more than ``TOKEN_RUN_LENGTH`` letters and digits with no separator that
    draws on at least two of lower-case letters, upper-case letters and digits."""
    return any(sum(bool(re.search(group, run)) for group in ("[a-z]", "[A-Z]", "[0-9]")) >= 2
               for run in TOKEN_RUN.findall(value))


def _credential_shaped(value: str, *, revision: bool = False) -> bool:
    """The credential screen for one string value: an issuer prefix on any '/'-separated part, or a token-shaped
    run. With ``revision`` (the value sits under a revision key) 40 or 64 lower-case hex digits are a commit id
    or a content hash and pass."""
    if revision and (HEX40.fullmatch(value) or HEX64.fullmatch(value)):
        return False
    return _credential_prefixed(value.split("/")) or _token_shaped(value)


def _shown(names: Iterable[Any]) -> str:
    """Key names for a refusal message. A name is printed only when it is a short identifier that does not
    start like a credential; every other name is counted, not printed."""
    listed = list(names)
    safe = sorted(name for name in listed if isinstance(name, str) and SETTING_KEY.fullmatch(name)
                  and not _credential_prefixed([name]))
    hidden = len(listed) - len(safe)
    return f"{safe}" + (f" and {hidden} name(s) that are not short identifiers" if hidden else "")


def _resolves_to_null(doc: Any, pointer: Any) -> bool:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False
    node = doc
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and key in node:
            node = node[key]
        # isascii first: str.isdigit accepts characters such as a superscript two, which int() refuses.
        elif isinstance(node, list) and key.isascii() and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
        else:
            return False
    return node is None


def _check_not_recorded(record: Mapping[str, Any], nulls: Iterable[str], where: str) -> None:
    """A null is allowed only when its pointer is listed; a listed pointer must be a null field.

    The pointers of unlisted nulls are built from the record's own keys, which the caller has checked, and are
    printed. An entry of ``not_recorded`` that points at no null field is arbitrary text: its position is
    reported and its text is not."""
    listed = record["not_recorded"]
    require(isinstance(listed, list), "not_recorded_pointer", f"{where}: not_recorded must be a list")
    known = {entry for entry in listed if isinstance(entry, str)}
    silent = sorted(set(nulls) - known)
    require(not silent, "silent_missing_provenance", f"{where}: null fields not listed in not_recorded: {silent}")
    stale = [number for number, entry in enumerate(listed) if not _resolves_to_null(record, entry)]
    require(not stale, "not_recorded_pointer",
            f"{where}: {len(stale)} of the {len(listed)} not_recorded entries point at no null field, at "
            f"position(s) {stale[:16]}. An entry's text is not repeated here")


def _check_record_pointers(listed: Any, roots: Iterable[str], where: str) -> None:
    """``listed`` is a list of distinct JSON pointers made of key names and list indexes, each under one of
    ``roots``. Checked before the list is used for anything else, so that text placed in ``not_recorded`` is
    refused here and is never repeated: the message gives positions and a count."""
    require(isinstance(listed, list) and len(listed) <= MAX_POINTERS, "not_recorded_pointer",
            f"{where}: not_recorded must be a list of at most {MAX_POINTERS} JSON pointers")
    allowed = tuple(roots)
    bad = [number for number, entry in enumerate(listed)
           if not (isinstance(entry, str) and RECORD_POINTER.fullmatch(entry) and entry.split("/")[1] in allowed
                   and not _credential_prefixed(entry.split("/")))]
    require(not bad, "not_recorded_pointer",
            f"{where}: {len(bad)} of the {len(listed)} not_recorded entries are not JSON pointers of key names "
            f"under {['/' + root for root in allowed]}, at position(s) {bad[:16]}. An entry's text is not "
            "repeated here")
    require(len(set(listed)) == len(listed), "not_recorded_pointer", f"{where}: not_recorded lists a pointer twice")


def _optional_id(value: Any) -> bool:
    return value is None or value == NOT_APPLICABLE or bool(ID_TOKEN.fullmatch(str(value)))


def _usable_id(value: Any) -> bool:
    return isinstance(value, str) and value != NOT_APPLICABLE and bool(ID_TOKEN.fullmatch(value))


def _placeholders(template: str) -> list[str]:
    return re.findall(r"\{([^{}]*)\}", template)


def _check_url_pattern(entry: Mapping[str, Any], where: str, synthetic: bool) -> None:
    pattern = entry["url_pattern"]
    if pattern is None:
        return
    template = pattern["template"]
    require(pattern["kind"] in URL_KINDS, "url_template",
            f"{where}: url_pattern.kind must be one of {list(URL_KINDS)}")
    require(text(pattern["source"]) and bool(DATE.fullmatch(pattern["read_utc_date"])), "url_template",
            f"{where}: a URL pattern needs the source it was read in and the date it was read")
    require(bool(TEMPLATE_TEXT.fullmatch(template)), "url_template",
            f"{where}: the template must be https, with a fixed host and path segments made of ids and "
            "placeholders. A query string, a fragment and percent-encoding are refused: they are where text goes")
    names = _placeholders(template)
    remainder = re.sub(r"\{[^{}]*\}", "", template)
    require(all(name in PLACEHOLDERS for name in names) and "{" not in remainder and "}" not in remainder,
            "url_template", f"{where}: placeholders must be among {list(PLACEHOLDERS)}; got {_shown(names)}")
    host = template[len("https://"):].split("/")[0]
    require("{" not in host, "url_template", f"{where}: the host is fixed text, not a placeholder")
    require(host.endswith(FIXTURE_HOST_SUFFIX) == synthetic, "synthetic_label",
            f"{where}: a synthetic registry links only to a {FIXTURE_HOST_SUFFIX} host, and a real registry never")
    neuronpedia = entry["neuronpedia"] or {}
    for name in ("model_id", "source_set", "source_id"):
        require(name not in names or _usable_id(neuronpedia.get(name)), "url_template",
                f"{where}: the template uses {{{name}}} and the entry records no usable neuronpedia.{name}")


def _check_entry(entry: Any, where: str, synthetic: bool) -> None:
    require(isinstance(entry, dict), "invalid_input", f"{where}: an entry must be an object")
    require(bool(REGISTRY_ID.fullmatch(str(entry["registry_id"]))), "registry_entry", f"{where}: registry_id")
    require(entry["representation_type"] in REPRESENTATION_TYPES, "representation_type",
            f"{where}: representation_type must be one of {list(REPRESENTATION_TYPES)}")
    require(entry["method"] in METHOD_IDS, "unknown_method",
            f"{where}: method is not one of the method ids in scripts/experiments/common.py (METHOD_IDS)")
    require(entry["calibration"] in CALIBRATIONS and entry["use"] in USES, "registry_entry",
            f"{where}: calibration must be one of {list(CALIBRATIONS)} and use one of {list(USES)}")

    model = entry["model"]
    require(text(model["hf_id"]) and (model["study_id"] is None or bool(ID_TOKEN.fullmatch(model["study_id"]))),
            "registry_entry", f"{where}: model.hf_id and model.study_id")
    require(model["revision"] is None or bool(HEX40.fullmatch(model["revision"])), "registry_entry",
            f"{where}: model.revision must be a 40-hex commit or null")
    fixture = model["hf_id"].startswith(FIXTURE_PREFIX)
    require(fixture == synthetic and (entry["use"] == "synthetic_fixture") == synthetic, "synthetic_label",
            f"{where}: a synthetic registry holds only {FIXTURE_PREFIX} models with use 'synthetic_fixture', "
            "and a real registry holds none")

    neuronpedia = entry["neuronpedia"]
    if neuronpedia is not None:
        require(bool(ID_TOKEN.fullmatch(neuronpedia["model_id"])) and _optional_id(neuronpedia["source_set"])
                and _optional_id(neuronpedia["source_id"]) and text(neuronpedia["id_source"]), "registry_entry",
                f"{where}: neuronpedia ids must be id tokens and id_source must say where they were read")

    site = entry["site"]
    layers = site["layers"]
    require(site["layer_index_base"] in (None, 0, 1), "layer_metadata", f"{where}: site.layer_index_base")
    require(layers is None or (bool(layers) and all(integer(x) for x in layers) and len(set(layers)) == len(layers)),
            "layer_metadata", f"{where}: site.layers must be distinct non-negative integers, or null")
    component = entry["component_id"]
    require(component is None or component == NOT_APPLICABLE
            or (isinstance(component, dict) and text(component["form"]) and text(component["index_kind"])
                and text(component["source"])),
            "registry_entry", f"{where}: component_id is {{form, index_kind, source}}, '{NOT_APPLICABLE}' or null")
    require(not isinstance(component, dict) or "count" not in component
            or (integer(component["count"], 1) and component["count"] <= MAX_COMPONENT_ID), "registry_entry",
            f"{where}: component_id.count, when recorded, is the number of components one layer's source holds: "
            f"an integer from 1 to {MAX_COMPONENT_ID}")

    sha = entry["fitted_artifact_sha256"]
    require(sha is None or sha == NOT_APPLICABLE or bool(HEX64.fullmatch(sha)), "registry_entry",
            f"{where}: fitted_artifact_sha256 must be 64 hex, '{NOT_APPLICABLE}' or null")
    artifact = entry["artifact"]
    if artifact is not None:
        require(text(artifact["id"]), "registry_entry", f"{where}: artifact.id")
        for key in ("revision", "fit_model_revision"):
            require(artifact[key] is None or bool(HEX40.fullmatch(artifact[key])), "registry_entry",
                    f"{where}: artifact.{key} must be a 40-hex commit or null")
    stamp = entry["label_source"]["retrieved_utc"]
    require(stamp is None or stamp == NOT_APPLICABLE or bool(UTC_STAMP.fullmatch(stamp)), "registry_entry",
            f"{where}: label_source.retrieved_utc must be a UTC date or timestamp")

    verification = entry["verification"]
    status, evidence = verification["status"], verification["evidence"]
    require(status in VERIFICATION_STATUSES, "verification_status",
            f"{where}: verification.status must be one of {list(VERIFICATION_STATUSES)}")
    require(bool(evidence) and all(text(e["source"]) and text(e["states"]) and bool(DATE.fullmatch(e["date"]))
                                   for e in evidence) and bool(DATE.fullmatch(verification["checked_utc_date"])),
            "verification_evidence", f"{where}: a status needs evidence items {{source, date, states}} and a "
            "checked_utc_date")
    hosted = verification["hosted_checkpoint_revision"]
    require(hosted is None or bool(HEX40.fullmatch(hosted)), "registry_entry",
            f"{where}: verification.hosted_checkpoint_revision must be a 40-hex commit or null")
    if status == VERIFIED:
        require(neuronpedia is not None and model["revision"] is not None and hosted == model["revision"],
                "verification_status",
                f"{where}: verified_exact needs a recorded mapping and a hosted checkpoint revision equal to "
                "the study revision. An alias with no checkpoint revision is alias_unverified_checkpoint")
    require(not entry["links_enabled"] or status == VERIFIED, "links_without_verification",
            f"{where}: links_enabled is true and the status is {status!r}; only verified_exact permits a link")

    _check_url_pattern(entry, where, synthetic)
    nulls = [p for key in sorted(entry) if key != "not_recorded" for p in null_pointers(entry[key], f"/{key}")]
    _check_not_recorded(entry, nulls, where)


@_guarded
def validate_registry(doc: Any) -> dict[str, Any]:
    """Validate a registry document and return it. Refuses a link flag without ``verified_exact``, an unlisted
    null, an unknown vocabulary word, a duplicate id and a URL template that could carry text."""
    require(isinstance(doc, dict) and doc.get("schema_version") == REGISTRY_SCHEMA, "schema_version",
            f"Expected {REGISTRY_SCHEMA}")
    require_structure(doc, "representation_registry")
    require(doc["verification_statuses"] == list(VERIFICATION_STATUSES), "verification_status",
            f"verification_statuses must repeat {list(VERIFICATION_STATUSES)}")
    require(bool(DATE.fullmatch(doc["as_of"])), "registry_entry", "as_of must be a date")
    for number, item in enumerate(doc.get("sources_not_read", [])):
        # The URL is not repeated: one that fails this check may carry a query string.
        require(bool(PLAIN_URL.fullmatch(item["url"])) and bool(DATE.fullmatch(item["attempted_utc_date"]))
                and text(item["result"]), "registry_entry",
                f"sources_not_read[{number}] needs a plain https url, an attempted_utc_date and a result")
    seen: set[str] = set()
    for number, entry in enumerate(doc["entries"]):
        _check_entry(entry, f"entries[{number}]", doc["synthetic"])
        require(entry["registry_id"] not in seen, "duplicate_entry", f"a second entry {entry['registry_id']!r}")
        seen.add(entry["registry_id"])
    return doc


def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    """The validated registry at ``path`` (default: the committed registry). Reads one local file."""
    return validate_registry(read_json(Path(path) if path is not None else REGISTRY_PATH))


def entry_by_id(registry: Mapping[str, Any], registry_id: str) -> dict[str, Any] | None:
    return next((e for e in registry["entries"] if e["registry_id"] == registry_id), None)


@dataclass(frozen=True)
class Resolution:
    """Result of ``resolve``. ``status`` is ``mapped``, ``no_mapping`` or ``ambiguous``; only ``mapped`` carries
    an entry. ``verified`` is true only for a ``verified_exact`` entry, so an alias never reads as verified."""
    status: str
    entry: dict[str, Any] | None
    reason: str
    query: dict[str, Any]
    candidates: tuple[str, ...] = ()
    layer_coverage: str = NOT_APPLICABLE

    @property
    def mapped(self) -> bool:
        return self.status == "mapped"

    @property
    def verified(self) -> bool:
        return self.entry is not None and self.entry["verification"]["status"] == VERIFIED


def resolve(study_model_id: str, representation_type: str, layer: int | None = None, *, method: str | None = None,
            source_set: str | None = None, artifact_id: str | None = None, require_verified: bool = False,
            registry: Mapping[str, Any] | None = None) -> Resolution:
    """The registry entry for a study model and representation type, or a typed result that says why none.

    Matching is on the engine's study id, never on a Neuronpedia id: an alias is a field of an entry and is not a
    second key. ``study_model_id`` must be a non-empty string (``invalid_input`` otherwise), so an entry whose
    model has no study id (a basis for a model the engine does not run) is never returned. ``layer`` excludes
    an entry whose recorded layers omit it; an entry that records no layer list still matches and the result
    says ``layer_coverage: 'not_recorded'``. Two matching entries give ``ambiguous``
    with both ids; the caller narrows with ``method``, ``source_set`` or ``artifact_id``. Nothing is picked for
    the caller. ``require_verified`` turns a match that is not ``verified_exact`` into ``no_mapping``.
    """
    require(text(study_model_id), "invalid_input",
            "study_model_id must be a non-empty string, the engine's study id; got "
            f"{'an empty string' if isinstance(study_model_id, str) else type(study_model_id).__name__}. An entry "
            "whose model has no study id is not an engine model and is never matched")
    require(isinstance(representation_type, str) and representation_type in REPRESENTATION_TYPES,
            "representation_type", f"representation_type must be one of {list(REPRESENTATION_TYPES)}")
    require(layer is None or integer(layer), "layer_metadata", "layer must be a non-negative integer or None")
    registry = registry if registry is not None else load_registry()
    query = {"study_model_id": study_model_id, "representation_type": representation_type, "layer": layer,
             "method": method, "source_set": source_set, "artifact_id": artifact_id,
             "require_verified": require_verified}

    def none(reason: str, candidates: Iterable[str] = ()) -> Resolution:
        return Resolution("no_mapping", None, f"{REASON_NO_MAPPING}: {reason}", query, tuple(candidates))

    of_model = [e for e in registry["entries"] if e["model"]["study_id"] == study_model_id]
    if not of_model:
        return none(f"the registry has no entry for study model {study_model_id!r}")
    matches = [e for e in of_model if e["representation_type"] == representation_type]
    if not matches:
        return none(f"study model {study_model_id!r} has no {representation_type} entry; its entries are of type "
                    f"{sorted({e['representation_type'] for e in of_model})}, and types are not interchangeable")
    if method is not None:
        matches = [e for e in matches if e["method"] == method]
    if source_set is not None:
        matches = [e for e in matches if (e["neuronpedia"] or {}).get("source_set") == source_set]
    if artifact_id is not None:
        matches = [e for e in matches if (e["artifact"] or {}).get("id") == artifact_id]
    if not matches:
        return none("no entry matches the method, source set or artifact asked for")
    if layer is not None:
        inside = [e for e in matches if e["site"]["layers"] is None or layer in e["site"]["layers"]]
        if not inside:
            return none(f"layer {layer} is outside the recorded layers of {[e['registry_id'] for e in matches]}")
        matches = inside
    if len(matches) > 1:
        ids = tuple(sorted(e["registry_id"] for e in matches))
        return Resolution("ambiguous", None, f"{len(ids)} entries match; narrow the query", query, ids)
    entry = matches[0]
    status = entry["verification"]["status"]
    if require_verified and status != VERIFIED:
        return none(f"{entry['registry_id']} is {status}, not {VERIFIED}", [entry["registry_id"]])
    coverage = NOT_APPLICABLE if layer is None else "not_recorded" if entry["site"]["layers"] is None else "recorded"
    return Resolution("mapped", entry, f"mapped with verification status {status}", query, (entry["registry_id"],),
                      coverage)


# ------------------------------------------------------------------------------------------------ links

@dataclass(frozen=True)
class Link:
    """A URL, or None with the reason. ``reason`` is one of the three module constants."""
    url: str | None
    reason: str
    detail: str


def _check_ids(component_id: Any, layer: Any) -> None:
    """Type and size of the two integers a URL may hold. Neither value is repeated in the message."""
    require(integer(component_id), "free_text_in_url",
            "component_id must be a non-negative integer. Text, a label, a token or a prompt is never put in a URL")
    require(component_id < MAX_COMPONENT_ID, "free_text_in_url",
            f"component_id must be below {MAX_COMPONENT_ID} (2**20). An integer of that size is not a component "
            "index; a hash or other data written as a number is never put in a URL")
    require(layer is None or integer(layer), "free_text_in_url", "layer must be a non-negative integer or None")
    require(layer is None or layer < MAX_LAYER, "free_text_in_url", f"layer must be below {MAX_LAYER}")


def _component_count(entry: Mapping[str, Any]) -> int | None:
    """The number of components one layer's source holds, when the entry records it (``component_id.count``),
    else None. No entry of the committed registry records one on 2026-11-10."""
    component = entry["component_id"]
    return component.get("count") if isinstance(component, dict) else None


def build_link(entry: Mapping[str, Any], component_id: int, *, layer: int | None = None) -> Link:
    """A link to the external page for one component, or ``Link(None, reason, detail)``.

    A URL is returned only when the entry's ``links_enabled`` is true (which the validator allows only for
    ``verified_exact``) and the registry records a URL pattern with its source. The URL is the recorded template
    with ids from the registry and the two integers given here. This function takes no text. A non-integer
    ``component_id`` or ``layer`` is refused (``free_text_in_url``) before anything else is looked at, and so is
    a ``component_id`` at or above ``MAX_COMPONENT_ID`` (2**20) or a ``layer`` at or above ``MAX_LAYER`` (4096).
    When the entry records a component count (``component_id.count``), a ``component_id`` at or above it is
    refused with the same code, before the entry's status is looked at.
    """
    _check_ids(component_id, layer)
    synthetic = str(entry["model"]["hf_id"]).startswith(FIXTURE_PREFIX)
    named = entry.get("registry_id")
    where = f"entry {named!r}" if isinstance(named, str) and REGISTRY_ID.fullmatch(named) else "entry"
    _guarded(_check_entry)(entry, where, synthetic)
    count = _component_count(entry)
    require(count is None or component_id < count, "free_text_in_url",
            f"component_id is at or above the component count the entry records ({count}); it names no "
            "component of this representation")
    status = entry["verification"]["status"]
    if not entry["links_enabled"]:
        return Link(None, REASON_NOT_VERIFIED, f"verification status is {status}; links are off for this entry")
    pattern = entry["url_pattern"]
    if pattern is None:
        return Link(None, REASON_NO_PATTERN, "the registry records no URL pattern for this entry")
    template = pattern["template"]
    names = _placeholders(template)
    require("layer" not in names or layer is not None, "link_arguments", "the recorded pattern needs a layer")
    layers = entry["site"]["layers"]
    require(layer is None or layers is None or layer in layers, "layer_metadata",
            f"layer {layer} is outside the entry's recorded layers {layers}")
    neuronpedia = entry["neuronpedia"] or {}
    values = {"model_id": neuronpedia.get("model_id"), "source_set": neuronpedia.get("source_set"),
              "source_id": neuronpedia.get("source_id"), "layer": layer, "component": component_id}
    url = template
    for name in names:
        url = url.replace("{" + name + "}", str(values[name]))
    require(bool(BUILT_URL.fullmatch(url)), "free_text_in_url", "the assembled URL left the id-only character set")
    return Link(url, LINK_BUILT, f"{pattern['kind']} pattern read in {pattern['source']} on {pattern['read_utc_date']}")


def local_record(entry: Mapping[str, Any], component_id: int, layer: int | None,
                 record: Mapping[str, Any] | None) -> dict[str, Any]:
    """What a reader needs to inspect one component with no external page: identity, status and the caller's
    own structured record (scores, labels, ranks) under ``record``."""
    return {
        "registry_id": entry["registry_id"],
        "representation_type": entry["representation_type"],
        "method": entry["method"],
        "model": dict(entry["model"]),
        "neuronpedia": dict(entry["neuronpedia"]) if entry["neuronpedia"] is not None else None,
        "site": dict(entry["site"]),
        "layer": layer,
        "component_id": component_id,
        "fitted_artifact_sha256": entry["fitted_artifact_sha256"],
        "artifact": dict(entry["artifact"]) if entry["artifact"] is not None else None,
        "label_source": dict(entry["label_source"]),
        "verification": {"status": entry["verification"]["status"],
                         "checked_utc_date": entry["verification"]["checked_utc_date"]},
        "not_recorded": list(entry["not_recorded"]),
        "record": dict(record) if record is not None else None,
        "inspectable_offline": True,
    }


def link_or_fallback(target: Resolution | Mapping[str, Any], component_id: int, *, layer: int | None = None,
                     record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``{"link": url | None, "reason": ..., "detail": ..., "local": {...}}`` for one component.

    ``local`` is always present and never depends on the external site, so a bundle stays usable when the site
    is unreachable, renamed or gone. ``target`` is a registry entry or a ``Resolution``; an unmapped resolution
    gives ``link: None`` with the "no mapping" reason and a local record built from the query.
    """
    _check_ids(component_id, layer)
    if isinstance(target, Resolution):
        if target.entry is None:
            return {"link": None, "reason": REASON_NO_MAPPING, "detail": target.reason,
                    "local": {"registry_id": None, "query": dict(target.query), "candidates": list(target.candidates),
                              "layer": layer, "component_id": component_id,
                              "record": dict(record) if record is not None else None, "inspectable_offline": True}}
        entry: Mapping[str, Any] = target.entry
    else:
        entry = target
    link = build_link(entry, component_id, layer=layer)
    return {"link": link.url, "reason": link.reason, "detail": link.detail,
            "local": local_record(entry, component_id, layer, record)}


# ------------------------------------------------------------------------------------------------ snapshots

def _stamp(value: Any, code: str, name: str) -> None:
    require(value is None or (isinstance(value, str) and bool(UTC_STAMP.fullmatch(value))), code,
            f"{name} must be a UTC date (YYYY-MM-DD) or timestamp (YYYY-MM-DDTHH:MM:SSZ), or None")


def _plain_url(value: Any, code: str, name: str) -> None:
    require(value is None or (isinstance(value, str) and bool(PLAIN_URL.fullmatch(value))), code,
            f"{name} must be an https URL with no query string, fragment or user part. A pre-signed download "
            "URL carries a credential in its query string and is not recorded")


def record_snapshot(path: Path | str, source_url: str | None, retrieved_utc: str | None) -> dict[str, Any]:
    """Describe a bulk-export file somebody already downloaded: ``{sha256, bytes, source_url, retrieved_utc}``.

    This function reads the local file and hashes it. It fetches nothing and reads no clock: the caller states
    where the file came from and when. A provenance value that is not known is passed as None and its pointer
    is listed in ``not_recorded``; it is never filled in.
    """
    file = Path(path)
    require(file.is_file(), "snapshot_missing", f"{file} is not a file")
    _plain_url(source_url, "snapshot_url", "source_url")
    _stamp(retrieved_utc, "snapshot_provenance", "retrieved_utc")
    data = file.read_bytes()
    return {"schema_version": SNAPSHOT_SCHEMA, "sha256": sha256_bytes(data), "bytes": len(data),
            "source_url": source_url, "retrieved_utc": retrieved_utc,
            "not_recorded": [f"/{key}" for key, value in (("retrieved_utc", retrieved_utc), ("source_url", source_url))
                             if value is None]}


@_guarded
def verify_snapshot(path: Path | str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Compare a local file with its snapshot record. Refuses ``snapshot_missing``, ``snapshot_size`` or
    ``snapshot_hash``. A match returns ``provenance_complete``: false when the record lists a missing source
    or retrieval time, which a matching hash does not repair."""
    require(isinstance(record, dict) and record.get("schema_version") == SNAPSHOT_SCHEMA, "schema_version",
            f"Expected {SNAPSHOT_SCHEMA}")
    require(set(record) == {"schema_version", "sha256", "bytes", "source_url", "retrieved_utc", "not_recorded"},
            "snapshot_provenance", "A snapshot record has exactly sha256, bytes, source_url, retrieved_utc, "
            "not_recorded and schema_version")
    require(bool(HEX64.fullmatch(str(record["sha256"]))) and integer(record["bytes"]), "snapshot_provenance",
            "sha256 and bytes")
    _plain_url(record["source_url"], "snapshot_url", "source_url")
    _stamp(record["retrieved_utc"], "snapshot_provenance", "retrieved_utc")
    _check_not_recorded(record, [f"/{k}" for k in ("retrieved_utc", "source_url") if record[k] is None], "snapshot")
    file = Path(path)
    require(file.is_file(), "snapshot_missing", f"{file} is not a file")
    data = file.read_bytes()
    require(len(data) == record["bytes"], "snapshot_size", f"{file} has {len(data)} bytes, not {record['bytes']}")
    actual = sha256_bytes(data)
    require(actual == record["sha256"], "snapshot_hash", f"{file} has SHA-256 {actual}, not the recorded value")
    return {"status": "verified", "sha256": actual, "bytes": len(data),
            "provenance_complete": not record["not_recorded"], "not_recorded": list(record["not_recorded"])}


# ------------------------------------------------------------------------------------------------ request records

def _normalized(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _id_string(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_VALUE.fullmatch(value))


def _number(value: Any) -> bool:
    return value is None or isinstance(value, bool) or (type(value) in (int, float) and math.isfinite(value))


def _string_violation(item: str) -> str:
    """The code for a string that sits where no string is allowed."""
    return "secret_in_record" if _credential_shaped(item) else "free_text_in_record"


def _record_violations(value: Any, path: str) -> list[tuple[str, str]]:
    """``(refusal code, JSON pointer)`` for everything in a settings or identity block that the three rules
    above refuse. A pointer names keys that passed the key-form check and the credential-prefix check, and list
    positions; a value is never copied into a message, and neither is a key that failed one of those two checks
    (it is reported by its position among the object's keys in sorted order)."""
    found: list[tuple[str, str]] = []
    if isinstance(value, list):
        for number, item in enumerate(value):
            where = f"{path}/{number}"
            if isinstance(item, (dict, list)):
                found.extend(_record_violations(item, where))
            elif isinstance(item, str):
                found.append((_string_violation(item), where))
            elif not _number(item):
                found.append(("free_text_in_record", where))
        return found
    for number, key in enumerate(sorted(value, key=str)):
        item = value[key]
        if not isinstance(key, str) or not SETTING_KEY.fullmatch(key):
            # Not echoed: a key that is not a short identifier may itself be the text that must not be stored.
            found.append(("free_text_in_record", f"{path}/(key number {number}: not a short identifier)"))
            continue
        if _credential_prefixed([key]):
            # Not echoed either: a key and its value may have been swapped.
            found.append(("secret_in_record", f"{path}/(key number {number}: starts like a credential)"))
            continue
        where = f"{path}/{key}"
        name = _normalized(key)
        hashed = name.endswith(HASH_KEY_SUFFIX)
        counted = name in COUNT_SETTING_KEYS
        stem = name[:-len(HASH_KEY_SUFFIX)] if hashed else name
        textual = not hashed and not counted and any(fragment in name for fragment in TEXT_FRAGMENTS)
        secret = not counted and any(fragment in stem for fragment in SECRET_FRAGMENTS
                                     if not (hashed and fragment == "token"))
        if textual:
            found.append(("prompt_text_in_record", where))
        if secret:
            found.append(("secret_in_record", where))
        if textual or secret:
            continue
        if hashed:
            if not (item is None or (isinstance(item, str) and HEX64.fullmatch(item))):
                found.append(("free_text_in_record", where))
        elif counted:
            if not (isinstance(item, bool) or integer(item)):
                found.append(("free_text_in_record", where))
        elif isinstance(item, str):
            if _credential_shaped(item, revision=name in REVISION_KEYS):
                found.append(("secret_in_record", where))
            elif name not in ID_VALUE_KEYS or not _id_string(item):
                found.append(("free_text_in_record", where))
        elif name in ID_VALUE_KEYS and isinstance(item, list):
            # One key takes a list of strings, and then only a short list of distinct upper-case constants.
            # Under every other id key a list is not an id, whatever it holds.
            strings = [one for one in item if isinstance(one, str)]
            if any(_credential_shaped(one) for one in strings):
                found.append(("secret_in_record", where))
            elif not (name in LIST_VALUE_KEYS and 1 <= len(item) <= MAX_LIST_ITEMS and len(strings) == len(item)
                      and all(LIST_ITEM.fullmatch(one) for one in strings) and len(set(strings)) == len(strings)):
                found.append(("free_text_in_record", where))
        elif isinstance(item, (dict, list)):
            found.extend(_record_violations(item, where))
        elif not _number(item):
            found.append(("free_text_in_record", where))
    return found


@_guarded
def validate_request_record(doc: Any) -> dict[str, Any]:
    """Validate a bounded-API request record and return it.

    The record has ``endpoint``, ``effective_request_settings``, ``service_identity``, ``response_sha256``,
    ``retrieved_utc`` and ``not_recorded``. ``effective_request_settings`` holds the settings the service
    applied, defaults included, with the input named by hash. ``service_identity`` says which host and which
    model or instrument answered; a revision the service did not report is null and listed. This is a
    structure. Nothing here sends it.

    Neither block may hold prompt text or a credential, at any depth. The check has three parts:

    * by key name: a key whose letters and digits, lowercased, contain a credential fragment (``key``,
      ``token``, ``secret``, ``auth``, ...: ``secret_in_record``) or a text fragment (``prompt``, ``text``,
      ``message``, ``content``, ``input``, ``query``, ``body``, ``slug``, ...: ``prompt_text_in_record``) is
      refused, whatever its value. A key ending in ``sha256`` and four counted settings are the exceptions, each
      with its own value rule;
    * by value type: a string is accepted only under a known id key (``model_id``, ``source_set``, ``service``,
      ``instrument_revision``, ``type``, ...), where it must be one id (64 characters at most, no whitespace,
      optionally ``owner/name``), or under a hash key, where it must be 64 hex digits. A list of strings is
      accepted under one key, ``type``, the only field of the engine's own request bodies that holds one
      (``scripts/jlens_readout.py``: ``"type": [lens_type]``): 1 to 8 distinct upper-case constants such as
      ``JACOBIAN_LENS`` (``[A-Z][A-Z0-9_]{0,31}``). Every other value is null, a boolean, a finite number, an
      object or a list of those (``free_text_in_record`` otherwise). A string with whitespace is therefore
      refused under every key, and a string inside a list is refused everywhere except in that one list;
    * by the credential screen (``secret_in_record``): a string is refused when a '/'-separated part of it
      starts like a credential of a known issuer (``sk-``, ``hf_``, ``AIza``, ``ghp_``, ``gho_``,
      ``github_pat_``, ``xox``, in any letter case). The same prefix test is applied to every key name, to every
      segment of the endpoint path and to every label of the endpoint host (there also with a hyphen in place
      of the underscore). An id value is also refused when it holds a run of more than 24 letters and digits
      with no separator that draws on at least two of lower-case letters, upper-case letters and digits, which
      is the form of an issued token. The one exception is 40 or 64 lower-case hex digits under
      ``model_revision``, ``instrument_revision`` or ``dictionary_revision``; a hash key holds 64 hex digits by
      its own rule.

    ``not_recorded`` is checked before it is used: every entry is a JSON pointer made of key names and list
    indexes under one of the record's four nullable roots, and every entry must point at a null field.

    No refusal of this function repeats a value, an entry of ``not_recorded``, or a key that failed the key-form
    check or the prefix test. A message names keys that passed both, positions and counts.

    What this cannot see. A credential that passes the screen: one of 24 characters or fewer, one with a
    separator at least every 24 characters, one made of a single character class (for example lower-case
    letters only), and one from an issuer whose prefix is not in the list. A short text that has the form of
    an id and is stored under one of the id keys (one id, 64 characters per part), and up to 8 upper-case words
    in the ``type`` list. Words spelled as a key name, or as one of the at most 8 segments of the endpoint
    path. A number that encodes something. The check is on names, types, character classes and string forms.
    It does not read meaning, and a record still needs a person's review before it is committed.
    """
    keys = {"schema_version", "endpoint", "effective_request_settings", "service_identity", "response_sha256",
            "retrieved_utc", "not_recorded"}
    require(isinstance(doc, dict) and doc.get("schema_version") == REQUEST_SCHEMA, "schema_version",
            f"Expected {REQUEST_SCHEMA}")
    require(set(doc) == keys, "request_record", f"A request record has exactly {sorted(keys)}")
    _check_record_pointers(doc["not_recorded"], REQUEST_POINTER_ROOTS, "request record")
    endpoint = doc["endpoint"]
    require(isinstance(endpoint, dict) and set(endpoint) == {"method", "host", "path"}
            and isinstance(endpoint["method"], str) and endpoint["method"] in ("GET", "POST")
            and isinstance(endpoint["host"], str) and bool(ENDPOINT_HOST.fullmatch(endpoint["host"]))
            and isinstance(endpoint["path"], str) and bool(ENDPOINT_PATH.fullmatch(endpoint["path"]))
            and endpoint["path"].count("/") <= MAX_PATH_SEGMENTS, "request_record",
            "endpoint is {method: GET|POST, host, path}; the host has at most 8 labels of letters, digits and "
            f"hyphens; the path has no query string and no text, at most {MAX_PATH_SEGMENTS} segments, and each "
            "segment has at most 64 characters")
    require(not _credential_prefixed(endpoint["path"].split("/"))
            and not _credential_prefixed(endpoint["host"].split("."), host=True), "secret_in_record",
            "endpoint: a path segment or a host label starts like a credential of a known issuer. It is not "
            "repeated here")
    settings, identity = doc["effective_request_settings"], doc["service_identity"]
    require(isinstance(settings, dict) and isinstance(identity, dict), "request_record",
            "effective_request_settings and service_identity must be objects")
    require({"service", "model_id", "instrument_revision"} <= set(identity) and text(identity["service"]),
            "request_record", "service_identity needs service, model_id and instrument_revision")
    refused = (_record_violations(settings, "/effective_request_settings")
               + _record_violations(identity, "/service_identity"))
    require(not refused, refused[0][0] if refused else "request_record",
            "a request record holds no prompt text, no credential and no free string. Refused, by key: "
            f"{[f'{where} ({code})' for code, where in refused[:16]]}"
            + (f" and {len(refused) - 16} more" if len(refused) > 16 else ""))
    require(doc["response_sha256"] is None or bool(HEX64.fullmatch(str(doc["response_sha256"]))), "request_record",
            "response_sha256 must be 64 hex or null")
    _stamp(doc["retrieved_utc"], "request_record", "retrieved_utc")
    nulls = [p for key in sorted(keys - {"not_recorded", "schema_version"}) for p in null_pointers(doc[key], f"/{key}")]
    _check_not_recorded(doc, nulls, "request record")
    return doc


@_guarded
def request_record(*, endpoint: Mapping[str, Any], effective_request_settings: Mapping[str, Any],
                   service_identity: Mapping[str, Any], response_sha256: str | None, retrieved_utc: str | None,
                   not_recorded: Iterable[str] = ()) -> dict[str, Any]:
    """Assemble and validate a request record. The caller lists every null pointer; none is computed here.

    ``not_recorded`` is sorted and de-duplicated when every entry is a string; a list that holds anything else
    is passed on as given and ``validate_request_record`` refuses it by position."""
    listed = list(not_recorded)
    if all(isinstance(entry, str) for entry in listed):
        listed = sorted(set(listed))
    return validate_request_record({
        "schema_version": REQUEST_SCHEMA, "endpoint": dict(endpoint),
        "effective_request_settings": dict(effective_request_settings), "service_identity": dict(service_identity),
        "response_sha256": response_sha256, "retrieved_utc": retrieved_utc, "not_recorded": listed,
    })


# ------------------------------------------------------------------------------------------------ explanations

def token_list_label(label_id: str, tokens: Iterable[str], *, source: Mapping[str, Any],
                     scorer: Mapping[str, Any] | None) -> dict[str, Any]:
    """A label made from a token list alone. It is stored with basis ``token_list_only`` and the flag
    ``not_a_clinical_concept_name``: a list of top tokens is an observation about a vocabulary readout, and no
    step here turned it into the name of a clinical concept."""
    listed = [str(token) for token in tokens]
    require(bool(listed), "token_list_label", "A token-list label needs at least one token")
    return {"label_id": label_id, "text": " | ".join(listed), "tokens": listed, "basis": TOKEN_LIST_BASIS,
            "flags": [TOKEN_LIST_FLAG], "status": LABEL_STATUS, "source": dict(source),
            "scorer": dict(scorer) if scorer is not None else None}


def _closed(node: Any, required: Iterable[str], optional: Iterable[str], where: str, code: str) -> None:
    """``node`` is an object with every key of ``required`` and no key outside ``required`` and ``optional``.
    A generic score key is ``merged_score``; any other missing or extra key is ``code``."""
    require(isinstance(node, dict), code, f"{where} must be an object")
    generic = [key for key in node if key in GENERIC_SCORE_KEYS
               or _normalized(str(key)).endswith(("score", "scores"))]
    require(not generic, "merged_score", f"{where}: generic score keys are refused: {_shown(generic)}")
    required, allowed = set(required), set(required) | set(optional)
    require(required <= set(node) <= allowed, code,
            f"{where} holds exactly {sorted(required)}"
            + (f" and optionally {sorted(allowed - required)}" if allowed - required else "")
            + f"; missing {sorted(required - set(node))}, not allowed {_shown(set(node) - allowed)}")


def _check_scorer(scorer: Any, where: str, code: str) -> None:
    """A scorer is ``{name, version}`` and nothing else: a name, and a version that is a string or null. A
    number has no place in it; a score belongs in one of the four quantity fields."""
    _closed(scorer, SCORER_KEYS, (), where, code)
    require(text(scorer["name"]) and (scorer["version"] is None or isinstance(scorer["version"], str)), code,
            f"{where}: name must be text and version a string or null")


def _check_quantity(record: Any, field: str, where: str, label_ids: set[str]) -> None:
    require(isinstance(record, dict), "invalid_input", f"{where}: a quantity record must be an object")
    generic = sorted(GENERIC_SCORE_KEYS.intersection(record))
    require(not generic, "merged_score", f"{where}: generic score keys are refused: {generic}")
    kind = record.get("kind")
    require(kind == field, "score_kind_mismatch",
            f"{where}: a record of {'kind ' + kind if kind in QUANTITY_KINDS else 'another kind'} is filed under "
            f"{field}. The four quantities are different measurements and are not moved between fields")
    extra = set(record) - set(QUANTITY_FIELDS[field])
    require(not extra, "quantity_fields", f"{where}: {field} does not carry {_shown(extra)}")
    require(text(record.get("source")), "quantity_fields", f"{where}: source")
    value = record.get("value")
    if value is None:
        require(text(record.get("missing_reason")), "missing_value",
                f"{where}: a missing value is null with a missing_reason. It is never zero")
    else:
        require("missing_reason" not in record, "missing_value", f"{where}: missing_reason with a value")
        require(type(value) in (int, float) and math.isfinite(value), "quantity_fields", f"{where}: value")
    if field in ("feature_interpretability_score", "label_prediction_score"):
        require(isinstance(record.get("scorer"), dict) and text(record.get("scale")), "quantity_fields",
                f"{where}: {field} needs scorer {{name, version}} and a scale")
        _check_scorer(record["scorer"], f"{where}.scorer", "quantity_fields")
    if field == "label_prediction_score":
        require(record.get("label_id") in label_ids, "quantity_fields",
                f"{where}: label_id must name one of this feature's labels")
    if field == "lens_token_rank":
        require(record.get("lens") in LENS_METHODS and integer(record.get("layer")) and integer(record.get("token_id"))
                and record.get("rank_base") in (0, 1) and isinstance(record.get("filtered"), bool), "quantity_fields",
                f"{where}: lens_token_rank needs lens, layer, token_id, rank_base (0 or 1) and filtered")
        require(value is None or (type(value) is int and value >= record["rank_base"]), "quantity_fields",
                f"{where}: a rank is an integer at or above its rank_base")
    if field == "clinical_outcome":
        require(text(record.get("outcome_id")) and record.get("owner") == OUTCOME_OWNER and text(record.get("scale")),
                "quantity_fields", f"{where}: clinical_outcome needs outcome_id, a scale and owner '{OUTCOME_OWNER}'")


@_guarded
def validate_feature_explanations(doc: Any) -> dict[str, Any]:
    """Validate the explanation record of one component and return it.

    ``labels`` keeps every competing label, each with ``source`` and ``scorer``; no key selects a winner. The
    key sets of a label (``label_id``, ``text``, ``basis``, ``flags``, ``status``, ``source``, ``scorer`` and,
    for a token-list label, ``tokens``), of a source and of a scorer are closed, and a flag is one of the known
    flags. A rank, a confidence, a "best" marker or a merged number therefore has no key to sit under inside a
    label, its source or its scorer. A label that carries ``tokens`` needs the token-list flag whatever basis
    it declares.
    ``quantities`` has four fields: ``feature_interpretability_score`` (how well any description accounts for
    the component, under a named scorer), ``label_prediction_score`` (how well one named label predicts the
    activations, under a named scorer), ``lens_token_rank`` (the rank of a token in a lens readout at a layer)
    and ``clinical_outcome`` (a study outcome that PatientWords owns, referenced by id). A record under the
    wrong field, a generic ``score`` key and an unknown field are refused.
    """
    keys = {"schema_version", "registry_id", "layer", "component", "labels", "quantities", "not_recorded"}
    require(isinstance(doc, dict) and doc.get("schema_version") == EXPLANATION_SCHEMA, "schema_version",
            f"Expected {EXPLANATION_SCHEMA}")
    generic = sorted(GENERIC_SCORE_KEYS.intersection(doc))
    require(not generic, "merged_score", f"generic score keys are refused: {generic}")
    selection = sorted(LABEL_SELECTION_KEYS.intersection(doc))
    require(not selection, "label_selection", f"{selection}: every label is kept; none is stored as the label")
    require(set(doc) == keys, "explanation_record", f"An explanation record has exactly {sorted(keys)}")
    require(bool(REGISTRY_ID.fullmatch(str(doc["registry_id"]))) and integer(doc["component"])
            and (doc["layer"] == NOT_APPLICABLE or integer(doc["layer"])), "explanation_record",
            "registry_id, component and layer")

    labels = doc["labels"]
    require(isinstance(labels, list), "explanation_record", "labels must be a list")
    label_ids: set[str] = set()
    for number, label in enumerate(labels):
        where = f"labels[{number}]"
        _closed(label, LABEL_KEYS, LABEL_OPTIONAL_KEYS, where, "explanation_record")
        require(text(label["label_id"]) and label["label_id"] not in label_ids, "duplicate_label",
                f"{where}: label_id must be present and distinct")
        label_ids.add(label["label_id"])
        require(text(label["text"]) and isinstance(label["basis"], str) and label["basis"] in LABEL_BASES
                and isinstance(label["flags"], list), "explanation_record",
                f"{where}: text, basis (one of {list(LABEL_BASES)}) and flags")
        require(all(isinstance(flag, str) and flag in FLAG_TEXT for flag in label["flags"]), "explanation_record",
                f"{where}: flags holds only the known flags {sorted(FLAG_TEXT)}")
        require(label["status"] == LABEL_STATUS, "annotation_status",
                f"{where}: a label is stored with status '{LABEL_STATUS}'")
        if "tokens" in label:
            require(isinstance(label["tokens"], list) and bool(label["tokens"]) and all(
                text(token) for token in label["tokens"]), "token_list_label",
                f"{where}: tokens is a non-empty list of strings")
        require((label["basis"] != TOKEN_LIST_BASIS and "tokens" not in label) or TOKEN_LIST_FLAG in label["flags"],
                "token_list_label",
                f"{where}: a label built from a token list, or one that carries its tokens, has the flag "
                f"{TOKEN_LIST_FLAG!r} ({FLAG_TEXT[TOKEN_LIST_FLAG]}), whatever basis it declares")
        source, scorer = label["source"], label["scorer"]
        _closed(source, SOURCE_KEYS, (), f"{where}.source", "explanation_record")
        require(all(source[key] is None or isinstance(source[key], str) for key in SOURCE_KEYS),
                "explanation_record", f"{where}.source: every value is a string or null")
        if scorer is not None:
            _check_scorer(scorer, f"{where}.scorer", "explanation_record")
        _stamp(source["retrieved_utc"], "explanation_record", f"{where}.source.retrieved_utc")

    quantities = doc["quantities"]
    require(isinstance(quantities, dict), "explanation_record", "quantities must be an object")
    unknown = set(quantities) - set(QUANTITY_KINDS)
    require(not unknown, "merged_score",
            f"quantities holds only {list(QUANTITY_KINDS)}; {_shown(unknown)} would be a fifth, unnamed quantity")
    for field in QUANTITY_KINDS:
        records = quantities.get(field, [])
        require(isinstance(records, list), "explanation_record", f"quantities.{field} must be a list")
        for number, record in enumerate(records):
            _check_quantity(record, field, f"quantities.{field}[{number}]", label_ids)

    nulls = [p for number, label in enumerate(labels) for key in ("source", "scorer")
             for p in null_pointers(label[key], f"/labels/{number}/{key}")]
    _check_not_recorded(doc, nulls, "explanation record")
    return doc


def add_label(doc: Mapping[str, Any], label: Mapping[str, Any], not_recorded: Iterable[str] = ()) -> dict[str, Any]:
    """A copy of the explanation record with ``label`` appended. An existing label is never replaced: a second
    label with an existing ``label_id`` is refused (``duplicate_label``)."""
    updated = {**doc, "labels": [*doc["labels"], dict(label)],
               "not_recorded": sorted(set(doc["not_recorded"]) | set(not_recorded))}
    return validate_feature_explanations(updated)


def collect_quantity(kind: str, records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The records of one kind, unchanged and in order. A record of another kind refuses (``score_kind_merge``).
    This is the only gathering function in the module, and it computes nothing."""
    require(isinstance(kind, str) and kind in QUANTITY_KINDS, "score_kind_merge",
            f"kind must be one of {list(QUANTITY_KINDS)}")
    gathered = [dict(record) for record in records]
    other = [record.get("kind") for record in gathered if record.get("kind") != kind]
    named = sorted({found for found in other if isinstance(found, str) and found in QUANTITY_KINDS})
    require(not other, "score_kind_merge",
            f"{len(other)} record(s) of another kind ({named if named else 'not one of the four kinds'}) cannot be "
            f"gathered with {kind}: they measure different things")
    return gathered


# ------------------------------------------------------------------------------------------------ graph reference

GRAPH_REF_KEYS = {
    "": ("kind", "registry_id", "model", "neuronpedia", "graph", "input", "settings_sha256", "retrieved_utc",
         "not_recorded"),
    "model": ("study_id", "hf_id", "revision"),
    "neuronpedia": ("model_id", "source_set"),
    "graph": ("native_retained", "native_sha256", "native_bytes", "schema_version", "slug_sha256", "n_nodes",
              "n_links"),
    "input": ("prompt_sha256", "token_sha256"),
}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for key in value for s in _strings(value[key])]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


@_guarded
def validate_graph_reference(ref: Any, registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate an ``attribution_graph_ref/1`` payload: ids, hashes and source-set identity, and nothing else.

    The reference names a graph that lives elsewhere. It carries the registry id of the node representation, the
    study model identity, the Neuronpedia model id and source set the graph was generated with, the SHA-256 and
    size of the native graph JSON when it was kept, the graph's ``schema_version`` (which fixes how a node's
    feature index is encoded), node and link counts, the hashes of the prompt and token ids, and the hash of the
    generation settings. It carries no prompt, no slug (the engine's slugs embed prompt characters; only the
    slug's hash is kept), no label and no node list: the key set is closed and every string is checked against an
    id-only character set. With ``registry`` the ids are compared with the entry (``source_set_identity``), and
    so is the model: study id, Hugging Face id and revision (``graph_ref_identity``). Two ids can name different
    commits, so a reference whose ``model.revision`` differs from the entry's pin is refused. A reference whose
    revision is null (and therefore listed in ``not_recorded``) cannot be compared: the result then says
    ``model_revision_compared: false``, and it says the same when no registry is given.
    """
    require(isinstance(ref, dict) and ref.get("kind") == GRAPH_REF_KIND, "payload_kind", f"Expected {GRAPH_REF_KIND}")
    for block, keys in GRAPH_REF_KEYS.items():
        node = ref if not block else ref[block]
        require(isinstance(node, dict) and set(node) == set(keys), "graph_ref_keys",
                f"{block or 'reference'} has exactly the keys {sorted(keys)}"
                + (f"; missing {sorted(set(keys) - set(node))}, not allowed {_shown(set(node) - set(keys))}"
                   if isinstance(node, dict) else ""))
    loose = [s for s in _strings(ref) if not NO_FREE_TEXT.fullmatch(s)]
    require(not loose, "free_text_in_reference",
            f"{len(loose)} string value(s) are not ids, hashes, dates or pointers. A graph reference holds no text")
    require(bool(REGISTRY_ID.fullmatch(ref["registry_id"])), "graph_ref_identity", "registry_id")
    model, neuronpedia, graph = ref["model"], ref["neuronpedia"], ref["graph"]
    require(bool(ID_TOKEN.fullmatch(str(model["study_id"]))) and text(model["hf_id"])
            and (model["revision"] is None or bool(HEX40.fullmatch(model["revision"]))), "graph_ref_identity",
            "model.study_id, model.hf_id and a 40-hex model.revision or null")
    require(bool(ID_TOKEN.fullmatch(str(neuronpedia["model_id"]))) and bool(ID_TOKEN.fullmatch(
        str(neuronpedia["source_set"]))), "source_set_identity",
        "neuronpedia.model_id and neuronpedia.source_set must both be recorded: a graph's nodes index one source set")
    hashes = {"graph.native_sha256": graph["native_sha256"], "graph.slug_sha256": graph["slug_sha256"],
              "input.prompt_sha256": ref["input"]["prompt_sha256"], "input.token_sha256": ref["input"]["token_sha256"],
              "settings_sha256": ref["settings_sha256"]}
    bad = sorted(name for name, value in hashes.items() if value is not None and not HEX64.fullmatch(str(value)))
    require(not bad, "graph_ref_hash", f"{bad} must be 64 hex or null")
    require(isinstance(graph["native_retained"], bool), "graph_native_artifact", "graph.native_retained is a boolean")
    if graph["native_retained"]:
        require(graph["native_sha256"] is not None and integer(graph["native_bytes"], 1), "graph_native_artifact",
                "A retained native graph is identified by its SHA-256 and its size in bytes")
    else:
        require(graph["native_sha256"] is None and graph["native_bytes"] is None, "graph_native_artifact",
                "A graph that was not retained has no native hash; a hash of a pruned or annotated copy is not one")
    for key in ("schema_version", "n_nodes", "n_links", "native_bytes"):
        require(graph[key] is None or integer(graph[key]), "graph_ref_identity", f"graph.{key}")
    _stamp(ref["retrieved_utc"], "graph_ref_identity", "retrieved_utc")
    nulls = [p for key in GRAPH_REF_KEYS[""] if key != "not_recorded" for p in null_pointers(ref[key], f"/{key}")]
    _check_not_recorded(ref, nulls, "graph reference")

    revision_compared = False
    if registry is not None:
        entry = entry_by_id(registry, ref["registry_id"])
        require(entry is not None, "unknown_registry_id", f"the registry has no entry {ref['registry_id']!r}")
        require(entry["representation_type"] in GRAPH_REPRESENTATIONS, "representation_type",
                f"{entry['registry_id']} is a {entry['representation_type']}; a graph's nodes are one of "
                f"{list(GRAPH_REPRESENTATIONS)}")
        recorded = entry["neuronpedia"] or {}
        require(recorded.get("model_id") == neuronpedia["model_id"]
                and recorded.get("source_set") == neuronpedia["source_set"], "source_set_identity",
                f"the reference names {neuronpedia['model_id']}/{neuronpedia['source_set']}; the registry entry "
                f"records {recorded.get('model_id')}/{recorded.get('source_set')}")
        require(entry["model"]["study_id"] == model["study_id"] and entry["model"]["hf_id"] == model["hf_id"],
                "graph_ref_identity", "model identity differs from the registry entry")
        if model["revision"] is not None:
            require(entry["model"]["revision"] == model["revision"], "graph_ref_identity",
                    f"the reference names model revision {model['revision']}; the registry entry pins "
                    f"{entry['model']['revision']}")
            revision_compared = True
    return {"status": "validated", "native_retained": graph["native_retained"],
            "registry_checked": registry is not None, "model_revision_compared": revision_compared}
