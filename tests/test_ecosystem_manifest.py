"""The ecosystem manifest and its read-only status command.

Three things are held here. The committed manifest validates and cannot drift from the real pins: every
pin it records is read again from its pointer file (``constraints.txt``, the Petri lock, the dated source
receipts). Every repository entry keeps its latest source head apart from the pin the engine has executed.
And ``scripts/ecosystem_status.py`` is read-only: on a synthetic layout of tiny git repositories it reports
matching, differing, dirty and missing checkouts with the documented exit codes, runs no git verb outside
``rev-parse``, ``status``, ``ls-remote`` and ``remote``, and leaves every byte of the layout unchanged.

Nothing here needs the network or a sibling checkout. Remote tips are supplied by a fake ``git ls-remote``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import ecosystem_status as es

ENGINE = Path(__file__).resolve().parents[1]
MANIFEST = ENGINE / "data" / "ecosystem" / "repositories.v1.json"
SCHEMA = ENGINE / "schemas" / "ecosystem" / "repositories.v1.schema.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
ALLOWED_VERBS = {"rev-parse", "status", "ls-remote", "remote"}
SEVEN = {"patientwords", "patientwords-engine", "patientwords-ica-lens-paper", "patient-words-jpp_lens",
         "patientwords-interp-engine", "patientwords-inspect_petri", "jacobian-lens-patientwords"}
OUTSIDE = {"patientwords-traces", "patient-words-causalab", "patientwords-verify"}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def by_id(doc: dict, name: str) -> dict:
    return next(entry for entry in doc["repositories"] if entry["id"] == name)


def all_pins(doc: dict) -> list[tuple[str, dict]]:
    owners = doc["repositories"] + doc["external_services"]
    return [(owner["id"], pin) for owner in owners for item in owner["consumed_by_engine"] for pin in item["pins"]]


# --- the committed manifest -------------------------------------------------------------------------------

def test_manifest_validates_against_its_schema_and_rules(manifest: dict, schema: dict) -> None:
    assert manifest["schema_version"] == "patientwords.ecosystem/1" == schema["$id"]
    assert es.validate_manifest(manifest, schema) == []


def test_manifest_lists_the_seven_and_the_three_resolved_from_engine_source(manifest: dict) -> None:
    groups = {entry["id"]: entry["group"] for entry in manifest["repositories"]}
    assert set(groups) == SEVEN | OUTSIDE
    assert {name for name, group in groups.items() if group == "outside_the_seven"} == OUTSIDE
    assert {name for name, group in groups.items() if group == "core"} == {"patientwords", "patientwords-engine"}
    assert [e["id"] for e in manifest["repositories"] if e["holds_this_manifest"]] == ["patientwords-engine"]
    # The private app: role and exchange scripts only. No head and no checkout path are recorded.
    verify = by_id(manifest, "patientwords-verify")
    assert verify["visibility"]["value"] == "private"
    assert verify["recorded_head"]["commit"] is None and verify["default_sibling_path"] is None
    assert verify["source_facts"] == []


def test_schema_rejects_unknown_keys_and_code_rejects_unknown_vocabulary(manifest: dict, schema: dict) -> None:
    extra = copy.deepcopy(manifest)
    extra["repositories"][0]["understanding_score"] = 1
    assert any("additional property" in p for p in es.validate_manifest(extra, schema))

    bad_type = copy.deepcopy(manifest)
    by_id(bad_type, "patientwords-interp-engine")["consumed_by_engine"][0]["type"] = "vendored"
    assert any("unknown consumption type" in p for p in es.validate_manifest(bad_type, schema))

    short = copy.deepcopy(manifest)
    by_id(short, "patientwords")["recorded_head"]["commit"] = "b7da453"
    problems = es.validate_manifest(short, schema)
    assert any("40 lowercase hex" in p for p in problems)
    assert any("latest_source_head differs" in p for p in problems)

    version = copy.deepcopy(manifest)
    version["schema_version"] = "patientwords.ecosystem/2"
    assert any("schema_version" in p for p in es.validate_manifest(version, schema))


def test_commits_and_digests_have_full_length(manifest: dict) -> None:
    for entry in manifest["repositories"]:
        commit = entry["recorded_head"]["commit"]
        assert commit is None or HEX40.fullmatch(commit), entry["id"]
    for owner, pin in all_pins(manifest):
        name = pin["name"].lower()
        if "commit" in name or "revision" in name and pin["pointer"]["kind"] == "json_pointer":
            assert pin["value"] is None or HEX40.fullmatch(pin["value"]), (owner, pin["name"])
        if "sha256" in name or "digest" in name:
            assert HEX64.fullmatch(pin["value"]), (owner, pin["name"])


def test_every_entry_separates_latest_source_head_from_tested_execution_pin(manifest: dict) -> None:
    for entry in manifest["repositories"]:
        block = entry["head_vs_pin"]
        assert set(block) == {"latest_source_head", "tested_execution_pin", "relation", "note"}, entry["id"]
        assert block["latest_source_head"] == entry["recorded_head"]["commit"], entry["id"]
        assert block["relation"] in es.RELATIONS, entry["id"]
        assert block["tested_execution_pin"] != block["latest_source_head"] or block["latest_source_head"] is None
        assert block["note"].strip(), entry["id"]
    # A synced fork is not a migrated runtime: the two executed pins are not the fork heads.
    interp = by_id(manifest, "patientwords-interp-engine")
    assert interp["head_vs_pin"]["relation"] == "pin_is_separate_distribution"
    assert "1.5.1" in interp["head_vs_pin"]["tested_execution_pin"]
    declared = next(f["value"] for f in interp["source_facts"] if f["name"].startswith("version declared"))
    assert declared != "1.5.1"
    petri = by_id(manifest, "patientwords-inspect_petri")
    assert petri["head_vs_pin"]["relation"] == "pin_is_older_source"
    assert HEX40.fullmatch(petri["head_vs_pin"]["tested_execution_pin"])
    assert petri["head_vs_pin"]["tested_execution_pin"] != petri["recorded_head"]["commit"]


def test_same_head_and_pin_is_refused(manifest: dict, schema: dict) -> None:
    merged = copy.deepcopy(manifest)
    petri = by_id(merged, "patientwords-inspect_petri")
    petri["head_vs_pin"]["tested_execution_pin"] = petri["recorded_head"]["commit"]
    assert any("repeats the latest source head" in p for p in es.validate_manifest(merged, schema))

    dropped = copy.deepcopy(manifest)
    by_id(dropped, "patientwords-interp-engine")["head_vs_pin"]["tested_execution_pin"] = None
    assert any("needs a tested_execution_pin" in p for p in es.validate_manifest(dropped, schema))


def test_every_pointer_file_exists_and_every_pin_equals_what_it_says_now(manifest: dict) -> None:
    pins = all_pins(manifest)
    assert len(pins) >= 20
    for owner, pin in pins:
        assert (ENGINE / pin["pointer_file"]).is_file(), (owner, pin["pointer_file"])
    rows = es.check_pins(manifest, ENGINE)
    assert len(rows) == len(pins)
    assert [(r["owner"], r["name"], r["detail"]) for r in rows if not r["matches"]] == []


def test_interp_engine_and_petri_pins_agree_with_the_files_read_independently(manifest: dict) -> None:
    """The same comparison without the script's own reader, for the two pins that govern execution."""
    constraints = (ENGINE / "constraints.txt").read_text(encoding="utf-8")
    versions = dict(re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)$", constraints, flags=re.MULTILINE))
    interp = by_id(manifest, "patientwords-interp-engine")
    recorded = {p["name"]: p["value"] for p in interp["consumed_by_engine"][0]["pins"]}
    assert interp["consumed_by_engine"][0]["type"] == "installed_distribution"
    assert recorded["interp-engine"] == versions["interp-engine"]
    assert recorded["transformers"] == versions["transformers"]
    assert recorded["torch"] == versions["torch"]

    lock = json.loads((ENGINE / "docs/framework/petri_environment.lock.json").read_text(encoding="utf-8"))
    petri = by_id(manifest, "patientwords-inspect_petri")
    recorded = {p["name"]: p["value"] for p in petri["consumed_by_engine"][0]["pins"]}
    assert petri["consumed_by_engine"][0]["type"] == "source_checkout"
    assert recorded["harness commit"] == lock["harness"]["commit"] == petri["head_vs_pin"]["tested_execution_pin"]
    assert recorded["python"] == lock["python"]["version"]
    assert recorded["lock digest"] == lock["lock_sha256"]
    for package in ("inspect-ai", "inspect-scout", "anthropic", "openai", "google-genai"):
        assert recorded[package] == lock["pins_of_record"][package] == lock["packages"][package], package


def test_unknown_identity_and_absent_pins_are_recorded_as_such(manifest: dict) -> None:
    jpp = {p["name"]: p["value"] for p in by_id(manifest, "patient-words-jpp_lens")["consumed_by_engine"][0]["pins"]}
    assert jpp["fit identity"].startswith("unknown") and jpp["transport authorized"] is False
    causalab = by_id(manifest, "patient-words-causalab")
    pins = {p["name"]: p["value"] for p in causalab["consumed_by_engine"][0]["pins"]}
    assert pins["execution commit"] is None  # recorded as missing, not filled with a dated receipt's commit
    assert causalab["head_vs_pin"]["tested_execution_pin"] is None
    assert "unresolved" in causalab["licence"]["code"].lower()
    for name in ("jacobian-lens-patientwords", "patientwords-ica-lens-paper"):
        consumed = by_id(manifest, name)["consumed_by_engine"]
        assert [item["type"] for item in consumed] == ["none"] and consumed[0]["pins"] == []
    lens = manifest["external_services"][0]["consumed_by_engine"][0]
    assert lens["type"] == "hosted_service" and "No revision is recorded" in lens["note"]


def test_upstream_relations_say_how_they_are_known(manifest: dict) -> None:
    assert "owner-reported, not re-derived" in manifest["owner_preparation_note"]["status"]
    for entry in manifest["repositories"]:
        relation = entry["upstream_relation"]
        if relation is not None:
            assert relation["basis"].startswith("verified"), entry["id"]
            assert relation["as_of"] == manifest["as_of"]


def _adapter_cases() -> list[Any]:
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [pytest.param(a["path"], a["state"], id=f"{entry['id']}:{a['path']}")
            for entry in doc["repositories"] for a in entry["adapters"]]


@pytest.mark.parametrize("path, state", _adapter_cases())
def test_adapter_paths_exist(path: str, state: str) -> None:
    if state == "added_in_change_set_20261110" and not (ENGINE / path).exists():
        pytest.skip(f"{path} is listed as added by the 2026-11-10 change set and is not in this tree yet")
    assert (ENGINE / path).exists(), path


# --- a synthetic layout of tiny git repositories -----------------------------------------------------------

def _git_setup(cwd: Path, *args: str) -> str:
    """Test-side git (creates the layout). Signing is switched off: the container signs commits by default."""
    done = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=fixture",
                           "-c", "user.email=fixture@example.invalid", "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _make_repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True)
    for name, body in files.items():
        (path / name).write_text(body, encoding="utf-8")
    _git_setup(path, "init", "-q")
    _git_setup(path, "add", "-A")
    _git_setup(path, "commit", "-q", "-m", "fixture")
    return _git_setup(path, "rev-parse", "HEAD")


def _entry(name: str, commit: str | None, *, holds: bool = False, fork_of: str | None = None,
           consumed: list[dict] | None = None, facts: list[dict] | None = None) -> dict:
    relation = None if fork_of is None else {"upstream_url": fork_of, "ahead": 0, "behind": 0,
                                             "as_of": "2000-01-01", "basis": "fixture", "note": "fixture"}
    return {
        "id": name, "group": "core" if holds else "method_fork", "url": f"https://github.com/example/{name}",
        "role": "fixture", "visibility": {"value": "public", "basis": "fixture"}, "fork_of": fork_of,
        "holds_this_manifest": holds, "default_sibling_path": f"../{name}",
        "path_override": {"cli_flags": [], "environment_variables": [], "note": "fixture"},
        "recorded_head": {"commit": commit, "recorded_utc_date": "2000-01-01", "source": "fixture"},
        "upstream_relation": relation,
        "licence": {"code": "fixture", "data": "fixture", "notice_obligations": "fixture"},
        "maintenance": "fixture", "entry_points": [], "environment": {"python": "fixture", "lock_or_constraints": []},
        "tests_and_ci": {"tests": "none", "ci": "none", "lint": "none"},
        "consumed_by_engine": consumed or [{"type": "none", "artifact": "nothing", "pins": [], "note": None}],
        "engine_writes": [],
        "head_vs_pin": {"latest_source_head": commit, "tested_execution_pin": None, "relation": "no_execution_pin",
                        "note": "fixture"},
        "source_facts": facts or [], "adapters": [], "active_vs_historical": "fixture", "dependencies": [],
    }


class Layout:
    """A temporary engine checkout holding a manifest, plus sibling clones under ``clones/``."""

    def __init__(self, tmp_path: Path) -> None:
        self.engine = tmp_path / "engine"
        self.clones = tmp_path / "clones"
        self.heads = {"engine": _make_repo(self.engine, {
            "constraints.txt": "# fixture\ntoolpkg==1.0\notherpkg==3.2\n",
            "lock.json": json.dumps({"harness": {"commit": "a" * 40}, "pins": {"dep": "0.1"}}),
        })}
        for name in ("match", "differ", "dirty"):
            self.heads[name] = _make_repo(self.clones / name, {"pyproject.toml": 'version = "9.9.9"\n'})
        (self.clones / "dirty" / "local_patch.txt").write_text("uncommitted\n", encoding="utf-8")
        self.path = self.engine / "data" / "ecosystem" / "repositories.v1.json"
        self.path.parent.mkdir(parents=True)
        self.write(self.document())

    def document(self) -> dict:
        consumed = [{"type": "installed_distribution", "artifact": "toolpkg from an index", "note": None, "pins": [
            {"name": "toolpkg", "value": "1.0", "pointer_file": "constraints.txt",
             "pointer": {"kind": "constraints_line", "package": "toolpkg"}, "how_to_read": "fixture"},
            {"name": "harness commit", "value": "a" * 40, "pointer_file": "lock.json",
             "pointer": {"kind": "json_pointer", "pointer": "/harness/commit"}, "how_to_read": "fixture"}]}]
        fact = [{"name": "declared version", "value": "9.9.9", "file": "pyproject.toml",
                 "text": 'version = "9.9.9"'}]
        match = _entry("match", self.heads["match"], fork_of="https://github.com/example/upstream",
                       consumed=consumed, facts=fact)
        match["head_vs_pin"].update(tested_execution_pin="toolpkg==1.0", relation="pin_is_separate_distribution")
        return {
            "schema_version": "patientwords.ecosystem/1", "as_of": "2000-01-01", "description": "fixture",
            "vocabularies": {name: list(values) for name, values in es.VOCABULARIES.items()},
            "owner_preparation_note": {"date": "2000-01-01", "status": "fixture", "statement": "fixture",
                                       "scope": "fixture"},
            "repositories": [_entry("engine", self.heads["engine"], holds=True), match,
                             _entry("differ", self.heads["differ"]), _entry("dirty", self.heads["dirty"]),
                             _entry("missing", "c" * 40)],
            "external_services": [],
        }

    def write(self, doc: Any) -> None:
        self.path.write_text(doc if isinstance(doc, str) else json.dumps(doc, indent=2), encoding="utf-8")

    def run(self, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
        capsys.readouterr()
        code = es.main(["--engine-root", str(self.engine), "--root", str(self.clones), *extra])
        captured = capsys.readouterr()
        return code, captured.out + captured.err

    def snapshot(self) -> dict[str, str]:
        """Every file under the layout, git internals included, by content hash."""
        root = self.engine.parent
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture()
def layout(tmp_path: Path) -> Layout:
    return Layout(tmp_path)


def test_synthetic_manifest_is_valid(layout: Layout, schema: dict) -> None:
    assert es.validate_manifest(layout.document(), schema) == []


def test_offline_status_matching_dirty_and_missing_exit_zero(layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = layout.run(capsys)
    assert code == 0, out
    assert out.count("head matches manifest") == 4  # engine, match, differ (not yet differing), dirty
    assert "dirty (1 changed path(s))" in out  # reported, not counted without --fail-on-dirty
    assert "checkout       absent" in out and "missing: checkout absent" in out
    assert "toolpkg [installed_distribution] : pin matches manifest (constraints.txt: toolpkg==1.0)" in out
    assert "harness commit [installed_distribution] : pin matches manifest" in out
    assert "declared version = 9.9.9 : matches" in out
    assert "differences: none" in out and "Offline: no network call was made." in out


def test_offline_status_differing_head_exits_one(layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    doc = layout.document()
    for entry in doc["repositories"]:
        if entry["id"] == "differ":
            entry["recorded_head"]["commit"] = entry["head_vs_pin"]["latest_source_head"] = "d" * 40
    layout.write(doc)
    code, out = layout.run(capsys)
    assert code == 1
    assert f"differ: local HEAD {layout.heads['differ']} differs from recorded head {'d' * 40}" in out
    assert out.rstrip().endswith("exit 1")


def test_dirty_tree_counts_only_when_asked(layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    assert layout.run(capsys)[0] == 0
    code, out = layout.run(capsys, "--fail-on-dirty")
    assert code == 1 and "dirty: working tree has 1 changed path(s)" in out


def test_changed_pin_and_changed_source_fact_exit_one_and_print_both_values(
        layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    (layout.engine / "constraints.txt").write_text("toolpkg==2.0\n", encoding="utf-8")
    code, out = layout.run(capsys)
    assert code == 1
    assert 'pin \'toolpkg\': manifest "1.0", pointer file says constraints.txt: toolpkg==2.0' in out
    (layout.engine / "constraints.txt").write_text("toolpkg==1.0\n", encoding="utf-8")
    (layout.engine / "lock.json").unlink()
    code, out = layout.run(capsys)
    assert code == 1 and "lock.json: unreadable" in out  # a missing pointer file is a difference, never a pass
    (layout.engine / "lock.json").write_text(json.dumps({"harness": {"commit": "a" * 40}}), encoding="utf-8")
    assert layout.run(capsys)[0] == 0
    (layout.clones / "match" / "pyproject.toml").write_text('version = "10.0.0"\n', encoding="utf-8")
    code, out = layout.run(capsys)
    assert code == 1 and "source fact 'declared version' (9.9.9) not found in pyproject.toml" in out


def test_the_manifest_holder_is_reported_but_counted_only_with_strict_self(
        layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    doc = layout.document()
    doc["repositories"][0]["recorded_head"]["commit"] = "e" * 40
    doc["repositories"][0]["head_vs_pin"]["latest_source_head"] = "e" * 40
    layout.write(doc)
    code, out = layout.run(capsys)
    assert code == 0 and "cannot record its own commit" in out
    assert layout.run(capsys, "--strict-self")[0] == 1


def test_path_override_wins_over_root(layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = layout.run(capsys, "--path", f"missing={layout.clones / 'dirty'}")
    assert code == 1  # the directory exists, and its HEAD is not the head recorded for `missing`
    assert f"{layout.clones / 'dirty'} (--path)" in out


def test_a_plain_directory_is_not_read_as_the_enclosing_repository(
        layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    (layout.engine / "inner").mkdir()
    code, out = layout.run(capsys, "--path", f"missing={layout.engine / 'inner'}")
    assert code == 0 and "is not a git checkout" in out


def test_malformed_manifest_exits_two(layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    layout.write("{not json")
    code, out = layout.run(capsys)
    assert code == 2 and "malformed manifest" in out
    doc = layout.document()
    doc["repositories"][1]["consumed_by_engine"][0]["type"] = "vendored"
    layout.write(doc)
    code, out = layout.run(capsys)
    assert code == 2 and "unknown consumption type" in out
    doc = layout.document()
    del doc["repositories"][2]["head_vs_pin"]
    layout.write(doc)
    assert layout.run(capsys, "--json")[0] == 2
    layout.path.unlink()
    assert layout.run(capsys)[0] == 2


def test_json_output_is_one_report(layout: Layout, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = layout.run(capsys, "--json")
    report = json.loads(out)
    assert code == report["exit_code"] == 0 and report["read_only"] is True
    assert report["schema_version"] == "patientwords.ecosystem-status/1" and report["mode"] == "offline"
    states = {row["id"]: row["state"] for row in report["repositories"]}
    assert states == {"engine": "present", "match": "present", "differ": "present", "dirty": "present",
                      "missing": "absent"}
    assert [row["dirty"] for row in report["repositories"] if row["id"] == "dirty"] == [True]
    assert all(pin["matches"] for pin in report["pins"]) and len(report["pins"]) == 2


# --- the read-only guarantee -------------------------------------------------------------------------------

class GitGuard:
    """Stands in for ``subprocess.run`` inside the script: fails on anything but the four read-only verbs."""

    def __init__(self, tips: dict[str, str | None] | None = None) -> None:
        self.real = subprocess.run
        self.tips = tips or {}
        self.verbs: list[str] = []
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        assert command[0] == "git", f"non-git command: {command}"
        rest = command[1:]
        if rest[:1] == ["-C"]:
            rest = rest[2:]
        verb = rest[0]
        assert verb in ALLOWED_VERBS, f"git verb outside the read-only set: {command}"
        assert verb != "remote" or rest[1] == "get-url", f"git remote may only read a URL: {command}"
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0", "git status must not refresh the index"
        self.verbs.append(verb)
        self.commands.append(command)
        if verb == "ls-remote":  # never the network in a test
            tip = self.tips.get(rest[1])
            if tip is None:
                return subprocess.CompletedProcess(command, 128, "", "fatal: repository not found")
            return subprocess.CompletedProcess(command, 0, f"{tip}\tHEAD\n", "")
        return self.real(command, **kwargs)


def test_docstring_states_the_read_only_guarantee() -> None:
    text = " ".join((es.__doc__ or "").split())
    assert "never clones, fetches, pulls, checks out, installs or writes a file" in text
    assert "cannot count commits ahead or behind without history" in text
    assert set(es.ALLOWED_GIT) == ALLOWED_VERBS


def test_offline_run_uses_only_read_only_git_verbs_and_changes_no_byte(
        layout: Layout, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    guard = GitGuard()
    monkeypatch.setattr(es.subprocess, "run", guard)
    before = layout.snapshot()
    assert layout.run(capsys, "--fail-on-dirty")[0] == 1
    assert layout.run(capsys, "--json")[0] == 0
    assert layout.snapshot() == before  # worktrees, indexes and refs are byte-identical
    assert set(guard.verbs) == {"rev-parse", "status", "remote"}
    assert "ls-remote" not in guard.verbs  # offline means no remote query at all


def test_write_and_network_verbs_are_refused_before_a_process_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(es.subprocess, "run", explode)
    for args in (["clone", "https://github.com/example/x"], ["fetch"], ["pull"], ["checkout", "main"],
                 ["reset", "--hard"], ["commit", "-m", "x"], ["push"], ["stash"], ["clean", "-fd"],
                 ["remote", "add", "o", "u"], ["remote", "set-url", "origin", "u"], ["remote"], []):
        with pytest.raises(PermissionError):
            es._git(args)


def test_remote_mode_compares_tips_only_and_never_fetches(
        layout: Layout, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    heads = layout.heads
    tips = {f"https://github.com/example/{name}": heads[name] for name in ("engine", "match", "differ", "dirty")}
    tips["https://github.com/example/missing"] = "c" * 40
    tips["https://github.com/example/upstream"] = heads["match"]
    guard = GitGuard(tips)
    monkeypatch.setattr(es.subprocess, "run", guard)
    before = layout.snapshot()
    code, out = layout.run(capsys, "--remote")
    assert code == 0, out
    assert out.count("recorded head is the remote head") == 5
    assert "fork tip equals upstream tip" in out
    assert "cannot count commits ahead or behind without history" in out
    assert set(guard.verbs) == ALLOWED_VERBS and layout.snapshot() == before
    assert all(c[1:] == ["ls-remote", c[2], "HEAD"] for c in guard.commands if "ls-remote" in c)

    guard.tips["https://github.com/example/differ"] = "f" * 40  # the remote moved on
    guard.tips["https://github.com/example/upstream"] = "9" * 40  # the upstream moved on
    code, out = layout.run(capsys, "--remote")
    assert code == 1
    assert f"differ: recorded head is not the remote head ({'f' * 40})" in out
    assert "match: manifest records the fork level with its upstream, but the tips differ" in out

    guard.tips["https://github.com/example/differ"] = None  # unreachable is not a pass and not a difference
    guard.tips["https://github.com/example/upstream"] = heads["match"]
    code, out = layout.run(capsys, "--remote")
    assert code == 0 and "differ: remote unreachable (fatal: repository not found)" in out


def test_remote_mode_skips_private_repositories(
        layout: Layout, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    doc = layout.document()
    doc["repositories"][4]["visibility"]["value"] = "private"
    layout.write(doc)
    guard = GitGuard({f"https://github.com/example/{n}": layout.heads[n] for n in ("engine", "match", "differ", "dirty")}
                     | {"https://github.com/example/upstream": layout.heads["match"]})
    monkeypatch.setattr(es.subprocess, "run", guard)
    code, out = layout.run(capsys, "--remote")
    assert code == 0 and "missing: private repository; remote not queried" in out
    assert not any("example/missing" in " ".join(c) for c in guard.commands)


def test_repositories_with_daily_operational_commits_are_printed_and_not_counted() -> None:
    """The site receives a data publish most days and the traces mirror builds nightly, so their recorded
    heads go stale by design. The difference is printed; it is counted only with --strict-self."""
    manifest = json.loads((ENGINE / "data" / "ecosystem" / "repositories.v1.json").read_text(encoding="utf-8"))
    moving = sorted(e["id"] for e in manifest["repositories"] if e.get("head_moves_with_operations"))
    assert moving == ["patientwords", "patientwords-traces"]
    source = (ENGINE / "scripts" / "ecosystem_status.py").read_text(encoding="utf-8")
    assert source.count('row["holds_this_manifest"] or row["head_moves_with_operations"]') == 1
    assert source.count('entry["holds_this_manifest"] or entry.get("head_moves_with_operations")') == 1
