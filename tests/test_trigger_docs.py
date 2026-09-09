"""The lane tables in docs/triggers.md and AGENTS.md against the script
that owns the facts (scripts/fire_trigger.py: TRIGGERS, PAID_TRIGGERS,
PARK_DEFAULTS, KNOWN_KEYS) and the workflows on this branch. The 2026-09-04
fact-check found .github/trigger/README.md six lanes behind and the AGENTS table one
behind, with nothing checking either; the guard hooks refuse session writes under
.github/trigger/, so the reference moved to docs/triggers.md, and this is the check."""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")
README = (ROOT / "docs" / "triggers.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"


def _table_rows(text):
    """{trigger: [cells]} for every markdown table row whose first cell is `<name>.json`."""
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*`([a-z-]+)\.json`\s*\|(.*)\|\s*$", line)
        if m:
            rows[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return rows


def _workflows_reading(trigger):
    needle = f".github/trigger/{trigger}.json"
    return sorted(p.name for p in WORKFLOWS.glob("*.yml") if needle in p.read_text(encoding="utf-8"))


def test_readme_lists_every_trigger_the_script_knows_and_no_other():
    rows = _table_rows(README)
    assert set(rows) == set(ft.TRIGGERS), (sorted(set(rows) ^ set(ft.TRIGGERS)))


def test_readme_rows_name_the_workflow_that_reads_the_file():
    rows = _table_rows(README)
    for trigger, cells in rows.items():
        workflow = cells[0].strip("`")
        readers = _workflows_reading(trigger)
        if trigger == "pab-probe":
            assert readers == [] and not (WORKFLOWS / workflow).exists(), "pab-probe is wired on the PAB branch only"
            assert "PAB branch" in cells[1]
        else:
            assert readers == [workflow], (trigger, readers, workflow)


def test_readme_rows_carry_the_exact_key_set_the_script_accepts():
    rows = _table_rows(README)
    for trigger, cells in rows.items():
        listed = set(re.findall(r"`([a-z_0-9]+)`", cells[-1]))
        assert listed == set(ft.KNOWN_KEYS[trigger]), (trigger, sorted(listed ^ set(ft.KNOWN_KEYS[trigger])))


def test_readme_rows_mark_paid_lanes_and_park_defaults_as_the_script_does():
    rows = _table_rows(README)
    for trigger, cells in rows.items():
        assert ("**paid**" in cells[1]) == (trigger in ft.PAID_TRIGGERS), trigger
        assert cells[2].startswith("yes") == (trigger in ft.PARK_DEFAULTS), (trigger, cells[2])


def test_agents_table_lists_every_lane_wired_on_this_branch():
    rows = _table_rows(AGENTS)
    wired = {t for t in ft.TRIGGERS if _workflows_reading(t)}
    assert set(rows) == wired, sorted(set(rows) ^ wired)
    for trigger, cells in rows.items():
        assert _workflows_reading(trigger) == [cells[0].strip("`")], trigger
    m = re.search(r"^(\w+) lanes\.", AGENTS, re.M)
    assert m, "AGENTS.md should state the lane count under its table"
    words = {8: "Eight", 9: "Nine", 10: "Ten", 7: "Seven"}
    assert m.group(1) == words.get(len(wired), str(len(wired))), (m.group(1), len(wired))
