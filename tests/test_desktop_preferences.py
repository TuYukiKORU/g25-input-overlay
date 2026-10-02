import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from desktop_preferences import DesktopPreferences


def test_language_persists_independently_of_http_port_and_webview(tmp_path):
    preferences = DesktopPreferences(tmp_path)
    preferences.save_language("ja")
    assert DesktopPreferences(tmp_path).language == "ja"
    preferences.save_language("en")
    assert DesktopPreferences(tmp_path).language == "en"


def test_language_update_preserves_other_preferences(tmp_path):
    (tmp_path / "preferences.json").write_text(json.dumps({"language": "en", "future_option": 42}), encoding="utf-8")
    DesktopPreferences(tmp_path).save_language("ja")
    assert json.loads((tmp_path / "preferences.json").read_text())["future_option"] == 42


@pytest.mark.parametrize("value", ["fr", "", None, ["ja"]])
def test_unsupported_language_does_not_change_preferences(tmp_path, value):
    preferences = DesktopPreferences(tmp_path)
    before = preferences.language
    with pytest.raises(ValueError):
        preferences.save_language(value)
    assert preferences.language == before
    assert not preferences.path.exists()


@pytest.mark.parametrize("content", ["bad json", "[]", "null", '{"language":"invalid"}'])
def test_corrupt_preferences_recover_on_next_save(tmp_path, content):
    (tmp_path / "preferences.json").write_text(content, encoding="utf-8")
    preferences = DesktopPreferences(tmp_path)
    assert preferences.language in ("en", "ja")
    preferences.save_language("ja")
    assert DesktopPreferences(tmp_path).language == "ja"
