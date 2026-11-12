"""Batch intake: from an authored batch of case families to a review packet and a proposed measurement manifest.

Offline. It loads no model, tokenizes nothing, fires nothing and writes no measurement. The input is a JSON list
of case families in the hand-authored format (``family_id``, ``reference_facts``, ``texts``, ``changed_fact``,
``swap_spans``, ``everyday_sources``; optionally ``attribution`` and the mixed-register texts). The rules it
applies are data: ``data/experiments/intake_design.v1.json`` names the endpoint, the contrasts, the strata, the
split method, the alignment classes and the two kinds of eligibility. That file is a draft until the owner
agrees it, and every manifest records its SHA-256 and status.

Three things are kept apart in every output:

* **software validation**: structural checks (``scripts/check_candidate_pairs.py`` on every contrast, plus the
  family-level checks here). It says nothing about clinical content or patient language.
* **the owner's read**: a keep or exclude decision on a named version of the texts. A decision on texts that
  have since changed is reported as stale and is not carried over.
* **domain review**: the clinician's six dimensions and the patient-language reviewer's two items of the
  rubric (``data/protocols/instrument_validity_rubric.draft.json``). Nothing here fills them in; a family
  without both stays ``domain_review_pending``.

A read or a review is bound to the family's *review basis*: its texts, reference facts, care levels, carrier,
target and changed-fact declaration. When any of these changes, with or without a change of prompt text, the
read or review is reported as stale with the part that changed, and is not carried over.

**Known concerns** about a family's content (``--concerns``) are a fourth record, independent of all three. A
concern keeps its own disposition. The owner keeping a family does not close it: only a recorded disposition
does, and a disposition that names another version of the family no longer applies. A concern about a control
is reported on that control and does not block the family's register pair.

**Source verification and source fit** are separate. ``--source-check`` records that a cited record exists and
contains the evidence sentence. Whether patients in the family's population use the expression is source fit:
a judgement, recorded as a concern of kind ``source_fit``.

And three manipulations are kept apart: the register contrast (medical against everyday, facts held equal), the
patient-explanation contrast (everyday against everyday with a stated belief added) and the syntax crossings.
A family whose everyday wording uses a dialect form, or whose carrier phrase has no earlier measurement, keeps
its register contrast in an exploratory stratum of its own.

Splits are per family, by a seeded draw recorded before any measurement of the batch. A recorded assignment is
read back and never redrawn; a new one is refused once ``trace_out/<stem>*`` exists. The same holds for the
mechanistic subset.

Outputs are deterministic (no clock value), so a rerun with the same inputs writes the same bytes. An existing
output with other bytes is never overwritten: the command refuses and names the file.
"""
from __future__ import annotations

import collections
import difflib
import random
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from scripts import check_candidate_pairs as pair_checks
from scripts.experiments.common import (
    HEX40, HEX64, SAFE_NAME, SPLITS, check_output_path, digest, exclusive_write_bytes, integer,
    json_bytes, prompt_digest, read_json, require, sha256_bytes, text,
)
from scripts.experiments.estimate import estimate_cpu_logits_seconds, recorded_slowest_rates

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "patientwords.batch-intake/1"
DESIGN_SCHEMA = "patientwords.intake-design/1"
TOKENIZATION_SCHEMA = "patientwords.prompt-tokenization/1"
REVIEWS_SCHEMA = "patientwords.pair-equivalence-reviews/1"
REVIEW_FORM_SCHEMA = "patientwords.pair-equivalence-review-form/1"
CONCERNS_SCHEMA = "patientwords.intake-concerns/1"
SOURCE_CHECK_SCHEMA = "patientwords.source-check/1"
BASIS_PARTS = ("texts", "reference_facts", "care_levels", "carrier_and_target", "changed_fact")
DESIGN_PATH = ROOT / "data" / "experiments" / "intake_design.v1.json"
RUBRIC_PATH = ROOT / "data" / "protocols" / "instrument_validity_rubric.draft.json"
QUOTE_TYPES = ("direct patient quote", "authors' summary", "dictionary definition", "lexicon entry", "none")
OWNER_VERDICTS = {"right": "kept", "kept": "kept", "excluded": "excluded"}
OUTPUT_NAMES = ("intake_manifest.json", "review_packet.md", "review_form.json")
NOT_RECORDED = "not_recorded"
NOT_VERIFIED = "not_verified_by_this_command"
SOURCE_ID = re.compile(r"PMID: ?\d{1,9}|DOI: ?10\.\S+|https://\S+")

Sealed = Callable[[str], bool]


def load_design(path: Path | None = None) -> dict[str, Any]:
    design = read_json(path or DESIGN_PATH)
    require(isinstance(design, dict) and design.get("schema") == DESIGN_SCHEMA, "invalid_design",
            f"Expected a {DESIGN_SCHEMA} document")
    names = set(design["variants"]["required"]) | set(design["variants"]["optional"])
    for contrast in design["contrasts"]:
        require({contrast["top"], contrast["bottom"]} <= names and contrast["stratum"] in design["strata"],
                "invalid_design", f"contrast {contrast['suffix']} names an unknown variant or stratum")
    return design


def _words(value: str) -> list[str]:
    return value.split()


def differing_stretch(top: str, bottom: str) -> dict[str, Any]:
    """Word-level: what is left of each side after removing the common leading and trailing words."""
    a, b = _words(top), _words(bottom)
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    j = 0
    while j < min(len(a), len(b)) - i and a[len(a) - 1 - j] == b[len(b) - 1 - j]:
        j += 1
    regions = sum(op[0] != "equal" for op in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes())
    return {"prefix_words": i, "suffix_words": j, "top_stretch_words": len(a) - i - j,
            "bottom_stretch_words": len(b) - i - j, "word_edit_regions": regions,
            "top_stretch": " ".join(a[i:len(a) - j]), "bottom_stretch": " ".join(b[i:len(b) - j])}


def _spans_for(contrast: Mapping[str, Any], family: Mapping[str, Any], top: str, bottom: str) -> dict[str, str]:
    """The declared edit of one contrast in the shape ``check_candidate_pairs`` reads."""
    edit = contrast["edit"]
    if edit == "swap_spans" and isinstance(family.get("swap_spans"), dict):
        spans = family["swap_spans"]
        return {"clinical_span": spans.get("medical_span"), "patient_span": spans.get("everyday_span")}
    if edit == "changed_fact" and isinstance(family.get("changed_fact"), dict):
        return {"clinical_span": family["changed_fact"].get("from"), "patient_span": family["changed_fact"].get("to")}
    stretch = differing_stretch(top, bottom)
    if edit == "attribution" and stretch["top_stretch_words"] == 0:
        return {"clinical_span": "", "patient_span": " " + stretch["bottom_stretch"]}
    if stretch["top_stretch_words"] == 0 or stretch["bottom_stretch_words"] == 0 or \
            top.count(stretch["top_stretch"]) != 1:     # widen by one leading word so the span is replaceable
        a, b, i = _words(top), _words(bottom), max(0, stretch["prefix_words"] - 1)
        j = stretch["suffix_words"]
        return {"clinical_span": " ".join(a[i:len(a) - j]), "patient_span": " ".join(b[i:len(b) - j])}
    return {"clinical_span": stretch["top_stretch"], "patient_span": stretch["bottom_stretch"]}


def _family_shape_errors(family: Any, design: Mapping[str, Any], max_words: int) -> list[str]:
    """Family-level structure. Contrast-level checks are ``check_candidate_pairs``'s."""
    if not isinstance(family, dict):
        return ["shape: a family must be an object"]
    errors: list[str] = []
    fid = family.get("family_id")
    if not (text(fid) and SAFE_NAME.fullmatch(fid)):
        return [f"shape: family_id {fid!r} must be a short name of letters, digits, '.', '_' or '-'"]
    if not integer(family.get("right_care"), 1) or family["right_care"] > 4:
        errors.append("shape: right_care must be a care level 1 to 4")
    for key in ("carrier_frame", "target_token"):
        if not text(family.get(key)):
            errors.append(f"shape: {key} is missing")
    facts = family.get("reference_facts")
    fact_ids = [f.get("fact_id") for f in facts] if isinstance(facts, list) and all(isinstance(f, dict) for f in facts) else None
    if not fact_ids or not all(text(f.get("fact_id")) and text(f.get("text")) for f in facts) or len(set(fact_ids)) != len(fact_ids):
        errors.append("shape: reference_facts must be a non-empty list of {fact_id, text} with distinct ids")
        fact_ids = fact_ids or []
    texts = family.get("texts")
    known = set(design["variants"]["required"]) | set(design["variants"]["optional"])
    if not isinstance(texts, dict):
        return errors + ["shape: texts must be an object of variant name to text"]
    for name in design["variants"]["required"]:
        if not text(texts.get(name)):
            errors.append(f"shape: text {name} is missing")
    for name, value in texts.items():
        if name not in known:
            errors.append(f"shape: unknown variant {name!r}")
        elif text(value) and len(_words(value)) > max_words:
            errors.append(f"length: text {name} has {len(_words(value))} words, more than {max_words}")
    if ("quad_b" in texts) != ("quad_c" in texts):
        errors.append("shape: quad_b and quad_c come together or not at all")
    changed = family.get("changed_fact")
    if not isinstance(changed, dict) or not all(text(changed.get(k)) for k in ("fact_id", "from", "to")):
        errors.append("changed_fact: needs fact_id, from and to")
    else:
        if changed["fact_id"] not in fact_ids:
            errors.append(f"changed_fact: fact_id {changed['fact_id']!r} is not a reference fact")
        after = changed.get("right_care_after")
        if not integer(after, 1) or after > 4 or after == family.get("right_care"):
            errors.append("changed_fact: right_care_after must be a care level 1 to 4 that differs from right_care")
    if not isinstance(family.get("swap_spans"), dict) and not text(family.get("swap_note")):
        errors.append("shape: swap_spans is missing and no swap_note explains why")
    if "everyday_attribution" in texts and not (isinstance(family.get("attribution"), dict)
                                                and text(family["attribution"].get("clause"))):
        errors.append("attribution: a family with everyday_attribution needs attribution.clause")
    sources = family.get("everyday_sources")
    if not isinstance(sources, list) or not all(isinstance(s, dict) for s in sources):
        errors.append("sources: everyday_sources must be a list of objects")
    else:
        for entry in sources + ([family["attribution"]] if isinstance(family.get("attribution"), dict) else []):
            label = entry.get("expression") or entry.get("clause")
            quote = entry.get("quote_type")
            if not text(label) or not any(quote == q or (text(quote) and quote.startswith(q)) for q in QUOTE_TYPES):
                errors.append(f"sources: entry {label!r} needs an expression and a quote_type from {list(QUOTE_TYPES)}")
                continue
            unsourced = str(entry.get("source")).strip().lower() in ("none", "")
            if unsourced != (quote == "none") or (unsourced and entry.get("pmid_or_doi")):
                errors.append(f"sources: entry {label!r} mixes a source with quote_type or source 'none'")
            if not unsourced and entry.get("pmid_or_doi") is not None and not SOURCE_ID.search(str(entry["pmid_or_doi"])):
                errors.append(f"sources: entry {label!r} has an identifier that is not a PMID, a DOI or an https link")
    return errors


def _source_summary(family: Mapping[str, Any]) -> dict[str, Any]:
    entries = [s for s in family.get("everyday_sources") or [] if isinstance(s, dict)]
    by_type = collections.Counter("none" if e.get("quote_type") == "none" else str(e.get("quote_type")).split(" (")[0]
                                  for e in entries)
    return {"expressions": len(entries), "by_quote_type": dict(sorted(by_type.items())),
            "with_evidence_sentence": sum(text(e.get("evidence")) for e in entries),
            "note": "Counts of what the author declared. This command does not open any source."}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def review_basis(family: Mapping[str, Any]) -> dict[str, Any]:
    """What a reader or reviewer judges: the texts and the labels they are judged against. Sources, notes and the
    level rationale are not part of it."""
    changed = family.get("changed_fact") if isinstance(family.get("changed_fact"), dict) else {}
    return {"texts": family.get("texts"), "reference_facts": family.get("reference_facts"),
            "care_levels": {"right_care": family.get("right_care"), "right_care_after": changed.get("right_care_after")},
            "carrier_and_target": {"carrier_frame": family.get("carrier_frame"), "target_token": family.get("target_token")},
            "changed_fact": {k: changed.get(k) for k in ("fact_id", "from", "to")}}


def _owner_reads(batch: Sequence[Mapping[str, Any]], verdict_docs: Sequence[Mapping[str, Any]],
                 read_batches: Mapping[str, Sequence[Mapping[str, Any]]], batch_sha256: str) -> dict[str, dict[str, Any]]:
    """family_id -> the owner's decision on the family's current review basis, or why none applies."""
    current = {f["family_id"]: f for f in batch if isinstance(f, dict) and text(f.get("family_id"))}
    reads: dict[str, dict[str, Any]] = {fid: {"status": "not_read"} for fid in current}
    for doc in verdict_docs:
        source_sha = (doc.get("source") or {}).get("families_sha256")
        require(isinstance(doc.get("families"), list) and bool(HEX64.fullmatch(str(source_sha))), "invalid_verdicts",
                "A verdicts file needs source.families_sha256 and a families list")
        if source_sha == batch_sha256:
            read_families: Mapping[str, Mapping[str, Any]] = current
        else:
            require(source_sha in read_batches, "verdicts_source_missing",
                    f"The verdicts were recorded on a batch with SHA-256 {source_sha[:12]}, not this one; "
                    "pass that version with --read-batch so each family's texts can be compared")
            read_families = {f["family_id"]: f for f in read_batches[source_sha]}
        for row in doc["families"]:
            fid, verdict = row.get("family_id"), row.get("owner_verdict")
            if fid not in current:
                continue
            require(verdict in OWNER_VERDICTS and fid in read_families, "invalid_verdicts",
                    f"{fid}: verdict {verdict!r} must be one of {sorted(OWNER_VERDICTS)} for a family of the read batch")
            entry = {"decision": OWNER_VERDICTS[verdict], "reasons": list(row.get("owner_reasons") or []),
                     "note": row.get("owner_note") or "", "read_utc": doc.get("owner_read_utc"),
                     "read_batch_sha256": source_sha}
            then, now = review_basis(read_families[fid]), review_basis(current[fid])
            changed = [part for part in BASIS_PARTS if then[part] != now[part]]
            reads[fid] = {"status": entry["decision"], **entry} if not changed else {
                "status": "stale", "previous": entry, "changed_since_read": changed,
                "detail": f"{', '.join(changed).replace('_', ' ')} changed after this read; the decision is not carried over"}
    return reads


def _domain_reviews(batch_ids: Mapping[str, str], docs: Sequence[Mapping[str, Any]],
                    rubric: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """family_id -> clinician and patient-language review state, by the rubric's own status rule."""
    form = rubric["pair_equivalence_review"]
    roles = {r["role"]: list(r["reviews"]) for r in form["reviewers"]}
    values = set(form["values"])
    state = {fid: {role: {"status": "not_reviewed", "items": {item: None for item in items}}
                   for role, items in roles.items()} for fid in batch_ids}
    for doc in docs:
        require(isinstance(doc, dict) and doc.get("schema") == REVIEWS_SCHEMA and isinstance(doc.get("reviews"), list),
                "invalid_reviews", f"Expected a {REVIEWS_SCHEMA} document with a reviews list")
        for row in doc["reviews"]:
            fid, role = row.get("family_id"), row.get("role")
            require(role in roles and text(row.get("reviewer")) and text(row.get("date")), "invalid_reviews",
                    f"{fid}: a review needs a role from {sorted(roles)}, a reviewer and a date")
            require(row.get("reviewer_kind") == "human", "not_a_review",
                    f"{fid}: {form['not_a_review']}")
            items = row.get("items")
            require(isinstance(items, dict) and set(items) <= set(roles[role])
                    and all(v is None or v in values for v in items.values()), "invalid_reviews",
                    f"{fid}: items must be among {roles[role]} with values from {sorted(values)} or null")
            if fid not in batch_ids:
                continue
            if row.get("review_basis_sha256") != batch_ids[fid]:
                state[fid][role] = {**state[fid][role], "status": "stale",
                                    "detail": "the review names another version of the family's texts, reference facts "
                                              "or care labels than the family now holds"}
                continue
            merged = {item: items.get(item) for item in roles[role]}
            done = all(v is not None for v in merged.values())
            state[fid][role] = {"status": "different" if "different" in merged.values() else
                                "recorded" if done else "incomplete",
                                "items": merged, "reviewer": row["reviewer"], "date": row["date"]}
    return state


def _review_status(review: Mapping[str, Any], design: Mapping[str, Any]) -> str:
    clinician, language = review["clinician"], review["patient_language_reviewer"]
    if "different" in (clinician["status"], language["status"]):
        return "removed_by_review"
    clinician_same = clinician["status"] == "recorded" and set(clinician["items"].values()) == {"same"}
    if clinician_same and language["status"] == "recorded":
        return design["review"]["reviewed_status"]
    return design["review"]["pending_status"]


def _concerns(families: Mapping[str, Mapping[str, Any]], basis: Mapping[str, str], docs: Sequence[Mapping[str, Any]],
              design: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """family_id -> its known concerns, each with the state its recorded disposition gives it for this version.

    Nothing but a recorded disposition closes a concern. ``accepted_as_is`` and ``resolved_by_revision`` are a
    person's decisions, so a model cannot record them: a revision made to address a concern leaves it open as
    ``revised_pending_reread`` until a person confirms it. ``resolved_by_revision`` names the version that resolved
    it; for any other version the concern is open again. ``label`` in ``applies_to`` means the reviewer-only
    condition label, which is in no prompt."""
    rules = design["concerns"]
    suffixes = {c["suffix"]: c for c in design["contrasts"]}
    out: dict[str, list[dict[str, Any]]] = {fid: [] for fid in families}
    seen: set[str] = set()
    for doc in docs:
        require(isinstance(doc, dict) and doc.get("schema") == CONCERNS_SCHEMA and isinstance(doc.get("concerns"), list),
                "invalid_concerns", f"Expected a {CONCERNS_SCHEMA} document with a concerns list")
        for row in doc["concerns"]:
            cid, fid = row.get("concern_id"), row.get("family_id")
            require(text(cid) and bool(SAFE_NAME.fullmatch(cid)) and cid not in seen, "invalid_concerns",
                    f"concern_id {cid!r} must be a short safe name used once")
            seen.add(cid)
            require(fid in families, "invalid_concerns", f"{cid}: {fid!r} is not a usable family of this batch")
            applies = row.get("applies_to")
            present = {s for s, c in suffixes.items() if {c["top"], c["bottom"]} <= set(families[fid]["texts"])}
            require(isinstance(applies, list) and bool(applies) and set(applies) <= present | {"family", "label"},
                    "invalid_concerns",
                    f"{cid}: applies_to must name 'family', 'label' or contrasts of {fid}: {sorted(present)}")
            require(row.get("kind") in rules["kinds"] and text(row.get("text")) and text(row.get("raised_by"))
                    and row.get("raised_by_kind") in ("human", "model") and text(row.get("raised_on")), "invalid_concerns",
                    f"{cid}: needs a kind from {sorted(rules['kinds'])}, text, raised_by, raised_by_kind and raised_on")
            disposition = row.get("disposition") or {"status": "open"}
            status = disposition.get("status")
            require(status in rules["open_statuses"] + rules["closed_statuses"], "invalid_concerns",
                    f"{cid}: disposition.status must be one of {rules['open_statuses'] + rules['closed_statuses']}")
            state, why = ("open" if status in rules["open_statuses"] else "closed"), None
            if state == "closed":
                require(text(disposition.get("by")) and text(disposition.get("date")) and text(disposition.get("note")),
                        "invalid_concerns", f"{cid}: a closing disposition needs by, date and note")
                if status == "withdrawn":
                    require((disposition["by"], disposition.get("by_kind")) == (row["raised_by"], row["raised_by_kind"]),
                            "not_a_disposition",
                            f"{cid}: a concern is withdrawn only by whoever raised it ({row['raised_by']!r}); anyone "
                            "else records accepted_as_is or resolved_by_revision")
                else:
                    require(disposition.get("by_kind") == "human", "not_a_disposition",
                            f"{cid}: {status} is a person's decision; a model's statement does not close a concern")
                if status == "resolved_by_revision" and disposition.get("resolved_in_review_basis_sha256") != basis[fid]:
                    state, why = "open", "the disposition names another version of the family than the one in this batch"
            raised_on_basis = row.get("raised_on_review_basis_sha256")
            out[fid].append({
                "concern_id": cid, "kind": row["kind"], "applies_to": sorted(applies), "text": row["text"],
                "raised_by": row["raised_by"], "raised_by_kind": row["raised_by_kind"], "raised_on": row["raised_on"],
                "family_changed_since_raised": NOT_RECORDED if raised_on_basis is None else raised_on_basis != basis[fid],
                "disposition": dict(disposition), "state": state, **({"state_reason": why} if why else {})})
    return out


def _source_checks(docs: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """(family_id, expression or clause, identifier) -> what a recorded check of that citation found."""
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for doc in docs:
        require(isinstance(doc, dict) and doc.get("schema") == SOURCE_CHECK_SCHEMA and isinstance(doc.get("entries"), list)
                and text(doc.get("method")) and text(doc.get("checked_utc")), "invalid_source_check",
                f"Expected a {SOURCE_CHECK_SCHEMA} document with method, checked_utc and entries")
        for row in doc["entries"]:
            require(text(row.get("family_id")) and text(row.get("expression")) and text(row.get("identifier"))
                    and isinstance(row.get("record_matches_citation"), bool) and isinstance(row.get("evidence_found"), bool),
                    "invalid_source_check", "An entry needs family_id, expression, identifier and two booleans")
            out[(row["family_id"], row["expression"], row["identifier"])] = {
                "record_matches_citation": row["record_matches_citation"],
                "evidence_found": row["evidence_found"], "checked_utc": doc["checked_utc"]}
    return out


def _citation_status(family_id: str, entry: Mapping[str, Any],
                     checks: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> str:
    """One citation row: an expression with one identifier. A check of another citation of the same wording does
    not count for this one."""
    label = entry.get("expression") or entry.get("clause")
    hit = checks.get((family_id, label, entry.get("pmid_or_doi")))
    if hit is None:
        return "not_checked"
    return "record_and_sentence_found" if hit["record_matches_citation"] and hit["evidence_found"] else "not_found"


def _verification(family: Mapping[str, Any], checks: Mapping[tuple[str, str, str], Mapping[str, Any]]) -> dict[str, Any]:
    """Per citation row: verified, not found, or not checked. Unsourced expressions are not counted."""
    entries = [s for s in family.get("everyday_sources") or [] if isinstance(s, dict)]
    if isinstance(family.get("attribution"), dict):
        entries = entries + [family["attribution"]]
    rows = [{"expression": entry.get("expression") or entry.get("clause"), "identifier": entry.get("pmid_or_doi"),
             "status": _citation_status(family["family_id"], entry, checks)}
            for entry in entries
            if entry.get("quote_type") != "none" and text(entry.get("expression") or entry.get("clause"))]
    return {"per_citation": rows, "counts": dict(sorted(collections.Counter(r["status"] for r in rows).items())),
            "means": "The cited record exists and contains the evidence sentence. It does not show that patients in "
                     "the family's population use the expression; that is source fit, recorded as a concern."}


def assign_splits(strata: Mapping[str, int], seed: int) -> dict[str, str]:
    """The design's split method: per care level from highest to lowest, sorted ids, one seeded shuffle each."""
    rng = random.Random(seed)
    out: dict[str, str] = {}
    for care in sorted(set(strata.values()), reverse=True):
        ids = sorted(fid for fid, level in strata.items() if level == care)
        rng.shuffle(ids)
        n = len(ids)
        for i, fid in enumerate(ids):
            out[fid] = SPLITS[0] if i < n // 2 else SPLITS[1] if i < n // 2 + n // 4 else SPLITS[2]
    return out


def _splits(families: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]], seed: int | None,
            removed: set[str], measured: bool, stem: str | None) -> dict[str, Any]:
    """Recorded splits are read, never redrawn. This command cannot see when a record was written. Once the batch
    has measurements it therefore accepts a record only if the record is bound to this batch (its strata are
    exactly this batch's families and care levels) and is the seeded draw its own seed gives; a bare mapping, a
    record of another batch or a hand-chosen assignment is refused. That the record predates the measurements
    is shown by the commit that added it, not by this command, and the manifest says so."""
    recorded: dict[str, str] = {}
    sources: dict[str, str] = {}
    reproduced: list[dict[str, Any]] = []
    batch_strata = {f["family_id"]: f["right_care"] for f in families}
    for n, record in enumerate(records, 1):
        body = record.get("split_assignment", record)
        require(isinstance(body.get("splits"), dict) and set(body["splits"].values()) <= set(SPLITS), "invalid_split_record",
                f"split record {n} needs a splits object with values from {list(SPLITS)}")
        if measured:
            require(integer(body.get("seed")) and isinstance(body.get("strata"), dict)
                    and body["strata"] == batch_strata
                    and assign_splits(body["strata"], body["seed"]) == body["splits"], "split_record_unbound",
                    f"split record {n}: the batch already has measurements, so a record is accepted only when its "
                    "strata are exactly this batch's families and care levels and its splits are the draw its seed "
                    "gives. This one is not; a split is not assigned or adopted after measurement")
        for fid, split in body["splits"].items():
            require(recorded.setdefault(fid, split) == split, "split_conflict",
                    f"{fid} is in {recorded[fid]} in one split record and in {split} in another")
            sources.setdefault(fid, f"record {n}")
        if integer(body.get("seed")) and isinstance(body.get("strata"), dict):
            reproduced.append({"record": n, "seed": body["seed"],
                               "reproduces_from_its_seed": assign_splits(body["strata"], body["seed"]) == body["splits"]})
    strata = {f["family_id"]: f["right_care"] for f in families}
    new = {fid: care for fid, care in strata.items() if fid not in recorded and fid not in removed}
    assigned: dict[str, str] = {}
    if new and seed is not None:
        require(not measured, "split_after_measurement",
                f"{sorted(new)} have no recorded split and the batch already has measurements; a split is assigned "
                "before measurement or not at all")
        assigned = assign_splits(new, seed)
    per_family = {fid: recorded.get(fid) or assigned.get(fid) for fid in strata}
    return {"per_family": per_family,
            "source": {fid: sources.get(fid) or ("assigned by this run" if fid in assigned else
                                                 "removed by review before the split" if fid in removed else "unassigned")
                       for fid in strata},
            "seed_for_new_assignments": seed if assigned else None, "newly_assigned": sorted(assigned),
            "records_checked": reproduced,
            "records_timing": ("Not verified by this command. The batch has measurements; each record matches this "
                               "batch's families and care levels and reproduces from its seed. That it was written "
                               "before the measurements is shown by the commit that added it."
                               if measured and records else
                               "No stem was named, so this command did not look for measurements. The records are "
                               "read as given and support no claim about timing." if records and stem is None else
                               "The batch has no measurements under its stem." if records else None),
            "counts": dict(sorted(collections.Counter(str(v) for v in per_family.values()).items()))}


def _mechanistic(candidates: Mapping[str, int], n: int, seed: int | None, measured: bool,
                 previous: Mapping[str, Any] | None, design: Mapping[str, Any], batch_id: str,
                 basis: Mapping[str, str], stem: str | None) -> dict[str, Any]:
    """A seeded draw before measurement. After measurement nothing is drawn: the subset is restored from a
    manifest of this batch and this stem that records no run directory of the stem, and only while every family
    of that subset still has the review basis it had then. A manifest written without a stem, or for another
    stem, lists no run directory whatever exists, so it is refused.

    An earlier manifest is a file the caller supplies. Its fields can be checked for consistency; when it was
    written cannot be established from them (it may have been produced against another tree, or edited). A
    restored subset is therefore never labelled as selected before outcomes by this command: its status is
    ``restored_from_earlier_manifest`` and the manifest says that the timing rests on the commit that added the
    earlier manifest."""
    base = {"selection": design["mechanistic_subset"]["selection"], "rule": design["mechanistic_subset"]["rule"],
            "controls_per_site": design["mechanistic_subset"]["controls_per_site"],
            "ica_basis": design["mechanistic_subset"]["ica_basis"]}
    if not n:
        return {**base, "families": [], "status": "not_selected"}
    require(seed is not None, "missing_seed", "--mechanistic-seed is required with --mechanistic-families")
    if measured:
        refusal = ("The batch already has measurements. A mechanistic subset is selected before outcomes: pass "
                   "--previous-manifest, an intake manifest of this batch and this stem written before any run "
                   "directory of the stem existed, "
                   "or report the families as outcome-selected and exploratory")
        earlier = (previous or {}).get("mechanistic_subset") if isinstance(previous, dict) else None
        require(isinstance(previous, dict) and previous.get("schema") == SCHEMA
                and (previous.get("batch") or {}).get("batch_id") == batch_id
                and stem is not None and (previous.get("measurements") or {}).get("stem") == stem
                and (previous.get("measurements") or {}).get("existing_run_directories") == []
                and isinstance(earlier, dict) and earlier.get("status") == "selected_before_outcomes"
                and isinstance(earlier.get("families"), list) and bool(earlier["families"])
                and earlier.get("seed") == seed and earlier.get("requested") == n, "subset_after_measurement", refusal)
        then = {r.get("family_id"): r.get("review_basis_sha256") for r in previous.get("families") or []
                if isinstance(r, dict)}
        moved = sorted(f for f in earlier["families"] if then.get(f) is None or then.get(f) != basis.get(f))
        require(not moved, "subset_family_changed",
                f"{moved}: the earlier manifest chose these families in another version than the batch now holds, or "
                "does not record their version; its subset cannot be restored for this batch")
        dropped = sorted(f for f in earlier["families"] if f not in candidates)
        require(not dropped, "subset_family_not_candidate",
                f"{dropped}: the earlier manifest chose these families, and they are no longer owner-kept, unflagged "
                "discovery families of this batch. The subset is not restored with a family the batch's current state "
                "removes or holds out; record the change and report the remaining work as exploratory")
        return {**base, "families": sorted(earlier["families"]), "seed": seed, "requested": n,
                "candidates": earlier.get("candidates"), "status": "restored_from_earlier_manifest",
                "outcome_selected": NOT_VERIFIED, "restored_from_previous_manifest": True,
                "timing": "Not verified by this command. The batch has measurements. The subset is the one an earlier "
                          "manifest of this batch and stem records, and that manifest lists no run directory; whether it "
                          "was written before the measurements is shown by the commit that added it. Until that is "
                          "checked, treat the subset as possibly outcome-selected and exploratory."}
    rng = random.Random(seed)
    queues = []
    for care in sorted(set(candidates.values()), reverse=True):
        ids = sorted(fid for fid, level in candidates.items() if level == care)
        rng.shuffle(ids)
        queues.append(ids)
    drawn: list[str] = []
    while len(drawn) < n and any(queues):
        for queue in queues:
            if queue and len(drawn) < n:
                drawn.append(queue.pop(0))
    return {**base, "families": sorted(drawn), "seed": seed, "requested": n, "candidates": len(candidates),
            "status": "selected_before_outcomes", "outcome_selected": False, "restored_from_previous_manifest": False}


def _tokenizers(docs: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    out: dict[tuple[str, str], Mapping[str, Any]] = {}
    for doc in docs:
        require(isinstance(doc, dict) and doc.get("schema") == TOKENIZATION_SCHEMA and text(doc.get("tokenizer_id"))
                and bool(HEX40.fullmatch(str(doc.get("tokenizer_revision")))) and text(doc.get("source"))
                and isinstance(doc.get("prompts"), dict), "invalid_tokenization",
                f"Expected a {TOKENIZATION_SCHEMA} document with tokenizer_id, a 40-hex tokenizer_revision, a source "
                "saying where the ids were recorded, and prompts keyed by prompt SHA-256")
        out[(doc["tokenizer_id"], doc["tokenizer_revision"])] = doc
    return out


def _alignment(top_ids: Sequence[int] | None, bottom_ids: Sequence[int] | None) -> dict[str, Any]:
    if not top_ids or not bottom_ids:
        return {"class": NOT_RECORDED}
    i = 0
    while i < min(len(top_ids), len(bottom_ids)) and top_ids[i] == bottom_ids[i]:
        i += 1
    j = 0
    while j < min(len(top_ids), len(bottom_ids)) - i and top_ids[-1 - j] == bottom_ids[-1 - j]:
        j += 1
    top_n, bottom_n = len(top_ids) - i - j, len(bottom_ids) - i - j
    return {"class": "position_aligned" if j > 0 and top_n == bottom_n else "suffix_aligned" if j > 0 else "unaligned",
            "prefix_tokens": i, "suffix_tokens": j, "top_stretch_tokens": top_n, "bottom_stretch_tokens": bottom_n,
            "top_tokens": len(top_ids), "bottom_tokens": len(bottom_ids)}


def _partial(target_words: int, target_tokens: Mapping[str, Any]) -> bool | str:
    """Whether the endpoint reads only part of the target: known True, known False, or not recorded."""
    if target_words > 1 or any(isinstance(n, int) and n > 1 for n in target_tokens.values()):
        return True
    if not target_tokens or NOT_RECORDED in target_tokens.values():
        return NOT_RECORDED
    return False


def model_identities(study_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Pinned identities from ``scripts/logits_eval.py``. An id without a pin is refused, never guessed."""
    from scripts import logits_eval

    out = []
    for study_id in study_ids:
        require(study_id in logits_eval.HF_IDS, "unknown_model", f"{study_id} is not in logits_eval.HF_IDS")
        revision = logits_eval.HF_REVISIONS.get(study_id)
        require(revision is not None, "missing_revision", f"{study_id} has no pinned revision in logits_eval.HF_REVISIONS")
        out.append({"study_id": study_id, "hf_id": logits_eval.HF_IDS[study_id], "revision": revision,
                    "tokenizer_id": logits_eval.HF_IDS[study_id], "tokenizer_revision": revision,
                    "identity_source": "scripts/logits_eval.py HF_IDS and HF_REVISIONS; the lane loads the tokenizer "
                                       "from the same pinned commit as the weights"})
    return out


def _cpu_estimate(pairs: int, models: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    recorded = recorded_slowest_rates()
    rates = {m["study_id"]: recorded["seconds_per_pair"][m["study_id"]] for m in models
             if m["study_id"] in recorded["seconds_per_pair"]}
    out: dict[str, Any] = {"pairs": pairs, "rates_source": recorded["source"], "rates_label": recorded["label"],
                           "no_recorded_rate": sorted(m["study_id"] for m in models if m["study_id"] not in rates),
                           "measured": False}
    if pairs and rates:
        out["cpu_logits"] = estimate_cpu_logits_seconds(pairs, rates, prompts_per_family=2,
                                                        leg_budget_seconds=recorded["leg_budget_seconds"],
                                                        max_pairs_per_leg=recorded["max_pairs_per_leg"])
    return out


def run_intake(batch: Any, *, batch_id: str, batch_sha256: str, source_ref: str, design: Mapping[str, Any],
               design_sha256: str, root: Path = ROOT, verdicts: Sequence[Mapping[str, Any]] = (),
               read_batches: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
               reviews: Sequence[Mapping[str, Any]] = (), prior_batches: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
               concerns: Sequence[Mapping[str, Any]] = (), source_checks: Sequence[Mapping[str, Any]] = (),
               split_records: Sequence[Mapping[str, Any]] = (), split_seed: int | None = None,
               models: Sequence[str] = (), tokenizations: Sequence[Mapping[str, Any]] = (),
               mechanistic_families: int = 0, mechanistic_seed: int | None = None,
               previous_manifest: Mapping[str, Any] | None = None, stem: str | None = None,
               pairs_file: Sequence[Mapping[str, Any]] | None = None, pairs_file_ref: str | None = None,
               input_hashes: Mapping[str, Any] | None = None,
               forbid: str = ",;-", max_words: int = 40, lexicon: set[str] | None = None,
               sealed: Sealed | None = None) -> dict[str, Any]:
    """The manifest for one authored batch. Raises ``Refusal`` for unusable inputs; findings about the batch's
    content are returned in the manifest, never raised."""
    require(text(batch_id) and bool(SAFE_NAME.fullmatch(batch_id)), "invalid_input", "batch_id must be a short safe name")
    require(isinstance(batch, list) and bool(batch), "invalid_input", "A batch is a non-empty JSON list of families")
    require(stem is None or bool(SAFE_NAME.fullmatch(stem)), "invalid_input", "stem must be a short safe name")
    require(stem is not None or (split_seed is None and not mechanistic_families), "stem_required",
            "A split or a mechanistic subset is assigned for a named stem, so that this command can see whether "
            "trace_out/ already holds measurements under it. Pass --stem")
    rubric = read_json(RUBRIC_PATH)
    run_dirs = sorted(p.name for p in (root / "trace_out").glob(f"{stem}*")) if stem else []
    measured = bool(run_dirs)

    findings: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: {"errors": [], "warnings": []})
    ids = [f.get("family_id") if isinstance(f, dict) else None for f in batch]
    shape = {i: _family_shape_errors(f, design, max_words) for i, f in enumerate(batch)}
    usable = [f for i, f in enumerate(batch) if not any(e.startswith("shape") for e in shape[i])]
    for i, family in enumerate(batch):
        key = ids[i] if text(ids[i]) else f"#{i + 1}"
        findings[key]["errors"] += shape[i]
        if text(ids[i]) and ids.count(ids[i]) > 1:
            findings[key]["errors"].append(f"duplicate: family_id appears {ids.count(ids[i])} times in the batch")

    # Duplicate cases, inside the batch and against earlier batches: the same text, the same condition, a reused id.
    seen_text: dict[str, str] = {}
    seen_condition: dict[str, str] = {}
    for label, families in (prior_batches or {}).items():
        for family in families:
            for value in (family.get("texts") or {}).values():
                seen_text.setdefault(_norm(value), f"{family['family_id']} of {label}")
            if text(family.get("condition")):
                seen_condition.setdefault(_norm(family["condition"]), f"{family['family_id']} of {label}")
            if family.get("family_id") in ids:
                same = next(f for f in batch if isinstance(f, dict) and f.get("family_id") == family["family_id"])
                if same != family:
                    findings[family["family_id"]]["errors"].append(
                        f"duplicate: family_id is already used by a different family in {label}; ids are stable")
    for family in usable:
        fid = family["family_id"]
        for name, value in family["texts"].items():
            other = seen_text.setdefault(_norm(value), fid)
            if other != fid:
                findings[fid]["errors"].append(f"duplicate: text {name} is also a text of {other}")
        if text(family.get("condition")):
            other = seen_condition.setdefault(_norm(family["condition"]), fid)
            if other != fid:
                findings[fid]["warnings"].append(f"duplicate_case: the condition label is also that of {other}")

    # Contrast-level checks: the existing pair checker on every contrast of every usable family.
    candidates, contrast_rows = [], {}
    for family in usable:
        fid, texts = family["family_id"], family["texts"]
        for contrast in design["contrasts"]:
            if contrast["top"] not in texts or contrast["bottom"] not in texts:
                continue
            top, bottom = texts[contrast["top"]], texts[contrast["bottom"]]
            cid = f"{fid}-{contrast['suffix']}"
            contrast_rows[cid] = (family, contrast, top, bottom)
            candidates.append({"id": cid, "top_prompt": top, "bottom_prompt": bottom,
                               "target_clinical_token": family["target_token"], "carrier_frame": family["carrier_frame"],
                               "clinical_tier_expected": family["right_care"],
                               "swap_spans": _spans_for(contrast, family, top, bottom),
                               "lexicon_entries": family.get("lexicon_entries") or []})
    checked = pair_checks.check(candidates, root=root, lexicon=lexicon, forbid=forbid, sealed=sealed) if candidates else {}
    for cid, result in checked.items():
        fid = contrast_rows[cid][0]["family_id"]
        findings[fid]["errors"] += [f"{cid}: {m}" for m in result["errors"]]
        findings[fid]["warnings"] += [f"{cid}: {m}" for m in result["warnings"]]

    texts_sha = {f["family_id"]: digest(f["texts"]) for f in usable}
    basis_sha = {f["family_id"]: digest(review_basis(f)) for f in usable}
    owner = _owner_reads(usable, verdicts, read_batches or {}, batch_sha256)
    domain = _domain_reviews(basis_sha, reviews, rubric)
    known = _concerns({f["family_id"]: f for f in usable}, basis_sha, concerns, design)
    checks = _source_checks(source_checks)
    review_status = {fid: _review_status(domain[fid], design) for fid in texts_sha}
    removed = {fid for fid, status in review_status.items() if status == "removed_by_review"}
    splits = _splits(usable, split_records, split_seed, removed, measured, stem)
    tokenizers = _tokenizers(tokenizations)
    identities = model_identities(models)
    signed = bool(re.match(r"signed\b", str(design["protocol"].get("status", ""))))    # "not signed" is not signed

    family_rows: list[dict[str, Any]] = []
    for family in usable:
        fid = family["family_id"]
        errors, warnings = findings[fid]["errors"], findings[fid]["warnings"]
        flags = [name for name, on in (("dialect", bool(family.get("lexicon_entries"))),
                                       ("new_carrier", family["carrier_frame"] not in design["established_carriers"])) if on]
        register_stratum = design["family_flags"][flags[0]]["register_stratum"] if flags else "register"
        target_words = len(_words(family["target_token"]))
        target_tokens = {f"{tid}@{rev[:12]}": len(doc.get("targets", {}).get(family["target_token"]) or []) or NOT_RECORDED
                         for (tid, rev), doc in sorted(tokenizers.items())}
        contrasts = []
        for contrast in design["contrasts"]:
            cid = f"{fid}-{contrast['suffix']}"
            if cid not in contrast_rows:
                continue
            _, _, top, bottom = contrast_rows[cid]
            stretch = differing_stretch(top, bottom)
            stratum = register_stratum if contrast["stratum"] == "register" else contrast["stratum"]
            contrasts.append({
                "id": cid, "stratum": stratum, "role": contrast["role"], "top": contrast["top"], "bottom": contrast["bottom"],
                "top_sha256": prompt_digest(top), "bottom_sha256": prompt_digest(bottom),
                "holds_constant": contrast["holds_constant"],
                "open_concerns": [c["concern_id"] for c in known[fid]
                                  if c["state"] == "open" and contrast["suffix"] in c["applies_to"]],
                "words": {k: stretch[k] for k in ("prefix_words", "suffix_words", "top_stretch_words",
                                                  "bottom_stretch_words", "word_edit_regions")},
                "alignment": {f"{tid}@{rev[:12]}": _alignment(doc["prompts"].get(prompt_digest(top)),
                                                             doc["prompts"].get(prompt_digest(bottom)))
                              for (tid, rev), doc in sorted(tokenizers.items())} or {"status": NOT_RECORDED}})
        admissible = not errors
        open_here = [c for c in known[fid] if c["state"] == "open"]
        on_pair = sorted(c["concern_id"] for c in open_here if {"family", "reg"} & set(c["applies_to"]))
        blocked = [reason for reason, on in (
            ("software_validation_failed", bool(errors)), ("protocol_not_signed", not signed),
            ("clinician_review_missing", domain[fid]["clinician"]["status"] != "recorded"),
            ("patient_language_review_missing", domain[fid]["patient_language_reviewer"]["status"] != "recorded"),
            ("removed_by_review", fid in removed),
            (f"owner_read_{owner[fid]['status']}", owner[fid]["status"] != "kept"),
            (f"exploratory_stratum:{register_stratum}", bool(flags)),
            ("split_unassigned", splits["per_family"][fid] is None),
            ("split_timing_not_verified", measured and splits["per_family"][fid] is not None),
            ("stem_not_named", stem is None),
            ("open_concern_on_register_pair:" + ",".join(on_pair), bool(on_pair))) if on]
        family_rows.append({
            "family_id": fid, "family_sha256": digest(family), "texts_sha256": texts_sha[fid],
            "review_basis_sha256": basis_sha[fid],
            "right_care": family["right_care"], "carrier_frame": family["carrier_frame"],
            "target": {"text": family["target_token"], "words": target_words, "tokens": target_tokens or NOT_RECORDED,
                       "endpoint_partial": _partial(target_words, target_tokens)},
            "flags": flags, "register_stratum": register_stratum,
            "split": splits["per_family"][fid], "split_source": splits["source"][fid],
            "variants": {name: {"sha256": prompt_digest(value), "words": len(_words(value))}
                         for name, value in sorted(family["texts"].items())},
            "contrasts": contrasts, "sources": {**_source_summary(family), "verification": _verification(family, checks)},
            "review": {"status": review_status[fid], "owner_read": owner[fid], **domain[fid]},
            "concerns": {"records": known[fid], "open": len(open_here), "closed": len(known[fid]) - len(open_here),
                         "note": design["concerns"]["rule"]},
            "validation": {"errors": errors, "warnings": warnings}, "admissible": admissible,
            "eligibility": {
                "publication": {"membership": "public-display/1", "shareable": admissible,
                                "labels_required": ["exploratory, hand-authored", f"review status: {review_status[fid]}"]},
                "confirmatory": {"eligible": not blocked, "blocked_by": blocked,
                                 "applies_to": "the register pair. A control with an open concern is listed in "
                                               "controls_with_open_concerns and does not block the pair. Without "
                                               "a named stem the command has not looked for measurements and "
                                               "reports no family as eligible. Once the "
                                               "batch has measurements this command cannot verify that a split was "
                                               "recorded first, so it reports no family as eligible: eligibility is "
                                               "read from a manifest written before measurement.",
                                 "controls_with_open_concerns": {
                                     c["id"]: c["open_concerns"] for c in contrasts
                                     if c["role"] != "contrast" and c["open_concerns"]}}}})

    unusable = [{"position": i + 1, "family_id": ids[i], "errors": shape[i]} for i in range(len(batch))
                if batch[i] not in usable]
    admissible_rows = [r for r in family_rows if r["admissible"]]
    kept_rows = [r for r in admissible_rows if r["review"]["owner_read"]["status"] == "kept"]
    subset_candidates = {r["family_id"]: r["right_care"] for r in kept_rows
                         if not r["flags"] and r["split"] == SPLITS[0] and r["family_id"] not in removed}
    subset = _mechanistic(subset_candidates, mechanistic_families, mechanistic_seed, measured, previous_manifest, design,
                          batch_id, basis_sha, stem)

    def pairs_of(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [c for r in rows for c in r["contrasts"]]

    def inventory_of(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        contrasts = pairs_of(rows)
        return {"families": len(rows), "prompts": sum(len(r["variants"]) for r in rows), "contrasts": len(contrasts),
                "contrasts_by_stratum_and_role": dict(sorted(collections.Counter(
                    f"{c['stratum']}/{c['role']}" for c in contrasts).items())),
                "families_by_split": dict(sorted(collections.Counter(str(r["split"]) for r in rows).items())),
                "families_by_register_stratum": dict(sorted(collections.Counter(r["register_stratum"] for r in rows).items())),
                "families_by_carrier_and_target": dict(sorted(collections.Counter(
                    f"{r['carrier_frame']} |{r['target']['text']}" for r in rows).items()))}

    discovery = [r for r in kept_rows if r["split"] == "discovery"]
    patch = design["work_rates"]["activation_patching_minutes_per_pair"]
    sites = 1 + len(design["mechanistic_subset"]["controls_per_site"])
    n_subset = len(subset["families"])
    all_errors = [m for f in findings.values() for m in f["errors"]]
    all_warnings = [m for f in findings.values() for m in f["warnings"]]
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "batch": {"batch_id": batch_id, "source": source_ref, "sha256": batch_sha256, "families": len(batch)},
        "design": {"file": "data/experiments/intake_design.v1.json", "sha256": design_sha256, "status": design["status"],
                   "protocol": design["protocol"]},
        "inputs": dict(input_hashes or {}),
        "endpoint": design["endpoint"],
        "comparisons_not_made": design["comparisons_not_made"],
        "software_validation": {
            "status": "failed" if all_errors or unusable else "passed", "errors": len(all_errors),
            "warnings": len(all_warnings),
            "by_check": dict(sorted(collections.Counter(re.sub(r"^\S+-\w+: ", "", m).split(":", 1)[0]
                                                        for m in all_errors + all_warnings).items())),
            "is": design["review"]["layers"]["software_validation"],
            "parameters": {"forbid": forbid, "max_words": max_words, "lexicon_supplied": lexicon is not None,
                           "note": "Caller-set. Another value changes which texts pass; compare runs on these."},
            "unusable_families": unusable},
        "review_layers": design["review"]["layers"],
        "eligibility_rules": design["eligibility"],
        "families": family_rows,
        "splits": {**{k: v for k, v in splits.items() if k != "per_family"}, "method": design["split"]["method"],
                   "unit": design["split"]["unit"], "open": design["split"]["open"]},
        "mechanistic_subset": subset,
        "models": identities or NOT_RECORDED,
        "tokenization": [{"tokenizer_id": tid, "tokenizer_revision": rev, "source": doc["source"],
                          "prompts_recorded": len(doc["prompts"])} for (tid, rev), doc in sorted(tokenizers.items())]
        or {"status": NOT_RECORDED, "note": "No tokenizer file is available offline. Token ids come from a recorded run; "
                                              "until then alignment is known at word level only."},
        "inventory": {"all_admissible": inventory_of(admissible_rows), "owner_kept": inventory_of(kept_rows),
                      "owner_kept_discovery": inventory_of(discovery),
                      "review_status": dict(sorted(collections.Counter(r["review"]["status"] for r in family_rows).items())),
                      "owner_read": dict(sorted(collections.Counter(r["review"]["owner_read"]["status"] for r in family_rows).items())),
                      "confirmatory_eligible": sum(r["eligibility"]["confirmatory"]["eligible"] for r in family_rows),
                      "concerns": {
                          "open": sum(r["concerns"]["open"] for r in family_rows),
                          "closed": sum(r["concerns"]["closed"] for r in family_rows),
                          "open_by_kind": dict(sorted(collections.Counter(
                              c["kind"] for r in family_rows for c in r["concerns"]["records"] if c["state"] == "open").items())),
                          "open_by_disposition": dict(sorted(collections.Counter(
                              c["disposition"]["status"] for r in family_rows for c in r["concerns"]["records"]
                              if c["state"] == "open").items())),
                          "owner_kept_families_with_open_concerns": sorted(
                              r["family_id"] for r in family_rows
                              if r["review"]["owner_read"]["status"] == "kept" and r["concerns"]["open"]),
                          "rule": design["concerns"]["rule"]},
                      "source_verification": dict(sorted(collections.Counter(
                          c["status"] for r in family_rows for c in r["sources"]["verification"]["per_citation"]).items()))},
        "estimated_work": {
            "note": "Arithmetic on recorded rates and documented estimates. Nothing here is a measurement.",
            "behavioural_pass_owner_kept": _cpu_estimate(len(pairs_of(kept_rows)), identities),
            "behavioural_pass_owner_kept_discovery": _cpu_estimate(len(pairs_of(discovery)), identities),
            "mechanistic_subset": {
                "families": n_subset, "register_contrasts": n_subset, "sites_per_contrast_with_controls": sites,
                "runner_minutes": {"low": n_subset * sites * patch["low"], "high": n_subset * sites * patch["high"]},
                "formula": "families * (1 + controls per site) * minutes per pair", "source": patch["source"],
                "measured": False},
            "domain_review": {"families_awaiting_clinician": sum(r["review"]["clinician"]["status"] != "recorded" for r in admissible_rows),
                              "families_awaiting_patient_language": sum(
                                  r["review"]["patient_language_reviewer"]["status"] != "recorded" for r in admissible_rows),
                              "texts_to_read": sum(len(r["variants"]) for r in admissible_rows),
                              "minutes": NOT_RECORDED}},
        "measurements": {"stem": stem, "existing_run_directories": run_dirs,
                         "note": "Directories under trace_out/ whose name starts with the stem. This command reads their "
                                 "names only and never their contents."},
    }
    if pairs_file is not None:
        # A lane reads every row of the file, so every row is accounted for: a repeated id is never collapsed
        # into its last row, and a row without an id is counted.
        rows_of: dict[Any, list[tuple[int, Mapping[str, Any]]]] = collections.defaultdict(list)
        for n, pair in enumerate(pairs_file, 1):
            generation = pair.get("generation") if isinstance(pair, dict) else None
            rows_of[generation.get("id") if isinstance(generation, dict) else None].append((n, pair))
        without_id = [n for n, _ in rows_of.pop(None, [])]
        duplicated = {str(i): [n for n, _ in rows] for i, rows in sorted(rows_of.items(), key=lambda kv: str(kv[0]))
                      if len(rows) > 1}
        state = {}
        for cid, (family, _, top, bottom) in contrast_rows.items():
            rows = rows_of.get(cid) or []
            state[cid] = "absent" if not rows else "duplicated" if len(rows) > 1 else "identical" if (
                rows[0][1].get("top_prompt"), rows[0][1].get("bottom_prompt"), rows[0][1].get("target_clinical_token")) == (
                top, bottom, family["target_token"]) else "differs"
        manifest["lane_input"] = {
            "pairs_file": pairs_file_ref, "pairs": len(pairs_file),
            "identical": sum(v == "identical" for v in state.values()),
            "differs": sorted(c for c, v in state.items() if v == "differs"),
            "absent": sorted(c for c, v in state.items() if v == "absent"),
            "duplicate_ids": duplicated, "rows_without_id": without_id,
            "not_in_this_batch": sorted(str(i) for i in rows_of if i not in contrast_rows),
            "clean": not duplicated and not without_id and "differs" not in state.values(),
            "clean_means": "No row has a repeated or missing id and no contrast differs from the batch. Absent "
                           "contrasts and rows of other batches are listed, not judged.",
            "index_of": {cid: rows_of[cid][0][0] for cid in sorted(state) if state[cid] == "identical"}}
    return manifest


def render_packet(manifest: Mapping[str, Any], batch: Sequence[Mapping[str, Any]]) -> str:
    """The reviewers' packet: per family, the facts, every wording, the changed fact and the declared sources."""
    by_id = {f["family_id"]: f for f in batch if isinstance(f, dict) and text(f.get("family_id"))}
    check = manifest["software_validation"]

    def counts(table: Mapping[str, int]) -> str:
        return ", ".join(f"{n} {name.replace('_', ' ')}" for name, n in table.items()) or "none"

    out = [f"# Review packet: batch {manifest['batch']['batch_id']}", "",
           f"Source: {manifest['batch']['source']} (SHA-256 `{manifest['batch']['sha256']}`).", "",
           f"Design rules: `{manifest['design']['file']}` (`{manifest['design']['sha256'][:12]}`). Status of those "
           f"rules: {manifest['design']['status']}", "",
           "What has and has not been reviewed:", "",
           f"- **Software validation: {check['status']}** ({check['errors']} errors, {check['warnings']} warnings). "
           f"These are {check['is']}",
           f"- **Owner's read:** {counts(manifest['inventory']['owner_read'])}. This is "
           f"{manifest['review_layers']['owner_read']}",
           f"- **Domain review:** {counts(manifest['inventory']['review_status'])}. A family is reviewed only when a "
           "clinician and a patient-language reviewer have both recorded their items; nothing in this packet does that.",
           f"- **Known concerns:** {manifest['inventory']['concerns']['open']} open, "
           f"{manifest['inventory']['concerns']['closed']} closed. {manifest['inventory']['concerns']['rule']}",
           "- **Sources:** " + (counts(manifest["inventory"]["source_verification"]) or "none") + ". A check shows that "
           "the cited record exists and contains the evidence sentence. It does not show that patients in the family's "
           "population use the expression.",
           "", "No model output appears in this packet.", "",
           f"Measured endpoint, when measured: {manifest['endpoint']['definition']}. It is not "
           + ", ".join(manifest["endpoint"]["is_not"]) + ".", ""]
    for note in manifest["comparisons_not_made"]:
        out.append(f"- {note}")
    out.append("")
    for row in manifest["families"]:
        family = by_id[row["family_id"]]
        review = row["review"]
        out += [f"## {row['family_id']}", "",
                f"Care level {row['right_care']} · ends on \"{row['carrier_frame']}\" + \"{row['target']['text'].strip()}\" · "
                f"split {row['split'] or 'unassigned'} · register stratum `{row['register_stratum']}`"
                + (f" (flags: {', '.join(row['flags'])})" if row["flags"] else ""), "",
                f"Label for reviewers only, in no text: {family.get('condition', 'none given')}", "",
                f"Status: software {'passed' if row['admissible'] else 'FAILED'} · owner read: {review['owner_read']['status']}"
                + (f" ({review['owner_read'].get('note') or review['owner_read'].get('detail')})"
                   if review["owner_read"].get("note") or review["owner_read"].get("detail") else "")
                + f" · clinician: {review['clinician']['status']} · patient language: "
                  f"{review['patient_language_reviewer']['status']} · overall: **{review['status']}**", "",
                "Reference facts:", ""]
        out += [f"- `{fact['fact_id']}` {fact['text']}" for fact in family["reference_facts"]]
        out += ["", "| Wording | Text |", "|---|---|"]
        out += [f"| {name} | {family['texts'][name]} |" for name in
                [n for n in ("medical", "everyday", "medical_paraphrase", "everyday_paraphrase", "changed_fact",
                             "everyday_attribution", "quad_b", "quad_c") if n in family["texts"]]]
        changed = family["changed_fact"] if isinstance(family.get("changed_fact"), dict) else {}
        out += ["", f"Changed fact `{changed.get('fact_id')}`: \"{changed.get('from')}\" became \"{changed.get('to')}\"; "
                    f"right care after the change: level {changed.get('right_care_after')}."]
        if isinstance(family.get("attribution"), dict):
            a = family["attribution"]
            out += ["", f"Patient explanation (adds a belief, analysed apart from register): \"{a.get('clause')}\"; "
                        f"source: {a.get('source') or 'none'} ({a.get('quote_type')})."]
        verified = {(c["expression"], c["identifier"]): c["status"] for c in row["sources"]["verification"]["per_citation"]}
        out += ["", "| Everyday expression | Declared support | Citation check | Source | Evidence sentence |",
                "|---|---|---|---|---|"]
        cited = list(family.get("everyday_sources") or [])
        if isinstance(family.get("attribution"), dict) and family["attribution"].get("quote_type") != "none":
            cited.append({**family["attribution"], "expression": family["attribution"].get("clause")})
        for entry in cited:
            unsourced = entry.get("quote_type") == "none"
            out.append(f"| {entry.get('expression')} | {'no source' if unsourced else entry.get('quote_type')} | "
                       f"{'' if unsourced else verified.get((entry.get('expression'), entry.get('pmid_or_doi')), 'not_checked').replace('_', ' ')} | "
                       f"{'' if unsourced else str(entry.get('source'))[:90]} {'' if unsourced else entry.get('pmid_or_doi') or ''} | "
                       f"{entry.get('evidence') or ('' if unsourced else 'not given')} |")
        records = row["concerns"]["records"]
        out += ["", "Known concerns: " + ("none recorded." if not records else
                                          f"{row['concerns']['open']} open, {row['concerns']['closed']} closed.")]
        for c in records:
            d = c["disposition"]
            out.append(f"- `{c['concern_id']}` **{c['state']}** · {c['kind'].replace('_', ' ')} · applies to "
                       f"{', '.join(c['applies_to'])} · {c['text']} (raised by {c['raised_by']}, {c['raised_on']}). "
                       f"Disposition: {d['status'].replace('_', ' ')}"
                       + (f", {d['by']}, {d['date']}: {d['note']}" if d.get("by") else (f": {d['note']}" if d.get("note") else ""))
                       + (f" Not applied: {c['state_reason']}." if c.get("state_reason") else ""))
        problems = row["validation"]["errors"] + row["validation"]["warnings"]
        out += ["", "Software findings: " + ("none." if not problems else "")]
        out += [f"- ERROR {m}" for m in row["validation"]["errors"]] + [f"- warning {m}" for m in row["validation"]["warnings"]]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def review_form(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Blank review rows for the two reviewers, bound to each family's current texts."""
    rubric = read_json(RUBRIC_PATH)["pair_equivalence_review"]
    rows = [{"family_id": row["family_id"], "role": reviewer["role"], "reviewer": None, "reviewer_kind": None,
             "date": None, "texts_sha256": row["texts_sha256"], "review_basis_sha256": row["review_basis_sha256"],
             "open_concerns": [c["concern_id"] for c in row["concerns"]["records"] if c["state"] == "open"],
             "items": {item: None for item in reviewer["reviews"]}}
            for row in manifest["families"] if row["admissible"] for reviewer in rubric["reviewers"]]
    return {"schema": REVIEW_FORM_SCHEMA, "batch_id": manifest["batch"]["batch_id"],
            "returns_as": REVIEWS_SCHEMA, "values": rubric["values"], "missing_value": rubric["missing_value"],
            "status_rule": rubric["status_rule"], "not_a_review": rubric["not_a_review"],
            "instructions": "Fill reviewer, reviewer_kind ('human'), date and every item. Leave an item null when it was "
                            "not reviewed; null is never read as 'same'. Keep review_basis_sha256 as given: it binds the "
                            "review to this version of the texts, reference facts and care labels. A review does not close "
                            "a listed concern; a disposition does. Return the rows under the key 'reviews' in a "
                            f"{REVIEWS_SCHEMA} document.",
            "reviews": rows}


def write_outputs(out_dir: Path, files: Mapping[str, bytes], allow_roots: Iterable[Path | str] = ()) -> dict[str, str]:
    """Create each output; leave an identical one alone; refuse to replace one that differs."""
    states: dict[str, str] = {}
    targets = {name: check_output_path(out_dir / name, allow_roots) for name in files}
    for name, path in targets.items():
        if path.exists():
            require(path.read_bytes() == files[name], "output_differs",
                    f"{path} exists with other content. Outputs are never overwritten: choose a new --out directory")
    for name, path in targets.items():
        if path.exists():
            states[name] = "unchanged"
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_write_bytes(path, files[name])
        states[name] = "written"
    return states


def file_record(path: Path) -> dict[str, str]:
    """How an input file is named in a manifest: its file name and SHA-256, never a machine path."""
    return {"name": path.name, "sha256": sha256_bytes(path.read_bytes())}


def intake_files(batch_path: Path, *, batch_id: str, source_ref: str | None = None, design_path: Path | None = None,
                 **options: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Read a batch file, run the intake and render the three outputs as bytes."""
    data = batch_path.read_bytes()
    batch = read_json(batch_path)
    design = load_design(design_path)
    manifest = run_intake(batch, batch_id=batch_id, batch_sha256=sha256_bytes(data),
                          source_ref=source_ref or batch_path.name, design=design,
                          design_sha256=sha256_bytes((design_path or DESIGN_PATH).read_bytes()), **options)
    files = {"intake_manifest.json": json_bytes(manifest),
             "review_packet.md": render_packet(manifest, batch).encode("utf-8"),
             "review_form.json": json_bytes(review_form(manifest))}
    return manifest, files
