"""Tests for the macOS TSM crash workaround (SPEC §13.3)."""

import sys
import threading

import pytest

import koekichi.macos_tsm as macos_tsm


def test_prime_is_noop_off_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off darwin, prime_keyboard_layout() returns without touching state."""
    monkeypatch.setattr(macos_tsm.sys, "platform", "linux")
    monkeypatch.setattr(macos_tsm, "_primed", False)

    macos_tsm.prime_keyboard_layout()  # must not raise

    assert macos_tsm._primed is False


@pytest.mark.skipif(
    sys.platform != "darwin", reason="TSM patching only applies on macOS"
)
def test_prime_patches_pynput_and_works_off_main_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On darwin, prime patches keycode_context and it works off-thread."""
    import pynput._util.darwin as d

    original_context = d.keycode_context

    # Reset the module-level guard so priming actually runs in this test.
    monkeypatch.setattr(macos_tsm, "_primed", False)
    macos_tsm.prime_keyboard_layout()

    # The function object must have been replaced (patched).
    assert d.keycode_context is not original_context

    # Calling it from a background thread must not raise (no TSM call).
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            with d.keycode_context() as _ctx:
                pass
        except BaseException as exc:  # noqa: BLE001 - propagate to parent
            errors.append(exc)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()

    assert errors == [], f"keycode_context raised off-thread: {errors!r}"
