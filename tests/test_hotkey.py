"""Test hotkey logic: combo validation, DoubleTapDetector, describe_hotkey (SPEC §13, §17)."""

import sys
import time
from unittest.mock import MagicMock

from pynput.keyboard import Key

from koekichi.hotkey import (
    DEFAULT_COMBO,
    DoubleTapDetector,
    HotkeyManager,
    describe_hotkey,
    validate_combo,
)


class FakeClock:
    """Manually advanced clock for deterministic tests (now_fn injection)."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance_ms(self, ms: float) -> None:
        self.t += ms / 1000.0


def _tap(detector: DoubleTapDetector, key) -> bool:
    """Perform a clean press+release; return True if the release fired."""
    detector.on_press(key)
    return detector.on_release(key)


class TestValidateCombo:
    """Test combo string validation and fallback."""

    def test_valid_default_combo(self) -> None:
        combo = "<ctrl>+<shift>+<space>"
        assert validate_combo(combo) == combo

    def test_valid_cmd_combo(self) -> None:
        combo = "<cmd>+<shift>+d"
        assert validate_combo(combo) == combo

    def test_invalid_combo_falls_back(self) -> None:
        assert validate_combo("<notakey>+++") == DEFAULT_COMBO

    def test_empty_combo_falls_back(self) -> None:
        assert validate_combo("") == DEFAULT_COMBO


class TestDoubleTapDetector:
    """SPEC §17: DoubleTapDetector deterministic tests via now_fn injection."""

    def test_clean_double_tap_fires(self) -> None:
        """Two clean taps within the window fire on the second release."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        assert _tap(detector, Key.alt) is False  # first tap
        clock.advance_ms(200)
        assert _tap(detector, Key.alt) is True  # second tap fires

    def test_other_key_during_press_does_not_fire(self) -> None:
        """A key event during press->release makes the tap unclean."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        # Dirty tap: Alt+C style chord
        detector.on_press(Key.alt)
        detector.on_press("c")
        detector.on_release("c")
        assert detector.on_release(Key.alt) is False

        # A following clean tap is only tap #1 (no credit from the dirty tap)
        clock.advance_ms(100)
        assert _tap(detector, Key.alt) is False

    def test_window_exceeded_does_not_fire(self) -> None:
        """Second tap after window_ms does not fire."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        assert _tap(detector, Key.alt) is False
        clock.advance_ms(500)  # > 400ms
        assert _tap(detector, Key.alt) is False

        # But that late tap counts as a new first tap
        clock.advance_ms(200)
        assert _tap(detector, Key.alt) is True

    def test_triple_tap_fires_once_then_two_more_taps_refire(self) -> None:
        """3 taps fire once (state resets on fire); the next 2 taps fire again."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        assert _tap(detector, Key.alt) is False  # tap 1
        clock.advance_ms(200)
        assert _tap(detector, Key.alt) is True  # tap 2: fires
        clock.advance_ms(200)
        assert _tap(detector, Key.alt) is False  # tap 3: no fire (state was reset)

        # After the triple tap, the next tap pairs with tap 3 and fires again
        clock.advance_ms(200)
        assert _tap(detector, Key.alt) is True

    def test_left_right_variant_mix_fires(self) -> None:
        """alt_l followed by alt_r within window fires (same logical key)."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        assert _tap(detector, Key.alt_l) is False
        clock.advance_ms(150)
        assert _tap(detector, Key.alt_r) is True


class TestDoubleTapDetectorBugFixes:
    """Test SPEC §13.1-A-1 bug fixes: unrelated keys and autorepeat."""

    def test_unrelated_key_during_waiting_does_not_cancel_first_tap(self) -> None:
        """Unrelated key during tap waiting (not pressed) should not reset first_release_time."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        # First clean tap
        assert _tap(detector, Key.alt) is False
        clock.advance_ms(100)

        # Unrelated key press+release while waiting (not pressing target key)
        detector.on_press("c")
        detector.on_release("c")

        # Second tap should still pair with first tap and fire
        clock.advance_ms(100)
        assert _tap(detector, Key.alt) is True

    def test_autorepeat_does_not_restore_clean_flag(self) -> None:
        """OS autorepeat press should not restore _clean flag after interrupt."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        # Start first tap
        detector.on_press(Key.alt)
        clock.advance_ms(100)

        # Interrupt with another key
        detector.on_press("c")
        assert detector._clean is False  # Tap is dirty

        # Release the other key
        detector.on_release("c")

        # OS autorepeat of Alt (alt still held down)
        detector.on_press(Key.alt)
        # _clean should remain False (not be restored to True)
        assert detector._clean is False

        # Verify that the release is not clean
        detector.on_release(Key.alt)
        # Since it wasn't clean, first_release_time should be cleared
        assert detector._first_release_time is None

    def test_reset_clears_all_state(self) -> None:
        """reset() should clear _pressed, _clean, and _first_release_time."""
        clock = FakeClock()
        detector = DoubleTapDetector("alt", window_ms=400, now_fn=clock)

        # Build up some state
        detector.on_press(Key.alt)
        clock.advance_ms(100)
        detector.on_release(Key.alt)

        # Verify state was set
        assert detector._first_release_time is not None

        # Reset
        detector.reset()

        # All state should be cleared
        assert detector._pressed is False
        assert detector._clean is False
        assert detector._first_release_time is None


class TestDescribeHotkey:
    """Test human-readable hotkey descriptions."""

    def test_describe_double_tap(self) -> None:
        # hold_to_record omitted -> defaults to True (SPEC §13.1-A-2, v1.3),
        # so the default description includes the hold suffix.
        cfg = {"type": "double-tap", "double_tap_key": "alt"}
        expected_key = "Option" if sys.platform == "darwin" else "Alt"
        assert describe_hotkey(cfg) == f"{expected_key} 2回押し / 長押し"

    def test_describe_combo(self) -> None:
        cfg = {"type": "combo", "combo": "<ctrl>+<shift>+<space>"}
        assert describe_hotkey(cfg) == "Ctrl+Shift+Space"

    def test_describe_double_tap_with_hold_to_record(self) -> None:
        """SPEC §13.1-A-2: describe_hotkey should append ' / 長押し' when hold_to_record is True."""
        cfg = {
            "type": "double-tap",
            "double_tap_key": "alt",
            "hold_to_record": True,
        }
        expected_key = "Option" if sys.platform == "darwin" else "Alt"
        assert describe_hotkey(cfg) == f"{expected_key} 2回押し / 長押し"

    def test_describe_double_tap_without_hold_to_record(self) -> None:
        """Without hold_to_record or False, no ' / 長押し' suffix."""
        cfg = {
            "type": "double-tap",
            "double_tap_key": "alt",
            "hold_to_record": False,
        }
        expected_key = "Option" if sys.platform == "darwin" else "Alt"
        assert describe_hotkey(cfg) == f"{expected_key} 2回押し"


class TestHotkeyLongPress:
    """Test SPEC §13.1-A-2: Long-press (push-to-talk) support."""

    def test_long_press_fires_on_hold_start(self) -> None:
        """Hold timer fires after hold_threshold_ms and calls on_hold_start."""
        cfg = {
            "type": "double-tap",
            "double_tap_key": "alt",
            "hold_to_record": True,
            "hold_threshold_ms": 50,  # 50ms for test
        }
        hold_start_callback = MagicMock()
        toggle_callback = MagicMock()
        mgr = HotkeyManager(
            cfg, on_toggle=toggle_callback, on_hold_start=hold_start_callback
        )
        mgr.enabled = True

        # Need to start the hotkey listener (which initializes _detector)
        # For this test, we'll initialize detector manually
        from koekichi.hotkey import DoubleTapDetector
        mgr._detector = DoubleTapDetector(mgr.double_tap_key, mgr.double_tap_window_ms)

        # Press target key
        mgr._dt_on_press(Key.alt)
        # Let the timer fire
        time.sleep(0.1)  # 100ms, longer than 50ms threshold

        # on_hold_start should have been called (in a separate thread)
        # Note: This is a race condition. In real code, Timer runs in its own thread.
        # For a deterministic test, we'd need to mock threading.Timer, but we use
        # real timers here to verify basic functionality.
        # Just verify that _hold_confirmed was set
        assert mgr._hold_confirmed is True

    def test_short_release_before_threshold_triggers_tap_detection(self) -> None:
        """Release before hold_threshold_ms should trigger normal tap detection."""
        cfg = {
            "type": "double-tap",
            "double_tap_key": "alt",
            "hold_to_record": True,
            "hold_threshold_ms": 500,  # 500ms threshold
        }
        hold_start_callback = MagicMock()
        toggle_callback = MagicMock()
        mgr = HotkeyManager(
            cfg, on_toggle=toggle_callback, on_hold_start=hold_start_callback
        )
        mgr.enabled = True

        # Press and quickly release (much faster than 500ms)
        mgr._dt_on_press(Key.alt)
        time.sleep(0.05)  # 50ms, well below 500ms
        mgr._dt_on_release(Key.alt)

        # on_hold_start should NOT have been called (timer didn't fire)
        hold_start_callback.assert_not_called()

        # Timer should have been cancelled
        assert mgr._hold_timer is None
        assert mgr._hold_confirmed is False

    def test_timer_fire_after_release_does_not_call_on_hold_start(self) -> None:
        """
        Regression test: if the key is released before the (racing) Timer
        thread runs _on_hold_timer_fire, on_hold_start must NOT fire and
        _hold_confirmed must remain False. Otherwise a ghost recording
        starts with no matching on_hold_end.
        """
        cfg = {
            "type": "double-tap",
            "double_tap_key": "alt",
            "hold_to_record": True,
            "hold_threshold_ms": 300,
        }
        hold_start_callback = MagicMock()
        hold_end_callback = MagicMock()
        mgr = HotkeyManager(
            cfg, on_hold_start=hold_start_callback, on_hold_end=hold_end_callback
        )
        mgr.enabled = True

        from koekichi.hotkey import DoubleTapDetector
        mgr._detector = DoubleTapDetector(mgr.double_tap_key, mgr.double_tap_window_ms)

        # Press the key: this starts the hold timer.
        mgr._dt_on_press(Key.alt)

        # Simulate release happening first (race): _dt_held becomes False,
        # timer is cancelled and cleared, but pretend the Timer thread's
        # function body was already entered before cancellation took effect
        # by calling _on_hold_timer_fire directly after the release.
        mgr._dt_on_release(Key.alt)

        # Now invoke the timer callback as if the racing Timer thread still
        # ran it despite the (attempted) cancellation.
        mgr._on_hold_timer_fire()

        # on_hold_start must not have fired, and no ghost hold is confirmed.
        hold_start_callback.assert_not_called()
        assert mgr._hold_confirmed is False

    def test_hold_confirmed_records_last_fire_ts(self) -> None:
        """SPEC §14.2: confirming a long-press should update last_fire_ts."""
        cfg = {
            "type": "double-tap",
            "double_tap_key": "alt",
            "hold_to_record": True,
            "hold_threshold_ms": 50,
        }
        hold_start_callback = MagicMock()
        mgr = HotkeyManager(cfg, on_hold_start=hold_start_callback)
        mgr.enabled = True

        from koekichi.hotkey import DoubleTapDetector
        mgr._detector = DoubleTapDetector(mgr.double_tap_key, mgr.double_tap_window_ms)

        assert mgr.last_fire_ts == 0.0

        t_before = time.perf_counter()
        mgr._dt_on_press(Key.alt)
        time.sleep(0.1)  # let the 50ms timer fire
        t_after = time.perf_counter()

        assert mgr._hold_confirmed is True
        assert t_before <= mgr.last_fire_ts <= t_after
        hold_start_callback.assert_called_once()


class TestLastFireTs:
    """Test PERF measurement: last_fire_ts recording (SPEC §14.2)."""

    def test_fire_toggle_records_timestamp(self) -> None:
        """_fire_toggle should record time.perf_counter() into last_fire_ts."""
        cfg = {"type": "double-tap", "double_tap_key": "alt"}
        callback = MagicMock()
        mgr = HotkeyManager(cfg, on_toggle=callback)

        assert mgr.last_fire_ts == 0.0

        # Call _fire_toggle (enabled)
        mgr.enabled = True
        t_before = time.perf_counter()
        mgr._fire_toggle()
        t_after = time.perf_counter()

        # last_fire_ts should be set to a time in the range
        assert t_before <= mgr.last_fire_ts <= t_after
        callback.assert_called_once()

    def test_fire_hold_start_records_timestamp(self) -> None:
        """_fire_hold_start should record time.perf_counter() into last_fire_ts."""
        cfg = {"type": "combo", "combo": "<ctrl>+<space>", "mode": "hold"}
        callback = MagicMock()
        mgr = HotkeyManager(cfg, on_hold_start=callback)

        assert mgr.last_fire_ts == 0.0
        assert mgr._held is False

        # Call _fire_hold_start (enabled)
        mgr.enabled = True
        t_before = time.perf_counter()
        mgr._fire_hold_start()
        t_after = time.perf_counter()

        # last_fire_ts should be set
        assert t_before <= mgr.last_fire_ts <= t_after
        assert mgr._held is True
        callback.assert_called_once()

    def test_fire_disabled_does_not_record(self) -> None:
        """If enabled=False, _fire_toggle should not record timestamp."""
        cfg = {"type": "double-tap", "double_tap_key": "alt"}
        callback = MagicMock()
        mgr = HotkeyManager(cfg, on_toggle=callback)

        mgr.enabled = False
        mgr._fire_toggle()

        # last_fire_ts should remain 0
        assert mgr.last_fire_ts == 0.0
        callback.assert_not_called()
