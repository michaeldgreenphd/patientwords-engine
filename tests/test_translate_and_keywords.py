import json

from medlang_circuits.keywords import CATEGORIES, load_keyword_config
from medlang_circuits.translate import translate_to_clinical


def test_load_keyword_config_placeholders_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(tmp_path / "nope.json"))
    monkeypatch.chdir(tmp_path)
    config = load_keyword_config()
    assert set(config) == set(CATEGORIES)
    assert all(isinstance(v, list) for v in config.values())


def test_load_keyword_config_from_env(tmp_path, monkeypatch):
    path = tmp_path / "keyword_config.json"
    path.write_text(json.dumps({"clinical": ["alpha"], "ignored_key": ["x"]}), encoding="utf-8")
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(path))
    config = load_keyword_config()
    assert config["clinical"] == ["alpha"]
    assert config["off_target"] == []
    assert "ignored_key" not in config


def test_translate_phrase_table(tmp_path, monkeypatch):
    path = tmp_path / "keyword_config.json"
    path.write_text(
        json.dumps({"translations": {"placeholder colloquial": "placeholder standard"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(path))
    result = translate_to_clinical("I said placeholder colloquial yesterday", use_llm=False)
    assert result == {"text": "I said placeholder standard yesterday", "method": "phrase_table"}


def test_translate_unchanged_without_table(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(tmp_path / "nope.json"))
    monkeypatch.chdir(tmp_path)
    result = translate_to_clinical("no table entry matches this", use_llm=False)
    assert result["method"] == "unchanged"
