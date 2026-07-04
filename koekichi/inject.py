"""Text insertion via clipboard paste (SPEC §12).

Pure module: no Qt dependency. Runs on the worker thread.
Controller is generated and reused at module level (SPEC §12).
Clipboard restoration is delegated to a daemon threading.Timer (v1.1, SPEC §12).
"""

import logging
import sys
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Module-level Controller (reused, generated once on first use)
_controller = None
_controller_lock = threading.Lock()


def _get_controller():
    """Lazily generate and cache the pynput Controller (thread-safe)."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                from pynput.keyboard import Controller
                _controller = Controller()
    return _controller


def _restore_clipboard(saved_text: str | None, restore_delay_s: float) -> None:
    """
    Daemon timer callback: restore clipboard after restore_delay_s.

    Only restores if saved_text is a non-empty string.
    Exceptions logged as WARNING; does not propagate.
    """
    import pyperclip

    if isinstance(saved_text, str) and saved_text:
        try:
            pyperclip.copy(saved_text)
            logger.debug("Clipboard restored (async)")
        except Exception as e:
            logger.warning(f"Could not restore clipboard: {e}")
    else:
        logger.debug("Clipboard backup empty or non-text; not restoring")


def inject_text(text: str, config: dict[str, Any], copy_only: bool = False) -> None:
    """
    Insert text at the cursor of the active application (SPEC §12, §14.1).

    When copy_only=True (permission fallback, SPEC §14.1):
    - Copy text to clipboard only
    - Skip paste keystroke and clipboard restoration
    - Return immediately

    When copy_only=False (normal operation, v1.1 SPEC §12):
    1. Save current clipboard text (if restore_clipboard enabled)
    2. Set text to clipboard (pyperclip)
    3. Wait paste_delay_ms
    4. Send paste keystroke (darwin: Cmd+V, others: Ctrl+V)
    5. Return immediately (injection complete on critical path)
    6. (async) Schedule daemon timer to restore clipboard after restore_delay_ms
       (does not wait for restoration)

    Args:
        text: Text to insert (caller ensures non-empty)
        config: Configuration dict with insert settings
        copy_only: If True, copy to clipboard only (SPEC §14.1 fallback)
    """
    import pyperclip

    # Fallback path: copy to clipboard without pasting (SPEC §14.1)
    if copy_only:
        pyperclip.copy(text)
        return

    insert_cfg = config.get("insert", {})
    restore_clipboard = insert_cfg.get("restore_clipboard", True)
    paste_delay_s = insert_cfg.get("paste_delay_ms", 30) / 1000.0
    restore_delay_s = insert_cfg.get("restore_delay_ms", 500) / 1000.0

    # 1. Save current clipboard (text only)
    saved: str | None = None
    if restore_clipboard:
        try:
            saved = pyperclip.paste()
        except Exception as e:
            logger.warning(f"Could not read clipboard for backup: {e}")
            saved = None

    # 2. Set result text to clipboard
    pyperclip.copy(text)

    # 3. Wait before paste
    time.sleep(paste_delay_s)

    # 4. Send paste keystroke
    _send_paste_keystroke()

    # 5. Return immediately (critical path done). Restoration is async (daemon).
    if restore_clipboard:
        # Start daemon timer for non-blocking restoration
        timer = threading.Timer(
            restore_delay_s, _restore_clipboard, args=(saved, restore_delay_s)
        )
        timer.daemon = True
        timer.start()


def _send_paste_keystroke() -> None:
    """Send Cmd+V (macOS) or Ctrl+V (others) via module-level pynput Controller."""
    from pynput.keyboard import Key

    kb = _get_controller()
    modifier = Key.cmd if sys.platform == "darwin" else Key.ctrl

    # Modifier down -> v down/up -> modifier up (SPEC §12)
    kb.press(modifier)
    try:
        kb.press("v")
        kb.release("v")
    finally:
        kb.release(modifier)
