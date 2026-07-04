"""System tray / menu bar icon (SPEC §11.2).

Icon is drawn in code with QPainter (simple leaf shape, distinct from the
OS's own microphone/audio glyphs); color changes with state (idle =
gray/white, recording = red, transcribing = blue).
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from koekichi.config import get_config_file
from koekichi.dictionary import get_dictionary_file
from koekichi.paths import get_config_dir

logger = logging.getLogger(__name__)

STATE_COLORS = {
    "idle": QColor(200, 200, 200),
    "recording": QColor(235, 70, 70),
    "transcribing": QColor(80, 140, 240),
}


def open_path(path: Path) -> None:
    """Open a file with the OS default application."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        logger.error(f"Failed to open {path}: {e}")


def _make_leaf_icon(color: QColor) -> QIcon:
    """
    Draw a simple monochrome leaf icon with QPainter (no external assets).

    Deliberately not a microphone glyph: menu-bar mic icons are easily
    confused with the OS's own audio/recording indicators. A leaf reads
    as distinct at a glance while still fitting the same color-coded
    state scheme (idle/recording/transcribing).
    """
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Leaf silhouette: pointed at both the bottom tip and the top, wide
    # belly at mid-height, traced with two symmetric bezier curves.
    leaf = QPainterPath()
    leaf.moveTo(32, 58)
    leaf.cubicTo(3, 44, 25, 5, 32, 3)
    leaf.cubicTo(39, 5, 61, 44, 32, 58)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(leaf)

    # Center vein: punched through as a thin transparent line so it reads
    # cleanly against any of the state colors.
    painter.setCompositionMode(QPainter.CompositionMode_Clear)
    vein_pen = QPen(Qt.black, 2)
    vein_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(vein_pen)
    painter.drawLine(32, 13, 32, 51)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    # Short stem below the tip
    stem_pen = QPen(color, 3)
    stem_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(stem_pen)
    painter.drawLine(32, 58, 32, 62)

    painter.end()
    return QIcon(pixmap)


class Tray(QSystemTrayIcon):
    """System tray icon with state colors and control menu."""

    def __init__(
        self,
        config: dict[str, Any],
        on_toggle_recording: Callable[[], None] | None = None,
        on_enabled_changed: Callable[[bool], None] | None = None,
        on_reload_dictionary: Callable[[], None] | None = None,
        on_retry_engine_load: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self._icons = {
            state: _make_leaf_icon(color) for state, color in STATE_COLORS.items()
        }
        self._state = "idle"
        self.setIcon(self._icons["idle"])
        self.setToolTip("KoeKichi")

        self._on_toggle_recording = on_toggle_recording
        self._on_enabled_changed = on_enabled_changed
        self._on_reload_dictionary = on_reload_dictionary
        self._on_retry_engine_load = on_retry_engine_load
        self._on_quit = on_quit
        self._on_open_settings = on_open_settings

        self._menu = QMenu()

        self._record_action = QAction("録音開始", self._menu)
        self._record_action.triggered.connect(self._handle_toggle_recording)
        self._menu.addAction(self._record_action)

        self._enabled_action = QAction("有効", self._menu)
        self._enabled_action.setCheckable(True)
        self._enabled_action.setChecked(True)
        self._enabled_action.toggled.connect(self._handle_enabled_toggled)
        self._menu.addAction(self._enabled_action)

        self._menu.addSeparator()

        settings_action = QAction("ホットキー設定…", self._menu)
        settings_action.triggered.connect(self._handle_open_settings)
        self._menu.addAction(settings_action)

        open_config_action = QAction("設定ファイルを開く", self._menu)
        open_config_action.triggered.connect(lambda: open_path(get_config_file()))
        self._menu.addAction(open_config_action)

        open_dict_action = QAction("辞書を開く", self._menu)
        open_dict_action.triggered.connect(lambda: open_path(get_dictionary_file()))
        self._menu.addAction(open_dict_action)

        reload_dict_action = QAction("辞書を再読み込み", self._menu)
        reload_dict_action.triggered.connect(self._handle_reload_dictionary)
        self._menu.addAction(reload_dict_action)

        # SPEC §11.2: Retry engine load menu item
        retry_engine_action = QAction("認識モデルを再読み込み", self._menu)
        retry_engine_action.triggered.connect(self._handle_retry_engine_load)
        self._menu.addAction(retry_engine_action)

        open_log_action = QAction("ログを開く", self._menu)
        open_log_action.triggered.connect(
            lambda: open_path(get_config_dir() / "koekichi.log")
        )
        self._menu.addAction(open_log_action)

        self._menu.addSeparator()

        quit_action = QAction("終了", self._menu)
        quit_action.triggered.connect(self._handle_quit)
        self._menu.addAction(quit_action)

        if sys.platform == "darwin":
            # WORKAROUND (macOS): attaching the menu natively to the NSStatusItem
            # crashes with an NSEvent clickCount assertion when menu tracking
            # begins while the app's current event is not a mouse event (common
            # here because the double-tap hotkey delivers flagsChanged events).
            # Pop the menu up ourselves so AppKit's status-bar menu tracking
            # (and Qt's crashing notification observer) is never engaged.
            self.activated.connect(self._popup_menu)
        else:
            self.setContextMenu(self._menu)

    def _popup_menu(self, reason) -> None:
        """macOS: show the menu manually on any tray icon activation."""
        self._menu.popup(QCursor.pos())

    # --- public API ---

    def set_state(self, state: str) -> None:
        """Update icon color and menu label: idle | recording | transcribing."""
        if state not in self._icons:
            state = "idle"
        self._state = state
        self.setIcon(self._icons[state])
        self._record_action.setText(
            "録音停止" if state == "recording" else "録音開始"
        )

    def set_tooltip(self, text: str) -> None:
        self.setToolTip(text)

    def notify(self, title: str, message: str) -> None:
        """Show a tray notification balloon."""
        try:
            self.showMessage(title, message)
        except Exception as e:
            logger.warning(f"Tray notification failed: {e}")

    def is_enabled_checked(self) -> bool:
        return self._enabled_action.isChecked()

    # --- menu handlers (Qt main thread) ---

    def _handle_toggle_recording(self) -> None:
        if self._on_toggle_recording is not None:
            self._on_toggle_recording()

    def _handle_enabled_toggled(self, checked: bool) -> None:
        if self._on_enabled_changed is not None:
            self._on_enabled_changed(checked)

    def _handle_reload_dictionary(self) -> None:
        if self._on_reload_dictionary is not None:
            self._on_reload_dictionary()

    def _handle_retry_engine_load(self) -> None:
        if self._on_retry_engine_load is not None:
            self._on_retry_engine_load()

    def _handle_quit(self) -> None:
        if self._on_quit is not None:
            self._on_quit()

    def _handle_open_settings(self) -> None:
        if self._on_open_settings is not None:
            self._on_open_settings()
