"""Holdout-seal integrity check (scripts/seal_check.py) — offline.

Pins: empty-set refusal (exit 2, the wrong-branch guard), leak detection by
exact AND normalized match, label-only reporting (phrase text never printed),
and the clean path. Since 2026-09-23 also: the only skipped directories are the
engine's registry sources and measurement store, matched by resolved path, and
.git by path component (a substring test on the path skipped the site's
data/simulated_*.json files, its whole modes/ render tree and .github/); HTML
entities and JSON escapes are decoded before matching; and the owner-ruled
allowlist suppresses a sealed phrase only inside a whole-field occurrence of
the exact containing field whose sha256 it records, never inside that text run
on into more words, and never for a field that is the phrase up to case and
whitespace; and a root whose git checkout keeps tracked files off disk (a
sparse checkout) is a configuration error, not a CLEAN sweep. Uses abstract
non-medical synthetic phrases only.
"""

import hashlib
import html
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("seal_check", _ROOT / "scripts" / "seal_check.py")
sc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sc)

SEALED_BATCH = "pairs_20260711T000000Z"
EXPLORE_BATCH = "pairs_20260801T000000Z"


def _holdout(p):
    return int(hashlib.sha1(p.encode()).hexdigest(), 16) % 10 == 0


def sealed_phrase(base="zz test phrase"):
    """Find a phrase variant that lands in the sha1-mod-10 holdout bucket."""
    for i in range(200):
        p = f"{base} {i}"
        if _holdout(p):
            return p
    raise AssertionError("no holdout phrase found in 200 tries")


def container_of(phrase, sealed=False):
    """A longer, different phrase that contains `phrase`, hashing explore (or holdout)."""
    for i in range(500):
        c = f"{phrase} n{i}"
        if _holdout(c) == sealed:
            return c
    raise AssertionError("no container found")


def setup(tmp_path, phrase, explore_rows=()):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / f"{SEALED_BATCH}.json").write_text(json.dumps(
        [{"top_prompt": phrase, "bottom_prompt": "kept out of it"}]), encoding="utf-8")
    if explore_rows:
        (sim / f"{EXPLORE_BATCH}.json").write_text(json.dumps(
            [{"top_prompt": t, "bottom_prompt": "other"} for t in explore_rows]), encoding="utf-8")
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "dashboard.json").write_text(json.dumps(
        {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}), encoding="utf-8")
    site = tmp_path / "site" / "data"
    site.mkdir(parents=True)
    return sim, ops, site


def write_allowlist(tmp_path, entries):
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def entry(containing_text, **over):
    e = {"label": f"{SEALED_BATCH}#1", "containing": f"{EXPLORE_BATCH}#1", "field": "top_prompt",
         "sha256": hashlib.sha256(containing_text.encode()).hexdigest(),
         "ruling_date": "2026-09-23", "reason": "synthetic ruling"}
    e.update(over)
    return e


def run(tmp_path, capsys, extra="", allowlist=None):
    rc = sc.main(["--site", str(tmp_path / "site"),
                  "--dashboard", str(tmp_path / "ops" / "dashboard.json"),
                  "--simulated", str(tmp_path / "data" / "simulated"),
                  "--trace-out", str(tmp_path / "trace_out"),
                  "--allowlist", str(allowlist or tmp_path / "no_allowlist.json"),
                  "--extra", extra])
    return rc, capsys.readouterr().out


def test_empty_sealed_set_is_a_config_error(tmp_path, capsys):
    phrase = sealed_phrase()
    setup(tmp_path, phrase)
    (tmp_path / "ops" / "dashboard.json").write_text(json.dumps({"tierb": {}}))
    rc, out = run(tmp_path, capsys)
    assert rc == 2 and "CONFIG ERROR" in out


def test_clean_when_site_has_no_sealed_phrase(tmp_path, capsys):
    phrase = sealed_phrase()
    _, _, site = setup(tmp_path, phrase)
    (site / "payload.json").write_text(json.dumps({"scenarios": [{"p": "harmless"}]}))
    rc, out = run(tmp_path, capsys)
    assert rc == 0 and "CLEAN" in out


def test_leak_found_by_normalized_match_and_never_quoted(tmp_path, capsys):
    phrase = sealed_phrase()
    _, _, site = setup(tmp_path, phrase)
    mangled = phrase.upper().replace(" ", "   ")          # case + whitespace mangling
    (site / "leaky.json").write_text(json.dumps({"text": mangled}))
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and "LEAK" in out
    assert f"{SEALED_BATCH}#1" in out                     # label-only reporting
    assert phrase not in out and mangled not in out        # the report is not the leak


# --- path exclusions: the resolved registry dir only, never a substring ------ #

def test_site_files_whose_names_start_with_simulated_are_scanned(tmp_path, capsys):
    # The 2026-07-21..09-23 checker skipped any path containing "data/simulated",
    # which is a prefix of the site's per-row payload files.
    phrase = sealed_phrase()
    _, _, site = setup(tmp_path, phrase)
    (site / "simulated_scenarios.json").write_text(
        json.dumps({"scenarios": [{"clinical_prompt": f"{phrase} zq"}]}), encoding="utf-8")
    (site / "simulated_x.json").write_text(json.dumps([phrase]), encoding="utf-8")
    rc, out = run(tmp_path, capsys)
    assert rc == 1
    assert str(site / "simulated_scenarios.json") in out
    assert str(site / "simulated_x.json") in out
    assert phrase not in out


def test_modes_render_tree_is_scanned(tmp_path, capsys):
    phrase = sealed_phrase()
    setup(tmp_path, phrase)
    render = tmp_path / "site" / "modes" / "simulated" / SEALED_BATCH / "index_01.html"
    render.parent.mkdir(parents=True)
    render.write_text(f"<html><body><p>{phrase}</p></body></html>", encoding="utf-8")
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and str(render) in out


def test_registry_source_dir_is_not_a_leak_even_as_an_extra_root(tmp_path, capsys):
    phrase = sealed_phrase()
    sim, _, _ = setup(tmp_path, phrase)
    rc, out = run(tmp_path, capsys, extra=str(sim))
    assert rc == 0 and "CLEAN" in out


def test_engine_trace_out_skipped_but_a_trace_out_copy_elsewhere_is_scanned(tmp_path, capsys):
    phrase = sealed_phrase()
    setup(tmp_path, phrase)
    own = tmp_path / "trace_out" / SEALED_BATCH / "batch_summary.part_01.json"
    own.parent.mkdir(parents=True)
    own.write_text(json.dumps({"results": [{"prompts": {"clinical": phrase}}]}), encoding="utf-8")
    rc, _ = run(tmp_path, capsys, extra=str(tmp_path / "trace_out"))
    assert rc == 0, "the engine's own measurement store is a registry-class source"
    copy = tmp_path / "site" / "trace_out" / "batch_summary.part_01.json"
    copy.parent.mkdir(parents=True)
    copy.write_text(own.read_text(encoding="utf-8"), encoding="utf-8")
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and str(copy) in out


def test_git_dir_skipped_by_component_but_github_is_scanned(tmp_path, capsys):
    phrase = sealed_phrase()
    setup(tmp_path, phrase)
    in_git = tmp_path / "site" / ".git" / "objects.json"
    in_git.parent.mkdir(parents=True)
    in_git.write_text(json.dumps([phrase]), encoding="utf-8")
    rc, _ = run(tmp_path, capsys)
    assert rc == 0
    workflow = tmp_path / "site" / ".github" / "workflows" / "checks.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(f"name: {phrase}\n", encoding="utf-8")
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and str(workflow) in out and str(in_git) not in out


# --- decoding: HTML entities and JSON escapes --------------------------------- #

def test_html_escaped_phrase_with_apostrophe_is_found(tmp_path, capsys):
    phrase = sealed_phrase("zz it's a test phrase")
    setup(tmp_path, phrase)
    page = tmp_path / "site" / "t" / "index_09.html"
    page.parent.mkdir(parents=True)
    escaped = html.escape(phrase)                          # the apostrophe becomes &#x27;
    assert escaped != phrase
    page.write_text(f"<p>{escaped}</p>", encoding="utf-8")
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and str(page) in out and escaped not in out


def test_decimal_entity_spelling_is_found_too(tmp_path, capsys):
    phrase = sealed_phrase("zz it's a test phrase")
    setup(tmp_path, phrase)
    page = tmp_path / "site" / "p.html"
    page.write_text(f"<p>{phrase.replace(chr(39), '&#39;')}</p>", encoding="utf-8")
    rc, _ = run(tmp_path, capsys)
    assert rc == 1


def test_ascii_escaped_json_phrase_is_found(tmp_path, capsys):
    # json.dumps' default ensure_ascii writes a non-ASCII phrase as \uXXXX
    phrase = sealed_phrase("zz café test phrase")
    _, _, site = setup(tmp_path, phrase)
    body = json.dumps({"clinical_prompt": phrase})
    assert phrase not in body
    (site / "payload.json").write_text(body, encoding="utf-8")
    rc, _ = run(tmp_path, capsys)
    assert rc == 1


def test_json_unescape_keeps_an_escaped_backslash_literal():
    assert sc.json_unescape("a\\\\u0041b") == "a\\u0041b"
    assert sc.json_unescape('\\u00e9 \\"q\\"') == 'é "q"'
    assert sc.json_unescape("\\ud83d\\ude00") == "\U0001F600"


# --- allowlist: keyed on the containing field's sha256 ------------------------ #

def test_allowlisted_containing_field_suppresses_the_hit(tmp_path, capsys):
    phrase = sealed_phrase()
    container = container_of(phrase)
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    (site / "simulated_scenarios.json").write_text(
        json.dumps({"scenarios": [{"clinical_prompt": container}]}), encoding="utf-8")
    (site / "simulated_archive.csv").write_text(f'batch,clinical_prompt\nx,"{container}"\n',
                                                encoding="utf-8")
    page = tmp_path / "site" / "t" / "index_09.html"
    page.parent.mkdir(parents=True)
    page.write_text(f"<p>{html.escape(container)}</p>", encoding="utf-8")
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(container)]))
    assert rc == 0 and "CLEAN" in out
    assert "1 of 1 entry active" in out and "3 file(s) had only allowlisted occurrences" in out
    assert f"{SEALED_BATCH}#1 inside {EXPLORE_BATCH}#1.top_prompt" in out
    assert phrase not in out and container not in out


def test_bare_phrase_still_flags_with_the_allowlist_active(tmp_path, capsys):
    phrase = sealed_phrase()
    container = container_of(phrase)
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    (site / "contained.json").write_text(json.dumps([container]), encoding="utf-8")
    (site / "bare.json").write_text(json.dumps([phrase]), encoding="utf-8")
    (site / "both.json").write_text(json.dumps([container, f"{phrase}."]), encoding="utf-8")
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(container)]))
    assert rc == 1
    leak_block = out.split("allowlist:")[0]
    assert str(site / "bare.json") in leak_block and str(site / "both.json") in leak_block
    assert str(site / "contained.json") not in leak_block


def test_a_different_container_is_not_suppressed(tmp_path, capsys):
    # The ruling covers one field, not every longer text that contains the phrase.
    phrase = sealed_phrase()
    container = container_of(phrase)
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    (site / "other.json").write_text(json.dumps([f"{phrase} and more words"]), encoding="utf-8")
    rc, _ = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(container)]))
    assert rc == 1


def _short_word_case():
    """A sealed phrase whose container is the phrase plus a space and a
    one-letter word, hashing explore (the shape of the 2026-09-23 entry)."""
    for i in range(5000):
        p = f"zz test phrase {i}"
        if _holdout(p) and not _holdout(f"{p} a"):
            return p, f"{p} a"
    raise AssertionError("no such pair found")


def test_container_run_on_into_more_words_still_flags(tmp_path, capsys):
    # 2026-09-23 review: substring masking masked "<phrase> a" inside
    # "<phrase> also ...", so a bare leak followed by any word starting with the
    # container's last letter was reported as allowlisted.
    phrase, container = _short_word_case()
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    leaks = {
        "value.json": json.dumps([f"{phrase} also more"]),
        "page.html": f"<p>quoted: {phrase} also more</p>",
        "upper.html": f"<p>{phrase} Also</p>",
        "brief.md": f"- the sealed prompt was {phrase} and it moved\n",
        "cells.csv": f'k,v\nx,"{phrase} also"\ny,{phrase} and\n',
    }
    for name, body in leaks.items():
        (site / name).write_text(body, encoding="utf-8")
    allowlist = write_allowlist(tmp_path, [entry(container)])
    rc, out = run(tmp_path, capsys, allowlist=allowlist)
    assert rc == 1
    leak_block = out.split("allowlist:")[0]
    for name in leaks:
        assert str(site / name) in leak_block, name
    assert "1 of 1 entry active" in out and phrase not in out


def test_run_on_leak_exits_1_with_the_allowlist_and_without_it(tmp_path, capsys):
    phrase, container = _short_word_case()
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    (site / "notes.md").write_text(f"{phrase} also appears here\n", encoding="utf-8")
    rc_without, _ = run(tmp_path, capsys)
    rc_with, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(container)]))
    assert rc_without == 1 and rc_with == 1 and "CLEAN" not in out


def test_whole_field_container_is_allowlisted_in_every_encoding(tmp_path, capsys):
    phrase, container = _short_word_case()
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    ok = {
        "value.json": json.dumps({"clinical_prompt": container, "k": [container]}),
        "cell_quoted.csv": f'a,b\nx,"{container}"\n',
        "cell_bare.csv": f"a,b,c\n{container},y,z\nx,{container},z\nx,y,{container}\n",
        "element.html": f"<td>\n  {html.escape(container)}\n</td><b>k:</b> {container}</p>",
        "attribute.html": f'<a title="{html.escape(container)}" data-x=\'{container}\'>k</a>',
        "upper.json": json.dumps([container.upper()]),
    }
    for name, body in ok.items():
        (site / name).write_text(body, encoding="utf-8")
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(container)]))
    assert rc == 0 and "CLEAN" in out
    assert f"{len(ok)} file(s) had only allowlisted occurrences" in out


def test_csv_bounds_apply_only_to_csv_files(tmp_path, capsys):
    # A comma is a field delimiter only in a CSV file; in prose it is not.
    phrase, container = _short_word_case()
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    (site / "prose.md").write_text(f"first, {container}, then more\n", encoding="utf-8")
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(container)]))
    assert rc == 1 and str(site / "prose.md") in out.split("allowlist:")[0]


def _variant_case(make):
    """A sealed phrase and a variant of it (made by `make`) that hashes explore."""
    for i in range(5000):
        p = f"zz test phrase {i}"
        if _holdout(p) and not _holdout(make(p)):
            return p, make(p)
    raise AssertionError("no such pair found")


def test_case_variant_container_is_inactive_and_a_bare_leak_flags(tmp_path, capsys):
    # 2026-09-23 review: the "itself sealed" test compared exactly, while
    # matching and masking are normalized, so a container differing from the
    # phrase only by case activated and then masked every bare occurrence.
    phrase, variant = _variant_case(str.upper)
    _, _, site = setup(tmp_path, phrase, explore_rows=[variant])
    (site / "bare.json").write_text(json.dumps([phrase]), encoding="utf-8")
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(variant)]))
    assert rc == 1 and "INACTIVE (containing field is itself sealed)" in out
    assert "0 of 1 entry active" in out


def test_whitespace_variant_container_is_inactive_and_a_bare_leak_flags(tmp_path, capsys):
    phrase, variant = _variant_case(lambda p: p.replace(" ", "  ", 1))
    _, _, site = setup(tmp_path, phrase, explore_rows=[variant])
    (site / "bare.json").write_text(json.dumps([phrase]), encoding="utf-8")
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [entry(variant)]))
    assert rc == 1 and "INACTIVE (containing field is itself sealed)" in out


def test_residue_and_line_preserving_normalization():
    phrase = sealed_phrase()
    assert sc._residue(f"{phrase}  {phrase.upper()}", phrase) == ""   # a repetition is the phrase
    assert sc._residue(f"{phrase} a", phrase) == "a"
    assert sc.norm(sc.norm_lines("A\t b\r\n\n c")) == sc.norm("A\t b\r\n\n c")
    assert sc.norm_lines("A\t b\r\n\n c") == "a b\nc"


def test_allowlist_entry_with_a_stale_hash_suppresses_nothing(tmp_path, capsys):
    phrase = sealed_phrase()
    container = container_of(phrase)
    _, _, site = setup(tmp_path, phrase, explore_rows=[container])
    (site / "contained.json").write_text(json.dumps([container]), encoding="utf-8")
    stale = entry(container, sha256=hashlib.sha256(b"an older field").hexdigest())
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [stale]))
    assert rc == 1 and "INACTIVE (containing field no longer matches its sha256)" in out


def test_allowlist_entry_whose_container_is_itself_sealed_suppresses_nothing(tmp_path, capsys):
    phrase = sealed_phrase()
    sealed_container = container_of(phrase, sealed=True)
    _, _, site = setup(tmp_path, phrase, explore_rows=[sealed_container])
    (site / "contained.json").write_text(json.dumps([sealed_container]), encoding="utf-8")
    rc, out = run(tmp_path, capsys,
                  allowlist=write_allowlist(tmp_path, [entry(sealed_container)]))
    assert rc == 1 and "containing field is itself sealed" in out


def test_allowlist_keyed_on_a_label_alone_or_a_hash_prefix_is_refused(tmp_path, capsys):
    phrase = sealed_phrase()
    container = container_of(phrase)
    setup(tmp_path, phrase, explore_rows=[container])
    label_only = {"label": f"{SEALED_BATCH}#1", "ruling_date": "2026-09-23", "reason": "r"}
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [label_only]))
    assert rc == 2 and "CONFIG ERROR" in out
    prefix = entry(container)
    prefix["sha256"] = prefix["sha256"][:12]
    rc, out = run(tmp_path, capsys, allowlist=write_allowlist(tmp_path, [prefix]))
    assert rc == 2 and "never a prefix" in out


def test_committed_allowlist_is_well_formed_and_hash_keyed():
    entries = sc.load_allowlist(_ROOT / "data" / "seal_allowlist.json")
    assert entries, "the 2026-09-23 ruling entry is present"
    for e in entries:
        assert len(e["sha256"]) == 64 and e["containing"] != e["label"]


# --- a root whose checkout keeps tracked files off disk (2026-09-23 review) ---- #

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(cwd, *argv):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *argv],
                   cwd=str(cwd), check=True, capture_output=True)


@needs_git
def test_sparse_site_checkout_is_a_config_error_not_clean(tmp_path, capsys):
    # The cloud containers' site clone excludes modes/; the sweep then read no
    # render and still printed CLEAN.
    phrase = sealed_phrase()
    setup(tmp_path, phrase)
    site_root = tmp_path / "site"
    (site_root / "data" / "payload.json").write_text(json.dumps({"p": "harmless"}), encoding="utf-8")
    render = site_root / "modes" / "simulated" / SEALED_BATCH / "index_01.html"
    render.parent.mkdir(parents=True)
    render.write_text(f"<p>{phrase}</p>", encoding="utf-8")
    _git(site_root, "init", "-q")
    _git(site_root, "add", "-A")
    _git(site_root, "commit", "-qm", "site")
    _git(site_root, "sparse-checkout", "set", "--no-cone", "/*", "!/modes/")
    assert not render.exists()
    rc, out = run(tmp_path, capsys)
    assert rc == 2 and "CONFIG ERROR" in out and "sparse-checkout disable" in out
    assert "CLEAN" not in out and phrase not in out
    _git(site_root, "sparse-checkout", "disable")
    rc, out = run(tmp_path, capsys)
    assert rc == 1 and str(render) in out


@needs_git
def test_hidden_files_in_excluded_dirs_or_unscanned_suffixes_do_not_refuse(tmp_path):
    root = tmp_path / "engine"
    for rel in ("trace_out/a/batch_summary.part_01.json", "docs/fig.png", "docs/note.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "e")
    _git(root, "update-index", "--skip-worktree", "trace_out/a/batch_summary.part_01.json", "docs/fig.png")
    assert sc.hidden_scannable([root], [root / "trace_out"]) == []
    _git(root, "update-index", "--skip-worktree", "docs/note.md")
    assert sc.hidden_scannable([root], [root / "trace_out"]) == [str(root / "docs" / "note.md")]
    assert sc.hidden_scannable([root / "docs" / "note.md"]) == [str(root / "docs" / "note.md")]
