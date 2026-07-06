"""Offscreen smoke tests for the dictionary editor dialog (SPEC §11.5).

Requires QT_QPA_PLATFORM=offscreen (set in CI / pytest invocation) since it
instantiates real PySide6 widgets.
"""

import json
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import koekichi.dictionary as dict_module
from koekichi.dictionary import load_dictionary, save_dictionary
from koekichi.ui.dictionary_editor import DictionaryEditorDialog


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def dict_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the dictionary module at a temp dictionary.json."""
    path = tmp_path / "dictionary.json"
    monkeypatch.setattr(dict_module, "get_dictionary_file", lambda: path)
    return path


class TestDictionaryEditorConstruction:
    """Test basic dialog construction."""

    def test_dialog_constructs_offscreen(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Dialog construction does not raise (offscreen)."""
        dialog = DictionaryEditorDialog()
        assert dialog is not None

    def test_dialog_is_modal(self, qapp: QApplication, dict_file: Path) -> None:
        """Dialog is modal."""
        from PySide6.QtCore import Qt

        dialog = DictionaryEditorDialog()
        assert dialog.isModal()

    def test_dialog_window_title(self, qapp: QApplication, dict_file: Path) -> None:
        """Dialog has correct title."""
        dialog = DictionaryEditorDialog()
        assert dialog.windowTitle() == "辞書を編集"


class TestDictionaryEditorLoading:
    """Test dictionary loading into the table."""

    def test_empty_dictionary_loads(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Empty dictionary loads with zero rows."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()
        assert dialog.table.rowCount() == 0

    def test_single_entry_loads(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Single entry loads into table."""
        save_dictionary(
            {
                "entries": [
                    {
                        "word": "Anthropic",
                        "reading": "アンソロピック",
                        "corrections": ["アンスロピック", "アンソロピク"],
                    }
                ]
            }
        )
        dialog = DictionaryEditorDialog()
        assert dialog.table.rowCount() == 1
        assert dialog.table.item(0, 0).text() == "Anthropic"
        assert dialog.table.item(0, 1).text() == "アンソロピック"
        # Corrections joined with "、"
        assert dialog.table.item(0, 2).text() == "アンスロピック、アンソロピク"

    def test_multiple_entries_load(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Multiple entries load in order."""
        save_dictionary(
            {
                "entries": [
                    {"word": "Word1", "reading": "よみ1", "corrections": []},
                    {"word": "Word2", "reading": "よみ2", "corrections": ["correction"]},
                ]
            }
        )
        dialog = DictionaryEditorDialog()
        assert dialog.table.rowCount() == 2
        assert dialog.table.item(0, 0).text() == "Word1"
        assert dialog.table.item(1, 0).text() == "Word2"

    def test_empty_corrections_list(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Entry with empty corrections list loads correctly."""
        save_dictionary(
            {"entries": [{"word": "TestWord", "reading": "よみ", "corrections": []}]}
        )
        dialog = DictionaryEditorDialog()
        assert dialog.table.item(0, 2).text() == ""

    def test_missing_reading_field(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Entry without reading field loads with empty reading cell."""
        save_dictionary(
            {
                "entries": [
                    {"word": "Word", "corrections": ["corr"]}
                    # No reading field
                ]
            }
        )
        dialog = DictionaryEditorDialog()
        assert dialog.table.item(0, 1).text() == ""
        assert dialog.table.item(0, 2).text() == "corr"


class TestDictionaryEditorTableManipulation:
    """Test adding and deleting rows."""

    def test_add_row_increases_count(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Clicking add button increases row count."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()
        assert dialog.table.rowCount() == 0

        dialog._add_row()
        assert dialog.table.rowCount() == 1
        # New cells are empty
        assert dialog.table.item(0, 0).text() == ""
        assert dialog.table.item(0, 1).text() == ""
        assert dialog.table.item(0, 2).text() == ""

    def test_add_multiple_rows(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Multiple add operations accumulate."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        dialog._add_row()
        dialog._add_row()
        dialog._add_row()
        assert dialog.table.rowCount() == 3

    def test_delete_selected_row(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Delete removes the selected row."""
        save_dictionary(
            {
                "entries": [
                    {"word": "A"},
                    {"word": "B"},
                    {"word": "C"},
                ]
            }
        )
        dialog = DictionaryEditorDialog()
        assert dialog.table.rowCount() == 3

        # Select second row and delete
        dialog.table.selectRow(1)
        dialog._delete_selected_row()

        assert dialog.table.rowCount() == 2
        # Verify remaining rows
        assert dialog.table.item(0, 0).text() == "A"
        assert dialog.table.item(1, 0).text() == "C"

    def test_delete_with_no_selection(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Delete with no selection does nothing."""
        save_dictionary(
            {
                "entries": [
                    {"word": "A"},
                    {"word": "B"},
                ]
            }
        )
        dialog = DictionaryEditorDialog()
        initial_count = dialog.table.rowCount()

        dialog._delete_selected_row()

        # No change
        assert dialog.table.rowCount() == initial_count


class TestDictionaryEditorSaving:
    """Test save logic and file write."""

    def test_save_with_no_changes_writes_same_content(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Saving without changes writes the same dictionary."""
        original = {
            "entries": [
                {
                    "word": "Anthropic",
                    "reading": "アンソロピック",
                    "corrections": ["アンスロピック"],
                }
            ]
        }
        save_dictionary(original)

        dialog = DictionaryEditorDialog()
        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)

        # Save without changes
        dialog._handle_save()

        # Verify file content
        assert dict_file.exists()
        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == original

    def test_save_skips_empty_word_rows(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Rows with empty word field are ignored on save."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        # Add three rows
        dialog._add_row()
        dialog._add_row()
        dialog._add_row()

        # Set only rows 0 and 2
        dialog.table.item(0, 0).setText("Word1")
        dialog.table.item(2, 0).setText("Word2")
        # Row 1 is empty

        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)
        dialog._handle_save()

        # Only 2 entries should be saved
        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved["entries"]) == 2
        assert saved["entries"][0]["word"] == "Word1"
        assert saved["entries"][1]["word"] == "Word2"

    def test_save_splits_corrections_by_comma(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Corrections are split by both "、" and ","."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        dialog._add_row()
        dialog.table.item(0, 0).setText("Word")
        dialog.table.item(0, 2).setText("corr1、corr2,corr3")

        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)
        dialog._handle_save()

        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved["entries"]) == 1
        assert saved["entries"][0]["corrections"] == ["corr1", "corr2", "corr3"]

    def test_save_trims_whitespace_from_corrections(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Correction strings have whitespace trimmed."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        dialog._add_row()
        dialog.table.item(0, 0).setText("Word")
        dialog.table.item(0, 2).setText("  corr1  、  corr2  ")

        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)
        dialog._handle_save()

        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["entries"][0]["corrections"] == ["corr1", "corr2"]

    def test_save_excludes_empty_corrections(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Empty correction strings (after trim) are excluded."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        dialog._add_row()
        dialog.table.item(0, 0).setText("Word")
        # Multiple delimiters with only whitespace between them
        dialog.table.item(0, 2).setText("corr1、、   、corr2")

        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)
        dialog._handle_save()

        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["entries"][0]["corrections"] == ["corr1", "corr2"]

    def test_save_calls_on_save_callback(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """on_save callback is called after successful save."""
        save_dictionary({"entries": []})
        callback_called = []

        def on_save_cb():
            callback_called.append(True)

        dialog = DictionaryEditorDialog(on_save=on_save_cb)
        dialog._add_row()
        dialog.table.item(0, 0).setText("Word")

        dialog._handle_save()

        assert len(callback_called) == 1

    def test_cancel_does_not_call_on_save_callback(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """on_save callback is NOT called on cancel."""
        save_dictionary({"entries": []})
        callback_called = []

        def on_save_cb():
            callback_called.append(True)

        dialog = DictionaryEditorDialog(on_save=on_save_cb)
        dialog.reject()

        assert len(callback_called) == 0

    def test_save_preserves_reading_field(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Reading field is preserved in saved entry."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        dialog._add_row()
        dialog.table.item(0, 0).setText("Word")
        dialog.table.item(0, 1).setText("よみ")
        dialog.table.item(0, 2).setText("corr")

        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)
        dialog._handle_save()

        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["entries"][0]["reading"] == "よみ"

    def test_save_with_empty_reading_stores_empty_string(
        self, qapp: QApplication, dict_file: Path
    ) -> None:
        """Empty reading field is stored as empty string (optional field)."""
        save_dictionary({"entries": []})
        dialog = DictionaryEditorDialog()

        dialog._add_row()
        dialog.table.item(0, 0).setText("Word")
        dialog.table.item(0, 1).setText("")
        dialog.table.item(0, 2).setText("corr")

        on_save_called = []
        dialog._on_save = lambda: on_save_called.append(True)
        dialog._handle_save()

        with open(dict_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["entries"][0]["reading"] == ""
