"""Export the site's Multi-turn page data from the landed wave-2 runs and the design note's section 10 artifact.

The site's `multi-turn/index.html` reads two files, written here into `<site>/data/`:

- `petri_multiturn_summary.json`: the headline and the style sentence (the design note's registered wording, verbatim),
  the primary test's counts and p-values, the scenario gate, D per conversation triple with its partition and
  eligibility, the scenario means, the "does it repeat" table, the status block and the provenance.
- `petri_multiturn_conversations.json`: the measures, the mechanisms, the seeds, every conversation exchange by exchange
  with its graded reply and grades, the rule outcomes, and one scripted turn in its three wordings.

The page reads both or neither (it falls back to the two `.sample.json` fixtures). `--write-samples` writes those two
fixtures from SYNTHETIC input (scripts/petri_multiturn_synthetic.py), in the same shapes.

Owner-run, once, after the design note's section 10 analysis (`scripts/petri_w2_register_contrast.py --final`) has run
on the final data. It is not part of the daily Routine's publish chain. Usage:

  python scripts/export_petri_multiturn.py --analysis data/petri/w2_register_contrast.json \\
      --site ../patientwords [--previous ../patientwords/data/petri_multiturn_summary.json] [--dry-run] \\
      data/petri/runs/<run> [data/petri/runs/<run> ...]
  python scripts/export_petri_multiturn.py --write-samples --site ../patientwords

`--dry-run` checks every input and prints what it would write, writing nothing. `--previous` prints every summary cell
that differs from an earlier summary file. Exit 0 on success, 2 on a refusal (nothing is written).

What it refuses, by name, before writing anything (AGENTS.md: no silent failures):
- an artifact that is not final, that was administratively truncated (the summary has no field that would say so),
  that records no analysis commit, or that ran with any input git could not show committed;
- run directories that are not exactly the runs the artifact covers: the run stems, each run id, and each manifest's
  and judgments file's sha256 must be the ones the artifact recorded; each transcripts and rule-outcomes file must be
  the one its manifest binds;
- a run whose publication conditions do not hold (docs/petri_integration_design.md section 4): no bound environment
  lock (`harness.environment_lock_sha256`), no bound raw log with its custody, a raw log marked published, no bound
  sanitised projection, no holdout block, or a holdout-seal contract check that did not pass;
- a missing final row: every exchange of every exported conversation must carry one final-reply row for each
  instrument the judge plans at that reply (the response-only tier, the contextual tier from the second assistant
  message on, and every outcome dimension the seed judges, as judge_runner.plan_record plans them);
- a conversation without its rule outcome;
- a missing measure mapping: every row shown, and every instrument a seed judges, needs a measure in
  data/petri/multiturn_measures.json, whose values and kind must agree with the rubric and the outcome registry;
- a registered text that differs from the design note (data/petri/w2_registered_wording.json is re-read against
  docs/petri_wave2_design.md sections 10.2 and 10.3 on every export);
- a D the rows do not reproduce: for every triple the exporter recomputes D(colloquial, clinical) over the exchanges
  the artifact counts as comparable, and refuses when an entering triple's sum, n or D, the primary test's counts or
  a scenario mean differ from the artifact's;
- a tool result that is not the seed's scripted result (the page labels every tool result as text the study wrote);
- a sealed Tier B phrase anywhere in the output (reported by label only).

What the engine computes and the page only renders: D for every triple (the artifact's value for an entering triple;
for a triple below its floor, the same mean over the exchanges the artifact counts as comparable, marked not
eligible; null when a conversation is missing or no exchange is comparable), the scenario means, and the "does it
repeat" table (per seed: the campaign epochs with an entering triple, and how many of them have a mean D, the two
speakers of an identity seed pooled as the gate pools them, in the primary test's direction; null when the primary
test has no direction). The headline is the section 10.2 row the artifact selects, its text the table's cell
verbatim; a row that is not selectable as registered, `not_computable` or `no_prespecified_row` is carried by name
with no text. The style sentence follows section 10.3 the same way. `status.clinician_review` is "pending" while any
of its three sources (the advice rubric, the outcome registry, the seed file, and the entries of each the page uses)
is marked draft; with none marked draft the exporter refuses, because no file records a clinician review.
`status.vendor_pack` is the latest lane "petri" entry for anthropic in ops/disclosure_log.jsonl, or nulls.

The keys are the site samples' (tests/fixtures/petri_multiturn_site_contract.json holds their skeleton), with these
readings: a triple's partition is the page's `seen_before_plan` for the plan's `discovery`; a headline that is not
selectable as registered has row_id `not_selectable_as_registered:<row>`; the reverse direction keeps the artifact's
`row4/<row>` id and row 4's text; a style sentence with the added clause is `style_larger+vocabulary_also_lowered`;
the summary's `seed` is the analysis's bootstrap seed and the conversations file's is null (nothing in it is random).
Two keys go beyond the samples: a tool result in `interim` carries `fixture: true`, and a grade judged under a prompt
file or rubric other than the current one carries `superseded: <the digest it was judged under>` (shown, never
compared). A null answer is `{"v": null}`.

No medical vocabulary lives here: seed ids, labels, mechanisms and registered texts are read from data files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

if not __package__:
    # Run as a file path: put THIS checkout's root first. A fallback that inserts it only when the import fails is
    # not enough here: an environment whose .pth file puts another checkout of the engine on sys.path (an editable
    # install, a second worktree) would satisfy `scripts.petri_audit` from that checkout, and every data path below
    # (framework.ROOT) would then name the other checkout's files.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.petri_audit import judge_runner  # noqa: E402
from scripts.petri_audit.framework import (  # noqa: E402
    ADVICE_RUBRIC,
    OUTCOME_REGISTRY,
    ROOT,
    SEED_FILE,
    load_json,
    prompt_digest,
    sha256_file,
)
from scripts.petri_audit.manifest import ARTIFACT_FILENAMES  # noqa: E402
from scripts.petri_audit.seal import scan_strings, sealed_registry  # noqa: E402
from scripts.petri_audit.seeds import ROOT_BRANCH, text_of, texts_by_key, tool_result_for  # noqa: E402

if Path(ROOT).resolve() != Path(__file__).resolve().parents[1]:
    raise ImportError(f"scripts.petri_audit was imported from {ROOT}, not from this checkout "
                      f"({Path(__file__).resolve().parents[1]}); its data paths would name the other checkout's files")

SUMMARY_NAME = "petri_multiturn_summary"
CONVERSATIONS_NAME = "petri_multiturn_conversations"
VOCABULARY_FILE = ROOT / "data" / "petri" / "multiturn_measures.json"
WORDING_FILE = ROOT / "data" / "petri" / "w2_registered_wording.json"
DESIGN_NOTE = ROOT / "docs" / "petri_wave2_design.md"
SWAPS_FILE = ROOT / "data" / "petri" / "lay_careful_swaps.draft.json"
DISCLOSURE_LOG = ROOT / "ops" / "disclosure_log.jsonl"
DEFAULT_SITE = ROOT.parent / "patientwords"

# the chain-verification command the page prints; the runs must sit in this checkout's data/petri/runs
RUNS_SUBPATH = ("data", "petri", "runs")
RUNS_DIR = ROOT.joinpath(*RUNS_SUBPATH)
VERIFY_COMMAND = "python -m scripts.petri_audit.cli verify-chain --data-dir " + "/".join(RUNS_SUBPATH)
# the three wordings, in the page's order (the register ids of the framing registry)
COLLOQUIAL, CAREFUL_LAY, CLINICAL = "colloquial", "lay_careful", "clinical"
REGISTERS = (COLLOQUIAL, CAREFUL_LAY, CLINICAL)
# 10.1's outcome, the rows D is computed on
PRIMARY_ROW = ("tier", "response_only")
PRIMARY_CONTRAST = "primary"
# the artifact's partitions (the plan's) and the page's names for them
PARTITION_LABEL = {"discovery": "seen_before_plan", "prospective": "prospective"}
# the section 10.2 and 10.3 ids the table has no text for: carried by name, never worded here
UNWORDED_ROWS = ("not_computable", "no_prespecified_row")
UNWORDED_STATEMENTS = ("not_computable", "no_prespecified_statement")
NOT_SELECTABLE = "not_selectable_as_registered"
ALSO_LOWERED = "vocabulary_also_lowered"
DISCLOSURE_LANE, DISCLOSURE_VENDOR = "petri", "anthropic"
REVIEW_PENDING = "pending"
MEASURE_KINDS = ("ordinal", "nominal", "binary")

SAMPLE_NOTES = {
    SUMMARY_NAME: ("SYNTHETIC SAMPLE: numbers are random, the headline is a placeholder. The real file comes from "
                   "scripts/export_petri_multiturn.py after the design note's section 10 analysis runs once."),
    CONVERSATIONS_NAME: ("SYNTHETIC SAMPLE for building the page: placeholder text, randomly assigned grades. "
                         "Not results."),
}


class ExportRefusal(Exception):
    """An input the exporter cannot publish, refused by name; nothing is written."""


# ------------------------------------------------------------------ small readers


def _load(path: Path, what: str) -> Any:
    if not Path(path).is_file():
        raise ExportRefusal(f"{what} {path} not found")
    try:
        return load_json(path)
    except ValueError as exc:
        raise ExportRefusal(f"{what} {path} does not parse: {exc}") from exc


def _jsonl(path: Path, what: str) -> list[dict]:
    if not Path(path).is_file():
        raise ExportRefusal(f"{what} {path} not found")
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ExportRefusal(f"{what} {path} line {n} does not parse: {exc}") from exc
        if not isinstance(row, dict):
            raise ExportRefusal(f"{what} {path} line {n} is not a JSON object")
        out.append(row)
    return out


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _sign(x: Fraction | int) -> int:
    return (x > 0) - (x < 0)


# ------------------------------------------------------------------ the section 10 artifact


def load_artifact(path: Path) -> dict[str, Any]:
    """The artifact `scripts/petri_w2_register_contrast.py --final` writes, refused unless it is the final, untruncated
    analysis and names the commit it ran from with every input committed."""
    doc = _load(path, "the section 10 artifact")
    if not isinstance(doc, dict):
        raise ExportRefusal(f"the section 10 artifact {path} is not a JSON object")
    if doc.get("final") is not True:
        raise ExportRefusal(f"the section 10 artifact {path} is not final (final: {doc.get('final')!r}); the page "
                            f"publishes only the once-only --final analysis (design note 10.6)")
    if doc.get("administratively_truncated") is not False:
        raise ExportRefusal(f"the section 10 artifact {path} is administratively truncated "
                            f"({doc.get('truncation_reason')!r}; fires not landed: {doc.get('fires_not_landed')}), "
                            f"and the summary has no field that would tell the page's reader so: an owner decision")
    ident = doc.get("identity")
    commit = ident.get("commit") if isinstance(ident, dict) else None
    if not (isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ExportRefusal(f"the section 10 artifact {path} records no analysis commit (identity.commit {commit!r})")
    changes = ident.get("uncommitted_changes")
    if not isinstance(changes, dict) or not changes:
        raise ExportRefusal(f"the section 10 artifact {path} records no identity.uncommitted_changes, so its commit "
                            f"cannot be shown to name the code and data it ran from")
    dirty = sorted(k for k, v in changes.items() if v != [])
    if dirty:
        raise ExportRefusal(f"the section 10 artifact {path} ran with inputs git did not show committed ({dirty}); the "
                            f"analysis commit it records would not name them")
    for key, kind in (("coverage", dict), ("triples", list), ("section_10_2", dict), ("section_10_3", dict)):
        if not isinstance(doc.get(key), kind):
            raise ExportRefusal(f"the section 10 artifact {path} has no {key} {kind.__name__}")
    if not _count(doc.get("bootstrap_seed")):
        raise ExportRefusal(f"the section 10 artifact {path} records no bootstrap_seed")
    return doc


# ------------------------------------------------------------------ the page vocabulary (data)


@dataclass(frozen=True)
class MeasureSpec:
    """One grade the page can show: the rows it reads (`row`), or the flag it reads off another measure's rows
    (`flag_of` = kind, key, flag), its values (low to high), and the digest a current row carries."""
    id: str
    row: tuple[str, str] | None
    flag_of: tuple[str, str, str] | None
    label: str
    kind: str
    values: tuple[str, ...]
    definition: str | None
    digest: str

    @property
    def source(self) -> tuple[str, str]:
        return self.row if self.row is not None else (self.flag_of[0], self.flag_of[1])

    def exported(self) -> dict[str, Any]:
        return {"id": self.id, "row": list(self.row) if self.row else None, "label": self.label, "kind": self.kind,
                "values": list(self.values), "definition": self.definition}


@dataclass(frozen=True)
class Vocabulary:
    measures: tuple[MeasureSpec, ...]
    mechanisms: dict[str, dict[str, str]]
    mechanism_of: dict[str, str]
    example: dict[str, Any]
    samples: dict[str, Any]

    def by_row(self) -> dict[tuple[str, str], MeasureSpec]:
        return {m.row: m for m in self.measures if m.row is not None}


def load_vocabulary(path: Path, rubric: Mapping[str, Any], registry: Mapping[str, Any]) -> Vocabulary:
    """The measure map, mechanisms, example and sample settings, checked against the rubric (tier rows: its tier ids in
    order, its flags) and the outcome registry (outcome rows: the dimension's values in order, `ordinal` iff the kind
    is ordinal, the definition). Every problem is refused by name."""
    doc = _load(path, "the page vocabulary")
    problems: list[str] = []
    tiers = tuple(t["id"] for t in rubric.get("tiers") or [])
    flags = {f["id"] for f in rubric.get("flags") or []}
    tier_instruments = {k for k in (registry.get("tier_instruments") or {}) if not k.startswith("_")}
    dims = {d["id"]: d for d in registry.get("dimensions") or []}
    rubric_digest = judge_runner.rubric_digest(dict(rubric))
    measures: list[MeasureSpec] = []
    raw = doc.get("measures") if isinstance(doc, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ExportRefusal(f"the page vocabulary {path} has no measures list")
    pending_flags: list[tuple[int, dict]] = []
    for i, m in enumerate(raw):
        where = f"measure {i + 1} ({m.get('id') if isinstance(m, dict) else m!r})"
        if not isinstance(m, dict) or not _text(m.get("id")) or not _text(m.get("label")):
            problems.append(f"{where}: needs an id and a label")
            continue
        values = m.get("values")
        if m.get("kind") not in MEASURE_KINDS:
            problems.append(f"{where}: kind {m.get('kind')!r} is not one of {list(MEASURE_KINDS)}")
            continue
        if not (isinstance(values, list) and values and all(_text(v) for v in values)
                and len(set(values)) == len(values)):
            problems.append(f"{where}: values must be a non-empty list of distinct strings")
            continue
        row = m.get("row")
        if row is None:
            pending_flags.append((i, m))
            continue
        if not (isinstance(row, list) and len(row) == 2 and all(_text(x) for x in row)):
            problems.append(f"{where}: row must be [kind, key] or null")
            continue
        kind, key = row
        if kind == "tier":
            if key not in tier_instruments:
                problems.append(f"{where}: tier instrument {key!r} is not in the outcome registry")
            elif tuple(values) != tiers:
                problems.append(f"{where}: values {values} are not the rubric's tiers in order {list(tiers)}")
            elif m["kind"] != "ordinal":
                problems.append(f"{where}: a tier is ordinal, not {m['kind']}")
            else:
                measures.append(MeasureSpec(m["id"], (kind, key), None, m["label"], m["kind"], tuple(values), None,
                                            rubric_digest))
        elif kind == "outcome":
            dim = dims.get(key)
            if dim is None:
                problems.append(f"{where}: outcome dimension {key!r} is not in the outcome registry")
            elif list(values) != list(dim.get("values") or []):
                problems.append(f"{where}: values {values} are not the registry's {dim.get('values')}")
            elif (m["kind"] == "ordinal") != (dim.get("ordinal") is True) or m["kind"] == "binary":
                problems.append(f"{where}: kind {m['kind']} disagrees with the registry "
                                f"(ordinal: {dim.get('ordinal')})")
            else:
                digest = prompt_digest(dim["detection"]["judge_prompt_ref"])
                measures.append(MeasureSpec(m["id"], (kind, key), None, m["label"], m["kind"], tuple(values),
                                            dim.get("definition"), digest))
        else:
            problems.append(f"{where}: row kind {kind!r} is neither tier nor outcome")
    mapped = {x.row: x for x in measures}
    for i, m in pending_flags:
        where = f"measure {i + 1} ({m['id']})"
        f = m.get("flag_of")
        src = tuple(f.get("row") or ()) if isinstance(f, dict) else ()
        if len(src) != 2 or not _text(f.get("flag")):
            problems.append(f"{where}: a measure without a row needs flag_of {{row: [kind, key], flag}}")
        elif src not in mapped:
            problems.append(f"{where}: flag_of row {list(src)} is not itself a mapped measure")
        elif src[0] == "tier" and f["flag"] not in flags:
            problems.append(f"{where}: flag {f['flag']!r} is not one of the rubric's flags {sorted(flags)}")
        elif m["kind"] != "binary" or len(m["values"]) != 2:
            problems.append(f"{where}: a flag measure is binary with two values (false, then true)")
        else:
            measures.append(MeasureSpec(m["id"], None, (src[0], src[1], f["flag"]), m["label"], m["kind"],
                                        tuple(m["values"]), None, mapped[src].digest))
    ids = [x.id for x in measures]
    if len(ids) != len(set(ids)):
        problems.append(f"measure ids repeat: {sorted(k for k, n in Counter(ids).items() if n > 1)}")
    rows = [x.row for x in measures if x.row]
    if len(rows) != len(set(rows)):
        problems.append("two measures read the same rows")
    mech = doc.get("mechanisms")
    mechanisms: dict[str, dict[str, str]] = {}
    mechanism_of: dict[str, str] = {}
    if not isinstance(mech, dict) or not mech:
        problems.append("mechanisms must map each mechanism id to {title, question, seeds}")
    else:
        for mid, entry in mech.items():
            if not (isinstance(entry, dict) and _text(entry.get("title")) and _text(entry.get("question"))
                    and isinstance(entry.get("seeds"), list) and all(_text(s) for s in entry["seeds"])):
                problems.append(f"mechanism {mid!r}: needs a title, a question and a list of seeds")
                continue
            mechanisms[mid] = {"title": entry["title"], "question": entry["question"]}
            for sid in entry["seeds"]:
                if sid in mechanism_of:
                    problems.append(f"seed {sid} is listed under mechanisms {mechanism_of[sid]!r} and {mid!r}")
                mechanism_of[sid] = mid
    example = doc.get("example")
    if not (isinstance(example, dict) and _text(example.get("seed_id")) and _count(example.get("turn"))
            and example["turn"] >= 1):
        problems.append("example must be {seed_id, turn}")
    samples = doc.get("samples")
    if not (isinstance(samples, dict) and isinstance(samples.get("seed_ids"), list) and samples["seed_ids"]
            and _count(samples.get("epochs")) and samples["epochs"] >= 1 and _count(samples.get("rng_seed"))):
        problems.append("samples must be {seed_ids, epochs, rng_seed}")
    if problems:
        raise ExportRefusal(f"the page vocabulary {path}: " + "; ".join(problems))
    # measures keep the file's order (a flag measure was held back only until its source was known)
    order = {m["id"]: i for i, m in enumerate(raw) if isinstance(m, dict)}
    measures.sort(key=lambda x: order[x.id])
    return Vocabulary(tuple(measures), mechanisms, mechanism_of, dict(example), dict(samples))


# ------------------------------------------------------------------ the registered wording (checked against the note)


@dataclass(frozen=True)
class Wording:
    rows: dict[str, str]          # 10.2: row1..row5 -> the 'What may be said' cell, verbatim
    statements: dict[str, str]    # 10.3: statement id -> the bullet's text after its label, verbatim


def _section(note: str, heading: str, where: Path) -> str:
    start = note.find("\n" + heading)
    if start < 0:
        raise ExportRefusal(f"{where}: no section starting {heading!r}")
    end = note.find("\n### ", start + 1)
    return note[start + 1: end if end >= 0 else len(note)]


def note_table_rows(section: str, header: str) -> list[list[str]]:
    """The body rows of the markdown table whose header row names `header`, as stripped cells."""
    lines = section.splitlines()
    at = next((i for i, ln in enumerate(lines) if ln.startswith("|") and header in ln), None)
    if at is None:
        return []
    rows = []
    for ln in lines[at + 2:]:
        if not ln.startswith("|"):
            break
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows


def note_bullets(section: str, list_heading: str) -> dict[str, str]:
    """The nested bullets under the top-level bullet that starts `list_heading`, as {bold label: text after it}, each
    bullet's wrapped lines joined with single spaces (the text a markdown reader sees)."""
    lines = section.splitlines()
    at = next((i for i, ln in enumerate(lines) if ln.startswith(list_heading)), None)
    if at is None:
        return {}
    bullets: list[str] = []
    cur: str | None = None
    for ln in lines[at + 1:]:
        if ln.startswith("  - "):
            if cur is not None:
                bullets.append(cur)
            cur = ln[4:].strip()
        elif ln.startswith("    ") and cur is not None:
            cur += " " + ln.strip()
        elif ln.startswith("  ") and cur is None:
            continue            # the heading bullet's own continuation line
        else:
            break
    if cur is not None:
        bullets.append(cur)
    out = {}
    for b in bullets:
        m = re.match(r"\*\*(.+?):\*\* (.*)$", b)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def load_wording(path: Path, design_note: Path) -> Wording:
    """The registered texts, refused unless each is the design note's, character for character."""
    doc = _load(path, "the registered wording")
    if not Path(design_note).is_file():
        raise ExportRefusal(f"the design note {design_note} not found")
    note = Path(design_note).read_text(encoding="utf-8")
    problems: list[str] = []
    s2, s3 = doc.get("section_10_2") or {}, doc.get("section_10_3") or {}
    table = note_table_rows(_section(note, s2.get("heading", "### 10.2 "), design_note), s2.get("table_header", ""))
    rows: dict[str, str] = {}
    data_rows = s2.get("rows") or []
    if len(table) != len(data_rows):
        problems.append(f"section 10.2's table has {len(table)} rows, the wording file {len(data_rows)}")
    for i, (cells, row) in enumerate(zip(table, data_rows), 1):
        mine = [row.get(k) for k in ("primary_test", "general_gate", "prospective_partition", "text")]
        if row.get("row_id") != f"row{i}":
            problems.append(f"wording row {i} is named {row.get('row_id')!r}, not row{i}")
        elif cells != mine:
            problems.append(f"{row.get('row_id')} differs from section 10.2's table row {i}")
        else:
            rows[row["row_id"]] = row["text"]
    bullets = note_bullets(_section(note, s3.get("heading", "### 10.3 "), design_note), s3.get("list_heading", ""))
    statements: dict[str, str] = {}
    for st in s3.get("statements") or []:
        sid, label = st.get("statement_id"), st.get("label")
        if bullets.get(label) != st.get("text"):
            problems.append(f"statement {sid!r} differs from section 10.3's bullet {label!r}")
        else:
            statements[sid] = st["text"]
    if not rows or not statements:
        problems.append("no registered row or statement was read")
    if problems:
        raise ExportRefusal(f"the registered wording {path} is not the design note's ({design_note}): "
                            + "; ".join(problems))
    return Wording(rows, statements)


# ------------------------------------------------------------------ runs


def publication_problems(manifest: Mapping[str, Any]) -> list[str]:
    """Why a run may not be published (docs/petri_integration_design.md section 4, 'Publication conditions'), or []."""
    problems = []
    harness = manifest.get("harness") if isinstance(manifest.get("harness"), dict) else {}
    if not _text(harness.get("environment_lock_sha256")):
        problems.append("harness.environment_lock_sha256 is missing, so the environment lock the run executed under "
                        "is not bound")
    art = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    if not _text(art.get("raw_eval_log_sha256")) or not art.get("raw_eval_log_custody"):
        problems.append("the raw .eval log is not bound with its custody (artifacts.raw_eval_log_sha256, "
                        "raw_eval_log_custody)")
    if art.get("raw_eval_log_published") is not False:
        problems.append(f"artifacts.raw_eval_log_published is {art.get('raw_eval_log_published')!r}; the raw .eval is "
                        f"never published")
    sanitiser = art.get("sanitiser")
    if not _text(art.get("sanitised_log_sha256")) or not (isinstance(sanitiser, dict)
                                                          and _text(sanitiser.get("allowlist_sha256"))):
        problems.append("no sanitised allowlist projection is bound (artifacts.sanitised_log_sha256, sanitiser)")
    hold = manifest.get("holdout")
    if not isinstance(hold, dict) or not isinstance(hold.get("consumed"), bool):
        problems.append("the manifest has no holdout block recording whether a sealed phrase was consumed")
    elif hold["consumed"] and not hold.get("consumption_registry_ref"):
        problems.append("the holdout block records a consumed sealed phrase without its registry entry")
    checks = (manifest.get("execution") or {}).get("contract_checks") or {}
    seal = checks.get("holdout_seal")
    status = seal.get("status") if isinstance(seal, dict) else seal
    if status != "pass":
        problems.append(f"the holdout-seal contract check is {status!r}, not 'pass'")
    return problems


def collapse_retries(judgments: Sequence[dict]) -> tuple[list[dict], int]:
    """The latest judgment per `judge_runner.dedupe_key`, in file order, and how many it superseded: a retried null is
    decided by its retry, as the section 10 analysis and the run's own totals decide it."""
    latest: dict[tuple, int] = {}
    for i, j in enumerate(judgments):
        latest[judge_runner.dedupe_key(j)] = i
    keep = sorted(latest.values())
    return [judgments[i] for i in keep], len(judgments) - len(keep)


@dataclass
class RunData:
    stem: str
    path: Path
    manifest: dict
    rows: list[dict]
    superseded_by_retry: int
    records: dict[str, dict]
    rules: dict[str, dict]
    trees: dict[str, tuple[dict, dict]]


def load_run(path: Path, recorded: Mapping[str, Any], seeds: Mapping[str, dict]) -> RunData:
    """One run directory, refused unless its publication conditions hold and its files are the bytes the artifact
    and its own manifest bound; its analysis rows rebuilt as the section 10 analysis rebuilt them."""
    path = Path(path)
    where = path.name
    if not path.is_dir():
        raise ExportRefusal(f"{path}: no such run directory")
    manifest = _load(path / "manifest.json", f"run {where}:")
    if not isinstance(manifest, dict):
        raise ExportRefusal(f"run {where}: manifest.json is not an object")
    problems = publication_problems(manifest)
    if problems:
        raise ExportRefusal(f"run {where}: the publication conditions do not hold: " + "; ".join(problems))
    if sha256_file(path / "manifest.json") != recorded.get("manifest_sha256"):
        raise ExportRefusal(f"run {where}: manifest.json is not the manifest the section 10 artifact read (sha256 "
                            f"differs from {recorded.get('manifest_sha256')!r})")
    if manifest.get("run_id") != recorded.get("run_id"):
        raise ExportRefusal(f"run {where}: run id {manifest.get('run_id')!r} is not the artifact's "
                            f"{recorded.get('run_id')!r}")
    art = manifest.get("artifacts") or {}
    files = {family: path / name for family, name in ARTIFACT_FILENAMES.items()}
    for family in ("judgments", "transcripts", "rule_outcomes"):
        if not files[family].is_file():
            raise ExportRefusal(f"run {where}: {files[family].name} is missing")
    judgments_sha = sha256_file(files["judgments"])
    if judgments_sha != recorded.get("judgments_sha256"):
        raise ExportRefusal(f"run {where}: judgments.jsonl is not the file the section 10 artifact read (sha256 "
                            f"{judgments_sha[:12]} against the artifact's "
                            f"{str(recorded.get('judgments_sha256'))[:12]})")
    for family in ("judgments", "transcripts", "rule_outcomes"):
        if sha256_file(files[family]) != art.get(f"{family}_sha256"):
            raise ExportRefusal(f"run {where}: {files[family].name} is not the file its manifest binds")
    collapsed, superseded = collapse_retries(_jsonl(files["judgments"], f"run {where}:"))
    try:
        rows = judge_runner.analysis_rows(collapsed, manifest, dict(seeds))
    except (ValueError, KeyError) as exc:
        raise ExportRefusal(f"run {where}: judge_runner.analysis_rows refused it: {exc}") from exc
    records: dict[str, dict] = {}
    for rec in _jsonl(files["transcripts"], f"run {where}:"):
        cid = rec.get("conversation_id")
        if cid in records:
            raise ExportRefusal(f"run {where}: two transcript records for conversation {cid}")
        records[cid] = rec
    rules: dict[str, dict] = {}
    for rule in _jsonl(files["rule_outcomes"], f"run {where}:"):
        cid = rule.get("conversation_id")
        if cid in rules:
            raise ExportRefusal(f"run {where}: two rule outcomes for conversation {cid}")
        if not isinstance(rule.get("outcomes"), dict):
            raise ExportRefusal(f"run {where}: the rule outcome of conversation {cid} has no outcomes object")
        rules[cid] = rule["outcomes"]
    trees: dict[str, tuple[dict, dict]] = {}
    for tree in manifest.get("trees") or []:
        for branch in tree.get("branches") or []:
            trees[branch["conversation_id"]] = (tree, branch)
    return RunData(where, path, manifest, rows, superseded, records, rules, trees)


# ------------------------------------------------------------------ seeds


def seed_cells(seed: Mapping[str, Any]) -> tuple[list[str | None], dict[tuple[str | None, str], dict]]:
    """A seed's speakers in first-appearance order, and its arm for each (speaker, register): the speaker is the arm's
    `user_is` when speaker identity is a declared factor, none otherwise; the register is that of the arm's turn-1
    text (the section 10 analysis reads them the same way)."""
    factor = (seed.get("speaker_identity") or {}).get("policy") == "factor"
    texts = texts_by_key(dict(seed))
    speakers: list[str | None] = []
    cells: dict[tuple[str | None, str], dict] = {}
    for arm in seed["protocol"]["arms"]:
        register = texts[arm["turns"][0]["text_ref"]]["register"]
        speaker = arm["user_is"] if factor else None
        if register not in REGISTERS:
            raise ExportRefusal(f"seed {seed['seed_id']}: arm {arm['id']} is in register {register!r}")
        if (speaker, register) in cells:
            raise ExportRefusal(f"seed {seed['seed_id']}: two arms realise ({speaker}, {register})")
        if speaker not in speakers:
            speakers.append(speaker)
        cells[(speaker, register)] = arm
    return speakers, cells


def swaps_of(seed_id: str, declared: Mapping[str, Any] | None, n_turns: int) -> dict[str, list[list[Any]]] | None:
    """The declared [clinical span, careful-lay span] pairs of a second-set seed per speaker prefix ('' without speaker
    arms, else '<speaker>_') as a list indexed by exchange, a turn shared by both speakers applied to each."""
    if declared is None:
        return None
    out: dict[str, list[list[Any]]] = {}
    for key, pairs in declared.items():
        turn, _, rest = key.partition("_")
        if not (turn.startswith("t") and turn[1:].isdigit() and rest.endswith(CAREFUL_LAY)):
            raise ExportRefusal(f"swaps of {seed_id}: key {key!r} is not t<NN>_[<speaker>_]{CAREFUL_LAY}")
        n = int(turn[1:])
        if not 1 <= n <= n_turns:
            raise ExportRefusal(f"swaps of {seed_id}: key {key!r} names turn {n} of {n_turns}")
        prefix = rest[: -len(CAREFUL_LAY)]
        out.setdefault(prefix, [[] for _ in range(n_turns)])[n - 1] = pairs
    shared = out.pop("", None) if len(out) > 1 else None
    for per in (out.values() if shared else ()):
        for i, pairs in enumerate(shared):
            if pairs:
                if per[i]:
                    raise ExportRefusal(f"swaps of {seed_id}: turn {i + 1} is declared both shared and per speaker")
                per[i] = pairs
    return out


# ------------------------------------------------------------------ conversations


def expected_rows(seed: Mapping[str, Any], assistant_index: int) -> set[tuple[str, str]]:
    """The rows judge_runner.plan_record plans for one assistant message: the response-only tier, the contextual tier
    from the second assistant message of the conversation on, and every outcome dimension the seed judges (a gated
    dimension is planned as a not-applicable row, so it has a row too)."""
    judge = seed["judge"]
    out = {("outcome", d) for d in judge["outcome_dimensions"]}
    if judge["advice_tier"].get("response_only"):
        out.add(("tier", "response_only"))
    if judge["advice_tier"].get("contextual") and assistant_index >= 2:
        out.add(("tier", "contextual"))
    return out


def split_exchanges(record: Mapping[str, Any], where: str) -> tuple[list[dict], int]:
    """The record split at its user turns, and the number of system turns before the first (not part of any
    exchange). A message before the first user turn that is not a system turn is refused."""
    out: list[dict] = []
    system = 0
    for t in record.get("turns") or []:
        if t["role"] == "user":
            out.append({"user": t["text"], "msgs": []})
        elif out:
            out[-1]["msgs"].append(t)
        elif t["role"] == "system":
            system += 1
        else:
            raise ExportRefusal(f"{where}: a {t['role']} turn precedes the first user turn")
    return out, system


def _cell(rows: Sequence[dict], m: MeasureSpec, where: str) -> dict | None:
    """The page cell of one measure at one exchange, from its final rows: the row under the measure's current digest,
    or a single row under another digest, shown flagged `superseded` (never compared); two rows under the current
    digest, or several under others, are refused. {"v": value}, {"v": null} for a null answer, {"na": reason}."""
    if not rows:
        return None
    current = [r for r in rows if r.get("prompt_file_digest") == m.digest]
    if len(current) > 1:
        raise ExportRefusal(f"{where}: {len(current)} final rows for {m.source[0]}:{m.source[1]} under digest "
                            f"{m.digest}")
    if not current and len(rows) > 1:
        raise ExportRefusal(f"{where}: {len(rows)} final rows for {m.source[0]}:{m.source[1]}, none under the current "
                            f"digest {m.digest}")
    row = current[0] if current else rows[0]
    if row.get("not_applicable_reason") or row.get("value") == judge_runner.NA:
        cell: dict[str, Any] = {"na": row.get("not_applicable_reason") or "the judge answered not_applicable"}
    elif row.get("value") is None:
        cell = {"v": None}
    elif m.flag_of is None:
        if row["value"] not in m.values:
            raise ExportRefusal(f"{where}: {m.id} value {row['value']!r} is not one of its values {list(m.values)}")
        cell = {"v": row["value"]}
    else:
        flags = row.get("flags")
        flag = flags.get(m.flag_of[2]) if isinstance(flags, dict) else None
        cell = {"v": m.values[1] if flag is True else m.values[0] if flag is False else None}
    if row.get("prompt_file_digest") != m.digest:
        cell["superseded"] = row.get("prompt_file_digest") or "none recorded"
    return cell


def build_conversation(run: RunData, cid: str, seed: Mapping[str, Any], arm: Mapping[str, Any], vocab: Vocabulary,
                       rows: Sequence[dict], notes: Counter) -> list[dict]:
    """One conversation's exchanges: the scripted user turn, the graded reply (the last assistant message of the
    exchange, which the judge grades as final_in_exchange), the other messages as interim (a tool result flagged
    `fixture`), and the grades of the graded reply per measure."""
    where = f"run {run.stem} conversation {cid[:12]}"
    record = run.records.get(cid)
    if record is None:
        raise ExportRefusal(f"{where}: no transcript record")
    exs, system = split_exchanges(record, where)
    notes["system turns outside any exchange"] += system
    if len(exs) != len(arm["turns"]):
        raise ExportRefusal(f"{where}: {len(exs)} exchanges, but arm {arm['id']} scripts {len(arm['turns'])}")
    by_row = vocab.by_row()
    final: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("exchange_index") is None or r.get("final_in_exchange") is None:
            raise ExportRefusal(f"{where}: a judgment row carries no exchange_index or final_in_exchange (judged "
                                f"before the exchange ordinal existed), so it cannot be placed")
        if (r["kind"], r["key"]) not in by_row:
            raise ExportRefusal(f"{where}: rows of {r['kind']}:{r['key']} have no measure in the page vocabulary")
        if r["final_in_exchange"] is True:
            final[(r["exchange_index"], r["kind"], r["key"])].append(r)
        else:
            notes["grades of interim messages not shown (the page shows one graded reply per exchange)"] += 1
    stray = sorted({e for e, _, _ in final if not 1 <= e <= len(exs)})
    if stray:
        raise ExportRefusal(f"{where}: final rows for exchange(s) {stray}, which the transcript does not have")
    calls = {c["call_id"]: c for t in record["turns"] if t["role"] == "assistant" for c in t.get("tool_calls") or []}
    out: list[dict] = []
    assistant_index = 0
    for i, ex in enumerate(exs, 1):
        assistants = [m for m in ex["msgs"] if m["role"] == "assistant"]
        if not assistants:
            raise ExportRefusal(f"{where}: exchange {i} has no assistant reply")
        reply = assistants[-1]
        assistant_index += len(assistants)
        missing = sorted(expected_rows(seed, assistant_index) - {(k, key) for (e, k, key) in final if e == i})
        if missing:
            raise ExportRefusal(f"{where}: no final row for exchange {i}: "
                                + ", ".join(f"{k}:{key}" for k, key in missing))
        turn_ids = {r["turn_id"] for (e, _, _), rs in final.items() if e == i for r in rs}
        if turn_ids != {reply["turn_id"]}:
            raise ExportRefusal(f"{where}: exchange {i}'s final rows grade turn(s) {sorted(turn_ids)}, not its last "
                                f"assistant message (turn {reply['turn_id']})")
        interim = []
        for msg in ex["msgs"]:
            if msg is reply:
                continue
            if msg["role"] == "assistant":
                interim.append({"role": "assistant", "text": msg.get("text") or ""})
            elif msg["role"] == "tool":
                call = calls.get(msg.get("tool_call_id"))
                scripted = None
                if call is not None and not call.get("parse_error"):
                    scripted, _, _ = tool_result_for(dict(seed), call["name"], dict(call.get("arguments") or {}))
                if scripted is None or scripted != msg.get("text"):
                    raise ExportRefusal(f"{where}: the tool result at turn {msg['turn_id']} is not the seed's scripted "
                                        f"result, and the page labels every tool result as text the study wrote")
                interim.append({"role": "tool", "text": msg["text"], "fixture": True})
            else:
                raise ExportRefusal(f"{where}: exchange {i} carries a {msg['role']} turn")
        vals: dict[str, dict] = {}
        for m in vocab.measures:
            cell = _cell(final.get((i, *m.source), []), m, f"{where} exchange {i}")
            if cell is not None:
                vals[m.id] = cell
                if "superseded" in cell:
                    notes["cells graded under a superseded prompt or rubric (flagged, never compared)"] += 1
        text = reply.get("text") or ""
        out.append({"user": ex["user"], "reply": text if text.strip() else None, "reply_turn": reply["turn_id"],
                    "reply_is_graded": True, "interim": interim, "vals": vals})
    return out


# ------------------------------------------------------------------ status


def clinician_review(sources: Mapping[str, Any]) -> tuple[str, list[str]]:
    """'pending' while any source status is marked draft, with the sources that are; refused when none is, because
    no file records a clinician review and the exporter never infers one."""
    drafts = sorted(name for name, status in sources.items() if isinstance(status, str) and "draft" in status.lower())
    if not drafts:
        raise ExportRefusal("none of the rubric, the outcome registry or the seed file (nor any entry of them the page "
                            "uses) is marked draft, but no file records a clinician review: status.clinician_review "
                            "cannot be derived; record the review and extend the exporter (owner decision)")
    return REVIEW_PENDING, drafts


def vendor_pack(log: Path) -> dict[str, str | None]:
    """The latest (last-written) disclosure-log entry of lane 'petri' for anthropic: its pack version and when it was
    sent, or nulls when there is none. A line that does not parse is refused, never skipped."""
    latest = None
    if Path(log).is_file():
        for entry in _jsonl(log, "the disclosure log"):
            if entry.get("lane") == DISCLOSURE_LANE and entry.get("vendor") == DISCLOSURE_VENDOR:
                latest = entry
    if latest is None:
        return {"version": None, "sent": None}
    if not _text(latest.get("pack_version")) or not (latest.get("sent_utc") is None or _text(latest["sent_utc"])):
        raise ExportRefusal(f"the disclosure log {log}: its latest {DISCLOSURE_LANE} entry for {DISCLOSURE_VENDOR} has "
                            f"no pack_version, or a sent_utc that is not a string")
    return {"version": latest["pack_version"], "sent": latest.get("sent_utc")}


# ------------------------------------------------------------------ the export


@dataclass
class Export:
    summary: dict[str, Any]
    conversations: dict[str, Any]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Checkout:
    """Where an export's runs must sit: the directory the page's verify-chain command names, run from the root of the
    repository it belongs to. For a real export this is the checkout's own data/petri/runs (RUNS_DIR)."""
    runs_dir: Path


REPOSITORY = Checkout(RUNS_DIR)


def synthetic_checkout(root: Path) -> Checkout:
    """For SYNTHETIC input only (the tests, --write-samples): runs under `<root>/data/petri/runs`, since synthetic run
    directories are in no repository. The CLI never exports with it."""
    return Checkout(Path(root).joinpath(*RUNS_SUBPATH))


def _verify_command(run_dirs: Sequence[Path], runs_dir: Path) -> str:
    """The chain-verification command the page prints, refused unless every run sits in `runs_dir` itself: a copy of
    the runs in another data/petri/runs would be exported while the command verifies the checkout's own (Codex review
    of 2026-09-24: a suffix check accepted any directory ending in data/petri/runs)."""
    parents = {Path(p).resolve().parent for p in run_dirs}
    if parents != {Path(runs_dir).resolve()}:
        raise ExportRefusal(f"the runs sit in {', '.join(sorted(map(str, parents)))}, not in {runs_dir}, the "
                            f"directory the page's verify-chain command ({VERIFY_COMMAND}) names, so it would verify "
                            f"other bytes than the ones exported")
    return VERIFY_COMMAND


def export(run_dirs: Sequence[Path], artifact_path: Path, *, seeds_path: Path = SEED_FILE,
           rubric_path: Path = ADVICE_RUBRIC, registry_path: Path = OUTCOME_REGISTRY,
           vocabulary_path: Path = VOCABULARY_FILE, wording_path: Path = WORDING_FILE, design_note: Path = DESIGN_NOTE,
           swaps_path: Path = SWAPS_FILE, disclosure_log: Path = DISCLOSURE_LOG,
           seal_registry: Mapping[str, str] | None = None, example: Mapping[str, Any] | None = None,
           checkout: Checkout | None = None) -> Export:
    """Build both files in memory from the run directories and the section 10 artifact; refuse by name on any
    problem. `seal_registry` (phrase -> label) defaults to the study's sealed set; `example` overrides the vocabulary
    file's (the sample fixtures use it); `checkout` defaults to REPOSITORY (synthetic input passes
    synthetic_checkout)."""
    checkout = checkout or REPOSITORY
    artifact = load_artifact(Path(artifact_path))
    rubric = _load(rubric_path, "the advice rubric")
    registry = _load(registry_path, "the outcome registry")
    seed_doc = _load(seeds_path, "the seed file")
    seeds = {s["seed_id"]: s for s in seed_doc.get("seeds") or []}
    vocab = load_vocabulary(vocabulary_path, rubric, registry)
    wording = load_wording(wording_path, design_note)
    swaps_decl = _load(swaps_path, "the declared term swaps").get("seeds") or {}
    rubric_digest = judge_runner.rubric_digest(rubric)
    ranked_under = (artifact["coverage"].get("rubric") or {}).get("digest")
    if ranked_under != rubric_digest:
        raise ExportRefusal(f"the artifact ranked tiers under rubric digest {ranked_under!r}, the rubric in hand is "
                            f"{rubric_digest}")
    runs = _load_runs(run_dirs, artifact, seeds, checkout.runs_dir)
    notes: Counter = Counter()
    for run in runs.values():
        notes["judgments superseded by a retry (the latest per key is read)"] += run.superseded_by_retry
    rows_of: dict[str, list[dict]] = defaultdict(list)
    for run in runs.values():
        for r in run.rows:
            rows_of[r["conversation_id"]].append(r)

    seed_order, set_of = _plan_seeds(artifact["triples"], seeds, vocab)
    convs = _conversations(artifact["triples"], runs, seeds, vocab, rows_of, seed_order, notes)
    swaps = {sid: swaps_of(sid, swaps_decl.get(sid), len(seeds[sid]["protocol"]["arms"][0]["turns"]))
             for sid in seed_order}
    _check_swaps(convs, swaps)
    triples, entering = _triples(artifact["triples"], seeds, rows_of, vocab, rubric_digest)
    primary, scenario_means, direction = _primary(artifact["section_10_2"], entering, seeds, seed_order)
    review, drafts = clinician_review(_draft_sources(rubric, registry, seed_doc, seeds, seed_order))
    order = sorted(runs.values(), key=lambda r: (str(r.manifest.get("created_utc")), r.stem))
    summary = {"seed": artifact["bootstrap_seed"],
               "status": {"final": True, "clinician_review": review, "vendor_pack": vendor_pack(disclosure_log)},
               "headline": _headline(artifact["section_10_2"].get("wording") or {}, wording),
               "style_sentence": _style_sentence(artifact["section_10_3"], wording),
               "primary": primary, "triples": triples, "scenario_means": scenario_means,
               "repeats": _repeats(seed_order, entering, direction),
               "provenance": {"runs": [r.stem for r in order], "analysis_commit": artifact["identity"]["commit"],
                              "verify": _verify_command(run_dirs, checkout.runs_dir)}}
    mechanisms = {mid: dict(v) for mid, v in vocab.mechanisms.items()
                  if any(vocab.mechanism_of[s] == mid for s in seed_order)}
    conversations = {"seed": None, "measures": [m.exported() for m in vocab.measures], "mechanisms": mechanisms,
                     "seeds": [_seed_record(sid, seeds[sid], vocab, set_of[sid], convs, swaps[sid])
                               for sid in seed_order],
                     "conversations": convs,
                     "example": _example(dict(example or vocab.example), seeds, seed_order)}

    # nothing sealed leaves through these files
    registry_sealed = sealed_registry() if seal_registry is None else dict(seal_registry)
    scan = scan_strings([json.dumps(summary, ensure_ascii=False), json.dumps(conversations, ensure_ascii=False)],
                        registry_sealed, "Multi-turn export")
    if scan.status == "fail":
        labels = sorted({label for v in scan.hits.values() for label in v})
        raise ExportRefusal(f"sealed Tier B phrase(s) in the export, by label: {labels}")
    pack = summary["status"]["vendor_pack"]
    lines = [f"{n} {what}" for what, n in sorted(notes.items()) if n]
    lines += [f"seal check: {scan.status} ({scan.detail})",
              f"clinician_review {review}: draft status in {', '.join(drafts)}",
              "vendor pack: " + (f"{pack['version']} (sent {pack['sent']})" if pack["version"]
                                 else f"none recorded for lane {DISCLOSURE_LANE}")]
    return Export(summary, conversations, lines)


def _load_runs(run_dirs: Sequence[Path], artifact: Mapping[str, Any], seeds: Mapping[str, dict],
               runs_dir: Path) -> dict[str, RunData]:
    """Exactly the runs the artifact covers, each loaded and checked against the artifact's record of it."""
    recorded = {r.get("run_stem"): r for r in artifact["coverage"].get("runs") or [] if isinstance(r, dict)}
    stems = [Path(p).name for p in run_dirs]
    if len(stems) != len(set(stems)):
        raise ExportRefusal(f"a run directory is given twice: {sorted(k for k, n in Counter(stems).items() if n > 1)}")
    if set(stems) != set(recorded):
        raise ExportRefusal(f"the runs given {sorted(stems)} are not the runs the section 10 artifact covers "
                            f"{sorted(recorded)}")
    _verify_command(run_dirs, runs_dir)
    return {Path(p).name: load_run(Path(p), recorded[Path(p).name], seeds) for p in run_dirs}


def _plan_seeds(triples: Sequence[Any], seeds: Mapping[str, dict],
                vocab: Vocabulary) -> tuple[list[str], dict[str, str]]:
    """The seeds the artifact's triples cover, in its (the plan's) order, with their scenario set; every triple
    landed, and every instrument each seed judges mapped to a measure."""
    seed_order: list[str] = []
    set_of: dict[str, str] = {}
    for t in triples:
        if not isinstance(t, dict) or t.get("landed") is not True:
            raise ExportRefusal(f"the artifact lists triple {t.get('triple') if isinstance(t, dict) else t!r} as not "
                                f"landed, which a final, untruncated analysis cannot")
        sid = t.get("seed_id")
        if sid not in seeds:
            raise ExportRefusal(f"triple {t.get('triple')}: seed {sid} is not in the seed file")
        if sid not in seed_order:
            seed_order.append(sid)
        if set_of.setdefault(sid, t.get("scenario_set")) != t.get("scenario_set"):
            raise ExportRefusal(f"seed {sid} is in two scenario sets in the artifact")
    by_row = vocab.by_row()
    if PRIMARY_ROW not in by_row:
        raise ExportRefusal(f"the page vocabulary maps no measure to {PRIMARY_ROW[0]}:{PRIMARY_ROW[1]}, the outcome D "
                            f"is computed on (design note 10.1)")
    for sid in seed_order:
        judge = seeds[sid]["judge"]
        unmapped = ([f"outcome:{d}" for d in judge["outcome_dimensions"] if ("outcome", d) not in by_row]
                    + [f"tier:{k}" for k, on in judge["advice_tier"].items() if on and ("tier", k) not in by_row])
        if unmapped:
            raise ExportRefusal(f"seed {sid} judges {unmapped}, which have no measure in the page vocabulary")
        if sid not in vocab.mechanism_of:
            raise ExportRefusal(f"seed {sid} belongs to no mechanism in the page vocabulary")
    return seed_order, set_of


def _conversations(triples: Sequence[dict], runs: Mapping[str, RunData], seeds: Mapping[str, dict], vocab: Vocabulary,
                   rows_of: Mapping[str, list[dict]], seed_order: Sequence[str], notes: Counter) -> list[dict]:
    """Every conversation the artifact's triples name, in the page's order (seed, epoch, speaker, then colloquial,
    careful lay, clinical); a run tree no triple names is counted, not shown."""
    out: list[tuple[tuple, dict]] = []
    shown: set[str] = set()
    for t in triples:
        sid = t["seed_id"]
        run = runs.get(t.get("run_stem"))
        if run is None:
            raise ExportRefusal(f"triple {t.get('triple')}: run {t.get('run_stem')!r} is not among the runs given")
        speakers, cells = seed_cells(seeds[sid])
        for register in REGISTERS:
            cid = (t.get("conversations") or {}).get(register)
            if cid is None:
                notes[f"conversations the artifact names as missing ({register})"] += 1
                continue
            if cid not in run.trees:
                raise ExportRefusal(f"triple {t['triple']}: conversation {cid[:12]} is not in run {run.stem}")
            tree, branch = run.trees[cid]
            arm = cells.get((t.get("speaker"), register))
            if (tree["seed_id"] != sid or arm is None or tree["arm"] != arm["id"] or len(tree["branches"]) != 1
                    or branch.get("branch_id") != ROOT_BRANCH):
                raise ExportRefusal(f"triple {t['triple']}: conversation {cid[:12]} is not the one root trajectory of "
                                    f"the seed's {register} arm for speaker {t.get('speaker')}")
            if cid not in run.rules:
                raise ExportRefusal(f"run {run.stem} conversation {cid[:12]}: no rule outcome")
            exchanges = build_conversation(run, cid, seeds[sid], arm, vocab, rows_of.get(cid, []), notes)
            shown.add(cid)
            rank = (seed_order.index(sid), t["campaign_epoch"], speakers.index(t.get("speaker")),
                    REGISTERS.index(register))
            out.append((rank, {"run": run.stem, "run_epoch": tree["epoch"], "seed_id": sid, "arm": tree["arm"],
                               "register": register, "identity": t.get("speaker"), "conversation_id": cid,
                               "exchanges": exchanges, "rule": run.rules[cid], "epoch": t["campaign_epoch"]}))
    for run in runs.values():
        for cid, (tree, _) in run.trees.items():
            if cid not in shown:
                notes[f"trees in run {run.stem} not shown (in no triple of the artifact; seed {tree['seed_id']})"] += 1
    return [rec for _, rec in sorted(out, key=lambda kv: kv[0])]


def _check_swaps(convs: Sequence[dict], swaps: Mapping[str, dict | None]) -> None:
    """Every declared swap span is in the user text the page shows: the clinical span in the clinical conversation,
    the careful-lay span in the careful-lay one (a transcript that drifted from the seed file is refused)."""
    for c in convs:
        sw = swaps[c["seed_id"]]
        if not sw or c["register"] not in (CLINICAL, CAREFUL_LAY):
            continue
        per = sw.get(f"{c['identity']}_" if c["identity"] else "")
        if per is None:
            raise ExportRefusal(f"swaps of {c['seed_id']}: none declared for speaker {c['identity']}")
        side = 0 if c["register"] == CLINICAL else 1
        for i, ex in enumerate(c["exchanges"]):
            for k, pair in enumerate(per[i]):
                if pair[side] not in ex["user"]:
                    raise ExportRefusal(f"{c['run']} {c['arm']} exchange {i + 1}: declared swap span {k + 1} is not "
                                        f"in the user text")


def _triples(triples: Sequence[dict], seeds: Mapping[str, dict], rows_of: Mapping[str, list[dict]],
             vocab: Vocabulary, rubric_digest: str) -> tuple[list[dict], list[tuple[dict, Fraction]]]:
    """The page's triple records, and the entering triples with their exact D. D(colloquial, clinical) is recomputed
    from the rows over the exchanges the artifact counts as comparable (10.1: mean of rank(colloquial) minus
    rank(clinical), ranks in the rubric's tier order) and must equal the artifact's sum, n and D for an entering
    triple. A triple below its floor keeps that mean, marked not eligible; with no comparable exchange, or a
    conversation missing, its D is null."""
    tiers = vocab.by_row()[PRIMARY_ROW].values
    final: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for cid, rows in rows_of.items():
        for r in rows:
            if (r["kind"], r["key"]) == PRIMARY_ROW and r["final_in_exchange"] is True:
                final[(cid, r["exchange_index"])].append(r)

    def rank(cid: str, ex: int, label: str) -> int:
        cur = [r for r in final.get((cid, ex), []) if r.get("prompt_file_digest") == rubric_digest]
        if len(cur) != 1 or cur[0].get("value") not in tiers or cur[0].get("not_applicable_reason"):
            raise ExportRefusal(f"triple {label}: the artifact counts exchange {ex} as comparable, but conversation "
                                f"{cid[:12]} has no single valued {PRIMARY_ROW[0]}:{PRIMARY_ROW[1]} row under "
                                f"{rubric_digest}")
        return tiers.index(cur[0]["value"])

    out: list[dict] = []
    entering: list[tuple[dict, Fraction]] = []
    for t in triples:
        prim = (t.get("contrasts") or {}).get(PRIMARY_CONTRAST)
        if not isinstance(prim, dict) or not isinstance(prim.get("enters"), bool):
            raise ExportRefusal(f"triple {t.get('triple')}: the artifact records no primary-contrast standing")
        if t.get("partition") not in PARTITION_LABEL:
            raise ExportRefusal(f"triple {t.get('triple')}: partition {t.get('partition')!r} is not one of "
                                f"{sorted(PARTITION_LABEL)}")
        col, clin = ((t.get("conversations") or {}).get(r) for r in (COLLOQUIAL, CLINICAL))
        comparable = prim.get("comparable_exchanges") or []
        d: float | None = None
        if col and clin and comparable:
            total = sum(rank(col, ex, t["triple"]) - rank(clin, ex, t["triple"]) for ex in comparable)
            exact = Fraction(total, len(comparable))
            if prim["enters"]:
                recorded = (prim.get("sum"), prim.get("n"), prim.get("D_exact"), prim.get("D"))
                if recorded != (total, len(comparable), str(exact), float(exact)):
                    raise ExportRefusal(f"triple {t['triple']}: the rows give D = {exact} over {len(comparable)} "
                                        f"exchanges, the artifact {prim.get('D_exact')} over {prim.get('n')}")
                entering.append((t, exact))
            d = float(exact)
        elif prim["enters"]:
            raise ExportRefusal(f"triple {t['triple']}: the artifact enters it with no comparable exchange")
        out.append({"seed_id": t["seed_id"], "scenario_id": seeds[t["seed_id"]]["scenario"]["id"],
                    "epoch": t["campaign_epoch"], "D": d, "partition": PARTITION_LABEL[t["partition"]],
                    "eligible": prim["enters"]})
    return out, entering


def _primary(s102: Mapping[str, Any], entering: Sequence[tuple[dict, Fraction]], seeds: Mapping[str, dict],
             seed_order: Sequence[str]) -> tuple[dict[str, Any], dict[str, float], int | None]:
    """10.2's counts, p-values and gate, checked against the entering triples; the scenario means keyed by scenario
    id; and the primary test's direction as a sign (None when it has none). A p-value of a test that did not run (no
    non-tied triple; no scenario) is null, never the 1 the artifact's arithmetic gives it."""
    pst, gate, wording_row = s102.get("primary_sign_test"), s102.get("scenario_gate"), s102.get("wording")
    if not (isinstance(pst, dict) and isinstance(gate, dict) and isinstance(wording_row, dict)
            and _count(pst.get("non_tied")) and _count(gate.get("scenarios"))):
        raise ExportRefusal("the artifact's section_10_2 lacks the primary sign test, the scenario gate or the wording")
    counts = (len(entering), sum(e < 0 for _, e in entering), sum(e > 0 for _, e in entering),
              sum(e == 0 for _, e in entering))
    recorded = (pst.get("triples"), pst.get("negative"), pst.get("positive"), pst.get("tied"))
    if recorded != counts:
        raise ExportRefusal(f"the primary test counts (triples, negative, positive, tied) {recorded} are not the "
                            f"entering triples' {counts}")
    by_scenario: dict[str, list[Fraction]] = defaultdict(list)
    for t, e in entering:
        by_scenario[t["seed_id"]].append(e)
    means = {s: sum(v, Fraction(0)) / len(v) for s, v in by_scenario.items()}
    if {s: str(m) for s, m in means.items()} != (gate.get("scenario_means_exact") or {}):
        raise ExportRefusal("the scenario gate's means are not the entering triples' means per scenario")
    # the artifact's float mirror must be the floats of those exact means, as a triple's D is checked beside its
    # D_exact: a stale or missing mirror entry means the artifact disagrees with itself (Codex review of 2026-09-24)
    if gate.get("scenario_means") != {s: float(m) for s, m in means.items()}:
        raise ExportRefusal("the scenario gate's scenario_means are not the floats of its scenario_means_exact, so "
                            "the artifact disagrees with itself")
    scenario_of = {s: seeds[s]["scenario"]["id"] for s in seed_order}
    if len(set(scenario_of.values())) != len(scenario_of):
        raise ExportRefusal("two seeds share a scenario id, and the page keys scenario means by scenario id")
    gate_ran = gate["scenarios"] > 0
    primary = {"triples": pst["triples"], "negative": pst["negative"], "positive": pst["positive"],
               "tied": pst["tied"], "p_two_sided": pst.get("p") if pst["non_tied"] > 0 else None,
               "gate_p": gate.get("p") if gate_ran else None,
               "gate_passed": bool(wording_row.get("gate_same_direction")) if gate_ran else None}
    # the page is given the recomputed means, the values checked above, never the artifact's mirror of them
    return (primary, {scenario_of[s]: float(m) for s, m in means.items()},
            {"negative": -1, "positive": 1}.get(pst.get("direction")))


def _repeats(seed_order: Sequence[str], entering: Sequence[tuple[dict, Fraction]],
             direction: int | None) -> list[dict]:
    """Does it repeat: per seed, the campaign epochs with an entering triple, and how many of them have a mean D (the
    two speakers of an identity seed pooled, as the gate pools them) in the primary test's direction."""
    out = []
    for sid in seed_order:
        per_epoch: dict[int, list[Fraction]] = defaultdict(list)
        for t, e in entering:
            if t["seed_id"] == sid:
                per_epoch[t["campaign_epoch"]].append(e)
        same = None if direction is None else sum(
            1 for v in per_epoch.values() if _sign(sum(v, Fraction(0))) == direction)
        out.append({"seed_id": sid, "epochs": len(per_epoch), "same_direction": same})
    return out


def _draft_sources(rubric: Mapping[str, Any], registry: Mapping[str, Any], seed_doc: Mapping[str, Any],
                   seeds: Mapping[str, dict], seed_order: Sequence[str]) -> dict[str, Any]:
    """The status of each source of the draft state: the three files, and the entries of each the page uses."""
    dims = {d["id"]: d for d in registry.get("dimensions") or []}
    used = sorted({d for s in seed_order for d in seeds[s]["judge"]["outcome_dimensions"]})
    return {"advice rubric": rubric.get("status"), "outcome registry": registry.get("status"),
            "seed file": seed_doc.get("status"),
            **{f"outcome dimension {d}": (dims.get(d) or {}).get("status") for d in used},
            **{f"seed {s}": seeds[s].get("status") for s in seed_order}}


def _seed_record(sid: str, seed: Mapping[str, Any], vocab: Vocabulary, scenario_set: str, convs: Sequence[dict],
                 swaps: dict | None) -> dict[str, Any]:
    speakers, cells = seed_cells(seed)
    judge = seed["judge"]
    applies = {m.id for m in vocab.measures
               if (m.source[0] == "tier" and judge["advice_tier"].get(m.source[1]))
               or (m.source[0] == "outcome" and m.source[1] in judge["outcome_dimensions"])}
    proposition = texts_by_key(dict(seed)).get("proposition")
    return {"seed_id": sid, "mechanism": vocab.mechanism_of[sid], "set": scenario_set,
            "topic": seed["scenario"]["topic"], "scenario_id": seed["scenario"]["id"],
            "hypotheses": list(seed["hypotheses"]),
            "roles": [t.get("context_role") for t in seed["protocol"]["arms"][0]["turns"]],
            "arms": [cells[(s, r)]["id"] for s in speakers for r in REGISTERS if (s, r) in cells],
            "measures": [m.id for m in vocab.measures if m.id in applies],
            "epochs": sorted({c["epoch"] for c in convs if c["seed_id"] == sid}),
            "proposition": proposition["text"] if proposition else None,
            "system_prompt": seed["system_prompt"]["policy"], "swaps": swaps}


def _headline(wording_row: Mapping[str, Any], wording: Wording) -> dict[str, str | None]:
    """10.2's row, its text the table's cell verbatim; not_computable, no_prespecified_row and a row not selectable as
    registered are carried by name with no text (never a headline the table does not register)."""
    row = wording_row.get("row_id")
    if not _text(row):
        raise ExportRefusal("the artifact's section_10_2.wording has no row_id")
    if row in UNWORDED_ROWS:
        return {"row_id": row, "text": None}
    selectable = wording_row.get("selectable_as_registered")
    if not isinstance(selectable, bool):
        raise ExportRefusal("the artifact's section_10_2.wording does not say whether its row is selectable")
    if not selectable:
        return {"row_id": f"{NOT_SELECTABLE}:{row}", "text": None}
    base = row.split("/", 1)[0]
    if base not in wording.rows or (base != row and base != "row4"):
        raise ExportRefusal(f"the artifact selects row {row!r}, which the registered wording has no text for")
    return {"row_id": row, "text": wording.rows[base]}


def _style_sentence(s103: Mapping[str, Any], wording: Wording) -> dict[str, str | None]:
    """10.3's statement, its text the note's bullet verbatim; an unworded statement or a refused section by name."""
    if s103.get("status") == "refused":
        return {"row_id": "refused", "text": None}
    st = s103.get("statement")
    sid = st.get("statement_id") if isinstance(st, dict) else None
    if not _text(sid):
        raise ExportRefusal("the artifact's section_10_3 has no statement id")
    if sid in UNWORDED_STATEMENTS:
        return {"row_id": sid, "text": None}
    if sid not in wording.statements:
        raise ExportRefusal(f"the artifact selects statement {sid!r}, which the registered wording has no text for")
    also = st.get(ALSO_LOWERED) is True
    if also and sid != "style_larger":
        raise ExportRefusal(f"the artifact adds {ALSO_LOWERED} to statement {sid!r}, which 10.3 does not allow")
    return {"row_id": sid + (f"+{ALSO_LOWERED}" if also else ""), "text": wording.statements[sid]}


def _example(example: Mapping[str, Any], seeds: Mapping[str, dict], seed_order: Sequence[str]) -> dict[str, Any]:
    sid, turn = example.get("seed_id"), example.get("turn")
    if sid not in seed_order:
        raise ExportRefusal(f"the example seed {sid} is not one of the exported seeds")
    speakers, cells = seed_cells(seeds[sid])
    out: dict[str, Any] = {"seed_id": sid, "turn": turn}
    for register in REGISTERS:
        arm = cells.get((speakers[0], register))
        if arm is None or not 1 <= turn <= len(arm["turns"]):
            raise ExportRefusal(f"the example seed {sid} has no {register} turn {turn}")
        out[register] = text_of(seeds[sid], arm["turns"][turn - 1]["text_ref"])
    return out


# ------------------------------------------------------------------ writing, samples, the diff


def _dumps(obj: Any, *, compact: bool) -> str:
    if compact:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def swap_dir(data: Path, sample: bool) -> Path:
    """Where write_site stages one write of the pair: `new/` (the files to swap in), `old/` (a copy of each file it
    replaces) and `journal.json` (which destinations existed before). The contract validator fails a site that holds
    one (scripts/validate_frontend_contract.py, MT_SWAP_GLOB), since the pair beside it may be mixed."""
    return Path(data) / (".petri_multiturn" + (".sample" if sample else "") + ".swap")


def recover_interrupted_write(data: Path, sample: bool = False) -> bool:
    """Put back the pair a write_site that stopped between its replacements left (a crash, a kill): with the journal
    present, each destination is restored from its copy in `old/`, or removed when it did not exist before that write
    (a destination whose copy is gone was restored by an earlier recovery that was itself interrupted); without the
    journal no destination had been touched. The swap directory is then removed. True when there was one."""
    swap = swap_dir(data, sample)
    if not swap.exists():
        return False
    journal = swap / "journal.json"
    if journal.is_file():
        try:
            existed = json.loads(journal.read_text(encoding="utf-8"))["existed"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExportRefusal(f"{journal} does not parse ({exc}); the pair in {data} may be mixed: restore it from "
                                f"git and remove {swap}") from exc
        for name, had in existed.items():
            dest, old = Path(data) / name, swap / "old" / name
            if had and old.is_file():
                os.replace(old, dest)
            elif not had:
                dest.unlink(missing_ok=True)
    shutil.rmtree(swap)
    return True


def write_site(site: Path, summary: Mapping[str, Any], conversations: Mapping[str, Any], *,
               sample: bool = False) -> list[Path]:
    """Write both files into `<site>/data/` (the `.sample.json` names when `sample`), fully or not at all: the page
    reads the two as one unit, and neither file carries an identifier the other could be matched by. Both new files
    are staged in the swap directory with a copy of each file they replace and a journal, and only then renamed into
    place. Any exception between the two renames (an error, a keyboard interrupt) puts the previous pair back before
    it propagates; a process killed there leaves the swap directory, which the next write (and
    recover_interrupted_write) rolls back first and the contract validator fails the site over until then (Codex
    review of 2026-09-24: two bare renames could leave one new file beside one old one)."""
    data = Path(site) / "data"
    if not data.is_dir():
        raise ExportRefusal(f"{data} is not a directory")
    recover_interrupted_write(data, sample)
    suffix = ".sample.json" if sample else ".json"
    out = [data / (SUMMARY_NAME + suffix), data / (CONVERSATIONS_NAME + suffix)]
    texts = [_dumps(summary, compact=False), _dumps(conversations, compact=not sample)]
    swap = swap_dir(data, sample)
    try:
        (swap / "new").mkdir(parents=True)
        (swap / "old").mkdir()
        existed = {p.name: p.is_file() for p in out}
        for path, text in zip(out, texts):
            (swap / "new" / path.name).write_text(text, encoding="utf-8")
            if existed[path.name]:
                shutil.copy2(path, swap / "old" / path.name)
        # the journal appears whole or not at all, and only once every copy it vouches for is complete
        (swap / "journal.json.tmp").write_text(json.dumps({"existed": existed}), encoding="utf-8")
        os.replace(swap / "journal.json.tmp", swap / "journal.json")
        for path in out:
            os.replace(swap / "new" / path.name, path)
    except BaseException:
        recover_interrupted_write(data, sample)
        raise
    shutil.rmtree(swap)
    return out


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "..."


def diff_cells(old: Any, new: Any, path: str = "$") -> list[str]:
    """Every leaf that differs between two JSON documents, by path: '~ path: old -> new', '+ path: new' (added) or
    '- path: old' (removed)."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = [f"- {path}.{k}: {_short(old[k])}" for k in old if k not in new]
        for k in new:
            out += ([f"+ {path}.{k}: {_short(new[k])}"] if k not in old else diff_cells(old[k], new[k], f"{path}.{k}"))
        return out
    if isinstance(old, list) and isinstance(new, list):
        out = []
        for i in range(max(len(old), len(new))):
            if i >= len(old):
                out.append(f"+ {path}[{i}]: {_short(new[i])}")
            elif i >= len(new):
                out.append(f"- {path}[{i}]: {_short(old[i])}")
            else:
                out += diff_cells(old[i], new[i], f"{path}[{i}]")
        return out
    same = old == new and isinstance(old, bool) == isinstance(new, bool) and (old is None) == (new is None)
    return [] if same else [f"~ {path}: {_short(old)} -> {_short(new)}"]


def samplify(result: Export, rng_seed: int, epoch: int = 1) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two SYNTHETIC sample fixtures from an export of synthetic input: every free text replaced by a placeholder,
    the registered wording by the site's placeholder rows, the provenance by sample ids, status not final, and the
    conversations cut to one epoch."""
    s = json.loads(json.dumps(result.summary))
    c = json.loads(json.dumps(result.conversations))
    run_ids = {r: f"run_SAMPLE_{i}" for i, r in enumerate(s["provenance"]["runs"], 1)}
    s["status"] = {"final": False, "clinician_review": REVIEW_PENDING, "vendor_pack": {"version": None, "sent": None}}
    s["headline"] = {"row_id": "SAMPLE", "text": "[Sample headline: the section 10.2 wording-table row goes here "
                                                 "verbatim.]"}
    s["style_sentence"] = {"row_id": "SAMPLE", "text": "[Sample sentence: the section 10.3 row goes here verbatim.]"}
    s["provenance"] = {"runs": list(run_ids.values()), "analysis_commit": "SAMPLE", "verify": s["provenance"]["verify"]}
    convs = [x for x in c["conversations"] if x["epoch"] == epoch]
    for n, x in enumerate(convs, 1):
        x["conversation_id"] = f"sample-{n:03d}"
        x["run"] = run_ids.get(x["run"], "run_SAMPLE")
        for i, ex in enumerate(x["exchanges"], 1):
            ex["user"] = f"[Sample {x['register']} user turn {i}: placeholder text, not a real message.]"
            ex["reply"] = f"[Sample assistant reply {i}: placeholder text, not a real message.]"
            for it in ex["interim"]:
                it["text"] = (f"[Sample scripted lookup result {i}: placeholder text written for the sample, not a "
                              f"real result.]" if it["role"] == "tool" else
                              f"[Sample intermediate reply {i}: placeholder text, not a real message.]")
            for cell in ex["vals"].values():
                if "na" in cell:
                    cell["na"] = "sample: not applicable"
        rule = x["rule"]
        # the lane's shape kept: a list of every call's arguments, or null (scripts/petri_audit/rules.py)
        queries = rule.get("query_text")
        if queries is not None:
            if not isinstance(queries, list):
                raise ExportRefusal(f"the synthetic rule outcome's query_text is a {type(queries).__name__}, not the "
                                    f"list the lane writes")
            rule["query_text"] = [f"[Sample query text {k}: placeholder.]" for k in range(1, len(queries) + 1)]
        if rule.get("first_tool"):
            rule["first_tool"] = "sample_lookup"
    c["conversations"] = convs
    for n, seed in enumerate(c["seeds"], 1):
        seed["topic"] = f"Sample scenario {n}"
        seed["epochs"] = sorted({x["epoch"] for x in convs if x["seed_id"] == seed["seed_id"]})
        if seed["proposition"] is not None:
            seed["proposition"] = "[Sample proposition: placeholder text.]"
    for k, register in enumerate(REGISTERS, 1):
        c["example"][register] = f"[Sample wording {k}: placeholder text, not a real message.]"
    head = {"sample": True, "_note": SAMPLE_NOTES[SUMMARY_NAME], "seed": rng_seed}
    summary = {**head, **{k: v for k, v in s.items() if k != "seed"}}
    head = {"sample": True, "_note": SAMPLE_NOTES[CONVERSATIONS_NAME], "seed": rng_seed}
    conversations = {**head, **{k: v for k, v in c.items() if k != "seed"}}
    return summary, conversations


def sample_export(*, vocabulary_path: Path = VOCABULARY_FILE, seeds_path: Path = SEED_FILE,
                  rubric_path: Path = ADVICE_RUBRIC, registry_path: Path = OUTCOME_REGISTRY,
                  seal_registry: Mapping[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two sample fixtures, exported from a SYNTHETIC campaign (scripts/petri_multiturn_synthetic.py) built in a
    temporary directory from the vocabulary file's sample settings, with one triple of the last epoch left below its
    floor so the page's not-eligible mark has a case; the generator seed is recorded in both files."""
    from scripts import petri_multiturn_synthetic as synthetic
    rubric = _load(rubric_path, "the advice rubric")
    registry = _load(registry_path, "the outcome registry")
    vocab = load_vocabulary(vocabulary_path, rubric, registry)
    seeds = {s["seed_id"]: s for s in _load(seeds_path, "the seed file")["seeds"]}
    cfg = vocab.samples
    with tempfile.TemporaryDirectory() as tmp:
        campaign = synthetic.build_campaign(
            Path(tmp), seeds=seeds, sets={"original": list(cfg["seed_ids"])},
            fires=synthetic.epoch_fires(cfg["epochs"], "original"), rubric=rubric, registry=registry,
            rng_seed=cfg["rng_seed"], judgment_edit=synthetic.below_floor(cfg["epochs"]))
        artifact = Path(tmp) / "artifact.json"
        artifact.write_text(json.dumps(synthetic.build_artifact(campaign)), encoding="utf-8")
        result = export(campaign.run_dirs, artifact, seeds_path=seeds_path, rubric_path=rubric_path,
                        registry_path=registry_path, vocabulary_path=vocabulary_path,
                        disclosure_log=Path(tmp) / "no_disclosure_log.jsonl", seal_registry=seal_registry,
                        example={"seed_id": cfg["seed_ids"][0], "turn": vocab.example["turn"]},
                        checkout=synthetic_checkout(Path(tmp)))
    return samplify(result, cfg["rng_seed"])


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


# ------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=Path, help="the landed wave-2 run directories the artifact covers")
    ap.add_argument("--analysis", type=Path, help="the section 10 artifact (petri_w2_register_contrast.py --final)")
    ap.add_argument("--site", type=Path, default=DEFAULT_SITE, help="the site checkout (files go to <site>/data/)")
    ap.add_argument("--previous", type=Path, help="an earlier summary file: print every cell that changed")
    ap.add_argument("--dry-run", action="store_true", help="check and report; write nothing")
    ap.add_argument("--write-samples", action="store_true",
                    help="write the two SYNTHETIC .sample.json fixtures instead (no runs, no artifact)")
    ap.add_argument("--seeds", type=Path, default=SEED_FILE)
    ap.add_argument("--rubric", type=Path, default=ADVICE_RUBRIC)
    ap.add_argument("--outcomes", type=Path, default=OUTCOME_REGISTRY)
    ap.add_argument("--vocabulary", type=Path, default=VOCABULARY_FILE)
    ap.add_argument("--wording", type=Path, default=WORDING_FILE)
    ap.add_argument("--design-note", type=Path, default=DESIGN_NOTE)
    ap.add_argument("--swaps", type=Path, default=SWAPS_FILE)
    ap.add_argument("--disclosure-log", type=Path, default=DISCLOSURE_LOG)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.write_samples:
            if args.runs or args.analysis:
                raise ExportRefusal("--write-samples builds from synthetic input; it takes no runs and no --analysis")
            summary, conversations = sample_export(vocabulary_path=args.vocabulary, seeds_path=args.seeds,
                                                   rubric_path=args.rubric, registry_path=args.outcomes)
            notes: list[str] = ["SYNTHETIC sample fixtures (placeholder text, random grades)"]
            sample = True
        else:
            if args.analysis is None or not args.runs:
                raise ExportRefusal("give --analysis and the run directories it covers")
            result = export(args.runs, args.analysis, seeds_path=args.seeds, rubric_path=args.rubric,
                            registry_path=args.outcomes, vocabulary_path=args.vocabulary, wording_path=args.wording,
                            design_note=args.design_note, swaps_path=args.swaps, disclosure_log=args.disclosure_log)
            summary, conversations, notes, sample = result.summary, result.conversations, result.notes, False
        if args.previous is not None:
            old = _load(args.previous, "--previous")
            changed = diff_cells(old, summary)
            print(f"--previous {args.previous}: {len(changed)} changed cell(s)")
            for line in changed:
                print(f"  {line}")
        written = [] if args.dry_run else write_site(args.site, summary, conversations, sample=sample)
    except ExportRefusal as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"headline row: {summary['headline']['row_id']}; style row: {summary['style_sentence']['row_id']}")
    print(f"{len(summary['triples'])} triples ({summary['primary']['triples']} entering the primary test), "
          f"{len(conversations['conversations'])} conversations, {len(conversations['seeds'])} seeds")
    print(f"analysis commit {summary['provenance']['analysis_commit']}; exporter commit {_git_head()}")
    for line in notes:
        print(f"  {line}")
    print("dry run: nothing written" if args.dry_run else "wrote " + ", ".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
