"""First-run setup wizard (SPEC §11.4).

Shown once, after the tray has started, when the `setup_done` marker file
is absent (`--check` never shows it — see app.py `run_check`). The wizard
is **non-modal**: it must never block hotkeys/tray operation, so callers
must `show()` it rather than `exec()` it.

Pages:
    1. Welcome           - what KoeKichi does, model download size notice
    2. Model download    - triggers AppController.ensure_engine_loading()
                            and waits for sig_engine_ready
    3. Permissions (mac only) - mic / accessibility / input monitoring
    4. Done               - current hotkey (describe_hotkey) + basic usage

Closing the wizard for any reason (Finish, Cancel, or the window's close
box) writes the `setup_done` marker (content = app version string) so it
is not shown again.
"""

import logging
import subprocess
import sys
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from koekichi import __version__
from koekichi.hotkey import describe_hotkey
from koekichi.paths import write_setup_marker

logger = logging.getLogger(__name__)

# SPEC §11.4: approximate model download sizes shown to the user
MODEL_SIZE_MAC = "約 1.6GB"
MODEL_SIZE_WIN = "約 500MB"

# SPEC §11.4: macOS privacy pane deep links, opened via `open`
_MAC_PRIVACY_PANES = [
    (
        "マイク",
        "録音に必要です。",
        "x-apple.systempreference:com.apple.preference.security?Privacy_Microphone",
    ),
    (
        "アクセシビリティ",
        "ペーストキー(Cmd+V)の送出に必要です。",
        "x-apple.systempreference:com.apple.preference.security?Privacy_Accessibility",
    ),
    (
        "入力監視",
        "グローバルホットキーの検出に必要です。",
        "x-apple.systempreference:com.apple.preference.security?Privacy_ListenEvent",
    ),
]


def _open_system_settings(url: str) -> None:
    """Open a macOS System Settings privacy pane via `open` (SPEC §11.4)."""
    try:
        subprocess.Popen(["open", url])
    except Exception as e:
        logger.error(f"Failed to open system settings pane {url}: {e}")


class WelcomePage(QWizardPage):
    """Page 1: what KoeKichi does + model download size notice."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("KoeKichi へようこそ")

        layout = QVBoxLayout(self)
        size = MODEL_SIZE_MAC if sys.platform == "darwin" else MODEL_SIZE_WIN
        label = QLabel(
            "KoeKichi はローカルで完結する音声入力ツールです。\n"
            "音声はネットワークへ送信されません。\n\n"
            "初回利用には音声認識モデルのダウンロードが必要です"
            f"(目安サイズ: {size})。次のページでダウンロードします。"
        )
        label.setWordWrap(True)
        layout.addWidget(label)


class ModelDownloadPage(QWizardPage):
    """Page 2: triggers ensure_engine_loading() and awaits sig_engine_ready."""

    def __init__(
        self,
        ensure_engine_loading: Callable[[], None],
        engine_ready_signal: Signal,
        parent=None,
    ):
        super().__init__(parent)
        self.setTitle("音声認識モデルのダウンロード")
        self._ensure_engine_loading = ensure_engine_loading
        self._done = False
        self._skipped = False

        layout = QVBoxLayout(self)

        self.status_label = QLabel(
            "[ダウンロード開始] を押すとモデルの取得・読み込みを開始します。\n"
            "(モデルがキャッシュ済みの場合は数秒で完了します)"
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate: no fine-grained progress
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.start_button = QPushButton("ダウンロード開始")
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)

        self.skip_button = QPushButton("スキップ")
        self.skip_button.clicked.connect(self._skip)
        layout.addWidget(self.skip_button)

        engine_ready_signal.connect(self._on_engine_ready)

    def _start(self) -> None:
        self.status_label.setText("ダウンロード・読み込み中…")
        self.progress.setVisible(True)
        self.start_button.setText("再試行")
        self.start_button.setEnabled(False)
        try:
            self._ensure_engine_loading()
        except Exception as e:
            logger.exception("ensure_engine_loading() failed")
            self._on_engine_ready(False, str(e))

    def _skip(self) -> None:
        """SPEC §11.4: skipping loads the model normally on first use instead."""
        self._skipped = True
        self.completeChanged.emit()
        wizard = self.wizard()
        if wizard is not None:
            wizard.next()

    def _on_engine_ready(self, ok: bool, error: str) -> None:
        self.progress.setVisible(False)
        self.start_button.setEnabled(True)
        if ok:
            self.status_label.setText("完了しました。")
            self._done = True
        else:
            self.status_label.setText(
                f"読み込みに失敗しました: {error[:120]}\n[再試行] を押してください。"
            )
            self._done = False
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802 (Qt override naming)
        return self._done or self._skipped


class PermissionsPage(QWizardPage):
    """Page 3 (macOS only): mic / accessibility / input monitoring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("権限設定 (macOS)")

        layout = QVBoxLayout(self)
        intro = QLabel(
            "ホットキー検出・ペースト・録音のために、次の3つの権限が必要です。\n"
            "付与状態の自動判定は行わないため、各ボタンからシステム設定を開いて"
            "手動で確認・許可してください。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        for name, reason, url in _MAC_PRIVACY_PANES:
            row_label = QLabel(f"■ {name} — {reason}")
            row_label.setWordWrap(True)
            layout.addWidget(row_label)

            button = QPushButton("システム設定を開く")
            button.clicked.connect(
                lambda _checked=False, u=url: _open_system_settings(u)
            )
            layout.addWidget(button)


class DonePage(QWizardPage):
    """Page 4: current hotkey + basic usage."""

    def __init__(self, config: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setTitle("準備完了")

        layout = QVBoxLayout(self)
        hotkey = describe_hotkey(config.get("hotkey", {}))
        label = QLabel(
            f"ホットキー「{hotkey}」で録音を開始/停止します。\n"
            "録音中に Esc を押すと録音を破棄できます。\n\n"
            "設定はメニューバー(タスクトレイ)のアイコンからいつでも変更できます。"
        )
        label.setWordWrap(True)
        layout.addWidget(label)


class FirstRunWizard(QWizard):
    """
    Non-modal first-run setup wizard (SPEC §11.4).

    Call `show()` (never `exec()`) so the tray/hotkeys keep working while
    the wizard is open. The `setup_done` marker is written when the wizard
    closes, no matter how (Finish, Cancel, or the window's close box).
    """

    def __init__(
        self,
        config: dict[str, Any],
        ensure_engine_loading: Callable[[], None],
        engine_ready_signal: Signal,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("KoeKichi 初回セットアップ")
        self.setWindowModality(Qt.NonModal)
        self.setOption(QWizard.NoBackButtonOnLastPage, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.addPage(WelcomePage())
        self.addPage(ModelDownloadPage(ensure_engine_loading, engine_ready_signal))
        if sys.platform == "darwin":
            self.addPage(PermissionsPage())
        self.addPage(DonePage(config))

    def done(self, result: int) -> None:  # noqa: N802 (Qt override naming)
        """Write the setup_done marker regardless of how the wizard closed."""
        try:
            write_setup_marker(__version__)
        except Exception:
            logger.exception("Failed to write setup marker on wizard close")
        super().done(result)
