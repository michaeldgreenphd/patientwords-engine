"""Readability worklist: scoring heuristics."""
from scripts.readability_report import score, syllables, visible_text


def test_syllable_heuristic():
    assert syllables("cat") == 1
    assert syllables("probability") == 5
    assert syllables("free") == 1  # trailing-e rule spares 'ee'


def test_visible_text_strips_script_style():
    html = "<style>p{color:red}</style><p>Kept prose.</p><script>var x=1;</script>"
    assert visible_text(html) == "Kept prose."


def test_score_short_text_is_none():
    assert score("Too short to score.") is None


def test_simple_text_scores_lower_than_dense_text():
    simple = "The dog ran to the park. " * 20
    dense = ("Mechanistic interpretability of probabilistic representations "
             "necessitates considerable methodological sophistication. " * 20)
    assert score(simple)["fk_grade"] < score(dense)["fk_grade"]
