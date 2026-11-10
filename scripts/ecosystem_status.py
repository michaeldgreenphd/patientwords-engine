"""Read-only status of the repositories and pins in ``data/ecosystem/repositories.v1.json``.

Usage (from any directory)::

    python scripts/ecosystem_status.py                       # offline; sibling checkouts next to the engine
    python scripts/ecosystem_status.py --root DIR            # clones live in DIR/<repository id>
    python scripts/ecosystem_status.py --path patientwords=/some/where --path NAME=DIR
    python scripts/ecosystem_status.py --remote              # also compare remote tips (read-only network)
    python scripts/ecosystem_status.py --json                # machine output
    python scripts/ecosystem_status.py --strict-self --fail-on-dirty   # stricter counting, see below

What it reports. For each manifest entry whose checkout exists: the recorded head against the local
``HEAD``, whether the working tree is dirty, whether ``origin`` is the manifest URL, and the entry's source
facts (a literal the manifest says the source holds, for example the version a fork declares). For each
consumed pin: the pointer file is read again and the line says ``pin matches manifest`` or prints both
values. With ``--remote`` it asks ``git ls-remote <url> HEAD`` for the repository and its upstream and says
whether the recorded head is still the remote head and whether the fork tip equals the upstream tip.

Read-only guarantee. This command never clones, fetches, pulls, checks out, installs or writes a file. The
only git verbs it runs are ``rev-parse``, ``status``, ``remote get-url`` and, with ``--remote``,
``ls-remote``; ``_git`` refuses any other verb before a process starts, and ``status`` runs with
``GIT_OPTIONAL_LOCKS=0`` so it does not refresh the index. ``tests/test_ecosystem_manifest.py`` replaces
``subprocess.run`` with a guard that fails on any other command.

Limits. A remote comparison compares tips only. It cannot count commits ahead or behind without history,
and a shallow clone has none. A checkout that is absent is listed as absent and is not a difference. A
dirty working tree is reported and counted only with ``--fail-on-dirty``. The
entry that holds the manifest (the engine) can never record the commit that contains the manifest, so its
head comparison is printed but counted only with ``--strict-self``.

Checkout lookup, first match wins: ``--path ID=DIR``; ``--root DIR`` when ``DIR/<id>`` exists; the entry's
``default_sibling_path`` resolved against the engine root (not the current directory). The engine entry is
always the checkout that holds this script (``--engine-root`` names another one; tests use it). A directory
without its own ``.git`` entry is reported as not a checkout, so git never walks up into an enclosing
repository.

Exit codes: 0 every compared value matches the manifest; 1 at least one recorded value differs; 2 the
manifest is unreadable, fails its schema or fails a vocabulary or consistency rule.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.frontend_contract_schema import check_schema_subset
except ImportError:  # invoked as `python scripts/ecosystem_status.py`
    from frontend_contract_schema import check_schema_subset

ENGINE = Path(__file__).resolve().parents[1]
MANIFEST = ENGINE / "data" / "ecosystem" / "repositories.v1.json"
SCHEMA = ENGINE / "schemas" / "ecosystem" / "repositories.v1.schema.json"
SCHEMA_VERSION = "patientwords.ecosystem/1"
REPORT_VERSION = "patientwords.ecosystem-status/1"

GROUPS = ("core", "method_fork", "outside_the_seven")
CONSUMPTION_TYPES = ("source_checkout", "installed_distribution", "fitted_artifact", "model_weights",
                     "hosted_service", "generated_files", "none")
POINTER_KINDS = ("constraints_line", "json_pointer", "text_contains")
RELATIONS = ("same_repository", "no_execution_pin", "not_executed_by_engine", "pin_is_older_source",
             "pin_is_separate_distribution")
RELATIONS_WITH_PIN = ("pin_is_older_source", "pin_is_separate_distribution")
ADAPTER_STATES = ("active", "manual", "staged", "historical", "added_in_change_set_20261110")
VOCABULARIES = {"group": GROUPS, "consumption_type": CONSUMPTION_TYPES, "pointer_kind": POINTER_KINDS,
                "head_vs_pin_relation": RELATIONS, "adapter_state": ADAPTER_STATES}

# verb -> allowed first argument (None: any). Nothing here writes to a repository or to the network.
ALLOWED_GIT = {"rev-parse": None, "status": None, "ls-remote": None, "remote": ("get-url",)}
COMMIT = re.compile(r"[0-9a-f]{40}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIPS_ONLY = ("A remote comparison reads tips only. It cannot count commits ahead or behind without history, "
             "and it does not fetch any.")


class ManifestError(Exception):
    """The manifest cannot be used: unreadable, structurally invalid or inconsistent."""


def load_json(path: Path) -> Any:
    """Parse one JSON file, turning any read or parse failure into ManifestError."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{path}: {exc}") from exc


def validate_manifest(doc: Any, schema: dict) -> list[str]:
    """Return every structural, vocabulary and consistency problem of a manifest (empty list: valid).

    The schema covers structure. The rules here are the ones the schema dialect cannot express: exact
    vocabularies, 40-hex commits, one entry holding the manifest, and the separation of the latest source
    head from the tested execution pin.
    """
    errors: list[str] = []
    try:
        check_schema_subset(lambda _artifact, path, message: errors.append(f"{path}: {message}"),
                            "ecosystem manifest", doc, schema)
    except (ValueError, KeyError, TypeError) as exc:
        return [f"schema could not be applied: {exc}"]
    if errors:
        return errors
    if doc["schema_version"] != SCHEMA_VERSION:
        errors.append(f"$.schema_version: expected {SCHEMA_VERSION!r}, found {doc['schema_version']!r}")
    if not DATE.fullmatch(doc["as_of"]):
        errors.append("$.as_of: expected YYYY-MM-DD")
    for name, values in VOCABULARIES.items():
        if doc["vocabularies"].get(name) != list(values):
            errors.append(f"$.vocabularies.{name}: differs from the vocabulary enforced in code")
    ids = [entry["id"] for entry in doc["repositories"]] + [entry["id"] for entry in doc["external_services"]]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate id {dup!r}")
    holders = [entry["id"] for entry in doc["repositories"] if entry["holds_this_manifest"]]
    if len(holders) != 1:
        errors.append(f"exactly one repository must hold the manifest; found {holders}")
    for entry in doc["repositories"]:
        errors.extend(_repository_problems(entry))
    for service in doc["external_services"]:
        errors.extend(_consumed_problems(f"service {service['id']}", service["consumed_by_engine"]))
    return errors


def _repository_problems(entry: dict) -> list[str]:
    where = f"repository {entry['id']}"
    errors: list[str] = []
    if entry["group"] not in GROUPS:
        errors.append(f"{where}: unknown group {entry['group']!r}")
    if not entry["url"].startswith("https://github.com/"):
        errors.append(f"{where}: url must be an https://github.com/ URL")
    if entry["visibility"]["value"] not in ("public", "private"):
        errors.append(f"{where}: visibility must be public or private")
    sibling = entry["default_sibling_path"]
    if sibling is not None and (not sibling.startswith("../") or "/" in sibling[3:] or sibling == "../"):
        errors.append(f"{where}: default_sibling_path must be ../<directory> or null")
    head = entry["recorded_head"]
    commit = head["commit"]
    if commit is not None and not COMMIT.fullmatch(commit):
        errors.append(f"{where}: recorded_head.commit is not 40 lowercase hex characters")
    if not DATE.fullmatch(head["recorded_utc_date"]):
        errors.append(f"{where}: recorded_head.recorded_utc_date must be YYYY-MM-DD")
    relation = entry["upstream_relation"]
    if (entry["fork_of"] is None) != (relation is None):
        errors.append(f"{where}: upstream_relation must be present exactly when fork_of is set")
    if relation is not None:
        if relation["upstream_url"] != entry["fork_of"]:
            errors.append(f"{where}: upstream_relation.upstream_url differs from fork_of")
        for key in ("ahead", "behind"):
            if relation[key] is not None and relation[key] < 0:
                errors.append(f"{where}: upstream_relation.{key} is negative")
        if not DATE.fullmatch(relation["as_of"]):
            errors.append(f"{where}: upstream_relation.as_of must be YYYY-MM-DD")
    errors.extend(_consumed_problems(where, entry["consumed_by_engine"]))
    errors.extend(_head_vs_pin_problems(where, entry))
    for adapter in entry["adapters"]:
        if adapter["state"] not in ADAPTER_STATES:
            errors.append(f"{where}: adapter {adapter['path']}: unknown state {adapter['state']!r}")
        if _escapes(adapter["path"]):
            errors.append(f"{where}: adapter path {adapter['path']!r} must be relative to the engine root")
    for fact in entry["source_facts"]:
        if _escapes(fact["file"]):
            errors.append(f"{where}: source fact file {fact['file']!r} must be relative to the checkout")
    return errors


def _head_vs_pin_problems(where: str, entry: dict) -> list[str]:
    """The latest source head and the tested execution pin are two statements and must not be merged."""
    errors: list[str] = []
    block = entry["head_vs_pin"]
    if block["latest_source_head"] != entry["recorded_head"]["commit"]:
        errors.append(f"{where}: head_vs_pin.latest_source_head differs from recorded_head.commit")
    if block["relation"] not in RELATIONS:
        errors.append(f"{where}: unknown head_vs_pin.relation {block['relation']!r}")
        return errors
    tested = block["tested_execution_pin"]
    if block["relation"] in RELATIONS_WITH_PIN:
        values = [str(p["value"]) for item in entry["consumed_by_engine"] for p in item["pins"]
                  if isinstance(p["value"], str)]
        if not tested:
            errors.append(f"{where}: relation {block['relation']} needs a tested_execution_pin")
        elif tested == block["latest_source_head"]:
            errors.append(f"{where}: tested_execution_pin repeats the latest source head")
        elif not any(value in tested for value in values):
            errors.append(f"{where}: tested_execution_pin names no value from consumed_by_engine pins")
    elif tested is not None:
        errors.append(f"{where}: relation {block['relation']} must leave tested_execution_pin null")
    return errors


def _consumed_problems(where: str, consumed: list[dict]) -> list[str]:
    errors: list[str] = []
    if not consumed:
        errors.append(f"{where}: consumed_by_engine is empty; state type 'none' explicitly")
    for item in consumed:
        if item["type"] not in CONSUMPTION_TYPES:
            errors.append(f"{where}: unknown consumption type {item['type']!r}")
        if item["type"] == "none" and item["pins"]:
            errors.append(f"{where}: type 'none' cannot carry pins")
        for pin in item["pins"]:
            pointer = pin["pointer"]
            need = {"constraints_line": "package", "json_pointer": "pointer", "text_contains": "text"}
            if pointer["kind"] not in POINTER_KINDS:
                errors.append(f"{where}: pin {pin['name']!r}: unknown pointer kind {pointer['kind']!r}")
            elif need[pointer["kind"]] not in pointer:
                errors.append(f"{where}: pin {pin['name']!r}: pointer lacks {need[pointer['kind']]!r}")
            if _escapes(pin["pointer_file"]):
                errors.append(f"{where}: pin {pin['name']!r}: pointer_file must be relative to the engine root")
    return errors


def _escapes(relative: str) -> bool:
    path = Path(relative)
    return path.is_absolute() or ".." in path.parts or not relative


def read_pointer(engine_root: Path, pin: dict) -> tuple[bool, Any, str]:
    """Read what a pin's pointer file says now: (readable, value, detail). Never raises on a bad file."""
    path = engine_root / pin["pointer_file"]
    pointer = pin["pointer"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, None, f"{pin['pointer_file']}: unreadable ({exc.__class__.__name__})"
    if pointer["kind"] == "constraints_line":
        prefix = pointer["package"] + "=="
        lines = [line.strip() for line in text.splitlines() if line.strip().startswith(prefix)]
        if len(lines) != 1:
            return False, None, f"{pin['pointer_file']}: {len(lines)} lines start with {prefix!r}; expected 1"
        return True, lines[0][len(prefix):], f"{pin['pointer_file']}: {lines[0]}"
    if pointer["kind"] == "json_pointer":
        try:
            value: Any = json.loads(text)
            for part in pointer["pointer"].split("/")[1:]:
                part = part.replace("~1", "/").replace("~0", "~")
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return False, None, f"{pin['pointer_file']}: {pointer['pointer']} not found ({exc.__class__.__name__})"
        return True, value, f"{pin['pointer_file']}: {pointer['pointer']} = {json.dumps(value)}"
    present = pointer["text"] in text
    return True, pin["value"] if present else None, (
        f"{pin['pointer_file']}: literal {'present' if present else 'absent'}: {pointer['text']}")


def check_pins(doc: dict, engine_root: Path) -> list[dict]:
    """Compare every consumed pin in the manifest with its pointer file. One row per pin."""
    rows: list[dict] = []
    owners = [(e["id"], e["consumed_by_engine"]) for e in doc["repositories"]]
    owners += [(s["id"], s["consumed_by_engine"]) for s in doc["external_services"]]
    for owner, consumed in owners:
        for item in consumed:
            for pin in item["pins"]:
                readable, found, detail = read_pointer(engine_root, pin)
                matches = readable and found == pin["value"] and type(found) is type(pin["value"])
                rows.append({"owner": owner, "type": item["type"], "name": pin["name"], "manifest": pin["value"],
                             "pointer_file": pin["pointer_file"], "found": found, "readable": readable,
                             "matches": matches, "detail": detail})
    return rows


def _git(args: list[str], cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run one allowlisted, read-only git command. Any other verb raises before a process starts."""
    verb = args[0] if args else ""
    if verb not in ALLOWED_GIT:
        raise PermissionError(f"ecosystem_status is read-only: git verb {verb!r} is not allowed")
    first = ALLOWED_GIT[verb]
    if first is not None and (len(args) < 2 or args[1] not in first):
        raise PermissionError(f"ecosystem_status is read-only: git {verb} {args[1:2]} is not allowed")
    command = ["git"] + (["-C", str(cwd)] if cwd is not None else []) + args
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def locate(entry: dict, engine_root: Path, root: Path | None, overrides: dict[str, Path]) -> tuple[Path | None, str]:
    """Where an entry's checkout is looked for, and which rule chose it."""
    if entry["holds_this_manifest"]:
        return engine_root, "the checkout that holds the manifest"
    if entry["id"] in overrides:
        return overrides[entry["id"]], "--path"
    if root is not None and (root / entry["id"]).is_dir():
        return root / entry["id"], "--root"
    if entry["default_sibling_path"] is None:
        return None, "no sibling path is defined"
    return (engine_root / entry["default_sibling_path"]).resolve(), "default sibling path"


def _same_repository_url(a: str, b: str) -> bool:
    def norm(url: str) -> str:
        url = url.strip().rstrip("/")
        url = re.sub(r"^git@github\.com:", "https://github.com/", url)
        return url[:-4].lower() if url.endswith(".git") else url.lower()
    return norm(a) == norm(b)


def checkout_status(entry: dict, path: Path | None, how: str) -> dict:
    """Local, offline state of one checkout. Runs rev-parse, status and remote get-url only."""
    recorded = entry["recorded_head"]["commit"]
    row: dict[str, Any] = {"id": entry["id"], "group": entry["group"], "path": str(path) if path else None,
                           "located_by": how, "recorded_head": recorded, "holds_this_manifest":
                           entry["holds_this_manifest"],
                           "head_moves_with_operations": bool(entry.get("head_moves_with_operations")),
                           "relation": entry["head_vs_pin"]["relation"],
                           "tested_execution_pin": entry["head_vs_pin"]["tested_execution_pin"],
                           "state": "absent", "local_head": None, "head_matches": None, "dirty": None,
                           "dirty_paths": None, "origin": None, "origin_matches": None, "source_facts": []}
    if path is None or not path.is_dir():
        return row
    if not (path / ".git").exists():  # never let git walk up into an enclosing repository
        row["state"] = "not_a_git_checkout"
        return row
    head = _git(["rev-parse", "HEAD"], cwd=path)
    local = head.stdout.strip()
    if head.returncode != 0 or not COMMIT.fullmatch(local):
        row["state"] = "not_a_git_checkout"
        return row
    row.update(state="present", local_head=local)
    row["head_matches"] = None if recorded is None else local == recorded
    status = _git(["status", "--porcelain"], cwd=path)
    if status.returncode == 0:
        changed = [line for line in status.stdout.splitlines() if line.strip()]
        row.update(dirty=bool(changed), dirty_paths=len(changed))
    origin = _git(["remote", "get-url", "origin"], cwd=path)
    if origin.returncode == 0 and origin.stdout.strip():
        row.update(origin=origin.stdout.strip(),
                   origin_matches=_same_repository_url(origin.stdout.strip(), entry["url"]))
    for fact in entry["source_facts"]:
        try:
            holds: bool | None = fact["text"] in (path / fact["file"]).read_text(encoding="utf-8")
        except OSError:
            holds = None
        row["source_facts"].append({"name": fact["name"], "value": fact["value"], "file": fact["file"],
                                    "matches": holds})
    return row


def _remote_tip(url: str) -> tuple[str | None, str | None]:
    try:
        done = _git(["ls-remote", url, "HEAD"], timeout=60)
    except subprocess.TimeoutExpired:
        return None, "timed out"
    for line in done.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "HEAD" and COMMIT.fullmatch(parts[0]):
            return parts[0], None
    return None, (done.stderr.strip().splitlines() or ["no HEAD line returned"])[-1]


def remote_status(entry: dict) -> dict:
    """Remote tips of an entry and its upstream, read with ``git ls-remote``. Compares tips only."""
    recorded = entry["recorded_head"]["commit"]
    tip, error = _remote_tip(entry["url"])
    row: dict[str, Any] = {"id": entry["id"], "url": entry["url"], "remote_head": tip, "error": error,
                           "recorded_is_remote_head": None if tip is None or recorded is None else tip == recorded,
                           "upstream_url": entry["fork_of"], "upstream_head": None, "upstream_error": None,
                           "fork_tip_equals_upstream_tip": None, "manifest_ahead": None, "manifest_behind": None}
    if entry["fork_of"]:
        relation = entry["upstream_relation"]
        up, up_error = _remote_tip(entry["fork_of"])
        row.update(upstream_head=up, upstream_error=up_error, manifest_ahead=relation["ahead"],
                   manifest_behind=relation["behind"])
        if tip is not None and up is not None:
            row["fork_tip_equals_upstream_tip"] = tip == up
    return row


def build_report(doc: dict, engine_root: Path, *, root: Path | None = None,
                 overrides: dict[str, Path] | None = None, remote: bool = False, strict_self: bool = False,
                 fail_on_dirty: bool = False, manifest_name: str | None = None) -> dict:
    """Assemble the whole status. ``differences`` lists every recorded value that does not hold now."""
    differences: list[str] = []
    not_checked: list[str] = []
    checkouts = []
    for entry in doc["repositories"]:
        path, how = locate(entry, engine_root, root, overrides or {})
        row = checkout_status(entry, path, how)
        checkouts.append(row)
        # A repository that receives operational commits every day (the engine's CI outputs, the site's data
        # publishes, the traces mirror) has a recorded head that is the head inspected on the recorded date.
        # Its difference is printed and counted only with --strict-self, like the manifest holder's.
        counted = strict_self or not (row["holds_this_manifest"] or row["head_moves_with_operations"])
        if row["state"] == "absent":
            not_checked.append(f"{row['id']}: checkout absent ({how})")
        elif row["state"] == "not_a_git_checkout":
            not_checked.append(f"{row['id']}: {row['path']} is not a git checkout")
        else:
            if row["head_matches"] is False and counted:
                differences.append(f"{row['id']}: local HEAD {row['local_head']} differs from recorded head "
                                   f"{row['recorded_head']}")
            if row["origin_matches"] is False:
                differences.append(f"{row['id']}: origin {row['origin']} is not the manifest url")
            if row["dirty"] and fail_on_dirty:
                differences.append(f"{row['id']}: working tree has {row['dirty_paths']} changed path(s)")
            for fact in row["source_facts"]:
                if fact["matches"] is not True:
                    differences.append(f"{row['id']}: source fact {fact['name']!r} ({fact['value']}) not found "
                                       f"in {fact['file']}")
    pins = check_pins(doc, engine_root)
    for pin in pins:
        if not pin["matches"]:
            differences.append(f"{pin['owner']}: pin {pin['name']!r}: manifest {json.dumps(pin['manifest'])}, "
                               f"pointer file says {pin['detail']}")
    remotes = []
    if remote:
        for entry in doc["repositories"]:
            if entry["visibility"]["value"] == "private":
                not_checked.append(f"{entry['id']}: private repository; remote not queried")
                continue
            row = remote_status(entry)
            remotes.append(row)
            counted = strict_self or not (entry["holds_this_manifest"] or entry.get("head_moves_with_operations"))
            if row["remote_head"] is None:
                not_checked.append(f"{row['id']}: remote unreachable ({row['error']})")
            elif row["recorded_is_remote_head"] is False and counted:
                differences.append(f"{row['id']}: recorded head is not the remote head ({row['remote_head']})")
            if row["upstream_url"] and row["upstream_head"] is None:
                not_checked.append(f"{row['id']}: upstream unreachable ({row['upstream_error']})")
            if (row["fork_tip_equals_upstream_tip"] is False and row["manifest_ahead"] == 0
                    and row["manifest_behind"] == 0):
                differences.append(f"{row['id']}: manifest records the fork level with its upstream, but the "
                                   f"tips differ (upstream {row['upstream_head']})")
    return {"schema_version": REPORT_VERSION,
            "manifest": manifest_name or MANIFEST.relative_to(ENGINE).as_posix(),
            "manifest_as_of": doc["as_of"], "mode": "remote" if remote else "offline",
            "read_only": True, "repositories": checkouts, "pins": pins, "remotes": remotes,
            "differences": differences, "not_checked": not_checked,
            "note": TIPS_ONLY if remote else "Offline: no network call was made.",
            "exit_code": 1 if differences else 0}


def _short(commit: str | None) -> str:
    return commit[:12] if commit else "none recorded"


def render_text(report: dict) -> str:
    """The human-readable form of a report."""
    out = [f"ecosystem status ({report['mode']}; manifest {report['manifest']} as of {report['manifest_as_of']})"]
    pins_by_owner: dict[str, list[dict]] = {}
    for pin in report["pins"]:
        pins_by_owner.setdefault(pin["owner"], []).append(pin)
    remotes = {row["id"]: row for row in report["remotes"]}
    for row in report["repositories"]:
        out.append("")
        out.append(f"{row['id']}  [{row['group']}]")
        if row["state"] == "absent":
            where = f"{row['located_by']}: {row['path']}" if row["path"] else row["located_by"]
            out.append(f"  checkout       absent ({where}); recorded head {_short(row['recorded_head'])}")
        elif row["state"] == "not_a_git_checkout":
            out.append(f"  checkout       {row['path']} is not a git checkout")
        else:
            out.append(f"  checkout       {row['path']} ({row['located_by']})")
            if row["head_matches"] is None:
                verdict = "no head recorded in the manifest"
            elif row["head_matches"]:
                verdict = "head matches manifest"
            elif row["holds_this_manifest"]:
                verdict = "DIFFERS (expected: this repository holds the manifest and cannot record its own commit)"
            elif row["head_moves_with_operations"]:
                verdict = ("DIFFERS (expected: this repository receives operational commits; the recorded head "
                           "is the head inspected on the recorded date)")
            else:
                verdict = "DIFFERS"
            out.append(f"  head           recorded {_short(row['recorded_head'])}  local {_short(row['local_head'])}"
                       f"  : {verdict}")
            dirty = "unknown" if row["dirty"] is None else (
                f"dirty ({row['dirty_paths']} changed path(s))" if row["dirty"] else "clean")
            out.append(f"  working tree   {dirty}")
            if row["origin"] is not None:
                out.append("  origin         " + ("matches manifest url" if row["origin_matches"]
                                                  else f"DIFFERS: {row['origin']}"))
            for fact in row["source_facts"]:
                state = {True: "matches", False: "DIFFERS", None: "DIFFERS (file unreadable)"}[fact["matches"]]
                out.append(f"  source fact    {fact['name']} = {fact['value']} : {state} ({fact['file']})")
        for pin in pins_by_owner.get(row["id"], []):
            out.append(_pin_line(pin))
        out.append(f"  head vs pin    {row['relation']}; tested execution pin: "
                   f"{row['tested_execution_pin'] or 'none'}")
        if row["id"] in remotes:
            out.extend(_remote_lines(remotes[row["id"]]))
    services = [owner for owner in pins_by_owner if owner not in {r["id"] for r in report["repositories"]}]
    for owner in services:
        out.append("")
        out.append(f"{owner}  [external service]")
        out.extend(_pin_line(pin) for pin in pins_by_owner[owner])
    out.append("")
    out.append(report["note"])
    if report["not_checked"]:
        out.append(f"not checked ({len(report['not_checked'])}):")
        out.extend(f"  - {line}" for line in report["not_checked"])
    if report["differences"]:
        out.append(f"differences ({len(report['differences'])}):")
        out.extend(f"  - {line}" for line in report["differences"])
    else:
        out.append("differences: none")
    out.append(f"exit {report['exit_code']}")
    return "\n".join(out)


def _pin_line(pin: dict) -> str:
    verdict = "pin matches manifest" if pin["matches"] else f"DIFFERS from manifest {json.dumps(pin['manifest'])}"
    return f"  pin            {pin['name']} [{pin['type']}] : {verdict} ({pin['detail']})"


def _remote_lines(row: dict) -> list[str]:
    lines = []
    if row["remote_head"] is None:
        lines.append(f"  remote         unreachable ({row['error']})")
    else:
        verdict = {True: "recorded head is the remote head", False: "recorded head is NOT the remote head",
                   None: "no head recorded"}[row["recorded_is_remote_head"]]
        lines.append(f"  remote         HEAD {_short(row['remote_head'])} : {verdict}")
    if row["upstream_url"]:
        if row["upstream_head"] is None:
            lines.append(f"  upstream       unreachable ({row['upstream_error']})")
        elif row["fork_tip_equals_upstream_tip"] is None:
            lines.append(f"  upstream       HEAD {_short(row['upstream_head'])} : fork tip unknown")
        elif row["fork_tip_equals_upstream_tip"]:
            lines.append(f"  upstream       HEAD {_short(row['upstream_head'])} : fork tip equals upstream tip")
        else:
            counts = [f"{key}={'not recorded' if value is None else value}"
                      for key, value in (("ahead", row["manifest_ahead"]), ("behind", row["manifest_behind"]))]
            lines.append(f"  upstream       HEAD {_short(row['upstream_head'])} : tips differ; manifest records "
                         f"{', '.join(counts)}; tips alone cannot confirm either count")
    return lines


def _parse_overrides(pairs: list[str], known: set[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not value or name not in known:
            raise SystemExit(f"ecosystem_status: --path wants ID=DIR with ID one of {sorted(known)}; got {pair!r}")
        overrides[name] = Path(value).expanduser().resolve()
    return overrides


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. Returns the exit code documented in the module docstring."""
    parser = argparse.ArgumentParser(description="Read-only status of the ecosystem manifest. Never clones, "
                                                 "fetches, pulls, installs or writes.")
    parser.add_argument("--manifest", default=None, help="manifest to read (default: the committed one)")
    parser.add_argument("--engine-root", default=str(ENGINE),
                        help="checkout that holds the manifest; pointer files are read from it (default: this one)")
    parser.add_argument("--root", default=None, help="directory that holds the clones as DIR/<repository id>")
    parser.add_argument("--path", action="append", default=[], metavar="ID=DIR",
                        help="checkout location for one repository id; repeatable")
    parser.add_argument("--remote", action="store_true",
                        help="also run git ls-remote for each public repository and its upstream (tips only)")
    parser.add_argument("--strict-self", action="store_true",
                        help="count a head difference of the repository that holds the manifest")
    parser.add_argument("--fail-on-dirty", action="store_true", help="count a dirty working tree as a difference")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    engine_root = Path(args.engine_root).expanduser().resolve()
    manifest = Path(args.manifest) if args.manifest else engine_root / MANIFEST.relative_to(ENGINE)
    try:
        doc = load_json(manifest)
        problems = validate_manifest(doc, load_json(SCHEMA))
    except ManifestError as exc:
        problems, doc = [str(exc)], None
    if problems:
        if args.json:
            print(json.dumps({"schema_version": REPORT_VERSION, "status": "malformed_manifest",
                              "problems": problems, "exit_code": 2}, indent=2))
        else:
            print("ecosystem_status: malformed manifest, nothing compared:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        return 2
    overrides = _parse_overrides(args.path, {entry["id"] for entry in doc["repositories"]})
    root = Path(args.root).expanduser().resolve() if args.root else None
    try:
        shown = manifest.resolve().relative_to(engine_root).as_posix()
    except ValueError:
        shown = str(manifest)
    report = build_report(doc, engine_root, root=root, overrides=overrides, remote=args.remote,
                          strict_self=args.strict_self, fail_on_dirty=args.fail_on_dirty, manifest_name=shown)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
