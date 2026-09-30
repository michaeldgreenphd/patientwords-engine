"""scripts/README.md indexes every top-level scripts/*.py, one row each.

The index is only useful while it is complete: a script with no row is a script
nobody can find the status or owner of, and a row for a deleted script sends a
reader to nothing. These tests fail on either, and on a status outside the
README's four-word vocabulary, so the row changes in the same pull request as
the script. scripts/petri_audit/ is a package with its own docstrings and is
deliberately not indexed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
README = SCRIPTS / "README.md"

STATUSES = frozenset({"live", "operator tool", "one-off and done", "staged"})
COLUMNS = ("Script", "What it does", "Status", "Writes", "Who runs it")
ROW = re.compile(r"^\|\s*`([^`/]+\.py)`\s*\|")


def top_level_scripts(scripts_dir: Path) -> set[str]:
    """File names of the top-level scripts/*.py, dunder modules excluded."""
    return {p.name for p in scripts_dir.glob("*.py") if not p.name.startswith("__")}


def index_rows(text: str) -> list[tuple[str, list[str]]]:
    """(script name, cells) for every table row whose first cell is a backticked `name.py`."""
    rows = []
    for line in text.splitlines():
        match = ROW.match(line)
        if match:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append((match.group(1), cells))
    return rows


def index_problems(text: str, scripts: set[str]) -> list[str]:
    """Every way the index disagrees with the scripts on disk, as readable lines."""
    problems = []
    rows = index_rows(text)
    names = [name for name, _ in rows]
    for name in sorted(scripts - set(names)):
        problems.append(f"no row for scripts/{name}")
    for name in sorted(set(names) - scripts):
        problems.append(f"row for scripts/{name}, which does not exist")
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"more than one row for scripts/{name}")
    for name, cells in rows:
        if len(cells) != len(COLUMNS):
            problems.append(f"scripts/{name}: {len(cells)} cells, expected {len(COLUMNS)} {COLUMNS}")
            continue
        status = cells[COLUMNS.index("Status")]
        if status not in STATUSES:
            problems.append(f"scripts/{name}: status {status!r} is not one of {sorted(STATUSES)}")
        for column, cell in zip(COLUMNS, cells):
            if not cell:
                problems.append(f"scripts/{name}: empty {column!r} cell")
    return problems


def test_every_top_level_script_has_exactly_one_valid_row() -> None:
    scripts = top_level_scripts(SCRIPTS)
    assert scripts, "found no scripts/*.py; the test is looking in the wrong place"
    problems = index_problems(README.read_text(encoding="utf-8"), scripts)
    assert not problems, "scripts/README.md is out of date:\n" + "\n".join(problems)


def test_every_table_header_uses_the_indexed_columns() -> None:
    headers = [line for line in README.read_text(encoding="utf-8").splitlines() if line.startswith("| Script |")]
    assert headers, "scripts/README.md has no index table"
    for header in headers:
        assert [c.strip() for c in header.strip().strip("|").split("|")] == list(COLUMNS), header


def _table(*rows: str) -> str:
    return "| Script | What it does | Status | Writes | Who runs it |\n|---|---|---|---|---|\n" + "\n".join(rows)


@pytest.mark.parametrize(
    ("text", "scripts", "expected"),
    [
        (_table("| `a.py` | does a | live | x | CI lane |"), {"a.py", "b.py"}, ["no row for scripts/b.py"]),
        (_table("| `a.py` | does a | live | x | CI lane |", "| `gone.py` | old | staged | y | owner |"),
         {"a.py"}, ["row for scripts/gone.py, which does not exist"]),
        (_table("| `a.py` | does a | live | x | CI lane |", "| `a.py` | again | live | x | CI lane |"),
         {"a.py"}, ["more than one row for scripts/a.py"]),
        (_table("| `a.py` | does a | retired | x | owner |"), {"a.py"},
         ["scripts/a.py: status 'retired' is not one of ['live', 'one-off and done', 'operator tool', 'staged']"]),
        (_table("| `a.py` | does a | live | x |"), {"a.py"},
         ["scripts/a.py: 4 cells, expected 5 ('Script', 'What it does', 'Status', 'Writes', 'Who runs it')"]),
        (_table("| `a.py` | does a | live |  | owner |"), {"a.py"}, ["scripts/a.py: empty 'Writes' cell"]),
        (_table("| `a.py` | does a | one-off and done | x | session |"), {"a.py"}, []),
    ],
)
def test_index_problems_names_each_defect(text: str, scripts: set[str], expected: list[str]) -> None:
    assert index_problems(text, scripts) == expected


def test_top_level_scripts_ignores_packages_and_dunder_modules(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text("")
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "inner.py").write_text("")
    assert top_level_scripts(tmp_path) == {"tool.py"}
