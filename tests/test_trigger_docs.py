"""The lane tables in docs/triggers.md and AGENTS.md against the script that
owns the facts (scripts/fire_trigger.py: TRIGGERS, PAID_TRIGGERS, PARK_DEFAULTS,
KNOWN_KEYS, MITIGATION_IMPUTED_USD) and against the workflows on this branch,
read from their parsed `on.push.paths` and their push-path key reads rather
than from a substring search. The 2026-09-04 fact-check found
.github/trigger/README.md six lanes behind and the AGENTS table one behind,
with nothing checking either; the guard hooks refuse session writes under
.github/trigger/, so the reference moved to docs/triggers.md, and this is the
check."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")
DOC = (ROOT / "docs" / "triggers.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"
PAB_WORKFLOW = WORKFLOWS / "pab_probe.yml"


def _table_rows(text: str) -> dict[str, list[str]]:
    """{trigger: [cells]} for every markdown table row whose first cell is
    `<name>.json`. A trigger with two rows is a failure, not a last-wins."""
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*`([a-z-]+)\.json`\s*\|(.*)\|\s*$", line)
        if not m:
            continue
        trigger = m.group(1)
        assert trigger not in rows, f"two rows for {trigger}"
        rows[trigger] = [c.strip() for c in m.group(2).split("|")]
    return rows


def _push_paths(workflow: Path) -> list[str]:
    """The workflow's parsed `on.push.paths` (PyYAML reads the `on` key as True)."""
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    on = data.get(True, data.get("on")) or {}
    push = on.get("push") or {}
    return list(push.get("paths") or [])


def _workflows_reading(trigger: str) -> list[str]:
    needle = f".github/trigger/{trigger}.json"
    return sorted(p.name for p in WORKFLOWS.glob("*.yml") if needle in _push_paths(p))


def _workflow_keys(workflow: Path) -> set[str]:
    """The keys the workflow's push path reads from the trigger file: the keys of
    its params heredoc `defaults` dict, or, for a workflow that reads `cfg`
    directly (archive_renders.yml), every `cfg["k"]` / `cfg.get("k")`."""
    text = workflow.read_text(encoding="utf-8")
    if "defaults = {" in text:
        block = text[text.index("defaults = {"):]
        block = block[:block.index("}") + 1]
        return set(re.findall(r'"(\w+)":', block))
    return set(re.findall(r'cfg(?:\.get\(|\[)"(\w+)"', text))


def test_doc_lists_every_trigger_the_script_knows_and_no_other() -> None:
    rows = _table_rows(DOC)
    assert set(rows) == set(ft.TRIGGERS), sorted(set(rows) ^ set(ft.TRIGGERS))


def test_doc_rows_name_the_workflow_whose_push_paths_read_the_file() -> None:
    rows = _table_rows(DOC)
    for trigger, cells in rows.items():
        workflow = cells[0].strip("`")
        readers = _workflows_reading(trigger)
        if trigger == "pab-probe" and not PAB_WORKFLOW.exists():
            assert readers == [], "pab-probe must be unwired where its workflow is absent"
            assert "PAB branch" in cells[1]
            continue
        assert readers == [workflow], (trigger, readers, workflow)


def test_doc_rows_carry_the_exact_key_set_the_script_accepts() -> None:
    rows = _table_rows(DOC)
    for trigger, cells in rows.items():
        listed = set(re.findall(r"`([a-z_0-9]+)`", cells[-1]))
        assert listed == set(ft.KNOWN_KEYS[trigger]), (trigger, sorted(listed ^ set(ft.KNOWN_KEYS[trigger])))


@pytest.mark.parametrize("trigger", [t for t in ft.TRIGGERS if _workflows_reading(t)])
def test_known_keys_match_the_workflow_push_path_reads(trigger: str) -> None:
    """KNOWN_KEYS is not both sides of the check: the workflow's own push-path
    reads are the other side. A key only in the workflow cannot be set through
    the sanctioned path; a key only in KNOWN_KEYS is silently dropped by CI."""
    (workflow,) = _workflows_reading(trigger)
    in_workflow = _workflow_keys(WORKFLOWS / workflow)
    assert in_workflow == set(ft.KNOWN_KEYS[trigger]), (
        f"only in workflow: {sorted(in_workflow - set(ft.KNOWN_KEYS[trigger]))}; "
        f"only in KNOWN_KEYS: {sorted(set(ft.KNOWN_KEYS[trigger]) - in_workflow)}")


def test_doc_rows_mark_paid_lanes_park_defaults_and_the_mitigation_cost_as_the_script_does() -> None:
    rows = _table_rows(DOC)
    for trigger, cells in rows.items():
        assert ("**paid**" in cells[1]) == (trigger in ft.PAID_TRIGGERS), trigger
        assert cells[2].startswith("yes") == (trigger in ft.PARK_DEFAULTS), (trigger, cells[2])
    # circuit-trace is outside PAID_TRIGGERS and becomes paid with show_mitigation,
    # at the flat imputed amount the budget guard charges; the row must say so.
    what = rows["circuit-trace"][1]
    assert "`show_mitigation: true`" in what and f"${ft.MITIGATION_IMPUTED_USD:.2f}" in what, what


def test_agents_table_lists_every_lane_wired_on_this_branch() -> None:
    rows = _table_rows(AGENTS)
    wired = {t for t in ft.TRIGGERS if _workflows_reading(t)}
    assert set(rows) == wired, sorted(set(rows) ^ wired)
    for trigger, cells in rows.items():
        assert _workflows_reading(trigger) == [cells[0].strip("`")], trigger
    m = re.search(r"^(\w+) lanes\.", AGENTS, re.M)
    assert m, "AGENTS.md should state the lane count under its table"
    words = {7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
    assert m.group(1) == words.get(len(wired), str(len(wired))), (m.group(1), len(wired))
