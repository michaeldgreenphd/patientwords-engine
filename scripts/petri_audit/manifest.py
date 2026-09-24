"""Run manifest assembly, validation and hash chain
(docs/framework/petri_run_manifest.schema.json, draft 0.2; design memo section 9).

The manifest is the closed execution sidecar: everything Petri-specific lives
here, the transcript stays generic. Two digests:

- `identity_sha256`: the manifest with the chain block removed and the
  record-dependent artifact fields blanked (the transcript, rule-outcome and
  judgment digests, the judgment path and the judge-of-record block).
  Transcript records carry it in `provenance.run_manifest.sha256`; it cannot
  cover the transcript digest because the transcript carries it, and it does
  not cover the judge stage because judging happens after the records are
  bound.
- `manifest_sha256`: the whole manifest with that one field blanked.
  `prev_sha256` links each run's manifest to the previous one under the same
  data directory, so the family is append-only and any rewrite is detectable.

One reseal is legitimate: `bind_judgments` fills the judgment fields after the
judge of record runs, keeps the identity digest (asserted), and replaces the
chain line of the manifest it reseals, which must still be the chain head.
`verify_chain` checks every manifest's digest and link and, since the first
Codex review of the lane (PR #26), also that every artifact a manifest names
exists and digests to its recorded value, so a judgment file altered or
removed after binding is detected.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .framework import MANIFEST_SCHEMA, canonical_json, load_json, sha256_file, sha256_text, validate_with_refs

MANIFEST_VERSION = "0.2"
CHAIN_FILE = "manifests.chain"           # one manifest digest per line, append-only, per data directory
RECORD_DEPENDENT_FIELDS = ("transcripts_sha256", "rule_outcomes_sha256", "judgments_path", "judgments_sha256",
                           "judge_of_record")
ARTIFACT_FAMILIES = ("sanitised_log", "transcripts", "rule_outcomes", "judgments")
# the filename each family's consumers open by name (the adapter writes them, the judge, the analysis and the summary
# read them); a manifest binding a family to any other file would verify while the consumed file stayed unbound
ARTIFACT_FILENAMES = {"sanitised_log": "sanitised_log.json", "transcripts": "transcripts.jsonl",
                      "rule_outcomes": "rule_outcomes.jsonl", "judgments": "judgments.jsonl"}
JUDGE_REPORT_SUFFIX = ".judge.report.json"


def artifact_name_problems(pairs: list[tuple], manifest_dir: str | None = None) -> list[str]:
    """Each recorded artifact path names the file its family's consumers
    open, and no two families share a path (Codex, PR #27, twelfth round:
    `transcripts_path` sealed as `sanitised_log.json` with that file's
    digest verified, while `transcripts.jsonl` was unbound). With
    `manifest_dir`, every path must also sit in the manifest's own run
    directory (thirteenth round: a resealed manifest naming another run's
    files, same basenames and matching digests, verified while the files
    beside it were unbound). `pairs` are `(relative path, digest, family)`;
    a null or non-string path is another check's problem."""
    problems: list[str] = []
    seen: dict[str, list[str]] = {}
    for rel, _digest, fam in pairs:
        if not isinstance(rel, str):
            continue
        if manifest_dir is not None and Path(rel).parent.as_posix() != manifest_dir:
            problems.append(f"{fam}: {rel} is recorded outside the manifest's directory {manifest_dir}")
        name = Path(rel).name
        expected = ARTIFACT_FILENAMES.get(fam)
        if expected is not None and name != expected:
            problems.append(f"{fam}: recorded as {name}, expected {expected}")
        elif expected is None and not name.endswith(JUDGE_REPORT_SUFFIX):
            problems.append(f"{fam}: recorded as {name}, expected *{JUDGE_REPORT_SUFFIX}")
        seen.setdefault(rel, []).append(fam)
    for rel, fams in seen.items():
        if len(fams) > 1:
            problems.append(f"artifact path {rel} is recorded for more than one family: {', '.join(fams)}")
    return problems


def identity_digest(manifest: dict) -> str:
    body = {k: v for k, v in manifest.items() if k != "chain"}
    artifacts = dict(body.get("artifacts") or {})
    for key in RECORD_DEPENDENT_FIELDS:
        if key in artifacts:
            artifacts[key] = None
    body["artifacts"] = artifacts
    return sha256_text(canonical_json(body))


def manifest_digest(manifest: dict) -> str:
    body = dict(manifest)
    chain = dict(body.get("chain") or {})
    chain["manifest_sha256"] = ""
    body["chain"] = chain
    return sha256_text(canonical_json(body))


def seal_manifest(manifest: dict, prev_sha256: str | None) -> dict:
    """Return the manifest with its chain block completed."""
    out = dict(manifest)
    out["chain"] = {"prev_sha256": prev_sha256, "identity_sha256": identity_digest(out), "manifest_sha256": ""}
    out["chain"]["manifest_sha256"] = manifest_digest(out)
    return out


def manifest_problems(manifest: dict, schema: dict | None = None) -> list[str]:
    """Schema problems plus the two digest checks. A `chain` or `artifacts`
    value that is not an object is reported as a problem rather than raised
    from the digest helpers, which assume objects (Codex, PR #27: a
    downloaded manifest with `chain: [1]` produced a traceback instead of a
    verdict)."""
    schema = schema or load_json(MANIFEST_SCHEMA)
    try:
        problems = list(validate_with_refs(manifest, schema))
    except Exception as exc:  # noqa: BLE001 - a validator failure is itself a named problem, never a crash
        problems = [f"schema validation failed: {type(exc).__name__}: {exc}"]
    chain = manifest.get("chain")
    artifacts = manifest.get("artifacts")
    if chain is not None and not isinstance(chain, dict):
        problems.append("chain is not an object; digests cannot be checked")
        return problems
    if artifacts is not None and not isinstance(artifacts, dict):
        problems.append("artifacts is not an object; digests cannot be checked")
        return problems
    chain = chain or {}
    if chain.get("identity_sha256") != identity_digest(manifest):
        problems.append("chain.identity_sha256 does not match the manifest body")
    if chain.get("manifest_sha256") != manifest_digest(manifest):
        problems.append("chain.manifest_sha256 does not match the manifest body")
    return problems


def chain_head(data_dir: Path) -> str | None:
    path = data_dir / CHAIN_FILE
    if not path.is_file():
        return None
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[-1].split()[-1] if lines else None


def chain_head_line(data_dir: Path) -> tuple[str, str] | None:
    """(relative manifest path, digest) of the chain's last line; None when
    the chain does not exist or is empty."""
    path = data_dir / CHAIN_FILE
    if not path.is_file():
        return None
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    rel, digest = lines[-1].rsplit(" ", 1)
    return rel, digest


def append_chain(data_dir: Path, manifest: dict, manifest_path: Path) -> None:
    path = data_dir / CHAIN_FILE
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{manifest_path.relative_to(data_dir).as_posix()} {manifest['chain']['manifest_sha256']}\n")


def readapt_report_problems(manifest: dict, run_dir: Path, recorded_name: str | None = None) -> list[str]:
    """A re-adapted run's manifest binds the source run's landed target cost
    sidecar by digest (`readapt.target_report`, scripts/petri_audit/readapt.py):
    it must sit in this run's own directory, under the name the ledger keys it
    by, and still digest to what was bound, so a sidecar rewritten after the
    readapt is detected. `recorded_name` is the run directory's name as the
    manifest records it, for a downloaded directory extracted under another
    folder name (default: `run_dir`'s own name). Empty for a manifest with no
    `readapt` block (every run adapted in the ordinary way)."""
    block = manifest.get("readapt")
    if block is None:
        return []
    report = block.get("target_report") if isinstance(block, dict) else None
    if not isinstance(report, dict) or not isinstance(report.get("path"), str):
        return ["readapt.target_report records no path; the landed target sidecar cannot be verified"]
    run_dir = Path(run_dir)
    name = recorded_name or run_dir.name
    expected = f"{name}/{name}.report.json"
    if report["path"] != expected:
        return [f"readapt.target_report: {report['path']} is not this run's target sidecar ({expected})"]
    fpath = run_dir / f"{name}.report.json"
    if not fpath.is_file():
        return [f"readapt.target_report: {fpath.name} is missing; the source run's target spend is no longer recorded"]
    if sha256_file(fpath) != report.get("sha256"):
        return [f"readapt.target_report: {fpath.name} does not digest to the value the readapt bound; a landed "
                "sidecar is never rewritten"]
    return []


def artifact_problems(manifest: dict, data_dir: Path, manifest_dir: str | None = None) -> list[str]:
    """Every artifact the manifest names (relative to the runs directory)
    exists and digests to its recorded value; a null path is one not yet
    written (judgments before judging). `manifest_dir` is the manifest's own
    run directory (its name under `data_dir`); when given, every artifact
    must be recorded inside it, and a re-adapted run's landed target sidecar
    must still be the bytes the readapt bound (`readapt_report_problems`)."""
    problems: list[str] = []
    artifacts = manifest.get("artifacts") or {}
    pairs = [(artifacts.get(f"{fam}_path"), artifacts.get(f"{fam}_sha256"), fam) for fam in ARTIFACT_FAMILIES]
    judge = artifacts.get("judge_of_record")
    if isinstance(judge, dict):
        pairs.append((judge.get("report_path"), judge.get("report_sha256"), "judge_of_record.report"))
    problems.extend(artifact_name_problems(pairs, manifest_dir))
    for rel, digest, fam in pairs:
        if rel is None:
            continue
        fpath = data_dir / rel
        if not fpath.is_file():
            problems.append(f"{fam}: {rel} is missing")
        elif sha256_file(fpath) != digest:
            problems.append(f"{fam}: {rel} does not digest to its recorded value")
    if manifest_dir is not None:
        problems.extend(readapt_report_problems(manifest, data_dir / manifest_dir))
    return problems


def verify_chain(data_dir: Path) -> tuple[bool, str]:
    """Every manifest the chain file names exists, digests to its recorded
    value, links to the previous line, and names only artifacts that exist
    and digest to their recorded values."""
    path = data_dir / CHAIN_FILE
    if not path.is_file():
        return True, "no chain file (no manifests yet)"
    prev: str | None = None
    for n, line in enumerate(ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()):
        rel, digest = line.rsplit(" ", 1)
        mpath = data_dir / rel
        if not mpath.is_file():
            return False, f"line {n + 1}: {rel} is missing"
        manifest = load_json(mpath)
        if manifest_digest(manifest) != digest or manifest["chain"]["manifest_sha256"] != digest:
            return False, f"line {n + 1}: {rel} does not digest to {digest}"
        if manifest["chain"]["prev_sha256"] != prev:
            return False, f"line {n + 1}: {rel} links to {manifest['chain']['prev_sha256']!r}, expected {prev!r}"
        # the chain knows where each manifest sits, so its artifacts are bound to that directory
        problems = artifact_problems(manifest, data_dir, manifest_dir=Path(rel).parent.as_posix())
        if problems:
            return False, f"line {n + 1}: {rel}: " + "; ".join(problems)
        prev = digest
    return True, f"chain intact ({prev})"


def verify_run(run_dir: Path) -> list[str]:
    """Every problem with ONE run directory taken on its own: the manifest
    exists and validates, its chain block digests to its body (identity and
    manifest digests), and every artifact it names exists beside it and
    digests to its recorded value. Needs no chain file, so a downloaded run
    directory (the dry-run exports artifact) verifies exactly like the
    committed one; the link to the previous run is the manifest's own
    `chain.prev_sha256`, which only the full chain can check (Codex, PR #27:
    the cumulative chain file in the artifact referenced runs the artifact
    did not carry)."""
    run_dir = Path(run_dir)
    mpath = run_dir / "manifest.json"
    if not mpath.is_file():
        return [f"{run_dir.name}: manifest.json is missing"]
    try:
        manifest = load_json(mpath)
    except ValueError as exc:
        return [f"{run_dir.name}: manifest.json does not parse ({exc})"]
    if not isinstance(manifest, dict):
        # valid JSON that is not an object (Codex, PR #27): a named refusal, never a traceback out of the schema check
        return [f"{run_dir.name}: manifest.json holds a {type(manifest).__name__}, not an object"]
    problems = [f"manifest: {p}" for p in manifest_problems(manifest)]
    # artifact paths are recorded as `<recorded run directory>/<file>` relative to the runs directory; the files are
    # looked up by basename under the directory given, so a downloaded artifact extracted flat under any folder name
    # verifies exactly like the committed layout (Codex, PR #27: upload-artifact roots the archive at the run
    # directory, so the extraction carries no enclosing directory); every path must still share one recorded
    # directory and name a file directly inside it
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return problems + [f"artifacts is {'absent' if artifacts is None else 'not an object'}; no artifact can be verified"]
    pairs = [(artifacts.get(f"{fam}_path"), artifacts.get(f"{fam}_sha256"), fam) for fam in ARTIFACT_FAMILIES]
    judge = artifacts.get("judge_of_record")
    if isinstance(judge, dict):
        pairs.append((judge.get("report_path"), judge.get("report_sha256"), "judge_of_record.report"))
    problems.extend(artifact_name_problems(pairs))
    recorded_dirs: set[str] = set()
    for rel, digest, fam in pairs:
        if rel is None:
            continue
        if not isinstance(rel, str):
            problems.append(f"{fam}: path is not a string")
            continue
        parts = Path(rel).parts
        # exactly two plain components (Codex, PR #27): `../x`, `/x` and `a\\b` also have two parts or one, and would
        # resolve elsewhere under the chain verifier while hashing a local basename here
        if (len(parts) != 2 or Path(rel).is_absolute()
                or any(p in (".", "..", "") or "/" in p or "\\" in p for p in parts)):
            problems.append(f"{fam}: {rel} is not recorded as <run directory>/<file>")
            continue
        recorded_dirs.add(parts[0])
        fpath = run_dir / parts[1]
        if not fpath.is_file():
            problems.append(f"{fam}: {parts[1]} is missing from the run directory")
        elif sha256_file(fpath) != digest:
            problems.append(f"{fam}: {parts[1]} does not digest to its recorded value")
    if len(recorded_dirs) > 1:
        problems.append(f"artifacts are recorded under more than one run directory: {sorted(recorded_dirs)}")
    # a re-adapted run binds its landed target sidecar too; checked under the recorded directory name, since a
    # downloaded artifact may be extracted under any folder name (the other artifacts are looked up by basename)
    if manifest.get("readapt") is not None:
        recorded = next(iter(recorded_dirs)) if len(recorded_dirs) == 1 else run_dir.name
        problems.extend(readapt_report_problems(manifest, run_dir, recorded_name=recorded))
    return problems


def replace_chain_head(data_dir: Path, manifest_path: Path, old_digest: str, new_digest: str) -> None:
    """Rewrite the chain's last line for a manifest being resealed. Only the
    head may be resealed: a later manifest links to this one's digest, and
    changing an interior line would break every successor. Written atomically
    (temp file, then rename)."""
    path = data_dir / CHAIN_FILE
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rel = manifest_path.resolve().relative_to(data_dir.resolve()).as_posix()
    if not lines or lines[-1] != f"{rel} {old_digest}":
        raise ValueError(f"{rel} is not the chain head; only the head manifest can be resealed")
    lines[-1] = f"{rel} {new_digest}"
    _atomic_write_text(path, "".join(ln + "\n" for ln in lines))


def bound_prefix_intact(path: Path, recorded_sha256: str) -> bool:
    """Whether the bytes a manifest bound (`recorded_sha256`) are still the
    start of an append-only file: exactly the file, or a line-aligned prefix
    of it. The recovery path for a judgments file a previous invocation
    appended to and then failed to bind."""
    if not path.is_file():
        return False
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for line in fh:
            h.update(line)
            if h.hexdigest() == recorded_sha256:
                return True
    return False


def reseal_problems(run_dir: Path, report_path: Path | None = None) -> list[str]:
    """Why the run's manifest cannot be resealed, established before the judge
    spends anything (Codex round 5: `judge` used to append rows and rewrite
    the sidecar first and learn at binding time that the run was no longer
    the chain head, leaving the manifest's recorded digests stale). Empty
    when: the chain's last line names the manifest; the manifest digests to
    its own seal (the line's digest may differ only in the state a reseal
    leaves when interrupted between the manifest write and the chain write,
    which the next binding repairs); the immutable artifacts it binds (the
    sanitised log, the transcripts, the rule outcomes) digest to their
    recorded values; and a bound judgments file still starts with the bytes
    that were bound (round 6: a judge could otherwise spend against altered
    transcripts, and the reseal would bless altered rows). The judgments
    file may have grown past its bound prefix, the state a previous
    invocation leaves when it appended rows and then failed to bind, but
    only when the judge sidecar that invocation wrote records the file's
    current digest (round 7); the judge report's own digest is not checked
    here, since every invocation regenerates it (`verify_chain` checks it
    after binding). `report_path` names the sidecar the caller is about to
    bind, consulted first for that digest."""
    run_dir = Path(run_dir)
    data_dir = run_dir.parent
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return [f"{manifest_path} is missing"]
    head = chain_head_line(data_dir)
    if head is None:
        return [f"{data_dir / CHAIN_FILE} is missing or empty"]
    rel = manifest_path.resolve().relative_to(data_dir.resolve()).as_posix()
    problems: list[str] = []
    if head[0] != rel:
        problems.append(f"{rel} is not the chain head ({head[0]} is); only the head manifest can be resealed")
    manifest = load_json(manifest_path)
    if manifest_digest(manifest) != manifest["chain"]["manifest_sha256"]:
        problems.append(f"{rel} does not digest to its own seal")
    artifacts = manifest.get("artifacts") or {}
    for fam in ARTIFACT_FAMILIES:
        if fam == "judgments":
            continue
        art_rel, digest = artifacts.get(f"{fam}_path"), artifacts.get(f"{fam}_sha256")
        if art_rel is None:
            continue
        fpath = data_dir / art_rel
        if not fpath.is_file():
            problems.append(f"{fam}: {art_rel} is missing")
        elif sha256_file(fpath) != digest:
            problems.append(f"{fam}: {art_rel} does not digest to its recorded value; a judge must not run against "
                            "altered records")
    # the judgments file: bound and unchanged, or every row past what was bound authenticated by the judge sidecar
    # the invocation that wrote them left behind (Codex round 7: a prefix check alone accepted any append)
    bound_rel, bound_digest = artifacts.get("judgments_path"), artifacts.get("judgments_sha256")
    if bound_rel is not None:
        jpath = data_dir / bound_rel
        if not jpath.is_file():
            problems.append(f"judgments: {bound_rel} is missing")
        elif sha256_file(jpath) != bound_digest:
            if not bound_prefix_intact(jpath, bound_digest):
                problems.append(f"judgments: {bound_rel} no longer starts with the bytes that were bound")
            else:
                problems.extend(_unbound_rows_problems(run_dir, manifest, jpath, "grew past its bound prefix", report_path))
    elif (run_dir / "judgments.jsonl").is_file():
        problems.extend(_unbound_rows_problems(run_dir, manifest, run_dir / "judgments.jsonl", "exists but is not bound",
                                               report_path))
    return problems


def _unbound_rows_problems(run_dir: Path, manifest: dict, jpath: Path, why: str, report_path: Path | None) -> list[str]:
    """Rows not covered by the manifest's binding are accepted only when the
    run's judge sidecar (the one being bound, the bound report path, or
    `<run>.judge.report.json`) records the current file's digest as
    `judgments_sha256`: every judge invocation, an aborted one included,
    writes that after its last row, so a file edited or appended outside an
    invocation never matches."""
    data_dir = run_dir.parent
    judge = (manifest.get("artifacts") or {}).get("judge_of_record") or {}
    candidates = [run_dir / f"{run_dir.name}.judge.report.json"]
    if judge.get("report_path"):
        candidates.insert(0, data_dir / judge["report_path"])
    if report_path is not None:
        candidates.insert(0, Path(report_path))
    sidecar_path = next((c for c in candidates if c.is_file()), None)
    if sidecar_path is None:
        return [f"judgments: {jpath.name} {why} and no judge sidecar records it; rows written outside a judge "
                "invocation cannot be authenticated"]
    try:
        recorded = load_json(sidecar_path).get("judgments_sha256")
    except (OSError, ValueError):
        recorded = None
    if recorded != sha256_file(jpath):
        return [f"judgments: {jpath.name} {why} and the judge sidecar {sidecar_path.name} records a different digest "
                "for it; rows written outside a judge invocation cannot be authenticated"]
    return []


def bind_judgments(run_dir: Path, *, judgments_path: Path, report_path: Path, judge_of_record: dict) -> dict:
    """After the judge of record has written `judgments.jsonl` and its report,
    record both in the run's manifest (path, digest, provenance), reseal it
    with the same `prev_sha256`, assert the identity digest is unchanged (so
    every transcript bound to it stays bound), validate, write the manifest,
    then replace the chain head line. Raises before writing anything when the
    run is not resealable (`reseal_problems`) or the reseal fails validation.
    The manifest is written before the chain line that references it, each
    atomically, so an interruption between the two leaves a manifest that
    digests to its own seal under a stale head line, a state `reseal_problems`
    accepts and the next binding repairs (Codex round 5: the reverse order
    left a chain line naming a digest no manifest had)."""
    run_dir = Path(run_dir)
    data_dir = run_dir.parent
    manifest_path = run_dir / "manifest.json"
    problems = reseal_problems(run_dir, report_path=report_path)
    if problems:
        raise ValueError("; ".join(problems))
    head = chain_head_line(data_dir)
    if head is None:                                   # reseal_problems already refused this; defensive, not reachable
        raise ValueError(f"{data_dir / CHAIN_FILE} is missing or empty")
    manifest = load_json(manifest_path)
    before_identity = manifest["chain"]["identity_sha256"]
    before_digest = head[1]                            # the line's digest, which equals the manifest's unless interrupted

    def rel(p: Path) -> str:
        return p.resolve().relative_to(data_dir.resolve()).as_posix()

    manifest["artifacts"]["judgments_path"] = rel(judgments_path)
    manifest["artifacts"]["judgments_sha256"] = sha256_file(judgments_path)
    manifest["artifacts"]["judge_of_record"] = {**judge_of_record, "report_path": rel(report_path),
                                                "report_sha256": sha256_file(report_path)}
    sealed = seal_manifest(manifest, manifest["chain"]["prev_sha256"])
    if sealed["chain"]["identity_sha256"] != before_identity:
        raise ValueError("binding the judgments changed the run's identity digest; nothing written")
    problems = manifest_problems(sealed)
    if problems:
        raise ValueError("manifest does not validate after binding the judgments: " + "; ".join(problems[:8]))
    write_manifest(manifest_path, sealed)
    replace_chain_head(data_dir, manifest_path, before_digest, sealed["chain"]["manifest_sha256"])
    return sealed


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file in the same directory and rename, so a reader
    never sees a partial file and an interruption leaves the old one."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_manifest(path: Path, manifest: dict) -> None:
    _atomic_write_text(Path(path), json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
