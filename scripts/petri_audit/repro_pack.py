"""Vendor reproduction packs for the Petri lane (the pre-registration's binding rule,
docs/preregistration_advice.md "Vendor reproduction packs and sequencing"; its scope ruling of 2026-09-23 and
decision 16 of docs/petri_wave2_design.md bind the planned Multi-turn page, which names the target model).

The advice lane's builder is `scripts/advice_eval.py repro-pack`; this is the Petri lane's, with the same three modes,
the same disclosure log and the same exit codes. It reuses that module's log, supersession and send helpers rather
than restating them, and attributes a model to a vendor by the rule of its `_vendor_match`.

    python -m scripts.petri_audit.cli repro-pack --vendor VENDOR --publication-state STATE \\
        --run-dir data/petri/runs/RUN [--run-dir ...] [--analysis FILE] [--out dist] [--log FILE] \\
        [--public-since DATE --deviation-link URL [--public-until DATE --withheld-reason TEXT]]
    python -m scripts.petri_audit.cli repro-pack --check [--log FILE]
    python -m scripts.petri_audit.cli repro-pack --record-sent PACK_VERSION --sent-to "ROLE OR CHANNEL" [--log FILE]

What a pack holds, from the public repository alone (the bundle `dist/petri_repro_<vendor>_<version>/`; `dist/` is
gitignored, so a pack is never committed, as in the advice lane):

- `runs/<run>/`: every landed file of each listed run, byte for byte: the manifest, the sanitised log, the transcripts,
  the judgments, the rule outcomes, the cost sidecars (the target's, the judge's, and a re-adapted run's judge sidecar
  named for its readapt) and the committed analysis rows. Each copy passes `verify-run` on its own.
- `analysis/`: the section 10 analysis artifact (`data/petri/w2_register_contrast.json`, written by
  `scripts/petri_w2_register_contrast.py --final`) and the plan it read.
- `CLAIMS.json`: the claims and caveats. From the artifact: the selected 10.2 wording row and whether it is selectable
  as registered, the 10.3 statement, the as-first-written block's row (labelled secondary) and any administrative
  truncation; their texts, and the plan's limitations, from `data/petri/w2_repro_pack_claims.json`, which the suite
  holds verbatim to the design note.
- `prompts/<repository path>`: the rubric and every judge prompt file the judgments name; `seeds.json`: the seeds the
  runs used with each seed's digest; `environment/`: the environment lock when its digest is the one every run
  recorded.
- `README.md` and `DISCLOSURE_NOTE.md`, rendered from the data templates `docs/petri_repro_pack_readme_template.md` and
  `docs/petri_repro_pack_disclosure_note_template.md` (the note in the version `--publication-state` names); request
  ids are counted from the records, never promised. What a public state's note states beyond the records (since when a
  page has shown the results, until when and why it withheld them, the link to the recorded deviation) is a build
  input (`--public-since`, `--public-until`, `--withheld-reason`, `--deviation-link`, publication_record), recorded in
  the manifest, so the version and SHA256SUMS cover the note as sent; a note that still holds a bracketed field is
  refused.
- `MANIFEST.json` (the pack's state and identity) and `SHA256SUMS` (every other file's sha256).

The build refuses, by name and before anything is written: an analysis artifact that is absent, is not a `--final`
output, was computed on other bytes of a run than the ones listed, or whose truncation record
(`administratively_truncated`, `truncation_reason`, `fires_not_landed`) is absent, contradicts itself, or names other
fires not landed than the plan's fires without a listed run; a run list that differs from the runs the analysis read, or
omits a landed run of the plan's fires; a run that fails `verify-run`, is missing from the chain, holds an unknown file,
or lacks a cost sidecar; a chain that does not verify; any record naming a model of another vendor (runs are never
filtered: their files are bound by digest); a seed whose current digest differs from the one a run recorded; a missing
prompt file; a judgment that records no prompt digest (the pack could not name the prompt it was judged under); a claim
id the wording file does not carry; an analysis artifact and a plan that share a basename (both are carried under
`analysis/`); a pack that fails the holdout seal (labels only, never a phrase); and a pack directory of the same version
that holds other bytes.

Identity. A pack is keyed by (vendor, analysis artifact stem), like the advice lane's (vendor, archive). Its version is
`petri-v` + the first 12 hex of the sha256 of its manifest's canonical JSON (MANIFEST.json without `pack_version`),
which covers every input the bundle's bytes depend on (the state below, the run facts, the claims, the templates'
sha256, the publication state with its dates and link, and the engine commit), so a rebuild from the same inputs is
byte-identical and logs nothing, and any change is a new version. The log entry keeps the part of the manifest --check
reads, the publication state with its inputs, and the claim ids (LOG_MANIFEST_KEYS); the bundle's MANIFEST.json holds
the whole. The build appends one entry per new version to the disclosure log (`ops/disclosure_log.jsonl`, public and
append-only, no contact details) with `"lane": "petri"`; the advice lane's --check counts entries of another lane and
skips them. `supersedes` names the newest earlier build for the same key. A sent pack is never rebuilt in place and no
entry is ever rewritten.

STALE. `--check` recomputes, for the newest pack of every (vendor, analysis), the state it was built from, and the
pack is STALE when any of these moved:
1. a listed run's files: any byte of any file in its directory, a file added or removed, the directory gone;
2. the campaign: a landed run (a line of the chain) whose fire (`spend.journal_nonce`) is one of the plan's fires and
   that the pack does not list, i.e. a new landed run the pack's claims do not cover;
3. the chain where it touches the listed runs: a listed run's line (position or digest), the lines up to the last
   listed run (their sha256), or those lines failing verification. Lines appended after them move the chain head but
   leave the pack FRESH: a later run is not this pack's evidence;
4. the analysis artifact, the plan, or the claims wording file (sha256);
5. the digest (and sha256) of the rubric or of any judge prompt file the listed runs' judgments name, or the digest of
   any seed the listed runs used.
Nothing else stales a pack: not another seed in the seed file, not the environment lock (every run manifest binds the
lock digest it ran under), not the templates or the engine commit (those change a rebuild's text, and so its version,
not the evidence a sent pack carries).

`--check` exits 2 when the newest pack of a key was sent and is STALE, or an earlier pack of that key was sent and a
newer build is unsent (the vendor holds an outdated pack); 3 when a petri-lane log entry cannot be read and nothing
escalates; otherwise 0, with STALE-but-unsent reported, and "never-built" when the log holds no petri-lane pack. The
frontend contract gate (scripts/validate_frontend_contract.py `repro_pack_gate`) fails on any non-zero exit of this
check, as it does for the advice lane's. `--record-sent` appends a copy of the build entry stamped with the time it is
run, so record a send on the day it is made.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import seal
from .envlock import load_lock, lock_digest
from .framework import (
    ENV_LOCK,
    ROOT,
    SEED_FILE,
    canonical_json,
    load_json,
    prompt_canonical,
    sha256_file,
    sha256_text,
)
from .judge_runner import _advice_eval_module, rubric_digest
from .manifest import ARTIFACT_FILENAMES, CHAIN_FILE, JUDGE_REPORT_SUFFIX, verify_chain, verify_run
from .seeds import seed_digest
from .spend import PROVIDERS_PATH, registry_spec_to_inspect, split_inspect_name

LANE = "petri"
VERSION_PREFIX = "petri-v"
PACK_FORMAT = "petri-repro-pack/0.1"
DEFAULT_RUNS_DIR = ROOT / "data" / "petri" / "runs"
DEFAULT_ANALYSIS = ROOT / "data" / "petri" / "w2_register_contrast.json"
DEFAULT_PLAN = ROOT / "data" / "petri" / "w2_register_contrast_plan.json"
DEFAULT_CLAIMS = ROOT / "data" / "petri" / "w2_repro_pack_claims.json"
README_TEMPLATE = ROOT / "docs" / "petri_repro_pack_readme_template.md"
NOTE_TEMPLATE = ROOT / "docs" / "petri_repro_pack_disclosure_note_template.md"
DEFAULT_LOG = ROOT / "ops" / "disclosure_log.jsonl"
DEFAULT_OUT = ROOT / "dist"
ANALYSIS_SCRIPT = "scripts/petri_w2_register_contrast.py"
ANALYSIS_SEED = 20260923                      # design note 10.2; the only seed the analysis's --final accepts
PUBLICATION_STATES = ("not_yet_public", "already_public", "formerly_public")
# what the note of each publication state states beyond the pack's own records: build inputs, recorded in the manifest,
# so the pack's version and SHA256SUMS cover the note as it is sent (publication_record)
PUBLICATION_FIELDS = {"public_since": "--public-since", "public_until": "--public-until",
                      "withheld_reason": "--withheld-reason", "deviation_link": "--deviation-link"}
PUBLICATION_REQUIRES = {"not_yet_public": (),
                        "already_public": ("public_since", "deviation_link"),
                        "formerly_public": ("public_since", "public_until", "withheld_reason", "deviation_link")}
REFUSED_EXIT = 13                             # the petri CLI's codes 3-12 are taken
# every file a landed run directory holds besides its cost sidecars (manifest.ARTIFACT_FILENAMES are the four bound
# families); a committed analysis_rows.jsonl is not bound by the manifest, and the analysis reads it only for its
# as-first-written block
RUN_FILES = ("manifest.json", *ARTIFACT_FILENAMES.values(), "analysis_rows.jsonl")
MAX_MOVED_SHOWN = 8
# the digest a judgment records for its prompt file (judge_runner.plan_record; prompt_file_digest below)
PROMPT_DIGEST = re.compile(r"[0-9a-f]{12}")
# what a log entry's manifest keeps: everything --check reads, the pack's identity and the claim ids. The bundle's
# MANIFEST.json holds the whole manifest, whose canonical sha256 the version is cut from.
LOG_MANIFEST_KEYS = ("pack_format", "lane", "vendor", "scope", "publication_state", "publication", "inputs",
                     "depends_on", "state",
                     "chain_head_at_build", "engine_commit", "state_utc", "pack_version")


class PackRefusal(Exception):
    """A pack that cannot be built or a send that cannot be recorded, with every reason by name."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


def _advice() -> Any:
    """scripts/advice_eval.py, whose disclosure-log helpers this module reuses."""
    return _advice_eval_module()


# ------------------------------------------------------------------ paths


def _rel(path: Path | str) -> str:
    """A path as the log records it: relative to the repository root when inside it (so the public log names no local
    directory), absolute otherwise."""
    p = Path(path).resolve()
    try:
        rel = p.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)
    return rel or "."


def _abs(recorded: str) -> Path:
    p = Path(recorded)
    return p if p.is_absolute() else ROOT / p


def _sha(path: Path) -> str | None:
    """sha256 of a file, None when it is absent, and the reason when it cannot be read: a value that differs from any
    digest, so an unreadable input reads as moved, never as unchanged."""
    try:
        return sha256_file(path) if Path(path).is_file() else None
    except OSError as exc:
        return f"unreadable: {type(exc).__name__}: {exc}"


def _read_jsonl(path: Path) -> list[Any]:
    """Rows of a JSONL file; a line that does not parse raises ValueError naming the file and line."""
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"{Path(path).name} line {n} does not parse ({exc})") from exc
    return rows


@dataclass(frozen=True)
class PackInputs:
    """Where a pack's inputs live. Recorded in the log entry (`record`), so --check recomputes the same state."""

    vendor: str
    run_dirs: tuple[Path, ...]
    runs_dir: Path = DEFAULT_RUNS_DIR
    analysis: Path = DEFAULT_ANALYSIS
    plan: Path = DEFAULT_PLAN
    claims: Path = DEFAULT_CLAIMS
    seeds: Path = SEED_FILE
    lock: Path = ENV_LOCK
    repo_root: Path = ROOT            # where the prompt refs the judgments record resolve

    def record(self) -> dict[str, Any]:
        return {"vendor": self.vendor, "run_dirs": [_rel(d) for d in self.run_dirs], "runs_dir": _rel(self.runs_dir),
                "analysis": _rel(self.analysis), "plan": _rel(self.plan), "claims": _rel(self.claims),
                "seeds": _rel(self.seeds), "lock": _rel(self.lock), "repo_root": _rel(self.repo_root)}

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> PackInputs:
        return cls(vendor=rec["vendor"], run_dirs=tuple(_abs(d) for d in rec["run_dirs"]),
                   runs_dir=_abs(rec["runs_dir"]), analysis=_abs(rec["analysis"]), plan=_abs(rec["plan"]),
                   claims=_abs(rec["claims"]), seeds=_abs(rec["seeds"]), lock=_abs(rec["lock"]),
                   repo_root=_abs(rec["repo_root"]))


INPUT_KEYS = ("vendor", "run_dirs", "runs_dir", "analysis", "plan", "claims", "seeds", "lock", "repo_root")


# ------------------------------------------------------------------ vendor attribution


def spec_matches_vendor(spec: str, vendor: str, providers: Mapping[str, Any] | None = None) -> bool:
    """Whether a model spec is the vendor's. Registry form (`provider:model`, a bare registry provider, or a bare model
    id, which the registry reads as an Anthropic id) is expanded to Inspect form first (`spend.registry_spec_to_inspect`,
    the resolver's rule); then, as the advice lane's `_vendor_match` decides, the spec is the vendor's when its provider
    is the vendor or its model slug is (`openrouter/google/...` is google's)."""
    s = str(spec).strip()
    if ":" in s or "/" not in s:
        try:
            s = registry_spec_to_inspect(s, dict(providers) if providers is not None else None)
        except ValueError:
            return False
    provider, model = split_inspect_name(s)
    return provider == vendor or model.startswith(vendor + "/")


def _model_fields(run_dir: Path, manifest: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Every (file, field, spec) in a run that names a model: the manifest's roles, usage, judge of record and the
    eval's model roles; each transcript's source model; each judgment's and committed analysis row's judge; each cost
    sidecar's models; each model event of the sanitised log. Placeholder values that name no model (null, empty) are
    skipped. Raises ValueError for a file that does not parse."""
    out: list[tuple[str, str, str]] = []

    def add(file: str, field: str, value: Any) -> None:
        if isinstance(value, str) and value.strip():
            out.append((file, field, value))

    models = manifest.get("models") or {}
    for role, block in models.items():
        if isinstance(block, dict):
            add("manifest.json", f"models.{role}.inspect_name", block.get("inspect_name"))
            add("manifest.json", f"models.{role}.registry_spec", block.get("registry_spec"))
        else:
            add("manifest.json", f"models.{role}", block)
    usage = manifest.get("usage") or {}
    for part in ("by_model", "by_role"):
        for row in usage.get(part) or []:
            if isinstance(row, dict):
                add("manifest.json", f"usage.{part}.model", row.get("model"))
    judge = (manifest.get("artifacts") or {}).get("judge_of_record") or {}
    add("manifest.json", "artifacts.judge_of_record.judge_model", judge.get("judge_model"))
    roles = (manifest.get("eval_spec_dump") or {}).get("model_roles") or {}
    for role, block in roles.items():
        if isinstance(block, dict):
            add("manifest.json", f"eval_spec_dump.model_roles.{role}.model", block.get("model"))
    for name, field in (("transcripts.jsonl", "source.model"), ("judgments.jsonl", "judge_model"),
                        ("analysis_rows.jsonl", "judge_model")):
        path = run_dir / name
        if not path.is_file():
            continue
        for row in _read_jsonl(path):
            if not isinstance(row, dict):
                continue
            value = (row.get("source") or {}).get("model") if field == "source.model" else row.get(field)
            add(name, field, value)
    for path in sorted(run_dir.glob("*.report.json")):
        doc = load_json(path)
        if isinstance(doc, dict):
            for row in doc.get("models") or []:
                if isinstance(row, dict):
                    add(path.name, "models.model", row.get("model"))
            add(path.name, "judge_model", doc.get("judge_model"))
            add(path.name, "target", doc.get("target"))
    log_path = run_dir / ARTIFACT_FILENAMES["sanitised_log"]
    if log_path.is_file():
        doc = load_json(log_path)
        roles = ((doc.get("eval") or {}).get("model_roles") or {}) if isinstance(doc, dict) else {}
        for role, block in roles.items():
            if isinstance(block, dict):
                add(log_path.name, f"eval.model_roles.{role}.model", block.get("model"))
        for event in _model_events(doc):
            add(log_path.name, "samples.events.model", event.get("model"))
    return out


def _model_events(sanitised_log: Any) -> list[dict]:
    if not isinstance(sanitised_log, dict):
        return []
    return [e for s in sanitised_log.get("samples") or [] if isinstance(s, dict)
            for e in s.get("events") or [] if isinstance(e, dict) and e.get("event") == "model"]


def foreign_model_problems(run_dir: Path, manifest: Mapping[str, Any], vendor: str,
                           providers: Mapping[str, Any] | None = None) -> list[str]:
    """One problem per (file, field, spec) naming a model that is not the vendor's, with its count. A pack carries the
    runs whole, because their files are bound by digest, so a run that involves another vendor's model is refused
    rather than filtered."""
    try:
        fields = _model_fields(run_dir, manifest)
    except (OSError, ValueError) as exc:
        return [f"{run_dir.name}: the records cannot be read for their models ({exc})"]
    foreign = Counter((f, field, spec) for f, field, spec in fields if not spec_matches_vendor(spec, vendor, providers))
    return [f"{run_dir.name}/{f} {field} names {spec!r}, not a {vendor} model ({n} record(s)); a pack carries only "
            f"the vendor's model" for (f, field, spec), n in sorted(foreign.items())]


# ------------------------------------------------------------------ the run directory


def classify_run_files(run_dir: Path, manifest: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """(files to pack, problems, hidden names ignored). A landed run directory holds RUN_FILES, its target cost sidecar
    `<run>.report.json` and one or more judge sidecars (`<run>.judge.report.json`, `<run>.readapt_<id>.judge.report.json`).
    Anything else is refused by name, as is a missing required file; hidden files (a Finder `.DS_Store`) are ignored and
    named by the caller."""
    stem = run_dir.name
    problems: list[str] = []
    files: list[str] = []
    hidden: list[str] = []
    for p in sorted(run_dir.iterdir()):
        if p.name.startswith("."):
            hidden.append(p.name)
        elif p.is_dir():
            problems.append(f"{stem}: holds a directory {p.name}/, which no landed run has; the pack does not know it")
        elif p.name in RUN_FILES or p.name == f"{stem}.report.json" or (
                p.name.startswith(stem + ".") and p.name.endswith(JUDGE_REPORT_SUFFIX)):
            files.append(p.name)
        else:
            problems.append(f"{stem}: holds {p.name}, which is not a file of a landed run; the pack does not know it")
    required = ["manifest.json", *ARTIFACT_FILENAMES.values(), f"{stem}.report.json"]
    judge = (manifest.get("artifacts") or {}).get("judge_of_record") or {}
    if not isinstance(judge, dict) or not judge.get("report_path"):
        problems.append(f"{stem}: the manifest binds no judge of record, so the run has no judgments to pack")
    else:
        required.append(Path(judge["report_path"]).name)
    for name in required:
        if name not in files:
            what = " (the target's cost sidecar)" if name == f"{stem}.report.json" else ""
            problems.append(f"{stem}: {name} is missing{what}")
    return files, problems, hidden


def run_file_state(run_dir: Path) -> dict[str, Any]:
    """The freshness basis of one listed run: the sha256 of every (non-hidden) file in its directory, and its
    subdirectories by name; `missing` when the directory is gone."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        return {"missing": True}
    return {"files": {p.name: _sha(p) for p in sorted(run_dir.iterdir()) if p.is_file() and not p.name.startswith(".")},
            "subdirectories": sorted(p.name for p in run_dir.iterdir() if p.is_dir() and not p.name.startswith("."))}


# ------------------------------------------------------------------ chain and campaign


def chain_lines(runs_dir: Path) -> list[tuple[str, str]]:
    """(manifest path relative to the runs directory, digest) per chain line; empty without a chain."""
    path = Path(runs_dir) / CHAIN_FILE
    if not path.is_file():
        return []
    out: list[tuple[str, str]] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rel, digest = ln.strip().rsplit(" ", 1)
            out.append((rel, digest))
    return out


def chain_state(runs_dir: Path, stems: Sequence[str]) -> dict[str, Any]:
    """The part of the chain the listed runs depend on: each run's line (1-based position and digest, null when it is
    not in the chain), the sha256 of the lines up to the last listed run, and whether those lines verify
    (`manifest.verify_chain` over them alone). Lines appended after them are outside it."""
    try:
        lines = chain_lines(runs_dir)
    except (OSError, ValueError) as exc:
        return {"lines": {s: None for s in stems}, "prefix_lines": None, "prefix_sha256": None, "intact": False,
                "problem": f"the chain cannot be read ({exc})"}
    where = {}
    for n, (rel, digest) in enumerate(lines, 1):
        where[Path(rel).parent.as_posix()] = [n, digest]
    positions = {s: where.get(s) for s in stems}
    found = [p[0] for p in positions.values() if p]
    last = max(found) if found and len(found) == len(stems) else None
    if last is None:
        return {"lines": positions, "prefix_lines": None, "prefix_sha256": None, "intact": False,
                "problem": "a listed run is not in the chain"}
    try:
        ok, msg = verify_chain(Path(runs_dir), lines=last)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        ok, msg = False, f"verification failed to run ({type(exc).__name__}: {exc})"
    prefix = "".join(f"{rel} {digest}\n" for rel, digest in lines[:last])
    return {"lines": positions, "prefix_lines": last, "prefix_sha256": sha256_text(prefix), "intact": ok,
            "problem": None if ok else msg}


def plan_fires(plan_path: Path) -> dict[str, dict[str, Any]]:
    """The plan's fires by journal nonce. Raises ValueError for a plan that does not name them."""
    plan = load_json(plan_path)
    fires = plan.get("fires") if isinstance(plan, dict) else None
    if not isinstance(fires, list) or not all(isinstance(f, dict) and isinstance(f.get("journal_nonce"), str)
                                              for f in fires):
        raise ValueError(f"{Path(plan_path).name} names no fires by journal_nonce")
    return {f["journal_nonce"]: f for f in fires}


def run_nonce(manifest: Mapping[str, Any]) -> str | None:
    nonce = (manifest.get("spend") or {}).get("journal_nonce")
    return nonce if isinstance(nonce, str) and nonce else None


def campaign_runs(runs_dir: Path, plan_path: Path) -> list[str]:
    """The landed runs of the plan's fires: every run in the chain whose manifest records one of the plan's journal
    nonces (a re-adapted run keeps its source fire's). An input that cannot be read is named in the list, so it can
    never read as an unchanged campaign."""
    try:
        fires = plan_fires(plan_path)
    except (OSError, ValueError) as exc:
        return [f"unreadable plan: {type(exc).__name__}: {exc}"]
    try:
        lines = chain_lines(runs_dir)
    except (OSError, ValueError) as exc:
        return [f"unreadable chain: {type(exc).__name__}: {exc}"]
    out = []
    for rel, _digest in lines:
        stem = Path(rel).parent.as_posix()
        try:
            manifest = load_json(Path(runs_dir) / rel)
        except (OSError, ValueError) as exc:
            out.append(f"{stem} (manifest unreadable: {type(exc).__name__})")
            continue
        if isinstance(manifest, dict) and run_nonce(manifest) in fires:
            out.append(stem)
    return sorted(set(out))


# ------------------------------------------------------------------ prompts and seeds


def prompt_file_digest(path: Path, kind: str) -> str:
    """The 12-hex digest a judgment records for its prompt file (judge_runner.plan_record): the rubric's
    `rubric_digest` for a tier row, the order-preserving canonical digest for an outcome prompt."""
    doc = load_json(path)
    if kind == "rubric":
        return rubric_digest(doc)
    return sha256_text(prompt_canonical(doc))[:12]


def prompt_state(repo_root: Path, refs: Mapping[str, str]) -> dict[str, dict[str, str | None]]:
    """{ref: {sha256, digest}} for each prompt file the listed runs' judgments name, as the files stand now."""
    out: dict[str, dict[str, str | None]] = {}
    for ref, kind in sorted(refs.items()):
        path = Path(repo_root) / ref
        digest: str | None
        try:
            digest = prompt_file_digest(path, kind) if path.is_file() else None
        except (OSError, ValueError) as exc:
            digest = f"unreadable: {type(exc).__name__}: {exc}"
        out[ref] = {"sha256": _sha(path), "digest": digest}
    return out


def seed_state(seed_file: Path, seed_ids: Sequence[str]) -> dict[str, str | None]:
    """{seed_id: seeds.seed_digest of its current text} for the seeds the listed runs used; null when absent."""
    try:
        doc = load_json(seed_file)
        seeds = {s["seed_id"]: s for s in doc["seeds"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {sid: f"unreadable seed file: {type(exc).__name__}" for sid in seed_ids}
    return {sid: (seed_digest(seeds[sid]) if sid in seeds else None) for sid in sorted(seed_ids)}


# ------------------------------------------------------------------ the freshness basis


def pack_state(inputs: PackInputs, prompt_refs: Mapping[str, str], seed_ids: Sequence[str]) -> dict[str, Any]:
    """The current value of every input a pack depends on: the freshness basis --check compares (module docstring,
    STALE). Never raises: an input that is missing or unreadable is recorded as such, so it reads as moved."""
    stems = [Path(d).name for d in inputs.run_dirs]
    return {
        "runs": {Path(d).name: run_file_state(Path(d)) for d in inputs.run_dirs},
        "campaign_runs": campaign_runs(inputs.runs_dir, inputs.plan),
        "chain": chain_state(inputs.runs_dir, stems),
        "analysis_sha256": _sha(inputs.analysis),
        "plan_sha256": _sha(inputs.plan),
        "claims_sha256": _sha(inputs.claims),
        "prompts": prompt_state(inputs.repo_root, prompt_refs),
        "seeds": seed_state(inputs.seeds, seed_ids),
    }


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(obj, dict) and obj:
        out: dict[str, Any] = {}
        for k in sorted(obj):
            out.update(_flatten(obj[k], f"{prefix}[{k}]" if prefix else str(k)))
        return out
    return {prefix: obj}


def _short(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
        return value[:12]
    return str(value)


def moved_fields(built: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    """Each input whose value moved since the build, as `field: old -> new`."""
    a, b = _flatten(dict(built)), _flatten(dict(current))
    return [f"{k}: {_short(a.get(k))} -> {_short(b.get(k))}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


# ------------------------------------------------------------------ the analysis artifact and the claims


def read_analysis(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """The section 10 artifact, or the reasons it cannot carry a claim: absent, unparseable, not a --final output, or
    missing a block the claims are read from."""
    where = _rel(path)
    if not Path(path).is_file():
        return None, [f"the analysis artifact {where} is absent: build the pack after `python {ANALYSIS_SCRIPT} --final "
                      f"--out {where}` has written it"]
    try:
        doc = load_json(path)
    except ValueError as exc:
        return None, [f"the analysis artifact {where} does not parse ({exc})"]
    if not isinstance(doc, dict):
        return None, [f"the analysis artifact {where} holds a {type(doc).__name__}, not an object"]
    if doc.get("final") is not True:
        return None, [f"the analysis artifact {where} is not a final analysis (final: {doc.get('final')!r}): the "
                      f"coverage-only output computes no contrast, so it carries no claim"]
    problems = []
    for dotted in ("section_10_2.wording.row_id", "section_10_3", "as_first_written", "coverage.runs", "identity",
                   "run_list", "bootstrap_seed"):
        node: Any = doc
        for part in dotted.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            problems.append(f"the analysis artifact {where} has no {dotted}")
    if doc.get("bootstrap_seed") not in (None, ANALYSIS_SEED):
        problems.append(f"the analysis artifact {where} ran with bootstrap seed {doc.get('bootstrap_seed')}, not the "
                        f"{ANALYSIS_SEED} section 10.2 fixes")
    if not isinstance((doc.get("coverage") or {}).get("runs"), list):
        problems.append(f"the analysis artifact {where}: coverage.runs is not a list of runs")
    problems += truncation_problems(doc, where)
    return (None if problems else doc), problems


TRUNCATION_KEYS = ("administratively_truncated", "truncation_reason", "fires_not_landed")


def truncation_problems(doc: Mapping[str, Any], where: str) -> list[str]:
    """The artifact's truncation record, which a --final output always writes (`administratively_truncated`, a bool;
    `truncation_reason`, the --declare-truncated text or null; `fires_not_landed`, the plan's fires with no run). The
    README states from it whether every fire landed, so an absent field is refused, never read as the untruncated
    case, and so is a combination that contradicts itself."""
    missing = [k for k in TRUNCATION_KEYS if k not in doc]
    if missing:
        return [f"the analysis artifact {where} has no {', '.join(missing)}: a --final output records whether the "
                f"campaign was truncated, and the pack never assumes it was not"]
    truncated, reason, fires = (doc[k] for k in TRUNCATION_KEYS)
    problems = []
    if not isinstance(truncated, bool):
        problems.append(f"the analysis artifact {where}: administratively_truncated is {truncated!r}, not true or "
                        f"false")
    if not isinstance(fires, list) or not all(isinstance(f, str) and f for f in fires):
        problems.append(f"the analysis artifact {where}: fires_not_landed is {fires!r}, not a list of fire nonces")
    elif truncated is True:
        if not (isinstance(reason, str) and reason.strip()):
            problems.append(f"the analysis artifact {where} is truncated but records no truncation_reason")
        if not fires:
            problems.append(f"the analysis artifact {where} is truncated but names no fire not landed")
    elif truncated is False:
        if reason is not None:
            problems.append(f"the analysis artifact {where} is not truncated but records a truncation_reason "
                            f"({reason!r})")
        if fires:
            problems.append(f"the analysis artifact {where} is not truncated but names fire(s) not landed {fires}")
    return problems


def analysis_run_problems(doc: Mapping[str, Any], run_dirs: Sequence[Path]) -> list[str]:
    """The listed runs must be the runs the analysis read, on the same bytes: the manifest and judgments it rebuilt
    from, and the committed analysis rows its as-first-written block read (their sha256, as the artifact records)."""
    recorded = {r.get("run_stem"): r for r in doc["coverage"]["runs"] if isinstance(r, dict)}
    listed = {Path(d).name: Path(d) for d in run_dirs}
    problems = []
    for stem in sorted(set(recorded) - set(listed), key=str):
        problems.append(f"the analysis read {stem}, which the pack does not list; the claims rest on every run it read")
    for stem in sorted(set(listed) - set(recorded)):
        problems.append(f"the pack lists {stem}, which the analysis did not read; its claims do not cover that run")
    for stem in sorted(set(listed) & set(recorded)):
        rec, run_dir = recorded[stem], listed[stem]
        rows = rec.get("committed_analysis_rows") or {}
        for name, want in (("manifest.json", rec.get("manifest_sha256")),
                           ("judgments.jsonl", rec.get("judgments_sha256")),
                           ("analysis_rows.jsonl", rows.get("sha256") if isinstance(rows, dict) else None)):
            have = _sha(run_dir / name)
            if have != want:
                problems.append(f"{stem}/{name}: the analysis read sha256 {_short(want)}, the run holds "
                                f"{_short(have)}; the claims were computed on other bytes")
    return problems


def _wording(row_id: str, table: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    """The 10.2 table's permitted wording for a row id the analysis wrote, or the problem. `rowA/rowB` (the reverse
    direction, rows 1-3's rule B applied) joins row A's cell and row B's."""
    rows, without = table["rows"], table["without_a_row"]
    if row_id in rows:
        return {"what_may_be_said": rows[row_id]["what_may_be_said"], "note": None}, None
    if row_id in without:
        return {"what_may_be_said": None, "note": without[row_id]["note"]}, None
    head, sep, base = row_id.partition("/")
    if sep and head in rows and base in rows:
        return {"what_may_be_said": f"{rows[head]['what_may_be_said']} Under {base}'s rule: "
                                    f"{rows[base]['what_may_be_said']}", "note": None}, None
    return {}, f"the wording table ({table['section']}) has no row {row_id!r}"


def claims_block(doc: Mapping[str, Any], wording: Mapping[str, Any], analysis_path: Path,
                 claims_path: Path) -> tuple[dict[str, Any], list[str]]:
    """What the pack says the results permit, from the artifact's ids and the wording file's texts (the design note's,
    verbatim), with the plan's limitations. A claim id the wording file does not carry is a problem, never a guess."""
    problems: list[str] = []
    table = wording["wording_table"]
    head = doc["section_10_2"]["wording"]
    headline, p = _wording(str(head["row_id"]), table)
    if p:
        problems.append(p)
    statements = wording["decomposition_statements"]
    sec3 = doc["section_10_3"]
    if sec3.get("status") == "refused":
        decomposition: dict[str, Any] = {"status": "refused", "reason": sec3.get("reason"), "statement_id": None,
                                         "what_may_be_said": None, "note": None}
    else:
        st = sec3.get("statement") or {}
        sid = st.get("statement_id")
        entry = statements["statements"].get(sid)
        if entry is None:
            problems.append(f"the statement table ({statements['section']}) has no statement {sid!r}")
            entry = {}
        text = entry.get("what_may_be_said")
        if text and st.get("vocabulary_also_lowered"):
            text = f"{text} Add: {statements['vocabulary_also_lowered']['what_may_be_said']}"
        decomposition = {"status": "computed", "statement_id": sid,
                         "vocabulary_also_lowered": bool(st.get("vocabulary_also_lowered")),
                         "what_may_be_said": text, "note": entry.get("note")}
    afw = doc["as_first_written"]
    first: dict[str, Any] = {"label": afw.get("label"), "status": afw.get("status")}
    if afw.get("status") == "computed":
        rid = str(((afw.get("section_10_2") or {}).get("wording") or {}).get("row_id"))
        text_block, p = _wording(rid, table)
        if p:
            problems.append(f"as first written: {p}")
        first.update({"row_id": rid, **text_block})
    else:
        first["reason"] = afw.get("reason")
    identity = doc.get("identity") or {}
    changes = identity.get("uncommitted_changes") or {}
    dirty = {k: v for k, v in changes.items() if v} if isinstance(changes, dict) else {"all": changes}
    block = {
        "analysis": {"path": _rel(analysis_path), "sha256": _sha(analysis_path), "commit": identity.get("commit"),
                     "generated_utc": identity.get("generated_utc"), "bootstrap_seed": doc.get("bootstrap_seed"),
                     # read_analysis has refused an artifact without these three (truncation_problems)
                     "administratively_truncated": doc["administratively_truncated"],
                     "truncation_reason": doc["truncation_reason"],
                     "fires_not_landed": list(doc["fires_not_landed"]), "uncommitted_changes": dirty},
        "headline": {"source": "section_10_2.wording", "table": table["section"], "row_id": head["row_id"],
                     "selectable_as_registered": head.get("selectable_as_registered"),
                     "not_selectable_reasons": head.get("not_selectable_reasons") or [],
                     "scenarios_with_mean_in_primary_direction":
                         head.get("scenarios_with_mean_in_primary_direction") or [], **headline},
        "decomposition": {"source": "section_10_3.statement", "table": statements["section"], **decomposition},
        "never_said": statements["always"],
        "as_first_written": {"source": "as_first_written.section_10_2.wording", **first},
        "limitations": list(wording["limitations"]),
        "wording_file": {"path": _rel(claims_path), "sha256": _sha(claims_path), "source": wording.get("source")},
    }
    return block, problems


# ------------------------------------------------------------------ counted facts for the README and the note


def _judge_facts(runs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Judgments per judge model and method, the judge's request ids (on rows with method `judge`, the calls), and
    whether each run's judge billed through an aggregator, whose ids are not the vendor's."""
    by_model: dict[str, Counter] = {}
    calls = with_id = routed = routed_ids = 0
    served: set[str] = set()
    for run in runs.values():
        via_aggregator = run["judge_billing_channel"] == "openrouter"
        for j in run["judgments"]:
            by_model.setdefault(str(j.get("judge_model")), Counter())[str(j.get("method"))] += 1
            if j.get("method") == "judge":
                calls += 1
                has_id = bool(j.get("judge_request_id"))
                if via_aggregator:
                    routed += 1
                    routed_ids += has_id
                else:
                    with_id += has_id
                if j.get("served_model"):
                    served.add(str(j["served_model"]))
    return {"by_model": {m: dict(c) for m, c in sorted(by_model.items())}, "calls": calls,
            "calls_with_vendor_request_id": with_id, "calls_via_aggregator": routed,
            "aggregator_request_ids": routed_ids, "served_models": sorted(served)}


def _target_facts(runs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    calls = sum(r["target_calls"] for r in runs.values())
    events = sum(r["model_events"] for r in runs.values())
    raw = sum(r["model_events_with_call"] for r in runs.values())
    served = sorted({m for r in runs.values() for m in r["target_served"]})
    return {"calls": calls, "model_events": events, "model_events_with_raw_call": raw,
            "headers_kept_runs": sorted(s for s, r in runs.items() if r["headers_kept"]), "served_models": served}


def request_id_text(target: Mapping[str, Any], judge: Mapping[str, Any], run_count: int) -> str:
    """The README's request-id paragraph, counted from the records: a request id is offered only where a record
    carries one of the vendor's."""
    n = target["calls"]
    if target["model_events_with_raw_call"] or target["headers_kept_runs"]:
        text = (f"Of the {n} target calls, {target['model_events_with_raw_call']} model events in the sanitised logs "
                f"keep the raw provider call, and the logs of {len(target['headers_kept_runs'])} of the {run_count} "
                f"runs keep response headers; any request id your API returned is there, and only there.")
    else:
        text = (f"None of the {n} target calls carries a request id from your API in these records: the sanitised "
                f"logs keep neither the raw provider call nor response headers. They can be matched by the model "
                f"events' timestamps in `sanitised_log.json` and the served build string.")
    c = judge["calls"]
    own = judge["calls_with_vendor_request_id"]
    direct = c - judge["calls_via_aggregator"]
    if direct and own == direct:
        text += f" All {own} judge calls made directly carry the request id your API returned (`judge_request_id`)."
    elif own:
        text += (f" {own} of the {direct} judge calls made directly carry the request id your API returned "
                 f"(`judge_request_id`); the other {direct - own} carry none.")
    elif direct:
        text += f" None of the {direct} judge calls carries a request id from your API."
    if judge["calls_via_aggregator"]:
        text += (f" {judge['calls_via_aggregator']} judge calls were routed through an aggregator; the request ids on "
                 f"{judge['aggregator_request_ids']} of them are the aggregator's, not yours.")
    return text


def _judges_text(judge: Mapping[str, Any]) -> str:
    """Per judge model: the judge calls, and the codings recorded by another method (`rule`: not applicable, decided
    without a call)."""
    parts = []
    for model, methods in judge["by_model"].items():
        part = f"{methods.get('judge', 0)} judge calls to `{model}`"
        other = {m: n for m, n in methods.items() if m != "judge"}
        if other:
            part += "".join(f" and {n} codings by `{m}` recorded without a call" for m, n in sorted(other.items()))
        parts.append(part)
    return "; ".join(parts) + "." if parts else "none."


# ------------------------------------------------------------------ templates


_NOTE_BLOCK = re.compile(r"<!-- BEGIN (\S+) -->\n(.*?)\n<!-- END \1 -->", re.S)


def note_blocks(template: str) -> dict[str, str]:
    return dict(_NOTE_BLOCK.findall(template))


def render_note(template: str, publication_state: str, fields: Mapping[str, Any]) -> str:
    """The disclosure note: the template's `note` block with the opening and dispute clauses of the publication state
    it names, every clause's fields filled. Raises PackRefusal for a template missing a block or naming a field the
    builder does not fill, and for a note that still holds a bracketed field: the note is sealed into the pack, so
    nothing in it is left to fill by hand."""
    blocks = note_blocks(template)
    need = ["note", f"opening:{publication_state}", f"dispute:{publication_state}"]
    missing = [b for b in need if b not in blocks]
    if missing:
        raise PackRefusal([f"the note template {_rel(NOTE_TEMPLATE)} has no block(s) {missing}"])
    try:
        text = blocks["note"].format(opening=blocks[f"opening:{publication_state}"].strip().format(**fields),
                                     dispute=blocks[f"dispute:{publication_state}"].strip().format(**fields),
                                     **fields) + "\n"
    except (KeyError, IndexError, ValueError) as exc:
        raise PackRefusal([f"the note template names a field the builder does not fill ({exc!r})"]) from exc
    left = sorted(set(re.findall(r"\[[^\]\n]*\]", text)))
    if left:
        raise PackRefusal([f"the rendered note still holds bracketed field(s) {left}; a pack seals its note, so every "
                           f"field is a build input ({', '.join(PUBLICATION_FIELDS.values())})"])
    return text


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def publication_record(publication_state: str, details: Mapping[str, Any]) -> tuple[dict[str, str | None], list[str]]:
    """The facts the note of a publication state states beyond the pack's records: since when a page has shown the
    results (`already_public`, `formerly_public`), until when and why the page withheld them (`formerly_public`), and
    where the deviation is recorded (both). Returns (the four fields, null where the state has none; problems). A
    field the state requires and lacks, a field it does not use, a date that is not YYYY-MM-DD, an end before the
    start, a link that is not https and a text with a line break or a bracket are each refused by name."""
    required = PUBLICATION_REQUIRES.get(publication_state, ())
    record: dict[str, str | None] = {}
    problems: list[str] = []
    for field, flag in PUBLICATION_FIELDS.items():
        raw = details.get(field)
        value = raw.strip() if isinstance(raw, str) else raw
        if value in (None, ""):
            record[field] = None
            if field in required:
                problems.append(f"{flag} is required for --publication-state {publication_state}: its note states it")
            continue
        record[field] = value
        if field not in required:
            problems.append(f"{flag} does not apply to --publication-state {publication_state}, whose note does not "
                            f"state it")
        elif not isinstance(value, str):
            problems.append(f"{flag} is {value!r}, not text")
        elif field in ("public_since", "public_until"):
            try:
                ok = bool(_DATE.fullmatch(value)) and date.fromisoformat(value).isoformat() == value
            except ValueError:
                ok = False
            if not ok:
                problems.append(f"{flag} {value!r} is not a date in the form YYYY-MM-DD")
        elif field == "deviation_link" and (not value.startswith("https://") or re.search(r"\s", value)):
            problems.append(f"{flag} {value!r} is not an https link")
        elif field == "withheld_reason" and re.search(r"[\n\r\[\]]", value):
            problems.append(f"{flag} holds a line break or a bracket; give the reason as one line of text")
    since, until = record["public_since"], record["public_until"]
    dated = not any(p.startswith(("--public-since", "--public-until")) for p in problems)
    if since and until and dated and until < since:            # YYYY-MM-DD compares as the dates do
        problems.append(f"--public-until {until} is before --public-since {since}")
    return record, problems


def render_readme(template: str, fields: Mapping[str, Any]) -> str:
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError) as exc:
        raise PackRefusal([f"the README template {_rel(README_TEMPLATE)} names a field the builder does not fill "
                           f"({exc!r})"]) from exc


def _claims_text(claims: Mapping[str, Any]) -> str:
    def said(block: Mapping[str, Any]) -> str:
        if block.get("what_may_be_said"):
            return block["what_may_be_said"]
        return f"No wording is permitted. {block.get('note') or ''}".strip()

    head = claims["headline"]
    lines = [f"- **Headline** (design note {head['table']}, row `{head['row_id']}`): {said(head)}"]
    if head["scenarios_with_mean_in_primary_direction"]:
        lines.append(f"  Scenarios whose mean is in the primary test's direction: "
                     f"{', '.join(f'`{s}`' for s in head['scenarios_with_mean_in_primary_direction'])}.")
    if head["selectable_as_registered"] is False:
        lines.append(f"  Not selectable as registered: {'; '.join(head['not_selectable_reasons'])}.")
    dec = claims["decomposition"]
    if dec["status"] == "refused":
        lines.append(f"- **Style against vocabulary** ({dec['table']}): not computed; the analysis refused "
                     f"it ({dec.get('reason')}).")
    else:
        lines.append(f"- **Style against vocabulary** ({dec['table']}, statement `{dec['statement_id']}`): "
                     f"{said(dec)}")
    lines.append(f"- **Never said**: {claims['never_said']}")
    first = claims["as_first_written"]
    if first["status"] == "computed":
        lines.append(f"- **Secondary: the analysis as first written** (row `{first['row_id']}`): {said(first)} "
                     f"It selects no headline; the analysis above does.")
    else:
        lines.append(f"- **Secondary: the analysis as first written**: {first['status']} ({first.get('reason')}).")
    an = claims["analysis"]
    if an["administratively_truncated"]:
        lines.append(f"- **Administratively truncated**: {an['truncation_reason']}; fires not landed: "
                     f"{', '.join(an['fires_not_landed'])}.")
    else:
        lines.append("- Every fire of the plan landed: the analysis is not truncated.")
    return "\n".join(lines)


# ------------------------------------------------------------------ the build


def _state_utc(values: Sequence[Any]) -> str | None:
    stamps = [v for v in values if isinstance(v, str) and v]
    return max(stamps) if stamps else None


def _dir_digests(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _safe_ref(ref: str) -> bool:
    parts = Path(ref).parts
    return bool(parts) and not Path(ref).is_absolute() and not any(p in ("..", ".", "") for p in parts)


def _collect(inputs: PackInputs) -> tuple[dict[str, Any], list[str], list[str]]:
    """Read and check every input. Returns (facts, problems, notices); a build proceeds only without problems."""
    problems: list[str] = []
    notices: list[str] = []
    vendor = inputs.vendor.strip()
    if not vendor:
        problems.append("--vendor is empty")
    if not inputs.run_dirs:
        problems.append("no --run-dir given: a pack is built over an explicit list of landed runs")
    stems = [Path(d).name for d in inputs.run_dirs]
    doubled = sorted(s for s, n in Counter(stems).items() if n > 1)
    if doubled:
        problems.append(f"run(s) listed twice: {doubled}")
    try:
        providers = load_json(PROVIDERS_PATH) if PROVIDERS_PATH.is_file() else {}
    except ValueError as exc:
        providers = {}
        problems.append(f"the provider registry {_rel(PROVIDERS_PATH)} does not parse ({exc})")
    doc, analysis_problems = read_analysis(inputs.analysis)
    problems += analysis_problems
    if Path(inputs.analysis).name == Path(inputs.plan).name:
        problems.append(f"--analysis and --plan share the basename {Path(inputs.analysis).name}, and the pack carries "
                        f"both under analysis/ by that name; rename one")
    wording: dict[str, Any] | None = None
    try:
        loaded = load_json(inputs.claims)
        absent = [k for k in ("wording_table", "decomposition_statements", "limitations")
                  if not isinstance(loaded, dict) or k not in loaded]
        if absent:
            problems.append(f"the claims wording file {_rel(inputs.claims)} has no {', '.join(absent)}")
        else:
            wording = loaded
    except (OSError, ValueError) as exc:
        problems.append(f"the claims wording file {_rel(inputs.claims)} cannot be read ({type(exc).__name__}: {exc})")
    try:
        seed_doc = load_json(inputs.seeds)
        current_seeds = {s["seed_id"]: s for s in seed_doc["seeds"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        current_seeds = {}
        problems.append(f"the seed file {_rel(inputs.seeds)} cannot be read ({type(exc).__name__}: {exc})")
    try:
        fires = plan_fires(inputs.plan)
    except (OSError, ValueError) as exc:
        fires = {}
        problems.append(f"the plan {_rel(inputs.plan)} cannot be read ({type(exc).__name__}: {exc})")

    runs: dict[str, dict[str, Any]] = {}
    prompt_refs: dict[str, str] = {}
    prompt_rows: dict[str, Counter] = {}
    seed_recorded: dict[str, dict[str, str]] = {}
    for run_dir in (Path(d) for d in inputs.run_dirs):
        stem = run_dir.name
        if not run_dir.is_dir():
            problems.append(f"{_rel(run_dir)}: no such run directory")
            continue
        if run_dir.resolve().parent != Path(inputs.runs_dir).resolve():
            problems.append(f"{_rel(run_dir)} is not a run directory of {_rel(inputs.runs_dir)}, whose chain the pack "
                            f"cites")
            continue
        vr = verify_run(run_dir)
        if vr:
            problems.append(f"{stem} does not pass verify-run: " + "; ".join(vr))
            continue
        manifest = load_json(run_dir / "manifest.json")
        files, file_problems, hidden = classify_run_files(run_dir, manifest)
        problems += file_problems
        if hidden:
            notices.append(f"{stem}: hidden file(s) {hidden} ignored and not packed")
        problems += foreign_model_problems(run_dir, manifest, vendor, providers)
        try:
            judgments = _read_jsonl(run_dir / "judgments.jsonl")
            transcripts = _read_jsonl(run_dir / "transcripts.jsonl")
            sanitised = load_json(run_dir / ARTIFACT_FILENAMES["sanitised_log"])
        except (OSError, ValueError) as exc:
            problems.append(f"{stem}: {exc}")
            continue
        undigested: Counter = Counter()
        for j in judgments:
            ref, digest = j.get("prompt_ref"), j.get("prompt_file_digest")
            kind = "rubric" if j.get("kind") == "tier" else "prompt"
            if not isinstance(ref, str) or not ref:
                problems.append(f"{stem}: a judgment names no prompt_ref, so its prompt file cannot be packed")
                break
            if prompt_refs.setdefault(ref, kind) != kind:
                problems.append(f"{ref} is named both as a rubric and as an outcome prompt")
            if not (isinstance(digest, str) and PROMPT_DIGEST.fullmatch(digest)):
                undigested[ref] += 1
                continue
            prompt_rows.setdefault(ref, Counter())[f"{digest} ({stem})"] += 1
        for ref, n in sorted(undigested.items()):
            problems.append(f"{stem}: {n} judgment(s) naming {ref} record no prompt_file_digest (absent, null, empty "
                            f"or not the 12-hex digest a judgment records), so the pack cannot name the prompt they "
                            f"were judged under")
        for s in manifest.get("seeds") or []:
            seed_recorded.setdefault(s["seed_id"], {})[stem] = s["seed_sha256"]
        nonce = run_nonce(manifest)
        if nonce not in fires:
            problems.append(f"{stem}: its fire {nonce!r} is not one of the plan's fires {sorted(fires)}")
        artifacts = manifest.get("artifacts") or {}
        judge = artifacts.get("judge_of_record") or {}
        target_usage = [r for r in (manifest.get("usage") or {}).get("by_role") or [] if r.get("role") == "target"]
        events = _model_events(sanitised)
        redaction = ((artifacts.get("sanitiser") or {}).get("redaction_report") or {})
        readapt = manifest.get("readapt")
        runs[stem] = {
            "files": files, "manifest": manifest, "judgments": judgments,
            "judge_billing_channel": judge.get("billing_channel"),
            "target_calls": sum(int(r.get("calls") or 0) for r in target_usage),
            "model_events": len(events), "model_events_with_call": sum(1 for e in events if e.get("call") is not None),
            "headers_kept": bool(redaction.get("headers_kept")),
            "target_served": sorted({str((t.get("source") or {}).get("model_version")) for t in transcripts
                                     if isinstance(t, dict) and (t.get("source") or {}).get("model_version")}),
            "facts": {"run_id": manifest.get("run_id"), "eval_id": manifest.get("eval_id"),
                      "journal_nonce": nonce, "partition": (fires.get(nonce) or {}).get("partition"),
                      "campaign_epochs": (fires.get(nonce) or {}).get("campaign_epochs"),
                      "created_utc": manifest.get("created_utc"), "judged_utc": judge.get("judged_utc"),
                      "target": ((manifest.get("models") or {}).get("target") or {}).get("inspect_name"),
                      "judge_model": judge.get("judge_model"), "conversations": len(transcripts),
                      "judgments": len(judgments), "manifest_sha256": (manifest.get("chain") or {}).get("manifest_sha256"),
                      "environment_lock_sha256": (manifest.get("harness") or {}).get("environment_lock_sha256"),
                      "outcome_registry_sha256": (manifest.get("framework") or {}).get("outcome_registry_sha256"),
                      "readapt": None if readapt is None else {
                          k: readapt.get(k) for k in ("source_workflow_run_id", "readapt_workflow_run_id",
                                                      "readapt_journal_nonce", "readapt_commit")}},
        }

    for sid, by_run in sorted(seed_recorded.items()):
        current = seed_digest(current_seeds[sid]) if sid in current_seeds else None
        for stem, recorded in sorted(by_run.items()):
            if recorded != current:
                problems.append(f"seed {sid}: {stem} recorded digest {_short(recorded)}, the seed file holds "
                                f"{_short(current)}; the analysis refuses a seed that drifted, and so does the pack")
    for ref in sorted(prompt_refs):
        if not _safe_ref(ref):
            problems.append(f"prompt ref {ref!r} is not a plain repository-relative path")
        elif not (Path(inputs.repo_root) / ref).is_file():
            problems.append(f"prompt file {ref} is missing, so the pack cannot carry it")
    ok, msg = verify_chain(Path(inputs.runs_dir))
    if not ok:
        problems.append(f"the chain under {_rel(inputs.runs_dir)} does not verify: {msg}")
    lines = chain_lines(inputs.runs_dir)
    chained = {Path(rel).parent.as_posix() for rel, _ in lines}
    for stem in stems:
        if stem not in chained:
            problems.append(f"{stem} is not in {_rel(Path(inputs.runs_dir) / CHAIN_FILE)}; a pack cites its chain line")
    campaign = campaign_runs(inputs.runs_dir, inputs.plan)
    for stem in campaign:
        if stem not in stems:
            problems.append(f"{stem} is a landed run of the plan's fires that the pack does not list")
    if doc is not None:
        problems += analysis_run_problems(doc, inputs.run_dirs)
    if doc is not None and fires and len(runs) == len(stems):
        # the README's truncation statement, counted by the pack as well: the plan's fires no listed run carries
        unlanded = sorted(set(fires) - {r["facts"]["journal_nonce"] for r in runs.values()})
        stated = sorted(doc["fires_not_landed"])
        if stated != unlanded:
            problems.append(f"the analysis artifact {_rel(inputs.analysis)} names fires not landed {stated}, but the "
                            f"plan's fires with no listed run are {unlanded}; the pack states the truncation only "
                            f"where the two agree")
    claims: dict[str, Any] = {}
    if doc is not None and wording is not None:
        try:
            claims, claim_problems = claims_block(doc, wording, inputs.analysis, inputs.claims)
            problems += claim_problems
        except (KeyError, TypeError, AttributeError) as exc:
            problems.append(f"the claims cannot be read from the artifact and the wording file "
                            f"({type(exc).__name__}: {exc})")
    facts = {"doc": doc, "claims": claims, "runs": runs, "prompt_refs": prompt_refs, "prompt_rows": prompt_rows,
             "seed_recorded": seed_recorded, "current_seeds": current_seeds, "chain_head": lines[-1][1] if lines else None,
             "stems": stems}
    return facts, problems, notices


def build_pack(inputs: PackInputs, *, publication_state: str, out: Path = DEFAULT_OUT, log: Path = DEFAULT_LOG,
               note: str = "", registry: Mapping[str, str] | None = None,
               publication_details: Mapping[str, Any] | None = None) -> Path:
    """Assemble one vendor's pack over the listed runs, write it under `out`, and log a new version. Deterministic: the
    same inputs give a byte-identical bundle and log nothing new; wall-clock time enters only the log entry's
    built_utc. Raises PackRefusal, before anything is written, for every reason the module docstring lists."""
    if publication_state not in PUBLICATION_STATES:
        raise PackRefusal([f"--publication-state {publication_state!r} is not one of {list(PUBLICATION_STATES)}"])
    publication, publication_problems = publication_record(publication_state, publication_details or {})
    facts, problems, notices = _collect(inputs)
    problems = publication_problems + problems
    if problems:
        raise PackRefusal(problems)
    for n in notices:
        print(f"note: {n}")
    ae = _advice()
    vendor = inputs.vendor.strip()
    runs = facts["runs"]
    stems = facts["stems"]
    prompt_refs = facts["prompt_refs"]
    seed_ids = sorted(facts["seed_recorded"])
    state = pack_state(inputs, prompt_refs, seed_ids)
    judge = _judge_facts(runs)
    target = _target_facts(runs)
    lock_recorded = {s: r["facts"]["environment_lock_sha256"] for s, r in runs.items()}
    try:
        current_lock = lock_digest(load_lock(inputs.lock))
    except (OSError, ValueError) as exc:
        current_lock = f"unreadable: {type(exc).__name__}"
    lock_packed = len(set(lock_recorded.values())) == 1 and current_lock in lock_recorded.values()
    prompts = {ref: {"kind": kind, **state["prompts"][ref],
                     "rows_by_recorded_digest": dict(sorted(facts["prompt_rows"][ref].items()))}
               for ref, kind in sorted(prompt_refs.items())}
    readme_template = README_TEMPLATE.read_text(encoding="utf-8")
    note_template = NOTE_TEMPLATE.read_text(encoding="utf-8")
    manifest: dict[str, Any] = {
        "pack_format": PACK_FORMAT, "lane": LANE, "vendor": vendor, "scope": Path(inputs.analysis).stem,
        "publication_state": publication_state,
        "publication": publication,
        "inputs": inputs.record(),
        "depends_on": {"run_stems": stems, "prompt_refs": dict(sorted(prompt_refs.items())), "seed_ids": seed_ids},
        "state": state,
        "runs": {s: runs[s]["facts"] for s in stems},
        "chain_head_at_build": facts["chain_head"],
        "claims": {k: facts["claims"][k] for k in ("headline", "decomposition", "as_first_written")}
                  | {"analysis": facts["claims"]["analysis"]},
        "target": target, "judge": judge, "prompts": prompts,
        "seeds": {sid: state["seeds"][sid] for sid in seed_ids},
        "environment_lock": {"path": _rel(inputs.lock), "current_digest": current_lock,
                             "recorded_by_runs": lock_recorded, "packed": lock_packed},
        "templates": {"readme": {"path": _rel(README_TEMPLATE), "sha256": sha256_text(readme_template)},
                      "note": {"path": _rel(NOTE_TEMPLATE), "sha256": sha256_text(note_template)}},
        "engine_commit": ae.engine_sha(),
        "state_utc": _state_utc([r["facts"]["judged_utc"] for r in runs.values()]
                                + [r["facts"]["created_utc"] for r in runs.values()]
                                + [facts["claims"]["analysis"]["generated_utc"]]),
    }
    version = VERSION_PREFIX + sha256_text(canonical_json(manifest))[:12]
    manifest["pack_version"] = version

    out = Path(out)
    bundle = out / f"petri_repro_{vendor}_{version}"
    staging = out / f".staging_{vendor}_{version}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        _write_bundle(staging, inputs, facts, manifest, readme_template, note_template, target, judge, lock_packed)
        hits = _seal_problems(staging, registry)
        if hits:
            raise PackRefusal(hits)
        if bundle.exists():
            if _dir_digests(bundle) != _dir_digests(staging):
                raise PackRefusal([f"{_rel(bundle)} exists and holds other bytes than version {version} builds; a pack "
                                   f"directory is never rebuilt in place (move it aside if it is not a sent pack)"])
            shutil.rmtree(staging)
        else:
            staging.rename(bundle)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    _append_build_entry(Path(log), manifest, note)
    print(f"pack {version} for {vendor}: {len(stems)} run(s), {sum(r['facts']['conversations'] for r in runs.values())} "
          f"conversation(s) -> {bundle}")
    return bundle


def _seal_problems(staging: Path, registry: Mapping[str, str] | None) -> list[str]:
    """The holdout seal over every file of the pack (labels and counts only, never a phrase). An empty sealed set
    cannot show the pack clean, so it refuses too."""
    reg = dict(registry) if registry is not None else seal.sealed_registry()
    result = seal.scan_paths(sorted(p for p in staging.rglob("*") if p.is_file()), reg)
    if result.status == "pass":
        return []
    if result.status == "fail":
        labels = sorted({label for found in result.hits.values() for label in found})
        return [f"holdout seal: {result.detail}; sealed-phrase labels {labels}; a pack goes to a vendor and never "
                f"carries a sealed phrase"]
    return [f"holdout seal not checked: {result.detail}; the pack cannot be shown free of sealed phrases"]


def _write_bundle(root: Path, inputs: PackInputs, facts: Mapping[str, Any], manifest: Mapping[str, Any],
                  readme_template: str, note_template: str, target: Mapping[str, Any], judge: Mapping[str, Any],
                  lock_packed: bool) -> None:
    runs = facts["runs"]
    stems = facts["stems"]
    for stem in stems:
        dest = root / "runs" / stem
        dest.mkdir(parents=True)
        for name in runs[stem]["files"]:
            shutil.copyfile(Path(inputs.runs_dir) / stem / name, dest / name)
    (root / "analysis").mkdir()
    shutil.copyfile(inputs.analysis, root / "analysis" / Path(inputs.analysis).name)
    shutil.copyfile(inputs.plan, root / "analysis" / Path(inputs.plan).name)
    for ref in sorted(facts["prompt_refs"]):
        dest = root / "prompts" / ref
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(inputs.repo_root) / ref, dest)
    if lock_packed:
        (root / "environment").mkdir()
        shutil.copyfile(inputs.lock, root / "environment" / Path(inputs.lock).name)
    seeds = [{"seed_id": sid, "seed_sha256": manifest["seeds"][sid], "recorded_by_runs": facts["seed_recorded"][sid],
              "seed": facts["current_seeds"][sid]} for sid in sorted(facts["seed_recorded"])]
    _write_json(root / "seeds.json", {"seed_file": _rel(inputs.seeds),
                                      "digest_rule": "sha256 of the seed's canonical JSON (sorted keys, no whitespace)",
                                      "seeds": seeds})
    _write_json(root / "CLAIMS.json", facts["claims"])
    _write_json(root / "MANIFEST.json", manifest)
    fields = _readme_fields(inputs, facts, manifest, target, judge, lock_packed)
    (root / "README.md").write_text(render_readme(readme_template, fields), encoding="utf-8")
    note_fields = {"vendor": manifest["vendor"], "pack_version": manifest["pack_version"],
                   "target_model": fields["target_model"], "run_count": fields["run_count"],
                   "conversations": fields["conversations"], "judgments": fields["judgments"],
                   "request_id_clause": _request_id_clause(target, judge), **manifest["publication"]}
    (root / "DISCLOSURE_NOTE.md").write_text(render_note(note_template, manifest["publication_state"], note_fields),
                                             encoding="utf-8")
    sums = _dir_digests(root)
    (root / "SHA256SUMS").write_text("".join(f"{d}  {p}\n" for p, d in sums.items()), encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _request_id_clause(target: Mapping[str, Any], judge: Mapping[str, Any]) -> str:
    """The note's one-sentence request-id clause, from the same counts as the README's paragraph."""
    own, direct = judge["calls_with_vendor_request_id"], judge["calls"] - judge["calls_via_aggregator"]
    if target["model_events_with_raw_call"] or target["headers_kept_runs"]:
        target_part = f"some of the {target['calls']} target calls keep the raw provider call in the sanitised logs"
    else:
        target_part = f"the {target['calls']} target calls carry none in these records"
    if direct and own == direct:
        judge_part = f"all {own} judge calls made directly carry the one your API returned"
    elif own:
        judge_part = f"{own} of the {direct} judge calls made directly carry the one your API returned"
    else:
        judge_part = "no judge call carries one of yours"
    return f"Request ids: {target_part}; {judge_part}. The README counts them."


def _readme_fields(inputs: PackInputs, facts: Mapping[str, Any], manifest: Mapping[str, Any],
                   target: Mapping[str, Any], judge: Mapping[str, Any], lock_packed: bool) -> dict[str, Any]:
    runs = facts["runs"]
    stems = facts["stems"]
    claims = facts["claims"]
    runs_dir = _rel(inputs.runs_dir)
    run_list = []
    for s in stems:
        f = runs[s]["facts"]
        line = (f"- `runs/{s}/` — fire `{f['journal_nonce']}` ({f['partition']} partition, campaign epochs "
                f"{json.dumps(f['campaign_epochs'], sort_keys=True)}); adapted {f['created_utc']}, judged "
                f"{f['judged_utc']}; {f['conversations']} conversations, {f['judgments']} judgments.")
        if f["readapt"]:
            line += (f" Re-adapted by workflow run {f['readapt']['readapt_workflow_run_id']} (fire "
                     f"`{f['readapt']['readapt_journal_nonce']}`) from the retained log of the source run.")
        run_list.append(line)
    chain_text = "\n".join(f"- line {manifest['state']['chain']['lines'][s][0]}: `{s}/manifest.json` "
                           f"`{manifest['state']['chain']['lines'][s][1]}`" for s in stems)
    verify = "\n".join(f"    python -m scripts.petri_audit.cli verify-run --run-dir {runs_dir}/{s}" for s in stems)
    an = claims["analysis"]
    analysis_rel = _rel(inputs.analysis)
    plan_rel = _rel(inputs.plan)
    cmds = []
    if an["commit"]:
        cmds.append(f"    git checkout {an['commit']}")
    cmds += [f"    python -m scripts.petri_audit.cli verify-run --run-dir {runs_dir}/{s}" for s in stems]
    final = (f"    python {ANALYSIS_SCRIPT} --final --plan {plan_rel} --seed {ANALYSIS_SEED} "
             f"--out {Path(analysis_rel).stem}.reproduced.json")
    if an["administratively_truncated"]:
        final += f" --declare-truncated {json.dumps(an['truncation_reason'])}"
    cmds.append(final)
    lead = (f"At the commit the analysis ran from ({an['commit']}), in a checkout of the public repository:"
            if an["commit"] else "The analysis artifact records no commit; in a checkout of the public repository:")
    identity_note = ""
    if an["uncommitted_changes"]:
        identity_note = (f"The analysis ran with uncommitted changes to {', '.join(sorted(an['uncommitted_changes']))}"
                         f", which its `identity` block records; that commit alone may not reproduce it.")
    stale_prompts = []
    for ref, p in manifest["prompts"].items():
        earlier = {k: n for k, n in p["rows_by_recorded_digest"].items() if not k.startswith(f"{p['digest']} ")}
        if earlier:
            stale_prompts.append(f"`{ref}` (digest `{p['digest']}` here): "
                                 + ", ".join(f"{n} judgments under {k}" for k, n in sorted(earlier.items()))
                                 + " were judged under an earlier version of the file, which the repository's git "
                                   "history holds")
    prompt_note = ("Every judgment's recorded digest is the digest of the file here." if not stale_prompts
                   else "Not every judgment was judged under the file here: " + "; ".join(stale_prompts) + ".")
    lock = manifest["environment_lock"]
    recorded = sorted(set(lock["recorded_by_runs"].values()), key=str)
    lock_note = (f"`environment/{Path(inputs.lock).name}` — the environment lock every run ran under (digest "
                 f"`{recorded[0]}`)." if lock_packed else
                 f"The environment lock is not included: the runs recorded digest(s) {', '.join(map(str, recorded))} "
                 f"and the repository's current lock digests to {lock['current_digest']}; git history holds the "
                 f"recorded one.")
    limitations = "\n".join(f"- {lim['text']} (design note {lim['section']}"
                            + (f", of {lim['about']})" if lim.get("about") else ")") for lim in claims["limitations"])
    return {
        "vendor": manifest["vendor"], "pack_version": manifest["pack_version"],
        "run_count": len(stems), "target_model": ", ".join(sorted({runs[s]['facts']['target'] for s in stems})),
        "conversations": sum(runs[s]["facts"]["conversations"] for s in stems), "target_calls": target["calls"],
        "served_target": ", ".join(f"`{m}`" for m in target["served_models"]) or "none recorded",
        "run_list": "\n".join(run_list), "judgments": sum(runs[s]["facts"]["judgments"] for s in stems),
        "judges": _judges_text(judge), "request_ids": request_id_text(target, judge, len(stems)),
        "analysis_name": Path(inputs.analysis).name, "plan_name": Path(inputs.plan).name,
        "analysis_sha256": claims["analysis"]["sha256"],
        "rubric_digest": ", ".join(sorted(p["digest"] for p in manifest["prompts"].values() if p["kind"] == "rubric")),
        "prompt_note": prompt_note, "seed_count": len(manifest["seeds"]), "lock_note": lock_note,
        "runs_dir": runs_dir, "chain_head": manifest["chain_head_at_build"], "chain_lines": chain_text,
        "verify_run_commands": verify, "analysis_commands": lead + "\n\n" + "\n".join(cmds),
        "analysis_identity_note": identity_note, "claims": _claims_text(claims), "limitations": limitations,
    }


# ------------------------------------------------------------------ the disclosure log


def pack_key(entry: Mapping[str, Any]) -> tuple[str, str]:
    """A Petri pack's identity: (vendor, analysis artifact stem). A later analysis (another campaign's artifact) is
    another pack, never a supersession of this one."""
    return (entry["vendor"], entry["manifest"]["scope"])


def partition_log(entries: Sequence[Any]) -> tuple[list[dict], dict[str, int], list[str]]:
    """(readable petri-lane entries, a count per other lane, one description per unreadable petri-lane entry). An entry
    without a lane is the advice lane's (advice_eval._partition_log), so this check counts and skips it."""
    ae = _advice()
    mine: list[dict] = []
    other: dict[str, int] = {}
    unreadable: list[str] = []
    for n, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            # no lane can be read from it, and an entry without one is the advice lane's: counted under that lane,
            # and the advice check names it as unreadable
            other[ae.ADVICE_LANE] = other.get(ae.ADVICE_LANE, 0) + 1
            continue
        lane = e.get("lane") or ae.ADVICE_LANE
        if lane != LANE:
            other[str(lane)] = other.get(str(lane), 0) + 1
            continue
        missing = [k for k in ("pack_version", "vendor") if not isinstance(e.get(k), str) or not e.get(k)]
        man = e.get("manifest")
        if not isinstance(man, dict):
            missing.append("manifest")
        else:
            if not isinstance(man.get("scope"), str) or not man.get("scope"):
                missing.append("manifest.scope")
            inputs = man.get("inputs")
            if not isinstance(inputs, dict) or any(k not in inputs for k in INPUT_KEYS) \
                    or not isinstance(inputs.get("run_dirs"), list):
                missing.append("manifest.inputs")
            dep = man.get("depends_on")
            if not isinstance(dep, dict) or not isinstance(dep.get("prompt_refs"), dict) \
                    or not isinstance(dep.get("seed_ids"), list):
                missing.append("manifest.depends_on")
            if not isinstance(man.get("state"), dict):
                missing.append("manifest.state")
        if missing:
            unreadable.append(f"entry {n} ({e.get('pack_version') or 'no pack_version'}): missing {', '.join(missing)}")
            continue
        mine.append(e)
    return mine, other, unreadable


def _append_build_entry(log: Path, manifest: Mapping[str, Any], note: str) -> None:
    ae = _advice()
    entries = ae._log_entries(log)
    version = manifest["pack_version"]
    if any(isinstance(e, dict) and e.get("pack_version") == version for e in entries):
        print(f"log: {version} is already in {_rel(log)}; nothing appended")
        return
    newest, _ = ae._newest_by_key(partition_log(entries)[0], key_fn=pack_key)
    prior = newest.get((manifest["vendor"], manifest["scope"]))
    claims = manifest["claims"]
    logged = {k: manifest[k] for k in LOG_MANIFEST_KEYS}
    logged["claim_ids"] = {"headline_row_id": claims["headline"]["row_id"],
                           "decomposition_statement_id": claims["decomposition"].get("statement_id"),
                           "as_first_written_row_id": claims["as_first_written"].get("row_id"),
                           "analysis_sha256": claims["analysis"]["sha256"]}
    entry = {"pack_version": version, "lane": LANE, "vendor": manifest["vendor"], "manifest": logged,
             "built_utc": ae.utc_now_iso(), "sent_utc": None, "sent_to": None,
             "supersedes": prior["pack_version"] if prior else None, "note": note or "built"}
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"log: build entry for {version} appended to {_rel(log)}"
          + (f" (supersedes {entry['supersedes']})" if entry["supersedes"] else ""))


def check_packs(log: Path = DEFAULT_LOG) -> int:
    """FRESH/STALE for the newest Petri pack of every (vendor, analysis); exit codes as the module docstring states."""
    ae = _advice()
    entries = ae._log_entries(log)
    mine, other, unreadable = partition_log(entries)
    for lane, n in sorted(other.items()):
        print(f"skipped: {n} log entr{'y' if n == 1 else 'ies'} of lane {lane!r} (this check covers lane {LANE!r} only)")
    for problem in unreadable:
        print(f"UNREADABLE: {problem} - not checked")
    if not mine:
        print(f"never-built: no readable {LANE}-lane pack in {_rel(log)}")
        return 3 if unreadable else 0
    escalate = False
    newest, sent_versions = ae._newest_by_key(mine, key_fn=pack_key)
    for key in sorted(newest):
        vendor, scope = key
        e = newest[key]
        man = e["manifest"]
        dep = man["depends_on"]
        try:
            current = pack_state(PackInputs.from_record(man["inputs"]), dep["prompt_refs"], dep["seed_ids"])
            moved = moved_fields(man["state"], current)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            moved = [f"state could not be recomputed ({type(exc).__name__}: {exc})"]
        status = "FRESH" if not moved else "STALE"
        shown = moved[:MAX_MOVED_SHOWN] + ([f"... and {len(moved) - MAX_MOVED_SHOWN} more"]
                                           if len(moved) > MAX_MOVED_SHOWN else [])
        print(f"{status}  {e['pack_version']}  {vendor}  {scope}" + ("" if not moved else "  | " + "; ".join(shown)))
        sent = sent_versions.get(key, set())
        if e["pack_version"] in sent:
            if status == "STALE":
                print(f"ESCALATION: sent pack {e['pack_version']} ({vendor}, {scope}) is stale - an updated pack is "
                      f"owed")
                escalate = True
        elif sent:
            print(f"note: {vendor} {scope}: SENT pack(s) {', '.join(sorted(sent))}; newest built is "
                  f"{e['pack_version']} (unsent) - send the superseding pack")
            escalate = True
    if escalate:
        return 2
    return 3 if unreadable else 0


def record_sent(log: Path, version: str, sent_to: str, note: str = "") -> None:
    """Append a send event for a Petri pack already in the log, stamped now (advice_eval.repro_pack_record_sent)."""
    problems = []
    if not sent_to.strip():
        problems.append("--sent-to is required: the role or channel the pack went to")
    elif "@" in sent_to:
        problems.append("--sent-to looks like a contact address; the log is public, so give a role or channel only")
    entries = _advice()._log_entries(log)
    mine = [e for e in entries if isinstance(e, dict) and e.get("pack_version") == version]
    if not mine:
        problems.append(f"pack {version!r} is not in {_rel(log)}")
    elif any((e.get("lane") or _advice().ADVICE_LANE) != LANE for e in mine):
        problems.append(f"pack {version!r} is not a {LANE}-lane pack; record its send with its own lane's tooling")
    if problems:
        raise PackRefusal(problems)
    _advice().repro_pack_record_sent(argparse.Namespace(log=str(log), record_sent=version, sent_to=sent_to.strip(),
                                                        note=note))


# ------------------------------------------------------------------ CLI


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--vendor", default=None, help="build: the vendor whose model the runs involve (e.g. anthropic)")
    p.add_argument("--run-dir", action="append", default=[],
                   help="build: a landed run directory under --runs-dir (repeat for each run of the analysis)")
    p.add_argument("--publication-state", choices=PUBLICATION_STATES, default=None,
                   help="build: which disclosure-note version is true (not_yet_public until a page shows the results)")
    p.add_argument("--public-since", default=None, metavar="YYYY-MM-DD",
                   help="build, already_public and formerly_public: the date a page first showed the results")
    p.add_argument("--public-until", default=None, metavar="YYYY-MM-DD",
                   help="build, formerly_public: the date the page withheld them")
    p.add_argument("--withheld-reason", default=None,
                   help="build, formerly_public: why the page withheld them, as the page states it (one line)")
    p.add_argument("--deviation-link", default=None, metavar="URL",
                   help="build, already_public and formerly_public: the https link to the recorded deviation")
    p.add_argument("--analysis", default=str(DEFAULT_ANALYSIS), help="the section 10 --final artifact")
    p.add_argument("--plan", default=str(DEFAULT_PLAN))
    p.add_argument("--claims", default=str(DEFAULT_CLAIMS), help="the claims wording file")
    p.add_argument("--seeds", default=str(SEED_FILE))
    p.add_argument("--lock", default=str(ENV_LOCK))
    p.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    p.add_argument("--repo-root", default=str(ROOT), help="where the prompt refs the judgments record resolve")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="where the bundle is written (dist/, never committed)")
    p.add_argument("--log", default=str(DEFAULT_LOG))
    p.add_argument("--note", default="")
    p.add_argument("--check", action="store_true",
                   help="FRESH/STALE for the newest Petri pack of each (vendor, analysis); exit 2 when a sent pack is "
                        "stale or superseded-but-unsent, 3 when a petri-lane log entry cannot be read")
    p.add_argument("--record-sent", metavar="PACK_VERSION", default=None,
                   help="append a send event for a built Petri pack, stamped now")
    p.add_argument("--sent-to", default="", help="role/channel reference only - never private contact details")


def cmd_repro_pack(args: argparse.Namespace) -> int:
    if args.check:
        return check_packs(Path(args.log))
    try:
        if args.record_sent:
            record_sent(Path(args.log), args.record_sent, args.sent_to, args.note)
            return 0
        missing = [flag for flag, value in (("--vendor", args.vendor), ("--run-dir", args.run_dir),
                                            ("--publication-state", args.publication_state)) if not value]
        if missing:
            raise PackRefusal([f"build mode requires {', '.join(missing)}"])
        inputs = PackInputs(vendor=args.vendor, run_dirs=tuple(Path(d) for d in args.run_dir),
                            runs_dir=Path(args.runs_dir), analysis=Path(args.analysis), plan=Path(args.plan),
                            claims=Path(args.claims), seeds=Path(args.seeds), lock=Path(args.lock),
                            repo_root=Path(args.repo_root))
        build_pack(inputs, publication_state=args.publication_state, out=Path(args.out), log=Path(args.log),
                   note=args.note, publication_details={f: getattr(args, f) for f in PUBLICATION_FIELDS})
        return 0
    except PackRefusal as exc:
        for p in exc.problems:
            print(f"refused: {p}", file=sys.stderr)
        return REFUSED_EXIT
