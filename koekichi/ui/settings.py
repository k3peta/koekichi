"""Hotkey settings dialog (SPEC §11.3).

Modal dialog opened from the tray menu. This dialog is allowed to take focus.
"""

import logging
import sys
from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from koekichi.hotkey import (
    DEFAULT_COMBO,
    DEFAULT_DOUBLE_TAP_KEY,
    is_valid_combo,
)

logger = logging.getLogger(__name__)

# Internal values are OS-independent; display names switch per OS (SPEC §11.3)
_MODIFIER_VALUES = ["alt", "ctrl", "shift", "cmd"]
_MODIFIER_LABELS_MAC = ["Option", "Ctrl", "Shift", "Cmd"]
_MODIFIER_LABELS_WIN = ["Alt", "Ctrl", "Shift", "Win"]


class SettingsDialog(QDialog):
    """Hotkey configuration dialog."""

    def __init__(
        self,
        hotkey_cfg: dict[str, Any],
        on_save: Callable[[dict[str, Any]], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("ホットキー設定")
        self.setModal(True)
        self._cfg = dict(hotkey_cfg)
        self._on_save = on_save

        labels = (
            _MODIFIER_LABELS_MAC if sys.platform == "darwin" else _MODIFIER_LABELS_WIN
        )

        layout = QVBoxLayout(self)

        # --- Radio A: double-tap ---
        self.radio_double = QRadioButton("修飾キー2回押し")
        layout.addWidget(self.radio_double)

        double_row = QHBoxLayout()
        double_row.addSpacing(24)
        self.key_box = QComboBox()
        for value, label in zip(_MODIFIER_VALUES, labels):
            self.key_box.addItem(label, value)
        double_row.addWidget(self.key_box)
        double_row.addStretch()
        layout.addLayout(double_row)

        # --- Radio B: combo ---
        self.radio_combo = QRadioButton("キーコンビネーション")
        layout.addWidget(self.radio_combo)

        combo_row = QHBoxLayout()
        combo_row.addSpacing(24)
        self.combo_edit = QLineEdit()
        self.combo_edit.setPlaceholderText(DEFAULT_COMBO)
        combo_row.addWidget(self.combo_edit)
        self.mode_box = QComboBox()
        self.mode_box.addItem("トグル", "toggle")
        self.mode_box.addItem("押している間だけ", "hold")
        combo_row.addWidget(self.mode_box)
        layout.addLayout(combo_row)

        # SPEC §13.1-A-2: Hold-to-record checkbox (double-tap mode only)
        self.hold_checkbox = QCheckBox("長押しでも録音(押している間だけ)")
        hold_row = QHBoxLayout()
        hold_row.addSpacing(24)
        hold_row.addWidget(self.hold_checkbox)
        hold_row.addStretch()
        layout.addLayout(hold_row)

        # --- Error label (red) ---
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d03030;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # --- Buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("キャンセル")
        buttons.accepted.connect(self._handle_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # --- Initial values from current config ---
        current_key = self._cfg.get("double_tap_key", DEFAULT_DOUBLE_TAP_KEY)
        idx = self.key_box.findData(current_key)
        self.key_box.setCurrentIndex(idx if idx >= 0 else 0)

        self.combo_edit.setText(self._cfg.get("combo", DEFAULT_COMBO))
        mode_idx = self.mode_box.findData(self._cfg.get("mode", "toggle"))
        self.mode_box.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)

        # SPEC §13.1-A-2: Initialize hold_to_record checkbox
        self.hold_checkbox.setChecked(self._cfg.get("hold_to_record", False))

        if self._cfg.get("type", "double-tap") == "combo":
            self.radio_combo.setChecked(True)
        else:
            self.radio_double.setChecked(True)

        # Enable/disable widgets per selected radio
        self.radio_double.toggled.connect(self._update_enabled_widgets)
        self.radio_combo.toggled.connect(self._update_enabled_widgets)
        self._update_enabled_widgets()

    def _update_enabled_widgets(self) -> None:
        double_selected = self.radio_double.isChecked()
        self.key_box.setEnabled(double_selected)
        self.combo_edit.setEnabled(not double_selected)
        self.mode_box.setEnabled(not double_selected)
        # SPEC §13.1-A-2: Hold checkbox enabled only in double-tap mode
        self.hold_checkbox.setEnabled(double_selected)

    def _handle_save(self) -> None:
        new_cfg = dict(self._cfg)

        if self.radio_combo.isChecked():
            combo = self.combo_edit.text().strip()
            if not is_valid_combo(combo):
                self.error_label.setText(
                    "無効なキーコンビネーションです(例: <ctrl>+<shift>+<space>)"
                )
                self.error_label.setVisible(True)
                return
            new_cfg["type"] = "combo"
            new_cfg["combo"] = combo
            new_cfg["mode"] = self.mode_box.currentData()
        else:
            new_cfg["type"] = "double-tap"
            new_cfg["double_tap_key"] = self.key_box.currentData()
            # SPEC §13.1-A-2: Save hold_to_record for double-tap mode
            new_cfg["hold_to_record"] = self.hold_checkbox.isChecked()

        self.error_label.setVisible(False)
        if self._on_save is not None:
            try:
                self._on_save(new_cfg)
            except Exception:
                logger.exception("Error in settings on_save callback")
        self.accept()
