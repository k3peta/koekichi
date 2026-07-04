"""macOS TSM crash workaround (SPEC §13.3).

pynput queries the keyboard layout via Text Input Source Manager APIs that
abort (dispatch_assert_queue / SIGTRAP) when called off the main thread on
recent macOS. We prime the layout once on the main thread and monkeypatch
pynput to reuse the cached value so it never calls TSM again.
"""
import contextlib
import logging
import sys

logger = logging.getLogger(__name__)

_primed = False


def prime_keyboard_layout() -> None:
    """Cache the keyboard layout on the main thread and patch pynput.

    No-op off darwin. Must be called on the main thread before any
    pynput Listener/Controller is created. Safe to call more than once.
    """
    global _primed
    if sys.platform != "darwin" or _primed:
        return
    try:
        import pynput._util.darwin as d
        import pynput.keyboard._darwin as kd

        with d.keycode_context() as ctx:
            cached_ctx = ctx
        cached_map = d.get_unicode_to_keycode_map()

        @contextlib.contextmanager
        def _patched_context():
            yield cached_ctx

        def _patched_map():
            return dict(cached_map)

        for mod in (d, kd):
            mod.keycode_context = _patched_context
            mod.get_unicode_to_keycode_map = _patched_map

        _primed = True
        logger.info(
            "Primed keyboard layout on main thread "
            f"(map_size={len(cached_map)}); pynput TSM calls disabled"
        )
    except Exception:
        logger.exception("Failed to prime keyboard layout; continuing unpatched")
