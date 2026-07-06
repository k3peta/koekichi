"""Dictionary editor dialog (SPEC §11.5).

Modal dialog opened from the tray menu ("辞書を編集…"). Allows the user to
add, remove, and edit dictionary entries via a QTableWidget.
"""

import logging
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from koekichi.dictionary import load_dictionary, save_dictionary

logger = logging.getLogger(__name__)


class DictionaryEditorDialog(QDialog):
    """Dialog for editing the user dictionary via a table."""

    def __init__(
        self,
        on_save: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("辞書を編集")
        self.setModal(True)
        self.resize(560, 400)
        self._on_save = on_save

        layout = QVBoxLayout(self)

        # Table with 3 columns: word / reading / corrections
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["単語", "読み", "誤認識パターン"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # Buttons: Add row, Delete row, Save, Cancel
        button_layout = QVBoxLayout()

        self.add_button = QPushButton("行を追加")
        self.add_button.clicked.connect(self._add_row)
        button_layout.addWidget(self.add_button)

        self.delete_button = QPushButton("選択行を削除")
        self.delete_button.clicked.connect(self._delete_selected_row)
        button_layout.addWidget(self.delete_button)

        button_layout.addStretch()

        # Dialog buttons (Save/Cancel)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("キャンセル")
        buttons.accepted.connect(self._handle_save)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)

        layout.addLayout(button_layout)

        # Load dictionary entries into table
        self._load_entries()

    def _load_entries(self) -> None:
        """Load dictionary entries from disk and populate the table."""
        dictionary = load_dictionary()
        entries = dictionary.get("entries", [])

        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            word = entry.get("word", "")
            reading = entry.get("reading", "")
            corrections = entry.get("corrections", [])

            # Join corrections with "、" for display
            corrections_text = "、".join(corrections) if corrections else ""

            self.table.setItem(row, 0, QTableWidgetItem(word))
            self.table.setItem(row, 1, QTableWidgetItem(reading))
            self.table.setItem(row, 2, QTableWidgetItem(corrections_text))

    def _add_row(self) -> None:
        """Add an empty row at the end of the table."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))
        self.table.setItem(row, 2, QTableWidgetItem(""))

    def _delete_selected_row(self) -> None:
        """Delete the currently selected row."""
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)

    def _handle_save(self) -> None:
        """Save changes to the dictionary file."""
        entries = []

        for row in range(self.table.rowCount()):
            word_item = self.table.item(row, 0)
            reading_item = self.table.item(row, 1)
            corrections_item = self.table.item(row, 2)

            word = word_item.text() if word_item else ""
            reading = reading_item.text() if reading_item else ""
            corrections_text = corrections_item.text() if corrections_item else ""

            # Skip rows where word is empty (SPEC §11.5)
            if not word.strip():
                continue

            # Parse corrections: split by both "、" and "," (SPEC §11.5)
            corrections = []
            if corrections_text:
                # Split by both separators
                parts = corrections_text.replace("、", ",").split(",")
                for part in parts:
                    trimmed = part.strip()
                    if trimmed:  # Skip empty strings
                        corrections.append(trimmed)

            entry = {
                "word": word.strip(),
                "reading": reading.strip() if reading.strip() else "",
                "corrections": corrections,
            }
            entries.append(entry)

        # Save to dictionary.json
        dictionary = {"entries": entries}
        try:
            save_dictionary(dictionary)
            logger.info("Dictionary saved from editor dialog")

            # Call on_save callback if provided
            if self._on_save is not None:
                self._on_save()

            self.accept()
        except Exception as e:
            logger.error(f"Failed to save dictionary: {e}")
