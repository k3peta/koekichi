"""Offscreen regression tests for the tray menu (SPEC §11.2).

Requires QT_QPA_PLATFORM=offscreen (set in CI / pytest invocation) since it
instantiates real PySide6 widgets.

On macOS the menu must NOT be attached via setContextMenu: native
NSStatusItem menu tracking crashes with an NSEvent clickCount assertion when
the app's current event is not a mouse event (frequent with the double-tap
hotkey, which delivers flagsChanged events). The menu is popped up manually
from the activated signal instead.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from koekichi.config import DEFAULT_CONFIG
from koekichi.ui.tray import Tray


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def test_no_native_context_menu_on_darwin(qapp: QApplication) -> None:
    """macOS: contextMenu() must be unset (crash workaround); others keep it."""
    tray = Tray(DEFAULT_CONFIG)
    if sys.platform == "darwin":
        assert tray.contextMenu() is None
    else:
        assert tray.contextMenu() is tray._menu


def test_menu_has_quit_action(qapp: QApplication) -> None:
    """The manually popped-up menu still carries all actions (e.g. 終了)."""
    tray = Tray(DEFAULT_CONFIG)
    action_texts = [action.text() for action in tray._menu.actions()]
    assert "終了" in action_texts
