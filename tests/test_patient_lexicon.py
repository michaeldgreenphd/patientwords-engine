"""CHV lexicon derivation: exclusions, structural filters, ranking."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.build_patient_lexicon import CONCEPTS, INCORRECT, STOP, build, normalize

# 15-column flatfile rows with abstract placeholder terms (real vocabulary
# lives in data files, never in test source).
COLS = 15


def row(cui, term, chv_pref, umls_pref, disparaged="no", freq="0.5", combo="0.5",
        umls_flag="no", chv_flag="no"):
    r = [cui, term, chv_pref, umls_pref, "", umls_flag, chv_flag, disparaged,
         freq, "0", "0.5", combo, combo, "0000", "0001"]
    assert len(r) == COLS
    return "\t".join(r)


def write_chv(tmp_path: Path, concept_rows, stop_rows=(), incorrect_rows=()):
    d = tmp_path / "chv"
    d.mkdir()
    (d / CONCEPTS).write_text("\n".join(concept_rows) + "\n", encoding="utf-8")
    (d / STOP).write_text("CUI\tUMLS_NAME\n" + "".join(f"{c}\tx\n" for c in stop_rows),
                          encoding="utf-8")
    (d / INCORRECT).write_text("CUI\tUMLS_PREF\tINCORRECT\n"
                               + "".join(f"{c}\tx\t{t}\n" for c, t in incorrect_rows),
                               encoding="utf-8")
    return d


def test_basic_mapping_survives(tmp_path):
    d = write_chv(tmp_path, [row("C1", "zeta ache", "zeta ache", "omicron syndrome")])
    entries, counts = build(d, top=10)
    assert len(entries) == 1
    e = entries[0]
    assert e["lay"] == "zeta ache" and e["clinical"] == "omicron syndrome"
    assert counts["flatfile_rows"] == 1


def test_exclusions_stop_incorrect_disparaged(tmp_path):
    d = write_chv(
        tmp_path,
        [row("C1", "zeta ache", "z", "omicron syndrome"),
         row("C2", "kappa pain", "k", "upsilon disorder"),          # stop CUI
         row("C3", "lambda itch", "l", "rho condition"),            # incorrect mapping
         row("C4", "mu burn", "m", "sigma illness", disparaged="yes")],
        stop_rows=["C2"],
        incorrect_rows=[("C3", "lambda itch")],
    )
    entries, _ = build(d, top=10)
    assert [e["cui"] for e in entries] == ["C1"]


def test_structural_filters_drop_wording_trivia(tmp_path):
    d = write_chv(tmp_path, [
        row("C1", "bodies", "b", "body"),                    # shared 4-char stem prefix
        row("C2", "omicron pains", "o", "omicron pain"),     # plural-trivial
        row("C3", "sharp twinge", "s", "twinge event"),      # shared content token
        row("C4", "belly gripe", "b", "omicron colic"),      # genuine gap - survives
    ])
    entries, _ = build(d, top=10)
    assert [e["cui"] for e in entries] == ["C4"]


def test_best_per_cui_by_frequency_and_ranking(tmp_path):
    d = write_chv(tmp_path, [
        row("C1", "zeta ache", "z", "omicron syndrome", freq="0.2"),
        row("C1", "puffy zeta", "z", "omicron syndrome", freq="0.9"),
        row("C2", "kappa chill", "k", "upsilon disorder", freq="0.5"),
    ])
    entries, counts = build(d, top=10)
    assert [e["lay"] for e in entries] == ["puffy zeta", "kappa chill"]  # freq desc
    assert counts["concepts_with_lay_term"] == 2
    assert entries[0]["scores"]["frequency"] == 0.9


def test_top_cap_and_draft_labeling(tmp_path):
    d = write_chv(tmp_path, [
        row(f"C{i}", f"gamma{i} wobble", "g", f"delta{i} apraxia", freq=str(0.1 * i))
        for i in range(1, 6)
    ])
    entries, _ = build(d, top=2)
    assert len(entries) == 2
    # the CLI writes the draft label - run it end to end
    out = tmp_path / "lex.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_patient_lexicon.py"
    subprocess.run([sys.executable, str(script), "--chv-dir", str(d),
                    "--top", "2", "--out", str(out)], check=True, capture_output=True)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "draft pending domain review"
    assert "OAC" in payload["source"]
    assert len(payload["entries"]) == 2


def test_normalize_collapses_trivia():
    assert normalize("Omicron Pains") == normalize("omicron pain")
    assert normalize("zeta-ache!") == "zetaache"
