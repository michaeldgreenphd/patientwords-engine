"""The spend-accounting step of the daily Routine, against the prompt that
drives it (docs/routine_standing_prompt.md) and the script it names
(scripts/ledger_update.py).

The 2026-08-29 maintenance rewrite of the prompt (fd5304c9) dropped its
"§3 · Account" step, which ran `python scripts/ledger_update.py`, and nothing
else ran the script. Every dashboard commit from the last fold
(2026-08-28T12:50:56Z) through the 2026-09-22 Routine, 57 of them, carried the
same `spend` block, so `spend.today` stayed dated 2026-08-28 and
fire_trigger.py's landed term read 0.00 in every budget check after it. Nothing
checked that the prompt still ran the fold; these tests are the check, so a
future slimming of the prompt cannot drop the step without failing the suite.
They read the prompt's sections by heading rather than by a bare substring
search, because a mention of the script elsewhere (the §6 writer note) must not
satisfy the check that a step runs it."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ledger_update  # noqa: E402
from scripts.petri_audit import reconcile  # noqa: E402

PROMPT = (ROOT / "docs" / "routine_standing_prompt.md").read_text(encoding="utf-8")
FOLD_COMMAND = "python scripts/ledger_update.py"


def _sections(text: str) -> list[tuple[str, str]]:
    """[(section number, body)] for every `## <number> · <title>` heading, in
    order. The number is the token before the middle dot ("2", "2a", "6");
    headings without one (e.g. "Boundaries (absolute)") are not cycle steps."""
    out: list[tuple[str, str]] = []
    parts = re.split(r"^## ", text, flags=re.M)
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        m = re.match(r"(\w+) · ", heading)
        if m:
            out.append((m.group(1), body))
    return out


def test_the_script_the_prompt_runs_exists() -> None:
    assert (ROOT / "scripts" / "ledger_update.py").is_file()


def test_exactly_one_cycle_step_runs_the_fold_and_it_sits_between_harvest_and_the_first_fire() -> None:
    """The fold follows the harvest (sidecars that landed are on disk) and
    precedes §3, whose fires need a checkout with nothing modified but the
    dashboard and one fire (fire_trigger.py publish refuses anything else)."""
    sections = _sections(PROMPT)
    numbers = [n for n, _ in sections]
    running = [n for n, body in sections if FOLD_COMMAND in body]
    assert running == ["2a"], running
    assert numbers.index("2") < numbers.index("2a") < numbers.index("3"), numbers


# Lettered step labels of the prompt before the 2026-08-29 maintenance rewrite (`git show fd5304c9^:
# docs/routine_standing_prompt.md`), with what each named then. Committed documents still cite them in that
# sense: §2b in the doc-accuracy audits, docs/audits/seal_incident_20260721.md, docs/decisions_20260815_owner.md
# and the August decks. The restored fold first shipped as "2b", with a note claiming the label kept existing
# citations valid; it sent every one of them to the spend fold instead (2026-09-23 review).
RETIRED_LABELS = {"2b": "Integrity checks", "4b": "Endpoint guard", "6b": "Watchdog"}


def test_no_step_reuses_a_label_that_meant_another_step() -> None:
    reused = {n: RETIRED_LABELS[n] for n, _ in _sections(PROMPT) if n in RETIRED_LABELS}
    assert not reused, f"retired labels reused (they meant: {reused})"


def test_every_skill_that_describes_the_routines_dashboard_commit_names_the_fold_step() -> None:
    """The fold step commits the dashboard before §3, so "the Routine commits the dashboard in step 6" is no
    longer the whole story. The first version updated the daily-ops-cycle skill and missed the same sentence in
    fire-trigger-safe (2026-09-23 review). The label comes from the prompt, so renumbering the step without
    updating the skills fails here too."""
    label = next(n for n, body in _sections(PROMPT) if FOLD_COMMAND in body)
    describing = {}
    for path in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"commits the dashboard|dashboard commits?\b", text, flags=re.I):
            describing[path.parent.name] = f"§{label}" in text or f"section {label}" in text
    # never vacuous: the two skills that carried the sentence when this test was written must still be found
    assert {"daily-ops-cycle", "fire-trigger-safe"} <= set(describing), sorted(describing)
    missing = sorted(name for name, names_it in describing.items() if not names_it)
    assert not missing, f"skills describing the Routine's dashboard commit without naming §{label}: {missing}"


def test_the_fold_step_commits_both_outputs_together() -> None:
    """The ledger bullets and spend.entries_seen are two halves of one record:
    a dashboard committed alone loses the trail, bullets committed alone are
    written again by the next fold."""
    body = dict(_sections(PROMPT))["2a"]
    assert "ONE commit" in body and "ops/dashboard.json" in body and "docs/*ledger*.md" in body, body


def test_the_fold_step_names_every_dashboard_key_the_script_writes_beyond_spend() -> None:
    """The first version of the step said the script folds sidecars "into the `spend` block", but a run also
    stamps `updated_utc` and can write `tierb`. The Routine was told never to hand-edit what it wrote, so it
    would have carried a 1703/1600 Tier B count as real (2026-09-23 review). The step names both keys and the
    `note:` lines the script prints for a haiku batch it keeps out of the closed campaign."""
    body = dict(_sections(PROMPT))["2a"]
    for token in ("`updated_utc`", "`tierb`", "`note:`", "pairs_20260721T132205Z"):
        assert token in body, token


def test_the_dashboard_section_names_spend_and_its_only_writer() -> None:
    """§6 lists the dashboard sections the Routine rewrites. Without `spend`
    there, with its writer named, a Routine that rebuilds the file from an
    earlier copy undoes the fold it committed in §2a."""
    body = dict(_sections(PROMPT))["6"]
    assert "`spend`" in body and "scripts/ledger_update.py" in body, body


def test_the_bare_invocation_scans_the_directory_petri_writes() -> None:
    """The prompt runs the script with no arguments, so its default Petri
    directory has to be the one the lane's CLI writes run directories into."""
    default = Path(ledger_update.parse_args([]).petri_dir)
    assert not default.is_absolute()
    assert ROOT / default == reconcile.DEFAULT_RUNS_DIR


def test_the_bare_invocation_folds_a_petri_runs_two_sidecars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end from a scratch checkout: `python scripts/ledger_update.py`
    with no arguments books both the run sidecar and the judge sidecar that
    petri_audit.yml commits under data/petri/runs/<run>/, to the run's UTC day
    and the channel the sidecar names. Shapes follow the 2026-09-23 wave-2
    sidecars (the judge one is cumulative with run_cost_usd equal to its
    cost_usd)."""
    monkeypatch.chdir(tmp_path)
    stem = "run_35812312136_1"
    run_dir = tmp_path / "data" / "petri" / "runs" / stem
    run_dir.mkdir(parents=True)
    (run_dir / f"{stem}.report.json").write_text(json.dumps(
        {"cost_usd": 0.927362, "billing_channel": "anthropic", "run_utc": "2026-09-23T02:57:12Z",
         "cost_basis": "engine_repriced_from_inspect_model_usage", "journal_nonce": "w2e2"}), encoding="utf-8")
    (run_dir / f"{stem}.judge.report.json").write_text(json.dumps(
        {"cost_usd": 1.607517, "run_cost_usd": 1.607517, "billing_channel": "anthropic",
         "run_utc": "2026-09-23T03:14:49Z", "cost_basis": "cumulative_from_records"}), encoding="utf-8")

    assert ledger_update.main(["--date", "2026-09-25"]) == 0

    spend = json.loads((tmp_path / "ops" / "dashboard.json").read_text(encoding="utf-8"))["spend"]
    assert sorted(spend["entries_seen"]) == [f"{stem}.judge.report.json", f"{stem}.report.json"]
    assert spend["by_day"] == {"2026-09-23": 2.5349}   # each addition is rounded to four decimals
    assert spend["by_day_by_channel"] == {"anthropic": {"2026-09-23": 2.5349}}
    ledger = (tmp_path / "docs" / "spend_ledger.md").read_text(encoding="utf-8")
    assert f"- {stem}.report.json · $0.9274 ·" in ledger and f"- {stem}.judge.report.json · $1.6075 ·" in ledger

    # idempotent: a second run the same cycle finds nothing and writes nothing
    before = (tmp_path / "ops" / "dashboard.json").read_bytes(), ledger
    assert ledger_update.main(["--date", "2026-09-25"]) == 0
    after = (tmp_path / "ops" / "dashboard.json").read_bytes(), (tmp_path / "docs" / "spend_ledger.md").read_text(
        encoding="utf-8")
    assert after == before
