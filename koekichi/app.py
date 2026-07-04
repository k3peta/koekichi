"""KoeKichi application entry point (SPEC §3, §6, §14).

State machine:
    IDLE --(hotkey)--> RECORDING --(hotkey/release)--> TRANSCRIBING -> INSERTING -> IDLE
    RECORDING --(Esc)--> IDLE (discard)
    RECORDING --(max duration)--> TRANSCRIBING
    any state --(error)--> IDLE (short error on overlay)
"""

import argparse
import logging
import platform
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication

from koekichi import __version__
from koekichi.antihallucination import filter_segments
from koekichi.audio import AudioRecorder
from koekichi.config import load_config, save_config
from koekichi.dictionary import (
    apply_corrections,
    dictionary_mtime,
    get_dictionary_words,
    load_dictionary,
    load_dictionary_if_changed,
)
from koekichi.engine import get_engine
from koekichi.formatter import format_text
from koekichi.hotkey import HotkeyManager, describe_hotkey
from koekichi.inject import inject_text
from koekichi.llm_format import format_with_llm
from koekichi.macos_perms import accessibility_trusted, input_monitoring_granted
from koekichi.macos_tsm import prime_keyboard_layout
from koekichi.paths import ensure_config_dir, is_setup_done
from koekichi.prompt import build_prompt
from koekichi.ui.firstrun import FirstRunWizard
from koekichi.ui.overlay import Overlay
from koekichi.ui.settings import SettingsDialog
from koekichi.ui.tray import Tray
from koekichi.vad import trim_and_validate_audio

logger = logging.getLogger(__name__)

# States
IDLE = "IDLE"
RECORDING = "RECORDING"
TRANSCRIBING = "TRANSCRIBING"


def setup_logging(config: dict[str, Any]) -> None:
    """Configure logging: RotatingFileHandler (1MB x 3) + stderr (SPEC §14)."""
    level_name = str(config.get("log_level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return  # already configured

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        log_file = ensure_config_dir() / "koekichi.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as e:
        print(f"Could not open log file: {e}", file=sys.stderr)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)


class AppController(QObject):
    """Connects hotkey, audio, engine, formatting, injection, and UI."""

    # Signals bridge pynput/worker threads to the Qt main thread.
    sig_toggle = Signal()
    sig_hold_start = Signal()
    sig_hold_end = Signal()
    sig_esc = Signal()
    sig_no_speech = Signal()
    sig_pipeline_done = Signal()
    sig_error = Signal(str)
    sig_perm_missing = Signal(str)  # Permission missing message (SPEC §14.1)
    sig_engine_ready = Signal(bool, str)

    def __init__(self, config: dict[str, Any], app: QApplication):
        super().__init__()
        self.config = config
        self.app = app
        self.state = IDLE

        # Dictionary
        self.dictionary = load_dictionary()
        self._dict_mtime = dictionary_mtime()

        # UI (main thread)
        self.overlay = Overlay(config)
        self.tray = Tray(
            config,
            on_toggle_recording=self._on_toggle,
            on_enabled_changed=self._on_enabled_changed,
            on_reload_dictionary=self._reload_dictionary,
            on_retry_engine_load=self._retry_engine_load,
            on_quit=self._quit,
            on_open_settings=self._open_settings,
        )

        # Audio (SPEC §6.0: pass full audio config)
        audio_cfg = config.get("audio", {})
        self.recorder = AudioRecorder(
            device=audio_cfg.get("device"),
            sample_rate=audio_cfg.get("sample_rate", 16000),
            max_duration_s=audio_cfg.get("max_duration_s", 120),
            idle_stream=audio_cfg.get("idle_stream", "running"),
            pre_roll_ms=audio_cfg.get("pre_roll_ms", 200),
        )
        self._rec_start = 0.0
        self._last_fire_ts = 0.0  # For PERF logging

        # Engine (loaded in worker thread)
        self.engine = None
        self._engine_ready = threading.Event()
        self._engine_load_started = False

        # SPEC §13.1-A-2: Distinguish long-press from toggle recordings
        self._hold_recording = False

        # First-run wizard (kept alive on self while shown; SPEC §11.4)
        self._first_run_wizard: FirstRunWizard | None = None

        # Timers (main thread)
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setInterval(50)
        self._overlay_timer.timeout.connect(self._update_overlay)

        self._max_duration_timer = QTimer(self)
        self._max_duration_timer.setInterval(100)
        self._max_duration_timer.timeout.connect(self._check_max_duration)

        # Cross-thread signal wiring (queued: slots run on main thread)
        self.sig_toggle.connect(self._on_toggle, Qt.QueuedConnection)
        self.sig_hold_start.connect(self._on_hold_start, Qt.QueuedConnection)
        self.sig_hold_end.connect(self._on_hold_end, Qt.QueuedConnection)
        self.sig_esc.connect(self._on_esc, Qt.QueuedConnection)
        self.sig_no_speech.connect(self._on_no_speech, Qt.QueuedConnection)
        self.sig_pipeline_done.connect(self._on_pipeline_done, Qt.QueuedConnection)
        self.sig_error.connect(self._on_error, Qt.QueuedConnection)
        self.sig_perm_missing.connect(self._on_perm_missing, Qt.QueuedConnection)
        self.sig_engine_ready.connect(self._on_engine_ready, Qt.QueuedConnection)

        # Hotkeys (pynput threads -> signals only; never touch widgets directly)
        self.hotkeys = self._build_hotkey_manager(config.get("hotkey", {}))

    def _build_hotkey_manager(self, hotkey_cfg: dict[str, Any]) -> HotkeyManager:
        return HotkeyManager(
            hotkey_cfg,
            on_toggle=self.sig_toggle.emit,
            on_hold_start=self.sig_hold_start.emit,
            on_hold_end=self.sig_hold_end.emit,
            on_esc=self.sig_esc.emit,
        )

    def _hotkey_desc(self) -> str:
        return describe_hotkey(self.config.get("hotkey", {}))

    # --- lifecycle ---

    def start(self) -> None:
        self.tray.show()
        self.tray.set_tooltip(
            f"KoeKichi — モデルを読み込み中… ({self._hotkey_desc()})"
        )

        # Open resident audio stream (SPEC §6.0)
        try:
            self.recorder.open_stream()
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            self.tray.notify("KoeKichi", f"マイクを開けませんでした: {e}")
            # Continue; may retry on first recording

        self.ensure_engine_loading()

        # macOS permission check (SPEC §14.1)
        if sys.platform == "darwin":
            missing_perms = []
            if not accessibility_trusted():
                missing_perms.append("アクセシビリティ")
            if not input_monitoring_granted():
                missing_perms.append("入力監視")
            if missing_perms:
                perm_msg = "、".join(missing_perms)
                msg = f"KoeKichi には {perm_msg} の権限が必要です。システム設定 > プライバシーとセキュリティ で許可してください。"
                self.tray.notify("KoeKichi", msg)
                logger.warning(f"Missing permissions: {perm_msg}")

        try:
            self.hotkeys.start()
        except Exception as e:
            logger.error(f"Failed to start hotkey listener: {e}")
            self.tray.notify(
                "KoeKichi",
                "ホットキーを開始できませんでした。入力監視権限を確認してください。",
            )

        if not is_setup_done():
            self._show_first_run_wizard()

    def ensure_engine_loading(self) -> None:
        """
        Idempotently start the engine preload thread (SPEC §11.4).

        Public so the first-run wizard's "ダウンロード開始" button can (re)kick
        off preloading without caring whether `start()` already began it.
        Safe to call multiple times; only the first call spawns a thread.
        """
        if self._engine_load_started:
            # A successful load may have finished before a late listener
            # (e.g. the wizard's button) asked for it; re-emit readiness so
            # that listener converges instead of waiting forever.
            if self._engine_ready.is_set() and self.engine is not None:
                self.sig_engine_ready.emit(True, "")
            return
        self._engine_load_started = True
        # Clear (in case a prior failed attempt already set this) so any
        # pipeline run correctly waits for this attempt instead of seeing
        # the stale "ready" state from the previous failure.
        self._engine_ready.clear()
        threading.Thread(
            target=self._load_engine, name="engine-load", daemon=True
        ).start()

    def _show_first_run_wizard(self) -> None:
        """Show the non-modal first-run wizard (SPEC §11.4). Never in --check."""
        self._first_run_wizard = FirstRunWizard(
            self.config, self.ensure_engine_loading, self.sig_engine_ready
        )
        self._first_run_wizard.show()

    def _quit(self) -> None:
        logger.info("Quitting KoeKichi")
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self.recorder.close()
        except Exception:
            pass
        self.app.quit()

    def _load_engine(self) -> None:
        """Worker thread: preload the ASR model (SPEC §15)."""
        try:
            self.engine = get_engine(self.config)
            self.engine.load()
            self._engine_ready.set()
            self.sig_engine_ready.emit(True, "")
        except Exception as e:
            logger.exception("Engine load failed")
            self.engine = None
            # Unblock any pipeline waiting on preload; it will fail fast
            # with a clear error instead of hanging for the full timeout.
            self._engine_ready.set()
            # Allow a subsequent ensure_engine_loading() call (e.g. the
            # first-run wizard's [再試行]) to actually retry the load.
            self._engine_load_started = False
            self.sig_engine_ready.emit(False, str(e))

    def _on_engine_ready(self, ok: bool, error: str) -> None:
        if ok:
            self.tray.set_tooltip(
                f"KoeKichi — 準備完了 ({self.engine.name} / {self._hotkey_desc()})"
            )
            logger.info(f"Engine ready: {self.engine.name}")
        else:
            self.tray.set_tooltip("KoeKichi — モデルの読み込みに失敗しました")
            self.tray.notify(
                "KoeKichi", f"モデルの読み込みに失敗しました: {error[:80]}"
            )

    # --- hotkey handlers (main thread via queued signals) ---

    def _on_toggle(self) -> None:
        if self.state == IDLE:
            # SPEC §13.1-A-2: Mark as toggle (not hold) recording
            self._hold_recording = False
            self._start_recording()
        elif self.state == RECORDING:
            self._stop_and_transcribe()
        # TRANSCRIBING: ignore (reentry prohibited)

    def _on_hold_start(self) -> None:
        # SPEC §13.1-A-2: Only start if IDLE. Don't double-start during toggle recording.
        if self.state == IDLE:
            self._hold_recording = True
            self._start_recording()

    def _on_hold_end(self) -> None:
        # SPEC §13.1-A-2: Only stop if this was a hold recording.
        # If _hold_recording is False (toggle recording), don't stop here.
        if self._hold_recording and self.state == RECORDING:
            self._stop_and_transcribe()

    def _on_esc(self) -> None:
        if self.state == RECORDING:
            self._cancel_recording()

    def _on_enabled_changed(self, enabled: bool) -> None:
        self.hotkeys.set_enabled(enabled)
        # Pause/resume resident stream (SPEC §6.0)
        if enabled:
            self.recorder.resume_stream()
        else:
            # Cancel any in-progress recording before pausing
            if self.state == RECORDING:
                self._cancel_recording()
            self.recorder.pause_stream()

    def _open_settings(self) -> None:
        """Open the hotkey settings dialog (SPEC §11.3)."""
        dialog = SettingsDialog(
            self.config.get("hotkey", {}), on_save=self._apply_hotkey_config
        )
        dialog.exec()

    def _apply_hotkey_config(self, new_hotkey_cfg: dict[str, Any]) -> None:
        """Save new hotkey config and restart the HotkeyManager (SPEC §13.2)."""
        # Cancel an in-progress recording before swapping listeners
        if self.state == RECORDING:
            self._cancel_recording()

        self.config["hotkey"] = new_hotkey_cfg
        save_config(self.config)

        was_enabled = self.hotkeys.enabled
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        self.hotkeys = self._build_hotkey_manager(new_hotkey_cfg)
        self.hotkeys.set_enabled(was_enabled)
        try:
            self.hotkeys.start()
        except Exception as e:
            logger.error(f"Failed to restart hotkey listener: {e}")
            self.tray.notify(
                "KoeKichi",
                "ホットキーを再起動できませんでした。入力監視権限を確認してください。",
            )

        desc = self._hotkey_desc()
        if self._engine_ready.is_set() and self.engine is not None:
            self.tray.set_tooltip(f"KoeKichi — 準備完了 ({self.engine.name} / {desc})")
        else:
            self.tray.set_tooltip(f"KoeKichi — {desc}")
        logger.info(f"Hotkey config applied: {desc}")

    def _reload_dictionary(self) -> None:
        try:
            self.dictionary = load_dictionary()
            self._dict_mtime = dictionary_mtime()
            logger.info("Dictionary reloaded (tray menu)")
        except Exception as e:
            logger.error(f"Dictionary reload failed: {e}")

    def _retry_engine_load(self) -> None:
        """Retry engine load (SPEC §11.2). Called from tray menu."""
        # If already loaded, just notify
        if self._engine_ready.is_set() and self.engine is not None:
            self.tray.notify("KoeKichi", "モデルは既に準備完了しています。")
            return

        # If loading in progress, notify
        if self._engine_load_started and not self._engine_ready.is_set():
            self.tray.notify("KoeKichi", "モデルを読み込み中です。しばらくお待ちください。")
            return

        # Start/retry loading
        self.tray.set_tooltip(f"KoeKichi — モデルを読み込み中… ({self._hotkey_desc()})")
        self.ensure_engine_loading()

    # --- recording (main thread) ---

    def _start_recording(self) -> None:
        # Auto-reload dictionary if changed (SPEC §10.4)
        try:
            reloaded, mtime = load_dictionary_if_changed(self._dict_mtime)
            if reloaded is not None:
                self.dictionary = reloaded
                self._dict_mtime = mtime
                logger.info("Dictionary auto-reloaded (mtime changed)")
        except Exception as e:
            logger.warning(f"Dictionary auto-reload failed: {e}")

        try:
            self.recorder.start_recording()
        except Exception as e:
            logger.exception("Failed to start recording")
            self._show_error_and_idle(f"録音を開始できません: {e}")
            return

        self.state = RECORDING
        self._rec_start = time.perf_counter()
        self.hotkeys.set_esc_enabled(True)
        self.tray.set_state("recording")
        self.overlay.show_recording(0.0, 0.0)
        self._overlay_timer.start()
        self._max_duration_timer.start()

        # PERF measurement: fire→capture latency (SPEC §14.2)
        if self.hotkeys.last_fire_ts > 0:
            dt_ms = (time.perf_counter() - self.hotkeys.last_fire_ts) * 1000.0
            logger.info(f"PERF rec_start {dt_ms:.1f}ms (fire→capture)")
            self.hotkeys.last_fire_ts = 0.0  # Reset

        logger.info("Recording started")

    def _update_overlay(self) -> None:
        if self.state != RECORDING:
            return
        elapsed = time.monotonic() - self._rec_start
        self.overlay.show_recording(self.recorder.get_current_rms(), elapsed)

    def _check_max_duration(self) -> None:
        if self.state == RECORDING and self.recorder.check_max_duration_reached():
            logger.info("Max recording duration reached; auto-stopping")
            self._stop_and_transcribe()

    def _stop_recording_common(self) -> None:
        self._overlay_timer.stop()
        self._max_duration_timer.stop()
        self.hotkeys.set_esc_enabled(False)

    def _cancel_recording(self) -> None:
        self._stop_recording_common()
        try:
            self.recorder.stop_recording()  # discard
        except Exception:
            pass
        self.state = IDLE
        self.overlay.hide_overlay()
        self.tray.set_state("idle")
        logger.info("Recording discarded (Esc)")

    def _stop_and_transcribe(self) -> None:
        self._stop_recording_common()
        try:
            audio = self.recorder.stop_recording()
        except Exception as e:
            logger.exception("Failed to stop recording")
            self._show_error_and_idle(f"録音停止エラー: {e}")
            return

        self.state = TRANSCRIBING
        self.overlay.show_transcribing()
        self.tray.set_state("transcribing")
        threading.Thread(
            target=self._pipeline, args=(audio,), name="pipeline", daemon=True
        ).start()

    # --- pipeline (worker thread; UI updates only via signals) ---

    def _pipeline(self, audio) -> None:
        try:
            t_start = time.perf_counter()

            # H1: VAD gate + endpoint trim
            t_vad_start = time.perf_counter()
            vad_cfg = self.config.get("vad", {})
            sample_rate = self.config.get("audio", {}).get("sample_rate", 16000)
            trimmed, valid = trim_and_validate_audio(
                audio,
                sample_rate,
                min_speech_ms=vad_cfg.get("min_speech_ms", 300),
                pad_ms=vad_cfg.get("pad_ms", 200),
                aggressiveness=vad_cfg.get("aggressiveness", 2),
                min_speech_ratio=vad_cfg.get("min_speech_ratio", 0.10),
            )
            t_vad_ms = (time.perf_counter() - t_vad_start) * 1000.0

            if not valid:
                # No speech: log drop with VAD time only (SPEC §14.2)
                t_total_ms = (time.perf_counter() - t_start) * 1000.0
                logger.info(
                    f"PERF stop→drop total={t_total_ms:.0f}ms vad={t_vad_ms:.0f}"
                )
                self.sig_no_speech.emit()
                return

            # Wait for model preload if still in progress
            if not self._engine_ready.wait(timeout=180):
                raise RuntimeError("モデルの読み込みが完了していません")
            if self.engine is None:
                raise RuntimeError("モデルの読み込みに失敗しています(ログを確認してください)")

            # ASR
            t_asr_start = time.perf_counter()
            language = self.config.get("language", "ja")
            initial_prompt = build_prompt(get_dictionary_words(self.dictionary))
            segments = self.engine.transcribe(trimmed, initial_prompt, language)
            t_asr_ms = (time.perf_counter() - t_asr_start) * 1000.0

            # H3-H6 filtering, then join (no separator for Japanese)
            filtered = filter_segments(segments, self.config, initial_prompt)
            text = "".join(seg.text.strip() for seg in filtered)

            # Format: dictionary corrections + rule formatting + LLM (SPEC §9, §10.3)
            t_fmt_start = time.perf_counter()
            text = apply_corrections(text, self.dictionary)
            text = format_text(text, self.config)
            text = format_with_llm(text, self.config)
            t_fmt_ms = (time.perf_counter() - t_fmt_start) * 1000.0

            if text:
                # Injection (including clipboard ops and paste, but not async restore)
                t_inj_start = time.perf_counter()

                # macOS accessibility check before injection (SPEC §14.1)
                if sys.platform == "darwin" and not accessibility_trusted():
                    inject_text(text, self.config, copy_only=True)
                    self.sig_perm_missing.emit(
                        "アクセシビリティ権限が必要です(テキストはコピー済み)"
                    )
                    logger.warning(
                        "Accessibility not granted; copied to clipboard only"
                    )
                else:
                    inject_text(text, self.config)
                    logger.info(f"Inserted {len(text)} chars")

                t_inj_ms = (time.perf_counter() - t_inj_start) * 1000.0
                t_total_ms = (time.perf_counter() - t_start) * 1000.0

                # PERF measurement (SPEC §14.2)
                logger.info(
                    f"PERF stop→insert total={t_total_ms:.0f}ms vad={t_vad_ms:.0f} "
                    f"asr={t_asr_ms:.0f} fmt={t_fmt_ms:.0f} inject={t_inj_ms:.0f}"
                )
            else:
                # Empty result
                t_total_ms = (time.perf_counter() - t_start) * 1000.0
                logger.info(
                    f"PERF stop→drop total={t_total_ms:.0f}ms vad={t_vad_ms:.0f} "
                    f"asr={t_asr_ms:.0f}"
                )
                logger.info("Empty result after filtering; nothing inserted")

            self.sig_pipeline_done.emit()
        except Exception as e:
            logger.exception("Pipeline error")
            self.sig_error.emit(str(e))

    # --- pipeline result handlers (main thread) ---

    def _on_no_speech(self) -> None:
        self.state = IDLE
        self.overlay.show_no_speech()
        self.tray.set_state("idle")

    def _on_pipeline_done(self) -> None:
        self.state = IDLE
        self.overlay.hide_overlay()
        self.tray.set_state("idle")

    def _on_error(self, msg: str) -> None:
        self._show_error_and_idle(msg)

    def _on_perm_missing(self, msg: str) -> None:
        """Handle permission missing error with overlay and tray notification."""
        self.state = IDLE
        self.overlay.show_error(msg[:60])
        self.tray.set_state("idle")
        self.tray.notify("KoeKichi", msg)

    def _show_error_and_idle(self, msg: str) -> None:
        self.state = IDLE
        self.overlay.show_error(msg[:60])
        self.tray.set_state("idle")


def run_check(config: dict[str, Any]) -> int:
    """
    Diagnostic mode (`koekichi --check`). Works with QT_QPA_PLATFORM=offscreen.

    Loads config, constructs the engine (without loading the model) and the
    UI widgets. Does not start microphone or hotkeys. Prints "OK" on success.
    """
    try:
        engine = get_engine(config)
        logger.info(f"Engine factory OK: {engine.name}")

        app = QApplication.instance() or QApplication(sys.argv)
        overlay = Overlay(config)
        tray = Tray(config)
        settings = SettingsDialog(config.get("hotkey", {}))
        _ = (overlay, tray, settings, app)

        print("OK")
        return 0
    except Exception as e:
        logger.exception("Check failed")
        print(f"NG: {e}", file=sys.stderr)
        return 1


def main() -> None:
    """Main entry point for KoeKichi."""
    parser = argparse.ArgumentParser(prog="koekichi", description="KoeKichi voice input")
    parser.add_argument("--check", action="store_true", help="diagnostic mode")
    parser.add_argument(
        "--version", action="version", version=f"koekichi {__version__}"
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(config)

    # SPEC §2: Intel Mac is unsupported
    if sys.platform == "darwin" and platform.machine() != "arm64":
        print(
            "KoeKichi は Apple Silicon (arm64) の Mac のみ対応しています。",
            file=sys.stderr,
        )
        sys.exit(1)

    # Log uncaught exceptions in threads instead of crashing silently
    def _thread_excepthook(exc_args) -> None:
        logger.error(
            "Uncaught exception in thread %s",
            exc_args.thread.name if exc_args.thread else "?",
            exc_info=(exc_args.exc_type, exc_args.exc_value, exc_args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook

    # macOS TSM crash workaround (SPEC §13.3): must run on the main thread
    # before any pynput Listener/Controller is created. Also covers --check.
    prime_keyboard_layout()

    if args.check:
        sys.exit(run_check(config))

    logger.info(f"KoeKichi {__version__} starting")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("KoeKichi")

    controller = AppController(config, app)
    controller.start()

    sys.exit(app.exec())
