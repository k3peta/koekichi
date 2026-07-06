"""Test dictionary loading and corrections (SPEC §10)."""

import json
import tempfile
from pathlib import Path

import pytest

import koekichi.dictionary as dict_module
from koekichi.dictionary import (
    apply_corrections,
    dictionary_mtime,
    get_dictionary_words,
    load_dictionary,
    load_dictionary_if_changed,
)


class TestDictionaryLoading:
    """Test dictionary loading and parsing."""

    def test_load_empty_dictionary(self) -> None:
        """Load empty dictionary structure."""
        dictionary = {"entries": []}
        words = get_dictionary_words(dictionary)
        assert words == []

    def test_load_single_entry(self) -> None:
        """Load dictionary with single entry."""
        dictionary = {
            "entries": [
                {
                    "word": "Anthropic",
                    "reading": "アンソロピック",
                }
            ]
        }
        words = get_dictionary_words(dictionary)
        assert words == ["Anthropic"]

    def test_load_multiple_entries(self) -> None:
        """Load dictionary with multiple entries."""
        dictionary = {
            "entries": [
                {"word": "word1"},
                {"word": "word2"},
                {"word": "word3"},
            ]
        }
        words = get_dictionary_words(dictionary)
        assert words == ["word1", "word2", "word3"]

    def test_reading_optional(self) -> None:
        """Reading field is optional."""
        dictionary = {
            "entries": [
                {"word": "Anthropic"},  # No reading
            ]
        }
        words = get_dictionary_words(dictionary)
        assert words == ["Anthropic"]

    def test_skip_entries_without_word(self) -> None:
        """Skip entries that don't have 'word' field."""
        dictionary = {
            "entries": [
                {"reading": "only reading, no word"},
                {"word": "valid word"},
            ]
        }
        words = get_dictionary_words(dictionary)
        assert words == ["valid word"]


class TestApplyCorrections:
    """Test dictionary corrections application."""

    def test_no_corrections(self) -> None:
        """Text unchanged when no corrections."""
        text = "テスト"
        dictionary = {"entries": []}
        result = apply_corrections(text, dictionary)
        assert result == text

    def test_single_correction(self) -> None:
        """Apply single correction."""
        text = "アンスロピック"
        dictionary = {
            "entries": [
                {
                    "word": "Anthropic",
                    "corrections": ["アンスロピック"],
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "Anthropic"

    def test_multiple_corrections_for_single_word(self) -> None:
        """Apply multiple corrections for same word."""
        text = "アンスロピックとアンソロピク"
        dictionary = {
            "entries": [
                {
                    "word": "Anthropic",
                    "corrections": ["アンスロピック", "アンソロピク"],
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "AnthropicとAnthropic"

    def test_corrections_longest_first(self) -> None:
        """Corrections applied in descending order of length."""
        # If we apply short correction first, it might destroy the long one
        text = "abcde"
        dictionary = {
            "entries": [
                {
                    "word": "X",
                    "corrections": ["ab", "abcde"],  # Both match
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        # Longest first: "abcde" → "X", then "ab" has nothing to match
        assert result == "X"

    def test_longest_correction_order(self) -> None:
        """Verify longest corrections are applied first."""
        text = "abcdefg"
        dictionary = {
            "entries": [
                {
                    "word": "X",
                    "corrections": ["abc", "abcdefg"],  # Short and long
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        # Should apply "abcdefg" → "X" first (longest)
        # If we applied "abc" first, we'd get "Xdefg" then "Xdefg" (no more matches)
        # If we apply "abcdefg" first, we get "X"
        assert result == "X"

    def test_multiple_entries_corrections(self) -> None:
        """Apply corrections from multiple entries."""
        text = "テストとサンプル"
        dictionary = {
            "entries": [
                {
                    "word": "Test",
                    "corrections": ["テスト"],
                },
                {
                    "word": "Sample",
                    "corrections": ["サンプル"],
                },
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "TestとSample"

    def test_no_corrections_field(self) -> None:
        """Skip entries without corrections field."""
        text = "テスト"
        dictionary = {
            "entries": [
                {
                    "word": "Word",
                    # No corrections field
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "テスト"

    def test_empty_corrections_list(self) -> None:
        """Skip entries with empty corrections list."""
        text = "テスト"
        dictionary = {
            "entries": [
                {
                    "word": "Word",
                    "corrections": [],
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "テスト"

    def test_repeated_corrections(self) -> None:
        """Handle multiple occurrences of same correction."""
        text = "テストテストテスト"
        dictionary = {
            "entries": [
                {
                    "word": "Test",
                    "corrections": ["テスト"],
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "TestTestTest"

    def test_empty_correction_skipped(self) -> None:
        """Empty string corrections must be skipped (no runaway replace)."""
        text = "テスト"
        dictionary = {
            "entries": [
                {
                    "word": "X",
                    "corrections": ["", "テスト"],
                }
            ]
        }
        result = apply_corrections(text, dictionary)
        assert result == "X"


class TestMtimeReload:
    """Test mtime-based dictionary reload (SPEC §10.4)."""

    @pytest.fixture
    def dict_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point the dictionary module at a temp dictionary.json."""
        path = tmp_path / "dictionary.json"
        monkeypatch.setattr(dict_module, "get_dictionary_file", lambda: path)
        return path

    def test_mtime_missing_file_is_zero(self, dict_file: Path) -> None:
        """dictionary_mtime returns 0.0 when file does not exist."""
        assert dictionary_mtime() == 0.0

    def test_mtime_of_existing_file(self, dict_file: Path) -> None:
        """dictionary_mtime returns file mtime when file exists."""
        dict_file.write_text('{"entries": []}', encoding="utf-8")
        assert dictionary_mtime() == dict_file.stat().st_mtime

    def test_reload_when_changed(self, dict_file: Path) -> None:
        """load_dictionary_if_changed reloads when mtime differs."""
        dict_file.write_text(
            json.dumps({"entries": [{"word": "A"}]}), encoding="utf-8"
        )
        loaded, mtime = load_dictionary_if_changed(0.0)
        assert loaded is not None
        assert get_dictionary_words(loaded) == ["A"]
        assert mtime == dict_file.stat().st_mtime

    def test_no_reload_when_unchanged(self, dict_file: Path) -> None:
        """load_dictionary_if_changed returns (None, last_mtime) when unchanged."""
        dict_file.write_text('{"entries": []}', encoding="utf-8")
        current = dictionary_mtime()
        loaded, mtime = load_dictionary_if_changed(current)
        assert loaded is None
        assert mtime == current

    def test_reload_after_modification(self, dict_file: Path) -> None:
        """Modifying the file (new mtime) triggers a reload."""
        import os

        dict_file.write_text('{"entries": []}', encoding="utf-8")
        _, mtime1 = load_dictionary_if_changed(0.0)

        dict_file.write_text(
            json.dumps({"entries": [{"word": "B"}]}), encoding="utf-8"
        )
        # Force a distinct mtime (filesystem timestamp resolution)
        os.utime(dict_file, (dict_file.stat().st_atime, mtime1 + 10))

        loaded, mtime2 = load_dictionary_if_changed(mtime1)
        assert loaded is not None
        assert get_dictionary_words(loaded) == ["B"]
        assert mtime2 != mtime1


class TestLegacyKoeKichiWinMigration:
    """A KoeKichiWin-era dictionary.json in the shared %APPDATA%/KoeKichi
    folder must be converted on load, not treated as empty (and later
    clobbered by the editor's save)."""

    @pytest.fixture
    def dict_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point the dictionary module at a temp dictionary.json."""
        path = tmp_path / "dictionary.json"
        monkeypatch.setattr(dict_module, "get_dictionary_file", lambda: path)
        return path

    def _write_legacy(self, path: Path, replacements: list) -> None:
        path.write_text(
            json.dumps(
                {"version": 1, "replacements": replacements}, ensure_ascii=False
            ),
            encoding="utf-8",
        )

    def test_legacy_replacements_become_entries(self, dict_file: Path) -> None:
        """Literal replacements are grouped by their "to" word."""
        self._write_legacy(
            dict_file,
            [
                {"from": "\u58f0\u57fa\u5730", "to": "\u58f0\u5409", "mode": "literal"},
                {"from": "\u58f0\u30ad\u30c1", "to": "\u58f0\u5409", "mode": "literal"},
                {"from": "\u30aa\u30fc\u30d7\u30f3AI", "to": "OpenAI", "mode": "literal"},
            ],
        )
        loaded = load_dictionary()
        assert loaded == {
            "entries": [
                {
                    "word": "\u58f0\u5409",
                    "reading": "",
                    "corrections": ["\u58f0\u57fa\u5730", "\u58f0\u30ad\u30c1"],
                },
                {"word": "OpenAI", "reading": "", "corrections": ["\u30aa\u30fc\u30d7\u30f3AI"]},
            ]
        }

    def test_migration_persists_and_backs_up(self, dict_file: Path) -> None:
        """The legacy file is backed up, then rewritten in the new schema."""
        self._write_legacy(dict_file, [{"from": "a", "to": "b", "mode": "literal"}])
        load_dictionary()
        backup = dict_file.with_name("dictionary.json.koekichiwin.bak")
        assert backup.exists()
        assert json.loads(backup.read_text(encoding="utf-8"))["version"] == 1
        on_disk = json.loads(dict_file.read_text(encoding="utf-8"))
        assert on_disk == {
            "entries": [{"word": "b", "reading": "", "corrections": ["a"]}]
        }

    def test_non_literal_modes_are_skipped(self, dict_file: Path) -> None:
        """Only literal replacements can be expressed as corrections."""
        self._write_legacy(
            dict_file,
            [
                {"from": "x+", "to": "y", "mode": "regex"},
                {"from": "a", "to": "b", "mode": "literal"},
            ],
        )
        loaded = load_dictionary()
        assert loaded == {
            "entries": [{"word": "b", "reading": "", "corrections": ["a"]}]
        }

    def test_current_schema_untouched(self, dict_file: Path) -> None:
        """A current-schema file is returned as-is, with no backup created."""
        current = {"entries": [{"word": "w", "reading": "", "corrections": []}]}
        dict_file.write_text(json.dumps(current), encoding="utf-8")
        assert load_dictionary() == current
        assert not dict_file.with_name(
            "dictionary.json.koekichiwin.bak"
        ).exists()

    def test_corrections_applied_after_migration(self, dict_file: Path) -> None:
        """Migrated entries feed the normal corrections pipeline."""
        self._write_legacy(
            dict_file,
            [{"from": "\u58f0\u57fa\u5730", "to": "\u58f0\u5409", "mode": "literal"}],
        )
        loaded = load_dictionary()
        assert (
            apply_corrections("\u58f0\u57fa\u5730\u3092\u8d77\u52d5", loaded)
            == "\u58f0\u5409\u3092\u8d77\u52d5"
        )
