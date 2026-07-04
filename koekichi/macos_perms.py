"""macOS permission self-checks (SPEC §14.1).

Darwin-only utilities to detect whether Accessibility and Input Monitoring
permissions are granted. Non-darwin platforms always return True.
"""

import ctypes
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

PANE_ACCESSIBILITY = "x-apple.systempreference:com.apple.preference.security?Privacy_Accessibility"
PANE_INPUT_MONITORING = "x-apple.systempreference:com.apple.preference.security?Privacy_ListenEvent"


def accessibility_trusted() -> bool:
    """
    Check if the process has Accessibility permission (SPEC §14.1).

    Uses ApplicationServices.AXIsProcessTrusted() via ctypes.
    Returns True on non-darwin platforms or if the check fails (fail-open).
    """
    if sys.platform != "darwin":
        return True
    try:
        AS = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        AS.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(AS.AXIsProcessTrusted())
    except Exception:
        logger.exception("AXIsProcessTrusted check failed")
        return True  # fail open


def input_monitoring_granted() -> bool:
    """
    Check if Input Monitoring is granted (SPEC §14.1).

    Uses IOKit.IOHIDCheckAccess(kIOHIDRequestTypeListenEvent=1) via ctypes.
    Returns 0 (granted) or non-zero (denied).
    Returns True on non-darwin platforms or if the check fails (fail-open).
    """
    if sys.platform != "darwin":
        return True
    try:
        IOKit = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/IOKit.framework/IOKit"
        )
        IOKit.IOHIDCheckAccess.restype = ctypes.c_int
        IOKit.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
        # kIOHIDRequestTypeListenEvent = 1; 0 = granted, non-zero = denied
        return IOKit.IOHIDCheckAccess(1) == 0
    except Exception:
        logger.exception("IOHIDCheckAccess check failed")
        return True


def open_settings_pane(url: str) -> None:
    """Open a macOS System Settings privacy pane via `open` command."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.Popen(["open", url])
    except Exception:
        logger.exception("Failed to open settings pane %s", url)
