"""Global hotkey handling via pynput (SPEC §13).

Two trigger types (hotkey.type):
- "double-tap" (default): double-tap of a lone modifier key (§13.1-A).
  Detection logic is the pynput-independent pure class DoubleTapDetector.
- "combo": key combination via GlobalHotKeys (toggle) / Listener (hold).

Pure module: no Qt dependency. Callbacks are supplied by the caller and are
invoked on pynput listener threads — callers must marshal to their own event
loop (e.g. via Qt Signals).
"""

import logging
import sys
import threading
import time
from typing import Any, Callable

from pynput import keyboard
from pynput.keyboard import Key

logger = logging.getLogger(__name__)

DEFAULT_COMBO = "<ctrl>+<shift>+<space>"
DEFAULT_DOUBLE_TAP_KEY = "alt"
DEFAULT_DOUBLE_TAP_WINDOW_MS = 400
DEFAULT_HOLD_TO_RECORD = True

# Left/right variants are treated as the same key (SPEC §13.1-A)
MODIFIER_KEY_MAP: dict[str, frozenset] = {
    "alt": frozenset({Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr}),
    "ctrl": frozenset({Key.ctrl, Key.ctrl_l, Key.ctrl_r}),
    "shift": frozenset({Key.shift, Key.shift_l, Key.shift_r}),
    "cmd": frozenset({Key.cmd, Key.cmd_l, Key.cmd_r}),
}

_DISPLAY_NAMES_MAC = {"alt": "Option", "ctrl": "Ctrl", "shift": "Shift", "cmd": "Cmd"}
_DISPLAY_NAMES_WIN = {"alt": "Alt", "ctrl": "Ctrl", "shift": "Shift", "cmd": "Win"}


def validate_combo(combo: str) -> str:
    """
    Validate a pynput combo string.

    Returns the combo unchanged if parseable; otherwise logs a warning and
    returns DEFAULT_COMBO (SPEC §13.1-B fallback).
    """
    try:
        keyboard.HotKey.parse(combo)
        return combo
    except (ValueError, KeyError) as e:
        logger.warning(
            f"Invalid hotkey combo {combo!r}: {e}. Falling back to {DEFAULT_COMBO}"
        )
        return DEFAULT_COMBO


def is_valid_combo(combo: str) -> bool:
    """Return True if the combo string is parseable by pynput."""
    try:
        keyboard.HotKey.parse(combo)
        return True
    except (ValueError, KeyError):
        return False


def describe_hotkey(hotkey_cfg: dict[str, Any]) -> str:
    """
    Return a short human-readable description of the configured hotkey.

    Examples: "Option 2回押し" (mac double-tap alt), "Option 2回押し / 長押し" (with hold).
    """
    hotkey_type = hotkey_cfg.get("type", "double-tap")
    if hotkey_type == "combo":
        combo = validate_combo(hotkey_cfg.get("combo", DEFAULT_COMBO))
        parts = [part.strip("<>").capitalize() for part in combo.split("+")]
        return "+".join(parts)

    key = hotkey_cfg.get("double_tap_key", DEFAULT_DOUBLE_TAP_KEY)
    if key not in MODIFIER_KEY_MAP:
        key = DEFAULT_DOUBLE_TAP_KEY
    names = _DISPLAY_NAMES_MAC if sys.platform == "darwin" else _DISPLAY_NAMES_WIN
    desc = f"{names[key]} 2回押し"

    # SPEC §13.1-A-2: Append " / 長押し" if hold_to_record is enabled
    if hotkey_cfg.get("hold_to_record", DEFAULT_HOLD_TO_RECORD):
        desc += " / 長押し"

    return desc


class DoubleTapDetector:
    """
    Pure double-tap detection logic (SPEC §13.1-A). pynput-independent.

    A "clean tap" is a press→release of the target modifier with no other
    keyboard event in between. The detector fires (returns True from
    on_release) when two clean taps occur and the time from the first tap's
    release to the second tap's release is within window_ms. After firing,
    internal state resets (a triple tap fires only once).
    """

    def __init__(
        self,
        target: str,
        window_ms: int = DEFAULT_DOUBLE_TAP_WINDOW_MS,
        now_fn: Callable[[], float] = time.monotonic,
    ):
        if target not in MODIFIER_KEY_MAP:
            logger.warning(
                f"Unknown double_tap_key {target!r}, falling back to "
                f"{DEFAULT_DOUBLE_TAP_KEY!r}"
            )
            target = DEFAULT_DOUBLE_TAP_KEY
        self.target = target
        self.window_ms = window_ms
        self._now = now_fn
        self._targets = MODIFIER_KEY_MAP[target]

        self._pressed = False  # target key currently held
        self._clean = False  # current press has seen no other event
        self._first_release_time: float | None = None  # first clean tap release

    def on_press(self, key: Any) -> bool:
        """Feed a key press event. Always returns False (fires on release)."""
        if key in self._targets:
            # SPEC §13.1-A-2: _clean=True only on "not pressed → pressed" transition,
            # not on OS autorepeat (when _pressed is already True).
            if not self._pressed:
                self._clean = True
            self._pressed = True
        else:
            # SPEC §13.1-A-1: Other keys only dirty a tap if currently in progress.
            # If waiting between taps (_pressed=False), don't reset first_release_time.
            if self._pressed:
                self._clean = False
        return False

    def on_release(self, key: Any) -> bool:
        """Feed a key release event. Returns True when a double-tap fires."""
        if key not in self._targets:
            if self._pressed:
                self._clean = False
            # SPEC §13.1-A-1: Don't clear first_release_time if waiting between taps
            return False

        was_clean = self._pressed and self._clean
        self._pressed = False
        self._clean = False

        if not was_clean:
            self._first_release_time = None
            return False

        now = self._now()
        if (
            self._first_release_time is not None
            and (now - self._first_release_time) * 1000.0 <= self.window_ms
        ):
            self._first_release_time = None  # reset: 3rd tap does not re-fire
            return True

        self._first_release_time = now
        return False

    def reset(self) -> None:
        """Reset all internal state (SPEC §13.1-A-1)."""
        self._pressed = False
        self._clean = False
        self._first_release_time = None


class HotkeyManager:
    """
    Global hotkey manager driven by the hotkey config dict (SPEC §13).

    - type="double-tap": Listener + DoubleTapDetector, fires on_toggle.
    - type="combo": mode="toggle" uses GlobalHotKeys (on_toggle);
      mode="hold" uses Listener + HotKey (on_hold_start / on_hold_end).
    - Esc monitoring is off by default; enable only during RECORDING via
      set_esc_enabled(True) (SPEC §13.2).
    - set_enabled(False) makes all hotkeys pass through (tray "有効" off).
    - Config change: stop() this instance, build a new one, start() (§13.2).
    """

    def __init__(
        self,
        hotkey_cfg: dict[str, Any],
        on_toggle: Callable[[], None] | None = None,
        on_hold_start: Callable[[], None] | None = None,
        on_hold_end: Callable[[], None] | None = None,
        on_esc: Callable[[], None] | None = None,
    ):
        hotkey_type = hotkey_cfg.get("type", "double-tap")
        if hotkey_type not in ("double-tap", "combo"):
            logger.warning(
                f"Unknown hotkey type {hotkey_type!r}, falling back to 'double-tap'"
            )
            hotkey_type = "double-tap"
        self.type = hotkey_type

        mode = hotkey_cfg.get("mode", "toggle")
        if mode not in ("toggle", "hold"):
            logger.warning(f"Unknown hotkey mode {mode!r}, falling back to 'toggle'")
            mode = "toggle"
        self.mode = mode

        self.combo = validate_combo(hotkey_cfg.get("combo", DEFAULT_COMBO))
        self.double_tap_key = hotkey_cfg.get("double_tap_key", DEFAULT_DOUBLE_TAP_KEY)
        self.double_tap_window_ms = hotkey_cfg.get(
            "double_tap_window_ms", DEFAULT_DOUBLE_TAP_WINDOW_MS
        )

        # SPEC §13.1-A-2: Long-press (push-to-talk) support for double-tap mode
        self.hold_to_record = hotkey_cfg.get("hold_to_record", DEFAULT_HOLD_TO_RECORD)
        self.hold_threshold_ms = hotkey_cfg.get("hold_threshold_ms", 300)

        self.on_toggle = on_toggle
        self.on_hold_start = on_hold_start
        self.on_hold_end = on_hold_end
        self.on_esc = on_esc

        self.enabled = True
        self.last_fire_ts: float = 0.0  # PERF measurement (SPEC §14.2)
        self._listener: keyboard.Listener | None = None
        self._esc_listener: keyboard.Listener | None = None
        self._detector: DoubleTapDetector | None = None
        self._hotkey: keyboard.HotKey | None = None
        self._main_key = None
        self._held = False

        # SPEC §13.1-A-2: Long-press state (double-tap mode only)
        self._dt_lock = threading.Lock()
        self._dt_held = False  # target key currently pressed
        self._hold_timer: threading.Timer | None = None
        self._hold_confirmed = False  # long-press threshold reached

    def start(self) -> None:
        """
        Start listening for the global hotkey.

        May raise on macOS if Input Monitoring permission is missing;
        callers should catch and continue (SPEC §14).
        """
        if self._listener is not None:
            return

        if self.type == "double-tap":
            self._detector = DoubleTapDetector(
                self.double_tap_key, self.double_tap_window_ms
            )
            self._listener = keyboard.Listener(
                on_press=self._dt_on_press,
                on_release=self._dt_on_release,
            )
        elif self.mode == "toggle":
            self._listener = keyboard.GlobalHotKeys({self.combo: self._fire_toggle})
        else:  # combo + hold
            keys = keyboard.HotKey.parse(self.combo)
            self._main_key = keys[-1]
            self._hotkey = keyboard.HotKey(keys, self._fire_hold_start)
            self._listener = keyboard.Listener(
                on_press=self._hold_on_press,
                on_release=self._hold_on_release,
            )
        self._listener.start()
        logger.info(
            f"Hotkey listener started: type={self.type} "
            f"({describe_hotkey(self._as_cfg())})"
        )

    def stop(self) -> None:
        """Stop all listeners."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self.set_esc_enabled(False)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable hotkey handling (disabled = keys pass through)."""
        self.enabled = enabled
        logger.info(f"Hotkeys {'enabled' if enabled else 'disabled'}")

    def set_esc_enabled(self, enabled: bool) -> None:
        """
        Start/stop the Esc listener. Only call with True during RECORDING.
        """
        if enabled and self._esc_listener is None:
            try:
                self._esc_listener = keyboard.Listener(on_press=self._esc_on_press)
                self._esc_listener.start()
            except Exception as e:
                logger.error(f"Failed to start Esc listener: {e}")
                self._esc_listener = None
        elif not enabled and self._esc_listener is not None:
            try:
                self._esc_listener.stop()
            except Exception:
                pass
            self._esc_listener = None

    def _as_cfg(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "double_tap_key": self.double_tap_key,
            "double_tap_window_ms": self.double_tap_window_ms,
            "mode": self.mode,
            "combo": self.combo,
        }

    # --- internal callbacks (pynput threads) ---

    def _dt_on_press(self, key) -> None:
        if self._detector is None:
            return
        try:
            # Check if this is the target key (SPEC §13.1-A-2)
            is_target = key in self._detector._targets
            old_pressed = self._detector._pressed

            # Feed to detector first
            self._detector.on_press(key)

            # Handle long-press logic (SPEC §13.1-A-2)
            with self._dt_lock:
                if is_target and not old_pressed:
                    # "not pressed → pressed" transition: new press, not autorepeat
                    self._dt_held = True
                    if self.hold_to_record:
                        # Start hold timer
                        if self._hold_timer is not None:
                            self._hold_timer.cancel()
                        self._hold_timer = threading.Timer(
                            self.hold_threshold_ms / 1000.0, self._on_hold_timer_fire
                        )
                        self._hold_timer.start()
                elif not is_target and self._dt_held and self._hold_timer is not None:
                    # Other key pressed while holding target key: cancel timer
                    self._hold_timer.cancel()
                    self._hold_timer = None
        except Exception:
            logger.exception("Error in double-tap press handler")

    def _dt_on_release(self, key) -> None:
        if self._detector is None:
            return
        try:
            is_target = key in self._detector._targets

            if is_target:
                # Handle long-press release (SPEC §13.1-A-2)
                with self._dt_lock:
                    self._dt_held = False
                    timer_to_cancel = self._hold_timer
                    was_confirmed = self._hold_confirmed
                    self._hold_timer = None

                if timer_to_cancel is not None:
                    timer_to_cancel.cancel()

                if was_confirmed:
                    # Long-press was confirmed: emit on_hold_end, reset detector
                    self._hold_confirmed = False
                    if self.on_hold_end is not None:
                        try:
                            self.on_hold_end()
                        except Exception:
                            logger.exception("Error in on_hold_end callback")
                    self._detector.reset()
                    return
                # If not confirmed, fall through to normal tap detection

            # Feed to detector for normal tap detection
            if self._detector.on_release(key):
                self._fire_toggle()
        except Exception:
            logger.exception("Error in double-tap release handler")

    def _on_hold_timer_fire(self) -> None:
        """Timer callback for long-press threshold (SPEC §13.1-A-2)."""
        try:
            with self._dt_lock:
                if not self._dt_held:
                    # Key was already released (race with _dt_on_release);
                    # do not confirm a hold or fire on_hold_start for a key
                    # that is no longer down (would orphan on_hold_end).
                    return
                self._hold_confirmed = True
                # PERF measurement: fire→capture latency (SPEC §14.2)
                self.last_fire_ts = time.perf_counter()
            # Emit callback outside the lock
            if self.on_hold_start is not None:
                try:
                    self.on_hold_start()
                except Exception:
                    logger.exception("Error in on_hold_start callback")
        except Exception:
            logger.exception("Error in hold timer fire handler")

    def _fire_toggle(self) -> None:
        if not self.enabled:
            return
        # Record fire timestamp for PERF measurement (SPEC §14.2)
        self.last_fire_ts = time.perf_counter()
        if self.on_toggle is not None:
            try:
                self.on_toggle()
            except Exception:
                logger.exception("Error in on_toggle callback")

    def _fire_hold_start(self) -> None:
        if not self.enabled:
            return
        if self._held:
            return
        self._held = True
        # Record fire timestamp for PERF measurement (SPEC §14.2)
        self.last_fire_ts = time.perf_counter()
        if self.on_hold_start is not None:
            try:
                self.on_hold_start()
            except Exception:
                logger.exception("Error in on_hold_start callback")

    def _hold_on_press(self, key) -> None:
        if self._listener is None or self._hotkey is None:
            return
        try:
            self._hotkey.press(self._listener.canonical(key))
        except Exception:
            logger.exception("Error in hold press handler")

    def _hold_on_release(self, key) -> None:
        if self._listener is None or self._hotkey is None:
            return
        try:
            canonical = self._listener.canonical(key)
            self._hotkey.release(canonical)
            if self._held and canonical == self._main_key:
                self._held = False
                if self.on_hold_end is not None:
                    self.on_hold_end()
        except Exception:
            logger.exception("Error in hold release handler")

    def _esc_on_press(self, key) -> None:
        if key == keyboard.Key.esc and self.on_esc is not None:
            try:
                self.on_esc()
            except Exception:
                logger.exception("Error in on_esc callback")
