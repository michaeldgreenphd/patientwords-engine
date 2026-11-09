"""scripts/check_candidate_pairs.py: mechanical checks run on hand-authored candidate pairs before anyone reads them."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_candidate_pairs.py"


def _mod():
    spec = importlib.util.spec_from_file_location("check_candidate_pairs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GOOD = {
    "id": "t-001",
    "top_prompt": "Since this morning I have had crushing chest pain so I need to go to the",
    "bottom_prompt": "Since this morning I have had a heavy squeezing in my chest so I need to go to the",
    "target_clinical_token": " ER",
    "swap_spans": {"clinical_span": "crushing chest pain", "patient_span": "a heavy squeezing in my chest"},
    "carrier_frame": "so I need to go to the",
    "clinical_tier_expected": 4,
    "expected_patient_continuations": [" doctor"],
}


def _check(*cands, **kw):
    kw.setdefault("sealed", lambda text: False)
    return _mod().check(list(cands), root=ROOT, **kw)


def _with(**changes):
    c = copy.deepcopy(GOOD)
    c.update(changes)
    return c


def test_a_well_formed_candidate_passes_with_nothing_to_look_at() -> None:
    assert _check(GOOD) == {"t-001": {"errors": [], "warnings": []}}


def _errors(cand, **kw) -> list[str]:
    return [m.split(":", 1)[0] for m in _check(cand, **kw)[cand["id"]]["errors"]]


def _warnings(cand, **kw) -> list[str]:
    return [m.split(":", 1)[0] for m in _check(cand, **kw)[cand["id"]]["warnings"]]


def test_shape_and_boundary_errors() -> None:
    assert _errors(_with(carrier_frame="")) == ["shape"]
    assert "shape" in _errors(_with(target_clinical_token="ER"))
    ended = _with(top_prompt=GOOD["top_prompt"] + ".", bottom_prompt=GOOD["bottom_prompt"] + ".")
    assert _errors(ended).count("boundary") == 4          # terminal punctuation and carrier frame, both sides
    twice = _check(GOOD, copy.deepcopy(GOOD))["t-001"]["errors"]
    assert any(m.startswith("shape: id appears 2 times") for m in twice)


def test_the_declared_edit_must_turn_the_clinical_side_into_the_everyday_side() -> None:
    assert _errors(_with(swap_spans={"clinical_span": "crushing chest pain", "patient_span": "chest ache"})) \
        == ["single_swap"]
    assert _errors(_with(swap_spans={"clinical_span": "chest pain in my chest", "patient_span": "x"})) \
        == ["single_swap"]
    assert _errors(_with(swap_spans=None)) == ["single_swap"]          # spans are required
    two_edits = _with(bottom_prompt="Since this evening I have had a heavy squeezing in my chest so I need to go to the")
    assert _errors(two_edits) == ["single_swap"]          # an edit outside the declared span


def test_insertions_and_misspellings_are_edits_too() -> None:
    mid = _with(bottom_prompt="Since this morning I have had crushing chest pain and I think it is just indigestion "
                              "so I need to go to the",
                swap_spans={"clinical_span": "", "patient_span": " and I think it is just indigestion"})
    assert _errors(mid) == []
    initial = _with(bottom_prompt="Maybe since this morning I have had crushing chest pain so I need to go to the",
                    swap_spans={"clinical_span": "", "patient_span": "Maybe "})
    assert _errors(initial) == []
    typo = _with(bottom_prompt="Since this morning I have had crushing chest pian so I need to go to the",
                 swap_spans=[{"correct": "pain", "misspelled": "pian"}])
    assert _errors(typo) == []
    both = _with(swap_spans={"clinical_span": "pain", "patient_span": "pian", "correct": "pain", "misspelled": "pian"},
                 bottom_prompt="Since this morning I have had crushing chest pian so I need to go to the")
    assert _errors(both) == []                            # the span recorded twice is one edit
    assert _errors(_with(swap_spans=[{"correct": "pain", "misspelled": "pian"}])) == ["single_swap"]


def test_duplicates_holdout_tier_and_style() -> None:
    assert [m for m in _check(GOOD, _with(id="t-002"))["t-002"]["errors"]] == ["duplicate: same pair as t-001"]
    committed = json.loads((ROOT / "data" / "simulated" / "agscen_r6_20261109.json").read_text(encoding="utf-8"))[0]
    copy_of = {"id": "t-003", "top_prompt": committed["top_prompt"], "bottom_prompt": committed["bottom_prompt"],
               "target_clinical_token": committed["target_clinical_token"],
               "swap_spans": committed["generation"]["swap_spans"],
               "carrier_frame": committed["generation"]["carrier_frame"], "clinical_tier_expected": 4}
    assert _errors(copy_of) == ["duplicate"]
    recheck = dict(copy_of, id=committed["generation"]["id"])
    assert _errors(recheck) == []                         # the committed pair itself, re-checked
    assert _errors(GOOD, sealed=lambda text: text == GOOD["bottom_prompt"]) == ["holdout"]
    assert _errors(_with(clinical_tier_expected=2)) == ["tier"]
    assert _errors(_with(top_prompt="Since this morning, I have had crushing chest pain so I need to go to the",
                         bottom_prompt="Since this morning, I have had a heavy squeezing in my chest so I need to go "
                                       "to the"), forbid=",;") == ["style", "style"]


def test_a_variant_copies_its_original_exactly() -> None:
    orig = json.loads((ROOT / "data" / "simulated" / "agscen_r6_20261109.json").read_text(encoding="utf-8"))[0]
    gen = orig["generation"]
    span = gen["swap_spans"]["patient_span"]
    variant = {"id": "t-v1", "variant_of": gen["id"], "top_prompt": orig["top_prompt"],
               "bottom_prompt": orig["top_prompt"].replace(gen["swap_spans"]["clinical_span"], span + " again"),
               "original_bottom_prompt": orig["bottom_prompt"],
               "target_clinical_token": orig["target_clinical_token"],
               "swap_spans": {"clinical_span": gen["swap_spans"]["clinical_span"], "patient_span": span + " again"},
               "carrier_frame": gen["carrier_frame"], "clinical_tier_expected": gen["tier_given"]}
    assert _errors(variant) == []
    assert _errors(dict(variant, original_bottom_prompt="x")) == ["original"]
    assert _errors(dict(variant, variant_of="no-such-id")) == ["original"]
    same = dict(variant, bottom_prompt=orig["bottom_prompt"], swap_spans=gen["swap_spans"])
    assert "original" in _errors(same)


def test_warnings_name_what_to_look_at() -> None:
    m = _mod()
    assert m.punct_counts("a, b; c-d") == {",": 1, ";": 1, "-": 1}
    hyphen = _with(top_prompt="Since this morning I have had crushing left-sided chest pain so I need to go to the",
                   swap_spans={"clinical_span": "crushing left-sided chest pain",
                               "patient_span": "a heavy squeezing in my chest"})
    assert _warnings(hyphen) == ["punctuation"]
    number = _with(top_prompt="Since this morning I have had a pulse of 34 so I need to go to the",
                   bottom_prompt="Since this morning I have had a slow pulse so I need to go to the",
                   swap_spans={"clinical_span": "a pulse of 34", "patient_span": "a slow pulse"})
    assert [w for w in _check(number)["t-001"]["warnings"]] == ["number: the everyday span drops ['34']"]
    assert _warnings(_with(target_clinical_token=" eye doctor", clinical_tier_expected=3)) \
        == ["target_vocab", "target_vocab"]
    assert _warnings(_with(lexicon_entries=["fell out"]), lexicon={"spell"}) == ["lexicon"]
    assert _warnings(_with(expected_patient_continuations=[" hospital"])) == ["prediction"]


def test_every_committed_agscen_file_passes_except_the_comma_twins_stale_spans() -> None:
    """The kept rounds pass. The -nocomma twins of the comma test kept their comma originals' spans (engine #158);
    no analysis reads those spans, so the file stays as committed and this pins the known finding."""
    m = _mod()
    for path in sorted((ROOT / "data" / "simulated").glob("agscen_*.json")):
        if path.name.endswith(".report.json"):
            continue
        report = m.check(json.loads(path.read_text(encoding="utf-8")), root=ROOT, exclude=path)
        failing = {cid for cid, r in report.items() if r["errors"]}
        if path.stem == "agscen_commas_20261109":
            assert failing == {f"sc-0{n}-nocomma" for n in (25, 27, 29, 31, 33, 35)}, failing
            assert all(r["errors"][0].startswith("single_swap: clinical_span occurs 0 times")
                       for cid, r in report.items() if cid in failing)
        else:
            assert not failing, (path.name, {c: report[c]["errors"] for c in failing})


def test_the_command_line_exits_1_on_an_error(tmp_path: Path) -> None:
    bad = tmp_path / "candidates.json"
    bad.write_text(json.dumps([_with(clinical_tier_expected=2)]), encoding="utf-8")
    out = tmp_path / "report.json"
    run = subprocess.run([sys.executable, str(SCRIPT), str(bad), "--out", str(out)], capture_output=True, text=True)
    assert run.returncode == 1 and "ERROR   t-001  tier:" in run.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["errors_by_check"] == {"tier": 1}
    bad.write_text(json.dumps([GOOD]), encoding="utf-8")
    assert subprocess.run([sys.executable, str(SCRIPT), str(bad)], capture_output=True).returncode == 0
