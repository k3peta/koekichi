"""Floating overlay window (SPEC §11.1).

Frameless, always-on-top, never takes focus (mandatory: stealing focus would
break insertion into the target application).
"""

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

OVERLAY_WIDTH = 280
OVERLAY_HEIGHT = 56
CORNER_RADIUS = 14
BG_COLOR = QColor(20, 20, 24, 235)  # rgba(20,20,24,0.92)
FG_COLOR = QColor(255, 255, 255)
REC_COLOR = QColor(235, 70, 70)
BAR_COLOR = QColor(120, 220, 140)
BAR_DIM_COLOR = QColor(255, 255, 255, 50)
EDGE_MARGIN = 80  # px from screen edge


class Overlay(QWidget):
    """Status overlay. All methods must be called from the Qt main thread."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(None)
        self.config = config

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # macOS hides Qt.Tool windows while the app is inactive; KoeKichi is a
        # background tray app and is effectively always inactive.
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(OVERLAY_WIDTH, OVERLAY_HEIGHT)

        self._state = "hidden"
        self._rms = 0.0
        self._elapsed = 0.0
        self._error_msg = ""
        self._spin_angle = 0

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(80)
        self._spin_timer.timeout.connect(self._advance_spinner)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_overlay)

    # --- public state API ---

    def show_recording(self, rms: float, elapsed_s: float) -> None:
        """Show recording state: blinking red dot, level bars, elapsed time."""
        self._hide_timer.stop()
        self._spin_timer.stop()
        self._state = "recording"
        self._rms = rms
        self._elapsed = elapsed_s
        self._show_in_place()

    def show_transcribing(self) -> None:
        """Show transcribing state: spinner + 認識中…"""
        self._hide_timer.stop()
        self._state = "transcribing"
        if not self._spin_timer.isActive():
            self._spin_timer.start()
        self._show_in_place()

    def show_no_speech(self) -> None:
        """Show (無音) for 800ms, then hide."""
        self._spin_timer.stop()
        self._state = "no_speech"
        self._show_in_place()
        self._hide_timer.start(800)

    def show_error(self, msg: str) -> None:
        """Show an error message for 1.5s, then hide."""
        self._spin_timer.stop()
        self._state = "error"
        self._error_msg = msg
        self._show_in_place()
        self._hide_timer.start(1500)

    def hide_overlay(self) -> None:
        """Hide the overlay (IDLE)."""
        self._spin_timer.stop()
        self._hide_timer.stop()
        self._state = "hidden"
        self.hide()

    # --- internals ---

    def _show_in_place(self) -> None:
        self._reposition()
        if not self.isVisible():
            self.show()
        self.update()

    def _reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        position = self.config.get("ui", {}).get("overlay_position", "bottom-center")
        if position == "top-center":
            y = geo.y() + EDGE_MARGIN
        else:  # bottom-center (default)
            y = geo.y() + geo.height() - self.height() - EDGE_MARGIN
        self.move(x, y)

    def _advance_spinner(self) -> None:
        self._spin_angle = (self._spin_angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background: rounded dark panel
        painter.setPen(Qt.NoPen)
        painter.setBrush(BG_COLOR)
        painter.drawRoundedRect(self.rect(), CORNER_RADIUS, CORNER_RADIUS)

        font = QFont()
        font.setPointSize(13)
        painter.setFont(font)

        if self._state == "recording":
            self._paint_recording(painter)
        elif self._state == "transcribing":
            self._paint_transcribing(painter)
        elif self._state == "no_speech":
            painter.setPen(FG_COLOR)
            painter.drawText(self.rect(), Qt.AlignCenter, "(無音)")
        elif self._state == "error":
            painter.setPen(FG_COLOR)
            metrics = QFontMetrics(font)
            text = "⚠ " + metrics.elidedText(
                self._error_msg, Qt.ElideRight, self.width() - 60
            )
            painter.drawText(self.rect(), Qt.AlignCenter, text)

        painter.end()

    def _paint_recording(self, painter: QPainter) -> None:
        cy = self.height() // 2

        # Blinking red dot (1s period: on 0.5s, off 0.5s)
        blink_on = int(self._elapsed * 2) % 2 == 0
        if blink_on:
            painter.setPen(Qt.NoPen)
            painter.setBrush(REC_COLOR)
            painter.drawEllipse(18, cy - 7, 14, 14)

        # Level meter: 10 vertical bars driven by RMS
        n_bars = 10
        active = min(n_bars, int(self._rms * 40))
        bar_w = 5
        gap = 4
        x0 = 48
        max_h = 26
        painter.setPen(Qt.NoPen)
        for i in range(n_bars):
            h = 8 + int((max_h - 8) * (i + 1) / n_bars)
            painter.setBrush(BAR_COLOR if i < active else BAR_DIM_COLOR)
            painter.drawRoundedRect(
                x0 + i * (bar_w + gap), cy - h // 2, bar_w, h, 2, 2
            )

        # Elapsed time "0:07"
        minutes = int(self._elapsed) // 60
        seconds = int(self._elapsed) % 60
        painter.setPen(FG_COLOR)
        painter.drawText(
            QRectF(self.width() - 76, 0, 64, self.height()),
            Qt.AlignVCenter | Qt.AlignRight,
            f"{minutes}:{seconds:02d}",
        )

    def _paint_transcribing(self, painter: QPainter) -> None:
        cy = self.height() // 2

        # Spinner arc
        pen = QPen(FG_COLOR, 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(
            QRectF(18, cy - 9, 18, 18), -self._spin_angle * 16, 120 * 16
        )

        painter.setPen(FG_COLOR)
        painter.drawText(
            QRectF(48, 0, self.width() - 60, self.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            "認識中…",
        )
